# Fiuto: risultato della prova unica sugli 84 compiti di prova (14/10/2026, 19:03–19:39)

Piano: PIANO_FIUTO_PROVA.md (etichetta congelamento-fiuto-2026-10-14, commit 0f32f14, fiuto.py sha256 b04c9388…).
Dati: strumenti/risultati/fiuto/ (fiuto_prova_risposte.jsonl, 2.184 chiamate, 0 errori; fiuto_prova_riassunto.json).
Contano 78 compiti (quelli con una definizione d'oro).

## Ipotesi del piano

| | primo | secondo | solo primo | solo secondo | p | p di Holm | esito |
|---|---|---|---|---|---|---|---|
| H1: FILA@1 contro L@1 | 28 | 17 | 18 | 7 | 0,043 | 0,087 | **non confermata** |
| H2: FILA@k contro agente push_lex (stesse posizioni) | 37 | 40 | 12 | 15 | 0,70 | 0,70 | **non confermata** |

**Frase scritta prima dei dati che il piano impone: "Il vantaggio visto sullo sviluppo non è dimostrato sui compiti
mai visti"; ci si ferma.** H1 va nella direzione prevista ma non supera la soglia corretta per due ipotesi. Nessun
confronto va in modo significativo nella direzione opposta.

## Descrittive (senza test, fissate nel piano)

- Funzione esatta @1 / @5 / @10: L 17 / 40 / 51; F 17 / 36 / 49; FILA 28 / 52 / 58; FIUTO 31 / 51 / 57.
- FILA@5 (5 posizioni) contro gli agenti (le loro 1–5): none 52–29, pull 52–31, push_graph 52–31, push_lex 52–40.
  Non è un confronto alla pari: push_lex ha consegnato una sola posizione in 48 compiti su 78.
- FILA@1 contro push_lex: 28 contro 40. Con una sola risposta, l'agente con i suggerimenti BM25 sbaglia meno.
- FIUTO@1 contro FILA@1: 31 contro 28 (6 contro 3). Sullo sviluppo era 15 contro 16: la mappa non aggiunge in modo
  stabile.
- Per repository, @1 (L / FILA / FIUTO): fastapi 11 / 14 / 15, rich 5 / 9 / 13, requests 1 / 5 / 3.
- Token per compito, mediana: FILA 10.951, agente push_lex 22.960 (approssimato).
- Il campo "sentence" del riassunto viene dalle soglie dello sviluppo; per la prova contano solo le ipotesi qui sopra.

## Ricalcolo indipendente

Fatto il 14/10 alle 22:10 da un agente separato, con codice proprio (senza fiuto.py né analisi_grafi.py; script in
scratchpad/ricalcolo_fiuto/ricalcolo.py): 78 compiti, H1 28 contro 17 (18 contro 7, p 0,0433, Holm 0,0866), H2 37
contro 40 (12 contro 15, p 0,701), FILA@5 52 contro L@5 40 (17 contro 5). Nessuna differenza: MATCH.

## Lettura

Il riordino da parte del modello migliora la ricerca per parole in modo coerente sullo sviluppo e sulla prova (primo
posto 8→16 e 17→28; primi cinque 20→23 e 40→52), ma sulla prova la differenza al primo posto non basta per la soglia
fissata. Contro l'agente, a parità di posizioni, non c'è differenza dimostrata. I compiti di prova sono stati usati
due volte: una nuova conferma richiederebbe compiti nuovi.
