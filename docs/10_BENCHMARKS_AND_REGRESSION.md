# Benchmarks and regression protocol

> **Parent:** [Performance and optimization](09_PERFORMANCE_AND_OPTIMIZATION.md)  
> **Tools:** `scripts/profile_solver_work.py`, `scripts/compare_property_apis.py`

Timings vary with machine load. Work counts, result fingerprints and physical
residuals are the reproducible contract.

## Commands

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/profile_solver_work.py --config heat_and_power_example_config.json
python scripts/compare_property_apis.py --config heat_and_power_example_config.json
```

The profiler hashes the complete sorted `PlantResult` and reports work/heat,
objective, inventory evaluations, component first-law residual and total exergy
residual.

## Current structural evidence

Configuration: supplied LTHP example, AbstractState, one session. The baseline
column is the frozen serial cascade at commit `22b7bb7`, run in a worktree on
the same machine.

| topology | light discharge evaluations | charge trials | final materializations | diagnostic time | fingerprint prefix |
|---|---:|---:|---:|---:|---|
| serial cascade, `K=1` (`22b7bb7`) | 1586 | 386 | 10 | 12.9 s | `c4d62b6a...` |
| E-302 + E-304 extraction | 534 | 520 | 10 | 4.8 s | `b9e2b02d...` |

The fingerprint changed because the plant changed, not because a numerical
shortcut was taken: this is a different topology with a different accepted
inventory, cold-tank temperature and heat product. The field-level deltas are
tabulated in
[the results section](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md#5-measured-against-the-frozen-cascade).

The discharge saving comes from the search coordinate: the extraction margin
starts every inverse HX solve a known distance above a known demand, where the
equal drop dragged all of them along one shared temperature. The charge-side
increase is a real cost of the warmer cold tank and is not netted against it.

## Property-interface comparison

On CoolProp 7.2.0, HEOS Air/Water and the supplied LTHP configuration, the
controlled comparison produced:

| interface | light trains | materializations | diagnostic time | complete result |
|---|---:|---:|---:|---|
| AbstractState | 534 | 10 | 5.2 s | identical |
| PropsSI | 534 | 10 | 27.7 s | identical |

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
