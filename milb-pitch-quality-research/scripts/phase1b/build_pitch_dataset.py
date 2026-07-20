"""Phase 1B, step 2: flatten every cached game (Phase 1A's venue-coverage
sample + Phase 1B's team/venue-stratified sample -- same data_cache/{level}/
{gamePk}.json cache, deduped automatically since gamePk is the cache key)
into a single pitch-grain table for reliability/variance-decomposition work.

Output: data_cache/derived/pitch_dataset.parquet (gitignored -- internal
working artifact, not committed; the whole data_cache/ tree is excluded
regardless of extension, so parquet is fine here even though it's globally
gitignored repo-wide for committed files).

Usage: python build_pitch_dataset.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import LEVELS, DATA_CACHE, load_json  # noqa: E402

WHIFF_DESCRIPTIONS = {"Swinging Strike", "Swinging Strike (Blocked)", "Missed Bunt"}
FOUL_DESCRIPTIONS = {"Foul", "Foul Tip", "Foul Bunt"}
CALLED_STRIKE_DESCRIPTIONS = {"Called Strike"}


def season_third(d: date) -> str:
    if d.month <= 5:
        return "early"
    if d.month <= 7:
        return "mid"
    return "late"


def rows_for_game(level: str, feed: dict) -> list[dict]:
    game_data = feed.get("gameData", {}) or {}
    venue = game_data.get("venue", {}) or {}
    venue_id = venue.get("id")
    game_pk = (game_data.get("game", {}) or {}).get("pk")
    official_date_str = (game_data.get("datetime", {}) or {}).get("officialDate")
    try:
        game_date = date.fromisoformat(official_date_str) if official_date_str else None
    except ValueError:
        game_date = None

    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    rows = []
    for p in plays:
        matchup = p.get("matchup", {}) or {}
        pitcher = matchup.get("pitcher", {}) or {}
        batter = matchup.get("batter", {}) or {}
        pitcher_hand = (matchup.get("pitchHand", {}) or {}).get("code")
        batter_hand = (matchup.get("batSide", {}) or {}).get("code")

        for e in p.get("playEvents", []):
            if not e.get("isPitch"):
                continue
            details = e.get("details", {}) or {}
            pdata = e.get("pitchData", {}) or {}
            coords = pdata.get("coordinates", {}) or {}
            breaks = pdata.get("breaks", {}) or {}
            count = e.get("count", {}) or {}
            description = details.get("description")

            rows.append(
                {
                    "level": level,
                    "gamePk": game_pk,
                    "venue_id": venue_id,
                    "game_date": game_date,
                    "season_third": season_third(game_date) if game_date else None,
                    "pitcher_id": pitcher.get("id"),
                    "batter_id": batter.get("id"),
                    "pitcher_hand": pitcher_hand,
                    "batter_hand": batter_hand,
                    "pitch_type_code": (details.get("type", {}) or {}).get("code"),
                    "call_description": description,
                    "balls_pre": count.get("balls"),
                    "strikes_pre": count.get("strikes"),
                    "is_strike": details.get("isStrike"),
                    "is_ball": details.get("isBall"),
                    "is_in_play": details.get("isInPlay"),
                    "is_whiff": description in WHIFF_DESCRIPTIONS,
                    "is_foul": description in FOUL_DESCRIPTIONS,
                    "is_called_strike": description in CALLED_STRIKE_DESCRIPTIONS,
                    "is_swing": (description in WHIFF_DESCRIPTIONS)
                    or (description in FOUL_DESCRIPTIONS)
                    or bool(details.get("isInPlay")),
                    "tracked": pdata.get("startSpeed") is not None,
                    "start_speed": pdata.get("startSpeed"),
                    "end_speed": pdata.get("endSpeed"),
                    "pfx_x": coords.get("pfxX"),
                    "pfx_z": coords.get("pfxZ"),
                    "spin_rate": breaks.get("spinRate"),
                    "extension": pdata.get("extension"),
                    "plate_x": coords.get("pX"),
                    "plate_z": coords.get("pZ"),
                    "zone": pdata.get("zone"),
                }
            )
    return rows


def main() -> None:
    all_rows: list[dict] = []
    for level in LEVELS:
        level_dir = DATA_CACHE / level
        files = sorted(level_dir.glob("*.json")) if level_dir.exists() else []
        print(f"{level}: parsing {len(files)} cached games...")
        n_before = len(all_rows)
        for fp in files:
            feed = load_json(fp)
            all_rows.extend(rows_for_game(level, feed))
        print(f"  {level}: {len(all_rows) - n_before} pitches")

    df = pd.DataFrame(all_rows)
    out_dir = DATA_CACHE / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pitch_dataset.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df):,} pitches, {df['pitcher_id'].nunique():,} distinct pitchers -> {out_path}")

    print("\nPer-level summary:")
    summary = df.groupby("level").agg(
        n_pitches=("pitcher_id", "size"),
        n_pitchers=("pitcher_id", "nunique"),
        n_games=("gamePk", "nunique"),
        tracked_share=("tracked", "mean"),
    )
    print(summary)


if __name__ == "__main__":
    main()
