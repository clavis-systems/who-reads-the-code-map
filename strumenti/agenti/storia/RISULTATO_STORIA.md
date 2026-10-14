# Storia (riserva S1): risultato della prova (14/10/2026)

Piano: PIANO_STORIA.md (commit 67e2445, congelato prima dei punteggi). Dati: strumenti/risultati/storia/
(storia_valutazione.json; archivi git copiati in archivi/, 6,3 GB, ignorati da git).

## Misura principale (42 compiti di sviluppo con una definizione d'oro; fn_exact@5)

| Classifica | @1 | @5 | @10 |
|---|---|---|---|
| L (BM25 congelato) | 8 | 20 | 21 |
| F (PageRank sul grafo delle chiamate, congelato) | 11 | 21 | 22 |
| R (recenza) | 2 | 7 | 10 |
| CC (grafo "cambiate insieme") | 5 | 15 | 25 |
| RRF(L, R), principale | 5 | 11 | 21 |
| RRF(L, CC) | 9 | 20 | 26 |
| R mescolata (controllo) | 2 | 5 | 5 |
| RRF(L, R mescolata) | 0 | 8 | 14 |

Soglie: 1) RRF(L, R) − L = −9 (serviva ≥ +3): NO. 2) CC 15 > R 7: sì. 3) il controllo non si può applicare
(guadagno negativo): NO. 4) fuori da fastapi, vinti meno persi = −7: NO.
**Decisione secondo il piano: la riserva NON PASSA.**

## Descrittive (senza soglia)

- L'ultimo commit della libreria prima del compito aveva toccato la funzione d'oro in 7 compiti su 42; gli ultimi 5 in
  12; gli ultimi 20 in 21; gli ultimi 100 in 31. Il segnale esiste, ma la recenza mette in alto troppe altre funzioni
  e, fusa con BM25, spinge fuori le risposte giuste.
- Issue che citano un numero di PR: 12; un hash: 2; una versione: 6.
- Per repository (@5, L / RRF(L, R)): fastapi 8 / 6, rich 7 / 3, requests 4 / 2, httpx 1 / 0.
- Fuori piano, solo da notare: CC@10 = 25 contro L@10 = 21 (non era una misura fissata; non decide nulla).

## Nota tecnica

Gli archivi git delle istantanee non contengono l'oggetto base_commit; il punto di partenza è la punta del ramo
principale di ogni archivio, i cui file .py della libreria coincidono byte per byte con l'istantanea in tutti i 45
compiti (archivi.json). Quindi nessun commit successivo al compito entra nella storia della libreria.
