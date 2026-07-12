import pytest

from caes import (
    CAESPlant,
    HeatExchangerModel,
    PlantConfig,
    PlantMode,
    ThermalSurplusUse,
    WaterFlowMode,
)
from caes.logic import active_fields


def test_normalized_two_tank_cycle_closes_energy_and_pressure():
    config = PlantConfig(compressor_stages=3, expander_stages=3, storage_pressure_bar=60.0)
    result = CAESPlant(config).run()
    store = result.thermal_store
    assert store is not None
    assert store.recovered_heat_j_per_kg_air == pytest.approx(
        store.delivered_heat_j_per_kg_air + store.storage_loss_j_per_kg_air + store.surplus_heat_j_per_kg_air,
        abs=1e-5,
    )
    assert result.charging.outlet.pressure_bar == pytest.approx(config.storage_pressure_bar)
    assert result.discharging.outlet.pressure_bar == pytest.approx(config.ambient_pressure_bar)
    assert 0 < result.round_trip_efficiency < 1


def test_diabatic_and_adiabatic_share_machinery_but_not_thermal_store():
    common = dict(compressor_stages=3, expander_stages=3, storage_pressure_bar=60.0)
    adiabatic = CAESPlant(PlantConfig(mode=PlantMode.ADIABATIC, **common)).run()
    diabatic = CAESPlant(PlantConfig(mode=PlantMode.DIABATIC, **common)).run()
    assert adiabatic.thermal_store is not None
    assert diabatic.thermal_store is None
    assert adiabatic.round_trip_efficiency > diabatic.round_trip_efficiency


def test_useful_surplus_increases_total_useful_exergy_efficiency():
    reject = CAESPlant(PlantConfig(thermal_surplus_use=ThermalSurplusUse.REJECT)).run()
    useful = CAESPlant(PlantConfig(thermal_surplus_use=ThermalSurplusUse.USEFUL_HEAT)).run()
    assert useful.round_trip_efficiency == pytest.approx(reject.round_trip_efficiency)
    assert useful.exergy.total_useful_exergy_efficiency > useful.exergy.electrical_efficiency
    assert useful.exergy.useful_heat_exergy_j_per_kg_air > 0


@pytest.mark.parametrize(
    "flow_mode",
    [
        WaterFlowMode.MAX_ELECTRIC_EFFICIENCY,
        WaterFlowMode.MAX_HOT_WATER_EXERGY,
        WaterFlowMode.MAX_TOTAL_EXERGY_EFFICIENCY,
    ],
)
def test_normalized_water_ratio_optimizers_select_within_bounds(flow_mode):
    config = PlantConfig(
        heat_exchanger_model=HeatExchangerModel.COUNTERFLOW_NTU,
        water_flow_mode=flow_mode,
        water_air_ratio_search_min=0.1,
        water_air_ratio_search_max=3.0,
        compressor_stages=2,
        expander_stages=2,
        storage_pressure_bar=30.0,
    )
    result = CAESPlant(config).run()
    assert result.optimization is not None
    assert 0.1 <= result.optimization.selected_water_air_mass_ratio <= 3.0


def test_configuration_logic_enforces_mutual_exclusivity():
    pinch = PlantConfig(heat_exchanger_model=HeatExchangerModel.PINCH)
    ntu_optimized = PlantConfig(
        heat_exchanger_model=HeatExchangerModel.COUNTERFLOW_NTU,
        water_flow_mode=WaterFlowMode.MAX_ELECTRIC_EFFICIENCY,
    )
    assert "heat_exchanger_pinch_c" in active_fields(pinch)
    assert "heat_exchanger_ntu" not in active_fields(pinch)
    assert "water_air_mass_ratio" not in active_fields(pinch)
    assert "heat_exchanger_ntu" in active_fields(ntu_optimized)
    assert "water_air_mass_ratio" not in active_fields(ntu_optimized)
    assert "water_air_ratio_search_min" in active_fields(ntu_optimized)


def test_every_component_closes_steady_flow_first_law_and_has_nonnegative_destruction():
    result = CAESPlant(PlantConfig()).run()
    for process in result.charging.processes + result.discharging.processes:
        assert abs(process.first_law_residual_j_per_kg) < 1e-5
        assert process.exergy_destruction_j_per_kg >= 0


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError, match="storage_pressure"):
        PlantConfig(storage_pressure_bar=1.0)
