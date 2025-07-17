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

def analyze_exergy(compression_states, expansion_states, compression_processes, expansion_processes):
    """
    Performs the exergetic analysis for the entire CAES cycle.

    Args:
        compression_states (list): List of thermodynamic states for the compression cycle.
        expansion_states (list): List of thermodynamic states for the expansion cycle.
        compression_processes (list): List of process types for the compression cycle.
        expansion_processes (list): List of process types for the expansion cycle.
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
            # We set irreversibility to a small value for plotting, as it's a gain, not a loss.
            irr = 0 
            print(f"Exergy gain in {comp_name}: {exergy_gain / 1e3:.2f} kJ/kg")


        irreversibilities[comp_name] = irr

    # --- Plotting ---
    plot_irreversibility_pie_chart(irreversibilities)


def plot_irreversibility_pie_chart(irreversibilities):
    """
    Plots a pie chart of the irreversibilities for each component.

    Args:
        irreversibilities (dict): A dictionary with component names as keys and
                                  their irreversibility values (in J/kg) as values.
    """
    # Filter out zero or negative irreversibilities for a cleaner chart
    labels = [key for key, value in irreversibilities.items() if value > 0]
    sizes = [value for value in irreversibilities.values() if value > 0]

    if not sizes:
        print("No positive irreversibilities to plot.")
        return

    total_irr = sum(sizes)
    print("\n--- Exergy Destruction per Component ---")
    for label, size in zip(labels, sizes):
        print(f"{label}: {size / 1e3:.2f} kJ/kg ({(size/total_irr)*100:.1f}%)")
    print(f"Total: {total_irr / 1e3:.2f} kJ/kg")


    # Define colors for component types
    colors_map = {
        'C': 'skyblue',   # Compressor
        'E': 'salmon',    # Expander (Turbine)
        'IC': 'lightgreen', # Intercooler (Heat Exchanger)
        'IH': 'gold',     # Interheater (Heat Exchanger)
        'S': 'grey'       # Storage
    }
    
    colors = []
    for label in labels:
        prefix = ''.join(filter(str.isalpha, label))
        colors.append(colors_map.get(prefix, 'lightgrey'))


    fig, ax = plt.subplots(figsize=(10, 8))
    wedges, texts, autotexts = ax.pie(
        sizes, 
        autopct=lambda p: f'{p:.1f}%\n({(p/100)*total_irr/1e3:.1f} kJ/kg)',
        startangle=90,
        colors=colors,
        pctdistance=0.85,
        wedgeprops=dict(width=0.4, edgecolor='w')
    )

    # Style text
    plt.setp(autotexts, size=8, weight="bold", color="white")
    
    # Legend
    legend_labels = {
        'Compressors': 'skyblue',
        'Turbines': 'salmon',
        'Heat Exchangers': 'lightgreen',
        'Storage': 'grey'
    }
    handles = [plt.Rectangle((0,0),1,1, color=color) for color in legend_labels.values()]
    ax.legend(handles, legend_labels.keys(), title="Component Types", loc="center")

    ax.set_title("Distribution of Exergetic Irreversibilities", pad=20)
    plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    plt.show()
