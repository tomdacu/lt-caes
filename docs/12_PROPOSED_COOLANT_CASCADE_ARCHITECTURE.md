# Single-store extraction architecture (E-302 + E-304)

> **Status:** implemented. Replaced the serial K-station heat-user cascade.  
> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Implementation:** [Single-store store and discharge solver](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md)  
> **Algorithms:** [Algorithm index](algorithms/README.md)  
> **Frozen predecessor:** commit `22b7bb7`, the serial cascade this document used to describe

The filename is retained so existing links keep working.

## 1. What replaced what

The discharge coolant network used to be `K` heat-user exchangers in series, each
followed by one interheater-group bleed. It is now:

```text
one mixed hot TES
  -> E-302, ONE heat-user exchanger crossed by the whole inventory
  -> E-304, ONE counter-current body with one extraction per expansion stage,
            fully consumed at the last extraction
```

`coolant_cascade_groups` was removed together with the serial cascade it
configured. Older configuration files still load: the key is ignored with a
deprecation warning, because there is no group count left for it to control.

## 2. Why the trunk is staged at all

Every expansion stage must reach its own air temperature before its turbine,
fixed by the anti-icing envelope and independent of both tanks. Those demands
fall steeply along the train. On the six-stage 85.8 bar reference plant:

```text
  stage          1      2      3      4      5      6
  demand [C]   65.95  61.24  50.89  41.20  32.13  23.63
```

Under one common supply temperature - which is what the cascade delivered, since
every stage was bled at the same post-user trunk temperature - the tail stages
are fed water they cannot use:

```text
  cascade supply 67.6 C to every stage
    stage 1:  1.65 K of margin   <- this stage alone sets the supply
    stage 6: 43.97 K of margin   <- 44 K of grade destroyed on arrival
```

E-304 gives each stage a supply a single common margin above its own demand and
recuperates the difference into the coolant return.

## 3. The one unknown: the extraction margin

Each extraction sits at

```text
  T_extraction,g = T_demand,g + m
```

and `m` is rooted so the extractions consume exactly the conserved inventory:

```text
  sum_g  b_g( T_demand,g + m )  =  R_total
```

A hotter supply needs less flow for the same duty, so the total demanded flow is
monotone decreasing in `m` and one safeguarded root closes exact coolant mass.
This is the same cost class as the cascade's equal-drop root: the expensive
object is the light discharge train, and this needs no more of them.

The first extraction is the trunk inlet, so `m` also fixes what E-302 gets:

```text
  T_trunk,in = T_demand,0 + m
  Q_user     = R_total cp ( T_hot - T_trunk,in )
```

There is therefore **no separate split to choose** between what is sold and what
is recuperated. The user takes everything above the first extraction; E-304
takes everything below it. The user exchanger's finite-NTU check becomes an
admissibility filter on `(R_total, m)` rather than a degree of freedom, and the
outer search still has exactly one variable, the conserved inventory.

## 4. The demand profile is not always monotone

A trunk that is progressively withdrawn only ever gets colder, so it cannot hand
a later stage a hotter supply than an earlier one. The raw demand profile does
not always cooperate. Measured on the 300 bar eight-stage train:

```text
  stage          1      2      3      4      5      6      7      8
  demand [C]   63.34  64.45  60.14  50.32  40.94  32.12  23.85  16.06
               ^^^^^  ^^^^^ stage 2 demands MORE than stage 1
```

because the first expansion starts from stored air at ambient temperature while
later ones start from a turbine outlet sitting on the icing floor.

The profile is therefore raised to its **suffix maximum**: each extraction is
placed at the hottest demand still ahead of it. Where that binds, the two stages
share one nozzle and the zone between them carries no duty. That is the honest
picture of what the hardware can do, not a rejection, and where the profile
already falls the envelope is the identity and changes nothing.

## 5. E-304 is solved zone by zone

The trunk loses mass at every extraction, so its heat-capacity rate is a step
function of position. A single whole-body LMTD or effectiveness is invalid, and
its error is not conservative in any predictable direction. The body is cut at
the extractions; inside one zone both capacity rates are constant, which is
exactly what the counter-current effectiveness relation needs.

For zone `g`, between extraction `g` and extraction `g+1`:

```text
  m_g   = sum( b_h  for h > g )                 trunk still to be withdrawn
  Q_g   = m_g cp ( T_g - T_(g+1) )
  Cr_g  = m_g / R_total                         cold side carries the whole inventory
  eps_required  = Q_g / [ m_g cp ( T_g - Tc_(g+1) ) ]
  eps_available = eps_counterflow( NTU_E304, Cr_g )
```

The cold side is the plant's own mixed coolant return, carrying the full
inventory through every zone, so the trunk is always `C_min` and `Cr <= 1`.

Total recuperation and the cold-tank inlet:

```text
  Q_recup  = sum_g Q_g
  T_cold,in = T_mixed_return + Q_recup / ( R_total cp )
```

Two things are checked and never assumed:

- **the pinch, at every node.** With a stepped trunk capacity rate the tightest
  approach migrates inside the body, so terminal-only checking would miss a
  crossed profile;
- **the finite area,** as the same required-versus-available effectiveness
  statement every other exchanger in this model is held to.

A zone that fails either check makes the candidate infeasible. That is
self-correcting rather than fatal: less inventory needs a wider margin, which
lifts the whole ladder away from the return it exchanges against, so the outer
inventory search walks out of a pinched region on its own.

## 6. Where the recuperated heat goes, and what it costs

E-304's cold side is the coolant return, so the duty is **internal**. It is not a
product, it is not an ambient input, and the coolant energy balance is unchanged:

```text
  Q_charge + Q_ambient = Q_user + Q_interheat
```

What it buys is grade. What it costs is a warmer cold tank, which captures less
compression heat and raises compressor work. Both effects are real and the net
is a measurement, not an argument - see
[the results](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md#5-measured-against-the-frozen-cascade).

## 7. Order on the return path

```text
  interheater returns
    -> E-303 on the COLDEST group (one ambient exchanger, its own NTU)
    -> mixed with the bypass returns
    -> E-304 cold side
    -> cold TES
```

The coolant loop closes on the **recuperated** inlet, not on the mixed return.
Closing it on the mixed return would accept a plant whose cold tank is tens of
kelvin colder than the one actually built.

E-303's group is selected by TEMPERATURE, coldest first. Under the cascade every
interheater was fed from one trunk temperature, which happened to make the
returns monotone in stage order and let an ordered-suffix search be optimal.
E-304 gives each stage its own supply, the returns are no longer sorted by
stage, and a stage-ordered suffix would quietly stop being the optimum. Any
optimal group is downward closed in temperature, so the `N` coldest-first
thresholds remain the complete search rather than a slice of the `2**N` subsets.

## 8. Why not without a heat user

Without a user there is no reason to stage the trunk. The only sink for the
descent would be the plant's own cold return, so staging would warm the cold
tank, capture less compression heat and raise compressor work, in exchange for
nothing sellable. LTA-CAES and the `max_electric_efficiency` dispatch therefore
keep the direct path: every interheater draws from the one mixed hot-store
temperature and the conserved inventory is allocated for maximum turbine work.

## 9. Required invariants

Automated tests assert that:

- there is exactly one heat-user exchanger and it sees the complete inventory;
- E-302's outlet is exactly the first extraction;
- there is one extraction per expansion stage and the bleeds sum to the inventory;
- trunk flow through the zones is strictly decreasing and equals the suffix sum;
- the ladder is non-increasing and never starves a stage;
- one common margin sets every extraction;
- a non-monotone demand profile puts two stages on one nozzle with a zero-duty zone;
- every zone is inside its finite-NTU class and both its terminals are positive;
- recuperated duty equals the zone sum and equals the return's temperature rise;
- E-304 sits between the final mixing and the cold tank;
- first law and exergy balances close.

See `tests/test_extraction_exchanger.py` for executable definitions.

## 10. Provenance

The device is a counter-current multi-stream heat exchanger with staged side
draw-offs on the hot stream. Its thermodynamic ancestor is the regenerative
feedwater heating train; its closest working relatives are cryogenic liquefier
cold boxes, where a fraction of the stream is bled to an expander at each
temperature level.

- Wolf and Budt, *LTA-CAES - A low-temperature approach to Adiabatic Compressed
  Air Energy Storage*, Applied Energy 125 (2014),
  [DOI](https://doi.org/10.1016/j.apenergy.2014.03.013);
- Liu et al., *Characteristics of air cooling for cold storage and power
  recovery of CAES with inter-cooling*, Applied Thermal Engineering 107 (2016),
  [DOI](https://doi.org/10.1016/j.applthermaleng.2016.06.168);
- *Subcooled compressed air energy storage system for coproduction of heat,
  cooling and electricity*, Applied Energy 205 (2017),
  [DOI](https://doi.org/10.1016/j.apenergy.2017.08.006).

The exact branch topology remains this project's design hypothesis.
