"""Phase 1C, step 1: extend Phase 1B's flat pitch dataset with `hitData`
fields (launch speed, launch angle, trajectory, hardness) -- the one field
group Phase 1A confirmed present at tracked venues but Phase 1B explicitly
flagged as "not computed this phase" (FEATURE_FEASIBILITY_MATRIX.md).

No new API pull: parses the SAME cached games Phase 1B already pulled
(data_cache/{level}/{gamePk}.json), consistent with the charter's own
instruction to build on Phase 1A/1B evidence rather than repeat data-audit
work. Writes a new derived file rather than overwriting Phase 1B's, so that
report's numbers stay reproducible from the artifact it was written against.

Output: data_cache/derived/pitch_dataset_v2.parquet

Usage: python build_pitch_dataset_v2.py
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
HARD_HIT_THRESHOLD_MPH = 95.0  # standard Statcast hard-hit-ball definition


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
            hit_data = e.get("hitData") or {}

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
                    # New in Phase 1C: hitData fields (batted-ball only; null on
                    # every non-batted-ball pitch, not just untracked venues).
                    "has_hit_data": bool(hit_data),
                    "launch_speed": hit_data.get("launchSpeed"),
                    "launch_angle": hit_data.get("launchAngle"),
                    "total_distance": hit_data.get("totalDistance"),
                    "trajectory": hit_data.get("trajectory"),
                    "hardness": hit_data.get("hardness"),
                    "is_ground_ball": hit_data.get("trajectory") == "ground_ball",
                    "is_hard_hit": (
                        hit_data.get("launchSpeed") is not None
                        and hit_data.get("launchSpeed") >= HARD_HIT_THRESHOLD_MPH
                    ),
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
    out_path = out_dir / "pitch_dataset_v2.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df):,} pitches, {df['pitcher_id'].nunique():,} distinct pitchers -> {out_path}")

    print("\nPer-level summary (including new hitData coverage):")
    summary = df.groupby("level").agg(
        n_pitches=("pitcher_id", "size"),
        n_pitchers=("pitcher_id", "nunique"),
        tracked_share=("tracked", "mean"),
        n_batted_balls=("has_hit_data", "sum"),
        hit_data_launch_speed_coverage=("launch_speed", lambda s: s.notna().mean()),
    )
    print(summary)


if __name__ == "__main__":
    main()
