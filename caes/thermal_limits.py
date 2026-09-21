"""Physical temperature limits shared by both CAES architectures.

The discharge train is based on a *wet-rated*, water-tolerant turboexpander.
Liquid condensation is therefore not, by itself, the lower-temperature limit.
Ice is.  The common operating envelope is:

* when the local saturation boundary is above freezing, permit liquid
  condensation but keep the bulk outlet at least 10 K above 0 degC;
* when the boundary is below freezing, keep the outlet at least 10 K above the
  local frost point.

The same rule governs every expansion stage here.  It is an equipment-selection
screening rule, not a substitute for an OEM guarantee on liquid loading,
droplet size, local blade temperature or transient icing.
"""

from __future__ import annotations

from .constants import WATER_FREEZING_TEMPERATURE_K, WATER_TRIPLE_POINT_K
from .moisture import phase_change_temperature_k


# Plant-wide design rules.  The old unconditional floor is replaced by a
# physical wet/liquid versus dry/frost envelope.
EXPANDER_ICE_MARGIN_K = 10.0
# The liquid arm of the envelope: the freezing reference plus the margin.  The
# two coincide only because pure water freezes at 0 degC; keeping the sum named
# here is what stops the report, the GUI table and the two drawings from
# drifting apart when the margin is retuned.
WET_EXPANDER_LIQUID_FLOOR_C = WATER_FREEZING_TEMPERATURE_K - 273.15 + EXPANDER_ICE_MARGIN_K


def wet_expander_floor_label(phase_boundary_c: float) -> str:
    """The arm of the envelope in force at a phase boundary: liquid or frost."""

    if phase_boundary_c >= 0.0:
        return f"{WET_EXPANDER_LIQUID_FLOOR_C:.0f} °C liquid-water floor"
    return f"frost point + {EXPANDER_ICE_MARGIN_K:.0f} K"


def wet_expander_envelope_label() -> str:
    """The whole lower envelope, in the short form used on drawings and titles."""

    return (
        f"{WET_EXPANDER_LIQUID_FLOOR_C:.0f} °C liquid"
        f" / local frost + {EXPANDER_ICE_MARGIN_K:.0f} K"
    )
# Single numerical acceptance tolerance for enforcing temperature limits
# everywhere in the solver (wet-expander envelope and coolant limits).  It is
# a numerical guard sized just above the
# solver's own noise (the heater-target root is solved to 2e-5 K), NOT a
# physical relaxation: every physical limit itself stays hard.
TEMPERATURE_LIMIT_TOLERANCE_K = 1e-4

# Reference screening envelope from the published Baker Hughes
# turboexpander-compressor family specification.  These are not universal
# turbomachinery limits and must be replaced by the selected OEM guarantee at
# detailed design.  The model assumes an upstream separator, so inlet free
# liquid is zero; the conservative discharge check assumes every remaining
# gram of water vapour could condense.
REFERENCE_WET_EXPANDER_MAX_INLET_LIQUID_MASS_FRACTION = 0.01
REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION = 0.35
# The reference family also publishes 300 kJ/kg as its maximum enthalpy drop
# per stage.  Limiting unmodelled condensate to 0.1 wt% caps its approximately
# 2.5 MJ/kg latent term near 2.5 kJ/kg-stream, below 1% of that published stage
# envelope.  This is a model-validity screen, not an OEM hardware limit.
DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION = 0.001


def wet_expander_hard_floor_temperature_k(
    outlet_pressure_pa: float,
    protected_humidity_ratio: float,
) -> float:
    """Unmargined lower boundary for the water-tolerant expander [K].

    Above the water triple point the wet-rated machine may cross the liquid
    dew point, but it may not cool carried or newly condensed water below the
    freezing temperature.  Below the triple point there is no permitted liquid
    region: the local ice-saturation (frost-point) boundary applies.
    """

    phase_boundary_k = phase_change_temperature_k(
        outlet_pressure_pa,
        protected_humidity_ratio,
    )
    # The branch decision uses the same triple-point reference the moisture
    # correlations use, so a boundary computed in the ice regime can never be
    # classified as "liquid permitted".  The floor returned in the liquid
    # branch is the conventional 0 degC equipment floor.
    if phase_boundary_k >= WATER_TRIPLE_POINT_K:
        return WATER_FREEZING_TEMPERATURE_K
    return phase_boundary_k


def minimum_wet_expander_temperature_k(
    outlet_pressure_pa: float,
    protected_humidity_ratio: float,
) -> float:
    """Wet-rated expander lower operating envelope including ice margin [K]."""

    return (
        wet_expander_hard_floor_temperature_k(
            outlet_pressure_pa,
            protected_humidity_ratio,
        )
        + EXPANDER_ICE_MARGIN_K
    )


def maximum_possible_liquid_mass_fraction(humidity_ratio: float) -> float:
    """Conservative liquid fraction if all remaining vapour condenses.

    ``humidity_ratio`` is kg-water per kg-dry-air.  Dividing by total wet-stream
    mass converts that basis to the mass fraction used in OEM specifications.
    """

    if humidity_ratio < 0.0:
        raise ValueError("humidity_ratio must be non-negative")
    return humidity_ratio / (1.0 + humidity_ratio)


def reference_wet_expander_liquid_envelope_ok(humidity_ratio: float) -> bool:
    """Whether the worst-case condensate stays within the reference OEM cap."""

    return (
        maximum_possible_liquid_mass_fraction(humidity_ratio)
        <= REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION + 1e-12
    )


def dry_air_wet_expansion_approximation_ok(humidity_ratio: float) -> bool:
    """Whether omitted condensation latent heat stays within model scope."""

    return (
        maximum_possible_liquid_mass_fraction(humidity_ratio)
        <= DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION + 1e-12
    )
