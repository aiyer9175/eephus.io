"""Phase 1B, step 3: split-half reliability, month-to-month reliability, and
stabilization curves for every candidate metric (scripts/phase1b/metrics.py),
per level.

TRACKED_ONLY metrics are still run at every level -- the metric's own
denominator filter (df["tracked"]) naturally restricts to tracked pitches
within whatever level is being processed, which for AA/High-A yields ~0
pitchers (correctly surfacing "not identifiable here, no tracked pitches
exist") rather than being silently skipped.

Output: reports/phase1b/RELIABILITY_STATS.json

Usage: python reliability_analysis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import METRICS, pitcher_values  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import LEVELS, DATA_CACHE, REPORTS_DIR  # noqa: E402

MIN_PITCHES_RATE = 20
MIN_PITCHES_MEAN = 15
STABILIZATION_THRESHOLDS = [20, 50, 100, 200, 400, 800]


def spearman_brown(r_half: float) -> float | None:
    if r_half is None or np.isnan(r_half) or r_half <= -1:
        return None
    return 2 * r_half / (1 + r_half)


def split_half(sub: pd.DataFrame, metric, min_pitches: int) -> dict:
    """Odd/even split by chronological rank within each pitcher, then
    correlate the metric across pitchers between the two halves."""
    sub = sub.sort_values(["game_date", "gamePk"], kind="stable").copy()
    sub["rank"] = sub.groupby("pitcher_id").cumcount()
    half1 = sub[sub["rank"] % 2 == 0]
    half2 = sub[sub["rank"] % 2 == 1]

    def agg(half_df):
        if metric.kind == "rate":
            return metric.numerator(half_df).groupby(half_df["pitcher_id"]).agg(["mean", "size"])
        return half_df.groupby("pitcher_id")[metric.value_col].agg(["mean", "size"])

    a1, a2 = agg(half1), agg(half2)
    a1.columns = ["v1", "n1"]
    a2.columns = ["v2", "n2"]
    joined = a1.join(a2, how="inner")
    joined = joined[(joined["n1"] >= min_pitches / 2) & (joined["n2"] >= min_pitches / 2)]

    if len(joined) < 8:
        return {"status": "insufficient_pitchers", "n_pitchers": len(joined)}

    r_half = joined["v1"].corr(joined["v2"])
    return {
        "r_half": None if pd.isna(r_half) else round(float(r_half), 4),
        "r_full_spearman_brown": (
            None if pd.isna(r_half) else round(float(spearman_brown(r_half) or float("nan")), 4)
        ),
        "n_pitchers": int(len(joined)),
    }


def month_to_month(sub: pd.DataFrame, metric, min_pitches: int) -> dict:
    early = sub[sub["season_third"] == "early"]
    late = sub[sub["season_third"] == "late"]

    def agg(half_df):
        if metric.kind == "rate":
            return metric.numerator(half_df).groupby(half_df["pitcher_id"]).agg(["mean", "size"])
        return half_df.groupby("pitcher_id")[metric.value_col].agg(["mean", "size"])

    a1, a2 = agg(early), agg(late)
    a1.columns = ["v1", "n1"]
    a2.columns = ["v2", "n2"]
    joined = a1.join(a2, how="inner")
    joined = joined[(joined["n1"] >= min_pitches) & (joined["n2"] >= min_pitches)]

    if len(joined) < 8:
        return {"status": "insufficient_pitchers", "n_pitchers": len(joined)}

    r = joined["v1"].corr(joined["v2"])
    return {
        "r": None if pd.isna(r) else round(float(r), 4),
        "n_pitchers": int(len(joined)),
    }


def stabilization_curve(sub: pd.DataFrame, metric, min_pitches: int) -> list[dict]:
    curve = []
    totals = pitcher_values(sub, metric)
    for threshold in STABILIZATION_THRESHOLDS:
        eligible_pitchers = totals[totals["n"] >= threshold].index
        restricted = sub[sub["pitcher_id"].isin(eligible_pitchers)]
        if len(eligible_pitchers) < 8:
            curve.append({"min_n": threshold, "status": "insufficient_pitchers", "n_pitchers": int(len(eligible_pitchers))})
            continue
        result = split_half(restricted, metric, min_pitches)
        result["min_n"] = threshold
        curve.append(result)
    return curve


def main() -> None:
    df = pd.read_parquet(DATA_CACHE / "derived" / "pitch_dataset.parquet")
    df = df.dropna(subset=["pitcher_id", "game_date"])

    results = {}
    for level in LEVELS:
        level_df = df[df["level"] == level]
        results[level] = {}
        for metric in METRICS:
            sub_mask = metric.denominator_filter(level_df)
            sub = level_df[sub_mask]
            min_pitches = MIN_PITCHES_RATE if metric.kind == "rate" else MIN_PITCHES_MEAN

            results[level][metric.name] = {
                "scope": metric.scope,
                "description": metric.description,
                "n_qualifying_pitches": int(len(sub)),
                "split_half": split_half(sub, metric, min_pitches),
                "month_to_month_early_vs_late": month_to_month(sub, metric, min_pitches),
                "stabilization_curve": stabilization_curve(sub, metric, min_pitches),
            }
        print(f"{level}: done")

    out_path = REPORTS_DIR / "phase1b" / "RELIABILITY_STATS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
