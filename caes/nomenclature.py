"""Canonical human-readable names for the three CAES concepts.

The configuration and result objects deliberately keep the short, stable
machine values (``adiabatic`` and ``diabatic``).  This module is the single
source of truth for labels shown to users in the GUI, reports and drawings;
changing a label here therefore cannot break old JSON files or programmatic
callers.
"""

from __future__ import annotations

from .config import HeatOfftake, PlantMode


PLANT_MODE_LABELS: dict[PlantMode, str] = {
    PlantMode.DIABATIC: "AD-CAES (ambient diabatic)",
    PlantMode.ADIABATIC: "LTA/LTHP-CAES (low-temperature adiabatic/heat and power)",
}

LTA_LABEL = "LTA-CAES (low-temperature adiabatic CAES)"
LTHP_LABEL = "LTHP-CAES (low-temperature heat and power CAES)"

HEAT_OFFTAKE_LABELS: dict[HeatOfftake, str] = {
    HeatOfftake.NONE: f"No external heat user — {LTA_LABEL}",
    HeatOfftake.HEAT_USER: f"External heat user — {LTHP_LABEL}",
}


def plant_mode_label(mode: PlantMode | str) -> str:
    """Return the canonical UI/report label for a mode or result value."""

    return PLANT_MODE_LABELS[PlantMode(mode)]


def plant_concept_label(
    mode: PlantMode | str,
    *,
    exports_heat: bool = False,
) -> str:
    """Return the specific concept name for a result or P&ID.

    ``PlantMode.ADIABATIC`` is the stable machine value shared by LTA and LTHP;
    the heat-offtake flag is what distinguishes the two user-facing concepts.
    """

    selected_mode = PlantMode(mode)
    if selected_mode is PlantMode.DIABATIC:
        return PLANT_MODE_LABELS[selected_mode]
    return LTHP_LABEL if exports_heat else LTA_LABEL
