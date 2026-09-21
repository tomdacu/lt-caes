"""Canonical human-readable names for the two low-temperature CAES forms.

The configuration and result objects deliberately keep the short, stable
machine values (``none`` and ``heat_user`` for the heat off-take).  This module
is the single source of truth for labels shown to users in the GUI, reports and
drawings; changing a label here therefore cannot break old JSON files or
programmatic callers.
"""

from __future__ import annotations

from .config import HeatOfftake


LTA_LABEL = "LTA-CAES (low-temperature adiabatic CAES)"
LTAHP_LABEL = "LTAHP-CAES (low-temperature adiabatic heat and power CAES)"

HEAT_OFFTAKE_LABELS: dict[HeatOfftake, str] = {
    HeatOfftake.NONE: f"No external heat user — {LTA_LABEL}",
    HeatOfftake.HEAT_USER: f"External heat user — {LTAHP_LABEL}",
}


def plant_concept_label(*, exports_heat: bool) -> str:
    """Return the specific concept name for a result or P&ID.

    Both forms share one plant, one coolant loop and one machine value for the
    thermal architecture; the heat-offtake flag is the only thing that
    distinguishes the user-facing concepts.
    """

    return LTAHP_LABEL if exports_heat else LTA_LABEL
