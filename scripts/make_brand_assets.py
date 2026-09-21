"""Generate the project artwork: a centrifugal compressor impeller and volute.

Run from the repository root:

    python scripts/make_brand_assets.py

Writes, for the application icon and the README banner, a PNG at the exact
pixel size each surface needs plus an SVG carrying the same vector source.
The drawing is deterministic - no randomness, no clock - and it uses the same
colour vocabulary as every diagram in the package (``caes.palette``).

The subject is the machine the concept rests on: a centrifugal compressor
impeller seen from the front, inside its volute. Cold air enters at the eye
(the blue disc), nine backswept vanes pick it up, and the volute collects the
just-compressed, just-heated air that leaves at the rim; the warm dot at the
centre is the shaft, which is where the electricity actually arrives. At a
glance: electricity becomes a hot store and a cold store, through one machine.
"""

from __future__ import annotations

from math import cos, pi, sin
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Circle

# One colour vocabulary (see caes.palette): a hue is declared exactly once.
BACKGROUND = "#0f1b24"
INK = "#263238"
STEEL = "#eceff1"
STEEL_MID = "#b0bec5"
STEEL_DARK = "#546e7a"
WARM = "#ef6c00"
HOT = "#c62828"
COLD = "#1565c0"
TITLE = "#ffffff"
SUBTITLE = "#cfd8dc"
MUTED = "#78909c"

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

DPI = 100
BLADE_COUNT = 9
BLADE_SWEEP = 38 * pi / 180     # backsweep, inducer to rim
BLADE_FRACTION = 0.30           # blade width as a fraction of the local pitch
VOLUTE_START = 0.62 * pi        # tongue angle
VOLUME_ARC = 1.78 * pi          # how far the volute wraps


def _vane(
    ax: Axes, cx: float, cy: float,
    r_root: float, r_tip: float, theta0: float,
) -> None:
    """One backswept blade, linear width set against the local pitch."""

    outer: list[tuple[float, float]] = []
    inner: list[tuple[float, float]] = []
    for step in range(29):
        t = step / 28
        radius = r_root * (r_tip / r_root) ** t
        theta = theta0 - BLADE_SWEEP * t
        # Constant tangential width as a fraction of the pitch 2 pi r / N.
        half = 0.5 * BLADE_FRACTION * 2 * pi * radius / BLADE_COUNT / radius
        outer.append((radius, theta + half))
        inner.append((radius, theta - half))
    points = outer + inner[::-1]
    ax.fill(
        [cx + r * cos(a) for r, a in points],
        [cy + r * sin(a) for r, a in points],
        facecolor=STEEL, edgecolor=INK, linewidth=1.0, zorder=4,
    )


def draw_impeller(ax: Axes, cx: float, cy: float, radius: float) -> None:
    """The machine: volute, backplate, nine blades, shroud, eye, shaft."""

    # Volute: starts at the tongue, widens with the collected flow, discharges.
    start, end = 0.62 * pi, 0.62 * pi + 1.78 * pi
    theta = np.linspace(start, end, 110)
    r = 1.045 * radius + 0.13 * radius * ((theta - start) / (end - start)) ** 1.4
    ax.plot(
        cx + r * np.cos(theta), cy + r * np.sin(theta),
        color=HOT, linewidth=0.028 * radius, zorder=1, solid_capstyle="round",
    )

    ax.add_patch(Circle((cx, cy), 0.97 * radius, facecolor=STEEL_DARK,
                        edgecolor=INK, linewidth=1.6, zorder=2))
    for index in range(BLADE_COUNT):
        _vane(ax, cx, cy, 0.27 * radius, 0.90 * radius,
              pi / 2 + index * 2 * pi / BLADE_COUNT)
    # Shroud rim.
    ax.add_patch(Circle((cx, cy), 0.97 * radius, facecolor="none",
                        edgecolor=STEEL_MID, linewidth=0.05 * radius, zorder=5))
    # The eye: cold air entering between the blades, not a lens in a ring.
    ax.add_patch(Circle((cx, cy), 0.26 * radius, facecolor=COLD,
                        edgecolor=INK, linewidth=1.4, zorder=5))
    ax.add_patch(Circle((cx, cy), 0.15 * radius, facecolor=STEEL_MID,
                        edgecolor=INK, linewidth=1.1, zorder=6))
    ax.add_patch(Circle((cx, cy), 0.085 * radius, facecolor=INK,
                        edgecolor=STEEL_MID, linewidth=0.9, zorder=6))
    ax.add_patch(Circle((cx, cy), 0.046 * radius, facecolor=WARM,
                        edgecolor=INK, linewidth=0.7, zorder=7))


def _canvas(width: int, height: int) -> tuple[Figure, Axes]:
    figure = plt.figure(
        figsize=(width / DPI, height / DPI), dpi=DPI, facecolor=BACKGROUND,
    )
    ax = figure.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(BACKGROUND)
    return figure, ax


def _save(figure: Figure, png: Path, svg: Path) -> None:
    figure.savefig(png, dpi=DPI, facecolor=BACKGROUND)
    figure.savefig(svg, facecolor=BACKGROUND)
    plt.close(figure)


def make_icon(png: Path, svg: Path, size: int = 1024) -> None:
    """The application icon: one impeller in its volute, full bleed."""

    figure, ax = _canvas(size, size)
    draw_impeller(ax, size / 2, size / 2, 0.415 * size)
    _save(figure, png, svg)


def make_banner(png: Path, svg: Path, title: str, subtitle: str,
                note: str, width: int = 1280, height: int = 320) -> None:
    """The README banner: the machine on the left, the wordmark on the right."""

    figure, ax = _canvas(width, height)
    draw_impeller(ax, 0.17 * width, 0.50 * height, 0.385 * height)

    x_text = 0.38 * width
    ax.text(x_text, 0.72 * height, title, color=TITLE, fontsize=58,
            fontweight="bold", family="DejaVu Sans", ha="left",
            va="baseline", zorder=6)
    ax.text(x_text, 0.40 * height, subtitle, color=SUBTITLE, fontsize=17,
            family="DejaVu Sans", ha="left", va="baseline", zorder=6)
    ax.text(x_text, 0.23 * height, note, color=MUTED, fontsize=13,
            family="DejaVu Sans", ha="left", va="baseline", zorder=6)
    _save(figure, png, svg)


if __name__ == "__main__":
    make_icon(ASSETS / "lt-caes-icon.png", ASSETS / "lt-caes-icon.svg")
    make_banner(
        ASSETS / "lt-caes-banner.png", ASSETS / "lt-caes-banner.svg",
        title="LT-CAES",
        subtitle="Low-temperature adiabatic CAES - LTA & LTAHP",
        note="one plant, two uses of the stored heat - screened per kilogram of air",
    )
    print("wrote:", *(str(p.relative_to(ROOT)) for p in sorted(ASSETS.glob("*"))))
