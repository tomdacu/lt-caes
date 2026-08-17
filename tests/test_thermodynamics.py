from dataclasses import asdict, replace
from math import exp

import pytest

from caes import CAESPlant, PlantConfig, PlantMode
from caes.heat_exchangers import cool_air_with_water, exchange_air_with_ambient_ntu
from caes.thermodynamics import (
    COOL_ONLY,
    HEAT_ONLY,
    PropertyAPI,
    air_cp,
    compress,
    current_property_api,
    expand,
    state_ph,
    state_pt,
    using_property_api,
    water_saturation_pressure_pa,
    water_saturation_temperature_k,
)


@pytest.fixture
def air_state():
    return state_pt(101_325.0, 288.15, "Air")


@pytest.mark.parametrize(
    ("pressure_pa", "temperature_k"),
    [(101_325.0, 180.0), (1.0e6, 288.15), (10.0e6, 500.0), (30.0e6, 1050.0)],
)
def test_property_front_ends_use_the_same_heos_state(
    pressure_pa, temperature_k
):
    values = {}
    for api in PropertyAPI:
        with using_property_api(api):
            state = state_pt(pressure_pa, temperature_k, "Air")
            inverse = state_ph(pressure_pa, state.enthalpy_j_per_kg, "Air")
            values[api] = (
                state,
                inverse,
                air_cp(pressure_pa, temperature_k, "Air"),
            )

    assert values[PropertyAPI.ABSTRACT_STATE] == values[PropertyAPI.PROPS_SI]


def test_property_api_context_covers_water_and_restores_the_default():
    assert current_property_api() is PropertyAPI.ABSTRACT_STATE
    values = {}
    for api in PropertyAPI:
        with using_property_api(api):
            pressure = water_saturation_pressure_pa(373.15)
            values[api] = (pressure, water_saturation_temperature_k(pressure))
    assert values[PropertyAPI.ABSTRACT_STATE] == values[PropertyAPI.PROPS_SI]
    assert current_property_api() is PropertyAPI.ABSTRACT_STATE


def test_property_api_switch_covers_an_entire_plant_solve():
    # One-stage diabatic is fast enough for the unit suite but still traverses
    # PT, PH and PS air calls, water saturation and moisture diagnostics.
    config = replace(
        PlantConfig(mode=PlantMode.DIABATIC),
        compressor_stages=1,
        expander_stages=1,
    )
    abstract = CAESPlant(config, PropertyAPI.ABSTRACT_STATE).run()
    props = CAESPlant(config, PropertyAPI.PROPS_SI).run()
    assert asdict(abstract) == asdict(props)


def test_turbomachinery_closes_first_law(air_state):
    compressor = compress(air_state, 600_000.0, 0.86, "Air")
    turbine = expand(compressor.outlet, 101_325.0, 0.88, "Air")
    assert compressor.work_j_per_kg > 0
    assert turbine.work_j_per_kg < 0
    assert abs(compressor.first_law_residual_j_per_kg) < 1e-5
    assert abs(turbine.first_law_residual_j_per_kg) < 1e-5


def test_ntu_model_is_bounded_by_maximum_possible_duty():
    hot_air = state_pt(600_000.0, 450.0, "Air")
    process = cool_air_with_water(hot_air, 293.15, 0.02, "Air", 2.0, 1.0)
    hx = process.heat_exchanger
    assert hx is not None
    assert 0 < hx.effectiveness < 1
    assert 293.15 < hx.water_outlet_temperature_k < 450.0
    assert process.outlet.temperature_k < 450.0
    assert abs(process.first_law_residual_j_per_kg) < 1e-5


def test_higher_ntu_brings_the_air_outlet_closer_to_the_cold_water():
    hot_air = state_pt(600_000.0, 450.0, "Air")
    low_ntu = cool_air_with_water(hot_air, 293.15, 0.02, "Air", 1.0, 0.25)
    high_ntu = cool_air_with_water(hot_air, 293.15, 0.02, "Air", 8.0, 0.25)

    assert low_ntu.heat_exchanger.ntu == 1.0
    assert high_ntu.heat_exchanger.ntu == 8.0
    assert high_ntu.outlet.temperature_k < low_ntu.outlet.temperature_k
    assert high_ntu.outlet.temperature_k - 293.15 < low_ntu.outlet.temperature_k - 293.15


def test_ambient_cooler_is_the_cr_zero_limit_of_the_shared_counterflow_code():
    hot_air = state_pt(600_000.0, 450.0, "Air")
    process = exchange_air_with_ambient_ntu(
        hot_air, 288.15, 0.02, "Air", 3.0, "intercooling", COOL_ONLY,
    )
    # The atmosphere has no finite second stream to report.
    assert process.heat_exchanger is None
    assert 288.15 < process.outlet.temperature_k < 450.0
    # Cr = 0: the terminal gap retains exp(-NTU) of the inlet gap,
    # up to the small variable-cp correction.
    gap_ratio = (process.outlet.temperature_k - 288.15) / (450.0 - 288.15)
    assert gap_ratio == pytest.approx(exp(-3.0), rel=0.05)
    assert abs(process.first_law_residual_j_per_kg) < 1e-5


def test_ambient_exchangers_are_one_way_devices():
    cold_air = state_pt(200_000.0, 270.0, "Air")
    cooler = exchange_air_with_ambient_ntu(
        cold_air, 288.15, 0.02, "Air", 3.0, "intercooling", COOL_ONLY,
    )
    # A cooler cannot heat air arriving colder than the atmosphere:
    # it degenerates to an isenthalpic pressure drop.
    assert cooler.outlet.enthalpy_j_per_kg == pytest.approx(cold_air.enthalpy_j_per_kg)
    assert cooler.heat_to_air_j_per_kg == 0.0

    reheater = exchange_air_with_ambient_ntu(
        cold_air, 288.15, 0.02, "Air", 3.0, "ambient_reheat", HEAT_ONLY,
    )
    assert reheater.outlet.temperature_k > 270.0
    assert reheater.outlet.temperature_k < 288.15
    assert reheater.heat_to_air_j_per_kg > 0.0
