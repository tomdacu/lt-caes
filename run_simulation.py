"""
CAES Plant Simulation Runner
===========================

This script runs simulations based on the configuration in dashboard.py.
It provides all analysis types: normal operation, parametric studies, and time evolution.
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import csv
import os

# Import dashboard configuration
from dashboard import *

# Import existing modules
from data_models import PlantConfig
from plant import Plant
from plotting import plot_thermodynamic_cycles
from analysis.exergetic_analysis import calculate_exergy_efficiency, run_exergetic_analysis

def create_plant_config():
    """Create PlantConfig from dashboard settings."""
    return PlantConfig(
        # Basic configuration
        heat_storage_enabled=HEAT_STORAGE_ENABLED,
        stages_compressor=COMPRESSOR_STAGES,
        stages_expander=EXPANDER_STAGES,
        
        # Operating conditions
        T_ambient_C=AMBIENT_TEMPERATURE_C,
        P_ambient_bar=AMBIENT_PRESSURE_BAR,
        P_storage_bar=STORAGE_PRESSURE_BAR,
        
        # Component efficiencies
        eta_compressor=COMPRESSOR_EFFICIENCY,
        eta_expander=EXPANDER_EFFICIENCY,
        
        # Heat exchange
        delta_T_ambient=DELTA_T_AMBIENT,
        heat_exchange_approach_temp=HEAT_EXCHANGE_APPROACH_TEMP,
        turbine_inlet_delta_T=TURBINE_INLET_DELTA_T,
        
        # Pressure drops
        intercooler_pressure_drop=INTERCOOLER_PRESSURE_DROP,
        interheater_pressure_drop=INTERHEATER_PRESSURE_DROP,
        
        # Heat storage (when enabled)
        tank_volume_m3=WATER_TANK_VOLUME_M3,
        tank_height_m=TANK_HEIGHT_M,
        tank_diameter_m=TANK_DIAMETER_M,
        insulation_thickness_m=INSULATION_THICKNESS_M,
        insulation_conductivity=INSULATION_CONDUCTIVITY,
        
        # Time evolution parameters
        nominal_mass_flow_kg_s=NOMINAL_MASS_FLOW_KG_S
    )

def print_results_header(analysis_type):
    """Print formatted header for results."""
    print("\n" + "="*80)
    print(f"🔋 CAES PLANT SIMULATION RESULTS - {analysis_type.upper()}")
    print("="*80)
    print(f"⏰ Simulation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🏭 Heat Storage: {'✅ ENABLED (A-CAES)' if HEAT_STORAGE_ENABLED else '❌ DISABLED (D-CAES)'}")
    print(f"⚙️  Compression/Expansion Stages: {COMPRESSOR_STAGES}/{EXPANDER_STAGES}")
    print(f"🌡️  Ambient Temperature: {AMBIENT_TEMPERATURE_C}°C")
    print(f"📊 Storage Pressure: {STORAGE_PRESSURE_BAR} bar")
    print("-"*80)

def print_efficiency_results(results, config_name="Plant"):
    """Print efficiency results in a formatted way."""
    efficiency = results.round_trip_efficiency * 100
    
    print(f"\n📈 {config_name} PERFORMANCE:")
    print(f"   ⚡ Overall Efficiency: {efficiency:.2f}%")
    print(f"   🔥 Compression Work: {results.charging_results.total_work_specific/1000:.1f} kJ/kg")
    print(f"   🔌 Expansion Work: {-results.discharging_results.total_work_specific/1000:.1f} kJ/kg")
    
    # Get average compression outlet temperature
    compression_states = results.charging_results.all_states
    if len(compression_states) > 2:
        compression_outlets = compression_states[1::2]  # Every other state starting from index 1
        avg_temp = sum(state.t for state in compression_outlets) / len(compression_outlets)
        print(f"   🌡️  Average Compression Outlet: {avg_temp-273.15:.1f}°C")
    
    if results.hot_water_temperature_c is not None:
        print(f"   🏺 Hot Water Tank Temperature: {results.hot_water_temperature_c:.1f}°C")

def run_normal_analysis():
    """Run single plant configuration analysis."""
    print_results_header("Normal Operation")
    
    config = create_plant_config()
    plant = Plant(config)
    
    print("🔄 Running simulation...")
    results = plant.run_complete_simulation()
    
    print_efficiency_results(results)
    
    # Show exergy analysis
    if SHOW_EXERGY_ANALYSIS and SHOW_EXERGY_DIAGRAM:
        try:
            print("\n🔬 DETAILED EXERGY ANALYSIS:")
            compression_states_dict = [{'H': s.h, 'S': s.s, 'T': s.t, 'P': s.p} for s in results.charging_results.all_states]
            expansion_states_dict = [{'H': s.h, 'S': s.s, 'T': s.t, 'P': s.p} for s in results.discharging_results.all_states]
            
            run_exergetic_analysis(
                compression_states_dict,
                expansion_states_dict, 
                results.charging_results.process_types,
                results.discharging_results.process_types,
                results.hot_water_temperature_c
            )
            
        except Exception as e:
            print(f"   ⚠️  Exergy analysis failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Show thermodynamic plots
    if SHOW_PLOTS:
        print("\n📊 Generating thermodynamic cycle plots...")
        try:
            compression_states_dict = [{'H': s.h, 'S': s.s, 'T': s.t, 'P': s.p} for s in results.charging_results.all_states]
            expansion_states_dict = [{'H': s.h, 'S': s.s, 'T': s.t, 'P': s.p} for s in results.discharging_results.all_states]
            
            plot_thermodynamic_cycles(
                compression_states_dict,
                expansion_states_dict, 
                results.charging_results.process_types,
                results.discharging_results.process_types,
                'air'
            )
        except Exception as e:
            print(f"   ⚠️  Plotting failed: {e}")
    
    # Save results
    if SAVE_RESULTS_TO_FILE:
        save_single_result(results, config)
    
    return results

def run_comparison_analysis():
    """Compare plant with and without heat storage."""
    print_results_header("Heat Storage Comparison")
    
    # Configuration without heat storage
    config_no_hs = create_plant_config()
    config_no_hs.heat_storage_enabled = False
    plant_no_hs = Plant(config_no_hs)
    
    # Configuration with heat storage  
    config_with_hs = create_plant_config()
    config_with_hs.heat_storage_enabled = True
    plant_with_hs = Plant(config_with_hs)
    
    print("🔄 Running D-CAES simulation (no heat storage)...")
    results_no_hs = plant_no_hs.run_complete_simulation()
    
    print("🔄 Running A-CAES simulation (with heat storage)...")
    results_with_hs = plant_with_hs.run_complete_simulation()
    
    print_efficiency_results(results_no_hs, "D-CAES (No Heat Storage)")
    print_efficiency_results(results_with_hs, "A-CAES (With Heat Storage)")
    
    # Calculate improvement
    improvement = (results_with_hs.round_trip_efficiency - results_no_hs.round_trip_efficiency) * 100
    print(f"\n🚀 IMPROVEMENT WITH HEAT STORAGE:")
    print(f"   📈 Efficiency Gain: +{improvement:.2f} percentage points")
    print(f"   🔢 Relative Improvement: {improvement/results_no_hs.round_trip_efficiency:.1%}")
    
    if SAVE_RESULTS_TO_FILE:
        save_comparison_results(results_no_hs, results_with_hs)
    
    return results_no_hs, results_with_hs

def run_parametric_analysis(parameter_type):
    """Run parametric analysis varying specified parameter."""
    print_results_header(f"Parametric Analysis - {parameter_type}")
    
    # Define parameter ranges and labels
    param_ranges = {
        'stages': (STAGES_RANGE, 'Number of Stages', 'stages'),
        'delta_t': (DELTA_T_RANGE, 'Temperature Difference [°C]', 'delta_T_ambient'),
        'efficiency': (EFFICIENCY_RANGE, 'Component Efficiency', 'eta_compressor'),
        'pressure': (PRESSURE_DROP_RANGE, 'Pressure Drop [fraction]', 'intercooler_pressure_drop'),
        'ambient': (AMBIENT_TEMP_RANGE, 'Ambient Temperature [°C]', 'T_ambient_C')
    }
    
    if parameter_type not in param_ranges:
        print(f"❌ Unknown parameter type: {parameter_type}")
        return
    
    values, label, attr_name = param_ranges[parameter_type]
    results = []
    
    print(f"🔄 Running parametric study: {label}")
    print(f"📊 Testing {len(values)} different values...")
    
    for i, value in enumerate(values):
        config = create_plant_config()
        
        # Set the parameter value
        if parameter_type == 'stages':
            config.stages_compressor = value
            config.stages_expander = value
        elif parameter_type == 'efficiency':
            config.eta_compressor = value
            config.eta_expander = value
        elif parameter_type == 'pressure':
            config.intercooler_pressure_drop = value
            config.interheater_pressure_drop = value
        else:
            setattr(config, attr_name, value)
        
        try:
            plant = Plant(config)
            result = plant.run_complete_simulation()
            efficiency = result.round_trip_efficiency * 100
            results.append((value, efficiency))
            print(f"   ✅ {label}: {value:6.2f} → Efficiency: {efficiency:5.2f}%")
        except Exception as e:
            print(f"   ❌ {label}: {value:6.2f} → Error: {e}")
            results.append((value, 0))
    
    # Plot results
    if SHOW_PLOTS and results:
        plot_parametric_results(results, label, parameter_type)
    
    if SAVE_RESULTS_TO_FILE:
        save_parametric_results(results, parameter_type, label)
    
    return results

def run_time_evolution_analysis():
    """Run time-varying analysis for heat storage system."""
    print_results_header("Time Evolution Analysis")
    
    if not HEAT_STORAGE_ENABLED:
        print("❌ Time evolution analysis requires heat storage to be enabled!")
        return
    
    config = create_plant_config()
    plant = Plant(config)
    
    print(f"🔄 Running {SIMULATION_DAYS}-day simulation...")
    print(f"⏱️  Time step: {TIME_STEP_MINUTES} minutes")
    print(f"💨 Nominal mass flow: {NOMINAL_MASS_FLOW_KG_S} kg/s")
    
    # Calculate time points
    minutes_per_day = 24 * 60
    time_steps_per_day = minutes_per_day // TIME_STEP_MINUTES
    total_time_steps = SIMULATION_DAYS * time_steps_per_day
    
    # Initialize storage
    time_points = []
    tank_temperatures = []
    efficiencies = []
    power_levels = []
    
    # Initial tank temperature
    current_tank_temp = config.T_ambient_C + 273.15  # Start at ambient
    
    for day in range(SIMULATION_DAYS):
        for step in range(time_steps_per_day):
            current_time = day * minutes_per_day + step * TIME_STEP_MINUTES
            time_points.append(current_time / 60)  # Convert to hours
            
            # Get power level from daily profile
            profile_index = step % len(DAILY_POWER_PROFILE)
            power_fraction = DAILY_POWER_PROFILE[profile_index]
            power_levels.append(power_fraction)
            
            # Update tank temperature based on operation
            if power_fraction > 0:  # Charging
                # Heat is stored from compression
                temp_rise = power_fraction * 10  # Simplified model
                current_tank_temp += temp_rise * TIME_STEP_MINUTES / 60
            elif power_fraction < 0:  # Discharging  
                # Heat is extracted for expansion
                temp_drop = abs(power_fraction) * 8  # Simplified model
                current_tank_temp -= temp_drop * TIME_STEP_MINUTES / 60
            else:
                # Idle - heat losses
                temp_loss = 0.1 * TIME_STEP_MINUTES / 60
                current_tank_temp -= temp_loss
            
            # Prevent tank temperature from going below ambient
            current_tank_temp = max(current_tank_temp, config.T_ambient_C + 273.15)
            tank_temperatures.append(current_tank_temp - 273.15)  # Store in °C
            
            # Calculate instantaneous efficiency (simplified)
            if abs(power_fraction) > 0.01:
                temp_benefit = min((current_tank_temp - 273.15 - config.T_ambient_C) / 50, 0.15)
                base_efficiency = 0.67  # Base efficiency without heat storage
                efficiency = (base_efficiency + temp_benefit) * 100
            else:
                efficiency = 0  # No operation
            
            efficiencies.append(efficiency)
    
    # Print summary
    avg_efficiency = np.mean([e for e in efficiencies if e > 0])
    max_tank_temp = max(tank_temperatures)
    min_tank_temp = min(tank_temperatures)
    
    print(f"\n📊 TIME EVOLUTION RESULTS:")
    print(f"   ⚡ Average Operating Efficiency: {avg_efficiency:.2f}%")
    print(f"   🌡️  Tank Temperature Range: {min_tank_temp:.1f}°C - {max_tank_temp:.1f}°C")
    print(f"   🔄 Total Charge/Discharge Cycles: {sum(1 for p in power_levels if abs(p) > 0.5)}")
    
    # Plot time evolution
    if SHOW_PLOTS:
        plot_time_evolution(time_points, tank_temperatures, efficiencies, power_levels)
    
    if SAVE_RESULTS_TO_FILE:
        save_time_evolution_results(time_points, tank_temperatures, efficiencies, power_levels)
    
    return time_points, tank_temperatures, efficiencies, power_levels

def plot_parametric_results(results, xlabel, parameter_type):
    """Plot parametric analysis results."""
    if PLOT_STYLE != "default":
        plt.style.use(PLOT_STYLE)
    
    values, efficiencies = zip(*results)
    
    plt.figure(figsize=FIGURE_SIZE)
    plt.plot(values, efficiencies, 'bo-', linewidth=2, markersize=8)
    plt.grid(True, alpha=0.3)
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel('Overall Efficiency [%]', fontsize=12)
    plt.title(f'Parametric Analysis: {xlabel}', fontsize=14, fontweight='bold')
    
    # Add best efficiency annotation
    best_idx = np.argmax(efficiencies)
    best_value, best_eff = values[best_idx], efficiencies[best_idx]
    plt.annotate(f'Best: {best_eff:.2f}% at {best_value}',
                xy=(best_value, best_eff), xytext=(10, 10),
                textcoords='offset points', fontsize=10,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
    
    plt.tight_layout()
    plt.show()

def plot_time_evolution(time_points, temperatures, efficiencies, power_levels):
    """Plot time evolution results."""
    if PLOT_STYLE != "default":
        plt.style.use(PLOT_STYLE)
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
    
    # Tank temperature
    ax1.plot(time_points, temperatures, 'r-', linewidth=2)
    ax1.set_xlabel('Time [hours]')
    ax1.set_ylabel('Tank Temperature [°C]')
    ax1.set_title('Hot Water Tank Temperature')
    ax1.grid(True, alpha=0.3)
    
    # Efficiency
    efficiency_nonzero = [e if e > 0 else np.nan for e in efficiencies]
    ax2.plot(time_points, efficiency_nonzero, 'g-', linewidth=2)
    ax2.set_xlabel('Time [hours]')
    ax2.set_ylabel('Efficiency [%]')
    ax2.set_title('Instantaneous Efficiency')
    ax2.grid(True, alpha=0.3)
    
    # Power profile
    colors = ['red' if p > 0 else 'blue' if p < 0 else 'gray' for p in power_levels]
    ax3.bar(time_points, power_levels, width=TIME_STEP_MINUTES/60, color=colors, alpha=0.7)
    ax3.set_xlabel('Time [hours]')
    ax3.set_ylabel('Power Level [fraction]')
    ax3.set_title('Power Profile (Red=Charge, Blue=Discharge)')
    ax3.grid(True, alpha=0.3)
    
    # Temperature vs Efficiency scatter
    temp_nonzero = [temperatures[i] for i, e in enumerate(efficiencies) if e > 0]
    eff_nonzero = [e for e in efficiencies if e > 0]
    ax4.scatter(temp_nonzero, eff_nonzero, alpha=0.6, c='purple')
    ax4.set_xlabel('Tank Temperature [°C]')
    ax4.set_ylabel('Efficiency [%]')
    ax4.set_title('Efficiency vs Tank Temperature')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()

def save_single_result(results, config):
    """Save single simulation results to CSV with both results and input parameters."""
    # Create results directory if it doesn't exist
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)
    
    filename = os.path.join(results_dir, "normal_analysis.csv")
    
    # Check if file exists to determine if we need headers
    file_exists = os.path.exists(filename)
    
    with open(filename, 'a', newline='') as file:
        writer = csv.writer(file)
        
        # Write headers if file is new
        if not file_exists:
            writer.writerow([
                # Results columns
                'Timestamp', 'Plant_Type', 'Overall_Efficiency_%', 'Compression_Work_kJ/kg', 
                'Expansion_Work_kJ/kg', 'Hot_Water_Temp_C', 'Cold_Water_Temp_C',
                # Input parameters columns  
                'Heat_Storage_Enabled', 'Compressor_Stages', 'Expander_Stages',
                'Ambient_Temp_C', 'Storage_Pressure_bar', 'Compressor_Efficiency',
                'Expander_Efficiency', 'Delta_T_Ambient_C', 'Heat_Exchange_Approach_C',
                'Intercooler_Pressure_Drop', 'Interheater_Pressure_Drop'
            ])
        
        # Write data row
        plant_type = "A-CAES" if config.heat_storage_enabled else "D-CAES"
        writer.writerow([
            # Results
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            plant_type,
            f"{results.round_trip_efficiency * 100:.2f}",
            f"{results.charging_results.total_work_specific/1000:.1f}",
            f"{-results.discharging_results.total_work_specific/1000:.1f}",
            f"{results.hot_water_temperature_c:.1f}" if results.hot_water_temperature_c else "",
            f"{results.cold_water_temperature_c:.1f}" if results.cold_water_temperature_c else "",
            # Input parameters
            config.heat_storage_enabled,
            config.stages_compressor,
            config.stages_expander,
            config.T_ambient_C,
            config.P_storage_bar,
            config.eta_compressor,
            config.eta_expander,
            config.delta_T_ambient,
            config.heat_exchange_approach_temp,
            config.intercooler_pressure_drop,
            config.interheater_pressure_drop
        ])
    
    print(f"💾 Results saved to: {filename}")

def save_comparison_results(results_no_hs, results_with_hs):
    """Save comparison results to CSV with both configurations."""
    # Create results directory if it doesn't exist
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)
    
    filename = os.path.join(results_dir, "comparison_analysis.csv")
    
    # Check if file exists to determine if we need headers
    file_exists = os.path.exists(filename)
    
    with open(filename, 'a', newline='') as file:
        writer = csv.writer(file)
        
        # Write headers if file is new
        if not file_exists:
            writer.writerow([
                # Results columns
                'Timestamp', 'D-CAES_Efficiency_%', 'A-CAES_Efficiency_%', 'Improvement_%',
                'D-CAES_Compression_Work_kJ/kg', 'A-CAES_Compression_Work_kJ/kg',
                'D-CAES_Expansion_Work_kJ/kg', 'A-CAES_Expansion_Work_kJ/kg',
                'A-CAES_Hot_Water_Temp_C',
                # Input parameters columns
                'Compressor_Stages', 'Storage_Pressure_bar', 'Ambient_Temp_C',
                'Compressor_Efficiency', 'Expander_Efficiency'
            ])
        
        # Calculate values
        d_caes_eff = results_no_hs.round_trip_efficiency * 100
        a_caes_eff = results_with_hs.round_trip_efficiency * 100
        improvement = a_caes_eff - d_caes_eff
        
        # Write data row
        writer.writerow([
            # Results
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            f"{d_caes_eff:.2f}",
            f"{a_caes_eff:.2f}",
            f"{improvement:.2f}",
            f"{results_no_hs.charging_results.total_work_specific/1000:.1f}",
            f"{results_with_hs.charging_results.total_work_specific/1000:.1f}",
            f"{-results_no_hs.discharging_results.total_work_specific/1000:.1f}",
            f"{-results_with_hs.discharging_results.total_work_specific/1000:.1f}",
            f"{results_with_hs.hot_water_temperature_c:.1f}" if results_with_hs.hot_water_temperature_c else "",
            # Input parameters (use current dashboard values)
            COMPRESSOR_STAGES,
            STORAGE_PRESSURE_BAR,
            AMBIENT_TEMPERATURE_C,
            COMPRESSOR_EFFICIENCY,
            EXPANDER_EFFICIENCY
        ])
    
    print(f"💾 Comparison results saved to: {filename}")

def save_parametric_results(results, parameter_type, label):
    """Save parametric results to CSV with all parameter values and efficiencies."""
    # Create results directory if it doesn't exist
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)
    
    filename = os.path.join(results_dir, f"parametric_{parameter_type}.csv")
    
    with open(filename, 'w', newline='') as file:
        writer = csv.writer(file)
        
        # Write headers
        writer.writerow([
            'Timestamp', 'Parameter_Value', 'Parameter_Label', 'Efficiency_%',
            # Input parameters (constant for this analysis)
            'Heat_Storage_Enabled', 'Base_Compressor_Stages', 'Base_Storage_Pressure_bar',
            'Base_Ambient_Temp_C', 'Base_Compressor_Efficiency', 'Base_Expander_Efficiency'
        ])
        
        # Write all results
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for value, efficiency in results:
            writer.writerow([
                timestamp,
                value,
                label,
                f"{efficiency:.2f}",
                # Base parameters
                HEAT_STORAGE_ENABLED,
                COMPRESSOR_STAGES,
                STORAGE_PRESSURE_BAR,
                AMBIENT_TEMPERATURE_C,
                COMPRESSOR_EFFICIENCY,
                EXPANDER_EFFICIENCY
            ])
    
    print(f"💾 Parametric results saved to: {filename}")

def save_time_evolution_results(time_points, temperatures, efficiencies, power_levels):
    """Save time evolution results to CSV with detailed time-series data."""
    # Create results directory if it doesn't exist
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)
    
    filename = os.path.join(results_dir, "time_evolution.csv")
    
    with open(filename, 'w', newline='') as file:
        writer = csv.writer(file)
        
        # Write headers
        writer.writerow([
            'Timestamp', 'Simulation_Time_hours', 'Tank_Temperature_C', 
            'Efficiency_%', 'Power_Level_fraction',
            # Configuration parameters (constant for this analysis)
            'Simulation_Days', 'Time_Step_minutes', 'Nominal_Mass_Flow_kg/s',
            'Tank_Volume_m3', 'Heat_Storage_Enabled'
        ])
        
        # Write all time points
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for i, (time_h, temp, eff, power) in enumerate(zip(time_points, temperatures, efficiencies, power_levels)):
            writer.writerow([
                timestamp,
                f"{time_h:.2f}",
                f"{temp:.1f}",
                f"{eff:.2f}" if eff > 0 else "0.00",
                f"{power:.3f}",
                # Configuration
                SIMULATION_DAYS,
                TIME_STEP_MINUTES,
                NOMINAL_MASS_FLOW_KG_S,
                WATER_TANK_VOLUME_M3,
                HEAT_STORAGE_ENABLED
            ])
    
    print(f"💾 Time evolution results saved to: {filename}")

def main():
    """Main simulation runner."""
    print("🚀 CAES Plant Simulation Starting...")
    print(f"📋 Analysis Type: {ANALYSIS_TYPE}")
    
    # Set matplotlib style
    if PLOT_STYLE != "default":
        try:
            plt.style.use(PLOT_STYLE)
        except:
            print(f"⚠️  Could not set plot style '{PLOT_STYLE}', using default")
    
    # Route to appropriate analysis
    try:
        if ANALYSIS_TYPE == "normal":
            run_normal_analysis()
            
        elif ANALYSIS_TYPE == "comparison":
            run_comparison_analysis()
            
        elif ANALYSIS_TYPE.startswith("parametric_"):
            param_type = ANALYSIS_TYPE.replace("parametric_", "")
            run_parametric_analysis(param_type)
            
        elif ANALYSIS_TYPE == "time_evolution":
            run_time_evolution_analysis()
            
        else:
            print(f"❌ Unknown analysis type: {ANALYSIS_TYPE}")
            print("Available types: normal, comparison, parametric_stages, parametric_delta_t,")
            print("                parametric_efficiency, parametric_pressure, parametric_ambient, time_evolution")
            return
            
    except Exception as e:
        print(f"❌ Simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n✅ Simulation completed successfully!")
    print("💡 Tip: Modify parameters in dashboard.py and run again to explore different configurations.")

if __name__ == "__main__":
    main()
