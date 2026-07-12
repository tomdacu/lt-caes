"""Validated configuration for a batch CAES cycle.

The model represents a fixed mass of air charged to and discharged from a
constant-pressure store.  It is a cycle-performance model, not a transient
cavern-flow model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class PlantMode(str, Enum):
    """Thermal architecture of the CAES plant."""

    ADIABATIC = "adiabatic"
    DIABATIC = "diabatic"


class HeatExchangerModel(str, Enum):
    """Level of detail used for air/water heat exchangers."""

    PINCH = "pinch"
    COUNTERFLOW_NTU = "counterflow_ntu"


class WaterFlowStrategy(str, Enum):
    """How the water-side mass flow is selected for finite-area A-CAES HXs."""

    SPECIFIED = "specified"
    OPTIMIZE_THERMAL = "optimize_thermal"


@dataclass(frozen=True)
class PlantConfig:
    """Inputs for one charge/discharge batch.

    ``air_mass_kg`` is essential for a finite thermal store: a water-tank
    volume alone cannot determine how much compression heat it receives.
    """

    mode: PlantMode = PlantMode.ADIABATIC
    fluid: str = "Air"
    ambient_temperature_c: float = 15.0
    ambient_pressure_bar: float = 1.01325
    storage_pressure_bar: float = 150.0
    compressor_stages: int = 4
    expander_stages: int = 4
    compressor_efficiency: float = 0.85
    expander_efficiency: float = 0.85
    intercooler_pressure_drop: float = 0.02
    interheater_pressure_drop: float = 0.02
    heat_exchanger_pinch_c: float = 5.0
    heat_exchanger_model: HeatExchangerModel = HeatExchangerModel.PINCH

    # Finite-area counter-current exchanger inputs. ``heat_transfer_coefficient``
    # is U, the effective overall coefficient—not an individual film h.
    heat_exchanger_area_m2: float = 100.0
    overall_heat_transfer_coefficient_w_m2k: float = 100.0
    air_mass_flow_kg_s: float = 5.0
    water_mass_flow_kg_s: float = 20.0
    water_flow_strategy: WaterFlowStrategy = WaterFlowStrategy.SPECIFIED
    water_flow_target_fraction: float = 0.95
    water_mass_flow_search_min_kg_s: float = 0.1
    water_mass_flow_search_max_kg_s: float = 1_000.0

    # Batch and sensible-water thermal storage inputs (A-CAES only).
    air_mass_kg: float = 10_000.0
    water_tank_volume_m3: float = 100.0
    water_initial_temperature_c: float = 15.0
    heat_recovery_effectiveness: float = 0.95
    thermal_store_loss_fraction: float = 0.02

    # Optional, user-supplied screening correlation. No universal exchanger
    # price is assumed: omitted reference cost means no monetary estimate.
    heat_exchanger_reference_area_m2: float = 100.0
    heat_exchanger_reference_cost_eur: float | None = None
    heat_exchanger_cost_exponent: float = 0.65
    heat_exchanger_installation_factor: float = 1.0

    # D-CAES reheat is external energy, reported separately, never free.
    use_ambient_reheat: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", PlantMode(self.mode))
        object.__setattr__(self, "heat_exchanger_model", HeatExchangerModel(self.heat_exchanger_model))
        object.__setattr__(self, "water_flow_strategy", WaterFlowStrategy(self.water_flow_strategy))
        if self.storage_pressure_bar <= self.ambient_pressure_bar:
            raise ValueError("storage_pressure_bar must exceed ambient_pressure_bar")
        if self.compressor_stages < 1 or self.expander_stages < 1:
            raise ValueError("stage counts must be at least one")
        for name in ("compressor_efficiency", "expander_efficiency", "heat_recovery_effectiveness"):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        for name in ("intercooler_pressure_drop", "interheater_pressure_drop", "thermal_store_loss_fraction"):
            value = getattr(self, name)
            if not 0 <= value < 1:
                raise ValueError(f"{name} must be in [0, 1)")
        if self.heat_exchanger_pinch_c < 0:
            raise ValueError("heat_exchanger_pinch_c must be non-negative")
        for name in (
            "air_mass_kg", "water_tank_volume_m3", "heat_exchanger_area_m2",
            "overall_heat_transfer_coefficient_w_m2k", "air_mass_flow_kg_s",
            "water_mass_flow_kg_s", "heat_exchanger_reference_area_m2",
            "heat_exchanger_cost_exponent", "heat_exchanger_installation_factor",
            "water_mass_flow_search_min_kg_s", "water_mass_flow_search_max_kg_s",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.heat_exchanger_reference_cost_eur is not None and self.heat_exchanger_reference_cost_eur <= 0:
            raise ValueError("heat_exchanger_reference_cost_eur must be positive when supplied")
        if not 0 < self.water_flow_target_fraction <= 1:
            raise ValueError("water_flow_target_fraction must be in (0, 1]")
        if self.water_mass_flow_search_max_kg_s < self.water_mass_flow_search_min_kg_s:
            raise ValueError("water_mass_flow_search_max_kg_s must not be below the search minimum")
        if self.water_flow_strategy is WaterFlowStrategy.OPTIMIZE_THERMAL:
            if self.mode is not PlantMode.ADIABATIC or self.heat_exchanger_model is not HeatExchangerModel.COUNTERFLOW_NTU:
                raise ValueError("optimize_thermal requires adiabatic mode and counterflow_ntu heat exchangers")

    @property
    def ambient_temperature_k(self) -> float:
        return self.ambient_temperature_c + 273.15

    @property
    def water_initial_temperature_k(self) -> float:
        return self.water_initial_temperature_c + 273.15

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        data["heat_exchanger_model"] = self.heat_exchanger_model.value
        data["water_flow_strategy"] = self.water_flow_strategy.value
        return data
