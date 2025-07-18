"""
Heat transfer losses for the water storage tank.

This module calculates heat losses from the water storage tank due to conduction,
convection, and radiation. These losses are used in the time-evolution analysis
of the heat storage system.
"""

import config
import math

def calculate_tank_surface_area(height, diameter):
    """
    Calculates the total surface area of a cylindrical tank.
    
    Args:
        height (float): Tank height in meters
        diameter (float): Tank diameter in meters
        
    Returns:
        float: Total surface area in m²
    """
    radius = diameter / 2.0
    # Surface area = 2πr² (top and bottom) + 2πrh (side)
    return 2 * math.pi * radius**2 + 2 * math.pi * radius * height

def calculate_conduction_loss(surface_area, insulation_thickness, insulation_k, delta_t):
    """
    Calculates heat loss through conduction.
    
    Args:
        surface_area (float): Tank surface area in m²
        insulation_thickness (float): Insulation thickness in m
        insulation_k (float): Thermal conductivity of insulation in W/m·K
        delta_t (float): Temperature difference between water and ambient in K
        
    Returns:
        float: Heat loss rate in Watts
    """
    if insulation_thickness <= 0:
        return 0.0
    return (insulation_k * surface_area * delta_t) / insulation_thickness

def calculate_convection_loss(surface_area, h_conv, delta_t):
    """
    Calculates heat loss through free convection.
    
    Args:
        surface_area (float): Tank surface area in m²
        h_conv (float): Convection heat transfer coefficient in W/m²·K
        delta_t (float): Temperature difference between surface and ambient in K
        
    Returns:
        float: Heat loss rate in Watts
    """
    return h_conv * surface_area * delta_t

def calculate_radiation_loss(surface_area, emissivity, T_surface_K, T_ambient_K):
    """
    Calculates heat loss through radiation.
    
    Args:
        surface_area (float): Tank surface area in m²
        emissivity (float): Surface emissivity (0-1)
        T_surface_K (float): Surface temperature in Kelvin
        T_ambient_K (float): Ambient temperature in Kelvin
        
    Returns:
        float: Heat loss rate in Watts
    """
    # Stefan-Boltzmann constant
    sigma = 5.67e-8  # W/m²·K⁴
    return emissivity * surface_area * sigma * (T_surface_K**4 - T_ambient_K**4)

def calculate_total_heat_loss_rate(water_t_c, ambient_t_c):
    """
    Calculates the total heat loss rate from the water storage tank.
    
    Args:
        water_t_c (float): Water temperature in Celsius
        ambient_t_c (float): Ambient temperature in Celsius
        
    Returns:
        float: Total heat loss rate in Watts
    """
    # Convert temperatures to Kelvin
    T_water_K = water_t_c + 273.15
    T_ambient_K = ambient_t_c + 273.15
    
    # Calculate tank surface area
    surface_area = calculate_tank_surface_area(config.TANK_HEIGHT_M, config.TANK_DIAMETER_M)
    
    # Calculate temperature difference
    delta_t = T_water_K - T_ambient_K
    
    # Calculate individual losses
    conduction_loss = calculate_conduction_loss(
        surface_area,
        config.INSULATION_THICKNESS_M,
        config.INSULATION_THERMAL_CONDUCTIVITY_WMK,
        delta_t
    )
    
    convection_loss = calculate_convection_loss(
        surface_area,
        config.CONVECTION_HEAT_TRANSFER_COEFFICIENT_WM2K,
        delta_t
    )
    
    radiation_loss = calculate_radiation_loss(
        surface_area,
        config.TANK_EMISSIVITY,
        T_water_K,
        T_ambient_K
    )
    
    # Return total losses
    return conduction_loss + convection_loss + radiation_loss

def get_tank_parameters():
    """
    Returns a dictionary with tank parameters for easy access.
    
    Returns:
        dict: Tank parameters including geometry and material properties
    """
    return {
        'height': config.TANK_HEIGHT_M,
        'diameter': config.TANK_DIAMETER_M,
        'volume': config.WATER_STORAGE_TANK_VOLUME_M3,
        'insulation_thickness': config.INSULATION_THICKNESS_M,
        'insulation_k': config.INSULATION_THERMAL_CONDUCTIVITY_WMK,
        'emissivity': config.TANK_EMISSIVITY,
        'h_conv': config.CONVECTION_HEAT_TRANSFER_COEFFICIENT_WM2K
    }
