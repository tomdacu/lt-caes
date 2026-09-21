"""Shared declarations for the CAES suite.

The LTAHP configuration is the same two-key literal in every file, and several
files re-derive the same wet-expander envelope check. Both live here, so a
change to the concept definition - or to the envelope tolerance - is one edit
instead of seventeen.
"""

from __future__ import annotations

from dataclasses import replace

from caes import HeatOfftake, OptimizationObjective, PlantConfig
from caes.models import PlantResult
from caes.thermal_limits import minimum_wet_expander_temperature_k


LTAHP = PlantConfig(
    heat_offtake=HeatOfftake.HEAT_USER,
    optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
)

# Numerical acceptance used throughout the suite. The solver aims exactly AT a
# physical envelope when the interheater duty is the binding constraint, so the
# check has to allow the root's own noise.
ENVELOPE_TOLERANCE_K = 0.02


def ltahp(**overrides) -> PlantConfig:
    """LTAHP-CAES - heat user plus the combined-delivery objective - with overrides."""

    return replace(LTAHP, **overrides)


def assert_expander_envelope(result: PlantResult) -> None:
    """Every expansion outlet must clear its own pressure-dependent floor.

    The stored moisture sets the floor: the wet-expander envelope allows +10 K
    where condensation is possible and the local frost point plus 10 K below
    freezing, and no expansion may cross it.
    """
    moisture = result.moisture
    assert moisture is not None
    humidity = moisture.stored_air_water_vapor_kg_per_kg_dry_air
    for process in result.discharging.processes:
        if process.kind != "expansion":
            continue
        floor_k = minimum_wet_expander_temperature_k(
            process.outlet.pressure_pa, humidity
        )
        assert process.outlet.temperature_k >= floor_k - ENVELOPE_TOLERANCE_K, (
            f"{process.kind} outlet at {process.outlet.pressure_bar:.2f} bar reaches "
            f"{process.outlet.temperature_c:.2f} °C, below its "
            f"{floor_k - 273.15:.2f} °C floor"
        )
