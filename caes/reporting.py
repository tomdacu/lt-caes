"""Text and plot output for normalized CAES results."""

from __future__ import annotations

from pathlib import Path

from .models import PlantResult


def summary(result: PlantResult) -> str:
    lines = [
        f"Mode: {result.mode}",
        "Analysis basis: 1 kg of charged/discharged air",
        f"Compression work: {result.compression_work_input_j_per_kg / 1000:.2f} kJ/kg-air",
        f"Expansion work: {result.expansion_work_output_j_per_kg / 1000:.2f} kJ/kg-air",
        f"Electrical round-trip efficiency: {result.round_trip_efficiency:.2%}",
        f"Total useful exergy efficiency: {result.exergy.total_useful_exergy_efficiency:.2%}",
        f"Total component exergy destruction: {result.exergy.total_destruction_j_per_kg_air / 1000:.2f} kJ/kg-air",
    ]
    if result.external_heat_input_j_per_kg > 0:
        lines.append(f"External ambient heat: {result.external_heat_input_j_per_kg / 1000:.2f} kJ/kg-air")
    if result.thermal_store:
        store = result.thermal_store
        destination = "useful heat" if store.useful_surplus else "rejected"
        lines.extend(
            (
                f"Cold/hot/available water temperature: {store.cold_temperature_k - 273.15:.1f} / {store.hot_temperature_before_loss_k - 273.15:.1f} / {store.hot_temperature_available_k - 273.15:.1f} °C",
                f"Water returned after reheat: {store.returned_temperature_k - 273.15:.1f} °C",
                f"Total normalized water mass: {store.total_water_mass_ratio:.3f} kg-water/kg-air",
                f"Recovered/delivered/surplus heat: {store.recovered_heat_j_per_kg_air / 1000:.2f} / {store.delivered_heat_j_per_kg_air / 1000:.2f} / {store.surplus_heat_j_per_kg_air / 1000:.2f} kJ/kg-air",
                f"Surplus destination: {destination}",
                f"Hot-water exergy: {result.exergy.hot_water_exergy_j_per_kg_air / 1000:.2f} kJ/kg-air",
            )
        )
    if result.selected_water_air_mass_ratio is not None:
        lines.append(f"Selected water/air ratio per charging HX: {result.selected_water_air_mass_ratio:.4f} kg/kg")
    if result.optimization:
        lines.append(
            f"Optimization: {result.optimization.objective}, objective={result.optimization.objective_value:.5g}, {result.optimization.evaluated_points} points"
        )
    return "\n".join(lines)


def save_thermodynamic_plots(result: PlantResult, path: str | Path) -> Path:
    """Save T-s, T-h, and p-h traces to one comparison figure."""
    import matplotlib.pyplot as plt

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    diagrams = (
        (axes[0], lambda state: state.entropy_j_per_kgk / 1000, lambda state: state.temperature_c,
         "Specific entropy [kJ/(kg·K)]", "Temperature [°C]", "T-s", False),
        (axes[1], lambda state: state.enthalpy_j_per_kg / 1000, lambda state: state.temperature_c,
         "Specific enthalpy [kJ/kg]", "Temperature [°C]", "T-h", False),
        (axes[2], lambda state: state.enthalpy_j_per_kg / 1000, lambda state: state.pressure_bar,
         "Specific enthalpy [kJ/kg]", "Pressure [bar]", "p-h", True),
    )
    for ax, x_value, y_value, x_label, y_label, title, log_pressure in diagrams:
        for cycle, color in ((result.charging, "tab:red"), (result.discharging, "tab:blue")):
            states = cycle.states
            ax.plot(
                [x_value(state) for state in states],
                [y_value(state) for state in states],
                "o-",
                color=color,
                label=cycle.name,
            )
        ax.set(xlabel=x_label, ylabel=y_label, title=title)
        if log_pressure:
            ax.set_yscale("log")
        ax.legend()
        ax.grid(True, which="both", alpha=0.3)
    fig.suptitle(f"Normalized CAES cycle · electrical RTE {result.round_trip_efficiency:.1%}")
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output
