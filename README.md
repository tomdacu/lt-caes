# Normalized LTA-CAES Simulator

A flexible Python simulator for comparing two closely related compressed-air
energy-storage plants:

- **D-CAES** rejects compression heat through ambient intercoolers.
- **Water LTA-CAES** transfers compression heat to parallel water branches,
  mixes them into a hot tank, and uses that water in parallel interheaters
  during expansion.

The analysis is normalized to **one kilogram of stored air**. It focuses on
electrical round-trip efficiency, useful-heat exergy, component exergy
destruction, hot/cold water temperatures, and thermal surplus. It deliberately
contains no time-domain, equipment-cost, tank-pressure, or plant-power model.

## Quick start

```powershell
python -m pip install -r requirements.txt
python -m pytest
python -m caes.cli
python -m caes.cli --config counterflow_example_config.json --explain-config
python -m caes.gui
```

The desktop application updates results as inputs change. Its left panel is
dependency-aware: selecting a pinch model disables effectiveness, NTU, and
water-ratio inputs; selecting an optimizer disables the specified ratio;
selecting D-CAES disables the water-storage block.

## Heat-exchanger choices

The A-CAES water loop has three mutually exclusive specifications:

| Model | Active input | Water-flow behavior |
|---|---|---|
| `pinch` | terminal pinch temperature | Water flow is solved stage by stage to meet both terminal approaches. |
| `effectiveness` | specified exchanger effectiveness | Use a specified normalized water/air ratio or optimize it. |
| `counterflow_ntu` | NTU | Effectiveness is calculated from NTU and capacity-rate ratio; flow can be specified or optimized. |

For finite exchanger models, the normalized water/air ratio can be selected
directly or optimized for electrical RTE, stored hot-water exergy, or total
useful exergy efficiency.

## Thermal surplus

The hot-water store is allowed to contain more energy than expansion requires.
After air reheat, residual water heat can be marked as:

- `reject`: surplus exergy is counted as a loss;
- `useful_heat`: surplus is treated as a district-heating-style useful output.

Electrical RTE remains separate. The total useful exergy efficiency includes
the exergy—not simply the energy—of exported heat.

## Interactive thermodynamic views

The GUI contains live T-s, T-h, and logarithmic p-h diagrams, stage tables, and
an exergy breakdown. All three plots use the same real-fluid air states as the
solver and update whenever a valid input changes. The CLI `--plot` option saves
the three diagrams together in one PNG.

## Documentation

- [Usage and examples](docs/USAGE.md)
- [Physics and equations](docs/PHYSICS.md)
- [Configuration dependency logic](docs/CONFIGURATION_LOGIC.md)
- [Research map](docs/research/README.md)
- [Migration notes](docs/MIGRATION.md)

The solver uses [CoolProp](https://coolprop.org/) for real-air properties. The
water LTA-CAES concept is informed by [Wolf and Budt's low-temperature A-CAES
work](https://doi.org/10.1016/j.apenergy.2014.03.013).
