"""Invariants of the single user exchanger and the E-304 extraction body.

There is one mixed hot store. The whole conserved inventory crosses ONE heat-user
exchanger (E-302), which takes the top of the store, and then enters ONE
counter-current extraction body (E-304), where it is withdrawn once per expansion
stage and is completely consumed at the last extraction.

E-304's cold side is the plant's own coolant return, so the trunk's descent below
the user is recuperated INSIDE the plant. That is the whole point of the device:
it decouples what the user is offered from what the interheaters need, so the
user keeps the hot end of the store and the tail stages stop being fed water tens
of kelvin hotter than they can use.

These tests replaced the serial K-station cascade suite. The cascade's own
invariants are preserved in git at the frozen baseline; what carries over here is
the discipline, not the topology: conserved mass, finite exchanger area, a real
pinch check at every node, and books that close.
"""

from dataclasses import replace

import pytest

from caes import CAESPlant, HeatOfftake, PlantConfig
from caes.heat_exchangers import WATER_CP_J_PER_KGK


USER_NTU = 5.0
EXTRACTION_NTU = 5.0
BASE = PlantConfig(
    storage_pressure_bar=85.8,
    compressor_stages=6,
    expander_stages=6,
    heat_offtake=HeatOfftake.HEAT_USER,
    optimization_objective="max_combined_energy_delivery",
    coolant_maximum_temperature_c=200.0,
    coolant_minimum_temperature_c=-80.0,
    thermal_storage_tank_ua_w_per_k=0.0,
    heat_user_supply_temperature_c=80.0,
    heat_user_return_temperature_c=45.0,
    heat_user_exchanger_ntu=USER_NTU,
    extraction_exchanger_ntu=EXTRACTION_NTU,
)

# A deliberately awkward second point: at 300 bar with eight stages the raw
# per-stage demand profile is NOT monotone, so it exercises the suffix-maximum
# envelope rather than the easy falling case.
NON_MONOTONE = replace(
    BASE, storage_pressure_bar=300.0, compressor_stages=8, expander_stages=8
)


def solved(config=BASE, **overrides):
    return CAESPlant(replace(config, **overrides)).run()


def interheater_branches(result):
    return [
        process.heat_exchanger
        for process in result.discharging.processes
        if process.kind == "interheating" and process.heat_exchanger
    ]


# --------------------------------------------------------------- topology shape

def test_there_is_exactly_one_user_exchanger_and_it_sees_the_whole_trunk():
    result = solved()
    store = result.thermal_store
    taps = result.heat_offtake.taps

    assert len(taps) == 1
    assert taps[0].plant_water_per_kg_air == pytest.approx(
        store.total_water_mass_ratio, abs=2e-6
    )
    assert taps[0].plant_inlet_temperature_k == pytest.approx(
        store.hot_temperature_available_k
    )
    # The store itself stays one mixed inventory: E-304 changes the discharge
    # network, never the storage.
    assert len(store.hot_level_temperatures_k) == 1
    assert store.hot_level_water_mass_ratios[0] == pytest.approx(
        store.total_water_mass_ratio
    )


def test_the_user_exchanger_hands_the_trunk_straight_to_the_first_extraction():
    result = solved()
    tap = result.heat_offtake.taps[0]
    extraction = result.extraction_exchanger

    assert extraction.trunk_inlet_temperature_k == pytest.approx(
        tap.plant_outlet_temperature_k, abs=1e-9
    )
    assert extraction.extraction_temperatures_k[0] == pytest.approx(
        extraction.trunk_inlet_temperature_k
    )


@pytest.mark.parametrize("config", [BASE, NON_MONOTONE], ids=["86bar-6", "300bar-8"])
def test_one_extraction_per_stage_consuming_the_whole_inventory(config):
    result = solved(config)
    store = result.thermal_store
    extraction = result.extraction_exchanger

    assert len(extraction.extraction_temperatures_k) == config.expander_stages
    assert len(extraction.extraction_mass_ratios) == config.expander_stages
    assert sum(extraction.extraction_mass_ratios) == pytest.approx(
        store.total_water_mass_ratio, abs=2e-6
    )
    # Every kilogram passes exactly one interheater core.
    assert sum(
        hx.water_air_mass_ratio for hx in interheater_branches(result)
    ) == pytest.approx(store.total_water_mass_ratio, abs=2e-6)


@pytest.mark.parametrize("config", [BASE, NON_MONOTONE], ids=["86bar-6", "300bar-8"])
def test_trunk_flow_thins_monotonically_along_the_body(config):
    """The defining behaviour: mass leaves at every nozzle and never returns."""
    extraction = solved(config).extraction_exchanger
    flows = [segment.trunk_flow_per_kg_air for segment in extraction.segments]

    assert flows == sorted(flows, reverse=True)
    assert all(flow > 0.0 for flow in flows)
    # The suffix identity: the flow crossing zone g is everything not yet drawn.
    inventory = extraction.total_water_mass_ratio
    drawn = 0.0
    for index, segment in enumerate(extraction.segments):
        drawn += extraction.extraction_mass_ratios[index]
        assert segment.trunk_flow_per_kg_air == pytest.approx(
            inventory - drawn, abs=2e-6
        )


# ------------------------------------------------------------- the duty ladder

@pytest.mark.parametrize("config", [BASE, NON_MONOTONE], ids=["86bar-6", "300bar-8"])
def test_the_ladder_is_non_increasing_and_never_starves_a_stage(config):
    """A withdrawn trunk only gets colder, and must still meet every demand."""
    result = solved(config)
    extractions = list(result.extraction_exchanger.extraction_temperatures_k)
    demands = [
        process.outlet.temperature_k
        for process in result.discharging.processes
        if process.kind == "interheating"
    ]

    assert extractions == sorted(extractions, reverse=True)
    for supply_k, produced_k in zip(extractions, demands):
        assert supply_k > produced_k - 1e-9


def test_a_common_margin_sets_every_extraction():
    """One unknown closes the whole discharge network, not one per stage."""
    result = solved()
    extraction = result.extraction_exchanger
    supplied = [hx.water_inlet_temperature_k for hx in interheater_branches(result)]

    assert supplied == pytest.approx(
        list(extraction.extraction_temperatures_k), abs=1e-7
    )
    margins = [
        supply_k - process.outlet.temperature_k
        for supply_k, process in zip(
            extraction.extraction_temperatures_k,
            [
                process
                for process in result.discharging.processes
                if process.kind == "interheating"
            ],
        )
    ]
    # Measured against the temperature each interheater ACHIEVED, which differs
    # from the demand it was sized for by the inverse-HX tolerance (tens of
    # microkelvin). A millikelvin is therefore the honest bound here; asking for
    # machine precision would be asserting that the inverse solve is exact.
    assert min(margins) > 0.0
    assert extraction.margin_k == pytest.approx(min(margins), abs=1e-3)


def test_a_non_monotone_demand_profile_shares_one_nozzle():
    """Where physics forbids a hotter later stage, two stages share a bleed.

    The 300 bar eight-stage train demands 64.45 C at stage two against 63.34 C
    at stage one. A descending trunk cannot serve that, so the envelope puts
    both on the hotter of the two and the zone between them carries no duty.
    """
    extraction = solved(NON_MONOTONE).extraction_exchanger
    temperatures = list(extraction.extraction_temperatures_k)

    assert temperatures[0] == pytest.approx(temperatures[1], abs=1e-9)
    assert extraction.segments[0].duty_j_per_kg_air == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------ finite area and real approach

@pytest.mark.parametrize("config", [BASE, NON_MONOTONE], ids=["86bar-6", "300bar-8"])
def test_every_zone_stays_inside_its_finite_ntu_class(config):
    extraction = solved(config).extraction_exchanger

    for segment in extraction.segments:
        assert segment.required_effectiveness <= segment.available_effectiveness + 2e-6
        # The cold side carries the whole inventory, so the trunk is C_min.
        assert 0.0 <= segment.capacity_ratio <= 1.0
    assert extraction.exchanger_ntu == EXTRACTION_NTU
    assert extraction.minimum_effectiveness_margin >= -2e-6


@pytest.mark.parametrize("config", [BASE, NON_MONOTONE], ids=["86bar-6", "300bar-8"])
def test_the_profiles_never_cross_at_any_node(config):
    """With a stepped trunk capacity rate the pinch migrates INSIDE the body.

    Checking only the two ends of the exchanger would miss a crossed profile, so
    both terminals of every zone are asserted, not just the outer two.
    """
    extraction = solved(config).extraction_exchanger

    for segment in extraction.segments:
        assert segment.hot_end_terminal_difference_k > 0.0
        assert segment.cold_end_terminal_difference_k > 0.0
    assert extraction.minimum_terminal_difference_k > 0.0


# -------------------------------------------------------------- the books close

@pytest.mark.parametrize("config", [BASE, NON_MONOTONE], ids=["86bar-6", "300bar-8"])
def test_recuperated_duty_is_the_zone_sum_and_the_return_temperature_rise(config):
    extraction = solved(config).extraction_exchanger
    inventory = extraction.total_water_mass_ratio

    assert extraction.recuperated_heat_j_per_kg_air == pytest.approx(
        sum(segment.duty_j_per_kg_air for segment in extraction.segments), abs=1e-6
    )
    assert extraction.recuperated_heat_j_per_kg_air == pytest.approx(
        inventory
        * WATER_CP_J_PER_KGK
        * (
            extraction.return_outlet_temperature_k
            - extraction.return_inlet_temperature_k
        ),
        abs=1e-6,
    )
    assert extraction.recuperated_heat_j_per_kg_air > 0.0


def test_e304_sits_between_the_final_mixing_and_the_cold_tank():
    """The loop closes on the RECUPERATED inlet, not on the mixed return."""
    result = solved()
    store = result.thermal_store
    extraction = result.extraction_exchanger

    assert extraction.return_inlet_temperature_k == pytest.approx(
        store.recuperator_inlet_temperature_k
    )
    assert extraction.return_outlet_temperature_k == pytest.approx(
        store.cold_return_exchanger_outlet_temperature_k
    )
    assert store.extraction_recuperated_heat_j_per_kg_air == pytest.approx(
        extraction.recuperated_heat_j_per_kg_air
    )
    # Recuperation is internal, so it must be strictly warming and must not
    # appear as an ambient import.
    assert (
        store.cold_return_exchanger_outlet_temperature_k
        > store.recuperator_inlet_temperature_k
    )
    assert store.cold_return_heat_rejected_to_ambient_j_per_kg_air == 0.0


@pytest.mark.parametrize("config", [BASE, NON_MONOTONE], ids=["86bar-6", "300bar-8"])
def test_heat_and_exergy_books_close(config):
    """Internal recuperation must cancel out of the coolant energy balance.

    If E-304 were ever booked as a source or a product, this closure is the test
    that catches it: the trunk's loss and the return's gain are the same joules.
    """
    result = solved(config)
    store = result.thermal_store
    closure = (
        store.recovered_heat_j_per_kg_air
        + store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
        - store.delivered_heat_j_per_kg_air
        - store.offtake_heat_j_per_kg_air
        - store.cold_return_heat_rejected_to_ambient_j_per_kg_air
        - store.storage_loss_j_per_kg_air
        - store.cold_storage_loss_j_per_kg_air
    )
    assert abs(closure) < 1.0
    assert abs(result.exergy.balance_residual_j_per_kg_air) < 1.0
    assert result.exergy.component_destruction_j_per_kg_air[
        "extraction_exchanger"
    ] >= 0.0


def test_user_side_is_one_counter_current_stream():
    dh = solved().heat_offtake
    tap = dh.taps[0]

    assert dh.network_water_per_kg_air == pytest.approx(tap.user_water_per_kg_air)
    assert tap.user_inlet_temperature_k == pytest.approx(dh.return_temperature_k)
    assert tap.user_outlet_temperature_k == pytest.approx(
        dh.supply_temperature_k, abs=1e-6
    )
    assert tap.heat_j_per_kg_air == pytest.approx(
        tap.plant_water_per_kg_air
        * WATER_CP_J_PER_KGK
        * (tap.plant_inlet_temperature_k - tap.plant_outlet_temperature_k),
        abs=1e-6,
    )
    assert tap.required_effectiveness <= tap.available_effectiveness + 2e-6


# ------------------------------------------------------- what the device buys

def test_the_ladder_beats_one_common_supply_on_the_tail_stages():
    """The reason E-304 exists, stated as a measurement.

    One tank temperature for every interheater wastes grade at the back of the
    train. With the ladder, no stage is fed more than the common margin above
    what it needs, so the worst excess is the margin itself rather than the
    whole span between the first and last stage demands.
    """
    result = solved()
    extraction = result.extraction_exchanger
    produced = [
        process.outlet.temperature_k
        for process in result.discharging.processes
        if process.kind == "interheating"
    ]
    excesses = [
        supply_k - produced_k
        for supply_k, produced_k in zip(
            extraction.extraction_temperatures_k, produced
        )
    ]
    span = max(produced) - min(produced)

    # Same inverse-HX tolerance as above: equal to a millikelvin, not exact.
    assert max(excesses) < span
    assert max(excesses) == pytest.approx(min(excesses), abs=1e-3)


def test_a_hot_user_return_is_feasible_because_the_trunk_continues_below_it():
    """The serial cascade could not do this, and that is why it was replaced.

    A 95/75 user return sits above several interheater demands. In the serial
    cascade the trunk had to stay above the user return all the way to the last
    bleed, which squeezed the turbines out. Here the trunk crosses E-302 once and
    then keeps descending inside E-304, well below the user return.
    """
    result = solved(
        heat_user_supply_temperature_c=95.0, heat_user_return_temperature_c=75.0
    )
    extraction = result.extraction_exchanger

    assert extraction.trunk_outlet_temperature_k < 75.0 + 273.15
    assert result.heat_offtake.heat_j_per_kg_air > 0.0
    assert abs(result.exergy.balance_residual_j_per_kg_air) < 1.0
