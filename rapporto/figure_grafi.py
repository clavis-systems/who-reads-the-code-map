"""Figures of the code-graph paper, drawn from the study's output files (no number is typed by hand).

    python -I rapporto/figure_grafi.py            # figure 1; figure 2 too once analisi_finale.json exists

Writes rapporto/figure/grafi_fig1.(png|svg) and grafi_fig2.(png|svg).
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "strumenti", "risultati", "grafi")
FIG = os.path.join(ROOT, "rapporto", "figure")
sys.path.insert(0, os.path.join(ROOT, "strumenti", "agenti", "grafi"))
import analisi_grafi  # noqa: E402

WORDS, GRAPH, NEUTRAL = "#2a78d6", "#eb6834", "#9aa1a8"
INK, INK2, GRID = "#15202b", "#4b5560", "#e1e0d9"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK, "text.color": INK, "svg.fonttype": "none"})


def load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return json.load(fh)


def pair(rows, first, second, metric):
    a = {r["task"]: r["scores"][first][metric] for r in rows if r["gold_defs"]}
    b = {r["task"]: r["scores"][second][metric] for r in rows if r["gold_defs"]}
    return analisi_grafi.paired(a, b)


def clean(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(os.path.join(FIG, f"{name}.{ext}"), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("written", name)


def figure1():
    test = load("statico_test.json")
    rows = test["tasks"]
    n = sum(bool(r["gold_defs"]) for r in rows)
    s = analisi_grafi.static(os.path.join(OUT, "statico_test.json"))
    fig, (a, b) = plt.subplots(1, 2, figsize=(10.5, 3.4), gridspec_kw={"width_ratios": [1, 1.15], "wspace": 0.55})
    # (a) exact function among the first k, test
    measures = [("Exact, top 1", "fn_exact@1"), ("Exact, top 5", "fn_exact@5"), ("Exact, top 10", "fn_exact@10")]
    y = list(range(len(measures)))[::-1]
    h = 0.34
    for i, (label, key) in enumerate(measures):
        for off, name, color in ((h / 2, "L", WORDS), (-h / 2, "F", GRAPH)):
            v = s["summary"][name][key] * 100
            a.barh(y[i] + off, v, height=h * 0.9, color=color)
            a.text(v + 1, y[i] + off, f"{v:.1f}%", va="center", fontsize=9, color=INK)
    a.set_yticks(y, [m[0] for m in measures])
    a.set_xlim(0, 100)
    a.set_xlabel(f"share of the {n} test tasks that change a function")
    a.xaxis.grid(True, color=GRID, linewidth=0.8)
    a.set_axisbelow(True)
    clean(a)
    a.set_title("(a) Without a model: words vs graph walk", loc="left", fontsize=10.5, color=INK)
    a.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=WORDS), plt.Rectangle((0, 0), 1, 1, color=GRAPH)],
             labels=["Words (BM25)", "Graph walk"], loc="upper left", bbox_to_anchor=(0, -0.24), ncol=2,
             frameon=False, fontsize=9)
    # (b) tasks won by only one method, from development to the frozen test
    old = pair(load("statico_dev_v2.json")["tasks"], "F", "L", "fn@5")
    new = pair(load("statico_dev_v6.json")["tasks"], "F", "L", "fn_exact@5")
    steps = [("Development, first version\n(lenient match)", old), ("Development, after review\n(exact match)", new),
             ("Frozen test, 84 tasks\n(exact match)", s["H1"])]
    yy = list(range(len(steps)))[::-1]
    for i, (label, p) in enumerate(steps):
        b.barh(yy[i], -p["second_only"], height=0.5, color=WORDS)
        b.barh(yy[i], p["first_only"], height=0.5, color=GRAPH)
        b.text(-p["second_only"] - 0.4, yy[i], str(p["second_only"]), va="center", ha="right", fontsize=9)
        b.text(p["first_only"] + 0.4, yy[i], str(p["first_only"]), va="center", ha="left", fontsize=9)
    lim = max(max(p["first_only"], p["second_only"]) for _, p in steps) + 3
    b.set_xlim(-lim, lim)
    b.axvline(0, color=INK2, linewidth=0.8)
    b.set_yticks(yy, [t for t, _ in steps])
    b.set_xticks([])
    clean(b)
    b.spines["bottom"].set_visible(False)
    b.set_title("(b) Tasks won by only one method", loc="left", fontsize=10.5, color=INK)
    b.text(-lim + 0.3, -0.85, "word search only", color=INK2, fontsize=9, ha="left")
    b.text(lim - 0.3, -0.85, "graph walk only", color=INK2, fontsize=9, ha="right")
    save(fig, "grafi_fig1")


def figure2():
    fin = load("analisi_finale.json")
    conds = fin["agent"]["conditions"]
    n = fin["hypotheses"]["H2"]["n"]
    order = [("none", "none: no map", NEUTRAL), ("pull", "pull: official map tools", NEUTRAL),
             ("push_lex", "push_lex: 5 hints from word search", WORDS),
             ("push_graph", "push_graph: 5 hints from the graph walk", GRAPH)]
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    y = list(range(len(order)))[::-1]
    for i, (c, label, color) in enumerate(order):
        k = conds[c]["fn_exact"]
        ax.barh(y[i], 100 * k / n, height=0.55, color=color)
        ax.text(100 * k / n + 1, y[i], f"{k} of {n}", va="center", fontsize=9)
    ax.set_yticks(y, [o[1] for o in order])
    ax.set_xlim(0, 100)
    ax.set_xlabel("test tasks where Gemma 4 E4B submitted the exact function (%)")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    clean(ax)
    h = fin["hypotheses"]
    ax.set_title(f"H2 push_graph vs pull: {h['H2']['first_only']} vs {h['H2']['second_only']} discordant, "
                 f"Holm p = {h['H2']['p_holm']:.2f}.   H3 push_graph vs push_lex: {h['H3']['first_only']} vs "
                 f"{h['H3']['second_only']}, Holm p = {h['H3']['p_holm']:.2f}", loc="left", fontsize=9, color=INK2)
    save(fig, "grafi_fig2")


if __name__ == "__main__":
    figure1()
    if os.path.exists(os.path.join(OUT, "analisi_finale.json")):
        figure2()
