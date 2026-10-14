"""Localization agent for the code-graph study: Gemma 4 reads a real issue and names the functions to change.

The agent only lists, searches and reads files of the task snapshot (base_commit), so no code from the data or from
the model is ever executed. Four conditions, same budget:
  none        list_files, search_code, read_file, submit_locations
  pull        the same plus the three official graph tools, with the official prompt text
  push_lex    no graph tools; the first message adds host candidates ranked from the issue text only
  push_graph  no graph tools; the first message adds host candidates ranked with the code graph
The graph tools follow the semantics of the swegemma harness (HARNESS_README.md, section 6.3).

    python -I agente_grafi.py --tasks dev --conditions none,pull,push_lex,push_graph --out <folder>
"""

import argparse
import fnmatch
import hashlib
import http.client
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dati  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LOCK = os.path.join(ROOT, "strumenti", "risultati", ".gpu_lock")
LOCK_MAX_AGE = 24 * 3600
OLLAMA_BASE = "http://127.0.0.1:11434"
MODEL = "gemma4:e4b-it-qat"
OPTIONS = {"temperature": 0, "seed": 1, "num_ctx": 32768, "num_predict": 1024}    # 32,768: the official window
MAX_CALLS = 20
MAX_LINES, MAX_CHARS, OUT_CHARS = 150, 10000, 5000      # official read_file and output limits
REGEX_SECONDS = 5                                       # time limit of one regular-expression search
CONTEXT_LIMIT, KEEP_RECENT = 14336, 5                   # official compaction threshold and kept events (section 7.2)
CONDITIONS = ("none", "pull", "push_lex", "push_graph")
CALL_TEXT = False                 # the text written next to a tool call is logged, not sent back: sent back, it
                                  # made Gemma answer with an empty turn (dev experiment, PREMESSA §4c)
MAX_NUDGES, MAX_TURNS = 3, 60     # official: the loop ends after more than 3 consecutive turns without a tool call
NUDGE_TEXT = ("Please continue your work using the available tools, or call submit_locations when you know where "
              "the code must change.")                          # the official continuation message, adapted
NUDGE_EMPTY = "Your last reply was empty. " + NUDGE_TEXT + " Write tool arguments as plain JSON strings."
STUB = json.dumps({"status": "ok", "note": "Older tool output removed to save context. Call the tool again if you "
                   "need it."})

SYSTEM = """You are a careful software engineer. A user reports an issue in a Python repository. Your only job is to
find WHERE the code must change to fix it: the functions or classes to edit. Do not write a fix.
Explore with the tools, then call submit_locations once, with up to 5 locations, most likely first, each written as
path/to/file.py::Class.method or path/to/file.py::function (or path/to/file.py::Class)."""

OFFICIAL_GRAPH_TEXT = """## Code Intelligence Tools
This repository has pre-built code graph and embedding data. Use these tools for fast, targeted navigation:
- `search_similar_code(query)`: Find semantically similar functions/classes by keyword.
- `get_code_neighbors(node)`: Find callers, callees, and definitions related to a symbol.
- `get_code_subgraph(nodes)`: Get the induced subgraph for a set of symbols."""


def tool(name, description, props, required):
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props,
                                                            "required": required}}}


BASE_TOOLS = [
    tool("list_files", "List files and folders under a directory of the repository (default: the root).",
         {"path": {"type": "string"}, "max_depth": {"type": "integer"}}, []),
    tool("search_code", "Search the repository's .py files for a text (case-sensitive substring; set regex=true for a "
         "regular expression). Returns file:line: text for each match.",
         {"pattern": {"type": "string"}, "regex": {"type": "boolean"}}, ["pattern"]),
    tool("read_file", "Read a file, optionally lines start_line..end_line (1-based, at most 150 lines).",
         {"filepath": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
         ["filepath"]),
    tool("submit_locations", "Submit up to 5 locations to change, most likely first, e.g. "
         "['pkg/mod.py::Class.method', 'pkg/other.py::function']. Ends the task.",
         {"locations": {"type": "array", "items": {"type": "string"}}}, ["locations"]),
]
GRAPH_TOOLS = [
    tool("search_similar_code", "Find semantically similar functions/classes by keyword.",
         {"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"]),
    tool("get_code_neighbors", "Find callers, callees, and definitions related to a symbol.",
         {"node": {"type": "string"}, "edge_type": {"type": "string"}, "max_neighbors": {"type": "integer"}},
         ["node"]),
    tool("get_code_subgraph", "Get the induced subgraph for a set of symbols.",
         {"nodes": {"type": "array", "items": {"type": "string"}}}, ["nodes"]),
]


class InfraError(RuntimeError):
    """A failure of the infrastructure (Ollama), not of the model."""


def ok(**kw):
    return json.dumps(dict(status="ok", **kw), ensure_ascii=False)


def error(kind, message):
    return json.dumps({"status": "error", "error_type": kind, "error_message": message}, ensure_ascii=False)


class Repo:
    """Read-only view of one task: snapshot files (path -> text), the code graph and the node embeddings."""

    def __init__(self, files, graph=None, embeddings=None, root_names=()):
        self.files = files
        self.graph = graph            # {"ids": [...], "text": {...}, "out": {id: [(target, type)]}, "inc": {...}}
        self.emb = embeddings         # {node id: numpy vector}
        self.root_names = set(root_names)       # other names of the repository root (the GitHub name owner/repo)

    # ----- plain tools -----
    def list_files(self, path=".", max_depth=2):
        base = path.strip().strip("/")
        base = "" if base == "workspace" else base.removeprefix("workspace/")
        for name in self.root_names:                  # 'psf/requests' or 'psf/requests/src' as the model may write
            base = "" if base == name else base.removeprefix(name + "/")
        base = "" if base == "." else base.strip("/")
        depth = max(1, min(int(max_depth or 2), 4))
        seen = set()
        for f in self.files:
            if base and not (f == base or f.startswith(base + "/")):
                continue
            rest = f[len(base) + 1:] if base else f
            parts = rest.split("/")
            entry = "/".join(parts[:depth]) + ("/" if len(parts) > depth else "")
            seen.add(((base + "/") if base else "") + entry)
        if not seen:
            return error("NotFound", f"no files under {path!r}")
        entries = sorted(seen)
        return ok(path=path, entries=entries[:300], count=len(entries), is_truncated=len(entries) > 300)

    def search_code(self, pattern, regex=False):
        if not pattern:
            return error("ValidationError", "empty pattern")
        if regex and len(pattern) > 200:
            return error("ValidationError", "regular expressions are limited to 200 characters")
        import regex as regex_module            # like re, but a search can be stopped after a time limit
        try:
            rx = regex_module.compile(pattern) if regex else None
        except regex_module.error as exc:
            return error("ValidationError", f"bad regular expression: {exc}")
        hits, size, deadline = [], 0, time.time() + REGEX_SECONDS
        for f in sorted(self.files):
            if not f.endswith(".py"):
                continue
            for n, line in enumerate(self.files[f].splitlines(), 1):
                if rx:
                    try:
                        found = rx.search(line[:500], timeout=max(0.01, deadline - time.time()))
                    except TimeoutError:
                        return error("Timeout", "the regular expression took too long; use a simpler one")
                else:
                    found = pattern in line
                if found:
                    hit = f"{f}:{n}: {line.strip()[:200]}"
                    size += len(hit) + 1
                    if size > OUT_CHARS:
                        return ok(pattern=pattern, matches=hits, count=len(hits), is_truncated=True)
                    hits.append(hit)
        return ok(pattern=pattern, matches=hits, count=len(hits), is_truncated=False)

    def read_file(self, filepath, start_line=None, end_line=None):
        path = filepath.strip().removeprefix("/").removeprefix("workspace/")
        if ".." in path.split("/"):
            return error("ValidationError", "path traversal is not allowed")
        if path not in self.files:
            return error("FileNotFound", f"{filepath} does not exist")
        lines = self.files[path].splitlines()
        first = max(1, int(start_line or 1))
        wanted = min(len(lines), int(end_line)) if end_line else len(lines)
        last = min(wanted, first + MAX_LINES - 1)
        out, size, cut = [], 0, last < wanted
        for n in range(first, last + 1):
            line = lines[n - 1]
            if size + len(line) + 1 > MAX_CHARS:
                last, cut = n - 1, True
                break
            out.append(line)
            size += len(line) + 1
        return ok(filepath=path, content="\n".join(out), start_line=first, end_line=last, total_lines=len(lines),
                  is_truncated=cut)

    # ----- official graph tools (swegemma section 6.3) -----
    def resolve(self, name):
        """Exact match, then '.' or '/' suffix match, then case-insensitive match, then substring match. Before the
        official steps (our addition, normalize_symbol): a name in the location format 'path.py::Qual' becomes the
        dotted node id, so the format our prompt asks for also works with the graph tools."""
        ids = self.graph["ids"]
        name = normalize_symbol(name)
        if not name:
            return None
        if name in self.graph["text"]:
            return name
        for test in (lambda i: i.endswith("." + name) or i.endswith("/" + name),
                     lambda i: i.lower() == name.lower(),
                     lambda i: name in i):
            hits = [i for i in ids if test(i)]
            if hits:
                return sorted(hits, key=len)[0]
        return None

    def get_code_neighbors(self, node, edge_type=None, max_neighbors=50):
        if not self.graph:
            return error("Unavailable", "no code graph for this repository")
        rid = self.resolve(node)
        if rid is None:
            return error("NodeNotFound", f"no symbol matches {node!r}")
        want = (edge_type or "").upper() or None
        out = [t for t, k in self.graph["out"].get(rid, []) if want in (None, k.upper())]
        inc = [s for s, k in self.graph["inc"].get(rid, []) if want in (None, k.upper())]
        neighbors = list(dict.fromkeys(out + inc))[:max(1, int(max_neighbors or 50))]
        return ok(node=rid, neighbors=neighbors, count=len(neighbors))

    def search_similar_code(self, query, k=10):
        import numpy as np
        if not self.emb:
            return error("Unavailable", "no embeddings for this repository")
        query = normalize_symbol(query)
        keys = [key for key in self.emb if query and (key == query or key.endswith("." + query) or
                                                      key.endswith("/" + query))]
        if not keys:
            return ok(query=query, results=[], count=0)
        q = self.emb[sorted(keys, key=len)[0]]
        names = list(self.emb)
        mat = np.stack([self.emb[n] for n in names])
        sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-12)
        order = np.argsort(-sims)[:max(1, int(k or 10))]
        results = [{"node_name": names[i], "code": (self.graph or {}).get("text", {}).get(names[i], "")[:500],
                    "similarity": round(float(sims[i]), 4)} for i in order]
        return ok(query=query, results=results, count=len(results))

    def get_code_subgraph(self, nodes):
        if not self.graph:
            return error("Unavailable", "no code graph for this repository")
        ids = [r for r in (self.resolve(n) for n in nodes or []) if r]
        keep = set(ids)
        edges = [{"from": s, "to": t, "type": k} for s in ids for t, k in self.graph["out"].get(s, []) if t in keep]
        return ok(nodes=ids, edges=edges, node_count=len(ids), edge_count=len(edges))

    def call(self, name, args):
        """Run one tool. Arguments of the wrong type, or any other failure of a tool, come back to the model as an
        error message: a malformed call never stops the run."""
        args = args if isinstance(args, dict) else {}
        text = lambda key, default="": "" if args.get(key) is None else str(args.get(key, default))  # noqa: E731
        try:
            if name == "list_files":
                return self.list_files(text("path", ".") or ".", args.get("max_depth") or 2)
            if name == "search_code":
                return self.search_code(text("pattern"), args.get("regex") in (True, "true", "True", 1))
            if name == "read_file":
                return self.read_file(text("filepath"), args.get("start_line"), args.get("end_line"))
            if name == "search_similar_code":
                return self.search_similar_code(text("query"), args.get("k") or 10)
            if name == "get_code_neighbors":
                return self.get_code_neighbors(text("node"), text("edge_type") or None, args.get("max_neighbors") or 50)
            if name == "get_code_subgraph":
                nodes = args.get("nodes") or []
                return self.get_code_subgraph([str(n) for n in (nodes if isinstance(nodes, list) else [nodes])])
        except Exception as exc:                                      # noqa: BLE001 - reported to the model
            return error("ValidationError", f"bad arguments: {type(exc).__name__}: {exc}")
        return error("UnknownTool", f"no tool named {name!r}")


# ---------- the agent loop ----------

def ollama_chat(messages, tools, model=MODEL):
    body = {"model": model, "messages": messages, "tools": tools, "stream": False, "think": False,
            "options": OPTIONS}
    req = urllib.request.Request(OLLAMA_BASE + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")[:500] if exc.fp else ""
        except OSError:
            body = ""
        raise InfraError(f"ollama: HTTP {exc.code}: {body}") from exc
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise InfraError(f"ollama: {type(exc).__name__}: {exc}") from exc
    if not isinstance(reply, dict) or not isinstance(reply.get("message"), dict):
        raise InfraError(f"ollama: reply without a message: {str(reply)[:200]}")
    return reply


def workspace_layout(files):
    """The top-level entries of the repository: a short version of the official Workspace Layout section."""
    entries = {f.split("/", 1)[0] + ("/" if "/" in f else "") for f in files}
    return "\n".join(sorted(e for e in entries if e not in (".git/", "__pycache__/") and not e.endswith(".pyc")))


def first_message(task, condition, brief=None, layout=None):
    text = f"Repository: {task['repo']}\n\nIssue:\n{task['problem_statement']}"
    if (task.get("hints_text") or "").strip():
        text += f"\n\nHints:\n{task['hints_text'].strip()}"
    if layout:
        text += "\n\n## Workspace Layout\nTop-level entries of the repository (paths are relative to it):\n" + layout
    if condition == "pull":
        text += "\n\n" + OFFICIAL_GRAPH_TEXT
    if condition in ("push_lex", "push_graph") and brief:
        text += "\n\n## Candidate locations from the host\n" + brief + \
                "\nThese candidates were computed automatically and may be wrong: check them before you submit."
    return text


def estimated_tokens(messages):
    """A cautious token count: one token per 3 characters of message text and tool-call arguments."""
    return sum(len(m.get("content") or "") + len(json.dumps(m.get("tool_calls") or [])) for m in messages) // 3


def fit_context(sent, limit=CONTEXT_LIMIT, keep=KEEP_RECENT):
    """Keep the conversation under the official compaction threshold without losing the system prompt or the issue:
    tool outputs older than the last `keep` are replaced by a short note, oldest first, until the estimate fits.
    (Past num_ctx, Ollama would drop whole old messages, the issue included.) Returns how many were replaced."""
    older = [i for i, m in enumerate(sent) if m["role"] == "tool" and m["content"] != STUB]
    older = older[:-keep] if keep else older
    replaced = 0
    for i in older:
        if estimated_tokens(sent) <= limit:
            break
        sent[i] = dict(sent[i], content=STUB)
        replaced += 1
    return replaced


def run_task(task, repo, condition, brief=None, chat=ollama_chat, max_calls=MAX_CALLS, call_text=CALL_TEXT):
    tools = BASE_TOOLS + (GRAPH_TOOLS if condition == "pull" else [])
    sent = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": first_message(task, condition, brief, workspace_layout(repo.files))}]
    log = [dict(m) for m in sent]
    calls, submitted, started, infra, tokens_total = 0, None, time.time(), None, {"prompt": 0, "completion": 0}
    turns = nudges = nudges_total = replaced_total = 0
    end = "submitted"
    try:
        while submitted is None:
            if calls >= max_calls or turns >= MAX_TURNS:
                end = "budget" if calls >= max_calls else "turns"
                break
            turns += 1
            t0 = time.time()
            replaced = fit_context(sent)
            replaced_total += replaced
            context = {"estimated_tokens": estimated_tokens(sent), "outputs_replaced": replaced}
            reply = chat(sent, tools)
            msg = reply.get("message") or {}
            tokens_total["prompt"] += reply.get("prompt_eval_count") or 0
            tokens_total["completion"] += reply.get("eval_count") or 0
            context.update(prompt_tokens=reply.get("prompt_eval_count"), completion_tokens=reply.get("eval_count"),
                           seconds=round(time.time() - t0, 2))
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                # As in the official loop: no tool call costs no tool call; more than 3 such turns in a row end it.
                text = msg.get("content") or ""
                sent.append({"role": "assistant", "content": text})
                log.append({"role": "assistant", "content": text, **context})
                nudges += 1
                if nudges > MAX_NUDGES:
                    end = "nudges"
                    break
                nudges_total += 1
                nudge = NUDGE_TEXT if text.strip() else NUDGE_EMPTY
                sent += [{"role": "user", "content": nudge}]
                log += [{"role": "user", "content": nudge}]
                continue
            nudges = 0
            # The text the model writes next to a tool call stays in the log; whether it goes back to the model is
            # call_text (PREMESSA §4b).
            sent.append({"role": "assistant", "content": (msg.get("content") or "") if call_text else "",
                         "tool_calls": tool_calls})
            log.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls,
                        **context})
            for tc in tool_calls:
                if calls >= max_calls:
                    break
                fn = tc.get("function") if isinstance(tc, dict) and isinstance(tc.get("function"), dict) else {}
                name, args = fn.get("name"), tool_arguments(fn)
                calls += 1
                if name == "submit_locations":
                    submitted = submission(args)
                    result = ok(submitted=len(submitted))
                else:
                    result = with_budget_warning(repo.call(name, args), calls, max_calls)
                sent.append({"role": "tool", "content": result})
                log.append({"role": "tool", "name": name, "content": result})
                if submitted is not None:
                    break
        forced = False
        if submitted is None:
            # Exploration over (budget, nudges or turns): one last turn in which only submit_locations is offered,
            # the same for every condition.
            final = "No more exploration is possible. Call submit_locations now with your best guess."
            sent.append({"role": "user", "content": final})
            log.append({"role": "user", "content": final})
            replaced = fit_context(sent)
            replaced_total += replaced
            context = {"estimated_tokens": estimated_tokens(sent), "outputs_replaced": replaced}
            t0 = time.time()
            reply = chat(sent, [t for t in BASE_TOOLS if t["function"]["name"] == "submit_locations"])
            msg = reply.get("message") or {}
            tokens_total["prompt"] += reply.get("prompt_eval_count") or 0
            tokens_total["completion"] += reply.get("eval_count") or 0
            log.append({"role": "assistant", "content": msg.get("content") or "",
                        "tool_calls": msg.get("tool_calls") or [], "prompt_tokens": reply.get("prompt_eval_count"),
                        "completion_tokens": reply.get("eval_count"), "seconds": round(time.time() - t0, 2),
                        **context})
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") if isinstance(tc, dict) and isinstance(tc.get("function"), dict) else {}
                if fn.get("name") == "submit_locations":
                    submitted, forced = submission(tool_arguments(fn)), True
                    break
    except InfraError as exc:
        infra, forced, end = str(exc), False, "infra_error"
    return {"task": task["instance_id"], "condition": condition, "submitted": submitted, "forced_submit": forced,
            "end": end, "calls": calls, "turns": turns, "nudges": nudges_total, "infra_error": infra,
            "seconds": round(time.time() - started, 1), "tokens": tokens_total, "outputs_replaced": replaced_total,
            "brief": brief, "messages": log}


def tool_arguments(fn):
    """The arguments of a tool call as a dict ({} when they are missing or malformed)."""
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    return args if isinstance(args, dict) else {}


def submission(args):
    """Up to 5 submitted locations as strings. One string that holds several locations ('a.py::f, b.py::g') is
    split where a new path starts."""
    locs = args.get("locations") if isinstance(args, dict) else None
    out = []
    for item in (locs if isinstance(locs, list) else [] if locs is None else [locs]):
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        out += [p.strip() for p in re.split(r"[,;\n]\s*(?=[\w./-]+\.py\b)", text) if p.strip()]
    return out[:5]


def with_budget_warning(result, used, budget):
    """As the official harness does: with a budget of at least 20 calls, every tool response carries a warning once
    10 calls or fewer remain."""
    remaining = budget - used
    if budget >= 20 and remaining <= 10:
        body = json.loads(result)
        body["budget_warning"] = (f"Only {remaining} tool call(s) remaining ({used}/{budget} used). Finalize your "
                                  "search and call submit_locations soon.")
        return json.dumps(body, ensure_ascii=False)
    return result


# ---------- runs ----------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ollama_get(path):
    with urllib.request.urlopen(OLLAMA_BASE + path, timeout=30) as r:
        return json.load(r)


def condition_order(seed, task_id, conditions):
    order = list(conditions)
    random.Random(f"{seed}-{task_id}").shuffle(order)
    return order


def save_result(path, result):
    if os.path.exists(path):
        raise SystemExit(f"{path} already exists")
    part = f"{path}.{os.getpid()}.part"
    with open(part, "x", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(part, path)


# ---------- host briefs and scoring ----------

def location(node, files):
    """'path/to/file.py::Qual.name' for a graph node (the bare node id if no file defines it)."""
    import localizza
    path = localizza.node_file(node, files)
    if not path:
        return node
    module = dati.module_name(path)
    rest = node[len(module) + 1:] if node.startswith(module + ".") else ""
    return f"{path}::{rest}" if rest else path


def brief(ranking, rankings, graph, files, n=5):
    """Numbered host candidates with a short reason each."""
    anchors, lexical = set(rankings["A"]), set(rankings["L"][:10])
    seeds = list(dict.fromkeys(rankings["A"] + rankings["L"][:10]))
    lines = []
    for i, node in enumerate(ranking[:n], 1):
        if node in anchors:
            why = "named in the issue"
        elif node in lexical:
            why = "its code shares words with the issue"
        else:
            near = [s for s in seeds if s in {t for t, _ in graph["out"].get(node, [])} |
                    {s2 for s2, _ in graph["inc"].get(node, [])}]
            why = f"connected in the code graph to {near[0]}" if near else "close in the code graph to the issue"
        lines.append(f"{i}. {location(node, files)} ({why})")
    return "\n".join(lines)


LOCATION = re.compile(r"^(?P<path>[\w./-]+\.py)(?:\s*:{1,2}\s*(?P<qual>.*))?$")


def split_location(text):
    """(path or None, qualified name) of a location. Accepted: 'path.py::Qual', 'path.py:Qual', 'path.py' and a
    dotted id. Quotes, backticks, './', '/workspace/' and a trailing '(...)' are ignored ('f(x)' names 'f'); a line
    number after the colon ('path.py:120') keeps only the file."""
    text = str(text).strip().strip("`'\"").strip()
    for prefix in ("./", "/workspace/", "workspace/", "/"):
        text = text.removeprefix(prefix)
    m = LOCATION.match(text)
    if not m:
        return None, re.sub(r"\(.*\)$", "", text).strip()
    qual = re.sub(r"\(.*\)$", "", (m.group("qual") or "").strip().strip("`")).strip()
    return m.group("path"), "" if qual.isdigit() else qual


def location_node(text):
    """Graph-style dotted id of a location ('src/' dropped, '__init__' folded into the package)."""
    path, qual = split_location(text)
    if path is None:
        return qual
    module = dati.module_name(path)
    return f"{module}.{qual}" if qual and module else qual or module


def normalize_symbol(name):
    """Our one addition to the official lookup of the graph tools: a name written in the location format our prompt
    asks for ('path.py::Qual') becomes the dotted node id. Any other name goes to the official steps unchanged."""
    name = str(name)
    return location_node(name) if "::" in name else name


def location_file(text, files):
    """The snapshot file a location points to (None if it names none): its path, with 'src/' added if needed, or
    the file that defines a dotted id."""
    import localizza
    path, qual = split_location(text)
    if path is not None:
        return next((p for p in (path, "src/" + path) if p in files), None)
    return localizza.node_file(qual, files) if qual else None


def resolve_in_file(text, files):
    """The dotted id of a submitted location, completed inside the file it names, when it is not a definition of
    that file at base_commit: a name inside a function of the file counts for that function ('handler.app' ->
    handler, as in dati.definitions); else, if exactly one definition of the file ends with '.' + the given name,
    that definition ('models.py::prepare_body' -> PreparedRequest.prepare_body). Otherwise the plain dotted id."""
    node = location_node(text)
    path = location_file(text, files)
    if not node or not path:
        return node
    module = dati.module_name(path)
    try:
        kinds = {d[0]: d[1] for d in dati.definitions(files[path], module)}
    except SyntaxError:
        return node
    if node in kinds or not node.startswith(module + "."):
        return node
    prefix = node
    while prefix.count(".") > module.count("."):
        prefix = prefix.rsplit(".", 1)[0]
        if kinds.get(prefix) in ("function", "async"):
            return prefix                     # a function written inside this one belongs to it (dati.definitions)
    found = [n for n in kinds if n.endswith("." + node[len(module) + 1:])]
    return found[0] if len(found) == 1 else node


def agent_hit(submitted, gold_defs, gold_files, files=None):
    """The one scoring rule for agent runs (PREMESSA §3), used at run time and again by the analysis.
    fn_exact (primary): a submitted location, completed inside its file (resolve_in_file, which needs the snapshot
    files), is a gold definition itself. fn_exact_raw: the same without completing. fn: also the definition that
    directly contains it or a direct member of it (dati.def_match); kind says which of these the best match was.
    file: a submitted location lies in a gold file (with the snapshot files, dotted ids and paths without 'src/'
    resolve)."""
    raw = [location_node(s) for s in submitted or []]
    nodes = [resolve_in_file(s, files) for s in submitted or []] if files is not None else raw
    if files is not None:
        found = {location_file(s, files) for s in submitted or []}
    else:
        found = {split_location(s)[0] for s in submitted or []}
    return {"fn_exact": dati.fn_hit_at(nodes, gold_defs, gold_files, 5, exact=True) or 0,
            "fn_exact_raw": dati.fn_hit_at(raw, gold_defs, gold_files, 5, exact=True) or 0,
            "fn": dati.fn_hit_at(nodes, gold_defs, gold_files, 5) or 0,
            "kind": dati.best_match_kind(nodes[:5], gold_defs, gold_files),
            "file": int(bool((found - {None}) & set(gold_files)))}


EXPECTED = {"model_digest": "ee6656371218", "ollama_version": "0.32.13"}     # the environment fixed in PREMESSA §4b
MAX_INFRA_ATTEMPTS = 3


def run_config(seed, params):
    import platform
    import numpy
    import regex
    import scipy
    import valuta_statico
    tags = ollama_get("/api/tags").get("models", [])
    return {"model": MODEL, "model_digest": next((m.get("digest") for m in tags if m.get("name") == MODEL), None),
            "ollama_version": ollama_get("/api/version").get("version"), "options": OPTIONS, "think": False,
            "call_text": CALL_TEXT, "max_calls": MAX_CALLS, "max_nudges": MAX_NUDGES, "max_turns": MAX_TURNS,
            "context_limit": CONTEXT_LIMIT, "keep_recent": KEEP_RECENT, "seed": seed, "params": params,
            "code_sha256": valuta_statico.code_hashes(),
            "tasks_sha256": sha256_file(os.path.join(ROOT, "esterni", "gemma4_agent", "tasks.jsonl")),
            "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "regex": regex.__version__}


def main():
    import glob
    import localizza
    import valuta_statico
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True, help="dev, test, or comma-separated instance ids")
    p.add_argument("--conditions", default=",".join(CONDITIONS))
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=20261012)
    a = p.parse_args()
    lock_text = ""
    if os.path.exists(LOCK):
        with open(LOCK, encoding="utf-8", errors="replace") as fh:
            lock_text = fh.read()
    if "agente_grafi" not in lock_text or time.time() - os.path.getmtime(LOCK) > LOCK_MAX_AGE:
        raise SystemExit("The GPU lock strumenti/risultati/.gpu_lock must exist, name agente_grafi and be less than "
                         "24 hours old (CLAUDE.md).")
    conditions = [c for c in a.conditions.split(",") if c]
    assert all(c in CONDITIONS for c in conditions), conditions
    tasks = dati.load_tasks(valuta_statico.TASKS)
    dev, test = dati.split_tasks(tasks)
    wanted = set(dev if a.tasks == "dev" else test if a.tasks == "test" else a.tasks.split(","))
    config = run_config(a.seed, localizza.PARAMS)
    same_model = (config["model_digest"] or "").startswith(EXPECTED["model_digest"])
    if not same_model or config["ollama_version"] != EXPECTED["ollama_version"]:
        raise SystemExit(f"Model or Ollama differ from the plan: {config['model_digest']}, {config['ollama_version']}")
    os.makedirs(a.out, exist_ok=True)
    for task in tasks:
        if task["instance_id"] not in wanted:
            continue
        graph, emb, files = valuta_statico.task_inputs(task)
        gold = dati.gold_locations(task["patch"], files.get, task["repo"])
        rankings = localizza.all_rankings(graph, emb, task, files=files)
        briefs = {"push_lex": brief(rankings["L"], rankings, graph, files),
                  "push_graph": brief(rankings["F"], rankings, graph, files)}
        repo = Repo(files, graph, emb, root_names=(task["repo"],))
        for cond in condition_order(a.seed, task["instance_id"], conditions):
            path = os.path.join(a.out, f"{task['instance_id']}_{cond}.json")
            if os.path.exists(path):
                continue
            result = run_task(task, repo, cond, briefs.get(cond))
            result.update(config=config, hit=agent_hit(result["submitted"], gold["defs"], gold["files"], files),
                          gold_defs=[list(x) for x in gold["defs"]], gold_files=gold["files"],
                          gold_new_files=gold["new_files"])
            if result["infra_error"]:
                # Saved apart, so that the next start runs it again; after 3 failures it is recorded as missing.
                attempt = len(glob.glob(path[:-5] + ".infra_*.json")) + 1
                save_result(f"{path[:-5]}.infra_{attempt}.json", result)
                if attempt >= MAX_INFRA_ATTEMPTS:
                    save_result(path, dict(result, missing=True))
                raise SystemExit(f"Stopped by an infrastructure error (attempt {attempt}): {result['infra_error']}")
            save_result(path, result)
            print(f"{task['instance_id']} {cond}: hit {result['hit']}, calls {result['calls']}, "
                  f"{result['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
