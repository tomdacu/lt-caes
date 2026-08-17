"""Configuration logic shared by the GUI, documentation, and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import HeatOfftake, PlantConfig, PlantMode


Predicate = Callable[[PlantConfig], bool]


@dataclass(frozen=True)
class FieldRule:
    label: str
    unit: str = ""
    help: str = ""
    active_when: Predicate = lambda config: True
    editable_when: Predicate = lambda config: True


def _adiabatic(c: PlantConfig) -> bool:
    return c.mode is PlantMode.ADIABATIC


def _diabatic(c: PlantConfig) -> bool:
    return c.mode is PlantMode.DIABATIC


def _offtake(c: PlantConfig) -> bool:
    """Any external heat off-take at all."""
    return _adiabatic(c) and c.heat_offtake is not HeatOfftake.NONE


CONFIG_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Plant concept", ("mode",)),
    (
        "Boundary conditions",
        (
            "ambient_temperature_c",
            "ambient_pressure_bar",
            "ambient_relative_humidity",
            "storage_pressure_bar",
        ),
    ),
    (
        "Turbomachinery",
        (
            "compressor_stages", "expander_stages", "compressor_efficiency", "expander_efficiency",
            "intercooler_pressure_drop", "interheater_pressure_drop",
        ),
    ),
    (
        "AD-CAES ambient recovery and throttling",
        (
            "ambient_heat_exchanger_ntu",
        ),
    ),
    (
        "LTA/LTHP-CAES coolant heat exchangers",
        (
            "heat_exchanger_ntu",
            "cold_return_cooler_ntu",
            "coolant_maximum_temperature_c",
            "coolant_minimum_temperature_c",
        ),
    ),
    (
        "Coolant-flow optimization",
        ("optimization_objective",),
    ),
    (
        "Thermal store",
        (
            "thermal_storage_tank_ua_w_per_k",
            "storage_duration_hours",
        ),
    ),
    (
        "Heat off-take",
        (
            "heat_offtake",
            "coolant_cascade_groups",
            "heat_user_supply_temperature_c",
            "heat_user_return_temperature_c",
            "heat_user_exchanger_ntu",
        ),
    ),
)


FIELD_RULES: dict[str, FieldRule] = {
    "mode": FieldRule(
        "Plant mode",
        help="AD-CAES (ambient diabatic) rejects compression heat and scavenges "
             "ambient heat on discharge; the adiabatic concepts (LTA-CAES, "
             "LTHP-CAES) store it in a two-tank coolant loop.",
    ),
    "ambient_temperature_c": FieldRule("Ambient temperature", "°C"),
    "ambient_pressure_bar": FieldRule("Ambient pressure", "bar"),
    "ambient_relative_humidity": FieldRule(
        "Ambient relative humidity",
        "(0,1]",
        help="Humidity diagnostic inlet condition. Charge coolers are followed "
             "by ideal liquid separators in the moisture post-processing; this "
             "does not add latent heat to the dry-air energy balance.",
    ),
    "storage_pressure_bar": FieldRule("Storage pressure", "bar"),
    "compressor_stages": FieldRule("Compressor stages"),
    "expander_stages": FieldRule("Expander stages"),
    "compressor_efficiency": FieldRule("Compressor isentropic efficiency", "0-1"),
    "expander_efficiency": FieldRule("Expander isentropic efficiency", "0-1"),
    "intercooler_pressure_drop": FieldRule("Intercooler pressure drop", "fraction"),
    "interheater_pressure_drop": FieldRule("Interheater pressure drop", "fraction"),
    "ambient_heat_exchanger_ntu": FieldRule(
        "Ambient HX NTU", "UA/Cair",
        help="Finite counter-flow sizing of every air/atmosphere exchanger; the "
             "atmosphere is an infinite capacity rate, so effectiveness is 1-exp(-NTU). "
             "AD-CAES only: the adiabatic concepts have no air/ambient exchanger.",
        active_when=_diabatic,
    ),
    "heat_exchanger_ntu": FieldRule(
        "Counterflow NTU", "UA/Cmin",
        help="Common finite-area sizing input for every air/coolant stage HX.",
        active_when=_adiabatic,
    ),
    "coolant_maximum_temperature_c": FieldRule(
        "Coolant maximum temperature",
        "°C",
        help="Direct upper limit for every coolant state. The model no longer "
             "derives a ceiling from circuit pressure or saturation.",
        active_when=_adiabatic,
    ),
    "coolant_minimum_temperature_c": FieldRule(
        "Coolant minimum temperature",
        "°C",
        help="Direct lower limit for every coolant state. A negative value is "
             "allowed for a characterized low-freezing coolant; its real "
             "properties still require vendor validation.",
        active_when=_adiabatic,
    ),
    "cold_return_cooler_ntu": FieldRule(
        "E-303 ambient recovery NTU",
        "UA/Ccoolant",
        help="One heat-only coolant/ambient exchanger. After solving the "
             "interheater returns, the backend places it on the contiguous "
             "cold suffix that maximizes ambient heat pickup, then remixes "
             "that subgroup with the warmer bypass returns.",
        active_when=_adiabatic,
    ),
    "optimization_objective": FieldRule(
        "Optimization objective",
        help="Electrical RTE bypasses the LTHP heat-user exchangers and sends "
             "all available coolant to turbine reheat. Combined delivery "
             "activates heat export and ranks electricity plus useful heat "
             "over charge work; that delivery ratio is not an efficiency.",
        active_when=_adiabatic,
    ),
    "coolant_cascade_groups": FieldRule(
        "Coolant cascade groups",
        "1..expander stages",
        help="Number of interheater branch groups and serial heat-user "
             "exchangers. The hot TES always remains one mixed store. Each "
             "station cools the complete remaining trunk; its group then "
             "bleeds off and only the residual reaches the next station.",
        active_when=_offtake,
    ),
    "thermal_storage_tank_ua_w_per_k": FieldRule(
        "Normalized tank UA",
        "W/K per kg-air",
        help="Combined per-tank conductance on the normalized one-kilogram-air "
             "basis; applied to both the hot and the cold tank.",
        active_when=_adiabatic,
    ),
    "storage_duration_hours": FieldRule(
        "Thermal storage duration",
        "h",
        help="Standing time between charge and discharge; evaluated analytically without timestepping.",
        active_when=_adiabatic,
    ),
    "heat_offtake": FieldRule(
        "External heat off-take",
        help="LTHP-CAES: add E-302 and send the complete feasible upstream "
             "surplus to an external heat user of any kind - a heat network, a "
             "process loop, an absorption chiller. With no user (LTA-CAES) "
             "E-302 is absent and stored heat is used for additional turbine work.",
        active_when=_adiabatic,
    ),
    "heat_user_supply_temperature_c": FieldRule(
        "Heat-user supply temperature", "°C",
        help="What the external user demands. The finite-NTU capacity check "
             "rejects a station that cannot deliver it.",
        active_when=_offtake,
    ),
    "heat_user_return_temperature_c": FieldRule(
        "Heat-user return temperature", "°C",
        help="What the external user gives back. This sets how cold the plant "
             "coolant can leave the exchanger, and hence the duty; the user-side "
             "mass flow then follows from it.",
        active_when=_offtake,
    ),
    "heat_user_exchanger_ntu": FieldRule(
        "Heat-user exchanger NTU", "UA/Cmin",
        help="Performance class of every serial plant/user exchanger. The "
             "physical area is implicitly resized with plant capacity, as for "
             "the air/coolant exchangers.",
        active_when=_offtake,
    ),
}


def active_fields(config: PlantConfig) -> set[str]:
    return {name for name, rule in FIELD_RULES.items() if rule.active_when(config)}


def editable_fields(config: PlantConfig) -> set[str]:
    """Fields that are both relevant and user-editable for this configuration."""
    return {
        name
        for name, rule in FIELD_RULES.items()
        if rule.active_when(config) and rule.editable_when(config)
    }
