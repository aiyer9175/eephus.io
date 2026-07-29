"""SCRATCH: is UNEXPLAINED playing time a revealed-preference signal of team
private information? Test: residual PT in season W-1 (actual minus point-in-time
projected PT) predicting the WAR residual in season W, conditional on projected WAR.
Also: does it predict SURVIVAL (playing at all in W)?
"""
from __future__ import annotations
import math, pickle, statistics, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import fa_projection as fp

corpus = pickle.load(open(ROOT / ".cache" / "fa_corpus.pkl", "rb"))
league = corpus["league"]
hist = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
for side in ("hit", "pit"):
    for r in corpus[side]:
        hist[side][r["mlbam"]][r["season"]] = r

EXPO = {"hit": "pa", "pit": "bf"}
PTKEY = {"hit": "pt_proj", "pit": "ip_proj"}
rows = []
for W in range(2008, 2026):
    c1, w1 = fp.fitted_models(corpus, max_season=W - 2)   # to project season W-1
    c2, w2 = fp.fitted_models(corpus, max_season=W - 1)   # to project season W
    for side in ("hit", "pit"):
        for mid, bys in hist[side].items():
            s2 = bys.get(W - 2); s1 = bys.get(W - 1)
            if not s2 or not s1:
                continue
            if (s2.get(EXPO[side]) or 0) < 200:
                continue
            a2 = s2.get("age")
            if a2 is None or not (22 <= a2 <= 39):
                continue
            h2 = [bys[s] for s in (W - 2, W - 3, W - 4) if s in bys]
            pj1 = fp.project_player(h2, side, W - 1, c1, league, a2 + 1, role=s2.get("role"))
            if not pj1:
                continue
            ptp = pj1.get(PTKEY[side]) or 0.0
            if side == "pit":
                act_pt = (s1.get("ip") or 0.0)
            else:
                act_pt = (s1.get("pa") or 0.0)
            if ptp <= 0:
                continue
            pt_resid = (act_pt - ptp) / ptp          # relative residual PT
            h1 = [bys[s] for s in (W - 1, W - 2, W - 3) if s in bys]
            pj2 = fp.project_player(h1, side, W, c2, league, a2 + 2, role=s1.get("role"))
            if not pj2:
                continue
            pw = fp.war_from_projection(pj2, side, w2, league, W)
            cur = bys.get(W)
            rows.append({"W": W, "side": side, "age": a2 + 2, "pt_resid": max(-1.0, min(2.0, pt_resid)),
                         "proj_war": pw, "war": (cur.get("war") if cur else 0.0) or 0.0,
                         "played": 1 if cur else 0,
                         "prev_war": s1.get("war") or 0.0})
print("n =", len(rows))

def ols(y, X, names):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ b
    s2 = float(r @ r) / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X)))
    for n, bb, ss in zip(names, b, se):
        print(f"  {n:14s} {bb:+.4f} se {ss:.4f} t {bb/ss:+.2f}")
    return b

for side in ("hit", "pit", "both"):
    sub = rows if side == "both" else [r for r in rows if r["side"] == side]
    print(f"\n--- {side} (n={len(sub)}) : resid_WAR_W ~ pt_resid_{{W-1}} + proj + age ---")
    y = np.array([r["war"] - r["proj_war"] for r in sub])
    X = np.array([[1.0, r["pt_resid"], r["proj_war"], r["age"], r["age"]**2/100.0] for r in sub])
    ols(y, X, ["const", "pt_resid", "proj_war", "age", "age2"])
    print(f"--- {side}: PLAYED_W ~ pt_resid + proj + age (LPM) ---")
    y2 = np.array([float(r["played"]) for r in sub])
    ols(y2, X, ["const", "pt_resid", "proj_war", "age", "age2"])

# terciles of pt_resid
sub = sorted(rows, key=lambda r: r["pt_resid"])
q = len(sub)//3
print("\npt_resid terciles (all):")
for i, ch in enumerate([sub[:q], sub[q:2*q], sub[2*q:]]):
    rr = [r["war"] - r["proj_war"] for r in ch]
    print(f"  T{i+1}: n={len(ch):5d} ptresid med {statistics.median([r['pt_resid'] for r in ch]):+.2f} "
          f"WARresid {statistics.mean(rr):+.3f} +- {1.96*statistics.stdev(rr)/math.sqrt(len(rr)):.3f} "
          f"played {statistics.mean([r['played'] for r in ch]):.3f}")
