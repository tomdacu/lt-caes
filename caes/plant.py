"""Normalized AD-CAES and two-tank coolant LTA/LTHP-CAES cycle solver.

The adiabatic model is a *closed coolant cycle*. It solves these physical
constraints together:

1. every intercooler branch starts at the common cold-tank temperature and is
   given its own stage-specific flow; the real coolant returns then mix to the
   hot-tank temperature;
2. the same total coolant inventory is divided among the interheaters, one bleed
   per expansion stage, each sized by that stage's own duty;
3. every wet-rated expander outlet stays above the common anti-icing envelope:
   10 degC while liquid condensation is possible, otherwise the local frost
   point plus 10 K;
4. one heat-only E-303 is placed on the contiguous cold suffix of interheater
   returns that maximises ambient heat pickup; that warmed subgroup then mixes
   with the bypass returns before the cold tank;
5. the configured direct coolant maximum limits every hot state without a
   pressure or saturation correlation;
6. the configured direct coolant minimum limits the cold tank and every
   physical return;
7. with a heat user, the whole mixed hot-store trunk crosses ONE user exchanger
   (E-302) and then enters ONE counter-current extraction body (E-304), where it
   is withdrawn stage by stage to feed the interheaters and is fully consumed at
   the last extraction. E-304's cold side is the plant's own coolant return, so
   the trunk's descent below the user is recuperated internally instead of being
   sold. Without a heat user neither body exists and the complete hot-store
   stream is optimized for turbine work.

Those seven statements are the logic map of the solver. The detailed workflow
and Mermaid concept maps live in ``docs/04_OPTIMIZATION_WORKFLOW.md``.

WHY THE TRUNK IS STAGED AT ALL
------------------------------
Each expansion stage must reach its own air temperature before its turbine, and
those demands fall steeply along the train.  Feeding every interheater from one
tank temperature therefore wastes grade on the tail stages - measured at 44 K of
excess on the last stage of the six-stage reference plant, against 1.7 K on the
first.  E-304 gives each stage a supply a common margin above its own demand and
recuperates the difference into the return.  That margin is the single unknown
of the discharge network; see :meth:`CAESPlant._solve_extraction_margin`.

WHAT THE SEARCH VARIABLE IS, AND WHY
------------------------------------
The coolant loop is closed on the cold-tank temperature. Branch-selective
ambient recovery cannot be reconstructed from the raw mixed return: the branch
distribution is part of the state. Each trial therefore builds the actual
returns, optimises E-303 analytically, applies cold-tank standing, and closes
the resulting tank temperature against the trial.

WHAT THE ADIABATIC TRAIN DOES *NOT* DO
--------------------------------------
It scavenges no ambient heat.  Every joule the turbines receive comes from the
coolant loop.  The AH-20x ambient preheaters that used to sit ahead of each coolant
interheater in the district-heating concept have been removed: they were up to
eight extra high-pressure gas/ambient exchangers with their fans and controls,
and they were modelled with zero air-side pressure drop while every other
exchanger in the train paid one.  Ambient reheat remains in AD-CAES
(:meth:`CAESPlant._simulate_diabatic`), where it is the only heat source there
is.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import lru_cache
from math import exp

from .config import HeatOfftake, OptimizationObjective, PlantConfig, PlantMode
from .constants import MINIMUM_FROST_CORRELATION_TEMPERATURE_K
from .exergy import air_exergy, process_exergy_destruction, water_exergy
from .heat_exchangers import (
    WATER_CP_J_PER_KGK,
    counterflow_effectiveness,
    cool_air_with_water,
    exchange_air_with_ambient_ntu,
    heat_air_with_water,
    water_ratio_for_duty,
)
from .models import (
    Cycle,
    OfftakeTap,
    HeatOfftakeSummary,
    ExergySummary,
    ExtractionExchangerSummary,
    ExtractionSegment,
    MoistureSummary,
    OptimizationSummary,
    PlantResult,
    Process,
    TwoTankSummary,
)
from .moisture import analyze_charge_moisture, inlet_humidity_ratio, saturation_humidity_ratio
from .numerics import (
    SearchUnresolved, affine_fixed_point, bisect, bracketed_root, illinois_residuals,
    sampled_roots, simplex_feasible, trial_point,
)
from .thermal_limits import (
    TEMPERATURE_LIMIT_TOLERANCE_K,
    dry_air_wet_expansion_approximation_ok,
    minimum_wet_expander_temperature_k,
    reference_wet_expander_liquid_envelope_ok,
    wet_expander_hard_floor_temperature_k,
)
from .thermodynamics import (
    BOTH_WAYS,
    COOL_ONLY,
    HEAT_ONLY,
    PropertyAPI,
    compress,
    exchange_with_environment,
    expand,
    state_ph,
    state_pt,
    throttle,
    using_property_api,
)


WORKING_FLUID = "Air"

# Numerical search limits, not plant inputs.  The branch bound is intentionally
# generous; normal solutions are around 0.1-1.0 kg-water/kg-air per branch.
MAX_BRANCH_WATER_AIR_RATIO = 30.0
INVENTORY_MIN = 0.1
INVENTORY_MAX = 30.0

# Coolant-loop search window around the ambient temperature [K].  The lower end is
# additionally kept a named safety margin above the frost-correlation domain
# limit (see caes.constants), so every trial point stays where the moisture
# correlations are valid.
COLD_LOOP_SEARCH_BELOW_AMBIENT_K = 100.0
COLD_LOOP_SEARCH_ABOVE_AMBIENT_K = 180.0
COLD_LOOP_CORRELATION_MARGIN_K = 5.0
# Coarse walk of the search coordinate before any root is bracketed [K].
COLD_LOOP_SCAN_STEP_K = 2.0
# Continuation of the root between neighbouring inventories: probe outward from
# the previous root instead of rescanning the whole window.  The root moves
# roughly 43 K per unit RELATIVE change in inventory in the measured designs, so
# the probe span is scaled by that change rather than fixed; beyond the cap the
# full walk is cheaper than more speculative probing.
COLD_LOOP_CONTINUATION_SENSITIVITY_K = 45.0
COLD_LOOP_CONTINUATION_MIN_SPAN_K = 4.0
COLD_LOOP_CONTINUATION_MAX_SPAN_K = 40.0
# The legacy fast walk assumes one feasible interval and abandons it after
# these consecutive failures. This is a work-saving heuristic, NOT a proof:
# nested allocation/dispatch and finite-area constraints can split the domain.
# The separate recovery search does not stop after leaving the first island.
COLD_LOOP_ABANDON_AFTER_LEAVING = 3

# Charge-side coolant allocation.  The capacity-matched split is a fixed point in
# the branch flows; it is iterated to a tolerance, not to a fixed count, because
# an under-converged split can read as violating the coolant maximum and hand
# the design to the far more expensive relief allocation.
CHARGE_FIXED_POINT_TOLERANCE = 2e-6
CHARGE_FIXED_POINT_MAX_ITERATIONS = 20
# The update contracts in every measured case; a change that stops shrinking by
# at least this factor means it will not converge and further work is wasted.
CHARGE_FIXED_POINT_STAGNATION = 0.99
CHARGE_RELIEF_ITERATIONS = 10
# Relief blend: coarse first-feasible scan (the peak temperature is monotone
# along the segment in every measured case, but that is not guaranteed) followed
# by bisection inside the bracketing interval.  Paid only when the ceiling binds.
CASCADE_ROOT_REFINEMENTS = 18
CASCADE_FEASIBILITY_BISECTIONS = 12
CHARGE_BLEND_COARSE_STEPS = 4
CHARGE_BLEND_BISECTIONS = 12
# Acceptance on the closed loop: the mixed return the assembled cycle produces
# must be the one its charge train was built from.  Applied on the RETURN, which
# E-303 and the tank standing period both CONTRACT toward ambient, so
# the implied tolerance on the cold tank itself is never looser than this.
COLD_LOOP_RETURN_CLOSURE_K = 5e-4
# Numerical root target is tighter than physical acceptance because the K=1
# analytic construction expresses exact mass closure through an equivalent
# return-temperature residual before the materialized energy book is checked.
COLD_LOOP_ROOT_RESIDUAL_K = 1e-7

# Water-mass closure budget.  A residual ``dr`` in ``sum(r_interheater) - r_total``
# does not stay a mass error: the water energy balance books the interheater
# duties against the real branch flows but the tank terms against ``r_total``, so
# ``dr`` reappears as roughly ``dr * cp_water * T_x`` of spurious heat.  Both the
# root search and the final acceptance are therefore derived from ONE energy
# budget instead of from independent ad-hoc numbers, so neither can silently
# admit more error than the ~1 J/kg-air the energy and exergy books are asserted
# against.  The reference supply temperature is a deliberately generous bound on
# T_x for this model.
WATER_MASS_CLOSURE_REFERENCE_SUPPLY_K = 500.0
# Target for the bisection: half a joule per kilogram of air.
WATER_MASS_CLOSURE_SEARCH_ERROR = 0.5 / (
    WATER_CP_J_PER_KGK * WATER_MASS_CLOSURE_REFERENCE_SUPPLY_K
)
# Acceptance for the assembled design.  Twice the search target, so a root that
# stopped on iteration count rather than on tolerance still lands inside the
# one-joule budget instead of the ~30 J/kg a plain relative tolerance allowed.
MAX_WATER_MASS_CLOSURE_ERROR = 2.0 * WATER_MASS_CLOSURE_SEARCH_ERROR

class HeatOfftakeTemperatureError(ValueError):
    """The requested DH temperatures cannot match the plant-coolant profile."""


def _hx_profile_spread(result: PlantResult) -> float:
    """Worst endpoint T-Q non-parallelism over every air/water HX [K].

    Full plotted curves retain small curvature from variable air cp.  The
    endpoint difference is the inexpensive exact measure needed inside the
    optimiser and is zero for equal secant heat-capacity rates.
    """
    spreads: list[float] = []
    for cycle in (result.charging, result.discharging):
        for process in cycle.processes:
            hx = process.heat_exchanger
            if hx is None:
                continue
            if process.kind == "intercooling":
                first = process.inlet.temperature_k - hx.water_outlet_temperature_k
                last = process.outlet.temperature_k - hx.water_inlet_temperature_k
            else:
                first = hx.water_outlet_temperature_k - process.inlet.temperature_k
                last = hx.water_inlet_temperature_k - process.outlet.temperature_k
            spreads.append(abs(last - first))
    return max(spreads, default=float("inf"))


@dataclass(frozen=True)
class _ThermalStore:
    """Internal store state passed between the charge and discharge solvers.

    One mixed hot store: all parallel intercooler returns mix before the
    standing period, so the store owns one mass and one temperature.
    """

    total_ratio: float
    cold_k: float
    hot_before_loss_k: float
    hot_available_k: float
    storage_loss_j_per_kg_air: float
    charge_returns: tuple[tuple[float, float, float], ...]
    protected_humidity_ratio: float
    maximum_water_temperature_reached_k: float
    # Filled only for the final, validated charge train; provisional iterates
    # skip the moisture analysis entirely (see _charge_with_ratios).
    moisture: MoistureSummary | None = None


@dataclass(frozen=True)
class _DischargeDesign:
    """The result of sizing all parallel interheater branches together."""

    cycle: Cycle
    returns: tuple[tuple[float, float, float], ...]
    supply_k: float                  # hottest supply any stage sees
    returned_mean_k: float
    # Post-user temperature at which each STAGE group is bled, in train order.
    stage_supplies: tuple[float, ...] = ()


@dataclass(frozen=True)
class _DischargeRequirement:
    """Invariant minimum-duty air trajectory for one LTHP expansion stage.

    ``heater_outlet_temperature_k`` is the air temperature this stage's
    interheater must produce for the following expander to land exactly on its
    anti-icing envelope.  It is the DEMAND that E-304's extraction ladder is
    matched to, and like the duty and the outlet pressure it depends only on the
    pressure train and the protected humidity, never on either tank temperature.
    """

    turbine_pressure_pa: float
    duty_j_per_kg_air: float
    heater_outlet_temperature_k: float = 0.0


@dataclass(frozen=True)
class _LadderEvaluation:
    """Coolant extraction-ladder result used while roots are still being refined."""

    required_ratio: float
    returns: tuple[tuple[float, float, float], ...]
    supplies: tuple[float, ...]
    returned_mean_k: float


@dataclass(frozen=True)
class _ColdReturnRecovery:
    """Optimal placement and state of the single heat-only E-303."""

    start_stage: int | None
    branch_count: int
    mass_ratio: float
    inlet_k: float
    outlet_k: float
    mixed_tank_inlet_k: float
    heat_absorbed_j_per_kg_air: float


class CAESPlant:
    """Simulate one charge/discharge cycle, normalized to one kilogram of air."""

    def __init__(
        self,
        config: PlantConfig,
        property_api: PropertyAPI | str = PropertyAPI.ABSTRACT_STATE,
    ):
        self.config = config
        self.property_api = PropertyAPI(property_api)
        # Keep already accepted designs on the historical fast path. Recovery
        # is deterministic and does not require any continuation seed.
        self._preserve_search_path = False
        self._recovering = False
        self._duty_relative_tolerance = 1e-6
        # Warm-start seed for the charge-side capacity-matching fixed point:
        # the last converged branch split and its cold-tank temperature.
        self._charge_seed: tuple[float, list[float]] | None = None
        # Continuation seed for the coolant-loop closure: the inventory of the
        # last accepted root and the mixed return it closed on.
        self._cold_loop_seed: tuple[float, float] | None = None
        # Continuation seed for the E-304 extraction margin.  Stored as a
        # fraction of the currently admissible margin span so it remains useful
        # while inventory and hot-store temperature move in the outer searches.
        self._extraction_margin_fraction_seed: float | None = None
        # Per-stage duty targets keyed by protected humidity ratio.  Held on the
        # instance so the plant can be collected when it goes out of scope.
        self._requirements_cache: dict[
            float, tuple[_DischargeRequirement, ...]
        ] = {}

    @property
    def _p_ambient(self) -> float:
        return self.config.ambient_pressure_bar * 1e5

    @property
    def _p_storage(self) -> float:
        return self.config.storage_pressure_bar * 1e5

    def _absorbs_surplus(self) -> bool:
        """Electricity-first dispatch: use all high-grade heat in the turbines.

        Both E-302 and E-304 are absent in LTA-CAES and bypassed in
        electricity-first LTHP-CAES. In both cases every kilogram from the hot
        tank goes directly to an interheater branch, at the one stored
        temperature.

        There is no point staging the trunk without a buyer for the top of it:
        the only sink for the descent would be the plant's own coolant return,
        so E-304 would warm the cold tank, capture less compression heat and
        raise compressor work in exchange for nothing sellable.

        Combined-delivery LTHP instead keeps the minimum moisture-safe turbine
        duty, so E-302 can export the band above the first extraction while
        E-304 feeds each stage a supply matched to its own demand.
        """
        c = self.config
        return (
            c.mode is PlantMode.ADIABATIC
            and not self._dispatches_heat_to_user()
        )

    def _dispatches_heat_to_user(self) -> bool:
        """Whether this solve routes coolant through E-302 and E-304.

        The two stand or fall together: E-304 exists to let the user keep the
        hot end of the store, and without a user there is nothing for it to do.

        ``heat_offtake`` describes installed/selected LTHP hardware; the
        objective selects its dispatch.  Electricity-first operation bypasses
        that hardware instead of imposing a small, unwanted heat sale before
        ranking inventory candidates by electrical RTE.
        """
        c = self.config
        return (
            c.mode is PlantMode.ADIABATIC
            and c.heat_offtake is HeatOfftake.HEAT_USER
            and c.optimization_objective
            is OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY
        )

    def run(self) -> PlantResult:
        """Return an isolated copy because cached value objects must not be shared."""
        return deepcopy(_solve_cached(self.config, self.property_api))

    # ---------------------------------------------------------------- optimization

    def _objective(self, result: PlantResult) -> float:
        """Value of one design under the selected objective. Larger is better.

        Shared by the inventory search and the coolant-loop root selection, so a
        design can never be ranked by two different rules depending on which
        loop happened to compare it.
        """
        if (
            self.config.optimization_objective
            is OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY
        ):
            return result.useful_energy_delivery_ratio
        return result.round_trip_efficiency

    def _run_uncached(self) -> PlantResult:
        self._preserve_search_path = True
        try:
            result = self._run_fast_search()
        except ValueError as original:
            self._preserve_search_path = False
            if self.config.mode is PlantMode.DIABATIC:
                raise
            # This necessary inequality really does exclude every passive
            # heat-user design; a sampled failure elsewhere does not.
            if (self._dispatches_heat_to_user() and
                    self.config.heat_user_supply_temperature_k >=
                    self.config.coolant_maximum_temperature_k):
                raise
            result = self._recover_inventory_search(original)
        finally:
            self._preserve_search_path = False
        return self._polish_wet_result(result)

    def _polish_wet_result(self, result: PlantResult) -> PlantResult:
        """Repair inverse-HX numerical error, never relax the wet envelope."""
        if result.moisture is None:
            return result
        humidity = result.moisture.stored_air_water_vapor_kg_per_kg_dry_air
        safe = all(
            p.outlet.temperature_k >= minimum_wet_expander_temperature_k(
                p.outlet.pressure_pa, humidity
            ) - TEMPERATURE_LIMIT_TOLERANCE_K
            for p in result.discharging.processes if p.kind == "expansion"
        )
        if safe:
            return result
        if result.thermal_store is None or self._duty_relative_tolerance < 1e-6:
            raise ValueError("materialized train violates the wet-expander lower envelope")
        self._duty_relative_tolerance = 1e-9
        store = result.thermal_store
        # Preserve the accepted charge allocation. Reoptimizing it can jump
        # between relief blends at an active coolant ceiling, much farther
        # than the inverse-HX error being repaired. First refine only discharge
        # and require the ORIGINAL cold-loop acceptance tolerance afterwards.
        ratios = [p.heat_exchanger.water_air_mass_ratio
                  for p in result.charging.processes
                  if p.kind == "intercooling" and p.heat_exchanger is not None]
        polished = None
        try:
            charging, internal_store = self._charge_with_ratios(store.cold_temperature_k, ratios)
            discharge = self._discharge_adiabatic(internal_store, store.cold_temperature_k)
            candidate = self._assemble_adiabatic(charging, internal_store, discharge)
            if abs(candidate.thermal_store.cold_loop_closure_error_k) <= COLD_LOOP_RETURN_CLOSURE_K:
                polished = self._polish_wet_result(candidate)
        except ValueError:
            pass
        if polished is None:
            self._cold_loop_seed = (store.total_water_mass_ratio, store.cold_temperature_k)
            polished = self._close_cold_loop(store.total_water_mass_ratio)
        if result.optimization is not None:
            polished.optimization = replace(
                result.optimization, objective_value=self._objective(polished),
                max_hx_temperature_spread_k=_hx_profile_spread(polished),
            )
        return polished

    def _recover_inventory_search(self, original: ValueError) -> PlantResult:
        """Budgeted feasibility restoration, followed by objective ranking.

        Dyadic subdivision covers intermediate inventories missed by the fast
        geometric walk. The capacity-rate scale orders work, not feasibility.
        A finite sampling search cannot certify that all roots are absent.
        """
        self._recovering = True
        reference = .25 * min(self.config.compressor_stages, self.config.expander_stages)
        tried: set[float] = set()
        solutions: list[tuple[float, PlantResult]] = []
        causes: Counter[str] = Counter()
        def probe(inventory: float) -> None:
            inventory = min(INVENTORY_MAX, max(INVENTORY_MIN, inventory))
            if inventory in tried:
                return
            tried.add(inventory)
            try:
                solutions.append((inventory, self._recover_cold_loop(inventory)))
            except ValueError as exc:
                causes[str(exc).split(";")[0]] += 1
        for divisions in (8, 16, 32):
            for i in range(divisions + 1):
                probe(reference * (.5 + 1.5 * i / divisions))
            if solutions:
                break
        if not solutions:
            # Cover the remainder of the declared numerical inventory domain.
            for i in range(25):
                probe(INVENTORY_MIN * (INVENTORY_MAX / INVENTORY_MIN) ** (i / 24))
        if not solutions:
            raise SearchUnresolved(
                "no closed two-tank design found by bounded search; "
                "nonexistence is not certified. Original diagnostic: " + str(original)
                + "; recovery observations: " + str(causes.most_common(3))
            ) from original
        for _ in range(5):
            best, _ = max(solutions, key=lambda item: self._objective(item[1]))
            ordered = sorted(tried)
            index = ordered.index(best)
            for neighbour in ordered[max(0, index-1):index] + ordered[index+1:index+2]:
                probe(.5 * (best + neighbour))
        _, result = max(solutions, key=lambda item: self._objective(item[1]))
        result.optimization = OptimizationSummary(
            objective=self.config.optimization_objective.value,
            objective_value=self._objective(result), evaluated_points=len(tried),
            max_hx_temperature_spread_k=_hx_profile_spread(result),
        )
        return result

    def _run_fast_search(self) -> PlantResult:
        if self.config.mode is PlantMode.DIABATIC:
            return self._simulate_diabatic()

        c = self.config
        objective = self._objective

        # The outer variable is conserved coolant throughput, not a tank volume.
        # A capacity-matched air/coolant branch normally needs cp_air/cp_coolant ~=
        # 0.25 kg/kg, so the smaller train supplies a physically informed scale
        # even when compressor and expander stage counts differ.
        reference_inventory = 0.25 * min(c.compressor_stages, c.expander_stages)

        evaluated = 0
        last_dh_error: HeatOfftakeTemperatureError | None = None
        failure_causes: Counter[str] = Counter()
        attempted_values: set[float] = set()

        # Set when an inventory was rejected because the hot tank could not
        # reach the district-heating supply temperature.  That rejection IS
        # directional: more water only makes the tank colder, so there is no
        # point walking further up.  Every other rejection says nothing about
        # which way to go and must not stop the search.
        hot_end_exhausted = False

        def scan(values: list[float]) -> list[tuple[float, PlantResult]]:
            nonlocal evaluated, last_dh_error, hot_end_exhausted
            solutions: list[tuple[float, PlantResult]] = []
            for inventory in values:
                if inventory in attempted_values:
                    continue
                attempted_values.add(inventory)
                evaluated += 1
                try:
                    result = self._close_cold_loop(inventory)
                except HeatOfftakeTemperatureError as exc:
                    last_dh_error = exc
                    hot_end_exhausted = True
                    continue
                except ValueError as exc:
                    # Keep the physical cause: when every inventory fails, the
                    # user must learn WHICH constraint rejected the plant, not
                    # just that none was found.
                    failure_causes[str(exc)] += 1
                    continue
                solutions.append((inventory, result))
            return solutions

        coarse_factors = (
            (0.8, 1.0, 1.2)
            if self._absorbs_surplus()
            else (0.6, 0.8, 1.0, 1.2, 1.5)
        )
        # Walk OUTWARD from the physically informed reference, one side at a
        # time.  Order is chosen for cost, not for the answer: the first design
        # that closes seeds the coolant-loop continuation, and every later
        # inventory then follows that branch instead of proving the whole
        # return window out again.
        #
        # A failure does NOT end a side.  The feasible band can be an interval
        # that does not contain the reference at all - measured at 200 bar with
        # eight stages, where the reference is 2.0 and the band is [1.0, 1.3] -
        # so giving up on the first rejection loses the only designs that work.
        # The one exception is a hot-end district-heating rejection while
        # walking UP: more water can only make the tank colder, so that
        # direction is genuinely exhausted.
        def clamp(value: float) -> float:
            return min(INVENTORY_MAX, max(INVENTORY_MIN, value))

        below = sorted(
            {clamp(reference_inventory * f) for f in coarse_factors if f < 1.0},
            reverse=True,
        )
        above = sorted(
            {clamp(reference_inventory * f) for f in coarse_factors if f > 1.0}
        )
        coarse = scan([clamp(reference_inventory)])
        for value in above:
            coarse.extend(scan([value]))
            if hot_end_exhausted:
                break
        for value in below:
            coarse.extend(scan([value]))
        if not coarse:
            # A binding direct coolant limit can leave a narrow feasible band around
            # 1.7 times the capacity-rate scale. Probe it before paying for the
            # architecture-wide fallback.
            coarse = scan([
                reference_inventory * 1.5,
                reference_inventory * 1.7,
            ])
        if not coarse:
            # Unequal or single-stage trains can have a narrow feasible inventory
            # window.  A deterministic fallback avoids making the ordinary solve
            # expensive while still covering those architectures.
            coarse = scan([0.2, 0.3, 0.5, 0.7, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0])
            if not coarse:
                if last_dh_error is not None:
                    raise last_dh_error
                message = (
                    "no closed two-tank design is feasible for these pressures, "
                    "stage counts, coolant temperature limits, and finite heat-"
                    "exchanger settings"
                )
                if failure_causes:
                    # Report the real binding constraints, most frequent first.
                    reported = "; ".join(
                        f"{count}x {cause}"
                        for cause, count in failure_causes.most_common(3)
                    )
                    message += f". The constraints that rejected the candidate plants were: {reported}"
                message += (
                    ". Typical remedies, by cause: raise the selected coolant "
                    "maximum if the hot-side limit binds; increase "
                    "E-303 NTU if a selected sub-ambient return needs more recovery; add "
                    "stages/NTU if the moisture-safe turbine duties cannot be "
                    "reached; lower the heat-user temperatures or increase its "
                    "exchanger NTU if its finite effectiveness binds"
                )
                raise ValueError(message)
        # The selected objective always ranks the designs.  T-Q profile spread
        # remains a reported equipment-quality metric, never a hidden veto over
        # a better physical cycle: with no heat user every objective shares the
        # same surplus-absorbing dispatch, and with district heating the
        # minimum-turbine-duty topology is fixed by the heat export, so the
        # objective is free to pick the inventory directly.
        # Refine around the best *feasible* design while retaining infeasible
        # samples as interval boundaries.  This matters at high NTU: the most
        # parallel design can lie immediately below the DH hot-end limit, so a
        # single fixed refinement pass can stop far from the real boundary.
        solutions = list(coarse)
        for _ in range(5):
            solution_by_inventory = {item[0]: item for item in solutions}
            best_inventory = max(
                solutions, key=lambda item: objective(item[1])
            )[0]
            ordered = sorted(attempted_values)
            index = ordered.index(best_inventory)
            neighbours: list[float] = []
            if index > 0:
                neighbours.append(ordered[index - 1])
            if index + 1 < len(ordered):
                neighbours.append(ordered[index + 1])

            if neighbours:
                # An adjacent rejected point is the most valuable information:
                # the optimum often lies immediately on its feasible side.  If
                # both neighbours are feasible, refine toward the thermally
                # better one.  Only one new full cycle is needed per round.
                target = min(
                    neighbours,
                    key=lambda value: (
                        value in solution_by_inventory,
                        -objective(solution_by_inventory[value][1])
                        if value in solution_by_inventory
                        else abs(value - best_inventory),
                    ),
                )
            elif best_inventory < INVENTORY_MAX:
                target = min(INVENTORY_MAX, 1.25 * best_inventory)
            elif best_inventory > INVENTORY_MIN:
                target = 0.5 * (INVENTORY_MIN + best_inventory)
            else:
                break
            refine_value = 0.5 * (best_inventory + target)
            if refine_value in attempted_values:
                # The bracket stopped moving: further rounds would recompute
                # the same point without adding information.
                break
            solutions.extend(scan([refine_value]))

        _, result = max(solutions, key=lambda item: objective(item[1]))
        assert result.thermal_store is not None
        result.optimization = OptimizationSummary(
            objective=c.optimization_objective.value,
            objective_value=objective(result),
            evaluated_points=evaluated,
            max_hx_temperature_spread_k=_hx_profile_spread(result),
        )
        return result

    def _cold_loop_search_window(self) -> tuple[float, float]:
        """Bounds of the mixed-return search coordinate [K].

        The return is itself a coolant state, so it lives between the selected
        direct coolant minimum and maximum.  The
        window is kept a named margin above the frost-correlation domain limit
        so every trial point stays where the moisture correlations are valid.
        """
        c = self.config
        low = max(
            MINIMUM_FROST_CORRELATION_TEMPERATURE_K + COLD_LOOP_CORRELATION_MARGIN_K,
            c.ambient_temperature_k - COLD_LOOP_SEARCH_BELOW_AMBIENT_K,
            c.coolant_minimum_temperature_k,
        )
        high = min(
            c.ambient_temperature_k + COLD_LOOP_SEARCH_ABOVE_AMBIENT_K,
            c.coolant_maximum_temperature_k,
        )
        return low, high

    def _close_cold_loop(self, total_inventory: float) -> PlantResult:
        if self._preserve_search_path:
            return self._close_cold_loop_fast(total_inventory)
        try:
            result = self._close_cold_loop_fast(total_inventory)
        except ValueError as original:
            result = self._recover_cold_loop(total_inventory, original)
        return self._polish_wet_result(result)

    def _recover_cold_loop(
        self, total_inventory: float, original: ValueError | None = None,
    ) -> PlantResult:
        """Search the constructible temperature domain without assuming one island.

        Phi(T)=T0+d*(Tmix(E303(returns))+Q304/(r*cp)-T0).
        Only Phi(T)-T is rooted. E303 is heat-only; neither invariance of the
        domain nor endpoint sign opposition follows just from having E303.
        Final materialization validates every inequality as well as closure.
        """
        self._recovering = True
        self._cold_loop_seed = self._charge_seed = None
        self._extraction_margin_fraction_seed = None
        c = self.config
        inlet = state_pt(self._p_ambient, c.ambient_temperature_k, WORKING_FLUID)
        first = compress(inlet, self._p_ambient * self._compression_ratio(),
                         c.compressor_efficiency, WORKING_FLUID)
        low = max(c.coolant_minimum_temperature_k,
                  MINIMUM_FROST_CORRELATION_TEMPERATURE_K + COLD_LOOP_CORRELATION_MARGIN_K)
        high = min(c.coolant_maximum_temperature_k, first.outlet.temperature_k)
        states: dict[float, tuple[float, Cycle, _ThermalStore, _DischargeDesign | _LadderEvaluation] | None] = {}
        causes: Counter[str] = Counter()
        # Schur reduction of the minimum-duty network: at fixed inventory and
        # protected humidity, the mass equation and returns do not depend on
        # the charge temperature or available hot-store temperature. The latter
        # is only an inequality. Solve once against its physical upper bound;
        # never use that provisional temperature as an actual stored state.
        ladders: dict[float, _LadderEvaluation] = {}
        def ladder(store: _ThermalStore) -> _LadderEvaluation:
            humidity = store.protected_humidity_ratio
            if humidity not in ladders:
                bound = replace(store, hot_available_k=c.coolant_maximum_temperature_k
                                + TEMPERATURE_LIMIT_TOLERANCE_K)
                _, evaluation, _ = self._solve_extraction_margin_recovery(bound)
                ladders[humidity] = evaluation
            evaluation = ladders[humidity]
            if max(evaluation.supplies) > store.hot_available_k:
                raise ValueError("available hot store is below the mass-closed extraction ladder")
            return evaluation

        def produced_cold(design: _DischargeDesign | _LadderEvaluation) -> float:
            supplies = (design.supplies if isinstance(design, _LadderEvaluation)
                        else design.stage_supplies)
            recovery = self._optimize_cold_return_recovery(design.returns)
            tank = self._recuperated_tank_inlet_k(total_inventory, supplies,
                                                design.returns, recovery.mixed_tank_inlet_k)
            return c.ambient_temperature_k + (tank-c.ambient_temperature_k)*self._tank_decay(total_inventory)

        def residual(cold: float) -> float | None:
            if cold not in states:
                try:
                    self._charge_seed = None
                    charging, store = self._charge_adiabatic(cold, total_inventory)
                    if self._absorbs_surplus():
                        design = self._discharge_absorbing(store)
                    else:
                        try:
                            design = ladder(store)
                        except ValueError:
                            # Retain the original numerical recovery if the
                            # bound solve is unresolved (e.g. inverse tolerances).
                            _, design = self._discharge_adiabatic_unchecked(store, cold)
                            if design is None:
                                raise SearchUnresolved("no duty-feasible extraction ladder")
                    value = produced_cold(design)-cold
                    states[cold] = (value, charging, store, design)
                except ValueError as exc:
                    causes[str(exc)] += 1
                    states[cold] = None
            state = states[cold]
            return state[0] if state is not None else None

        def accept(root: float) -> PlantResult | None:
            state = states.get(root)
            if state is None or abs(state[0]) > COLD_LOOP_ROOT_RESIDUAL_K:
                return None
            _, charging, store, design = state
            try:
                if isinstance(design, _LadderEvaluation):
                    design = self._materialize_ladder(store, design)
                if abs(sum(r for r, _, _ in design.returns)-total_inventory) > MAX_WATER_MASS_CLOSURE_ERROR:
                    return None
                result = self._assemble_adiabatic(charging, store, design)
                if abs(result.thermal_store.cold_loop_closure_error_k) <= COLD_LOOP_RETURN_CLOSURE_K:
                    return result
            except ValueError:
                pass
            return None

        predictor_candidates: list[PlantResult] = []
        if not self._absorbs_surplus():
            # Analytic constant-map seed for the warm-cold-tank branch. All
            # coolers then discharge at >= T0 and the final separator sets the
            # humidity. Even outside that regime this is only a predictor:
            # residual() rebuilds the real charge, humidity and every guard.
            humidity = min(inlet_humidity_ratio(c),
                           saturation_humidity_ratio(self._p_storage, c.ambient_temperature_k))
            provisional = _ThermalStore(total_inventory, c.ambient_temperature_k,
                                        c.coolant_maximum_temperature_k,
                                        c.coolant_maximum_temperature_k, 0., (), humidity,
                                        c.coolant_maximum_temperature_k)
            try:
                predicted = produced_cold(ladder(provisional))
                if low <= predicted <= high:
                    residual(predicted)
                    result = accept(predicted)
                    if result is not None:
                        return result
            except ValueError:
                pass
        else:
            # M0 -> finite-NTU sensible-store predictor (uniform allocation,
            # constant cp, no wet envelope). Only propose a coordinate: all
            # real-fluid, allocation and humidity constraints stay in residual.
            try:
                predicted = self._sensible_cold_seed(total_inventory, low, high)
                value = residual(predicted)
                result = accept(predicted)
                if result is not None:
                    predictor_candidates.append(result)
                # One local signed bracket around the analytic predictor. No
                # global monotonicity is assumed across allocation switches.
                if value is not None:
                    neighbour = min(high, predicted+1.) if value > 0 else max(low, predicted-1.)
                    other = residual(neighbour)
                    if other is not None and value*other <= 0:
                        def finite(cold: float) -> float:
                            value = residual(cold)
                            if value is None:
                                raise SearchUnresolved("predictor bracket leaves the admissible branch")
                            return value
                        root = bracketed_root(finite, min(predicted, neighbour), max(predicted, neighbour),
                                              residual_tolerance=COLD_LOOP_ROOT_RESIDUAL_K,
                                              max_iterations=8)
                        result = accept(root)
                        if result is not None:
                            predictor_candidates.append(result)
            except ValueError:
                pass
        candidates = []
        for divisions in (16, 64):
            for root in sampled_roots(residual, low, high, subdivisions=divisions,
                                      residual_tolerance=COLD_LOOP_ROOT_RESIDUAL_K):
                result = accept(root)
                if result is not None:
                    candidates.append(result)
            if candidates:
                # A continuation/affine root need not be the best LTA branch.
                # Keep the original sampled branch comparison even when the
                # predictor closes (25 bar has two distinct valid roots).
                return max(candidates + predictor_candidates, key=self._objective)
        if predictor_candidates:
            return max(predictor_candidates, key=self._objective)
        raise SearchUnresolved(
            "no closed coolant-loop root found in the sampled physical domain; "
            "nonexistence is not certified; " + str(original or causes.most_common(3))
        ) from original

    def _sensible_cold_seed(self, inventory: float, low: float, high: float) -> float:
        """Closed affine M1-M3 predictor; never used as plant physics.

        Calorically perfect air (cp=1005, kappa=2/7), uniform parallel splits,
        actual NTU/efficiencies/pressure ratios/tank decay. E303 is inactive on
        this warm-return surrogate. In M0, equal stage counts and matched
        capacities give Tc=T0, Th=T0*Pi**(kappa/n), RTE=1 exactly. In other
        regimes the real residual, not this extrapolation, decides acceptance.
        """
        c = self.config
        cp = 1005.
        decay = self._tank_decay(inventory)
        alpha = 1.+(self._compression_ratio()**(2./7.)-1.)/c.compressor_efficiency
        beta = 1.-c.expander_efficiency*(1.-self._expansion_ratio()**(2./7.))
        def capacity(count: int) -> tuple[float, float]:
            water = inventory*WATER_CP_J_PER_KGK/count
            small, large = min(cp, water), max(cp, water)
            conductance = counterflow_effectiveness(c.heat_exchanger_ntu, small/large)*small
            return water, conductance
        wc, kc = capacity(c.compressor_stages)
        we, ke = capacity(c.expander_stages)
        def mapping(cold: float) -> float:
            air = c.ambient_temperature_k
            recovered = 0.
            for _ in range(c.compressor_stages):
                hot = alpha*air
                duty = kc*(hot-cold)
                air = hot-duty/cp
                recovered += duty
            hot_store = c.ambient_temperature_k + decay*(cold+recovered/(inventory*WATER_CP_J_PER_KGK)-c.ambient_temperature_k)
            air = c.ambient_temperature_k
            returns = 0.
            for _ in range(c.expander_stages):
                duty = ke*(hot_store-air)
                returns += hot_store-duty/we
                air = beta*(air+duty/cp)
            return c.ambient_temperature_k + decay*(returns/c.expander_stages-c.ambient_temperature_k)
        intercept = mapping(0.)
        return affine_fixed_point(intercept, mapping(1.)-intercept, low, high)

    def _close_cold_loop_fast(self, total_inventory: float) -> PlantResult:
        """Close the coolant loop for one conserved coolant inventory.

        The search coordinate is the cold-tank temperature. A trial builds the
        charge and discharge trains, selects the best legal E-303 return suffix,
        mixes its warmed outlet with the bypass returns, applies cold-tank
        standing, and closes that produced tank state against the trial.
        """
        low, high = self._cold_loop_search_window()

        candidates: list[PlantResult] = []
        last_dh_error: HeatOfftakeTemperatureError | None = None
        # Physical rejections counted by frequency.  Reporting the LAST
        # exception is misleading: it is almost always an artifact of the scan
        # probing an obviously unphysical end of the window, while the cause
        # that rejected most of the window is the one the user must act on.
        causes: Counter[str] = Counter()
        # Most recent successful evaluation, reused by accept_root so the
        # accepted root does not pay for a second identical full cycle solve.
        last_evaluation: tuple[
            float,
            Cycle,
            _ThermalStore,
            _DischargeDesign | _LadderEvaluation,
            _ColdReturnRecovery,
        ] | None = None

        def closure_residual(cold_k: float) -> tuple[float, float] | None:
            nonlocal last_evaluation, last_dh_error
            try:
                charging, store = self._charge_adiabatic(cold_k, total_inventory)
                if self._absorbs_surplus():
                    design = self._discharge_absorbing(store)
                else:
                    solved = self._discharge_adiabatic_unchecked(store, cold_k)
                    design = solved[1]
                    if design is None:
                        return None
                assert design is not None
                recovery = self._optimize_cold_return_recovery(design.returns)
                # E-304 sits between the final return mixing and the cold tank,
                # so the loop closes on the RECUPERATED inlet, not on the mixed
                # return. Omitting it here would close a plant whose cold tank
                # is tens of kelvin colder than the one actually built.
                supplies = (
                    design.supplies
                    if isinstance(design, _LadderEvaluation)
                    else design.stage_supplies
                )
                tank_inlet_k = self._recuperated_tank_inlet_k(
                    store.total_ratio,
                    supplies,
                    design.returns,
                    recovery.mixed_tank_inlet_k,
                )
                produced_cold_k = self.config.ambient_temperature_k + (
                    tank_inlet_k - self.config.ambient_temperature_k
                ) * self._tank_decay(total_inventory)
                residual = produced_cold_k - cold_k
            except HeatOfftakeTemperatureError as exc:
                last_dh_error = exc
                causes[str(exc)] += 1
                return None
            except ValueError as exc:
                causes[str(exc)] += 1
                return None
            if design is None:
                causes[
                    "the finite interheaters cannot transfer the moisture-safe "
                    "stage duties from the available coolant temperature"
                ] += 1
                return None
            last_evaluation = (cold_k, charging, store, design, recovery)
            return cold_k, residual

        def accept_root(cold_k: float) -> bool:
            nonlocal last_dh_error
            try:
                if last_evaluation is not None and last_evaluation[0] == cold_k:
                    # The residual evaluation just solved this exact cycle;
                    # assemble the result from it instead of re-solving.
                    _, charging, store, solved_discharge, _ = last_evaluation
                    if isinstance(solved_discharge, _LadderEvaluation):
                        design = self._materialize_ladder(
                            store, solved_discharge
                        )
                        full_required = sum(
                            ratio for ratio, _, _ in design.returns
                        )
                        if (
                            abs(full_required - store.total_ratio)
                            > MAX_WATER_MASS_CLOSURE_ERROR
                        ):
                            return False
                    else:
                        design = solved_discharge
                    result = self._assemble_adiabatic(charging, store, design)
                else:
                    result = self._simulate_adiabatic(cold_k, total_inventory)
            except HeatOfftakeTemperatureError as exc:
                last_dh_error = exc
                return False
            except ValueError as exc:
                causes[str(exc)] += 1
                return False
            assert result.thermal_store is not None
            produced_cold_k = self.config.ambient_temperature_k + (
                result.thermal_store.cold_return_exchanger_outlet_temperature_k
                - self.config.ambient_temperature_k
            ) * self._tank_decay(total_inventory)
            if (
                abs(produced_cold_k - cold_k)
                > COLD_LOOP_RETURN_CLOSURE_K
            ):
                return False
            candidates.append(result)
            self._cold_loop_seed = (total_inventory, cold_k)
            return True

        # A feasible window can start between two coarse samples, and the root
        # can lie less than a kelvin above that boundary.  Locate the boundary
        # adaptively instead of discarding the first feasible point's left side.
        def first_feasible(
            infeasible_return_k: float, feasible: tuple[float, float]
        ) -> tuple[float, float]:
            left = infeasible_return_k
            best = feasible
            # Fourteen halvings locate a 2 K boundary to about 1e-4 K,
            # already tighter than the final physical closure tolerance.
            for _ in range(14):
                middle_return_k = 0.5 * (left + best[0])
                middle = closure_residual(middle_return_k)
                if middle is None:
                    left = middle_return_k
                else:
                    best = middle
            return best

        def bisect(
            left: tuple[float, float], right: tuple[float, float]
        ) -> float:
            """Safeguarded Illinois refinement of one return-temperature root.

            Both dispatch paths now close the coolant mass inside their own
            solve, so this outer residual is always a return temperature that
            the assembled result re-verifies to
            ``COLD_LOOP_RETURN_CLOSURE_K``.
            """
            if left[0] == right[0]:
                return left[0]
            a, b = left, right
            f_a, f_b = a[1], b[1]
            last_side = 0
            best = min((a, b), key=lambda item: abs(item[1]))
            for _ in range(32):
                trial_k = trial_point(a[0], f_a, b[0], f_b)
                trial = closure_residual(trial_k)
                if trial is None:
                    break
                if abs(trial[1]) < abs(best[1]):
                    best = trial
                if abs(trial[1]) <= COLD_LOOP_ROOT_RESIDUAL_K:
                    return trial[0]
                if f_a * trial[1] <= 0.0:
                    b = trial
                    f_b = trial[1]
                    if last_side == -1:
                        f_a *= 0.5
                    last_side = -1
                else:
                    a = trial
                    f_a = trial[1]
                    if last_side == 1:
                        f_b *= 0.5
                    last_side = 1
                if b[0] - a[0] <= COLD_LOOP_ROOT_RESIDUAL_K:
                    break
            return best[0]

        def local_bracket(
            centre_k: float, span_k: float
        ) -> tuple[tuple[float, float], tuple[float, float]] | None:
            """Expand outward from a previous root until a sign change is caught.

            Continuation along one solution branch.  The full window walk costs
            about a hundred complete charge/discharge closures per inventory;
            following the branch costs a handful, and it is also the physically
            correct thing to do, because it keeps consecutive inventories on the
            SAME root instead of letting the objective jump between branches.
            """
            here = closure_residual(centre_k)
            if here is None:
                return None
            nearest_left = nearest_right = here
            if abs(here[1]) <= COLD_LOOP_ROOT_RESIDUAL_K:
                return here, here
            # Geometric expansion catches the same interval in at most nine
            # probes instead of walking ten equal steps in both directions.
            for fraction in (1 / 16, 1 / 8, 1 / 4, 1 / 2, 1.0):
                offset = fraction * span_k
                for probe_k, going_left in (
                    (centre_k - offset, True),
                    (centre_k + offset, False),
                ):
                    if not low <= probe_k <= high:
                        continue
                    probe = closure_residual(probe_k)
                    if probe is None:
                        continue
                    if going_left:
                        if probe[1] * nearest_left[1] <= 0.0:
                            return probe, nearest_left
                        nearest_left = probe
                    else:
                        if probe[1] * nearest_right[1] <= 0.0:
                            return nearest_right, probe
                        nearest_right = probe
            return None

        def walk() -> None:
            """Walk the whole return window, refining and accepting every root.

            Refines every infeasible-to-feasible transition and accepts EVERY
            residual sign change.  Stopping at the first one silently selected
            the lowest-temperature root whenever the closure has more than one,
            which is a selection error rather than a tolerance one.

            The fast walk stops after leaving the first observed component.
            This legacy heuristic is retained for reproducibility; a failed
            fast search is followed by recovery without the single-island
            assumption. Neither finite scan certifies root absence.
            """
            previous: tuple[float, float] | None = None
            previous_return_k: float | None = None
            entered = False
            left_for = 0
            steps = int((high - low) / COLD_LOOP_SCAN_STEP_K) + 1
            for index in range(steps + 1):
                return_k = min(high, low + index * COLD_LOOP_SCAN_STEP_K)
                evaluated = closure_residual(return_k)
                if evaluated is not None:
                    entered = True
                    left_for = 0
                    if previous is None and previous_return_k is not None:
                        boundary = first_feasible(previous_return_k, evaluated)
                        if boundary[0] < evaluated[0] - 1e-9:
                            previous = boundary
                    if previous is not None and previous[1] * evaluated[1] <= 0.0:
                        accept_root(bisect(previous, evaluated))
                    previous = evaluated
                else:
                    # Never bridge a thermodynamically infeasible interval.
                    previous = None
                    if entered:
                        left_for += 1
                        if left_for >= COLD_LOOP_ABANDON_AFTER_LEAVING:
                            return
                previous_return_k = return_k
                if return_k >= high:
                    return

        seed = self._cold_loop_seed
        if seed is not None:
            seed_inventory, seed_return_k = seed
            # The branch moves with the inventory, so the probe span follows the
            # RELATIVE change rather than being a fixed number of kelvin.
            span_k = min(
                COLD_LOOP_CONTINUATION_MAX_SPAN_K,
                max(
                    COLD_LOOP_CONTINUATION_MIN_SPAN_K,
                    COLD_LOOP_CONTINUATION_SENSITIVITY_K
                    * abs(total_inventory - seed_inventory)
                    / seed_inventory,
                ),
            )
            if low <= seed_return_k <= high:
                bracket = local_bracket(seed_return_k, span_k)
                if bracket is not None and accept_root(bisect(*bracket)):
                    return candidates[0]

        # First inventory: the physical return normally lies near ambient.
        # Try that informed centre before walking upward from the cold edge of
        # the full correlation window.
        ambient_centre = min(
            high, max(low, self.config.ambient_temperature_k)
        )
        initial_span = min(80.0, max(0.0, high - low))
        bracket = local_bracket(ambient_centre, initial_span)
        if bracket is not None and accept_root(bisect(*bracket)):
            return candidates[0]

        # No usable branch to continue from: sample the legacy search window.
        walk()

        if not candidates:
            if last_dh_error is not None:
                raise last_dh_error
            message = "no closed coolant-loop root exists for this coolant inventory"
            if causes:
                reported = "; ".join(
                    f"{count}x {cause}" for cause, count in causes.most_common(2)
                )
                message += f"; the constraints that rejected it were: {reported}"
            raise ValueError(message)
        # Several roots can close the same inventory.  Rank them by the plant
        # objective rather than by where the scan happened to meet them first.
        return max(candidates, key=self._objective)

    # ---------------------------------------------------------------- pressure layout

    def _compression_ratio(self) -> float:
        c = self.config
        alpha = 1.0 - c.intercooler_pressure_drop
        return (self._p_storage / self._p_ambient) ** (1.0 / c.compressor_stages) / alpha

    def _expansion_ratio(self) -> float:
        c = self.config
        alpha = 1.0 - c.interheater_pressure_drop
        # Every expansion stage is preceded by one heat-exchanger/duct train, so
        # every stage counts one pressure drop even if ambient reheat is bypassed.
        heaters = c.expander_stages
        return ((self._p_ambient / self._p_storage) / alpha**heaters) ** (1.0 / c.expander_stages)

    # ---------------------------------------------------------------- A-CAES charge

    def _tank_decay(self, total_ratio: float) -> float:
        """Lumped-capacitance decay factor of one standing tank over the dwell.

        Integrates ``C dT/dt = -UA (T - T_ambient)`` analytically between the
        charged and discharged equilibrium states, so the plant stays a steady
        two-state model rather than a transient one.  The same normalized UA
        and standing time are applied to both tanks: the hot tank stands full
        between charge and discharge, the cold tank between discharge and the
        next charge.  UA is normalized to the one-kilogram-air analysis basis.
        """
        c = self.config
        if c.thermal_storage_tank_ua_w_per_k <= 0.0 or total_ratio <= 0.0:
            return 1.0
        capacitance_j_per_k_per_kg_air = total_ratio * WATER_CP_J_PER_KGK
        return exp(
            -c.thermal_storage_tank_ua_w_per_k
            * c.storage_duration_hours * 3600.0
            / capacitance_j_per_k_per_kg_air
        )

    def _cold_return_exchanger_outlet_temperature(
        self,
        returned_temperature_k: float,
    ) -> float:
        """Heat-only E-303 outlet for one already mixed selected subgroup [K]."""
        ambient_k = self.config.ambient_temperature_k
        if (
            self.config.cold_return_cooler_ntu <= 0.0
            or returned_temperature_k >= ambient_k
        ):
            return returned_temperature_k
        return ambient_k + (
            returned_temperature_k - ambient_k
        ) * exp(-self.config.cold_return_cooler_ntu)

    def _optimize_cold_return_recovery(
        self,
        branches: tuple[tuple[float, float, float], ...],
    ) -> _ColdReturnRecovery:
        """Place one E-303 on the coldest group of interheater returns.

        There is exactly one ambient exchanger, so the only decision is which
        returns join the manifold ahead of it. A candidate mixes that group,
        warms the mixture toward ambient through the finite-NTU body, and only
        then mixes it with the bypass returns. For constant coolant ``cp`` and
        one implicitly resized NTU class, maximising the final cold-tank inlet
        is exactly equivalent to maximising

            R_s cp (T0 - T_s) (1 - exp(-NTU)),  T_s < T0.

        The candidates are the returns SORTED BY TEMPERATURE, coldest first.
        Any optimal group is downward closed in temperature - swapping a warmer
        member for a colder non-member always lowers the mixed inlet and so
        raises the duty - which makes those N thresholds the complete search,
        not a heuristic slice of the 2**N subsets.

        Ordering by temperature rather than by stage index matters here. The
        former serial cascade fed every interheater from one trunk temperature,
        which happened to make the returns monotone in stage order; E-304 feeds
        each stage its own supply, and the returns are no longer sorted by stage.
        A stage-ordered suffix would then quietly stop being the optimum.
        """
        positive = [
            (index, ratio, temperature)
            for index, (ratio, temperature, _) in enumerate(branches)
            if ratio > 0.0
        ]
        if not positive:
            raise ValueError("the discharge produced no coolant return flow")
        total_ratio = sum(item[1] for item in positive)
        raw_energy = sum(ratio * temperature for _, ratio, temperature in positive)
        raw_mean = raw_energy / total_ratio
        ambient_k = self.config.ambient_temperature_k
        coldest_first = sorted(positive, key=lambda item: (item[2], item[0]))

        best: _ColdReturnRecovery | None = None
        for count in range(1, len(coldest_first) + 1):
            group = coldest_first[:count]
            start_stage = min(item[0] for item in group)
            ratio = sum(item[1] for item in group)
            inlet_k = sum(item[1] * item[2] for item in group) / ratio
            if inlet_k >= ambient_k - 1e-12:
                continue
            outlet_k = self._cold_return_exchanger_outlet_temperature(inlet_k)
            absorbed = ratio * WATER_CP_J_PER_KGK * (outlet_k - inlet_k)
            bypass_energy = raw_energy - ratio * inlet_k
            tank_inlet_k = (bypass_energy + ratio * outlet_k) / total_ratio
            candidate = _ColdReturnRecovery(
                start_stage=start_stage,
                branch_count=count,
                mass_ratio=ratio,
                inlet_k=inlet_k,
                outlet_k=outlet_k,
                mixed_tank_inlet_k=tank_inlet_k,
                heat_absorbed_j_per_kg_air=absorbed,
            )
            if best is None or absorbed > best.heat_absorbed_j_per_kg_air + 1e-9:
                best = candidate

        if best is not None:
            return best
        # No legal subgroup is colder than ambient: E-303 is bypassed, never
        # reversed into a cooler.
        return _ColdReturnRecovery(
            start_stage=None,
            branch_count=0,
            mass_ratio=0.0,
            inlet_k=raw_mean,
            outlet_k=raw_mean,
            mixed_tank_inlet_k=raw_mean,
            heat_absorbed_j_per_kg_air=0.0,
        )

    def _charge_with_ratios(
        self,
        cold_k: float,
        ratios: list[float],
        *,
        enforce_water_limit: bool = True,
        analyze_moisture: bool = True,
    ) -> tuple[Cycle, _ThermalStore]:
        """Run the sequential compressor train for an explicit parallel-water split.

        Provisional fixed-point iterates pass ``analyze_moisture=False``: the
        humidity propagation and its validity screens only need to run - and
        can only legitimately reject - on the final, validated train.
        """
        c = self.config
        if cold_k < c.coolant_minimum_temperature_k - TEMPERATURE_LIMIT_TOLERANCE_K:
            raise ValueError(
                "cold TES temperature is below the selected coolant freezing point"
            )
        current = state_pt(self._p_ambient, c.ambient_temperature_k, WORKING_FLUID)
        cycle = Cycle("charging", current)
        pressure_ratio = self._compression_ratio()
        branches: list[tuple[float, float, float]] = []

        for stage in range(c.compressor_stages):
            p_out = self._p_storage / (1.0 - c.intercooler_pressure_drop) if stage == c.compressor_stages - 1 else current.pressure_pa * pressure_ratio
            compressor = compress(current, p_out, c.compressor_efficiency, WORKING_FLUID)
            cycle.processes.append(compressor)
            cooler = cool_air_with_water(
                compressor.outlet, cold_k, c.intercooler_pressure_drop, WORKING_FLUID,
                c.heat_exchanger_ntu, ratios[stage],
            )
            cycle.processes.append(cooler)
            hx = cooler.heat_exchanger
            if hx is None:
                raise ValueError("charging water is not colder than a compressor outlet")
            branches.append((ratios[stage], hx.water_outlet_temperature_k, hx.duty_j_per_kg_air))
            current = cooler.outlet

        if abs(current.temperature_k - c.ambient_temperature_k) > 1e-9:
            cavern = exchange_with_environment(
                current, c.ambient_temperature_k, 0.0, WORKING_FLUID,
                "aftercooling", BOTH_WAYS,
            )
            cycle.processes.append(cavern)

        total_ratio = sum(branch[0] for branch in branches)
        recovered = sum(branch[2] for branch in branches)
        hot_before = cold_k + recovered / (total_ratio * WATER_CP_J_PER_KGK)
        maximum_water_reached = max(
            cold_k,
            hot_before,
            *(temperature for _, temperature, _ in branches),
        )
        decay = self._tank_decay(total_ratio)
        hot_available = c.ambient_temperature_k + (
            hot_before - c.ambient_temperature_k
        ) * decay
        storage_loss = total_ratio * WATER_CP_J_PER_KGK * (
            hot_before - hot_available
        )
        store = _ThermalStore(
            total_ratio=total_ratio,
            cold_k=cold_k,
            hot_before_loss_k=hot_before,
            hot_available_k=hot_available,
            storage_loss_j_per_kg_air=storage_loss,
            charge_returns=tuple(branches),
            protected_humidity_ratio=0.0,
            maximum_water_temperature_reached_k=maximum_water_reached,
            moisture=None,
        )
        return self._finalize_charge(
            cycle,
            store,
            enforce_water_limit=enforce_water_limit,
            analyze_moisture=analyze_moisture,
        )

    def _finalize_charge(
        self,
        cycle: Cycle,
        store: _ThermalStore,
        *,
        enforce_water_limit: bool,
        analyze_moisture: bool,
    ) -> tuple[Cycle, _ThermalStore]:
        """Validate and annotate an already-built charge train exactly once."""

        c = self.config
        maximum_water_allowed = c.coolant_maximum_temperature_k
        if (
            enforce_water_limit
            and store.maximum_water_temperature_reached_k
            > maximum_water_allowed + TEMPERATURE_LIMIT_TOLERANCE_K
        ):
            raise ValueError(
                "coolant maximum temperature limit exceeded: the hottest coolant reaches "
                f"{store.maximum_water_temperature_reached_k - 273.15:.2f} °C, while "
                f"the configured maximum of {maximum_water_allowed - 273.15:.2f} °C"
            )
        if not analyze_moisture:
            return cycle, store

        moisture = analyze_charge_moisture(c, cycle)
        protected_humidity_ratio = (
            moisture.stored_air_water_vapor_kg_per_kg_dry_air
        )
        if not reference_wet_expander_liquid_envelope_ok(
            protected_humidity_ratio
        ):
            raise ValueError(
                "remaining charge-side moisture exceeds the selected reference "
                "wet-expander discharge liquid envelope; add deeper drying or "
                "select an OEM machine with a larger guaranteed liquid capacity"
            )
        if not dry_air_wet_expansion_approximation_ok(
            protected_humidity_ratio
        ):
            raise ValueError(
                "possible wet-expander condensate exceeds the dry-air model's "
                "0.1 wt% validity screen; use a coupled humid-air/two-phase "
                "energy balance for this configuration"
            )
        return cycle, replace(
            store,
            protected_humidity_ratio=protected_humidity_ratio,
            moisture=moisture,
        )

    def _charge_adiabatic(self, cold_k: float, total_inventory: float) -> tuple[Cycle, _ThermalStore]:
        """Allocate charge water by heat-capacity matching, not by HX duty.

        In a counter-current exchanger the two T-Q curves are locally parallel
        when their heat-capacity rates match.  On the one-kilogram-air basis this
        is ``r_i cp_water ~= cp_air,eff``.  The effective air heat capacity is
        evaluated from the *real solved enthalpy and temperature change* of each
        stage, so compressor inefficiency, pressure, variable cp and upstream HX
        decisions are all included.

        Because each cooler changes the inlet of the next compressor, the target
        ratios are a small fixed-point problem.  Repeatedly solve the real train,
        derive its capacity-matched ratios, and project them back onto the exact
        conserved total inventory. This avoids starving an early stage and
        propagating an unnecessarily hot inlet through the train.
        """
        capacity_matched = self._capacity_matched_ratios(cold_k, total_inventory)
        allowed_k = self.config.coolant_maximum_temperature_k

        # ``fits`` and the accepted path used to build the same charge train
        # twice. Retain the most recent exact trial and add the expensive
        # moisture annotation only after its split has been accepted.
        last_trial: tuple[
            tuple[float, ...], tuple[Cycle, _ThermalStore]
        ] | None = None

        def trial(ratios: list[float]) -> tuple[Cycle, _ThermalStore]:
            nonlocal last_trial
            key = tuple(ratios)
            if last_trial is not None and last_trial[0] == key:
                return last_trial[1]
            solved = self._charge_with_ratios(
                cold_k,
                ratios,
                enforce_water_limit=False,
                analyze_moisture=False,
            )
            last_trial = (key, solved)
            return solved

        def finalize(ratios: list[float]) -> tuple[Cycle, _ThermalStore]:
            return self._finalize_charge(
                *trial(ratios),
                enforce_water_limit=True,
                analyze_moisture=True,
            )

        def peak_water_k(ratios: list[float]) -> float:
            _, store = trial(ratios)
            return store.maximum_water_temperature_reached_k

        def fits(ratios: list[float]) -> bool:
            return peak_water_k(ratios) <= allowed_k + TEMPERATURE_LIMIT_TOLERANCE_K

        if fits(capacity_matched):
            return finalize(capacity_matched)

        # The ceiling binds.  Move toward the peak-minimizing split only as far
        # as the ceiling actually requires, instead of jumping to it: that jump
        # used to cost 35 kJ/kg of compression work (-1.6 points of round-trip
        # efficiency) for a 0.5% change in inventory, because the relief split
        # is chosen to minimize the hottest coolant state and not to minimize
        # work, so a starved branch cools its stage badly.
        relief = self._peak_minimizing_ratios(cold_k, total_inventory)

        def blend(fraction: float) -> list[float]:
            return [
                (1.0 - fraction) * matched + fraction * relieved
                for matched, relieved in zip(capacity_matched, relief)
            ]

        # The peak temperature is monotone along this segment in every case
        # measured, but that is not guaranteed, so find the FIRST feasible
        # coarse point and bisect only inside the interval that precedes it.
        lower, upper = 0.0, None
        for step in range(1, CHARGE_BLEND_COARSE_STEPS + 1):
            fraction = step / CHARGE_BLEND_COARSE_STEPS
            if fits(blend(fraction)):
                upper = fraction
                break
            lower = fraction
        if upper is None:
            # Even the pure relief split exceeds the coolant maximum. Hand it to the validating call
            # so the user gets the real temperatures in the error, not a bare
            # search failure.
            return finalize(relief)
        lower, upper = bisect(
            lambda fraction: fits(blend(fraction)),
            lower,
            upper,
            iterations=CHARGE_BLEND_BISECTIONS,
        )
        return finalize(blend(upper))

    def _capacity_matched_ratios(
        self, cold_k: float, total_inventory: float
    ) -> list[float]:
        """Converge the capacity-rate-matched charge split for one cold state.

        Iterated to a real tolerance rather than to a fixed iteration count.
        Stopping early was not a cosmetic inaccuracy: an under-converged split
        lands slightly above the coolant maximum and hands the design to
        the much worse relief allocation, which is what produced the measured
        discontinuity in the objective.
        """
        n = self.config.compressor_stages
        # Warm start from the last converged split: neighbouring coolant-loop
        # trial points then need one or two updates instead of the full walk.
        seed = None if self._recovering else self._charge_seed
        if seed is not None and abs(seed[0] - cold_k) <= 4.0 and len(seed[1]) == n:
            ratios = [
                ratio * total_inventory / sum(seed[1]) for ratio in seed[1]
            ]
        else:
            ratios = [total_inventory / n] * n

        previous_change = float("inf")
        for iteration in range(CHARGE_FIXED_POINT_MAX_ITERATIONS):
            provisional, _ = self._charge_with_ratios(
                cold_k, ratios, enforce_water_limit=False, analyze_moisture=False
            )
            targets: list[float] = []
            for process in provisional.processes:
                if process.kind != "intercooling" or not process.heat_exchanger:
                    continue
                delta_t_air = process.inlet.temperature_k - process.outlet.temperature_k
                duty = process.heat_exchanger.duty_j_per_kg_air
                if delta_t_air <= 1e-9 or duty <= 0.0:
                    raise ValueError("charging train recovers no usable heat")
                # Q / DeltaT is the secant heat capacity of the real air path.
                targets.append(duty / (WATER_CP_J_PER_KGK * delta_t_air))
            scale = total_inventory / sum(targets)
            projected = [target * scale for target in targets]
            change = max(abs(new - old) for new, old in zip(projected, ratios))
            ratios = projected
            if change <= CHARGE_FIXED_POINT_TOLERANCE:
                break
            # Stagnation guard.  The update is a contraction in every case
            # measured; if it stops contracting it will not converge, and the
            # remaining iterations would only burn CoolProp calls.  The split
            # is still an exactly conserved one, and the forward solve that
            # follows validates the real physics, so this degrades accuracy
            # rather than correctness.
            if iteration >= 3 and change > CHARGE_FIXED_POINT_STAGNATION * previous_change:
                break
            previous_change = change

        self._charge_seed = (cold_k, list(ratios))
        return ratios

    def _peak_minimizing_ratios(
        self, cold_k: float, total_inventory: float
    ) -> list[float]:
        """Conserved charge split that minimizes the hottest coolant state.

        Equalising the real branch water-temperature rises moves water from
        cooler branches to hotter ones while preserving the exact inventory.
        This is the split that best respects a low coolant-circuit pressure, and
        it is deliberately never used on its own merits: it is only the far end
        of the relief segment in :meth:`_charge_adiabatic`.
        """
        n = self.config.compressor_stages
        ratios = [total_inventory / n] * n
        best_ratios = list(ratios)
        best_maximum = float("inf")
        for _ in range(CHARGE_RELIEF_ITERATIONS):
            _, provisional_store = self._charge_with_ratios(
                cold_k, ratios, enforce_water_limit=False, analyze_moisture=False
            )
            maximum = provisional_store.maximum_water_temperature_reached_k
            if maximum < best_maximum:
                best_maximum = maximum
                best_ratios = list(ratios)
            rises = [
                max(1e-6, temperature_k - cold_k)
                for _, temperature_k, _ in provisional_store.charge_returns
            ]
            weighted_mean = sum(
                ratio * rise for ratio, rise in zip(ratios, rises)
            ) / total_inventory
            projected = [
                max(1e-6, ratio * rise / weighted_mean)
                for ratio, rise in zip(ratios, rises)
            ]
            scale = total_inventory / sum(projected)
            new_ratios = [ratio * scale for ratio in projected]
            if max(abs(a - b) for a, b in zip(new_ratios, ratios)) <= 2e-6:
                return new_ratios
            ratios = new_ratios
        return best_ratios

    # ---------------------------------------------------------------- A-CAES discharge

    def _heater_target(
        self,
        inlet,
        turbine_outlet_pressure_pa: float,
        protected_humidity_ratio: float,
    ):
        """Air state after the interheater that meets the local moisture limit."""
        c = self.config
        heater_pressure = inlet.pressure_pa * (1.0 - c.interheater_pressure_drop)
        target_temperature_k = minimum_wet_expander_temperature_k(
            turbine_outlet_pressure_pa,
            protected_humidity_ratio,
        )

        # Start from an isenthalpic pressure drop. If no heat is needed, retain it.
        base = state_ph(heater_pressure, inlet.enthalpy_j_per_kg, WORKING_FLUID)
        if expand(
            base, turbine_outlet_pressure_pa, c.expander_efficiency, WORKING_FLUID
        ).outlet.temperature_k >= target_temperature_k:
            return base

        def outlet_at(heater_temperature_k: float) -> float:
            return expand(
                state_pt(heater_pressure, heater_temperature_k, WORKING_FLUID),
                turbine_outlet_pressure_pa, c.expander_efficiency, WORKING_FLUID,
            ).outlet.temperature_k

        # Bracket the root adaptively: high stage pressure ratios combined with
        # a high selected outlet limit can need heater temperatures far above
        # the usual few hundred kelvin, so a fixed upper bound silently missed
        # the root and surfaced later as an unrelated "infeasible" error.
        low_t = base.temperature_k
        high_t = max(base.temperature_k + 20.0, target_temperature_k + 400.0, 800.0)
        for _ in range(20):
            if outlet_at(high_t) >= target_temperature_k:
                break
            low_t = high_t
            high_t = 2.0 * high_t
        else:
            raise ValueError(
                "no pre-expansion temperature below "
                f"{high_t:.0f} K keeps the expander outlet at the selected "
                f"{target_temperature_k - 273.15:.1f} °C local moisture limit; "
                "the stage pressure ratio is too large for one heating step"
            )
        low_t, high_t = bisect(
            lambda heater_k: outlet_at(heater_k) >= target_temperature_k,
            low_t,
            high_t,
            iterations=55,
            tolerance=2e-5,
        )
        solved = state_pt(heater_pressure, 0.5 * (low_t + high_t), WORKING_FLUID)
        return solved

    def _discharge_requirements(
        self,
        protected_humidity_ratio: float,
    ) -> tuple[_DischargeRequirement, ...]:
        """Target duty and outlet pressure for each expansion stage.

        These targets depend only on the pressure train and turbomachinery, not
        on either tank temperature.  Computing them once avoids repeating the
        expensive CoolProp root solve inside every thermal-design candidate -
        tens of thousands of hits per solve.

        The cache is PER INSTANCE, not an ``lru_cache`` on the bound method:
        that keys on ``self`` and so pins every plant object it ever saw in a
        module-level dictionary for the lifetime of the process.
        """
        cached = self._requirements_cache.get(protected_humidity_ratio)
        if cached is not None:
            return cached
        computed = self._solve_discharge_requirements(protected_humidity_ratio)
        self._requirements_cache[protected_humidity_ratio] = computed
        return computed

    def _solve_discharge_requirements(
        self,
        protected_humidity_ratio: float,
    ) -> tuple[_DischargeRequirement, ...]:
        c = self.config
        current = state_pt(self._p_storage, c.ambient_temperature_k, WORKING_FLUID)
        pressure_ratio = self._expansion_ratio()
        requirements: list[_DischargeRequirement] = []
        for stage in range(c.expander_stages):
            heater_pressure = current.pressure_pa * (
                1.0 - c.interheater_pressure_drop
            )
            turbine_pressure = self._p_ambient if stage == c.expander_stages - 1 else heater_pressure * pressure_ratio
            target = self._heater_target(
                current, turbine_pressure, protected_humidity_ratio
            )
            turbine = expand(
                target, turbine_pressure, c.expander_efficiency, WORKING_FLUID
            )
            requirements.append(_DischargeRequirement(
                turbine_pressure_pa=turbine_pressure,
                duty_j_per_kg_air=max(
                    0.0,
                    target.enthalpy_j_per_kg - current.enthalpy_j_per_kg,
                ),
                heater_outlet_temperature_k=target.temperature_k,
            ))
            current = turbine.outlet
        return tuple(requirements)

    def _level_supplies(self, store: _ThermalStore) -> list[float]:
        """Direct hot-store supply used when the heat user is bypassed."""
        return [store.hot_available_k] * self.config.expander_stages

    def _discharge_at_supply(
        self,
        store: _ThermalStore,
        supplies: list[float],
        *,
        enforce_coolant_freezing: bool = True,
    ) -> tuple[float, _DischargeDesign | None]:
        """Return minimum-duty water demand at ``supplies`` and the full train.

        ``supplies`` is per stage: the E-304 extraction ladder may hand several
        stages one temperature where the demand envelope binds.

        The minimum-duty construction is also the lower-bound seed for the
        no-DH surplus-allocation solve. In that one use, an individual seed
        branch may be colder than the coolant limit because conserved surplus
        flow is added before a physical candidate is accepted. The final
        :meth:`_discharge_with_ratios` call always enforces freezing.
        """
        c = self.config
        current = state_pt(self._p_storage, c.ambient_temperature_k, WORKING_FLUID)
        cycle = Cycle("discharging", current)
        branches: list[tuple[float, float, float]] = []
        required_total = 0.0

        for supply_k, requirement in zip(
            supplies,
            self._discharge_requirements(store.protected_humidity_ratio),
        ):
            minimum_duty = requirement.duty_j_per_kg_air
            turbine_pressure = requirement.turbine_pressure_pa
            ratio, achievable = water_ratio_for_duty(
                minimum_duty, current, supply_k, c.interheater_pressure_drop,
                WORKING_FLUID, c.heat_exchanger_ntu, MAX_BRANCH_WATER_AIR_RATIO,
                relative_tolerance=self._duty_relative_tolerance,
            )
            if minimum_duty > 0.0 and achievable < minimum_duty * (1.0 - 2e-6):
                return float("inf"), None
            heater = heat_air_with_water(
                current, supply_k, ratio, c.interheater_pressure_drop,
                WORKING_FLUID, c.heat_exchanger_ntu,
                # A stage with zero moisture-safe duty legitimately gets an
                # empty branch in the minimum-duty design.
                allow_zero_flow=True,
            )
            if minimum_duty > 1e-8 and heater.heat_exchanger is None:
                return float("inf"), None
            cycle.processes.append(heater)
            hx = heater.heat_exchanger
            if hx is None:
                branches.append((0.0, supply_k, 0.0))
            else:
                if (
                    enforce_coolant_freezing
                    and hx.water_outlet_temperature_k
                    < c.coolant_minimum_temperature_k - TEMPERATURE_LIMIT_TOLERANCE_K
                ):
                    return float("inf"), None
                branches.append((
                    ratio,
                    hx.water_outlet_temperature_k,
                    hx.duty_j_per_kg_air,
                ))
            required_total += ratio

            turbine = expand(
                heater.outlet, turbine_pressure, c.expander_efficiency, WORKING_FLUID
            )
            cycle.processes.append(turbine)
            current = turbine.outlet

        if required_total <= 0.0:
            return 0.0, None
        returned_mean = sum(r * t for r, t, _ in branches) / required_total
        # The reported supply is the hottest one any stage sees: it is what the
        # upstream district-heating exchanger has to leave behind.
        return required_total, _DischargeDesign(
            cycle, tuple(branches), max(supplies), returned_mean
        )

    def _light_discharge_at_supply(
        self,
        store: _ThermalStore,
        supplies: list[float],
        *,
        enforce_coolant_freezing: bool = True,
    ) -> _LadderEvaluation | None:
        """Evaluate an LTHP ladder without constructing a complete ``Cycle``.

        The moisture-safe duty and outlet pressure are invariant, but the
        inverse heat exchanger reaches that duty only to its numerical
        tolerance.  Those tiny duty differences propagate through the next
        turbine and therefore belong to the exact residual seen by the legacy
        full-train solve.  This reduced path consequently advances the *real*
        air state after every exchanger and turbine.  It skips only reporting
        objects and the duplicate forward HX evaluation; the accepted root is
        still materialized once by the complete model.
        """

        c = self.config
        current = state_pt(self._p_storage, c.ambient_temperature_k, WORKING_FLUID)
        branches: list[tuple[float, float, float]] = []
        required_total = 0.0
        for supply_k, requirement in zip(
            supplies,
            self._discharge_requirements(store.protected_humidity_ratio),
        ):
            minimum_duty = requirement.duty_j_per_kg_air
            ratio, achievable = water_ratio_for_duty(
                minimum_duty,
                current,
                supply_k,
                c.interheater_pressure_drop,
                WORKING_FLUID,
                c.heat_exchanger_ntu,
                MAX_BRANCH_WATER_AIR_RATIO,
                relative_tolerance=self._duty_relative_tolerance,
            )
            if minimum_duty > 0.0 and achievable < minimum_duty * (1.0 - 2e-6):
                return None
            heater_pressure = current.pressure_pa * (1.0 - c.interheater_pressure_drop)
            if ratio <= 0.0:
                branches.append((0.0, supply_k, 0.0))
                heater_outlet = state_ph(
                    heater_pressure, current.enthalpy_j_per_kg, WORKING_FLUID
                )
            else:
                water_outlet_k = supply_k - achievable / (
                    ratio * WATER_CP_J_PER_KGK
                )
                if (
                    enforce_coolant_freezing
                    and water_outlet_k
                    < c.coolant_minimum_temperature_k
                    - TEMPERATURE_LIMIT_TOLERANCE_K
                ):
                    return None
                branches.append((ratio, water_outlet_k, achievable))
                heater_outlet = state_ph(
                    heater_pressure,
                    current.enthalpy_j_per_kg + achievable,
                    WORKING_FLUID,
                )
            required_total += ratio
            current = expand(
                heater_outlet,
                requirement.turbine_pressure_pa,
                c.expander_efficiency,
                WORKING_FLUID,
            ).outlet

        if required_total <= 0.0:
            return None
        returned_mean = sum(
            ratio * temperature for ratio, temperature, _ in branches
        ) / required_total
        return _LadderEvaluation(
            required_ratio=required_total,
            returns=tuple(branches),
            supplies=tuple(supplies),
            returned_mean_k=returned_mean,
        )

    def _discharge_with_ratios(
        self, store: _ThermalStore, ratios: list[float]
    ) -> _DischargeDesign:
        """Run the absorbing turbine train for an explicit conserved-water split.

        With the heat user bypassed, every stage draws from the one mixed
        hot-store temperature and ``ratios`` is conserved globally.

        A branch may legitimately carry NO water.  A stage whose moisture-safe
        duty is already zero - the expansion stays above the anti-icing
        envelope on its own - needs no reheat, and its exchanger degenerates
        into the pressure drop it would impose anyway.  Rejecting a zero ratio
        outright made every surplus-allocation candidate infeasible as soon as
        one stage had no duty, because the candidates are built by adding the
        surplus to ONE stage and leaving the others at their minimum.  The
        plant then fell through to the bypass path and dumped the whole surplus
        at E-303 - a large, silent loss caused purely by a guard disagreeing
        with the candidate generator that feeds it.
        """
        c = self.config
        if len(ratios) != c.expander_stages or any(ratio < 0.0 for ratio in ratios):
            raise ValueError("interheater branch flows must be non-negative")
        if sum(ratios) <= 0.0:
            raise ValueError("the interheater train needs some coolant allocation")

        current = state_pt(self._p_storage, c.ambient_temperature_k, WORKING_FLUID)
        cycle = Cycle("discharging", current)
        branches: list[tuple[float, float, float]] = []
        supplies = self._level_supplies(store)
        for supply_k, ratio, requirement in zip(
            supplies,
            ratios,
            self._discharge_requirements(store.protected_humidity_ratio),
        ):
            minimum_duty = requirement.duty_j_per_kg_air
            turbine_pressure = requirement.turbine_pressure_pa
            heater = heat_air_with_water(
                current,
                supply_k,
                ratio,
                c.interheater_pressure_drop,
                WORKING_FLUID,
                c.heat_exchanger_ntu,
                allow_zero_flow=True,
            )
            hx = heater.heat_exchanger
            if hx is None or hx.duty_j_per_kg_air <= 0.0:
                if minimum_duty > 0.0 or ratio > 0.0:
                    raise ValueError("the hot tank cannot deliver useful turbine reheat")
                # A dry branch on a stage that needs no heat: the exchanger is
                # just its pressure drop, and it contributes nothing to the
                # returns except the flow it does not carry.
                cycle.processes.append(heater)
                branches.append((0.0, supply_k, 0.0))
                turbine = expand(
                    heater.outlet,
                    turbine_pressure,
                    c.expander_efficiency,
                    WORKING_FLUID,
                )
                if (
                    turbine.outlet.temperature_k
                    < minimum_wet_expander_temperature_k(
                        turbine.outlet.pressure_pa,
                        store.protected_humidity_ratio,
                    )
                    - TEMPERATURE_LIMIT_TOLERANCE_K
                ):
                    raise ValueError(
                        "finite interheaters cannot reach the wet-expander "
                        "anti-icing lower envelope"
                    )
                cycle.processes.append(turbine)
                current = turbine.outlet
                continue
            if (
                hx.water_outlet_temperature_k
                < c.coolant_minimum_temperature_k - TEMPERATURE_LIMIT_TOLERANCE_K
            ):
                raise ValueError(
                    "an interheater return is below the selected coolant "
                    "freezing point"
                )
            cycle.processes.append(heater)
            branches.append(
                (ratio, hx.water_outlet_temperature_k, hx.duty_j_per_kg_air)
            )

            turbine = expand(
                heater.outlet,
                turbine_pressure,
                c.expander_efficiency,
                WORKING_FLUID,
            )
            local_minimum_k = minimum_wet_expander_temperature_k(
                turbine.outlet.pressure_pa,
                store.protected_humidity_ratio,
            )
            if (
                turbine.outlet.temperature_k
                < local_minimum_k - TEMPERATURE_LIMIT_TOLERANCE_K
            ):
                raise ValueError(
                    "finite interheaters cannot reach the wet-expander "
                    "anti-icing lower envelope"
                )
            cycle.processes.append(turbine)
            current = turbine.outlet

        total_ratio = sum(ratios)
        returned_mean = sum(r * t for r, t, _ in branches) / total_ratio
        return _DischargeDesign(
            cycle,
            tuple(branches),
            max(supplies),
            returned_mean,
        )

    def _discharge_absorbing(self, store: _ThermalStore) -> _DischargeDesign:
        """Allocate the complete inventory to maximize turbine work.

        First calculate the minimum branch flows that satisfy the wet-expander
        anti-icing envelope at the mixed hot-store temperature.
        The remaining conserved flow is then tested as additional conductance
        at every possible stage, plus an even distribution.  The candidate
        giving the greatest real multi-stage expansion work wins.  Thus branch
        flows are chosen by the plant objective rather than by T-Q profile
        matching.

        The complete surplus is globally conserved because there is one hot
        store: the spare is the inventory the moisture-safe minimum leaves
        unused.
        """
        supplies = self._level_supplies(store)
        minimum_total, minimum_design = self._discharge_at_supply(
            store,
            supplies,
            enforce_coolant_freezing=False,
        )
        if minimum_design is None or minimum_total > store.total_ratio + 2e-6:
            raise ValueError(
                "the conserved coolant inventory cannot provide the minimum "
                "moisture-safe interheater duties"
            )

        minimum = [branch[0] for branch in minimum_design.returns]
        drawn = sum(minimum)
        if drawn > store.total_ratio + 2e-6:
            raise ValueError(
                "the mixed hot store cannot supply the moisture-safe duties"
            )
        spare = max(0.0, store.total_ratio - drawn)

        candidates: list[list[float]] = []
        # Spread the store's spare evenly over all stages.
        candidates.append([
            ratio + spare / len(minimum) for ratio in minimum
        ])
        # ...or give the spare entirely to one stage.
        for recipient in range(len(minimum)):
            candidate = list(minimum)
            candidate[recipient] += spare
            candidates.append(candidate)

        feasible: list[_DischargeDesign] = []
        for ratios in candidates:
            try:
                feasible.append(self._discharge_with_ratios(store, ratios))
            except ValueError:
                continue
        if feasible:
            return min(feasible, key=lambda design: design.cycle.work_j_per_kg)

        # Last-resort physical dispatch.  When the conserved inventory holds
        # more heat than the turbines can absorb (the wet-expander envelope or
        # the turbine-inlet cap rejects every absorbing allocation), the
        # turbines receive only their moisture-safe minimum duty and the
        # unabsorbable water bypasses the interheaters straight into the cold
        # return. E-303 is heat-only: it cannot reject this surplus. The outer
        # cold-loop closure must still find a consistent tank temperature,
        # including standing losses when present. A valid discharge alone is
        # not a feasible closed plant.
        minimum_total, fallback = self._discharge_at_supply(store, supplies)
        if fallback is None or minimum_total > store.total_ratio + 2e-6:
            if not self._preserve_search_path:
                restored = simplex_feasible(
                    lambda ratios: self._allocation_violation(store, ratios),
                    store.total_ratio, self.config.expander_stages,
                )
                if restored is not None:
                    return self._discharge_with_ratios(store, restored)
            raise ValueError(
                "no conserved interheater-flow allocation satisfies the "
                "wet-expander lower envelope and turbine-inlet limit, and the "
                "minimum moisture-safe dispatch cannot absorb the surplus "
                "either"
            )
        # Any unabsorbable spare bypasses at the hot-store temperature.
        bypassed = (
            ((spare, store.hot_available_k, 0.0),) if spare > 0.0 else ()
        )
        returns = fallback.returns + bypassed
        returned_mean = sum(
            ratio * temperature for ratio, temperature, _ in returns
        ) / store.total_ratio
        return _DischargeDesign(
            fallback.cycle,
            returns,
            max(supplies),
            returned_mean,
        )

    def _allocation_violation(self, store: _ThermalStore, ratios: list[float]) -> float:
        """Continuous constraint merit for trial allocations, never an acceptance.

        Forward thermodynamics are identical to _discharge_with_ratios. The
        squared negative coolant/wet margins guide simplex feasibility
        restoration; the original guarded routine validates its answer.
        """
        c = self.config
        current = state_pt(self._p_storage, c.ambient_temperature_k, WORKING_FLUID)
        penalty = 0.0
        for ratio, requirement in zip(ratios, self._discharge_requirements(store.protected_humidity_ratio)):
            heater = heat_air_with_water(current, store.hot_available_k, ratio,
                                         c.interheater_pressure_drop, WORKING_FLUID,
                                         c.heat_exchanger_ntu, allow_zero_flow=True)
            hx = heater.heat_exchanger
            if hx is None or hx.duty_j_per_kg_air <= 0:
                if requirement.duty_j_per_kg_air > 0 or ratio > 0:
                    penalty += 1.0 + max(0., current.temperature_k-store.hot_available_k)**2
            else:
                penalty += max(0., c.coolant_minimum_temperature_k
                               - TEMPERATURE_LIMIT_TOLERANCE_K - hx.water_outlet_temperature_k)**2
            current = expand(heater.outlet, requirement.turbine_pressure_pa,
                             c.expander_efficiency, WORKING_FLUID).outlet
            floor = minimum_wet_expander_temperature_k(current.pressure_pa, store.protected_humidity_ratio)
            penalty += max(0., floor-TEMPERATURE_LIMIT_TOLERANCE_K-current.temperature_k)**2
        return penalty

    def _discharge_adiabatic(
        self, store: _ThermalStore, returned_mean_k: float
    ) -> _DischargeDesign:
        """Close the discharge water side for the selected design.

        Minimum-duty design: the E-304 extraction ladder fixes one supply per
        stage. Absorption design: the user is bypassed and conserved inventory is allocated for
        maximum real expansion work.  In both, every kilogram passes through
        exactly one interheater core and the outer root closes the coolant loop.
        """
        if self._absorbs_surplus():
            return self._discharge_absorbing(store)

        required, evaluation = self._discharge_adiabatic_unchecked(
            store, returned_mean_k
        )
        if evaluation is None:
            raise ValueError(
                "finite interheaters cannot reach the selected expander outlet temperature"
            )
        if abs(required - store.total_ratio) > MAX_WATER_MASS_CLOSURE_ERROR:
            raise ValueError("interheater branch flows do not close the stored-water mass balance")
        design = self._materialize_ladder(store, evaluation)
        full_required = sum(ratio for ratio, _, _ in design.returns)
        if abs(full_required - store.total_ratio) > MAX_WATER_MASS_CLOSURE_ERROR:
            raise ValueError(
                "materialized interheater flows do not close the stored-water mass balance"
            )
        returned_mean = sum(r * t for r, t, _ in design.returns) / store.total_ratio
        return replace(design, returned_mean_k=returned_mean)

    def _discharge_adiabatic_unchecked(
        self, store: _ThermalStore, returned_mean_k: float
    ) -> tuple[float, _LadderEvaluation | None]:
        """Minimum-duty discharge on the temperature ladder, mass balance UNCHECKED.

        Split out because the coolant-loop root has to evaluate exactly the
        construction it is going to accept.  Evaluating the residual on one
        averaged supply and then assembling the design on the ladder closes a
        plant that was never solved.
        """
        required, evaluation, _ = self._solve_extraction_margin(
            store, returned_mean_k
        )
        return required, evaluation

    def _materialize_ladder(
        self, store: _ThermalStore, evaluation: _LadderEvaluation
    ) -> _DischargeDesign:
        """Build the complete air train once from the accepted inverse-HX ratios.

        Re-running :func:`water_ratio_for_duty` here would solve the same
        inverse once more for reporting.  The accepted evaluation already owns
        those exact ratios, so only the forward exchangers and the ``Cycle``
        value objects are materialized.
        """

        c = self.config
        current = state_pt(self._p_storage, c.ambient_temperature_k, WORKING_FLUID)
        cycle = Cycle("discharging", current)
        branches: list[tuple[float, float, float]] = []
        for supply_k, light_branch, requirement in zip(
            evaluation.supplies,
            evaluation.returns,
            self._discharge_requirements(store.protected_humidity_ratio),
        ):
            ratio = light_branch[0]
            heater = heat_air_with_water(
                current,
                supply_k,
                ratio,
                c.interheater_pressure_drop,
                WORKING_FLUID,
                c.heat_exchanger_ntu,
                allow_zero_flow=True,
            )
            hx = heater.heat_exchanger
            if requirement.duty_j_per_kg_air > 1e-8 and hx is None:
                raise ValueError(
                    "the accepted ladder cannot be materialized by the complete "
                    "interheater model"
                )
            if hx is None:
                branches.append((0.0, supply_k, 0.0))
            else:
                if (
                    hx.water_outlet_temperature_k
                    < c.coolant_minimum_temperature_k
                    - TEMPERATURE_LIMIT_TOLERANCE_K
                ):
                    raise ValueError(
                        "the materialized interheater return violates the coolant "
                        "freezing limit"
                    )
                branches.append((
                    ratio,
                    hx.water_outlet_temperature_k,
                    hx.duty_j_per_kg_air,
                ))
            cycle.processes.append(heater)
            turbine = expand(
                heater.outlet,
                requirement.turbine_pressure_pa,
                c.expander_efficiency,
                WORKING_FLUID,
            )
            cycle.processes.append(turbine)
            current = turbine.outlet

        returned_mean = sum(
            ratio * temperature for ratio, temperature, _ in branches
        ) / evaluation.required_ratio
        return _DischargeDesign(
            cycle=cycle,
            returns=tuple(branches),
            supply_k=max(evaluation.supplies),
            returned_mean_k=returned_mean,
            stage_supplies=evaluation.supplies,
        )

    def _extraction_demands(self, store: _ThermalStore) -> list[float]:
        """Non-increasing supply demand for each extraction on E-304 [K].

        The raw quantity is the air temperature each stage's interheater has to
        produce. It normally falls along the expansion train, because every
        stage expands from a lower pressure onto the same anti-icing envelope -
        which is exactly why one common tank temperature is a poor supply for
        the tail stages, and why staging the trunk is worth a body.

        It does NOT always fall. Measured on the 300 bar eight-stage train, the
        second stage demands 64.45 °C against the first stage's 63.34 °C,
        because the first expansion starts from stored air at ambient
        temperature while later ones start from a turbine outlet sitting on the
        icing floor.

        A trunk that is progressively withdrawn can only ever get COLDER along
        its length, so it physically cannot hand a later stage a hotter supply
        than an earlier one. The demand profile is therefore raised to its
        SUFFIX MAXIMUM: each extraction is placed at the hottest demand still
        ahead of it. Where that binds, the two stages share one nozzle and the
        zone between them carries no duty - which is the honest picture, not a
        rejection. Where the profile already falls, the envelope is the identity
        and nothing changes.
        """
        demands = [
            requirement.heater_outlet_temperature_k
            for requirement in self._discharge_requirements(
                store.protected_humidity_ratio
            )
        ]
        envelope: list[float] = []
        running = -float("inf")
        for demand in reversed(demands):
            running = max(running, demand)
            envelope.append(running)
        envelope.reverse()
        return envelope

    def _solve_extraction_margin(
        self, store: _ThermalStore, returned_mean_k: float
    ) -> tuple[float, _LadderEvaluation | None, list[float]]:
        """Root the common extraction margin so the bleeds consume the inventory.

        Every stage is fed from its own extraction on E-304, placed a single
        common margin above the air temperature that stage has to produce::

            T_extraction,g = T_demand,g + m

        The inverse finite-NTU solve makes the flow a stage needs FALL as its
        supply gets hotter, so the total demanded flow is monotone decreasing in
        ``m``. One safeguarded root therefore closes exact coolant mass, exactly
        as the former equal-drop cascade did, and at the same cost: the
        expensive object is the light discharge train, and this needs no more of
        them.

        Choosing the margin rather than a uniform temperature step is the whole
        point of the device. Uniform steps ignore what each stage actually
        demands; a common margin lays the trunk's cooling curve directly on top
        of the demand profile, which is the curve-matching argument for staged
        extraction and the reason the tail stages stop being fed 40-odd kelvin
        hotter than they can use.

        The margin is bounded above by the hot store itself: the first
        extraction is the trunk inlet, so ``T_demand,0 + m`` can never exceed
        the available store temperature. The second argument is retained for
        private API compatibility; branch-selective recovery means a guessed
        mixed return is not a state variable.
        """
        if self._recovering:
            return self._solve_extraction_margin_recovery(store)
        del returned_mean_k
        demands = self._extraction_demands(store)
        hot_k = store.hot_available_k

        # The trunk enters E-304 at the FIRST extraction, so the hottest demand
        # plus the margin is the trunk inlet and the store has to reach it.
        span = hot_k - max(demands)
        if span <= 0.0:
            raise HeatOfftakeTemperatureError(
                "the mixed hot store is not warmer than the hottest interheater "
                f"demand ({max(demands) - 273.15:.2f} °C): no extraction margin "
                "exists, so E-304 cannot feed the first expansion stage"
            )

        def evaluate(
            margin: float,
        ) -> tuple[float, _LadderEvaluation | None, list[float]]:
            supplies = [demand + margin for demand in demands]
            evaluation = self._light_discharge_at_supply(store, supplies)
            required = (
                evaluation.required_ratio if evaluation is not None else float("inf")
            )
            return required, evaluation, supplies

        # A vanishing margin needs unbounded flow, so the cold endpoint is the
        # over-inventory side by construction; the hot endpoint is the store.
        widest = evaluate(span)
        if widest[1] is not None and widest[0] > store.total_ratio + 2e-6:
            # Even feeding every stage from the very top of the store leaves the
            # interheaters short: this inventory cannot be consumed at all.
            return widest

        # Warm-start at the last accepted normalized margin.  Neighbouring
        # cold-loop and inventory candidates move this root only slightly.
        seed = self._extraction_margin_fraction_seed
        seeded = (
            evaluate(seed * span)
            if seed is not None and 0.0 < seed < 1.0
            else None
        )
        if (
            seeded is not None
            and seeded[1] is not None
            and abs(seeded[0] - store.total_ratio)
            <= WATER_MASS_CLOSURE_SEARCH_ERROR
        ):
            return seeded

        # Smooth continuation fast path.  Required flow is close to inversely
        # proportional to the driving force, so a secant on the RECIPROCAL mass
        # residual normally converges in 2-4 new trains.  The safeguarded
        # bracket below is the legacy fallback, not an infeasibility proof.
        # Recovery separates undefined duty from return-temperature rejection.
        if seeded is not None and seeded[1] is not None:
            x0 = seed * span
            p0 = seeded
            f0 = 1.0 / p0[0] - 1.0 / store.total_ratio
            # Over-supplied means the margin must shrink, and vice versa.
            direction = -1.0 if p0[0] < store.total_ratio else 1.0
            x1 = min(span, max(0.0, x0 + direction * 0.002 * span))
            p1 = evaluate(x1) if abs(x1 - x0) > 1e-15 else None
            if p1 is not None and p1[1] is not None:
                f1 = 1.0 / p1[0] - 1.0 / store.total_ratio
                for _ in range(7):
                    if (
                        abs(p1[0] - store.total_ratio)
                        <= WATER_MASS_CLOSURE_SEARCH_ERROR
                    ):
                        self._extraction_margin_fraction_seed = x1 / span
                        return p1
                    denominator = f1 - f0
                    if abs(denominator) < 1e-30:
                        break
                    x2 = x1 - f1 * (x1 - x0) / denominator
                    if not 0.0 < x2 < span:
                        break
                    p2 = evaluate(x2)
                    if p2[1] is None:
                        break
                    x0, p0, f0 = x1, p1, f1
                    x1, p1 = x2, p2
                    f1 = 1.0 / p1[0] - 1.0 / store.total_ratio

        # Bracket: required flow DECREASES with the margin, so the small-margin
        # end over-supplies and the wide end under-supplies.  ``left`` always
        # holds the over-inventory side.
        left_x = 0.0
        left_probe = evaluate(0.0)
        right_x, right_probe = span, widest
        if seeded is not None and seeded[1] is not None:
            seed_x = seed * span
            if seeded[0] > store.total_ratio:
                left_x, left_probe = seed_x, seeded
            else:
                right_x, right_probe = seed_x, seeded

        if left_probe[1] is not None and left_probe[0] < store.total_ratio:
            # Flow demand never rises to the inventory even at zero margin:
            # there is more coolant than the interheaters can ever take.
            raise HeatOfftakeTemperatureError(
                "the conserved coolant inventory is larger than the minimum-duty "
                "interheater extractions can consume at any margin above their "
                "own temperature demands"
            )

        # An infeasible narrow endpoint has no finite residual.  Widen only
        # until a finite over-inventory point brackets the root; this work is
        # needed only near a heat-exchanger feasibility boundary.
        if left_probe[1] is None:
            for _ in range(CASCADE_FEASIBILITY_BISECTIONS):
                middle_x = 0.5 * (left_x + right_x)
                middle_probe = evaluate(middle_x)
                if middle_probe[1] is None:
                    left_x = middle_x
                elif middle_probe[0] >= store.total_ratio:
                    left_x, left_probe = middle_x, middle_probe
                    break
                else:
                    right_x, right_probe = middle_x, middle_probe
            else:
                return right_probe

        f_left = 1.0 / left_probe[0] - 1.0 / store.total_ratio
        f_right = (
            1.0 / right_probe[0] - 1.0 / store.total_ratio
            if right_probe[1] is not None
            else 1.0 / store.total_ratio
        )
        best = left_probe
        for _ in range(CASCADE_ROOT_REFINEMENTS):
            trial_x = trial_point(left_x, f_left, right_x, f_right)
            probe = evaluate(trial_x)
            if probe[1] is None:
                # Infeasible interiors sit on the narrow side of this root.
                left_x = trial_x
                continue
            residual = probe[0] - store.total_ratio
            if abs(residual) <= WATER_MASS_CLOSURE_SEARCH_ERROR:
                self._extraction_margin_fraction_seed = trial_x / span
                return probe
            moved_high = residual <= 0.0
            f_probe = 1.0 / probe[0] - 1.0 / store.total_ratio
            if moved_high:
                right_x, right_probe = trial_x, probe
                f_left, f_right = illinois_residuals(
                    f_left, f_probe, moved_high=True
                )
            else:
                left_x, left_probe = trial_x, probe
                best = probe
                f_left, f_right = illinois_residuals(
                    f_probe, f_right, moved_high=False
                )

        self._extraction_margin_fraction_seed = left_x / span
        return best

    def _solve_extraction_margin_recovery(
        self, store: _ThermalStore,
    ) -> tuple[float, _LadderEvaluation, list[float]]:
        """Separate the mass equation from coolant-return inequalities.

        With freezing *excluded from trial evaluation only*, inverse-HX mass
        decreases with increasing supply. A duty-inaccessible lower endpoint
        is distinct from a cold return at the upper endpoint. Root the mass
        equation first, then enforce the unchanged return-temperature bound.
        Thus an invalid hot endpoint never deletes a valid interior interval.
        No continuation state is used by this recovery path.
        """
        demands = self._extraction_demands(store)
        span = store.hot_available_k - max(demands)
        if span <= 0:
            raise ValueError("mixed hot store is below the hottest interheater demand")
        cache: dict[float, _LadderEvaluation | None] = {}
        def evaluate(margin: float) -> _LadderEvaluation | None:
            if margin not in cache:
                cache[margin] = self._light_discharge_at_supply(
                    store, [d + margin for d in demands], enforce_coolant_freezing=False,
                )
            return cache[margin]
        right = evaluate(span)
        if right is None or right.required_ratio > store.total_ratio + WATER_MASS_CLOSURE_SEARCH_ERROR:
            raise SearchUnresolved("no mass bracket at the available hot-store temperature")
        low, high = 0.0, span
        left = evaluate(low)
        if left is None:
            for _ in range(64):
                middle = .5 * (low + high)
                trial = evaluate(middle)
                if trial is None:
                    low = middle
                elif trial.required_ratio >= store.total_ratio:
                    low, left = middle, trial
                    break
                else:
                    high, right = middle, trial
            if left is None:
                raise SearchUnresolved("duty boundary reached without a finite mass bracket")
        if left.required_ratio < store.total_ratio:
            raise SearchUnresolved("minimum-duty ladder cannot bracket the conserved inventory")
        def mass(margin: float) -> float:
            trial = evaluate(margin)
            if trial is None:
                raise SearchUnresolved("undefined duty inside extraction mass bracket")
            return trial.required_ratio - store.total_ratio
        root = bracketed_root(mass, low, high,
                              residual_tolerance=WATER_MASS_CLOSURE_SEARCH_ERROR)
        design = evaluate(root)
        assert design is not None
        if any(t < self.config.coolant_minimum_temperature_k - TEMPERATURE_LIMIT_TOLERANCE_K
               for _, t, _ in design.returns):
            raise ValueError("mass-closed interheater return is below the coolant freezing point")
        return design.required_ratio, design, list(design.supplies)

    def _build_extraction_exchanger(
        self,
        store: _ThermalStore,
        design: _DischargeDesign,
        return_inlet_k: float,
    ) -> ExtractionExchangerSummary:
        """Solve E-304 zone by zone and return its complete solved state.

        The trunk enters at the first extraction carrying the whole inventory
        and is withdrawn stage by stage until it is exhausted at the last one,
        so its heat-capacity rate is a STEP function of position. A single
        whole-body LMTD or effectiveness would therefore be wrong, and wrong in
        no predictable direction. The body is instead cut at the extractions:
        inside one zone both capacity rates are constant, which is exactly the
        condition ordinary counter-current effectiveness needs.

        The cold side is the plant's own mixed coolant return, carrying the full
        inventory through every zone. It is therefore always the C_max stream
        and the trunk is always C_min.

        Two things are checked and never assumed:

        * the pinch, at EVERY node rather than only at the two ends of the body.
          With a variable trunk capacity rate the tightest approach migrates
          inside, so terminal-only checking would miss a crossed profile;
        * the finite area, as the same required-vs-available effectiveness
          statement every other exchanger in this model is held to.

        A zone that fails either check makes the whole candidate infeasible.
        That is the honest response and it is also self-correcting: less
        inventory needs a wider margin, which lifts the whole ladder away from
        the return it is exchanging against, so the outer inventory search walks
        out of a pinched region on its own.
        """
        c = self.config
        inventory = store.total_ratio
        cold_capacity = inventory * WATER_CP_J_PER_KGK
        extractions = [
            (branch[0], supply_k)
            for supply_k, branch in zip(design.stage_supplies, design.returns)
        ]
        temperatures = [supply_k for _, supply_k in extractions]
        flows = [ratio for ratio, _ in extractions]

        # Guard, not a physical constraint: the ladder is built from a
        # non-increasing envelope, so this can only fire on a construction bug.
        for earlier, later in zip(temperatures, temperatures[1:]):
            if later > earlier + 1e-9:
                raise ValueError(
                    "the E-304 extraction ladder is not monotone: a later "
                    "expansion stage was placed hotter than an earlier one, so "
                    "the trunk would have to be reheated inside the body"
                )

        # Trunk flow crossing the zone BELOW extraction g is the suffix sum of
        # everything still to be withdrawn.
        remaining = inventory
        zone_flows: list[float] = []
        for ratio in flows[:-1]:
            remaining -= ratio
            zone_flows.append(remaining)

        # March from the cold end, where the return enters: only there is the
        # cold-side temperature known before the duties are.
        duties = [
            flow * WATER_CP_J_PER_KGK * (hot - cold)
            for flow, hot, cold in zip(zone_flows, temperatures, temperatures[1:])
        ]
        cold_side = [return_inlet_k]
        for duty in reversed(duties):
            cold_side.append(cold_side[-1] + duty / cold_capacity)
        cold_side.reverse()          # cold_side[g] is the return at extraction g

        segments: list[ExtractionSegment] = []
        for index, (flow, duty) in enumerate(zip(zone_flows, duties)):
            trunk_inlet_k = temperatures[index]
            trunk_outlet_k = temperatures[index + 1]
            return_outlet_k = cold_side[index]
            return_zone_inlet_k = cold_side[index + 1]
            capacity_ratio = flow / inventory if inventory > 0.0 else 0.0
            driving_force = trunk_inlet_k - return_zone_inlet_k
            hot_capacity = flow * WATER_CP_J_PER_KGK
            if duty > 0.0 and (driving_force <= 0.0 or hot_capacity <= 0.0):
                raise ValueError(
                    "an E-304 zone has no positive inlet temperature driving "
                    f"force: trunk enters at {trunk_inlet_k - 273.15:.2f} °C "
                    f"against a return at {return_zone_inlet_k - 273.15:.2f} °C"
                )
            required = (
                duty / (hot_capacity * driving_force) if duty > 0.0 else 0.0
            )
            available = counterflow_effectiveness(
                c.extraction_exchanger_ntu, capacity_ratio
            )
            if required > available + 2e-6:
                raise ValueError(
                    "the E-304 exchanger class is too small in the zone between "
                    f"{trunk_inlet_k - 273.15:.1f} and "
                    f"{trunk_outlet_k - 273.15:.1f} °C: required "
                    f"effectiveness={required:.4f}, available={available:.4f} "
                    f"at NTU={c.extraction_exchanger_ntu:g}"
                )
            segment = ExtractionSegment(
                index=index,
                trunk_flow_per_kg_air=flow,
                trunk_inlet_temperature_k=trunk_inlet_k,
                trunk_outlet_temperature_k=trunk_outlet_k,
                return_inlet_temperature_k=return_zone_inlet_k,
                return_outlet_temperature_k=return_outlet_k,
                duty_j_per_kg_air=duty,
                capacity_ratio=capacity_ratio,
                required_effectiveness=required,
                available_effectiveness=available,
            )
            if segment.terminal_difference_k <= 0.0 and duty > 0.0:
                raise ValueError(
                    "the E-304 temperature profiles cross: the trunk falls to "
                    f"{trunk_outlet_k - 273.15:.2f} °C while the coolant return "
                    f"it is heating is already at "
                    f"{return_zone_inlet_k - 273.15:.2f} °C. The extraction "
                    "ladder reaches below its own cold side"
                )
            segments.append(segment)

        recuperated = sum(duties)
        t0 = c.ambient_temperature_k
        # Internal recuperation: the trunk's loss and the return's gain are both
        # inside the plant, so what is destroyed is the difference between them.
        trunk_exergy_drop = sum(
            flow * (
                water_exergy(hot, t0) - water_exergy(cold, t0)
            )
            for flow, hot, cold in zip(zone_flows, temperatures, temperatures[1:])
        )
        return_exergy_gain = inventory * (
            water_exergy(cold_side[0], t0) - water_exergy(return_inlet_k, t0)
        )
        return ExtractionExchangerSummary(
            margin_k=(
                temperatures[0] - self._extraction_demands(store)[0]
                if temperatures
                else 0.0
            ),
            exchanger_ntu=c.extraction_exchanger_ntu,
            trunk_inlet_temperature_k=temperatures[0],
            trunk_outlet_temperature_k=temperatures[-1],
            return_inlet_temperature_k=return_inlet_k,
            return_outlet_temperature_k=cold_side[0],
            total_water_mass_ratio=inventory,
            recuperated_heat_j_per_kg_air=recuperated,
            extraction_temperatures_k=tuple(temperatures),
            extraction_mass_ratios=tuple(flows),
            segments=tuple(segments),
            minimum_terminal_difference_k=min(
                (segment.terminal_difference_k for segment in segments),
                default=0.0,
            ),
            maximum_required_effectiveness=max(
                (segment.required_effectiveness for segment in segments),
                default=0.0,
            ),
            minimum_effectiveness_margin=min(
                (
                    segment.available_effectiveness - segment.required_effectiveness
                    for segment in segments
                ),
                default=0.0,
            ),
            exergy_destruction_j_per_kg_air=max(
                0.0, trunk_exergy_drop - return_exergy_gain
            ),
        )

    def _recuperated_heat_j_per_kg_air(
        self,
        inventory: float,
        supplies: tuple[float, ...] | list[float],
        returns: tuple[tuple[float, float, float], ...],
    ) -> float:
        """Duty E-304 moves from the trunk into the coolant return [J/kg-air].

        The trunk crosses the zone below extraction ``g`` carrying the suffix
        sum of everything still to be withdrawn, and cools by the gap to the
        next extraction. Summing those zone duties is the whole recuperation.

        The coolant-loop residual needs this number on EVERY trial, so it is
        computed from the same suffix sums the reporting builder uses but
        without the per-zone effectiveness and pinch checks - those only the
        accepted candidate has to survive.

        The suffix is floored at zero. Exact mass closure is the job of
        :meth:`_solve_extraction_margin` and is already held to the one-joule
        budget by the time this runs; the floor only stops a root that bailed on
        iteration count from turning a small overdraw into a negative flow.
        """
        if inventory <= 0.0:
            return 0.0
        remaining = inventory
        recuperated = 0.0
        for branch, hot, cold in zip(returns, supplies, supplies[1:]):
            remaining = max(0.0, remaining - branch[0])
            recuperated += remaining * WATER_CP_J_PER_KGK * (hot - cold)
        return recuperated

    def _recuperated_tank_inlet_k(
        self,
        inventory: float,
        supplies: tuple[float, ...] | list[float],
        returns: tuple[tuple[float, float, float], ...],
        mixed_return_k: float,
    ) -> float:
        """Cold-tank inlet after E-304 has warmed the mixed coolant return [K].

        Without a heat user there is no E-304 and the mixed return reaches the
        tank unchanged.
        """
        if not self._dispatches_heat_to_user() or inventory <= 0.0:
            return mixed_return_k
        recuperated = self._recuperated_heat_j_per_kg_air(
            inventory, supplies, returns
        )
        return mixed_return_k + recuperated / (inventory * WATER_CP_J_PER_KGK)

    def _closed_loop_supply_temperature(
        self, store: _ThermalStore, returned_mean_k: float
    ) -> float:
        """Common post-tap temperature required by the selected discharge design.

        Minimum-duty design: the lowest `T_x` containing exactly the turbine
        heat demand, hence maximum surplus for the heat user, in one shot from
        the first law against the mixed return the loop is being closed on.
        Absorption design: there is no upstream exchanger, so the complete
        hot-tank stream reaches the interheaters at `T_hot`.  The branch-flow
        closure then decides how much of that available heat the finite-NTU
        exchangers can transfer while conserving the complete coolant inventory.
        """
        if self._absorbs_surplus():
            if store.hot_available_k <= returned_mean_k:
                raise ValueError(
                    "the hot tank is not warmer than the mixed coolant return, "
                    "so no surplus heat is available for turbine reheat"
                )
            return store.hot_available_k

        total_duty = sum(
            item.duty_j_per_kg_air
            for item in self._discharge_requirements(
                store.protected_humidity_ratio
            )
        )
        supply_k = returned_mean_k + total_duty / (
            store.total_ratio * WATER_CP_J_PER_KGK
        )
        if supply_k >= store.hot_available_k:
            raise ValueError(
                "hot tank cannot supply all interheater duties required by the selected "
                "expander outlet temperature"
            )
        return supply_k

    def _build_offtake_taps(
        self, store: _ThermalStore, discharge: _DischargeDesign
    ) -> tuple[OfftakeTap, ...]:
        """Size/check the single heat-user exchanger E-302 with one finite NTU class.

        The whole conserved inventory leaves the hot store and crosses this one
        counter-current body, which cools it from the available store
        temperature down to the FIRST extraction. Everything below that belongs
        to E-304 and is recuperated inside the plant instead of being sold, so
        the user is served entirely from the hot end of the store.

        The user flow follows from its requested supply/return span and the
        duty. The required effectiveness ``Q/[Cmin (Th,in-Tc,in)]`` must not
        exceed the effectiveness available from ``heat_user_exchanger_ntu`` and
        the local capacity ratio. This replaces the former endpoint-approach
        surrogate with the same NTU discipline used by every other exchanger in
        the model.
        """
        c = self.config
        hottest_available_k = store.hot_available_k
        if c.heat_user_supply_temperature_k >= hottest_available_k - 1e-9:
            raise HeatOfftakeTemperatureError(
                "the mixed hot store cannot deliver the requested heat-user supply "
                f"temperature ({c.heat_user_supply_temperature_c:.2f} °C): "
                f"the hottest plant coolant is only "
                f"{hottest_available_k - 273.15:.2f} °C"
            )
        # The trunk leaves the store at the available hot temperature and is
        # bled at the hottest extraction; E-302 sells exactly that band.
        outlet_k = max(discharge.stage_supplies)
        total_duty = store.total_ratio * WATER_CP_J_PER_KGK * (
            hottest_available_k - outlet_k
        )
        if total_duty <= 0.0:
            raise HeatOfftakeTemperatureError(
                "the turbines already need every kelvin the store holds, so the "
                "plant has no gap left to put a user exchanger in: the trunk "
                f"leaves the store at {hottest_available_k - 273.15:.2f} °C and "
                f"is bled at {discharge.supply_k - 273.15:.2f} °C. Lower the "
                "expander stage count, raise the storage pressure, or accept "
                "electricity only."
            )

        # (17): the user side is a slave. Its flow is whatever absorbs the duty
        # across the span its operator fixed; it is never a free variable here.
        user_water = total_duty / (
            WATER_CP_J_PER_KGK
            * (c.heat_user_supply_temperature_k - c.heat_user_return_temperature_k)
        )
        user_inlet_k = c.heat_user_return_temperature_k
        user_outlet_k = user_inlet_k + total_duty / (
            user_water * WATER_CP_J_PER_KGK
        )
        hot_capacity = store.total_ratio * WATER_CP_J_PER_KGK
        user_capacity = user_water * WATER_CP_J_PER_KGK
        c_min = min(hot_capacity, user_capacity)
        c_max = max(hot_capacity, user_capacity)
        q_max = c_min * (hottest_available_k - user_inlet_k)
        if q_max <= 0.0:
            raise HeatOfftakeTemperatureError(
                "the heat-user exchanger has no positive inlet temperature "
                "driving force"
            )
        required_effectiveness = total_duty / q_max
        available_effectiveness = counterflow_effectiveness(
            c.heat_user_exchanger_ntu, c_min / c_max
        )
        if required_effectiveness > available_effectiveness + 2e-6:
            raise HeatOfftakeTemperatureError(
                "the heat-user exchanger class is too small between "
                f"{hottest_available_k - 273.15:.1f} and "
                f"{outlet_k - 273.15:.1f} °C: required "
                f"effectiveness={required_effectiveness:.4f}, available="
                f"{available_effectiveness:.4f} at NTU="
                f"{c.heat_user_exchanger_ntu:g}"
            )
        return (OfftakeTap(
            plant_inlet_temperature_k=hottest_available_k,
            plant_outlet_temperature_k=outlet_k,
            plant_water_per_kg_air=store.total_ratio,
            user_inlet_temperature_k=user_inlet_k,
            user_outlet_temperature_k=user_outlet_k,
            user_water_per_kg_air=user_water,
            heat_j_per_kg_air=total_duty,
            required_effectiveness=required_effectiveness,
            available_effectiveness=available_effectiveness,
        ),)

    def _simulate_adiabatic(
        self, cold_k: float, total_inventory: float
    ) -> PlantResult:
        """One complete cycle for a trial cold-tank temperature."""
        charging, store = self._charge_adiabatic(cold_k, total_inventory)
        discharge = self._discharge_adiabatic(store, cold_k)
        return self._assemble_adiabatic(charging, store, discharge)

    def _assemble_adiabatic(
        self,
        charging: Cycle,
        store: _ThermalStore,
        discharge: _DischargeDesign,
    ) -> PlantResult:
        """Build the result from an already-solved charge/discharge pair.

        The coolant-loop root acceptance reuses this directly on the cycle its
        residual evaluation just computed, instead of paying for a second
        identical solve.

        The air train scavenges no ambient heat directly: every joule delivered
        to an interheater comes from the coolant. E-303 can nevertheless add
        zero-dead-state-exergy ambient heat to a selected cold return subgroup;
        that real external energy is reported on the result rather than hidden.
        """
        charging = self._annotate_exergy(charging)
        discharging = self._annotate_exergy(discharge.cycle)
        thermal, exergy, district, extraction = self._summarize_adiabatic(
            charging, discharging, store, discharge
        )
        # The validated charge train already ran the moisture analysis once;
        # its summary is reused, not recomputed.
        assert store.moisture is not None
        result = PlantResult(
            mode=self.config.mode.value,
            charging=charging,
            discharging=discharging,
            thermal_store=thermal,
            exergy=exergy,
            heat_offtake=district,
            extraction_exchanger=extraction,
            external_heat_input_j_per_kg=(
                thermal.cold_return_heat_absorbed_from_ambient_j_per_kg_air
            ),
            moisture=store.moisture,
        )
        return result

    # ---------------------------------------------------------------- D-CAES

    def _safe_diabatic_pressure_reduction(
        self,
        inlet,
        outlet_pressure_pa: float,
        protected_humidity_ratio: float,
    ) -> tuple[Process, ...]:
        """Take maximum safe turbine work, then throttle the remaining pressure.

        A complete turbine expansion is used whenever its outlet stays above
        the wet-rated anti-icing envelope: 10 degC in the permitted liquid
        region or local frost point plus 10 K in the dry sub-zero region.
        Otherwise the
        turbine stops at the lowest safe intermediate pressure and an
        isenthalpic valve completes the stage. If even an infinitesimal turbine
        drop starts below the protected boundary, the complete stage is
        throttled.
        """

        c = self.config

        def safe_margin(pressure_pa: float) -> float:
            candidate = expand(
                inlet, pressure_pa, c.expander_efficiency, WORKING_FLUID
            )
            return (
                candidate.outlet.temperature_k
                - minimum_wet_expander_temperature_k(
                    pressure_pa, protected_humidity_ratio
                )
            )

        full = expand(
            inlet, outlet_pressure_pa, c.expander_efficiency, WORKING_FLUID
        )
        if (
            full.outlet.temperature_k
            >= minimum_wet_expander_temperature_k(
                outlet_pressure_pa, protected_humidity_ratio
            )
            - TEMPERATURE_LIMIT_TOLERANCE_K
        ):
            return (full,)

        near_inlet_pressure = inlet.pressure_pa * (1.0 - 1e-9)
        if safe_margin(near_inlet_pressure) <= 0.0:
            valve = throttle(inlet, outlet_pressure_pa, WORKING_FLUID)
            if (
                valve.outlet.temperature_k
                < wet_expander_hard_floor_temperature_k(
                    outlet_pressure_pa, protected_humidity_ratio
                )
                - TEMPERATURE_LIMIT_TOLERANCE_K
            ):
                raise ValueError(
                    "even full isenthalpic throttling crosses the local pressure "
                    "wet-expander freezing/frost boundary before ambient trim "
                    "heat can be applied"
                )
            return (valve,)

        low_pressure = outlet_pressure_pa
        high_pressure = near_inlet_pressure
        # At low pressure the full expansion is unsafe; at high pressure it is
        # safe. Geometric bisection respects the logarithmic pressure scale.
        low_pressure, high_pressure = bisect(
            lambda pressure: safe_margin(pressure) >= 0.0,
            low_pressure,
            high_pressure,
            iterations=60,
            tolerance=1e-10,
            geometric=True,
        )

        turbine = expand(
            inlet, high_pressure, c.expander_efficiency, WORKING_FLUID
        )
        valve = throttle(turbine.outlet, outlet_pressure_pa, WORKING_FLUID)
        if (
            valve.outlet.temperature_k
            < wet_expander_hard_floor_temperature_k(
                outlet_pressure_pa, protected_humidity_ratio
            )
            - TEMPERATURE_LIMIT_TOLERANCE_K
        ):
            # A real-gas Joule-Thomson shift could make the two-step path less
            # safe than a full throttle. Prefer the safe, lower-work fallback.
            valve = throttle(inlet, outlet_pressure_pa, WORKING_FLUID)
            if (
                valve.outlet.temperature_k
                < wet_expander_hard_floor_temperature_k(
                    outlet_pressure_pa, protected_humidity_ratio
                )
                - TEMPERATURE_LIMIT_TOLERANCE_K
            ):
                raise ValueError(
                    "no fuel-free turbine/throttle split satisfies the local "
                    "wet-expander anti-icing envelope"
                )
            return (valve,)
        return turbine, valve

    def _simulate_diabatic(self) -> PlantResult:
        """Fuel-free D-CAES with ambient reheat and anti-icing throttling."""
        c = self.config
        current = state_pt(self._p_ambient, c.ambient_temperature_k, WORKING_FLUID)
        charging = Cycle("charging", current)
        ratio = self._compression_ratio()
        for stage in range(c.compressor_stages):
            p_out = self._p_storage / (1.0 - c.intercooler_pressure_drop) if stage == c.compressor_stages - 1 else current.pressure_pa * ratio
            compressor = compress(current, p_out, c.compressor_efficiency, WORKING_FLUID)
            charging.processes.append(compressor)
            cooler = exchange_air_with_ambient_ntu(
                compressor.outlet, c.ambient_temperature_k, c.intercooler_pressure_drop,
                WORKING_FLUID, c.ambient_heat_exchanger_ntu, "intercooling", COOL_ONLY,
            )
            charging.processes.append(cooler)
            current = cooler.outlet
        if abs(current.temperature_k - c.ambient_temperature_k) > 1e-9:
            charging.processes.append(exchange_with_environment(
                current, c.ambient_temperature_k, 0.0, WORKING_FLUID,
                "aftercooling", BOTH_WAYS,
            ))

        moisture = analyze_charge_moisture(c, charging)
        protected_humidity_ratio = (
            moisture.stored_air_water_vapor_kg_per_kg_dry_air
        )
        if not reference_wet_expander_liquid_envelope_ok(
            protected_humidity_ratio
        ):
            raise ValueError(
                "remaining charge-side moisture exceeds the selected reference "
                "wet-expander discharge liquid envelope; add deeper drying or "
                "select an OEM machine with a larger guaranteed liquid capacity"
            )
        if not dry_air_wet_expansion_approximation_ok(
            protected_humidity_ratio
        ):
            raise ValueError(
                "possible wet-expander condensate exceeds the dry-air model's "
                "0.1 wt% validity screen; use a coupled humid-air/two-phase "
                "energy balance for this configuration"
            )
        current = state_pt(self._p_storage, c.ambient_temperature_k, WORKING_FLUID)
        discharging = Cycle("discharging", current)
        pressure_ratio = self._expansion_ratio()
        external_heat = 0.0
        for stage in range(c.expander_stages):
            heater_pressure = current.pressure_pa * (1.0 - c.interheater_pressure_drop)
            turbine_pressure = self._p_ambient if stage == c.expander_stages - 1 else heater_pressure * pressure_ratio

            # AD-CAES always recovers ambient heat before each expansion.  A
            # no-reheat branch is physically unusable here: the expansion
            # temperatures would cross the icing envelope.
            reheater = exchange_air_with_ambient_ntu(
                current, c.ambient_temperature_k, c.interheater_pressure_drop,
                WORKING_FLUID, c.ambient_heat_exchanger_ntu, "ambient_reheat", HEAT_ONLY,
            )
            discharging.processes.append(reheater)
            current = reheater.outlet
            external_heat += max(0.0, reheater.heat_to_air_j_per_kg)

            reductions = self._safe_diabatic_pressure_reduction(
                current,
                turbine_pressure,
                protected_humidity_ratio,
            )
            discharging.processes.extend(reductions)
            current = reductions[-1].outlet
            local_minimum_k = minimum_wet_expander_temperature_k(
                current.pressure_pa,
                protected_humidity_ratio,
            )
            if current.temperature_k < local_minimum_k - TEMPERATURE_LIMIT_TOLERANCE_K:
                anti_icing_reheat = exchange_air_with_ambient_ntu(
                    current,
                    c.ambient_temperature_k,
                    0.0,
                    WORKING_FLUID,
                    c.ambient_heat_exchanger_ntu,
                    "ambient_anti_icing_reheat",
                    HEAT_ONLY,
                )
                discharging.processes.append(anti_icing_reheat)
                current = anti_icing_reheat.outlet
                external_heat += max(
                    0.0, anti_icing_reheat.heat_to_air_j_per_kg
                )
                if current.temperature_k < local_minimum_k - TEMPERATURE_LIMIT_TOLERANCE_K:
                    raise ValueError(
                        "ambient trim heat cannot restore the wet-expander "
                        "anti-icing margin after D-CAES throttling"
                    )

        charging = self._annotate_exergy(charging)
        discharging = self._annotate_exergy(discharging)
        exergy = self._summarize_diabatic(charging, discharging)
        return PlantResult(
            mode=c.mode.value, charging=charging, discharging=discharging,
            thermal_store=None, exergy=exergy,
            external_heat_input_j_per_kg=external_heat,
            moisture=moisture,
        )

    # ---------------------------------------------------------------- exergy books

    def _annotate_exergy(self, cycle: Cycle) -> Cycle:
        c = self.config
        return Cycle(cycle.name, cycle.inlet, [
            replace(process, exergy_destruction_j_per_kg=process_exergy_destruction(
                process, c.ambient_temperature_k, self._p_ambient, WORKING_FLUID
            )) for process in cycle.processes
        ])

    def _base_books(
        self,
        charging: Cycle,
        discharging: Cycle,
    ) -> tuple[float, float, dict[str, float], dict[str, float]]:
        c = self.config
        component: dict[str, float] = {}
        for process in charging.processes + discharging.processes:
            component[process.kind] = component.get(process.kind, 0.0) + process.exergy_destruction_j_per_kg
        losses = {"exhaust_air": max(0.0, air_exergy(
            discharging.outlet, c.ambient_temperature_k, self._p_ambient, WORKING_FLUID
        ))}
        return charging.work_j_per_kg, -discharging.work_j_per_kg, component, losses

    def _summarize_diabatic(self, charging: Cycle, discharging: Cycle) -> ExergySummary:
        compression, expansion, component, losses = self._base_books(
            charging, discharging
        )
        destruction, loss = sum(component.values()), sum(losses.values())
        electrical = expansion / compression
        return ExergySummary(
            total_useful_exergy_efficiency=electrical,
            hot_water_exergy_j_per_kg_air=0.0,
            useful_heat_exergy_j_per_kg_air=0.0,
            component_destruction_j_per_kg_air=component,
            loss_j_per_kg_air=losses,
            total_destruction_j_per_kg_air=destruction,
            total_loss_j_per_kg_air=loss,
            balance_residual_j_per_kg_air=compression - (expansion + destruction + loss),
        )

    def _summarize_adiabatic(
        self, charging: Cycle, discharging: Cycle,
        store: _ThermalStore, discharge: _DischargeDesign,
    ) -> tuple[
        TwoTankSummary,
        ExergySummary,
        HeatOfftakeSummary | None,
        ExtractionExchangerSummary | None,
    ]:
        c = self.config
        t0 = c.ambient_temperature_k
        compression, expansion, component, losses = self._base_books(
            charging, discharging
        )
        recovered = sum(branch[2] for branch in store.charge_returns)
        delivered = sum(branch[2] for branch in discharge.returns)

        # The upstream temperature drop is zero in the no-user absorption
        # design.  In DH mode the series exchanger removes
        # T_hot,available -> T_x and the network must absorb ALL of it: there
        # is deliberately no upstream rejection cooler, so the exported duty
        # always equals the whole upstream drop by construction.  We never add
        # a hidden cooler to rescue an infeasible DH temperature match.
        dh_duty = dh_water = dh_exergy = 0.0
        dh_supply_actual = c.heat_user_supply_temperature_k
        taps: tuple[OfftakeTap, ...] = ()
        if self._dispatches_heat_to_user():
            taps = self._build_offtake_taps(store, discharge)
            # One user exchanger and ONE user stream through it, so the duty and
            # the flow are the tap's own numbers - nothing to sum.
            tap = taps[0]
            dh_duty = tap.heat_j_per_kg_air
            dh_water = tap.user_water_per_kg_air
            dh_supply_actual = c.heat_user_supply_temperature_k
            dh_exergy = dh_water * (
                water_exergy(dh_supply_actual, t0)
                - water_exergy(c.heat_user_return_temperature_k, t0)
            )
            plant_drop_exergy = tap.plant_water_per_kg_air * (
                water_exergy(tap.plant_inlet_temperature_k, t0)
                - water_exergy(tap.plant_outlet_temperature_k, t0)
            )
            if dh_duty > 0.0:
                component["heat_offtake_taps"] = max(0.0, plant_drop_exergy - dh_exergy)

        def branch_exergy(branches: tuple[tuple[float, float, float], ...]) -> float:
            return sum(r * water_exergy(t, t0) for r, t, _ in branches)

        # The store owns one mixed temperature, so its exergy is its mass times
        # the specific exergy at that temperature.
        hot_before_exergy = store.total_ratio * water_exergy(
            store.hot_before_loss_k, t0
        )
        hot_available_exergy = store.total_ratio * water_exergy(
            store.hot_available_k, t0
        )
        recovery = self._optimize_cold_return_recovery(discharge.returns)
        mixed_return_k = recovery.mixed_tank_inlet_k
        # E-304 is the LAST thing on the return path, between the final mixing
        # and the cold tank, so it is what actually sets the tank inlet.
        extraction = (
            self._build_extraction_exchanger(store, discharge, mixed_return_k)
            if self._dispatches_heat_to_user()
            else None
        )
        cold_tank_inlet_k = (
            extraction.return_outlet_temperature_k
            if extraction is not None
            else mixed_return_k
        )
        component["hot_tank_mixing"] = max(0.0, branch_exergy(store.charge_returns) - hot_before_exergy)
        component["thermal_storage_loss"] = max(0.0, hot_before_exergy - hot_available_exergy)
        selected_inlet_exergy = recovery.mass_ratio * water_exergy(
            recovery.inlet_k, t0
        )
        selected_outlet_exergy = recovery.mass_ratio * water_exergy(
            recovery.outlet_k, t0
        )
        cold_return_exergy_destruction = max(
            0.0, selected_inlet_exergy - selected_outlet_exergy
        )
        # Mixing is booked against the return BEFORE recuperation: E-304 raises
        # that stream afterwards, and charging its gain to the mixing header
        # would net two unrelated irreversibilities against each other.
        component["cold_tank_mixing"] = max(
            0.0,
            branch_exergy(discharge.returns)
            - store.total_ratio * water_exergy(mixed_return_k, t0)
            - cold_return_exergy_destruction,
        )
        component["cold_return_ambient_exchange"] = cold_return_exergy_destruction
        if extraction is not None:
            # Internal recuperation destroys the gap between what the trunk
            # gives up and what the return picks up. Neither side crosses the
            # plant boundary, so nothing here is a product or a loss.
            component["extraction_exchanger"] = (
                extraction.exergy_destruction_j_per_kg_air
            )
        # The cold tank also stands for the configured dwell and drifts toward
        # ambient. The drift always lowers the water's exergy (toward the
        # dead-state minimum), so the leaked amount is destruction too.
        component["cold_tank_standing_loss"] = max(0.0, store.total_ratio * (
            water_exergy(cold_tank_inlet_k, t0)
            - water_exergy(store.cold_k, t0)
        ))
        cold_storage_loss = store.total_ratio * WATER_CP_J_PER_KGK * (
            cold_tank_inlet_k - store.cold_k
        )
        minimum_water_reached_k = min(
            store.cold_k,
            cold_tank_inlet_k,
            mixed_return_k,
            recovery.inlet_k,
            recovery.outlet_k,
            discharge.returned_mean_k,
            *(temperature for _, temperature, _ in discharge.returns),
        )
        if (
            minimum_water_reached_k
            < c.coolant_minimum_temperature_k - TEMPERATURE_LIMIT_TOLERANCE_K
        ):
            raise ValueError(
                "the closed coolant loop falls below the selected coolant "
                "freezing point"
            )

        thermal = TwoTankSummary(
            cold_temperature_k=store.cold_k,
            hot_temperature_before_loss_k=store.hot_before_loss_k,
            hot_temperature_available_k=store.hot_available_k,
            returned_temperature_k=discharge.returned_mean_k,
            total_water_mass_ratio=store.total_ratio,
            recovered_heat_j_per_kg_air=recovered,
            delivered_heat_j_per_kg_air=delivered,
            offtake_heat_j_per_kg_air=dh_duty,
            storage_loss_j_per_kg_air=store.storage_loss_j_per_kg_air,
            storage_duration_hours=c.storage_duration_hours,
            thermal_storage_tank_ua_w_per_k=c.thermal_storage_tank_ua_w_per_k,
            cold_return_heat_rejected_to_ambient_j_per_kg_air=0.0,
            cold_return_heat_absorbed_from_ambient_j_per_kg_air=(
                recovery.heat_absorbed_j_per_kg_air
            ),
            cold_return_exergy_destruction_j_per_kg_air=(
                cold_return_exergy_destruction
            ),
            cold_storage_loss_j_per_kg_air=cold_storage_loss,
            cold_return_exchanger_ntu=c.cold_return_cooler_ntu,
            cold_return_exchanger_outlet_temperature_k=cold_tank_inlet_k,
            cold_return_recovery_start_stage=recovery.start_stage,
            cold_return_recovery_branch_count=recovery.branch_count,
            cold_return_recovery_inlet_temperature_k=recovery.inlet_k,
            cold_return_recovery_outlet_temperature_k=recovery.outlet_k,
            recuperator_inlet_temperature_k=mixed_return_k,
            extraction_recuperated_heat_j_per_kg_air=(
                extraction.recuperated_heat_j_per_kg_air
                if extraction is not None
                else 0.0
            ),
            cold_loop_closure_error_k=(
                c.ambient_temperature_k
                + (cold_tank_inlet_k - c.ambient_temperature_k)
                * self._tank_decay(store.total_ratio)
                - store.cold_k
            ),
            coolant_maximum_temperature_k=c.coolant_maximum_temperature_k,
            coolant_maximum_temperature_reached_k=(
                store.maximum_water_temperature_reached_k
            ),
            coolant_minimum_temperature_k=c.coolant_minimum_temperature_k,
            coolant_minimum_temperature_reached_k=minimum_water_reached_k,
            # One-element tuples: the result schema names the former multi-level
            # store, and the active plant puts exactly one mixed state in it.
            hot_level_temperatures_k=(store.hot_available_k,),
            hot_level_water_mass_ratios=(store.total_ratio,),
        )

        district = None
        if c.heat_offtake is HeatOfftake.HEAT_USER:
            district = HeatOfftakeSummary(
                mode=c.heat_offtake.value,
                hot_tank_temperature_k=max(
                    (tap.plant_inlet_temperature_k for tap in taps),
                    default=store.hot_available_k,
                ),
                turbine_supply_temperature_k=discharge.supply_k,
                supply_temperature_k=dh_supply_actual,
                return_temperature_k=c.heat_user_return_temperature_k,
                heat_j_per_kg_air=dh_duty,
                exergy_j_per_kg_air=dh_exergy,
                network_water_per_kg_air=dh_water,
                taps=taps,
                heat_exchanger_ntu=c.heat_user_exchanger_ntu,
                maximum_required_effectiveness=max(
                    (tap.required_effectiveness for tap in taps), default=0.0
                ),
                minimum_effectiveness_margin=min(
                    (
                        tap.available_effectiveness - tap.required_effectiveness
                        for tap in taps
                    ),
                    default=0.0,
                ),
            )

        total_efficiency = (expansion + dh_exergy) / compression
        destruction, loss = sum(component.values()), sum(losses.values())
        exergy = ExergySummary(
            total_useful_exergy_efficiency=total_efficiency,
            hot_water_exergy_j_per_kg_air=hot_available_exergy,
            useful_heat_exergy_j_per_kg_air=dh_exergy,
            component_destruction_j_per_kg_air=component,
            loss_j_per_kg_air=losses,
            total_destruction_j_per_kg_air=destruction,
            total_loss_j_per_kg_air=loss,
            balance_residual_j_per_kg_air=compression - (expansion + dh_exergy + destruction + loss),
        )
        return thermal, exergy, district, extraction


@lru_cache(maxsize=128)
def _solve_cached(config: PlantConfig, property_api: PropertyAPI) -> PlantResult:
    with using_property_api(property_api):
        return CAESPlant(config, property_api)._run_uncached()
