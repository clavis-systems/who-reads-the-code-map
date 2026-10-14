"""Bussola (Compass), 48-hour probe on development tasks only (PIANO_SONDA.md).

How often does Gemma 4 E4B point the right way on the official call graph? Every question is one stateless call: the
issue, one node's code and its neighbours, and a one-number or yes/no answer. The held-out tasks are never read.
  python sonda.py costruisci   CPU: writes the questions (deterministic)
  python sonda.py esegui       GPU: asks Ollama, appends the answers, resumable
  python sonda.py riassumi     scores the answers against the gold
"""
import ast
import collections
import hashlib
import json
import os
import random
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "grafi")))
import agente_grafi as ag  # noqa: E402
import dati  # noqa: E402
import localizza  # noqa: E402
import valuta_statico as vs  # noqa: E402

OUT = os.path.join(vs.ROOT, "strumenti", "risultati", "bussola")
QUESTIONS = os.path.join(OUT, "sonda_domande.jsonl")
ANSWERS = os.path.join(OUT, "sonda_risposte.jsonl")
CONFIG = os.path.join(OUT, "sonda_config.json")
SUMMARY = os.path.join(OUT, "sonda_riassunto.json")
SEED = "bussola-sonda-2026-10-14"
MAX_NEIGHBOURS = 25          # neighbours shown, the first ones by BM25 rank (what Compass would show at its first step)
MAX_DIRECTION = 16           # direction questions per task besides the gold ones
PER_DISTANCE = 4             # random direction questions per distance 1..4 from the gold
MAX_GOLD = 2
SET_SIZES = (3, 60)
SETS_PER_KIND = 2            # positives, hard negatives and random negatives per set type and task (each at most)
ISSUE_CHARS = 6000
CODE_LINES, CODE_CHARS = 60, 4000
OPTIONS = {"temperature": 0, "seed": 1, "num_ctx": 16384, "num_predict": 8}
SOURCES = ("sonda.py",)


# ---------- the library call graph ----------

def library_graph(graph, files, repo):
    """Undirected call graph over the library nodes (no tests, no docs). The official edges are not reliably
    directed (a function can point to its callers), so no direction is shown to the model."""
    lib = [n for n in graph["ids"] if (p := localizza.node_file(n, files)) and dati.in_library(p, repo)
           and not dati.is_test_path(p)]
    keep = set(lib)
    adj = {n: {} for n in lib}
    for s, outs in graph["out"].items():
        if s not in keep:
            continue
        for t, _ in outs:
            if t in keep and t != s:
                adj[s][t] = "both" if adj[s].get(t) == "caller" else "callee"
                adj[t][s] = "both" if adj[t].get(s) == "callee" else "caller"
    return adj


def distances(adj, sources):
    dist = {s: 0 for s in sources}
    frontier = list(sources)
    while frontier:
        nxt = []
        for u in frontier:
            for v in sorted(adj[u]):
                if v not in dist:
                    dist[v] = dist[u] + 1
                    nxt.append(v)
        frontier = nxt
    return dist


def shortest_path(adj, dist_gold, start):
    """From start to the nearest gold node, always taking the alphabetically first neighbour one step closer."""
    if start not in dist_gold:
        return []
    path = [start]
    while dist_gold[path[-1]] > 0:
        path.append(min(v for v in adj[path[-1]] if dist_gold.get(v) == dist_gold[path[-1]] - 1))
    return path


def communities(adj, seed):
    """Label propagation in a seeded node order (no extra packages); isolated nodes form no community."""
    rng = random.Random(seed)
    label = {n: n for n in adj}
    nodes = sorted(n for n in adj if adj[n])
    for _ in range(20):
        rng.shuffle(nodes)
        changed = 0
        for n in nodes:
            counts = collections.Counter(label[v] for v in adj[n])
            top = max(counts.values())
            best = min(lab for lab, c in counts.items() if c == top)
            if best != label[n]:
                label[n], changed = best, changed + 1
        if not changed:
            break
    groups = collections.defaultdict(list)
    for n in nodes:
        groups[label[n]].append(n)
    return [sorted(g) for _, g in sorted(groups.items())]


# ---------- what the model sees ----------

def signature(text):
    """Compact signature (name and parameter names) and the first line of the docstring."""
    try:
        node = ast.parse(textwrap.dedent(text or "")).body[0]
    except (SyntaxError, IndexError, ValueError):
        node = None
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = node.args
        names = [x.arg for x in a.posonlyargs + a.args]
        names += ["*" + a.vararg.arg] if a.vararg else (["*"] if a.kwonlyargs else [])
        names += [x.arg for x in a.kwonlyargs] + (["**" + a.kwarg.arg] if a.kwarg else [])
        head = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({', '.join(names)})"
    elif isinstance(node, ast.ClassDef):
        head = f"class {node.name}" + (f"({', '.join(ast.unparse(b) for b in node.bases)})" if node.bases else "")
    else:
        head = next((x.strip() for x in (text or "").splitlines() if x.strip()), "")
    doc = ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
    doc = next((x.strip() for x in (doc or "").splitlines() if x.strip()), "")
    return head[:200] + (f"  # {doc[:120]}" if doc else "")


def code_of(text):
    lines = (text or "").splitlines()[:CODE_LINES]
    return "\n".join(lines)[:CODE_CHARS]


def direction_prompt(task, graph, node, shown, adj):
    items = "\n".join(f"{i}. {n}: {signature(graph['text'][n])}" for i, n in enumerate(shown, 1)) or "(none)"
    return (f"You are helping find where a bug must be fixed in the Python repository {task['repo']}.\n\n"
            f"ISSUE:\n{localizza.issue_text(task)[:ISSUE_CHARS]}\n\n"
            f"We are looking at `{node}`:\n```python\n{code_of(graph['text'][node])}\n```\n\n"
            f"Its neighbours in the call graph (linked to it by a call, in either direction):\n{items}\n\n"
            f"Question: is `{node}` itself the function or class that must be changed to fix the issue? If yes, "
            "answer 0. If not, which neighbour leads toward it (it is that neighbour, or the way to it goes through "
            "that neighbour)? Answer with one number only.")


SET_INTRO = {"file": "the definitions in the file `{}`", "class": "the class `{}` and its methods",
             "community": "a group of functions that call each other (around `{}`)"}
SET_QUESTION = {"+": "Must at least one of these be changed to fix the issue? Answer yes or no.",
                "-": "Can all of these stay unchanged when the issue is fixed (the fix is elsewhere)? Answer yes or no."}


def set_prompt(task, graph, kind, scope, items, polarity):
    listing = "\n".join(f"- {n}: {signature(graph['text'][n])}" for n in items)
    return (f"You are helping find where a bug must be fixed in the Python repository {task['repo']}.\n\n"
            f"ISSUE:\n{localizza.issue_text(task)[:ISSUE_CHARS]}\n\n"
            f"Here are {len(items)} items, {SET_INTRO[kind].format(scope)}:\n{listing}\n\n"
            f"Question: {SET_QUESTION[polarity]}")


# ---------- building the questions ----------

def is_class(text):
    return any(x.strip().startswith("class ") for x in (text or "").splitlines()[:5])


def candidate_sets(adj, graph, files):
    by_file = collections.defaultdict(list)
    for n in adj:
        by_file[localizza.node_file(n, files)].append(n)
    out = [("file", f, sorted(ns)) for f, ns in sorted(by_file.items())]
    for n in sorted(adj):
        if is_class(graph["text"][n]):
            out.append(("class", n, [n] + sorted(m for m in adj if m.startswith(n + "."))))
    for g in communities(adj, SEED):
        out.append(("community", g[0], g))
    return [s for s in out if SET_SIZES[0] <= len(s[2]) <= SET_SIZES[1]]


def set_label(kind, scope, items, gold_names, gold_files, files):
    """'pos' if an item is a gold definition; None (skipped) if the fix touches the set's scope another way."""
    if gold_names & set(items):
        return "pos"
    if kind == "file" and scope in gold_files:
        return None
    if any(g.startswith(i + ".") for g in gold_names for i in items):
        return None
    return "neg"


def build_task(task, rng):
    graph, _emb, files = vs.task_inputs(task)
    gold = dati.gold_locations(task["patch"], files.get, task["repo"])
    adj = library_graph(graph, files, task["repo"])
    gold_names = {n for n, _ in gold["defs"]}
    gnodes = sorted(gold_names & set(adj))
    info = {"task": task["instance_id"], "library_nodes": len(adj), "gold_defs": len(gold_names),
            "gold_nodes": len(gnodes)}
    if not gnodes:
        return info, []
    lex = [n for n in localizza.rank_lexical(graph, task) if n in adj]
    rank = {n: i for i, n in enumerate(lex)}
    dist = distances(adj, gnodes)
    comp = [n for n in adj if n in dist]
    info.update({"gold_component": len(comp), "bm25_top1": lex[0] if lex else None,
                 "top1_distance": dist.get(lex[0]) if lex else None})
    qs = []

    def direction(node, source):
        neigh = sorted(adj[node], key=lambda n: (rank.get(n, len(rank)), n))
        shown = neigh[:MAX_NEIGHBOURS]
        if dist.get(node) == 0:
            correct = [0] + [i for i, n in enumerate(shown, 1) if dist.get(n) == 0]
        elif node in dist:
            correct = [i for i, n in enumerate(shown, 1) if dist.get(n) == dist[node] - 1]
        else:
            correct = []
        orders = [("prior", shown)]
        if len(shown) > 1:
            orders.append(("shuffled", rng.sample(shown, len(shown))))
        for order, items in orders:
            right = [0] if dist.get(node) == 0 else []
            right += [i for i, n in enumerate(items, 1) if n in {shown[j - 1] for j in correct if j}]
            qs.append({"qid": f"{task['instance_id']}|dir|{order}|{node}", "task": task["instance_id"],
                       "repo": task["repo"], "kind": "direction", "source": source, "order": order, "node": node,
                       "distance": dist.get(node), "degree": len(neigh), "shown": items, "correct": right,
                       "answerable": bool(right), "chance": len(right) / (len(items) + 1),
                       "prompt": direction_prompt(task, graph, node, items, adj)})

    for g in gnodes[:MAX_GOLD]:
        direction(g, "gold")
    path = [n for n in shortest_path(adj, dist, lex[0])][:-1] if lex else []
    chosen = path[:MAX_DIRECTION]
    by_d = collections.defaultdict(list)
    for n in sorted(comp):
        if 1 <= dist[n] <= 4 and n not in chosen:
            by_d[dist[n]].append(n)
    for d in (1, 2, 3, 4):
        for n in rng.sample(by_d[d], min(PER_DISTANCE, len(by_d[d]))):
            if len(chosen) < MAX_DIRECTION:
                chosen.append(n)
    for n in chosen:
        direction(n, "path" if n in path else "random")

    top10 = set(lex[:10])
    kinds = collections.defaultdict(lambda: {"pos": [], "hard": [], "neg": []})
    for kind, scope, items in candidate_sets(adj, graph, files):
        lab = set_label(kind, scope, items, gold_names, set(gold["files"]), files)
        if lab == "neg" and top10 & set(items):
            lab = "hard"
        if lab:
            kinds[kind][lab].append((scope, items))
    for kind in ("file", "class", "community"):
        for lab in ("pos", "hard", "neg"):
            pool = kinds[kind][lab]
            for scope, items in rng.sample(pool, min(SETS_PER_KIND, len(pool))):
                for pol in ("+", "-"):
                    qs.append({"qid": f"{task['instance_id']}|set|{kind}|{pol}|{scope}", "task": task["instance_id"],
                               "repo": task["repo"], "kind": "set", "set_kind": kind, "label": lab, "polarity": pol,
                               "scope": scope, "size": len(items),
                               "correct": "yes" if (lab == "pos") == (pol == "+") else "no",
                               "prompt": set_prompt(task, graph, kind, scope, items, pol)})
    info["questions"] = len(qs)
    return info, qs


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build():
    tasks = {t["instance_id"]: t for t in dati.load_tasks(vs.TASKS)}
    dev, _test = dati.split_tasks(list(tasks.values()))
    os.makedirs(OUT, exist_ok=True)
    infos, total = [], 0
    with open(QUESTIONS, "w", encoding="utf-8") as fh:
        for iid in dev:
            info, qs = build_task(tasks[iid], random.Random(f"{SEED}:{iid}"))
            infos.append(info)
            for q in qs:
                fh.write(json.dumps(q, ensure_ascii=False) + "\n")
            total += len(qs)
            print(iid, info.get("gold_nodes"), info.get("gold_component"), info.get("top1_distance"), len(qs), flush=True)
    meta = {"dev_tasks": len(dev), "tasks_with_questions": sum(1 for i in infos if i.get("questions")),
            "questions": total, "questions_sha256": sha256_file(QUESTIONS), "tasks": infos,
            "code_sha256": {f: sha256_file(os.path.join(HERE, f)) for f in SOURCES},
            "study_code_sha256": vs.code_hashes()}
    with open(os.path.join(OUT, "sonda_costruzione.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print({k: v for k, v in meta.items() if k != "tasks"})


# ---------- asking ----------

def ask(prompt):
    body = {"model": ag.MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False,
            "options": OPTIONS, "logprobs": True, "top_logprobs": 5}
    req = urllib.request.Request(ag.OLLAMA_BASE + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def run():
    tags = ag.ollama_get("/api/tags").get("models", [])
    config = {"model": ag.MODEL, "model_digest": next((m.get("digest") for m in tags if m.get("name") == ag.MODEL), None),
              "ollama_version": ag.ollama_get("/api/version").get("version"), "options": OPTIONS, "think": False,
              "questions_sha256": sha256_file(QUESTIONS),
              "code_sha256": {f: sha256_file(os.path.join(HERE, f)) for f in SOURCES},
              "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not (config["model_digest"] or "").startswith(ag.EXPECTED["model_digest"]):
        raise SystemExit(f"Model differs from the plan: {config['model_digest']}")
    with open(CONFIG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(config) + "\n")
    done = set()
    if os.path.exists(ANSWERS):
        with open(ANSWERS, encoding="utf-8") as fh:
            done = {json.loads(x)["qid"] for x in fh if x.strip()}
    with open(QUESTIONS, encoding="utf-8") as fh:
        todo = [q for q in map(json.loads, fh) if q["qid"] not in done]
    print(f"{len(done)} done, {len(todo)} to ask", flush=True)
    with open(ANSWERS, "a", encoding="utf-8") as out:
        for i, q in enumerate(todo, 1):
            t0 = time.time()
            for attempt in range(1, 4):
                try:
                    reply = ask(q["prompt"])
                    break
                except (OSError, ValueError, urllib.error.URLError) as exc:
                    reply = {"error": f"{type(exc).__name__}: {exc}"}
                    time.sleep(10 * attempt)
            msg = (reply.get("message") or {}).get("content") if "error" not in reply else None
            first = (reply.get("logprobs") or [None])[0]
            out.write(json.dumps({"qid": q["qid"], "reply": msg, "error": reply.get("error"),
                                  "first_token": first, "prompt_tokens": reply.get("prompt_eval_count"),
                                  "seconds": round(time.time() - t0, 2)}, ensure_ascii=False) + "\n")
            out.flush()
            if i % 50 == 0:
                print(f"{i}/{len(todo)} {time.strftime('%H:%M:%S')}", flush=True)


# ---------- scoring ----------

def parse(q, reply):
    if reply is None:
        return None
    if q["kind"] == "direction":
        m = re.search(r"\d+", reply)
        return int(m.group()) if m and int(m.group()) <= len(q["shown"]) else None
    m = re.search(r"\b(yes|no)\b", reply.lower())
    return m.group(1) if m else None


def rate(xs):
    return round(sum(xs) / len(xs), 3) if xs else None


def boot(rows, key, n=2000):
    """95% interval of a pooled rate, resampling whole tasks."""
    by_task = collections.defaultdict(list)
    for r in rows:
        by_task[r["task"]].append(r[key])
    tasks = sorted(by_task)
    rng = random.Random(SEED)
    vals = []
    for _ in range(n):
        xs = [x for t in (rng.choice(tasks) for _ in tasks) for x in by_task[t]]
        vals.append(sum(xs) / len(xs))
    vals.sort()
    return [round(vals[int(0.025 * n)], 3), round(vals[int(0.975 * n)], 3)]


def summarize():
    with open(QUESTIONS, encoding="utf-8") as fh:
        qs = {q["qid"]: q for q in map(json.loads, fh)}
    with open(ANSWERS, encoding="utf-8") as fh:
        ans = {a["qid"]: a for a in map(json.loads, fh)}
    rows = []
    for qid, q in qs.items():
        if qid not in ans:
            continue
        got = parse(q, ans[qid]["reply"])
        r = {k: q.get(k) for k in ("task", "repo", "kind", "source", "order", "distance", "degree", "chance",
                                    "answerable", "set_kind", "label", "polarity", "size", "node", "scope")}
        r["answer"], r["valid"] = got, got is not None
        r["right"] = int(got in q["correct"]) if q["kind"] == "direction" else int(got == q["correct"])
        rows.append(r)
    d = [r for r in rows if r["kind"] == "direction" and r["answerable"]]
    prior = [r for r in d if r["order"] == "prior"]
    out = {"answered": len(rows), "of": len(qs), "invalid": sum(not r["valid"] for r in rows)}

    def block(rs):
        return {"n": len(rs), "p": rate([r["right"] for r in rs]), "chance": rate([r["chance"] for r in rs]),
                "says_here": rate([int(r["answer"] == 0) for r in rs])} if rs else None
    out["p_primary"] = dict(block(prior), ci95=boot(prior, "right"), tasks=len({r["task"] for r in prior}))
    out["p_shuffled"] = block([r for r in d if r["order"] == "shuffled"])
    out["p_by_distance"] = {str(k): block([r for r in prior if min(r["distance"], 4) == k]) for k in range(5)}
    out["p_by_source"] = {s: block([r for r in prior if r["source"] == s]) for s in ("gold", "path", "random")}
    buckets = (("1-3", 1, 3), ("4-10", 4, 10), ("11-25", 11, 25), (">25", 26, 10**9))
    out["p_by_degree"] = {b: block([r for r in prior if lo <= r["degree"] <= hi]) for b, lo, hi in buckets}
    out["p_by_repo"] = {repo: block([r for r in prior if r["repo"] == repo]) for repo in sorted({r["repo"] for r in prior})}
    out["false_here_off_gold"] = rate([int(r["answer"] == 0) for r in prior if r["distance"] != 0])
    pairs = collections.defaultdict(dict)
    for r in d:
        pairs[(r["task"], r["node"])][r["order"]] = r["right"]
    both = [v for v in pairs.values() if len(v) == 2]
    out["order_agreement_on_right"] = rate([int(v["prior"] == v["shuffled"]) for v in both])
    sets = [r for r in rows if r["kind"] == "set"]
    out["sets"] = {}
    for kind in ("file", "class", "community"):
        ks = [r for r in sets if r["set_kind"] == kind]
        pos = [r for r in ks if r["label"] == "pos"]
        neg = [r for r in ks if r["label"] != "pos"]
        fn, fp = 1 - (rate([r["right"] for r in pos]) or 0), 1 - (rate([r["right"] for r in neg]) or 0)
        out["sets"][kind] = {"n_pos": len(pos), "n_neg": len(neg), "miss_rate": round(fn, 3) if pos else None,
                             "false_alarm_rate": round(fp, 3) if neg else None,
                             "balanced_error": round((fn + fp) / 2, 3) if pos and neg else None,
                             "hard_false_alarm": rate([1 - r["right"] for r in ks if r["label"] == "hard"]),
                             "mean_size": rate([r["size"] for r in ks]),
                             "yes_rate": rate([int(r["answer"] == "yes") for r in ks])}
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"costruisci": build, "esegui": run, "riassumi": summarize}[sys.argv[1]]()
