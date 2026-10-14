# Provenance

- Tag in my private working repository: `congelamento-grafi-2026-10-13`, commit 04dce8c (13/10/2026, 19:32 CEST), made before any
  run on the test tasks.
- The files in `strumenti/agenti/grafi/` are byte-identical to the tagged files (`git archive` of the tag, with
  LF line endings). Their SHA-256, which every output file also records under `code_sha256`:

| File | SHA-256 |
|---|---|
| dati.py | `19822f47b395be35ece5c59c9c68503d153fe377e3474a0f43c99dcc87a31862` |
| istantanee.py | `169d20daaec0facabb65d811600bee65eb95c69242a3e3293a632f3eb10af4b0` |
| localizza.py | `1d4396593e44c09fe31b1a2a35f887f08f5b16baa7ace582f008420fe6587c01` |
| valuta_statico.py | `a22af5988ff659d200324a333c04f851d32816ab2b5eeed4af1cc1519afdf872` |
| agente_grafi.py | `0ff1746c602f636360ac07ce5e583f6ff9679abc4163f07e0fb4fbc2c569b893` |
| analisi_grafi.py | `65875c4613565f5a18d6b85b11936a6fd262c8f3552eed5463e1de82f95ef2ee` |

- Competition data: SHA-256 of the zip, of `tasks.jsonl`, of the extraction manifest and of the harness
  description in `PREREGISTRATION_EN.md` §7.
- Test run: started 13/10/2026 at 19:33; paused by hand at 19:54 (37 of 336 runs saved); resumed at 21:32;
  stopped at 21:41 by an Ollama error (CUDA out of memory, the model server stopped), saved as
  `fastapi_14873_none.infra_1.json`; resumed at 21:41 with the same command, as the plan says; paused by hand once more overnight and resumed
  with the same command; finished on 14/10/2026 at 09:58 (last write of `agente_test.log`). 336 of 336 runs.
- Exploratory analyses (`rapporto/esplorative_grafi.py`) were decided after the test run and are labelled as such.

## Later steps (probe, history map, line-up)

- Probe: plan and code committed in 38f7478 before any answer. `sonda_costruzione.json` and `sonda_config.json`
  record the SHA-256 of `sonda.py` as `a1886a46…`: it was computed on my Windows working copy, which had CRLF line
  endings. The LF file published here gives the same hash after converting LF to CRLF.
- History map: plan and code committed in 67e2445 before any score; `storia.py` SHA-256 `3e9c0579…` (as recorded in
  `storia_valutazione.json`).
- Line-up: development plan e28cb4c; test plan frozen with the tag `congelamento-fiuto-2026-10-14` (commit 0f32f14);
  `fiuto.py` SHA-256 `b04c938845efa1ecf75c9480d76a6bdce4441ccc064fb08d4dcf1db5f538b389`, as recorded in
  `fiuto_prova_config.json`. Test run on 14/10/2026 from 19:03 to 19:39, one run, no interruption.
- The files in `strumenti/agenti/bussola/`, `storia/` and `fiuto/` are `git archive` copies of my working repository
  (LF line endings).
