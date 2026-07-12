"""Result models for normalized energy and exergy analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class State:
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
class HeatExchangerPerformance:
    model: str
    effectiveness: float
    ntu: float | None
    water_air_mass_ratio: float
    water_inlet_temperature_k: float
    water_outlet_temperature_k: float
    duty_j_per_kg_air: float


@dataclass(frozen=True)
class Process:
    kind: str
    inlet: State
    outlet: State
    work_j_per_kg: float = 0.0
    heat_to_air_j_per_kg: float = 0.0
    exergy_destruction_j_per_kg: float = 0.0
    heat_exchanger: HeatExchangerPerformance | None = None
    note: str = ""

    @property
    def first_law_residual_j_per_kg(self) -> float:
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
    def max_first_law_residual_j_per_kg(self) -> float:
        return max((abs(p.first_law_residual_j_per_kg) for p in self.processes), default=0.0)


@dataclass(frozen=True)
class TwoTankSummary:
    cold_temperature_k: float
    hot_temperature_before_loss_k: float
    hot_temperature_available_k: float
    returned_temperature_k: float
    total_water_mass_ratio: float
    recovered_heat_j_per_kg_air: float
    delivered_heat_j_per_kg_air: float
    storage_loss_j_per_kg_air: float
    surplus_heat_j_per_kg_air: float
    surplus_exergy_j_per_kg_air: float
    useful_surplus: bool


@dataclass(frozen=True)
class ExergySummary:
    electrical_efficiency: float
    total_useful_exergy_efficiency: float
    hot_water_exergy_j_per_kg_air: float
    useful_heat_exergy_j_per_kg_air: float
    rejected_heat_exergy_j_per_kg_air: float
    component_destruction_j_per_kg_air: dict[str, float]
    total_destruction_j_per_kg_air: float


@dataclass(frozen=True)
class OptimizationSummary:
    objective: str
    selected_water_air_mass_ratio: float
    objective_value: float
    evaluated_points: int


@dataclass
class PlantResult:
    mode: str
    charging: Cycle
    discharging: Cycle
    thermal_store: TwoTankSummary | None
    exergy: ExergySummary
    selected_water_air_mass_ratio: float | None = None
    optimization: OptimizationSummary | None = None
    external_heat_input_j_per_kg: float = 0.0

    @property
    def compression_work_input_j_per_kg(self) -> float:
        return self.charging.work_j_per_kg

    @property
    def expansion_work_output_j_per_kg(self) -> float:
        return -self.discharging.work_j_per_kg

    @property
    def shaft_work_ratio(self) -> float:
        return self.expansion_work_output_j_per_kg / self.compression_work_input_j_per_kg

    @property
    def round_trip_efficiency(self) -> float:
        return self.shaft_work_ratio
