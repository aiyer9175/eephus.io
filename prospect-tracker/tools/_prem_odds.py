# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ODDS LANE: is the SERVED p_bust calibrated CONDITIONAL on stratum?

p_bust is served as vf.p_bucket_given_fv(xfv_grade, is_pit)[bust] -- a pure function of
the model's realized-implied grade and the role. It sees NO level, NO age, NO production.
This lab builds the served analog out-of-fold (forward-chained refit per cohort year,
exactly efv_score.run's chain: ridge -> linear cal -> xfv_war -> realized_implied_fv ->
p_bucket) and measures reliability by stratum.

Read-only w.r.t. production. Nothing here is imported by the site.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

import value_framework as vf                                    # noqa: E402
import efv_model as em                                          # noqa: E402
import efv_score as es                                          # noqa: E402
from efv_dataset import matrix_path                             # noqa: E402

BUST_AVG_WAR = 0.5          # engine band: bust = 6yr-AVERAGE annual WAR < 0.5
TARGET_SEASONS = es.TARGET_SEASONS

# CALIBRATION FRAME. Production forward-chains on SCORED_YEARS (2020-2023), but
# 2021-2023 are CENSORED for every debuted row (a 6-season window that has not
# closed) and therefore resolve as bust-only: 3 of the 4 shipped folds cannot
# test a probability at all. Decision years 2014-2020 are the years in which
# EVERY row -- debuted and bust -- carries a closed 6-season window, so they are
# the only unbiased frame for a calibration measurement. 7 forward-chained folds,
# each trained strictly on earlier decision years.
CAL_YEARS = (2014, 2015, 2016, 2017, 2018, 2019, 2020)


def bust_label(target_resolved: float) -> int:
    """The SHIPPED bust event: 6yr-average annual WAR < 0.5, i.e. summed < 3.0."""
    return 1 if (float(target_resolved) / float(TARGET_SEASONS)) < BUST_AVG_WAR else 0


def oos_served_rows(side: str) -> list[dict]:
    """Forward-chained out-of-fold replication of the served scoring chain.

    Returns one dict per labeled row scored out-of-fold, carrying the incumbent
    served p_bust and every stratum covariate the board could condition on."""
    is_pit = side == "pit"
    keys, _mono = em._feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if not (r.get("kind") == "bust" and r.get("bust_recent"))]
    by_key = {r["player_key"]: r for r in pool}
    data = em._prep(pool, "target_censored", side)

    out = []
    for yr in CAL_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ridge = em._fit_ridge(tr, keys)
        ols = em._fit_ols_fv(tr)
        if not (ridge and ols):
            continue
        cal = em._fit_linear_calibration(
            [(em._predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            pk = r["player_key"]
            src = by_key[pk]
            xfv_war = max(-2.0, a + b * em._predict(ridge, r["feats"]))
            pos = src.get("position")
            dyear = src.get("debut_year") or 2020
            age_debut = es._age_at(src.get("birth_date"), dyear)
            gm_age = es._grade_map_age(age_debut, 0.0)
            grade = vf.realized_implied_fv(xfv_war, is_pit, age=gm_age, position=pos,
                                           exposure_seasons=TARGET_SEASONS)
            if grade is None:
                continue
            probs = vf.p_bucket_given_fv(grade, is_pit)
            if not probs:
                continue
            mb = src.get("milb") if isinstance(src.get("milb"), dict) else None
            rates_missing = float((mb or {}).get("rates_missing", 1.0) or 0.0)
            has_track = bool(mb) and rates_missing == 0.0
            out.append({
                "player_key": pk, "side": side, "is_pit": is_pit,
                "decision_year": r["decision_year"], "fold": yr,
                "kind": src.get("kind"),
                "censored": bool(src.get("censored")),
                "target_resolved": src.get("target_resolved"),
                "xfv_war": float(xfv_war), "grade": float(grade),
                "p_bust_inc": float(probs[0]),
                "consensus_fv_raw": src.get("consensus_fv_raw"),
                "has_track": has_track,
                "level": (mb or {}).get("milb_level"),
                "level_rank": (mb or {}).get("level_rank"),
                "milb_age": (mb or {}).get("age"),
                "age_rel_level": (mb or {}).get("age_rel_level"),
                "ops_rel": (mb or {}).get("ops_rel"),
                "k_rel": (mb or {}).get("k_rel"),
                "n_milb_seasons": (mb or {}).get("n_milb_seasons"),
                "tool_speed": src.get("tool_speed"),
                "position": pos,
            })
    return out


def resolved(rows):
    return [r for r in rows
            if r["censored"] is False and isinstance(r["target_resolved"], (int, float))]


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main():
    allrows = []
    for side in ("hit", "pit"):
        rs = oos_served_rows(side)
        print(f"{side}: {len(rs)} scored out-of-fold "
              f"({sum(1 for r in rs if r['censored'] is False)} resolved, "
              f"{sum(1 for r in rs if r['has_track'])} with a track record)")
        allrows += rs
    out = ROOT / "tools" / "_prem_odds_pool.json"
    out.write_text(json.dumps(allrows, separators=(",", ":")), encoding="utf-8")
    print("wrote", out, len(allrows))

    res = resolved(allrows)
    print(f"\nRESOLVED out-of-fold pool: {len(res)}")
    for name, sel in (("ALL resolved", res),
                      ("has track record (SERVED-comparable)",
                       [r for r in res if r["has_track"]]),
                      ("NO track record (never on the board)",
                       [r for r in res if not r["has_track"]])):
        n = len(sel)
        if not n:
            continue
        obs = sum(bust_label(r["target_resolved"]) for r in sel)
        pred = sum(r["p_bust_inc"] for r in sel)
        lo, hi = wilson(obs, n)
        print(f"  {name:42s} n={n:5d}  observed {obs/n:.4f} "
              f"CI95[{lo:.4f},{hi:.4f}]  predicted {pred/n:.4f}  "
              f"gap {obs/n - pred/n:+.4f}")


if __name__ == "__main__":
    raise SystemExit(main())
