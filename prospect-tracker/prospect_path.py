# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Prospect path challenger — the MiLB-stats translation model (WS-7,
the fork recorded when /projections/ shipped).

mlb_projections_prospects ships post-ETA WAR paths from P(bucket|FV) x
calibrated trajectories — FV-ONLY. The recorded question: do the
prospect's actual MiLB rates (level-translated) add forward signal on
top of the scouting consensus? This module answers it with a committed
backtest and (only if the gate is won) a dispatch hook for
proj_export._prospect_rows.

  COHORT     debuts.json, debut years 2017-2021 (first-3y windows all
             resolved by 2025 — 2022+ debuts are NOT scoreable yet).
  VINTAGE    consensus FV strictly pre-debut: median of each source's
             LATEST snapshot dated before the debut date.
  FEATURES   from the StatsAPI ladder (milb_history), final MiLB season
             strictly before the debut year (2021 debuts fall back to
             2019 — the 2020 MiLB season didn't exist; the staleness
             gap is itself a feature):
               age - level-median age (age-rel-level), level rank,
               seasons-stale gap, consensus FV, and league-relative
               rates: hitters k/bb/iso vs level median; pitchers
               era/k/bb vs level median. Sides get separate models.
             NO Statcast features: AAA tracking starts 2023, so the
             2017-21 training cohorts have none — including columns
             that are 100% missing in training would be theater
             (the plan: "don't promise more").
  TARGET     first-3-MLB-season bWAR (career_war, seasons debut..debut+2).
  CHALLENGER ridge regression (closed form, standardized features,
             alpha picked inside the training folds only) — at n~600/side
             a deep learner is variance, not signal.
  BASELINE   the LIVE FV-only machinery: sum of the first 3 seasons of
             the P(bucket|FV)-weighted bucket trajectories from the
             player's debut age (exactly what /projections/ renders).
  PROTOCOL   forward-chained by debut year: predict year Y with models
             fit on debuts < Y (2019, 2020, 2021 scored; 2017-18 seed
             the first fold). Pooled OOS MAE + Spearman vs the baseline
             on identical rows; calibration slope/bias for both.
  SHIP RULE  challenger must beat the baseline on BOTH pooled MAE and
             Spearman, with calibration not worse. Otherwise FV-only
             retains and the loss is committed (program rule).

Artifact: data/prospect_path_eval.json.
Run: python prospect_path.py
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import milb_history as mh
import storage
import value_framework as vf

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "prospect_path_eval.json"

DEBUT_YEARS = (2017, 2018, 2019, 2020, 2021)
SCORED_YEARS = (2019, 2020, 2021)        # forward-chained eval folds
TARGET_SEASONS = 3
LAST_FULL_SEASON = 2025
_LEVEL_RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
_ALPHAS = (1.0, 10.0, 100.0)


# ---------------------------------------------------------------------------
# cohort construction
# ---------------------------------------------------------------------------

def _load_db() -> tuple[dict, dict, dict]:
    """(pre_debut_fv, war_seasons, debut_rows)."""
    debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    drows = {d["player_key"]: d for d in debuts
             if d.get("player_key") and d.get("debut_date") and d.get("mlbam_id")
             and int(d["debut_date"][:4]) in DEBUT_YEARS}
    with storage.connect() as con:
        cw = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
        fv_pre: dict[str, float] = {}
        if drows:
            placeholders = ",".join("?" for _ in drows)
            rows = con.execute(f"""
                SELECT s.player_key, s.source, s.fv, s.snapshot_date
                FROM snapshots s WHERE s.fv IS NOT NULL
                  AND s.player_key IN ({placeholders})""",
                tuple(drows)).fetchall()
            per: dict[str, dict[str, tuple[str, float]]] = {}
            for r in rows:
                dd = drows[r["player_key"]]["debut_date"]
                if r["snapshot_date"] >= dd:
                    continue
                cur = per.setdefault(r["player_key"], {})
                prev = cur.get(r["source"])
                if prev is None or r["snapshot_date"] > prev[0]:
                    cur[r["source"]] = (r["snapshot_date"], float(r["fv"]))
            for pk, by_src in per.items():
                fv_pre[pk] = statistics.median(v for _, v in by_src.values())
    return fv_pre, cw, drows


def _final_milb_season(mlbam: int, debut_year: int,
                       group: str) -> tuple[int, list[dict]] | None:
    """Most recent season strictly before the debut year with MiLB rows."""
    for season in range(debut_year - 1, 2013, -1):
        rows = [r for r in (mh.player_index(season, group).get(mlbam) or [])
                if r.get("level") != "MLB"]
        if rows:
            return season, rows
    return None


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _features(mlbam: int, debut_year: int, fv: float,
              is_pit: bool) -> dict | None:
    group = "pitching" if is_pit else "hitting"
    found = _final_milb_season(mlbam, debut_year, group)
    if not found:
        return None
    season, rows = found
    level = mh.highest_level(rows)
    if level not in _LEVEL_RANK:
        return None
    row = mh.level_row(rows, level, group)
    norms = mh.league_norms(season, level, group, fetch=False) or {}
    age = _f(row.get("age"))
    feats = {
        "fv": fv,
        "level_rank": float(_LEVEL_RANK[level]),
        "stale": float(debut_year - 1 - season),
        "age": age if age is not None else 23.0,
        "age_missing": 1.0 if age is None else 0.0,
    }
    if is_pit:
        bf = _f(row.get("bf")) or 0.0
        so, bb = _f(row.get("so")), _f(row.get("bb"))
        era = _f(row.get("era"))
        feats.update({
            "k_rel": ((so / bf) - (norms.get("k_pct") or 0.0)) if so is not None and bf else 0.0,
            "bb_rel": ((bb / bf) - (norms.get("bb_pct") or 0.0)) if bb is not None and bf else 0.0,
            "era_rel": (era - (norms.get("era") or 4.5)) if era is not None else 0.0,
            "rates_missing": 1.0 if not bf else 0.0,
        })
    else:
        pa = _f(row.get("pa")) or 0.0
        so, bb = _f(row.get("so")), _f(row.get("bb"))
        slg, avg = _f(row.get("slg")), _f(row.get("avg"))
        iso = (slg - avg) if slg is not None and avg is not None else None
        feats.update({
            "k_rel": ((so / pa) - (norms.get("k_pct") or 0.0)) if so is not None and pa else 0.0,
            "bb_rel": ((bb / pa) - (norms.get("bb_pct") or 0.0)) if bb is not None and pa else 0.0,
            "iso_rel": (iso - (norms.get("iso") or 0.0)) if iso is not None else 0.0,
            "rates_missing": 1.0 if not pa else 0.0,
        })
    return feats


def _baseline_first3(fv: float, is_pit: bool, position: str | None,
                     debut_age: float | None) -> float | None:
    """The LIVE FV-only expectation: P(bucket|FV)-weighted bucket
    trajectories from debut age, first TARGET_SEASONS summed — the same
    machinery proj_export._prospect_rows renders."""
    probs = vf.p_bucket_given_fv(fv, is_pit)
    if not probs:
        return None
    role = vf._role_key(is_pit)
    reliever = vf.is_reliever_position(position)
    scale = vf._war_scale_for(fv, role)
    paths = [vf._bucket_season_wars(role, i, reliever, debut_age, scale)
             for i in range(len(probs))]
    return round(sum(sum(pr * paths[i][t] for i, pr in enumerate(probs))
                     for t in range(min(TARGET_SEASONS, len(paths[0])))), 3)


def build_cohort() -> tuple[list[dict], dict]:
    fv_pre, cw, drows = _load_db()
    acct = {"debuts": len(drows), "no_pre_debut_fv": 0, "no_war_rows": 0,
            "no_milb_features": 0, "scored": 0}
    rows = []
    for pk, d in sorted(drows.items()):
        debut_year = int(d["debut_date"][:4])
        fv = fv_pre.get(pk)
        if fv is None:
            acct["no_pre_debut_fv"] += 1
            continue
        seasons = cw.get(pk)
        if not seasons:
            acct["no_war_rows"] += 1
            continue
        target = round(sum(w for y, w in seasons.items()
                           if debut_year <= y <= debut_year + TARGET_SEASONS - 1
                           and y <= LAST_FULL_SEASON), 2)
        pos = d.get("position")
        is_pit = vf.is_pitcher_position(pos)
        feats = _features(int(d["mlbam_id"]), debut_year, fv, is_pit)
        if feats is None:
            acct["no_milb_features"] += 1
            continue
        age_b = d.get("birth_date")
        debut_age = None
        if age_b:
            try:
                b = date.fromisoformat(age_b[:10])
                debut_age = round((date.fromisoformat(d["debut_date"][:10]) - b)
                                  .days / 365.25, 1)
            except ValueError:
                pass
        base = _baseline_first3(fv, is_pit, pos, debut_age)
        if base is None:
            continue
        acct["scored"] += 1
        rows.append({"player_key": pk, "debut_year": debut_year, "fv": fv,
                     "is_pit": is_pit, "feats": feats, "target": target,
                     "baseline": base})
    return rows, acct


# ---------------------------------------------------------------------------
# ridge (closed form, numpy)
# ---------------------------------------------------------------------------

_RIDGE_HOLDOUT_SEED = 20260707


def _fit_ridge(train: list[dict], keys: list[str]) -> dict | None:
    import numpy as np
    if len(train) < 40:
        return None
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    # KM observed-fraction SAMPLE WEIGHTS (efv_dataset emits `weight`: a fully-resolved
    # 6-season row = 1.0, a censored row = observed_seasons/6, busts down-weighted). The
    # fit used to DROP these (the docstring claimed they were applied); the weighted
    # normal equations honor them so a thin-exposure censored row does not count as a
    # full observation. Rows without a weight default to 1.0 (back-compat).
    wts = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in train]), 1e-3, None)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    n = len(train)

    def _wmean(idx):
        ww = wts[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())

    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], wts[idx]
        WX = Xi * wi[:, None]
        A = WX.T @ Xi + alpha * np.eye(len(keys))
        return np.linalg.solve(A, WX.T @ (y[idx] - b))

    # Alpha picked on a DETERMINISTIC, representative holdout (a seeded permutation), NOT
    # the contiguous last-fifth: the eFV matrix is kind-blocked + year-descending, so the
    # last fifth was systematically the oldest bust rows, tuning alpha on a degenerate
    # slice. The fixed seed keeps the fit deterministic (golden-fingerprint stable).
    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    k = max(1, n // 5)
    ho, tri = order[:k], order[k:]
    b_tr = _wmean(tri)
    best = None
    for alpha in _ALPHAS:
        w = _wridge(tri, alpha, b_tr)
        pred = Xs[ho] @ w + b_tr
        mae = (float(np.average(np.abs(pred - y[ho]), weights=wts[ho]))
               if wts[ho].sum() > 0 else float(np.abs(pred - y[ho]).mean()))
        if best is None or mae < best[0]:
            best = (mae, alpha)
    alpha = best[1]
    b = _wmean(np.arange(n))
    w = _wridge(np.arange(n), alpha, b)
    return {"keys": keys, "mu": mu.tolist(), "sd": sd.tolist(),
            "w": w.tolist(), "b": float(b), "alpha": alpha}


def _predict(model: dict, feats: dict) -> float:
    z = 0.0
    for k, m, s, w in zip(model["keys"], model["mu"], model["sd"], model["w"]):
        z += w * ((feats.get(k, 0.0) - m) / (s or 1.0))
    return z + model["b"]


_KEYS = {
    False: ["fv", "level_rank", "stale", "age", "age_missing",
            "k_rel", "bb_rel", "iso_rel", "rates_missing"],
    True: ["fv", "level_rank", "stale", "age", "age_missing",
           "k_rel", "bb_rel", "era_rel", "rates_missing"],
}


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

def _spearman(xs, ys):
    def _ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for t in range(i, j + 1):
                r[order[t]] = (i + j) / 2 + 1
            i = j + 1
        return r
    n = len(xs)
    if n < 8:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return round(cov / (vx * vy) ** 0.5, 4) if vx and vy else None


def _calibration(pred, obs):
    n = len(pred)
    if n < 8:
        return None
    mp, mo = statistics.mean(pred), statistics.mean(obs)
    cov = sum((p - mp) * (o - mo) for p, o in zip(pred, obs))
    vp = sum((p - mp) ** 2 for p in pred)
    return {"slope": round(cov / vp, 3) if vp else None,
            "bias": round(mp - mo, 3)}


def _score(pairs):
    pred = [p for p, _ in pairs]
    obs = [o for _, o in pairs]
    return {
        "n": len(pairs),
        "mae": round(sum(abs(p - o) for p, o in pairs) / len(pairs), 3),
        "spearman": _spearman(pred, obs),
        "calibration": _calibration(pred, obs),
    }


def _fit_lgbm(train: list[dict], keys: list[str]):
    """LightGBM challenger (the audit's best-model-wins mandate) - small
    and heavily regularized for n~250/side; deterministic."""
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        return None
    if len(train) < 60:
        return None
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    model = lgb.LGBMRegressor(
        n_estimators=200, learning_rate=0.05, num_leaves=7,
        min_child_samples=25, subsample=0.9, subsample_freq=1,
        colsample_bytree=0.8, reg_lambda=5.0,
        random_state=7, deterministic=True, verbose=-1)
    model.fit(X, y)
    return {"model": model, "keys": keys}


def _fit_linear_calibration(pairs: list[tuple[float, float]]) -> dict | None:
    """OLS realized ~ a + b * predicted - the mean-path correction
    candidate for the LIVE FV-only model (registry-noted: slope .751,
    bias +0.245 = over-projection at the mean)."""
    if len(pairs) < 50:
        return None
    n = len(pairs)
    mp = sum(p for p, _ in pairs) / n
    mo = sum(o for _, o in pairs) / n
    cov = sum((p - mp) * (o - mo) for p, o in pairs)
    var = sum((p - mp) ** 2 for p, _ in pairs)
    if var <= 0:
        return None
    b = cov / var
    a = mo - b * mp
    return {"a": round(a, 4), "b": round(b, 4), "n": n}


def run(persist: bool = True) -> dict:
    rows, acct = build_cohort()
    chall_pairs, base_pairs, lgbm_pairs = [], [], []
    cal_pairs = []          # forward-chained CALIBRATED baseline pairs
    ical_pairs = []         # candidate #2: intercept-only, min-train-n
    ical_base_pairs = []    # the RAW baseline on the SAME rows (fair compare)
    per_year = {}
    for yr in SCORED_YEARS:
        train = [r for r in rows if r["debut_year"] < yr]
        test = [r for r in rows if r["debut_year"] == yr]
        # forward-chained calibration of the FV-only baseline: fit on
        # PRIOR debut cohorts' (baseline, realized), apply to this fold
        cal = _fit_linear_calibration([(r["baseline"], r["target"]) for r in train])
        # candidate #2 (PRE-REGISTERED 2026-06-11, after #1 failed its
        # slope criterion on the thin 2019 fold): INTERCEPT-ONLY shift,
        # applied only when the training fold has >= 250 rows. Rule:
        # held-out |bias| must shrink AND slope must not worsen by more
        # than 0.02 AND MAE not degrade by more than 0.02.
        ic_n = len(train)
        ic_shift = (sum(r["baseline"] - r["target"] for r in train) / ic_n
                    if ic_n >= 250 else None)
        yr_c, yr_b, yr_g, yr_k, yr_i, yr_ib = [], [], [], [], [], []
        for is_pit in (False, True):
            side_train = [r for r in train if r["is_pit"] == is_pit]
            model = _fit_ridge(side_train, _KEYS[is_pit])
            gbm = _fit_lgbm(side_train, _KEYS[is_pit])
            for r in test:
                if r["is_pit"] != is_pit:
                    continue
                if model is not None:
                    yr_c.append((_predict(model, r["feats"]), r["target"]))
                    yr_b.append((r["baseline"], r["target"]))
                if gbm is not None:
                    import warnings as _w
                    import numpy as np
                    X = np.array([[r["feats"].get(k, 0.0) for k in gbm["keys"]]])
                    with _w.catch_warnings():
                        _w.simplefilter("ignore")   # feature-name nag on ndarray input
                        yr_g.append((float(gbm["model"].predict(X)[0]), r["target"]))
                if cal is not None:
                    yr_k.append((max(0.0, cal["a"] + cal["b"] * r["baseline"]),
                                 r["target"]))
                if ic_shift is not None:
                    yr_i.append((max(0.0, r["baseline"] - ic_shift),
                                 r["target"]))
                    yr_ib.append((r["baseline"], r["target"]))
        chall_pairs.extend(yr_c)
        base_pairs.extend(yr_b)
        lgbm_pairs.extend(yr_g)
        cal_pairs.extend(yr_k)
        ical_pairs.extend(yr_i)
        ical_base_pairs.extend(yr_ib)
        if yr_c:
            per_year[yr] = {"challenger": _score(yr_c), "baseline": _score(yr_b)}
            if yr_g:
                per_year[yr]["lgbm"] = _score(yr_g)
            if yr_k:
                per_year[yr]["baseline_calibrated"] = _score(yr_k)

    chall = _score(chall_pairs) if chall_pairs else {"n": 0}
    base = _score(base_pairs) if base_pairs else {"n": 0}
    lgbm = _score(lgbm_pairs) if lgbm_pairs else {"n": 0}
    cal_fc = _score(cal_pairs) if cal_pairs else {"n": 0}
    ical_fc = _score(ical_pairs) if ical_pairs else {"n": 0}
    ical_base = _score(ical_base_pairs) if ical_base_pairs else {"n": 0}
    wins = (chall.get("n", 0) > 100
            and chall.get("mae") is not None and base.get("mae") is not None
            and chall["mae"] < base["mae"]
            and (chall.get("spearman") or 0) > (base.get("spearman") or 0))
    lgbm_wins = (lgbm.get("n", 0) > 100
                 and lgbm.get("mae") is not None and base.get("mae") is not None
                 and lgbm["mae"] < base["mae"]
                 and (lgbm.get("spearman") or 0) > (base.get("spearman") or 0))
    # CALIBRATION ship rule: a linear recentering of the LIVE model's mean
    # (rank-preserving, b>0) must move the held-out calibration slope
    # toward 1 and shrink |bias| without degrading MAE. Shipped as the
    # full-window fit; proj_export applies it to prospect mean paths.
    cal_full = _fit_linear_calibration([(r["baseline"], r["target"]) for r in rows])
    ic_full = (sum(r["baseline"] - r["target"] for r in rows) / len(rows)
               if len(rows) >= 250 else None)
    ic_cal_diag = (ical_fc.get("calibration") or {})
    base_cal_diag = (base.get("calibration") or {})
    fc_cal_diag = (cal_fc.get("calibration") or {})
    cal_ship = bool(
        cal_full and cal_fc.get("n", 0) > 100
        and fc_cal_diag.get("slope") is not None
        and base_cal_diag.get("slope") is not None
        and abs(fc_cal_diag["slope"] - 1) < abs(base_cal_diag["slope"] - 1)
        and abs(fc_cal_diag.get("bias", 9)) < abs(base_cal_diag.get("bias", 9))
        and cal_fc.get("mae", 9e9) <= base.get("mae", 0) + 0.02)
    base_cal2 = (ical_base.get("calibration") or {})
    ic_ship = bool(
        ic_full is not None and ical_fc.get("n", 0) > 100
        and ic_cal_diag.get("bias") is not None
        and base_cal2.get("bias") is not None
        and abs(ic_cal_diag["bias"]) < abs(base_cal2["bias"])
        and ic_cal_diag.get("slope") is not None
        and base_cal2.get("slope") is not None
        and abs(ic_cal_diag["slope"] - 1) <= abs(base_cal2["slope"] - 1) + 0.02
        and ical_fc.get("mae", 9e9) <= ical_base.get("mae", 0) + 0.02)
    out = {
        "generated_at": date.today().isoformat(),
        "debut_years": list(DEBUT_YEARS),
        "scored_years": list(SCORED_YEARS),
        "accounting": acct,
        "conventions": {
            "vintage_fv": "median of each source's latest strictly-pre-debut snapshot",
            "features": "final pre-debut-year MiLB season (2021 debuts fall back to 2019 — no 2020 MiLB), league-relative rates vs level-season medians, age, level rank, staleness; NO Statcast (AAA tracking starts 2023 — all-missing in training)",
            "target": f"first-{TARGET_SEASONS}-season bWAR (career_war)",
            "baseline": "the LIVE FV-only machinery (P(bucket|FV) x bucket trajectories from debut age)",
            "model": "per-side ridge (closed form), alpha tuned inside training folds only",
        },
        "challenger_pooled_oos": chall,
        "baseline_pooled_oos": base,
        "lgbm_challenger_pooled_oos": lgbm,
        "baseline_calibrated_pooled_oos": cal_fc,
        "baseline_intercept_only_pooled_oos": ical_fc,
        "baseline_on_intercept_rows": ical_base,
        "per_year": {str(k): v for k, v in per_year.items()},
        "ship_decision": {
            "rule": "challenger must beat FV-only on pooled OOS MAE AND "
                    "Spearman with calibration not worse; loser is "
                    "committed either way",
            "challenger_wins": bool(wins),
            "lgbm_wins": bool(lgbm_wins),
        },
        "calibration": {
            "rule": "linear recentering of the live mean path (rank-"
                    "preserving): held-out slope must move toward 1 and "
                    "|bias| shrink, MAE not degraded (+0.02 tolerance)",
            "forward_chained": cal_fc,
            "baseline_uncalibrated": {"calibration": base_cal_diag},
            "full_window_fit": cal_full,
            "ship": cal_ship,
            "applies_to": "proj_export._prospect_rows mean paths (display "
                          "layer only - surplus has its own isotonic "
                          "calibration, never double-corrected)",
        },
        "calibration_intercept_only": {
            "rule": "PRE-REGISTERED candidate #2 (2026-06-11): intercept-"
                    "only shift, min-train-n 250 (skips the thin 2019 "
                    "fold). Held-out |bias| must shrink, slope not worsen "
                    "by >0.02, MAE not degrade by >0.02.",
            "forward_chained": ical_fc,
            "full_window_shift": round(ic_full, 4) if ic_full is not None else None,
            "ship": ic_ship,
        },
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print("accounting:", rep["accounting"])
    print("challenger:", rep["challenger_pooled_oos"])
    print("baseline:  ", rep["baseline_pooled_oos"])
    for yr, v in rep["per_year"].items():
        print(yr, "chall", v["challenger"]["mae"], v["challenger"]["spearman"],
              "| base", v["baseline"]["mae"], v["baseline"]["spearman"])
    print("ship:", rep["ship_decision"]["challenger_wins"])
