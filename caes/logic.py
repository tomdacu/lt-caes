"""Configuration logic shared by the GUI, documentation, and validation.

:data:`FIELD_RULES` is the single field table: it carries the label, the unit,
the activation predicate and the INPUT GROUP of every ``PlantConfig`` field, so
the GUI form, the CLI's ``--explain-config`` listing and the documentation all
read the same declaration. Adding a field means adding one entry here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import HeatOfftake, PlantConfig, PlantMode


Predicate = Callable[[PlantConfig], bool]


@dataclass(frozen=True)
class FieldRule:
    label: str
    group: str
    unit: str = ""
    help: str = ""
    active_when: Predicate = lambda config: True


def _adiabatic(c: PlantConfig) -> bool:
    return c.mode is PlantMode.ADIABATIC


def _diabatic(c: PlantConfig) -> bool:
    return c.mode is PlantMode.DIABATIC


def _offtake(c: PlantConfig) -> bool:
    """Any external heat off-take at all."""
    return _adiabatic(c) and c.heat_offtake is not HeatOfftake.NONE


# Group names, used by the rules below and by the GUI's form layout.
CONCEPT_GROUP = "Plant concept"
BOUNDARY_GROUP = "Boundary conditions"
MACHINERY_GROUP = "Turbomachinery"
AMBIENT_GROUP = "AD-CAES ambient recovery and throttling"
COOLANT_HX_GROUP = "LTA/LTHP-CAES coolant heat exchangers"
OPTIMIZATION_GROUP = "Coolant-flow optimization"
STORE_GROUP = "Thermal store"
OFFTAKE_GROUP = "Heat off-take"


FIELD_RULES: dict[str, FieldRule] = {
    "mode": FieldRule(
        "Plant mode", CONCEPT_GROUP,
        help="AD-CAES (ambient diabatic) rejects compression heat and scavenges "
             "ambient heat on discharge; the adiabatic concepts (LTA-CAES, "
             "LTHP-CAES) store it in a two-tank coolant loop.",
    ),
    "ambient_temperature_c": FieldRule("Ambient temperature", BOUNDARY_GROUP, "°C"),
    "ambient_pressure_bar": FieldRule("Ambient pressure", BOUNDARY_GROUP, "bar"),
    "ambient_relative_humidity": FieldRule(
        "Ambient relative humidity", BOUNDARY_GROUP,
        "(0,1]",
        help="Humidity diagnostic inlet condition. Charge coolers are followed "
             "by ideal liquid separators in the moisture post-processing; this "
             "does not add latent heat to the dry-air energy balance.",
    ),
    "storage_pressure_bar": FieldRule("Storage pressure", BOUNDARY_GROUP, "bar"),
    "compressor_stages": FieldRule("Compressor stages", MACHINERY_GROUP),
    "expander_stages": FieldRule("Expander stages", MACHINERY_GROUP),
    "compressor_efficiency": FieldRule("Compressor isentropic efficiency", MACHINERY_GROUP, "0-1"),
    "expander_efficiency": FieldRule("Expander isentropic efficiency", MACHINERY_GROUP, "0-1"),
    "intercooler_pressure_drop": FieldRule("Intercooler pressure drop", MACHINERY_GROUP, "fraction"),
    "interheater_pressure_drop": FieldRule("Interheater pressure drop", MACHINERY_GROUP, "fraction"),
    "ambient_heat_exchanger_ntu": FieldRule(
        "Ambient HX NTU", AMBIENT_GROUP, "UA/Cair",
        help="Finite counter-flow sizing of every air/atmosphere exchanger; the "
             "atmosphere is an infinite capacity rate, so effectiveness is 1-exp(-NTU). "
             "AD-CAES only: the adiabatic concepts have no air/ambient exchanger.",
        active_when=_diabatic,
    ),
    "heat_exchanger_ntu": FieldRule(
        "Counterflow NTU", COOLANT_HX_GROUP, "UA/Cmin",
        help="Common finite-area sizing input for every air/coolant stage HX.",
        active_when=_adiabatic,
    ),
    "cold_return_cooler_ntu": FieldRule(
        "E-303 ambient recovery NTU", COOLANT_HX_GROUP,
        "UA/Ccoolant",
        help="One heat-only coolant/ambient exchanger. After solving the "
             "interheater returns, the backend places it on the contiguous "
             "cold suffix that maximizes ambient heat pickup, then remixes "
             "that subgroup with the warmer bypass returns.",
        active_when=_adiabatic,
    ),
    "coolant_maximum_temperature_c": FieldRule(
        "Coolant maximum temperature", COOLANT_HX_GROUP,
        "°C",
        help="Direct upper limit for every coolant state. The model no longer "
             "derives a ceiling from circuit pressure or saturation.",
        active_when=_adiabatic,
    ),
    "coolant_minimum_temperature_c": FieldRule(
        "Coolant minimum temperature", COOLANT_HX_GROUP,
        "°C",
        help="Direct lower limit for every coolant state. A negative value is "
             "allowed for a characterized low-freezing coolant; its real "
             "properties still require vendor validation.",
        active_when=_adiabatic,
    ),
    "optimization_objective": FieldRule(
        "Optimization objective", OPTIMIZATION_GROUP,
        help="Electrical RTE bypasses the LTHP heat-user exchangers and sends "
             "all available coolant to turbine reheat. Combined delivery "
             "activates heat export and ranks electricity plus useful heat "
             "over charge work; that delivery ratio is not an efficiency.",
        active_when=_adiabatic,
    ),
    "thermal_storage_tank_ua_w_per_k": FieldRule(
        "Normalized tank UA", STORE_GROUP,
        "W/K per kg-air",
        help="Combined per-tank conductance on the normalized one-kilogram-air "
             "basis; applied to both the hot and the cold tank.",
        active_when=_adiabatic,
    ),
    "storage_duration_hours": FieldRule(
        "Thermal storage duration", STORE_GROUP,
        "h",
        help="Standing time between charge and discharge; evaluated analytically without timestepping.",
        active_when=_adiabatic,
    ),
    "heat_offtake": FieldRule(
        "External heat off-take", OFFTAKE_GROUP,
        help="LTHP-CAES: add E-302 and send the complete feasible upstream "
             "surplus to an external heat user of any kind - a heat network, a "
             "process loop, an absorption chiller. With no user (LTA-CAES) "
             "E-302 is absent and stored heat is used for additional turbine work.",
        active_when=_adiabatic,
    ),
    "heat_user_supply_temperature_c": FieldRule(
        "Heat-user supply temperature", OFFTAKE_GROUP, "°C",
        help="What the external user demands. The finite-NTU capacity check "
             "rejects a user exchanger that cannot deliver it.",
        active_when=_offtake,
    ),
    "heat_user_return_temperature_c": FieldRule(
        "Heat-user return temperature", OFFTAKE_GROUP, "°C",
        help="What the external user gives back. This sets how cold the plant "
             "coolant can leave the exchanger, and hence the duty; the user-side "
             "mass flow then follows from it.",
        active_when=_offtake,
    ),
    "heat_user_exchanger_ntu": FieldRule(
        "Heat-user exchanger NTU", OFFTAKE_GROUP, "UA/Cmin",
        help="Performance class of the single plant/user exchanger E-302. The "
             "physical area is implicitly resized with plant capacity, as for "
             "the air/coolant exchangers.",
        active_when=_offtake,
    ),
    "extraction_exchanger_ntu": FieldRule(
        "E-304 extraction HX NTU", OFFTAKE_GROUP, "UA/Cmin per zone",
        help="Performance class of EACH zone of the multi-stream extraction "
             "body. The trunk's capacity rate steps down at every bleed, so the "
             "body is solved zone by zone rather than with one whole-body "
             "effectiveness; a single figure would be invalid here.",
        active_when=_offtake,
    ),
}


def grouped_fields() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """``FIELD_RULES`` folded into display groups, in declaration order.

    The form layout, the group order and the membership of every group are all
    read from the one table above, so a field cannot be listed in a group in
    one place and omitted in another.
    """
    groups: dict[str, list[str]] = {}
    for name, rule in FIELD_RULES.items():
        groups.setdefault(rule.group, []).append(name)
    return tuple((group, tuple(names)) for group, names in groups.items())


def active_fields(config: PlantConfig) -> set[str]:
    return {name for name, rule in FIELD_RULES.items() if rule.active_when(config)}
