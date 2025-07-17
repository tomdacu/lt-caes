"""
This module provides functions to model and analyze the energy storage component
of a Compressed Air Energy Storage (CAES) system.
"""

from CoolProp.CoolProp import PropsSI

def storage_analysis(pressure, temperature, volume, fluid):
    """
    Analyzes the storage vessel to determine the mass of stored fluid.

    Args:
        pressure (float): Storage pressure in Pascals.
        temperature (float): Storage temperature in Kelvin.
        volume (float): The volume of the storage vessel in cubic meters.
        fluid (str): The working fluid (e.g., 'Air').

    Returns:
        dict: A dictionary containing the mass of the stored fluid.
    """

    # Density of the fluid at storage conditions
    density = PropsSI('D', 'P', pressure, 'T', temperature, fluid)

    # Mass of the stored fluid
    mass = density * volume

    return {
        "stored_mass": mass
    }
