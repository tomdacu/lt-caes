# LT-CAES — low-temperature adiabatic compressed-air energy storage

![LT-CAES banner](assets/lt-caes-banner.png)

Compressed-air storage usually starts from a fuel you burn or a cavern a
kilometre down. This one starts from electricity, air and plain water: compress
the air, keep the compression heat in a two-tank water store at temperatures
plain steel and liquid can live with, then spend that heat where it pays. The
simulator screens the family in two forms that differ in one question — who
buys the stored heat:

```text
LT-CAES — low-temperature adiabatic CAES
├── LTA-CAES    no heat user   heat_offtake = "none"      all of it back into the turbines
└── LTAHP-CAES  heat user      heat_offtake = "heat_user" the top of the store is sold
```

Every run is one candidate plant, resized to the exchanger class and the
machinery you asked for, normalized to one kilogram of stored air, solved with
real-fluid properties. The tool exists to answer thermodynamic questions before
anyone buys anything: which architecture closes, which constraint binds, what a
hotter user or a colder return does to the plant. It deliberately does **not**
do equipment sizing, cost, off-design maps or dispatch — that boundary is
[written down](docs/02_PHYSICS_AND_MODEL_BOUNDARY.md), and it is what makes the
comparisons honest.

## The two forms

`heat_offtake` is the one input that selects the form. Everything else — the
plant, the machinery, the coolant loop, the solver — is shared, so a comparison
between the forms is a comparison of the *use* of heat, not of two different
plants.

- **LTA-CAES** (`heat_offtake = "none"`): the stored heat is turbine reheat and
  nothing else. The complete inventory reaches the parallel interheaters at the
  one stored temperature; one heat-only E-303 may recover free ambient energy
  into the coldest returning coolant.
- **LTAHP-CAES** (`heat_offtake = "heat_user"`): E-302 exports the band above
  the first extraction to an external heat user — a district network, a process
  loop, an absorption chiller, a greenhouse, a dryer; the three numbers that
  describe the user are its supply temperature, its return temperature and its
  exchanger NTU class — and E-304 stages the rest of the trunk down to what
  each expansion stage actually needs.

The heat user is generic by design: the model never assumes a network, and the
[Denmark note](docs/research/LTAHP_CAES_AND_DENMARK.md) is one application, not
the subject.

## Quick start

```powershell
python -m caes                                        # the GUI is the primary interface
python -m caes.cli --config counterflow_example_config.json      # study LTA-CAES
python -m caes.cli --config heat_and_power_example_config.json   # study LTAHP-CAES
python -m pytest
```

The CLI can also save the cycle plots, the P&ID and both Sankey diagrams:

```powershell
python -m caes.cli --config heat_and_power_example_config.json `
  --plot artifacts/cycles.png `
  --pid artifacts/pid.png `
  --sankey artifacts/sankeys.png
```

## What one run gives you

- a complete charge/discharge cycle with real-fluid states and moisture
  diagnostics;
- the coolant loop closed inside the solve — tank temperatures, per-stage water
  ratios, E-303's recovery group, the extraction margin of E-304;
- an electrical round-trip efficiency, a useful-energy delivery ratio and a
  full exergy book with a closed residual;
- the constraint that binds, stated in words, when a design is infeasible.

## The one design worth reading about

The discharge side is one user exchanger crossed by the whole trunk (E-302) and
one extraction body (E-304) with a bleed per expansion stage, fully consumed at
the last one. The extraction ladder sits a single common margin above each
stage's own anti-icing demand, so the tail stages are no longer fed water they
cannot use, and the descent between bleeds is recuperated into the plant's own
coolant return. Measured against the frozen serial cascade it replaced:

| user [C] | serial cascade `R` | E-302 + E-304 `R` |
|---|---:|---:|
| 80/45 | 1.0693 | 1.0744 |
| 95/75 | 1.0078 | 1.0624 |
| 100/80 | 0.9820 | 1.0379 |
| 110/90 | *infeasible* | 0.9847 |

Same electricity, more heat sold, a T-Q spread that collapses from 40 K to
11 K, and a user return that no longer dictates what the turbines get.
[Architecture](docs/12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md) ·
[measurements](docs/08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md#5-measured-against-the-frozen-cascade).

The headline metric is the **useful-energy delivery ratio**
`(W_exp + Q_heat_user) / W_comp`. Its denominator is the electricity the plant
buys and nothing else — ambient energy is free — so it may exceed one, like a
heat-pump COP, and it is not an efficiency. The exergy books stay bounded and
below unity; both are
[defined once](docs/03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) and never
quietly redefined.

## Documentation

| Read | For |
|---|---|
| [Plant concepts](docs/01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) | the two architectures, component by component |
| [Physics boundary](docs/02_PHYSICS_AND_MODEL_BOUNDARY.md) | what is modelled and what is deliberately not |
| [Objectives and exergy](docs/03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) | the metrics and the accounting rules |
| [Configuration logic](docs/05_CONFIGURATION_LOGIC.md) | every input, and which one selects the form |
| [Moisture and wet expansion](docs/06_MOISTURE_DEW_POINT_AND_WET_EXPANSION.md) | the anti-icing envelope |
| [Usage](docs/07_USAGE.md) | workflows for both forms |
| [The E-302/E-304 architecture](docs/12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md) | why the trunk is staged |
| [Research map](docs/research/README.md) | the literature this builds on (Wolf & Budt onward) |

## The frozen sibling

Before this line existed, the repository compared three fuel-free concepts:
the ambient-diabatic **AD-CAES** baseline together with LTA and LTAHP. That
tool is frozen on the [`no-combustion-caes`
branch](https://github.com/tomdacu/lt-caes/tree/no-combustion-caes) (tag
`v2.0.0-no-combustion-caes`) for readers who need the diabatic comparison;
nothing in this line simulates a diabatic plant.

## Artwork and licence

The banner and the application icon are generated, not drawn:
`scripts/make_brand_assets.py` writes the PNG and its SVG source from the same
colour vocabulary as the diagrams. Everything here is released under the
[MIT licence](LICENSE).
