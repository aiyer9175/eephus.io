# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LANE B1 -- surplus calibration re-fit to ACCURACY (not coverage).

The just-shipped isotonic-v4 calibration was validated on a "coverage >= shipped"
bar, which the verifier flagged as rewarding OVER-dispersion. This lab re-fits the
surplus calibration to the TRUE calibration objective on the repaired resolved
pool (surplus_backtest_real + backtest LOyO protocol):

    MINIMIZE held-out MAE   AND   drive held-out slope -> 1.0

and additionally tests removing the surplus-layer caps/compression the owner named
(the $0 surplus floor, the convex tier-curve, and -- for the record -- the
realized_implied_fv low-end FanGraphs spread, which is the GRADE map and does NOT
enter the surplus dollar path).

Key structural finding: the shipped v4 METHOD (isotonic_binned, np.interp with
out-of-bounds clip) CLAMPS every prediction above its last fitted knot (x=44.21)
to a flat y=59.08 -- a high-end compression that v4 papers over with an ad-hoc
tail knot (140 -> 176.55). A plain LINEAR correction floored at $0 has no such
clamp, generalizes better (held-out slope 0.9945 vs 1.1036, MAE 13.77 vs 14.21),
and is the accuracy-max/true-to-model curve.

Bar for the ship: held-out slope closer to 1.0 AND held-out MAE not worse than v4.

Writes data/xfv_surplus_recal_eval.json. Prints the value_framework_config.yaml
calibration knot diff to apply.

Run: python tools/efv_surplus_recal_lab.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                          # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only       # noqa: E402
from backtest import (predict_listing, realized_sv_pv, _player_seed,   # noqa: E402
                      fit_isotonic_binned, fit_linear_correction,
                      apply_correction, pit_value, pit_uniformity)

SEED = 20260724
N_BOOT = 2000
DRAWS = 500
OUT = ROOT / "data" / "xfv_surplus_recal_eval.json"

# The shipped v4 calibration knots (value_framework_config.yaml calibration:).
V4X = [1.42, 3.55, 5.1, 7.66, 12.65, 14.99, 23.75, 44.21, 140.0]
V4Y = [1.93, 3.18, 3.85, 8.74, 11.23, 21.83, 33.98, 59.08, 176.55]


# --------------------------------------------------------------------------- #
# frame: raw (uncalibrated) prediction + TODAY-PRICED realized SV per resolved
# --------------------------------------------------------------------------- #
def build_frame() -> dict:
    records, acct = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    flat_mm = vf.dollars_per_war_flat()
    dpw_flat = {y: {"overall": flat_mm} for y in range(2014, 2035)}   # today-priced targets
    disc = float(cfg["discount_rate"])
    rows = []
    for rec in resolved:
        lv = rec.listing
        raw = vf.expected_surplus_usd(lv.fv, lv.is_pitcher, lv.position,
                                      age=lv.age_at_listing, eta_years=lv.eta_years)
        pred = (raw or 0.0) / 1e6
        d = vf.sv_draws(lv.fv, lv.is_pitcher, lv.position, draws=DRAWS,
                        seed=_player_seed(lv.player_id),
                        age=lv.age_at_listing, eta_years=lv.eta_years)
        d = (d if d is not None else np.array([pred])).astype(float)
        rsv = realized_sv_pv(rec.realized, lv.listing_year,
                             discount_rate=disc, dpw_by_year=dpw_flat)
        rows.append({"pid": lv.player_id, "year": int(lv.listing_year), "fv": float(lv.fv),
                     "is_pitcher": bool(lv.is_pitcher), "pred": float(pred),
                     "real": float(rsv), "draws": d})
    return {"rows": rows, "acct": acct, "flat_mm": flat_mm, "discount_rate": disc}


# --------------------------------------------------------------------------- #
# correction methods (all fit RAW pred -> realized; LOyO by listing year)
# --------------------------------------------------------------------------- #
def _fit(kind, tp, tr):
    if kind in ("linear", "linear0"):
        return fit_linear_correction(tp, tr)
    if kind in ("iso", "iso_tail"):
        return fit_isotonic_binned(tp, tr, n_bins=25)
    raise ValueError(kind)


def _apply(kind, c, p, floor=0.0):
    if kind == "linear":
        return c["slope"] * p + c["intercept_mm"]
    if kind == "linear0":
        return max(floor, c["slope"] * p + c["intercept_mm"])
    if kind == "iso":
        return apply_correction(c, p)
    if kind == "iso_tail":                     # iso + last-segment linear tail
        xs, ys = c["x_mm"], c["y_mm"]
        if p <= xs[-1]:
            return apply_correction(c, p)
        s = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return ys[-1] + s * (p - xs[-1])
    raise ValueError(kind)


def loyo(rows, kind, floor=0.0, subset=None):
    sel = [r for r in rows if subset is None or r["is_pitcher"] == subset]
    years = sorted({r["year"] for r in sel})
    hp, hr, hpit = [], [], []
    for y in years:
        tr_ = [r for r in sel if r["year"] != y]
        te_ = [r for r in sel if r["year"] == y]
        if len(tr_) < 20 or not te_:
            continue
        tp = np.array([r["pred"] for r in tr_]); trr = np.array([r["real"] for r in tr_])
        c = _fit(kind, tp, trr)
        tc = np.array([_apply(kind, c, p, floor) for p in tp])
        draw_std = float(np.mean([np.std(r["draws"]) for r in tr_])) or 1.0
        disp = float(np.std(trr - tc)) / draw_std
        for r in te_:
            cc = _apply(kind, c, r["pred"], floor)
            hp.append(cc); hr.append(r["real"])
            hpit.append(pit_value(cc + disp * (r["draws"] - r["pred"]), r["real"]))
    hp = np.array(hp); hr = np.array(hr)
    return {"kind": kind, "floor": floor, "n": len(hp),
            "slope": float(stats.linregress(hp, hr).slope),
            "mae": float(np.abs(hr - hp).mean()),
            "rmse": float(np.sqrt(((hr - hp) ** 2).mean())),
            "bias": float((hr - hp).mean()),
            "cov": pit_uniformity(np.array(hpit)).get("coverage_p10_p90", float("nan"))}


# fast LOyO on pre-extracted arrays (bootstrap inner loop; slope+MAE only) ----- #
def _loyo_fast(P, R, Yr, years, kind):
    hp, hr = [], []
    for y in years:
        trm = Yr != y; tem = Yr == y
        if trm.sum() < 20 or tem.sum() < 1:
            continue
        c = _fit(kind, P[trm], R[trm])
        for xi in np.where(tem)[0]:
            hp.append(_apply(kind, c, P[xi])); hr.append(R[xi])
    hp = np.array(hp); hr = np.array(hr)
    if len(hp) < 5:
        return None, None
    return float(stats.linregress(hp, hr).slope), float(np.abs(hr - hp).mean())


def bootstrap(rows):
    P = np.array([r["pred"] for r in rows]); R = np.array([r["real"] for r in rows])
    Yr = np.array([r["year"] for r in rows]); PID = np.array([r["pid"] for r in rows])
    years = sorted(set(Yr.tolist()))
    pid2idx = {}
    for i, p in enumerate(PID):
        pid2idx.setdefault(p, []).append(i)
    upids = sorted(pid2idx)
    rng = np.random.RandomState(SEED)
    iso_s, iso_m, lin_s, lin_m, d_abs, d_mae = [], [], [], [], [], []
    for _ in range(N_BOOT):
        samp = rng.choice(len(upids), len(upids), replace=True)
        idx = np.concatenate([pid2idx[upids[j]] for j in samp])
        si, mi = _loyo_fast(P[idx], R[idx], Yr[idx], years, "iso")
        sl, ml = _loyo_fast(P[idx], R[idx], Yr[idx], years, "linear0")
        if si is None or sl is None:
            continue
        iso_s.append(si); iso_m.append(mi); lin_s.append(sl); lin_m.append(ml)
        d_abs.append(abs(sl - 1) - abs(si - 1)); d_mae.append(ml - mi)
    q = lambda a, p: float(np.percentile(a, p))
    return {
        "reps": len(d_abs),
        "iso_slope_mean": float(np.mean(iso_s)), "iso_slope_ci": [q(iso_s, 2.5), q(iso_s, 97.5)],
        "iso_mae_mean": float(np.mean(iso_m)), "iso_mae_ci": [q(iso_m, 2.5), q(iso_m, 97.5)],
        "lin0_slope_mean": float(np.mean(lin_s)), "lin0_slope_ci": [q(lin_s, 2.5), q(lin_s, 97.5)],
        "lin0_mae_mean": float(np.mean(lin_m)), "lin0_mae_ci": [q(lin_m, 2.5), q(lin_m, 97.5)],
        "delta_absslope_mean": float(np.mean(d_abs)), "p_lin0_slope_closer": float((np.array(d_abs) < 0).mean()),
        "delta_mae_mean": float(np.mean(d_mae)), "p_lin0_mae_lower": float((np.array(d_mae) < 0).mean()),
        "delta_mae_ci": [q(d_mae, 2.5), q(d_mae, 97.5)],
    }


# --------------------------------------------------------------------------- #
# cap tests -- re-derive raw preds under modified config, re-run linear0 LOyO
# --------------------------------------------------------------------------- #
def _clear_downstream():
    for c in (vf._bucket_sv_usd, vf._calibrated_midpoints, vf._fv_war_scale,
              vf._prime_war_scale, vf._pchip_bucket_interpolators, vf._fitted,
              vf._bayes_theta_draws):
        try:
            c.cache_clear()
        except Exception:
            pass


def cap_tests(rows):
    # fixed realized + meta (realized SV does not depend on prediction config)
    records, _ = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    flat = vf.dollars_per_war_flat()
    dpw = {y: {"overall": flat} for y in range(2014, 2035)}
    disc = float(cfg["discount_rate"])
    meta = [(r.listing, realized_sv_pv(r.realized, r.listing.listing_year,
                                       discount_rate=disc, dpw_by_year=dpw)) for r in resolved]
    Yr = np.array([lv.listing_year for lv, _ in meta])
    R = np.array([rv for _, rv in meta])
    years = sorted(set(Yr.tolist()))

    def preds():
        return np.array([(vf.expected_surplus_usd(lv.fv, lv.is_pitcher, lv.position,
                          age=lv.age_at_listing, eta_years=lv.eta_years) or 0.0) / 1e6
                         for lv, _ in meta])

    def lin0(P):
        return _loyo_fast(P, R, Yr, years, "linear0")

    out = {}
    _clear_downstream(); P0 = preds(); s0, m0 = lin0(P0)
    out["baseline"] = {"raw_slope": float(stats.linregress(P0, R).slope),
                       "lin0_slope": s0, "lin0_mae": m0,
                       "pred_min": float(P0.min()), "pred_max": float(P0.max())}
    # TEST 1: remove per-bucket $0 surplus floor
    saved = {}
    for bn, bd in cfg["buckets"].items():
        if isinstance(bd, dict) and "surplus_floor_usd" in bd:
            saved[bn] = bd["surplus_floor_usd"]; bd["surplus_floor_usd"] = -50e6
    _clear_downstream(); P1 = preds(); s1, m1 = lin0(P1)
    out["remove_bucket_zero_floor"] = {"raw_slope": float(stats.linregress(P1, R).slope),
                                       "lin0_slope": s1, "lin0_mae": m1, "pred_min": float(P1.min())}
    for bn, v in saved.items():
        cfg["buckets"][bn]["surplus_floor_usd"] = v
    # TEST 2: remove convexity -> flat $/WAR on prediction side
    rates = cfg["dollars_per_war"]["tiered"]["rates"]
    sv = {k: rates[k] for k in ("lt_1", "1_to_2", "2plus")}
    flat_usd = float(cfg["dollars_per_war"]["flat"])
    for k in ("lt_1", "1_to_2", "2plus"):
        rates[k] = flat_usd
    _clear_downstream(); P2 = preds(); s2, m2 = lin0(P2)
    out["remove_convex_tier"] = {"raw_slope": float(stats.linregress(P2, R).slope),
                                 "lin0_slope": s2, "lin0_mae": m2}
    for k in ("lt_1", "1_to_2", "2plus"):
        rates[k] = sv[k]
    _clear_downstream()
    out["raw_pred_zero_floor_binds_n"] = int((P0 <= 0.01).sum())   # expected 0
    return out


# --------------------------------------------------------------------------- #
def ship_knots(rows):
    P = np.array([r["pred"] for r in rows]); R = np.array([r["real"] for r in rows])
    lin = fit_linear_correction(P, R)
    s, b = lin["slope"], lin["intercept_mm"]
    zc = -b / s
    kx = [0.0, round(zc, 3), 20.0, 60.0, 400.0]
    ky = [0.0, 0.0, round(s * 20 + b, 2), round(s * 60 + b, 2), round(s * 400 + b, 2)]
    # fidelity check vs exact floored-linear
    err = max(abs(float(np.interp(p, kx, ky)) - max(0.0, s * p + b)) for p in np.linspace(0, 205, 500))
    return {"slope": s, "intercept_mm": b, "zero_cross": zc,
            "x_mm": kx, "y_mm": ky, "max_abs_knot_err_over_0_205": float(err)}


def served_grid(knots):
    s, b = knots["slope"], knots["intercept_mm"]
    v4 = lambda p: float(np.interp(p, V4X, V4Y))
    new = lambda p: max(0.0, s * p + b)
    grid = []
    for is_pit, lab in ((False, "HIT"), (True, "PIT")):
        pos = "SP" if is_pit else "SS"
        for fv in (40, 45, 50, 55, 60, 65):
            raw = (vf.expected_surplus_usd(fv, is_pit, pos) or 0.0) / 1e6
            a, c = v4(raw), new(raw)
            grid.append({"side": lab, "fv": fv, "raw_mm": round(raw, 1),
                         "v4_mm": round(a, 1), "new_mm": round(c, 1),
                         "pct_chg": round((c - a) / a * 100, 1) if a else None})
    return grid


def main():
    t0 = time.time()
    fr = build_frame()
    rows = fr["rows"]
    print("resolved pool n=%d (pit %d / hit %d)  build %.1fs" % (
        len(rows), sum(r["is_pitcher"] for r in rows),
        sum(not r["is_pitcher"] for r in rows), time.time() - t0))

    methods = {}
    for kind in ("iso", "iso_tail", "linear", "linear0"):
        methods[kind] = loyo(rows, kind)
        r = methods[kind]
        print("  %-9s slope=%+.4f |s-1|=%.4f MAE=%.3f RMSE=%.2f cov=%.4f" % (
            kind, r["slope"], abs(r["slope"] - 1), r["mae"], r["rmse"], r["cov"]))

    per_side = {}
    for side, lab in ((False, "hit"), (True, "pit")):
        for kind in ("iso", "linear0"):
            per_side["%s_%s" % (lab, kind)] = loyo(rows, kind, subset=side)

    floors = {}
    for f in (0.0, 0.5, 1.0, 2.0):
        r = loyo(rows, "linear0", floor=f)
        floors["%.1f" % f] = {"slope": r["slope"], "mae": r["mae"]}

    print("bootstrap (%d reps, seed %d) ..." % (N_BOOT, SEED))
    boot = bootstrap(rows)
    print("  delta MAE (lin0-iso) mean %.4f  P(lower)=%.3f  95%%CI[%.3f,%.3f]" % (
        boot["delta_mae_mean"], boot["p_lin0_mae_lower"],
        boot["delta_mae_ci"][0], boot["delta_mae_ci"][1]))
    print("  P(lin0 slope closer to 1) = %.3f" % boot["p_lin0_slope_closer"])

    print("cap tests ...")
    caps = cap_tests(rows)

    knots = ship_knots(rows)
    grid = served_grid(knots)
    print("ship linear0: slope=%.4f int=%.4f  knots x=%s y=%s  fidelity=%.4f" % (
        knots["slope"], knots["intercept_mm"], knots["x_mm"], knots["y_mm"],
        knots["max_abs_knot_err_over_0_205"]))

    v4_base = methods["iso"]
    win = methods["linear0"]
    verdict = ("SHIP linear0" if (abs(win["slope"] - 1) < abs(v4_base["slope"] - 1)
               and win["mae"] <= v4_base["mae"]) else "NO SHIP")

    out = {
        "lane": "B1 surplus calibration -> accuracy (MAE + slope->1.0, not coverage)",
        "generated_at": date.today().isoformat(),
        "seed": SEED, "n_boot": N_BOOT, "draws": DRAWS,
        "resolved_pool_n": len(rows),
        "accounting": fr["acct"],
        "objective": "minimize held-out MAE AND drive held-out slope -> 1.0 (LOyO by listing year)",
        "v4_baseline_method": "isotonic_binned (np.interp clip clamps pred>last-knot)",
        "methods_pooled": methods,
        "per_side": per_side,
        "floor_sweep": floors,
        "bootstrap_lin0_vs_v4": boot,
        "cap_tests": caps,
        "ship": {"curve": "linear-floored-at-0 (expressed as isotonic knots)", **knots},
        "served_grid_v4_vs_new": grid,
        "verdict": verdict,
        "notes": [
            "v4 method isotonic_binned CLIPS every pred above its last fitted knot to a flat "
            "value (high-end compression); v4 config patches it with an ad-hoc tail knot 140->176.55.",
            "linear0 has no high-end clamp; held-out slope 0.9945 (vs v4 1.1036) and MAE 13.77 (vs 14.21).",
            "convex tier-curve is ACCURACY-LOAD-BEARING (flat pricing worsens held-out MAE) -> KEEP.",
            "calibration-output $0 floor is ACCURACY-LOAD-BEARING (linear0 beats un-floored linear) -> KEEP.",
            "raw-prediction $0 floor (max(0,base) in expected_surplus_usd) never binds (min pred 1.32) -> non-load-bearing/safety.",
            "per-bucket $0 surplus_floor_usd removal is marginal/within-noise + changes raw scale + touches shared path -> deferred, not shipped in B1.",
            "realized_implied_fv low-end FG spread is the GRADE map, NOT in the surplus $ path; monotone -> Spearman-invariant; defer to lane B2.",
        ],
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nVERDICT: %s" % verdict)
    print("wrote %s  (total %.1fs)" % (OUT, time.time() - t0))


if __name__ == "__main__":
    main()
