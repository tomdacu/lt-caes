"""
Parametric analysis module for the CAES plant simulator.

This script runs parametric studies based on the settings in `config.py`.
It analyzes the effect of varying key parameters on the plant's round-trip efficiency.
"""

import matplotlib.pyplot as plt
import config
import specifications
from main import run_cycle
from CoolProp.CoolProp import PropsSI

def run_simulation_for_efficiency(params_override={}):
    """
    Runs a single CAES simulation with overridden parameters and returns the round-trip efficiency.
    This is a simplified version of the main function, focused on returning a single value
    without generating plots for each run.
    """
    # Override config values for this specific run
    original_values = {}
    for key, value in params_override.items():
        if hasattr(config, key):
            original_values[key] = getattr(config, key)
            setattr(config, key, value)
        # Special handling for DELTA_T as it affects two other parameters
        if key == 'DELTA_T':
            original_values['INTERCOOLER_OUTLET_T_C'] = config.INTERCOOLER_OUTLET_T_C
            original_values['INTERHEATER_OUTLET_T_C'] = config.INTERHEATER_OUTLET_T_C
            setattr(config, 'INTERCOOLER_OUTLET_T_C', config.T_AMBIENT_C + value)
            setattr(config, 'INTERHEATER_OUTLET_T_C', config.T_AMBIENT_C - value)


    # --- Compression Cycle ---
    initial_compression_state = {
        'P': config.COMPRESSOR_INLET_P_BAR * 1e5,
        'T': config.COMPRESSOR_INLET_T_C + 273.15,
        'H': PropsSI('H', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
        'S': PropsSI('S', 'P', config.COMPRESSOR_INLET_P_BAR * 1e5, 'T', config.COMPRESSOR_INLET_T_C + 273.15, config.FLUID),
    }
    compression_cycle_def = specifications.define_compression_cycle()
    _, compression_work, _ = run_cycle(
        initial_compression_state, compression_cycle_def, config.COMPRESSOR_OUTLET_P_BAR * 1e5
    )

    # --- Expansion Cycle ---
    initial_expansion_state = {
        'P': config.STORAGE_PRESSURE_BAR * 1e5,
        'T': config.T_AMBIENT_C + config.ZERO_C,
        'H': PropsSI('H', 'P', config.STORAGE_PRESSURE_BAR * 1e5, 'T', config.T_AMBIENT_C + config.ZERO_C, config.FLUID),
        'S': PropsSI('S', 'P', config.STORAGE_PRESSURE_BAR * 1e5, 'T', config.T_AMBIENT_C + config.ZERO_C, config.FLUID),
    }
    expansion_cycle_def = specifications.define_expansion_cycle()
    _, expansion_work, expansion_heat_added = run_cycle(
        initial_expansion_state, expansion_cycle_def, config.EXPANDER_OUTLET_P_BAR * 1e5
    )

    # --- Efficiency Calculation ---
    round_trip_efficiency = -expansion_work / (compression_work) if (compression_work) > 0 else 0

    # Restore original config values to avoid side effects
    for key, value in original_values.items():
        setattr(config, key, value)

    return round_trip_efficiency

def analyze_stages():
    """
    Performs a parametric analysis on the number of compressor/expander stages.
    """
    print("--- Running Parametric Analysis: Number of Stages ---")
    efficiencies = []
    stages_range = config.STAGES_RANGE
    for stages in stages_range:
        print(f"Analyzing for {stages} stages...")
        params = {
            "COMPRESSOR_STAGES": stages,
            "EXPANDER_STAGES": stages
        }
        eff = run_simulation_for_efficiency(params)
        efficiencies.append(eff)

    # Plotting results
    plt.figure(figsize=(10, 6))
    plt.plot(stages_range, efficiencies, 'o-', label='Round-trip Efficiency')
    plt.xlabel("Number of Stages (Compressor & Expander)")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Parametric Analysis: Efficiency vs. Number of Stages")
    plt.grid(True)
    plt.legend()
    plt.show()

def analyze_delta_t():
    """
    Performs a parametric analysis on the temperature difference (DELTA_T).
    """
    print("--- Running Parametric Analysis: DELTA_T ---")
    efficiencies = []
    delta_t_range = config.DELTA_T_RANGE
    for delta_t in delta_t_range:
        print(f"Analyzing for DELTA_T = {delta_t} C...")
        eff = run_simulation_for_efficiency({'DELTA_T': delta_t})
        efficiencies.append(eff)

    # Plotting results
    plt.figure(figsize=(10, 6))
    plt.plot(delta_t_range, efficiencies, 'o-')
    plt.xlabel("DELTA_T (Temperature difference for intercoolers/heaters) [°C]")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Parametric Analysis: Efficiency vs. DELTA_T")
    plt.grid(True)
    plt.show()

def analyze_heat_storage():
    """
    Performs a parametric analysis on heat storage system parameters.
    """
    print("--- Running Parametric Analysis: Heat Storage System ---")
    
    # Analysis for water storage tank volume
    print("\nAnalyzing water storage tank volume impact...")
    efficiencies_volume = []
    volumes_range = [50, 100, 200, 500, 1000]  # m³
    
    for volume in volumes_range:
        print(f"Analyzing for water tank volume = {volume} m³...")
        
        # Store original values
        original_heat_storage = config.HEAT_STORAGE_ENABLED
        original_volume = config.WATER_STORAGE_TANK_VOLUME_M3
        
        # Set heat storage parameters
        config.HEAT_STORAGE_ENABLED = True
        config.WATER_STORAGE_TANK_VOLUME_M3 = volume
        
        # Run simulation
        eff = run_simulation_for_efficiency({})
        efficiencies_volume.append(eff)
        
        # Restore original values
        config.HEAT_STORAGE_ENABLED = original_heat_storage
        config.WATER_STORAGE_TANK_VOLUME_M3 = original_volume
    
    # Plot volume analysis
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    plt.plot(volumes_range, efficiencies_volume, 'o-')
    plt.xlabel("Water Storage Tank Volume [m³]")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Efficiency vs. Water Storage Tank Volume")
    plt.grid(True)
    
    # Analysis for temperature difference
    print("\nAnalyzing temperature difference impact...")
    efficiencies_delta_t = []
    delta_t_range = [5, 10, 15, 20, 30]  # °C
    
    for delta_t in delta_t_range:
        print(f"Analyzing for temperature difference = {delta_t} °C...")
        
        # Store original values
        original_heat_storage = config.HEAT_STORAGE_ENABLED
        original_delta_t = config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C
        
        # Set heat storage parameters
        config.HEAT_STORAGE_ENABLED = True
        config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C = delta_t
        
        # Run simulation
        eff = run_simulation_for_efficiency({})
        efficiencies_delta_t.append(eff)
        
        # Restore original values
        config.HEAT_STORAGE_ENABLED = original_heat_storage
        config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C = original_delta_t
    
    # Plot delta T analysis
    plt.subplot(1, 2, 2)
    plt.plot(delta_t_range, efficiencies_delta_t, 'o-')
    plt.xlabel("Temperature Difference [°C]")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Efficiency vs. Temperature Difference")
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()
    
    # Print summary
    print("\nHeat Storage Analysis Summary:")
    print("="*50)
    print("Water Tank Volume Analysis:")
    for vol, eff in zip(volumes_range, efficiencies_volume):
        print(f"  {vol} m³: {eff:.2%}")
    print("\nTemperature Difference Analysis:")
    for dt, eff in zip(delta_t_range, efficiencies_delta_t):
        print(f"  {dt} °C: {eff:.2%}")

def analyze_heat_storage():
    """
    Performs a parametric analysis on heat storage system parameters.
    """
    print("--- Running Parametric Analysis: Heat Storage System ---")
    
    # Analysis for water storage tank volume
    print("\nAnalyzing water storage tank volume impact...")
    efficiencies_volume = []
    volumes_range = [50, 100, 200, 500, 1000]  # m³
    
    for volume in volumes_range:
        print(f"Analyzing for water tank volume = {volume} m³...")
        
        # Store original values
        original_heat_storage = config.HEAT_STORAGE_ENABLED
        original_volume = config.WATER_STORAGE_TANK_VOLUME_M3
        
        # Set heat storage parameters
        config.HEAT_STORAGE_ENABLED = True
        config.WATER_STORAGE_TANK_VOLUME_M3 = volume
        
        # Run simulation
        eff = run_simulation_for_efficiency({})
        efficiencies_volume.append(eff)
        
        # Restore original values
        config.HEAT_STORAGE_ENABLED = original_heat_storage
        config.WATER_STORAGE_TANK_VOLUME_M3 = original_volume
    
    # Plot volume analysis
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    plt.plot(volumes_range, efficiencies_volume, 'o-')
    plt.xlabel("Water Storage Tank Volume [m³]")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Efficiency vs. Water Storage Tank Volume")
    plt.grid(True)
    
    # Analysis for temperature difference
    print("\nAnalyzing temperature difference impact...")
    efficiencies_delta_t = []
    delta_t_range = [5, 10, 15, 20, 30]  # °C
    
    for delta_t in delta_t_range:
        print(f"Analyzing for temperature difference = {delta_t} °C...")
        
        # Store original values
        original_heat_storage = config.HEAT_STORAGE_ENABLED
        original_delta_t = config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C
        
        # Set heat storage parameters
        config.HEAT_STORAGE_ENABLED = True
        config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C = delta_t
        
        # Run simulation
        eff = run_simulation_for_efficiency({})
        efficiencies_delta_t.append(eff)
        
        # Restore original values
        config.HEAT_STORAGE_ENABLED = original_heat_storage
        config.TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C = original_delta_t
    
    # Plot delta T analysis
    plt.subplot(1, 2, 2)
    plt.plot(delta_t_range, efficiencies_delta_t, 'o-')
    plt.xlabel("Temperature Difference [°C]")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Efficiency vs. Temperature Difference")
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()
    
    # Print summary
    print("\nHeat Storage Analysis Summary:")
    print("="*50)
    print("Water Tank Volume Analysis:")
    for vol, eff in zip(volumes_range, efficiencies_volume):
        print(f"  {vol} m³: {eff:.2%}")
    print("\nTemperature Difference Analysis:")
    for dt, eff in zip(delta_t_range, efficiencies_delta_t):
        print(f"  {dt} °C: {eff:.2%}")

def analyze_efficiency():
    """
    Performs a parametric analysis on the isentropic efficiency of compressors and expanders.
    """
    print("--- Running Parametric Analysis: Isentropic Efficiency ---")
    efficiencies_results = []
    efficiency_range = config.EFFICIENCY_RANGE
    for eff in efficiency_range:
        print(f"Analyzing for machine efficiency = {eff:.2f}...")
        params = {
            "COMPRESSOR_ISENTROPIC_EFFICIENCY": eff,
            "EXPANDER_ISENTROPIC_EFFICIENCY": eff
        }
        sim_eff = run_simulation_for_efficiency(params)
        efficiencies_results.append(sim_eff)

    # Plotting results
    plt.figure(figsize=(10, 6))
    plt.plot(efficiency_range, efficiencies_results, 'o-')
    plt.xlabel("Isentropic Efficiency (Compressor & Expander)")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Parametric Analysis: Round-trip vs. Machine Isentropic Efficiency")
    plt.grid(True)
    plt.show()

def analyze_pressure_drop():
    """
    Performs a parametric analysis on the pressure drop factor for intercoolers and interheaters.
    """
    print("--- Running Parametric Analysis: Pressure Drop Factor ---")
    efficiencies = []
    pressure_drop_range = config.PRESSURE_DROP_RANGE
    for pressure_drop in pressure_drop_range:
        print(f"Analyzing for pressure drop factor = {pressure_drop:.2f}...")
        params = {
            "INTERCOOLER_PRESSURE_DROP_FACTOR": pressure_drop,
            "INTERHEATER_PRESSURE_DROP_FACTOR": pressure_drop
        }
        eff = run_simulation_for_efficiency(params)
        efficiencies.append(eff)

    # Plotting results
    plt.figure(figsize=(10, 6))
    plt.plot(pressure_drop_range, efficiencies, 'o-')
    plt.xlabel("Pressure Drop Factor (Intercoolers & Interheaters)")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Parametric Analysis: Efficiency vs. Pressure Drop Factor")
    plt.grid(True)
    plt.show()

def analyze_ambient_temperature():
    """
    Performs a parametric analysis on the ambient temperature.
    """
    print("--- Running Parametric Analysis: Ambient Temperature ---")
    efficiencies = []
    ambient_t_values = config.AMBIENT_T_VALUES
    for ambient_t in ambient_t_values:
        print(f"Analyzing for ambient temperature = {ambient_t} C...")
        params = {
            "T_AMBIENT_C": ambient_t
        }
        eff = run_simulation_for_efficiency(params)
        efficiencies.append(eff)

    # Plotting results
    plt.figure(figsize=(10, 6))
    plt.plot(ambient_t_values, efficiencies, 'o-')
    plt.xlabel("Ambient Temperature [°C]")
    plt.ylabel("Round-trip Efficiency")
    plt.title("Parametric Analysis: Efficiency vs. Ambient Temperature")
    plt.grid(True)
    plt.show()
