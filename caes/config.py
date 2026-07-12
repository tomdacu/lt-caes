"""Validated inputs for normalized CAES efficiency and exergy analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class PlantMode(str, Enum):
    """Thermal architecture of the plant."""

    ADIABATIC = "adiabatic"
    DIABATIC = "diabatic"


class HeatExchangerModel(str, Enum):
    """Mutually exclusive heat-exchanger specifications."""

    PINCH = "pinch"
    EFFECTIVENESS = "effectiveness"
    COUNTERFLOW_NTU = "counterflow_ntu"


class WaterFlowMode(str, Enum):
    """How the normalized water/air mass ratio is selected."""

    SPECIFIED_RATIO = "specified_ratio"
    MAX_ELECTRIC_EFFICIENCY = "max_electric_efficiency"
    MAX_HOT_WATER_EXERGY = "max_hot_water_exergy"
    MAX_TOTAL_EXERGY_EFFICIENCY = "max_total_exergy_efficiency"


class ThermalSurplusUse(str, Enum):
    """Destination of hot-water energy remaining after air reheat."""

    REJECT = "reject"
    USEFUL_HEAT = "useful_heat"


@dataclass(frozen=True)
class PlantConfig:
    """Configuration for a cycle normalized to one kilogram of stored air.

    Dormant fields are intentionally accepted so one JSON file can switch
    between models. :mod:`caes.logic` is the single source of truth for which
    fields are active under each selection.
    """

    # Plant and boundary conditions.
    mode: PlantMode = PlantMode.ADIABATIC
    fluid: str = "Air"
    ambient_temperature_c: float = 15.0
    ambient_pressure_bar: float = 1.01325
    storage_pressure_bar: float = 100.0

    # Turbomachinery.
    compressor_stages: int = 4
    expander_stages: int = 4
    compressor_efficiency: float = 0.85
    expander_efficiency: float = 0.85
    intercooler_pressure_drop: float = 0.02
    interheater_pressure_drop: float = 0.02

    # D-CAES ambient heat exchange.
    ambient_heat_exchanger_approach_c: float = 5.0
    use_ambient_reheat: bool = True

    # A-CAES two-tank water loop.
    cold_tank_temperature_c: float = 20.0
    heat_exchanger_model: HeatExchangerModel = HeatExchangerModel.PINCH
    heat_exchanger_pinch_c: float = 5.0
    heat_exchanger_effectiveness: float = 0.85
    heat_exchanger_ntu: float = 3.0
    water_flow_mode: WaterFlowMode = WaterFlowMode.SPECIFIED_RATIO
    water_air_mass_ratio: float = 1.0
    water_air_ratio_search_min: float = 0.05
    water_air_ratio_search_max: float = 10.0
    thermal_storage_loss_fraction: float = 0.0
    thermal_surplus_use: ThermalSurplusUse = ThermalSurplusUse.REJECT

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", PlantMode(self.mode))
        object.__setattr__(self, "heat_exchanger_model", HeatExchangerModel(self.heat_exchanger_model))
        object.__setattr__(self, "water_flow_mode", WaterFlowMode(self.water_flow_mode))
        object.__setattr__(self, "thermal_surplus_use", ThermalSurplusUse(self.thermal_surplus_use))

        if self.storage_pressure_bar <= self.ambient_pressure_bar:
            raise ValueError("storage_pressure_bar must exceed ambient_pressure_bar")
        if self.compressor_stages < 1 or self.expander_stages < 1:
            raise ValueError("stage counts must be at least one")
        for name in ("compressor_efficiency", "expander_efficiency", "heat_exchanger_effectiveness"):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        for name in ("intercooler_pressure_drop", "interheater_pressure_drop", "thermal_storage_loss_fraction"):
            value = getattr(self, name)
            if not 0 <= value < 1:
                raise ValueError(f"{name} must be in [0, 1)")
        for name in (
            "ambient_pressure_bar",
            "storage_pressure_bar",
            "heat_exchanger_ntu",
            "water_air_mass_ratio",
            "water_air_ratio_search_min",
            "water_air_ratio_search_max",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("ambient_heat_exchanger_approach_c", "heat_exchanger_pinch_c"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.water_air_ratio_search_max < self.water_air_ratio_search_min:
            raise ValueError("water_air_ratio_search_max must not be below the minimum")

    @property
    def ambient_temperature_k(self) -> float:
        return self.ambient_temperature_c + 273.15

    @property
    def cold_tank_temperature_k(self) -> float:
        return self.cold_tank_temperature_c + 273.15

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("mode", "heat_exchanger_model", "water_flow_mode", "thermal_surplus_use"):
            data[name] = getattr(self, name).value
        return data
