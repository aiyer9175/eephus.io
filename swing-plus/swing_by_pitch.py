# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
swing_by_pitch.py — Swing+ split by pitch GROUP (Fastball / Breaking / Offspeed)
and by INDIVIDUAL pitch type (4-seam, sinker, cutter, slider, sweeper, curve,
changeup, splitter, …) so the modal can drill down inside a group.

Validated as a real, stable signal: FB Swing+ half-to-half r=0.87, BR r=0.74, and
the FB−BR gap (path quality vs FB vs vs BR) r=0.72 — a repeatable trait, not noise.

Scores career (batter, stand, key) profiles with the deployable model and caches to
data/processed/swing_by_pitch.parquet. `level` is "group" or "type"; for type rows
`pgroup` is the parent group so the UI can nest them.
"""
from pathlib import Path
import pandas as pd
from swing_plus import SwingPlusModel

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2", "2026_H1"]
FB = {"FF", "SI", "FC"}
BR = {"SL", "ST", "CU", "KC", "SV", "CS", "KN"}
OFF = {"CH", "FS", "FO", "SC"}
TYPE_LABEL = {"FF": "4-Seam", "SI": "Sinker", "FC": "Cutter", "SL": "Slider",
              "ST": "Sweeper", "CU": "Curveball", "KC": "Knuckle-Curve", "SV": "Slurve",
              "CS": "Slow Curve", "KN": "Knuckleball", "CH": "Changeup", "FS": "Splitter",
              "FO": "Forkball", "SC": "Screwball"}
MIN_TYPE = 30


def _group(pt):
    if pt in FB: return "FB"
    if pt in BR: return "BR"
    if pt in OFF: return "OFF"
    return None


def build():
    m = SwingPlusModel(ROOT / "swing_plus_model_v1.joblib")
    m.min_swings = MIN_TYPE   # allow sub-splits below the 180 leaderboard floor;
    #                           reliability-shrinkage (swing_plus) handles small-n noise
    parts = []
    for h in HALVES:
        f = ROOT / "data" / "raw" / f"statcast_{h}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f)
        d["pgroup"] = d["pitch_type"].map(_group)
        parts.append(d[d["pgroup"].notna()])
    allp = pd.concat(parts, ignore_index=True)
    cols = ["batter", "stand", "swing_plus", "n_swings",
            "bat_speed_mean", "attack_angle_mean", "swing_path_tilt_mean"]

    # group level
    grp = m.score_pitch_level(allp, group_by=["stand", "pgroup"])
    grp = grp[[c for c in cols + ["pgroup"] if c in grp.columns]].copy()
    grp = grp[grp["n_swings"] >= 30]
    grp["level"] = "group"; grp["key"] = grp["pgroup"]; grp["label"] = grp["pgroup"]

    # individual pitch-type level
    typ = m.score_pitch_level(allp, group_by=["stand", "pitch_type"])
    typ = typ[[c for c in cols + ["pitch_type"] if c in typ.columns]].copy()
    typ = typ[typ["n_swings"] >= MIN_TYPE]
    typ["pgroup"] = typ["pitch_type"].map(_group)
    typ = typ[typ["pgroup"].notna()]
    typ["level"] = "type"; typ["key"] = typ["pitch_type"]
    typ["label"] = typ["pitch_type"].map(lambda p: TYPE_LABEL.get(p, p))

    sc = pd.concat([grp, typ], ignore_index=True)
    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")[["batter", "stand", "name"]]
    sc = sc.merge(at, on=["batter", "stand"], how="left")
    keep = ["batter", "stand", "level", "key", "label", "pgroup", "swing_plus",
            "n_swings", "bat_speed_mean", "attack_angle_mean", "swing_path_tilt_mean", "name"]
    sc = sc[[c for c in keep if c in sc.columns]]
    sc.to_parquet(PROC / "swing_by_pitch.parquet", index=False)
    print(f"wrote swing_by_pitch.parquet ({len(sc)} rows: "
          f"{(sc.level=='group').sum()} group + {(sc.level=='type').sum()} type)")
    return sc


if __name__ == "__main__":
    sc = build()
    v = sc[sc["batter"] == 678246]
    print("\nMiguel Vargas:")
    print(v[["level", "key", "label", "swing_plus", "n_swings"]]
          .sort_values(["level", "n_swings"], ascending=[True, False]).to_string(index=False))
