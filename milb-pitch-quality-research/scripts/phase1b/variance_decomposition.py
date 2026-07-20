"""Phase 1B, step 4: method-of-moments variance-component decomposition.

Standard unbalanced one-way random-effects ANOVA estimator (Searle et al.):
given groups i=1..k with n_i observations, N=sum(n_i):
  SSB = sum_i n_i*(mean_i - grand_mean)^2 ;  MSB = SSB/(k-1)
  SSW = sum_i sum_j (y_ij - mean_i)^2      ;  MSW = SSW/(N-k)
  n0  = (N - sum(n_i^2)/N) / (k-1)
  var_within  = MSW
  var_between = max(0, (MSB - MSW) / n0)
  ICC = var_between / (var_between + var_within)

No statsmodels dependency (not installed in this environment) -- this is
plain numpy/pandas, and it's the same math underlying classical reliability
theory, so it's directly comparable to reliability_analysis.py's numbers.
This is a method-of-moments point estimate, not a full mixed-effects model
with confidence intervals -- adequate for "where does variance live," not
precision estimation (per the charter's own framing of this deliverable).

Output: reports/phase1b/VARIANCE_STATS.json

Usage: python variance_decomposition.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import METRICS  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import LEVELS, DATA_CACHE, REPORTS_DIR  # noqa: E402

MIN_GROUPS = 8
MIN_OBS_PER_GROUP = 5

PITCH_FAMILY = {
    "FF": "fastball", "SI": "fastball", "FT": "fastball", "FC": "fastball",
    "SL": "breaking", "CU": "breaking", "KC": "breaking", "ST": "breaking",
    "SV": "breaking", "CS": "breaking", "SC": "breaking",
    "CH": "offspeed", "FS": "offspeed", "FO": "offspeed", "KN": "offspeed",
}


def one_way_variance(df: pd.DataFrame, group_col: str, value_col: str) -> dict:
    sub = df[[group_col, value_col]].dropna()
    counts = sub.groupby(group_col).size()
    valid_groups = counts[counts >= MIN_OBS_PER_GROUP].index
    sub = sub[sub[group_col].isin(valid_groups)]

    k = sub[group_col].nunique()
    n_total = len(sub)
    if k < MIN_GROUPS or n_total < MIN_GROUPS * MIN_OBS_PER_GROUP:
        return {"status": "insufficient_data", "k_groups": int(k), "n_obs": int(n_total)}

    grand_mean = sub[value_col].mean()
    group_stats = sub.groupby(group_col)[value_col].agg(["mean", "size"])

    ssb = (group_stats["size"] * (group_stats["mean"] - grand_mean) ** 2).sum()
    msb = ssb / (k - 1)

    merged = sub.join(group_stats["mean"].rename("group_mean"), on=group_col)
    ssw = ((merged[value_col] - merged["group_mean"]) ** 2).sum()
    dof_w = n_total - k
    if dof_w <= 0:
        return {"status": "insufficient_data", "k_groups": int(k), "n_obs": int(n_total)}
    msw = ssw / dof_w

    n0 = (n_total - (group_stats["size"] ** 2).sum() / n_total) / (k - 1)
    var_within = msw
    var_between = max(0.0, (msb - msw) / n0) if n0 > 0 else 0.0
    denom = var_between + var_within
    icc = (var_between / denom) if denom > 0 else None

    return {
        "k_groups": int(k),
        "n_obs": int(n_total),
        "var_between": round(float(var_between), 6),
        "var_within_residual": round(float(var_within), 6),
        "icc_share_between": None if icc is None else round(float(icc), 4),
    }


def add_metric_value_column(df: pd.DataFrame, metric) -> pd.DataFrame:
    """Return a copy with a single float column '_value' = the metric's
    per-pitch contribution (1/0 for rate metrics, the raw value for mean
    metrics), already restricted to the metric's denominator filter."""
    mask = metric.denominator_filter(df)
    sub = df[mask].copy()
    if metric.kind == "rate":
        sub["_value"] = metric.numerator(sub).astype(float)
    else:
        sub["_value"] = sub[metric.value_col].astype(float)
    return sub


def nested_pitcher_family_decomposition(df: pd.DataFrame, metric) -> dict:
    """Nested Pitcher > Pitch-family > residual decomposition for
    TRACKED_ONLY metrics where pitch_type_code is available.

    Same method-of-moments logic as one_way_variance, applied one level
    deeper: cells = (pitcher, family) combinations, nested within pitcher.
      MSW_residual = pooled within-cell (pitch-to-pitch) mean square
      MSB_cells    = between-cell mean square, deviations taken from each
                     pitcher's OWN mean (not the grand mean), df = k_cells - k_pitchers
      var_family_within_pitcher = max(0, (MSB_cells - MSW_residual) / n0)
    n0 uses the simple average-cell-size approximation (N_total / k_cells)
    rather than the exact unbalanced-nested formula -- adequate for "where
    does variance live," not a precision estimate (see module docstring).
    """
    sub = add_metric_value_column(df, metric)
    sub = sub.dropna(subset=["pitch_type_code"])
    sub["family"] = sub["pitch_type_code"].map(PITCH_FAMILY).fillna("other")

    cell_stats = sub.groupby(["pitcher_id", "family"])["_value"].agg(["mean", "size"])
    cell_stats = cell_stats[cell_stats["size"] >= MIN_OBS_PER_GROUP]
    valid_cells = cell_stats.index
    sub = sub[sub.set_index(["pitcher_id", "family"]).index.isin(valid_cells)]
    cell_stats = cell_stats.reset_index()

    k_pitchers = cell_stats["pitcher_id"].nunique()
    k_cells = len(cell_stats)
    n_total = len(sub)
    if k_pitchers < MIN_GROUPS or k_cells <= k_pitchers:
        return {"status": "insufficient_data", "k_pitchers": int(k_pitchers), "k_cells": int(k_cells)}

    pitcher_means = sub.groupby("pitcher_id")["_value"].mean()
    cell_stats = cell_stats.merge(pitcher_means.rename("pitcher_mean"), on="pitcher_id")

    # within-cell residual (pitch-to-pitch, pooled across all cells)
    merged = sub.merge(
        cell_stats[["pitcher_id", "family", "mean"]].rename(columns={"mean": "cell_mean"}),
        on=["pitcher_id", "family"],
    )
    ssw_residual = ((merged["_value"] - merged["cell_mean"]) ** 2).sum()
    dof_w = n_total - k_cells
    if dof_w <= 0:
        return {"status": "insufficient_data", "k_pitchers": int(k_pitchers), "k_cells": int(k_cells)}
    msw_residual = ssw_residual / dof_w

    # between-cell (family-within-pitcher), deviations from each pitcher's own mean
    ssb_cells = (cell_stats["size"] * (cell_stats["mean"] - cell_stats["pitcher_mean"]) ** 2).sum()
    msb_cells = ssb_cells / (k_cells - k_pitchers)

    n0_approx = n_total / k_cells  # simple average-cell-size approximation, see docstring
    var_family_within_pitcher = max(0.0, (msb_cells - msw_residual) / n0_approx) if n0_approx > 0 else 0.0

    pitcher_level = one_way_variance(sub.assign(_pid=sub["pitcher_id"]), "_pid", "_value")

    return {
        "between_pitcher": pitcher_level,
        "family_within_pitcher_var": round(float(var_family_within_pitcher), 6),
        "residual_within_cell_var": round(float(msw_residual), 6),
        "n_pitcher_family_cells": int(k_cells),
        "families_observed": sorted(cell_stats["family"].unique().tolist()),
    }


def main() -> None:
    df = pd.read_parquet(DATA_CACHE / "derived" / "pitch_dataset.parquet")
    df = df.dropna(subset=["pitcher_id", "venue_id"])

    results = {"by_pitcher": {}, "by_venue": {}, "nested_pitcher_family": {}}

    for level in LEVELS:
        level_df = df[df["level"] == level]
        results["by_pitcher"][level] = {}
        results["by_venue"][level] = {}
        results["nested_pitcher_family"][level] = {}

        for metric in METRICS:
            sub = add_metric_value_column(level_df, metric)

            results["by_pitcher"][level][metric.name] = {
                "scope": metric.scope,
                **one_way_variance(sub.assign(_pid=sub["pitcher_id"]), "_pid", "_value"),
            }
            results["by_venue"][level][metric.name] = {
                "scope": metric.scope,
                **one_way_variance(sub.assign(_vid=sub["venue_id"]), "_vid", "_value"),
            }
            if metric.scope == "TRACKED_ONLY":
                results["nested_pitcher_family"][level][metric.name] = nested_pitcher_family_decomposition(
                    level_df, metric
                )
        print(f"{level}: done")

    out_path = REPORTS_DIR / "phase1b" / "VARIANCE_STATS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
