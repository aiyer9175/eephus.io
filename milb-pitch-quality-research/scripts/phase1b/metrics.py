"""Shared candidate-metric definitions for Phase 1B's reliability and
variance-decomposition scripts, so both compute the exact same quantities.

Two families:

- "rate" metrics: numerator boolean column, evaluated within a denominator
  filter (e.g. whiff_rate = is_whiff among is_swing pitches).
- "mean" metrics: a continuous column's mean, evaluated within a filter
  (e.g. avg_start_speed among tracked pitches).

`scope` marks whether a metric is computable at every level (ALL_LEVELS,
built only from outcome/count fields present regardless of tracking) or only
where Trackman/Hawkeye data exists (TRACKED_ONLY) -- this is the load-bearing
boundary found before Phase 1B was scoped: pitch type itself is unavailable
at untracked venues, so nothing pitch-type-specific can ever be ALL_LEVELS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

ZONE_STRIKE = {1, 2, 3, 4, 5, 6, 7, 8, 9}
ZONE_CHASE = {11, 12, 13, 14}


@dataclass
class MetricSpec:
    name: str
    kind: str  # "rate" or "mean"
    scope: str  # "ALL_LEVELS" or "TRACKED_ONLY"
    numerator: Callable[[pd.DataFrame], pd.Series]
    denominator_filter: Callable[[pd.DataFrame], pd.Series]
    value_col: str | None = None  # for "mean" metrics
    description: str = ""


METRICS: list[MetricSpec] = [
    MetricSpec(
        name="whiff_rate",
        kind="rate",
        scope="ALL_LEVELS",
        numerator=lambda df: df["is_whiff"],
        denominator_filter=lambda df: df["is_swing"],
        description="Whiffs per swing -- outcome-only, no tracking required.",
    ),
    MetricSpec(
        name="called_strike_rate",
        kind="rate",
        scope="ALL_LEVELS",
        numerator=lambda df: df["is_called_strike"],
        denominator_filter=lambda df: ~df["is_swing"],
        description="Called strikes per taken pitch -- outcome-only.",
    ),
    MetricSpec(
        name="swing_rate",
        kind="rate",
        scope="ALL_LEVELS",
        numerator=lambda df: df["is_swing"],
        denominator_filter=lambda df: pd.Series(True, index=df.index),
        description="Swings per pitch thrown -- outcome-only.",
    ),
    MetricSpec(
        name="in_play_rate",
        kind="rate",
        scope="ALL_LEVELS",
        numerator=lambda df: df["is_in_play"],
        denominator_filter=lambda df: pd.Series(True, index=df.index),
        description="Balls in play per pitch thrown -- outcome-only.",
    ),
    MetricSpec(
        name="foul_rate",
        kind="rate",
        scope="ALL_LEVELS",
        numerator=lambda df: df["is_foul"],
        denominator_filter=lambda df: df["is_swing"],
        description="Fouls per swing -- outcome-only.",
    ),
    MetricSpec(
        name="avg_start_speed",
        kind="mean",
        scope="TRACKED_ONLY",
        numerator=lambda df: df["start_speed"],
        denominator_filter=lambda df: df["tracked"],
        value_col="start_speed",
        description="Mean pitch velocity -- requires tracking.",
    ),
    MetricSpec(
        name="avg_spin_rate",
        kind="mean",
        scope="TRACKED_ONLY",
        numerator=lambda df: df["spin_rate"],
        denominator_filter=lambda df: df["tracked"] & df["spin_rate"].notna(),
        value_col="spin_rate",
        description="Mean spin rate -- requires tracking; noted in Phase 1A as less reliable than velocity even at tracked venues.",
    ),
    MetricSpec(
        name="avg_pfx_x",
        kind="mean",
        scope="TRACKED_ONLY",
        numerator=lambda df: df["pfx_x"],
        denominator_filter=lambda df: df["tracked"] & df["pfx_x"].notna(),
        value_col="pfx_x",
        description="Mean horizontal movement -- requires tracking.",
    ),
    MetricSpec(
        name="avg_pfx_z",
        kind="mean",
        scope="TRACKED_ONLY",
        numerator=lambda df: df["pfx_z"],
        denominator_filter=lambda df: df["tracked"] & df["pfx_z"].notna(),
        value_col="pfx_z",
        description="Mean vertical movement (induced) -- requires tracking.",
    ),
    MetricSpec(
        name="zone_rate",
        kind="rate",
        scope="TRACKED_ONLY",
        numerator=lambda df: df["zone"].isin(ZONE_STRIKE),
        denominator_filter=lambda df: df["tracked"] & df["zone"].notna(),
        description="Share of pitches located in the strike zone -- a location/command proxy; requires tracking (zone is a Trackman-derived field).",
    ),
    MetricSpec(
        name="chase_rate",
        kind="rate",
        scope="TRACKED_ONLY",
        numerator=lambda df: df["is_swing"],
        denominator_filter=lambda df: df["tracked"] & df["zone"].isin(ZONE_CHASE),
        description="Swings on pitches outside the zone -- requires tracking to know zone.",
    ),
]

METRICS_BY_NAME = {m.name: m for m in METRICS}


def pitcher_values(df: pd.DataFrame, metric: MetricSpec) -> pd.DataFrame:
    """Return a DataFrame indexed by pitcher_id with columns [value, n]."""
    mask = metric.denominator_filter(df)
    sub = df[mask]
    if metric.kind == "rate":
        num = metric.numerator(sub)
        grouped = num.groupby(sub["pitcher_id"]).agg(["mean", "size"])
    else:
        grouped = sub.groupby("pitcher_id")[metric.value_col].agg(["mean", "size"])
    grouped.columns = ["value", "n"]
    return grouped
