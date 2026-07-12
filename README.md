# CAES Storage

An energy-balanced, batch-performance simulator for compressed-air energy
storage (CAES). It replaces the previous preview scripts and the partially
overlapping `CAES_program` implementation with one root-level project.

The model supports two clearly separated modes:

- **A-CAES (`adiabatic`)**: intermediate compression heat is recovered into a
  finite sensible-water store, then used for turbine reheat. The reported
  round-trip efficiency is shaft/electrical output divided by shaft/electrical
  compression input.
- **D-CAES (`diabatic`)**: heat rejected during compression is not stored.
  Ambient reheat can be modelled between turbine stages, but it is reported as
  an external heat input. The program deliberately does **not** call the
  resulting shaft-work ratio a storage-only round-trip efficiency.

## Quick start

```powershell
python -m pip install -r requirements.txt
python -m pytest
python -m caes.cli --mode adiabatic --plot artifacts/cycle.png
python -m caes.cli --write-default-config example_config.json
python -m caes.cli --config example_config.json
python -m caes.cli --config counterflow_example_config.json
```

The command reports compression work, expansion work, the shaft-work ratio,
thermal-store recovery/delivery/losses, and (for A-CAES only) a closed-cycle
round-trip efficiency. The counter-current configuration additionally reports
per-exchanger `UA`, NTU performance, total heat-transfer area, and an optional
user-supplied screening-cost correlation.

## Modelling boundary

This is a **steady-flow, fixed-mass batch model**. The air in the store is
assumed to reach ambient temperature during a long dwell at the specified
storage pressure. The water store is a finite, well-mixed sensible store.
Consequently it is suitable for conceptual comparison and sensitivity studies,
not for sizing a real cavern, heat exchanger, or tank without further work.

Read [the physics and assumptions](docs/PHYSICS.md), [configuration and use](docs/USAGE.md), and [the migration record](docs/MIGRATION.md) before interpreting results.

## Validation

The test suite verifies component energy balances, final pressures, heat-store
energy conservation, pressure/temperature constraints, and correct handling of
external D-CAES heat. It does not validate a specific commercial plant.

## Sources

The implementation uses [CoolProp's high-level property interface](https://coolprop.org/coolprop/HighLevelAPI.html) for real-fluid air properties. The mode definitions follow the [IEA Energy Storage CAES fact sheet](https://www.iea-es.org/wp-content/uploads/public/FactSheet_mechanical_CAES.pdf): A-CAES temporarily stores the heat of compression for reuse during expansion.
