import pytest

from caes import CAESPlant, PlantConfig, PlantMode


def _config(mode: PlantMode) -> PlantConfig:
    return PlantConfig(
        mode=mode,
        compressor_stages=3,
        expander_stages=3,
        storage_pressure_bar=60.0,
        air_mass_kg=2_000.0,
        water_tank_volume_m3=10.0,
        thermal_store_loss_fraction=0.03,
    )


def test_adiabatic_cycle_has_finite_energy_balanced_thermal_store():
    config = _config(PlantMode.ADIABATIC)
    result = CAESPlant(config).run()
    store = result.thermal_store
    assert store is not None
    assert result.round_trip_efficiency is not None
    assert 0.0 < result.round_trip_efficiency < 1.0
    assert store.recovered_energy_j > 0
    assert store.delivered_energy_j >= 0
    assert store.energy_above_initial_j == pytest.approx(
        store.recovered_energy_j - store.delivered_energy_j - store.lost_energy_j, abs=1e-4
    )
    assert result.charging.outlet.pressure_bar == pytest.approx(config.storage_pressure_bar)
    assert result.discharging.outlet.pressure_bar == pytest.approx(config.ambient_pressure_bar)
    assert result.charging.outlet.temperature_c == pytest.approx(config.ambient_temperature_c)


def test_diabatic_external_reheat_is_reported_not_called_round_trip_efficiency():
    result = CAESPlant(_config(PlantMode.DIABATIC)).run()
    assert result.round_trip_efficiency is None
    assert result.external_heat_input_j > 0
    assert result.shaft_work_ratio > 0


def test_all_component_processes_close_the_steady_flow_first_law():
    result = CAESPlant(_config(PlantMode.ADIABATIC)).run()
    assert result.charging.max_first_law_residual_j_per_kg < 1e-5
    assert result.discharging.max_first_law_residual_j_per_kg < 1e-5


def test_invalid_storage_pressure_is_rejected():
    with pytest.raises(ValueError, match="storage_pressure"):
        PlantConfig(storage_pressure_bar=1.0)
