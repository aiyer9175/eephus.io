# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Continuous calibration: derive the FV -> six-year-avg controlled-WAR anchors
(`fv_to_6yr_avg_war`) EMPIRICALLY from resolved historical prospect cohorts, so the
surplus model self-updates as new cohorts resolve.

This is the data-driven source for the anchors that the bucket-WAR levels reconcile
to (see value_framework `_fv_war_scale`). It is run as part of `value_framework.py
--fit` (build-time, has DB access); the result is written to the fitted file and
read live by `fv_to_6yr_avg_war`. Rebuilds (run_daily / run_monthly --rebuild-only)
read the committed fitted anchors, so per-run values stay stable until the next fit.

Method (matches docs/surplus-recalibration.md):
  * cohort = prospects with snapshots in the RESOLVED window [year-lag_max, year-lag_min]
    (old enough that their 6-year control window is mostly complete or they clearly
    busted), pooled across hitters/pitchers;
  * realized = sum of the first 6 MLB-season WAR (bust / never-debuted = 0), per year;
  * per FV tier: the bust-INCLUSIVE mean realized WAR/yr, with sample size n;
  * blend with the Edwards-scale-implied reference (config) by a weight that rises
    where the cell is thin/censored, then enforce monotonicity. Pure reference where
    there is no cohort data (e.g. 70/80, out of the resolved sample).

As the snapshot history accrues, the resolved window slides forward automatically
(reference_year defaults to the current year), so re-running --fit re-derives the
anchors from the newly-resolved cohorts.
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import statistics as _st
from collections import defaultdict
from pathlib import Path

_DB_DEFAULT = Path(__file__).resolve().parent / "prospects.db"


def _is_pitcher_positions(positions: list[str]) -> bool:
    npit = sum(1 for p in positions if p[:1] == "P" or p in ("SP", "RP", "LHP", "RHP"))
    return npit > len(positions) / 2


def _cohort(db_path: Path, y0: int, y1: int) -> dict[str, dict]:
    """Resolved cohort: per player, their pooled entry FV (mean over window snapshots),
    role, and realized first-6-MLB-season WAR (0 if never reached MLB)."""
    con = sqlite3.connect(str(db_path))
    try:
        c = con.cursor()
        fvs: dict[str, list[float]] = defaultdict(list)
        pos: dict[str, list[str]] = defaultdict(list)
        for k, fv, p in c.execute(
            "SELECT player_key, fv, position FROM snapshots "
            "WHERE snapshot_date BETWEEN ? AND ? AND fv IS NOT NULL",
            (f"{y0}-01-01", f"{y1}-12-31"),
        ):
            fvs[k].append(float(fv))
            pos[k].append((p or "").upper())
        war: dict[str, float] = {}
        for k, pj in c.execute("SELECT player_key, payload_json FROM career_war"):
            seasons = sorted((int(y), float(w)) for y, w in (json.loads(pj).get("seasons") or {}).items())
            war[k] = sum(w for _, w in seasons[:6])
    finally:
        con.close()
    out = {}
    for k, fl in fvs.items():
        out[k] = {"fv": _st.mean(fl), "is_pit": _is_pitcher_positions(pos[k]), "realized_war": war.get(k, 0.0)}
    return out


def derive_empirical_war_anchors(db_path: str | Path | None = None, *, policy: dict,
                                 reference_year: int | None = None) -> dict | None:
    """Derive the empirical fv_to_6yr_avg_war anchors. Returns None if the DB or a
    usable cohort is unavailable (caller keeps the config seed). Pure function of the
    DB + policy + reference_year (captured in the result for reproducibility)."""
    db_path = Path(db_path) if db_path else _DB_DEFAULT
    if not db_path.exists():
        return None
    ry = int(reference_year or _dt.date.today().year)
    lag_min = int(policy.get("resolved_lag_min", 6))
    lag_max = int(policy.get("resolved_lag_max", 9))
    y0, y1 = ry - lag_max, ry - lag_min
    cohort = _cohort(db_path, y0, y1)
    if len(cohort) < int(policy.get("min_cohort", 200)):
        return None

    tiers = [int(t) for t in policy.get("tiers", [40, 45, 50, 55, 60, 65, 70, 80])]
    ref = {int(k): float(v) for k, v in policy.get("public_reference", {}).items()}
    min_n = int(policy.get("min_n_robust", 40))
    w_base = float(policy.get("blend_weight_public", 0.5))
    w_thin = float(policy.get("blend_thin_extra", 0.4))

    # bust-inclusive realized WAR/yr by tier (pooled roles)
    by_tier: dict[int, list[float]] = defaultdict(list)
    for r in cohort.values():
        tier = int(round(r["fv"] / 5) * 5)
        by_tier[tier].append(r["realized_war"] / 6.0)

    diag, raw = {}, {}
    for t in tiers:
        ws = by_tier.get(t, [])
        n = len(ws)
        emp = _st.mean(ws) if n else None
        rt = ref.get(t)
        if rt is None:  # no reference for this tier -> interpolate from neighbors below
            rt = max((ref[k] for k in ref if k <= t), default=ref[min(ref)] if ref else 0.0)
        if n == 0:
            w = 1.0                                   # no data -> pure reference
            val = rt
        else:
            w = min(0.95, w_base + (w_thin * max(0.0, 1.0 - n / min_n)))
            val = (1.0 - w) * emp + w * rt
        raw[t] = val
        diag[t] = {"n": n, "empirical_war_yr": round(emp, 3) if emp is not None else None,
                   "reference_war_yr": round(rt, 3), "blend_w_public": round(w, 3),
                   "bust_pct": round(100 * sum(1 for x in ws if x < 0.5 / 6) / n, 1) if n else None}

    # enforce monotone non-decreasing in FV, round
    anchors, prev = {}, None
    for t in tiers:
        v = raw[t] if prev is None else max(raw[t], prev)
        anchors[str(t)] = round(v, 2)
        prev = v

    return {
        "anchors": anchors,
        "diagnostics": diag,
        "cohort_window": [y0, y1],
        "reference_year": ry,
        "n_cohort": len(cohort),
        "policy_digest": {"min_n_robust": min_n, "blend_weight_public": w_base, "blend_thin_extra": w_thin},
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }


if __name__ == "__main__":  # quick manual derivation/inspection
    import sys
    import value_framework as vf
    pol = vf._config().get("anchor_calibration", {})
    res = derive_empirical_war_anchors(policy=pol)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(res, indent=2))
