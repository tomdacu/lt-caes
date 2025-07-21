"""
CAES Plant Configuration Dashboard
==================================

This file provides an easy-to-use interface for configuring and testing
different CAES plant designs. Simply modify the parameters below and run
the simulation to see results.

USAGE:
1. Choose your analysis type
2. Modify plant parameters as needed  
3. Run: python dashboard.py
"""

# =============================================================================
# 🎛️ ANALYSIS CONFIGURATION
# =============================================================================

# Choose what type of analysis to run:
# "normal"              - Single plant simulation with efficiency and plots
# "comparison"          - Compare heat storage vs no heat storage  
# "parametric_stages"   - Analyze effect of number of stages
# "parametric_delta_t"  - Analyze effect of temperature differences
# "parametric_efficiency" - Analyze effect of component efficiencies
# "parametric_pressure" - Analyze effect of pressure drops
# "parametric_ambient"  - Analyze effect of ambient temperature
# "time_evolution"      - Time-varying analysis for heat storage system

ANALYSIS_TYPE = "normal"

# =============================================================================
# 🏭 PLANT CONFIGURATION
# =============================================================================

# --- Basic Plant Setup ---
HEAT_STORAGE_ENABLED = False       # True = Advanced CAES with heat storage
                                   # False = Traditional CAES without heat storage

COMPRESSOR_STAGES = 6              # Number of compression stages (1-10)
EXPANDER_STAGES = 6                # Number of expansion stages (usually same as compression)

# --- Operating Conditions ---
AMBIENT_TEMPERATURE_C = 15.0       # Ambient temperature [°C] (-20 to 50)
AMBIENT_PRESSURE_BAR = 1.0         # Ambient pressure [bar] (0.8 to 1.2)
STORAGE_PRESSURE_BAR = 100.0        # Storage pressure [bar] (10 to 200)

# --- Component Efficiencies ---
COMPRESSOR_EFFICIENCY = 0.85       # Compressor isentropic efficiency (0.7 to 0.98)
EXPANDER_EFFICIENCY = 0.85         # Expander isentropic efficiency (0.7 to 0.98)

# --- Heat Exchanger Configuration ---
DELTA_T_AMBIENT = 5.0              # Temperature difference for ambient air heat exchange [°C] (0 to 20)
HEAT_EXCHANGE_APPROACH_TEMP = 5.0  # Heat exchanger approach temperature [°C] (2 to 15)
TURBINE_INLET_DELTA_T = 10.0       # Additional temperature difference for turbine inlet [°C] (5 to 20)

# --- Pressure Drops ---
INTERCOOLER_PRESSURE_DROP = 0.03   # Pressure drop in intercoolers [fraction] (0.01 to 0.10)
INTERHEATER_PRESSURE_DROP = 0.03   # Pressure drop in interheaters [fraction] (0.01 to 0.10)

# =============================================================================
# 🔥 HEAT STORAGE SYSTEM (Only used when HEAT_STORAGE_ENABLED = True)
# =============================================================================

# --- Tank Design ---
WATER_TANK_VOLUME_M3 = 100         # Water tank volume [m³] (50 to 1000)
TANK_HEIGHT_M = 5.0                # Tank height [m] (3 to 15)
TANK_DIAMETER_M = 4.0              # Tank diameter [m] (2 to 10)

# --- Insulation ---
INSULATION_THICKNESS_M = 0.1       # Insulation thickness [m] (0.05 to 0.3)
INSULATION_CONDUCTIVITY = 0.04     # Thermal conductivity [W/m·K] (0.02 to 0.08)

# --- Time Evolution Analysis ---
SIMULATION_DAYS = 7                # Number of days to simulate (1 to 30)
TIME_STEP_MINUTES = 15             # Time step [minutes] (5 to 60)
NOMINAL_MASS_FLOW_KG_S = 5.0       # Nominal air mass flow rate [kg/s] (1 to 50)

# Daily power profile (96 values for 15-minute intervals over 24 hours)
# Positive = charging (compression), Negative = discharging (expansion), 0 = idle
# Values represent fraction of nominal power (-1.0 to +1.0)
DAILY_POWER_PROFILE = [
    # Night (00:00 - 06:00) - Low energy demand, charge storage
    0.0, 0.0, 0.0, 0.0, 0.2, 0.3, 0.4, 0.5,   # 00:00 - 02:00
    0.6, 0.5, 0.4, 0.3, 0.2, 0.0, 0.0, 0.0,   # 02:00 - 04:00  
    0.0, 0.0, 0.2, 0.4, 0.6, 0.7, 0.5, 0.3,   # 04:00 - 06:00
    
    # Morning (06:00 - 12:00) - Rising demand, mixed operation
    0.0, 0.0, -0.2, -0.3, -0.2, 0.0, 0.2, 0.3, # 06:00 - 08:00
    0.0, -0.2, -0.4, -0.3, -0.2, 0.0, 0.0, 0.1, # 08:00 - 10:00
    0.0, -0.1, -0.3, -0.5, -0.4, -0.2, 0.0, 0.0, # 10:00 - 12:00
    
    # Afternoon (12:00 - 18:00) - Peak demand, discharge storage  
    -0.2, -0.4, -0.6, -0.8, -0.7, -0.5, -0.3, -0.2, # 12:00 - 14:00
    -0.3, -0.5, -0.7, -0.9, -0.8, -0.6, -0.4, -0.2, # 14:00 - 16:00
    -0.2, -0.4, -0.6, -0.5, -0.3, -0.2, -0.1, 0.0,  # 16:00 - 18:00
    
    # Evening (18:00 - 24:00) - Declining demand, light charging
    0.0, -0.1, -0.2, -0.1, 0.0, 0.1, 0.2, 0.1,  # 18:00 - 20:00
    0.0, 0.0, 0.1, 0.2, 0.3, 0.2, 0.1, 0.0,     # 20:00 - 22:00
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,     # 22:00 - 24:00
]

# =============================================================================
# 📊 PARAMETRIC ANALYSIS RANGES
# =============================================================================

# Ranges for parametric studies (only used when ANALYSIS_TYPE starts with "parametric_")
STAGES_RANGE = [1, 2, 3, 4, 5, 6, 7, 8, 10]
DELTA_T_RANGE = [0, 2, 5, 8, 10, 15, 20, 25]
EFFICIENCY_RANGE = [0.70, 0.75, 0.80, 0.85, 0.90, 0.92, 0.94, 0.96, 0.98]
PRESSURE_DROP_RANGE = [0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10]
AMBIENT_TEMP_RANGE = [-20, -10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45]

# =============================================================================
# 🎨 OUTPUT CONFIGURATION  
# =============================================================================

# Plot Selection - Choose which plots to show
SHOW_TS_DIAGRAM = True             # Show T-S (Temperature-Entropy) diagram
SHOW_HS_DIAGRAM = False             # Show H-S (Enthalpy-Entropy) diagram  
SHOW_PH_DIAGRAM = False             # Show P-H (Pressure-Enthalpy) diagram
SHOW_EXERGY_DIAGRAM = True         # Show exergy analysis diagram

SHOW_PLOTS = True                  # Master switch for all thermodynamic cycle plots
SHOW_EXERGY_ANALYSIS = True        # Show exergy analysis
SHOW_DETAILED_OUTPUT = True        # Show detailed component-by-component results
SAVE_RESULTS_TO_FILE = True        # Save results to CSV files in results/ directory

# Plot configuration
PLOT_STYLE = "seaborn-v0_8"       # Matplotlib style ("default", "seaborn-v0_8", "ggplot")
FIGURE_SIZE = (12, 8)             # Figure size for plots (width, height)
DPI = 300                         # Resolution for saved plots

# Sankey Diagram Configuration (for D-CAES exergy flow visualization)
SANKEY_DIAGRAM_TYPE = "detailed"   # "simplified" or "detailed" - Type of Sankey diagram
SANKEY_ARROW_SCALE = 0.001           # Arrow thickness (smaller = thinner arrows) [0.001-0.01]
SANKEY_ARROW_GAP = 0.3               # Arrow length (larger = longer arrows) [0.5-3.0]  
SANKEY_ARROW_SHOULDER = 0.4          # Arrow head size (smaller = sharper heads) [0.005-0.02]
SANKEY_FIGURE_WIDTH = 12             # Figure width for Sankey diagram [15-30]
SANKEY_FIGURE_HEIGHT = 6.5           # Figure height for Sankey diagram [8-15]

# Detailed Sankey Configuration (for individual component visualization)
DETAILED_SANKEY_ARROW_SCALE = 0.0008 # Arrow thickness for detailed diagram (even thinner) [0.0005-0.005]
DETAILED_SANKEY_ARROW_GAP = 0.5      # Arrow length for detailed diagram [0.3-2.0]
DETAILED_SANKEY_ARROW_SHOULDER = 0.3 # Arrow head size for detailed diagram [0.003-0.015]
DETAILED_SANKEY_FIGURE_WIDTH = 20    # Figure width for detailed diagram [18-35]
DETAILED_SANKEY_FIGURE_HEIGHT = 12   # Figure height for detailed diagram [10-18]

# =============================================================================
# 🚀 QUICK PRESETS
# =============================================================================

def apply_preset(preset_name):
    """Apply predefined configuration presets for common scenarios."""
    global HEAT_STORAGE_ENABLED, COMPRESSOR_STAGES, STORAGE_PRESSURE_BAR
    global COMPRESSOR_EFFICIENCY, EXPANDER_EFFICIENCY, ANALYSIS_TYPE
    
    if preset_name == "basic_caes":
        HEAT_STORAGE_ENABLED = False
        COMPRESSOR_STAGES = 4
        STORAGE_PRESSURE_BAR = 50.0
        ANALYSIS_TYPE = "normal"
        
    elif preset_name == "advanced_caes":
        HEAT_STORAGE_ENABLED = True
        COMPRESSOR_STAGES = 6
        STORAGE_PRESSURE_BAR = 70.0
        ANALYSIS_TYPE = "normal"
        
    elif preset_name == "high_pressure":
        HEAT_STORAGE_ENABLED = True
        COMPRESSOR_STAGES = 8
        STORAGE_PRESSURE_BAR = 150.0
        ANALYSIS_TYPE = "normal"
        
    elif preset_name == "efficiency_study":
        HEAT_STORAGE_ENABLED = True
        ANALYSIS_TYPE = "parametric_efficiency"
        
    elif preset_name == "time_analysis":
        HEAT_STORAGE_ENABLED = True
        ANALYSIS_TYPE = "time_evolution"
        SIMULATION_DAYS = 3

# Uncomment one of these to use a preset:
# apply_preset("basic_caes")
# apply_preset("advanced_caes") 
# apply_preset("high_pressure")
# apply_preset("efficiency_study")
# apply_preset("time_analysis")

# =============================================================================
# 💡 HELP AND GUIDANCE
# =============================================================================

HELP_TEXT = """
QUICK START GUIDE:
1. Choose ANALYSIS_TYPE above (e.g., "normal", "comparison", "parametric_stages")
2. Set HEAT_STORAGE_ENABLED (True for A-CAES, False for D-CAES)
3. Adjust plant parameters as needed
4. Run: python dashboard.py
5. View results in console and plots

ANALYSIS TYPES EXPLAINED:
- "normal": Single simulation with efficiency and cycle diagrams
- "comparison": Compare efficiency with/without heat storage  
- "parametric_stages": See how efficiency changes with number of stages
- "parametric_delta_t": See how efficiency changes with temperature differences
- "time_evolution": Simulate plant operation over multiple days

TYPICAL RANGES:
- Compressor stages: 3-8 (more stages = higher efficiency, more complexity)
- Storage pressure: 30-200 bar (higher pressure = more energy density)
- Component efficiency: 0.85-0.96 (modern equipment typically 0.92-0.96)
- Heat exchange approach: 3-10°C (smaller = better heat recovery, larger equipment)

SANKEY DIAGRAM CUSTOMIZATION (for D-CAES):
- SANKEY_DIAGRAM_TYPE: Choose "simplified" (grouped components) or "detailed" (individual components)
- SANKEY_ARROW_SCALE: Controls arrow thickness (0.001-0.01, smaller = thinner)
- SANKEY_ARROW_GAP: Controls arrow length (0.5-3.0, larger = longer)
- SANKEY_ARROW_SHOULDER: Controls arrow head size (0.005-0.02, smaller = sharper)
- SANKEY_FIGURE_WIDTH/HEIGHT: Controls overall diagram size
- DETAILED_SANKEY_*: Separate configuration for detailed diagram with individual components

DIAGRAM TYPES:
- "simplified": Groups components by type (current perfect configuration)
- "detailed": Shows every individual component (C1, IC1, C2, IC2, E1, IH1, etc.)

For more details, see the plant_description.md file.
"""

if __name__ == "__main__":
    print("CAES Configuration Dashboard")
    print("=" * 50)
    print("This file contains configuration parameters.")
    print("To run the simulation, use: python run_simulation.py")
    print(HELP_TEXT)
