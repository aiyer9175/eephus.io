# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xFV Pass 2 -- the HITTER model + leakage-free out-of-time backtest vs consensus FV.

Trains the xFV hitter model on the Pass-1 matrix (data/xfv_hitter_matrix.json) and scores
it forward-chained against the consensus-FV-only baseline (the bar established in Pass 1).
Honest by mandate: the loser is committed either way (program rule), and we expect a TIE
on rank per the Phase-1 verdict -- the flagship case rests on the distribution/surplus
(Pass 3), not a rank win.

  TARGET     first-6-season summed bWAR, KM-censored (target_censored), sample-weighted by
             observed fraction; resolved-only run as the sensitivity check.
  COHORT     hitters; decision-year = debut_year (debuted) or last-prospect-point year + 1
             (bust). Forward-chained: predict cohort year Y with models fit on rows whose
             decision_year < Y. Two evals: DEBUTED-ONLY (clean WAR regression, the
             prospect_path protocol) and FULL-POOL (debuted + busts; the rank-the-board task,
             with the decision-year-proxy caveat stated).
  MODELS     baseline = within-fold OLS WAR~consensus_fv_raw (Spearman == FV's rank corr);
             xFV-core = prior-anchored ridge (FV dominant, standardized, alpha tuned in-fold);
             challenger = monotone LightGBM; comps = distance-weighted k-NN (also the UI
             feature); ensemble = mean(ridge, lgbm).
  GATE       a model beats consensus only if it wins BOTH pooled-OOS MAE and Spearman.

Artifact: data/xfv_eval.json. Run: python xfv_model.py
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import date
from pathlib import Path

from prospect_path import (_spearman, _calibration, _score, _fit_ridge, _predict,
                           _fit_linear_calibration)

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
MATRIX_PATH = DATA_DIR / "xfv_hitter_matrix.json"
OUT_PATH = DATA_DIR / "xfv_eval.json"

# forward-chained test cohorts (>= ~30 test rows each; earlier years seed the first fold)
SCORED_YEARS = (2020, 2021, 2022, 2023)

# feature keys + monotone direction (LightGBM); ridge ignores the sign, regularizes only.
_FEATURES_HIT = [
    ("fv",             +1),   # consensus_fv_raw -- the dominant prior
    ("n_sources",       0),
    ("tool_hit",       +1),   # Phase-1: best tool ADDER beyond FV
    ("tool_game_pwr",  +1),
    ("tool_speed",      0),
    ("tool_field",      0),
    ("age_rel_level",  -1),   # younger-for-level better
    ("level_rank",     +1),
    ("k_rel",          -1),   # hitter: more whiffs worse
    ("bb_rel",         +1),
    ("iso_rel",        +1),
    ("milb_missing",    0),
    ("pick_overall",   -1),   # earlier pick better
    ("pick_missing",    0),
    ("bonus_log",      +1),
    ("il_stints_pre",   0),
    ("fv_stddev",       0),   # Phase-1: ~dead; kept so regularization can zero it
]
_FEATURES_PIT = [
    ("fv",             +1),
    ("n_sources",       0),
    ("tool_fb",        +1),   # Phase-1: fastball the best pitcher tool adder
    ("tool_cmd",       +1),
    ("tool_sl",        +1),
    ("tool_ch",         0),
    ("tool_cb",         0),
    ("age_rel_level",  -1),
    ("level_rank",     +1),
    ("k_rel",          +1),   # pitcher: higher K-rate better (Phase-1 top adder)
    ("bb_rel",         -1),
    ("era_rel",        -1),
    ("milb_missing",    0),
    ("pick_overall",   -1),
    ("pick_missing",    0),
    ("bonus_log",      +1),
    ("il_stints_pre",   0),
    ("fv_stddev",       0),
]


def _feature_spec(side: str):
    feats = _FEATURES_PIT if side == "pit" else _FEATURES_HIT
    return [k for k, _ in feats], [m for _, m in feats]


_KEYS, _MONO = _feature_spec("hit")   # hitter defaults (back-compat for imports)


# ---------------------------------------------------------------------------
# feature vectorization (impute + missingness indicators)
# ---------------------------------------------------------------------------

def _decision_year(r) -> int:
    if r["kind"] == "debuted":
        return int(r["debut_year"])
    c = r.get("cutoff") or ""
    return (int(c[:4]) + 1) if c[:4].isdigit() else 2026


def _vec(r, side: str = "hit") -> dict:
    m = r.get("milb") or {}
    milb_missing = 0.0 if r.get("milb") else 1.0
    pick = r.get("pick_overall")
    bonus = r.get("bonus_usd")
    def g(v, d=0.0):
        return float(v) if v is not None else d
    out = {
        "fv": g(r.get("consensus_fv_raw")),
        "n_sources": g(r.get("n_sources")),
        "age_rel_level": g(m.get("age_rel_level")),
        "level_rank": g(m.get("level_rank")),
        "k_rel": g(m.get("k_rel")),
        "bb_rel": g(m.get("bb_rel")),
        "milb_missing": milb_missing,
        "pick_overall": float(pick) if pick is not None else 250.0,
        "pick_missing": 0.0 if pick is not None else 1.0,
        "bonus_log": math.log1p(float(bonus)) if bonus else 0.0,
        "il_stints_pre": g(r.get("il_stints_pre")),
        "fv_stddev": g(r.get("fv_stddev")),
    }
    if side == "pit":
        out.update({
            "tool_fb": g(r.get("tool_fb"), 45.0), "tool_cmd": g(r.get("tool_cmd"), 45.0),
            "tool_sl": g(r.get("tool_sl"), 45.0), "tool_ch": g(r.get("tool_ch"), 45.0),
            "tool_cb": g(r.get("tool_cb"), 45.0), "era_rel": g(m.get("era_rel")),
        })
    else:
        out.update({
            "tool_hit": g(r.get("tool_hit"), 45.0), "tool_game_pwr": g(r.get("tool_game_pwr"), 45.0),
            "tool_speed": g(r.get("tool_speed"), 45.0), "tool_field": g(r.get("tool_field"), 45.0),
            "iso_rel": g(m.get("iso_rel")),
        })
    return out


def _prep(rows, target_key, side: str = "hit"):
    out = []
    for r in rows:
        t = r.get(target_key)
        if t is None or r.get("consensus_fv_raw") is None:
            continue
        out.append({"player_key": r["player_key"], "kind": r["kind"],
                    "decision_year": _decision_year(r),
                    "feats": _vec(r, side), "target": float(t),
                    "weight": float(r.get("weight", 1.0)),
                    "fv": float(r["consensus_fv_raw"])})
    return out


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

def _fit_ols_fv(train):
    """Baseline: WAR ~ a + b*FV (the bar). Spearman of its prediction == FV rank corr."""
    n = len(train)
    if n < 8:
        return None
    mx = sum(r["fv"] for r in train) / n
    my = sum(r["target"] for r in train) / n
    cov = sum((r["fv"] - mx) * (r["target"] - my) for r in train)
    var = sum((r["fv"] - mx) ** 2 for r in train)
    if var <= 0:
        return None
    b = cov / var
    return {"a": my - b * mx, "b": b}


def _pred_ols(model, fv):
    return model["a"] + model["b"] * fv


def _fit_lgbm_mono(train, keys, mono):
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        return None
    if len(train) < 60:
        return None
    X = np.array([[r["feats"][k] for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    w = np.array([r["weight"] for r in train])
    model = lgb.LGBMRegressor(
        n_estimators=250, learning_rate=0.04, num_leaves=7,
        min_child_samples=25, subsample=0.9, subsample_freq=1,
        colsample_bytree=0.8, reg_lambda=5.0, monotone_constraints=mono,
        random_state=7, deterministic=True, verbose=-1)
    model.fit(X, y, sample_weight=w)
    return {"model": model, "keys": keys}


def _pred_lgbm(gbm, feats):
    import numpy as np
    import warnings as _w
    X = np.array([[feats[k] for k in gbm["keys"]]])
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        return float(gbm["model"].predict(X)[0])


def _fit_comps(train, keys):
    import numpy as np
    if len(train) < 40:
        return None
    X = np.array([[r["feats"][k] for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    return {"Xs": (X - mu) / sd, "y": y, "mu": mu, "sd": sd, "keys": keys,
            "pk": [r["player_key"] for r in train]}


def _pred_comps(cm, feats, k=20):
    import numpy as np
    x = (np.array([feats[c] for c in cm["keys"]]) - cm["mu"]) / cm["sd"]
    d = np.sqrt(((cm["Xs"] - x) ** 2).sum(axis=1))
    idx = np.argsort(d)[:k]
    w = 1.0 / (d[idx] + 1e-6)
    pred = float((w * cm["y"][idx]).sum() / w.sum())
    comps = [(cm["pk"][i], round(float(cm["y"][i]), 2), round(float(d[i]), 2))
             for i in idx[:5]]
    return pred, comps


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

def _lofo_calibrate(fold_map):
    """Leave-one-fold-out linear recentering (realized ~ a + b*pred). Rank-
    preserving (b>0), so Spearman is unchanged vs raw; only the scale/MAE
    moves. Calibration for each fold is fit on the OTHER folds only -> no
    leakage. Returns pooled calibrated [(cal_pred, target)]."""
    out, yrs = [], list(fold_map)
    for yr in yrs:
        others = [p for y in yrs if y != yr for p in fold_map[y]]
        cal = _fit_linear_calibration(others)
        if not cal:
            out.extend(fold_map[yr])
            continue
        out.extend((max(0.0, cal["a"] + cal["b"] * pred), t) for pred, t in fold_map[yr])
    return out


def _run_eval(data, label, keys=None, mono=None):
    keys = keys or _KEYS
    mono = mono or _MONO
    pairs = {m: [] for m in ("baseline", "ridge", "lgbm", "comps", "ensemble")}
    fold_map = {m: {} for m in ("ridge", "ensemble")}   # for LOFO calibration
    per_year = {}
    for yr in SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = _fit_ols_fv(train)
        ridge = _fit_ridge(train, keys)
        gbm = _fit_lgbm_mono(train, keys, mono)
        cm = _fit_comps(train, keys)
        yp = {m: [] for m in pairs}
        for r in test:
            t = r["target"]
            if ols:
                yp["baseline"].append((max(0.0, _pred_ols(ols, r["fv"])), t))
            if ridge:
                yp["ridge"].append((_predict(ridge, r["feats"]), t))
            if gbm:
                yp["lgbm"].append((_pred_lgbm(gbm, r["feats"]), t))
            if cm:
                p, _ = _pred_comps(cm, r["feats"])
                yp["comps"].append((p, t))
            if ridge and gbm:
                yp["ensemble"].append(
                    ((_predict(ridge, r["feats"]) + _pred_lgbm(gbm, r["feats"])) / 2, t))
        for m in pairs:
            pairs[m].extend(yp[m])
        for m in fold_map:
            fold_map[m][yr] = yp[m]
        per_year[str(yr)] = {m: _score(yp[m]) for m in pairs if len(yp[m]) >= 8}
    pooled = {m: (_score(pairs[m]) if pairs[m] else {"n": 0}) for m in pairs}
    # calibrated (rank-preserving) variants — the Pass-3 step that should
    # close the MAE gap without surrendering the rank edge.
    pooled["ridge_cal"] = _score(_lofo_calibrate(fold_map["ridge"])) if fold_map["ridge"] else {"n": 0}
    pooled["ensemble_cal"] = _score(_lofo_calibrate(fold_map["ensemble"])) if fold_map["ensemble"] else {"n": 0}
    base = pooled["baseline"]
    verdict = {}
    for m in ("ridge", "lgbm", "comps", "ensemble", "ridge_cal", "ensemble_cal"):
        s = pooled[m]
        if s.get("n", 0) > 80 and s.get("mae") is not None and base.get("mae") is not None:
            beats_mae = s["mae"] < base["mae"]
            beats_rho = (s.get("spearman") or -9) > (base.get("spearman") or -9)
            verdict[m] = {"beats_mae": beats_mae, "beats_spearman": beats_rho,
                          "rank_win": bool(beats_mae and beats_rho)}
    return {"label": label, "pooled_oos": pooled, "per_year": per_year,
            "verdict_vs_consensus": verdict}


def _importances(data, keys=None, mono=None):
    """Full-window diagnostics (NOT shipped predictions): standardized ridge weights +
    lgbm gain, to show WHERE the signal is. Interpretation only."""
    keys = keys or _KEYS
    mono = mono or _MONO
    out = {}
    ridge = _fit_ridge(data, keys)
    if ridge:
        out["ridge_std_weights"] = {k: round(w, 3) for k, w in zip(ridge["keys"], ridge["w"])}
    gbm = _fit_lgbm_mono(data, keys, mono)
    if gbm:
        imp = gbm["model"].feature_importances_
        tot = float(sum(imp)) or 1.0
        out["lgbm_gain_share"] = {k: round(float(v) / tot, 3)
                                  for k, v in sorted(zip(keys, imp), key=lambda x: -x[1])}
    return out


def run(persist: bool = True, side: str = "hit") -> dict:
    from xfv_dataset import matrix_path
    keys, mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in rows if r["kind"] == "debuted"]
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]

    evals = {
        "debuted_km": _run_eval(_prep(deb, "target_censored", side), "debuted, KM-censored target", keys, mono),
        "debuted_resolved": _run_eval(_prep([r for r in deb if not r["censored"]],
                                            "target_resolved", side), "debuted, resolved-only (sensitivity)", keys, mono),
        "full_pool_km": _run_eval(_prep(full, "target_censored", side),
                                  "full pool (debuted+busts), KM target [decision-year proxy]", keys, mono),
    }
    out = {
        "generated_at": date.today().isoformat(),
        "model": f"xFV {'pitcher' if side == 'pit' else 'hitter'} v0",
        "scope": "PITCHERS" if side == "pit" else "HITTERS",
        "conventions": {
            "target": "first-6-season summed bWAR; KM-censored (rate-projected tail) + resolved sensitivity",
            "vintage": "features strictly pre-outcome (Pass-1 matrix; leakage verified 0)",
            "protocol": "forward-chained by decision-year cohort; pooled OOS",
            "baseline": "within-fold OLS WAR ~ consensus_fv_raw (THE bar)",
            "gate": "beat consensus on BOTH pooled-OOS MAE and Spearman",
            "features": keys,
        },
        "evals": evals,
        "feature_diagnostics_full_window": _importances(_prep(deb, "target_censored", side), keys, mono),
        "honest_note": ("xFV's flagship case is the calibrated distribution + uncertainty + "
                        "surplus, plus a small rank edge where the data supports it. The loser "
                        "is committed either way."),
    }
    if persist:
        out_path = OUT_PATH if side == "hit" else (DATA_DIR / "xfv_eval_pitcher.json")
        out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", out_path)
    return out


def _fmt(s):
    return f"n={s.get('n',0):4d} mae={s.get('mae')} rho={s.get('spearman')}"


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run(side="pit" if "--pit" in sys.argv else "hit")
    for ek, ev in rep["evals"].items():
        print(f"\n=== {ek}: {ev['label']} ===")
        for m, s in ev["pooled_oos"].items():
            if s.get("n"):
                print(f"  {m:10s} {_fmt(s)}")
        print("  verdict vs consensus:", json.dumps(ev["verdict_vs_consensus"]))
    print("\nfeature diagnostics (full-window, interpretation only):")
    print("  ridge std weights:", json.dumps(rep["feature_diagnostics_full_window"].get("ridge_std_weights", {})))
    print("  lgbm gain share:  ", json.dumps(rep["feature_diagnostics_full_window"].get("lgbm_gain_share", {})))
