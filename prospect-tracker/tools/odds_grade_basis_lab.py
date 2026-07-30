# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE-ODDS: is p_bust better keyed to the RETIRED grade map or the NEW one?

MEASUREMENT ONLY. This module imports production code read-only, edits nothing, and
writes exactly one artifact (data/odds_grade_basis_eval.json). It is never imported by
the site or by any exporter.

Pre-registration (written to disk BEFORE this lab ran, and not altered afterwards):
docs/efv-2026-07-30/ODDS_GRADE_BASIS_GATE.md. Gate standard: docs/EFV_GATE_STANDARD.md.

THE CONTEST
-----------
efv_score.run computes TWO grades from the same predicted WAR:

    xfv_grade   = vf.outcome_implied_fv(xfv_war)                       -> the board grade
    _odds_grade = vf.realized_implied_fv(xfv_war, is_pit, age, pos)    -> the odds key

and pins p_bucket / p_bust / sv_distribution to the second (the RETIRED map). This lab
replays efv_score.run's own scoring chain out of fold, forward-chained over decision
years 2014-2020, and scores the resulting probabilities against the realized outcome
under BOTH keyings.

Run:  python -m tools.odds_grade_basis_lab            (from the repo root)
      python -m tools.odds_grade_basis_lab --quick    (B=100, for a smoke check)
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

import value_framework as vf                                    # noqa: E402
import efv_model as em                                          # noqa: E402
import efv_score as es                                          # noqa: E402
from efv_dataset import matrix_path, TARGET_SEASONS             # noqa: E402

# --- pre-registered constants (PART 1 of the gate doc) ----------------------
BUST_AVG_WAR = 0.5      # value_framework_config.yaml:38  buckets.bust.band "<0.5"
STAR_AVG_WAR = 4.0      # value_framework_config.yaml:42  buckets.star.band "4.0+"
CAL_YEARS = (2014, 2015, 2016, 2017, 2018, 2019, 2020)
PLATT_YEARS = CAL_YEARS[1:]      # nested chain: fold 2014 is the first Platt training set
N_BINS = 10
B_BOOT = 1000
B_PERM = 1000
SEED = 20260730
_EPS = 1e-6

BUST_IDX, STAR_IDX = 0, 4
ARMS = ("A_pin", "B_rekey", "C_zeroinfo", "D_twin_rankB", "E_twin_rankA",
        "F_pin_platt", "G_rekey_platt")


def bust_label(target_resolved: float) -> int:
    """The SHIPPED bust event (tools/_prem_odds.py:41): 6yr-AVERAGE annual WAR < 0.5."""
    return 1 if (float(target_resolved) / float(TARGET_SEASONS)) < BUST_AVG_WAR else 0


def star_label(target_resolved: float) -> int:
    """The same five-bucket ladder at the top end: 6yr-AVERAGE annual WAR >= 4.0."""
    return 1 if (float(target_resolved) / float(TARGET_SEASONS)) >= STAR_AVG_WAR else 0


# ===========================================================================
# metric primitives
# ===========================================================================
def brier(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2)) if p.size else float("nan")


def logloss(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    if not p.size:
        return float("nan")
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _equal_count_bins(p, n_bins: int):
    """Indices grouped into n_bins near-equal-count bins by ascending p."""
    order = np.argsort(p, kind="stable")
    return [b for b in np.array_split(order, n_bins) if b.size]


def murphy(p, y, n_bins: int = N_BINS) -> dict:
    """Brier = reliability - resolution + uncertainty on equal-count bins, plus ECE."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    n = p.size
    if n == 0:
        return {k: float("nan") for k in
                ("reliability", "resolution", "uncertainty", "ece", "brier_binned")}
    obar = float(y.mean())
    rel = res = ece = 0.0
    for b in _equal_count_bins(p, n_bins):
        w = b.size / n
        pb, ob = float(p[b].mean()), float(y[b].mean())
        rel += w * (pb - ob) ** 2
        res += w * (ob - obar) ** 2
        ece += w * abs(pb - ob)
    unc = obar * (1.0 - obar)
    return {"reliability": rel, "resolution": res, "uncertainty": unc, "ece": ece,
            "brier_binned": rel - res + unc}


def _wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def reliability_curve(p, y, n_bins: int = N_BINS) -> list[dict]:
    p, y = np.asarray(p, float), np.asarray(y, float)
    out = []
    for b in _equal_count_bins(p, n_bins):
        k = int(y[b].sum())
        lo, hi = _wilson(k, b.size)
        out.append({"n": int(b.size),
                    "p_lo": round(float(p[b].min()), 4),
                    "p_hi": round(float(p[b].max()), 4),
                    "pred": round(float(p[b].mean()), 4),
                    "obs": round(k / b.size, 4),
                    "obs_ci95": [round(lo, 4), round(hi, 4)]})
    return out


def _logit(p):
    p = np.clip(np.asarray(p, float), _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


def irls_logit(x, y, iters: int = 60):
    """Newton/IRLS fit of y ~ a + b*x. Returns (a, b) or None on failure."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = x.size
    if n < 12 or len(np.unique(y)) < 2:
        return None
    X = np.column_stack([np.ones(n), x])
    beta = np.zeros(2)
    for _ in range(iters):
        eta = np.clip(X @ beta, -35, 35)
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(mu * (1 - mu), 1e-9, None)
        z = eta + (y - mu) / w
        A = X.T @ (X * w[:, None]) + 1e-8 * np.eye(2)
        try:
            nb = np.linalg.solve(A, X.T @ (w * z))
        except np.linalg.LinAlgError:
            return None
        if not np.all(np.isfinite(nb)):
            return None
        if np.max(np.abs(nb - beta)) < 1e-9:
            beta = nb
            break
        beta = nb
    return float(beta[0]), float(beta[1])


def calibration_ab(p, y):
    """(intercept, slope) of y ~ a + b*logit(p). Perfect calibration is (0, 1)."""
    r = irls_logit(_logit(p), y)
    return (None, None) if r is None else r


def auc(p, y) -> float | None:
    p, y = np.asarray(p, float), np.asarray(y, float)
    pos, neg = p[y == 1], p[y == 0]
    if pos.size == 0 or neg.size == 0:
        return None
    order = np.argsort(p, kind="stable")
    ranks = np.empty(p.size, float)
    sp = p[order]
    i = 0
    while i < sp.size:
        j = i
        while j + 1 < sp.size and sp[j + 1] == sp[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return float((ranks[y == 1].sum() - pos.size * (pos.size + 1) / 2.0)
                 / (pos.size * neg.size))


def platt_apply(p, ab):
    if ab is None:
        return np.asarray(p, float)
    a, b = ab
    z = np.clip(a + b * _logit(p), -35, 35)
    return 1.0 / (1.0 + np.exp(-z))


def quantile_match(p_rank, p_marginal):
    """The ranking of `p_rank` carrying the marginal distribution of `p_marginal`."""
    p_rank, p_marginal = np.asarray(p_rank, float), np.asarray(p_marginal, float)
    order = np.argsort(p_rank, kind="stable")
    out = np.empty_like(p_rank)
    out[order] = np.sort(p_marginal, kind="stable")
    return out


# ===========================================================================
# the out-of-fold scoring chain (efv_score.run's chain, forward-chained)
# ===========================================================================
def load_side(side: str):
    is_pit = side == "pit"
    keys, _mono = em._feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    by_key = {r["player_key"]: r for r in pool}
    data = em._prep(pool, "target_censored", side)
    # Per-row static grade-map inputs, resolved once (they never change across draws).
    ctx = {}
    for r in data:
        src = by_key[r["player_key"]]
        dyear = src.get("debut_year") or 2020
        ctx[r["player_key"]] = {
            "gm_age": es._grade_map_age(es._age_at(src.get("birth_date"), dyear), 0.0),
            "position": src.get("position"),
            "censored": src.get("censored"),
            "target_resolved": src.get("target_resolved"),
            "kind": src.get("kind"),
            "has_track": (isinstance(src.get("milb"), dict)
                          and float((src.get("milb") or {}).get("rates_missing", 1.0) or 0.0) == 0.0),
        }
    return {"side": side, "is_pit": is_pit, "keys": keys, "data": data, "ctx": ctx}


_GRADE_MEMO: dict = {}


def _grades(war: float, is_pit: bool, gm_age, pos):
    """(old realized-implied grade, new outcome-implied grade). Memoized on a
    3dp WAR grid: both maps are smooth and the memo is a pure speed device for the
    1000-draw bootstrap. Production is unaffected (this module is never imported)."""
    k = (round(float(war), 3), is_pit, None if gm_age is None else round(float(gm_age), 1), pos)
    hit = _GRADE_MEMO.get(k)
    if hit is None:
        g_old = vf.realized_implied_fv(war, is_pit, age=gm_age, position=pos,
                                       exposure_seasons=TARGET_SEASONS)
        g_new = vf.outcome_implied_fv(war, exposure_seasons=TARGET_SEASONS)
        po = vf.p_bucket_given_fv(g_old, is_pit) if g_old is not None else None
        pn = vf.p_bucket_given_fv(g_new, is_pit) if g_new is not None else None
        hit = (g_old, g_new, po, pn)
        _GRADE_MEMO[k] = hit
    return hit


def score_chain(bundle, data=None, *, with_platt: bool = True) -> list[dict]:
    """Forward-chained OOS replication of efv_score.run's scoring chain, emitting BOTH
    keyings' bucket vectors for every resolved test row."""
    keys, is_pit, ctx = bundle["keys"], bundle["is_pit"], bundle["ctx"]
    data = bundle["data"] if data is None else data
    by_year = {}
    for r in data:
        by_year.setdefault(r["decision_year"], []).append(r)

    out = []
    for yr in CAL_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = by_year.get(yr, [])
        if len(te) < 15 or len(tr) < 60:
            continue
        ridge = em._fit_ridge(tr, keys)
        ols = em._fit_ols_fv(tr)
        if not (ridge and ols):
            continue
        cal = em._fit_linear_calibration(
            [(em._predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            c = ctx[r["player_key"]]
            if c["censored"] is not False or not isinstance(c["target_resolved"], (int, float)):
                continue
            war = max(-2.0, a + b * em._predict(ridge, r["feats"]))
            g_old, g_new, po, pn = _grades(war, is_pit, c["gm_age"], c["position"])
            if g_old is None or g_new is None or not po or not pn:
                continue
            tres = float(c["target_resolved"])
            out.append({
                "player_key": r["player_key"], "fold": yr, "kind": c["kind"],
                "has_track": c["has_track"], "xfv_war": float(war),
                "grade_old": float(g_old), "grade_new": float(g_new),
                "A_bust": float(po[BUST_IDX]), "B_bust": float(pn[BUST_IDX]),
                "A_star": float(po[STAR_IDX]), "B_star": float(pn[STAR_IDX]),
                "y_bust": bust_label(tres), "y_star": star_label(tres),
                "target_resolved": tres,
            })
    if with_platt:
        _attach_platt(out)
    return out


def _attach_platt(rows: list[dict]) -> None:
    """Nested forward chain: the Platt map served on fold Y is fit ONLY on the rows
    scored out of fold in folds < Y. Fold CAL_YEARS[0] therefore carries no Platt arm."""
    for lab in ("bust", "star"):
        for yr in CAL_YEARS:
            hist = [r for r in rows if r["fold"] < yr]
            cur = [r for r in rows if r["fold"] == yr]
            if not cur:
                continue
            if len(hist) < 25:
                for r in cur:
                    r[f"F_{lab}"] = r[f"A_{lab}"]
                    r[f"G_{lab}"] = r[f"B_{lab}"]
                    r[f"platt_{lab}"] = False
                continue
            y = np.array([r[f"y_{lab}"] for r in hist], float)
            ab_a = irls_logit(_logit([r[f"A_{lab}"] for r in hist]), y)
            ab_b = irls_logit(_logit([r[f"B_{lab}"] for r in hist]), y)
            fa = platt_apply([r[f"A_{lab}"] for r in cur], ab_a)
            gb = platt_apply([r[f"B_{lab}"] for r in cur], ab_b)
            for r, va, vb in zip(cur, fa, gb):
                r[f"F_{lab}"] = float(va)
                r[f"G_{lab}"] = float(vb)
                r[f"platt_{lab}"] = ab_a is not None and ab_b is not None


def attach_derived(rows: list[dict], train_base: dict) -> None:
    """Arms C (zero-info), D and E (rank-identical twins). Twins are matched on the
    frame being evaluated, which is deliberately GENEROUS to the ranking hypothesis."""
    for lab in ("bust", "star"):
        for r in rows:
            r[f"C_{lab}"] = float(train_base[lab].get(r["fold"], 0.5))
        if not rows:
            continue
        pa = np.array([r[f"A_{lab}"] for r in rows], float)
        pb = np.array([r[f"B_{lab}"] for r in rows], float)
        d = quantile_match(pb, pa)      # B's ranking, A's marginal
        e = quantile_match(pa, pb)      # A's ranking, B's marginal
        for r, dv, ev in zip(rows, d, e):
            r[f"D_{lab}"] = float(dv)
            r[f"E_{lab}"] = float(ev)


def training_base_rates(bundle, data=None) -> dict:
    """Fold -> base rate of each label among the fold's RESOLVED TRAINING rows.
    This is arm C: the honest zero-information forecast available at decision time."""
    ctx = bundle["ctx"]
    data = bundle["data"] if data is None else data
    out = {"bust": {}, "star": {}}
    for yr in CAL_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        lab = [(bust_label(ctx[r["player_key"]]["target_resolved"]),
                star_label(ctx[r["player_key"]]["target_resolved"]))
               for r in tr
               if ctx[r["player_key"]]["censored"] is False
               and isinstance(ctx[r["player_key"]]["target_resolved"], (int, float))]
        if lab:
            out["bust"][yr] = sum(x[0] for x in lab) / len(lab)
            out["star"][yr] = sum(x[1] for x in lab) / len(lab)
        else:
            out["bust"][yr] = 0.5
            out["star"][yr] = 0.01
    return out


# ===========================================================================
# reporting
# ===========================================================================
def arm_report(rows: list[dict], arm: str, lab: str) -> dict:
    key = f"{arm.split('_')[0]}_{lab}"
    p = np.array([r[key] for r in rows], float)
    y = np.array([r[f"y_{lab}"] for r in rows], float)
    m = murphy(p, y)
    a, b = calibration_ab(p, y)
    return {
        "n": int(p.size), "n_pos": int(y.sum()),
        "brier": round(brier(p, y), 6), "logloss": round(logloss(p, y), 6),
        "ece": round(m["ece"], 6),
        "reliability": round(m["reliability"], 6),
        "resolution": round(m["resolution"], 6),
        "uncertainty": round(m["uncertainty"], 6),
        "cal_slope": (None if b is None else round(b, 4)),
        "cal_intercept": (None if a is None else round(a, 4)),
        "cal_in_the_large": round(float(p.mean() - y.mean()), 6),
        "mean_p": round(float(p.mean()), 6), "base_rate": round(float(y.mean()), 6),
        "auc": (None if auc(p, y) is None else round(auc(p, y), 4)),
    }


def cut_report(rows: list[dict], lab: str) -> dict:
    if not rows:
        return {}
    out = {"arms": {a: arm_report(rows, a, lab) for a in ARMS}}
    out["reliability_curve"] = {
        "A_pin": reliability_curve([r[f"A_{lab}"] for r in rows], [r[f"y_{lab}"] for r in rows]),
        "B_rekey": reliability_curve([r[f"B_{lab}"] for r in rows], [r[f"y_{lab}"] for r in rows]),
    }
    per_fold = {}
    for yr in CAL_YEARS:
        sub = [r for r in rows if r["fold"] == yr]
        if len(sub) < 10:
            continue
        per_fold[str(yr)] = {
            "n": len(sub), "base_rate": round(float(np.mean([r[f"y_{lab}"] for r in sub])), 4),
            "brier_A": round(brier([r[f"A_{lab}"] for r in sub], [r[f"y_{lab}"] for r in sub]), 6),
            "brier_B": round(brier([r[f"B_{lab}"] for r in sub], [r[f"y_{lab}"] for r in sub]), 6),
            "logloss_A": round(logloss([r[f"A_{lab}"] for r in sub], [r[f"y_{lab}"] for r in sub]), 6),
            "logloss_B": round(logloss([r[f"B_{lab}"] for r in sub], [r[f"y_{lab}"] for r in sub]), 6),
            "brier_C": round(brier([r[f"C_{lab}"] for r in sub], [r[f"y_{lab}"] for r in sub]), 6),
        }
        per_fold[str(yr)]["d_brier"] = round(per_fold[str(yr)]["brier_A"] - per_fold[str(yr)]["brier_B"], 6)
        per_fold[str(yr)]["d_logloss"] = round(per_fold[str(yr)]["logloss_A"] - per_fold[str(yr)]["logloss_B"], 6)
    out["per_fold"] = per_fold
    return out


# ===========================================================================
# controls
# ===========================================================================
def _deltas(rows, lab) -> dict:
    """d = metric(A) - metric(B); positive means the RE-KEY is better."""
    y = [r[f"y_{lab}"] for r in rows]
    pa, pb = [r[f"A_{lab}"] for r in rows], [r[f"B_{lab}"] for r in rows]
    pf = [r.get(f"F_{lab}", r[f"A_{lab}"]) for r in rows]
    pg = [r.get(f"G_{lab}", r[f"B_{lab}"]) for r in rows]
    return {
        "d_brier": brier(pa, y) - brier(pb, y),
        "d_logloss": logloss(pa, y) - logloss(pb, y),
        "d_ece": murphy(pa, y)["ece"] - murphy(pb, y)["ece"],
        "d_brier_platt": brier(pf, y) - brier(pg, y),
        "d_logloss_platt": logloss(pf, y) - logloss(pg, y),
    }


def paired_bootstrap(bundles, B: int, seed: int = SEED, verbose: bool = True) -> dict:
    """Cluster (player_key) paired bootstrap resampling TRAIN AND TEST with a full
    refit of the ridge + linear-calibration + consensus-OLS chain on every draw."""
    cut_names = ("hit", "pit", "pooled",
                 "hit_served", "pit_served", "pooled_served")
    draws = {c: {lab: {k: [] for k in
                       ("d_brier", "d_logloss", "d_ece", "d_brier_platt", "d_logloss_platt")}
                 for lab in ("bust", "star")}
             for c in cut_names}
    t0 = time.time()
    for i in range(B):
        rng = np.random.RandomState(seed + i)
        per_side_rows = {}
        for side, bundle in bundles.items():
            data = bundle["data"]
            idx = rng.randint(0, len(data), len(data))
            resampled = [data[j] for j in idx]
            base = training_base_rates(bundle, resampled)
            rows = score_chain(bundle, resampled, with_platt=True)
            if rows:
                attach_derived(rows, base)
            per_side_rows[side] = rows
        pooled = per_side_rows.get("hit", []) + per_side_rows.get("pit", [])
        srv = {k: [r for r in v if r["has_track"]] for k, v in per_side_rows.items()}
        for cut, rows in (("hit", per_side_rows.get("hit", [])),
                          ("pit", per_side_rows.get("pit", [])),
                          ("pooled", pooled),
                          ("hit_served", srv.get("hit", [])),
                          ("pit_served", srv.get("pit", [])),
                          ("pooled_served", srv.get("hit", []) + srv.get("pit", []))):
            if len(rows) < 30:
                continue
            for lab in ("bust", "star"):
                if len(set(r[f"y_{lab}"] for r in rows)) < 2:
                    continue
                for k, v in _deltas(rows, lab).items():
                    if v == v:                      # skip NaN
                        draws[cut][lab][k].append(v)
        if verbose and (i + 1) % 50 == 0:
            el = time.time() - t0
            print(f"    bootstrap {i+1}/{B}  {el:.0f}s elapsed, "
                  f"~{el/(i+1)*(B-i-1):.0f}s left", flush=True)
    return {c: {lab: {k: _ci(v) for k, v in d.items()} for lab, d in cd.items()}
            for c, cd in draws.items()}


def _ci(vals) -> dict:
    if not vals:
        return {"n_draws": 0}
    a = np.asarray(vals, float)
    return {"n_draws": int(a.size), "mean": round(float(a.mean()), 6),
            "sd": round(float(a.std(ddof=1)), 6) if a.size > 1 else None,
            "ci95": [round(float(np.percentile(a, 2.5)), 6),
                     round(float(np.percentile(a, 97.5)), 6)],
            "p_rekey_better": round(float((a > 0).mean()), 4)}


def test_only_bootstrap(rows_by_cut, B: int, seed: int = SEED) -> dict:
    """Row-resample-only bootstrap on the fixed point-estimate frame. Reported ONLY to
    document how far a test-only bootstrap understates sd; it is not the gate."""
    out = {}
    for cut, rows in rows_by_cut.items():
        out[cut] = {}
        for lab in ("bust", "star"):
            acc = {k: [] for k in ("d_brier", "d_logloss")}
            if len(rows) < 30:
                out[cut][lab] = {k: {"n_draws": 0} for k in acc}
                continue
            rng = np.random.RandomState(seed + 7919)
            n = len(rows)
            for _ in range(B):
                idx = rng.randint(0, n, n)
                sub = [rows[j] for j in idx]
                if len(set(r[f"y_{lab}"] for r in sub)) < 2:
                    continue
                d = _deltas(sub, lab)
                acc["d_brier"].append(d["d_brier"])
                acc["d_logloss"].append(d["d_logloss"])
            out[cut][lab] = {k: _ci(v) for k, v in acc.items()}
    return out


def permutation_null(rows_by_cut, B: int, seed: int = SEED) -> dict:
    """Label permuted WITHIN fold, predictions held fixed: the distribution of the same
    paired delta under no label information at all."""
    out = {}
    for cut, rows in rows_by_cut.items():
        out[cut] = {}
        for lab in ("bust", "star"):
            if len(rows) < 30:
                out[cut][lab] = {"n_draws": 0}
                continue
            by_fold = {}
            for i, r in enumerate(rows):
                by_fold.setdefault(r["fold"], []).append(i)
            ys = [r[f"y_{lab}"] for r in rows]
            pa = [r[f"A_{lab}"] for r in rows]
            pb = [r[f"B_{lab}"] for r in rows]
            rng = random.Random(seed + 104729)
            db, dl = [], []
            for _ in range(B):
                yp = list(ys)
                for _f, idxs in by_fold.items():
                    vals = [ys[i] for i in idxs]
                    rng.shuffle(vals)
                    for i, v in zip(idxs, vals):
                        yp[i] = v
                if len(set(yp)) < 2:
                    continue
                db.append(brier(pa, yp) - brier(pb, yp))
                dl.append(logloss(pa, yp) - logloss(pb, yp))
            out[cut][lab] = {
                "d_brier": _null_band(db), "d_logloss": _null_band(dl)}
    return out


def _null_band(vals) -> dict:
    if not vals:
        return {"n_draws": 0}
    a = np.asarray(vals, float)
    return {"n_draws": int(a.size), "mean": round(float(a.mean()), 6),
            "band95": [round(float(np.percentile(a, 2.5)), 6),
                       round(float(np.percentile(a, 97.5)), 6)],
            "abs_p95": round(float(np.percentile(np.abs(a), 95)), 6)}


# ===========================================================================
# main
# ===========================================================================
def main(quick: bool = False) -> dict:
    b_boot = 100 if quick else B_BOOT
    b_perm = 200 if quick else B_PERM
    t_start = time.time()

    print("LANE-ODDS: p_bust grade-basis gate")
    print(f"  pre-registration: docs/efv-2026-07-30/ODDS_GRADE_BASIS_GATE.md")
    bundles = {s: load_side(s) for s in ("hit", "pit")}
    frames, bases = {}, {}
    for side, bundle in bundles.items():
        bases[side] = training_base_rates(bundle)
        rows = score_chain(bundle)
        attach_derived(rows, bases[side])
        frames[side] = rows
        print(f"  {side}: {len(rows)} resolved OOS rows, "
              f"bust base {np.mean([r['y_bust'] for r in rows]):.4f}, "
              f"stars {sum(r['y_star'] for r in rows)}")

    pooled = frames["hit"] + frames["pit"]
    cuts = {"hit": frames["hit"], "pit": frames["pit"], "pooled": pooled}
    served = {k: [r for r in v if r["has_track"]] for k, v in cuts.items()}
    all_cuts = dict(cuts)
    all_cuts.update({f"{k}_served": v for k, v in served.items()})

    report = {}
    for lab in ("bust", "star"):
        report[lab] = {c: cut_report(rows, lab) for c, rows in cuts.items()}
        report[lab + "_served_comparable"] = {c: cut_report(rows, lab)
                                              for c, rows in served.items()}

    print("  permutation null ...", flush=True)
    perm = permutation_null(all_cuts, b_perm)
    print("  test-only bootstrap (diagnostic) ...", flush=True)
    testonly = test_only_bootstrap(all_cuts, b_boot)
    print(f"  paired refit bootstrap B={b_boot} ...", flush=True)
    boot = paired_bootstrap(bundles, b_boot)

    # Five-bucket outcome census on the frame: the data a REFIT of the odds model on
    # the new grade would actually have to fit (costed in the gate doc, not built).
    bands = ((-1e9, 0.5, "bust"), (0.5, 1.5, "bench"), (1.5, 2.5, "regular"),
             (2.5, 4.0, "good"), (4.0, 1e9, "star"))
    census = {}
    for side, rows in frames.items():
        c = {b[2]: 0 for b in bands}
        for r in rows:
            a = r["target_resolved"] / float(TARGET_SEASONS)
            for lo, hi, nm in bands:
                if lo <= a < hi:
                    c[nm] += 1
                    break
        census[side] = {"n": len(rows), "counts": c,
                        "rates": {k: round(v / len(rows), 4) for k, v in c.items()}}

    grade_shift = {}
    for side, rows in frames.items():
        d = np.array([r["B_bust"] - r["A_bust"] for r in rows])
        grade_shift[side] = {
            "n": len(rows),
            "mean_d_p_bust_rekey_minus_pin": round(float(d.mean()), 6),
            "median": round(float(np.median(d)), 6),
            "max_abs": round(float(np.abs(d).max()), 6),
            "n_moving_gt_1pt": int((np.abs(d) > 0.01).sum()),
            "mean_grade_old": round(float(np.mean([r["grade_old"] for r in rows])), 3),
            "mean_grade_new": round(float(np.mean([r["grade_new"] for r in rows])), 3),
            "sd_grade_old": round(float(np.std([r["grade_old"] for r in rows])), 3),
            "sd_grade_new": round(float(np.std([r["grade_new"] for r in rows])), 3),
        }

    out = {
        "line": "LANE-ODDS 2026-07-30: p_bust / p_star grade-basis gate (re-key vs the pin).",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lab": "tools/odds_grade_basis_lab.py",
        "pre_registration": "docs/efv-2026-07-30/ODDS_GRADE_BASIS_GATE.md",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "registry_row": "xfv_odds_grade_basis",
        "changes_served_output": False,
        "frame": {
            "pool": "xfv_{hitter,pitcher}_matrix.json minus (kind=bust AND bust_recent), "
                    "prepped on target_censored (efv_score.run's own pool + target)",
            "test_restriction": "censored is False AND target_resolved numeric",
            "folds": list(CAL_YEARS),
            "why_not_2021_plus": "the 6-season window has not closed, so every resolved row "
                                 "in 2021-2024 is a bust by construction (base rate 1.000) "
                                 "and cannot test a probability",
            "n_hit": len(frames["hit"]), "n_pit": len(frames["pit"]),
        },
        "labels": {
            "bust": "target_resolved / 6 < 0.5 WAR per season (< 3.0 total). SHIPPED "
                    "definition, tools/_prem_odds.py:41; band from "
                    "value_framework_config.yaml:38 buckets.bust.band '<0.5'.",
            "star": "target_resolved / 6 >= 4.0 WAR per season (>= 24.0 total). Same "
                    "five-bucket ladder, value_framework_config.yaml:42 "
                    "buckets.star.band '4.0+'. NOT the star_odds model's definition.",
            "star_power_caveat": "declared UNPOWERED in the pre-registration: the frame "
                                 "holds 9 hitter stars and 2 pitcher stars.",
        },
        "arms": {
            "A_pin": "p_bucket_given_fv(realized_implied_fv(war, is_pit, age, pos)) - the incumbent",
            "B_rekey": "p_bucket_given_fv(outcome_implied_fv(war)) - the candidate",
            "C_zeroinfo": "constant at the fold's TRAINING base rate (climatology)",
            "D_twin_rankB": "B's ranking carrying A's marginal (rank-identical twin of B)",
            "E_twin_rankA": "A's ranking carrying B's marginal",
            "F_pin_platt": "A after a nested forward-chained Platt map",
            "G_rekey_platt": "B after a nested forward-chained Platt map",
        },
        "sign_convention": "d = metric(A_pin) - metric(B_rekey); POSITIVE d means the "
                           "RE-KEY is better.",
        "ship_criterion": "re-key ships only if B beats A on Brier AND logloss on BOTH "
                          "sides, and the paired refit bootstrap CI95 excludes zero on the "
                          "pooled cut for both metrics; plus the level-shift trap (1.7.3) "
                          "and the twin rule (1.7.4).",
        "caveats": [
            "The D/E twins are quantile-matched on the FULL per-side frame; on the "
            "served-comparable SUBSET the match is therefore approximate. The primary "
            "cuts are exact.",
            "F/G carry no Platt map on fold 2014 (no prior out-of-fold rows to fit one), "
            "where they fall back to A/B unchanged.",
            "Per-fold Platt maps make F and G globally non-monotone transforms of A and B, "
            "so their AUC is not preserved; the proper scores are the quantities of "
            "interest there.",
        ],
        "report": report,
        "outcome_bucket_census": census,
        "p_bust_shift": grade_shift,
        "controls": {
            "paired_refit_bootstrap": boot,
            "permutation_null": perm,
            "test_only_bootstrap_diagnostic": testonly,
        },
        "runtime_s": round(time.time() - t_start, 1),
    }
    (DATA / "odds_grade_basis_eval.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print(f"  wrote data/odds_grade_basis_eval.json ({out['runtime_s']}s)")
    return out


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
