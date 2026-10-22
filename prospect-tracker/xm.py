# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xM$ (Expected Market $): what the free-agent market would pay a player this
winter, as AAV, years and total guarantee with a P10 to P90 band.

Registered in docs/xm/XM_GATE.md (model id ``xm``, owner decisions XM-1 to
XM-4 of 2026-10-19) before any of this code existed. The producer is
tools/xm_lab.py; it writes data/xm_eval.json. Nothing served reads this module
yet: XM_2 consumes the selected model.

GENERALIZED, NOT FORKED. The served /fa/ machinery in fa_market.py is reused,
never copied: the as-of WAR path (fa_market.contract_war_path on
fa_projection.fitted_models), the implied $/WAR series
(fa_market.dollars_per_war_by_winter), the incumbent price model
(fa_market.MarketModel, candidate (a)) and the rational value behind Fair $
(fa_market.expected_rational_value_usd).

This module holds pure functions and the two challenger model classes:
  dpw_index            the one-step random-walk-with-drift $/WAR index
  static_features      the per-row as-of features of gate section 4
  feature_vector       the fold-dependent design row
  Hurdle               candidate (b): P(MLB deal) logit, ordered-logit years,
                       Tobit log AAV given years (left-censored at the minimum)
  GBM                  candidate (c): monotone gradient boosting
  Null1                the naive comparator: platform WAR x index x years by age
  support_box, clip_to_support, prospect_path, fair_value_usd
  metrics, cluster_lo95
Every random draw takes SEED (20261019) unless a caller passes its own.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict

import numpy as np

SEED = 20261019
MODEL_VERSION = "xm_v1"
WARMUP_THROUGH = 2017
DEV_WINTERS = tuple(range(2018, 2025))
HOLDOUT_WINTERS = (2025, 2026)
SERVE_WINTER = 2027
DEMAND_ROOM_USD = 20_000_000
YEAR_CATS = 7                     # categories 1..6 and "7 or more"
RIDGE = 1.0
LOG_TOTAL_FLOOR = math.log(1.0)
MAX_YEARS = 15.0
BAND_TARGET = (0.75, 0.85)        # dev coverage window before the conformal switch
AGE_BANDS = ((0, 27), (28, 29), (30, 31), (32, 33), (34, 99))

# Gate section 4, in design order. Fold-dependent names are filled by
# feature_vector; the rest come from static_features.
FEATURES = ("age", "war_y1", "war_3", "war_tot", "plat_war", "war_3y",
            "pos_sp", "pos_rp", "pos_c", "pos_prem", "gs_share",
            "il_prior1", "il_3y", "qo", "supply_z", "demand",
            "log_index", "log_rational3")
WAR_FEATURES = ("war_y1", "war_3", "war_tot", "plat_war", "war_3y", "log_rational3")
_PREMIUM = {"SS", "2B", "3B", "CF"}


# ============================================================================
# $/WAR index (gate section 4): one-step random walk with drift, ex ante
# ============================================================================

def dpw_index(series: dict, winter: int, flat_usd: float | None = None) -> float:
    """The market-clearing $/WAR index for ``winter`` from the winters STRICTLY
    before it: log d(W) = log d(W-1) + mean prior log difference. One prior
    winter carries forward with no drift; none returns ``flat_usd`` (the caller
    passes fa_class._flat_dpw_usd()). A winter never sees its own or a later
    winter's prices."""
    prior = sorted((int(y), float(v)) for y, v in series.items()
                   if int(y) < int(winter) and v and float(v) > 0)
    if not prior:
        if flat_usd is None:
            raise ValueError("dpw_index: no prior winter and no flat fallback")
        return float(flat_usd)
    logs = [math.log(v) for _, v in prior]
    steps = [(logs[i] - logs[i - 1]) / max(prior[i][0] - prior[i - 1][0], 1)
             for i in range(1, len(logs))]
    drift = statistics.mean(steps) if steps else 0.0
    last_y, _ = prior[-1]
    return math.exp(logs[-1] + drift * (int(winter) - last_y))


# ============================================================================
# Features
# ============================================================================

def pos_flags(position: str | None) -> dict:
    """SP / RP / C / premium (SS, 2B, 3B, CF) dummies; corner and DH are the
    base. The group is fa_market._pos_group's, so 'SP/SP2' is SP and 'RP/CL'
    is RP exactly as the incumbent reads them."""
    import fa_market as fm
    g = fm._pos_group(position)
    head = (position or "").upper().split("/")[0].strip()
    return {"pos_sp": 1.0 if g == "SP" else 0.0, "pos_rp": 1.0 if g == "RP" else 0.0,
            "pos_c": 1.0 if g == "C" else 0.0,
            "pos_prem": 1.0 if (g == "POS" and head in _PREMIUM) else 0.0}


def disc_war(path_years: list, n: int, rate: float) -> float:
    return sum(float(w) / ((1 + rate) ** t) for t, w in enumerate(list(path_years)[:n]))


def static_features(*, age, war_by_year, side, position, qo, seasons: dict,
                    il_seasons: dict, winter: int, demand: float,
                    disc_rate: float) -> dict:
    """The as-of features of gate section 4 that do not depend on the fold.

    ``seasons`` maps season -> projection-corpus row for this player and side
    (only seasons before ``winter`` are read); ``il_seasons`` maps season ->
    (il_days, il_stints)."""
    wy = [float(w) for w in (war_by_year or [])]
    seasons = seasons or {}
    il_seasons = il_seasons or {}
    prior = [seasons.get(winter - k) for k in (1, 2, 3)]
    plat = float((prior[0] or {}).get("war") or 0.0)
    war3y = sum(float((r or {}).get("war") or 0.0) for r in prior)
    gs = 0.0
    if side == "pit":
        bf_sp = sum(float((r or {}).get("bf") or 0.0) for r in prior
                    if r and r.get("role") == "SP")
        bf = sum(float((r or {}).get("bf") or 0.0) for r in prior if r)
        gs = bf_sp / bf if bf > 0 else 0.0
    il1 = float((il_seasons.get(winter - 1) or (0.0, 0))[0])
    il3 = sum(float((il_seasons.get(winter - k) or (0.0, 0))[0]) for k in (1, 2, 3))
    out = {"age": float(age), "war_y1": wy[0] if wy else 0.0,
           "war_3": sum(wy[:3]), "war_tot": sum(wy),
           "plat_war": plat, "war_3y": war3y, "gs_share": gs,
           "il_prior1": il1, "il_3y": il3, "qo": 1.0 if qo else 0.0,
           "demand": float(demand), "disc3": disc_war(wy, 3, disc_rate)}
    out.update(pos_flags(position))
    return out


def feature_vector(st: dict, index_usd: float, supply_z: float) -> list:
    """The design row in FEATURES order for one fold."""
    li = math.log(max(float(index_usd), 1e5))
    lr = math.log(max(max(st["disc3"], 0.25) * float(index_usd), 1e6))
    full = dict(st, supply_z=float(supply_z), log_index=li, log_rational3=lr)
    return [float(full[k]) for k in FEATURES]


def demand_count(tax_payroll_prev: dict, threshold_usd: float,
                 room_usd: float = DEMAND_ROOM_USD) -> int:
    """Clubs whose prior-season tax payroll sits at least ``room_usd`` below the
    winter's CBT threshold. Clubs with no value are not counted."""
    return sum(1 for v in tax_payroll_prev.values()
               if v and float(v) <= float(threshold_usd) - float(room_usd))


def age_band(age: float) -> int:
    for i, (lo, hi) in enumerate(AGE_BANDS):
        if lo <= int(age) <= hi:
            return i
    return len(AGE_BANDS) - 1


def year_cat(years: float) -> int:
    """0-based ordinal category: 1..6 years -> 0..5, 7 or more -> 6."""
    return int(min(max(int(round(float(years))), 1), YEAR_CATS) - 1)


# ============================================================================
# Linear building blocks (standardized ridge; penalty 0.5 * RIDGE * |b_z|^2)
# ============================================================================

class _Std:
    def __init__(self, X: np.ndarray):
        self.mu = X.mean(axis=0)
        sd = X.std(axis=0)
        sd[sd < 1e-12] = 1.0
        self.sd = sd

    def __call__(self, X: np.ndarray) -> np.ndarray:
        return (np.asarray(X, dtype=float) - self.mu) / self.sd


def tobit_fit(Z: np.ndarray, y: np.ndarray, cens: np.ndarray, floor: np.ndarray,
              ridge: float = RIDGE) -> tuple[np.ndarray, float]:
    """Left-censored normal regression by maximum likelihood.

    Z: standardized design WITHOUT intercept (the intercept is added and not
    penalized). y: observed log values (ignored where cens). cens: bool, the
    latent value is below ``floor``. Returns (beta with intercept first, sigma)."""
    from scipy.optimize import minimize
    from scipy.special import log_ndtr
    A = np.column_stack([np.ones(len(Z)), Z])
    obs = ~cens
    k = A.shape[1]
    b0 = np.zeros(k + 1)
    if obs.any():
        b0[0] = float(np.mean(y[obs]))
        b0[-1] = math.log(max(float(np.std(y[obs])), 0.1))

    def f(p):
        b, ls = p[:k], p[k]
        s = math.exp(ls)
        mu = A @ b
        g = np.zeros(k)
        nll = 0.0
        gls = 0.0
        if obs.any():
            z = (y[obs] - mu[obs]) / s
            nll += float(0.5 * (z ** 2).sum() + ls * obs.sum())
            g += -(A[obs].T @ (z / s))
            gls += float((1.0 - z ** 2).sum())
        if cens.any():
            a = (floor[cens] - mu[cens]) / s
            lphi = -0.5 * a ** 2 - 0.5 * math.log(2 * math.pi)
            lPhi = log_ndtr(a)
            lam = np.exp(lphi - lPhi)
            nll += float(-lPhi.sum())
            g += A[cens].T @ (lam / s)
            gls += float((lam * a).sum())
        nll += 0.5 * ridge * float((b[1:] ** 2).sum())
        g[1:] += ridge * b[1:]
        return nll, np.concatenate([g, [gls]])

    res = minimize(f, b0, jac=True, method="L-BFGS-B",
                   options={"maxiter": 2000, "gtol": 1e-8})
    return res.x[:k], math.exp(res.x[k])


def ordered_logit_fit(Z: np.ndarray, ycat: np.ndarray, K: int = YEAR_CATS,
                      ridge: float = RIDGE) -> tuple[np.ndarray, np.ndarray]:
    """Proportional-odds logit: P(y <= j) = F(theta_j - Z b). Returns (b,
    theta). Categories absent from the training rows still get a cutpoint
    (the increments are bounded below by exp, so theta stays ordered)."""
    from scipy.optimize import minimize
    from scipy.special import expit
    n, k = Z.shape
    y = np.asarray(ycat, dtype=int)

    def unpack(p):
        b = p[:k]
        a = p[k:]
        th = np.cumsum(np.concatenate([[a[0]], np.exp(a[1:])]))
        return b, a, th

    def f(p):
        b, a, th = unpack(p)
        eta = Z @ b
        thp = np.concatenate([[-np.inf], th, [np.inf]])
        up = thp[y + 1] - eta
        lo = thp[y] - eta
        Fu = np.where(np.isfinite(up), expit(up), 1.0)
        Fl = np.where(np.isfinite(lo), expit(lo), 0.0)
        pr = np.clip(Fu - Fl, 1e-300, None)
        fu = Fu * (1 - Fu)
        fl = Fl * (1 - Fl)
        nll = float(-np.log(pr).sum()) + 0.5 * ridge * float((b ** 2).sum())
        gb = Z.T @ ((fu - fl) / pr) + ridge * b
        # d nll / d theta_j
        gth = np.zeros(K - 1)
        for j in range(K - 1):
            m_up = (y == j)            # theta_j is the upper edge of category j
            m_lo = (y == j + 1)        # and the lower edge of category j + 1
            gth[j] = -float((fu[m_up] / pr[m_up]).sum()) + float((fl[m_lo] / pr[m_lo]).sum())
        # chain rule to the unconstrained a
        ga = np.zeros(K - 1)
        ga[0] = gth.sum()
        for m in range(1, K - 1):
            ga[m] = math.exp(a[m]) * gth[m:].sum()
        return nll, np.concatenate([gb, ga])

    counts = np.bincount(y, minlength=K).astype(float) + 0.5
    cum = np.cumsum(counts)[:-1] / counts.sum()
    th0 = np.log(cum / (1 - cum))
    a0 = np.concatenate([[th0[0]], np.log(np.maximum(np.diff(th0), 1e-3))])
    res = minimize(f, np.concatenate([np.zeros(k), a0]), jac=True, method="L-BFGS-B",
                   options={"maxiter": 2000, "gtol": 1e-8})
    b, _, th = unpack(res.x)
    return b, th


def ordered_probs(Z: np.ndarray, b: np.ndarray, th: np.ndarray) -> np.ndarray:
    from scipy.special import expit
    eta = Z @ b
    cdf = expit(th[None, :] - eta[:, None])
    cdf = np.column_stack([np.zeros(len(eta)), cdf, np.ones(len(eta))])
    return np.clip(np.diff(cdf, axis=1), 0.0, 1.0)


def truncated_median(mu, sigma: float, floor):
    """Median of N(mu, sigma) truncated below at ``floor`` (vectorized). The
    point given an MLB deal: the latent price is known to clear the floor."""
    from scipy.special import ndtr, ndtri
    mu = np.asarray(mu, dtype=float)
    a = (np.asarray(floor, dtype=float) - mu) / sigma
    tail = ndtr(-a)                          # P(latent above floor)
    tail = np.clip(tail, 1e-300, 1.0)
    return mu - sigma * ndtri(0.5 * tail)


# ============================================================================
# Candidate (b): the hurdle model
# ============================================================================

def _years_design(F: np.ndarray) -> np.ndarray:
    age = F[:, FEATURES.index("age")]
    return np.column_stack([F, (age - 30.0) ** 2])


def _aav_design(F: np.ndarray, log_years: np.ndarray) -> np.ndarray:
    return np.column_stack([_years_design(F), log_years])


class Hurdle:
    """Candidate (b), gate section 5. Fit on MLB rows (F_mlb, years, log AAV)
    and floor rows (F_floor, log floor)."""

    name = "b_hurdle"

    def fit(self, F_mlb: np.ndarray, years: np.ndarray, log_aav: np.ndarray,
            F_floor: np.ndarray, log_floor_floor: np.ndarray,
            log_floor_mlb: np.ndarray, ridge: float = RIDGE) -> "Hurdle":
        from sklearn.linear_model import LogisticRegression
        F_mlb = np.asarray(F_mlb, dtype=float)
        F_floor = np.asarray(F_floor, dtype=float).reshape(-1, F_mlb.shape[1])
        # (i) P(guaranteed MLB deal)
        Fa = np.vstack([F_mlb, F_floor])
        lab = np.concatenate([np.ones(len(F_mlb)), np.zeros(len(F_floor))])
        self.std_p = _Std(Fa)
        self.p_model = None
        if len(F_floor) >= 5:
            self.p_model = LogisticRegression(C=1.0 / ridge, max_iter=5000).fit(
                self.std_p(Fa), lab)
        self.p_const = float(lab.mean())
        # (ii) ordinal years
        Xy = _years_design(F_mlb)
        self.std_y = _Std(Xy)
        ycat = np.array([year_cat(v) for v in years])
        self.b_y, self.th_y = ordered_logit_fit(self.std_y(Xy), ycat, ridge=ridge)
        top = [float(v) for v in years if year_cat(v) == YEAR_CATS - 1]
        self.top_years = statistics.mean(top) if top else float(YEAR_CATS)
        # (iii) Tobit log AAV given log years
        ly_mlb = np.log(np.asarray(years, dtype=float))
        ly_floor = np.zeros(len(F_floor))                  # floor rows: 1 year
        Xa = np.vstack([_aav_design(F_mlb, ly_mlb), _aav_design(F_floor, ly_floor)])
        self.std_a = _Std(Xa)
        yv = np.concatenate([np.asarray(log_aav, dtype=float), np.asarray(log_floor_floor, dtype=float)])
        cens = np.concatenate([np.zeros(len(F_mlb), bool), np.ones(len(F_floor), bool)])
        floor = np.concatenate([np.asarray(log_floor_mlb, dtype=float),
                                np.asarray(log_floor_floor, dtype=float)])
        self.b_a, self.sigma = tobit_fit(self.std_a(Xa), yv, cens, floor, ridge=ridge)
        return self

    def p_mlb(self, F: np.ndarray) -> np.ndarray:
        F = np.asarray(F, dtype=float)
        if self.p_model is None:
            return np.full(len(F), self.p_const)
        return self.p_model.predict_proba(self.std_p(F))[:, 1]

    def predict(self, F: np.ndarray, log_floor: np.ndarray) -> dict:
        F = np.asarray(F, dtype=float)
        P = ordered_probs(self.std_y(_years_design(F)), self.b_y, self.th_y)
        cum = np.cumsum(P, axis=1)
        cat = np.argmax(cum >= 0.5, axis=1)
        years_f = np.where(cat == YEAR_CATS - 1, self.top_years, cat + 1.0)
        Xa = _aav_design(F, np.log(years_f))
        mu = self.b_a[0] + self.std_a(Xa) @ self.b_a[1:]
        log_aav = truncated_median(mu, self.sigma, log_floor)
        return {"years_f": years_f, "log_total": log_aav + np.log(years_f)}


# ============================================================================
# Candidate (c): monotone gradient boosting
# ============================================================================

GBM_PARAMS = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                  min_samples_leaf=20, l2_regularization=1.0,
                  early_stopping=False, random_state=SEED)


def monotone_cst(names, stage: str) -> list:
    out = []
    for n in names:
        if n in WAR_FEATURES:
            out.append(1)
        elif n == "age" and stage == "years":
            out.append(-1)
        else:
            out.append(0)
    return out


class GBM:
    """Candidate (c), gate section 5. Fit on MLB rows only."""

    name = "c_gbm"

    def fit(self, F_mlb: np.ndarray, years: np.ndarray, log_aav: np.ndarray,
            seed: int = SEED) -> "GBM":
        from sklearn.ensemble import HistGradientBoostingRegressor
        F = np.asarray(F_mlb, dtype=float)
        params = dict(GBM_PARAMS, random_state=seed)
        ly = np.log(np.asarray(years, dtype=float))
        self.m_years = HistGradientBoostingRegressor(
            monotonic_cst=monotone_cst(FEATURES, "years"), **params).fit(F, ly)
        self.m_aav = HistGradientBoostingRegressor(
            monotonic_cst=monotone_cst(FEATURES + ("log_years",), "aav"), **params
        ).fit(np.column_stack([F, ly]), np.asarray(log_aav, dtype=float))
        return self

    def predict(self, F: np.ndarray, log_floor=None) -> dict:
        F = np.asarray(F, dtype=float)
        years_f = np.clip(np.exp(self.m_years.predict(F)), 1.0, MAX_YEARS)
        la = self.m_aav.predict(np.column_stack([F, np.log(years_f)]))
        return {"years_f": years_f, "log_total": la + np.log(years_f)}


# ============================================================================
# NULL 1 and the constant comparator (gate section 8)
# ============================================================================

class Null1:
    """total = years_age x max(league minimum, max(plat_war, 0) x index)."""

    name = "null1"

    def fit(self, ages, years) -> "Null1":
        by = defaultdict(list)
        for a, y in zip(ages, years):
            by[age_band(a)].append(float(y))
        allv = [float(y) for y in years]
        self.years_by_band = {b: statistics.median(by[b]) if by[b] else statistics.median(allv)
                              for b in range(len(AGE_BANDS))}
        return self

    def predict(self, ages, plat_war, index_usd, league_min) -> dict:
        yrs = np.array([self.years_by_band[age_band(a)] for a in ages], dtype=float)
        per = np.maximum(np.asarray(league_min, dtype=float),
                         np.maximum(np.asarray(plat_war, dtype=float), 0.0)
                         * np.asarray(index_usd, dtype=float))
        return {"years_f": yrs, "log_total": np.log(per * yrs)}


def band_quantiles(resid) -> tuple[float, float]:
    """P10 and P90 of log-total residuals (actual - point)."""
    r = np.asarray(resid, dtype=float)
    if len(r) < 20:
        return (-1.0, 1.0)
    return float(np.quantile(r, 0.10)), float(np.quantile(r, 0.90))


def apply_band(log_point, q: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """P10 <= P50 <= P90 by construction (the quantiles are clamped around 0)."""
    p = np.asarray(log_point, dtype=float)
    lo, hi = min(q[0], 0.0), max(q[1], 0.0)
    return p + lo, p + hi


# ============================================================================
# Scoring (gate section 7)
# ============================================================================

def pinball(y, q, tau: float) -> np.ndarray:
    d = np.asarray(y, dtype=float) - np.asarray(q, dtype=float)
    return np.maximum(tau * d, (tau - 1.0) * d)


def metrics(y_log, p50, p10, p90, years_pred, years_act) -> dict:
    y = np.asarray(y_log, dtype=float)
    p50 = np.asarray(p50, dtype=float)
    if len(y) == 0:
        return {"n": 0}
    pb = {t: float(pinball(y, q, t).mean()) for t, q in ((0.1, p10), (0.5, p50), (0.9, p90))}
    yp = np.maximum(np.rint(np.asarray(years_pred, dtype=float)), 1)
    ya = np.asarray(years_act, dtype=float)
    cov = float(((y >= np.asarray(p10)) & (y <= np.asarray(p90))).mean())
    return {"n": int(len(y)), "log_total_mae": float(np.abs(y - p50).mean()),
            "pinball_p10": pb[0.1], "pinball_p50": pb[0.5], "pinball_p90": pb[0.9],
            "crps_proxy": float(statistics.mean(pb.values())),
            "coverage_p10_p90": cov,
            "years_exact": float((yp == ya).mean()),
            "years_within_one": float((np.abs(yp - ya) <= 1).mean())}


def bootstrap_weights(draws: np.ndarray, C: int) -> np.ndarray:
    """How many times each of the C clusters is drawn in each bootstrap
    replicate (one row of ``draws`` per replicate), as a float (B, C) matrix.

    One flat bincount over replicate * C + cluster. It replaces an
    ``np.add.at`` fancy-index accumulation: the first xM$ read died with a
    native access violation (exit 139, no traceback) right after the
    development bootstraps, and this interpreter has recorded access
    violations in numpy fancy-index assignment inside long bootstrap loops
    (tools/efv_rank_objective_lab.py, tools/ba_tool_grade_lab.py). The counts
    are integers, so the two forms are exactly equal (test_xm pins it)."""
    draws = np.asarray(draws, dtype=np.int64)
    B = draws.shape[0]
    flat = (np.arange(B, dtype=np.int64)[:, None] * C + draws).ravel()
    return np.bincount(flat, minlength=B * C).reshape(B, C).astype(float)


def cluster_lo95(err_cmp, err_cand, clusters, B: int = 4000, seed: int = SEED) -> dict:
    """Paired improvement MAE(comparator) - MAE(candidate) with a player-
    clustered bootstrap. Returns the point, the one-sided 95 percent lower
    bound (5th percentile) and the two-sided 95 percent interval."""
    a = np.asarray(err_cmp, dtype=float)
    c = np.asarray(err_cand, dtype=float)
    ids = {}
    cl = np.array([ids.setdefault(k, len(ids)) for k in clusters])
    C = len(ids)
    if C == 0:
        return {"n": 0, "clusters": 0, "delta": None, "lo95_one_sided": None}
    sa = np.bincount(cl, weights=a, minlength=C)
    sc = np.bincount(cl, weights=c, minlength=C)
    nn = np.bincount(cl, minlength=C).astype(float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, C, size=(B, C))
    W = bootstrap_weights(draws, C)
    den = W @ nn
    d = (W @ sa - W @ sc) / den
    return {"n": int(len(a)), "clusters": int(C),
            "delta": float(a.mean() - c.mean()),
            "lo95_one_sided": float(np.quantile(d, 0.05)),
            "ci95": [float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))],
            "B": int(B), "seed": int(seed)}


# ============================================================================
# Counterfactual extension (gate section 11)
# ============================================================================

def support_box(rows_static: list[dict]) -> dict:
    """[min, max] of age, war_y1 and war_tot over the training rows."""
    box = {}
    for k in ("age", "war_y1", "war_tot"):
        vals = [float(r[k]) for r in rows_static]
        box[k] = [min(vals), max(vals)]
    return box


def clip_to_support(age: float, war_by_year: list, box: dict) -> tuple[float, list, bool]:
    """Clip age into the box and scale the WAR path DOWN so war_y1 and war_tot
    fall inside it. Returns (age, path, outside_support). A path whose year 1
    or total sits below the box's floor is flagged and left as is (scaling a
    short path up would invent production)."""
    wy = [float(w) for w in war_by_year]
    out = False
    a = float(age)
    lo, hi = box["age"]
    if a < lo or a > hi:
        out = True
        a = min(max(a, lo), hi)
    y1, tot = (wy[0] if wy else 0.0), sum(wy)
    f = 1.0
    if y1 > box["war_y1"][1] and y1 > 0:
        f = min(f, box["war_y1"][1] / y1)
    if tot > box["war_tot"][1] and tot > 0:
        f = min(f, box["war_tot"][1] / tot)
    if f < 1.0:
        out = True
        wy = [w * f for w in wy]
    if y1 < box["war_y1"][0] or tot < box["war_tot"][0]:
        out = True
    return a, wy, out


def prospect_path(war_6yr: float, eta_season: int | None, age_in_winter: float,
                  winter: int = SERVE_WINTER, n_years: int = 15) -> list[float]:
    """The eFV WAR path of gate section 11: ``war_6yr`` (expected six-season
    WAR, reach probability included) spread evenly over the six seasons from
    the ETA season, zero before it; the six-season level held until age 30,
    then walked down 0.5 WAR a season (floored at 0)."""
    level = max(float(war_6yr or 0.0), 0.0) / 6.0
    eta = int(eta_season) if eta_season else int(winter)
    eta = max(eta, int(winter))
    out = []
    for t in range(n_years):
        season = int(winter) + t
        age = float(age_in_winter) + t
        if season < eta:
            out.append(0.0)
        elif season < eta + 6 or age <= 30:
            out.append(level)
        else:
            out.append(max(0.0, level - 0.5 * (age - 30.0)))
    return out


def fair_value_usd(war_path: dict, years: int, class_year: int, dpw_usd: float,
                   infl: float | None = None) -> int:
    """Fair $ (XM-1): fa_market's rational value on the same WAR path at the
    xM$ point term. Reused, never re-implemented."""
    import fa_market as fm
    return int(fm.expected_rational_value_usd(war_path, max(1, int(years)), class_year,
                                              dpw_usd, infl=infl))
