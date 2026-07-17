# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Validation gate: reconstructed PA/K/BB/HBP must match official statlines.

Hard gate before any modeling. Reconstructed counts come from the PA table
(play results), so they do not depend on pitch tracking completeness.
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    BB_EVENT_TYPES, DATA_PROCESSED, DATA_RAW, HBP_EVENT_TYPES, K_EVENT_TYPES,
    LEVEL_ORDER, OUTPUTS, log_run,
)


def load_pa_tables(seasons=None, levels=None) -> pd.DataFrame:
    frames = []
    for d in sorted((DATA_RAW / "pitches").iterdir()):
        if not d.is_dir():
            continue
        season_str, safe_level = d.name.split("_", 1)
        season = int(season_str)
        level = safe_level.replace("plus", "+")
        if seasons and season not in seasons:
            continue
        if levels and level not in levels:
            continue
        files = glob.glob(str(d / "pa_*.parquet"))
        if files:
            frames.append(pd.concat([pd.read_parquet(f) for f in files], ignore_index=True))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def reconstruct(pa: pd.DataFrame) -> pd.DataFrame:
    pa = pa[pa.is_pa].copy()
    pa["is_k"] = pa.event_type.isin(K_EVENT_TYPES)
    pa["is_bb"] = pa.event_type.isin(BB_EVENT_TYPES)
    pa["is_hbp"] = pa.event_type.isin(HBP_EVENT_TYPES)
    rec = (pa.groupby(["batter_id", "season", "level"], as_index=False)
           .agg(pa_rec=("is_pa", "sum"), k_rec=("is_k", "sum"),
                bb_rec=("is_bb", "sum"), hbp_rec=("is_hbp", "sum"),
                g_rec=("gamePk", "nunique"),
                batter_name=("batter_name", "first")))
    return rec


def metrics(df: pd.DataFrame, rec_col: str, off_col: str) -> dict:
    a, b = df[rec_col].astype(float), df[off_col].astype(float)
    err = a - b
    return {
        "corr": round(float(np.corrcoef(a, b)[0, 1]), 5) if len(df) > 2 else np.nan,
        "mae": round(float(err.abs().mean()), 4),
        "rmse": round(float(np.sqrt((err ** 2).mean())), 4),
        "bias": round(float(err.mean()), 4),
        "exact_match": round(float((err == 0).mean()), 5),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", default=None)
    ap.add_argument("--levels", nargs="+", default=None)
    args = ap.parse_args()

    pa = load_pa_tables(args.seasons, args.levels)
    if pa.empty:
        print("no PA tables found"); return
    rec = reconstruct(pa)

    official = pd.read_parquet(DATA_RAW / "official_statlines" / "official_player_season_level.parquet")
    official = official.rename(columns={"player_id": "batter_id"})
    # only compare level-seasons that have been extracted
    extracted = rec[["season", "level"]].drop_duplicates()
    official = official.merge(extracted, on=["season", "level"], how="inner")

    merged = rec.merge(
        official[["batter_id", "season", "level", "pa", "bb", "so", "hbp", "g", "player_name"]],
        on=["batter_id", "season", "level"], how="outer", indicator=True)

    rows = []
    for (season, level), grp in merged.groupby(["season", "level"]):
        both = grp[grp._merge == "both"]
        only_rec = grp[(grp._merge == "left_only") & (grp.pa_rec > 0)]
        only_off = grp[(grp._merge == "right_only") & (grp.pa > 0)]
        row = {"season": season, "level": level,
               "players_matched": len(both),
               "players_only_reconstructed": len(only_rec),
               "players_only_official": len(only_off),
               "official_pa_missing": int(only_off.pa.sum()) if len(only_off) else 0}
        for name, (rc, oc) in {"pa": ("pa_rec", "pa"), "k": ("k_rec", "so"),
                               "bb": ("bb_rec", "bb"), "hbp": ("hbp_rec", "hbp")}.items():
            for k, v in metrics(both, rc, oc).items():
                row[f"{name}_{k}"] = v
        # rate-level checks on meaningful samples
        q = both[both.pa >= 50]
        if len(q) > 5:
            krate_err = (q.k_rec / q.pa_rec - q.so / q.pa)
            bbrate_err = (q.bb_rec / q.pa_rec - q.bb / q.pa)
            row["kpct_mae_pa50"] = round(float(krate_err.abs().mean()), 5)
            row["bbpct_mae_pa50"] = round(float(bbrate_err.abs().mean()), 5)
        rows.append(row)

    report = pd.DataFrame(rows).sort_values(
        ["season", "level"], key=lambda s: s.map(LEVEL_ORDER).fillna(s))
    out_dir = OUTPUTS / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(out_dir / "pa_reconstruction_by_level_season.csv", index=False)

    # global duplicate checks
    dup_pa = pa.duplicated(["gamePk", "play_idx"]).sum()
    n_games = pa.gamePk.nunique()

    gate_cols = ["pa_exact_match", "k_exact_match", "bb_exact_match"]
    worst = report[gate_cols].min().min()
    print(report.to_string(index=False))
    print(f"\nduplicate (gamePk, play_idx) PA rows: {dup_pa}")
    print(f"games covered: {n_games}")
    print(f"worst exact-match rate across level-seasons: {worst:.4f}")
    gate = "PASS" if (report.pa_corr.min() > 0.999 and worst > 0.95
                      and report.kpct_mae_pa50.max() < 0.002) else "REVIEW"
    print(f"GATE: {gate}")
    log_run("pa_reconstruction_gate_v1", gate=gate, n_games=int(n_games),
            dup_pa=int(dup_pa), worst_exact=float(worst))


if __name__ == "__main__":
    main()
