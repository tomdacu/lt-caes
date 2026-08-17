"""Text and plot output for normalized CAES results."""

from __future__ import annotations

from pathlib import Path

from .constants import WATER_FREEZING_TEMPERATURE_K
from .models import PlantResult
from .nomenclature import plant_concept_label
from .moisture import (
    compressor_moisture_inventory,
    expander_moisture_inventory,
    phase_change_temperature_k,
)
from .thermal_limits import (
    DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION,
    EXPANDER_ICE_MARGIN_K,
    REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION,
    REFERENCE_WET_EXPANDER_MAX_INLET_LIQUID_MASS_FRACTION,
    maximum_possible_liquid_mass_fraction,
    minimum_wet_expander_temperature_k,
    wet_expander_hard_floor_temperature_k,
)


def summary(result: PlantResult) -> str:
    lines = [
        f"Plant concept: {plant_concept_label(result.mode, exports_heat=result.heat_offtake is not None)}",
        "Analysis basis: 1 kg of charged/discharged air",
        f"Compression work: {result.compression_work_input_j_per_kg / 1000:.2f} kJ/kg-air",
        f"Expansion work: {result.expansion_work_output_j_per_kg / 1000:.2f} kJ/kg-air",
        f"Electrical round-trip efficiency: {result.round_trip_efficiency:.2%}",
        # The single energy metric: output over PURCHASED input. Free ambient
        # streams are reported below as flows, never charged to the denominator,
        # so this may exceed 100%. See PlantResult.
        f"Electricity-based useful-energy delivery ratio: {result.useful_energy_delivery_ratio:.2%}",
        f"Total useful exergy efficiency: {result.exergy.total_useful_exergy_efficiency:.2%}",
        f"Total component exergy destruction: {result.exergy.total_destruction_j_per_kg_air / 1000:.2f} kJ/kg-air",
        f"Total exergy loss (left the boundary unused): {result.exergy.total_loss_j_per_kg_air / 1000:.2f} kJ/kg-air",
    ]
    # Spell the loss routes out. They are the terms that are easiest to forget and
    # the ones a plant-level change (bottoming cycle, heat offtake) can actually
    # recover - unlike destruction, which needs better hardware.
    for route, value in sorted(result.exergy.loss_j_per_kg_air.items(), key=lambda kv: -kv[1]):
        lines.append(f"  loss via {route}: {value / 1000:.2f} kJ/kg-air")
    # If this is not ~0 the numbers above are not to be trusted; see caes.exergy eq (6).
    lines.append(f"Exergy balance residual: {result.exergy.balance_residual_j_per_kg_air:.3f} J/kg-air")
    if result.external_heat_input_j_per_kg > 0:
        lines.append(
            "Ambient energy scavenged (zero exergy at T0): "
            f"{result.external_heat_input_j_per_kg / 1000:.2f} kJ/kg-air"
        )
    throttling = sum(
        process.exergy_destruction_j_per_kg
        for process in result.discharging.processes
        if process.kind == "throttling"
    )
    if throttling > 0:
        lines.append(
            "Anti-icing throttling exergy destruction: "
            f"{throttling / 1000:.2f} kJ/kg-air"
        )
    if result.moisture:
        moisture = result.moisture
        storage_limit_c = phase_change_temperature_k(
            moisture.storage_pressure_pa,
            moisture.stored_air_water_vapor_kg_per_kg_dry_air,
        ) - 273.15
        worst_liquid_fraction = maximum_possible_liquid_mass_fraction(
            moisture.stored_air_water_vapor_kg_per_kg_dry_air
        )
        compressor_inventory = compressor_moisture_inventory(
            result,
            separate_after_each_cooler=True,
        )
        final_only_inventory = compressor_moisture_inventory(
            result,
            separate_after_each_cooler=False,
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
        lines.extend(
            (
                "",
                "Moisture diagnostic (ideal charge-side liquid separators; "
                "latent heat is outside the dry-air energy balance):",
                f"  ambient RH: {moisture.ambient_relative_humidity:.1%}",
                "  inlet water vapour: "
                f"{moisture.inlet_water_vapor_kg_per_kg_dry_air * 1000:.4f} g/kg-dry-air",
                "  removed by surface cooler separators: "
                f"{moisture.surface_separator_water_kg_per_kg_dry_air * 1000:.4f} g/kg-dry-air",
                "  vapour after charge coolers: "
                f"{moisture.stored_air_water_vapor_kg_per_kg_dry_air * 1000:.4f} g/kg-dry-air",
                f"  stored-air pressure dew point at {moisture.storage_pressure_pa / 1e5:.2f} bar: "
                f"{storage_limit_c:.2f} °C",
                "  wet-expander reference screening:",
                "    maximum calculated expander-suction liquid: "
                f"{maximum_expander_suction_liquid:.6%} by mass",
                "    published reference suction capacity: "
                f"{REFERENCE_WET_EXPANDER_MAX_INLET_LIQUID_MASS_FRACTION:.0%} by mass",
                "    worst case if every remaining gram condenses: "
                f"{worst_liquid_fraction:.4%} by mass",
                "    published reference discharge capacity: "
                f"{REFERENCE_WET_EXPANDER_MAX_DISCHARGE_LIQUID_MASS_FRACTION:.0%} by mass",
                "    dry-air model validity cap: "
                f"{DRY_AIR_MODEL_MAX_POSSIBLE_LIQUID_MASS_FRACTION:.1%} by mass",
                "  discharge phase boundaries and wet-rated lower envelope:",
            )
        )
        for process in result.discharging.processes:
            if process.kind not in {"expansion", "throttling"}:
                continue
            limit_c = phase_change_temperature_k(
                process.outlet.pressure_pa,
                moisture.stored_air_water_vapor_kg_per_kg_dry_air,
            ) - 273.15
            phase = "PDP" if limit_c >= 0.0 else "frost point"
            if process.kind == "throttling":
                operating_minimum_c = wet_expander_hard_floor_temperature_k(
                    process.outlet.pressure_pa,
                    moisture.stored_air_water_vapor_kg_per_kg_dry_air,
                ) - 273.15
                basis = "temporary hard floor before trim"
                threshold_name = "required floor"
            else:
                operating_minimum_c = minimum_wet_expander_temperature_k(
                    process.outlet.pressure_pa,
                    moisture.stored_air_water_vapor_kg_per_kg_dry_air,
                ) - 273.15
                basis = (
                    # The floor is the freezing reference plus the margin, not
                    # the margin itself; the two happen to be equal only
                    # because pure water freezes at 0 degC.
                    f"{WATER_FREEZING_TEMPERATURE_K - 273.15 + EXPANDER_ICE_MARGIN_K:.0f} °C liquid-water floor"
                    if limit_c >= 0.0
                    else f"frost point + {EXPANDER_ICE_MARGIN_K:.0f} K"
                )
                threshold_name = "wet-rated minimum"
            lines.append(
                f"    {process.kind} outlet at {process.outlet.pressure_bar:.2f} bar: "
                f"{phase} {limit_c:.2f} °C; {threshold_name} "
                f"{operating_minimum_c:.2f} °C ({basis}); actual "
                f"{process.outlet.temperature_c:.2f} °C"
            )
        lines.append(
            "  compressor body water inventory with a separator after each cooler:"
        )
        for point in compressor_inventory:
            if point.position not in {"suction", "discharge"}:
                continue
            lines.append(
                f"    {point.equipment_tag} {point.position}: "
                f"{point.pressure_bar:.3f} bar, {point.temperature_c:.2f} °C; "
                f"vapour {point.water_vapor_mass_fraction:.6%}, "
                f"liquid {point.condensed_water_mass_fraction:.6%}"
            )
        lines.append("  cooler outlets before their separator:")
        for point in compressor_inventory:
            if point.position != "cooler outlet / separator inlet":
                continue
            lines.append(
                f"    {point.equipment_tag}: {point.pressure_bar:.3f} bar, "
                f"{point.temperature_c:.2f} °C; vapour "
                f"{point.water_vapor_mass_fraction:.6%}, liquid "
                f"{point.condensed_water_mass_fraction:.6%}"
            )
        lines.append(
            "  counterfactual with only the final separator "
            "(equilibrium screen; wet compressor physics not modelled):"
        )
        for point in final_only_inventory:
            if point.position not in {"suction", "discharge"}:
                continue
            lines.append(
                f"    {point.equipment_tag} {point.position}: "
                f"vapour {point.water_vapor_mass_fraction:.6%}, "
                f"liquid {point.condensed_water_mass_fraction:.6%}"
            )
        if expander_inventory:
            lines.append(
                "  expander body water inventory with sequential outlet separators:"
            )
            for point in expander_inventory:
                if point.position not in {"suction", "discharge"}:
                    continue
                suffix = f"; {point.note}" if point.note else ""
                lines.append(
                    f"    {point.equipment_tag} {point.position}: "
                    f"{point.pressure_bar:.3f} bar, {point.temperature_c:.2f} °C; "
                    f"vapour {point.water_vapor_mass_fraction:.6%}, "
                    f"liquid {point.condensed_water_mass_fraction:.6%}{suffix}"
                )
    if result.thermal_store:
        store = result.thermal_store
        lines.extend(
            (
                f"Cold/hot/available coolant temperature: {store.cold_temperature_k - 273.15:.1f} / {store.hot_temperature_before_loss_k - 273.15:.1f} / {store.hot_temperature_available_k - 273.15:.1f} °C",
                "Coolant direct limits (minimum / maximum) and calculated extrema: "
                f"{store.coolant_minimum_temperature_k - 273.15:.2f} / "
                f"{store.coolant_maximum_temperature_k - 273.15:.2f} °C; "
                f"coldest={store.coolant_minimum_temperature_reached_k - 273.15:.2f} °C, "
                f"hottest={store.coolant_maximum_temperature_reached_k - 273.15:.2f} °C",
                f"Untreated all-return mean: {store.returned_temperature_k - 273.15:.1f} °C",
                "E-303 heat-only optimized suffix: "
                + (
                    f"stages {store.cold_return_recovery_start_stage + 1} onward, "
                    if store.cold_return_recovery_start_stage is not None
                    else "bypassed, "
                )
                + f"selected mix {store.cold_return_recovery_inlet_temperature_k - 273.15:.1f} -> "
                f"{store.cold_return_recovery_outlet_temperature_k - 273.15:.1f} °C, "
                f"final mixed tank inlet {store.cold_return_exchanger_outlet_temperature_k - 273.15:.1f} °C, "
                f"NTU={store.cold_return_exchanger_ntu:.3g}, absorbed "
                f"{store.cold_return_heat_absorbed_from_ambient_j_per_kg_air / 1000:.2f} kJ/kg-air",
                f"Total normalized coolant mass: {store.total_water_mass_ratio:.3f} kg-coolant/kg-air",
                f"Hot-tank standing loss: {store.storage_loss_j_per_kg_air / 1000:.2f} kJ/kg-air "
                f"over {store.storage_duration_hours:.2f} h "
                f"(normalized UA={store.thermal_storage_tank_ua_w_per_k:.6g} W/K per kg-air)",
                # Equation (12).  E-303 is on the LEFT when it harvests ambient
                # heat, so the balance is written with both sides explicit.
                "Coolant heat: recovered "
                f"{store.recovered_heat_j_per_kg_air / 1000:.2f} + E-303 absorbed "
                f"{store.cold_return_heat_absorbed_from_ambient_j_per_kg_air / 1000:.2f}"
                " = air "
                f"{store.delivered_heat_j_per_kg_air / 1000:.2f} + district heat "
                f"{store.offtake_heat_j_per_kg_air / 1000:.2f} + hot-tank loss "
                f"{store.storage_loss_j_per_kg_air / 1000:.2f} + cold-tank loss "
                f"{store.cold_storage_loss_j_per_kg_air / 1000:.2f} kJ/kg-air",
                f"Hot-coolant exergy: {result.exergy.hot_water_exergy_j_per_kg_air / 1000:.2f} kJ/kg-air",
            )
        )

    if result.heat_offtake:
        # The turbines are served first; the user gets what their exact duties
        # left in the trunk, station by station down the cascade.
        dh = result.heat_offtake
        store = result.thermal_store
        assert store is not None
        lines.extend(
            (
                "",
                f"Heat user [{dh.mode}] - series cascade, "
                f"{len(dh.taps)} station" + ("s" if len(dh.taps) != 1 else "")
                + f", {store.total_water_mass_ratio:.3f} kg-coolant/kg-air in the store:",
                f"  trunk: {dh.hot_tank_temperature_k - 273.15:.1f} -> "
                f"{dh.turbine_supply_temperature_k - 273.15:.1f} °C at the hottest bleed",
                f"  heat sold: {dh.heat_j_per_kg_air / 1000:.2f} kJ/kg-air",
                f"  exergy sold: {dh.exergy_j_per_kg_air / 1000:.2f} kJ/kg-air",
                f"  user: {dh.return_temperature_k - 273.15:.0f} -> {dh.supply_temperature_k - 273.15:.0f} °C, "
                f"{dh.network_water_per_kg_air:.3f} kg-coolant/kg-air, one counter-current stream",
                f"  exchanger class NTU={dh.heat_exchanger_ntu:g}; maximum required "
                f"effectiveness={dh.maximum_required_effectiveness:.4f}; minimum "
                f"margin={dh.minimum_effectiveness_margin:.4f}",
            )
        )
        if len(dh.taps) > 1:
            lines.append("  stations, hot end first:")
            for tap in dh.taps:
                lines.append(
                    f"    E-302{chr(ord('a') + tap.station_index)}: trunk "
                    f"{tap.plant_inlet_temperature_k - 273.15:6.1f} -> "
                    f"{tap.plant_outlet_temperature_k - 273.15:6.1f} °C at "
                    f"{tap.plant_water_per_kg_air:.3f} kg/kg-air, user "
                    f"{tap.user_inlet_temperature_k - 273.15:5.1f} -> "
                    f"{tap.user_outlet_temperature_k - 273.15:5.1f} °C, "
                    f"{tap.heat_j_per_kg_air / 1000:6.2f} kJ/kg-air"
                )
        lines.append(
            "  wet-expander outlet minimum: "
            f"{WATER_FREEZING_TEMPERATURE_K - 273.15 + EXPANDER_ICE_MARGIN_K:.0f} °C "
            "in the permitted liquid region; otherwise local frost point "
            f"+ {EXPANDER_ICE_MARGIN_K:.0f} K"
        )
    if result.optimization:
        lines.append(
            f"Optimization: {result.optimization.objective}, objective={result.optimization.objective_value:.5g}, "
            f"worst HX endpoint spread={result.optimization.max_hx_temperature_spread_k:.3f} K, "
            f"{result.optimization.evaluated_points} points"
        )
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
