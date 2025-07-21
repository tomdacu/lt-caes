"""
Main Plant class for the CAES system.

This module contains the Plant class that orchestrates the entire simulation,
replacing the complex cycle_runner and specifications modules.
"""

import math
from typing import Optional
from CoolProp.CoolProp import PropsSI

from data_models import PlantConfig, ThermodynamicState, CycleResults, PlantResults
from components import Compressor, Expander, Intercooler, Interheater
from core.heat_storage import HeatStorageSystem


class Plant:
    """Main CAES plant class that orchestrates the simulation."""
    
    def __init__(self, config: PlantConfig):
        """
        Initialize the plant with the given configuration.
        
        Args:
            config: Plant configuration parameters
        """
        self.config = config
        
        # Initialize components
        self.compressors = [
            Compressor(config.compressor_isentropic_efficiency) 
            for _ in range(config.compressor_stages)
        ]
        self.expanders = [
            Expander(config.expander_isentropic_efficiency) 
            for _ in range(config.expander_stages)
        ]
        self.intercoolers = [
            Intercooler(config.intercooler_pressure_drop_factor) 
            for _ in range(config.compressor_stages)
        ]
        # Initialize interheaters based on configuration
        # Configuration 1 (No Heat Storage): stages-1 interheaters (after first expansion)
        # Configuration 2 (With Heat Storage): stages interheaters (before every expansion)
        interheater_count = config.expander_stages if config.heat_storage_enabled else config.expander_stages - 1
        self.interheaters = [
            Interheater(config.interheater_pressure_drop_factor) 
            for _ in range(interheater_count)
        ]
        
        # Initialize heat storage system
        self.heat_storage = HeatStorageSystem(config) if config.heat_storage_enabled else None
        
        # Calculate pressure ratios
        self.compression_stage_pressure_ratio = self._calculate_compression_pressure_ratio()
        self.expansion_stage_pressure_ratio = self._calculate_expansion_pressure_ratio()
    
    def _calculate_compression_pressure_ratio(self) -> float:
        """
        Calculate the pressure ratio per compression stage accounting for intercooler losses.
        
        The final pressure after ALL compressors AND intercoolers must equal storage pressure.
        Each compressor must overcome both the design pressure ratio AND compensate 
        for the pressure drop in the following intercooler.
        """
        if self.config.compressor_stages <= 1:
            # Single stage: compressor must reach storage pressure considering final intercooler loss
            final_intercooler_loss = (1 - self.config.intercooler_pressure_drop_factor)
            required_compressor_outlet = self.config.storage_pressure_bar / final_intercooler_loss
            return required_compressor_outlet / self.config.compressor_inlet_p_bar
        
        # Target: reach storage_pressure_bar AFTER final intercooler (IC6)
        target_final_pressure = self.config.storage_pressure_bar
        
        # Each intercooler causes a pressure drop factor (1 - drop_fraction)
        # We have (stages) intercoolers total - ALL compressors are followed by intercoolers
        intercooler_loss_factor = (1 - self.config.intercooler_pressure_drop_factor)
        
        # Working backwards from storage pressure:
        # Final state (storage): storage_pressure_bar
        # Before IC6 (after C6): storage_pressure_bar / loss_factor  
        # Before IC5 (after C5): (storage_pressure_bar / loss_factor) / loss_factor
        # And so on...
        
        # The FINAL compressor (C6) must reach: storage_pressure_bar / loss_factor
        # This accounts for the final intercooler IC6 pressure drop
        pressure_after_final_compressor = target_final_pressure / intercooler_loss_factor
        
        # Total pressure ratio from inlet to final compressor outlet
        total_compressor_pressure_ratio = pressure_after_final_compressor / self.config.compressor_inlet_p_bar
        
        # All previous intercoolers cause additional losses that compressors must overcome
        # C1 through C5 must overcome their intercooler losses too
        previous_intercooler_losses = intercooler_loss_factor ** (self.config.compressor_stages - 1)
        
        # Effective total pressure ratio all compressors must achieve together
        effective_total_ratio = total_compressor_pressure_ratio / previous_intercooler_losses
        
        # Divide equally among all compressor stages
        stage_pressure_ratio = effective_total_ratio ** (1 / self.config.compressor_stages)
        
        print(f"   🔧 Compression pressure calculation:")
        print(f"      📊 Target storage pressure: {target_final_pressure:.2f} bar")
        print(f"      📉 Intercooler loss factor per stage: {intercooler_loss_factor:.3f}")
        print(f"      🎯 Pressure after final compressor: {pressure_after_final_compressor:.2f} bar")
        print(f"      📉 Previous intercooler losses: {previous_intercooler_losses:.3f}")
        print(f"      ⚙️  Effective pressure ratio per stage: {stage_pressure_ratio:.2f}")
        
        return stage_pressure_ratio
    
    def _calculate_expansion_pressure_ratio(self) -> float:
        """
        Calculate the pressure ratio per expansion stage accounting for interheater losses.
        
        Configuration 1: (stages-1) interheaters (after first expansion)
        Configuration 2: (stages) interheaters (before every expansion)
        """
        if self.config.expander_stages <= 1:
            return self.config.expander_outlet_p_bar / self.config.storage_pressure_bar
        
        # Total pressure ratio from storage to outlet (this is < 1, so it's pressure reduction)
        total_pressure_ratio = self.config.expander_outlet_p_bar / self.config.storage_pressure_bar
        
        # Number of interheaters depends on configuration
        if self.config.heat_storage_enabled:
            # Configuration 2: interheater before every expander stage
            num_interheaters = self.config.expander_stages
        else:
            # Configuration 1: interheater after first expander stage
            num_interheaters = self.config.expander_stages - 1
        
        # Each interheater causes a pressure drop
        interheater_loss_factor = (1 - self.config.interheater_pressure_drop_factor)
        total_interheater_losses = interheater_loss_factor ** num_interheaters
        
        # The effective pressure ratio accounting for interheater losses
        effective_total_ratio = total_pressure_ratio / total_interheater_losses
        
        # Divide equally among all expander stages
        stage_pressure_ratio = effective_total_ratio ** (1 / self.config.expander_stages)
        
        print(f"   🔧 Expansion pressure calculation:")
        print(f"      📊 Total pressure ratio: {total_pressure_ratio:.3f}")
        print(f"      🔥 Number of interheaters: {num_interheaters}")
        print(f"      📉 Interheater loss factor per stage: {interheater_loss_factor:.3f}")
        print(f"      📉 Total loss factor: {total_interheater_losses:.3f}")
        print(f"      ⚙️  Effective pressure ratio per stage: {stage_pressure_ratio:.3f}")
        
        return stage_pressure_ratio
    
    def _get_intercooler_target_temperature(self, stage: int) -> float:
        """
        Get the target temperature for an intercooler stage.
        
        Args:
            stage: Stage number (0-indexed)
            
        Returns:
            Target temperature in K
        """
        # The LAST intercooler ALWAYS cools to ambient temperature regardless of configuration
        if stage == self.config.compressor_stages - 1:
            return self.config.t_ambient_c + self.config.zero_c
        
        if self.config.heat_storage_enabled and self.heat_storage:
            # Configuration 2: With heat storage - intermediate intercoolers to cold tank temp
            return self.heat_storage.get_intercooler_target_temperature()
        else:
            # Configuration 1: Without heat storage (ambient air cooling)
            return self.config.t_ambient_c + self.config.delta_t + self.config.zero_c
    
    def _get_interheater_target_temperature(self, stage: int) -> float:
        """
        Get the target temperature for an interheater stage.
        
        Args:
            stage: Stage number (0-indexed)
            
        Returns:
            Target temperature in K
        """
        if self.config.heat_storage_enabled and self.heat_storage:
            # Configuration 2: With heat storage
            return self.heat_storage.get_interheater_target_temperature()
        else:
            # Configuration 1: Without heat storage (ambient air heating)
            # Heat air to ambient - delta_t (external heat source)
            return self.config.t_ambient_c - self.config.delta_t + self.config.zero_c
    
    def run_charging_cycle(self) -> CycleResults:
        """
        Run the compression (charging) cycle.
        
        Returns:
            CycleResults containing all process results and totals
        """
        # Initial state
        current_state = ThermodynamicState(
            p=self.config.compressor_inlet_p_bar * 1e5,  # Convert bar to Pa
            t=self.config.compressor_inlet_t_c + self.config.zero_c,  # Convert C to K
            h=PropsSI('H', 'P', self.config.compressor_inlet_p_bar * 1e5, 'T', 
                     self.config.compressor_inlet_t_c + self.config.zero_c, self.config.fluid),
            s=PropsSI('S', 'P', self.config.compressor_inlet_p_bar * 1e5, 'T', 
                     self.config.compressor_inlet_t_c + self.config.zero_c, self.config.fluid)
        )
        
        results = CycleResults(inlet_state=current_state)
        
        # Run through compressor and intercooler stages
        for stage in range(self.config.compressor_stages):
            # Compression
            if stage == self.config.compressor_stages - 1:
                # Last stage: compress to final pressure
                target_pressure = self.config.compressor_outlet_p_bar * 1e5
            else:
                # Intermediate stage
                target_pressure = current_state.p * self.compression_stage_pressure_ratio
            
            compression_result = self.compressors[stage].run(
                current_state, target_pressure, self.config.fluid
            )
            results.process_results.append(compression_result)
            results.total_work_specific += compression_result.work
            current_state = compression_result.outlet_state
            
            # Intercooling (except after the last compressor)
            if stage < self.config.compressor_stages:
                target_temp = self._get_intercooler_target_temperature(stage)
                
                intercooling_result = self.intercoolers[stage].run(
                    current_state, target_temp, self.config.fluid
                )
                results.process_results.append(intercooling_result)
                current_state = intercooling_result.outlet_state
        
        results.outlet_state = current_state
        
        # Update heat storage if enabled
        if self.config.heat_storage_enabled and self.heat_storage:
            # For simple analysis: calculate hot water temperature from compression results
            self.heat_storage.calculate_simple_hot_temp(results)
        
        return results
    
    def run_discharging_cycle(self) -> CycleResults:
        """
        Run the expansion (discharging) cycle.
        
        Returns:
            CycleResults containing all process results and totals
        """
        # Initial state (from storage)
        current_state = ThermodynamicState(
            p=self.config.storage_pressure_bar * 1e5,  # Convert bar to Pa
            t=self.config.t_ambient_c + self.config.zero_c,  # Storage at ambient temperature
            h=PropsSI('H', 'P', self.config.storage_pressure_bar * 1e5, 'T', 
                     self.config.t_ambient_c + self.config.zero_c, self.config.fluid),
            s=PropsSI('S', 'P', self.config.storage_pressure_bar * 1e5, 'T', 
                     self.config.t_ambient_c + self.config.zero_c, self.config.fluid)
        )
        
        results = CycleResults(inlet_state=current_state)
        
        # Run through expander and interheater stages
        for stage in range(self.config.expander_stages):
            # Interheating logic depends on configuration:
            # Configuration 1 (No Heat Storage): First stage expands directly from ambient T, others get interheated
            # Configuration 2 (With Heat Storage): ALL stages get interheated before expansion
            
            should_interheat = False
            interheater_index = stage
            
            if self.config.heat_storage_enabled:
                # Configuration 2: Interheat before EVERY expander stage (index = stage)
                should_interheat = True
                interheater_index = stage
            else:
                # Configuration 1: Interheat before every stage EXCEPT the first (index = stage-1)
                should_interheat = (stage > 0)
                interheater_index = stage - 1
            
            if should_interheat and interheater_index < len(self.interheaters):
                target_temp = self._get_interheater_target_temperature(interheater_index)
                
                interheating_result = self.interheaters[interheater_index].run(
                    current_state, target_temp, self.config.fluid
                )
                results.process_results.append(interheating_result)
                results.total_heat_added_specific += interheating_result.heat_transfer
                current_state = interheating_result.outlet_state
            
            # Expansion
            if stage == self.config.expander_stages - 1:
                # Last stage: expand to final pressure
                target_pressure = self.config.expander_outlet_p_bar * 1e5
            else:
                # Intermediate stage
                target_pressure = current_state.p * self.expansion_stage_pressure_ratio
            
            expansion_result = self.expanders[stage].run(
                current_state, target_pressure, self.config.fluid
            )
            results.process_results.append(expansion_result)
            results.total_work_specific += expansion_result.work  # Already negative
            current_state = expansion_result.outlet_state
        
        results.outlet_state = current_state
        return results
    
    def run_complete_simulation(self) -> PlantResults:
        """
        Run a complete plant simulation (charging + discharging).
        
        Returns:
            PlantResults containing all simulation results
        """
        # Run charging cycle
        charging_results = self.run_charging_cycle()
        
        # Run discharging cycle
        discharging_results = self.run_discharging_cycle()
        
        # Calculate round-trip efficiency
        if charging_results.total_work_specific > 0:
            efficiency = abs(discharging_results.total_work_specific) / charging_results.total_work_specific
        else:
            efficiency = 0.0
        
        # Prepare results
        plant_results = PlantResults(
            charging_results=charging_results,
            discharging_results=discharging_results,
            round_trip_efficiency=efficiency
        )
        
        # Add heat storage temperatures if enabled
        if self.config.heat_storage_enabled and self.heat_storage:
            plant_results.hot_water_temperature_c = self.heat_storage.hot_tank_temperature_c
            plant_results.cold_water_temperature_c = self.heat_storage.cold_tank_temperature_c
        
        return plant_results
