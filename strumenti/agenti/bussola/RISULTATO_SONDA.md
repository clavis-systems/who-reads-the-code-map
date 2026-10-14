# Bussola: risultato della sonda (14/10/2026, 11:32–11:55)

Piano: PIANO_SONDA.md (commit 38f7478, congelato prima delle risposte). Dati: strumenti/risultati/bussola/
(sonda_risposte.jsonl, 2.167 risposte, 0 errori di rete, 4 risposte illeggibili; sonda_riassunto.json).

## Misura principale

- p̂ = 0,393 (613 domande rispondibili, 39 compiti; intervallo 95% ricampionando i compiti 0,337–0,451).
  Il caso, con lo stesso numero di opzioni, darebbe 0,310.
- Gruppi (errore bilanciato, due versioni della domanda insieme): file 0,355, classi 0,382, comunità 0,403.
- **Decisione secondo il piano: SI FERMA** (p̂ < 0,60 e nessun tipo di gruppo ≤ 0,15). Si passa all'idea di riserva
  (grafo della storia); questi dati restano per l'analisi "perché un modello da 4B non sa leggere una mappa del codice".

## Dettagli fissati nel piano (senza soglia)

- Sul nodo d'oro dice "è qui" l'87% delle volte, ma lo dice anche nel 47% dei nodi sbagliati.
- Per distanza dall'oro (1/2/3/4): 0,39 / 0,29 / 0,38 / 0,35, vicino al caso (0,26 / 0,31 / 0,30 / 0,34).
- Sul cammino che parte dal primo risultato BM25: 0,15, sotto il caso (0,22); lì dice "è qui" il 60% delle volte.
- Ordine mescolato: 0,32 (caso 0,24); stessa correttezza nei due ordini nell'83% delle coppie.
- Per repository: fastapi 0,44, requests 0,46, rich 0,30, httpx 0,67 (solo 18 domande).

## Esplorative, decise dopo aver visto i dati (esplora_sonda.py; non cambiano la decisione)

- Quando non dice "è qui" e sceglie un vicino, ha ragione il 66% delle volte (caso 50%).
- La probabilità del token "0" separa oro e non oro con AUC 0,76.
- Gruppi con la domanda diretta ("va cambiato almeno uno?"): sì nell'89% dei file giusti e nel 47% di quelli
  sbagliati; AUC della probabilità di "sì" 0,80 (file), 0,80 (classi), 0,79 (comunità). La domanda rovesciata
  ("possono restare tutti uguali?") lo confonde: risponde quasi sempre "no".
- Lettura: Gemma è un sensore debole ma non nullo; sbaglia soprattutto dove le parole della issue somigliano al
  codice (la "trappola delle parole"), cioè proprio dove la ricerca parte.
