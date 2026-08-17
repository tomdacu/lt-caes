"""Coupled interheater sizing and the upstream heat destination."""

import pytest
from CoolProp.CoolProp import PropsSI

from caes import CAESPlant, HeatOfftake, OptimizationObjective, PlantConfig
from caes.heat_exchangers import WATER_CP_J_PER_KGK
from caes.thermal_limits import minimum_wet_expander_temperature_k


def _expander_outlets_c(result):
    return [p.outlet.temperature_c for p in result.discharging.processes if p.kind == "expansion"]


def _hx_ratios(cycle, kind):
    return [p.heat_exchanger.water_air_mass_ratio for p in cycle.processes if p.kind == kind and p.heat_exchanger]


def _temperature_difference_profile(process, points=40):
    """Solved counter-current DeltaT(Q), including variable air cp and pressure drop."""
    hx = process.heat_exchanger
    values = []
    for i in range(points + 1):
        fraction = i / points
        enthalpy = process.inlet.enthalpy_j_per_kg + fraction * (
            process.outlet.enthalpy_j_per_kg - process.inlet.enthalpy_j_per_kg
        )
        pressure = process.inlet.pressure_pa + fraction * (
            process.outlet.pressure_pa - process.inlet.pressure_pa
        )
        air_k = PropsSI("T", "P", pressure, "H", enthalpy, "Air")
        water_k = hx.water_outlet_temperature_k + fraction * (
            hx.water_inlet_temperature_k - hx.water_outlet_temperature_k
        )
        values.append(air_k - water_k if process.kind == "intercooling" else water_k - air_k)
    return values


def test_every_expander_outlet_respects_its_pressure_dependent_moisture_minimum():
    config = PlantConfig(
        compressor_stages=1,
        expander_stages=1,
        storage_pressure_bar=30.0,
        coolant_maximum_temperature_c=450.0,
    )
    result = CAESPlant(config).run()
    humidity = (
        result.moisture.stored_air_water_vapor_kg_per_kg_dry_air
    )
    for process in result.discharging.processes:
        if process.kind != "expansion":
            continue
        target_k = minimum_wet_expander_temperature_k(
            process.outlet.pressure_pa, humidity
        )
        assert process.outlet.temperature_k >= target_k - 0.02


def test_charge_and_discharge_use_different_stage_specific_splits():
    result = CAESPlant(PlantConfig()).run()
    charge = _hx_ratios(result.charging, "intercooling")
    discharge = _hx_ratios(result.discharging, "interheating")
    assert len({round(value, 4) for value in charge}) > 1
    assert len({round(value, 4) for value in discharge}) > 1
    assert charge != pytest.approx(discharge)
    assert sum(charge) == pytest.approx(sum(discharge), rel=2e-4)
    assert sum(charge) == pytest.approx(result.thermal_store.total_water_mass_ratio, rel=1e-9)


@pytest.mark.parametrize(("compressors", "expanders"), [(1, 1), (6, 3)])
def test_complete_inventory_crosses_interheaters(compressors, expanders):
    result = CAESPlant(PlantConfig(
        compressor_stages=compressors,
        expander_stages=expanders,
        coolant_maximum_temperature_c=(
            450.0 if compressors == expanders == 1 else 188.29
        ),
        storage_pressure_bar=(
            30.0 if compressors == expanders == 1 else 100.0
        ),
    )).run()
    discharge = _hx_ratios(result.discharging, "interheating")
    assert len(discharge) == expanders
    assert sum(discharge) == pytest.approx(
        result.thermal_store.total_water_mass_ratio, rel=2e-5, abs=2e-6
    )
def test_optimizer_reports_profile_spread_without_using_it_as_a_veto():
    result = CAESPlant(PlantConfig()).run()
    exchangers = [
        process
        for cycle in (result.charging, result.discharging)
        for process in cycle.processes
        if process.heat_exchanger
    ]
    profiles = [_temperature_difference_profile(process) for process in exchangers]
    measured_spread = max(max(values) - min(values) for values in profiles)
    assert min(min(values) for values in profiles) > 0.0
    assert result.optimization.max_hx_temperature_spread_k == pytest.approx(
        measured_spread, abs=0.05
    )
    # An objective optimum need not be capacity matched. The solution reports
    # this mismatch instead of silently vetoing the selected dispatch.
    assert measured_spread > 2.5
    assert result.thermal_store.total_water_mass_ratio > 0.0


def test_cold_tank_follows_the_optimized_heat_only_return_recovery():
    config = PlantConfig()
    result = CAESPlant(config).run()
    store = result.thermal_store
    assert store.cold_return_recovery_inlet_temperature_k < config.ambient_temperature_k
    assert store.cold_return_recovery_outlet_temperature_k < config.ambient_temperature_k
    assert store.cold_return_heat_rejected_to_ambient_j_per_kg_air == 0.0
    assert store.cold_return_heat_absorbed_from_ambient_j_per_kg_air > 0.0
    assert store.cold_temperature_k == pytest.approx(
        store.cold_return_exchanger_outlet_temperature_k, abs=5e-4
    )


def test_default_heat_only_return_architecture_needs_the_heat_user_sink():
    with pytest.raises(ValueError, match="no closed two-tank design"):
        CAESPlant(PlantConfig(heat_offtake=HeatOfftake.NONE)).run()
    sold = CAESPlant(PlantConfig(
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
    )).run()

    # With E-303 forbidden to reject heat, the default periodic loop needs the
    # installed high-grade user sink; it must not invent a hidden cooler.
    assert sold.thermal_store.offtake_heat_j_per_kg_air > 0.0
    assert sold.exergy.useful_heat_exergy_j_per_kg_air > 0.0


def test_electric_only_dispatch_does_not_hide_a_return_cooler():
    with pytest.raises(ValueError, match="no closed two-tank design"):
        CAESPlant(PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            optimization_objective=OptimizationObjective.MAX_ELECTRIC_EFFICIENCY,
        )).run()
    lthp_combined = CAESPlant(PlantConfig(
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
    )).run()

    assert lthp_combined.thermal_store.offtake_heat_j_per_kg_air > 0.0


def test_series_exchanger_duty_follows_the_plant_side_temperature_drop():
    result = CAESPlant(PlantConfig(
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
    )).run()
    dh = result.heat_offtake
    expected = result.thermal_store.total_water_mass_ratio * WATER_CP_J_PER_KGK * (
        dh.hot_tank_temperature_k - dh.turbine_supply_temperature_k
    )
    # A feasible network absorbs the complete upstream surplus.
    assert dh.heat_j_per_kg_air == pytest.approx(expected, rel=1e-6)


def test_network_flow_is_derived_from_its_temperature_span():
    dh = CAESPlant(PlantConfig(
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        heat_user_supply_temperature_c=80.0,
        heat_user_return_temperature_c=45.0,
    )).run().heat_offtake
    span = dh.supply_temperature_k - dh.return_temperature_k
    assert dh.network_water_per_kg_air == pytest.approx(
        dh.heat_j_per_kg_air / (WATER_CP_J_PER_KGK * span), rel=1e-9
    )


def test_unreachable_hot_end_supply_raises_instead_of_silently_capping_it():
    with pytest.raises(ValueError, match="mixed hot store cannot deliver the requested"):
        CAESPlant(PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
            heat_user_supply_temperature_c=400.0,
            heat_user_return_temperature_c=45.0,
        ))._close_cold_loop(1.0)


def test_a_user_return_below_the_first_extraction_is_reported_as_finite_area():
    """Where the plant now stops, and why the message is worth reading.

    E-304 removed the old squeeze: the trunk no longer has to stay above the
    user return all the way to the last bleed, so a hot return on its own is no
    longer fatal. What remains is an ordinary finite-area statement about the
    ONE user exchanger. Asking for 140/130 needs E-302 to take the trunk from
    160.6 C down to the first extraction at 93.7 C against a 130 C return - that
    is, below its own cold-side inlet - so the required effectiveness comes out
    above one, which is the exchanger saying the duty is not merely expensive
    but impossible.
    """
    with pytest.raises(ValueError, match="heat-user exchanger class is too small"):
        CAESPlant(PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
            heat_user_supply_temperature_c=140.0,
            heat_user_return_temperature_c=130.0,
            heat_user_exchanger_ntu=5.0,
        ))._close_cold_loop(1.0)


def test_a_hot_user_return_that_the_serial_cascade_rejected_now_closes():
    """The regression that justifies the architecture change.

    A 95/75 user return sits above four of the six interheater demands. The
    serial cascade could only serve it by shrinking the inventory until the
    store reached 139 C, which cost intercooling and dropped the delivery ratio
    below the 80/45 case. Here the trunk crosses E-302 once and keeps descending
    inside E-304, well below the user return, so the store stays cool enough to
    intercool properly.
    """
    result = CAESPlant(PlantConfig(
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        heat_user_supply_temperature_c=95.0,
        heat_user_return_temperature_c=75.0,
    )).run()

    extraction = result.extraction_exchanger
    assert extraction is not None
    assert extraction.trunk_outlet_temperature_k < 75.0 + 273.15
    assert result.useful_energy_delivery_ratio > 1.0
    assert abs(result.exergy.balance_residual_j_per_kg_air) < 1.0


def test_high_ntu_eight_stage_search_finds_a_closed_loop_window():
    """E-303 moves the old narrow root; closure and safe expansion still hold."""
    result = CAESPlant(PlantConfig(
        storage_pressure_bar=200.0,
        compressor_stages=8,
        expander_stages=8,
        heat_exchanger_ntu=100.0,
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        # This deliberately extreme NTU root returns one branch near -27.6 degC.
        # Keep it as an antifreeze-screening regression; pure water and a -5 degC
        # blend must correctly reject the same design.
        coolant_minimum_temperature_c=-30.0,
    )).run()

    store = result.thermal_store
    assert store.total_water_mass_ratio > 0.0
    assert abs(
        store.cold_return_exchanger_outlet_temperature_k
        - store.cold_temperature_k
    ) < 5e-4
    assert result.optimization.max_hx_temperature_spread_k < 100.0
    humidity = result.moisture.stored_air_water_vapor_kg_per_kg_dry_air
    expected = [
        minimum_wet_expander_temperature_k(process.outlet.pressure_pa, humidity)
        - 273.15
        for process in result.discharging.processes
        if process.kind == "expansion"
    ]
    assert _expander_outlets_c(result) == pytest.approx(expected, abs=0.02)


@pytest.mark.parametrize("ntu", [3.0, 6.0])
def test_finite_ntu_hxs_meet_all_stage_targets(ntu):
    result = CAESPlant(PlantConfig(heat_exchanger_ntu=ntu)).run()
    humidity = (
        result.moisture.stored_air_water_vapor_kg_per_kg_dry_air
    )
    for process in result.discharging.processes:
        if process.kind == "expansion":
            assert process.outlet.temperature_k >= (
                minimum_wet_expander_temperature_k(
                    process.outlet.pressure_pa, humidity
                )
                - 0.02
            )
