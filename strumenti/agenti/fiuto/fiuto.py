"""Fiuto: the program walks the call graph, the model only sniffs (PIANO_FIUTO.md). Development tasks only.

The probe (bussola/RISULTATO_SONDA.md) found that Gemma 4 E4B cannot choose a direction on the code map but often
recognizes the function to fix when it sees it. So the model gets one question per candidate, "must this be changed?",
and the program decides where to look next. Two arms with the same budget of model calls:
  FILA   the first 20 BM25 candidates, reordered by the model's P(yes)
  FIUTO  the first 10 BM25 candidates, then best-first on the call graph: next comes the unasked neighbour of the
         highest-scoring asked node (ties by BM25 rank), until 20 calls
  python fiuto.py esegui     GPU: asks Ollama (answers cached in fiuto_risposte.jsonl, resumable)
  python fiuto.py riassumi   rebuilds both arms from the cached answers only and scores them
"""
import collections
import hashlib
import json
import math
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "bussola")))
import sonda  # noqa: E402  (also puts ../grafi on the path)
import agente_grafi as ag  # noqa: E402
import dati  # noqa: E402
import localizza  # noqa: E402
import valuta_statico as vs  # noqa: E402

PART = sys.argv[2] if len(sys.argv) > 2 else "sviluppo"   # "prova": the 84 held-out tasks (PIANO_FIUTO_PROVA.md)
if PART not in ("sviluppo", "prova"):
    raise SystemExit("part: sviluppo or prova")
TAG = "" if PART == "sviluppo" else "_prova"
OUT = os.path.join(vs.ROOT, "strumenti", "risultati", "fiuto")
ANSWERS = os.path.join(OUT, f"fiuto{TAG}_risposte.jsonl")
CONFIG = os.path.join(OUT, f"fiuto{TAG}_config.json")
SUMMARY = os.path.join(OUT, f"fiuto{TAG}_riassunto.json")
AGENT_RUNS = os.path.join(vs.OUT_DIR, "agente_test")      # the frozen study's agent runs on the same held-out tasks
BUDGET = 20
START = 10
KS = (1, 5, 10)
TOP_LOGPROBS = 20
MAIN_REPOS = ("fastapi/fastapi", "Textualize/rich", "psf/requests")


def prompt(task, graph, node):
    return (f"You are helping find where a bug must be fixed in the Python repository {task['repo']}.\n\n"
            f"ISSUE:\n{localizza.issue_text(task)[:sonda.ISSUE_CHARS]}\n\n"
            f"Candidate: `{node}`\n```python\n{sonda.code_of(graph['text'][node])}\n```\n\n"
            f"Question: must `{node}` itself be changed to fix the issue? Answer yes or no.")


def ask(text):
    """One stateless call, as in the probe but with the top 20 first tokens (with 5, "yes" is often missing)."""
    body = {"model": ag.MODEL, "messages": [{"role": "user", "content": text}], "stream": False, "think": False,
            "options": sonda.OPTIONS, "logprobs": True, "top_logprobs": TOP_LOGPROBS}
    req = urllib.request.Request(ag.OLLAMA_BASE + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def p_yes(answer):
    """Score in [0, 1]: 0.5 + (P(yes) - P(no)) / 2 over the first token's top 20 (all spellings); the mass on other
    tokens counts as neutral, so the score stays graded when "yes" is not among them. The parsed reply if neither."""
    tops = (answer.get("first_token") or {}).get("top_logprobs") or []
    y = sum(math.exp(t["logprob"]) for t in tops if t["token"].strip().lower() == "yes")
    n = sum(math.exp(t["logprob"]) for t in tops if t["token"].strip().lower() == "no")
    if y + n > 0:
        return 0.5 + (y - n) / 2
    reply = (answer.get("reply") or "").strip().lower()
    return 0.75 if reply.startswith("yes") else 0.25 if reply.startswith("no") else 0.5


def load_cache():
    cache = {}
    if os.path.exists(ANSWERS):
        cut = 0
        with open(ANSWERS, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    a = json.loads(line)
                except ValueError:               # a line cut by an interruption: that question is asked again
                    cut += 1
                    continue
                cache[(a["task"], a["node"])] = a
        if cut:
            print(f"{cut} cut line(s) skipped in {ANSWERS}", flush=True)
    return cache


def final(scores, L):
    rank = {n: i for i, n in enumerate(L)}
    asked = sorted(scores, key=lambda n: (-scores[n], rank.get(n, len(rank)), n))
    return asked + [n for n in L if n not in scores]


def fila(L, sniff):
    return final({n: sniff(n) for n in L[:BUDGET]}, L)


def fiuto(L, adj, sniff):
    rank = {n: i for i, n in enumerate(L)}
    scores = {n: sniff(n) for n in L[:START]}
    while len(scores) < min(BUDGET, len(adj)):
        frontier = {}
        for n, s in scores.items():
            for v in adj.get(n, ()):
                if v not in scores:
                    frontier[v] = max(frontier.get(v, -1.0), s)
        if frontier:
            v = min(frontier, key=lambda v: (-frontier[v], rank.get(v, len(rank)), v))
        else:
            v = next((n for n in L if n not in scores), None)
            if v is None:
                break
        scores[v] = sniff(v)
    return final(scores, L), list(scores)


def tasks_part():
    tasks = {t["instance_id"]: t for t in dati.load_tasks(vs.TASKS)}
    dev, test = dati.split_tasks(list(tasks.values()))
    return tasks, (dev if PART == "sviluppo" else test)


def walk(ask_model):
    """Both arms for every task of PART with a gold definition. ask_model(task, graph, node) -> answer record."""
    tasks, dev = tasks_part()
    rows = []
    for iid in dev:
        task = tasks[iid]
        graph, emb, files = vs.task_inputs(task)
        gold = dati.gold_locations(task["patch"], files.get, task["repo"])
        if not gold["defs"]:
            continue
        named = localizza.all_rankings(graph, emb, task, files=files)
        L = named["L"]
        adj = sonda.library_graph(graph, files, task["repo"])

        def sniff(node):
            return p_yes(ask_model(task, graph, node))
        arms = {"L": L, "F_callgraph": named["F"], "FILA": fila(L, sniff)}
        arms["FIUTO"], asked = fiuto(L, adj, sniff)
        golds = {n for n, _ in gold["defs"]}
        row = {"task": iid, "repo": task["repo"], "gold_defs": sorted(golds),
               "scores": {a: {f"@{k}": dati.fn_hit_at(r, gold["defs"], gold["files"], k, exact=True) for k in KS}
                          for a, r in arms.items()},
               "gold_asked": {"FILA": bool(golds & set(L[:BUDGET])), "FIUTO": bool(golds & set(asked))},
               "top5": {a: r[:5] for a, r in arms.items()}, "fiuto_asked": asked, "fila_asked": L[:BUDGET]}
        rows.append(row)
        print(iid, {a: s["@1"] for a, s in row["scores"].items()}, flush=True)
    return rows


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def run():
    tags = ag.ollama_get("/api/tags").get("models", [])
    config = {"model": ag.MODEL, "model_digest": next((m.get("digest") for m in tags if m.get("name") == ag.MODEL), None),
              "ollama_version": ag.ollama_get("/api/version").get("version"), "options": sonda.OPTIONS,
              "top_logprobs": TOP_LOGPROBS, "think": False, "code_sha256": {f: sha256_file(os.path.join(HERE, f)) for f in ("fiuto.py",)},
              "sonda_sha256": sha256_file(os.path.join(HERE, "..", "bussola", "sonda.py")),
              "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not (config["model_digest"] or "").startswith(ag.EXPECTED["model_digest"]):
        raise SystemExit(f"Model differs from the plan: {config['model_digest']}")
    if config["ollama_version"] != ag.EXPECTED["ollama_version"]:
        raise SystemExit(f"Ollama differs from the plan: {config['ollama_version']}")
    os.makedirs(OUT, exist_ok=True)
    with open(CONFIG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(config) + "\n")
    cache = load_cache()
    out = open(ANSWERS, "a", encoding="utf-8")
    if out.tell():
        out.write("\n")          # keeps a line cut by an interruption apart from the next answer (blank lines skip)

    def ask_model(task, graph, node):
        key = (task["instance_id"], node)
        if key not in cache:
            t0 = time.time()
            reply = None
            for attempt in range(1, 4):
                try:
                    reply = ask(prompt(task, graph, node))
                    break
                except OSError as exc:
                    print("retry", attempt, exc, flush=True)
                    time.sleep(10 * attempt)
            if reply is None:
                raise SystemExit(f"Ollama failed three times on {key}")
            cache[key] = {"task": key[0], "node": node, "reply": (reply.get("message") or {}).get("content"),
                          "first_token": (reply.get("logprobs") or [None])[0],
                          "prompt_tokens": reply.get("prompt_eval_count"), "seconds": round(time.time() - t0, 2)}
            out.write(json.dumps(cache[key], ensure_ascii=False) + "\n")
            out.flush()
        return cache[key]
    walk(ask_model)
    out.close()


def confirm(rows):
    """PIANO_FIUTO_PROVA.md: H1 FILA@1 vs L@1; H2 FILA@5 vs the frozen agent push_lex (fn_exact of its submission,
    same tasks); exact McNemar, Holm over the two. Descriptive: the other agent conditions, FIUTO, cost."""
    import analisi_grafi as an
    runs, _attempts = an.load_runs(AGENT_RUNS)
    ids = [r["task"] for r in rows]

    def col(arm, k):
        return {r["task"]: r["scores"][arm][f"@{k}"] for r in rows}

    def agent_col(cond):
        return {t: runs[(t, cond)]["hit"]["fn_exact"] for t in ids if (t, cond) in runs}

    def slots(t):
        """How many locations push_lex submitted on task t (1 to 5): FILA gets the same number."""
        return min(5, max(1, len(runs[(t, "push_lex")]["submitted"] or [])))
    fila_matched = {r["task"]: dati.fn_hit_at(r["top5"]["FILA"], [(g, None) for g in r["gold_defs"]], [],
                                              slots(r["task"]), exact=True) for r in rows if (r["task"], "push_lex") in runs}
    hyp = {"H1": dict(an.paired(col("FILA", 1), col("L", 1)), first_arm="FILA@1", second_arm="L@1"),
           "H2": dict(an.paired(fila_matched, agent_col("push_lex")), first_arm="FILA@k (k = push_lex's own count)",
                      second_arm="agent push_lex fn_exact")}
    assert hyp["H1"]["n"] == len(rows) and hyp["H2"]["n"] == len(rows), "tasks missing from a comparison"
    adjusted = an.holm({k: v["p_mcnemar"] for k, v in hyp.items()})
    for k, v in hyp.items():
        v["p_holm"] = adjusted[k]
        v["supported"] = v["p_holm"] < 0.05 and v["first"] > v["second"]
    descriptive = {f"FILA@5 (5 slots) vs agent {c} (its own 1-5)": an.paired(col("FILA", 5), agent_col(c))
                   for c in ("none", "pull", "push_graph", "push_lex")}
    descriptive["FILA@1 vs agent push_lex"] = an.paired(col("FILA", 1), agent_col("push_lex"))
    descriptive["FILA@5 vs L@5"] = an.paired(col("FILA", 5), col("L", 5))
    descriptive["FIUTO@1 vs FILA@1"] = an.paired(col("FIUTO", 1), col("FILA", 1))
    descriptive["F_callgraph@1 vs L@1"] = an.paired(col("F_callgraph", 1), col("L", 1))
    descriptive["push_lex_slots"] = dict(collections.Counter(slots(t) for t in ids if (t, "push_lex") in runs))
    cache = load_cache()
    descriptive["prompt_tokens_missing"] = sum(cache[(r["task"], n)]["prompt_tokens"] is None
                                               for r in rows for n in r["fila_asked"])
    fila_tokens = [sum(cache[(r["task"], n)]["prompt_tokens"] or 0 for n in r["fila_asked"]) for r in rows]
    agent_tokens = [runs[(t, "push_lex")]["tokens"]["prompt"] for t in ids if (t, "push_lex") in runs]
    descriptive["prompt_tokens_per_task_median"] = {"FILA": sorted(fila_tokens)[len(fila_tokens) // 2],
                                                    "agent_push_lex": sorted(agent_tokens)[len(agent_tokens) // 2]}
    return {"hypotheses": hyp, "descriptive": descriptive}


def summarize():
    cache = load_cache()

    def from_cache(task, graph, node):
        return cache[(task["instance_id"], node)]
    rows = walk(from_cache)
    arms = list(rows[0]["scores"])

    def total(arm, k=1, rs=None):
        return sum(r["scores"][arm][f"@{k}"] for r in (rows if rs is None else rs))
    out = {"tasks": len(rows), "calls": len(cache),
           "fn_exact": {a: {f"@{k}": total(a, k) for k in KS} for a in arms},
           "by_repo_at1": {repo: {a: total(a, 1, [r for r in rows if r["repo"] == repo]) for a in arms}
                           for repo in sorted({r["repo"] for r in rows})},
           "gold_asked": {a: sum(r["gold_asked"][a] for r in rows) for a in ("FILA", "FIUTO")}}
    base1, base5 = total("L", 1), total("L", 5)
    verdict = {}
    for arm in ("FILA", "FIUTO"):
        net = {repo: sum(r["scores"][arm]["@1"] - r["scores"]["L"]["@1"] for r in rows if r["repo"] == repo)
               for repo in MAIN_REPOS}
        verdict[arm] = {"1_at1_ge_L_plus_5": [total(arm, 1), base1 + 5, total(arm, 1) >= base1 + 5],
                        "2_at5_ge_L": [total(arm, 5), base5, total(arm, 5) >= base5],
                        "3_net_win_in_2_of_3_repos": [net, sum(v > 0 for v in net.values()) >= 2]}
        verdict[arm]["passes"] = all(v[-1] for v in verdict[arm].values() if isinstance(v, list))
    out["criteria"] = verdict
    fiuto_over_fila = total("FIUTO", 1) - total("FILA", 1)
    if verdict["FIUTO"]["passes"] and fiuto_over_fila >= 2:
        out["sentence"] = "MAP: the program walks the map, the model only sniffs"
    elif verdict["FILA"]["passes"] or verdict["FIUTO"]["passes"]:
        out["sentence"] = "LINE-UP: the model recognizes but does not navigate; a line-up beats walking"
    else:
        out["sentence"] = "STOP: recognition does not beat the words"
    out["fiuto_minus_fila_at1"] = fiuto_over_fila
    if PART == "prova":
        out["confirmatory"] = confirm(rows)
    out["rows"] = rows
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"esegui": run, "riassumi": summarize}[sys.argv[1]]()
