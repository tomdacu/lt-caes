# Future hot-to-cold recuperator study

> **Status:** explored conceptually; not implemented  
> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Prerequisite:** [Heat-only cold-return recovery](algorithms/cold_return_recovery.md)

## Proposed function

If the external user accepts heat only above a threshold (for example 40 °C),
some lower-grade hot-cascade duty may have no useful buyer. The proposed extra
exchanger would transfer that otherwise unusable heat into the final cold-return
stream after:

1. the optimized cold suffix has mixed;
2. E-303 has warmed that suffix from ambient;
3. the warmed suffix has mixed with the bypass returns;
4. but before the cold tank.

This is an internal recuperator, not E-303. It moves energy inside the plant
boundary and therefore cannot be counted as a new product or ambient input.

## Why it is not included yet

Adding it changes the hot-side heat-user allocation, cold-loop fixed point,
available temperature grades and potentially the optimal E-303 cutoff. It must
therefore be solved simultaneously, not added as a post-processing credit. A
credible implementation needs at least:

- a user minimum useful-temperature or demand curve;
- its own finite NTU and pressure drops;
- a pinch-safe hot-source selection rule;
- proof that transferred heat does not reduce useful heat or turbine work more
  than it improves the next charge;
- pump/fan parasitics and equipment cost for configuration ranking.

The first study should compare three explicit topologies: no recuperator,
recuperator before E-303, and recuperator after E-303/final mixing. The last is
the user's proposed baseline and avoids warming a stream that E-303 could have
heated freely, but the whole-cycle optimum must still be demonstrated.
