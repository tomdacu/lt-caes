"""
Main script for the CAES (Compressed Air Energy Storage) plant analysis.

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
from analysis import exergetic_analysis, parametric_analysis
from simulation.heat_storage_simulation import run_heat_storage_time_analysis
from utils.cycle_runner import run_cycle
from CoolProp.CoolProp import PropsSI


def run_normal_analysis():
    """Runs the normal CAES analysis without heat storage."""
    # --- Compression Cycle ---
    print("--- Running Compression Cycle ---")
    initial_compression_state = {
        'P': config.COMPRESSOR_INLET_P_BAR * 1e5,
        'T': config.COMPRESSOR_INLET_T_C + 273.15,
        'H': PropsSI('H', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
        'S': PropsSI('S', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
    }
    compression_cycle_def = specifications.define_compression_cycle()
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


def main():
    """Main function to run the CAES analysis."""
    
    if config.ANALYSIS_TYPE == 'normal':
        run_normal_analysis()
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
    elif config.ANALYSIS_TYPE == 'heat_storage_analysis':
        parametric_analysis.analyze_heat_storage()
    elif config.ANALYSIS_TYPE == 'heat_storage_time_analysis':
        run_heat_storage_time_analysis()
    else:
        print(f"Error: Unknown analysis type '{config.ANALYSIS_TYPE}' in config.py")


if __name__ == "__main__":
    main()
