# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- GATE RUN (docs/EFV_GATE_STANDARD.md).

Every claim carries: (1) a paired bootstrap resampling TRAIN AND TEST with a refit
per draw, (2) a zero-information control (row-permuted twin of the same column),
(3) a permutation null band, (4) the effect averaged over >= 4 independent time
splits (folds 2016-2020, the fully-resolved decision years).

Writes data/xfv_level_calibration_eval.json.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import efv_model as M                      # noqa: E402
import value_framework as vf               # noqa: E402
from efv_dataset import matrix_path        # noqa: E402
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration  # noqa: E402

OUT = HERE / "_sweep_calib_out"
OUT.mkdir(exist_ok=True)
ART = ROOT / "data" / "xfv_level_calibration_eval.json"

FOLDS = (2016, 2017, 2018, 2019, 2020)     # fully resolved decision years
TARGET_SEASONS = 6
B = int(sys.argv[2]) if len(sys.argv) > 2 else 500
SEED = 7
TIERS = (35, 40, 45, 50, 55, 60)
# BUST, two readings. PRIMARY = the repo's own operative threshold: first-6yr summed
# bWAR < 0.5 (efv_model._SF_BUST_WAR, and empirical_anchors' bust_pct which counts
# realized_war/6 < 0.5/6). LITERAL = the config band "<0.5" read as an average over the
# 6-season window (< 3.0 summed). The config calls the bands per-SEASON projected TALENT
# normalized to 600 PA / 200 IP, which no realized accumulation reproduces exactly, so
# both are reported.
BUST_SUM = 0.5
BUST_SUM_LITERAL = 3.0
CV = (0.0, 0.30, 0.38, 0.48, 0.70)
CFG_MID = (0.0, 1.0, 2.0, 3.2, 5.0)         # buckets.*.midpoint_war (per season)


@lru_cache(maxsize=400000)
def _rif(war_r, is_pit, age_r, pos):
    return vf.realized_implied_fv(war_r, is_pit, age=age_r, position=pos,
                                  exposure_seasons=TARGET_SEASONS)


@lru_cache(maxsize=200000)
def _pb(g_r, is_pit):
    return tuple(vf.p_bucket_given_fv(g_r, is_pit) or (0.0,) * 5)


@lru_cache(maxsize=200000)
def _implied(g_r):
    v = vf.fv_to_6yr_avg_war(g_r)
    return None if v is None else v * 6.0


@lru_cache(maxsize=200000)
def _war_band(g_r, is_pit, lo=0.10, hi=0.90):
    """q10/q90 of the first-6yr-WAR distribution induced by the SAME bucket mixture the
    served $ band is drawn from. Per-bucket per-season level = buckets.midpoint_war *
    vf._war_scale_for(grade, role) -- the engine's FV-dependent reconciliation scalar, so
    the mixture mean equals 6 * fv_to_6yr_avg_war(grade) exactly, as the engine enforces.
    WAR | bucket ~ mean-preserving Gamma at within_bucket_cv; bust = point mass at 0."""
    p = np.asarray(_pb(g_r, is_pit), dtype=float)
    if p.sum() <= 0:
        return (0.0, 0.0)
    p = p / p.sum()
    k = vf._war_scale_for(g_r, "pitcher" if is_pit else "hitter")
    mid = [m * k * 6.0 for m in CFG_MID]      # summed over the 6-season window
    rng = np.random.RandomState(abs(hash((g_r, is_pit))) % (2 ** 31))
    idx = rng.choice(5, size=8000, p=p)
    out = np.zeros(8000)
    for b in range(1, 5):
        m = idx == b
        c = int(m.sum())
        if c and mid[b] > 0:
            out[m] = rng.gamma(1.0 / CV[b] ** 2, mid[b] * CV[b] ** 2, size=c)
    return (float(np.quantile(out, lo)), float(np.quantile(out, hi)))


def _age_at(birth_date, year):
    if not birth_date:
        return None
    try:
        return float(int(year) - int(str(birth_date)[:4]))
    except (TypeError, ValueError):
        return None


def _acq(r):
    if float(r.get("is_ifa") or 0) >= 0.5:
        return "IFA"
    if float(r.get("is_college") or 0) >= 0.5:
        return "college"
    if r.get("pick_overall") is not None:
        return "HS"
    return "unknown"


def load_side(side):
    raw_rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    raw = [r for r in raw_rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    meta = {}
    for r in raw:
        milb = r.get("milb") or {}
        dy = r.get("debut_year") or M._decision_year(r)
        meta[r["player_key"]] = {
            "level": milb.get("milb_level"), "age": milb.get("age"),
            "acq": _acq(r), "position": r.get("position"),
            "gm_age": (lambda a: None if a is None else a + TARGET_SEASONS)(_age_at(r.get("birth_date"), dy)),
            "has_milb": bool(milb),
        }
    data = M._prep(raw, "target_censored", side)
    for d in data:
        d.update(meta[d["player_key"]])
    return data


def score_folds(data, side, lam, keys, folds=FOLDS, permute_grade=False,
                permute_war=False, rng=None):
    """Forward-chained OOS scoring of the SERVED stack. Returns scored test rows."""
    is_pit = side == "pit"
    out = []
    for yr in folds:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = M._fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        pool = []
        for r in te:
            xw = max(-2.0, a + b * _predict(ridge, r["feats"]))
            g_raw = _rif(round(xw, 2), is_pit, r["gm_age"], r["position"])
            if g_raw is None:
                continue
            cw = max(0.0, M._pred_ols(ols, r["fv"]))
            pool.append({"pk": r["player_key"], "war": r["target"], "fv": r["fv"],
                         "rank_war": (1 - lam) * cw + lam * xw,
                         "g_raw": round(float(g_raw), 1),
                         "level": r["level"], "age": r["age"], "acq": r["acq"],
                         "has_milb": r["has_milb"], "year": yr})
        if not pool:
            continue
        target = sorted(p["fv"] for p in pool)
        order = sorted(range(len(pool)), key=lambda i: (pool[i]["rank_war"], pool[i]["pk"]))
        m = len(pool)
        for rp, i in enumerate(order):
            pos = ((rp / (m - 1)) if m > 1 else 0.0) * (m - 1)
            lo = int(pos); hi = min(m - 1, lo + 1); f = pos - lo
            pool[i]["g_disp"] = round(target[lo] * (1 - f) + target[hi] * f, 1)
        if permute_grade:                       # zero-information twin of the GRADE column
            gs = [p["g_disp"] for p in pool]
            gr = [p["g_raw"] for p in pool]
            rng.shuffle(gs); rng.shuffle(gr)
            for p, g1, g2 in zip(pool, gs, gr):
                p["g_disp"], p["g_raw"] = g1, g2
        if permute_war:                         # permutation null for the OUTCOME
            ws = [p["war"] for p in pool]
            rng.shuffle(ws)
            for p, w in zip(pool, ws):
                p["war"] = w
        out.extend(pool)
    return out


def _tier_bias(rows, prefix, s):
    by = defaultdict(list)
    for r in rows:
        t = int(round(r["g_disp"] / 5) * 5)
        if t in TIERS:
            by[t].append(r["war"] - _implied(r["g_disp"]))
    for t in TIERS:
        s[f"{prefix}bias_t{t}"] = statistics.mean(by[t]) if len(by[t]) >= 5 else None
        s[f"{prefix}n_t{t}"] = len(by[t])


def stats(scored):
    """All calibration statistics for one scored pool (one side)."""
    if not scored:
        return {}
    s = {}
    imp = [_implied(r["g_disp"]) for r in scored]
    war = [r["war"] for r in scored]
    s["pooled_bias"] = statistics.mean(w - i for w, i in zip(war, imp))
    s["mean_implied"] = statistics.mean(imp)
    s["mean_realized"] = statistics.mean(war)
    _tier_bias(scored, "", s)
    by = defaultdict(list)
    for r, i in zip(scored, imp):
        t = int(round(r["g_disp"] / 5) * 5)
        if t in TIERS:
            by[t].append(r["war"] - i)

    # --- LIVE-COMPARABLE subset: the served board scores only players with a pro
    # track record (xfv.json meta), so these are the numbers that govern served output.
    lm = [r for r in scored if r["has_milb"]]
    if lm:
        s["lm_n"] = len(lm)
        s["lm_pooled_bias"] = statistics.mean(r["war"] - _implied(r["g_disp"]) for r in lm)
        _tier_bias(lm, "lm_", s)
        s["lm_mean_p_bust"] = statistics.mean(_pb(r["g_raw"], r.get("_is_pit", False))[0] for r in lm)
        s["lm_realized_bust_rate"] = sum(1 for r in lm if r["war"] < BUST_SUM) / len(lm)
        s["lm_p_bust_gap"] = s["lm_mean_p_bust"] - s["lm_realized_bust_rate"]
        s["lm_realized_bust_rate_literal"] = sum(1 for r in lm if r["war"] < BUST_SUM_LITERAL) / len(lm)
        s["lm_p_bust_gap_literal"] = s["lm_mean_p_bust"] - s["lm_realized_bust_rate_literal"]
        cov, covlo, covhi = [], [], []
        for r in lm:
            q10, q90 = _war_band(r["g_disp"], r.get("_is_pit", False))
            cov.append(1 if q10 <= r["war"] <= q90 else 0)
            covlo.append(1 if r["war"] < q10 else 0)
            covhi.append(1 if r["war"] > q90 else 0)
        s["lm_coverage"] = statistics.mean(cov)
        s["lm_miss_low"] = statistics.mean(covlo)     # nominal 0.10
        s["lm_miss_high"] = statistics.mean(covhi)    # nominal 0.10

    # --- OOS dispersion of the WAR prediction: realized ~ a + b*rank_war.
    # b < 1 == the served xfv_war_6yr is over-dispersed (a shrinkage deficit).
    xs = [r["rank_war"] for r in scored]
    ys = war
    mx, my = statistics.mean(xs), statistics.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    s["oos_shrink_slope"] = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else None
    s["oos_shrink_intercept"] = (my - s["oos_shrink_slope"] * mx) if s["oos_shrink_slope"] is not None else None
    s["pred_bias_rank_war"] = statistics.mean(x - y for x, y in zip(xs, ys))

    # --- comparator: the SAME anchor read at the CONSENSUS grade (is the level bias
    # an eFV artifact, or the anchor table itself?)
    s["cons_pooled_bias"] = statistics.mean(r["war"] - _implied(round(r["fv"], 1)) for r in scored)
    if lm:
        s["lm_cons_pooled_bias"] = statistics.mean(r["war"] - _implied(round(r["fv"], 1)) for r in lm)
    # slope of bias on tier (the "is it a slope problem" statistic)
    pts = [(t, s[f"bias_t{t}"]) for t in TIERS if s.get(f"bias_t{t}") is not None]
    if len(pts) >= 3:
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        s["bias_slope_per_fv_pt"] = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else None
    else:
        s["bias_slope_per_fv_pt"] = None
    # p_bust (served at the REALIZED grade)
    pbs = [_pb(r["g_raw"], r.get("_is_pit", False))[0] for r in scored]
    s["mean_p_bust"] = statistics.mean(pbs)
    s["realized_bust_rate"] = sum(1 for w in war if w < BUST_SUM) / len(war)
    s["p_bust_gap"] = s["mean_p_bust"] - s["realized_bust_rate"]
    s["realized_bust_rate_literal"] = sum(1 for w in war if w < BUST_SUM_LITERAL) / len(war)
    s["p_bust_gap_literal"] = s["mean_p_bust"] - s["realized_bust_rate_literal"]
    # p_bust gap by DISPLAYED tier (the reliability surface, not just the marginal)
    byt = defaultdict(list)
    for r in scored:
        t = int(round(r["g_disp"] / 5) * 5)
        if t in TIERS:
            byt[t].append(r)
    for t in TIERS:
        g = byt[t]
        s[f"pbust_gap_t{t}"] = (statistics.mean(_pb(r["g_raw"], r.get("_is_pit", False))[0] for r in g)
                                - sum(1 for r in g if r["war"] < BUST_SUM) / len(g)) if len(g) >= 5 else None
    # coverage of the induced 80% WAR band at the DISPLAYED grade
    cov, cov_milb, cov_nomilb = [], [], []
    covlev = defaultdict(list)
    for r in scored:
        q10, q90 = _war_band(r["g_disp"], r.get("_is_pit", False))
        c = 1 if q10 <= r["war"] <= q90 else 0
        cov.append(c)
        (cov_milb if r["has_milb"] else cov_nomilb).append(c)
        covlev[r["level"] or "none"].append(c)
    s["coverage_marginal"] = statistics.mean(cov)
    s["coverage_has_milb"] = statistics.mean(cov_milb) if cov_milb else None
    s["coverage_no_milb"] = statistics.mean(cov_nomilb) if cov_nomilb else None
    for lv in ("A", "A+", "AA", "AAA"):
        s[f"coverage_{lv}"] = statistics.mean(covlev[lv]) if len(covlev[lv]) >= 5 else None
    s["coverage_cond_spread"] = ((s["coverage_no_milb"] - s["coverage_has_milb"])
                                 if (s["coverage_has_milb"] is not None
                                     and s["coverage_no_milb"] is not None) else None)
    return s


def run_once(data_by_side, lams, keys_by_side, permute_grade=False, permute_war=False, rng=None):
    out = {}
    for side in ("hit", "pit"):
        sc = score_folds(data_by_side[side], side, lams[side], keys_by_side[side],
                         permute_grade=permute_grade, permute_war=permute_war, rng=rng)
        for r in sc:
            r["_is_pit"] = side == "pit"
        out[side] = stats(sc)
        out[side]["n"] = len(sc)
    return out


def _ci(vals, lo=2.5, hi=97.5):
    v = [x for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if len(v) < 10:
        return None
    return [round(float(np.percentile(v, lo)), 4), round(float(np.percentile(v, hi)), 4)]


def main():
    lams, lam_src = M._sf_live_lambdas()
    data_by_side = {s: load_side(s) for s in ("hit", "pit")}
    keys_by_side = {s: M._feature_spec(s)[0] for s in ("hit", "pit")}

    point = run_once(data_by_side, lams, keys_by_side)

    # --- per-fold (time-split) point estimates -----------------------------
    per_fold = {}
    for side in ("hit", "pit"):
        per_fold[side] = {}
        for yr in FOLDS:
            sc = score_folds(data_by_side[side], side, lams[side], keys_by_side[side], folds=(yr,))
            for r in sc:
                r["_is_pit"] = side == "pit"
            per_fold[side][str(yr)] = stats(sc)

    # --- paired bootstrap (resample TRAIN AND TEST, refit per draw) --------
    rng = random.Random(SEED)
    nprng = np.random.RandomState(SEED)
    draws = {s: defaultdict(list) for s in ("hit", "pit")}
    ctrl_grade = {s: defaultdict(list) for s in ("hit", "pit")}
    ctrl_war = {s: defaultdict(list) for s in ("hit", "pit")}
    for it in range(B):
        boot = {}
        for side in ("hit", "pit"):
            d = data_by_side[side]
            idx = nprng.randint(0, len(d), len(d))
            boot[side] = [d[i] for i in idx]
        r1 = run_once(boot, lams, keys_by_side)
        r2 = run_once(boot, lams, keys_by_side, permute_grade=True, rng=rng)
        r3 = run_once(boot, lams, keys_by_side, permute_war=True, rng=rng)
        for side in ("hit", "pit"):
            for k, v in r1[side].items():
                draws[side][k].append(v)
            for k, v in r2[side].items():
                ctrl_grade[side][k].append(v)
            for k, v in r3[side].items():
                ctrl_war[side][k].append(v)
        if (it + 1) % 50 == 0:
            print(f"  boot {it+1}/{B}", flush=True)

    art = {
        "generated_at": __import__("datetime").date.today().isoformat(),
        "lane": "calibration -- LEVEL calibration audit of eFV",
        "standard": "docs/EFV_GATE_STANDARD.md",
        "lambda": lams, "lambda_source": lam_src,
        "folds": list(FOLDS),
        "frame": ("forward-chained OOS reproduction of efv_score.run: OLS(FV) anchor + lean "
                  "ridge + linear output calibration -> rank_war blend -> per-fold "
                  "rank-preserving quantile display map. Fully-resolved decision years only "
                  "(6yr window closed by 2025); KM target == resolved target on every row."),
        "definitions": {
            "implied_war": "6 * value_framework.fv_to_6yr_avg_war(grade) -- the config's own "
                           "declared level meaning of a grade (first-6yr summed bWAR)",
            "bust": "realized first-6yr summed bWAR < 3.0 == the config buckets.bust band "
                    "'<0.5' average WAR/yr over the 6-season window",
            "coverage": "80% nominal, on the first-6yr-WAR distribution induced by the SAME "
                        "bucket mixture the served $ band is drawn from",
        },
        "bootstrap": {"B": B, "seed": SEED,
                      "scheme": "resample the whole side pool (train AND test) with "
                                "replacement, refit OLS + ridge + output calibration on "
                                "every draw"},
        "point": point,
        "per_fold": per_fold,
        "boot_ci95": {s: {k: _ci(v) for k, v in draws[s].items()} for s in ("hit", "pit")},
        "zero_info_control_permuted_grade_ci95": {
            s: {k: _ci(v) for k, v in ctrl_grade[s].items()} for s in ("hit", "pit")},
        "permutation_null_permuted_outcome_ci95": {
            s: {k: _ci(v) for k, v in ctrl_war[s].items()} for s in ("hit", "pit")},
    }
    ART.write_text(json.dumps(art, indent=1), encoding="utf-8")
    (OUT / "gate.json").write_text(json.dumps(art, indent=1), encoding="utf-8")
    print("wrote", ART)


if __name__ == "__main__":
    main()
