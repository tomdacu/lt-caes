"""Count solver work and fingerprint one CAES result deterministically."""

from __future__ import annotations

# ruff: noqa: E402 -- cache/path setup must precede project imports in a script.

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict, replace
from functools import wraps
from hashlib import sha256
import json
from time import perf_counter
from typing import Any, Callable
from unittest.mock import patch

from caes import CAESPlant, PlantConfig, PropertyAPI, load_config
import caes.plant as plant_module


def _fingerprint(result: Any) -> str:
    payload = json.dumps(
        asdict(result), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _counted(
    counter: Counter[str], name: str, function: Callable[..., Any]
) -> Callable[..., Any]:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        counter[name] += 1
        return function(*args, **kwargs)

    return wrapper


def profile(config: PlantConfig, property_api: PropertyAPI) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    methods = (
        "_charge_with_ratios",
        "_discharge_at_supply",
        "_light_discharge_at_supply",
        "_materialize_ladder",
        "_discharge_with_ratios",
        "_solve_extraction_margin",
        "_build_extraction_exchanger",
        "_close_cold_loop",
    )
    with ExitStack() as stack:
        for name in methods:
            original = getattr(CAESPlant, name)
            stack.enter_context(
                patch.object(CAESPlant, name, _counted(counters, name, original))
            )
        stack.enter_context(
            patch.object(
                plant_module,
                "water_ratio_for_duty",
                _counted(
                    counters,
                    "water_ratio_for_duty",
                    plant_module.water_ratio_for_duty,
                ),
            )
        )
        started = perf_counter()
        result = CAESPlant(config, property_api).run()
        elapsed = perf_counter() - started

    processes = result.charging.processes + result.discharging.processes
    return {
        "property_api": property_api.value,
        "expander_stages": config.expander_stages,
        "heat_offtake": config.heat_offtake.value,
        "diagnostic_seconds": elapsed,
        "fingerprint_sha256": _fingerprint(result),
        "counts": dict(sorted(counters.items())),
        "metrics": {
            "compression_j_per_kg": result.compression_work_input_j_per_kg,
            "expansion_j_per_kg": result.expansion_work_output_j_per_kg,
            "round_trip_efficiency": result.round_trip_efficiency,
            "useful_energy_delivery_ratio": result.useful_energy_delivery_ratio,
            "objective_value": (
                result.optimization.objective_value
                if result.optimization is not None
                else None
            ),
            "evaluated_inventory_points": (
                result.optimization.evaluated_points
                if result.optimization is not None
                else None
            ),
            "max_component_first_law_residual_j_per_kg": max(
                (abs(process.first_law_residual_j_per_kg) for process in processes),
                default=0.0,
            ),
            "exergy_balance_residual_j_per_kg": (
                result.exergy.balance_residual_j_per_kg_air
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Count complete solver work independently of machine timing."
    )
    parser.add_argument("--config", type=Path, help="configuration JSON")
    parser.add_argument(
        "--extraction-ntu", type=float, help="override extraction_exchanger_ntu"
    )
    parser.add_argument(
        "--property-api",
        choices=[api.value for api in PropertyAPI],
        default=PropertyAPI.ABSTRACT_STATE.value,
    )
    args = parser.parse_args(argv)

    config = load_config(args.config) if args.config else PlantConfig()
    if args.extraction_ntu is not None:
        config = replace(config, extraction_exchanger_ntu=args.extraction_ntu)
    print(json.dumps(profile(config, PropertyAPI(args.property_api)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
