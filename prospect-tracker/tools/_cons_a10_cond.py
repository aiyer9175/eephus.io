# A10 -- (a) conditional per-outlet accuracy with CIs (the "is a source better at
# the top / on college bats" question), (b) second-metric (AUC) read for the gate,
# (c) blast radius of RETIRING the shipped source weights.
from __future__ import annotations

import collections
import json

import numpy as np

from _cons_data import cluster_bootstrap, ci, load_matrix_rows, spearman, auc, DATA, OUT

rows = load_matrix_rows()
pair = [r for r in rows if r["fg"] is not None and r["mp"] is not None]
print(f"paired pool n={len(pair)}")


def cell(sub, label):
    if len(sub) < 80:
        return None
    k = np.array([r["player_key"] for r in sub])
    fg = np.array([r["fg"] for r in sub], float)
    mp = np.array([r["mp"] for r in sub], float)
    t = np.array([r["target"] for r in sub], float)
    lab = t >= 3.0
    d_rho = lambda i: spearman(fg[i], t[i]) - spearman(mp[i], t[i])
    obs = d_rho(np.arange(len(sub)))
    bs = cluster_bootstrap(k, d_rho, B=1200, seed=7)
    lo, hi = ci(bs)
    a_obs = None
    if lab.sum() >= 15 and (~lab).sum() >= 15:
        a_obs = auc(fg, lab) - auc(mp, lab)
    return {"label": label, "n": len(sub),
            "rho_fg": spearman(fg, t), "rho_mp": spearman(mp, t),
            "d": obs, "ci": [lo, hi], "d_auc": a_obs,
            "gap": float((mp - fg).mean())}


CUTS = [
    ("ALL", lambda r: True),
    ("top of board (cons>=50)", lambda r: r["cons"] >= 50),
    ("mid (45<=cons<50)", lambda r: 45 <= r["cons"] < 50),
    ("fringe (cons<45)", lambda r: r["cons"] < 45),
    ("hitters", lambda r: r["side"] == "hit"),
    ("pitchers", lambda r: r["side"] == "pit"),
    ("IFA", lambda r: r["is_ifa"]),
    ("college", lambda r: r["is_college"]),
    ("HS/other", lambda r: not r["is_ifa"] and not r["is_college"]),
    ("college bats", lambda r: r["is_college"] and r["side"] == "hit"),
    ("college arms", lambda r: r["is_college"] and r["side"] == "pit"),
    ("IFA bats", lambda r: r["is_ifa"] and r["side"] == "hit"),
    ("IFA arms", lambda r: r["is_ifa"] and r["side"] == "pit"),
    ("<=2019 decisions", lambda r: r["decision_year"] <= 2019),
    (">=2020 decisions", lambda r: r["decision_year"] >= 2020),
]
print("\n=== A10a. CONDITIONAL head-to-head: FanGraphs vs MLB Pipeline, "
      "rank correlation with realized first-6yr bWAR ===")
print(f"{'cut':>24} {'n':>5} {'rho FG':>8} {'rho MP':>8} {'d(FG-MP)':>9} "
      f"{'CI95':>21} {'dAUC':>8} {'scale gap':>10}")
out = []
for lbl, sel in CUTS:
    c = cell([r for r in pair if sel(r)], lbl)
    if c is None:
        print(f"{lbl:>24}  (n<80, not scored)")
        continue
    out.append(c)
    print(f"{lbl:>24} {c['n']:>5} {c['rho_fg']:>8.4f} {c['rho_mp']:>8.4f} "
          f"{c['d']:>+9.4f} [{c['ci'][0]:+.4f},{c['ci'][1]:+.4f}] "
          f"{(f'{c[chr(100)+chr(95)+chr(97)+chr(117)+chr(99)]:+.4f}' if c['d_auc'] is not None else '     n/a'):>8} "
          f"{c['gap']:>+10.3f}")
sig = [c for c in out if c["ci"][0] > 0 or c["ci"][1] < 0]
print(f"\n  cells where the two outlets are DISTINGUISHABLE (CI95 excludes 0): "
      f"{len(sig)} of {len(out)}  {[c['label'] for c in sig]}")
print("  (with 15 cuts, ~0.75 false positives are expected at alpha=0.05 by chance alone)")

# ---------------------------------------------------------------------------
# (c) blast radius of RETIRING the shipped source weights on the served board
# ---------------------------------------------------------------------------
import math
SHIPPED_W = {"fangraphs": 0.9363, "mlb_pipeline": 1.0637}
ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))["players"]
moved = tot = 0
deltas = []
disp = collections.Counter()
for p in ts:
    pts = [q for q in (p.get("points") or []) if q.get("snapshot_date")]
    if not pts:
        continue
    pt = max(pts, key=lambda q: q["snapshot_date"])
    per = pt.get("per_source") or {}
    fvs = {s: v.get("fv_published") for s, v in per.items() if v.get("fv_published") is not None}
    if len(fvs) < 2 or not ({"fangraphs", "mlb_pipeline"} & set(fvs)):
        continue
    # the WEIGHTS only matter when the weighted and equal means differ
    wnum = sum(SHIPPED_W.get(s, 1.0) * v for s, v in fvs.items())
    wden = sum(SHIPPED_W.get(s, 1.0) for s in fvs)
    d = sum(fvs.values()) / len(fvs) - wnum / wden
    tot += 1
    deltas.append(d)
    a, b = math.ceil(wnum / wden), math.ceil(sum(fvs.values()) / len(fvs))
    disp[b - a] += 1
    if b != a:
        moved += 1
deltas = np.array(deltas)
print(f"\n=== A10b. blast radius of RETIRING the shipped source weights "
      f"(equal votes everywhere) ===")
print(f"  multi-source served players affected: {tot}")
print(f"  raw consensus move: mean {deltas.mean():+.4f} FV  "
      f"p5 {np.percentile(deltas,5):+.3f}  p95 {np.percentile(deltas,95):+.3f}  "
      f"max|d| {np.abs(deltas).max():.3f}")
print(f"  DISPLAYED (ceil) grade would move: {moved} ({moved/max(tot,1):.1%})  "
      f"{dict(sorted(disp.items()))}")
json.dump({"conditional": out, "retire_weights": {"n": tot,
           "mean": float(deltas.mean()), "moved_disp": moved}},
          open(OUT / "a10_cond.json", "w"), indent=1)
