# No-combustion CAES — three fuel-free concepts on one normalized basis

![No-combustion CAES banner](assets/banner.png)

Compressed-air storage usually starts from a fuel you burn or a cavern a
kilometre down. Every concept here starts from electricity, air and plain
water instead, and the three of them differ in one question: what happens to
the compression heat.

```text
no-combustion CAES
├── AD-CAES      ambient diabatic  no store at all: the heat is rejected to,
│                                 and recovered from, the atmosphere
└── LT-CAES      low-temperature adiabatic family: a liquid two-tank TES
    ├── LTA-CAES     no heat user  heat_offtake = "none"
    └── LTAHP-CAES   heat user     heat_offtake = "heat_user"
```

"Low temperature" qualifies the *store* — a liquid two-tank TES sized for the
temperatures water and plain steel can live with — which is why it names the
adiabatic family only: AD-CAES has no store for it to qualify. All three are
fuel-free: no combustion chamber, no high-temperature thermal store.

The simulator is a **configuration screening tool**. Each run is one candidate
plant, resized to the exchanger class and machinery you asked for, normalized
to one kilogram of stored air, solved with real-fluid properties. It answers
thermodynamic questions before anyone buys anything: which architecture closes,
which constraint binds, what a hotter user or a colder return costs. It
deliberately does not do equipment sizing, cost, off-design maps or dispatch —
that boundary is [written down](docs/02_PHYSICS_AND_MODEL_BOUNDARY.md), and it
is what makes the comparisons honest.

## The three concepts

- **AD-CAES (ambient diabatic)** — `mode = "diabatic"`. Every intercooler
  rejects compression heat to the atmosphere; there is no thermal store. On
  discharge a finite ambient exchanger warms the process air, the turbines take
  the largest pressure drop the wet-expander envelope allows, and an
  isenthalpic valve completes the reduction when frost safety demands it.
- **LTA-CAES (low-temperature adiabatic)** — `heat_offtake = "none"`. The
  compression heat is stored in a two-tank water loop and returned to the
  parallel interheaters at the one stored temperature; one heat-only E-303 may
  recover free ambient energy into the coldest returning coolant.
- **LTAHP-CAES (low-temperature adiabatic heat and power)** — 
  `heat_offtake = "heat_user"`. E-302 exports the band above the first
  extraction to an external heat user — a district network, a process loop, an
  absorption chiller, a greenhouse, a dryer — and E-304 stages the rest of the
  trunk down to what each expansion stage actually needs, recuperating the
  descent into the plant's own cold return.

The heat user is generic by design: three numbers (supply temperature, return
temperature, exchanger NTU class) describe it, and nothing in the solver
assumes a network. The
[Denmark note](docs/research/LTAHP_CAES_AND_DENMARK.md) is one application, not
the subject.

## Quick start

```powershell
python -m caes                                   # the GUI is the primary interface
python -m caes.cli --config counterflow_example_config.json       # LTA-CAES
python -m caes.cli --config heat_and_power_example_config.json    # LTAHP-CAES
python -m caes.cli --mode diabatic               # AD-CAES
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
- for the adiabatic concepts, the coolant loop closed inside the solve: tank
  temperatures, per-stage water ratios, E-303's recovery group, and — with a
  heat user — the extraction ladder of E-304;
- an electrical round-trip efficiency, a useful-energy delivery ratio and a
  full exergy book with a closed residual;
- the constraint that binds, stated in words, when a design is infeasible.

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
| [Plant concepts](docs/01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) | the three architectures, component by component |
| [Physics boundary](docs/02_PHYSICS_AND_MODEL_BOUNDARY.md) | what is modelled and what is deliberately not |
| [Objectives and exergy](docs/03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) | the metrics and the accounting rules |
| [Configuration logic](docs/05_CONFIGURATION_LOGIC.md) | every input, and which concept activates it |
| [Moisture and wet expansion](docs/06_MOISTURE_DEW_POINT_AND_WET_EXPANSION.md) | the anti-icing envelope, charge and discharge |
| [Usage](docs/07_USAGE.md) | workflows for each concept |
| [The E-302/E-304 architecture](docs/12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md) | why the adiabatic trunk is staged |
| [Research map](docs/research/README.md) | the literature this builds on (Wolf & Budt onward) |

## A branch exists for the adiabatic family alone

The [`lt-caes`](https://github.com/tomdacu/lt-caes/tree/lt-caes) branch carries
an experimental cut that keeps only LTA and LTAHP: the diabatic concept, the
`mode` axis and the air/ambient exchanger are removed from that line. It is
kept because a narrower tool may be easier to grow — main does not simulate a
diabatic plant *there*, and *here* it does.

## Artwork and licence

The banner and the application icon are generated, not drawn:
`scripts/make_brand_assets.py` writes the PNG and its SVG source from the same
colour vocabulary as the diagrams. Everything here is released under the
[MIT licence](LICENSE).
