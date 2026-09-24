# Theory and design objectives

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Children:** [Metrics and exergy](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) · [Physics boundary](02_PHYSICS_AND_MODEL_BOUNDARY.md) · [Algorithm index](algorithms/README.md)  
> **Related:** [Configuration logic](05_CONFIGURATION_LOGIC.md)

## What the program is for

The program is a normalized **brainstorming and configuration-screening tool**.
It asks which complete plant architecture is worth studying in higher fidelity.
It does not yet predict annual dispatch, component cost, cavern transients or
the off-design map of one purchased machine.

That distinction determines the interpretation of inputs. Holding NTU constant
means comparing exchanger designs from the same performance class while
implicitly resizing each candidate:

```text
UA_design = NTU_selected * C_min,design
```

It does not mean holding the physical `UA` of one exchanger constant while mass
flow and plant size change. A later fixed-hardware/off-design module would need
geometry, heat-transfer correlations, pressure-loss scaling and explicit mass
flow; it must not be mixed silently into this screening model.

## Three layers of objectives

The word “objective” currently covers three distinct questions. They must stay
separate.

1. **Physical closure:** mass, energy, coolant-loop temperature, pressure train,
   moisture-safe expansion and finite heat-transfer feasibility must all close.
   These are equations and hard constraints, not preferences.
2. **Configuration ranking:** among feasible normalized plants, maximize the
   selected useful product metric. This is the implemented optimizer.
3. **Research decision:** decide which architecture merits equipment sizing,
   cost, dynamics and experimental validation. The code supplies evidence but
   cannot make this multi-criteria decision from thermodynamics alone.

## Objective by architecture

| Architecture | Useful products in the present boundary | Normal screening objective | Why |
|---|---|---|---|
| AD-CAES (ambient diabatic) | electricity | electrical RTE | Ambient reheat is an external energy flow; the sold product is shaft/electric work |
| LTA-CAES (low-temperature adiabatic CAES) | electricity | electrical RTE | With no heat user, stored heat is valuable only insofar as it raises expansion work |
| LTAHP-CAES (low-temperature adiabatic heat and power CAES) | electricity and useful heat | useful-energy delivery ratio | The concept is explicitly sector-coupled and must not discard the heat product during ranking |

Useful-exergy efficiency is reported as the thermodynamic quality audit. It is
not the ranking objective, but it chooses the charge-water split of the
heat-user plant, because the delivery ratio values heat equal to electricity
and would reward spending electricity as heat
([document 14](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md)). Cost, equipment volume, `UA`, water
inventory, parasitic loads and deliverability duration are also not yet in the
objective, so an “optimal” result means optimal only inside this normalized
thermodynamic boundary.

## Boundary conditions that define feasibility

The major boundary conditions are:

- ambient intake temperature, pressure and humidity;
- cavern/storage pressure and staged pressure ratios;
- compressor and expander isentropic efficiencies;
- finite exchanger performance class (NTU) and pressure drops;
- direct coolant minimum and maximum temperatures;
- wet-expander liquid/frost anti-icing envelope;
- hot/cold store dwell and normalized loss coefficient;
- for LTAHP, heat-user supply/return temperatures and exchanger NTU class.

Changing any of these can change not only the metric but whether a topology is
feasible and which constraint is active. Sensitivity studies should therefore
report feasibility regions and binding constraints, not only a curve of RTE.

## What theory can simplify safely

Several first-principle relations remove numerical degrees of freedom:

- stage pressures follow a chosen equal pressure-ratio train;
- energy conservation fixes coolant return temperature once duty and water ratio
  are known;
- each stage's demand temperature is invariant, so the extraction ladder is a
  known profile plus ONE common margin rather than N free temperatures;
- raising that profile to its suffix maximum makes the ladder monotone by
  construction, so no ordering search is needed;
- constant-`cp` liquid-coolant mixing is exactly enthalpy-weighted in this model;
- an optimal E-303 group is downward closed in temperature, so sorting the
  returns once reduces `2**N` subsets to N thresholds;
- under the heat-user (minimum-duty) dispatch the discharge side depends on the
  inventory and the stored humidity only, so the cold tank is explicit and the
  whole plant is one-dimensional in the inventory
  ([document 14](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md)). The coolant-loop
  root disappears there;
- a closed first-law identity,
  `W_exp + Q_user = W_comp + Q_amb + (h0 - h_exh) - Q_ac - L_tank`, explains
  every delivery ratio below one (aftercooler rejection) and shows that the
  user temperatures enter the delivery ratio only through feasibility.

Other unknowns cannot yet be removed honestly. Finite-NTU effectiveness depends
on capacity ratio, air `cp` varies with state, and active coolant-limit and
finite-NTU constraints create piecewise branches. The inverse-HX sizing, the
extraction-margin mass root and the inventory search therefore remain
numerical. Under the electricity-first (absorbing) dispatch the discharge
depends on the hot store, E-303 and dwell couple the return to the next
charge, and the cold-loop closure stays a genuine root.

## Measured sensitivity of the delivery ratio J (LTAHP)

One parameter at a time from the reference plant (85.8 bar, 6+6 stages,
efficiencies 0.85, NTU 5, 80/45 °C user, 15 °C ambient), each point solved to
its own optimum inventory. Energy terms in kJ/kg-air.

| change | J | RTE | eta_ex | Q_amb | h0 - h_exh | Q_ac |
|---|---:|---:|---:|---:|---:|---:|
| reference | 1.075 | 0.551 | 0.625 | 44.4 | 38.6 | 42.2 |
| storage 30 / 150 / 300 bar | 1.097 / 1.054 / 1.025 | 0.574 / 0.541 / 0.536 | 0.647 / 0.613 / 0.604 | 34.7 / 45.6 / 39.6 | 30.2 / 41.8 / 43.4 | 26.1 / 52.8 / 64.5 |
| stages 3 / 4 / 8 / 10 | 0.943 / 0.986 / 1.154 / 1.172 | 0.506 / 0.505 / 0.552 / 0.534 | 0.568 / 0.573 / 0.637 / 0.624 | 0 / 19.6 / 77.9 / 89.7 | 38.6 | 75.3 / 67.0 / 34.6 / 35.2 |
| exchanger NTU 3 / 10 / 30 / 100 | 1.010 / 1.128 / 1.171 / 1.187 | 0.533 / 0.565 / 0.572 / 0.575 | 0.600 / 0.644 / 0.656 / 0.661 | 25.4 / 61.2 / 76.9 / 82.5 | 38.6 | 58.4 / 31.2 / 25.3 / 23.0 |
| E-303 NTU 1 / 2 / 20 | 1.050 / 1.066 / 1.075 | 0.554 / 0.552 / 0.551 | 0.624 / 0.625 / 0.625 | 28.3 / 38.7 / 44.7 | 38.6 | ~40 |
| machine efficiency 0.80 / 0.90 / 0.95 | 1.075 / 1.073 / 1.073 | 0.483 / 0.625 / 0.700 | 0.566 / 0.688 / 0.753 | ~45 | 38.6 | ~43 |
| ambient 0 / 30 °C | 1.031 / 1.153 | 0.548 / 0.551 | 0.637 / 0.609 | 31.9 / 75.6 | 32.4 / 45.1 | 47.9 / 34.8 |
| user 60/30, 95/75, 110/90 °C | 1.070 / 1.072 / 1.040 | 0.549 / 0.543 / 0.511 | 0.598 / 0.647 / 0.631 | ~45 / 45.7 / 39.8 | 38.6 | 46.7 / 44.5 / 54.8 |
| coolant minimum 0 °C (instead of -80) | 1.057 | 0.552 | 0.624 | 32.8 | 38.6 | 40.0 |
| pressure drops 0 / 5 % (instead of 2 %) | 1.074 / 1.076 | 0.585 / 0.503 | 0.654 / 0.583 | ~44 | 38.6 | ~42 |
| combined: 200 bar, 10+10, NTU 30, E-303 NTU 20, eta 0.90, drops 1 %, user 60/30 | **1.215** | 0.655 | 0.707 | 134.5 | 42.8 | 52.7 |

Formal bounds, ideal-component results and the heat-pump reading are in
[document 16](16_PERFORMANCE_LIMITS.md).

How to read it, through the identity
`J = 1 + (Q_amb + (h0 - h_exh) - Q_ac - L_tank) / W_comp`:

- **J measures free ambient energy, not machine quality.** Machine efficiency
  and pressure drops barely move J (1.073-1.076) while RTE moves by 20 points:
  every irreversibility turns electricity into heat, and J counts that heat
  at par. Always read J next to RTE or eta_ex.
- **What raises J is what lets the plant act as a heat pump**: more expansion
  stages and better exchangers make colder interheater returns, so E-303
  harvests more ambient heat (`Q_amb` 0 kJ with 3 stages, 90 kJ with 10), and
  they shrink the aftercooler loss `Q_ac`. A warmer ambient helps for the same
  reason. A coolant that must stay above 0 °C caps the harvest.
- **Higher storage pressure lowers J**, because the aftercooler loss grows
  faster than the harvest.
- **An upper bound in this model.** `Q_ac` and `L_tank` are non-negative, and
  the exhaust cannot fall below the anti-icing floor, so
  `J <= 1 + (Q_amb + (h0 - h_exh)) / W_comp`. For the combined case that is
  `1 + (134.5 + 42.8) / 579.9 = 1.31`: even an ideal aftercooler would leave J
  near 1.3. The practical optimum found so far is 1.22 (1.215 above, 1.222 at
  200 bar, 8+8, NTU 100, coolant minimum -30 °C). Pushing further means more
  stages and exchanger area, which this model does not cost.

## Recommended theory-led sensitivity program

For each parameter, separate three outputs:

1. feasible/infeasible and the binding physical constraint;
2. energy/exergy/product metrics for the feasible set;
3. numerical work, to reveal solver pathologies independently of plant physics.

The first sweep should cover storage pressure, stage count, compressor/expander
efficiency, HX NTU class, pressure loss, coolant limits, normalized
tank UA, duration, humidity and LTAHP supply/return/user NTU. Use dimensionless
groups where possible: overall pressure ratio, per-stage pressure ratio,
capacity ratio, NTU, temperature approach ratios and normalized storage loss.

Each claimed trend should then be classified as:

- a theorem/identity of the current model;
- an observed monotone trend over a stated domain;
- a local sensitivity near one design;
- or a hypothesis requiring a wider sweep or external evidence.

This classification is essential before presenting results to a research
institute: demonstrations validate an implementation over sampled points;
theory states why the trend should persist and where it can fail.

## Parameter-influence hypotheses to test

This table is the theoretical starting point for demonstrations. “Expected” is
not “guaranteed monotone”: coupled closures and active constraints can reverse a
local trend.

| Parameter | First-order theoretical effect | Why the result may be non-monotone or change branch |
|---|---|---|
| Storage pressure | Raises compression work, available expansion pressure ratio and compression temperature | Thermal limits, real-gas properties, moisture, throttling and stage pressure drops change together |
| Compressor stages | With effective intercooling, approaches isothermal compression and tends to reduce work | Every added cooler adds pressure loss and changes coolant allocation/equipment count |
| Expander stages | Reheat between stages can recover more stored heat and work | Added interheater pressure loss and moisture-safe duty can offset the gain |
| Compressor efficiency | Directly reduces actual compression work at fixed pressure ratio | It also reduces recovered compression heat and can lower LTAHP heat delivery |
| Expander efficiency | Directly raises shaft work | A larger enthalpy drop lowers turbine outlet temperature and can demand more anti-icing reheat |
| Intercooler/interheater NTU class | Improves approach/effectiveness for a given capacity ratio | Candidate `UA` is resized; water-temperature grade and required flow change, so cost is not represented |
| Ambient E-303 NTU | Warms the selected sub-ambient return suffix more strongly toward ambient | It never rejects heat; changed recovery alters the next charge and can move the optimal suffix |
| Pressure drop | Normally degrades work recovery and raises compression burden | It also changes downstream temperature and moisture constraints, so feasibility can switch abruptly |
| Conserved coolant inventory | More heat capacity improves air cooling but lowers coolant temperature grade | This is the core interior trade-off; direct coolant limits, finite-HX duty asymptotes and heat-user approaches create a bounded feasible band |
| Optimized E-303 group | Selects the coldest-return group with maximum ambient pickup | The O(N log N) optimum excludes fixed-area cost, pumps/fans and cross-connected piping |
| Charge-water split (heat user) | Exergy-optimal: hot users switch the first intercooler off and give the last one more water | Chosen by useful exergy because the delivery ratio would reward electric heating; limited by the coolant ceiling |

| Normalized tank UA × duration | Exponentially relaxes stored water toward ambient | Hot and cold tank losses can have different signs relative to ambient; duration is not yet a dispatch variable |
| Heat-user supply temperature | Raises delivered heat quality/exergy | Requires a hotter store and tighter hot-end approach, shrinking feasibility |
| Heat-user return temperature | A colder return permits more useful duty | It may be unrealistic for the intended network and changes the cold-end terminal constraint |
| Heat-user exchanger NTU | Higher NTU raises available station effectiveness | Constant NTU implicitly resizes area; capital cost and off-design controllability are not represented |
| Ambient humidity | Raises stored water vapour/condensate and the wet-expander protection burden | The dry-air energy model omits latent heat and separator dynamics, so this is primarily a safety/domain screen |
| Ambient temperature | Changes compression inlet work, dead-state exergy, E-303 suffix duty and heat-user margins | Seasonal operation is not modeled; one ambient point can favor a different architecture |

The demonstration scripts should state the domain swept and mark every point by
binding constraint. Plotting only surviving RTE values would hide the most
important design information: where and why an architecture stops existing.

## Limits before research-grade claims

The present tool still omits or simplifies component costs, motor/generator and
auxiliary efficiencies, pump/fan power, cavern mass/time dynamics, real gas
mixtures with moisture in the energy balance, droplet separation and two-phase
machinery, exchanger geometry/fouling/control, pipe pressure losses, TES
stratification dynamics and annual heat/electricity demand. These omissions do
not invalidate configuration brainstorming, but they bound the language of any
conclusion: results identify promising concepts and dominant constraints, not a
bankable plant design.
