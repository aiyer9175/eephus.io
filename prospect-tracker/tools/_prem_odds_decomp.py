# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ODDS LANE: decompose the covariate-free recalibration gain into LEVEL vs SLOPE.

The 2026-07-15 BUCKET-AGE-HEAD lane closed the "recalibrate the bucket curve toward
the bustier resolved pool" line: a pure population LEVEL shift posts big in-population
gains for free and is not new information. So the recalibration must be split:

  R0  intercept-only:  logit(p') = a + 1.0*logit(p_inc)     <- the CLOSED level shift
  R1  intercept+slope: logit(p') = a +   b*logit(p_inc)     <- adds the DISPERSION fix

If R1 beats R0 out of fold, the defect is that the curve is being READ at a grade whose
dispersion it was never fitted for -- a different defect from the closed one.
Read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools._prem_odds import bust_label, resolved                       # noqa: E402
from tools._prem_odds_gate import (FOLDS, SEED, EPS, logit, sigmoid,    # noqa: E402
                                   fit_logistic, brier, logloss, murphy, labels)

POOL = ROOT / "tools" / "_prem_odds_pool.json"


def fit_offset(train):
    """Intercept-only: slope pinned at 1, so only the LEVEL moves."""
    z = logit([r["p_bust_inc"] for r in train])
    y = labels(train)
    X = np.ones((len(train), 1))
    # Newton on a with offset z
    a = 0.0
    for _ in range(80):
        p = sigmoid(a + z)
        g = float(np.sum(p - y))
        h = float(np.sum(np.clip(p * (1 - p), 1e-8, None)))
        step = g / max(h, 1e-8)
        a -= step
        if abs(step) < 1e-10:
            break
    return a


def fit_platt(train):
    z = logit([r["p_bust_inc"] for r in train])
    X = np.column_stack([np.ones(len(train)), z])
    return fit_logistic(X, labels(train))


def chain(rows, rng=None, resample=False):
    out = {k: ([], []) for k in ("INC", "R0", "R1")}
    for Y in FOLDS:
        tr = [r for r in rows if r["fold"] < Y]
        te = [r for r in rows if r["fold"] == Y]
        if len(tr) < 25 or len(te) < 10:
            continue
        if resample and rng is not None:
            tr = [tr[i] for i in rng.integers(0, len(tr), len(tr))]
            te = [te[i] for i in rng.integers(0, len(te), len(te))]
        zte = logit([r["p_bust_inc"] for r in te])
        yte = labels(te)
        a = fit_offset(tr)
        w = fit_platt(tr)
        out["INC"][0].append(np.clip(sigmoid(zte), EPS, 1 - EPS))
        out["R0"][0].append(np.clip(sigmoid(a + zte), EPS, 1 - EPS))
        out["R1"][0].append(np.clip(sigmoid(w[0] + w[1] * zte), EPS, 1 - EPS))
        for k in out:
            out[k][1].append(yte)
    return {k: (np.concatenate(v[0]), np.concatenate(v[1])) for k, v in out.items()}


def main():
    allrows = resolved(json.loads(POOL.read_text(encoding="utf-8")))
    served = [r for r in allrows if r["has_track"]]
    print(f"served-comparable n={len(served)}   folds {FOLDS}")

    pt = chain(served)
    print(f"\n  {'model':<6s} {'Brier':>9s} {'logloss':>9s} {'reliab':>9s} {'resol':>9s} {'mean p':>8s}")
    for k in ("INC", "R0", "R1"):
        p, y = pt[k]
        m = murphy(p, y)
        print(f"  {k:<6s} {brier(p,y):9.5f} {logloss(p,y):9.5f} {m['reliability']:9.5f} "
              f"{m['resolution']:9.5f} {p.mean():8.4f}")
    print(f"  observed base rate {pt['INC'][1].mean():.4f}")

    B = 500
    d = {k: {"b": [], "l": []} for k in ("INC", "R0", "R1")}
    for i in range(B):
        rng = np.random.default_rng(SEED + 7000 + i)
        r = chain(served, rng=rng, resample=True)
        for k in d:
            p, y = r[k]
            d[k]["b"].append(brier(p, y))
            d[k]["l"].append(logloss(p, y))
    print(f"\n  PAIRED DELTAS (B={B}, train+test resampled, refit per draw; +ve = first WORSE)")
    for a, c in (("INC", "R0"), ("INC", "R1"), ("R0", "R1")):
        db = np.asarray(d[a]["b"]) - np.asarray(d[c]["b"])
        dl = np.asarray(d[a]["l"]) - np.asarray(d[c]["l"])
        print(f"  {a:>4s} - {c:<4s} Brier {db.mean():+9.5f} "
              f"[{np.percentile(db,2.5):+.5f},{np.percentile(db,97.5):+.5f}] P(>0)={float((db>0).mean()):.3f}"
              f"   logloss {dl.mean():+9.5f} "
              f"[{np.percentile(dl,2.5):+.5f},{np.percentile(dl,97.5):+.5f}] P(>0)={float((dl>0).mean()):.3f}")

    # ---- fitted coefficients on the FULL frame (what a ship would carry) ----
    w = fit_platt(served)
    a0 = fit_offset(served)
    print(f"\n  FULL-FRAME fits:  R1 logit(p') = {w[0]:+.4f} {w[1]:+.4f}*logit(p_inc)"
          f"     R0 offset a = {a0:+.4f}")
    print("  per-fold R1 coefficients (stability):")
    for Y in FOLDS:
        tr = [r for r in served if r["fold"] < Y]
        if len(tr) < 25:
            continue
        ww = fit_platt(tr)
        print(f"    train<{Y}  n={len(tr):4d}  a={ww[0]:+.4f}  b={ww[1]:+.4f}")


if __name__ == "__main__":
    raise SystemExit(main())
