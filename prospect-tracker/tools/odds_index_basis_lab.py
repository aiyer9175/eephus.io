# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE-ODDS-INDEX: is p_bucket_given_fv being read in the WRONG UNITS?

MEASUREMENT ONLY. Imports production code read-only, edits nothing, and writes exactly one
artifact (data/odds_index_basis_eval.json). Never imported by the site or by an exporter.

Pre-registration (on disk and committed BEFORE this file was written):
docs/efv-2026-07-30/ODDS_INDEX_MISMATCH_GATE.md. Gate standard: docs/EFV_GATE_STANDARD.md.

THE CONTEST
-----------
p_bucket_given_fv is a proportional-odds fit on five PUBLISHED CONSENSUS-FV cells per side
(value_framework_config.yaml:63-77; n = 678 hit / 437 pit) whose own recorded support is
data/value_framework_fitted.json bayes.data_fv_range = [45, 60]. efv_score.py:1188-1196
evaluates it at realized_implied_fv(model WAR) -- a different quantity on a different
scale (sd 2.70x / 2.26x the consensus marginal, mean 5-6 FV low).

This lab replays efv_score.run's own scoring chain out of fold, forward-chained over
decision years 2014-2020, and scores SEVEN forecasts on the identical rows:

    INC   the incumbent                          baseline 1
    CAL   incumbent + forward-chained Platt      baseline 2 (NOT re-litigated; rebuilt to score against)
    CONST flat within-cut base rate              baseline 3
    QNT   table read at the consensus-scale rank-quantile grade      THE CANDIDATE
    QWAR  same quantile construction on pure model WAR               candidate variant
    NAT   table read at its NATIVE index (consensus_fv_raw)          THE DECISIVE DIAGNOSTIC
    QNT_P QNT + forward-chained Platt                                the level-shift trap

Run:  python -m tools.odds_index_basis_lab            (from the repo root)
      python -m tools.odds_index_basis_lab --quick    (B=60, smoke check)
"""
from __future__ import annotations

import bisect
import json
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
from tools.odds_grade_basis_lab import (                        # noqa: E402
    brier, logloss, murphy, reliability_curve, calibration_ab, auc,
    irls_logit, _logit, platt_apply, bust_label, CAL_YEARS, BUST_IDX,
    _ci, _null_band, N_BINS, SEED,
)

B_BOOT = 1000
B_PERM = 1000

ARMS = ("INC", "CAL", "CONST", "QNT", "QWAR", "NAT", "QNT_P")
CANDIDATES = ("QNT", "QWAR", "NAT")
BASELINES = ("INC", "CAL", "CONST")
CUTS = ("hit", "pit", "pooled", "hit_served", "pit_served", "pooled_served")


# ===========================================================================
# frame construction
# ===========================================================================
def load_side(side: str) -> dict:
    is_pit = side == "pit"
    keys, _mono = em._feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    by_key = {r["player_key"]: r for r in pool}
    data = em._prep(pool, "target_censored", side)
    ctx = {}
    for r in data:
        src = by_key[r["player_key"]]
        dyear = src.get("debut_year") or 2020
        cf = src.get("consensus_fv_raw")
        ctx[r["player_key"]] = {
            "gm_age": es._grade_map_age(es._age_at(src.get("birth_date"), dyear), 0.0),
            "position": src.get("position"),
            "censored": src.get("censored"),
            "target_resolved": src.get("target_resolved"),
            "consensus_fv": None if cf is None else float(cf),
            "has_track": (isinstance(src.get("milb"), dict)
                          and float((src.get("milb") or {}).get("rates_missing", 1.0) or 0.0) == 0.0),
        }
    return {"side": side, "is_pit": is_pit, "keys": keys, "data": data, "ctx": ctx,
            "lam": es.blend_lambda(side)}


_PB_MEMO: dict = {}


def _p_bust(fv, is_pit: bool):
    """p_bucket_given_fv(fv)[bust], memoized on a 2dp grade grid. Pure speed device for the
    1000-draw bootstrap; the curve is smooth and production is unaffected."""
    if fv is None:
        return None
    k = (round(float(fv), 2), is_pit)
    v = _PB_MEMO.get(k)
    if v is None:
        pb = vf.p_bucket_given_fv(float(fv), is_pit)
        v = None if not pb else float(pb[BUST_IDX])
        _PB_MEMO[k] = v
    return v


_G_MEMO: dict = {}


def _realized_grade(war, is_pit, gm_age, pos):
    k = (round(float(war), 3), is_pit, None if gm_age is None else round(float(gm_age), 1), pos)
    v = _G_MEMO.get(k)
    if v is None:
        v = vf.realized_implied_fv(war, is_pit, age=gm_age, position=pos,
                                   exposure_seasons=TARGET_SEASONS)
        _G_MEMO[k] = v
    return v


def _quantile_grade(x: float, xs_sorted: list, target_sorted: list):
    """The xfv_grade_display construction, read out of fold: the value's within-pool rank
    quantile carried onto the pool's consensus-FV distribution, interpolated. `xs_sorted` is
    the TRAINING pool's ordering statistic, `target_sorted` its consensus-FV values."""
    n, m = len(xs_sorted), len(target_sorted)
    if n < 2 or m < 1:
        return None
    p = bisect.bisect_left(xs_sorted, x) / (n - 1)
    p = min(1.0, max(0.0, p))
    pos = p * (m - 1)
    lo = int(pos)
    hi = min(m - 1, lo + 1)
    frac = pos - lo
    return target_sorted[lo] * (1 - frac) + target_sorted[hi] * frac


def score_chain(bundle: dict, data=None) -> list[dict]:
    """Forward-chained OOS replication of efv_score.run's chain, emitting every arm's
    p_bust for each resolved test row."""
    keys, is_pit, ctx, lam = bundle["keys"], bundle["is_pit"], bundle["ctx"], bundle["lam"]
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

        # The consensus-scale quantile map, built on the TRAINING rows only (1.2).
        tr_cons, tr_rank, tr_war = [], [], []
        for r in tr:
            c = ctx[r["player_key"]]
            if c["consensus_fv"] is None:
                continue
            w = max(-2.0, a + b * em._predict(ridge, r["feats"]))
            cw = max(0.0, em._pred_ols(ols, c["consensus_fv"]))
            tr_cons.append(c["consensus_fv"])
            tr_rank.append((1 - lam) * cw + lam * w)
            tr_war.append(w)
        tr_cons.sort(); tr_rank.sort(); tr_war.sort()
        if len(tr_cons) < 30:
            continue

        for r in te:
            c = ctx[r["player_key"]]
            if c["censored"] is not False or not isinstance(c["target_resolved"], (int, float)):
                continue
            if c["consensus_fv"] is None:
                continue
            war = max(-2.0, a + b * em._predict(ridge, r["feats"]))
            cw = max(0.0, em._pred_ols(ols, c["consensus_fv"]))
            rank_war = (1 - lam) * cw + lam * war

            g_inc = _realized_grade(war, is_pit, c["gm_age"], c["position"])
            g_qnt = _quantile_grade(rank_war, tr_rank, tr_cons)
            g_qwar = _quantile_grade(war, tr_war, tr_cons)
            g_nat = c["consensus_fv"]
            p_inc = _p_bust(g_inc, is_pit)
            p_qnt = _p_bust(g_qnt, is_pit)
            p_qwar = _p_bust(g_qwar, is_pit)
            p_nat = _p_bust(g_nat, is_pit)
            if None in (p_inc, p_qnt, p_qwar, p_nat):
                continue
            out.append({
                "player_key": r["player_key"], "fold": yr, "has_track": c["has_track"],
                "xfv_war": float(war), "rank_war": float(rank_war),
                "g_INC": float(g_inc), "g_QNT": float(g_qnt),
                "g_QWAR": float(g_qwar), "g_NAT": float(g_nat),
                "INC": p_inc, "QNT": p_qnt, "QWAR": p_qwar, "NAT": p_nat,
                "y": bust_label(float(c["target_resolved"])),
                "target_resolved": float(c["target_resolved"]),
            })
    return out


def attach_platt(rows: list[dict]) -> None:
    """Nested forward chain: the Platt map served on fold Y is fit ONLY on rows scored out of
    fold in folds < Y. Fold CAL_YEARS[0] carries none and falls back to the raw arm."""
    for src, dst in (("INC", "CAL"), ("QNT", "QNT_P")):
        for yr in CAL_YEARS:
            hist = [r for r in rows if r["fold"] < yr]
            cur = [r for r in rows if r["fold"] == yr]
            if not cur:
                continue
            if len(hist) < 25:
                for r in cur:
                    r[dst] = r[src]
                continue
            y = np.array([r["y"] for r in hist], float)
            ab = irls_logit(_logit([r[src] for r in hist]), y)
            for r, v in zip(cur, platt_apply([r[src] for r in cur], ab)):
                r[dst] = float(v)


def attach_const(rows: list[dict], fallback: dict) -> None:
    """Arm CONST, fitted WITHIN the cut (gate doc 1.3): the base rate of the SAME cut's
    prior folds. Fold CAL_YEARS[0] falls back to the full-frame training base rate."""
    for yr in CAL_YEARS:
        hist = [r for r in rows if r["fold"] < yr]
        cur = [r for r in rows if r["fold"] == yr]
        if not cur:
            continue
        v = (float(np.mean([r["y"] for r in hist])) if len(hist) >= 25
             else float(fallback.get(yr, 0.5)))
        for r in cur:
            r["CONST"] = v


def training_base_rates(bundle: dict, data=None) -> dict:
    """Full-frame training base rate per fold (the CONST_all fallback)."""
    ctx = bundle["ctx"]
    data = bundle["data"] if data is None else data
    out = {}
    for yr in CAL_YEARS:
        lab = [bust_label(ctx[r["player_key"]]["target_resolved"])
               for r in data if r["decision_year"] < yr
               and ctx[r["player_key"]]["censored"] is False
               and isinstance(ctx[r["player_key"]]["target_resolved"], (int, float))]
        out[yr] = (sum(lab) / len(lab)) if lab else 0.5
    return out


def build_cuts(per_side: dict) -> dict:
    pooled = per_side.get("hit", []) + per_side.get("pit", [])
    cuts = {"hit": per_side.get("hit", []), "pit": per_side.get("pit", []), "pooled": pooled}
    for k in ("hit", "pit", "pooled"):
        cuts[f"{k}_served"] = [r for r in cuts[k] if r["has_track"]]
    return cuts


# ===========================================================================
# metrics + deltas
# ===========================================================================
def arm_report(rows: list[dict], arm: str) -> dict:
    p = np.array([r[arm] for r in rows], float)
    y = np.array([r["y"] for r in rows], float)
    m = murphy(p, y)
    a, b = calibration_ab(p, y)
    au = auc(p, y)
    return {
        "n": int(p.size), "brier": round(brier(p, y), 6), "logloss": round(logloss(p, y), 6),
        "ece": round(m["ece"], 6), "reliability": round(m["reliability"], 6),
        "resolution": round(m["resolution"], 6), "uncertainty": round(m["uncertainty"], 6),
        "cal_slope": (None if b is None else round(b, 4)),
        "cal_intercept": (None if a is None else round(a, 4)),
        "cal_in_the_large": round(float(p.mean() - y.mean()), 6),
        "mean_p": round(float(p.mean()), 6), "base_rate": round(float(y.mean()), 6),
        "auc": (None if au is None else round(au, 4)),
    }


def grade_census(rows: list[dict]) -> dict:
    out = {}
    for g in ("g_INC", "g_QNT", "g_QWAR", "g_NAT"):
        a = np.array([r[g] for r in rows], float)
        out[g] = {"mean": round(float(a.mean()), 3), "sd": round(float(a.std(ddof=1)), 3),
                  "p05": round(float(np.percentile(a, 5)), 2),
                  "p50": round(float(np.percentile(a, 50)), 2),
                  "p95": round(float(np.percentile(a, 95)), 2),
                  "share_below_fit_support_45": round(float((a < 45).mean()), 4)}
    return out


def cut_report(rows: list[dict]) -> dict:
    if not rows:
        return {}
    out = {"n": len(rows), "base_rate": round(float(np.mean([r["y"] for r in rows])), 4),
           "arms": {a: arm_report(rows, a) for a in ARMS},
           "grades": grade_census(rows),
           "reliability_curve": {a: reliability_curve([r[a] for r in rows],
                                                      [r["y"] for r in rows], N_BINS)
                                 for a in ("INC", "QNT", "NAT", "CONST")}}
    per_fold = {}
    for yr in CAL_YEARS:
        sub = [r for r in rows if r["fold"] == yr]
        if len(sub) < 10:
            continue
        y = [r["y"] for r in sub]
        f = {"n": len(sub), "base_rate": round(float(np.mean(y)), 4)}
        for a in ARMS:
            f[f"brier_{a}"] = round(brier([r[a] for r in sub], y), 6)
            f[f"logloss_{a}"] = round(logloss([r[a] for r in sub], y), 6)
        for cand in CANDIDATES:
            for base in BASELINES:
                f[f"dBrier_{cand}_vs_{base}"] = round(f[f"brier_{base}"] - f[f"brier_{cand}"], 6)
                f[f"dLL_{cand}_vs_{base}"] = round(f[f"logloss_{base}"] - f[f"logloss_{cand}"], 6)
        per_fold[str(yr)] = f
    out["per_fold"] = per_fold
    return out


def deltas(rows: list[dict]) -> dict:
    """d = metric(baseline) - metric(candidate). POSITIVE means the CANDIDATE is better."""
    y = [r["y"] for r in rows]
    mb = {a: brier([r[a] for r in rows], y) for a in ARMS}
    ml = {a: logloss([r[a] for r in rows], y) for a in ARMS}
    me = {a: murphy([r[a] for r in rows], y)["ece"] for a in ARMS}
    out = {}
    for cand in CANDIDATES:
        for base in BASELINES:
            out[f"brier_{cand}_vs_{base}"] = mb[base] - mb[cand]
            out[f"logloss_{cand}_vs_{base}"] = ml[base] - ml[cand]
            out[f"ece_{cand}_vs_{base}"] = me[base] - me[cand]
    # the level-shift trap: both arms recalibrated out of fold
    out["brier_QNTP_vs_CAL"] = mb["CAL"] - mb["QNT_P"]
    out["logloss_QNTP_vs_CAL"] = ml["CAL"] - ml["QNT_P"]
    return out


DELTA_KEYS = tuple(
    [f"{m}_{c}_vs_{b}" for c in CANDIDATES for b in BASELINES
     for m in ("brier", "logloss", "ece")] + ["brier_QNTP_vs_CAL", "logloss_QNTP_vs_CAL"])


# ===========================================================================
# controls
# ===========================================================================
def _score_all(bundles, resampled=None, bases=None):
    per_side = {}
    for side, bundle in bundles.items():
        rows = score_chain(bundle, None if resampled is None else resampled[side])
        if rows:
            attach_platt(rows)
        per_side[side] = rows
    cuts = build_cuts(per_side)
    for name, rows in cuts.items():
        if not rows:
            continue
        side = "pit" if name.startswith("pit") else "hit"
        attach_const(rows, (bases or {}).get(side, {}))
    return cuts


def paired_bootstrap(bundles, B: int, seed: int = SEED, verbose: bool = True) -> dict:
    """Player-clustered paired bootstrap resampling TRAIN AND TEST with a full refit of the
    ridge, the linear calibration, the consensus OLS, the consensus-scale quantile map and
    the forward-chained Platt maps on every draw."""
    draws = {c: {k: [] for k in DELTA_KEYS} for c in CUTS}
    t0 = time.time()
    for i in range(B):
        rng = np.random.RandomState(seed + i)
        resampled, bases = {}, {}
        for side, bundle in bundles.items():
            data = bundle["data"]
            idx = rng.randint(0, len(data), len(data))
            resampled[side] = [data[j] for j in idx]
            bases[side] = training_base_rates(bundle, resampled[side])
        cuts = _score_all(bundles, resampled, bases)
        for cut in CUTS:
            rows = cuts.get(cut) or []
            if len(rows) < 30 or len(set(r["y"] for r in rows)) < 2:
                continue
            for k, v in deltas(rows).items():
                if v == v:
                    draws[cut][k].append(v)
        if verbose and (i + 1) % 25 == 0:
            el = time.time() - t0
            print(f"    bootstrap {i+1}/{B}  {el:.0f}s elapsed, "
                  f"~{el/(i+1)*(B-i-1):.0f}s left", flush=True)
    return {c: {k: _ci(v) for k, v in d.items()} for c, d in draws.items()}


def permutation_null(cuts: dict, B: int, seed: int = SEED) -> dict:
    """Labels permuted WITHIN fold, all forecasts held fixed: the reference distribution of
    each paired delta under no label information at all."""
    out = {}
    for cut, rows in cuts.items():
        if len(rows) < 30:
            out[cut] = {"n_draws": 0}
            continue
        by_fold = {}
        for i, r in enumerate(rows):
            by_fold.setdefault(r["fold"], []).append(i)
        ys = [r["y"] for r in rows]
        P = {a: [r[a] for r in rows] for a in ARMS}
        rng = random.Random(seed + 104729)
        acc = {k: [] for k in DELTA_KEYS}
        for _ in range(B):
            yp = list(ys)
            for _f, idxs in by_fold.items():
                vals = [ys[i] for i in idxs]
                rng.shuffle(vals)
                for i, v in zip(idxs, vals):
                    yp[i] = v
            if len(set(yp)) < 2:
                continue
            mb = {a: brier(P[a], yp) for a in ARMS}
            ml = {a: logloss(P[a], yp) for a in ARMS}
            me = {a: murphy(np.asarray(P[a], float), np.asarray(yp, float))["ece"] for a in ARMS}
            for cand in CANDIDATES:
                for base in BASELINES:
                    acc[f"brier_{cand}_vs_{base}"].append(mb[base] - mb[cand])
                    acc[f"logloss_{cand}_vs_{base}"].append(ml[base] - ml[cand])
                    acc[f"ece_{cand}_vs_{base}"].append(me[base] - me[cand])
            acc["brier_QNTP_vs_CAL"].append(mb["CAL"] - mb["QNT_P"])
            acc["logloss_QNTP_vs_CAL"].append(ml["CAL"] - ml["QNT_P"])
        out[cut] = {k: _null_band(v) for k, v in acc.items()}
    return out


# ===========================================================================
# main
# ===========================================================================
def main(quick: bool = False) -> dict:
    b_boot = 60 if quick else B_BOOT
    b_perm = 200 if quick else B_PERM
    t0 = time.time()

    print("LANE-ODDS-INDEX: is p_bucket_given_fv read in the wrong units?")
    print("  pre-registration: docs/efv-2026-07-30/ODDS_INDEX_MISMATCH_GATE.md")
    bundles = {s: load_side(s) for s in ("hit", "pit")}
    bases = {s: training_base_rates(b) for s, b in bundles.items()}
    cuts = _score_all(bundles, None, bases)
    for s in ("hit", "pit"):
        rows = cuts[s]
        print(f"  {s}: {len(rows)} resolved OOS rows, bust base "
              f"{np.mean([r['y'] for r in rows]):.4f}")

    report = {c: cut_report(rows) for c, rows in cuts.items()}
    point = {c: {k: round(v, 6) for k, v in deltas(rows).items()}
             for c, rows in cuts.items() if rows}

    print("  permutation null ...", flush=True)
    perm = permutation_null(cuts, b_perm)
    print(f"  paired refit bootstrap B={b_boot} ...", flush=True)
    boot = paired_bootstrap(bundles, b_boot)

    fit = json.loads((DATA / "value_framework_fitted.json").read_text(encoding="utf-8"))
    out = {
        "line": "LANE-ODDS-INDEX 2026-07-30: the p_bucket_given_fv index mismatch, measured.",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lab": "tools/odds_index_basis_lab.py",
        "pre_registration": "docs/efv-2026-07-30/ODDS_INDEX_MISMATCH_GATE.md",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "registry_row": "xfv_odds_index_basis",
        "changes_served_output": False,
        "table_identity": {
            "source": "value_framework_config.yaml p_bucket_given_fv_{hitter,pitcher}: five "
                      "published CONSENSUS-FV cells per side (45, 45+ axis 47.5, 50, 55, 60)",
            "fit_method": fit.get("method"),
            "training_n": fit.get("training_n"),
            "fitted_support_fv": fit.get("bayes", {}).get("data_fv_range"),
            "note": "every served probability outside that support is an extrapolation",
        },
        "arms": {
            "INC": "p_bucket_given_fv(realized_implied_fv(war, is_pit, age, pos))[bust] - the incumbent",
            "CAL": "INC through a nested forward-chained Platt map (baseline, not re-litigated)",
            "CONST": "flat constant at the WITHIN-CUT base rate of prior folds",
            "QNT": "p_bucket_given_fv(consensus-scale rank-quantile grade)[bust] - THE CANDIDATE",
            "QWAR": "same quantile construction on pure model WAR instead of rank_war",
            "NAT": "p_bucket_given_fv(consensus_fv_raw)[bust] - the table at its NATIVE index",
            "QNT_P": "QNT through the same nested forward-chained Platt map",
        },
        "sign_convention": "d = metric(baseline) - metric(candidate); POSITIVE means the "
                           "CANDIDATE is better.",
        "ship_criterion": "QNT ships only if it beats CONST on Brier AND log loss, on pooled "
                          "AND pooled_served, with the paired refit bootstrap CI95 excluding "
                          "zero on all four; plus the level-shift trap and the permutation rule.",
        "frame": {"folds": list(CAL_YEARS),
                  "test_restriction": "censored is False, target_resolved numeric, "
                                      "consensus_fv_raw present",
                  "n": {c: len(r) for c, r in cuts.items()}},
        "report": report,
        "point_deltas": point,
        "controls": {"paired_refit_bootstrap": boot, "permutation_null": perm},
        "runtime_s": round(time.time() - t0, 1),
    }
    (DATA / "odds_index_basis_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"  wrote data/odds_index_basis_eval.json ({out['runtime_s']}s)")
    return out


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
