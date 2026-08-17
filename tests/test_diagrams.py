"""Cycle plots and per-exchanger composite curves."""

import matplotlib

matplotlib.use("Agg")   # must precede pyplot; no display in CI
import matplotlib.pyplot as plt
import pytest

from caes import (
    CAESPlant,
    HeatOfftake,
    OptimizationObjective,
    PlantConfig,
    PlantMode,
)
from caes import diagrams


@pytest.mark.parametrize(
    "count, expected",
    [
        (1, (1, 1)), (2, (1, 2)), (3, (1, 3)),
        (4, (2, 2)),      # NOT 1x4: a square reads better in a wide tab
        (6, (2, 3)),
        (8, (2, 4)),      # NOT 3x3: that would leave a hole
        (9, (3, 3)),
        (10, (2, 5)),
        (12, (3, 4)),
        (16, (4, 4)),
    ],
)
def test_grid_shape_matches_what_you_would_choose_by_hand(count, expected):
    assert diagrams.grid_shape(count) == expected


def test_grid_always_has_room_for_every_panel():
    """Whatever the heuristic does, it may never drop an exchanger off the figure."""
    for count in range(1, 33):
        rows, cols = diagrams.grid_shape(count)
        assert rows * cols >= count, f"{count} panels do not fit in {rows}x{cols}"


def test_exchanger_count_follows_the_stage_count():
    """4 compressors + 4 expanders = 8 water exchangers = 8 panels."""
    result = CAESPlant(PlantConfig(compressor_stages=4, expander_stages=4)).run()
    assert len(diagrams.exchangers(result)) == 8

    result = CAESPlant(PlantConfig(compressor_stages=6, expander_stages=3)).run()
    assert len(diagrams.exchangers(result)) == 9

    # Tags line up with the P&ID, so a panel can be traced to a symbol on the drawing.
    tags = [tag for tag, _ in diagrams.exchangers(result)]
    assert tags == [f"E-{101 + i}" for i in range(6)] + [f"E-{201 + i}" for i in range(3)]


def test_diabatic_plant_has_no_composites_to_draw():
    """No water loop means no second stream, so there is nothing to plot against.
    The figure must say so rather than throwing or drawing an empty grid."""
    result = CAESPlant(PlantConfig(mode=PlantMode.DIABATIC)).run()
    assert diagrams.exchangers(result) == []

    figure = plt.figure()
    try:
        diagrams.draw_composites(figure, result, "Air")   # must not raise
    finally:
        plt.close(figure)


@pytest.mark.parametrize(
    "config",
    [
        PlantConfig(),
        PlantConfig(
            compressor_stages=1,
            expander_stages=1,
            storage_pressure_bar=30.0,
            coolant_maximum_temperature_c=450.0,
        ),
        PlantConfig(compressor_stages=5, expander_stages=5),
        PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        ),
        PlantConfig(mode=PlantMode.DIABATIC),
    ],
)
def test_every_diagram_renders(config):
    result = CAESPlant(config).run()
    figure, axes = plt.subplots(1, 3)
    try:
        diagrams.draw_ts(axes[0], result)
        diagrams.draw_hs(axes[1], result)
        diagrams.draw_ph(axes[2], result)
    finally:
        plt.close(figure)

    composite = plt.figure()
    try:
        diagrams.draw_composites(composite, result, "Air")
    finally:
        plt.close(composite)


@pytest.mark.parametrize(
    "config",
    [
        PlantConfig(),
        PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        ),
        PlantConfig(mode=PlantMode.DIABATIC),
    ],
)
def test_sankey_diagrams_run_the_length_of_the_plant_and_close_the_books(config):
    """Both flow Sankeys run inlet to outlet with one arrow per station.

    The point of the redraw is that a reader can see WHERE along the machine
    each joule joins or leaves, so every compressor, exchanger and expander
    must appear by its own tag rather than being summed into one band. The
    energy diagram must still close the first law on the air stream.
    """
    result = CAESPlant(config).run()
    figure, axes = plt.subplots(1, 2)
    try:
        energy_regions = diagrams.draw_energy_sankey(axes[0], result)
        exergy_regions = diagrams.draw_exergy_sankey(axes[1], result)
        for axis in axes:
            assert len(axis.patches) >= 3
            titles = [text.get_text() for text in axis.texts]
            assert any("CAES" in title for title in titles)

        # Every machine of both trains gets its own arrow, and each arrow
        # carries the full description the GUI reveals on hover.
        tags = {text.get_text() for text in axes[0].texts}
        for index in range(config.compressor_stages):
            assert f"K-{101 + index}" in tags
        # AD-CAES may throttle a stage away entirely rather than expand it, so
        # the count follows the real train, not the configured stage count.
        expansions = sum(
            1 for p in result.discharging.processes if p.kind == "expansion"
        )
        assert sum(1 for tag in tags if tag.startswith("T-2")) == expansions
        assert all(region[1] for region in energy_regions)
        assert all(region[1] for region in exergy_regions)
        assert len(energy_regions) > config.compressor_stages

        energy_note = next(
            text.get_text() for text in axes[0].texts if "closure" in text.get_text()
        )
        residual = float(
            energy_note.split("closure")[1].split("J/kg-air")[0].strip()
        )
        assert abs(residual) < 1.0
    finally:
        plt.close(figure)


def test_cycle_diagrams_include_hot_supply_and_cold_return_references():
    config = PlantConfig(
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
    )
    result = CAESPlant(config).run()
    figure, axes = plt.subplots(1, 3)
    try:
        diagrams.draw_ts(axes[0], result)
        diagrams.draw_hs(axes[1], result)
        diagrams.draw_ph(axes[2], result)
        for axis in axes:
            labels = {line.get_label() for line in axis.lines}
            assert any(label.startswith("cold TES") for label in labels)
            assert any(label.startswith("hot TES") for label in labels)
            assert any(label.startswith("coolant supply") for label in labels)
            assert any(label.startswith("coolant return") for label in labels)
            reference_lines = [
                line for line in axis.lines
                if (
                    "TES" in line.get_label()
                    or "coolant supply" in line.get_label()
                    or "coolant return" in line.get_label()
                )
            ]
            assert all(line.get_linestyle() == ":" for line in reference_lines)
    finally:
        plt.close(figure)


def test_cold_coolant_reference_levels_are_real_interheater_returns():
    result = CAESPlant(PlantConfig()).run()
    expected = sorted({
        round(process.heat_exchanger.water_outlet_temperature_k, 6)
        for process in result.discharging.processes
        if process.kind == "interheating" and process.heat_exchanger
    })
    references = diagrams.thermal_reference_temperatures(result)
    actual = sorted({
        round(value, 6)
        for label, value, color in references
        if color == diagrams.RETURN_REFERENCE_COLOR
    })
    assert actual == expected


def test_single_store_and_every_cascade_supply_get_an_isotherm():
    """The plot distinguishes stored state from discharge routing.

    ``K`` changes the number of post-user bleed temperatures, never the number
    of stored hot states.
    """
    from dataclasses import replace

    config = replace(
        PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        ),
        coolant_cascade_groups=4,
    )
    result = CAESPlant(config).run()
    store = result.thermal_store
    assert len(store.hot_level_temperatures_k) == 1

    references = diagrams.thermal_reference_temperatures(result)
    hot = [value for label, value, _ in references if label == "hot TES"]
    supplies = [
        value for label, value, color in references
        if color == diagrams.SUPPLY_REFERENCE_COLOR
    ]
    assert hot == pytest.approx([store.hot_temperature_available_k])
    assert len(supplies) == 4

    figure, axis = plt.subplots()
    try:
        diagrams.draw_ts(axis, result)
        labels = {line.get_label() for line in axis.lines}
        assert any(label.startswith("hot TES") for label in labels)
        assert not any(label.startswith("TES level") for label in labels)
    finally:
        plt.close(figure)


def test_cycle_diagrams_show_isobars_and_process_direction():
    result = CAESPlant(PlantConfig()).run()
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    try:
        diagrams.draw_ts(axes[0], result)
        diagrams.draw_hs(axes[1], result)
        diagrams.draw_ph(axes[2], result)

        for axis in axes:
            pressure_lines = [
                line for line in axis.lines if line.get_gid() == "pressure-reference"
            ]
            pressure_labels = [
                text for text in axis.texts if text.get_gid() == "pressure-reference-label"
            ]
            direction_arrows = [
                text for text in axis.texts
                if (text.get_gid() or "").startswith("cycle-direction-")
            ]
            assert len(pressure_lines) == len(diagrams.pressure_reference_levels(result))
            assert len(pressure_labels) == len(pressure_lines)
            assert len(direction_arrows) >= (
                len(result.charging.processes) + len(result.discharging.processes) - 2
            )

        # An isobar on p-h is horizontal by definition.
        for line in axes[2].lines:
            if line.get_gid() == "pressure-reference":
                assert len(set(line.get_ydata())) == 1
    finally:
        plt.close(figure)


@pytest.mark.parametrize("mode", [PlantMode.ADIABATIC, PlantMode.DIABATIC])
def test_cycle_diagrams_show_surface_drying_and_stored_air_dew_frost_limits(mode):
    result = CAESPlant(PlantConfig(mode=mode)).run()
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    try:
        diagrams.draw_ts(axes[0], result)
        diagrams.draw_hs(axes[1], result)
        diagrams.draw_ph(axes[2], result)
        for axis in axes:
            moisture_lines = {
                line.get_gid()
                for line in axis.lines
                if (line.get_gid() or "").startswith("moisture-")
            }
            assert "moisture-wet-expander-lower-boundary" in moisture_lines
            assert "moisture-dew-boundary" in moisture_lines
            assert "moisture-frost-boundary" in moisture_lines
    finally:
        plt.close(figure)


def test_every_cascade_station_gets_its_own_composite_panel():
    from dataclasses import replace

    config = replace(
        PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
        ),
        coolant_cascade_groups=3,
    )
    result = CAESPlant(config).run()
    stations = diagrams.offtake_stations(result)
    assert len(stations) == len(result.heat_offtake.taps) > 1
    figure = plt.figure(figsize=(12, 7))
    try:
        diagrams.draw_composites(figure, result, "Air")
        assert len(figure.axes) == len(diagrams.exchangers(result)) + len(stations)
        titles = [axis.get_title() for axis in figure.axes]
        # Hot end first, and the tags follow the flow down the trunk.
        for index, (tag, _) in enumerate(stations):
            assert titles[index].startswith(tag)
        for axis, (_, tap) in zip(figure.axes, stations):
            if tap.heat_j_per_kg_air <= 0.0:
                continue
            plant_line, user_line = axis.lines[:2]
            assert all(
                hot > cold
                for hot, cold in zip(plant_line.get_ydata(), user_line.get_ydata())
            )
    finally:
        plt.close(figure)


def test_offtake_composite_is_present():
    config = PlantConfig(
        heat_offtake=HeatOfftake.HEAT_USER,
        optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
    )
    result = CAESPlant(config).run()
    figure = plt.figure(figsize=(12, 7))
    try:
        diagrams.draw_composites(figure, result, "Air")
        assert len(figure.axes) == len(diagrams.exchangers(result)) + 1
        dh_axis = next(axis for axis in figure.axes if "E-302" in axis.get_title())
        plant_line, network_line = dh_axis.lines[:2]
        assert all(
            hot > cold
            for hot, cold in zip(plant_line.get_ydata(), network_line.get_ydata())
        )
    finally:
        plt.close(figure)


def test_composite_curves_never_cross():
    """The hot stream must stay above the cold stream at every point along the
    exchanger. A crossing means heat flowing from cold to hot - a second-law violation
    that an average-only model would hide, and that only the composite curve exposes.

    NOTE this checks the SOLVED profiles, using real air enthalpy at every step, so it
    catches a cross that opens up in the MIDDLE of the exchanger even when both ends
    look fine - which is exactly the failure mode a two-point terminal check cannot see.
    """
    from CoolProp.CoolProp import PropsSI

    config = PlantConfig()
    result = CAESPlant(config).run()

    for tag, process in diagrams.exchangers(result):
        hx = process.heat_exchanger
        if hx.duty_j_per_kg_air <= 0:
            continue
        cooling = process.kind == "intercooling"

        steps = 40
        h_in, h_out = process.inlet.enthalpy_j_per_kg, process.outlet.enthalpy_j_per_kg
        p_in, p_out = process.inlet.pressure_pa, process.outlet.pressure_pa
        t_w_in = hx.water_inlet_temperature_k
        t_w_out = hx.water_outlet_temperature_k

        for i in range(steps + 1):
            f = i / steps
            air_t = PropsSI("T", "P", p_in + (p_out - p_in) * f, "H", h_in + (h_out - h_in) * f, "Air")
            water_t = t_w_out + (t_w_in - t_w_out) * f
            hot, cold = (air_t, water_t) if cooling else (water_t, air_t)
            assert hot - cold > -1e-6, (
                f"{tag}: streams cross at {f:.0%} of the duty "
                f"(hot {hot - 273.15:.1f} C < cold {cold - 273.15:.1f} C)"
            )
