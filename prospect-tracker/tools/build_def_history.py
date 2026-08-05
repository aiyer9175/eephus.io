# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Build data/mlb_def_history.json -- per (mlbam, season) DEFENSIVE split from the
SAME Baseball-Reference WAR daily tables the projection corpus already pulls for total
WAR (fa_projection._war_age_maps). No new data source.

Per season we keep the two stable defensive reads the projection model can use as a
forward prior, plus the exposure needed to reliability-shrink them:

  war_def        WAR_def -- defensive wins (fielding + positional adjustment), the
                 complete single-season defensive-value read.
  runs_position  the POSITIONAL ADJUSTMENT in runs -- "where the player is trusted to
                 play". This is the report's thesis ("it's position, not fielding
                 stats"): position is the org's revealed, persistent defensive
                 assessment; raw fielding rates are noisy. Kept separately so the
                 model can lean on the stable part.
  pa             plate appearances -- the exposure for shrinkage.

A player-season with multiple stints (trades) is summed (runs are counting stats; PA
sums; WAR_def sums). Leakage is the caller's job: build_features only ever reads
seasons <= base-1, exactly like the existing war_l1/l2/l3 lags from the same source.

Run: python tools/build_def_history.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "mlb_def_history.json"
FIRST_SEASON = 2000   # matches the corpus floor; trims the historical tail we never score


def _f(v, default=0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def build() -> dict:
    # The run-value decomposition read (WAR_def / runs_position) rides the
    # batting stint frame, via the war_source facade (provider 'bwar').
    import war_source
    df = war_source.run_value_frame("bat")
    # position players only: pitcher==N (the 'pitcher' column flags two-way/pitcher bats)
    cols = {"mlb_ID", "year_ID", "PA", "WAR_def", "runs_position", "pitcher"}
    missing = cols - set(df.columns)
    if missing:
        raise SystemExit(f"bwar_bat missing columns {missing}")
    agg: dict[tuple[int, int], dict[str, float]] = defaultdict(
        lambda: {"war_def": 0.0, "runs_position": 0.0, "pa": 0.0})
    for row in df.itertuples(index=False):
        try:
            mid = int(row.mlb_ID)
            yr = int(row.year_ID)
        except (TypeError, ValueError):
            continue
        if yr < FIRST_SEASON:
            continue
        if str(getattr(row, "pitcher", "N")).upper() == "Y":
            continue
        a = agg[(mid, yr)]
        a["war_def"] += _f(row.WAR_def)
        a["runs_position"] += _f(row.runs_position)
        a["pa"] += _f(row.PA)
    # key as "mlbam:season"; round to keep the sidecar small
    out = {}
    for (mid, yr), a in agg.items():
        if a["pa"] <= 0:
            continue
        out[f"{mid}:{yr}"] = {
            "war_def": round(a["war_def"], 3),
            "runs_position": round(a["runs_position"], 2),
            "pa": int(round(a["pa"])),
        }
    return out


def main() -> None:
    out = build()
    payload = {
        "generated_from": "pybaseball bwar_bat (Baseball-Reference war_daily_bat)",
        "first_season": FIRST_SEASON,
        "fields": ["war_def", "runs_position", "pa"],
        "count": len(out),
        "rows": out,
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    seasons = sorted({int(k.split(":")[1]) for k in out})
    print(f"wrote {OUT} -- {len(out)} player-seasons, {seasons[0]}-{seasons[-1]}")


if __name__ == "__main__":
    main()
