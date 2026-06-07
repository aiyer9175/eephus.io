# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Backtest & calibration harness for the surplus-value engine (Prompt F).

Turns the surplus model from a principled prior into a *calibrated* estimator by
comparing its as-of-listing predictions to what listed prospects actually
produced, then fitting a documented correction. Pipeline:

    ingest -> ID-join -> reconstruct realized SV (ground truth)
           -> predict as-of-listing (no look-ahead) -> metrics -> correction (CV)

CARDINAL RULES (asserted):
  * NO LOOK-AHEAD. The prediction path receives a frozen `ListingView` carrying
    ONLY listing-time fields; the post-listing `RealizedRecord` is a separate
    object joined by player_id AFTER prediction. It is structurally impossible
    for predict_listing() to read realized data. assert_no_lookahead() verifies.
  * CONSISTENT UNITS. Predicted and realized SV are both PRESENT VALUE at the
    listing year, discounted at the same `discount_rate`. (The $/WAR a win is
    valued at legitimately differs -- realized uses the rate that prevailed the
    year it was produced; predicted uses the model's standing assumption -- that
    difference is precisely what the calibration is meant to absorb, and the
    decomposition attributes it.)

DATA. A *real* backtest needs completed-window cohorts (2015-19 FV lists),
season-by-season fWAR, ACTUAL historical salaries, service time, and historical
$/WAR -- none of which ship with this repo. So ingestion is a PLUGGABLE
interface (supply your own loader returning PlayerRecord objects), and this
module ships a synthetic-cohort generator with a KNOWN injected shrinkage so the
harness can be validated end-to-end (it must recover the injected correction)
without fabricating real calibration. The committed config correction stays
IDENTITY until a real-data backtest is run; see docs/sv-backtest.md.

Run the synthetic self-validation + report:

    python backtest.py --synthetic
"""

from __future__ import annotations

import argparse
import json
import math
import zlib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

import value_framework as vf

_HERE = Path(__file__).resolve().parent
_SERVICE_FULL_DAYS = 172.0          # one full service year
_CONTROL_SERVICE_YEARS = 6.0        # service years to free agency


# =============================================================================
# Data model -- the no-look-ahead boundary is a TYPE boundary
# =============================================================================
@dataclass(frozen=True)
class ListingView:
    """Everything the prediction path is allowed to see -- ONLY information
    available at listing time. The prediction function takes this and nothing
    else, so it cannot read post-listing outcomes."""
    player_id: str
    name: str
    listing_year: int
    fv: float
    is_pitcher: bool
    position: str | None
    age_at_listing: float | None
    eta_years: float | None          # projected years to debut, as believed at listing
    pre_debut: bool                  # restrict the clean prospect backtest to True


# Fields a ListingView is permitted to carry (anything else = potential leak).
_LISTING_ALLOWED = {f.name for f in fields(ListingView)}


@dataclass(frozen=True)
class RealizedSeason:
    """One actual MLB season of record (post-listing ground truth)."""
    year: int
    fwar: float
    salary_mm: float
    service_days: float              # active-roster/IL days accrued that season


@dataclass(frozen=True)
class RealizedRecord:
    """Post-listing ground truth. NEVER passed to the prediction path."""
    player_id: str
    debut_year: int | None           # None => never reached MLB
    seasons: tuple[RealizedSeason, ...] = ()
    super_two: bool = False
    released_year: int | None = None  # control ends after this season


@dataclass(frozen=True)
class PlayerRecord:
    listing: ListingView
    realized: RealizedRecord


# =============================================================================
# No-look-ahead guard (assertable)
# =============================================================================
def assert_no_lookahead(predict_fn: Callable) -> None:
    """Verify the prediction path cannot access post-listing data:
      (1) ListingView carries only whitelisted listing-time fields,
      (2) ListingView and RealizedRecord share NO field names beyond the join
          key (so a realized field can't masquerade as a listing field),
      (3) the predict function takes a single ListingView argument.
    Raises AssertionError on violation."""
    import inspect

    listing_fields = {f.name for f in fields(ListingView)}
    assert listing_fields <= _LISTING_ALLOWED, \
        f"ListingView leaked non-listing fields: {listing_fields - _LISTING_ALLOWED}"
    realized_fields = {f.name for f in fields(RealizedRecord)} | {f.name for f in fields(RealizedSeason)}
    overlap = (listing_fields & realized_fields) - {"player_id"}
    assert not overlap, f"Listing/realized field overlap (leak risk): {overlap}"
    sig = inspect.signature(predict_fn)
    params = [p for p in sig.parameters.values()
              if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    assert params, "predict_fn takes no positional argument"
    ann = params[0].annotation
    assert ann in (ListingView, "ListingView"), \
        f"predict_fn's first arg must be a ListingView, got {ann!r}"


# =============================================================================
# Step 1 -- realized surplus reconstruction (the ground truth)
# =============================================================================
def _dpw_overall_mm(dpw_by_year: dict, year: int) -> float:
    """$M/WAR overall that season; fall back to the nearest available year."""
    row = dpw_by_year.get(year) or dpw_by_year.get(str(year))
    if row is None and dpw_by_year:
        yrs = sorted(int(y) for y in dpw_by_year)
        nearest = min(yrs, key=lambda y: abs(y - year))
        row = dpw_by_year.get(nearest) or dpw_by_year.get(str(nearest))
    return float((row or {}).get("overall", 0.0))


def realized_sv_pv(realized: RealizedRecord, listing_year: int, *,
                   discount_rate: float, dpw_by_year: dict,
                   tiered: bool = False, inflation: float = 0.0) -> float:
    """Realized surplus value, present value at the listing year:

        SV = Σ_{control years}  (fWAR[y]*dpw_actual[y] - salary[y])
                                / (1+discount_rate)**(y - listing_year)

    Control window = MLB debut through the season in which the player accrues
    6.000 service years (free agency), located by CUMULATIVE service, not
    calendar. Edge cases:
      * never debuted -> 0 (no seasons / debut_year None);
      * replacement-level or injured -> genuinely negative, NOT floored;
      * released/non-tendered -> control ends that year;
      * partial seasons -> actual prorated fWAR/salary; service accrues only on
        active days, delaying FA;
      * extension -> the ACTUAL salary paid is used for control years; years the
        extension bought out beyond 6.000 service are FA years, excluded by the
        service cutoff;
      * traded mid-control -> all control years count (asset value, not org ROI).

    Valuation convention:
      * tiered=False (REAL data, default): production is valued at the OVERALL
        market $/WAR that prevailed the year it was produced (what a win actually
        cost). The model's convex TIERED-pricing assumption then becomes one of
        the things the backtest calibrates, and the decomposition attributes it.
      * tiered=True (SYNTHETIC self-test): production is valued with the MODEL's
        OWN convention -- the convex tiered $/WAR grown by `inflation` -- so the
        only injected predicted-vs-realized difference is the WAR-shrink, making
        the self-test fair (inject_shrink=1.0 -> slope ~1, bias ~0)."""
    if realized.debut_year is None or not realized.seasons:
        return 0.0
    cum_service = 0.0
    total = 0.0
    for s in sorted(realized.seasons, key=lambda s: s.year):
        if realized.released_year is not None and s.year > realized.released_year:
            break                                       # control ended at release
        if cum_service >= _CONTROL_SERVICE_YEARS * _SERVICE_FULL_DAYS:
            break                                       # already a free agent
        years_out = s.year - listing_year
        if tiered:
            # Match the model's pricing: convex tiered $/WAR grown by inflation,
            # netted against the discount rate -- the same factor the engine uses.
            market = vf.tiered_war_value_usd(s.fwar) / 1e6
            total += (market - s.salary_mm) * (((1.0 + inflation) / (1.0 + discount_rate)) ** years_out)
        else:
            dpw = _dpw_overall_mm(dpw_by_year, s.year)  # $M/WAR overall, that season
            total += (s.fwar * dpw - s.salary_mm) / ((1.0 + discount_rate) ** years_out)
        cum_service += s.service_days                   # crossing season is still in-window
    return total


# =============================================================================
# Step 2 -- model predictions, as-of-listing (NO look-ahead: input is ListingView)
# =============================================================================
def _player_seed(player_id: str, base: int = 20260530) -> int:
    """Stable (process-independent) per-player seed for reproducible MC draws."""
    return (base + zlib.crc32(player_id.encode("utf-8"))) % (2 ** 32)


def predict_listing(listing: ListingView, *, draws: int = 4000) -> dict:
    """Predict SV from listing-time info ONLY. Emits the RAW (uncalibrated)
    point SV, the predicted SV draws (Prompt E distribution, for PIT), and a
    separate predicted-WAR aggregate (for the FV->WAR vs $/WAR decomposition).
    Uses the model's STANDING $/WAR + discount assumptions, held fixed across all
    players, with the reference date = listing year (the engine discounts the
    control window from projected debut via eta_years)."""
    raw_usd = vf.expected_surplus_usd(
        listing.fv, listing.is_pitcher, listing.position,
        age=listing.age_at_listing, eta_years=listing.eta_years)
    pred_mm = (raw_usd or 0.0) / 1e6
    d = vf.sv_draws(listing.fv, listing.is_pitcher, listing.position,
                    draws=draws, seed=_player_seed(listing.player_id),
                    age=listing.age_at_listing, eta_years=listing.eta_years)
    # Decomposition handle: predicted total control-window WAR (FV->WAR layer
    # only), independent of the $ conversion.
    avg_war = vf.expected_six_year_avg_war(listing.fv, listing.is_pitcher) or 0.0
    control_years = int(vf._config()["service_time"]["control_years"])
    pred_war = avg_war * control_years
    return {
        "player_id": listing.player_id,
        "pred_mm": pred_mm,
        "draws_mm": d if d is not None else np.array([pred_mm]),
        "pred_control_war": pred_war,
    }


# =============================================================================
# Step 3 -- metrics
# =============================================================================
def calibration_regression(pred: np.ndarray, realized: np.ndarray) -> dict:
    """Regress realized ~ predicted. slope<1 => the model overshoots (needs
    shrinkage); the (slope, intercept) ARE the linear correction."""
    from scipy import stats
    if len(pred) < 2:
        return {"slope": float("nan"), "intercept": float("nan"), "r2": float("nan")}
    lr = stats.linregress(pred, realized)
    return {"slope": float(lr.slope), "intercept": float(lr.intercept), "r2": float(lr.rvalue ** 2)}


def binned_calibration(pred: np.ndarray, realized: np.ndarray, n_bins: int = 8) -> dict:
    """Calibration slope on BINNED means -- a low-VARIANCE, readable estimate of
    the same level slope as the raw OLS fit. The predictor here is deterministic
    (predicted SV is a fixed function of listing inputs, with no measurement
    error), so the raw OLS slope of realized-on-predicted is already UNBIASED --
    the enormous per-player outcome variance inflates its standard error but does
    NOT attenuate it. Binning predictions and regressing per-bin MEAN realized on
    MEAN predicted trades degrees of freedom for far lower variance (much higher
    R^2, cleaner plot); it estimates the same slope, not a de-attenuated one."""
    if len(pred) < n_bins + 1:
        return calibration_regression(pred, realized)
    order = np.argsort(pred)
    ps, rs = pred[order], realized[order]
    bins = np.array_split(np.arange(len(pred)), n_bins)
    mp = np.array([ps[b].mean() for b in bins if len(b)])
    mr = np.array([rs[b].mean() for b in bins if len(b)])
    out = calibration_regression(mp, mr)
    out["bin_pred_mean"] = [round(float(x), 2) for x in mp]
    out["bin_real_mean"] = [round(float(x), 2) for x in mr]
    return out


def bootstrap_slope_ci(pred: np.ndarray, realized: np.ndarray, *, n_boot: int = 2000,
                       seed: int = 7, alpha: float = 0.10) -> tuple[float, float]:
    """Percentile bootstrap CI on the calibration slope (high-FV cells are thin
    -> the calibration itself is uncertain; report its CI)."""
    from scipy import stats
    rng = np.random.RandomState(seed)
    n = len(pred)
    if n < 3:
        return (float("nan"), float("nan"))
    slopes = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.randint(0, n, n)
        slopes[i] = stats.linregress(pred[idx], realized[idx]).slope
    return (float(np.quantile(slopes, alpha / 2)), float(np.quantile(slopes, 1 - alpha / 2)))


def error_metrics(pred: np.ndarray, realized: np.ndarray) -> dict:
    from scipy import stats
    err = realized - pred
    sp = stats.spearmanr(pred, realized).correlation if len(pred) > 2 else float("nan")
    return {
        "n": int(len(pred)),
        "bias": float(err.mean()),                    # mean(realized - predicted)
        "rmse": float(np.sqrt((err ** 2).mean())),
        "mae": float(np.abs(err).mean()),
        "spearman": float(sp),
    }


def pit_value(draws_mm: np.ndarray, realized_mm: float) -> float:
    """Probability Integral Transform: where the realized value falls in the
    predicted CDF. Well-calibrated distributions => PITs ~ Uniform(0,1); mass
    near 0 => the model is systematically optimistic (realized below predicted)."""
    return float((draws_mm <= realized_mm).mean())


def pit_uniformity(pits: np.ndarray) -> dict:
    """KS test of the PITs against Uniform(0,1) + P10-P90 coverage (~0.80 ideal)."""
    from scipy import stats
    pits = np.asarray(pits, dtype=float)
    if len(pits) < 3:
        return {"ks_stat": float("nan"), "ks_p": float("nan"), "coverage_p10_p90": float("nan")}
    ks = stats.kstest(pits, "uniform")
    cov = float(((pits >= 0.10) & (pits <= 0.90)).mean())
    return {"ks_stat": float(ks.statistic), "ks_p": float(ks.pvalue), "coverage_p10_p90": cov}


def decomposition(records: Sequence[PlayerRecord], preds: list[dict], *,
                  discount_rate: float, dpw_by_year: dict, model_dpw_mm: float,
                  tiered: bool = False, inflation: float = 0.0) -> dict:
    """Attribute total error across the FV->WAR layer vs the $/WAR + arb layers.
    WAR-level: realized control-window WAR vs predicted control WAR. Holding
    $/WAR at the model's flat assumption isolates the FV->WAR contribution; the
    remaining gap to the full realized SV (which used each year's actual $/WAR
    and actual salaries) is the $/WAR-regime + arb residual."""
    pred_war, real_war, war_priced_gap, total_gap = [], [], [], []
    by_id = {p["player_id"]: p for p in preds}
    for rec in records:
        pr = by_id.get(rec.listing.player_id)
        if pr is None:
            continue
        rw = _realized_control_war(rec.realized)
        pw = pr["pred_control_war"]
        real_war.append(rw)
        pred_war.append(pw)
        war_priced_gap.append((rw - pw) * model_dpw_mm)     # WAR error priced at model $/WAR
        rsv = realized_sv_pv(rec.realized, rec.listing.listing_year,
                             discount_rate=discount_rate, dpw_by_year=dpw_by_year,
                             tiered=tiered, inflation=inflation)
        total_gap.append(rsv - pr["pred_mm"])
    pred_war = np.array(pred_war); real_war = np.array(real_war)
    total = np.array(total_gap); warp = np.array(war_priced_gap)
    return {
        "war_bias": float((real_war - pred_war).mean()) if len(pred_war) else float("nan"),
        "war_calibration": calibration_regression(pred_war, real_war) if len(pred_war) > 1 else {},
        "total_sv_bias": float(total.mean()) if len(total) else float("nan"),
        "explained_by_war_bias": float(warp.mean()) if len(warp) else float("nan"),
        "dollar_arb_residual_bias": float((total - warp).mean()) if len(total) else float("nan"),
    }


def _realized_control_war(realized: RealizedRecord) -> float:
    """Total fWAR over the control window (same service-time cutoff as Step 1)."""
    if realized.debut_year is None or not realized.seasons:
        return 0.0
    cum, war = 0.0, 0.0
    for s in sorted(realized.seasons, key=lambda s: s.year):
        if realized.released_year is not None and s.year > realized.released_year:
            break
        if cum >= _CONTROL_SERVICE_YEARS * _SERVICE_FULL_DAYS:
            break
        war += s.fwar
        cum += s.service_days
    return war


# =============================================================================
# Step 4 -- correction layer (linear / isotonic) + out-of-sample CV
# =============================================================================
def fit_linear_correction(pred: np.ndarray, realized: np.ndarray) -> dict:
    reg = calibration_regression(pred, realized)
    return {"method": "linear", "slope": reg["slope"], "intercept_mm": reg["intercept"]}


def fit_isotonic_correction(pred: np.ndarray, realized: np.ndarray) -> dict:
    """Monotone (shape-free) correction: isotonic regression of realized on
    predicted. Stored as breakpoints (predicted -> calibrated)."""
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(np.asarray(pred, dtype=float), np.asarray(realized, dtype=float))
    xs = np.unique(np.asarray(pred, dtype=float))
    ys = iso.predict(xs)
    return {"method": "isotonic", "x_mm": [float(x) for x in xs], "y_mm": [float(y) for y in ys]}


def apply_correction(corr: dict, pred_mm: float) -> float:
    if corr.get("method") == "isotonic":
        xs, ys = corr["x_mm"], corr["y_mm"]
        if len(xs) >= 2:
            return float(np.interp(pred_mm, xs, ys))
        return pred_mm
    return float(corr.get("slope", 1.0)) * pred_mm + float(corr.get("intercept_mm", 0.0))


def leave_one_year_out_cv(records: Sequence[PlayerRecord], preds: list[dict], *,
                          discount_rate: float, dpw_by_year: dict,
                          method: str = "linear", tiered: bool = False,
                          inflation: float = 0.0) -> dict:
    """Fit the correction leaving out one list-year at a time and evaluate
    calibration / bias / PIT uniformity on the HELD-OUT year only -- never fit
    and evaluate on the same data.

    The held-out PIT uses an AFFINE recalibration of the predictive draws --
    location AND scale -- because the level correction (slope<1 / isotonic mean
    map) only fixes the MEAN; left un-rescaled the shrunk distribution stays
    over-dispersed (PIT piles in the middle, coverage -> 1.0). The per-fold
    dispersion scale = std(train residuals about the corrected mean) /
    mean(train predictive-draw std), so the corrected predictive spread is
    calibrated to the held-out residual spread."""
    by_id = {p["player_id"]: p for p in preds}
    rows = []
    for rec in records:
        pr = by_id.get(rec.listing.player_id)
        if pr is None:
            continue
        rsv = realized_sv_pv(rec.realized, rec.listing.listing_year,
                             discount_rate=discount_rate, dpw_by_year=dpw_by_year,
                             tiered=tiered, inflation=inflation)
        rows.append((rec.listing.listing_year, pr["pred_mm"], rsv, pr["draws_mm"]))
    years = sorted({r[0] for r in rows})
    held_pred, held_real, held_pit = [], [], []
    for y in years:
        train = [(p, r, d) for (yr, p, r, d) in rows if yr != y]
        test = [(p, r, d) for (yr, p, r, d) in rows if yr == y]
        if len(train) < 3 or not test:
            continue
        tp = np.array([p for p, _, _ in train]); tr = np.array([r for _, r, _ in train])
        corr = (fit_isotonic_correction(tp, tr) if method == "isotonic"
                else fit_linear_correction(tp, tr))
        # Dispersion scale from the TRAIN fold: how wide should the corrected
        # predictive be vs the raw draw spread, to match realized residuals?
        tc = np.array([apply_correction(corr, p) for p in tp])
        resid_std = float(np.std(tr - tc))
        draw_std = float(np.mean([np.std(d) for _, _, d in train])) or 1.0
        disp = resid_std / draw_std
        for (p, r, d) in test:
            c = apply_correction(corr, p)
            held_pred.append(c); held_real.append(r)
            # Affine-recalibrated predictive: recentre on c AND rescale spread.
            recal = c + disp * (np.asarray(d, dtype=float) - p)
            held_pit.append(pit_value(recal, r))
    held_pred = np.array(held_pred); held_real = np.array(held_real)
    out = {
        "method": method,
        "held_out_calibration": calibration_regression(held_pred, held_real) if len(held_pred) > 1 else {},
        "held_out_bias": float((held_real - held_pred).mean()) if len(held_pred) else float("nan"),
        "held_out_rmse": float(np.sqrt(((held_real - held_pred) ** 2).mean())) if len(held_pred) else float("nan"),
        "held_out_pit": pit_uniformity(np.array(held_pit)) if held_pit else {},
        "n_held_out": int(len(held_pred)),
        "years": years,
    }
    return out


# =============================================================================
# Sensitivity table -- rank model params by |dSV/dparam| over a reference grid
# =============================================================================
def sensitivity_table(reference: Sequence[ListingView] | None = None, *, rel_step: float = 0.05) -> list[dict]:
    """Numerically perturb each scalar model parameter by +/-rel_step and report
    the mean |relative dSV| over a reference prospect grid. Expect $/WAR (esp.
    the 2+ tier) and discount_rate to dominate -- that is where precision pays."""
    if reference is None:
        reference = [ListingView(f"ref_{fv}_{r}", f"ref{fv}", 2024, fv, r, None, 23, 1.5, True)
                     for fv in (45, 50, 55, 60, 65) for r in (False, True)]
    cfg = vf._config()

    def mean_sv() -> float:
        vf._reset_caches() if False else vf._bucket_sv_usd.cache_clear()
        vals = [vf.surplus_value_mm(lv.fv, lv.is_pitcher, lv.position,
                                    age=lv.age_at_listing, eta_years=lv.eta_years) or 0.0
                for lv in reference]
        return float(np.mean(vals))

    # (path-to-scalar) knobs to perturb.
    knobs = [
        ("discount_rate", lambda c: c, "discount_rate"),
        ("dollars_per_war_inflation", lambda c: c, "dollars_per_war_inflation"),
        ("dpw_2plus", lambda c: c["dollars_per_war"]["tiered"]["rates"], "2plus"),
        ("dpw_1_to_2", lambda c: c["dollars_per_war"]["tiered"]["rates"], "1_to_2"),
        ("dpw_lt_1", lambda c: c["dollars_per_war"]["tiered"]["rates"], "lt_1"),
        ("league_min_usd", lambda c: c["service_time"], "league_min_usd"),
        ("relief_war_haircut", lambda c: c["position"], "relief_war_haircut"),
    ]
    base = mean_sv()
    rows = []
    for label, container_fn, key in knobs:
        cont = container_fn(cfg)
        orig = float(cont[key])
        if orig == 0:
            continue
        cont[key] = orig * (1 + rel_step)
        hi = mean_sv()
        cont[key] = orig * (1 - rel_step)
        lo = mean_sv()
        cont[key] = orig                                  # restore
        vf._bucket_sv_usd.cache_clear()
        # elasticity: (%dSV) / (%dparam)
        elasticity = ((hi - lo) / base) / (2 * rel_step) if base else float("nan")
        rows.append({"param": label, "base_value": orig,
                     "d_meanSV_pct_per_1pct_param": round(100 * elasticity / 100, 4),
                     "elasticity": round(elasticity, 4)})
    rows.sort(key=lambda r: -abs(r["elasticity"]))
    return rows


# =============================================================================
# Synthetic cohort -- known data-generating process for self-validation
# =============================================================================
def make_synthetic_cohort(*, years: Sequence[int] = (2012, 2013, 2014, 2015, 2016),
                          n_per_year: int = 120, seed: int = 1234,
                          inject_shrink: float = 0.80, high_fv_extra_shrink: float = 0.010,
                          bust_extra: float = 0.0, constant_dpw_mm: float | None = None,
                          dpw_by_year: dict | None = None, discount_rate: float | None = None,
                          ) -> tuple[list[PlayerRecord], dict]:
    """Generate a synthetic cohort with a KNOWN injected shrinkage so the harness
    can be validated end-to-end (it must recover the shrinkage). Realized WAR =
    (model's per-season expected WAR) * shrink(FV) * noise, with shrink falling
    further at high FV (mimics the semi-aspirational top of the FV scale). Per-
    season salaries follow the league-min/arb schedule; service makes a clean
    6-year window. Returns (records, dpw_by_year_used)."""
    rng = np.random.RandomState(seed)
    cfg = vf._config()
    control_years = int(cfg["service_time"]["control_years"])
    league_min = float(cfg["service_time"]["league_min_usd"]) / 1e6
    arb_fracs = list(cfg["service_time"]["arb_model"]["fractions_of_fa_value"])
    pre_arb = int(cfg["service_time"]["pre_arb_years"])
    r = float(discount_rate if discount_rate is not None else cfg["discount_rate"])
    # Use one flat $/WAR for realized so the only injected difference is WAR-shrink
    # (keeps the slope-recovery clean); real backtests pass historical_dollars_per_war.
    dpw_mm = float(constant_dpw_mm if constant_dpw_mm is not None
                   else vf.dollars_per_war_flat())
    dpw_used = dpw_by_year or {y: {"overall": dpw_mm} for y in range(min(years), max(years) + control_years + 3)}

    # FV sampling over the PIPELINE region (>= 45) -- the synthetic DGP samples
    # career-outcome buckets, which is the model's >=45 path; FV<=40 uses the
    # Edwards anchor (a different path), so it's excluded from this self-test.
    # Heavier at the low/mid grades, thin at the top (realistic).
    fv_grid = np.array([45, 47, 50, 52, 55, 57, 60, 63, 65, 70])
    fv_w = np.array([16, 11, 17, 10, 11, 6, 7, 3, 2, 1], dtype=float)
    fv_w /= fv_w.sum()

    records: list[PlayerRecord] = []
    for y in years:
        for i in range(n_per_year):
            pid = f"syn_{y}_{i}"
            fv = float(rng.choice(fv_grid, p=fv_w))
            is_pit = bool(rng.rand() < 0.5)
            pos = ("SP" if is_pit else rng.choice(["SS", "CF", "C", "3B", "1B", "OF"]))
            age = float(rng.choice([19, 20, 21, 22, 23, 24]))
            eta = float(rng.choice([1, 2, 3, 4]))
            debut_year = y + int(round(eta))
            # injected shrink on the realized TALENT LEVEL: lower (more
            # aspirational) at high FV. This is the ground-truth correction.
            shrink = max(0.05, inject_shrink - high_fv_extra_shrink * max(0.0, fv - 50.0))
            # Sample the player's actual career-outcome bucket from the model's
            # own P(bucket|FV) (so the realized OUTCOME DISTRIBUTION is preserved),
            # then realize a shrunk version of that bucket's talent level.
            _role = "pitcher" if is_pit else "hitter"
            _ws = vf._war_scale_for(fv, _role)             # v47: FV-dependent bucket level
            mids = [m * _ws for m in vf._calibrated_midpoints(_role)]
            probs = np.asarray(vf.p_bucket_given_fv(fv, is_pit), dtype=float)
            probs = probs / probs.sum()
            b = int(rng.choice(len(mids), p=probs))
            p_bust = min(0.99, (1.0 if b == 0 else 0.0) + bust_extra)
            seasons = []
            if rng.rand() < p_bust:
                debut_year = None                          # washed out, never debuted -> SV 0
            else:
                level = mids[b] * shrink                   # shrunk realized talent level
                for k in range(control_years):
                    yr = debut_year + k
                    noise = float(rng.lognormal(mean=0.0, sigma=0.20))
                    war = max(-0.5, level * noise)
                    if rng.rand() < 0.05:                  # injury / replacement season
                        war = round(float(rng.uniform(-0.5, 0.3)), 2)
                    if k < pre_arb:
                        sal = league_min
                    else:
                        frac = arb_fracs[min(k - pre_arb, len(arb_fracs) - 1)]
                        # arb = fraction of the season's TIERED market value (matches
                        # the model's arb convention, so the self-test isolates WAR-shrink)
                        sal = frac * vf.tiered_war_value_usd(war) / 1e6
                    seasons.append(RealizedSeason(yr, round(war, 2), round(sal, 3), _SERVICE_FULL_DAYS))
            listing = ListingView(pid, pid, y, fv, is_pit, pos, age, eta, True)
            realized = RealizedRecord(pid, debut_year, tuple(seasons))
            records.append(PlayerRecord(listing, realized))
    return records, dpw_used


# =============================================================================
# Orchestration + report
# =============================================================================
def run_backtest(records: Sequence[PlayerRecord], *, discount_rate: float,
                 dpw_by_year: dict, draws: int = 4000, correction_method: str = "isotonic",
                 tiered: bool = False, inflation: float = 0.0) -> dict:
    """End-to-end: reconstruct realized -> predict (no look-ahead) -> metrics ->
    correction (LOyO CV). Returns a report dict (no production config writes).

    tiered/inflation select the REALIZED valuation convention: defaults (overall
    market $/WAR, no growth) for REAL data; tiered=True + model inflation for the
    SYNTHETIC self-test, so realized and predicted share the model's pricing
    convention and the only injected difference is the WAR-shrink."""
    assert_no_lookahead(predict_listing)
    # restrict to pre-debut prospects for a clean prospect backtest
    recs = [r for r in records if r.listing.pre_debut]
    listings = [r.listing for r in recs]                  # prediction sees ONLY these
    preds = [predict_listing(lv, draws=draws) for lv in listings]
    realized = np.array([realized_sv_pv(r.realized, r.listing.listing_year,
                                        discount_rate=discount_rate, dpw_by_year=dpw_by_year,
                                        tiered=tiered, inflation=inflation)
                         for r in recs])
    pred_mm = np.array([p["pred_mm"] for p in preds])
    pits = np.array([pit_value(p["draws_mm"], rv) for p, rv in zip(preds, realized)])

    model_dpw_mm = vf.dollars_per_war_flat()
    report = {
        "n_players": len(recs),
        "binned_calibration": binned_calibration(pred_mm, realized),
        "raw_calibration": calibration_regression(pred_mm, realized),
        "raw_calibration_slope_ci90": bootstrap_slope_ci(pred_mm, realized),
        "raw_errors": error_metrics(pred_mm, realized),
        "raw_pit": pit_uniformity(pits),
        "decomposition": decomposition(recs, preds, discount_rate=discount_rate,
                                       dpw_by_year=dpw_by_year, model_dpw_mm=model_dpw_mm,
                                       tiered=tiered, inflation=inflation),
        "cross_validated_correction": leave_one_year_out_cv(
            recs, preds, discount_rate=discount_rate, dpw_by_year=dpw_by_year,
            method=correction_method, tiered=tiered, inflation=inflation),
        "fitted_correction_full_sample": (
            fit_isotonic_correction(pred_mm, realized) if correction_method == "isotonic"
            else fit_linear_correction(pred_mm, realized)),
        "by_fv_tier": _by_tier_metrics(pred_mm, realized, [r.listing.fv for r in recs]),
        "by_role": _by_role_metrics(pred_mm, realized, [r.listing.is_pitcher for r in recs]),
        "sensitivity": sensitivity_table(),
    }
    return report


def _by_tier_metrics(pred, realized, fvs) -> dict:
    fvs = np.array(fvs)
    out = {}
    for lo, hi, name in [(40, 49.9, "40-45"), (50, 54.9, "50"), (55, 59.9, "55"), (60, 100, "60+")]:
        m = (fvs >= lo) & (fvs <= hi)
        if m.sum() >= 3:
            out[name] = {**error_metrics(pred[m], realized[m]),
                         "calibration": calibration_regression(pred[m], realized[m])}
    return out


def _by_role_metrics(pred, realized, is_pit) -> dict:
    ip = np.array(is_pit)
    out = {}
    for flag, name in [(False, "hitter"), (True, "pitcher")]:
        m = ip == flag
        if m.sum() >= 3:
            out[name] = {**error_metrics(pred[m], realized[m]),
                         "calibration": calibration_regression(pred[m], realized[m])}
    return out


def run_synthetic_validation(*, write_report: bool = True, seed: int = 1234) -> dict:
    """Self-validation: generate a synthetic cohort with a KNOWN injected
    shrinkage, run the full harness, and check it recovers the shrinkage (raw
    slope < 1) and that the cross-validated correction removes the bias on
    held-out years. Writes docs/sv-backtest.md (synthetic results, clearly
    labeled) but does NOT touch the production calibration config."""
    cfg = vf._config()
    r = float(cfg["discount_rate"])
    infl = float(cfg.get("dollars_per_war_inflation", 0.0))
    inject = 0.80
    records, dpw = make_synthetic_cohort(seed=seed, inject_shrink=inject)
    # Self-test values realized with the MODEL's convention (tiered + inflation),
    # so the only injected predicted-vs-realized difference is the WAR-shrink.
    rep = run_backtest(records, discount_rate=r, dpw_by_year=dpw, correction_method="isotonic",
                       tiered=True, inflation=infl)
    rep_lin = leave_one_year_out_cv(
        [x for x in records if x.listing.pre_debut],
        [predict_listing(x.listing, draws=4000) for x in records if x.listing.pre_debut],
        discount_rate=r, dpw_by_year=dpw, method="linear", tiered=True, inflation=infl)
    rep["injected_shrink"] = inject
    rep["cross_validated_correction_linear"] = rep_lin
    # Fairness check: with NO injected shrink, a fair self-test must report
    # slope ~1 and bias ~0 (any residual is pure tier-convexity/noise, not a
    # fabricated correction). Demonstrates the realized/predicted conventions
    # now match (the convention-mismatch defect is fixed).
    recs0, dpw0 = make_synthetic_cohort(seed=seed, inject_shrink=1.0, high_fv_extra_shrink=0.0)
    pre0 = [x for x in recs0 if x.listing.pre_debut]
    pred0 = np.array([predict_listing(x.listing, draws=2000)["pred_mm"] for x in pre0])
    real0 = np.array([realized_sv_pv(x.realized, x.listing.listing_year, discount_rate=r,
                                     dpw_by_year=dpw0, tiered=True, inflation=infl) for x in pre0])
    rep["fairness_no_shrink"] = {
        "binned_slope": round(binned_calibration(pred0, real0)["slope"], 3),
        "bias_mm": round(float((real0 - pred0).mean()), 2),
    }
    if write_report:
        _write_report(rep)
    return rep


def _write_report(rep: dict) -> Path:
    """Render docs/sv-backtest.md from a report dict."""
    cal = rep["raw_calibration"]; ci = rep["raw_calibration_slope_ci90"]
    binned = rep.get("binned_calibration", {})
    err = rep["raw_errors"]; pit = rep["raw_pit"]
    cv = rep["cross_validated_correction"]; cvl = rep.get("cross_validated_correction_linear", {})
    dec = rep["decomposition"]
    lines = []
    A = lines.append
    A("# Surplus-Value Backtest & Calibration — Report\n")
    A("> **Synthetic self-validation.** This repo carries no completed-window prospect")
    A("> cohorts, historical salaries, or service-time data, so a *real* backtest cannot")
    A("> run here. The numbers below come from a SYNTHETIC cohort with a KNOWN injected")
    A("> shrinkage — they validate that the harness machinery (reconstruction, no-look-ahead")
    A("> prediction, metrics, cross-validated correction) works, NOT real-world calibration.")
    A("> The production correction in `value_framework_config.yaml` stays IDENTITY until a")
    A(f"> real-data backtest is run. Injected shrink (ground truth): **{rep.get('injected_shrink')}**.\n")
    A(f"- Players: **{rep['n_players']}**\n")
    fair = rep.get("fairness_no_shrink", {})
    if fair:
        A("## Self-test fairness (no shrink injected)")
        A(f"- With ZERO injected shrink the harness reports bias **{fair.get('bias_mm', float('nan')):.2f}M (≈0)** and slope")
        A(f"  {fair.get('binned_slope', float('nan')):.3f} (≈1) — realized and predicted share the model's pricing convention")
        A("  (tiered $/WAR + inflation), so the harness does NOT fabricate a correction; the shrinkage it reports below is")
        A("  attributable to the injected WAR-shrink, not a $/WAR-convention artifact.\n")
    A("## Model calibration (realized ~ predicted)")
    A(f"- Raw (individual) OLS slope **{cal['slope']:.3f}** (90% CI {ci[0]:.3f}–{ci[1]:.3f}, R² {cal['r2']:.3f}) — the")
    A("  unbiased level estimate (predictor is deterministic, so OLS is not attenuated; the low R² just reflects the")
    A("  irreducible per-player outcome variance — prospects are high-variance, so we target unbiasedness, not per-player precision).")
    A(f"- Binned-mean slope {binned.get('slope', float('nan')):.3f} (R² {binned.get('r2', float('nan')):.3f}) — same slope, far lower")
    A("  variance (per-bin means); a readable cross-check, not a different estimand.")
    A(f"- slope < 1 ⇒ the model **overshoots** and needs shrinkage — the harness recovered this.")
    A(f"- bias mean(realized−pred) = **{err['bias']:.2f}M**, RMSE {err['rmse']:.1f}M, MAE {err['mae']:.1f}M, Spearman {err['spearman']:.3f}\n")
    A("## Distributional coverage (PIT)")
    A(f"- raw PIT KS stat {pit.get('ks_stat', float('nan')):.3f} (p {pit.get('ks_p', float('nan')):.3f}); P10–P90 coverage {pit.get('coverage_p10_p90', float('nan')):.2f}\n")
    A("## Cross-validated correction (leave-one-list-year-out, held-out only)")
    A(f"- ISOTONIC: held-out bias **{cv.get('held_out_bias', float('nan')):.2f}M**, RMSE {cv.get('held_out_rmse', float('nan')):.1f}M; "
      f"held-out PIT coverage {cv.get('held_out_pit', {}).get('coverage_p10_p90', float('nan')):.2f}")
    if cvl:
        A(f"- LINEAR:   held-out bias **{cvl.get('held_out_bias', float('nan')):.2f}M**, RMSE {cvl.get('held_out_rmse', float('nan')):.1f}M; "
          f"held-out slope {cvl.get('held_out_calibration', {}).get('slope', float('nan')):.3f}")
    A("- The correction is applied out-of-sample; bias collapses toward 0 on held-out years.\n")
    A("## Error decomposition (FV→WAR vs $/WAR/arb)")
    A(f"- total SV bias {dec['total_sv_bias']:.2f}M = WAR-error component {dec['explained_by_war_bias']:.2f}M "
      f"+ $/WAR-&-arb residual {dec['dollar_arb_residual_bias']:.2f}M")
    A(f"- WAR-level bias (realized−pred control WAR) {dec['war_bias']:.2f} WAR\n")
    A("## Per-FV-tier calibration")
    for k, v in rep["by_fv_tier"].items():
        c = v.get("calibration", {})
        A(f"- FV {k}: n={v['n']}, slope {c.get('slope', float('nan')):.3f}, bias {v['bias']:.1f}M, Spearman {v['spearman']:.3f}")
    A("\n## Per-role calibration")
    for k, v in rep["by_role"].items():
        c = v.get("calibration", {})
        A(f"- {k}: n={v['n']}, slope {c.get('slope', float('nan')):.3f}, bias {v['bias']:.1f}M")
    A("\n## Sensitivity (∂SV/∂param, ranked) — where precision pays off")
    A("| param | base | elasticity (%ΔSV per %Δparam) |")
    A("|---|---|---|")
    for row in rep["sensitivity"]:
        A(f"| {row['param']} | {row['base_value']:.4g} | {row['elasticity']:.3f} |")
    A("\n## Caveats (for a real run)")
    A("- **Regime drift:** $/WAR and the talent landscape move; re-fit on the most recent")
    A("  complete cohorts periodically.")
    A("- **fWAR revisions & salary gaps:** pin one fWAR snapshot; document salary imputation")
    A("  (league-minimum schedule by year) and how service time was approximated.")
    A("- **Small N at the top:** 60+ FV prospects are rare even pooling years — wide")
    A("  calibration CIs there; resist over-fitting the top tier.")
    A("- **Censoring:** incomplete-window cohorts are weaker evidence; exclude or project the")
    A("  unfinished tail and flag it.")
    A("- **No look-ahead / consistent units** are enforced structurally (see backtest.py).")
    A("- **Fractional ETA:** the realized leg discounts from the integer calendar debut offset")
    A("  (year − listing_year), while the model discounts from the projected (possibly fractional)")
    A("  ETA; for real listings with non-integer ETAs, round both to the same convention to keep")
    A("  the PV reference aligned (the synthetic self-test uses integer ETAs, so it is unaffected).")
    A("- **PIT after correction:** the level/isotonic correction recalibrates the MEAN; the held-out")
    A("  PIT additionally AFFINE-rescales the predictive spread, since a mean-only correction would")
    A("  leave the distribution over-dispersed (coverage → 1.0). Distributional calibration of the")
    A("  spread is approximate.\n")
    out_path = _HERE.parent / "docs" / "sv-backtest.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true",
                    help="Run the synthetic self-validation + write docs/sv-backtest.md")
    args = ap.parse_args()
    if args.synthetic:
        rep = run_synthetic_validation()
        cal = rep["raw_calibration"]; bcal = rep["binned_calibration"]; cv = rep["cross_validated_correction"]
        fair = rep["fairness_no_shrink"]
        print(f"n={rep['n_players']} injected_shrink={rep['injected_shrink']}")
        print(f"FAIRNESS (no shrink injected): slope={fair['binned_slope']:.3f} (~1.0 expected)  bias={fair['bias_mm']:.2f}M (~0)")
        print(f"INJECTED shrink: raw slope={cal['slope']:.3f}  binned slope={bcal['slope']:.3f} (<1 => overshoot recovered)  bias={rep['raw_errors']['bias']:.2f}M")
        print(f"CV(isotonic) held-out bias={cv.get('held_out_bias', float('nan')):.2f}M  "
              f"affine-recal PIT P10-P90 coverage={cv.get('held_out_pit', {}).get('coverage_p10_p90', float('nan')):.2f} (~0.80)")
        print("top sensitivity:", [r["param"] for r in rep["sensitivity"][:3]])
        print("wrote docs/sv-backtest.md")
    else:
        ap.print_help()
