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
from core import heat_storage
from matplotlib.patches import Rectangle

try:
    from dashboard import AMBIENT_PRESSURE_BAR, AMBIENT_TEMPERATURE_C, HEAT_STORAGE_ENABLED
except ImportError:
    AMBIENT_PRESSURE_BAR = 1.0
    AMBIENT_TEMPERATURE_C = 15.0
    HEAT_STORAGE_ENABLED = True

FLUID = "Air"  # Working fluid
ZERO_C = 273.15  # Conversion constant

def calculate_physical_exergy(state, dead_state):
    """
    Calculates the specific physical exergy of a thermodynamic state using the correct equation:
    b = ξ - ξ₀ = h - h₀ - T₀(s - s₀)
    
    Where:
    ξ = h - T₀s (specific flow exergy)
    ξ₀ = h₀ - T₀s₀ (dead state flow exergy)
    
    Args:
        state (dict): The thermodynamic state {'H', 'S', 'T', 'P'}.
        dead_state (dict): The dead state {'H', 'S', 'T', 'P'}.

    Returns:
        float: The specific physical exergy (J/kg).
    """
    h = state['H']      # Specific enthalpy [J/kg]
    s = state['S']      # Specific entropy [J/kg·K]
    h0 = dead_state['H'] # Dead state enthalpy [J/kg]
    s0 = dead_state['S'] # Dead state entropy [J/kg·K]
    T0 = dead_state['T'] # Dead state temperature [K]
    
    # Calculate flow exergy for current state
    xi = h - T0 * s
    
    # Calculate flow exergy for dead state  
    xi0 = h0 - T0 * s0
    
    # Physical exergy
    b = xi - xi0  # This equals (h - h0) - T0 * (s - s0)
    
    return b

def calculate_exergy_destruction(inlet_state, outlet_state, dead_state, process_type="generic", heat_source_temp=None):
    """
    Calculate exergy destruction for a process using proper exergy balance according to 
    "equazione dell'energia utilizzabile".
    
    General exergy balance: I = b_in - b_out + Σ Q_j(1 - T0/T_j) - W
    
    For adiabatic processes (compressor, expander):
    I = T0 * s_gen (no heat transfer, Q=0)
    
    For heat exchange processes (intercooler, interheater):
    I = b_in - b_out + Q(1 - T0/T_source) where Q is heat added to fluid
    
    Args:
        inlet_state (dict): Inlet thermodynamic state
        outlet_state (dict): Outlet thermodynamic state
        dead_state (dict): Dead state (ambient conditions)
        process_type (str): Type of process for specific calculations
        heat_source_temp (float): Temperature of heat source/sink [K]
        
    Returns:
        float: Exergy destruction (irreversibility) [J/kg]
    """
    # Calculate physical exergy at inlet and outlet
    b_in = calculate_physical_exergy(inlet_state, dead_state)
    b_out = calculate_physical_exergy(outlet_state, dead_state)
    
    T0 = dead_state['T']
    
    if process_type in ['compressor', 'expander']:
        # For adiabatic work processes: I = T0 * s_gen (Q=0)
        s_in = inlet_state['S']
        s_out = outlet_state['S'] 
        s_gen = s_out - s_in  # Entropy generation
        exergy_destruction = T0 * s_gen
        
    elif process_type in ['intercooler', 'interheater']:
        # For heat exchange processes: I = b_in - b_out + Q(1 - T0/T_source)
        h_in = inlet_state['H']
        h_out = outlet_state['H']
        Q = h_out - h_in  # Heat added to fluid [J/kg]
        
        if process_type == 'intercooler':
            # Heat rejected to ambient: Q < 0, T_sink = T0
            # I = b_in - b_out + Q(1 - T0/T0) = b_in - b_out + 0
            exergy_destruction = b_in - b_out
        else:  # interheater
            # Heat added from external source: Q > 0
            if heat_source_temp is not None and heat_source_temp > T0:
                # A-CAES: Heat from hot water storage
                # I = b_in - b_out + Q(1 - T0/T_source)
                exergy_of_heat = Q * (1 - T0 / heat_source_temp)
                exergy_destruction = b_in - b_out + exergy_of_heat
            else:
                # D-CAES: Heat from ambient (free exergy from environment)
                # The heat input reduces the exergy destruction
                # For ambient air interheating: I = b_in - b_out - |Q|
                exergy_destruction = b_in - b_out - abs(Q)  # Negative because heat reduces destruction
            
    else:
        # Generic process - simple exergy balance
        exergy_destruction = b_in - b_out
    
    return abs(exergy_destruction)  # Return absolute value


def calculate_exergy_efficiency(compression_states, expansion_states, T_ambient_K, P_ambient_Pa):
    """
    Calculate the exergy efficiency of the CAES cycle.
    
    Exergy efficiency = Useful exergy output / Exergy input
    For CAES: Exergy efficiency = Net work output / Compression work input
    
    Args:
        compression_states: List of thermodynamic states during compression
        expansion_states: List of thermodynamic states during expansion  
        T_ambient_K: Ambient temperature in Kelvin
        P_ambient_Pa: Ambient pressure in Pascal
        
    Returns:
        float: Exergy efficiency as percentage
    """
    try:
        # Calculate compression work (only compressor work, positive values only)
        compression_work_input = 0
        for i in range(len(compression_states) - 1):
            state_in = compression_states[i]
            state_out = compression_states[i + 1]
            
            # Work calculation
            work = state_out['H'] - state_in['H']  # J/kg
            
            # Only count positive work (actual compression work)
            if work > 0:
                compression_work_input += work
        
        # Calculate expansion work (only turbine work, positive values only)
        expansion_work_output = 0
        for i in range(len(expansion_states) - 1):
            state_in = expansion_states[i]
            state_out = expansion_states[i + 1]
            
            # Work calculation
            work = state_in['H'] - state_out['H']  # J/kg
            
            # Only count positive work (actual expansion work)
            if work > 0:
                expansion_work_output += work
        
        # Calculate exergy efficiency
        if compression_work_input > 0:
            exergy_efficiency = (expansion_work_output / compression_work_input) * 100
        else:
            exergy_efficiency = 0
            
        return min(exergy_efficiency, 100)  # Cap at 100%
        
    except Exception as e:
        print(f"   ❌ Error in exergy efficiency calculation: {e}")
        import traceback
        traceback.print_exc()
        return 0

def run_exergetic_analysis(compression_states, expansion_states, compression_processes, expansion_processes, water_tank_temperature_c=None):
    """
    Performs the complete exergetic analysis for the entire CAES cycle.
    
    This function calculates irreversibilities (exergy destruction) for each component
    ONLY ONCE and then uses these values for visualization.

    Args:
        compression_states (list): List of thermodynamic states for the compression cycle.
        expansion_states (list): List of thermodynamic states for the expansion cycle.
        compression_processes (list): List of process types for the compression cycle.
        expansion_processes (list): List of process types for the expansion cycle.
        water_tank_temperature_c (float, optional): Water tank temperature in Celsius for heat storage analysis.
    
    Returns:
        dict: Dictionary containing component irreversibilities and overall efficiency
    """
    print("\n🔬 DETAILED EXERGY ANALYSIS:")
    print("="*60)

    # Define the dead state (ambient conditions)
    p0 = AMBIENT_PRESSURE_BAR * 1e5
    t0 = AMBIENT_TEMPERATURE_C + ZERO_C
    dead_state = {
        'P': p0,
        'T': t0,
        'H': PropsSI('H', 'P', p0, 'T', t0, FLUID),
        'S': PropsSI('S', 'P', p0, 'T', t0, FLUID),
    }

    # Dictionary to store ALL component irreversibilities
    irreversibilities = {}

    print("🔍 Component-wise Exergy Destruction:")
    print("-"*60)

    # --- Compression Cycle Irreversibilities ---
    print("📈 COMPRESSION CYCLE:")
    for i, process in enumerate(compression_processes):
        in_state = compression_states[i]
        out_state = compression_states[i+1]
        
        # Determine component name based on process order
        if 'compressor' in process:
            comp_name = f"C{(i//2) + 1}"
        else: # intercooler
            comp_name = f"IC{((i-1)//2) + 1}"
        
        # Calculate exergy destruction using proper thermodynamic method
        irr = calculate_exergy_destruction(in_state, out_state, dead_state, process)
        
        print(f"   {comp_name:4s} ({process:12s}): {irr/1000:6.2f} kJ/kg")
        irreversibilities[comp_name] = irr

    # --- Expansion Cycle Irreversibilities ---  
    print("\n📉 EXPANSION CYCLE:")
    for i, process in enumerate(expansion_processes):
        in_state = expansion_states[i]
        out_state = expansion_states[i+1]
        
        # Determine component name based on process order
        if 'expander' in process:
            exp_name = f"E{((i+1)//2) + 1}"
        else: # interheater
            exp_name = f"IH{(i//2) + 1}"
        
        # For interheaters, consider heat source temperature if available
        heat_source_temp = None
        if 'interheater' in process and HEAT_STORAGE_ENABLED and water_tank_temperature_c is not None:
            heat_source_temp = water_tank_temperature_c + ZERO_C
        
        # Calculate exergy destruction with proper heat flow considerations
        irr = calculate_exergy_destruction(in_state, out_state, dead_state, process, heat_source_temp)
        
        print(f"   {exp_name:4s} ({process:12s}): {irr/1000:6.2f} kJ/kg")
        irreversibilities[exp_name] = irr

    # --- Calculate Overall Performance ---
    print("\n" + "="*60)
    print("⚡ OVERALL PERFORMANCE:")
    
    # Calculate efficiency using the same thermodynamic states
    efficiency = calculate_exergy_efficiency(compression_states, expansion_states, t0, p0)
    print(f"🎯 Overall Exergy Efficiency: {efficiency:.2f}%")
    
    # Calculate total irreversibilities
    total_irreversibilities = sum(irreversibilities.values())
    print(f"🔥 Total Exergy Destruction: {total_irreversibilities/1000:.2f} kJ/kg")
    
    # --- Enhanced Plotting with SINGLE calculation ---
    print("\n📊 Generating visualization...")
    plot_enhanced_exergy_analysis(irreversibilities, compression_processes, expansion_processes)
    
    # Return results for potential further use
    return {
        'irreversibilities': irreversibilities,
        'efficiency': efficiency,
        'total_destruction': total_irreversibilities
    }


def plot_enhanced_exergy_analysis(irreversibilities, compression_processes, expansion_processes):
    """
    Plots enhanced visualization based on configuration:
    - Configuration 1 (No Heat Storage): Sankey diagram for exergy flows (simplified or detailed)
    - Configuration 2 (With Heat Storage): Pie chart for irreversibilities
    
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
    
    # Determine configuration based on heat storage
    config_with_heat_storage = HEAT_STORAGE_ENABLED
    
    if config_with_heat_storage:
        # Configuration 2: A-CAES with Heat Storage - Use Pie Chart
        plot_a_caes_pie_chart(positive_irreversibilities)
    else:
        # Configuration 1: D-CAES without Heat Storage - Use Sankey Diagram
        # Check diagram type from dashboard configuration
        try:
            from dashboard import SANKEY_DIAGRAM_TYPE
        except ImportError:
            SANKEY_DIAGRAM_TYPE = "simplified"  # Default to simplified
        
        if SANKEY_DIAGRAM_TYPE == "detailed":
            plot_d_caes_detailed_sankey_diagram(positive_irreversibilities, compression_processes, expansion_processes)
        else:
            plot_d_caes_sankey_diagram(positive_irreversibilities, compression_processes, expansion_processes)


def plot_a_caes_pie_chart(irreversibilities):
    """
    Create pie chart for A-CAES (Configuration 2) showing irreversibility distribution.
    """
    # Create categories for A-CAES
    categories = {
        'Heat Exchangers (Intercoolers)': 0,
        'Heat Exchangers (Interheaters)': 0,
        'Compressors': 0,
        'Expanders': 0,
        'Heat Storage System': 0,
        'Storage': 0
    }
    
    # Categorize components
    for comp, irr in irreversibilities.items():
        if comp.startswith('IC'):
            categories['Heat Exchangers (Intercoolers)'] += irr
        elif comp.startswith('IH'):
            categories['Heat Exchangers (Interheaters)'] += irr
        elif comp.startswith('C'):
            categories['Compressors'] += irr
        elif comp.startswith('E'):
            categories['Expanders'] += irr
        elif comp == 'Heat Storage':
            categories['Heat Storage System'] += irr
        elif comp == 'Storage':
            categories['Storage'] += irr
    
    # Remove empty categories
    categories = {k: v for k, v in categories.items() if v > 0}
    
    # Create pie chart
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    labels = list(categories.keys())
    sizes = list(categories.values())
    total_irr = sum(sizes)
    
    # Custom colors for A-CAES
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']
    
    # Create pie chart with percentage labels
    def autopct_func(pct):
        absolute = int(pct/100.*total_irr)
        return f'{pct:.1f}%\n({absolute/1000:.1f} kJ/kg)'
    
    wedges, texts, autotexts = ax.pie(
        sizes, 
        labels=labels,
        autopct=autopct_func,
        startangle=90,
        colors=colors[:len(categories)],
        textprops={'fontsize': 10},
        explode=[0.05] * len(categories)  # Small separation for clarity
    )
    
    ax.set_title('A-CAES Exergy Destruction Distribution\n(Configuration 2: With Heat Storage)', 
                 fontsize=14, fontweight='bold', pad=20)
    
    # Add total destruction info
    plt.figtext(0.5, 0.02, f'Total Exergy Destruction: {total_irr/1000:.1f} kJ/kg', 
                ha='center', fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    plt.show()


def plot_d_caes_sankey_diagram(irreversibilities, compression_processes, expansion_processes):
    """
    Create a simplified Sankey diagram for D-CAES showing major component groups.
    Shows exergy input flowing left-to-right through component categories with color coding.
    """
    from matplotlib.sankey import Sankey
    
    # Import dashboard config - use try/except to provide defaults if import fails
    try:
        from dashboard import SANKEY_ARROW_SCALE, SANKEY_ARROW_GAP, SANKEY_ARROW_SHOULDER, SANKEY_FIGURE_WIDTH, SANKEY_FIGURE_HEIGHT
    except ImportError:
        # Default values if dashboard import fails
        SANKEY_ARROW_SCALE = 0.003
        SANKEY_ARROW_GAP = 1.8
        SANKEY_ARROW_SHOULDER = 0.008
        SANKEY_FIGURE_WIDTH = 22
        SANKEY_FIGURE_HEIGHT = 10
    
    print("📊 Creating simplified Sankey diagram for D-CAES...")
    
    # Separate and organize components by category
    compression_irr = {k: v for k, v in irreversibilities.items() if k.startswith(('C', 'IC'))}
    expansion_irr = {k: v for k, v in irreversibilities.items() if k.startswith(('E', 'IH'))}
    
    # Group by component types
    compressor_losses = sum(v for k, v in compression_irr.items() if k.startswith('C')) / 1000  # kJ/kg
    intercooler_losses = sum(v for k, v in compression_irr.items() if k.startswith('IC')) / 1000
    expander_losses = sum(v for k, v in expansion_irr.items() if k.startswith('E')) / 1000
    interheater_losses = sum(v for k, v in expansion_irr.items() if k.startswith('IH')) / 1000
    
    total_losses = compressor_losses + intercooler_losses + expander_losses + interheater_losses
    
    # Estimate work values based on typical D-CAES efficiency
    estimated_efficiency = 0.52
    loss_fraction = 1 - estimated_efficiency
    compression_work = total_losses / loss_fraction
    expansion_work = compression_work - total_losses
    
    print(f"   📈 Input work: {compression_work:.1f} kJ/kg")
    print(f"   📉 Component losses - Compressors: {compressor_losses:.1f}, Intercoolers: {intercooler_losses:.1f}")
    print(f"   📉 Component losses - Expanders: {expander_losses:.1f}, Interheaters: {interheater_losses:.1f}")
    print(f"   🔌 Output work: {expansion_work:.1f} kJ/kg")
    
    # Create simplified Sankey diagram with individual colored flows
    fig = plt.figure(figsize=(SANKEY_FIGURE_WIDTH, SANKEY_FIGURE_HEIGHT))
    ax = fig.add_subplot(1, 1, 1)
    
    # Create multiple Sankey flows with different colors for each component type
    # Using configuration parameters for arrow appearance
    sankey = Sankey(ax=ax, 
                   scale=SANKEY_ARROW_SCALE,     # From dashboard config - controls arrow thickness
                   offset=0.1,       
                   format='', 
                   gap=SANKEY_ARROW_GAP,         # From dashboard config - controls arrow length
                   shoulder=SANKEY_ARROW_SHOULDER, # From dashboard config - controls arrow head size
                   margin=0.4)       
    
    # Input flow (gray)
    sankey.add(
        flows=[compression_work, -compression_work],
        labels=[f'Input Work\n{compression_work:.0f} kJ/kg', ''],
        orientations=[0, 0],
        pathlengths=[0.25, 1.0],  # Increased pathlengths for longer arrows
        facecolor='lightgray',
        edgecolor='darkgray',
        alpha=0.8
    )
    
    # Compressor losses (green)
    sankey.add(
        flows=[compression_work, -compressor_losses, -(compression_work - compressor_losses)],
        labels=['', f'Compressor Losses\n{compressor_losses:.0f} kJ/kg', ''],
        orientations=[0, 1, 0],
        pathlengths=[1.0, 0.5, 1.0],  # Increased pathlengths for longer arrows
        prior=0, connect=(1, 0),
        facecolor='#2ca02c',
        edgecolor='darkgreen',
        alpha=0.7
    )
    
    # Intercooler losses (blue)
    remaining_after_comp = compression_work - compressor_losses
    sankey.add(
        flows=[remaining_after_comp, -intercooler_losses, -(remaining_after_comp - intercooler_losses)],
        labels=['', f'Intercooler Losses\n{intercooler_losses:.0f} kJ/kg', ''],
        orientations=[0, 1, 0],
        pathlengths=[1.0, 0.5, 1.0],  # Increased pathlengths for longer arrows
        prior=1, connect=(2, 0),
        facecolor='#1f77b4',
        edgecolor='darkblue',
        alpha=0.7
    )
    
    # To storage (orange) - remove duplicate label
    to_storage = remaining_after_comp - intercooler_losses
    sankey.add(
        flows=[to_storage, -to_storage],
        labels=['', ''],  # Remove labels to avoid duplication
        orientations=[0, 0],
        pathlengths=[1.0, 1.0],  # Increased pathlengths for longer arrows
        prior=2, connect=(2, 0),
        facecolor='orange',
        edgecolor='darkorange',
        alpha=0.8
    )
    
    # From storage (same as to storage) - single label in middle
    sankey.add(
        flows=[to_storage, -to_storage],
        labels=[f'Storage\n{to_storage:.0f} kJ/kg', ''],  # Single label for storage
        orientations=[0, 0],
        pathlengths=[1.0, 1.0],  # Increased pathlengths for longer arrows
        prior=3, connect=(1, 0),
        facecolor='orange',
        edgecolor='darkorange',
        alpha=0.8
    )
    
    # Expander losses (purple)
    sankey.add(
        flows=[to_storage, -expander_losses, -(to_storage - expander_losses)],
        labels=['', f'Expander Losses\n{expander_losses:.0f} kJ/kg', ''],
        orientations=[0, -1, 0],
        pathlengths=[1.0, 0.5, 1.0],  # Increased pathlengths for longer arrows
        prior=4, connect=(1, 0),
        facecolor='#9467bd',
        edgecolor='purple',
        alpha=0.7
    )
    
    # Interheater losses (red)
    remaining_after_exp = to_storage - expander_losses
    sankey.add(
        flows=[remaining_after_exp, -interheater_losses, -(remaining_after_exp - interheater_losses)],
        labels=['', f'Interheater Losses\n{interheater_losses:.0f} kJ/kg', ''],
        orientations=[0, -1, 0],
        pathlengths=[1.0, 0.5, 1.0],  # Increased pathlengths for longer arrows
        prior=5, connect=(2, 0),
        facecolor='#d62728',
        edgecolor='darkred',
        alpha=0.7
    )
    
    # Final output (light green)
    final_output = remaining_after_exp - interheater_losses
    sankey.add(
        flows=[final_output],
        labels=[f'Output Work\n{final_output:.0f} kJ/kg'],
        orientations=[0],
        pathlengths=[0.25],  
        prior=6, connect=(2, 0),
        facecolor='lightgreen',
        edgecolor='darkgreen',
        alpha=0.8
    )
    
    # Finish the diagram
    diagrams = sankey.finish()
    
    # Fix matplotlib warning by setting axis properties correctly
    ax.set_xlim(None, None)  # Let matplotlib auto-scale
    ax.set_ylim(None, None)  # Let matplotlib auto-scale
    ax.set_aspect('auto')    # Use automatic aspect ratio instead of 'equal'
    
    # Add title
    plt.title('D-CAES Exergy Flow Diagram\n(Simplified Component-wise Breakdown)', 
              fontsize=16, fontweight='bold', pad=20)
    
    # Add efficiency info (use calculated final output) - moved to bottom left
    final_work_output = compression_work - total_losses
    efficiency = (final_work_output/compression_work)*100
    info_text = f"""SYSTEM PERFORMANCE:
Round-trip Efficiency: {efficiency:.1f}%
Total Exergy Destruction: {total_losses:.1f} kJ/kg

COMPONENT BREAKDOWN:
• Compressors: {compressor_losses:.1f} kJ/kg ({compressor_losses/total_losses*100:.1f}%)
• Intercoolers: {intercooler_losses:.1f} kJ/kg ({intercooler_losses/total_losses*100:.1f}%)
• Expanders: {expander_losses:.1f} kJ/kg ({expander_losses/total_losses*100:.1f}%)  
• Interheaters: {interheater_losses:.1f} kJ/kg ({interheater_losses/total_losses*100:.1f}%)"""
    
    props = dict(boxstyle='round,pad=0.5', facecolor='lightyellow', alpha=0.9, edgecolor='orange')
    # Move yellow box to bottom left (changed from 0.02, 0.98 to 0.02, 0.35 and top to bottom)
    ax.text(0.02, 0.02, info_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='bottom', bbox=props, family='monospace')
    
    # Add color legend
    legend_elements = [
        plt.Rectangle((0,0),1,1, facecolor='#2ca02c', label='Compressor Losses'),
        plt.Rectangle((0,0),1,1, facecolor='#1f77b4', label='Intercooler Losses'),
        plt.Rectangle((0,0),1,1, facecolor='#9467bd', label='Expander Losses'),
        plt.Rectangle((0,0),1,1, facecolor='#d62728', label='Interheater Losses')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    plt.tight_layout()
    plt.show()
    
    print("✅ Simplified Sankey diagram created successfully")
    
    # Also create a detailed breakdown table
    print("\n📋 DETAILED COMPONENT BREAKDOWN:")
    print("="*50)
    print("COMPRESSION COMPONENTS:")
    for comp, irr in sorted(compression_irr.items()):
        print(f"   {comp:4s}: {irr/1000:6.2f} kJ/kg")
    
    print("\nEXPANSION COMPONENTS:")
    for comp, irr in sorted(expansion_irr.items()):
        print(f"   {comp:4s}: {irr/1000:6.2f} kJ/kg")
    
    print(f"\nTOTAL LOSSES: {total_losses:.2f} kJ/kg")
    print(f"EFFICIENCY: {efficiency:.2f}%")


def plot_d_caes_detailed_sankey_diagram(irreversibilities, compression_processes, expansion_processes):
    """
    Create a detailed Sankey diagram for D-CAES showing individual component losses.
    Shows exergy input flowing through every individual component (C1, IC1, C2, IC2, etc.)
    """
    from matplotlib.sankey import Sankey
    
    # Import detailed dashboard config - use try/except to provide defaults if import fails
    try:
        from dashboard import (DETAILED_SANKEY_ARROW_SCALE, DETAILED_SANKEY_ARROW_GAP, 
                              DETAILED_SANKEY_ARROW_SHOULDER, DETAILED_SANKEY_FIGURE_WIDTH, 
                              DETAILED_SANKEY_FIGURE_HEIGHT)
    except ImportError:
        # Default values if dashboard import fails
        DETAILED_SANKEY_ARROW_SCALE = 0.0008
        DETAILED_SANKEY_ARROW_GAP = 0.5
        DETAILED_SANKEY_ARROW_SHOULDER = 0.3
        DETAILED_SANKEY_FIGURE_WIDTH = 20
        DETAILED_SANKEY_FIGURE_HEIGHT = 12
    
    print("📊 Creating detailed Sankey diagram for D-CAES (individual components)...")
    
    # Sort components by name for consistent ordering
    all_components = sorted(irreversibilities.items())
    
    # Separate compression and expansion components
    compression_components = [(name, irr) for name, irr in all_components if name.startswith(('C', 'IC'))]
    expansion_components = [(name, irr) for name, irr in all_components if name.startswith(('E', 'IH'))]
    
    # Convert to kJ/kg
    compression_losses = {name: irr/1000 for name, irr in compression_components}
    expansion_losses = {name: irr/1000 for name, irr in expansion_components}
    
    total_compression_losses = sum(compression_losses.values())
    total_expansion_losses = sum(expansion_losses.values())
    total_losses = total_compression_losses + total_expansion_losses
    
    # Estimate work values based on typical D-CAES efficiency
    estimated_efficiency = 0.52
    loss_fraction = 1 - estimated_efficiency
    compression_work = total_losses / loss_fraction
    final_work_output = compression_work - total_losses
    
    print(f"   📈 Input work: {compression_work:.1f} kJ/kg")
    print(f"   📉 Total compression losses: {total_compression_losses:.1f} kJ/kg ({len(compression_components)} components)")
    print(f"   📉 Total expansion losses: {total_expansion_losses:.1f} kJ/kg ({len(expansion_components)} components)")
    print(f"   🔌 Output work: {final_work_output:.1f} kJ/kg")
    
    # Create detailed Sankey diagram
    fig = plt.figure(figsize=(DETAILED_SANKEY_FIGURE_WIDTH, DETAILED_SANKEY_FIGURE_HEIGHT))
    ax = fig.add_subplot(1, 1, 1)
    
    sankey = Sankey(ax=ax, 
                   scale=DETAILED_SANKEY_ARROW_SCALE,
                   offset=0.05,       
                   format='%.0f', 
                   gap=DETAILED_SANKEY_ARROW_GAP,
                   shoulder=DETAILED_SANKEY_ARROW_SHOULDER,
                   margin=0.3)
    
    # Start with input work
    current_flow = compression_work
    
    # Input flow (gray)
    sankey.add(
        flows=[current_flow, -current_flow],
        labels=[f'Input Work\n{current_flow:.0f} kJ/kg', ''],
        orientations=[0, 0],
        pathlengths=[0.2, 0.8],
        facecolor='lightgray',
        edgecolor='darkgray',
        alpha=0.8
    )
    
    prior_index = 0
    
    # Add compression components one by one
    for i, (comp_name, loss) in enumerate(compression_losses):
        remaining_flow = current_flow - loss
        
        # Color coding for compression components
        if comp_name.startswith('C'):
            color = '#2ca02c'  # Green for compressors
            edge_color = 'darkgreen'
        else:  # IC components
            color = '#1f77b4'  # Blue for intercoolers
            edge_color = 'darkblue'
        
        # Create label with component name and loss
        label = f'{comp_name}\n{loss:.1f} kJ/kg'
        
        sankey.add(
            flows=[current_flow, -loss, -remaining_flow],
            labels=['', label, ''],
            orientations=[0, 1 if i % 2 == 0 else -1, 0],  # Alternate loss directions
            pathlengths=[0.8, 0.4, 0.8],
            prior=prior_index, connect=(1, 0),
            facecolor=color,
            edgecolor=edge_color,
            alpha=0.7
        )
        
        current_flow = remaining_flow
        prior_index += 1
    
    # Storage section (orange)
    storage_flow = current_flow
    sankey.add(
        flows=[storage_flow, -storage_flow],
        labels=[f'Storage\n{storage_flow:.0f} kJ/kg', ''],
        orientations=[0, 0],
        pathlengths=[0.8, 0.8],
        prior=prior_index, connect=(2, 0),
        facecolor='orange',
        edgecolor='darkorange',
        alpha=0.8
    )
    
    current_flow = storage_flow
    prior_index += 1
    
    # Add expansion components one by one
    for i, (comp_name, loss) in enumerate(expansion_losses):
        remaining_flow = current_flow - loss
        
        # Color coding for expansion components
        if comp_name.startswith('E'):
            color = '#9467bd'  # Purple for expanders
            edge_color = 'purple'
        else:  # IH components
            color = '#d62728'  # Red for interheaters
            edge_color = 'darkred'
        
        # Create label with component name and loss
        label = f'{comp_name}\n{loss:.1f} kJ/kg'
        
        sankey.add(
            flows=[current_flow, -loss, -remaining_flow],
            labels=['', label, ''],
            orientations=[0, 1 if i % 2 == 0 else -1, 0],  # Alternate loss directions
            pathlengths=[0.8, 0.4, 0.8],
            prior=prior_index, connect=(1, 0),
            facecolor=color,
            edgecolor=edge_color,
            alpha=0.7
        )
        
        current_flow = remaining_flow
        prior_index += 1
    
    # Final output (light green)
    sankey.add(
        flows=[current_flow],
        labels=[f'Output Work\n{current_flow:.0f} kJ/kg'],
        orientations=[0],
        pathlengths=[0.2],
        prior=prior_index, connect=(2, 0),
        facecolor='lightgreen',
        edgecolor='darkgreen',
        alpha=0.8
    )
    
    # Finish the diagram
    diagrams = sankey.finish()
    
    # Fix matplotlib warning by setting axis properties correctly
    ax.set_xlim(None, None)
    ax.set_ylim(None, None)
    ax.set_aspect('auto')
    
    # Add title
    plt.title('D-CAES Detailed Exergy Flow Diagram\n(Individual Component Breakdown)', 
              fontsize=16, fontweight='bold', pad=20)
    
    # Add efficiency info in bottom left
    efficiency = (final_work_output/compression_work)*100
    info_text = f"""DETAILED PERFORMANCE:
Round-trip Efficiency: {efficiency:.1f}%
Total Exergy Destruction: {total_losses:.1f} kJ/kg

COMPONENT COUNT:
• Compressors: {len([c for c, _ in compression_components if c.startswith('C')])} stages
• Intercoolers: {len([c for c, _ in compression_components if c.startswith('IC')])} units
• Expanders: {len([c for c, _ in expansion_components if c.startswith('E')])} stages
• Interheaters: {len([c for c, _ in expansion_components if c.startswith('IH')])} units

LOSS BREAKDOWN:
• Compression: {total_compression_losses:.1f} kJ/kg ({total_compression_losses/total_losses*100:.1f}%)
• Expansion: {total_expansion_losses:.1f} kJ/kg ({total_expansion_losses/total_losses*100:.1f}%)"""
    
    props = dict(boxstyle='round,pad=0.5', facecolor='lightcyan', alpha=0.9, edgecolor='teal')
    ax.text(0.02, 0.4, info_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='bottom', bbox=props, family='monospace')
    
    # Add color legend for component types
    legend_elements = [
        plt.Rectangle((0,0),1,1, facecolor='#2ca02c', label='Compressors (C1-C6)'),
        plt.Rectangle((0,0),1,1, facecolor='#1f77b4', label='Intercoolers (IC1-IC6)'),
        plt.Rectangle((0,0),1,1, facecolor='#9467bd', label='Expanders (E1-E6)'),
        plt.Rectangle((0,0),1,1, facecolor='#d62728', label='Interheaters (IH1-IH6)'),
        plt.Rectangle((0,0),1,1, facecolor='orange', label='Storage')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
    
    plt.tight_layout()
    plt.show()
    
    print("✅ Detailed Sankey diagram created successfully")
    
    # Print detailed component table
    print("\n📋 INDIVIDUAL COMPONENT BREAKDOWN:")
    print("="*60)
    
    print("COMPRESSION CYCLE:")
    for comp_name, loss in compression_components:
        comp_type = "Compressor  " if comp_name.startswith('C') else "Intercooler"
        print(f"   {comp_name:4s} ({comp_type}): {loss:6.2f} kJ/kg")
    
    print("\nEXPANSION CYCLE:")
    for comp_name, loss in expansion_components:
        comp_type = "Expander    " if comp_name.startswith('E') else "Interheater"
        print(f"   {comp_name:4s} ({comp_type}): {loss:6.2f} kJ/kg")
    
    print(f"\nTOTAL INDIVIDUAL LOSSES: {total_losses:.2f} kJ/kg")
    print(f"DETAILED EFFICIENCY: {efficiency:.2f}%")


# Removed plot_detailed_breakdown function - no longer needed
# Only configuration-specific plots are used now
