"""Search failures are not physical infeasibility certificates.

These witnesses were found independently of the recovery algorithm. No test
supplies a good cold-loop, charge, or extraction-margin seed.
"""

from dataclasses import replace
from math import nan

import pytest

from caes import CAESPlant, HeatOfftake, PlantConfig
from caes.numerics import SearchUnresolved, bracketed_root, sampled_roots, simplex_feasible
from caes.thermal_limits import minimum_wet_expander_temperature_k


def assert_closed_and_wet_safe(result):
    assert abs(result.thermal_store.cold_loop_closure_error_k) <= 5e-4
    humidity = result.moisture.stored_air_water_vapor_kg_per_kg_dry_air
    for process in result.discharging.processes:
        if process.kind == "expansion":
            floor = minimum_wet_expander_temperature_k(process.outlet.pressure_pa, humidity)
            assert process.outlet.temperature_k >= floor - 1e-4


@pytest.mark.parametrize("power", [1, 3, 15])
def test_safeguard_retains_badly_scaled_signed_bracket(power):
    function = lambda x: x**power - .3
    root = bracketed_root(function, 0., 1., residual_tolerance=1e-11)
    assert abs(function(root)) <= 1e-11


def test_discontinuity_is_not_an_accepted_root():
    with pytest.raises(SearchUnresolved):
        bracketed_root(lambda x: -1. if x < .4 else 1., 0., 1., residual_tolerance=1e-8)


def test_undefined_interior_has_no_sign():
    with pytest.raises(SearchUnresolved):
        bracketed_root(lambda x: nan if .3 < x < .7 else x-.5,
                       0., 1., residual_tolerance=1e-8)
    assert sampled_roots(lambda x: None if .3 < x < .7 else x-.5,
                         0., 1., subdivisions=16, residual_tolerance=1e-8) == []


def test_isolates_both_edges_of_a_valid_island():
    def residual(x):
        return (x-.201)*(x-.699) if .2 < x < .7 else None
    roots = sampled_roots(residual, 0., 1., subdivisions=8, residual_tolerance=1e-9)
    assert any(abs(x-.201) < 1e-7 for x in roots)
    assert any(abs(x-.699) < 1e-7 for x in roots)


def test_empty_sampling_does_not_claim_tangential_root_absence():
    # Finite sampling cannot exclude tangential roots. The API returns no
    # certificate; plant callers explicitly raise SearchUnresolved.
    assert sampled_roots(lambda x: (x-.123456789)**2, 0., 1.,
                         subdivisions=8, residual_tolerance=1e-14) == []


def test_simplex_search_conserves_mass_at_every_trial():
    def violation(point):
        assert min(point) >= 0.
        assert sum(point) == pytest.approx(1., abs=1e-14)
        return max(0., .6-point[0])**2
    point = simplex_feasible(violation, 1., 6)
    assert point is not None
    assert point[0] >= .6


@pytest.mark.parametrize("overrides,inventory,rte", [
    ({"coolant_minimum_temperature_c": 0.}, 2.45, .55226368475),
    ({"coolant_maximum_temperature_c": 100.}, 2.49, .55216146737),
])
def test_rejected_cold_loop_witness_needs_no_manual_seed(overrides, inventory, rte):
    plant = CAESPlant(replace(PlantConfig(), **overrides))
    result = plant._close_cold_loop(inventory)
    assert_closed_and_wet_safe(result)
    assert result.round_trip_efficiency == pytest.approx(rte, abs=2e-7)


@pytest.mark.parametrize("overrides", [
    {"coolant_minimum_temperature_c": 0.},
    {"coolant_maximum_temperature_c": 100.},
])
def test_inventory_search_recovers_previously_rejected_design(overrides):
    config = replace(PlantConfig(), **overrides)
    result = CAESPlant(config).run()
    assert_closed_and_wet_safe(result)
    assert result.round_trip_efficiency > .54
    assert result.useful_energy_delivery_ratio > 1.04


def test_recovery_discards_arbitrary_stale_seeds():
    plant = CAESPlant(replace(PlantConfig(), coolant_minimum_temperature_c=0.))
    plant._cold_loop_seed = (29., 600.)
    plant._charge_seed = (600., [5.] * 6)
    plant._extraction_margin_fraction_seed = .99
    result = plant._recover_cold_loop(2.45)
    assert_closed_and_wet_safe(result)
    assert result.round_trip_efficiency == pytest.approx(.55226368475, abs=2e-7)


def test_lta_feasible_allocation_between_original_n_plus_one_candidates():
    config = replace(PlantConfig(), heat_offtake=HeatOfftake.NONE,
                     coolant_minimum_temperature_c=40., coolant_maximum_temperature_c=300.)
    plant = CAESPlant(config)
    _, store = plant._charge_adiabatic(333.15, 1.)
    design = plant._discharge_absorbing(store)
    assert sum(ratio for ratio, _, _ in design.returns) == pytest.approx(1., abs=2e-6)
    assert min(temperature for _, temperature, _ in design.returns) >= 313.15-1e-4
    # This certifies the allocation, NOT a closed whole-plant cold loop.
    assert design.cycle.work_j_per_kg < -390_000


@pytest.mark.parametrize("overrides", [
    dict(compressor_efficiency=.95, expander_efficiency=.95,
         heat_exchanger_ntu=30., heat_user_exchanger_ntu=10.,
         extraction_exchanger_ntu=10., intercooler_pressure_drop=0.,
         interheater_pressure_drop=0.),
    dict(expander_stages=4),
    dict(storage_pressure_bar=300., compressor_stages=4, expander_stages=4),
    dict(heat_user_supply_temperature_c=110., heat_user_return_temperature_c=90.),
])
def test_materialized_wet_envelope_uses_declared_tolerance(overrides):
    plant = CAESPlant(replace(PlantConfig(), **overrides))
    plant._preserve_search_path = True
    original = plant._run_fast_search()
    plant._preserve_search_path = False
    result = plant._polish_wet_result(original)
    assert_closed_and_wet_safe(result)
    assert result.charging == original.charging
    assert result.thermal_store.total_water_mass_ratio == original.thermal_store.total_water_mass_ratio
    assert result.round_trip_efficiency == pytest.approx(original.round_trip_efficiency, abs=3e-7)
