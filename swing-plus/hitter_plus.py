# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
hitter_plus.py — Hitter+ : the complete-hitter metric = OPS-optimal blend of the three
orthogonal axes Swing+ (power), Decision+ (selection), B2B+ (bat-to-ball / contact quality).

Weights are the standardized OPS-regression coefficients (Swing+ 0.39 / Decision+ 0.28 /
B2B+ 0.33). Scaled to 100 = league avg, SD 10. Beats SwingDecision+ and SEAGER on ISO,
BB%, and OPS (same- and next-season). Component parts sum to (Hitter+ - 100) for drivers.
"""
import numpy as np, pandas as pd

W_SP, W_DEC, W_B2B = 0.39, 0.28, 0.33
COLS = ["hitter_plus", "h_swing_part", "h_dec_part", "h_b2b_part"]


def add_to_boards(board: pd.DataFrame) -> pd.DataFrame:
    b = board.copy()
    need = ["swing_plus", "decision_plus_mlb", "b2b_plus"]
    if not all(c in b.columns for c in need):
        return board
    m = b[need].notna().all(axis=1)
    if m.sum() < 20:
        return board
    zs = {}
    for c, w in [("swing_plus", W_SP), ("decision_plus_mlb", W_DEC), ("b2b_plus", W_B2B)]:
        mu, sd = b.loc[m, c].mean(), b.loc[m, c].std()
        zs[c] = (b[c] - mu) / sd
    raw = W_SP * zs["swing_plus"] + W_DEC * zs["decision_plus_mlb"] + W_B2B * zs["b2b_plus"]
    sd = raw[m].std()
    b["hitter_plus"] = (100 + 10 * (raw - raw[m].mean()) / sd).round(1)
    b["h_swing_part"] = (10 * W_SP * zs["swing_plus"] / sd).round(1)
    b["h_dec_part"] = (10 * W_DEC * zs["decision_plus_mlb"] / sd).round(1)
    b["h_b2b_part"] = (10 * W_B2B * zs["b2b_plus"] / sd).round(1)
    b.loc[~m, COLS] = np.nan
    return b


if __name__ == "__main__":
    from pathlib import Path
    P = Path("data/processed")
    for v in ["half", "season", "alltime"]:
        f = P / f"leaderboard_{v}.parquet"
        b = add_to_boards(pd.read_parquet(f))
        n = b["hitter_plus"].notna().sum() if "hitter_plus" in b else 0
        print(f"{v}: Hitter+ on {n}/{len(b)}")
        if v == "alltime" and n:
            top = b.dropna(subset=["hitter_plus"]).sort_values("hitter_plus", ascending=False).head(8)
            for _, r in top.iterrows():
                print(f"   {r['name']:22s} Hitter+ {r.hitter_plus:.0f}  (Swing {r.h_swing_part:+.0f} / Dec {r.h_dec_part:+.0f} / B2B {r.h_b2b_part:+.0f})")
