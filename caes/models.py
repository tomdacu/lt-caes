"""Result data structures for the normalised energy and exergy analysis.

Everything in this module is a plain, frozen value object: the solver in
:mod:`caes.plant` builds these, and the CLI, GUI, P&ID and tests only ever read
them. Keeping them dumb is deliberate - it means a result can be pickled,
diffed, or dropped into a notebook without dragging CoolProp along.

UNITS ARE IN THE FIELD NAMES. Anything ending ``_j_per_kg`` or
``_j_per_kg_air`` is joules per kilogram of air moved through the cavern; ``_k``
is kelvin, ``_c`` celsius, ``_pa`` pascal. There is no time domain, so there are
no rates anywhere - do not add a field called ``power``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class State:
    """A thermodynamic state point of the air. Fully determined by any two of these."""

    pressure_pa: float
    temperature_k: float
    enthalpy_j_per_kg: float
    entropy_j_per_kgk: float

    @property
    def pressure_bar(self) -> float:
        return self.pressure_pa / 1e5

    @property
    def temperature_c(self) -> float:
        return self.temperature_k - 273.15


@dataclass(frozen=True)
class HeatExchangerPerformance:
    """The solved water side of one finite counter-current air/water HX."""

    effectiveness: float
    ntu: float
    water_air_mass_ratio: float          # r = m_water / m_air for THIS exchanger
    water_inlet_temperature_k: float
    water_outlet_temperature_k: float
    duty_j_per_kg_air: float             # always >= 0; the direction is in Process.heat_to_air_j_per_kg


@dataclass(frozen=True)
class Process:
    """One component: air enters at ``inlet``, leaves at ``outlet``.

    ``work_j_per_kg`` and ``heat_to_air_j_per_kg`` follow the air-centric sign
    convention documented at the top of :mod:`caes.thermodynamics`:
    positive means "into the air".
    """

    kind: str                            # compression | intercooling | aftercooling | interheating | expansion | throttling | interheater_pressure_drop
    inlet: State
    outlet: State
    work_j_per_kg: float = 0.0
    heat_to_air_j_per_kg: float = 0.0
    exergy_destruction_j_per_kg: float = 0.0
    heat_exchanger: HeatExchangerPerformance | None = None

    @property
    def first_law_residual_j_per_kg(self) -> float:
        """Closure error of the steady-flow energy equation h_out - h_in = q + w.

        This is a self-check, not a physical quantity: it must be zero to machine
        precision for every component. If it drifts, a component model has an
        inconsistency between the state it reports and the q/w it claims - which
        is exactly the class of bug that silently inflates round-trip efficiency.
        The tests assert on it; please keep them.
        """
        return (self.outlet.enthalpy_j_per_kg - self.inlet.enthalpy_j_per_kg) - (
            self.heat_to_air_j_per_kg + self.work_j_per_kg
        )


@dataclass
class Cycle:
    """An ordered chain of processes - either the charging train or the discharging train."""

    name: str
    inlet: State
    processes: list[Process] = field(default_factory=list)

    @property
    def outlet(self) -> State:
        return self.processes[-1].outlet if self.processes else self.inlet

    @property
    def states(self) -> list[State]:
        """Every state point, in flow order. This is what the T-s / p-h plots trace."""
        return [self.inlet, *(process.outlet for process in self.processes)]

    @property
    def work_j_per_kg(self) -> float:
        """Net work into the air. Positive for charging, negative for discharging."""
        return sum(process.work_j_per_kg for process in self.processes)

@dataclass(frozen=True)
class TwoTankSummary:
    """State of the two-tank sensible-water thermal store over one charge/discharge.

    Energy bookkeeping the plant guarantees (asserted in the tests):

        recovered + cold_return_heat_absorbed_from_ambient
              = delivered + offtake_heat
              + storage_loss + cold_storage_loss                  (12)

    There is deliberately no ambient rejection path:
    with no heat user the complete hot-tank stream reaches the interheaters,
    and with district heating E-302 exports exactly the upstream surplus, so
    any residual rejection would require an extra cooler the topology does not
    have. E-303 is instead a heat-only ambient recovery exchanger. The solver
    places that single body on the contiguous suffix of cold interheater
    returns that maximises ambient heat pickup, then mixes its outlet with the
    warmer bypass returns before the cold tank.

    The cold-tank standing loss is genuinely signed, and stays that way: it is
    negative when the cold tank sits below ambient and leaks heat in.
    """

    cold_temperature_k: float
    hot_temperature_before_loss_k: float   # mixed-mean of the intercooler branches
    hot_temperature_available_k: float     # after standing losses; what the hot tank actually offers
    returned_temperature_k: float          # untreated mixed-mean of ALL returns
    total_water_mass_ratio: float          # sum of r over all charging exchangers
    recovered_heat_j_per_kg_air: float
    delivered_heat_j_per_kg_air: float     # to the AIR, in the interheaters
    offtake_heat_j_per_kg_air: float      # to the NETWORK, in the DH exchanger
    storage_loss_j_per_kg_air: float
    storage_duration_hours: float
    thermal_storage_tank_ua_w_per_k: float # normalized UA on the 1 kg-air basis
    # Compatibility field: the heat-only architecture can never reject here.
    cold_return_heat_rejected_to_ambient_j_per_kg_air: float = 0.0
    cold_return_heat_absorbed_from_ambient_j_per_kg_air: float = 0.0
    # Destruction either way: water exergy is convex about the dead state, so
    # both directions move the stream toward its minimum.
    cold_return_exergy_destruction_j_per_kg_air: float = 0.0
    cold_storage_loss_j_per_kg_air: float = 0.0  # signed standing loss of the cold tank
    cold_return_exchanger_ntu: float = 0.0
    # Final mixed cold-tank inlet, after the selected E-303 subgroup rejoins
    # the warmer bypass branches.
    cold_return_exchanger_outlet_temperature_k: float = 0.0
    cold_return_recovery_start_stage: int | None = None  # zero-based stage index
    cold_return_recovery_branch_count: int = 0
    cold_return_recovery_inlet_temperature_k: float = 0.0
    cold_return_recovery_outlet_temperature_k: float = 0.0
    # Mixed coolant return AFTER E-303 and the final remix, but BEFORE the
    # E-304 recuperation. This is what the extraction body sees on its cold
    # side; ``cold_return_exchanger_outlet_temperature_k`` above stays the
    # final cold-tank inlet, so the two differ by exactly the recuperated duty.
    # Without a heat user there is no E-304 and the two are equal.
    recuperator_inlet_temperature_k: float = 0.0
    extraction_recuperated_heat_j_per_kg_air: float = 0.0
    cold_loop_closure_error_k: float = 0.0
    coolant_maximum_temperature_k: float = 0.0
    coolant_maximum_temperature_reached_k: float = 0.0
    coolant_minimum_temperature_k: float = 273.15
    coolant_minimum_temperature_reached_k: float = 273.15
    # The physical hot store.  The current architecture always reports one
    # entry: intercooler returns mix before storage.  The tuple shape is kept
    # for result-file compatibility, not as a cascade-control surface.
    hot_level_temperatures_k: tuple[float, ...] = ()
    hot_level_water_mass_ratios: tuple[float, ...] = ()


@dataclass(frozen=True)
class OfftakeTap:
    """The heat-user exchanger E-302. There is exactly one.

    The whole conserved inventory leaves the hot store, crosses this single
    counter-current body, and only then reaches E-304 to be extracted stage by
    stage. So ``plant_water_per_kg_air`` is always the plant inventory and
    ``plant_inlet_temperature_k`` is always the available hot-store temperature.
    """

    plant_inlet_temperature_k: float        # trunk temperature entering
    plant_outlet_temperature_k: float       # trunk temperature leaving
    plant_water_per_kg_air: float           # trunk flow, the whole inventory
    user_inlet_temperature_k: float         # user water entering
    user_outlet_temperature_k: float        # user water leaving
    user_water_per_kg_air: float            # the ONE user stream, from (17)
    heat_j_per_kg_air: float                # duty handed to the user, eq. (20)
    required_effectiveness: float = 0.0
    available_effectiveness: float = 0.0


@dataclass(frozen=True)
class ExtractionSegment:
    """One zone of E-304, between two consecutive trunk extractions.

    The trunk loses mass at every extraction, so its heat-capacity rate is a
    STEP FUNCTION of position and a single whole-body LMTD or epsilon-NTU is
    invalid. The body is therefore solved zone by zone: inside one zone both
    capacity rates are constant, which is exactly the condition the ordinary
    counter-current effectiveness relation needs.

    ``trunk_flow_per_kg_air`` is the flow crossing THIS zone - the suffix sum of
    the extractions still downstream - never the plant inventory. The cold side
    carries the whole inventory through every zone, so the trunk is always the
    C_min stream and ``capacity_ratio`` is at most one.

    Both terminal differences are reported because with a variable trunk
    capacity rate the pinch migrates to an internal node; checking only the two
    ends of the body would miss it.
    """

    index: int                              # 0 is the HOTTEST zone
    trunk_flow_per_kg_air: float            # kg-coolant/kg-air crossing this zone
    trunk_inlet_temperature_k: float        # trunk entering, at the hot end
    trunk_outlet_temperature_k: float       # trunk leaving, at the cold end
    return_inlet_temperature_k: float       # cold side entering, at the cold end
    return_outlet_temperature_k: float      # cold side leaving, at the hot end
    duty_j_per_kg_air: float
    capacity_ratio: float                   # C_min/C_max = trunk flow / inventory
    required_effectiveness: float = 0.0
    available_effectiveness: float = 0.0

    @property
    def hot_end_terminal_difference_k(self) -> float:
        return self.trunk_inlet_temperature_k - self.return_outlet_temperature_k

    @property
    def cold_end_terminal_difference_k(self) -> float:
        return self.trunk_outlet_temperature_k - self.return_inlet_temperature_k

    @property
    def terminal_difference_k(self) -> float:
        """Tighter of the two ends: the zone's own approach."""
        return min(
            self.hot_end_terminal_difference_k,
            self.cold_end_terminal_difference_k,
        )


@dataclass(frozen=True)
class ExtractionExchangerSummary:
    """E-304: one counter-current body with staged extractions on the trunk.

    The trunk enters at the first extraction temperature, is progressively
    withdrawn to feed each interheater, and is fully consumed at the last
    extraction. Its cold side is the plant's own coolant return, so every joule
    the trunk gives up here is INTERNAL recuperation: it is not a product, it is
    not an ambient input, and it must never be booked as either. What it buys is
    grade - the heat user upstream keeps the whole hot end of the store to
    itself, and each interheater is fed at the temperature it actually needs
    instead of at one common tank temperature.

    ``margin_k`` is the single solved unknown of the discharge network: every
    extraction sits that many kelvin above the air temperature its own stage
    must reach, and the margin is rooted so the extractions consume exactly the
    conserved coolant inventory.

    Energy identity the plant guarantees (asserted in the tests):

        recuperated_heat = sum(segment duties)
                         = inventory * cp * (return_outlet - return_inlet)
    """

    margin_k: float                          # common approach above each stage demand
    exchanger_ntu: float
    trunk_inlet_temperature_k: float         # = hottest extraction
    trunk_outlet_temperature_k: float        # = coldest extraction
    return_inlet_temperature_k: float        # mixed coolant return entering
    return_outlet_temperature_k: float       # what reaches the cold tank
    total_water_mass_ratio: float            # inventory, the cold-side flow
    recuperated_heat_j_per_kg_air: float
    extraction_temperatures_k: tuple[float, ...] = ()   # one per expansion stage
    extraction_mass_ratios: tuple[float, ...] = ()      # one per expansion stage
    segments: tuple[ExtractionSegment, ...] = ()
    minimum_terminal_difference_k: float = 0.0
    maximum_required_effectiveness: float = 0.0
    minimum_effectiveness_margin: float = 0.0
    exergy_destruction_j_per_kg_air: float = 0.0


@dataclass(frozen=True)
class HeatOfftakeSummary:
    """Heat sold to an EXTERNAL USER through the one user exchanger E-302.

    The user is described by the temperatures it wants and hands back plus the
    exchanger NTU class, so this is equally a
    district-heating network, an industrial process loop, an absorption chiller
    or a dryer. District heating is the likely application, not the subject.

    The whole conserved trunk crosses E-302, which cools it from the available
    hot-store temperature down to the FIRST extraction. What E-304 takes below
    that is recuperated inside the plant rather than sold, so the user is
    served entirely from the hot end of the store.
    """

    mode: str
    hot_tank_temperature_k: float           # trunk temperature entering E-302
    turbine_supply_temperature_k: float     # hottest temperature reaching the turbines
    supply_temperature_k: float             # requested supply; infeasible HX matches raise
    return_temperature_k: float             # what the user gives back
    heat_j_per_kg_air: float                # total duty handed to the user, eq. (20)
    exergy_j_per_kg_air: float              # exergy the user RECEIVES - this is the product
    network_water_per_kg_air: float         # the ONE user flow, from (17)
    taps: tuple[OfftakeTap, ...] = ()       # the one E-302 tap
    heat_exchanger_ntu: float = 0.0
    maximum_required_effectiveness: float = 0.0
    minimum_effectiveness_margin: float = 0.0


@dataclass(frozen=True)
class ExergySummary:
    """Grassmann balance for the cycle, per kg of air. See equation (6) in caes.exergy.

    The invariant that makes this trustworthy:

        compression work
          = expansion work + useful heat exergy      <- products
          + sum(component_destruction)               <- irreversibility
          + sum(losses)                              <- exergy that left unused
          + balance_residual                         <- must be ~0

    ``balance_residual_j_per_kg_air`` is the honesty check. If it grows beyond a
    few J/kg, a term has gone missing and the efficiencies above it are lies.

    Heat rejected to the ambient dead state is DESTRUCTION, not loss: it still
    carried exergy when it crossed the boundary, but the receiver (the
    atmosphere) is the dead state itself, so nothing usable leaves the plant.
    Losses are reserved for streams that leave intact (the exhaust air).
    """

    total_useful_exergy_efficiency: float      # (W_exp + district-heat exergy) / W_comp
    hot_water_exergy_j_per_kg_air: float       # exergy the hot tank offers the discharge, after standing losses
    useful_heat_exergy_j_per_kg_air: float     # PRODUCT: exergy the DH network receives (0 if no offtake)
    component_destruction_j_per_kg_air: dict[str, float]   # DESTRUCTION, by component kind
    loss_j_per_kg_air: dict[str, float]        # LOSS, e.g. exhaust air
    total_destruction_j_per_kg_air: float
    total_loss_j_per_kg_air: float
    balance_residual_j_per_kg_air: float


@dataclass(frozen=True)
class OptimizationSummary:
    """Outcome of the coupled thermal-store design optimization."""

    objective: str
    objective_value: float
    evaluated_points: int
    max_hx_temperature_spread_k: float       # worst endpoint variation of DeltaT over all water HXs


@dataclass(frozen=True)
class MoistureSummary:
    """Vapour and condensate balance through the calculated charge train.

    Every charging intercooler and the final aftercooler are treated as a cooler
    followed by an ideal liquid separator.

    ``stored_air_water_vapor_kg_per_kg_dry_air`` is the ratio leaving the LAST
    charge-side cooler/separator, so it is simultaneously the cavern inventory
    and the protected basis the wet-expander envelope is evaluated against.
    There used to be a second field for "after the charge coolers"; the two were
    provably identical for every train, which invited call sites to pick one at
    random as though they differed. One name, one meaning.

    The balance the tests assert:

        inlet = surface_separator + stored_air
    """

    ambient_relative_humidity: float
    inlet_water_vapor_kg_per_kg_dry_air: float
    stored_air_water_vapor_kg_per_kg_dry_air: float
    surface_separator_water_kg_per_kg_dry_air: float
    storage_pressure_pa: float


@dataclass
class PlantResult:
    charging: Cycle
    discharging: Cycle
    thermal_store: TwoTankSummary
    exergy: ExergySummary
    heat_offtake: HeatOfftakeSummary | None = None   # None for LTA: no heat user is installed
    # E-304. Present exactly when a heat user is dispatched: without one there
    # is no trunk to stage, because the only sink for the descent would be the
    # plant's own cold return and warming it buys nothing.
    extraction_exchanger: ExtractionExchangerSummary | None = None
    optimization: OptimizationSummary | None = None
    external_heat_input_j_per_kg: float = 0.0  # E-303 ambient recovery; zero-exergy at the selected dead state
    moisture: MoistureSummary | None = None        # diagnostic only; dry-air energy balance is unchanged

    @property
    def compression_work_input_j_per_kg(self) -> float:
        return self.charging.work_j_per_kg

    @property
    def expansion_work_output_j_per_kg(self) -> float:
        # Discharging work is negative under the air-centric sign convention;
        # flip it once, here, so that everything downstream sees a positive output.
        return -self.discharging.work_j_per_kg

    @property
    def round_trip_efficiency(self) -> float:
        """Shaft-to-shaft electrical round trip: work out over work in.

        NOT a grid-to-grid figure - motor, gearbox, generator and auxiliary loads
        (notably the water pumps) are outside the model, so expect the real plant
        to land several points lower.
        """
        return self.expansion_work_output_j_per_kg / self.compression_work_input_j_per_kg

    @property
    def useful_energy_delivery_ratio(self) -> float:
        """THE energy metric: useful output over what the plant PAYS FOR.

            R_delivery = (W_exp + Q_DH) / W_comp

        The denominator is charging electricity and nothing else. Every ambient
        energy stream the plant harvests is free, so none of it is a cost and
        none of it belongs here:

          * the heat-only E-303 coolant recovery into the returning coolant
            (reported as ``external_heat_input_j_per_kg``), and
          * the energy the air stream itself hands over when the exhaust leaves
            below intake enthalpy - intake and exhaust are both at p0 and the
            intake is at T0, so that is ``h(T0, p0) - h_exhaust``, worth up to
            ~49 kJ/kg-air over the supplied configurations.

        Both are reported as flows; neither is charged to the plant. There used
        to be a second "first-law" ratio that put the first of those two into
        the denominator while still ignoring the second. It was an inconsistent
        half-measure - it priced one free stream and not the other - so it is
        gone. One energy metric, one meaning.

        Consequently this ratio is NOT bounded by one, for the same reason a
        heat-pump COP is not: the plant draws low-temperature, high-entropy heat
        out of the atmosphere and converts part of it into useful output. That
        is a result, not an error, and it is deliberately not called an
        efficiency.

        Where to look for the other two questions:

          * the CLOSED first-law boundary balance, with every free stream drawn
            explicitly, is :func:`caes.diagrams.draw_energy_sankey`;
          * the bounded, thermodynamically complete figure is the exergy
            efficiency, where the cold exhaust is booked as ``exhaust_air``
            loss and ambient heat correctly carries ~zero exergy at T0.
        """
        offtake_heat = (
            self.heat_offtake.heat_j_per_kg_air
            if self.heat_offtake is not None
            else 0.0
        )
        return (
            self.expansion_work_output_j_per_kg + offtake_heat
        ) / self.compression_work_input_j_per_kg
