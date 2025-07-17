"""
This module defines the specifications and structure of the CAES plant cycle.

It outlines the sequence of operations for both the compression (charging) and
expansion (discharging) phases of the CAES system.
"""

import config
from transformation import compressor_formulas, expander_formulas, exchanger

def define_compression_cycle():
    """
    Defines the sequence of components for the compression cycle.

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
            cycle.append(
                {
                    "type": "intercooler",
                    "function": exchanger.heat_exchanger_analysis,
                    "params": {
                        "target_t": config.INTERCOOLER_OUTLET_T_C + 273.15,
                        "pressure_drop_factor": config.INTERCOOLER_PRESSURE_DROP_FACTOR,
                    },
                }
            )
    return cycle

def define_expansion_cycle():
    """
    Defines the sequence of components for the expansion cycle.

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
            cycle.append(
                {
                    "type": "interheater",
                    "function": exchanger.heat_exchanger_analysis,
                    "params": {
                        "target_t": config.INTERHEATER_OUTLET_T_C + 273.15,
                        "pressure_drop_factor": config.INTERHEATER_PRESSURE_DROP_FACTOR,
                    },
                }
            )
    return cycle
