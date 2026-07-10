# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Contract-model ML challenger (model-audit Phase 2, WS-2f).

LightGBM quantile heads for guarantee (log-NPV) and years, challenging
the fa_mkt_v2 two-stage OLS champion under "best model wins". Same
stacking hedge as the WAR challenger: the CHAMPION'S OWN predictions ride
as features, so the trees learn its residuals.

  MONOTONIC CONSTRAINTS (owner-approved option, ON): predicted guarantee
  is constrained non-decreasing in the rational-value anchor and the
  comps-median anchor — the two economic primitives a price must respect.
  At n≈1,200 training rows this is the right regularizer.
  NPV BASIS: targets are deferral-adjusted guarantees (WS-2a), identical
  to the champion's Gate-2 v3 protocol.
  POPULATION IDENTITY: the challenger trains/predicts on exactly the
  champion's enriched rows; its internal champion instance also supplies
  comps stats, so neither model sees anything the other can't.

Evaluated by fa_backtest.run_market_gate(challenger=True) — same
forward-chained nine winters, same comps baseline. Ship criterion:
beats the champion's guarantee MAE AND megadeal slice not worse AND
years not worse. The honest prior at this n: OLS may retain."""

from __future__ import annotations

import logging
import math

import numpy as np

import fa_market as fm

log = logging.getLogger(__name__)

ML_MARKET_VERSION = "fa_mkt_lgbm_v1"
SEED = 20260612
GUAR_QUANTILES = (0.10, 0.50, 0.90)

# Feature order matters; monotone constraints are positional.
FEATURES = [
    "age", "war_y1", "war_y1_sq", "age_x_war", "prime_war",
    "pos_sp", "pos_rp", "pos_c", "qo", "supply_z",
    "disc_war_3", "disc_war_5", "disc_war_7", "pt_y1",
    "comps_my", "log_comps_guar", "log_comps_aav",
    "log_rational_at_champ_years",
    "champ_years", "champ_log_guar",
]
_MONOTONE = {"log_comps_guar": 1, "log_rational_at_champ_years": 1}

_PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 25,
    "subsample": 0.9, "subsample_freq": 1,
    "colsample_bytree": 0.9,
    "reg_lambda": 1.0,
    "deterministic": True,
    "force_row_wise": True,
    "n_jobs": 1,
    "random_state": SEED,
    "verbose": -1,
}


class MarketModelML:
    """Drop-in challenger: same constructor and .predict(s) contract as
    fa_market.MarketModel (proj_years / proj_guarantee_usd / proj_aav_usd
    + P10/P90 band keys), NPV basis throughout."""

    def __init__(self, train: list[dict], dpw_series: dict[int, float]):
        from lightgbm import LGBMRegressor
        # The champion supplies comps machinery AND the stacked features.
        self.champ = fm.MarketModel(train, dpw_series)
        self.dpw_series = dpw_series
        rows = self.champ.train_pool
        X = np.asarray([self._features(s) for s in rows], dtype=float)
        y_guar = np.asarray([math.log(fm._npv_of(s)) for s in rows], dtype=float)
        y_years = np.asarray([float(s["years"]) for s in rows], dtype=float)
        mono = [_MONOTONE.get(f, 0) for f in FEATURES]
        # LightGBM forbids monotone constraints under quantile AND L1
        # objectives (leaf-renewal restriction) — the POINT head is L2 on
        # the LOG target (the log already tames the right tail) WITH the
        # economic monotonicity constraints; the band heads are
        # unconstrained quantiles, kept ordered against the point at
        # predict time.
        self.guar_point = LGBMRegressor(objective="regression",
                                        monotone_constraints=mono, **_PARAMS)
        self.guar_point.fit(X, y_guar)
        self.guar_heads = {}
        for q in (0.10, 0.90):
            m = LGBMRegressor(objective="quantile", alpha=q, **_PARAMS)
            m.fit(X, y_guar)
            self.guar_heads[q] = m
        self.years_point = LGBMRegressor(objective="regression", **_PARAMS)
        self.years_point.fit(X, y_years)
        self.years_heads = {}
        for q in (0.10, 0.90):
            m = LGBMRegressor(objective="quantile", alpha=q, **_PARAMS)
            m.fit(X, y_years)
            self.years_heads[q] = m
        self.n_train = len(rows)

    def _features(self, s: dict) -> list[float]:
        g = fm._pos_group(s.get("position"))
        w1 = s["_war_path"]["war_y1"]
        # _comps_stats grew a 4th element (p75 comps years) in the champion's v3
        # my75 addition; a 3-name unpack crashed this challenger before fitting.
        comps_my, log_comps_guar, comps_aav, _comps_my75 = self.champ._comps_stats(s)
        champ_pred = self.champ._point(s)
        champ_years, champ_guar = champ_pred
        dpw = fm.winter_dpw(self.dpw_series, s["class_year"])
        return [
            float(s["_age"]), w1, w1 * w1, s["_age"] * w1,
            self.champ._prime_war(s),
            1.0 if g == "SP" else 0.0, 1.0 if g == "RP" else 0.0,
            1.0 if g == "C" else 0.0, 1.0 if s.get("qo") else 0.0,
            self.champ._supply_z(s),
            fm.disc_war(s["_war_path"], 3), fm.disc_war(s["_war_path"], 5),
            fm.disc_war(s["_war_path"], 7), s["_war_path"].get("pt_y1") or 0.0,
            comps_my, log_comps_guar, math.log(max(comps_aav, 1.0)),
            self.champ._log_rational(s, champ_years, dpw),
            champ_years, math.log(max(champ_guar, 1.0)),
        ]

    def predict(self, s: dict) -> dict:
        x = np.asarray(self._features(s), dtype=float).reshape(1, -1)
        gq = sorted([float(self.guar_heads[0.10].predict(x)[0]),
                     float(self.guar_point.predict(x)[0]),
                     float(self.guar_heads[0.90].predict(x)[0])])
        yq = sorted([float(self.years_heads[0.10].predict(x)[0]),
                     float(self.years_point.predict(x)[0]),
                     float(self.years_heads[0.90].predict(x)[0])])
        guar = math.exp(gq[1])
        years = max(1, int(round(yq[1])))
        return {
            "proj_years": years,
            "proj_years_p10": max(1, int(round(yq[0]))),
            "proj_years_p90": max(1, int(round(yq[2]))),
            "proj_guarantee_usd": int(guar),
            "proj_guarantee_p10_usd": int(math.exp(gq[0])),
            "proj_guarantee_p90_usd": int(math.exp(gq[2])),
            "proj_aav_usd": int(guar / years),
            "proj_aav_p10_usd": int(math.exp(gq[0]) / years),
            "proj_aav_p90_usd": int(math.exp(gq[2]) / years),
            "model": ML_MARKET_VERSION,
        }
