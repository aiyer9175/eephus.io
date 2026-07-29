# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- band anatomy + the two-grade inconsistency on served rows."""
from __future__ import annotations
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf   # noqa: E402

F = json.loads((HERE / "_sweep_calib_out" / "frame.json").read_text(encoding="utf-8"))
PRIMARY = [r for r in F["rows"] if r["year"] <= 2020]
CFG_MID = (0.0, 1.0, 2.0, 3.2, 5.0)
CV = (0.0, 0.30, 0.38, 0.48, 0.70)


def war_q(g, is_pit, qs=(0.10, 0.50, 0.90)):
    p = np.asarray(vf.p_bucket_given_fv(g, is_pit) or [0] * 5, float)
    if p.sum() <= 0:
        return None
    p = p / p.sum()
    k = vf._war_scale_for(g, "pitcher" if is_pit else "hitter")
    mid = [m * k * 6 for m in CFG_MID]
    rng = np.random.RandomState(int(abs(g) * 1000) % 99991)
    idx = rng.choice(5, 8000, p=p)
    out = np.zeros(8000)
    for b in range(1, 5):
        m = idx == b
        c = int(m.sum())
        if c and mid[b] > 0:
            out[m] = rng.gamma(1 / CV[b] ** 2, mid[b] * CV[b] ** 2, size=c)
    return np.quantile(out, qs)


print("=== the served outcome mixture has ZERO mass below 0 WAR ===")
for side in ("hit", "pit"):
    for lbl, sub in (("all", lambda r: True), ("has_milb", lambda r: bool(r["level"]))):
        rs = [r for r in PRIMARY if r["side"] == side and sub(r)]
        neg = sum(1 for r in rs if r["war"] < 0)
        print(f"  {side:3s} {lbl:9s} n={len(rs):4d}  realized first-6yr WAR < 0: {neg} ({neg/len(rs):.3f}); "
              f"min={min(r['war'] for r in rs):.2f}  "
              f"share in [0, 0.001]={sum(1 for r in rs if 0 <= r['war'] <= 0.001)/len(rs):.3f}")

print("\n=== band anatomy on the live-comparable rows (WAR-space analogue of the served band) ===")
for side in ("hit", "pit"):
    rs = [r for r in PRIMARY if r["side"] == side and r["level"]]
    is_pit = side == "pit"
    by = defaultdict(list)
    for r in rs:
        by[max(35, min(60, int(round(r["grade_quantile"] / 5) * 5)))].append(r)
    print(f"  {side}: tier    n     q10     q50     q90   real_p10  real_p50  real_p90  cov  low  high")
    for t in sorted(by):
        g = by[t]
        if len(g) < 5:
            continue
        qs = [war_q(r["grade_quantile"], is_pit) for r in g]
        q10 = statistics.mean(q[0] for q in qs); q50 = statistics.mean(q[1] for q in qs)
        q90 = statistics.mean(q[2] for q in qs)
        w = sorted(r["war"] for r in g)
        cov = sum(1 for r, q in zip(g, qs) if q[0] <= r["war"] <= q[2]) / len(g)
        lo = sum(1 for r, q in zip(g, qs) if r["war"] < q[0]) / len(g)
        hi = sum(1 for r, q in zip(g, qs) if r["war"] > q[2]) / len(g)
        print(f"       {t:4d} {len(g):4d} {q10:7.2f} {q50:7.2f} {q90:7.2f} "
              f"{np.percentile(w,10):9.2f} {np.percentile(w,50):9.2f} {np.percentile(w,90):9.2f} "
              f"{cov:5.2f}{lo:5.2f}{hi:5.2f}")

print("\n=== SERVED rows: the band and the odds are read at DIFFERENT grades ===")
d = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))
act = [v for v in d["by_player"].values() if v.get("kind") == "active"]
gap = [v["xfv_grade_quantile"] - v["xfv_grade_realized"] for v in act
       if v.get("xfv_grade_quantile") is not None and v.get("xfv_grade_realized") is not None]
print(f"  n={len(gap)} displayed-minus-realized grade: mean {statistics.mean(gap):+.2f} FV, "
      f"median {statistics.median(gap):+.2f}, p10 {np.percentile(gap,10):+.2f}, p90 {np.percentile(gap,90):+.2f}")
print("  band_p10/p90 + surplus_mm are priced on xfv_grade_quantile "
      "(efv_score._reprice_surplus_on_display);")
print("  p_bucket / p_bust / dist.p_bust stay on xfv_grade_realized. Same row, two grades.")
odds_gap = []
for v in act:
    gq, gr = v.get("xfv_grade_quantile"), v.get("xfv_grade_realized")
    if gq is None or gr is None:
        continue
    is_pit = v.get("side") == "P"
    a = (vf.p_bucket_given_fv(gr, is_pit) or [0])[0]
    b = (vf.p_bucket_given_fv(gq, is_pit) or [0])[0]
    odds_gap.append(a - b)
print(f"  p_bust(realized) - p_bust(displayed): mean {statistics.mean(odds_gap):+.3f}, "
      f"max {max(odds_gap):+.3f}, share > 0.10: {sum(1 for x in odds_gap if x > 0.10)/len(odds_gap):.3f}")

print("\n=== served $ band degeneracy ===")
c = defaultdict(int)
for v in act:
    p10, p90 = v.get("band_p10_mm"), v.get("band_p90_mm")
    c["p10==0"] += (p10 == 0.0)
    c["p10==p90"] += (p10 is not None and p10 == p90)
    c["p_bust>=0.10"] += ((v.get("p_bust") or 0) >= 0.10)
print(f"  active n={len(act)}: band_p10_mm == 0.0 for {c['p10==0']} ({c['p10==0']/len(act):.4f}); "
      f"band_p10 == band_p90 for {c['p10==p90']} ({c['p10==p90']/len(act):.4f}); "
      f"p_bust >= 0.10 for {c['p_bust>=0.10']} ({c['p_bust>=0.10']/len(act):.4f})")
print("  mechanism: within_bucket_cv.bust = 0.0 -> the bust bucket is a POINT MASS at the")
print("  $0 surplus floor, so the 10th percentile of the mixture is exactly 0 whenever")
print("  p_bust >= 0.10. band_p10_mm carries no player-specific information on this board.")
