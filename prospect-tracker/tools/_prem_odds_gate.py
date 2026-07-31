# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ODDS LANE part (c): GATE a conditional p_bust recalibration with proper scoring rules.

p_bust is a probability, so it is graded with Brier + log loss and a Murphy
reliability/resolution decomposition, never with a rank metric.

MODELS (all forward-chained: fold Y is fitted strictly on decision_year < Y)
  INC    incumbent served p_bust = vf.p_bucket_given_fv(xfv_grade)[bust]
  CONST  train base rate (no covariate, no grade)     -- resolution floor
  R1     Platt recalibration on logit(p_inc) ALONE    -- the COVARIATE-FREE ablation.
         This is the population-recalibration effect the 2026-07-15 BUCKET-AGE-HEAD
         post-hoc found DOMINATED its age head; any conditional claim must beat it.
  R2     R1 + the conditional surface (level_rank, age, production)
  CTRL   R2 with the conditional columns ROW-PERMUTED (zero-information twin of the
         SAME columns; identical degrees of freedom)
  NULL   R2 fitted against permuted LABELS (permutation null band)

Read-only. Nothing here is imported by the site.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools._prem_odds import bust_label, resolved              # noqa: E402

POOL = ROOT / "tools" / "_prem_odds_pool.json"
FOLDS = (2017, 2018, 2019, 2020)      # >= 4 forward-chained time splits
EPS = 1e-4
SEED = 20260725


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def fit_logistic(X, y, ridge=1e-3, iters=60):
    """Newton/IRLS logistic with a small ridge on the non-intercept columns."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, k = X.shape
    w = np.zeros(k)
    pen = np.eye(k) * ridge
    pen[0, 0] = 0.0
    for _ in range(iters):
        p = sigmoid(X @ w)
        g = X.T @ (p - y) + pen @ w
        W = np.clip(p * (1 - p), 1e-8, None)
        H = X.T @ (X * W[:, None]) + pen
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, g, rcond=None)[0]
        w_new = w - step
        if not np.all(np.isfinite(w_new)):
            break
        if np.max(np.abs(w_new - w)) < 1e-9:
            w = w_new
            break
        w = w_new
    return w


# ---------------------------------------------------------------------------
# design matrices
# ---------------------------------------------------------------------------
def base_cols(rows):
    return np.column_stack([np.ones(len(rows)), logit([r["p_bust_inc"] for r in rows])])


def cond_cols(rows, perm=None):
    """The conditional surface: level, age, production (+ a production-missing
    indicator; ops_rel is absent for ~53% of served-comparable rows)."""
    lr = np.array([float(r["level_rank"]) for r in rows])
    ag = np.array([float(r["milb_age"]) for r in rows])
    om = np.array([1.0 if r.get("ops_rel") is None else 0.0 for r in rows])
    op = np.array([0.0 if r.get("ops_rel") is None else float(r["ops_rel"]) for r in rows])
    M = np.column_stack([lr - 4.0, ag - 22.0, op, om])
    if perm is not None:
        M = M[perm]
    return M


def design(rows, kind, rng=None):
    B = base_cols(rows)
    if kind in ("R1",):
        return B
    if kind == "CONST":
        return np.ones((len(rows), 1))
    perm = rng.permutation(len(rows)) if (kind == "CTRL" and rng is not None) else None
    return np.column_stack([B, cond_cols(rows, perm)])


def labels(rows):
    return np.array([float(bust_label(r["target_resolved"])) for r in rows])


def predict(train, test, kind, rng=None, perm_labels=False):
    if kind == "INC":
        return np.clip(np.array([r["p_bust_inc"] for r in test]), EPS, 1 - EPS)
    ytr = labels(train)
    if perm_labels and rng is not None:
        ytr = ytr[rng.permutation(len(ytr))]
    w = fit_logistic(design(train, kind, rng), ytr)
    return np.clip(sigmoid(design(test, kind, rng) @ w), EPS, 1 - EPS)


# ---------------------------------------------------------------------------
# proper scoring rules
# ---------------------------------------------------------------------------
def brier(p, y):
    return float(np.mean((p - y) ** 2))


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def murphy(p, y, bins=10):
    """Brier = reliability - resolution + uncertainty (lower reliability is better,
    higher resolution is better)."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    n = len(y)
    ybar = y.mean()
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    idx = np.digitize(p, edges[1:-1], right=False)
    rel = res = 0.0
    for b in range(bins):
        m = idx == b
        nb = int(m.sum())
        if nb == 0:
            continue
        rel += nb * (p[m].mean() - y[m].mean()) ** 2
        res += nb * (y[m].mean() - ybar) ** 2
    return {"reliability": rel / n, "resolution": res / n,
            "uncertainty": float(ybar * (1 - ybar))}


def run_chain(rows, kinds, rng=None, perm_labels=False, resample=False):
    """Forward-chained evaluation. Returns {kind: (probs, labels)} pooled over folds."""
    acc = {k: ([], []) for k in kinds}
    for Y in FOLDS:
        tr = [r for r in rows if r["fold"] < Y]
        te = [r for r in rows if r["fold"] == Y]
        if len(tr) < 25 or len(te) < 10:
            continue
        if resample and rng is not None:
            tr = [tr[i] for i in rng.integers(0, len(tr), len(tr))]
            te = [te[i] for i in rng.integers(0, len(te), len(te))]
        yte = labels(te)
        for k in kinds:
            p = predict(tr, te, k, rng=rng, perm_labels=perm_labels)
            acc[k][0].append(p)
            acc[k][1].append(yte)
    return {k: (np.concatenate(v[0]), np.concatenate(v[1])) for k, v in acc.items() if v[0]}


def main():
    allrows = resolved(json.loads(POOL.read_text(encoding="utf-8")))
    frames = {
        "SERVED-COMPARABLE (has MiLB track record -- what the board shows)":
            [r for r in allrows if r["has_track"]],
        "POOLED (every labeled row, incl. the no-track-record majority)":
            [r for r in allrows if r["level_rank"] is not None and r["milb_age"] is not None],
    }
    kinds = ("INC", "CONST", "R1", "R2", "CTRL")
    report = {}

    for fname, rows in frames.items():
        print("=" * 100)
        print(fname)
        print(f"  n = {len(rows)}   folds {FOLDS}")
        rng = np.random.default_rng(SEED)
        point = run_chain(rows, kinds, rng=np.random.default_rng(SEED))
        print(f"\n  {'model':<7s} {'n':>5s} {'Brier':>9s} {'logloss':>9s} "
              f"{'reliab':>9s} {'resol':>9s} {'mean p':>8s} {'obs':>7s}")
        for k in kinds:
            if k not in point:
                continue
            p, y = point[k]
            m = murphy(p, y)
            print(f"  {k:<7s} {len(y):5d} {brier(p,y):9.5f} {logloss(p,y):9.5f} "
                  f"{m['reliability']:9.5f} {m['resolution']:9.5f} {p.mean():8.4f} {y.mean():7.4f}")

        # ---- paired bootstrap: resample TRAIN and TEST, refit every draw ----
        B = 500
        draws = {k: {"brier": [], "ll": [], "rel": [], "res": []} for k in kinds}
        for b in range(B):
            r = np.random.default_rng(SEED + 1000 + b)
            res = run_chain(rows, kinds, rng=r, resample=True)
            for k in kinds:
                if k not in res:
                    continue
                p, y = res[k]
                mm = murphy(p, y)
                draws[k]["brier"].append(brier(p, y))
                draws[k]["ll"].append(logloss(p, y))
                draws[k]["rel"].append(mm["reliability"])
                draws[k]["res"].append(mm["resolution"])

        def ci(a):
            a = np.asarray(a)
            return float(a.mean()), float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))

        print(f"\n  PAIRED BOOTSTRAP (B={B}, train+test resampled, refit per draw)")
        print(f"  {'model':<7s} {'Brier mean':>11s} {'CI95':>20s} "
              f"{'logloss mean':>13s} {'CI95':>20s}")
        for k in kinds:
            if not draws[k]["brier"]:
                continue
            bm, bl, bh = ci(draws[k]["brier"])
            lm, ll_, lh = ci(draws[k]["ll"])
            print(f"  {k:<7s} {bm:11.5f} [{bl:.5f},{bh:.5f}] {lm:13.5f} [{ll_:.5f},{lh:.5f}]")

        print(f"\n  PAIRED DELTAS (positive = FIRST model is WORSE)")
        pairs = [("INC", "R1"), ("INC", "R2"), ("R1", "R2"), ("CTRL", "R2"),
                 ("R1", "CTRL"), ("CONST", "R1"), ("INC", "CONST")]
        deltas = {}
        for a, c in pairs:
            if not (draws[a]["brier"] and draws[c]["brier"]):
                continue
            db = np.asarray(draws[a]["brier"]) - np.asarray(draws[c]["brier"])
            dl = np.asarray(draws[a]["ll"]) - np.asarray(draws[c]["ll"])
            deltas[f"{a}-{c}"] = {
                "brier": [float(db.mean()), float(np.percentile(db, 2.5)),
                          float(np.percentile(db, 97.5)), float((db > 0).mean())],
                "logloss": [float(dl.mean()), float(np.percentile(dl, 2.5)),
                            float(np.percentile(dl, 97.5)), float((dl > 0).mean())]}
            print(f"  {a:>5s} - {c:<5s} Brier {db.mean():+9.5f} "
                  f"[{np.percentile(db,2.5):+.5f},{np.percentile(db,97.5):+.5f}] "
                  f"P(>0)={float((db>0).mean()):.3f}   "
                  f"logloss {dl.mean():+9.5f} "
                  f"[{np.percentile(dl,2.5):+.5f},{np.percentile(dl,97.5):+.5f}] "
                  f"P(>0)={float((dl>0).mean()):.3f}")

        # ---- permutation null band on the R2-vs-R1 gain ----
        nullg = []
        for b in range(300):
            r = np.random.default_rng(SEED + 5000 + b)
            res = run_chain(rows, ("R1", "R2"), rng=r, perm_labels=True)
            if "R1" in res and "R2" in res:
                p1, y1 = res["R1"]
                p2, _ = res["R2"]
                nullg.append(brier(p1, y1) - brier(p2, y1))
        nullg = np.asarray(nullg)
        obs_gain = (brier(*point["R1"]) - brier(*point["R2"])) if "R2" in point else float("nan")
        print(f"\n  PERMUTATION NULL on the conditional gain (R1 Brier - R2 Brier), n={len(nullg)}")
        print(f"    null p50 {np.percentile(nullg,50):+.5f}  p95 {np.percentile(nullg,95):+.5f}  "
              f"p99 {np.percentile(nullg,99):+.5f}")
        print(f"    OBSERVED gain {obs_gain:+.5f}   "
              f"{'ABOVE' if obs_gain > np.percentile(nullg,95) else 'INSIDE'} the 95% null band")

        report[fname] = {
            "n": len(rows),
            "point": {k: {"brier": brier(*point[k]), "logloss": logloss(*point[k]),
                          **murphy(*point[k]), "mean_p": float(point[k][0].mean()),
                          "observed": float(point[k][1].mean())}
                      for k in point},
            "bootstrap": {k: {"brier": ci(draws[k]["brier"]), "logloss": ci(draws[k]["ll"]),
                              "reliability": ci(draws[k]["rel"]),
                              "resolution": ci(draws[k]["res"])}
                          for k in kinds if draws[k]["brier"]},
            "deltas": deltas,
            "perm_null": {"p50": float(np.percentile(nullg, 50)),
                          "p95": float(np.percentile(nullg, 95)),
                          "p99": float(np.percentile(nullg, 99)),
                          "observed": obs_gain},
        }
        print()

    (ROOT / "tools" / "_prem_odds_gate_out.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8")
    print("wrote tools/_prem_odds_gate_out.json")


if __name__ == "__main__":
    raise SystemExit(main())
