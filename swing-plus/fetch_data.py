# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
fetch_data.py — get the generated data the app needs (it is NOT in git; per repo rules
the ~56 MB of generated leaderboards / trajectories live in external storage).

Two paths for a fresh clone:

  1)  FETCH a prebuilt bundle (fast — recommended for collaborators):
        export SWING_PLUS_DATA_URL="https://.../swing_plus_data.tar.gz"   # Drive/S3/GCS direct link
        python fetch_data.py
      Downloads + extracts into data/processed/.

  2)  REGENERATE from scratch (slow — pulls Statcast, then builds everything):
        python run_leaderboard.py            # pulls raw Statcast + builds leaderboards/trajectories
        python mlb_decision.py               # Decision+ + components
        python decision_drivers.py           # rolling decision driver trajectory
        python swing_grade.py                # per-pitch swing grades
        python swing_by_pitch.py             # Swing+ by pitch type
        python matchup.py                    # pitcher arsenal + hitter skill + scale
        # then merge B2B+/Hitter+ onto the boards (see SETUP.md)

Maintainer: package the current data for hosting with:
        python fetch_data.py --pack          # writes swing_plus_data.tar.gz (upload to Drive/S3/GCS)
"""
import os, sys, tarfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
BUNDLE = ROOT / "swing_plus_data.tar.gz"
# files the app loads at runtime (everything under data/processed it actually reads)
NEEDED = [
    "leaderboard_half.parquet", "leaderboard_season.parquet", "leaderboard_alltime.parquet",
    "trajectories.parquet", "swing_grades.parquet", "mlb_decision.parquet",
    "decision_traj.parquet", "swing_by_pitch.parquet", "pitcher_arsenal.parquet",
    "hitter_skill.parquet", "bat_to_ball_plus.parquet", "birthdates.json",
    "matchup_scale.json", "matchup_league.json", "swing_grade_scale.json",
    # collision data + Contact+ v2 + DCV+ + luck layer (board-rebuild inputs, small)
    "savant_collision.parquet", "savant_collision_halves.parquet",
    "contact_v2.parquet", "obs_rates.parquet", "dcv_plus.parquet",
    "variance_layer.parquet", "variance_handoff/variance_model_output.parquet",
    "variance_handoff/shrinkage_constants.csv", "variance_handoff/engine_adjustments.json",
    "aging_projection.parquet", "stat_projections.parquet",
]


def pack():
    PROC.mkdir(parents=True, exist_ok=True)
    have = [f for f in NEEDED if (PROC / f).exists()]
    with tarfile.open(BUNDLE, "w:gz") as t:
        for f in have:
            t.add(PROC / f, arcname=f"data/processed/{f}")
    mb = BUNDLE.stat().st_size / 1e6
    print(f"packed {len(have)}/{len(NEEDED)} files -> {BUNDLE.name} ({mb:.1f} MB)")
    print("Upload it to Drive/S3/GCS, then collaborators set SWING_PLUS_DATA_URL to its direct link.")


def fetch():
    url = os.environ.get("SWING_PLUS_DATA_URL")
    if not url:
        sys.exit("SWING_PLUS_DATA_URL not set. Either set it to the hosted bundle URL, or "
                 "regenerate from scratch (see this file's docstring / SETUP.md).")
    PROC.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url} ...")
    urllib.request.urlretrieve(url, BUNDLE)
    with tarfile.open(BUNDLE, "r:gz") as t:
        t.extractall(ROOT)
    missing = [f for f in NEEDED if not (PROC / f).exists()]
    print(f"extracted to data/processed/. missing: {missing or 'none ✓'}")


if __name__ == "__main__":
    pack() if "--pack" in sys.argv else fetch()
