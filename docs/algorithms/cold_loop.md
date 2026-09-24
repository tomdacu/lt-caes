# Cold-loop closure

> **Parent:** [Algorithm index](README.md)  
> **Related:** [Charge train](charge_train.md) · [Discharge train](discharge_train.md) · [E-303 optimization](cold_return_recovery.md)  
> **Code:** `CAESPlant._close_cold_loop` in `caes/plant.py`

**Scope.** This root exists only under the electricity-first (absorbing)
dispatch. With a heat user and combined delivery the cold tank is an explicit
function of the inventory and no root is solved; see
[document 14](../14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md#1-three-structural-facts).

The root coordinate is the cold-tank temperature. This is required by the
branch-selective E-303 topology: an untreated all-return mean loses the branch
distribution and therefore cannot determine which returns are warmed or how
much ambient heat enters.

For one conserved coolant inventory, every residual evaluation performs:

```text
trial cold-tank temperature
 -> charge train and one mixed hot store
 -> discharge branch flows and temperatures
 -> analytic selection of the one E-303 group, coldest returns first
 -> final mixing of the warmed group and the bypass returns
 -> E-304 recuperation into that mixture (heat user only)
 -> cold-tank standing map
 -> produced cold-tank temperature.
```

The residual is `produced - trial`. The admissible window is bounded by the
direct coolant limits and moisture-correlation domain. A previous inventory's
root seeds a local bracket; a full deterministic window walk remains the
fallback because root uniqueness has not been proven globally. Illinois
refinement is safeguarded by bisection and the accepted materialized cycle
rechecks the physical cold-tank closure.

The old raw-mixed-return coordinate was valid only while every return was mixed
before one bidirectional E-303. It is intentionally retired: it cannot represent
the current topology.

Failures are not assigned a direction unless physics proves one. A heat-user
hot-end rejection while increasing coolant inventory is directional because
more coolant lowers the mixed hot-store temperature; a generic finite-HX or
closure failure is not.
