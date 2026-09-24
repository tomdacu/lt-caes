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

## Heat-user solver (current)

Command used (one case list, run once per revision, serially):

```powershell
python scripts/benchmark_heat_user.py <repository root> bench.json   # each case = one CAESPlant.run()
```

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

The field-level deltas are intentional model changes, not numerical noise: the
inventory now lands on the active constraint boundary instead of a grid cell
near it, and the charge split is exergy-optimal
([document 14](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md)). Fingerprints of
every LTAHP combined-delivery result therefore change; LTA and
electricity-first results are unchanged, because their solver is untouched.

Test suite at this revision: 296 passed, with
`test_district_heating.py::test_electric_only_dispatch_does_not_hide_a_return_cooler`
deselected. It runs for more than 45 minutes on the old code as well.

## Extraction-margin evidence (history)

Configuration: supplied LTAHP example, AbstractState, one session. The baseline
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

On CoolProp 7.2.0, HEOS Air/Water and the supplied LTAHP configuration, the
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
