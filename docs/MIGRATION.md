# Migration and corrections

## New project layout

```text
caes_storage/
├── caes/          # one tested simulation package
├── docs/          # assumptions, theory, and usage
├── tests/         # physics and regression tests
├── pyproject.toml # packaging and test configuration
└── README.md
```

The earlier `CAES_preview` scripts and the previous `CAES_program` repository
are intentionally removed after this migration. Their code combined exploratory
plots, duplicated component models, and incompatible package roots.

## Material corrections from the former model

1. Heat storage is now finite and energy balanced; it is no longer inferred
   from the maximum compressor-outlet temperature.
2. Intercoolers cannot add heat to air. Inactive exchangers throttle
   isenthalpically across their pressure loss.
3. Thermal-store heat delivery is limited by both pinch temperature and
   remaining stored energy.
4. The final aftercooling/cavern-equilibration step is not falsely recovered
   into an already-hot, well-mixed water store.
5. D-CAES external reheat is explicit and its shaft-work ratio is not labelled
   a closed round-trip efficiency.
6. Pressure-loss compensation reaches the requested final storage and exhaust
   pressures exactly.
7. The public entry point is a reproducible CLI rather than modules with
   simulation loops running at import time.

## Deliberate removals

The obsolete Tk GUIs, generated images, duplicate legacy modules, and
unverified exergy/Sankey outputs are not carried over. A reliable thermal and
energy model is a prerequisite for reintroducing richer visualization or a GUI.
