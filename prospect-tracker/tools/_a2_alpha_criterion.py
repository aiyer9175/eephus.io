# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""A2 addendum: instrument the shipped per-fold auto-alpha picks, and test a DEPLOYABLE
in-fold criterion swap -- select alpha inside each training fold's seeded holdout by
Spearman (rank) instead of MAE, on a wider grid. Leakage-honest (holdout is inside train).
Bar: pooled Spearman delta lo95 > 0 vs the shipped MAE-selector."""
from __future__ import annotations
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)
import numpy as np
import efv_lab_runner as LAB
import efv_model as XM
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
from prospect_path import _spearman, _RIDGE_HOLDOUT_SEED
import efv_weight_recal_lab as A2

SCORED_YEARS = XM.SCORED_YEARS
WIDE = [1.0, 3.0, 10.0, 30.0, 100.0, 300.0]


def _fit_ridge_crit(train, keys, grid, criterion):
    """Mirror shipped _fit_ridge but pick alpha on the seeded holdout by 'mae' or 'spearman',
    over the supplied grid. Returns (model_dict, chosen_alpha)."""
    if len(train) < 40:
        return None, None
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in train], dtype=float)
    y = np.array([r["target"] for r in train], dtype=float)
    wts = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in train]), 1e-3, None)
    mu, sd = X.mean(axis=0), X.std(axis=0); sd[sd == 0] = 1.0
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

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    k = max(1, n // 5)
    ho, tri = order[:k], order[k:]
    b_tr = _wmean(tri)
    best = None
    for alpha in grid:
        w = _wridge(tri, alpha, b_tr)
        pred = Xs[ho] @ w + b_tr
        if criterion == "mae":
            score = -(float(np.average(np.abs(pred - y[ho]), weights=wts[ho]))
                      if wts[ho].sum() > 0 else float(np.abs(pred - y[ho]).mean()))
        else:  # spearman (higher better)
            sp = _spearman(pred.tolist(), y[ho].tolist())
            score = sp if sp is not None else -9
        if best is None or score > best[0]:
            best = (score, alpha)
    alpha = best[1]
    b = _wmean(np.arange(n))
    w = _wridge(np.arange(n), alpha, b)
    return {"keys": keys, "mu": mu.tolist(), "sd": sd.tolist(),
            "w": w.tolist(), "b": float(b), "alpha": alpha}, alpha


def forward_crit(side, grid, criterion):
    lean = _feature_spec(side)[0]
    lam = blend_lambda(side)
    rows = [r for r in LAB.data_for(side) if r.get("target_censored") is not None]
    out, picks = [], {}
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": r["feats"], "target": r["target_censored"], "weight": r["weight"]} for r in tr]
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        m, a = _fit_ridge_crit(trf, lean, grid, criterion)
        if not (ols and m):
            continue
        picks[str(yr)] = a
        for r in te:
            z = 0.0
            for kk, mm, ss, ww in zip(m["keys"], m["mu"], m["sd"], m["w"]):
                z += ww * ((r["feats"].get(kk, 0.0) - mm) / (ss or 1.0))
            rp = z + m["b"]
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            out.append({"pk": r["player_key"], "fv": r["fv"],
                        "score": float((1 - lam) * cw + lam * rp),
                        "truth": float(r["target_censored"])})
    return out, picks


def main():
    rep = {}
    for side in ("hit", "pit"):
        base = A2.forward(side, alpha=None)   # shipped auto (MAE, grid 1/10/100)
        _, picks_mae_ship = forward_crit(side, [1.0, 10.0, 100.0], "mae")
        mae_wide, picks_mae_wide = forward_crit(side, WIDE, "mae")
        spr_ship, picks_spr_ship = forward_crit(side, [1.0, 10.0, 100.0], "spearman")
        spr_wide, picks_spr_wide = forward_crit(side, WIDE, "spearman")
        rep[side] = {
            "shipped_perfold_alpha_mae(1/10/100)": picks_mae_ship,
            "mae_wide": {"picks": picks_mae_wide, "delta": A2.boot_delta(base, mae_wide)},
            "spearman_ship_grid": {"picks": picks_spr_ship, "delta": A2.boot_delta(base, spr_ship)},
            "spearman_wide_grid": {"picks": picks_spr_wide, "delta": A2.boot_delta(base, spr_wide)},
        }
        for tag in ("mae_wide", "spearman_ship_grid", "spearman_wide_grid"):
            dd = rep[side][tag]["delta"]
            print(f"[{side}] {tag:20s} picks={rep[side][tag]['picks']} "
                  f"rho={dd['var_spearman']} dmean={dd['d_spearman_mean']:+.4f} "
                  f"lo95={dd['d_spearman_lo95']:+.4f} p={dd['p_gt0']} "
                  f"auc {dd['base_auc']}->{dd['var_auc']}")
        print(f"[{side}] shipped per-fold MAE picks (1/10/100): {picks_mae_ship}")
    Path(ROOT / "data" / "_a2_alpha_criterion.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print("wrote data/_a2_alpha_criterion.json")


if __name__ == "__main__":
    main()
