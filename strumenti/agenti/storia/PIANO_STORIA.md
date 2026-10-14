# Storia: piano della prova di 48 ore (idea di riserva S1), scritto prima di calcolare i punteggi

Data: 14/10/2026. Solo i 45 compiti di sviluppo; gli 84 compiti di prova non vengono letti. Solo CPU, nessun modello.

## Domanda

La storia git dentro ogni istantanea (che finisce a base_commit) indica la funzione da correggere meglio, o in
aggiunta, alle parole della issue (BM25)? Idea: le funzioni toccate di recente, e quelle che cambiano insieme a loro,
sono i posti dove nascono i guasti.

Onestà: durante la ricerca di idee (14/10) un agente ha già guardato questi dati di sviluppo con un abbinamento
grezzo (BM25 top-5 19 su 38; con la storia 25–27 su 38). Questo piano quindi non è cieco sui dati di sviluppo; le
soglie sono quelle scritte allora dallo stratega, fissate qui prima del calcolo esatto.

## Come (storia.py)

- Per ogni repository si copia solo l'archivio git (oggetti e riferimenti) di un'istantanea di sviluppo in un nuovo
  repository vuoto con la nostra configurazione: niente checkout, niente hook, niente configurazione dell'archivio.
- Per ogni compito si usano solo i commit antenati del "punto di partenza" lungo il primo genitore (niente date: un
  taglio per data farebbe entrare commit di rami non ancora uniti). Trovato prima del calcolo: gli archivi non
  contengono l'oggetto base_commit; il punto di partenza è quindi il commit più recente del ramo principale i cui file
  .py della libreria sono identici byte per byte a quelli dell'istantanea. Per tutti i 45 compiti è la punta del ramo
  principale del proprio archivio, con 0 file diversi (archivi.json).
- Le definizioni toccate da ogni commit con la stessa regola dell'oro (dati.gold_locations), quindi anche le async.
  I commit che toccano più di 30 definizioni non contano (rifacimenti generali).
- Candidati: le definizioni della libreria che esistono a base_commit.
- Classifiche:
  - L = BM25 congelato (come nello studio dei grafi);
  - R = recenza: somma di exp(−età/50) sui commit che toccano la definizione (età = posizione del commit, 0 = il più
    recente);
  - CC = PageRank personalizzato sul grafo "cambiate insieme" (commit con 2–30 definizioni), semi = primi 5 di L e
    primi 5 di R, riavvio 0,5;
  - fusioni RRF(L, R) (principale) e RRF(L, CC), k = 60;
  - controllo: R con l'ordine dei commit mescolato a caso (stesse dimensioni), e RRF(L, R mescolata).
- Misura: fn_exact@5 (come nello studio congelato), anche @1 e @10.

## Soglie (fissate ora): la riserva PASSA se valgono tutte e quattro

1. RRF(L, R) trova almeno 3 compiti in più di L (fn_exact@5).
2. CC batte R da sola (fn_exact@5): serve perché la storia sia "un grafo" e non solo recenza.
3. Il controllo mescolato conserva meno del 70% del guadagno di RRF(L, R) su L.
4. Almeno un compito vinto in più che perso (RRF(L, R) contro L) fuori da fastapi.

Se passano 1, 3 e 4 ma non 2: "recenza sì, grafo no"; si decide con l'utente.
Se non passa 1: si scrive l'articolo dell'autopsia (studio congelato + sonda della Bussola) con le risorse.

## Si riporta anche, senza soglia

Quota di definizioni d'oro toccate negli ultimi 1/5/20/100 commit della libreria; quante issue citano un numero di
PR, un hash o una versione; risultati per repository; il PageRank congelato sul grafo delle chiamate (F) sullo stesso
sviluppo.

## Scostamenti

(vuoto)
