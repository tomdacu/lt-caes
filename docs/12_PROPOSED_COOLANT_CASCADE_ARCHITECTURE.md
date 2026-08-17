# Single-store coolant cascade architecture

> **Status:** implemented hot-side cascade and optimized heat-only cold-return routing.  
> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Implementation:** [Single-store cascade and solver](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md)  
> **Algorithms:** [Algorithm index](algorithms/README.md)

## 1. Exact meaning of K

`coolant_cascade_groups = K` is the number of non-empty, contiguous groups of
expansion stages. It is also exactly the number of serial heat-user
exchangers. It is **not** a number of tanks, stored temperature levels, extra
exchangers, or bleed points in addition to a base exchanger.

The allowed range is

```text
1 <= K <= number of expansion stages.
```

The compressor count does not bound K. Charge-side intercooler returns mix
before storage, so every K uses one mixed hot tank and one mixed cold tank.

## 2. Implemented flow sequence

For K groups, the plant-side flow is

```text
one mixed hot TES
  -> user HX 0 -> bleed to interheater group 0
  -> user HX 1 -> bleed to interheater group 1
  -> ...
  -> user HX K-1 -> final bleed to interheater group K-1.
```

All coolant crosses the first exchanger. Only the flow not taken by group 0
crosses the second; only the flow not taken by groups 0 and 1 crosses the
third. After the final bleed no plant coolant remains, so there is no terminal
zero-flow exchanger. This is why the correct count is K, not K+1.

Let `b_g` be the coolant flow bled to group g and `R_g` the trunk flow through
user exchanger g. Mass conservation is

```text
R_g = sum(b_h for h = g..K-1)
R_0 = R_total
R_(g+1) = R_g - b_g
sum(b_g) = R_total.
```

The plant-side duty of station g is

```text
Q_user,g = R_g cp,coolant (T_g,in - T_g,out).
```

The implemented screening rule gives every station the same plant-side
temperature drop `delta_T`:

```text
T_g,out = T_hot - (g + 1) delta_T.
```

`delta_T` is not a user input. The solver chooses it so the inverse finite-NTU
interheater calculations consume exactly the conserved coolant inventory. Since
`R_g` decreases strictly, equal `delta_T` makes the first exchanger deliver the
largest heat duty and every later duty smaller. This is the intended physical
consequence of the corrected topology, not a manually imposed duty split.

The external-user side is one counter-current stream through all K exchangers.
Its configured return enters the coldest station; its configured supply leaves
the hottest. The same user flow therefore appears in every result tap and must
never be summed K times.

## 3. Stage grouping

Expansion stages stay in process order and are partitioned into K contiguous
groups. Cuts balance the groups' minimum moisture-safe reheat duties. Contiguous
grouping avoids crossed piping and preserves the thermodynamic order: the
highest-duty front of the turbine train is served by the first, hottest bleed.

Examples for N expansion stages:

- K=1: one exchanger, then one bleed manifold feeding all N interheaters;
- K=N/2: K exchangers; each group normally serves about two adjacent stages;
- K=N: one exchanger and one bleed per stage.

## 4. Storage placement and temporal coupling

The implemented default stores heat only before the user cascade:

```text
charge intercoolers -> hot TES -> user cascade -> interheaters
                    -> selected-return E-303 -> final mixing -> cold TES.
```

This decouples charge from discharge, but useful-heat delivery remains coupled
to electrical discharge. Fully decoupling the external user from turbine
operation would require storage after the user cascade. Because those branch
states have different temperatures, preserving their grade would require
multiple tanks or a genuinely stratified store. That additional hardware is
not silently represented by K.

## 5. Cold returns and ambient heat

Interheater returns can be below ambient because the expansion train operates
near its moisture/icing boundary. A coolant/ambient exchanger then moves a
return toward ambient and can absorb heat into the loop. This is heat-pump-like
energy recovery: compression work later upgrades that low-temperature energy;
ambient heat carries no exergy at the selected dead state.

The backend installs one heat-only E-303. It evaluates every ordered suffix of
the interheater returns. For a candidate cutoff, that suffix mixes first, is
warmed toward ambient, and then mixes with the warmer bypass returns. E-303 is
never allowed to cool a hot return.

For selected suffix flow `R_s` and mixed temperature `T_s < T0`,

```text
T_out = T0 + (T_s - T0) exp(-NTU_303)
Q_ambient = R_s cp (T0 - T_s) [1 - exp(-NTU_303)].
```

Maximizing this duty also maximizes the final mixed cold-tank inlet for the
fixed discharge solution. Testing N suffixes is complete for this topology and
costs O(N), not 2^N. The selected stages, pre/post E-303 temperatures, flow and
ambient duty are stored in `TwoTankSummary`; the solved P&ID draws the two
manifolds and actual cutoff. See [the algorithm](algorithms/cold_return_recovery.md).

## 6. Objectives and bypass

`max_combined_energy_delivery` activates the topology above: turbines receive
their minimum moisture-safe reheat first, and the user receives the feasible
upstream temperature drop. `max_electric_efficiency` bypasses the user
cascade. With heat-only E-303 this dispatch is feasible only when the turbine
train consumes enough stored heat to close the coolant loop without a rejection
sink; the default six-stage point does not. The solver rejects it rather than
inventing a cooler. A future Pareto control may minimize necessary heat export
instead of using the two endpoint dispatches.

## 7. Evidence and required invariants

Automated tests assert that:

- K always leaves exactly one hot stored state;
- there are exactly K user exchangers;
- the first exchanger sees the complete inventory;
- trunk flow and exchanger duty decrease after each bleed;
- consecutive exchanger temperatures are continuous;
- all group bleeds sum to the stored coolant flow;
- the external-user stream is single and counter-current;
- every user station's required effectiveness is within its finite-NTU class;
- E-303 selects the maximum-duty legal suffix and never rejects heat;
- first law and exergy balance close.

The thermodynamic opportunity is consistent with staged low-temperature CAES
and cold-recovery literature, while the exact branch topology remains this
project's design hypothesis:

- Wolf and Budt, *LTA-CAES – A low-temperature approach to Adiabatic Compressed
  Air Energy Storage*, Applied Energy 125 (2014),
  [DOI](https://doi.org/10.1016/j.apenergy.2014.03.013);
- Liu et al., *Characteristics of air cooling for cold storage and power
  recovery of CAES with inter-cooling*, Applied Thermal Engineering 107 (2016),
  [DOI](https://doi.org/10.1016/j.applthermaleng.2016.06.168);
- *Subcooled compressed air energy storage system for coproduction of heat,
  cooling and electricity*, Applied Energy 205 (2017),
  [DOI](https://doi.org/10.1016/j.apenergy.2017.08.006).
