"""Humidity, pressure-dew-point and frost-point diagnostics.

The plant energy solver deliberately remains a normalized dry-air model. This
module is a post-processor: it carries the inlet water-vapour ratio through the
calculated charging states, condenses vapour whenever a cooler outlet is below
the local phase-change temperature, and assumes an ideal liquid separator after
each charging intercooler and the final aftercooler.

The distinction matters:

* a cooler lowers temperature and can create liquid water;
* a separator removes that liquid but cannot remove water vapour;
* only condensation (or a true dryer) lowers the downstream pressure dew point.

Humidity ratio is expressed per kilogram of dry air, the conventional
psychrometric basis. The main cycle remains per kilogram of CoolProp ``Air``;
the small basis difference is intentionally not folded into its energy balance.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import exp, log
from typing import TYPE_CHECKING

from .config import PlantConfig
from .constants import (
    MINIMUM_FROST_CORRELATION_TEMPERATURE_K,
    WATER_CRITICAL_POINT_K,
    WATER_TO_DRY_AIR_MOLAR_MASS_RATIO,
    WATER_TRIPLE_POINT_K,
    WATER_TRIPLE_POINT_PRESSURE_PA,
)
from .models import Cycle, MoistureSummary
from .thermodynamics import (
    PropertyAPI,
    current_property_api,
    water_saturation_pressure_pa,
    water_saturation_temperature_k,
)

if TYPE_CHECKING:
    from .models import PlantResult


@dataclass(frozen=True)
class MoistureInventoryPoint:
    """Water inventory at one machinery or separator connection.

    Mass fractions use the total wet-stream basis used by machinery vendors,
    while the internal vapour and condensate balances retain the conventional
    kg-water/kg-dry-air basis.
    """

    equipment_tag: str
    position: str
    pressure_pa: float
    temperature_k: float
    water_vapor_kg_per_kg_dry_air: float
    condensed_water_kg_per_kg_dry_air: float
    note: str = ""

    @property
    def water_vapor_mass_fraction(self) -> float:
        total = (
            1.0
            + self.water_vapor_kg_per_kg_dry_air
            + self.condensed_water_kg_per_kg_dry_air
        )
        return self.water_vapor_kg_per_kg_dry_air / total

    @property
    def condensed_water_mass_fraction(self) -> float:
        total = (
            1.0
            + self.water_vapor_kg_per_kg_dry_air
            + self.condensed_water_kg_per_kg_dry_air
        )
        return self.condensed_water_kg_per_kg_dry_air / total

    @property
    def pressure_bar(self) -> float:
        return self.pressure_pa / 1e5

    @property
    def temperature_c(self) -> float:
        return self.temperature_k - 273.15


def saturation_vapor_pressure_pa(temperature_k: float) -> float:
    """Equilibrium water-vapour pressure over liquid water or ice [Pa].

    CoolProp supplies the liquid-vapour saturation curve at and above the water
    triple point. Below it, the Murphy-Koop ice correlation is used:

        ln(p_ice/Pa) = 9.550426 - 5723.265/T + 3.53068 ln(T) - 0.00728332 T
    """

    return _saturation_vapor_pressure_pa(temperature_k, current_property_api())


@lru_cache(maxsize=8192)
def _saturation_vapor_pressure_pa(
    temperature_k: float, property_api: PropertyAPI
) -> float:
    """API-keyed implementation, avoiding cross-contamination in A/B tests."""

    if temperature_k < MINIMUM_FROST_CORRELATION_TEMPERATURE_K:
        raise ValueError(
            "frost-point correlation is not valid below "
            f"{MINIMUM_FROST_CORRELATION_TEMPERATURE_K:.0f} K"
        )
    if temperature_k >= WATER_CRITICAL_POINT_K:
        return float("inf")
    if temperature_k < WATER_TRIPLE_POINT_K:
        return exp(
            9.550426
            - 5723.265 / temperature_k
            + 3.53068 * log(temperature_k)
            - 0.00728332 * temperature_k
        )
    return water_saturation_pressure_pa(temperature_k, property_api)


# --------------------------------------------------------------- enhancement factor
#
# Water vapour in compressed AIR does not behave like pure water vapour.  The
# air raises the equilibrium vapour content above the pure-component saturation
# pressure, by the Poynting effect (the liquid sits at total pressure, not at
# its own vapour pressure) and by air-water molecular interaction in the gas
# phase.  The ratio is the enhancement factor
#
#     f(T, p) = x_vapour * p / p_saturation,pure(T)          [-]
#
# and it is NOT a detail at these pressures.  Measured against CoolProp's real
# humid-air model at 15 degC: f = 1.004 at 1 bar, 1.10 at 30 bar, 1.39 at
# 100 bar.  Ignoring it made this module report 28% LESS water than is really
# there at 100 bar, which is the wrong direction for a safety screen: it
# understated the stored moisture, the pressure dew point, the frost point, and
# therefore the wet-expander anti-icing floor by 3 to 4 K at every stage.
#
# The factor is applied in the ONE place both directions share, so the forward
# map (state -> saturated humidity) and the inverse (humidity -> dew/frost
# point) can never drift apart.
# CoolProp's humid-air backend is valid up to 10 MPa inclusive, but the top of
# the table is kept just inside it: a log-spaced grid lands on the boundary with
# a last-bit rounding error that the backend rejects outright.
ENHANCEMENT_REFERENCE_MAX_PRESSURE_PA = 9.9e6
ENHANCEMENT_TABLE_MIN_TEMPERATURE_K = 210.0
ENHANCEMENT_TABLE_MAX_TEMPERATURE_K = 460.0
ENHANCEMENT_TABLE_TEMPERATURE_STEP_K = 5.0
# Below this the vapour is too dilute for the correction to matter at all, and
# CoolProp's humid-air backend is outside its own range.
ENHANCEMENT_TABLE_MIN_PRESSURE_PA = 1.0e5
# Saturated air stops being "air with some water in it" as the pure saturation
# pressure approaches the total pressure; the enhancement concept degenerates
# there and the humidity ratio is already reported as infinite.
ENHANCEMENT_MAX_SATURATION_FRACTION = 0.5


@lru_cache(maxsize=2)
def _enhancement_table(property_api: PropertyAPI) -> tuple[
    tuple[float, ...], tuple[float, ...], tuple[tuple[float, ...], ...]
]:
    """Lazily tabulate ln f on a (temperature, ln pressure) grid.

    Built once from CoolProp's humid-air backend, which is the same library the
    rest of the package uses, so the correction is consistent with the air
    properties rather than being an independent correlation.  Roughly a
    thousand backend calls at about 18 us each: a one-off cost of a few tens of
    milliseconds, after which every lookup is arithmetic.  A direct call per
    lookup would be far too slow, because the dew/frost-point inversion below
    evaluates saturation dozens of times per solve.
    """
    from CoolProp.HumidAirProp import HAPropsSI

    temperatures = tuple(
        ENHANCEMENT_TABLE_MIN_TEMPERATURE_K
        + index * ENHANCEMENT_TABLE_TEMPERATURE_STEP_K
        for index in range(
            int(
                (
                    ENHANCEMENT_TABLE_MAX_TEMPERATURE_K
                    - ENHANCEMENT_TABLE_MIN_TEMPERATURE_K
                )
                / ENHANCEMENT_TABLE_TEMPERATURE_STEP_K
            )
            + 1
        )
    )
    steps = 24
    ratio = log(
        ENHANCEMENT_REFERENCE_MAX_PRESSURE_PA / ENHANCEMENT_TABLE_MIN_PRESSURE_PA
    ) / steps
    pressures = tuple(
        ENHANCEMENT_TABLE_MIN_PRESSURE_PA * exp(index * ratio)
        for index in range(steps + 1)
    )

    rows: list[tuple[float, ...]] = []
    for temperature_k in temperatures:
        pure = _saturation_vapor_pressure_pa(temperature_k, property_api)
        row: list[float | None] = []
        for pressure_pa in pressures:
            if pure >= ENHANCEMENT_MAX_SATURATION_FRACTION * pressure_pa:
                # Degenerate corner: the mixture stops being "air with some
                # water in it".  Callers never reach it, because the humidity
                # ratio saturates to infinity first.
                row.append(None)
                continue
            try:
                humidity = HAPropsSI(
                    "W", "P", pressure_pa, "T", temperature_k, "R", 1.0
                )
            except (ValueError, RuntimeError):
                row.append(None)
                continue
            vapor = (
                pressure_pa
                * humidity
                / (WATER_TO_DRY_AIR_MOLAR_MASS_RATIO + humidity)
            )
            row.append(log(max(vapor / pure, 1.0)))
        rows.append(tuple(_fill_gaps(row, pressures)))
    return temperatures, pressures, tuple(rows)


def _fill_gaps(
    row: list[float | None], pressures: tuple[float, ...]
) -> list[float]:
    """Replace unavailable cells by extrapolation, never by their neighbour.

    Holding the previous value would freeze ln f at a plateau, and because the
    factor grows with pressure that silently UNDERSTATES the water content in
    exactly the high-pressure corner this correction exists for.  Extrapolating
    the local slope keeps the curve going the right way, and a leading hole
    (vapour too dilute to matter) is simply f = 1.
    """
    known = [index for index, value in enumerate(row) if value is not None]
    if not known:
        return [0.0] * len(row)
    filled: list[float] = []
    for index, value in enumerate(row):
        if value is not None:
            filled.append(value)
            continue
        if index < known[0]:
            filled.append(0.0)
            continue
        last, previous = known[-1], known[-2] if len(known) > 1 else known[-1]
        if last == previous:
            filled.append(row[last])
            continue
        slope = (row[last] - row[previous]) / (
            pressures[last] - pressures[previous]
        )
        filled.append(row[last] + slope * (pressures[index] - pressures[last]))
    return filled


def water_vapor_enhancement_factor(
    total_pressure_pa: float,
    temperature_k: float,
) -> float:
    """Enhancement factor of water vapour in air at (p, T) [-]. Always >= 1.

    Bilinear in temperature and in ln pressure over the tabulated range.  Above
    ``ENHANCEMENT_REFERENCE_MAX_PRESSURE_PA`` the humid-air backend has no
    validated data, so ln f is extrapolated linearly in pressure from the slope
    at the top of the table.  That is an admitted extrapolation for 100 to
    300 bar caverns, and it is deliberately the conservative direction for a
    moisture screen: it keeps MORE water in the stored air than the
    uncorrected model, never less.
    """
    if total_pressure_pa <= ENHANCEMENT_TABLE_MIN_PRESSURE_PA:
        return 1.0
    temperatures, pressures, rows = _enhancement_table(current_property_api())
    temperature_k = min(
        max(temperature_k, temperatures[0]), temperatures[-1]
    )
    position = (temperature_k - temperatures[0]) / (
        ENHANCEMENT_TABLE_TEMPERATURE_STEP_K
    )
    low_index = min(int(position), len(temperatures) - 2)
    weight = position - low_index

    def at(pressure_pa: float) -> float:
        """ln f at one pressure, interpolated between the two temperature rows."""
        span = log(pressures[-1] / pressures[0])
        fraction = log(pressure_pa / pressures[0]) / span * (len(pressures) - 1)
        index = min(int(fraction), len(pressures) - 2)
        blend = fraction - index
        values = []
        for row in (rows[low_index], rows[low_index + 1]):
            values.append(row[index] + blend * (row[index + 1] - row[index]))
        return values[0] + weight * (values[1] - values[0])

    top = pressures[-1]
    if total_pressure_pa <= top:
        return exp(at(total_pressure_pa))
    # First-order extrapolation of ln f in pressure, using the slope over the
    # last tabulated decade rather than a chord through the origin: the two
    # differ by several percent by 100 bar and the gap grows with pressure.
    lower = pressures[-3]
    slope = (at(top) - at(lower)) / (top - lower)
    return exp(at(top) + slope * (total_pressure_pa - top))


def effective_saturation_vapor_pressure_pa(
    total_pressure_pa: float,
    temperature_k: float,
) -> float:
    """Equilibrium water partial pressure over condensate IN AIR at (p, T) [Pa].

    This is the quantity the whole module is really about, and the single
    source of both the forward and the inverse map.
    """
    return water_vapor_enhancement_factor(
        total_pressure_pa, temperature_k
    ) * saturation_vapor_pressure_pa(temperature_k)


def humidity_ratio_from_vapor_pressure(
    vapor_pressure_pa: float,
    total_pressure_pa: float,
) -> float:
    """Return kg-water-vapour/kg-dry-air from water partial pressure."""

    if vapor_pressure_pa < 0 or total_pressure_pa <= vapor_pressure_pa:
        raise ValueError("water vapour pressure must be in [0, total pressure)")
    return (
        WATER_TO_DRY_AIR_MOLAR_MASS_RATIO
        * vapor_pressure_pa
        / (total_pressure_pa - vapor_pressure_pa)
    )


def vapor_pressure_from_humidity_ratio(
    humidity_ratio: float,
    total_pressure_pa: float,
) -> float:
    """Return water partial pressure [Pa] from kg-vapour/kg-dry-air."""

    if humidity_ratio < 0 or total_pressure_pa <= 0:
        raise ValueError("humidity ratio must be non-negative and pressure positive")
    return (
        total_pressure_pa
        * humidity_ratio
        / (WATER_TO_DRY_AIR_MOLAR_MASS_RATIO + humidity_ratio)
    )


def saturation_humidity_ratio(
    total_pressure_pa: float,
    temperature_k: float,
) -> float:
    """Saturated humidity ratio at a compressed-air state. FORWARD map."""

    vapor_pressure_pa = effective_saturation_vapor_pressure_pa(
        total_pressure_pa, temperature_k
    )
    if vapor_pressure_pa >= total_pressure_pa:
        return float("inf")
    return humidity_ratio_from_vapor_pressure(vapor_pressure_pa, total_pressure_pa)


def inlet_humidity_ratio(config: PlantConfig) -> float:
    """Ambient inlet water vapour on the dry-air mass basis."""

    total_pressure_pa = config.ambient_pressure_bar * 1e5
    vapor_pressure_pa = (
        config.ambient_relative_humidity
        * effective_saturation_vapor_pressure_pa(
            total_pressure_pa, config.ambient_temperature_k
        )
    )
    return humidity_ratio_from_vapor_pressure(
        vapor_pressure_pa,
        total_pressure_pa,
    )


def phase_change_temperature_k(
    total_pressure_pa: float,
    humidity_ratio: float,
) -> float:
    """Pressure dew point (>= 0 °C) or frost point (< 0 °C) [K]. INVERSE map.

    Solves ``f(T, p) p_saturation,pure(T) = p_vapour`` for T, i.e. it inverts
    exactly the same relation :func:`saturation_humidity_ratio` evaluates
    forward.  Correcting only one of the two would have left the module
    reporting a saturated humidity that its own dew point disagreed with.

    The bracket is seeded from the UNCORRECTED inversion, which is a strict
    upper bound: the enhancement factor is never below one, so accounting for
    it always lowers the temperature at which the same vapour pressure
    saturates.  That keeps the search short even though the corrected relation
    has no closed-form inverse.
    """
    return _phase_change_temperature_k(
        total_pressure_pa, humidity_ratio, current_property_api()
    )


@lru_cache(maxsize=8192)
def _phase_change_temperature_k(
    total_pressure_pa: float,
    humidity_ratio: float,
    property_api: PropertyAPI,
) -> float:
    """API-keyed inverse saturation calculation."""

    vapor_pressure_pa = vapor_pressure_from_humidity_ratio(
        humidity_ratio, total_pressure_pa
    )
    if vapor_pressure_pa < saturation_vapor_pressure_pa(
        MINIMUM_FROST_CORRELATION_TEMPERATURE_K
    ):
        raise ValueError("water content gives a frost point below 110 K")

    if vapor_pressure_pa >= WATER_TRIPLE_POINT_PRESSURE_PA:
        uncorrected_k = water_saturation_temperature_k(
            vapor_pressure_pa, property_api
        )
    else:
        low = MINIMUM_FROST_CORRELATION_TEMPERATURE_K
        high = WATER_TRIPLE_POINT_K
        for _ in range(60):
            middle = 0.5 * (low + high)
            if saturation_vapor_pressure_pa(middle) < vapor_pressure_pa:
                low = middle
            else:
                high = middle
        uncorrected_k = 0.5 * (low + high)

    if water_vapor_enhancement_factor(total_pressure_pa, uncorrected_k) <= 1.0:
        return uncorrected_k

    def excess(temperature_k: float) -> float:
        return (
            effective_saturation_vapor_pressure_pa(total_pressure_pa, temperature_k)
            - vapor_pressure_pa
        )

    high = uncorrected_k
    low = max(MINIMUM_FROST_CORRELATION_TEMPERATURE_K, high - 1.0)
    # Widen downward until the corrected saturation falls below the target.
    for _ in range(12):
        if excess(low) < 0.0:
            break
        if low <= MINIMUM_FROST_CORRELATION_TEMPERATURE_K:
            return low
        low = max(MINIMUM_FROST_CORRELATION_TEMPERATURE_K, high - 2.0 * (high - low))
    else:
        return low
    while high - low > 1e-5:
        middle = 0.5 * (low + high)
        if excess(middle) < 0.0:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def analyze_charge_moisture(config: PlantConfig, charging: Cycle) -> MoistureSummary:
    """Propagate ambient humidity through calculated charge-side coolers.

    ``intercooling`` and ``aftercooling`` mean real surface coolers followed by
    ideal liquid separators.
    """

    inlet_ratio = inlet_humidity_ratio(config)
    current_ratio = inlet_ratio
    surface_removed = 0.0

    for process in charging.processes:
        if process.kind not in {"intercooling", "aftercooling"}:
            continue
        if process.outlet.temperature_k >= process.inlet.temperature_k - 1e-9:
            continue

        saturated_outlet_ratio = saturation_humidity_ratio(
            process.outlet.pressure_pa,
            process.outlet.temperature_k,
        )
        outlet_ratio = min(current_ratio, saturated_outlet_ratio)
        condensed = max(0.0, current_ratio - outlet_ratio)
        surface_removed += condensed
        current_ratio = outlet_ratio

    return MoistureSummary(
        ambient_relative_humidity=config.ambient_relative_humidity,
        inlet_water_vapor_kg_per_kg_dry_air=inlet_ratio,
        stored_air_water_vapor_kg_per_kg_dry_air=current_ratio,
        surface_separator_water_kg_per_kg_dry_air=surface_removed,
        storage_pressure_pa=config.storage_pressure_bar * 1e5,
    )


def equilibrium_water_split(
    total_water_kg_per_kg_dry_air: float,
    pressure_pa: float,
    temperature_k: float,
) -> tuple[float, float]:
    """Return equilibrium vapour and condensed water ratios at one state.

    The condensed term is liquid above freezing and an ice-equivalent inventory
    below freezing. A positive value below 0 degC therefore identifies an
    unacceptable icing state; the normal expander envelope prevents it.
    """

    if total_water_kg_per_kg_dry_air < 0.0:
        raise ValueError("total water ratio must be non-negative")
    saturated_vapor_ratio = saturation_humidity_ratio(pressure_pa, temperature_k)
    vapor_ratio = min(total_water_kg_per_kg_dry_air, saturated_vapor_ratio)
    return vapor_ratio, max(0.0, total_water_kg_per_kg_dry_air - vapor_ratio)


def compressor_moisture_inventory(
    result: "PlantResult",
    *,
    separate_after_each_cooler: bool,
) -> tuple[MoistureInventoryPoint, ...]:
    """Water wt-fractions at every compressor body and cooler outlet.

    With ``separate_after_each_cooler=False`` this is a counterfactual,
    equilibrium-only calculation: all condensed water is carried into the next
    compressor until the final aftercooler. It quantifies the liquid ingestion
    that a single final separator would create, but it does not make the dry-air
    compressor model valid for that wet stream.
    """

    moisture = result.moisture
    if moisture is None:
        return ()

    total_water_ratio = moisture.inlet_water_vapor_kg_per_kg_dry_air
    last_vapor_ratio = total_water_ratio
    last_condensed_ratio = 0.0
    compressor_stage = 0
    points: list[MoistureInventoryPoint] = []

    for process in result.charging.processes:
        if process.kind == "compression":
            compressor_stage += 1
            tag = f"K-{100 + compressor_stage}"
            points.append(
                MoistureInventoryPoint(
                    tag,
                    "suction",
                    process.inlet.pressure_pa,
                    process.inlet.temperature_k,
                    last_vapor_ratio,
                    last_condensed_ratio,
                    (
                        "single-final-separator counterfactual; dry compressor "
                        "model invalid with liquid ingestion"
                        if last_condensed_ratio > 0.0
                        else ""
                    ),
                )
            )
            last_vapor_ratio, last_condensed_ratio = equilibrium_water_split(
                total_water_ratio,
                process.outlet.pressure_pa,
                process.outlet.temperature_k,
            )
            points.append(
                MoistureInventoryPoint(
                    tag,
                    "discharge",
                    process.outlet.pressure_pa,
                    process.outlet.temperature_k,
                    last_vapor_ratio,
                    last_condensed_ratio,
                )
            )
            continue

        if process.kind not in {"intercooling", "aftercooling"}:
            continue

        last_vapor_ratio, last_condensed_ratio = equilibrium_water_split(
            total_water_ratio,
            process.outlet.pressure_pa,
            process.outlet.temperature_k,
        )
        tag = (
            f"E-{100 + compressor_stage}"
            if process.kind == "intercooling"
            else "AC-101"
        )
        points.append(
            MoistureInventoryPoint(
                tag,
                "cooler outlet / separator inlet",
                process.outlet.pressure_pa,
                process.outlet.temperature_k,
                last_vapor_ratio,
                last_condensed_ratio,
                (
                    "final dedicated aftercooler/separator"
                    if process.kind == "aftercooling"
                    else ""
                ),
            )
        )
        if separate_after_each_cooler or process.kind == "aftercooling":
            total_water_ratio = last_vapor_ratio
            last_condensed_ratio = 0.0

    return tuple(points)


def expander_moisture_inventory(
    result: "PlantResult",
) -> tuple[MoistureInventoryPoint, ...]:
    """Water wt-fractions at each identifiable expander suction and discharge.

    The generated P&ID removes equilibrium condensate after the final pressure
    reduction of each stage. A-CAES stages are identified by their water
    ``interheating`` process, including DH trains that have an
    ``ambient_reheat`` immediately before it. D-CAES stages are identified by
    ``ambient_reheat`` only when no coolant interheaters exist. If every reheater
    is disabled, the reduced process list does not retain enough stage-boundary
    metadata and this diagnostic safely returns an empty tuple.
    """

    moisture = result.moisture
    if moisture is None:
        return ()

    processes = result.discharging.processes
    water_stage_starts = [
        index
        for index, process in enumerate(processes)
        if process.kind == "interheating"
    ]
    stage_starts = water_stage_starts or [
        index
        for index, process in enumerate(processes)
        if process.kind == "ambient_reheat"
    ]
    if not stage_starts:
        return ()

    current_total_water_ratio = moisture.stored_air_water_vapor_kg_per_kg_dry_air
    points: list[MoistureInventoryPoint] = []

    for stage_offset, start in enumerate(stage_starts):
        end = (
            stage_starts[stage_offset + 1]
            if stage_offset + 1 < len(stage_starts)
            else len(processes)
        )
        group = processes[start:end]
        expander_tag = f"T-{201 + stage_offset}"
        separator_tag = f"MS-{201 + stage_offset}"
        suction = group[0].outlet
        suction_vapor, suction_condensed = equilibrium_water_split(
            current_total_water_ratio,
            suction.pressure_pa,
            suction.temperature_k,
        )
        points.append(
            MoistureInventoryPoint(
                expander_tag,
                "suction",
                suction.pressure_pa,
                suction.temperature_k,
                suction_vapor,
                suction_condensed,
            )
        )

        expansion = next(
            (process for process in group if process.kind == "expansion"),
            None,
        )
        if expansion is None:
            points.append(
                MoistureInventoryPoint(
                    expander_tag,
                    "discharge",
                    suction.pressure_pa,
                    suction.temperature_k,
                    suction_vapor,
                    suction_condensed,
                    "turbine bypassed; scheduled pressure drop is throttled",
                )
            )
        else:
            discharge_vapor, discharge_condensed = equilibrium_water_split(
                current_total_water_ratio,
                expansion.outlet.pressure_pa,
                expansion.outlet.temperature_k,
            )
            points.append(
                MoistureInventoryPoint(
                    expander_tag,
                    "discharge",
                    expansion.outlet.pressure_pa,
                    expansion.outlet.temperature_k,
                    discharge_vapor,
                    discharge_condensed,
                )
            )

        reductions = [
            process
            for process in group
            if process.kind in {"expansion", "throttling"}
        ]
        if not reductions:
            continue
        separator_inlet = reductions[-1].outlet
        separator_vapor, separator_condensed = equilibrium_water_split(
            current_total_water_ratio,
            separator_inlet.pressure_pa,
            separator_inlet.temperature_k,
        )
        points.append(
            MoistureInventoryPoint(
                separator_tag,
                "separator inlet",
                separator_inlet.pressure_pa,
                separator_inlet.temperature_k,
                separator_vapor,
                separator_condensed,
            )
        )
        current_total_water_ratio = separator_vapor

    return tuple(points)
