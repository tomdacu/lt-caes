# Documentation map

> **Parent:** [project README](../README.md)  
> **Purpose:** start here and follow links toward implementation detail

This repository is a configuration brainstorming and screening tool for the two
forms of low-temperature adiabatic CAES, LTA (`heat_offtake = "none"`) and
LTAHP (`heat_offtake = "heat_user"`). A fixed
NTU selects an exchanger performance class; each candidate implicitly resizes
the exchanger as `UA_design = NTU_selected C_min,design`.

## Read by question

| Question | Canonical document | Deeper detail |
|---|---|---|
| What plants are represented? | [Plant concepts](01_PLANT_CONCEPTS_AND_ARCHITECTURES.md) | [Physics boundary](02_PHYSICS_AND_MODEL_BOUNDARY.md) |
| What is optimized? | [Theory and objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md) | [Metrics and exergy](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md) |
| How does the solver nest? | [Optimization workflow](04_OPTIMIZATION_WORKFLOW.md) | [Algorithm index](algorithms/README.md) |
| How is the trunk staged to the turbines? | [Extraction architecture](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md) | [Discharge solver and results](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md) |
| Where is E-303 placed? | [Cold-return recovery](algorithms/cold_return_recovery.md) | [Extraction architecture](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md) |
| What about direct hot-to-cold recuperation? | [Recuperator study, now delivered as E-304](13_HOT_TO_COLD_RECUPERATOR_STUDY.md) | [Extraction architecture](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md) |
| Why is a run slow? | [Performance](09_PERFORMANCE_AND_OPTIMIZATION.md) | [Benchmarks](10_BENCHMARKS_AND_REGRESSION.md) |
| Which fields are active? | [Configuration logic](05_CONFIGURATION_LOGIC.md) | [Usage](07_USAGE.md) |
| How are properties called? | [Property API and cache](algorithms/property_api_and_cache.md) | `caes/thermodynamics.py` |

## Theory and architecture

1. [Plant concepts and architectures](01_PLANT_CONCEPTS_AND_ARCHITECTURES.md)
2. [Physics and model boundary](02_PHYSICS_AND_MODEL_BOUNDARY.md)
3. [Objectives, metrics and exergy accounting](03_OBJECTIVES_METRICS_AND_EXERGY_ACCOUNTING.md)
4. [Theory and design objectives](11_THEORY_AND_DESIGN_OBJECTIVES.md)
5. [Moisture, dew point and wet expansion](06_MOISTURE_DEW_POINT_AND_WET_EXPANSION.md)
6. [Single-store extraction architecture (E-302 + E-304)](12_PROPOSED_COOLANT_CASCADE_ARCHITECTURE.md)
7. [Single-store TES, discharge solver and measured results](08_MULTILEVEL_TES_AND_THE_DISCHARGE_CASCADE.md)
8. [Hot-to-cold recuperator study, closed](13_HOT_TO_COLD_RECUPERATOR_STUDY.md)

## Solver and evidence

1. [Optimization workflow](04_OPTIMIZATION_WORKFLOW.md)
2. [Algorithm index](algorithms/README.md)
3. [Performance and optimization](09_PERFORMANCE_AND_OPTIMIZATION.md)
4. [Benchmarks and regression protocol](10_BENCHMARKS_AND_REGRESSION.md)
5. [Configuration logic](05_CONFIGURATION_LOGIC.md)
6. [Usage](07_USAGE.md)

## Research layer

- [Research map](research/README.md)
- [LTA-CAES literature](research/LITERATURE.md)
- [People, groups and related software](research/PEOPLE_AND_GROUPS.md)
- [LTAHP-CAES and Denmark](research/LTAHP_CAES_AND_DENMARK.md)
- [LTAHP heat rejection and cogeneration](research/LTAHP_CAES_HEAT_REJECTION_AND_COGENERATION.md)
