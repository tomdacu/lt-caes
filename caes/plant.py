"""Normalized D-CAES and two-tank water LTA-CAES cycle solver."""

from __future__ import annotations

from dataclasses import replace
from math import log10

from .config import HeatExchangerModel, PlantConfig, PlantMode, ThermalSurplusUse, WaterFlowMode
from .exergy import process_exergy_destruction, water_exergy
from .heat_exchangers import WATER_CP_J_PER_KGK, cool_air_with_water, heat_air_with_water
from .models import Cycle, ExergySummary, OptimizationSummary, PlantResult, Process, TwoTankSummary
from .thermodynamics import compress, exchange_with_environment, expand, state_pt


class CAESPlant:
    """Simulate a cycle normalized to one kilogram of charged/discharged air."""

    def __init__(self, config: PlantConfig):
        self.config = config

    @property
    def _p_ambient(self) -> float:
        return self.config.ambient_pressure_bar * 1e5

    @property
    def _p_storage(self) -> float:
        return self.config.storage_pressure_bar * 1e5

    def run(self) -> PlantResult:
        c = self.config
        finite_hx = c.heat_exchanger_model is not HeatExchangerModel.PINCH
        should_optimize = (
            c.mode is PlantMode.ADIABATIC
            and finite_hx
            and c.water_flow_mode is not WaterFlowMode.SPECIFIED_RATIO
        )
        if not should_optimize:
            ratio = c.water_air_mass_ratio if finite_hx else None
            return self._simulate(ratio)

        points = 81
        low, high = log10(c.water_air_ratio_search_min), log10(c.water_air_ratio_search_max)
        candidates = [10 ** (low + i * (high - low) / (points - 1)) for i in range(points)]
        evaluated = [(ratio, self._simulate(ratio)) for ratio in candidates]

        def objective(item: tuple[float, PlantResult]) -> float:
            result = item[1]
            if c.water_flow_mode is WaterFlowMode.MAX_ELECTRIC_EFFICIENCY:
                return result.round_trip_efficiency
            if c.water_flow_mode is WaterFlowMode.MAX_HOT_WATER_EXERGY:
                return result.exergy.hot_water_exergy_j_per_kg_air
            return result.exergy.total_useful_exergy_efficiency

        selected_ratio, result = max(evaluated, key=objective)
        result.optimization = OptimizationSummary(
            c.water_flow_mode.value,
            selected_ratio,
            objective((selected_ratio, result)),
            points,
        )
        result.selected_water_air_mass_ratio = selected_ratio
        return result

    def _compression_ratio(self) -> float:
        c = self.config
        alpha = 1.0 - c.intercooler_pressure_drop
        return (self._p_storage / self._p_ambient) ** (1.0 / c.compressor_stages) / alpha

    def _expansion_ratio(self) -> float:
        c = self.config
        alpha = 1.0 - c.interheater_pressure_drop
        if c.mode is PlantMode.ADIABATIC:
            heaters = c.expander_stages
        else:
            heaters = c.expander_stages - 1 if c.use_ambient_reheat else 0
        return ((self._p_ambient / self._p_storage) / alpha**heaters) ** (1.0 / c.expander_stages)

    def _simulate(self, finite_water_ratio: float | None) -> PlantResult:
        charging, water_returns = self._charge(finite_water_ratio)
        store = self._build_hot_tank(water_returns) if self.config.mode is PlantMode.ADIABATIC else None
        discharging, return_temperatures, external_heat = self._discharge(store)
        charging = self._annotate_exergy(charging)
        discharging = self._annotate_exergy(discharging)
        thermal_store, exergy = self._summarize(charging, discharging, store, return_temperatures)
        selected_ratio = None
        if store and self.config.compressor_stages:
            selected_ratio = store[0] / self.config.compressor_stages
        return PlantResult(
            mode=self.config.mode.value,
            charging=charging,
            discharging=discharging,
            thermal_store=thermal_store,
            exergy=exergy,
            selected_water_air_mass_ratio=selected_ratio,
            external_heat_input_j_per_kg=external_heat,
        )

    def _charge(self, finite_water_ratio: float | None) -> tuple[Cycle, list[tuple[float, float, float]]]:
        c = self.config
        current = state_pt(self._p_ambient, c.ambient_temperature_k, c.fluid)
        cycle = Cycle("charging", current)
        ratio = self._compression_ratio()
        water_returns: list[tuple[float, float, float]] = []

        for stage in range(c.compressor_stages):
            p_out = self._p_storage / (1.0 - c.intercooler_pressure_drop) if stage == c.compressor_stages - 1 else current.pressure_pa * ratio
            compressor = compress(current, p_out, c.compressor_efficiency, c.fluid)
            cycle.processes.append(compressor)
            current = compressor.outlet

            if c.mode is PlantMode.ADIABATIC:
                cooler = cool_air_with_water(
                    current,
                    c.cold_tank_temperature_k,
                    c.intercooler_pressure_drop,
                    c.fluid,
                    c.heat_exchanger_model,
                    c.heat_exchanger_pinch_c,
                    c.heat_exchanger_effectiveness,
                    c.heat_exchanger_ntu,
                    finite_water_ratio,
                )
                if cooler.heat_exchanger and cooler.heat_exchanger.water_air_mass_ratio > 0:
                    hx = cooler.heat_exchanger
                    water_returns.append((hx.water_air_mass_ratio, hx.water_outlet_temperature_k, hx.duty_j_per_kg_air))
            else:
                target = c.ambient_temperature_k if stage == c.compressor_stages - 1 else c.ambient_temperature_k + c.ambient_heat_exchanger_approach_c
                cooler = exchange_with_environment(
                    current,
                    target,
                    c.intercooler_pressure_drop,
                    c.fluid,
                    "intercooling",
                    "compression heat rejected to ambient",
                )
            cycle.processes.append(cooler)
            current = cooler.outlet

        if abs(current.temperature_k - c.ambient_temperature_k) > 1e-8:
            cavern = exchange_with_environment(
                current,
                c.ambient_temperature_k,
                0.0,
                c.fluid,
                "cavern_equilibration",
                "air equilibrates with cavern",
            )
            cycle.processes.append(cavern)
        return cycle, water_returns

    def _build_hot_tank(self, returns: list[tuple[float, float, float]]) -> tuple[float, float, float, float, list[tuple[float, float, float]]]:
        c = self.config
        total_ratio = sum(ratio for ratio, _, _ in returns)
        recovered = sum(duty for _, _, duty in returns)
        if total_ratio <= 0 or recovered <= 0:
            raise ValueError("selected heat-exchanger settings recover no compression heat")
        hot_before_loss = c.cold_tank_temperature_k + recovered / (total_ratio * WATER_CP_J_PER_KGK)
        hot_available = c.cold_tank_temperature_k + (
            hot_before_loss - c.cold_tank_temperature_k
        ) * (1.0 - c.thermal_storage_loss_fraction)
        storage_loss = total_ratio * WATER_CP_J_PER_KGK * (hot_before_loss - hot_available)
        return total_ratio, hot_before_loss, hot_available, storage_loss, returns

    def _discharge(
        self,
        store: tuple[float, float, float, float, list[tuple[float, float, float]]] | None,
    ) -> tuple[Cycle, list[tuple[float, float, float]], float]:
        c = self.config
        current = state_pt(self._p_storage, c.ambient_temperature_k, c.fluid)
        cycle = Cycle("discharging", current)
        pressure_ratio = self._expansion_ratio()
        water_returns: list[tuple[float, float, float]] = []
        external_heat = 0.0
        water_ratio = store[0] / c.expander_stages if store else 0.0
        hot_temperature = store[2] if store else 0.0

        for stage in range(c.expander_stages):
            if c.mode is PlantMode.ADIABATIC:
                heater = heat_air_with_water(
                    current,
                    hot_temperature,
                    water_ratio,
                    c.interheater_pressure_drop,
                    c.fluid,
                    c.heat_exchanger_model,
                    c.heat_exchanger_pinch_c,
                    c.heat_exchanger_effectiveness,
                    c.heat_exchanger_ntu,
                )
                cycle.processes.append(heater)
                current = heater.outlet
                if heater.heat_exchanger:
                    hx = heater.heat_exchanger
                    water_returns.append((hx.water_air_mass_ratio, hx.water_outlet_temperature_k, hx.duty_j_per_kg_air))
                else:
                    water_returns.append((water_ratio, hot_temperature, 0.0))
            elif c.use_ambient_reheat and stage > 0:
                heater = exchange_with_environment(
                    current,
                    c.ambient_temperature_k - c.ambient_heat_exchanger_approach_c,
                    c.interheater_pressure_drop,
                    c.fluid,
                    "interheating",
                    "external ambient heat",
                )
                cycle.processes.append(heater)
                current = heater.outlet
                external_heat += max(0.0, heater.heat_to_air_j_per_kg)

            p_out = self._p_ambient if stage == c.expander_stages - 1 else current.pressure_pa * pressure_ratio
            turbine = expand(current, p_out, c.expander_efficiency, c.fluid)
            cycle.processes.append(turbine)
            current = turbine.outlet
        return cycle, water_returns, external_heat

    def _annotate_exergy(self, cycle: Cycle) -> Cycle:
        c = self.config
        processes = [
            replace(
                process,
                exergy_destruction_j_per_kg=process_exergy_destruction(
                    process, c.ambient_temperature_k, self._p_ambient, c.fluid
                ),
            )
            for process in cycle.processes
        ]
        return Cycle(cycle.name, cycle.inlet, processes)

    def _summarize(
        self,
        charging: Cycle,
        discharging: Cycle,
        store: tuple[float, float, float, float, list[tuple[float, float, float]]] | None,
        water_returns: list[tuple[float, float, float]],
    ) -> tuple[TwoTankSummary | None, ExergySummary]:
        c = self.config
        compression_work = charging.work_j_per_kg
        expansion_work = -discharging.work_j_per_kg
        component: dict[str, float] = {}
        for process in charging.processes + discharging.processes:
            component[process.kind] = component.get(process.kind, 0.0) + process.exergy_destruction_j_per_kg

        if store is None:
            electrical = expansion_work / compression_work
            exergy = ExergySummary(electrical, electrical, 0.0, 0.0, 0.0, component, sum(component.values()))
            return None, exergy

        total_ratio, hot_before, hot_available, storage_loss, charge_returns = store
        cold = c.cold_tank_temperature_k
        recovered = sum(duty for _, _, duty in charge_returns)
        delivered = sum(duty for _, _, duty in water_returns)
        returned_temperature = (
            sum(ratio * temperature for ratio, temperature, _ in water_returns) / total_ratio
            if water_returns
            else hot_available
        )
        returned_temperature = max(cold, returned_temperature)
        surplus = total_ratio * WATER_CP_J_PER_KGK * (returned_temperature - cold)
        surplus_exergy = total_ratio * (water_exergy(returned_temperature, c.ambient_temperature_k) - water_exergy(cold, c.ambient_temperature_k))

        branch_exergy = sum(
            ratio * (water_exergy(temperature, c.ambient_temperature_k) - water_exergy(cold, c.ambient_temperature_k))
            for ratio, temperature, _ in charge_returns
        )
        hot_before_exergy = total_ratio * (
            water_exergy(hot_before, c.ambient_temperature_k) - water_exergy(cold, c.ambient_temperature_k)
        )
        hot_available_exergy = total_ratio * (
            water_exergy(hot_available, c.ambient_temperature_k) - water_exergy(cold, c.ambient_temperature_k)
        )
        component["hot_tank_mixing"] = max(0.0, branch_exergy - hot_before_exergy)
        component["thermal_storage_loss"] = max(0.0, hot_before_exergy - hot_available_exergy)
        useful = c.thermal_surplus_use is ThermalSurplusUse.USEFUL_HEAT
        if not useful:
            component["surplus_heat_rejection"] = max(0.0, surplus_exergy)

        electrical = expansion_work / compression_work
        useful_heat_exergy = surplus_exergy if useful else 0.0
        total_efficiency = (expansion_work + useful_heat_exergy) / compression_work
        thermal = TwoTankSummary(
            cold,
            hot_before,
            hot_available,
            returned_temperature,
            total_ratio,
            recovered,
            delivered,
            storage_loss,
            max(0.0, surplus),
            max(0.0, surplus_exergy),
            useful,
        )
        exergy = ExergySummary(
            electrical,
            total_efficiency,
            hot_available_exergy,
            useful_heat_exergy,
            0.0 if useful else max(0.0, surplus_exergy),
            component,
            sum(component.values()),
        )
        return thermal, exergy
