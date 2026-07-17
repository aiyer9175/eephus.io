# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Aggregate pitch-level data to player-season-level behavioral metrics.

Two metric families, honestly separated by what the data supports:
  - call-code metrics (ALL levels, every pitch): swing%, contact%, whiff%,
    CSW%, count-state swing behavior, first-pitch swing, 2-strike behavior
  - zone metrics (tracked pitches only): zone%, z-swing%, chase (o-swing%),
    z-contact%, o-contact%, in-zone take%, zone recognition (z-o swing gap)

Tracking coverage (share of pitches with a zone) is computed per player and
drives the data-quality tier. Zone metrics are never imputed where tracking
does not exist.
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
    BB_EVENT_TYPES, DATA_PROCESSED, DATA_RAW, HBP_EVENT_TYPES, IN_ZONE,
    K_EVENT_TYPES, log_run,
)
from zone_lib import best_zone_frame, load_calibration

GRP = ["batter_id", "season", "level"]
PITCH_ROOT = "pitches_v2"
TB_BY_EVENT = {"single": 1, "double": 2, "triple": 3, "home_run": 4}


def iter_dirs(seasons=None, levels=None):
    for d in sorted((DATA_RAW / PITCH_ROOT).iterdir()):
        if not d.is_dir():
            continue
        season_str, safe_level = d.name.split("_", 1)
        season = int(season_str)
        level = safe_level.replace("plus", "+")
        if seasons and season not in seasons:
            continue
        if levels and level not in levels:
            continue
        yield d, season, level


def agg_level_season(d: Path, calib: dict) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    files = glob.glob(str(d / "pitches_*.parquet"))
    if not files:
        return None, None
    p = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    p = p[p.batter_id.notna()].copy()
    p["batter_id"] = p.batter_id.astype("int64")
    # universal zone: official label where tracked, calibrated stringer else
    p = best_zone_frame(p, calib)
    p["in_zone"] = pd.to_numeric(p.zone_final, errors="coerce").isin(IN_ZONE)
    p["tracked"] = pd.to_numeric(p.zone, errors="coerce").notna()
    p["has_zone"] = p.zone_final.notna()
    p["two_strike"] = p.pre_strikes == 2
    p["three_ball"] = p.pre_balls == 3
    p["first_pitch"] = (p.pre_balls == 0) & (p.pre_strikes == 0)
    p["csw"] = p.is_called_strike | p.is_whiff
    p["is_ball"] = p.code.isin(["B", "*B", "P", "I", "V"])
    p["ts_called"] = p.two_strike & p.is_called_strike

    g = p.groupby(GRP)
    out = g.agg(
        pitches=("code", "size"),
        swings=("is_swing", "sum"),
        whiffs=("is_whiff", "sum"),
        contacts=("is_contact", "sum"),
        fouls=("is_foul", "sum"),
        inplay=("is_inplay", "sum"),
        called_strikes=("is_called_strike", "sum"),
        balls_taken=("is_ball", "sum"),
        ts_called=("ts_called", "sum"),
        csw=("csw", "sum"),
        n_tracked=("tracked", "sum"),
        n_zoned=("has_zone", "sum"),
        n_games=("gamePk", "nunique"),
        bat_side_share_R=("bat_side", lambda s: (s == "R").mean()),
    ).reset_index()

    # count-state swing behavior (call codes, all pitches)
    for name, mask in {
        "fp": p.first_pitch, "ts": p.two_strike, "tb": p.three_ball,
    }.items():
        sub = p[mask].groupby(GRP).agg(
            **{f"{name}_pitches": ("code", "size"), f"{name}_swings": ("is_swing", "sum")}
        ).reset_index()
        out = out.merge(sub, on=GRP, how="left")

    # zone metrics on best-available zone (tracked label or calibrated stringer)
    grid = None
    t = p[p.has_zone]
    if len(t):
        tz = t.groupby(GRP).agg(
            trk_zone=("in_zone", "sum"),
            trk_pitches=("in_zone", "size"),
        ).reset_index()
        z = t[t.in_zone].groupby(GRP).agg(
            z_pitches=("in_zone", "size"), z_swings=("is_swing", "sum"),
            z_whiffs=("is_whiff", "sum"), z_contacts=("is_contact", "sum"),
            z_called=("is_called_strike", "sum"),
        ).reset_index()
        o = t[~t.in_zone].groupby(GRP).agg(
            o_pitches=("in_zone", "size"), o_swings=("is_swing", "sum"),
            o_whiffs=("is_whiff", "sum"), o_contacts=("is_contact", "sum"),
        ).reset_index()
        out = out.merge(tz, on=GRP, how="left").merge(z, on=GRP, how="left").merge(o, on=GRP, how="left")

    # per-player 13-zone grids for swing/take + damage graphics
    tg = t.copy()
    tg["tb"] = tg.pa_event_type.map(TB_BY_EVENT).fillna(0.0) * tg.is_inplay
    tg["bip"] = tg.is_inplay
    grid = tg.groupby(GRP + ["zone_final"]).agg(
        zpitches=("code", "size"), zswings=("is_swing", "sum"),
        zwhiffs=("is_whiff", "sum"), zcontacts=("is_contact", "sum"),
        zcalled=("is_called_strike", "sum"), zbip=("bip", "sum"),
        ztb=("tb", "sum"),
    ).reset_index()

    # PA outcomes from the PA table
    pa_files = glob.glob(str(d / "pa_*.parquet"))
    pa = pd.concat([pd.read_parquet(f) for f in pa_files], ignore_index=True)
    pa = pa[pa.is_pa & pa.batter_id.notna()].copy()
    pa["batter_id"] = pa.batter_id.astype("int64")
    pa["is_k"] = pa.event_type.isin(K_EVENT_TYPES)
    pa["is_bb"] = pa.event_type.isin(BB_EVENT_TYPES)
    pa["is_hbp"] = pa.event_type.isin(HBP_EVENT_TYPES)
    pao = pa.groupby(GRP).agg(
        pa=("is_pa", "sum"), k=("is_k", "sum"), bb=("is_bb", "sum"),
        hbp=("is_hbp", "sum"), batter_name=("batter_name", "first"),
    ).reset_index()
    out = out.merge(pao, on=GRP, how="outer")
    return out, grid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", default=None)
    ap.add_argument("--levels", nargs="+", default=None)
    args = ap.parse_args()

    calib = load_calibration()
    frames, grids = [], []
    for d, season, level in iter_dirs(args.seasons, args.levels):
        df, grid = agg_level_season(d, calib)
        if df is not None and len(df):
            frames.append(df)
            if grid is not None:
                grids.append(grid)
            print(f"{season} {level}: {len(df)} player rows", flush=True)
    m = pd.concat(frames, ignore_index=True)
    grid_all = pd.concat(grids, ignore_index=True)
    grid_all.to_parquet(DATA_PROCESSED / "zone_grids.parquet", index=False)

    cnt_cols = [c for c in m.columns if m[c].dtype.kind in "fi" and c not in GRP]
    m[cnt_cols] = m[cnt_cols].fillna(0)

    # rates (call-code family: defined everywhere)
    m["swing_pct"] = m.swings / m.pitches.where(m.pitches > 0)
    m["contact_pct"] = m.contacts / m.swings.where(m.swings > 0)
    m["whiff_pct"] = m.whiffs / m.swings.where(m.swings > 0)
    m["csw_pct"] = m.csw / m.pitches.where(m.pitches > 0)
    m["called_strike_pct"] = m.called_strikes / m.pitches.where(m.pitches > 0)
    m["fp_swing_pct"] = m.fp_swings / m.fp_pitches.where(m.fp_pitches > 0)
    m["ts_swing_pct"] = m.ts_swings / m.ts_pitches.where(m.ts_pitches > 0)
    m["tb_swing_pct"] = m.tb_swings / m.tb_pitches.where(m.tb_pitches > 0)
    m["k_pct"] = m.k / m.pa.where(m.pa > 0)
    m["bb_pct"] = m.bb / m.pa.where(m.pa > 0)
    # take quality: of pitches taken, share that were called balls.
    # Zone-free discipline measure available at every level (Tier B core).
    m["takes"] = m.pitches - m.swings
    m["take_ball_share"] = m.balls_taken / (m.balls_taken + m.called_strikes).where(
        (m.balls_taken + m.called_strikes) > 0)
    m["ts_called_share"] = m.ts_called / m.ts_pitches.where(m.ts_pitches > 0)

    # zone family: best-available zone (tracked label or calibrated stringer)
    m["tracked_share"] = m.n_tracked / m.pitches.where(m.pitches > 0)
    m["zone_coverage"] = m.n_zoned / m.pitches.where(m.pitches > 0)
    m["zone_rate"] = m.trk_zone / m.trk_pitches.where(m.trk_pitches > 0)
    m["z_swing_pct"] = m.z_swings / m.z_pitches.where(m.z_pitches > 0)
    m["o_swing_pct"] = m.o_swings / m.o_pitches.where(m.o_pitches > 0)  # chase
    m["z_contact_pct"] = m.z_contacts / m.z_swings.where(m.z_swings > 0)
    m["o_contact_pct"] = m.o_contacts / m.o_swings.where(m.o_swings > 0)
    m["z_take_pct"] = 1 - m.z_swing_pct
    m["zone_recognition"] = m.z_swing_pct - m.o_swing_pct

    # ages: chadwick birthdays, season age as of June 30
    bd = pd.read_csv(Path.home() / "chadwick_birthdays.csv")
    bd = bd.dropna(subset=["key_mlbam", "birth_year"]).copy()
    bd["batter_id"] = bd.key_mlbam.astype("int64")
    bd = bd.drop_duplicates("batter_id")
    m = m.merge(bd[["batter_id", "birth_year", "birth_month", "birth_day"]],
                on="batter_id", how="left")
    after_jun30 = (m.birth_month > 6) | ((m.birth_month == 6) & (m.birth_day > 30))
    m["age"] = m.season - m.birth_year - after_jun30.fillna(False).astype(int)

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out_path = DATA_PROCESSED / "player_season_level_metrics.parquet"
    m.to_parquet(out_path, index=False)
    print(f"\n{len(m)} player-season-level rows -> {out_path}")
    print("age coverage: %.1f%%" % (100 * m.age.notna().mean()))
    log_run("player_metrics_v1", n_rows=len(m),
            seasons=sorted(m.season.unique().tolist()))


if __name__ == "__main__":
    main()
