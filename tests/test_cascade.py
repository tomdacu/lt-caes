"""Invariants of the single-store, serial heat-user coolant cascade.

There is one mixed hot store.  For ``K`` groups the complete hot trunk crosses
exactly ``K`` user exchangers.  After exchanger ``g`` the coolant required by
interheater group ``g`` leaves the trunk; only the remainder reaches exchanger
``g + 1``.  There is deliberately no terminal exchanger after the last bleed.
"""

from dataclasses import replace

import pytest

from caes import CAESPlant, HeatOfftake, PlantConfig
from caes.heat_exchangers import WATER_CP_J_PER_KGK


USER_NTU = 5.0
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
)


def cascade(groups: int, **overrides):
    return CAESPlant(
        replace(BASE, coolant_cascade_groups=groups, **overrides)
    ).run()


def interheater_branches(result):
    return [
        process.heat_exchanger
        for process in result.discharging.processes
        if process.kind == "interheating" and process.heat_exchanger
    ]


@pytest.mark.parametrize("groups", [1, 2, 3, 4])
def test_group_count_is_exchanger_count_not_store_count(groups):
    result = cascade(groups)
    store = result.thermal_store
    taps = result.heat_offtake.taps

    assert len(store.hot_level_temperatures_k) == 1
    assert len(store.hot_level_water_mass_ratios) == 1
    assert store.hot_level_temperatures_k[0] == pytest.approx(
        store.hot_temperature_available_k
    )
    assert store.hot_level_water_mass_ratios[0] == pytest.approx(
        store.total_water_mass_ratio
    )
    assert len(taps) == groups


@pytest.mark.parametrize("groups", [1, 2, 3, 4])
def test_complete_trunk_then_bleed_mass_balance(groups):
    result = cascade(groups)
    store = result.thermal_store
    taps = result.heat_offtake.taps
    branches = interheater_branches(result)

    assert taps[0].plant_water_per_kg_air == pytest.approx(
        store.total_water_mass_ratio, abs=2e-6
    )
    assert sum(hx.water_air_mass_ratio for hx in branches) == pytest.approx(
        store.total_water_mass_ratio, abs=2e-6
    )
    assert all(
        later.plant_water_per_kg_air < earlier.plant_water_per_kg_air
        for earlier, later in zip(taps, taps[1:])
    )
    for earlier, later in zip(taps, taps[1:]):
        assert later.plant_inlet_temperature_k == pytest.approx(
            earlier.plant_outlet_temperature_k, abs=1e-9
        )


@pytest.mark.parametrize("groups", [2, 3, 4])
def test_equal_drop_makes_first_exchanger_the_largest(groups):
    taps = cascade(groups).heat_offtake.taps
    drops = [
        tap.plant_inlet_temperature_k - tap.plant_outlet_temperature_k
        for tap in taps
    ]
    duties = [tap.heat_j_per_kg_air for tap in taps]

    assert max(drops) - min(drops) < 1e-7
    assert duties == sorted(duties, reverse=True)
    assert all(a > b for a, b in zip(duties, duties[1:]))


@pytest.mark.parametrize("groups", [1, 2, 4])
def test_user_side_is_one_counter_current_stream(groups):
    dh = cascade(groups).heat_offtake
    taps = dh.taps

    assert len({round(t.user_water_per_kg_air, 12) for t in taps}) == 1
    assert dh.network_water_per_kg_air == pytest.approx(
        taps[0].user_water_per_kg_air
    )
    assert taps[-1].user_inlet_temperature_k == pytest.approx(
        dh.return_temperature_k
    )
    assert taps[0].user_outlet_temperature_k == pytest.approx(
        dh.supply_temperature_k, abs=1e-6
    )
    for hotter, colder in zip(taps, taps[1:]):
        assert colder.user_outlet_temperature_k == pytest.approx(
            hotter.user_inlet_temperature_k
        )
    for tap in taps:
        assert tap.heat_j_per_kg_air == pytest.approx(
            tap.plant_water_per_kg_air
            * WATER_CP_J_PER_KGK
            * (tap.plant_inlet_temperature_k - tap.plant_outlet_temperature_k),
            abs=1e-6,
        )


@pytest.mark.parametrize("groups", [1, 2, 3, 4])
def test_every_user_exchanger_respects_finite_ntu_capacity(groups):
    dh = cascade(groups).heat_offtake
    for tap in dh.taps:
        assert tap.required_effectiveness <= tap.available_effectiveness + 2e-6
    assert dh.heat_exchanger_ntu == USER_NTU
    assert dh.minimum_effectiveness_margin >= -2e-6


@pytest.mark.parametrize("groups", [1, 2, 4])
def test_heat_and_exergy_books_close(groups):
    result = cascade(groups)
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
    assert sum(t.heat_j_per_kg_air for t in result.heat_offtake.taps) == pytest.approx(
        result.heat_offtake.heat_j_per_kg_air
    )


def test_one_group_is_one_exchanger_followed_by_all_interheater_bleeds():
    result = cascade(1)
    tap = result.heat_offtake.taps[0]
    store = result.thermal_store

    assert tap.plant_water_per_kg_air == pytest.approx(
        store.total_water_mass_ratio, abs=2e-6
    )
    assert tap.plant_inlet_temperature_k == pytest.approx(
        store.hot_temperature_available_k
    )
    supplies = {
        round(hx.water_inlet_temperature_k, 7)
        for hx in interheater_branches(result)
    }
    assert supplies == {round(tap.plant_outlet_temperature_k, 7)}


def test_groups_are_bounded_only_by_expander_count():
    for groups in (0, 5):
        with pytest.raises(ValueError, match="coolant_cascade_groups"):
            PlantConfig(expander_stages=4, coolant_cascade_groups=groups)
    PlantConfig(compressor_stages=1, expander_stages=4, coolant_cascade_groups=4)
