# Single-store TES and the discharge coolant cascade

> The filename is retained so existing links do not break; multi-level hot TES
> was removed from the active architecture.  
> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Concept specification:** [Single-store coolant cascade](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)  
> **Performance:** [Performance and optimization](09_PERFORMANCE_AND_OPTIMIZATION.md)

## 1. Model boundary

The active LTA/LTHP model contains one mixed hot coolant store and one mixed
cold coolant store. Parallel intercooler returns may have different local
temperatures, but they mix before the standing period. The configuration field
`coolant_cascade_groups` changes only the discharge network downstream of the
hot store.

The result fields `hot_level_temperatures_k` and
`hot_level_water_mass_ratios` remain tuples for result compatibility, but each
contains exactly one value. They must not be interpreted as a control for
stratified storage.

## 2. Solve hierarchy

For a trial conserved coolant inventory, the solver:

1. proposes a cold-tank temperature and solves the charge split and one mixed hot-store state;
2. builds the discharge branch returns;
3. selects the maximum-duty legal E-303 suffix, remixes it, and applies cold-tank standing;
4. computes each expansion stage's fixed moisture-safe minimum duty;
5. partitions those stages into K contiguous duty-balanced groups;
6. solves the common user-station drop `delta_T` so the K group bleeds consume
   the exact inventory;
7. materializes the accepted train once and checks heat, mass and exergy books;
8. ranks feasible inventories by the selected plant objective.

For every K, each station has the same plant-side drop:

```text
T_supply,g = T_hot - (g + 1) delta_T.
```

The total inverse-HX coolant demand is monotone in `delta_T`. A safeguarded
Illinois root, warm-started by the previous normalized drop, solves

```text
sum(b_g(delta_T)) - R_total = 0.
```

Only after that internal mass closure does the outer coolant-loop residual
compare the produced cold-tank temperature with its trial value.

## 3. Why the first user exchanger is largest

Let group bleed flows be `b_0 ... b_(K-1)`. The flow through station g is the
suffix sum

```text
R_g = b_g + b_(g+1) + ... + b_(K-1).
```

Thus `R_0 = R_total` and `R_(g+1) = R_g - b_g`. With the implemented common
drop,

```text
Q_user,g = R_g cp,coolant delta_T.
```

Every non-empty bleed makes `R_(g+1) < R_g`; therefore duties decrease strictly
and station zero supplies the most heat. There is no extra station after the
last bleed because its plant-side flow would be zero.

## 4. Finite exchanger constraints

Air/coolant interheaters use the common counter-current finite-NTU model. The
user cascade is an energy-balanced liquid/liquid series network whose every
station is checked against a finite counterflow NTU performance class.

This separation is explicit:

- `heat_exchanger_ntu` sizes the air/coolant exchanger performance class;
- `heat_user_exchanger_ntu` sizes every external liquid/liquid station;
- the user's mass flow is solved from total duty and configured supply/return,
  and is one repeated value across all stations.

## 5. Numerical work and measured improvement

Wall time is diagnostic only on an unstable workstation. The deterministic
measure is the number of `_light_discharge_at_supply` evaluations, each of
which represents one light discharge-train construction.

For `heat_and_power_example_config.json` with AbstractState after the corrected
topology and root optimizations:

| K | light discharge trains | diagnostic time |
|---:|---:|---:|
| 1 | 1586 | 5.6 s |
| 4 | 1179 | 11.2 s |

The earlier multi-level implementation measured 6843–6792 trains for K=2–4.
The K=4 count is therefore about 5.8 times smaller. K=1 increased because
branch-selective E-303 removes its guessed-return shortcut. Times must not be compared across machine states; counts
are the regression metric.

The same profiles counted 386 charge trials for K=1 and 1250 for K=4. Further
work must reduce both nested roots without changing the topology, but any reduction must preserve the
direct coolant ceiling and the accepted charge train exactly.

Reproduce the work count with:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/profile_solver_work.py --config heat_and_power_example_config.json --levels 4 --property-api abstract_state
```

## 6. Regression invariants

Implementation changes are accepted only if they preserve:

- one hot stored state for every K;
- exactly K stations and K non-empty group bleeds;
- station-zero flow equal to total inventory;
- continuous plant temperatures between stations;
- strictly decreasing trunk flow and duty;
- common station `delta_T` within numerical tolerance;
- one counter-current external-user stream;
- mass closure inside the one-joule energy budget;
- component first-law residuals near machine precision;
- total exergy residual below 1 J/kg-air.

See `tests/test_cascade.py` for executable definitions of these statements.
