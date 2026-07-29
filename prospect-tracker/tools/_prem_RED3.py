# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ADVERSARIAL RE-DERIVATION 3: audit the ODDS lane's ship candidate.

Checks the recalibration win for (i) reproducibility, (ii) fold stability, (iii) the
DENSITY of the frame in the low-p region that actually drives the served move, and
(iv) whether the served application is interpolation or extrapolation.

Read-only. Prints only.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)
from tools._prem_odds import bust_label, resolved
from tools._prem_odds_gate import (run_chain, brier, logloss, murphy, FOLDS, labels,
                                   design, fit_logistic, sigmoid, logit)

POOL = ROOT / "tools" / "_prem_odds_pool.json"


def main():
    allrows = resolved(json.loads(POOL.read_text(encoding="utf-8")))
    srv = [r for r in allrows if r["has_track"]]
    print(f"frame: {len(allrows)} resolved, {len(srv)} served-comparable")

    # ---- 1. reproduce the point estimates ----
    pt = run_chain(srv, ("INC", "CONST", "R1", "R2"), rng=np.random.default_rng(20260725))
    for k in ("INC", "CONST", "R1", "R2"):
        p, y = pt[k]
        m = murphy(p, y)
        print(f"  {k:<6s} n={len(y):4d} Brier {brier(p,y):.5f} LL {logloss(p,y):.5f} "
              f"rel {m['reliability']:.5f} res {m['resolution']:.5f} meanp {p.mean():.4f}")

    # ---- 2. LOW-p DENSITY: where does the served move come from? ----
    pinc, y = pt["INC"]
    print("\n  INCUMBENT p_bust density in the frame (the served board sits at p>=0.95):")
    edges = [0.0, .05, .10, .20, .30, .50, .70, .90, .95, .99, 1.01]
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (pinc >= lo) & (pinc < hi)
        if m.sum() == 0:
            print(f"    [{lo:.2f},{hi:.2f})  n=   0")
            continue
        print(f"    [{lo:.2f},{hi:.2f})  n={int(m.sum()):4d}  pred {pinc[m].mean():.4f} "
              f"obs {y[m].mean():.4f}  busts {int(y[m].sum()):4d}")

    # ---- 3. FOLD STABILITY of the whole win ----
    print("\n  PER-FOLD (leave-the-fold-in) Brier, INC vs R1:")
    for Y in FOLDS:
        tr = [r for r in srv if r["fold"] < Y]
        te = [r for r in srv if r["fold"] == Y]
        if len(tr) < 25 or len(te) < 10:
            print(f"    fold {Y}: skipped (tr={len(tr)} te={len(te)})")
            continue
        yte = labels(te)
        pi = np.clip(np.array([r["p_bust_inc"] for r in te]), 1e-4, 1 - 1e-4)
        w = fit_logistic(design(tr, "R1"), labels(tr))
        p1 = np.clip(sigmoid(design(te, "R1") @ w), 1e-4, 1 - 1e-4)
        print(f"    fold {Y}: n={len(te):4d} obs {yte.mean():.4f} | INC Brier {brier(pi,yte):.5f} "
              f"-> R1 {brier(p1,yte):.5f}  d={brier(pi,yte)-brier(p1,yte):+.5f} | "
              f"LL {logloss(pi,yte):.4f} -> {logloss(p1,yte):.4f}  "
              f"Platt A={w[0]:+.4f} B={w[1]:+.4f}")

    # ---- 4. leave-one-fold-out: does one fold carry the whole win? ----
    print("\n  DROP-ONE-FOLD (pooled Brier delta INC-R1, positive = R1 better):")
    for drop in (None,) + FOLDS:
        sel = [r for r in srv if r["fold"] != drop] if drop else srv
        res = run_chain(sel, ("INC", "R1"), rng=np.random.default_rng(1))
        if "R1" not in res:
            continue
        pI, yI = res["INC"]; pR, _ = res["R1"]
        print(f"    drop={str(drop):>5s}  n={len(yI):4d}  dBrier {brier(pI,yI)-brier(pR,yI):+.5f} "
              f"dLL {logloss(pI,yI)-logloss(pR,yI):+.5f}")

    # ---- 5. is the served application extrapolation? ----
    xf = ROOT / "data" / "xfv.json"
    if xf.exists():
        doc = json.loads(xf.read_text(encoding="utf-8"))
        recs = doc.get("players") or doc.get("rows") or []
        if isinstance(recs, dict):
            recs = list(recs.values())
        pb = [r.get("p_bust") for r in recs
              if isinstance(r.get("p_bust"), (int, float)) and r.get("active", True)]
        pb = np.array(pb, dtype=float)
        print(f"\n  SERVED board p_bust distribution, n={len(pb)}")
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (pb >= lo) & (pb < hi)
            frac_frame = float(((pinc >= lo) & (pinc < hi)).mean())
            print(f"    [{lo:.2f},{hi:.2f})  board n={int(m.sum()):5d} "
                  f"({m.mean()*100:5.1f}%)   frame {frac_frame*100:5.1f}%")


if __name__ == "__main__":
    raise SystemExit(main())
