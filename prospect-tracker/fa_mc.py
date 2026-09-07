# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Correlated-path Monte Carlo for the MLB Free Agency module (T1.3 / T1.4).

TWO DEFECTS THIS REPLACES

  SUM OF QUANTILES.  warTotalP10 was round(sum(per-year P10)) and warTotalP90
  the same for the upper band, for 221 of 221 priced 2027 members. Adding
  quantiles is only valid under COMONOTONICITY, i.e. the assumption that a
  player who lands at his 10th percentile in year 1 lands at his 10th
  percentile in every remaining year. Measured horizon residual Spearman
  (tools/_fa_rho.py, 7 anchored forward-chained cohorts, n = 13,923 paths,
  39,664 lag-1 pairs): 0.4455 at lag 1, 0.3594 at lag 2, 0.3090 at lag 3,
  0.2571 at lag 4. Real paths are correlated, not identical, so a
  sum-of-quantiles total runs materially too wide.

  VALUE OF THE EXPECTATION.  rational_value_usd prices the MEAN path through
  value_framework.tiered_war_value_usd, whose own docstring says "never call
  on an averaged WAR". expected_tier_value_usd integrates the curve over the
  shock instead of evaluating it at the middle.

  A CORRECTION TO THE PREMISE, measured 2026-07-25 rather than assumed. The
  tier curve is NOT strictly convex, its own docstring's claim that "both are
  convex in WAR" notwithstanding. Numerically differencing the production
  kernel on a 0.02-WAR grid over [0, 6]:

    w < ~1.2      convex (the $0 floor plus the rising smoothstep ramp)
    1.2 <= w < 2.52  a CONCAVE pocket, deepest at w = 2.48
                     (second difference -68.4 $M per WAR^2)
    w >= 2.52     exactly LINEAR (second difference 0.0 to 1e-6)

  because the v46 smoothstep ramp passes through the tier rates at the tier
  CENTERS and then flattens at the top rate. So the Jensen correction is
  large and POSITIVE where free-agent seasons actually live, nil at the top,
  and mildly negative in one pocket. Per-season gap on a one-year band:

    point 0.8, band 0.0-1.9   +35.997%
    point 1.2, band 0.0-2.4   +23.803%
    point 3.0, band 1.2-4.8    -3.968%
    point 5.0, band 3.0-7.0    -0.012%

  The net effect on the real corpus is a +35.2% level lift, because the FA
  contract-year distribution is dominated by sub-2-WAR seasons.

THE COPULA

  eps_t = sqrt(rho) Z + sqrt(1 - rho) u_t     Z drawn ONCE per player,
                                              u_t iid, both standard normal
  W_t   = F_t^-1(Phi(eps_t))

  so every horizon keeps its own marginal exactly while the path carries one
  shared latent. The EQUICORRELATED spec is earned rather than assumed: an
  AR(1) fitted to the measured lag-1 of 0.4455 would predict a lag-2 of
  0.1985 and the measured lag-2 is 0.3594, nearly twice that. The truth sits
  between AR(1) and perfect equicorrelation, and equicorrelation is the
  conservative (wider) of the two admissible one-parameter specs.

  rho is taken as the mean of the four measured lag Spearmans, 0.3427,
  converted to a Gaussian-copula correlation by rho = 2 sin(pi rho_S / 6) =
  0.3570 (the standard Spearman-to-Pearson map for the Gaussian copula).

THE MARGINALS

  Each horizon's F_t is pinned to the three numbers the platform already
  serves for that season: the point path, the P10 path and the P90 path (the
  T1.2 player-specific band decayed along the aging curves). Between them the
  quantile function is a TWO-PIECE GAUSSIAN, i.e. Gaussian below the point
  with sigma (point - p10)/1.2816 and above it with sigma (p90 - point)/1.2816.
  That reproduces all three served numbers exactly, is monotone by
  construction, and carries the right-skew the WAR distribution actually has.
  Draws are floored at 0 exactly as fa_market._decay_path floors the served
  paths, so simulated and displayed seasons live on one support.

WHY THE EXPECTATION DOES NOT NEED THE COPULA

  Contract value is ADDITIVE across seasons, so E[sum] = sum E[], and the
  correlation structure cancels out of the expectation. The expectation is
  therefore computed by deterministic per-season quadrature (no simulation
  noise in a served dollar figure) and the copula is used only where it
  actually matters: the DISTRIBUTION of a total, which is what CVaR and
  P(at least one star season) read off.

WHAT THE MEASUREMENT SAID, INCLUDING THE PART THAT WENT AGAINST US

  Pre-registered before the run (tools/_fa_total.py): total-interval coverage
  under sum-of-quantiles would come out ABOVE nominal (over-wide) while
  per-year SURVIVED coverage came out far below it.

  Measured on 3,913 held 5-year paths, paired bootstrap B=60 resampling the
  whole panel by anchor cohort:

    per-year coverage, all rows           0.7321   (nominal 0.80)
    per-year coverage, SURVIVED rows      0.3666   (nominal 0.80)
    TOTAL coverage, sum-of-quantiles      0.6474
    TOTAL coverage, copula                0.3863
      delta -0.2611, CI95 [-0.2742, -0.2430], MDE95 0.0147
    TOTAL CRPS, sum-of-quantiles          1.2922
    TOTAL CRPS, copula                    1.4493
      delta +0.1571, CI95 [+0.1435, +0.1674], MDE95 0.0127
    TOTAL interval width                  4.489 -> 3.079 (-31.4%)

  So HALF the prediction holds and half does not, and the half that does not
  is the important one. Per-year survived coverage really is far below nominal
  (0.367). But the sum-of-quantiles total was NOT over-wide: it was 0.647,
  also below nominal. Two errors were cancelling. The quantile sum added width
  it had no right to add, and the per-year marginals were far too narrow
  conditional on the player actually appearing, and the two roughly offset.

  Removing only the first error therefore makes the measured total interval
  WORSE, by a margin 18x its own detection limit. That is a regression, it is
  reported as a regression, and it is shipped anyway on CORRECTNESS grounds:
  the comonotone assumption is measurably false (lag Spearmans 0.4455 / 0.3594
  / 0.3090 / 0.2571, nowhere near 1), so the old number was right by accident
  and would go on being right by accident only until one of the two errors
  moved. Both totals are served (warTotalP10/P90 from the copula,
  warTotalP10Comon/P90Comon from the quantile sum) so the disagreement is on
  the page rather than in a commit message.

  THE ACTUAL NEXT LEVER is the marginal, not the aggregation: a band that
  covers 0.367 of survivors cannot produce a calibrated total under ANY
  aggregation rule. T1.2 narrowed the gap and did not close it.
"""

from __future__ import annotations

import math

# ---- measured inputs (tools/_fa_rho.py, 2026-07-25) ------------------------
# 7 anchored forward-chained cohorts 2015-2021, one held projection per
# player, residual_h = actual(Y+h-1) - path[h-1].
RHO_LAGS_SPEARMAN = {1: 0.4455, 2: 0.3594, 3: 0.3090, 4: 0.2571}
RHO_SPEARMAN = 0.3427                       # mean of the four lags
RHO = 0.3570                                # 2 sin(pi * RHO_SPEARMAN / 6)
N_DRAWS = 10000
Z90 = 1.2815515655446004                    # Phi^-1(0.90)

# Deterministic quadrature grid for the expectation. 19 interior nodes on the
# same uniform tau grid fa_calibration scores on, so the integral and the
# calibration report speak one discretization.
QUAD_TAUS = tuple(round(i / 20.0, 3) for i in range(1, 20))


def _z(p: float) -> float:
    import fa_calibration as fc
    return fc._z(p)


# ============================================================================
# Marginals
# ============================================================================

def two_piece_quantile(point: float, p10: float, p90: float, u: float) -> float:
    """F_t^-1(u) pinned to the three served numbers.

    Degenerate bands (p10 == point == p90, which is what a 0-WAR projection
    decays to) return the point, so a player with no spread simulates as a
    constant rather than dividing by zero."""
    z = _z(min(max(u, 1e-6), 1 - 1e-6))
    if z < 0:
        s = (point - p10) / Z90
        return max(0.0, point + s * z) if s > 0 else max(0.0, point)
    s = (p90 - point) / Z90
    return max(0.0, point + s * z) if s > 0 else max(0.0, point)


# ============================================================================
# T1.3 - correlated-path simulation
# ============================================================================

def simulate(point_path, p10_path, p90_path, years: int,
             draws: int = N_DRAWS, rho: float = RHO, seed: int = 20260725):
    """(draws x years) simulated WAR paths under the one-factor copula.

    Returns a numpy array. ``seed`` is fixed so a served number is
    reproducible: a board that reprints a different P10 every night because
    of simulation noise is not publishing a measurement.

    Implementation note. The generic copula step is W_t = F_t^-1(Phi(eps_t)),
    and here F_t is the two-piece GAUSSIAN pinned to (p10, point, p90), so
    F_t^-1(u) = point + s(u) * Phi^-1(u). The Phi then Phi^-1 round trip is
    the identity and drops out: Phi^-1(Phi(eps_t)) = eps_t. Nothing is
    approximated by skipping it, and it turns 10,000 x T scalar inverse-normal
    evaluations per player into zero."""
    import numpy as np
    T = max(1, int(years))
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal((draws, 1))
    U = rng.standard_normal((draws, T))
    eps = math.sqrt(rho) * Z + math.sqrt(1.0 - rho) * U
    out = np.empty((draws, T))
    for t in range(T):
        pt = float(point_path[t]) if t < len(point_path) else 0.0
        lo = float(p10_path[t]) if p10_path and t < len(p10_path) else pt
        hi = float(p90_path[t]) if p90_path and t < len(p90_path) else pt
        s_lo = max((pt - lo) / Z90, 0.0)
        s_hi = max((hi - pt) / Z90, 0.0)
        z = eps[:, t]
        out[:, t] = np.maximum(np.where(z < 0, pt + s_lo * z, pt + s_hi * z), 0.0)
    return out


def path_quantiles(sims, taus=(0.10, 0.50, 0.90)) -> dict:
    """Empirical quantiles of the TOTAL over the simulated term, plus the
    functionals sum-of-quantiles cannot express."""
    import numpy as np
    tot = sims.sum(axis=1)
    out = {f"p{int(t * 100)}": float(np.quantile(tot, t)) for t in taus}
    out["mean"] = float(tot.mean())
    out["sd"] = float(tot.std())
    # CVaR at 10%: the mean of the worst tenth of outcomes. The number a
    # front office actually cares about, and unreachable from a quantile sum.
    k = max(1, int(0.10 * len(tot)))
    out["cvar10"] = float(np.sort(tot)[:k].mean())
    out["p_any_star"] = float((sims >= 4.0).any(axis=1).mean())
    out["p_replacement"] = float((tot <= 0.5).mean())
    return out


# ============================================================================
# T1.4 - expectation of a convex function of the shock
# ============================================================================

def expected_tier_value_usd(point_path, p10_path, p90_path, years: int,
                            class_year: int, dpw_usd: float,
                            infl: float, discount: float,
                            taus=QUAD_TAUS) -> int:
    """NPV of E[tier value] rather than tier value of E[WAR].

    Deterministic per-season quadrature over the SHIPPED band: for each
    contract season the two-piece marginal is evaluated at the tau grid, each
    node priced through value_framework.tiered_war_value_usd, and the nodes
    averaged. Additivity means the copula cannot change this number, so it is
    computed without simulation and is byte-stable run to run.

    THE GRID TRUNCATES THE TAIL, AND BY 7.4%, NOT "SLIGHTLY". QUAD_TAUS is
    i/20 for i in 1..19: an interior grid on the 5% marks that never evaluates
    u below 0.05 or above 0.95, so the convex tail this whole correction exists
    to capture is exactly what it drops. Measured 2026-09-06 against a converged
    reference (midpoint rule, n=399, which sits 0.03% from the n=102,399 limit;
    the integral converges cleanly to a finite value):

        served FA class, 231 rows   converged/shipped  median 1.0796
                                    p05 1.0370, p95 1.1402
        1,300-signing corpus        Deal+ ratio        median 1.0740
                                    p05 1.0342, p95 1.1359

    It is therefore a LOWER bound, as stated, but not a slight one and not a
    uniform one: a 3.4% to 13.6% spread across rows moves the ORDER of Deal+ and
    not only its level. A midpoint rule on the same 19 nodes already recovers
    most of the gap, so the node count is not the problem; the endpoints are.

    WHY IT IS STILL i/20. Not because the change is unsupported. On this lane's
    own gate (tools/_fa_jensen.py, 444 forward-chained signings scored against
    realized tier-priced WAR) converging the grid moves the PRIMARY metric,
    signed bias, from -1.761 to -1.137 against a realized mean of $12.447M:
    delta +0.624, CI95 [+0.551, +0.705] on a winter-clustered paired bootstrap,
    B=2000, P(right direction) 1.0000. MAE worsens +0.231, CI95 [+0.139, +0.319],
    which is the same trade this correction already accepted when it shipped.

    It is deferred because it is not a numerics decision alone. Deal+ is
    100 * this value / price, so converging the grid raises every published
    Deal+ by a median 7.4% and flips 74 of the 1,300 corpus rows (5.7%) unless
    the verdict terciles are re-cut with it. Those terciles are ALREADY carrying
    one deferred re-cut: fa_market records that VERDICT_GROUP_EDGES is owed a
    cut on the 2026-08-19 basis and that "served verdicts do not move until"
    it happens. Stacking a second basis move onto published VALUE / MARKET /
    OVERPAY labels is an owner call, and the numbers for it are laid out in
    docs/fa-2026-09-06/QUAD_CONVERGENCE.md so it is one decision and not two."""
    from value_framework import _config as _vf_config
    from value_framework import tiered_war_value_usd
    level = dpw_usd / float(_vf_config()["dollars_per_war"]["flat"])
    total = 0.0
    n = len(taus)
    for t in range(max(1, int(years))):
        pt = float(point_path[t]) if t < len(point_path) else 0.0
        lo = float(p10_path[t]) if p10_path and t < len(p10_path) else pt
        hi = float(p90_path[t]) if p90_path and t < len(p90_path) else pt
        acc = 0.0
        for u in taus:
            w = two_piece_quantile(pt, lo, hi, u)
            acc += tiered_war_value_usd(w)
        season = (acc / n) * level * ((1 + infl) ** t)
        total += season / ((1 + discount) ** t)
    return int(total)


def jensen_gap_usd(point_path, p10_path, p90_path, years: int,
                   class_year: int, dpw_usd: float, infl: float,
                   discount: float) -> dict:
    """The correction, itemized: value-of-the-mean vs mean-of-the-value."""
    from value_framework import _config as _vf_config
    from value_framework import tiered_war_value_usd
    level = dpw_usd / float(_vf_config()["dollars_per_war"]["flat"])
    naive = 0.0
    for t in range(max(1, int(years))):
        w = float(point_path[t]) if t < len(point_path) else 0.0
        naive += (tiered_war_value_usd(w) * level * ((1 + infl) ** t)) / \
                 ((1 + discount) ** t)
    exact = expected_tier_value_usd(point_path, p10_path, p90_path, years,
                                    class_year, dpw_usd, infl, discount)
    return {"value_of_mean_usd": int(naive), "mean_of_value_usd": exact,
            "gap_usd": int(exact - naive),
            "gap_pct": (100.0 * (exact - naive) / naive) if naive else None}
