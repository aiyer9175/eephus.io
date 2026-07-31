# SCRATCH (frontier lane: POOL HITTERS AND PITCHERS INTO ONE MODEL).
# Read-only wrt every shipped module. Writes JSON to tools/_frontier_out/.
# Run: python tools/_frontier_pooled.py            (FP_B=<n> bootstrap draws, default 400)
#
# Question: today eFV fits TWO ridges (hit / pit) on ~350-440 test rows each.
# Does one pooled ridge (side indicator + side-interacted terms + shared columns
# where the feature means the same thing) beat the two separate ridges
#   (1) on OOS rank / MAE per side, and
#   (2) on MEASUREMENT PRECISION (sd of a paired candidate delta)?
#
# Production fit config throughout: train = full pool minus bust_recent, KM sample
# weights, side-specific consensus OLS anchor, side-specific linear calibration,
# side-specific PINNED blend lambda. ONLY the ridge leg changes between arms.

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as em                                    # noqa: E402 (read-only)
from prospect_path import _fit_linear_calibration          # noqa: E402

DATA = ROOT / "data"
OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)

SEED = 20260724
LAM = {"hit": 0.85, "pit": 0.63}          # PINNED served blend weights (never re-derived)
ORIGINS_GATE = (2020, 2021, 2022, 2023)   # the shipped gate's SCORED_YEARS
ORIGINS_REC = (2020, 2021, 2022, 2023, 2024)   # recommended-evaluator window
ALPHAS = (1.0, 10.0, 100.0)
DEV_MULTS = (0.25, 1.0, 4.0, 16.0, 64.0)  # deviation-penalty grid for the hierarchical arm
RIDGE_SEED = 20260707
CONTRIB = 3.0

BASE_KEYS = {s: em._feature_spec(s)[0] for s in ("hit", "pit")}


# --------------------------------------------------------------------- ridge (numpy replica)
def fit_ridge(rows, keys, seed=RIDGE_SEED, pen=None, pen_grid=None):
    """prospect_path._fit_ridge logic (weighted, seeded alpha holdout).
    pen      : per-column penalty multiplier vector (None = all 1.0)
    pen_grid : list of (name, penvec); the holdout picks alpha AND penvec jointly.
    """
    n = len(rows)
    if n < 40:
        return None
    p = len(keys)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in rows], dtype=float)
    y = np.array([r["target"] for r in rows], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in rows], dtype=float), 1e-3, None)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    grid = pen_grid if pen_grid else [("flat", np.ones(p) if pen is None else pen)]

    def wridge(idx, alpha, b, pv):
        Xi, wi = Xs[idx], w[idx]
        WX = Xi * wi[:, None]
        return np.linalg.solve(WX.T @ Xi + alpha * np.diag(pv), WX.T @ (y[idx] - b))

    order = np.random.default_rng(seed).permutation(n)
    k = max(1, n // 5)
    ho, tri = order[:k], order[k:]
    b_tr = float(np.average(y[tri], weights=w[tri]))
    best = None
    for gname, pv in grid:
        for alpha in ALPHAS:
            ww = wridge(tri, alpha, b_tr, pv)
            mae = float(np.average(np.abs(Xs[ho] @ ww + b_tr - y[ho]), weights=w[ho]))
            if best is None or mae < best[0]:
                best = (mae, alpha, pv, gname)
    b = float(np.average(y, weights=w))
    return {"keys": keys, "mu": mu, "sd": sd,
            "w": wridge(np.arange(n), best[1], b, best[2]), "b": b,
            "alpha": best[1], "pen": best[3]}


def predict(model, rows):
    X = np.array([[r["feats"].get(k, 0.0) for k in model["keys"]] for r in rows], dtype=float)
    return ((X - model["mu"]) / model["sd"]) @ model["w"] + model["b"]


def fit_ols_fv(rows):
    fv = np.array([r["fv"] for r in rows], dtype=float)
    y = np.array([r["target"] for r in rows], dtype=float)
    if len(rows) < 10 or fv.std() == 0:
        return None
    b = float(((fv - fv.mean()) * (y - y.mean())).sum() / ((fv - fv.mean()) ** 2).sum())
    return (float(y.mean() - b * fv.mean()), b)


# --------------------------------------------------------------------- feature sets
SHARED = ["fv", "age_rel_level", "age", "level_rank", "n_milb_seasons", "milb_missing",
          "is_ifa", "is_college", "k_skill", "peak_k_skill", "tool_best"]
SIDE_SPEC = ["h_obp_rel", "h_ops_rel", "h_tool_speed", "p_bb_rel", "p_x_era_k"]
UNION = SHARED + SIDE_SPEC

POOL_P1 = ["is_pit"] + UNION                                    # side indicator only
POOL_P2 = ["is_pit", "pit_x_fv"] + UNION                        # + side-interacted FV slope
POOL_P3 = ["is_pit"] + UNION + ["dev_" + k for k in SHARED]     # + hierarchical deviations
POOL_P4 = (["is_pit"] + ["hit_" + k for k in BASE_KEYS["hit"]]
           + ["pit_" + k for k in BASE_KEYS["pit"]])            # FULL interaction (~= separate)

# --- P6: the CLEAN pooling continuum -------------------------------------------
# Exactly the union of the two SHIPPED key sets (no extra features), split into
#   COMMON6  features present on both sides with the same meaning -> main + deviation
#   side-only features                                            -> zero-filled side columns
# dev penalty -> 0  reproduces the two separate models (== p4 == sep)
# dev penalty -> inf forces one shared coefficient per common feature (full pooling)
COMMON6 = ["fv", "age_rel_level", "age", "k_skill", "peak_k_skill", "tool_best"]
HIT_ONLY = ["obp_rel", "ops_rel", "tool_speed", "n_milb_seasons", "milb_missing",
            "is_ifa", "is_college", "level_rank"]
PIT_ONLY = ["bb_rel", "x_era_k"]
POOL_P6 = (["is_pit"] + COMMON6 + ["dev_" + k for k in COMMON6]
           + ["hit_" + k for k in HIT_ONLY] + ["pit_" + k for k in PIT_ONLY])

ARM_KEYS = {"p1": POOL_P1, "p2": POOL_P2, "p3": POOL_P3, "p4": POOL_P4,
            "p5": POOL_P3, "p6": POOL_P6}


def pen_grid_for(arm, keys, cand):
    """p5 = hierarchical: holdout jointly selects alpha and the deviation penalty."""
    if arm != "p5":
        return None
    grid = []
    isdev = np.array([1.0 if k.startswith("dev_") else 0.0 for k in keys + cand])
    for m in DEV_MULTS:
        grid.append(("dev%g" % m, np.where(isdev > 0, m, 1.0)))
    return grid


# --------------------------------------------------------------------- data
def load_pool():
    rng = random.Random(SEED)
    pool = {}
    for side, fn in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        raw = json.loads((DATA / fn).read_text(encoding="utf-8"))
        out = []
        for r in raw:
            p = em._prep([r], "target_censored", side)
            if not p:
                continue
            d = p[0]
            d["side"] = side
            d["bust_recent"] = bool(r.get("bust_recent"))
            f = d["feats"]
            sgn = 1.0 if side == "pit" else -1.0        # k-rate -> "missing bats is skill"
            f["is_pit"] = 1.0 if side == "pit" else 0.0
            f["pit_x_fv"] = f["is_pit"] * f["fv"]
            f["k_skill"] = sgn * f.get("k_rel", 0.0)
            f["peak_k_skill"] = sgn * f.get("peak_k_rel", 0.0)
            f["tool_best"] = f.get("tool_fb", 0.0) if side == "pit" else f.get("tool_hit", 0.0)
            f["h_obp_rel"] = f.get("obp_rel", 0.0) if side == "hit" else 0.0
            f["h_ops_rel"] = f.get("ops_rel", 0.0) if side == "hit" else 0.0
            f["h_tool_speed"] = f.get("tool_speed", 0.0) if side == "hit" else 0.0
            f["p_bb_rel"] = f.get("bb_rel", 0.0) if side == "pit" else 0.0
            f["p_x_era_k"] = f.get("x_era_k", 0.0) if side == "pit" else 0.0
            for k in SHARED:
                f["dev_" + k] = sgn * f.get(k, 0.0)
            f.setdefault("prod_trend", 0.0)
            for j in range(24):                          # zero-information placebo columns
                f["_z%02d" % j] = rng.gauss(0.0, 1.0)
            # full-interaction (p4/p6) columns: zero off-side
            extra = ["prod_trend"] + ["_z%02d" % j for j in range(24)]
            for k in list(BASE_KEYS["hit"]) + extra:
                f["hit_" + k] = f.get(k, 0.0) if side == "hit" else 0.0
            for k in list(BASE_KEYS["pit"]) + extra:
                f["pit_" + k] = f.get(k, 0.0) if side == "pit" else 0.0
            for k in extra:
                f["dev_" + k] = sgn * f.get(k, 0.0)
            out.append(d)
        pool[side] = out
    return pool


def cand_keys(arm, cand):
    """Map a candidate feature name into the arm's parameterization."""
    if not cand:
        return []
    if arm == "sep":
        return list(cand)                     # appended to each side's own key list
    if arm in ("p4", "p6"):                   # one fit, but two free coefficients (as `sep` has)
        return ["hit_" + c for c in cand] + ["pit_" + c for c in cand]
    return list(cand)                         # p1/p2/p3: ONE shared coefficient


# --------------------------------------------------------------------- scoring
def score(pool, arm, origins=ORIGINS_REC, cand=None, ridge_seed=RIDGE_SEED, drop=None):
    """Forward-chained production-analogue scoring -> [(side, year, blend, target, fv)]."""
    cand = list(cand or [])
    drop = set(drop or [])
    allrows = pool["hit"] + pool["pit"]
    tr_all = [r for r in allrows if not (r["kind"] == "bust" and r["bust_recent"])]
    recs = []
    for yr in origins:
        tr_pool = [r for r in tr_all if r["decision_year"] < yr]
        pooled_ridge = None
        if arm != "sep":
            base = [k for k in ARM_KEYS[arm] if k not in drop]
            extra = cand_keys(arm, cand)
            pooled_ridge = fit_ridge(tr_pool, base + extra, ridge_seed,
                                     pen_grid=pen_grid_for(arm, base, extra))
            if pooled_ridge is None:
                continue
        for side in ("hit", "pit"):
            tr = [r for r in tr_pool if r["side"] == side]
            te = [r for r in pool[side] if r["kind"] == "debuted" and r["decision_year"] == yr]
            if len(te) < 15 or len(tr) < 60:
                continue
            ols = fit_ols_fv(tr)
            if arm == "sep":
                ks = [k for k in BASE_KEYS[side] if k not in drop] + cand
                model = fit_ridge(tr, ks, ridge_seed)
            else:
                model = pooled_ridge
            if ols is None or model is None:
                continue
            ptr = predict(model, tr)
            c = _fit_linear_calibration([(float(p), r["target"]) for p, r in zip(ptr, tr)])
            a, b = (c["a"], c["b"]) if c else (0.0, 1.0)
            lam = LAM[side]
            for r, pm in zip(te, predict(model, te)):
                cons = max(0.0, ols[0] + ols[1] * r["fv"])
                mod = max(-2.0, a + b * float(pm))
                recs.append((side, yr, (1 - lam) * cons + lam * mod, r["target"], r["fv"]))
    return recs


# --------------------------------------------------------------------- metrics
def _rank(v):
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
    return r


def rho(p, t):
    if len(p) < 8:
        return float("nan")
    rp, rt = _rank(p), _rank(t)
    rp = rp - rp.mean(); rt = rt - rt.mean()
    d = math.sqrt(float((rp * rp).sum()) * float((rt * rt).sum()))
    return float((rp * rt).sum() / d) if d > 0 else float("nan")


def _auc(scores, labels):
    labels = np.asarray(labels, dtype=bool)
    npos, nneg = int(labels.sum()), int((~labels).sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    r = _rank(scores)
    return float((r[labels].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def metrics(recs):
    out = {}
    per = {}
    for s, y, p, t, fv in recs:
        per.setdefault(s, []).append((y, p, t, fv))
    for side in ("hit", "pit"):
        g = [x for x in per.get(side, []) if x[0] in ORIGINS_GATE]
        if not g:
            continue
        P = np.array([x[1] for x in g]); T = np.array([x[2] for x in g])
        FV = np.array([x[3] for x in g])
        out["rho_" + side] = rho(P, T)
        out["mae_" + side] = float(np.abs(P - T).mean())
        out["n_" + side] = len(g)
        sel = (np.round(FV / 5.0) * 5.0) == 45.0
        out["t45_" + side] = rho(P[sel], T[sel]) if sel.sum() >= 15 else float("nan")
    blocks = {}
    for s, y, p, t, fv in recs:
        blocks.setdefault((s, y), []).append((p, t))
    Pp, Tt, Yy = [], [], []
    for g in blocks.values():
        if len(g) < 8:
            continue
        n = len(g)
        Pp.append((_rank([x[0] for x in g]) - 0.5) / n)
        Tt.append((_rank([x[1] for x in g]) - 0.5) / n)
        Yy.append(np.array([x[1] for x in g], dtype=float))
    if Pp:
        Pp = np.concatenate(Pp); Tt = np.concatenate(Tt); Yy = np.concatenate(Yy)
        out["block_rho"] = rho(Pp, Tt)
        out["cauc"] = _auc(Pp, Yy >= CONTRIB)
        out["n_block"] = int(len(Pp))
    return out


KEYSTATS = ["rho_hit", "rho_pit", "mae_hit", "mae_pit", "t45_hit", "t45_pit", "block_rho", "cauc"]


def resample(pool, rng):
    """Stratified by (side, decision_year); players with replacement; TRAIN AND TEST."""
    strata = {}
    for side in ("hit", "pit"):
        for r in pool[side]:
            strata.setdefault((side, r["decision_year"]), []).append(r)
    out = {"hit": [], "pit": []}
    for (side, _), rows in strata.items():
        n = len(rows)
        for i in rng.integers(0, n, n):
            out[side].append(rows[i])
    return out


def summ(d):
    d = np.asarray(d, dtype=float)
    d = d[np.isfinite(d)]
    if len(d) < 10:
        return None
    return {"mean": float(d.mean()), "sd": float(d.std(ddof=1)),
            "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
            "p_gt0": float((d > 0).mean()), "n": int(len(d))}


# =========================================================================== main
def main():
    t0 = time.time()
    pool = load_pool()
    print("[pool] hit=%d pit=%d  (%.0fs)" % (len(pool["hit"]), len(pool["pit"]), time.time() - t0),
          flush=True)

    arms = ["sep", "p1", "p2", "p3", "p4", "p5"]
    point = {a: metrics(score(pool, a)) for a in arms}
    print("\n=== POINT ESTIMATES (production fit; test = debuted rows) ===")
    hdr = "arm   rho_hit  rho_pit  mae_hit  mae_pit  t45_hit  t45_pit  block_rho  cauc"
    print(hdr)
    for a in arms:
        m = point[a]
        print("%-5s %7.4f %8.4f %8.4f %8.4f %8.4f %8.4f %10.4f %6.4f"
              % (a, m["rho_hit"], m["rho_pit"], m["mae_hit"], m["mae_pit"],
                 m["t45_hit"], m["t45_pit"], m["block_rho"], m["cauc"]))
    print("n_hit=%d n_pit=%d n_block=%d" % (point["sep"]["n_hit"], point["sep"]["n_pit"],
                                            point["sep"]["n_block"]))

    # ---------------- paired bootstrap: every pooled arm vs the separate baseline
    B = int(os.environ.get("FP_B", "400"))
    rng = np.random.default_rng(SEED)
    draws = {a: {k: [] for k in KEYSTATS} for a in arms}
    for bi in range(B):
        rp = resample(pool, rng)
        for a in arms:
            m = metrics(score(rp, a))
            for k in KEYSTATS:
                draws[a][k].append(m.get(k, float("nan")))
        if (bi + 1) % 50 == 0:
            print("  boot %d/%d  %.0fs" % (bi + 1, B, time.time() - t0), flush=True)

    print("\n=== PAIRED BOOTSTRAP (B=%d, resample TRAIN+TEST, refit) : pooled - separate ===" % B)
    boot = {}
    for a in arms[1:]:
        print("-- %s" % a)
        boot[a] = {}
        for k in KEYSTATS:
            s = summ(np.array(draws[a][k]) - np.array(draws["sep"][k]))
            if not s:
                continue
            boot[a][k] = s
            pt = point[a].get(k, float("nan")) - point["sep"].get(k, float("nan"))
            print("   %-9s point %+0.4f | mean %+0.4f sd %0.4f CI95 [%+0.4f,%+0.4f] P(>0)=%.3f"
                  % (k, pt, s["mean"], s["sd"], s["lo"], s["hi"], s["p_gt0"]))

    print("\n=== ARM-LEVEL sd (unpaired) ===")
    armsd = {}
    for a in arms:
        armsd[a] = {}
        for k in ("rho_hit", "rho_pit", "block_rho"):
            s = summ(draws[a][k])
            armsd[a][k] = s["sd"] if s else None
            print("   %-4s %-10s sd %0.4f" % (a, k, s["sd"] if s else float("nan")))

    json.dump({"point": point, "B": B, "boot": boot, "armsd": armsd,
               "draws": {a: {k: list(map(float, draws[a][k])) for k in KEYSTATS} for a in arms}},
              open(OUT / "_scratch_pooled.json", "w"), indent=1)
    print("total %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
