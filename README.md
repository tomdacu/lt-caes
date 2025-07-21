# 🔋 CAES Plant Simulation - Professional Energy Storage Analysis Tool

**Compressed Air Energy Storage (CAES) Plant Simulation and Analysis System**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.or```
I_CAES/
```
I_CAES/
├── 🎛️ dashbo├── 📁 core/                     # Core functionality
│   └── heat_storage.py          # Heat storage modeling
├── 📁 analysis/                 # Analysis modules
│   └── exergetic_analysis.py    # Exergy analysis
├── 📄 PLANT_DESCRIPTION.md      # Technical plant descriptions
└── 📁 .old/                     # Archived files
```

---          # Main configuration file
├── 🚀 run_simulation.py         # Simulation execution
├── 🏭 plant.py                  # Plant simulation logic
├── ⚙️ components.py             # Component models
├── 📊 data_models.py            # Data structures
├── 📈 plotting.py               # Visualization
├── 📁 core/                     # Core functionality
│   └── heat_storage.py          # Heat storage modeling
├── 📁 analysis/                 # Analysis modules
│   └── exergetic_analysis.py    # Exergy analysis
├── � PLANT_DESCRIPTION.md      # Technical plant descriptions
├── 📁 results/                  # CSV output files (auto-created)
│   ├── normal_analysis.csv      # Normal simulation results
│   ├── comparison_analysis.csv  # D-CAES vs A-CAES comparison
│   ├── parametric_*.csv         # Parametric studies
│   └── time_evolution.csv       # Time-varying analysis
└── 📁 .old/                     # Archived files
```py              # Main configuration file
├── 🚀 run_simulation.py         # Simulation execution
├── 🏭 plant.py                  # Plant simulation logic
├── ⚙️ components.py             # Component models
├── 📊 data_models.py            # Data structures
├── 📈 plotting.py               # Visualization
├── 📁 core/                     # Core functionality
│   └── heat_storage.py          # Heat storage modeling
├── 📁 analysis/                 # Analysis modules
│   └── exergetic_analysis.py    # Exergy analysis
├── � PLANT_DESCRIPTION.md      # Technical plant descriptions
└── 📁 .old/                     # Archived files
```https://img.shields.io/badge/CoolProp-Thermodynamics-green)](http://www.coolprop.org/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)](#)

---

## 🎯 Overview

This repository provides a comprehensive simulation environment for **Compressed Air Energy Storage (CAES)** plants. It supports both traditional **D-CAES** (Diabatic) and advanced **A-CAES** (Adiabatic) configurations with integrated thermal energy storage.

### 🏭 Plant Types Supported
- **D-CAES**: Traditional system without heat storage (~67% efficiency)
- **A-CAES**: Advanced system with thermal storage (~81% efficiency)
- **Configurable**: All parameters adjustable for custom studies

### 📊 Analysis Capabilities
- **Single plant performance** with thermodynamic cycle visualization
- **Comparative studies** between D-CAES and A-CAES technologies
- **Parametric optimization** for component sizing and operating conditions
- **Time-evolution simulations** for realistic operational analysis
- **Exergy analysis** for thermodynamic quality assessment

---

## 🚀 Quick Start

### 1️⃣ Setup Environment
```bash
pip install CoolProp matplotlib numpy
```

### 2. Configure Plant
Edit `dashboard.py`:
```python
ANALYSIS_TYPE = "normal"           # Analysis type
HEAT_STORAGE_ENABLED = True        # True = A-CAES, False = D-CAES
COMPRESSOR_STAGES = 6              # Number of stages
STORAGE_PRESSURE_BAR = 70.0        # Storage pressure
AMBIENT_TEMPERATURE_C = 15.0       # Operating temperature
```

### 3. Run Simulation
```bash
python run_simulation.py
```

### 4. View Results
- Console output with efficiency metrics
- Thermodynamic cycle plots (T-s, h-s, P-h)
- CSV files with detailed data

---

## � Analysis Types

Configure `ANALYSIS_TYPE` in `dashboard.py`:

| Type | Purpose |
|------|---------|
| `"normal"` | Single plant analysis with efficiency and plots |
| `"comparison"` | Compare D-CAES vs A-CAES performance |
| `"parametric_stages"` | Optimize number of compression stages |
| `"parametric_delta_t"` | Study temperature difference effects |
| `"parametric_efficiency"` | Analyze component efficiency impact |
| `"parametric_pressure"` | Study pressure drop sensitivity |
| `"parametric_ambient"` | Evaluate ambient temperature effects |
| `"time_evolution"` | Multi-day dynamic operation simulation |

---

## ⚙️ Configuration Parameters

### Basic Plant Settings
```python
# Plant Type
HEAT_STORAGE_ENABLED = True        # A-CAES vs D-CAES
COMPRESSOR_STAGES = 6              # Number of compression stages (1-10)
EXPANDER_STAGES = 6                # Number of expansion stages

# Operating Conditions  
AMBIENT_TEMPERATURE_C = 15.0       # Ambient temperature (-20 to 50°C)
AMBIENT_PRESSURE_BAR = 1.0         # Ambient pressure
STORAGE_PRESSURE_BAR = 70.0        # Storage pressure (10-200 bar)
```

### Component Performance
```python
# Efficiencies
COMPRESSOR_EFFICIENCY = 0.85       # Compressor efficiency (0.70-0.98)
EXPANDER_EFFICIENCY = 0.80         # Expander efficiency (0.70-0.98)

# Pressure Drops
INTERCOOLER_PRESSURE_DROP = 0.03   # Intercooler pressure drop (0.01-0.10)
INTERHEATER_PRESSURE_DROP = 0.03   # Interheater pressure drop (0.01-0.10)
```

### Heat Exchange Settings
```python
# Temperature Management
DELTA_T_AMBIENT = 5.0              # HX temperature difference (0-20°C)
HEAT_EXCHANGE_APPROACH_TEMP = 5.0  # HX approach temperature (2-15°C)
TURBINE_INLET_DELTA_T = 10.0       # Additional turbine inlet ΔT (5-20°C)
```

### Heat Storage System (A-CAES only)
```python
# Tank Design
WATER_TANK_VOLUME_M3 = 100         # Tank volume (50-1000 m³)
TANK_HEIGHT_M = 5.0                # Tank height (3-15 m)
TANK_DIAMETER_M = 4.0              # Tank diameter (2-10 m)

# Insulation
INSULATION_THICKNESS_M = 0.1       # Insulation thickness (0.05-0.3 m)
INSULATION_CONDUCTIVITY = 0.04     # Thermal conductivity (0.02-0.08 W/m·K)
```

### Time Evolution Parameters
```python
# Dynamic Analysis
SIMULATION_DAYS = 7                # Simulation duration (1-30 days)
TIME_STEP_MINUTES = 15             # Time resolution (5-60 minutes)
NOMINAL_MASS_FLOW_KG_S = 5.0       # Nominal air flow rate (1-50 kg/s)

# Power Profile (96 values for 24h in 15-min intervals)
DAILY_POWER_PROFILE = [...]        # Charge/discharge pattern (-1.0 to +1.0)
```

---

## � Quick Configuration Presets

Use these preset functions in `dashboard.py`:

```python
# Uncomment one of these:
apply_preset("basic_caes")      # 4-stage D-CAES at 50 bar
apply_preset("advanced_caes")   # 6-stage A-CAES at 70 bar  
apply_preset("high_pressure")   # 8-stage A-CAES at 150 bar
apply_preset("efficiency_study") # Parametric efficiency analysis
apply_preset("time_analysis")   # 3-day time evolution
```

---

## 📈 Understanding Results

### Normal Analysis Output
```
🔋 CAES PLANT SIMULATION RESULTS - NORMAL OPERATION
================================================================
⚡ Overall Efficiency: 80.64%
🔥 Compression Work: 428.0 kJ/kg
🔌 Expansion Work: 345.2 kJ/kg
🌡️ Average Compression Outlet: 90.6°C
🏺 Hot Water Tank Temperature: 85.6°C (A-CAES only)
🎯 Exergy Efficiency: 78.45%
```

### Comparison Results
```
📈 D-CAES (No Heat Storage):  67.20% efficiency
📈 A-CAES (With Heat Storage): 80.64% efficiency
🚀 IMPROVEMENT: +13.44 percentage points
```

### Parametric Optimization
```
Stages Study:
✅ 3 stages → 77.49% efficiency
✅ 4 stages → 80.21% efficiency
✅ 5 stages → 80.85% efficiency ← OPTIMAL
✅ 6 stages → 80.64% efficiency
```

---

## � Output Files

### Plots Generated
- **T-s Diagram**: Temperature vs entropy showing thermal processes
- **h-s Diagram**: Enthalpy vs entropy (Mollier diagram)
- **P-h Diagram**: Pressure vs enthalpy with process paths
- **Parametric Plots**: Optimization curves with best points highlighted
- **Time Evolution**: Temperature and efficiency vs time

### Data Export
- **CSV Files**: Timestamped results saved in `results/` directory
- **Performance Metrics**: Efficiency, work, temperatures
- **Component Data**: Individual component performance
- **Parametric Results**: Complete optimization datasets

---

## 🏭 Plant Configurations

### D-CAES (Diabatic CAES)
- **Heat Management**: Rejects compression heat, requires external heating
- **Typical Efficiency**: ~67%
- **Complexity**: Lower
- **Use Case**: Simple installations, lower capital cost

### A-CAES (Adiabatic CAES)  
- **Heat Management**: Stores compression heat, reuses for expansion
- **Typical Efficiency**: ~81%
- **Complexity**: Higher
- **Use Case**: High efficiency requirements, no external fuel

For detailed technical descriptions, see `PLANT_DESCRIPTION.md`

---

## � Optimization Guidelines

### Stage Count Optimization
- **1-2 stages**: Simple but low efficiency (~26-68%)
- **3-4 stages**: Good balance (~77-80%)
- **5-6 stages**: Optimal range (~80-81%)
- **7+ stages**: Diminishing returns (~79-77%)

### Component Selection
- **Compressor/Expander Efficiency**: Target 0.92-0.96 for modern equipment
- **Pressure Drops**: Keep below 3% per heat exchanger
- **Heat Exchange**: Minimize approach temperatures (3-7°C)

### Operating Conditions
- **Storage Pressure**: Balance energy density vs compression work
- **Ambient Conditions**: Consider climate impact on performance
- **Heat Storage**: Proper insulation reduces thermal losses

---

## 🛠️ File Structure

```
I_CAES/
├── 🎛️ dashboard.py              # Main configuration file
├── 🚀 run_simulation.py         # Simulation execution
├── 🏭 plant.py                  # Plant simulation logic
├── ⚙️ components.py             # Component models
├── 📊 data_models.py            # Data structures
├── 📈 plotting.py               # Visualization
├── 📄 config.py                 # Configuration management
├── 📄 main.py                   # Legacy compatibility
├── � core/                     # Core functionality
│   └── heat_storage.py          # Heat storage modeling
├── 📁 analysis/                 # Analysis modules
│   └── exergetic_analysis.py    # Exergy analysis
├── 📁 help/                     # Documentation
│   └── plant_description.md     # Technical plant descriptions
└── 📁 .old/                     # Archived files
```

---

## 🎓 Educational Applications

### For Students
- Compare D-CAES vs A-CAES technologies
- Study effect of design parameters
- Understand thermodynamic cycles
- Learn optimization principles

### For Researchers
- Test new configurations
- Sensitivity analysis
- Performance evaluation
- Technology comparison

### For Industry
- Preliminary design
- Performance assessment
- Technology selection
- Economic analysis support

---

## 🔍 Troubleshooting

### Common Issues
```bash
# Missing modules
pip install CoolProp matplotlib numpy

# Import errors - check file structure
python -c "from plant import Plant; print('OK')"

# Configuration errors - verify parameter ranges
# Efficiency: 0.70-0.98
# Stages: 1-10
# Pressure: 10-200 bar
```

### Performance Tips
- Use fewer parametric points for faster analysis
- Disable plots for batch runs: `SHOW_PLOTS = False`
- Reduce time evolution duration for quick tests

---

## � References

- **Technical Description**: `PLANT_DESCRIPTION.md`
- **Configuration Examples**: `dashboard.py` comments
- **Component Models**: See individual files in repository

---

## 🏆 Features

✅ **Complete CAES modeling** - Both D-CAES and A-CAES configurations  
✅ **Parametric optimization** - Find optimal design points  
✅ **Time evolution** - Dynamic operation simulation  
✅ **Professional visualization** - Thermodynamic cycle plots  
✅ **Easy configuration** - Single file setup  
✅ **Data export** - CSV files for further analysis  
✅ **Educational friendly** - Clear documentation and examples  

**Ready to analyze your CAES plant? Start with `python run_simulation.py`!** 🚀
