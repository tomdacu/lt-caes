# Usage

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Related:** [Configuration logic](05_CONFIGURATION_LOGIC.md) · [Benchmark protocol](10_BENCHMARKS_AND_REGRESSION.md)  
> **Code:** `caes/cli.py`, `caes/gui.py`, example JSON files

## Desktop application

The GUI is the primary interface:

```powershell
caes-atlas          # after pip install -e .
python -m caes      # equivalent, from a checkout
```

## Command line automation

```powershell
python -m caes.cli
python -m caes.cli --config heat_and_power_example_config.json --mode diabatic
python -m caes.cli --config counterflow_example_config.json
python -m caes.cli --config heat_and_power_example_config.json
python -m caes.cli --plot artifacts/cycle.png
python -m caes.cli --pid artifacts/pid.png
python -m caes.cli --sankey artifacts/sankeys.png
```

`--pid` draws the configuration-derived P&ID: flow-oriented machines on a shaft
and counter-flow exchanger blocks rendered as schemdraw elements on the same
Matplotlib axis that carries all hand-routed pipes, tanks, instruments, and the
title block.
`--sankey` writes the energy Sankey and exergy Grassmann diagrams side by side
in one PNG.

Add `--explain-config` to print which fields are active and dormant under the
selected model. Generate a clean starting file with:

```powershell
python -m caes.cli --write-default-config my_config.json
```

Configuration files saved by the GUI and files passed to `--config` use one
shared JSON format and are fully interchangeable.

## Desktop application features

The application provides:

- a live configuration-aware P&ID (schemdraw hero symbols on the routed
  Matplotlib canvas);
- logic blocks for plant concept, machinery, heat exchangers, coolant flow, and
  thermal surplus;
- automatic disabling of irrelevant inputs;
- debounced background recalculation after every valid change, with a rotating
  calculation indicator and stale-result protection;
- live T-s, h-s, and logarithmic p-h cycle plots;
- dotted cold-tank and hot-tank isotherms, plus post-`E-302` (`T_x`) when
  a heat off-take is active, on all three cycle plots;
- a double-width `E-302` heat-user composite curve beside the stage HXs;
- separate **Energy Sankey** and **Exergy Sankey (Grassmann)** tabs, each with
  an explicit boundary-closure residual;
- stage tables with air/coolant states and exergy destruction;
- normalized efficiency, exergy, coolant-limit, E-303 recovery and AD-CAES
  throttling results;
- ambient-energy input, useful-energy delivery ratio and coolant freezing
  margin.

## Typical workflows

### Counterflow NTU study

Enter the common stage NTU and select the optimization objective. Effectiveness
is calculated independently for every HX from NTU and its solved air/water
heat-capacity-rate ratio, with the air `cp` iterated at the exchanger mean
temperature. Higher NTU brings the air outlet closer to the entering
coolant temperature, at the cost of a larger `UA`.

Calculations run in a separate spawned process. Inputs, menus, scrolling, and
window resizing therefore remain available during long optimization runs; the
rotating status indicator disappears only after the latest requested result is
applied.

### Inspect the closed coolant design

After a run, check that every expansion process reaches the wet-rated lower
envelope (+10 degC in the permitted liquid region or local frost point plus
10 K), every throttle remains above the unmargined freezing/frost hard floor,
the mixed return reaches the optimized cold tank after `E-303` and tank
standing, every coolant state remains between `coolant_minimum_temperature_c`
and `coolant_maximum_temperature_c`, and the sum of charging ratios
matches the sum of discharging ratios. The GUI stage
tables and composite curves expose these values directly. The P&ID must show
the thermodynamic process equipment only: dryers and liquid separators are
intentionally omitted from the simplified schematic.

The same results panel now lists vapour and liquid wt% at every compressor and
expander suction/discharge. The `final separator only` rows are a
counterfactual screen: any non-zero compressor-suction liquid means that the
intermediate knock-out/drain cannot be removed unless the compressor OEM
explicitly guarantees wet ingestion. The final unit is the only special
deep-cooling/drying duty; intermediate separators are bulk-liquid devices.

### Compare AD-CAES and LTA-CAES

Keep machinery, pressure, and stage inputs unchanged and switch only `mode`.
The same compressor/storage/expander backbone is retained. Both concepts use
the same wet-expander anti-icing envelope. AD-CAES is fuel-free and combines
ambient reheat, maximum safe turbine work and isenthalpic throttling; LTA-CAES
routes compression heat through the pressurized two-tank coolant loop. E-303
can only warm the coldest sub-ambient returns; it never rejects heat. Neither
concept carries E-304: without a heat user there is nothing to sell off the top
of the trunk, so there is no reason to stage it.

### Study LTAHP-CAES

Start from `heat_and_power_example_config.json`. Its process order is:

```text
hot TES -> E-302 heat-user HX (whole trunk, sells the top band)
        -> E-304 extraction HX, one bleed per stage, trunk fully consumed
        -> coolant interheaters
        -> E-303 on the coldest returns -> final mixing
        -> E-304 cold side (internal recuperation) -> cold TES

cavern air -> coolant interheater -> turbine
```

There is no ambient exchanger on the air side: AD-CAES ambient reheat is
mandatory and applies only to the diabatic concept. Select
`max_combined_energy_delivery` to
maximize electricity plus heat per unit of charging work. The charge-water
split is then chosen for maximum useful exergy, and an infeasible
configuration is reported as a map of which constraint refuses which range of
coolant inventory. Compare the
off-take duty, electrical RTE, useful exergy efficiency, E-303 ambient absorption and coldest
coolant state; do not compare only the delivery ratio, which prices no free
stream.

## Interpreting efficiency

- Electrical RTE is expansion work divided by compression work (shaft only).
- Total useful exergy efficiency is useful exergy out (expansion + district
  heat) over compression-work exergy in.
- Useful-energy delivery ratio is `(W_exp + Q_DH) / W_comp`, and it is the only
  energy metric. Its denominator is purchased electricity alone: ambient heat
  (E-303 in the adiabatic concepts, AH-20x in AD-CAES) and the energy an
  exhaust below intake enthalpy carries in are both free, so neither is
  charged to it. It may therefore exceed one, and it
  is not a thermodynamic
  efficiency. Read the closed boundary balance off the Energy Sankey tab
  instead, and the bounded figure off the exergy efficiency.
- Heat at ambient temperature is positive energy but approximately zero exergy
  at the selected dead state.
- Results are normalized per kilogram of air; they are not a power rating.

Only `max_electric_efficiency` and `max_combined_energy_delivery` are active
objectives. Useful-exergy efficiency remains reported, not optimized. See the
canonical [objectives and metric definitions](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md).
