# SCRATCH: (b2) LEVERAGE / OUT-OF-SUPPORT shrinkage of the model leg.
# Principled small-n variance control: a row whose feature vector sits far from the
# training design gets a high-variance ridge prediction, so shrink IT toward the
# consensus anchor rather than applying one global lambda. Controls: matched-strength
# placebos that shuffle the leverage vector within block (identical marginal, zero
# information) and a reversed-direction arm.
# Run: python tools/_frontier_shrink_bd2.py [B]
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontier_shrink import (ORIGINS, LAM, BASE_KEYS, OUT, load_pool, train_rows,
                              test_rows, fit_ridge_cfg, predict_many, block_rho,
                              resample_pool, _design, _rank_np)
import efv_model as em
from prospect_path import _fit_linear_calibration

CFG = {"mode": "shipped"}


def score_with_leverage(pool, rng_shuf):
    recs = []
    for side in ("hit", "pit"):
        rows = pool[side]
        tr_pool = train_rows(rows)
        te_pool = test_rows(rows)
        keys = BASE_KEYS[side]
        for yr in ORIGINS:
            tr = [r for r in tr_pool if r["decision_year"] < yr]
            te = [r for r in te_pool if r["decision_year"] == yr]
            if len(te) < 15 or len(tr) < 60:
                continue
            ols = em._fit_ols_fv(tr)
            ridge = fit_ridge_cfg(tr, keys, CFG)
            if not (ols and ridge):
                continue
            Xs, y, w, mu, sd = _design(tr, keys)
            alpha = ridge["alpha"]
            A = (Xs * w[:, None]).T @ Xs + alpha * np.eye(Xs.shape[1])
            Ainv = np.linalg.inv(A)
            Xte = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in te], dtype=float)
            Zte = (Xte - mu) / np.where(sd == 0, 1.0, sd)
            lev = np.einsum("ij,jk,ik->i", Zte, Ainv, Zte)      # x' A^-1 x
            maha = (Zte ** 2).sum(axis=1)                        # distance from train centre
            raw_tr = predict_many(ridge, tr)
            c = _fit_linear_calibration(list(zip(raw_tr.tolist(),
                                                 [r["target"] for r in tr])))
            a, b = (c["a"], c["b"]) if c else (0.0, 1.0)
            raw_te = predict_many(ridge, te)
            # within-block percentile of each dispersion statistic (scale-free)
            plev = (_rank_np(lev) - 0.5) / len(lev)
            pmah = (_rank_np(maha) - 0.5) / len(maha)
            shuf = plev.copy()
            rng_shuf.shuffle(shuf)                                # placebo #1
            shuf2 = plev.copy()
            rng_shuf.shuffle(shuf2)                               # placebo #2
            for i, r in enumerate(te):
                recs.append({"side": side, "year": yr,
                             "cons": max(0.0, em._pred_ols(ols, r["fv"])),
                             "mod": max(-2.0, a + b * float(raw_te[i])),
                             "target": r["target"], "fv": r["fv"],
                             "plev": float(plev[i]), "pmah": float(pmah[i]),
                             "shuf": float(shuf[i]), "shuf2": float(shuf2[i])})
    return recs


def sch():
    S = {"global": {"k": None}}
    for key in ("plev", "pmah", "shuf", "shuf2"):
        for floor in (0.75, 0.5, 0.25):
            S[f"{'PLACEBO_' if key.startswith('shuf') else ''}{key}_f{floor:g}"] = {
                "k": key, "floor": floor, "rev": False}
        if key in ("plev", "pmah"):
            S[f"REV_{key}_f0.5"] = {"k": key, "floor": 0.5, "rev": True}
    return S


def preds(recs, sc):
    out = np.empty(len(recs))
    for i, r in enumerate(recs):
        lam = LAM[r["side"]]
        if sc["k"] is not None:
            p = r[sc["k"]]
            if sc["rev"]:
                p = 1.0 - p
            # p = 1 -> most out-of-support -> lam scaled down to `floor`
            lam = lam * (1.0 - (1.0 - sc["floor"]) * p)
        out[i] = (1 - lam) * r["cons"] + lam * r["mod"]
    return out


def main(B=400):
    t0 = time.time()
    pool = load_pool()
    rs = random.Random(2468)
    recs = score_with_leverage(pool, rs)
    S = sch()
    lv = np.array([r["plev"] for r in recs])
    print(f"n={len(recs)}  leverage percentile ok ({lv.min():.3f}..{lv.max():.3f})", flush=True)
    point = {nm: block_rho(recs, preds(recs, sc)) for nm, sc in S.items()}
    print("\n== point block_rho ==")
    for nm in S:
        print(f"  {nm:22s} {point[nm]:.5f}  d={point[nm]-point['global']:+.5f}")

    boots = {nm: [] for nm in S}
    rng = random.Random(4242)
    for b in range(B):
        rp = resample_pool(pool, rng)
        rr = score_with_leverage(rp, rs)
        for nm, sc in S.items():
            boots[nm].append(block_rho(rr, preds(rr, sc)))
        if (b + 1) % 50 == 0:
            print(f"[{time.time()-t0:.0f}s] boot {b+1}/{B}", flush=True)

    base = np.array(boots["global"], dtype=float)
    print(f"\n== paired refit bootstrap (B={B}) ==")
    print(f"{'scheme':22s} {'delta':>9s} {'bmean':>9s} {'sd':>8s} {'CI95lo':>9s} "
          f"{'CI95hi':>9s} {'P(d>0)':>7s} {'MDE95':>8s}")
    res = {}
    for nm in S:
        d = np.array(boots[nm], dtype=float) - base
        sd = float(d.std(ddof=1))
        res[nm] = {"delta": round(point[nm] - point["global"], 5),
                   "bmean": round(float(d.mean()), 5), "sd": round(sd, 5),
                   "ci95": [round(float(np.percentile(d, 2.5)), 5),
                            round(float(np.percentile(d, 97.5)), 5)],
                   "p_gt0": round(float((d > 0).mean()), 3),
                   "mde95_80": round(2.49 * sd, 5)}
        r = res[nm]
        print(f"{nm:22s} {r['delta']:>9.5f} {r['bmean']:>9.5f} {r['sd']:>8.5f} "
              f"{r['ci95'][0]:>9.5f} {r['ci95'][1]:>9.5f} {r['p_gt0']:>7.3f} "
              f"{r['mde95_80']:>8.5f}")
    plac = [nm for nm in S if nm.startswith("PLACEBO")]
    pv = np.array([res[nm]["delta"] for nm in plac])
    print(f"\nPLACEBO band (n={len(plac)}): mean {pv.mean():+.5f} "
          f"sd {pv.std(ddof=1):.5f} max|d| {np.abs(pv).max():.5f}")

    (OUT / "_scratch_shrink_bd2.json").write_text(
        json.dumps({"n": len(recs), "B": B,
                    "point": {k: round(v, 5) for k, v in point.items()},
                    "bootstrap": res,
                    "placebo_band": {"n": len(plac), "mean": round(float(pv.mean()), 5),
                                     "sd": round(float(pv.std(ddof=1)), 5),
                                     "max_abs": round(float(np.abs(pv).max()), 5)}},
                   indent=1), encoding="utf-8")
    print("\nwrote", OUT / "_scratch_shrink_bd2.json", f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(B=int(sys.argv[1]) if len(sys.argv) > 1 else 400)
