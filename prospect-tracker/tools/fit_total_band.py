# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""F-01 remediation: simulated path-total quantile bands (lane R-BAND).

The projection/FA surfaces display a multi-year WAR total band as
"(P10-P90)" but build it by SUMMING the per-year quantile points
(proj_export.py warTotalP10/P90, fa_export.py warTotalP10/P90). The sum of
per-year P90s is the P90 of the total ONLY under perfect year-to-year
correlation; the displayed band is therefore systematically too wide.

This module (1) estimates the year-to-year dependence of realized WAR
outcomes around their per-year projections from the proj_eval realized
corpus, (2) builds a path-total quantile by simulating seeded per-player
paths from the per-year quantile curves under a Gaussian copula at the
estimated correlation, and (3) evaluates the pre-registered R-BAND gate on
held-out cohorts (coverage of realized multi-year totals in [0.75, 0.85];
simulated band narrower than the summed band on average; point estimates
untouched).

The estimation corpus is MLB-only (proj_eval / fa_projection); the
dependence is measured on the vet population and applied to the continuous
aging-quantile paths (vets + FA) that the same aging model produces.

Estimator: for each resolved player-season the realized bWAR is mapped to
its position u = F_year(actual) in the per-year predictive marginal (a
piecewise-linear quantile function pinned to (p10, mean, p90)); the
Gaussian-copula correlation is the Pearson correlation of consecutive-year
z = Phi^-1(u). Lag-2 is measured to choose AR(1) vs exchangeable; AR(1) is
the primary structure (WAR persistence decays with lag).

Public API used by the exports (only after the gate passes):
    simulated_total_band(mean, p10, p90, n_years=None) -> (totalP10, totalP90)

Run:  python tools/fit_total_band.py [--fit 2013-2018] [--holdout 2019-2021]
Writes data/total_band_eval.json.  SEED documented below; fully determinstic.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm, pearsonr, spearmanr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fa_projection as fp                                     # noqa: E402
import proj_eval                                               # noqa: E402

log = logging.getLogger(__name__)
ARTIFACT = ROOT / "data" / "total_band_eval.json"

SEED = 20260702                 # fixed; documented in the artifact
N_SIM = 20000                   # simulated paths per player
HORIZONS = proj_eval.HORIZONS   # 5

# Correlation structure that WOULD be applied in production had the gate
# passed (pinned as a module constant so the exports would not re-fit at render
# time). The R-BAND gate FAILED (see data/total_band_eval.json): no export
# imports this module, so this value is inert. It is the estimated AR(1) rho
# from the last fit run, kept only so a future re-run under a redesigned gate
# starts from the measured value rather than a guess.
AR1_RHO = 0.3451                # estimated AR(1) copula rho; UNUSED (gate failed)

Q_LO, Q_HI = 0.10, 0.90
_Z_LO, _Z_HI = norm.ppf(Q_LO), norm.ppf(Q_HI)   # +/-1.2816


# ---------------------------------------------------------------------------
# Per-year marginal: piecewise-linear quantile function pinned to (p10,mean,p90)
# ---------------------------------------------------------------------------
def _knots(p10: float, mean: float, p90: float):
    """Return monotone (q10, q50, q90). mean is used as the central (median)
    anchor; clamped into [p10, p90] so the marginal is non-decreasing."""
    lo = min(p10, p90)
    hi = max(p10, p90)
    mid = min(max(mean, lo), hi)
    return lo, mid, hi


def _quantile(u: float, q10: float, q50: float, q90: float) -> float:
    """Piecewise-linear quantile function through (0.10,q10),(0.50,q50),
    (0.90,q90) with slope-continued linear tails."""
    if u <= Q_LO:
        slope = (q50 - q10) / (0.50 - Q_LO)
        return q10 + (u - Q_LO) * slope
    if u <= 0.50:
        return q10 + (u - Q_LO) / (0.50 - Q_LO) * (q50 - q10)
    if u <= Q_HI:
        return q50 + (u - 0.50) / (Q_HI - 0.50) * (q90 - q50)
    slope = (q90 - q50) / (Q_HI - 0.50)
    return q90 + (u - Q_HI) * slope


def _cdf(x: float, q10: float, q50: float, q90: float) -> float:
    """Invert the piecewise-linear quantile function: return u in (0,1) with
    Q(u) = x. Monotone, so unambiguous."""
    if q90 - q10 < 1e-9:
        return 0.5
    if x <= q50:
        if q50 - q10 < 1e-9:
            return 0.50 if x >= q50 else Q_LO
        if x >= q10:
            return Q_LO + (x - q10) / (q50 - q10) * (0.50 - Q_LO)
        slope = (q50 - q10) / (0.50 - Q_LO)          # lower tail slope
        u = Q_LO + (x - q10) / slope
        return float(min(max(u, 1e-4), 0.50))
    if q90 - q50 < 1e-9:
        return 0.50 if x <= q50 else Q_HI
    if x <= q90:
        return 0.50 + (x - q50) / (q90 - q50) * (Q_HI - 0.50)
    slope = (q90 - q50) / (Q_HI - 0.50)              # upper tail slope
    u = Q_HI + (x - q90) / slope
    return float(min(max(u, Q_HI), 1 - 1e-4))


# ---------------------------------------------------------------------------
# Simulated total band (the production entry point)
# ---------------------------------------------------------------------------
def _ar1_normals(rng: np.random.Generator, n_sim: int, h: int, rho: float):
    """AR(1) standard normals: corr(z_t, z_{t+1}) = rho."""
    eps = rng.standard_normal((n_sim, h))
    z = np.empty_like(eps)
    z[:, 0] = eps[:, 0]
    s = float(np.sqrt(max(0.0, 1.0 - rho * rho)))
    for t in range(1, h):
        z[:, t] = rho * z[:, t - 1] + s * eps[:, t]
    return z


def simulated_total_band(mean, p10, p90, n_years: int | None = None,
                         rho: float | None = None, n_sim: int | None = None,
                         seed: int | None = None):
    """P10/P90 of the simulated multi-year WAR total.

    mean/p10/p90 are the per-year projection arrays (mean path + per-year
    quantile curves). Returns (totalP10, totalP90) rounded to 0.1 to match
    the incumbent field precision. Deterministic under the module SEED.

    Point estimate (sum(mean)) is NOT produced here and is never touched by
    this routine - only the band fields move."""
    rho = AR1_RHO if rho is None else rho
    n_sim = N_SIM if n_sim is None else n_sim
    h = len(mean) if n_years is None else min(n_years, len(mean))
    if h <= 0:
        return None, None
    mean = list(mean)[:h]
    p10 = list(p10)[:h]
    p90 = list(p90)[:h]
    # Degenerate / missing bands -> fall back to the comonotonic sum (no worse
    # than the incumbent; keeps the field populated).
    if any(a is None for a in p10) or any(a is None for a in p90):
        return (round(sum(x for x in p10 if x is not None), 1) if all(a is not None for a in p10) else None,
                round(sum(x for x in p90 if x is not None), 1) if all(a is not None for a in p90) else None)
    if h == 1:
        return round(p10[0], 1), round(p90[0], 1)
    rng = np.random.default_rng(SEED if seed is None else seed)
    z = _ar1_normals(rng, n_sim, h, rho)
    u = norm.cdf(z)
    totals = np.zeros(n_sim)
    for t in range(h):
        q10, q50, q90 = _knots(p10[t], mean[t], p90[t])
        # vectorised piecewise-linear quantile evaluation
        ut = u[:, t]
        yt = np.empty(n_sim)
        if q90 - q10 < 1e-9:
            yt[:] = q50
        else:
            m1 = ut <= Q_LO
            m2 = (ut > Q_LO) & (ut <= 0.50)
            m3 = (ut > 0.50) & (ut <= Q_HI)
            m4 = ut > Q_HI
            slo = (q50 - q10) / (0.50 - Q_LO)
            shi = (q90 - q50) / (Q_HI - 0.50)
            yt[m1] = q10 + (ut[m1] - Q_LO) * slo
            yt[m2] = q10 + (ut[m2] - Q_LO) / (0.50 - Q_LO) * (q50 - q10)
            yt[m3] = q50 + (ut[m3] - 0.50) / (Q_HI - 0.50) * (q90 - q50)
            yt[m4] = q90 + (ut[m4] - Q_HI) * shi
        totals += yt
    lo = float(np.quantile(totals, Q_LO))
    hi = float(np.quantile(totals, Q_HI))
    return round(lo, 1), round(hi, 1)


# ---------------------------------------------------------------------------
# Realized-corpus collection (mirrors proj_eval.run's forward-chained loop)
# ---------------------------------------------------------------------------
def _collect(bases, predict_fn=None):
    """Per player-base records: mean/p10/p90 per horizon + realized bWAR
    (absent target season = 0, both sides), forward-chained on the champion."""
    predict_fn = predict_fn or proj_eval.default_predict_fn
    corpus = fp.build_corpus()
    league = corpus["league"]
    last = corpus["last"]
    by_player = {"hit": {}, "pit": {}}
    war_actual = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side].setdefault(r["mlbam"], {})[r["season"]] = r
                if r.get("war") is not None:
                    k = (r["mlbam"], r["season"])
                    war_actual[k] = war_actual.get(k, 0.0) + r["war"]
    records = []
    for B in bases:
        curves, war_map = fp.fitted_models(corpus, B - 1)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                age_row = next((h for h in hist if h.get("age")), None)
                if age_row is None:
                    continue
                age = age_row["age"] + (B - age_row["season"])
                path = predict_fn(hist, side, B, age, curves, war_map, league)
                if path is None:
                    continue
                p10s = path.get("war_by_year_p10")
                p90s = path.get("war_by_year_p90")
                if not p10s or not p90s:
                    continue
                mean, p10, p90, act, survived = [], [], [], [], []
                for h in range(1, HORIZONS + 1):
                    target = B + h - 1
                    if target > last - 1:            # complete seasons only
                        break
                    if h - 1 >= len(p10s):
                        break
                    mean.append(path["war_by_year"][h - 1])
                    p10.append(p10s[h - 1])
                    p90.append(p90s[h - 1])
                    act.append(war_actual.get((mlbam, target), 0.0))
                    survived.append((mlbam, target) in war_actual)
                if len(mean) >= 2:
                    records.append({"mlbam": mlbam, "side": side, "base": B,
                                    "mean": mean, "p10": p10, "p90": p90,
                                    "act": act, "survived": survived,
                                    "full": len(mean) == HORIZONS})
    return records


# ---------------------------------------------------------------------------
# Dependence estimation
# ---------------------------------------------------------------------------
def estimate_dependence(records):
    """Gaussian-copula correlation of consecutive-year residuals.

    Residual position u_h = F_h(actual_h) in the per-year marginal; z_h =
    Phi^-1(u_h). Lag-1 Pearson(z_h, z_{h+1}) is the AR(1) copula rho; lag-2
    checks whether the decay is AR(1) (lag2 ~ lag1^2) or exchangeable
    (lag2 ~ lag1)."""
    lag1_a, lag1_b = [], []
    lag2_a, lag2_b = [], []
    su1_a, su1_b = [], []
    for rec in records:
        z = []
        for t in range(len(rec["mean"])):
            q10, q50, q90 = _knots(rec["p10"][t], rec["mean"][t], rec["p90"][t])
            u = _cdf(rec["act"][t], q10, q50, q90)
            u = min(max(u, 1e-4), 1 - 1e-4)
            z.append(float(norm.ppf(u)))
            su = u
            if t >= 1:
                su1_a.append(_prev_u)
                su1_b.append(su)
            _prev_u = su
        for t in range(len(z) - 1):
            lag1_a.append(z[t])
            lag1_b.append(z[t + 1])
        for t in range(len(z) - 2):
            lag2_a.append(z[t])
            lag2_b.append(z[t + 2])
    lag1 = float(pearsonr(lag1_a, lag1_b)[0]) if len(lag1_a) > 2 else None
    lag2 = float(pearsonr(lag2_a, lag2_b)[0]) if len(lag2_a) > 2 else None
    spear1 = float(spearmanr(su1_a, su1_b)[0]) if len(su1_a) > 2 else None
    return {
        "n_lag1_pairs": len(lag1_a), "n_lag2_pairs": len(lag2_a),
        "ar1_rho_pearson_z": round(lag1, 4) if lag1 is not None else None,
        "lag2_rho_pearson_z": round(lag2, 4) if lag2 is not None else None,
        "lag1_spearman_u": round(spear1, 4) if spear1 is not None else None,
        "implied_ar1_from_lag2": round(float(np.sqrt(lag2)), 4) if (lag2 and lag2 > 0) else None,
    }


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------
def evaluate_gate(holdout_records, rho, n_sim=N_SIM, seed=SEED):
    """R-BAND gate on holdout: coverage of realized multi-year totals,
    width vs summed band, and point-estimate invariance."""
    full = [r for r in holdout_records if r["full"]]
    n_in_sim = n_in_sum = 0
    sim_below = sim_above = sum_below = sum_above = 0
    sim_widths, sum_widths = [], []
    by_side = {"hit": [0, 0], "pit": [0, 0]}
    sv_in_sim = sv_in_sum = sv_n = 0
    for rec in full:
        realized = sum(rec["act"])
        s10, s90 = simulated_total_band(rec["mean"], rec["p10"], rec["p90"],
                                        rho=rho, n_sim=n_sim, seed=seed)
        sum10 = sum(rec["p10"])
        sum90 = sum(rec["p90"])
        in_sim = s10 <= realized <= s90
        in_sum = sum10 <= realized <= sum90
        n_in_sim += in_sim
        n_in_sum += in_sum
        sim_below += realized < s10
        sim_above += realized > s90
        sum_below += realized < sum10
        sum_above += realized > sum90
        sim_widths.append(s90 - s10)
        sum_widths.append(sum90 - sum10)
        by_side[rec["side"]][0] += in_sim
        by_side[rec["side"]][1] += 1
        if all(rec["survived"]):        # played every window year (no dropout 0s)
            sv_n += 1
            sv_in_sim += in_sim
            sv_in_sum += in_sum
    n = len(full)
    cov_sim = n_in_sim / n if n else None
    cov_sum = n_in_sum / n if n else None
    mean_sim_w = float(np.mean(sim_widths)) if sim_widths else None
    mean_sum_w = float(np.mean(sum_widths)) if sum_widths else None
    return {
        "n_holdout_full_window": n,
        "coverage_simulated": round(cov_sim, 4) if cov_sim is not None else None,
        "coverage_summed_incumbent": round(cov_sum, 4) if cov_sum is not None else None,
        "mean_width_simulated": round(mean_sim_w, 3) if mean_sim_w is not None else None,
        "mean_width_summed_incumbent": round(mean_sum_w, 3) if mean_sum_w is not None else None,
        "width_ratio_sim_over_sum": (round(mean_sim_w / mean_sum_w, 4)
                                     if mean_sum_w else None),
        "coverage_by_side": {s: (round(v[0] / v[1], 4) if v[1] else None, v[1])
                             for s, v in by_side.items()},
        # Tail-miss decomposition: WHERE realized totals escape each band. The
        # summed band's misses are dominated by the DOWNSIDE (attrition: players
        # who leave the league realize ~0, below a strictly-positive p10 path),
        # which no narrowing can fix - it only makes the downside miss worse.
        "summed_frac_below_p10": round(sum_below / n, 4) if n else None,
        "summed_frac_above_p90": round(sum_above / n, 4) if n else None,
        "simulated_frac_below_p10": round(sim_below / n, 4) if n else None,
        "simulated_frac_above_p90": round(sim_above / n, 4) if n else None,
        # Survived-all subset (played every window year): removes the dropout-0
        # attrition mass to isolate the width question on rostered players.
        "n_survived_all_window": sv_n,
        "coverage_summed_survived_all": round(sv_in_sum / sv_n, 4) if sv_n else None,
        "coverage_simulated_survived_all": round(sv_in_sim / sv_n, 4) if sv_n else None,
    }


def coverage_vs_rho(holdout_records, rhos=(0.0, 0.2, 0.3451, 0.5, 0.7, 0.9, 0.99),
                    n_sim=6000, seed=SEED):
    """Coverage/width as a function of the copula rho: shows coverage is
    monotone increasing in rho and tops out at the comonotonic (summed) band,
    so no admissible narrowing reaches the 0.75 gate floor."""
    full = [r for r in holdout_records if r["full"]]
    rows = []
    for rho in rhos:
        nin = 0
        ws = []
        for rec in full:
            s10, s90 = simulated_total_band(rec["mean"], rec["p10"], rec["p90"],
                                            rho=rho, n_sim=n_sim, seed=seed)
            realized = sum(rec["act"])
            nin += s10 <= realized <= s90
            ws.append(s90 - s10)
        rows.append({"rho": rho, "coverage": round(nin / len(full), 4),
                     "mean_width": round(float(np.mean(ws)), 3)})
    return rows


def _example_players(holdout_records, rho, names=None, k=3):
    """Before/after band widths for a few example holdout players."""
    full = [r for r in holdout_records if r["full"]]
    full = sorted(full, key=lambda r: -sum(r["mean"]))       # top projected
    out = []
    for rec in full[:k]:
        s10, s90 = simulated_total_band(rec["mean"], rec["p10"], rec["p90"], rho=rho)
        out.append({
            "mlbam": rec["mlbam"], "side": rec["side"], "base": rec["base"],
            "point_warTotal": round(sum(rec["mean"]), 1),
            "summed_band": [round(sum(rec["p10"]), 1), round(sum(rec["p90"]), 1)],
            "summed_width": round(sum(rec["p90"]) - sum(rec["p10"]), 1),
            "simulated_band": [s10, s90],
            "simulated_width": round(s90 - s10, 1),
            "realized_total": round(sum(rec["act"]), 1),
        })
    return out


def run(fit_bases, holdout_bases, persist=True):
    log.info("collecting fit corpus %s ...", fit_bases)
    fit_records = _collect(fit_bases)
    log.info("collecting holdout corpus %s ...", holdout_bases)
    holdout_records = _collect(holdout_bases)
    dep = estimate_dependence(fit_records)
    rho = dep["ar1_rho_pearson_z"] or 0.0
    rho = float(min(max(rho, 0.0), 0.99))
    gate = evaluate_gate(holdout_records, rho)
    rho_sweep = coverage_vs_rho(holdout_records)

    cov = gate["coverage_simulated"]
    c1 = cov is not None and 0.75 <= cov <= 0.85
    c2 = (gate["width_ratio_sim_over_sum"] is not None
          and gate["width_ratio_sim_over_sum"] < 1.0)
    c3 = True   # point estimates are never touched by this routine (structural)
    verdict = c1 and c2 and c3

    loss = None
    if not verdict:
        loss = []
        if not c1:
            loss.append(
                f"C1 FAIL: simulated coverage {cov} is outside the [0.75,0.85] gate band. "
                f"Root cause is NOT band width: the incumbent COMONOTONIC summed band "
                f"(the widest admissible, rho->1) already covers only "
                f"{gate['coverage_summed_incumbent']} of realized multi-year totals, well "
                f"below the 0.75 floor. It UNDER-covers, so the F-01 premise that the "
                f"displayed band is 'too wide' does not hold against realized totals.")
            loss.append(
                f"The summed band's misses are downside-dominated: "
                f"{gate['summed_frac_below_p10']} of realized totals fall BELOW its p10 "
                f"(attrition -- players who leave the league realize ~0 WAR, below a "
                f"strictly-positive decayed p10 path) vs {gate['summed_frac_above_p90']} "
                f"above p90. The per-year quantile marginals carry no full-dropout zero "
                f"floor, so the total band is MIS-CENTERED (too high), not too wide.")
            loss.append(
                f"Coverage is monotone increasing in the copula rho and tops out at the "
                f"comonotonic band: {[(r['rho'], r['coverage']) for r in rho_sweep]}. "
                f"No admissible rho (<1) reaches 0.75; the mathematically-correct "
                f"dependence fix (narrowing) moves coverage AWAY from the 0.80 target.")
            loss.append(
                f"Even on the survived-all-window subset (n="
                f"{gate['n_survived_all_window']}, dropout-0 mass removed), the summed "
                f"band covers only {gate['coverage_summed_survived_all']} and the "
                f"simulated {gate['coverage_simulated_survived_all']}: the marginals "
                f"undercover on rostered players too, so this is not solely an attrition "
                f"artifact.")
        if not c2:
            loss.append(f"C2 FAIL: simulated band not narrower: width ratio "
                        f"{gate['width_ratio_sim_over_sum']}")
        loss.append(
            "Disposition per R-BAND pre-registration: FAIL -> touch NO export code. "
            "The owner-approved fallback (drop the total P10-P90 bands from display) is "
            "a separate decision; the summed bands remain in the payloads unchanged. "
            "This gate result is evidence FOR that fallback: the displayed total bands "
            "are miscalibrated (undercover, mis-centered), and the dependence-correct "
            "replacement is narrower and therefore covers even less.")

    artifact = {
        "experiment": "R-BAND (F-01): simulated path-total quantile bands",
        "generated_by": "tools/fit_total_band.py",
        "seed": SEED, "n_sim": N_SIM, "horizons": HORIZONS,
        "method": (
            "Per-year predictive marginal = piecewise-linear quantile function "
            "pinned to (p10, mean, p90) with slope-continued tails. Year-to-year "
            "dependence = Gaussian copula, AR(1) structure, rho = Pearson corr of "
            "consecutive-year z=Phi^-1(F_year(realized bWAR)) on the fit cohort. "
            "Total band = P10/P90 of N_SIM seeded simulated path sums (inverse-CDF "
            "sampling of the per-year marginals under the AR(1) copula). Estimation "
            "corpus is MLB-only (proj_eval/fa_projection), champion marcel_decay_v2, "
            "forward-chained (fit<=B-1, score complete seasons only)."),
        "fit_bases": fit_bases, "holdout_bases": holdout_bases,
        "n_fit_records": len(fit_records),
        "n_holdout_records": len(holdout_records),
        "dependence": dep,
        "applied_ar1_rho": rho,
        "coverage_vs_rho": rho_sweep,
        "gate": {
            "conditions": {
                "c1_coverage_in_0.75_0.85": c1,
                "c2_simulated_narrower_than_summed": c2,
                "c3_point_estimates_untouched": c3,
            },
            "metrics": gate,
            "verdict": "PASS" if verdict else "FAIL",
        },
        "examples_top_projected": _example_players(holdout_records, rho),
        "scope_note": (
            "Dependence measured on the MLB vet corpus; applied to the continuous "
            "aging-quantile paths (vets + FA) produced by the same aging model. "
            "Prospect bucket paths (proj_export _prospect_rows) are a discrete "
            "career-trait mixture, a different statistical object with no realized "
            "FV->outcome corpus join; handling documented in the export change."),
    }
    if loss is not None:
        artifact["loss_ledger"] = loss

    if persist:
        ARTIFACT.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
        log.info("wrote %s", ARTIFACT)
    return artifact


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", default="2013-2018")
    ap.add_argument("--holdout", default="2019-2021")
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()

    def _parse(spec):
        if "-" in spec and "," not in spec:
            a, b = spec.split("-")
            return list(range(int(a), int(b) + 1))
        return [int(x) for x in spec.split(",")]

    art = run(_parse(args.fit), _parse(args.holdout), persist=not args.no_persist)
    g = art["gate"]
    print("\n==== R-BAND gate ====")
    print("dependence:", json.dumps(art["dependence"]))
    print("applied AR1 rho:", art["applied_ar1_rho"])
    print("metrics:", json.dumps(g["metrics"], indent=1))
    print("conditions:", json.dumps(g["conditions"]))
    print("VERDICT:", g["verdict"])
    for ex in art["examples_top_projected"]:
        print(f"  {ex['side']} {ex['mlbam']} base{ex['base']}: point {ex['point_warTotal']} "
              f"summed {ex['summed_band']} (w{ex['summed_width']}) -> "
              f"sim {ex['simulated_band']} (w{ex['simulated_width']}) | real {ex['realized_total']}")


if __name__ == "__main__":
    main()
