# Heat-only cold-return ambient recovery

> **Parent:** [Algorithm index](README.md)  
> **Architecture:** [Single-store extraction architecture](../12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)  
> **Code:** `CAESPlant._optimize_cold_return_recovery`

## Topology being optimized

There is exactly one E-303. For a candidate group, its members mix first, pass
through E-303, and then join the bypass returns before the cold tank.

The candidates are the returns SORTED BY TEMPERATURE, coldest first, giving N
thresholds plus the bypass state. That is the complete search, not a heuristic
slice of the `2**N` subsets: any optimal group is downward closed in
temperature, because swapping a warmer member for a colder non-member always
lowers the mixed inlet and so raises the duty.

Ordering by temperature rather than by stage index is what changed with E-304.
The former serial cascade fed every interheater from one trunk temperature,
which happened to make the returns monotone in stage order and let an
ordered-suffix search be optimal by accident. E-304 gives each stage its own
supply, the returns are no longer sorted by stage, and a stage-ordered suffix
would quietly stop being the optimum.

E-303 is heat-only. A selected mixture at or above ambient bypasses it; the
model never reverses E-303 into a rejection cooler.

## Closed-form candidate score

For group mass ratio `R_s` and its mass-weighted inlet temperature `T_s`, the
ambient side is treated as an infinite capacity rate. With the configured
constant-NTU exchanger class,

```text
T_E303,out = T0 + (T_s - T0) exp(-NTU_303),  when T_s < T0
Q_ambient,s = R_s cp (T0 - T_s) [1 - exp(-NTU_303)].
```

After E-303, the selected outlet mixes with the bypass returns. Since total
mass and `cp` are fixed, maximizing `Q_ambient,s` is exactly equivalent to
maximizing the final cold-tank inlet temperature for that discharge solution.
The solver sorts once and evaluates the N thresholds in O(N log N); it needs no
nested root and no `2**N` subset search.

E-303's outlet mix is NOT the cold-tank inlet when a heat user is dispatched:
the mixture then crosses E-304's cold side and reaches the tank warmer. The
coolant loop closes on that recuperated temperature.

Constant NTU means an exchanger performance class, not one fixed-area body
shared by all candidates. For every plant and selected subgroup the implied
design area satisfies `UA = NTU C_selected`. Equipment area, cost, fan power
and off-design maps remain outside this screening model.

## Coolant-loop closure

Branch-selective recovery cannot be reconstructed from the untreated all-return
mean. The cold-tank temperature is therefore the closure coordinate:

```text
trial T_cold
 -> charge and mixed hot store
 -> discharge branch returns
 -> coldest-group selection and E-303
 -> final mixing
 -> E-304 recuperation (heat user only)
 -> cold-tank standing map
 -> produced T_cold.
```

The root residual is `produced T_cold - trial T_cold`. The accepted full cycle
rechecks that residual after materializing the detailed exchanger train.

## What the objective proves—and what it does not

The selected group is globally optimal for ambient heat pickup at a fixed
discharge solution, and the temperature ordering makes that a complete claim
over all subsets rather than one restricted to a particular manifold order. It is not yet a whole-plant
mixed-integer optimum over arbitrary piping, fixed exchanger area, pump/fan
parasitics, capital cost or annual weather. Those belong to later design layers.
