# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
savant_collision.py — pull Savant's NEW bat-tracking collision dataset
(leaderboard/bat-tracking/swing-timing-miss-distance) for every player.

Per (batter, year): avg miss distance, flawed/perfect contact %, horizontal
alignment (tied-up/centered/flailed + avg inches), timing (early/on-time/late
+ avg ms), vertical alignment (over/lined-up/under + avg inches), n_swings,
whiff rate. Data starts at the 2023 ASG.

Outputs:
  data/processed/savant_collision.parquet         (full seasons 2023-2026)
  data/processed/savant_collision_halves.parquet  (within-season date halves,
                                                   for split-half reliability)
Also engineers derived features: timing/horiz/vert biases + entropies.
"""
import io, time, urllib.request
import numpy as np, pandas as pd
from pathlib import Path

BASE = ("https://baseballsavant.mlb.com/leaderboard/bat-tracking/"
        "swing-timing-miss-distance?type=batter&season%5B%5D={yr}"
        "{dates}&min={mn}&csv=true")
OUT = Path("data/processed")

# within-season halves (2023 starts at the ASG; 2026 in progress as of Jun 2026)
HALVES = {
    2023: [("2023-07-01", "2023-08-22"), ("2023-08-23", "2023-11-01")],
    2024: [("2024-03-01", "2024-06-15"), ("2024-06-16", "2024-11-01")],
    2025: [("2025-03-01", "2025-06-15"), ("2025-06-16", "2025-11-01")],
    2026: [("2026-03-01", "2026-05-07"), ("2026-05-08", "2026-12-01")],
}
PCT = ["flawed_percent", "perfect_percent", "tied_up_percent", "centered_percent",
       "flailed_percent", "early_percent", "on_time_percent", "late_percent",
       "over_percent", "lined_up_percent", "under_percent", "whiff_rate",
       "competitive_percent"]


def _get(yr, dates="", mn=25):
    url = BASE.format(yr=yr, dates=dates, mn=mn)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")
    df = pd.read_csv(io.StringIO(raw))
    df["miss_distance"] = pd.to_numeric(df["miss_distance"], errors="coerce")
    return df


def _entropy(df, cols):
    p = df[cols].clip(1e-9, 1).to_numpy()
    p = p / p.sum(axis=1, keepdims=True)
    return -(p * np.log(p)).sum(axis=1)


def engineer(df):
    d = df.copy()
    d["timing_bias"] = d["early_percent"] - d["late_percent"]          # +early/-late
    d["horiz_bias"] = d["flailed_percent"] - d["tied_up_percent"]      # +flail/-tied
    d["vert_bias"] = d["under_percent"] - d["over_percent"]            # +under/-over
    d["timing_entropy"] = _entropy(d, ["early_percent", "on_time_percent", "late_percent"])
    d["horiz_entropy"] = _entropy(d, ["tied_up_percent", "centered_percent", "flailed_percent"])
    d["vert_entropy"] = _entropy(d, ["over_percent", "lined_up_percent", "under_percent"])
    d["collision_entropy"] = d[["timing_entropy", "horiz_entropy", "vert_entropy"]].mean(axis=1)
    return d


if __name__ == "__main__":
    full, halves = [], []
    for yr in [2023, 2024, 2025, 2026]:
        f = _get(yr)
        f["year"] = yr
        full.append(f)
        print(f"{yr}: {len(f)} hitters (full)")
        for i, (a, b) in enumerate(HALVES[yr]):
            h = _get(yr, dates=f"&dateStart={a}&dateEnd={b}")
            h["year"], h["half_idx"] = yr, i
            halves.append(h)
            print(f"   half {i} ({a}..{b}): {len(h)}")
            time.sleep(1)
        time.sleep(1)
    F = engineer(pd.concat(full, ignore_index=True))
    H = engineer(pd.concat(halves, ignore_index=True))
    F.to_parquet(OUT / "savant_collision.parquet", index=False)
    H.to_parquet(OUT / "savant_collision_halves.parquet", index=False)
    print(f"\nsaved: full {F.shape}, halves {H.shape}")
    print("columns:", [c for c in F.columns if c not in ("name", "team_name")])
