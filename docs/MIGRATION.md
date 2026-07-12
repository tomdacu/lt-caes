# Migration notes

The project now has one normalized solver and one shared configuration model.

## Removed concepts

- batch air mass and tank-volume sizing;
- absolute air/water mass flow and power rating;
- exchanger area, overall U, and screening cost;
- the previous minimum-flow-to-duty optimizer;
- the well-mixed single-water-store approximation;
- duplicate legacy source trees and generated result images.

Those belong to later sizing, time-domain, and economic layers.

## Current architecture

```text
caes/config.py            validated choices and parameters
caes/logic.py             field groups and interdependency rules
caes/thermodynamics.py    air states and turbomachinery
caes/heat_exchangers.py   pinch, effectiveness, and NTU models
caes/exergy.py            air/water exergy functions
caes/plant.py             D-CAES and two-tank A-CAES orchestration
caes/gui.py               dependency-aware GUI and thermodynamic diagrams
```

The CLI and GUI call the same `PlantConfig` and `CAESPlant`. Dormant fields can
remain in JSON files, but they do not influence results under the selected
model.
