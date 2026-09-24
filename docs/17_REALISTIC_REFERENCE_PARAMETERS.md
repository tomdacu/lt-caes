# The reference plant: parameters and their sources

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Code:** `caes/presets.py` (`REALISTIC_REFERENCE`), `realistic_reference_config.json`  
> **Full source dossier:** [research/REALISTIC_PARAMETERS_SOURCES.md](research/REALISTIC_PARAMETERS_SOURCES.md) (163 links, 155 verified reachable)

The desktop application opens with this configuration. "Reset defaults" and
the command line without `--config` use it too. It describes a **large
LTAHP-CAES plant, tens of MW**, built from commercially available machinery.
Most values are the typical published value for that class. Five are design
choices of this project, marked `[choice]` and justified against the
published range they sit in: equal stage counts, the two machine
efficiencies, the air/water exchanger class and the 80 °C user supply.

`PlantConfig()` without arguments keeps its original field defaults. Those are
the fixed numerical baseline of the test suite, not a claim about a real
plant.

## 1. The plant

```text
site         North-German salt-cavern region, 10 °C annual mean, 80 % RH
storage      salt cavern at 100 bar (single design pressure)
compression  integrally geared compressor, 8 stages, intercooled after every stage
expansion    integrally geared radial expander, 8 stages (two 4-stage gearboxes)
store        two tanks, water-glycol loop from -25 to 150 °C
heat user    district heating, supply 80 °C, return 40 °C
```

## 2. Parameters

Tags: `[datasheet]` vendor document, `[paper]` peer-reviewed, `[project]`
operator or project document, `[estimate]` engineering estimate with the
stated basis, `[choice]` a design decision of this project.

| input | value | published range | basis | tag |
|---|---:|---|---|---|
| `storage_pressure_bar` | 100 | 40-152 | The LTA-CAES design window: 100-152 bar in [Budt, Wolf and Span 2012](https://2012.international.conference.modelica.org/proceedings/html/pdf/ecp12076791_BudtWolfSpan.pdf); 40-100 bar for KompEx (Hadam and Budt 2023). Operating caverns run 43-76 bar (Huntorf, McIntosh). 100 bar sits at the meeting point of the two LTA-CAES designs. Higher pressure lowers every figure of merit here (section 3) | `[paper]` |
| `compressor_stages` | 8 | 5-10 | "an eight stage compressor and a four stage expander, both integrally geared" (Budt, Wolf and Span 2012); IGC vendors offer up to 8-10 stages with intercooling after each ([MAN RG](https://www.man-es.com/docs/default-source/document-sync/rg-integrally-geared-compressors-eng.pdf)). At 100 bar this is a stage ratio of about 1.8, inside the 1.7-2.2 IGC band | `[paper]` |
| `expander_stages` | 8 | 3-8 | Equal to the compressor by choice. An integrally geared expander carries 1-4 stages per gearbox ([Atlas Copco](https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/gas-and-process/documents/new-folder/AC%20Turboexpander%20Brochure.pdf.coredownload.pdf)), so eight stages mean two gearboxes. LTA-CAES used four | `[choice]` |
| `compressor_efficiency` | 0.86 | 0.85-0.89 | Per-stage **isentropic**. Inside the band converted from the IGC polytropic "high eighties" ([Witkowski and Majkut 2012](https://journals.pan.pl/Content/84623/PDF/06_paper.pdf)), one point above its conservative end: a margin for a large machine running across its map | `[choice]` |
| `expander_efficiency` | 0.85 | 0.80-0.92 | Isentropic, total-to-static. The KompEx turbomachine value, 85 % (Hadam and Budt 2023), below the 0.88-0.90 of design studies ([Sciacovelli et al. 2017](https://pure-oai.bham.ac.uk/ws/portalfiles/portal/42823087/Manuscript_Clear_v4.pdf); Pottie et al. 2024) | `[choice]` |
| `intercooler_pressure_drop` | 0.015 | 0.005-0.025 | 1.5 % per exchanger, the base value of the Huntorf-calibrated low-temperature A-CAES model of [Luo et al. 2016](https://wrap.warwick.ac.uk/76075/1/WRAP_1-s2.0-S0306261915013185-main.pdf) | `[paper]` |
| `interheater_pressure_drop` | 0.015 | 0.005-0.025 | Same source; every paper that publishes both applies one value to charge and discharge exchangers | `[paper]` |
| `heat_exchanger_ntu` | 3.4 | 2.8-3.4 | The top of six A-CAES design points in [Barbour et al. 2025](https://pure-oai.bham.ac.uk/ws/portalfiles/portal/279134473/IET_Renewable_Power_Gen_-_2025_-_Barbour_-_Exergy_analysis_of_isochoric_and_isobaric_adiabatic_compressed_air_energy.pdf) (NTU 2.83-3.41). No source supports a larger class | `[choice]` |
| `heat_user_exchanger_ntu` | 5.0 | 3.7-8.9 | Conventional substation, LMTD about 10 K ([Thorsen and Iversen 2012](https://assets.danfoss.com/documents/latest/90874/AC098986469348en-010201.pdf)) | `[paper]` |
| `extraction_exchanger_ntu` | 8 per zone | 3-13 | By analogy with closed feedwater heaters, terminal difference 2.8-4.4 K ([EPRI TR-107422-V2](https://restservice.epri.com/publicdownload/TR-107422-V2/0/Product)). The least constrained input: no staged-bleed exchanger of this kind exists in a built CAES plant | `[estimate]` |
| `cold_return_cooler_ntu` | 0.8 | 0.4-1.1 | Dry cooler at a typical 5-9 K approach to ambient ([IEA SHC Task 38, C5](https://task38.iea-shc.org/Data/Sites/1/publications/IEA-Task38-Report_C5_Heat%20rejection.pdf)). The model treats the atmosphere as an infinite stream, `eps = 1 - exp(-NTU)`: about 55 % effectiveness | `[paper]` |
| `coolant_minimum_temperature_c` | -25 | | Water-glycol, roughly 40 % glycol. **Needed, not optional:** the tail interheaters see air below 0 °C and their returns leave below the freezing point of water; with pure water (+2 °C) the plant has no feasible design, with 8 + 8 or 6 + 6 stages. The coldest return reaches -11.3 °C, so the limit does not bind; -25 °C keeps the mixture's freezing point about 14 K below it, since a glycol mixture starts forming ice crystals before its nominal freezing point | `[estimate]` |
| `coolant_maximum_temperature_c` | 150 | | Glycol mixtures degrade above roughly 150-175 °C. The plant reaches 86 °C, so the limit does not bind | `[estimate]` |
| `thermal_storage_tank_ua_w_per_k` | 1.0e-3 per kg of air | 3e-4 to 3e-3 | About 1.5 kW/K for a 10 000 m³ insulated hot-water store ([IEA-ES fact sheet](https://iea-es.org/wp-content/uploads/public/FactSheet_Thermal_Sensible_Water_2022-10-19.pdf)), divided by the 1.56e6 kg of air it serves | `[estimate]` |
| `storage_duration_hours` | 4 | 2-12 | The **standing time** of each tank between charge and discharge, not the discharge duration; one value applies to both tanks | `[estimate]` |
| `heat_user_supply_temperature_c` | 80 | 65-90 | Close to the measured Danish average supply of 78 °C; inside the 3rd-generation range (Sweden 86 °C, Germany 88 °C) | `[choice]` |
| `heat_user_return_temperature_c` | 40 | 35-55 | Danish guidance: return "should never exceed 40 °C" | `[project]` |
| `ambient_temperature_c` | 10 | 8.7-10.1 | Deutscher Wetterdienst, Bremen, 1991-2020 annual mean 9.8 °C ([DWD CDC](https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/multi_annual/mean_91-20/Temperatur_1991-2020.txt)); Elsfleth, next to Huntorf, 9.9 °C | `[datasheet]` |
| `ambient_relative_humidity` | 0.80 | 0.78-0.82 | DWD Klimatafel Bremen, mean of daily means ([DWD](https://www.dwd.de/DWD/klima/beratung/ak/ak_102240_kt.pdf)); a 1961-1990 normal | `[datasheet]` |
| `optimization_objective` | combined delivery | | The plant sells heat. The charge split is still chosen by exergy ([document 14](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md)) | |

### What the literature does not give

- **A total pressure-drop target for LTA-CAES.** Wolf and Budt 2014 and the
  Modelica paper of Budt, Wolf and Span 2012 contain no numeric pressure loss.
  Luo et al. 2016 is the best-supported source for a low-temperature A-CAES.
  At 1.5 % per exchanger, eight intercoolers compound to 11.4 % of the
  compressor discharge pressure; the model includes that compounding.
- **An air/water stage exchanger better than NTU 3.4** in any A-CAES design.
- **A measured per-stage isentropic efficiency** of an air-service IGC at
  60-100 bar: the value is converted from polytropic figures.
- **Any operating staged-extraction exchanger** in CAES service.

## 3. What the reference plant does

Solved with the current code (`python -m caes.cli`, no arguments):

| quantity | value |
|---|---:|
| compression work | 543.9 kJ/kg-air |
| expansion work | 304.9 kJ/kg-air |
| heat delivered at 80/40 °C | 261.4 kJ/kg-air |
| ambient heat drawn in | 30.9 kJ/kg-air |
| electrical round-trip efficiency | **56.1 %** |
| useful-exergy efficiency | 63.2 % |
| useful-energy delivery ratio `J` | 1.041 |
| net heat-pump COP (Carnot at 80/40 °C and 10 °C ambient: 6.7) | 1.09 |
| coolant inventory | 2.49 kg / kg air |
| cold / hot store | 35.5 °C / 85.7 °C |

**Against the literature.** The electrical efficiency lies inside the 52-60 %
published for LTA-CAES concepts (Wolf and Budt 2014; 55.5 % for KompEx).

**Where the compression heat goes.** Every joule of compression work ends up
as heat; the only question is where. Here 522 kJ/kg reach the store through
the intercoolers and 44 kJ/kg are lost in the cavern, where the air leaving
the last intercooler at 48 °C cools to the 10 °C ground. The intercooler
duties grow along the train (27 kJ/kg in the first, 64-78 in the others)
because only the first stage draws air at ambient temperature. Every later
stage draws air that its intercooler could cool only to about 48 °C, with a
cold store at 35.5 °C and exchangers of NTU 3.4, so it compresses warmer air,
does more work and releases more heat. The last intercooler carries the most
(78 kJ/kg) and is given the most water on purpose: whatever it does not take
becomes the cavern loss.

**Why `J` exceeds one.** Eight expansion stages send the tail interheater
returns below ambient; the dry cooler warms them back from the atmosphere
(31 kJ/kg-air), and by the identity of
[document 16](16_PERFORMANCE_LIMITS.md) that free heat is what lifts `J`
above one.

**Sensitivity.**

| variant | RTE | J | eta_ex |
|---|---:|---:|---:|
| reference (80/40 °C user) | 0.561 | 1.041 | 0.632 |
| user return 45 °C | 0.561 | 1.042 | 0.636 |
| pure water, 8 + 8 or 6 + 6 stages | infeasible: tail returns below freezing | | |
| earlier ambitious preset (100 bar, 8 + 8, 0.89/0.90, 1 % drops, NTU 3, 70/40 °C) | 0.623 | 1.031 | 0.679 |
| earlier conservative preset (60 bar, 6 + 4, 0.87/0.88, NTU 3, 75/40 °C, water) | 0.572 | 0.912 | 0.621 |

**Other concepts on these parameters.** The same site and machines do not
close as AD-CAES: at 10 °C ambient and 100 bar, ambient reheat cannot keep
the expander outlets above the anti-icing floor. Use
`--config heat_and_power_example_config.json --mode diabatic` (15 °C,
85.8 bar) to see AD-CAES. The electricity-only dispatch of the same hardware
still runs through the older coupled cold-loop solver.

## 4. Where the model and real machines differ

- **Constant storage pressure.** A real cavern swings between its minimum and
  maximum pressure during a cycle, and the turbine inlet is often throttled
  to a constant value, a loss the model does not represent.
- **Equal stage ratios.** Real LTA-CAES compressors raise the ratio in the last
  stages (Budt, Wolf and Span 2012, figure 12).
- **Coolant properties.** The loop is modelled with the heat capacity of
  water. A 30 % glycol mixture has about 10 % less, which would raise the
  inventory the solver reports by about as much.
- **Expander outlet floor.** The model holds every turbine outlet at 10 °C, or
  at the frost point plus 10 K. Vendors accept 0 °C as a hard limit.
- **The AD-CAES ambient exchanger** (`ambient_heat_exchanger_ntu`) was not
  part of this research and keeps its original value, 5.
