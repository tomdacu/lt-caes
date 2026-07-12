# Water-flow optimisation at a fixed air-flow design point

## Purpose

For a selected air mass flow, the model reports the corresponding compressor
and turbine shaft-power scale:

```text
Pcompressor = m_dot_air wcompressor
Pturbine    = m_dot_air |wturbine|
```

This connects `air_mass_flow_kg_s` to a chosen plant power rating. The same air
flow fixes the air-side heat-capacity rate in every finite-area counter-current
heat exchanger.

## What is optimised

Select:

```json
"heat_exchanger_model": "counterflow_ntu",
"water_flow_strategy": "optimize_thermal"
```

The optimiser finds the **smallest water mass flow** that recovers the chosen
`water_flow_target_fraction` of the heat recovered at
`water_mass_flow_search_max_kg_s`. The default target is 95%.

This is a useful design rule: it avoids making the water circuit unnecessarily
large once additional flow gives only a small thermal benefit.

## Why this is not yet an economic optimum

For a fixed exchanger area and fixed overall coefficient `U`, the epsilon-NTU
model predicts heat duty that increases toward an asymptote as water flow
increases. Therefore maximum thermal duty alone has no finite optimum.

A true economic optimum requires a hydraulic model: water-side pressure drop
as a function of flow, pump efficiency, pump capital cost, and electricity
cost. Those terms are not yet modelled, so the code honestly returns a
minimum-flow-for-target design instead. The configured upper search limit is a
high-flow proxy for the asymptotic reference; make it large enough that the
result no longer changes materially.

## Run the supplied case

```powershell
python -m caes.cli --config counterflow_optimized_config.json
```

The output reports the optimised water mass flow, achieved recovery fraction,
and compressor/turbine power scale. This optimisation is available only for
adiabatic, water-based `counterflow_ntu` cases.
