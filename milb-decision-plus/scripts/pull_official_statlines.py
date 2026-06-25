# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Pull official season hitting statlines per level-season from the MLB Stats API.

These are the ground-truth lines the reconstructed pitch/PA data must match
(validation gate) and the historical-rate inputs for baseline models.
Multi-team players: the API returns one split per team stint plus, when a
player changed teams, a combined split without a `team` key. We keep stint
rows and aggregate ourselves so org/team metadata survives, then dedupe.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import API_BASE, DATA_RAW, SPORT_LEVELS, get_json, log_run, make_session

STAT_FIELDS = {
    "gamesPlayed": "g",
    "plateAppearances": "pa",
    "atBats": "ab",
    "baseOnBalls": "bb",
    "intentionalWalks": "ibb",
    "strikeOuts": "so",
    "hitByPitch": "hbp",
    "hits": "h",
    "doubles": "doubles",
    "triples": "triples",
    "homeRuns": "hr",
    "sacFlies": "sf",
    "sacBunts": "sh",
}


def pull_level_season(session, sport_id: int, season: int) -> pd.DataFrame:
    rows = []
    offset = 0
    total = None
    while total is None or offset < total:
        data = get_json(session, f"{API_BASE}/stats", params={
            "stats": "season", "group": "hitting", "sportId": sport_id,
            "season": season, "playerPool": "ALL", "limit": 1000, "offset": offset,
        }, timeout=60)
        stats = data.get("stats", [])
        if not stats:
            break
        block = stats[0]
        total = block.get("totalSplits", 0)
        splits = block.get("splits", [])
        if not splits:
            break
        for sp in splits:
            stat = sp.get("stat", {})
            row = {
                "player_id": sp.get("player", {}).get("id"),
                "player_name": sp.get("player", {}).get("fullName"),
                "season": season,
                "sport_id": sport_id,
                "level": SPORT_LEVELS[sport_id],
                "team_id": sp.get("team", {}).get("id"),
                "team": sp.get("team", {}).get("name"),
                "league": sp.get("league", {}).get("name"),
                "position": sp.get("position", {}).get("abbreviation"),
                "num_teams": sp.get("numTeams"),
                "is_combined": "team" not in sp,
            }
            for api_key, col in STAT_FIELDS.items():
                row[col] = stat.get(api_key)
            rows.append(row)
        offset += len(splits)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", default=[2021, 2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--sports", type=int, nargs="+", default=[1, 11, 12, 13, 14, 16])
    args = ap.parse_args()

    session = make_session()
    out_dir = DATA_RAW / "official_statlines"
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for season in args.seasons:
        for sport_id in args.sports:
            df = pull_level_season(session, sport_id, season)
            print(f"{season} {SPORT_LEVELS[sport_id]:>4}: {len(df)} splits", flush=True)
            if not df.empty:
                frames.append(df)

    raw = pd.concat(frames, ignore_index=True)
    raw.to_parquet(out_dir / "statline_splits_raw.parquet", index=False)

    # Aggregate to player-season-level (sum team stints; combined rows only
    # exist alongside stints, so drop them to avoid double counting).
    stints = raw[~raw.is_combined].copy()
    num_cols = list(STAT_FIELDS.values())
    agg = (stints.groupby(["player_id", "season", "sport_id", "level"], as_index=False)
           .agg({**{c: "sum" for c in num_cols},
                 "player_name": "first", "position": "first",
                 "team": lambda s: "/".join(sorted(set(str(x) for x in s if pd.notna(x)))),
                 "league": "first"}))
    agg["k_pct"] = agg.so / agg.pa.where(agg.pa > 0)
    agg["bb_pct"] = agg.bb / agg.pa.where(agg.pa > 0)
    agg.to_parquet(out_dir / "official_player_season_level.parquet", index=False)
    print(f"\nraw splits: {len(raw)}  player-season-level rows: {len(agg)}")
    log_run("official_statlines_v1", seasons=args.seasons, sports=args.sports,
            n_raw=len(raw), n_agg=len(agg))


if __name__ == "__main__":
    main()
