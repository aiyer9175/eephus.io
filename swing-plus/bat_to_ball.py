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


def add_to_boards(board: pd.DataFrame) -> pd.DataFrame:
    if not SRC.exists():
        return board
    s = _src()
    keep = ["b2b_plus", "contact_plus_b2b", "dc_plus_b2b"]
    b = board.copy()
    s_yr = s.assign(_yr=s["season"].astype(int))[["batter", "_yr"] + keep]
    if "half" in b.columns:                       # half board -> match the half's season year
        b["_yr"] = b["half"].str[:4].astype(int)
        b = b.merge(s_yr, on=["batter", "_yr"], how="left").drop(columns="_yr")
    elif "season" in b.columns:                   # season board -> match year
        b["_yr"] = b["season"].astype(int)
        b = b.merge(s_yr, on=["batter", "_yr"], how="left").drop(columns="_yr")
    else:                                         # all-time -> BIP-weighted career B2B+
        car = s.groupby("batter").apply(lambda g: pd.Series({
            "b2b_plus": np.average(g.b2b_plus, weights=g.n_bip),
            "contact_plus_b2b": np.average(g.contact_plus_b2b, weights=g.n_bip),
            "dc_plus_b2b": np.average(g.dc_plus_b2b, weights=g.n_bip)})).reset_index()
        b = b.merge(car, on="batter", how="left")
    for c in keep:
        if c in b.columns:
            b[c] = b[c].round(1)
    return b


if __name__ == "__main__":
    for v in ["alltime", "season", "half"]:
        bd = add_to_boards(pd.read_parquet(PROC / f"leaderboard_{v}.parquet"))
        print(v, "B2B+ coverage:", bd["b2b_plus"].notna().sum(), "/", len(bd))
