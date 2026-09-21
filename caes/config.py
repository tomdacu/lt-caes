"""Validated inputs for normalized CAES efficiency and exergy analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from enum import Enum
import json
from pathlib import Path
from typing import Any
import warnings

from .constants import (
    ABSOLUTE_ZERO_CELSIUS,
    MINIMUM_FROST_CORRELATION_TEMPERATURE_K,
)


class OptimizationObjective(str, Enum):
    """Objective used to optimize the normalized water/air mass ratio.

    LTA-CAES (no heat user) maximizes electrical round-trip efficiency: with no
    external demand, maximum electrical work and maximum useful exergy are the
    same dispatch.  LTAHP-CAES maximizes the combined electricity-plus-heat
    delivery ratio.  Total useful exergy efficiency remains a reported metric,
    but is not a selectable objective: it either coincides with one of these two
    or misclassifies the free ambient heat input.
    """

    MAX_ELECTRIC_EFFICIENCY = "max_electric_efficiency"
    MAX_COMBINED_ENERGY_DELIVERY = "max_combined_energy_delivery"


# Removed objective kept as a compatibility alias when loading old JSON files:
# it coincides with max_electric_efficiency without a heat user and maps to
# max_combined_energy_delivery with district heating.
_LEGACY_EXERGY_OBJECTIVE = "max_total_exergy_efficiency"


class HeatOfftake(str, Enum):
    """Whether an external HEAT USER draws from the store before the turbines.

    This is a heat-and-power plant, not a store with a district-heating bolt-on.
    The off-take is specified by three inputs - the temperature the user wants,
    the temperature it hands back, and its exchanger NTU class - so it
    describes a district-heating network, an industrial process loop, an
    absorption chiller, a greenhouse, or a drying plant equally well. District
    heating is the most likely application, not the model's subject.

    Without an off-take the E-302 taps are absent and every objective converts
    as much stored heat as possible to shaft work. With one, the taps export
    the feasible high-grade fraction and the turbines receive the remaining
    moisture-safe duty, entirely from the coolant loop.
    """

    NONE = "none"
    HEAT_USER = "heat_user"

    @classmethod
    def _missing_(cls, value: object) -> "HeatOfftake | None":
        # ``district_heating`` was the original name, from back when the heat
        # user was assumed to be a network.  Old configurations keep loading.
        if isinstance(value, str) and value == "district_heating":
            return cls.HEAT_USER
        return None


@dataclass(frozen=True)
class PlantConfig:
    """Configuration for a cycle normalized to one kilogram of stored air.

    Dormant fields are intentionally accepted so one JSON file can switch
    between models. :mod:`caes.logic` is the single source of truth for which
    fields are active under each selection.
    """

    # Plant and boundary conditions.
    ambient_temperature_c: float = 15.0
    ambient_pressure_bar: float = 1.01325
    ambient_relative_humidity: float = 0.60
    # Six nominal 2.1 pressure-ratio stages: 2.1**6 = 85.766... bar.
    storage_pressure_bar: float = 85.8

    # Turbomachinery.
    compressor_stages: int = 6
    expander_stages: int = 6
    compressor_efficiency: float = 0.85
    expander_efficiency: float = 0.85
    intercooler_pressure_drop: float = 0.02
    interheater_pressure_drop: float = 0.02
    # A-CAES two-tank coolant loop.  Every joule of turbine reheat comes from
    # stored compression heat; there is no air/ambient exchanger anywhere in
    # this train, and the AH-20x preheaters it used to carry are gone.
    heat_exchanger_ntu: float = 5.0
    # One finite coolant-to-ambient recovery exchanger (E-303). The solver
    # places it on the best contiguous suffix of interheater returns, before
    # that subgroup is mixed with the warmer bypass returns. It is heat-only:
    # a return at or above ambient bypasses it and is never cooled.
    cold_return_cooler_ntu: float = 5.0
    # Direct coolant temperature limits.  The model retains a constant liquid
    # heat capacity internally, but does not infer a temperature limit from
    # any pressure or phase-equilibrium correlation.
    coolant_maximum_temperature_c: float = 200.0
    coolant_minimum_temperature_c: float = -80.0
    optimization_objective: OptimizationObjective = OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY
    # Combined per-tank conductance on the normalized one-kilogram-air basis,
    # applied to BOTH tanks (hot tank standing between charge and discharge,
    # cold tank standing between discharge and charge).
    # A physical plant value is normalized as UA_tank / stored_air_mass.
    thermal_storage_tank_ua_w_per_k: float = 0.0
    storage_duration_hours: float = 4.0

    # Heat-user off-take. IN SERIES: all hot coolant crosses the first user HX;
    # each group then bleeds and only the remainder crosses the next.
    heat_offtake: HeatOfftake = HeatOfftake.HEAT_USER
    heat_user_supply_temperature_c: float = 80.0
    heat_user_return_temperature_c: float = 45.0
    # Installed performance class of the single plant/user exchanger. As for
    # all other HXs, constant NTU means the body is implicitly resized when the
    # plant flow changes.
    heat_user_exchanger_ntu: float = 5.0
    # E-304, the counter-current multi-stream body with staged extractions that
    # replaced the serial user cascade. It is solved zone by zone - one zone per
    # extraction interval - because the trunk's heat-capacity rate steps down at
    # every extraction and a single whole-body effectiveness would be invalid.
    # This NTU is the performance class of EACH zone, so as everywhere else in
    # the model the physical area follows the plant flow instead of being fixed.
    extraction_exchanger_ntu: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "heat_offtake", HeatOfftake(self.heat_offtake))
        objective = self.optimization_objective
        if isinstance(objective, str) and objective == _LEGACY_EXERGY_OBJECTIVE:
            objective = (
                OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY
                if self.heat_offtake is HeatOfftake.HEAT_USER
                else OptimizationObjective.MAX_ELECTRIC_EFFICIENCY
            )
            warnings.warn(
                f"optimization_objective '{_LEGACY_EXERGY_OBJECTIVE}' was "
                f"removed and is mapped to '{objective.value}' for this "
                "configuration; exergy efficiency remains a reported metric",
                DeprecationWarning,
                stacklevel=2,
            )
        object.__setattr__(
            self, "optimization_objective", OptimizationObjective(objective)
        )

        if self.storage_pressure_bar <= self.ambient_pressure_bar:
            raise ValueError("storage_pressure_bar must exceed ambient_pressure_bar")
        if not 0 < self.ambient_relative_humidity <= 1:
            raise ValueError("ambient_relative_humidity must be in (0, 1]")
        if self.compressor_stages < 1 or self.expander_stages < 1:
            raise ValueError("stage counts must be at least one")
        for name in ("compressor_efficiency", "expander_efficiency"):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        for name in ("intercooler_pressure_drop", "interheater_pressure_drop"):
            value = getattr(self, name)
            if not 0 <= value < 1:
                raise ValueError(f"{name} must be in [0, 1)")
        for name in (
            "ambient_pressure_bar",
            "storage_pressure_bar",
            "heat_exchanger_ntu",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.thermal_storage_tank_ua_w_per_k < 0:
            raise ValueError("thermal_storage_tank_ua_w_per_k must be non-negative")
        if self.cold_return_cooler_ntu < 0:
            raise ValueError("cold_return_cooler_ntu must be non-negative")
        if self.storage_duration_hours < 0:
            raise ValueError("storage_duration_hours must be non-negative")
        if self.heat_user_exchanger_ntu <= 0:
            raise ValueError("heat_user_exchanger_ntu must be positive")
        if self.extraction_exchanger_ntu <= 0:
            raise ValueError("extraction_exchanger_ntu must be positive")
        # Domain validity first, then cross-field consistency: a temperature
        # below absolute zero is meaningless regardless of any other field.
        for name in (
            "ambient_temperature_c",
            "heat_user_supply_temperature_c",
            "heat_user_return_temperature_c",
            "coolant_maximum_temperature_c",
            "coolant_minimum_temperature_c",
        ):
            if getattr(self, name) <= ABSOLUTE_ZERO_CELSIUS:
                raise ValueError(f"{name} must be above absolute zero")
        if (
            self.ambient_temperature_k
            < MINIMUM_FROST_CORRELATION_TEMPERATURE_K
        ):
            raise ValueError(
                "ambient_temperature_c is below the validity domain of the "
                "moisture correlations "
                f"({MINIMUM_FROST_CORRELATION_TEMPERATURE_K:.0f} K)"
            )
        # A network cannot return coolant hotter than it supplies it.
        if self.heat_user_return_temperature_c >= self.heat_user_supply_temperature_c:
            raise ValueError(
                "heat_user_return_temperature_c must be below heat_user_supply_temperature_c"
            )
        if self.coolant_maximum_temperature_c <= self.coolant_minimum_temperature_c:
            raise ValueError(
                "coolant_maximum_temperature_c must exceed "
                "coolant_minimum_temperature_c"
            )

    @property
    def ambient_temperature_k(self) -> float:
        return self.ambient_temperature_c + 273.15

    @property
    def heat_user_supply_temperature_k(self) -> float:
        return self.heat_user_supply_temperature_c + 273.15

    @property
    def heat_user_return_temperature_k(self) -> float:
        return self.heat_user_return_temperature_c + 273.15

    @property
    def coolant_maximum_temperature_k(self) -> float:
        return self.coolant_maximum_temperature_c + 273.15

    @property
    def coolant_minimum_temperature_k(self) -> float:
        return self.coolant_minimum_temperature_c + 273.15

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("optimization_objective", "heat_offtake"):
            data[name] = getattr(self, name).value
        return data


# The heat off-take was originally written as if the only possible user were a
# district-heating network.  It is not - the same three numbers describe an
# industrial process loop, an absorption chiller, a dryer.  The keys were
# renamed to say so; the old ones keep loading, because a configuration file is
# a record of an experiment and old records must stay readable.
_LEGACY_FIELD_NAMES = {
    "district_heating_supply_temperature_c": "heat_user_supply_temperature_c",
    "district_heating_return_temperature_c": "heat_user_return_temperature_c",
}

# Inputs that no longer exist. Silently copying an old value into a different
# field would alter the experiment while pretending to migrate it, so every one
# of these is ignored explicitly, with its own reason, and the current default
# is used. A configuration file is a record of an experiment and old records
# must stay readable.
_REMOVED_LEGACY_FIELDS = {
    "district_heating_approach_c": (
        "terminal approach is not an exchanger sizing model; "
        "heat_user_exchanger_ntu keeps its default unless explicitly set"
    ),
    "heat_user_approach_c": (
        "terminal approach is not an exchanger sizing model; "
        "heat_user_exchanger_ntu keeps its default unless explicitly set"
    ),
    "coolant_cascade_groups": (
        "the hot store is always one mixed state and the user side is one "
        "exchanger (E-302) plus one extraction per expansion stage (E-304), so "
        "a grouping count has nothing left to control"
    ),
    "thermal_storage_levels": (
        "the hot store is always one mixed state, so no level count is "
        "configurable"
    ),
    "ambient_heat_exchanger_ntu": (
        "the adiabatic train has no air/ambient exchanger at all: every joule "
        "of turbine reheat comes from the stored coolant, and E-303 is the only "
        "coolant/ambient body"
    ),
}

_LEGACY_FIELD_NAMES.update({
    "coolant_freezing_temperature_c": "coolant_minimum_temperature_c",
})

# The thermal architecture is no longer a configuration axis: this package
# simulates the low-temperature ADIABATIC family only.  A record of an adiabatic
# experiment still loads, because the key no longer selects anything.  A
# diabatic record must NOT be migrated into this plant while pretending to read
# it - that concept has no thermal store at all, so the solver would answer a
# different question than the file asks.
_LEGACY_MODE_KEY = "mode"
_LEGACY_ADIABATIC_MODE = "adiabatic"


def _translate_legacy_plant_mode(data: dict[str, Any]) -> dict[str, Any]:
    """Drop the retired ``mode`` key, refusing a non-adiabatic record."""

    if _LEGACY_MODE_KEY not in data:
        return data
    requested = str(data[_LEGACY_MODE_KEY])
    if requested != _LEGACY_ADIABATIC_MODE:
        raise ValueError(
            f"configuration selects mode '{requested}', which this package does "
            "not simulate: it contains the low-temperature adiabatic family "
            "only (LTA without a heat user, LTAHP with one). The diabatic "
            "concept is kept in the frozen no-combustion-caes archive"
        )
    warnings.warn(
        "configuration field 'mode' was removed: the low-temperature adiabatic "
        "family is the only architecture here, so the key has nothing left to "
        "select",
        DeprecationWarning,
        stacklevel=3,
    )
    return {key: value for key, value in data.items() if key != _LEGACY_MODE_KEY}


def config_from_dict(data: dict[str, Any]) -> PlantConfig:
    """Build a configuration from the JSON-compatible public schema."""
    if not isinstance(data, dict):
        raise ValueError("configuration root must be a JSON object")
    data = _translate_legacy_plant_mode(data)
    translated: dict[str, Any] = {}
    for key, value in data.items():
        if key in _REMOVED_LEGACY_FIELDS:
            warnings.warn(
                f"configuration field '{key}' was removed because "
                f"{_REMOVED_LEGACY_FIELDS[key]}",
                DeprecationWarning,
                stacklevel=2,
            )
            continue
        canonical = _LEGACY_FIELD_NAMES.get(key, key)
        if canonical != key:
            if canonical in data:
                raise ValueError(
                    f"configuration sets both '{key}' and its current name "
                    f"'{canonical}'; keep only one"
                )
            if key == "coolant_freezing_temperature_c":
                reason = (
                    "the coolant loop now uses direct minimum/maximum "
                    "temperature limits"
                )
            else:
                reason = (
                    "the heat off-take describes ANY heat user, not only a "
                    "district-heating network"
                )
            warnings.warn(
                f"configuration field '{key}' was renamed to '{canonical}': {reason}",
                DeprecationWarning,
                stacklevel=2,
            )
        translated[canonical] = value
    allowed = {field.name for field in fields(PlantConfig)}
    unknown = set(translated) - allowed
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(sorted(unknown))}")
    return PlantConfig(**translated)


def load_config(path: str | Path) -> PlantConfig:
    """Load and validate the configuration format shared by GUI and CLI."""
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    return config_from_dict(data)


def save_config(config: PlantConfig, path: str | Path) -> Path:
    """Write the shared configuration format and return its path."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    return output
