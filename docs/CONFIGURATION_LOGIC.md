# Configuration dependency logic

`caes.logic` is the single source of truth for configuration groups and active
fields. The GUI uses it to disable dormant inputs; the CLI exposes it through
`--explain-config`.

| Selection | Active inputs | Dormant inputs |
|---|---|---|
| D-CAES | ambient HX approach, optional ambient reheat | water tanks, water HX model, water flow, surplus routing |
| A-CAES + pinch | cold-tank temperature, pinch, storage loss, surplus routing | effectiveness, NTU, water-flow selection |
| A-CAES + effectiveness | effectiveness and water-flow selection | pinch, NTU |
| A-CAES + counterflow NTU | NTU and water-flow selection | pinch, specified effectiveness |
| finite HX + specified ratio | normalized water/air ratio | optimization bounds |
| finite HX + optimization | ratio search bounds | specified ratio |

The machinery and boundary-condition blocks are always active. Switching plant
mode therefore changes only thermal management while retaining the common CAES
backbone.

## Optimization objectives

- `max_electric_efficiency`: maximize expansion/compression work ratio.
- `max_hot_water_exergy`: maximize mixed hot-tank exergy after storage loss.
- `max_total_exergy_efficiency`: maximize electricity plus useful-heat exergy.

Each optimizer scans a logarithmic normalized water/air-ratio range. The chosen
ratio and objective are returned with the result, so the analysis is auditable.
