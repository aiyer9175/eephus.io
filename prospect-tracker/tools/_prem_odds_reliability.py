# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ODDS LANE part (a): WHERE is the served p_bust wrong by more than sampling error?

Reliability of the incumbent p_bust on the out-of-fold, fully-resolved calibration
frame, conditioned on level / age / production and their interaction. Read-only.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools._prem_odds import bust_label, wilson, resolved      # noqa: E402

POOL = ROOT / "tools" / "_prem_odds_pool.json"
LEVELS = ("DSL", "CPX", "A", "A+", "AA", "AAA")


def load():
    return resolved(json.loads(POOL.read_text(encoding="utf-8")))


def cell(sel):
    n = len(sel)
    if not n:
        return None
    obs_k = sum(bust_label(r["target_resolved"]) for r in sel)
    obs = obs_k / n
    pred = sum(r["p_bust_inc"] for r in sel) / n
    lo, hi = wilson(obs_k, n)
    # "wrong by more than its own sampling error" = predicted outside the
    # Wilson CI95 of the observed frequency.
    return {"n": n, "obs": obs, "pred": pred, "gap": obs - pred,
            "lo": lo, "hi": hi, "outside": not (lo <= pred <= hi)}


def show(title, groups):
    print(f"\n{title}")
    print(f"  {'stratum':<34s} {'n':>5s} {'observed':>9s} {'CI95':>17s} "
          f"{'served':>8s} {'gap':>8s}  flag")
    for name, sel in groups:
        c = cell(sel)
        if not c:
            continue
        flag = "MISCALIBRATED" if c["outside"] else "ok"
        print(f"  {name:<34s} {c['n']:5d} {c['obs']:9.4f} "
              f"[{c['lo']:.4f},{c['hi']:.4f}] {c['pred']:8.4f} {c['gap']:+8.4f}  {flag}")


def age_band(r):
    a = r.get("milb_age")
    if a is None:
        return None
    a = float(a)
    return "age<=21" if a <= 21 else ("age 21-23.5" if a < 23.5 else "age>=23.5")


def prod_band(r):
    o = r.get("ops_rel")
    if o is None:
        return None
    return "ops_rel<0 (below median)" if float(o) < 0 else "ops_rel>=0"


def main():
    rows = load()
    served = [r for r in rows if r["has_track"]]
    print(f"out-of-fold fully-resolved frame: {len(rows)} rows "
          f"({len(served)} served-comparable, i.e. with a MiLB track record)")

    show("BY TRACK RECORD (the board shows only the first group)", [
        ("has track record", served),
        ("no track record", [r for r in rows if not r["has_track"]]),
    ])

    show("SERVED-COMPARABLE, BY ROLE", [
        ("hitters", [r for r in served if not r["is_pit"]]),
        ("pitchers", [r for r in served if r["is_pit"]]),
    ])

    show("SERVED-COMPARABLE, BY SERVED GRADE BAND", [
        (f"grade {lo}-{hi}", [r for r in served if lo <= r["grade"] < hi])
        for lo, hi in ((20, 35), (35, 40), (40, 45), (45, 50), (50, 55), (55, 80))
    ])

    show("SERVED-COMPARABLE, BY LEVEL", [
        (lv, [r for r in served if r["level"] == lv]) for lv in LEVELS
    ])

    show("SERVED-COMPARABLE, BY AGE BAND", [
        (b, [r for r in served if age_band(r) == b])
        for b in ("age<=21", "age 21-23.5", "age>=23.5")
    ])

    show("SERVED-COMPARABLE, BY PRODUCTION BAND", [
        (b, [r for r in served if prod_band(r) == b])
        for b in ("ops_rel<0 (below median)", "ops_rel>=0")
    ])

    # --- the interaction the complaint lives in --------------------------
    upper = [r for r in served if r["level"] in ("AA", "AAA")]
    show("INTERACTION: upper minors (AA/AAA) x age x production", [
        (f"{ab} & {pb}", [r for r in upper if age_band(r) == ab and prod_band(r) == pb])
        for ab in ("age<=21", "age 21-23.5", "age>=23.5")
        for pb in ("ops_rel<0 (below median)", "ops_rel>=0")
    ])

    show("THE BRADFIELD STRATUM (AAA, age>=23.5, ops_rel<0) and its neighbours", [
        ("AAA, age>=23.5, ops_rel<0",
         [r for r in served if r["level"] == "AAA" and age_band(r) == "age>=23.5"
          and prod_band(r) == "ops_rel<0 (below median)"]),
        ("AAA, age>=23.5, ops_rel>=0",
         [r for r in served if r["level"] == "AAA" and age_band(r) == "age>=23.5"
          and prod_band(r) == "ops_rel>=0"]),
        ("AAA, age<23.5, ops_rel<0",
         [r for r in served if r["level"] == "AAA" and age_band(r) in ("age<=21", "age 21-23.5")
          and prod_band(r) == "ops_rel<0 (below median)"]),
        ("AAA, age<23.5, ops_rel>=0",
         [r for r in served if r["level"] == "AAA" and age_band(r) in ("age<=21", "age 21-23.5")
          and prod_band(r) == "ops_rel>=0"]),
    ])

    # --- reliability by predicted-probability decile (the classic view) ---
    print("\nRELIABILITY BY PREDICTED p_bust DECILE (served-comparable)")
    ss = sorted(served, key=lambda r: r["p_bust_inc"])
    m = 8
    print(f"  {'bin':<16s} {'n':>5s} {'served':>8s} {'observed':>9s} {'CI95':>17s} {'gap':>8s}  flag")
    for i in range(m):
        chunk = ss[i * len(ss) // m:(i + 1) * len(ss) // m]
        c = cell(chunk)
        if not c:
            continue
        rng = f"{chunk[0]['p_bust_inc']:.2f}-{chunk[-1]['p_bust_inc']:.2f}"
        flag = "MISCALIBRATED" if c["outside"] else "ok"
        print(f"  {rng:<16s} {c['n']:5d} {c['pred']:8.4f} {c['obs']:9.4f} "
              f"[{c['lo']:.4f},{c['hi']:.4f}] {c['gap']:+8.4f}  {flag}")


if __name__ == "__main__":
    raise SystemExit(main())
