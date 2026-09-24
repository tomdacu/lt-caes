# Algorithm index

> **Parent:** [Documentation map](../00_DOCUMENTATION_MAP.md)  
> **Related:** [Optimization workflow](../04_OPTIMIZATION_WORKFLOW.md) · [Performance registry](../09_PERFORMANCE_AND_OPTIMIZATION.md)  
> **Code:** `caes/plant.py`, `caes/heat_exchangers.py`, `caes/thermodynamics.py`

The solver is nested because it must close several different physical
constraints. These pages separate the equations from their numerical method so
that a speed-up cannot silently change the plant being solved.

Heat-user plant (LTAHP, combined delivery) - no coolant-loop root:

```text
inventory scan -> constraint boundary / Brent
  -> stored humidity
  -> extraction-margin root (also fixes the E-302 duty)
       -> inverse finite-NTU interheater duties and exact bleed mass
  -> O(N log N) heat-only E-303 coldest-group selection and final mixing
  -> E-304 recuperation and dwell: the cold tank, explicitly
  -> charge train at that tank, exergy-optimal two-share split
```

Electricity-first plant (LTA, and LTAHP with `max_electric_efficiency`):

```text
candidate coolant inventory
  -> cold-loop closure (root on the cold-tank temperature)
       -> charge train and hot store
       -> absorbing discharge allocation
       -> heat-only E-303 coldest-group selection and final mixing
  -> objective ranking
```

| Block | Detailed page | Main unknown or output |
|---|---|---|
| Thermodynamic states | [Property API and cache](property_api_and_cache.md) | `State(p,T)` / `State(p,h)` and isentropic enthalpy |
| Charge | [Charge train](charge_train.md) | stage water splits and hot-store temperatures |
| Discharge | [Discharge train](discharge_train.md) | turbine work, coolant returns and feasibility |
| Heat-user search | [One-dimensional heat-user solver](../14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md) | inventory, binding-constraint map, exergy-optimal charge split |
| Coolant-loop root | [Cold-loop closure](cold_loop.md) | cold-tank temperature reproduced after selected E-303 routing and dwell (electricity-first dispatch only) |
| E-303 placement | [Cold-return recovery](cold_return_recovery.md) | maximum-ambient-duty coldest return group |
| Extraction ladder | [Extraction-margin mass root](ladder_theta.md) | common margin, extraction temperatures and bleed distribution |
| Interheater sizing | [Inverse heat exchanger](heat_exchanger_inverse.md) | water/air ratio delivering a fixed duty |

Each page states invariants, numerical method, performance implications,
failure modes, and the tests that guard it.
