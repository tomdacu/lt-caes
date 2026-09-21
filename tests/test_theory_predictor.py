"""Analytic/reduced predictors remain subordinate to the real plant guards."""
from dataclasses import replace
from unittest.mock import patch

import pytest

from caes import CAESPlant, HeatOfftake, PlantConfig
from caes.numerics import SearchUnresolved, affine_fixed_point


def test_affine_closure_is_exact():
    assert affine_fixed_point(5., .5, 0., 20.) == 10.


@pytest.mark.parametrize("intercept,slope", [(0., 1.), (1., 1.), (100., .5)])
def test_affine_failure_is_not_nonlinear_nonexistence(intercept, slope):
    with pytest.raises(SearchUnresolved):
        affine_fixed_point(intercept, slope, 0., 20.)


@pytest.mark.parametrize("stages", [1, 4, 8])
def test_balanced_m0_predictor_closes_at_ambient(stages):
    config = replace(PlantConfig(), heat_offtake=HeatOfftake.NONE,
                     compressor_stages=stages, expander_stages=stages,
                     compressor_efficiency=1., expander_efficiency=1.,
                     intercooler_pressure_drop=0., interheater_pressure_drop=0.,
                     heat_exchanger_ntu=1e12)
    plant = CAESPlant(config)
    seed = plant._sensible_cold_seed(stages*1005./4180., 200., 1000.)
    assert seed == pytest.approx(config.ambient_temperature_k, abs=1e-6)


@pytest.mark.parametrize("override,inventory", [
    ({"coolant_minimum_temperature_c": 0.}, 2.45),
    ({"coolant_maximum_temperature_c": 100.}, 2.49),
])
def test_reduced_warm_branch_needs_one_charge_not_a_temperature_grid(override, inventory):
    plant = CAESPlant(replace(PlantConfig(), **override))
    with patch.object(plant, "_charge", wraps=plant._charge) as charge:
        result = plant._recover_cold_loop(inventory)
    assert charge.call_count == 1
    assert abs(result.thermal_store.cold_loop_closure_error_k) <= 5e-4
    assert abs(result.exergy.balance_residual_j_per_kg_air) < 1.


def test_analytic_predictor_cannot_bypass_user_temperature_guard():
    plant = CAESPlant(replace(PlantConfig(), heat_user_supply_temperature_c=400.))
    with patch("caes.plant.sampled_roots", return_value=[]) as fallback:
        with pytest.raises(SearchUnresolved):
            plant._recover_cold_loop(1.5)
    assert fallback.call_count == 2


def test_singular_surrogate_retains_sampled_fallback():
    plant = CAESPlant(replace(PlantConfig(), heat_offtake=HeatOfftake.NONE))
    with patch.object(plant, "_sensible_cold_seed", side_effect=SearchUnresolved("singular")), \
         patch("caes.plant.sampled_roots", return_value=[]) as fallback:
        with pytest.raises(SearchUnresolved):
            plant._recover_cold_loop(1.5)
    assert fallback.call_count == 2


def test_closed_lta_predictor_does_not_hide_a_better_branch():
    # Same inventory/configuration, two real closures. A perfectly converged
    # ideal-model continuation reaches the LOWER-work root. Feasibility is not
    # an optimality certificate, so the existing branch comparison must run.
    plant = CAESPlant(replace(PlantConfig(), heat_offtake=HeatOfftake.NONE,
                             storage_pressure_bar=25.))
    with patch.object(plant, "_sensible_cold_seed", return_value=343.73984042):
        result = plant._recover_cold_loop(1.06640625)
    assert abs(result.thermal_store.cold_loop_closure_error_k) <= 5e-4
    assert result.round_trip_efficiency > .64
