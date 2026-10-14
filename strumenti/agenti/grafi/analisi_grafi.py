"""Analysis of the code-graph study (PREMESSA_GRAFI.md, section 5).

    python -I analisi_grafi.py statico <valuta_statico output .json>
    python -I analisi_grafi.py agente <folder of agente_grafi results> [--file]
    python -I analisi_grafi.py finale <static .json> <agent folder>      (H1-H3 with Holm's correction)

Primary measure everywhere: an EXACT function-level hit (a gold definition itself among the first 5 locations).
The lenient variant (also the containing definition or a direct member) is reported as secondary, with the kind of
each match. Function-level counts use only the tasks whose reference patch changes at least one definition.
H1 (static): the graph ranking F against the lexical ranking L. H2 and H3 (agent): push_graph against pull and
against push_lex. Paired exact McNemar tests; Holm's correction over H1-H3 (alpha 0.05).
Agent hits are always recomputed here from the submitted strings with agente_grafi.agent_hit, the one scoring rule.
"""

import collections
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agente_grafi  # noqa: E402
import dati  # noqa: E402

CONDITIONS = agente_grafi.CONDITIONS
GRAPH_TOOLS = ("search_similar_code", "get_code_neighbors", "get_code_subgraph")


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value from the discordant pairs b and c."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired(first, second):
    """first, second: {task: 0/1}. Counts over the tasks present in both."""
    common = sorted(set(first) & set(second))
    b = sum(first[t] == 1 and second[t] == 0 for t in common)
    c = sum(first[t] == 0 and second[t] == 1 for t in common)
    return {"n": len(common), "first": sum(first[t] for t in common), "second": sum(second[t] for t in common),
            "first_only": b, "second_only": c, "p_mcnemar": mcnemar_exact(b, c)}


def holm(pvalues):
    """Holm-adjusted p-values for {name: p}."""
    names = sorted(pvalues, key=lambda k: pvalues[k])
    out, running = {}, 0.0
    for i, k in enumerate(names):
        running = max(running, min(1.0, (len(names) - i) * pvalues[k]))
        out[k] = running
    return out


# ---------- static rankings ----------

def static(path, graph_method="F", lexical_method="L"):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = [r for r in data["tasks"] if r["gold_defs"]]
    pick = lambda name, metric: {r["task"]: r["scores"][name][metric] for r in rows}  # noqa: E731
    out = {"part": data["part"], "task_ids": data.get("task_ids"), "params": data["params"],
           "code_sha256": data.get("code_sha256"), "summary": data["summary"],
           "H1": dict(paired(pick(graph_method, "fn_exact@5"), pick(lexical_method, "fn_exact@5")),
                      graph=graph_method, lexical=lexical_method, metric="fn_exact@5"),
           "H1_lenient": dict(paired(pick(graph_method, "fn@5"), pick(lexical_method, "fn@5")), metric="fn@5")}
    diag = collections.Counter()
    for r in data["tasks"]:
        diag["tasks"] += 1
        diag["tasks_with_gold_defs"] += bool(r["gold_defs"])
        diag["gold_defs"] += len(r["gold_defs"])
        diag["gold_defs_missing_from_graph"] += len(r["gold_defs_missing_from_graph"])
        diag["tasks_all_gold_defs_missing"] += bool(r["gold_defs"]) and not r["gold_nodes"]
        diag["tasks_with_any_anchor"] += bool(r["anchors"])
        diag["tasks_with_resolved_anchor"] += bool(r["anchors_resolved"])
        diag["tasks_where_similar_code_can_work"] += bool(r["anchors_usable_by_similar_code"])
        diag["tasks_naming_a_gold_def"] += bool(r["issue_names_a_gold_def"])
        diag["tasks_with_unapplied_patch"] += bool(r.get("gold_unapplied"))
        for kind, n in r["gold_kinds"].items():
            diag[f"gold_kind_{kind}"] += n
    out["diagnosis"] = dict(diag)
    return out


# ---------- agent runs ----------

def load_runs(folder):
    """{(task, condition): run}, plus the number of saved infrastructure failures (files *.infra_<n>.json)."""
    runs, attempts = {}, 0
    for f in sorted(glob.glob(os.path.join(folder, "*.json"))):
        if ".infra_" in os.path.basename(f):
            attempts += 1
            continue
        with open(f, encoding="utf-8") as fh:
            r = json.load(fh)
        runs[(r["task"], r["condition"])] = r
    return runs, attempts


def repeated_calls(run):
    seen, repeats = set(), 0
    for m in run["messages"]:
        for tc in m.get("tool_calls") or []:
            key = json.dumps(tc.get("function"), sort_keys=True)
            repeats += key in seen
            seen.add(key)
    return repeats


def config_key(run):
    c = dict(run.get("config") or {})
    return json.dumps(c, sort_keys=True)


def agent(folder, files_for=None):
    """files_for(task) -> snapshot files. Without them (no --file) the names are not completed inside their file
    and dotted ids get no file-level credit: finale always uses them, like the scores stored at run time."""
    runs, attempts = load_runs(folder)
    exact, lenient = collections.defaultdict(dict), collections.defaultdict(dict)
    exact_present, exact_raw = collections.defaultdict(dict), collections.defaultdict(dict)
    stats = collections.defaultdict(collections.Counter)
    tools = collections.Counter()
    for (task, cond), r in sorted(runs.items()):
        s = stats[cond]
        if r.get("missing"):                   # three infrastructure failures (PREMESSA §4b): a miss
            s["missing"] += 1
            if r["gold_defs"]:
                exact[cond][task] = lenient[cond][task] = exact_raw[cond][task] = 0
            continue
        hit = agente_grafi.agent_hit(r["submitted"], [tuple(x) for x in r["gold_defs"]], r["gold_files"],
                                     files_for(task) if files_for else None)
        s["runs"] += 1
        if r["gold_defs"]:
            exact[cond][task], lenient[cond][task] = hit["fn_exact"], hit["fn"]
            exact_present[cond][task], exact_raw[cond][task] = hit["fn_exact"], hit["fn_exact_raw"]
            s["fn_exact_raw"] += hit["fn_exact_raw"]
            s["runs_with_gold_defs"] += 1
            s["fn_exact"] += hit["fn_exact"]
            s["fn"] += hit["fn"]
            s[f"kind_{hit['kind']}"] += 1
        if set(r["gold_files"]) - set(r.get("gold_new_files") or []):
            s["runs_with_old_gold_files"] += 1
            s["file"] += hit["file"]
        s["submitted"] += r["submitted"] is not None
        s["forced_submit"] += bool(r.get("forced_submit"))
        s[f"end_{r.get('end')}"] += 1
        s["calls"] += r["calls"]
        s["repeated_calls"] += repeated_calls(r)
        s["turns"] += r.get("turns") or 0
        s["nudges"] += r.get("nudges") or 0
        s["empty_replies"] += sum(m.get("role") == "user" and m.get("content", "").startswith(
            "Your last reply was empty") for m in r["messages"])
        s["outputs_replaced"] += r.get("outputs_replaced") or 0
        s["prompt_tokens"] += r["tokens"]["prompt"]
        s["seconds"] += r["seconds"]
        if cond == "pull":
            used = False
            for m in r["messages"]:
                if m.get("role") == "tool" and m.get("name") in GRAPH_TOOLS:
                    used = True
                    tools[m["name"]] += 1
                    body = json.loads(m["content"])
                    tools[m["name"] + "_empty_or_error"] += body.get("status") != "ok" or not (
                        body.get("results") or body.get("neighbors") or body.get("nodes"))
            tools["pull_runs_using_graph_tools"] += used
    out = {"conditions": {c: dict(s) for c, s in stats.items()}, "pull_graph_tools": dict(tools),
           "infra_failures_saved": attempts, "distinct_configs": len({config_key(r) for r in runs.values()}),
           "code_sha256": sorted({json.dumps((r.get("config") or {}).get("code_sha256"), sort_keys=True)
                                  for r in runs.values()}),
           "params": sorted({json.dumps((r.get("config") or {}).get("params"), sort_keys=True) for r in runs.values()}),
           "tasks": {c: sorted({t for (t, cc) in runs if cc == c}) for c in CONDITIONS}}
    pairs = {"H2_push_graph_vs_pull": ("push_graph", "pull"), "H3_push_graph_vs_push_lex": ("push_graph", "push_lex"),
             "push_graph_vs_none": ("push_graph", "none"), "push_lex_vs_none": ("push_lex", "none"),
             "push_lex_vs_pull": ("push_lex", "pull"), "pull_vs_none": ("pull", "none")}
    for name, (x, y) in pairs.items():
        if x in exact and y in exact:
            out[name] = paired(exact[x], exact[y])
            out[name + "_lenient"] = paired(lenient[x], lenient[y])
            out[name + "_raw"] = paired(exact_raw[x], exact_raw[y])
            out[name + "_without_missing"] = paired(exact_present[x], exact_present[y])
    return out


# ---------- the pre-registered test ----------

def final(static_path, agent_folder, files_for=None):
    """H1-H3 on the 84 test tasks with Holm's correction. Refuses to report if anything is missing or mixed."""
    import valuta_statico
    _dev, test = dati.split_tasks(dati.load_tasks(valuta_statico.TASKS))
    s, a = static(static_path), agent(agent_folder, files_for)
    problems = []
    if s["part"] != "test" or sorted(s["task_ids"] or []) != sorted(test):
        problems.append("the static file is not the test part")
    for c in CONDITIONS:
        if a["tasks"][c] != sorted(test):
            problems.append(f"{c}: {len(set(test) - set(a['tasks'][c]))} test tasks without a run")
    if a["distinct_configs"] != 1:
        problems.append(f"{a['distinct_configs']} different run configurations")
    import localizza
    current = json.dumps(valuta_statico.code_hashes(), sort_keys=True)
    if json.dumps(s["code_sha256"], sort_keys=True) != current or a["code_sha256"] != [current]:
        problems.append("the outputs were not all made by the code that is running now")
    if json.dumps(s["params"], sort_keys=True) != json.dumps(localizza.PARAMS, sort_keys=True) or \
            a["params"] != [json.dumps(localizza.PARAMS, sort_keys=True)]:
        problems.append("the parameters differ from localizza.PARAMS")
    tests = {"H1": s["H1"], "H2": a.get("H2_push_graph_vs_pull"), "H3": a.get("H3_push_graph_vs_push_lex")}
    problems += [f"{k} could not be computed" for k, v in tests.items() if not v]
    if problems:
        raise SystemExit("Not ready for the final analysis: " + "; ".join(problems))
    adjusted = holm({k: v["p_mcnemar"] for k, v in tests.items()})
    for k, v in tests.items():
        v["p_holm"] = adjusted[k]
        v["supported"] = v["first_only"] > v["second_only"] and adjusted[k] < 0.05
    missing = {c: st.get("missing", 0) for c, st in a["conditions"].items()}
    return {"hypotheses": tests, "missing_runs": missing, "static": s, "agent": a}


def snapshot_files():
    """files_for(task) that reads the task snapshot (for file-level hits)."""
    import istantanee
    import valuta_statico
    return lambda task: istantanee.read_snapshot(os.path.join(valuta_statico.DATA, "snapshots", f"{task}.tgz"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    what = sys.argv[1]
    files_for = snapshot_files() if "--file" in sys.argv or what == "finale" else None
    if what == "finale":
        result = final(sys.argv[2], sys.argv[3], files_for)
        out = os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "analisi_finale.json")
        with open(out, "x", encoding="utf-8", newline="\n") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=1)
        print(json.dumps(result["hypotheses"], indent=1, default=str))
        print("saved", out)
    elif what == "statico":
        print(json.dumps(static(sys.argv[2]), indent=1))
    else:
        print(json.dumps(agent(sys.argv[2], files_for), indent=1))
