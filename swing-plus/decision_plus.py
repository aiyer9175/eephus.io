# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
decision_plus.py — pull in the externally-built MLB swing-DECISION model and join it
to the Swing+ boards on batter id (mlbam_id).

Decision+ is the orthogonal axis to Swing+: Swing+ = how good the bat PATH is
(execution); Decision+ = swing/take SELECTION (chase avoidance, zone attack,
projected BB/K). Validated on the 138 MLB overlap: swing_decision_talent+ vs
Swing+ r=-0.10 (orthogonal); their projected K% vs our observed K% r=0.87.

The source is a separate project; we cache a local MLB-only copy so swing_plus is
self-contained and never needs the upstream pipeline rerun.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
LOCAL = PROC / "decision_plus_mlb.csv"
SRC = Path("/Users/willcahoon/Documents/New project/swing_decision_translation_outputs/"
           "full_swing_decision_tool_2026/full_swing_decision_leaderboard_2026.csv")

DCOLS = ["decision_plus", "decision_value_plus", "swing_decision_talent_plus",
         "chase_avoidance_plus", "zone_attack_plus",
         "projected_bb_pct", "projected_k_pct", "projected_bb_minus_k_pct",
         "decision_pitches"]


def sync() -> bool:
    """Refresh the local MLB-only cache from the source project if it's present."""
    if not SRC.exists():
        return False
    d = pd.read_csv(SRC)
    d = d[d["level"] == "MLB"].rename(columns={"mlbam_id": "batter", "pitches": "decision_pitches"})
    keep = ["batter"] + [c for c in DCOLS if c in d.columns]
    d = d[keep].dropna(subset=["batter"])
    d["batter"] = d["batter"].astype(int)
    d = d.drop_duplicates("batter")
    PROC.mkdir(parents=True, exist_ok=True)
    d.to_csv(LOCAL, index=False)
    return True


def load() -> pd.DataFrame:
    if not LOCAL.exists():
        sync()
    if not LOCAL.exists():
        return pd.DataFrame(columns=["batter"] + DCOLS)
    return pd.read_csv(LOCAL)


def add_to_boards(half, season, alltime):
    sync()
    dec = load()
    keep = ["batter"] + [c for c in DCOLS if c in dec.columns]
    dec = dec[keep]
    return tuple(b.merge(dec, on="batter", how="left") for b in (half, season, alltime))


if __name__ == "__main__":
    ok = sync()
    d = load()
    print(f"synced={ok}  MLB decision rows={len(d)}  cols={[c for c in d.columns if c!='batter']}")
    print(d.head(5).to_string(index=False))
