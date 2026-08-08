# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LANE C4 -- re-decompose the surplus error chain on the v6 EV frame and
re-derive the gate currency ("+0.01 pooled rho = -$X M surplus MAE").

Pre-registration: docs/efv-2026-08-07b/SURPLUS_DECOMPOSITION_V6.md (written
BEFORE this file; only its RESULT section is filled afterwards).
Artifact: data/surplus_decomposition_v6.json.

Read-only on value_framework.py and surplus_backtest_real.py. The v5 dollar
calibration is re-expressed as isotonic knots and applied as a PURE FUNCTION
(`_apply_cal`) to raw prices; the pre-registration allowed patching the cached
config dict in memory, but nothing is patched at all, which is strictly safer
under parallel agents. No config file is written and prospects.db is only READ.

Run: python tools/surplus_decomposition_lab.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backtest as bt                      # noqa: E402
import surplus_backtest_real as sbr        # noqa: E402
import value_framework as vf               # noqa: E402

OUT = ROOT / "data" / "surplus_decomposition_v6.json"
CACHE_DIR = Path(os.environ.get(
    "C4_CACHE_DIR",
    r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR"
    r"\51d4716c-ebca-464e-b136-f45585e28ab6\scratchpad"))

SEED = 20260808          # fixed literal; never derived from a string hash
B_LADDER = 2000
B_CURRENCY = 2000
FV_LO, FV_HI = 20.0, 80.0

# v5 = linearmap-v5-todaypriced-2026-07-24: corrected = max(0, 1.382491*raw - 2.318551)
V5_SLOPE, V5_INTERCEPT = 1.382491, 2.318551
V5_ZERO_CROSS = V5_INTERCEPT / V5_SLOPE                      # 1.6771... $M raw
V5_KNOTS = {
    "method": "isotonic",
    "enabled": True,
    "version": "linearmap-v5-reconstructed-by-lane-C4",
    "isotonic": {"x_mm": [0.0, V5_ZERO_CROSS, 400.0],
                 "y_mm": [0.0, 0.0, V5_SLOPE * 400.0 - V5_INTERCEPT]},
    "linear": {"slope": 1.0, "intercept_mm": 0.0},
}

PUBLISHED_CURRENCY = -0.0704
PUBLISHED_CI95 = (-0.0878, -0.0550)
C3_GONE_THRESHOLD = 0.05        # self-added; decides C3; declared in the headline


# ---------------------------------------------------------------------------
# pool construction (DB read only)
# ---------------------------------------------------------------------------
def _cohort_rows(fv_scale: str) -> list[dict]:
    """Resolved-only listings under `fv_scale`, with everything the ladder needs.
    Cached to the scratchpad so re-runs never touch the DB twice."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"c4_cohort_{fv_scale}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    prev = sbr.FV_SCALE
    sbr.FV_SCALE = fv_scale                    # GATE_SCALE stays 'raw': pool fixed
    try:
        records, acct = sbr.build_cohorts()
    finally:
        sbr.FV_SCALE = prev
    cfg = vf._config()
    dpw_by_year = {int(k): dict(v) for k, v in
                   (cfg.get("historical_dollars_per_war") or {}).items()}
    disc = float(cfg["discount_rate"])
    rows = []
    for rec in sbr._resolved_only(records):
        li = rec.listing
        rows.append({
            "player_key": li.player_id,
            "year": int(li.listing_year),
            "fv": float(li.fv),
            "is_pitcher": bool(li.is_pitcher),
            "position": li.position,
            "age": li.age_at_listing,
            "eta_years": li.eta_years,
            "truth_mm": float(bt.realized_sv_pv(
                rec.realized, li.listing_year,
                discount_rate=disc, dpw_by_year=dpw_by_year)),
            "realized_control_war": float(bt._realized_control_war(rec.realized)),
            "debuted": rec.realized.debut_year is not None,
        })
    rows.sort(key=lambda r: (r["player_key"], r["year"]))
    payload = {"accounting": acct, "rows": rows}
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# pricing
# ---------------------------------------------------------------------------
def _raw_price_mm(fv, is_pit, pos, age, eta) -> float:
    usd = vf.expected_surplus_usd(fv, is_pit, pos, age=age, eta_years=eta)
    return (usd or 0.0) / 1e6


def _fv_star(target_war: float, is_pit: bool, control_years: int,
             grid: dict) -> tuple[float, str]:
    """Continuous FV whose model-predicted control WAR equals `target_war`.
    `grid` is {side: (fvs, wars)} precomputed and monotone increasing."""
    fvs, wars = grid[bool(is_pit)]
    lo, hi = wars[0], wars[-1]
    if target_war <= lo:
        return FV_LO, "clamp_lo"
    if target_war >= hi:
        return FV_HI, "clamp_hi"
    i = int(np.searchsorted(wars, target_war))
    w0, w1 = wars[i - 1], wars[i]
    f0, f1 = fvs[i - 1], fvs[i]
    t = 0.0 if w1 == w0 else (target_war - w0) / (w1 - w0)
    return float(f0 + t * (f1 - f0)), "interp"


def _apply_cal(raw: np.ndarray, block: dict | None) -> np.ndarray:
    """Vectorised apply_calibration for a calibration config block (None = live)."""
    cal = block if block is not None else (vf._config().get("calibration", {}) or {})
    if not cal.get("enabled"):
        return raw.copy()
    if str(cal.get("method", "linear")).lower() == "isotonic":
        xs = np.asarray([float(v) for v in cal["isotonic"]["x_mm"]], float)
        ys = np.asarray([float(v) for v in cal["isotonic"]["y_mm"]], float)
        return np.interp(raw, xs, ys, left=ys[0], right=ys[-1])
    lin = cal.get("linear", {})
    return float(lin.get("slope", 1.0)) * raw + float(lin.get("intercept_mm", 0.0))


# ---------------------------------------------------------------------------
# ladder
# ---------------------------------------------------------------------------
def _rank_u(x: np.ndarray) -> np.ndarray:
    """Average-rank quantiles in (0,1]; ties share a rank (the served FV grid is
    coarse and the ties are the point)."""
    from scipy.stats import rankdata
    return rankdata(x, method="average") / len(x)


def _reassign(multiset: np.ndarray, score: np.ndarray) -> np.ndarray:
    """Assign the ascending-sorted `multiset` to rows in ascending `score` order.
    Deterministic tie handling: stable sort on (score, original index)."""
    order = np.lexsort((np.arange(len(score)), score))
    out = np.empty_like(multiset)
    out[order] = np.sort(multiset)
    return out


def _err(pred: np.ndarray, truth: np.ndarray) -> dict:
    d = pred - truth
    out = {"n": int(len(pred)), "mae": float(np.abs(d).mean()),
           "mse": float((d ** 2).mean()), "rmse": float(np.sqrt((d ** 2).mean())),
           "bias": float(d.mean()), "pred_mean": float(pred.mean())}
    if len(pred) > 2 and pred.std() > 0:
        from scipy import stats
        lr = stats.linregress(pred, truth)
        out["cal_slope"] = float(lr.slope)
        out["cal_intercept"] = float(lr.intercept)
        out["cal_r2"] = float(lr.rvalue ** 2)
        out["spearman_vs_truth"] = float(stats.spearmanr(pred, truth).statistic)
    return out


def _binned_calibration(pred: np.ndarray, truth: np.ndarray, n_bins: int = 8) -> dict:
    order = np.argsort(pred, kind="stable")
    ps, ts = pred[order], truth[order]
    bins = np.array_split(np.arange(len(pred)), n_bins)
    mp = np.array([ps[b].mean() for b in bins if len(b)])
    mt = np.array([ts[b].mean() for b in bins if len(b)])
    from scipy import stats
    lr = stats.linregress(mp, mt)
    return {"slope": float(lr.slope), "intercept": float(lr.intercept),
            "r2": float(lr.rvalue ** 2),
            "bin_pred_mean": [round(float(v), 3) for v in mp],
            "bin_real_mean": [round(float(v), 3) for v in mt],
            "bin_abs_err": [round(float(abs(a - b)), 3) for a, b in zip(mp, mt)]}


def _ladder(p: np.ndarray, p0: np.ndarray, t: np.ndarray) -> dict:
    """p = served prices, p0 = perfect-foresight prices, t = realized surplus."""
    u_t = _rank_u(t)
    u_p = _rank_u(p)
    L2 = p
    L1 = _reassign(p, u_t)                      # perfect rank, served multiset
    L0 = p0                                     # perfect level AND rank
    L1B = _reassign(p0, u_p)                    # perfect level, incumbent rank
    return {"L2": L2, "L1": L1, "L0": L0, "L1B": L1B}


def _shares(mae2: float, mae1: float, mae0: float) -> dict:
    return {"rank": (mae2 - mae1) / mae2, "level": (mae1 - mae0) / mae2,
            "floor": mae0 / mae2}


def _partition(arms: dict, t: np.ndarray, loss: str) -> dict:
    def L(pred):
        d = pred - t
        return float(np.abs(d).mean()) if loss == "mae" else float((d ** 2).mean())
    m2, m1, m0, m1b = L(arms["L2"]), L(arms["L1"]), L(arms["L0"]), L(arms["L1B"])
    A = _shares(m2, m1, m0)
    B = {"level": (m2 - m1b) / m2, "rank": (m1b - m0) / m2, "floor": m0 / m2}
    shap = {k: 0.5 * (A[k] + B[k]) for k in ("rank", "level", "floor")}
    return {"loss": loss, "L2": m2, "L1": m1, "L0": m0, "L1B": m1b,
            "order_A": A, "order_B": B, "shapley": shap,
            "sum_A": sum(A.values()), "sum_B": sum(B.values()),
            "sum_shapley": sum(shap.values()),
            "interaction_rank": abs(A["rank"] - B["rank"])}


# ---------------------------------------------------------------------------
# currency
# ---------------------------------------------------------------------------
W_GRID = (0.0, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0)
SEGMENTS = (0.05, 0.10, 0.20, 0.50, 1.0)


def _currency_curve(p: np.ndarray, t: np.ndarray, war: np.ndarray,
                    rank_on: np.ndarray | None = None) -> dict:
    """`rank_on` is the variable whose order defines the incumbent board. Default
    (pre-registered) is the served PRICE, which is nearly tie-free. Passing the
    served FV instead reproduces the published stage-H instrument, whose FV grid
    ties in large blocks."""
    from scipy import stats
    u_inc = _rank_u(p if rank_on is None else rank_on)
    u_truth = _rank_u(t)
    curve = {}
    for w in W_GRID:
        board = _reassign(p, (1.0 - w) * u_inc + w * u_truth)
        curve[w] = {
            "rho_vs_realized_war": float(stats.spearmanr(board, war).statistic),
            "rho_vs_realized_surplus": float(stats.spearmanr(board, t).statistic),
            "mae_mm": float(np.abs(board - t).mean()),
            "mse_mm2": float(((board - t) ** 2).mean()),
        }
    base = curve[0.0]
    segs = {}
    for w in SEGMENTS:
        drho = curve[w]["rho_vs_realized_war"] - base["rho_vs_realized_war"]
        dmae = curve[w]["mae_mm"] - base["mae_mm"]
        segs[w] = {"d_rho": drho, "d_mae_mm": dmae,
                   "mm_per_0.01_rho": (dmae / (drho / 0.01)) if drho else float("nan")}
    return {"curve": {str(k): v for k, v in curve.items()},
            "segments": {str(k): v for k, v in segs.items()},
            "currency_mm_per_0.01_rho": segs[0.10]["mm_per_0.01_rho"]}


def _currency_point(p: np.ndarray, t: np.ndarray, war: np.ndarray,
                    w: float = 0.10, rank_on: np.ndarray | None = None) -> float:
    from scipy import stats
    u_inc = _rank_u(p if rank_on is None else rank_on)
    u_truth = _rank_u(t)
    b0 = _reassign(p, u_inc)
    bw = _reassign(p, (1.0 - w) * u_inc + w * u_truth)
    r0 = stats.spearmanr(b0, war).statistic
    rw = stats.spearmanr(bw, war).statistic
    m0 = np.abs(b0 - t).mean()
    mw = np.abs(bw - t).mean()
    drho = rw - r0
    return float((mw - m0) / (drho / 0.01)) if drho else float("nan")


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------
def _cluster_index(keys: list[str]) -> tuple[list[str], dict]:
    uniq = sorted(set(keys))
    idx = {k: [] for k in uniq}
    for i, k in enumerate(keys):
        idx[k].append(i)
    return uniq, {k: np.asarray(v, int) for k, v in idx.items()}


def _boot_draws(uniq, idx, rng, reps):
    n = len(uniq)
    for _ in range(reps):
        pick = rng.integers(0, n, size=n)
        yield np.concatenate([idx[uniq[j]] for j in pick])


def _ci(vals) -> dict:
    a = np.asarray([v for v in vals if np.isfinite(v)], float)
    if not len(a):
        return {"mean": float("nan"), "ci95": [float("nan")] * 2, "reps": 0}
    return {"mean": float(a.mean()),
            "ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))],
            "reps": int(len(a))}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    t_start = time.time()
    report: dict = {"pre_registration": "docs/efv-2026-08-07b/SURPLUS_DECOMPOSITION_V6.md",
                    "seed": SEED, "b_ladder": B_LADDER, "b_currency": B_CURRENCY,
                    "valuation_set": vf.active_valuation_set(),
                    "live_calibration_version": vf.calibration_version()}

    # ---- C0: v5 reconstruction check ------------------------------------
    probe = np.concatenate([np.linspace(0, 40, 4001), np.linspace(40, 400, 3601)])
    recon = _apply_cal(probe, V5_KNOTS)
    exact = np.maximum(0.0, V5_SLOPE * probe - V5_INTERCEPT)
    c0_max = float(np.abs(recon - exact).max())
    report["C0_v5_reconstruction"] = {
        "max_abs_dev_mm": c0_max, "threshold_mm": 0.01, "pass": bool(c0_max < 0.01),
        "zero_cross_raw_mm": V5_ZERO_CROSS}

    # ---- pool + pricing --------------------------------------------------
    cfg = vf._config()
    control_years = int(cfg["service_time"]["control_years"])
    grid_fv = np.arange(FV_LO, FV_HI + 0.001, 0.05)
    war_grid = {}
    mono = {}
    for is_pit in (False, True):
        w = np.asarray([(vf.expected_six_year_avg_war(float(f), is_pit) or 0.0)
                        * control_years for f in grid_fv], float)
        # The engine's FV->WAR map is NOT exactly monotone on a 0.05 grid: it dips
        # by up to ~0.007 total WAR in the FV20-35 region (measured, recorded here,
        # not silently swallowed). Inversion needs a monotone map, so take the
        # running max; the distortion is far below one FV point of resolution.
        d = np.diff(w)
        mono[str(is_pit)] = {"n_decreasing_steps": int((d < -1e-12).sum()),
                             "worst_step_war": float(d.min()),
                             "fv_range_of_violations": [
                                 float(grid_fv[np.where(d < -1e-12)[0].min()]),
                                 float(grid_fv[np.where(d < -1e-12)[0].max() + 1])]
                             if (d < -1e-12).any() else None}
        war_grid[is_pit] = (grid_fv, np.maximum.accumulate(w))
    report["fv_to_war_monotonicity_repair"] = mono

    pools = {}
    for scale in ("raw", "normalized"):
        payload = _cohort_rows(scale)
        rows = payload["rows"]
        pools[scale] = {"acct": payload["accounting"], "rows": rows}
    keys_raw = [r["player_key"] + "|" + str(r["year"]) for r in pools["raw"]["rows"]]
    keys_nrm = [r["player_key"] + "|" + str(r["year"]) for r in pools["normalized"]["rows"]]
    report["pool_membership_identical"] = bool(keys_raw == keys_nrm)
    rows = pools["normalized"]["rows"]
    report["accounting"] = pools["normalized"]["acct"]
    report["n_resolved"] = len(rows)
    report["n_distinct_players"] = len({r["player_key"] for r in rows})

    truth = np.asarray([r["truth_mm"] for r in rows], float)
    war = np.asarray([r["realized_control_war"] for r in rows], float)
    keys = [r["player_key"] for r in rows]
    report["truth"] = {"mean": float(truth.mean()), "sd": float(truth.std(ddof=1)),
                       "mean_abs": float(np.abs(truth).mean()),
                       "frac_exact_zero": float((truth == 0).mean()),
                       "n_busts_never_debuted": int(sum(1 for r in rows if not r["debuted"]))}

    raw_price = {}
    for scale in ("raw", "normalized"):
        rr = pools[scale]["rows"]
        raw_price[scale] = np.asarray(
            [_raw_price_mm(r["fv"], r["is_pitcher"], r["position"], r["age"],
                           r["eta_years"]) for r in rr], float)
        report.setdefault("served_fv", {})[scale] = {
            "mean": float(np.mean([r["fv"] for r in rr])),
            "sd": float(np.std([r["fv"] for r in rr], ddof=1)),
            "min": float(min(r["fv"] for r in rr)),
            "max": float(max(r["fv"] for r in rr))}

    fv_star, clamps = [], {"clamp_lo": 0, "clamp_hi": 0, "interp": 0}
    for r in rows:
        f, how = _fv_star(r["realized_control_war"], r["is_pitcher"], control_years, war_grid)
        fv_star.append(f)
        clamps[how] += 1
    raw_price_L0 = np.asarray(
        [_raw_price_mm(f, r["is_pitcher"], r["position"], r["age"], r["eta_years"])
         for f, r in zip(fv_star, rows)], float)
    report["L0_inversion"] = {"clamps": clamps, "control_years_used": control_years,
                              "fv_star_mean": float(np.mean(fv_star)),
                              "fv_star_min": float(np.min(fv_star)),
                              "fv_star_max": float(np.max(fv_star))}

    live_cal = dict(vf._config().get("calibration", {}) or {})
    cal_blocks = {"v5": V5_KNOTS, "v6": live_cal}
    cells = {}
    for scale in ("raw", "normalized"):
        for cal_id, block in cal_blocks.items():
            name = f"{scale}_{cal_id}"
            cells[name] = {"p": _apply_cal(raw_price[scale], block),
                           "p0": _apply_cal(raw_price_L0, block)}

    # ---- ladder per cell -------------------------------------------------
    rng = np.random.default_rng(SEED)
    uniq, idx = _cluster_index(keys)
    draws = list(_boot_draws(uniq, idx, rng, B_LADDER))

    report["cells"] = {}
    for name, cell in cells.items():
        arms = _ladder(cell["p"], cell["p0"], truth)
        entry = {"rungs": {k: _err(v, truth) for k, v in arms.items()},
                 "binned_calibration_L2": _binned_calibration(arms["L2"], truth),
                 "partition_mae": _partition(arms, truth, "mae"),
                 "partition_mse": _partition(arms, truth, "mse")}
        # bust subgroup: where the $0 floor used to live
        bust = np.asarray([not r["debuted"] for r in rows])
        entry["busts"] = {
            "n": int(bust.sum()),
            "served_price_mean_mm": float(arms["L2"][bust].mean()),
            "L0_price_mean_mm": float(arms["L0"][bust].mean()),
            "truth_mean_mm": float(truth[bust].mean()),
            "L0_mae_mm": float(np.abs(arms["L0"][bust] - truth[bust]).mean()),
            "L0_share_of_total_L0_abs_err": float(
                np.abs(arms["L0"][bust] - truth[bust]).sum()
                / np.abs(arms["L0"] - truth).sum())}
        # where the L0 (perfect-foresight) residual actually lives
        deb = ~bust
        qs = np.quantile(war[deb], [0.25, 0.5, 0.75])
        buckets = {"never_debuted": bust,
                   "debuted_war_q1": deb & (war <= qs[0]),
                   "debuted_war_q2": deb & (war > qs[0]) & (war <= qs[1]),
                   "debuted_war_q3": deb & (war > qs[1]) & (war <= qs[2]),
                   "debuted_war_q4": deb & (war > qs[2])}
        tot_abs = float(np.abs(arms["L0"] - truth).sum())
        entry["L0_residual_by_bucket"] = {
            k: {"n": int(m.sum()),
                "mae_mm": float(np.abs(arms["L0"][m] - truth[m]).mean()),
                "bias_mm": float((arms["L0"][m] - truth[m]).mean()),
                "share_of_L0_abs_err": float(np.abs(arms["L0"][m] - truth[m]).sum() / tot_abs)}
            for k, m in buckets.items()}
        # bootstrap the shares
        acc = {f"{loss}_{order}_{term}": []
               for loss in ("mae", "mse") for order in ("A", "shapley")
               for term in ("rank", "level", "floor")}
        for sel in draws:
            ts = truth[sel]
            a = _ladder(cell["p"][sel], cell["p0"][sel], ts)
            for loss in ("mae", "mse"):
                part = _partition(a, ts, loss)
                for order_key, order_name in (("order_A", "A"), ("shapley", "shapley")):
                    for term in ("rank", "level", "floor"):
                        acc[f"{loss}_{order_name}_{term}"].append(part[order_key][term])
        entry["share_ci"] = {k: _ci(v) for k, v in acc.items()}
        report["cells"][name] = entry

    # ---- currency --------------------------------------------------------
    report["currency"] = {}
    for name in ("raw_v5", "normalized_v6", "raw_v6", "normalized_v5"):
        report["currency"][name] = _currency_curve(cells[name]["p"], truth, war)
    # POST-HOC DIAGNOSIS of clause C1 (run only after C1 failed; the C1 verdict is
    # NOT re-specified). The published instrument ranks the board by served FV,
    # which lives on a coarse grid and ties in large blocks; the pre-registered
    # instrument ranks by served PRICE, which is nearly tie-free because age and
    # eta enter it. If the tie structure is what moved the number, this variant
    # lands on the published figure.
    fv_raw = np.asarray([r["fv"] for r in pools["raw"]["rows"]], float)
    fv_nrm = np.asarray([r["fv"] for r in pools["normalized"]["rows"]], float)
    report["currency_ranked_on_served_fv"] = {
        "raw_v5": _currency_curve(cells["raw_v5"]["p"], truth, war, rank_on=fv_raw),
        "normalized_v6": _currency_curve(cells["normalized_v6"]["p"], truth, war,
                                         rank_on=fv_nrm)}
    report["tie_structure"] = {
        "n_rows": int(len(truth)),
        "distinct_served_fv_raw": int(len(np.unique(fv_raw))),
        "distinct_served_fv_normalized": int(len(np.unique(fv_nrm))),
        "distinct_served_price_raw_v5": int(len(np.unique(cells["raw_v5"]["p"]))),
        "distinct_served_price_normalized_v6": int(
            len(np.unique(cells["normalized_v6"]["p"]))),
        "largest_fv_tie_block_raw": int(np.bincount(
            np.unique(fv_raw, return_inverse=True)[1]).max())}

    rng2 = np.random.default_rng(SEED)
    draws2 = list(_boot_draws(uniq, idx, rng2, B_CURRENCY))
    old_p, new_p = cells["raw_v5"]["p"], cells["normalized_v6"]["p"]
    b_old, b_new, b_diff = [], [], []
    for sel in draws2:
        ts, ws = truth[sel], war[sel]
        co = _currency_point(old_p[sel], ts, ws)
        cn = _currency_point(new_p[sel], ts, ws)
        b_old.append(co)
        b_new.append(cn)
        if np.isfinite(co) and np.isfinite(cn):
            b_diff.append(co - cn)
    report["currency_bootstrap"] = {
        "instrument": "ranked on served PRICE (pre-registered)",
        "raw_v5": _ci(b_old), "normalized_v6": _ci(b_new),
        "paired_diff_old_minus_new": _ci(b_diff),
        "P(new_more_negative_than_old)": float(np.mean(np.asarray(b_diff) > 0))
        if b_diff else float("nan")}
    # Same bands for the PUBLISHED instrument (ranked on served FV), because that
    # is the one the program actually quotes and the like-for-like replacement
    # number has to carry a band too.
    f_old, f_new, f_diff = [], [], []
    for sel in draws2:
        ts, ws = truth[sel], war[sel]
        co = _currency_point(old_p[sel], ts, ws, rank_on=fv_raw[sel])
        cn = _currency_point(new_p[sel], ts, ws, rank_on=fv_nrm[sel])
        f_old.append(co)
        f_new.append(cn)
        if np.isfinite(co) and np.isfinite(cn):
            f_diff.append(co - cn)
    report["currency_bootstrap_served_fv_instrument"] = {
        "instrument": "ranked on served FV (reproduces the published stage-H figure)",
        "raw_v5": _ci(f_old), "normalized_v6": _ci(f_new),
        "paired_diff_old_minus_new": _ci(f_diff)}

    # ---- controls --------------------------------------------------------
    ctrl = {}
    med_fv = float(np.median([r["fv"] for r in rows]))
    const_raw = np.asarray([_raw_price_mm(med_fv, r["is_pitcher"], r["position"],
                                          r["age"], r["eta_years"]) for r in rows], float)
    ctrl["CTRL1_zero_information_board"] = {
        "constant_fv": med_fv,
        "v6": _err(_apply_cal(const_raw, live_cal), truth),
        "v5": _err(_apply_cal(const_raw, V5_KNOTS), truth)}

    rng3 = np.random.default_rng(SEED)
    perm = {}
    for name in ("raw_v5", "normalized_v6"):
        maes = []
        for _ in range(40):
            sh = cells[name]["p"][rng3.permutation(len(truth))]
            maes.append(float(np.abs(sh - truth).mean()))
        perm[name] = {"reps": 40, "mae_mean": float(np.mean(maes)),
                      "mae_sd": float(np.std(maes, ddof=1))}
    ctrl["CTRL2_permuted_board"] = perm

    rng4 = np.random.default_rng(SEED)
    ptruth = truth[rng4.permutation(len(truth))]
    ctrl["CTRL6_permuted_truth"] = {}
    for name in ("raw_v5", "normalized_v6"):
        a = _ladder(cells[name]["p"], cells[name]["p0"], ptruth)
        ctrl["CTRL6_permuted_truth"][name] = _partition(a, ptruth, "mae")
    ctrl["CTRL5_segment_sweep_note"] = ("see report['currency'][cell]['segments']; "
                                        "clause C5 evaluated below")
    report["controls"] = ctrl

    # ---- clause evaluation ----------------------------------------------
    cur_old = report["currency"]["raw_v5"]["currency_mm_per_0.01_rho"]
    cur_new = report["currency"]["normalized_v6"]["currency_mm_per_0.01_rho"]
    floor_ci = report["cells"]["normalized_v6"]["share_ci"]["mae_A_floor"]["ci95"]
    segs_new = report["currency"]["normalized_v6"]["segments"]
    mags = [abs(segs_new[str(w)]["mm_per_0.01_rho"]) for w in SEGMENTS]
    spread = max(mags) / min(mags) if min(mags) else float("inf")
    sums_ok = all(
        abs(report["cells"][c][f"partition_{l}"][k] - 1.0) < 1e-9
        for c in cells for l in ("mae", "mse")
        for k in ("sum_A", "sum_B", "sum_shapley"))
    diff_ci = report["currency_bootstrap"]["paired_diff_old_minus_new"]["ci95"]
    report["clauses"] = {
        "C0_v5_reconstruction": {"pass": bool(c0_max < 0.01), "max_dev_mm": c0_max},
        "C1_reproduction": {
            "raw_v5_currency": cur_old, "published_ci95": list(PUBLISHED_CI95),
            "pass": bool(PUBLISHED_CI95[0] <= cur_old <= PUBLISHED_CI95[1]),
            "post_hoc_diagnosis_ranked_on_served_fv": report[
                "currency_ranked_on_served_fv"]["raw_v5"]["currency_mm_per_0.01_rho"],
            "post_hoc_note": ("run AFTER C1 failed, to explain it; the C1 verdict "
                              "above is not re-specified")},
        "C2_partition_integrity": {"pass": bool(sums_ok), "tolerance": 1e-9},
        "C3_floor_term_gone": {
            "threshold_note": "SELF-ADDED THRESHOLD 0.05, decides this verdict",
            "norm_v6_floor_share_ci95": floor_ci,
            "gone": bool(floor_ci[1] < C3_GONE_THRESHOLD)},
        "C4_currency_moved": {
            "old": cur_old, "new": cur_new, "paired_diff_ci95": diff_ci,
            "material": bool(diff_ci[0] > 0 or diff_ci[1] < 0),
            "new_outside_published_band": bool(
                not (PUBLISHED_CI95[0] <= cur_new <= PUBLISHED_CI95[1]))},
        "C5_currency_is_a_currency": {
            "segment_magnitudes": {str(w): segs_new[str(w)]["mm_per_0.01_rho"]
                                   for w in SEGMENTS},
            "max_over_min": spread, "threshold": 2.0, "pass": bool(spread <= 2.0)},
    }
    report["runtime_s"] = round(time.time() - t_start, 1)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("wrote", OUT, "in", report["runtime_s"], "s")

    for name in ("raw_v5", "normalized_v5", "raw_v6", "normalized_v6"):
        e = report["cells"][name]
        pm = e["partition_mae"]
        ps = e["partition_mse"]
        print(f"\n== {name} ==  L2 {pm['L2']:.3f}  L1 {pm['L1']:.3f}  L0 {pm['L0']:.3f}"
              f"  L1B {pm['L1B']:.3f}")
        print(f"   MAE shares A rank {pm['order_A']['rank']:.3f} level "
              f"{pm['order_A']['level']:.3f} floor {pm['order_A']['floor']:.3f}"
              f" | B rank {pm['order_B']['rank']:.3f} level {pm['order_B']['level']:.3f}")
        print(f"   MSE shares A rank {ps['order_A']['rank']:.3f} level "
              f"{ps['order_A']['level']:.3f} floor {ps['order_A']['floor']:.3f}")
        print(f"   L2 bias {e['rungs']['L2']['bias']:.3f} cal_slope "
              f"{e['rungs']['L2'].get('cal_slope', float('nan')):.3f} "
              f"binned {e['binned_calibration_L2']['slope']:.3f}")
        print(f"   busts n={e['busts']['n']} served {e['busts']['served_price_mean_mm']:.3f} "
              f"L0 {e['busts']['L0_price_mean_mm']:.3f} truth "
              f"{e['busts']['truth_mean_mm']:.3f} L0share "
              f"{e['busts']['L0_share_of_total_L0_abs_err']:.3f}")
    print("\nclauses:", json.dumps(report["clauses"], indent=1)[:2500])


if __name__ == "__main__":
    main()
