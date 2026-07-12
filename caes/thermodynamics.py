"""Air-property access and turbomachinery component models."""

from __future__ import annotations

from CoolProp.CoolProp import PropsSI

from .models import Process, State


def state_pt(pressure_pa: float, temperature_k: float, fluid: str) -> State:
    return State(
        pressure_pa,
        temperature_k,
        PropsSI("H", "P", pressure_pa, "T", temperature_k, fluid),
        PropsSI("S", "P", pressure_pa, "T", temperature_k, fluid),
    )


def state_ph(pressure_pa: float, enthalpy_j_per_kg: float, fluid: str) -> State:
    return State(
        pressure_pa,
        PropsSI("T", "P", pressure_pa, "H", enthalpy_j_per_kg, fluid),
        enthalpy_j_per_kg,
        PropsSI("S", "P", pressure_pa, "H", enthalpy_j_per_kg, fluid),
    )


def compress(inlet: State, outlet_pressure_pa: float, efficiency: float, fluid: str) -> Process:
    if outlet_pressure_pa <= inlet.pressure_pa:
        raise ValueError("compressor outlet pressure must exceed inlet pressure")
    h_is = PropsSI("H", "P", outlet_pressure_pa, "S", inlet.entropy_j_per_kgk, fluid)
    h_out = inlet.enthalpy_j_per_kg + (h_is - inlet.enthalpy_j_per_kg) / efficiency
    outlet = state_ph(outlet_pressure_pa, h_out, fluid)
    return Process("compression", inlet, outlet, work_j_per_kg=h_out - inlet.enthalpy_j_per_kg)


def expand(inlet: State, outlet_pressure_pa: float, efficiency: float, fluid: str) -> Process:
    if outlet_pressure_pa >= inlet.pressure_pa:
        raise ValueError("expander outlet pressure must be below inlet pressure")
    h_is = PropsSI("H", "P", outlet_pressure_pa, "S", inlet.entropy_j_per_kgk, fluid)
    h_out = inlet.enthalpy_j_per_kg - efficiency * (inlet.enthalpy_j_per_kg - h_is)
    outlet = state_ph(outlet_pressure_pa, h_out, fluid)
    return Process("expansion", inlet, outlet, work_j_per_kg=h_out - inlet.enthalpy_j_per_kg)


def exchange_with_environment(
    inlet: State,
    target_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    kind: str,
    note: str,
) -> Process:
    """Exchange heat with the ambient boundary, bypassing isenthalpically."""
    p_out = inlet.pressure_pa * (1.0 - pressure_drop)
    cooling = kind in {"intercooling", "cavern_equilibration"}
    active = target_temperature_k < inlet.temperature_k if cooling else target_temperature_k > inlet.temperature_k
    outlet = state_pt(p_out, target_temperature_k, fluid) if active else state_ph(p_out, inlet.enthalpy_j_per_kg, fluid)
    return Process(
        kind,
        inlet,
        outlet,
        heat_to_air_j_per_kg=outlet.enthalpy_j_per_kg - inlet.enthalpy_j_per_kg,
        note=note if active else f"{note}; bypassed",
    )
