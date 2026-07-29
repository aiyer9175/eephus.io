# scratch lab (lane: discover) -- does an archetype BLOCK earn pooled rank accuracy?
#
# Strictly forward-chained: for each test year Y the cluster geometry (standardizer
# + k-means centroids) is fit on TRAIN rows only (decision_year < Y) and applied
# forward to the test rows. Outcomes are never used to define, tune or select an
# archetype. Cluster ids are matched across folds to a reference solution by
# centroid nearest-neighbour so the dummy columns mean the same thing in every fold.
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.cluster import KMeans

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _arch_discover as A                                            # noqa: E402
from _arch_theory import theory_hit, theory_pit                       # noqa: E402
from efv_model import (_decision_year, _feature_spec, _fit_ols_fv, _pred_ols,
                       _prep, _vec)                                   # noqa: E402
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration  # noqa: E402

K = {"hit": 5, "pit": 6}
CK = {"hit": A.CLUSTER_KEYS_HIT, "pit": A.CLUSTER_KEYS_PIT}


def _cf(r, side):
    return A.cfeat({"milb": r.get("milb"), "position": r.get("position"),
                    "is_college": r.get("is_college"), "is_ifa": r.get("is_ifa"),
                    **{t: r.get(t) for t in A._TOOL_D}}, side)


def reference_centroids(side, seed=7):
    rows = [r for r in A.load(side) if r.get("milb")]
    X, mu, sd = A.zmat([_cf(r, side) for r in rows], CK[side])
    km = KMeans(n_clusters=K[side], n_init=50, random_state=seed).fit(X)
    return km.cluster_centers_, mu, sd


def _match(cent, ref):
    """Greedy nearest-centroid matching of a fold solution onto the reference."""
    d = ((cent[:, None, :] - ref[None, :, :]) ** 2).sum(-1)
    out, used = {}, set()
    for i, j in sorted(((i, j) for i in range(len(cent)) for j in range(len(ref))),
                       key=lambda p: d[p[0], p[1]]):
        if i in out or j in used:
            continue
        out[i], _ = j, used.add(j)
    return out


def run(side, mode="base", years=A.TEST_YEARS, rng=None, boot_idx=None, seed=0):
    """mode: base | clu | clu_perm | arch | arch_perm"""
    rows = A.load(side)
    if boot_idx is not None:
        rows = [rows[i] for i in boot_idx]
    keys, _m = _feature_spec(side)
    ref, rmu, rsd = REF[side]
    theory = theory_hit if side == "hit" else theory_pit
    rr = np.random.default_rng(seed)

    prepped = _prep(rows, "target_censored", side)
    by_key = {}
    for r in rows:
        by_key.setdefault(r["player_key"], r)

    # extra dummy columns
    nk = K[side]
    if mode.startswith("clu"):
        extra = [f"_clu{i}" for i in range(1, nk)]
    elif mode.startswith("arch"):
        labs = sorted({theory(_cf(r, side), r.get("position")) for r in rows if r.get("milb")})
        extra = [f"_a_{l}" for l in labs[1:]]
    else:
        extra = []
    use = keys + extra

    preds, targs, tr_flag = [], [], []
    for yr in years:
        tr = [r for r in prepped if r["decision_year"] < yr]
        te = [r for r in prepped if r["decision_year"] == yr]
        if len(tr) < 80 or not te:
            continue
        # --- fold-local, TRAIN-ONLY archetype geometry ---
        assign = {}
        if mode.startswith("clu"):
            trk = [by_key[r["player_key"]] for r in tr if by_key[r["player_key"]].get("milb")]
            if len(trk) >= 40:
                Xt, mu, sd = A.zmat([_cf(r, side) for r in trk], CK[side])
                km = KMeans(n_clusters=nk, n_init=20, random_state=7).fit(Xt)
                m = _match((km.cluster_centers_ * sd + mu - rmu) / rsd, ref)
                tgt = [r for r in prepped if by_key[r["player_key"]].get("milb")]
                if tgt:
                    Xa = (np.array([[_cf(by_key[r["player_key"]], side)[k]
                                     for k in CK[side]] for r in tgt]) - mu) / sd
                    lab = ((Xa[:, None, :] - km.cluster_centers_[None, :, :]) ** 2).sum(-1).argmin(1)
                    for r, l in zip(tgt, lab):
                        assign[r["player_key"]] = m[int(l)]
        elif mode.startswith("arch"):
            for r in prepped:
                s = by_key[r["player_key"]]
                if s.get("milb"):
                    assign[r["player_key"]] = theory(_cf(s, side), s.get("position"))
        if "_perm" in mode:
            ks = [k for k in assign]
            vs = rr.permutation([assign[k] for k in ks])
            assign = dict(zip(ks, vs))

        for r in prepped:
            lab = assign.get(r["player_key"])
            for c in extra:
                r["feats"][c] = 0.0
            if lab is not None:
                col = f"_clu{lab}" if mode.startswith("clu") else f"_a_{lab}"
                if col in r["feats"]:
                    r["feats"][col] = 1.0

        fitkeys = keys if mode.endswith("_offset") else use
        ridge = _fit_ridge(tr, fitkeys)
        ols = _fit_ols_fv(tr)
        if not ridge or not ols:
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        lam = A.LAM[side]

        # PROFILE-COMP OFFSET: shrunk train-fold mean residual per archetype, added
        # to the test prediction. The most direct production form of a comp-based
        # correction. Shrinkage K=50 comps; train residuals only, never test.
        off = {}
        if mode.endswith("_offset"):
            acc = {}
            for r in tr:
                lab = assign.get(r["player_key"])
                if lab is None:
                    continue
                p = (1 - lam) * _pred_ols(ols, r["fv"]) + lam * (a + b * _predict(ridge, r["feats"]))
                acc.setdefault(lab, []).append((r["target"] - p, r["weight"]))
            for lab, v in acc.items():
                ww = sum(w for _e, w in v)
                if ww <= 0:
                    continue
                m = sum(e * w for e, w in v) / ww
                off[lab] = m * (len(v) / (len(v) + 50.0))

        for r in te:
            p = (1 - lam) * _pred_ols(ols, r["fv"]) + lam * (a + b * _predict(ridge, r["feats"]))
            p += off.get(assign.get(r["player_key"]), 0.0)
            preds.append(p)
            targs.append(r["target"])
            tr_flag.append(bool(by_key[r["player_key"]].get("milb")))
    preds, targs, tr_flag = np.array(preds), np.array(targs), np.array(tr_flag)
    if len(preds) < 50:
        return {"rho": float("nan"), "rho_tr": float("nan"), "n": len(preds)}
    return {"rho": float(spearmanr(targs, preds).statistic),
            "rho_tr": float(spearmanr(targs[tr_flag], preds[tr_flag]).statistic),
            "n": int(len(preds)), "n_tr": int(tr_flag.sum())}


REF = {}
for _s in ("hit", "pit"):
    REF[_s] = reference_centroids(_s)
