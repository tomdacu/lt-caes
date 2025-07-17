"""
This module provides functions for visualizing the thermodynamic cycles of the CAES plant.
"""

import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram
import numpy as np
import config # Import config to access ambient temperature

def _plot_process(diagram, ax, diagram_type, states, process_type, **kwargs):
    """Helper function to plot a single process on a diagram."""
    # Convert state properties to the units required by fluprodia
    start_state = {
        'p': states[0]['P'] / 1e5,  # bar
        'T': states[0]['T'] - 273.15, # °C
        'h': states[0]['H'] / 1e3, # kJ/kg
        's': states[0]['S'] / 1e3 # kJ/kgK
    }
    end_state = {
        'p': states[1]['P'] / 1e5, # bar
        'T': states[1]['T'] - 273.15, # °C
        'h': states[1]['H'] / 1e3, # kJ/kg
        's': states[1]['S'] / 1e3 # kJ/kgK
    }

    # Define the process based on its type
    if process_type in ['compressor', 'expander']:
        # Isentropic process
        data = {
            'isoline_property': 's',
            'isoline_value': start_state['s'],
            'isoline_value_end': end_state['s'],
            'starting_point_property': 'p',
            'starting_point_value': start_state['p'],
            'ending_point_property': 'p',
            'ending_point_value': end_state['p']
        }
    else: # intercooler, interheater
        # Isobaric process
        data = {
            'isoline_property': 'p',
            'isoline_value': start_state['p'],
            'isoline_value_end': end_state['p'], # Account for pressure drop
            'starting_point_property': 'T',
            'starting_point_value': start_state['T'],
            'ending_point_property': 'T',
            'ending_point_value': end_state['T']
        }

    datapoints = diagram.calc_individual_isoline(**data)
    
    # Get the correct x and y properties from the diagram type string
    x_key = diagram_type[1]
    y_key = diagram_type[0] # Corrected: Removed .lower()
    
    # For logph diagram, pressure is 'p' and enthalpy is 'h'
    if diagram_type == 'logph':
        y_key = 'p'
        x_key = 'h'

    ax.plot(datapoints[x_key], datapoints[y_key], **kwargs)

def plot_thermodynamic_cycles(compression_states, expansion_states, compression_processes, expansion_processes, fluid_name):
    """
    Plots T-s, h-s, and P-h diagrams for the CAES cycle, each in a separate window.
    """
    
    color_map = {
        'compressor': 'green',
        'intercooler': 'blue',
        'expander': 'purple',
        'interheater': 'red',
    }

    all_states = compression_states + expansion_states
    
    # Determine plot limits dynamically from all states
    s_all = [s['S']/1e3 for s in all_states] # kJ/kgK
    t_all = [s['T']-273.15 for s in all_states] # C
    h_all = [s['H']/1e3 for s in all_states] # kJ/kg
    p_all = [s['P']/1e5 for s in all_states] # bar

    s_min, s_max = min(s_all), max(s_all)
    t_min, t_max = min(t_all), max(t_all)
    h_min, h_max = min(h_all), max(h_all)
    p_min, p_max = min(p_all), max(p_all)
    
    margin_s = (s_max - s_min) * 0.1
    margin_t = (t_max - t_min) * 0.1
    margin_h = (h_max - h_min) * 0.1

    # --- Calculate Ambient Isotherm Data ---
    isotherm_diagram = FluidPropertyDiagram(fluid_name)
    isotherm_diagram.set_unit_system(T='°C', p='bar', h='kJ/kg', s='kJ/kgK')
    isotherm_data = isotherm_diagram.calc_individual_isoline(
        isoline_property='T',
        isoline_value=config.T_AMBIENT_C,
        starting_point_property='p',
        starting_point_value=p_min, # Start at ambient pressure
        ending_point_property='p',
        ending_point_value=p_max    # End at max cycle pressure
    )
    isotherm_label = f'Ambient Temp ({config.T_AMBIENT_C}°C)'

    # --- T-s Diagram ---
    ts_diagram = FluidPropertyDiagram(fluid_name)
    ts_diagram.set_unit_system(T='°C', p='bar', h='kJ/kg', s='kJ/kgK')
    ts_diagram.calc_isolines()
    fig, ax = plt.subplots(1, figsize=(12, 8)) # Smaller figure size
    ts_diagram.draw_isolines(fig, ax, 'Ts', x_min=s_min-margin_s, x_max=s_max+margin_s, y_min=t_min-margin_t, y_max=t_max+margin_t)

    # Plot ambient temperature isotherm
    ax.plot(isotherm_data['s'], isotherm_data['T'], 'k--', label=isotherm_label, linewidth=0.75)

    for i in range(len(compression_processes)):
        _plot_process(ts_diagram, ax, 'Ts', [compression_states[i], compression_states[i+1]], compression_processes[i], color=color_map[compression_processes[i]], label=compression_processes[i].capitalize())
    for i in range(len(expansion_processes)):
        _plot_process(ts_diagram, ax, 'Ts', [expansion_states[i], expansion_states[i+1]], expansion_processes[i], color=color_map[expansion_processes[i]], label=expansion_processes[i].capitalize())
    
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys())
    ax.set_title('T-s Diagram')
    plt.show()

    # --- h-s Diagram ---
    hs_diagram = FluidPropertyDiagram(fluid_name)
    hs_diagram.set_unit_system(T='°C', p='bar', h='kJ/kg', s='kJ/kgK')
    hs_diagram.calc_isolines()
    fig, ax = plt.subplots(1, figsize=(10, 6)) # Smaller figure size
    hs_diagram.draw_isolines(fig, ax, 'hs', x_min=s_min-margin_s, x_max=s_max+margin_s, y_min=h_min-margin_h, y_max=h_max+margin_h)

    # Plot ambient temperature isotherm
    ax.plot(isotherm_data['s'], isotherm_data['h'], 'k--', label=isotherm_label, linewidth=0.75)

    for i in range(len(compression_processes)):
        _plot_process(hs_diagram, ax, 'hs', [compression_states[i], compression_states[i+1]], compression_processes[i], color=color_map[compression_processes[i]], label=compression_processes[i].capitalize())
    for i in range(len(expansion_processes)):
        _plot_process(hs_diagram, ax, 'hs', [expansion_states[i], expansion_states[i+1]], expansion_processes[i], color=color_map[expansion_processes[i]], label=expansion_processes[i].capitalize())

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys())
    ax.set_title('h-s Diagram')
    plt.show()

    # --- P-h Diagram ---
    ph_diagram = FluidPropertyDiagram(fluid_name)
    ph_diagram.set_unit_system(T='°C', p='bar', h='kJ/kg', s='kJ/kgK')
    ph_diagram.calc_isolines()
    fig, ax = plt.subplots(1, figsize=(10, 6)) # Smaller figure size
    ph_diagram.draw_isolines(fig, ax, 'logph', x_min=h_min-margin_h, x_max=h_max+margin_h, y_min=p_min*0.9, y_max=p_max*1.1)

    # Plot ambient temperature isotherm
    ax.plot(isotherm_data['h'], isotherm_data['p'], 'k--', label=isotherm_label, linewidth=0.75)

    for i in range(len(compression_processes)):
        _plot_process(ph_diagram, ax, 'logph', [compression_states[i], compression_states[i+1]], compression_processes[i], color=color_map[compression_processes[i]], label=compression_processes[i].capitalize())
    for i in range(len(expansion_processes)):
        _plot_process(ph_diagram, ax, 'logph', [expansion_states[i], expansion_states[i+1]], expansion_processes[i], color=color_map[expansion_processes[i]], label=expansion_processes[i].capitalize())
    
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys())
    ax.set_title('P-h Diagram')
    plt.show()
