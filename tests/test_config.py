import json

import pytest

from caes import HeatOfftake, PlantConfig, load_config, save_config
from caes.logic import active_fields


def test_gui_and_cli_share_one_json_round_trip(tmp_path):
    source = PlantConfig(coolant_maximum_temperature_c=175.0)
    path = tmp_path / "plant.json"

    assert save_config(source, path) == path
    assert load_config(path) == source


@pytest.mark.parametrize(
    "unknown",
    (
        "obsolete_option",
        "thermal_storage_loss_fraction",
        "minimum_expander_outlet_temperature_c",
        "use_natural_gas_topping",
        "combustor_efficiency",
        "natural_gas_lhv_mj_per_kg",
        "natural_gas_exergy_factor",
        "ambient_heat_exchanger_approach_c",
    ),
)
def test_unknown_and_retired_fields_fail_loudly(tmp_path, unknown):
    """A file naming a field this model does not have must stop, not be guessed at.

    Renamed keys keep loading (with a warning) and *removed* keys are ignored
    explicitly; a key that is neither is an error. The JSON-file variant is
    included because ``load_config`` is what a user actually calls.
    """
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps({unknown: 1.0}), encoding="utf-8")

    with pytest.raises(ValueError, match=unknown):
        load_config(path)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("thermal_storage_tank_ua_w_per_k", -0.001),
        ("storage_duration_hours", -1.0),
        ("cold_return_cooler_ntu", -0.1),
    ),
)
def test_physical_storage_loss_inputs_must_be_nonnegative(field, value):
    with pytest.raises(ValueError, match=field):
        PlantConfig(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    (("coolant_maximum_temperature_c", -90.0), ("coolant_minimum_temperature_c", -300.0)),
)
def test_direct_coolant_limits_are_validated(field, value):
    with pytest.raises(ValueError):
        PlantConfig(**{field: value})


def test_the_heat_user_is_the_only_axis_that_dormants_fields():
    """LTA and LTAHP are one plant: installing a user cannot silence the coolant
    inputs, and removing it must silence exactly the E-302/E-304 group."""
    lta = active_fields(PlantConfig(heat_offtake=HeatOfftake.NONE))
    for field in ("coolant_maximum_temperature_c", "cold_return_cooler_ntu",
                  "heat_exchanger_ntu", "optimization_objective"):
        assert field in lta
    for field in ("heat_user_supply_temperature_c", "heat_user_return_temperature_c",
                  "heat_user_exchanger_ntu", "extraction_exchanger_ntu"):
        assert field not in lta

    ltahp = active_fields(PlantConfig(heat_offtake=HeatOfftake.HEAT_USER))
    for field in ("heat_user_supply_temperature_c", "extraction_exchanger_ntu"):
        assert field in ltahp


@pytest.mark.parametrize(
    "retired",
    ("coolant_cascade_groups", "thermal_storage_levels", "ambient_heat_exchanger_ntu"),
)
def test_retired_fields_load_with_a_warning(retired):
    """Old files keep loading: a retired key is ignored, never remapped.

    The hot store is one mixed state, the user side is one exchanger plus one
    extraction per stage, and the adiabatic train has no air/ambient exchanger
    at all; each key therefore has nothing left to control, and silently
    copying its value into another field would alter the experiment.
    """
    from caes import config_from_dict

    with pytest.warns(DeprecationWarning, match=retired):
        config = config_from_dict({retired: 3})

    assert config == PlantConfig()


def test_a_retired_mode_key_selects_nothing_or_stops_the_load(tmp_path):
    """A record of an adiabatic experiment still loads; a diabatic record must
    NOT be answered with a different plant while pretending to read it."""
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps({**PlantConfig().to_dict(), "mode": "adiabatic"}), encoding="utf-8"
    )
    with pytest.warns(DeprecationWarning, match="mode"):
        assert load_config(path) == PlantConfig()

    path.write_text(
        json.dumps({**PlantConfig().to_dict(), "mode": "diabatic"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="diabatic"):
        load_config(path)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ambient_temperature_c", -300.0),
        ("heat_user_supply_temperature_c", -300.0),
        ("heat_user_return_temperature_c", -300.0),
        ("coolant_maximum_temperature_c", -300.0),
        ("coolant_minimum_temperature_c", -300.0),
    ),
)
def test_every_temperature_field_is_validated_against_absolute_zero(field, value):
    with pytest.raises(ValueError, match="absolute zero"):
        PlantConfig(**{field: value})


def test_ambient_temperature_must_stay_inside_the_moisture_correlation_domain():
    with pytest.raises(ValueError, match="moisture correlations"):
        PlantConfig(ambient_temperature_c=-200.0)


def test_removed_exergy_objective_maps_to_the_concept_objective_with_a_warning():
    """Old JSON files selecting max_total_exergy_efficiency keep working: the
    objective coincides with max electrical efficiency when there is no heat
    user, and with the combined delivery ratio under district heating."""
    from caes import HeatOfftake, OptimizationObjective, config_from_dict

    with pytest.warns(DeprecationWarning, match="max_total_exergy_efficiency"):
        none_config = config_from_dict(
            {
                "optimization_objective": "max_total_exergy_efficiency",
                "heat_offtake": HeatOfftake.NONE.value,
            }
        )
    assert none_config.optimization_objective is (
        OptimizationObjective.MAX_ELECTRIC_EFFICIENCY
    )

    with pytest.warns(DeprecationWarning, match="max_total_exergy_efficiency"):
        dh_config = config_from_dict(
            {
                "optimization_objective": "max_total_exergy_efficiency",
                "heat_offtake": HeatOfftake.HEAT_USER.value,
            }
        )
    assert dh_config.optimization_objective is (
        OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY
    )
