# Performance and optimization

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Children:** [Algorithm index](algorithms/README.md) · [Benchmarks](10_BENCHMARKS_AND_REGRESSION.md)  
> **Tools:** `scripts/profile_solver_work.py`, `scripts/compare_property_apis.py`

Performance changes may reduce repeated work, but may not silently change the
plant topology, constraints, objective or accepted balances. Wall-clock time
is diagnostic; deterministic work counts and complete-result fingerprints are
the primary evidence.

## Heat-user solver: measured against the coupled search

Since 2026-09-23 the combined-delivery LTAHP plant is solved in one variable
([document 14](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md)). Same machine,
one process at a time, CoolProp 7.2.0 AbstractState; "old" is commit `b08650a`
run from a worktree. Seconds are wall clock for one `CAESPlant.run()`.

| case | old s | new s | old J / RTE / eta_ex | new J / RTE / eta_ex |
|---|---:|---:|---|---|
| 85.8 bar, 6+6, 80/45 (reference) | 4.2 | 7.9 | 1.0744 / 0.5503 / 0.6241 | 1.0745 / 0.5511 / 0.6248 |
| 85.8 bar, 6+6, 95/75 | 40.0 | 9.2 | 1.0624 / 0.5435 / 0.6448 | 1.0715 / 0.5434 / 0.6465 |
| 85.8 bar, 6+6, 110/90 | 36.5 | 8.2 | 0.9847 / 0.5102 / 0.6182 | 1.0399 / 0.5109 / 0.6313 |
| 30 bar, 6+6, 95/75 | 86.7 | 5.9 | 0.9616 / 0.5273 / 0.6121 | 1.0285 / 0.5271 / 0.6250 |
| 150 bar, 3+3, 80/45 | 56.2 | 2.2 | 0.9154 / 0.4806 / 0.5418 | 0.9165 / 0.4798 / 0.5413 |
| 250 bar, 6+6, 80/45 | 14.8 | 4.7 | 1.0359 / 0.5333 / 0.6041 | 1.0326 / 0.5354 / 0.6054 |
| 85.8 bar, 8+8, 95/75 | 298.0 | 7.1 | 1.0148 / 0.5047 / 0.6043 | 1.0678 / 0.5067 / 0.6163 |
| 250 bar, 3+3, 80/45 | 298.8, `SearchUnresolved` | 10.3, constraint map | - | infeasible: coolant ceiling and E-304 area cross |

How to read it:

- **Hot users are where it pays.** The old search stopped a grid cell short
  of the E-302 boundary, and the exergy split lifts the store. Delivery ratio
  and exergy efficiency rise together (+5 to +7 points of J at 110/90, 95/75
  and 8+8), and RTE stays within 0.03 points.
- **The reference case is slower** (7.9 s against 4.2 s). Its optimum is
  interior, the old coarse walk happened to land close to it, and the new
  search pays for the scan, the window bisection and the split. The result is
  marginally better on all three metrics.
- **At 250 bar, 6+6, J goes down** (1.0359 to 1.0326) while RTE and exergy go
  up. This is the split rule doing what it is for: exergy values 80/45 heat at
  theta = 0.14, so it trades a little heat for work, and J, which values heat
  at 1, reads that as a loss. See [document 14](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md#6-what-is-and-is-not-claimed).
- **At 150 bar, 3+3** the optimum is on the coolant ceiling; the new search
  finds the boundary itself, J rises by 0.001 and exergy falls by 0.0005.
- Every new result closes the exergy book to below 0.005 J/kg-air.

The sections below describe the coupled cold-loop solver, which LTA-CAES and
electricity-first LTAHP still use, and the history of the extraction-margin
work.

## Current nesting (coupled solver)

```text
inventory candidates
  -> cold-tank temperature closure
       -> charge allocation and one mixed hot store
       -> extraction-margin mass root (also fixes the E-302 duty)
            -> inverse finite-NTU HX for every expansion stage
       -> O(N log N) analytical E-303 coldest-group selection
       -> O(N) E-304 zone march into the cold-tank inlet
  -> objective ranking.
```

Neither the former multi-level `theta` root nor the equal-drop cascade root that
replaced it is part of the active architecture. Note that the outer search still
has exactly ONE variable: because the first extraction is the trunk inlet, the
margin root also fixes how much heat E-302 sells, so making the sold-versus-
recuperated split explicit would have added a search dimension for nothing.

## Implemented reductions

| Optimization | Exactness mechanism | Effect |
|---|---|---|
| Selectable AbstractState/PropsSI API | One plant-wide `PropertyAPI`; cache key includes API | Controlled backend comparison |
| PT, PH, cp and isentropic caches | Exact input floats, fluid and API in key | Reuse repeated CoolProp states |
| Per-plant discharge requirements | Keyed by protected humidity | Do not resolve invariant moisture-safe targets |
| Reduced discharge evaluation | Propagates achieved HX duties and real turbine states | Avoid trial `Cycle` objects |
| Accepted-ratio reuse | Accepted inverse ratios feed final forward materialization | No duplicate final inverse |
| Cold-loop continuation and Illinois refinement | Re-evaluate seed; safeguarded bracket and full-window fallback | Fewer tank-temperature residuals |
| Extraction-margin continuation | Re-evaluate the previous normalized margin | Fewer mass-root trials |
| Duty-matched ladder | Each stage starts a known margin above its own demand | Inverse HX solves start near their answers; 66% fewer discharge trains |
| Cheap recuperation residual | Suffix sums only, no per-zone checks on trial points | E-304 zone effectiveness and pinch are paid once, on the accepted design |
| Secant mass continuation | Smooth local predictor plus safeguarded global mass bracket | Removes part of the repeated discharge work |
| E-303 group enumeration | Closed-form duty; N temperature-ordered thresholds | No nested topology root and no 2^N subset search |

## Work-count evidence

For `heat_and_power_example_config.json`, AbstractState, measured on one machine
against the frozen serial cascade at commit `22b7bb7`:

| | cascade `K=1` | E-304 | |
|---|---:|---:|---|
| light discharge trains | 1586 | **534** | -66% |
| `water_ratio_for_duty` calls | 8656 | **3184** | -63% |
| mass-root calls | 121 | **83** | -31% |
| charge trials | 386 | 520 | +35% |
| diagnostic seconds | 12.87 | **4.82** | 2.7x |

The discharge side got much cheaper because the margin is a far better
conditioned search coordinate than the common drop was: every stage sits a known
distance above a known demand, so the inverse exchanger solves start close to
their answers instead of being dragged along one shared temperature.

Charge trials rose because the cold tank moved to a new fixed point - E-304
recuperation warms it - and the charge allocation has to work harder to find it.
That is a real cost and it is not netted against the discharge saving above.

Counts remain the regression metric; times are diagnostic and vary by
workstation state. Both columns above were taken in the same session.

## Current bottleneck and next safe work

The electricity-first path is now the slow one. At the default configuration
`test_electric_only_dispatch_does_not_hide_a_return_cooler` runs for more than
45 minutes on both the old and the new code, and two LTA infeasibility tests
take 320-380 s each: an infeasible inventory is proved only by walking the whole
cold-tank window. A reduction of that dispatch (a one-dimensional fixed point in
the cold tank per inventory, instead of a sampled root search) is the next
target.

Within the coupled solver, charge-side allocation dominates even more clearly than before: it is 520 of
the trials against 534 discharge trains, and each charge trial is itself a
fixed-point iteration. Candidate accelerations are:

- continue the ceiling-relief blend and capacity-matched split together across
  neighbouring return/inventory points;
- cache exact accepted charge trials by their physical coordinates within one
  plant solve;
- derive a safeguarded sensitivity seed for the charge fixed point;
- audit global cold-loop root uniqueness before relying exclusively on local
  continuation.

Tabulation or surrogate fits remain research items. They require explicit
interpolation-error bounds and full rechecking of direct coolant, HX saturation,
moisture and icing constraints.

## Property API policy

AbstractState and PropsSI are interfaces to the same selected CoolProp backend,
not two plant solvers. One constructor/CLI parameter switches all pure-fluid
calls in a run; humid-air properties remain HAPropsSI because CoolProp exposes
that model separately. Exact state caches are partitioned by API, fluid and
inputs. Covered comparisons currently agree end to end, but reproducible
research must record CoolProp version, backend and selected API. See
[Property API and cache](algorithms/property_api_and_cache.md).

## Acceptance gates

1. Preserve topology and all feasibility decisions.
2. Preserve selected inventory and reported work/heat within documented root
   tolerances; explain any intentional fingerprint change field by field.
3. Keep component first-law and whole-plant exergy residuals below 1 J/kg-air.
4. Exercise K=1, intermediate K and K=N, plus coolant and moisture boundaries.
5. Count expensive work independently of elapsed time.
6. Retain a bracketed fallback whenever a continuation seed can leave its
   validated branch.
