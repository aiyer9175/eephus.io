"""SCRATCH (read-only analysis): does the FA pool underperform its own projection?

Adverse-selection test. For each winter W, build the point-in-time fa_projection
for target season W for EVERY corpus veteran, then compare realized-minus-projected
for players who ENTERED free agency that winter (D=1, from fa_signings) vs players
who did not (D=0, retained/controlled).

Nothing is written to the repo. Delete freely.
"""
from __future__ import annotations
import json, math, sqlite3, sys, pickle, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_projection as fp

corpus = pickle.load(open(ROOT / ".cache" / "fa_corpus.pkl", "rb"))
league = corpus["league"]

hist = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
for side in ("hit", "pit"):
    for r in corpus[side]:
        hist[side][r["mlbam"]][r["season"]] = r

# ---- FA entrants by winter -------------------------------------------------
db = sqlite3.connect(ROOT / "prospects.db")
entrants = defaultdict(set)
for pk, cy, pj in db.execute("select player_key, class_year, payload_json from fa_signings"):
    p = json.loads(pj)
    mid = p.get("mlbam_id")
    if mid:
        entrants[int(cy)].add(int(mid))
print("entrant counts:", {y: len(s) for y, s in sorted(entrants.items())})

MINPA = {"hit": 250, "pit": 150}   # prior-season exposure floor
EXPO = {"hit": "pa", "pit": "bf"}

rows = []
for W in range(2015, 2026):
    curves, war_map = fp.fitted_models(corpus, max_season=W - 1)
    ent = entrants.get(W, set())
    for side in ("hit", "pit"):
        for mid, byseason in hist[side].items():
            prev = byseason.get(W - 1)
            cur = byseason.get(W)
            if not prev:
                continue
            if (prev.get(EXPO[side]) or 0) < MINPA[side]:
                continue
            age = prev.get("age")
            if age is None or age < 27 or age > 40:
                continue
            h = [byseason[s] for s in (W - 1, W - 2, W - 3) if s in byseason]
            proj = fp.project_player(h, side, W, curves, league, age + 1,
                                     role=prev.get("role"))
            if not proj:
                continue
            pw = fp.war_from_projection(proj, side, war_map, league, W)
            realized = (cur or {}).get("war")
            played = cur is not None
            # WAR if absent = 0 (replacement); that is the decision-relevant number
            rw = float(realized) if played else 0.0
            rows.append({
                "W": W, "side": side, "mid": mid, "age": age + 1,
                "D": 1 if mid in ent else 0,
                "proj_war": pw, "real_war": rw, "played": int(played),
                "proj_pt": proj.get("pt_proj") or proj.get("ip_proj") or 0.0,
                "real_pt": (cur or {}).get(EXPO[side]) or 0.0,
                "prev_war": prev.get("war"),
                "prev_expo": prev.get(EXPO[side]),
            })

print("n rows", len(rows), "D=1", sum(r["D"] for r in rows))

def summarize(sel, label):
    a = [r for r in sel if r["D"] == 1]
    b = [r for r in sel if r["D"] == 0]
    if len(a) < 20 or len(b) < 20:
        return
    def m(x, k): return statistics.mean([r[k] for r in x])
    def resid(x): return [r["real_war"] - r["proj_war"] for r in x]
    ra, rb = resid(a), resid(b)
    sd = math.sqrt(statistics.pvariance(ra) / len(ra) + statistics.pvariance(rb) / len(rb))
    print(f"{label:28s} nD1={len(a):5d} nD0={len(b):5d} "
          f"projWAR {m(a,'proj_war'):5.2f}/{m(b,'proj_war'):5.2f} "
          f"realWAR {m(a,'real_war'):5.2f}/{m(b,'real_war'):5.2f} "
          f"resid {statistics.mean(ra):+.3f}/{statistics.mean(rb):+.3f} "
          f"diff {statistics.mean(ra)-statistics.mean(rb):+.3f} (se {sd:.3f}) "
          f"play% {m(a,'played'):.2f}/{m(b,'played'):.2f}")

summarize(rows, "ALL")
for side in ("hit", "pit"):
    summarize([r for r in rows if r["side"] == side], f"side={side}")
# age-matched strata
for lo, hi in ((27, 29), (30, 32), (33, 41)):
    summarize([r for r in rows if lo <= r["age"] <= hi], f"age {lo}-{hi}")
# projection strata
for lo, hi in ((-9, 1.0), (1.0, 2.5), (2.5, 99)):
    summarize([r for r in rows if lo <= r["proj_war"] < hi], f"projWAR {lo}-{hi}")

# ---- OLS: resid ~ D + age + proj + side, with year FE -----------------------
try:
    import numpy as np
    ys = np.array([r["real_war"] - r["proj_war"] for r in rows])
    years = sorted({r["W"] for r in rows})
    X = []
    for r in rows:
        base = [1.0, r["D"], r["age"], r["proj_war"], 1.0 if r["side"] == "pit" else 0.0,
                r["age"] ** 2 / 100.0]
        fe = [1.0 if r["W"] == y else 0.0 for y in years[1:]]
        X.append(base + fe)
    X = np.array(X)
    beta, *_ = np.linalg.lstsq(X, ys, rcond=None)
    resid = ys - X @ beta
    dof = len(ys) - X.shape[1]
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    names = ["const", "D_enteredFA", "age", "proj_war", "pit", "age2"] + [f"y{y}" for y in years[1:]]
    print("\nOLS resid_WAR ~ ...   (n=%d)" % len(ys))
    for n, b, s in list(zip(names, beta, se))[:6]:
        print(f"  {n:14s} {b:+.4f}  se {s:.4f}  t {b/s:+.2f}")

    # PLACEBO: pre-treatment residual (season W-1 residual, projected from W-2)
except Exception as e:
    print("OLS failed", e)

# ---- placebo: same D, but residual measured in season W-1 (pre-decision) ----
pre = []
for W in range(2015, 2026):
    curves, war_map = fp.fitted_models(corpus, max_season=W - 2)
    ent = entrants.get(W, set())
    for side in ("hit", "pit"):
        for mid, byseason in hist[side].items():
            prev = byseason.get(W - 2)
            cur = byseason.get(W - 1)
            if not prev or not cur:
                continue
            if (prev.get(EXPO[side]) or 0) < MINPA[side]:
                continue
            age = prev.get("age")
            if age is None or age < 26 or age > 39:
                continue
            h = [byseason[s] for s in (W - 2, W - 3, W - 4) if s in byseason]
            proj = fp.project_player(h, side, W - 1, curves, league, age + 1, role=prev.get("role"))
            if not proj:
                continue
            pw = fp.war_from_projection(proj, side, war_map, league, W - 1)
            pre.append({"D": 1 if mid in ent else 0, "real_war": cur.get("war") or 0.0,
                        "proj_war": pw, "age": age + 1, "side": side, "W": W,
                        "played": 1})
print()
summarize(pre, "PLACEBO (pre-decision)")
