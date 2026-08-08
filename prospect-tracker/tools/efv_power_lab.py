# eFV POWER / ESTIMATOR lab (LANE A1, 2026-08-07b).
#
# WHY THIS FILE EXISTS. The hitter full_pool_km margin (-0.0215 on n 1792) is a NULL
# under the shipped paired bootstrap (MDE95 0.0297, 0.72x) and a RESOLVABLE LOSS under
# a bootstrap that holds the fits fixed and resamples only the scored rows (MDE95
# 0.0204, 1.05x). The published claim does not say which estimator it is about. This
# lab settles that by checking each estimator against ITS OWN estimand.
#
# REGISTRATION: docs/efv-2026-08-07b/POWER_GATE.md, parts 0-4, written in full BEFORE
# this file existed. Part 5 is a placeholder filled after the run. Read it first.
#
# THE TRAP. A tighter floor looks like progress and is usually power laundering. The
# criterion here is NOT "is it tighter", it is "does it cover its own estimand at 95%",
# and the gate is coded TWO-SIDED: over-coverage fails exactly like under-coverage.
# The existing coverage gate in tools/efv_cohort_floor_lab.py is `coverage_95 >= 0.90`
# with no upper bound and cannot see over-coverage at all; mode `onesided_defect`
# demonstrates that on the wave-1 numbers.
#
# THIS WAVE CHANGES NO SHIPPED FLOOR CONSTANT. Nothing here retires the shipped floor,
# reopens a closed arm, or retroactively resolves a past null.
#
# Primitives (ridge_fit / ridge_pred / ols_fit / wrho) are IMPORTED from
# tools/efv_mde_lab.py, never reimplemented, so every floor in this file is comparable
# to data/xfv_mde_floor.json and data/xfv_cohort_floors.json.
#
# Run: python tools/efv_power_lab.py repro          reproduce the wave-1 numbers
#      python tools/efv_power_lab.py decomp         variance decomposition (control 3.3)
#      python tools/efv_power_lab.py detect [B]     real-data `fv` detection (3.1)
#      python tools/efv_power_lab.py coverage [NC]  EXP-1 + EXP-2, the gate (part 2)
#      python tools/efv_power_lab.py power          simulated power / type-I (3.2)
#      python tools/efv_power_lab.py verdict [B]    the four cuts under both estimators
#      python tools/efv_power_lab.py all [B]        everything + write the ledger
from __future__ import annotations

import json
import math
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

import efv_model as E                                          # noqa: E402  read-only
from efv_mde_lab import ridge_fit, ridge_pred, ols_fit, wrho    # noqa: E402
from efv_cohort_floor_lab import load_pool                      # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_power_eval.json"
SEED = 20260807
SIDES = ("hit", "pit")
Z95_ONE = 1.645
Z95_TWO = 1.96
Z_BONF4_ONE = 2.2414   # one-sided alpha 0.05/4 = 0.0125
N_CHECK = 200          # fixed in POWER_GATE.md part 2 so over-coverage can fail
SD_BAND = (0.90, 1.10)  # self-added, reported, NOT the registration criterion


# ===================================================================== chain
def chain_full(D, sel=None, years=None, lam=None, min_test=15, min_train=60,
               drop_feat=None, keep_fits=False):
    """Forward-chained consensus + blend, returning the pooled scored rows.

    Structurally identical to efv_mde_lab.chain / efv_cohort_floor_lab.chain. Two
    additions this lane needs:
      drop_feat  index of a feature column to remove from the ridge (detection check)
      keep_fits  also return the per-fold (ols, ridge) fits and the per-fold test row
                 indices, which is what the conditional estimator needs.
    """
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"] if lam is None else lam
    if sel is None:
        sel = np.arange(D["n"])
    X, y, w, fv, dy = D["X"][sel], D["y"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    if drop_feat is not None:
        X = np.delete(X, drop_feat, axis=1)
    C, B, T, W, YR, FITS = [], [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < min_test or len(tr) < min_train:
            continue
        o = ols_fit(fv[tr], y[tr])
        rg = ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = ridge_pred(rg, X[te])
        C.append(cons)
        B.append((1 - lam) * cons + lam * mod)
        T.append(y[te])
        W.append(w[te])
        YR.append(np.full(len(te), yr))
        if keep_fits:
            FITS.append({"yr": yr, "ols": o, "ridge": rg, "n_te": int(len(te))})
    if not B:
        return None
    out = {"cons": np.concatenate(C), "blend": np.concatenate(B),
           "y": np.concatenate(T), "w": np.concatenate(W), "yr": np.concatenate(YR)}
    if keep_fits:
        out["fits"] = FITS
    return out


def delta_of(r, idx=None, weighted=True):
    if r is None:
        return float("nan")
    sl = slice(None) if idx is None else idx
    c, b, y = r["cons"][sl], r["blend"][sl], r["y"][sl]
    if len(y) < 8:
        return float("nan")
    w = r["w"][sl] if weighted else None
    return wrho(b, y, w) - wrho(c, y, w)


def legs_of(r, weighted=True):
    w = r["w"] if weighted else None
    c = wrho(r["cons"], r["y"], w)
    b = wrho(r["blend"], r["y"], w)
    return {"n": int(len(r["y"])), "consensus": round(c, 5), "blend": round(b, 5),
            "delta": round(b - c, 5)}


def summarize(draws, point, z=Z95_ONE, tag="MDE95"):
    a = np.asarray(draws, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 20:
        return {"B_used": int(len(a)), "point_delta": round(float(point), 5),
                "sd": None, tag: None, "verdict": "UNMEASURABLE"}
    sd = float(a.std(ddof=1))
    fl = z * sd
    return {
        "B_used": int(len(a)),
        "point_delta": round(float(point), 5),
        "boot_mean_delta": round(float(a.mean()), 5),
        "sd": round(sd, 5),
        tag: round(fl, 4),
        "mde95_twosided": round(Z95_TWO * sd, 4),
        "ci95": [round(float(np.percentile(a, 2.5)), 5),
                 round(float(np.percentile(a, 97.5)), 5)],
        "p_gt_0": round(float((a > 0).mean()), 4),
        "margin_over_floor": round(abs(float(point)) / fl, 3) if fl > 0 else None,
        "resolvable": bool(abs(float(point)) >= fl),
        "verdict": ("RESOLVABLE " + ("WIN" if point > 0 else "LOSS")
                    if abs(float(point)) >= fl else "NULL"),
    }


# ===================================================================== estimators
def boot_refit(D, B, rng, weighted=True, years=None, min_test=15, min_train=60):
    """E_refit, the SHIPPED estimator. Resample the whole pool, refit every draw."""
    out = []
    for _ in range(B):
        r = chain_full(D, rng.integers(0, D["n"], D["n"]), years=years,
                       min_test=min_test, min_train=min_train)
        out.append(delta_of(r, weighted=weighted))
    return out


def boot_cond(r, B, rng, weighted=True, stratify=False):
    """E_cond, the CANDIDATE. Fits are already fixed inside `r`; resample scored rows.

    stratify=False -> E_cond_iid   (PRIMARY, the scheme wave 1 measured)
    stratify=True  -> E_cond_strat (SENSITIVITY, preserves each fold's test n)
    """
    n = len(r["y"])
    out = []
    if stratify:
        blocks = [np.flatnonzero(r["yr"] == u) for u in np.unique(r["yr"])]
        for _ in range(B):
            idx = np.concatenate([b[rng.integers(0, len(b), len(b))] for b in blocks])
            out.append(delta_of(r, idx, weighted=weighted))
    else:
        for _ in range(B):
            out.append(delta_of(r, rng.integers(0, n, n), weighted=weighted))
    return out


def boot_train_only(D, B, rng, weighted=True):
    """Control 3.3 leg: resample and refit on the TRAIN rows only, test rows fixed.

    Each fold's train block is resampled with replacement inside the fold's own train
    window, so the test rows scored are exactly the real ones and the only varying
    input is the fit.
    """
    years = tuple(E.SCORED_YEARS)
    lam = D["lam"]
    X, y, w, fv, dy = D["X"], D["y"], D["w"], D["fv"], D["dy"]
    out = []
    for _ in range(B):
        C, Bl, T, W = [], [], [], []
        for yr in years:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 15 or len(tr) < 60:
                continue
            rs = tr[rng.integers(0, len(tr), len(tr))]
            o = ols_fit(fv[rs], y[rs])
            rg = ridge_fit(X[rs], y[rs], w[rs])
            if o is None or rg is None:
                continue
            cons = np.maximum(0.0, o[0] + o[1] * fv[te])
            C.append(cons)
            Bl.append((1 - lam) * cons + lam * ridge_pred(rg, X[te]))
            T.append(y[te])
            W.append(w[te])
        if not Bl:
            out.append(float("nan"))
            continue
        r = {"cons": np.concatenate(C), "blend": np.concatenate(Bl),
             "y": np.concatenate(T), "w": np.concatenate(W)}
        out.append(delta_of(r, weighted=weighted))
    return out


# ===================================================================== repro
def repro():
    print("=== REPRO: the wave-1 numbers this lane is about ===")
    out = {}
    art = json.loads((ROOT / "data" / "xfv_eval.json").read_text(encoding="utf-8"))
    p = art["evals"]["full_pool_km"]["pooled_oos"]
    cons = float(p["baseline"]["spearman"])
    blend = float(p["blend"]["spearman"])
    out["artifact_hit_full_pool_km"] = {
        "n": p["baseline"]["n"], "consensus": cons, "blend": blend,
        "delta": round(blend - cons, 5),
        "source": ("data/xfv_eval.json evals.full_pool_km.pooled_oos "
                   "(baseline.spearman vs blend.spearman)"),
    }
    cf = json.loads((ROOT / "data" / "xfv_cohort_floors.json").read_text(encoding="utf-8"))
    w1 = cf["i4_full_pool"]["hit"]["weighted"]
    out["wave1_refit_floor"] = {
        "sd": w1["sd"], "mde95_onesided": w1["mde95_onesided"],
        "margin_over_floor": w1["margin_over_floor"], "verdict": w1["verdict"],
        "source": "data/xfv_cohort_floors.json i4_full_pool.hit.weighted",
    }
    nc = cf["null_coverage_check"]
    out["wave1_null_coverage"] = {
        "pooled_sd_ratio": nc["pooled"]["sd_ratio_boot_over_true"],
        "pooled_coverage_95": nc["pooled"]["coverage_95"],
        "cell_sd_ratio": nc["cell_restricted"]["sd_ratio_boot_over_true"],
        "cell_coverage_95": nc["cell_restricted"]["coverage_95"],
        "gate_as_coded": "coverage_95 >= 0.90, NO UPPER BOUND",
        "source": "data/xfv_cohort_floors.json null_coverage_check",
    }
    for k, v in out.items():
        print(f"  {k}: {json.dumps(v)}")
    return out


def onesided_defect():
    """Show, arithmetically, what the existing one-sided gate cannot see."""
    cf = json.loads((ROOT / "data" / "xfv_cohort_floors.json").read_text(encoding="utf-8"))
    nc = cf["null_coverage_check"]
    rows = []
    for key in ("pooled", "cell_restricted"):
        v = nc[key]
        cov = float(v["coverage_95"])
        rows.append({
            "leg": key,
            "coverage_95": cov,
            "sd_ratio_boot_over_true": v["sd_ratio_boot_over_true"],
            "one_sided_gate_verdict": "PASS" if cov >= 0.90 else "FAIL",
            "two_sided_binomial_verdict": binom_gate(int(round(cov * v["n_checked"])),
                                                     int(v["n_checked"]))["verdict"],
            "n_checked": int(v["n_checked"]),
        })
    out = {
        "defect": ("tools/efv_cohort_floor_lab.py nullcov codes passes = coverage_95 "
                   ">= 0.90 with no upper bound. An over-wide floor therefore reads as "
                   "PASS. For a program whose product is NULL verdicts, over-wide is "
                   "the PERMISSIVE direction."),
        "legs": rows,
        "note": ("n_checked was 40 in wave 1, so even a two-sided binomial region has a "
                 "weak upper edge there; the defect is the missing upper bound, not the "
                 "sample size alone."),
    }
    print("=== ONE-SIDED GATE DEFECT ===")
    for r in rows:
        print(f"  {r['leg']:<16} coverage {r['coverage_95']:.3f} sd_ratio "
              f"{r['sd_ratio_boot_over_true']} -> one-sided {r['one_sided_gate_verdict']}, "
              f"two-sided {r['two_sided_binomial_verdict']}")
    return out


# ===================================================================== binomial gate
def _binom_pmf(k, n, p):
    return math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                    + k * math.log(p) + (n - k) * math.log1p(-p))


def binom_region(n, p=0.95, level=0.95):
    """Central `level` acceptance region for Binomial(n, p): smallest [lo, hi] with
    P(lo <= X <= hi) >= level, trimming equal tail mass."""
    pm = [_binom_pmf(k, n, p) for k in range(n + 1)]
    cum = np.cumsum(pm)
    tail = (1 - level) / 2
    lo = int(np.searchsorted(cum, tail, side="right"))
    hi = int(np.searchsorted(cum, 1 - tail, side="left"))
    return lo, min(hi, n)


def binom_gate(k, n, p=0.95, level=0.95):
    lo, hi = binom_region(n, p, level)
    if k < lo:
        v = "FAIL UNDER-COVERS"
    elif k > hi:
        v = "FAIL OVER-COVERS"
    else:
        v = "PASS"
    return {"k": int(k), "n": int(n), "coverage": round(k / n, 4),
            "accept_lo": lo, "accept_hi": hi,
            "accept_coverage_band": [round(lo / n, 4), round(hi / n, 4)],
            "verdict": v}


# ===================================================================== synthetic DGP
# DGP constants, fitted ONCE to the real hitter full pool on three marginals that
# drive Spearman variance (consensus rho, target zero share, target sd). See
# `dgp_match` for the reproduction of the match. They are structural constants of the
# simulation, not tuning knobs on any result: nothing in part 2's gate depends on them
# beyond the design being realistic.
DGP_A, DGP_C, DGP_S, DGP_DF = 0.7, 50.0, 8.0, 5.0
DGP_ALT_GAIN = 0.2     # orthogonal-signal strength; puts the alternative's true delta
#                        at about +0.031, i.e. just above the real shipped floor, so the
#                        power table is informative rather than trivially saturated.


def make_dgp(real, alt=False):
    """Design-matched synthetic generator, built from the REAL hitter full pool.

    Matched: n, the 11 fold sizes, k = 14 features, lambda, the `fv` and weight
    marginals (resampled from the real ones), and the target's consensus rho, zero
    share and sd.

    Feature structure. Column 0 is `fv` itself, exactly as in the real spec. Columns
    1-3 are noisy copies of `fv`. Columns 4+ are pure noise. Under the NULL every
    column is conditionally uninformative given `fv`, so the model carries NO
    information the consensus lacks, while the noise columns still give the ridge
    genuine estimation variance, which is the quantity in dispute.

    Alternative (alt=True): column 4 becomes a noisy read of the component of the
    target that is ORTHOGONAL to `fv`, so the model does carry information the
    consensus cannot have.
    """
    fv_pool = real["fv"].copy()
    w_pool = real["w"].copy()
    n = real["n"]
    k = real["X"].shape[1]
    lam = real["lam"]

    # Fold sizes are FIXED across every synthetic draw, exactly as they are fixed in the
    # real forward chain. Without this the conditional experiment would confound a change
    # of fold size with a redraw of the scored sample.
    dy_fixed = np.sort(real["dy"])
    years = tuple(y for y in E.SCORED_YEARS if (dy_fixed == y).sum() >= 15)
    dy_pool = real["dy"].copy()

    def gen(seed, vary_folds=False):
        g = np.random.default_rng(seed)
        idx = g.integers(0, n, n)
        fv = fv_pool[idx]
        w = w_pool[idx]
        dy_fixed_local = np.sort(dy_pool[idx]) if vary_folds else dy_fixed
        z = g.standard_t(DGP_DF, n)                 # noise, orthogonal to fv
        y = np.maximum(0.0, DGP_A * (fv - DGP_C) + DGP_S * z)
        cols = [fv]
        cols += [fv + g.normal(0, 6.0, n) for _ in range(3)]
        cols += [g.normal(0, 1.0, n) for _ in range(k - 4)]
        X = np.column_stack(cols)
        if alt:
            X[:, 4] = DGP_ALT_GAIN * z + g.normal(0, 1.0, n)
        return {"X": X, "y": y, "w": w, "fv": fv, "dy": dy_fixed_local,
                "lam": lam, "n": n}

    return gen, years


def dgp_match(verbose: bool = True):
    """Reproduce the three marginals the DGP is matched on, real against synthetic."""
    real = load_pool("hit", "full")
    gen, years = make_dgp(real, alt=False)
    r_real = chain_full(real)
    D = gen(SEED + 77)
    r_syn = chain_full(D, years=years)
    out = {
        "real": {"n": real["n"], "target_zero_share": round(float((real["y"] <= 0).mean()), 3),
                 "target_sd": round(float(real["y"].std()), 3),
                 "consensus_rho_oos": round(wrho(r_real["cons"], r_real["y"], r_real["w"]), 4),
                 "folds": len(np.unique(r_real["yr"])), "k_features": int(real["X"].shape[1])},
        "synthetic": {"n": D["n"], "target_zero_share": round(float((D["y"] <= 0).mean()), 3),
                      "target_sd": round(float(D["y"].std()), 3),
                      "consensus_rho_oos": round(wrho(r_syn["cons"], r_syn["y"], r_syn["w"]), 4),
                      "folds": len(np.unique(r_syn["yr"])), "k_features": int(D["X"].shape[1])},
        "params": {"a": DGP_A, "c": DGP_C, "s": DGP_S, "t_df": DGP_DF,
                   "alt_gain": DGP_ALT_GAIN},
    }
    rng = np.random.default_rng(SEED + 78)
    r_syn_f = chain_full(D, years=years, keep_fits=True)
    for nm, D_, r_ in (("real", real, r_real), ("synthetic", D, r_syn_f)):
        yy = None if nm == "real" else years
        sh = float(np.nanstd(np.asarray(boot_refit(D_, 200, rng, years=yy)), ddof=1))
        te = float(np.nanstd(np.asarray(boot_cond(r_, 200, rng)), ddof=1))
        out[nm]["boot_sd_shipped"] = round(sh, 5)
        out[nm]["boot_sd_test_only"] = round(te, 5)
        out[nm]["shipped_over_test_sd_ratio"] = round(sh / te, 3)
    out["limitation"] = (
        "the synthetic matches the real design on n, folds, k, lambda, the fv and weight "
        "marginals, the target's zero share, sd and consensus rho, and it reproduces the "
        "shipped-over-test sd RATIO, which is the structural quantity this lane is about. "
        "Its ABSOLUTE bootstrap sds run about 0.7x the real ones. Coverage is a relative "
        "property so the part-2 gate is unaffected, but the sd_ratio correction "
        "transported to the real pool inherits this as its main limitation.")
    if verbose:
        print("=== DGP DESIGN MATCH ===")
        for k_ in out["real"]:
            print(f"  {k_:<26} real {out['real'][k_]}   synthetic {out['synthetic'][k_]}")
    return out


def fresh_test(gen, seed, fits, years, lam):
    """Draw a FRESH test set and score it with FIXED fits. This is the conditional
    sampling experiment: the training corpus is held, only the scored sample redraws."""
    D2 = gen(seed)
    C, B, T, W = [], [], [], []
    for f in fits:
        te = np.flatnonzero(D2["dy"] == f["yr"])
        if len(te) == 0:
            continue
        assert len(te) == f["n_te"], "fold sizes must be fixed across synthetic draws"
        cons = np.maximum(0.0, f["ols"][0] + f["ols"][1] * D2["fv"][te])
        C.append(cons)
        B.append((1 - lam) * cons + lam * ridge_pred(f["ridge"], D2["X"][te]))
        T.append(D2["y"][te])
        W.append(D2["w"][te])
    if not B:
        return None
    return {"cons": np.concatenate(C), "blend": np.concatenate(B),
            "y": np.concatenate(T), "w": np.concatenate(W)}


# ===================================================================== coverage
def coverage(n_check: int = N_CHECK, S: int = 400, B: int = 300, M: int = 300,
             verbose: bool = True):
    """EXP-1 (unconditional estimand) and EXP-2 (conditional estimand) on one set of
    synthetic datasets. Each estimator is gated against ITS OWN estimand; the crossed
    pairings are reported as diagnostics only."""
    real = load_pool("hit", "full")
    gen, years = make_dgp(real, alt=False)
    if verbose:
        print(f"=== COVERAGE (design-matched: n={real['n']}, k={real['X'].shape[1]}, "
              f"folds={len(years)}, lam={real['lam']}) ===")
        print(f"    S={S} truth datasets, n_check={n_check}, B={B}, M={M}")

    # ---- EXP-1 truth: variation over fresh datasets, refit each time
    t0 = time.time()
    pts, pts_v = [], []
    for s in range(S):
        pts.append(delta_of(chain_full(gen(SEED + 5_000 + s), years=years)))
        # CONTROL: the same truth with cohort SIZES redrawn too. The shipped bootstrap
        # scatters resampled rows across folds, so it reshuffles fold sizes; a truth that
        # holds them fixed would charge that variance to "refit noise" for free. This is
        # the dumbest available explanation for the refit leg being over-wide and it is
        # measured rather than assumed.
        pts_v.append(delta_of(chain_full(gen(SEED + 5_000 + s, vary_folds=True),
                                         years=years)))
    truth_u = float(np.nanmean(pts))
    sd_u = float(np.nanstd(pts, ddof=1))
    truth_v = float(np.nanmean(pts_v))
    sd_v = float(np.nanstd(pts_v, ddof=1))
    if verbose:
        print(f"  EXP-1 TRUTH fixed folds : mean {truth_u:+.5f}, sd {sd_u:.5f}")
        print(f"  EXP-1 TRUTH redrawn folds: mean {truth_v:+.5f}, sd {sd_v:.5f} "
              f"({time.time()-t0:.0f}s)")

    rng = np.random.default_rng(SEED + 7)
    hits = {(e, t): 0 for e in ("refit", "cond_iid", "cond_strat")
            for t in ("uncond", "uncond_varfolds", "cond")}
    sds = {k: [] for k in ("refit", "cond_iid", "cond_strat")}
    true_cond_sds, true_cond_means, point_deltas = [], [], []
    t0 = time.time()
    for s in range(n_check):
        D = gen(SEED + 5_000 + s)
        r = chain_full(D, years=years, keep_fits=True)
        point = delta_of(r)
        point_deltas.append(point)

        # EXP-2 truth for THIS dataset: fresh test sets, fits held fixed
        fd = [delta_of(fresh_test(gen, SEED + 900_000 + s * 10_000 + m, r["fits"],
                                  years, D["lam"])) for m in range(M)]
        fd = np.asarray(fd, dtype=float)
        fd = fd[np.isfinite(fd)]
        t_cond = float(fd.mean())
        true_cond_means.append(t_cond)
        true_cond_sds.append(float(fd.std(ddof=1)))

        draws = {
            "refit": boot_refit(D, B, rng, years=years),
            "cond_iid": boot_cond(r, B, rng, stratify=False),
            "cond_strat": boot_cond(r, B, rng, stratify=True),
        }
        for name, dr in draws.items():
            a = np.asarray(dr, dtype=float)
            a = a[np.isfinite(a)]
            sds[name].append(float(a.std(ddof=1)))
            lo, hi = np.percentile(a, 2.5), np.percentile(a, 97.5)
            if lo <= truth_u <= hi:
                hits[(name, "uncond")] += 1
            if lo <= truth_v <= hi:
                hits[(name, "uncond_varfolds")] += 1
            if lo <= t_cond <= hi:
                hits[(name, "cond")] += 1
        if verbose and (s + 1) % 25 == 0:
            print(f"  {s+1}/{n_check}  {time.time()-t0:.0f}s", flush=True)

    sd_cond_true = float(np.mean(true_cond_sds))
    out = {
        "design": {
            "n_rows": real["n"], "k_features": int(real["X"].shape[1]),
            "folds": len(years), "lam": real["lam"],
            "S_truth_datasets": S, "n_check": n_check, "B": B, "M_fresh_test_sets": M,
            "null": ("model features are noisy copies of the consensus column, so the "
                     "model carries no information the consensus lacks"),
            "seed": SEED,
        },
        "estimands": {
            "unconditional": {"truth_mean_delta": round(truth_u, 5),
                              "true_sd": round(sd_u, 5),
                              "question": "what would we conclude from a different dataset "
                                          "with the SAME cohort sizes"},
            "unconditional_varfolds": {
                "truth_mean_delta": round(truth_v, 5), "true_sd": round(sd_v, 5),
                "question": "what would we conclude from a different dataset whose "
                            "cohort SIZES also redraw",
                "role": "CONTROL for the refit leg, see the code comment in EXP-1"},
            "conditional": {"truth_mean_delta": round(float(np.mean(true_cond_means)), 5),
                            "true_sd": round(sd_cond_true, 5),
                            "question": "given this training corpus, is this margin real"},
        },
        "gate_level": "central 95% binomial acceptance region for p=0.95",
    }
    legs = {}
    for name in ("refit", "cond_iid", "cond_strat"):
        own = "uncond" if name == "refit" else "cond"
        true_sd = sd_u if own == "uncond" else sd_cond_true
        mean_sd = float(np.mean(sds[name]))
        g = binom_gate(hits[(name, own)], n_check)
        legs[name] = {
            "own_estimand": "unconditional" if own == "uncond" else "conditional",
            "mean_bootstrap_sd": round(mean_sd, 5),
            "true_sd_of_own_estimand": round(true_sd, 5),
            "sd_ratio_boot_over_true": round(mean_sd / true_sd, 3),
            "sd_ratio_in_band": bool(SD_BAND[0] <= mean_sd / true_sd <= SD_BAND[1]),
            "gate_two_sided": g,
            "one_sided_gate_as_currently_coded": (
                "PASS" if g["coverage"] >= 0.90 else "FAIL"),
            "cross_check_other_estimand": {
                "coverage": round(hits[(name, "cond" if own == "uncond" else "uncond")]
                                  / n_check, 4),
                "note": "DIAGNOSTIC ONLY, never a gate: it is the wrong question for "
                        "this estimator",
            },
            "coverage_all_three_estimands": {
                t: round(hits[(name, t)] / n_check, 4)
                for t in ("uncond", "uncond_varfolds", "cond")},
        }
        if name == "refit":
            legs[name]["varfolds_control"] = {
                "gate_two_sided": binom_gate(hits[("refit", "uncond_varfolds")], n_check),
                "sd_ratio_boot_over_true": round(mean_sd / sd_v, 3),
                "reading": ("if the refit leg fails against the fixed-fold truth but "
                            "passes here, its extra width is cohort-size resampling, not "
                            "refit noise, and the 'over-wide floor' claim is wrong"),
            }
    out["legs"] = legs
    out["sd_band_reported_not_gating"] = list(SD_BAND)
    prim = legs["cond_iid"]["gate_two_sided"]["verdict"]
    sens = legs["cond_strat"]["gate_two_sided"]["verdict"]
    if prim == "PASS":
        out["registration"] = "E_cond_iid REGISTERED (primary, as pre-registered)"
    elif sens == "PASS":
        out["registration"] = ("E_cond_iid FAILED; E_cond_strat passes. Post-hoc "
                               "substitution, must be disclosed in the headline.")
    else:
        out["registration"] = "STOP CLAUSE FIRES: no conditional estimator registered."
    out["elapsed_s"] = round(time.time() - t0, 1)
    if verbose:
        for name, v in legs.items():
            g = v["gate_two_sided"]
            print(f"  {name:<11} own={v['own_estimand']:<13} sd {v['mean_bootstrap_sd']:.5f}"
                  f" vs true {v['true_sd_of_own_estimand']:.5f} "
                  f"(ratio {v['sd_ratio_boot_over_true']}) cov {g['coverage']:.3f} "
                  f"accept {g['accept_coverage_band']} -> {g['verdict']}  "
                  f"[one-sided gate would say {v['one_sided_gate_as_currently_coded']}]")
        print("  REGISTRATION:", out["registration"])
    return out


# ===================================================================== power (3.2)
def power(n_sim: int = 120, B: int = 200, verbose: bool = True):
    """Detection rate under a design-matched ALTERNATIVE and error rate under the part-2
    null, for all three estimators, each at its own floor.

    TWO fire rates are reported and the difference between them matters.

      fire_rate_vs_zero      |point| >= MDE95. This is the gate AS THE PROGRAM APPLIES
                             IT, testing "is the delta different from zero".
      fire_rate_centered     |point - truth| >= MDE95, where `truth` is the Monte-Carlo
                             mean point delta of the same DGP. This is the actual
                             false-positive rate of the instrument.

    They differ under this null because the null's true delta is NOT zero: a blend that
    adds a noisier predictor to the consensus degrades the rank by a fixed amount of the
    design. Reading fire_rate_vs_zero as a type-I rate would be wrong, and the earlier
    run of this lab printed only that number.

    Note on the convention: MDE95 here is the gate standard's ONE-SIDED 1.645*sd applied
    to |delta|, so a perfectly calibrated instrument has fire_rate_centered near 0.10,
    not 0.05. That is a property of the published convention, not of any estimator.
    """
    real = load_pool("hit", "full")
    out = {}
    for label, alt in (("null", False), ("alternative", True)):
        gen, years = make_dgp(real, alt=alt)
        rng = np.random.default_rng(SEED + (11 if alt else 13))
        pts, sds = [], {"refit": [], "cond_iid": [], "cond_strat": []}
        t0 = time.time()
        for s in range(n_sim):
            D = gen(SEED + 30_000 + s)
            r = chain_full(D, years=years, keep_fits=True)
            pts.append(delta_of(r))
            draws = {"refit": boot_refit(D, B, rng, years=years),
                     "cond_iid": boot_cond(r, B, rng, stratify=False),
                     "cond_strat": boot_cond(r, B, rng, stratify=True)}
            for name, dr in draws.items():
                a = np.asarray(dr, dtype=float)
                sds[name].append(float(a[np.isfinite(a)].std(ddof=1)))
        pts = np.asarray(pts, dtype=float)
        truth = float(np.nanmean(pts))
        out[label] = {
            "n_sim": n_sim, "B": B,
            "mean_point_delta": round(truth, 5),
            "sd_point_delta": round(float(np.nanstd(pts, ddof=1)), 5),
            "fire_rate_vs_zero": {
                k: round(float(np.mean(np.abs(pts) >= Z95_ONE * np.asarray(v))), 4)
                for k, v in sds.items()},
            "fire_rate_centered": {
                k: round(float(np.mean(np.abs(pts - truth) >= Z95_ONE * np.asarray(v))), 4)
                for k, v in sds.items()},
            "mean_floor": {k: round(float(Z95_ONE * np.mean(v)), 4) for k, v in sds.items()},
            "elapsed_s": round(time.time() - t0, 1),
        }
        if verbose:
            o = out[label]
            print(f"  {label:<12} truth {o['mean_point_delta']:+.5f}")
            print(f"    vs zero  {o['fire_rate_vs_zero']}")
            print(f"    centered {o['fire_rate_centered']}")
    out["reading"] = (
        "fire_rate_centered under 'null' is the instrument's false-positive rate and the "
        "calibrated target is about 0.10, since MDE95 is one-sided 1.645*sd applied to an "
        "absolute margin. fire_rate_vs_zero under 'null' is NOT a type-I rate: the null's "
        "true delta is not zero. fire_rate_vs_zero under 'alternative' is power.")
    out["zero_information_blend_cost"] = (
        "the null's mean point delta is the rho a blend loses by mixing in a predictor "
        "that carries NO information the consensus lacks. It is the dumbest available "
        "explanation for a negative full-pool margin and it is quantified here rather "
        "than assumed away. It is a property of this synthetic design and its magnitude "
        "does not transfer to the real pool as a point estimate.")
    return out


# ===================================================================== detection (3.1)
def _leg(r, which, lam):
    """The blend leg, or the ridge leg recovered from it: blend = (1-lam)*cons+lam*ridge."""
    if which == "blend":
        return r["blend"]
    return (r["blend"] - (1 - lam) * r["cons"]) / lam


def detect(B: int = 2000, verbose: bool = True):
    """Real-data known-real alternative: the hitter `fv` feature.

    PRE-REGISTERED CONTRAST (POWER_GATE.md 3.1): pooled rho of the shipped BLEND minus
    pooled rho of the same blend refit on the spec MINUS `fv`, on the FULL pool.

    THAT CONTRAST IS MIS-SPECIFIED AND THIS FUNCTION SAYS SO RATHER THAN SWAPPING IT
    SILENTLY. The blend is (1-lam)*consensus + lam*ridge and the consensus leg IS an
    OLS on `fv`, so deleting `fv` from the ridge does not remove `fv` from the blend.
    The contrast's truth is therefore near zero by construction, and applying the
    pre-registered PASS clause literally would de-register the SHIPPED estimator too.
    That is a reductio on the check, not on the estimators.

    So all four cells of the (pool x leg) grid are run and reported. The AMENDED
    primary, disclosed as post-hoc, is ridge-leg on the FULL pool: the same pool as the
    lane's primary cut, and the leg the feature actually enters. The amendment is not
    outcome-selected, since every cell except the mis-specified one answers the same way.
    """
    if verbose:
        print(f"=== 3.1 DETECTION on hitter `fv` (B={B}) ===")
    rng = np.random.default_rng(SEED + 3)
    cells = {}
    for pool in ("full", "debuted"):
        D = load_pool("hit", pool)
        lam = D["lam"]
        fi = D["keys"].index("fv")
        r_full = chain_full(D)
        r_drop = chain_full(D, drop_feat=fi)
        n = len(r_full["y"])
        blocks = [np.flatnonzero(r_full["yr"] == u) for u in np.unique(r_full["yr"])]

        pre = {"blend": [], "ridge": []}
        for _ in range(B):
            sel = rng.integers(0, D["n"], D["n"])
            a = chain_full(D, sel)
            b = chain_full(D, sel, drop_feat=fi)
            for wch in ("blend", "ridge"):
                if a is None or b is None:
                    pre[wch].append(float("nan"))
                else:
                    pre[wch].append(wrho(_leg(a, wch, lam), a["y"], a["w"])
                                    - wrho(_leg(b, wch, lam), b["y"], b["w"]))
        cond = {("blend", "iid"): [], ("blend", "strat"): [],
                ("ridge", "iid"): [], ("ridge", "strat"): []}
        for _ in range(B):
            i = rng.integers(0, n, n)
            j = np.concatenate([b[rng.integers(0, len(b), len(b))] for b in blocks])
            for wch in ("blend", "ridge"):
                pa, pb = _leg(r_full, wch, lam), _leg(r_drop, wch, lam)
                cond[(wch, "iid")].append(
                    wrho(pa[i], r_full["y"][i], r_full["w"][i])
                    - wrho(pb[i], r_drop["y"][i], r_drop["w"][i]))
                cond[(wch, "strat")].append(
                    wrho(pa[j], r_full["y"][j], r_full["w"][j])
                    - wrho(pb[j], r_drop["y"][j], r_drop["w"][j]))

        for wch in ("blend", "ridge"):
            pa, pb = _leg(r_full, wch, lam), _leg(r_drop, wch, lam)
            rf = wrho(pa, r_full["y"], r_full["w"])
            rd = wrho(pb, r_drop["y"], r_drop["w"])
            pt = rf - rd
            row = {
                "pool": pool, "leg": wch, "n_scored": int(n),
                "rho_full_spec": round(rf, 5), "rho_spec_minus_fv": round(rd, 5),
                "point": round(float(pt), 5),
                "refit": summarize(pre[wch], pt),
                "cond_iid": summarize(cond[(wch, "iid")], pt),
                "cond_strat": summarize(cond[(wch, "strat")], pt),
            }
            for k in ("refit", "cond_iid", "cond_strat"):
                row[k]["detects"] = bool(row[k].get("resolvable"))
            cells[f"{pool}.{wch}"] = row
            if verbose:
                print(f"  {pool}.{wch:<6} point {pt:+.5f}  " + "  ".join(
                    f"{k}={'DETECTS' if row[k]['detects'] else 'MISSES'}"
                    f"({row[k]['MDE95']})" for k in ("refit", "cond_iid", "cond_strat")))

    out = {
        "cells": cells,
        "preregistered_cell": "full.blend",
        "preregistered_result": {
            k: cells["full.blend"][k]["detects"] for k in ("refit", "cond_iid", "cond_strat")
        },
        "preregistered_cell_is_misspecified": True,
        "why_misspecified": (
            "blend = (1-lam)*consensus + lam*ridge and the consensus leg is an OLS on "
            "`fv`, so deleting `fv` from the ridge leaves `fv` in the blend at weight "
            "1-lam = 0.30. The contrast's truth is near zero by construction. Applying "
            "the pre-registered PASS clause literally would de-register the SHIPPED "
            "estimator as well, which is a reductio on the check."),
        "amended_primary_cell": "full.ridge",
        "amendment_is_post_hoc_and_disclosed": True,
        "amended_result": {
            k: cells["full.ridge"][k]["detects"] for k in ("refit", "cond_iid", "cond_strat")
        },
        "amendment_selection_disclosure": (
            "the point estimates of all four cells were seen before the amended primary "
            "was designated; the FLOORS were not. full.ridge was chosen because it matches "
            "the lane's primary pool, and it is the SMALLER of the two ridge-leg effects, "
            "so the choice is the conservative one, not the flattering one."),
        "discriminative_reading": (
            "the purpose of 3.1 is to rule out a never-rejecting instrument. All three "
            "estimators fire on debuted.ridge, the cell where EFV_GATE_STANDARD.md section "
            "6 locates the known-real `fv` effect, and none fires where another does not. "
            "The check therefore does not discriminate between the estimators; it confirms "
            "none of them is inert. Registration rests on the part-2 coverage gate and the "
            "3.2 simulated power table."),
    }
    return out


# ===================================================================== decomp (3.3)
def decomp(B: int = 1200, verbose: bool = True):
    """The embarrassing control: is '53% refit noise' actually a decomposition?"""
    if verbose:
        print(f"=== 3.3 VARIANCE DECOMPOSITION, hitter full pool (B={B}) ===")
    D = load_pool("hit", "full")
    r = chain_full(D, keep_fits=True)
    rng = np.random.default_rng(SEED + 5)
    sd_ship = float(np.nanstd(np.asarray(boot_refit(D, B, rng), dtype=float), ddof=1))
    sd_test = float(np.nanstd(np.asarray(boot_cond(r, B, rng), dtype=float), ddof=1))
    sd_train = float(np.nanstd(np.asarray(boot_train_only(D, B, rng), dtype=float), ddof=1))
    recon = math.sqrt(sd_test ** 2 + sd_train ** 2)
    out = {
        "B": B,
        "sd_shipped_both_resampled": round(sd_ship, 5),
        "sd_test_rows_only": round(sd_test, 5),
        "sd_train_refit_only": round(sd_train, 5),
        "additive_reconstruction": round(recon, 5),
        "reconstruction_over_shipped": round(recon / sd_ship, 3),
        "refit_variance_share_of_shipped": round(1 - (sd_test ** 2) / (sd_ship ** 2), 3),
        "additivity_holds": bool(0.90 <= recon / sd_ship <= 1.10),
        "reading": ("if the reconstruction ratio is far from 1 the '53% refit noise' "
                    "framing is not a variance decomposition and must not be used"),
    }
    if verbose:
        print(f"  shipped {sd_ship:.5f}  test-only {sd_test:.5f}  train-only "
              f"{sd_train:.5f}  sqrt(sum sq) {recon:.5f} "
              f"(ratio {out['reconstruction_over_shipped']})")
        print(f"  refit share of shipped variance: "
              f"{out['refit_variance_share_of_shipped']:.3f}")
    return out


# ===================================================================== verdict
CUTS = [
    ("hit.full_pool_km", "hit", "full", "PRIMARY"),
    ("pit.full_pool_km", "pit", "full", "secondary"),
    ("hit.debuted_km", "hit", "debuted", "secondary"),
    ("pit.debuted_km", "pit", "debuted", "secondary"),
]


def verdict(B: int = 2000, sd_ratio: dict | None = None, verbose: bool = True):
    """The four cuts under both estimators, raw and coverage-corrected."""
    if verbose:
        print(f"=== VERDICT: four cuts, both estimators (B={B}) ===")
    rng = np.random.default_rng(SEED + 9)
    out = {}
    for key, side, pool, rank in CUTS:
        D = load_pool(side, pool)
        r = chain_full(D, keep_fits=True)
        pt = delta_of(r)
        row = {"rank": rank, "legs": legs_of(r), "n_scored": int(len(r["y"]))}
        row["refit"] = summarize(boot_refit(D, B, rng), pt)
        row["cond_iid"] = summarize(boot_cond(r, B, rng, stratify=False), pt)
        row["cond_strat"] = summarize(boot_cond(r, B, rng, stratify=True), pt)
        for est in ("refit", "cond_iid", "cond_strat"):
            v = row[est]
            if v.get("sd") is None:
                continue
            bf = Z_BONF4_ONE * v["sd"]
            v["mde95_bonferroni_k4"] = round(bf, 4)
            v["resolvable_bonferroni_k4"] = bool(abs(pt) >= bf)
            if sd_ratio and est in sd_ratio and sd_ratio[est]:
                rr = float(sd_ratio[est])
                corr = v["MDE95"] / rr
                v["sd_ratio_applied"] = round(rr, 3)
                v["mde95_coverage_corrected"] = round(corr, 4)
                v["margin_over_corrected_floor"] = round(abs(pt) / corr, 3)
                v["resolvable_corrected"] = bool(abs(pt) >= corr)
        out[key] = row
        if verbose:
            print(f"  {key:<18} delta {pt:+.5f} n {row['n_scored']}")
            for est in ("refit", "cond_iid", "cond_strat"):
                v = row[est]
                extra = ""
                if "mde95_coverage_corrected" in v:
                    extra = (f" | corrected {v['mde95_coverage_corrected']} -> "
                             f"{'RESOLVABLE' if v['resolvable_corrected'] else 'NULL'}")
                print(f"    {est:<11} sd {v['sd']} MDE95 {v['MDE95']} "
                      f"({v['margin_over_floor']}x) {v['verdict']}{extra}")
    out["multiplicity"] = {
        "primary": "hit.full_pool_km, named in the lane brief before measurement",
        "secondary_k": 4,
        "bonferroni_z_one_sided": Z_BONF4_ONE,
        "note": "no secondary cut is called resolvable on its unadjusted floor alone",
    }
    return out


# ===================================================================== driver
def run_all(B: int = 2000):
    t0 = time.time()
    rp = repro()
    print()
    osd = onesided_defect()
    print()
    dm = dgp_match()
    print()
    dc = decomp()
    print()
    dt = detect(B)
    print()
    cov = coverage()
    print()
    pw = power()
    print()
    registered = cov["registration"].startswith("E_cond_iid REGISTERED") or \
        cov["registration"].startswith("E_cond_iid FAILED; E_cond_strat passes")
    ratios = None
    if registered:
        ratios = {k: cov["legs"][k]["sd_ratio_boot_over_true"]
                  for k in ("refit", "cond_iid", "cond_strat")}
    vd = verdict(B, sd_ratio=ratios)
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_power_lab.py all",
        "registration": ("docs/efv-2026-08-07b/POWER_GATE.md parts 0-4, written in full "
                         "BEFORE this lab existed; part 5 is a placeholder filled after "
                         "the run"),
        "lane": "A1 (which bootstrap is the published claim about)",
        "scope_note": ("registers an instrument and reports a verdict. Changes NO shipped "
                       "floor constant, retires nothing, reopens no closed arm, and "
                       "retroactively resolves no past null."),
        "seed": SEED,
        "repro": rp,
        "onesided_gate_defect": osd,
        "dgp_design_match": dm,
        "variance_decomposition": dc,
        "detection_fv": dt,
        "coverage": cov,
        "power": pw,
        "verdict": vd,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT_PATH}  ({out['elapsed_s']}s)")
    return out


def main():
    a = sys.argv[1:] or ["all"]
    cmd = a[0]
    if cmd == "repro":
        repro()
    elif cmd == "onesided_defect":
        onesided_defect()
    elif cmd == "dgp_match":
        dgp_match()
    elif cmd == "decomp":
        decomp(int(a[1]) if len(a) > 1 else 1200)
    elif cmd == "detect":
        detect(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "coverage":
        coverage(int(a[1]) if len(a) > 1 else N_CHECK)
    elif cmd == "power":
        power()
    elif cmd == "verdict":
        verdict(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "all":
        run_all(int(a[1]) if len(a) > 1 else 2000)
    else:
        print(__doc__ or "unknown mode")


if __name__ == "__main__":
    main()
