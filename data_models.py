"""
Data models for the CAES plant simulation.

This module defines the data structures used throughout the simulation,
including configuration and results.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class PlantConfig:
    """Configuration parameters for the CAES plant."""
    
    # Basic configuration
    heat_storage_enabled: bool = True
    stages_compressor: int = 6
    stages_expander: int = 6
    
    # Operating conditions
    T_ambient_C: float = 15.0
    P_ambient_bar: float = 1.0
    P_storage_bar: float = 70.0
    
    # Component efficiencies  
    eta_compressor: float = 0.96
    eta_expander: float = 0.96
    
    # Heat exchange
    delta_T_ambient: float = 5.0
    heat_exchange_approach_temp: float = 5.0
    turbine_inlet_delta_T: float = 10.0
    
    # Pressure drops
    intercooler_pressure_drop: float = 0.03
    interheater_pressure_drop: float = 0.03
    
    # Heat storage system parameters
    tank_volume_m3: float = 100.0
    tank_height_m: float = 5.0
    tank_diameter_m: float = 4.0
    insulation_thickness_m: float = 0.1
    insulation_conductivity: float = 0.04
    
    # Time evolution parameters
    nominal_mass_flow_kg_s: float = 5.0
    
    # Legacy compatibility properties
    @property
    def fluid(self) -> str:
        return "Air"
    
    @property
    def backend(self) -> str:
        return "HEOS"
    
    @property
    def p_ambient_bar(self) -> float:
        return self.P_ambient_bar
    
    @property
    def t_ambient_c(self) -> float:
        return self.T_ambient_C
    
    @property
    def zero_c(self) -> float:
        return 273.15
    
    @property
    def delta_t(self) -> float:
        return self.delta_T_ambient
    
    @property
    def compressor_stages(self) -> int:
        return self.stages_compressor
    
    @property
    def compressor_isentropic_efficiency(self) -> float:
        return self.eta_compressor
    
    @property
    def compressor_inlet_p_bar(self) -> float:
        return self.P_ambient_bar
    
    @property
    def compressor_inlet_t_c(self) -> float:
        return self.T_ambient_C
    
    @property
    def compressor_outlet_p_bar(self) -> float:
        return self.P_storage_bar
    
    @property
    def intercooler_pressure_drop_factor(self) -> float:
        return self.intercooler_pressure_drop
    
    @property
    def storage_pressure_bar(self) -> float:
        return self.P_storage_bar
    
    @property
    def expander_stages(self) -> int:
        return self.stages_expander
    
    @property
    def expander_isentropic_efficiency(self) -> float:
        return self.eta_expander
    
    @property
    def expander_outlet_p_bar(self) -> float:
        return self.P_ambient_bar
    
    @property
    def interheater_pressure_drop_factor(self) -> float:
        return self.interheater_pressure_drop
    
    @property
    def heat_storage_complete_analysis(self) -> bool:
        return True
    
    @property  
    def heat_exchange_approach_temp_c(self) -> float:
        return self.heat_exchange_approach_temp
    turbine_inlet_heat_exchange_delta_t_c: float = 10.0
    
    # Heat storage time analysis
    tank_height_m: float = 5.0
    tank_diameter_m: float = 4.0
    water_specific_heat_kj_kgk: float = 4.186
    water_density_kg_m3: float = 997
    water_storage_tank_volume_m3: float = 100
    insulation_thickness_m: float = 0.1
    insulation_thermal_conductivity_wmk: float = 0.04
    tank_emissivity: float = 0.9
    convection_heat_transfer_coefficient_wm2k: float = 5.0
    nominal_air_mass_flow_rate_kg_s: float = 5.0
    simulation_days: int = 1
    time_step_minutes: int = 15
    initial_water_tank_t_c: float = 15.0
    
    # Daily power profile (96 values for 15-minute intervals)
    power_fraction_profile_daily: List[float] = field(default_factory=lambda: [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 00:00 - 01:30
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
    ])
    
    # Analysis settings
    target_energy_output_mwh: float = 100
    show_plots: bool = True
    show_exergy_analysis: bool = True
    analysis_type: str = 'normal'
    
    # Parametric analysis ranges
    stages_range: List[int] = field(default_factory=lambda: [1, 2, 3, 4, 6, 8, 10])
    delta_t_range: List[float] = field(default_factory=lambda: [0, 5, 10, 15, 20, 30])
    efficiency_range: List[float] = field(default_factory=lambda: [0.92, 0.9, 0.87, 0.85, 0.82, 0.8, 0.77, 0.75, 0.72, 0.7, 0.68])
    pressure_drop_range: List[float] = field(default_factory=lambda: [0.00, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.1])
    ambient_t_values: List[float] = field(default_factory=lambda: [-15, -10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40])


@dataclass
class ThermodynamicState:
    """Represents a thermodynamic state point."""
    p: float  # Pressure in Pa
    t: float  # Temperature in K
    h: float  # Specific enthalpy in J/kg
    s: float  # Specific entropy in J/kg·K


@dataclass
class ProcessResult:
    """Results from a single component operation."""
    inlet_state: ThermodynamicState
    outlet_state: ThermodynamicState
    work: float = 0.0  # Specific work in J/kg (positive for work input, negative for work output)
    heat_transfer: float = 0.0  # Specific heat transfer in J/kg
    process_type: str = ""  # e.g., "compression", "expansion", "intercooling", "interheating"


@dataclass
class CycleResults:
    """Results from a complete cycle (charging or discharging)."""
    process_results: List[ProcessResult] = field(default_factory=list)
    total_work_specific: float = 0.0  # Total specific work in J/kg
    total_heat_added_specific: float = 0.0  # Total specific heat added in J/kg
    inlet_state: Optional[ThermodynamicState] = None
    outlet_state: Optional[ThermodynamicState] = None
    
    @property
    def all_states(self) -> List[ThermodynamicState]:
        """Get all thermodynamic states in the cycle."""
        states = []
        if self.inlet_state:
            states.append(self.inlet_state)
        for result in self.process_results:
            states.append(result.outlet_state)
        return states
    
    @property
    def process_types(self) -> List[str]:
        """Get all process types in the cycle."""
        return [result.process_type for result in self.process_results]


@dataclass
class PlantResults:
    """Complete results from a plant simulation."""
    charging_results: CycleResults
    discharging_results: CycleResults
    round_trip_efficiency: float = 0.0
    hot_water_temperature_c: Optional[float] = None
    cold_water_temperature_c: Optional[float] = None
    exergy_analysis: Optional[Dict[str, Any]] = None
