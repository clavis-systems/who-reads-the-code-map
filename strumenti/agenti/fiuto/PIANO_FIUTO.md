# Fiuto: piano della prova (scritto prima delle risposte del modello), 14/10/2026

Solo i compiti di sviluppo con una definizione d'oro (42 su 45); gli 84 compiti di prova non vengono letti.

## Idea in una riga

La sonda della Bussola ha mostrato che Gemma 4 E4B non sa scegliere la strada sulla mappa del codice, ma spesso
riconosce la funzione da cambiare quando ce l'ha davanti. Quindi: il programma cammina, il modello annusa soltanto.

## Come (fiuto.py)

- Stesso modello e stesso Ollama dello studio (gemma4:e4b-it-qat, digest ee6656371218), temperatura 0, una chiamata
  senza memoria per candidato: la issue, il codice del candidato, "va cambiato proprio questo? sì o no".
  Punteggio = 0,5 + (P(sì) − P(no)) / 2, con le probabilità del primo token (i 20 più probabili, tutte le grafie).
  Prova di fumo prima del congelamento, solo sul formato, su 2 nodi di rich_3063 (non contano): con i primi 5 token
  il "sì" spesso manca e il punteggio diventava 0 per tutti; con i primi 20 compare, e il punteggio resta graduato.
- Stesso budget per i due bracci: 20 chiamate per compito.
  - FILA: i primi 20 candidati BM25 (libreria), riordinati per punteggio.
  - FIUTO: i primi 10 BM25, poi sulla mappa ufficiale delle chiamate (solo libreria, senza verso): si chiede al
    vicino non ancora chiesto del nodo con il punteggio più alto (a parità, rango BM25), fino a 20.
  - Classifica finale: i nodi chiesti per punteggio, poi il resto di BM25 nel suo ordine.
- Confronti: L (BM25 congelato) e F (PageRank congelato sul grafo delle chiamate).
- Misura principale: fn_exact@1 (la funzione giusta al primo posto); anche @5 e @10.

## Soglie (fissate ora). Un braccio PASSA se valgono tutte e tre

1. @1 almeno 5 compiti più di L (L@1 sullo sviluppo era 8 su 42, quindi almeno 13).
2. @5 non peggio di L.
3. Più compiti vinti che persi al primo posto in almeno 2 dei 3 repository principali (fastapi, rich, requests).

## Il criterio dell'utente: "un risultato positivo che si spiega in una frase"

Le frasi sono scritte ora, prima dei dati; si usa quella che i numeri permettono:
- se FIUTO passa e batte FILA di almeno 2 compiti al primo posto: "Un modello piccolo non sa leggere una mappa del
  codice, ma sa riconoscere il colpevole: se il programma cammina sulla mappa e il modello annusa soltanto, la funzione
  giusta arriva al primo posto N volte su 42 invece di 8";
- se passa un braccio ma la mappa non aggiunge almeno 2 compiti: "Un modello piccolo non sa orientarsi, ma sa
  riconoscere: mettergli i sospetti in fila funziona meglio che farlo camminare" (onesto: la mappa non serve);
- se non passa nessun braccio: ci fermiamo come deciso con l'utente; il materiale diventa una risorsa pubblica e le
  energie vanno su altro.

## Limiti noti

- Le funzioni async mancano dalla mappa ufficiale: se l'oro è solo async, nessun braccio può trovarlo.
- La domanda sì/no non è stata provata prima (la sonda usava "è qui o quale vicino?"); prova di fumo solo sul formato.
- È sviluppo: se passa, serve un piano congelato e la prova unica sugli 84 compiti di prova.

## Scostamenti

(vuoto)
