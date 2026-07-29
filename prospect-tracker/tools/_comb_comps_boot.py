# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Scratch: paired bootstrap (docs/EFV_GATE_STANDARD.md) for the comps engine.

Resamples TRAIN and TEST within every forward-chained fold and REFITS both legs per draw
(comp donors + weights + standardization; and the shipped ridge/OLS/blend), so the CI
reflects SAMPLING variability rather than numerical perturbation. The registered-noise-floor
lesson in this repo is that those two get confused; this is the sampling version.

Read-only. Companion to tools/_comb_comps.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cc", ROOT / "tools" / "_comb_comps.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)
import efv_model as EM  # noqa: E402

B = 400


def main(side="hit"):
    pool = cc.load_pool(side, track_record=True)
    cache = cc.precompute(pool, side, cc.FOLD_YEARS)
    keys, _m = EM._feature_spec(side)
    lam = EM._BLEND_LAMBDA_RESELECT.get(side) or EM._BLEND_LAMBDA_FALLBACK[side]
    rng = np.random.default_rng(cc.SEED)

    cfgs = {"M_MODEL": cc.M_MODEL, "M_ARCH": cc.M_ARCH}
    diffs = {k: [] for k in cfgs}
    rhos = {k: [] for k in cfgs}
    rho_blend = []

    for _ in range(B):
        pc = {k: [] for k in cfgs}
        pb, tt = [], []
        for yr, F in cache.items():
            ntr, nte = len(F["tr"]), len(F["te"])
            itr = rng.integers(0, ntr, ntr)
            ite = rng.integers(0, nte, nte)
            ytr_b = F["ytr"][itr]
            yte_b = F["yte"][ite]
            tt.extend(yte_b.tolist())
            # comp legs: donors + weights refit on the resampled train
            for lab, cfg in cfgs.items():
                Ztr, Zte, _ = F["per"][cfg["axis_set"]]
                A, Bm = Ztr[itr], Zte[ite]
                w = cc.fit_weights(A, ytr_b, cfg["weighting"])
                g = cfg["gate"] == "G1_LEVEL_BAND"
                pc[lab].extend(cc.comp_predict(
                    A, ytr_b, Bm, w, cfg["k"],
                    F["lvl_tr"][itr] if g else None,
                    F["lvl_te"][ite] if g else None).tolist())
            # shipped leg: ridge + consensus OLS refit on the resampled train
            trb = [F["tr"][i] for i in itr]
            teb = [F["te"][i] for i in ite]
            d = EM._prep(trb, cc.TARGET, side)
            ols = EM._fit_ols_fv(d)
            ridge = EM._fit_ridge(d, keys)
            if not (ols and ridge):
                pb.extend([0.0] * len(teb))
                continue
            for r in teb:
                cons = max(0.0, EM._pred_ols(ols, float(r["consensus_fv_raw"])))
                pb.append((1 - lam) * cons + lam * EM._predict(ridge, EM._vec(r, side)))
        tt = np.array(tt)
        rb = cc.spearman(np.array(pb), tt)
        rho_blend.append(rb)
        for lab in cfgs:
            rc = cc.spearman(np.array(pc[lab]), tt)
            rhos[lab].append(rc)
            diffs[lab].append(rc - rb)

    out = {"side": side, "B": B, "lambda": lam,
           "shipped_blend_rho": {"mean": float(np.mean(rho_blend)),
                                 "ci95": [float(np.percentile(rho_blend, 2.5)),
                                          float(np.percentile(rho_blend, 97.5))]}}
    print(f"== PAIRED BOOTSTRAP (refit per draw) side={side}  B={B}")
    print(f"   shipped blend rho  mean {np.mean(rho_blend):+.4f}  "
          f"CI95 [{np.percentile(rho_blend,2.5):+.4f}, {np.percentile(rho_blend,97.5):+.4f}]")
    for lab in cfgs:
        d = np.array(diffs[lab])
        r = np.array(rhos[lab])
        lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
        out[lab] = {"id": cfgs[lab]["id"],
                    "rho_mean": float(r.mean()),
                    "rho_ci95": [float(np.percentile(r, 2.5)),
                                 float(np.percentile(r, 97.5))],
                    "delta_vs_blend_mean": float(d.mean()),
                    "delta_vs_blend_ci95": [lo, hi],
                    "p_beats_blend": float((d > 0).mean()),
                    "ci_excludes_zero": bool(lo > 0 or hi < 0)}
        print(f"   [{lab}] rho {r.mean():+.4f} CI95 "
              f"[{np.percentile(r,2.5):+.4f}, {np.percentile(r,97.5):+.4f}]")
        print(f"        delta vs shipped blend {d.mean():+.4f}  CI95 [{lo:+.4f}, {hi:+.4f}]"
              f"   P(beats blend) {(d>0).mean():.3f}   "
              f"{'RESOLVED' if (lo>0 or hi<0) else 'NOT RESOLVED (CI straddles 0)'}")
    (cc.OUT / f"boot_{side}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "hit")
