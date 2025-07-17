"""
Main script for the analysis of the CAES (Compressed Air Energy Storage) plant.

This script orchestrates the entire simulation by:
1. Loading the plant configuration from `config.py`.
2. Defining the compression and expansion cycles from `specifications.py`.
3. Executing the thermodynamic calculations for each component in the cycle.
4. Calculating the overall round-trip efficiency of the plant.
5. Visualizing the thermodynamic cycles using `plotting.py`.
6. Performing exergetic analysis using `exergetic_analysis.py`.
"""

import config
import specifications
import plotting
import exergetic_analysis
from CoolProp.CoolProp import PropsSI
import parametric_analysis

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

def main():
    """Main function to run the CAES analysis."""

    if config.ANALYSIS_TYPE == 'normal':
        # --- Compression Cycle ---
        print("--- Running Compression Cycle ---")
        initial_compression_state = {
            'P': config.COMPRESSOR_INLET_P_BAR * 1e5,
            'T': config.COMPRESSOR_INLET_T_C + 273.15,
            'H': PropsSI('H', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
            'S': PropsSI('S', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
        }
        compression_cycle_def = specifications.define_compression_cycle()

        # Find the last intercooler and set its target to ambient temperature
        last_intercooler_index = -1
        for i, component in enumerate(compression_cycle_def):
            if component.get('type') == 'intercooler':
                last_intercooler_index = i
        
        if last_intercooler_index != -1:
            # The parameter for target temperature in heat_exchanger_analysis is 'target_t'
            # Convert temperature to Kelvin for CoolProp
            compression_cycle_def[last_intercooler_index]['params']['target_t'] = config.T_AMBIENT_C + config.ZERO_C

        compression_processes = [p['type'] for p in compression_cycle_def]
        compression_states, compression_work, _ = run_cycle(
            initial_compression_state, compression_cycle_def, config.COMPRESSOR_OUTLET_P_BAR * 1e5
        )
        print(f"Total specific compression work: {compression_work / 1e3:.2f} kJ/kg")

        # --- Expansion Cycle ---
        print("\n--- Running Expansion Cycle ---")
        initial_expansion_state = {
            'P': config.STORAGE_PRESSURE_BAR * 1e5,
            'T': config.T_AMBIENT_C + config.ZERO_C,
            'H': PropsSI('H', 'P', config.STORAGE_PRESSURE_BAR * 1e5, 'T', config.T_AMBIENT_C + config.ZERO_C, config.FLUID),
            'S': PropsSI('S', 'P', config.STORAGE_PRESSURE_BAR * 1e5, 'T', config.T_AMBIENT_C + config.ZERO_C, config.FLUID),
        }
        expansion_cycle_def = specifications.define_expansion_cycle()
        expansion_processes = [p['type'] for p in expansion_cycle_def]
        expansion_states, expansion_work, expansion_heat_added = run_cycle(
            initial_expansion_state, expansion_cycle_def, config.EXPANDER_OUTLET_P_BAR * 1e5
        )
        print(f"Total specific expansion work: {-expansion_work / 1e3:.2f} kJ/kg")
        print(f"Total specific heat added during expansion: {expansion_heat_added / 1e3:.2f} kJ/kg")

        # --- Efficiency Calculation ---
        round_trip_efficiency = -expansion_work / (compression_work) if (compression_work) > 0 else 0
        print(f"\nRound-trip efficiency: {round_trip_efficiency:.2%}")

        # --- Plotting ---
        if config.SHOW_PLOTS:
            print("\n--- Generating Plots ---")
            plotting.plot_thermodynamic_cycles(
                compression_states,
                expansion_states,
                compression_processes,
                expansion_processes,
                config.FLUID
            )

        # --- Exergetic Analysis ---
        if config.SHOW_EXERGY_ANALYSIS:
            print("\n--- Running Exergetic Analysis ---")
            exergetic_analysis.analyze_exergy(
                compression_states,
                expansion_states,
                compression_processes,
                expansion_processes
            )

    elif config.ANALYSIS_TYPE == 'stages':
        parametric_analysis.analyze_stages()
    elif config.ANALYSIS_TYPE == 'delta_t':
        parametric_analysis.analyze_delta_t()
    elif config.ANALYSIS_TYPE == 'efficiency':
        parametric_analysis.analyze_efficiency()
    elif config.ANALYSIS_TYPE == 'pressure_drop':
        parametric_analysis.analyze_pressure_drop()
    elif config.ANALYSIS_TYPE == 'ambient_t':
        parametric_analysis.analyze_ambient_temperature()
    else:
        print(f"Error: Unknown analysis type '{config.ANALYSIS_TYPE}' in config.py")

if __name__ == "__main__":
    main()
