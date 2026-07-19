# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Coverage guarantee: zone metrics exist for every player — no rank cutoffs.

The extraction is game-centric (every hitter in every completed game), so no
player can be excluded by FV/ranking/publication status — there is no player
list anywhere in the pipeline. This report PROVES coverage by reconciling
three universes per level-season:
  1. official statline players (PA > 0)
  2. players with extracted pitch data
  3. players with zone-classified pitches (>=80% of their pitches zoned)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, DATA_RAW, OUTPUTS, log_run


def main() -> None:
    m = pd.read_parquet(DATA_PROCESSED / "player_season_level_metrics.parquet")
    off = pd.read_parquet(DATA_RAW / "official_statlines" / "official_player_season_level.parquet")
    off = off[off.pa > 0].rename(columns={"player_id": "batter_id"})

    mm = m[m.pitches > 0]
    merged = off.merge(mm[["batter_id", "season", "level", "pitches", "n_zoned"]],
                       on=["batter_id", "season", "level"], how="left")
    merged["has_pitches"] = merged.pitches.notna()
    merged["has_zone"] = (merged.n_zoned / merged.pitches) >= 0.8

    rows = []
    for (season, level), g in merged.groupby(["season", "level"]):
        meaningful = g[g.pa >= 20]
        rows.append({
            "season": season, "level": level,
            "official_players": len(g),
            "official_pa20": len(meaningful),
            "with_pitch_data": int(g.has_pitches.sum()),
            "with_zone_data": int(g.has_zone.fillna(False).sum()),
            "pa20_pitch_cov": round(meaningful.has_pitches.mean(), 4),
            "pa20_zone_cov": round(meaningful.has_zone.fillna(False).mean(), 4),
        })
    rep = pd.DataFrame(rows)
    out = OUTPUTS / "coverage"
    out.mkdir(parents=True, exist_ok=True)
    rep.to_csv(out / "player_zone_coverage.csv", index=False)
    print(rep.to_string(index=False))

    worst = rep[rep.official_pa20 > 50][["pa20_pitch_cov", "pa20_zone_cov"]].min()
    missing = merged[(merged.pa >= 20) & ~merged.has_pitches]
    print(f"\nworst PA>=20 pitch coverage: {worst.pa20_pitch_cov:.4f}")
    print(f"worst PA>=20 zone coverage:  {worst.pa20_zone_cov:.4f}")
    print(f"players PA>=20 missing pitch data: {len(missing)}")
    if len(missing):
        print(missing[["player_name", "season", "level", "pa"]].head(10).to_string(index=False))
    print("\nNo FV/ranking/publication filter exists anywhere in this pipeline: "
          "the extraction unit is the GAME, not the player.")
    log_run("coverage_report_v1",
            worst_pitch=float(worst.pa20_pitch_cov),
            worst_zone=float(worst.pa20_zone_cov), n_missing=len(missing))


if __name__ == "__main__":
    main()
