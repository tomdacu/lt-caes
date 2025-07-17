"""
Configuration file for the CAES (Compressed Air Energy Storage) plant analysis.

This file contains all the key parameters and settings required for the simulation
of the CAES plant. Modifying these values will allow for the analysis of different
plant designs and operating conditions.
"""

# --- Fluid and Thermodynamic Properties ---
FLUID = "Air"  # Working fluid for the cycle
BACKEND = "HEOS"  # Backend for CoolProp property calculations

# --- Ambient Conditions ---
P_AMBIENT_BAR = 1.0  # Ambient pressure in bar
T_AMBIENT_C = 15.0  # Ambient temperature in degrees Celsius
ZERO_C = 273.15  # Zero degrees Celsius in Kelvin
DELTA_T = 5 # Difference in temperature from ambient air

# --- Compression System Configuration ---
COMPRESSOR_STAGES = 6  # Number of compression stages
COMPRESSOR_ISENTROPIC_EFFICIENCY = 0.8  # Isentropic efficiency of each compressor stage
COMPRESSOR_INLET_P_BAR = P_AMBIENT_BAR  # Inlet pressure for the first compressor stage
COMPRESSOR_INLET_T_C = T_AMBIENT_C  # Inlet temperature for the first compressor stage
COMPRESSOR_OUTLET_P_BAR = 70.0  # Final outlet pressure of the compression train in bar

# --- Intercooler Configuration ---
INTERCOOLER_OUTLET_T_C = T_AMBIENT_C + DELTA_T  # Target temperature at the outlet of each intercooler
INTERCOOLER_PRESSURE_DROP_FACTOR = 0.03  # Pressure drop as a fraction of inlet pressure (e.g., 0.01 = 1% drop)

# --- Storage System Configuration ---
STORAGE_PRESSURE_BAR = COMPRESSOR_OUTLET_P_BAR  # Storage pressure is assumed to be the same as compressor outlet
STORAGE_TEMPERATURE_C = INTERCOOLER_OUTLET_T_C  # Storage temperature

# --- Expansion System Configuration ---
EXPANDER_STAGES = COMPRESSOR_STAGES  # Number of expansion stages
EXPANDER_ISENTROPIC_EFFICIENCY = COMPRESSOR_ISENTROPIC_EFFICIENCY  # Isentropic efficiency of each expander stage
EXPANDER_OUTLET_P_BAR = P_AMBIENT_BAR  # Final outlet pressure of the expansion train

# --- Interheater Configuration ---
INTERHEATER_OUTLET_T_C = T_AMBIENT_C - DELTA_T # Target temperature at the outlet of each interheater
INTERHEATER_PRESSURE_DROP_FACTOR = INTERCOOLER_PRESSURE_DROP_FACTOR  # Pressure drop as a fraction of inlet pressure

# --- Analysis Settings ---
TARGET_ENERGY_OUTPUT_MWH = 100  # Target energy output for storage sizing in MWh
SHOW_PLOTS = True  # Set to False to disable showing thermodynamic cycle plots
# Options: 'normal', 'stages', 'delta_t', 'efficiency', 'pressure_drop', 'ambient_t'
ANALYSIS_TYPE = 'normal'  # Type of analysis to perform

# --- Parametric Analysis Ranges ---
# These values are used when ANALYSIS_TYPE is set to a parametric option
STAGES_RANGE = [1, 2, 3, 4, 6, 8, 10]
DELTA_T_RANGE = [0, 5, 10, 15, 20, 30]
EFFICIENCY_RANGE = [0.92, 0.9, 0.87, 0.85, 0.82, 0.8, 0.77, 0.75, 0.72, 0.7, 0.68]
PRESSURE_DROP_RANGE = [0.00, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.1]
AMBIENT_T_VALUES = [-15, -10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40]
