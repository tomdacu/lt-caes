# Guida al Simulatore di Impianti CAES (Compressed Air Energy Storage)

Questo documento fornisce una guida completa alla struttura, all'utilizzo e alle formule implementate nel simulatore di impianti CAES.

## Struttura del Progetto

Il codice è organizzato in moduli per garantire flessibilità e manutenibilità:

- **`main.py`**: È lo script principale che orchestra l'intera simulazione. Carica la configurazione, esegue i cicli di compressione ed espansione, calcola l'efficienza e avvia la visualizzazione dei risultati.

- **`config.py`**: Contiene tutti i parametri di configurazione dell'impianto. Modificando questo file, è possibile analizzare diversi scenari senza alterare la logica del codice. I parametri includono:
  - Proprietà del fluido di lavoro (es. `AIR`).
  - Condizioni operative (pressioni e temperature di ingresso/uscita).
  - Efficienze dei componenti (compressori, espansori).
  - Numero di stadi di compressione/espansione.

- **`specifications.py`**: Definisce la sequenza dei componenti per i cicli di compressione ed espansione. Questo permette di costruire cicli complessi (es. con inter-refrigerazione o riscaldamento) in modo modulare.

- **`transformation/`**: Questa directory contiene i moduli con le formule termodinamiche per ciascun componente:
  - **`compressor_formulas.py`**: Calcola la trasformazione adiabatica reale in un compressore.
  - **`expander_formulas.py`**: Calcola la trasformazione adiabatica reale in un espansore.
  - **`exchanger_formulas.py`**: Gestisce gli scambiatori di calore (inter-refrigeratori e riscaldatori).

- **`plotting.py`**: È responsabile della visualizzazione dei cicli termodinamici sui diagrammi T-s, h-s e P-h, utilizzando le proprietà reali del fluido.

## Formule Termodinamiche

Le trasformazioni sono calcolate utilizzando le proprietà reali del fluido di lavoro (aria) tramite la libreria `CoolProp`.

### 1. Compressione Adiabatica Reale

Il lavoro specifico richiesto dal compressore (`work_required`) è calcolato considerando un'efficienza isentropica (`eta_is`).

- **Stato di uscita isentropico (ideale)**:
  - `s_out_is = s_in`
  - `h_out_is = PropsSI('H', 'P', p_out, 'S', s_out_is, fluid)`

- **Lavoro isentropico**:
  - `work_is = h_out_is - h_in`

- **Lavoro reale**:
  - `work_real = work_is / eta_is`

- **Stato di uscita reale**:
  - `h_out_real = h_in + work_real`
  - Le altre proprietà (`T_out`, `s_out`) sono calcolate in base a `p_out` e `h_out_real`.

### 2. Espansione Adiabatica Reale

Il lavoro specifico prodotto dall'espansore (`work_produced`) è calcolato in modo analogo, usando l'efficienza isentropica dell'espansore.

- **Stato di uscita isentropico (ideale)**:
  - `s_out_is = s_in`
  - `h_out_is = PropsSI('H', 'P', p_out, 'S', s_out_is, fluid)`

- **Lavoro isentropico**:
  - `work_is = h_in - h_out_is`

- **Lavoro reale**:
  - `work_real = work_is * eta_is`

- **Stato di uscita reale**:
  - `h_out_real = h_in - work_real`
  - Le altre proprietà sono calcolate in base a `p_out` e `h_out_real`.

### 3. Scambiatori di Calore

Gli scambiatori di calore sono modellati come trasformazioni isobare (a pressione costante).
- **Inter-refrigeratore**: Raffredda il fluido fino a una temperatura target (es. `T_ambientale`).
- **Riscaldatore**: Riscalda il fluido fino a una temperatura target prima dell'espansione.

### 4. Efficienza di Round-Trip

L'efficienza complessiva dell'impianto è calcolata come il rapporto tra l'energia utile prodotta e l'energia totale consumata:

`Efficienza = |Lavoro Espansione| / (Lavoro Compressione + Calore Fornito)`

Dove:
- `Lavoro Espansione` è il lavoro netto prodotto dagli espansori (negativo per convenzione).
- `Lavoro Compressione` è il lavoro netto richiesto dai compressori (positivo).
- `Calore Fornito` è il calore totale aggiunto nei riscaldatori durante il ciclo di espansione.

## Utilizzo

1.  **Configurazione**: Aprire `config.py` e impostare i parametri desiderati per la simulazione.
2.  **Definizione Ciclo**: Se necessario, modificare `specifications.py` per cambiare la sequenza o il tipo di componenti.
3.  **Esecuzione**: Eseguire lo script `main.py` da un terminale:
    ```bash
    python I_CAES/main.py
    ```
4.  **Analisi Risultati**:
    - I risultati numerici (lavoro, efficienza) saranno stampati sulla console.
    - I diagrammi termodinamici (T-s, h-s, P-h) verranno visualizzati in finestre separate, mostrando i cicli di compressione ed espansione con processi colorati e stati numerati.
