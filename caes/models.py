"""Data models shared by the solver, reports, and plots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class State:
    """A thermodynamic state in SI units."""

    pressure_pa: float
    temperature_k: float
    enthalpy_j_per_kg: float
    entropy_j_per_kgk: float

    @property
    def pressure_bar(self) -> float:
        return self.pressure_pa / 1e5

    @property
    def temperature_c(self) -> float:
        return self.temperature_k - 273.15


@dataclass(frozen=True)
class Process:
    """One steady-flow component process, expressed per kg of air."""

    kind: Literal["compression", "expansion", "intercooling", "interheating"]
    inlet: State
    outlet: State
    work_j_per_kg: float = 0.0
    heat_to_air_j_per_kg: float = 0.0
    heat_to_store_j_per_kg: float = 0.0
    note: str = ""

    @property
    def first_law_residual_j_per_kg(self) -> float:
        """Residual for dh = q_to_air + w_to_air (steady-flow, KE/PE neglected)."""
        return (self.outlet.enthalpy_j_per_kg - self.inlet.enthalpy_j_per_kg) - (
            self.heat_to_air_j_per_kg + self.work_j_per_kg
        )


@dataclass
class Cycle:
    name: str
    inlet: State
    processes: list[Process] = field(default_factory=list)

    @property
    def outlet(self) -> State:
        return self.processes[-1].outlet if self.processes else self.inlet

    @property
    def states(self) -> list[State]:
        return [self.inlet, *(process.outlet for process in self.processes)]

    @property
    def work_j_per_kg(self) -> float:
        return sum(process.work_j_per_kg for process in self.processes)

    @property
    def heat_to_air_j_per_kg(self) -> float:
        return sum(process.heat_to_air_j_per_kg for process in self.processes)

    @property
    def max_first_law_residual_j_per_kg(self) -> float:
        return max((abs(p.first_law_residual_j_per_kg) for p in self.processes), default=0.0)


@dataclass(frozen=True)
class ThermalStoreSnapshot:
    temperature_k: float
    energy_above_initial_j: float
    recovered_energy_j: float
    delivered_energy_j: float
    lost_energy_j: float


@dataclass
class PlantResult:
    charging: Cycle
    discharging: Cycle
    thermal_store: ThermalStoreSnapshot | None
    mode: str
    air_mass_kg: float
    external_heat_input_j: float = 0.0

    @property
    def compression_work_input_j(self) -> float:
        return self.charging.work_j_per_kg * self.air_mass_kg

    @property
    def expansion_work_output_j(self) -> float:
        return -self.discharging.work_j_per_kg * self.air_mass_kg

    @property
    def shaft_work_ratio(self) -> float:
        return self.expansion_work_output_j / self.compression_work_input_j

    @property
    def round_trip_efficiency(self) -> float | None:
        """Electrical/shaft RTE for a closed A-CAES cycle only.

        A D-CAES cycle uses external reheat, so its shaft-work ratio is not a
        storage-only round-trip efficiency and is deliberately not labelled RTE.
        """
        return self.shaft_work_ratio if self.mode == "adiabatic" else None
