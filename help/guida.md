# 📚 Guida Completa al Simulatore CAES (Compressed Air Energy Storage)

## 🎯 Panoramica del Programma
Questo simulatore calcola il comportamento termodinamico di un impianto CAES, analizzando i cicli di compressione ed espansione con metodi reali (non ideali) utilizzando la libreria CoolProp per proprietà accurate dell'aria.

---

## 📁 Struttura del Progetto

```
I_CAES/
├── main.py                 # 🚀 Script principale - punto di ingresso
├── config.py               # ⚙️  Parametri configurabili dell'impianto
├── specifications.py       # 🔄 Definizione sequenza componenti
├── plotting.py             # 📊 Visualizzazione grafici termodinamici
├── transformation/         # 📐 Formule termodinamiche
│   ├── compressor_formulas.py  # Compressione adiabatica reale
│   ├── expander_formulas.py    # Espansione adiabatica reale
│   ├── exchanger.py            # Scambiatori di calore
│   └── storage.py              # Modello di accumulo
└── help/                   # 📖 Documentazione
    ├── guida.md              # Questa guida
    ├── PROJECT_CHANGELOG.md # Storico versioni
    └── commit_history.log    # Log completo commit
```

---

## 🚀 Come Funziona il Programma - Step by Step

### 1️⃣ **Avvio e Configurazione**
```python
# In main.py - caricamento configurazione
config = load_config()
```
- Legge i parametri da `config.py`
- Imposta condizioni iniziali (pressioni, temperature, efficienze)

### 2️⃣ **Definizione Ciclo**
```python
# In specifications.py - costruzione ciclo
compression_sequence = [
    ('compressor', {...}),
    ('intercooler', {...}),
    ('compressor', {...}),
    ...
]
```
- Definisce l'ordine dei componenti
- Ogni componente ha parametri specifici

### 3️⃣ **Simulazione Ciclo di Compressione**
```python
# Processo per ogni compressore
1. Calcola stato ideale (isentropico)
2. Applica efficienza reale
3. Determina stato reale di uscita
4. Aggiorna proprietà per il prossimo componente
```

### 4️⃣ **Simulazione Ciclo di Espansione**
```python
# Processo per ogni espansore
1. Calcola espansione ideale
2. Applica efficienza reale
3. Determina stato reale di uscita
4. Aggiorna proprietà per il prossimo componente
```

### 5️⃣ **Calcolo Prestazioni**
```python
# Calcolo efficienza round-trip
efficienza = |Lavoro_espansione| / (Lavoro_compressione + Calore_fornito)
```

### 6️⃣ **Visualizzazione Risultati**
- Grafici T-s (Temperatura-Entropia)
- Grafici h-s (Entalpia-Entropia)
- Grafici P-h (Pressione-Entalpia)
- Report numerico su console

---

## ⚙️ Configurazione - File per File

### 🔧 **config.py** - Parametri Principali
```python
# Fluido di lavoro
FLUID = 'AIR'

# Condizioni ambientali
T_AMBIENT = 298.15  # K (25°C)
P_AMBIENT = 101325  # Pa (1 atm)

# Condizioni operative
P_IN_COMPRESSOR = 101325    # Pa - pressione ingresso compressione
P_OUT_COMPRESSOR = 70e5      # Pa - pressione massima accumulo
P_IN_EXPANDER = 70e5          # Pa - pressione ingresso espansione
P_OUT_EXPANDER = 101325       # Pa - pressione uscita espansione

# Efficienze componenti
ETA_COMPRESSOR = 0.85        # 85% efficienza compressori
ETA_EXPANDER = 0.88           # 88% efficienza espansori
```

### 🔄 **specifications.py** - Sequenza Componenti
```python
# Ciclo di compressione a 3 stadi con inter-refrigerazione
compression_sequence = [
    ('compressor', {'eta_is': 0.85, 'p_out': 3.5e5}),
    ('intercooler', {'T_out': 298.15}),
    ('compressor', {'eta_is': 0.85, 'p_out': 12e5}),
    ('intercooler', {'T_out': 298.15}),
    ('compressor', {'eta_is': 0.85, 'p_out': 70e5}),
]

# Ciclo di espansione a 3 stadi con riscaldamento
expansion_sequence = [
    ('heater', {'T_out': 1200}),
    ('expander', {'eta_is': 0.88, 'p_out': 12e5}),
    ('heater', {'T_out': 1200}),
    ('expander', {'eta_is': 0.88, 'p_out': 3.5e5}),
    ('heater', {'T_out': 1200}),
    ('expander', {'eta_is': 0.88, 'p_out': 101325}),
]
```

---

## 📐 Formule Termodinamiche Dettagliate

### 🔵 **Compressione Adiabatica Reale**
```python
# Stato 1: Ingresso compressore
T1, P1, h1, s1 = stato_iniziale

# Stato 2s: Uscita ideale (isentropica)
s2s = s1
h2s = PropsSI('H', 'P', P2, 'S', s2s, 'AIR')
W_is = h2s - h1

# Stato 2: Uscita reale
W_real = W_is / eta_is
h2 = h1 + W_real
T2 = PropsSI('T', 'P', P2, 'H', h2, 'AIR')
```

### 🔴 **Espansione Adiabatica Reale**
```python
# Stato 3: Ingresso espansore
T3, P3, h3, s3 = stato_iniziale

# Stato 4s: Uscita ideale (isentropica)
s4s = s3
h4s = PropsSI('H', 'P', P4, 'S', s4s, 'AIR')
W_is = h3 - h4s

# Stato 4: Uscita reale
W_real = W_is * eta_is
h4 = h3 - W_real
T4 = PropsSI('T', 'P', P4, 'H', h4, 'AIR')
```

### 🟡 **Scambiatori di Calore**
```python
# Inter-refrigeratore
T_out = T_target  # Imposta temperatura target
h_out = PropsSI('H', 'T', T_out, 'P', P_costante, 'AIR')

# Riscaldatore
T_out = T_target  # Imposta temperatura target
h_out = PropsSI('H', 'T', T_out, 'P', P_costante, 'AIR')
```

---

## 🎮 Guida all'Uso Pratico

### 📋 **Prima Esecuzione**
1. **Installazione dipendenze:**
   ```bash
   pip install CoolProp matplotlib numpy
   ```

2. **Esecuzione simulazione:**
   ```bash
   python main.py
   ```

3. **Output atteso:**
   ```
   === RISULTATI SIMULAZIONE CAES ===
   Lavoro compressione: 1234.5 kJ/kg
   Lavoro espansione: -987.6 kJ/kg
   Calore fornito: 456.7 kJ/kg
   Efficienza round-trip: 67.8%
   ```

### 🎯 **Modifica Parametri**
Per testare configurazioni diverse:

1. **Cambia pressioni:**
   ```python
   # In config.py
   P_OUT_COMPRESSOR = 100e5  # 100 bar invece di 70
   ```

2. **Aggiungi stadi:**
   ```python
   # In specifications.py
   compression_sequence = [
       ('compressor', {...}),
       ('intercooler', {...}),
       ('compressor', {...}),
       ('intercooler', {...}),
       ('compressor', {...}),
       ('intercooler', {...}),
       ('compressor', {...}),  # Nuovo stadio
   ]
   ```

3. **Cambia efficienze:**
   ```python
   # In config.py
   ETA_COMPRESSOR = 0.90  # 90% invece di 85%
   ```

### 📊 **Interpretazione Grafici**
- **Diagramma T-s:** Mostra l'aumento di entropia dovuto alle irreversibilità
- **Diagramma h-s:** Visualizza il lavoro scambiato nei componenti
- **Diagramma P-h:** Mostra le trasformazioni a pressione variabile

---

## 🔍 **Esempio Pratico - Ciclo Completo**

### Configurazione Test
```python
# Parametri di test
P_MAX = 70 bar
T_AMB = 25°C
N_STADI = 3
```

### Risultati Attesi
- **Efficienza:** 65-75% (tipica per CAES)
- **Lavoro specifico:** 800-1200 kJ/kg
- **Rapporto di pressione per stadio:** ~3.5:1

---

## 🚨 **Risoluzione Problemi Comuni**

### ❌ **Errore: "CoolProp not found"**
```bash
pip install CoolProp
```

### ❌ **Errore: "ValueError in PropsSI"**
Verificare che:
- Le temperature siano > 200 K
- Le pressioni siano > 1000 Pa
- Il fluido sia 'AIR'

### ❌ **Grafici vuoti**
Controllare che:
- I valori di pressione siano coerenti
- Le temperature non siano troppo basse

---

## 📞 **Supporto e Contatti**
Per domande o problemi, consultare:
- Questa guida
- I commenti nel codice
- La documentazione CoolProp
