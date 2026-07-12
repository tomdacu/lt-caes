"""Cycle orchestration for physically bounded D-CAES and A-CAES models."""

from __future__ import annotations

from .config import HeatExchangerModel, PlantConfig, PlantMode
from .models import Cycle, HeatExchangerSummary, PlantResult
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
            heat_exchanger_summary=self._heat_exchanger_summary(),
            external_heat_input_j=external_heat_input_j,
        )

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
