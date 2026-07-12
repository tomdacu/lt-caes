"""Finite, energy-balanced sensible-water thermal storage model."""

from __future__ import annotations

from dataclasses import dataclass

from .config import PlantConfig
from .models import Process, State, ThermalStoreSnapshot
from .thermodynamics import heat_to, state_ph


WATER_DENSITY_KG_PER_M3 = 997.0
WATER_CP_J_PER_KGK = 4_180.0


@dataclass
class SensibleWaterStore:
    """A well-mixed water store with a finite usable sensible-energy inventory.

    It intentionally does not claim to model stratification, hydraulic design,
    or transient heat-transfer coefficients.  Those require a different model.
    """

    config: PlantConfig
    temperature_k: float
    recovered_energy_j: float = 0.0
    delivered_energy_j: float = 0.0
    lost_energy_j: float = 0.0

    @classmethod
    def from_config(cls, config: PlantConfig) -> "SensibleWaterStore":
        return cls(config=config, temperature_k=config.water_initial_temperature_k)

    @property
    def heat_capacity_j_per_k(self) -> float:
        return self.config.water_tank_volume_m3 * WATER_DENSITY_KG_PER_M3 * WATER_CP_J_PER_KGK

    @property
    def energy_above_initial_j(self) -> float:
        return max(0.0, (self.temperature_k - self.config.water_initial_temperature_k) * self.heat_capacity_j_per_k)

    def charge(self, recovered_specific_j_per_kg: float) -> None:
        """Add recovered intercooler heat for the configured mass of charged air."""
        energy = max(0.0, recovered_specific_j_per_kg) * self.config.air_mass_kg
        self.temperature_k += energy / self.heat_capacity_j_per_k
        self.recovered_energy_j += energy

    def apply_standing_loss(self) -> None:
        """Apply the explicitly configured loss before the discharge batch."""
        loss = self.energy_above_initial_j * self.config.thermal_store_loss_fraction
        self.temperature_k -= loss / self.heat_capacity_j_per_k
        self.lost_energy_j += loss

    def heat_air(self, inlet: State, pressure_drop: float, fluid: str) -> Process:
        """Heat air subject to hot-side pinch and remaining stored energy."""
        outlet_pressure = inlet.pressure_pa * (1.0 - pressure_drop)
        pinch_target = max(inlet.temperature_k, self.temperature_k - self.config.heat_exchanger_pinch_c)
        ideal = heat_to(inlet, pinch_target, pressure_drop, fluid, note="thermal-store limited")
        requested_j = ideal.heat_to_air_j_per_kg * self.config.air_mass_kg
        available_j = self.energy_above_initial_j
        delivered_j = min(requested_j, available_j)
        if requested_j <= 0:
            return ideal
        h_out = inlet.enthalpy_j_per_kg + delivered_j / self.config.air_mass_kg
        outlet = state_ph(outlet_pressure, h_out, fluid)
        self.temperature_k -= delivered_j / self.heat_capacity_j_per_k
        self.delivered_energy_j += delivered_j
        return Process(
            "interheating",
            inlet,
            outlet,
            heat_to_air_j_per_kg=delivered_j / self.config.air_mass_kg,
            heat_to_store_j_per_kg=-delivered_j / self.config.air_mass_kg,
            note="thermal-store limited",
        )

    def snapshot(self) -> ThermalStoreSnapshot:
        return ThermalStoreSnapshot(
            temperature_k=self.temperature_k,
            energy_above_initial_j=self.energy_above_initial_j,
            recovered_energy_j=self.recovered_energy_j,
            delivered_energy_j=self.delivered_energy_j,
            lost_energy_j=self.lost_energy_j,
        )
