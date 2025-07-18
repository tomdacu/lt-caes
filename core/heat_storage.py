"""
Heat storage system for the CAES plant.

This module provides functions to model and analyze the heat storage system,
which captures heat from intercoolers and uses it to heat air entering the turbine.
"""

import config
from CoolProp.CoolProp import PropsSI

def calculate_water_mass():
    """
    Calculates the mass of water in the storage tank.
    
    Returns:
        float: Mass of water in kg
    """
    return config.WATER_STORAGE_TANK_VOLUME_M3 * config.WATER_DENSITY_KG_M3

def calculate_heat_recovered_from_intercooler(inlet_t_air, outlet_t_air, fluid):
    """
    Calculates the specific heat recovered from air during intercooling.
    
    Args:
        inlet_t_air (float): Inlet air temperature in Kelvin
        outlet_t_air (float): Outlet air temperature in Kelvin
        fluid (str): Working fluid name
        
    Returns:
        float: Specific heat recovered in J/kg
    """
    h_in = PropsSI('H', 'T', inlet_t_air, 'P', 1e5, fluid)
    h_out = PropsSI('H', 'T', outlet_t_air, 'P', 1e5, fluid)
    return h_in - h_out

def update_water_tank_temperature(heat_added_joules, water_mass_kg, initial_water_t_c, heat_loss_joules_per_step=0.0):
    """
    Updates the water tank temperature based on heat added and losses.
    
    Args:
        heat_added_joules (float): Heat added to water in Joules
        water_mass_kg (float): Mass of water in kg
        initial_water_t_c (float): Initial water temperature in Celsius
        heat_loss_joules_per_step (float): Heat lost from tank in Joules (default: 0.0)
        
    Returns:
        float: New water temperature in Celsius
    """
    # Convert specific heat from kJ/kg·K to J/kg·K
    specific_heat = config.WATER_SPECIFIC_HEAT_KJ_KGK * 1000
    
    # Net heat change considering losses
    net_heat_change = heat_added_joules - heat_loss_joules_per_step
    
    delta_t = net_heat_change / (water_mass_kg * specific_heat)
    return initial_water_t_c + delta_t

def calculate_heat_supplied_to_expander(water_t_c, target_delta_t_c, fluid):
    """
    Calculates the specific heat supplied from water storage to expander inlet air.
    
    Args:
        water_t_c (float): Water temperature in Celsius
        target_delta_t_c (float): Target temperature difference for heating
        fluid (str): Working fluid name
        
    Returns:
        float: Specific heat supplied in J/kg
    """
    # Calculate target air temperature based on water temperature and delta T
    target_air_t_c = water_t_c - target_delta_t_c
    
    # Calculate heat required to heat air from ambient to target temperature
    h_ambient = PropsSI('H', 'T', config.T_AMBIENT_C + 273.15, 'P', 1e5, fluid)
    h_target = PropsSI('H', 'T', target_air_t_c + 273.15, 'P', 1e5, fluid)
    
    return h_target - h_ambient

def get_total_energy_stored_joules(water_t_c, water_mass_kg, reference_t_c=None):
    """
    Calculates the total thermal energy stored in the water tank.
    
    Args:
        water_t_c (float): Water temperature in Celsius
        water_mass_kg (float): Mass of water in kg
        reference_t_c (float): Reference temperature for energy calculation (default: ambient)
        
    Returns:
        float: Total energy stored in Joules
    """
    if reference_t_c is None:
        reference_t_c = config.T_AMBIENT_C
    
    # Convert specific heat from kJ/kg·K to J/kg·K
    specific_heat = config.WATER_SPECIFIC_HEAT_KJ_KGK * 1000
    
    # Calculate energy relative to reference temperature
    delta_t = water_t_c - reference_t_c
    return water_mass_kg * specific_heat * delta_t

def calculate_heat_supplied_to_expander(mass_flow_rate_air, water_t_c, target_delta_t_c, fluid):
    """
    Calculates the heat supplied from water storage to expander inlet air.
    
    Args:
        mass_flow_rate_air (float): Mass flow rate of air in kg/s
        water_t_c (float): Water temperature in Celsius
        target_delta_t_c (float): Target temperature difference for heating
        fluid (str): Working fluid name
        
    Returns:
        float: Heat supplied in Joules
    """
    # Calculate target air temperature based on water temperature and delta T
    target_air_t_c = water_t_c - target_delta_t_c
    
    # Calculate heat required to heat air from ambient to target temperature
    h_ambient = PropsSI('H', 'T', config.T_AMBIENT_C + 273.15, 'P', 1e5, fluid)
    h_target = PropsSI('H', 'T', target_air_t_c + 273.15, 'P', 1e5, fluid)
    
    return mass_flow_rate_air * (h_target - h_ambient)

def calculate_exergy_of_heat_transfer(Q, T_source, T_dead):
    """
    Calculates the exergy of heat transfer.
    
    Args:
        Q (float): Heat transferred in Joules
        T_source (float): Source temperature in Kelvin
        T_dead (float): Dead state temperature in Kelvin
        
    Returns:
        float: Exergy of heat transfer in Joules
    """
    if T_source <= T_dead:
        return 0  # No exergy if source temperature is below dead state
    return Q * (1 - T_dead / T_source)

def calculate_exergy_of_water_storage(water_t_c, water_mass_kg, t_dead):
    """
    Calculates the exergy stored in the water tank.
    
    Args:
        water_t_c (float): Water temperature in Celsius
        water_mass_kg (float): Mass of water in kg
        t_dead (float): Dead state temperature in Kelvin
        
    Returns:
        float: Exergy stored in water in Joules
    """
    # Convert specific heat from kJ/kg·K to J/kg·K
    specific_heat = config.WATER_SPECIFIC_HEAT_KJ_KGK * 1000
    
    # Calculate exergy using the formula: m * c * [(T - T0) - T0 * ln(T/T0)]
    t_water = water_t_c + 273.15
    t0 = t_dead
    
    if t_water <= t0:
        return 0
    
    exergy = water_mass_kg * specific_heat * ((t_water - t0) - t0 * (t_water / t0))
    return exergy
