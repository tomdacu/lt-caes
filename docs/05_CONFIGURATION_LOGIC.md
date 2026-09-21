# Configuration logic

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Related:** [Plant concepts](01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) · [Theory and objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md) · [Usage](07_USAGE.md)  
> **Code/tests:** `caes/config.py`, `tests/test_config.py`

## Canonical concept names

The interface, reports and P&ID use the same names everywhere:

- **LTA-CAES (low-temperature adiabatic CAES)**;
- **LTAHP-CAES (low-temperature adiabatic heat and power CAES)**.

The two names are labels for one plant selected by `heat_offtake`, whose JSON
and Python values are the stable compatibility values `none` and `heat_user`.
The labels are presentation text only; changing them does not invalidate
existing studies. There is no `mode` field and no `PlantMode` enum in the
schema: the off-take is the only architectural switch.

A legacy `"mode": "adiabatic"` key in an old JSON file is **ignored with a
deprecation warning**, so records written before the split still load.
`"mode": "diabatic"` is **rejected** with a clear error, because the ambient
diabatic concept is not part of this line.

`caes.logic` is shared by the GUI and CLI and is the source of truth for active
and dormant inputs. JSON keeps the stable low-level enum value; the concept
name is derived from it.

## Current brainstorming defaults

Reset Defaults opens the LTAHP reference point requested for configuration
screening: six compressor and six expander stages, 85.8 bar storage pressure
(`2.1^6` rounded to one decimal), all active exchanger NTUs equal to 5, direct
coolant limits -80/200 degC, 80/45 degC heat user, zero
normalized tank UA and the combined heat-plus-power objective. The broad
coolant limits are intentionally non-binding defaults, not a material claim;
real candidate fluids must replace them with characterized limits/properties.

## Concept mapping

| Concept | `heat_offtake` | Ambient reheat | Example file |
|---|---|---|---|
| LTA-CAES | `none` | none; the plant must close on the coolant loop alone | `counterflow_example_config.json` |
| LTAHP-CAES | `heat_user` | none; the heat user is the off-take sink | `heat_and_power_example_config.json` |

Neither form has an air-side ambient exchanger; the one ambient exchanger in
the model is the heat-only E-303 on the coolant return, sized by
`cold_return_cooler_ntu` and active in both forms.

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

`ambient_heat_exchanger_ntu` belongs to the ambient diabatic concept and no
longer exists in the schema. An old JSON file carrying it still loads: the key
is ignored with a deprecation warning, because this line has no air-side
ambient exchanger for it to size.

Equipment tags follow: `E-20x` is a coolant interheater. It once shared a tag
band with the ambient reheaters an earlier revision carried, which made "the
reheater" mean two different devices depending on which concept was being
drawn.

Machinery, boundary pressure/temperature, ambient humidity, the coolant loop,
E-303, circuit limits, tanks and the objective are active in both forms.
LTA leaves the heat-user fields dormant; LTAHP additionally activates the E-302
heat-user temperatures, `heat_user_exchanger_ntu` and `extraction_exchanger_ntu`.

`heat_exchanger_ntu`, `cold_return_cooler_ntu`, `heat_user_exchanger_ntu` and
`extraction_exchanger_ntu` select exchanger performance classes at the plant
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

LTA/LTAHP supplies stage-specific coolant duty: LTAHP sells the top of the
trunk through E-302 and then stages the rest to the interheaters in E-304. The
0.1 wt% possible-condensate
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

- `max_electric_efficiency` - normal LTA policy;
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
