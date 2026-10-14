"""Shared pieces for the code-graph study ("who reads the map"): tasks, gold locations, issue anchors, lexical and
graph ranking. Pure standard library plus numpy/scipy; nothing here executes code from the data.

Gold locations come from the reference patch (gold_locations): a removed or modified line is mapped to the innermost
function or class that contains it at base_commit; an added line to the innermost definition that contains it in the
patched file, or to its nearest enclosing definition that already exists. Blank lines do not count; changes outside
any definition count only at file level; only the library package of each repository counts.
"""

import ast
import collections
import json
import math
import os
import re

import numpy as np

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
DIFF_FILE = re.compile(r"^diff --git a/(\S+) b/(\S+)")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
BACKTICK = re.compile(r"`([^`\n]{1,200})`")
PYFILE = re.compile(r"[\w./-]+\.py\b")
SUBTOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
STOP = frozenset("""a an and are as at be but by can do does for from has have if in into is it its not of on or so
that the their then there these this to was were when which while will with you your i we our self none true false
def class return import return raise use used using get set new add should would could also only just more one two""".split())


# ---------- tasks ----------

def load_tasks(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def split_tasks(tasks, seed=20261012, dev_share=1 / 3):
    """Fixed development/test split, stratified by repository: in each repository the instance ids are sorted, shuffled
    with random.Random(seed) and the first ceil(dev_share * n) go to development."""
    import random
    dev, test = [], []
    by_repo = collections.defaultdict(list)
    for t in tasks:
        by_repo[t["repo"]].append(t["instance_id"])
    for repo in sorted(by_repo):
        ids = sorted(by_repo[repo])
        random.Random(f"{seed}:{repo}").shuffle(ids)
        k = math.ceil(dev_share * len(ids))
        dev += ids[:k]
        test += ids[k:]
    return sorted(dev), sorted(test)


# ---------- patches ----------

def _diff_path(text, prefix):
    p = text.split("\t", 1)[0].strip()
    return p[len(prefix):] if p.startswith(prefix) else p


def parse_patch(patch):
    """{path: [hunk]} for every file of a unified diff, with or without 'diff --git' headers. A hunk is
    (old start, old count, new start, new count, body lines with their ' ', '-', '+' or '\\' prefix). Hunk bodies are
    read by the line counts of their headers, so a code line that starts with '---' cannot be taken for a file
    header. A new file (old side empty or /dev/null) keeps its new path."""
    out = collections.OrderedDict()
    lines = patch.splitlines()
    path, i = None, 0
    while i < len(lines):
        line = lines[i]
        m = DIFF_FILE.match(line)
        if m:
            path = m.group(2)
            out.setdefault(path, [])
            i += 1
            continue
        if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            old, new = _diff_path(line[4:], "a/"), _diff_path(lines[i + 1][4:], "b/")
            path = new if old == "/dev/null" else old
            out.setdefault(path, [])
            i += 2
            continue
        m = HUNK.match(line)
        if m and path is not None:
            old_start, new_start = int(m.group(1)), int(m.group(3))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            new_count = int(m.group(4)) if m.group(4) is not None else 1
            old_left, new_left, body = old_count, new_count, []
            i += 1
            while i < len(lines) and (old_left > 0 or new_left > 0):
                b = lines[i] if lines[i] else " "              # an empty line is an empty context line
                body.append(b)
                if b.startswith("-"):
                    old_left -= 1
                elif b.startswith("+"):
                    new_left -= 1
                elif not b.startswith("\\"):
                    old_left -= 1
                    new_left -= 1
                i += 1
            out[path].append((old_start, old_count, new_start, new_count, body))
            continue
        i += 1
    return dict(out)


def changed_lines(hunks):
    """(removed old line numbers, added new line numbers) of one file. Blank lines are left out: adding or removing
    an empty line changes no location."""
    removed, added = [], []
    for old_start, _oc, new_start, _nc, body in hunks:
        o, n = old_start, new_start
        for b in body:
            tag, text = b[:1], b[1:]
            if tag == "-":
                if text.strip():
                    removed.append(o)
                o += 1
            elif tag == "+":
                if text.strip():
                    added.append(n)
                n += 1
            elif tag != "\\":
                o += 1
                n += 1
    return removed, added


def apply_hunks(old_text, hunks):
    """The file after the patch, or None if a context or removed line does not match the old text."""
    old = old_text.splitlines()
    new, pos = [], 0                                      # pos: index of the next old line to copy
    for old_start, old_count, _ns, _nc, body in hunks:
        start = old_start if old_count == 0 else old_start - 1
        if start < pos or start > len(old):
            return None
        new += old[pos:start]
        pos = start
        for b in body:
            tag, text = b[:1], b[1:]
            if tag in (" ", "-"):
                if pos >= len(old) or old[pos].rstrip() != text.rstrip():
                    return None
                if tag == " ":
                    new.append(old[pos])
                pos += 1
            elif tag == "+":
                new.append(text)
    return "\n".join(new + old[pos:]) + "\n"


def module_name(path):
    """Dotted module of a repository file: 'src/' prefix and '.py' removed, '__init__' dropped."""
    p = path[4:] if path.startswith("src/") else path
    p = p[:-3] if p.endswith(".py") else p
    parts = [x for x in p.split("/") if x]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


BLOCKS = (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While) + (
    (ast.TryStar,) if hasattr(ast, "TryStar") else ())


def definitions(source, module):
    """[(qualified name, kind, first line, last line)] of the functions and classes a developer would open, outermost
    first: those at module level and in class bodies, also inside if/try/with/for/while/match blocks there. A
    function or class defined inside a function belongs to that function and is not listed. Decorators belong to
    their definition."""
    tree = ast.parse(source)
    out = []

    def walk(statements, prefix):
        for child in statements:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                kind = "class" if isinstance(child, ast.ClassDef) else (
                    "async" if isinstance(child, ast.AsyncFunctionDef) else "function")
                name = f"{prefix}.{child.name}"
                out.append((name, kind, start, child.end_lineno))
                if isinstance(child, ast.ClassDef):
                    walk(child.body, name)
            elif isinstance(child, BLOCKS):
                for field in ("body", "orelse", "finalbody"):
                    walk(getattr(child, field, None) or [], prefix)
                for handler in getattr(child, "handlers", None) or []:
                    walk(handler.body, prefix)
            elif hasattr(ast, "Match") and isinstance(child, ast.Match):
                for case in child.cases:
                    walk(case.body, prefix)

    walk(tree.body, module)
    return out


def _innermost(table, line):
    inner = [d for d in table if d[2] <= line <= d[3]]
    return max(inner, key=lambda d: d[2]) if inner else None


def gold_locations(patch, read_source, repo=None):
    """Gold files and gold definitions of a patch. read_source(path) returns the base_commit text of a file or None.
    Only library files count (LIBRARY, when repo is given), never test files. Blank lines are ignored.
    - A removed or modified line belongs to the innermost definition that contains it at base_commit.
    - An added line belongs to the innermost definition that contains it in the patched file; if that definition is
      new, to its nearest enclosing definition that exists at base_commit (a new method counts for its class).
    - A change that belongs to no definition counts at file level only ("module_level").
    - A file that the patch empties (deleted) counts at file level only: its definitions are not places to fix.
    Returns {"files", "defs": [(qualified name, kind)], "module_level", "new_files", "deleted_files", "unapplied"}:
    new_files are absent at base_commit; unapplied are files whose hunks do not match the snapshot (their additions
    then count at file level)."""
    files, defs, module_level, new_files, deleted_files, unapplied = [], [], [], [], [], []

    def add(d, path):
        if d is None:
            if path not in module_level:
                module_level.append(path)
        elif (d[0], d[1]) not in defs:
            defs.append((d[0], d[1]))

    for path, hunks in parse_patch(patch).items():
        if not path.endswith(".py") or is_test_path(path) or (repo and not in_library(path, repo)):
            continue
        files.append(path)
        source = read_source(path)
        if source is None:
            new_files.append(path)
            continue
        removed, added = changed_lines(hunks)
        if not (removed or added):
            continue
        module = module_name(path)
        try:
            table = definitions(source, module)
        except SyntaxError:
            continue
        new_text = apply_hunks(source, hunks)
        if new_text is not None and not new_text.strip():
            deleted_files.append(path)
            add(None, path)
            continue
        for ln in removed:
            add(_innermost(table, ln), path)
        if not added:
            continue
        try:
            new_table = definitions(new_text, module) if new_text is not None else None
        except SyntaxError:
            new_table = None
        if new_table is None:
            unapplied.append(path)
            add(None, path)
            continue
        old_by_name = {d[0]: d for d in table}
        for ln in added:
            d = _innermost(new_table, ln)
            name = d[0] if d else module
            while name not in old_by_name and name.count(".") > module.count("."):
                name = name.rsplit(".", 1)[0]
            add(old_by_name.get(name), path)
    return {"files": files, "defs": defs, "module_level": module_level, "new_files": new_files,
            "deleted_files": deleted_files, "unapplied": unapplied}


LIBRARY = {"fastapi/fastapi": ("fastapi/",), "Textualize/rich": ("rich/",), "psf/requests": ("src/requests/",),
           "encode/httpx": ("src/httpx/", "src/ahttpx/")}      # the package of each repository, fixed 13/10


def in_library(path, repo):
    """True if a file belongs to the library package of its repository (not docs, examples, scripts or tests)."""
    return any(path.startswith(p) for p in LIBRARY.get(repo, ("",)))


def is_test_path(path):
    name = path.rsplit("/", 1)[-1]
    return (name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
            or "/tests/" in "/" + path or "/test/" in "/" + path)


# ---------- issue text ----------

def anchors(text):
    """Code-like strings of an issue, most specific first: backticked spans, dotted names, .py paths, CamelCase or
    snake_case words. Plain English words are left out."""
    found = []
    for span in BACKTICK.findall(text):
        found += IDENT.findall(span)
    found += PYFILE.findall(text)
    for word in IDENT.findall(text):
        if "." in word or "_" in word or re.search(r"[a-z][A-Z]", word) or re.match(r"[A-Z][a-z]+[A-Z]", word):
            found.append(word)
    seen, out = set(), []
    for w in found:
        w = w.strip(".")
        if len(w) >= 3 and w.lower() not in STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def tokens(text):
    """Lower-case sub-tokens: identifiers are split at underscores, dots and case changes."""
    out = []
    for word in re.findall(r"[A-Za-z0-9_]+", text or ""):
        for part in word.split("_"):
            for sub in SUBTOKEN.findall(part):
                s = sub.lower()
                if len(s) >= 2 and s not in STOP:
                    out.append(s)
    return out


# ---------- lexical ranking ----------

class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.docs = [collections.Counter(d) for d in docs]
        self.lens = np.array([sum(c.values()) for c in self.docs], dtype=float)
        self.avg = float(self.lens.mean()) if len(self.lens) else 0.0
        df = collections.Counter(t for c in self.docs for t in c)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query):
        q = collections.Counter(query)
        out = np.zeros(len(self.docs))
        for i, c in enumerate(self.docs):
            s = 0.0
            for t, qf in q.items():
                f = c.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
            out[i] = s
        return out


# ---------- graph ranking ----------

def personalized_pagerank(n, edges, seeds, alpha=0.15, iters=100, tol=1e-10):
    """Random walk with restart on an undirected view of the graph. edges: (i, j) index pairs; seeds: {index: weight}.
    alpha is the restart probability. Returns a numpy vector that sums to 1 (all zeros if there are no seeds)."""
    from scipy import sparse
    if not seeds:
        return np.zeros(n)
    rows, cols = [], []
    for i, j in edges:
        if i != j:
            rows += [i, j]
            cols += [j, i]
    a = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    a.data[:] = 1.0
    deg = np.asarray(a.sum(axis=1)).ravel()
    inv = np.divide(1.0, deg, out=np.zeros(n), where=deg > 0)
    p = np.zeros(n)
    for i, w in seeds.items():
        p[i] += w
    p /= p.sum()
    r = p.copy()
    for _ in range(iters):
        spread = a.T @ (r * inv)
        dangling = r[deg == 0].sum()
        new = (1 - alpha) * (spread + dangling * p) + alpha * p
        if np.abs(new - r).sum() < tol:
            r = new
            break
        r = new
    return r


def def_match(found, gold, modules):
    """A found location (dotted id) matches a gold definition if it is the definition, the class that directly contains
    it, or a direct member of it. A module never matches."""
    return match_kind(found, gold, modules) is not None


def match_kind(found, gold, modules):
    """'exact', 'container' (found is the definition that directly contains gold), 'member' (found is a direct
    member of gold) or None. Modules never match."""
    if found in modules:
        return None
    if found == gold:
        return "exact"
    if found == gold.rsplit(".", 1)[0]:
        return "container"
    if found.rsplit(".", 1)[0] == gold:
        return "member"
    return None


def best_match_kind(found_list, gold_defs, gold_files):
    """The best match of a list of found locations: 'exact' over 'member' over 'container'; None if nothing
    matches (also when there is no gold definition)."""
    modules = {module_name(f) for f in gold_files}
    kinds = {match_kind(f, g, modules) for f in found_list for g, _ in gold_defs} - {None}
    return next((k for k in ("exact", "member", "container") if k in kinds), None)


def fn_hit_at(ranked, gold_defs, gold_files, k, exact=False):
    """1 if any of the first k found locations matches a gold definition (None if there is no gold definition)."""
    golds = [g for g, _ in gold_defs]
    if not golds:
        return None
    modules = {module_name(f) for f in gold_files}
    for found in ranked[:k]:
        if any((found == g) if exact else def_match(found, g, modules) for g in golds):
            return 1
    return 0


def recall_at(ranked, gold, k):
    """Share of gold items among the first k ranked items (None if there is no gold)."""
    if not gold:
        return None
    top = set(ranked[:k])
    return sum(g in top for g in gold) / len(gold)


def hit_at(ranked, gold, k):
    """1 if any gold item is among the first k ranked items (None if there is no gold)."""
    if not gold:
        return None
    return int(any(g in set(ranked[:k]) for g in gold))
