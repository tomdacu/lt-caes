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

# --- Heat Storage Configuration ---
HEAT_STORAGE_ENABLED = True  # Set to True to enable heat storage system
HEAT_STORAGE_COMPLETE_ANALYSIS = True  # Set to True for time-evolution analysis with losses

# Basic Heat Storage Parameters (used for both simple and complete analysis)
WATER_SPECIFIC_HEAT_KJ_KGK = 4.186  # Specific heat capacity of water in kJ/kg·K
WATER_DENSITY_KG_M3 = 997  # Density of water at room temperature in kg/m³
WATER_STORAGE_TANK_VOLUME_M3 = 100  # Volume of water storage tank in m³
TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C = 10  # Temperature difference for heating turbine inlet air using stored heat
HEAT_EXCHANGE_APPROACH_TEMP_C = 5  # Minimum temperature difference for heat exchange between air and water

# --- Heat Storage Time Analysis Configuration ---
# These parameters are only used when HEAT_STORAGE_COMPLETE_ANALYSIS = True

# Tank Geometry
TANK_HEIGHT_M = 5.0  # Height of cylindrical water storage tank [m]
TANK_DIAMETER_M = 4.0  # Diameter of cylindrical water storage tank [m]

# Insulation Properties
INSULATION_THICKNESS_M = 0.1  # Thickness of tank insulation [m]
INSULATION_THERMAL_CONDUCTIVITY_WMK = 0.04  # Thermal conductivity of insulation [W/m·K]
TANK_EMISSIVITY = 0.9  # Surface emissivity of tank (0-1)
CONVECTION_HEAT_TRANSFER_COEFFICIENT_WM2K = 5.0  # Free convection heat transfer coefficient [W/m²·K]

# Simulation Parameters
NOMINAL_AIR_MASS_FLOW_RATE_KG_S = 5.0  # Nominal air mass flow rate for time analysis [kg/s]
SIMULATION_DAYS = 1  # Number of days to simulate for time analysis
TIME_STEP_MINUTES = 15  # Time step for simulation [minutes]
INITIAL_WATER_TANK_T_C = T_AMBIENT_C  # Initial water tank temperature [°C]

# Daily Power Profile (96 values for 15-minute intervals over 24 hours)
# Positive values = charging (compression), Negative values = discharging (expansion)
POWER_FRACTION_PROFILE_DAILY = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 00:00 - 01:30 (8 intervals)
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 01:30 - 03:00
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0,  # 03:00 - 04:30
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 04:30 - 06:00
    0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0,  # 06:00 - 07:30
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 07:30 - 09:00
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 09:00 - 10:30
    0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0,  # 10:30 - 12:00
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 12:00 - 13:30
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 13:30 - 15:00
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 15:00 - 16:30
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 16:30 - 18:00
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 18:00 - 19:30
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 19:30 - 21:00
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 21:00 - 22:30
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 22:30 - 24:00
]

# --- Compression System Configuration ---
COMPRESSOR_STAGES = 6  # Number of compression stages
COMPRESSOR_ISENTROPIC_EFFICIENCY = 0.96  # Isentropic efficiency of each compressor stage
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
SHOW_EXERGY_ANALYSIS = True  # Set to True to show exergetic analysis pie chart
# Options: 'normal', 'stages', 'delta_t', 'efficiency', 'pressure_drop', 'ambient_t', 'heat_storage_analysis', 'heat_storage_time_analysis'
ANALYSIS_TYPE = 'normal'  # Type of analysis to perform

# --- Parametric Analysis Ranges ---
# These values are used when ANALYSIS_TYPE is set to a parametric option
STAGES_RANGE = [1, 2, 3, 4, 6, 8, 10]
DELTA_T_RANGE = [0, 5, 10, 15, 20, 30]
EFFICIENCY_RANGE = [0.92, 0.9, 0.87, 0.85, 0.82, 0.8, 0.77, 0.75, 0.72, 0.7, 0.68]
PRESSURE_DROP_RANGE = [0.00, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.1]
AMBIENT_T_VALUES = [-15, -10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40]
