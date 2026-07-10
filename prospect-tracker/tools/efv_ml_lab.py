# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV ML lab -- swap the MODEL CLASS / feature set / target / objective on the EXACT
forward-chained, leakage-clean OOS protocol that data/xfv_eval.json + tools/efv_lab_runner.py
use. The shipped eFV ranker is a prior-anchored linear RIDGE (LightGBM is only an evaluated
challenger that LOSES). This harness answers: can a different ML model / objective / target
/ feature set beat the ridge on the Spearman gate -- pooled, within-tier, and at the FV-45
fringe (the hard, valuable cohort)?

A variant spec (dict):
  {"id": str,
   "side": "hit"|"pit",
   "model": "ols_fv"|"ridge"|"elasticnet"|"lgbm"|"histgbm"|"rf"|"extratrees"|
            "gbr"|"knn"|"lgbm_rank"|"lgbm_quantile",
   "features": "lean"|"full"|"rich"|[explicit keys],
   "target": "censored"|"resolved"|"wpy"|"rank"|"residual",
   "params": {...},                 # model hyperparams (optional)
   "blend": "war"|"z"|"none",      # how to combine with consensus for the headline score
   "lam": float|null,               # blend weight (default = shipped blend_lambda(side))
   "mono": bool,                    # apply monotone constraints (tree models, lean set only)
   "extra_join": "defense"|"decision"|null}   # join Will's-model per-player features (if present)

Reports, vs the shipped ridge baseline for that side: pooled OOS Spearman (pure model AND
blended), within-FV-tier weighted-mean + t45 (the model-only signal, since FV is ~constant
in a tier), era split, per-cohort, per-year stability.

Run:  python tools/xfv_ml_lab.py SPECS.json OUT.json
      python tools/xfv_ml_lab.py --selftest        # confirm baseline reproduces 0.3699/0.2625
"""
from __future__ import annotations
import sys, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import numpy as np
import efv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
import efv_lab_runner as LAB

SCORED_YEARS = XM.SCORED_YEARS

# ---------------------------------------------------------------------------
# feature sets
# ---------------------------------------------------------------------------

# the rich "full" set: everything _vec emits that is a usable numeric feature.
# (excludes pure-id/leakage fields; cohort flags are added in LAB.load_side.)
_FULL_HIT = [
    "fv", "fv_trend", "fv_stddev", "n_sources", "age_rel_level", "level_rank",
    "k_rel", "bb_rel", "obp_rel", "ops_rel", "iso_rel",
    "peak_obp_rel", "peak_k_rel", "peak_iso_rel", "peak_ops_rel",
    "milb_missing", "n_milb_seasons", "prod_trend", "pos_prem",
    "pick_overall", "pick_missing", "bonus_log", "il_stints_pre",
    "is_ifa", "is_college", "is_hs",
    "tool_hit", "tool_game_pwr", "tool_speed", "tool_field",
]
_FULL_PIT = [
    "fv", "fv_trend", "fv_stddev", "n_sources", "age_rel_level", "level_rank",
    "k_rel", "bb_rel", "era_rel", "peak_k_rel", "peak_bb_rel", "x_era_k",
    "milb_missing", "n_milb_seasons", "prod_trend",
    "pick_overall", "pick_missing", "bonus_log", "il_stints_pre",
    "is_ifa", "is_college", "is_hs",
    "tool_fb", "tool_cmd", "tool_sl", "tool_ch", "tool_cb",
]
# "rich" = lean + a hand-picked few extra signals (a middle ground)
_RICH_HIT = [k for k, _ in XM._FEATURES_HIT] + [
    "ops_rel", "peak_ops_rel", "iso_rel", "level_rank", "prod_trend",
    "fv_trend", "il_stints_pre", "tool_field", "pos_prem"]
_RICH_PIT = [k for k, _ in XM._FEATURES_PIT] + [
    "bb_rel", "peak_bb_rel", "level_rank", "prod_trend", "fv_trend",
    "il_stints_pre", "tool_cmd", "tool_sl"]

# monotone direction for the LEAN set (matches efv_model)
_MONO_LEAN = {"hit": {k: m for k, m in XM._FEATURES_HIT},
              "pit": {k: m for k, m in XM._FEATURES_PIT}}


def feature_keys(side, spec_features):
    if isinstance(spec_features, list):
        return list(spec_features)
    if spec_features == "lean":
        return _feature_spec(side)[0]
    if spec_features == "full":
        return list(_FULL_HIT if side == "hit" else _FULL_PIT)
    if spec_features == "rich":
        # de-dup preserving order
        base = _RICH_HIT if side == "hit" else _RICH_PIT
        seen, out = set(), []
        for k in base:
            if k not in seen:
                seen.add(k); out.append(k)
        return out
    raise ValueError(f"unknown feature set {spec_features!r}")


# ---------------------------------------------------------------------------
# target transforms (leakage-free: computed within TRAIN only where needed)
# ---------------------------------------------------------------------------

def target_value(r, target):
    if target == "censored":
        return r["target_censored"]
    if target == "resolved":
        return r["target_resolved"]
    if target == "wpy":
        return r["wpy"]
    if target in ("rank", "residual"):
        return r["target_censored"]   # transformed per-fold in run_variant
    raise ValueError(target)


# ---------------------------------------------------------------------------
# model registry: fit(Xtr, ytr, wtr, keys, params) -> obj ; predict(obj, Xte) -> arr
# X are raw numeric arrays (n,d). Scaling handled per-model.
# ---------------------------------------------------------------------------

def _standardize(Xtr, Xte):
    mu = Xtr.mean(axis=0); sd = Xtr.std(axis=0); sd[sd == 0] = 1.0
    return (Xtr - mu) / sd, (Xte - mu) / sd


def _fit_predict(model, Xtr, ytr, wtr, Xte, keys, params, side, groups_tr=None):
    p = dict(params or {})
    if model in ("ens_ridge_histgbm", "ens_ridge_lgbm"):
        gbm = "histgbm" if model.endswith("histgbm") else "lgbm"
        pr = np.asarray(_fit_predict("ridge", Xtr, ytr, wtr, Xte, keys, {}, side), dtype=float)
        pg = np.asarray(_fit_predict(gbm, Xtr, ytr, wtr, Xte, keys, {**p, "mono": True}, side), dtype=float)
        wgt = p.get("ens_w", 0.5)   # weight on the GBM
        return (1 - wgt) * pr + wgt * pg
    if model == "ridge":
        # use the SHIPPED ridge (standardizes + tunes alpha in-fold) for exact parity
        tr = [{"feats": {k: Xtr[i, j] for j, k in enumerate(keys)}, "target": ytr[i]}
              for i in range(len(ytr))]
        rg = _fit_ridge(tr, keys)
        if rg is None:
            return None
        return np.array([_predict(rg, {k: Xte[i, j] for j, k in enumerate(keys)})
                         for i in range(len(Xte))])
    if model == "elasticnet":
        from sklearn.linear_model import ElasticNetCV
        Xs, Xt = _standardize(Xtr, Xte)
        m = ElasticNetCV(l1_ratio=p.get("l1_ratio", [.1, .5, .7, .9, .95, 1.0]),
                         alphas=p.get("alphas", None), cv=5, max_iter=5000,
                         random_state=7)
        m.fit(Xs, ytr, sample_weight=wtr)
        return m.predict(Xt)
    if model == "knn":
        from sklearn.neighbors import KNeighborsRegressor
        Xs, Xt = _standardize(Xtr, Xte)
        m = KNeighborsRegressor(n_neighbors=p.get("k", 20), weights="distance")
        m.fit(Xs, ytr)
        return m.predict(Xt)
    if model in ("lgbm", "lgbm_rank", "lgbm_quantile"):
        import lightgbm as lgb
        mono = None
        if p.get("mono"):
            mono = [_MONO_LEAN[side].get(k, 0) for k in keys]
        common = dict(n_estimators=p.get("n_estimators", 250),
                      learning_rate=p.get("learning_rate", 0.04),
                      num_leaves=p.get("num_leaves", 7),
                      min_child_samples=p.get("min_child_samples", 25),
                      subsample=p.get("subsample", 0.9), subsample_freq=1,
                      colsample_bytree=p.get("colsample_bytree", 0.8),
                      reg_lambda=p.get("reg_lambda", 5.0),
                      random_state=7, deterministic=True, verbose=-1, n_jobs=1)
        if mono is not None:
            common["monotone_constraints"] = mono
        if model == "lgbm":
            m = lgb.LGBMRegressor(**common)
            m.fit(Xtr, ytr, sample_weight=wtr)
            return m.predict(Xtr if False else Xte)
        if model == "lgbm_quantile":
            common.update(objective="quantile", alpha=p.get("alpha", 0.5))
            m = lgb.LGBMRegressor(**common)
            m.fit(Xtr, ytr, sample_weight=wtr)
            return m.predict(Xte)
        if model == "lgbm_rank":
            # learning-to-rank: relevance = decile bin of target within each train group
            common.pop("subsample", None); common.pop("subsample_freq", None)
            common.pop("colsample_bytree", None)
            m = lgb.LGBMRanker(objective=p.get("rank_obj", "lambdarank"),
                               label_gain=list(range(0, 64)), **common)
            # build group sizes from groups_tr (must be contiguous-sorted)
            order = np.argsort(groups_tr, kind="stable")
            Xo, yo, go = Xtr[order], ytr[order], np.array(groups_tr)[order]
            # relevance grades 0..9 per group by decile of target
            rel = np.zeros(len(yo), dtype=int)
            sizes = []
            i = 0
            while i < len(go):
                j = i
                while j + 1 < len(go) and go[j + 1] == go[i]:
                    j += 1
                grp = yo[i:j + 1]
                if len(grp) >= 2:
                    ranks = grp.argsort().argsort()
                    rel[i:j + 1] = np.minimum(9, (ranks * 10 // len(grp)).astype(int))
                sizes.append(j + 1 - i)
                i = j + 1
            m.fit(Xo, rel, group=sizes)
            return m.predict(Xte)
    if model == "histgbm":
        from sklearn.ensemble import HistGradientBoostingRegressor
        mono = None
        if p.get("mono"):
            mono = [_MONO_LEAN[side].get(k, 0) for k in keys]
        m = HistGradientBoostingRegressor(
            max_iter=p.get("max_iter", 300), learning_rate=p.get("learning_rate", 0.04),
            max_leaf_nodes=p.get("max_leaf_nodes", 8), min_samples_leaf=p.get("min_samples_leaf", 25),
            l2_regularization=p.get("l2", 5.0), max_depth=p.get("max_depth", None),
            monotonic_cst=mono, random_state=7)
        m.fit(Xtr, ytr, sample_weight=wtr)
        return m.predict(Xte)
    if model in ("rf", "extratrees"):
        from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor
        cls = RandomForestRegressor if model == "rf" else ExtraTreesRegressor
        m = cls(n_estimators=p.get("n_estimators", 400),
                min_samples_leaf=p.get("min_samples_leaf", 8),
                max_features=p.get("max_features", 0.5), n_jobs=1, random_state=7)
        m.fit(Xtr, ytr, sample_weight=wtr)
        return m.predict(Xte)
    if model == "gbr":
        from sklearn.ensemble import GradientBoostingRegressor
        m = GradientBoostingRegressor(
            n_estimators=p.get("n_estimators", 250), learning_rate=p.get("learning_rate", 0.04),
            max_depth=p.get("max_depth", 3), subsample=p.get("subsample", 0.9),
            min_samples_leaf=p.get("min_samples_leaf", 25), random_state=7)
        m.fit(Xtr, ytr, sample_weight=wtr)
        return m.predict(Xte)
    raise ValueError(f"unknown model {model!r}")


def _tier(fv): return round(fv / 5) * 5
def _era(yr): return "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")


# ---------------------------------------------------------------------------
# extra (Will's-model) per-player feature joins, if present on disk
# ---------------------------------------------------------------------------
_EXTRA_CACHE = {}

def _load_extra(kind):
    """kind 'defense'|'decision' -> {mlbam_id(str): {feat:val}}. Returns {} if not generated."""
    if kind in _EXTRA_CACHE:
        return _EXTRA_CACHE[kind]
    path = ROOT / "data" / f"xfv_extra_{kind}.json"
    out = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for r in raw:
                key = str(r.get("mlbam_id") or r.get("player_key") or "")
                if key:
                    out[key] = {k: v for k, v in r.items()
                                if k not in ("mlbam_id", "player_key", "name") and v is not None}
        except (OSError, ValueError):
            pass
    _EXTRA_CACHE[kind] = out
    return out


# need the raw matrix rows to recover mlbam_id for joins
_MID_CACHE = {}
def _mlbam_map(side):
    if side not in _MID_CACHE:
        from efv_dataset import matrix_path
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        _MID_CACHE[side] = {r["player_key"]: str(r.get("mlbam_id") or "") for r in rows}
    return _MID_CACHE[side]


def run_variant(v):
    side = v.get("side", "hit")
    target = v.get("target", "censored")
    blend = v.get("blend", "war")
    model = v.get("model", "ridge")
    params = dict(v.get("params") or {})
    if v.get("mono"):
        params["mono"] = True
    keys = feature_keys(side, v.get("features", "lean"))
    lam = v.get("lam")
    if lam is None:
        lam = blend_lambda(side)
    extra = v.get("extra_join")

    rows = list(LAB.data_for(side))
    # attach extra features
    extra_keys = []
    if extra:
        emap = _load_extra(extra)
        mid = _mlbam_map(side)
        if emap:
            # union of feature keys present
            allk = sorted({k for d in emap.values() for k in d})
            extra_keys = [f"x_{extra}_{k}" for k in allk]
            for r in rows:
                d = emap.get(mid.get(r["player_key"], ""), {})
                for k in allk:
                    r["feats"][f"x_{extra}_{k}"] = float(d.get(k, 0.0) or 0.0)
            keys = keys + extra_keys

    pooled = []        # (blended_score, target_value, fv, cohort)
    pooled_pure = []   # (pure_model_score, target_value)
    per_year = defaultdict(list)
    n_skipped = 0
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr and target_value(r, target) is not None]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        ytr = np.array([target_value(r, target) for r in tr], dtype=float)
        # EVAL TRUTH is ALWAYS the canonical realized first-6yr summed WAR (target_censored),
        # regardless of which target the model was TRAINED on -- so target-engineering variants
        # are fairly comparable to the shipped model on the product's actual ranking goal.
        eval_truth = v.get("eval_target", "censored")
        if eval_truth == "wpy":
            yte_actual = np.array([r["wpy"] for r in te], dtype=float)
        elif eval_truth == "resolved":
            yte_actual = np.array([r["target_resolved"] for r in te], dtype=float)
        else:
            yte_actual = np.array([r["target_censored"] for r in te], dtype=float)
        Xtr = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in tr], dtype=float)
        Xte = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in te], dtype=float)
        wtr = np.array([r["weight"] for r in tr], dtype=float)

        # consensus OLS anchor (always on realized WAR for the blend)
        olst = [{"fv": r["fv"], "target": r["target_censored"]} for r in tr]
        ols = _fit_ols_fv(olst)
        if ols is None:
            continue
        cons_te = np.array([max(0.0, _pred_ols(ols, r["fv"])) for r in te])

        # target transforms that need per-fold train stats
        groups_tr = None
        if target == "rank":
            # within-cohort percentile rank of censored target (per decision_year group)
            grp = defaultdict(list)
            for i, r in enumerate(tr):
                grp[r["decision_year"]].append(i)
            yt = np.zeros(len(tr))
            for idxs in grp.values():
                vals = ytr[idxs]
                rk = vals.argsort().argsort().astype(float)
                yt[idxs] = rk / max(1, len(idxs) - 1)
            ytr = yt
        elif target == "residual":
            cons_tr = np.array([max(0.0, _pred_ols(ols, r["fv"])) for r in tr])
            ytr = np.array([r["target_censored"] for r in tr]) - cons_tr
        if model == "lgbm_rank":
            groups_tr = [r["decision_year"] for r in tr]

        try:
            pred = _fit_predict(model, Xtr, ytr, wtr, Xte, keys, params, side, groups_tr)
        except Exception as e:  # noqa
            n_skipped += 1
            continue
        if pred is None:
            n_skipped += 1
            continue
        pred = np.asarray(pred, dtype=float)

        # build the headline (blended) score
        if target == "residual":
            model_war = cons_te + pred       # additive correction
        else:
            model_war = pred
        if blend == "none":
            score = pred
        elif blend == "z":
            # z-standardize cons and model on the TEST fold's mean/std is leakage; use train preds' stats
            # cheap proxy: standardize within the test fold (rank-comparison only) -- acceptable since
            # spearman is computed within-fold-pooled; to stay clean we standardize by train-pred stats:
            mtr = _fit_predict(model, Xtr, ytr, wtr, Xtr, keys, params, side, groups_tr)
            mtr = np.asarray(mtr, dtype=float)
            mu_m, sd_m = mtr.mean(), (mtr.std() or 1.0)
            ctr = np.array([max(0.0, _pred_ols(ols, r["fv"])) for r in tr])
            mu_c, sd_c = ctr.mean(), (ctr.std() or 1.0)
            score = (1 - lam) * ((cons_te - mu_c) / sd_c) + lam * ((pred - mu_m) / sd_m)
        else:  # "war"
            score = (1 - lam) * cons_te + lam * model_war

        for i, r in enumerate(te):
            pooled.append((float(score[i]), float(yte_actual[i]), r["fv"], r["cohort"]))
            pooled_pure.append((float(pred[i]), float(yte_actual[i])))
            per_year[yr].append((float(score[i]), float(yte_actual[i])))

    if len(pooled) < 30:
        return {"id": v.get("id"), "n": len(pooled), "spearman": None,
                "error": "too few rows", "skipped_folds": n_skipped}

    rho = _spearman([a for a, _, _, _ in pooled], [b for _, b, _, _ in pooled])
    rho_pure = _spearman([a for a, _ in pooled_pure], [b for _, b in pooled_pure])
    # within-tier
    byt = defaultdict(list)
    for s, t, fv, _ in pooled:
        byt[_tier(fv)].append((s, t))
    wsum = wn = 0; t45 = None; per_tier = {}
    for tk, grp in byt.items():
        if len(grp) < 15:
            continue
        r = _spearman([a for a, _ in grp], [b for _, b in grp])
        if r is None:
            continue
        per_tier[tk] = {"n": len(grp), "rho": round(r, 4)}
        wsum += r * len(grp); wn += len(grp)
        if tk == 45:
            t45 = round(r, 4)
    bye = defaultdict(list)
    for yr, prs in per_year.items():
        bye[_era(yr)].extend(prs)
    era = {k: round(_spearman([a for a, _ in g], [b for _, b in g]), 4)
           for k, g in bye.items() if len(g) >= 15 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    byc = defaultdict(list)
    for s, t, fv, c in pooled:
        byc[c].append((s, t))
    coh = {k: {"n": len(g), "rho": round(_spearman([a for a, _ in g], [b for _, b in g]), 4)}
           for k, g in byc.items() if len(g) >= 25 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    pyr = {int(yr): round(_spearman([a for a, _ in g], [b for _, b in g]), 4)
           for yr, g in per_year.items() if len(g) >= 12 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}

    return {"id": v.get("id"), "side": side, "model": model, "target": target,
            "features": v.get("features", "lean") if not isinstance(v.get("features"), list) else f"custom[{len(keys)}]",
            "blend": blend, "lam": round(lam, 3), "extra_join": extra,
            "n": len(pooled), "n_keys": len(keys),
            "spearman": round(rho, 4) if rho is not None else None,
            "spearman_pure": round(rho_pure, 4) if rho_pure is not None else None,
            "within_tier_wm": round(wsum / wn, 4) if wn else None,
            "t45": t45, "per_tier": per_tier, "era": era, "per_cohort": coh, "per_year": pyr,
            "skipped_folds": n_skipped}


def baseline(side):
    return run_variant({"id": f"BASELINE:{side}", "side": side, "model": "ridge",
                        "features": "lean", "target": "censored", "blend": "war"})


def lambda_curve(side, model="ridge", features="lean", lams=None):
    """Pooled-OOS Spearman of the blend as a function of lambda -- diagnostic only
    (selecting lambda on this pooled curve is test-tuning; use lambda_fwdchain to SHIP)."""
    lams = lams or [round(0.05 * i, 2) for i in range(0, 21)]
    return {lam: run_variant({"id": f"{side}:{model}:lam{lam}", "side": side, "model": model,
                              "features": features, "target": "censored", "blend": "war",
                              "lam": lam})["spearman"] for lam in lams}


def lambda_fwdchain(side, model="ridge", features="lean", cand=None):
    """LEAKAGE-FREE lambda selection: for each test cohort year Y, pick the lambda that
    maximizes the blend Spearman on the cohorts BEFORE Y (decision_year < Y), then apply it
    to Y. Pool. This is how a re-tuned lambda would actually have to be chosen in production
    -- no peeking at the cohort being scored. Returns pooled rho + the per-year lambdas."""
    cand = cand or [round(0.05 * i, 2) for i in range(1, 21)]
    keys = feature_keys(side, features)
    rows = list(LAB.data_for(side))
    # precompute pure-model + consensus preds per fold (forward-chained)
    fold_preds = {}   # yr -> list of (cons, model_pred, truth, fv)
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        ytr = np.array([r["target_censored"] for r in tr], dtype=float)
        Xtr = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in tr], dtype=float)
        Xte = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in te], dtype=float)
        wtr = np.array([r["weight"] for r in tr], dtype=float)
        params = {"mono": True} if model in ("lgbm", "histgbm") else {}
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        pred = _fit_predict(model, Xtr, ytr, wtr, Xte, keys, params, side)
        cons = np.array([max(0.0, _pred_ols(ols, r["fv"])) for r in te])
        fold_preds[yr] = [(float(cons[i]), float(pred[i]), float(r["target_censored"]), r["fv"])
                          for i, r in enumerate(te)]

    def pooled_rho_at(lam, years):
        pr, tr_ = [], []
        for y in years:
            for c, m, t, _ in fold_preds.get(y, []):
                pr.append((1 - lam) * c + lam * m); tr_.append(t)
        return _spearman(pr, tr_) if len(pr) >= 8 else None

    yrs = sorted(fold_preds)
    chosen, pooled = {}, []
    for y in yrs:
        prior = [yy for yy in yrs if yy < y]
        if not prior:
            lam = blend_lambda(side)   # first scored cohort: fall back to shipped
        else:
            lam = max(cand, key=lambda L: (pooled_rho_at(L, prior) or -9))
        chosen[y] = lam
        for c, m, t, _ in fold_preds[y]:
            pooled.append(((1 - lam) * c + lam * m, t))
    rho = _spearman([a for a, _ in pooled], [b for _, b in pooled])
    return {"side": side, "model": model, "features": features,
            "fwdchain_rho": round(rho, 4) if rho is not None else None,
            "per_year_lambda": chosen, "n": len(pooled)}


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        for side in ("hit", "pit"):
            b = baseline(side)
            print(f"BASELINE {side}: blend_rho={b['spearman']} pure_rho={b['spearman_pure']} "
                  f"wm={b['within_tier_wm']} t45={b['t45']} era={b['era']}")
        sys.exit(0)
    if len(sys.argv) >= 3:
        specs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        results = [run_variant(v) for v in specs]
        Path(sys.argv[2]).write_text(json.dumps(results, indent=1), encoding="utf-8")
        # compact stdout summary
        for r in results:
            print(f"{r.get('id'):42s} rho={r.get('spearman')} pure={r.get('spearman_pure')} "
                  f"wm={r.get('within_tier_wm')} t45={r.get('t45')} "
                  f"{'ERR:'+r['error'] if r.get('error') else ''}")
        print(f"wrote {sys.argv[2]} ({len(results)} variants)")
    else:
        print(__doc__)
