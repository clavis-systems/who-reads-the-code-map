# Data and licences

| Source | Licence | What this repository contains |
|---|---|---|
| Kaggle competition data, Gemma 4 Developer Agent (`gemma-4-developer-agent.zip`: tasks, code graphs, embeddings, repository snapshots, harness description) | Apache 2.0 | Not redistributed as files. The run logs include the issue texts and hints of the test tasks (the first message to the model) and the outputs of the tools, which quote nodes of the graphs. The static results list task ids, node names and gold definitions derived from the reference patches |
| fastapi (`fastapi/fastapi`) | MIT | Excerpts of its source code inside the run logs (what the agent read or searched), and function names in the results |
| rich (`Textualize/rich`) | MIT | As above |
| requests (`psf/requests`) | Apache 2.0 | As above |
| httpx (`encode/httpx`) | BSD 3-Clause for the published project; the competition snapshot of this development branch has no licence file | Nothing of its code: the test part has no httpx task, and the development smoke tests (where httpx excerpts appear) are left out. Only node names appear in the probe and line-up answers |
| Gemma 4 E4B (`gemma4:e4b-it-qat`) | Apache 2.0 (model card) | The model's replies in the run logs, and its short answers with first-token probabilities in the probe and line-up files, which I release with the rest of this repository under Apache 2.0 |

The excerpts are unchanged copies of what the tools returned during the runs, cut by the tools' own limits (150
lines or 10,000 characters per read, 5,000 characters per search). The copyright notices of the four projects
apply to those excerpts.

My own code, texts and results in this repository are released under Apache 2.0 (`LICENSE`).

The probe and line-up answer files contain task ids, node names, the model's short replies and token probabilities,
but not the prompts. The probe's question file (issue texts and code) is not included and can be rebuilt from the
competition data.
