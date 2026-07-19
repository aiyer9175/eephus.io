# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Phases 3-5 — meaningful assignments, active development time, raw advancement measures.

build_asof(threshold) returns one row per player x as-of season with:
  meaningful-assignment flags (PA >= threshold at a level-season),
  active professional development time (observed active seasons; 2020 has no
  MiLB rows so it can never count as active time),
  candidate raw measures:
    A  steps_per_season   = (highest meaningful rank - starting rank) / active seasons
    C  highest_rank       = highest meaningful rank reached so far
    D  area_pace          = mean PA-weighted ladder height per active season
    B  arrival gaps       = active seasons between consecutive first meaningful arrivals
                            (diagnostic; summarized in the raw-measure report)

Scoring population guard rails:
  - entry cohorts 2009+ only (2008 entries are left-censored: pre-2008 history unobservable)
  - seasons after the player's MLB debut season are excluded (post-debut MiLB
    rows are rehab/option assignments, not ladder advancement)
"""

from pathlib import Path

import numpy as np
import pandas as pd

from level_map import LEVEL_RANK

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

CANCELLED_MILB_SEASONS = {2020}


def load_inputs():
    hist = pd.read_parquet(DATA / "level_history.parquet")
    idx = pd.read_parquet(DATA / "player_index.parquet")
    return hist, idx


def build_asof(threshold: int, hist: pd.DataFrame = None, idx: pd.DataFrame = None) -> pd.DataFrame:
    if hist is None:
        hist, idx = load_inputs()

    h = hist.copy()
    # drop post-debut seasons (debut season itself retained)
    debut = idx.set_index("player_id").mlb_debut_season
    h["debut_season"] = h.player_id.map(debut)
    h = h[h.debut_season.isna() | (h.season <= h.debut_season)]

    h["meaningful"] = h.pa >= threshold

    # per player x season aggregates
    m = h[h.meaningful]
    per_season = h.groupby(["player_id", "season"], as_index=False).agg(total_pa=("pa", "sum"))
    ms = m.assign(wr=m.pa * m.level_rank).groupby(["player_id", "season"]).agg(
        m_pa=("pa", "sum"), wr=("wr", "sum"), max_rank=("level_rank", "max"),
        n_assign=("level_rank", "size"))
    ms["season_height"] = ms.wr / ms.m_pa
    per_season = per_season.merge(ms.drop(columns="wr"), on=["player_id", "season"], how="left")
    per_season["active"] = per_season.max_rank.notna()

    per_season = per_season.sort_values(["player_id", "season"])
    g = per_season.groupby("player_id")
    per_season["active_seasons"] = g.active.cumsum()
    per_season["highest_rank"] = g.max_rank.cummax()
    # cummax leaves NaN on inactive seasons; carry the running max forward
    per_season["highest_rank"] = per_season.groupby("player_id").highest_rank.ffill()
    per_season["meaningful_assignments"] = g.n_assign.transform(lambda s: s.fillna(0).cumsum())
    per_season["height_sum"] = g.season_height.transform(lambda s: s.fillna(0).cumsum())

    # starting level = max-PA meaningful level in first meaningful season
    fm = m.merge(m.groupby("player_id").season.min().rename("fms"), on="player_id")
    fm = fm[fm.season == fm.fms]
    start = fm.sort_values("pa", ascending=False).groupby("player_id").agg(
        starting_rank=("level_rank", "first"), starting_level=("level", "first"),
        first_meaningful_season=("season", "first"))
    per_season = per_season.merge(start, on="player_id", how="left")

    a = per_season[per_season.active_seasons >= 1].copy()
    a["steps_per_season"] = (a.highest_rank - a.starting_rank) / a.active_seasons  # A
    a["area_pace"] = a.height_sum / a.active_seasons                               # D
    a["meaningful_promotions"] = (a.highest_rank - a.starting_rank).astype(int)

    # attach entry attributes
    cols = ["player_id", "first_pro_season", "entry_age", "entry_pathway",
            "position_group", "name", "mlb_debut_season", "debuted"]
    a = a.merge(idx[cols], on="player_id", how="left")
    a["experience_year"] = a.active_seasons.astype(int)
    a["calendar_years"] = (a.season - a.first_meaningful_season + 1
                           - ((a.first_meaningful_season <= 2020) & (a.season >= 2020)).astype(int))
    a["left_censored"] = a.first_pro_season <= 2008
    a["scoreable"] = ~a.left_censored
    return a


def arrival_gaps(threshold: int, hist: pd.DataFrame = None, idx: pd.DataFrame = None) -> pd.DataFrame:
    """Measure B diagnostic: active seasons elapsed between consecutive first
    meaningful arrivals at successive rungs."""
    a = build_asof(threshold, hist, idx)
    a = a[a.scoreable & a.active]
    firsts = (a.sort_values("season").groupby(["player_id", "highest_rank"], as_index=False)
                .first()[["player_id", "highest_rank", "active_seasons"]])
    firsts = firsts.sort_values(["player_id", "highest_rank"])
    firsts["gap"] = firsts.groupby("player_id").active_seasons.diff()
    firsts["rung_jump"] = firsts.groupby("player_id").highest_rank.diff()
    gaps = firsts.dropna(subset=["gap"])
    gaps = gaps[gaps.rung_jump > 0].copy()
    gaps["gap_per_rung"] = gaps.gap / gaps.rung_jump
    return gaps
