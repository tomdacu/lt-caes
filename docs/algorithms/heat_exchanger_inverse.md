# Inverse heat exchanger

> **Parent:** [Algorithm index](README.md)  
> **Related:** [Equal-drop cascade root](ladder_theta.md) · [Physics boundary](../02_PHYSICS_AND_MODEL_BOUNDARY.md)  
> **Code:** `water_ratio_for_duty` and `_counterflow_air_duty` in `caes/heat_exchangers.py`  
> **Tests:** heat-exchanger and plant tests in `tests/`

The inverse asks for the water/air mass ratio `r` that delivers a target
air-side duty at a stated water inlet temperature. It solves the same
counter-current finite-NTU law used by the forward exchanger.

It is not generally a constant-`cp` algebraic division. Effectiveness depends
on the capacity ratio, the limiting capacity side can switch, air `cp` is
relocated iteratively at the exchanger mean temperature, and duty saturates as
coolant flow increases. The duty is monotone and saturating in the admissible
branch, enabling a capacity-rate seed followed by bracketed Illinois refinement.

The return is `(ratio, achieved_duty)`. Callers must check saturation: reaching
the maximum allowed ratio does not imply the target was achieved. They must
also propagate `achieved_duty`, not silently substitute the requested target,
because outer roots can be narrower than the inverse tolerance.

Constant NTU is a design-screening assumption. Each candidate exchanger is
implicitly resized to the selected performance class; this inverse does not
represent the off-design flow map of a fixed physical core.
