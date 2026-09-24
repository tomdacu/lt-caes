# Performance limits: electrical efficiency, delivery ratio and the time-shifted heat pump

> **Parent:** [Theory and design objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md)  
> **Related:** [Metrics and exergy](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) · [Heat-user reduction](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md) · [How the solver works](15_HOW_THE_SOLVER_WORKS.md)

How good can a combustion-free CAES plant be? This document answers that at
three levels:

1. **universal bounds** from the first and second laws, valid for any plant
   that stores electricity and returns electricity and heat;
2. **what this plant architecture reaches with ideal components**, computed
   with the model;
3. **what realistic parameters give**, and which parameters matter.

Every relation marked *identity* has been checked on 31 solved designs to
the printed digits.

## 1. Metrics

All quantities are per kilogram of stored air. `W_c` is compression work, `W_e`
expansion work, `Q` heat delivered to the user, and `T0` the ambient (dead-state)
temperature.

```text
RTE    = W_e / W_c                          electrical round-trip efficiency
J      = (W_e + Q) / W_c                    useful-energy delivery ratio
eta_ex = (W_e + theta Q) / W_c              useful-exergy efficiency
```

The user stream is heated from its return temperature `T_r` to its supply
temperature `T_s`. The exergy it receives per joule of heat is the Carnot
factor at its **thermodynamic mean temperature** `T_u`:

```text
T_u   = (T_s - T_r) / ln(T_s / T_r)
theta = 1 - T0 / T_u
```

| user `T_s/T_r` | `T_u` | `theta` | `1/theta` (Carnot heat-pump COP) |
|---|---:|---:|---:|
| 60 / 30 °C | 44.8 °C | 0.094 | 10.7 |
| 80 / 45 °C | 62.2 °C | 0.141 | 7.1 |
| 95 / 75 °C | 84.9 °C | 0.195 | 5.1 |
| 110 / 90 °C | 99.9 °C | 0.228 | 4.4 |

(`T0` = 15 °C.)

### The plant as a time-shifted heat pump

A plant that returns less electricity than it took and delivers heat as well
can be read as a heat pump whose delivery is shifted in time: the electricity
it does *not* give back has bought the heat. Its net coefficient of
performance is

```text
COP_net = Q / (W_c - W_e)
```

It answers a question a planner actually asks: compared with running an
electric heat pump from the same grid, how much heat did each unit of
electricity *not returned* buy?

## 2. Two exact identities

**Identity 1, the first law over the whole plant.** With `Q_amb` the heat the
plant takes from the atmosphere through its coolant, `h_in - h_ex` the
enthalpy by which the exhaust leaves colder than the intake, `Q_ac` the heat
lost when the compressed air cools to ambient in storage, and `L` the tank
standing losses,

```text
W_e + Q = W_c + Q_amb + (h_in - h_ex) - Q_ac - L

J = 1 + (Q_amb + (h_in - h_ex) - Q_ac - L) / W_c
```

The delivery ratio exceeds one only by the free ambient energy the plant
pumps in, minus its heat losses. Derivation and checks:
[document 14, section 2](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md#2-an-exact-energy-identity).

**Identity 2, the three metrics are not independent.** Write `q = Q / W_c`.
Then `J = RTE + q` and `eta_ex = RTE + theta q`. Eliminating `q`:

```text
J       = RTE + (eta_ex - RTE) / theta
COP_net = (J - RTE) / (1 - RTE) = (eta_ex - RTE) / (theta (1 - RTE))
```

The exergy the plant delivers *as heat*, `eta_ex - RTE`, is amplified by
`1/theta` into the delivery ratio. That is why a low-temperature user makes `J`
look large: every point of heat exergy is worth 7 to 11 points of `J` for
users whose mean temperature is 45-62 °C.

## 3. Universal bounds (second law)

For any real plant `eta_ex <= 1`, with equality only if the plant is
reversible. Identity 2 then gives, with no assumption about the architecture:

```text
RTE     <= 1
J       <= RTE + (1 - RTE) / theta      <= 1 / theta
COP_net <= 1 / theta = T_u / (T_u - T0)          (Carnot heat pump)
```

- **Electricity only.** A reversible store returns everything: `RTE = 1`.
- **Heat and electricity.** At a given `RTE`, the delivery ratio is bounded by
  the heat a Carnot heat pump would make from the electricity not returned.
  The absolute bound, `J = 1/theta`, is reached by returning no electricity at
  all: the plant would then be a reversible heat pump, 7.1 for an 80/45 °C
  user.
- **The net COP** can never beat a Carnot heat pump working between ambient and
  the user's mean temperature.

These bounds are loose for CAES on purpose: they say what physics forbids,
not what this machine can do.

## 4. What this architecture reaches with ideal components

Ideal here means isentropic machines, no pressure drops, exchangers of NTU 200
(E-303 and the user exchanger 50), no tank losses. Everything else is the
reference plant: 85.8 bar, 80/45 °C user, 15 °C ambient.

| case | RTE | J | eta_ex | COP_net | COP_net / Carnot | `Q_amb` | `h_in - h_ex` | `Q_ac` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| electricity only, 6+6 stages | 0.987 | - | 0.987 | - | - | 0.1 | 3.5 | 9.0 |
| heat user, 6+6 stages | 0.876 | 1.229 | 0.925 | 2.84 | 0.40 | 83.5 | 38.6 | 23.0 |
| heat user, 12+12 stages | 0.850 | 1.353 | 0.921 | 3.36 | 0.47 | 129.5 | 38.6 | 18.5 |
| reference, real components | 0.551 | 1.075 | 0.625 | 1.17 | 0.16 | 44.4 | 38.6 | 42.2 |

(energy terms in kJ/kg-air)

**Electricity only: the reversible limit is reachable in principle.** With
identical stages, balanced counter-current exchangers and ideal machines, each
intercooler stores exactly the heat its interheater returns, and the cycle
tends to reversibility. The model reaches `RTE = 0.987`; the remaining 1.3 %
is finite exchanger area, real-gas mismatch between charge and discharge
heat capacities, and the heat left in the air after the last intercooler.

**With a heat user the architecture itself costs exergy, even when every
component is perfect.** The ideal 6+6 plant still destroys 30 kJ/kg-air
(`eta_ex = 0.925`), for three structural reasons:

- the turbines receive only their *minimum* anti-icing duty, so the exhaust
  leaves at the icing floor (-23 °C here), well below ambient. That is where
  the heat-pump effect comes from, but the cold exhaust also carries exergy
  out unused;
- the heat is sold across a finite temperature difference between the store
  and the user stream, and staged down to each turbine through a finite
  temperature ladder;
- the air leaving the last intercooler is still warmer than ambient
  (`Q_ac`).

**The heat-pump effect is a by-product, not a designed cycle.** Ambient heat
enters only where the process air is below ambient during expansion: through
the coolant returns (`Q_amb`) and through the cold exhaust (`h_in - h_ex`).
More expansion stages mean more stages that start below ambient, so more
ambient heat. That is why 12 stages reach `J = 1.35` against 1.23 for 6. But
the net COP stays at 40-47 % of Carnot even with ideal components, and at
16 % for the reference plant; dedicated heat pumps typically reach 40-60 %.

## 5. Realistic designs and the parameters that matter

The measured one-at-a-time sensitivity is tabulated in
[document 11](11_THEORY_AND_DESIGN_OBJECTIVES.md#measured-sensitivity-of-the-delivery-ratio-j-ltahp).
In summary, from the reference plant (`J = 1.075`):

| parameter | effect on J | mechanism (via identity 1) |
|---|---|---|
| number of stages | 3: 0.943, 8: 1.154, 10: 1.172 (strongest) | colder coolant returns: ambient harvest 0 to 90 kJ/kg; smaller `Q_ac` |
| exchanger NTU | 3: 1.010, 30: 1.171, 100: 1.187 | same mechanism, diminishing beyond ~30 |
| ambient temperature | 0 °C: 1.031, 30 °C: 1.153 | more free heat available |
| storage pressure (lower is better) | 30 bar: 1.097, 300 bar: 1.025 | `Q_ac` grows faster than the harvest |
| ambient-recovery exchanger NTU | saturates at about 5 | |
| coolant minimum temperature | 0 °C instead of -80 °C: 1.057 | caps how cold the returns may run |
| machine efficiency 0.80 to 0.95 | 1.073-1.075 (no effect) | irreversibility becomes heat, counted at par |
| pressure drops 0 to 5 % | 1.074-1.076 (no effect) | same |

The best realistic combination found (200 bar, 10+10 stages, NTU 30,
ambient-recovery NTU 20, machine efficiency 0.90, 1 % pressure drops, 60/30 °C
user) gives **J = 1.215**, RTE 0.655, eta_ex 0.707, COP_net 1.62; another
(200 bar, 8+8, NTU 100, antifreeze to -30 °C) gives J = 1.222. Setting `Q_ac`
and `L` to zero in identity 1 for the first combination bounds it at
`1 + (134.5 + 42.8)/579.9 = 1.31`.

## 6. How to report a design

- `J` alone cannot tell a good plant from one that wastes work into heat:
  machine efficiency moves RTE by 22 points and `J` by 0.2. Report it only
  together with `RTE` and `eta_ex`. Identity 2 makes any two of them determine
  the third, given `theta`.
- `COP_net` is the figure to compare with a heat pump. Unlike `J`, it does
  respond to machine quality (1.15 to 1.24 as the efficiency goes from 0.80 to
  0.95). Quote it against the Carnot value `1/theta` of the same user.
- For the electricity-only concept, `RTE` against the reversible bound of 1 is
  the whole story; the ideal-component model result (0.987) shows how much of
  the gap is architecture and how much is components.
