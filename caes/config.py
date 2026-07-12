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

    # Batch and sensible-water thermal storage inputs (A-CAES only).
    air_mass_kg: float = 10_000.0
    water_tank_volume_m3: float = 100.0
    water_initial_temperature_c: float = 15.0
    heat_recovery_effectiveness: float = 0.95
    thermal_store_loss_fraction: float = 0.02

    # D-CAES reheat is external energy, reported separately, never free.
    use_ambient_reheat: bool = True

    def __post_init__(self) -> None:
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
        if self.air_mass_kg <= 0 or self.water_tank_volume_m3 <= 0:
            raise ValueError("air_mass_kg and water_tank_volume_m3 must be positive")

    @property
    def ambient_temperature_k(self) -> float:
        return self.ambient_temperature_c + 273.15

    @property
    def water_initial_temperature_k(self) -> float:
        return self.water_initial_temperature_c + 273.15

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data
