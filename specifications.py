"""
This module defines the specifications and structure of the CAES plant cycle.

It outlines the sequence of operations for both the compression (charging) and
expansion (discharging) phases of the CAES system.
"""

import config
from transformation import compressor_formulas, expander_formulas, exchanger

def define_compression_cycle(water_tank_temperature_c=None):
    """
    Defines the sequence of components for the compression cycle.

    Args:
        water_tank_temperature_c (float, optional): Current water tank temperature in Celsius.
            Used for heat storage calculations.

    Returns:
        list: A list of functions and their arguments representing the
              compression cycle.
    """
    cycle = []
    for i in range(config.COMPRESSOR_STAGES):
        cycle.append(
            {
                "type": "compressor",
                "function": compressor_formulas.compressor_stage_analysis,
                "params": {
                    "isentropic_efficiency": config.COMPRESSOR_ISENTROPIC_EFFICIENCY,
                },
            }
        )
        if i < config.COMPRESSOR_STAGES:
            # Determine target temperature based on heat storage configuration
            if config.HEAT_STORAGE_ENABLED and water_tank_temperature_c is not None:
                # With heat storage: cool air to water tank temperature + approach
                target_t = water_tank_temperature_c + config.HEAT_EXCHANGE_APPROACH_TEMP_C + 273.15
            else:
                # Without heat storage: cool air to ambient + delta T
                target_t = config.INTERCOOLER_OUTLET_T_C + 273.15
            
            cycle.append(
                {
                    "type": "intercooler",
                    "function": exchanger.heat_exchanger_analysis,
                    "params": {
                        "target_t": target_t,
                        "pressure_drop_factor": config.INTERCOOLER_PRESSURE_DROP_FACTOR,
                    },
                }
            )
    return cycle

def define_expansion_cycle(water_tank_temperature_c=None):
    """
    Defines the sequence of components for the expansion cycle.

    Args:
        water_tank_temperature_c (float, optional): Current water tank temperature in Celsius.
            Used for heat storage calculations.

    Returns:
        list: A list of functions and their arguments representing the
              expansion cycle.
    """
    cycle = []
    for i in range(config.EXPANDER_STAGES):
        cycle.append(
            {
                "type": "expander",
                "function": expander_formulas.expander_stage_analysis,
                "params": {
                    "isentropic_efficiency": config.EXPANDER_ISENTROPIC_EFFICIENCY,
                },
            }
        )
        if i < config.EXPANDER_STAGES - 1:
            # Determine target temperature based on heat storage configuration
            if config.HEAT_STORAGE_ENABLED and water_tank_temperature_c is not None:
                # With heat storage: heat air to water tank temperature - approach
                target_t = water_tank_temperature_c - config.HEAT_EXCHANGE_APPROACH_TEMP_C + 273.15
            else:
                # Without heat storage: heat air to ambient - delta T (external heat source)
                target_t = config.INTERHEATER_OUTLET_T_C + 273.15
            
            cycle.append(
                {
                    "type": "interheater",
                    "function": exchanger.heat_exchanger_analysis,
                    "params": {
                        "target_t": target_t,
                        "pressure_drop_factor": config.INTERHEATER_PRESSURE_DROP_FACTOR,
                    },
                }
            )
    return cycle
