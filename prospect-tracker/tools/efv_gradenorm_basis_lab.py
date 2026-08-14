# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV GRADE-NORMALIZATION BASIS GATE (LEVER 2), pre-registered in
docs/efv-2026-07-30/ARIAS_COUNTERFACTUAL_GATE.md.

QUESTION -- does turning cross-source grade normalization OFF
(consensus.ADOPT_NORMALIZED_CONSENSUS True -> False) improve eFV out-of-sample accuracy?

HOW THE COUNTERFACTUAL IS BUILT. No file is regenerated and no production module is
edited. `consensus.build_timeseries` is a PURE function of the snapshot pool, so it is
called twice in memory on storage.load_all_snapshots() -- once with normalize=True (the
shipped basis) and once with normalize=False -- and the per-(player_key, snapshot_date)
consensus_fv_raw is harvested from both. That makes the "replication" the SHIPPED code
path rather than a re-implementation; the fidelity check below confirms the normalize=True
pass reproduces the stored matrix column.

WHY OVERWRITING consensus_fv_raw IS THE COMPLETE COUNTERFACTUAL. efv_model._feature_spec
is ['fv', ...] on both sides and contains NEITHER fv_trend NOR consensus_fv_pre_shrinkage,
so the consensus column reaches the model through exactly two channels: the `fv` ridge
feature (efv_model._vec: fv_effective or consensus_fv_raw; training rows have no
fv_effective) and the consensus OLS leg. Both are driven off the same number.

PROTOCOL -- the shipped forward-chained OOS read that tools/efv_lab_runner.py performs:
SCORED_YEARS folds, train>=50 / test>=12, blend = (1-lam)*max(0, OLS(FV)) + lam*ridge,
lam = efv_model.blend_lambda(side), target_censored, matrix sample weights. The pure
Python path (prospect_path._fit_ridge / efv_model._fit_ols_fv) produces the point
estimates; a numerically-verified numpy twin of the same fit is used for the 2000-draw
refit bootstrap and the permutation band.

ARMS
  ON        shipped normalized consensus (baseline)
  OFF       candidate: normalize=False consensus
  ZI_CTRL   zero-information control -- ON consensus row-permuted WITHIN decision-year
            strata (identical marginal per stratum, information destroyed)
  RANKID    diagnostic -- the OFF marginal placed on the ON rank order (rank-identical
            twin of ON carrying OFF's scale). Separates "the reordering carries
            information" from "the scale moved".

Run:  python tools/efv_gradenorm_basis_lab.py            # full gate -> data/xfv_gradenorm_basis_eval.json
      python tools/efv_gradenorm_basis_lab.py --smoke    # fidelity + point estimates only
      python tools/efv_gradenorm_basis_lab.py --boot 200 # smaller bootstrap
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.chdir(ROOT)

import numpy as np                                                     # noqa: E402

import efv_model as XM                                                 # noqa: E402
import efv_dataset as DS                                               # noqa: E402
import efv_lab_runner as LAB                                           # noqa: E402
from efv_model import _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda, _prep   # noqa: E402
from prospect_path import _fit_ridge, _predict, _spearman, _ALPHAS, _RIDGE_HOLDOUT_SEED  # noqa: E402

SEED = 20260730
NBOOT = 2000
NPERM = 2000
SCORED_YEARS = XM.SCORED_YEARS                       # (2020, 2021, 2022, 2023)
MULTI_SPLIT_FOLDS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
FLOOR = {"hit": 0.017, "pit": 0.016}                 # EFV_GATE_STANDARD sec.1 incremental MDE95
ARMS = ("ON", "OFF", "ZI_CTRL", "SHIFT_CTRL", "RANKID")
OUT = ROOT / "data" / "xfv_gradenorm_basis_eval.json"
DOC = ROOT / "docs" / "efv-2026-07-30" / "ARIAS_COUNTERFACTUAL_GATE.md"
CACHE = Path(os.environ.get("TEMP", "/tmp")) / "efv_gradenorm_cons_cache.json"


# ===========================================================================
# 1. the two consensus bases (shipped code, in memory, nothing written)
# ===========================================================================
def consensus_bases(use_cache: bool = True):
    """{(player_key, snapshot_date): fv} for normalize=True and normalize=False."""
    if use_cache and CACHE.exists():
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
        out = {}
        for basis in ("on", "off"):
            out[basis] = {tuple(k.split("|", 1)): v for k, v in raw[basis].items()}
        return out["on"], out["off"]
    import storage
    from consensus import build_timeseries
    snaps = storage.load_all_snapshots()
    res = {}
    for basis, norm in (("on", True), ("off", False)):
        ts = build_timeseries(snaps, normalize=norm)
        res[basis] = {(p.player_key, pt.snapshot_date): pt.consensus_fv_raw
                      for p in ts for pt in p.points}
    try:
        CACHE.write_text(json.dumps(
            {b: {f"{k[0]}|{k[1]}": v for k, v in m.items()} for b, m in res.items()}),
            encoding="utf-8")
    except OSError:
        pass
    return res["on"], res["off"]


def fidelity(c_on) -> dict:
    """The normalize=True pass must reproduce the stored consensus_fv_raw column."""
    out = {}
    for side in ("hit", "pit"):
        rows = json.loads(DS.matrix_path(side).read_text(encoding="utf-8"))
        n = ok = miss = 0
        worst = 0.0
        for r in rows:
            st = r.get("consensus_fv_raw")
            if st is None:
                continue
            n += 1
            v = c_on.get((r["player_key"], r.get("asof_date")))
            if v is None:
                miss += 1
                continue
            d = abs(float(v) - float(st))
            worst = max(worst, d)
            if d <= 0.01:
                ok += 1
        out[side] = {"n_rows": n, "n_within_0.01": ok, "frac_within_0.01": round(ok / n, 5),
                     "n_unmatched_key": miss, "max_abs_dev": round(worst, 4)}
    return out


# ===========================================================================
# 2. pools + arm columns
# ===========================================================================
def build_pool(side, c_on, c_off, pool="deb"):
    """pool='deb'  -> the efv_lab_runner primary pool (kind==debuted, canonical cohorts,
                      reproduces the shipped headline rho).
       pool='full' -> the production labeled pool (full matrix minus bust_recent busts),
                      used for the debut/no-debut AUC secondary."""
    keys = _feature_spec(side)[0]
    if pool == "deb":
        rows = [dict(r) for r in LAB.data_for(side) if r.get("target_censored") is not None]
        for r in rows:
            r["target"] = r["target_censored"]
            r["kind"] = "debuted"
    else:
        raw = json.loads(DS.matrix_path(side).read_text(encoding="utf-8"))
        raw = [r for r in raw if not (r.get("kind") == "bust" and r.get("bust_recent"))]
        prepped = _prep(raw, "target_censored", side)
        acq = LAB._load_acq()
        by_pk = {r["player_key"]: r for r in raw}
        rows = []
        for d in prepped:
            src = by_pk[d["player_key"]]
            coh = LAB._cohort_of(d["player_key"], src, acq)
            f = dict(d["feats"])
            f["is_ifa"] = 1.0 if coh == "ifa" else 0.0
            f["is_college"] = 1.0 if coh == "college" else 0.0
            f["is_hs"] = 1.0 if coh == "hs" else 0.0
            rows.append({"player_key": d["player_key"], "kind": d["kind"],
                         "decision_year": d["decision_year"], "feats": f,
                         "target": d["target"], "weight": d["weight"], "fv": d["fv"],
                         "cohort": coh})
        # asof_date lookup for the counterfactual column
        for r in rows:
            r["asof_date"] = by_pk[r["player_key"]].get("asof_date")

    # attach the as-of date on the deb pool too (LAB rows drop it)
    if pool == "deb":
        raw = json.loads(DS.matrix_path(side).read_text(encoding="utf-8"))
        adate = {r["player_key"]: r.get("asof_date") for r in raw}
        for r in rows:
            r["asof_date"] = adate.get(r["player_key"])

    keep = []
    for r in rows:
        k = (r["player_key"], r["asof_date"])
        if k not in c_on or k not in c_off:
            continue
        r["fv_on"] = float(c_on[k])
        r["fv_off"] = float(c_off[k])
        keep.append(r)
    dropped = len(rows) - len(keep)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in keep], float)
    D = {
        "side": side, "pool": pool, "keys": keys, "rows": keep, "X": X,
        "y": np.array([r["target"] for r in keep], float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in keep]), 1e-3, None),
        "dy": np.array([r["decision_year"] for r in keep], int),
        "deb": np.array([1.0 if r["kind"] == "debuted" else 0.0 for r in keep]),
        "pk": [r["player_key"] for r in keep],
        "n_dropped_no_consensus_key": dropped,
        "fv_idx": keys.index("fv"),
    }
    return D


def arm_columns(D, rng) -> dict:
    """fv vector per arm (also substituted into the ridge `fv` column)."""
    on, off, dy = (np.array([r["fv_on"] for r in D["rows"]]),
                   np.array([r["fv_off"] for r in D["rows"]]), D["dy"])
    cols = {"ON": on.copy(), "OFF": off.copy()}
    # zero-information control: ON values row-permuted WITHIN decision-year strata
    zi = on.copy()
    for yr in np.unique(dy):
        m = np.flatnonzero(dy == yr)
        zi[m] = on[m][rng.permutation(len(m))]
    cols["ZI_CTRL"] = zi
    # zero-information twin of the CHANGE ITSELF: keep ON, then add the (OFF - ON)
    # per-row shift permuted WITHIN decision-year strata. Identical shift marginal,
    # scrambled as to WHICH player receives which shift. This is the control that is
    # magnitude-comparable to the candidate; ZI_CTRL above destroys the whole column
    # and only establishes that the instrument responds at all.
    shift = off - on
    sc = on.copy()
    for yr in np.unique(dy):
        m = np.flatnonzero(dy == yr)
        sc[m] = on[m] + shift[m][rng.permutation(len(m))]
    cols["SHIFT_CTRL"] = sc
    # rank-identical twin of ON carrying the OFF marginal
    order = np.argsort(np.argsort(on, kind="mergesort"), kind="mergesort")
    cols["RANKID"] = np.sort(off)[order]
    return cols


def arm_X(D, fv_vec):
    X = D["X"].copy()
    X[:, D["fv_idx"]] = fv_vec
    return X


# ===========================================================================
# 3. numpy twin of the shipped fit (verified against prospect_path._fit_ridge)
# ===========================================================================
def ridge_fit(X, y, w):
    n = len(y)
    if n < 40:
        return None
    k = X.shape[1]
    mu, sd = X.mean(axis=0), X.std(axis=0).copy()
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd

    def _wmean(idx):
        ww = w[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())

    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], w[idx]
        WX = Xi * wi[:, None]
        A = WX.T @ Xi + alpha * np.eye(k)
        try:
            return np.linalg.solve(A, WX.T @ (y[idx] - b))
        except np.linalg.LinAlgError:
            return np.linalg.lstsq(A, WX.T @ (y[idx] - b), rcond=None)[0]

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    folds = np.array_split(order, 5)
    best = None
    for alpha in _ALPHAS:
        err = wsum = 0.0
        for i in range(len(folds)):
            ho = folds[i]
            tri = np.concatenate([folds[j] for j in range(len(folds)) if j != i])
            if len(ho) == 0 or len(tri) == 0:
                continue
            b_tr = _wmean(tri)
            pred = Xs[ho] @ _wridge(tri, alpha, b_tr) + b_tr
            ww = w[ho]
            if ww.sum() > 0:
                err += float(np.sum(np.abs(pred - y[ho]) * ww)); wsum += float(ww.sum())
            else:
                err += float(np.sum(np.abs(pred - y[ho]))); wsum += float(len(ho))
        mae = (err / wsum) if wsum > 0 else float("inf")
        if best is None or mae < best[0]:
            best = (mae, alpha)
    b = _wmean(np.arange(n))
    return (mu, sd, _wridge(np.arange(n), best[1], b), b)


def ridge_pred(m, X):
    mu, sd, w, b = m
    return ((X - mu) / sd) @ w + b


def ols_fit(fv, y):
    if len(y) < 8:
        return None
    mx, my = fv.mean(), y.mean()
    var = ((fv - mx) ** 2).sum()
    if var <= 0:
        return None
    b = ((fv - mx) * (y - my)).sum() / var
    return (my - b * mx, b)


# ===========================================================================
# 4. metrics
# ===========================================================================
def _rankv(v):
    v = np.asarray(v, float)
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v), float)
    sv = v[order]
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and sv[j + 1] == sv[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def spear(a, b):
    if len(a) < 8:
        return float("nan")
    ra, rb = _rankv(a) - (len(a) + 1) / 2.0, _rankv(b) - (len(b) + 1) / 2.0
    den = math.sqrt(float((ra ** 2).sum()) * float((rb ** 2).sum()))
    return float((ra * rb).sum() / den) if den else float("nan")


def auc(score, lab):
    lab = np.asarray(lab, float)
    if lab.sum() < 5 or (1 - lab).sum() < 5:
        return float("nan")
    r = _rankv(score)
    n1, n0 = lab.sum(), (1 - lab).sum()
    return float((r[lab == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def block_rho(pred, y, blk):
    up, uy = np.empty(len(y)), np.empty(len(y))
    for b in np.unique(blk):
        m = blk == b
        if m.sum() < 3:
            up[m] = 0.5; uy[m] = 0.5; continue
        up[m] = _rankv(pred[m]) / (m.sum() + 1.0)
        uy[m] = _rankv(y[m]) / (m.sum() + 1.0)
    return spear(up, uy)


def pct(a, q):
    if not len(a):
        return None
    s = np.sort(np.asarray(a, float))
    k = (len(s) - 1) * q
    f = int(k); c = min(f + 1, len(s) - 1)
    return float(s[f] + (s[c] - s[f]) * (k - f))


# ===========================================================================
# 5. forward chain (numpy) -- shipped efv_lab_runner protocol
# ===========================================================================
def chain(D, Xa, fv, lam, folds=SCORED_YEARS, idx=None):
    """Returns (pred, y, dy, deb) pooled over the folds. `idx` = a resample index
    array (bootstrap); None = the full pool."""
    dy, y, w = D["dy"], D["y"], D["w"]
    all_idx = np.arange(len(y)) if idx is None else idx
    P, Y, B, Db = [], [], [], []
    for yr in folds:
        itr = all_idx[dy[all_idx] < yr]
        ite = all_idx[dy[all_idx] == yr]
        if len(ite) < 12 or len(itr) < 50:
            continue
        rg = ridge_fit(Xa[itr], y[itr], w[itr])
        ol = ols_fit(fv[itr], y[itr])
        if rg is None or ol is None:
            continue
        cons = np.maximum(0.0, ol[0] + ol[1] * fv[ite])
        model = ridge_pred(rg, Xa[ite])
        P.append((1 - lam) * cons + lam * model)
        Y.append(y[ite]); B.append(np.full(len(ite), yr)); Db.append(D["deb"][ite])
    if not P:
        return None
    return tuple(np.concatenate(v) for v in (P, Y, B, Db))


def chain_py(D, fv_vec, lam, folds=SCORED_YEARS):
    """Pure-Python protocol (prospect_path._fit_ridge / efv_model._fit_ols_fv) --
    the reference the numpy twin is checked against."""
    keys = D["keys"]
    rows = D["rows"]
    pooled = []
    for yr in folds:
        tr = [(r, v) for r, v in zip(rows, fv_vec) if r["decision_year"] < yr]
        te = [(r, v) for r, v in zip(rows, fv_vec) if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": {**r["feats"], "fv": v}, "target": r["target"],
                "weight": r["weight"], "fv": v} for r, v in tr]
        ols = _fit_ols_fv([{"fv": v, "target": r["target"]} for r, v in tr])
        ridge = _fit_ridge(trf, keys)
        if not (ols and ridge):
            continue
        for r, v in te:
            cw = max(0.0, _pred_ols(ols, v))
            rp = _predict(ridge, {**r["feats"], "fv": v})
            pooled.append(((1 - lam) * cw + lam * rp, r["target"]))
    if not pooled:
        return None
    return _spearman([a for a, _ in pooled], [b for _, b in pooled]), len(pooled)


# ===========================================================================
# 6. bootstrap / permutation
# ===========================================================================
def boot_deltas(D, cols, lam, nboot=NBOOT, folds=SCORED_YEARS, arms=ARMS):
    """Paired player-clustered bootstrap resampling TRAIN AND TEST with a refit of
    ridge + consensus OLS on every draw. Every arm sees the identical resample."""
    Xs = {a: arm_X(D, cols[a]) for a in arms}
    clus = defaultdict(list)
    for i, pk in enumerate(D["pk"]):
        clus[pk].append(i)
    ckeys = list(clus)
    nc = len(ckeys)
    rng = np.random.default_rng(SEED)
    d_rho = {a: [] for a in arms if a != "ON"}
    d_auc = {a: [] for a in arms if a != "ON"}
    n_ok = 0
    for _ in range(nboot):
        pick = rng.integers(0, nc, size=nc)
        idx = np.concatenate([clus[ckeys[j]] for j in pick])
        res = {}
        for a in arms:
            r = chain(D, Xs[a], cols[a], lam, folds=folds, idx=idx)
            if r is None:
                res = None
                break
            res[a] = r
        if res is None:
            continue
        base = res["ON"]
        r0 = spear(base[0], base[1])
        a0 = auc(base[0], base[3])
        if r0 != r0:
            continue
        n_ok += 1
        for a in arms:
            if a == "ON":
                continue
            r1 = spear(res[a][0], res[a][1])
            if r1 == r1:
                d_rho[a].append(r1 - r0)
            a1 = auc(res[a][0], res[a][3])
            if a1 == a1 and a0 == a0:
                d_auc[a].append(a1 - a0)
    out = {}
    for a in d_rho:
        out[a] = {
            "n_boot": n_ok,
            "d_spearman_mean": round(float(np.mean(d_rho[a])), 5) if d_rho[a] else None,
            "d_spearman_lo95": round(pct(d_rho[a], 0.025), 5) if d_rho[a] else None,
            "d_spearman_hi95": round(pct(d_rho[a], 0.975), 5) if d_rho[a] else None,
            "d_spearman_lo90_one_sided": round(pct(d_rho[a], 0.05), 5) if d_rho[a] else None,
            "p_improves": round(float(np.mean(np.asarray(d_rho[a]) > 0)), 4) if d_rho[a] else None,
            "d_auc_mean": round(float(np.mean(d_auc[a])), 5) if d_auc[a] else None,
            "d_auc_lo95": round(pct(d_auc[a], 0.025), 5) if d_auc[a] else None,
            "d_auc_hi95": round(pct(d_auc[a], 0.975), 5) if d_auc[a] else None,
        }
    return out


def perm_band(D, cols, lam, nperm=NPERM, folds=SCORED_YEARS, observed=None):
    """Permutation null band: the OFF consensus column permuted WITHIN decision-year
    strata, full forward chain re-run per draw. Gives the null distribution of the
    same delta statistic for a column with OFF's marginal and no information."""
    X_on = arm_X(D, cols["ON"])
    base = chain(D, X_on, cols["ON"], lam, folds=folds)
    r0 = spear(base[0], base[1])
    off, dy = cols["OFF"], D["dy"]
    rng = np.random.default_rng(SEED + 1)
    ds = []
    for _ in range(nperm):
        p = off.copy()
        for yr in np.unique(dy):
            m = np.flatnonzero(dy == yr)
            p[m] = off[m][rng.permutation(len(m))]
        r = chain(D, arm_X(D, p), p, lam, folds=folds)
        if r is None:
            continue
        v = spear(r[0], r[1])
        if v == v:
            ds.append(v - r0)
    ds = np.asarray(ds, float)
    out = {"n_perm": int(len(ds)), "mean": round(float(ds.mean()), 5),
           "lo95": round(pct(ds, 0.025), 5), "hi95": round(pct(ds, 0.975), 5),
           "p95_abs": round(float(np.percentile(np.abs(ds), 95)), 5)}
    if observed is not None:
        out["observed_delta"] = round(float(observed), 5)
        out["p_two_sided"] = round(float((np.sum(np.abs(ds) >= abs(observed)) + 1)
                                        / (len(ds) + 1)), 4)
    return out


def boot_block_rho(bundles, nboot=NBOOT, folds=SCORED_YEARS, arms=ARMS):
    """Paired player-clustered bootstrap of the BOTH-SIDES-POOLED block-rho
    (blocks = side x cohort-year). Each side is resampled on its own clusters from a
    single rng stream, so ON and every arm share the identical joint resample."""
    prep = {}
    for side, (D, cols, lam) in bundles.items():
        clus = defaultdict(list)
        for i, pk in enumerate(D["pk"]):
            clus[pk].append(i)
        ck = list(clus)
        prep[side] = (D, cols, lam, {a: arm_X(D, cols[a]) for a in arms}, clus, ck)
    rng = np.random.default_rng(SEED + 2)
    d = {a: [] for a in arms if a != "ON"}
    n_ok = 0
    for _ in range(nboot):
        idxs = {}
        for side, (_D, _c, _l, _X, clus, ck) in prep.items():
            pick = rng.integers(0, len(ck), size=len(ck))
            idxs[side] = np.concatenate([clus[ck[j]] for j in pick])
        per_arm = {}
        ok = True
        for a in arms:
            P, Y, B = [], [], []
            for side, (D, cols, lam, Xs, _clus, _ck) in prep.items():
                r = chain(D, Xs[a], cols[a], lam, folds=folds, idx=idxs[side])
                if r is None:
                    ok = False
                    break
                P.append(r[0]); Y.append(r[1])
                B.append(np.array([f"{side}:{int(v)}" for v in r[2]]))
            if not ok:
                break
            per_arm[a] = block_rho(np.concatenate(P), np.concatenate(Y), np.concatenate(B))
        if not ok or per_arm["ON"] != per_arm["ON"]:
            continue
        n_ok += 1
        for a in arms:
            if a != "ON" and per_arm[a] == per_arm[a]:
                d[a].append(per_arm[a] - per_arm["ON"])
    return {a: {"n_boot": n_ok,
                "d_block_rho_mean": round(float(np.mean(v)), 5) if v else None,
                "d_block_rho_lo95": round(pct(v, 0.025), 5) if v else None,
                "d_block_rho_hi95": round(pct(v, 0.975), 5) if v else None,
                "p_improves": round(float(np.mean(np.asarray(v) > 0)), 4) if v else None}
            for a, v in d.items()}


def boot_arm_vs_arm(D, cols, lam, a1, a2, nboot=NBOOT, folds=SCORED_YEARS):
    """Paired player-clustered refit bootstrap of rho(a1) - rho(a2) directly.
    Used for the decision-relevant contrast: the candidate against its
    correctly-scaled zero-information twin (OFF vs SHIFT_CTRL)."""
    Xs = {a: arm_X(D, cols[a]) for a in (a1, a2)}
    clus = defaultdict(list)
    for i, pk in enumerate(D["pk"]):
        clus[pk].append(i)
    ck = list(clus)
    rng = np.random.default_rng(SEED + 3)
    d = []
    for _ in range(nboot):
        pick = rng.integers(0, len(ck), size=len(ck))
        idx = np.concatenate([clus[ck[j]] for j in pick])
        vals = {}
        for a in (a1, a2):
            r = chain(D, Xs[a], cols[a], lam, folds=folds, idx=idx)
            if r is None:
                vals = None
                break
            vals[a] = spear(r[0], r[1])
        if vals is None or vals[a1] != vals[a1] or vals[a2] != vals[a2]:
            continue
        d.append(vals[a1] - vals[a2])
    return {"contrast": f"{a1} minus {a2}", "n_boot": len(d),
            "d_spearman_mean": round(float(np.mean(d)), 5) if d else None,
            "d_spearman_lo95": round(pct(d, 0.025), 5) if d else None,
            "d_spearman_hi95": round(pct(d, 0.975), 5) if d else None,
            "p_candidate_better": round(float(np.mean(np.asarray(d) > 0)), 4) if d else None}


def per_split(D, cols, lam, folds=MULTI_SPLIT_FOLDS, arms=ARMS):
    """Per-fold rho for every arm, each fold fit and scored on its own (>=4 splits)."""
    Xs = {a: arm_X(D, cols[a]) for a in arms}
    out = {}
    for yr in folds:
        cell = {}
        n = None
        for a in arms:
            r = chain(D, Xs[a], cols[a], lam, folds=(yr,))
            if r is None:
                cell = None
                break
            cell[a] = spear(r[0], r[1])
            n = len(r[1])
        if not cell:
            continue
        out[str(yr)] = {"n_test": n,
                        **{a: round(cell[a], 5) for a in arms},
                        **{f"d_{a}": round(cell[a] - cell["ON"], 5)
                           for a in arms if a != "ON"}}
    return out


# ===========================================================================
# 7. Arias consensus-input effect (NOT a board rank)
# ===========================================================================
def arias_effect(c_on, c_off):
    xfv = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    live = json.loads((DS.live_matrix_path("hit")).read_text(encoding="utf-8"))
    asof = {r["player_key"]: r.get("asof_date") for r in live}
    pool = []
    for pk, row in xfv.items():
        if row.get("side") != "H" or row.get("kind") != "active":
            continue
        k = (pk, asof.get(pk))
        if k[1] is None or k not in c_on or k not in c_off:
            continue
        pool.append((pk, float(c_on[k]), float(c_off[k]), row.get("xfv_grade")))
    on = np.array([p[1] for p in pool])
    off = np.array([p[2] for p in pool])
    idx = {p[0]: i for i, p in enumerate(pool)}
    out = {"n_live_active_hitters": len(pool),
           "note": ("CONSENSUS-INPUT effect only. efv_score.run_live was NOT re-run; no "
                    "board rank is claimed. The board ranks on storage.BOARD_GRADE_FIELD "
                    "(xfv_grade), which is a blend of this consensus input and the model leg."),
           "shift_all_live_hitters": {
               "mean_off_minus_on": round(float((off - on).mean()), 3),
               "sd": round(float((off - on).std()), 3),
               "min": round(float((off - on).min()), 3),
               "max": round(float((off - on).max()), 3),
               "frac_unchanged": round(float(np.mean(np.abs(off - on) < 1e-9)), 4)},
           "players": {}}
    for pk in ("franklin_arias", "jesus_made"):
        if pk not in idx:
            out["players"][pk] = None
            continue
        i = idx[pk]
        out["players"][pk] = {
            "consensus_on": round(float(on[i]), 2), "consensus_off": round(float(off[i]), 2),
            "delta": round(float(off[i] - on[i]), 2),
            "rank_by_consensus_on": int((on > on[i]).sum() + 1),
            "rank_by_consensus_off": int((off > off[i]).sum() + 1),
            "pctile_by_consensus_on": round(float((on <= on[i]).mean() * 100), 3),
            "pctile_by_consensus_off": round(float((off <= off[i]).mean() * 100), 3),
            "served_xfv_grade": pool[i][3]}
    a, m = idx.get("franklin_arias"), idx.get("jesus_made")
    if a is not None and m is not None:
        out["arias_minus_made_consensus"] = {
            "on": round(float(on[a] - on[m]), 2), "off": round(float(off[a] - off[m]), 2),
            "gap_change": round(float((off[a] - off[m]) - (on[a] - on[m])), 3)}
    out["source_mechanics"] = arias_source_mechanics()
    return out


def arias_source_mechanics():
    """WHY the flip cannot reorder these two. grade_normalization._apply_offset is a
    per-(source, role, cycle) ADDITIVE offset applied identically to every player that
    outlet grades, so for two players with the SAME contributing source set the
    normalized consensus differs from the raw consensus by the same constant and their
    gap is invariant. Recorded per source so the claim is checkable, not asserted."""
    import storage
    from consensus import build_timeseries, SOURCE_ALIASES
    from grade_normalization import build_remapper
    ts = build_timeseries(storage.load_all_snapshots(), normalize=True)
    by = {p.player_key: p for p in ts}
    # as-of cutoff threaded 2026-08-14 with the C-4 flip, and this site was
    # INTERNALLY INCONSISTENT before it: the build_timeseries call just above runs
    # with normalize=True and therefore picks up the flip, while this remapper did
    # not. One script, two bases, silently.
    import consensus as _cons
    rm = build_remapper(aliases=SOURCE_ALIASES,
                        as_of_year=_cons.grade_norm_cutoff())
    out = {"mechanism": (
        "grade_normalization._apply_offset(fv) = clamp(fv - (mean(source_paired) - "
        "mean(fangraphs_paired))) -- a pure per-(source, role, cycle) ADDITIVE offset, "
        "order-preserving by construction. consensus is the (equal-weight, per "
        "data/source_weights.json which was reverted to empty on 2026-07-25) mean of the "
        "per-source values. Therefore two multi-source players with the IDENTICAL "
        "contributing source set have an IDENTICAL consensus shift and an INVARIANT gap: "
        "turning normalization off cannot reorder them.")}
    for pk in ("franklin_arias", "jesus_made"):
        p = by.get(pk)
        if p is None or not p.points:
            out[pk] = None
            continue
        pt = p.points[-1]
        srcs = {}
        for s, v in sorted(pt.per_source.items()):
            raw = v.get("fv_published")
            if raw is None:
                continue
            yr = int(str(v.get("snapshot_date"))[:4])
            nm = rm(raw, s, p.position, yr)
            srcs[s] = {"fv_published": raw, "normalized": round(float(nm), 2),
                       "offset": round(float(nm) - float(raw), 2),
                       "snapshot_date": v.get("snapshot_date")}
        out[pk] = {"position": p.position, "asof": pt.snapshot_date,
                   "consensus_on": pt.consensus_fv_raw,
                   "n_fv_sources": len(srcs), "per_source": srcs,
                   "shrinkage_weight": pt.shrinkage_weight}
    a, m = out.get("franklin_arias"), out.get("jesus_made")
    if a and m:
        out["same_source_set"] = sorted(a["per_source"]) == sorted(m["per_source"])
    return out


# ===========================================================================
# 8. driver
# ===========================================================================
LEVER_1 = {
    "lever": "efv_dataset._K_REL_PA 50->100 / _K_REL_BF 40->80 (reliability shrink K)",
    "status": "ALREADY ANSWERED - NOT RE-RUN",
    "source_artifact": "data/xfv_cap_sweep_eval.json",
    "cited_cell": "sides.{hit,pit}.caps.reliability_shrink_K.K_x0.5",
    "cell_meaning": ("that artifact was generated when K=100/80 was shipped, so its K_x0.5 "
                     "cell IS today's shipped K=50/40; the recorded deltas are "
                     "(K50 minus K100)"),
    "hit": {"d_spearman": 0.00052, "ci95": [-0.00277, 0.00384], "d_auc": 0.00075},
    "pit": {"d_spearman": 0.00340, "ci95": [-0.00152, 0.00862], "d_auc": 0.00021},
    "reverting_to_K100": "reverses the sign of both deltas",
    "verdict": ("NULL in both directions under docs/EFV_GATE_STANDARD.md section 1 "
                "(incremental floor 0.017 hit / 0.016 pit; even the loosest lambda-class "
                "floor is 0.0076 hit / 0.005 pit). Both CIs straddle zero. CLOSED without "
                "a re-run.")}


def merge_diagnostics(nboot=NBOOT):
    """Recompute the board-effect block + the candidate-vs-control contrast and merge
    them into an existing artifact, so the 27-minute bootstrap need not be re-run."""
    c_on, c_off = consensus_bases()
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    res["arias_consensus_input_effect"] = arias_effect(c_on, c_off)
    contrast = {}
    for side in ("hit", "pit"):
        lam = blend_lambda(side)
        D = build_pool(side, c_on, c_off, "deb")
        cols = arm_columns(D, np.random.default_rng(SEED))
        contrast[side] = boot_arm_vs_arm(D, cols, lam, "OFF", "SHIFT_CTRL", nboot=nboot)
        print(side, contrast[side])
    res["candidate_vs_scaled_control_contrast"] = {
        "what": ("the decision-relevant control read: the real re-basing (OFF) against a "
                 "RANDOM re-basing of identical magnitude (SHIFT_CTRL = ON plus the "
                 "(OFF-ON) shift permuted within decision-year strata). If the real "
                 "re-basing carries information the contrast is positive; it is not."),
        **contrast}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res["arias_consensus_input_effect"]["source_mechanics"], indent=1)[:1200])
    return 0


def main():
    t0 = time.time()
    if "--merge-diagnostics" in sys.argv:
        n = (int(sys.argv[sys.argv.index("--boot") + 1])
             if "--boot" in sys.argv else NBOOT)
        return merge_diagnostics(nboot=n)
    smoke = "--smoke" in sys.argv
    nboot = NBOOT
    if "--boot" in sys.argv:
        nboot = int(sys.argv[sys.argv.index("--boot") + 1])
    nperm = 0 if smoke else NPERM

    print("[1] building both consensus bases (shipped consensus.build_timeseries) ...")
    c_on, c_off = consensus_bases()
    fid = fidelity(c_on)
    for s, v in fid.items():
        print(f"    fidelity {s}: {v['frac_within_0.01']*100:.3f}% within 0.01 FV "
              f"({v['n_within_0.01']}/{v['n_rows']}), max dev {v['max_abs_dev']}, "
              f"unmatched {v['n_unmatched_key']}")
    if min(v["frac_within_0.01"] for v in fid.values()) < 0.99:
        print("STOP: replication fidelity below the pre-registered 99% bar.")
        return 2

    res = {
        "generated": "2026-07-30",
        "question": ("does consensus.ADOPT_NORMALIZED_CONSENSUS True->False (grade "
                     "normalization OFF) improve eFV out-of-sample accuracy?"),
        "pre_registration": "docs/efv-2026-07-30/ARIAS_COUNTERFACTUAL_GATE.md",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "seed": SEED, "n_boot": nboot, "n_perm": nperm,
        "ship_floors_pooled_spearman": FLOOR,
        "protocol": ("shipped forward-chained OOS (tools/efv_lab_runner.py): SCORED_YEARS "
                     "folds, train>=50/test>=12, blend=(1-lam)*max(0,OLS(FV))+lam*ridge, "
                     "lam=efv_model.blend_lambda(side), target_censored, matrix weights"),
        "counterfactual_construction": (
            "consensus.build_timeseries(storage.load_all_snapshots(), normalize=False) run "
            "IN MEMORY -- the shipped code path, not a re-implementation. consensus_fv_raw "
            "is then substituted into both channels it feeds: the `fv` ridge column and the "
            "consensus OLS leg. Verified complete: neither fv_trend nor "
            "consensus_fv_pre_shrinkage appears in efv_model._feature_spec on either side, "
            "so no other feature carries the consensus basis."),
        "replication_fidelity": fid,
        "arms": {
            "ON": "shipped normalized consensus (baseline)",
            "OFF": "candidate -- normalize=False consensus",
            "ZI_CTRL": ("zero-information control -- ON consensus row-permuted WITHIN "
                        "decision-year strata (marginal preserved, information destroyed)"),
            "RANKID": ("diagnostic rank-identical twin -- the OFF marginal placed on the ON "
                       "rank order (isolates reordering from scale)")},
        "lever_1_k_shrink": LEVER_1,
        "sides": {},
    }

    pooled_for_block = {}
    bundles = {}
    for side in ("hit", "pit"):
        print(f"\n[2] side={side}")
        lam = blend_lambda(side)
        D = build_pool(side, c_on, c_off, "deb")
        rng = np.random.default_rng(SEED)
        cols = arm_columns(D, rng)
        print(f"    pool n={len(D['y'])} lam={lam} dropped_no_key={D['n_dropped_no_consensus_key']}")

        # --- protocol equivalence: pure-python reference vs numpy twin -----
        py_on = chain_py(D, cols["ON"], lam)
        np_on = chain(D, arm_X(D, cols["ON"]), cols["ON"], lam)
        rho_np = spear(np_on[0], np_on[1])
        print(f"    ON pooled rho: pure-python {py_on[0]:.6f} (n={py_on[1]})  "
              f"numpy-twin {rho_np:.6f} (n={len(np_on[1])})  |d|={abs(py_on[0]-rho_np):.2e}")
        py_off = chain_py(D, cols["OFF"], lam)

        point = {}
        for a in ARMS:
            r = chain(D, arm_X(D, cols[a]), cols[a], lam)
            point[a] = {"n": int(len(r[1])), "spearman": round(spear(r[0], r[1]), 5),
                        "auc_debut_full_pool": None}
            if a == "ON":
                pooled_for_block[side] = {}
            pooled_for_block[side][a] = (r[0], r[1], r[2])
        for a in ARMS:
            if a != "ON":
                point[a]["d_spearman_point"] = round(point[a]["spearman"] - point["ON"]["spearman"], 5)

        # --- full-pool debut/no-debut AUC (secondary) ---------------------
        DF = build_pool(side, c_on, c_off, "full")
        colsF = arm_columns(DF, np.random.default_rng(SEED))
        aucs = {}
        for a in ARMS:
            r = chain(DF, arm_X(DF, colsF[a]), colsF[a], lam)
            aucs[a] = {"n": int(len(r[1])), "auc_debut": round(auc(r[0], r[3]), 5),
                       "spearman": round(spear(r[0], r[1]), 5),
                       "n_debuted": int(r[3].sum())}
        for a in ARMS:
            if a != "ON":
                aucs[a]["d_auc_point"] = round(aucs[a]["auc_debut"] - aucs["ON"]["auc_debut"], 5)
                aucs[a]["d_spearman_point"] = round(aucs[a]["spearman"] - aucs["ON"]["spearman"], 5)

        print("    point estimates (debuted pool):")
        for a in ARMS:
            print(f"      {a:9s} rho={point[a]['spearman']:+.5f}"
                  + ("" if a == "ON" else f"  d={point[a]['d_spearman_point']:+.5f}"))
        print("    full-pool AUC:")
        for a in ARMS:
            print(f"      {a:9s} auc={aucs[a]['auc_debut']:.5f}"
                  + ("" if a == "ON" else f"  d={aucs[a]['d_auc_point']:+.5f}"))

        splits = per_split(D, cols, lam)
        print("    per-split d(OFF-ON):",
              {k: v["d_OFF"] for k, v in splits.items()})

        boot = {} if smoke else boot_deltas(D, cols, lam, nboot=nboot)
        if boot:
            for a, b in boot.items():
                print(f"    boot(deb,rho) {a:11s} dRho={b['d_spearman_mean']:+.5f} "
                      f"[{b['d_spearman_lo95']:+.5f},{b['d_spearman_hi95']:+.5f}] "
                      f"P(improve)={b['p_improves']}")
        bootF = {} if smoke else boot_deltas(DF, colsF, lam, nboot=nboot)
        if bootF:
            for a, b in bootF.items():
                print(f"    boot(full,auc) {a:10s} dAUC={b['d_auc_mean']:+.5f} "
                      f"[{b['d_auc_lo95']:+.5f},{b['d_auc_hi95']:+.5f}]  "
                      f"dRho={b['d_spearman_mean']:+.5f} "
                      f"[{b['d_spearman_lo95']:+.5f},{b['d_spearman_hi95']:+.5f}]")
        perm = ({} if nperm == 0 else
                perm_band(D, cols, lam, nperm=nperm,
                          observed=point["OFF"]["spearman"] - point["ON"]["spearman"]))
        if perm:
            print(f"    perm null d: mean={perm['mean']:+.5f} "
                  f"[{perm['lo95']:+.5f},{perm['hi95']:+.5f}] p95|d|={perm['p95_abs']:.5f} "
                  f"p2sided={perm.get('p_two_sided')}")
        bundles[side] = (D, cols, lam)

        d_pt = point["OFF"]["d_spearman_point"]
        lo = (boot.get("OFF") or {}).get("d_spearman_lo95")
        clears = (d_pt >= FLOOR[side]) and (lo is not None and lo > 0)
        res["sides"][side] = {
            "lam": lam,
            "n_pool_debuted": int(len(D["y"])),
            "protocol_equivalence": {
                "pure_python_ON_rho": round(py_on[0], 6), "numpy_twin_ON_rho": round(rho_np, 6),
                "abs_diff": round(abs(py_on[0] - rho_np), 8),
                "pure_python_OFF_rho": round(py_off[0], 6),
                "note": ("the numpy fit is only used for the 2000-draw refit bootstrap and the "
                         "permutation band; every point estimate is reproduced by the shipped "
                         "pure-Python fit")},
            "point_estimates_debuted_pool": point,
            "full_pool_auc": aucs,
            "per_split_deltas": splits,
            "per_split_mean_d_OFF": (round(float(np.mean([v["d_OFF"] for v in splits.values()])), 5)
                                     if splits else None),
            "bootstrap_paired_refit": boot,
            "bootstrap_paired_refit_full_pool": bootF,
            "permutation_null": perm,
            "floor": FLOOR[side],
            "clears_ship_criterion": bool(clears),
        }

    # --- block-rho, both sides pooled --------------------------------------
    blk = {}
    for a in ARMS:
        P = np.concatenate([pooled_for_block[s][a][0] for s in ("hit", "pit")])
        Y = np.concatenate([pooled_for_block[s][a][1] for s in ("hit", "pit")])
        B = np.concatenate([np.array([f"{s}:{int(y)}" for y in pooled_for_block[s][a][2]])
                            for s in ("hit", "pit")])
        blk[a] = round(block_rho(P, Y, B), 5)
    res["block_rho_both_sides_pooled"] = {
        **blk,
        **{f"d_{a}": round(blk[a] - blk["ON"], 5) for a in ARMS if a != "ON"},
        "mde95": 0.0149, "blocks": "(side x cohort-year)",
        "bootstrap": ({} if smoke else boot_block_rho(bundles, nboot=nboot))}
    print("\n[3] block-rho (both sides pooled):", blk, "MDE95 0.0149")
    if res["block_rho_both_sides_pooled"]["bootstrap"]:
        for a, b in res["block_rho_both_sides_pooled"]["bootstrap"].items():
            print(f"    boot {a:11s} d_block_rho={b['d_block_rho_mean']:+.5f} "
                  f"[{b['d_block_rho_lo95']:+.5f},{b['d_block_rho_hi95']:+.5f}]")

    res["arias_consensus_input_effect"] = arias_effect(c_on, c_off)
    print("[4] Arias consensus-input effect:",
          json.dumps(res["arias_consensus_input_effect"]["players"], indent=1))

    hit_ok = res["sides"]["hit"]["clears_ship_criterion"]
    pit_ok = res["sides"]["pit"]["clears_ship_criterion"]
    res["verdict"] = {
        "ship": bool(hit_ok and pit_ok),
        "label": "SHIP" if (hit_ok and pit_ok) else "NULL / NO-SHIP",
        "hit_clears": bool(hit_ok), "pit_clears": bool(pit_ok),
    }
    res["runtime_sec"] = round(time.time() - t0, 1)
    if not smoke:
        OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(f"\nwrote {OUT}  ({res['runtime_sec']}s)")
    print("VERDICT:", res["verdict"]["label"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
