# Physics, accounting boundary, and model limitations

## What is modelled

The solver follows a fixed mass of dry air through steady-flow components. All
state variables use SI units and are calculated with CoolProp's real-air
properties. Kinetic and potential energy changes are neglected.

For each compressor and turbine, the isentropic reference state is obtained at
the outlet pressure and inlet entropy. The actual enthalpy change is then:

```text
compressor: h₂ = h₁ + (h₂s - h₁) / ηc
turbine:    h₂ = h₁ - ηt (h₁ - h₂s)
```

The sign convention is explicit: compressor work is positive (input to air);
turbine work is negative (output from air). Every component is checked against
the steady-flow relation, per unit air mass:

```text
h₂ - h₁ = q_to_air + w_to_air
```

## Pressure losses and staging

Every intercooler and interheater has a fractional pressure loss `δ`, so its
outlet pressure is `p_out = p_in (1 - δ)`. Equal stage pressure ratios are
calculated including all downstream exchanger losses. The final compressor and
turbine stage are then targeted exactly to the configured storage and ambient
pressures. This removes the old model's pressure-drift ambiguity.

An exchanger that cannot transfer heat is represented as an **isenthalpic
throttle** across its pressure loss. It is not forced to an isothermal state;
forcing constant temperature across a real-gas pressure drop can create a small
but nonphysical heat input.

## A-CAES: finite sensible-water thermal store

The A-CAES model recovers a configured fraction of the heat rejected by
**intermediate** intercoolers. The final aftercooler brings the air to the
cavern's ambient-temperature assumption; its residual heat is rejected to the
environment rather than incorrectly sent to a possibly hotter water store.

The store is intentionally simple but conserves energy:

```text
Cstore = Vwater ρwater cp,water
Tstore,new = Tstore,old + Qrecovered / Cstore
```

Before discharge, an explicit standing-loss fraction is applied. At every
interheater, air can be heated only while both conditions hold:

```text
Tair,out ≤ Twater - pinch
Qdelivered ≤ remaining sensible energy above initial water temperature
```

The delivered energy reduces store temperature. Therefore stored heat cannot
be reused independently at every turbine stage, a defect of the previous
maximum-temperature approximation.

For this closed A-CAES boundary:

```text
ηRT = Wturbine,out / Wcompressor,in
```

## D-CAES: external reheat is not free stored energy

In D-CAES, compression heat is rejected and not stored. The model optionally
reheats air between turbine stages from an ambient external source, respecting
the configured pinch. That heat is reported as `external_heat_input_j`.

Because an external heat source supplies energy during discharge, the ratio
`Wturbine,out / Wcompressor,in` is shown only as a **shaft-work ratio**, not as
a closed storage round-trip efficiency. Comparing it directly with A-CAES RTE
would be misleading. A fuel-fired D-CAES analysis additionally needs fuel
lower-heating value, combustor efficiency, exhaust losses, and an exergy or
primary-energy boundary; those are outside this model.

## Important limitations

- The cavern has fixed pressure and reaches ambient temperature; it is not a
  dynamic mass/energy model of cavern charge, discharge, rock heat transfer,
  or pressure swing.
- The water store is well mixed with constant water heat capacity. It does not
  represent thermocline stratification, two-tank hydraulics, or heat-exchanger
  UA/NTU design.
- There is no motor/generator, mechanical-drive, valve, pipeline, or auxiliary
  power model. Add those before quoting plant-level electrical RTE.
- The code is a conceptual design tool, not a safety, control, or equipment
  sizing tool.

## References

- CoolProp documentation: [High-Level Interface](https://coolprop.org/coolprop/HighLevelAPI.html) and [pure-fluid formulations](https://coolprop.org/fluid_properties/PurePseudoPure.html).
- International Energy Agency Energy Storage: [Compressed Air Energy Storage fact sheet](https://www.iea-es.org/wp-content/uploads/public/FactSheet_mechanical_CAES.pdf).
- Zhao, Wang, & Ding, *Performance analysis of compressed air energy storage systems considering dynamic characteristics of compressed air storage*, Applied Energy 2018, [DOI landing page](https://www.sciencedirect.com/science/article/pii/S0360544217311441). This is relevant background for the dynamic-cavern effects intentionally excluded here.
