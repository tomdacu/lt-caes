"""
Cycle runner utility module.

This module provides the run_cycle function to avoid circular imports
between main.py, parametric_analysis.py, and heat_storage_simulation.py
"""

import config
from CoolProp.CoolProp import PropsSI

def run_cycle(initial_state, cycle_definition, outlet_p):
    """
    Runs a thermodynamic cycle (compression or expansion).

    Args:
        initial_state (dict): The initial thermodynamic state.
        cycle_definition (list): The list of components in the cycle.
        outlet_p (float): The final outlet pressure for the cycle.

    Returns:
        tuple: A tuple containing the list of thermodynamic states, total work, and total heat added.
    """
    thermo_states = [initial_state]
    total_work = 0
    total_heat_added = 0
    current_state = initial_state

    # Determine the effective pressure ratio per stage, accounting for inter-stage pressure drops
    if any(c['type'] == 'compressor' for c in cycle_definition):
        num_stages = config.COMPRESSOR_STAGES
        if num_stages > 1:
            # Calculate the total pressure loss factor from all intercoolers
            total_loss_factor = (1 - config.INTERCOOLER_PRESSURE_DROP_FACTOR) ** (num_stages)
            # Adjust the target pressure ratio to compensate for the losses
            effective_total_pressure_ratio = (outlet_p / initial_state['P']) / total_loss_factor
            stage_pressure_ratio = effective_total_pressure_ratio ** (1 / num_stages)
        else:
            stage_pressure_ratio = outlet_p / initial_state['P']

    elif any(c['type'] == 'expander' for c in cycle_definition):
        num_stages = config.EXPANDER_STAGES
        if num_stages > 1:
            # Calculate the total pressure loss factor from all interheaters
            total_loss_factor = (1 - config.INTERHEATER_PRESSURE_DROP_FACTOR) ** (num_stages - 1)
            # Adjust the target pressure ratio to compensate for the losses
            effective_total_pressure_ratio = (outlet_p / initial_state['P']) / total_loss_factor
            stage_pressure_ratio = effective_total_pressure_ratio ** (1 / num_stages)
        else:
            stage_pressure_ratio = outlet_p / initial_state['P']
    else:
        stage_pressure_ratio = 1

    for i, component in enumerate(cycle_definition):
        inlet_p = current_state['P']
        inlet_t = current_state['T']

        if component["type"] == "compressor" or component["type"] == "expander":
            # Check if this is the last expansion stage
            is_last_expander = (component["type"] == "expander" and 
                                i + 2 >= len(cycle_definition))

            if is_last_expander:
                stage_outlet_p = outlet_p # Ensure final pressure is exactly the target
            else:
                # The outlet pressure for every other stage is the inlet pressure times the stage ratio
                stage_outlet_p = inlet_p * stage_pressure_ratio

            result = component["function"](
                inlet_p, inlet_t, stage_outlet_p, **component["params"], fluid=config.FLUID
            )
            work = result.pop("work_required", 0) or -result.pop("work_produced", 0)
            total_work += work

        else: # Heat exchanger
            result = component["function"](
                inlet_p, inlet_t, **component["params"], fluid=config.FLUID
            )
            heat_transfer = result.get("heat_transfer", 0)
            if heat_transfer > 0:
                total_heat_added += heat_transfer

        current_state = {
            'P': result['outlet_p'],
            'T': result['outlet_t'],
            'H': result['outlet_h'],
            'S': result['outlet_s'],
        }
        thermo_states.append(current_state)

    return thermo_states, total_work, total_heat_added
