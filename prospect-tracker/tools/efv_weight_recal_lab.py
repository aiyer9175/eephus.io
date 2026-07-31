# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""LANE A2 -- weight + alpha + feature recalibration on the REPAIRED matrices.

Reuses the SHIPPED forward-chained OOS protocol (tools/efv_lab_runner.data_for +
efv_model._fit_ols_fv / _pred_ols / blend_lambda), so a gain here is a real leakage-clean
gain on the exact protocol data/xfv_eval.json uses. Baseline reproduces the same-run
scoreboard (hit pooled Spearman 0.3787 / pit 0.302).

Three jobs (owner: "maximize accuracy / check the weighting on the different aspects"):
  (1) RIDGE ALPHA re-selection per side -- the shipped fit auto-picks alpha in-fold from
      (1,10,100) by seeded-holdout MAE; sweep a wider grid, pick pooled-OOS-Spearman-max,
      cross-check with a leakage-honest forward-chained alpha pick + AUC.
  (2) FITTED RIDGE ATTRIBUTE WEIGHTS dumped per feature both sides, before (shipped alpha)
      and after (re-selected alpha).
  (3) MARGINAL REJECTED FEATURES re-tested on repaired labels: iso_rel, peak_iso_rel, a
      level feature (pit level_rank), explicit K-BB. Each ADDED to the shipped lean set.
      Missing MiLB-rate rows imputed at the TRAIN-FOLD observed mean (neutral under
      standardization -- never a constant that manufactures signal from missingness); the
      0-imputed (shipped-convention) contrast is reported alongside.

Bar for any ship: pooled Spearman delta lo95 > 0 (player-clustered bootstrap, seed 20260724,
2000 reps) AND AUC not worse.

Run:  python tools/efv_weight_recal_lab.py            # full sweep -> data/xfv_weight_recal_eval.json
      python tools/efv_weight_recal_lab.py --verify   # baseline reproduction only
"""
from __future__ import annotations
import sys, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)

import numpy as np
import efv_lab_runner as LAB
import efv_model as XM
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
from prospect_path import _spearman, _predict

SCORED_YEARS = XM.SCORED_YEARS
SEED = 20260724
NREPS = 2000
CONTRIB_WAR = 3.0   # positive class for the AUC co-check (a first-6yr contributor)


# ---------------------------------------------------------------------------
# ridge with a FIXED alpha -- byte-for-byte the shipped _fit_ridge math except
# the in-fold MAE alpha auto-selection is replaced by the passed alpha.
# ---------------------------------------------------------------------------
def _fit_ridge_fixed(train, keys, alpha, added=None, impute=None):
    if len(train) < 40:
        return None
    added = added or {}
    impute = impute or {}

    def _val(r, k):
        f = r["feats"]
        if k in added:
            miss = f.get("milb_missing", 0.0) == 1.0
            if miss and k in impute:
                return impute[k]
            return added[k](f)
        return f.get(k, 0.0)

    X = np.array([[_val(r, k) for k in keys] for r in train], dtype=float)
    y = np.array([r["target"] for r in train], dtype=float)
    wts = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in train]), 1e-3, None)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    b = float(np.average(y, weights=wts))
    WX = Xs * wts[:, None]
    A = WX.T @ Xs + alpha * np.eye(len(keys))
    w = np.linalg.solve(A, WX.T @ (y - b))
    return {"keys": keys, "mu": mu.tolist(), "sd": sd.tolist(),
            "w": w.tolist(), "b": b, "alpha": alpha,
            "added": added, "impute": impute}


def _predict_fixed(model, r):
    added = model.get("added") or {}
    impute = model.get("impute") or {}
    f = r["feats"]
    z = 0.0
    for k, m, s, w in zip(model["keys"], model["mu"], model["sd"], model["w"]):
        if k in added:
            miss = f.get("milb_missing", 0.0) == 1.0
            v = impute[k] if (miss and k in impute) else added[k](f)
        else:
            v = f.get(k, 0.0)
        z += w * ((v - m) / (s or 1.0))
    return z + model["b"]


# ---------------------------------------------------------------------------
# forward-chained blend, returning PER-ROW aligned reads for bootstrapping
# ---------------------------------------------------------------------------
def forward(side, alpha=None, added=None, impute_mode="mean"):
    """Return list of dicts: {pk, fv, score, truth}. alpha=None -> shipped auto-alpha ridge.
    added: {name: fn(feats)->float} extra features appended to the lean key set.
    impute_mode: 'mean' (train-fold observed mean for milb-missing rows) | 'zero' (shipped raw)."""
    from prospect_path import _fit_ridge as _fit_ridge_auto
    lean = _feature_spec(side)[0]
    added = added or {}
    keys = lean + list(added.keys())
    lam = blend_lambda(side)
    rows = [r for r in LAB.data_for(side) if r.get("target_censored") is not None]
    out = []
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        # per-fold train-observed means for the added features (leakage-free)
        impute = {}
        if added and impute_mode == "mean":
            for k, fn in added.items():
                obs = [fn(r["feats"]) for r in tr if r["feats"].get("milb_missing", 0.0) != 1.0]
                impute[k] = float(np.mean(obs)) if obs else 0.0
        trf = [{"feats": r["feats"], "target": r["target_censored"], "weight": r["weight"]} for r in tr]
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        if ols is None:
            continue
        if alpha is None and not added:
            ridge = _fit_ridge_auto(trf, keys)
            if ridge is None:
                continue
            pred = lambda r: _predict(ridge, r["feats"])
        else:
            a = alpha if alpha is not None else _shipped_alpha(side, trf, keys)
            ridge = _fit_ridge_fixed(trf, keys, a, added=added, impute=impute)
            if ridge is None:
                continue
            pred = lambda r: _predict_fixed(ridge, r)
        for r in te:
            rp = pred(r)
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            score = (1 - lam) * cw + lam * rp
            out.append({"pk": r["player_key"], "fv": r["fv"],
                        "score": float(score), "truth": float(r["target_censored"])})
    return out


def _shipped_alpha(side, trf, keys):
    """The alpha the shipped auto-selector would pick for this exact train set (so an
    added-feature test at 'shipped alpha' matches production behaviour)."""
    from prospect_path import _fit_ridge as _fit_ridge_auto
    m = _fit_ridge_auto(trf, keys)
    return m["alpha"] if m else 10.0


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------
def _auc(scores, truths, bar=CONTRIB_WAR):
    pos = [s for s, t in zip(scores, truths) if t >= bar]
    neg = [s for s, t in zip(scores, truths) if t < bar]
    if not pos or not neg:
        return None
    # Mann-Whitney U / (n_pos*n_neg), tie-corrected
    allv = sorted(zip(scores, [1] * len(scores)))  # placeholder, use rank method
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    labels = [1 if t >= bar else 0 for t in truths]
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    sum_pos = sum(ranks[i] for i in range(len(labels)) if labels[i] == 1)
    u = sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def summarize(reads, bar=CONTRIB_WAR):
    s = [r["score"] for r in reads]
    t = [r["truth"] for r in reads]
    return {"n": len(reads),
            "spearman": round(_spearman(s, t), 4) if _spearman(s, t) is not None else None,
            "auc": round(_auc(s, t, bar), 4) if _auc(s, t, bar) is not None else None}


def boot_delta(base_reads, var_reads, bar=CONTRIB_WAR, nreps=NREPS, seed=SEED):
    """Player-clustered paired bootstrap of (variant - baseline) pooled Spearman AND AUC.
    Reads are aligned by player_key (each player appears once in the forward-chain)."""
    bmap = {r["pk"]: r for r in base_reads}
    vmap = {r["pk"]: r for r in var_reads}
    pks = [pk for pk in bmap if pk in vmap]
    bs = np.array([bmap[pk]["score"] for pk in pks])
    bt = np.array([bmap[pk]["truth"] for pk in pks])
    vs = np.array([vmap[pk]["score"] for pk in pks])
    vt = np.array([vmap[pk]["truth"] for pk in pks])
    # truths identical by construction; use bt
    rng = np.random.default_rng(seed)
    n = len(pks)
    d_rho, d_auc = [], []
    labels = (bt >= bar).astype(int)
    for _ in range(nreps):
        idx = rng.integers(0, n, n)
        br = _spearman(bs[idx].tolist(), bt[idx].tolist())
        vr = _spearman(vs[idx].tolist(), bt[idx].tolist())
        if br is not None and vr is not None:
            d_rho.append(vr - br)
        if labels[idx].sum() > 0 and labels[idx].sum() < n:
            ba = _auc(bs[idx].tolist(), bt[idx].tolist(), bar)
            va = _auc(vs[idx].tolist(), bt[idx].tolist(), bar)
            if ba is not None and va is not None:
                d_auc.append(va - ba)
    d_rho = np.array(d_rho); d_auc = np.array(d_auc)
    base = summarize(base_reads, bar); var = summarize(var_reads, bar)
    return {
        "base_spearman": base["spearman"], "var_spearman": var["spearman"],
        "d_spearman_mean": round(float(d_rho.mean()), 4),
        "d_spearman_lo95": round(float(np.percentile(d_rho, 2.5)), 4),
        "d_spearman_hi95": round(float(np.percentile(d_rho, 97.5)), 4),
        "p_gt0": round(float((d_rho > 0).mean()), 3),
        "base_auc": base["auc"], "var_auc": var["auc"],
        "d_auc_mean": round(float(d_auc.mean()), 4) if len(d_auc) else None,
        "d_auc_lo95": round(float(np.percentile(d_auc, 2.5)), 4) if len(d_auc) else None,
        "n": base["n"],
    }


# ---------------------------------------------------------------------------
# added-feature constructors (side-specific)
# ---------------------------------------------------------------------------
def _added_features(side):
    """name -> fn(feats)->float, for the marginal rejected features re-tested."""
    out = {}
    if side == "hit":
        out["iso_rel"] = lambda f: f.get("iso_rel", 0.0)
        out["peak_iso_rel"] = lambda f: f.get("peak_iso_rel", 0.0)
        # hitter plate-discipline K-BB analogue: walk minus whiff, higher = better
        out["kbb_rel"] = lambda f: f.get("bb_rel", 0.0) - f.get("k_rel", 0.0)
    else:
        out["level_rank"] = lambda f: f.get("level_rank", 0.0)
        # pitcher K-BB command edge, higher = better
        out["kbb_rel"] = lambda f: f.get("k_rel", 0.0) - f.get("bb_rel", 0.0)
        out["peak_bb_rel"] = lambda f: f.get("peak_bb_rel", 0.0)
    return out


ALPHA_GRID = [0.1, 0.3, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 50.0, 100.0, 200.0, 300.0, 1000.0]


def alpha_sweep(side, base_reads):
    res = []
    for a in ALPHA_GRID:
        reads = forward(side, alpha=a)
        d = boot_delta(base_reads, reads)
        res.append({"alpha": a, "spearman": d["var_spearman"], "auc": d["var_auc"],
                    "d_spearman_mean": d["d_spearman_mean"], "d_spearman_lo95": d["d_spearman_lo95"],
                    "d_auc_mean": d["d_auc_mean"], "p_gt0": d["p_gt0"]})
    return res


def fwdchain_alpha(side):
    """Leakage-honest deployable alpha: for each test year Y, pick the pooled-Spearman-max
    alpha on the cohorts BEFORE Y, apply to Y. Pool. (No peeking at the scored cohort.)"""
    lean = _feature_spec(side)[0]
    lam = blend_lambda(side)
    rows = [r for r in LAB.data_for(side) if r.get("target_censored") is not None]
    from prospect_path import _fit_ridge as _fit_ridge_auto  # noqa
    # precompute per-fold, per-alpha test reads
    fold = {}   # yr -> {alpha: [(pk, score, truth)]}
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": r["feats"], "target": r["target_censored"], "weight": r["weight"]} for r in tr]
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        if ols is None:
            continue
        fold[yr] = {}
        for a in ALPHA_GRID:
            ridge = _fit_ridge_fixed(trf, lean, a)
            reads = []
            for r in te:
                rp = _predict_fixed(ridge, r)
                cw = max(0.0, _pred_ols(ols, r["fv"]))
                reads.append((r["player_key"], (1 - lam) * cw + lam * rp, float(r["target_censored"])))
            fold[yr][a] = reads

    def pooled_rho(alpha, years):
        s, t = [], []
        for y in years:
            for _, sc, tv in fold.get(y, {}).get(alpha, []):
                s.append(sc); t.append(tv)
        return _spearman(s, t) if len(s) >= 8 else None

    yrs = sorted(fold)
    chosen, pooled = {}, []
    for y in yrs:
        prior = [z for z in yrs if z < y]
        if not prior:
            a = 10.0  # first cohort: mid-grid default (shipped auto lands here)
        else:
            a = max(ALPHA_GRID, key=lambda A: (pooled_rho(A, prior) or -9))
        chosen[y] = a
        for pk, sc, tv in fold[y][a]:
            pooled.append({"pk": pk, "fv": None, "score": sc, "truth": tv})
    return {"per_year_alpha": chosen, "reads": pooled}


def weight_dump(side, alpha):
    """Fit ridge on ALL debuted rows (production-style, single fit) at the given alpha;
    return the standardized attribute weight per feature."""
    lean = _feature_spec(side)[0]
    rows = [r for r in LAB.data_for(side) if r.get("target_censored") is not None]
    trf = [{"feats": r["feats"], "target": r["target_censored"], "weight": r["weight"]} for r in rows]
    m = _fit_ridge_fixed(trf, lean, alpha)
    return {k: round(w, 4) for k, w in zip(m["keys"], m["w"])}, m["b"]


def weight_dump_auto(side):
    from prospect_path import _fit_ridge as _fit_ridge_auto
    lean = _feature_spec(side)[0]
    rows = [r for r in LAB.data_for(side) if r.get("target_censored") is not None]
    trf = [{"feats": r["feats"], "target": r["target_censored"], "weight": r["weight"]} for r in rows]
    m = _fit_ridge_auto(trf, lean)
    return {k: round(w, 4) for k, w in zip(m["keys"], m["w"])}, m["b"], m["alpha"]


def main(verify_only=False):
    report = {"seed": SEED, "nreps": NREPS, "contrib_bar": CONTRIB_WAR, "sides": {}}
    for side in ("hit", "pit"):
        base_reads = forward(side, alpha=None)
        base = summarize(base_reads)
        block = {"baseline": base}
        print(f"[{side}] baseline pooled Spearman={base['spearman']} AUC={base['auc']} n={base['n']}")
        if verify_only:
            report["sides"][side] = block
            continue

        # (1) alpha sweep
        sweep = alpha_sweep(side, base_reads)
        best = max(sweep, key=lambda r: (r["spearman"] if r["spearman"] is not None else -9))
        block["alpha_sweep"] = sweep
        block["alpha_best_by_pooled"] = best
        # forward-chained honest alpha
        fc = fwdchain_alpha(side)
        fc_sum = summarize(fc["reads"])
        fc_delta = boot_delta(base_reads, fc["reads"])
        block["alpha_fwdchain"] = {"per_year_alpha": fc["per_year_alpha"],
                                   "pooled": fc_sum, "delta_vs_base": fc_delta}
        # best-fixed-alpha delta vs baseline
        best_reads = forward(side, alpha=best["alpha"])
        block["alpha_best_delta_vs_base"] = boot_delta(base_reads, best_reads)
        print(f"[{side}] alpha sweep best={best['alpha']} rho={best['spearman']} "
              f"(dlo95={block['alpha_best_delta_vs_base']['d_spearman_lo95']}); "
              f"fwdchain rho={fc_sum['spearman']} (dlo95={fc_delta['d_spearman_lo95']})")

        # (2) weight dumps: shipped-auto vs best-fixed alpha
        w_auto, b_auto, a_auto = weight_dump_auto(side)
        w_best, b_best = weight_dump(side, best["alpha"])
        block["weights_shipped_auto"] = {"alpha_full_fit": a_auto, "b": round(b_auto, 4), "w": w_auto}
        block["weights_reselected"] = {"alpha": best["alpha"], "b": round(b_best, 4), "w": w_best}

        # (3) marginal feature re-tests (single adds), mean-imputed + zero-imputed
        feats = _added_features(side)
        ftests = {}
        for name, fn in feats.items():
            r_mean = forward(side, added={name: fn}, impute_mode="mean")
            r_zero = forward(side, added={name: fn}, impute_mode="zero")
            ftests[name] = {
                "mean_impute": boot_delta(base_reads, r_mean),
                "zero_impute": boot_delta(base_reads, r_zero),
            }
            print(f"[{side}] +{name}: mean-imp d={ftests[name]['mean_impute']['d_spearman_mean']} "
                  f"lo95={ftests[name]['mean_impute']['d_spearman_lo95']} | "
                  f"zero-imp d={ftests[name]['zero_impute']['d_spearman_mean']} "
                  f"lo95={ftests[name]['zero_impute']['d_spearman_lo95']}")
        block["feature_addbacks"] = ftests

        report["sides"][side] = block

    outp = ROOT / "data" / "xfv_weight_recal_eval.json"
    outp.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {outp}")
    return report


if __name__ == "__main__":
    main(verify_only=("--verify" in sys.argv))
