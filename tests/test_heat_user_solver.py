"""The heat-user plant solved as a one-variable problem in the inventory.

Under minimum-duty dispatch the E-304 ladder depends on the inventory and the
stored humidity only, so the cold tank is explicit and no coolant-loop root is
needed. These tests hold that structure, the first-law identity that explains
the delivery ratio, and the rule that the charge split is chosen by exergy.
See docs/14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md.
"""

from __future__ import annotations

from math import log

import pytest

from caes import CAESPlant
from caes.numerics import brent_maximize, geometric_grid

from conftest import LTAHP, assert_expander_envelope, lthp


def _aftercooler_duty(result) -> float:
    coolers = [p for p in result.charging.processes if p.kind == "aftercooling"]
    return sum(p.inlet.enthalpy_j_per_kg - p.outlet.enthalpy_j_per_kg for p in coolers)


def test_the_cold_tank_does_not_depend_on_the_trial_cold_tank():
    """Fact 2: the produced cold tank is one evaluation, not a root."""
    plant = CAESPlant(LTAHP)
    produced = []
    for trial_c in (5.0, 25.0, 45.0):
        plant._heat_user_cold_seed = trial_c + 273.15
        result = plant._heat_user_design(1.5, optimize_split=False)
        produced.append(result.thermal_store.cold_temperature_k)
        assert abs(result.thermal_store.cold_loop_closure_error_k) < 5e-4
    assert max(produced) - min(produced) < 1e-9


def test_first_law_identity_closes_the_delivery_ratio():
    """W_exp + Q_user = W_comp + Q_amb + (h0 - h_exh) - Q_ac - L_tanks."""
    result = CAESPlant(LTAHP).run()
    intake = result.charging.processes[0].inlet.enthalpy_j_per_kg
    exhaust = result.discharging.processes[-1].outlet.enthalpy_j_per_kg
    store = result.thermal_store
    left = result.expansion_work_output_j_per_kg + result.heat_offtake.heat_j_per_kg_air
    right = (
        result.compression_work_input_j_per_kg
        + result.external_heat_input_j_per_kg
        + (intake - exhaust)
        - _aftercooler_duty(result)
        - store.storage_loss_j_per_kg_air
        - store.cold_storage_loss_j_per_kg_air
    )
    assert left == pytest.approx(right, abs=1.0)


def test_exergy_weight_is_the_carnot_factor_of_the_user_stream():
    plant = CAESPlant(LTAHP)
    t0 = LTAHP.ambient_temperature_k
    supply = LTAHP.heat_user_supply_temperature_k
    back = LTAHP.heat_user_return_temperature_k
    expected = 1.0 - t0 * log(supply / back) / (supply - back)
    assert plant._heat_value_weight() == pytest.approx(expected, rel=1e-12)


def test_the_exergy_split_never_loses_exergy_and_serves_a_hot_user_better():
    """Hot user: first intercooler starved, last one fed more, exergy up."""
    config = lthp(heat_user_supply_temperature_c=110.0,
                  heat_user_return_temperature_c=90.0)
    plant = CAESPlant(config)
    base = plant._heat_user_design(1.03, optimize_split=False)
    best = plant._heat_user_design(1.03, optimize_split=True)
    matched = [p.heat_exchanger.water_air_mass_ratio
               for p in base.charging.processes if p.kind == "intercooling"]
    split = [p.heat_exchanger.water_air_mass_ratio
             for p in best.charging.processes if p.kind == "intercooling"]
    assert sum(split) == pytest.approx(sum(matched), rel=1e-9)
    assert split[0] < 0.1 * matched[0]
    assert split[-1] > 1.2 * matched[-1]
    base_ex = base.exergy.total_useful_exergy_efficiency
    best_ex = best.exergy.total_useful_exergy_efficiency
    assert best_ex > base_ex + 0.005
    assert abs(best.exergy.balance_residual_j_per_kg_air) < 1.0


def test_search_result_is_closed_and_wet_safe():
    result = CAESPlant(LTAHP).run()
    assert_expander_envelope(result)
    assert abs(result.thermal_store.cold_loop_closure_error_k) <= 5e-4
    assert result.useful_energy_delivery_ratio > 1.07
    assert abs(result.exergy.balance_residual_j_per_kg_air) < 1.0


def test_an_infeasible_plant_is_reported_as_a_constraint_map():
    with pytest.raises(ValueError) as rejection:
        CAESPlant(lthp(storage_pressure_bar=250.0, compressor_stages=3,
                       expander_stages=3)).run()
    message = str(rejection.value)
    assert "binding constraint along the coolant inventory" in message
    assert "coolant maximum temperature limit exceeded" in message
    assert "E-304 exchanger class is too small" in message


def test_geometric_grid_covers_both_ends_within_the_ratio():
    grid = geometric_grid(0.375, 6.0, 1.25)
    assert grid[0] == pytest.approx(0.375) and grid[-1] == pytest.approx(6.0)
    assert max(b / a for a, b in zip(grid, grid[1:])) <= 1.25 + 1e-12


def test_brent_finds_interior_and_ranks_infeasible_trials_last():
    x, value = brent_maximize(lambda x: -(x - 0.3) ** 2, 0.0, 1.0, x_tolerance=1e-6)
    assert x == pytest.approx(0.3, abs=1e-5) and value == pytest.approx(0.0, abs=1e-9)
    x, value = brent_maximize(
        lambda x: None if x > 0.6 else x, 0.0, 1.0, x_tolerance=1e-6
    )
    assert value is not None and x == pytest.approx(0.6, abs=1e-4)
