# Fiuto: risultato sui compiti di sviluppo (14/10/2026, 17:22–18:46)

Piano: PIANO_FIUTO.md (commit e28cb4c, congelato prima delle risposte). Dati: strumenti/risultati/fiuto/
(fiuto_risposte.jsonl, 1.152 chiamate, 0 errori; fiuto_riassunto.json).

| 42 compiti, funzione esatta | @1 | @5 | @10 |
|---|---|---|---|
| L (BM25 congelato) | 8 | 20 | 21 |
| F (PageRank congelato sulla mappa) | 11 | 21 | 22 |
| FILA (20 sospetti BM25, riordinati da Gemma) | **16** | 23 | 25 |
| FIUTO (10 BM25 + cammino sulla mappa, 20 chiamate) | 15 | 21 | 23 |

- Soglie: passano entrambi i bracci (@1 ≥ 13; @5 ≥ 20; vittorie nette in fastapi +3, rich +2, requests +3 per FILA).
- La mappa non aggiunge niente: FIUTO − FILA = −1 al primo posto.
- **Frase scritta prima dei dati che i numeri permettono: "Un modello piccolo non sa orientarsi, ma sa riconoscere:
  mettergli i sospetti in fila funziona meglio che farlo camminare."**
- Esplorative: FILA contro L al primo posto 8 vinti e 0 persi (McNemar esatto p = 0,008, sviluppo, non conferma).
  Quando la funzione giusta è tra i 20 sospetti (26 compiti), Gemma la mette prima in 16.
- Costo: 20 domande da circa 600 token ciascuna, 0,9 s l'una (17 minuti di modello in tutto).
- È sviluppo. Conta solo la prova unica sugli 84 compiti di prova (PIANO_FIUTO_PROVA.md).
