# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""bat_to_ball.py — join the Bat-to-Ball+ model (external 12-module framework) onto the
leaderboards. B2B+ is a third orthogonal hitter axis (contact-quality / bat-to-ball damage;
~uncorrelated with Swing+ r=-0.03 and Decision+ r=-0.07, but +0.32 with OPS)."""
import numpy as np, pandas as pd
from pathlib import Path

PROC = Path(__file__).parent / "data" / "processed"
SRC = PROC / "bat_to_ball_plus.parquet"
COLS = ["bat_to_ball_plus", "contact_plus", "dc_plus"]   # B2B+, contact-freq, damage-conversion


def _src():
    p = pd.read_parquet(SRC)
    return p.rename(columns={"bat_to_ball_plus": "b2b_plus", "contact_plus": "contact_plus_b2b",
                             "dc_plus": "dc_plus_b2b"})[["batter", "season", "n_bip",
                             "b2b_plus", "contact_plus_b2b", "dc_plus_b2b"]]


def _v2():
    """Contact+ v2 (collision-aware, contact_v2.py); falls back to v1 in add_to_boards."""
    p = PROC / "contact_v2.parquet"
    if not p.exists():
        return None
    v = pd.read_parquet(p).rename(columns={"id": "batter", "year": "_yr",
                                           "contact2_plus": "contact2_plus"})
    return v[["batter", "_yr", "contact2_plus", "n_swings"]].drop_duplicates(["batter", "_yr"])


def _dcv():
    """DCV+ (external damage-geometry framework; 2026 calibrated by dcv_2026.py)."""
    p = PROC / "dcv_plus.parquet"
    if not p.exists():
        return None
    v = pd.read_parquet(p).rename(columns={"season": "_yr"})
    v["batter"] = v["batter"].astype("int64")
    v["_yr"] = v["_yr"].astype("int64")
    return v.dropna(subset=["dcv_plus"])[["batter", "_yr", "dcv_plus", "n_bip"]]


VAR_COLS = ["sk_woba", "luck_woba", "sk_iso", "luck_iso"]


def _proj():
    """next-season skill projection (aging framework; ~/aging_curves 03_project.py)."""
    p = PROC / "aging_projection.parquet"
    if not p.exists():
        return None
    v = pd.read_parquet(p).rename(columns={"season": "_yr"})
    return v[["batter", "_yr", "hitter_plus_proj"]].dropna(
        subset=["hitter_plus_proj"]).drop_duplicates(["batter", "_yr"])


STATPROJ = ["proj_xwoba", "proj_woba", "proj_k_pct", "proj_bb_pct", "proj_iso"]


def _statproj():
    """next-season stat projections (projection engine; ~/projection_engine)."""
    p = PROC / "stat_projections.parquet"
    if not p.exists():
        return None
    v = pd.read_parquet(p).rename(columns={"season": "_yr"})
    return v[["batter", "_yr"] + STATPROJ].dropna(
        subset=["proj_xwoba"]).drop_duplicates(["batter", "_yr"])


def _variance():
    """luck/regression layer (external variance model; variance_layer.py)."""
    p = PROC / "variance_layer.parquet"
    if not p.exists():
        return None
    v = pd.read_parquet(p).rename(columns={"season": "_yr"})
    return v[["batter", "_yr"] + VAR_COLS].drop_duplicates(["batter", "_yr"])


def add_to_boards(board: pd.DataFrame) -> pd.DataFrame:
    if not SRC.exists():
        return board
    s = _src()
    v2 = _v2()
    dcv = _dcv()
    var = _variance()
    prj = _proj()
    sp_ = _statproj()
    keep = ["b2b_plus", "contact_plus_b2b", "dc_plus_b2b"]
    b = board.copy()
    s_yr = s.assign(_yr=s["season"].astype(int))[["batter", "_yr"] + keep]
    if "half" in b.columns:                       # half board -> match the half's season year
        b["_yr"] = b["half"].str[:4].astype(int)
        b = b.merge(s_yr, on=["batter", "_yr"], how="left")
    elif "season" in b.columns:                   # season board -> match year
        b["_yr"] = b["season"].astype(int)
        b = b.merge(s_yr, on=["batter", "_yr"], how="left")
    else:                                         # all-time -> BIP-weighted career B2B+
        car = s.groupby("batter").apply(lambda g: pd.Series({
            "b2b_plus": np.average(g.b2b_plus, weights=g.n_bip),
            "contact_plus_b2b": np.average(g.contact_plus_b2b, weights=g.n_bip),
            "dc_plus_b2b": np.average(g.dc_plus_b2b, weights=g.n_bip)})).reset_index()
        b = b.merge(car, on="batter", how="left")
        if v2 is not None:                        # swing-weighted career Contact+ v2
            c2 = v2.groupby("batter").apply(lambda g: pd.Series({
                "contact2_plus": np.average(g.contact2_plus, weights=g.n_swings)})).reset_index()
            b = b.merge(c2, on="batter", how="left")
        if dcv is not None:                       # BIP-weighted career DCV+
            dc = dcv.dropna(subset=["n_bip"]).groupby("batter").apply(lambda g: pd.Series({
                "dcv_plus": np.average(g.dcv_plus, weights=g.n_bip)})).reset_index()
            b = b.merge(dc, on="batter", how="left")
        if var is not None:                       # alltime -> CURRENT (latest-season) luck
            cur = var.sort_values("_yr").groupby("batter").tail(1).drop(columns="_yr")
            b = b.merge(cur, on="batter", how="left")
        if prj is not None:                       # alltime -> latest-season projection
            cur = prj.sort_values("_yr").groupby("batter").tail(1).drop(columns="_yr")
            b = b.merge(cur, on="batter", how="left")
        if sp_ is not None:
            cur = sp_.sort_values("_yr").groupby("batter").tail(1).drop(columns="_yr")
            b = b.merge(cur, on="batter", how="left")
    if "_yr" in b.columns:
        if v2 is not None:
            b = b.merge(v2[["batter", "_yr", "contact2_plus"]], on=["batter", "_yr"], how="left")
        if dcv is not None:
            b = b.merge(dcv[["batter", "_yr", "dcv_plus"]], on=["batter", "_yr"], how="left")
        if var is not None:
            b = b.merge(var, on=["batter", "_yr"], how="left")
        if prj is not None:
            b = b.merge(prj, on=["batter", "_yr"], how="left")
        if sp_ is not None:
            b = b.merge(sp_, on=["batter", "_yr"], how="left")
        b = b.drop(columns="_yr")
    # the contact AXIS the app + Hitter+ use: v2 (collision-aware) where available, else v1
    if "contact2_plus" in b.columns:
        b["contact_axis"] = b["contact2_plus"].fillna(b["contact_plus_b2b"])
    else:
        b["contact_axis"] = b["contact_plus_b2b"]
    for c in keep + ["contact2_plus", "contact_axis", "dcv_plus"]:
        if c in b.columns:
            b[c] = b[c].round(1)
    for c in VAR_COLS:
        if c in b.columns:
            b[c] = b[c].round(3)
    return b


if __name__ == "__main__":
    for v in ["alltime", "season", "half"]:
        bd = add_to_boards(pd.read_parquet(PROC / f"leaderboard_{v}.parquet"))
        print(v, "B2B+ coverage:", bd["b2b_plus"].notna().sum(), "/", len(bd))
