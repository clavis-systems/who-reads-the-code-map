"""Localization without a model (PREMESSA_GRAFI.md, section 4): rank the graph nodes of a task from the issue text.

    L  BM25 of the issue text over node texts
    A  nodes named in the issue, resolved as the official tools resolve names
    G  personalized PageRank on the code graph, seeded by the top of L and by A
    E  embedding neighbours of the seeds (what search_similar_code returns when given the right symbol)
    F  reciprocal-rank fusion of the rankings

A ranking is a list of node ids, best first. Node ids are fully qualified symbols (module.Class.method).
"""

import collections
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dati  # noqa: E402

PARAMS = {"k1": 1.2, "b": 0.75, "seeds_from_L": 20, "alpha": 0.5, "degree_power": 0.5, "rrf_k": 60,
          "fusion": ("G",)}         # chosen on development tasks only: griglia_dev_v3.json (PREMESSA §4)
URL = re.compile(r"https?://\S+")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
KEEP = 200                          # library nodes kept per ranking (scores and briefs use at most 10)


# ---------- loading ----------

def load_graph(path):
    with open(path, encoding="utf-8") as fh:
        g = json.load(fh)
    ids = [n["id"] for n in g["nodes"]]
    text = {n["id"]: n.get("text") or "" for n in g["nodes"]}
    out, inc = collections.defaultdict(list), collections.defaultdict(list)
    for e in g.get("edges") or g.get("links") or []:
        s, t, k = e.get("source"), e.get("target"), str(e.get("type") or e.get("key") or "")
        if s in text and t in text:
            out[s].append((t, k))
            inc[t].append((s, k))
    return {"ids": ids, "text": text, "out": dict(out), "inc": dict(inc)}


def load_embeddings(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k].astype(np.float32) for k in z.files}


# ---------- rankings ----------

def issue_text(task):
    """Description and hints for the rankings, without HTML comments and web addresses (their words are noise)."""
    text = "\n".join([task.get("problem_statement") or "", task.get("hints_text") or ""])
    return URL.sub(" ", HTML_COMMENT.sub(" ", text))


def lexical_index(graph):
    """BM25 over the node texts and node names, split into sub-words."""
    return dati.BM25([dati.tokens(graph["text"][i]) + dati.tokens(i) for i in graph["ids"]])


def rank_lexical(graph, task, bm25=None, k1=None, b=None):
    ids = graph["ids"]
    bm25 = bm25 or lexical_index(graph)
    bm25.k1 = PARAMS["k1"] if k1 is None else k1
    bm25.b = PARAMS["b"] if b is None else b
    s = bm25.scores(dati.tokens(issue_text(task)))
    order = np.argsort(-s, kind="stable")
    return [ids[i] for i in order if s[i] > 0]


def resolve(graph, name):
    """Same four tiers as the official tools: exact, '.'/'/' suffix, case-insensitive, substring."""
    if name in graph["text"]:
        return name
    for test in (lambda i: i.endswith("." + name) or i.endswith("/" + name),
                 lambda i: i.lower() == name.lower(),
                 lambda i: name in i):
        hits = [i for i in graph["ids"] if test(i)]
        if hits:
            return sorted(hits, key=len)[0]
    return None


def rank_anchors(graph, task):
    """Nodes named in the issue, resolved as the official tools do. The project's own name ('FastAPI' in a fastapi
    issue) is skipped: it says nothing about where the bug is."""
    out, project = [], task["repo"].rsplit("/", 1)[-1].lower()
    for a in dati.anchors(issue_text(task)):
        if a.lower() == project:
            continue
        name = a[:-3].replace("/", ".") if a.endswith(".py") else a
        name = name[4:] if name.startswith("src.") else name
        r = resolve(graph, name)
        if r and r not in out:
            out.append(r)
    return out


def rank_graph(graph, seeds, alpha, degree_power=0.0):
    """Personalized PageRank from the seeds (weight 1/position) on the undirected graph. With degree_power > 0 the
    score is divided by degree ** degree_power, so that hubs (big classes linked to all their methods) do not win
    only by being linked to everything."""
    ids = graph["ids"]
    index = {n: i for i, n in enumerate(ids)}
    edges = [(index[s], index[t]) for s, lst in graph["out"].items() for t, _ in lst]
    weights = {}
    for rank, n in enumerate(seeds):
        weights[index[n]] = weights.get(index[n], 0) + 1.0 / (rank + 1)
    r = dati.personalized_pagerank(len(ids), edges, weights, alpha=alpha)
    if degree_power:
        near = collections.defaultdict(set)
        for i, j in edges:
            if i != j:
                near[i].add(j)
                near[j].add(i)
        r = r / np.maximum(np.array([len(near[i]) for i in range(len(ids))], dtype=float), 1.0) ** degree_power
    order = np.argsort(-r, kind="stable")
    return [ids[i] for i in order if r[i] > 0]


def rank_embeddings(emb, seeds, k=50):
    names = list(emb)
    if not names:
        return []
    mat = np.stack([emb[n] for n in names])
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
    pos = {n: i for i, n in enumerate(names)}
    score = np.zeros(len(names))
    for rank, s in enumerate(seeds):
        if s in pos:
            score = np.maximum(score, (mat @ mat[pos[s]]) / (rank + 1))
    order = np.argsort(-score, kind="stable")
    return [names[i] for i in order[:k] if score[i] > 0]


def fuse(rankings, k=60):
    score = collections.defaultdict(float)
    for ranking in rankings:
        for r, n in enumerate(ranking):
            score[n] += 1.0 / (k + r + 1)
    return [n for n, _ in sorted(score.items(), key=lambda x: -x[1])]


def all_rankings(graph, emb, task, params=PARAMS, files=None, bm25=None):
    """L, A, G, E and F for one task. With files (the task snapshot), every ranking keeps only nodes of the library
    package (keep_library): the place to fix is never a test, a doc example or a script (dati.gold_locations).
    Tests and examples still seed and carry the graph walk."""
    L = rank_lexical(graph, task, bm25, params["k1"], params["b"])
    A = rank_anchors(graph, task)
    seeds = list(dict.fromkeys(A + L[:params["seeds_from_L"]]))
    G = rank_graph(graph, seeds, params["alpha"], params["degree_power"]) if seeds else []
    E = rank_embeddings(emb, seeds) if emb else []
    named = {"L": L, "A": A, "G": G, "E": E}
    if files is not None:
        named = {k: keep_library(v, files, task["repo"]) for k, v in named.items()}
    named["F"] = fuse([named[x] for x in params["fusion"]], params["rrf_k"])
    return named


def keep_library(ranking, files, repo, keep=KEEP):
    """The first `keep` nodes of a ranking whose file is in the library package of the repository and is not a test.
    Nodes whose file is unknown are dropped too (in the fastapi graphs these are the docs_src examples)."""
    out = []
    for n in ranking:
        path = node_file(n, files)
        if path is not None and dati.in_library(path, repo) and not dati.is_test_path(path):
            out.append(n)
            if len(out) >= keep:
                break
    return out


# ---------- scoring ----------

def gold_nodes(graph, gold_defs):
    """Gold definitions present as graph nodes (a method also counts through its class if only the class is there)."""
    found = []
    for name, _kind in gold_defs:
        if name in graph["text"]:
            found.append(name)
        else:
            parent = name.rsplit(".", 1)[0]
            if parent in graph["text"]:
                found.append(parent)
    return list(dict.fromkeys(found))


def node_file(node, files):
    """Repository file that defines a node, by its module prefix (None if no prefix is a file)."""
    parts = node.split(".")
    for cut in range(len(parts), 0, -1):
        base = "/".join(parts[:cut])
        for cand in (f"{base}.py", f"{base}/__init__.py", f"src/{base}.py", f"src/{base}/__init__.py"):
            if cand in files:
                return cand
    return None


def file_ranking(ranking, files):
    return list(dict.fromkeys(f for f in (node_file(n, files) for n in ranking) if f))
