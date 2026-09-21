# Moisture, dew point, and wet expansion

> **Parent:** [Physics and model boundary](02_PHYSICS_AND_MODEL_BOUNDARY.md)  
> **Related:** [Plant concepts](01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) · [Discharge algorithm](algorithms/discharge_train.md)  
> **Code/tests:** `caes/moisture.py`, `caes/thermal_limits.py`, `tests/test_moisture.py`

This is the single source for
moisture, separator, dew/frost-point, and wet-expander guidance; other project
documents should link here instead of duplicating these rules.

## 1. Why moisture limits these plants

Atmospheric air always carries water vapour. Compression raises its partial
pressure, so air that was unsaturated at the compressor inlet can cross its
saturation boundary when an intercooler, aftercooler, pipe, or cavern cools it.
Three conditions must not be confused:

- **water vapour** is gaseous water mixed with air and cannot be removed by a
  mechanical separator;
- **liquid carryover** is condensed water transported as droplets or wall film
  and can be removed by a knock-out vessel, centrifugal separator, demister,
  or coalescer;
- **ice** forms when wet air or carried liquid reaches a sufficiently cold
  surface or expansion state.

The relevant quantities are pressure dew point and frost point, not a
combustible flash point. A separator after each condensation-producing cooler
protects the next compressor body. Free liquid can erode impeller leading
edges and diffusers, reduce surge margin, cause vibration and imbalance,
promote corrosion, wash lubricant films, damage valves or cylinders, form a
liquid slug, and later freeze in valves or turbine passages. Two-phase
compressor studies place severe erosion near the first impeller surfaces; see
the [Virginia Tech wet-compression study](https://vtechworks.lib.vt.edu/items/4a77cb76-5862-45a5-945a-c62183e89529/full).

## 2. Definitions and math

The **pressure dew point (PDP)** is the temperature at which compressed-air
vapour first saturates with respect to liquid water at the local total
pressure. The **frost point** is the corresponding saturation temperature with
respect to ice below the water triple point. Both change with total pressure.

The humidity ratio on a dry-air basis is

```text
w = m_water-vapour / m_dry-air
w = 0.621945 p_v / (p - p_v)
p_v = p w / (0.621945 + w)
```

where `p_v` is water partial pressure and `p` is total pressure. CoolProp
supplies the liquid saturation curve. Below the shared water triple point,
273.16 K and 611.657 Pa, the diagnostic uses the Murphy-Koop ice correlation:

```text
ln(p_ice/Pa) = 9.550426 - 5723.265/T + 3.53068 ln(T) - 0.00728332 T
```

The correlation is not evaluated below 110 K. These constants, the water
critical point, absolute zero, and the psychrometric ratio are defined once in
`caes/constants.py`.

### The enhancement factor, and why it is not optional here

Water vapour in compressed **air** is not pure-component water vapour. The
liquid sits at the total pressure rather than at its own vapour pressure
(Poynting), and air and water molecules interact in the gas phase. Both effects
raise the equilibrium vapour content above the pure saturation curve by the
enhancement factor

```text
f(T, p) = x_vapour p / p_saturation,pure(T)        [-]     f >= 1
```

so the relation this module actually uses, in BOTH directions, is

```text
p_v,saturated(T, p) = f(T, p) p_saturation,pure(T)
phase boundary:       f(T_phase, p) p_saturation,pure(T_phase) = p_v
```

At CAES pressures this is a leading-order term, not a refinement:

| total pressure | `f` at 15 degC |
|---|---|
| 1 bar | 1.004 |
| 10 bar | 1.033 |
| 30 bar | 1.100 |
| 70 bar | 1.255 |
| 100 bar | 1.392 |

Omitting it made the model report **28% less water** than is really there at
100 bar. That is the wrong direction for a safety screen: it understated the
stored vapour ratio, the pressure dew point, the frost point, and therefore the
wet-rated anti-icing floor by 3 to 4 K at every expansion stage. At 30 bar it
also flipped the regime, reporting a frost boundary at -2.1 degC where the real
one is a dew point at +2.1 degC.

`f` is tabulated once from CoolProp's humid-air backend - the same library the
air properties come from - on a temperature by log-pressure grid, and then
interpolated. The forward map agrees with that backend to better than 0.2% over
its whole validity range, and the dew/frost-point inversion reproduces the
state it came from to better than 1e-4 K. The factor is applied in the single
function both maps share (`effective_saturation_vapor_pressure_pa`), precisely
so a future change cannot correct one direction and leave the other behind.

**Admitted extrapolation.** The humid-air backend is validated to 10 MPa. Above
that, `ln f` is extrapolated linearly in pressure from the slope at the top of
the table, which matters for 100 to 300 bar caverns. The extrapolation is
monotonic and conservative for a moisture screen: it keeps more water in the
stored air than the uncorrected model, never less. It is not a validated
correlation at those pressures and should be replaced by measured or
Hyland-Wexler-type data before any detailed design.

## 3. What the model calculates and its validity screens

Every charging intercooler and the final aftercooler are modelled as a cooler
followed by an ideal liquid separator:

```text
compressor -> cooler -> knock-out/demister -> drain -> next body or cavern
w_out = min(w_in, w_saturation(p_out, T_out))
```

There is no separate cavern-condensate bookkeeping term. The final
aftercooler/separator vapour ratio is the protected discharge basis. The
diagnostic follows vapour and equilibrium condensate through both trains and
draws the continuous dew/frost boundary, but the energy and exergy cycle still
uses dry CoolProp `Air`. Humidity therefore does not change compressor or
turbine work, latent cooler duty, air mass flow, TES optimization, or exergy
destruction.

Two different approximation checks must remain distinct:

- The **discharge-side** maximum-possible-condensate screen is 0.1 wt% of the
  wet stream. At that bound, latent energy is about 2.5 kJ/kg-stream, below 1%
  of the 300 kJ/kg per-stage reference enthalpy-drop envelope. At the default
  0.010610 wt%, the omitted discharge latent term is about 0.27 kJ/kg-air.
- The **charge-side** condensation omission is not bounded by that screen. The
  default separators remove 6.2402 g/kg-dry-air, corresponding to about
  15.3 kJ/kg-dry-air at 2.45 MJ/kg-water. This larger admitted limitation can
  alter cooler duty, water allocation, and optimized outlet temperatures.

The hardware reference is also separate from model validity. Baker Hughes
publishes up to 250 bar inlet pressure, -270 to +270 degC, 300 kJ/kg enthalpy
drop per stage, 1 wt% liquid at suction, and 35 wt% at discharge for its
[turboexpander-compressor family](https://www.bakerhughes.com/expanders/turboexpander-compressors).
The model assumes a wellhead separator and checks the conservative bound
`y_liquid,max = w/(1+w)` against the discharge reference. The 0.1 wt% dry-air
screen binds orders of magnitude earlier, so the 35 wt% check does not control
current accepted cases. Neither value replaces an OEM guarantee for droplet
size, distribution, tip speed, erosion life, drains, off-design operation, or
slug volume. Atlas Copco lists CAES applications and API 617 / ASME PTC-10 Type
2 design/test bases in its
[expander brochure](https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/gas-and-process/documents/Atlas_Copco_Gas_and_Process_Expander_Brochure.pdf.coredownload.pdf).

Not modelled are finite separator efficiency, drain failure, droplet size,
wall films, corrosion, brine evaporation, latent heat, transient cavern
humidity, and any validated enhancement-factor data above 10 MPa. A Huntorf-based study reported cavern relative-humidity cycling from
36.45% to 99.85%, demonstrating that dry injection alone cannot guarantee dry
withdrawal: [Applied Energy cavern-moisture study](https://www.sciencedirect.com/science/article/pii/S0306261924017860).

## 4. The wet-expander operating envelope

All three concepts use one water-tolerant radial-expander screening basis.
Liquid condensation may occur in a wet-rated body; ice may not. For protected
vapour ratio `w` and local pressure `p`:

```text
T_hard(p,w) = 273.15 K       if T_phase >= 273.16 K
              T_frost(p,w)   if T_phase <  273.16 K

T_min,wet(p,w) = T_hard(p,w) + 10 K
```

The triple point controls the liquid/ice branch; the liquid-region hard floor
remains the conventional 0 degC freezing reference. Thus the bulk expander
outlet must be at least +10 degC where liquid is permitted, or 10 K above the
local frost point in dry sub-zero operation. Liquid carryover into a sub-zero
section is not permitted. One solver-wide
`TEMPERATURE_LIMIT_TOLERANCE_K = 1e-4 K` enforces the boundary; it is a
numerical guard, not a physical relaxation.

The 10 K preliminary margin replaces an earlier unsupported 5 K assumption.
Its evidence chain is deliberately conservative rather than a claim of a
universal OEM limit:

- ANSI/ISA-7.0.01 instrument-air guidance calls for PDP at least 10 degC below
  the lowest system temperature; see the
  [Atlas Copco summary](https://www.atlascopco.com/en-uk/compressors/wiki/compressed-air-articles/instrument-air-quality).
- GE identifies icing exposure below +4.4 degC at RH above 65% and describes
  anti-icing temperature rises of 5.6 to 22.2 K in its
  [anti-icing guide](https://www.gevernova.com/content/dam/gepower-new/global/en_US/downloads/gas-new-site/services/gas-turbines/GEA32069A-AntiIcing-US-R1-LR.pdf).
- EASA's generic engine-icing definition includes visible-moisture operation
  below +10 degC in its
  [CS-MMEL guidance](https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-master-minimum-equipment-0?page=5).
- A representative Vaisala DMT143 dew/frost transmitter specifies +/-2 degC
  accuracy, already a substantial part of a 5 K allowance:
  [Vaisala specification](https://docs.vaisala.com/api/khub/documents/I69cByWEnaVMF~sSf1ywFA/content).

Water management is still mandatory. NOAA distinguishes liquid dew from ice
deposition in its [frost-point description](https://gml.noaa.gov/ozwv/wvap/instrument.html);
GE documents rapid hoar-frost accumulation from supercooled droplets in
[GER-3419](https://www.gevernova.com/content/dam/gepower-pgdp/global/en_US/documents/technical/ger/ger-3419a-gas-turbine-inlet-air-treatment.pdf);
and [ASME TDP-1](https://www.asme.org/codes-standards/find-codes-standards/prevention-of-water-damage-to-steam-turbines-used-for-electric-power-generation-fossil-fueled-plants)
requires drains, controls, instrumentation, and procedures to prevent turbine
water damage. GE wet-steam hardware likewise uses moisture removal and erosion
protection ([GER-3582](https://www.gevernova.com/content/dam/gepower-pgdp/global/en_US/documents/technical/ger/ger-3582e-steam-turbines-for-stag-power-systems.pdf)).
Steam-turbine evidence supports the protection architecture, not direct reuse
of steam-quality limits for compressed air.

Cryostar offers aluminium, titanium, and stainless expander wheels
([wheel specification](https://cryostar.com/datas-pdf/booklet/en/HYDROCARBON-TURBO_EXPANDERS.pdf)).
A preliminary wet-service design should therefore review stainless or titanium
rather than accept aluminium automatically. Published 17-4PH data list rotor
applications, corrosion resistance, and a Charpy value at -75 degF (-59 degC)
([voestalpine data](https://www.voestalpine.com/specialtymetals/nam/en/materials/17-4ph/)),
but a coupon result is not an expander minimum design metal temperature. Final
material, coating, fracture, erosion, and local-temperature acceptance belongs
to the OEM.

## 5. Stage-by-stage moisture inventory of the default plant

The following tables were regenerated with the current code for 15 degC,
60% RH, 1.01325 to 100 bar, four compression stages, four expansion stages,
and the 15 degC final aftercooler. Wet-stream mass is the denominator for wt%.
The inlet is 0.630630 wt% water; both concepts finish with
`w = 0.000106109038 kg/kg-dry-air`, or **0.010609778 wt%** stored vapour, and
remove 6.240212 g/kg-dry-air.

### LTA-CAES charge train

| Connection | Pressure | Temperature | Vapour | Liquid before separator |
|---|---:|---:|---:|---:|
| K-101 suction | 1.013 bar | 15.00 degC | 0.630630 wt% | 0 |
| K-101 discharge | 3.259 bar | 148.78 degC | 0.630630 wt% | 0 |
| E-101 outlet | 3.194 bar | 49.88 degC | 0.630630 wt% | 0 |
| K-102 suction | 3.194 bar | 49.88 degC | 0.630630 wt% | 0 |
| K-102 discharge | 10.271 bar | 199.24 degC | 0.630630 wt% | 0 |
| E-102 outlet | 10.066 bar | 62.47 degC | 0.630630 wt% | 0 |
| K-103 suction | 10.066 bar | 62.47 degC | 0.630630 wt% | 0 |
| K-103 discharge | 32.375 bar | 217.79 degC | 0.630630 wt% | 0 |
| E-103 outlet | 31.727 bar | 67.15 degC | 0.541424 wt% | 0.089206 wt% |
| K-104 suction, after separation | 31.727 bar | 67.15 degC | 0.541908 wt% | 0 |
| K-104 discharge | 102.041 bar | 225.64 degC | 0.541908 wt% | 0 |
| E-104 outlet | 100.000 bar | 69.28 degC | 0.187623 wt% | 0.354284 wt% |
| AC-101 outlet | 100.000 bar | 15.00 degC | 0.010591 wt% | 0.177700 wt% |

Condensation begins at E-103. E-101 and E-102 need no bulk separator at this
design point, although off-design drains or a compact demister are prudent.
E-103, E-104, and AC-101 require liquid removal. With only a final separator,
K-104 would ingest 0.089206 wt% liquid; predicted re-evaporation in the hot
body is not an acceptable design credit.

### AD-CAES charge train

| Connection | Pressure | Temperature | Vapour | Liquid before separator |
|---|---:|---:|---:|---:|
| K-101 suction | 1.013 bar | 15.00 degC | 0.630630 wt% | 0 |
| K-101 discharge | 3.259 bar | 148.78 degC | 0.630630 wt% | 0 |
| E-101 outlet | 3.194 bar | 21.73 degC | 0.507805 wt% | 0.122824 wt% |
| K-102 suction, after separation | 3.194 bar | 21.73 degC | 0.508430 wt% | 0 |
| K-102 discharge | 10.271 bar | 158.70 degC | 0.508430 wt% | 0 |
| E-102 outlet | 10.066 bar | 22.27 degC | 0.165782 wt% | 0.342648 wt% |
| K-103 suction, after separation | 10.066 bar | 22.27 degC | 0.166352 wt% | 0 |
| K-103 discharge | 32.375 bar | 160.00 degC | 0.166352 wt% | 0 |
| E-103 outlet | 31.727 bar | 22.44 degC | 0.053218 wt% | 0.113134 wt% |
| K-104 suction, after separation | 31.727 bar | 22.44 degC | 0.053278 wt% | 0 |
| K-104 discharge | 102.041 bar | 161.39 degC | 0.053278 wt% | 0 |
| E-104 outlet | 100.000 bar | 22.89 degC | 0.017358 wt% | 0.035920 wt% |
| AC-101 outlet | 100.000 bar | 15.00 degC | 0.010609 wt% | 0.006756 wt% |

Every ambient intercooler condenses water. Retain a knock-out/demister and
automatic drain after each. In the single-final-separator counterfactual,
K-102, K-103, and K-104 would ingest 0.122824, 0.465052, and 0.577659 wt%
liquid respectively, while AC-101 would finally receive 0.620086 wt% liquid.
That scenario is only an equilibrium screen and is invalid for the dry
compressor model. Atlas Copco's ZR/ZT package similarly places moisture
separation and drains between stages
([flow description](https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/oil-free-air/documents/zrzt-200-355-vsd-plus.pdf)).

### Expansion inventory

The envelope enforcement holds the final charge-side humidity ratio fixed for
every expander stage. The reporting diagnostic below instead credits
equilibrium condensate removed at each `MS-20x` separator before continuing to
the next stage. Reported downstream liquid fractions are therefore
systematically lower than the conservative enforcement basis; the current UI
does not flag that distinction at each row.

| Concept / expander | Suction P / T | Discharge P / T | Vapour suction / discharge | Liquid suction / discharge |
|---|---:|---:|---:|---:|
| LTA T-201 | 98.000 bar / 122.63 degC | 31.727 bar / 27.30 degC | 0.010610 / 0.010610 wt% | 0 / 0 |
| LTA T-202 | 31.092 bar / 121.39 degC | 10.066 bar / 28.14 degC | 0.010610 / 0.010610 wt% | 0 / 0 |
| LTA T-203 | 9.865 bar / 117.21 degC | 3.194 bar / 25.66 degC | 0.010610 / 0.010610 wt% | 0 / 0 |
| LTA T-204 | 3.130 bar / 112.78 degC | 1.013 bar / 22.50 degC | 0.010610 / 0.010610 wt% | 0 / 0 |
| AD T-201, bypassed | 98.000 bar / 14.67 degC | no turbine drop | 0.010597 / 0.010597 wt% | 0.000013 / 0.000013 wt% |
| AD T-202 | 31.092 bar / 14.83 degC | 27.851 bar / 6.98 degC | 0.010610 / 0.010610 wt% | 0 / 0 |
| AD T-203 | 9.865 bar / 14.33 degC | 7.039 bar / -8.42 degC | 0.010610 / 0.010610 wt% | 0 / 0 |
| AD T-204 | 3.130 bar / 13.76 degC | 1.801 bar / -22.03 degC | 0.010610 / 0.010610 wt% | 0 / 0 |

The tiny AD T-201 suction liquid follows the 100-to-98 bar reheater pressure
drop and remains far below the 1 wt% reference suction cap. MS-201 through
MS-204 provide off-design protection against cavern carryover, transients, and
non-equilibrium droplets. One dedicated final deep-cooling/drying duty suffices
to guarantee cavern PDP; E-104 and AC-101 may share a casing if the vendor
preserves their separate thermal duties. Dryers and separators are deliberately
omitted from the simplified generated P&ID.

## 6. AD-CAES throttle/valve moisture rules

AD-CAES takes the maximum pressure drop that a wet-rated turbine can accept at
each stage. If full expansion would cross the margined line, it expands only
to the safe intermediate pressure and throttles the rest isenthalpically. A
downstream ambient trim reheater restores the 10 K margin where possible. A
bypassed turbine means its scheduled pressure drop is assigned to the throttle.

The bulk throttle outlet may consume the engineering margin but may never
cross the unmargined liquid/frost hard floor. Detailed valve sizing must also
verify local throat and wall temperatures during steady operation, start-up,
and transients; a safe bulk outlet alone does not prove local ice immunity.

## 7. Real-plant drying arrangement

The 93-151 kg/s range in compressed-air drying guidance is a generic CAES
equipment-sizing reference. The separate **169.7 kg/s** value is the dry-air
flow obtained by scaling the supplied LTAHP example to a 70 MW compressor shaft
input (`70 MW / 412.58 kJ/kg-air`). They are not two estimates for one plant.

A defensible low-cost baseline is staged cooling and bulk separation:

1. Install a cooler and high-efficiency separator after each compressor stage
   that can cross its local PDP.
2. Add a final high-pressure surface aftercooler before storage, targeting a
   PDP 5-10 K below the coldest expected wellhead, line, and cavern condition.
3. Use a knock-out section, demister/coalescer, redundant zero-loss drains,
   high-level trip, differential-pressure monitoring, and freeze protection.
4. Install a wellhead scrubber on withdrawal because a wet cavern or bottom
   brine can rehumidify dried injection air.
5. Use a refrigerated dryer near +3 degC PDP when surface cooling cannot meet
   the guarantee. Use heat-of-compression adsorption at -20 or -40 degC PDP
   only when a quantified icing, corrosion, or cavern requirement justifies
   its cost and loss of heat otherwise available to LTA/LTAHP TES.

Conventional separators collect about 80-90% of precipitated water, so the
ideal 100% diagnostic requires a real high-efficiency demister/coalescer and a
verified drain system; see the
[Atlas Copco Compressed Air Manual](https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/compressor-technique-service/documents/Compressed-Air-Manual-9th-edition.pdf)
and [U.S. DOE sourcebook](https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/compressed_air_sourcebook.pdf).
Heatless adsorption and membrane drying are poor default choices at this flow:
CAGI reports roughly 15-18% purge for heatless and about 8% for heated
desiccant dryers, while refrigerated dryers require no purge
([CAGI sizing guidance](https://www.cagi.org/assets/documents/pdfs/SizingFAQ.pdf?updated=1657712701)).

Acceptance criteria should specify seasonal ambient humidity, final charge and
withdrawal-wellhead online PDP, separator outlet liquid loading and cut size,
drain redundancy and capacity, compressor and turbine OEM carryover limits,
droplet erosion limits, and anti-icing margin including sensor uncertainty.
ISO 8573 terminology is useful: class 4 is +3 degC PDP, class 3 is -20 degC,
class 2 is -40 degC, and class 1 is -70 degC. These are pressure dew points,
not atmospheric equivalents
([ISO air-quality guide](https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/oil-free-air/documents/ISO_regulations_%20best_practices_%20guide_air_quality.pdf)).

## 8. Reading the graph overlays

The T-s, h-s, and p-h plots use:

- orange dash-dot: wet-expander operating minimum;
- cyan dashed: stored-air liquid dew-point boundary;
- purple dashed: stored-air frost-point boundary.

A state below the dew line can condense liquid and is acceptable only if it
also stays above the orange operating line. A state below the frost line can
ice and is not acceptable. The curves are equilibrium boundaries, not proof
that real hardware is safe from carried droplets.

For the default stored vapour at 100 bar, the pressure-dependent boundary is:

| Pressure | Phase boundary | Wet-rated minimum |
|---:|---:|---:|
| 100.000 bar | +15.00 degC | +10.00 degC |
| 31.727 bar | -1.47 degC | +8.53 degC |
| 10.066 bar | -14.59 degC | -4.59 degC |
| 3.194 bar | -26.49 degC | -16.49 degC |
| 1.013 bar | -37.35 degC | -27.35 degC |

A colder final aftercooler/dryer shifts the frost boundary:

| Final PDP at 100 bar | Vapour remaining | Frost point at 31.727 bar | Frost point near 1 bar |
|---:|---:|---:|---:|
| +15 degC | 0.106 g/kg | -1.5 degC | -37.3 degC |
| +10 degC | 0.076 g/kg | -5.4 degC | -40.3 degC |
| +3 degC | 0.047 g/kg | -10.9 degC | -44.5 degC |
| -20 degC | 0.0064 g/kg | -31.4 degC | -60.2 degC |
| -40 degC | 0.00080 g/kg | -49.7 degC | -74.6 degC |

An ordinary aftercooler capable of a +10 degC PDP can therefore correspond to
about -40 degC frost point after expansion to atmospheric pressure, but it
cannot provide -40 degC **PDP at 100 bar**; that requires adsorption drying.
