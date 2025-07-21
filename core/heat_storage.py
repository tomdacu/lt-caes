"""
Heat storage system for the CAES plant.

This module provides functions to model and analyze the heat storage system,
which captures heat from intercoolers and uses it to heat air entering the turbine.
"""

import math
from CoolProp.CoolProp import PropsSI



class HeatStorageSystem:
    """
    Heat storage system class for CAES plant.
    
    Manages thermal energy storage using hot water tanks to store heat
    from compression and provide it during expansion.
    """
    
    def __init__(self, config):
        """Initialize heat storage system with plant configuration."""
        self.config = config
        # Initialize tank temperatures to reasonable values
        # Start hot tank at ambient + reasonable offset to avoid cold interheater temperatures
        self.hot_tank_temperature_c = config.T_ambient_C + 50  # Start at 65°C for 15°C ambient
        self.cold_tank_temperature_c = config.T_ambient_C
        self.water_mass_kg = self._calculate_water_mass()
        
    def _calculate_water_mass(self):
        """Calculate water mass from tank dimensions."""
        # Use tank volume from config
        volume = self.config.tank_volume_m3
        water_density = 1000  # kg/m³ for water
        return volume * water_density
    
    def get_intercooler_target_temperature(self):
        """Get target temperature for intercooler outlet in Kelvin."""
        # Target is ambient + heat exchange approach, converted to Kelvin
        return (self.config.T_ambient_C + self.config.heat_exchange_approach_temp) + 273.15
    
    def get_interheater_target_temperature(self):
        """Get target temperature for interheater outlet in Kelvin."""
        # Use stored hot water temperature minus approach temperature, converted to Kelvin
        target_temp_k = (self.hot_tank_temperature_c - self.config.heat_exchange_approach_temp) + 273.15
        # Ensure minimum temperature is reasonable
        min_temp_k = self.config.T_ambient_C + 273.15  # At least ambient temperature
        return max(target_temp_k, min_temp_k)
    
    def calculate_simple_hot_temp(self, charging_results):
        """
        Calculate hot tank temperature based on compression heat recovery.
        
        Args:
            charging_results: Results from compression cycle
        """
        # Simple model: calculate average compression outlet temperature
        compression_states = charging_results.all_states
        if len(compression_states) > 2:
            # Get compression outlet states (every other state starting from index 1)
            compression_outlets = compression_states[1::2]
            
            if compression_outlets:
                # Average outlet temperature
                avg_compression_temp = sum(state.t for state in compression_outlets) / len(compression_outlets)
                
                # Hot tank temperature is compression outlet minus heat exchange approach
                self.hot_tank_temperature_c = avg_compression_temp - 273.15 - self.config.heat_exchange_approach_temp
                
                # Ensure it's not below ambient
                self.hot_tank_temperature_c = max(self.hot_tank_temperature_c, self.config.T_ambient_C)
                
                # Cold tank remains near ambient (simplified)
                self.cold_tank_temperature_c = self.config.T_ambient_C + 2
        
        # Fallback if no compression states
        if not hasattr(self, 'hot_tank_temperature_c') or self.hot_tank_temperature_c <= self.config.T_ambient_C:
            self.hot_tank_temperature_c = self.config.T_ambient_C + 50  # Default hot temperature
            self.cold_tank_temperature_c = self.config.T_ambient_C
