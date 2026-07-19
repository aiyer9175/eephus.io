# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
fix_b2b_proj_intervals.py — add a CALIBRATED forecast interval to Bat-to-Ball+'s
one-year-ahead projection (`bat_to_ball_plus_proj_next`).

Audit finding (Universal Audit Suite, model 3): `proj_next` shipped with no
forecast interval. Using the within-season posterior SD as a proxy covered only
57% of realized next-year values at the nominal 80% level — overconfident by
~1.75x, because the posterior SD captures *measurement* error of this season's
estimate but NOT season-to-season talent movement.

Fix (method of moments): the realized residual variance decomposes as
    Var(realized - proj) = E[posterior_var] + drift_var
so we estimate
    drift_var = mean((realized - proj)^2) - mean(posterior_sd^2)
and set the per-row forecast SD to
    proj_sd = sqrt(posterior_sd^2 + drift_var)        (heteroskedastic; wider for low-sample)
then 80% CI = proj +/- 1.2816 * proj_sd.

drift_var is estimated only from rows with an observed next season, then applied
to every row that has a projection (including the latest season, whose next year
is not yet observed).
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm

Z80 = float(norm.ppf(0.90))  # 1.2816
SHIPPED = Path(__file__).parent / "data" / "processed" / "bat_to_ball_plus.parquet"


def estimate_drift_var(df: pd.DataFrame) -> float:
    """Method-of-moments season-to-season talent-movement variance."""
    nxt = df.rename(columns={"bat_to_ball_plus": "realized"})[["batter", "season", "realized"]].copy()
    nxt["season"] = nxt["season"] - 1
    pj = df[["batter", "season", "bat_to_ball_plus_proj_next", "bat_to_ball_plus_sd"]].merge(
        nxt, on=["batter", "season"]).dropna()
    resid = pj["realized"] - pj["bat_to_ball_plus_proj_next"]
    drift_var = (resid ** 2).mean() - (pj["bat_to_ball_plus_sd"] ** 2).mean()
    return max(0.0, float(drift_var)), pj, resid


def main():
    df = pd.read_parquet(SHIPPED)
    df["season"] = df["season"].astype(int)
    for c in ["bat_to_ball_plus_proj_next", "bat_to_ball_plus_sd"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    drift_var, pj, resid = estimate_drift_var(df)
    drift_sd = drift_var ** 0.5

    # per-row calibrated forecast SD + 80% interval (applied to every row with a projection)
    df["bat_to_ball_plus_proj_next_sd"] = np.sqrt(
        df["bat_to_ball_plus_sd"].fillna(df["bat_to_ball_plus_sd"].median()) ** 2 + drift_var)
    df["bat_to_ball_plus_proj_next_ci_lo"] = df["bat_to_ball_plus_proj_next"] - Z80 * df["bat_to_ball_plus_proj_next_sd"]
    df["bat_to_ball_plus_proj_next_ci_hi"] = df["bat_to_ball_plus_proj_next"] + Z80 * df["bat_to_ball_plus_proj_next_sd"]

    # provenance note so downstream never re-confuses measurement vs forecast SD
    df["proj_next_sd_method"] = f"posterior_sd (+) drift_sd={drift_sd:.2f} (MoM season-to-season)"

    # verify coverage on the observed pairs
    proj_sd_pj = np.sqrt(pj["bat_to_ball_plus_sd"] ** 2 + drift_var)
    z = resid / proj_sd_pj
    print(f"estimated drift SD = {drift_sd:.2f}  (n_pairs={len(pj)})")
    for lvl, zc in [("50%", 0.6745), ("80%", 1.2816), ("90%", 1.6449)]:
        old = (resid.abs() <= zc * pj["bat_to_ball_plus_sd"]).mean()
        new = (z.abs() <= zc).mean()
        print(f"  {lvl} coverage: OLD {100*old:4.0f}%  ->  NEW {100*new:4.0f}%  (target {lvl})")

    df.to_parquet(SHIPPED, index=False)
    print(f"saved {SHIPPED} ({len(df)} rows) with proj_next_sd + 80% CI")


if __name__ == "__main__":
    main()
