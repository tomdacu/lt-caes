# Algorithm index

> **Parent:** [Documentation map](../00_DOCUMENTATION_MAP.md)  
> **Related:** [Optimization workflow](../04_OPTIMIZATION_WORKFLOW.md) · [Performance registry](../09_PERFORMANCE_AND_OPTIMIZATION.md)  
> **Code:** `caes/plant.py`, `caes/heat_exchangers.py`, `caes/thermodynamics.py`

The solver is nested because it must close several different physical
constraints. These pages separate the equations from their numerical method so
that a speed-up cannot silently change the plant being solved.

```text
candidate coolant inventory
  -> cold-loop closure
       -> charge train and hot store
       -> equal-drop discharge cascade
            -> inverse finite-NTU interheater duties and exact bleed mass
       -> O(N) heat-only E-303 suffix selection and cold-tank return
  -> objective ranking
```

| Block | Detailed page | Main unknown or output |
|---|---|---|
| Thermodynamic states | [Property API and cache](property_api_and_cache.md) | `State(p,T)` / `State(p,h)` and isentropic enthalpy |
| Charge | [Charge train](charge_train.md) | stage water splits and hot-store temperatures |
| Discharge | [Discharge train](discharge_train.md) | turbine work, coolant returns and feasibility |
| Coolant-loop root | [Cold-loop closure](cold_loop.md) | cold-tank temperature reproduced after selected E-303 routing and dwell |
| E-303 placement | [Cold-return recovery](cold_return_recovery.md) | maximum-ambient-duty ordered return suffix |
| Cascade profile | [Equal-drop cascade root](ladder_theta.md) | common station drop and group bleed distribution |
| Interheater sizing | [Inverse heat exchanger](heat_exchanger_inverse.md) | water/air ratio delivering a fixed duty |

Each page states invariants, numerical method, performance implications,
failure modes, and the tests that guard it.
