# Configuration logic

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Related:** [Plant concepts](01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) · [Theory and objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md) · [Usage](07_USAGE.md)  
> **Code/tests:** `caes/config.py`, `tests/test_config.py`

## Canonical concept names

The interface, reports and P&ID use the same names everywhere:

- **AD-CAES (ambient diabatic)**;
- **LTA-CAES (low-temperature adiabatic CAES)**;
- **LTAHP-CAES (low-temperature adiabatic heat and power CAES)**.

The JSON and Python values remain the stable compatibility values shown in the
table below (`diabatic`, `adiabatic`, `none`, and `heat_user`). The labels are
presentation text only; changing them does not invalidate existing studies.

`caes.logic` is shared by the GUI and CLI and is the source of truth for active
and dormant inputs. JSON keeps the stable low-level enum values; concept names
are derived from their combination.

## Startup configuration and code defaults

The application opens with, and "Reset defaults" restores, the **reference
plant** `caes.presets.REALISTIC_REFERENCE`: a large (tens of MW) plant with
typical published component values and a few marked design choices. It has a
100 bar salt cavern, eight integrally geared compression and eight expansion
stages at 0.86 / 0.85 isentropic efficiency, 1.5 % pressure drop per
exchanger, air/water exchangers of NTU 3.4, a water-glycol loop limited to
-25/150 °C and an 80/40 °C district-heating user at a 10 °C, 80 % RH site. The command line uses it when no `--config` is
given, and `--write-default-config` writes it. Every value and its source is
in [document 17](17_REALISTIC_REFERENCE_PARAMETERS.md).

`PlantConfig()` without arguments keeps the older screening point: six
compressor and six expander stages, 85.8 bar storage pressure (`2.1^6`
rounded to one decimal), all active exchanger NTUs equal to 5, direct coolant
limits -80/200 degC, 80/45 degC heat user, zero normalized tank UA. It is the
fixed numerical baseline of the test suite and of
`heat_and_power_example_config.json`; its broad coolant limits are
intentionally non-binding and are not a material claim.

## Concept mapping

| Concept | `mode` | `heat_offtake` | Ambient reheat | Example file |
|---|---|---|---|---|
| AD-CAES | `diabatic` | dormant / `none` | always enabled; otherwise expansion temperatures violate the icing envelope | `--config heat_and_power_example_config.json --mode diabatic` |
| LTA-CAES | `adiabatic` | `none` | dormant | concept option; each point must prove a heat-only closed loop |
| LTAHP-CAES | `adiabatic` | `heat_user` | dormant | `heat_and_power_example_config.json` |

The off-take enum value is `heat_user`. The older `district_heating` still
loads and maps to it, as do the older `district_heating_supply_temperature_c`,
`district_heating_return_temperature_c` keys, each with a deprecation warning.
Old approach fields are ignored with a warning because a kelvin value cannot
be reinterpreted as NTU. A configuration file is the record of an
experiment, so old records must stay readable; the names were changed because
the heat user is not necessarily a network, and code that says otherwise keeps
misleading its reader.

`coolant_cascade_groups` (and the older `thermal_storage_levels`) was
**removed** together with the serial cascade it configured: the topology has
exactly one user exchanger (E-302) and one extraction per expansion stage on
E-304, so a grouping count has nothing left to control. Old files still load -
the key is ignored with a deprecation warning, never remapped onto another
field.

`extraction_exchanger_ntu` sizes EACH ZONE of E-304. The zone, rather than the
body, is the unit here because the trunk loses mass at every extraction, so its
heat-capacity rate is a step function of position and one whole-body
effectiveness would be invalid. See
[document 08](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md) and the
[architecture specification](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md).

`ambient_heat_exchanger_ntu` is the only AD-CAES recovery input. Ambient
reheat is mandatory: a no-reheat expansion would drive the air below the
icing-safe temperature envelope. There is no switch or alternate no-reheat
branch in the public schema or solver.

Equipment tags follow: `AH-20x` is an ambient reheater and exists only in
AD-CAES, `E-20x` is a coolant interheater and exists only in the adiabatic
concepts. The two used to share the `E-20x` band, which made "the reheater"
mean two different devices depending on which concept was being drawn.

Machinery, boundary pressure/temperature, and ambient humidity are active for
all concepts. AD-CAES activates ambient-HX NTU and its turbine/throttle
controls; coolant-loop, tank, objective, and heat-off-take fields are dormant.
LTA activates the coolant HX, E-303, circuit limits, tanks, and objective.
LTAHP additionally activates the E-302 heat-user temperatures and exchanger NTU
fields; it does not activate air-side ambient recovery.

`heat_exchanger_ntu`, `ambient_heat_exchanger_ntu`,
`cold_return_cooler_ntu`, and `heat_user_exchanger_ntu` select exchanger performance classes at the plant
design point. For every different candidate plant the corresponding exchanger
is implicitly resized so that `UA_design = NTU * C_min,design`. These fields do
not describe one fixed core operated off-design while the optimizer changes
flows, pressure or stage count. Geometry, area, fouling, part-load coefficients
and cost belong to a later equipment-sizing layer.

## Derived operating limits

The removed `minimum_expander_outlet_temperature_c` and all fuel inputs are not
part of the schema. The expander limit is derived at every pressure from the
final-aftercooler vapour ratio:

```text
T_hard(p) = 0 degC       when the local phase boundary permits liquid
            T_frost(p)   when it is an ice boundary
T_out,min(p) = T_hard(p) + 10 K
```

AD-CAES takes the maximum safe turbine pressure drop and throttles the
remainder. LTA/LTAHP supplies stage-specific coolant duty; LTAHP sells the top of
the trunk through E-302 and then stages the rest to the interheaters in E-304. The 0.1 wt% possible-condensate
screen protects only the discharge-side dry-air approximation. See
[Moisture, dew point, and wet expansion](06_MOISTURE_DEW_POINT_AND_WET_EXPANSION.md).

`coolant_maximum_temperature_c` and `coolant_minimum_temperature_c` are direct
limits checked on every coolant state. They replace the old pressure-derived
saturation ceiling and `coolant_freezing_temperature_c`; the latter remains a
load-only alias for the new minimum field. The present solver retains a
water-like constant liquid heat capacity internally (4180 J/kg/K), but does
not infer a coolant limit from pressure or saturation. `cold_return_cooler_ntu`
sizes the one heat-only E-303, placed on the coldest group of returns.

Public configuration, GUI labels and reports call this loop **coolant**. Some
Python result attributes and low-level helper names still contain `water` for
backward compatibility with saved analyses; in those identifiers the word
means the generic constant-`cp` plant coolant, not a claim that pure water is
valid down to the configured -80 degC screening limit. Water mentioned in the
moisture model is different: that is actual condensable water carried by air.

`thermal_storage_tank_ua_w_per_k` is the per-tank conductance normalized to the
one-kilogram-air basis and is applied to both tanks.
`storage_duration_hours` is each tank's standing time.

## Solver outputs, not inputs

The following are deliberately absent from `PlantConfig`:

- cold- and hot-tank temperatures;
- the E-304 extraction margin, the extraction temperatures and the bleed flows;
  the recuperated duty and the cold-tank inlet that follows from it;
- total and per-stage coolant/air ratios;
- the user's own mass flow, which is a slave of the duty and the span its
  operator fixed;
- E-303 selected cutoff, flow, temperatures and ambient heat absorption.

They are mutually dependent results of water mass/energy closure. Exposing one
as an independent knob would over-constrain the model.

## Objectives and migration

The active objectives are:

- `max_electric_efficiency` - normal AD/LTA policy;
- `max_combined_energy_delivery` - normal LTAHP policy, maximizing
  `(W_exp + Q_DH)/W_comp`.

For LTAHP the objective is also a dispatch instruction. With
`max_electric_efficiency` both E-302 and E-304 are bypassed (`Q_user = 0`) and
the full hot-coolant inventory is available to the interheaters at the one
stored temperature. With `max_combined_energy_delivery` both bodies are active:
the user receives everything above the first extraction, and E-304 recuperates
the descent below it into the coolant return.
Because E-303 is heat-only, bypass operation is feasible only if the turbine
train itself leaves a periodic coolant loop; the default LTAHP point needs the
user as a real heat sink and correctly rejects electricity-only dispatch.

The delivery ratio is the single energy metric. It may exceed one when ambient
energy is harvested and is not a thermodynamic efficiency. Useful-exergy
efficiency remains the reported guard metric and is the only one bounded by
unity; see
[Objectives, metrics, and exergy accounting](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md#the-one-energy-metric-and-what-it-deliberately-excludes).

The removed string `max_total_exergy_efficiency` is accepted only as a legacy
JSON alias. Loading it emits `DeprecationWarning` and maps to
`max_electric_efficiency` when `heat_offtake=none`, or
`max_combined_energy_delivery` with a heat user. Saved configurations use
the resolved active value.

## Validation order and domains

`PlantConfig` validates domains before cross-field ordering:

- ambient, district supply/return, and coolant-limit
  temperatures must be above absolute zero;
- ambient temperature must be at least 110 K, the moisture-correlation domain;
- heat-user return must be below supply and user-exchanger NTU must be positive;
- coolant maximum temperature must exceed its minimum and both must be above
  absolute zero;
- storage pressure must exceed ambient pressure;
- efficiency, pressure-drop, humidity, stage-count, NTU, UA, and duration
  ranges are checked explicitly.

The shared coolant heat-capacity and psychrometric constants live in
`caes/constants.py`.
