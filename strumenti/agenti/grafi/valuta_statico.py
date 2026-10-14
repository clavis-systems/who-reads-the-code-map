"""Static evaluation (PREMESSA_GRAFI.md, sections 3-4): diagnosis of the official map and rankings without a model.

    python -I valuta_statico.py --part dev --out statico_dev.json

For each task: gold files and definitions from the reference patch, their presence in the graph, the issue anchors
and how the official tools would resolve them, and hit@1/5/10 of every ranking at function and file level.
"""

import argparse
import collections
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dati  # noqa: E402
import istantanee  # noqa: E402
import localizza  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DATA = os.path.join(ROOT, "esterni", "gemma4_agent", "dati")
TASKS = os.path.join(ROOT, "esterni", "gemma4_agent", "tasks.jsonl")
OUT_DIR = os.path.join(ROOT, "strumenti", "risultati", "grafi")
KS = (1, 5, 10)
CODE = ("dati.py", "istantanee.py", "localizza.py", "valuta_statico.py", "agente_grafi.py", "analisi_grafi.py")


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code_hashes():
    """SHA-256 of the study's code, saved in every output."""
    return {f: sha256_file(os.path.join(HERE, f)) for f in CODE}


def task_inputs(task):
    """The zip keeps one graph and one embedding file per commit: <repo short name>_<base_commit>.json/.npz."""
    iid = task["instance_id"]
    key = f"{iid.split('_')[0]}_{task['base_commit']}"
    graph = localizza.load_graph(os.path.join(DATA, "graphs", f"{key}.json"))
    emb_path = os.path.join(DATA, "embeddings", f"{key}.npz")
    emb = localizza.load_embeddings(emb_path) if os.path.exists(emb_path) else {}
    files = istantanee.read_snapshot(os.path.join(DATA, "snapshots", f"{iid}.tgz"))
    return graph, emb, files


def hops(graph, sources, targets, limit=6):
    """Fewest undirected edges from any source node to any target node (None if more than limit or unreachable)."""
    targets = set(targets)
    if not sources or not targets:
        return None
    seen, frontier = set(sources), list(dict.fromkeys(sources))
    for depth in range(limit + 1):
        if targets & set(frontier):
            return depth
        nxt = []
        for n in frontier:
            for m in [t for t, _ in graph["out"].get(n, [])] + [s for s, _ in graph["inc"].get(n, [])]:
                if m not in seen:
                    seen.add(m)
                    nxt.append(m)
        frontier = nxt
    return None


def diagnose(task, graph, emb, files):
    gold = dati.gold_locations(task["patch"], files.get, task["repo"])
    gnodes = localizza.gold_nodes(graph, gold["defs"])
    kinds = collections.Counter(k for _, k in gold["defs"])
    missing = [(n, k) for n, k in gold["defs"] if n not in graph["text"]]
    text = localizza.issue_text(task)
    anchors = dati.anchors(text)
    resolved = [a for a in anchors if localizza.resolve(graph, a)]
    emb_keys = [a for a in anchors if any(key == a or key.endswith("." + a) for key in emb)]
    anchor_nodes = localizza.rank_anchors(graph, task)
    return {"hops_anchor_to_gold": hops(graph, anchor_nodes, gnodes),
            "gold_files": gold["files"], "gold_defs": [list(x) for x in gold["defs"]],
            "gold_new_files": gold["new_files"], "gold_unapplied": gold["unapplied"],
            "module_level_files": gold["module_level"], "gold_kinds": dict(kinds), "gold_nodes": gnodes,
            "gold_defs_missing_from_graph": [list(x) for x in missing], "graph_nodes": len(graph["ids"]),
            "graph_edges": sum(len(v) for v in graph["out"].values()), "emb_nodes": len(emb),
            "anchors": anchors, "anchors_resolved": resolved, "anchors_usable_by_similar_code": emb_keys,
            "issue_names_a_gold_def": any(re.search(r"(?<!\w)" + re.escape(n.rsplit(".", 1)[-1]) + r"\b", text)
                                          for n, _ in gold["defs"]),
            "gold_deleted_files": gold["deleted_files"]}


def score(rankings, gold_defs, gold_files, files):
    """fn_exact@k (primary), fn@k (also the containing definition or a direct member), the kind of the best match
    in the top 5, and file@k over the gold files that exist at base_commit."""
    old_files = [f for f in gold_files if f in files]
    out = {}
    for name, ranking in rankings.items():
        franking = localizza.file_ranking(ranking, files)
        out[name] = {f"fn_exact@{k}": dati.fn_hit_at(ranking, gold_defs, gold_files, k, exact=True) for k in KS}
        out[name].update({f"fn@{k}": dati.fn_hit_at(ranking, gold_defs, gold_files, k) for k in KS})
        out[name].update({f"file@{k}": dati.hit_at(franking, old_files, k) for k in KS})
        out[name]["kind@5"] = dati.best_match_kind(ranking[:5], gold_defs, gold_files)
    return out


# Development grids (PREMESSA §4), measure fn_exact@5. First L alone, then G with the chosen L.
L_GRID = {"k1": (0.9, 1.2, 1.5), "b": (0.5, 0.75, 0.9)}
G_GRID = {"seeds_from_L": (5, 10, 20), "alpha": (0.15, 0.3, 0.5), "degree_power": (0.0, 0.5, 1.0),
          "fusion": (("G",), ("L", "G"))}


def _rate(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / max(1, len(xs))


def grid_search(tasks, keep):
    """Development only. Stage 1: BM25 k1 and b for L. Stage 2, with that L: the graph walk's seeds, alpha and degree
    power, and the fusion. Best fn_exact@5 wins; ties go to the simpler choice in this order: default BM25 (1.2,
    0.75), then fewer fused rankings, smaller degree_power, larger alpha, more seeds."""
    import itertools
    dev = [t for t in tasks if t["instance_id"] in keep]
    l_hits = {c: [] for c in itertools.product(L_GRID["k1"], L_GRID["b"])}
    for task in dev:
        graph, _emb, files = task_inputs(task)
        gold = dati.gold_locations(task["patch"], files.get, task["repo"])
        bm25 = localizza.lexical_index(graph)
        for k1, b in l_hits:
            L = localizza.keep_library(localizza.rank_lexical(graph, task, bm25, k1, b), files, task["repo"])
            l_hits[(k1, b)].append(dati.fn_hit_at(L, gold["defs"], gold["files"], 5, exact=True))
        print("L", task["instance_id"], flush=True)
    l_table = sorted(l_hits, key=lambda c: (-_rate(l_hits[c]), c != (1.2, 0.75), c))
    k1, b = l_table[0]
    combos = list(itertools.product(G_GRID["seeds_from_L"], G_GRID["alpha"], G_GRID["degree_power"],
                                    G_GRID["fusion"]))
    g_hits = {c: [] for c in combos}
    for task in dev:
        graph, _emb, files = task_inputs(task)
        gold = dati.gold_locations(task["patch"], files.get, task["repo"])
        L = localizza.rank_lexical(graph, task, None, k1, b)
        A = localizza.rank_anchors(graph, task)
        Lf = localizza.keep_library(L, files, task["repo"])
        for n_seeds, alpha, power in itertools.product(G_GRID["seeds_from_L"], G_GRID["alpha"],
                                                       G_GRID["degree_power"]):
            seeds = list(dict.fromkeys(A + L[:n_seeds]))       # as all_rankings: any node may seed the walk
            G = localizza.rank_graph(graph, seeds, alpha, power) if seeds else []
            named = {"L": Lf, "G": localizza.keep_library(G, files, task["repo"])}
            for fusion in G_GRID["fusion"]:
                F = localizza.fuse([named[x] for x in fusion], localizza.PARAMS["rrf_k"])
                g_hits[(n_seeds, alpha, power, fusion)].append(dati.fn_hit_at(F, gold["defs"], gold["files"], 5,
                                                                               exact=True))
        print("G", task["instance_id"], flush=True)
    g_table = sorted(g_hits, key=lambda c: (-_rate(g_hits[c]), len(c[3]), c[2], -c[1], -c[0]))
    return {"measure": "fn_exact@5", "tasks": len(dev),
            "L_grid": [{"fn_exact@5": _rate(l_hits[c]), "k1": c[0], "b": c[1]} for c in l_table],
            "G_grid": [{"fn_exact@5": _rate(g_hits[c]), "seeds_from_L": c[0], "alpha": c[1], "degree_power": c[2],
                        "fusion": list(c[3])} for c in g_table],
            "chosen": {"k1": k1, "b": b, "seeds_from_L": g_table[0][0], "alpha": g_table[0][1],
                       "degree_power": g_table[0][2], "fusion": list(g_table[0][3])}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--part", choices=("dev", "test", "all"), required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--grid", action="store_true", help="development only: compare parameter combinations")
    a = p.parse_args()
    if a.grid:
        if a.part != "dev":
            raise SystemExit("the parameter grid is run on development tasks only")
        tasks = dati.load_tasks(TASKS)
        dev, _ = dati.split_tasks(tasks)
        out = grid_search(tasks, set(dev))
        out["code_sha256"] = code_hashes()
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, a.out), "x", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, indent=1)
        print(json.dumps({"L": out["L_grid"][:4], "G": out["G_grid"][:8], "chosen": out["chosen"]}, indent=1))
        return
    tasks = dati.load_tasks(TASKS)
    dev, test = dati.split_tasks(tasks)
    keep = set(dev if a.part == "dev" else test if a.part == "test" else dev + test)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, a.out)
    rows = []
    for task in tasks:
        if task["instance_id"] not in keep:
            continue
        t0 = time.time()
        graph, emb, files = task_inputs(task)
        row = {"task": task["instance_id"], "repo": task["repo"]}
        row.update(diagnose(task, graph, emb, files))
        rankings = localizza.all_rankings(graph, emb, task, files=files)
        row["scores"] = score(rankings, [tuple(x) for x in row["gold_defs"]], row["gold_files"], files)
        row["top5"] = {k: v[:5] for k, v in rankings.items()}
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        print(task["instance_id"], {k: v["fn_exact@5"] for k, v in row["scores"].items()}, row["seconds"],
              flush=True)
    summary = {}
    for name in rows[0]["scores"] if rows else []:
        summary[name] = {m: _rate([r["scores"][name][m] for r in rows])
                         for m in rows[0]["scores"][name] if m != "kind@5"}
        summary[name]["kind@5"] = dict(collections.Counter(str(r["scores"][name]["kind@5"]) for r in rows
                                                           if r["gold_defs"]))
    result = {"part": a.part, "params": localizza.PARAMS, "n": len(rows), "task_ids": sorted(keep),
              "code_sha256": code_hashes(), "tasks_sha256": sha256_file(TASKS), "summary": summary, "tasks": rows}
    with open(out_path, "x", encoding="utf-8", newline="\n") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
