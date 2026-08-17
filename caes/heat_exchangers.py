"""Counter-current air/water heat-exchanger models, normalised per kg of air.

THE NORMALISATION - read this first, it explains every unit in the file
----------------------------------------------------------------------
The whole package is written for 1 kg of air.  The water side is therefore
never expressed as a mass flow but as a *mass ratio*

    r = m_water / m_air            [kg-water / kg-air]

and the coolant-side heat-capacity rate becomes

    C_water = r * cp_water         [J / (K . kg-air)]
    C_air   =     cp_air           [J / (K . kg-air)]

Both capacity rates are per kilogram of air, so they are directly comparable and
the ordinary epsilon-NTU algebra applies unchanged.  Duties come out in J/kg-air,
which is the unit the rest of the package speaks.

WHY r IS THE CENTRAL DESIGN VARIABLE
------------------------------------
r sets the *shape* of the temperature profile in the exchanger, and it trades
off the two things an LTA-CAES plant wants and cannot have at once:

  * small r -> little water, so it comes out HOT (high exergy quality per kg)
    but the air is poorly cooled, so the next compressor stage starts hot and
    eats more work;
  * large r -> lots of water, so the air is cooled almost to the cold-tank
    temperature (cheap compression) but the water comes back LUKEWARM, and
    lukewarm water cannot reheat the air much on discharge.

There is a genuine interior optimum, which is what
:class:`caes.config.OptimizationObjective` searches for.

THE EXCHANGER MODEL
-------------------
Every air/water HX is a finite counter-current exchanger specified by NTU,
where ``NTU = UA/C_min``. Effectiveness is always a derived result of NTU and
the solved air/water capacity-rate ratio; it is never an independent input.
"""

from __future__ import annotations

from math import exp, inf

from .models import HeatExchangerPerformance, Process, State
from .thermodynamics import COOL_ONLY, HEAT_ONLY, air_cp, state_ph

# Liquid water, near-incompressible, 20-90 C. Varies by well under 1% over the
# range this plant uses, so a constant is fine and keeps the water side linear
# in temperature (which the tank mixing algebra in plant.py relies on).
WATER_CP_J_PER_KGK = 4_180.0


def counterflow_effectiveness(ntu: float, capacity_ratio: float) -> float:
    """Effectiveness of a pure counter-flow exchanger.

        eps = (1 - exp(-NTU (1 - Cr))) / (1 - Cr exp(-NTU (1 - Cr)))          (4)

    with ``NTU = UA / C_min`` and ``Cr = C_min / C_max``.  Standard result; see
    Incropera & DeWitt, *Fundamentals of Heat and Mass Transfer*, Table 11.3.

    The expression is 0/0 at Cr = 1, where it collapses to the balanced-flow
    limit ``eps = NTU / (1 + NTU)``.  We branch on that explicitly rather than
    letting floating point decide, because Cr lands exactly on 1 more often than
    you would think (the optimiser happily parks r right where the two capacity
    rates match, since that is the most *area*-efficient point).
    """
    if abs(1.0 - capacity_ratio) < 1e-10:
        return ntu / (1.0 + ntu)
    exponential = exp(-ntu * (1.0 - capacity_ratio))
    return (1.0 - exponential) / (1.0 - capacity_ratio * exponential)


def _counterflow_air_duty(
    inlet: State,
    secondary_inlet_temperature_k: float,
    secondary_capacity_rate_j_per_kgk_air: float,
    outlet_pressure_pa: float,
    fluid: str,
    ntu: float,
    air_is_hot_side: bool,
    with_state: bool = True,
) -> tuple[float, State | None, float]:
    """Epsilon-NTU duty with the air cp evaluated at the exchanger MEAN temperature.

    The textbook epsilon-NTU method assumes constant cp, evaluated once.  That
    is fine at 1 bar, but at 100-300 bar the real-air cp varies enough across
    one exchanger (several percent over a 100 K span) to move the duty.  So we
    iterate: solve with the current cp, re-evaluate cp at the arithmetic mean
    of the two ends, and repeat.  Two passes usually converge.

    The outlet temperature used to re-locate cp is the LINEAR estimate
    ``T_in +/- duty/cp`` - cheap and accurate to well under a kelvin for a
    cp-relocation purpose.  The expensive real-fluid inversion ``T(p, h)`` is
    paid exactly once, at the end, and only when ``with_state`` asks for it
    (the inverse solver in :func:`water_ratio_for_duty` needs the duty, never
    the state).

    Returns ``(duty_j_per_kg_air, outlet_state_or_None, effectiveness)``.  With
    an infinite secondary capacity rate (the atmosphere) Cr = 0 falls out of
    the shared formula and the effectiveness is exactly ``1 - exp(-NTU)``.
    """
    span = (
        inlet.temperature_k - secondary_inlet_temperature_k
        if air_is_hot_side
        else secondary_inlet_temperature_k - inlet.temperature_k
    )
    cp_air = air_cp(inlet.pressure_pa, inlet.temperature_k, fluid)
    duty = 0.0
    effectiveness = 0.0
    for _ in range(3):
        c_min = min(cp_air, secondary_capacity_rate_j_per_kgk_air)
        c_max = max(cp_air, secondary_capacity_rate_j_per_kgk_air)
        effectiveness = counterflow_effectiveness(ntu, c_min / c_max)
        duty = effectiveness * c_min * span
        t_out_estimate = (
            inlet.temperature_k - duty / cp_air
            if air_is_hot_side
            else inlet.temperature_k + duty / cp_air
        )
        refined = air_cp(
            0.5 * (inlet.pressure_pa + outlet_pressure_pa),
            0.5 * (inlet.temperature_k + t_out_estimate),
            fluid,
        )
        # A 1e-4 relative cp change moves the duty by far less than the model's
        # own uncertainty; iterating any tighter just doubles the CoolProp
        # calls per exchanger evaluation.
        if abs(refined - cp_air) <= 1e-4 * cp_air:
            cp_air = refined
            break
        cp_air = refined
    outlet = None
    if with_state:
        enthalpy_out = (
            inlet.enthalpy_j_per_kg - duty
            if air_is_hot_side
            else inlet.enthalpy_j_per_kg + duty
        )
        outlet = state_ph(outlet_pressure_pa, enthalpy_out, fluid)
    return duty, outlet, effectiveness


def cool_air_with_water(
    inlet: State,
    water_inlet_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    ntu: float,
    water_air_mass_ratio: float | None,
) -> Process:
    """Intercooler / aftercooler: hot air gives heat to cold-tank water.

    Air is the hot stream, water the cold stream.  Water always enters at the
    cold-tank temperature (the plant never recycles part-warmed water into an
    intercooler), which is what lets :mod:`caes.plant` mix all the branch outlets
    into one hot tank with a single energy balance.

    Returns a Process with ``q = -duty`` (heat leaves the air) and a populated
    :class:`~caes.models.HeatExchangerPerformance` describing the water side.
    """
    p_out = inlet.pressure_pa * (1.0 - pressure_drop)

    # Second law: you cannot cool the air below the temperature of the coolant
    # you are cooling it with. If the air already arrives colder than the cold
    # tank there is nothing to recover; the exchanger becomes a pressure drop.
    if inlet.temperature_k <= water_inlet_temperature_k:
        outlet = state_ph(p_out, inlet.enthalpy_j_per_kg, fluid)
        return Process("intercooling", inlet, outlet)

    if water_air_mass_ratio is None or water_air_mass_ratio <= 0:
        raise ValueError("heat-exchanger models require a positive water/air mass ratio")
    ratio = water_air_mass_ratio

    c_water = ratio * WATER_CP_J_PER_KGK
    duty, outlet, effectiveness = _counterflow_air_duty(
        inlet, water_inlet_temperature_k, c_water, p_out, fluid, ntu,
        air_is_hot_side=True,
    )
    t_water_out = water_inlet_temperature_k + duty / c_water

    hx = HeatExchangerPerformance(
        effectiveness, ntu, ratio, water_inlet_temperature_k, t_water_out, duty,
    )
    return Process(
        "intercooling", inlet, outlet,
        heat_to_air_j_per_kg=-duty,   # negative: heat LEAVES the air
        heat_exchanger=hx,
    )


def heat_air_with_water(
    inlet: State,
    water_inlet_temperature_k: float,
    water_air_mass_ratio: float,
    pressure_drop: float,
    fluid: str,
    ntu: float,
    *,
    allow_zero_flow: bool = False,
) -> Process:
    """Interheater: hot coolant gives its stored heat back to the expanding air.

    The mirror image of :func:`cool_air_with_water`.  No cold-temperature clamp is
    applied here: the finite exchanger equations determine the real branch return.
    The plant solver varies each branch flow and closes the mixed cold-tank
    temperature over the whole cycle.  A local clamp would hide an external cooler
    and violate the physical cycle closure.

    A non-positive water ratio raises, mirroring :func:`cool_air_with_water`,
    unless ``allow_zero_flow`` is set.  The exception exists for the
    minimum-duty discharge design, where a stage whose moisture-safe duty is
    zero legitimately gets an empty branch (a plain pressure drop).
    """
    p_out = inlet.pressure_pa * (1.0 - pressure_drop)

    if water_air_mass_ratio <= 0 and not allow_zero_flow:
        raise ValueError("heat-exchanger models require a positive water/air mass ratio")

    # No water, or water that is not hotter than the air: nothing to transfer.
    if water_air_mass_ratio <= 0 or water_inlet_temperature_k <= inlet.temperature_k:
        outlet = state_ph(p_out, inlet.enthalpy_j_per_kg, fluid)
        return Process("interheating", inlet, outlet)

    c_water = water_air_mass_ratio * WATER_CP_J_PER_KGK
    duty, outlet, effectiveness = _counterflow_air_duty(
        inlet, water_inlet_temperature_k, c_water, p_out, fluid, ntu,
        air_is_hot_side=False,
    )
    t_water_out = water_inlet_temperature_k - duty / c_water  # water gives it up

    hx = HeatExchangerPerformance(
        effectiveness, ntu, water_air_mass_ratio,
        water_inlet_temperature_k, t_water_out, duty,
    )
    return Process(
        "interheating", inlet, outlet,
        heat_to_air_j_per_kg=duty,    # positive: heat ENTERS the air
        heat_exchanger=hx,
    )


def exchange_air_with_ambient_ntu(
    inlet: State,
    ambient_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    ntu: float,
    kind: str,
    direction: str,
) -> Process:
    """Finite-NTU exchanger against the atmosphere (D-CAES coolers and reheaters).

    The atmosphere is an *infinite* capacity rate - it does not change
    temperature - so this is the same shared counter-flow code as the water
    exchangers with Cr = 0, where the effectiveness collapses to
    ``1 - exp(-NTU)``.  There is no separate idealised "hit the target
    temperature" model: NTU = UA/C_air sizes the approach exactly as it does
    for the water side, which keeps the D-CAES and A-CAES comparisons on the
    same exchanger discipline.

    ``direction`` is one-way, like the real hardware: a cooler
    (``COOL_ONLY``) cannot heat air that arrives colder than the atmosphere,
    and a reheater (``HEAT_ONLY``) cannot chill air that arrives warmer.  In
    those cases the component degenerates to an isenthalpic pressure drop.

    No :class:`~caes.models.HeatExchangerPerformance` is attached: the second
    stream is the dead state itself, which is what the exergy module keys on to
    book the exchanger's irreversibility (heat exchanged with the environment
    carries zero exergy).
    """
    p_out = inlet.pressure_pa * (1.0 - pressure_drop)

    if direction == COOL_ONLY:
        active = inlet.temperature_k > ambient_temperature_k
        air_is_hot = True
    elif direction == HEAT_ONLY:
        active = inlet.temperature_k < ambient_temperature_k
        air_is_hot = False
    else:
        raise ValueError("ambient exchangers are one-way devices: use COOL_ONLY or HEAT_ONLY")

    if not active or ntu <= 0.0:
        outlet = state_ph(p_out, inlet.enthalpy_j_per_kg, fluid)
        return Process(kind, inlet, outlet)

    _, outlet, _ = _counterflow_air_duty(
        inlet, ambient_temperature_k, inf, p_out, fluid, ntu,
        air_is_hot_side=air_is_hot,
    )
    return Process(
        kind, inlet, outlet,
        # q is whatever the enthalpy change turns out to be; by (1) with w = 0.
        heat_to_air_j_per_kg=outlet.enthalpy_j_per_kg - inlet.enthalpy_j_per_kg,
    )


def water_ratio_for_duty(
    target_duty_j_per_kg_air: float,
    inlet: State,
    water_inlet_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    ntu: float,
    max_ratio: float,
) -> tuple[float, float]:
    """Invert an interheater: how much water do I need to deliver exactly this duty?

    Returns ``(ratio, achievable_duty)``. If even ``max_ratio`` cannot reach the
    target, returns ``(max_ratio, duty_at_max_ratio)`` - the caller must check.

    HOW IT SOLVES, AND WHY NOT PURE ALGEBRA
    ---------------------------------------
    Duty is a monotonically increasing, saturating function of r. The NTU
    effectiveness depends on r through the capacity ratio, so the inverse is
    refined numerically against the same forward model used by the plant -
    specifically against :func:`_counterflow_air_duty`, the duty core of the
    forward model, evaluated without paying for the unused outlet state.

    We seed with a capacity-rate estimate, then refine with a few Illinois
    (modified regula-falsi) steps. The seed makes it fast - typically 2-4 refinement
    steps rather than the ~60 a cold bisection needs, which matters because this runs
    inside the coupled water-ratio optimiser and a slow inverse made the outer solve
    unnecessarily expensive. The refinement makes it correct - the answer comes from
    the same duty law the solver uses to build the real exchanger process.

    Saturation is real and must be handled: past the point where the water becomes
    the larger capacity rate, pouring in more stops helping, because the AIR-side
    capacity rate then limits the transfer.
    """
    if target_duty_j_per_kg_air <= 0.0 or max_ratio <= 0.0:
        return 0.0, 0.0

    p_out = inlet.pressure_pa * (1.0 - pressure_drop)

    def duty_at(ratio: float) -> float:
        if ratio <= 0.0 or water_inlet_temperature_k <= inlet.temperature_k:
            return 0.0
        duty, _, _ = _counterflow_air_duty(
            inlet, water_inlet_temperature_k, ratio * WATER_CP_J_PER_KGK,
            p_out, fluid, ntu, air_is_hot_side=False, with_state=False,
        )
        return duty

    duty_max = duty_at(max_ratio)
    if duty_max <= target_duty_j_per_kg_air:
        # Even all the water in the tank is not enough - the air simply cannot be
        # heated this far. Hand back everything and let the caller raise the flag.
        return max_ratio, duty_max

    # --- Analytic seed. Assume the WATER is the smaller capacity rate (true whenever
    # the exchanger is not saturated, which is exactly the regime we are solving in),
    # so duty is linear in r:
    #
    #   Q ~= eps(r) r cp_w (T_w,in - T_a,in)
    #
    span = water_inlet_temperature_k - inlet.temperature_k
    if span <= 0:
        return 0.0, 0.0
    guess = target_duty_j_per_kg_air / (WATER_CP_J_PER_KGK * span)

    low, high = 0.0, max_ratio
    f_low = -target_duty_j_per_kg_air              # duty(0) - target  < 0
    f_high = duty_max - target_duty_j_per_kg_air   # > 0, checked above

    ratio = min(max(guess, 1e-9), max_ratio)
    for _ in range(40):
        duty_ratio = duty_at(ratio)
        f_ratio = duty_ratio - target_duty_j_per_kg_air
        if abs(f_ratio) <= 1e-6 * target_duty_j_per_kg_air:
            return ratio, duty_ratio

        if f_ratio < 0:
            low, f_low = ratio, f_ratio
            f_high *= 0.5          # the Illinois fix: stops one endpoint from sticking
        else:
            high, f_high = ratio, f_ratio
            f_low *= 0.5

        denominator = f_high - f_low
        nxt = 0.5 * (low + high) if abs(denominator) < 1e-30 else (low * f_high - high * f_low) / denominator
        # Regula falsi can wander outside the bracket on badly-scaled problems; if it
        # does, fall back to the midpoint for that step. Guarantees convergence.
        ratio = nxt if low < nxt < high else 0.5 * (low + high)
        if high - low < 1e-9 * max(1.0, max_ratio):
            break

    return ratio, duty_at(ratio)


def cascade_station_duty(
    water_air_mass_ratio: float,
    inlet_temperature_k: float,
    outlet_temperature_k: float,
) -> float:
    """Duty of ONE user exchanger in the descending plant-water cascade.

        Q_station = r_trunk . cp . (T_in - T_out)                              (20)

    ``r_trunk`` is the flow through THIS station, not the plant's inventory: the
    trunk thins by one bleed every time an expansion stage takes what it needs,
    and thickens again when a colder storage level joins.  Using the inventory
    here would sell heat the exchanger never saw.

    The user side is a slave and is solved once for the whole cascade rather
    than per station, because it is ONE counter-current stream through all of
    them; see :meth:`caes.plant.CAESPlant._build_offtake_taps`.
    """
    if water_air_mass_ratio <= 0.0 or outlet_temperature_k >= inlet_temperature_k:
        return 0.0
    return (
        water_air_mass_ratio
        * WATER_CP_J_PER_KGK
        * (inlet_temperature_k - outlet_temperature_k)
    )
