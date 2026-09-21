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
| LTHP-CAES (low-temperature heat and power CAES) | electricity and useful heat | useful-energy delivery ratio | The concept is explicitly sector-coupled and must not discard the heat product during ranking |

Useful-exergy efficiency is reported as the thermodynamic quality audit. It is
not the current ranking objective. Cost, equipment volume, `UA`, water
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
- for LTHP, heat-user supply/return temperatures and exchanger NTU class.

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
  returns once reduces `2**N` subsets to N thresholds.

Other unknowns cannot yet be removed honestly. Finite-NTU effectiveness depends
on capacity ratio, air `cp` varies with state, E-303 and dwell couple the return
to the next charge, and active coolant-limit/finite-NTU constraints create
piecewise branches. Inventory, cold-loop closure, inverse-HX sizing and the
extraction-margin mass root therefore remain numerical until stronger
monotonicity or convexity is proved over the complete admissible domain.

## Recommended theory-led sensitivity program

For each parameter, separate three outputs:

1. feasible/infeasible and the binding physical constraint;
2. energy/exergy/product metrics for the feasible set;
3. numerical work, to reveal solver pathologies independently of plant physics.

The first sweep should cover storage pressure, stage count, compressor/expander
efficiency, HX NTU class, pressure loss, coolant limits, normalized
tank UA, duration, humidity and LTHP supply/return/user NTU. Use dimensionless
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
| Compressor efficiency | Directly reduces actual compression work at fixed pressure ratio | It also reduces recovered compression heat and can lower LTHP heat delivery |
| Expander efficiency | Directly raises shaft work | A larger enthalpy drop lowers turbine outlet temperature and can demand more anti-icing reheat |
| Intercooler/interheater NTU class | Improves approach/effectiveness for a given capacity ratio | Candidate `UA` is resized; water-temperature grade and required flow change, so cost is not represented |
| Ambient E-303 NTU | Warms the selected sub-ambient return suffix more strongly toward ambient | It never rejects heat; changed recovery alters the next charge and can move the optimal suffix |
| Pressure drop | Normally degrades work recovery and raises compression burden | It also changes downstream temperature and moisture constraints, so feasibility can switch abruptly |
| Conserved coolant inventory | More heat capacity improves air cooling but lowers coolant temperature grade | This is the core interior trade-off; direct coolant limits, finite-HX duty asymptotes and heat-user approaches create a bounded feasible band |
| Optimized E-303 cutoff | Selects the ordered cold-return suffix with maximum ambient pickup | The local O(N) optimum excludes fixed-area cost, pumps/fans and arbitrary cross-connected subsets |

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
