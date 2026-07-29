# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- exploratory pass over the forward-chained frame."""
from __future__ import annotations
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf   # noqa: E402

F = json.loads((HERE / "_sweep_calib_out" / "frame.json").read_text(encoding="utf-8"))
ROWS = F["rows"]
PRIMARY = [r for r in ROWS if r["year"] <= 2020]
LATE = [r for r in ROWS if r["year"] >= 2021]

print("PRIMARY folds 2016-2020 (fully resolved):")
for side in ("hit", "pit"):
    rs = [r for r in PRIMARY if r["side"] == side]
    nb = sum(1 for r in rs if r["kind"] == "bust")
    nc = sum(1 for r in rs if r["censored"])
    print(f"  {side}: n={len(rs)} bust={nb} censored={nc} "
          f"mean_realized={statistics.mean(r['war'] for r in rs):.2f}")
print("LATE folds 2021-2024:")
for side in ("hit", "pit"):
    rs = [r for r in LATE if r["side"] == side]
    print(f"  {side}: n={len(rs)} bust={sum(1 for r in rs if r['kind']=='bust')} "
          f"censored={sum(1 for r in rs if r['censored'])}")

print()
print("=== (0) LEVEL check on the PREDICTION itself (rank_war / xfv_war, WAR units) ===")
for side in ("hit", "pit"):
    rs = [r for r in PRIMARY if r["side"] == side]
    for key in ("cons_war", "xfv_war", "rank_war"):
        print(f"  {side} {key:9s} mean_pred={statistics.mean(r[key] for r in rs):6.2f} "
              f"mean_real={statistics.mean(r['war'] for r in rs):6.2f} "
              f"bias={statistics.mean(r[key]-r['war'] for r in rs):+6.2f}")

print()
print("=== (a) reliability of the DISPLAYED grade vs realized WAR ===")
print("declared level meaning: E[first-6yr summed WAR] = 6 * vf.fv_to_6yr_avg_war(grade)")


def implied(g):
    v = vf.fv_to_6yr_avg_war(g)
    return None if v is None else v * 6.0


def tier(g):
    if g is None:
        return None
    b = int(round(g / 5.0) * 5)
    return max(30, min(65, b))


for gkey in ("grade_quantile", "grade_board", "fv"):
    print(f"\n  --- grade key: {gkey} ---")
    for side in ("hit", "pit"):
        rs = [r for r in PRIMARY if r["side"] == side and r.get(gkey) is not None]
        cells = defaultdict(list)
        for r in rs:
            cells[tier(r[gkey])].append(r)
        print(f"   {side}: tier      n   mean_g  implied  realized   bias   med_real")
        for t in sorted(cells):
            g = cells[t]
            mg = statistics.mean(x[gkey] for x in g)
            im = statistics.mean(implied(x[gkey]) for x in g)
            re = statistics.mean(x["war"] for x in g)
            md = statistics.median(x["war"] for x in g)
            print(f"        {t:5d} {len(g):5d}  {mg:6.1f}  {im:7.2f}  {re:7.2f}  {re-im:+6.2f}  {md:7.2f}")
