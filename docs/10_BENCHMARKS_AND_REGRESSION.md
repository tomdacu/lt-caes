# Benchmarks and regression protocol

> **Parent:** [Performance and optimization](09_PERFORMANCE_AND_OPTIMIZATION.md)  
> **Tools:** `scripts/profile_solver_work.py`, `scripts/compare_property_apis.py`

Timings vary with machine load. Work counts, result fingerprints and physical
residuals are the reproducible contract.

## Commands

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/profile_solver_work.py --config heat_and_power_example_config.json --levels 4
python scripts/compare_property_apis.py --config heat_and_power_example_config.json
```

The profiler hashes the complete sorted `PlantResult` and reports work/heat,
objective, inventory evaluations, component first-law residual and total exergy
residual.

## Current structural evidence

Configuration: supplied LTHP example, AbstractState. These are diagnostic runs
of the implemented single-store topology; rerun after any solver change.

| cascade groups K | light discharge evaluations | charge trials | final materializations | diagnostic time | fingerprint prefix |
|---:|---:|---:|---:|---:|---|
| 1 | 1586 | 386 | 10 | 5.6 s | `c4d62b6a...` |
| 4 | 1179 | 1250 | 5 | 11.2 s | `50d90107...` |

The retired multi-level path measured about 6792 light trains at K=4. The
current heat-only, branch-selective topology cuts that to 1179. K=1 increased
because it no longer has a mathematically valid guessed-mixed-return shortcut;
this model correction is recorded rather than mislabeled as an optimization.

## Property-interface comparison

On CoolProp 7.2.0, HEOS Air/Water and the default K=1 configuration, the
controlled comparison produced:

| interface | light trains | materializations | diagnostic time | complete result |
|---|---:|---:|---:|---|
| AbstractState | 1586 | 10 | 5.6 s | identical |
| PropsSI | 1586 | 10 | 35.3 s | identical |

The primitive PT/PH/cp/saturation grid was also exactly identical. Thus the
front-end switch changes call overhead, not the equations or solver work, in
this covered domain. These seconds are a local diagnostic, not a universal
speed ratio; rerun `compare_property_apis.py` after changing CoolProp, backend
or fluid.

## Regression record

Every published run should include:

- repository revision or archive hash;
- Python and CoolProp versions, backend, fluid and selected PropertyAPI;
- full configuration and command-line overrides;
- cold/warm process and result-cache state;
- complete fingerprint and method counts;
- selected inventory, objective and physical residuals;
- elapsed time, explicitly labelled diagnostic.

An intentional model correction may change a fingerprint. In that case record
the topology/equation change and compare field-level deltas; never describe a
changed result as a pure speed-up.
