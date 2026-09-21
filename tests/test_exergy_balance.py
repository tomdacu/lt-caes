"""Regression tests for the exergy books.

These exist because the model used to LOOK right and BE wrong. Every test here
corresponds to a bug that was actually found in the code, and each one fails
loudly if the bug is reintroduced. If you are changing caes.plant._summarize or
caes.exergy, these are the tests that decide whether you got away with it.
"""

from math import exp

import pytest

from caes import (
    CAESPlant,
    HeatOfftake,
    OptimizationObjective,
    PlantConfig,
    PlantMode,
)
from caes.exergy import air_exergy
from conftest import LTAHP

# A deliberately broad sweep: a low-pressure single-stage train,
# lopsided stage counts, multiple NTU sizes, both surplus destinations, both
# modes, and the pressure-drop-free limit.
CONFIGURATIONS = [
    pytest.param(PlantConfig(), id="adiabatic-ntu-default"),
    pytest.param(PlantConfig(mode=PlantMode.DIABATIC), id="diabatic"),
    pytest.param(
        PlantConfig(
            compressor_stages=1,
            expander_stages=1,
            storage_pressure_bar=30.0,
            coolant_maximum_temperature_c=450.0,
        ),
        id="single-stage",
    ),
    pytest.param(PlantConfig(compressor_stages=6, expander_stages=3), id="lopsided-stages"),
    pytest.param(
        LTAHP,
        id="heat-user",
    ),
    pytest.param(
        PlantConfig(
            thermal_storage_tank_ua_w_per_k=0.006,
            storage_duration_hours=4.0,
        ),
        id="tes-standing-loss",
    ),
    pytest.param(PlantConfig(heat_exchanger_ntu=6.0), id="high-ntu"),
    pytest.param(PlantConfig(intercooler_pressure_drop=0.0, interheater_pressure_drop=0.0), id="no-pressure-drop"),
    pytest.param(PlantConfig(storage_pressure_bar=300.0, compressor_stages=8, expander_stages=8), id="300bar-8stage"),
    pytest.param(PlantConfig(ambient_temperature_c=40.0), id="hot-ambient"),
]


@pytest.mark.parametrize("config", CONFIGURATIONS)
def test_grassmann_balance_closes(config):
    """exergy in = product + destruction + loss, to within a joule.

    This is THE test. It failed before the exhaust-air loss and the cold-tank
    mixing destruction were added: the books were short by up to 36 kJ/kg (4% of
    the input) on a single-stage machine, which meant the destruction table was
    quietly understating where the plant's availability was going.
    """
    result = CAESPlant(config).run()
    residual = result.exergy.balance_residual_j_per_kg_air
    assert abs(residual) < 1.0, (
        f"exergy balance is short by {residual / 1000:.3f} kJ/kg-air - a term is missing. "
        f"in={result.compression_work_input_j_per_kg / 1000:.2f}, "
        f"out={result.expansion_work_output_j_per_kg / 1000:.2f}, "
        f"destroyed={result.exergy.total_destruction_j_per_kg_air / 1000:.2f}, "
        f"lost={result.exergy.total_loss_j_per_kg_air / 1000:.2f} kJ/kg"
    )


@pytest.mark.parametrize("config", CONFIGURATIONS)
def test_no_energy_is_created_in_the_cavern(config):
    """The state the charging train leaves in the cavern is the state discharge starts from.

    Regression: exchange_with_environment used to be hard-wired cool-only for the
    cavern. Whenever the air arrived colder than the rock the step silently
    bypassed itself, yet _discharge still began from state_pt(p_storage, T_ambient)
    - inventing ~21 kJ/kg of enthalpy and inflating the round-trip efficiency.
    """
    result = CAESPlant(config).run()
    jump = result.discharging.inlet.enthalpy_j_per_kg - result.charging.outlet.enthalpy_j_per_kg
    assert abs(jump) < 1e-6, f"{jump / 1000:+.3f} kJ/kg-air appears out of nowhere across the cavern"

    assert result.charging.outlet.pressure_bar == pytest.approx(config.storage_pressure_bar)
    assert result.discharging.inlet.pressure_bar == pytest.approx(config.storage_pressure_bar)


@pytest.mark.parametrize("config", CONFIGURATIONS)
def test_first_law_closes_on_every_component(config):
    """h_out - h_in = q + w, exactly, for every process. See caes.thermodynamics eq (1)."""
    result = CAESPlant(config).run()
    for cycle in (result.charging, result.discharging):
        for process in cycle.processes:
            assert abs(process.first_law_residual_j_per_kg) < 1e-6, f"{cycle.name}/{process.kind}"


@pytest.mark.parametrize("config", CONFIGURATIONS)
def test_second_law_holds_everywhere(config):
    """No component may create exergy, and no efficiency may exceed unity."""
    result = CAESPlant(config).run()
    for cycle in (result.charging, result.discharging):
        for process in cycle.processes:
            assert process.exergy_destruction_j_per_kg >= 0.0, f"{cycle.name}/{process.kind}"
    assert 0.0 < result.round_trip_efficiency < 1.0
    assert 0.0 < result.exergy.total_useful_exergy_efficiency < 1.0


@pytest.mark.parametrize("config", CONFIGURATIONS)
def test_exhaust_loss_is_reported_and_matches_the_exhaust_state(config):
    """The stack loss must equal the physical exergy of the air actually leaving it."""
    result = CAESPlant(config).run()
    expected = air_exergy(
        result.discharging.outlet,
        config.ambient_temperature_k,
        config.ambient_pressure_bar * 1e5,
        "Air",
    )
    reported = result.exergy.loss_j_per_kg_air["exhaust_air"]
    assert reported == pytest.approx(max(0.0, expected), abs=1e-6)
    assert reported > 0.0, "the exhaust is never exactly at the dead state; this must not be zero"


def test_cold_tank_temperature_is_an_optimized_result():
    """A hot ambient makes the closed loop settle ABOVE the discharge inlet:
    the tank temperature is an outcome, not an input."""
    result = CAESPlant(PlantConfig(ambient_temperature_c=25.0)).run()
    assert result.thermal_store.cold_temperature_k > result.discharging.inlet.temperature_k


def test_diabatic_aftercooler_is_finite_ntu_and_never_reaches_ambient():
    """D-CAES coolers used to be idealised to "hit ambient + approach exactly",
    a free infinite-area exchanger the water-side exchangers never got. They are
    now finite counter-flow exchangers against the atmosphere (Cr = 0), so the
    outlet approaches ambient by 1 - exp(-NTU) of the span - and the cavern
    equilibration step always has the last kelvin or two to do."""
    config = PlantConfig(mode=PlantMode.DIABATIC, ambient_heat_exchanger_ntu=3.0)
    result = CAESPlant(config).run()
    coolers = [p for p in result.charging.processes if p.kind == "intercooling"]
    assert coolers, "diabatic charging must cool between stages"
    for cooler in coolers:
        span = cooler.inlet.temperature_k - config.ambient_temperature_k
        gap = cooler.outlet.temperature_k - config.ambient_temperature_k
        assert 0.0 < gap < span
        # Cr = 0 effectiveness, up to the small variable-cp correction.
        assert gap / span == pytest.approx(exp(-3.0), rel=0.1)

    # ...and the explicit final aftercooler does the last kelvins and is followed
    # by the ideal separator used by the moisture controller.
    assert any(p.kind == "aftercooling" for p in result.charging.processes)


def _ambient_heat_split(result):
    """(into the air, out of the air) ambient heat crossing the boundary [J/kg-air].

    A process carrying a ``heat_exchanger`` is water-coupled: its duty stays
    inside the plant and is booked by the two-tank balance instead. Everything
    else that moves heat - the AD coolers, the ambient reheaters, the anti-icing
    trim, the cavern equilibration - exchanges with the atmosphere.
    """
    into_air = out_of_air = 0.0
    for cycle in (result.charging, result.discharging):
        for process in cycle.processes:
            if process.heat_exchanger is not None:
                continue
            heat = process.heat_to_air_j_per_kg
            if heat > 0.0:
                into_air += heat
            else:
                out_of_air += -heat
    return into_air, out_of_air


@pytest.mark.parametrize("config", CONFIGURATIONS)
def test_closed_first_law_boundary_balance(config):
    """The COMPLETE energy balance on the plant boundary, air stream included.

    ``useful_energy_delivery_ratio`` is deliberately NOT this balance: it prices
    only the electricity the plant buys, and every free ambient stream - the
    preheater duty and the energy the air itself hands over when the exhaust
    leaves below intake enthalpy - is excluded from its denominator by design.
    That leaves the closed balance unasserted by any metric, so a term could go
    missing from the energy books without a test noticing. This is the guard.
    The energy Sankey draws exactly this identity.
    """
    result = CAESPlant(config).run()
    ambient_in, ambient_out = _ambient_heat_split(result)
    # Intake and exhaust are both at p0 and the intake is at T0, so this is the
    # net energy the working fluid itself delivers to the control volume.
    air_stream = (
        result.charging.inlet.enthalpy_j_per_kg
        - result.discharging.outlet.enthalpy_j_per_kg
    )
    store = result.thermal_store
    water_rejected = 0.0
    if store is not None:
        water_rejected = (
            store.offtake_heat_j_per_kg_air
            + store.cold_return_heat_rejected_to_ambient_j_per_kg_air
        - store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
            + store.storage_loss_j_per_kg_air
            + store.cold_storage_loss_j_per_kg_air
        )

    inflow = result.compression_work_input_j_per_kg + ambient_in + air_stream
    outflow = result.expansion_work_output_j_per_kg + ambient_out + water_rejected
    assert inflow == pytest.approx(outflow, abs=1.0), (
        f"boundary energy balance is short by {(inflow - outflow) / 1000:.4f} kJ/kg-air. "
        f"W_comp={result.compression_work_input_j_per_kg / 1000:.2f}, "
        f"ambient_in={ambient_in / 1000:.2f}, air_stream={air_stream / 1000:.2f} vs "
        f"W_exp={result.expansion_work_output_j_per_kg / 1000:.2f}, "
        f"ambient_out={ambient_out / 1000:.2f}, water={water_rejected / 1000:.2f}"
    )


def test_delivery_ratio_is_not_bounded_by_one():
    """Documented contract: the one energy metric is a cost ratio and may pass 100%.

    It can do so because E-303 imports ambient heat and because the exhaust can
    leave below intake enthalpy.  Neither contribution is purchased electricity;
    both must nevertheless appear in the first-law balance.  The exergy
    efficiency - which IS the complete accounting - stays below one on the very
    same design.

    See docs/03, "The one energy metric, and what it deliberately excludes".
    """
    config = PlantConfig(
        storage_pressure_bar=200.0,
        compressor_stages=8,
        expander_stages=8,
        heat_exchanger_ntu=100.0,
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        coolant_minimum_temperature_c=-30.0,
    )
    result = CAESPlant(config).run()

    assert result.external_heat_input_j_per_kg > 0.0
    assert result.thermal_store is not None
    assert result.external_heat_input_j_per_kg == pytest.approx(
        result.thermal_store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
    )
    assert result.useful_energy_delivery_ratio > 1.0

    # ...and it is the cold exhaust that pays for it.
    air_stream = (
        result.charging.inlet.enthalpy_j_per_kg
        - result.discharging.outlet.enthalpy_j_per_kg
    )
    assert air_stream > 40_000.0
    assert result.discharging.outlet.temperature_c < -20.0

    # The complete accounting stays bounded.
    assert 0.0 < result.exergy.total_useful_exergy_efficiency < 1.0


@pytest.mark.parametrize("config", CONFIGURATIONS)
def test_water_energy_balance_closes(config):
    """Equation (12): every joule the intercoolers put into the water leaves by
    exactly one of five doors - back into the air, out to the heat network,
    exchanged with ambient at E-303, or leaked out of either tank while it stood.

    Regression: an interheater was chilling the water below the cold tank.
    The duty got booked against that over-cooled water and the return temperature was
    then clamped back up on the way into the tank - quietly manufacturing ~10 kJ/kg-air.
    """
    store = CAESPlant(config).run().thermal_store
    if store is None:
        return   # diabatic: no water loop to balance

    doors = (
        store.delivered_heat_j_per_kg_air
        + store.offtake_heat_j_per_kg_air
        + store.cold_return_heat_rejected_to_ambient_j_per_kg_air
        - store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
        + store.storage_loss_j_per_kg_air
        + store.cold_storage_loss_j_per_kg_air
    )
    gap = store.recovered_heat_j_per_kg_air - doors
    assert abs(gap) < 1.0, (
        f"water energy balance is short by {gap / 1000:.3f} kJ/kg-air. "
        f"recovered={store.recovered_heat_j_per_kg_air / 1000:.2f} vs "
        f"air={store.delivered_heat_j_per_kg_air / 1000:.2f} + "
        f"district={store.offtake_heat_j_per_kg_air / 1000:.2f} + "
        f"cold_return_rejected={store.cold_return_heat_rejected_to_ambient_j_per_kg_air / 1000:.2f} + "
        f"hot_tank_loss={store.storage_loss_j_per_kg_air / 1000:.2f} + "
        f"cold_tank_loss={store.cold_storage_loss_j_per_kg_air / 1000:.2f}"
    )
