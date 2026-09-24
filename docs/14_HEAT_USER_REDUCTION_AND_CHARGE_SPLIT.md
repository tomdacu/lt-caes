# The heat-user plant is one-dimensional: reduction, objectives and the charge split

> **Parent:** [Theory and design objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md)  
> **Related:** [Optimization workflow](04_OPTIMIZATION_WORKFLOW.md) · [Metrics and exergy](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) · [Performance](09_PERFORMANCE_AND_OPTIMIZATION.md)  
> **Code:** `CAESPlant._run_heat_user_search`, `_heat_user_design`, `_exergy_optimal_charge_split` in `caes/plant.py`  
> **Scope:** LTAHP-CAES under `max_combined_energy_delivery` (E-302 and E-304 active). LTA-CAES and electricity-first LTAHP keep the coupled cold-loop solver.

This document records why the combined-delivery LTAHP plant can be solved as a
one-variable problem, the energy identity that explains its objective, and the
rule that now chooses the charge split. Every claim is marked as an identity
of the model, a measurement, or a design decision.

## 1. Three structural facts

Symbols, all per kilogram of dry air:

```text
R        conserved coolant inventory, kg water / kg air      (the design variable)
w        stored humidity ratio after the charge train
T_c      cold-tank temperature
T_h      hot-store temperature available to discharge
m        common E-304 extraction margin
T_d,g    air temperature interheater g must produce (moisture envelope)
```

**Fact 1 - the ladder does not see either tank (identity).** Each extraction
sits at `T_d,g + m`. The bleed each stage needs follows from its fixed
moisture-safe duty and that supply, so the mass equation

```text
sum_g b_g(T_d,g + m) = R
```

contains `R` and `w` only. The hot store enters as an inequality,
`T_h >= T_d,0 + m`, never in the equation.

**Fact 2 - the cold tank is explicit (identity).** E-303, final mixing, E-304
recuperation and cold-tank dwell act on the returns and extraction
temperatures of Fact 1. None of them depends on the trial cold-tank
temperature, so

```text
T_c(R) = T0 + d(R) * ( Phi(returns(R), supplies(R)) - T0 )
```

is one evaluation, not a root. Measured at the reference plant: trial `T_c`
from 5 to 55 °C produced the same `T_c = 37.4726 °C` at `R = 1.5`, and the
same `41.4823 °C` at `R = 2.0`, identical to the printed digits.

**Fact 3 - the humidity is set at the cavern (identity, with one exception).**
The charge ends with the air cooled to ambient at storage pressure, so `w` is
the saturation humidity there unless an intercooler outlet is colder still,
which needs a cold tank well below ambient. The solver checks this instead of
assuming it: humidity -> ladder -> `T_c` -> charge -> humidity is repeated
until `w` is unchanged, and in every measured case it is unchanged on the first
pass.

Consequence: at fixed `R` the discharge side, the cold tank and the stored
humidity are all fixed. The only remaining freedom is how the charge train
spends the inventory, the **charge split**.

## 2. An exact energy identity

A closed first-law balance over the whole plant, with the air entering at
`(T0, p0)` and leaving as turbine exhaust:

```text
W_exp + Q_user = W_comp + Q_amb + (h0 - h_exh) - Q_ac - L_tank

W_comp   compression work                 Q_amb   ambient heat taken by E-303
W_exp    expansion work                   h0      air enthalpy at intake
Q_user   heat sold through E-302          h_exh   air enthalpy at exhaust
Q_ac     aftercooler rejection: air leaving the last intercooler cools to T0 in the cavern
L_tank   hot- and cold-tank standing losses
```

It closes to 0.002 J/kg-air on the reference plant. Dividing by `W_comp`:

```text
J = (W_exp + Q_user) / W_comp
  = 1 + (Q_amb + (h0 - h_exh) - Q_ac - L_tank) / W_comp
```

Two consequences:

- **The user temperatures are not in J.** They only decide feasibility (the
  E-302 effectiveness). At 30 bar with 3 + 3 stages, users at 80/45, 95/75 and
  110/90 °C all returned `J = 0.9525` from the original solver, because E-302
  did not bind in any of them.
- **J < 1 is not caused by the exhaust.** Under minimum-duty dispatch the
  turbine exhaust sits on the anti-icing floor below 0 °C, so `h0 - h_exh` is
  a gain. A delivery ratio below one comes from the aftercooler, when the last
  intercooler releases hot air, often together with an idle E-303 (all returns
  above ambient). Measured at each case's optimum with the capacity-matched
  split, in kJ/kg-air:

| case | J | Q_amb | h0 - h_exh | Q_ac (air leaving last cooler) | T_c |
|---|---:|---:|---:|---:|---:|
| 85.8 bar, 6+6, 80/45 | 1.074 | 45.1 | +38.6 | 42.8 (52.8 °C) | 39 °C |
| 30 bar, 6+6, 95/75 | 0.962 | 27.7 | +30.2 | 74.4 (86.1 °C) | 28 °C |
| 30 bar, 3+3, 80/45 | 0.953 | 2.7 | +30.2 | 53.8 (66.3 °C) | 43 °C |
| 150 bar, 3+3, 80/45 | 0.917 | 0.0 | +41.8 | 106.9 (105.5 °C) | 96 °C |

## 3. One family of objectives, and why J cannot choose the split

At fixed `R`, `Q_amb`, `h_exh` and `W_exp` are fixed. Write
`K(R) = Q_amb + (h0 - h_exh) - W_exp`. Then every product ratio of the form

```text
Psi_w = (W_exp + w * Q_user) / W_comp
```

becomes

```text
Psi_w = w + (W_exp + w * (K - Q_ac - L_tank)) / W_comp
```

and the three metrics the code reports are three weights:

| w | Psi_w | meaning of the weight |
|---|---|---|
| 0 | electrical RTE | heat is worth nothing |
| theta | useful-exergy efficiency | heat is worth its exergy |
| 1 | delivery ratio J | heat is worth as much as electricity |

`theta` is exact because the user stream is heated between two fixed
temperatures:

```text
theta = [e(T_supply) - e(T_return)] / [cp (T_supply - T_return)]
      = 1 - T0 ln(T_supply / T_return) / (T_supply - T_return)

80/45 °C: 0.141     95/75 °C: 0.195     110/90 °C: 0.228     (T0 = 15 °C)
```

Holding `Q_ac` and `L_tank` fixed,

```text
d Psi_w / d W_comp = -(Psi_w - w) / W_comp
```

so **extra compression work raises Psi_w exactly when Psi_w < w**. A resistance
heater has `Psi_1 = 1`. Any plant with `J < 1` can therefore raise `J` by
behaving more like a resistance heater, and a plant with `J > 1` is penalized
for it only by the factor `J - 1`, which is small. Under exergy (`w = theta`,
about 0.14-0.23, against `eta_ex` about 0.55-0.63) the same move is always
penalized.

Measured: the free split that maximizes `J` at 30 bar, 3+3 stages, switches the
first intercooler off completely:

| split | J | RTE | eta_ex | W_comp |
|---|---:|---:|---:|---:|
| capacity-matched | 0.9525 | 0.5556 | 0.6115 | 440.0 |
| maximizes J | 0.9825 | 0.5111 | 0.5774 | 478.3 |
| maximizes eta_ex | 0.9459 | 0.5572 | 0.6119 | 438.7 |

The J-optimal split buys 3 points of J with 4.5 points of RTE and 3.4 points of
exergy efficiency. **This is why the split is chosen by exergy, whatever
objective ranks the inventory.** Section 6 states what this leaves open.

## 4. Rules for the charge split

The branches are not alike:

- the **last** branch's air goes to the aftercooler, so its heat is either
  stored or thrown away (`Q_ac`);
- the **first** branch cools air compressed from ambient, the coldest outlet
  in the train, so its water returns coldest and dilutes the grade of the
  store;
- the **intermediate** branches all trade intercooling against grade the same
  way, and capacity matching already balances them.

Exergy-optimal splits at fixed `R`. "Two shares" optimizes only the first and
last branch multipliers `a` and `b` and rescales the capacity-matched middle;
"free" optimizes every branch:

| case | capacity-matched | two shares (a, b) | free |
|---|---:|---:|---:|
| 85.8 bar, 6+6, 80/45 | 0.6241 | 0.6243 (0.88, 0.99) | 0.6243 |
| 30 bar, 3+3, 80/45 | 0.6115 | 0.6119 (0.96, 0.93) | 0.6119 |
| 85.8 bar, 6+6, 110/90 | 0.6182 | 0.6303 (0.00, 1.33) | 0.6308 |
| 30 bar, 6+6, 95/75 | 0.6121 | 0.6247 (0.00, 1.39) | 0.6275 |
| 85.8 bar, 8+8, 95/75 | 0.6046 | 0.6154 (0.00, 1.41) | 0.6186 |

Read as rules (measurements, not theorems):

1. **Mild users (80/45):** capacity matching is already within 0.02 exergy
   points of optimal. The last branch gets slightly *less* water, not more.
2. **Hot users (95/75, 110/90):** the store's grade is what E-302 sells, so the
   first intercooler is switched off (`a -> 0`: the first stage's heat passes
   into the second compressor and comes out hotter), and the last branch gets
   33-41 % more water to recover what would reach the aftercooler.
3. **Beyond two shares the landscape is flat and non-convex.** The free
   optimum adds at most 0.3 points, by switching off alternate intercoolers.
   That is a different machine (fewer, hotter stages), not a better split of
   this one, so it is not pursued.

The implementation therefore optimizes the two shares. Each is a bounded
one-dimensional maximization (Brent), alternated to convergence, and only the
charge train is re-solved (about 2 ms a trial). The coolant ceiling is a hard
constraint. The starved end of each share is always evaluated explicitly,
because the optimum is often exactly there.

**Electricity-first dispatch (LTA, and LTAHP with `max_electric_efficiency`)
is different and is left unchanged.** There is no user, all heat goes back to
the turbines, and the cold tank depends on the hot store, so none of Facts 1-2
holds. Measured at 30 bar, 3+3 stages (LTA), the free RTE-optimal split beats
the existing allocation by 0.0001 RTE. The existing capacity-matched split,
with its coolant-ceiling relief, is kept.

## 5. The search

```text
scan R on a geometric grid, reference/4 .. reference*4, neighbours 25 % apart
    (if nothing closes: the whole domain 0.1 .. 30, 10 % apart)
    each point: feasible with its objective, or refused by a NAMED constraint
bisect every gap between two points refused by DIFFERENT constraints, to 0.2 %
climb to the best cell with the exergy-optimal split
bisect any adjacent constraint boundary to 0.02 % in R
if the objective still rises into that boundary: the boundary is the optimum
otherwise: Brent on the bracket
```

The gap bisection is what the named refusals buy. A feasible window can only
open where one constraint gives way before the next takes over, so two
neighbours refused for different reasons are exactly where to look, and two
neighbours refused for the same reason are not. The case that motivated it: with
a 0 °C coolant minimum the reference plant is refused by the freezing limit up
to `R = 2.3` and by E-304's area from `R = 2.53`. It closes only in between, around
`R = 2.45`, and a plain 10 % grid steps straight over that window.

The scan doubles as the diagnosis. When nothing closes, the error lists which
constraint refused which part of the inventory axis. For example, at 250 bar
with 3+3 stages, the original solver ran 440 s and returned "nonexistence is not
certified". The scan instead reports that the inventory is too small below
`R = 0.67`, that the coolant ceiling binds from 0.74 to 3.0, and that E-304's
finite area binds above 3.0. The two constraints cross, so no inventory
satisfies both.

With a hot user or an active coolant ceiling, the optimum normally lies on a
constraint boundary where the objective is still rising. The original
inventory refinement (five halvings toward a neighbour) stopped a grid cell
short of it. That is why the new solver finds larger objectives there even
before the split is optimized.

## 6. What is and is not claimed

- Facts 1-3 and the identity of Section 2 are properties of this model,
  checked numerically; they are not approximations.
- `J(R)` has been smooth and single-peaked on its feasible interval in every
  case examined. That is an observation, not a proof. Brent finds a local
  maximum.
- Between two points refused by different constraints, the scan resolves a
  feasible window down to 0.2 % of `R`. A window between two points refused
  by the same constraint (a constraint that relaxes and then binds again
  inside one grid cell) could still be missed; the error message says how many
  points were sampled.
- The split is optimal within the two-share family, not over all splits.
- **The split can lower J.** Choosing the split by exergy is a real trade,
  not a free gain: at 250 bar, 6+6, 80/45 the solved plant has J 1.0326
  against 1.0359 before, with RTE 0.5354 against 0.5333 and exergy 0.6054
  against 0.6041. For hot users all three rise or hold
  ([benchmarks](10_BENCHMARKS_AND_REGRESSION.md)).
- **Open question for the objective itself.** `J` still ranks the inventory,
  as the project's objective policy requires. Section 3 shows that `J` rewards
  electric heating when `J < 1`. Along `R` the effect was measured to be
  small: at 150 bar, 3+3 stages, the J-optimal inventory costs 0.0005 exergy
  points against the previous design. It is not zero in principle. Ranking by
  `eta_ex`, or by a `Psi_w` whose weight is the heat-to-electricity price
  ratio of the actual user, would remove it. That is a project decision, not a
  numerical one.
