# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Build the unified statline spine and transition pairs.

Spine: player-season-level official statlines from
  - deep history (projection_engine): MLB 2000-2026, AAA/AA 2008-2026
  - fresh API pulls: all six levels 2021-2026
Transitions: for every player-season-level, the same player's next-season
line at each level (incl. same level), plus AAA->MLB pairs defined as the
first MLB season with >=100 PA within two years of the AAA season.

Everything here is statline-only (no pitch data) so it is leak-free with
respect to the swing-decision features and available for deep history.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, DATA_RAW, SPORT_LEVELS, log_run

PE_DATA = Path.home() / "projection_engine" / "data"


def load_spine() -> pd.DataFrame:
    cols = ["player_id", "season", "level", "pa", "bb", "so", "hbp", "age", "k_pct", "bb_pct"]

    deep_mlb = pd.read_parquet(PE_DATA / "deep_mlb.parquet")
    deep_mlb["level"] = "MLB"
    deep_minors = pd.read_parquet(PE_DATA / "deep_minors.parquet")
    deep_minors["level"] = deep_minors.sport.map(SPORT_LEVELS)
    deep = pd.concat([deep_mlb, deep_minors], ignore_index=True)
    deep = deep.rename(columns={"batter": "player_id"})
    deep = deep[["player_id", "season", "level", "pa", "bb", "so", "hbp", "age", "k_pct", "bb_pct"]]
    deep["source"] = "deep_history"

    fresh = pd.read_parquet(DATA_RAW / "official_statlines" / "official_player_season_level.parquet")
    bd = pd.read_csv(Path.home() / "chadwick_birthdays.csv").dropna(subset=["key_mlbam", "birth_year"])
    bd["player_id"] = bd.key_mlbam.astype("int64")
    bd = bd.drop_duplicates("player_id")
    fresh = fresh.merge(bd[["player_id", "birth_year", "birth_month", "birth_day"]],
                        on="player_id", how="left")
    after = (fresh.birth_month > 6) | ((fresh.birth_month == 6) & (fresh.birth_day > 30))
    fresh["age"] = fresh.season - fresh.birth_year - after.fillna(False).astype(int)
    fresh = fresh[["player_id", "season", "level", "pa", "bb", "so", "hbp", "age", "k_pct", "bb_pct"]]
    fresh["source"] = "api_2021_2026"

    # prefer fresh rows where both exist (identical values verified earlier)
    spine = pd.concat([fresh, deep], ignore_index=True)
    spine = spine.drop_duplicates(subset=["player_id", "season", "level"], keep="first")
    spine = spine[spine.pa.notna() & (spine.pa > 0)].reset_index(drop=True)
    return spine


def build_next_season_pairs(spine: pd.DataFrame) -> pd.DataFrame:
    nxt = spine.copy()
    nxt["season"] = nxt.season - 1  # align next-season rows onto current season key
    pairs = spine.merge(
        nxt[["player_id", "season", "level", "pa", "k_pct", "bb_pct", "age"]],
        on=["player_id", "season"], how="inner", suffixes=("", "_next"))
    pairs = pairs.rename(columns={"level_next": "next_level", "pa_next": "next_pa",
                                  "k_pct_next": "next_k_pct", "bb_pct_next": "next_bb_pct"})
    return pairs


def build_milb_to_mlb_pairs(spine: pd.DataFrame, from_level: str) -> pd.DataFrame:
    src = spine[spine.level == from_level].copy()
    mlb = spine[(spine.level == "MLB") & (spine.pa >= 100)].copy()
    rows = []
    mlb_by_player = {pid: g.sort_values("season") for pid, g in mlb.groupby("player_id")}
    for r in src.itertuples(index=False):
        g = mlb_by_player.get(r.player_id)
        if g is None:
            continue
        fut = g[(g.season > r.season) & (g.season <= r.season + 2)]
        if len(fut) == 0:
            continue
        f = fut.iloc[0]
        rows.append({
            "player_id": r.player_id, "season": r.season, "level": from_level,
            "pa": r.pa, "k_pct": r.k_pct, "bb_pct": r.bb_pct, "age": r.age,
            "mlb_season": f.season, "mlb_pa": f.pa,
            "mlb_k_pct": f.k_pct, "mlb_bb_pct": f.bb_pct,
        })
    return pd.DataFrame(rows)


def main() -> None:
    spine = load_spine()
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    spine.to_parquet(DATA_PROCESSED / "statline_spine.parquet", index=False)
    print("spine rows:", len(spine))
    print(spine.groupby("level").agg(rows=("pa", "size"), first=("season", "min"),
                                     last=("season", "max")).to_string())

    pairs = build_next_season_pairs(spine)
    pairs.to_parquet(DATA_PROCESSED / "next_season_pairs.parquet", index=False)
    print("\nnext-season pairs:", len(pairs))

    frames = []
    for lv in ["AAA", "AA", "A+", "A", "CPX"]:
        p = build_milb_to_mlb_pairs(spine, lv)
        if len(p):
            frames.append(p)
        print(f"{lv} -> MLB pairs: {len(p)}")
    milb_mlb = pd.concat(frames, ignore_index=True)
    milb_mlb.to_parquet(DATA_PROCESSED / "milb_to_mlb_pairs.parquet", index=False)
    log_run("transitions_v1", spine=len(spine), next_pairs=len(pairs),
            mlb_pairs=len(milb_mlb))


if __name__ == "__main__":
    main()
