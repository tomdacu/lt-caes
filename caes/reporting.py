"""Human-readable reports and non-interactive cycle plots."""

from __future__ import annotations

from pathlib import Path

from .models import PlantResult


def summary(result: PlantResult) -> str:
    lines = [
        f"Mode: {result.mode}",
        f"Air batch: {result.air_mass_kg:,.0f} kg",
        f"Compression work: {result.compression_work_input_j / 3.6e6:,.2f} kWh",
        f"Expansion work: {result.expansion_work_output_j / 3.6e6:,.2f} kWh",
        f"Design-point compressor/turbine power: {result.charging_power_kw:,.1f} / {result.discharging_power_kw:,.1f} kW",
        f"Shaft-work ratio: {result.shaft_work_ratio:.2%}",
    ]
    if result.round_trip_efficiency is None:
        lines.append("Storage-only RTE: not defined for D-CAES with external reheat")
        lines.append(f"External heat supplied: {result.external_heat_input_j / 3.6e6:,.2f} kWh")
    else:
        lines.append(f"Electrical/shaft round-trip efficiency: {result.round_trip_efficiency:.2%}")
    if result.thermal_store:
        store = result.thermal_store
        lines.extend((
            f"Thermal-store final temperature: {store.temperature_k - 273.15:.1f} °C",
            f"Heat recovered/delivered/lost: {store.recovered_energy_j / 3.6e6:.2f} / {store.delivered_energy_j / 3.6e6:.2f} / {store.lost_energy_j / 3.6e6:.2f} kWh",
        ))
    hx = result.heat_exchanger_summary
    if hx.model == "counterflow_ntu" and hx.exchanger_count:
        lines.extend((
            f"Counter-current heat exchangers: {hx.exchanger_count}",
            f"Area per exchanger / total: {hx.area_per_exchanger_m2:.1f} / {hx.total_area_m2:.1f} m²",
            f"UA per exchanger: {hx.ua_per_exchanger_w_per_k:.1f} W/K",
        ))
        if hx.screening_installed_cost_eur is not None:
            lines.append(f"Configured screening installed cost: €{hx.screening_installed_cost_eur:,.0f}")
        else:
            lines.append("Screening installed cost: not calculated (supply a reference cost correlation)")
    if result.water_flow_optimization:
        optimisation = result.water_flow_optimization
        lines.extend((
            f"Optimized water mass flow: {optimisation.optimized_water_mass_flow_kg_s:.3f} kg/s",
            f"Thermal-recovery target achieved: {optimisation.achieved_fraction:.2%} of the {optimisation.reference_water_mass_flow_kg_s:g} kg/s reference",
        ))
    return "\n".join(lines)


def save_temperature_entropy_plot(result: PlantResult, path: str | Path) -> Path:
    """Save a simple T-s trace; no GUI or global plotting state is required."""
    import matplotlib.pyplot as plt

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    for cycle, color in ((result.charging, "tab:red"), (result.discharging, "tab:blue")):
        states = cycle.states
        ax.plot([s.entropy_j_per_kgk / 1000 for s in states], [s.temperature_c for s in states], "o-", color=color, label=cycle.name)
    ax.set(xlabel="Specific entropy [kJ/(kg·K)]", ylabel="Temperature [°C]", title="CAES cycle trace")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output
