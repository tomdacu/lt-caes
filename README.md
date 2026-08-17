# Normalized CAES Simulator - AD / LTA / LTHP-CAES

A steady-state simulator that compares three compressed-air energy-storage
concepts on one normalized basis:

- **AD-CAES (ambient diabatic)** rejects compression heat through
  finite-NTU ambient coolers. On discharge it uses only ambient heat, takes the
  largest anti-icing-safe turbine pressure drop, and throttles the remainder.
- **LTA-CAES (low-temperature adiabatic CAES)** stores compression heat in a
  two-tank sensible-coolant loop and returns it through parallel interheaters.
- **LTHP-CAES (low-temperature heat and power CAES)** adds heat export through
  the E-302 taps ahead of the coolant interheaters.

Its primary purpose is **configuration brainstorming and thermodynamic
screening**. Each simulated point represents a different candidate plant whose
components may be resized to meet the selected performance classes. The tool
is intended to reveal promising architectures, parameter interactions,
feasibility boundaries and questions worth taking into detailed design. It is
not an off-design digital twin of one fixed installation, and it does not yet
perform mechanical sizing, costing or dispatch simulation.

## This is a heat-and-power plant, not a store with a heating bolt-on

LTHP-CAES sells two products, electricity and heat, and the heat user is
described by three inputs: the temperature it wants, the temperature it hands
back, and the finite-NTU performance class of its exchanger.
Those three numbers describe a district-heating network, an industrial process
loop, an absorption chiller, a greenhouse or a drying plant equally well.
District heating is the most likely application in northern Europe - see the
[Denmark note](docs/research/LTHP_CAES_AND_DENMARK.md) - but it is **not the
model's subject**, and nothing in the solver assumes it.

The configuration says so: `heat_offtake = "heat_user"` with
`heat_user_supply_temperature_c`, `heat_user_return_temperature_c` and
`heat_user_exchanger_ntu`. Files written against the older `district_heating`
temperature names still load; obsolete approach inputs are ignored with a
deprecation warning because kelvin and NTU are not interchangeable.

Direct air/ambient reheat belongs to AD-CAES alone. The adiabatic concepts take
every joule of turbine reheat from the coolant loop, while one optimized
heat-only E-303 may warm a selected sub-ambient coolant-return suffix; the AH-20x ambient
preheaters they used to carry have been removed, because they were up to eight
extra high-pressure gas/ambient exchangers and the only ones in the model that
moved heat into the air without paying an air-side pressure drop.

The project builds on published LTA-CAES research, beginning with the name and
low-temperature two-tank concept described by Wolf and Budt; see the
[literature map](docs/research/LITERATURE.md). Literature **AA-CAES** means
advanced adiabatic CAES and must not be confused with this repository's
**AD-CAES**, which is ambient diabatic.

All three concepts use the same wet-expander envelope: +10 degC where liquid
condensation is permitted, or the local frost point plus 10 K in dry sub-zero
operation. Results are normalized to one kilogram of stored air. The model
reports real-fluid states, shaft work, heat/exergy flows, optimized tank
temperatures, stage water ratios, and constraint diagnostics - not plant
power, equipment size, time evolution, or cost.

## Quick start

Use an existing global Python environment with the declared dependencies; on
this machine do not create a local environment or cache under OneDrive.

```powershell
python -m caes
python -m caes.cli --config counterflow_example_config.json --explain-config
python -m caes.cli --config heat_and_power_example_config.json
python -m pytest
```

The GUI is the primary interface. The CLI supports reproducible batch runs and
can save the thermodynamic plots, P&ID, and both Sankey diagrams:

```powershell
python -m caes.cli --config example_config.json `
  --plot artifacts/cycles.png `
  --pid artifacts/pid.png `
  --sankey artifacts/sankeys.png
```

## Single-store coolant cascade

The adiabatic concepts always use one mixed hot coolant tank and one mixed cold
coolant tank. `coolant_cascade_groups = K` controls discharge routing only; it
never splits the stored coolant into temperature levels.

`1 <= K <= expander_stages`. Expansion stages are assigned to K contiguous,
duty-balanced groups; the compressor count does not bound this discharge-side
parameter.

### The discharge cascade

For K groups there are exactly K serial user exchangers. All coolant crosses
the first; group 0 then bleeds its required interheater flow, and only the
remainder crosses the second. The pattern ends with exchanger K-1 and the final
bleed. There is no K+1 exchanger after the trunk has been emptied.

```text
mixed hot TES -> HX 0 -> bleed 0 -> HX 1 -> bleed 1 -> ... -> final HX -> final bleed
```

Every station receives the same solved plant-side temperature drop. Because
trunk flow decreases after each bleed, the first exchanger transfers the most
heat and successive duties decrease.

The user side is **one counter-current stream in series** through all the
stations: in at the coldest at its return temperature, out of the hottest at
its supply temperature, so the cold stations preheat and only the top one makes
the final lift. A parallel connection cannot work - it would demand
an effectiveness unavailable at the configured NTU, and the cold ones cannot
offer it. Both streams are represented as constant-`cp` liquids, so each station's
profile is two straight lines and its narrowest gap is at one of its ends;
checking both ends of every station therefore checks the whole cascade. See
[the architecture specification](docs/12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)
and [the solver note](docs/08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md).

## Coolant-loop optimization

The LTA/LTHP coolant cycle is closed inside the solve:

1. choose a candidate cold-tank temperature;
2. iterate each charging ratio toward capacity-rate matching;
3. mix the charging returns into one hot-tank state;
4. group the stages, solve the K post-user supply temperatures, and make the
   group bleeds consume exactly the stored inventory;
5. enforce wet-expander, direct coolant minimum/maximum, icing, and
   finite-HX temperature constraints;
6. optimize the heat-only E-303 return suffix, mix it with bypass returns, and
   check that E-303 plus tank standing reproduce the trial cold-tank state.

With a heat user, the cascade sells whatever the exact turbine duties left in
the trunk. Without one, E-302 is absent, the complete inventory reaches the
interheaters, and candidates are ranked by real multi-stage expansion work.

The loop is closed on the **cold-tank temperature**. Branch-selective E-303
cannot be reconstructed from one raw mixed mean, so every trial retains the
individual return flows and temperatures through the placement decision.

Normally the complete coolant inventory crosses the interheaters. If an LTA
inventory needs a rejection sink to close, it is infeasible: E-303 is never
silently reversed into a cooler.

Near-parallel heat-exchanger T-Q profiles are a reported design diagnostic,
not a hidden ranking rule. The selected objective always ranks feasible
designs. When no closed design is feasible, the final error reports the
binding constraints observed across the inventory search and gives
cause-specific remedies.

See the [optimization workflow](docs/04_OPTIMIZATION_WORKFLOW.md).

## Thermal store and exchangers

Every air/coolant and air/ambient exchanger uses the same finite counter-current
NTU model. The atmosphere is the `Cr = 0` limit, so its effectiveness is
`1 - exp(-NTU)`. Air heat capacity is iterated at the exchanger mean
temperature. For balanced capacity rates, `epsilon = NTU/(1+NTU)`; NTU=3
therefore removes about 75% of the inlet temperature gap rather than reaching
the cold-stream inlet exactly.

NTU is intentionally held constant as an exchanger **performance class**.
Every different candidate plant implicitly receives a resized exchanger with
`UA_design = NTU * C_min,design`; the optimization is therefore a comparison of
complete plant designs at equal dimensionless exchanger performance, not an
off-design simulation of one fixed core at different flows. Geometry, area,
part-load correlations and cost are outside this thermodynamic layer.

Every coolant state must satisfy
`coolant_minimum_temperature_c <= T_coolant <= coolant_maximum_temperature_c`.
The direct limits are checked at every branch return and mixed tank state. A
negative minimum is only a low-freezing coolant
sensitivity: real glycol or brine design also needs mixture properties,
corrosion checks, and pump work.

Both tanks use the same normalized conductance and standing time. Each
lumped-capacitance standing period obeys

```text
Q_dot_loss = UA_tank (T_tank - T_ambient)
T_after = T_ambient + (T_before - T_ambient)
          exp[-UA_tank t / (r_total cp_coolant)]
```

The hot tank stands between charge and discharge; the cold tank stands between
E-303 and the next charge. `thermal_storage_tank_ua_w_per_k` is normalized to
one kilogram of stored air, so
`UA_normalized = UA_physical / stored_air_mass`.

## Heat destination and coolant balance

```text
LTA:
hot store -> parallel interheaters -> E-303 -> cold tank

LTHP, K discharge groups and one mixed hot store:
hot TES -> E-302A -> group-0 bleed -> E-302B -> group-1 bleed -> ...
              |                              |
              +---- one user stream <--------+   (counter-current)
      ... -> final E-302x -> final group bleed -> interheaters
          -> mixed return -> E-303 -> cold TES

air side:
cavern -> E-20x coolant interheater -> turbine
```

The coolant first-law balance has the following destination terms:

```text
Q_recovered + Q_E303,ambient
    = Q_turbine_reheat + Q_user
    + Q_hot_tank_standing + Q_cold_tank_standing
```

`E-303` is one finite heat-only coolant/ambient exchanger. The solver evaluates
every ordered return suffix, warms the maximum-duty sub-ambient mixture, and
then mixes it with the warmer bypass returns. The P&ID is generated after the
solve and draws that actual cutoff.

There is no upstream surplus-rejection cooler. With LTHP, the whole temperature
drop the cascade takes out of the trunk is useful heat for the user. Residual
low-temperature return energy may be recovered at E-303. Every user station
must fit `heat_user_exchanger_ntu`; requested temperatures are never silently
capped.

Because the user exchangers are the only thing that cools the trunk, no bleed
can be colder than `T_user,return`. A user whose return is hotter
than the mean supply the turbines need is therefore infeasible for a reason
that belongs to no individual exchanger, and it is reported as such rather than
as N separate interheater duty failures.

## Objectives and metrics

The concept policy is:

- AD-CAES: maximum electrical RTE; the direct turbine/throttle solve has no
  independent water-allocation loop;
- LTA-CAES: maximum electrical RTE;
- LTHP-CAES: maximum useful-energy delivery ratio.

Only `max_electric_efficiency` and `max_combined_energy_delivery` are active
objectives. Old JSON containing `max_total_exergy_efficiency` loads with a
deprecation warning and maps to the appropriate active objective. Useful
exergy efficiency remains a reported guard metric.

The delivery ratio `(W_exp + Q_DH) / W_comp` is the single energy metric. Its
denominator is the electricity the plant buys and nothing else: harvested
ambient energy is free, so neither the AD-CAES ambient reheat duty nor the
energy an exhaust below intake enthalpy carries in is charged to it. It may therefore
exceed 100%, like a heat-pump COP, and it is not a thermodynamic efficiency.
The energy Sankey is the closed boundary balance; the exergy books are the
bounded accounting and stay below unity. Electrical RTE remains shaft work out
over shaft work in. Definitions and accounting rules are canonicalized in
[Objectives, metrics, and exergy accounting](docs/03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md).

## AD-CAES pressure control

```text
cavern air -> finite-NTU ambient reheater
           -> turbine to the lowest safe intermediate pressure
           -> isenthalpic throttle to scheduled stage pressure
           -> optional ambient anti-icing trim
```

If the full pressure ratio is safe, the valve is bypassed. If no useful safe
turbine drop exists, the complete stage is throttled. Throttling produces no
shaft work and its lost-work opportunity is explicit exergy destruction.
There is no fuel, combustor, LHV input, or chemical-exergy term.

## GUI, diagrams, and accounting

The GUI recalculates in a spawned background process and retains only the
newest requested result. It includes a configuration-derived P&ID, T-s, h-s,
and p-h traces, composite curves, stage tables, component energy/exergy books,
an energy Sankey and an exergy Sankey (Grassmann diagram).

The window is one draggable split between the plots and the tables, with the
plots taking the larger share by default: a sixteen-panel composite figure and
a six-row table do not want the same amount of height.

### Every coolant temperature is drawn on the cycle plots

The T-s, h-s and p-h traces carry dotted isotherms for the mixed cold tank, the
one mixed hot store, every distinct post-user group supply, and every distinct
interheater return. Supply rungs are discharge states, not stored TES levels.

### One composite-curve panel per exchanger, cascade included

The composite tab draws **every** coolant-coupled exchanger, and the user's
cascade stations come first, in the order the trunk meets them: `E-302A` is the
station that hands the user its supply temperature, and the last letter is the
one that meets its return. One station keeps the plain `E-302` tag. Each panel
plots the station's OWN end temperatures rather than the user's overall span -
only the top station reaches the supply temperature, and drawing the others
against it would invent an approach violation the hardware does not have.

### The Sankeys run inlet to outlet, one arrow per station

Both diagrams draw the stream from the air intake to the stack rather than
summing everything into two columns with an opaque box between them. A
four-stage plant has eight machines and eight exchangers, and lumping them into
"compression work" and "heat rejected" throws away exactly the per-stage
structure the solver works so hard to produce. Every compressor, intercooler,
interheater and expander therefore gets **its own arrow**, tagged with the
equipment number, and the band's thickness at any point is the energy the
stream is carrying there - so the picture cannot lie about the balance.

Naming three times as many things at readable size would crowd the picture past
usefulness, so each arrow carries a very small tag and **the full description
with its number appears when the cursor is over it**. Saved PNGs have no
cursor, so they keep the tags alone.

The energy band is the AIR stream and closes the first law on it exactly. The
coolant loop's own disposition - to the turbines, to the heat user, to E-303, to
tank standing - is reported in the caption rather than drawn on the same band,
because the heat that leaves the air at E-10x and returns at E-20x is already
on it at both ends and drawing what the loop then does with the difference
would count the same joules twice.

The Grassmann balance is

```text
W_compression = W_expansion + B_heat_user + destruction + exhaust loss + residual
```

The residual should remain within about 1 J/kg-air. Heat sent to the ambient
dead state - in an AD-CAES cooler, a tank standing loss, or E-303 in either
direction - is classified as destruction. Heat received by a real external user
is a product. Only exhaust air leaves as intact exergy loss.

### The P&ID follows the configuration

Change `coolant_cascade_groups` and the P&ID retains one TK-301 while drawing
exactly K serial E-302 user exchangers. Add a heat off-take and the cascade plus
external user appear; remove it and they vanish. `AH-20x` exists only in AD-CAES, where ambient reheat is the
sole discharge heat source, and `E-20x` now means a coolant interheater and
nothing else - the two used to share a tag band, which made "the reheater" mean
two different devices depending on which concept was drawn.

## Documentation map

Start from the [hierarchical documentation map](docs/00_DOCUMENTATION_MAP.md).
It routes from plant concepts and theory to the nested solver algorithms,
performance registry, reproducible benchmarks, usage and research notes.

The performance/theory entry points are:

- [Theory and design objectives](docs/11_THEORY_AND_DESIGN_OBJECTIVES.md)
- [Proposed single-store coolant cascade](docs/12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)
- [Optimization workflow](docs/04_OPTIMIZATION_WORKFLOW.md)
- [Performance and optimization](docs/09_PERFORMANCE_AND_OPTIMIZATION.md)
- [Benchmarks and regression protocol](docs/10_BENCHMARKS_AND_REGRESSION.md)
- [Detailed algorithm index](docs/algorithms/README.md)

Research notes:

- [Research map](docs/research/README.md)
- [LTA-CAES literature](docs/research/LITERATURE.md)
- [People, groups, and related software](docs/research/PEOPLE_AND_GROUPS.md)
- [LTHP-CAES and the Denmark opportunity](docs/research/LTHP_CAES_AND_DENMARK.md)
- [LTHP-CAES heat rejection and cogeneration](docs/research/LTHP_CAES_HEAT_REJECTION_AND_COGENERATION.md)

## Model boundary

CoolProp supplies dry-air properties. Moisture is a separate diagnostic:
latent heat, finite droplet separation, and two-phase machinery physics remain
outside the energy balance.

Water vapour in compressed air is **not** treated as pure-component water
vapour. The equilibrium content is `f(T,p) · p_sat,pure(T)`, where `f` is the
enhancement factor: 1.004 at 1 bar, 1.10 at 30 bar, 1.39 at 100 bar. Ignoring
it understated the stored moisture by 28% at 100 bar and the wet-expander
anti-icing floor by 3 to 4 K at every stage — the wrong direction for a safety
screen. `f` is tabulated once from CoolProp's humid-air backend (agreement
better than 0.2% over its validity range) and applied in the single place the
forward map and the dew/frost-point inversion share, so the two can never
disagree. Above 10 MPa the backend has no validated data and `f` is
extrapolated; that is an admitted extrapolation for 100 to 300 bar caverns and
it errs toward more water, never less. The 0.1 wt% maximum-condensate screen bounds only
the discharge-side dry-air approximation; charge-side latent heat is a
separate admitted limitation. Dryers and liquid separators are deliberately
omitted from the simplified P&ID but remain required by the documented
moisture design. The thermal-loop coolant is represented as an incompressible
constant-`cp` sensible-storage medium with direct minimum and maximum
temperature limits; pressure, phase behaviour, pump work and variable liquid
properties are outside the current model.
