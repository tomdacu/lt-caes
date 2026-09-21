"""Text and plot output for normalized CAES results."""

from __future__ import annotations

from pathlib import Path

from .models import PlantResult
from .nomenclature import plant_concept_label
from .moisture import (
    compressor_moisture_inventory,
    expander_moisture_inventory,
    phase_change_temperature_k,
)
from .thermal_limits import (
    DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION,
    REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION,
    REFERENCE_WET_EXPANDER_MAX_INLET_LIQUID_MASS_FRACTION,
    maximum_possible_liquid_mass_fraction,
    minimum_wet_expander_temperature_k,
    wet_expander_envelope_label,
    wet_expander_floor_label,
    wet_expander_hard_floor_temperature_k,
)


def _kj(value: float) -> str:
    return f"{value / 1000:.2f} kJ/kg-air"


def _c(kelvin: float, digits: int = 1) -> str:
    return f"{kelvin - 273.15:.{digits}f} °C"


def _store_rows(result: PlantResult) -> list[tuple[str, str]]:
    store = result.thermal_store
    assert store is not None
    interheaters = sum(
        1 for process in result.discharging.processes if process.kind == "interheating"
    )
    # The E-303 group is chosen by TEMPERATURE, not by stage order, so it is
    # reported by size: with E-304 the returns are no longer sorted by stage and
    # "stages 4 onward" would misdescribe it.
    recovery = (
        f"{store.cold_return_recovery_branch_count} coldest of {interheaters} returns"
        if store.cold_return_recovery_branch_count
        else "bypassed (no sub-ambient return)"
    )
    return [
        (
            "Cold / hot / available coolant temperature",
            f"{_c(store.cold_temperature_k)} / {_c(store.hot_temperature_before_loss_k)}"
            f" / {_c(store.hot_temperature_available_k)}",
        ),
        (
            "Coolant direct limits (minimum / maximum)",
            f"{_c(store.coolant_minimum_temperature_k, 2)} / "
            f"{_c(store.coolant_maximum_temperature_k, 2)}",
        ),
        (
            "Calculated coolant extrema (coldest / hottest)",
            f"{_c(store.coolant_minimum_temperature_reached_k, 2)} / "
            f"{_c(store.coolant_maximum_temperature_reached_k, 2)}",
        ),
        ("Untreated all-return mean", _c(store.returned_temperature_k)),
        ("E-303 heat-only optimized group", recovery),
        (
            "E-303 selected mix / warmed outlet",
            f"{_c(store.cold_return_recovery_inlet_temperature_k, 2)} → "
            f"{_c(store.cold_return_recovery_outlet_temperature_k, 2)}",
        ),
        ("Mixed return, before E-304", _c(store.recuperator_inlet_temperature_k)),
        ("E-303 ambient heat absorbed", _kj(store.cold_return_heat_absorbed_from_ambient_j_per_kg_air)),
        ("E-303 exergy destruction", _kj(store.cold_return_exergy_destruction_j_per_kg_air)),
        ("E-303 exchanger NTU", f"{store.cold_return_exchanger_ntu:.3g}"),
        ("E-304 recuperation (internal)", _kj(store.extraction_recuperated_heat_j_per_kg_air)),
        ("Cold-tank inlet after E-304", _c(store.cold_return_exchanger_outlet_temperature_k)),
        ("Total normalized coolant mass", f"{store.total_water_mass_ratio:.3f} kg-coolant/kg-air"),
        (
            "Hot store (one mixed state)",
            f"{_c(store.hot_temperature_available_k)} "
            f"({store.total_water_mass_ratio:.3f} kg/kg)",
        ),
        (
            "Hot-tank standing loss",
            f"{_kj(store.storage_loss_j_per_kg_air)} over {store.storage_duration_hours:.2f} h",
        ),
        ("Cold-tank standing loss", _kj(store.cold_storage_loss_j_per_kg_air)),
        ("Normalized hot-tank UA", f"{store.thermal_storage_tank_ua_w_per_k:.6g} W/K per kg-air"),
        # Equation (12), written with both sides explicit. E-303 is on the LEFT
        # when it harvests ambient heat; the balance has to add up either way.
        (
            "Coolant heat balance (eq. 12)",
            f"recovered {store.recovered_heat_j_per_kg_air / 1000:.2f} + E-303 absorbed "
            f"{store.cold_return_heat_absorbed_from_ambient_j_per_kg_air / 1000:.2f}"
            f" = air {store.delivered_heat_j_per_kg_air / 1000:.2f} + district heat "
            f"{store.offtake_heat_j_per_kg_air / 1000:.2f} + hot-tank loss "
            f"{store.storage_loss_j_per_kg_air / 1000:.2f} + cold-tank loss "
            f"{store.cold_storage_loss_j_per_kg_air / 1000:.2f} kJ/kg-air",
        ),
        ("Hot-coolant exergy", _kj(result.exergy.hot_water_exergy_j_per_kg_air)),
        ("Cold-loop closure error", f"{store.cold_loop_closure_error_k:.4f} K"),
    ]


def _moisture_rows(result: PlantResult) -> list[tuple[str, str]]:
    """The charge-side moisture diagnostic, as rows.

    ``compressor_moisture_inventory`` is the expensive part - it walks the
    charge train twice - so it is called exactly here, once, for both the CLI
    report and the GUI table.
    """
    moisture = result.moisture
    assert moisture is not None
    vapour = moisture.stored_air_water_vapor_kg_per_kg_dry_air
    storage_limit_c = phase_change_temperature_k(
        moisture.storage_pressure_pa, vapour
    ) - 273.15
    worst_liquid_fraction = maximum_possible_liquid_mass_fraction(vapour)
    compressor_inventory = compressor_moisture_inventory(
        result, separate_after_each_cooler=True
    )
    final_only_inventory = compressor_moisture_inventory(
        result, separate_after_each_cooler=False
    )
    expander_inventory = expander_moisture_inventory(result)
    maximum_expander_suction_liquid = max(
        (
            point.condensed_water_mass_fraction
            for point in expander_inventory
            if point.position == "suction"
        ),
        default=worst_liquid_fraction,
    )
    rows: list[tuple[str, str]] = [
        (
            "Moisture basis",
            "ideal charge-side liquid separators; latent heat is outside the "
            "dry-air energy balance",
        ),
        ("Ambient relative humidity", f"{moisture.ambient_relative_humidity:.1%}"),
        ("Inlet water vapour", f"{moisture.inlet_water_vapor_kg_per_kg_dry_air * 1000:.4f} g/kg-dry-air"),
        (
            "Removed by surface cooler separators",
            f"{moisture.surface_separator_water_kg_per_kg_dry_air * 1000:.4f} g/kg-dry-air",
        ),
        ("Vapour after charge coolers", f"{vapour * 1000:.4f} g/kg-dry-air"),
        (
            f"Stored-air pressure dew point at {moisture.storage_pressure_pa / 1e5:.2f} bar",
            f"{storage_limit_c:.2f} °C",
        ),
        (
            "Maximum calculated expander-suction liquid",
            f"{maximum_expander_suction_liquid:.6%} by mass (published reference "
            f"suction capacity {REFERENCE_WET_EXPANDER_MAX_INLET_LIQUID_MASS_FRACTION:.0%})",
        ),
        (
            "Worst case if every remaining gram condenses",
            f"{worst_liquid_fraction:.4%} by mass (published reference discharge "
            f"capacity {REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION:.0%}; "
            f"dry-air model validity cap "
            f"{DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION:.1%})",
        ),
    ]
    for process in result.discharging.processes:
        if process.kind not in {"expansion", "throttling"}:
            continue
        limit_c = phase_change_temperature_k(
            process.outlet.pressure_pa, vapour
        ) - 273.15
        phase = "PDP" if limit_c >= 0.0 else "frost point"
        if process.kind == "throttling":
            operating_minimum_c = wet_expander_hard_floor_temperature_k(
                process.outlet.pressure_pa, vapour
            ) - 273.15
            basis = "temporary hard floor before trim"
            threshold_name = "required floor"
        else:
            operating_minimum_c = minimum_wet_expander_temperature_k(
                process.outlet.pressure_pa, vapour
            ) - 273.15
            basis = wet_expander_floor_label(limit_c)
            threshold_name = "wet-rated minimum"
        rows.append((
            f"Moisture limit at {process.outlet.pressure_bar:.2f} bar",
            f"{phase} {limit_c:.2f} °C; {threshold_name} "
            f"{operating_minimum_c:.2f} °C ({basis}); actual "
            f"{process.outlet.temperature_c:.2f} °C",
        ))
    for point in compressor_inventory:
        if point.position not in {"suction", "discharge"}:
            continue
        rows.append((
            f"{point.equipment_tag} {point.position} water",
            f"{point.pressure_bar:.3f} bar, {point.temperature_c:.2f} °C; vapour "
            f"{point.water_vapor_mass_fraction:.6%}, liquid "
            f"{point.condensed_water_mass_fraction:.6%}",
        ))
    for point in compressor_inventory:
        if point.position != "cooler outlet / separator inlet":
            continue
        rows.append((
            f"{point.equipment_tag} pre-separator water",
            f"{point.pressure_bar:.3f} bar, {point.temperature_c:.2f} °C; vapour "
            f"{point.water_vapor_mass_fraction:.6%}, liquid "
            f"{point.condensed_water_mass_fraction:.6%}",
        ))
    # Counterfactual screen: what a single final separator would let through.
    for point in final_only_inventory:
        if point.position not in {"suction", "discharge"}:
            continue
        rows.append((
            f"{point.equipment_tag} {point.position} water, final separator only",
            f"vapour {point.water_vapor_mass_fraction:.6%}, liquid "
            f"{point.condensed_water_mass_fraction:.6%}",
        ))
    for point in expander_inventory:
        if point.position not in {"suction", "discharge"}:
            continue
        suffix = f"; {point.note}" if point.note else ""
        rows.append((
            f"{point.equipment_tag} {point.position} water",
            f"{point.pressure_bar:.3f} bar, {point.temperature_c:.2f} °C; vapour "
            f"{point.water_vapor_mass_fraction:.6%}, liquid "
            f"{point.condensed_water_mass_fraction:.6%}{suffix}",
        ))
    return rows


def _offtake_rows(result: PlantResult) -> list[tuple[str, str]]:
    dh = result.heat_offtake
    store = result.thermal_store
    assert dh is not None and store is not None
    return [
        (
            "Heat user",
            f"[{dh.mode}] one exchanger on the whole trunk, "
            f"{store.total_water_mass_ratio:.3f} kg-coolant/kg-air in the store",
        ),
        (
            "Trunk at the first extraction",
            f"{_c(dh.hot_tank_temperature_k)} → {_c(dh.turbine_supply_temperature_k)}",
        ),
        ("Heat sold", _kj(dh.heat_j_per_kg_air)),
        ("Exergy sold", _kj(dh.exergy_j_per_kg_air)),
        (
            "User supply / return",
            f"{dh.return_temperature_k - 273.15:.0f} → {dh.supply_temperature_k - 273.15:.0f} °C, "
            f"{dh.network_water_per_kg_air:.3f} kg-coolant/kg-air, one counter-current stream",
        ),
        (
            "Heat-user exchanger class",
            f"NTU={dh.heat_exchanger_ntu:g}; maximum required "
            f"effectiveness={dh.maximum_required_effectiveness:.4f}; minimum "
            f"margin={dh.minimum_effectiveness_margin:.4f}",
        ),
        ("Wet-expander outlet minimum", wet_expander_envelope_label()),
    ]


def summary_rows(result: PlantResult) -> list[tuple[str, str]]:
    """Every scalar of ``result`` as one ``(metric, value)`` pair.

    THE formatter for plant output. :func:`summary` renders these rows as the
    CLI text report, the GUI inserts the same rows into its table, and neither
    can drift from the other because there is only one list. A leading two-space
    indent marks a sub-row; the order is the order a reader wants: concept and
    headline metrics, the exergy books, the coolant store, the moisture
    diagnostic, the heat user, the optimization outcome.
    """
    rows: list[tuple[str, str]] = [
        (
            "Plant concept",
            plant_concept_label(
                exports_heat=result.heat_offtake is not None
            ),
        ),
        ("Analysis basis", "1 kg of charged/discharged air"),
        ("Compression work", _kj(result.compression_work_input_j_per_kg)),
        ("Expansion work", _kj(result.expansion_work_output_j_per_kg)),
        ("Electrical round-trip efficiency", f"{result.round_trip_efficiency:.2%}"),
        # The single energy metric: output over PURCHASED input. Free ambient
        # streams are reported below as flows, never charged to the denominator,
        # so this may exceed 100%. See PlantResult.
        (
            "Electricity-based useful-energy delivery ratio",
            f"{result.useful_energy_delivery_ratio:.2%}",
        ),
        (
            "Total useful exergy efficiency",
            f"{result.exergy.total_useful_exergy_efficiency:.2%}",
        ),
    ]

    # The Grassmann books, largest first inside each block: destruction is what
    # the components wrecked, loss is what left the boundary intact, and the
    # residual proves nothing has been left out. See caes.exergy equation (6).
    exergy = result.exergy
    rows.append((
        "Total component exergy destruction",
        _kj(exergy.total_destruction_j_per_kg_air),
    ))
    for component, value in sorted(
        exergy.component_destruction_j_per_kg_air.items(), key=lambda item: -item[1]
    ):
        rows.append((f"  exergy destruction: {component}", f"{value / 1000:.3f} kJ/kg-air"))
    rows.append((
        "Total exergy loss (left the boundary unused)",
        _kj(exergy.total_loss_j_per_kg_air),
    ))
    for route, value in sorted(
        exergy.loss_j_per_kg_air.items(), key=lambda item: -item[1]
    ):
        rows.append((f"  loss via {route}", f"{value / 1000:.3f} kJ/kg-air"))
    rows.append((
        "Exergy balance residual",
        f"{exergy.balance_residual_j_per_kg_air:.3f} J/kg-air",
    ))
    if result.external_heat_input_j_per_kg > 0.0:
        rows.append((
            "Ambient energy scavenged (zero exergy at T0)",
            _kj(result.external_heat_input_j_per_kg),
        ))
    throttling = sum(
        process.exergy_destruction_j_per_kg
        for process in result.discharging.processes
        if process.kind == "throttling"
    )
    if throttling > 0.0:
        rows.append(("Anti-icing throttling exergy destruction", _kj(throttling)))

    if result.thermal_store is not None:
        rows.extend(_store_rows(result))
    if result.moisture is not None:
        rows.extend(_moisture_rows(result))
    if result.heat_offtake is not None:
        rows.extend(_offtake_rows(result))
    if result.optimization is not None:
        rows.extend([
            ("Optimization objective", result.optimization.objective),
            (
                "Optimization objective value",
                f"{result.optimization.objective_value:.5g}",
            ),
            ("Optimization points evaluated", str(result.optimization.evaluated_points)),
            (
                "Worst HX endpoint ΔT spread",
                f"{result.optimization.max_hx_temperature_spread_k:.3f} K",
            ),
        ])
    return rows


def _extraction_table(result: PlantResult) -> list[str]:
    """The E-304 ladder as a table: the demand column is what each stage needs,
    the extraction column is what it gets, and the gap is the common margin.

    Under one tank temperature that gap was tens of kelvin at the back of the
    train, and every one of those kelvin was destroyed.
    """
    extraction = result.extraction_exchanger
    assert extraction is not None
    demands = [
        process.outlet.temperature_k
        for process in result.discharging.processes
        if process.kind == "interheating"
    ]
    lines = [
        "",
        f"E-304 extraction exchanger - {len(extraction.extraction_temperatures_k)} "
        f"bleeds, per-zone NTU={extraction.exchanger_ntu:g}:",
        f"  trunk: {_c(extraction.trunk_inlet_temperature_k)} -> "
        f"{_c(extraction.trunk_outlet_temperature_k)}, fully withdrawn "
        f"({extraction.total_water_mass_ratio:.3f} kg-coolant/kg-air in, 0 out)",
        f"  common margin above each stage demand: {extraction.margin_k:.2f} K",
        f"  recuperated into the return: "
        f"{_kj(extraction.recuperated_heat_j_per_kg_air)}, "
        f"{_c(extraction.return_inlet_temperature_k)} -> "
        f"{_c(extraction.return_outlet_temperature_k)}",
        f"  tightest zone approach: {extraction.minimum_terminal_difference_k:.2f} K; "
        f"maximum required effectiveness={extraction.maximum_required_effectiveness:.4f}; "
        f"minimum margin={extraction.minimum_effectiveness_margin:.4f}",
        "  stage      demand   extraction   bleed [kg/kg-air]",
    ]
    for index, (supply_k, ratio) in enumerate(
        zip(extraction.extraction_temperatures_k, extraction.extraction_mass_ratios)
    ):
        demand_c = (
            f"{demands[index] - 273.15:7.2f}" if index < len(demands) else "      -"
        )
        lines.append(
            f"    {index + 1:>3}    {demand_c}      "
            f"{supply_k - 273.15:7.2f}       {ratio:.4f}"
        )
    return lines


def summary(result: PlantResult) -> str:
    """The CLI text report: the shared rows, then the E-304 ladder table."""

    lines = [f"{label}: {value}" for label, value in summary_rows(result)]
    if result.extraction_exchanger is not None:
        lines.extend(_extraction_table(result))
    return "\n".join(lines)


def save_thermodynamic_plots(result: PlantResult, path: str | Path, fluid: str = "Air") -> Path:
    """Save the GUI's T-s, h-s, and p-h diagrams to one comparison figure."""
    import matplotlib.pyplot as plt
    from . import diagrams as plot_diagrams

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    # One set of renderers owns both GUI and file output, preventing the plots
    # from drifting apart as reference lines or state definitions evolve.
    plot_diagrams.draw_ts(axes[0], result, fluid)
    plot_diagrams.draw_hs(axes[1], result, fluid)
    plot_diagrams.draw_ph(axes[2], result, fluid)
    fig.suptitle(f"Normalized CAES cycle · electrical RTE {result.round_trip_efficiency:.1%}")
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def save_sankey_plots(result: PlantResult, path: str | Path) -> Path:
    """Save the energy Sankey and the exergy Grassmann diagram to one figure."""
    import matplotlib.pyplot as plt
    from . import diagrams as plot_diagrams

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stacked, not side by side: both diagrams now run the length of the
    # plant, so they want width, not height. The hover detail the GUI offers
    # has no meaning on paper, and the small tags carry the picture alone.
    fig, axes = plt.subplots(2, 1, figsize=(16, 9))
    plot_diagrams.draw_energy_sankey(axes[0], result)
    plot_diagrams.draw_exergy_sankey(axes[1], result)
    fig.suptitle(
        f"Normalized CAES flow books · electrical RTE {result.round_trip_efficiency:.1%}"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output
