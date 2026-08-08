# PROVISIONAL (efv_ungraded) GATE LAB -- LANE F, 2026-08-07b.
#
# PRE-REGISTRATION: docs/efv-2026-08-07b/PROVISIONAL_GATE.md, parts 0-6, written in full
# BEFORE this file existed. Read it first. This lab may only fill part 7.
#
# WHY THIS FILE EXISTS. efv_ungraded grades ~5,993 players and floor routing
# (efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT) puts ~2,434 of those grades on the
# main board. Its entire eval, data/xfv_ungraded_eval.json, is four bare Spearman numbers
# from 2026-07-14: no paired bootstrap, no zero-information control, no permutation null,
# no MDE, no multi-split average. docs/EFV_GATE_STANDARD.md section 2 requires all four
# for anything shipped, and a grade printed on the board is shipped.
#
# WHAT IT MEASURES
#   part A   the section-2 battery on the model's own labeled pool, under BOTH registered
#            estimators (E_refit, section 1; E_cond, section 7 / POWER_GATE.md).
#   part B   the question the routing decision needed and never had: on the ROUTED cohort
#            specifically, does the provisional grade order realized WAR better than the
#            constant FV 20.0 it replaced? Two independent failure routes, both
#            pre-registered (PROVISIONAL_GATE.md 4.2): the sampling floor, and the
#            permutation null band that models the incumbent tie block honestly.
#   part C   _PROV_RANK_PENALTY re-derived (estimator B of
#            data/provisional_calibration_eval.json) on the partition routing creates.
#
# READ-ONLY on efv_ungraded.py, efv_score.py, prospx/index.html. Writes exactly one
# artifact, data/xfv_ungraded_eval.json.
#
# Run: python tools/efv_ungraded_gate_lab.py all [B]
#      python tools/efv_ungraded_gate_lab.py parity     (harness parity, no writes)
#      python tools/efv_ungraded_gate_lab.py legacy     (reproduce the 2026-07-14 numbers)
from __future__ import annotations

import json

import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np   # noqa: E402  after the thread pins, as in efv_mde_lab.py

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                                   # noqa: E402  read-only
import efv_ungraded as U                                # noqa: E402  read-only
import value_framework as vf                            # noqa: E402  read-only
from efv_dataset import matrix_path                     # noqa: E402
from efv_mde_lab import ridge_fit, ridge_pred, ols_fit, wrho   # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_ungraded_eval.json"
SEED = 20260808                     # PROVISIONAL_GATE.md threshold 2, fixed before the run
Z95_ONE = 1.645
Z95_TWO = 1.96
Z_BONF4_ONE = 2.2414                # one-sided alpha 0.05/4, k = 4 pre-registered cuts
SIDES = ("hit", "pit")
ANCHOR_CONST = 35.0                 # consensus.CONSTANT_ANCHOR_SOURCES placeholder
ANCHOR_SENS = (30.0, 40.0)          # threshold-3 sensitivity
MIN_TRAIN, MIN_TEST = 60, 15        # efv_ungraded.evaluate's own floors
PENALTY_GRID = np.arange(-4.0, 16.0 + 1e-9, 0.25)
PENALTY_B = 1000
PENALTY_PAIRS_BOOT = 60000          # cross-pool pair subsample per bootstrap draw
B_SENS = 500                        # draws for the anchor-sensitivity floors


# ===================================================================== data
def load_side(side: str) -> dict:
    """The provisional model's OWN pool, as arrays, plus the flagship feature block.

    Pool filter is efv_ungraded.fit_nofv / evaluate verbatim: production-bearing rows of
    this side, recent busts excluded. `_prep` is efv_ungraded's, so `feats` comes from
    efv_model._vec exactly as the shipped model builds it.
    """
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows
            if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = U._prep(pool, side)
    by_key = {r["player_key"]: r for r in pool}

    kp = list(U._keys(side))
    kf, _mono = E._feature_spec(side)
    kf = list(kf)
    Xp = np.array([[d["feats"].get(k, 0.0) for k in kp] for d in data], dtype=float)
    Xf = np.array([[d["feats"].get(k, 0.0) for k in kf] for d in data], dtype=float)

    src = [by_key[d["player_key"]] for d in data]
    fv = np.array([(r.get("consensus_fv_raw") if r.get("consensus_fv_raw") is not None
                    else np.nan) for r in src], dtype=float)
    out = {
        "side": side, "keys_prov": kp, "keys_flag": kf,
        "Xp": Xp, "Xf": Xf,
        "y": np.array([d["target"] for d in data], dtype=float),
        "w": np.clip(np.array([float(d.get("weight", 1.0) or 0.0) for d in data]), 1e-3, None),
        "dy": np.array([d["decision_year"] for d in data], dtype=int),
        "fv": fv,
        "has_fv": np.isfinite(fv),
        "debuted": np.array([r.get("kind") == "debuted" for r in src], dtype=bool),
        "level": [(r.get("milb") or {}).get("milb_level") for r in src],
        "level_rank": np.array([float((r.get("milb") or {}).get("level_rank") or 0.0)
                                for r in src], dtype=float),
        "age_rel": np.array([float((r.get("milb") or {}).get("age_rel_level") or 0.0)
                             for r in src], dtype=float),
        "lam": float(E.blend_lambda(side)),
        "n": len(data),
    }
    # Constant-anchor twin of the flagship design matrix: fv -> the placeholder, and the
    # scout tool columns -> their missing-value imputes, because a player nobody has
    # graded has published no tools. PROVISIONAL_GATE.md 4.1, threshold 3.
    out["Xf_const"] = {a: _const_anchor_matrix(Xf, kf, a) for a in (ANCHOR_CONST,) + ANCHOR_SENS}
    out["years"] = tuple(E.SCORED_YEARS)
    return out


def _const_anchor_matrix(Xf, kf, anchor):
    M = Xf.copy()
    for j, k in enumerate(kf):
        if k == "fv":
            M[:, j] = anchor
        elif k in E._TOOL_IMPUTE:
            M[:, j] = E._TOOL_IMPUTE[k]
    return M


# ===================================================================== primitives
def lin_cal(pred, y):
    """prospect_path._fit_linear_calibration, including its round(.,4). Returns (a, b)."""
    n = len(y)
    if n < 50:
        return (0.0, 1.0)
    mp, mo = float(pred.mean()), float(y.mean())
    var = float(((pred - mp) ** 2).sum())
    if var <= 0:
        return (0.0, 1.0)
    b = float(((pred - mp) * (y - mo)).sum()) / var
    return (round(mo - b * mp, 4), round(b, 4))


def ridge_pred_clipped(m, X, clip=None):
    """efv_ungraded._predict_clipped, vectorized. Standardized features are clipped to
    +/- _Z_CLIP before weighting; this is LOCAL to the provisional path."""
    clip = U._Z_CLIP if clip is None else clip
    mu, sd, ww, b = m
    Z = np.clip((X - mu) / sd, -clip, clip)
    return Z @ ww + b


def grade_map(war, side):
    """efv_ungraded._grade, vectorized, honoring the shipped UNCAPPED_GRADE flag.

    NOTE the exposure sub-floor clamp (min(grade, 30.0) below _MIN_EXPO_PA/_MIN_EXPO_BF)
    is NOT applied: the labeled matrix carries no PA/BF column. Disclosed limitation,
    PROVISIONAL_GATE.md part 2.
    """
    m = U._GRADE_MAP[side]
    g = np.maximum(m["FLOOR"], m["BASE"] + m["SLOPE"] * war)
    if not U.UNCAPPED_GRADE:
        knee, ceil, soft = m["KNEE"], m["CEIL"], m["SOFT"]
        hi = g > knee
        g = np.where(hi, knee + (ceil - knee) * (1.0 - np.exp(-(g - knee) / soft)), g)
    return np.round(g, 1)


def auc(score, label):
    """Rank AUC, average-rank tie handling. label True = debuted."""
    score = np.asarray(score, dtype=float)
    label = np.asarray(label, dtype=bool)
    n1, n0 = int(label.sum()), int((~label).sum())
    if n1 < 5 or n0 < 5:
        return float("nan")
    order = score.argsort(kind="mergesort")
    r = np.empty(len(score), dtype=float)
    r[order] = np.arange(1, len(score) + 1, dtype=float)
    s = score[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return (float(r[label].sum()) - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def block_norm(v):
    """Percentile position inside one block on [0, 1], average-rank ties (efv_model)."""
    v = np.asarray(v, dtype=float)
    order = v.argsort(kind="mergesort")
    r = np.empty(len(v), dtype=float)
    r[order] = np.arange(1, len(v) + 1, dtype=float)
    s = v[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return (r - 0.5) / len(v)


def summarize(draws, point, z=Z95_ONE, label="MDE95"):
    a = np.asarray(draws, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 20:
        return {"B_used": int(len(a)), "point": round(float(point), 5), "sd": None,
                label: None, "verdict": "UNMEASURABLE"}
    sd = float(a.std(ddof=1))
    fl = z * sd
    return {
        "B_used": int(len(a)),
        "point": round(float(point), 5),
        "boot_mean": round(float(a.mean()), 5),
        "sd": round(sd, 5),
        label: round(fl, 4),
        "mde95_twosided": round(Z95_TWO * sd, 4),
        "mde95_bonferroni_k4": round(Z_BONF4_ONE * sd, 4),
        "ci95": [round(float(np.percentile(a, 2.5)), 5),
                 round(float(np.percentile(a, 97.5)), 5)],
        "p_le_0": round(float((a <= 0).mean()), 4),
        "margin_over_floor": round(abs(float(point)) / fl, 3) if fl > 0 else None,
        "resolvable": bool(abs(float(point)) >= fl),
        "clears_bonferroni_k4": bool(abs(float(point)) >= Z_BONF4_ONE * sd),
        "verdict": ("RESOLVABLE " + ("WIN" if point > 0 else "LOSS")
                    if abs(float(point)) >= fl else "NULL"),
    }


# ===================================================================== chains
def chain_prov(D, sel=None, keep_fits=False):
    """Forward-chained PROVISIONAL scoring. Mirrors efv_ungraded.evaluate's fold loop
    (its own _fit_ridge + _fit_linear_calibration + clipped _war), then applies the
    SERVED grade map on top, which the incumbent eval does not do."""
    if sel is None:
        sel = np.arange(D["n"])
    X, y, w, dy = D["Xp"][sel], D["y"][sel], D["w"][sel], D["dy"][sel]
    deb, lvl, agr = D["debuted"][sel], D["level_rank"][sel], D["age_rel"][sel]
    W_, Y_, G_, R_, YR_, DE_, LV_, AG_ = [], [], [], [], [], [], [], []
    fits = []
    for yr in D["years"]:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        rg = ridge_fit(X[tr], y[tr], w[tr])
        if rg is None:
            continue
        a, b = lin_cal(ridge_pred(rg, X[tr]), y[tr])
        war = np.maximum(-2.0, a + b * ridge_pred_clipped(rg, X[te]))
        G_.append(grade_map(war, D["side"]))
        R_.append(war)
        Y_.append(y[te])
        W_.append(w[te])
        YR_.append(np.full(len(te), yr))
        DE_.append(deb[te])
        LV_.append(lvl[te])
        AG_.append(agr[te])
        if keep_fits:
            fits.append({"yr": int(yr), "n_te": int(len(te)), "alpha_free": True})
    if not G_:
        return None
    out = {"grade": np.concatenate(G_), "war": np.concatenate(R_),
           "y": np.concatenate(Y_), "w": np.concatenate(W_),
           "yr": np.concatenate(YR_), "debuted": np.concatenate(DE_),
           "level_rank": np.concatenate(LV_), "age_rel": np.concatenate(AG_)}
    if keep_fits:
        out["folds"] = fits
    return out


def chain_joint(D, sel=None, anchor=ANCHOR_CONST):
    """Forward chain that scores BOTH models on the SAME test rows, so the routed-cohort
    membership and the provisional grade are aligned row for row.

    A fold enters only if both legs fit (the flagship leg needs an anchor, so it trains on
    rows with a consensus point; the provisional leg trains on the full production pool,
    which is what each model does live).
    """
    if sel is None:
        sel = np.arange(D["n"])
    Xp, Xf = D["Xp"][sel], D["Xf"][sel]
    Xfc = D["Xf_const"][anchor][sel]
    y, w, dy, fv = D["y"][sel], D["w"][sel], D["dy"][sel], D["fv"][sel]
    hf = D["has_fv"][sel]
    lvl, agr, deb = D["level_rank"][sel], D["age_rel"][sel], D["debuted"][sel]
    lam = D["lam"]
    G_, F_, FC_, Y_, W_, YR_, RT_, LV_, AG_, DE_ = ([] for _ in range(10))
    for yr in D["years"]:
        tr = np.flatnonzero(dy < yr)
        trf = np.flatnonzero((dy < yr) & hf)
        tef = np.flatnonzero((dy == yr) & hf)
        if len(tr) < MIN_TRAIN or len(tef) < MIN_TEST or len(trf) < MIN_TRAIN:
            continue
        rgp = ridge_fit(Xp[tr], y[tr], w[tr])
        rgf = ridge_fit(Xf[trf], y[trf], w[trf])
        o = ols_fit(fv[trf], y[trf])
        if rgp is None or rgf is None or o is None:
            continue
        a, b = lin_cal(ridge_pred(rgp, Xp[tr]), y[tr])
        war = np.maximum(-2.0, a + b * ridge_pred_clipped(rgp, Xp[tef]))
        grade = grade_map(war, D["side"])
        cons_c = max(0.0, o[0] + o[1] * anchor)
        blend_c = (1 - lam) * cons_c + lam * ridge_pred(rgf, Xfc[tef])
        cons_r = np.maximum(0.0, o[0] + o[1] * fv[tef])
        blend_r = (1 - lam) * cons_r + lam * ridge_pred(rgf, Xf[tef])
        G_.append(grade)
        F_.append(np.array([vf.outcome_implied_fv(float(v)) for v in blend_r]))
        # The INCUMBENT grade on a routed row is the constant-anchor flagship grade, not
        # the real-anchor one: routing fires only where no source published an opinion, so
        # the real anchor does not exist for that player. Clause B0 checks THIS column.
        FC_.append(np.array([vf.outcome_implied_fv(float(v)) for v in blend_c]))
        RT_.append(blend_c <= 0.0)
        Y_.append(y[tef])
        W_.append(w[tef])
        YR_.append(np.full(len(tef), yr))
        LV_.append(lvl[tef])
        AG_.append(agr[tef])
        DE_.append(deb[tef])
    if not G_:
        return None
    return {"grade": np.concatenate(G_), "flag_grade": np.concatenate(F_),
            "flag_grade_const": np.concatenate(FC_),
            "routed": np.concatenate(RT_), "y": np.concatenate(Y_),
            "w": np.concatenate(W_), "yr": np.concatenate(YR_),
            "level_rank": np.concatenate(LV_), "age_rel": np.concatenate(AG_),
            "debuted": np.concatenate(DE_)}


# ===================================================================== statistics
def rho_of(r, key="grade", idx=None, weighted=True, mask=None):
    sl = np.arange(len(r["y"])) if mask is None else np.flatnonzero(mask)
    if idx is not None:
        sl = sl[idx] if len(sl) else sl
    if len(sl) < 8:
        return float("nan")
    w = r["w"][sl] if weighted else None
    return wrho(r[key][sl], r["y"][sl], w)


def const_rho(vals, y, w):
    """The incumbent's Spearman. A constant predictor has zero rank variance, so this is
    undefined; PROVISIONAL_GATE.md 4.2 adopts rho_constant := 0.0 and this function
    VERIFIES the constancy rather than asserting it (clause B0)."""
    u = np.unique(vals)
    return {"n": int(len(vals)), "distinct_values": int(len(u)),
            "value": (round(float(u[0]), 4) if len(u) == 1 else None),
            "predictor_variance": round(float(np.var(vals)), 12),
            "spearman_raw": (None if len(u) == 1 else round(float(wrho(vals, y, w)), 5)),
            "spearman_convention": 0.0,
            "note": ("a constant has zero rank information by construction; its Spearman is "
                     "undefined, not zero, and the 0.0 is a convention this lane names")}


# ===================================================================== estimators
def boot_refit_prov(D, B, rng, stat_fn):
    out = []
    for _ in range(B):
        r = chain_prov(D, rng.integers(0, D["n"], D["n"]))
        out.append(stat_fn(r) if r is not None else float("nan"))
    return out


def boot_cond(r, B, rng, stat_fn, mask=None):
    n = int(len(r["y"]) if mask is None else mask.sum())
    out = []
    for _ in range(B):
        out.append(stat_fn(r, rng.integers(0, n, n)))
    return out


def boot_refit_joint(D, B, rng, stat_fn, anchor=ANCHOR_CONST):
    out = []
    for _ in range(B):
        r = chain_joint(D, rng.integers(0, D["n"], D["n"]), anchor=anchor)
        out.append(stat_fn(r) if r is not None else float("nan"))
    return out


def perm_null(r, B, rng, key="grade", mask=None):
    """Permutation null on the SAME rows: permute the prediction, keep every (y, w) pair
    intact, recompute the statistic. Returns the null draws."""
    sl = np.arange(len(r["y"])) if mask is None else np.flatnonzero(mask)
    g, y = r[key][sl], r["y"][sl]
    w = r["w"][sl]
    return [wrho(g[rng.permutation(len(sl))], y, w) for _ in range(B)]


# ===================================================================== part A
def battery(B=2000, verbose=True):
    rng = np.random.default_rng(SEED)
    res = {}
    chains = {}
    for side in SIDES:
        D = load_side(side)
        r = chain_prov(D, keep_fits=True)
        chains[side] = (D, r)
        pt_w = rho_of(r, "grade", weighted=True)
        pt_u = rho_of(r, "grade", weighted=False)
        pt_war_w = rho_of(r, "war", weighted=True)
        pt_war_u = rho_of(r, "war", weighted=False)

        t0 = time.time()
        dr_refit = boot_refit_prov(D, B, rng, lambda x: rho_of(x, "grade", weighted=True))
        dr_cond = boot_cond(r, B, rng, lambda x, i: rho_of(x, "grade", idx=i, weighted=True))
        # A3 zero-information twin: ONE row permutation of the served grade, fixed seed.
        tw_rng = np.random.default_rng(SEED + 1)
        twin = r["grade"][tw_rng.permutation(len(r["y"]))]
        rho_twin = wrho(twin, r["y"], r["w"])
        # A4 permutation null
        nulls = perm_null(r, B, np.random.default_rng(SEED + 2))
        p_perm = float(np.mean(np.abs(np.asarray(nulls)) >= abs(pt_w)))
        # A5 per fold
        folds = {}
        for yr in np.unique(r["yr"]):
            m = r["yr"] == yr
            folds[int(yr)] = {"n": int(m.sum()),
                              "rho": round(float(wrho(r["grade"][m], r["y"][m], r["w"][m])), 5)}
        fvals = [v["rho"] for v in folds.values()]
        # AUC on the track-record population (the section-3 admissible substitute)
        a_pt = auc(r["grade"], r["debuted"])
        a_refit = boot_refit_prov(D, B, rng, lambda x: auc(x["grade"], x["debuted"]))

        sm_refit = summarize(dr_refit, pt_w)
        sm_cond = summarize(dr_cond, pt_w)
        sm_auc = summarize(a_refit, a_pt)
        res[side] = {
            "n_scored": int(len(r["y"])),
            "folds_used": sorted(int(v) for v in np.unique(r["yr"])),
            "rho_grade_weighted": round(float(pt_w), 5),
            "rho_grade_unweighted": round(float(pt_u), 5),
            "rho_war_weighted": round(float(pt_war_w), 5),
            "rho_war_unweighted": round(float(pt_war_u), 5),
            "share_on_floor_20": round(float(np.mean(r["grade"] <= 20.0)), 4),
            "E_refit": sm_refit,
            "E_cond": sm_cond,
            "A1_pass": bool(sm_refit["resolvable"]),
            "A2_pass": bool(sm_cond["resolvable"]),
            "A3_zero_information_twin": {
                "rho": round(float(rho_twin), 5),
                "margin_over_refit_floor": round(abs(rho_twin) / sm_refit["MDE95"], 3),
                "pass": bool(abs(rho_twin) < sm_refit["MDE95"])},
            "A4_permutation_null": {
                "B": int(B), "p_two_sided": round(p_perm, 5),
                "null_p95": round(float(np.percentile(nulls, 95)), 5),
                "null_sd": round(float(np.std(nulls, ddof=1)), 5),
                "pass": bool(p_perm <= 0.05)},
            "A5_folds": {
                "per_fold": folds, "k": len(fvals),
                "mean": round(float(np.mean(fvals)), 5),
                "n_positive": int(sum(1 for v in fvals if v > 0)),
                "pass": bool(np.mean(fvals) > 0 and sum(1 for v in fvals if v > 0) > len(fvals) / 2)},
            "auc_track_record": sm_auc,
            "auc_ci_excludes_half": bool(sm_auc["ci95"][0] > 0.5),
            "seconds": round(time.time() - t0, 1),
        }
        if verbose:
            print(f"[A] {side}: rho={pt_w:.4f} refit MDE95={sm_refit['MDE95']} "
                  f"({sm_refit['margin_over_floor']}x) cond MDE95={sm_cond['MDE95']} "
                  f"({sm_cond['margin_over_floor']}x) perm p={p_perm:.4f} "
                  f"AUC={a_pt:.4f} {sm_auc['ci95']}  [{res[side]['seconds']}s]")

    # block-rho: (side x fold-year) blocks, both sides pooled
    def _block_pairs(chain_map):
        P, T = [], []
        for side, r in chain_map.items():
            for yr in np.unique(r["yr"]):
                m = r["yr"] == yr
                if m.sum() < 8:
                    continue
                P.append(block_norm(r["grade"][m]))
                T.append(block_norm(r["y"][m]))
        if not P:
            return None
        return np.concatenate(P), np.concatenate(T)

    pt_blocks = _block_pairs({s: chains[s][1] for s in SIDES})
    br_pt = wrho(pt_blocks[0], pt_blocks[1])
    br_draws = []
    for _ in range(B):
        cm = {}
        ok = True
        for s in SIDES:
            D = chains[s][0]
            rr = chain_prov(D, rng.integers(0, D["n"], D["n"]))
            if rr is None:
                ok = False
                break
            cm[s] = rr
        if not ok:
            br_draws.append(float("nan"))
            continue
        bp = _block_pairs(cm)
        br_draws.append(wrho(bp[0], bp[1]) if bp else float("nan"))
    sm_br = summarize(br_draws, br_pt)
    two_metric = {"block_rho": sm_br, "n_blocks_pooled": int(len(pt_blocks[0])),
                  "block_rho_ci_excludes_zero": bool(sm_br["ci95"][0] > 0)}
    for side in SIDES:
        res[side]["A6_pass"] = bool(two_metric["block_rho_ci_excludes_zero"]
                                    and res[side]["auc_ci_excludes_half"])
    if verbose:
        print(f"[A] block-rho={br_pt:.4f} ci={sm_br['ci95']} n={two_metric['n_blocks_pooled']}")
    return {"by_side": res, "two_metric": two_metric, "B": int(B)}


# ===================================================================== part B
def routed(B=2000, verbose=True):
    rng = np.random.default_rng(SEED + 100)
    out = {}
    joint_pt = {}
    for side in SIDES:
        D = load_side(side)
        r = chain_joint(D)
        joint_pt[side] = (D, r)
        m = r["routed"]
        nr = int(m.sum())
        b0 = const_rho(r["flag_grade_const"][m], r["y"][m], r["w"][m])
        # Fidelity diagnostic, NOT a competitor: these analog rows DO carry real
        # scout anchors in the labeled matrix and are only being scored as if they
        # did not. How well their REAL-anchor flagship grade ranks the same rows
        # bounds how much the analog is a hypothetical. PROVISIONAL_GATE.md part 1.
        b0["real_anchor_flagship_rho_on_same_rows"] = round(
            float(wrho(r["flag_grade"][m], r["y"][m], r["w"][m])), 5)
        b0["real_anchor_note"] = ("routing fires only where no source published an "
            "opinion, so this column does not exist for a live routed player; it is "
            "reported to size the analog's selection, not as an alternative")
        pt = float(wrho(r["grade"][m], r["y"][m], r["w"][m]))

        t0 = time.time()
        dr_refit = boot_refit_joint(
            D, B, rng, lambda x: (wrho(x["grade"][x["routed"]], x["y"][x["routed"]],
                                       x["w"][x["routed"]])
                                  if x is not None and x["routed"].sum() >= 8 else float("nan")))
        idxR = np.flatnonzero(m)
        rc = {"grade": r["grade"][idxR], "y": r["y"][idxR], "w": r["w"][idxR],
              "yr": r["yr"][idxR], "level_rank": r["level_rank"][idxR],
              "age_rel": r["age_rel"][idxR]}
        dr_cond = boot_cond(rc, B, rng,
                            lambda x, i: wrho(x["grade"][i], x["y"][i], x["w"][i]))
        tw_rng = np.random.default_rng(SEED + 101)
        twin = rc["grade"][tw_rng.permutation(nr)]
        rho_twin = float(wrho(twin, rc["y"], rc["w"]))
        nulls = np.asarray(perm_null(rc, B, np.random.default_rng(SEED + 102)))
        null_p95 = float(np.percentile(nulls, 95))
        p_perm_two = float(np.mean(np.abs(nulls) >= abs(pt)))

        sm_refit = summarize(dr_refit, pt)
        sm_cond = summarize(dr_cond, pt)

        # B5 the embarrassing control: one-column heads on identical rows, PAIRED.
        rho_lvl = float(wrho(rc["level_rank"], rc["y"], rc["w"]))
        rho_age = float(wrho(-rc["age_rel"], rc["y"], rc["w"]))
        pair_pt = pt - rho_lvl
        pair_draws = []
        for _ in range(B):
            i = rng.integers(0, nr, nr)
            pair_draws.append(wrho(rc["grade"][i], rc["y"][i], rc["w"][i])
                              - wrho(rc["level_rank"][i], rc["y"][i], rc["w"][i]))
        sm_pair = summarize(pair_draws, pair_pt)

        # threshold-3 sensitivity on the anchor placeholder, WITH its own floors, because
        # a self-added threshold that moves a verdict has to be shown to move it or not.
        sens = {}
        for a in (ANCHOR_CONST,) + ANCHOR_SENS:
            ra = r if a == ANCHOR_CONST else chain_joint(D, anchor=a)
            ma = ra["routed"]
            na = int(ma.sum())
            pa = float(wrho(ra["grade"][ma], ra["y"][ma], ra["w"][ma]))
            srng = np.random.default_rng(SEED + 300)
            sdr = boot_refit_joint(
                D, B_SENS, srng,
                lambda x: (wrho(x["grade"][x["routed"]], x["y"][x["routed"]],
                                x["w"][x["routed"]])
                           if x is not None and x["routed"].sum() >= 8 else float("nan")),
                anchor=a)
            ia = np.flatnonzero(ma)
            sdc = [wrho(ra["grade"][ia][k], ra["y"][ia][k], ra["w"][ia][k])
                   for k in (srng.integers(0, na, na) for _ in range(B_SENS))]
            sa, sc = summarize(sdr, pa), summarize(sdc, pa)
            sens[str(a)] = {"n_routed": na, "rho": round(pa, 5),
                            "B_sens": B_SENS,
                            "E_refit": {"MDE95": sa["MDE95"], "x": sa["margin_over_floor"],
                                        "verdict": sa["verdict"]},
                            "E_cond": {"MDE95": sc["MDE95"], "x": sc["margin_over_floor"],
                                       "verdict": sc["verdict"]}}
        sens["_note"] = ("35.0 is the value consensus.CONSTANT_ANCHOR_SOURCES actually "
                         "stamps, verified in-repo (efv_ungraded.flagship_owns: 2,632 "
                         "constant-only players 'every one of them at fv_raw exactly 35.0'; "
                         "efv_score's FLOOR ROUTING block says the same). 30.0 and 40.0 are "
                         "counterfactuals reported because the cohort SIZE is highly "
                         "sensitive to this value and a self-added threshold that can move a "
                         "verdict must be shown to move it or not.")

        out[side] = {
            "n_scored_joint": int(len(r["y"])),
            "n_routed": nr,
            "routed_share": round(nr / max(len(r["y"]), 1), 4),
            "routed_debut_rate": round(float(r["debuted"][m].mean()), 4),
            "mapping_caveat": ("the analog's debut rate is that of labeled prospects; the "
                               "SERVED routed cohort is org filler two rungs lower on the "
                               "ladder. PROVISIONAL_GATE.md part 1."),
            "B0_incumbent": b0,
            "rho_provisional_weighted": round(pt, 5),
            "rho_provisional_unweighted": round(float(wrho(rc["grade"], rc["y"])), 5),
            "E_refit": sm_refit,
            "E_cond": sm_cond,
            "B1_pass": bool(sm_refit["resolvable"]),
            "B2_pass": bool(sm_cond["resolvable"]),
            "B3_permutation_band": {
                "B": int(B), "null_p95": round(null_p95, 5),
                "null_sd": round(float(nulls.std(ddof=1)), 5),
                "p_two_sided": round(p_perm_two, 5),
                "pass": bool(pt > null_p95)},
            "B4_zero_information_twin": {
                "rho": round(rho_twin, 5),
                "margin_over_refit_floor": round(abs(rho_twin) / sm_refit["MDE95"], 3)
                if sm_refit["MDE95"] else None,
                "pass": bool(sm_refit["MDE95"] and abs(rho_twin) < sm_refit["MDE95"])},
            "B5_dumb_controls": {
                "rho_provisional": round(pt, 5),
                "rho_level_rank_only": round(rho_lvl, 5),
                "rho_neg_age_rel_only": round(rho_age, 5),
                "paired_delta_prov_minus_level": sm_pair,
                "level_lookup_matches_model": bool(not sm_pair["resolvable"])},
            "B6_bonferroni_k4": {
                "z": Z_BONF4_ONE,
                "E_refit_floor": sm_refit["mde95_bonferroni_k4"],
                "E_cond_floor": sm_cond["mde95_bonferroni_k4"],
                "clears_refit": sm_refit["clears_bonferroni_k4"],
                "clears_cond": sm_cond["clears_bonferroni_k4"]},
            "anchor_sensitivity": sens,
            "estimators_agree": bool(sm_refit["resolvable"] == sm_cond["resolvable"]),
            "seconds": round(time.time() - t0, 1),
        }
        if verbose:
            print(f"[B] {side}: n_routed={nr} rho={pt:.4f} refit={sm_refit['MDE95']} "
                  f"({sm_refit['margin_over_floor']}x) cond={sm_cond['MDE95']} "
                  f"({sm_cond['margin_over_floor']}x) nullp95={null_p95:.4f} "
                  f"lvl={rho_lvl:.4f} pairdelta={pair_pt:+.4f} [{out[side]['seconds']}s]")
    out["_joint"] = joint_pt
    return out


# ===================================================================== part C
def _concordance_grid(gp, yp, gg, yg, grid, pairs=None, rng=None):
    """Cross-pool pair concordance of adjusted-grade order vs realized-WAR order, over a
    grid of display penalties. Pool P displays gp - delta, pool G displays gg. Ties on
    either side are excluded from the denominator, exactly as estimator B specifies."""
    if pairs is None:
        sy = np.sign(yp[:, None] - yg[None, :])
        out = []
        for d in grid:
            sg = np.sign((gp[:, None] - d) - gg[None, :])
            ok = (sy != 0) & (sg != 0)
            n = int(ok.sum())
            out.append(float((sg[ok] == sy[ok]).sum()) / n if n else float("nan"))
        return np.asarray(out), int(((sy != 0)).sum())
    i = rng.integers(0, len(gp), pairs)
    j = rng.integers(0, len(gg), pairs)
    sy = np.sign(yp[i] - yg[j])
    out = []
    for d in grid:
        sg = np.sign((gp[i] - d) - gg[j])
        ok = (sy != 0) & (sg != 0)
        n = int(ok.sum())
        out.append(float((sg[ok] == sy[ok]).sum()) / n if n else float("nan"))
    return np.asarray(out), pairs


def penalty(joint_pt, B=PENALTY_B, verbose=True):
    """C0 fact check + C1 estimator-B re-derivation on the partition routing creates."""
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8", errors="replace")
    line_no, val = None, None
    for i, ln in enumerate(src.splitlines(), 1):
        if "_PROV_RANK_PENALTY" in ln and "const" in ln:
            line_no = i
            val = ln.split("=")[-1].strip().rstrip(";")
            break
    shipped = {
        "value": (float(val) if val is not None and val.replace(".", "", 1).lstrip("-").isdigit()
                  else val),
        "file_line": f"prospx/index.html:{line_no}",
        "uncapped_grade": bool(U.UNCAPPED_GRADE),
        "brief_claimed_value": 4,
        "brief_claimed_line": "prospx/index.html:31243",
        "brief_claimed_decap": True,
        "premises_hold": False,
    }

    gp, yp, gg, yg = [], [], [], []
    for side in SIDES:
        _D, r = joint_pt[side]
        m = r["routed"]
        gp.append(r["grade"][m])
        yp.append(r["y"][m])
        gg.append(r["flag_grade"][~m])
        yg.append(r["y"][~m])
    dp, dg = [], []
    for side in SIDES:
        _D, r = joint_pt[side]
        m = r["routed"]
        dp.append(r["debuted"][m])
        dg.append(r["debuted"][~m])
    gp, yp = np.concatenate(gp), np.concatenate(yp)
    gg, yg = np.concatenate(gg), np.concatenate(yg)
    dp, dg = np.concatenate(dp), np.concatenate(dg)

    conc, npairs = _concordance_grid(gp, yp, gg, yg, PENALTY_GRID)
    best = int(np.nanargmax(conc))
    top = float(conc[best])
    plateau = [float(PENALTY_GRID[k]) for k in range(len(conc))
               if np.isfinite(conc[k]) and top - conc[k] <= 1e-4]
    rng = np.random.default_rng(SEED + 200)
    argmaxes = []
    for _ in range(B):
        ip = rng.integers(0, len(gp), len(gp))
        ig = rng.integers(0, len(gg), len(gg))
        c, _n = _concordance_grid(gp[ip], yp[ip], gg[ig], yg[ig], PENALTY_GRID,
                                  pairs=PENALTY_PAIRS_BOOT, rng=rng)
        if np.all(~np.isfinite(c)):
            continue
        argmaxes.append(float(PENALTY_GRID[int(np.nanargmax(c))]))
    am = np.asarray(argmaxes)

    def at(d):
        k = int(np.argmin(np.abs(PENALTY_GRID - d)))
        return round(float(conc[k]), 5)

    est = {
        "pool_P_routed_n": int(len(gp)), "pool_G_graded_n": int(len(gg)),
        "cross_pool_pairs": int(npairs),
        "grid": [float(PENALTY_GRID[0]), float(PENALTY_GRID[-1]), 0.25],
        "argmax_delta": float(PENALTY_GRID[best]),
        "concordance_at_argmax": round(top, 5),
        "plateau_within_1e4": [min(plateau), max(plateau)] if plateau else None,
        "concordance_at_shipped_0": at(0.0),
        "concordance_at_retired_4": at(4.0),
        "concordance_at_2026_07_23_argmax_3_75": at(3.75),
        "bootstrap": {"B": int(len(am)), "pairs_per_draw": PENALTY_PAIRS_BOOT,
                      "ci95_argmax": [float(np.percentile(am, 2.5)),
                                      float(np.percentile(am, 97.5))],
                      "median_argmax": float(np.median(am)),
                      "share_argmax_le_0": round(float((am <= 0).mean()), 4),
                      "note": ("bootstrap draws use a random subsample of cross-pool pairs "
                               "for tractability; that adds Monte-Carlo noise to the CI, "
                               "which widens it, the conservative direction")},
        "argmax_on_grid_boundary": bool(best in (0, len(PENALTY_GRID) - 1)),
        "curve": {str(round(float(d), 2)): round(float(c), 5)
                  for d, c in zip(PENALTY_GRID, conc)
                  if abs(float(d) - round(float(d))) < 1e-9 and float(d) % 2 == 0},
        "pool_diagnostics": {
            "pool_P_mean_display_grade": round(float(gp.mean()), 2),
            "pool_G_mean_display_grade": round(float(gg.mean()), 2),
            "pool_P_mean_realized_war": round(float(yp.mean()), 3),
            "pool_G_mean_realized_war": round(float(yg.mean()), 3),
            "pool_P_debut_rate": round(float(dp.mean()), 3),
            "pool_G_debut_rate": round(float(dg.mean()), 3),
            "note": ("THE POOL-MAPPING DEFECT, quantified. Pool P here is real-anchored "
                     "labeled players re-scored AS IF constant-anchored, so its debut rate "
                     "is that of graded prospects, not of the org filler routing actually "
                     "serves. Any penalty this estimator returns is contaminated by that "
                     "selection in the direction of its own answer."),
        },
        "shipped_value_inside_ci95": None,
    }
    # POST-HOC, DISCLOSED: the pre-registered grid's argmax landed on its lower boundary,
    # which is a grid mis-specification, not a result. The grid is widened ONCE to locate
    # the interior optimum and BOTH answers are published. It does not change the
    # recommendation, which is KEEP, under either grid.
    wide_grid = np.arange(-20.0, 16.0 + 1e-9, 0.25)
    wconc, _n = _concordance_grid(gp, yp, gg, yg, wide_grid)
    wb = int(np.nanargmax(wconc))
    est["widened_grid_post_hoc"] = {
        "grid": [-20.0, 16.0, 0.25],
        "argmax_delta": float(wide_grid[wb]),
        "concordance_at_argmax": round(float(wconc[wb]), 5),
        "on_boundary": bool(wb in (0, len(wide_grid) - 1)),
        "disclosure": ("the pre-registered grid [-4, 16] returned its LOWER boundary, so it "
                       "did not contain the optimum. Widened once, post hoc, and disclosed. "
                       "Both grids agree the optimum is NEGATIVE, i.e. neither supports the "
                       "retired value 4 nor any positive penalty, so the recommendation is "
                       "the same under either."),
    }
    est["shipped_value_inside_ci95"] = bool(
        est["bootstrap"]["ci95_argmax"][0] <= float(shipped["value"])
        <= est["bootstrap"]["ci95_argmax"][1])
    if verbose:
        print(f"[C] shipped={shipped['value']} at {shipped['file_line']} "
              f"UNCAPPED_GRADE={shipped['uncapped_grade']}")
        print(f"[C] argmax={est['argmax_delta']} conc={est['concordance_at_argmax']} "
              f"at0={est['concordance_at_shipped_0']} at4={est['concordance_at_retired_4']} "
              f"ci={est['bootstrap']['ci95_argmax']}")
    return {"shipped": shipped, "estimator_b": est}


# ===================================================================== legacy
def legacy(verbose=True):
    """Reproduce the incumbent artifact's own protocol on current code and corpus, so the
    four published numbers can be located against the new battery."""
    out = {}
    for side in SIDES:
        is_pit = side == "pit"
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        data = U._prep([r for r in rows
                        if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
                        and not (r.get("kind") == "bust" and r.get("bust_recent"))], side)
        keys = U._keys(side)
        res = {}
        for label, levels, max_age in (("low_minors_age_le21", {"DSL", "CPX", "A"}, 21),
                                       ("all_levels", None, None)):
            P, T = [], []
            for yr in (2019, 2020, 2021, 2022, 2023):
                tr = [r for r in data if r["decision_year"] < yr]
                te = [r for r in data if r["decision_year"] == yr]
                if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
                    continue
                rg = U._fit_ridge(tr, keys)
                cal = U._fit_linear_calibration(
                    [(U._predict(rg, r["feats"]), r["target"]) for r in tr])
                a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
                for r in te:
                    m = r["milb"]
                    if ((levels is None or m.get("milb_level") in levels)
                            and (max_age is None or m.get("age") is None
                                 or m.get("age") <= max_age)):
                        P.append(U._war(rg, a, b, r["feats"]))
                        T.append(r["target"])
            res[label] = {"n": len(P),
                          "spearman_vs_realized_war": (round(U._spearman(P, T), 4)
                                                       if len(P) >= 8 else None)}
        out[side] = res
        if verbose:
            print(f"[legacy] {side}: " + ", ".join(
                f"{k} n={v['n']} rho={v['spearman_vs_realized_war']}" for k, v in res.items()))
    return out


def parity(verbose=True):
    """Harness parity: this lab's numpy chain against efv_ungraded's own python fit, on
    the same fold, same rows. Rule E -- every number must reproduce from the artifact, so
    the harness has to be shown equivalent to the shipped model first."""
    rep = {}
    for side in SIDES:
        D = load_side(side)
        is_pit = side == "pit"
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        data = U._prep([r for r in rows
                        if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
                        and not (r.get("kind") == "bust" and r.get("bust_recent"))], side)
        keys = U._keys(side)
        yr = max(D["years"])
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        rg = U._fit_ridge(tr, keys)
        cal = U._fit_linear_calibration([(U._predict(rg, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        ref_war = np.array([U._war(rg, a, b, r["feats"]) for r in te])
        ref_grade = np.array([U._grade(w, side) for w in ref_war])

        dy = D["dy"]
        trm, tem = np.flatnonzero(dy < yr), np.flatnonzero(dy == yr)
        rg2 = ridge_fit(D["Xp"][trm], D["y"][trm], D["w"][trm])
        a2, b2 = lin_cal(ridge_pred(rg2, D["Xp"][trm]), D["y"][trm])
        my_war = np.maximum(-2.0, a2 + b2 * ridge_pred_clipped(rg2, D["Xp"][tem]))
        my_grade = grade_map(my_war, side)
        rep[side] = {
            "fold": int(yr), "n_test": int(len(te)),
            "cal_shipped": [a, b], "cal_lab": [a2, b2],
            "max_abs_war_diff": round(float(np.max(np.abs(ref_war - my_war))), 9),
            "max_abs_grade_diff": round(float(np.max(np.abs(ref_grade - my_grade))), 9),
            "rho_shipped": round(float(wrho(ref_grade, D["y"][tem], D["w"][tem])), 6),
            "rho_lab": round(float(wrho(my_grade, D["y"][tem], D["w"][tem])), 6),
        }
        rep[side]["pass"] = bool(rep[side]["max_abs_grade_diff"] < 1e-9)
        if verbose:
            print(f"[parity] {side}: war_diff={rep[side]['max_abs_war_diff']} "
                  f"grade_diff={rep[side]['max_abs_grade_diff']} pass={rep[side]['pass']}")
    return rep


def population():
    """The mapping caveat, as numbers, so PROVISIONAL_GATE.md part 1 reproduces here."""
    import collections
    lab = collections.Counter()
    for side in SIDES:
        is_pit = side == "pit"
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        for r in rows:
            if (bool(r.get("is_pitcher")) == is_pit and r.get("milb")
                    and not (r.get("kind") == "bust" and r.get("bust_recent"))):
                lab[(r.get("milb") or {}).get("milb_level")] += 1
    srv = collections.Counter()
    try:
        doc = json.loads((ROOT / "data" / "xfv_ungraded.json").read_text(encoding="utf-8"))
        for e in (doc.get("by_player") or {}).values():
            srv[e.get("level")] += 1
    except Exception:
        pass
    nl, ns = sum(lab.values()), sum(srv.values())
    return {
        "labeled_pool_by_level": dict(lab), "labeled_pool_n": nl,
        "served_provisional_by_level": dict(srv), "served_provisional_n": ns,
        "labeled_pool_share": {k: round(v / nl, 4) for k, v in lab.items()} if nl else {},
        "served_share": {k: round(v / ns, 4) for k, v in srv.items()} if ns else {},
        "note": ("THE MAPPING CAVEAT. Everything in this artifact is measured on the "
                 "labeled pool and applied to the served population, which sits about two "
                 "rungs lower on the ladder. Not repairable inside this lane."),
    }


# ===================================================================== driver
def run_all(B=2000):
    t0 = time.time()
    par = parity()
    leg = legacy()
    bat = battery(B)
    rou = routed(B)
    joint_pt = rou.pop("_joint")
    pen = penalty(joint_pt)

    doc = {
        "population": population(),
        "generated_at": __import__("datetime").date.today().isoformat(),
        "model": "eFV ungraded (no-FV production ridge), PROVISIONAL grades",
        "producer": "python tools/efv_ungraded_gate_lab.py all %d" % B,
        "registration": "docs/efv-2026-08-07b/PROVISIONAL_GATE.md",
        "seed": SEED, "B": int(B),
        "standard": "docs/EFV_GATE_STANDARD.md sections 2, 3 and 7",
        "estimators": {
            "E_refit": "whole-pool paired bootstrap, provisional ridge + linear "
                       "calibration refit on every draw (gate standard section 1)",
            "E_cond": "per-fold fits held fixed, scored rows resampled i.i.d. "
                      "(gate standard section 7 / POWER_GATE.md, E_cond_iid)",
            "convention": "MDE95 is ONE-SIDED (1.645 sd); two-sided and Bonferroni k=4 "
                          "figures are printed beside every one",
        },
        "harness_parity": par,
        "legacy_2026_07_14": {
            "published": {
                "hit": {"low_minors_age_le21": 0.2369, "all_levels": 0.2985},
                "pit": {"low_minors_age_le21": 0.0867, "all_levels": 0.1854}},
            "reproduced_on_current_code_and_corpus": leg,
            "note": ("the incumbent protocol scores efv_ungraded._war unweighted; the "
                     "battery below scores the SERVED GRADE pair-weighted, which is what "
                     "the board actually publishes"),
        },
        "battery": bat,
        "routed": rou,
        "penalty": pen,
        "caveats": [
            "POOL MAPPING: measured on the labeled matrix, which is AA/AAA-heavy, and "
            "applied to a served population that is DSL/CPX-heavy org filler. "
            "PROVISIONAL_GATE.md part 1.",
            "The exposure sub-floor clamp (min(grade,30) below _MIN_EXPO_PA/_MIN_EXPO_BF) "
            "cannot be reproduced historically (no PA/BF column in the matrix) and is NOT "
            "applied to the served-grade analog.",
            "Forward-chained folds share training rows and are sequentially nested, not "
            "independent; clause A5 is a stability check, not a replication.",
            "The corpus moved this session (Baseball America, 1,535 rows), so every number "
            "here is a fresh measurement rather than a replication of the 2026-07-14 one.",
            "This lane changed no shipped constant and flipped no switch.",
        ],
        "runtime_seconds": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print("wrote", OUT_PATH, f"({doc['runtime_seconds']}s)")
    return doc


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    B = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    if cmd == "parity":
        parity()
    elif cmd == "legacy":
        legacy()
    elif cmd == "battery":
        battery(B)
    elif cmd == "routed":
        routed(B)
    elif cmd == "all":
        run_all(B)
    else:
        print(__doc__ or "commands: parity | legacy | battery | routed | all [B]")


if __name__ == "__main__":
    main()
