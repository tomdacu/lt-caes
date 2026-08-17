"""Wet-rated expander lower-envelope and reference liquid-cap tests."""

import pytest

from caes.moisture import (
    phase_change_temperature_k,
    saturation_humidity_ratio,
)
from caes.thermal_limits import (
    DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION,
    EXPANDER_ICE_MARGIN_K,
    REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION,
    WATER_FREEZING_TEMPERATURE_K,
    dry_air_wet_expansion_approximation_ok,
    maximum_possible_liquid_mass_fraction,
    minimum_wet_expander_temperature_k,
    reference_wet_expander_liquid_envelope_ok,
    wet_expander_hard_floor_temperature_k,
)


def test_liquid_dew_point_is_crossable_but_freezing_is_not():
    pressure_pa = 100.0e5
    humidity_ratio = saturation_humidity_ratio(pressure_pa, 273.15 + 15.0)

    assert phase_change_temperature_k(
        pressure_pa, humidity_ratio
    ) == pytest.approx(273.15 + 15.0, abs=0.02)
    assert wet_expander_hard_floor_temperature_k(
        pressure_pa, humidity_ratio
    ) == pytest.approx(WATER_FREEZING_TEMPERATURE_K)
    assert minimum_wet_expander_temperature_k(
        pressure_pa, humidity_ratio
    ) == pytest.approx(
        WATER_FREEZING_TEMPERATURE_K + EXPANDER_ICE_MARGIN_K
    )


def test_dry_subzero_operation_follows_local_frost_point():
    storage_pressure_pa = 100.0e5
    humidity_ratio = saturation_humidity_ratio(
        storage_pressure_pa, 273.15 + 15.0
    )
    outlet_pressure_pa = 1.01325e5
    frost_k = phase_change_temperature_k(
        outlet_pressure_pa, humidity_ratio
    )

    assert frost_k < WATER_FREEZING_TEMPERATURE_K
    assert wet_expander_hard_floor_temperature_k(
        outlet_pressure_pa, humidity_ratio
    ) == pytest.approx(frost_k)
    assert minimum_wet_expander_temperature_k(
        outlet_pressure_pa, humidity_ratio
    ) == pytest.approx(frost_k + EXPANDER_ICE_MARGIN_K)


def test_reference_liquid_screen_uses_wet_stream_mass_basis():
    assert maximum_possible_liquid_mass_fraction(0.01) == pytest.approx(
        0.01 / 1.01
    )
    assert reference_wet_expander_liquid_envelope_ok(0.01)

    humidity_ratio_at_reference_cap = (
        REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION
        / (
            1.0
            - REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION
        )
    )
    assert reference_wet_expander_liquid_envelope_ok(
        humidity_ratio_at_reference_cap
    )
    assert not reference_wet_expander_liquid_envelope_ok(
        humidity_ratio_at_reference_cap * 1.01
    )


def test_dry_air_model_screen_is_stricter_than_hardware_envelope():
    humidity_ratio_at_model_cap = (
        DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION
        / (1.0 - DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION)
    )
    assert dry_air_wet_expansion_approximation_ok(
        humidity_ratio_at_model_cap * 0.999
    )
    assert not dry_air_wet_expansion_approximation_ok(
        humidity_ratio_at_model_cap * 1.001
    )
    assert reference_wet_expander_liquid_envelope_ok(
        humidity_ratio_at_model_cap * 1.001
    )
