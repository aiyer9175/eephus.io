# eFV RANK-OBJECTIVE lab (LANE I1 + I2 + I3, 2026-08-07b).
#
# WHY THIS FILE EXISTS. The eFV rank frontier is CLOSED for FEATURE COMPOSITION
# (EFV_GATE_STANDARD.md section 6). Three mechanisms sit OUTSIDE that ledger and have
# never been measured:
#
#   I1  the FIT TARGET the ridge minimizes squared error on (raw WAR today)
#   I2  a classifier fit DIRECTLY to the contributor / star AUC bars (nothing is)
#   I3  the FIT SAMPLE WEIGHTS (observed_seasons/6 today, never compared)
#
# None of them adds or removes a feature. All three are loss-function or weighting
# changes.
#
# REGISTRATION: docs/efv-2026-08-07b/RANK_AUC_GATE.md, parts 0-6, written in full BEFORE
# this file existed. Part 7 is a placeholder filled after the run. Read it first.
#
# THE TRAP THIS LANE IS BUILT AGAINST. The expected outcome is NULL on all three, and a
# lane whose product is null verdicts is exactly the lane where an over-wide control band
# manufactures a clean sweep. So every control band here is reported at three widths, the
# floors are derived per arm from the arm's own paired bootstrap on its own rows (never
# borrowed: XFV_VS_CONSENSUS_MDE95 = 0.044 is a model-vs-consensus REFIT floor and is not
# a floor for an arm-vs-production paired delta), and both registered estimators are run.
#
# Primitives (ridge_fit / ridge_pred / ols_fit / wrho / block_norm) are IMPORTED from
# tools/efv_mde_lab.py, never reimplemented, so every number here is comparable to
# data/xfv_mde_floor.json, data/xfv_cohort_floors.json and data/xfv_power_eval.json.
#
# WRITES: data/xfv_rank_objective_eval.json ONLY. Touches no production module, no
# served artifact, and no database.
#
# Run: python tools/efv_rank_objective_lab.py parity        replica parity, no writes
#      python tools/efv_rank_objective_lab.py carveout      I2 admissibility + censoring
#      python tools/efv_rank_objective_lab.py rank [B]      I1 + I3 rank battery
#      python tools/efv_rank_objective_lab.py auc [B]       I2 battery
#      python tools/efv_rank_objective_lab.py live          live-robustness clause
#      python tools/efv_rank_objective_lab.py all [B]       everything + write the ledger
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
# WINDOWS/ANACONDA STABILITY PINS. The paired bootstrap runs about 1e6 tiny BLAS calls
# per cell. Without these, three separate runs died with a native access violation at
# three different sites (numpy fancy-index assignment, then MKL gemm inside
# efv_mde_lab._wridge), which is the classic duplicate-OpenMP-runtime signature on
# anaconda for Windows. Forcing MKL's sequential threading layer removes the second
# runtime. They affect SPEED and PROCESS SURVIVAL only: every arithmetic result is
# identical, which the `parity` mode re-verifies against the shipped primitives on
# every run.
os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np   # noqa: E402  after the thread pins, as in efv_mde_lab.py

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                                                    # noqa: E402
from efv_mde_lab import ridge_fit, ridge_pred, ols_fit                    # noqa: E402
import efv_mde_lab as M                                                   # noqa: E402
from prospect_path import _ALPHAS, _RIDGE_HOLDOUT_SEED                    # noqa: E402


# --------------------------------------------------------------------------- ranks
def rankavg(v):
    """Average ranks with ties shared, FULLY VECTORIZED.

    WHY THIS EXISTS AND WHY IT IS NOT A DEVIATION. `efv_mde_lab._rankavg` walks tie
    groups in a Python while-loop and assigns each group with a fancy-index slice.
    Called about 1e5 times per arm inside the paired bootstrap, that path raised a
    Windows access violation (numpy fancy-index assignment) and killed four consecutive
    runs; the faulthandler traceback lands on efv_mde_lab.py:149. This is the same
    function computed without the Python loop, and `parity` checks it is EXACTLY equal
    to the shipped one (max abs diff 0.0) on the real scored vectors of every pool,
    including the heavily tied target with its 1,041 zeros. Every rho in this lab is
    therefore still the shipped primitive's number.
    """
    v = np.asarray(v, dtype=float)
    n = len(v)
    order = v.argsort(kind="mergesort")
    s = v[order]
    bnd = np.flatnonzero(np.concatenate(([True], s[1:] != s[:-1], [True])))
    avg = (bnd[:-1] + bnd[1:] - 1) / 2.0 + 1.0
    grp = np.repeat(np.arange(len(bnd) - 1), np.diff(bnd))
    r = np.empty(n, dtype=float)
    r[order] = avg[grp]
    return r


def wrho(p, t, w=None):
    """Pair-weighted Spearman, UNROUNDED. Identical to efv_mde_lab.wrho except that it
    ranks through `rankavg` above (see its docstring)."""
    if len(p) < 8:
        return float("nan")
    rp, rt = rankavg(p), rankavg(t)
    if w is None:
        w = np.ones(len(p))
    sw = float(np.sum(w))
    if sw <= 0:
        return float("nan")
    mx = float(np.sum(w * rp)) / sw
    my = float(np.sum(w * rt)) / sw
    a, b = rp - mx, rt - my
    cov = float(np.sum(w * a * b))
    vx = float(np.sum(w * a * a))
    vy = float(np.sum(w * b * b))
    if vx <= 0 or vy <= 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def block_norm(yr, v):
    """Percentile position inside each cohort-year block, on [0, 1]. Same as
    efv_mde_lab.block_norm, ranking through `rankavg`."""
    out = np.empty(len(v), dtype=float)
    for u in np.unique(yr):
        m = yr == u
        out[m] = (rankavg(v[m]) - 0.5) / int(m.sum())
    return out

DATA = ROOT / "data"
OUT_PATH = DATA / "xfv_rank_objective_eval.json"

SEED = 20260807
SIDES = ("hit", "pit")
POOLS = ("full", "debuted")          # full = PRIMARY (registration section 1)
Z95_ONE = 1.645
Z95_TWO = 1.96
K_PRIMARY = 10                       # 5 rank arms x 2 sides, primary pool
Z_BONF_PRIMARY = 2.5758              # one-sided alpha 0.05/10
K_ALL = 20
Z_BONF_ALL = 2.7344                  # one-sided alpha 0.05/20
N_CTRL = 200                         # control-band draws (registration section 3.2)
WARP_KNOTS = (5, 20, 50)             # band reported at three widths; 20 is primary
IPCW_CAP = 5.0                       # mirrors efv_model._SF_IPCW_CAP
CONTRIB_WAR = E._CONTRIB_WAR
STAR_WAR = E._STAR_WAR

# Self-added thresholds. Declared in RANK_AUC_GATE.md section 4.3.
LIVE_RHO_MIN = 0.999
LIVE_MAX_SHIFT = 100
FOLD_MAJORITY = 6                    # strictly more than this many of 11
CARVEOUT_AUC_BAND = (0.45, 0.55)
CARVEOUT_RATE_RATIO_MAX = 2.0
PERM_AUC_BAND = (0.45, 0.55)


# ===================================================================== pools
def load_pool(side: str, pool: str = "full") -> dict:
    """One eFV eval pool as numpy arrays.

    Same construction as tools/efv_cohort_floor_lab.load_pool (which matches
    efv_model.run()), plus the three columns this lane needs and that _prep drops:
    `cens` (censored flag), `obs` (observed_seasons) and `pk` (player_key). They are
    recovered by joining the raw matrix rows on player_key, which is unique per matrix.
    """
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    if pool == "full":
        rows = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
    else:
        rows = [r for r in raw if r["kind"] == "debuted"]
    by_key = {r["player_key"]: r for r in rows}
    prep = E._prep(rows, "target_censored", side)
    keys, mono = E._feature_spec(side)
    pk = [r["player_key"] for r in prep]
    return {
        "side": side, "pool": pool, "keys": list(keys), "mono": mono,
        "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "deb": np.array([r["kind"] == "debuted" for r in prep], dtype=bool),
        "cens": np.array([bool(by_key[k].get("censored")) for k in pk], dtype=bool),
        # "no pre-decision MiLB production block", measured from the RAW row exactly
        # the way efv_model._vec:1171 decides it. Measured on BOTH sides regardless of
        # whether `milb_missing` is in that side's feature spec: a carve-out check that
        # read the feature list would inspect an empty set on the pitcher side and
        # report a pass that could not have failed.
        "nomilb": np.array([0.0 if by_key[k].get("milb") else 1.0 for k in pk],
                           dtype=float),
        "obs": np.array([float(by_key[k].get("observed_seasons") or 0.0) for k in pk],
                        dtype=float),
        "yres": np.array([(by_key[k].get("target_resolved")
                           if by_key[k].get("target_resolved") is not None else np.nan)
                          for k in pk], dtype=float),
        "pk": pk,
        "lam": E.blend_lambda(side),
        "n": len(prep),
    }


# ===================================================================== arms
def tf_identity(y):
    return y.copy()


def tf_signed_log1p(y):
    """Strictly monotone on all of R and equal to log1p on y >= 0.

    Plain log1p is UNDEFINED on this target: it goes to -5.20 (hit) / -5.34 (pit), and
    log1p(max(0, y)) would map every negative row to the same value, making it a
    rank-DESTROYING transform rather than the rank-identical relabel the arm is about.
    """
    return np.sign(y) * np.log1p(np.abs(y))


def _rank_u(y):
    """(rank - 0.5) / n with ties averaged, on (0, 1)."""
    return (rankavg(y) - 0.5) / len(y)


_ACK_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
          1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_ACK_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01)
_ACK_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
          -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_ACK_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00)


def _norm_ppf(u):
    """Phi^-1, Acklam's rational approximation, FULLY VECTORIZED.

    IMPLEMENTATION NOTE, and it is a performance fix rather than a statistical one.
    The first version of this function solved erf(x/sqrt2) = 2u - 1 by Newton with a
    scalar `math.erf` inside a Python list comprehension, 60 iterations deep. Called
    once per fold per bootstrap draw that is about 2e9 scalar erf calls per arm, which
    is why the first attempt at the rank battery did not finish. The transform it
    defines is identical to within 1.2e-9 absolute (verified in `parity`), and the
    rank_normal target is a MONOTONE relabel, so a perturbation at that scale cannot reorder
    anything the ridge sees. No scipy dependency, deterministic everywhere.
    """
    u = np.clip(np.asarray(u, dtype=float), 1e-16, 1 - 1e-16)
    lo, hi = 0.02425, 1 - 0.02425
    x = np.empty_like(u)
    m = u < lo
    if m.any():
        q = np.sqrt(-2 * np.log(u[m]))
        x[m] = ((((((_ACK_C[0] * q + _ACK_C[1]) * q + _ACK_C[2]) * q + _ACK_C[3]) * q
                  + _ACK_C[4]) * q + _ACK_C[5])
                / ((((_ACK_D[0] * q + _ACK_D[1]) * q + _ACK_D[2]) * q + _ACK_D[3]) * q + 1))
    m = u > hi
    if m.any():
        q = np.sqrt(-2 * np.log1p(-u[m]))
        x[m] = -((((((_ACK_C[0] * q + _ACK_C[1]) * q + _ACK_C[2]) * q + _ACK_C[3]) * q
                   + _ACK_C[4]) * q + _ACK_C[5])
                 / ((((_ACK_D[0] * q + _ACK_D[1]) * q + _ACK_D[2]) * q + _ACK_D[3]) * q + 1))
    m = (u >= lo) & (u <= hi)
    if m.any():
        q = u[m] - 0.5
        r = q * q
        x[m] = ((((((_ACK_A[0] * r + _ACK_A[1]) * r + _ACK_A[2]) * r + _ACK_A[3]) * r
                  + _ACK_A[4]) * r + _ACK_A[5]) * q
                / (((((_ACK_B[0] * r + _ACK_B[1]) * r + _ACK_B[2]) * r + _ACK_B[3]) * r
                    + _ACK_B[4]) * r + 1))
    return x


def _norm_ppf_newton(u):
    """The slow reference implementation, kept ONLY so `parity` can check the fast one
    against it. Never called on the hot path."""
    u = np.clip(np.asarray(u, dtype=float), 1e-12, 1 - 1e-12)
    t = 2.0 * u - 1.0
    x = np.zeros_like(t)
    for _ in range(80):
        f = np.array([math.erf(v) for v in x]) - t
        d = (2.0 / math.sqrt(math.pi)) * np.exp(-x * x)
        x = x - f / np.maximum(d, 1e-300)
    return x * math.sqrt(2.0)


def tf_rank_normal(y):
    """van der Waerden scores on the TRAIN fold."""
    return _norm_ppf(_rank_u(y))


def make_warp(seed: int, knots: int):
    """A RANDOM strictly monotone relabel of the train target, centred on IDENTITY.

    Construction: warp the quantile scale with Dirichlet(1) increments over `knots`
    equal knots, piecewise-linear between them, then map back through the TRAIN target's
    own empirical quantile function. At the Dirichlet MEAN the increments are uniform,
    the warp is the identity map on the quantile scale, and g(y) == y exactly. So the
    identity is the centre of the family and the band measures what an ARBITRARY smooth
    rank-identical relabel does to pooled rho.
    """
    def _tf(y):
        rng = np.random.default_rng(seed)
        u = _rank_u(y)
        inc = rng.dirichlet(np.ones(knots))
        h = np.concatenate([[0.0], np.cumsum(inc)])
        t = np.linspace(0.0, 1.0, knots + 1)
        v = np.interp(u, t, h)
        ys = np.sort(y)
        # empirical quantile function of the train target at the warped quantile
        pos = np.clip(v * (len(ys) - 1), 0, len(ys) - 1)
        lo = np.floor(pos).astype(int)
        hi = np.minimum(lo + 1, len(ys) - 1)
        fr = pos - lo
        return ys[lo] * (1 - fr) + ys[hi] * fr
    return _tf


def wf_production(D, tr):
    return np.arange(len(tr)), D["w"][tr]


def wf_uniform(D, tr):
    return np.arange(len(tr)), np.ones(len(tr))


def wf_sqrt(D, tr):
    return np.arange(len(tr)), np.sqrt(D["w"][tr])


def wf_ipcw(D, tr):
    """Resolved rows only, 1 / P(resolved) capped at IPCW_CAP.

    P(resolved) is estimated INSIDE THE TRAIN FOLD in (decision-year, nearest-5 FV)
    cells with a (decision-year) fallback below 5 rows, mirroring
    efv_model._sf_ipcw_weights. Estimating it on the train fold only keeps the forward
    chain clean: no test-fold censoring information enters the fit.
    """
    cens, fv, dy = D["cens"][tr], D["fv"][tr], D["dy"][tr]
    cell_n, cell_r, coarse_n, coarse_r = {}, {}, {}, {}
    for i in range(len(tr)):
        k = (int(dy[i]), int(round(fv[i] / 5) * 5))
        cell_n[k] = cell_n.get(k, 0) + 1
        cell_r[k] = cell_r.get(k, 0) + (0 if cens[i] else 1)
        c = int(dy[i])
        coarse_n[c] = coarse_n.get(c, 0) + 1
        coarse_r[c] = coarse_r.get(c, 0) + (0 if cens[i] else 1)
    keep, wts = [], []
    for i in range(len(tr)):
        if cens[i]:
            continue
        k = (int(dy[i]), int(round(fv[i] / 5) * 5))
        n, nr = (cell_n[k], cell_r[k]) if cell_n[k] >= 5 else (coarse_n[int(dy[i])],
                                                               coarse_r[int(dy[i])])
        p = (nr / n) if n else 1.0
        keep.append(i)
        wts.append(min(IPCW_CAP, 1.0 / p) if p > 0 else IPCW_CAP)
    if len(keep) < 60:
        return None, None
    return np.array(keep, dtype=int), np.array(wts, dtype=float)


def make_wf_permuted(seed: int):
    """Production weight marginal, row link destroyed. Permuted ONCE over the whole
    pool per draw, so a row carries the same wrong weight in every fold it trains in."""
    def _wf(D, tr):
        rng = np.random.default_rng(seed)
        perm = rng.permutation(D["n"])
        return np.arange(len(tr)), D["w"][perm][tr]
    return _wf


ARM_PROD = {"id": "production", "tf": tf_identity, "wf": wf_production, "recal": False,
            "noise": 0}


def arm(aid, tf=tf_identity, wf=wf_production, recal=True, noise=0, zero_feat=None):
    return {"id": aid, "tf": tf, "wf": wf, "recal": recal, "noise": noise,
            "zero_feat": zero_feat}


# ===================================================================== chain
def chain_pair(D, arm_a, arm_b, sel=None, years=None, min_test=15, min_train=60,
               noise_cols=None):
    """Forward-chain TWO arms in ONE fold loop so their scored rows always align.

    The consensus leg is identical in both (an OLS on fv), so a delta between the two
    legs is entirely the ridge fit. Returns pooled arrays plus the per-fold fits, which
    is what the conditional estimator needs.
    """
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"]
    if sel is None:
        sel = np.arange(D["n"])
    X, y, w, fv, dy = D["X"][sel], D["y"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    Dl = {"n": len(sel), "w": w, "cens": D["cens"][sel], "fv": fv, "dy": dy}
    out = {"cons": [], "y": [], "w": [], "yr": []}
    for tag in ("a", "b"):
        out["blend_" + tag] = []
        out["ridge_" + tag] = []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < min_test or len(tr) < min_train:
            continue
        o = ols_fit(fv[tr], y[tr])
        if o is None:
            continue
        legs = {}
        ok = True
        for tag, a in (("a", arm_a), ("b", arm_b)):
            sub, wf = a["wf"](Dl, tr)
            if sub is None:
                ok = False
                break
            idx = tr[sub]
            Xtr, ytr = X[idx], y[idx]
            Xte = X[te]
            if a.get("zero_feat") is not None:
                # Blank one feature column in BOTH train and test. ridge_fit sets sd = 1
                # for a zero-variance column and its standardized values are then all 0,
                # so the column contributes exactly nothing: equivalent to deleting it,
                # without changing the matrix shape or the alpha grid.
                Xtr, Xte = Xtr.copy(), Xte.copy()
                Xtr[:, a["zero_feat"]] = 0.0
                Xte[:, a["zero_feat"]] = 0.0
            if a.get("noise"):
                nc = noise_cols[a["noise"]]
                Xtr = np.hstack([Xtr, nc[sel][idx][:, None]])
                Xte = np.hstack([Xte, nc[sel][te][:, None]])
            g = a["tf"](ytr)
            rg = ridge_fit(Xtr, g, wf)
            if rg is None:
                ok = False
                break
            ptr = ridge_pred(rg, Xtr)
            if a["recal"]:
                cal = E._fit_linear_calibration(list(zip(ptr.tolist(), ytr.tolist())))
                ca, cb = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            else:
                ca, cb = 0.0, 1.0
            legs[tag] = ca + cb * ridge_pred(rg, Xte)
        if not ok:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        out["cons"].append(cons)
        out["y"].append(y[te])
        out["w"].append(w[te])
        out["yr"].append(np.full(len(te), yr))
        for tag in ("a", "b"):
            out["ridge_" + tag].append(legs[tag])
            out["blend_" + tag].append((1 - lam) * cons + lam * legs[tag])
    if not out["cons"]:
        return None
    return {k: np.concatenate(v) for k, v in out.items()}


def deltas(r, idx=None):
    """(arm b) minus (arm a) on pooled pair-weighted rho and side block-rho, both legs."""
    if r is None:
        return {k: float("nan") for k in ("blend_rho", "ridge_rho", "blend_block",
                                          "ridge_block")}
    sl = slice(None) if idx is None else idx
    y, w, yr = r["y"][sl], r["w"][sl], r["yr"][sl]
    if len(y) < 8:
        return {k: float("nan") for k in ("blend_rho", "ridge_rho", "blend_block",
                                          "ridge_block")}
    bt = block_norm(yr, y)
    out = {}
    for leg in ("blend", "ridge"):
        a, b = r[leg + "_a"][sl], r[leg + "_b"][sl]
        out[leg + "_rho"] = wrho(b, y, w) - wrho(a, y, w)
        out[leg + "_block"] = (wrho(block_norm(yr, b), bt, w)
                               - wrho(block_norm(yr, a), bt, w))
    return out


def legs_of(r):
    y, w, yr = r["y"], r["w"], r["yr"]
    bt = block_norm(yr, y)
    out = {"n": int(len(y)),
           "consensus_rho": round(wrho(r["cons"], y, w), 5),
           "consensus_block": round(wrho(block_norm(yr, r["cons"]), bt, w), 5)}
    for tag in ("a", "b"):
        for leg in ("blend", "ridge"):
            out[f"{leg}_{tag}_rho"] = round(wrho(r[f"{leg}_{tag}"], y, w), 5)
    return out


def fold_deltas(r):
    out = {}
    for u in sorted(set(int(v) for v in r["yr"])):
        m = r["yr"] == u
        if int(m.sum()) < 12:
            continue
        d = (wrho(r["blend_b"][m], r["y"][m], r["w"][m])
             - wrho(r["blend_a"][m], r["y"][m], r["w"][m]))
        out[int(u)] = round(float(d), 5)
    return out


def summarize(draws, point, key="MDE95"):
    a = np.asarray(draws, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 20:
        return {"B_used": int(len(a)), "point": round(float(point), 5), "sd": None,
                key: None, "verdict": "UNMEASURABLE"}
    sd = float(a.std(ddof=1))
    fl = Z95_ONE * sd
    return {
        "B_used": int(len(a)),
        "point": round(float(point), 5),
        "boot_mean": round(float(a.mean()), 5),
        "sd": round(sd, 5),
        key: round(fl, 5),
        "mde95_twosided": round(Z95_TWO * sd, 5),
        "ci95": [round(float(np.percentile(a, 2.5)), 5),
                 round(float(np.percentile(a, 97.5)), 5)],
        "p_gt_0": round(float((a > 0).mean()), 4),
        "x_floor": round(abs(float(point)) / fl, 3) if fl > 0 else None,
        "resolvable": bool(abs(float(point)) >= fl),
        "mde95_bonferroni_k10": round(Z_BONF_PRIMARY * sd, 5),
        "resolvable_bonferroni_k10": bool(abs(float(point)) >= Z_BONF_PRIMARY * sd),
        "verdict": ("RESOLVABLE " + ("WIN" if point > 0 else "LOSS")
                    if abs(float(point)) >= fl else "NULL"),
    }


# ===================================================================== rank battery
def gate_arm(D, arm_a, arm_b, B, rng, noise_cols=None, tag=""):
    """Full section-2 battery for one arm against one baseline, both estimators."""
    t0 = time.time()
    r = chain_pair(D, arm_a, arm_b, noise_cols=noise_cols)
    if r is None:
        return {"tag": tag, "error": "no fold survived"}
    pt = deltas(r)
    n = len(r["y"])

    ref = {k: [] for k in pt}
    for _ in range(B):
        sel = rng.integers(0, D["n"], D["n"])
        rb = chain_pair(D, arm_a, arm_b, sel=sel, noise_cols=noise_cols)
        d = deltas(rb)
        for k in ref:
            ref[k].append(d[k])
    cnd = {k: [] for k in pt}
    for _ in range(B):
        idx = rng.integers(0, n, n)
        d = deltas(r, idx)
        for k in cnd:
            cnd[k].append(d[k])

    fd = fold_deltas(r)
    wins = sum(1 for v in fd.values() if v > 0)
    out = {
        "tag": tag, "n_pool": D["n"], "n_scored": n,
        "legs": legs_of(r),
        "point": {k: round(float(v), 5) for k, v in pt.items()},
        "folds_scored": len(fd), "fold_wins": wins,
        "fold_delta": fd,
        "fold_mean_delta": round(float(np.mean(list(fd.values()))), 5) if fd else None,
        "E_refit": {k: summarize(ref[k], pt[k]) for k in sorted(pt)},
        "E_cond": {k: summarize(cnd[k], pt[k]) for k in sorted(pt)},
        "elapsed_s": round(time.time() - t0, 1),
    }
    return out


def control_band(D, arm_a, make_arm, n_draws, label, noise_cols=None):
    """K-draw zero-information band for one arm family.

    `make_arm(seed)` returns a zero-information twin. The band is the distribution of
    the blend-leg pooled-rho delta against the SAME baseline the real arms are gated
    against, so the two numbers are directly comparable.
    """
    vals, vals_ridge, vals_block = [], [], []
    for s in range(n_draws):
        r = chain_pair(D, arm_a, make_arm(SEED + 400_000 + s), noise_cols=noise_cols)
        if r is None:
            continue
        d = deltas(r)
        if np.isfinite(d["blend_rho"]):
            vals.append(d["blend_rho"])
            vals_ridge.append(d["ridge_rho"])
            vals_block.append(d["blend_block"])
    a = np.asarray(vals, dtype=float)
    if len(a) < 10:
        return {"label": label, "draws": int(len(a)), "error": "band did not populate"}
    return {
        "label": label, "draws": int(len(a)),
        "mean": round(float(a.mean()), 5),
        "sd": round(float(a.std(ddof=1)), 5),
        "p05": round(float(np.percentile(a, 5)), 5),
        "p95": round(float(np.percentile(a, 95)), 5),
        "max_abs": round(float(np.abs(a).max()), 5),
        "ridge_leg_p95": round(float(np.percentile(vals_ridge, 95)), 5),
        "block_p95": round(float(np.percentile(vals_block, 95)), 5),
    }


def rank_battery(B: int = 2000, verbose: bool = True, only_side=None, only_pool=None,
                 out_path=None):
    """`only_side` / `only_pool` exist ONLY so the battery can be run as four separate
    processes and merged. They change no number: each (side, pool) cell is completely
    independent, uses its own `np.random.default_rng(SEED)` stream inside `gate_arm`'s
    caller, and the merge is verified by re-running one cell end to end. They were added
    because a single 20-minute process segfaulted in the BLAS layer partway through."""
    out = {"protocol": {
        "primary_pool": "full", "secondary_pool": "debuted",
        "primary_leg": "blend", "secondary_leg": "ridge",
        "B": int(B), "seed": SEED, "control_draws": N_CTRL,
        "scoring_weight": "production observed_seasons/6, NEVER changed by any arm",
        "i1_blend_baseline": "recal_identity (T0); delta vs raw production also reported",
        "i3_baseline": "production (identity target, no recal, observed_seasons/6)",
    }, "cells": {}, "control_bands": {}, "plumbing": {}}
    for si, side in enumerate(SIDES):
        if only_side and side != only_side:
            continue
        for pi, pool in enumerate(POOLS):
            if only_pool and pool != only_pool:
                continue
            # Per-CELL seed, not one shared stream. This is what makes the split run
            # byte-identical to a single-process run: every cell draws from
            # default_rng(SEED + 100*side_index + 10*pool_index) regardless of which
            # other cells ran in the same process.
            rng = np.random.default_rng(SEED + 100 * si + 10 * pi)
            D = load_pool(side, pool)
            noise_cols = {}
            for s in range(1, 6):
                noise_cols[s] = np.random.default_rng(SEED + 900 + s).standard_normal(D["n"])
            key0 = f"{side}.{pool}"
            if verbose:
                print(f"\n=== {key0}  n={D['n']} lam={D['lam']} ===", flush=True)

            t0_arm = arm("recal_identity", tf_identity, wf_production, recal=True)

            # PLUMBING CHECK (not a control): the recal leg must leave the RIDGE leg's
            # rank untouched. A positive affine map cannot reorder anything, so a
            # nonzero ridge-leg delta here would mean the harness itself moves rho.
            rp = chain_pair(D, ARM_PROD, t0_arm)
            dp = deltas(rp)
            out["plumbing"][key0] = {
                "recal_identity_vs_production": {
                    "ridge_rho_delta": round(float(dp["ridge_rho"]), 8),
                    "blend_rho_delta": round(float(dp["blend_rho"]), 5),
                    "ridge_delta_is_exactly_zero": bool(abs(dp["ridge_rho"]) < 1e-12),
                    "reading": ("the ridge-leg delta MUST be exactly 0 (an affine map "
                                "cannot reorder). The blend-leg delta is the cost of "
                                "putting the ridge on the WAR scale, which is why T0 "
                                "and not raw production is the I1 blend baseline."),
                },
            }

            arms = [
                ("I1.signed_log1p", t0_arm, arm("signed_log1p", tf_signed_log1p,
                                                wf_production, recal=True)),
                ("I1.rank_normal", t0_arm, arm("rank_normal", tf_rank_normal,
                                               wf_production, recal=True)),
                ("I3.uniform", ARM_PROD, arm("uniform", tf_identity, wf_uniform,
                                             recal=False)),
                ("I3.sqrt", ARM_PROD, arm("sqrt", tf_identity, wf_sqrt, recal=False)),
                ("I3.ipcw", ARM_PROD, arm("ipcw", tf_identity, wf_ipcw, recal=False)),
            ]
            for aid, base, cand in arms:
                g = gate_arm(D, base, cand, B, rng, tag=f"{key0}.{aid}")
                out["cells"][f"{key0}.{aid}"] = g
                if verbose and "error" not in g:
                    er = g["E_refit"]["blend_rho"]
                    ec = g["E_cond"]["blend_rho"]
                    print(f"  {aid:<18} blend d {g['point']['blend_rho']:+.5f} "
                          f"ridge d {g['point']['ridge_rho']:+.5f} "
                          f"folds {g['fold_wins']}/{g['folds_scored']} | "
                          f"refit {er['MDE95']} ({er['x_floor']}x) {er['verdict']} | "
                          f"cond {ec['MDE95']} ({ec['x_floor']}x) {ec['verdict']}",
                          flush=True)

            # ---- control bands
            bands = {}
            for kn in WARP_KNOTS:
                bands[f"I1.monotone_warp_k{kn}"] = control_band(
                    D, t0_arm,
                    lambda s, kn=kn: arm(f"warp{kn}", make_warp(s, kn), wf_production,
                                         recal=True),
                    N_CTRL, f"random monotone relabel of the train target, {kn} knots")
            bands["I3.weight_permuted"] = control_band(
                D, ARM_PROD,
                lambda s: arm("wperm", tf_identity, make_wf_permuted(s), recal=False),
                N_CTRL, "production weight marginal, row link destroyed")
            noise_vals = []
            for s in range(1, 6):
                rr = chain_pair(D, ARM_PROD, arm(f"noise{s}", tf_identity, wf_production,
                                                 recal=False, noise=s),
                                noise_cols=noise_cols)
                if rr is not None:
                    noise_vals.append(deltas(rr)["blend_rho"])
            bands["shared.noise_column"] = {
                "label": "five pure-noise N(0,1) columns appended to the ridge",
                "draws": len(noise_vals),
                "deltas": [round(float(v), 5) for v in noise_vals],
                "max_abs": round(float(np.abs(noise_vals).max()), 5) if noise_vals else None,
            }
            out["control_bands"][key0] = bands
            if verbose:
                for bk in sorted(bands):
                    b = bands[bk]
                    if "p95" in b:
                        print(f"  BAND {bk:<28} p95 {b['p95']:+.5f} p05 {b['p05']:+.5f} "
                              f"sd {b['sd']:.5f}", flush=True)
                    else:
                        print(f"  BAND {bk:<28} {b.get('deltas')}", flush=True)
    if out_path:
        Path(out_path).write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", out_path, flush=True)
    return out


def detect_control(B: int = 2000, verbose: bool = True):
    """THE CONTROL THAT WOULD EMBARRASS THIS LANE, and the reason it is here.

    This lane's product is twenty NULL verdicts. A harness that cannot fire at all would
    produce exactly the same twenty nulls and would be worthless. So the same `gate_arm`
    battery, at the same B, on the same pools, is pointed at a change that IS known to be
    resolvable: blanking `fv`, the one feature `EFV_GATE_STANDARD.md` section 6 says is
    individually resolvable, and the cell `docs/efv-2026-08-07b/POWER_GATE.md` 3.1 uses as
    its amended detection primary.

    Expected direction is a resolvable LOSS on the RIDGE leg: removing a real feature
    should hurt. If it does not fire, every null in this lane is uninformative and must be
    read that way.

    The blend leg is reported too and is expected to be MUTED, because the blend keeps
    `fv` at weight (1 - lambda) through the consensus OLS anchor no matter what the ridge
    does. That is the same mis-specification POWER_GATE.md 3.1 documents, and it is
    included rather than hidden so the two legs can be compared.
    """
    if verbose:
        print(f"=== DETECTION CONTROL: blank `fv` in the ridge (B={B}) ===", flush=True)
    out = {"purpose": ("harness liveness. Same battery, same B, same pools, pointed at a "
                       "change known to be resolvable. If this does not fire, the twenty "
                       "nulls in this lane are uninformative."),
           "expected": "resolvable LOSS on the ridge leg; muted on the blend leg",
           "cells": {}}
    for si, side in enumerate(SIDES):
        for pi, pool in enumerate(POOLS):
            D = load_pool(side, pool)
            fi = D["keys"].index("fv")
            rng = np.random.default_rng(SEED + 50_000 + 100 * si + 10 * pi)
            g = gate_arm(D, ARM_PROD, arm("blank_fv", zero_feat=fi, recal=False),
                         B, rng, tag=f"{side}.{pool}.blank_fv")
            row = {
                "n_scored": g["n_scored"],
                "point": g["point"], "fold_wins": g["fold_wins"],
                "ridge_leg": {"E_refit": g["E_refit"]["ridge_rho"],
                              "E_cond": g["E_cond"]["ridge_rho"]},
                "blend_leg": {"E_refit": g["E_refit"]["blend_rho"],
                              "E_cond": g["E_cond"]["blend_rho"]},
                "fires_ridge_both_estimators": bool(
                    g["E_refit"]["ridge_rho"].get("resolvable")
                    and g["E_cond"]["ridge_rho"].get("resolvable")),
            }
            out["cells"][f"{side}.{pool}"] = row
            if verbose:
                r, c = g["E_refit"]["ridge_rho"], g["E_cond"]["ridge_rho"]
                print(f"  {side}.{pool:<8} ridge d {g['point']['ridge_rho']:+.5f} "
                      f"refit {r['MDE95']} ({r['x_floor']}x) {r['verdict']} | "
                      f"cond {c['MDE95']} ({c['x_floor']}x) {c['verdict']}  || "
                      f"blend d {g['point']['blend_rho']:+.5f}", flush=True)
    n_fire = sum(1 for v in out["cells"].values() if v["fires_ridge_both_estimators"])
    out["cells_firing_ridge_both_estimators"] = n_fire
    out["cells_total"] = len(out["cells"])
    out["harness_is_live"] = bool(n_fire > 0)
    out["reading"] = (
        "cells firing on the ridge leg under BOTH estimators, out of 4. A count of 0 "
        "would mean this lane's twenty nulls are uninformative.")
    if verbose:
        print(f"  harness live: {out['harness_is_live']} ({n_fire}/{len(out['cells'])} "
              f"cells fire on the ridge leg under both estimators)", flush=True)
    return out


# ===================================================================== I2
def _auc_np(scores, labels):
    """Mann-Whitney U with ties at 0.5. Parity-checked against source_backtest._auc."""
    labels = np.asarray(labels, dtype=bool)
    npos = int(labels.sum())
    nneg = int(len(labels) - npos)
    if npos == 0 or nneg == 0:
        return float("nan")
    r = rankavg(np.asarray(scores, dtype=float))
    u = float(r[labels].sum()) - npos * (npos + 1) / 2.0
    return u / (npos * nneg)


def logit_fit(X, z, w, alphas=_ALPHAS, seed=_RIDGE_HOLDOUT_SEED):
    """Weighted logistic ridge, standardized features, penalty by the SAME seeded
    5-fold CV the production ridge uses (weighted log-loss instead of weighted MAE).

    IRLS/Newton, no penalty on the intercept. Deterministic.
    """
    n, k = X.shape
    if n < 60 or z.sum() < 8 or (n - z.sum()) < 8:
        return None
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = sd.copy()
    sd[sd == 0] = 1.0
    Xs = np.hstack([np.ones((n, 1)), (X - mu) / sd])
    pen = np.ones(k + 1)
    pen[0] = 0.0

    def _fit(idx, alpha):
        Xi, zi, wi = Xs[idx], z[idx], w[idx]
        beta = np.zeros(k + 1)
        beta[0] = math.log(max(1e-6, min(1 - 1e-6, float(np.average(zi, weights=wi))))
                           / max(1e-6, 1 - float(np.average(zi, weights=wi))))
        for _ in range(40):
            p = 1.0 / (1.0 + np.exp(-np.clip(Xi @ beta, -30, 30)))
            W = wi * p * (1 - p) + 1e-9
            A = Xi.T @ (W[:, None] * Xi) + alpha * np.diag(pen)
            g = Xi.T @ (wi * (zi - p)) - alpha * pen * beta
            try:
                step = np.linalg.solve(A, g)
            except np.linalg.LinAlgError:
                return None
            beta = beta + step
            if np.max(np.abs(step)) < 1e-8:
                break
        return beta

    order = np.random.default_rng(seed).permutation(n)
    folds = np.array_split(order, 5)
    best = None
    for alpha in alphas:
        ll, sw = 0.0, 0.0
        for i in range(len(folds)):
            ho = folds[i]
            tri = np.concatenate([folds[j] for j in range(len(folds)) if j != i])
            if len(ho) == 0 or len(tri) == 0 or z[tri].sum() < 4:
                continue
            b = _fit(tri, alpha)
            if b is None:
                continue
            p = 1.0 / (1.0 + np.exp(-np.clip(Xs[ho] @ b, -30, 30)))
            p = np.clip(p, 1e-9, 1 - 1e-9)
            ll += float(np.sum(w[ho] * -(z[ho] * np.log(p) + (1 - z[ho]) * np.log(1 - p))))
            sw += float(w[ho].sum())
        val = (ll / sw) if sw > 0 else float("inf")
        if best is None or val < best[0]:
            best = (val, alpha)
    beta = _fit(np.arange(n), best[1])
    if beta is None:
        return None
    return {"mu": mu, "sd": sd, "beta": beta, "alpha": best[1]}


def logit_pred(m, X):
    Xs = np.hstack([np.ones((len(X), 1)), (X - m["mu"]) / m["sd"]])
    return 1.0 / (1.0 + np.exp(-np.clip(Xs @ m["beta"], -30, 30)))


def chain_clf(D, bars=(CONTRIB_WAR, STAR_WAR), sel=None, perm_seed=None, years=None):
    """Forward-chained blend + consensus + one classifier per bar, on identical rows."""
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"]
    if sel is None:
        sel = np.arange(D["n"])
    X, y, w, fv, dy = D["X"][sel], D["y"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    yres = D["yres"][sel]
    nomilb = D["nomilb"][sel]
    acc = {"cons": [], "blend": [], "y": [], "w": [], "yr": [], "yres": [], "nomilb": []}
    for b in bars:
        acc[f"clf{b}"] = []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fv[tr], y[tr])
        rg = ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        models = {}
        ok = True
        for b in bars:
            z = (y[tr] >= b).astype(float)
            if perm_seed is not None:
                z = z[np.random.default_rng(perm_seed + int(b * 10) + yr).permutation(len(z))]
            m = logit_fit(X[tr], z, w[tr])
            if m is None:
                ok = False
                break
            models[b] = m
        if not ok:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        acc["cons"].append(cons)
        acc["blend"].append((1 - lam) * cons + lam * ridge_pred(rg, X[te]))
        acc["y"].append(y[te])
        acc["w"].append(w[te])
        acc["yres"].append(yres[te])
        acc["nomilb"].append(nomilb[te])
        acc["yr"].append(np.full(len(te), yr))
        for b in bars:
            acc[f"clf{b}"].append(logit_pred(models[b], X[te]))
    if not acc["cons"]:
        return None
    return {k: np.concatenate(v) for k, v in acc.items()}


def auc_cells(r, idx=None, label_key="y"):
    sl = slice(None) if idx is None else idx
    y = r[label_key][sl]
    out = {}
    for b in (CONTRIB_WAR, STAR_WAR):
        lab = y >= b
        if not np.isfinite(y).all():
            m = np.isfinite(y)
            lab = lab & m
        cell = {}
        for rater in ("cons", "blend", f"clf{b}"):
            cell[rater] = _auc_np(r[rater][sl], lab)
        cell["n_pos"] = int(lab.sum())
        cell["n"] = int(len(lab))
        out[str(b)] = cell
    return out


def auc_battery(B: int = 2000, verbose: bool = True):
    out = {"protocol": {
        "auc_pool": "debuted (registration Q1); full pool reported as sensitivity",
        "auc": "Mann-Whitney U, ties 0.5, UNWEIGHTED, parity-checked against "
               "source_backtest._auc",
        "bars": {"contributor": CONTRIB_WAR, "star": STAR_WAR},
        "role": "ADDITIONAL rater. Never replaces the blend anywhere.",
        "B": int(B), "seed": SEED,
    }, "cells": {}, "controls": {}}
    rng = np.random.default_rng(SEED + 11)
    for side in SIDES:
        for pool in ("debuted", "full"):
            D = load_pool(side, pool)
            key0 = f"{side}.{pool}"
            r = chain_clf(D)
            if r is None:
                out["cells"][key0] = {"error": "no fold survived"}
                continue
            pt = auc_cells(r)
            n = len(r["y"])
            if verbose:
                print(f"\n=== I2 {key0}  n_scored={n} ===", flush=True)

            cell = {"n_scored": n, "point": {}, "E_refit": {}, "E_cond": {},
                    "rank_leg": {}}
            for b in (CONTRIB_WAR, STAR_WAR):
                bk = str(b)
                c = pt[bk]
                cell["point"][bk] = {
                    "n": c["n"], "n_pos": c["n_pos"],
                    "consensus_auc": round(c["cons"], 5),
                    "blend_auc": round(c["blend"], 5),
                    "classifier_auc": round(c[f"clf{b}"], 5),
                    "clf_minus_blend": round(c[f"clf{b}"] - c["blend"], 5),
                    "clf_minus_consensus": round(c[f"clf{b}"] - c["cons"], 5),
                    "blend_minus_consensus": round(c["blend"] - c["cons"], 5),
                }
            # rank leg: pooled pair-weighted rho of each rater against raw WAR
            for b in (CONTRIB_WAR, STAR_WAR):
                cell["rank_leg"][str(b)] = round(
                    wrho(r[f"clf{b}"], r["y"], r["w"]), 5)
            cell["rank_leg"]["blend"] = round(wrho(r["blend"], r["y"], r["w"]), 5)
            cell["rank_leg"]["consensus"] = round(wrho(r["cons"], r["y"], r["w"]), 5)

            # E_cond: fits fixed, resample scored rows
            cond = {str(b): {"vs_blend": [], "vs_cons": []} for b in (CONTRIB_WAR, STAR_WAR)}
            for _ in range(B):
                idx = rng.integers(0, n, n)
                cc = auc_cells(r, idx)
                for b in (CONTRIB_WAR, STAR_WAR):
                    bk = str(b)
                    cond[bk]["vs_blend"].append(cc[bk][f"clf{b}"] - cc[bk]["blend"])
                    cond[bk]["vs_cons"].append(cc[bk][f"clf{b}"] - cc[bk]["cons"])
            for b in (CONTRIB_WAR, STAR_WAR):
                bk = str(b)
                cell["E_cond"][bk] = {
                    "vs_blend": summarize(cond[bk]["vs_blend"],
                                          cell["point"][bk]["clf_minus_blend"]),
                    "vs_consensus": summarize(cond[bk]["vs_cons"],
                                              cell["point"][bk]["clf_minus_consensus"]),
                }

            # E_refit: resample the pool, refit everything. Costlier, so B is reduced
            # on the classifier legs and the reduction is REPORTED, not hidden.
            b_ref = max(200, B // 4)
            ref = {str(b): {"vs_blend": [], "vs_cons": []} for b in (CONTRIB_WAR, STAR_WAR)}
            t0 = time.time()
            for i in range(b_ref):
                rr = chain_clf(D, sel=rng.integers(0, D["n"], D["n"]))
                if rr is None:
                    continue
                cc = auc_cells(rr)
                for b in (CONTRIB_WAR, STAR_WAR):
                    bk = str(b)
                    ref[bk]["vs_blend"].append(cc[bk][f"clf{b}"] - cc[bk]["blend"])
                    ref[bk]["vs_cons"].append(cc[bk][f"clf{b}"] - cc[bk]["cons"])
                if verbose and (i + 1) % 100 == 0:
                    print(f"    E_refit {i+1}/{b_ref}  {time.time()-t0:.0f}s", flush=True)
            for b in (CONTRIB_WAR, STAR_WAR):
                bk = str(b)
                cell["E_refit"][bk] = {
                    "B_requested": b_ref,
                    "vs_blend": summarize(ref[bk]["vs_blend"],
                                          cell["point"][bk]["clf_minus_blend"]),
                    "vs_consensus": summarize(ref[bk]["vs_cons"],
                                              cell["point"][bk]["clf_minus_consensus"]),
                }

            # censoring sensitivity (clause Q3): resolved-only rows, resolved label
            fin = np.isfinite(r["yres"])
            if fin.sum() >= 60:
                sub = np.flatnonzero(fin)
                rr = dict(r)
                res_pt = auc_cells(rr, sub, label_key="yres")
                cell["resolved_only"] = {
                    "n": int(fin.sum()),
                    str(CONTRIB_WAR): {k: (round(v, 5) if isinstance(v, float) else v)
                                       for k, v in res_pt[str(CONTRIB_WAR)].items()},
                    str(STAR_WAR): {k: (round(v, 5) if isinstance(v, float) else v)
                                    for k, v in res_pt[str(STAR_WAR)].items()},
                }
            # C-I2d (registration section 5): the gate standard's admissible substitute,
            # AUC on the TRACK-RECORD population only. If the verdict differs from the
            # full-pool number, the full-pool number is discarded.
            trk = np.flatnonzero(r["nomilb"] == 0.0)
            if len(trk) >= 60:
                tp = auc_cells(r, trk)
                cell["track_record_only"] = {
                    "n": int(len(trk)),
                    "n_dropped_no_milb_block": int(len(r["y"]) - len(trk)),
                }
                for b in (CONTRIB_WAR, STAR_WAR):
                    c = tp[str(b)]
                    cell["track_record_only"][str(b)] = {
                        "n_pos": c["n_pos"],
                        "consensus_auc": round(c["cons"], 5),
                        "blend_auc": round(c["blend"], 5),
                        "classifier_auc": round(c[f"clf{b}"], 5),
                        "clf_minus_blend": round(c[f"clf{b}"] - c["blend"], 5),
                    }
            out["cells"][key0] = cell
            if verbose:
                for b in (CONTRIB_WAR, STAR_WAR):
                    p = cell["point"][str(b)]
                    ec = cell["E_cond"][str(b)]["vs_blend"]
                    er = cell["E_refit"][str(b)]["vs_blend"]
                    print(f"  bar {b:>5}: pos {p['n_pos']:>4}  cons {p['consensus_auc']} "
                          f"blend {p['blend_auc']} clf {p['classifier_auc']}  "
                          f"clf-blend {p['clf_minus_blend']:+.5f}  "
                          f"cond {ec['MDE95']} ({ec['x_floor']}x) {ec['verdict']} | "
                          f"refit {er['MDE95']} ({er['x_floor']}x) {er['verdict']}",
                          flush=True)

    # ---- permuted-label control band (clauses Q4 / Q5)
    for side in SIDES:
        D = load_pool(side, "debuted")
        vals = {str(b): {"auc": [], "vs_blend": []} for b in (CONTRIB_WAR, STAR_WAR)}
        for s in range(min(N_CTRL, 60)):
            rr = chain_clf(D, perm_seed=SEED + 700_000 + s * 100)
            if rr is None:
                continue
            cc = auc_cells(rr)
            for b in (CONTRIB_WAR, STAR_WAR):
                bk = str(b)
                vals[bk]["auc"].append(cc[bk][f"clf{b}"])
                vals[bk]["vs_blend"].append(cc[bk][f"clf{b}"] - cc[bk]["blend"])
        band = {}
        for b in (CONTRIB_WAR, STAR_WAR):
            bk = str(b)
            a = np.asarray(vals[bk]["auc"], dtype=float)
            d = np.asarray(vals[bk]["vs_blend"], dtype=float)
            if len(a) < 5:
                band[bk] = {"draws": int(len(a)), "error": "band did not populate"}
                continue
            band[bk] = {
                "draws": int(len(a)),
                "permuted_clf_auc_mean": round(float(a.mean()), 5),
                "permuted_clf_auc_p05_p95": [round(float(np.percentile(a, 5)), 5),
                                             round(float(np.percentile(a, 95)), 5)],
                "auc_inside_q5_band": bool(PERM_AUC_BAND[0] <= a.mean() <= PERM_AUC_BAND[1]),
                "vs_blend_p95": round(float(np.percentile(d, 95)), 5),
                "vs_blend_mean": round(float(d.mean()), 5),
            }
        out["controls"][f"{side}.debuted.label_permuted"] = band
        if verbose:
            print(f"\n  CONTROL {side}.debuted label_permuted: "
                  + json.dumps({k: band[k].get('permuted_clf_auc_mean') for k in sorted(band)}),
                  flush=True)
    return out


# ===================================================================== carve-out
def carveout(verbose: bool = True):
    """Registration section 5. Run BEFORE any AUC number is read."""
    out = {"admissibility": {}, "censoring": {}}
    for side in SIDES:
        for pool in ("debuted", "full"):
            D = load_pool(side, pool)
            key0 = f"{side}.{pool}"
            keys = D["keys"]
            # The indicator under test is "row has NO MiLB production block", read from
            # the raw matrix row. `milb_missing` (the FEATURE) is a narrower flag: rows
            # marked milb_unavailable are held neutral at 0.0 by _vec:1173. Both are
            # reported; the carve-out is adjudicated on the broader raw indicator, which
            # is the one the gate standard's carve-out describes.
            mm = D["nomilb"]
            feat_mm = (D["X"][:, keys.index("milb_missing")] if "milb_missing" in keys
                       else None)
            row = {"has_milb_missing_feature": "milb_missing" in keys,
                   "feature_milb_missing_rate": (round(float(feat_mm.mean()), 5)
                                                 if feat_mm is not None else None),
                   "missing_rate": round(float(mm.mean()), 5),
                   "n_missing": int(mm.sum())}
            for b in (CONTRIB_WAR, STAR_WAR):
                lab = D["y"] >= b
                a = _auc_np(mm, lab) if 0 < mm.sum() < D["n"] else float("nan")
                pm = float(lab[mm == 1].mean()) if (mm == 1).any() else float("nan")
                pn = float(lab[mm == 0].mean()) if (mm == 0).any() else float("nan")
                ratio = (max(pm, pn) / min(pm, pn)) if (np.isfinite(pm) and np.isfinite(pn)
                                                        and min(pm, pn) > 0) else float("inf")
                row[str(b)] = {
                    "missingness_standalone_auc": (round(a, 5) if np.isfinite(a) else None),
                    "auc_inside_band": (bool(CARVEOUT_AUC_BAND[0] <= a <= CARVEOUT_AUC_BAND[1])
                                        if np.isfinite(a) else None),
                    "pos_rate_missing": (round(pm, 5) if np.isfinite(pm) else None),
                    "pos_rate_present": (round(pn, 5) if np.isfinite(pn) else None),
                    "rate_ratio": (round(ratio, 3) if np.isfinite(ratio) else None),
                    "ratio_under_bar": bool(np.isfinite(ratio)
                                            and ratio < CARVEOUT_RATE_RATIO_MAX),
                }
            out["admissibility"][key0] = row
            if verbose:
                print(f"  carve-out {key0}: missing {row['n_missing']}/{D['n']} "
                      f"({row['missing_rate']})  "
                      + " ".join(f"auc@{b}={row[str(b)]['missingness_standalone_auc']}"
                                 for b in (CONTRIB_WAR, STAR_WAR)), flush=True)

    # 5.1 censored star class, on THIS frame
    from efv_dataset import matrix_path
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        deb = [r for r in raw if r["kind"] == "debuted"]
        blk = {"n_debuted": len(deb),
               "n_censored": sum(1 for r in deb if r.get("censored"))}
        for b in (CONTRIB_WAR, STAR_WAR):
            n_both = pos_c = pos_r = chg = 0
            chg_obs2 = obs2 = 0
            for r in deb:
                tc, tr = r.get("target_censored"), r.get("target_resolved")
                if tc is None or tr is None:
                    continue
                n_both += 1
                a, bb = tc >= b, tr >= b
                pos_c += a
                pos_r += bb
                chg += (a != bb)
                if float(r.get("observed_seasons") or 0) <= 2:
                    obs2 += 1
                    chg_obs2 += (a != bb)
            blk[str(b)] = {
                "n": n_both, "pos_censored_label": pos_c, "pos_resolved_label": pos_r,
                "rows_changing_class": chg,
                "share_of_censored_positives_lost": (round(1 - pos_r / pos_c, 4)
                                                     if pos_c else None),
                "rows_obs_seasons_le2": obs2,
                "class_changes_among_obs_le2": chg_obs2,
            }
        out["censoring"][side] = blk
        if verbose:
            print(f"  censoring {side}: " + json.dumps(
                {k: out["censoring"][side][k] for k in sorted(out["censoring"][side])
                 if k != "n_debuted"}), flush=True)
    return out


# ===================================================================== live
def live_move(side: str, cand, base=ARM_PROD):
    """Blast radius on the SERVED board (registration section 3.4).

    Both legs are fit on the PRODUCTION training frame (full minus recent busts, the
    frame fit_production_stack uses) and both score the live matrix through the
    production live path: train-fold linear calibration and the -2 WAR clamp, exactly
    as efv_score.run_live does. So the calibration is present in BOTH legs and the only
    difference is the arm.
    """
    from efv_dataset import matrix_path, live_matrix_path
    is_pit = side == "pit"
    train_raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    live_raw = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in train_raw
            if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    by_key = {r["player_key"]: r for r in pool}
    prep = E._prep(pool, "target_censored", side)
    keys, _m = E._feature_spec(side)
    lam = E.blend_lambda(side)
    Xtr = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    ytr = np.array([r["target"] for r in prep], dtype=float)
    wtr = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fvtr = np.array([r["fv"] for r in prep], dtype=float)
    cens = np.array([bool(by_key[r["player_key"]].get("censored")) for r in prep], dtype=bool)
    Dl = {"n": len(prep), "w": wtr, "cens": cens, "fv": fvtr,
          "dy": np.array([r["decision_year"] for r in prep], dtype=int)}

    live_rows, live_feats, live_fv = [], [], []
    for r in live_raw:
        if bool(r.get("is_pitcher")) != is_pit:
            continue
        fv = r.get("fv_effective")
        if fv is None:
            fv = r.get("consensus_fv_raw")
        if fv is None:
            continue
        live_rows.append(r)
        live_feats.append(E._vec(r, side))
        live_fv.append(float(fv))
    Xlv = np.array([[f.get(k, 0.0) for k in keys] for f in live_feats], dtype=float)
    live_fv = np.array(live_fv, dtype=float)
    o = ols_fit(fvtr, ytr)
    cons = np.maximum(0.0, o[0] + o[1] * live_fv)

    def _score(a):
        sub, wf = a["wf"](Dl, np.arange(len(prep)))
        if sub is None:
            return None
        Xa, ya = Xtr[sub], ytr[sub]
        rg = ridge_fit(Xa, a["tf"](ya), wf)
        if rg is None:
            return None
        raw_tr = ridge_pred(rg, Xa)
        cal = E._fit_linear_calibration(list(zip(raw_tr.tolist(), ya.tolist())))
        ca, cb = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        mod = np.maximum(-2.0, ca + cb * ridge_pred(rg, Xlv))
        return (1 - lam) * cons + lam * mod

    s0, s1 = _score(base), _score(cand)
    if s0 is None or s1 is None:
        return {"side": side, "error": "fit failed"}
    shift = np.abs(rankavg(s1) - rankavg(s0))
    d = s1 - s0
    order = np.argsort(-shift)[:8]
    rho = float(wrho(s0, s1))
    mx = int(shift.max())
    return {
        "side": side, "n_live": int(len(s0)),
        "rank_spearman_old_new": round(rho, 5),
        "max_abs_rank_shift": mx,
        "p99_abs_rank_shift": int(np.percentile(shift, 99)),
        "median_abs_rank_shift": float(np.median(shift)),
        "max_abs_war_delta": round(float(np.abs(d).max()), 4),
        "p99_abs_war_delta": round(float(np.percentile(np.abs(d), 99)), 4),
        "passes_live_clause": bool(rho >= LIVE_RHO_MIN and mx <= LIVE_MAX_SHIFT),
        "top_movers": [{"player_key": live_rows[i]["player_key"],
                        "fv": round(float(live_fv[i]), 1),
                        "rank_shift": int(shift[i]),
                        "war_delta": round(float(d[i]), 3)} for i in order],
    }


def live_battery(verbose: bool = True):
    out = {"clause": {"rho_min": LIVE_RHO_MIN, "max_abs_rank_shift_max": LIVE_MAX_SHIFT,
                      "self_added": True,
                      "staleness_note": ("the served matrices reproduce consensus_fv_raw "
                                         "on 74.8% of rows; a stale board understates "
                                         "spread, so these numbers are a LOWER bound on "
                                         "blast radius, the conservative direction for a "
                                         "clause used to disqualify")},
           "arms": {}}
    cands = [
        ("I1.signed_log1p", arm("signed_log1p", tf_signed_log1p, wf_production, recal=True)),
        ("I1.rank_normal", arm("rank_normal", tf_rank_normal, wf_production, recal=True)),
        ("I3.uniform", arm("uniform", tf_identity, wf_uniform, recal=True)),
        ("I3.sqrt", arm("sqrt", tf_identity, wf_sqrt, recal=True)),
        ("I3.ipcw", arm("ipcw", tf_identity, wf_ipcw, recal=True)),
    ]
    base = arm("recal_identity", tf_identity, wf_production, recal=True)
    for aid, cand in cands:
        out["arms"][aid] = {}
        for side in SIDES:
            m = live_move(side, cand, base)
            out["arms"][aid][side] = m
            if verbose and "error" not in m:
                print(f"  LIVE {aid:<18} {side}: rho {m['rank_spearman_old_new']} "
                      f"median {m['median_abs_rank_shift']} p99 {m['p99_abs_rank_shift']} "
                      f"max {m['max_abs_rank_shift']} -> "
                      f"{'PASS' if m['passes_live_clause'] else 'FAIL'}", flush=True)
    # informational: what the board would look like if the contributor classifier
    # replaced the ridge leg. NOT a gate; I2 is an additional rater by registration.
    out["i2_informational"] = {
        "note": ("I2 is an ADDITIONAL rater by registration, so it has no live clause. "
                 "This row exists only to bound what a replacement would cost if a "
                 "later program tried one.")}
    return out


# ===================================================================== parity
def parity(verbose: bool = True):
    """The harness must reproduce the shipped chain and the shipped AUC exactly."""
    out = {}
    # rank-primitive parity: the vectorized rankavg / wrho / block_norm in this file
    # against the shipped efv_mde_lab ones, on the REAL scored vectors of every pool
    # (including the heavily tied target). Must be exactly 0.0.
    rp = {}
    for side in SIDES:
        for pool in POOLS:
            Dp = load_pool(side, pool)
            rr = chain_pair(Dp, ARM_PROD, ARM_PROD)
            worst_rank = max(
                float(np.abs(rankavg(v) - M._rankavg(v)).max())
                for v in (rr["y"], rr["blend_a"], rr["cons"], Dp["w"], Dp["fv"]))
            worst_rho = abs(wrho(rr["blend_a"], rr["y"], rr["w"])
                            - M.wrho(rr["blend_a"], rr["y"], rr["w"]))
            worst_bn = float(np.abs(block_norm(rr["yr"], rr["y"])
                                    - M.block_norm(rr["yr"], rr["y"])).max())
            rp[f"{side}.{pool}"] = {
                "n": int(len(rr["y"])),
                "max_abs_rank_diff": worst_rank,
                "max_abs_wrho_diff": worst_rho,
                "max_abs_block_norm_diff": worst_bn,
                "exact": bool(worst_rank == 0.0 and worst_rho == 0.0 and worst_bn == 0.0),
            }
    out["rank_primitive_parity"] = rp
    if verbose:
        print("  rank primitive parity:", json.dumps(rp), flush=True)
    for side in SIDES:
        D = load_pool(side, "debuted")
        r = chain_pair(D, ARM_PROD, ARM_PROD)
        Dm = M.load_side(side)
        rm = M.chain(Dm)
        art = ROOT / "data" / ("xfv_eval_pitcher.json" if side == "pit" else "xfv_eval.json")
        ship = {}
        if art.exists():
            ev = json.loads(art.read_text(encoding="utf-8"))
            ship = ((ev.get("evals") or {}).get("debuted_km") or {}).get("pooled_oos") or {}
        mine_b = wrho(r["blend_a"], r["y"], r["w"])
        mine_c = wrho(r["cons"], r["y"], r["w"])
        mde_b = wrho(rm[2], rm[3], rm[4])
        out[side] = {
            "n_mine": int(len(r["y"])), "n_mde_lab": int(len(rm[3])),
            "blend_mine": round(mine_b, 5), "blend_mde_lab": round(mde_b, 5),
            "cons_mine": round(mine_c, 5),
            "shipped_artifact_blend": (ship.get("blend") or {}).get("spearman"),
            "shipped_artifact_baseline": (ship.get("baseline") or {}).get("spearman"),
            "matches_mde_lab": bool(abs(mine_b - mde_b) < 1e-12),
        }
        if verbose:
            print(f"  parity {side}: {json.dumps(out[side])}", flush=True)
    # AUC parity against source_backtest._auc
    from source_backtest import _auc as sb_auc
    rng = np.random.default_rng(SEED + 99)
    s = rng.normal(size=400)
    lab = (rng.random(400) < 0.3)
    a1, a2 = _auc_np(s, lab), sb_auc(s.tolist(), lab.tolist())
    s2 = np.round(s, 1)   # force ties
    b1, b2 = _auc_np(s2, lab), sb_auc(s2.tolist(), lab.tolist())
    out["auc_parity"] = {
        "no_ties": [round(a1, 12), round(a2, 12), bool(abs(a1 - a2) < 1e-12)],
        "with_ties": [round(b1, 12), round(b2, 12), bool(abs(b1 - b2) < 1e-12)],
    }
    uu = (np.arange(1, 4001) - 0.5) / 4000.0
    err = float(np.abs(_norm_ppf(uu) - _norm_ppf_newton(uu)).max())
    out["norm_ppf_parity"] = {
        "max_abs_diff_vs_erf_newton": err,
        "n_checked": 4000,
        "note": ("the fast Acklam Phi^-1 against the scalar-erf Newton reference. The "
                 "rank_normal target is a MONOTONE relabel, so a difference at this "
                 "scale cannot reorder anything."),
    }
    if verbose:
        print("  auc parity:", json.dumps(out["auc_parity"]), flush=True)
    return out


# ===================================================================== verdicts
def adjudicate(rank, live):
    """Apply the pre-registered PASS clauses mechanically. No judgement in here."""
    verdicts = {}
    for cell_key in sorted(rank["cells"]):
        g = rank["cells"][cell_key]
        if "error" in g:
            verdicts[cell_key] = {"verdict": "ERROR"}
            continue
        side, pool, aid = cell_key.split(".", 2)
        bands = rank["control_bands"][f"{side}.{pool}"]
        if aid.startswith("I1"):
            band = bands.get("I1.monotone_warp_k20", {})
        else:
            band = bands.get("I3.weight_permuted", {})
        p95 = band.get("p95")
        pt = g["point"]["blend_rho"]
        er = g["E_refit"]["blend_rho"]
        ec = g["E_cond"]["blend_rho"]
        lv = (live["arms"].get(aid) or {}).get(side) or {}
        c = {
            # NOTE ON P1's SIGN LEG. The registration wrote "same sign" under both
            # estimators. As coded that sub-leg is VACUOUS: both estimators are given
            # the SAME paired point estimate and differ only in their floor, so the
            # signs cannot disagree. It is kept because it is what was registered, and
            # it is flagged here rather than reported as a control that passed. The
            # non-vacuous part of P1 is "resolvable under both", and `estimators_agree`
            # below carries the substantive comparison.
            "P1_both_estimators_resolvable": bool(er.get("resolvable")
                                                  and ec.get("resolvable")
                                                  and np.sign(er["point"]) == np.sign(ec["point"])),
            "P2_block_sign_agrees": bool(np.sign(pt) == np.sign(g["point"]["blend_block"])
                                         and pt != 0),
            "P3_fold_majority": bool(g["fold_wins"] > FOLD_MAJORITY),
            "P4_above_control_p95": (bool(pt > p95) if p95 is not None else None),
            "P5_bonferroni_k10": bool(er.get("resolvable_bonferroni_k10")
                                      and ec.get("resolvable_bonferroni_k10")),
            "P6_live_robust": bool(lv.get("passes_live_clause")) if lv else None,
        }
        allp = all(v is True for v in c.values())
        verdicts[cell_key] = {
            "point_blend_rho": pt,
            "x_floor_refit": er.get("x_floor"), "x_floor_cond": ec.get("x_floor"),
            "estimators_agree": bool(er.get("verdict") == ec.get("verdict")),
            "clauses": c,
            "control_band_position": {
                "band": ("I1.monotone_warp_k20" if aid.startswith("I1")
                         else "I3.weight_permuted"),
                "p05": band.get("p05"), "p95": band.get("p95"),
                "inside_band": (bool(band.get("p05") <= pt <= band.get("p95"))
                                if band.get("p05") is not None else None),
            },
            "verdict": ("PASS" if allp else
                        ("RESOLVABLE LOSS" if (er.get("resolvable") and ec.get("resolvable")
                                               and pt < 0) else "NULL")),
        }
    return verdicts


# ===================================================================== driver
def merge_shards(shard_dir) -> dict:
    """Merge per-(side, pool) rank shards written by `rankcell`.

    Sharding is a PROCESS-LAYOUT decision, not a statistical one: every cell seeds its
    own RNG from SEED + 100*side_index + 10*pool_index, so a shard is byte-identical to
    the same cell computed inside a single process. `parity_shard_check` re-verifies
    that on one cell.
    """
    p = Path(shard_dir)
    files = sorted(p.glob("rank_*.json"))
    if not files:
        raise SystemExit(f"no rank_*.json shards in {p}")
    out = None
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if out is None:
            out = {"protocol": d["protocol"], "cells": {}, "control_bands": {},
                   "plumbing": {}, "shards": []}
        for k in ("cells", "control_bands", "plumbing"):
            out[k].update(d[k])
        out["shards"].append(f.name)
    return out


def run_all(B: int = 2000, shard_dir=None):
    t0 = time.time()
    print("=== PARITY ===")
    par = parity()
    print("\n=== CARVE-OUT + CENSORING (registration section 5, run FIRST) ===")
    co = carveout()
    print("\n=== I1 + I3 RANK BATTERY ===")
    rk = merge_shards(shard_dir) if shard_dir else rank_battery(B)
    print("\n=== DETECTION CONTROL (harness liveness) ===")
    dc = detect_control(B)
    print("\n=== LIVE ROBUSTNESS ===")
    lv = live_battery()
    print("\n=== I2 AUC BATTERY ===")
    au = auc_battery(B)
    vd = adjudicate(rk, lv)
    n_pass = sum(1 for v in vd.values() if v["verdict"] == "PASS")
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_rank_objective_lab.py all",
        "registration": ("docs/efv-2026-08-07b/RANK_AUC_GATE.md parts 0-6, written in "
                         "full BEFORE this lab existed; part 7 is a placeholder filled "
                         "after the run"),
        "lane": "I1 + I2 + I3 (the last three untested rank levers)",
        "scope_note": ("measurement only. Adds and removes NO feature, changes no shipped "
                       "constant, retires nothing, reopens no closed arm, and "
                       "retroactively resolves no past null."),
        "seed": SEED,
        "self_added_thresholds": {
            "live_rho_min": LIVE_RHO_MIN,
            "live_max_abs_rank_shift": LIVE_MAX_SHIFT,
            "fold_majority_strictly_above": FOLD_MAJORITY,
            "control_band_bar": "p95, signed",
            "carveout_auc_band": list(CARVEOUT_AUC_BAND),
            "carveout_rate_ratio_max": CARVEOUT_RATE_RATIO_MAX,
            "bonferroni_family": {"primary_k": K_PRIMARY, "z": Z_BONF_PRIMARY,
                                  "all_cells_k": K_ALL, "z_all": Z_BONF_ALL},
        },
        "parity": par,
        "detection_control": dc,
        "carveout": co,
        "rank": rk,
        "live": lv,
        "auc": au,
        "verdicts": vd,
        "multiplicity": {
            "primary_family": ("5 rank arms x 2 sides on the PRIMARY (full) pool = 10 "
                               "cells; the debuted pool adds 10 more, reported as "
                               "sensitivity"),
            "rank_cells_total": len(vd),
            "rank_cells_passing_all_clauses": n_pass,
            "i2_cells": "2 bars x 2 sides x 2 pools = 8 AUC comparisons",
            "family_was_not_narrowed": True,
        },
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT_PATH}  ({out['elapsed_s']}s)")
    print("verdicts:", json.dumps({k: v["verdict"] for k, v in sorted(vd.items())}, indent=1))
    return out


def main():
    a = sys.argv[1:] or ["all"]
    cmd = a[0]
    if cmd == "parity":
        parity()
    elif cmd == "carveout":
        print(json.dumps(carveout(), indent=1))
    elif cmd == "rank":
        rank_battery(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "rankcell":
        # rankcell SIDE POOL B OUTFILE  -- one (side, pool) shard, own process
        rank_battery(int(a[3]), only_side=a[1], only_pool=a[2], out_path=a[4])
    elif cmd == "detect":
        detect_control(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "auc":
        auc_battery(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "live":
        live_battery()
    elif cmd == "all":
        sd = None
        if "--shards" in a:
            sd = a[a.index("--shards") + 1]
        b = 2000
        for tok in a[1:]:
            if tok.isdigit():
                b = int(tok)
                break
        run_all(b, shard_dir=sd)
    else:
        print("modes: parity | carveout | rank [B] | rankcell SIDE POOL B OUT | "
              "auc [B] | live | all [B] [--shards DIR]")


if __name__ == "__main__":
    main()
