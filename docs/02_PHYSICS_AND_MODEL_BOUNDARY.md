# Physics and model boundary

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Children:** [Moisture and wet expansion](06_MOISTURE_DEW_POINT_AND_WET_EXPANSION.md) · [Algorithm index](algorithms/README.md)  
> **Related:** [Theory and objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md)

## Boundary

The model exists to brainstorm and screen alternative CAES configurations.
Each configuration is treated as its own design-point plant and its components
are implicitly resized to satisfy the selected dimensionless performance
classes. Results compare thermodynamic concepts and feasibility boundaries;
they are not an off-design map of one fixed set of hardware.

The solver follows one kilogram of **dry** air through steady-flow components. The
cavern is a fixed-pressure, ambient-rock-temperature boundary. There is no time
domain, power rating, tank geometry, component cost, or water-pump model.

For the plant-level definition of AD-CAES, LTA-CAES, and LTAHP-CAES,
including left-to-right exergy flowcharts, read
[Plant concepts and architectures](01_PLANT_CONCEPTS_AND_ARCHITECTURES.md).

Dry air means humidity remains outside the **energy and exergy balance**: no
latent heat distorts the cooling curves and no two-phase mass changes the
turbomachinery work. A separate moisture post-processor now carries the
configured ambient humidity through the calculated cooler outlets, assumes an
ideal liquid separator after each charge intercooler and the final aftercooler,
and draws the resulting pressure dew/frost boundary. It is a plant-risk
diagnostic, not a coupled humid-air property model. The wet-rated expander may
cross a liquid dew point: its operating minimum is +10 degC in the liquid
region and local frost point plus 10 K in dry sub-zero operation. A 0.1 wt%
possible-condensate screen bounds only the discharge-side dry-air
approximation; omitted charge-side latent heat is a separate limitation. Local blade-wall
temperatures, finite separator efficiency, droplet transport and cavern
rehumidification remain outside the solver. See
[the unified moisture and wet-expander basis](06_MOISTURE_DEW_POINT_AND_WET_EXPANSION.md).

Shared physical constants live in `caes/constants.py`. Every solver-side
temperature limit uses one numerical tolerance,
`TEMPERATURE_LIMIT_TOLERANCE_K = 1e-4 K`; it protects floating-point boundary
checks and does not relax the physical constraint.

## Turbomachinery

CoolProp supplies real-air enthalpy and entropy. Stage outlet enthalpies use
the standard isentropic-efficiency definitions:

```text
h2,compressor = h1 + (h2s - h1) / eta_c
h2,expander   = h1 - eta_t (h1 - h2s)
```

Pressure ratios include each exchanger pressure drop and land exactly at the
storage and ambient boundaries.

### CoolProp backend and diagnostic API selector

`PropsSI` and `AbstractState` are **not two thermodynamic solvers in this
project**. They are the high- and low-level front ends to the same CoolProp
`HEOS` backend. With the same fluid, input pair and reference state they solve
the same Helmholtz equation of state. Production uses a retained
`AbstractState("HEOS", fluid)` instance because its integer input-pair update
avoids repeated string parsing and backend construction. The diagnostic path
uses `PropsSI` to prove that this implementation choice does not change the
plant result. This is also the distinction made by CoolProp's official
[low-level-interface documentation](https://coolprop.org/coolprop/LowLevelAPI.html):
the high-level interface calls the low-level machinery internally, while a
retained state removes repeated construction and string-processing overhead.

One selector covers every pure-air and pure-water property call made by the
physical solver:

```python
CAESPlant(config, property_api="abstract_state").run()  # default
CAESPlant(config, property_api="props_si").run()        # diagnostic A/B path
```

The CLI exposes the same switch as
`caes-simulate --property-api {abstract_state,props_si}`. The selector is held
in a context-local value for the duration of one solve and is also part of the
whole-plant result-cache key. Water saturation, dew/frost inversion and the
enhancement table have API-specific cache keys, so a second A/B run cannot
silently reuse a pure-water value calculated by the first.

The call mappings are:

| State/property | `AbstractState` path | `PropsSI` path |
|---|---|---|
| air `(P,T) -> h,s` | `update(PT_INPUTS)` then `hmass(), smass()` | outputs `Hmass, Smass` at `P,T` |
| air `(P,h) -> T,s` | `update(HmassP_INPUTS)` then `T(), smass()` | outputs `T, Smass` at `P,Hmass` |
| air `(P,s) -> h_is` | `update(PSmass_INPUTS)` then `hmass()` | output `Hmass` at `P,Smass` |
| air `cp(P,T)` | `update(PT_INPUTS)` then `cpmass()` | output `Cpmass` at `P,T` |
| water `P,Q=0 -> T_sat` | `update(PQ_INPUTS)` then `T()` | output `T` at `P,Q=0` |
| water `T,Q=0 -> P_sat` | `update(QT_INPUTS)` then `p()` | output `P` at `T,Q=0` |

`HAPropsSI` is deliberately common to both paths. CoolProp's humid-air model
does not have an interchangeable `AbstractState` front end, and here it is used
only to tabulate the moisture enhancement factor. Plotting also retains its
own vectorized `PropsSI` calls; those generate chart coordinates after the
plant has been solved and cannot alter energy, exergy, constraints or the
selected optimum.

The A/B validation made with the locally installed CoolProp 7.2.0 covered
`Air` from 1 to 300 bar and 180 to 1050 K, including `(P,T)`, `(P,h)`, `(P,s)`
and `cp`, plus pure-water saturation. The returned values were bit-for-bit
equal. Complete AD-CAES, LTA-CAES, LTAHP-CAES and counterflow results were also
equal as full result dataclasses. The four-level LTAHP-CAES case followed
the same 6,792 discharge-train evaluations and gave the same objective; its
actual state envelope was 1.013 to 102.04 bar and 248.78 to 574.55 K. This is
inside the primitive-property test envelope.

The dependency currently says `CoolProp>=6.4`, so it does **not** make results
reproducible across future CoolProp releases. A research release must pin and
record the exact CoolProp version/revision and retain numerical golden cases.
The API-equivalence tests prove equivalence within one installed release; they
do not prove that two different CoolProp releases contain identical fluid data
or flash algorithms.

The complete comparison can be repeated without writing project caches:

```powershell
python -B scripts/compare_property_apis.py --config heat_and_power_example_config.json
python -B scripts/compare_property_apis.py `
  --config counterflow_example_config.json
```

The second command is intentionally a complete K=4 plant comparison rather
than a property-call microbenchmark.

## Finite counter-flow exchangers, one code path

Every exchanger in the plant - air/water on the LTA/LTAHP side and
air/atmosphere on the AD-CAES side - uses the same finite counter-current
model:

```text
Q = epsilon C_min (T_hot,in - T_cold,in)
C_water = r cp,water                 r = kg-water / kg-air
NTU = UA / C_min
Cr = C_min / C_max
epsilon = [1 - exp(-NTU(1-Cr))] / [1 - Cr exp(-NTU(1-Cr))]
```

The atmosphere is an *infinite* capacity rate, so the ambient coolers and
reheaters are the `Cr = 0` limit of the same formula:

```text
epsilon_ambient = 1 - exp(-NTU)
```

No exchanger is idealized to "hit a target temperature": every approach is paid
for with `UA`, so all plant architectures are sized by the same discipline.

The air `cp` entering `C_min` is evaluated at the exchanger **mean**
temperature, iterated two or three times against the solved outlet, because at
100-300 bar the real-fluid cp varies enough across one exchanger to move the
duty. The linear estimate `T_out = T_in +/- Q/cp` is used to re-locate cp; the
final outlet state is always a full real-fluid `(p, h)` fix, so the first law
closes exactly on every component.

When the optimized coolant profiles are nearly parallel, `Cr ≈ 1`, and the
effectiveness reduces to `NTU / (1 + NTU)`. NTU=3 therefore retains about one
quarter of the inlet temperature gap; approaching the secondary inlet
temperature requires a substantially higher NTU, hence a larger `UA`.

No duty is capped at an assumed tank temperature. Each exchanger reports the
water outlet resulting from its finite effectiveness and branch ratio.

### Confirmed design interpretation: fixed NTU and implicit sizing

The current optimization holds the configured `NTU` fixed while it varies the
water/air ratio `r`. Because `C_min` changes with `r` and
`NTU = UA/C_min`, this means the implied `UA` also changes between candidates.
This is intentional: the input selects an exchanger **performance class**, and
the exchanger is implicitly sized for every different candidate plant so that
its design-point NTU remains in that class. At the selected operating point,
each core therefore implies

```text
UA_design,i = NTU_selected C_min,design,i
```

The optimizer is comparing complete plant designs whose exchangers are resized
to provide the same dimensionless thermal performance; it is not sending
different candidate flows through one pre-existing core. This makes comparisons
between pressures, stage counts, water inventories and architectures consistent
at equal exchanger class.

Consequently, `heat_exchanger_ntu` is a plant-design assumption, not an
off-design control variable. Fixed geometry, part-load behaviour, fouling,
velocity-dependent heat-transfer coefficients, pressure-drop/area trade-offs
and exchanger cost remain outside the present model. A later equipment-sizing
layer should report the implied `UA_design` and convert it into surface area and
cost, but it must preserve the NTU class selected here unless the research
question explicitly changes that class.

## AD-CAES ambient reheat and throttling

AD-CAES uses the same wet-expander lower envelope as LTA/LTAHP-CAES:

```text
T_hard,i = 0 degC        if T_phase >= 0 degC
           T_frost,i     if T_phase <  0 degC
T_min,i  = T_hard,i + 10 K
```

Each stage first takes all finite-NTU ambient heat available. The solver then
tests a complete turbine expansion. If unsafe, it finds the lowest intermediate
pressure at which the turbine outlet just reaches `T_min`; an isenthalpic valve
completes the remaining pressure drop. If the inlet is already too close to the
boundary for any turbine work, the whole stage is throttled. A zero-pressure-
drop ambient trim reheater can restore the 10 K margin after the valve, but the
valve outlet itself may never cross the unmargined freezing/frost hard floor.

```text
cavern -> withdrawal scrubber -> ambient reheat
       -> maximum safe turbine expansion -> h=constant throttle
               -> moisture separator/demister -> optional ambient anti-icing trim
```

The throttle obeys `h_out = h_in`, `q = 0`, `w = 0`. Its physical-exergy drop
is component destruction: it is the work opportunity deliberately sacrificed
to remain fuel-free. There is no burner, fuel energy, fuel mass or chemical
exergy anywhere in the model.

## LTAHP-CAES process order

With a heat user, the hot TES first crosses the `E-302` taps; only the remaining
temperature level reaches the turbine coolant interheaters. The air-side order at
every adiabatic expansion stage is simply:

```text
previous turbine outlet -> finite coolant interheater -> turbine
```

There is no ambient exchanger on the adiabatic air side. AD-CAES is the only
concept that scavenges ambient heat, and there it is the sole discharge heat
source. Ambient heat is a positive energy input, but at the selected dead-state
temperature its heat-transfer exergy is approximately zero.

## Coupled charging design

For a candidate cold temperature and total normalized water throughput, every
intercooler branch starts at `T_cold`. The solver iterates the real sequential
train toward heat-capacity matching:

```text
cp_air,effective,i = Q_i / (T_air,in,i - T_air,out,i)
r_parallel,i = cp_air,effective,i / cp_water
sum(r_c,i) = r_total
```

The final projection preserves `r_total` exactly. Variable air properties
retain a small curvature in the full T-Q profile. Water branch returns are not
generally forced equal: they join an ideal, adiabatic mixer before the hot
tank. With the constant liquid-water heat capacity used by every HX, its
enthalpy balance is exactly:

```text
r_total = sum(r_c,i)
Q_recovered = sum(Q_c,i)
T_hot = T_cold + Q_recovered / (r_total cp,water)
      = sum(r_c,i T_water,out,i) / r_total
```

The discharge returns are mixed by the same mass-weighted rule before E-303.
This is not an unweighted temperature average. Exergy destroyed by collapsing
different branch temperatures into one tank state is explicitly reported as
`hot_tank_mixing` and `cold_tank_mixing`. This is a conservative perfectly
mixed two-tank model; it does not represent thermoclines or
temperature-selective tank manifolds.

## Direct coolant temperature limits

The coolant loop uses two explicit limits instead of a pressure/saturation
correlation:

```text
T_coolant,min <= T_coolant <= T_coolant,max
```

`coolant_minimum_temperature_c` defaults to -80 degC and
`coolant_maximum_temperature_c` defaults to 200 degC as broad direct screening
inputs. Every charging-HX outlet, mixed tank
state, cold state, and interheater return is checked directly. A negative
minimum is only a screening input for an externally characterized low-freezing
fluid. The solver deliberately retains a constant 4180 J/kg/K liquid
heat-capacity approximation internally; density, viscosity, conductivity,
phase behaviour and pump work are not inferred from the limits.

## Physical standing loss of both tanks

Each tank is treated as one lumped thermal capacitance during its standing
period. Its instantaneous loss to ambient is:

```text
Q_dot_loss = UA_tank (T_tank - T_ambient)
C_tank dT_tank/dt = -Q_dot_loss
C_tank = r_total cp,water
```

Integration between the filled and emptied equilibrium states gives:

```text
T_after = T_ambient
        + (T_before - T_ambient)
          exp[-UA_tank t_storage / (r_total cp,water)]

Q_storage_loss = r_total cp,water (T_before - T_after)
```

No time grid or transient tank state is introduced. The same normalized UA and
standing time apply to BOTH tanks, at the two moments each actually holds the
inventory: the hot tank stands between charge and discharge, the cold tank
between discharge and the next charge. The hot-tank result lowers
`T_hot,available`. On the return path, one heat-only `E-303` warms the selected
group of COLDEST sub-ambient returns at `epsilon = 1 - exp(-NTU_return)`, the
warmed group remixes with the bypass returns, and that mixture then crosses
`E-304`'s cold side before the tank:

```text
T_group,out = T_ambient
            + (T_group,in - T_ambient) exp(-NTU_return)

T_recuperated = T_final_mix + Q_recup / (r_total cp,water)

T_cold,next   = T_ambient + (T_recuperated - T_ambient) * tank_decay
```

Without a heat user there is no `E-304`, `Q_recup` is zero, and the mixed return
reaches the tank unchanged.

Returns at or above ambient bypass E-303. Its absorbed ambient heat and exergy
destruction are reported separately from cold-tank standing loss. The standing
loss is signed: a cold tank below ambient leaks heat in.
On a real plant, the normalized result scales as

```text
Q_dot_E303 = m_dot_dry_air q_E303
UA_E303 ~= NTU_return r_total cp,water m_dot_dry_air
```

when the water side is the minimum heat-capacity rate used by this model.
Fan power, water-pump power, cooling-tower approach and seasonal wet/dry-bulb
limits are not yet deducted; they must be added when E-303 is sized for the
70 MW plant.
`UA_tank` is specified on the normalized one-kilogram-air basis,
in W/K per kg-air. For a physical plant:

```text
UA_tank,normalized = UA_tank,physical / stored_air_mass
```

## Wet-rated expander outlet constraint

The former configurable 5 °C floor is removed. The vapour content guaranteed
by the final charge aftercooler and ideal separator is held fixed during
discharge. For every stage:

```text
p_v,i = p_out,i w_sep / (0.621945 + w_sep)
p_sat(T_phase,i) = p_v,i
T_hard,i = 273.15 K      if T_phase,i >= 273.15 K
           T_phase,i     if T_phase,i <  273.15 K
T_out,min,i = T_hard,i + 10 K
```

`T_phase` is a PDP above 0 °C and a frost point below it. The wet-rated
machine may cross a positive PDP, but every body is followed by a
separator/demister. Later, lower-pressure stages can operate dry below zero
while remaining above their frost boundary. For each pressure stage the solver
finds the required pre-expansion enthalpy and `Q_i`.
With a heat user, the one mixed hot store is cooled through exactly one user
exchanger and then withdrawn stage by stage inside `E-304`. Each extraction sits
a single common margin above the air temperature its own stage must produce:

```text
T_supply,g = T_demand,g + m
```

`m` is refined until the inverse-HX bleeds consume the complete stored coolant
flow, which also fixes what `E-302` receives, since the first extraction IS the
trunk inlet. The demand profile is raised to its non-increasing suffix maximum
first, because a progressively withdrawn trunk cannot serve a later stage hotter
than an earlier one. Finite-NTU feasibility is checked on `E-302` and on every
`E-304` zone separately.

At each extraction the finite-HX equation is inverted independently for every
stage to obtain `r_h,i`. The physical closed-cycle constraints are:

```text
sum(r_h,i) = r_total
tank_decay(E304(final_mix(E303(coldest_group(returns))))) = T_cold
```

Every kilogram of transferred water crosses one active interheater core, so
`sum(r_h,i)` is exactly the complete normalized throughput. With a heat user,
the margin root closes bleed mass inside the discharge solve and the outer root
reproduces the cold-tank state. With no heat
user, E-302 is absent for every objective, every stage is served from the one
mixed hot store, and candidate allocations of
all conserved water are compared by real multi-stage expansion work. That
path roots on the actual routed-return/tank closure. E-303 never becomes a
rejection cooler.

The outer search uses the capacity-rate scale `cp_air/cp_coolant ~= 0.25` and
additional inventory candidates because direct coolant limits and finite-HX
constraints can leave a narrow feasible window. With no heat user it refines
around maximum RTE; HX profile spread remains a reported equipment metric.
The inner cold-loop search also locates the precise start
of each feasible temperature window before bracketing its mass-balance root.
The actual cold-tank closure, rather than a loose proxy residual, is the final
acceptance test.

Strongly unequal compressor and expander stage counts can make the two required
capacity-matched throughput sums incompatible. In that case the solver reports
the design as infeasible instead of silently producing strongly non-parallel
profiles or inventing an unmodelled water path. When roots do exist, endpoint
T-Q spread remains a reported optimization metric rather than an independent
feasibility limit: maximum off-take duty, extreme NTU and hot seasonal conditions can
prevent tight capacity matching even while all finite-NTU station checks remain
feasible.

## Stored-heat destination

With a heat user, the group bleeds contain exactly the minimum moisture-safe
turbine heat demand. The user receives the upstream trunk drops:

```text
Q_user = r_total cp,water (T_hot,available - T_return) - sum(Q_i)
```

For one mixed store this identity fixes the total once the closed return and
inventory are known. What the architecture decides is how that total SPLITS
between the user and internal recuperation, and the split follows from the
extraction margin rather than being chosen: the user takes everything above the
first extraction. See
[document 12](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md). The separate
Heat-only `E-303` remains explicit and can add only sub-ambient ambient heat;
it cannot dispose of residual heat.

With no heat user, rejecting available exergy would produce nothing. E-302 is
therefore absent and the one mixed hot-store inventory feeds the interheaters.
Finite NTU and the configured coolant temperature limits bound the extra
turbine heat. Because electricity is then the only useful output, all
objectives use the same physical dispatch.

If every full-inventory allocation leaves heat that has no modeled sink, the
LTA point is infeasible. The solver does not hide that heat in E-303 or relax a
wet-expander/coolant-temperature limit.

For every heat-user station, finite counterflow effectiveness is enforced:

```text
epsilon_required = Q / [Cmin (T_hot,in - T_user,in)]
epsilon_required <= epsilon_counterflow(NTU_user, Cmin/Cmax)
```

The user's water is one counter-current stream through all stations. Its flow
is derived from total duty and the configured supply/return span.

If either condition fails, the solver raises an exception instead of silently
lowering the requested network supply temperature. Increasing network mass flow
can change the duty and network temperature rise, but it cannot reverse either
terminal temperature ordering.

Water energy closes as:

```text
Q_recovered + Q_E303,ambient
            = Q_air_reheat + Q_user
            + Q_hot_tank_loss + Q_cold_tank_loss
```

There is no modeled ambient rejection path: any feasible E-302 temperature
drop is useful heat product, and E-303 appears only on the input side.

## Exergy

```text
air:   e = (h - h0) - T0(s - s0)
water: b = cp[(T - T0) - T0 ln(T/T0)]
eta_electric = W_expansion / W_compression                                    (shaft only)
eta_ex,total = (W_expansion + B_district) / W_compression
R_delivery = (W_expansion + Q_district) / W_compression
```

`R_delivery` is the single energy metric: an electricity-based sector-coupling
delivery ratio, not a thermodynamic efficiency. Its denominator is purchased
electricity only, so every ambient stream the plant harvests for free - the
AD-CAES ambient reheat duty and the energy carried in by an exhaust leaving
below intake enthalpy - stays out of it. It is therefore not bounded by one. The
exergy metric correctly assigns approximately zero exergy to heat received at
the ambient dead-state temperature, and is bounded by one. The closed first-law
boundary balance is the energy Sankey. See
[Objectives, metrics, and exergy accounting](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md#the-one-energy-metric-and-what-it-deliberately-excludes).

One classification, every concept. Finite HX temperature difference, pressure
loss, turbomachinery, throttling, tank mixing and tank standing leaks
appear as destruction. Heat pushed into the ambient dead state - AD-CAES
cooler heat, tank standing loss, or E-303 duty in EITHER direction - is
DESTRUCTION: the atmosphere is the dead state itself, so nothing usable crosses
the boundary. Warming a sub-ambient return destroys its cold exergy exactly as
cooling a hot one destroys its heat exergy.
Heat received by a real external heat user is a PRODUCT. Only the exhaust
air is an exergy loss, because it alone leaves the boundary still intact. The
reported residual audits the full Grassmann balance
`W_compression = products + destruction + losses`.

Only `max_electric_efficiency` and `max_combined_energy_delivery` are active
optimization objectives. Useful-exergy efficiency remains reported rather
than optimized. See
[Objectives, metrics, and exergy accounting](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md).

## Current limitations

- **dry-air thermodynamics with a humidity diagnostic**: calculated
  cooler/separator condensation and PDP/frost overlays do not yet feed latent
  heat, water mass, droplet carryover or real icing back into the cycle; a
  0.1 wt% maximum-possible-condensate screen limits the discharge-side
  approximation; charge-side latent heat remains separately omitted;
- the coolant has constant specific heat and direct temperature limits, but
  blend-dependent properties, phase behaviour, pressure-dependent liquid
  enthalpy and pump work are not modelled;
- tanks are perfectly mixed steady-state nodes;
- equal turbomachinery pressure ratios and constant isentropic efficiencies are
  design assumptions, not optimized maps;
- the wet-expander bulk-air envelope does not model local blade-wall icing;
- each heat-user tap is checked against a common finite-NTU performance class;
- the heat user is a normalized energy/exergy sink, not an economic model.
