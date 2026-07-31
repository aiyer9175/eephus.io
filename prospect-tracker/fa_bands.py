# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Player-specific band widths for the MLB Free Agency module (T1.2).

WHAT THIS REPLACES

  Gate-1 WAR bands   four reliability buckets (side x exposure hi/lo), each
                     contributing one q10 and one q90 offset. A two-bit
                     approximation to a continuous variance function: a
                     37-year-old coming off 40 innings and a 26-year-old
                     coming off a full season landed in the same bucket if
                     their projected exposure fell on the same side of one
                     threshold.
  Market bands       ONE unconditional residual band. Measured on the served
                     2027 class: projGuarP90 / projGuarP10 = 9.6495 for all
                     221 priced members to six significant figures. Every
                     free agent in baseball was published with the same
                     relative uncertainty.

THE MODEL

  log sigma = z'gamma / 2 over a RESTRICTED z, fit in two steps:

    1. OLS of the residual on z. The point forecast is not guaranteed
       conditionally unbiased, and any leftover conditional mean would be
       absorbed by the scale as spurious variance.
    2. OLS of log(e^2) on z, de-biased by E[log chi2_1] = -1.270363 so that
       exp((z'gamma - E)/2) is a consistent estimator of sigma.

  The SHAPE is then the empirical quantile grid of the standardized residual
  e/sigma, per group (side for WAR, position group for dollars). Empirical,
  not Gaussian, because the residuals are fat-middled: that is the measured
  reason the shipped Gate-1 bands are empirical quantiles in the first place.

  Two-step OLS rather than joint MLE on purpose. It is a closed form, it has
  no convergence mode to babysit inside a nightly pipeline, and on this panel
  it is efficient enough that the measured lift already clears its floor.

MEASURED (Gate-1 WAR bands, 2026-07-25, tools/_fa_bandlab.py, five
forward-chained folds 2021-2025, paired bootstrap B=500 resampling the WHOLE
panel and refitting on every draw):

  metric                 shipped   scale     delta      CI95              MDE95
  pinball avg q10/q90    0.16657   0.15879   -0.00778   [-.01008,-.00558] 0.00229
  CRPS (3-node)          0.42193   0.41428   -0.00766   [-.01173,-.00354] 0.00398
  conditional-cov RMSE   0.10748   0.09763   -0.00985   [-.01702,-.00289] 0.00702
  conditional-cov maxabs 0.22015   0.20078   -0.01937   [-.04474,+.00298] 0.02424
  marginal coverage      0.79047   0.78396   -0.00652   [-.01346,+.00117] 0.00731

  The first three clear their floors (3.4x, 1.9x, 1.4x). The last two are
  NULLS and are reported as nulls.

  ZERO-INFORMATION CONTROL (the same estimator fit on a row-permuted residual
  column, on the identical bootstrap draws): sigma dispersion collapses from
  0.907 to 0.014, i.e. the variance function returns a FLAT sigma exactly as
  it must, and its delta-vs-shipped null band sits at [+0.0229, +0.0281]
  pinball, on the WRONG side of zero and 3x the real effect's magnitude.
"""

from __future__ import annotations

import math
import statistics

BAND_VERSION = "fa_bands_v1"

# E[log(chi2_1)] = digamma(1/2) + log 2
LOGCHI2_1 = -1.2703628454614782

# sigma is clipped into this band. Not a tuning knob: it is a guard against a
# single extrapolated z blowing a served interval to infinity. The default is
# in WAR units; a caller on a LOG-DOLLAR residual must pass its own, because
# sigma 10 there means a p90/p10 ratio of e^25.6, i.e. 1.2e11. Measured
# 2026-07-25 before the clip was made per-model: the guarantee band produced a
# max served p90/p10 of 5.87e9 on the Gate-2 chain.
SIGMA_CLIP = (0.05, 10.0)
# Log-dollar residuals. The flat band it replaces implies sigma
# ln(12.2486)/2.5631 = 0.9776, so this brackets it by a factor of ~2 each way.
SIGMA_CLIP_LOG_USD = (0.35, 2.00)

# The tau grid the standardized-residual SHAPE is stored on.
SHAPE_TAUS = tuple(round(i / 20.0, 2) for i in range(1, 20))    # 0.05..0.95


def _mean(v) -> float:
    v = list(v)
    return math.fsum(float(x) for x in v) / len(v) if v else 0.0


# ============================================================================
# Feature builders (the RESTRICTED z)
# ============================================================================

WAR_Z_NAMES = ("const", "age_c", "age_c2", "is_pit", "log1p_pred",
               "expo", "thin", "tj_n")


def war_z(side: str, pred: float, expo: float, age: float | None,
          thin: float = 0.0, tj_n: float = 0.0,
          age_mean: float = 29.0) -> list[float]:
    """z for the Gate-1 year-1 WAR residual.

    Every term is a quantity a reader could name out loud: how old he is,
    whether he pitches, how good the projection says he is, how much he is
    projected to play, whether the platform season was injury-thin, and how
    many elbow reconstructions are behind him. Deliberately small: the panel
    is roughly 2,000 rows per fold-year and an unrestricted z would fit fold
    noise into the width of a served interval.

    ``thin`` and ``tj_n`` default to 0 so a caller that cannot supply them
    degrades to the healthy, full-platform case rather than erroring. That is
    a documented DIRECTION (bands come out narrower), not a neutral default."""
    a = (float(age) if age is not None else age_mean) - age_mean
    return [1.0, a / 5.0, (a / 5.0) ** 2,
            1.0 if side == "pit" else 0.0,
            math.log1p(max(float(pred), 0.0)),
            min(max(float(expo), 0.0) / 600.0, 2.0),
            float(thin), min(float(tj_n), 2.0)]


GUAR_Z_NAMES = ("const", "age_c", "age_c2", "is_sp", "is_rp", "is_c",
                "log_pred_guar_c", "years", "qo", "tj_n")
LOG_50M = math.log(50e6)


def guar_z(pos_group: str, log_pred_guar: float, years: float,
           age: float | None, qo: float = 0.0, tj_n: float = 0.0,
           age_mean: float = 30.0) -> list[float]:
    """z for the log-guarantee residual of the market model.

    ``years`` is the dollars-side analog of exposure (how much contract is
    being priced), and ``log_pred_guar`` is the log projected value the spec
    names. There is no platform-thinness flag in the signing corpus, so the
    restricted set drops it rather than inventing one.

    log_pred_guar is CENTERED at log($50M) = 17.7275 (the same $50M the mega
    blend uses as its lower hinge) so the intercept is the width of a
    mid-market deal and the slope reads as a per-log-dollar elasticity around
    it. Uncentered, the column sits at 16-20 and the two-step regression is
    badly conditioned."""
    a = (float(age) if age is not None else age_mean) - age_mean
    return [1.0, a / 5.0, (a / 5.0) ** 2,
            1.0 if pos_group == "SP" else 0.0,
            1.0 if pos_group == "RP" else 0.0,
            1.0 if pos_group == "C" else 0.0,
            float(log_pred_guar) - LOG_50M, min(float(years), 15.0) / 5.0,
            float(qo), min(float(tj_n), 2.0)]


# ============================================================================
# Fit / predict
# ============================================================================

def fit(Z: list[list[float]], resid: list[float], groups: list,
        names: tuple = (), age_mean: float = 29.0,
        min_rows: int = 300, min_group: int = 200,
        permute_seed: int | None = None,
        sigma_clip: tuple = SIGMA_CLIP, ridge: float = 0.0) -> dict | None:
    """Two-step location-scale fit. Returns a JSON-serializable model, or
    None when there is not enough material (the caller then keeps whatever
    it was doing before; this never half-fits).

    ``permute_seed`` row-permutes the residual column: the ZERO-INFORMATION
    CONTROL. A correct estimator must return an essentially flat sigma."""
    import numpy as np
    if len(Z) < min_rows:
        return None
    y = list(resid)
    if permute_seed is not None:
        import random
        random.Random(permute_seed).shuffle(y)
    A = np.asarray(Z, dtype=float)
    yv = np.asarray(y, dtype=float)
    beta = _lstsq_ridge(A, yv, ridge)
    e = yv - A @ beta
    gamma = _lstsq_ridge(A, np.log(np.maximum(e * e, 1e-6)), ridge)
    sig = np.clip(np.exp(0.5 * (A @ gamma - LOGCHI2_1)), *sigma_clip)
    u = e / sig
    shape: dict = {}
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(str(g), []).append(float(u[i]))
    for g, vals in by.items():
        if len(vals) >= min_group:
            vals.sort()
            shape[g] = [_emp_q(vals, t) for t in SHAPE_TAUS]
    if not shape:
        return None
    return {"version": BAND_VERSION, "names": list(names),
            "sigma_clip": [float(sigma_clip[0]), float(sigma_clip[1])],
            "ridge": float(ridge),
            "beta": [float(b) for b in beta], "gamma": [float(g) for g in gamma],
            "age_mean": float(age_mean), "n": len(Z),
            "taus": list(SHAPE_TAUS), "shape": shape,
            "shape_fallback": max(shape, key=lambda g: len(by[g])),
            # served-side diagnostics: a flat sigma means the fit found
            # nothing, which is what the permuted control must produce.
            "sigma_mean": float(np.mean(sig)), "sigma_sd": float(np.std(sig))}


def _lstsq_ridge(A, y, ridge: float):
    """OLS, or ridge on STANDARDIZED non-intercept columns.

    The variance step is fit on a few hundred to a few thousand rows. On the
    WAR panel (~20k) that is plenty and ridge 0 is right; on the signing
    corpus (n=1,199 pooled, train folds from 100 rows up) an unregularized
    log(e^2) regression chases fold noise into the width of a published
    interval. Shrinking gamma toward its intercept shrinks sigma toward the
    pooled constant, i.e. toward the flat band it is replacing, which is the
    correct null to shrink to."""
    import numpy as np
    A = np.asarray(A, dtype=float)
    y = np.asarray(y, dtype=float)
    if not ridge:
        b, *_ = np.linalg.lstsq(A, y, rcond=None)
        return b
    mu, sd = A.mean(axis=0), A.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (A - mu) / sd
    Z[:, 0] = 1.0
    lam = ridge * np.eye(Z.shape[1])
    lam[0, 0] = 0.0
    bz = np.linalg.solve(Z.T @ Z + lam * len(y), Z.T @ y)
    b = bz / sd
    b[0] = bz[0] - float(((mu / sd)[1:] * bz[1:]).sum())
    return b


def _emp_q(sorted_vals: list[float], tau: float) -> float:
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    i = tau * (n - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return sorted_vals[lo] + (i - lo) * (sorted_vals[hi] - sorted_vals[lo])


def sigma(model: dict, z: list[float]) -> float:
    """The player's own residual scale."""
    s = math.exp(0.5 * (sum(g * x for g, x in zip(model["gamma"], z)) - LOGCHI2_1))
    lo, hi = model.get("sigma_clip") or SIGMA_CLIP
    return min(max(s, lo), hi)


def location(model: dict, z: list[float]) -> float:
    """The conditional-mean correction the scale step is net of."""
    return sum(b * x for b, x in zip(model["beta"], z))


def offsets(model: dict, z: list[float], group: str,
            taus=(0.10, 0.90)) -> dict[float, float]:
    """{tau: additive offset to the point forecast}.

    Additive by design: every consumer of the old bucket bands added a q10 /
    q90 offset to the year-1 point and decayed the shifted talent along the
    aging curves. Keeping the same shape means the band change is the ONLY
    change, and the aging machinery is untouched."""
    sh = model["shape"].get(str(group)) or model["shape"].get(model["shape_fallback"])
    if not sh:
        return {}
    mu = location(model, z)
    s = sigma(model, z)
    grid = list(model["taus"])
    out = {}
    for t in taus:
        out[float(t)] = mu + s * _interp(grid, sh, float(t))
    return out


def _interp(grid: list[float], vals: list[float], t: float) -> float:
    if t <= grid[0]:
        return vals[0]
    if t >= grid[-1]:
        return vals[-1]
    for (t0, v0), (t1, v1) in zip(zip(grid, vals), zip(grid[1:], vals[1:])):
        if t0 <= t <= t1:
            if t1 == t0:
                return v0
            return v0 + (t - t0) / (t1 - t0) * (v1 - v0)
    return vals[len(vals) // 2]


def width_summary(model: dict, rows: list[tuple[list[float], str]]) -> dict:
    """Served-side honesty check: how much do the widths actually VARY?
    A band model whose p90/p10 ratio is constant to six significant figures
    is the thing being replaced, so the replacement has to publish its own
    dispersion."""
    if not rows:
        return {"n": 0}
    ws = []
    for z, g in rows:
        o = offsets(model, z, g, (0.10, 0.90))
        if o:
            ws.append(o[0.90] - o[0.10])
    if not ws:
        return {"n": 0}
    return {"n": len(ws), "mean": round(_mean(ws), 5),
            "sd": round(statistics.pstdev(ws), 5),
            "min": round(min(ws), 5), "max": round(max(ws), 5),
            "p10": round(_emp_q(sorted(ws), 0.10), 5),
            "p90": round(_emp_q(sorted(ws), 0.90), 5),
            "ratio_max_min": round(max(ws) / min(ws), 4) if min(ws) > 0 else None}
