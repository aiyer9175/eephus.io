# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The two-stage arbitration award model, and its baselines.

STAGE 1 (arb 1): a level model on log(deflated salary). There is no prior
arbitration salary to raise from, so the first trip is a different statistic
class and gets its own model, its own baseline and its own floor. Pooling it
with arb2+ lets the raise model's mechanical accuracy carry it.

STAGE 2 (arb 2/3/4): a RAISE model, because that is what the process is. The
CBA's maximum-cut rule floors the outcome at 0.80x the prior salary, and the
floor is imposed as a TRANSFORMED TARGET rather than a clamp:

    z      = log(s_t / s_{t-1} - f),      f = 0.795
    s_hat  = s_{t-1} * (f + exp(z_hat))

The feasible region (f, inf) maps to the whole real line, so EVERY prediction,
every bootstrap draw and every band endpoint respects the CBA by construction. A
clamp fixes only the point estimate and leaves the lower band arm dangling below
a legally impossible value. f sits a hair under 0.80 so boundary rows stay
finite.

Three costs of the transform, stated rather than discovered later:
  1. E[s] != s_{t-1}(f + exp(E[z])). A Jensen/smearing term is fit PER ARB STEP.
  2. Loss in z space is not loss in dollars, so every reported metric is computed
     after the inverse transform, in deflated dollars.
  3. The transform is undefined below the floor - which is a feature. It turns
     contamination into a parse error instead of a silent bias.

WHY RIDGE AND NOT A BOOSTED ENSEMBLE. The serve path must be pure arithmetic
over a committed JSON, and a linear model serialises to coefficients while an
ensemble does not. Per-fold n is 150-250. And this repo has already run
LightGBM against transparent OLS on a dollars target twice - fa_market_ml lost
all three ship criteria, and the ML WAR-input path failed Gate 2. The primitives
are IMPORTED from tools/efv_mde_lab rather than reimplemented, which is the
explicit rule at tools/efv_power_lab.py:22-24.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np                                              # noqa: E402

ROOT = Path(__file__).parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from efv_mde_lab import ridge_fit, ridge_pred                   # noqa: E402

MAX_CUT_FLOOR = 0.795

# Projectable features ONLY. Every one is available from the existing MLB
# projection at the tender deadline, which is what makes the backtest and the
# forward projection the same model. Counting stats (HR, RBI, SB, saves, holds)
# are DIAGNOSTIC-ONLY and live in CEILING_KEYS: arbitration panels reward them
# and nothing in this pipeline projects them forward, so serving them would mean
# the forecast could not reproduce the backtest.
CHAMPION_KEYS = (
    "arb_year", "super_two", "log_prior_salary", "has_prior",
    "war", "war3", "career_war", "age",
    "pa_share", "ip_share", "gs_share",
    "is_pitcher", "is_reliever",
    "hem", "sem", "rem",
)
CEILING_KEYS = CHAMPION_KEYS + ("hr", "sb", "sv", "hld")


def _f(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def features(row: dict, metrics: dict | None, keys=CHAMPION_KEYS) -> list[float]:
    """One feature vector. `metrics` is the arb_metrics block for that
    player-season, or None."""
    m = metrics or {}
    prior = row.get("prior_salary")
    pa = _f(row.get("pa"))
    ipouts = _f(row.get("ipouts"))
    is_pit = 1.0 if ipouts > 0 and pa < 50 else 0.0
    gs = _f(row.get("gs"))
    vals = {
        "arb_year": _f(row.get("arb_year")),
        "super_two": 1.0 if row.get("super_two") else 0.0,
        # log(prior) with a 0 placeholder when absent; `has_prior` carries the
        # missingness so the model is never told a missing prior is a cheap one.
        "log_prior_salary": math.log(prior) if prior else 0.0,
        "has_prior": 1.0 if prior else 0.0,
        "war": _f(row.get("war")),
        "war3": _f(row.get("war3")),
        "career_war": _f(row.get("career_war")),
        "age": _f(row.get("age"), 27.0),
        "pa_share": pa / 650.0,
        "ip_share": ipouts / 600.0,
        "gs_share": gs / 32.0,
        "is_pitcher": is_pit,
        "is_reliever": 1.0 if (is_pit and gs < 5 and ipouts > 0) else 0.0,
        "hem": _f(m.get("hem"), 100.0) / 100.0,
        "sem": _f(m.get("sem"), 100.0) / 100.0,
        "rem": _f(m.get("rem"), 100.0) / 100.0,
        "hr": _f(m.get("hr")) / 30.0,
        "sb": _f(m.get("sb")) / 20.0,
        "sv": _f(m.get("sv")) / 30.0,
        "hld": _f(m.get("hld")) / 20.0,
    }
    return [vals[k] for k in keys]


# --------------------------------------------------------------------------- #
# Deflator
# --------------------------------------------------------------------------- #

def fit_deflator(rows: list[dict], *, base_year: int) -> dict[int, float]:
    """League-wide arbitration salary index, normalised to base_year = 1.0.

    Year effects from a least-squares fit of log(salary) on arb-step dummies, a
    production term and year dummies, so the year effect is not absorbing
    production drift.

    MUST BE FIT ON TRAIN YEARS ONLY. Fitting once on the whole panel and then
    scoring folds against it gives every test year its own fitted mean, which is
    leakage of exactly the kind that shipped 260 as-of violations inside a
    matrix documenting itself as leak-free. The caller enforces this; the A5
    leak twin measures what it is worth.
    """
    rows = [r for r in rows if r.get("salary") and r.get("arb_year")]
    if len(rows) < 30:
        return {}
    years = sorted({int(r["season"]) for r in rows})
    steps = sorted({int(r["arb_year"]) for r in rows})
    cols = []
    y = []
    for r in rows:
        v = [1.0, _f(r.get("war")), _f(r.get("war")) ** 2]
        v += [1.0 if int(r["arb_year"]) == s else 0.0 for s in steps[1:]]
        v += [1.0 if int(r["season"]) == yr else 0.0 for yr in years[1:]]
        cols.append(v)
        y.append(math.log(float(r["salary"])))
    X = np.asarray(cols, float)
    beta, *_ = np.linalg.lstsq(X, np.asarray(y, float), rcond=None)
    off = 3 + len(steps) - 1
    eff = {years[0]: 0.0}
    for i, yr in enumerate(years[1:]):
        eff[yr] = float(beta[off + i])
    base = eff.get(int(base_year), 0.0)
    return {yr: math.exp(v - base) for yr, v in eff.items()}


def deflate(salary: float, season: int, defl: dict[int, float]) -> float:
    d = defl.get(int(season))
    if not d or d <= 0:
        # An unseen year (the test fold, under a train-only deflator) carries
        # the last known level forward rather than silently dividing by 1.0.
        known = sorted(defl)
        if not known:
            return float(salary)
        d = defl[known[-1] if int(season) > known[-1] else known[0]]
    return float(salary) / d


# --------------------------------------------------------------------------- #
# Baselines
# --------------------------------------------------------------------------- #

def fit_step_multipliers(rows: list[dict], defl: dict) -> dict[int, float]:
    """B1: the median deflated raise multiplier per arbitration step.

    THIS, not carry-forward, is the baseline the champion must beat.
    Carry-forward is a strawman: it is biased low by exactly the mean raise, and
    the maximum-cut rule floors the label, so an intercept beats it.
    """
    by: dict[int, list[float]] = {}
    for r in rows:
        p, s = r.get("prior_salary"), r.get("salary")
        if not p or not s or not r.get("arb_year"):
            continue
        a = deflate(s, r["season"], defl)
        b = deflate(p, r["season"] - 1, defl)
        if b > 0:
            by.setdefault(int(r["arb_year"]), []).append(a / b)
    return {k: float(np.median(v)) for k, v in by.items() if v}


SALARY_BANDS = ((0, 2e6), (2e6, 5e6), (5e6, 10e6), (10e6, float("inf")))


def _band(prior_usd: float) -> int:
    for i, (lo, hi) in enumerate(SALARY_BANDS):
        if lo <= prior_usd < hi:
            return i
    return len(SALARY_BANDS) - 1


def fit_banded_multipliers(rows: list[dict], defl: dict) -> dict:
    """Median observed raise multiplier by (arb step, prior-salary band).

    THIS IS WHAT THE BOARD SERVES FOR ARB 2/3/4, because GATE A ruled the
    per-player model a NULL there: it does not beat a step multiplier by more
    than the measured floor, so serving the model would be serving a more
    complex estimator the evidence does not support.

    The band matters and is measured, not assumed. Observed median ratios on
    the scored pool fall steeply with the prior salary:
        prior < $2M   1.70 (n=183)
        $2-5M         1.56 (n=202)
        $5-10M        1.43 (n=69)
        $10M+         1.37 (n=20)
    A step-only multiplier ignores that and compounds a small-salary raise onto
    a large one. Chaining it three times took a $4.15M arb-1 player to $48M,
    which is above the largest arbitration award ever made.
    """
    by: dict[tuple, list[float]] = {}
    for r in rows:
        p, s = r.get("prior_salary"), r.get("salary")
        step = int(r.get("arb_year") or 0)
        if not p or not s or step < 2:
            continue
        a = deflate(s, r["season"], defl)
        b = deflate(p, r["season"] - 1, defl)
        if b > 0:
            by.setdefault((step, _band(p)), []).append(a / b)
    out = {}
    for k, v in by.items():
        if len(v) >= 8:
            out[k] = float(np.median(v))
    # Band-only fallback for thin (step, band) cells.
    byband: dict[int, list[float]] = {}
    for (step, band), v in by.items():
        byband.setdefault(band, []).extend(v)
    return {"cells": out,
            "by_band": {b: float(np.median(v)) for b, v in byband.items() if v}}


def banded_predict(row: dict, mult: dict, defl: dict) -> float | None:
    """Served arb2+ estimate: prior salary times the empirical multiplier for
    its (step, band), floored at the max cut and the league minimum."""
    p = row.get("prior_salary")
    step = int(row.get("arb_year") or 0)
    if not p or step < 2 or not mult:
        return None
    band = _band(p)
    m = mult["cells"].get((step, band)) or mult["by_band"].get(band) or 1.4
    base = deflate(p, row["season"] - 1, defl)
    lm = deflate(_f(row.get("league_min"), 700_000.0), row["season"], defl)
    return max(base * m, base * 0.80, lm)


def baseline_b1(row: dict, mult: dict[int, float], defl: dict) -> float | None:
    """Predicted DEFLATED salary under the step-multiplier baseline, floored at
    both the maximum cut and the league minimum."""
    p = row.get("prior_salary")
    if not p:
        return None
    m = mult.get(int(row["arb_year"]), 1.0)
    base = deflate(p, row["season"] - 1, defl)
    lm = deflate(_f(row.get("league_min"), 700_000.0), row["season"], defl)
    return max(base * m, base * 0.80, lm)


def baseline_b0(row: dict, defl: dict) -> float | None:
    p = row.get("prior_salary")
    return deflate(p, row["season"] - 1, defl) if p else None


def fit_arb1_baselines(rows: list[dict], defl: dict) -> dict:
    """arb-1 baselines. A LAG BASELINE IS THE WRONG BAR FOR THE FIRST TRIP.

    A first-time arbitration player's "prior salary" is a pre-arb renewal near
    the league minimum, so a step multiplier off it is both enormous and wildly
    noisy - and it only exists for the minority of rows that carry a prior
    figure at all. Measured: pairing the champion against B1 on arb-1 scored
    only 199 of 513 rows, and the 314 it dropped were the players whose first
    arbitration award is the whole question.

    So arb-1 gets a no-lag pair, on ALL its rows:
      A1  intercept  - the train-year median deflated arb-1 award. The honest
                       "no information" bar.
      A2  + one WAR term - the bar that asks whether the model carries anything
                       beyond a single production number.
    """
    vals, xs, ys = [], [], []
    for r in rows:
        if int(r.get("arb_year") or 0) != 1 or not r.get("salary"):
            continue
        d = deflate(r["salary"], r["season"], defl)
        vals.append(d)
        xs.append(_f(r.get("war")))
        ys.append(math.log(d))
    if len(vals) < 20:
        return {}
    out = {"median": float(np.median(vals))}
    x = np.asarray(xs, float)
    y = np.asarray(ys, float)
    if float(((x - x.mean()) ** 2).sum()) > 0:
        b = float(((x - x.mean()) * (y - y.mean())).sum()
                  / ((x - x.mean()) ** 2).sum())
        a = float(y.mean() - b * x.mean())
        resid = y - (a + b * x)
        out["war_ols"] = (a, b, float(np.mean(np.exp(resid))))
    return out


def baseline_a1(row: dict, base: dict) -> float | None:
    """arb-1 intercept baseline."""
    return base.get("median") if base else None


def baseline_a2(row: dict, base: dict) -> float | None:
    """arb-1 intercept plus one WAR term, smearing-corrected."""
    if not base or "war_ols" not in base:
        return None
    a, b, smear = base["war_ols"]
    return float(math.exp(a + b * _f(row.get("war"))) * smear)


# --------------------------------------------------------------------------- #
# The two stages
# --------------------------------------------------------------------------- #

def fit_stage1(rows, metrics_by, defl, keys=CHAMPION_KEYS):
    """arb-1: level model on log(deflated salary)."""
    X, y = [], []
    for r in rows:
        if int(r["arb_year"]) != 1 or not r.get("salary"):
            continue
        X.append(features(r, _mx(metrics_by, r), keys))
        y.append(math.log(deflate(r["salary"], r["season"], defl)))
    if len(y) < 20:
        return None
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    m = ridge_fit(X, y, np.ones(len(y)))
    resid = y - ridge_pred(m, X)
    # Duan smearing: E[exp(e)] on the residuals, so the served point is the
    # conditional MEAN. exp(mu_hat) alone understates every award by exp(s^2/2)
    # (about 4.6% at a residual log-sd of 0.30), which becomes a same-signed
    # OVERSTATEMENT of surplus for every player.
    smear = float(np.mean(np.exp(resid)))
    return {"m": m, "smear": smear, "keys": list(keys)}


def fit_stage2(rows, metrics_by, defl, keys=CHAMPION_KEYS):
    """arb-2/3/4: raise model on the floor-transformed target."""
    X, y, steps = [], [], []
    for r in rows:
        if int(r["arb_year"]) < 2 or not r.get("salary") or not r.get("prior_salary"):
            continue
        a = deflate(r["salary"], r["season"], defl)
        b = deflate(r["prior_salary"], r["season"] - 1, defl)
        if b <= 0:
            continue
        ratio = a / b
        if ratio <= MAX_CUT_FLOOR:
            # Definitionally not an award (CBA Article VI). arb_dataset already
            # removes these; the guard is here so a caller that skips the panel
            # cannot inject one.
            continue
        X.append(features(r, _mx(metrics_by, r), keys))
        y.append(math.log(ratio - MAX_CUT_FLOOR))
        steps.append(int(r["arb_year"]))
    if len(y) < 20:
        return None
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    m = ridge_fit(X, y, np.ones(len(y)))
    resid = y - ridge_pred(m, X)
    smear_by = {}
    for s in sorted(set(steps)):
        idx = [i for i, v in enumerate(steps) if v == s]
        smear_by[s] = float(np.mean(np.exp(resid[idx]))) if idx else 1.0
    return {"m": m, "smear_by_step": smear_by, "keys": list(keys),
            "floor": MAX_CUT_FLOOR}


def _mx(metrics_by, row):
    return (metrics_by.get(int(row["season"])) or {}).get(int(row["mlbam"]))


def predict(row, metrics_by, defl, s1, s2):
    """Predicted DEFLATED salary, smearing-corrected. None when the model has
    nothing to say (an arb2+ row with no prior salary)."""
    step = int(row["arb_year"])
    if step == 1:
        if not s1:
            return None
        x = np.asarray([features(row, _mx(metrics_by, row), s1["keys"])], float)
        return float(math.exp(ridge_pred(s1["m"], x)[0]) * s1["smear"])
    if not s2 or not row.get("prior_salary"):
        return None
    x = np.asarray([features(row, _mx(metrics_by, row), s2["keys"])], float)
    z = float(ridge_pred(s2["m"], x)[0])
    sm = s2["smear_by_step"].get(step, 1.0)
    b = deflate(row["prior_salary"], row["season"] - 1, defl)
    return float(b * (s2["floor"] + math.exp(z) * sm))


# --------------------------------------------------------------------------- #
# Forward-chained evaluation
# --------------------------------------------------------------------------- #

def forward_chain(rows, metrics_by, *, seasons, keys=CHAMPION_KEYS,
                  leak_deflator=False):
    """Train strictly on earlier class years, score the next one.

    Returns per-row records carrying the champion and all three baselines, so
    every comparison is same-rows same-fold. `leak_deflator=True` is the A5 LEAK
    TWIN: it fits the deflator on the whole panel instead of train-only, and the
    difference between the two runs is what deflator leakage is worth.
    """
    seasons = sorted(seasons)
    out = []
    for i in range(1, len(seasons)):
        test_y = seasons[i]
        tr = [r for r in rows if r["season"] < test_y]
        te = [r for r in rows if r["season"] == test_y]
        if len(tr) < 60 or len(te) < 15:
            continue
        defl_rows = rows if leak_deflator else tr
        defl = fit_deflator(defl_rows, base_year=seasons[0])
        mult = fit_step_multipliers(tr, defl)
        banded = fit_banded_multipliers(tr, defl)
        a_base = fit_arb1_baselines(tr, defl)
        s1 = fit_stage1(tr, metrics_by, defl, keys)
        s2 = fit_stage2(tr, metrics_by, defl, keys)
        for r in te:
            if not r.get("salary"):
                continue
            step = int(r["arb_year"])
            actual = deflate(r["salary"], r["season"], defl)
            rec = {
                "mlbam": r["mlbam"], "name": r["name"], "season": test_y,
                "arb_year": step,
                "actual": actual,
                "champion": predict(r, metrics_by, defl, s1, s2),
                "b0": baseline_b0(r, defl),
            }
            # The bar depends on the statistic class. arb-1 has no arbitration
            # prior to raise from, so it is scored against the no-lag pair; the
            # lag baseline is reported for arb2+ where it is the right bar.
            if step == 1:
                rec["bar"] = baseline_a1(r, a_base)
                rec["bar2"] = baseline_a2(r, a_base)
                rec["bar_name"] = "arb1_intercept"
            else:
                rec["bar"] = baseline_b1(r, mult, defl)
                rec["bar2"] = None
                rec["bar_name"] = "b1_step_multiplier"
            rec["b1"] = baseline_b1(r, mult, defl)
            # THE SERVED ESTIMATOR, which is what the board actually shows and
            # therefore what the history must score. GATE A selects it per step:
            # the model for arb-1 (PASSED at 3.25x its floor), the empirical
            # banded multiplier for arb2+ (the model is a NULL there). Scoring
            # the history against something the board does not serve would make
            # the accuracy panel describe a different product.
            rec["served"] = (rec["champion"] if step == 1
                             else banded_predict(r, banded, defl))
            out.append(rec)
    return out


def paired(recs, *keys):
    """Rows where EVERY named prediction exists.

    Comparisons must be same-rows or they are not comparisons. The champion
    abstains on an arb2+ row with no prior salary while a baseline may not, so
    scoring each on its own row set silently compares two different populations
    - and the population the champion drops is exactly the one with a broken
    salary chain, i.e. the hardest rows.
    """
    return [r for r in recs
            if r.get("actual")
            and all(r.get(k) is not None for k in keys)]


def mse(recs, key) -> float | None:
    v = [(r[key] - r["actual"]) ** 2 for r in recs
         if r.get(key) is not None and r.get("actual") is not None]
    return float(np.mean(v)) if v else None


def mdape(recs, key) -> float | None:
    v = [abs(r[key] - r["actual"]) / r["actual"] for r in recs
         if r.get(key) and r.get("actual")]
    return float(np.median(v)) if v else None


def compare(recs, a: str, b: str) -> dict:
    """Paired comparison of two prediction keys on identical rows."""
    p = paired(recs, a, b)
    if not p:
        return {"n": 0}
    return {
        "n": len(p),
        f"mse_{a}": mse(p, a), f"mse_{b}": mse(p, b),
        f"mdape_{a}": mdape(p, a), f"mdape_{b}": mdape(p, b),
        "mse_delta": (mse(p, b) - mse(p, a)),
        "mdape_delta": (mdape(p, b) - mdape(p, a)),
    }
