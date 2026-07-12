"""Interactive normalized CAES simulator with dependency-aware inputs."""

from __future__ import annotations

import json
import tkinter as tk
from dataclasses import fields
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .config import (
    HeatExchangerModel,
    PlantConfig,
    PlantMode,
    ThermalSurplusUse,
    WaterFlowMode,
)
from .logic import CONFIG_GROUPS, FIELD_RULES, active_fields
from .models import PlantResult, Process
from .plant import CAESPlant

ENUM_TYPES = {
    "mode": PlantMode,
    "heat_exchanger_model": HeatExchangerModel,
    "water_flow_mode": WaterFlowMode,
    "thermal_surplus_use": ThermalSurplusUse,
}
INTEGER_FIELDS = {"compressor_stages", "expander_stages"}


class CAESGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Normalized LTA-CAES Simulator")
        self.geometry("1420x900")
        self.minsize(1120, 700)
        self._values = PlantConfig().to_dict()
        self._widgets: dict[str, ttk.Widget] = {}
        self._variables: dict[str, tk.Variable] = {}
        self._result: PlantResult | None = None
        self._status = tk.StringVar(value="Ready")
        self._auto_run = tk.BooleanVar(value=True)
        self._pending: str | None = None
        self._build_style()
        self._build_menu()
        self._build_layout()
        self._refresh_dependencies()
        self.after(100, self._run)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 9, "bold"))
        style.configure("KPI.TLabel", font=("Segoe UI Semibold", 14))
        style.configure("Muted.TLabel", foreground="#666", font=("Segoe UI", 8))

    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="Load configuration…", command=self._load, accelerator="Ctrl+O")
        file_menu.add_command(label="Save configuration…", command=self._save, accelerator="Ctrl+S")
        file_menu.add_command(label="Reset defaults", command=self._reset)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.destroy)
        bar.add_cascade(label="File", menu=file_menu)
        run_menu = tk.Menu(bar, tearoff=0)
        run_menu.add_command(label="Run simulation", command=self._run, accelerator="F5")
        bar.add_cascade(label="Run", menu=run_menu)
        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="About model", command=self._about)
        bar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=bar)
        self.bind("<Control-o>", lambda event: self._load())
        self.bind("<Control-s>", lambda event: self._save())
        self.bind("<F5>", lambda event: self._run())

    def _build_layout(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, width=430)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=3)
        self._build_config(left)
        self._build_results(right)
        ttk.Label(self, textvariable=self._status, relief="sunken", anchor="w", padding=(6, 2)).pack(fill="x")

    def _build_config(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, padding=8)
        header.pack(fill="x")
        ttk.Label(header, text="Model inputs", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(header, text="Reset", command=self._reset).pack(side="right")

        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        field_map = {field.name: field for field in fields(PlantConfig)}
        for group_name, names in CONFIG_GROUPS:
            group = ttk.LabelFrame(body, text=group_name, padding=8, style="Section.TLabelframe")
            group.pack(fill="x", padx=8, pady=(0, 7))
            for name in names:
                self._build_field(group, name, field_map[name])

        controls = ttk.Frame(parent, padding=8)
        controls.pack(fill="x", side="bottom")
        ttk.Button(controls, text="Run simulation (F5)", command=self._run).pack(fill="x")
        ttk.Checkbutton(controls, text="Auto-run on change", variable=self._auto_run).pack(anchor="w", pady=(4, 0))

    def _build_field(self, parent: ttk.Frame, name: str, field: Any) -> None:
        rule = FIELD_RULES[name]
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=rule.label, width=26, anchor="w").pack(side="left")
        enum_type = ENUM_TYPES.get(name)
        current = self._values[name]
        if enum_type:
            variable = tk.StringVar(value=str(current))
            widget = ttk.Combobox(row, textvariable=variable, values=[member.value for member in enum_type], state="readonly", width=18)
            widget.bind("<<ComboboxSelected>>", lambda event, n=name: self._changed(n))
        elif field.type is bool or name == "use_ambient_reheat":
            variable = tk.BooleanVar(value=bool(current))
            widget = ttk.Checkbutton(row, variable=variable, command=lambda n=name: self._changed(n))
        else:
            variable = tk.StringVar(value=f"{current:g}" if isinstance(current, float) else str(current))
            widget = ttk.Entry(row, textvariable=variable, width=18)
            widget.bind("<FocusOut>", lambda event, n=name: self._changed(n))
            widget.bind("<Return>", lambda event, n=name: self._changed(n))
        widget.pack(side="left")
        if rule.unit:
            ttk.Label(row, text=rule.unit, style="Muted.TLabel", width=10).pack(side="left", padx=(4, 0))
        self._widgets[name] = widget
        self._variables[name] = variable

    def _parse_values(self) -> PlantConfig:
        data: dict[str, Any] = {}
        for field in fields(PlantConfig):
            name = field.name
            value = self._variables[name].get()
            if name in ENUM_TYPES:
                data[name] = value
            elif name == "use_ambient_reheat":
                data[name] = bool(value)
            elif name in INTEGER_FIELDS:
                data[name] = int(round(float(str(value).replace(",", "."))))
            elif name == "fluid":
                data[name] = str(value)
            else:
                data[name] = float(str(value).replace(",", "."))
        return PlantConfig(**data)

    def _changed(self, name: str) -> None:
        try:
            config = self._parse_values()
        except (ValueError, TypeError) as exc:
            self._status.set(f"Invalid input: {exc}")
            return
        self._values = config.to_dict()
        self._refresh_dependencies(config)
        self._status.set(f"Updated {FIELD_RULES[name].label}")
        if self._auto_run.get():
            if self._pending:
                self.after_cancel(self._pending)
            self._pending = self.after(250, self._run)

    def _refresh_dependencies(self, config: PlantConfig | None = None) -> None:
        config = config or PlantConfig(**self._values)
        active = active_fields(config)
        dormant: list[str] = []
        for name, widget in self._widgets.items():
            enabled = name in active
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly" if enabled else "disabled")
            else:
                widget.configure(state="normal" if enabled else "disabled")
            if not enabled:
                dormant.append(FIELD_RULES[name].label)
        if dormant:
            self._status.set("Dormant inputs: " + ", ".join(dormant))

    def _load(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON configuration", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            allowed = {field.name for field in fields(PlantConfig)}
            unknown = set(data) - allowed
            if unknown:
                raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")
            config = PlantConfig(**data)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Load failed", str(exc))
            return
        self._values = config.to_dict()
        for name, value in self._values.items():
            self._variables[name].set(value)
        self._refresh_dependencies(config)
        self._run()

    def _save(self) -> None:
        try:
            config = self._parse_values()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid configuration", str(exc))
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON configuration", "*.json")])
        if path:
            Path(path).write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")

    def _reset(self) -> None:
        config = PlantConfig()
        self._values = config.to_dict()
        for name, value in self._values.items():
            self._variables[name].set(value)
        self._refresh_dependencies(config)
        self._run()

    def _build_results(self, parent: ttk.Frame) -> None:
        self._build_kpis(parent)
        graphics = ttk.Notebook(parent)
        graphics.pack(fill="both", expand=True, padx=8, pady=4)
        self._ts_ax, self._ts_canvas = self._make_figure_tab(graphics, "T-s cycle", (8, 4.2))
        self._th_ax, self._th_canvas = self._make_figure_tab(graphics, "T-h cycle", (8, 4.2))
        self._ph_ax, self._ph_canvas = self._make_figure_tab(graphics, "p-h cycle", (8, 4.2))
        details = ttk.Notebook(parent)
        details.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self._charge_table = self._make_table(details, "Charging")
        self._discharge_table = self._make_table(details, "Discharging")
        self._summary_table = self._make_summary(details, "Efficiency & exergy")

    def _build_kpis(self, parent: ttk.Frame) -> None:
        strip = ttk.Frame(parent, padding=8)
        strip.pack(fill="x")
        self._kpis: dict[str, ttk.Label] = {}
        for title, key in (
            ("Electrical RTE", "rte"),
            ("Total exergy eff.", "exergy"),
            ("Hot-water temp.", "hot"),
            ("Thermal surplus", "surplus"),
        ):
            card = ttk.LabelFrame(strip, text=title, padding=8)
            card.pack(side="left", fill="x", expand=True, padx=(0, 6))
            value = ttk.Label(card, text="—", style="KPI.TLabel")
            value.pack(anchor="w")
            self._kpis[key] = value

    def _make_figure_tab(self, notebook: ttk.Notebook, title: str, size: tuple[float, float]):
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        figure, axis = plt.subplots(figsize=size, dpi=100)
        canvas = FigureCanvasTkAgg(figure, master=frame)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        return axis, canvas

    def _make_table(self, notebook: ttk.Notebook, title: str) -> ttk.Treeview:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        columns = ("kind", "p_in", "t_in", "p_out", "t_out", "work", "heat", "water", "water_out", "ex_dest")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        headings = {
            "kind": "Component", "p_in": "p in [bar]", "t_in": "T in [°C]", "p_out": "p out [bar]",
            "t_out": "T out [°C]", "work": "w [kJ/kg]", "heat": "q air [kJ/kg]",
            "water": "mw/ma", "water_out": "Tw out [°C]", "ex_dest": "I [kJ/kg]",
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=105, anchor="w" if column == "kind" else "e")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    def _make_summary(self, notebook: ttk.Notebook, title: str) -> ttk.Treeview:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        tree = ttk.Treeview(frame, columns=("metric", "value"), show="headings")
        tree.heading("metric", text="Metric")
        tree.heading("value", text="Value")
        tree.column("metric", width=360, anchor="w")
        tree.column("value", width=260, anchor="e")
        tree.pack(fill="both", expand=True)
        return tree

    def _run(self) -> None:
        self._pending = None
        try:
            config = self._parse_values()
            result = CAESPlant(config).run()
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"Simulation error: {exc}")
            return
        self._result = result
        self._values = config.to_dict()
        self._update_kpis()
        self._draw_thermodynamic_diagrams(result)
        self._populate_tables(result)
        self._status.set(f"Complete: {result.mode}, RTE={result.round_trip_efficiency:.2%}")

    def _update_kpis(self) -> None:
        result = self._result
        if not result:
            return
        self._kpis["rte"].configure(text=f"{result.round_trip_efficiency:.1%}")
        self._kpis["exergy"].configure(text=f"{result.exergy.total_useful_exergy_efficiency:.1%}")
        if result.thermal_store:
            self._kpis["hot"].configure(text=f"{result.thermal_store.hot_temperature_available_k - 273.15:.1f} °C")
            self._kpis["surplus"].configure(text=f"{result.thermal_store.surplus_heat_j_per_kg_air / 1000:.1f} kJ/kg")
        else:
            self._kpis["hot"].configure(text="n/a")
            self._kpis["surplus"].configure(text="rejected")

    def _draw_thermodynamic_diagrams(self, result: PlantResult) -> None:
        diagrams = (
            (
                self._ts_ax,
                self._ts_canvas,
                lambda state: state.entropy_j_per_kgk / 1000,
                lambda state: state.temperature_c,
                "Specific entropy [kJ/(kg·K)]",
                "Temperature [°C]",
                "T-s cycle",
                False,
            ),
            (
                self._th_ax,
                self._th_canvas,
                lambda state: state.enthalpy_j_per_kg / 1000,
                lambda state: state.temperature_c,
                "Specific enthalpy [kJ/kg]",
                "Temperature [°C]",
                "T-h cycle",
                False,
            ),
            (
                self._ph_ax,
                self._ph_canvas,
                lambda state: state.enthalpy_j_per_kg / 1000,
                lambda state: state.pressure_bar,
                "Specific enthalpy [kJ/kg]",
                "Pressure [bar]",
                "p-h cycle",
                True,
            ),
        )
        cycles = ((result.charging, "tab:red"), (result.discharging, "tab:blue"))
        for ax, canvas, x_value, y_value, x_label, y_label, title, log_pressure in diagrams:
            ax.clear()
            for cycle, color in cycles:
                states = cycle.states
                ax.plot(
                    [x_value(state) for state in states],
                    [y_value(state) for state in states],
                    "o-",
                    color=color,
                    label=cycle.name,
                )
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)
            ax.set_title(f"{title} · electrical RTE {result.round_trip_efficiency:.1%}")
            if log_pressure:
                ax.set_yscale("log")
            ax.grid(True, which="both", alpha=0.3)
            ax.legend()
            canvas.draw_idle()

    def _populate_tables(self, result: PlantResult) -> None:
        self._populate_processes(self._charge_table, result.charging.processes)
        self._populate_processes(self._discharge_table, result.discharging.processes)
        tree = self._summary_table
        for item in tree.get_children():
            tree.delete(item)
        rows = [
            ("Electrical round-trip efficiency", f"{result.round_trip_efficiency:.3%}"),
            ("Total useful exergy efficiency", f"{result.exergy.total_useful_exergy_efficiency:.3%}"),
            ("Compression specific work", f"{result.compression_work_input_j_per_kg / 1000:.2f} kJ/kg-air"),
            ("Expansion specific work", f"{result.expansion_work_output_j_per_kg / 1000:.2f} kJ/kg-air"),
            ("Total exergy destruction", f"{result.exergy.total_destruction_j_per_kg_air / 1000:.2f} kJ/kg-air"),
        ]
        if result.thermal_store:
            s = result.thermal_store
            rows += [
                ("Hot-water temperature available", f"{s.hot_temperature_available_k - 273.15:.2f} °C"),
                ("Recovered heat", f"{s.recovered_heat_j_per_kg_air / 1000:.2f} kJ/kg-air"),
                ("Air-reheat delivery", f"{s.delivered_heat_j_per_kg_air / 1000:.2f} kJ/kg-air"),
                ("Thermal surplus", f"{s.surplus_heat_j_per_kg_air / 1000:.2f} kJ/kg-air"),
                ("Surplus exergy", f"{s.surplus_exergy_j_per_kg_air / 1000:.2f} kJ/kg-air"),
                ("Total normalized water", f"{s.total_water_mass_ratio:.4f} kg/kg-air"),
            ]
        if result.optimization:
            rows += [
                ("Optimization objective", result.optimization.objective),
                ("Selected water/air ratio per HX", f"{result.optimization.selected_water_air_mass_ratio:.5f}"),
            ]
        for component, value in sorted(result.exergy.component_destruction_j_per_kg_air.items()):
            rows.append((f"Exergy destruction: {component}", f"{value / 1000:.3f} kJ/kg-air"))
        for metric, value in rows:
            tree.insert("", "end", values=(metric, value))

    def _populate_processes(self, tree: ttk.Treeview, processes: list[Process]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for process in processes:
            hx = process.heat_exchanger
            tree.insert(
                "",
                "end",
                values=(
                    process.kind,
                    f"{process.inlet.pressure_bar:.2f}",
                    f"{process.inlet.temperature_c:.1f}",
                    f"{process.outlet.pressure_bar:.2f}",
                    f"{process.outlet.temperature_c:.1f}",
                    f"{process.work_j_per_kg / 1000:+.2f}",
                    f"{process.heat_to_air_j_per_kg / 1000:+.2f}",
                    f"{hx.water_air_mass_ratio:.3f}" if hx else "—",
                    f"{hx.water_outlet_temperature_k - 273.15:.1f}" if hx else "—",
                    f"{process.exergy_destruction_j_per_kg / 1000:.3f}",
                ),
            )

    def _about(self) -> None:
        messagebox.showinfo(
            "About",
            "Normalized D-CAES / water LTA-CAES simulator\n\n"
            "Interactive T-s, T-h, and p-h thermodynamic diagrams.\n"
            "All results are normalized per kilogram of air; no economic or time-domain model is included.",
        )


def main() -> int:
    app = CAESGUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
