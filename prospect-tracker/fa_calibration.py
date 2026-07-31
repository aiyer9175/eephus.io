# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Calibration instrumentation for the MLB Free Agency module (T1.1).

Built BEFORE anything it grades, and validated as an INSTRUMENT rather than
as a lift. Before this module the FA path carried exactly one distributional
diagnostic: a single pooled P10-P90 hit rate. Gate 1's is 0.79996 against a
nominal 0.80, which is perfect on average and says nothing at all about
whether the bands are calibrated anywhere in particular.

What is here:

  PINBALL / CRPS  crps_from_quantiles is 2 x the mean pinball loss over the
                  supplied tau grid, which is the exact quantile-decomposition
                  identity CRPS(F, y) = 2 * integral_0^1 PL_tau(y, F^-1(tau))
                  dtau evaluated on a discrete grid. A proper score: it grades
                  sharpness and calibration together, so a band cannot buy a
                  better score by getting wider.

  PIT             pit_values interpolates the predictive CDF at the realized
                  value. Under a perfectly calibrated forecast the PIT is
                  Uniform(0,1). The SHAPE of the departure names the defect:
                  hump = intervals too wide, U = too narrow, lean = biased.
                  pit_histogram returns the counts, a chi-square uniformity
                  test, and three named shape statistics so a caller does not
                  have to eyeball a picture.

  RELIABILITY     quantile_reliability sweeps the tau grid and reports
                  empirical P(y <= q_tau) against nominal tau with a binomial
                  standard error, which is the quantile-forecast reliability
                  diagram as data. conditional_coverage does the same for a
                  central interval, binned by any covariate, which is the test
                  that a marginal hit rate cannot do.

Nothing here fits anything or makes a ship decision. It only measures.

VALIDATION (validate_instrument): three synthetic generators with known
answers are pushed through the whole stack, and the instrument must return
the right diagnosis for each:
  calibrated      quantiles equal the true quantiles  -> flat PIT
  inflated 1.5x   quantile spread multiplied by 1.5   -> humped PIT
  biased +0.3     truth shifted, quantiles are not    -> leaning PIT
See test_fa_calibration.py for the asserted thresholds.
"""

from __future__ import annotations

import math
import statistics

# The default tau grid. Deliberately excludes 0 and 1 (unbounded quantiles)
# and is uniform so the mean pinball -> CRPS identity holds without weights.
DEFAULT_TAUS = tuple(round(i / 20.0, 3) for i in range(1, 20))   # 0.05..0.95


def _mean(vals) -> float:
    """Plain float mean. statistics.mean promotes to Fraction, which is both
    slow in these inner loops and (observed 2026-07-25 under a
    ProcessPoolExecutor on CPython 3.13) not re-entrancy safe."""
    v = list(vals)
    if not v:
        raise ValueError("_mean of empty sequence")
    return math.fsum(float(x) for x in v) / len(v)


def _z(p: float) -> float:
    """Standard normal quantile (Acklam's rational approximation, |err| <
    1.15e-9). Local so the module has no scipy dependency."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"z() needs 0<p<1, got {p}")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _sorted_grid(q: dict) -> list[tuple[float, float]]:
    """[(tau, value)] sorted by tau, with the values made non-decreasing.

    Quantile crossing is a real failure mode of independently-estimated
    quantile heads. Rather than error out (which would make the instrument
    unusable exactly where it is most needed) the grid is isotonized by a
    running max and the caller can detect it via ``n_crossings``."""
    grid = sorted(((float(t), float(v)) for t, v in q.items()), key=lambda r: r[0])
    out = []
    hi = None
    for t, v in grid:
        hi = v if hi is None else max(hi, v)
        out.append((t, hi))
    return out


def n_crossings(q: dict) -> int:
    grid = sorted(((float(t), float(v)) for t, v in q.items()), key=lambda r: r[0])
    return sum(1 for a, b in zip(grid, grid[1:]) if b[1] < a[1])


# ============================================================================
# Proper scores
# ============================================================================

def pinball(y: float, q: float, tau: float) -> float:
    """Quantile (pinball) loss. Minimized in expectation at the true tau
    quantile, which is what makes the CRPS built from it proper."""
    d = y - q
    return tau * d if d >= 0 else (tau - 1.0) * d


def crps_from_quantiles(y: float, q: dict) -> float:
    """CRPS approximated by 2 x mean pinball over the supplied tau grid.

    Exact identity: CRPS(F, y) = 2 * integral_0^1 PL_tau(y, F^-1(tau)) dtau.
    The mean over an interior grid is a RECTANGLE rule that drops the two
    tail strips, and since a mean over m points at i/(m+1) covers only
    m/(m+1) of the tau range the result runs slightly HIGH. Measured on the
    calibrated synthetic panel (n=4000, DEFAULT_TAUS, m=19): grid CRPS
    0.584697 vs the closed-form Gaussian 0.557850, i.e. +4.8%, and
    0.95 x 0.584697 = 0.555462 recovers the analytic value to 0.4%. The
    offset is a property of the GRID, not of the forecast, so two forecasts
    scored on the same grid are compared on equal terms. Never mix grids."""
    grid = _sorted_grid(q)
    if not grid:
        raise ValueError("crps_from_quantiles needs a non-empty quantile grid")
    return 2.0 * _mean(pinball(y, v, t) for t, v in grid)


def crps_normal(y: float, mu: float, sigma: float) -> float:
    """Closed-form CRPS of a Gaussian predictive distribution. Used ONLY to
    check that the grid approximation above converges to the right number."""
    if sigma <= 0:
        return abs(y - mu)
    z = (y - mu) / sigma
    cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return sigma * (z * (2.0 * cdf - 1.0) + 2.0 * pdf - 1.0 / math.sqrt(math.pi))


def log_score_normal(y: float, mu: float, sigma: float) -> float:
    """Negative log predictive density under a Gaussian fit to the band.
    Reported alongside CRPS because the two disagree in an informative way:
    the log score punishes tail misses far harder."""
    s = max(float(sigma), 1e-9)
    return 0.5 * math.log(2 * math.pi * s * s) + 0.5 * ((y - mu) / s) ** 2


def sigma_from_band(lo: float, hi: float, lo_tau: float = 0.10,
                    hi_tau: float = 0.90) -> float:
    """Gaussian-equivalent sigma implied by a central band. The FA path
    already does this inline in enter_probability_v2; having one definition
    keeps the option pricer and the calibration report on one scale."""
    span = float(hi) - float(lo)
    z = _z(hi_tau) - _z(lo_tau)
    return max(span / z, 1e-9) if z > 0 else 1e-9


# ============================================================================
# PIT
# ============================================================================

def pit_value(y: float, q: dict) -> float:
    """The predictive CDF evaluated at the realization, by linear
    interpolation of the quantile grid.

    Outside the grid the value is extrapolated linearly in tau off the
    outermost pair and clamped into (0,1). This matters: without it every
    realization past q95 would pile at exactly 1.0 and a too-narrow band
    would look like a spike rather than a U, which is a different diagnosis.
    The clamp margin is half a grid step so the extremes stay distinguishable
    from the interior."""
    grid = _sorted_grid(q)
    if len(grid) < 2:
        raise ValueError("pit_value needs at least two quantiles")
    taus = [t for t, _ in grid]
    vals = [v for _, v in grid]
    step = min(b - a for a, b in zip(taus, taus[1:]))
    lo_clamp, hi_clamp = 0.5 * step * 0.5, 1.0 - 0.5 * step * 0.5
    if y <= vals[0]:
        dv = vals[1] - vals[0]
        t = taus[0] - (vals[0] - y) / dv * (taus[1] - taus[0]) if dv > 0 else taus[0] / 2
        return max(lo_clamp, min(t, taus[0]))
    if y >= vals[-1]:
        dv = vals[-1] - vals[-2]
        t = (taus[-1] + (y - vals[-1]) / dv * (taus[-1] - taus[-2])
             if dv > 0 else (1.0 + taus[-1]) / 2)
        return min(hi_clamp, max(t, taus[-1]))
    for (t0, v0), (t1, v1) in zip(grid, grid[1:]):
        if v0 <= y <= v1:
            if v1 == v0:
                return (t0 + t1) / 2.0
            return t0 + (y - v0) / (v1 - v0) * (t1 - t0)
    return 0.5                                          # unreachable in practice


def pit_values(rows: list[dict]) -> list[float]:
    """rows: [{"y": actual, "q": {tau: value}}]."""
    return [pit_value(r["y"], r["q"]) for r in rows]


def pit_histogram(pits: list[float], bins: int = 10) -> dict:
    """PIT histogram plus the statistics that NAME the departure.

      chi2 / dof / p_uniform  the omnibus uniformity test
      lean                    mean(PIT) - 0.5. Positive means realizations sit
                              high in the band, i.e. the forecast is biased LOW.
      central_frac / hump     share of PIT inside the central half [0.25,0.75]
                              minus the 0.50 it should be. Positive = intervals
                              too WIDE (mass bunches in the middle). Negative =
                              too narrow (mass flees to the tails).
      tail_frac               share outside [0.05,0.95], nominal 0.10.

    p_uniform uses a Wilson-Hilferty normal approximation to the chi-square
    tail, which is accurate to ~1e-3 in p for dof >= 5 and is used only to
    flag, never to gate."""
    n = len(pits)
    if n == 0:
        return {"n": 0}
    counts = [0] * bins
    for p in pits:
        counts[min(bins - 1, max(0, int(p * bins)))] += 1
    exp = n / bins
    chi2 = sum((c - exp) ** 2 / exp for c in counts)
    dof = bins - 1
    # Wilson-Hilferty: (chi2/dof)^(1/3) is approx normal(1 - 2/(9 dof), 2/(9 dof))
    h = 2.0 / (9.0 * dof)
    zz = ((chi2 / dof) ** (1.0 / 3.0) - (1.0 - h)) / math.sqrt(h)
    p_uniform = 0.5 * math.erfc(zz / math.sqrt(2.0))
    central = sum(1 for p in pits if 0.25 <= p <= 0.75) / n
    tail = sum(1 for p in pits if p < 0.05 or p > 0.95) / n
    return {
        "n": n, "bins": bins, "counts": counts,
        "freq": [round(c / n, 5) for c in counts],
        "chi2": round(chi2, 4), "dof": dof, "p_uniform": round(p_uniform, 6),
        "mean": round(_mean(pits), 5),
        "lean": round(_mean(pits) - 0.5, 5),
        "central_frac": round(central, 5), "hump": round(central - 0.5, 5),
        "tail_frac": round(tail, 5),
        # se of a bin frequency under the null, for reading `freq` by eye
        "bin_se": round(math.sqrt((1.0 / bins) * (1 - 1.0 / bins) / n), 5),
    }


def diagnose_pit(hist: dict, alpha: float = 0.01) -> str:
    """One word for what the histogram says. Ordered so the LARGEST defect
    wins: a biased forecast whose bands are also too wide reads as biased,
    because bias is the one a reader can see on the page."""
    if not hist.get("n"):
        return "empty"
    if hist["p_uniform"] >= alpha:
        return "calibrated"
    lean, hump = abs(hist["lean"]), hist["hump"]
    if lean >= 0.02 and lean >= abs(hump):
        return "biased_low" if hist["lean"] > 0 else "biased_high"
    if hump >= 0.02:
        return "over_wide"
    if hump <= -0.02:
        return "over_narrow"
    return "misshaped"


# ============================================================================
# Reliability
# ============================================================================

def quantile_reliability(rows: list[dict], taus=None) -> list[dict]:
    """The reliability diagram as data: nominal tau vs empirical
    P(y <= q_tau), with a binomial standard error per point."""
    if not rows:
        return []
    grid = taus or sorted(float(t) for t in rows[0]["q"])
    out = []
    for t in grid:
        hits = n = 0
        for r in rows:
            q = r["q"].get(t, r["q"].get(round(t, 3)))
            if q is None:
                continue
            n += 1
            hits += 1 if r["y"] <= q else 0
        if not n:
            continue
        emp = hits / n
        out.append({"tau": t, "empirical": round(emp, 5), "n": n,
                    "se": round(math.sqrt(max(emp * (1 - emp), 1e-12) / n), 5),
                    "gap": round(emp - t, 5)})
    return out


def reliability_summary(rel: list[dict]) -> dict:
    """Mean absolute reliability gap and the worst point. This is the single
    number a marginal hit rate hides: a forecast can sit exactly on nominal
    at 0.10/0.90 and be badly wrong at 0.25/0.75."""
    if not rel:
        return {"n_points": 0}
    worst = max(rel, key=lambda r: abs(r["gap"]))
    return {"n_points": len(rel),
            "mean_abs_gap": round(_mean(abs(r["gap"]) for r in rel), 5),
            "max_abs_gap": round(abs(worst["gap"]), 5),
            "worst_tau": worst["tau"],
            "signed_mean_gap": round(_mean(r["gap"] for r in rel), 5)}


def conditional_coverage(rows: list[dict], key, lo_tau: float = 0.10,
                         hi_tau: float = 0.90, n_bins: int = 10,
                         labels: dict | None = None) -> list[dict]:
    """Central-interval coverage BINNED by a covariate.

    ``key`` is either a callable row -> value or a row key. Numeric values
    are binned into ``n_bins`` equal-count bins; non-numeric values are used
    as categories directly. Each bin reports the binomial standard error, so
    a reader can tell a real miss from bin noise: ~2,000 rows per bin gives
    se ~0.9pp, so a 2.5pp departure is resolvable and a 1pp one is not.

    This is the test Gate 1's marginal 0.79996 cannot do."""
    getter = key if callable(key) else (lambda r: r.get(key))
    vals = [(getter(r), r) for r in rows]
    vals = [(v, r) for v, r in vals if v is not None]
    if not vals:
        return []
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                  for v, _ in vals)
    groups: dict = {}
    if numeric:
        vals.sort(key=lambda p: p[0])
        n = len(vals)
        for i, (v, r) in enumerate(vals):
            b = min(n_bins - 1, i * n_bins // n)
            groups.setdefault(b, []).append((v, r))
    else:
        for v, r in vals:
            groups.setdefault(v, []).append((v, r))
    out = []
    for g in sorted(groups, key=lambda k: (str(type(k)), k)):
        members = groups[g]
        hits = 0
        for _v, r in members:
            lo = r["q"].get(lo_tau)
            hi = r["q"].get(hi_tau)
            if lo is None or hi is None:
                continue
            hits += 1 if lo <= r["y"] <= hi else 0
        n = len(members)
        cov = hits / n if n else None
        row = {"bin": (labels or {}).get(g, g), "n": n,
               "coverage": round(cov, 5) if cov is not None else None,
               "nominal": round(hi_tau - lo_tau, 5)}
        if numeric:
            row["lo"] = round(members[0][0], 4)
            row["hi"] = round(members[-1][0], 4)
        if cov is not None and n:
            row["se"] = round(math.sqrt(max(cov * (1 - cov), 1e-12) / n), 5)
            row["z"] = round((cov - (hi_tau - lo_tau)) / (row["se"] or 1e-9), 3)
        out.append(row)
    return out


def coverage(rows: list[dict], lo_tau: float = 0.10, hi_tau: float = 0.90) -> dict:
    """Marginal central-interval coverage. Kept because it is what the
    module reported before, and reported NEXT TO the conditional table so the
    contrast between them is on the page."""
    hits = n = 0
    for r in rows:
        lo, hi = r["q"].get(lo_tau), r["q"].get(hi_tau)
        if lo is None or hi is None:
            continue
        n += 1
        hits += 1 if lo <= r["y"] <= hi else 0
    if not n:
        return {"n": 0}
    c = hits / n
    return {"n": n, "coverage": round(c, 5), "nominal": round(hi_tau - lo_tau, 5),
            "se": round(math.sqrt(max(c * (1 - c), 1e-12) / n), 5)}


# ============================================================================
# The report
# ============================================================================

def calibration_report(rows: list[dict], taus=None, bins: int = 10,
                       lo_tau: float = 0.10, hi_tau: float = 0.90,
                       conditioners: dict | None = None) -> dict:
    """Everything above, on one set of (y, quantile-grid) rows.

    ``conditioners`` maps a name to a row accessor for the conditional
    coverage tables."""
    if not rows:
        return {"n": 0}
    pits = pit_values(rows)
    rel = quantile_reliability(rows, taus)
    out = {
        "n": len(rows),
        "crps": round(_mean(crps_from_quantiles(r["y"], r["q"])
                                      for r in rows), 6),
        "mae_median": round(_mean(
            abs(r["y"] - _median_of(r["q"])) for r in rows), 6),
        "bias_median": round(_mean(
            _median_of(r["q"]) - r["y"] for r in rows), 6),
        "pinball": {str(t): round(_mean(
            pinball(r["y"], r["q"][t], t) for r in rows if t in r["q"]), 6)
            for t in (lo_tau, 0.5, hi_tau) if any(t in r["q"] for r in rows)},
        "pit": pit_histogram(pits, bins),
        "reliability": rel,
        "reliability_summary": reliability_summary(rel),
        "coverage": coverage(rows, lo_tau, hi_tau),
        "n_crossing_rows": sum(1 for r in rows if n_crossings(r["q"])),
    }
    out["diagnosis"] = diagnose_pit(out["pit"])
    if conditioners:
        out["conditional_coverage"] = {
            name: conditional_coverage(rows, acc, lo_tau, hi_tau)
            for name, acc in conditioners.items()}
    return out


def _median_of(q: dict) -> float:
    grid = _sorted_grid(q)
    if 0.5 in dict(grid):
        return dict(grid)[0.5]
    lo = [v for t, v in grid if t <= 0.5]
    hi = [v for t, v in grid if t >= 0.5]
    if lo and hi:
        return (lo[-1] + hi[0]) / 2.0
    return grid[len(grid) // 2][1]


# ============================================================================
# INSTRUMENT VALIDATION (T1.1) - three generators with known answers
# ============================================================================

def synthetic_rows(kind: str, n: int = 4000, seed: int = 11,
                   sigma: float = 1.0, taus=None, bias: float = 0.3,
                   inflate: float = 1.5) -> list[dict]:
    """Forecast/outcome pairs whose calibration defect is known by
    construction.

      "calibrated"  y ~ N(mu, sigma); quantiles are the TRUE quantiles.
      "inflated"    same truth; quantile spread multiplied by ``inflate``.
      "biased"      y ~ N(mu + bias, sigma); quantiles centered on mu.

    mu varies across rows (uniform 0..4) so the instrument is exercised on a
    heterogeneous panel, which is the FA case, not a single location."""
    import random
    rng = random.Random(seed)
    grid = list(taus or DEFAULT_TAUS)
    rows = []
    for _ in range(n):
        mu = rng.uniform(0.0, 4.0)
        shift = bias if kind == "biased" else 0.0
        scale = inflate if kind == "inflated" else 1.0
        y = rng.gauss(mu + shift, sigma)
        rows.append({"y": y,
                     "q": {t: mu + scale * sigma * _z(t) for t in grid},
                     "mu": mu})
    return rows


def validate_instrument(n: int = 4000, seed: int = 11) -> dict:
    """Run all three generators through the full report. Returns the report
    per generator plus the analytic CRPS the calibrated arm must hit.

    This validates the INSTRUMENT. No ship decision attaches to it."""
    out = {}
    for kind in ("calibrated", "inflated", "biased"):
        rows = synthetic_rows(kind, n=n, seed=seed)
        rep = calibration_report(rows)
        rep["analytic_crps_normal"] = round(_mean(
            crps_normal(r["y"], r["mu"], 1.0) for r in rows), 6)
        out[kind] = rep
    return out


if __name__ == "__main__":
    import json
    r = validate_instrument()
    for kind, rep in r.items():
        print(f"== {kind}: diagnosis={rep['diagnosis']} "
              f"chi2={rep['pit']['chi2']} p={rep['pit']['p_uniform']} "
              f"lean={rep['pit']['lean']} hump={rep['pit']['hump']} "
              f"crps={rep['crps']} (analytic N crps {rep['analytic_crps_normal']}) "
              f"cov={rep['coverage']['coverage']}")
    print(json.dumps(r["calibrated"]["reliability_summary"], indent=1))
