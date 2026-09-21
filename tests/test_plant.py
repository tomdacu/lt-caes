from math import exp

import pytest

from caes import (
    CAESPlant,
    PlantConfig,
    HeatOfftake,
    OptimizationObjective,
)
from caes.heat_exchangers import WATER_CP_J_PER_KGK
from caes.logic import active_fields
from conftest import LTAHP


def test_normalized_two_tank_cycle_closes_energy_and_pressure():
    config = PlantConfig(compressor_stages=3, expander_stages=3, storage_pressure_bar=60.0)
    result = CAESPlant(config).run()
    store = result.thermal_store
    assert store is not None
    # Equation (12): every joule the intercoolers recovered leaves by one of five doors.
    assert store.recovered_heat_j_per_kg_air == pytest.approx(
        store.delivered_heat_j_per_kg_air
        + store.offtake_heat_j_per_kg_air
        + store.cold_return_heat_rejected_to_ambient_j_per_kg_air
        - store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
        + store.storage_loss_j_per_kg_air
        + store.cold_storage_loss_j_per_kg_air,
        abs=1.0,
    )
    assert result.charging.outlet.pressure_bar == pytest.approx(config.storage_pressure_bar)
    assert result.discharging.outlet.pressure_bar == pytest.approx(config.ambient_pressure_bar)
    assert 0 < result.round_trip_efficiency < 1


def test_tes_header_temperatures_are_mass_weighted_branch_mixtures():
    result = CAESPlant(PlantConfig()).run()
    store = result.thermal_store
    assert store is not None
    charge_hxs = [
        process.heat_exchanger
        for process in result.charging.processes
        if process.heat_exchanger is not None
    ]
    discharge_hxs = [
        process.heat_exchanger
        for process in result.discharging.processes
        if process.heat_exchanger is not None
    ]

    def mixed_temperature(hxs):
        return sum(
            hx.water_air_mass_ratio * hx.water_outlet_temperature_k
            for hx in hxs
        ) / sum(hx.water_air_mass_ratio for hx in hxs)

    assert store.hot_temperature_before_loss_k == pytest.approx(
        mixed_temperature(charge_hxs), abs=1e-8
    )
    assert store.returned_temperature_k == pytest.approx(
        mixed_temperature(discharge_hxs), abs=1e-8
    )


def test_heat_offtake_hardware_is_bypassed_under_the_electrical_objective():
    """With electricity as the objective, the two forms are ONE plant.

    Same stage counts, same storage pressure, same objective: the heat-user form
    must give the same round-trip efficiency as the no-user form, because
    electricity-first operation bypasses E-302 and E-304 rather than selling a
    small, unwanted heat stream. The only surviving difference is the product the
    result carries: LTAHP reports a heat of-take with nothing sold through it,
    LTA reports none.

    The train is the suite's cheap single-stage recipe: one stage only closes at
    a gentle pressure ratio, and the higher material cap is what lets the
    intercooler reach it.
    """
    common = dict(
        compressor_stages=1,
        expander_stages=1,
        storage_pressure_bar=30.0,
        coolant_maximum_temperature_c=450.0,
        optimization_objective=OptimizationObjective.MAX_ELECTRIC_EFFICIENCY,
    )
    lta = CAESPlant(PlantConfig(heat_offtake=HeatOfftake.NONE, **common)).run()
    lta_hp = CAESPlant(PlantConfig(heat_offtake=HeatOfftake.HEAT_USER, **common)).run()

    assert lta.heat_offtake is None
    assert lta_hp.heat_offtake is not None
    assert lta_hp.heat_offtake.heat_j_per_kg_air == pytest.approx(0.0, abs=1e-9)
    assert lta_hp.round_trip_efficiency == pytest.approx(
        lta.round_trip_efficiency, rel=1e-9
    )


def test_cold_tank_standing_loss_follows_the_same_decay_law_as_the_hot_tank():
    config = PlantConfig(
        thermal_storage_tank_ua_w_per_k=0.006,
        storage_duration_hours=4.0,
    )
    result = CAESPlant(config).run()
    store = result.thermal_store
    assert store is not None

    # The cold tank is warmer than ambient here, so standing leaks heat out:
    # the post-standing cold state sits between ambient and the mixed return.
    assert (
        store.cold_return_exchanger_outlet_temperature_k
        > store.cold_temperature_k
    )
    assert store.cold_storage_loss_j_per_kg_air > 0.0
    capacitance = store.total_water_mass_ratio * WATER_CP_J_PER_KGK
    decay = exp(
        -config.thermal_storage_tank_ua_w_per_k * config.storage_duration_hours * 3600.0
        / capacitance
    )
    expected_cold = config.ambient_temperature_k + (
        store.cold_return_exchanger_outlet_temperature_k
        - config.ambient_temperature_k
    ) * decay
    assert store.cold_temperature_k == pytest.approx(expected_cold, abs=5e-4)
    assert store.cold_storage_loss_j_per_kg_air == pytest.approx(
        capacitance
        * (
            store.cold_return_exchanger_outlet_temperature_k
            - store.cold_temperature_k
        ),
        rel=1e-6,
    )


def test_heat_only_e303_does_not_rescue_a_default_plant_without_heat_sink():
    with pytest.raises(ValueError, match="no closed two-tank design"):
        CAESPlant(PlantConfig(heat_offtake=HeatOfftake.NONE)).run()
    selling = CAESPlant(LTAHP).run()

    # The LTAHP topology supplies the real high-grade sink instead of silently
    # turning E-303 back into a rejection cooler.
    assert selling.thermal_store.offtake_heat_j_per_kg_air > 0.0
    assert selling.exergy.total_useful_exergy_efficiency > selling.round_trip_efficiency
    assert selling.exergy.useful_heat_exergy_j_per_kg_air > 0


@pytest.mark.parametrize(
    "flow_mode",
    [OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY],
)
def test_normalized_water_ratio_optimizers_report_the_selected_design(flow_mode):
    config = PlantConfig(
        optimization_objective=flow_mode,
    )
    result = CAESPlant(config).run()
    assert result.optimization is not None
    assert result.thermal_store is not None
    assert result.thermal_store.total_water_mass_ratio > 0
    assert result.optimization.objective == flow_mode.value


def test_configuration_logic_exposes_only_ntu_sizing_for_adiabatic_hxs():
    config = PlantConfig(optimization_objective=OptimizationObjective.MAX_ELECTRIC_EFFICIENCY)
    active = active_fields(config)
    assert "heat_exchanger_ntu" in active
    assert "coolant_maximum_temperature_c" in active
    assert "optimization_objective" in active
    assert "minimum_expander_outlet_temperature_c" not in active


def test_direct_coolant_maximum_temperature_is_enforced():
    result = CAESPlant(PlantConfig(coolant_maximum_temperature_c=188.29)).run()
    store = result.thermal_store
    assert store is not None
    assert (
        store.coolant_maximum_temperature_reached_k
        <= store.coolant_maximum_temperature_k + 1e-6
    )

    limited = CAESPlant(PlantConfig(coolant_maximum_temperature_c=100.0))
    with pytest.raises(ValueError, match="coolant maximum"):
        limited._charge_with_ratios(
            limited.config.ambient_temperature_k,
            [0.05] * limited.config.compressor_stages,
        )


def test_coolant_minimum_limit_and_low_freezing_screening_input():
    water = CAESPlant(PlantConfig(coolant_minimum_temperature_c=0.0))
    with pytest.raises(ValueError, match="freezing point"):
        water._charge_with_ratios(
            272.15, [0.25] * water.config.compressor_stages
        )

    blend = CAESPlant(PlantConfig(coolant_minimum_temperature_c=-5.0))
    _, store = blend._charge_with_ratios(
        272.15, [0.25] * blend.config.compressor_stages
    )
    assert store.cold_k == pytest.approx(272.15)


def test_adiabatic_air_train_has_no_direct_ambient_reheater():
    """LTAHP takes every joule of direct air reheat from the coolant loop.

    The direct ambient preheaters are gone from the family. They were up to
    eight extra high-pressure gas/ambient exchangers ahead of the water
    interheaters, and they were the only exchangers in the model that moved heat
    into the air without paying an air-side pressure drop - which quietly
    flattered whichever concept carried them. Both surviving forms reheat from
    the coolant loop alone.
    """
    result = CAESPlant(LTAHP).run()

    assert result.external_heat_input_j_per_kg == pytest.approx(
        result.thermal_store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
    )
    assert not any(
        process.kind in {"ambient_reheat", "ambient_anti_icing_reheat"}
        for process in result.discharging.processes
    )
    assert {process.kind for process in result.discharging.processes} == {
        "interheating",
        "expansion",
    }
    assert 0.0 < result.exergy.total_useful_exergy_efficiency < 1.0


def test_250_bar_air_low_coolant_max_is_rejected_by_the_combined_limits():
    """The old apparent root cannot satisfy the current physical envelope.

    A deliberately selected 123.5 degC direct coolant maximum binds. With only
    six expander stages, the first finite-NTU interheater cannot reach the
    inlet state required to keep a 250-to-1 bar expansion moisture-safe. Heat
    rejection elsewhere in the loop cannot repair that temperature pinch.
    """
    config = PlantConfig(
        ambient_temperature_c=15.0,
        ambient_pressure_bar=1.01325,
        ambient_relative_humidity=0.60,
        storage_pressure_bar=250.0,
        coolant_maximum_temperature_c=123.5,
        heat_exchanger_ntu=3.0,
        cold_return_cooler_ntu=3.0,
        heat_offtake=HeatOfftake.NONE,
    )
    with pytest.raises(ValueError) as rejection:
        CAESPlant(config)._close_cold_loop(1.7)
    # The refusal must name the physics, not just report an empty search.
    assert "no closed coolant-loop root" in str(rejection.value)
    assert "moisture-safe interheater duties" in str(rejection.value)


def test_infeasible_design_error_names_the_binding_physical_constraint():
    """A rejected plant must say WHICH limit rejected it, not just that the
    search found nothing."""
    config = PlantConfig(
        storage_pressure_bar=250.0,
        coolant_maximum_temperature_c=123.5,
        heat_offtake=HeatOfftake.NONE,
    )
    with pytest.raises(ValueError, match="coolant maximum"):
        CAESPlant(config).run()


def test_every_component_closes_steady_flow_first_law_and_has_nonnegative_destruction():
    result = CAESPlant(PlantConfig()).run()
    for process in result.charging.processes + result.discharging.processes:
        assert abs(process.first_law_residual_j_per_kg) < 1e-5
        assert process.exergy_destruction_j_per_kg >= 0


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError, match="storage_pressure"):
        PlantConfig(storage_pressure_bar=1.0)


def test_hot_tank_loss_uses_analytic_ua_duration_model():
    config = PlantConfig(
        thermal_storage_tank_ua_w_per_k=0.006,
        storage_duration_hours=4.0,
    )
    store = CAESPlant(config).run().thermal_store
    assert store is not None

    capacitance = store.total_water_mass_ratio * WATER_CP_J_PER_KGK
    expected_available = config.ambient_temperature_k + (
        store.hot_temperature_before_loss_k - config.ambient_temperature_k
    ) * exp(
        -config.thermal_storage_tank_ua_w_per_k
        * config.storage_duration_hours
        * 3600.0
        / capacitance
    )
    expected_loss = capacitance * (
        store.hot_temperature_before_loss_k - expected_available
    )

    assert store.hot_temperature_available_k == pytest.approx(
        expected_available, abs=1e-9
    )
    assert store.storage_loss_j_per_kg_air == pytest.approx(
        expected_loss, abs=1e-6
    )


@pytest.mark.parametrize(
    "config",
    (
        PlantConfig(
            thermal_storage_tank_ua_w_per_k=0.0,
            storage_duration_hours=24.0,
        ),
        PlantConfig(
            thermal_storage_tank_ua_w_per_k=0.1,
            storage_duration_hours=0.0,
        ),
    ),
)
def test_zero_ua_or_zero_duration_gives_no_hot_tank_loss(config):
    store = CAESPlant(config).run().thermal_store
    assert store is not None
    assert store.hot_temperature_available_k == pytest.approx(
        store.hot_temperature_before_loss_k
    )
    assert store.storage_loss_j_per_kg_air == pytest.approx(0.0, abs=1e-9)


def test_a_stage_with_no_moisture_safe_duty_gets_an_empty_branch():
    """A dry interheater branch is legal, and refusing it was expensive.

    When a stage's expansion already clears the anti-icing envelope unheated,
    its moisture-safe duty is zero and it needs no water. The surplus-absorbing
    dispatch builds its candidates by giving the surplus to ONE stage and
    leaving the rest at their minimum, so a single zero-duty stage used to make
    EVERY candidate invalid: the guard rejected any zero ratio while the
    generator kept producing them. The plant then fell through to the bypass
    path and previously dumped the whole surplus at the retired E-303 cooler.
    """
    from caes.plant import _ThermalStore

    config = PlantConfig(
        storage_pressure_bar=10.0,
        compressor_stages=20,
        expander_stages=20,
        coolant_maximum_temperature_c=250.0,
    )
    plant = CAESPlant(config)
    humidity = 1.0e-4
    requirements = plant._discharge_requirements(humidity)
    dry_stages = [
        index
        for index, requirement in enumerate(requirements)
        if requirement.duty_j_per_kg_air <= 0.0
    ]
    assert dry_stages, "this configuration is meant to have stages needing no reheat"

    store = _ThermalStore(
        total_ratio=1.0,
        cold_k=290.0,
        hot_before_loss_k=380.0,
        hot_available_k=380.0,
        storage_loss_j_per_kg_air=0.0,
        charge_returns=((1.0, 380.0, 0.0),),
        protected_humidity_ratio=humidity,
        maximum_water_temperature_reached_k=380.0,
    )
    ratios = [0.0 if i in dry_stages else 1.0 / (20 - len(dry_stages))
              for i in range(20)]

    design = plant._discharge_with_ratios(store, ratios)

    # The dry stages exist in the train as their pressure drop, carry no water,
    # and never appear in the water returns.
    heaters = [p for p in design.cycle.processes if p.kind == "interheating"]
    assert len(heaters) == 20
    assert sum(1 for p in heaters if p.heat_exchanger is None) == len(dry_stages)
    assert sum(r for r, _, _ in design.returns) == pytest.approx(1.0)
    # And the conserved inventory really did reach the turbines.
    assert sum(duty for _, _, duty in design.returns) > 0.0


def test_e303_is_heat_only_and_never_cools_a_return():
    plant = CAESPlant(PlantConfig(ambient_temperature_c=15.0, cold_return_cooler_ntu=3.0))
    ambient_k = 288.15

    hot_return = plant._cold_return_exchanger_outlet_temperature(333.15)
    cold_return = plant._cold_return_exchanger_outlet_temperature(256.15)

    assert hot_return == 333.15, "a hot return must bypass the heat-only exchanger"
    assert 256.15 < cold_return < 288.15, "a cold return must be warmed toward ambient"
    assert plant._cold_return_exchanger_outlet_temperature(ambient_k) == pytest.approx(
        ambient_k
    )


def test_e303_optimizer_selects_the_last_four_returns_in_the_reference_example():
    plant = CAESPlant(PlantConfig())
    temperatures_c = (31.1, 31.6, 26.3, 20.0, 11.6, 3.8, -3.6, -10.5)
    branches = tuple(
        (1.0, temperature_c + 273.15, 0.0)
        for temperature_c in temperatures_c
    )

    recovery = plant._optimize_cold_return_recovery(branches)

    assert recovery.start_stage == 4
    assert recovery.branch_count == 4
    # For equal flows and constant cp, the suffix score is proportional to the
    # cumulative ambient deficit. The last four give 58.7 K, greater than both
    # the last three (55.3 K) and the last five (53.7 K).
    assert recovery.inlet_k - 273.15 == pytest.approx(0.325)
    assert recovery.heat_absorbed_j_per_kg_air > 0.0


def test_e303_selects_one_cold_suffix_and_only_absorbs_ambient_heat():
    result = CAESPlant(PlantConfig()).run()
    store = result.thermal_store
    assert store is not None

    assert store.cold_return_heat_rejected_to_ambient_j_per_kg_air == 0.0
    assert store.cold_return_heat_absorbed_from_ambient_j_per_kg_air > 0.0
    assert store.cold_return_recovery_start_stage is not None
    assert store.cold_return_recovery_branch_count > 0
    assert store.cold_return_recovery_inlet_temperature_k < 288.15
    assert (
        store.cold_return_recovery_inlet_temperature_k
        < store.cold_return_recovery_outlet_temperature_k
        < 288.15
    )

    # Equation (12), written with both sides explicit.
    assert (
        store.recovered_heat_j_per_kg_air
        + store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
    ) == pytest.approx(
        store.delivered_heat_j_per_kg_air
        + store.offtake_heat_j_per_kg_air
        + store.cold_return_heat_rejected_to_ambient_j_per_kg_air
        + store.storage_loss_j_per_kg_air
        + store.cold_storage_loss_j_per_kg_air,
        abs=1.0,
    )

    # Either direction destroys exergy: water exergy is convex about the dead
    # state, so both drag the stream toward its minimum.
    assert store.cold_return_exergy_destruction_j_per_kg_air >= 0.0
    assert result.exergy.component_destruction_j_per_kg_air[
        "cold_return_ambient_exchange"
    ] == pytest.approx(store.cold_return_exergy_destruction_j_per_kg_air)
