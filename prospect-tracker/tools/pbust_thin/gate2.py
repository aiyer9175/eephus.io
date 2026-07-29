# pbust thin-sample lane -- SCRATCH GATE LAB, variant selection (lane: pbust).
# Compares the shippable head shapes on the SAME leave-one-cohort-year-out folds:
#   A   logit(p_bust) = a + b*(grade-30)
#   B   A + c*level_rank                       (level is not in the pitcher grade)
#   Cxx A on min(grade, xx) -- the provisional grade plateaus at the top
# plus the two mandatory controls (row-permuted covariate; covariate-free constant)
# and a NESTED selection check for Cxx (inner fold picks the clip, outer scores it).
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate as G                                          # noqa: E402

LR = {"DSL": 0.0, "CPX": 1.0, "A": 2.0, "A+": 3.0, "AA": 4.0, "AAA": 5.0}


def fit_logistic2(X, ys, l2=1e-3, iters=300):
    """Newton-IRLS logistic on k covariates (X rows already include no intercept)."""
    import math
    k = len(X[0])
    w = [0.0] * (k + 1)
    for _ in range(iters):
        g = [0.0] * (k + 1)
        H = [[0.0] * (k + 1) for _ in range(k + 1)]
        for x, y in zip(X, ys):
            z = w[0] + sum(w[i + 1] * x[i] for i in range(k))
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            d = p - y
            om = max(p * (1 - p), 1e-9)
            v = [1.0] + list(x)
            for i in range(k + 1):
                g[i] += d * v[i]
                for j in range(k + 1):
                    H[i][j] += om * v[i] * v[j]
        for i in range(k + 1):
            g[i] += l2 * w[i]
            H[i][i] += l2
        # gaussian elimination
        M = [row[:] + [g[i]] for i, row in enumerate(H)]
        n = k + 1
        for c in range(n):
            piv = max(range(c, n), key=lambda r: abs(M[r][c]))
            if abs(M[piv][c]) < 1e-12:
                return w
            M[c], M[piv] = M[piv], M[c]
            for r in range(n):
                if r == c:
                    continue
                f = M[r][c] / M[c][c]
                for cc in range(c, n + 1):
                    M[r][cc] -= f * M[c][cc]
        step = [M[i][n] / M[i][i] for i in range(n)]
        w = [w[i] - step[i] for i in range(n)]
        if max(abs(s) for s in step) < 1e-10:
            break
    return w


def predict2(w, x):
    import math
    z = w[0] + sum(w[i + 1] * x[i] for i in range(len(x)))
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def design(g, r, variant):
    if variant == "A":
        return [g - 30.0]
    if variant == "B":
        return [g - 30.0, LR.get(r["level"], 2.0) - 2.0]
    if variant.startswith("C"):
        c = float(variant[1:])
        return [min(g, c) - 30.0]
    raise ValueError(variant)


def main():
    rng = random.Random(7)
    rows = [r for r in G.load() if r["year"] in G.PRIMARY_YEARS]
    fits = {s: G.fit_from(G.train_rows(s), s) for s in ("hit", "pit")}
    grades = G.regrade(rows, fits)
    for r, g in zip(rows, grades):
        r["g"] = g
        r["y"] = G.label_variant(r, "conservative")

    variants = ["A", "B", "C36", "C38", "C40", "C42", "C44"]
    res = {}
    for s in ("hit", "pit"):
        side_rows = [r for r in rows if r["side"] == s]
        per = {v: [] for v in variants}
        per["incumbent"] = []
        per["constant"] = []
        per["permuted_A"] = []
        per["nested_C"] = []
        picks = []
        for hold in G.PRIMARY_YEARS:
            trn = [r for r in side_rows if r["year"] != hold]
            tst = [r for r in side_rows if r["year"] == hold]
            yte = [r["y"] for r in tst]
            ytr = [r["y"] for r in trn]
            for v in variants:
                w = fit_logistic2([design(r["g"], r, v) for r in trn], ytr)
                per[v].append(G.logloss([predict2(w, design(r["g"], r, v)) for r in tst], yte))
            per["incumbent"].append(G.logloss([G.inc(r["g"], s == "pit") for r in tst], yte))
            k = sum(ytr) / len(ytr)
            per["constant"].append(G.logloss([k] * len(tst), yte))
            gp = [r["g"] for r in trn]
            rng.shuffle(gp)
            w = fit_logistic2([[g - 30.0] for g in gp], ytr)
            gpt = [r["g"] for r in tst]
            rng.shuffle(gpt)
            per["permuted_A"].append(G.logloss([predict2(w, [g - 30.0]) for g in gpt], yte))
            # NESTED clip selection: pick the clip on INNER folds of the training years only
            inner_years = sorted({r["year"] for r in trn})
            best, bestv = None, 1e9
            for v in variants:
                sc = []
                for ih in inner_years:
                    itr = [r for r in trn if r["year"] != ih]
                    its = [r for r in trn if r["year"] == ih]
                    if len(itr) < 200 or len(its) < 50:
                        continue
                    ww = fit_logistic2([design(r["g"], r, v) for r in itr], [r["y"] for r in itr])
                    sc.append(G.logloss([predict2(ww, design(r["g"], r, v)) for r in its],
                                        [r["y"] for r in its]))
                if sc and sum(sc) / len(sc) < bestv:
                    best, bestv = v, sum(sc) / len(sc)
            picks.append(best)
            w = fit_logistic2([design(r["g"], r, best) for r in trn], ytr)
            per["nested_C"].append(G.logloss([predict2(w, design(r["g"], r, best)) for r in tst], yte))
        res[s] = {k: {"folds": [round(x, 5) for x in v],
                      "mean": round(sum(v) / len(v), 5)} for k, v in per.items()}
        res[s]["nested_picks"] = picks
    print(json.dumps(res, indent=1))
    (HERE / "gate2_variants.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
