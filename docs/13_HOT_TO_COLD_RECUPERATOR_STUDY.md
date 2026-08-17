# Hot-to-cold recuperator: study closed, delivered as E-304

> **Status:** IMPLEMENTED. This document is kept as the record of what was asked
> of the idea before it was allowed in.  
> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Implementation:** [Single-store extraction architecture](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)  
> **Results:** [Measured against the frozen cascade](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md#5-measured-against-the-frozen-cascade)

## What was proposed

If the external user accepts heat only above a threshold, some lower-grade
hot-side duty has no useful buyer. An extra exchanger would move that otherwise
unusable heat into the final cold-return stream, after the optimized cold group
has mixed, after E-303 has warmed it, after it has remixed with the bypass
returns, and before the cold tank.

## What was delivered instead

The same recuperation, but fused with the interheater feed rather than bolted on
after it. E-304 is one counter-current body that simultaneously

- cools the trunk to the temperature each expansion stage actually demands, and
- absorbs that descent into the coolant return.

Fusing the two is what made the idea worth having. A recuperator alone only
moves low-grade heat around and warms the cold tank for nothing. The same body
with staged extractions also stops feeding the tail stages water they cannot
use, and on the reference plant that second effect is the larger one.

## The conditions this document set, and how they were met

| Condition demanded in the study | How it is met |
|---|---|
| a user minimum useful-temperature or demand curve | the user's configured supply/return pair, enforced through E-302's finite-NTU check |
| its own finite NTU | `extraction_exchanger_ntu`, applied per zone because the trunk's capacity rate steps down at every extraction |
| a pinch-safe hot-source selection rule | both terminals of every zone are checked; the ladder is the suffix maximum of the stage demands, so it can never invert |
| solved simultaneously, not added as a post-processing credit | the margin root sits inside the coolant-loop closure, and the loop closes on the RECUPERATED cold-tank inlet |
| proof that it does not cost more than it buys | measured against the frozen cascade at `22b7bb7`; see the results table |
| pump/fan parasitics and equipment cost | still absent, for E-304 exactly as for every other body in this model |

## The three topologies the study asked to compare

The study asked for no recuperator, recuperator before E-303, and recuperator
after E-303 and the final mixing. The delivered plant is the third, which the
study already named as the preferred baseline: it avoids warming a stream that
E-303 could have heated for free.

The first is still reachable and still measured - it is the frozen cascade at
`22b7bb7`, and it is what the results table compares against. The second was not
built: putting E-304 upstream of E-303 would hand E-303 a warmer stream and
strictly reduce the free ambient harvest, which the measured +33% harvest shows
is the term actually paying for the change.

## What remains open

- pump work and pressure drop through a multi-nozzle body, which is where the
  hardware complexity of many side draw-offs would show up;
- flow maldistribution across the extraction headers, to which real multi-stream
  plate-fin exchangers are notoriously sensitive;
- capital cost of one large multi-stream body against the `K` separate
  exchangers it replaced;
- whether a per-stage margin, rather than one common margin, buys enough to be
  worth the extra search dimension.
