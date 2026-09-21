"""One colour vocabulary for every drawing in the package.

The names here describe the HUE, not the role. Each drawing module keeps its
own role-named constants (``diagrams.REJECTION_COLOR``, ``pid.HOT``) and binds
them to these values, so a reader still sees what a colour means on that
canvas - but a hue is declared exactly once. Retuning it can therefore no
longer desynchronise the P&ID from the plots, where the same red already means
"hot water" in one place and "rejected heat" in another.
"""

from __future__ import annotations

INK = "#263238"          # outlines, symbol edges, body text
MUTED = "#78909c"        # secondary text, reference levels
WHITE = "#ffffff"        # fills
AIR = "#37474f"          # process air
HOT = "#c62828"          # hot water; also rejected heat
WARM = "#ef6c00"         # warm water, approaches, stored heat
COLD = "#1565c0"         # cold water, discharge side
DEEP = "#0277bd"         # deeper blue: the cold-tank reference isotherm
SHAFT = "#2e7d32"        # mechanical work on a shaft; work leaving the plant
ELEC = "#6a1b9a"         # electrical work across the plant boundary
ATMOSPHERE = "#90a4ae"   # atmosphere, ambient streams
GEOLOGY = "#8d6e63"      # rock, thermal-storage loss
AMBER = "#f9a825"        # ambient heat taken in from the atmosphere
EXHAUST = "#546e7a"      # exhaust leaving the boundary unused
DESTRUCTION = "#bf360c"  # exergy destruction
NETWORK = "#00897b"      # the district-heating network itself
DEW = "#00838f"          # dew-point line


def rgb(colour: str) -> tuple[int, int, int]:
    """``#rrggbb`` -> its three channels, for arithmetic on colours."""

    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def lerp(low: str, high: str, fraction: float) -> str:
    """Interpolate two ``#rrggbb`` colours; the graded water pass of an HX."""

    a, b = rgb(low), rgb(high)
    return "#%02x%02x%02x" % tuple(
        round(a[i] + (b[i] - a[i]) * fraction) for i in range(3)
    )
