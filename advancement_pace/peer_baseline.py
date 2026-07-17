# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Phases 6-7 — comparison cohort and expected-advancement baseline.

Expected raw pace exists ONLY to peer-adjust an observed historical path; the
target is the player's own observed advancement, never any future outcome.

Joint fixed-effects construction (chosen after two rejected alternatives — a
pure EB cell hierarchy could not hold every margin flat at once with thin deep
cells, and a sequential two-stage fit leaked entry-pathway/age effects back
into the starting-level margin because those categories are correlated; see
reports/07_expected_pace_model.md):

  expected pace = joint least squares on
      one dummy per starting_level x experience_year CELL   (the load-bearing
        interaction: what ladder height a path reaches after N active seasons
        depends strongly and non-linearly on where it started)
    + additive dummies for entry-age bucket, entry-cohort era,
      position group, entry pathway.

  Joint-OLS residuals are orthogonal to every included regressor, so ALL
  cohort margins are flat simultaneously. Rare start x experience cells fit
  their own mean exactly (their members score ~100) — the conservative
  behavior we want for oddball entry types (e.g. AA/AAA foreign-pro entries).

Position group IS in the adjustment: innings-weighted primary MiLB position from
milb_fielding_full covers 99% of scoreable rows (era-correct, not current-listed
position), and unadjusted group effects are systematic and face-valid (catchers
~1.8 public points slower than middle infielders).
"""

import numpy as np
import pandas as pd

K_SHRINK = 25  # EB prior strength (pseudo-observations) for stage-1 cells

AGE_BUCKETS = [(0, 17.5, "<=17"), (17.5, 18.5, "18"), (18.5, 20.5, "19-20"),
               (20.5, 22.5, "21-22"), (22.5, 99, "23+")]
ERA_BUCKETS = [(2009, 2013, "2009-13"), (2014, 2016, "2014-16"),
               (2017, 2019, "2017-19"), (2021, 2030, "2021+")]

ADJUST_COLS = ["age_bucket", "era", "position_group", "entry_pathway"]

REFERENCE_POPULATION = ("starting_level x experience_year cells "
                        "+ additive age/era/position/pathway adjustment")


def age_bucket(age: pd.Series) -> pd.Series:
    out = pd.Series("unknown", index=age.index)
    for lo, hi, lab in AGE_BUCKETS:
        out[(age > lo) & (age <= hi)] = lab
    return out


def era_bucket(cohort: pd.Series) -> pd.Series:
    out = pd.Series("other", index=cohort.index)
    for lo, hi, lab in ERA_BUCKETS:
        out[(cohort >= lo) & (cohort <= hi)] = lab
    return out


def add_cohort_keys(a: pd.DataFrame) -> pd.DataFrame:
    a = a.copy()
    a["age_bucket"] = age_bucket(a.entry_age)
    a["era"] = era_bucket(a.first_meaningful_season)
    return a


def _dummies(a: pd.DataFrame, categories: dict) -> pd.DataFrame:
    """Dummy matrix with FIXED category sets so fit and apply always align."""
    parts = []
    for col, cats in categories.items():
        for c in cats[1:]:  # first category is the reference level
            parts.append((a[col] == c).astype(float).rename(f"{col}::{c}"))
    return pd.concat(parts, axis=1)


class PeerBaseline:
    def __init__(self, measure: str = "area_pace"):
        self.measure = measure

    @staticmethod
    def _cell(a: pd.DataFrame) -> pd.Series:
        return a.starting_level.astype(str) + "|" + a.experience_year.astype(str)

    def fit(self, a: pd.DataFrame):
        fit = a[a.scoreable & a.active].copy()
        m = self.measure
        fit["cell"] = self._cell(fit)

        self.cells = sorted(fit.cell.unique())
        self.categories = {c: sorted(fit[c].astype(str).unique()) for c in ADJUST_COLS}
        self.exp_mean = fit.groupby("experience_year")[m].mean()
        self.global_mean = fit[m].mean()

        # cell block carries the intercept (full one-hot, no reference level);
        # adjustment blocks are drop-first dummies
        C = pd.get_dummies(fit.cell).reindex(columns=self.cells, fill_value=0).astype(float)
        X = _dummies(fit, self.categories)
        Xd = np.column_stack([C.to_numpy(), X.to_numpy()])
        beta, *_ = np.linalg.lstsq(Xd, fit[m].to_numpy(), rcond=None)
        self.beta = beta
        self.x_cols = list(X.columns)
        return self

    def predict(self, a: pd.DataFrame) -> pd.Series:
        cell = self._cell(a)
        C = pd.get_dummies(cell).reindex(columns=self.cells, fill_value=0).astype(float)
        X = _dummies(a, self.categories).reindex(columns=self.x_cols, fill_value=0.0)
        pred = pd.Series(np.column_stack([C.to_numpy(), X.to_numpy()]) @ self.beta,
                         index=a.index)
        # rows whose start x experience cell was never fitted: fall back to the
        # experience-year mean (these rows are outside the scoreable population)
        unseen = ~cell.isin(self.cells)
        pred[unseen] = a.experience_year[unseen].map(self.exp_mean).fillna(self.global_mean)
        return pred


def fit_apply(a: pd.DataFrame, measure: str = "area_pace") -> pd.DataFrame:
    a = a.copy()
    bl = PeerBaseline(measure).fit(a)
    a["expected_peer_pace"] = bl.predict(a)
    a["advancement_residual"] = a[measure] - a.expected_peer_pace
    a["reference_population"] = REFERENCE_POPULATION
    return a


def residual_scale(a: pd.DataFrame, min_n: int = 50) -> pd.Series:
    """Residual SD per experience_year (pooled-shrunk), for standardization."""
    fit = a[a.scoreable & a.active]
    sd = fit.groupby("experience_year").advancement_residual.agg(["std", "size"])
    pooled = fit.advancement_residual.std()
    sd["use"] = np.where(sd["size"] >= min_n, sd["std"], pooled)
    return a.experience_year.map(sd["use"]).fillna(pooled)
