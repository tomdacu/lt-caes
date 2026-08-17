# LTHP-CAES cold-return recovery and cogeneration

> **Historical note:** the numerical rejection audit below describes the
> retired bidirectional, all-return E-303 model. The active architecture has
> one heat-only E-303 on an optimized sub-ambient return suffix and reports
> zero E-303 rejection. The old numbers are retained only as migration evidence,
> not as current performance. See [the active algorithm](../algorithms/cold_return_recovery.md).

This note answers two separate questions:

1. where the present LTHP-CAES still rejects heat;
2. which research directions can turn that residual into a useful product.

Citation counts are a bibliometric snapshot, not a quality score. The counts in
the ranked table were read from OpenAlex on 20 July 2026. Scopus, Web of
Science, Google Scholar and OpenAlex do not count exactly the same documents,
so the database and retrieval date must accompany every number.

## Retired E-303 audit

For `heat_and_power_example_config.json`, the water-side balance is:

```text
compression heat recovered in the TES       591.06 kJ/kg-air
TES heat returned to turbine air            309.66 kJ/kg-air
district heat exported through E-302        200.37 kJ/kg-air
historical heat rejected through E-303       66.77 kJ/kg-air
hot- and cold-tank standing losses           14.26 kJ/kg-air
```

The retired E-303 therefore rejected 11.30% of recovered compression heat in
that historical design. On the 70 MW compressor-shaft basis:

```text
dry-air mass flow              108.2 kg/s
E-303 heat                     approximately 7.23 MW
E-303 heat exergy              approximately 0.25 MW
```

The distinction was important. The retired E-303 rejected a large heat quantity, but only
`2.28 kJ/kg-air` of exergy because it cools the mixed return only from about
34.63 degC to 15.98 degC near a 15 degC environment. An ORC or another heat
engine is consequently a poor match: there is almost no temperature potential
from which to make work.

The active first-law closure is instead:

```text
Q_recovered + Q_E303,ambient =
    Q_turbine_reheat
  + Q_user
  + Q_tank_losses
```

The active solver never deletes a residual: if the turbines and user cannot
provide a heat sink, the configuration is infeasible rather than cooled by E-303.

## Routes considered for the retired rejection duty

### 1. Direct low-temperature heat export

The historical option was to replace the rejecting E-303 with a useful low-temperature exchanger before any
ambient cooler:

```text
mixed TES return -> E-303-LT useful heat exchanger -> cold TES
```

This is the simplest and usually best option when a coincident sink exists:

- fifth-generation district heating/cooling ambient loops;
- swimming pools or aquaculture;
- greenhouse root heating;
- ventilation or domestic-water make-up preheat;
- wastewater, industrial wash-water or low-temperature process preheat;
- seasonal borehole or aquifer thermal storage.

The historical 23.84 degC mixed-return example required a colder sink. The
active model uses finite NTU rather than a terminal-approach surrogate.

### 2. Upgrade E-303 heat with a heat pump

Use the TES return as the evaporator source:

```text
mixed TES return -> heat-pump evaporator -> cold TES
                              |
                              +-> condenser -> district heating
```

This directly performs the two duties required by the plant: it closes the
cold tank and exports useful heat. It is the most general route when the DH
return is warmer than the TES return.

The compressor electricity must be subtracted from net electric output and
included in every first-law and exergy denominator. As an illustration only,
recovering a 7.30 MW evaporator source with heating COP 4 would require about
2.43 MW electric input and deliver about 9.73 MW at the condenser. Real COP
must be calculated from evaporating/condensing temperatures, approaches,
part-load performance, defrost, pumps and auxiliaries.

A 2026 paper directly explores AA-CAES coupled with an absorption heat pump and
cascade waste-heat recovery:

- Jiang et al., *Integrated waste heat recovery in advanced adiabatic
  compressed air energy storage and absorption heat pump systems*,
  [DOI](https://doi.org/10.1016/j.est.2025.120115).

### 3. Preserve temperature levels instead of mixing them

The retired model mixed all interheater returns. Mixing is energy-conserving
but destroys exergy and creates one return temperature that may fit neither the
cold tank nor a heat user.

Higher-value layouts are:

- separate low-, medium- and high-temperature return headers;
- three or more TES tanks;
- a stratified thermocline tank with temperature-selective ports;
- cascaded PCM stores;
- route the coldest branch directly to cold TES and only warmer branches to
  DH or a heat-pump evaporator.

This is the strongest architectural improvement because it reduces both mixing
destruction and the E-303 duty before adding another conversion device.

### 4. Add a no-rejection dispatch constraint

The optimizer should eventually support:

```text
Q_E303 <= tolerance
```

or a multi-objective function such as:

```text
max[W_net + value_DH Q_DH + value_LT Q_LT - value_dump Q_E303]
```

This may reduce electrical output or high-temperature DH export. A
zero-rejection point is not guaranteed for every pressure, number of stages,
network-return temperature and coolant limit. The solver must report
infeasibility rather than silently discard heat.

### 5. Export cooling as a third product

Sub-ambient turbine exhaust has value in a CCHP architecture. Instead of using
all of it only to absorb ambient heat, part can serve a cooling network,
refrigerated warehouse or industrial cold load. The optimum then depends on
the relative values of electricity, high-temperature heat, low-temperature
heat and cooling.

### 6. Buffer heat when the user is unavailable

No-rejection operation requires a sink at the same time as the residual heat
unless a low-temperature buffer or seasonal store is added. A plant cannot
guarantee zero ambient rejection through all seasons merely by changing
control logic.

## Recommended next simulator architecture

The most defensible implementation sequence is:

1. split the current E-303 into `useful LT HX -> optional heat pump -> emergency
   ambient cooler`;
2. add a low-temperature heat-sink supply/return/approach;
3. add heat-pump source/sink approaches, COP map and auxiliary electricity;
4. add an economic multi-product objective with explicit parasitic/capital cost;
5. replace the mixed return with three temperature headers;
6. retain the emergency cooler for off-design and unavailable-heat-user cases.

The emergency cooler may have zero annual design duty without being physically
removed. This is safer than assuming a heat network can always accept energy.

## Most-cited papers in the relevant research cluster

### Direct AA-CAES / A-CAES cogeneration papers

| OpenAlex citations, 20 Jul 2026 | Paper | Why it matters |
|---:|---|---|
| 78 | Li, Miao, Yin, Han et al. (2019), *Combined Heat and Power dispatch considering Advanced Adiabatic Compressed Air Energy Storage for wind power accommodation*. [DOI](https://doi.org/10.1016/j.enconman.2019.112091), [OpenAlex record](https://openalex.org/W2977641756) | Direct AA-CAES CHP dispatch model, off-design behavior, wind accommodation and heat-power coordination. |
| 58 | Han, Sun and Li (2020), *Thermo-economic analysis and optimization of a combined cooling, heating and power system based on advanced adiabatic compressed air energy storage*. [DOI](https://doi.org/10.1016/j.enconman.2020.112811), [OpenAlex record](https://openalex.org/W3015607515) | Central CCHP AA-CAES paper; compares five TES heat-allocation modes and performs multi-objective optimization. |
| 52 | Li, Hu, Sun and Han (2021), *Thermodynamic and economic performance analysis of heat and power cogeneration system based on advanced adiabatic compressed air energy storage coupled with solar auxiliary heat*. [DOI](https://doi.org/10.1016/j.est.2021.103089), [OpenAlex record](https://openalex.org/W3194238164) | Examines heat allocation, exergy, economics and solar auxiliary heat. |
| 17 | Zhang, Zhang, Ma, Wen et al. (2021), *Cogeneration compressed air energy storage system for industrial steam supply*. [DOI](https://doi.org/10.1016/j.enconman.2021.114000), [OpenAlex record](https://openalex.org/W3139092814) | Extends adiabatic CAES cogeneration from hot water to industrial dry steam and reports 89-95% energy efficiencies for its selected product boundary. |
| 4 | Jiang, Meng, Li, Wang et al. (online 2025 / volume 2026), *Integrated waste heat recovery in advanced adiabatic compressed air energy storage and absorption heat pump systems*. [DOI](https://doi.org/10.1016/j.est.2025.120115), [OpenAlex record](https://openalex.org/W7117536391) | The closest paper found to the proposed E-303 heat-pump route; too recent for citation count to indicate importance. |

### Highly cited adjacent papers that define the district-energy problem

| OpenAlex citations, 20 Jul 2026 | Paper | Scope caveat and relevance |
|---:|---|---|
| 107 | Safaei, Keith and Hugo (2013), *CAES with compressors distributed at heat loads to enable waste heat utilization*. [DOI](https://doi.org/10.1016/j.apenergy.2012.09.027), [OpenAlex record](https://openalex.org/W2075425626) | Not classical AA-CAES, but the most-cited paper in this selected heat-utilization cluster. It establishes heat-load location and pipeline distance as economic constraints. |
| 96 | Bagdanavicius and Jenkins (2014), *Exergy and exergoeconomic analysis of a CAES combined with a district energy system*. [DOI](https://doi.org/10.1016/j.enconman.2013.09.063), [OpenAlex record](https://openalex.org/W2053730678) | CAES plus thermal storage and district heat; a direct foundation for separating heat energy from useful heat exergy. |
| 73 | Arabkoohsar, Dremark-Larsen, Lorentzen and Andresen (2017), *Subcooled compressed air energy storage system for coproduction of heat, cooling and electricity*. [DOI](https://doi.org/10.1016/j.apenergy.2017.08.006), [OpenAlex record](https://openalex.org/W2744645657) | Not the same two-tank AA-CAES architecture, but highly relevant to Denmark, district energy and treating cold as a product. Aarhus University currently reports 75 Scopus citations, illustrating database variation. |

## What this literature says about the proposed plant

The literature strongly supports multi-product AA-CAES, heat-allocation
optimization, district-energy coupling and heat-pump integration. The
repository's specific sequence remains distinctive:

```text
high-grade E-302 DH export
-> ambient preheat of sub-ambient expansion air
-> minimum TES turbine duty
-> low-grade E-303 recovery or heat-pump upgrade
```

The research opportunity is not to claim that "no one has used AA-CAES for
cogeneration." That field is established. The publishable question is whether
temperature-level-preserving TES plus two-grade heat export and ambient
assistance can outperform the usual single-mixed-TES heat-allocation schemes
after all pump, fan, heat-pump and network constraints are counted.
