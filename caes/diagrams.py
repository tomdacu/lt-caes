"""Thermodynamic diagrams: cycle traces and per-exchanger composite curves.

WHY THERE IS NO T-h DIAGRAM HERE
--------------------------------
There used to be, and it was useless. For air, enthalpy is very nearly a function
of temperature ALONE: at 150 C, h moves only from 550.8 to 542.9 kJ/kg as pressure
goes from 1 bar to 100 bar - 1.4%. So a T-h plot collapses onto a single straight
line, and the charging and discharging traces lie on top of each other. It was
drawing correctly; it just carried no information the temperature axis did not
already have. T-h earns its keep in refrigeration, where the two-phase dome gives
it structure. For a near-ideal gas it is dead weight.

It is replaced by two diagrams that DO say something:

  h-s (Mollier)   - the vertical distance between the real and ideal end points IS
                    the turbomachinery loss. You can read the isentropic efficiency
                    straight off the chart.

  T-Q composites  - one panel per heat exchanger, air profile against coolant profile
                    versus cumulative duty. The GAP between the two curves is the
                    driving temperature difference, and its narrowest point is the
                    minimum approach. This is the diagram that shows you WHY the exchangers
                    destroy the exergy they do, and it is the one an engineer sizing
                    real hardware actually needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, degrees, exp, hypot, log

from CoolProp.CoolProp import PropsSI

from .models import PlantResult, Process
from .nomenclature import plant_concept_label
from .moisture import phase_change_temperature_k
from .constants import WATER_FREEZING_TEMPERATURE_K
from .thermal_limits import EXPANDER_ICE_MARGIN_K, minimum_wet_expander_temperature_k

CHARGE_COLOR = "#c62828"
DISCHARGE_COLOR = "#1565c0"
AIR_COLOR = "#37474f"
WATER_COLOR = "#1565c0"
APPROACH_COLOR = "#ef6c00"
HOT_REFERENCE_COLOR = "#c62828"
COLD_REFERENCE_COLOR = "#0277bd"
SUPPLY_REFERENCE_COLOR = "#ef6c00"
RETURN_REFERENCE_COLOR = "#6a1b9a"
NETWORK_COLOR = "#00897b"
PRESSURE_REFERENCE_COLOR = "#78909c"
MOISTURE_SURFACE_COLOR = "#ef6c00"
DEW_POINT_COLOR = "#00838f"
FROST_POINT_COLOR = "#6a1b9a"
PRESSURE_CLUSTER_RATIO = 1.03


# --------------------------------------------------------------------------- cycle plots


def draw_ts(ax, result: PlantResult, fluid: str = "Air") -> None:
    """Temperature-entropy. The classic: area under a reversible path is heat."""
    _draw_cycle(
        ax, result,
        x=lambda s: s.entropy_j_per_kgk / 1000,
        y=lambda s: s.temperature_c,
        xlabel="Specific entropy  [kJ/(kg·K)]",
        ylabel="Temperature  [°C]",
        title="T-s", diagram_kind="ts", fluid=fluid,
    )


def draw_hs(ax, result: PlantResult, fluid: str = "Air") -> None:
    """Enthalpy-entropy (Mollier).

    The diagram to read turbomachinery on. A reversible machine moves straight UP or
    DOWN (constant s); every degree of rightward drift is entropy generated, and the
    enthalpy you failed to convert is the vertical shortfall against that ideal. So
    the horizontal spread of the compression and expansion legs IS the loss, visible
    without computing anything.
    """
    _draw_cycle(
        ax, result,
        x=lambda s: s.entropy_j_per_kgk / 1000,
        y=lambda s: s.enthalpy_j_per_kg / 1000,
        xlabel="Specific entropy  [kJ/(kg·K)]",
        ylabel="Specific enthalpy  [kJ/kg]",
        title="h-s (Mollier)", diagram_kind="hs", fluid=fluid,
    )


def draw_ph(ax, result: PlantResult, fluid: str = "Air") -> None:
    """Pressure-enthalpy, log pressure. Shows the pressure staging at a glance."""
    _draw_cycle(
        ax, result,
        x=lambda s: s.enthalpy_j_per_kg / 1000,
        y=lambda s: s.pressure_bar,
        xlabel="Specific enthalpy  [kJ/kg]",
        ylabel="Pressure  [bar]",
        title="p-h",
        log_y=True, diagram_kind="ph", fluid=fluid,
    )


def pressure_reference_levels(result: PlantResult) -> list[float]:
    """Representative cycle pressures in Pa, with near-equal HX levels merged.

    The air pressure changes only slightly through each heat exchanger. Drawing
    both sides of every small pressure drop would produce pairs of almost
    indistinguishable isobars, so levels within three percent are grouped and an
    actual state pressure near the middle of each group is retained.
    """
    states = result.charging.states + result.discharging.states
    candidates = [state.pressure_pa for state in states]
    for cycle in (result.charging, result.discharging):
        for process in cycle.processes:
            if process.kind in {"compression", "expansion"}:
                candidates.extend((process.inlet.pressure_pa, process.outlet.pressure_pa))

    unique = sorted(set(candidates))
    clusters: list[list[float]] = []
    for pressure in unique:
        if not clusters or pressure / clusters[-1][-1] > PRESSURE_CLUSTER_RATIO:
            clusters.append([pressure])
        else:
            clusters[-1].append(pressure)
    return [cluster[len(cluster) // 2] for cluster in clusters]


def _draw_pressure_references(ax, result: PlantResult, diagram_kind: str, fluid: str):
    """Draw real-air isobars spanning the temperatures reached by the cycle."""
    states = result.charging.states + result.discharging.states
    temperatures = [state.temperature_k for state in states]
    padding = max(8.0, 0.04 * (max(temperatures) - min(temperatures)))
    t_min, t_max = min(temperatures) - padding, max(temperatures) + padding
    temperature_samples = [t_min + i * (t_max - t_min) / 44 for i in range(45)]

    references = []
    for pressure in pressure_reference_levels(result):
        try:
            # CoolProp's vector interface evaluates the complete isobar in one
            # state update and is far quicker than one call per plotted point.
            entropy = list(PropsSI("S", "P", pressure, "T", temperature_samples, fluid) / 1000)
            enthalpy = list(PropsSI("H", "P", pressure, "T", temperature_samples, fluid) / 1000)
            valid_temperatures = temperature_samples
        except ValueError:
            # Retain any valid part of an isobar if a backend has a narrower
            # temperature range than real-air CoolProp.
            entropy, enthalpy, valid_temperatures = [], [], []
            for temperature in temperature_samples:
                try:
                    entropy.append(PropsSI("S", "P", pressure, "T", temperature, fluid) / 1000)
                    enthalpy.append(PropsSI("H", "P", pressure, "T", temperature, fluid) / 1000)
                    valid_temperatures.append(temperature)
                except ValueError:
                    continue
        if len(valid_temperatures) < 2:
            continue

        if diagram_kind == "ts":
            x_values = entropy
            y_values = [temperature - 273.15 for temperature in valid_temperatures]
        elif diagram_kind == "hs":
            x_values, y_values = entropy, enthalpy
        else:
            x_values = enthalpy
            y_values = [pressure / 1e5] * len(enthalpy)

        line, = ax.plot(
            x_values, y_values, color=PRESSURE_REFERENCE_COLOR, lw=0.7,
            alpha=0.55, zorder=0, label="_nolegend_",
        )
        line.set_gid("pressure-reference")
        references.append((line, pressure))
    return references


def _label_pressure_references(ax, references, diagram_kind: str) -> None:
    """Put compact labels directly on isobars, following their screen angle."""
    transform = ax.transData
    inverse = transform.inverted()
    for index, (line, pressure) in enumerate(references):
        x_values, y_values = line.get_xdata(), line.get_ydata()
        fraction = 0.68 + 0.08 * (index % 3)
        position = min(len(x_values) - 2, max(0, round(fraction * (len(x_values) - 1))))

        first = transform.transform((x_values[position], y_values[position]))
        second = transform.transform((x_values[position + 1], y_values[position + 1]))
        angle = degrees(atan2(second[1] - first[1], second[0] - first[0]))
        # A small display-space lift keeps the label from sitting on the guide.
        label_point = inverse.transform((first[0], first[1] + 3.0))
        label = ax.text(
            label_point[0], label_point[1], f"{pressure / 1e5:.3g} bar",
            color=PRESSURE_REFERENCE_COLOR, fontsize=6.5,
            rotation=0 if diagram_kind == "ph" else angle,
            rotation_mode="anchor", ha="left", va="bottom", zorder=1.2,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.68, pad=0.2),
        )
        label.set_gid("pressure-reference-label")


def _draw_direction_arrows(ax, line, color: str, cycle_name: str) -> None:
    """Overlay one arrowhead on every state-to-state process segment."""
    x_values, y_values = line.get_xdata(), line.get_ydata()
    transform = ax.transData
    inverse = transform.inverted()
    for start, end in zip(zip(x_values[:-1], y_values[:-1]), zip(x_values[1:], y_values[1:])):
        start_display = transform.transform(start)
        end_display = transform.transform(end)
        dx, dy = end_display - start_display
        if hypot(dx, dy) < 12.0:
            continue
        tail = inverse.transform(start_display + 0.42 * (end_display - start_display))
        head = inverse.transform(start_display + 0.60 * (end_display - start_display))
        arrow = ax.annotate(
            "", xy=head, xytext=tail,
            arrowprops=dict(
                arrowstyle="-|>", color=color, lw=1.35, mutation_scale=9,
                shrinkA=0, shrinkB=0,
            ),
            zorder=4,
        )
        arrow.set_gid(f"cycle-direction-{cycle_name}")


def _level_color(index: int, count: int) -> str:
    """Blend the cold-TES blue into the hot-TES red across the level ladder.

    The colour carries the level's GRADE, so the reader can see at a glance
    which isotherm belongs near the top of the store and which near the bottom
    without reading any label.  With one level the blend collapses to the hot
    reference colour, so a single-tank plant looks exactly as it always did.
    """
    if count <= 1:
        return HOT_REFERENCE_COLOR
    cold = (0x02, 0x77, 0xbd)
    hot = (0xc6, 0x28, 0x28)
    fraction = index / (count - 1)
    return "#" + "".join(
        f"{round(low + (high - low) * fraction):02x}"
        for low, high in zip(cold, hot)
    )


def thermal_reference_temperatures(result: PlantResult) -> list[tuple[str, float, str]]:
    """Coolant-loop isotherms to overlay on the cycle plots.

    Every temperature the solved coolant loop actually holds gets a line: the
    cold tank, each hot level, the interheater supplies, and the distinct cold
    returns leaving those interheaters.  The return levels are especially
    important for the proposed branchwise ambient-recovery topology: they show
    which branches lie below ambient without pretending that the current result
    already contains separate post-ambient states.

    Duplicate isotherms are dropped rather than drawn on top of each other: a
    single-level store's level line and its hot-tank line are the same number.
    """
    store = result.thermal_store
    if store is None:
        return []
    levels = store.hot_level_temperatures_k or (store.hot_temperature_available_k,)
    references: list[tuple[str, float, str]] = [
        ("cold TES", store.cold_temperature_k, COLD_REFERENCE_COLOR),
    ]
    count = len(levels)
    for index, temperature_k in enumerate(levels):
        label = "hot TES" if count == 1 else f"TES level {index + 1}/{count}"
        references.append((label, temperature_k, _level_color(index, count)))

    # What the turbines are actually served at: with E-304 this is one
    # extraction temperature per expansion stage. Only the distinct ones are
    # worth a line - where the demand profile forces two stages onto one nozzle
    # they coincide, and drawing that twice would suggest a level that is not
    # there.
    supplies: list[float] = []
    for process in result.discharging.processes:
        if process.kind != "interheating" or not process.heat_exchanger:
            continue
        supply_k = round(process.heat_exchanger.water_inlet_temperature_k, 6)
        if supply_k not in supplies:
            supplies.append(supply_k)
    for index, supply_k in enumerate(supplies):
        if any(abs(supply_k - value) < 1e-6 for _, value, _ in references):
            continue
        label = (
            f"E-304 extraction {index + 1}/{len(supplies)}"
            if len(supplies) > 1
            else "coolant supply to interheaters"
        )
        references.append((label, supply_k, SUPPLY_REFERENCE_COLOR))

    returns: list[float] = []
    for process in result.discharging.processes:
        if process.kind != "interheating" or not process.heat_exchanger:
            continue
        return_k = round(process.heat_exchanger.water_outlet_temperature_k, 6)
        if return_k not in returns:
            returns.append(return_k)
    for index, return_k in enumerate(returns):
        if any(abs(return_k - value) < 1e-6 for _, value, _ in references):
            continue
        references.append((
            f"coolant return stage {index + 1}/{len(returns)}",
            return_k,
            RETURN_REFERENCE_COLOR,
        ))
    return references


def _draw_temperature_references(ax, result: PlantResult, diagram_kind: str, fluid: str) -> None:
    """Draw real-air isotherms at the three coolant-loop reference temperatures."""
    references = thermal_reference_temperatures(result)
    if not references:
        return
    states = result.charging.states + result.discharging.states
    p_min = min(state.pressure_pa for state in states)
    p_max = max(state.pressure_pa for state in states)
    pressures = [exp(log(p_min) + i * (log(p_max) - log(p_min)) / 35) for i in range(36)]
    for label, temperature_k, color in references:
        entropy: list[float] = []
        enthalpy: list[float] = []
        valid_pressures: list[float] = []
        for pressure in pressures:
            try:
                entropy.append(PropsSI("S", "P", pressure, "T", temperature_k, fluid) / 1000)
                enthalpy.append(PropsSI("H", "P", pressure, "T", temperature_k, fluid) / 1000)
                valid_pressures.append(pressure / 1e5)
            except ValueError:
                continue
        if not valid_pressures:
            continue
        if diagram_kind == "ts":
            x_values, y_values = entropy, [temperature_k - 273.15] * len(entropy)
        elif diagram_kind == "hs":
            x_values, y_values = entropy, enthalpy
        else:
            x_values, y_values = enthalpy, valid_pressures
        ax.plot(
            x_values, y_values, linestyle=":", linewidth=1.35, color=color, alpha=0.9,
            # An empty label means "same family as the line above": the ladder
            # gets one legend entry, not one per rung.
            label=(
                f"{label}  {temperature_k - 273.15:.1f} °C" if label
                else "_nolegend_"
            ),
            zorder=1,
        )


def _moisture_boundary_coordinates(
    result: PlantResult,
    humidity_ratio: float,
    diagram_kind: str,
    fluid: str,
    temperature_offset_k: float = 0.0,
    wet_expander_lower_envelope: bool = False,
) -> tuple[list[float], list[float], list[float]]:
    """Return coordinates for a phase line or wet-expander lower envelope."""

    states = result.charging.states + result.discharging.states
    p_min = min(state.pressure_pa for state in states)
    p_max = max(state.pressure_pa for state in states)
    pressures = [
        exp(log(p_min) + i * (log(p_max) - log(p_min)) / 71)
        for i in range(72)
    ]
    x_values: list[float] = []
    y_values: list[float] = []
    temperatures_c: list[float] = []
    for pressure in pressures:
        try:
            if wet_expander_lower_envelope:
                temperature_k = minimum_wet_expander_temperature_k(
                    pressure,
                    humidity_ratio,
                )
            else:
                temperature_k = (
                    phase_change_temperature_k(pressure, humidity_ratio)
                    + temperature_offset_k
                )
            entropy = PropsSI("S", "P", pressure, "T", temperature_k, fluid) / 1000
            enthalpy = PropsSI("H", "P", pressure, "T", temperature_k, fluid) / 1000
        except ValueError:
            continue
        temperature_c = temperature_k - 273.15
        if diagram_kind == "ts":
            x_value, y_value = entropy, temperature_c
        elif diagram_kind == "hs":
            x_value, y_value = entropy, enthalpy
        else:
            x_value, y_value = enthalpy, pressure / 1e5
        x_values.append(x_value)
        y_values.append(y_value)
        temperatures_c.append(temperature_c)
    return x_values, y_values, temperatures_c


def _draw_moisture_boundaries(
    ax,
    result: PlantResult,
    diagram_kind: str,
    fluid: str,
) -> None:
    """Overlay surface-separator and stored-air condensation/icing limits."""

    moisture = result.moisture
    if moisture is None:
        return

    # One ratio, one meaning: the vapour leaving the last charge-side
    # cooler/separator is simultaneously the cavern inventory and the basis the
    # wet-expander envelope is evaluated against.
    stored_ratio = moisture.stored_air_water_vapor_kg_per_kg_dry_air
    x_values, y_values, _ = _moisture_boundary_coordinates(
        result,
        stored_ratio,
        diagram_kind,
        fluid,
        wet_expander_lower_envelope=True,
    )
    if len(x_values) >= 2:
        line, = ax.plot(
            x_values,
            y_values,
            color=MOISTURE_SURFACE_COLOR,
            linestyle="-.",
            linewidth=1.25,
            alpha=0.9,
            label=(
                "wet-rated lower envelope: "
                f"{WATER_FREEZING_TEMPERATURE_K - 273.15 + EXPANDER_ICE_MARGIN_K:.0f} °C liquid"
                f" / frost + {EXPANDER_ICE_MARGIN_K:.0f} K"
            ),
            zorder=1.4,
        )
        line.set_gid("moisture-wet-expander-lower-boundary")

    x_values, y_values, temperatures_c = _moisture_boundary_coordinates(
        result, stored_ratio, diagram_kind, fluid
    )
    for phase, predicate, color, label in (
        ("dew", lambda value: value >= 0.0, DEW_POINT_COLOR, "stored-air pressure dew point"),
        ("frost", lambda value: value < 0.0, FROST_POINT_COLOR, "stored-air frost point"),
    ):
        selected = [
            (x_value, y_value)
            for x_value, y_value, temperature_c in zip(
                x_values, y_values, temperatures_c
            )
            if predicate(temperature_c)
        ]
        if len(selected) < 2:
            continue
        line, = ax.plot(
            [point[0] for point in selected],
            [point[1] for point in selected],
            color=color,
            linestyle="--",
            linewidth=1.6,
            alpha=0.95,
            label=label,
            zorder=1.6,
        )
        line.set_gid(f"moisture-{phase}-boundary")


def _draw_cycle(
    ax, result, x, y, xlabel, ylabel, title, log_y=False,
    diagram_kind: str = "ts", fluid: str = "Air",
) -> None:
    ax.clear()
    if log_y:
        ax.set_yscale("log")
    pressure_references = _draw_pressure_references(ax, result, diagram_kind, fluid)
    _draw_temperature_references(ax, result, diagram_kind, fluid)
    _draw_moisture_boundaries(ax, result, diagram_kind, fluid)
    cycle_lines = []
    for cycle, color in ((result.charging, CHARGE_COLOR), (result.discharging, DISCHARGE_COLOR)):
        states = cycle.states
        line, = ax.plot(
            [x(s) for s in states], [y(s) for s in states], "o-",
            color=color, label=cycle.name, markersize=4, lw=1.6, zorder=3,
        )
        cycle_lines.append((line, color, cycle.name))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}  ·  electrical RTE {result.round_trip_efficiency:.1%}")
    ax.relim()
    ax.autoscale_view()
    _label_pressure_references(ax, pressure_references, diagram_kind)
    for line, color, cycle_name in cycle_lines:
        _draw_direction_arrows(ax, line, color, cycle_name)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)


# --------------------------------------------------------------------------- composites


# The panels live in a wide GUI tab, so a landscape grid (more columns than rows)
# uses the space best. 1.6 is roughly the shape of the tab.
TARGET_ASPECT = 1.6
# Cost of an empty cell, in the same units as the aspect error. Blanks are allowed -
# a 3x4 grid holding 10 panels beats a 1x10 strip of unreadable slivers - but they
# are not free, so a layout that wastes two cells has to earn it with better shape.
BLANK_PENALTY = 0.35


def grid_shape(count: int) -> tuple[int, int]:
    """Pick a (rows, cols) panel grid for ``count`` exchangers.

    Searches every candidate row count and scores it on two things an eye actually
    cares about: how close the grid is to the tab's aspect ratio, and how many cells
    it wastes. That reproduces the layouts you would choose by hand -

        1..3 -> a single row        4 -> 2x2        6 -> 2x3
        8    -> 2x4                 9 -> 3x3       10 -> 2x5
        12   -> 3x4                16 -> 4x4

    - rather than the naive ``ceil(sqrt(n))``, which would put 8 panels in a 3x3 grid
    and leave a hole, or a naive single row, which turns 10 exchangers into slivers.
    """
    if count <= 0:
        return (1, 1)
    if count <= 3:
        return (1, count)   # a single row genuinely is best here; no search needed

    best, best_score = (1, count), float("inf")
    for rows in range(1, count + 1):
        cols = ceil(count / rows)
        blanks = rows * cols - count
        score = abs(cols / rows - TARGET_ASPECT) + BLANK_PENALTY * blanks
        if score < best_score:
            best, best_score = (rows, cols), score
    return best


def exchangers(result: PlantResult) -> list[tuple[str, Process]]:
    """Every coolant-coupled exchanger in the plant, tagged to match the P&ID.

    Air-cooled and ambient exchangers are excluded: they have no second stream to
    plot against, so a composite curve of them would just be the air profile alone.
    """
    found: list[tuple[str, Process]] = []
    charge = [p for p in result.charging.processes if p.kind == "intercooling" and p.heat_exchanger]
    discharge = [p for p in result.discharging.processes if p.kind == "interheating" and p.heat_exchanger]
    for i, process in enumerate(charge):
        found.append((f"E-{101 + i}", process))
    for i, process in enumerate(discharge):
        found.append((f"E-{201 + i}", process))
    return found


def _mark_minimum_approach(ax, x_values, index: int, hot, cold) -> None:
    """Draw and label the narrowest gap, without letting the label leave the axis.

    The pinch is very often AT an end of the exchanger - a balanced
    counter-current pair has its minimum at whichever end the capacity rates
    make it - so a centred label there hangs half outside the panel and gets
    clipped to something like "pproach 101.9 K". Anchor the text on the side
    that keeps it inside instead.
    """
    span = x_values[-1] - x_values[0]
    position = x_values[index]
    ax.plot([position] * 2, [hot[index], cold[index]],
            color=APPROACH_COLOR, lw=1.6, ls="--", zorder=3)
    if position <= x_values[0] + 0.2 * span:
        alignment = "left"
    elif position >= x_values[-1] - 0.2 * span:
        alignment = "right"
    else:
        alignment = "center"
    ax.annotate(
        f"minimum approach {hot[index] - cold[index]:.1f} K",
        xy=(position, 0.5 * (hot[index] + cold[index])),
        fontsize=7, color=APPROACH_COLOR, ha=alignment,
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=APPROACH_COLOR, lw=0.6, alpha=0.9),
    )


def draw_composite(ax, tag: str, process: Process, fluid: str) -> None:
    """T-Q composite curves for ONE counter-current exchanger.

    Both streams are plotted against CUMULATIVE DUTY (0 -> Q_total), which is the
    coordinate that makes a counter-flow exchanger legible: at any x you are looking
    at the same physical cross-section of the tube bundle, so the VERTICAL GAP between
    the two curves is the local driving temperature difference at that point.

    Reading the picture:

      * the two curves must never touch or cross - that would be heat flowing from
        cold to hot, and the second law forbids it;
      * where they come closest is the minimum terminal approach. That is the bottleneck that caps
        the duty, and it is where the exchanger destroys most of its exergy;
      * the AIR curve is not straight. Water's cp is essentially constant, so its
        profile is a straight line, but air's cp varies with temperature and pressure,
        so its profile bends. That curvature is why the model integrates real enthalpy
        rather than assuming cp - see caes.heat_exchangers.

    The air profile is reconstructed by walking enthalpy linearly from inlet to outlet
    (which is exactly what the duty coordinate means) and asking CoolProp for the
    temperature at each step. That makes this a genuine plot of the solved state, not
    a straight line drawn between two endpoints.
    """
    hx = process.heat_exchanger
    ax.clear()

    duty = hx.duty_j_per_kg_air
    if duty <= 0:
        ax.text(0.5, 0.5, f"{tag}\nbypassed\n(no duty)", ha="center", va="center",
                transform=ax.transAxes, fontsize=8, color="#90a4ae")
        ax.set_xticks([])
        ax.set_yticks([])
        return

    cooling = process.kind == "intercooling"
    steps = 30

    # AIR SIDE. Enthalpy moves linearly with cumulative duty by definition; pressure is
    # interpolated across the (small) exchanger pressure drop.
    h_in, h_out = process.inlet.enthalpy_j_per_kg, process.outlet.enthalpy_j_per_kg
    p_in, p_out = process.inlet.pressure_pa, process.outlet.pressure_pa
    air_q, air_t = [], []
    for i in range(steps + 1):
        f = i / steps
        h = h_in + (h_out - h_in) * f
        p = p_in + (p_out - p_in) * f
        air_q.append(duty * f)
        air_t.append(PropsSI("T", "P", p, "H", h, fluid) - 273.15)

    # In a COUNTER-flow exchanger the streams run opposite ways, so as we walk the air
    # from its inlet to its outlet we walk the water from its OUTLET back to its inlet.
    # Plotting both against the same cumulative-duty axis is what lines up the physical
    # cross-sections - and it is why the water line below is drawn from outlet to inlet.
    t_w_in, t_w_out = hx.water_inlet_temperature_k - 273.15, hx.water_outlet_temperature_k - 273.15
    water_t = [t_w_out + (t_w_in - t_w_out) * (i / steps) for i in range(steps + 1)]
    water_q = [duty * (i / steps) for i in range(steps + 1)]

    hot_t, cold_t = (air_t, water_t) if cooling else (water_t, air_t)
    approach = [h - c for h, c in zip(hot_t, cold_t)]
    minimum_approach = min(approach)
    approach_at = approach.index(minimum_approach)

    ax.plot([q / 1000 for q in air_q], air_t, color=AIR_COLOR, lw=1.8, label="air")
    ax.plot([q / 1000 for q in water_q], water_t, color=WATER_COLOR, lw=1.8, label="water")
    ax.fill_between([q / 1000 for q in air_q], air_t, water_t, color="#eceff1", alpha=0.7, zorder=0)

    # Mark the narrowest solved temperature gap.
    _mark_minimum_approach(
        ax, [q / 1000 for q in air_q], approach_at, hot_t, cold_t
    )

    role = "intercooler" if cooling else "interheater"
    ax.set_title(
        f"{tag} · {role} · NTU={hx.ntu:g} · ε={hx.effectiveness:.2f}\n"
        f"{duty / 1000:.0f} kJ/kg · r={hx.water_air_mass_ratio:.2f}",
        fontsize=8,
    )
    ax.set_xlabel("cumulative duty  [kJ/kg-air]", fontsize=7)
    ax.set_ylabel("T  [°C]", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=6, loc="best")


def offtake_stations(result: PlantResult) -> list[tuple[str, object]]:
    """The user exchanger, tagged like the P&ID.

    The active architecture has exactly one, ``E-302``, crossed by the whole
    trunk. The lettered form is retained only so a result written against the
    former serial cascade still renders: there, ``E-302A`` was the station that
    handed the user its supply temperature and the last letter met its return.
    """
    dh = result.heat_offtake
    if dh is None or not dh.taps:
        return []
    if len(dh.taps) == 1:
        return [("E-302", dh.taps[0])]
    return [
        (f"E-302{chr(ord('A') + index)}", tap)
        for index, tap in enumerate(dh.taps)
    ]


def draw_offtake_composite(ax, tag: str, tap, supply_k: float, return_k: float) -> None:
    """T-Q curves of ONE user exchanger on the descending plant-water trunk.

    Read exactly like :func:`draw_composite`: cumulative duty on x, the vertical
    gap is the local driving temperature difference.  Both sides are straight
    here because both are liquid water at essentially constant cp - the bend
    that shows up in the air/water panels comes from real-air cp, and there is
    no air in this exchanger.

    The station's own end temperatures are what is plotted, NOT the user's
    overall supply and return.  On a cascade only the hottest station reaches
    the supply temperature and only the coldest meets the return; the ones in
    between preheat, and drawing them against the overall span would invent an
    approach violation that the hardware does not have.
    """
    ax.clear()
    duty = tap.heat_j_per_kg_air
    if duty <= 0.0 or tap.user_water_per_kg_air <= 0.0:
        ax.text(0.5, 0.5, f"{tag}\nno heat-user duty", ha="center", va="center",
                transform=ax.transAxes, fontsize=8, color="#90a4ae")
        ax.set_xticks([])
        ax.set_yticks([])
        return
    steps = 30
    fractions = [index / steps for index in range(steps + 1)]
    q_kj = [duty * f / 1000 for f in fractions]
    # Counter-current: the plant inlet meets the user outlet, so walking the
    # plant stream toward its outlet walks the user stream toward its inlet.
    plant_t = [
        tap.plant_inlet_temperature_k
        - (tap.plant_inlet_temperature_k - tap.plant_outlet_temperature_k) * f
        - 273.15
        for f in fractions
    ]
    user_t = [
        tap.user_outlet_temperature_k
        - (tap.user_outlet_temperature_k - tap.user_inlet_temperature_k) * f
        - 273.15
        for f in fractions
    ]
    approaches = [hot - cold for hot, cold in zip(plant_t, user_t)]
    ax.plot(q_kj, plant_t, color=HOT_REFERENCE_COLOR, lw=2.0, label="plant trunk")
    ax.plot(q_kj, user_t, color=NETWORK_COLOR, lw=2.0, label="user water")
    ax.fill_between(q_kj, plant_t, user_t, color="#f3ece8", alpha=0.65, zorder=0)
    _mark_minimum_approach(
        ax, q_kj, approaches.index(min(approaches)), plant_t, user_t
    )
    reaches = ""
    if abs(tap.user_outlet_temperature_k - supply_k) < 1e-6:
        reaches = " · delivers supply"
    elif abs(tap.user_inlet_temperature_k - return_k) < 1e-6:
        reaches = " · takes the return"
    ax.set_title(
        f"{tag} · user tap{reaches}\n"
        f"{duty / 1000:.0f} kJ/kg · trunk r={tap.plant_water_per_kg_air:.2f} · "
        f"user r={tap.user_water_per_kg_air:.2f}",
        fontsize=8,
    )
    ax.set_xlabel("cumulative duty  [kJ/kg-air]", fontsize=7)
    ax.set_ylabel("T  [°C]", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=6, loc="best")


def draw_composites(figure, result: PlantResult, fluid: str) -> None:
    """Lay every exchanger out on one figure, in an automatically-chosen grid.

    Uses the constrained layout engine rather than ``tight_layout``: an 8-stage
    plant puts sixteen panels plus the double-width E-302 cell on one figure, and
    ``tight_layout`` cannot fit that many decorations - it gave up with a
    UserWarning and left the spacing it happened to have. Constrained layout
    solves the same problem as a proper optimisation and degrades gracefully.
    """
    figure.clear()
    figure.set_layout_engine("constrained")
    items = exchangers(result)
    stations = offtake_stations(result)
    if not items and not stations:
        ax = figure.add_subplot(1, 1, 1)
        ax.text(0.5, 0.5,
                "No coolant-coupled exchangers.\n\nA diabatic plant rejects its heat to\n"
                "atmosphere and reheats from it, so there is\nno second stream to plot against.",
                ha="center", va="center", fontsize=10, color="#90a4ae")
        ax.axis("off")
        return

    # The user's cascade stations come FIRST and in hot-to-cold order, so the
    # figure reads the way the coolant flows: down the trunk through the user
    # taps, then out to the interheaters. Every station is its own panel -
    # a cascade is several exchangers and drawing one averaged curve for them
    # would hide exactly the per-station approach the ladder is built to widen.
    rows, cols = grid_shape(len(items) + len(stations))
    dh = result.heat_offtake
    for index, (tag, tap) in enumerate(stations):
        draw_offtake_composite(
            figure.add_subplot(rows, cols, index + 1), tag, tap,
            dh.supply_temperature_k, dh.return_temperature_k,
        )
    for index, (tag, process) in enumerate(items, start=len(stations)):
        draw_composite(figure.add_subplot(rows, cols, index + 1), tag, process, fluid)
    figure.suptitle(
        "Heat-exchanger composite curves — the vertical gap is the driving ΔT; its narrowest point is the minimum approach",
        fontsize=9,
    )

# --------------------------------------------------------------------------- flow Sankeys
#
# THESE RUN LEFT TO RIGHT, INLET TO OUTLET.
#
# The earlier pair were two-column diagrams: everything the plant consumed on
# the left, everything it produced on the right, and an opaque box between
# them.  They balanced, but they hid the thing an engineer actually wants to
# see - WHERE along the machine each joule joins or leaves the stream.  A
# four-stage plant has eight separate exchangers and eight separate machines,
# and lumping them into "compression work" and "heat rejected" throws away
# exactly the per-stage structure the rest of this package works so hard to
# solve.
#
# So the stream is drawn as one band that starts at the air intake and ends at
# the stack, tapering as it goes.  Every station on the way - each compressor,
# each intercooler, each interheater, each expander, each tank, the ambient
# exchanger - gets its own arrow: down into the band if it adds, out of the
# band if it takes.  The band's thickness at any point IS the energy the stream
# is carrying there, so the picture cannot lie about the balance.
#
# LABELS.  A per-stage diagram has three times as many things to name, and
# writing them all out at full size makes the picture unreadable - which
# defeats the purpose.  Each arrow therefore carries a very small tag, and the
# full description with its number is revealed on hover in the GUI (see
# :func:`attach_hover`).  Saved PNGs have no cursor, so they keep the small
# tags and nothing else.

WORK_INPUT_COLOR = "#6a1b9a"
WORK_OUTPUT_COLOR = "#2e7d32"
AMBIENT_HEAT_COLOR = "#f9a825"
REJECTION_COLOR = "#c62828"
STORAGE_LOSS_COLOR = "#8d6e63"
EXHAUST_COLOR = "#546e7a"
DESTRUCTION_COLOR = "#bf360c"
STREAM_COLOR = "#90a4ae"
STORE_COLOR = "#ef6c00"

# Only flows above this size get their own arrow [J/kg-air]; smaller ones are
# numerical noise on a whole-plant scale and are simply not drawn.
_SANKEY_MIN_SLICE_J = 50.0


def _abbreviate(kind: str) -> str:
    """A four-character tag a reader can still map back to the component."""
    words = kind.split("_")
    if len(words) == 1:
        return words[0][:4]
    return (words[0][:2] + "".join(word[0] for word in words[1:]))[:4]


@dataclass(frozen=True)
class SankeyFlow:
    """One arrow joining or leaving the stream at a station."""

    tag: str            # two or three characters, drawn at the arrow tip
    label: str          # full description, revealed on hover
    value: float        # always positive; the direction is which list it is in
    color: str


@dataclass(frozen=True)
class SankeyStation:
    """One place along the plant where energy joins or leaves the stream."""

    name: str
    inflows: tuple[SankeyFlow, ...] = ()
    outflows: tuple[SankeyFlow, ...] = ()


def _draw_process_sankey(
    ax,
    *,
    title: str,
    inlet: SankeyFlow,
    stations: list[SankeyStation],
    note: str,
    unit: str,
) -> list[tuple[object, str]]:
    """Draw the stream from inlet to outlet and return the hover regions.

    Returns ``[(artist, text)]`` so a live canvas can reveal the full label for
    whichever arrow the cursor is over; static output ignores it.
    """
    from matplotlib.patches import Polygon

    ax.clear()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    carried = [inlet.value]
    for station in stations:
        carried.append(
            carried[-1]
            + sum(flow.value for flow in station.inflows)
            - sum(flow.value for flow in station.outflows)
        )
    scale = max(max(carried), 1e-9)

    # The band never touches the frame: the arrows need room above and below.
    span, baseline = 0.34, 0.33
    left, right = 0.055, 0.945
    slots = len(stations) + 1
    step = (right - left) / slots

    hover: list[tuple[object, str]] = []

    def height(value: float) -> float:
        return span * value / scale

    def band(x0: float, x1: float, v0: float, v1: float) -> None:
        ax.add_patch(Polygon(
            [(x0, baseline), (x0, baseline + height(v0)),
             (x1, baseline + height(v1)), (x1, baseline)],
            closed=True, facecolor=STREAM_COLOR, edgecolor="white",
            linewidth=0.4, alpha=0.55, zorder=2,
        ))

    def arrow(x: float, flow: SankeyFlow, top: float, going_out: bool) -> None:
        thickness = max(height(flow.value), 0.004)
        half = min(0.010, max(0.0035, step * 0.18))
        if going_out:
            tip_y = 0.155
            body = [(x - half, baseline), (x + half, baseline),
                    (x + half, tip_y + 0.02), (x, tip_y), (x - half, tip_y + 0.02)]
            text_y, va = tip_y - 0.014, "top"
        else:
            tip_y = 0.820
            body = [(x - half, tip_y), (x + half, tip_y),
                    (x + half, top + 0.02), (x, top), (x - half, top + 0.02)]
            text_y, va = tip_y + 0.012, "bottom"
        patch = ax.add_patch(Polygon(
            body, closed=True, facecolor=flow.color, edgecolor="white",
            linewidth=0.4, alpha=0.80, zorder=3,
        ))
        # A thin proportional stub next to the arrow carries the MAGNITUDE, so
        # the picture stays quantitative even where the arrow itself is a fixed
        # width for legibility.
        stub_y = (baseline - 0.02 - thickness) if going_out else (top + 0.02)
        ax.add_patch(Polygon(
            [(x + half, stub_y), (x + half + 0.006, stub_y),
             (x + half + 0.006, stub_y + thickness), (x + half, stub_y + thickness)],
            closed=True, facecolor=flow.color, edgecolor="none",
            alpha=0.95, zorder=4,
        ))
        ax.text(
            x, text_y, flow.tag, ha="center", va=va, fontsize=5.4,
            color="#37474f", rotation=90,
        )
        hover.append((patch, f"{flow.label}\n{flow.value / 1000:.2f} {unit}"))

    x = left
    band(x, x + step * 0.5, inlet.value, inlet.value)
    ax.text(
        x, baseline + height(inlet.value) + 0.012, inlet.tag,
        ha="left", va="bottom", fontsize=5.4, color="#37474f",
    )
    hover.append((
        ax.add_patch(Polygon(
            [(x, baseline), (x + step * 0.5, baseline),
             (x + step * 0.5, baseline + height(inlet.value)),
             (x, baseline + height(inlet.value))],
            closed=True, facecolor="none", edgecolor="none", zorder=5,
        )),
        f"{inlet.label}\n{inlet.value / 1000:.2f} {unit}",
    ))

    for index, station in enumerate(stations):
        x_station = left + step * (index + 0.75)
        before, after = carried[index], carried[index + 1]
        top_before = baseline + height(before)
        # A station may move several separate things at once - the last one
        # usually does, because that is where every product leaves. Spread them
        # across the station's own slot instead of stacking them on one x,
        # which drew them on top of each other.
        for group, going_out in ((station.inflows, False), (station.outflows, True)):
            width = step * 0.55
            for order, flow in enumerate(group):
                offset = 0.0 if len(group) == 1 else (
                    width * (order / (len(group) - 1) - 0.5)
                )
                arrow(x_station + offset, flow, top_before, going_out=going_out)
        band(left + step * (index + 0.5), x_station, before, before)
        band(x_station, left + step * (index + 1.5), before, after)


    ax.text(0.5, 0.995, title, ha="center", va="top", fontsize=10.5, weight="bold")
    ax.text(0.5, 0.962, note, ha="center", va="top", fontsize=6.6, color="#546e7a")
    return hover


def attach_hover(canvas, ax, regions: list[tuple[object, str]]) -> None:
    """Reveal an arrow's full description while the cursor is over it.

    A per-stage Sankey names three times as many things as the old two-column
    one. Printing every name at readable size would crowd the picture past
    usefulness, and shrinking them until they fit makes them unreadable, so the
    detail lives on the cursor instead. Static output keeps only the short tags.
    """
    annotation = ax.annotate(
        "", xy=(0, 0), xytext=(12, 12), textcoords="offset points",
        fontsize=7.5, zorder=10, visible=False,
        bbox=dict(boxstyle="round,pad=0.35", fc="#fffde7", ec="#8d6e63", lw=0.8),
    )

    def motion(event) -> None:
        if event.inaxes is not ax:
            if annotation.get_visible():
                annotation.set_visible(False)
                canvas.draw_idle()
            return
        for artist, text in regions:
            contains, _ = artist.contains(event)
            if contains:
                annotation.xy = (event.xdata, event.ydata)
                annotation.set_text(text)
                annotation.set_visible(True)
                canvas.draw_idle()
                return
        if annotation.get_visible():
            annotation.set_visible(False)
            canvas.draw_idle()

    canvas.mpl_connect("motion_notify_event", motion)


def _stage_stations(result: PlantResult) -> list[SankeyStation]:
    """Every machine and exchanger of both trains, in flow order.

    This is the whole point of the redraw: a four-stage plant has eight
    machines and eight exchangers, and each one gets its own arrow rather than
    being summed into a single "compression work" band.
    """
    stations: list[SankeyStation] = []
    compressors = coolers = expanders = heaters = 0

    for process in result.charging.processes:
        if process.kind == "compression":
            compressors += 1
            stations.append(SankeyStation(
                f"K-{100 + compressors}",
                inflows=(SankeyFlow(
                    f"K-{100 + compressors}", f"K-{100 + compressors} compressor shaft work",
                    process.work_j_per_kg, WORK_INPUT_COLOR,
                ),),
            ))
        elif process.kind in {"intercooling", "aftercooling"}:
            duty = -process.heat_to_air_j_per_kg
            if duty <= _SANKEY_MIN_SLICE_J:
                continue
            coolers += 1
            to_store = process.heat_exchanger is not None
            stations.append(SankeyStation(
                f"E-{100 + coolers}" if to_store else "AC",
                outflows=(SankeyFlow(
                    f"E-{100 + coolers}" if to_store else "AC-101",
                    f"E-{100 + coolers} "
                    + ("compression heat into the store" if to_store
                       else "compression heat to atmosphere"),
                    duty, STORE_COLOR if to_store else REJECTION_COLOR,
                ),),
            ))

    for process in result.discharging.processes:
        if process.kind == "interheating":
            duty = process.heat_to_air_j_per_kg
            heaters += 1
            if duty <= _SANKEY_MIN_SLICE_J:
                continue
            stations.append(SankeyStation(
                f"E-{200 + heaters}",
                inflows=(SankeyFlow(
                    f"E-{200 + heaters}",
                    f"E-{200 + heaters} stored heat back into the air",
                    duty, STORE_COLOR,
                ),),
            ))
        elif process.kind in {"ambient_reheat", "ambient_anti_icing_reheat"}:
            duty = process.heat_to_air_j_per_kg
            if duty <= _SANKEY_MIN_SLICE_J:
                continue
            stations.append(SankeyStation(
                "AH",
                inflows=(SankeyFlow(
                    "AH-20x", "AH-20x ambient heat scavenged before expansion",
                    duty, AMBIENT_HEAT_COLOR,
                ),),
            ))
        elif process.kind == "expansion":
            expanders += 1
            stations.append(SankeyStation(
                f"T-{200 + expanders}",
                outflows=(SankeyFlow(
                    f"T-{200 + expanders}", f"T-{200 + expanders} expander shaft work",
                    -process.work_j_per_kg, WORK_OUTPUT_COLOR,
                ),),
            ))
    return stations


def draw_energy_sankey(ax, result: PlantResult) -> list[tuple[object, str]]:
    """First-law flows, inlet to outlet, one arrow per station.

    The band is the enthalpy the air stream is carrying. It starts at the
    intake, swells at every compressor, shrinks at every cooler, and so on to
    the stack. The coolant loop is not a hidden box: the heat that leaves the air
    at E-10x and returns to it at E-20x is drawn at both ends, and whatever the
    loop could not give back leaves through its own station.
    """
    intake = SankeyFlow(
        "F-101 intake", "Air intake enthalpy at the dead state",
        max(result.charging.inlet.enthalpy_j_per_kg, 1.0), STREAM_COLOR,
    )
    stations = _stage_stations(result)

    stations.append(SankeyStation(
        "S-201 stack",
        outflows=(SankeyFlow(
            "S-201 exhaust", "Exhaust air leaving the stack, still carrying enthalpy",
            max(result.discharging.outlet.enthalpy_j_per_kg, 0.0), EXHAUST_COLOR,
        ),),
    ))

    added = intake.value + sum(f.value for s in stations for f in s.inflows)
    removed = sum(f.value for s in stations for f in s.outflows)

    # The store's own disposition is reported, not drawn on this band. The heat
    # that leaves the air at E-10x and returns at E-20x is already on it, at
    # both ends; adding what the loop then does with the difference would count
    # the same joules twice and the picture would stop being a balance.
    store = result.thermal_store
    aside = ""
    if store is not None:
        parts = [f"to turbines {store.delivered_heat_j_per_kg_air / 1000:.0f}"]
        offtake = result.heat_offtake
        if offtake is not None and offtake.heat_j_per_kg_air > _SANKEY_MIN_SLICE_J:
            parts.append(f"to the heat user {offtake.heat_j_per_kg_air / 1000:.0f}")
        absorbed = store.cold_return_heat_absorbed_from_ambient_j_per_kg_air
        tanks = store.storage_loss_j_per_kg_air + store.cold_storage_loss_j_per_kg_air
        if abs(tanks) > _SANKEY_MIN_SLICE_J:
            parts.append(f"tank standing {tanks / 1000:.0f}")
        aside = (
            f"  |  store: recovered {store.recovered_heat_j_per_kg_air / 1000:.0f}"
            f" + ambient E-303 {absorbed / 1000:.0f} = "
            + " + ".join(parts) + " kJ/kg-air"
        )

    concept = plant_concept_label(
        result.mode,
        exports_heat=result.heat_offtake is not None,
    )
    return _draw_process_sankey(
        ax,
        title=f"Energy flow along the air stream, intake to stack — {concept}",
        inlet=intake,
        stations=stations,
        unit="kJ/kg-air",
        note=(
            f"air stream: in {added / 1000:.1f} = out {removed / 1000:.1f} kJ/kg-air, "
            f"closure {added - removed:+.2f} J/kg-air{aside}. Hover an arrow for its name."
        ),
    )


def draw_exergy_sankey(ax, result: PlantResult) -> list[tuple[object, str]]:
    """Grassmann diagram as a process, not as a pie.

    The band is the availability the plant still has in hand. It enters as
    compression work and is whittled down component by component, in the order
    the machine actually destroys it, so the biggest offenders are read off by
    where the band narrows rather than by comparing bar lengths.
    """
    exergy = result.exergy
    inlet = SankeyFlow(
        "W compression", "Compression shaft work - the only exergy the plant buys",
        max(result.compression_work_input_j_per_kg, 1.0), WORK_INPUT_COLOR,
    )

    stations: list[SankeyStation] = []
    shades = ("#bf360c", "#d84315", "#e64a19", "#f4511e", "#ff5722", "#ff7043", "#ff8a65")
    ordered = sorted(
        (
            (kind, value)
            for kind, value in exergy.component_destruction_j_per_kg_air.items()
            if value > _SANKEY_MIN_SLICE_J
        ),
        key=lambda item: -item[1],
    )
    for index, (kind, value) in enumerate(ordered):
        pretty = kind.replace("_", " ")
        stations.append(SankeyStation(
            pretty,
            outflows=(SankeyFlow(
                pretty, f"Destroyed in {pretty}", value,
                shades[index % len(shades)],
            ),),
        ))

    products: list[SankeyFlow] = [SankeyFlow(
        "W expansion", "Expander shaft work - the electrical product",
        result.expansion_work_output_j_per_kg, WORK_OUTPUT_COLOR,
    )]
    if exergy.useful_heat_exergy_j_per_kg_air > _SANKEY_MIN_SLICE_J:
        products.append(SankeyFlow(
            "B heat user", "Exergy the external heat user receives - the thermal product",
            exergy.useful_heat_exergy_j_per_kg_air, WORK_OUTPUT_COLOR,
        ))
    for name, value in sorted(
        exergy.loss_j_per_kg_air.items(), key=lambda item: -item[1]
    ):
        if value > _SANKEY_MIN_SLICE_J:
            products.append(SankeyFlow(
                name.replace("_", " "),
                f"Left the boundary intact but unused: {name.replace('_', ' ')}",
                value, EXHAUST_COLOR,
            ))
    stations.append(SankeyStation("products", outflows=tuple(products)))

    note = f"balance residual {exergy.balance_residual_j_per_kg_air:.2f} J/kg-air"
    if result.external_heat_input_j_per_kg > 1e-6:
        note += (
            f"; ambient heat {result.external_heat_input_j_per_kg / 1000:.1f} "
            "kJ/kg-air enters at ~zero exergy"
        )
    note += ". Hover an arrow for its full name."
    concept = plant_concept_label(
        result.mode,
        exports_heat=result.heat_offtake is not None,
    )
    return _draw_process_sankey(
        ax,
        title=f"Exergy flow (Grassmann), work in to products out — {concept}",
        inlet=inlet,
        stations=stations,
        unit="kJ/kg-air",
        note=note,
    )
