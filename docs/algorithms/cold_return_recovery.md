# Heat-only cold-return ambient recovery

> **Parent:** [Algorithm index](README.md)  
> **Architecture:** [Single-store cascade](../12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)  
> **Code:** `CAESPlant._optimize_cold_return_recovery`

## Topology being optimized

There is exactly one E-303. For a cutoff `s`, return branches `s..N-1` mix
first, pass through E-303, and then join the bypass branches `0..s-1` before
the cold tank. The candidate set is therefore the N ordered suffixes plus the
bypass state. Arbitrary subsets are excluded because they would require a
cross-connected selection manifold rather than the ordered return header being
screened.

E-303 is heat-only. A selected mixture at or above ambient bypasses it; the
model never reverses E-303 into a rejection cooler.

## Closed-form candidate score

For suffix mass ratio `R_s` and its mass-weighted inlet temperature `T_s`, the
ambient side is treated as an infinite capacity rate. With the configured
constant-NTU exchanger class,

```text
T_E303,out = T0 + (T_s - T0) exp(-NTU_303),  when T_s < T0
Q_ambient,s = R_s cp (T0 - T_s) [1 - exp(-NTU_303)].
```

After E-303, the selected outlet mixes with the bypass returns. Since total
mass and `cp` are fixed, maximizing `Q_ambient,s` is exactly equivalent to
maximizing the final cold-tank inlet temperature for that discharge solution.
The solver evaluates all N suffixes in O(N); it does not need another root or
the 2^N search over arbitrary subsets.

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
 -> suffix optimization and E-303
 -> final mixing
 -> cold-tank standing map
 -> produced T_cold.
```

The root residual is `produced T_cold - trial T_cold`. The accepted full cycle
rechecks that residual after materializing the detailed exchanger train.

## What the objective proves—and what it does not

The selected cutoff is globally optimal inside the ordered-suffix topology for
ambient heat pickup at a fixed discharge solution. It is not yet a whole-plant
mixed-integer optimum over arbitrary piping, fixed exchanger area, pump/fan
parasitics, capital cost or annual weather. Those belong to later design layers.
