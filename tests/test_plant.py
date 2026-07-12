import pytest

from caes import CAESPlant, HeatExchangerModel, PlantConfig, PlantMode, WaterFlowStrategy


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


def test_finite_area_countercurrent_exchangers_report_ntu_area_and_screening_cost():
    config = PlantConfig(
        mode=PlantMode.ADIABATIC,
        heat_exchanger_model=HeatExchangerModel.COUNTERFLOW_NTU,
        compressor_stages=3,
        expander_stages=3,
        storage_pressure_bar=60.0,
        air_mass_kg=2_000.0,
        water_tank_volume_m3=10.0,
        air_mass_flow_kg_s=2.0,
        water_mass_flow_kg_s=10.0,
        heat_exchanger_area_m2=20.0,
        overall_heat_transfer_coefficient_w_m2k=100.0,
        heat_exchanger_reference_cost_eur=10_000.0,
        heat_exchanger_reference_area_m2=20.0,
        heat_exchanger_installation_factor=2.0,
    )
    result = CAESPlant(config).run()
    hx = result.heat_exchanger_summary
    assert hx.exchanger_count == 5  # two intermediate intercoolers + three reheaters
    assert hx.total_area_m2 == pytest.approx(100.0)
    assert hx.ua_per_exchanger_w_per_k == pytest.approx(2_000.0)
    assert hx.screening_installed_cost_eur == pytest.approx(100_000.0)
    finite_hx = [p.heat_exchanger for p in result.charging.processes + result.discharging.processes if p.heat_exchanger]
    assert finite_hx
    assert all(0.0 <= item.effectiveness <= 1.0 for item in finite_hx)
    assert all(item.duty_w <= item.maximum_duty_w for item in finite_hx)


def test_water_flow_optimizer_finds_smallest_flow_for_thermal_recovery_target():
    config = PlantConfig(
        mode=PlantMode.ADIABATIC,
        heat_exchanger_model=HeatExchangerModel.COUNTERFLOW_NTU,
        water_flow_strategy=WaterFlowStrategy.OPTIMIZE_THERMAL,
        compressor_stages=3,
        expander_stages=3,
        storage_pressure_bar=60.0,
        air_mass_kg=2_000.0,
        water_tank_volume_m3=10.0,
        air_mass_flow_kg_s=2.0,
        heat_exchanger_area_m2=20.0,
        overall_heat_transfer_coefficient_w_m2k=100.0,
        water_flow_target_fraction=0.90,
        water_mass_flow_search_min_kg_s=0.1,
        water_mass_flow_search_max_kg_s=100.0,
    )
    result = CAESPlant(config).run()
    optimum = result.water_flow_optimization
    assert optimum is not None
    assert 0.1 <= optimum.optimized_water_mass_flow_kg_s < 100.0
    assert optimum.achieved_fraction == pytest.approx(0.90, abs=2e-3)
    assert result.charging_power_kw > 0
    assert result.discharging_power_kw > 0
