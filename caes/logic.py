"""Configuration logic shared by the GUI, documentation, and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .config import HeatExchangerModel, PlantConfig, PlantMode, WaterFlowMode


Predicate = Callable[[PlantConfig], bool]


@dataclass(frozen=True)
class FieldRule:
    label: str
    unit: str = ""
    help: str = ""
    active_when: Predicate = lambda config: True
    inactive_reason: str = "Not used by the selected model"


def _adiabatic(c: PlantConfig) -> bool:
    return c.mode is PlantMode.ADIABATIC


def _diabatic(c: PlantConfig) -> bool:
    return c.mode is PlantMode.DIABATIC


def _pinch(c: PlantConfig) -> bool:
    return _adiabatic(c) and c.heat_exchanger_model is HeatExchangerModel.PINCH


def _effectiveness(c: PlantConfig) -> bool:
    return _adiabatic(c) and c.heat_exchanger_model is HeatExchangerModel.EFFECTIVENESS


def _ntu(c: PlantConfig) -> bool:
    return _adiabatic(c) and c.heat_exchanger_model is HeatExchangerModel.COUNTERFLOW_NTU


def _finite_hx(c: PlantConfig) -> bool:
    return _effectiveness(c) or _ntu(c)


def _specified_flow(c: PlantConfig) -> bool:
    return _finite_hx(c) and c.water_flow_mode is WaterFlowMode.SPECIFIED_RATIO


def _optimized_flow(c: PlantConfig) -> bool:
    return _finite_hx(c) and c.water_flow_mode is not WaterFlowMode.SPECIFIED_RATIO


CONFIG_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Plant concept", ("mode", "fluid")),
    ("Boundary conditions", ("ambient_temperature_c", "ambient_pressure_bar", "storage_pressure_bar")),
    (
        "Turbomachinery",
        (
            "compressor_stages", "expander_stages", "compressor_efficiency", "expander_efficiency",
            "intercooler_pressure_drop", "interheater_pressure_drop",
        ),
    ),
    ("D-CAES ambient exchangers", ("ambient_heat_exchanger_approach_c", "use_ambient_reheat")),
    (
        "A-CAES heat exchangers",
        (
            "cold_tank_temperature_c", "heat_exchanger_model", "heat_exchanger_pinch_c",
            "heat_exchanger_effectiveness", "heat_exchanger_ntu",
        ),
    ),
    (
        "Normalized water flow",
        (
            "water_flow_mode", "water_air_mass_ratio", "water_air_ratio_search_min",
            "water_air_ratio_search_max",
        ),
    ),
    ("Thermal surplus", ("thermal_storage_loss_fraction", "thermal_surplus_use")),
)


FIELD_RULES: dict[str, FieldRule] = {
    "mode": FieldRule("Plant mode", help="D-CAES rejects compression heat; A-CAES stores it in water."),
    "fluid": FieldRule("Working fluid"),
    "ambient_temperature_c": FieldRule("Ambient temperature", "°C"),
    "ambient_pressure_bar": FieldRule("Ambient pressure", "bar"),
    "storage_pressure_bar": FieldRule("Storage pressure", "bar"),
    "compressor_stages": FieldRule("Compressor stages"),
    "expander_stages": FieldRule("Expander stages"),
    "compressor_efficiency": FieldRule("Compressor isentropic efficiency", "0-1"),
    "expander_efficiency": FieldRule("Expander isentropic efficiency", "0-1"),
    "intercooler_pressure_drop": FieldRule("Intercooler pressure drop", "fraction"),
    "interheater_pressure_drop": FieldRule("Interheater pressure drop", "fraction"),
    "ambient_heat_exchanger_approach_c": FieldRule("Ambient HX approach", "K", active_when=_diabatic),
    "use_ambient_reheat": FieldRule("Use ambient reheat", active_when=_diabatic),
    "cold_tank_temperature_c": FieldRule("Cold-tank temperature", "°C", active_when=_adiabatic),
    "heat_exchanger_model": FieldRule("HX specification", active_when=_adiabatic),
    "heat_exchanger_pinch_c": FieldRule("Terminal pinch", "K", active_when=_pinch),
    "heat_exchanger_effectiveness": FieldRule("Specified effectiveness", "0-1", active_when=_effectiveness),
    "heat_exchanger_ntu": FieldRule("Counterflow NTU", active_when=_ntu),
    "water_flow_mode": FieldRule("Water-flow selection", active_when=_finite_hx),
    "water_air_mass_ratio": FieldRule("Water/air mass ratio per HX", "kg/kg", active_when=_specified_flow),
    "water_air_ratio_search_min": FieldRule("Ratio search minimum", "kg/kg", active_when=_optimized_flow),
    "water_air_ratio_search_max": FieldRule("Ratio search maximum", "kg/kg", active_when=_optimized_flow),
    "thermal_storage_loss_fraction": FieldRule("Normalized TES loss", "fraction", active_when=_adiabatic),
    "thermal_surplus_use": FieldRule("Surplus heat destination", active_when=_adiabatic),
}


def active_fields(config: PlantConfig) -> set[str]:
    return {name for name, rule in FIELD_RULES.items() if rule.active_when(config)}


def inactive_fields(config: PlantConfig) -> set[str]:
    return set(FIELD_RULES) - active_fields(config)


def active_config(config: PlantConfig) -> dict[str, Any]:
    data = config.to_dict()
    return {name: data[name] for name in active_fields(config)}
