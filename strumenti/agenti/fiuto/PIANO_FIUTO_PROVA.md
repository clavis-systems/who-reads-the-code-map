# Fiuto: piano della prova di conferma sugli 84 compiti di prova (congelato prima della prova)

Data: 14/10/2026. Sviluppo: RISULTATO_FIUTO.md. Questo piano non cambia nulla del metodo provato sullo sviluppo.

## Dichiarazione

È il **secondo uso** dei compiti di prova: il primo è lo studio congelato "chi legge la mappa" (etichetta
congelamento-grafi-2026-10-13), di cui conosciamo già i risultati aggregati (BM25 e agente). Nessuna risposta del
modello Fiuto sui compiti di prova è stata vista. Il metodo è stato scelto e misurato solo sui 45 compiti di sviluppo.

## Cosa si esegue (fiuto.py, stesso codice dello sviluppo con la sola scelta della parte)

- `python fiuto.py esegui prova`, poi `python fiuto.py riassumi prova`. Una sola esecuzione; se Ollama si interrompe
  si riprende dalle risposte già salvate (stessa domanda, temperatura 0).
- Modello e ambiente identici allo studio (gemma4:e4b-it-qat, digest ee6656371218, Ollama 0.32.13: il codice si
  ferma se diversi), stesse opzioni e stessa domanda dello sviluppo; fino a 20 chiamate per compito per ogni braccio
  (meno se BM25 ha meno di 20 candidati); punteggio 0,5 + (P(sì) − P(no)) / 2.
- Codice congelato: fiuto.py sha256 b04c938845efa1ecf75c9480d76a6bdce4441ccc064fb08d4dcf1db5f538b389 (sullo sviluppo riproduce esattamente
  RISULTATO_FIUTO.md). Durante la prova il codice non si tocca, anche se i punteggi per compito si vedono nel log.
- Compiti: gli 84 di prova; contano quelli con una definizione d'oro (78 nello studio congelato).

## Ipotesi (misura: funzione esatta, regola dello studio congelato)

- **H1 (principale)**: FILA mette la funzione giusta al primo posto più spesso di BM25 (FILA@1 contro L@1).
- **H2**: a parità di posizioni, FILA batte il miglior agente dello studio congelato sugli stessi compiti. L'agente
  push_lex (40 su 78) poteva consegnare fino a 5 posizioni ma in 48 compiti su 78 ne ha consegnata una sola (media
  circa 1,8). Quindi per ogni compito FILA conta solo i suoi primi k, con k = posizioni consegnate da push_lex in quel
  compito. push_lex è il migliore dei quattro agenti, scelto conoscendo i risultati: rende il confronto più difficile
  per FILA, non più facile. Restano vantaggi dell'agente: vede i primi 5 BM25, può nominare funzioni async o fuori
  dalla mappa, e ha il completamento dei nomi nel file.
- Test: McNemar esatto a due code sulle coppie discordanti; correzione di Holm su H1 e H2; confermata se p di Holm
  < 0,05 e nella direzione prevista.
- Descrittive senza test: FILA@5 (5 posizioni) contro i quattro agenti (le loro 1–5); FILA@1 contro push_lex; FILA@5
  contro L@5; FIUTO contro FILA; F contro L; risultati per repository; token per compito (FILA contro push_lex,
  approssimato: la cache dei prefissi abbassa il conteggio per entrambi). Il riassunto stampa anche le soglie dello
  sviluppo: per la prova contano solo le ipotesi qui sopra.

## Frasi scritte prima dei dati (criterio dell'utente: un risultato positivo che si spiega in una frase)

- H1 e H2 confermate: "Su compiti mai visti, Gemma 4 E4B che risponde solo sì o no a 20 sospetti mette la funzione
  giusta al primo posto N volte su 78 contro M della ricerca per parole, e a parità di risposte trova più dello
  stesso modello usato come agente."
- Solo H1: "Su compiti mai visti, rispondere sì o no a 20 sospetti porta la funzione giusta al primo posto N volte su
  78 invece di M; che batta l'agente a parità di risposte non è dimostrato."
- Solo H2: "A parità di risposte, il modello che risponde sì o no a 20 sospetti trova più dello stesso modello usato
  come agente; che migliori il primo posto rispetto alla ricerca per parole non è dimostrato."
- Nessuna confermata: "Il vantaggio visto sullo sviluppo non è dimostrato sui compiti mai visti"; ci si ferma.
- Se un confronto va in modo significativo nella direzione opposta (p di Holm < 0,05), lo si dice per primo.

## Controlli

- Prima della prova: un agente separato ha riletto questo piano e fiuto.py (14/10). Nessuna fuga dall'oro, nessun
  errore bloccante nel codice; tre punti bloccanti nel piano, corretti qui: H2 a parità di posizioni, frasi che non
  dicono più di quanto un risultato non significativo permette, congelamento con hash ed etichetta git.
- Dopo la prova: un agente separato ricalcola H1 e H2 dai file grezzi con codice proprio.

## Scostamenti

(vuoto)
