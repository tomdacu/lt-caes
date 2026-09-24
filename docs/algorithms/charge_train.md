# Charge train

> **Parent:** [Algorithm index](README.md)  
> **Related:** [Physics boundary](../02_PHYSICS_AND_MODEL_BOUNDARY.md) · [Cold-loop closure](cold_loop.md)  
> **Code:** `CAESPlant._charge_adiabatic`, `_charge_with_ratios`, `_finalize_charge` in `caes/plant.py`  
> **Tests:** `tests/test_plant.py`, `tests/test_thermal_limits.py`

The air path is sequential; the cold-coolant branches are parallel. For a trial
cold-tank temperature and conserved total coolant/air ratio, each compressor
stage is followed by a finite-NTU cooler. Its branch ratio is iterated toward
capacity matching using the real secant air heat capacity, then projected back
onto the conserved total water ratio.

The mixed branch-return enthalpy defines the one hot store. Cascade group count
does not alter this charge calculation. Every coolant state must remain within
the configured direct limits.

The fixed point remains numerical because the real air `cp`, exchanger
effectiveness and downstream compressor inlet states depend on the current
split. The accepted feasibility trial is retained and finalized once with the
moisture diagnostic; rebuilding the same physical train a second time was an
exact duplicate and has been removed.

## The split with a heat user

With a heat user and combined delivery, the capacity-matched split (or its
relief blend) is only the starting shape. Two multipliers, on the first and
on the last branch, are then optimized for maximum useful exergy at the
explicit cold tank, with the middle branches rescaled to keep the inventory
exact (`_exergy_optimal_charge_split`). Hot users switch the first intercooler
off and give the last one 30-40 % more water; mild users stay within 0.02
exergy points of capacity matching. Why exergy and not the delivery ratio, and
why two shares and not N, is in
[document 14](../14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md#4-rules-for-the-charge-split).
The electricity-first dispatch keeps the capacity-matched split: its free
optimum was measured 0.0001 RTE better.

Main invariants:

- sum of branch coolant ratios equals the candidate inventory;
- no local clamp hides rejected heat;
- compressor work and cooler duty satisfy each component first-law balance;
- coolant temperature stays within configured limits;
- the returned result is the exact train used for feasibility.
