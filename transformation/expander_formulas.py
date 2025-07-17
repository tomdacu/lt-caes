"""
This module provides functions to model and analyze the expansion stages (turbines)
of a Compressed Air Energy Storage (CAES) system.
"""

from CoolProp.CoolProp import PropsSI

def expander_stage_analysis(
    inlet_p, inlet_t, outlet_p, isentropic_efficiency, fluid
):
    """
    Analyzes a single expander stage, calculating thermodynamic properties,
    work produced, and heat added.

    Args:
        inlet_p (float): Inlet pressure in Pascals.
        inlet_t (float): Inlet temperature in Kelvin.
        outlet_p (float): Outlet pressure in Pascals.
        isentropic_efficiency (float): Isentropic efficiency of the expander.
        fluid (str): The working fluid (e.g., 'Air').

    Returns:
        dict: A dictionary containing the calculated thermodynamic properties
              at the outlet, work produced, and heat added.
    """

    # Inlet state
    inlet_h = PropsSI('H', 'P', inlet_p, 'T', inlet_t, fluid)
    inlet_s = PropsSI('S', 'P', inlet_p, 'T', inlet_t, fluid)

    # Ideal outlet state (isentropic expansion)
    ideal_outlet_s = inlet_s
    ideal_outlet_t = PropsSI('T', 'P', outlet_p, 'S', ideal_outlet_s, fluid)
    ideal_outlet_h = PropsSI('H', 'P', outlet_p, 'T', ideal_outlet_t, fluid)

    # Ideal work
    ideal_work = inlet_h - ideal_outlet_h

    # Actual work
    actual_work = ideal_work * isentropic_efficiency

    # Actual outlet state
    actual_outlet_h = inlet_h - actual_work
    actual_outlet_t = PropsSI('T', 'P', outlet_p, 'H', actual_outlet_h, fluid)
    actual_outlet_s = PropsSI('S', 'P', outlet_p, 'H', actual_outlet_h, fluid)

    # Heat added (from the preceding interheater)
    heat_added = inlet_h - PropsSI('H', 'P', inlet_p, 'T', ideal_outlet_t, fluid)

    return {
        "outlet_p": outlet_p,
        "outlet_t": actual_outlet_t,
        "outlet_h": actual_outlet_h,
        "outlet_s": actual_outlet_s,
        "work_produced": actual_work,
        "heat_added": heat_added,
    }
