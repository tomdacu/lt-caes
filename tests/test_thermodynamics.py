import pytest

from caes.thermodynamics import compress, cool_to, expand, state_pt


@pytest.fixture
def air_state():
    return state_pt(101_325.0, 288.15, "Air")


def test_compressor_and_expander_close_the_component_energy_balance(air_state):
    compressor = compress(air_state, 600_000.0, 0.86, "Air")
    turbine = expand(compressor.outlet, 101_325.0, 0.88, "Air")
    assert compressor.work_j_per_kg > 0
    assert turbine.work_j_per_kg < 0
    assert abs(compressor.first_law_residual_j_per_kg) < 1e-5
    assert abs(turbine.first_law_residual_j_per_kg) < 1e-5


def test_intercooler_never_adds_heat_even_if_target_is_hotter(air_state):
    cooler = cool_to(air_state, air_state.temperature_k + 100.0, 0.02, "Air")
    assert cooler.heat_to_air_j_per_kg == 0.0
    assert cooler.outlet.enthalpy_j_per_kg == pytest.approx(air_state.enthalpy_j_per_kg)
    assert abs(cooler.first_law_residual_j_per_kg) < 1e-5
