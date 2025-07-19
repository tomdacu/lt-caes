"""
Heat storage time simulation module.

This module provides the complete time-evolution analysis for the heat storage system,
including tank losses and daily power profiles.
"""

import config
import specifications
from utils.cycle_runner import run_cycle
from core import heat_storage, heat_transfer_losses
import numpy as np
import matplotlib.pyplot as plt
from CoolProp.CoolProp import PropsSI

def run_heat_storage_time_analysis():
    """
    Runs the heat storage time analysis with tank losses and daily power profile.
    """
    print("--- Running Heat Storage Time Analysis ---")
    
    # Initialize parameters
    water_mass_kg = heat_storage.calculate_water_mass()
    water_tank_temperature_c = config.INITIAL_WATER_TANK_T_C
    
    # Calculate time parameters
    time_step_seconds = config.TIME_STEP_MINUTES * 60
    total_steps = int(config.SIMULATION_DAYS * 24 * 60 / config.TIME_STEP_MINUTES)
    
    # Initialize data storage
    time_points = []
    temperatures = []
    energies = []
    heat_in_values = []
    heat_out_values = []
    losses_values = []
    
    # Calculate tank surface area for losses
    tank_surface_area = heat_transfer_losses.calculate_tank_surface_area(
        config.TANK_HEIGHT_M, config.TANK_DIAMETER_M
    )
    
    print(f"Simulating {config.SIMULATION_DAYS} days with {total_steps} time steps")
    print(f"Water mass: {water_mass_kg:.1f} kg")
    print(f"Tank surface area: {tank_surface_area:.2f} m²")
    
    # Main simulation loop
    for step in range(total_steps):
        # Calculate current time in hours
        current_time_hours = step * config.TIME_STEP_MINUTES / 60
        
        # Get power fraction for this time step
        daily_index = int((step * config.TIME_STEP_MINUTES) % (24 * 60)) // config.TIME_STEP_MINUTES
        power_fraction = config.POWER_FRACTION_PROFILE_DAILY[daily_index % len(config.POWER_FRACTION_PROFILE_DAILY)]
        
        # Calculate effective mass flow rate
        effective_mass_flow = config.NOMINAL_AIR_MASS_FLOW_RATE_KG_S * abs(power_fraction)
        
        # Initialize heat flows for this step
        heat_in_joules = 0.0
        heat_out_joules = 0.0
        
        # Calculate heat flows based on operation mode
        if power_fraction > 0:  # Charging
            # Run compression cycle
            initial_compression_state = {
                'P': config.COMPRESSOR_INLET_P_BAR * 1e5,
                'T': config.COMPRESSOR_INLET_T_C + 273.15,
                'H': PropsSI('H', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
                'S': PropsSI('S', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
            }
            compression_cycle_def = specifications.define_compression_cycle()
            compression_states, compression_work, _ = run_cycle(
                initial_compression_state, compression_cycle_def, config.COMPRESSOR_OUTLET_P_BAR * 1e5
            )
            
            # Calculate heat recovered from intercoolers
            specific_heat_recovered = 0.0
            for i, component in enumerate(compression_cycle_def):
                if component["type"] == "intercooler":
                    inlet_t = compression_states[i]['T']
                    outlet_t = compression_states[i+1]['T']
                    specific_heat_recovered += heat_storage.calculate_heat_recovered_from_intercooler(
                        inlet_t, outlet_t, config.FLUID
                    )
            
            heat_in_joules = specific_heat_recovered * effective_mass_flow * time_step_seconds
            
        elif power_fraction < 0:  # Discharging
            # Run expansion cycle
            initial_expansion_temp_c = water_tank_temperature_c - config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C
            initial_expansion_temp_c = max(initial_expansion_temp_c, config.T_AMBIENT_C)
            
            initial_expansion_state = {
                'P': config.STORAGE_PRESSURE_BAR * 1e5,
                'T': initial_expansion_temp_c + 273.15,
                'H': PropsSI('H', 'P', config.STORAGE_PRESSURE_BAR * 1e5, 'T', initial_expansion_temp_c + 273.15, config.FLUID),
                'S': PropsSI('S', 'P', config.STORAGE_PRESSURE_BAR * 1e5, 'T', initial_expansion_temp_c + 273.15, config.FLUID),
            }
            expansion_cycle_def = specifications.define_expansion_cycle()
            expansion_states, expansion_work, _ = run_cycle(
                initial_expansion_state, expansion_cycle_def, config.EXPANDER_OUTLET_P_BAR * 1e5
            )
            
            # Calculate heat supplied to expanders
            specific_heat_supplied = 0.0
            for i, component in enumerate(expansion_cycle_def):
                if component["type"] == "interheater":
                    specific_heat_supplied += heat_storage.calculate_heat_supplied_to_expander(
                        water_tank_temperature_c, config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C, config.FLUID
                    )
            
            heat_out_joules = specific_heat_supplied * effective_mass_flow * time_step_seconds
        
        # Calculate heat losses
        heat_loss_rate = heat_transfer_losses.calculate_total_heat_loss_rate(
            water_tank_temperature_c, config.T_AMBIENT_C
        )
        heat_loss_joules = heat_loss_rate * time_step_seconds
        
        # Update water tank temperature
        net_heat_change = heat_in_joules - heat_out_joules - heat_loss_joules
        water_tank_temperature_c = heat_storage.update_water_tank_temperature(
            net_heat_change, water_mass_kg, water_tank_temperature_c
        )
        
        # Store data
        time_points.append(current_time_hours)
        temperatures.append(water_tank_temperature_c)
        energies.append(heat_storage.get_total_energy_stored_joules(water_tank_temperature_c, water_mass_kg))
        heat_in_values.append(heat_in_joules)
        heat_out_values.append(heat_out_joules)
        losses_values.append(heat_loss_joules)
        
        # Progress update every 10 steps
        if step % 10 == 0:
            print(f"Step {step}/{total_steps}: T={water_tank_temperature_c:.1f}°C, Energy={energies[-1]/1e6:.2f} MJ")
    
    # Plot results
    print("\n--- Heat Storage Time Analysis Complete ---")
    print(f"Final water temperature: {water_tank_temperature_c:.2f}°C")
    print(f"Final energy stored: {energies[-1]/1e6:.2f} MJ")
    
    if config.SHOW_PLOTS:
        plot_heat_storage_results(time_points, temperatures, energies, heat_in_values, heat_out_values, losses_values)
    
    return {
        'time_points': time_points,
        'temperatures': temperatures,
        'energies': energies,
        'heat_in': heat_in_values,
        'heat_out': heat_out_values,
        'losses': losses_values
    }

def plot_heat_storage_results(time_points, temperatures, energies, heat_in, heat_out, losses):
    """
    Plots the results of the heat storage time analysis.
    
    Args:
        time_points (list): Time points in hours
        temperatures (list): Water tank temperatures in Celsius
        energies (list): Total energy stored in Joules
        heat_in (list): Heat input in Joules per step
        heat_out (list): Heat output in Joules per step
        losses (list): Heat losses in Joules per step
    """
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
    
    # Plot 1: Water tank temperature vs time
    ax1.plot(time_points, temperatures, 'b-', linewidth=2)
    ax1.set_xlabel('Time [hours]')
    ax1.set_ylabel('Water Tank Temperature [°C]')
    ax1.set_title('Water Tank Temperature Profile')
    ax1.grid(True)
    
    # Plot 2: Total energy stored vs time
    ax2.plot(time_points, [e/1e6 for e in energies], 'g-', linewidth=2)
    ax2.set_xlabel('Time [hours]')
    ax2.set_ylabel('Total Energy Stored [MJ]')
    ax2.set_title('Energy Storage Profile')
    ax2.grid(True)
    
    # Plot 3: Power flows vs time
    time_hours = np.array(time_points)
    heat_in_power = np.array(heat_in) / (config.TIME_STEP_MINUTES * 60)
    heat_out_power = np.array(heat_out) / (config.TIME_STEP_MINUTES * 60)
    losses_power = np.array(losses) / (config.TIME_STEP_MINUTES * 60)
    
    ax3.plot(time_hours, heat_in_power/1000, 'r-', label='Heat In', linewidth=2)
    ax3.plot(time_hours, heat_out_power/1000, 'b-', label='Heat Out', linewidth=2)
    ax3.plot(time_hours, losses_power/1000, 'k-', label='Losses', linewidth=2)
    ax3.set_xlabel('Time [hours]')
    ax3.set_ylabel('Power [kW]')
    ax3.set_title('Power Flows')
    ax3.legend()
    ax3.grid(True)
    
    # Plot 4: Cumulative energy flows
    cumulative_heat_in = np.cumsum(heat_in) / 1e6
    cumulative_heat_out = np.cumsum(heat_out) / 1e6
    cumulative_losses = np.cumsum(losses) / 1e6
    
    ax4.plot(time_hours, cumulative_heat_in, 'r-', label='Cumulative Heat In', linewidth=2)
    ax4.plot(time_hours, cumulative_heat_out, 'b-', label='Cumulative Heat Out', linewidth=2)
    ax4.plot(time_hours, cumulative_losses, 'k-', label='Cumulative Losses', linewidth=2)
    ax4.set_xlabel('Time [hours]')
    ax4.set_ylabel('Cumulative Energy [MJ]')
    ax4.set_title('Cumulative Energy Flows')
    ax4.legend()
    ax4.grid(True)
    
    plt.tight_layout()
    plt.show()
