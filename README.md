# Who reads the code map?

Code, frozen plans, reviews, model answers and results of my study on the code maps of the Kaggle **Gemma 4
Developer Agent** competition. Every task there comes with a map of its repository: a call graph with the code of
each function, an embedding per node, and three tools that the agent can call to read it. I asked whether this map
helps a small model on a laptop find the function that must change, and if not, why.

Author: Emanuele Rizzan, independent researcher (GitHub: clavis-systems). The full write-up is being submitted to
the Kaggle Gemma 4 Developer Agent Paper Track; I will add it here after the submission.

## What I found

Four steps, each with its rules written down and committed before I looked at the data. Measure: the exact function
or class that the reference patch changes; 84 held-out test tasks, 78 of them change a definition.

| Step | Result |
|---|---|
| 1. Without a model: does a walk on the map rank the right function higher than word search (BM25)? | **No.** Exact function in the top 5: words 40, graph 36 (where they disagree 10 to 6; Holm p = 0.91) |
| 2. Gemma 4 E4B as an agent: 5 hints from the map (push_graph) against the official map tools (pull) and against 5 hints from word search (push_lex) | **No** gain from the map: push_graph 31, pull 31, push_lex 40, no map 29. With the official tools, Gemma called a map tool in 1 of 84 runs |
| 3. Probe, development only: can Gemma tell which neighbour on the map leads to the bug? | Barely: right in 39.3% of 613 questions against 31.0% by chance (threshold to continue: 65%). It says "it is here" at 87% of the right functions but also at 47% of the wrong ones |
| 4. Line-up: Gemma only answers "must this change? yes/no" for the top 20 word-search candidates | Right function first in 28 of 78 tasks against 17 for word search (18 to 7; p = 0.043, Holm 0.087): **not confirmed**. Against the push_lex agent with the same number of locations: 37 against 40, **not confirmed** |

Over all 129 tasks: the map has no `async` functions at all (31 of the 415 functions to change are missing), the
official `search_similar_code` needs an exact symbol name although its description says "by keyword", and the call
edges are not reliably directed.

**A fake advantage that disappeared.** On development tasks my first version showed the graph winning 8 tasks to 1,
because I counted as correct the class that contains the right method. With the exact measure it became 2 to 1 on
development, and 6 to 10 on the frozen test.

## How the study was run

1. **Split.** The 129 tasks were split once, with a seeded shuffle per project: 45 for development, 84 for the
   test. Everything I tuned, I tuned on the 45.
2. **Steps 1–2.** Plan `strumenti/agenti/grafi/PREMESSA_GRAFI.md` (Italian, my language; English translation in
   `PREREGISTRATION_EN.md`), reviewed three times by separate Claude agents (eight blocking problems found and fixed),
   frozen with the git tag `congelamento-grafi-2026-10-13` (commit 04dce8c) in my private working repository. The test ran once, 13/10/2026 19:33 to
   14/10/2026 09:58, with two pauses I made by hand and one infrastructure error (the GPU ran out of memory) after
   which the same command was relaunched, as the plan says. All 336 runs are complete and share one configuration.
3. **Step 3, probe** (`strumenti/agenti/bussola/`, plan `PIANO_SONDA.md`, result `RISULTATO_SONDA.md`): development
   tasks only, frozen in commit 38f7478 before the answers.
4. **A history map** (`strumenti/agenti/storia/`, plan `PIANO_STORIA.md`, result `RISULTATO_STORIA.md`): development
   only, frozen in commit 67e2445 before the scores. It did not pass its thresholds.
5. **Step 4, line-up** (`strumenti/agenti/fiuto/`): development plan `PIANO_FIUTO.md` (commit e28cb4c), result
   `RISULTATO_FIUTO.md`; then the test plan `PIANO_FIUTO_PROVA.md`, reviewed by a separate agent (three blocking
   problems fixed, including one that favoured my method) and frozen with the tag `congelamento-fiuto-2026-10-14`
   (commit 0f32f14). This is declared as the second use of the test tasks. It ran once; result
   `RISULTATO_FIUTO_PROVA.md`.
6. **Independent recomputation.** Separate agents with their own code recomputed from the raw files every number of
   steps 1–2 (including the score of each of the 336 agent runs) and the two hypotheses of step 4: no difference.
   The probe and the walk arm of step 4 were not recomputed independently. The recomputation scripts are not
   included; the raw files are, so anyone can redo it.

The tags and commit ids cited here belong to my private working repository, which also holds unrelated projects.
This public repository starts from copies of the frozen files: `PROVENANCE.md` lists their SHA-256, and every
output file records the SHA-256 of the code that produced it, so the match can be checked without my history.

The plans and results of steps 3–4 are in Italian; this README summarizes them in English.

## What is in this repository

| Folder or file | Content |
|---|---|
| `strumenti/agenti/grafi/` | Steps 1–2: the frozen code, its tests and the plan |
| `strumenti/agenti/bussola/`, `storia/`, `fiuto/` | Probe, history map and line-up: code, plans, results |
| `strumenti/risultati/grafi/` | Static rankings (`statico_test.json`, `statico_tutti.json`, development grids), the 336 agent runs with every message (`agente_test/`), the run log and the final analysis (`analisi_finale.json`) |
| `strumenti/risultati/bussola/` | The probe's 2,167 model answers with first-token probabilities, summaries and the question build record (hashes) |
| `strumenti/risultati/storia/` | The history-map evaluation |
| `strumenti/risultati/fiuto/` | Every yes/no answer with its token probabilities (development and test), configurations and summaries |
| `rapporto/` | Figure scripts and figures, exploratory analyses (labelled as such) |
| `PREREGISTRATION_EN.md` | English translation of the first frozen plan (the Italian text is authoritative) |
| `esterni/gemma4_agent/` | Only a note: the competition data go here (not redistributed, see below) |

## How to reproduce

You need Python 3.12 with numpy, scipy and regex, the competition data, and, for the model parts, Ollama 0.32.13
with `gemma4:e4b-it-qat` (the programs stop if the model digest or the version differ).

1. Download `gemma-4-developer-agent.zip` from the competition page (SHA-256 in `PREREGISTRATION_EN.md` §7) and
   extract it safely, without running anything in it:

       python -I strumenti/agenti/grafi/estrai_dati.py gemma-4-developer-agent.zip esterni/gemma4_agent/dati

   Then copy `esterni/gemma4_agent/dati/tasks.jsonl` to `esterni/gemma4_agent/tasks.jsonl`.
2. Tests: from `strumenti/agenti/grafi`, `python -m unittest test_dati test_agente_grafi test_analisi_grafi`.
3. Steps 1–2: the commands of the plan (§5), from `strumenti/agenti/grafi`. The agent part needs a file
   `strumenti/risultati/.gpu_lock` containing `agente_grafi` (a rule of my working folder to share the GPU).
4. Probe: from `strumenti/agenti/bussola`, `python sonda.py costruisci` rebuilds the questions and writes their
   SHA-256 into `sonda_costruzione.json` (it overwrites the published file: keep a copy to compare); then
   `python sonda.py esegui`, `python sonda.py riassumi`, `python esplora_sonda.py`.
5. History map: from `strumenti/agenti/storia`, `python storia.py estrai`, `storia`, `valuta` (about 6 GB of disk).
   It copies only the git objects and references of each snapshot into a new bare repository, never checks
   anything out and runs no hook.
6. Line-up: from `strumenti/agenti/fiuto`, `python fiuto.py riassumi` (development) and
   `python fiuto.py riassumi prova` (test) rebuild every ranking and statistic from the saved answers without the
   model; `esegui` asks the model again.

No code from the competition data or from the model is ever executed: the agent can only list, search and read
files of the snapshot.

## Data and licences

See `DATA_LICENSES.md`. In short: the competition data are under Apache 2.0 and are not redistributed here, except
the parts that appear inside the agent run logs (issue texts and excerpts of the repositories' code that the agent
read). The probe's question file, which contains issue texts and code, is not included; `sonda.py costruisci`
rebuilds it, and its SHA-256 is recorded in `sonda_costruzione.json`.

## Use of AI

I designed and directed this study. Claude (Anthropic) wrote most of the code and the analyses under my direction,
and separate Claude agents did the independent reviews. Gemma 4 E4B is the model under test.
