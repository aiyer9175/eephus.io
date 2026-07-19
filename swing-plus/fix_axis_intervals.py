# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
fix_axis_intervals.py — batched Universal-Audit fixes for the skill axes.

(1) DCV+ / Damage+ ships NO uncertainty. Add an EB posterior SD + 80% credible
    interval from its shrinkage constant (k=100 BIP):
        reliability_i = n_bip_i / (n_bip_i + 100)
        sd_i          = SCALE * sqrt(1 - reliability_i)     (SCALE = 10, the 100±10 unit)
    so a full-sample hitter gets a tight band and a low-BIP hitter a wide one —
    consistent with how Swing+/B2B+/Contact+ already behave.

(2) Contact+ ships a WITHIN-SEASON credible interval (cred80) that only covers
    ~69% of next-year values — fine as a talent interval, under-covering as a
    forecast. Add an explicit calibrated FORECAST interval (drift term, same
    method-of-moments as the B2B+ fix) and label cred80 as within-season.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm

Z80 = float(norm.ppf(0.90))  # 1.2816
SWING = Path(__file__).parent / "data" / "processed"
DCV = SWING / "dcv_plus.parquet"
CONTACT = Path.home() / "contact_plus" / "data" / "processed" / "contact_plus.parquet"


def fix_dcv():
    d = pd.read_parquet(DCV)
    SCALE = 10.0
    rel = d["n_bip"] / (d["n_bip"] + 100.0)              # k = 100 BIP (build constant)
    d["dcv_plus_sd"] = (SCALE * np.sqrt(1.0 - rel)).round(2)
    d["dcv_plus_reliability"] = rel.round(3)
    d["dcv_plus_cred80_lo"] = (d["dcv_plus"] - Z80 * d["dcv_plus_sd"]).round(1)
    d["dcv_plus_cred80_hi"] = (d["dcv_plus"] + Z80 * d["dcv_plus_sd"]).round(1)
    d.to_parquet(DCV, index=False)
    print(f"[DCV+] added posterior SD + 80% credible interval "
          f"(sd median {d['dcv_plus_sd'].median():.1f}); saved {DCV.name} ({len(d)} rows)")


def fix_contact():
    if not CONTACT.exists():
        print(f"[Contact+] {CONTACT} missing — skipped"); return
    c = pd.read_parquet(CONTACT)
    c["season"] = c["season"].astype(int)
    # drift estimate from realized next-year residuals (method of moments)
    nxt = c.rename(columns={"contact_plus": "realized"})[["batter", "season", "realized"]].copy()
    nxt["season"] = nxt["season"] - 1
    pj = c[["batter", "season", "contact_plus", "contact_plus_sd"]].merge(nxt, on=["batter", "season"]).dropna()
    resid = pj["realized"] - pj["contact_plus"]
    drift_var = max(0.0, float((resid ** 2).mean() - (pj["contact_plus_sd"] ** 2).mean()))
    c["contact_plus_fcast_sd"] = np.sqrt(c["contact_plus_sd"] ** 2 + drift_var).round(2)
    c["contact_plus_fcast_lo"] = (c["contact_plus"] - Z80 * c["contact_plus_fcast_sd"]).round(1)
    c["contact_plus_fcast_hi"] = (c["contact_plus"] + Z80 * c["contact_plus_fcast_sd"]).round(1)
    c["interval_note"] = "cred80 = within-season talent; fcast = calibrated next-year forecast"
    # verify forecast coverage
    proj_sd = np.sqrt(pj["contact_plus_sd"] ** 2 + drift_var)
    cov = (resid.abs() <= Z80 * proj_sd).mean()
    c.to_parquet(CONTACT, index=False)
    print(f"[Contact+] added forecast interval (drift SD {drift_var**0.5:.2f}); "
          f"forecast 80% coverage {100*cov:.0f}% (was 69% cred80); saved {CONTACT.name}")


if __name__ == "__main__":
    fix_dcv()
    fix_contact()
