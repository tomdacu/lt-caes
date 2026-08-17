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

## One user exchanger and one extraction exchanger

The adiabatic concepts always use one mixed hot coolant tank and one mixed cold
coolant tank. With a heat user, the discharge side is two bodies:

```text
mixed hot TES
  -> E-302   one user exchanger, crossed by the WHOLE inventory
  -> E-304   one counter-current body, one bleed per expansion stage,
             trunk fully consumed at the last one
```

### Why the trunk is staged

Every expansion stage must reach its own air temperature before its turbine,
fixed by the anti-icing envelope. Those demands fall steeply along the train:

```text
  stage          1      2      3      4      5      6
  demand [C]   65.95  61.24  50.89  41.20  32.13  23.63
```

Feeding all of them from one temperature means sizing it for stage one and
handing stage six 44 K it cannot use. E-304 places each bleed a single common
margin `m` above its own stage's demand, and recuperates the descent between
bleeds into the plant's own coolant return, on its cold side:

```text
  T_extraction,g = T_demand,g + m
  sum_g b_g( T_demand,g + m ) = R_total      <- m is rooted on this
  T_trunk,in     = T_demand,0 + m            <- so E-302 gets everything above it
```

Because the first extraction IS the trunk inlet, one root closes the whole
discharge network: there is no separate split to choose between what is sold and
what is recuperated.

A progressively withdrawn trunk only gets colder, so where the raw demand
profile is not monotone - it is not, at 300 bar with eight stages - it is raised
to its suffix maximum and two stages share one nozzle.

### What it buys, and what it costs

The user's return temperature is no longer chained to what the turbines need.
Under the former serial cascade the trunk had to stay above the user's return
all the way to the last bleed, so a hot return squeezed the turbines out; a
95/75 C user cost 6 points of delivery ratio and 110/90 C was infeasible.
Measured against that frozen baseline (commit `22b7bb7`):

| user [C] | cascade `R` | E-304 `R` |
|---|---:|---:|
| 80/45 | 1.0693 | 1.0744 |
| 95/75 | 1.0078 | 1.0624 |
| 100/80 | 0.9820 | 1.0379 |
| 110/90 | *infeasible* | 0.9847 |

Recuperation does warm the cold tank and does cost compressor work. It is paid
for by the returns: matched supplies let the interheater returns come back
genuinely cold, and E-303 then harvests a third more free ambient energy. The
worst T-Q endpoint spread also falls from 40.4 K to 11.2 K. See
[the architecture specification](docs/12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)
and [the measured results](docs/08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md#5-measured-against-the-frozen-cascade).

`coolant_cascade_groups` is dormant. It still loads, and is still range checked,
so configuration files written against the cascade keep working.

## Coolant-loop optimization

The LTA/LTHP coolant cycle is closed inside the solve:

1. choose a candidate cold-tank temperature;
2. iterate each charging ratio toward capacity-rate matching;
3. mix the charging returns into one hot-tank state;
4. root the common extraction margin so the bleeds consume exactly the stored
   inventory, which also fixes what E-302 sells;
5. enforce wet-expander, direct coolant minimum/maximum, icing, and
   finite-HX temperature constraints, including a pinch check at every node of
   E-304 rather than only at its two ends;
6. select the heat-only E-303 group over the coldest returns, mix it with the
   bypass returns, recuperate that mixture through E-304, and check that the
   result plus tank standing reproduces the trial cold-tank state.

With a heat user, E-302 sells the band above the first extraction. Without one,
both E-302 and E-304 are absent, the complete inventory reaches the interheaters
at the one stored temperature, and candidates are ranked by real multi-stage
expansion work.

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

LTHP, one mixed hot store:
hot TES -> E-302 (whole trunk) -> E-304 -> bleed 1 -> bleed 2 -> ... -> bleed N
              |                     ^                                     |
        one user stream             |                              interheaters
        (counter-current)           |                                     |
                                    +----- E-303 <---- mixed return <-----+
                                    |
                                 cold TES

air side:
cavern -> E-20x coolant interheater -> turbine
```

The coolant first-law balance has the following destination terms:

```text
Q_recovered + Q_E303,ambient
    = Q_turbine_reheat + Q_user
    + Q_hot_tank_standing + Q_cold_tank_standing
```

`E-303` is one finite heat-only coolant/ambient exchanger. The solver sorts the
returns by temperature, warms the maximum-duty coldest group, and then mixes it
with the warmer bypass returns. The P&ID is generated after the solve and draws
that actual selection.

Note that `Q_recup`, the duty E-304 moves from the trunk into the return, does
not appear in the balance above. It is INTERNAL: the trunk's loss and the
return's gain are the same joules, so they cancel. What it changes is grade, and
the cold-tank temperature.

There is no surplus-rejection cooler anywhere. E-302 must fit
`heat_user_exchanger_ntu` and every E-304 zone must fit
`extraction_exchanger_ntu`; requested temperatures are never silently capped.

Because E-304 continues cooling the trunk below what E-302 took, a bleed CAN now
be colder than `T_user,return` - which is exactly the constraint the serial
cascade could not escape. What remains is an ordinary finite-area limit on one
body: a required effectiveness above one means E-302 would have to take the
trunk below its own cold-side inlet, and that is reported as such rather than
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

### One composite-curve panel per exchanger

The composite tab draws **every** coolant-coupled exchanger, and the single
`E-302` user station comes first, since it is the first thing the trunk meets
after the store. Each panel plots that body's OWN end temperatures.

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

Change the expander stage count and the P&ID keeps one TK-301 and one `E-302`
while redrawing `E-304` with exactly one extraction nozzle per stage. The body
is drawn TAPERED because that is its distinguishing feature: the trunk inside it
thins at every nozzle until it is exhausted. Add a heat off-take and both
exchangers plus the external user appear; remove it and all three vanish. `AH-20x` exists only in AD-CAES, where ambient reheat is the
sole discharge heat source, and `E-20x` now means a coolant interheater and
nothing else - the two used to share a tag band, which made "the reheater" mean
two different devices depending on which concept was drawn.

## Documentation map

Start from the [hierarchical documentation map](docs/00_DOCUMENTATION_MAP.md).
It routes from plant concepts and theory to the nested solver algorithms,
performance registry, reproducible benchmarks, usage and research notes.

The performance/theory entry points are:

- [Theory and design objectives](docs/11_THEORY_AND_DESIGN_OBJECTIVES.md)
- [Single-store extraction architecture (E-302 + E-304)](docs/12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)
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
