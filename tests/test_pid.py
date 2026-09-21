"""The P&ID must be a function of the configuration, not a drawing someone made once.

These tests assert on the TOPOLOGY (caes.pid.layout), never on pixels: what
equipment exists, how it is tagged, and how it changes when the plant changes.
That is the property that actually matters - a diagram that silently stops
matching the model is worse than no diagram at all.
"""

import matplotlib

matplotlib.use("Agg")   # no display in CI; must be set before pyplot is imported
import matplotlib.pyplot as plt
import pytest

from caes import PlantConfig, PlantMode, HeatOfftake
from caes.plant import CAESPlant
from caes import pid


@pytest.mark.parametrize("stages", [1, 2, 4, 6, 8])
def test_compressor_count_drives_the_charging_train(stages):
    """Add a compressor stage, get a compressor body AND its intercooler, tagged in sequence."""
    diagram = pid.layout(PlantConfig(compressor_stages=stages, expander_stages=stages))
    assert len(diagram.of_kind("compressor")) == stages
    assert [e.tag for e in diagram.of_kind("compressor")] == [f"K-{101 + i}" for i in range(stages)]

    intercoolers = [e for e in diagram.of_kind("water_hx") if e.y == pid.Y_EC]
    assert len(intercoolers) == stages, "every compressor stage must be followed by a cooler"


@pytest.mark.parametrize("stages", [1, 2, 4, 6, 8])
def test_expander_count_drives_the_discharging_train(stages):
    diagram = pid.layout(PlantConfig(compressor_stages=stages, expander_stages=stages))
    assert len(diagram.of_kind("expander")) == stages
    assert [e.tag for e in diagram.of_kind("expander")] == [f"T-{201 + i}" for i in range(stages)]
    assert not diagram.of_kind("moisture_separator")
    assert diagram.by_tag("MS-200") is None
    assert all(diagram.by_tag(f"MS-{201 + i}") is None for i in range(stages))


def test_stage_counts_are_independent():
    diagram = pid.layout(PlantConfig(compressor_stages=6, expander_stages=3))
    assert len(diagram.of_kind("compressor")) == 6
    assert len(diagram.of_kind("expander")) == 3


def test_adiabatic_plant_has_the_whole_water_loop():
    diagram = pid.layout(PlantConfig(heat_offtake=HeatOfftake.NONE))
    for tag in ("TK-301", "TK-302", "P-301", "P-302", "E-303", "V-401", "M-101", "G-201", "F-101", "S-201"):
        assert diagram.by_tag(tag) is not None, f"{tag} missing from the adiabatic plant"
    assert diagram.has_water_loop
    # With no heat user the hot tank feeds the turbine header directly.
    assert diagram.by_tag("E-302") is None


def test_diabatic_plant_drops_the_tanks_and_grows_fin_fans():
    """Switching mode must restructure the plant, not just recolour it."""
    diagram = pid.layout(PlantConfig(mode=PlantMode.DIABATIC))
    assert not diagram.has_water_loop
    for tag in ("TK-301", "TK-302", "P-301", "P-302"):
        assert diagram.by_tag(tag) is None, f"{tag} must not exist without a thermal store"
    assert not diagram.of_kind("water_hx"), "diabatic plants have no water exchangers at all"
    # The intercoolers become air-cooled, the reheaters pull from atmosphere,
    # and every expander gets an anti-icing throttle path.
    assert len(diagram.of_kind("air_cooler")) == diagram.compressor_stages
    assert len(diagram.of_kind("ambient_heater")) == diagram.expander_stages
    assert all(diagram.by_tag(f"TV-{201 + i}") for i in range(diagram.expander_stages))


def test_diabatic_every_stage_has_reheater_and_throttle_control():
    diagram = pid.layout(PlantConfig(mode=PlantMode.DIABATIC, expander_stages=4))
    for i in range(4):
        assert diagram.by_tag(f"AH-{201 + i}") is not None
        assert diagram.by_tag(f"TV-{201 + i}") is not None


def test_pid_omits_dryers_separators_and_pdp_trim_labels():
    diagram = pid.layout(PlantConfig())
    assert not diagram.of_kind("moisture_separator")
    assert all("dryer" not in item.label.lower() for item in diagram.equipment)
    assert all("separator" not in item.label.lower() for item in diagram.equipment)
    assert all("AC-101" not in item.label for item in diagram.equipment)


def test_heat_offtake_branch_appears_only_when_configured():
    """The heat-user exchanger and the network block are one unit: either the
    plant sells heat or it does not."""
    none = pid.layout(PlantConfig(heat_offtake=HeatOfftake.NONE))
    assert none.by_tag("E-302") is None
    assert none.by_tag("H-301") is None
    assert not none.exports_heat

    selling = pid.layout(PlantConfig(heat_offtake=HeatOfftake.HEAT_USER))
    assert selling.by_tag("E-302") is not None, "heat-user exchanger missing"
    assert selling.by_tag("H-301") is not None, "heat-user network block missing"
    assert selling.exports_heat


def test_heat_offtake_sits_in_series_between_the_hot_tank_and_the_turbines():
    """THE structural point. E-302 is ON the hot supply line - downstream of the tank,
    upstream of the interheaters - not on a parallel branch and not on the spent-water
    return (where the water is only ~46 C and no network would take it).

    The pump moves with it: with an off-take, the water leaves the tank SIDEWAYS through
    P-301 and into E-302, rather than dropping straight onto the header."""
    diagram = pid.layout(PlantConfig(heat_offtake=HeatOfftake.HEAT_USER))
    hot_tank = diagram.by_tag("TK-301")
    dh = diagram.by_tag("E-302")
    pump = diagram.by_tag("P-301")

    assert dh.y == pytest.approx(pid.Y_TANKS), "E-302 must sit on the hot tank's own band"
    assert dh.x > hot_tank.x, "E-302 must be downstream of the hot tank"

    # The pump is on the tank -> E-302 run, between the two of them.
    assert pump.y == pytest.approx(pid.Y_TANKS)
    assert hot_tank.x < pump.x < dh.x

    # Without an off-take there is no E-302: the pump feeds the header directly.
    plain = pid.layout(PlantConfig(heat_offtake=HeatOfftake.NONE))
    assert plain.by_tag("P-301").y == pytest.approx(pid.Y_TANKS)
    assert plain.by_tag("E-302") is None


def test_no_adiabatic_concept_draws_an_ambient_heater():
    """The AH-20x preheaters are gone from every adiabatic architecture.

    They were up to eight extra high-pressure gas/ambient exchangers, and the
    only ones in the model that paid no air-side pressure drop. Ambient reheat
    now belongs to AD-CAES alone, where it is the sole discharge heat source,
    and it carries the AH tag there so E-20x means "water interheater" and
    nothing else.
    """
    for offtake in (HeatOfftake.NONE, HeatOfftake.HEAT_USER):
        adiabatic = pid.layout(PlantConfig(heat_offtake=offtake))
        assert not adiabatic.of_kind("ambient_heater")
        assert all(adiabatic.by_tag(f"AH-{201 + i}") is None for i in range(adiabatic.expander_stages))

    diabatic = pid.layout(PlantConfig(mode=PlantMode.DIABATIC))
    assert len(diabatic.of_kind("ambient_heater")) == diabatic.expander_stages
    assert all(diabatic.by_tag(f"AH-{201 + i}") for i in range(diabatic.expander_stages))
    # E-20x is a water interheater, so a diabatic plant must not own one.
    assert all(diabatic.by_tag(f"E-{201 + i}") is None for i in range(diabatic.expander_stages))


def test_equipment_tags_are_unique():
    """A duplicate tag on a P&ID is a defect: it makes two different things the
    same thing in every downstream document."""
    for config in (
        PlantConfig(),
        PlantConfig(mode=PlantMode.DIABATIC),
        PlantConfig(compressor_stages=8, expander_stages=8),
        PlantConfig(heat_offtake=HeatOfftake.HEAT_USER),
    ):
        tags = pid.layout(config).tags
        assert len(tags) == len(set(tags)), f"duplicate tags: {sorted(t for t in tags if tags.count(t) > 1)}"


def test_water_corridors_stay_clear_of_every_symbol():
    """The cold-water risers are routed down two dedicated verticals to the left of
    the plant precisely so they never cross a machine. If a symbol ever lands on
    a corridor, the drawing has a pipe running through a compressor."""
    for n_c in (1, 4, 8):
        for n_e in (1, 4, 8):
            diagram = pid.layout(PlantConfig(compressor_stages=n_c, expander_stages=n_e))
            for corridor in (diagram.x_supply_corridor, diagram.x_return_corridor):
                for item in diagram.equipment:
                    if item.tag == "P-302":
                        continue    # these deliberately SIT on a corridor
                    assert abs(item.x - corridor) > 1.0, (
                        f"{item.tag} at x={item.x:.2f} collides with the corridor at "
                        f"x={corridor:.2f} ({n_c}c/{n_e}e)"
                    )


@pytest.mark.parametrize(
    "config",
    [
        PlantConfig(),
        PlantConfig(mode=PlantMode.DIABATIC),
        PlantConfig(compressor_stages=1, expander_stages=1),
        PlantConfig(compressor_stages=6, expander_stages=3),
        PlantConfig(heat_offtake=HeatOfftake.HEAT_USER),
    ],
)
def test_render_survives_every_architecture(config):
    """Smoke test: the renderer must not throw for any plant the solver accepts,
    and must also work with result=None (which is what the GUI shows when the
    solver fails but the configuration still describes a real layout)."""
    figure, axis = plt.subplots(figsize=(12, 7))
    try:
        try:
            result = CAESPlant(config).run()
        except ValueError:
            # Direct coolant limits and moisture-safe duty can intentionally
            # make some few-stage layouts thermodynamically infeasible.
            result = None
        pid.render(axis, config, result)
        pid.render(axis, config, None)
    finally:
        plt.close(figure)


def test_framing_matches_the_layout_extents():
    """The renderer runs a schemdraw Drawing, which autoscales the axis to its own
    symbols on draw; render() must pin the framing back to the layout extents
    afterwards, or the drawing is cropped."""
    config = PlantConfig()
    diagram = pid.layout(config)
    figure, axis = plt.subplots(figsize=(12, 7))
    try:
        pid.render(axis, config, None)
        assert axis.get_xlim() == pytest.approx((diagram.x_min, diagram.x_max))
        assert axis.get_ylim() == pytest.approx((diagram.y_min, diagram.y_max))
    finally:
        plt.close(figure)


def test_hero_symbols_reach_the_canvas():
    """The two symbols schemdraw owns - flow-oriented machines and counter-flow
    exchanger blocks - must actually be drawn, not silently dropped the way a
    schemdraw Drawing is when it is finalized with show=False via the context
    form.

    One added stage adds one compressor, one expander, one intercooler and one
    interheater, and each of those heroes is exactly one Polygon patch. The
    matplotlib peripherals do not change with the stage count, so the DELTA is
    the heroes: a dropped Drawing leaves it at zero.
    """
    from matplotlib.patches import Polygon

    def polygons(config: PlantConfig) -> int:
        figure, axis = plt.subplots(figsize=(12, 7))
        try:
            pid.render(axis, config, None)
            return sum(1 for patch in axis.patches if isinstance(patch, Polygon))
        finally:
            plt.close(figure)

    three = polygons(PlantConfig(compressor_stages=3, expander_stages=3))
    four = polygons(PlantConfig(compressor_stages=4, expander_stages=4))
    assert four - three == 4, (
        "machines/exchangers missing from canvas: "
        f"{four - three} new polygons per added stage"
    )


def test_one_hot_tank_one_user_hx_and_one_bleed_per_stage():
    """The drawn topology, and the two counts that must never drift apart.

    There is exactly one user exchanger whatever the stage count, and E-304
    carries exactly one extraction nozzle per expansion stage.
    """
    for stages in (4, 6, 8):
        diagram = pid.layout(PlantConfig(
            heat_offtake=HeatOfftake.HEAT_USER,
            compressor_stages=stages,
            expander_stages=stages,
        ))
        assert diagram.by_tag("TK-301") is not None
        assert diagram.by_tag("TK-301A") is None

        exchangers = diagram.of_kind("offtake_tap")
        assert [item.tag for item in exchangers] == ["E-302"]

        extraction = diagram.by_tag("E-304")
        assert extraction is not None
        assert extraction.ports == stages
        # Process order along the tank band: sell first, then stage the rest.
        assert exchangers[0].x < extraction.x < diagram.by_tag("H-301").x


def test_the_heat_user_is_not_called_a_district_heating_network():
    """This is a heat-and-power plant; the user is whoever wants the heat.

    Supply, return and finite exchanger NTU can describe a network, a process
    loop, an absorption chiller or a dryer equally. The drawing must not name
    one of them as if it were the only one.
    """
    diagram = pid.layout(PlantConfig(heat_offtake=HeatOfftake.HEAT_USER))
    user = diagram.by_tag("H-301")
    assert user is not None
    assert "district" not in user.label.lower()
    assert "heat user" in user.label.lower()
    tap = diagram.by_tag("E-302")
    assert tap is not None and "district" not in tap.label.lower()
