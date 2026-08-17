"""Reproducible end-to-end comparison of CoolProp's two solver front ends."""

# ruff: noqa: E402 -- cache/path setup must precede project imports in a script.

from __future__ import annotations

import sys
from pathlib import Path

# Keep this diagnostic from creating bytecode caches in the OneDrive project.
sys.dont_write_bytecode = True
# Make direct ``python scripts/...`` execution import the adjacent project.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict, replace
from functools import wraps
from time import perf_counter
from typing import Any
from unittest.mock import patch

import CoolProp

from caes import CAESPlant, PlantConfig, PropertyAPI, load_config
from caes.thermodynamics import (
    air_cp,
    state_ph,
    state_pt,
    using_property_api,
    water_saturation_pressure_pa,
    water_saturation_temperature_k,
)


def _first_differences(left: Any, right: Any, path: str = "result") -> list[str]:
    """Return a short structural diff without applying numerical tolerances."""

    if type(left) is not type(right):
        return [f"{path}: types {type(left).__name__} != {type(right).__name__}"]
    if isinstance(left, dict):
        messages: list[str] = []
        if left.keys() != right.keys():
            messages.append(f"{path}: keys differ")
        for key in left.keys() & right.keys():
            messages.extend(_first_differences(left[key], right[key], f"{path}.{key}"))
            if len(messages) >= 20:
                break
        return messages[:20]
    if isinstance(left, (list, tuple)):
        if len(left) != len(right):
            return [f"{path}: lengths {len(left)} != {len(right)}"]
        messages = []
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            messages.extend(
                _first_differences(left_item, right_item, f"{path}[{index}]")
            )
            if len(messages) >= 20:
                break
        return messages[:20]
    return [] if left == right else [f"{path}: {left!r} != {right!r}"]


def _primitive_comparison() -> list[str]:
    pressures = (1e5, 2e5, 5e5, 1e6, 3e6, 5e6, 10e6, 20e6, 30e6)
    temperatures = (180.0, 220.0, 273.15, 288.15, 350.0, 500.0, 700.0, 900.0, 1050.0)
    values: dict[PropertyAPI, list[tuple[float, ...]]] = {}
    for api in PropertyAPI:
        rows = []
        with using_property_api(api):
            for pressure_pa in pressures:
                for temperature_k in temperatures:
                    state = state_pt(pressure_pa, temperature_k, "Air")
                    inverse = state_ph(
                        pressure_pa, state.enthalpy_j_per_kg, "Air"
                    )
                    rows.append(
                        (
                            state.enthalpy_j_per_kg,
                            state.entropy_j_per_kgk,
                            air_cp(pressure_pa, temperature_k, "Air"),
                            inverse.temperature_k,
                            inverse.entropy_j_per_kgk,
                        )
                    )
            saturation_pressure = water_saturation_pressure_pa(373.15)
            rows.append(
                (
                    saturation_pressure,
                    water_saturation_temperature_k(saturation_pressure),
                )
            )
        values[api] = rows
    return _first_differences(
        values[PropertyAPI.ABSTRACT_STATE],
        values[PropertyAPI.PROPS_SI],
        "primitive_grid",
    )


def _solve(config: PlantConfig, api: PropertyAPI) -> tuple[Any, Counter[str], float]:
    counts: Counter[str] = Counter()

    def counted(name: str, function: Any) -> Any:
        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            counts[name] += 1
            return function(*args, **kwargs)

        return wrapper

    with ExitStack() as stack:
        for name in (
            "_light_discharge_at_supply",
            "_materialize_ladder",
            "_discharge_at_supply",
        ):
            original = getattr(CAESPlant, name)
            stack.enter_context(
                patch.object(CAESPlant, name, counted(name, original))
            )
        started = perf_counter()
        result = CAESPlant(config, api).run()
        elapsed = perf_counter() - started
    return result, counts, elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare AbstractState and PropsSI without changing the plant model."
    )
    parser.add_argument("--config", type=Path, help="configuration JSON; defaults to PlantConfig()")
    parser.add_argument(
        "--extraction-ntu", type=float, help="override extraction_exchanger_ntu"
    )
    parser.add_argument(
        "--primitives-only",
        action="store_true",
        help="run only the 1-300 bar, 180-1050 K property grid",
    )
    args = parser.parse_args(argv)

    print(f"CoolProp version: {CoolProp.__version__}")
    primitive_differences = _primitive_comparison()
    print(
        "Primitive grid: "
        + ("IDENTICAL" if not primitive_differences else "DIFFERENT")
    )
    for difference in primitive_differences:
        print(f"  {difference}")
    if args.primitives_only:
        return int(bool(primitive_differences))

    config = load_config(args.config) if args.config else PlantConfig()
    if args.extraction_ntu is not None:
        config = replace(config, extraction_exchanger_ntu=args.extraction_ntu)

    solved = {
        api: _solve(config, api)
        for api in (PropertyAPI.ABSTRACT_STATE, PropertyAPI.PROPS_SI)
    }
    for api, (result, counts, elapsed) in solved.items():
        states = result.charging.states + result.discharging.states
        print(
            f"{api.value}: light_trains={counts['_light_discharge_at_supply']}, "
            f"materializations={counts['_materialize_ladder']}, "
            f"diagnostic_time={elapsed:.3f} s, "
            f"RTE={result.round_trip_efficiency:.12f}, "
            f"P=[{min(s.pressure_pa for s in states) / 1e5:.3f}, "
            f"{max(s.pressure_pa for s in states) / 1e5:.3f}] bar, "
            f"T=[{min(s.temperature_k for s in states):.3f}, "
            f"{max(s.temperature_k for s in states):.3f}] K"
        )

    differences = _first_differences(
        asdict(solved[PropertyAPI.ABSTRACT_STATE][0]),
        asdict(solved[PropertyAPI.PROPS_SI][0]),
    )
    print("Complete PlantResult: " + ("IDENTICAL" if not differences else "DIFFERENT"))
    for difference in differences:
        print(f"  {difference}")
    if solved[PropertyAPI.ABSTRACT_STATE][1] != solved[PropertyAPI.PROPS_SI][1]:
        print("  solver-work counts differ")
        differences.append("solver-work counts differ")
    print("Timing is diagnostic only; use train counts to compare solver complexity.")
    return int(bool(primitive_differences or differences))


if __name__ == "__main__":
    raise SystemExit(main())
