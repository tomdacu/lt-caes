"""Single source of truth for shared physical constants.

Every module imports these instead of re-declaring its own copy, so a value
can never drift between the moisture correlations, the thermal limits, and
the configuration validation.
"""

from __future__ import annotations

# Water phase behaviour.
WATER_TRIPLE_POINT_K = 273.16
WATER_TRIPLE_POINT_PRESSURE_PA = 611.657
WATER_CRITICAL_POINT_K = 647.096
WATER_CRITICAL_PRESSURE_PA = 22.064e6
# Nominal 0 degC equipment floor for liquid water.  Distinct from the triple
# point above: the frost/liquid branch decision uses the triple point (the
# correlation boundary), the hard floor itself is the conventional 0 degC.
WATER_FREEZING_TEMPERATURE_K = 273.15
# Psychrometric ratio M_water / M_dry_air.
WATER_TO_DRY_AIR_MOLAR_MASS_RATIO = 0.621945
# Lower validity bound of the Murphy-Koop ice-saturation correlation.
MINIMUM_FROST_CORRELATION_TEMPERATURE_K = 110.0

# Celsius offset of absolute zero, for configuration validation.
ABSOLUTE_ZERO_CELSIUS = -273.15
