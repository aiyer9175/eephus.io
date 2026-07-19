# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
combo_plus.py — SwingDecision+ : the OPS-optimal blend of Swing+ (power/contact-quality)
and Decision+ (swing-decision selection). A single headline number that still decomposes
into its two orthogonal axes (the "better SEAGER": beats it on ISO, BB%, and OPS).

Weights are the standardized OPS-regression coefficients (Swing+ 0.63 / Decision+ 0.37).
Scaled to 100 = league average, SD 10. sd_swing_part + sd_dec_part = (SwingDecision+ - 100),
so the headline splits exactly back into how much each axis contributed.
"""
import numpy as np, pandas as pd

W_SP, W_DEC = 0.63, 0.37
COLS = ["swingdecision_plus", "sd_swing_part", "sd_dec_part"]


def add_to_boards(board: pd.DataFrame) -> pd.DataFrame:
    b = board.copy()
    if "swing_plus" not in b.columns or "decision_plus_mlb" not in b.columns:
        return board
    m = b["swing_plus"].notna() & b["decision_plus_mlb"].notna()
    if m.sum() < 20:
        return board
    sS, dS = b.loc[m, "swing_plus"], b.loc[m, "decision_plus_mlb"]
    zS = (b["swing_plus"] - sS.mean()) / sS.std()
    zD = (b["decision_plus_mlb"] - dS.mean()) / dS.std()
    raw = W_SP * zS + W_DEC * zD
    sd = raw[m].std()
    b["swingdecision_plus"] = (100 + 10 * (raw - raw[m].mean()) / sd).round(1)
    b["sd_swing_part"] = (10 * W_SP * zS / sd).round(1)     # contribution of each axis (sum ≈ SD+ - 100)
    b["sd_dec_part"] = (10 * W_DEC * zD / sd).round(1)
    b.loc[~m, COLS] = np.nan
    return b


if __name__ == "__main__":
    from pathlib import Path
    P = Path("data/processed")
    for v in ["half", "season", "alltime"]:
        f = P / f"leaderboard_{v}.parquet"
        b = pd.read_parquet(f)
        b = b[[c for c in b.columns if c not in COLS]]
        b = add_to_boards(b)
        b.to_parquet(f, index=False)
        n = b["swingdecision_plus"].notna().sum() if "swingdecision_plus" in b else 0
        print(f"{v}: SwingDecision+ on {n}/{len(b)}")
        if v == "alltime":
            top = b.dropna(subset=["swingdecision_plus"]).sort_values("swingdecision_plus", ascending=False).head(8)
            for _, r in top.iterrows():
                print(f"   {r['name']:22s} SD+ {r.swingdecision_plus:.0f}  (Swing {r.sd_swing_part:+.0f} / Dec {r.sd_dec_part:+.0f})")
