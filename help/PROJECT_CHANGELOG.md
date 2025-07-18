# 📋 PROJECT CHANGELOG

## [v2.0.0] - 2024-07-18 - Heat Storage Complete Analysis & Repository Restructuring

### 🆕 NEW FEATURES
- **Heat Storage Complete Analysis**: Added time-evolution simulation with tank losses
- **Daily Power Profile**: 96-value daily power profile for 15-minute intervals
- **Tank Heat Losses**: Comprehensive heat loss calculations (conduction, convection, radiation)
- **Configurable Tank Geometry**: Cylindrical tank with insulation parameters
- **Time Analysis Mode**: New analysis type `heat_storage_time_analysis`

### 🏗️ REPOSITORY RESTRUCTURING
- **Modular Architecture**: Split code into organized directories
- **Core Module**: `core/` directory for heat storage components
- **Analysis Module**: `analysis/` directory for exergy and parametric analysis
- **Simulation Module**: `simulation/` directory for time-evolution simulations
- **Utils Module**: `utils/` directory for future utilities

### 📁 NEW DIRECTORY STRUCTURE
```
I_CAES/
├── main.py                    # Main entry point (simplified)
├── config.py                  # Configuration parameters
├── specifications.py          # Cycle specifications
├── plotting.py                # Visualization tools
├── transformation/           # Thermodynamic formulas
├── core/                      # Heat storage core components
│   ├── heat_storage.py        # Heat storage calculations
│   └── heat_transfer_losses.py # Heat loss calculations
├── analysis/                 # Analysis modules
│   ├── exergetic_analysis.py   # Exergy analysis
│   └── parametric_analysis.py  # Parametric studies
├── simulation/                 # Simulation modules
│   └── heat_storage_simulation.py # Time-evolution simulation
├── utils/                      # Utility modules
└── help/                       # Documentation
    ├── guida.md               # User guide
    ├── PROJECT_CHANGELOG.md   # This file
    └── commit_history.log    # Git history
```

### 🔧 CONFIGURATION UPDATES
- Added `HEAT_STORAGE_COMPLETE_ANALYSIS` parameter
- Added `NOMINAL_AIR_MASS_FLOW_RATE_KG_S` parameter
- Added tank geometry parameters (`TANK_HEIGHT_M`, `TANK_DIAMETER_M`)
- Added insulation parameters (`INSULATION_THICKNESS_M`, `INSULATION_THERMAL_CONDUCTIVITY_WMK`)
- Added simulation parameters (`SIMULATION_DAYS`, `TIME_STEP_MINUTES`)
- Added daily power profile `POWER_FRACTION_PROFILE_DAILY`

### 📊 ENHANCED ANALYSIS CAPABILITIES
- **Time-evolution simulation** with configurable duration
- **Real-time temperature tracking** in water storage tank
- **Energy flow visualization** with heat in/out/losses
- **Cumulative energy analysis** over simulation period
- **Backward compatibility** maintained for existing analyses

### 🎯 USAGE EXAMPLES
```python
# Simple heat storage analysis
config.HEAT_STORAGE_ENABLED = True
config.ANALYSIS_TYPE = 'heat_storage_analysis'

# Complete time analysis
config.HEAT_STORAGE_COMPLETE_ANALYSIS = True
config.ANALYSIS_TYPE = 'heat_storage_time_analysis'
```

## [v1.1.0] - 2024-07-18 - Heat Storage System Implementation

### 🆕 NEW FEATURES
- **Heat Storage System**: Added water-based heat storage capability
- **Heat Recovery**: Captures heat from intercoolers during compression
- **Heat Supply**: Uses stored heat for turbine inlet air preheating
- **Exergy Analysis**: Enhanced to include heat storage components
- **Parametric Analysis**: Added heat storage parameter studies

### 🔧 CONFIGURATION UPDATES
- Added `HEAT_STORAGE_ENABLED` parameter
- Added water storage parameters (`WATER_SPECIFIC_HEAT_KJ_KGK`, `WATER_DENSITY_KG_M3`)
- Added `WATER_STORAGE_TANK_VOLUME_M3` parameter
- Added `TURBINE_INLET_HEAT_EXCHANGE_DELTA_T_C` parameter

### 📊 ANALYSIS TYPES
- Added `heat_storage_analysis` to `ANALYSIS_TYPE` options

## [v1.0.0] - 2024-07-05 - Initial Release

### ✅ INITIAL FEATURES
- **Basic CAES Cycle**: Compression and expansion cycles
- **Real Components**: Compressors, expanders, intercoolers, interheaters
- **Efficiency Calculation**: Round-trip efficiency calculation
- **Parametric Analysis**: Multiple parameter studies
- **Visualization**: Thermodynamic cycle plots
- **Exergy Analysis**: Component-level exergy destruction analysis

### 📁 INITIAL STRUCTURE
- Single directory with all Python files
- Basic configuration system
- Modular component definitions
- Comprehensive documentation
