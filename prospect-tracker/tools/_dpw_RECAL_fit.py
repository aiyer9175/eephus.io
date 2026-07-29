# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- refit + validate the surplus calibration (READ-ONLY lab).

Axes (every one of them is a documented decision the parent must see):
  scale    raw | norm     which FV the pool is built on
  gate     raw | norm     which scale the MIN_FV=40 pool gate is applied on
  anchors  shipped | norm fv_to_6yr_avg_war (sits UNDER the calibration)
  dpw      current | recon  $/WAR level (fa_implied off/on + escalation)
  target   today | era     how realized production is priced

The engine config is mutated IN PLACE on the cached dict (never rebound: a
rebind is invisible to modules that did `from value_framework import _config`)
and _reset_derived_caches() is called, mirroring the harness fix the divergence
lane recorded.

Fit = floored linear, the shipped v5 form: corrected = max(0, a*raw + b), a,b by
OLS of realized on raw predicted.

Nothing here writes to a production path.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                   # noqa: E402
from backtest import _SERVICE_FULL_DAYS                        # noqa: E402

SCRATCH = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
               r"\c--Users-noah-baseball-projects-BaseballR"
               r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")

CONTROL_YEARS = 6
LAST_FULL_SEASON = 2025
MIN_FV = 40.0
SHIPPED = (1.382491, -2.318551)          # linearmap-v5-todaypriced-2026-07-24


# --------------------------------------------------------------------------
# config regimes (in-place mutation of the cached dict)
# --------------------------------------------------------------------------
def set_regime(dpw: str, anchors: str, anchors_tbl: dict | None = None) -> dict:
    """dpw:
         current    as shipped (clemens_2026: flat 11.74M, fa_implied off, infl 0)
         recon_lvl  fa_implied re-anchor ON, escalation unchanged at 0.0 -- the
                    divergence lane's actual recommendation (the escalation gap is
                    a double-counted-growth bug on the FA side, fixed there)
         recon_full recon_lvl + the FA series escalation 0.0483 adopted on the
                    prospect side too (sensitivity arm only)"""
    cfg = vf._config()
    if not hasattr(set_regime, "_base"):
        set_regime._base = {
            "flat": float(cfg["dollars_per_war"]["flat"]),
            "rates": dict(cfg["dollars_per_war"]["tiered"]["rates"]),
            "infl": float(cfg.get("dollars_per_war_inflation", 0.0) or 0.0),
            "anchors": dict((vf._fitted().get("empirical_anchors") or {}).get("anchors") or {}),
        }
    b = set_regime._base
    # always restore the shipped level first, so regimes never compound
    cfg["dollars_per_war"]["flat"] = b["flat"]
    cfg["dollars_per_war"]["tiered"]["rates"] = dict(b["rates"])
    cfg["dollars_per_war"]["_fa_reanchor"] = None
    cfg["dollars_per_war_inflation"] = b["infl"]
    if dpw in ("recon_lvl", "recon_full"):
        was = cfg["dollars_per_war"].setdefault("fa_implied", {}).get("enabled")
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = True
        vf._apply_fa_implied_reanchor(cfg)          # the SHIPPED code path, in place
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = was
        if dpw == "recon_full":
            cfg["dollars_per_war_inflation"] = 0.0483099
    elif dpw != "current":
        raise ValueError(dpw)
    fit = vf._fitted()
    fit["empirical_anchors"]["anchors"] = dict(
        b["anchors"] if anchors == "shipped" else anchors_tbl)
    vf._reset_derived_caches()
    return {"flat_usd_per_war": cfg["dollars_per_war"]["flat"],
            "scale_vs_shipped": cfg["dollars_per_war"]["flat"] / b["flat"],
            "inflation": cfg["dollars_per_war_inflation"],
            "reanchor": cfg["dollars_per_war"].get("_fa_reanchor"),
            "anchors": dict(fit["empirical_anchors"]["anchors"])}


# --------------------------------------------------------------------------
# realized side
# --------------------------------------------------------------------------
def realized_mm(rec: dict, dpw_by_year: dict, discount: float) -> float:
    """Realized surplus PV at the listing year. Salary imputation and the
    service/control cutoff are byte-identical to surplus_backtest_real +
    backtest.realized_sv_pv (tiered=False branch)."""
    if rec["debut"] is None or not rec["war_by_year"]:
        return 0.0
    cfg = vf._config()
    fracs = list(cfg["service_time"]["arb_model"]["fractions_of_fa_value"])
    pre_arb = int(cfg["service_time"]["pre_arb_years"])
    lm_by_year = {int(k): float(v) for k, v in (cfg.get("league_min_by_year") or {}).items()}
    lm_default = float(cfg["service_time"]["league_min_usd"]) / 1e6
    total, service = 0.0, 0
    for y in sorted(rec["war_by_year"]):
        if y > LAST_FULL_SEASON or service >= CONTROL_YEARS:
            break
        war = round(float(rec["war_by_year"][y]), 2)
        if service < pre_arb:
            sal = lm_by_year.get(y, lm_default)
        else:
            i = service - pre_arb
            frac = fracs[i] if i < len(fracs) else fracs[-1]
            sal = frac * vf.tiered_war_value_usd(war) / 1e6
        sal = round(sal, 3)
        row = dpw_by_year.get(y)
        if row is None:
            yrs = sorted(dpw_by_year)
            row = dpw_by_year[min(yrs, key=lambda t: abs(t - y))]
        total += (war * float(row) - sal) / ((1.0 + discount) ** (y - rec["year"]))
        service += 1
    return total


def _seed(player_id: str, base: int = 20260530) -> int:
    import zlib
    return (base + zlib.crc32(player_id.encode("utf-8"))) % (2 ** 32)


def prep(pool: dict, *, scale: str, gate: str, target: str, draws: int,
         resolved_only: bool = True) -> dict:
    cfg = vf._config()
    disc = float(cfg["discount_rate"])
    if target == "today":
        flat = vf.dollars_per_war_flat()
        dpw = {y: flat for y in range(2010, 2036)}
    else:
        dpw = {int(k): float(v["overall"]) for k, v in
               cfg["historical_dollars_per_war"].items()}
    recs = [r for r in pool["records"] if r[f"fv_{gate}"] >= MIN_FV]
    if resolved_only:
        recs = [r for r in recs if r["resolved"]]
    fv = np.array([r[f"fv_{scale}"] for r in recs], dtype=float)
    pred = np.empty(len(recs)); real = np.empty(len(recs))
    D = np.empty((len(recs), draws), dtype=np.float32)
    for i, r in enumerate(recs):
        f = r[f"fv_{scale}"]
        pred[i] = (vf.expected_surplus_usd(f, r["is_pitcher"], r["position"],
                                           age=r["age"], eta_years=r["eta_years"]) or 0.0) / 1e6
        d = vf.sv_draws(f, r["is_pitcher"], r["position"], draws=draws,
                        seed=_seed(r["key"]), age=r["age"], eta_years=r["eta_years"])
        D[i] = np.asarray(d, dtype=np.float32) if d is not None else pred[i]
        real[i] = realized_mm(r, dpw, disc)
    return {"key": np.array([r["key"] for r in recs]),
            "year": np.array([r["year"] for r in recs]),
            "fv": fv, "pred": pred, "real": real, "draws": D,
            "is_pit": np.array([r["is_pitcher"] for r in recs], dtype=bool)}


# --------------------------------------------------------------------------
# fit + apply
# --------------------------------------------------------------------------
def fit_floored_linear(pred: np.ndarray, real: np.ndarray) -> tuple[float, float]:
    a, b = np.polyfit(pred, real, 1)
    return float(a), float(b)


def apply_map(coef: tuple[float, float], x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, coef[0] * np.asarray(x, dtype=float) + coef[1])


def metrics(corr: np.ndarray, real: np.ndarray) -> dict:
    from scipy import stats
    lr = stats.linregress(corr, real)
    err = real - corr
    return {"n": int(len(corr)), "slope": float(lr.slope), "intercept": float(lr.intercept),
            "r2": float(lr.rvalue ** 2), "bias": float(err.mean()),
            "mae": float(np.abs(err).mean()),
            "rmse": float(np.sqrt((err ** 2).mean())),
            "spearman": float(stats.spearmanr(corr, real).correlation)}


def coverage(coef, tr_pred, tr_real, te_pred, te_real, te_draws) -> tuple[np.ndarray, float]:
    """Affine-recalibrated predictive PITs (backtest.leave_one_year_out_cv's
    convention): recentre on the corrected mean AND rescale the spread by the
    TRAIN-fold residual/draw-spread ratio."""
    tc = apply_map(coef, tr_pred)
    resid_std = float(np.std(tr_real - tc))
    draw_std = float(np.mean(np.std(te_draws, axis=1))) or 1.0
    disp = resid_std / draw_std
    pits = np.empty(len(te_pred))
    for i in range(len(te_pred)):
        c = max(0.0, coef[0] * te_pred[i] + coef[1])
        recal = c + disp * (te_draws[i].astype(float) - te_pred[i])
        pits[i] = float((recal <= te_real[i]).mean())
    return pits, disp


def cov_rate(pits: np.ndarray) -> float:
    return float(((pits >= 0.10) & (pits <= 0.90)).mean())
