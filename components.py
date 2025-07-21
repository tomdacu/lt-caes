"""
Component models for the CAES plant.

This module contains classes for each physical component in the plant,
replacing the scattered functions in the transformation folder.
"""

from typing import Dict
from CoolProp.CoolProp import PropsSI
from data_models import ThermodynamicState, ProcessResult


class Compressor:
    """Models a single compressor stage."""
    
    def __init__(self, isentropic_efficiency: float):
        """
        Initialize the compressor.
        
        Args:
            isentropic_efficiency: Isentropic efficiency of the compressor (0-1)
        """
        self.efficiency = isentropic_efficiency
    
    def run(self, inlet_state: ThermodynamicState, outlet_pressure: float, fluid: str) -> ProcessResult:
        """
        Perform compression calculation.
        
        Args:
            inlet_state: Inlet thermodynamic state
            outlet_pressure: Target outlet pressure in Pa
            fluid: Working fluid name
            
        Returns:
            ProcessResult containing inlet/outlet states and work required
        """
        # Ideal outlet state (isentropic compression)
        ideal_outlet_t = PropsSI('T', 'P', outlet_pressure, 'S', inlet_state.s, fluid)
        ideal_outlet_h = PropsSI('H', 'P', outlet_pressure, 'T', ideal_outlet_t, fluid)
        
        # Ideal work
        ideal_work = ideal_outlet_h - inlet_state.h
        
        # Actual work
        actual_work = ideal_work / self.efficiency
        
        # Actual outlet state
        actual_outlet_h = inlet_state.h + actual_work
        actual_outlet_t = PropsSI('T', 'P', outlet_pressure, 'H', actual_outlet_h, fluid)
        actual_outlet_s = PropsSI('S', 'P', outlet_pressure, 'H', actual_outlet_h, fluid)
        
        outlet_state = ThermodynamicState(
            p=outlet_pressure,
            t=actual_outlet_t,
            h=actual_outlet_h,
            s=actual_outlet_s
        )
        
        return ProcessResult(
            inlet_state=inlet_state,
            outlet_state=outlet_state,
            work=actual_work,
            process_type="compressor"  # Changed to match plotting expectations
        )


class Expander:
    """Models a single expander (turbine) stage."""
    
    def __init__(self, isentropic_efficiency: float):
        """
        Initialize the expander.
        
        Args:
            isentropic_efficiency: Isentropic efficiency of the expander (0-1)
        """
        self.efficiency = isentropic_efficiency
    
    def run(self, inlet_state: ThermodynamicState, outlet_pressure: float, fluid: str) -> ProcessResult:
        """
        Perform expansion calculation.
        
        Args:
            inlet_state: Inlet thermodynamic state
            outlet_pressure: Target outlet pressure in Pa
            fluid: Working fluid name
            
        Returns:
            ProcessResult containing inlet/outlet states and work produced
        """
        # Ideal outlet state (isentropic expansion)
        ideal_outlet_t = PropsSI('T', 'P', outlet_pressure, 'S', inlet_state.s, fluid)
        ideal_outlet_h = PropsSI('H', 'P', outlet_pressure, 'T', ideal_outlet_t, fluid)
        
        # Ideal work
        ideal_work = inlet_state.h - ideal_outlet_h
        
        # Actual work
        actual_work = ideal_work * self.efficiency
        
        # Actual outlet state
        actual_outlet_h = inlet_state.h - actual_work
        actual_outlet_t = PropsSI('T', 'P', outlet_pressure, 'H', actual_outlet_h, fluid)
        actual_outlet_s = PropsSI('S', 'P', outlet_pressure, 'H', actual_outlet_h, fluid)
        
        outlet_state = ThermodynamicState(
            p=outlet_pressure,
            t=actual_outlet_t,
            h=actual_outlet_h,
            s=actual_outlet_s
        )
        
        return ProcessResult(
            inlet_state=inlet_state,
            outlet_state=outlet_state,
            work=-actual_work,  # Negative for work output
            process_type="expander"  # Changed to match plotting expectations
        )


class Intercooler:
    """Models an intercooler (cooling heat exchanger)."""
    
    def __init__(self, pressure_drop_factor: float):
        """
        Initialize the intercooler.
        
        Args:
            pressure_drop_factor: Pressure drop as fraction of inlet pressure
        """
        self.pressure_drop_factor = pressure_drop_factor
    
    def run(self, inlet_state: ThermodynamicState, target_temperature: float, fluid: str) -> ProcessResult:
        """
        Perform intercooling calculation.
        
        Args:
            inlet_state: Inlet thermodynamic state
            target_temperature: Target outlet temperature in K
            fluid: Working fluid name
            
        Returns:
            ProcessResult containing inlet/outlet states and heat transfer
        """
        # Outlet pressure with pressure drop
        outlet_pressure = inlet_state.p * (1 - self.pressure_drop_factor)
        
        # Outlet state at target temperature
        outlet_h = PropsSI('H', 'P', outlet_pressure, 'T', target_temperature, fluid)
        outlet_s = PropsSI('S', 'P', outlet_pressure, 'T', target_temperature, fluid)
        
        outlet_state = ThermodynamicState(
            p=outlet_pressure,
            t=target_temperature,
            h=outlet_h,
            s=outlet_s
        )
        
        # Heat transfer (negative for heat removal)
        heat_transfer = outlet_h - inlet_state.h
        
        return ProcessResult(
            inlet_state=inlet_state,
            outlet_state=outlet_state,
            heat_transfer=heat_transfer,
            process_type="intercooler"  # Changed to match plotting expectations
        )


class Interheater:
    """Models an interheater (heating heat exchanger)."""
    
    def __init__(self, pressure_drop_factor: float):
        """
        Initialize the interheater.
        
        Args:
            pressure_drop_factor: Pressure drop as fraction of inlet pressure
        """
        self.pressure_drop_factor = pressure_drop_factor
    
    def run(self, inlet_state: ThermodynamicState, target_temperature: float, fluid: str) -> ProcessResult:
        """
        Perform interheating calculation.
        
        Args:
            inlet_state: Inlet thermodynamic state
            target_temperature: Target outlet temperature in K
            fluid: Working fluid name
            
        Returns:
            ProcessResult containing inlet/outlet states and heat transfer
        """
        # Outlet pressure with pressure drop
        outlet_pressure = inlet_state.p * (1 - self.pressure_drop_factor)
        
        # Outlet state at target temperature
        outlet_h = PropsSI('H', 'P', outlet_pressure, 'T', target_temperature, fluid)
        outlet_s = PropsSI('S', 'P', outlet_pressure, 'T', target_temperature, fluid)
        
        outlet_state = ThermodynamicState(
            p=outlet_pressure,
            t=target_temperature,
            h=outlet_h,
            s=outlet_s
        )
        
        # Heat transfer (positive for heat addition)
        heat_transfer = outlet_h - inlet_state.h
        
        return ProcessResult(
            inlet_state=inlet_state,
            outlet_state=outlet_state,
            heat_transfer=heat_transfer,
            process_type="interheater"  # Changed to match plotting expectations
        )
