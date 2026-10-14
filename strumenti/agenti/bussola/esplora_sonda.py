"""Post hoc look at the probe (NOT in PIANO_SONDA.md; exploratory, decides nothing): set questions by polarity,
first-token probabilities as a ranking signal (AUC), and how much one answer moves the odds (likelihood ratios)."""
import collections
import json
import math
import os

import sonda

OUT = os.path.join(sonda.OUT, "sonda_esplorative.json")


def p_token(first, words):
    if not first:
        return 0.0
    return sum(math.exp(t["logprob"]) for t in first.get("top_logprobs") or [] if t["token"].strip().lower() in words)


def auc(pos, neg):
    """Probability that a random positive scores above a random negative (ties count half)."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def ratios(hit_pos, hit_neg):
    """How many times more likely the 'positive' answer is when the truth is positive, and the same for the other one."""
    a, b = sum(hit_pos) / len(hit_pos), sum(hit_neg) / len(hit_neg)
    return {"says_pos_if_pos": round(a, 3), "says_pos_if_neg": round(b, 3),
            "LR_pos_answer": round(a / b, 2) if b else None,
            "LR_neg_answer": round((1 - a) / (1 - b), 2) if b < 1 else None}


def main():
    with open(sonda.QUESTIONS, encoding="utf-8") as fh:
        qs = {q["qid"]: q for q in map(json.loads, fh)}
    with open(sonda.ANSWERS, encoding="utf-8") as fh:
        ans = {a["qid"]: a for a in map(json.loads, fh)}
    out = {"note": "post hoc, exploratory"}
    d = [(q, ans[k]) for k, q in qs.items() if q["kind"] == "direction" and q["order"] == "prior" and q["answerable"]]
    gold = [a for q, a in d if q["distance"] == 0]
    off = [a for q, a in d if q["distance"] != 0]
    out["here"] = ratios([int(sonda.parse(q, a["reply"]) == 0) for q, a in d if q["distance"] == 0],
                         [int(sonda.parse(q, a["reply"]) == 0) for q, a in d if q["distance"] != 0])
    out["here"]["auc_p0"] = auc([p_token(a["first_token"], {"0"}) for a in gold],
                                [p_token(a["first_token"], {"0"}) for a in off])
    # direction among neighbours only, where the model did not say "here"
    moved = [(q, sonda.parse(q, a["reply"])) for q, a in d if q["distance"] != 0]
    moved = [(q, x) for q, x in moved if x not in (None, 0)]
    out["direction_when_not_here"] = {"n": len(moved), "right": round(sum(x in q["correct"] for q, x in moved) / len(moved), 3),
                                      "chance": round(sum(len(q["correct"]) / len(q["shown"]) for q, _ in moved) / len(moved), 3),
                                      "picked_first_listed": round(sum(x == 1 for _, x in moved) / len(moved), 3)}
    out["path_nodes"] = collections.Counter(
        "here" if sonda.parse(q, a["reply"]) == 0 else ("right" if sonda.parse(q, a["reply"]) in q["correct"] else "wrong")
        for q, a in d if q["source"] == "path")
    out["sets_plus_polarity"], out["sets_minus_polarity"] = {}, {}
    for kind in ("file", "class", "community"):
        for pol, key in (("+", "sets_plus_polarity"), ("-", "sets_minus_polarity")):
            rows = [(q, a) for q, a in ((qs[k], ans[k]) for k in qs) if q["kind"] == "set" and q["set_kind"] == kind
                    and q["polarity"] == pol]
            yes = {lab: [int(sonda.parse(q, a["reply"]) == "yes") for q, a in rows if (q["label"] == "pos") == lab]
                   for lab in (True, False)}
            pyes = {lab: [p_token(a["first_token"], {"yes"}) / ((p_token(a["first_token"], {"yes"})
                                                                 + p_token(a["first_token"], {"no"})) or 1)
                          for q, a in rows if (q["label"] == "pos") == lab] for lab in (True, False)}
            r = ratios(yes[True], yes[False]) if pol == "+" else ratios([1 - x for x in yes[True]], [1 - x for x in yes[False]])
            r["auc_p_yes"] = auc(pyes[True], pyes[False]) if pol == "+" else auc(pyes[False], pyes[True])
            out[key][kind] = r
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
