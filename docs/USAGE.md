# Usage

## Command line

```powershell
python -m caes.cli
python -m caes.cli --mode diabatic
python -m caes.cli --config counterflow_example_config.json
python -m caes.cli --config optimization_example_config.json
python -m caes.cli --config useful_heat_example_config.json
python -m caes.cli --plot artifacts/cycle.png
```

Add `--explain-config` to print which fields are active and dormant under the
selected model. Generate a clean starting file with:

```powershell
python -m caes.cli --write-default-config my_config.json
```

## Desktop application

```powershell
python -m caes.gui
```

The application provides:

- logic blocks for plant concept, machinery, heat exchangers, water flow, and
  thermal surplus;
- automatic disabling of irrelevant inputs;
- auto-run after valid changes;
- live T-s, T-h, and logarithmic p-h cycle plots;
- stage tables with air/water states and exergy destruction;
- normalized efficiency, exergy, and surplus-heat results.

## Typical workflows

### Ideal pinch study

Choose `adiabatic` and `pinch`. Enter the cold-tank temperature and terminal
pinch. The solver determines the water required by every parallel compression
heat exchanger. Effectiveness, NTU, and water-ratio fields are dormant.

### Specified-effectiveness study

Choose `effectiveness`, then enter exchanger effectiveness and either a
specified water/air mass ratio or one of the optimization objectives.

### Counterflow NTU study

Choose `counterflow_ntu`, enter NTU, and select the normalized water-flow mode.
Effectiveness is calculated from NTU and the air/water heat-capacity-rate ratio.

### Compare D-CAES and water LTA-CAES

Keep machinery, pressure, and stage inputs unchanged and switch only `mode`.
The same compressor/storage/expander backbone is retained. D-CAES sends
compression heat to ambient; A-CAES routes it through the two-tank water loop.

## Interpreting efficiency

- Electrical RTE is expansion work divided by compression work.
- Total useful exergy efficiency adds the exergy of exported useful heat.
- Thermal energy is never added directly to electrical work.
- Results are normalized per kilogram of air; they are not a power rating.
