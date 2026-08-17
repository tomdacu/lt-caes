# Property API and cache

> **Parent:** [Algorithm index](README.md)  
> **Related:** [Performance registry](../09_PERFORMANCE_AND_OPTIMIZATION.md) · [Benchmark protocol](../10_BENCHMARKS_AND_REGRESSION.md)  
> **Code:** `caes/thermodynamics.py`, `caes/plant.py`, `caes/cli.py`  
> **Tests/tools:** `tests/test_thermodynamics.py`, `scripts/compare_property_apis.py`

## Interfaces and scope

`PropertyAPI.ABSTRACT_STATE` and `PropertyAPI.PROPS_SI` select two CoolProp
interfaces for pure-air and pure-water properties. They do not select two CAES
solvers. The plant equations, backend (`HEOS` unless explicitly changed), fluid
and reference state remain common.

The selection enters once through `CAESPlant(..., property_api=...)` or
`--property-api`. A context-local setting then governs every call to `state_pt`,
`state_ph`, `air_cp`, isentropic enthalpy and water saturation. Humid-air
psychrometric properties remain on `HAPropsSI`, the appropriate CoolProp
interface for that model.

## Why `AbstractState` is the default

`PropsSI` is a convenient stateless high-level call. `AbstractState` reuses one
state object per fluid and avoids repeated backend setup. In the covered CAES
domain they currently return identical solver results, while `AbstractState` is
faster. This is an empirical statement for the recorded CoolProp version and
backend, not a guarantee for all versions or fluids.

The current reference run uses CoolProp 7.2.0 with HEOS Air/Water. It found an
identical primitive grid, identical 1,586 light-train decisions and an
identical complete `PlantResult`; only diagnostic call time differed. The
recorded numbers live in [the benchmark protocol](../10_BENCHMARKS_AND_REGRESSION.md#property-interface-comparison).

## Cache design

The following exact-result LRU caches exist:

| Function | Maximum entries | Key includes |
|---|---:|---|
| PT state | 65,536 | pressure, temperature, fluid, property API |
| PH state | 65,536 | pressure, enthalpy, fluid, property API |
| air `cp` | 131,072 | pressure, temperature, fluid, property API |
| isentropic enthalpy | 65,536 | inlet pressure/entropy, outlet pressure, fluid, property API |

Inputs are not rounded. Rounding would turn a performance cache into a model
approximation and could move a narrow feasibility boundary. Including the API
prevents a preceding `PropsSI` run from supplying cached values to an
`AbstractState` comparison or vice versa.

`CAESPlant.run()` also caches complete immutable results by
`(PlantConfig, PropertyAPI)` and returns a deep copy. Per-plant discharge target
states are cached separately by protected humidity ratio so plant instances are
not pinned forever by a bound-method global cache.

## Reproducibility rule

Always record CoolProp version, backend, fluid, API selection and configuration.
A 30% change between revisions should first be localized by comparing raw
states, component processes and complete fingerprints. It must not be
attributed to the API interface without that controlled comparison.
