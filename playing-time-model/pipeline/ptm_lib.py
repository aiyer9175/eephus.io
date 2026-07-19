# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Shared pair construction + evaluation for the validation ladder.

Every ladder rung must use build_pairs() so train/test universes stay
identical across modules — Δmetrics are only meaningful on a fixed universe.
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SPINE = "/Users/willcahoon/playing_time_model/data/processed/usage_spine.parquet"

COUNT = ["pa", "games", "gs_total", "g_field_total", "g_c", "g_ss", "g_cf",
         "gs_dh"]
FEATS_A = ["pa_adj", "pa_adj_l1", "pa_adj_l2", "games_adj", "gs_total_adj",
           "gs_total_adj_l1", "g_field_total_adj", "g_c_adj", "g_ss_adj",
           "g_cf_adj", "gs_dh_adj", "n_positions", "premium_pos", "dh_share",
           "age"]
FEATS_B = FEATS_A + ["woba", "woba_marcel", "woba_l1", "obp", "iso",
                     "k_pct", "bb_pct"]
TEST_YEARS = [2023, 2024, 2025]


def prepare_spine():
    """Spine + era scaling + lags + marcel wOBA, all player-seasons."""
    sp = pd.read_parquet(SPINE)
    season_pa = sp.groupby("season").pa.sum()
    full = season_pa[(season_pa.index >= 2000) & (season_pa.index <= 2019)].median()
    sp = sp.merge((full / season_pa).rename("scale"),
                  left_on="season", right_index=True)
    for c in COUNT:
        sp[f"{c}_adj"] = sp[c] * sp.scale

    key = ["mlbam_id", "season"]
    for lag, suf in [(1, "_l1"), (2, "_l2")]:
        lagged = sp[key + ["pa_adj", "gs_total_adj", "woba"]].copy()
        lagged["season"] = lagged.season + lag
        lagged = lagged.rename(columns={c: c + suf for c in
                                        ["pa_adj", "gs_total_adj", "woba"]})
        sp = sp.merge(lagged, on=key, how="left")

    w = (5 * sp.woba.fillna(0) * sp.pa_adj
         + 4 * sp.woba_l1.fillna(0) * sp.pa_adj_l1.fillna(0)
         + 3 * sp.woba_l2.fillna(0) * sp.pa_adj_l2.fillna(0))
    d = (5 * sp.pa_adj + 4 * sp.pa_adj_l1.fillna(0)
         + 3 * sp.pa_adj_l2.fillna(0))
    sp["woba_marcel"] = (w / d.replace(0, np.nan)).fillna(sp.woba)
    return sp


def build_pairs(sp=None):
    """Prediction pairs: feature year t -> target PA in t+1 (0 if absent)."""
    if sp is None:
        sp = prepare_spine()
    key = ["mlbam_id", "season"]
    nxt = sp[key + ["pa"]].rename(columns={"pa": "pa_next"})
    nxt["season"] = nxt.season - 1
    pairs = sp.merge(nxt, on=key, how="left")
    pairs["pa_next"] = pairs.pa_next.fillna(0)
    # feature years 2019/2020 dropped (COVID target/feature), 2025+ dropped
    # (2026 target season in progress)
    pairs = pairs[~pairs.season.isin([2019, 2020, 2025, 2026])]
    return pairs.dropna(subset=["age"]).copy()


def split(pairs):
    train = pairs[pairs.season + 1 <= 2022]
    test = pairs[(pairs.season + 1).isin(TEST_YEARS)]
    return train, test


DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"
DRAFT = "/Users/willcahoon/playing_time_model/data/raw/draft_history.parquet"
MINORS_F = ["pa_aaa_adj", "pa_milb_adj", "woba_aaa", "mlb_share", "shuttle"]
DRAFT_F = ["overall_pick", "log_bonus", "drafted", "years_since_draft",
           "top10_pick", "first_rounder"]


def add_minors(pairs):
    """Rung F' minors-usage features (Module 7)."""
    mn = pd.read_parquet(DEEP_MIN)
    aaa = (mn[mn.sport == 11].groupby(["batter", "season"])
           .agg(pa_aaa=("pa", "sum"), woba_aaa=("woba", "mean")).reset_index())
    allm = (mn.groupby(["batter", "season"]).pa.sum()
              .rename("pa_milb").reset_index())
    mfeat = allm.merge(aaa, on=["batter", "season"], how="left") \
                .rename(columns={"batter": "mlbam_id"})
    pairs = pairs.merge(mfeat, on=["mlbam_id", "season"], how="left")
    pre = pairs.season < 2008
    pairs.loc[~pre, ["pa_milb", "pa_aaa"]] = (
        pairs.loc[~pre, ["pa_milb", "pa_aaa"]].fillna(0))
    pairs["pa_aaa_adj"] = pairs.pa_aaa * pairs.scale
    pairs["pa_milb_adj"] = pairs.pa_milb * pairs.scale
    pairs["mlb_share"] = pairs.pa / (pairs.pa + pairs.pa_milb).replace(0, np.nan)
    pairs["shuttle"] = ((pairs.pa > 0) & (pairs.pa_milb >= 50)).astype(float)
    pairs.loc[pre, "shuttle"] = np.nan
    return pairs


def add_draft(pairs):
    """Rung E2 draft-pedigree features (Module 9)."""
    dr = pd.read_parquet(DRAFT)
    pairs = pairs.merge(dr[["mlbam_id", "draft_year", "overall_pick",
                            "signing_bonus"]], on="mlbam_id", how="left")
    pairs["drafted"] = pairs.draft_year.notna().astype(int)
    pairs["years_since_draft"] = pairs.season - pairs.draft_year
    pairs["log_bonus"] = np.log1p(pairs.signing_bonus)
    pairs["top10_pick"] = (pairs.overall_pick <= 10).astype(int)
    pairs["first_rounder"] = (pairs.overall_pick <= 30).astype(int)
    return pairs


def champion_pairs():
    """Pairs with full champion (rung E2) feature set; returns (pairs, CHAMP)."""
    pairs = add_draft(add_minors(build_pairs()))
    return pairs, FEATS_B + MINORS_F + DRAFT_F


def evaluate(name, preds, t):
    y = t.pa_next.values
    err = preds - y
    r2 = 1 - (err ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(float(r2), 4),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "MAE": round(float(np.abs(err).mean()), 1),
            "Spearman": round(float(spearmanr(preds, y).statistic), 4)}
