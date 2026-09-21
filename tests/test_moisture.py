"""Humidity propagation and pressure dew/frost-point diagnostics."""

import pytest

from caes import CAESPlant, HeatOfftake, PlantConfig, PlantMode
from caes.moisture import (
    compressor_moisture_inventory,
    expander_moisture_inventory,
    humidity_ratio_from_vapor_pressure,
    inlet_humidity_ratio,
    phase_change_temperature_k,
    saturation_humidity_ratio,
    saturation_vapor_pressure_pa,
    water_vapor_enhancement_factor,
)
from caes.thermal_limits import (
    DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION,
    REFERENCE_WET_EXPANDER_MAX_INLET_LIQUID_MASS_FRACTION,
    minimum_wet_expander_temperature_k,
)


def test_enhancement_factor_matches_the_real_humid_air_model():
    """Water vapour in compressed air is not pure-component water vapour.

    The pure saturation curve understates the equilibrium water content badly
    at cavern pressures - by 28% at 100 bar - which is the wrong direction for
    a moisture safety screen. The corrected forward map must agree with
    CoolProp's real humid-air backend, the same library the air properties
    come from.
    """
    from CoolProp.HumidAirProp import HAPropsSI

    worst = 0.0
    for pressure_pa in (1.01325e5, 5e5, 10e5, 30e5, 70e5, 99e5):
        for temperature_k in (243.15, 263.15, 288.15, 303.15, 333.15):
            reference = HAPropsSI(
                "W", "P", pressure_pa, "T", temperature_k, "R", 1.0
            )
            model = saturation_humidity_ratio(pressure_pa, temperature_k)
            worst = max(worst, abs(model / reference - 1.0))
    assert worst < 5e-3, f"worst relative error {worst:.2%}"

    # It is a real correction, not a rounding one, and it grows with pressure.
    assert water_vapor_enhancement_factor(1.01325e5, 288.15) == pytest.approx(
        1.004, abs=0.01
    )
    assert water_vapor_enhancement_factor(100e5, 288.15) == pytest.approx(
        1.392, abs=0.02
    )
    # Above the humid-air backend's own range the factor is extrapolated, and
    # it must keep rising with pressure rather than flattening out.
    assert (
        water_vapor_enhancement_factor(250e5, 288.15)
        > water_vapor_enhancement_factor(150e5, 288.15)
        > water_vapor_enhancement_factor(100e5, 288.15)
    )


@pytest.mark.parametrize("pressure_bar", [1.5, 10.0, 100.0, 250.0])
@pytest.mark.parametrize("temperature_c", [-23.15, -10.0, 15.0, 36.85, 66.85])
def test_saturation_and_phase_boundary_are_the_same_relation(
    pressure_bar, temperature_c
):
    """Forward and inverse must invert each other exactly.

    The enhancement factor is applied in the one place both maps share. If it
    were applied to the saturated humidity alone, the module would report a
    dew point that disagreed with the state it was computed from.
    """
    pressure_pa = pressure_bar * 1e5
    temperature_k = temperature_c + 273.15
    ratio = saturation_humidity_ratio(pressure_pa, temperature_k)
    assert phase_change_temperature_k(pressure_pa, ratio) == pytest.approx(
        temperature_k, abs=1e-4
    )


def test_correction_raises_the_stored_moisture_and_the_expander_floor():
    """The correction moves the safety screen the conservative way.

    More stored water means a higher pressure dew point and a higher wet-rated
    lower envelope, so the anti-icing limit the solver enforces gets stricter,
    not looser.
    """
    result = CAESPlant(PlantConfig()).run()
    moisture = result.moisture
    assert moisture is not None
    stored = moisture.stored_air_water_vapor_kg_per_kg_dry_air

    uncorrected = humidity_ratio_from_vapor_pressure(
        saturation_vapor_pressure_pa(result.charging.outlet.temperature_k),
        moisture.storage_pressure_pa,
    )
    assert stored > uncorrected * 1.2

    for pressure_pa in (1.5e5, 10e5, 100e5):
        assert minimum_wet_expander_temperature_k(
            pressure_pa, stored
        ) >= minimum_wet_expander_temperature_k(pressure_pa, uncorrected)


def test_default_ambient_humidity_has_expected_dew_point():
    config = PlantConfig(
        ambient_temperature_c=15.0,
        ambient_pressure_bar=1.01325,
        ambient_relative_humidity=0.60,
    )
    ratio = inlet_humidity_ratio(config)
    dew_point_c = phase_change_temperature_k(
        config.ambient_pressure_bar * 1e5, ratio
    ) - 273.15

    # 6.372 g/kg, not the 6.346 a pure-water saturation curve gives: even at
    # one atmosphere the enhancement factor is 1.004. The dew point is the
    # inverse of the same relation and must agree with the ambient state it
    # came from.
    assert ratio * 1000 == pytest.approx(6.372, abs=0.01)
    assert dew_point_c == pytest.approx(7.31, abs=0.05)


@pytest.mark.parametrize("mode", [PlantMode.ADIABATIC, PlantMode.DIABATIC])
def test_charge_moisture_balance_closes_and_storage_boundary_varies_with_pressure(mode):
    result = CAESPlant(PlantConfig(mode=mode)).run()
    moisture = result.moisture
    assert moisture is not None
    assert moisture.inlet_water_vapor_kg_per_kg_dry_air == pytest.approx(
        moisture.surface_separator_water_kg_per_kg_dry_air
        + moisture.stored_air_water_vapor_kg_per_kg_dry_air,
        abs=1e-12,
    )

    storage_pdp_c = phase_change_temperature_k(
        moisture.storage_pressure_pa,
        moisture.stored_air_water_vapor_kg_per_kg_dry_air,
    ) - 273.15
    first_expander_outlet = next(
        process.outlet
        for process in result.discharging.processes
        if process.kind == "expansion"
    )
    first_stage_boundary_c = phase_change_temperature_k(
        first_expander_outlet.pressure_pa,
        moisture.stored_air_water_vapor_kg_per_kg_dry_air,
    ) - 273.15

    assert storage_pdp_c == pytest.approx(15.0, abs=0.02)
    # The claim is that the boundary FALLS with pressure, not which side of
    # freezing it lands on: with the enhancement factor applied, the first
    # stage of the default train now stays in the liquid-permitted region,
    # which the wet-rated envelope explicitly allows.
    assert first_stage_boundary_c < storage_pdp_c
    assert first_expander_outlet.pressure_pa < moisture.storage_pressure_pa


def test_final_aftercooler_and_separator_remove_cavern_liquid_risk():
    """The protected discharge basis must BE the last separator's real outlet.

    This used to compare two summary fields that were identical by construction,
    so it could never fail. It now checks the reported cavern vapour ratio
    against the physics that is supposed to produce it: the last charge-side
    cooler that actually condenses, and the local saturation ratio at its own
    outlet state.
    """
    adiabatic = CAESPlant(PlantConfig(mode=PlantMode.ADIABATIC)).run()
    diabatic = CAESPlant(PlantConfig(mode=PlantMode.DIABATIC)).run()

    for result in (adiabatic, diabatic):
        moisture = result.moisture
        assert moisture is not None
        assert moisture.surface_separator_water_kg_per_kg_dry_air > 0.0
        condensers = [
            process
            for process in result.charging.processes
            if process.kind in {"intercooling", "aftercooling"}
            and process.outlet.temperature_k < process.inlet.temperature_k - 1e-9
        ]
        assert condensers, "the default trains must condense somewhere"
        final = condensers[-1]
        assert moisture.stored_air_water_vapor_kg_per_kg_dry_air == pytest.approx(
            saturation_humidity_ratio(
                final.outlet.pressure_pa, final.outlet.temperature_k
            ),
            rel=1e-12,
        )
        assert (
            moisture.stored_air_water_vapor_kg_per_kg_dry_air
            < moisture.inlet_water_vapor_kg_per_kg_dry_air
        )


def test_single_final_separator_would_feed_liquid_to_intermediate_compressors():
    adiabatic = CAESPlant(PlantConfig(mode=PlantMode.ADIABATIC)).run()
    diabatic = CAESPlant(PlantConfig(mode=PlantMode.DIABATIC)).run()

    a_final_only = compressor_moisture_inventory(
        adiabatic,
        separate_after_each_cooler=False,
    )
    d_final_only = compressor_moisture_inventory(
        diabatic,
        separate_after_each_cooler=False,
    )
    d_every_cooler = compressor_moisture_inventory(
        diabatic,
        separate_after_each_cooler=True,
    )

    a_suction_liquid = {
        point.equipment_tag: point.condensed_water_mass_fraction
        for point in a_final_only
        if point.position == "suction"
    }
    d_suction_liquid = {
        point.equipment_tag: point.condensed_water_mass_fraction
        for point in d_final_only
        if point.position == "suction"
    }
    d_protected_suction_liquid = [
        point.condensed_water_mass_fraction
        for point in d_every_cooler
        if point.position == "suction"
    ]

    # These bounds state the CLAIM - that a single final separator leaves a
    # materially wet suction on the last adiabatic bodies and on every diabatic
    # one - rather than pinning the solver's exact numbers.  The adiabatic
    # values move with the optimized water inventory, so a tight pin here fails
    # for reasons that have nothing to do with moisture.
    a_suction_liquid_in_order = list(a_suction_liquid.values())
    assert max(a_suction_liquid_in_order[:-2]) == pytest.approx(0.0)
    assert min(a_suction_liquid_in_order[-2:]) > 2e-4  # >0.02 wt%
    d_suction_liquid_in_order = list(d_suction_liquid.values())
    assert d_suction_liquid_in_order[0] == pytest.approx(0.0)
    assert min(d_suction_liquid_in_order[1:]) > 1e-3  # every later body >0.1 wt%
    assert d_suction_liquid_in_order[-1] > 5e-3  # final body >0.5 wt%
    assert max(d_protected_suction_liquid) == pytest.approx(0.0)


@pytest.mark.parametrize("mode", [PlantMode.ADIABATIC, PlantMode.DIABATIC])
def test_default_expander_inventory_stays_inside_reference_inlet_liquid_cap(mode):
    result = CAESPlant(PlantConfig(mode=mode)).run()
    points = expander_moisture_inventory(result)
    assert points

    expander_connections = [
        point for point in points if point.equipment_tag.startswith("T-")
    ]
    assert max(
        point.condensed_water_mass_fraction for point in expander_connections
    ) < REFERENCE_WET_EXPANDER_MAX_INLET_LIQUID_MASS_FRACTION
    # Condensate at the separator inlets is permitted - the machine is
    # wet-rated and the envelope allows the liquid region - but it must stay
    # inside the screen that keeps the dry-air energy balance valid, which is
    # far stricter than the OEM discharge capacity. Asserting exactly zero here
    # only held while the model understated the moisture.
    assert max(
        (
            point.condensed_water_mass_fraction
            for point in points
            if point.position == "separator inlet"
        ),
        default=0.0,
    ) < DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION


def test_heat_offtake_train_has_one_expander_group_per_stage():
    config = PlantConfig(heat_offtake=HeatOfftake.HEAT_USER)
    points = expander_moisture_inventory(CAESPlant(config).run())
    suction_points = [
        point
        for point in points
        if point.equipment_tag.startswith("T-") and point.position == "suction"
    ]
    discharge_points = [
        point
        for point in points
        if point.equipment_tag.startswith("T-") and point.position == "discharge"
    ]
    assert len(suction_points) == config.expander_stages
    assert len(discharge_points) == config.expander_stages
    assert not any("turbine bypassed" in point.note for point in discharge_points)


@pytest.mark.parametrize("relative_humidity", [0.0, -0.1, 1.01])
def test_invalid_ambient_relative_humidity_is_rejected(relative_humidity):
    with pytest.raises(ValueError, match="ambient_relative_humidity"):
        PlantConfig(ambient_relative_humidity=relative_humidity)
