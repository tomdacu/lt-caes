"""Shared declarations for the CAES suite.

The LTHP concept is the same two-key configuration literal in every file, and
several files re-derive the same wet-expander envelope check. Both live here, so
a change to the concept definition - or to the envelope tolerance - is one edit
instead of seventeen.
"""

from __future__ import annotations

from dataclasses import replace

from caes import HeatOfftake, OptimizationObjective, PlantConfig
from caes.models import PlantResult
from caes.thermal_limits import (
    minimum_wet_expander_temperature_k,
    wet_expander_hard_floor_temperature_k,
)


LTHP = PlantConfig(
    heat_offtake=HeatOfftake.HEAT_USER,
    optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
)

# Numerical acceptance used throughout the suite. The solver aims exactly AT a
# physical envelope when the interheater duty is the binding constraint, so the
# check has to allow the root's own noise.
ENVELOPE_TOLERANCE_K = 0.02


def lthp(**overrides) -> PlantConfig:
    """LTHP-CAES - heat user plus the combined-delivery objective - with overrides."""

    return replace(LTHP, **overrides)


def assert_expander_envelope(
    result: PlantResult, *, include_throttling: bool = False
) -> None:
    """Every expansion outlet must respect its own pressure-dependent floor.

    An expansion must clear its moisture-safe wet-expander minimum; a throttle
    valve may spend the 10 K margin, but it may never cross the freezing/frost
    hard floor.
    """
    moisture = result.moisture
    assert moisture is not None
    humidity = moisture.stored_air_water_vapor_kg_per_kg_dry_air
    for process in result.discharging.processes:
        if process.kind == "expansion":
            floor_k = minimum_wet_expander_temperature_k(
                process.outlet.pressure_pa, humidity
            )
        elif include_throttling and process.kind == "throttling":
            floor_k = wet_expander_hard_floor_temperature_k(
                process.outlet.pressure_pa, humidity
            )
        else:
            continue
        assert process.outlet.temperature_k >= floor_k - ENVELOPE_TOLERANCE_K, (
            f"{process.kind} outlet at {process.outlet.pressure_bar:.2f} bar reaches "
            f"{process.outlet.temperature_c:.2f} °C, below its "
            f"{floor_k - 273.15:.2f} °C floor"
        )
