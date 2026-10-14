"""EXPLORATORY analyses of the code-graph study, decided AFTER the frozen test run (not part of the plan).

    python -I rapporto/esplorative_grafi.py

They only describe the frozen outputs (strumenti/risultati/grafi/statico_test.json, statico_tutti.json); nothing here
changes a hypothesis or a measure. Results are written to strumenti/risultati/grafi/esplorative.json.
"""

import collections
import json
import os
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "strumenti", "risultati", "grafi")
sys.path.insert(0, os.path.join(ROOT, "strumenti", "agenti", "grafi"))
import dati  # noqa: E402
import localizza  # noqa: E402
import valuta_statico  # noqa: E402


def load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    rows = [r for r in load("statico_test.json")["tasks"] if r["gold_defs"]]
    words = lambda r: r["scores"]["L"]["fn_exact@5"]  # noqa: E731
    graph = lambda r: r["scores"]["F"]["fn_exact@5"]  # noqa: E731
    groups = {"words_only": [r for r in rows if words(r) and not graph(r)],
              "graph_only": [r for r in rows if graph(r) and not words(r)],
              "both": [r for r in rows if words(r) and graph(r)],
              "neither": [r for r in rows if not words(r) and not graph(r)]}
    out = {"note": "exploratory, after the frozen test run", "groups": {}}
    for name, g in groups.items():
        out["groups"][name] = {
            "tasks": len(g),
            "issue_names_a_gold_def": sum(r["issue_names_a_gold_def"] for r in g),
            "anchor_is_gold": sum(r["hops_anchor_to_gold"] == 0 for r in g),
            "gold_reachable_within_6_hops": sum(r["hops_anchor_to_gold"] is not None for r in g),
            "median_gold_defs": statistics.median([len(r["gold_defs"]) for r in g]) if g else 0,
            "repos": dict(collections.Counter(r["repo"].rsplit("/", 1)[-1] for r in g))}
    out["per_repo"] = {}
    for repo in ("fastapi", "rich", "requests"):
        rr = [r for r in rows if r["repo"].endswith("/" + repo)]
        out["per_repo"][repo] = {"tasks": len(rr), "words": sum(map(words, rr)), "graph": sum(map(graph, rr))}
    tasks = {t["instance_id"]: t for t in dati.load_tasks(valuta_statico.TASKS)}
    share, hubs = collections.defaultdict(list), collections.Counter()
    for r in rows:
        t = tasks[r["task"]]
        g, _emb, files = valuta_statico.task_inputs(t)
        seeds = localizza.rank_lexical(g, t)[:localizza.PARAMS["seeds_from_L"]]
        lib = 0
        for n in seeds:
            f = localizza.node_file(n, files)
            lib += f is not None and dati.in_library(f, t["repo"]) and not dati.is_test_path(f)
        share[t["repo"].rsplit("/", 1)[-1]].append(1 - lib / max(1, len(seeds)))
        if words(r) and not graph(r):
            hubs.update(r["top5"]["F"])
    out["non_library_share_of_seeds"] = {k: round(sum(v) / len(v), 3) for k, v in share.items()}
    out["graph_top5_when_only_words_win"] = hubs.most_common(10)
    tutti = load("statico_tutti.json")["tasks"]
    with_defs = [r for r in tutti if r["gold_defs"]]
    out["all_129"] = {"hops_anchor_to_gold": dict(collections.Counter(str(r["hops_anchor_to_gold"])
                                                                      for r in with_defs))}
    with open(os.path.join(OUT, "esplorative.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
