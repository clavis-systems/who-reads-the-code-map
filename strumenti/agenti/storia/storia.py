"""Storia (backup idea S1), 48-hour test on development tasks only (PIANO_STORIA.md). CPU only, no model.

Does the git history inside each snapshot point at the definition a fix must change? The held-out tasks are never read.
  python storia.py estrai    one dev snapshot per repository: only its git objects and refs, copied into a new bare
                             repository with our own config (never checked out, no hooks, the archive's config unused)
  python storia.py storia    the definitions each first-parent commit touched, by the same rule as the gold
  python storia.py valuta    rankings and fn_exact@k on the dev tasks
"""
import collections
import hashlib
import json
import math
import os
import posixpath
import random
import re
import shutil
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "grafi")))
import dati  # noqa: E402
import istantanee  # noqa: E402
import localizza  # noqa: E402
import valuta_statico as vs  # noqa: E402

OUT = os.path.join(vs.ROOT, "strumenti", "risultati", "storia")
STORES = os.path.join(OUT, "archivi")
SNAP = os.path.join(vs.DATA, "snapshots")
SEED = "storia-2026-10-14"
HISTORY_PATHS = {"fastapi/fastapi": ("fastapi/",), "Textualize/rich": ("rich/",),
                 "psf/requests": ("src/requests/", "requests/"),
                 "encode/httpx": ("src/httpx/", "src/ahttpx/", "httpx/")}   # older layouts give the same module names
MAX_DEFS = 30        # commits touching more definitions are general rewrites and do not count
HALF = 50            # recency scale, in commits
TOP_SEEDS = 5
ALPHA = 0.5
RRF_K = 60
KS = (1, 5, 10)


# ---------- the git archives ----------

def git(store, *args):
    cmd = ["git", "-c", "safe.directory=*", "-c", "core.fsmonitor=false", "--git-dir", store, *args]
    return subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def dev_tasks():
    tasks = {t["instance_id"]: t for t in dati.load_tasks(vs.TASKS)}
    dev, _test = dati.split_tasks(list(tasks.values()))
    return tasks, dev


def copy_git(iid):
    """New bare repository with the snapshot's .git/objects, .git/refs, packed-refs and HEAD only (regular files,
    paths checked to stay inside). Its config, hooks and everything else are never copied."""
    dest = os.path.join(STORES, iid + ".git")
    if os.path.exists(os.path.join(dest, "copiato.ok")):
        return dest
    if os.path.exists(dest):
        raise SystemExit(f"{dest} exists but is incomplete: move it away and run again")
    subprocess.run(["git", "init", "--bare", "-q", dest], check=True)
    root = os.path.realpath(dest)
    with tarfile.open(os.path.join(SNAP, iid + ".tgz"), "r:*") as tar:
        for m in tar:
            if not m.isfile():
                continue
            parts = posixpath.normpath(m.name.removeprefix("./")).split("/")
            if ".git" not in parts[:2]:
                continue
            rel = parts[parts.index(".git") + 1:]
            if not rel or ".." in rel or not (rel[0] in ("objects", "refs") or rel in (["packed-refs"], ["HEAD"])):
                continue
            target = os.path.realpath(os.path.join(dest, *rel))
            if not target.startswith(root + os.sep):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with tar.extractfile(m) as src, open(target, "wb") as fh:
                shutil.copyfileobj(src, fh)
    with open(os.path.join(dest, "copiato.ok"), "w") as fh:
        fh.write(iid)
    return dest


def blob_sha(text):
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def find_tip(store, files, repo, depth=400):
    """The archives do not contain base_commit, and their main branch can be later than it. The tip used here is
    the newest first-parent commit whose library .py files are byte for byte the snapshot's (the base_commit
    state); only it and its ancestors count. Returns (sha, distance from main, files that differ)."""
    want = {p: blob_sha(t) for p, t in files.items() if p.endswith(".py") and dati.in_library(p, repo)}
    best = (None, None, None)
    for i, sha in enumerate(git(store, "rev-list", "--first-parent", f"--max-count={depth}", "HEAD").split()):
        got = {}
        for line in git(store, "-c", "core.quotePath=false", "ls-tree", "-r", sha, "--",
                        *dati.LIBRARY[repo]).splitlines():
            meta, path = line.split("\t", 1)
            if path.endswith(".py"):
                got[path] = meta.split()[2]
        differ = len(set(want.items()) ^ set(got.items()))
        if best[2] is None or differ < best[2]:
            best = (sha, i, differ)
        if differ == 0:
            break
    return best


def extract():
    tasks, dev = dev_tasks()
    where = {}
    for iid in dev:
        store = copy_git(iid)
        files = istantanee.read_snapshot(os.path.join(SNAP, iid + ".tgz"), extensions=(".py",))
        tip, distance, differ = find_tip(store, files, tasks[iid]["repo"])
        where[iid] = {"store": store, "tip": tip, "tip_distance": distance, "files_differing": differ}
        print(iid, where[iid], flush=True)
    with open(os.path.join(OUT, "archivi.json"), "w", encoding="utf-8") as fh:
        json.dump(where, fh, indent=1)


# ---------- what each commit touched ----------

class CatFile:
    """One `git cat-file --batch` process: text of <rev>:<path>, or None."""

    def __init__(self, store):
        self.p = subprocess.Popen(["git", "-c", "safe.directory=*", "--git-dir", store, "cat-file", "--batch"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, rev, path):
        self.p.stdin.write(f"{rev}:{path}\n".encode())
        self.p.stdin.flush()
        head = self.p.stdout.readline().decode().split()
        if len(head) != 3 or not head[2].isdigit():
            return None
        data = self.p.stdout.read(int(head[2]))
        self.p.stdout.read(1)
        return data.decode("utf-8", "replace") if head[1] == "blob" else None

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def history():
    """Commits are content-addressed, so one cache per repository serves every task; each task keeps its own list of
    first-parent commits up to its tip."""
    tasks, dev = dev_tasks()
    with open(os.path.join(OUT, "archivi.json"), encoding="utf-8") as fh:
        where = json.load(fh)
    for repo in sorted({tasks[i]["repo"] for i in dev}):
        commits, order = {}, {}
        for iid in [i for i in dev if tasks[i]["repo"] == repo]:
            w = where[iid]
            if w["files_differing"] != 0:
                print(iid, "skipped: no commit matches the snapshot", flush=True)
                continue
            order[iid] = git(w["store"], "rev-list", "--first-parent", w["tip"], "--", *HISTORY_PATHS[repo]).split()
            new = [s for s in order[iid] if s not in commits]
            if new:
                cmd = ["git", "-c", "safe.directory=*", "-c", "core.fsmonitor=false", "--git-dir", w["store"], "log",
                       "--stdin", "--no-walk=unsorted", "--diff-merges=first-parent", "-p", "-U0", "--no-renames",
                       "--no-textconv", "--no-ext-diff", "--no-color", "--format=COMMIT %H %P %ct", "--",
                       *HISTORY_PATHS[repo]]
                log = subprocess.run(cmd, input="\n".join(new).encode(), capture_output=True,
                                     check=True).stdout.decode("utf-8", "replace")
                cat = CatFile(w["store"])
                for chunk in re.split(r"^COMMIT ", log, flags=re.M)[1:]:
                    head, _, patch = chunk.partition("\n")
                    parts = head.split()
                    parent = parts[1] if len(parts) > 2 else None
                    g = dati.gold_locations(patch, (lambda p, r=parent: cat.read(r, p) if r else None))
                    commits[parts[0]] = {"time": int(parts[-1]), "defs": [n for n, _ in g["defs"]],
                                         "new_files": g["new_files"], "module_level": g["module_level"]}
                cat.close()
            print(iid, len(order[iid]), "commits,", len(new), "new", flush=True)
        with open(os.path.join(OUT, f"storia_{repo.replace('/', '_')}.json"), "w", encoding="utf-8") as fh:
            json.dump({"commits": commits, "order": order}, fh)


# ---------- rankings and scores ----------

def library_defs(files, repo):
    names = set()
    for path, src in files.items():
        if path.endswith(".py") and dati.in_library(path, repo) and not dati.is_test_path(path):
            try:
                names.update(d[0] for d in dati.definitions(src, dati.module_name(path)))
            except SyntaxError:
                pass
    return names


def recency(commits, existing, ages=None):
    score = collections.defaultdict(float)
    for i, c in enumerate(commits):
        for d in c["defs"]:
            if d in existing:
                score[d] += math.exp(-(ages[i] if ages else i) / HALF)
    return [n for n, _ in sorted(score.items(), key=lambda x: (-x[1], x[0]))]


def co_change(commits, existing, seeds):
    nodes = {}
    edges = []
    for c in commits:
        ds = sorted({d for d in c["defs"] if d in existing})
        if 2 <= len(ds):
            ids = [nodes.setdefault(d, len(nodes)) for d in ds]
            edges += [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]]
    for s in seeds:
        nodes.setdefault(s, len(nodes))
    if not seeds:
        return []
    r = dati.personalized_pagerank(len(nodes), edges, {nodes[s]: 1.0 for s in seeds}, alpha=ALPHA)
    names = sorted(nodes, key=lambda n: (-r[nodes[n]], n))
    return [n for n in names if r[nodes[n]] > 0 and n in existing]


CITES = {"pr_number": re.compile(r"(?<![\w/])#\d{2,6}\b"),
         "hash": re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"),
         "version": re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")}


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def evaluate():
    tasks, dev = dev_tasks()
    hist = {}
    for repo in sorted({tasks[i]["repo"] for i in dev}):
        with open(os.path.join(OUT, f"storia_{repo.replace('/', '_')}.json"), encoding="utf-8") as fh:
            hist[repo] = json.load(fh)
    rows = []
    for iid in dev:
        task = tasks[iid]
        graph, emb, files = vs.task_inputs(task)
        gold = dati.gold_locations(task["patch"], files.get, task["repo"])
        row = {"task": iid, "repo": task["repo"], "gold_defs": [n for n, _ in gold["defs"]]}
        if not gold["defs"] or iid not in hist[task["repo"]]["order"]:
            rows.append(row)
            continue
        named = localizza.all_rankings(graph, emb, task, files=files)
        L = named["L"]
        existing = library_defs(files, task["repo"])
        h = hist[task["repo"]]["commits"]
        every = [h[s] for s in hist[task["repo"]]["order"][iid] if h[s]["defs"]]
        commits = [c for c in every if len(c["defs"]) <= MAX_DEFS]
        R = recency(commits, existing)
        ages = list(range(len(commits)))
        random.Random(f"{SEED}:{iid}").shuffle(ages)
        Rs = recency(commits, existing, ages)
        CC = co_change(commits, existing, list(dict.fromkeys(L[:TOP_SEEDS] + R[:TOP_SEEDS])))
        rankings = {"L": L, "F_callgraph": named["F"], "R": R, "CC": CC, "L+R": localizza.fuse([L, R], RRF_K),
                    "L+CC": localizza.fuse([L, CC], RRF_K), "R_shuffled": Rs, "L+R_shuffled": localizza.fuse([L, Rs], RRF_K)}
        row["scores"] = {name: {f"@{k}": dati.fn_hit_at(r, gold["defs"], gold["files"], k, exact=True) for k in KS}
                         for name, r in rankings.items()}
        golds = set(row["gold_defs"])
        row["first_touch"] = next((i for i, c in enumerate(every) if golds & set(c["defs"])), None)
        row["history_commits"] = len(every)
        text = localizza.issue_text(task)
        row["cites"] = {k: bool(rx.search(text)) for k, rx in CITES.items()}
        row["top5"] = {name: r[:5] for name, r in rankings.items()}
        rows.append(row)
        print(iid, {n: s["@5"] for n, s in row["scores"].items()}, row["first_touch"], flush=True)
    scored = [r for r in rows if "scores" in r]

    def total(name, k=5, rs=None):
        return sum(r["scores"][name][f"@{k}"] for r in (rs if rs is not None else scored))
    names = list(scored[0]["scores"])
    out = {"tasks": len(dev), "scored": len(scored),
           "fn_exact": {n: {f"@{k}": total(n, k) for k in KS} for n in names},
           "by_repo": {repo: {n: total(n, 5, [r for r in scored if r["repo"] == repo]) for n in names}
                       for repo in sorted({r["repo"] for r in scored})}}
    gain = total("L+R") - total("L")
    gain_shuffled = total("L+R_shuffled") - total("L")
    others = [r for r in scored if r["repo"] != "fastapi/fastapi"]
    net_out = sum(r["scores"]["L+R"]["@5"] - r["scores"]["L"]["@5"] for r in others)
    out["criteria"] = {"1_fusion_gain_ge_3": [gain, gain >= 3], "2_cc_beats_r": [total("CC"), total("R"), total("CC") > total("R")],
                       "3_shuffled_keeps_lt_70pct": [gain_shuffled, gain > 0 and gain_shuffled < 0.7 * gain],
                       "4_net_win_outside_fastapi": [net_out, net_out >= 1]}
    out["passes"] = all(v[-1] for v in out["criteria"].values())
    out["wins_losses_L+R_vs_L"] = collections.Counter(
        ("win" if r["scores"]["L+R"]["@5"] > r["scores"]["L"]["@5"] else "loss") + ":" + r["repo"]
        for r in scored if r["scores"]["L+R"]["@5"] != r["scores"]["L"]["@5"])
    out["gold_touched_within"] = {str(n): sum(1 for r in scored if r["first_touch"] is not None and r["first_touch"] < n)
                                  for n in (1, 5, 20, 100)}
    out["issues_citing"] = {k: sum(r["cites"][k] for r in scored) for k in CITES}
    out["code_sha256"] = {"storia.py": sha256_file(os.path.abspath(__file__)), **vs.code_hashes()}
    out["params"] = {"MAX_DEFS": MAX_DEFS, "HALF": HALF, "TOP_SEEDS": TOP_SEEDS, "ALPHA": ALPHA, "RRF_K": RRF_K}
    out["rows"] = rows
    with open(os.path.join(OUT, "storia_valutazione.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    {"estrai": extract, "storia": history, "valuta": evaluate}[sys.argv[1]]()
