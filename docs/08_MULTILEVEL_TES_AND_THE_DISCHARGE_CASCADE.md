# Single-store TES and the discharge extraction network

> The filename is retained so existing links do not break; both multi-level hot
> TES and the serial K-station user cascade were removed from the active
> architecture.  
> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Concept specification:** [Single-store extraction architecture](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)  
> **Performance:** [Performance and optimization](09_PERFORMANCE_AND_OPTIMIZATION.md)

## 1. Model boundary

The active LTA/LTHP model contains one mixed hot coolant store and one mixed
cold coolant store. Parallel intercooler returns may have different local
temperatures, but they mix before the standing period.

The result fields `hot_level_temperatures_k` and `hot_level_water_mass_ratios`
remain tuples for result compatibility, but each contains exactly one value.
They must not be read as a control for stratified storage.

`coolant_cascade_groups` was removed together with the serial cascade it
configured. Older configuration files still load: the key is ignored with a
deprecation warning.

## 2. Solve hierarchy

For a trial conserved coolant inventory, the solver:

1. proposes a cold-tank temperature and solves the charge split and one mixed hot-store state;
2. computes each expansion stage's invariant moisture-safe demand temperature and duty;
3. raises that demand profile to its non-increasing suffix-maximum envelope;
4. roots the common extraction margin `m` so the bleeds consume the exact inventory;
5. builds the discharge branch returns;
6. selects the maximum-duty legal E-303 group over the COLDEST returns, then remixes;
7. runs the mixed return through E-304 and applies cold-tank standing;
8. materializes the accepted train once and checks heat, mass and exergy books;
9. ranks feasible inventories by the selected plant objective.

The margin root is monotone - a hotter supply needs less flow - so one
safeguarded Illinois root, warm-started by the previous normalized margin,
solves

```text
  sum_g  b_g( T_demand,g + m )  -  R_total  =  0
```

Only after that internal mass closure does the outer coolant-loop residual
compare the produced cold-tank temperature with its trial value. That produced
temperature is the **recuperated** one, downstream of E-304, not the mixed
return.

## 3. Finite exchanger constraints

```text
  heat_exchanger_ntu        air/coolant interheaters
  heat_user_exchanger_ntu   the single plant/user exchanger E-302
  extraction_exchanger_ntu  EACH zone of E-304
  cold_return_cooler_ntu    the single ambient exchanger E-303
```

E-304 is deliberately given a per-zone class rather than a whole-body one: its
trunk capacity rate steps down at every extraction, so a single effectiveness
would be invalid. The user's mass flow is solved from the E-302 duty and its
configured supply/return span.

## 4. Why the first exchanger is now the only one

Under the serial cascade, the trunk descended through `K` user exchangers and
the user absorbed the whole descent - which forced the user's return
temperature below the coldest interheater bleed. Now E-302 takes only the band
above the first extraction and E-304 recuperates everything below it into the
coolant return. The user's return temperature is therefore decoupled from what
the turbines need, which is the change that unlocks high-temperature users.

## 5. Measured against the frozen cascade

Baseline is commit `22b7bb7`, the serial cascade at `K=1`. Same machine, same
CoolProp backend, `heat_and_power_example_config.json` unless stated.

### 5.1 The design point (6 stages, 85.8 bar, 80/45 user)

| | cascade `K=1` | E-304 | |
|---|---:|---:|---|
| `R_delivery` | 1.0693 | **1.0744** | +0.5 pt |
| `eta_exergy` | 0.6320 | 0.6241 | -0.8 pt |
| heat sold [kJ/kg-air] | 274.57 | **287.87** | +4.8% |
| heat exergy sold [kJ/kg-air] | 38.64 | **40.51** | +4.8% |
| E-303 ambient harvest [kJ/kg-air] | 33.78 | **45.07** | +33% |
| hot / cold tank [C] | 105.9 / 32.9 | 113.6 / 39.1 | |
| worst HX endpoint spread [K] | 40.41 | **11.20** | -72% |

The delivery ratio rises rather than falls, which is not what a first reading of
the change predicts. Recuperation does raise the cold tank by 6.2 K and does
cost 9.8 kJ/kg-air of extra compression work. It is paid for by the returns: a
matched ladder sends each interheater water it can actually cool down, the
returns come back colder, and E-303 harvests a third more free ambient energy.

The exergy efficiency moves the other way by a smaller amount, because that
extra compression work is pure exergy while the extra harvested heat is nearly
worthless at the dead state. Both numbers are reported; neither is hidden.

The endpoint-spread collapse is the curve-matching effect stated as a
measurement: under one tank temperature the last stage was fed 44 K above what
it could use, and the T-Q profiles were correspondingly non-parallel.

### 5.2 High-temperature users - the reason for the change

Six stages, 85.8 bar, sweeping the user's supply/return pair.

| user [C] | cascade `R` | E-304 `R` | cascade `eta_ex` | E-304 `eta_ex` |
|---|---:|---:|---:|---:|
| 80/45 | 1.0693 | **1.0744** | 0.6320 | 0.6241 |
| 90/60 | 1.0693 | **1.0744** | 0.6478 | 0.6404 |
| 95/75 | 1.0078 | **1.0624** | 0.6250 | **0.6448** |
| 100/80 | 0.9820 | **1.0379** | 0.6162 | **0.6364** |
| 110/90 | *infeasible* | **0.9847** | - | 0.6182 |

The cascade's only escape from a hot user return was to shrink the inventory
until the store reached 139-149 C, which cripples intercooling; it lost 9 points
of delivery ratio by 100/80 and had no answer at all at 110/90. E-304 keeps the
inventory and lets the trunk continue below the user return, gaining 5-6 points
of delivery ratio AND 2 points of exergy efficiency on the hot users.

### 5.3 Where it still stops, and why

At 120/100 with `heat_user_exchanger_ntu = 5` the plant is rejected with

```text
  the heat-user exchanger class is too small ...
  required effectiveness=2.1847, available=0.9879
```

A required effectiveness above one is the exchanger stating that the duty is
impossible, not merely expensive: E-302 would have to take the trunk below its
own cold-side inlet. This is an honest finite-area limit on ONE body, and a
different limit from the cascade's, which was a topological squeeze. Raising the
class to `NTU = 15` makes 120/100 feasible at `R = 0.9515`, `eta_ex = 0.6104`,
with 275.3 kJ/kg-air sold at 68.2 kJ/kg-air of exergy - the highest heat exergy
of any point in this table.

### 5.4 Non-monotone demand: 300 bar, eight stages

| | cascade `K=1` | E-304 |
|---|---:|---:|
| `R_delivery` | 1.0743 | **1.0947** |
| `eta_exergy` | 0.6300 | 0.6235 |
| heat sold [kJ/kg-air] | 360.8 | **390.2** |
| worst HX endpoint spread [K] | 47.28 | **13.83** |

This train demands 64.45 C at stage two against 63.34 C at stage one, so the
suffix-maximum envelope puts both on one nozzle and the zone between them
carries no duty. Without the envelope the configuration is rejected outright.

## 6. Numerical work

Deterministic counts, not wall time, are the regression metric. Same machine and
config as above:

| | cascade `K=1` | E-304 | |
|---|---:|---:|---|
| light discharge trains | 1586 | **534** | -66% |
| `water_ratio_for_duty` calls | 8656 | **3184** | -63% |
| margin/drop root calls | 121 | **83** | -31% |
| charge trials | 386 | 520 | +35% |
| diagnostic seconds | 12.87 | **4.82** | 2.7x |

The discharge side got much cheaper because the margin is a far better
conditioned search coordinate than the equal drop was: every stage sits a known
distance above a known demand, so the inverse exchanger solves start close to
their answers instead of being dragged along one common temperature.

Charge trials rose because the cold tank moved to a new fixed point and the
charge allocation has to work harder to find it. That is a real cost and it is
not netted against the discharge saving above.

Reproduce with:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/profile_solver_work.py --config heat_and_power_example_config.json --property-api abstract_state
```

## 7. Regression invariants

Implementation changes are accepted only if they preserve:

- one hot stored state;
- exactly one heat-user exchanger, crossed by the complete inventory;
- exactly one extraction per expansion stage, summing to the inventory;
- a non-increasing extraction ladder that never starves a stage;
- one common margin above every stage demand;
- strictly decreasing trunk flow through the E-304 zones;
- a positive approach at BOTH terminals of every zone;
- recuperated duty equal to both the zone sum and the return's temperature rise;
- one counter-current external-user stream;
- mass closure inside the one-joule energy budget;
- component first-law residuals near machine precision;
- total exergy residual below 1 J/kg-air.

See `tests/test_extraction_exchanger.py` for executable definitions.
