# Coupled optimization workflow

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Children:** [Algorithm index](algorithms/README.md) · [Performance registry](09_PERFORMANCE_AND_OPTIMIZATION.md)  
> **Architecture:** [Single-store extraction architecture](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)

The LTA/LTAHP solver compares candidate plants on a one-kilogram-air basis. It
does not time-step one fixed exchanger: constant NTU denotes a performance
class and each candidate implicitly resizes `UA = NTU C_min`.

## Whole-plant map

```mermaid
flowchart LR
    A[Candidate conserved coolant flow] --> B[Trial cold-tank temperature]
    B --> D[Charge train and parallel coolant allocation]
    D --> E[One mixed hot TES plus standing loss]
    E --> F{Heat dispatched?}
    F -->|no| G[Direct hot-store interheater allocation]
    F -->|yes| H[E-302 on the full trunk, then E-304 staged bleeds]
    G --> I[Moisture-safe turbine train]
    H --> I
    I --> J[Mixed interheater return]
    J --> R[E-303, final mix, then E-304 recuperation]
    R --> K{Closure residual zero?}
    K -->|no| B
    K -->|yes| L[Energy, exergy and feasibility books]
    L --> M[Rank inventory by selected objective]
```

## Charge block

Air stages are sequential; coolant branches are parallel. For each stage, the
solver obtains the real secant air heat capacity from the solved enthalpy and
temperature change, matches coolant heat-capacity rate, projects all branch
flows onto the candidate inventory, and iterates the split to tolerance.

Every branch starts at the same cold-tank temperature. Its actual return is
checked against the direct coolant maximum. All returns then enthalpy-mix into
one hot stored state; the discharge network never changes this block.

## Heat-user discharge block

Stage pressure schedule, expander efficiency and protected humidity fix each
stage's minimum moisture-safe duty AND the air temperature its interheater must
produce, before any of the coolant network is solved. That demand profile is
raised to its non-increasing suffix maximum, because a progressively withdrawn
trunk can only get colder along its length.

```mermaid
flowchart TD
    H0[One mixed hot TES] --> H1[E-302: whole trunk, sells the top band]
    H1 --> EX[E-304: trunk enters at the first extraction]
    EX --> B0[Bleed 1 at T_demand,1 + m]
    EX --> B1[Bleed 2 at T_demand,2 + m]
    EX --> BF[Bleed N; trunk exhausted]
    B0 --> IH[Finite-NTU interheaters]
    B1 --> IH
    BF --> IH
    IH --> CR[Returns: E-303 on the COLDEST group, then final mix]
    CR --> RE[E-304 cold side: recuperation into the return]
    RE --> CT[Cold TES]
```

One safeguarded, continued scalar root chooses the common margin `m` so all
inverse-HX bleeds sum to the conserved inventory. Because the first extraction
is the trunk inlet, that same root also fixes what E-302 gets - there is no
separate split to search. The outer root then reproduces the physical cold-tank
state after E-303, final mixing, E-304 recuperation and dwell.

The user's coolant is one counter-current stream through one exchanger. Its mass
flow is derived from the duty and the configured supply/return temperatures, and
it must fit the configured counterflow NTU effectiveness. E-304 is held to the
same discipline zone by zone, since its trunk capacity rate steps down at every
extraction.

## Objective dispatch

`max_electric_efficiency` bypasses both E-302 and E-304 and searches the same
electrical endpoint as LTA: without a heat user there is no reason to stage the
trunk, because the only sink for the descent would be the plant's own cold
return. `max_combined_energy_delivery` activates both bodies, gives the turbines
their moisture-safe duty at matched supply temperatures and exports the band
above the first extraction. The two reported energy ratios are

```text
eta_electric = W_exp / W_comp
R_delivery = (W_exp + Q_user) / W_comp.
```

`R_delivery` can exceed one because ambient heat is not purchased electricity;
the bounded thermodynamic metric is total useful exergy efficiency.

## Numerical safeguards

- All inverse HXs refine against the same forward finite-NTU law.
- The cold-loop coordinate is the cold-tank temperature because the branch
  distribution, not its untreated mean, determines E-303 placement.
- Previous cold-loop and extraction-margin roots are continuation seeds, but
  every seed is re-evaluated and bracketed.
- The discharge network closes mass internally before cold-tank closure.
- A pinched or undersized E-304 zone rejects the candidate rather than being
  relaxed; less inventory needs a wider margin, which lifts the whole ladder
  away from the return, so the inventory search walks out of a pinched region.
- Charge and discharge coolant totals close within a one-joule energy budget.
- Direct coolant minimum/maximum, moisture, icing and finite-NTU user constraints
  are checked on the materialized train.
- Every component retains its steady-flow first-law residual, and total exergy
  residual must remain below 1 J/kg-air.

Work counts and currently accepted accelerations are canonical in
[Performance and optimization](09_PERFORMANCE_AND_OPTIMIZATION.md); equations
for individual roots are in the [algorithm index](algorithms/README.md).
