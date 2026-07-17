# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Phases 8-9 — Advancement Pace+ construction and reliability rules.

  Advancement Pace+ = 100 + 10 x standardized peer-adjusted residual

100 = typical advancement pace for a comparable player; 110 = one standard
unit faster. The scale is standardized-residual based, NOT percentage based.

Public score is shrunk toward 100 for thin samples (k on meaningful
assignments); the raw unshrunk score is retained internally. Display value is
capped 70-130; the uncapped score is retained internally.
"""

import numpy as np
import pandas as pd

from raw_pace import build_asof, load_inputs
from peer_baseline import add_cohort_keys, fit_apply, residual_scale

METHODOLOGY_VERSION = "1.0.0"
MEANINGFUL_PA_THRESHOLD = 30
PRIMARY_MEASURE = "area_pace"   # PA-weighted mean ladder height per active season
K_STABILIZE = 1                 # shrink-toward-100 strength (meaningful assignments)
DISPLAY_CAP = (70, 130)


def sample_quality(a: pd.DataFrame) -> pd.Series:
    tier = pd.Series("Insufficient", index=a.index)
    early = a.active_seasons >= 1
    tier[early] = "Early"
    dev = (a.experience_year >= 2) | (a.meaningful_promotions >= 1)
    tier[early & dev] = "Developing"
    est = (a.experience_year >= 3) & (a.meaningful_assignments >= 3)
    tier[early & est] = "Established"
    return tier


def build_scores(threshold: int = MEANINGFUL_PA_THRESHOLD) -> pd.DataFrame:
    hist, idx = load_inputs()
    a = build_asof(threshold, hist, idx)
    a = add_cohort_keys(a)
    a = fit_apply(a, PRIMARY_MEASURE)

    sd = residual_scale(a)
    a["z_raw"] = a.advancement_residual / sd
    stab = a.meaningful_assignments / (a.meaningful_assignments + K_STABILIZE)
    a["z_stab"] = a.z_raw * stab

    a["advancement_pace_plus_raw"] = 100 + 10 * a.z_raw
    a["advancement_pace_plus"] = 100 + 10 * a.z_stab
    a["advancement_pace_plus_display"] = a.advancement_pace_plus.clip(*DISPLAY_CAP)

    # percentile within reference cohort: same experience year, scoreable peers
    pool = a[a.scoreable & a.active]
    pct = (pool.groupby("experience_year").z_stab
               .rank(pct=True).mul(100).round(0))
    a["advancement_percentile"] = np.nan
    a.loc[pct.index, "advancement_percentile"] = pct

    a["sample_quality"] = sample_quality(a)
    a.loc[a.sample_quality == "Insufficient",
          ["advancement_pace_plus", "advancement_pace_plus_display",
           "advancement_percentile"]] = np.nan

    a["raw_advancement_pace"] = a[PRIMARY_MEASURE]
    a["current_level"] = a.highest_rank.map({1: "Rk", 2: "A", 3: "A+", 4: "AA", 5: "AAA"})
    a["methodology_version"] = METHODOLOGY_VERSION
    return a


if __name__ == "__main__":
    s = build_scores()
    print(s[s.scoreable].advancement_pace_plus.describe().round(2))
