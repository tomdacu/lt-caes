# Extraction-margin mass root

> The filename is retained for stable links. Neither the multi-level `theta`
> algorithm nor the equal-drop cascade root it replaced is active.  
> **Parent:** [Algorithm index](README.md)  
> **Architecture:** [Single-store extraction architecture](../12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)  
> **Code:** `CAESPlant._solve_extraction_margin` in `caes/plant.py`

## The unknown

One mixed hot store, one heat-user exchanger, and one extraction body carrying
one bleed per expansion stage. Each bleed sits a single common margin above the
air temperature that stage's interheater must produce:

```text
T_supply,g(m) = T_demand,g + m
```

`T_demand,g` is invariant: it depends on the pressure train, the expander
efficiency and the protected humidity, never on either tank. It is taken as the
**non-increasing suffix maximum** of the raw per-stage demands, because a
progressively withdrawn trunk cannot serve a later stage hotter than an earlier
one.

At each trial `m` the inverse finite-NTU interheater model computes every stage
bleed. The scalar physical residual is

```text
f(m) = sum_g b_g( T_demand,g + m )  -  R_total
```

## Why one root closes the whole discharge network

The first extraction IS the trunk inlet - E-302 has already taken everything
above it - so `m` fixes the user duty as well:

```text
T_trunk,in = T_demand,0 + m
Q_user     = R_total cp ( T_hot - T_trunk,in )
```

There is therefore no second unknown for the sold-versus-recuperated split, and
the outer search keeps exactly one variable, the conserved inventory. The user
exchanger's finite-NTU check becomes an admissibility filter on `(R_total, m)`.

## Monotonicity and bracketing

A hotter supply gives a larger driving force, so a stage needs LESS flow for the
same duty. `f` is therefore monotone decreasing in `m`:

```text
m -> 0+      required flow -> unbounded      f > 0   (over-inventory side)
m -> m_max   required flow at its smallest   f < 0
m_max = T_hot,available - max_g T_demand,g
```

`m_max` is the store itself: the trunk inlet can never be hotter than the
coolant available to it. A non-positive `m_max` is reported directly as the
store being unable to feed the first expansion stage.

The bracket is `[0, m_max]`, with the small-margin end always the
over-inventory side. Interior infeasibility - a stage the finite exchanger
cannot serve at all - is bisected toward the wide side until a finite
over-inventory point is recovered.

## Numerical method

1. **Warm start.** The previous accepted root is stored as a FRACTION of the
   current `m_max`, so it survives the outer searches moving both the inventory
   and the hot-store temperature. If it already satisfies the mass tolerance it
   is returned immediately.
2. **Secant continuation on the reciprocal residual.** Required flow is close to
   inversely proportional to the driving force, so a secant on
   `1/required - 1/R_total` is far better conditioned than on the raw mass
   residual and normally converges in two to four new discharge trains.
3. **Safeguarded false position.** The global bracket remains the proof path
   near feasibility boundaries, with the same reciprocal transform and Illinois
   halving so neither endpoint sticks.
4. **Seed-free fallback (heat-user solver).** A seed left by a distant
   inventory can stop steps 1-3 short of the mass tolerance. The heat-user
   solver then clears it and uses the seed-free bracketed root
   (`_solve_extraction_margin_recovery`), so a candidate's feasibility never
   depends on which candidate was solved before it. There the provisional hot
   end is the coolant ceiling, because the store does not enter the mass
   equation.

The tolerance is not an ad-hoc number: it is derived from the one-joule energy
budget in `WATER_MASS_CLOSURE_SEARCH_ERROR`, because a mass residual reappears
as spurious heat when the tank terms are booked against `R_total` and the
interheater duties against the real branch flows.

## Performance

Measured on `heat_and_power_example_config.json`, against the frozen equal-drop
cascade at commit `22b7bb7`, same machine:

| | equal-drop cascade | extraction margin |
|---|---:|---:|
| light discharge trains | 1586 | **534** |
| `water_ratio_for_duty` calls | 8656 | **3184** |
| root calls | 121 | **83** |

The margin is a much better conditioned coordinate than the common drop was:
every stage sits a known distance above a known demand, so the inverse exchanger
solves start close to their answers instead of being dragged along one shared
temperature.

## Failure modes

- **store below the hottest demand** - no margin exists; reported as such rather
  than as a generic infeasibility;
- **inventory larger than the extractions can ever consume** - `f < 0` even at
  zero margin; there is more coolant than the interheaters can take;
- **interior HX infeasibility** - a stage whose duty the finite exchanger cannot
  reach at that supply; bisected around rather than relaxed.

## Guarded by

`tests/test_extraction_exchanger.py`: one extraction per stage, bleeds summing
to the inventory, a non-increasing ladder that never starves a stage, and one
common margin measured against what each interheater actually achieved.
