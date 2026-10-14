# Bussola: piano della sonda di 48 ore (scritto prima di vedere le risposte)

Data: 14/10/2026. Riguarda solo i 45 compiti di sviluppo; gli 84 compiti di prova non vengono letti.

## Domanda

L'idea "Bussola": il programma tiene il conto delle probabilità su tutte le funzioni e chiede a Gemma 4 E4B solo
domande piccole ("il guasto è qui, o in quale vicino si va?"). La teoria della ricerca rumorosa sui grafi dice che
funziona se Gemma indica la direzione giusta abbastanza spesso. La simulazione (sim_search.py, non ancora ricalcolata
in modo indipendente) mette il pareggio intorno a p = 0,60–0,65. Questa sonda misura p.

## Cosa si misura (sonda.py, codice e domande con hash in sonda_costruzione.json)

- Grafo: il grafo ufficiale delle chiamate, solo nodi della libreria (niente test e documentazione), senza direzione
  (gli archi ufficiali non sono affidabili sul verso).
- Domande di direzione, una chiamata senza memoria per domanda, temperatura 0: la issue, il codice del nodo e fino a 25
  vicini (i primi per rango BM25), risposta = un numero (0 = "è qui").
  - Nodi: ogni nodo d'oro presente nel grafo (al massimo 2), il cammino più corto dal primo nodo BM25 all'oro, e nodi
    a caso a distanza 1–4 dall'oro (al massimo 4 per distanza, 16 domande per compito oltre l'oro).
  - Giusta: 0 su un nodo d'oro (o un vicino d'oro); altrove un vicino che è un passo più vicino all'oro.
  - Ogni domanda con più di un vicino è posta due volte: in ordine BM25 ("prior") e in ordine mescolato.
- Domande sui gruppi (sì/no): file, classi con i metodi, gruppi di funzioni che si chiamano (3–60 elementi);
  positivi, negativi difficili (contengono uno dei primi 10 BM25) e negativi a caso; ogni gruppo in due versioni
  ("va cambiato almeno uno?" / "possono restare tutti uguali?").
- Costruzione: 39 compiti su 45 hanno almeno una definizione d'oro nel grafo; 2.167 domande
  (sonda_domande.jsonl, sha256 ecbcaffc…).
- Prova di fumo prima del congelamento, solo per il formato, su 3 domande (non contano): risposte leggibili, circa
  0,7 s per domanda, Ollama restituisce anche le probabilità del primo token (salvate, usate solo come misura secondaria).

## Misura principale e soglie (fissate ora)

- p̂ = quota di risposte giuste sulle domande di direzione rispondibili, ordine "prior", tutte insieme (oro + cammino +
  a caso), con intervallo al 95% ricampionando i compiti.
- SI CONTINUA (passo successivo: Bussola completa su 16 compiti di sviluppo contro BM25) se p̂ ≥ 0,65, oppure se un tipo
  di gruppo con almeno 20 elementi in media ha errore bilanciato ≤ 0,15.
- SI FERMA se p̂ < 0,60 e nessun tipo di gruppo arriva a 0,15: si passa all'idea di riserva (grafo della storia) e i
  dati della sonda restano per il titolo "perché un modello da 4B non sa usare una mappa del codice".
- Zona grigia 0,60–0,65: si continua solo se il simulatore, con il p misurato e gli errori come li fa davvero Gemma,
  prevede almeno 4 compiti in più di BM25 sui 45 di sviluppo.
- Si riportano anche, senza soglia: p per distanza dall'oro, per numero di vicini, per repository, per tipo di nodo;
  quanto spesso dice "è qui" quando non lo è; il caso (1 su numero di opzioni); quanto cambia mescolando l'ordine.

## Limiti noti

- Le funzioni async mancano dal grafo ufficiale: i compiti con oro solo async non hanno domande.
- I nodi scelti non sono quelli che sceglierebbe la Bussola vera; p sui nodi reali può essere diverso.
- È una misura esplorativa sullo sviluppo; non decide nulla sul set di prova.

## Scostamenti

(vuoto)
