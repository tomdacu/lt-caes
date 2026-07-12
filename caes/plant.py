"""Cycle orchestration for physically bounded D-CAES and A-CAES models."""

from __future__ import annotations

from dataclasses import replace

from .config import HeatExchangerModel, PlantConfig, PlantMode, WaterFlowStrategy
from .models import Cycle, HeatExchangerSummary, PlantResult, WaterFlowOptimization
from .thermal_store import SensibleWaterStore
from .thermodynamics import compress, cool_to, expand, heat_to, state_pt


class CAESPlant:
    """Run a charge/discharge batch with explicit thermal-energy accounting.

    The cavern is represented as a fixed-pressure inventory whose air reaches
    ambient temperature before discharge.  This is appropriate for a simple
    performance model, but is not a dynamic cavern simulation.
    """

    def __init__(self, config: PlantConfig):
        self.config = config

    @property
    def _p_ambient(self) -> float:
        return self.config.ambient_pressure_bar * 1e5

    @property
    def _p_storage(self) -> float:
        return self.config.storage_pressure_bar * 1e5

    def _compression_ratio(self) -> float:
        alpha = 1.0 - self.config.intercooler_pressure_drop
        return (self._p_storage / self._p_ambient) ** (1.0 / self.config.compressor_stages) / alpha

    def _expansion_ratio(self) -> float:
        alpha = 1.0 - self.config.interheater_pressure_drop
        heater_count = self.config.expander_stages if self.config.mode is PlantMode.ADIABATIC else self.config.expander_stages - 1
        return ((self._p_ambient / self._p_storage) / alpha**heater_count) ** (1.0 / self.config.expander_stages)

    def run(self) -> PlantResult:
        if self.config.water_flow_strategy is WaterFlowStrategy.OPTIMIZE_THERMAL:
            return self._run_with_optimized_water_flow()
        return self._run_single_design_point()

    def _run_single_design_point(self) -> PlantResult:
        store = SensibleWaterStore.from_config(self.config) if self.config.mode is PlantMode.ADIABATIC else None
        charging = self._charge(store)
        if store:
            store.apply_standing_loss()
        discharging, external_heat_input_j = self._discharge(store)
        return PlantResult(
            charging=charging,
            discharging=discharging,
            thermal_store=store.snapshot() if store else None,
            mode=self.config.mode.value,
            air_mass_kg=self.config.air_mass_kg,
            design_air_mass_flow_kg_s=self.config.air_mass_flow_kg_s,
            heat_exchanger_summary=self._heat_exchanger_summary(),
            external_heat_input_j=external_heat_input_j,
        )

    def _run_with_optimized_water_flow(self) -> PlantResult:
        """Find the minimum water flow that reaches a target recovery fraction.

        With fixed U and area, thermal duty has no finite maximum as water flow
        rises; it approaches an asymptote. This deliberately chooses the least
        water flow that reaches the configured fraction of a high-flow reference.
        A true economic optimum additionally needs hydraulic pressure-drop and
        pump-power correlations, which are outside the present model.
        """
        c = self.config

        def evaluate(water_flow_kg_s: float) -> PlantResult:
            design_config = replace(
                c,
                water_mass_flow_kg_s=water_flow_kg_s,
                water_flow_strategy=WaterFlowStrategy.SPECIFIED,
            )
            return CAESPlant(design_config)._run_single_design_point()

        low_flow = c.water_mass_flow_search_min_kg_s
        high_flow = c.water_mass_flow_search_max_kg_s
        low_result = evaluate(low_flow)
        high_result = evaluate(high_flow)
        reference_energy = high_result.thermal_store.recovered_energy_j if high_result.thermal_store else 0.0
        if reference_energy <= 0:
            raise ValueError("water-flow optimisation found no recoverable thermal energy")
        target_energy = c.water_flow_target_fraction * reference_energy

        if low_result.thermal_store and low_result.thermal_store.recovered_energy_j >= target_energy:
            selected_flow, selected_result = low_flow, low_result
        else:
            lo, hi = low_flow, high_flow
            selected_result = high_result
            for _ in range(48):
                mid = (lo + hi) / 2
                candidate = evaluate(mid)
                recovered = candidate.thermal_store.recovered_energy_j if candidate.thermal_store else 0.0
                if recovered >= target_energy:
                    hi, selected_result = mid, candidate
                else:
                    lo = mid
            selected_flow = hi

        recovered_at_optimum = selected_result.thermal_store.recovered_energy_j if selected_result.thermal_store else 0.0
        selected_result.water_flow_optimization = WaterFlowOptimization(
            optimized_water_mass_flow_kg_s=selected_flow,
            target_fraction=c.water_flow_target_fraction,
            achieved_fraction=recovered_at_optimum / reference_energy,
            recovered_energy_at_optimum_j=recovered_at_optimum,
            recovered_energy_reference_j=reference_energy,
            reference_water_mass_flow_kg_s=high_flow,
        )
        return selected_result

    def _heat_exchanger_summary(self) -> HeatExchangerSummary:
        c = self.config
        if c.heat_exchanger_model is HeatExchangerModel.PINCH:
            return HeatExchangerSummary("pinch", 0, None, None, None, None)
        if c.mode is not PlantMode.ADIABATIC:
            # The finite-UA implementation models air-to-water recovery and
            # reheat. D-CAES ambient exchangers need an ambient-side design.
            return HeatExchangerSummary("counterflow_ntu", 0, None, None, None, None)
        count = (c.compressor_stages - 1) + c.expander_stages
        area = count * c.heat_exchanger_area_m2
        screening_cost = None
        if c.heat_exchanger_reference_cost_eur is not None:
            unit_cost = c.heat_exchanger_reference_cost_eur * (c.heat_exchanger_area_m2 / c.heat_exchanger_reference_area_m2) ** c.heat_exchanger_cost_exponent
            screening_cost = unit_cost * count * c.heat_exchanger_installation_factor
        return HeatExchangerSummary(
            "counterflow_ntu",
            count,
            c.heat_exchanger_area_m2,
            area,
            c.heat_exchanger_area_m2 * c.overall_heat_transfer_coefficient_w_m2k,
            screening_cost,
        )

    def _charge(self, store: SensibleWaterStore | None) -> Cycle:
        c = self.config
        current = state_pt(self._p_ambient, c.ambient_temperature_k, c.fluid)
        cycle = Cycle("charging", current)
        ratio = self._compression_ratio()
        for stage in range(c.compressor_stages):
            # The final compressor outlet compensates exactly for aftercooler loss.
            p_out = self._p_storage / (1.0 - c.intercooler_pressure_drop) if stage == c.compressor_stages - 1 else current.pressure_pa * ratio
            compression = compress(current, p_out, c.compressor_efficiency, c.fluid)
            cycle.processes.append(compression)
            current = compression.outlet

            if stage == c.compressor_stages - 1:
                # The cavern inventory is assumed to equilibrate with the rock at
                # ambient temperature. A hot, well-mixed water store cannot in
                # general provide that final cooling, so this residual heat is
                # rejected to the ambient sink and is not counted as recovered.
                intercooler = cool_to(current, c.ambient_temperature_k, c.intercooler_pressure_drop, c.fluid)
            elif store:
                intercooler = store.cool_air(current, c.intercooler_pressure_drop, c.fluid)
            else:
                # D-CAES rejects heat only to ambient; no artificial heating occurs.
                intercooler = cool_to(current, c.ambient_temperature_k + c.heat_exchanger_pinch_c, c.intercooler_pressure_drop, c.fluid)
            cycle.processes.append(intercooler)
            current = intercooler.outlet

        # At this point the aftercooler outlet is the fixed-pressure cavern state.
        # It is physically required to be near ambient before a long storage dwell.
        return cycle

    def _discharge(self, store: SensibleWaterStore | None) -> tuple[Cycle, float]:
        c = self.config
        current = state_pt(self._p_storage, c.ambient_temperature_k, c.fluid)
        cycle = Cycle("discharging", current)
        ratio = self._expansion_ratio()
        external_heat_j = 0.0
        for stage in range(c.expander_stages):
            # A-CAES reheats before every expansion. D-CAES may use externally
            # supplied ambient heat only between stages; its energy is reported.
            should_heat = c.mode is PlantMode.ADIABATIC or (c.use_ambient_reheat and stage > 0)
            if should_heat:
                if store:
                    heater = store.heat_air(current, c.interheater_pressure_drop, c.fluid)
                else:
                    source_limited_target = c.ambient_temperature_k - c.heat_exchanger_pinch_c
                    heater = heat_to(current, source_limited_target, c.interheater_pressure_drop, c.fluid, note="external ambient heat")
                    external_heat_j += heater.heat_to_air_j_per_kg * c.air_mass_kg
                cycle.processes.append(heater)
                current = heater.outlet

            p_out = self._p_ambient if stage == c.expander_stages - 1 else current.pressure_pa * ratio
            turbine = expand(current, p_out, c.expander_efficiency, c.fluid)
            cycle.processes.append(turbine)
            current = turbine.outlet
        return cycle, external_heat_j
