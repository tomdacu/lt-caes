"""Named plant configurations.

``REALISTIC_REFERENCE`` is what the desktop application opens with and what
"Reset defaults" and the command line (without ``--config``) use: a large
(tens of MW) LTAHP-CAES plant with typical published component values. A few
values are design choices of the project and are marked as such. The sources
and the reasoning behind each number are in
docs/17_REALISTIC_REFERENCE_PARAMETERS.md.

``PlantConfig()`` keeps its own field defaults on purpose: they are the fixed
numerical baseline the test suite is written against, not a plant claim.
"""

from __future__ import annotations

from .config import HeatOfftake, OptimizationObjective, PlantConfig, PlantMode

REALISTIC_REFERENCE = PlantConfig(
    mode=PlantMode.ADIABATIC,
    # Site: North-German salt-cavern region (DWD Bremen 1991-2020 mean 9.8 °C;
    # mean relative humidity 80 %).
    ambient_temperature_c=10.0,
    ambient_pressure_bar=1.01325,
    ambient_relative_humidity=0.80,
    # Salt cavern at the lower end of the LTA-CAES design window
    # (Budt/Wolf/Span 2012: 100-152 bar; KompEx: 40-100 bar).
    storage_pressure_bar=100.0,
    # Design choice: equal stage counts. Eight integrally geared compression
    # stages as in the LTA-CAES compressor; the expander gets the same count
    # (two four-stage integrally geared gearboxes).
    compressor_stages=8,
    expander_stages=8,
    # Design choice: per-stage isentropic 0.86 / 0.85, inside the published
    # IGC (0.85-0.89) and radial-expander (0.80-0.92) bands.
    compressor_efficiency=0.86,
    expander_efficiency=0.85,
    # 1.5 % per exchanger, charge and discharge alike (Luo et al. 2016 base
    # value for a low-temperature A-CAES).
    intercooler_pressure_drop=0.015,
    interheater_pressure_drop=0.015,
    # Design choice: air/water stage exchangers at NTU 3.4, the top of the six
    # published A-CAES design points (2.83-3.41, Barbour et al. 2025).
    heat_exchanger_ntu=3.4,
    # Water-glycol loop (about 40 % glycol). With these machines the tail
    # interheater returns leave below 0 °C, which pure water cannot take (no
    # feasible design with water, 6+6 or 8+8). The coldest return reaches
    # -11.3 °C; -25 °C keeps the freezing point 14 K clear of it. The glycol
    # caps the hot side at about 150 °C, which this plant does not reach.
    coolant_maximum_temperature_c=150.0,
    coolant_minimum_temperature_c=-25.0,
    # Dry cooler at a typical 5-9 K approach to ambient (IEA SHC Task 38).
    cold_return_cooler_ntu=0.8,
    optimization_objective=OptimizationObjective.MAX_COMBINED_ENERGY_DELIVERY,
    # Insulated hot-water store, about 1.5 kW/K per 10 000 m3, per 1.56e6 kg
    # of stored air.
    thermal_storage_tank_ua_w_per_k=1.0e-3,
    storage_duration_hours=4.0,
    # District heating: 80 °C supply (design choice), return 40 °C (Danish
    # guidance); a conventional substation exchanger.
    heat_offtake=HeatOfftake.HEAT_USER,
    heat_user_supply_temperature_c=80.0,
    heat_user_return_temperature_c=40.0,
    heat_user_exchanger_ntu=5.0,
    extraction_exchanger_ntu=8.0,
)
