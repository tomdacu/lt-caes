# Physics and model boundary

## Boundary

The solver follows one kilogram of dry air through steady-flow components. The
air store is represented by a fixed storage pressure and an ambient-temperature
discharge state. Cavern pressure variation, tank geometry, equipment cost,
water pressurization, and time evolution are future model layers.

## Turbomachinery

CoolProp supplies real-air enthalpy and entropy. Compressor and turbine outlet
enthalpies follow isentropic-efficiency definitions:

```text
h2,compressor = h1 + (h2s - h1) / eta_c
h2,turbine    = h1 - eta_t (h1 - h2s)
```

Stage pressure ratios compensate exchanger pressure losses and reach the
specified storage and ambient pressures exactly.

## Two plant concepts

Both configurations use the same pressure-storage backbone.

```text
D-CAES: ambient -> compressors -> ambient coolers -> air store
        air store -> ambient reheaters -> expanders -> ambient

A-CAES: ambient -> compressors -> water intercoolers -> air store
        cold tank -> parallel IC branches -> hot tank
        hot tank -> parallel IH branches -> cold tank
        air store -> water interheaters -> expanders -> ambient
```

D-CAES ambient heat is reported explicitly. A-CAES water branches are mixed by
mass and energy balance; the hot-tank temperature is a result, not an input.

## Heat exchangers

### Pinch model

For each compression stage:

```text
T_air,out   = T_cold,in + pinch
T_water,out = T_air,in  - pinch
```

The water/air mass ratio is solved from the air enthalpy change and the water
energy balance. During discharge, the available hot-water mass is split equally
among the parallel interheaters; actual duty is limited by both terminal pinch
constraints.

### Specified effectiveness

```text
Q = epsilon C_min (T_hot,in - T_cold,in)
```

The normalized water/air ratio fixes the water capacity rate.

### Counterflow NTU

```text
NTU = UA / C_min
C_r = C_min / C_max
epsilon = [1 - exp(-NTU(1-C_r))] / [1 - C_r exp(-NTU(1-C_r))]
```

Because the analysis is normalized, NTU is the meaningful conductance input;
absolute area and flow are deferred to plant sizing.

## Two-tank balance and surplus

Parallel cold-water returns mix into one hot-tank state:

```text
M_w cp (T_hot - T_cold) = sum(Q_recovered,i)
```

After normalized storage loss, hot water is split among expansion stages. The
returned streams mix into the cold-side return state. Cycle energy closes as:

```text
Q_recovered = Q_storage_loss + Q_air_reheat + Q_surplus
```

Surplus may be rejected or exported as useful heat. This permits hot-water
energy to exceed expansion demand without forcing an artificial equality.

## Exergy

Air physical-flow exergy relative to the ambient dead state is:

```text
e = (h - h0) - T0 (s - s0)
```

For water with constant heat capacity:

```text
b(T) = cp [(T - T0) - T0 ln(T/T0)]
```

The model reports compressor, turbine, exchanger, cavern-equilibration,
hot-tank-mixing, storage-loss, and rejected-surplus exergy destruction.

```text
eta_electric = W_expansion / W_compression
eta_ex,useful = (W_expansion + B_useful_heat) / W_compression
```

## Limits

- Water uses constant specific heat and no pressure/saturation model.
- Tanks are perfectly mixed nodes, not time-dependent vessels.
- Equal water allocation is used across discharge interheaters.
- Compressor and turbine maps are represented by constant isentropic efficiency.
- T-s, T-h, and p-h plots connect the calculated stage outlet states; they are
  cycle traces, not fluid-property envelope diagrams.
