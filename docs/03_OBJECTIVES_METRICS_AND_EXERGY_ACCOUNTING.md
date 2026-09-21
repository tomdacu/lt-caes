# Objectives, metrics, and exergy accounting

> **Parent:** [Theory and design objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md)  
> **Related:** [Plant concepts](01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) · [Optimization workflow](04_OPTIMIZATION_WORKFLOW.md)  
> **Code/tests:** `caes/exergy.py`, `caes/diagrams.py`, `tests/test_exergy_balance.py`

This document is the canonical definition of optimization objectives and
plant-level performance metrics. Other documents should link here rather than
redefine the ratios.

## Metric definitions

All quantities use the one-kilogram-dry-air basis. Shaft work and useful heat
are positive in the table, even though expansion work is negative under the
internal air-centric process sign convention.

| Metric | Definition | Interpretation |
|---|---|---|
| Electrical round-trip efficiency | `eta_electric = W_exp / W_comp` | Shaft work out divided by shaft work in. Motor, generator, pump, and fan losses are outside the current boundary. |
| Useful-energy delivery ratio | `R_delivery = (W_exp + Q_heat_user) / W_comp` | The one energy metric: sector-coupling output per unit of *purchased* charging electricity. Free harvested ambient energy never enters the denominator, so it may exceed 100% and must not be called a thermodynamic efficiency. |
| Useful-exergy efficiency | `eta_exergy = (W_exp + B_heat_user) / W_comp` | Useful exergy product divided by compression-work exergy. Ambient heat transferred at the dead-state temperature has approximately zero exergy. Reported, not optimized. |

There is exactly **one** energy metric. `R_delivery > 1` is not perpetual
motion; see the next section for why the denominator is what it is.

## The one energy metric, and what it deliberately excludes

`R_delivery` is an **expenditure ratio**: useful output over what the operator
pays for. Its denominator is charging electricity and nothing else, because
every ambient energy stream the plant harvests is free and a free stream is not
a cost. Two such streams exist:

- external ambient heat, reported as `external_heat_input_j_per_kg`: mandatory
  air-side ambient reheat in AD-CAES, or heat-only E-303 recovery into the
  returning coolant in LTA/LTAHP-CAES;
- the energy the air stream itself hands over. Intake and exhaust are both at
  `p0` and the intake is at `T0`, so the working fluid delivers a net

  ```text
  Q_air,stream = h(T0, p0) - h_exhaust
  ```

  to the control volume. Whenever the exhaust leaves colder than the intake
  that is a genuine ambient-energy inflow: the plant behaves somewhat like a
  heat pump, drawing low-temperature, high-entropy heat out of the atmosphere
  through its own working fluid and converting part of it into useful output.
  Measured over the supplied configurations it ranges from `-7.5` to
  `+48.7 kJ/kg-air`, so it is not a rounding term.

Both are reported as flows. Neither is charged to the denominator.

An earlier `eta_energy = (W_exp + Q_heat_user) / (W_comp + Q_ambient)` has been
**removed**. It was an inconsistent half-measure: it priced the first free
stream and ignored the second, so it was neither an expenditure ratio nor a
closed balance. Anything still referring to a "first-law useful-energy
efficiency" predates that removal.

Consequently `R_delivery` is **not bounded by one**, for exactly the reason a
heat-pump COP is not. A worked case:

```text
200 bar, 8+8 stages, NTU = 100, external heat user,
coolant_minimum_temperature_c = -30

W_comp = 639.63   W_exp = 355.70   Q_heat_user = 357.68   E-303 ambient = 69.39 kJ/kg-air
intake  +15.00 degC   h = 414.37 kJ/kg
exhaust -27.57 degC   h = 371.56 kJ/kg     -> 42.81 kJ/kg-air harvested, unpriced

R_delivery = 111.53 %      <- above one, and correct for what it measures
eta_exergy = 63.48 %       <- bounded thermodynamic metric
```

This LTAHP case has two distinct free ambient contributions: E-303 heats the
selected coldest returns, and the exhaust leaves below the inlet enthalpy.
Both belong in the closed first-law balance, but neither is purchased charging
electricity.  Their presence is exactly why `R_delivery` is a delivery ratio
and must not be relabelled as a thermodynamic efficiency.

The other two questions have their own answers, and neither is this ratio:

- the **closed first-law boundary balance** is the energy Sankey
  (`caes.diagrams.draw_energy_sankey`). It draws every free stream explicitly,
  including an `Exhaust air below intake` input, and prints a closure residual.
  It will therefore not agree term-for-term with `R_delivery`, by design.
  `tests/test_exergy_balance.py::test_closed_first_law_boundary_balance`
  asserts that identity over the whole concept matrix.
- `eta_exergy` **is** bounded by one and stays there, because the cold exhaust
  keeps positive physical exergy and is booked as `exhaust_air` loss rather
  than quietly dropped, and ambient heat correctly enters at ~zero exergy. The
  exergy books are the complete thermodynamic accounting; `R_delivery` is the
  commercial one.

## Objective policy by concept

The active enum contains two choices:

- `max_electric_efficiency`;
- `max_combined_energy_delivery`.

The project policy is:

| Concept | Configuration identity | Normal objective | Solver behavior |
|---|---|---|---|
| AD-CAES | `mode=diabatic` | maximum electrical RTE | Direct finite-NTU turbine/throttle solution; no coolant-inventory optimization loop. |
| LTA-CAES | `mode=adiabatic`, `heat_offtake=none` | maximum electrical RTE | Rank closed two-tank candidates by expansion work. |
| LTAHP-CAES, electric dispatch | `heat_offtake=heat_user`, `max_electric_efficiency` | maximum electrical RTE | Bypass E-302 and E-304 and route the complete hot-coolant inventory to the interheaters at the one stored temperature; this reproduces LTA unless non-bypassable hardware losses are later added. |
| LTAHP-CAES, combined dispatch | `heat_offtake=heat_user`, `max_combined_energy_delivery` | maximum useful-energy delivery ratio | Sell everything above the first E-304 extraction, feed each stage a common margin above its own demand, and recuperate the descent into the coolant return; rank candidates by `W_exp + Q_heat_user`. |

Both active objectives remain selectable for sensitivity studies, but the
selected objective always ranks candidates. Endpoint T-Q spread remains an
equipment-design metric in `OptimizationSummary`; it is never a hidden primary
criterion.

Legacy JSON containing `max_total_exergy_efficiency` is accepted only for
migration. `PlantConfig` emits a `DeprecationWarning` and maps it to maximum
electrical efficiency without a heat user, or maximum combined delivery with
a heat user. Useful-exergy efficiency stays available in result tables,
the GUI, the CLI summary, and the Grassmann audit.

Useful-exergy efficiency is not retained as an optimization objective because
it adds no decision information for LTA-CAES without a heat user (the only
product is electricity), while an ambient-diabatic comparison requires careful
treatment of cold-stream physical exergy and ambient interactions. LTAHP's
stated product goal is instead the combined delivery of electricity and heat.

The objective therefore controls both candidate ranking and the physical
heat/electric dispatch. Merely selecting LTAHP hardware does not force a heat
sale when the requested operating objective is electrical.

## First-law coolant accounting

For LTA/LTAHP the coolant loop has two energy sources and four modeled destinations:

```text
Q_recovered + Q_E303,ambient
            = Q_turbine_reheat + Q_heat_user
            + Q_hot_tank_standing + Q_cold_tank_standing
```

There is no rejection cooler anywhere. With a heat user, the complete E-302
temperature drop is a useful product, and the trunk's further descent inside
E-304 is INTERNAL recuperation - it is neither a product nor a loss, and it
cancels out of the coolant energy balance. E-303 can add heat only to the
coldest sub-ambient returns, before final mixing, E-304 and cold-tank standing.

In LTA-CAES, full-inventory absorption is preferred. If the conserved coolant
contains heat that neither the turbines nor another modeled product can accept,
the point is infeasible; E-303 is not a hidden rejection fallback.

## Exergy classification

Air physical-flow exergy relative to the ambient dead state is

```text
e = (h - h0) - T0 (s - s0)
```

For the constant-`cp` liquid model:

```text
b(T) = cp [(T - T0) - T0 ln(T/T0)]
```

One classification applies to all concepts:

- electricity and district-heat exergy delivered to a real user are
  **products**;
- finite temperature difference, pressure loss, turbomachinery
  irreversibility, throttling, mixing, tank standing loss, and heat transferred
  into the ambient dead state are **destruction**;
- only exhaust air leaving the boundary with intact physical exergy is a
  **loss**;
- ambient heat received at `T0` is positive energy but has approximately zero
  heat-transfer exergy.

The Grassmann balance is

```text
W_comp = W_exp + B_heat_user + sum(I_component) + B_exhaust + residual
```

`ExergySummary.balance_residual_j_per_kg_air` is the honesty check. Tests assert
an absolute residual below approximately 1 J/kg-air for the supported concept
matrix. A non-trivial residual is not silently absorbed into destruction.

## Sankey and Grassmann diagrams

The GUI exposes two distinct tabs:

- **Energy Sankey**: compression work and ambient-energy inputs versus shaft
  work, user heat, tank standing and exhaust sensible flow,
  and printed closure residual. This is the closed boundary balance, so it
  carries the free streams that `R_delivery` leaves out - a sub-intake exhaust
  appears here as an `Exhaust air below intake` **input**;
- **Exergy Sankey (Grassmann)**: compression-work exergy split into expansion
  work, district-heat exergy product, destruction by component category, and
  exhaust loss. Ambient heat is annotated as approximately zero exergy.

The CLI writes both diagrams to one PNG:

```powershell
python -m caes.cli --config heat_and_power_example_config.json `
  --sankey artifacts/sankeys.png
```

## Feasibility diagnostics

Closed two-tank candidates remain subject to hard thermodynamic limits; the
optimizer does not return a design that exceeds them. If no candidate closes,
the raised error aggregates the actual binding causes encountered over the
inventory search, including reached and permitted values where available, and
offers cause-specific remedies. Examples include direct coolant temperature
limits, finite-HX ordering, wet-expander boundary,
and incompatible capacity-matched throughput.

The E-303 optimizer is a different mechanism: it selects the maximum ambient
heat pickup among the temperature-ordered coldest return groups and never
disposes of heat.
