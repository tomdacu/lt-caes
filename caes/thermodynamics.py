"""Air-property access and turbomachinery component models.

SCOPE
-----
Every function here is a *steady-flow, open-system* component model written on a
per-kilogram-of-air basis.  There is no time domain and no mass inventory: the
whole plant is analysed for 1 kg of air pushed into the cavern and later pulled
back out.  All extensive quantities therefore carry the unit ``J/kg-air``.

SIGN CONVENTION (used consistently across the whole package)
------------------------------------------------------------
``Process.work_j_per_kg`` and ``Process.heat_to_air_j_per_kg`` are both written
from the point of view of the *air stream*:

    w > 0   work done ON the air      (compressor)
    w < 0   work done BY the air      (expander)
    q > 0   heat added TO the air     (reheater)
    q < 0   heat removed FROM the air (intercooler)

With that convention the steady-flow energy equation for every component is the
single identity

    h_out - h_in = q + w                                                    (1)

and :attr:`caes.models.Process.first_law_residual_j_per_kg` is exactly the
left-minus-right of (1).  It must stay at machine zero; the tests assert it.
Kinetic and potential energy terms are neglected (standard for turbomachinery
at these scales).

PROPERTIES
----------
Properties come from CoolProp, so the working fluid is a *real* fluid, not an
ideal gas: cp varies with temperature and pressure, and at 100 bar the
compressibility of air is far enough from 1 that ideal-gas relations (the
familiar ``T2/T1 = (p2/p1)^((k-1)/k)``) would introduce percent-level errors.
That is why every state change below is done through enthalpy and entropy
rather than through polytropic temperature ratios.

PROPERTY FRONT END
------------------
Production runs default to one cached ``CoolProp.AbstractState`` per fluid.
The alternative string-based ``PropsSI`` front end can be selected for a full
diagnostic A/B run.  Both select CoolProp's HEOS backend and therefore the same
equations of state; the switch is intended to expose any numerical/API-path
difference, not to change the physical model.  The ``AbstractState`` object is
stateful, so every low-level helper updates it immediately before reading it.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from functools import lru_cache
from typing import Iterator

from CoolProp import (
    AbstractState,
    HmassP_INPUTS,
    PQ_INPUTS,
    PSmass_INPUTS,
    PT_INPUTS,
    QT_INPUTS,
)
from CoolProp.CoolProp import PropsSI

from .models import Process, State


class PropertyAPI(str, Enum):
    """CoolProp front end used for pure-fluid property calls.

    Both choices use the same HEOS equations of state.  This selector exists
    to make their numerical equivalence and performance measurable end to end;
    it is not a choice between two physical plant models.
    """

    ABSTRACT_STATE = "abstract_state"
    PROPS_SI = "props_si"


_PROPERTY_API: ContextVar[PropertyAPI] = ContextVar(
    "caes_property_api", default=PropertyAPI.ABSTRACT_STATE
)


def current_property_api() -> PropertyAPI:
    """Return the property front end selected for the current solve context."""

    return _PROPERTY_API.get()


@contextmanager
def using_property_api(api: PropertyAPI | str) -> Iterator[None]:
    """Select one CoolProp front end for every property call in this context."""

    selected = PropertyAPI(api)
    token = _PROPERTY_API.set(selected)
    try:
        yield
    finally:
        _PROPERTY_API.reset(token)


@lru_cache(maxsize=4)
def property_backend(fluid: str) -> AbstractState:
    """One shared CoolProp low-level interface per fluid.

    ``AbstractState`` construction parses the fluid and loads its EOS tables
    once; afterwards each state fix is a plain ``update``.  The instance is
    shared, not copied, so callers must consume the values immediately after
    their ``update`` - which every function in this module does.
    """
    return AbstractState("HEOS", fluid)


def state_pt(pressure_pa: float, temperature_k: float, fluid: str) -> State:
    """Fix a state from pressure and temperature (the natural inputs for a boundary condition)."""
    return _state_pt_cached(
        pressure_pa, temperature_k, fluid, current_property_api()
    )


@lru_cache(maxsize=65_536)
def _state_pt_cached(
    pressure_pa: float,
    temperature_k: float,
    fluid: str,
    property_api: PropertyAPI,
) -> State:
    """Exact API-keyed cache for the solver's repeated boundary states."""

    if property_api is PropertyAPI.PROPS_SI:
        enthalpy, entropy = PropsSI(
            ["Hmass", "Smass"], "P", pressure_pa, "T", temperature_k, fluid
        )
        return State(pressure_pa, temperature_k, float(enthalpy), float(entropy))
    backend = property_backend(fluid)
    backend.update(PT_INPUTS, pressure_pa, temperature_k)
    return State(pressure_pa, temperature_k, backend.hmass(), backend.smass())


def state_ph(pressure_pa: float, enthalpy_j_per_kg: float, fluid: str) -> State:
    """Fix a state from pressure and enthalpy.

    This is the natural pairing after an energy balance: (1) hands us ``h_out``
    and the component's pressure behaviour hands us ``p_out``, so (p, h) closes
    the state without ever needing to guess a temperature.
    """
    return _state_ph_cached(
        pressure_pa, enthalpy_j_per_kg, fluid, current_property_api()
    )


@lru_cache(maxsize=65_536)
def _state_ph_cached(
    pressure_pa: float,
    enthalpy_j_per_kg: float,
    fluid: str,
    property_api: PropertyAPI,
) -> State:
    """Exact API-keyed cache for repeated energy-balance outlet states."""

    if property_api is PropertyAPI.PROPS_SI:
        temperature, entropy = PropsSI(
            ["T", "Smass"], "P", pressure_pa, "Hmass", enthalpy_j_per_kg, fluid
        )
        return State(
            pressure_pa, float(temperature), enthalpy_j_per_kg, float(entropy)
        )
    backend = property_backend(fluid)
    backend.update(HmassP_INPUTS, enthalpy_j_per_kg, pressure_pa)
    return State(pressure_pa, backend.T(), enthalpy_j_per_kg, backend.smass())


def air_cp(pressure_pa: float, temperature_k: float, fluid: str) -> float:
    """Isobaric specific heat of the working fluid at (p, T) [J/(kg K)].

    Exposed for the heat-exchanger models, whose epsilon-NTU algebra needs a
    heat-capacity rate.  At 100-300 bar the real-fluid cp varies appreciably
    across an exchanger, so callers iterate this over the exchanger's mean
    temperature rather than trusting the inlet value.
    """
    return _air_cp_cached(
        pressure_pa, temperature_k, fluid, current_property_api()
    )


@lru_cache(maxsize=131_072)
def _air_cp_cached(
    pressure_pa: float,
    temperature_k: float,
    fluid: str,
    property_api: PropertyAPI,
) -> float:
    """Exact API-keyed cache for repeated epsilon-NTU cp relocation."""

    if property_api is PropertyAPI.PROPS_SI:
        return float(
            PropsSI("Cpmass", "P", pressure_pa, "T", temperature_k, fluid)
        )
    backend = property_backend(fluid)
    backend.update(PT_INPUTS, pressure_pa, temperature_k)
    return backend.cpmass()


def _isentropic_enthalpy(pressure_pa: float, entropy_j_per_kgk: float, fluid: str) -> float:
    """h(p, s) - the discharge enthalpy of a reversible adiabatic machine."""
    return _isentropic_enthalpy_cached(
        pressure_pa, entropy_j_per_kgk, fluid, current_property_api()
    )


@lru_cache(maxsize=65_536)
def _isentropic_enthalpy_cached(
    pressure_pa: float,
    entropy_j_per_kgk: float,
    fluid: str,
    property_api: PropertyAPI,
) -> float:
    """Exact API-keyed cache for repeated turbomachinery inlet states."""

    if property_api is PropertyAPI.PROPS_SI:
        return float(
            PropsSI("Hmass", "P", pressure_pa, "Smass", entropy_j_per_kgk, fluid)
        )
    backend = property_backend(fluid)
    backend.update(PSmass_INPUTS, pressure_pa, entropy_j_per_kgk)
    return backend.hmass()


def water_saturation_temperature_k(
    pressure_pa: float, api: PropertyAPI | None = None
) -> float:
    """Pure-water saturation temperature at pressure, using the selected API."""

    selected = current_property_api() if api is None else PropertyAPI(api)
    if selected is PropertyAPI.PROPS_SI:
        return float(PropsSI("T", "P", pressure_pa, "Q", 0.0, "Water"))
    backend = property_backend("Water")
    backend.update(PQ_INPUTS, pressure_pa, 0.0)
    return float(backend.T())


def water_saturation_pressure_pa(
    temperature_k: float, api: PropertyAPI | None = None
) -> float:
    """Pure-water saturation pressure at temperature, using the selected API."""

    selected = current_property_api() if api is None else PropertyAPI(api)
    if selected is PropertyAPI.PROPS_SI:
        return float(PropsSI("P", "Q", 0.0, "T", temperature_k, "Water"))
    backend = property_backend("Water")
    backend.update(QT_INPUTS, 0.0, temperature_k)
    return float(backend.p())


def compress(inlet: State, outlet_pressure_pa: float, efficiency: float, fluid: str) -> Process:
    """Adiabatic compression at a given *isentropic* (not polytropic) efficiency.

    The isentropic efficiency of a compressor is defined as the ideal work over
    the actual work, both to the same discharge pressure:

        eta_is = (h_is - h_in) / (h_out - h_in)

    where ``h_is = h(p_out, s_in)`` is the discharge enthalpy of a reversible
    adiabatic machine.  Solving for the real discharge enthalpy:

        h_out = h_in + (h_is - h_in) / eta_is                                (2)

    Because the machine is adiabatic, q = 0 and (1) reduces to w = h_out - h_in,
    which is what we store.  Note this is the *fluid-side* (aerodynamic) work;
    mechanical and electrical drive-train losses are NOT modelled, so the
    round-trip efficiency reported by this package is a shaft-to-shaft figure
    and will read optimistically against a plant's grid-to-grid number.

    Caveat for future maintainers: for a multi-stage machine at high pressure
    ratio, the *polytropic* efficiency is the more honest constant to hold fixed
    across stages, because isentropic efficiency degrades with pressure ratio
    (the "reheat effect"). Holding eta_is constant per stage, as we do, slightly
    flatters machines with few stages. If you ever compare stage counts on
    equal footing, switch to a polytropic model here.
    """
    if outlet_pressure_pa <= inlet.pressure_pa:
        raise ValueError("compressor outlet pressure must exceed inlet pressure")
    h_is = _isentropic_enthalpy(outlet_pressure_pa, inlet.entropy_j_per_kgk, fluid)
    h_out = inlet.enthalpy_j_per_kg + (h_is - inlet.enthalpy_j_per_kg) / efficiency
    outlet = state_ph(outlet_pressure_pa, h_out, fluid)
    return Process("compression", inlet, outlet, work_j_per_kg=h_out - inlet.enthalpy_j_per_kg)


def expand(inlet: State, outlet_pressure_pa: float, efficiency: float, fluid: str) -> Process:
    """Adiabatic expansion at a given isentropic efficiency.

    For a turbine the efficiency is inverted relative to a compressor - actual
    work over ideal work - because now the ideal machine is the one that gives
    the *most* work:

        eta_is = (h_in - h_out) / (h_in - h_is)
        h_out  = h_in - eta_is * (h_in - h_is)                                (3)

    ``w = h_out - h_in`` is therefore negative, i.e. work leaves the air. The
    caller (:mod:`caes.plant`) flips the sign once, at the top level, when it
    reports "expansion work output".
    """
    if outlet_pressure_pa >= inlet.pressure_pa:
        raise ValueError("expander outlet pressure must be below inlet pressure")
    h_is = _isentropic_enthalpy(outlet_pressure_pa, inlet.entropy_j_per_kgk, fluid)
    h_out = inlet.enthalpy_j_per_kg - efficiency * (inlet.enthalpy_j_per_kg - h_is)
    outlet = state_ph(outlet_pressure_pa, h_out, fluid)
    return Process("expansion", inlet, outlet, work_j_per_kg=h_out - inlet.enthalpy_j_per_kg)


def throttle(
    inlet: State,
    outlet_pressure_pa: float,
    fluid: str,
    kind: str = "throttling",
) -> Process:
    """Isenthalpic pressure reduction through a valve, with no shaft work."""

    if outlet_pressure_pa >= inlet.pressure_pa:
        raise ValueError("throttle outlet pressure must be below inlet pressure")
    outlet = state_ph(outlet_pressure_pa, inlet.enthalpy_j_per_kg, fluid)
    return Process(kind, inlet, outlet)


def exchange_with_environment(
    inlet: State,
    target_temperature_k: float,
    pressure_drop: float,
    fluid: str,
    kind: str,
) -> Process:
    """Equilibrate the stored air with the cavern rock at constant pressure.

    This idealised "hits its target temperature" exchanger is now used ONLY for
    the cavern, where the stored air slowly drifts to rock temperature during
    the (unmodelled) dwell between charge and discharge.  The rock mass is so
    large that treating it as an infinite isothermal boundary is exact for our
    purposes, so no UA or effectiveness is needed.

    The coolant/ambient recovery body is NOT modelled here: E-303 lives in
    :class:`caes.heat_exchangers.CoolantAmbientExchanger`, sized by the same
    NTU discipline as every air/coolant exchanger.

    The cavern is free to heat the air as well as cool it: it is a huge
    isothermal rock mass, and the component degenerates into a plain pressure
    drop when the air already sits at the target, which is isenthalpic (a
    throttle: q = w = 0, so h_out = h_in by (1)).
    """
    p_out = inlet.pressure_pa * (1.0 - pressure_drop)

    active = abs(target_temperature_k - inlet.temperature_k) > 1e-9

    outlet = state_pt(p_out, target_temperature_k, fluid) if active else state_ph(p_out, inlet.enthalpy_j_per_kg, fluid)
    return Process(
        kind,
        inlet,
        outlet,
        # q is whatever the enthalpy change turns out to be; by (1) with w = 0.
        heat_to_air_j_per_kg=outlet.enthalpy_j_per_kg - inlet.enthalpy_j_per_kg,
    )
