# LTAHP-CAES literature and the Denmark opportunity

This note distinguishes what has already been explored from what is specific to
the LTAHP-CAES model in this repository.

## What is established

| Topic | Evidence | Relevance |
|---|---|---|
| Low-temperature A-CAES with liquid TES | Wolf and Budt, *LTA-CAES - A low-temperature approach to Adiabatic Compressed Air Energy Storage*, Applied Energy 125 (2014). [DOI](https://doi.org/10.1016/j.apenergy.2014.03.013) | Foundation for staged water-based heat recovery and reuse before expansion. |
| CAES plus district-energy heat recovery | Kim et al., *Exergy and exergoeconomic analysis of a Compressed Air Energy Storage combined with a district energy system*. [Publisher page](https://www.sciencedirect.com/science/article/pii/S0196890413006493) | Direct precedent for valuing compression heat in a district network. |
| Locating compressors near heat loads | Safaei, Keith and Hugo, *CAES with compressors distributed at heat loads to enable waste heat utilization*. [Paper PDF](https://davidkeith.earth/wp-content/uploads/2023/10/156.safaei.keith_.hugo_.caes_.e.pdf) | Shows that heat location and network coupling are central economic constraints. |
| AA-CAES combined heat and power | *Analysis of compression/expansion stage on compressed air energy storage cogeneration system*. [Open paper](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2023.1278289/full) | Establishes multi-stage AA-CAES/CHP as an active research category. |
| AA-CAES and district-network dispatch | *Stochastic optimal dispatch of combined heat and power integrated AA-CAES power station considering thermal inertia of DHN*. [Publisher page](https://www.sciencedirect.com/science/article/abs/pii/S0142061522001892) | Shows the value of district-network thermal inertia in system dispatch. |
| CAES-based combined cooling, heat and power | *Thermo-economic analysis and optimization of a combined cooling, heating and power system based on advanced adiabatic compressed air energy storage*. [DOI record](https://doi.org/10.1016/j.enconman.2020.112811) | Broader precedent for treating electricity, heat and cold as joint products. |

## What appears less explored

The literature above covers compression-heat sales, AA-CAES cogeneration,
district-network dispatch, and CAES-based combined cooling/heating/power.

The specific control sequence implemented here is narrower:

1. store compression heat in a pressurized low-temperature liquid TES;
2. export the maximum feasible high-temperature fraction through a series DH
   exchanger before turbine reheating;
3. use TES heat for the moisture-safe turbine duty and nothing else - there is
   no ambient exchanger on the adiabatic air side;
4. optimize `(electricity + DH heat) / charging electricity`;
5. separately report first-law and exergy efficiencies so a delivery ratio
   above 100% is not mislabeled.

Based on the sources reviewed, this exact combination is not yet a standard,
well-benchmarked CAES architecture. That is an inference from the literature
map, not a claim that no unpublished or differently named design exists.

## Why Denmark is a credible case study

Denmark combines three relevant assets.

### 1. A large district-heating sector

The Danish Energy Agency reports that collective heat supply serves about 80%
of homes and identifies district heating, cogeneration, heat pumps and electric
boilers as core parts of the heat system.

- [Danish Energy Agency: Heat](https://ens.dk/en/supply-and-consumption/heat)
- [Danish Energy Agency: electrification of heat, 2025](https://ens.dk/presse/ud-med-fossile-br%C3%A6ndsler-varmeforsyningen-i-danmark-bliver-mere-elektrisk)

The Agency reported that large heat pumps and electric boilers increased their
contribution by 17% from 2023 to 2024 and supplied nearly 10% of total district
heat in 2024. This demonstrates an existing market for electricity/ambient-heat
sector coupling.

### 2. High and variable wind generation

The IEA identifies Denmark among systems that can experience very low or
negative net load during high renewable output and low demand, increasing the
value of flexible loads and long-duration storage.

- [IEA Electricity 2026: Flexibility](https://www.iea.org/reports/electricity-2026/flexibility)
- [IEA Denmark 2023 review](https://www.iea.org/reports/denmark-2023/executive-summary)

The IEA also cites Aarhus electric boilers as an example of district heating
absorbing surplus wind electricity while supporting grid stability.

- [IEA: Opportunities for district heating](https://www.iea.org/commentaries/opportunities-for-district-heating-in-the-changing-energy-landscape)

### 3. Salt-cavern potential

GEUS has assessed renewable-electricity storage in salt caverns in southern
Jutland and Schleswig, explicitly including compressed air. Lille Torup in
northern Jutland already has seven solution-mined gas-storage caverns.

- [GEUS: renewable electrical-energy storage in salt caverns](https://pub.geus.dk/da/publications/assessing-the-potential-for-storage-of-renewable-electrical-energ/)
- [GEUS: Lille Torup cavern setting](https://pub.geus.dk/da/publications/potential-for-brine-storage-near-the-gas-storage-facility-at-lill/)

Energinet planning assumptions have also explicitly considered a CAES plant,
while warning that electricity-storage deployment remains geographically and
technologically uncertain.

- [Energinet planning assumptions, 2023 PDF](https://energinet.dk/media/eokdr5zh/fra-analyseforudsaetninger-til-netplanlaegningsforudsaetninger-oktober-2023.pdf)

## Hypothesis for a Danish demonstration

A promising screening case would co-locate:

- a suitable Jutland salt cavern;
- a district-heating transmission node with low return temperature;
- high-wind-price volatility and congestion exposure;
- space for pressurized TES tanks and ambient air exchangers.

The plant could buy electricity during high-wind/low-price periods, store
compressed air and compression heat, and later provide:

- dispatchable electricity;
- scheduled district heat;
- grid balancing and reserve services.

The concept competes with simpler large heat pumps plus hot-water storage and
with batteries for short-duration electricity balancing. Its plausible niche
is therefore not heat production alone. It must monetize the shared cavern,
long-duration electrical storage, district heat, and ancillary services.

## Antifreeze screening

Commercial inhibited glycol-water fluids can lower the freezing point well
below 0 degC, but their properties differ materially from water. Dow engineering
data show that freeze protection depends strongly on glycol concentration and
provide concentration-specific density, viscosity, conductivity, heat capacity,
freezing and boiling data.

- [Dow DOWTHERM SR-1 engineering guide](https://petroleumservicecompany.com/content/pdfs/DOWTHERMSR-1ENGINEERINGANDOPERATIONMANUAL.pdf)

Ethylene glycol is toxic and requires containment; propylene glycol is commonly
selected where incidental human contact is a concern. Both require inhibited
industrial formulations, corrosion control, concentration monitoring and
blend-specific hydraulic sizing.

The simulator's negative coolant-freezing input is therefore a sensitivity
constraint, not a completed glycol property package.

## Research questions worth publishing

1. Does ambient preheat increase annual LTAHP-CAES revenue after fan power and HX
   capital cost?
2. Which DH supply/return temperatures maximize heat export without destroying
   electrical value?
3. How does a stratified or multi-level TES compare with the present mixed
   two-tank loop?
4. Is glycol worthwhile after its lower heat capacity and higher pump work are
   included?
5. What cavern pressure schedule maximizes joint electricity and heat revenue?
6. How does DH thermal inertia change optimal charge/discharge timing?
7. At what duration does LTAHP-CAES outperform batteries plus a separate heat pump?
