"""
Exergetic analysis for the CAES plant.

This module calculates the exergy destruction (irreversibility) for each component
in the compression and expansion cycles. It then visualizes the distribution of these
losses in a pie chart.

The physical exergy 'b' is calculated for each state as:
b = (h - h_0) - T_0 * (s - s_0)
where h_0, s_0, and T_0 are the enthalpy, entropy, and temperature at the dead state (ambient conditions).

The irreversibility (exergy destruction) for a component is calculated based on the exergy balance.
For a steady-state component without work interaction (like a heat exchanger):
Irreversibility = m * (b_in - b_out)

For a work-producing/consuming component (turbine/compressor):
Irreversibility = T_0 * (s_out - s_in)

For the storage process, the irreversibility is the difference in exergy between the
fluid entering the storage and the fluid exiting it.
"""

import matplotlib.pyplot as plt
import numpy as np
from CoolProp.CoolProp import PropsSI
import config
from core import heat_storage
from matplotlib.patches import Rectangle

def calculate_physical_exergy(state, dead_state):
    """
    Calculates the specific physical exergy of a thermodynamic state.

    Args:
        state (dict): The thermodynamic state {'H', 'S'}.
        dead_state (dict): The dead state {'H', 'S', 'T'}.

    Returns:
        float: The specific physical exergy (J/kg).
    """
    h = state['H']
    s = state['S']
    h0 = dead_state['H']
    s0 = dead_state['S']
    t0 = dead_state['T']
    
    return (h - h0) - t0 * (s - s0)

def analyze_exergy(compression_states, expansion_states, compression_processes, expansion_processes, water_tank_temperature_c=None):
    """
    Performs the exergetic analysis for the entire CAES cycle.

    Args:
        compression_states (list): List of thermodynamic states for the compression cycle.
        expansion_states (list): List of thermodynamic states for the expansion cycle.
        compression_processes (list): List of process types for the compression cycle.
        expansion_processes (list): List of process types for the expansion cycle.
        water_tank_temperature_c (float, optional): Water tank temperature in Celsius for heat storage analysis.
    """
    print("\n--- Running Exergetic Analysis ---")

    # Define the dead state (ambient conditions)
    p0 = config.COMPRESSOR_INLET_P_BAR * 1e5
    t0 = config.T_AMBIENT_C + config.ZERO_C
    dead_state = {
        'P': p0,
        'T': t0,
        'H': PropsSI('H', 'P', p0, 'T', t0, config.FLUID),
        'S': PropsSI('S', 'P', p0, 'T', t0, config.FLUID),
    }

    irreversibilities = {}

    # --- Compression Cycle Irreversibilities ---
    for i, process in enumerate(compression_processes):
        in_state = compression_states[i]
        out_state = compression_states[i+1]
        comp_name = f"C{i//2 + 1}" if 'compressor' in process else f"IC{(i-1)//2 + 1}"
        
        if 'compressor' in process:
            # Irreversibility = T0 * (s_out - s_in)
            irr = dead_state['T'] * (out_state['S'] - in_state['S'])
        else: # Intercooler
            # Irreversibility = b_in - b_out
            b_in = calculate_physical_exergy(in_state, dead_state)
            b_out = calculate_physical_exergy(out_state, dead_state)
            irr = b_in - b_out
            
            # Add heat storage exergy destruction if enabled
            if config.HEAT_STORAGE_ENABLED and 'intercooler' in process:
                # Calculate exergy destruction in heat transfer to water storage
                heat_rejected = out_state['H'] - in_state['H']  # Negative value
                if water_tank_temperature_c is not None:
                    t_water = water_tank_temperature_c + 273.15
                    # Exergy destruction in heat transfer from air to water
                    exergy_destruction = dead_state['T'] * (out_state['S'] - in_state['S']) - (out_state['H'] - in_state['H']) * (1 - dead_state['T'] / t_water)
                    irr = abs(exergy_destruction)
        
        irreversibilities[comp_name] = irr

    # --- Storage Irreversibility ---
    # This is the exergy loss from the end of compression to the start of expansion
    storage_in_state = compression_states[-1]
    storage_out_state = expansion_states[0]
    b_storage_in = calculate_physical_exergy(storage_in_state, dead_state)
    b_storage_out = calculate_physical_exergy(storage_out_state, dead_state)
    # The equation should be b_in - b_out, but since we assume no loss, this will be zero.
    # We include it for completeness.
    storage_irr = b_storage_in - b_storage_out
    irreversibilities["Storage"] = storage_irr if storage_irr > 0 else 0

    # --- Heat Storage System Exergy ---
    if config.HEAT_STORAGE_ENABLED and water_tank_temperature_c is not None:
        # Calculate exergy stored in water tank
        water_mass = heat_storage.calculate_water_mass()
        exergy_water = heat_storage.calculate_exergy_of_water_storage(
            water_tank_temperature_c, water_mass, dead_state['T']
        )
        
        # Add heat storage irreversibility
        irreversibilities["Heat Storage"] = abs(exergy_water) * 0.05  # Assume 5% irreversibility
        
        print(f"\nHeat Storage System:")
        print(f"Water tank temperature: {water_tank_temperature_c:.2f}°C")
        print(f"Exergy stored in water: {exergy_water/1000:.2f} kJ/kg")

    # --- Expansion Cycle Irreversibilities ---
    for i, process in enumerate(expansion_processes):
        in_state = expansion_states[i]
        out_state = expansion_states[i+1]
        comp_name = f"E{i//2 + 1}" if 'expander' in process else f"IH{(i-1)//2 + 1}"

        if 'expander' in process:
            # Irreversibility = T0 * (s_out - s_in)
            irr = dead_state['T'] * (out_state['S'] - in_state['S'])
        else: # Interheater

            # Irreversibility = b_in - b_out (will be negative, so we take abs)
            # This represents exergy supplied by the heat source, not destroyed.
            # For a complete analysis, we'd need the source temperature.
            # Here, we calculate the exergy increase of the fluid.
            # The actual irreversibility is in the heat transfer process.
            # For simplicity, we'll label the exergy GAIN here, but not include it in the destruction pie chart.
            # A more rigorous approach would model the heat source.

            b_in = calculate_physical_exergy(in_state, dead_state)
            b_out = calculate_physical_exergy(out_state, dead_state)
            exergy_gain = b_out - b_in
            
            # Calculate exergy destruction in heat transfer from water to air
            if config.HEAT_STORAGE_ENABLED and water_tank_temperature_c is not None:
                t_water = water_tank_temperature_c + 273.15
                # Exergy destruction in heat transfer from water to air
                exergy_destruction = dead_state['T'] * (out_state['S'] - in_state['S']) - (out_state['H'] - in_state['H']) * (1 - dead_state['T'] / t_water)
                irr = abs(exergy_destruction)
            else:
                irr = 0 
            print(f"Exergy gain in {comp_name}: {exergy_gain / 1e3:.2f} kJ/kg")


        irreversibilities[comp_name] = irr

    # --- Enhanced Plotting ---
    plot_enhanced_exergy_analysis(irreversibilities, compression_processes, expansion_processes)


def plot_enhanced_exergy_analysis(irreversibilities, compression_processes, expansion_processes):
    """
    Plots enhanced pie charts showing both individual components and summed categories.
    
    Args:
        irreversibilities (dict): Dictionary with component names as keys and irreversibility values
        compression_processes (list): List of compression process types
        expansion_processes (list): List of expansion process types
    """
    import matplotlib.pyplot as plt
    import numpy as np
    
    # Filter out zero or negative irreversibilities
    positive_irreversibilities = {k: v for k, v in irreversibilities.items() if v > 0}
    
    if not positive_irreversibilities:
        print("No positive irreversibilities to plot.")
        return
    
    # Create categories for summed analysis
    categories = {
        'All Compressors': 0,
        'All Expanders': 0,
        'All Intercoolers': 0,
        'All Interheaters': 0,
        'Storage': 0
    }
    
    # Categorize individual components
    individual_detailed = {}
    
    for comp, irr in positive_irreversibilities.items():
        if comp.startswith('C'):
            categories['All Compressors'] += irr
            individual_detailed[comp] = irr
        elif comp.startswith('E'):
            categories['All Expanders'] += irr
            individual_detailed[comp] = irr
        elif comp.startswith('IC'):
            categories['All Intercoolers'] += irr
            individual_detailed[comp] = irr
        elif comp.startswith('IH'):
            categories['All Interheaters'] += irr
            individual_detailed[comp] = irr
        elif comp == 'Storage':
            categories['Storage'] += irr
            individual_detailed[comp] = irr
    
    # Remove empty categories
    categories = {k: v for k, v in categories.items() if v > 0}
    
    # Print detailed analysis
    total_irr = sum(positive_irreversibilities.values())
    
    print("\n" + "="*60)
    print("EXERGY DESTRUCTION ANALYSIS")
    print("="*60)
    
    print("\n--- Individual Components ---")
    for comp, irr in sorted(individual_detailed.items(), key=lambda x: x[1], reverse=True):
        percentage = (irr / total_irr) * 100
        print(f"{comp}: {irr/1000:.2f} kJ/kg ({percentage:.1f}%)")
    
    print("\n--- Summed Categories ---")
    for category, irr in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        percentage = (irr / total_irr) * 100
        print(f"{category}: {irr/1000:.2f} kJ/kg ({percentage:.1f}%)")
    
    print(f"\nTotal Exergy Destruction: {total_irr/1000:.2f} kJ/kg")
    print("="*60)
    
    # Create enhanced visualization
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    # Colors for individual components
    colors_individual = []
    for comp in individual_detailed.keys():
        if comp.startswith('C'):
            colors_individual.append('#1f77b4')  # blue
        elif comp.startswith('E'):
            colors_individual.append('#ff7f0e')  # orange
        elif comp.startswith('IC'):
            colors_individual.append('#2ca02c')  # green
        elif comp.startswith('IH'):
            colors_individual.append('#d62728')  # red
        elif comp == 'Storage':
            colors_individual.append('#9467bd')  # purple
    
    # Colors for categories
    colors_categories = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    
    # Plot 1: Individual Components
    if individual_detailed:
        sizes1 = list(individual_detailed.values())
        labels1 = list(individual_detailed.keys())
        
        wedges1, texts1, autotexts1 = ax1.pie(
            sizes1, 
            labels=labels1,
            autopct=lambda p: f'{p:.1f}%',
            startangle=90,
            colors=colors_individual,
            textprops={'fontsize': 9}
        )
        ax1.set_title('Individual Components\nExergy Destruction', fontsize=12, fontweight='bold')
    
    # Plot 2: Summed Categories
    if categories:
        sizes2 = list(categories.values())
        labels2 = [f'{k}\n{v/1000:.1f} kJ/kg' for k, v in categories.items()]
        
        wedges2, texts2, autotexts2 = ax2.pie(
            sizes2,
            labels=labels2,
            autopct=lambda p: f'{p:.1f}%',
            startangle=90,
            colors=colors_categories[:len(categories)],
            textprops={'fontsize': 10}
        )
        ax2.set_title('Summed Categories\nExergy Destruction', fontsize=12, fontweight='bold')
    
    plt.suptitle('Exergetic Analysis: Irreversibility Distribution', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.show()
    
    # Also create a summary table
    print("\n" + "="*60)
    print("EXERGY DESTRUCTION SUMMARY TABLE")
    print("="*60)
    print(f"{'Component':<15} {'Irreversibility':<15} {'Percentage':<10}")
    print("-"*45)
    
    for comp, irr in sorted(individual_detailed.items(), key=lambda x: x[1], reverse=True):
        percentage = (irr / total_irr) * 100
        print(f"{comp:<15} {irr/1000:<15.2f} {percentage:<10.1f}%")
    
    print("-"*45)
    print(f"{'TOTAL':<15} {total_irr/1000:<15.2f} {100.0:<10.1f}%")
    print("="*60)
