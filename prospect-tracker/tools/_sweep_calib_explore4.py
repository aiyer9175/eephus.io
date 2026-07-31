# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- restrict to the LIVE-COMPARABLE population.

The served board scores only players WITH a pro track record (xfv.json meta:
"eFV abstains on players with no MiLB production"), so the calibration that
governs served numbers must be measured on matrix rows that HAVE milb features.
Two thirds of the training matrix does not, and that mass is what props the
marginal statistics up.
"""
from __future__ import annotations
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf   # noqa: E402

F = json.loads((HERE / "_sweep_calib_out" / "frame.json").read_text(encoding="utf-8"))
PRIMARY = [r for r in F["rows"] if r["year"] <= 2020]
EDGES = (3.0, 9.0, 15.0, 24.0)


def implied(g):
    v = vf.fv_to_6yr_avg_war(g)
    return None if v is None else v * 6.0


def rb(w):
    for i, e in enumerate(EDGES):
        if w < e:
            return i
    return 4


def table(rows, side, gkey="grade_quantile"):
    by = defaultdict(list)
    for r in rows:
        by[max(30, min(65, int(round(r[gkey] / 5) * 5)))].append(r)
    print(f"   {side}: tier    n   grade  implied   real    bias   p_bust  bust_real  gap")
    for t in sorted(by):
        g = by[t]
        if len(g) < 5:
            continue
        mg = statistics.mean(x[gkey] for x in g)
        im = statistics.mean(implied(x[gkey]) for x in g)
        re = statistics.mean(x["war"] for x in g)
        pb = statistics.mean((vf.p_bucket_given_fv(x["grade_model_raw"], side == "pit") or [0])[0] for x in g)
        br = sum(1 for x in g if x["war"] < 3.0) / len(g)
        print(f"        {t:4d} {len(g):4d}  {mg:6.1f} {im:7.2f} {re:7.2f} {re-im:+7.2f}  {pb:6.3f}  {br:8.3f} {pb-br:+6.3f}")


print("=== LIVE-COMPARABLE subset: rows WITH a MiLB track record ===")
for side in ("hit", "pit"):
    rs = [r for r in PRIMARY if r["side"] == side and r["level"]]
    nb = sum(1 for r in rs if r["kind"] == "bust")
    print(f"\n {side}: n={len(rs)} (busts {nb}, {nb/len(rs):.1%})  "
          f"mean_implied={statistics.mean(implied(r['grade_quantile']) for r in rs):.2f} "
          f"mean_real={statistics.mean(r['war'] for r in rs):.2f} "
          f"pooled_bias={statistics.mean(r['war']-implied(r['grade_quantile']) for r in rs):+.2f}")
    table(rs, side)
    pb = statistics.mean((vf.p_bucket_given_fv(r["grade_model_raw"], side == "pit") or [0])[0] for r in rs)
    br = sum(1 for r in rs if r["war"] < 3.0) / len(rs)
    print(f"   marginal p_bust={pb:.3f} realized_bust={br:.3f} gap={pb-br:+.3f}")

print("\n=== the NO-track-record mass (not scored live, but 2/3 of the training pool) ===")
for side in ("hit", "pit"):
    rs = [r for r in PRIMARY if r["side"] == side and not r["level"]]
    pb = statistics.mean((vf.p_bucket_given_fv(r["grade_model_raw"], side == "pit") or [0])[0] for r in rs)
    br = sum(1 for r in rs if r["war"] < 3.0) / len(rs)
    print(f" {side}: n={len(rs)} bust_share={sum(1 for r in rs if r['kind']=='bust')/len(rs):.3f} "
          f"mean_real={statistics.mean(r['war'] for r in rs):.2f} "
          f"implied={statistics.mean(implied(r['grade_quantile']) for r in rs):.2f} "
          f"p_bust={pb:.3f} realized_bust={br:.3f}")

print("\n=== bust-threshold sensitivity (realized bust rate at several definitions) ===")
for side in ("hit", "pit"):
    for sub, lbl in ((lambda r: True, "all"), (lambda r: bool(r["level"]), "has_milb")):
        rs = [r for r in PRIMARY if r["side"] == side and sub(r)]
        row = " ".join(f"<{t}:{sum(1 for r in rs if r['war']<t)/len(rs):.3f}" for t in (0.5, 1.0, 3.0, 6.0))
        pb = statistics.mean((vf.p_bucket_given_fv(r["grade_model_raw"], side == "pit") or [0])[0] for r in rs)
        print(f" {side:3s} {lbl:9s} n={len(rs):4d}  {row}   mean_p_bust={pb:.3f}")

print("\n=== level meaning of the DISPLAYED grade vs the model's own WAR prediction ===")
print("xfv_war_6yr (served) is a direct E[first-6yr WAR]; check ITS level calibration")
for side in ("hit", "pit"):
    for sub, lbl in ((lambda r: True, "all"), (lambda r: bool(r["level"]), "has_milb")):
        rs = [r for r in PRIMARY if r["side"] == side and sub(r)]
        print(f" {side:3s} {lbl:9s} n={len(rs):4d} mean_xfv_war={statistics.mean(r['xfv_war'] for r in rs):6.2f} "
              f"mean_rank_war={statistics.mean(r['rank_war'] for r in rs):6.2f} "
              f"mean_real={statistics.mean(r['war'] for r in rs):6.2f}")
    # decile reliability of rank_war (WAR units, no anchor involved)
    rs = [r for r in PRIMARY if r["side"] == side]
    srt = sorted(rs, key=lambda r: r["rank_war"])
    print(f"   {side} rank_war decile reliability (pred vs real, WAR units):")
    for j in range(10):
        g = srt[j * len(srt) // 10:(j + 1) * len(srt) // 10]
        print(f"     d{j+1} n={len(g):4d} pred={statistics.mean(x['rank_war'] for x in g):6.2f} "
              f"real={statistics.mean(x['war'] for x in g):6.2f} "
              f"bias={statistics.mean(x['rank_war']-x['war'] for x in g):+6.2f}")
