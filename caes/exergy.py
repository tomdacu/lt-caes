"""Exergy (availability) accounting.

WHAT EXERGY BUYS YOU HERE
------------------------
The first law says where the *energy* went; it cannot say where the *value*
went, and for a storage plant only value matters. 500 kJ of air at 100 bar and
500 kJ of water at 40 C are the same number and utterly different assets. Exergy
is the common currency: the maximum work recoverable from a stream by bringing
it reversibly to equilibrium with the dead state (T0, p0).

THE ACCOUNTING WE KEEP (Grassmann / Tsatsaronis convention)
-----------------------------------------------------------
    exergy IN  =  exergy PRODUCT  +  exergy DESTRUCTION  +  exergy LOSS        (6)

where exergy IN is the compression work, with the three right-hand terms kept
strictly separate because they mean different things to an engineer:

  PRODUCT     what you sell: expander shaft work, plus useful heat if the
              hot-water surplus is exported rather than dumped.
  DESTRUCTION irreversibility INSIDE a component - entropy generation.
              This is the term you attack with better hardware (higher effectiveness,
              better polytropic efficiency, less throttling).  Heat rejected to
              the ambient dead state also lands here: the atmosphere is the
              receiver, and heat accepted by the dead state carries no exergy
              away, so every joule of availability it held is destroyed in the
              rejecting cooler.
  LOSS        exergy that leaves the plant boundary still intact but unused -
              in practice just the exhaust air.  You attack this with a
              different *plant*, not better components: add a bottoming cycle,
              a district-heat offtake, a recuperator.

Keeping losses and destruction separate is what makes the residual returned by
the plant-level exergy summary a useful audit, and keeping the classification
identical across plant modes is what makes two architectures comparable.

DEAD STATE
----------
(T0, p0) = ambient temperature and pressure from the config. Note that we use
*physical* (thermo-mechanical) exergy for the air and water streams. The
fuel-free D-CAES working stream remains dry ``Air`` with unchanged composition.
"""

from __future__ import annotations

from functools import lru_cache
from math import log

from .heat_exchangers import WATER_CP_J_PER_KGK
from .models import Process, State
from .thermodynamics import state_pt


@lru_cache(maxsize=64)
def _dead_state(ambient_temperature_k: float, ambient_pressure_pa: float, fluid: str) -> tuple[float, float]:
    """(h0, s0) at the dead state.

    Cached because it is CONSTANT for a given configuration, yet air_exergy is called
    twice per process, for every process, for every one of the 81 points in the
    water-ratio optimiser - thousands of times, all asking CoolProp the identical
    question. Memoising it is worth several seconds on the heavier configurations and
    costs nothing: (T0, p0, fluid) fully determine the answer.
    """
    dead = state_pt(ambient_pressure_pa, ambient_temperature_k, fluid)
    return dead.enthalpy_j_per_kg, dead.entropy_j_per_kgk


def air_exergy(state: State, ambient_temperature_k: float, ambient_pressure_pa: float, fluid: str) -> float:
    """Specific physical exergy of the air stream [J/kg-air].

        e = (h - h0) - T0 (s - s0)                                            (7)

    Both a thermal and a mechanical contribution are inside (7) implicitly - it
    does not matter whether the air is valuable because it is hot or because it
    is squeezed, (7) prices both.

    e >= 0 always, and e = 0 only at the dead state. In particular COLD air has
    positive exergy: the exhaust leaving a D-CAES expander at -57 C is a genuine
    (if awkward) asset that this plant throws away, and (7) counts it.
    """
    h0, s0 = _dead_state(ambient_temperature_k, ambient_pressure_pa, fluid)
    return (state.enthalpy_j_per_kg - h0) - ambient_temperature_k * (state.entropy_j_per_kgk - s0)


def water_exergy(temperature_k: float, ambient_temperature_k: float) -> float:
    """Specific exergy of liquid water at T, per kg of WATER [J/kg-water].

    Incompressible liquid at (essentially) ambient pressure, constant cp:

        e = cp [ (T - T0) - T0 ln(T / T0) ]                                   (8)

    (8) is the integral of (1 - T0/T) dq - i.e. the Carnot-weighted heat content -
    and it is strongly convex: doubling the temperature *rise* above ambient more
    than doubles the exergy. Consequently, useful-heat exergy rewards temperature
    quality as well as the amount of exported heat.

    Multiply by the water/air mass ratio r to get J/kg-air, which is what the
    rest of the package works in. Callers must not forget that factor; every call
    site below does it explicitly.
    """
    ratio = temperature_k / ambient_temperature_k
    return WATER_CP_J_PER_KGK * ((temperature_k - ambient_temperature_k) - ambient_temperature_k * log(ratio))


def process_exergy_destruction(
    process: Process,
    ambient_temperature_k: float,
    ambient_pressure_pa: float,
    fluid: str,
) -> float:
    """Exergy destroyed inside one component [J/kg-air]. Always >= 0 by the second law.

    This is an exergy balance drawn around the component: everything in, minus
    everything out. The three branches below differ only in what "everything"
    contains.
    """
    air_in = air_exergy(process.inlet, ambient_temperature_k, ambient_pressure_pa, fluid)
    air_out = air_exergy(process.outlet, ambient_temperature_k, ambient_pressure_pa, fluid)

    if process.heat_exchanger:
        # AIR/WATER EXCHANGER - a closed box with two streams in and two out.
        #
        #   I = (e_air,in + r e_w,in) - (e_air,out + r e_w,out)                (9)
        #
        # Nothing crosses the boundary except the four streams, so whatever does
        # not come out was destroyed: by the finite temperature difference
        # between the streams (the dominant term) and by the air-side pressure
        # drop (secondary, but it is why increasing effectiveness has diminishing
        # returns - you pay in dP what you save in dT).
        hx = process.heat_exchanger
        water_in = hx.water_air_mass_ratio * water_exergy(hx.water_inlet_temperature_k, ambient_temperature_k)
        water_out = hx.water_air_mass_ratio * water_exergy(hx.water_outlet_temperature_k, ambient_temperature_k)
        destruction = air_in + water_in - air_out - water_out

    elif process.kind in {"compression", "expansion"}:
        # ADIABATIC MACHINE - work crosses the boundary, and work is pure exergy
        # (it is 100% available by definition), so it enters the balance at face
        # value with the sign convention of thermodynamics.py:
        #
        #   I = e_in + w - e_out                                              (10)
        #
        # Compressor: w > 0, you put in more work than the air gains in exergy.
        # Expander:   w < 0, the air loses more exergy than you extract as work.
        # Either way I > 0. I = T0 * s_gen, which is the aerodynamic loss priced.
        destruction = air_in + process.work_j_per_kg - air_out

    else:
        # AMBIENT-COUPLED EXCHANGER OR THROTTLE.
        #
        #   I = e_in - e_out                                                  (11)
        #
        # No work crosses either boundary. Heat exchanged with the ambient dead
        # state carries zero exergy; a throttle has q=0 as well. Therefore the
        # decrease in stream exergy is destruction in both cases. This exposes
        # the work opportunity deliberately sacrificed by anti-icing throttling.
        destruction = air_in - air_out

    # Clamp. Analytically this is already >= 0; numerically CoolProp's h and s
    # come from separate interpolations and can disagree in the last bits, which
    # shows up as I ~ -1e-9 on a bypassed component. Clamping keeps the reported
    # tables clean without hiding anything of physical size.
    return max(0.0, destruction)
