# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- (c) p_bucket / p_bust odds, (d) interval coverage."""
from __future__ import annotations
import json, math, statistics, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf   # noqa: E402

F = json.loads((HERE / "_sweep_calib_out" / "frame.json").read_text(encoding="utf-8"))
PRIMARY = [r for r in F["rows"] if r["year"] <= 2020]

BUCKETS = ("bust", "bench", "regular", "good", "star")
EDGES = (3.0, 9.0, 15.0, 24.0)          # summed first-6yr WAR band edges (band * 6)
MID = (0.0, 6.0, 12.0, 19.2, 30.0)      # midpoint_war * 6
CV = (0.0, 0.30, 0.38, 0.48, 0.70)


def realized_bucket(w):
    for i, e in enumerate(EDGES):
        if w < e:
            return i
    return 4


print("=== (c) p_bucket / p_bust calibration, forward-chained folds 2016-2020 ===")
print("odds are served at the REALIZED (pure-model) grade -- efv_score.run:")
print("  probs = vf.p_bucket_given_fv(xfv_grade, is_pit); xfv_grade = realized_implied_fv(...)")
print()

for side in ("hit", "pit"):
    rs = [r for r in PRIMARY if r["side"] == side]
    is_pit = side == "pit"
    for r in rs:
        r["_p"] = vf.p_bucket_given_fv(r["grade_model_raw"], is_pit) or [0] * 5
        r["_rb"] = realized_bucket(r["war"])
    print(f"  {side}: n={len(rs)}   MARGINAL predicted vs realized bucket shares")
    print(f"    {'bucket':>9s} {'pred':>7s} {'real':>7s} {'diff':>7s}")
    for i, b in enumerate(BUCKETS):
        pr = statistics.mean(r["_p"][i] for r in rs)
        re = sum(1 for r in rs if r["_rb"] == i) / len(rs)
        print(f"    {b:>9s} {pr:7.3f} {re:7.3f} {pr-re:+7.3f}")
    # reliability of p_bust in deciles of predicted
    print(f"    p_bust reliability ({side}):")
    srt = sorted(rs, key=lambda r: r["_p"][0])
    k = 10
    for j in range(k):
        g = srt[j * len(srt) // k:(j + 1) * len(srt) // k]
        if not g:
            continue
        pr = statistics.mean(x["_p"][0] for x in g)
        re = sum(1 for x in g if x["_rb"] == 0) / len(g)
        print(f"      bin{j+1} n={len(g):4d} pred={pr:.3f} real={re:.3f} diff={pr-re:+.3f}")
    print()

print("=== also: the odds evaluated at the DISPLAYED grade (what the site shows) ===")
for side in ("hit", "pit"):
    rs = [r for r in PRIMARY if r["side"] == side]
    is_pit = side == "pit"
    pr = statistics.mean((vf.p_bucket_given_fv(r["grade_quantile"], is_pit) or [0] * 5)[0] for r in rs)
    prm = statistics.mean(r["_p"][0] for r in rs)
    re = sum(1 for r in rs if r["_rb"] == 0) / len(rs)
    print(f"  {side}: mean p_bust @realized-grade={prm:.3f}  @displayed-grade={pr:.3f}  realized={re:.3f}")

print()
print("=== (d) interval calibration of the served band ===")
print("The served band_p10/p90 are $M percentiles of the bucket mixture at the DISPLAYED")
print("grade (efv_score._reprice_surplus_on_display). Test the SAME probability object in")
print("WAR units, where truth exists: bucket ~ p_bucket_given_fv(g); WAR | bucket ~ Gamma")
print("(mean = midpoint_war*6, cv = within_bucket_cv); bust = point mass at 0.")

rng = np.random.RandomState(20260725)
NDRAW = 4000


def war_quantiles(probs, qs=(0.10, 0.90)):
    p = np.asarray(probs, dtype=float)
    p = p / p.sum()
    idx = rng.choice(5, size=NDRAW, p=p)
    out = np.empty(NDRAW)
    for b in range(5):
        m = idx == b
        c = int(m.sum())
        if not c:
            continue
        mu, cv = MID[b], CV[b]
        out[m] = 0.0 if (cv <= 0 or mu <= 0) else rng.gamma(1.0 / cv ** 2, mu * cv ** 2, size=c)
    return np.quantile(out, qs), out


for gkey, lbl in (("grade_quantile", "DISPLAYED grade (band basis)"),
                  ("grade_model_raw", "realized grade (p_bust basis)")):
    print(f"\n  --- {lbl} ---")
    for side in ("hit", "pit"):
        rs = [r for r in PRIMARY if r["side"] == side]
        is_pit = side == "pit"
        cov = []
        for r in rs:
            probs = vf.p_bucket_given_fv(r[gkey], is_pit)
            if not probs:
                continue
            (q10, q90), draws = war_quantiles(probs)
            r[f"_q10_{gkey}"] = q10
            r[f"_q90_{gkey}"] = q90
            cov.append(1 if q10 <= r["war"] <= q90 else 0)
        print(f"    {side}: n={len(cov)} marginal 80% coverage = {statistics.mean(cov):.3f}")
        # conditional coverage by grade tier
        by = defaultdict(list)
        for r in rs:
            if f"_q10_{gkey}" not in r:
                continue
            t = max(30, min(60, int(round(r[gkey] / 5) * 5)))
            by[t].append(1 if r[f"_q10_{gkey}"] <= r["war"] <= r[f"_q90_{gkey}"] else 0)
        print("      by grade tier: " + "  ".join(
            f"{t}:{statistics.mean(v):.2f}(n={len(v)})" for t, v in sorted(by.items()) if len(v) >= 10))
        for name, fn in (("level", lambda r: r["level"]),
                         ("acq", lambda r: r["acq"])):
            by = defaultdict(list)
            for r in rs:
                if f"_q10_{gkey}" not in r:
                    continue
                by[fn(r)].append(1 if r[f"_q10_{gkey}"] <= r["war"] <= r[f"_q90_{gkey}"] else 0)
            print(f"      by {name}: " + "  ".join(
                f"{k}:{statistics.mean(v):.2f}(n={len(v)})" for k, v in sorted(by.items(), key=lambda x: str(x[0]))
                if len(v) >= 15))
