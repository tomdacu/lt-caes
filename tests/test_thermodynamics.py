import pytest

from caes.config import HeatExchangerModel
from caes.heat_exchangers import cool_air_with_water
from caes.thermodynamics import compress, expand, state_pt


@pytest.fixture
def air_state():
    return state_pt(101_325.0, 288.15, "Air")


def test_turbomachinery_closes_first_law(air_state):
    compressor = compress(air_state, 600_000.0, 0.86, "Air")
    turbine = expand(compressor.outlet, 101_325.0, 0.88, "Air")
    assert compressor.work_j_per_kg > 0
    assert turbine.work_j_per_kg < 0
    assert abs(compressor.first_law_residual_j_per_kg) < 1e-5
    assert abs(turbine.first_law_residual_j_per_kg) < 1e-5


def test_pinch_model_solves_water_ratio_and_terminal_temperatures():
    hot_air = state_pt(600_000.0, 450.0, "Air")
    process = cool_air_with_water(
        hot_air, 293.15, 0.02, "Air", HeatExchangerModel.PINCH, 5.0, 0.8, 3.0, None
    )
    hx = process.heat_exchanger
    assert hx is not None
    assert hx.water_air_mass_ratio > 0
    assert hx.water_outlet_temperature_k == pytest.approx(445.0)
    assert process.outlet.temperature_k == pytest.approx(298.15, abs=1e-5)
    assert abs(process.first_law_residual_j_per_kg) < 1e-5


def test_ntu_model_is_bounded_by_maximum_possible_duty():
    hot_air = state_pt(600_000.0, 450.0, "Air")
    process = cool_air_with_water(
        hot_air, 293.15, 0.02, "Air", HeatExchangerModel.COUNTERFLOW_NTU, 5.0, 0.8, 2.0, 1.0
    )
    hx = process.heat_exchanger
    assert hx is not None
    assert 0 < hx.effectiveness < 1
    assert 293.15 < hx.water_outlet_temperature_k < 450.0
    assert process.outlet.temperature_k < 450.0
    assert abs(process.first_law_residual_j_per_kg) < 1e-5
