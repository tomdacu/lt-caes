"""
This module provides functions to model and analyze heat exchangers (intercoolers and interheaters)
in a Compressed Air Energy Storage (CAES) system.
"""

from CoolProp.CoolProp import PropsSI

def heat_exchanger_analysis(
    inlet_p, inlet_t, target_t, pressure_drop_factor, fluid
):
    """
    Analyzes a heat exchanger, calculating the outlet state and heat transfer.

    Args:
        inlet_p (float): Inlet pressure in Pascals.
        inlet_t (float): Inlet temperature in Kelvin.
        target_t (float): The target outlet temperature in Kelvin.
        pressure_drop_factor (float): Pressure drop as a fraction of inlet pressure.
        fluid (str): The working fluid (e.g., 'Air').

    Returns:
        dict: A dictionary containing the outlet state and heat transfer.
    """

    # Inlet state
    inlet_h = PropsSI('H', 'P', inlet_p, 'T', inlet_t, fluid)

    # Outlet pressure
    outlet_p = inlet_p * (1 - pressure_drop_factor)

    # Outlet state
    outlet_h = PropsSI('H', 'P', outlet_p, 'T', target_t, fluid)
    outlet_s = PropsSI('S', 'P', outlet_p, 'T', target_t, fluid)

    # Heat transfer
    heat_transfer = outlet_h - inlet_h

    return {
        "outlet_p": outlet_p,
        "outlet_t": target_t,
        "outlet_h": outlet_h,
        "outlet_s": outlet_s,
        "heat_transfer": heat_transfer,
    }
