# Usage and configuration

## Run a default case

```powershell
python -m caes.cli --mode adiabatic
python -m caes.cli --mode diabatic
```

Use `--plot artifacts/cycle.png` to save a simple temperature-entropy trace.
The program never opens a GUI or blocks on a plot window.

## Create and edit a configuration

```powershell
python -m caes.cli --write-default-config example_config.json
python -m caes.cli --config example_config.json
```

Important configuration groups:

| Inputs | Meaning |
|---|---|
| `ambient_*`, `storage_pressure_bar` | Air-store boundary states. Storage pressure must exceed ambient. |
| `compressor_*`, `expander_*` | Stage count and isentropic efficiency. |
| `*_pressure_drop`, `heat_exchanger_pinch_c` | Component loss and heat-transfer constraints. |
| `heat_exchanger_model` | `pinch` for a target-temperature study; `counterflow_ntu` for finite-area air/water exchangers. |
| `heat_exchanger_area_m2`, `overall_heat_transfer_coefficient_w_m2k` | Per-exchanger area and effective overall `U`; together these give `UA`. |
| `air_mass_flow_kg_s`, `water_mass_flow_kg_s` | Design-point heat-capacity rates for the counter-current NTU calculation. |
| `air_mass_kg` | Air mass represented by the charge/discharge batch. |
| `water_tank_volume_m3`, `water_initial_temperature_c` | Finite sensible-storage capacity and initial state. |
| `heat_recovery_effectiveness`, `thermal_store_loss_fraction` | Recovery and dwell loss for A-CAES. |
| `use_ambient_reheat` | Whether D-CAES uses externally supplied ambient heat between turbine stages. |

`air_mass_kg` and water volume must be chosen together. A tank volume without
the charged air mass cannot establish a physical thermal-energy balance.

## Counter-current area and screening cost

Start from [counterflow_example_config.json](../counterflow_example_config.json).
For an A-CAES train with `Nc` compressor stages and `Ne` expander stages, the
finite-area model reports `Nc - 1 + Ne` air/water exchangers: all intermediate
intercoolers plus every reheat exchanger. The final cavern aftercooler remains
an ambient heat-rejection step and is not included in recovered-heat area.

Set `heat_exchanger_reference_cost_eur` only when you have a cost correlation
appropriate to the exchanger construction, pressure rating, material, currency
year, and project location. The optional screening calculation is:

```text
installed cost = N × Creference × (A / Areference)^exponent × installation factor
```

It is intentionally a configurable sensitivity calculation, not a vendor cost
estimate. The example's monetary coefficient is illustrative only; replace it
with a traceable correlation or vendor data before making an economic decision.

## Interpreting results

For A-CAES, `Electrical/shaft round-trip efficiency` is the internal
mechanical/electrical boundary of this model. It excludes motor, generator,
and auxiliary losses.

For D-CAES, read `Shaft-work ratio` together with `External heat supplied`.
Do not describe it as storage RTE, because it includes energy drawn from outside
the stored-air/thermal-store boundary.
