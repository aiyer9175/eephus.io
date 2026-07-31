# SCRATCH LAB (combinatorial-archetype lane). READ-ONLY w.r.t. shipped code.
#
# THE COMBINATORIAL ARCHETYPE SWEEP, under a pre-registered multiplicity gate.
#
#   prereg   enumerate the candidate strata from FEATURES ONLY, hash + write the artifact,
#            print the exact hypothesis count. No outcome is touched in this mode.
#   run      compute per-stratum n / mean+median realized WAR / bust rate / mean OUT-OF-FOLD
#            RESIDUAL of the shipped model, BH q-values, permutation family-wise null,
#            zero-information control.
#   nested   nested CV on the SEARCH PROCEDURE: run the whole sweep inside each inner loop,
#            score the selected archetype on an untouched outer fold.
#   refit    outcome-permutation null WITH a model refit per draw (the expensive version).
#
# Gate: docs/EFV_GATE_STANDARD.md. Model replica: tools/_frontier_ablate.py.
from __future__ import annotations

import hashlib
import itertools
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import efv_model as E                                                  # noqa: E402
from _frontier_ablate import ridge_fit, ridge_pred, ols_fit, lincal    # noqa: E402
from _comb_axes import load_rows, build_axes, AXIS_META                # noqa: E402

OUT = HERE / "_comb_out"
OUT.mkdir(exist_ok=True)

SEED = 20260725
# ---- PRE-REGISTERED DESIGN CONSTANTS (fixed before any outcome was computed) ---------
ORIGINS = (2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024)
COMPLETE_ORIGINS = (2016, 2017, 2018, 2019, 2020)   # last year whose debuts
                                                   # have a finished 6yr window
MIN_N = 40            # stratum size floor, resolved rows carrying an OOF residual
MAX_FRAC = 0.40       # a stratum covering > 40% of the population is the population
MAX_WAY = 3
N_PERM = 2000         # residual-exchangeability family-wise null
N_REFIT_PERM = 200    # outcome-permutation-with-refit family-wise null
LAM = {"hit": 0.70, "pit": 0.54}   # efv_model.blend_lambda(), live


# ======================================================================= population
def build(side="hit"):
    rows = load_rows(side)
    prep = E._prep(rows, "target_censored", side)
    assert len(prep) == len(rows)
    keys = E._feature_spec(side)[0]
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    y = np.array([r["target"] for r in prep], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], dtype=float)
    dy = np.array([r["decision_year"] for r in prep], dtype=int)
    keep = np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                     for r, o in zip(prep, rows)])
    res = np.array([float(r["target_resolved"]) if isinstance(r.get("target_resolved"),
                                                              (int, float)) else np.nan
                    for r in rows])
    complete = np.array([not bool(r.get("censored")) for r in rows])
    debuted = np.array([r["kind"] == "debuted" for r in rows])
    has_milb = np.array([isinstance(r.get("milb"), dict) for r in rows])
    A, edges = build_axes(rows, side)
    return dict(side=side, rows=rows, X=X, y=y, w=w, fv=fv, dy=dy, keep=keep,
                res=res, complete=complete, deb=debuted, has_milb=has_milb,
                axes=A, edges=edges, keys=keys,
                pk=[r["player_key"] for r in rows])


def crossfit(D, mask_train_extra=None, origins=ORIGINS, seed_shift=0, y=None):
    """Forward-chained OUT-OF-FOLD prediction of the shipped blend for every row whose
    decision_year is an origin. Train = full pool minus bust_recent, decision_year < Y,
    KM weights (the production frame). Test = ALL rows at Y, busts included, because an
    archetype analysis that scores only debuts is survivorship-selected."""
    X, w, fv, dy, keep = D["X"], D["w"], D["fv"], D["dy"], D["keep"]
    y = D["y"] if y is None else y
    lam = LAM[D["side"]]
    pred = np.full(len(y), np.nan)
    tr_ok = keep if mask_train_extra is None else (keep & mask_train_extra)
    for yr in origins:
        tr = np.flatnonzero(tr_ok & (dy < yr))
        te = np.flatnonzero(dy == yr)
        if len(tr) < 60 or len(te) < 10:
            continue
        o = ols_fit(fv[tr], y[tr])
        rg = ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        a, b = lincal(ridge_pred(rg, X[tr]), y[tr])
        mod = np.maximum(-2.0, a + b * ridge_pred(rg, X[te]))
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        pred[te] = (1 - lam) * cons + lam * mod
    return pred


# ======================================================================= enumeration
def axis_names(D, scope="all"):
    ks = [k for k in AXIS_META if k in D["axes"]]
    if scope == "free":
        ks = [k for k in ks if AXIS_META[k][1] == "free"]
    return ks


def enumerate_strata(D, pop_mask, scope="all"):
    """Every 1-, 2- and 3-way stratum over the pre-registered axes, filtered by the
    pre-registered size floor. FEATURES ONLY: no outcome is read here."""
    names = axis_names(D, scope)
    core = [k for k in names if AXIS_META[k][0] == "CORE"]
    A = D["axes"]
    idx = np.flatnonzero(pop_mask)
    N = len(idx)
    lv = {}
    for k in names:
        v = [A[k][i] for i in idx]
        lv[k] = sorted({x for x in v if x is not None})
    memb = {}
    for k in names:
        col = [A[k][i] for i in idx]
        memb[k] = {b: np.array([c == b for c in col]) for b in lv[k]}

    out = []
    seen = set()

    def add(ax, bs):
        m = memb[ax[0]][bs[0]]
        for a, b in zip(ax[1:], bs[1:]):
            m = m & memb[a][b]
        n = int(m.sum())
        if n < MIN_N or n > MAX_FRAC * N:
            return
        sig = m.tobytes()
        if sig in seen:          # identical membership => the same hypothesis
            return
        seen.add(sig)
        out.append({"axes": list(ax), "buckets": list(bs), "n": n,
                    "id": "|".join(f"{a}={b}" for a, b in zip(ax, bs))})

    for k in names:
        for b in lv[k]:
            add((k,), (b,))
    for k1, k2 in itertools.combinations(names, 2):
        for b1 in lv[k1]:
            for b2 in lv[k2]:
                add((k1, k2), (b1, b2))
    if MAX_WAY >= 3:
        for k1, k2, k3 in itertools.combinations(core, 3):
            for b1 in lv[k1]:
                for b2 in lv[k2]:
                    for b3 in lv[k3]:
                        add((k1, k2, k3), (b1, b2, b3))
    return out, N, lv


def indicator(D, strata, pop_idx):
    A = D["axes"]
    M = np.zeros((len(pop_idx), len(strata)), dtype=np.float64)
    for j, s in enumerate(strata):
        m = np.ones(len(pop_idx), dtype=bool)
        for a, b in zip(s["axes"], s["buckets"]):
            m &= np.array([A[a][i] == b for i in pop_idx])
        M[:, j] = m
    return M


# ======================================================================= statistics
def welch_t(M, r):
    """Vectorized stratum-vs-complement Welch t for every column of M against r."""
    n = M.sum(axis=0)
    N = len(r)
    s1 = M.T @ r
    s2 = M.T @ (r * r)
    tot1, tot2 = r.sum(), float((r * r).sum())
    nc = N - n
    m1 = s1 / n
    m2 = (tot1 - s1) / nc
    v1 = np.maximum((s2 - n * m1 * m1) / np.maximum(n - 1, 1), 1e-12)
    v2 = np.maximum(((tot2 - s2) - nc * m2 * m2) / np.maximum(nc - 1, 1), 1e-12)
    se = np.sqrt(v1 / n + v2 / nc)
    return (m1 - m2) / se, m1, m2, n, se


def welch_t_batch(M, R):
    """R is (N x B) permuted residual columns. Returns (K x B) t matrix."""
    n = M.sum(axis=0)[:, None]
    N = R.shape[0]
    nc = N - n
    s1 = M.T @ R
    s2 = M.T @ (R * R)
    tot1 = R.sum(axis=0)[None, :]
    tot2 = (R * R).sum(axis=0)[None, :]
    m1 = s1 / n
    m2 = (tot1 - s1) / nc
    v1 = np.maximum((s2 - n * m1 * m1) / np.maximum(n - 1, 1), 1e-12)
    v2 = np.maximum(((tot2 - s2) - nc * m2 * m2) / np.maximum(nc - 1, 1), 1e-12)
    return (m1 - m2) / np.sqrt(v1 / n + v2 / nc)


def norm_p(t):
    from math import erfc, sqrt
    return np.array([erfc(abs(x) / sqrt(2.0)) for x in np.asarray(t, dtype=float)])


def bh(p):
    p = np.asarray(p, dtype=float)
    m = len(p)
    o = np.argsort(p)
    q = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = o[rank]
        val = min(prev, p[i] * m / (rank + 1))
        q[i] = val
        prev = val
    return q


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()[:16]


# ======================================================================= populations
def populations(D):
    """Pre-registered analysis populations.
      TRACK  = rows carrying a real MiLB block (the served board is 100% these rows;
               item E: efv_model._vec hard-zeroes the milb features for the rest, so
               'missing' is encoded as the DSL value). All axes.
      POOLED = every row at an origin year. Only the milb-free axes, precisely because
               the milb axes are contaminated on this population.
    """
    inorig = np.isin(D["dy"], np.array(ORIGINS))
    return {"TRACK": (inorig & D["has_milb"], "all"),
            "POOLED": (inorig, "free")}


def cmd_prereg(side="hit"):
    """STEP 1. Enumerate the search space from FEATURES ONLY and write it to disk.
    Nothing in this function reads a target, a residual or an outcome."""
    D = build(side)
    pops = populations(D)
    art = {"side": side, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "design": {"origins": list(ORIGINS), "min_n": MIN_N, "max_frac": MAX_FRAC,
                      "max_way": MAX_WAY, "n_perm": N_PERM, "n_refit_perm": N_REFIT_PERM,
                      "lambda": LAM[side],
                      "statistic": "Welch t of stratum-vs-complement mean out-of-fold "
                                   "residual (target_censored - shipped blend prediction)"},
           "axes": {k: {"tier": AXIS_META[k][0], "gate": AXIS_META[k][1],
                        "cut": AXIS_META[k][2], "justification": AXIS_META[k][3]}
                    for k in axis_names(D)},
           "tercile_edges": {k: (None if v is None else [round(v[0], 6), round(v[1], 6)])
                             for k, v in D["edges"].items()},
           "populations": {}}
    for pname, (mask, scope) in pops.items():
        strata, N, lv = enumerate_strata(D, mask, scope)
        art["populations"][pname] = {
            "n_rows": int(N),
            "axis_levels": {k: lv[k] for k in lv},
            "n_hypotheses": len(strata),
            "by_way": {str(w): sum(1 for s in strata if len(s["axes"]) == w)
                       for w in (1, 2, 3)},
            "strata": [{"id": s["id"], "n": s["n"]} for s in strata],
        }
        print(f"[{side}/{pname}] population n={N}  hypotheses={len(strata)}  "
              + "  ".join(f"{w}-way={art['populations'][pname]['by_way'][str(w)]}"
                          for w in ("1", "2", "3")))
    art["prereg_sha256_16"] = sha({p: [s["id"] for s in art["populations"][p]["strata"]]
                                   for p in art["populations"]})
    fp = OUT / f"prereg_{side}.json"
    fp.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print(f"wrote {fp}  sha={art['prereg_sha256_16']}")
    return art



# ======================================================================= STEP 2/3
#
# FOUR RESIDUAL ARMS. The first sweep pass exposed two measurement traps that have to be
# handled in the open, because either one on its own manufactures "archetypes":
#
#  (1) SUB-ZERO PREDICTIONS. 27.5% of out-of-fold predictions are negative WAR, which
#      cannot happen (a bust realizes exactly 0.0), so a raw WAR residual is mechanically
#      positive on any bust-heavy stratum. The whole top of the raw arm was "consensus FV
#      35 or below" restated eleven ways: predmean -0.558 vs ymean +0.157 there, and
#      +8.857 vs +7.860 at FV50+. That is the eFV WAR scale's out-of-fold calibration
#      SLOPE (ridge shrinkage surviving the train-fold lincal), a real and separately
#      reportable finding, but it is not an archetype.
#  (2) THE BUST TIE MASS. 36.4% of rows realize exactly 0.0 WAR, so in rank space they all
#      share one mid-rank. Any stratum sitting at the bottom of the PREDICTION order is
#      then guaranteed a large positive rank residual. The raw rank arm's top was the same
#      FV35- stratum at t +18.3.
#
# Both traps are GLOBAL MONOTONE miscalibrations of the prediction. The fix that removes
# them without touching the model's ordering is to compare against a monotone recalibrated
# prediction: g = isotonic regression of y on pred, CROSS-FITTED (fit on the other origin
# years, applied to the held-out year), so it is not an oracle within the fold. g preserves
# the model's rank exactly, so nothing an archetype could legitimately explain is absorbed.
#
#   R_cal    y - g(pred)          HEADLINE. WAR units, global calibration removed.
#   R_rkcal  pct(y) - h(pct(pred))  rank units (eFV serves a rank), same isotonic fix.
#   R_flr    y - max(0, pred)     what the product literally carries (negative WAR is
#                                 never served).
#   R_war    y - pred             the raw diagnostic that exposed trap (1). Reported.
#
# All four arms are corrected JOINTLY: the family-wise permutation null takes the max over
# every arm and every stratum, i.e. over 4 x K hypotheses, so moving to a better-behaved
# statistic buys no free significance.
ARMS = ("R_cal", "R_rkcal", "R_flr", "R_war")


def _pava(x, y, w=None):
    """isotonic (non-decreasing) regression of y on x. Returns (knots_x, knots_y)."""
    o = np.argsort(x, kind="mergesort")
    xs, ys = x[o], y[o]
    ww = np.ones(len(ys)) if w is None else w[o]
    vals, wts, cnt = [], [], 0
    for i in range(len(ys)):
        vals.append(ys[i])
        wts.append(ww[i])
        cnt += 1
        while cnt > 1 and vals[-2] > vals[-1]:
            v2, w2 = vals.pop(), wts.pop()
            v1, w1 = vals.pop(), wts.pop()
            vals.append((v1 * w1 + v2 * w2) / (w1 + w2))
            wts.append(w1 + w2)
            cnt -= 1
    fit = np.empty(len(ys))
    k = 0
    for v, wt in zip(vals, wts):
        m = 0
        s = 0.0
        # walk forward consuming the weight that formed this block
        while k + m < len(ys) and s < wt - 1e-9:
            s += ww[k + m]
            m += 1
        fit[k:k + m] = v
        k += m
    return xs, fit


def _iso_apply(knots_x, knots_y, xq):
    return np.interp(xq, knots_x, knots_y, left=knots_y[0], right=knots_y[-1])


def _pct_within(v, blk):
    """percentile rank (0..1, ties mid-ranked) within each block"""
    out = np.empty(len(v))
    for b in np.unique(blk):
        m = blk == b
        x = v[m]
        o = x.argsort(kind="mergesort")
        rk = np.empty(len(x))
        rk[o] = np.arange(1, len(x) + 1, dtype=float)
        s = x[o]
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and s[j + 1] == s[i]:
                j += 1
            if j > i:
                rk[o[i:j + 1]] = (i + j) / 2.0 + 1
            i = j + 1
        out[m] = (rk - 0.5) / len(x)
    return out


def _xfit_iso(x, y, blk):
    """cross-fitted isotonic: for each block, fit on the OTHER blocks and apply here."""
    out = np.empty(len(y))
    for b in np.unique(blk):
        m = blk == b
        kx, ky = _pava(x[~m], y[~m])
        out[m] = _iso_apply(kx, ky, x[m])
    return out


def residual_arms(D, idx, pred):
    y, dy = D["y"][idx], D["dy"][idx]
    p = pred[idx]
    py, pp = _pct_within(y, dy), _pct_within(p, dy)
    return {"R_cal": y - _xfit_iso(p, y, dy),
            "R_rkcal": py - _xfit_iso(pp, py, dy),
            "R_flr": y - np.maximum(0.0, p),
            "R_war": y - p}


def prepare(side, pop):
    """Rebuild the pre-registered family and attach the out-of-fold residuals.
    Refuses to proceed if the enumeration no longer matches the pre-registration."""
    art = json.loads((OUT / f"prereg_{side}.json").read_text(encoding="utf-8"))
    D = build(side)
    base = populations(D)
    root = pop[:-1] if pop.endswith("C") else pop
    mask, scope = base[root]
    if pop.endswith("C"):
        # COMPLETE-WINDOW variant. Filtering ROW-WISE on the censored flag is wrong: it
        # deletes every recent DEBUT while keeping every recent bust, so decision years
        # 2021+ become almost pure busts and the rank arm explodes on a composition
        # artifact. Restrict by YEAR instead - through decision_year 2020 every row,
        # debut and bust alike, has a finished 6-season window.
        mask = mask & np.isin(D["dy"], np.array(COMPLETE_ORIGINS))
    strata, _N, _lv = enumerate_strata(D, base[root][0], base[root][1])
    ids = [s["id"] for s in strata]
    assert ids == [s["id"] for s in art["populations"][root]["strata"]], \
        "enumeration drifted from the pre-registration"
    idx = np.flatnonzero(mask)
    pred = crossfit(D)
    assert np.isfinite(pred[idx]).all()
    R = residual_arms(D, idx, pred)
    M = indicator(D, strata, idx)
    keepj = M.sum(axis=0) >= MIN_N        # the C variants lose rows; hold the floor
    return D, art, strata, idx, M, R, len(idx), keepj, pred


def stratum_desc(D, idx, member):
    """Descriptive outcome stats. Realized WAR is read ONLY on rows whose 6-year window
    is complete: a censored row understates. Bust rate = share that never debuted."""
    sub = idx[member.astype(bool)]
    comp = sub[D["complete"][sub]]
    ys = np.sort(D["res"][comp])
    return {"n_complete": int(len(comp)),
            "mean_war": (round(float(ys.mean()), 3) if len(ys) else None),
            "median_war": (round(float(np.median(ys)), 3) if len(ys) else None),
            "bust_rate": (round(float((~D["deb"][comp]).mean()), 3) if len(comp) else None)}


def cmd_run(side="hit", pop="TRACK", nperm=N_PERM, quiet=False):
    t0 = time.time()
    D, art, strata0, idx, M0, R, N, keepj, pred = prepare(side, pop)
    strata = [s for s, k in zip(strata0, keepj) if k]
    M = M0[:, keepj]
    K = len(strata)
    rng = np.random.default_rng(SEED)

    stats = {}
    for a in ARMS:
        t, m1, m2, n, se = welch_t(M, R[a])
        pv = norm_p(t)
        stats[a] = dict(t=t, m1=m1, m2=m2, n=n, se=se, p=pv, q=bh(pv))

    # ---- joint family-wise null: one row permutation per draw applied to ALL arms,
    # max |t| taken over 3 x K hypotheses. Preserves the stratum correlation structure,
    # which a random-strata control does not, so it is the stricter null.
    best = np.empty(nperm)
    per_arm = {a: np.empty(nperm) for a in ARMS}
    done, B = 0, 200
    while done < nperm:
        b = min(B, nperm - done)
        perms = [rng.permutation(N) for _ in range(b)]
        cur = None
        for a in ARMS:
            Rm = np.column_stack([R[a][pm] for pm in perms])
            v = np.abs(welch_t_batch(M, Rm)).max(axis=0)
            per_arm[a][done:done + b] = v
            cur = v if cur is None else np.maximum(cur, v)
        best[done:done + b] = cur
        done += b
    crit = float(np.quantile(best, 0.95))
    crit_arm = {a: float(np.quantile(per_arm[a], 0.95)) for a in ARMS}

    # ---- zero-information control: random strata with IDENTICAL marginal sizes
    nsz = stats[ARMS[0]]["n"]
    Mc = np.zeros_like(M)
    for j in range(K):
        Mc[rng.choice(N, size=int(nsz[j]), replace=False), j] = 1.0
    ctrl = {a: float(np.abs(welch_t(Mc, R[a])[0]).max()) for a in ARMS}

    allt = np.concatenate([np.abs(stats[a]["t"]) for a in ARMS])
    obs_max = float(allt.max())
    recs = []
    for j, s in enumerate(strata):
        d = stratum_desc(D, idx, M[:, j])
        rec = {**s, "way": len(s["axes"]), "n": int(nsz[j]), **d}
        for a in ARMS:
            st = stats[a]
            sd_s = float(np.std(R[a][M[:, j] > 0], ddof=1))
            rec[a] = {"mean": round(float(st["m1"][j]), 4),
                      "rest": round(float(st["m2"][j]), 4),
                      "ci95": [round(float(st["m1"][j] - 1.96 * sd_s / np.sqrt(nsz[j])), 4),
                               round(float(st["m1"][j] + 1.96 * sd_s / np.sqrt(nsz[j])), 4)],
                      "t": round(float(st["t"][j]), 3), "p": float(st["p"][j]),
                      "q": float(st["q"][j])}
        rec["max_abs_t"] = max(abs(rec[a]["t"]) for a in ARMS)
        recs.append(rec)
    recs.sort(key=lambda x: -x["max_abs_t"])

    surv = {a: {"raw_p05": int((stats[a]["p"] < 0.05).sum()),
                "bh_q10": int((stats[a]["q"] < 0.10).sum()),
                "maxstat_95_arm": int((np.abs(stats[a]["t"]) > crit_arm[a]).sum()),
                "maxstat_95_joint": int((np.abs(stats[a]["t"]) > crit).sum()),
                "crit95_arm": round(crit_arm[a], 3),
                "observed_max_abs_t": round(float(np.abs(stats[a]["t"]).max()), 3),
                "perm_p_arm": float((per_arm[a] >= np.abs(stats[a]["t"]).max()).mean())}
            for a in ARMS}
    res = {"side": side, "pop": pop, "n_rows": int(N), "n_hypotheses_per_arm": K,
           "n_hypotheses_family": len(ARMS) * K, "arms": list(ARMS),
           "prereg_sha256_16": art["prereg_sha256_16"],
           "resid_summary": {a: {"mean": round(float(R[a].mean()), 4),
                                 "sd": round(float(R[a].std(ddof=1)), 4)} for a in ARMS},
           "survivors": surv,
           "survivors_family": {
               "raw_p05": int(sum(surv[a]["raw_p05"] for a in ARMS)),
               "bh_q10_joint": int((bh(np.concatenate([stats[a]["p"] for a in ARMS]))
                                    < 0.10).sum()),
               "maxstat_95": int(sum(surv[a]["maxstat_95_joint"] for a in ARMS))},
           "maxstat_null": {"n_perm": int(nperm), "crit95": round(crit, 3),
                            "median": round(float(np.median(best)), 3),
                            "max": round(float(best.max()), 3),
                            "observed_max_abs_t": round(obs_max, 3),
                            "perm_p_of_observed_max": float((best >= obs_max).mean())},
           "zero_info_control": ctrl,
           "survivor_ids": [x["id"] for x in recs if x["max_abs_t"] > crit],
           "perm_draws": [round(float(v), 4) for v in best],
           "top": recs[:80],
           "all_ids_t": {x["id"]: {a: x[a]["t"] for a in ARMS} for x in recs}}
    fp = OUT / ("run_%s_%s.json" % (side, pop))
    fp.write_text(json.dumps(res, indent=1), encoding="utf-8")
    if not quiet:
        print("[%s/%s] n=%d K=%d family=%d  " % (side, pop, N, K, len(ARMS) * K)
              + " ".join("%s:mu%+.3f/sd%.3f" % (a, R[a].mean(), R[a].std(ddof=1))
                         for a in ARMS))
        for a in ARMS:
            print("   %-7s raw p<.05 %5d  BH q<.10 %5d  arm-crit %5.2f  obs max|t| %5.2f"
                  "  survive-arm %3d  survive-joint %3d  perm p %.4f  zero-info %.2f"
                  % (a, surv[a]["raw_p05"], surv[a]["bh_q10"], crit_arm[a],
                     surv[a]["observed_max_abs_t"], surv[a]["maxstat_95_arm"],
                     surv[a]["maxstat_95_joint"], surv[a]["perm_p_arm"], ctrl[a]))
        print("  joint BH q<.10 %d   perm crit95 %.3f   observed max|t| %.3f   perm p %.4f"
              % (res["survivors_family"]["bh_q10_joint"], crit, obs_max,
                 res["maxstat_null"]["perm_p_of_observed_max"]))
        print("  --- top 18 by max |t| across arms ---")
        for x in recs[:18]:
            print("   n=%4d war %7s med %6s bust %5s | cal%+6.2f rk%+6.2f flr%+6.2f raw%+6.2f | %s"
                  % (x["n"], str(x["mean_war"]), str(x["median_war"]), str(x["bust_rate"]),
                     x["R_cal"]["t"], x["R_rkcal"]["t"], x["R_flr"]["t"], x["R_war"]["t"],
                     x["id"]))
        print("  %.1fs -> %s" % (time.time() - t0, fp))
    return res


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prereg"
    sd = sys.argv[2] if len(sys.argv) > 2 else "hit"
    if mode == "prereg":
        cmd_prereg(sd)
    elif mode == "run":
        cmd_run(sd, sys.argv[3] if len(sys.argv) > 3 else "TRACK",
                int(sys.argv[4]) if len(sys.argv) > 4 else N_PERM)
    else:
        raise SystemExit("unknown mode " + mode)
