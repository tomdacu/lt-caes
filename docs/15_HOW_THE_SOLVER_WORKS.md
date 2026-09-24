# How the solver works, from first principles

> **Parent:** [Documentation map](00_DOCUMENTATION_MAP.md)  
> **Audience:** an engineer from outside energy storage, or a student at the end of a bachelor's degree who knows thermodynamics, heat exchangers and a little numerical analysis. No prior knowledge of compressed-air storage is assumed.  
> **Deeper detail:** [Solver workflow](04_OPTIMIZATION_WORKFLOW.md) · [Reduction and charge split](14_HEAT_USER_REDUCTION_AND_CHARGE_SPLIT.md) · [Algorithm index](algorithms/README.md)

This page explains what the program computes and why it computes it in this
order. It follows one plant, the LTAHP reference configuration supplied with
the repository, and uses its real numbers throughout.

## 1. The plant in one paragraph

Electricity drives a compressor that pushes atmospheric air into a storage
vessel or cavern at 85.8 bar. It does so in six stages, because compressing in
one step would heat the air to several hundred degrees. After each stage the
hot air passes through an **intercooler**, a counter-current heat exchanger,
where water taken from a **cold tank** absorbs the heat. All that warmed water
is collected in a **hot tank**. Hours later the process runs backwards: the
stored air expands through six turbines, and before each one it is reheated
by water from the hot tank in an **interheater**. Without that reheat the
expanding air would cool far below freezing and the moisture in it would ice
the machine. The water that leaves the interheaters returns to the cold tank,
and the loop is closed. In the LTAHP variant, part of the hot water's heat is
also **sold** to an external user, for example a district-heating network
that wants 80 °C water and returns it at 45 °C.

```text
 CHARGE (electricity in)                         DISCHARGE (electricity + heat out)

 air -> [C1] -> (IC1) -> [C2] -> ... -> cavern     cavern -> (IH1) -> [T1] -> (IH2) -> [T2] -> ... -> exhaust
               ^   |                                           ^   |
   cold tank --+   +--> hot tank ----> E-302 (heat sold) ----> E-304 (one bleed per stage) --+
       ^                                                                                      |
       +---- E-303 (ambient warms the coldest returns) <---- returns from the interheaters <--+

 [C] compressor stage   [T] turbine stage   (IC) intercooler   (IH) interheater
```

Everything is computed **per kilogram of air** that is stored and later
released. Multiplying by an air mass flow gives powers.

## 2. What is given and what is unknown

**Given** (the configuration): ambient temperature, pressure and humidity;
storage pressure; number of stages; isentropic efficiencies of the machines;
the "size class" of every heat exchanger; the coolant's allowed temperature
range; and, for LTAHP, the user's supply and return temperatures.

**Unknown** (what the solver must find):

| symbol | meaning | unit |
|---|---|---|
| `R` | total water circulated per kg of air: the size of the thermal store | kg water / kg air |
| `r_1 ... r_N` | how `R` is split among the N intercoolers | kg / kg |
| `T_c` | cold-tank temperature | K |
| `T_h` | hot-tank temperature | K |
| `m` | margin by which each interheater's water is hotter than it strictly needs to be | K |

**Asked:** the design with the best objective, by default the useful-energy
delivery ratio

```text
J = (W_exp + Q_user) / W_comp
    W_comp  electricity spent compressing
    W_exp   electricity recovered by the turbines
    Q_user  heat sold to the user
```

The design must respect every physical limit, and if none does, the solver
must say which limit is responsible.

## 3. The building blocks

### 3.1 A compressor or turbine stage

Given the inlet state and the outlet pressure, an ideal (isentropic) stage
would reach an outlet enthalpy `h_s`. A real one is characterized by its
isentropic efficiency `eta`:

```text
compressor:  h_out = h_in + (h_s - h_in) / eta        work in  = h_out - h_in
turbine:     h_out = h_in - eta (h_in - h_s)          work out = h_in - h_out
```

Air is treated as a real fluid (CoolProp's reference equation of state),
because at 85-300 bar the ideal-gas law is noticeably wrong.

### 3.2 A counter-current heat exchanger of a given class

Each exchanger uses the effectiveness-NTU method. With the heat capacity rates
`C = (mass flow) x cp` of the two streams, `C_min` the smaller, and
`Cr = C_min / C_max`,

```text
eps = (1 - exp(-NTU (1 - Cr))) / (1 - Cr exp(-NTU (1 - Cr)))
Q   = eps * C_min * (T_hot,in - T_cold,in)
```

`NTU = UA / C_min` is fixed by the configuration (5 by default). That is a
deliberate choice for a screening tool: a fixed NTU means "an exchanger of this
performance class", resized for every candidate (`UA = NTU C_min`). It is not
one physical exchanger operated off-design.

The exchanger is used in two directions:

- **forward**: water flow given, compute the heat transferred (intercoolers);
- **inverse**: heat required, compute the water flow that delivers it
  (interheaters). The heat transferred grows monotonically with the flow and
  saturates, so a bracketed one-dimensional root finds the flow.

### 3.3 The anti-icing rule fixes what each turbine needs

Stored air still carries a trace of water vapour. If a turbine outlet is too
cold, that vapour condenses or freezes on the blades. Every turbine outlet must
therefore stay above a floor: 10 °C while liquid water can form, otherwise the
local frost point plus 10 K. Working backwards through each turbine gives the
air temperature `T_d,g` that interheater `g` must produce, and hence its
**minimum duty**. These numbers depend only on the pressures, the turbine
efficiency and the stored humidity. They do not depend on either tank.

For the reference plant the six demands are 65.9, 61.2, 50.9, 41.2, 32.1 and 23.6 °C.
They fall along the train because each later stage starts from colder air.

### 3.4 The extraction ladder (E-304) and the margin `m`

The turbines need water only a little hotter than their demands, and the
demands fall from stage to stage. Feeding every interheater from the hot tank
at 112 °C would waste temperature on the tail stages, temperature the heat
user would have paid for. So the hot water first gives the user its share in
**E-302**, then flows down a single counter-current body, **E-304**, from which
one bleed is withdrawn per stage, each at

```text
T_supply,g = T_d,g + m          (the same margin m for every stage)
```

For a given `m`, the inverse exchanger of 3.2 gives the flow `b_g` each stage
needs. A larger margin means hotter water, so each stage needs less of it. The
total is therefore strictly decreasing in `m`, and exactly one `m` makes the
bleeds use the whole store:

```text
f(m) = sum_g b_g(T_d,g + m) - R = 0
```

That is a monotone scalar equation, solved by a bracketed secant method. Once
`m` is known, so is everything the user receives: E-302 takes the water from
the hot-tank temperature down to the first extraction.

### 3.5 E-303: free heat from the atmosphere

Some interheater returns come back **colder than the ambient air**. From the
second stage on, the air reaching an interheater is the previous turbine's
exhaust, sitting on the anti-icing floor (down to about -16 °C at the
reference plant), and in a counter-current exchanger the water leaves close
to the air's inlet temperature. E-303 lets the atmosphere warm those returns before they reach the cold
tank. That heat is free, and it is one reason `J` can exceed one. Which
returns should pass through E-303? The colder a return, the more heat it can
pick up, so the best group is always "the k coldest". Sorting the returns once
and trying the N thresholds finds the optimum, instead of trying all 2^N
subsets.

## 4. The difficulty: everything depends on everything

Put the blocks together and the plant forms a loop:

```text
T_c --> charge train --> T_h --> discharge --> returns --> E-303, E-304, tank --> T_c
```

To compute the charge you need the cold-tank temperature, which is set by the
water coming back from the discharge. The discharge needs the stored heat,
which comes from the charge. The natural approach, and the one the program
used until 2026-09, treats `T_c` as unknown: guess it, go round the loop,
compare what comes back with the guess, and iterate on that residual with a
root finder. And that has to be repeated for every candidate `R`.

That works, but it is expensive and fragile:

- each guess costs a full charge and discharge simulation;
- when a candidate `R` is infeasible, proving it means sweeping the entire
  range of possible `T_c` and finding no root: about 900 simulations, 14 s,
  for a single rejected `R`;
- a root finder that finds nothing cannot say *why*, so the user was told
  "no design found; nonexistence is not certified".

## 5. The key observation: the loop is not really a loop

Look again at section 3. The turbine demands (3.3) do not depend on the tanks.
The ladder equation `f(m) = 0` (3.4) contains `R` and those demands, and
nothing else. The hot-tank temperature appears only as a check, "is the hot
tank hotter than the first extraction?", never inside the equation. So for a
given `R`:

```text
R  -->  m  -->  returns  -->  E-303, E-304, tank dwell  -->  T_c        (no guess needed)
                                                              |
                                                              v
                                              charge train at that T_c  -->  T_h, W_comp
```

The cold-tank temperature is an **explicit function** of `R`, not the root of
an equation. This was checked numerically: feeding the old residual guesses of
5, 15, ... 55 °C always returned exactly the same cold tank, 37.4726 °C at
`R = 1.5`. The dependence the old method was iterating on does not exist.

One subtlety: the stored humidity comes from the charge side, and the turbine
demands depend on it. The air is always cooled to ambient temperature in the
cavern, so the humidity is fixed there and does not change with `T_c`. The
program still checks this and repeats the chain if it did change. In every
case examined it never has.

**Consequence: for this kind of plant the whole problem has one design
variable, `R`**, apart from the charge split, discussed in section 7.

## 6. Searching along `R`

Why does `R` matter at all? More water means the intercoolers cool the air
better, so the next compressor works less. But the same heat spread over more
water means a cooler hot tank, and a cooler store is worth less to the heat
user and closer to the turbines' needs. `R` is the classic trade-off between
quantity and temperature grade.

Along `R`, the reference plant looks like this:

```text
R (kg/kg)   0.375        0.46 - 0.71              0.88 - 2.07          2.56 - 3.92         4.85 - 6.0
            too little   coolant exceeds 200 °C   FEASIBLE             E-304 too small     store too cold
            water        in the intercoolers                           for the ladder      for the user's 80 °C
```

and inside the feasible band `J(R)` is a smooth hump:

```text
R      1.20    1.40    1.60    1.69    1.80    2.00
J      1.027   1.059   1.074   1.074   1.074   1.069       (capacity-matched split)
```

The search follows that picture:

1. **Scan.** Evaluate about fourteen values of `R` spaced geometrically (25 %
   apart) around a physical reference, a quarter of a kilogram of water per
   stage. Each point is either feasible, with its `J`, or refused, with the
   *name* of the constraint that refused it. This is cheap: a point costs
   about 0.1-0.3 s.
2. **Look between different refusals.** If one point is refused by, say, the
   freezing limit and its neighbour by E-304's size, a narrow feasible window
   may lie between them, where one limit has relaxed and the other has not yet
   bitten. Bisect there. Two neighbours refused by the *same* limit give no
   such reason to look.
3. **Refine.** Take the best feasible point. If a neighbour is infeasible,
   bisect to the boundary. If `J` is still rising at the boundary, the
   boundary is the answer: this is typical with a hot user, where the best
   plant is the one that just satisfies the user's exchanger. Otherwise the
   maximum is inside, and Brent's method (golden-section search with parabolic
   steps) finds it.
4. **Report.** If nothing is feasible, the scan itself is the explanation: a
   list such as "R 0.1-0.67 too little water; R 0.74-3.0 coolant above its
   limit; R 3.06-27 E-304 too small". When two limits cross like that, no
   amount of searching will help, and the designer knows which input to relax.

On the configurations that used to take one to five minutes, this takes
2-10 seconds ([benchmarks](10_BENCHMARKS_AND_REGRESSION.md)).

## 7. The one other freedom: how to split the water among the intercoolers

The total `R` is fixed, but how much goes to each intercooler is not. The
default rule is **capacity matching**: give each intercooler the flow whose
heat capacity equals the air's, so that the air and water temperature lines in
the exchanger run parallel. That is the textbook recipe for an efficient
counter-current exchanger.

Is it the best choice for the plant as a whole? An exact energy balance over
the whole plant answers this. For every design,

```text
W_exp + Q_user = W_comp + Q_amb + (h_intake - h_exhaust) - Q_ac - L_tank

Q_amb       free heat from E-303
h_intake - h_exhaust   the exhaust leaves colder than the intake: also free energy
Q_ac        heat lost when the air leaving the LAST intercooler cools to ambient in the cavern
L_tank      heat lost by the tanks while waiting
```

Two things follow.

- The last intercooler is special. Whatever heat it fails to capture is lost
  in the cavern (`Q_ac`). Giving it more water is worth more than capacity
  matching suggests.
- The objective `J` weighs sold heat exactly like electricity. The identity
  shows that a plant with `J < 1` can raise `J` just by spending more
  electricity in the compressor and selling the result as heat, which is what
  an electric kettle does, with `J = 1`. Letting `J` choose the split does
  exactly that: at 30 bar with 3 stages it switched the first intercooler off,
  gaining 3 points of `J` and losing 4.5 points of round-trip efficiency.

So the split is chosen by **exergy**, which values heat at its thermodynamic
worth. For water heated from 45 to 80 °C that worth is only 14 % of its
energy (`theta = 1 - T0 ln(T_s/T_r)/(T_s - T_r)`). Exergy never rewards burning
electricity into warm water. Numerically:

- with a **mild user (80/45 °C)** capacity matching is already optimal to
  within 0.02 points;
- with a **hot user (95/75, 110/90 °C)** the optimum switches the first
  intercooler off, so the first stage's heat passes into the second
  compressor and leaves hotter, and gives the last intercooler 30-40 % more
  water.

The program therefore adjusts only those two branches, the first and the
last, keeping the capacity-matched shape of the others. Each adjustment is a
one-dimensional search that needs only the charge train (2 ms per trial), so
it is repeated at every `R` the outer search visits. Freeing all N branches was
measured to add at most 0.3 points, by switching off every other intercooler,
which describes a different machine rather than a better split.

## 8. When there is no heat user

Without a heat user (LTA-CAES), or when the objective is electricity only, all
the stored heat goes to the turbines, as much as they can use. The discharge
then *does* depend on the hot-tank temperature, and the hot tank depends on the
cold tank. The loop of section 4 is real, `T_c` is a genuine root, and the
older coupled solver is still used. Making that case fast is the next piece of
work ([performance](09_PERFORMANCE_AND_OPTIMIZATION.md#current-bottleneck-and-next-safe-work)).

## 9. How the answer is checked

A solver that finds numbers is not enough. Each accepted design is rebuilt
completely and checked:

- every component satisfies its own steady-flow energy balance (residual
  below 10^-5 J/kg);
- the water leaving the charge equals the water entering the discharge, to a
  tolerance derived from a 1 J/kg energy budget;
- the cold tank the loop produces equals the one the charge used, to 0.5 mK;
- every turbine outlet respects the anti-icing floor;
- every exchanger respects its effectiveness limit, and E-304 is checked zone
  by zone, because its flow drops at every bleed;
- the whole-plant exergy balance closes: work in = work out + exergy of the
  heat sold + exergy destroyed + exergy lost, with a residual below 1 J/kg.

Nearly 300 automated tests exercise these checks across the three plant
concepts.

## 10. Glossary

| term | meaning |
|---|---|
| CAES | compressed-air energy storage |
| AD / LTA / LTAHP | ambient diabatic / low-temperature adiabatic / low-temperature adiabatic heat and power |
| intercooler, interheater | exchangers between compressor stages (cooling) and before turbine stages (heating) |
| E-302 | the exchanger that sells heat to the external user |
| E-303 | the exchanger that lets the atmosphere warm the coldest returning water |
| E-304 | the counter-current body that bleeds water to each interheater at a matched temperature |
| NTU | number of transfer units, `UA / C_min`: the exchanger's size class |
| effectiveness | actual heat transferred / the maximum the inlet temperatures allow |
| capacity matching | equal heat-capacity rates on both sides of an exchanger |
| exergy | the part of energy that could be turned into work; for heat at temperature T it is `Q (1 - T0/T)` |
| `R` | kg of water circulated per kg of air stored |
| `J` | useful-energy delivery ratio, `(W_exp + Q_user) / W_comp` |
