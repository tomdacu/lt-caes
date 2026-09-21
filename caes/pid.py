"""Live piping & instrumentation diagram (P&ID) for the CAES plant.

WHAT THIS IS FOR
----------------
The T-s and p-h plots tell you what the *air* is doing. They tell you nothing
about what the *plant* looks like. This module draws the plant: the actual
machines, exchangers, tanks, pumps and lines implied by the current
configuration, using the symbol vocabulary an engineer already reads fluently
(ISO 10628 / ISA 5.1 shapes, ISA equipment tags).

The diagram is DERIVED, never hand-drawn. Change ``compressor_stages`` from 4 to
6 and two more compressor bodies, two more intercoolers, two more coolant branches
and two more tank tie-ins appear, correctly tagged and correctly piped. Switch
``mode`` to diabatic and the entire coolant loop - tanks, pumps, headers - vanishes
and is replaced by fin-fan coolers venting to atmosphere. That is the whole point:
the picture cannot drift out of sync with the model, because it is generated from
the same :class:`~caes.config.PlantConfig` the solver runs on.

TWO-STAGE DESIGN
----------------
``layout(config)``  -> a :class:`Diagram`: pure geometry and topology, no drawing.
                       Testable without a canvas; this is where "what equipment
                       exists and what is connected to what" is decided.
``render(ax, ...)`` -> paints a Diagram onto a matplotlib axis, and overlays the
                       live numbers from a :class:`~caes.models.PlantResult`.

HOW IT IS DRAWN
---------------
The two hero symbols - the flow-oriented machines (:class:`Machine`) and the
counter-flow exchanger blocks (:class:`CounterflowHX`) - are `schemdraw`_ elements,
drawn onto the axis via ``schemdraw.Drawing(canvas=ax)``. Everything else - the
orthogonal pipe routing, the annotations, and the peripheral ISA symbols (tanks,
pumps, valves, filter, stack, cavern, drivers, grid, air-cooled and
heat-user taps) - is drawn straight onto the same axis with
matplotlib, in the same data coordinates, so a schemdraw body placed at ``(x, y)``
lands exactly where the router expects its pipe stub.

.. _schemdraw: https://schemdraw.readthedocs.io

Keeping layout and render apart means the tests can assert that a 6-stage adiabatic
plant has six intercoolers tied into two tanks without ever opening a GUI.

READING THE DRAWING
-------------------
    dark grey  process air                  thin arrows show flow direction
    red        HOT coolant   - tank -> interheaters, and intercoolers -> tank
    orange     turbine-supply coolant downstream of the heat-user tap E-302
    blue       COLD coolant  - at cold-tank temperature, ready to be used again
    green      MECHANICAL power on a shaft (motor -> compressors, expanders -> generator)
    purple     ELECTRICAL power crossing the plant boundary (grid <-> plant)
    dashed     instrument signal (to the ISA balloons)

Charging runs left-to-right along the top, discharging right-to-left along the
bottom, and the cavern sits underground on the right where both trains meet it -
which is also how the real plant is arranged, since the wellhead is one shared
penetration.

EQUIPMENT TAG SCHEME (ISA-style, 100=charge, 200=discharge, 300=thermal, 400=storage)
    F-101   inlet filter / silencer      K-101..  compressor stages
    M-101   compressor motor             E-101..  intercoolers / final cooler
    T-201.. expander stages              E-201..  coolant interheaters (adiabatic only)
    TV-201.. anti-icing throttle valves (AD-CAES)
    G-201   generator                    S-201    exhaust stack
    TK-301  hot coolant tank             TK-302   cold coolant tank
    P-301   hot coolant pump             P-302    cold coolant pump
    AH-201.. ambient reheaters (AD-CAES only; its sole discharge heat source)
    E-302A.. heat-user cascade (present only with an external heat off-take)
    V-401   cavern                       XV-401/402  charge / discharge block valves
    W-101 / W-201  grid tie-in points
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, pi, sin

import schemdraw
from schemdraw import elements as elm
from schemdraw.segments import Segment, SegmentPoly

from .config import HeatOfftake, PlantConfig, PlantMode
from .models import PlantResult
from .nomenclature import plant_concept_label
from . import palette
from .thermal_limits import wet_expander_envelope_label

# --------------------------------------------------------------------------- palette
# One hue, one declaration (see caes.palette): the names here say what a colour
# MEANS on this canvas, the module says what it IS.

AIR = palette.AIR       # process air
HOT = palette.HOT       # highest-temperature water: intercoolers -> hot tank
WARM = palette.WARM     # minimum-duty turbine supply downstream of the heat-user HX
COLD = palette.COLD     # cold coolant, at cold-tank temperature
SHAFT = palette.SHAFT   # MECHANICAL power on a shaft
ELEC = palette.ELEC     # ELECTRICAL power across the plant boundary
VENT = palette.ATMOSPHERE   # atmosphere
ROCK = palette.GEOLOGY      # geology
FILL = palette.WHITE
INK = palette.INK       # symbol outlines and text
MUTED = palette.MUTED

# --------------------------------------------------------------------------- geometry
# The pitch is generous on purpose. Symbols are drawn in data coordinates but
# LABELS are drawn in points, so a tight pitch does not merely look cramped - the
# duty and work callouts start colliding with each other and with the equipment
# tags, and the drawing stops being readable exactly when the plant gets
# interesting (many stages).

STAGE_PITCH = 3.9      # x-distance between one machine and the next
X_ORIGIN = 4.0         # x of the first compressor

# CENTER-FACING BANDS. The tanks sit in the middle; every exchanger faces the
# centre - its WATER side toward the tanks, its AIR side toward the turbomachines -
# so the water runs are short and never cross a train, and the air stays local to
# each train. The layout is symmetric about the tank band.
#
#   grid  ─ motor/compressors (shaft) ─ intercoolers ─ [water headers] ─ TANKS ─
#         [water headers] ─ interheaters ─ expanders (shaft)/generator ─ grid
Y_KC = 6.6             # compressors + charging shaft
Y_EC = 4.3            # intercooler row  (air up -> compressors, water down -> tanks)
Y_CHDR_C = 2.7        # cold-supply header (charging)
Y_CHDR_H = 2.0        # hot-return header (charging)
Y_TANKS = 0.0         # tank / E-302 centreline (the middle band)
Y_DHDR_W = -2.0       # turbine-supply header (discharging)
Y_DHDR_C = -2.7       # cold-return header (discharging)
Y_EE = -4.3           # interheater row  (air down -> expanders, water up -> tanks)
Y_KE = -6.6           # expanders + discharging shaft
Y_GRID_TOP = 9.0      # grid import, above the motor
Y_GRID_BOT = -9.0     # grid export, below the generator
Y_GROUND = -10.4      # grade level
Y_CAVERN = -13.0      # cavern centreline

# Dedicated water pipe runs (the "corridors"): horizontal segments that leave
# the tank band sideways and rise/fall on two verticals kept left of every
# machine, so no water line ever crosses a symbol.
Y_COLD_SUPPLY_RUN = 0.9    # cold tank side -> supply corridor -> cold header
Y_SURPLUS_RUN = -1.5       # return corridor -> cold tank bottom (spent water)

X_SUPPLY_CORRIDOR_OFFSET = 2.8   # cold-supply riser, this far left of the leftmost symbol
X_RETURN_CORRIDOR_OFFSET = 4.4   # spent-water riser, further left still

X_COLD_TANK = X_ORIGIN + 0.5
X_HOT_TANK = X_ORIGIN + 5.0
HOP_R = 0.20          # radius of the crossing-bridge arcs

# E-304, the extraction body.  It is drawn WIDE and TAPERED rather than as
# another circle, because its two distinguishing features are exactly those: it
# is one body with several nozzles along its length, and the trunk inside it
# thins at every nozzle.  A circle would make it read as just one more
# exchanger in a series, which is the thing it replaced.
EXTRACTION_HALF_W = 1.8
EXTRACTION_HOT_HALF_H = 0.62     # trunk inlet end, carrying the whole inventory
EXTRACTION_COLD_HALF_H = 0.26    # last extraction, where the trunk is exhausted

# Horizontal bands used only when E-304 is present. The space between the tank
# band and the top of the interheater blocks (about -1.2 to -3.78) has to carry
# the user loop, the recuperated return, one bleed manifold per expansion stage,
# the E-303 collection header and the final mixing header - so the bands are
# named and allocated once here rather than nudged by hand at each call site.
Y_USER_RUN = Y_TANKS - 1.20          # user supply above, user return below
Y_RECUP_RETURN = Y_TANKS - 1.75      # E-304 cold outlet, on its way to TK-302
Y_BLEED_TOP = -2.08                  # manifold reaching FURTHEST left
Y_BLEED_BOTTOM = -3.30               # manifold reaching least far left
Y_E303_BAND = -2.95                  # E-303 body and its collection header
Y_FINAL_HEADER = -3.62               # everything mixed, on its way to E-304

# The user return and the recuperated return are BOTH blue and both leave the
# tank band leftward, so they are deliberately kept far enough apart to read as
# two runs. They are also almost disjoint in x - the user return lives right of
# E-302, the recuperated one left of E-304 - and letting them sit at one height
# made the drawing say the user return flows on into the cold tank, which is
# exactly wrong.


@dataclass(frozen=True)
class Equipment:
    """One symbol on the diagram. ``kind`` selects which primitive draws it."""

    tag: str
    kind: str
    label: str
    x: float
    y: float
    # ``flow`` is +1 when the fluid moves left-to-right through this item and -1
    # when it moves right-to-left. Machines are NOT symmetric - a compressor
    # trapezoid narrows in the direction of flow and an expander widens - so the
    # renderer needs this to point the symbol the right way.
    flow: int = 1
    # Number of side connections a multi-port body carries. Only E-304 uses it,
    # to place one extraction nozzle per expansion stage along its length.
    ports: int = 0


@dataclass(frozen=True)
class Diagram:
    """Topology + geometry of the plant implied by one PlantConfig."""

    equipment: list[Equipment] = field(default_factory=list)
    mode: str = "adiabatic"
    compressor_stages: int = 0
    expander_stages: int = 0
    has_water_loop: bool = False
    exports_heat: bool = False
    x_supply_corridor: float = 0.0
    x_return_corridor: float = 0.0
    x_min: float = 0.0
    x_max: float = 0.0
    y_min: float = 0.0
    y_max: float = 0.0

    def by_tag(self, tag: str) -> Equipment | None:
        return next((e for e in self.equipment if e.tag == tag), None)

    def of_kind(self, kind: str) -> list[Equipment]:
        return [e for e in self.equipment if e.kind == kind]

    @property
    def tags(self) -> list[str]:
        return [e.tag for e in self.equipment]


# --------------------------------------------------------------------------- layout


def layout(config: PlantConfig, result: PlantResult | None = None) -> Diagram:
    """Turn a configuration into the equipment list and its geometry.

    This function is the single source of truth for "what does this plant contain".
    It contains no matplotlib and no numbers from the solver - only the *shape* of
    the plant, which depends solely on the discrete architectural choices:

        compressor_stages / expander_stages  -> how many machines and exchangers
        mode                                 -> coolant loop, or fin-fans to atmosphere
        AD-CAES                              -> mandatory ambient reheat plus throttle bypass
        heat_offtake        (adiabatic only) -> district-heating exchanger + network
    """
    adiabatic = config.mode is PlantMode.ADIABATIC
    selling = adiabatic and config.heat_offtake is not HeatOfftake.NONE
    n_c, n_e = config.compressor_stages, config.expander_stages
    items: list[Equipment] = []

    # ---- CHARGING TRAIN --------------------------------------------------------
    # Compressors sit contiguous on the shaft at Y_KC; each intercooler drops to its
    # own row BELOW (Y_EC), facing the centre - air toward the compressors, water
    # toward the tanks. The cooler always exists; only its type depends on the mode.
    cx = [X_ORIGIN + i * STAGE_PITCH for i in range(n_c)]
    for i, x in enumerate(cx):
        items.append(Equipment(f"K-{101 + i}", "compressor", f"Compressor stage {i + 1}", x, Y_KC, flow=+1))
        cooler_name = (
            f"Intercooler {i + 1}"
            if i < n_c - 1
            else f"Final cooler {i + 1}"
        )
        items.append(Equipment(
            f"E-{101 + i}", "water_hx" if adiabatic else "air_cooler",
            cooler_name,
            x + STAGE_PITCH / 2, Y_EC, flow=+1))
    # Motor at the LEFT END of the shaft, its grid tie IN LINE with it (to the left,
    # same band) rather than stacked above - so the drawing spends no vertical space
    # on a tall electrical stub; filter on the inlet.
    items.append(Equipment("M-101", "motor", "Compressor motor", X_ORIGIN - 3.4, Y_KC))
    items.append(Equipment("W-101", "grid", "Grid import", X_ORIGIN - 3.4 - 2.9, Y_KC))
    items.append(Equipment("F-101", "filter", "Inlet filter\n& silencer", X_ORIGIN - 1.9, Y_KC - HALF_H - 0.1))

    # ---- DISCHARGING TRAIN (mirror; air flows RIGHT TO LEFT) -------------------
    # Expanders contiguous on the shaft at Y_KE; each interheater on the row ABOVE
    # (Y_EE), facing the centre - air toward the expanders, water toward the tanks.
    x_dstart = cx[-1] + STAGE_PITCH / 2 + 1.4
    # D-CAES needs room for its ambient reheater and anti-icing throttle path.
    # Moisture separators/dryers are intentionally omitted from this simplified
    # process schematic; the separate humidity diagnostic remains available.
    disc_pitch = STAGE_PITCH * (1.35 if adiabatic else 1.90)
    ex = [x_dstart - i * disc_pitch for i in range(n_e)]
    for i, x in enumerate(ex):
        if adiabatic:
            items.append(Equipment(
                f"E-{201 + i}", "water_hx", f"Reheater {i + 1}",
                x + STAGE_PITCH / 2, Y_EE, flow=-1,
            ))
        else:
            # Air flows right-to-left: ambient recovery comes first, followed
            # by the turbine/throttle pressure-reduction pair.  The ambient
            # reheater carries its own AH tag: E-20x means "coolant interheater"
            # and nothing else, so a tag can never mean two different devices
            # depending on which concept is drawn.
            # AD-CAES always includes ambient reheat; without it the expander
            # outlet temperatures violate the icing envelope.
            items.append(Equipment(
                f"AH-{201 + i}", "ambient_heater", f"Ambient reheater {i + 1}",
                x + 3.0, Y_EE, flow=-1,
            ))
            items.append(Equipment(
                f"TV-{201 + i}", "valve", f"Anti-icing throttle {i + 1}",
                x - 1.45, Y_EE, flow=-1,
            ))
        items.append(Equipment(f"T-{201 + i}", "expander", f"Expander stage {i + 1}", x, Y_KE, flow=-1))
    # Generator at the left end of the expander shaft, grid tie IN LINE with it; stack.
    items.append(Equipment("G-201", "generator", "Generator", ex[-1] - 3.0, Y_KE))
    items.append(Equipment("W-201", "grid", "Grid export", ex[-1] - 3.0 - 2.9, Y_KE))
    items.append(Equipment("S-201", "stack", "Exhaust\nto atmosphere", ex[-1] - STAGE_PITCH / 2 - 1.6, Y_EE))

    # ---- CAVERN (underground, on the right, shared by both trains) -------------
    x_cavern = max(cx[-1] + STAGE_PITCH / 2, x_dstart) + 4.6
    # The block valves sit ON the shared wellhead air riser (which the router runs
    # 1.4 to the right of the cavern centre), aligned on one vertical, not floating
    # over the cavern centreline where they read as disconnected.
    x_well = x_cavern + 1.4
    items.append(Equipment("V-401", "cavern", "Salt cavern", x_cavern, Y_CAVERN))
    items.append(Equipment("XV-401", "valve", "Charge block valve", x_well, Y_EC, flow=+1))
    items.append(Equipment("XV-402", "valve", "Discharge block valve", x_well, Y_EE, flow=-1))

    # ---- THERMAL STORE (adiabatic only), centred between the trains ------------
    if adiabatic:
        items.append(Equipment("TK-302", "cold_tank", "Cold coolant\ntank", X_COLD_TANK, Y_TANKS))
        # Cascade granularity is a discharge-routing choice.  Charge-side
        # returns mix into one hot store for every value of K.
        items.append(Equipment(
            "TK-301", "hot_tank", "Mixed hot coolant\ntank",
            X_HOT_TANK, Y_TANKS,
        ))
        items.append(Equipment("P-302", "pump", "Cold coolant pump", X_COLD_TANK, (Y_TANKS + Y_CHDR_C) / 2, flow=+1))
        items.append(Equipment("P-301", "pump", "Hot coolant pump", X_HOT_TANK + 2.1, Y_TANKS, flow=+1))
        extraction_x = None
        if selling:
            # ONE user exchanger takes the whole trunk off the top of the store,
            # then ONE extraction body stages what is left down to the
            # interheaters.  Left to right on the tank band, this is the
            # physical order the coolant actually travels.
            tap_x = X_HOT_TANK + 4.4
            items.append(Equipment(
                "E-302", "offtake_tap", "Heat-user HX", tap_x, Y_TANKS,
            ))
            extraction_x = tap_x + 1.45 + EXTRACTION_HALF_W
            items.append(Equipment(
                "E-304",
                "extraction_hx",
                f"Extraction HX\n{n_e} bleeds",
                extraction_x,
                Y_TANKS,
                ports=n_e,
            ))
            items.append(Equipment(
                "H-301", "heat_user", "External\nheat user",
                extraction_x + EXTRACTION_HALF_W + 3.2, Y_TANKS,
            ))
        items.append(Equipment(
            "E-303",
            "water_trim_cooler",
            (
                # The group is the COLDEST returns, so it is named by how many
                # join the manifold, not by a stage range: with E-304 the
                # returns are no longer ordered by stage.
                "Ambient recovery\n"
                + (
                    f"{result.thermal_store.cold_return_recovery_branch_count}"
                    f"/{config.expander_stages} coldest returns"
                    if result is not None
                    and result.thermal_store is not None
                    and result.thermal_store.cold_return_recovery_branch_count
                    else "bypassed"
                )
            ),
            X_COLD_TANK + 2.2,
            Y_E303_BAND if selling else Y_DHDR_C,
            flow=-1,
        ))

    xs = [e.x for e in items]
    # The water corridors are dedicated verticals kept LEFT of every symbol, so
    # no water pipe ever crosses a machine. Their position follows the actual
    # equipment extents: an expander-heavy train reaches much further left than
    # a balanced one, and a fixed corridor would end up inside the train.
    x_leftmost = min(xs)
    return Diagram(
        equipment=items,
        mode=config.mode.value,
        compressor_stages=n_c,
        expander_stages=n_e,
        has_water_loop=adiabatic,
        exports_heat=adiabatic and config.heat_offtake is not HeatOfftake.NONE,
        x_supply_corridor=x_leftmost - X_SUPPLY_CORRIDOR_OFFSET,
        x_return_corridor=x_leftmost - X_RETURN_CORRIDOR_OFFSET,
        x_min=min(xs) - 5.0,
        x_max=max(xs) + 6.4,          # room for the cavern instrument balloons
        y_min=Y_CAVERN - 2.6,
        # The grid ties now sit on the machine bands instead of on tall stubs at
        # +/-9, so the frame closes just above the compressor duty callouts.
        y_max=Y_KC + 2.9,
    )


# --------------------------------------------------------------------------- symbols

HALF_W = 0.85          # half-width of a machine body
HALF_H = 0.70          # half-height of a machine body at its TALL end
HX_R = 0.68            # heat-exchanger circle radius
TANK_W, TANK_H = 2.3, 2.2
# A multi-level store is drawn as a stack of shorter vessels occupying the same
# total height as the single tank it replaces, so nothing else in the layout has
# to move when the level count changes.


HXW, HXH = 1.9, 1.05       # counter-flow block width / height


class Machine(elm.Element):
    """Compressor (narrows in the flow direction) or expander (widens).

        COMPRESSOR  narrows in the direction of flow  (the gas is being squeezed)
        EXPANDER    widens  in the direction of flow  (the gas is letting go)

    ``widen`` picks which; ``flow`` (+1 / -1) mirrors the body for the bottom row.
    Air ties in at the two vertices on the exchanger side; ``sh_l``/``sh_r`` are
    the shaft centres, where the solid-green shaft connects one machine to the next.
    """

    def __init__(self, *args, widen: bool = False, flow: int = 1,
                 fill: str = "#e3f2fd", **kwargs):
        super().__init__(*args, **kwargs)
        x_in, x_out = -flow * HALF_W, flow * HALF_W
        h_in, h_out = (HALF_H / 2, HALF_H) if widen else (HALF_H, HALF_H / 2)
        self.segments.append(
            SegmentPoly(
                [(x_in, -h_in), (x_in, h_in), (x_out, h_out), (x_out, -h_out)],
                closed=True, fill=fill, color=INK, lw=1.4,
            )
        )
        self.anchors["center"] = (0, 0)
        self.anchors["air_in"] = (x_in, -h_in)
        self.anchors["air_out"] = (x_out, -h_out)
        self.anchors["sh_l"] = (-HALF_W, 0)
        self.anchors["sh_r"] = (HALF_W, 0)


class CounterflowHX(elm.Element):
    """Counter-flow exchanger block that faces the tank band.

    Two parallel, equidistant passes: a BLACK air line toward the machines and a
    WATER line graded ``c_l`` -> ``c_r`` toward the centre. Each pass is continuous
    with its own external pipes of the same colour (blue cold-supply meets the blue
    end, red hot-return meets the red end), so the water reads as one unbroken line
    passing through the exchanger. ``air_up`` puts the air band on top (charging,
    machines above); False puts it on the bottom (discharging, machines below).
    """

    def __init__(self, *args, c_l: str = COLD, c_r: str = HOT, air_up: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        w, h = HXW, HXH
        self.segments.append(
            SegmentPoly([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)],
                        closed=True, fill="#ffffff", color=INK, lw=1.5)
        )
        n, amp = 10, 0.16 * h
        ya, yw = (0.22 * h, -0.22 * h) if air_up else (-0.22 * h, 0.22 * h)
        xs = [-w / 2 + w * i / n for i in range(n + 1)]
        wpts = [(xs[i], yw + (amp if i % 2 else -amp)) for i in range(n + 1)]
        wpts[0], wpts[-1] = (-w / 2, yw), (w / 2, yw)          # ends flush with the pipes
        for i in range(n):
            self.segments.append(Segment([wpts[i], wpts[i + 1]], color=palette.lerp(c_l, c_r, i / (n - 1)), lw=2.0))
        apts = [(xs[i], ya + (amp if i % 2 else -amp)) for i in range(n + 1)]
        apts[0], apts[-1] = (-w / 2, ya), (w / 2, ya)
        self.segments.append(Segment(apts, color=AIR, lw=2.0))
        self.anchors["center"] = (0, 0)
        self.anchors["wat_l"] = (-w / 2, yw)
        self.anchors["wat_r"] = (w / 2, yw)
        self.anchors["air_l"] = (-w / 2, ya)
        self.anchors["air_r"] = (w / 2, ya)


def _hx_circle(ax, x, y, fc: str):
    """ISO 10628 general heat-exchanger symbol: a circle crossed by a zigzag.

    The zigzag is the tube pass. Air (or the primary fluid) runs horizontally
    through the circle; the other fluid ties in top and bottom.
    """
    from matplotlib.patches import Circle

    ax.add_patch(Circle((x, y), HX_R, facecolor=fc, edgecolor=INK, lw=1.3, zorder=4))
    span = HX_R * 0.72
    n = 4
    xs = [x - span + 2 * span * i / n for i in range(n + 1)]
    ys = [y + (span * 0.5 if i % 2 else -span * 0.5) for i in range(n + 1)]
    ax.plot(xs, ys, color=INK, lw=1.1, zorder=5, solid_joinstyle="miter")


def _air_cooler(ax, x, y):
    """Fin-fan (air-cooled) exchanger: the HX circle plus a fan and a vent arrow.

    This is what replaces every water exchanger when the plant is diabatic - the
    compression heat goes up the stack and is gone. Drawing it as a visibly
    *different* symbol from the water exchanger is the point: an engineer glancing
    at the diagram should see instantly that the heat is leaving the boundary.
    """
    from matplotlib.patches import Ellipse

    _hx_circle(ax, x, y, "#eceff1")
    ax.add_patch(Ellipse((x, y + HX_R + 0.36), 1.25, 0.32, facecolor=FILL, edgecolor=INK, lw=1.0, zorder=5))
    ax.plot([x - 0.55, x + 0.55], [y + HX_R + 0.36, y + HX_R + 0.36], color=INK, lw=0.9, zorder=6)
    ax.annotate(
        "", xy=(x, y + HX_R + 1.35), xytext=(x, y + HX_R + 0.56),
        arrowprops=dict(arrowstyle="-|>", color=VENT, lw=1.4, mutation_scale=11), zorder=5,
    )


def _ambient_heater(ax, x, y):
    """Ambient reheater: the HX circle fed by an arrow coming IN from atmosphere.

    Same shape as the fin-fan cooler but the arrow points the other way, because
    below ambient the atmosphere becomes a heat *source*. Free energy, but
    worthless exergy: it can never lift the air above ambient.
    """
    _hx_circle(ax, x, y, "#eceff1")
    ax.annotate(
        "", xy=(x, y - HX_R - 0.15), xytext=(x, y - HX_R - 1.35),
        arrowprops=dict(arrowstyle="-|>", color=VENT, lw=1.4, mutation_scale=11), zorder=5,
    )


def _dh_exchanger(ax, x, y):
    """District-heating exchanger: a water/water HX, so no fan and no vent.

    Distinct from the rejection cooler on purpose. Both take the same heat out of
    the same spent-water stream, but one SELLS it and one THROWS IT AWAY, and that
    is the single most consequential choice on this drawing - it is what separates
    an exergy product from an exergy loss.
    """
    _hx_circle(ax, x, y, "#fff3e0")


def _extraction_ports(x: float, bleeds: int) -> list[float]:
    """x of each extraction nozzle along E-304, hottest first.

    The first extraction IS the trunk inlet - E-302 has already taken everything
    above it - so nozzle zero sits on the hot face rather than inboard of it.
    The last one sits on the cold face, where the trunk is exhausted.
    """
    left = x - EXTRACTION_HALF_W
    if bleeds <= 1:
        return [left]
    span = 2.0 * EXTRACTION_HALF_W
    return [left + span * index / (bleeds - 1) for index in range(bleeds)]


def _extraction_hx(ax, x, y, bleeds: int):
    """E-304: one counter-current body, tapered, with a nozzle per extraction.

    The taper is the whole point and is drawn to scale in spirit: the body is
    tall where the trunk still carries the full inventory and thin at the last
    extraction, where the trunk has been completely withdrawn. Anyone reading
    the drawing should be able to see that this is NOT a series of exchangers
    passing the same flow along - the flow itself is disappearing into the
    nozzles.

    The counter-current arrow underneath is the coolant return, which runs the
    other way and is what absorbs the trunk's descent.
    """
    from matplotlib.patches import Polygon

    left, right = x - EXTRACTION_HALF_W, x + EXTRACTION_HALF_W
    hot_h, cold_h = EXTRACTION_HOT_HALF_H, EXTRACTION_COLD_HALF_H
    ax.add_patch(Polygon(
        [
            (left, y + hot_h), (right, y + cold_h),
            (right, y - cold_h), (left, y - hot_h),
        ],
        closed=True, facecolor="#fff3e0", edgecolor=INK, lw=1.5, zorder=4,
    ))
    # The house symbol for a heat exchanger is a zigzag tube pass, so E-304 gets
    # one too - otherwise a tapered block reads as a diffuser or a nozzle rather
    # than as the counter-current body it is. The zigzag shrinks with the shell,
    # which keeps the taper legible instead of fighting it.
    n = max(4, 2 * bleeds - 2)
    xs, ys = [], []
    for index in range(n + 1):
        fraction = index / n
        half_h = hot_h + (cold_h - hot_h) * fraction
        xs.append(left + 2.0 * EXTRACTION_HALF_W * fraction)
        ys.append(y + (0.45 if index % 2 else -0.45) * half_h)
    ax.plot(xs, ys, color=INK, lw=1.0, zorder=5, solid_joinstyle="miter")
    # Counter-current return, drawn along the body against the trunk direction.
    ax.annotate(
        "", xy=(left + 0.34, y + hot_h * 0.62),
        xytext=(right - 0.34, y + cold_h * 0.62),
        arrowprops=dict(arrowstyle="-|>", color=COLD, lw=1.1, mutation_scale=8),
        zorder=6,
    )
    for index, port_x in enumerate(_extraction_ports(x, bleeds)):
        fraction = index / max(1, bleeds - 1)
        half_h = hot_h + (cold_h - hot_h) * fraction
        # Nozzle stub on the underside, pointing at the bleed manifold.
        ax.plot(
            [port_x, port_x], [y - half_h, y - half_h - 0.14],
            color=WARM, lw=1.3, zorder=6, solid_capstyle="butt",
        )


def _heat_network(ax, x, y):
    """The district-heating network itself: a load block outside the plant boundary."""
    from matplotlib.patches import Rectangle

    ax.add_patch(Rectangle((x - 1.5, y - 0.75), 3.0, 1.5, facecolor="#fff3e0", edgecolor=HOT, lw=1.5, zorder=4))
    for k in range(3):
        yy = y - 0.36 + k * 0.36
        ax.annotate(
            "", xy=(x + 1.15, yy), xytext=(x - 1.15, yy),
            arrowprops=dict(arrowstyle="-|>", color=HOT, lw=1.0, mutation_scale=8), zorder=5,
        )


def _vessel(ax, x, y, w, h, fc: str):
    """Vertical vessel with elliptical heads - the standard tank/drum outline.

    The point order matters: trace the outline as one continuous, non-self-crossing
    loop, or the polygon fill turns the tank into an hourglass. Go from the
    top-right, over the top dome to the left, straight down the left wall, under
    the bottom dome to the right, then straight up the right wall.
    """
    from matplotlib.patches import Polygon

    a, dome = w / 2, w * 0.20
    top, bottom = y + h / 2, y - h / 2
    steps = 24

    pts = [(x + a * cos(pi * i / steps), top + dome * sin(pi * i / steps)) for i in range(steps + 1)]
    pts.append((x - a, bottom))
    pts += [(x - a * cos(pi * i / steps), bottom - dome * sin(pi * i / steps)) for i in range(steps + 1)]
    pts.append((x + a, top))
    ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor=INK, lw=1.4, zorder=4))


def _pump(ax, x, y, flow):
    """Centrifugal pump: circle with a triangle pointing the way it discharges."""
    from matplotlib.patches import Circle, Polygon

    r = 0.42
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=INK, lw=1.2, zorder=5))
    tip = (x + flow * r * 0.72, y)
    ax.add_patch(
        Polygon([(x - flow * r * 0.45, y - r * 0.55), (x - flow * r * 0.45, y + r * 0.55), tip],
                closed=True, facecolor=INK, edgecolor=INK, lw=0.8, zorder=6)
    )


def _driver(ax, x, y, letter: str):
    """Motor (M) or generator (G) - a circle with the letter, per ISA."""
    from matplotlib.patches import Circle

    ax.add_patch(Circle((x, y), 0.58, facecolor=FILL, edgecolor=SHAFT, lw=1.6, zorder=5))
    ax.text(x, y, letter, ha="center", va="center", fontsize=10, fontweight="bold", color=SHAFT, zorder=6)


def _grid(ax, x, y):
    """Grid tie-in: where ELECTRICITY crosses the plant boundary.

    Drawn as a distinct symbol from the motor/generator because the two are
    genuinely different quantities. What the grid delivers is electrical energy;
    what the shaft delivers is mechanical work. This model prices only the
    mechanical side (see PlantResult.round_trip_efficiency), so the transformer
    and the drive-train losses live in the gap between this symbol and the M/G
    circle - a gap that is real and is NOT modelled.
    """
    from matplotlib.patches import Polygon, Rectangle

    ax.add_patch(Rectangle((x - 1.5, y - 0.55), 3.0, 1.1, facecolor="#f3e5f5", edgecolor=ELEC, lw=1.5, zorder=5))
    ax.add_patch(
        Polygon([(x - 1.16, y - 0.02), (x - 0.86, y + 0.30), (x - 0.96, y + 0.02), (x - 0.66, y + 0.02),
                 (x - 1.06, y - 0.34), (x - 0.96, y - 0.02)],
                closed=True, facecolor=ELEC, edgecolor=ELEC, lw=0.6, zorder=6)
    )
    ax.text(x + 0.32, y, "GRID", ha="center", va="center", fontsize=8, fontweight="bold", color=ELEC, zorder=6)


def _valve(ax, x, y, flow):
    """Manual/block valve: the classic bowtie, drawn across the line."""
    from matplotlib.patches import Polygon

    w, h = 0.38, 0.34
    for sign in (-1, +1):
        ax.add_patch(
            Polygon([(x + sign * w, y - h), (x + sign * w, y + h), (x, y)], closed=True,
                    facecolor=FILL, edgecolor=INK, lw=1.1, zorder=5)
        )


def _filter(ax, x, y):
    """Inlet filter / silencer: hatched box, per ISO."""
    from matplotlib.patches import Rectangle

    ax.add_patch(
        Rectangle((x - 0.5, y - 0.68), 1.0, 1.36, facecolor=FILL, edgecolor=INK, lw=1.2, hatch="///", zorder=4)
    )
    ax.annotate(
        "", xy=(x - 0.56, y), xytext=(x - 2.0, y),
        arrowprops=dict(arrowstyle="-|>", color=VENT, lw=1.5, mutation_scale=12), zorder=3,
    )


def _stack(ax, x, y):
    """Exhaust stack: a slightly flared duct with the vent arrow leaving the plant."""
    from matplotlib.patches import Polygon

    ax.add_patch(
        Polygon([(x - 0.46, y - 0.78), (x + 0.46, y - 0.78), (x + 0.64, y + 0.78), (x - 0.64, y + 0.78)],
                closed=True, facecolor=FILL, edgecolor=INK, lw=1.2, zorder=4)
    )
    # Kept short: the spent-coolant return header runs across above it.
    ax.annotate(
        "", xy=(x, y + 1.55), xytext=(x, y + 0.88),
        arrowprops=dict(arrowstyle="-|>", color=VENT, lw=1.5, mutation_scale=12), zorder=3,
    )


def _cavern(ax, x, y):
    """Salt cavern below grade.

    Deliberately drawn as an irregular blob rather than a neat vessel: a solution-
    mined cavern is not a pressure vessel you bought, it is a hole you washed out
    of a salt dome, and the drawing should not pretend otherwise. The wobble
    factors are a fixed literal list so the shape is identical on every redraw -
    a diagram that shimmered as you dragged a slider would be unreadable.
    """
    from matplotlib.patches import Polygon

    wobble = [1.00, 1.09, 0.94, 1.12, 0.97, 1.06, 0.90, 1.10, 0.96, 1.04,
              0.92, 1.08, 1.00, 0.95, 1.11, 0.98, 1.05, 0.93]
    n = len(wobble)
    pts = [
        (x + 3.0 * wobble[i] * cos(2 * pi * i / n), y + 1.9 * wobble[i] * sin(2 * pi * i / n))
        for i in range(n)
    ]
    ax.add_patch(Polygon(pts, closed=True, facecolor="#eceff1", edgecolor=ROCK, lw=1.6, zorder=4))


# --------------------------------------------------------------------------- helpers


def _pipe(ax, points, color, lw=1.6, arrow_at=0.55, zorder=2, dashed=False):
    """Draw an orthogonal pipe run through ``points`` with one direction arrow.

    P&IDs use orthogonal (right-angle) routing, never diagonals, so callers pass
    the corner points and this just connects them. The single arrow goes on the
    longest segment, which keeps the drawing from turning into a hedgehog.

    ``arrow_at=None`` suppresses the arrow entirely - use it for shared bus lines
    (a shaft header, a water header) where there is no single flow direction to
    point at and a spurious arrowhead would be a lie.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ax.plot(xs, ys, color=color, lw=lw, zorder=zorder,
            linestyle="--" if dashed else "-", solid_joinstyle="miter", solid_capstyle="butt")

    if arrow_at is None:
        return

    best, best_len = 0, -1.0
    for i in range(len(points) - 1):
        seg = abs(xs[i + 1] - xs[i]) + abs(ys[i + 1] - ys[i])
        if seg > best_len:
            best, best_len = i, seg
    if best_len <= 0.3:
        return
    x0, y0, x1, y1 = xs[best], ys[best], xs[best + 1], ys[best + 1]
    tail = (x0 + (x1 - x0) * (arrow_at - 0.06), y0 + (y1 - y0) * (arrow_at - 0.06))
    head = (x0 + (x1 - x0) * arrow_at, y0 + (y1 - y0) * arrow_at)
    ax.annotate("", xy=head, xytext=tail,
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=11), zorder=zorder + 1)


def _tag(ax, x, y, text, fs, color=INK, weight="bold", va="top", ha="center"):
    ax.text(x, y, text, ha=ha, va=va, fontsize=fs, color=color, fontweight=weight, zorder=8)


def _stream_label(ax, x, y, text, fs, color=AIR):
    """Live process values, boxed so they stay legible where they cross a line."""
    ax.text(
        x, y, text, ha="center", va="center", fontsize=fs, color=color, zorder=9,
        bbox=dict(boxstyle="round,pad=0.20", facecolor="white", edgecolor=color, lw=0.6, alpha=0.94),
    )


def _balloon(ax, x, y, tag, value, fs):
    """ISA instrument balloon: a circle with the function letters over the loop number."""
    from matplotlib.patches import Circle

    ax.add_patch(Circle((x, y), 0.62, facecolor=FILL, edgecolor=MUTED, lw=1.0, zorder=6))
    ax.plot([x - 0.62, x + 0.62], [y, y], color=MUTED, lw=0.8, zorder=7)
    ax.text(x, y + 0.20, tag, ha="center", va="center", fontsize=fs * 0.85, color=MUTED, zorder=8)
    ax.text(x, y - 0.25, value, ha="center", va="center", fontsize=fs * 0.8, color=MUTED, zorder=8)


# --------------------------------------------------------------------------- render


def render(ax, config: PlantConfig, result: PlantResult | None = None, *, show_values: bool = True) -> None:
    """Paint the P&ID for ``config`` onto ``ax``, annotated with ``result``.

    ``result`` is optional: without it you get the bare schematic, which is what
    you want if the solver has just thrown (invalid input) - the user should still
    see the plant they described rather than a blank panel.

    NOT SHOWN ON THIS DRAWING, and worth knowing:
      * pump work - the water pumps are drawn because the plant has them, but their
        parasitic power is not in the energy balance anywhere. For a 100 bar plant
        this is a fraction of a percent of compression work; it is not nothing.
      * the transformer/drive-train losses between the GRID symbol and the M/G
        circle. The model's round trip is shaft-to-shaft, not grid-to-grid.
      * D-CAES throttle valves expose the pressure drop deliberately sacrificed
        when ambient reheat cannot support a frost-safe turbine expansion.
    """
    diagram = layout(config, result)
    ax.clear()

    # FILL THE CANVAS, AND STAY CENTRED. `adjustable="datalim"` tells matplotlib to
    # honour the equal aspect ratio by EXPANDING the data limits to fit the axes
    # box, rather than by shrinking the axes and leaving grey letterbox bars. The
    # expansion is symmetric, so the plant stays centred no matter how the drawing's
    # own aspect ratio changes when you add stages - which is exactly the "it should
    # re-centre when I change a value" behaviour.
    ax.set_position([0.005, 0.005, 0.99, 0.99])

    # Symbols are drawn in data coordinates and so shrink as the plant gets wider,
    # but text does not - it is measured in points. Scale the font down with the
    # drawing width, or an 8-stage plant becomes a pile of overlapping labels.
    width = diagram.x_max - diagram.x_min
    fs = max(4.5, min(9.0, 260.0 / width))

    adiabatic = diagram.has_water_loop

    compressors = _processes(result, "charging", "compression")
    coolers = _processes(result, "charging", "intercooling")
    heaters = _processes(result, "discharging", "interheating")
    ambient_heaters = _processes(result, "discharging", "ambient_reheat")
    throttles = _processes(result, "discharging", "throttling")
    expanders = _processes(result, "discharging", "expansion")

    _draw_ground(ax, diagram, fs)
    _draw_air_lines(ax, diagram, fs)
    _draw_power(ax, diagram, fs)
    if adiabatic:
        _draw_water_loop(ax, diagram, result, fs)
    else:
        # The middle band is where the thermal store WOULD be. Leaving it blank
        # reads as a drafting error; saying what is missing turns the empty space
        # into the most important statement on the diabatic drawing.
        mid = (diagram.x_min + diagram.x_max) / 2
        ax.text(
            mid, Y_TANKS,
            "NO THERMAL STORE\nall compression heat is rejected to atmosphere;\n"
            "ambient heat is recovered where available;\n"
            "unsafe anti-icing pressure drop is completed by throttling",
            ha="center", va="center", fontsize=fs * 1.1, color=VENT, style="italic", zorder=8,
            bbox=dict(boxstyle="round,pad=0.7", facecolor="#fafafa", edgecolor=VENT, lw=1.0, ls="--"),
        )
    _draw_equipment(ax, diagram, fs)

    if show_values and result is not None:
        _annotate_values(
            ax, diagram, result, compressors, coolers, heaters,
            ambient_heaters, throttles, expanders, fs,
        )
        _draw_instruments(ax, diagram, config, result, fs)
    _draw_title_block(ax, diagram, config, result, fs)
    _draw_legend(ax, diagram, fs)

    # PIN THE FRAMING LAST. `_draw_equipment` runs a schemdraw Drawing, which
    # autoscales the axis to fit only its own symbols on draw; setting the limits
    # afterwards restores the framing the layout asked for. `adjustable="datalim"`
    # honours the equal aspect ratio by EXPANDING the data limits to fill the axes
    # box rather than letterboxing, and the expansion is symmetric, so the plant
    # stays centred no matter how its aspect ratio changes as stages are added.
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlim(diagram.x_min, diagram.x_max)
    ax.set_ylim(diagram.y_min, diagram.y_max)
    ax.axis("off")


def _processes(result: PlantResult | None, cycle: str, kind: str):
    if result is None:
        return []
    source = result.charging if cycle == "charging" else result.discharging
    return [p for p in source.processes if p.kind == kind]


def _draw_ground(ax, diagram: Diagram, fs: float):
    """Grade line and overburden. The cavern is the only thing below it.

    The band is drawn absurdly wide on purpose. `adjustable="datalim"` will widen
    the visible x-range beyond diagram.x_min/x_max to fill the canvas, and a
    rectangle sized to the nominal extents would then stop short of the edges,
    leaving the ground floating in the middle of the screen. Overdraw and let the
    axes clip it.
    """
    from matplotlib.patches import Rectangle
    from matplotlib.transforms import blended_transform_factory

    span = (diagram.x_max - diagram.x_min) * 4.0
    ax.add_patch(
        Rectangle((diagram.x_min - span, diagram.y_min - span), span * 2 + (diagram.x_max - diagram.x_min),
                  span + (Y_GROUND - diagram.y_min), facecolor="#efebe9", edgecolor="none", zorder=0)
    )
    ax.plot([diagram.x_min - span, diagram.x_max + span], [Y_GROUND, Y_GROUND], color=ROCK, lw=1.6, zorder=1)

    # Anchor the caption to the left EDGE of the axes, not to a data coordinate, so
    # it stays put when the data limits expand.
    ax.text(0.012, Y_GROUND - 0.45, "grade", fontsize=fs * 0.9, color=ROCK, va="top", zorder=2,
            transform=blended_transform_factory(ax.transAxes, ax.transData))


_HX_AY = 0.22 * HXH        # air-band offset inside a counter-flow block


def _mach_air(e: Equipment) -> tuple[tuple[float, float], tuple[float, float]]:
    """The (inlet, outlet) air VERTICES on a machine's exchanger side.

    Compressors take their coolers below, so the air ties in at the BOTTOM vertices;
    expanders take their reheaters above, so the air ties in at the TOP vertices. The
    inlet is the tall face, the outlet the short one, mirrored by ``flow``.
    """
    s = -1 if e.y == Y_KC else 1
    x_in, x_out = e.x - e.flow * HALF_W, e.x + e.flow * HALF_W
    widen = e.kind == "expander"
    h_in, h_out = (HALF_H / 2, HALF_H) if widen else (HALF_H, HALF_H / 2)
    return (x_in, e.y + s * h_in), (x_out, e.y + s * h_out)


def _mach_shaft(e: Equipment) -> tuple[tuple[float, float], tuple[float, float]]:
    return (e.x - HALF_W, e.y), (e.x + HALF_W, e.y)


def _hx_air(e: Equipment) -> tuple[tuple[float, float], tuple[float, float]]:
    """The (left, right) air-pass connections of a counter-flow block. The air band
    faces the machines: on top for intercoolers (Y_EC), on the bottom for interheaters."""
    s = 1 if e.y == Y_EC else -1
    return (e.x - HXW / 2, e.y + s * _HX_AY), (e.x + HXW / 2, e.y + s * _HX_AY)


def _control_valve_air(e: Equipment) -> tuple[tuple[float, float], tuple[float, float]]:
    """The (left, right) process-air connections of a stage throttle valve."""
    return (e.x - 0.48, e.y - _HX_AY), (e.x + 0.48, e.y - _HX_AY)


def _hx_wat(e: Equipment) -> tuple[tuple[float, float], tuple[float, float]]:
    """The (left, right) water-pass connections of a block. The water band faces the
    tanks: on the bottom for intercoolers, on top for interheaters."""
    s = -1 if e.y == Y_EC else 1
    return (e.x - HXW / 2, e.y + s * _HX_AY), (e.x + HXW / 2, e.y + s * _HX_AY)


def _elbow(ax, p: tuple[float, float], q: tuple[float, float], color, lw=1.9, arrow=True):
    """A single right-angle (90 deg) air run from p to q: vertical at p, then across."""
    _pipe(ax, [p, (p[0], q[1]), q], color, lw=lw, arrow_at=0.7 if arrow else None)


def _draw_air_lines(ax, diagram: Diagram, fs: float):
    """Route the process air with 90-degree runs only, weaving each stage's air out of
    the machine's vertex, through its exchanger, and back into the next machine."""
    x_cav = diagram.by_tag("V-401").x
    comps = sorted(diagram.of_kind("compressor"), key=lambda e: e.x)
    coolers = sorted([e for e in diagram.equipment
                      if e.kind in {"water_hx", "air_cooler"} and e.y == Y_EC], key=lambda e: e.x)
    filt = diagram.by_tag("F-101")

    # filter -> first compressor inlet vertex (90 deg)
    k_in, _ = _mach_air(comps[0])
    _pipe(ax, [(filt.x + 0.5, filt.y), (k_in[0], filt.y), k_in], AIR, arrow_at=0.7)
    # weave: compressor outlet -> down into its cooler -> up into the next compressor
    for i, k in enumerate(comps):
        _, k_out = _mach_air(k)
        c_l, c_r = _hx_air(coolers[i])
        _elbow(ax, k_out, c_l, AIR)
        if i < len(comps) - 1:
            nxt_in, _ = _mach_air(comps[i + 1])
            _elbow(ax, c_r, nxt_in, AIR)
    # aftercooler -> down the well into the cavern
    _, last_r = _hx_air(coolers[-1])
    _pipe(ax, [last_r, (x_cav + 1.4, last_r[1]), (x_cav + 1.4, Y_CAVERN + 1.4)], AIR, arrow_at=0.6)

    # discharging: cavern ->
    # [AH-20x ambient reheater? -> E-20x water reheater? -> expander -> throttle?]
    # right-to-left -> stack.  The two heater kinds are mutually exclusive: the
    # adiabatic concepts have one water reheater per stage and no ambient one,
    # AD-CAES has an ambient reheater and its fuel-free trim throttle.
    seq: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i in range(diagram.expander_stages):
        ambient = diagram.by_tag(f"AH-{201 + i}")
        if ambient is not None:
            al, ar = _hx_air(ambient)
            seq.append((ar, al))
        heater = diagram.by_tag(f"E-{201 + i}")
        if heater is not None:
            hl, hr = _hx_air(heater)
            seq.append((hr, hl))                       # air enters the reheater from the right
        seq.append(_mach_air(diagram.by_tag(f"T-{201 + i}")))
        valve = diagram.by_tag(f"TV-{201 + i}")
        if valve is not None:
            vl, vr = _control_valve_air(valve)
            seq.append((vr, vl))
    _pipe(ax, [(x_cav + 1.4, Y_CAVERN + 1.4), (x_cav + 1.4, seq[0][0][1]), seq[0][0]], AIR, arrow_at=0.6)
    for (_, prev_out), (nxt_in, _) in zip(seq, seq[1:]):
        _elbow(ax, prev_out, nxt_in, AIR)
    stack = diagram.by_tag("S-201")
    _pipe(ax, [seq[-1][1], (seq[-1][1][0], stack.y), (stack.x, stack.y)], AIR, arrow_at=0.6)


def _draw_power(ax, diagram: Diagram, fs: float):
    """ELECTRICAL power (purple) crosses the boundary at the grid tie; MECHANICAL
    shaft power (SOLID green) is the shaft itself, connecting the machines from the
    motor at one end to the generator at the other. The model prices only the
    mechanical side, so the transformer/gearbox losses live in the gap between the
    purple line and the green shaft and are NOT in any reported number.
    """
    motor = diagram.by_tag("M-101")
    gen = diagram.by_tag("G-201")
    grid_in = diagram.by_tag("W-101")
    grid_out = diagram.by_tag("W-201")
    comps = sorted(diagram.of_kind("compressor"), key=lambda e: e.x)
    exps = sorted(diagram.of_kind("expander"), key=lambda e: e.x)   # left to right

    # Both grid ties are now level with their driver, so the electrical line is a
    # short horizontal run from the grid box into the motor / generator circle.
    _pipe(ax, [(grid_in.x + 1.5, grid_in.y), (motor.x - 0.58, motor.y)], ELEC, lw=1.8, arrow_at=0.6)
    _pipe(ax, [(gen.x - 0.58, gen.y), (grid_out.x + 1.5, grid_out.y)], ELEC, lw=1.8, arrow_at=0.6)

    # The shaft is a real object: a solid green line connecting the machine centres in
    # the gaps, motor at the left end of the compressor string, generator at the left
    # end of the expander string.
    def _shaft(driver, machines):
        segs = [((driver.x + 0.5, driver.y), _mach_shaft(machines[0])[0])]
        segs += [(_mach_shaft(machines[i])[1], _mach_shaft(machines[i + 1])[0]) for i in range(len(machines) - 1)]
        for p, q in segs:
            _pipe(ax, [p, q], SHAFT, lw=2.6, arrow_at=None)

    _shaft(motor, comps)
    _shaft(gen, exps)


def _bridge(ax, x, ya, yb, color, lw=1.6, arrow=True, hops=()):
    """A vertical water run from ya to yb that BRIDGES over each y in ``hops`` with a
    little arc, so a crossing of a different-fluid header reads as 'no connection'."""
    from matplotlib.patches import Arc

    step = -1 if ya > yb else 1
    ys = sorted([y for y in hops if min(ya, yb) + HOP_R < y < max(ya, yb) - HOP_R], reverse=(ya > yb))
    cur = ya
    for yh in ys:
        ax.plot([x, x], [cur, yh - step * HOP_R], color=color, lw=lw, solid_capstyle="butt", zorder=2)
        ax.add_patch(Arc((x, yh), 2 * HOP_R, 2 * HOP_R, angle=0, theta1=-90, theta2=90, color=color, lw=lw, zorder=2))
        cur = yh + step * HOP_R
    ax.plot([x, x], [cur, yb], color=color, lw=lw, solid_capstyle="round", zorder=2)
    if arrow:
        ax.annotate("", xy=(x, yb), xytext=(x, yb - step * 0.4),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=10), zorder=3)


def _draw_water_loop(ax, diagram: Diagram, result: PlantResult | None, fs: float):
    """Route the two-tank coolant circuit, center-facing.

    Every exchanger's water side faces the tanks, so each drop is short. The headers
    live between the exchanger row and the tanks; where a red drop crosses the blue
    header (or an orange drop the blue one), the crossing is bridged with a little
    arc so it reads as no connection.

        charging:  cold tank -> cold header -> intercooler (blue) ;
                   intercooler (red) -> hot header -> hot tank
        discharge without a user: hot tank -> P-301 -> turbine header (red);
        discharge with a heat user: hot tank -> P-301 -> E-302 (the whole trunk,
                   selling the top of the store) -> E-304, where one bleed per
                   expansion stage leaves along the body until the trunk is
                   exhausted; then interheater ; interheater (blue) ->
                   cold-return header -> E-303 -> final mixing -> E-304 cold
                   side -> cold tank
    """
    cold = diagram.by_tag("TK-302")
    trim_cooler = diagram.by_tag("E-303")
    hot = diagram.by_tag("TK-301")
    p_hot = diagram.by_tag("P-301")
    user_hxs = sorted(diagram.of_kind("offtake_tap"), key=lambda item: item.x)
    extraction = diagram.by_tag("E-304")
    network = diagram.by_tag("H-301")
    coolers = sorted([e for e in diagram.of_kind("water_hx") if e.y == Y_EC], key=lambda e: e.x)
    heaters = sorted([e for e in diagram.of_kind("water_hx") if e.y == Y_EE], key=lambda e: e.x)
    if not coolers:
        return
    x_ct, x_ht = cold.x, hot.x

    # --- CHARGING WATER: headers span every cooler AND reach their tank tie-in.
    wl = [_hx_wat(c)[0] for c in coolers]
    wr = [_hx_wat(c)[1] for c in coolers]
    cl0, cl1 = min([x_ct, *[p[0] for p in wl]]), max([x_ct, *[p[0] for p in wl]])
    cr0, cr1 = min([x_ht, *[p[0] for p in wr]]), max([x_ht, *[p[0] for p in wr]])
    _pipe(ax, [(x_ct, cold.y + TANK_H / 2), (x_ct, Y_CHDR_C)], COLD, lw=1.6, arrow_at=None)
    _pipe(ax, [(cl0, Y_CHDR_C), (cl1, Y_CHDR_C)], COLD, lw=1.6, arrow_at=None)
    _pipe(ax, [(cr0, Y_CHDR_H), (cr1, Y_CHDR_H)], HOT, lw=1.6, arrow_at=None)
    _pipe(ax, [(x_ht, Y_CHDR_H), (x_ht, hot.y + TANK_H / 2)], HOT, lw=1.6, arrow_at=0.6)
    for (lx, ly), (rx, ry) in zip(wl, wr):
        _bridge(ax, lx, Y_CHDR_C, ly, COLD)                      # cold supply up into wat_l
        _bridge(ax, rx, ry, Y_CHDR_H, HOT, hops=[Y_CHDR_C])      # hot return down, bridging the blue header

    if not heaters:
        return

    # --- Hot tank discharge.  The whole trunk crosses E-302, then enters E-304.
    _pipe(ax, [(x_ht + TANK_W / 2, Y_TANKS), (p_hot.x - 0.42, Y_TANKS)], HOT, lw=1.6, arrow_at=0.6)
    if user_hxs:
        _pipe(
            ax,
            [(p_hot.x + 0.42, Y_TANKS), (user_hxs[0].x - HX_R, Y_TANKS)],
            HOT,
            lw=1.6,
            arrow_at=0.6,
        )
        if extraction is not None:
            _pipe(
                ax,
                [(user_hxs[-1].x + HX_R, Y_TANKS),
                 (extraction.x - EXTRACTION_HALF_W, Y_TANKS)],
                WARM,
                lw=1.6,
                arrow_at=0.6,
            )
        supply_x = user_hxs[-1].x + HX_R + 0.5
        supply_color = WARM
    else:
        supply_x = p_hot.x + 0.9
        supply_color = HOT
        _pipe(ax, [(p_hot.x + 0.42, Y_TANKS), (supply_x, Y_TANKS)], HOT, lw=1.6, arrow_at=0.6)
    if user_hxs and network is not None:
        # The external-user stream is one counter-current pass through the one
        # exchanger: supply off the top, return in at the bottom. Both runs are
        # kept clear of E-304, which they pass over and under on their way to
        # the network block.
        user_run_up = Y_TANKS + (Y_TANKS - Y_USER_RUN)
        _pipe(ax, [(user_hxs[0].x, Y_TANKS + HX_R),
                   (user_hxs[0].x, user_run_up),
                   (network.x - 1.5, user_run_up)], HOT, lw=1.4, arrow_at=0.7)
        _pipe(ax, [(network.x - 1.5, Y_USER_RUN),
                   (user_hxs[0].x, Y_USER_RUN),
                   (user_hxs[0].x, Y_TANKS - HX_R)], COLD, lw=1.4, arrow_at=0.7)

    # --- DISCHARGING WATER: turbine-supply (orange) and cold-return (blue) headers,
    # both ABOVE the interheaters (which face the tanks with their water on top).
    hr = [_hx_wat(h)[1] for h in heaters]
    if extraction is not None:
        # One bleed per extraction nozzle, in stage order along the body. Every
        # stage owns a nozzle, so the drawing needs no grouping rule at all -
        # where two stages share a temperature the backend simply places their
        # nozzles at the same point and the two runs leave together.
        stage_heaters = sorted(heaters, key=lambda item: int(item.tag.split("-")[1]))
        ports = _extraction_ports(extraction.x, extraction.ports)
        count = len(stage_heaters)
        # One manifold per bleed, each on its own band. They cross each other
        # because the plant does: the hottest extraction is at the LEFT of the
        # body and belongs to the first expansion stage, which sits at the far
        # RIGHT of a train that flows right to left.
        #
        # The bands are ordered by how far LEFT each manifold has to reach, not
        # by stage. The one that travels furthest gets the top band, so it clears
        # E-303 and the cold tank instead of running straight through them.
        reach = sorted(
            range(count), key=lambda index: _hx_wat(stage_heaters[index])[1][0]
        )
        band_of = {stage: order for order, stage in enumerate(reach)}
        step = (
            (Y_BLEED_TOP - Y_BLEED_BOTTOM) / (count - 1) if count > 1 else 0.0
        )
        for index, heater in enumerate(stage_heaters):
            if index >= len(ports):
                break
            port_x = ports[index]
            target_x, target_y = _hx_wat(heater)[1]
            header_y = Y_BLEED_TOP - step * band_of[index]
            fraction = index / max(1, extraction.ports - 1)
            nozzle_y = Y_TANKS - (
                EXTRACTION_HOT_HALF_H
                + (EXTRACTION_COLD_HALF_H - EXTRACTION_HOT_HALF_H) * fraction
            )
            _bridge(
                ax, port_x, nozzle_y, header_y, WARM, lw=1.2, arrow=False,
                hops=[Y_USER_RUN],
            )
            _pipe(
                ax,
                [(min(port_x, target_x), header_y), (max(port_x, target_x), header_y)],
                WARM, lw=1.2, arrow_at=None,
            )
            _bridge(
                ax, target_x, header_y, target_y, WARM,
                hops=[Y_E303_BAND, Y_FINAL_HEADER],
            )
    else:
        wr0, wr1 = min([supply_x, *[p[0] for p in hr]]), max([supply_x, *[p[0] for p in hr]])
        _pipe(ax, [(supply_x, Y_TANKS), (supply_x, Y_DHDR_W)], supply_color, lw=1.6, arrow_at=None)
        _pipe(ax, [(wr0, Y_DHDR_W), (wr1, Y_DHDR_W)], supply_color, lw=1.6, arrow_at=None)
    # The solved topology has TWO return manifolds. Only the selected group
    # mixes upstream of E-303; warmer stages bypass it and join its warmed
    # outlet on the final manifold. This is the actual backend placement, not a
    # decorative label on an all-return cooler.
    #
    # The group is the COLDEST returns, which is not the same as a run of
    # consecutive stages: E-304 gives each stage its own supply, so the returns
    # are no longer ordered by stage. The selection is therefore reconstructed
    # from the solved return temperatures rather than from a stage index.
    header_y = Y_E303_BAND if extraction is not None else Y_DHDR_C
    final_y = Y_FINAL_HEADER if extraction is not None else Y_DHDR_C - 0.62
    by_stage = sorted(heaters, key=lambda item: int(item.tag.split("-")[1]))
    selected: list[Equipment] = []
    if result is not None and result.thermal_store is not None:
        count = result.thermal_store.cold_return_recovery_branch_count
        returns_k = [
            process.heat_exchanger.water_outlet_temperature_k
            for process in result.discharging.processes
            if process.kind == "interheating" and process.heat_exchanger
        ]
        if count and len(returns_k) == len(by_stage):
            coldest = sorted(
                range(len(by_stage)), key=lambda index: returns_k[index]
            )[:count]
            selected = [by_stage[index] for index in sorted(coldest)]
    bypassed = [heater for heater in by_stage if heater not in selected]

    if selected:
        selected_ports = [_hx_wat(heater)[0] for heater in selected]
        # The collection header reaches from the coldest return that joins the
        # group across to E-303, on whichever side of the drawing it sits.
        span = [trim_cooler.x, *[point[0] for point in selected_ports]]
        _pipe(
            ax,
            [(min(span), header_y), (max(span), header_y)],
            COLD, lw=1.6, arrow_at=None,
        )
        for port_x, port_y in selected_ports:
            _bridge(ax, port_x, port_y, header_y, COLD)
        _pipe(
            ax,
            [
                (trim_cooler.x - HX_R, header_y),
                (trim_cooler.x - HX_R, final_y),
            ],
            COLD,
            lw=1.6,
            arrow_at=0.7,
        )
    else:
        # Solved bypass: the body remains installed but has no active process
        # connection because no legal return suffix is below ambient.
        _tag(ax, trim_cooler.x, trim_cooler.y + 1.05, "BYPASS", fs * 0.82, MUTED)

    bypass_ports = [_hx_wat(heater)[0] for heater in bypassed]
    for port_x, port_y in bypass_ports:
        _bridge(ax, port_x, port_y, final_y, COLD)

    if extraction is None:
        # No user, no extraction body: the mixed return goes straight to the tank.
        final_right = max(
            [trim_cooler.x - HX_R, *[point[0] for point in bypass_ports]]
        )
        _pipe(ax, [(x_ct, final_y), (final_right, final_y)], COLD, lw=1.6, arrow_at=None)
        _pipe(
            ax,
            [(x_ct, final_y), (x_ct, cold.y - TANK_H / 2)],
            COLD, lw=1.6, arrow_at=0.7,
        )
    else:
        # E-304 is the LAST thing the return meets. Collect everything on the
        # final manifold, take it to the body's COLD face, run it counter to the
        # trunk, and only then drop it into the tank. Drawing it any other way
        # would put the recuperation on the wrong side of the tank and imply the
        # loop closes on the mixed return, which it does not.
        cold_face_x = extraction.x + EXTRACTION_HALF_W
        hot_face_x = extraction.x - EXTRACTION_HALF_W
        riser_x = cold_face_x + 0.62
        final_left = min(
            [trim_cooler.x - HX_R, *[point[0] for point in bypass_ports]]
        )
        _pipe(
            ax,
            [(final_left, final_y), (riser_x, final_y)],
            COLD, lw=1.6, arrow_at=0.55,
        )
        # Up past the bleed manifolds and into the body's COLD face, so the
        # return enters where the trunk is coldest and leaves where it is
        # hottest: a genuine counter-current pass, not a parallel one. The
        # manifolds it crosses are bridged, so no crossing reads as a tee.
        entry_y = Y_TANKS - EXTRACTION_COLD_HALF_H * 0.45
        crossed = [
            Y_BLEED_TOP - (Y_BLEED_TOP - Y_BLEED_BOTTOM) * index / max(1, len(heaters) - 1)
            for index in range(len(heaters))
        ]
        _bridge(
            ax, riser_x, final_y, entry_y, COLD,
            arrow=False,
            hops=[value for value in crossed if final_y < value < entry_y],
        )
        _pipe(
            ax,
            [(riser_x, entry_y), (cold_face_x, entry_y)],
            COLD, lw=1.6, arrow_at=0.7,
        )
        # Out of the hot face, under the trunk inlet, then home along its own
        # band. The return leaves E-304 warmer than it arrived, and THAT is the
        # temperature the cold tank actually receives.
        _pipe(
            ax,
            [
                (hot_face_x, Y_TANKS - EXTRACTION_HOT_HALF_H * 0.55),
                (hot_face_x - 0.35, Y_TANKS - EXTRACTION_HOT_HALF_H * 0.55),
                (hot_face_x - 0.35, Y_RECUP_RETURN),
                (x_ct, Y_RECUP_RETURN),
                (x_ct, cold.y - TANK_H / 2),
            ],
            COLD, lw=1.6, arrow_at=0.86,
        )

    for heater in heaters:
        (_, _), (rx, ry) = _hx_wat(heater)
        if extraction is None:
            _bridge(ax, rx, Y_DHDR_W, ry, supply_color, hops=[Y_DHDR_C, final_y])


# Peripheral symbols carry ISA details (hatches, atmosphere arrows, elliptical
# heads) drawn straight onto the axis with matplotlib patches. The two HERO symbols
# - flow-oriented machines and counter-flow exchanger blocks - are schemdraw
# elements, drawn onto the SAME axis so a body placed at a coordinate lands where
# the routers already expect it.
_PERIPHERAL = {
    "air_cooler": lambda ax, e: _air_cooler(ax, e.x, e.y),
    "ambient_heater": lambda ax, e: _ambient_heater(ax, e.x, e.y),
    "water_trim_cooler": lambda ax, e: _air_cooler(ax, e.x, e.y),
    "offtake_tap": lambda ax, e: _dh_exchanger(ax, e.x, e.y),
    "extraction_hx": lambda ax, e: _extraction_hx(ax, e.x, e.y, e.ports),
    "heat_user": lambda ax, e: _heat_network(ax, e.x, e.y),
    "hot_tank": lambda ax, e: _vessel(ax, e.x, e.y, TANK_W, TANK_H, "#ffebee"),
    "cold_tank": lambda ax, e: _vessel(ax, e.x, e.y, TANK_W, TANK_H, "#e3f2fd"),
    "pump": lambda ax, e: _pump(ax, e.x, e.y, e.flow),
    "motor": lambda ax, e: _driver(ax, e.x, e.y, "M"),
    "generator": lambda ax, e: _driver(ax, e.x, e.y, "G"),
    "grid": lambda ax, e: _grid(ax, e.x, e.y),
    "valve": lambda ax, e: _valve(ax, e.x, e.y, e.flow),
    "filter": lambda ax, e: _filter(ax, e.x, e.y),
    "stack": lambda ax, e: _stack(ax, e.x, e.y),
    "cavern": lambda ax, e: _cavern(ax, e.x, e.y),
}


def _draw_equipment(ax, diagram: Diagram, fs: float):
    """Paint every symbol, then its ISA tag and its plain-English name."""
    for e in diagram.equipment:
        if e.kind not in {"compressor", "expander", "water_hx"}:
            _PERIPHERAL[e.kind](ax, e)

    # The schemdraw Drawing must be finalized with an explicit ``draw(show=False)``:
    # the ``with`` form skips the render when show=False, and show=True would try to
    # pop a window under the GUI's interactive backend.
    d = schemdraw.Drawing(canvas=ax)
    for e in diagram.equipment:
        if e.kind == "compressor":
            d.add(Machine(widen=False, flow=e.flow, fill="#e3f2fd").at((e.x, e.y)).anchor("center"))
        elif e.kind == "expander":
            d.add(Machine(widen=True, flow=e.flow, fill="#e8f5e9").at((e.x, e.y)).anchor("center"))
        elif e.kind == "water_hx" and e.y == Y_EC:
            # Intercooler: air on top (toward the compressors), water graded blue->red
            # on the bottom (cold in from the cold tank, hot out to the hot tank).
            d.add(CounterflowHX(c_l=COLD, c_r=HOT, air_up=True).at((e.x, e.y)).anchor("center"))
        elif e.kind == "water_hx":
            # Interheater: air on the bottom (toward the expanders), water graded
            # blue->orange on top (cold out to the cold tank, warm turbine supply in).
            d.add(CounterflowHX(c_l=COLD, c_r=WARM, air_up=False).at((e.x, e.y)).anchor("center"))
    d.draw(show=False)

    for e in diagram.equipment:
        place_tag(ax, e, fs)


def place_tag(ax, e: Equipment, fs: float) -> None:
    """Draw one item's ISA tag (and, for vessels, its name).

    Tag placement follows normal drafting practice: inside the big vessels, beside
    anything that sits on a vertical pipe run, below everything else. Kept separate
    from the symbol drawing so the schemdraw equipment pass and the matplotlib
    peripheral pass share one set of drafting rules.
    """
    if e.kind in {"hot_tank", "cold_tank"}:
        ax.text(e.x, e.y + 0.42, e.tag, ha="center", va="center", fontsize=fs,
                fontweight="bold", color=INK, zorder=8)
        ax.text(e.x, e.y - 0.48, e.label, ha="center", va="center", fontsize=fs * 0.88, color=INK, zorder=8)
    elif e.kind == "cavern":
        ax.text(e.x, e.y + 0.35, e.tag, ha="center", va="center", fontsize=fs * 1.1,
                fontweight="bold", color=ROCK, zorder=8)
        ax.text(e.x, e.y - 0.5, e.label, ha="center", va="center", fontsize=fs * 0.95, color=ROCK, zorder=8)
    elif e.kind == "heat_user":
        ax.text(e.x, e.y - 1.05, f"{e.tag}  {e.label.replace(chr(10), ' ')}", ha="center", va="top",
                fontsize=fs * 0.9, fontweight="bold", color=HOT, zorder=8)
    elif e.kind == "grid":
        # The driver now sits to the RIGHT of the grid box, so the tag goes left.
        ax.text(e.x - 1.75, e.y, e.tag, ha="right", va="center", fontsize=fs * 0.9,
                fontweight="bold", color=ELEC, zorder=8)
    elif e.kind == "pump":
        # Pumps sit ON a vertical run, so a tag underneath lands on the header.
        ax.text(e.x + 0.62, e.y, e.tag, ha="left", va="center", fontsize=fs * 0.9,
                fontweight="bold", color=INK, zorder=8)
    elif e.kind in {"motor", "generator"}:
        # The shaft bus passes directly below the motor / above the generator,
        # so a tag under the circle lands on the line. Put it beside instead.
        ax.text(e.x + 0.78, e.y, e.tag, ha="left", va="center", fontsize=fs * 0.9,
                fontweight="bold", color=INK, zorder=8)
    elif e.kind == "valve":
        ax.text(e.x, e.y - 0.85, e.tag, ha="center", va="top", fontsize=fs * 0.9,
                fontweight="bold", color=INK, zorder=8)
    else:
        ax.text(e.x, e.y - 1.25, e.tag, ha="center", va="top", fontsize=fs,
                fontweight="bold", color=INK, zorder=8)


def _annotate_values(
    ax, diagram, result, compressors, coolers, heaters,
    ambient_heaters, throttles, expanders, fs,
):
    """Overlay the live solver output: the numbers that change as you move a slider.

    This is what makes the drawing a *simulation* view rather than a picture: every
    machine carries its specific work, every exchanger its duty, and every process
    line the temperature of the air actually in it.
    """
    for i, comp in enumerate(compressors):
        e = diagram.by_tag(f"K-{101 + i}")
        if e:
            _tag(ax, e.x, e.y + HALF_H + 0.30, f"{comp.work_j_per_kg / 1000:.0f} kJ/kg", fs * 0.95, SHAFT, va="bottom")
    for i, cool in enumerate(coolers):
        e = diagram.by_tag(f"E-{101 + i}")
        if e:
            _tag(ax, e.x, e.y + HX_R + 0.30, f"{abs(cool.heat_to_air_j_per_kg) / 1000:.0f} kJ/kg",
                 fs * 0.95, HOT if diagram.has_water_loop else VENT, va="bottom")
            # Air temperature LEAVING each cooler: the number that tells you whether
            # the exchanger is doing its job, and what the next stage has to swallow.
            _stream_label(ax, e.x + STAGE_PITCH / 2 - 0.4, Y_KC, f"{cool.outlet.temperature_c:.0f}°C", fs * 0.9)

    charge_states = result.charging.states
    _stream_label(ax, X_ORIGIN + 1.3, Y_KC - 1.5,
                  f"{charge_states[0].temperature_c:.0f} °C\n{charge_states[0].pressure_bar:.2f} bar", fs * 0.95)
    cav_in = charge_states[-1]
    _stream_label(ax, diagram.by_tag("V-401").x - 2.1, Y_KC - 1.5,
                  f"{cav_in.temperature_c:.0f} °C\n{cav_in.pressure_bar:.0f} bar", fs * 0.95)

    for i, exp in enumerate(expanders):
        e = diagram.by_tag(f"T-{201 + i}")
        if e:
            _tag(ax, e.x, e.y - HALF_H - 0.32, f"{abs(exp.work_j_per_kg) / 1000:.0f} kJ/kg", fs * 0.95, SHAFT, va="top")
    for i, heat in enumerate(heaters):
        e = diagram.by_tag(f"E-{201 + i}")
        if e:
            _tag(ax, e.x, e.y + HX_R + 0.30, f"{heat.heat_to_air_j_per_kg / 1000:.0f} kJ/kg",
                 fs * 0.95, HOT if diagram.has_water_loop else VENT, va="bottom")
            # Air temperature INTO each turbine - THE number that decides how much
            # work comes back out of the plant.
            _stream_label(ax, e.x - STAGE_PITCH / 2 + 0.4, Y_KE, f"{heat.outlet.temperature_c:.0f}°C", fs * 0.9)

    for i, heat in enumerate(ambient_heaters):
        e = diagram.by_tag(f"AH-{201 + i}")
        if e:
            _tag(
                ax, e.x, e.y + HX_R + 0.30,
                f"{heat.heat_to_air_j_per_kg / 1000:.0f} kJ/kg ambient",
                fs * 0.86, VENT, va="bottom",
            )
    for i, valve in enumerate(throttles):
        e = diagram.by_tag(f"TV-{201 + i}")
        if e:
            _tag(
                ax, e.x, e.y + 1.0,
                f"{valve.inlet.pressure_bar:.1f}→{valve.outlet.pressure_bar:.1f} bar",
                fs * 0.82, VENT, va="bottom",
            )

    # The exhaust is a real exergy loss and belongs to the exhaust stream.
    exhaust = result.discharging.outlet
    stack = diagram.by_tag("S-201")
    loss = result.exergy.loss_j_per_kg_air.get("exhaust_air", 0.0)
    # Sit the exhaust callout ABOVE the stack, in the free upper-left corner: the
    # generator's grid tie now shares the expander band, so the old spot on that band
    # collided with the GRID box.
    _stream_label(
        ax, stack.x - 1.5, Y_EE + 2.6,
        f"{exhaust.temperature_c:.0f} °C   {exhaust.pressure_bar:.2f} bar\nexergy lost: {loss / 1000:.1f} kJ/kg",
        fs * 0.9, color=VENT,
    )

    store = result.thermal_store
    trim = diagram.by_tag("E-303")
    if store and trim:
        # Keep the live duty above the fin-fan. The ordinary ISA tag is below
        # the symbol; putting both below made the two texts overlap.
        _stream_label(
            ax,
            trim.x,
            trim.y + 1.25,
            (
                f"{store.cold_return_heat_absorbed_from_ambient_j_per_kg_air / 1000:.0f}"
                " kJ/kg ambient heat\n"
            )
            + f"selected mix {store.cold_return_recovery_inlet_temperature_k - 273.15:.0f}→"
            f"{store.cold_return_recovery_outlet_temperature_k - 273.15:.0f} °C",
            fs * 0.82,
            VENT,
        )
    # E-304's solved state. The margin and the recuperated duty are the two
    # numbers that are not readable off the geometry, and the recuperation is
    # the one flow on this drawing that is neither a product nor an input - so
    # it is labelled as internal rather than left to be guessed.
    extraction = diagram.by_tag("E-304")
    solved_extraction = result.extraction_exchanger
    if extraction is not None and solved_extraction is not None:
        _stream_label(
            ax,
            extraction.x,
            Y_TANKS + EXTRACTION_HOT_HALF_H + 0.34,
            f"+{solved_extraction.margin_k:.1f} K over each stage demand   ·   "
            f"{solved_extraction.recuperated_heat_j_per_kg_air / 1000:.0f} kJ/kg "
            "recuperated (internal)\n"
            f"return {solved_extraction.return_inlet_temperature_k - 273.15:.0f}→"
            f"{solved_extraction.return_outlet_temperature_k - 273.15:.0f} °C   ·   "
            f"tightest zone approach {solved_extraction.minimum_terminal_difference_k:.1f} K",
            fs * 0.8,
            color=WARM,
        )

    # The heat user receives the band above the first extraction.  Selecting it
    # changes product vs internal recuperation, not turbine work.
    dh = result.heat_offtake
    user_hxs = sorted(diagram.of_kind("offtake_tap"), key=lambda item: item.x)
    dh_hx = user_hxs[0] if user_hxs else None
    network = diagram.by_tag("H-301")
    store = result.thermal_store
    if dh and dh_hx and network and store:
        # T_x is the optimized minimum turbine supply, fixed before heat destination.
        lines = [
            "wet-expander target: " + wet_expander_envelope_label(),
            f"trunk: {dh.hot_tank_temperature_k - 273.15:.0f} °C  →  "
            f"{dh.turbine_supply_temperature_k - 273.15:.0f} °C first extraction   "
            f"({store.total_water_mass_ratio:.2f} kg/kg-air in total)",
            f"heat sold:   {dh.heat_j_per_kg_air / 1000:.0f} kJ/kg-air in one exchanger",
            f"exergy sold: {dh.exergy_j_per_kg_air / 1000:.1f} kJ/kg-air",
            f"heat user:   {dh.return_temperature_k - 273.15:.0f} → {dh.supply_temperature_k - 273.15:.0f} °C, "
            f"{dh.network_water_per_kg_air:.2f} kg/kg-air, "
            f"HX NTU {dh.heat_exchanger_ntu:g}, minimum effectiveness margin "
            f"{dh.minimum_effectiveness_margin:.3f}",
        ]

        # The block describes the off-take branch; put it to the RIGHT of the user so it
        # no longer eats the vertical space below the tank band.
        ax.text(network.x + 1.9, Y_TANKS, "\n".join(lines), ha="left", va="center",
                fontsize=fs * 0.85,
                color=HOT,
                zorder=8,
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#fff8f6", edgecolor=HOT, lw=0.7, alpha=0.95))

        # Label the supply header with the hottest temperature any stage is bled
        # at. On a single-level plant that is the classic common T_x; on a
        # cascade it is the top of the ladder, and the rest of the ladder is
        # below it.
        _stream_label(
            ax, dh_hx.x, Y_DHDR_W + 0.9,
            f"hottest bleed {dh.turbine_supply_temperature_k - 273.15:.0f} °C",
            fs * 0.9, color=HOT,
        )


def _draw_instruments(ax, diagram, config, result, fs):
    """A few ISA instrument balloons on the streams an operator would actually watch."""
    cavern = diagram.by_tag("V-401")
    for dy, tag, value in (
        (0.9, "PI", f"{config.storage_pressure_bar:.0f}"),
        (-0.9, "TI", f"{config.ambient_temperature_c:.0f}"),
    ):
        _balloon(ax, cavern.x + 4.4, Y_CAVERN + dy, tag, value, fs)
        ax.plot([cavern.x + 2.9, cavern.x + 3.78], [Y_CAVERN + dy, Y_CAVERN + dy],
                color=MUTED, lw=0.8, ls="--", zorder=5)

    if result.thermal_store:
        # The two tank temperatures are the whole story of the thermal store: how
        # hot the water got, and how cold it has to come back.
        #
        # Balloons go to the LEFT of each tank. The hot tank's RIGHT side is now the
        # district-heating tap, and an instrument bubble sitting on that line would
        # read as a process connection.
        store = result.thermal_store
        hot = diagram.by_tag("TK-301")
        cold = diagram.by_tag("TK-302")
        for tank, value in (
            (hot, f"{store.hot_temperature_available_k - 273.15:.0f}"),
            (cold, f"{store.cold_temperature_k - 273.15:.0f}"),
        ):
            _balloon(ax, tank.x - 2.3, Y_TANKS, "TI", value, fs)
            ax.plot([tank.x - 1.68, tank.x - TANK_W / 2], [Y_TANKS, Y_TANKS],
                    color=MUTED, lw=0.8, ls="--", zorder=5)


def _draw_title_block(ax, diagram, config, result, fs):
    """Title block, pinned to the TOP-RIGHT corner of the canvas.

    Pinned in AXES coordinates, not data coordinates: `adjustable="datalim"` moves
    the visible data window around to fill the canvas, so anything anchored to
    x_max would drift inward and, at some stage counts, land on top of the cavern.
    """
    lines = [
             f"PLANT CONCEPT: {plant_concept_label(diagram.mode, exports_heat=diagram.exports_heat)}",
             f"{diagram.compressor_stages}x compression / {diagram.expander_stages}x expansion"]
    if diagram.has_water_loop:
        lines.append(
            "TES: 1 mixed hot tank + 1 mixed cold tank, "
            f"counterflow NTU={config.heat_exchanger_ntu:g}"
        )
        if diagram.exports_heat:
            lines.append(
                f"E-302 heat-user HX (whole trunk) NTU="
                f"{config.heat_user_exchanger_ntu:g}"
            )
            lines.append(
                f"E-304 extraction HX: {diagram.expander_stages} bleeds, "
                f"per-zone NTU={config.extraction_exchanger_ntu:g}"
            )
        lines.append(
            f"E-303 ambient exchanger NTU={config.cold_return_cooler_ntu:g}"
            " (heat-only, coldest returns)"
        )
        lines.append(
            "Heat off-take: external user"
            if diagram.exports_heat else "Heat off-take: none"
        )
        lines.append("Reheat: coolant loop only; no ambient scavenging")
    else:
        lines.append("TES: none - heat rejected to atmosphere")
        lines.append("Fuel: none; frost control by turbine + throttle")
        lines.append("Ambient reheat: mandatory (icing-safe AD-CAES operation)")
    lines.append("Lower envelope: " + wet_expander_envelope_label())
    if result is not None:
        lines.append(f"Electrical RTE:     {result.round_trip_efficiency:6.1%}")
        lines.append(f"Useful-energy ratio:{result.useful_energy_delivery_ratio:6.1%}")
        lines.append(f"Total exergy eff.:  {result.exergy.total_useful_exergy_efficiency:6.1%}")

    ax.text(
        0.995, 0.995, "\n".join(lines), transform=ax.transAxes,
        ha="right", va="top", fontsize=fs * 0.95, color=INK, family="monospace", zorder=11,
        bbox=dict(boxstyle="square,pad=0.6", facecolor="white", edgecolor=INK, lw=1.2),
    )


def _draw_legend(ax, diagram, fs):
    """Colour key, pinned to the BOTTOM-LEFT corner (also in axes coordinates)."""
    key = [
        ("process air", AIR),
        ("hot coolant", HOT),
        ("optimized turbine-supply coolant", WARM),
        ("cold coolant", COLD),
        ("mechanical shaft power", SHAFT),
        ("electrical power (grid)", ELEC),
        ("atmosphere", VENT),
    ]
    if not diagram.has_water_loop:
        key = [("process air", AIR), ("mechanical shaft power", SHAFT),
               ("electrical power (grid)", ELEC),
               ("atmosphere", VENT)]

    handles = [
        ax.plot([], [], color=color, lw=2.6 if color is SHAFT else 2.2, ls="-", label=name)[0]
        for name, color in key
    ]
    legend = ax.legend(
        handles=handles, loc="lower left", bbox_to_anchor=(0.005, 0.005),
        fontsize=fs * 0.95, frameon=True, framealpha=0.95, borderpad=0.7, labelspacing=0.55,
    )
    legend.set_zorder(11)
    legend.get_frame().set_edgecolor(INK)


def save(config: PlantConfig, result: PlantResult | None, path) -> "object":
    """Render the P&ID straight to a file. Used by the CLI and the tests."""
    from pathlib import Path

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    diagram = layout(config, result)
    width = diagram.x_max - diagram.x_min
    height = diagram.y_max - diagram.y_min
    scale = 0.46
    fig, ax = plt.subplots(figsize=(max(13.0, width * scale), max(8.0, height * scale)), dpi=140)
    render(ax, config, result)
    fig.savefig(output, dpi=140, facecolor="white")
    plt.close(fig)
    return output
