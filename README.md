# CAES Atlas

![CAES Atlas](assets/banner.png)

**Thermodynamic screening of combustion-free compressed-air energy storage,
with and without heat co-production.**

CAES Atlas is an open research code for the comparative assessment of
compressed-air energy storage (CAES) concepts that use neither fuel nor a
high-temperature thermal store. Each candidate plant is solved as a closed
charge-discharge cycle on a per-kilogram-of-air basis. It uses real-fluid
properties, finite-effectiveness heat exchangers, a moisture-safe expansion
envelope and a complete exergy balance. The code returns the optimal design
of each configuration or, when none exists, the physical constraint that rules
it out along the design axis.

## Scope

The compression heat can be treated in three ways, each modelled on a common
basis:

| concept | fate of the compression heat | products |
|---|---|---|
| **AD-CAES**, ambient diabatic | rejected to the atmosphere; the expanding air is reheated from ambient and throttled where needed | electricity |
| **LTA-CAES**, low-temperature adiabatic | stored in a pressurized two-tank water loop below about 200 °C and returned to the expansion train | electricity |
| **LTAHP-CAES**, low-temperature adiabatic heat and power | stored as in LTA; the high-temperature band is exported to an external heat user and the turbines receive only their minimum moisture-safe duty | electricity and heat |

The heat user is generic: a supply temperature, a return temperature and an
exchanger class describe a district-heating network, a process-heat loop, an
absorption chiller or a drying plant alike.

## Principal findings

**1. The heat-and-power plant is a one-variable problem.** Under minimum-duty
dispatch the discharge side depends only on the coolant inventory `R` and the
stored humidity, never on either tank temperature. The coolant-loop closure,
usually treated as a nonlinear root, is therefore explicit, and the design
problem reduces to a bounded one-dimensional search in `R` with named
constraint boundaries. Relative to a coupled root-finding formulation, solution
times drop from minutes to seconds, and optima that lie on constraint
boundaries are located exactly
([details](docs/14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md)).

**2. An exact first-law identity explains the delivery ratio.** For every
design,

```text
J = (W_exp + Q_user) / W_comp
  = 1 + (Q_ambient + (h_intake - h_exhaust) - Q_aftercooling - L_storage) / W_comp
```

`J` exceeds unity only by the ambient energy the plant draws in: sub-ambient
coolant returns warmed by the atmosphere, and an exhaust colder than the
intake. It falls below unity through the heat rejected when the compressed air
cools to ambient in storage.

**3. The three figures of merit are linked.** With `theta` the Carnot factor of
the user's thermodynamic mean temperature,

```text
J       = RTE + (eta_ex - RTE) / theta
COP_net = Q_user / (W_comp - W_exp) = (J - RTE) / (1 - RTE)
```

The delivery ratio amplifies heat exergy by `1/theta` (7 to 11 for
district-heating temperatures). It is almost insensitive to machine
efficiency: from 0.80 to 0.95, `J` changes by 0.003 while the round-trip
efficiency gains 22 points. Energy-based ratios alone therefore cannot rank
such plants; the code reports all three, and it chooses internal allocations
by exergy, because an energy ratio that weights heat equal to electricity
rewards resistive heating.

**4. Performance limits.** With ideal components the electricity-only store
approaches reversibility (`RTE = 0.987` in the model). With heat
co-production the architecture itself destroys exergy even with perfect
components (`eta_ex` about 0.92): the expansion is held at the icing floor,
and heat is exported across finite temperature differences. Read as a
time-shifted heat pump, the plant reaches 40-47 % of the Carnot COP with ideal
components and about 16 % at the screening design point. With realistic components
the delivery ratio reaches about 1.22 at best, and it is raised mainly by the
number of expansion stages and exchanger effectiveness, which enlarge the
ambient-energy harvest
([details](docs/16_PERFORMANCE_LIMITS.md)).

## Reference plant

The application starts from a large (tens of MW) plant built from
commercially available machinery, with typical published component values
([sources](docs/17_REALISTIC_REFERENCE_PARAMETERS.md)): a 100 bar salt
cavern, eight integrally geared compression and eight expansion stages at
0.86 / 0.85 isentropic efficiency, 1.5 % pressure loss per exchanger,
air/water exchangers of NTU 3.4 (the top of published designs), a water-glycol
store and an 80/40 °C district-heating user at a North-German site.

| quantity | per kg of air |
|---|---:|
| compression work | 543.9 kJ |
| expansion work | 304.9 kJ |
| heat delivered to the user | 261.4 kJ |
| ambient heat drawn in | 30.9 kJ |
| electrical round-trip efficiency | 56.1 % |
| useful-energy delivery ratio `J` | 104.1 % |
| useful-exergy efficiency | 63.2 % |
| cold / hot store | 36 °C / 86 °C |

The round-trip efficiency lies inside the 52-60 % published for LTA-CAES
concepts. Eight expansion stages drive
the coldest coolant returns below ambient, which is what lets the plant
harvest ambient heat. It is also why the cold loop needs an antifreeze: with
pure water the same plant has no feasible design.

## Screening design point

The numerical baseline used throughout the documentation and the test suite:
LTAHP-CAES at 85.8 bar, 6 + 6 stages, isentropic efficiencies 0.85, exchanger
NTU 5, heat user at 80/45 °C, ambient 15 °C:

| quantity | per kg of air |
|---|---:|
| compression work | 548.5 kJ |
| expansion work | 302.3 kJ |
| heat delivered to the user | 287.1 kJ |
| ambient heat drawn in | 44.4 kJ |
| electrical round-trip efficiency | 55.1 % |
| useful-energy delivery ratio `J` | 107.5 % |
| useful-exergy efficiency | 62.5 % |
| net heat-pump COP (Carnot 7.1) | 1.17 |
| cold / hot store | 39 °C / 112 °C |
| exergy balance residual | < 0.001 J |

## Method

- **Working fluid.** Dry air through CoolProp's reference Helmholtz equation
  of state; the coolant is liquid water at constant heat capacity within
  configurable temperature limits.
- **Machines.** Staged compression and expansion with equal pressure ratios
  and isentropic efficiencies.
- **Heat exchangers.** Counter-current effectiveness-NTU with the air heat
  capacity evaluated at the exchanger mean temperature. A fixed NTU denotes a
  performance class: every candidate is resized as `UA = NTU C_min`.
- **Moisture.** Charge-side condensation with ideal separators, and a
  wet-expander envelope on every turbine outlet (10 °C where liquid can form,
  otherwise the local frost point plus 10 K).
- **Heat-user topology.** The stored inventory first crosses the heat-user
  exchanger, then a counter-current staged-extraction exchanger that feeds each
  expansion stage at a common margin above its own demand and recuperates the
  remaining descent into the coolant return. A heat-only ambient exchanger
  warms the coldest returns.
- **Solution.** One-dimensional inventory search with constraint-boundary
  bisection and Brent's method for the heat-user plant; a coupled coolant-loop
  root for the electricity-only plants. Every accepted design is rebuilt and
  checked: component energy balances, water-mass closure, loop closure,
  exchanger feasibility, the moisture envelope, and a whole-plant exergy
  residual below 1 J/kg.

A step-by-step account of the solver, written for readers outside the field,
is in [How the solver works](docs/15_HOW_THE_SOLVER_WORKS.md).

## Model boundary

CAES Atlas is a screening model. It does not size equipment, estimate cost,
represent off-design maps, cavern transients, dispatch or seasonal weather.
Motor, generator, pump and fan losses are outside the boundary. The moisture
model is a dry-air energy balance with a validity screen. Results rank
concepts and identify binding constraints; they are not a detailed plant
design. The full boundary is documented in
[Physics and model boundary](docs/02_PHYSICS_AND_MODEL_BOUNDARY.md).

## Getting started

```powershell
pip install -e .[dev]

caes-atlas                                                        # desktop application
python -m caes.cli --config heat_and_power_example_config.json    # LTAHP-CAES
python -m caes.cli --config counterflow_example_config.json       # LTA-CAES
python -m caes.cli --config heat_and_power_example_config.json --mode diabatic   # AD-CAES
python -m pytest
```

The command line can also write the thermodynamic cycle diagrams, the process
flow diagram and the energy and exergy Sankey diagrams (`--plot`, `--pid`,
`--sankey`). Python 3.10 or later, CoolProp, Matplotlib and schemdraw are
required.

## Documentation

| document | content |
|---|---|
| [How the solver works](docs/15_HOW_THE_SOLVER_WORKS.md) | the solution method from first principles |
| [Realistic reference parameters](docs/17_REALISTIC_REFERENCE_PARAMETERS.md) | the startup plant, every value sourced |
| [Performance limits](docs/16_PERFORMANCE_LIMITS.md) | reversible bounds, ideal-component results, heat-pump reading |
| [One-variable reduction](docs/14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md) | the reduction, the energy identity, the charge-allocation rule |
| [Plant concepts](docs/01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) | the three architectures in detail |
| [Metrics and exergy accounting](docs/03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) | definitions of every figure of merit |
| [Moisture and wet expansion](docs/06_MOISTURE_DEW_POINT_AND_WET_EXPANSION.md) | the anti-icing envelope |
| [Benchmarks](docs/10_BENCHMARKS_AND_REGRESSION.md) | solver performance and regression protocol |
| [Documentation map](docs/00_DOCUMENTATION_MAP.md) | all documents, indexed by question |
| [Research map](docs/research/README.md) | the literature this work builds on |

## Verification

The test suite (about 300 tests) enforces component and whole-plant energy
balances, exergy closure below 1 J/kg across the concept matrix, water-mass
conservation between charge and discharge, the moisture envelope on every
turbine, and the invariants of the staged-extraction exchanger. Solver
performance is tracked with deterministic work counts and result
fingerprints, not only wall-clock time.

## Licence

MIT, see [LICENSE](LICENSE).
