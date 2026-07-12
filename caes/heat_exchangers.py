"""Normalized counter-current air/water heat-exchanger models."""

from __future__ import annotations

from math import exp

from CoolProp.CoolProp import PropsSI

from .config import HeatExchangerModel
from .models import HeatExchangerPerformance, Process, State
from .thermodynamics import state_ph

WATER_CP_J_PER_KGK = 4_180.0


def counterflow_effectiveness(ntu: float, capacity_ratio: float) -> float:
    if abs(1.0 - capacity_ratio) < 1e-10:
        return ntu / (1.0 + ntu)
    exponential = exp(-ntu * (1.0 - capacity_ratio))
    return (1.0 - exponential) / (1.0 - capacity_ratio * exponential)


def _finite_effectiveness(
    model: HeatExchangerModel,
    specified_effectiveness: float,
    ntu: float,
    c_air: float,
    c_water: float,
) -> tuple[float, float | None]:
    if model is HeatExchangerModel.EFFECTIVENESS:
        return specified_effectiveness, None
    c_min, c_max = min(c_air, c_water), max(c_air, c_water)
    return counterflow_effectiveness(ntu, c_min / c_max), ntu


def cool_air_with_water(
    inlet: State,
    water_inlet_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    model: HeatExchangerModel,
    pinch_k: float,
    specified_effectiveness: float,
    ntu: float,
    water_air_mass_ratio: float | None,
) -> Process:
    """Cool one kg of air and return the required/used water mass ratio."""
    p_out = inlet.pressure_pa * (1.0 - pressure_drop)
    if inlet.temperature_k <= water_inlet_temperature_k:
        outlet = state_ph(p_out, inlet.enthalpy_j_per_kg, fluid)
        return Process("intercooling", inlet, outlet, note="water HX bypassed")

    if model is HeatExchangerModel.PINCH:
        t_air_out = min(inlet.temperature_k, water_inlet_temperature_k + pinch_k)
        t_water_out = max(water_inlet_temperature_k, inlet.temperature_k - pinch_k)
        h_out = PropsSI("H", "P", p_out, "T", t_air_out, fluid)
        duty = max(0.0, inlet.enthalpy_j_per_kg - h_out)
        delta_water = t_water_out - water_inlet_temperature_k
        ratio = duty / (WATER_CP_J_PER_KGK * delta_water) if duty > 0 and delta_water > 0 else 0.0
        effectiveness, used_ntu = 1.0, None
    else:
        if water_air_mass_ratio is None or water_air_mass_ratio <= 0:
            raise ValueError("finite HX models require a positive water/air mass ratio")
        ratio = water_air_mass_ratio
        cp_air = PropsSI("C", "P", inlet.pressure_pa, "T", inlet.temperature_k, fluid)
        c_air, c_water = cp_air, ratio * WATER_CP_J_PER_KGK
        effectiveness, used_ntu = _finite_effectiveness(model, specified_effectiveness, ntu, c_air, c_water)
        duty = effectiveness * min(c_air, c_water) * (inlet.temperature_k - water_inlet_temperature_k)
        h_out = inlet.enthalpy_j_per_kg - duty
        t_water_out = water_inlet_temperature_k + duty / c_water

    outlet = state_ph(p_out, h_out, fluid)
    hx = HeatExchangerPerformance(
        model.value,
        effectiveness,
        used_ntu,
        ratio,
        water_inlet_temperature_k,
        t_water_out,
        duty,
    )
    return Process("intercooling", inlet, outlet, heat_to_air_j_per_kg=-duty, heat_exchanger=hx, note="water to hot tank")


def heat_air_with_water(
    inlet: State,
    water_inlet_temperature_k: float,
    water_air_mass_ratio: float,
    pressure_drop: float,
    fluid: str,
    model: HeatExchangerModel,
    pinch_k: float,
    specified_effectiveness: float,
    ntu: float,
) -> Process:
    """Heat one kg of air using a fixed share of hot-tank water."""
    p_out = inlet.pressure_pa * (1.0 - pressure_drop)
    if water_air_mass_ratio <= 0 or water_inlet_temperature_k <= inlet.temperature_k:
        outlet = state_ph(p_out, inlet.enthalpy_j_per_kg, fluid)
        return Process("interheating", inlet, outlet, note="water HX bypassed")

    cp_air = PropsSI("C", "P", inlet.pressure_pa, "T", inlet.temperature_k, fluid)
    c_air, c_water = cp_air, water_air_mass_ratio * WATER_CP_J_PER_KGK
    if model is HeatExchangerModel.PINCH:
        t_air_limit = max(inlet.temperature_k, water_inlet_temperature_k - pinch_k)
        h_limit = PropsSI("H", "P", p_out, "T", t_air_limit, fluid)
        air_capacity = max(0.0, h_limit - inlet.enthalpy_j_per_kg)
        water_capacity = max(0.0, c_water * (water_inlet_temperature_k - inlet.temperature_k - pinch_k))
        duty = min(air_capacity, water_capacity)
        effectiveness, used_ntu = 1.0, None
    else:
        effectiveness, used_ntu = _finite_effectiveness(model, specified_effectiveness, ntu, c_air, c_water)
        duty = effectiveness * min(c_air, c_water) * (water_inlet_temperature_k - inlet.temperature_k)

    h_out = inlet.enthalpy_j_per_kg + duty
    outlet = state_ph(p_out, h_out, fluid)
    t_water_out = water_inlet_temperature_k - duty / c_water
    hx = HeatExchangerPerformance(
        model.value,
        effectiveness,
        used_ntu,
        water_air_mass_ratio,
        water_inlet_temperature_k,
        t_water_out,
        duty,
    )
    return Process("interheating", inlet, outlet, heat_to_air_j_per_kg=duty, heat_exchanger=hx, note="water to cold tank")
