"""Physical-flow and sensible-water exergy calculations."""

from __future__ import annotations

from math import log

from CoolProp.CoolProp import PropsSI

from .heat_exchangers import WATER_CP_J_PER_KGK
from .models import Process, State


def air_exergy(state: State, ambient_temperature_k: float, ambient_pressure_pa: float, fluid: str) -> float:
    h0 = PropsSI("H", "P", ambient_pressure_pa, "T", ambient_temperature_k, fluid)
    s0 = PropsSI("S", "P", ambient_pressure_pa, "T", ambient_temperature_k, fluid)
    return (state.enthalpy_j_per_kg - h0) - ambient_temperature_k * (state.entropy_j_per_kgk - s0)


def water_exergy(temperature_k: float, ambient_temperature_k: float) -> float:
    ratio = temperature_k / ambient_temperature_k
    return WATER_CP_J_PER_KGK * ((temperature_k - ambient_temperature_k) - ambient_temperature_k * log(ratio))


def process_exergy_destruction(
    process: Process,
    ambient_temperature_k: float,
    ambient_pressure_pa: float,
    fluid: str,
) -> float:
    air_in = air_exergy(process.inlet, ambient_temperature_k, ambient_pressure_pa, fluid)
    air_out = air_exergy(process.outlet, ambient_temperature_k, ambient_pressure_pa, fluid)
    if process.heat_exchanger:
        hx = process.heat_exchanger
        water_in = hx.water_air_mass_ratio * water_exergy(hx.water_inlet_temperature_k, ambient_temperature_k)
        water_out = hx.water_air_mass_ratio * water_exergy(hx.water_outlet_temperature_k, ambient_temperature_k)
        destruction = air_in + water_in - air_out - water_out
    elif process.kind in {"compression", "expansion"}:
        destruction = air_in + process.work_j_per_kg - air_out
    else:
        # Heat exchanged with the dead-state environment carries zero exergy.
        destruction = air_in - air_out
    return max(0.0, destruction)
