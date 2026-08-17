# Performance and optimization

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Children:** [Algorithm index](algorithms/README.md) · [Benchmarks](10_BENCHMARKS_AND_REGRESSION.md)  
> **Tools:** `scripts/profile_solver_work.py`, `scripts/compare_property_apis.py`

Performance changes may reduce repeated work, but may not silently change the
plant topology, constraints, objective or accepted balances. Wall-clock time
is diagnostic; deterministic work counts and complete-result fingerprints are
the primary evidence.

## Current nesting

```text
inventory candidates
  -> cold-tank temperature closure
       -> charge allocation and one mixed hot store
       -> K-group equal-drop mass root
            -> inverse finite-NTU HX for every expansion stage
       -> O(N) analytical E-303 suffix selection
  -> objective ranking.
```

The former multi-level `theta` root and repeated feasibility bisection are not
part of the active architecture.

## Implemented reductions

| Optimization | Exactness mechanism | Effect |
|---|---|---|
| Selectable AbstractState/PropsSI API | One plant-wide `PropertyAPI`; cache key includes API | Controlled backend comparison |
| PT, PH, cp and isentropic caches | Exact input floats, fluid and API in key | Reuse repeated CoolProp states |
| Per-plant discharge requirements | Keyed by protected humidity | Do not resolve invariant moisture-safe targets |
| Reduced cascade evaluation | Propagates achieved HX duties and real turbine states | Avoid trial `Cycle` objects |
| Accepted-ratio reuse | Accepted inverse ratios feed final forward materialization | No duplicate final inverse |
| Cold-loop continuation and Illinois refinement | Re-evaluate seed; safeguarded bracket and full-window fallback | Fewer tank-temperature residuals |
| Equal-drop continuation | Re-evaluate previous normalized drop | Fewer K>1 mass-root trials |
| Secant mass continuation | Smooth local predictor plus safeguarded global mass bracket | Removes part of the repeated cascade work |
| E-303 cutoff enumeration | Closed-form suffix duty; N legal cutoffs | No nested topology root and no 2^N subset search |

## Work-count evidence

For `heat_and_power_example_config.json`, AbstractState, on the corrected
single-store topology:

| K | light discharge trains | charge trials | diagnostic time |
|---:|---:|---:|---:|
| 1 | 1586 | 386 | 5.6 s |
| 4 | 1179 | 1250 | 11.2 s |

The earlier multi-level implementation required about 6792 light discharge
trains at K=4; the current K=4 topology removes about 83% of that work. K=1 is
now more expensive than the former 256-train special path because
branch-selective E-303 invalidated its guessed-mean first-law shortcut: K=1 must
close exact coolant mass inside each cold-tank residual. This is an intentional
model cost, not presented as a speed-up. Counts remain the regression metric;
times are diagnostic and vary by workstation state.

## Current bottleneck and next safe work

Charge-side allocation now dominates. Candidate accelerations are:

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
