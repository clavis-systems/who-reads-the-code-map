# Pre-registration: who should read the code map? (FROZEN, 13/10/2026) — English translation

*Translation of `strumenti/agenti/grafi/PREMESSA_GRAFI.md` as frozen at git tag `congelamento-grafi-2026-10-13`
(commit 04dce8c). The Italian text is the authoritative version. This translation was made after the freeze, on
13/10/2026, and adds or removes nothing. Section numbers are the same. File and folder names are kept in Italian;
placeholders such as `path.py::Name` are translated. Dates are day/month (12/10 is 12 October). The Italian says
19:32: the file was saved at 19:32:59 and the tag created at 19:33.*

Status: frozen on 13/10/2026 at 19:32 with the git tag `congelamento-grafi-2026-10-13`, before any run on the test
tasks. Written and corrected by looking only at the development tasks, after three independent reviews (§4d). Any
change from here on must be written under "Deviations", with the reason.

## 1. Questions

For every task, the Gemma 4 Developer Agent competition provides a map of the code: a call graph with the text of
every function, plus one embedding per node. It also provides three tools that the agent can call to explore it.
Evidence published by competitors says these tools do not help: a large model rarely uses them, and the
semantic searches come back empty.

1. **Diagnosis.** Why do the official tools not help?
   - How well the map covers the functions to change.
   - How well semantic search can work with the text of a bug.
   - How well the graph connects the words of the bug to the places to change.
2. **Does the graph help?** Without a model: does ranking code locations with the graph give better results than
   text search alone?
3. **Who reads the map?** With Gemma 4 E4B on a laptop: is it better if the model calls the map tools (pull), or if
   the host reads the map and gives it a few hints (push)?

## 2. Data

- **Tasks.** The competition's 129 public tasks (`tasks.jsonl`), from fastapi, rich, requests and httpx, with the
  reference patch and the test patch. Apache 2.0 license.
- **Context.** Code snapshots at `base_commit`, graphs (NetworkX in JSON) and embeddings (npz), from the
  competition's data package, extracted with `estrai_dati.py` (`MANIFEST.json` with the SHA-256 of every file).
  The hashes are in §7.
- **Development/test split**, fixed before looking at the data: `dati.split_tasks`, seed 20261012.
  - For each repository the ids are sorted and shuffled with `random.Random("20261012:<repo>")`.
  - The first third, rounded up, is development; the rest is test.
  - Development: 45 tasks (fastapi 23, rich 16, requests 5, httpx 1). Test: 84 (fastapi 44, rich 32, requests 8).
  - All development is done on development tasks only. The test is run once, after the freeze.
- **Library only.** Only files of each repository's real package count (`dati.LIBRARY`): `fastapi/`, `rich/`,
  `src/requests/`, `src/httpx/` and `src/ahttpx/`. Tests, documentation examples (`docs_src/`, `examples/`),
  scripts and tools do not count.
- **Definitions** (`dati.definitions`) are the functions and classes a developer opens: those at module level and
  inside classes, also inside `if`, `try`, `with`, `for`, `while` or `match` blocks at those levels. A function or
  class written inside another function belongs to that function (the graph has few of them, with flattened names
  such as `fastapi.routing._serialize_item`).
- **The right places** (`dati.gold_locations`), from the reference patch:
  - a removed or modified line belongs to the innermost definition that contains it at `base_commit`;
  - an added line belongs to the innermost definition that contains it in the file after the patch; if that
    definition is new, to the nearest existing definition that contains it. So a new method counts for its class,
    and a new class at the end of the file counts only for the file;
  - blank lines, added or removed, do not count;
  - a file that the patch deletes entirely counts only as a file: its definitions are not places to fix;
  - a change outside every definition counts only at file level.
  - Edge cases: a comment changed after the last line of a function counts for the class or module that contains
    it (this happens, but in development and test it changes no right definition); a change of only the final
    newline and renamed files do not occur in the data.

## 3. Measures

- **Primary measure: the exact location.** A location found is right only if it is one of the patch's definitions
  itself. A module or a whole file never counts.
- **Secondary, lenient measure** (`dati.def_match`): the definition that directly contains the patch's definition
  (usually its class) or a direct member of it also counts. Which of the three cases occurred is reported
  (`dati.best_match_kind`: exact, member, container).
  - Why the exact one is primary: on development, big classes linked to all their methods (for example `FastAPI`
    or `Console`) often ended up in the graph's top 5 and earned the "container" point without saying where the
    bug is (review, §4d).
- **Rankings without a model.** A method ranks the library's functions and classes for a task. Primary: at least
  one exact location in the top 5 (exact@5). Secondary: exact@1, exact@10, lenient@5, file@5.
- **Agent.** Gemma submits up to 5 locations. Primary: at least one exact location. Secondary: lenient, file,
  calls, tokens, and the descriptive counts of §5.
- **On which tasks.** At function level only tasks with at least one definition in the patch count. At file level
  only tasks with at least one right file already present at `base_commit` (a new file cannot be found).
- **A single scoring rule for the agent:** `agente_grafi.agent_hit`, used during the runs and recomputed by the
  analysis from the submitted locations.
  - A location is read as `path.py::Qualified.name`, `path.py:Name`, `path.py` or a dotted name; quotes,
    backticks, `./`, `/workspace/` and trailing parentheses are ignored (`f(x)` counts as `f`); a number after the
    colon (`path.py:120`) counts only as the file.
  - A string is split into several locations only where, after a comma, a semicolon or a newline, a `.py` path
    begins; a list of dotted names is not split.
  - **Completion inside the file** (`resolve_in_file`), only if the name is not already a definition of the named
    file: a name inside a function of the file counts for that function (`handler.app` counts as `handler`, as for
    the right places); otherwise, if exactly one definition of that file ends with "." + that name, it counts as
    that definition (`models.py::prepare_body` counts as `PreparedRequest.prepare_body`). Without this, the push
    conditions were winning merely because they copied the class-qualified name from the hints (second review,
    §4d). The
    measure without completion remains as a secondary measure.

## 4. Methods without a model

- **Bug text for the rankings:** description and the task's hints text, without HTML comments and without web
  addresses (their
  words were noise: on development, an example with a sponsor link ended up in the top 5 in 11 tasks).
- **L:** BM25 of the bug text over the nodes' text and their names, split into sub-words; `k1` and `b` chosen on
  development.
- **A:** nodes named in the bug (`dati.anchors`), resolved the way the official tools do: exact name, then suffix,
  then case-insensitive, then substring. The project's own name ("FastAPI" in fastapi) does not count.
- **G:** random walk with restart (personalized PageRank) on the official graph taken as undirected.
  - It starts from the nodes of A and from the first `seeds_from_L` of L, with weight 1/position. It may also start
    from tests and examples, which often contain the bug's words and call the code to change.
  - `alpha` is the probability of returning to the starting point.
  - The score is divided by the node's degree to the power `degree_power`, so that nodes linked to everything do
    not win just for that.
- **E:** embedding neighbours of the starting nodes, as `search_similar_code` would do with the right name.
- **F:** rank fusion of the rankings listed in `fusion`. It is the "graph" method of H1.
- **Library only in the answers** (`localizza.keep_library`): nodes outside the library and nodes whose file is not
  found are removed from every ranking (in the fastapi maps these are the `docs_src` examples).

**Parameters chosen on development** (`valuta_statico.py --grid`, `griglia_dev_v5.json`, measure exact@5 on the 42
development tasks with at least one definition), in two steps fixed before seeing their results:
1. L alone: `k1` in (0.9; 1.2; 1.5) and `b` in (0.5; 0.75; 0.9). Six combinations tie at 0.476; on a tie the
   starting one wins: `k1` = 1.2, `b` = 0.75.
2. G with that L: `seeds_from_L` in (5, 10, 20), `alpha` in (0.15; 0.3; 0.5), `degree_power` in (0; 0.5; 1),
   `fusion` in ((G), (L, G)): 54 combinations, from 0.357 to 0.500. On a tie the winner is, in this order: fewer
   fused rankings, smaller `degree_power`, larger `alpha`, more seeds.
   Choice: `seeds_from_L` = 20, `alpha` = 0.5, `degree_power` = 0.5, `fusion` = (G), so F = G.

**Development with these parameters** (`statico_dev_v6.json`; not to be confused with the test). The "exact" and
"lenient" columns are over the 42 tasks with at least one definition; "file@5" over the 44 with at least one right
file already existing:

| Method | Exact@1 | Exact@5 | Exact@10 | Lenient@5 | File@5 |
|---|---|---|---|---|---|
| L | 0.190 | 0.476 | 0.500 | 0.524 | 0.795 |
| A | 0.214 | 0.238 | 0.262 | 0.310 | 0.364 |
| G | 0.262 | 0.500 | 0.524 | 0.571 | 0.795 |
| E | 0.190 | 0.214 | 0.214 | 0.286 | 0.477 |

On the G versus L pairs (exact@5) the discordant ones are 2 to 1 (exact McNemar p = 1.0). With the lenient measure
2 to 0. So on development, with the exact measure and a clean L, the graph adds little. The earlier versions
(`statico_dev_v2.json`, `statico_dev_v3.json`) gave 8 to 1 and 7 to 1, but with the lenient measure, the old rule for
the right places, unclean text and files outside the library (§4d).

**Diagnosis on development (45 tasks):**
- 42 tasks have at least one definition in the patch; 107 definitions: 84 functions, 9 async, 14 classes.
- 9 definitions are missing from the map: they are exactly the 9 async ones. In 3 tasks all are missing.
- Code names in the bug (clean text):
  - 34 tasks have at least one name;
  - in 29 at least one name matches a node;
  - in 24 at least one name is an embedding key, so `search_similar_code` could answer;
  - in 14 the bug names a definition of the patch (whole word).

## 4b. Agent

- **Model.** `gemma4:e4b-it-qat`, digest ee6656371218…, on Ollama 0.32.13 (the program stops if either differs),
  RTX 5060 Laptop GPU with 8 GB. Temperature 0, seed 1, context of 32,768 tokens (the competition's window), at
  most 1,024 tokens per reply, no extended reasoning.
- **First message**, the same for all conditions: the project's name, the bug and the task's hints text, then the
  list of the
  project's top-level entries ("Workspace Layout": a short version of the official section, which lists the first
  150 entries up to three levels). Without the list, in none and pull Gemma asked for wrong folders (26 errors in
  the smoke tests, none in push, whose hints contain paths).
- **Tools** (`agente_grafi.py`), all read-only on the snapshot at `base_commit`:
  - `list_files`: also accepts `/workspace` and the project's GitHub name (for example `psf/requests`) as the main
    folder, also at the start of a path (`psf/requests/src`);
  - `search_code`: substring or regular expression in the `.py` files, up to 5,000 characters of results. Regular
    expressions (at most 200 characters, on lines cut at 500) use the `regex` module, which stops after 5 seconds
    per search and returns an error instead of blocking the run;
  - `read_file`: at most 150 lines and 10,000 characters, like the official tool;
  - `submit_locations`: up to 5 locations, and it ends the run.
  - In the pull condition there are also the three official graph tools, with the behaviour described in
    HARNESS_README §6.3 and with the official prompt text. One addition of ours only: a name written in the
    location format our prompt asks for (`path.py::Name`) is translated into the node's name before the four
    official steps; every other name goes to the official steps as it is. Without it, in the smoke tests the only
    graph calls failed because of our format.
  - Wrong arguments or arguments of the wrong type go back to the model as an error: they never stop the run.
  - No code is executed.
- **Budget.** 20 tool calls, counting `submit_locations` too.
- **Turns without calls**, as in the official loop (HARNESS_README §5.3):
  - they cost no calls;
  - they receive the adapted official invitation ("Please continue your work using the available tools, or call
    submit_locations…"); if the reply is completely empty the invitation says so;
  - after more than 3 turns in a row without calls the exploration ends; a turn with a call resets the count.
    (In the official loop the text reply that closes a turn with calls does not count: here it counts, so our loop
    can end one turn earlier.)
  - To limit time, at most 60 turns in total.
- **The text written next to a call** stays in the log but is not sent back to the model. When sent back, with
  Ollama it made Gemma reply with an empty turn and then repeat the same call (§4c, experiment).
- **Budget warning**, as in the competition (HARNESS_README §6): when 10 calls or fewer remain, every tool reply
  carries the `budget_warning` notice.
- **Final submission.** If the exploration ends without a submission (budget, invitations or turns), there is one
  last turn in which the only tool offered is `submit_locations`. If the model answers in words, there is no
  submission.
- **Conversation memory.** The competition summarizes the conversation when it passes 14,336 tokens and keeps the
  last 5 events (HARNESS_README §7.2). Here, more simply and equally for all conditions: if the conversation's estimated
  token count passes 14,336 tokens, the tool outputs older than the last 5 become a short note, oldest first. The
  estimate is one token per 3 characters of the messages; in the smoke tests it was close to Ollama's true count
  (about 10% off, plus the tool descriptions, which it does not count). The system message, the bug and the host
  hints always stay. It is needed because, beyond the context window, Ollama throws away the oldest messages, bug
  included.
- **Host hints.** push_lex: the first 5 of L. push_graph: the first 5 of F. Each candidate has a short reason: "named in
  the issue", "its code shares words with the issue", "connected in the code graph to X" (X is a starting node) or
  "close in the code graph to the issue". If L has fewer than 5 library nodes, push_lex gives fewer.
- **Order of the four conditions** per task: `random.Random("20261012-<id>")`.
- **Ollama errors.** A run interrupted by an Ollama error (with the status and text of the HTTP response, if any) is
  saved apart (`<task>_<condition>.infra_<n>.json`) and the program stops; on restart that run is redone. After 3
  errors the run is recorded as missing. In the main analysis a missing run counts as a failure (0); the comparison
  without the tasks with missing runs is also reported, with their number.

## 4c. Smoke tests and experiment on development

They only serve to check the harness; their numbers do not enter the hypotheses. Folders in
`strumenti/risultati/grafi/`.

1. **`agente_dev_fumo`** (12/10): 3 tasks × 4 conditions, initial code (context 16,384). Problems found:
   - beyond the context window Ollama throws away the oldest messages, including the bug (a prompt reached
     16,275 tokens);
   - 10 calls unreadable for Ollama (`r"..."` in the arguments of `search_code`), all in one task;
   - 3 runs ended without a submission;
   - the hints proposed test functions;
   - in pull the graph tools were never called.
   Changes: context 32,768 and conversation memory, invitations, final submission, filter for test functions.
2. **`agente_dev_fumo2`** (12/10): 7 other tasks × 4 conditions, stopped after 16 runs. After reading a long file
   Gemma often replied empty and then re-read the same file. Change: the rules of the official loop.
3. **`agente_dev_fumo3`** (12-13/10): the same 7 tasks, 28 runs. 27 ended with a real submission; in one the budget
   ran out and at the final submission Gemma answered in words. In pull, 2 calls to the graph tools in 7 runs, both
   failed because of the `path.py::Name` format (fixed, §4b).
4. **Experiment on the text sent back** (`agente_dev_esperimento_testo`, 13/10): condition none on the same 7
   tasks, same code, once sending back to Gemma the text written next to the calls and once not.

   | Variant | Empty replies | Repeated calls | Runs ended by budget |
   |---|---|---|---|
   | text sent back | 17 (all of 1 token) | 28 | 2 of 7 |
   | text not sent back | 0 | 4 | 0 of 7 |

   Choice: the text is not sent back (§4b).
5. **`agente_dev_fumo4`** (13/10): 4 development tasks never used before (fastapi_14303, fastapi_14356, rich_3296,
   requests_7433) × 4 conditions, final code, analysed with `analisi_grafi.py agente --file`. All 16 runs ended
   with a real submission; no empty reply, no forced submission, no Ollama error, one configuration; from 1 to 4
   repeated calls per condition; in pull no call to the graph tools; about 19 seconds per run.
6. **`agente_dev_fumo5`** (13/10 evening): code after the second review (project list, alternative names of the
   main folder, name completion), 4 development tasks (requests_6644, requests_7205, fastapi_14266, rich_3130) × 4
   conditions. All 16 runs ended with a real submission; no empty reply; no "folder not found" error (there were 26
   before, in 5 tasks); one configuration; in pull still no call to the graph tools.
   The files of the experiment in item 4 have no configuration or hashes: they were made with the code of commit
   7a70170, with the text sent back as an option.
7. **`agente_dev_fumo6`** (13/10 evening): one task (requests_6644) × 4 conditions with the frozen code, only as a
   check: the 4 runs ended with a submission, no error.

## 4d. Independent review (13/10)

A separate Claude agent read the plan, the code, the development data and the logs, without touching the test
tasks. No leak from the test part; statistics and PageRank correct; the development numbers of that time
reproduced. Problems found and what changed:

- **Errors in the right places of 5 development tasks** (additions attributed to the previous line, blank lines counted):
  new rule on the file after the patch (§2).
- **Empty turns caused by the harness**: the text next to the calls is no longer sent back (§4b, §4c).
- **Malformed arguments that could stop the whole test**: they now go back to the model as an error.
- **Ollama errors never retried, analysis that did not check completeness**: runs redone up to 3 times; the final
  analysis refuses to report if tasks are missing, if the static part is not the test, if the runs do not all have
  the same configuration or if a hypothesis cannot be computed.
- **The measure rewarded "hub" classes**: the primary measure is now the exact one (§3); the graph also has
  `degree_power` (§4).
- **Our location format broke the graph tools in pull**: translated before the lookup (§4b).
- **Noisy and untuned L**: clean text, project name removed from A, a small grid for L too (§4).
- **Code outside the library**: excluded from the right places and from the rankings (§2, §4).
- **Reproducibility**: hashes of data, split and development results, program versions (§7); all code hashes in
  every output.
- Minor notes addressed in §3 (reading the locations), §6 (cautions) and in the code (limits of regular expressions).

**Second review (13/10 evening).** Another Claude agent, new, re-checked the fixes (commit 7a70170). They were
correct and the development numbers, the grid, the hashes and the experiment reproduced. 1,658 combinations of
malformed arguments produced no exceptions; the retry of Ollama errors, simulated without a model, worked. To check
the rule for the right places it also counted some properties of the test patches, only as totals, without
per-task details and without any measure of the methods: how many apply, how many delete whole files, how many
change nested functions or functions inside blocks. Three fixes below also come from those counts. Problems found
and changes:
- **The exact score rewarded copying the hints' names**: completion of the name inside its file (§3); the measure
  without completion stays secondary.
- **Functions inside `if`/`try` blocks invisible**: they now count (§2).
- **Files deleted entirely**: they count only as files (§2).
- **Nested functions**: they count for the function that contains them (§2).
- **Friction against none and pull**: the project's top-level list for everyone; `list_files` accepts `/workspace`
  and the project's GitHub name (§4b).
- **Regular expressions that can block a run**: `regex` module with a time limit (§4b).
- Minor:
  - the translation of names in the graph tools applies only to `path.py::Name`;
  - the final analysis checks that all outputs have the same code, equal to the running code, and the same
    parameters;
  - missing runs counted as failures, with a comparison without them;
  - exact p-values up to Holm, rounded only when printed;
  - result saved in `analisi_finale.json`;
  - diagnosis on all 129 tasks with a dedicated command (§5);
  - bug names searched as whole words in the diagnosis;
  - HTTP status of Ollama errors recorded;
  - plan texts corrected.

**Third check (same reviewer, 13/10 evening)** on the fixes of commit fb11f97: no blocking or important problem,
go-ahead for the freeze. Minor notes fixed before freezing:
- hidden folders of the snapshots (`.github`) no longer lose the initial dot;
- in the diagnosis, a name with a dot in front (`Segment._split_cells`) counts;
- a network error while reading an Ollama HTTP response counts as an Ollama error;
- name completion takes a nested function to the function that contains it;
- `list_files` accepts the GitHub name also at the start of a path;
- code documentation, a test of the time limit and plan texts.
Note not fixed, only declared: after the 5-second limit each line still has 10 milliseconds, so a search close to
the limit may depend on the machine's speed; the measured searches last at most 0.25 seconds.

## 5. Hypotheses

All are evaluated on the 84 test tasks; at function level only tasks with at least one definition in the patch
count. Measure: the exact location (§3). The tests are exact, two-sided McNemar tests on the pairs of the same task.
The three main hypotheses are corrected together with Holm, α = 0.05.

- **H1, without a model.** F (the graph, §4) has a higher exact@5 than L.
- **H2, with Gemma.** push_graph finds an exact location more often than pull.
- **H3, with Gemma.** push_graph finds an exact location more often than push_lex.
- **When a hypothesis is confirmed:** the difference goes in the predicted direction and the Holm-corrected p is
  below 0.05 (`analisi_grafi.py finale`). Otherwise it is written that it is not confirmed, with the numbers.
- **Descriptive:**
  - the diagnosis of §4 on the test tasks and on all 129;
  - the same pairs with the lenient measure, and which kind of match (exact, member, container);
  - for the agent, the same pairs without name completion (§3) and without the tasks with missing runs;
  - the other pairs (push_graph versus none, push_lex versus none, push_lex versus pull, pull versus none);
  - the file level;
  - in pull, how many runs use the graph tools and how many replies come back empty or with an error;
  - per condition: calls, identical repeated calls, turns, invitations, empty replies, forced submissions, how the
    exploration ends, shortened outputs, tokens, seconds, missing runs.

**How the test is run** (once only, after the freeze tag), from the folder `strumenti/agenti/grafi`. It needs the
GPU lock `strumenti/risultati/.gpu_lock`, a text file that contains "agente_grafi" and is less than 24 hours old
(project rule); Ollama must be running.

    python -I valuta_statico.py --part test --out statico_test.json
    python -I agente_grafi.py --tasks test --out ../../risultati/grafi/agente_test
    python -I analisi_grafi.py finale ../../risultati/grafi/statico_test.json ../../risultati/grafi/agente_test
    python -I valuta_statico.py --part all --out statico_tutti.json
    python -I analisi_grafi.py statico ../../risultati/grafi/statico_tutti.json

- If the second command stops, it is relaunched as it is: the runs already saved are not redone.
- The third command saves `analisi_finale.json` next to `statico_test.json` and refuses to report if something is
  missing.
- The last two give the descriptive diagnosis on all 129 tasks; the H1 that the last one prints over all 129 does
  not count (it mixes development and test).
- Afterwards, an independent agent recomputes H1-H3 from the raw files with its own code
  (`strumenti/risultati/grafi/prompt_verifica_finale.md`).

## 6. Cautions declared beforehand

- The reference patch is one solution, not the only one: a different place can be right too.
- The 129 public tasks are few and come from four projects; the competition evaluates on private projects.
- Localization is measured, not bug fixing: the official system with Docker does not run on this PC.
- One run per task and condition, with deterministic decoding: no variance across seeds.
- The tasks are not fully independent: some share the same commit (a development task of requests has the same
  commit as a test one; two test tasks of rich share a commit).
- Many "issues" are pull-request descriptions that already name the fix (for example "fix infinite loop in
  append"): localization may be easier than with a real bug.
- The rankings were tuned on development: L with 9 combinations, G with 54. Many combinations tie and the choice
  comes from the tie-break rule; the chosen values are at the edge of the grid (`seeds_from_L` = 20, `alpha` = 0.5).
- The project list in the first message is shorter than the official one (top level only).
- The official tools are rebuilt from their description (HARNESS_README.md, §6.3), not from the original code. Our
  choices where the description is not enough: on a tie the shortest name wins; `edge_type` is compared
  case-insensitively; in `search_similar_code` the code is cut at 500 characters, the searched symbol comes back as
  the first result and `count` is after the cut; `submit_locations` costs a call (the official `submit_patch` does
  not); the first message does not have the official sections on budget and folders.
- push_graph's reason "connected in the code graph to X" names one more symbol that push_lex does not receive: it is
  part of what the graph gives.
- The system prompt is ours (localization only), not the official one for fixing bugs. The model is the quantized
  QAT version on a laptop GPU, with Ollama instead of vLLM: whoever repeats the test with the official system may
  get different numbers.
- Tool calls are parsed by Ollama; when it cannot parse one, the reply arrives empty (§4b).
- `estrai_dati.py` also extracts folders the study does not use (`docker/`, `sandbox/`, `sample_submission/`);
  nothing downloaded is executed.
- The independent reviewer is a separate Claude agent, because Codex is blocked until 10 November (10/11).

## 7. Reproducibility

- Competition package `gemma-4-developer-agent.zip` (21,929,289,087 bytes): SHA-256
  06cec82cc9c9090edea659a31ce5ff92a6e96133c1fc152c06300e869a2e7421.
- `tasks.jsonl`: e4b3fd60f69dbc2b9213e54eeb9636db78aefe92c1d06269d73d9f5f8f3c8ad6.
- Extraction `MANIFEST.json`: 29abdf5731ab08c8efb59121f4babcd359fca269b1048e8fc818e47059323755.
- `HARNESS_README.md`: 3d6e57a13234cb4e783ba24eaab486459af76e0923ea4c6607cd41cc8961bbbb.
- Development ids, in order, joined by a newline and without a final newline:
  9cd02e083d4e81e27c66a66ea32eda01d8f46875261aab599cbf342ecbc95cac. Test ids, the same way:
  860b09e56584402823f2524fb5f99bbac92fdc6a59cdc5b3c3f3a62f30f4676e.
- Development results cited in §4, computed with the frozen code (the code hashes they contain are those of the
  tag): `griglia_dev_v5.json` 4520cb6e23ffa49e8233005e93c51156df1b50b644c11a09133883aac3cdbc61;
  `statico_dev_v6.json` 4ac11730447c2254114d77083ad7872acd7ccc9a6de3c8a191abf51ca1597169. The earlier versions give
  the same tables of §4; only the diagnosis changes (`griglia_dev_v4` and `griglia_dev_v5` are identical except for
  the hashes).
- Programs: Python 3.12.10, numpy 2.5.2, scipy 1.18.1, regex 2026.9.3, Ollama 0.32.13, Windows 11.
- Every output (rankings and runs) saves the SHA-256 of the six code files and of `tasks.jsonl`. The hashes are of
  the files with LF line endings, as stored in git: on Windows with automatic conversion to CRLF they change.

## Deviations

None.
