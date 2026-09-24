"""Serial benchmark of one repository revision on a fixed LTAHP case list.

    python scripts/benchmark_heat_user.py <repository root> <output.json>

Run it once per revision (for example once in a worktree of an older commit and
once here), one process at a time, and compare the two JSON files. Each case is
one complete ``CAESPlant.run()``; wall-clock seconds are diagnostic only.
"""
import json, os, sys, tempfile, time
repo = sys.argv[1]; out = sys.argv[2]
sys.path.insert(0, repo)
from caes import CAESPlant, load_config
CASES = [
    ("85.8 bar, 6+6, 80/45", {}),
    ("85.8 bar, 6+6, 95/75", {"heat_user_supply_temperature_c": 95.0, "heat_user_return_temperature_c": 75.0}),
    ("85.8 bar, 6+6, 110/90", {"heat_user_supply_temperature_c": 110.0, "heat_user_return_temperature_c": 90.0}),
    ("30 bar, 6+6, 95/75", {"storage_pressure_bar": 30.0, "heat_user_supply_temperature_c": 95.0, "heat_user_return_temperature_c": 75.0}),
    ("150 bar, 3+3, 80/45", {"storage_pressure_bar": 150.0, "compressor_stages": 3, "expander_stages": 3}),
    ("250 bar, 6+6, 80/45", {"storage_pressure_bar": 250.0}),
    ("85.8 bar, 8+8, 95/75", {"compressor_stages": 8, "expander_stages": 8, "heat_user_supply_temperature_c": 95.0, "heat_user_return_temperature_c": 75.0}),
    ("250 bar, 3+3, 80/45", {"storage_pressure_bar": 250.0, "compressor_stages": 3, "expander_stages": 3}),
]
rows = []
for name, overrides in CASES:
    base = json.load(open(os.path.join(repo, "heat_and_power_example_config.json")))
    base.update(overrides)
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
    json.dump(base, open(path, "w"))
    config = load_config(path)
    t = time.perf_counter()
    try:
        r = CAESPlant(config).run()
        row = dict(case=name, ok=True, seconds=round(time.perf_counter() - t, 1),
                   J=r.useful_energy_delivery_ratio, RTE=r.round_trip_efficiency,
                   eta_ex=r.exergy.total_useful_exergy_efficiency,
                   R=r.thermal_store.total_water_mass_ratio,
                   points=r.optimization.evaluated_points,
                   exergy_residual=r.exergy.balance_residual_j_per_kg_air)
    except Exception as exc:
        row = dict(case=name, ok=False, seconds=round(time.perf_counter() - t, 1),
                   error=f"{type(exc).__name__}: {str(exc)[:600]}")
    rows.append(row)
    print(json.dumps(row), flush=True)
json.dump(rows, open(out, "w"), indent=1)
