"""Property access and physically constrained component calculations."""

from __future__ import annotations

from CoolProp.CoolProp import PropsSI

from .models import Process, State


def state_pt(pressure_pa: float, temperature_k: float, fluid: str) -> State:
    """Return an equilibrium state fixed by pressure and temperature."""
    return State(
        pressure_pa=pressure_pa,
        temperature_k=temperature_k,
        enthalpy_j_per_kg=PropsSI("H", "P", pressure_pa, "T", temperature_k, fluid),
        entropy_j_per_kgk=PropsSI("S", "P", pressure_pa, "T", temperature_k, fluid),
    )


def state_ph(pressure_pa: float, enthalpy_j_per_kg: float, fluid: str) -> State:
    """Return an equilibrium state fixed by pressure and enthalpy."""
    return State(
        pressure_pa=pressure_pa,
        temperature_k=PropsSI("T", "P", pressure_pa, "H", enthalpy_j_per_kg, fluid),
        enthalpy_j_per_kg=enthalpy_j_per_kg,
        entropy_j_per_kgk=PropsSI("S", "P", pressure_pa, "H", enthalpy_j_per_kg, fluid),
    )


def compress(inlet: State, outlet_pressure_pa: float, efficiency: float, fluid: str) -> Process:
    """Adiabatic compressor using isentropic efficiency.

    Positive work is shaft work supplied to the air.
    """
    if outlet_pressure_pa <= inlet.pressure_pa:
        raise ValueError("a compressor outlet pressure must exceed its inlet pressure")
    h_is = PropsSI("H", "P", outlet_pressure_pa, "S", inlet.entropy_j_per_kgk, fluid)
    h_out = inlet.enthalpy_j_per_kg + (h_is - inlet.enthalpy_j_per_kg) / efficiency
    outlet = state_ph(outlet_pressure_pa, h_out, fluid)
    return Process("compression", inlet, outlet, work_j_per_kg=h_out - inlet.enthalpy_j_per_kg)


def expand(inlet: State, outlet_pressure_pa: float, efficiency: float, fluid: str) -> Process:
    """Adiabatic turbine using isentropic efficiency.

    Negative work is shaft work delivered by the air.
    """
    if outlet_pressure_pa >= inlet.pressure_pa:
        raise ValueError("an expander outlet pressure must be below its inlet pressure")
    h_is = PropsSI("H", "P", outlet_pressure_pa, "S", inlet.entropy_j_per_kgk, fluid)
    h_out = inlet.enthalpy_j_per_kg - efficiency * (inlet.enthalpy_j_per_kg - h_is)
    outlet = state_ph(outlet_pressure_pa, h_out, fluid)
    return Process("expansion", inlet, outlet, work_j_per_kg=h_out - inlet.enthalpy_j_per_kg)


def cool_to(
    inlet: State,
    target_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    recovery_effectiveness: float = 0.0,
) -> Process:
    """Cool an air stream without allowing an intercooler to heat it."""
    outlet_pressure = inlet.pressure_pa * (1.0 - pressure_drop)
    if target_temperature_k >= inlet.temperature_k:
        # A bypassed exchanger still has a pressure loss. Model it as a throttle
        # (h_out = h_in), not as an isothermal process that invents heat.
        outlet = state_ph(outlet_pressure, inlet.enthalpy_j_per_kg, fluid)
        heat_to_air = 0.0
        note = "bypassed"
    else:
        outlet = state_pt(outlet_pressure, target_temperature_k, fluid)
        heat_to_air = outlet.enthalpy_j_per_kg - inlet.enthalpy_j_per_kg
        note = ""
    recovered = -heat_to_air * recovery_effectiveness
    return Process(
        "intercooling",
        inlet,
        outlet,
        heat_to_air_j_per_kg=heat_to_air,
        heat_to_store_j_per_kg=recovered,
        note=note,
    )


def heat_to(
    inlet: State,
    target_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    note: str = "",
) -> Process:
    """Heat an air stream at a pressure loss; target below inlet means bypass."""
    outlet_pressure = inlet.pressure_pa * (1.0 - pressure_drop)
    if target_temperature_k <= inlet.temperature_k:
        outlet = state_ph(outlet_pressure, inlet.enthalpy_j_per_kg, fluid)
        heat_to_air = 0.0
        note = note or "bypassed"
    else:
        outlet = state_pt(outlet_pressure, target_temperature_k, fluid)
        heat_to_air = outlet.enthalpy_j_per_kg - inlet.enthalpy_j_per_kg
    return Process("interheating", inlet, outlet, heat_to_air_j_per_kg=heat_to_air, note=note)
