# Premessa: chi deve leggere la mappa del codice? (CONGELATA, 13/10/2026)

Stato: congelata il 13/10/2026 alle 19:32 con l'etichetta git `congelamento-grafi-2026-10-13`, prima di
qualunque corsa sui compiti di prova. Scritta e corretta guardando solo i compiti di sviluppo, dopo tre controlli
indipendenti (§4d). Ogni cambiamento da qui in poi va scritto in «Scostamenti», con il motivo.

## 1. Domande

La gara Gemma 4 Developer Agent dà, per ogni compito, una mappa del codice: un grafo di chiamate con il testo di ogni
funzione, più un embedding per nodo. Dà anche tre strumenti che l'agente può chiamare per esplorarla. Le prove
pubblicate dai concorrenti dicono che questi strumenti non aiutano: un modello grande li usa poco, e le ricerche
semantiche tornano vuote.

1. **Diagnosi.** Perché gli strumenti ufficiali non servono?
   - Quanto la mappa copre le funzioni da cambiare.
   - Quanto la ricerca semantica può funzionare con il testo di un bug.
   - Quanto il grafo collega le parole del bug ai punti da cambiare.
2. **Il grafo serve?** Senza modello: classificare i punti del codice usando il grafo dà risultati migliori della
   sola ricerca di testo?
3. **Chi legge la mappa?** Con Gemma 4 E4B su un portatile: va meglio se il modello chiama gli strumenti della mappa
   (pull), o se l'host legge la mappa e gli dà pochi indizi (push)?

## 2. Dati

- **Compiti.** I 129 compiti pubblici della gara (`tasks.jsonl`), su fastapi, rich, requests e httpx, con la patch
  di riferimento e la patch dei test. Licenza Apache 2.0.
- **Contesto.** Istantanee del codice a `base_commit`, grafi (NetworkX in JSON) ed embedding (npz), dal pacchetto dati
  della gara, estratto con `estrai_dati.py` (`MANIFEST.json` con lo SHA-256 di ogni file). Le impronte sono in §7.
- **Divisione sviluppo/prova**, fissata prima di guardare i dati: `dati.split_tasks`, seme 20261012.
  - Per ogni repository gli id vengono ordinati e mescolati con `random.Random("20261012:<repo>")`.
  - Il primo terzo, arrotondato per eccesso, è sviluppo; il resto è prova.
  - Sviluppo: 45 compiti (fastapi 23, rich 16, requests 5, httpx 1). Prova: 84 (fastapi 44, rich 32, requests 8).
  - Tutto lo sviluppo si fa solo sui compiti di sviluppo. La prova si esegue una volta, dopo il congelamento.
- **Solo la libreria.** Contano solo i file del pacchetto vero di ogni repository (`dati.LIBRARY`): `fastapi/`,
  `rich/`, `src/requests/`, `src/httpx/` e `src/ahttpx/`. Non contano test, esempi della documentazione
  (`docs_src/`, `examples/`), script e strumenti.
- **Le definizioni** (`dati.definitions`) sono le funzioni e classi che uno sviluppatore apre: quelle a livello di
  modulo e dentro le classi, anche dentro blocchi `if`, `try`, `with`, `for`, `while` o `match` a quei livelli. Una
  funzione o classe scritta dentro un'altra funzione appartiene a quella funzione (il grafo ne ha poche, con nomi
  appiattiti come `fastapi.routing._serialize_item`).
- **I punti giusti** (`dati.gold_locations`), dalla patch di riferimento:
  - una riga tolta o modificata appartiene alla definizione più interna che la contiene a `base_commit`;
  - una riga aggiunta appartiene alla definizione più interna che la contiene nel file dopo la patch; se quella
    definizione è nuova, alla definizione esistente più vicina che la contiene. Così un metodo nuovo conta per la
    sua classe, e una classe nuova in fondo al file conta solo per il file;
  - le righe vuote, aggiunte o tolte, non contano;
  - un file che la patch cancella del tutto conta solo come file: le sue definizioni non sono punti da correggere;
  - un cambio fuori da ogni definizione conta solo a livello di file.
  - Casi limite: un commento cambiato dopo l'ultima riga di una funzione conta per la classe o il modulo che la
    contiene (succede, ma nello sviluppo e nella prova non cambia nessuna definizione giusta); un cambio del solo
    «a capo» finale e i file rinominati non compaiono nei dati.

## 3. Misure

- **Misura principale: il luogo esatto.** Un luogo trovato è giusto solo se è proprio una delle definizioni della
  patch. Un modulo o un file intero non conta mai.
- **Misura secondaria, larga** (`dati.def_match`): vale anche la definizione che contiene direttamente quella della
  patch (di solito la sua classe) o un suo membro diretto. Si riporta quale dei tre casi è stato
  (`dati.best_match_kind`: esatto, membro, contenitore).
  - Perché la principale è quella esatta: sullo sviluppo, le classi grandi collegate a tutti i loro metodi (per
    esempio `FastAPI` o `Console`) finivano spesso tra i primi 5 del grafo e prendevano il punto «contenitore» senza
    dire dove sta il bug (revisione, §4d).
- **Classifiche senza modello.** Un metodo ordina le funzioni e classi della libreria per un compito. Principale:
  almeno un luogo esatto tra i primi 5 (esatto@5). Secondarie: esatto@1, esatto@10, largo@5, file@5.
- **Agente.** Gemma consegna fino a 5 luoghi. Principale: almeno un luogo esatto. Secondarie: largo, file, chiamate,
  token, e i conteggi descrittivi di §5.
- **Su quali compiti.** A livello di funzione contano solo i compiti con almeno una definizione nella patch. A
  livello di file solo i compiti con almeno un file giusto già presente a `base_commit` (un file nuovo non si può
  trovare).
- **Una sola regola di punteggio per l'agente:** `agente_grafi.agent_hit`, usata durante le corse e ricalcolata
  dall'analisi a partire dai luoghi consegnati.
  - Un luogo si legge come `percorso.py::Nome.qualificato`, `percorso.py:Nome`, `percorso.py` o nome puntato; si
    ignorano virgolette, apici inversi, `./`, `/workspace/` e le parentesi finali (`f(x)` vale `f`); un numero dopo
    i due punti (`percorso.py:120`) vale solo il file.
  - Una stringa si divide in più luoghi solo dove, dopo una virgola, un punto e virgola o un a capo, comincia un
    percorso `.py`; un elenco di nomi puntati non si divide.
  - **Completamento dentro il file** (`resolve_in_file`), solo se il nome non è già una definizione del file
    indicato: un nome dentro una funzione del file vale per quella funzione (`handler.app` vale `handler`, come
    per i punti giusti); altrimenti, se una sola definizione di quel file finisce con «.» + quel nome, vale quella
    (`models.py::prepare_body` vale `PreparedRequest.prepare_body`). Senza questo, le condizioni push vincevano anche solo perché copiano dagli
    indizi il nome con la classe (seconda revisione, §4d). La misura senza completamento resta come secondaria.

## 4. Metodi senza modello

- **Testo del bug per le classifiche:** descrizione e suggerimenti, senza commenti HTML e senza indirizzi web (le
  loro parole erano rumore: sullo sviluppo un esempio con un link di sponsor finiva tra i primi 5 in 11 compiti).
- **L:** BM25 del testo del bug sul testo dei nodi e sui loro nomi, divisi in sotto-parole; `k1` e `b` scelti sullo
  sviluppo.
- **A:** nodi nominati nel bug (`dati.anchors`), risolti come fanno gli strumenti ufficiali: nome esatto, poi
  suffisso, poi senza maiuscole, poi sottostringa. Il nome del progetto («FastAPI» in fastapi) non conta.
- **G:** passeggiata casuale con ritorno (PageRank personalizzato) sul grafo ufficiale preso senza direzione.
  - Parte dai nodi di A e dai primi `seeds_from_L` di L, con peso 1/posizione. Possono partire anche da test ed
    esempi, che spesso contengono le parole del bug e chiamano il codice da cambiare.
  - `alpha` è la probabilità di tornare al punto di partenza.
  - Il punteggio si divide per il grado del nodo alla `degree_power`, perché i nodi collegati a tutto non vincano
    solo per questo.
- **E:** vicini per embedding dei nodi di partenza, come farebbe `search_similar_code` con il nome giusto.
- **F:** fusione per rango delle classifiche elencate in `fusion`. È il metodo «grafo» di H1.
- **Solo la libreria nelle risposte** (`localizza.keep_library`): da ogni classifica si tolgono i nodi fuori dalla
  libreria e quelli di cui non si trova il file (nelle mappe di fastapi sono gli esempi di `docs_src`).

**Parametri scelti sullo sviluppo** (`valuta_statico.py --grid`, `griglia_dev_v5.json`, misura esatto@5 sui 42
compiti di sviluppo con almeno una definizione), in due passi fissati prima di vederne i risultati:
1. L da sola: `k1` in (0,9; 1,2; 1,5) e `b` in (0,5; 0,75; 0,9). Sei combinazioni a pari merito con 0,476; a pari
   merito vince quella di partenza: `k1` = 1,2, `b` = 0,75.
2. G con quella L: `seeds_from_L` in (5, 10, 20), `alpha` in (0,15; 0,3; 0,5), `degree_power` in (0; 0,5; 1),
   `fusion` in ((G), (L, G)): 54 combinazioni, da 0,357 a 0,500. A pari merito vince, in quest'ordine: meno
   classifiche fuse, `degree_power` più piccola, `alpha` più grande, più semi.
   Scelta: `seeds_from_L` = 20, `alpha` = 0,5, `degree_power` = 0,5, `fusion` = (G), quindi F = G.

**Sviluppo con questi parametri** (`statico_dev_v6.json`; da non confondere con la prova). Le colonne «esatto» e
«largo» sono sui 42 compiti con almeno una definizione; «file@5» sui 44 con almeno un file giusto già esistente:

| Metodo | Esatto@1 | Esatto@5 | Esatto@10 | Largo@5 | File@5 |
|---|---|---|---|---|---|
| L | 0,190 | 0,476 | 0,500 | 0,524 | 0,795 |
| A | 0,214 | 0,238 | 0,262 | 0,310 | 0,364 |
| G | 0,262 | 0,500 | 0,524 | 0,571 | 0,795 |
| E | 0,190 | 0,214 | 0,214 | 0,286 | 0,477 |

Sulle coppie G contro L (esatto@5) le discordanti sono 2 a 1 (McNemar esatto p = 1,0). Con la misura larga 2 a 0.
Quindi sullo sviluppo, con la misura esatta e una L pulita, il grafo aggiunge poco. Le versioni precedenti
(`statico_dev_v2.json`, `statico_dev_v3.json`) davano 8 a 1 e 7 a 1, ma con la misura larga, la vecchia regola dei
punti giusti, il testo non pulito e i file fuori dalla libreria (§4d).

**Diagnosi sullo sviluppo (45 compiti):**
- 42 compiti hanno almeno una definizione nella patch; 107 definizioni: 84 funzioni, 9 async, 14 classi.
- 9 definizioni mancano dalla mappa: sono tutte e sole le 9 async. In 3 compiti mancano tutte.
- Nomi di codice nel bug (testo pulito):
  - 34 compiti hanno almeno un nome;
  - in 29 almeno un nome corrisponde a un nodo;
  - in 24 almeno un nome è una chiave degli embedding, quindi `search_similar_code` potrebbe rispondere;
  - in 14 il bug nomina una definizione della patch (a parola intera).

## 4b. Agente

- **Modello.** `gemma4:e4b-it-qat`, digest ee6656371218…, su Ollama 0.32.13 (il programma si ferma se uno dei due
  è diverso), scheda RTX 5060 Laptop da 8 GB. Temperatura 0, seme 1, contesto di 32.768 token (la finestra della
  gara), al massimo 1.024 token per risposta, senza ragionamento esteso.
- **Primo messaggio**, uguale per tutte le condizioni: il nome del progetto, il bug e i suggerimenti, poi l'elenco
  degli elementi del primo livello del progetto («Workspace Layout»: una versione corta della sezione ufficiale, che
  elenca i primi 150 elementi fino a tre livelli). Senza elenco, in none e pull Gemma chiedeva cartelle sbagliate
  (26 errori nelle prove di fumo, nessuno in push, i cui indizi contengono percorsi).
- **Strumenti** (`agente_grafi.py`), tutti in sola lettura sull'istantanea a `base_commit`:
  - `list_files`: accetta anche `/workspace` e il nome GitHub del progetto (per esempio `psf/requests`) come
    cartella principale, anche all'inizio di un percorso (`psf/requests/src`);
  - `search_code`: sottostringa o espressione regolare nei file `.py`, fino a 5.000 caratteri di risultati. Le
    espressioni regolari (al massimo 200 caratteri, su righe tagliate a 500) usano il modulo `regex`, che si ferma
    dopo 5 secondi per ricerca e restituisce un errore invece di bloccare la corsa;
  - `read_file`: al massimo 150 righe e 10.000 caratteri, come lo strumento ufficiale;
  - `submit_locations`: fino a 5 luoghi, e chiude.
  - Nella condizione pull ci sono anche i tre strumenti ufficiali del grafo, con il comportamento descritto in
    HARNESS_README §6.3 e con il testo ufficiale del prompt. Una sola aggiunta nostra: un nome scritto nel formato
    che il nostro prompt chiede per i luoghi (`percorso.py::Nome`) viene tradotto nel nome del nodo prima dei
    quattro passi ufficiali; ogni altro nome passa ai passi ufficiali così com'è. Senza, nelle prove di fumo le
    uniche chiamate al grafo fallivano per colpa del nostro formato.
  - Argomenti sbagliati o di tipo sbagliato tornano al modello come errore: non fermano mai la corsa.
  - Nessun codice viene eseguito.
- **Budget.** 20 chiamate di strumenti, contando anche `submit_locations`.
- **Turni senza chiamate**, come nel ciclo ufficiale (HARNESS_README §5.3):
  - non costano chiamate;
  - ricevono l'invito ufficiale adattato («Please continue your work using the available tools, or call
    submit_locations…»); se la risposta è del tutto vuota l'invito lo dice;
  - dopo più di 3 turni di fila senza chiamate l'esplorazione finisce; un turno con una chiamata azzera il conto.
    (Nel ciclo ufficiale la risposta di testo che chiude un turno con chiamate non conta: qui conta, quindi il
    nostro ciclo può finire un turno prima.)
  - Per limitare il tempo, al massimo 60 turni in tutto.
- **Il testo scritto accanto a una chiamata** resta nel registro ma non viene rimandato al modello. Rimandato, con
  Ollama faceva rispondere Gemma con un turno vuoto e poi ripetere la stessa chiamata (§4c, esperimento).
- **Avviso di budget**, come nella gara (HARNESS_README §6): quando restano 10 chiamate o meno, ogni risposta di
  uno strumento porta l'avviso `budget_warning`.
- **Consegna finale.** Se l'esplorazione finisce senza consegna (budget, inviti o turni), c'è un ultimo turno in cui
  l'unico strumento offerto è `submit_locations`. Se il modello risponde a parole, non c'è consegna.
- **Memoria della conversazione.** La gara riassume la conversazione quando passa 14.336 token e tiene gli ultimi 5
  eventi (HARNESS_README §7.2). Qui, in modo più semplice e uguale per tutte le condizioni: se la stima della
  conversazione passa 14.336 token, le uscite degli strumenti più vecchie delle ultime 5 diventano una nota breve,
  dalla più vecchia. La stima è un token ogni 3 caratteri dei messaggi; nelle prove di fumo è stata vicina al
  conteggio vero di Ollama (scarto di circa il 10%, più le descrizioni degli strumenti, che non conta). Il
  messaggio di sistema, il bug e gli indizi restano sempre. Serve perché, oltre il contesto, Ollama butta via i
  messaggi più vecchi, bug compreso.
- **Indizi.** push_lex: i primi 5 di L. push_graph: i primi 5 di F. Ogni candidato ha un motivo breve: «named in the
  issue», «its code shares words with the issue», «connected in the code graph to X» (X è un nodo di partenza) o
  «close in the code graph to the issue». Se L ha meno di 5 nodi della libreria, push_lex ne dà meno.
- **Ordine delle quattro condizioni** per compito: `random.Random("20261012-<id>")`.
- **Errori di Ollama.** Una corsa interrotta da un errore di Ollama (con stato e testo della risposta HTTP, se c'è)
  si salva a parte (`<compito>_<condizione>.infra_<n>.json`) e il programma si ferma; al riavvio quella corsa si
  rifà. Dopo 3 errori la corsa è registrata come mancante. Nell'analisi principale una corsa mancante conta come
  un errore (0); si riporta anche il confronto senza i compiti con corse mancanti, e il loro numero.

## 4c. Prove di fumo ed esperimento sullo sviluppo

Servono solo a controllare il banco di prova; i loro numeri non entrano nelle ipotesi. Cartelle in
`strumenti/risultati/grafi/`.

1. **`agente_dev_fumo`** (12/10): 3 compiti × 4 condizioni, codice iniziale (contesto 16.384). Problemi trovati:
   - oltre il contesto Ollama butta via i messaggi più vecchi, compreso il bug (un prompt è arrivato a 16.275
     token);
   - 10 chiamate illeggibili per Ollama (`r"..."` negli argomenti di `search_code`), tutte in un compito;
   - 3 corse finite senza consegna;
   - gli indizi proponevano funzioni di test;
   - in pull gli strumenti del grafo non sono mai stati chiamati.
   Cambi: contesto 32.768 e memoria della conversazione, inviti, consegna finale, filtro dei test.
2. **`agente_dev_fumo2`** (12/10): 7 altri compiti × 4 condizioni, fermata dopo 16 corse. Dopo la lettura di un file
   lungo Gemma spesso rispondeva vuoto e poi rileggeva lo stesso file. Cambio: le regole del ciclo ufficiale.
3. **`agente_dev_fumo3`** (12-13/10): gli stessi 7 compiti, 28 corse. 27 finite con una consegna vera; in una il
   budget è finito e alla consegna finale Gemma ha risposto a parole. In pull 2 chiamate agli strumenti del grafo in
   7 corse, entrambe fallite per il formato `percorso.py::Nome` (corretto, §4b).
4. **Esperimento sul testo rimandato** (`agente_dev_esperimento_testo`, 13/10): condizione none sugli stessi 7
   compiti, stesso codice, una volta rimandando a Gemma il testo scritto accanto alle chiamate e una volta no.

   | Variante | Risposte vuote | Chiamate ripetute | Corse finite per budget |
   |---|---|---|---|
   | testo rimandato | 17 (tutte di 1 token) | 28 | 2 su 7 |
   | testo non rimandato | 0 | 4 | 0 su 7 |

   Scelta: il testo non si rimanda (§4b).
5. **`agente_dev_fumo4`** (13/10): 4 compiti di sviluppo mai usati prima (fastapi_14303, fastapi_14356, rich_3296,
   requests_7433) × 4 condizioni, codice finale, analizzati con `analisi_grafi.py agente --file`. Tutte le 16 corse
   finite con una consegna vera; nessuna risposta vuota, nessuna consegna forzata, nessun errore di Ollama, una sola
   configurazione; da 1 a 4 chiamate ripetute per condizione; in pull nessuna chiamata agli strumenti del grafo;
   circa 19 secondi a corsa.
6. **`agente_dev_fumo5`** (13/10 sera): codice dopo la seconda revisione (elenco del progetto, nomi alternativi della
   cartella principale, completamento dei nomi), 4 compiti di sviluppo (requests_6644, requests_7205,
   fastapi_14266, rich_3130) × 4 condizioni. Tutte le 16 corse finite con una consegna vera; nessuna risposta
   vuota; nessun errore «cartella non trovata» (prima erano 26, in 5 compiti); una sola configurazione; in pull
   ancora nessuna chiamata agli strumenti del grafo.
   I file dell'esperimento del punto 4 non hanno configurazione né impronte: sono stati fatti con il codice del
   commit 7a70170, con il testo rimandato come opzione.
7. **`agente_dev_fumo6`** (13/10 sera): un compito (requests_6644) × 4 condizioni con il codice congelato, solo per
   controllo: le 4 corse finite con una consegna, nessun errore.

## 4d. Revisione indipendente (13/10)

Un agente Claude separato ha letto piano, codice, dati di sviluppo e registri, senza toccare i compiti di prova.
Nessuna fuga dalla parte di prova; statistica e PageRank corretti; i numeri di sviluppo di allora si riproducevano.
Problemi trovati e cosa è cambiato:

- **Punti giusti sbagliati in 5 compiti di sviluppo** (aggiunte attribuite alla riga precedente, righe vuote
  contate): nuova regola sul file dopo la patch (§2).
- **Turni vuoti dovuti al banco di prova**: il testo accanto alle chiamate non si rimanda più (§4b, §4c).
- **Argomenti malformati che potevano fermare tutta la prova**: ora tornano al modello come errore.
- **Errori di Ollama mai ripetuti, analisi che non controllava la completezza**: corse rifatte fino a 3 volte;
  l'analisi finale si rifiuta di riportare se mancano compiti, se la parte statica non è la prova, se le corse non
  hanno tutte la stessa configurazione o se un'ipotesi non si può calcolare.
- **La misura premiava le classi «hub»**: la misura principale ora è quella esatta (§3); il grafo ha anche
  `degree_power` (§4).
- **Il nostro formato dei luoghi rompeva gli strumenti del grafo in pull**: tradotto prima della ricerca (§4b).
- **L rumorosa e non regolata**: testo pulito, nome del progetto tolto da A, piccola griglia anche per L (§4).
- **Codice fuori dalla libreria**: escluso dai punti giusti e dalle classifiche (§2, §4).
- **Riproducibilità**: impronte di dati, divisione e risultati di sviluppo, versioni dei programmi (§7); tutte le
  impronte del codice in ogni uscita.
- Note minori recepite in §3 (lettura dei luoghi), §6 (cautele) e nel codice (limiti delle espressioni regolari).

**Seconda revisione (13/10 sera).** Un altro agente Claude, nuovo, ha ricontrollato le correzioni (commit 7a70170).
Erano corrette e i numeri di sviluppo, la griglia, le impronte e l'esperimento si riproducevano. 1.658
combinazioni di argomenti malformati non hanno prodotto eccezioni; la ripetizione degli errori di Ollama, simulata
senza modello, funzionava. Per controllare la regola dei punti giusti ha anche contato alcune proprietà delle patch
di prova, solo come totali, senza dettagli per compito e senza alcuna misura dei metodi: quante si applicano,
quante cancellano file interi, quante cambiano funzioni annidate o dentro blocchi. Tre correzioni qui sotto vengono
anche da quei conteggi. Problemi trovati e cambi:
- **Il punteggio esatto premiava chi copia i nomi degli indizi**: completamento del nome dentro il suo file (§3); la
  misura senza completamento resta secondaria.
- **Funzioni dentro blocchi `if`/`try` invisibili**: ora contano (§2).
- **File cancellati del tutto**: contano solo come file (§2).
- **Funzioni annidate**: contano per la funzione che le contiene (§2).
- **Attrito a sfavore di none e pull**: elenco del primo livello del progetto per tutti; `list_files` accetta
  `/workspace` e il nome GitHub del progetto (§4b).
- **Espressioni regolari che possono bloccare una corsa**: modulo `regex` con limite di tempo (§4b).
- Minori:
  - la traduzione dei nomi negli strumenti del grafo vale solo per `percorso.py::Nome`;
  - l'analisi finale controlla che tutte le uscite abbiano lo stesso codice, uguale a quello che gira, e gli
    stessi parametri;
  - corse mancanti contate come errore, con un confronto senza di esse;
  - p esatti fino a Holm, arrotondati solo per la stampa;
  - risultato salvato in `analisi_finale.json`;
  - diagnosi su tutti i 129 compiti con un comando apposta (§5);
  - nomi del bug cercati a parola intera nella diagnosi;
  - stato HTTP degli errori di Ollama registrato;
  - testi del piano corretti.

**Terzo controllo (stesso revisore, 13/10 sera)** sulle correzioni del commit fb11f97: nessun problema bloccante né
importante, via libera al congelamento. Note minori sistemate prima di congelare:
- le cartelle nascoste delle istantanee (`.github`) non perdono più il punto iniziale;
- nella diagnosi, un nome con il punto davanti (`Segment._split_cells`) conta;
- un errore di rete mentre si legge una risposta HTTP di Ollama conta come errore di Ollama;
- il completamento dei nomi porta una funzione annidata alla funzione che la contiene;
- `list_files` accetta il nome GitHub anche all'inizio di un percorso;
- documentazione del codice, un test del limite di tempo e testi del piano.
Nota non sistemata, solo dichiarata: dopo il limite di 5 secondi ogni riga ha ancora 10 millisecondi, quindi una
ricerca vicina al limite può dipendere dalla velocità della macchina; le ricerche misurate durano al massimo 0,25
secondi.

## 5. Ipotesi

Tutte si valutano sui 84 compiti di prova; a livello di funzione contano solo i compiti con almeno una definizione
nella patch. Misura: il luogo esatto (§3). I test sono McNemar esatti, bilaterali, sulle coppie dello stesso
compito. Le tre ipotesi principali si correggono insieme con Holm, α = 0,05.

- **H1, senza modello.** F (il grafo, §4) ha esatto@5 più alto di L.
- **H2, con Gemma.** push_graph trova un luogo esatto più spesso di pull.
- **H3, con Gemma.** push_graph trova un luogo esatto più spesso di push_lex.
- **Quando un'ipotesi è confermata:** la differenza va nella direzione prevista e il p corretto con Holm è sotto
  0,05 (`analisi_grafi.py finale`). Altrimenti si scrive che non è confermata, con i numeri.
- **Descrittive:**
  - la diagnosi di §4 sui compiti di prova e su tutti i 129;
  - le stesse coppie con la misura larga, e quale tipo di corrispondenza (esatto, membro, contenitore);
  - per l'agente, le stesse coppie senza il completamento dei nomi (§3) e senza i compiti con corse mancanti;
  - le altre coppie (push_graph contro none, push_lex contro none, push_lex contro pull, pull contro none);
  - il livello di file;
  - in pull, quante corse usano gli strumenti del grafo e quante risposte tornano vuote o in errore;
  - per condizione: chiamate, chiamate ripetute uguali, turni, inviti, risposte vuote, consegne forzate, come
    finisce l'esplorazione, uscite accorciate, token, secondi, corse mancanti.

**Come si esegue la prova** (una volta sola, dopo l'etichetta di congelamento), dalla cartella
`strumenti/agenti/grafi`. Serve il lucchetto della scheda video `strumenti/risultati/.gpu_lock`, un file di testo
che contiene «agente_grafi» e ha meno di 24 ore (regola del progetto); Ollama deve essere acceso.

    python -I valuta_statico.py --part test --out statico_test.json
    python -I agente_grafi.py --tasks test --out ../../risultati/grafi/agente_test
    python -I analisi_grafi.py finale ../../risultati/grafi/statico_test.json ../../risultati/grafi/agente_test
    python -I valuta_statico.py --part all --out statico_tutti.json
    python -I analisi_grafi.py statico ../../risultati/grafi/statico_tutti.json

- Se il secondo comando si ferma, si rilancia uguale: le corse già salvate non si rifanno.
- Il terzo comando salva `analisi_finale.json` accanto a `statico_test.json` e si rifiuta di riportare se manca
  qualcosa.
- Gli ultimi due danno la diagnosi descrittiva su tutti i 129 compiti; l'H1 che l'ultimo stampa su tutti i 129
  non conta (mescola sviluppo e prova).
- Dopo, un agente indipendente ricalcola H1-H3 dai file grezzi con un codice suo
  (`strumenti/risultati/grafi/prompt_verifica_finale.md`).

## 6. Cautele dichiarate prima

- La patch di riferimento è una soluzione, non l'unica: un punto diverso può essere corretto lo stesso.
- I 129 compiti pubblici sono pochi e di quattro progetti; la gara valuta su progetti privati.
- Si misura la localizzazione, non la correzione dei bug: il sistema ufficiale con Docker non gira su questo PC.
- Una sola corsa per compito e condizione, con decodifica deterministica: niente varianza tra semi.
- I compiti non sono del tutto indipendenti: alcuni condividono lo stesso commit (un compito di sviluppo di requests
  ha lo stesso commit di uno di prova; due compiti di prova di rich condividono un commit).
- Molte «issue» sono descrizioni di pull request che nominano già la correzione (per esempio «fix infinite loop in
  append»): la localizzazione può essere più facile che con un bug vero.
- Le classifiche sono state regolate sullo sviluppo: L con 9 combinazioni, G con 54. Molte combinazioni sono a pari
  merito e la scelta viene dalla regola di spareggio; i valori scelti stanno al bordo della griglia
  (`seeds_from_L` = 20, `alpha` = 0,5).
- L'elenco del progetto nel primo messaggio è più corto di quello ufficiale (solo il primo livello).
- Gli strumenti ufficiali sono ricostruiti dalla loro descrizione (HARNESS_README.md, §6.3), non dal codice
  originale. Scelte nostre dove la descrizione non basta: a pari merito vince il nome più corto; `edge_type` si
  confronta senza maiuscole; in `search_similar_code` il codice è tagliato a 500 caratteri, il simbolo cercato
  torna come primo risultato e `count` è dopo il taglio; `submit_locations` costa una chiamata (`submit_patch`
  ufficiale no); il primo messaggio non ha le sezioni ufficiali su budget e cartelle.
- Il motivo «connected in the code graph to X» di push_graph nomina un simbolo in più che push_lex non riceve: fa
  parte di ciò che il grafo dà.
- Il prompt di sistema è nostro (solo localizzazione), non quello ufficiale per correggere i bug. Il modello è la
  versione quantizzata QAT su una scheda da portatile, con Ollama al posto di vLLM: chi rifà la prova con il
  sistema ufficiale può ottenere numeri diversi.
- Le chiamate agli strumenti le legge Ollama; quando non ci riesce la risposta arriva vuota (§4b).
- `estrai_dati.py` estrae anche cartelle che lo studio non usa (`docker/`, `sandbox/`, `sample_submission/`); niente
  di scaricato viene eseguito.
- Il revisore indipendente è un agente Claude separato, perché Codex è bloccato fino al 10/11.

## 7. Riproducibilità

- Pacchetto della gara `gemma-4-developer-agent.zip` (21.929.289.087 byte): SHA-256
  06cec82cc9c9090edea659a31ce5ff92a6e96133c1fc152c06300e869a2e7421.
- `tasks.jsonl`: e4b3fd60f69dbc2b9213e54eeb9636db78aefe92c1d06269d73d9f5f8f3c8ad6.
- `MANIFEST.json` dell'estrazione: 29abdf5731ab08c8efb59121f4babcd359fca269b1048e8fc818e47059323755.
- `HARNESS_README.md`: 3d6e57a13234cb4e783ba24eaab486459af76e0923ea4c6607cd41cc8961bbbb.
- Id di sviluppo, in ordine, uniti da un a capo e senza a capo finale:
  9cd02e083d4e81e27c66a66ea32eda01d8f46875261aab599cbf342ecbc95cac. Id di prova, allo stesso modo:
  860b09e56584402823f2524fb5f99bbac92fdc6a59cdc5b3c3f3a62f30f4676e.
- Risultati di sviluppo citati in §4, calcolati con il codice congelato (le impronte del codice che contengono
  sono quelle dell'etichetta): `griglia_dev_v5.json`
  4520cb6e23ffa49e8233005e93c51156df1b50b644c11a09133883aac3cdbc61; `statico_dev_v6.json`
  4ac11730447c2254114d77083ad7872acd7ccc9a6de3c8a191abf51ca1597169. Le versioni precedenti danno le stesse tabelle
  di §4; cambia solo la diagnosi (`griglia_dev_v4` e `griglia_dev_v5` sono identiche tranne le impronte).
- Programmi: Python 3.12.10, numpy 2.5.2, scipy 1.18.1, regex 2026.9.3, Ollama 0.32.13, Windows 11.
- Ogni uscita (classifiche e corse) salva lo SHA-256 dei sei file di codice e di `tasks.jsonl`. Le impronte sono dei
  file con a capo LF, come sono salvati in git: su Windows con la conversione automatica in CRLF cambiano.

## Scostamenti

Nessuno.
