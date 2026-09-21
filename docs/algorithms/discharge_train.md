# Discharge train

> **Parent:** [Algorithm index](README.md)  
> **Children:** [Extraction-margin mass root](ladder_theta.md) · [Inverse heat exchanger](heat_exchanger_inverse.md)  
> **Related:** [Single-store TES and the extraction network](../08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md)  
> **Code:** `_solve_discharge_requirements`, `_light_discharge_at_supply`, `_materialize_ladder` in `caes/plant.py`  
> **Tests:** `tests/test_extraction_exchanger.py`, `tests/test_district_heating.py`, `tests/test_plant.py`

For LTAHP, the turbine pressure train and efficiency together with the
moisture-safe outlet envelope determine, for every stage, both a minimum target
duty AND the air temperature its interheater must produce. That second quantity
is what E-304's extraction ladder is matched to. At each extraction temperature
the finite-HX inverse computes the coolant ratio needed to deliver the duty.

Trial evaluations propagate the actual achieved duty returned by the inverse,
construct the corresponding PH state, perform the real expansion and pass that
state to the next stage. This is intentionally stricter than propagating a
precomputed ideal trajectory: the inverse tolerance creates small real duty
differences that can matter to a narrow outer root.

Only accepted designs are materialized into a `Cycle` of `Process` objects. The
materializer reuses the accepted ratios, evaluates each forward exchanger and
expander, and verifies water-mass closure and coolant limits. Thus the reporting
path is complete while trial points avoid thousands of duplicate objects and HX
forward calls.

LTA without a heat user follows a different dispatch: conserved coolant is
allocated to maximize turbine work subject to moisture and temperature limits.
If full absorption is impossible, the documented minimum-duty bypass sends the
unabsorbed water to E-303 without relaxing a physical constraint.
