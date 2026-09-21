"""Interactive normalized CAES simulator with dependency-aware inputs."""

from __future__ import annotations

import tkinter as tk
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import fields
from multiprocessing import freeze_support, get_context
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .config import (
    OptimizationObjective,
    PlantConfig,
    PlantMode,
    HeatOfftake,
    load_config,
    save_config,
)
from . import diagrams, pid
from .logic import FIELD_RULES, active_fields, grouped_fields
from .models import PlantResult, Process
from .nomenclature import (
    HEAT_OFFTAKE_LABELS,
    LTAHP_LABEL,
    LTA_LABEL,
    PLANT_MODE_LABELS,
    plant_concept_label,
)
from .plant import CAESPlant
from .reporting import summary_rows

ENUM_TYPES = {
    "mode": PlantMode,
    "optimization_objective": OptimizationObjective,
    "heat_offtake": HeatOfftake,
}
ENUM_DISPLAY = {
    "mode": {
        mode.value: label for mode, label in PLANT_MODE_LABELS.items()
    },
    "optimization_objective": {
        OptimizationObjective.MAX_ELECTRIC_EFFICIENCY.value: "Maximum electrical RTE",
        OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY.value: "Maximum electricity + DH heat",
    },
    "heat_offtake": {
        offtake.value: label for offtake, label in HEAT_OFFTAKE_LABELS.items()
    },
}
# These values are used as counts by the plant solver (``range(count)``). Keep
# the GUI parser aligned with the dataclass schema: the startup parse used to
# convert the displayed ``4`` to ``4.0``, which then failed validation with
# ``TypeError: 'float' object cannot be interpreted as an integer``.
INTEGER_FIELDS = {
    "compressor_stages",
    "expander_stages",
}


def _is_bool_field(field: Any) -> bool:
    """Detect boolean config fields from their DEFAULT VALUE.

    ``caes.config`` uses postponed annotations, so ``field.type`` is the string
    ``"bool"``, not the type. The default is a real object and never lies.
    """
    return isinstance(field.default, bool)


def _solve_config(config: PlantConfig) -> PlantResult:
    """Process-pool entry point; it must remain module-level for Windows spawn."""
    return CAESPlant(config).run()


class CAESGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Normalized CAES Simulator - AD / LTA / LTAHP")
        self.geometry("1420x900")
        self.minsize(1120, 700)
        self._values = PlantConfig().to_dict()
        self._widgets: dict[str, ttk.Widget] = {}
        self._variables: dict[str, tk.Variable] = {}
        self._result: PlantResult | None = None
        self._status = tk.StringVar(value="Ready")
        self._busy_text = tk.StringVar(value="")
        self._pending: str | None = None
        # A worker thread is insufficient here: the nested CoolProp/root-finding
        # work can retain the GIL long enough to starve Tk's event loop.  A process
        # gives the window and spinner an independent Python interpreter.
        self._executor = ProcessPoolExecutor(
            max_workers=1,
            mp_context=get_context("spawn"),
        )
        self._solver_future: Future[PlantResult] | None = None
        self._active_run: tuple[int, PlantConfig] | None = None
        self._requested_run: tuple[int, PlantConfig] | None = None
        self._run_generation = 0
        self._spinner_index = 0
        self._spinner_job: str | None = None
        self._busy = False
        self._build_style()
        self._build_menu()
        self._build_layout()
        self._refresh_dependencies()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._poll_solver)
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
        file_menu.add_command(label="Quit", command=self._close)
        bar.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="About model", command=self._about)
        bar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=bar)
        self.bind("<Control-o>", lambda event: self._load())
        self.bind("<Control-s>", lambda event: self._save())

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.grid(row=0, column=0, sticky="nsew")
        left = ttk.Frame(paned, width=380)
        right = ttk.Frame(paned)
        paned.add(left, weight=0)
        paned.add(right, weight=1)
        self._build_config(left)
        self._build_results(right)
        self.after_idle(lambda: paned.sashpos(0, 380))
        status = ttk.Frame(self, relief="sunken", padding=(6, 2))
        status.grid(row=1, column=0, sticky="ew")
        ttk.Label(status, textvariable=self._status, anchor="w").pack(side="left", fill="x", expand=True)
        self._busy_container = ttk.Frame(status)
        surface = ttk.Style(self).lookup("TFrame", "background") or self.cget("background")
        self._spinner_canvas = tk.Canvas(
            self._busy_container,
            width=20,
            height=20,
            background=surface,
            highlightthickness=0,
            borderwidth=0,
        )
        self._spinner_arc = self._spinner_canvas.create_arc(
            3, 3, 17, 17,
            start=90,
            extent=255,
            style="arc",
            width=2.5,
            outline="#2767a8",
        )
        self._spinner_canvas.pack(side="left", padx=(0, 4))
        ttk.Label(self._busy_container, textvariable=self._busy_text, anchor="e").pack(side="left")

    def _build_config(self, parent: ttk.Frame) -> None:
        """The input column.

        LAID OUT ON A GRID, not with packed fixed widths.  Every field row is
        three columns - label, editor, unit - and only the editor column
        stretches, so the editors line up across all groups and grow into
        whatever width the sash gives them instead of leaving a dead strip on
        the right.  Padding is deliberately tight: this panel holds twenty-odd
        rows, and a couple of pixels per row is the difference between the whole
        model fitting on screen and having to scroll to reach the heat user.
        """
        header = ttk.Frame(parent, padding=(8, 6, 8, 2))
        header.pack(fill="x")
        ttk.Label(header, text="Model inputs", font=("Segoe UI", 11, "bold")).pack(side="left")

        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        # The wheel belongs to whatever is under the pointer; binding it to the
        # canvas only would scroll the plots when the cursor is over an input.
        for widget in (canvas, body):
            widget.bind(
                "<MouseWheel>",
                lambda event: canvas.yview_scroll(-event.delta // 120, "units"),
            )

        field_map = {field.name: field for field in fields(PlantConfig)}
        for group_name, names in grouped_fields():
            group = ttk.LabelFrame(
                body, text=group_name, padding=(8, 3, 6, 5),
                style="Section.TLabelframe",
            )
            group.pack(fill="x", padx=6, pady=(0, 4))
            group.columnconfigure(1, weight=1)
            for row, name in enumerate(names):
                self._build_field(group, row, name, field_map[name])

        # Keep the action in the same scrollable/aligned input column. A
        # separate bottom bar forced the canvas wider and created the empty
        # vertical strip visible between inputs and results.
        controls = ttk.Frame(body, padding=(6, 0, 6, 6))
        controls.pack(fill="x")
        ttk.Button(controls, text="Reset defaults", command=self._reset).pack(fill="x")

    def _build_field(self, parent: ttk.Frame, row: int, name: str, field: Any) -> None:
        rule = FIELD_RULES[name]
        ttk.Label(parent, text=rule.label, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 6), pady=1
        )
        enum_type = ENUM_TYPES.get(name)
        current = self._values[name]
        sticky = "ew"
        if enum_type:
            choices = ENUM_DISPLAY.get(name, {member.value: member.value for member in enum_type})
            variable = tk.StringVar(value=choices[str(current)])
            widget = ttk.Combobox(
                parent, textvariable=variable, values=list(choices.values()),
                state="readonly", width=12,
            )
            widget.bind("<<ComboboxSelected>>", lambda event, n=name: self._changed(n))
        elif _is_bool_field(field):
            variable = tk.BooleanVar(value=bool(current))
            widget = ttk.Checkbutton(parent, variable=variable, command=lambda n=name: self._changed(n))
            sticky = "w"
        else:
            variable = tk.StringVar(value=f"{current:g}" if isinstance(current, float) else str(current))
            widget = ttk.Entry(parent, textvariable=variable, width=10)
            widget.bind("<KeyRelease>", lambda event, n=name: self._changed(n))
            widget.bind("<FocusOut>", lambda event, n=name: self._changed(n))
            widget.bind("<Return>", lambda event, n=name: self._changed(n))
        widget.grid(row=row, column=1, sticky=sticky, pady=1)
        if rule.unit:
            ttk.Label(parent, text=rule.unit, style="Muted.TLabel", anchor="w").grid(
                row=row, column=2, sticky="w", padx=(5, 0), pady=1
            )
        self._widgets[name] = widget
        self._variables[name] = variable

    def _parse_values(self) -> PlantConfig:
        data: dict[str, Any] = {}
        for field in fields(PlantConfig):
            name = field.name
            value = self._variables[name].get()
            if name in ENUM_TYPES:
                choices = ENUM_DISPLAY.get(name)
                data[name] = next((raw for raw, label in choices.items() if label == value), value) if choices else value
            elif _is_bool_field(field):
                data[name] = bool(value)
            elif name in INTEGER_FIELDS:
                data[name] = int(round(float(str(value).replace(",", "."))))
            else:
                data[name] = float(str(value).replace(",", "."))
        return PlantConfig(**data)

    def _changed(self, name: str) -> None:
        try:
            config = self._parse_values()
        except (ValueError, TypeError) as exc:
            # An in-flight answer belongs to the last valid text, not to what is
            # currently visible. Invalidate it so it cannot overwrite this error.
            self._run_generation += 1
            self._requested_run = None
            if self._pending:
                self.after_cancel(self._pending)
                self._pending = None
            self._status.set(f"Invalid input: {exc}")
            return
        self._values = config.to_dict()
        self._refresh_dependencies(config)
        self._status.set(f"Updated {FIELD_RULES[name].label}")
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(450, self._run)

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
            config = load_config(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Load failed", str(exc))
            return
        self._values = config.to_dict()
        for name, value in self._values.items():
            self._variables[name].set(ENUM_DISPLAY.get(name, {}).get(value, value))
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
            save_config(config, path)

    def _reset(self) -> None:
        config = PlantConfig()
        self._values = config.to_dict()
        for name, value in self._values.items():
            self._variables[name].set(ENUM_DISPLAY.get(name, {}).get(value, value))
        self._refresh_dependencies(config)
        self._run()

    def _build_results(self, parent: ttk.Frame) -> None:
        """KPI strip, plots, tables.

        The plots and the tables share a DRAGGABLE vertical split instead of
        each taking half the height.  Two notebooks packed with ``expand=True``
        divided the window evenly no matter what was in them, which left a
        sixteen-panel composite figure squeezed into half the height while the
        table below it showed six rows and a lot of empty grey.  The plots get
        the larger share by default and the sash lets the reader take it back.
        """
        self._build_kpis(parent)
        split = ttk.Panedwindow(parent, orient="vertical")
        split.pack(fill="both", expand=True, padx=6, pady=(2, 4))
        upper = ttk.Frame(split)
        lower = ttk.Frame(split)
        split.add(upper, weight=4)
        split.add(lower, weight=1)
        graphics = ttk.Notebook(upper)
        graphics.pack(fill="both", expand=True)
        # The P&ID goes FIRST because it is the tab that answers "what did I just
        # build?", which is the question you have before you ask "how well does it
        # perform?". It is rebuilt from scratch on every run - the topology is
        # derived from the config, so adding a compressor stage adds a compressor
        # body, an intercooler, a water branch and two tank tie-ins, all correctly
        # tagged, with no state to keep in sync.
        self._pid_ax, self._pid_canvas = self._make_figure_tab(graphics, "P&ID schematic", (11, 6.4))
        self._ts_ax, self._ts_canvas = self._make_figure_tab(graphics, "T-s cycle", (8, 4.2))
        # The h-s view exposes turbomachinery entropy generation.
        self._hs_ax, self._hs_canvas = self._make_figure_tab(graphics, "h-s (Mollier)", (8, 4.2))
        self._ph_ax, self._ph_canvas = self._make_figure_tab(graphics, "p-h cycle", (8, 4.2))
        # Energy and exergy flow Sankeys: the whole-plant books at a glance.
        self._sankey_energy_ax, self._sankey_energy_canvas = self._make_figure_tab(
            graphics, "Energy Sankey", (9, 4.6)
        )
        self._sankey_exergy_ax, self._sankey_exergy_canvas = self._make_figure_tab(
            graphics, "Exergy Sankey (Grassmann)", (9, 4.6)
        )
        # One panel per water-coupled exchanger; the grid shape follows the count.
        self._hx_figure, self._hx_canvas = self._make_multi_figure_tab(graphics, "HX composite curves", (11, 6.4))
        details = ttk.Notebook(lower)
        details.pack(fill="both", expand=True)
        self._charge_table = self._make_table(details, "Charging")
        self._discharge_table = self._make_table(details, "Discharging")
        self._summary_table = self._make_summary(details, "Efficiency & exergy")
        # Enough to read the column headings and a few rows; everything above
        # goes to the plots, and the sash moves it back if the reader wants it.
        self.after_idle(lambda: split.sashpos(0, int(self.winfo_height() * 0.62)))

    def _build_kpis(self, parent: ttk.Frame) -> None:
        strip = ttk.Frame(parent, padding=(6, 4, 6, 0))
        strip.pack(fill="x")
        self._kpis: dict[str, ttk.Label] = {}
        self._kpi_cards: dict[str, ttk.LabelFrame] = {}
        for title, key in (
            ("Electricity efficiency", "rte"),
            ("Total efficiency (heat + power)", "exergy"),
            ("Optimized mw/ma", "ratio"),
            ("Hot-coolant temp.", "hot"),
            ("Thermal surplus", "surplus"),
        ):
            card = ttk.LabelFrame(strip, text=title, padding=(8, 0, 8, 3))
            card.pack(side="left", fill="x", expand=True, padx=(0, 5))
            value = ttk.Label(card, text="—", style="KPI.TLabel")
            value.pack(anchor="w")
            self._kpi_cards[key] = card
            self._kpis[key] = value

    def _make_figure_tab(self, notebook: ttk.Notebook, title: str, size: tuple[float, float]):
        """A tab holding ONE axis. Returns (axis, canvas)."""
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        figure, axis = plt.subplots(figsize=size, dpi=100)
        canvas = FigureCanvasTkAgg(figure, master=frame)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        return axis, canvas

    def _make_multi_figure_tab(self, notebook: ttk.Notebook, title: str, size: tuple[float, float]):
        """A tab holding a WHOLE FIGURE, whose subplot grid is rebuilt on every run.

        The composite-curve tab cannot own a fixed axis: the number of panels is the
        number of exchangers, which changes when you change the stage count. So we hand
        back the figure and let :func:`caes.diagrams.draw_composites` clear it and lay
        out a fresh grid each time.
        """
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        figure = plt.figure(figsize=size, dpi=100)
        canvas = FigureCanvasTkAgg(figure, master=frame)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        return figure, canvas

    def _make_table(self, notebook: ttk.Notebook, title: str) -> ttk.Treeview:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        columns = ("kind", "p_in", "t_in", "p_out", "t_out", "work", "heat", "water", "water_out", "ex_dest")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        headings = {
            "kind": "Component", "p_in": "p in [bar]", "t_in": "T in [°C]", "p_out": "p out [bar]",
            "t_out": "T out [°C]", "work": "w [kJ/kg]", "heat": "q air [kJ/kg]",
            "water": "mcoolant/ma", "water_out": "Tcoolant out [°C]", "ex_dest": "I [kJ/kg]",
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
        """Queue the latest valid configuration without blocking Tk's event loop."""
        self._pending = None
        try:
            config = self._parse_values()
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"Invalid input: {exc}")
            return
        self._run_generation += 1
        self._requested_run = (self._run_generation, config)
        self._draw_pid(config, None)
        self._set_busy(True)
        self._status.set("Calculating latest configuration...")
        self._start_requested_run()

    def _start_requested_run(self) -> None:
        """Start only when the single worker is free; newer requests replace queued ones."""
        if self._solver_future is not None or self._requested_run is None:
            return
        self._active_run = self._requested_run
        self._requested_run = None
        _, config = self._active_run
        self._solver_future = self._executor.submit(_solve_config, config)

    def _poll_solver(self) -> None:
        """Collect completed worker results on the Tk thread and discard stale runs."""
        future = self._solver_future
        if future is not None and future.done():
            active = self._active_run
            self._solver_future = None
            self._active_run = None
            try:
                result = future.result()
                error: Exception | None = None
            except Exception as exc:  # noqa: BLE001
                result, error = None, exc

            if active is not None and active[0] == self._run_generation:
                _, config = active
                if error is not None:
                    # Never leave a valid old cycle underneath an error for a
                    # new configuration: that made stale KPIs and plots look
                    # like results for the rejected inputs.
                    self._result = None
                    for label in self._kpis.values():
                        label.configure(text="—")
                    for tree in (
                        self._charge_table,
                        self._discharge_table,
                        self._summary_table,
                    ):
                        for item in tree.get_children():
                            tree.delete(item)
                    for axis, canvas in (
                        (self._ts_ax, self._ts_canvas),
                        (self._hs_ax, self._hs_canvas),
                        (self._ph_ax, self._ph_canvas),
                        (self._sankey_energy_ax, self._sankey_energy_canvas),
                        (self._sankey_exergy_ax, self._sankey_exergy_canvas),
                    ):
                        axis.clear()
                        axis.text(
                            0.5, 0.5, "No feasible solution",
                            ha="center", va="center", transform=axis.transAxes,
                        )
                        canvas.draw_idle()
                    self._hx_figure.clear()
                    hx_axis = self._hx_figure.add_subplot(1, 1, 1)
                    hx_axis.text(
                        0.5, 0.5, "No feasible solution",
                        ha="center", va="center", transform=hx_axis.transAxes,
                    )
                    hx_axis.axis("off")
                    self._hx_canvas.draw_idle()
                    self._draw_pid(config, None)
                    self._status.set(f"Simulation error: {error}")
                else:
                    self._result = result
                    self._values = config.to_dict()
                    self._update_kpis()
                    self._draw_pid(config, result)
                    self._draw_thermodynamic_diagrams(result)
                    self._populate_tables(result)
                    self._status.set(
                        f"Complete: {plant_concept_label(result.mode, exports_heat=result.heat_offtake is not None)}, "
                        f"RTE={result.round_trip_efficiency:.2%}"
                    )

            self._start_requested_run()
            if self._solver_future is None:
                self._set_busy(False)
        self.after(100, self._poll_solver)

    def _set_busy(self, busy: bool) -> None:
        if busy:
            self._busy = True
            if not self._busy_container.winfo_manager():
                self._busy_container.pack(side="right")
            if self._spinner_job is None:
                self._advance_spinner()
        else:
            self._busy = False
            if self._spinner_job is not None:
                self.after_cancel(self._spinner_job)
                self._spinner_job = None
            self._busy_text.set("")
            self._busy_container.pack_forget()

    def _advance_spinner(self) -> None:
        """Rotate a real canvas arc; unlike a glyph it is font-independent."""
        if not self._busy:
            self._spinner_job = None
            return
        self._busy_text.set("Calculating…")
        self._spinner_canvas.itemconfigure(
            self._spinner_arc, start=90 - 30 * self._spinner_index
        )
        self._spinner_index = (self._spinner_index + 1) % 12
        self._spinner_job = self.after(70, self._advance_spinner)

    def _close(self) -> None:
        """Stop accepting queued work, then kill the worker, then destroy Tk.

        ``shutdown(wait=False)`` does not make the window close immediately: a
        solve already running cannot be cancelled, and ``concurrent.futures``
        installs an ``atexit`` hook that joins the worker at interpreter exit -
        so the app appears to hang for the rest of a solve that nobody is
        waiting for any more.  A full solve is tens of seconds.

        The worker is a real OS process (spawn context), so it can simply be
        terminated.  Python 3.13 exposes no public API for that on
        ``ProcessPoolExecutor`` - ``terminate_workers`` arrives later - so the
        private process map is used, defensively: only this executor's own
        children, only those still alive, and the executor is never reused
        afterwards because the application is going away.
        """
        self._requested_run = None
        self._executor.shutdown(wait=False, cancel_futures=True)
        for process in tuple(getattr(self._executor, "_processes", {}).values()):
            try:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=1.0)
            except (OSError, ValueError, AttributeError):
                # Already reaped, or a future Python changed the internals:
                # closing the window must never raise.
                pass
        self.destroy()

    def _draw_pid(self, config: PlantConfig, result: PlantResult | None) -> None:
        """Build the P&ID only when the solved E-303 placement is known."""
        if result is None:
            self._pid_ax.clear()
            self._pid_ax.text(
                0.5,
                0.5,
                "P&ID generated after the simulation\n(E-303 placement is result-dependent)",
                ha="center",
                va="center",
                transform=self._pid_ax.transAxes,
            )
            self._pid_ax.axis("off")
            self._pid_canvas.draw_idle()
            return
        pid.render(self._pid_ax, config, result)
        self._pid_canvas.draw_idle()

    def _update_kpis(self) -> None:
        result = self._result
        if not result:
            return
        self._kpis["rte"].configure(text=f"{result.round_trip_efficiency:.1%}")
        self._kpis["exergy"].configure(text=f"{result.useful_energy_delivery_ratio:.1%}")
        if result.thermal_store:
            self._kpi_cards["ratio"].configure(text="Optimized mw/ma")
            self._kpis["ratio"].configure(
                text=f"{result.thermal_store.total_water_mass_ratio:.3f} kg/kg"
            )
            self._kpi_cards["hot"].configure(text="Hot-coolant temp.")
            self._kpis["hot"].configure(text=f"{result.thermal_store.hot_temperature_available_k - 273.15:.1f} °C")
            if result.heat_offtake:
                self._kpi_cards["surplus"].configure(text="Heat sold to user")
                heat = result.thermal_store.offtake_heat_j_per_kg_air
            else:
                self._kpi_cards["surplus"].configure(text="Heat to turbines")
                heat = result.thermal_store.delivered_heat_j_per_kg_air
            self._kpis["surplus"].configure(text=f"{heat / 1000:.1f} kJ/kg")
        else:
            # Diabatic: show the price of fuel-free anti-icing control.
            throttle_loss = sum(
                p.exergy_destruction_j_per_kg
                for p in result.discharging.processes
                if p.kind == "throttling"
            )
            self._kpi_cards["ratio"].configure(text="Throttle destruction")
            self._kpis["ratio"].configure(text=f"{throttle_loss / 1000:.1f} kJ/kg")
            self._kpi_cards["hot"].configure(text="Ambient heat (free)")
            self._kpis["hot"].configure(text=f"{result.external_heat_input_j_per_kg / 1000:.1f} kJ/kg")
            self._kpi_cards["surplus"].configure(text="Min expander outlet")
            min_outlet = min(
                (p.outlet.temperature_c for p in result.discharging.processes if p.kind == "expansion"),
                default=float("nan"),
            )
            self._kpis["surplus"].configure(text=f"{min_outlet:.1f} °C")

    def _draw_thermodynamic_diagrams(self, result: PlantResult, fluid: str = "Air") -> None:
        """Redraw the cycle traces and the per-exchanger composite curves.

        All of it is delegated to caes.diagrams so the CLI can render exactly the same
        figures without importing tkinter.
        """
        diagrams.draw_ts(self._ts_ax, result, fluid)
        self._ts_canvas.draw_idle()

        diagrams.draw_hs(self._hs_ax, result, fluid)
        self._hs_canvas.draw_idle()

        diagrams.draw_ph(self._ph_ax, result, fluid)
        self._ph_canvas.draw_idle()

        diagrams.attach_hover(
            self._sankey_energy_canvas,
            self._sankey_energy_ax,
            diagrams.draw_energy_sankey(self._sankey_energy_ax, result),
        )
        self._sankey_energy_canvas.draw_idle()

        diagrams.attach_hover(
            self._sankey_exergy_canvas,
            self._sankey_exergy_ax,
            diagrams.draw_exergy_sankey(self._sankey_exergy_ax, result),
        )
        self._sankey_exergy_canvas.draw_idle()

        # The composite grid is rebuilt from scratch: its panel count is the exchanger
        # count, which changes whenever the stage count does.
        diagrams.draw_composites(self._hx_figure, result, fluid)
        self._hx_canvas.draw_idle()


    def _populate_tables(self, result: PlantResult) -> None:
        self._populate_processes(self._charge_table, result.charging.processes)
        self._populate_processes(self._discharge_table, result.discharging.processes)
        tree = self._summary_table
        for item in tree.get_children():
            tree.delete(item)
        # One formatter for plant output: the CLI report prints these same rows.
        for metric, value in summary_rows(result):
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
            "Normalized simulator for three CAES plant concepts:\n\n"
            "- AD-CAES (ambient diabatic): fuel-free; discharge heat comes "
            "only from the atmosphere.\n"
            f"- {LTA_LABEL}: compression heat is "
            "stored in a two-tank coolant loop and returned to the turbines.\n"
            f"- {LTAHP_LABEL}: the LTA store "
            "additionally exports heat to a district network through E-302.\n\n"
            "The study builds on published LTA-CAES research (Wolf & Budt and "
            "successors). All results are normalized per kilogram of air; no "
            "economic or time-domain model is included.",
        )


def main() -> int:
    freeze_support()
    app = CAESGUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
