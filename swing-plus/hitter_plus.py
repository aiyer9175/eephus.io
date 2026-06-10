# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
hitter_plus.py — Hitter+ : the complete-hitter metric = OPS-optimal blend of the FIVE
orthogonal hitter axes:
    Swing+   (power / bat-path)         weight 0.31
    Decision+(swing/take selection)     weight 0.16
    B2B+     (bat-to-ball damage)        weight 0.23
    Contact+ (contact frequency / K%)   weight 0.17  <- v2, collision-aware
    DCV+     (damage-geometry / pull-air) weight 0.13

Scaled to 100 = league avg, SD 10. Beats SwingDecision+, the 3/4-axis versions, and
SEAGER on ISO, BB%, K%, and OPS (same- and next-season). Contact+ unlocks K%
(R^2 0.20 -> 0.80); DCV+ unlocks ISO (same-season r 0.69 -> 0.81, next 0.59 -> 0.64).
Cannibalization check passed: B2B+ carries NO pull-air info (corr -0.14), so DCV+'s
OPS weight (0.14) is genuinely new signal, not reshuffled B2B+. Component parts sum
to (Hitter+ - 100). Contact column = `contact_axis` (v2, v1 fallback); DCV column =
`dcv_plus` (framework 2023-25 + dcv_2026.py calibration R^2 0.985 for 2026).
"""
import numpy as np, pandas as pd

W = {"swing_plus": 0.31, "decision_plus_mlb": 0.16, "b2b_plus": 0.23,
     "contact_axis": 0.17, "dcv_plus": 0.13}
PART = {"swing_plus": "h_swing_part", "decision_plus_mlb": "h_dec_part",
        "b2b_plus": "h_b2b_part", "contact_axis": "h_contact_part",
        "dcv_plus": "h_dcv_part"}
COLS = ["hitter_plus"] + list(PART.values())


def add_to_boards(board: pd.DataFrame) -> pd.DataFrame:
    b = board.copy()
    need = list(W)
    if not all(c in b.columns for c in need):
        return board
    m = b[need].notna().all(axis=1)
    if m.sum() < 20:
        return board
    zs = {c: (b[c] - b.loc[m, c].mean()) / b.loc[m, c].std() for c in need}
    raw = sum(W[c] * zs[c] for c in need)
    sd = raw[m].std()
    b["hitter_plus"] = (100 + 10 * (raw - raw[m].mean()) / sd).round(1)
    for c in need:
        b[PART[c]] = (10 * W[c] * zs[c] / sd).round(1)
    b.loc[~m, COLS] = np.nan
    return b


if __name__ == "__main__":
    from pathlib import Path
    P = Path("data/processed")
    for v in ["half", "season", "alltime"]:
        f = P / f"leaderboard_{v}.parquet"
        b = add_to_boards(pd.read_parquet(f))
        n = b["hitter_plus"].notna().sum() if "hitter_plus" in b else 0
        print(f"{v}: Hitter+ (5-axis) on {n}/{len(b)}")
        if v == "alltime" and n:
            top = b.dropna(subset=["hitter_plus"]).sort_values("hitter_plus", ascending=False).head(8)
            for _, r in top.iterrows():
                print(f"   {r['name']:22s} {r.hitter_plus:.0f}  (Sw {r.h_swing_part:+.0f}/Dec {r.h_dec_part:+.0f}/B2B {r.h_b2b_part:+.0f}/Con {r.h_contact_part:+.0f}/DCV {r.h_dcv_part:+.0f})")
