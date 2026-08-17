# Equal-drop cascade mass root

> The filename is retained for stable links. The old multi-level `theta`
> algorithm is not active.  
> **Parent:** [Algorithm index](README.md)  
> **Code:** `CAESPlant._solve_ladder` in `caes/plant.py`

The active architecture has one mixed hot store. For K groups,

```text
T_supply,g(delta_T) = T_hot - (g + 1) delta_T.
```

At each trial `delta_T`, the inverse finite-NTU interheater model computes every
stage bleed. The scalar physical residual is

```text
sum(stage_bleed_i) - R_store.
```

One and many groups now use the same conserved-mass root; the E-303 branch
selection removed the guessed mixed return that previously supplied a special
K=1 first-law shortcut. The upper drop ends at the heat-user return
temperature. Actual heat-user feasibility is not an approach check: after the
ladder is built, every station must satisfy

```text
epsilon_required = Q / [Cmin (T_hot,in - T_user,in)]
epsilon_required <= epsilon_counterflow(NTU_user, Cmin/Cmax).
```

The solver reuses the previous normalized drop, tries a smooth secant
continuation, and retains a safeguarded full bracket near feasibility
boundaries. Refinement uses inverse coolant mass, which is closer to affine in
temperature driving force than raw required mass. Final materialization must
close the coolant inventory within the one-joule energy budget.
