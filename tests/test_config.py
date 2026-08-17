import json

import pytest

from caes import PlantConfig, PlantMode, load_config, save_config
from caes.logic import active_fields


def test_gui_and_cli_share_one_json_round_trip(tmp_path):
    source = PlantConfig(coolant_maximum_temperature_c=175.0)
    path = tmp_path / "plant.json"

    assert save_config(source, path) == path
    assert load_config(path) == source


def test_shared_json_loader_rejects_unknown_fields(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"obsolete_option": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="obsolete_option"):
        load_config(path)


def test_fractional_storage_loss_field_is_rejected(tmp_path):
    path = tmp_path / "obsolete-storage-loss.json"
    path.write_text(
        json.dumps({"thermal_storage_loss_fraction": 0.02}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="thermal_storage_loss_fraction"):
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


@pytest.mark.parametrize("field", ("ambient_heat_exchanger_ntu",))
def test_diabatic_inputs_must_be_positive(field):
    with pytest.raises(ValueError, match=field):
        PlantConfig(**{field: 0.0})


@pytest.mark.parametrize(
    ("field", "value"),
    (("coolant_maximum_temperature_c", -90.0), ("coolant_minimum_temperature_c", -300.0)),
)
def test_direct_coolant_limits_are_validated(field, value):
    with pytest.raises(ValueError):
        PlantConfig(**{field: value})


def test_coolant_limits_are_active_only_for_the_coolant_tes():
    assert "coolant_maximum_temperature_c" in active_fields(PlantConfig())
    assert "cold_return_cooler_ntu" in active_fields(PlantConfig())
    assert "coolant_maximum_temperature_c" not in active_fields(
        PlantConfig(mode=PlantMode.DIABATIC)
    )


@pytest.mark.parametrize(
    "removed",
    (
        "minimum_expander_outlet_temperature_c",
        "use_natural_gas_topping",
        "combustor_efficiency",
        "natural_gas_lhv_mj_per_kg",
        "natural_gas_exergy_factor",
    ),
)
def test_removed_fixed_temperature_and_fuel_fields_fail_loudly(removed):
    from caes import config_from_dict

    with pytest.raises(ValueError, match=removed):
        config_from_dict({removed: 1.0})


def test_removed_ideal_approach_field_is_rejected():
    """The D-CAES ambient exchangers are finite-NTU now; the old idealized
    approach-temperature input must fail loudly, not be silently ignored."""
    from caes import config_from_dict

    with pytest.raises(ValueError, match="ambient_heat_exchanger_approach_c"):
        config_from_dict({"ambient_heat_exchanger_approach_c": 5.0})


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
