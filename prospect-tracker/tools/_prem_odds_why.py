# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ODDS LANE part (b): WHY is the served p_bust wrong?

Four candidate mechanisms, each measured rather than asserted:
  M1  the mixture is fit pooled and never conditioned on level/age/production
  M2  the training pool is mostly no-track-record rows whose bust behaviour differs
  M3  the bust bucket is pinned at 0 surplus so negative outcomes cannot be expressed
  M4  READING MISMATCH: p_bucket_given_fv was fitted over the CONSENSUS-FV published-list
      population and is keyed on FV, but production reads it at the eFV MODEL grade,
      which is a fitted conditional mean and has a different dispersion.
Read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf                                    # noqa: E402
from tools._prem_odds import bust_label, wilson, resolved       # noqa: E402

POOL = ROOT / "tools" / "_prem_odds_pool.json"


def stats(sel, pk="p_bust_inc"):
    n = len(sel)
    if not n:
        return None
    k = sum(bust_label(r["target_resolved"]) for r in sel)
    lo, hi = wilson(k, n)
    return {"n": n, "obs": k / n, "pred": sum(r[pk] for r in sel) / n,
            "lo": lo, "hi": hi}


def main():
    rows = resolved(json.loads(POOL.read_text(encoding="utf-8")))
    served = [r for r in rows if r["has_track"]]

    # p_bust read at the CONSENSUS grade instead of the eFV grade
    for r in rows:
        cf = r.get("consensus_fv_raw")
        if cf is None:
            r["p_bust_cons"] = None
            continue
        pb = vf.p_bucket_given_fv(float(cf), r["is_pit"])
        r["p_bust_cons"] = float(pb[0]) if pb else None
    with_cons = [r for r in served if r.get("p_bust_cons") is not None]

    print("M4  READING MISMATCH: the same curve, read at the CONSENSUS grade vs the eFV grade")
    print("    (served-comparable, out-of-fold, fully-resolved frame)")
    print(f"    {'keyed on':<22s} {'n':>5s} {'predicted':>10s} {'observed':>9s} {'gap':>8s}")
    for name, key in (("consensus_fv_raw", "p_bust_cons"), ("eFV xfv_grade", "p_bust_inc")):
        s = stats(with_cons, key)
        print(f"    {name:<22s} {s['n']:5d} {s['pred']:10.4f} {s['obs']:9.4f} "
              f"{s['obs'] - s['pred']:+8.4f}")
    print("    If the consensus reading is calibrated and the eFV reading is not, the defect")
    print("    is the READ, not the curve.")

    print("\n    by CONSENSUS-FV band (the curve's own native key):")
    print(f"    {'band':<14s} {'n':>5s} {'predicted':>10s} {'observed':>9s} {'CI95':>17s} {'gap':>8s}")
    for lo, hi in ((20, 40), (40, 45), (45, 50), (50, 55), (55, 80)):
        sel = [r for r in with_cons if lo <= float(r["consensus_fv_raw"]) < hi]
        s = stats(sel, "p_bust_cons")
        if s:
            print(f"    {f'cons {lo}-{hi}':<14s} {s['n']:5d} {s['pred']:10.4f} {s['obs']:9.4f} "
                  f"[{s['lo']:.4f},{s['hi']:.4f}] {s['obs'] - s['pred']:+8.4f}")

    print("\nM2  TRACK-RECORD COMPOSITION: does the gap come from the no-track-record majority?")
    print(f"    {'population':<24s} {'n':>5s} {'predicted':>10s} {'observed':>9s} {'gap':>8s}")
    for name, sel in (("has track record", served),
                      ("no track record", [r for r in rows if not r["has_track"]])):
        s = stats(sel)
        print(f"    {name:<24s} {s['n']:5d} {s['pred']:10.4f} {s['obs']:9.4f} "
              f"{s['obs'] - s['pred']:+8.4f}")

    print("\nM3  NEGATIVE OUTCOMES: are they outside the bust bucket, as claimed?")
    neg = [r for r in served if float(r["target_resolved"]) < 0]
    inb = [r for r in neg if bust_label(r["target_resolved"])]
    print(f"    served-comparable rows with NEGATIVE first-6yr WAR: {len(neg)} of {len(served)} "
          f"({len(neg)/len(served):.1%})")
    print(f"    of those, {len(inb)} ({len(inb)/max(1,len(neg)):.0%}) fall INSIDE the bust bucket "
          f"(band '<0.5' avg annual WAR).")
    print("    => the 'mixture assigns negative outcomes probability zero' defect is a SURPLUS")
    print("       (dollar-fan) defect, not a p_bust defect: p_bust already covers them.")

    # M1 preview: does the gap survive conditioning on grade?
    print("\nM1  CONDITIONAL SURFACE preview: gap by grade band, and within band by stratum")
    print(f"    {'grade band':<14s} {'n':>5s} {'predicted':>10s} {'observed':>9s} {'gap':>8s}")
    for lo, hi in ((20, 40), (40, 45), (45, 50), (50, 55), (55, 80)):
        s = stats([r for r in served if lo <= r["grade"] < hi])
        if s:
            print(f"    {f'eFV {lo}-{hi}':<14s} {s['n']:5d} {s['pred']:10.4f} {s['obs']:9.4f} "
                  f"{s['obs'] - s['pred']:+8.4f}")


if __name__ == "__main__":
    raise SystemExit(main())
