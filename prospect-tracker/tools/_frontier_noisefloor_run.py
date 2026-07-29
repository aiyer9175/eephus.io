# SCRATCH (not shipped): (a) paired bootstrap, (b) permutation null, (c) MDE
# for the shipped eFV gate. Uses the parity-verified replica in _frontier_noisefloor.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                     # noqa: E402
import _frontier_noisefloor as F          # noqa: E402

B_BOOT = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
B_NULL = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
SEED = 20260724

# features whose ADD-decision is being audited (must exist in the shipped key list)
AUDIT_FEATS = {"hit": ["age", "ops_rel", "level_rank", "milb_missing"],
               "pit": ["age", "x_era_k"]}
LAM_PAIRS = {"hit": [(0.85, 0.70), (0.85, 0.63)], "pit": [(0.54, 0.70), (0.54, 0.63)]}


def q(a, p):
    return float(np.nanpercentile(a, p))


def summ(a):
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return {"n": 0}
    return {"mean": float(a.mean()), "sd": float(a.std(ddof=1)),
            "ci95": [q(a, 2.5), q(a, 97.5)], "p_gt0": float((a > 0).mean()),
            "p95": q(a, 95), "p5": q(a, 5), "n_draws": int(len(a))}


def run_combo(side, cut, lam, keys):
    data = F.load(side, cut)
    X, y, w, fv, dy = F.arrays(data, keys)
    n = len(y)
    kidx = {k: i for i, k in enumerate(keys)}
    full_cols = np.arange(len(keys))
    abl = {f: np.array([i for i in range(len(keys)) if i != kidx[f]])
           for f in AUDIT_FEATS[side] if f in kidx}

    def point(idx=None, y_tr=None, Xuse=None):
        """One full protocol pass on a row-index selection; returns dict of stats."""
        Xu = X if Xuse is None else Xuse
        if idx is None:
            idx = np.arange(n)
        Xi, yi, wi, fvi, dyi = Xu[idx], y[idx], w[idx], fv[idx], dy[idx]
        yti = None if y_tr is None else y_tr[idx]
        out = {}
        p = F.fwd_chain(Xi, yi, wi, fvi, dyi, y_train=yti, feat_cols=full_cols)
        if p is None:
            return None
        m = F.metrics(p, lam)
        out.update(m)
        for L1, L2 in LAM_PAIRS[side]:
            r1, t1 = F.blend_at(p, L1)
            r2, t2 = F.blend_at(p, L2)
            out[f"dlam_rho_{L1}_{L2}"] = r1 - r2
            out[f"dlam_t45_{L1}_{L2}"] = t1 - t2
        for f, cols in abl.items():
            pr = F.fwd_chain(Xi, yi, wi, fvi, dyi, y_train=yti, feat_cols=cols)
            if pr is None:
                continue
            mr = F.metrics(pr, lam)
            out[f"dfeat_rho_{f}"] = m["rho_blend"] - mr["rho_blend"]
            out[f"dfeat_rhoridge_{f}"] = m["rho_ridge"] - mr["rho_ridge"]
            out[f"dfeat_t45_{f}"] = m["t45_blend"] - mr["t45_blend"]
            out[f"dfeat_mae_{f}"] = m["mae_blend"] - mr["mae_blend"]
        return out

    res = {"side": side, "cut": cut, "lam": lam, "n_rows": n,
           "point": point()}

    # ---- (a) paired bootstrap: resample the WHOLE pool (train AND test), refit ----
    rng = np.random.default_rng(SEED)
    boot = {}
    t0 = time.time()
    for _ in range(B_BOOT):
        idx = rng.integers(0, n, n)
        d = point(idx=idx)
        if d is None:
            continue
        for k, v in d.items():
            boot.setdefault(k, []).append(v)
    res["boot"] = {k: summ(v) for k, v in boot.items()}
    res["boot_secs"] = round(time.time() - t0, 1)

    # ---- (b) permutation null: shuffle the TRAIN target (with its KM weight), refit ----
    rng2 = np.random.default_rng(SEED + 1)
    null = {}
    t0 = time.time()
    for _ in range(B_NULL):
        perm = rng2.permutation(n)
        # label + its KM exposure weight travel together, so only the
        # FEATURE->label association is destroyed
        y_sh, w_sh = y[perm], w[perm]
        d = _null_point(X, y, y_sh, w_sh, fv, dy, lam, side, full_cols, abl)
        if d is None:
            continue
        for k, v in d.items():
            null.setdefault(k, []).append(v)
    res["null_shuffled_train_target"] = {k: summ(v) for k, v in null.items()}
    res["null_secs"] = round(time.time() - t0, 1)

    # ---- (b2) placebo-feature null: add a rank/marginal-identical NOISE column ----
    placebo = {}
    rng3 = np.random.default_rng(SEED + 2)
    t0 = time.time()
    for f, cols in abl.items():
        vals = []
        for _ in range(B_NULL // 2):
            Xp = X.copy()
            Xp[:, kidx[f]] = X[rng3.permutation(n), kidx[f]]   # same marginal, zero info
            pf = F.fwd_chain(Xp, y, w, fv, dy, feat_cols=full_cols)
            pr = F.fwd_chain(Xp, y, w, fv, dy, feat_cols=cols)
            if pf is None or pr is None:
                continue
            mf, mr = F.metrics(pf, lam), F.metrics(pr, lam)
            vals.append((mf["rho_blend"] - mr["rho_blend"],
                         mf["t45_blend"] - mr["t45_blend"],
                         mf["rho_ridge"] - mr["rho_ridge"]))
        if vals:
            a = np.array(vals)
            placebo[f] = {"pooled_rho": summ(a[:, 0]), "t45": summ(a[:, 1]),
                          "ridge_rho": summ(a[:, 2])}
    res["null_placebo_feature"] = placebo
    res["placebo_secs"] = round(time.time() - t0, 1)
    return res


def _null_point(X, y, y_sh, w_sh, fv, dy, lam, side, full_cols, abl):
    """Permutation-null pass: train on shuffled (target, weight), evaluate on real y."""
    out = {}
    p = F.fwd_chain(X, y, w_sh, fv, dy, y_train=y_sh, feat_cols=full_cols)
    if p is None:
        return None
    m = F.metrics(p, lam)
    out.update(m)
    for f, cols in abl.items():
        pr = F.fwd_chain(X, y, w_sh, fv, dy, y_train=y_sh, feat_cols=cols)
        if pr is None:
            continue
        mr = F.metrics(pr, lam)
        out[f"dfeat_rho_{f}"] = m["rho_blend"] - mr["rho_blend"]
        out[f"dfeat_t45_{f}"] = m["t45_blend"] - mr["t45_blend"]
    return out


if __name__ == "__main__":
    allres = {}
    for side in ("hit", "pit"):
        keys, _m = E._feature_spec(side)
        lam = E.blend_lambda(side)
        for cut in ("debuted_km", "full_pool_km"):
            t = time.time()
            r = run_combo(side, cut, lam, keys)
            allres[f"{side}/{cut}"] = r
            print(f"done {side}/{cut} in {round(time.time()-t,1)}s "
                  f"(boot {r['boot_secs']}s null {r['null_secs']}s placebo {r['placebo_secs']}s)",
                  flush=True)
    outp = Path(sys.argv[3]) if len(sys.argv) > 3 else (ROOT / "tools" / "_frontier_noisefloor_out.json")
    outp.write_text(json.dumps(allres, indent=1), encoding="utf-8")
    print("wrote", outp)
