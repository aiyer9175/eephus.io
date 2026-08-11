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
# M1 PART B (2026-08-09) generalizes the estimator by STATISTIC CLASS and TARGET
# COLUMN. Registration: docs/efv-2026-08-08/POWER_EXTENSION_GATE.md, sections 0-7
# written before any part-B number existed. Part B adds nothing to the estimators
# above; it reduces every statistic to a SCORED FRAME and resamples the frame's units.
# `parity_x1` is the stop gate: the four registered cuts must reproduce EXACTLY under
# the generalized path, same seed, same draws.
#
# Run: python tools/efv_power_lab.py repro          reproduce the wave-1 numbers
#      python tools/efv_power_lab.py decomp         variance decomposition (control 3.3)
#      python tools/efv_power_lab.py detect [B]     real-data `fv` detection (3.1)
#      python tools/efv_power_lab.py coverage [NC]  EXP-1 + EXP-2, the gate (part 2)
#      python tools/efv_power_lab.py power          simulated power / type-I (3.2)
#      python tools/efv_power_lab.py verdict [B]    the four cuts under both estimators
#      python tools/efv_power_lab.py all [B]        everything + write the ledger
#      python tools/efv_power_lab.py parity_x1 [B]  PART B stop gate, merges the ledger
#      python tools/efv_power_lab.py h2hshape       head-to-head frame shape + clustering
#      python tools/efv_power_lab.py floors [Bp Bh] PART B step 3, the five floors
#      python tools/efv_power_lab.py x2cover [NC]   PART B step 2, CLUSTERED coverage
#      python tools/efv_power_lab.py x3detect [B]   X3 per class
#      python tools/efv_power_lab.py x4sign [n]     X4 losses vs wins
#      python tools/efv_power_lab.py adjudicate [B] B-L2 TOST / triage / REML / signs
#      python tools/efv_power_lab.py partb          all five of the above, in order
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
# `_load_h2h` / `_h2h_pass` are IMPORTED, not copied, for the same reason the numeric
# primitives are: the head-to-head frame they build is the one data/xfv_headtohead_gap.json
# was measured on, and a private copy would silently stop being that frame.
from efv_mde_lab import (ridge_fit, ridge_pred, ols_fit, wrho,   # noqa: E402
                         block_norm, _rankavg, _load_h2h, _h2h_pass)
from efv_cohort_floor_lab import load_pool                      # noqa: E402
import efv_mde_lab as MDE                                        # noqa: E402  read-only

OUT_PATH = ROOT / "data" / "xfv_power_eval.json"
SEED = 20260807
SIDES = ("hit", "pit")
Z95_ONE = 1.645
Z95_TWO = 1.96
Z_BONF4_ONE = 2.2414   # one-sided alpha 0.05/4 = 0.0125
N_CHECK = 200          # fixed in POWER_GATE.md part 2 so over-coverage can fail
SD_BAND = (0.90, 1.10)  # self-added, reported, NOT the registration criterion

# RNG DISCIPLINE (POWER_EXTENSION_GATE.md section 3.4). verdict() shares ONE
# default_rng(SEED + 9) across three estimators SEQUENTIALLY, so a draw inserted into
# any existing function moves every already-published number in data/xfv_power_eval.json.
# Part B therefore consumes nothing from an existing stream: each new class takes an
# unused offset from this table. Offsets already spent by part A and NOT reusable:
# 3 detect, 5 decomp, 7 coverage, 9 verdict, 11 and 13 power, 77 and 78 dgp_match,
# plus the dataset streams 5_000+s, 30_000+s and 900_000+.
SEED_OFF = {
    "h2h_cluster": 41,
    "block_rho": 43,
    "feature_add": 45,
    "lambda_shift": 47,
    # step 2 additions, none of them previously spent. Every consumer gets its own key
    # rather than an arithmetic offset off another key: `feature_add + 2` and
    # `lambda_shift` both evaluate to 47, which is how two unrelated streams end up
    # sharing draws without anyone noticing.
    "feature_add_block": 46,
    "feature_add_weak": 47,   # SHARED with lambda_shift, see the note below
    "h2h_cover": 49,       # X2 clustered coverage, dataset stream 5_000_000+ (see below)
    "h2h_cover_pe": 50,    # which training corpus each checked dataset gets
    "x3_detect": 51,       # X3, head-to-head leg
    "h2h_cover_sigma": 52,  # sigma_pe calibration
    "x4_sign": 53,         # X4 win arm
    "x4_loss": 54,         # X4 loss arm
    "fold_series": 55,     # per-fold delta series for the REML / sign-enumeration blocks
    "pooled_today": 57,    # the four registered cuts re-derived on TODAY's basis
    "x3_block": 61,        # X3, block instrument
    "x3_lambda": 63,       # X3, lambda-shifted geometry
}
# KNOWN SHARED STREAM, stated rather than left to be discovered: the weak-feature control
# and the lambda-shift refit both start at SEED + 47, so they draw the SAME resample
# indices out of the same pool. Two independent analyses seeded alike is the norm in this
# repo (efv_mde_lab.mde starts at SEED itself); it correlates the two cells' Monte-Carlo
# errors and biases neither sd. It is NOT a draw inserted into a published stream, which
# is the thing section 3.4 of the registration forbids.
# Dataset streams: part A spent SEED+5_000+s (s < 400), SEED+30_000+s and
# SEED+900_000+s*10_000+m, the last of which reaches 2_890_299. The clustered coverage
# DGP therefore starts at SEED+5_000_000 and the X4 arms at SEED+6_000_000, both clear
# of every range above.
H2H_DGP_BASE = 5_000_000
X4_DGP_BASE = 6_000_000
TOST_DELTA = 0.02      # owner-registered equivalence margin, Spearman points (B-L2)


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


# ============================================ generalized statistic classes (M1 part B)
#
# WHY THIS SECTION EXISTS. Everything above is hardcoded to ONE statistic: pooled
# pair-weighted Spearman of blend minus consensus, on the `target_censored` column, on a
# frame with exactly one row per player. The site's actual claims live on other
# statistics (head-to-head common set, block-rho, feature-add, lambda-shift), on other
# target columns (`war` for the common set), and one of them carries 3.07 rows per
# player. Registration: docs/efv-2026-08-08/POWER_EXTENSION_GATE.md sections 2 and 3.
#
# THE REDUCTION THAT MAKES IT SAFE. Every class collapses to a SCORED FRAME: challenger
# leg, baseline leg, target column, weight column, block ids, cluster ids. The
# conditional estimator resamples the frame's UNITS and knows nothing about which
# statistic produced it. `parity_x1` proves the reduction is exact on the four
# registered cuts: identical draws, identical floors, same seed, same stream order.
#
# WHAT IS DELIBERATELY NOT PARAMETERIZED. The pool loader stays
# efv_cohort_floor_lab.load_pool with its fixed `target_censored`. A second pool loader
# would be a reimplementation, and reimplemented pools are how two labs stop measuring
# the same thing. The target column is parameterized AT THE FRAME, which is where the
# classes actually differ.
CLASSES = {
    "pooled_rho": "WIRED. The four registered cuts. target_censored, 1 row per player.",
    "headtohead": "WIRED. target `war`, 3.07 rows per player, CLUSTER resampled.",
    "block_rho": "WIRED. debuted pools both sides, side x cohort-year blocks, n 1,645.",
    "feature_add": "WIRED. spec minus one feature, on the pooled AND block instruments.",
    "lambda_shift": "WIRED. blend at the pin vs blend at pin minus shift, same fits.",
}


def scored_frame(pa, pb, y, w=None, blk=None, clu=None, target="target_censored",
                 leg_names=("blend", "consensus"), label="", refit=None, transform=None):
    """One statistic reduced to resamplable units.

    pa/pb      challenger and baseline prediction legs, aligned row for row
    y          the TARGET COLUMN. `target_censored` for pooled_rho, `war` for the
               head-to-head common set. Named in `target` so an artifact never has to
               guess which outcome a floor was derived against.
    w          pair weights, or None for an unweighted statistic
    blk        block ids for the stratified conditional variant (cohort year, or
               side x cohort year)
    clu        cluster ids, or None when the frame is one row per player. NOT optional
               for a frame with repeated players: see boot_cond_cluster.
    refit      callable(B, rng) -> draws for the E_refit leg, which is class specific
               because refitting means resampling the POOL, not the scored frame.
    transform  callable(pa, pb, y, blk) -> (pa, pb, y) applied AFTER slicing, for a
               statistic whose definition includes a transform estimated from the scored
               sample itself. block_rho is the only such class: its percentile-inside-
               block normalization is recomputed on a fresh sample, so a bootstrap that
               froze it would drop a real variance component. None for every other
               class, and `parity_x1` re-checks that None leaves frame_delta bit-exact.
    """
    return {"pa": np.asarray(pa), "pb": np.asarray(pb), "y": np.asarray(y),
            "w": (None if w is None else np.asarray(w)),
            "blk": (None if blk is None else np.asarray(blk)),
            "clu": (None if clu is None else np.asarray(clu)),
            "target": target, "leg_names": tuple(leg_names), "label": label,
            "refit": refit, "transform": transform, "n": int(len(y))}


def frame_delta(F, idx=None):
    """delta = rho(challenger) - rho(baseline) on identical rows.

    Byte-identical to delta_of when the frame is (blend, cons, y, w): same slicing,
    same operand order, same short-circuit at n < 8. `parity_x1` checks that on 24,000
    real draws rather than asserting it.
    """
    sl = slice(None) if idx is None else idx
    pa, pb, y = F["pa"][sl], F["pb"][sl], F["y"][sl]
    if len(y) < 8:
        return float("nan")
    w = None if F["w"] is None else F["w"][sl]
    tf = F.get("transform")
    if tf is not None:
        pa, pb, y = tf(pa, pb, y, (None if F["blk"] is None else F["blk"][sl]))
    return wrho(pa, y, w) - wrho(pb, y, w)


def frame_legs(F):
    """The point legs, keyed by this class's own leg names and in the incumbent's key
    order (n, baseline, challenger, delta) so a pooled_rho row serializes identically
    to legs_of()."""
    a_name, b_name = F["leg_names"]
    w = F["w"]
    pa, pb, y = F["pa"], F["pb"], F["y"]
    tf = F.get("transform")
    if tf is not None:
        pa, pb, y = tf(pa, pb, y, F["blk"])
    a = wrho(pa, y, w)
    b = wrho(pb, y, w)
    return {"n": int(len(F["y"])), b_name: round(b, 5), a_name: round(a, 5),
            "delta": round(a - b, 5)}


def _frame_groups(F, key):
    """Row index groups for a resampling unit, cached on the frame. Built from
    np.unique, which is sorted and deterministic; never from a set and never from
    hash(), per the standing determinism rule."""
    ck = "_groups_" + key
    if ck not in F:
        v = F[key]
        F[ck] = [np.flatnonzero(v == u) for u in np.unique(v)]
    return F[ck]


def boot_cond_cluster(F, B, rng, mode="row"):
    """E_cond, generalized over resampling UNITS. Fits are already fixed inside `F`;
    only the scored units resample.

    mode="row"      one unit per row. idx = rng.integers(0, n, n), which is EXACTLY
                    boot_cond(r, B, rng, stratify=False): same single call, same
                    stream, same draws. `parity_x1` proves it on the four cuts.
    mode="strat"    resample inside each F["blk"] block, preserving per-fold n.
                    Exactly boot_cond(r, B, rng, stratify=True).
    mode="cluster"  resample F["clu"] units (players) WITH REPLACEMENT and concatenate
                    each drawn player's rows.
    mode="cluster_strat"  clusters resampled inside each F["blk"] block. Sensitivity
                    only, for a class whose clusters span sides.

    WHY mode="cluster" IS MANDATORY FOR THE HEAD-TO-HEAD CLASS. That frame carries
    3,224 rows over 1,051 players, 3.07 rows each. Row-level i.i.d. resampling treats
    3.07 correlated rows as 3.07 independent ones and narrows the floor in the
    ANTI-CONSERVATIVE direction. efv_mde_lab.headtohead already clusters (its `sel`
    resamples pool rows, and a pool row IS a player, carrying that player's whole
    common-set row list into the score); this is the conditional counterpart. The row
    variant is emitted as a labelled DIAGNOSTIC so the size of the violation is
    published, never as a gate.
    """
    n = F["n"]
    out = []
    if mode == "row":
        for _ in range(B):
            out.append(frame_delta(F, rng.integers(0, n, n)))
        return out
    if mode == "strat":
        blocks = _frame_groups(F, "blk")
        for _ in range(B):
            idx = np.concatenate([b[rng.integers(0, len(b), len(b))] for b in blocks])
            out.append(frame_delta(F, idx))
        return out
    if F["clu"] is None:
        raise ValueError("cluster resampling asked of a frame with no cluster ids")
    groups = _frame_groups(F, "clu")
    if mode == "cluster":
        g = len(groups)
        for _ in range(B):
            pick = rng.integers(0, g, g)
            out.append(frame_delta(F, np.concatenate([groups[i] for i in pick])))
        return out
    if mode == "cluster_strat":
        blocks = _frame_groups(F, "blk")
        # A cluster must live in exactly one block or "stratified clusters" is not
        # defined; for the head-to-head frame the block is the side and a player is
        # one side's prospect, so the partition holds. Checked, not assumed.
        owner = [int(np.unique(F["blk"][gi])[0]) if len(np.unique(F["blk"][gi])) == 1
                 else -1 for gi in groups]
        if -1 in owner:
            raise ValueError("a cluster spans blocks; cluster_strat is undefined here")
        by_block = [[i for i, o in enumerate(owner) if o == int(np.unique(F["blk"][b])[0])]
                    for b in blocks]
        for _ in range(B):
            pick = [np.asarray(ids)[rng.integers(0, len(ids), len(ids))]
                    for ids in by_block]
            idx = np.concatenate([groups[i] for part in pick for i in part])
            out.append(frame_delta(F, idx))
        return out
    raise ValueError("unknown mode " + repr(mode))


# --------------------------------------------------------------- class: pooled_rho
def cls_pooled_rho(side, pool, weighted=True):
    """The four registered cuts, as a scored frame. Target column `target_censored`."""
    D = load_pool(side, pool)
    r = chain_full(D, keep_fits=True)
    F = scored_frame(
        pa=r["blend"], pb=r["cons"], y=r["y"], w=(r["w"] if weighted else None),
        blk=r["yr"], clu=None, target="target_censored",
        leg_names=("blend", "consensus"), label=f"{side}.{pool}",
        refit=(lambda B, rng: boot_refit(D, B, rng, weighted=weighted)))
    F["_pool"] = D
    F["_chain"] = r
    return F


# --------------------------------------------------------------- class: headtohead
def _h2h_cluster_ids(P, real):
    """Cluster ids for the head-to-head frame, recovered WITHOUT reimplementing
    _h2h_pass.

    _h2h_pass emits, for pool row i of side s, one scored row per (consensus_fv, war)
    pair that player owns, and its fold selection and fits depend on X / y / w / fv / dy
    only, never on `rows`. So running the SAME function over a shallow copy whose
    `rows` lists are replaced by sentinel pairs (pool_index, within_player_index)
    returns the emission map for free. The grade leg of the instrumented pass must come
    back identical to the real one, and that is asserted rather than trusted.
    """
    ids, side_tag, off = [], [], 0
    inst = {}
    for s, D in P.items():
        marked = dict(D)
        marked["rows"] = [[(float(off + i), float(j)) for j in range(len(rw))]
                          for i, rw in enumerate(D["rows"])]
        inst[s] = marked
        side_tag.append((s, off))
        off += D["n"]
    g2, c2, _t2 = _h2h_pass(inst)
    if not np.array_equal(g2, real[0]):
        raise AssertionError("instrumented h2h pass diverged from the real one")
    ids = c2.astype(np.int64)
    sides = np.zeros(len(ids), dtype=np.int64)
    for s, base in side_tag:
        sides[ids >= base] = (1 if s == "pit" else 0)
    return ids, sides


def cls_headtohead():
    """eFV OOS grade against the published consensus on the source_backtest common set.

    Target column `war`, unweighted, and the only class in the family whose frame is
    NOT one row per player. Frame and legs come from efv_mde_lab._load_h2h /
    _h2h_pass, imported so this stays the same frame data/xfv_headtohead_gap.json was
    measured on.
    """
    P, n_common_players = _load_h2h()
    real = _h2h_pass(P)
    g, c, t = real
    clu, sides = _h2h_cluster_ids(P, real)
    F = scored_frame(pa=g, pb=c, y=t, w=None, blk=sides, clu=clu, target="war",
                     leg_names=("efv", "consensus"), label="headtohead_common",
                     refit=None)
    F["_pool"] = P
    F["_common_set_players"] = int(n_common_players)
    return F


def _h2h_drop_pool(P, side, feature):
    """A shallow copy of the head-to-head pool with one feature column removed from ONE
    side's ridge design.

    _h2h_pass reads X / y / w / fv / dy / rows and nothing else, so a shallow copy with a
    narrower X is a legitimate fv-dropped run of the SAME function. This is how the X3
    detection contrast is built for a class whose pass function lives in a read-only
    module and takes no drop_feat argument: the module is not edited and not copied.
    """
    out = {}
    for s, D in P.items():
        if s != side:
            out[s] = D
            continue
        d = dict(D)
        fi = D["keys"].index(feature)
        d["X"] = np.delete(D["X"], fi, axis=1)
        d["keys"] = [k for k in D["keys"] if k != feature]
        out[s] = d
    return out


def cls_headtohead_featdrop(feature="fv", side="hit"):
    """X3 for the head-to-head class: the SAME frame, with the challenger leg refit on
    the spec minus `feature`. Baseline leg is the full-spec eFV grade, so the contrast is
    rho(efv) - rho(efv without the feature) on the common set, target `war`.

    The consensus leg is not involved, which is the point: the head-to-head class refits
    only the eFV leg, so this is the only place a known-real feature effect can enter it.
    """
    P, _n = _load_h2h()
    real = _h2h_pass(P)
    g, _c, t = real
    clu, sides = _h2h_cluster_ids(P, real)
    Pd = _h2h_drop_pool(P, side, feature)
    gd, _cd, td = _h2h_pass(Pd)
    if not np.array_equal(t, td):
        raise AssertionError("dropping a feature moved the head-to-head scored rows")
    F = scored_frame(pa=g, pb=gd, y=t, w=None, blk=sides, clu=clu, target="war",
                     leg_names=("efv_full_spec", "efv_minus_" + feature),
                     label="headtohead_featdrop_" + feature, refit=None)
    F["_pool"] = P
    F["_pool_drop"] = Pd
    return F


def boot_refit_h2h(P, Pd, B, rng):
    """E_refit for a head-to-head contrast: resample the eFV matrix pool BY PLAYER (a
    pool row is a player and carries that player's whole common-set row list), refit the
    forward chain, score both legs on the rows the resampled players own.

    Same protocol as efv_mde_lab.headtohead, which is what data/xfv_headtohead_gap.json
    was measured under; that function is CALLED directly for the shipped contrast, and
    this variant exists only for the two-challenger-leg case (X3), which it cannot do.
    """
    out = []
    for _ in range(B):
        sel = {s: rng.integers(0, P[s]["n"], P[s]["n"]) for s in P}
        a = _h2h_pass(P, sel)
        b = _h2h_pass(Pd, sel)
        if a is None or b is None:
            out.append(float("nan"))
            continue
        out.append(wrho(a[0], a[2]) - wrho(b[0], b[2]))
    return out


# --------------------------------------------------------------- class: block_rho
def _block_tf(pa, pb, y, blk):
    """The block statistic's own transform: percentile position inside each
    (side x cohort-year) block, recomputed on whatever rows are passed.

    block_norm is IMPORTED from efv_mde_lab so the normalization is the one
    data/xfv_mde_floor.json's block leg was measured with.
    """
    return block_norm(blk, pa), block_norm(blk, pb), block_norm(blk, y)


def cls_block_rho(pool="debuted", weighted=True, freeze_transform=False):
    """The joint block-rho instrument: both sides pooled after normalizing each row to
    its percentile inside its own (side x cohort-year) block.

    n 1,645 on the debuted pools, which is the instrument POWER_EXTENSION_GATE.md
    section 2.2 registers and the one data/xfv_mde_floor.json calls `block`. The tag
    `yr * 10 + (1 if pit)` is efv_mde_lab.stats_from's, so hit-2020 and pit-2020 stay
    separate blocks; `partb_floors` checks the point delta against stats_from directly.

    freeze_transform=True holds the normalization fixed at the observed sample and is a
    SENSITIVITY only: on a fresh scored sample the percentiles would be recomputed, so
    freezing them drops a real variance component in the anti-conservative direction.
    """
    Ds = {s: load_pool(s, pool) for s in SIDES}
    rs = {s: chain_full(Ds[s], keep_fits=True) for s in SIDES}
    tag, PA, PB, Y, W = [], [], [], [], []
    for s in SIDES:
        r = rs[s]
        tag.append(r["yr"] * 10 + (1 if s == "pit" else 0))
        PA.append(r["blend"])
        PB.append(r["cons"])
        Y.append(r["y"])
        W.append(r["w"])
    tag, PA, PB, Y, W = (np.concatenate(a) for a in (tag, PA, PB, Y, W))

    def _refit(B, rng):
        out = []
        for _ in range(B):
            t2, a2, b2, y2, w2 = [], [], [], [], []
            ok = True
            for s in SIDES:
                D = Ds[s]
                r = chain_full(D, rng.integers(0, D["n"], D["n"]))
                if r is None:
                    ok = False
                    break
                t2.append(r["yr"] * 10 + (1 if s == "pit" else 0))
                a2.append(r["blend"])
                b2.append(r["cons"])
                y2.append(r["y"])
                w2.append(r["w"])
            if not ok:
                out.append(float("nan"))
                continue
            t2, a2, b2, y2, w2 = (np.concatenate(a) for a in (t2, a2, b2, y2, w2))
            na, nb, ny = _block_tf(a2, b2, y2, t2)
            ww = w2 if weighted else None
            out.append(wrho(na, ny, ww) - wrho(nb, ny, ww))
        return out

    F = scored_frame(pa=PA, pb=PB, y=Y, w=(W if weighted else None), blk=tag, clu=None,
                     target="target_censored", leg_names=("blend", "consensus"),
                     label="block_rho." + pool, refit=_refit,
                     transform=(None if freeze_transform else _block_tf))
    if freeze_transform:
        na, nb, ny = _block_tf(PA, PB, Y, tag)
        F["pa"], F["pb"], F["y"] = na, nb, ny
    F["_pools"] = Ds
    F["_chains"] = rs
    return F


# --------------------------------------------------------------- class: feature_add
def cls_feature_add(side="hit", pool="full", feature="fv", leg="ridge",
                    instrument="pooled", lam=None, weighted=True):
    """The contrast every driver lane needs: the shipped spec against the same spec with
    one feature removed, both legs refit inside the same forward chain.

    leg="ridge"   the model leg the feature actually enters. AMENDED PRIMARY for `fv`,
                  per part A: blend = (1-lam)*consensus + lam*ridge and the consensus leg
                  is an OLS on `fv`, so the blend contrast leaves `fv` in at weight 0.30.
    leg="blend"   the shipped output. Reported for every cell because a general driver
                  feature is not in the consensus leg and the blend IS what ships.
    instrument    "pooled" scores the side's own pooled rho; "block" scores the joint
                  block instrument with the drop applied to `side` only, which is what a
                  driver lane that reports block-rho would actually be measuring.
    lam           overrides the pinned blend weight; used by the lambda_shift class's X3.
    """
    D = load_pool(side, pool)
    lam_use = D["lam"] if lam is None else float(lam)
    fi = D["keys"].index(feature)
    r_a = chain_full(D, lam=lam_use)
    r_b = chain_full(D, lam=lam_use, drop_feat=fi)
    if not np.array_equal(r_a["y"], r_b["y"]):
        raise AssertionError("dropping a feature moved the scored rows")
    pa, pb = _leg(r_a, leg, lam_use), _leg(r_b, leg, lam_use)
    label = f"feature_add.{side}.{pool}.{feature}.{instrument}.{leg}"
    other = "pit" if side == "hit" else "hit"
    Do = None if instrument == "pooled" else load_pool(other, pool)
    r_o = None if Do is None else chain_full(Do)

    def _refit_multi(B, rng, legs=("ridge", "blend")):
        """ONE refit stream serving every leg of this contrast. The blend and ridge legs
        are algebraic reads of the SAME two chains, so drawing a separate stream per leg
        would charge two independent refits to one refit."""
        out = {lg: [] for lg in legs}
        for _ in range(B):
            sel = rng.integers(0, D["n"], D["n"])
            selo = None if Do is None else rng.integers(0, Do["n"], Do["n"])
            a = chain_full(D, sel, lam=lam_use)
            b = chain_full(D, sel, lam=lam_use, drop_feat=fi)
            o = None if Do is None else chain_full(Do, selo)
            if a is None or b is None or (Do is not None and o is None):
                for lg in legs:
                    out[lg].append(float("nan"))
                continue
            for lg in legs:
                A, Bl = _leg(a, lg, lam_use), _leg(b, lg, lam_use)
                yy, ww = a["y"], (a["w"] if weighted else None)
                if Do is not None:
                    t2 = np.concatenate([a["yr"] * 10 + (1 if side == "pit" else 0),
                                         o["yr"] * 10 + (1 if other == "pit" else 0)])
                    ol = _leg(o, lg, Do["lam"])
                    A = np.concatenate([A, ol])
                    Bl = np.concatenate([Bl, ol])
                    yy = np.concatenate([a["y"], o["y"]])
                    ww = np.concatenate([a["w"], o["w"]]) if weighted else None
                    A, Bl, yy = _block_tf(A, Bl, yy, t2)
                out[lg].append(wrho(A, yy, ww) - wrho(Bl, yy, ww))
        return out

    if instrument == "pooled":
        F = scored_frame(pa=pa, pb=pb, y=r_a["y"], w=(r_a["w"] if weighted else None),
                         blk=r_a["yr"], clu=None, target="target_censored",
                         leg_names=("full_spec", "minus_" + feature), label=label,
                         refit=(lambda B, rng: _refit_multi(B, rng, (leg,))[leg]))
        F["_pool"] = D
        F["_refit_multi"] = _refit_multi
        return F

    ot = r_o["yr"] * 10 + (1 if other == "pit" else 0)
    st = r_a["yr"] * 10 + (1 if side == "pit" else 0)
    ol = _leg(r_o, leg, Do["lam"])
    F = scored_frame(pa=np.concatenate([pa, ol]), pb=np.concatenate([pb, ol]),
                     y=np.concatenate([r_a["y"], r_o["y"]]),
                     w=(np.concatenate([r_a["w"], r_o["w"]]) if weighted else None),
                     blk=np.concatenate([st, ot]), clu=None, target="target_censored",
                     leg_names=("full_spec", "minus_" + feature), label=label,
                     refit=(lambda B, rng: _refit_multi(B, rng, (leg,))[leg]),
                     transform=_block_tf)
    F["_pool"] = D
    F["_refit_multi"] = _refit_multi
    return F


# --------------------------------------------------------------- class: lambda_shift
def cls_lambda_shift(side="hit", pool="full", shift=0.05, weighted=True):
    """Blend at the pinned lambda against blend at pin minus `shift`, on the SAME fits.

    The pin is 0.70 on the hitter side and the selector's own argmax is 0.51, so the
    registered shifts are 0.05, 0.10 and the full 0.19. Both legs are algebraic
    recombinations of one forward chain (blend = (1-lam)*cons + lam*ridge), so nothing
    is refit between the legs and the entire delta is the mixing weight. A POSITIVE
    delta means the pin outranks the shifted value.
    """
    D = load_pool(side, pool)
    lam = D["lam"]
    lam2 = round(lam - float(shift), 10)
    r = chain_full(D, keep_fits=True)
    ridge = _leg(r, "ridge", lam)
    pa = r["blend"]
    pb = (1 - lam2) * r["cons"] + lam2 * ridge

    def _refit(B, rng):
        out = []
        for _ in range(B):
            a = chain_full(D, rng.integers(0, D["n"], D["n"]))
            if a is None:
                out.append(float("nan"))
                continue
            rg = _leg(a, "ridge", lam)
            ww = a["w"] if weighted else None
            out.append(wrho(a["blend"], a["y"], ww)
                       - wrho((1 - lam2) * a["cons"] + lam2 * rg, a["y"], ww))
        return out

    F = scored_frame(pa=pa, pb=pb, y=r["y"], w=(r["w"] if weighted else None),
                     blk=r["yr"], clu=None, target="target_censored",
                     leg_names=(f"blend_lam{lam}", f"blend_lam{lam2:g}"),
                     label=f"lambda_shift.{side}.{pool}.{shift:g}", refit=_refit)
    F["_pool"] = D
    F["_lam"] = lam
    F["_lam2"] = lam2
    F["_chain"] = r
    return F


def boot_refit_lambda(D, shifts, B, rng, weighted=True):
    """One refit stream serving every lambda shift: each draw refits ONE chain and reads
    all three shifted legs off it, exactly as the point estimate does. Three separate
    streams would charge three independent refits to a statistic that only has one."""
    lam = D["lam"]
    out = {float(s): [] for s in shifts}
    for _ in range(B):
        a = chain_full(D, rng.integers(0, D["n"], D["n"]))
        if a is None:
            for s in shifts:
                out[float(s)].append(float("nan"))
            continue
        rg = _leg(a, "ridge", lam)
        ww = a["w"] if weighted else None
        base = wrho(a["blend"], a["y"], ww)
        for s in shifts:
            l2 = round(lam - float(s), 10)
            out[float(s)].append(base - wrho((1 - l2) * a["cons"] + l2 * rg, a["y"], ww))
    return out


# --------------------------------------------------------------- multiplicity: Holm
def _z_one_sided(alpha):
    """z with P(Z > z) = alpha, by bisection on math.erfc.

    Hand-rolled on the stdlib: statsmodels is installed in this environment but is
    UNDECLARED in requirements.txt, so anything that imports it is not shippable.
    Reduction check, emitted with every Holm block: this returns 1.6449 at 0.05 and
    2.2414 at 0.0125, which are Z95_ONE and the incumbent's hardcoded Z_BONF4_ONE.
    """
    lo, hi = 0.0, 40.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if 0.5 * math.erfc(mid / math.sqrt(2.0)) > alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _p_one_sided(delta, sd):
    """The p-value the program's own floor convention already implies. `resolvable` is
    |delta| >= 1.645*sd, which is exactly p <= 0.05 for p = P(Z > |delta|/sd); the
    Bonferroni k=4 line is exactly p <= 0.0125. So ordering the family on this p keeps
    Holm on the same scale as every floor already published."""
    if not sd or sd <= 0:
        return 1.0
    return 0.5 * math.erfc((abs(float(delta)) / float(sd)) / math.sqrt(2.0))


def holm_family(cells, alpha=0.05):
    """Holm step-down over a family of k cells, replacing the hardcoded k=4 Bonferroni.

    Holm is uniformly more powerful than Bonferroni (its first step is alpha/k, every
    later step is looser), controls FWER under ARBITRARY dependence, and costs nothing.
    The k=4 key name is NOT reused: floors land under `mde95_holm_k{k}`, because a
    label that says k=4 while the family is larger is how a multiplicity correction
    quietly stops being one.

    cells: [{"key": str, "delta": float, "sd": float}, ...] in a fixed order. Ties in p
    break on that order, so the output does not depend on sort stability.
    """
    k = len(cells)
    st = []
    for i, c in enumerate(cells):
        sd = float(c["sd"]) if c.get("sd") else 0.0
        st.append({"key": c["key"], "_order": i, "delta": round(float(c["delta"]), 5),
                   "sd": round(sd, 5), "abs_t": (round(abs(float(c["delta"])) / sd, 3)
                                                 if sd > 0 else None),
                   "p_one_sided": round(_p_one_sided(c["delta"], sd), 5)})
    order = sorted(range(k), key=lambda i: (st[i]["p_one_sided"], st[i]["_order"]))
    live = True
    for step, i in enumerate(order, 1):
        a_step = alpha / (k - step + 1)
        z_step = _z_one_sided(a_step)
        s = st[i]
        s["holm_step"] = step
        s["holm_alpha"] = round(a_step, 6)
        s["holm_z_one_sided"] = round(z_step, 4)
        s["mde95_holm_k%d" % k] = round(z_step * s["sd"], 4)
        s["clears_own_holm_step"] = bool(s["p_one_sided"] <= a_step)
        if live and s["clears_own_holm_step"]:
            s["reject_holm"] = True
        else:
            live = False
            s["reject_holm"] = False
        s.pop("_order")
    return {
        "k": k, "alpha": alpha, "procedure": "Holm step-down, one-sided on |delta|/sd",
        "bonferroni_z_one_sided": round(_z_one_sided(alpha / k), 4),
        "reduction_check": {
            "z_at_0.05": round(_z_one_sided(0.05), 4),
            "z_at_0.0125": round(_z_one_sided(0.05 / 4), 4),
            "matches_Z95_ONE": bool(abs(_z_one_sided(0.05) - Z95_ONE) < 5e-4),
            "matches_Z_BONF4_ONE": bool(abs(_z_one_sided(0.0125) - Z_BONF4_ONE) < 5e-5),
        },
        "note": ("uniformly more powerful than Bonferroni and valid under arbitrary "
                 "dependence. Step 1 uses alpha/k, so a family where nothing clears "
                 "Bonferroni also clears nothing here."),
        "cells": st,
    }


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


def verdict_general(B: int = 2000, sd_ratio: dict | None = None, verbose: bool = True):
    """The four cuts through the GENERALIZED path, in ROW mode.

    Deliberately a mirror of verdict() rather than a refactor OF it: the incumbent
    stays byte-frozen so `parity_x1` has a real oracle to check against, and so the
    published part-A stream provably cannot move. Same seed offset, same three legs in
    the same order, same key set. Any divergence IS the X1 parity failure.
    """
    if verbose:
        print(f"=== VERDICT (generalized path): four cuts, both estimators (B={B}) ===")
    rng = np.random.default_rng(SEED + 9)
    out = {}
    for key, side, pool, rank in CUTS:
        F = cls_pooled_rho(side, pool)
        pt = frame_delta(F)
        row = {"rank": rank, "legs": frame_legs(F), "n_scored": int(F["n"])}
        row["refit"] = summarize(F["refit"](B, rng), pt)
        row["cond_iid"] = summarize(boot_cond_cluster(F, B, rng, mode="row"), pt)
        row["cond_strat"] = summarize(boot_cond_cluster(F, B, rng, mode="strat"), pt)
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
    out["multiplicity"] = {
        "primary": "hit.full_pool_km, named in the lane brief before measurement",
        "secondary_k": 4,
        "bonferroni_z_one_sided": Z_BONF4_ONE,
        "note": "no secondary cut is called resolvable on its unadjusted floor alone",
    }
    return out


# ===================================================================== X1 parity gate
def _stored_sd_ratios():
    """The coverage-corrected sd ratios part A registered, so the parity run exercises
    the correction branch too. Read from the artifact, never recomputed here: a
    recomputed ratio would make the parity check compare two different corrections."""
    if not OUT_PATH.exists():
        return None
    art = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    legs = (art.get("coverage") or {}).get("legs") or {}
    r = {k: legs[k].get("sd_ratio_boot_over_true") for k in legs
         if k in ("refit", "cond_iid", "cond_strat")}
    return r or None


def _draw_streams(B, rng_seed):
    """The two draw streams, incumbent and generalized, each run in ONE shared
    generator across the four cuts in CUTS order, exactly as verdict() does. Compared
    element by element, which is a far stronger claim than comparing rounded floors."""
    inc, gen = {}, {}
    rng = np.random.default_rng(rng_seed)
    for key, side, pool, _rank in CUTS:
        D = load_pool(side, pool)
        r = chain_full(D, keep_fits=True)
        inc[(key, "refit")] = boot_refit(D, B, rng)
        inc[(key, "cond_iid")] = boot_cond(r, B, rng, stratify=False)
        inc[(key, "cond_strat")] = boot_cond(r, B, rng, stratify=True)
    rng = np.random.default_rng(rng_seed)
    for key, side, pool, _rank in CUTS:
        F = cls_pooled_rho(side, pool)
        gen[(key, "refit")] = F["refit"](B, rng)
        gen[(key, "cond_iid")] = boot_cond_cluster(F, B, rng, mode="row")
        gen[(key, "cond_strat")] = boot_cond_cluster(F, B, rng, mode="strat")
    return inc, gen


def _row_mode_is_degenerate_cluster(B=300):
    """Constraint check, not a result: mode="row" must BE mode="cluster" with one row
    per cluster. If it is not, then the four registered cuts and the clustered classes
    are running two different estimators and nothing in part B is comparable."""
    F = cls_pooled_rho("hit", "debuted")
    a = boot_cond_cluster(F, B, np.random.default_rng(SEED + 9), mode="row")
    G = scored_frame(pa=F["pa"], pb=F["pb"], y=F["y"], w=F["w"], blk=F["blk"],
                     clu=np.arange(F["n"]), target=F["target"],
                     leg_names=F["leg_names"])
    b = boot_cond_cluster(G, B, np.random.default_rng(SEED + 9), mode="cluster")
    return bool(np.array_equal(np.asarray(a), np.asarray(b))), int(B)


def _basis_drift():
    """Are today's pools the pools part A was registered on? Floors are functions of
    the data, so a moved basis makes the STORED numbers unreproducible for reasons that
    have nothing to do with the generalization. Measured first and reported separately
    so a data drift can never be read as a code parity failure, or the reverse.
    """
    if not OUT_PATH.exists():
        return None
    art = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    vd = art.get("verdict") or {}
    rows = {}
    same = True
    for key, side, pool, _rank in CUTS:
        F = cls_pooled_rho(side, pool)
        now = frame_legs(F)
        was = (vd.get(key) or {}).get("legs") or {}
        match = all(now.get(k) == was.get(k) for k in ("n", "consensus", "blend", "delta"))
        same = same and match
        rows[key] = {"registered": was, "today": now, "identical": bool(match),
                     "delta_shift": (round(now["delta"] - was["delta"], 5)
                                     if "delta" in was else None)}
    return {"part_a_generated_at": art.get("generated_at"), "cuts": rows,
            "basis_unchanged": bool(same)}


def parity_x1(B: int = 2000, write: bool = True, verbose: bool = True):
    """X1 PARITY, the part-B stop gate (POWER_EXTENSION_GATE.md sections 3.2 and 4.1).

    The four registered cuts must reproduce EXACTLY under the generalized estimator in
    row mode at the same seed. Three checks, strongest first:
      1. every bootstrap draw identical, element by element, across all four cuts and
         all three legs (B x 12 floats)
      2. the serialized verdict rows identical, key for key
      3. row mode is the degenerate one-row-per-cluster case of the cluster resampler

    Reproduction is checked against the INCUMBENT CODE RUN NOW, not against the stored
    artifact, because the stored artifact is a function of the pools as they stood on
    2026-08-08. `basis_drift` reports separately whether those pools still hold.
    """
    t0 = time.time()
    if verbose:
        print(f"=== X1 PARITY: four registered cuts, generalized vs incumbent (B={B}) ===")
    drift = _basis_drift()
    ratios = _stored_sd_ratios()
    inc_d, gen_d = _draw_streams(B, SEED + 9)
    draws = {}
    all_same = True
    for k in inc_d:
        a = np.asarray(inc_d[k], dtype=float)
        b = np.asarray(gen_d[k], dtype=float)
        ident = bool(a.shape == b.shape and np.array_equal(a, b, equal_nan=True))
        mad = (float(np.nanmax(np.abs(a - b))) if a.shape == b.shape else None)
        all_same = all_same and ident
        draws[f"{k[0]}.{k[1]}"] = {"B": int(len(a)), "identical": ident,
                                   "max_abs_diff": (0.0 if mad == 0 else mad)}
    vi = verdict(B, sd_ratio=ratios, verbose=False)
    vg = verdict_general(B, sd_ratio=ratios, verbose=False)
    si = json.dumps(vi, sort_keys=True)
    sg = json.dumps(vg, sort_keys=True)
    rows_same = bool(si == sg)
    deg, deg_b = _row_mode_is_degenerate_cluster()
    verdict_str = ("PASS" if (all_same and rows_same and deg) else "FAIL")
    out = {
        "gate": "X1 parity",
        "verdict": verdict_str,
        "B": int(B), "seed": SEED + 9,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_power_lab.py parity_x1",
        "draws_identical_all": bool(all_same),
        "draws": draws,
        "verdict_rows_identical": rows_same,
        "row_mode_is_degenerate_cluster": {"identical": deg, "B": deg_b},
        "sd_ratios_applied": ratios,
        "checked_against": ("the incumbent code path run in the same process on the same "
                            "pools, NOT the stored artifact: floors are functions of the "
                            "data, so a moved basis is a separate finding"),
        "basis_drift": drift,
        "elapsed_s": round(time.time() - t0, 1),
    }
    if not rows_same:
        diff = [k for k in vg if json.dumps(vg[k], sort_keys=True)
                != json.dumps(vi.get(k), sort_keys=True)]
        out["diverging_keys"] = diff
    if verbose:
        for k, v in draws.items():
            print(f"  {k:<30} B {v['B']:<5} identical {v['identical']} "
                  f"max_abs_diff {v['max_abs_diff']}")
        print(f"  verdict rows identical: {rows_same}")
        print(f"  row mode == degenerate cluster: {deg}")
        print(f"  basis unchanged since part A: {drift and drift['basis_unchanged']}")
        print(f"  X1 -> {verdict_str}  ({out['elapsed_s']}s)")
    if write:
        merge_artifact({"x1_parity": out})
    return out


def h2hshape(B: int = 2000, write: bool = True, verbose: bool = True):
    """Head-to-head frame shape and the SIZE OF THE CLUSTERING VIOLATION.

    Not a floor and not a gate. The class is UNFLOORED until its own two-sided coverage
    check passes (POWER_EXTENSION_GATE.md sections 3.3 and 7). What is published here
    is the structural fact that makes clustering mandatory, plus the i.i.d.-row
    diagnostic: publishing how much the row variant narrows the sd is the check that
    clustering was preserved.
    """
    F = cls_headtohead()
    groups = _frame_groups(F, "clu")
    sizes = np.array([len(g) for g in groups], dtype=float)
    rng = np.random.default_rng(SEED + SEED_OFF["h2h_cluster"])
    d_clu = np.asarray(boot_cond_cluster(F, B, rng, mode="cluster"), dtype=float)
    d_str = np.asarray(boot_cond_cluster(F, B, rng, mode="cluster_strat"), dtype=float)
    d_row = np.asarray(boot_cond_cluster(F, B, rng, mode="row"), dtype=float)
    sd_c = float(np.nanstd(d_clu, ddof=1))
    sd_s = float(np.nanstd(d_str, ddof=1))
    sd_r = float(np.nanstd(d_row, ddof=1))
    out = {
        "class": "headtohead_common",
        "status": ("UNFLOORED. No floor is quoted until this class passes its own "
                   "two-sided coverage gate against its own conditional estimand."),
        "target_column": F["target"],
        "legs": frame_legs(F),
        "n_rows": int(F["n"]),
        "n_clusters_scored": int(len(groups)),
        "common_set_players": F["_common_set_players"],
        "rows_per_cluster": round(float(sizes.mean()), 3),
        "rows_per_cluster_max": int(sizes.max()),
        "cond_sd_cluster": round(sd_c, 5),
        "cond_sd_cluster_side_stratified": round(sd_s, 5),
        "cond_sd_row_iid_DIAGNOSTIC": round(sd_r, 5),
        "iid_row_narrowing_ratio": round(sd_c / sd_r, 3) if sd_r > 0 else None,
        "diagnostic_reading": (
            "the row variant is the size of the clustering violation, never a gate. "
            "A frame with 3.07 rows per player scored as 3.07 independent rows narrows "
            "the sd by the ratio above, all of it in the anti-conservative direction."),
        "B": int(B), "seed": SEED + SEED_OFF["h2h_cluster"],
    }
    if verbose:
        print("=== HEAD-TO-HEAD FRAME SHAPE ===")
        print(f"  rows {out['n_rows']} over {out['n_clusters_scored']} players "
              f"({out['rows_per_cluster']} per player, max {out['rows_per_cluster_max']})")
        print(f"  legs {out['legs']}")
        print(f"  cond sd  cluster {sd_c:.5f}  cluster_strat {sd_s:.5f}  "
              f"row_iid {sd_r:.5f}  -> narrowing {out['iid_row_narrowing_ratio']}x")
    if write:
        merge_artifact({"headtohead_frame": out})
    return out


# ============================================================ PART B step 2: floors
def floor_cell(label, F, refit_draws, cond_draws, cond_unit, point=None, extra=None):
    """One statistic class, both estimators, in the key shape the scoreboard needs.

    NO CLAIM WITHOUT ITS ESTIMATOR: every cell carries MDE95 (E_refit) and MDE95_COND
    (E_cond) side by side, and a verdict under each. A cell that quotes one number is
    incomplete, which is the defect POWER_EXTENSION_GATE.md section 0 opens on.
    """
    pt = frame_delta(F) if point is None else float(point)
    ref = summarize(refit_draws, pt) if refit_draws is not None else None
    con = summarize(cond_draws, pt)
    row = {
        "label": label,
        "target_column": F["target"],
        "n_rows": int(F["n"]),
        "n_clusters": (None if F["clu"] is None else len(_frame_groups(F, "clu"))),
        "cond_resampling_unit": cond_unit,
        "legs": frame_legs(F),
        "point_delta": round(pt, 5),
        "MDE95": (ref or {}).get("MDE95"),
        "MDE95_COND": con.get("MDE95"),
        "margin_over_MDE95": (ref or {}).get("margin_over_floor"),
        "margin_over_MDE95_COND": con.get("margin_over_floor"),
        "verdict_E_refit": (ref or {}).get("verdict"),
        "verdict_E_cond": con.get("verdict"),
        "E_refit": ref,
        "E_cond": con,
    }
    sr = (ref or {}).get("sd")
    sc = con.get("sd")
    if sr and sc:
        # The decomposition the incumbent measures only on hit.full_pool: with the fits
        # fixed, E_cond IS the test-only leg, so sd_refit^2 - sd_cond^2 is the fit
        # component. decomp() checked additivity holds to 0.906x there; anywhere it goes
        # negative the subtraction is reported as NOT ADDITIVE rather than clipped away.
        share = 1.0 - (sc ** 2) / (sr ** 2)
        row["refit_share_of_variance"] = round(share, 3)
        row["fit_fixed_share_of_variance"] = round((sc ** 2) / (sr ** 2), 3)
        # UNITS. `share` is a share of VARIANCE; the floor is an sd. Driving test n to
        # infinity with the training corpus HELD leaves sqrt(share) of the floor
        # standing, so the removable part is 1 - sqrt(share), not 1 - sqrt(1-share).
        # On the pooled cut that is 1 - sqrt(0.541) = 0.265, which is the 27% figure
        # in plan section 9.1 and the check that this line is the right way up.
        row["floor_share_removable_by_infinite_test_n"] = round(
            1.0 - math.sqrt(max(0.0, share)), 3)
        if share <= 0:
            row["decomposition_note"] = ("NOT ADDITIVE: the conditional sd is not smaller "
                                         "than the refit sd on this cell, so no fit share "
                                         "can be read off the pair")
        else:
            asym = Z95_ONE * math.sqrt(max(0.0, sr ** 2 - sc ** 2))
            row["E_refit_floor_asymptote_infinite_test_n"] = round(asym, 4)
            row["permanently_undecidable_under_E_refit"] = bool(abs(pt) < asym)
    if extra:
        row.update(extra)
    return row


def partb_floors(B_pool: int = 1000, B_h2h: int = 2000, B_weak: int = 500,
                 write: bool = True, verbose: bool = True):
    """THE FIVE FLOORS. head-to-head common set, block-rho, feature-add on both
    instruments, and the three registered lambda shifts, each under BOTH estimators.

    B differs by class and is reported per cell: a bootstrap sd has relative error
    1/sqrt(2B), so B = 1,000 carries 2.2% and B = 2,000 carries 1.6%. The head-to-head
    E_refit leg runs at 2,000 because it is the one leg that reproduces a SHIPPED
    constant (XFV_HEADTOHEAD_MDE95, ledger data/xfv_headtohead_gap.json) and must stay
    comparable to it.
    """
    t0 = time.time()
    cells = {}
    notes = {}

    # ------------------------------- 0. the four registered cuts, on TODAY's basis
    # NOT a replacement for the part-A registration and not byte-comparable with it (new
    # seed, smaller B, and the matrices moved on 2026-08-09 14:08). It exists so the
    # adjudication table is on ONE basis: part A's stored `verdict` block is on the
    # 2026-08-08 pools, and mixing a 2026-08-08 sd with a 2026-08-09 delta is exactly the
    # staleness that crossed a verdict boundary in part A.
    if verbose:
        print("=== FLOORS 0/5: the four registered cuts, re-derived on today's basis ===",
              flush=True)
    rng = np.random.default_rng(SEED + SEED_OFF["pooled_today"])
    for key, side, pool, rank in CUTS:
        F = cls_pooled_rho(side, pool)
        ref = F["refit"](B_pool, rng)
        con = boot_cond_cluster(F, B_pool, rng, mode="row")
        row = floor_cell("pooled_rho." + key, F, ref, con, "scored row")
        row["B"] = int(B_pool)
        row["rank"] = rank
        row["basis"] = "re-derived 2026-08-09, NOT the registered part-A numbers"
        cells["pooled_rho." + key] = row

    # ---------------------------------------------------- 1. head-to-head common set
    if verbose:
        print("=== FLOORS 1/5: headtohead_common ===", flush=True)
    F = cls_headtohead()
    rng = np.random.default_rng(SEED + SEED_OFF["h2h_cluster"])
    d_clu = boot_cond_cluster(F, B_h2h, rng, mode="cluster")
    d_str = boot_cond_cluster(F, B_h2h, rng, mode="cluster_strat")
    d_row = boot_cond_cluster(F, B_h2h, rng, mode="row")
    # E_refit is the SHIPPED producer called directly, not a private copy: same seed
    # (SEED + 1), same protocol, same code path as data/xfv_headtohead_gap.json.
    hh = MDE.headtohead(B_h2h, write=False)
    pt = frame_delta(F)
    ref_sd = float(hh["sd"])
    ref_leg = {"B_used": hh["B_used"], "point_delta": hh["point"]["delta"], "sd": ref_sd,
               "MDE95": round(Z95_ONE * ref_sd, 4),
               "mde95_twosided": round(Z95_TWO * ref_sd, 4), "ci95": hh["ci95"],
               "p_gt_0": hh["p_gt_0"],
               "margin_over_floor": round(abs(pt) / (Z95_ONE * ref_sd), 3),
               "resolvable": bool(abs(pt) >= Z95_ONE * ref_sd),
               "verdict": ("RESOLVABLE " + ("WIN" if pt > 0 else "LOSS")
                           if abs(pt) >= Z95_ONE * ref_sd else "NULL"),
               "producer": "efv_mde_lab.headtohead(B, write=False), seed SEED+1",
               "note": ("its own point delta is on the SAME frame; any difference from "
                        "this cell's point_delta is the unrounded-vs-published primitive")}
    row = floor_cell("headtohead_common", F, None, d_clu, "player cluster", point=pt)
    row["E_refit"] = ref_leg
    row["MDE95"] = ref_leg["MDE95"]
    row["margin_over_MDE95"] = ref_leg["margin_over_floor"]
    row["verdict_E_refit"] = ref_leg["verdict"]
    sc = row["E_cond"]["sd"]
    if sc and ref_sd:
        share = 1.0 - (sc ** 2) / (ref_sd ** 2)
        row["refit_share_of_variance"] = round(share, 3)
        row["fit_fixed_share_of_variance"] = round((sc ** 2) / (ref_sd ** 2), 3)
        # UNITS. `share` is a share of VARIANCE; the floor is an sd. Driving test n to
        # infinity with the training corpus HELD leaves sqrt(share) of the floor
        # standing, so the removable part is 1 - sqrt(share), not 1 - sqrt(1-share).
        # On the pooled cut that is 1 - sqrt(0.541) = 0.265, which is the 27% figure
        # in plan section 9.1 and the check that this line is the right way up.
        row["floor_share_removable_by_infinite_test_n"] = round(
            1.0 - math.sqrt(max(0.0, share)), 3)
        if share > 0:
            asym = Z95_ONE * math.sqrt(ref_sd ** 2 - sc ** 2)
            row["E_refit_floor_asymptote_infinite_test_n"] = round(asym, 4)
            row["permanently_undecidable_under_E_refit"] = bool(abs(pt) < asym)
    row["sensitivity_cluster_side_stratified"] = summarize(d_str, pt)
    row["DIAGNOSTIC_row_iid_NOT_A_GATE"] = summarize(d_row, pt)
    row["iid_row_narrowing_ratio"] = round(row["E_cond"]["sd"]
                                           / row["DIAGNOSTIC_row_iid_NOT_A_GATE"]["sd"], 3)
    row["clustering_note"] = (
        "3.07 rows per player. The row-iid variant is published as the SIZE OF THE "
        "VIOLATION, never as a gate: scoring 3.07 correlated rows as 3.07 independent "
        "ones narrows the sd by the ratio above, entirely in the anti-conservative "
        "direction.")
    row["B"] = int(B_h2h)
    cells["headtohead_common"] = row

    # ---------------------------------------------------- 2. block rho
    if verbose:
        print("=== FLOORS 2/5: block_rho ===", flush=True)
    Fb = cls_block_rho("debuted")
    rng = np.random.default_rng(SEED + SEED_OFF["block_rho"])
    b_ref = Fb["refit"](B_pool, rng)
    b_row = boot_cond_cluster(Fb, B_pool, rng, mode="row")
    b_str = boot_cond_cluster(Fb, B_pool, rng, mode="strat")
    Ffz = cls_block_rho("debuted", freeze_transform=True)
    b_frz = boot_cond_cluster(Ffz, B_pool, np.random.default_rng(SEED + SEED_OFF["block_rho"]),
                              mode="row")
    row = floor_cell("block_rho.debuted", Fb, b_ref, b_row, "scored row")
    row["sensitivity_block_stratified"] = summarize(b_str, frame_delta(Fb))
    row["DIAGNOSTIC_frozen_normalization"] = summarize(b_frz, frame_delta(Ffz))
    row["normalization_note"] = (
        "the percentile-inside-block transform is RECOMPUTED on every resample, because "
        "a fresh scored sample would recompute it. Freezing it at the observed sample "
        "drops that component; the diagnostic above is how much.")
    row["B"] = int(B_pool)
    cells["block_rho"] = row
    st = MDE.stats_from({s: MDE.chain(MDE.load_side(s)) for s in SIDES}, weighted=True)
    notes["block_rho_class_parity"] = {
        "class_delta": frame_legs(Fb)["delta"],
        "efv_mde_lab_stats_from_delta": round(st["block"]["delta"], 5),
        # 1e-5, not 1e-9: frame_legs rounds to 5 decimals and stats_from does not,
        # so a tighter tolerance would report a rounding difference as a parity failure.
        "identical": bool(abs(frame_legs(Fb)["delta"] - st["block"]["delta"]) < 1e-5),
        "n_class": int(Fb["n"]), "n_stats_from": int(st["block"]["n"]),
    }

    # ---------------------------------------------------- 3-4. feature add, both instruments
    for inst in ("pooled", "block"):
        if verbose:
            print(f"=== FLOORS 3/5: feature_add fv, {inst} instrument ===", flush=True)
        rng = np.random.default_rng(SEED + SEED_OFF["feature_add" if inst == "pooled" else "feature_add_block"])
        Fr = cls_feature_add("hit", "full", "fv", leg="ridge", instrument=inst)
        Fbl = cls_feature_add("hit", "full", "fv", leg="blend", instrument=inst)
        multi = Fr["_refit_multi"](B_pool, rng, ("ridge", "blend"))
        for lg, Fx in (("ridge", Fr), ("blend", Fbl)):
            key = f"feature_add.fv.{inst}.{lg}"
            cond = boot_cond_cluster(Fx, B_pool, rng, mode="row")
            row = floor_cell(key, Fx, multi[lg], cond, "scored row")
            row["B"] = int(B_pool)
            row["primary"] = bool(lg == "ridge")
            row["leg_note"] = (
                "ridge leg is the AMENDED PRIMARY for `fv`: blend = (1-lam)*consensus + "
                "lam*ridge and the consensus leg is an OLS on `fv`, so the blend contrast "
                "leaves `fv` in at weight 0.30 and its truth is near zero by construction."
                if lg == "ridge" else
                "blend leg is the SHIPPED output. For `fv` it is mis-specified (see the "
                "ridge cell); for a general driver feature it is the right contrast.")
            cells[key] = row

    # a second feature, so the floor's FEATURE DEPENDENCE is visible rather than implied
    if B_weak:
        if verbose:
            print("=== FLOORS 3/5b: feature_add weak feature (floor is feature specific) ===",
                  flush=True)
        rng = np.random.default_rng(SEED + SEED_OFF["feature_add_weak"])
        Fw = cls_feature_add("hit", "full", "tool_speed", leg="ridge", instrument="pooled")
        wmulti = Fw["_refit_multi"](B_weak, rng, ("ridge",))
        cond = boot_cond_cluster(Fw, B_weak, rng, mode="row")
        row = floor_cell("feature_add.tool_speed.pooled.ridge", Fw, wmulti["ridge"], cond,
                         "scored row")
        row["B"] = int(B_weak)
        row["role"] = ("feature-dependence control. A feature-add floor is a property of "
                       "the FEATURE as well as the frame; quoting the `fv` floor for a "
                       "weak candidate would understate it.")
        cells["feature_add.tool_speed.pooled.ridge"] = row

    # ---------------------------------------------------- 5. lambda shift
    if verbose:
        print("=== FLOORS 5/5: lambda_shift 0.05 / 0.10 / 0.19 ===", flush=True)
    shifts = (0.05, 0.10, 0.19)
    D = load_pool("hit", "full")
    rng = np.random.default_rng(SEED + SEED_OFF["lambda_shift"])
    lam_ref = boot_refit_lambda(D, shifts, B_pool, rng)
    for sh in shifts:
        Fl = cls_lambda_shift("hit", "full", sh)
        cond = boot_cond_cluster(Fl, B_pool, rng, mode="row")
        key = f"lambda_shift.{sh:g}"
        row = floor_cell(key, Fl, lam_ref[float(sh)], cond, "scored row")
        row["B"] = int(B_pool)
        row["lambda_pin"] = Fl["_lam"]
        row["lambda_shifted"] = Fl["_lam2"]
        cells[key] = row
    notes["lambda_shift_note"] = (
        "one refit stream serves all three shifts: the legs are algebraic reads of the "
        "SAME chain, so three streams would charge three independent refits to one refit. "
        "A POSITIVE delta means the pinned 0.70 outranks the shifted value.")

    out = {
        "produced_by": "tools/efv_power_lab.py floors",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registration": ("docs/efv-2026-08-08/POWER_EXTENSION_GATE.md sections 2 and 5; "
                         "X1 parity discharged 2026-08-09, X2 in the block "
                         "x2_coverage_h2h"),
        "convention": ("MDE95 is ONE-SIDED 1.645*sd on |delta|, the convention in "
                       "docs/EFV_GATE_STANDARD.md section 1. MDE95 is E_refit, "
                       "MDE95_COND is E_cond. Neither is quoted without its estimator."),
        "B_pool": int(B_pool), "B_h2h": int(B_h2h), "B_weak": int(B_weak),
        "seeds": {k: SEED + v for k, v in SEED_OFF.items()},
        "cells": cells,
        "notes": notes,
        "elapsed_s": round(time.time() - t0, 1),
    }
    if verbose:
        for k, c in cells.items():
            print(f"  {k:<34} d {c['point_delta']:+.5f}  MDE95 {c['MDE95']} "
                  f"({c['margin_over_MDE95']}x {c['verdict_E_refit']})  COND "
                  f"{c['MDE95_COND']} ({c['margin_over_MDE95_COND']}x "
                  f"{c['verdict_E_cond']})")
    if write:
        merge_artifact({"partb_floors": out})
    return out


# ================================================ X2: the CLUSTERED coverage DGP
#
# WHY THIS IS THE HIGHEST-RISK STEP IN THE LANE. make_dgp emits ONE row per unit. The
# head-to-head frame carries 3.068 rows per player, and row-level i.i.d. resampling
# narrows its sd by 1.5x in the ANTI-CONSERVATIVE direction (measured, see
# `headtohead_frame`). A coverage check run on a one-row-per-player simulator would pass
# a broken estimator, so the simulator has to emit k rows per player with the WITHIN
# PLAYER structure the real frame has.
#
# THE STRUCTURE THE REAL FRAME HAS, measured 2026-08-09 on 3,224 rows over 1,051 players:
#   the eFV leg is constant inside 1,051 of 1,051 clusters
#   the target is constant inside 1,051 of 1,051 clusters
#   only the consensus leg varies within a player, and only in 848 of them
#   consensus rank ICC 0.660 (raw 0.693), i.e. 34% of consensus variance is vintage noise
#   rho(efv, war) 0.354, rho(consensus, war) 0.321, rho(efv, consensus) 0.697
# So the generator emits ONE grade, ONE target and k CORRELATED consensus reads per
# player. `make_dgp_h2h` matches all four of those numbers and publishes the match.
def _icc_rank(v, groups):
    """One-way random-effects ICC on RANKS, the scale the statistic actually uses."""
    r = _rankavg(v)
    n, k = len(r), len(groups)
    gm = r.mean()
    ssb = float(sum(len(g) * (r[g].mean() - gm) ** 2 for g in groups))
    ssw = float(sum(((r[g] - r[g].mean()) ** 2).sum() for g in groups))
    msb, msw = ssb / (k - 1), ssw / (n - k)
    k0 = (n - sum(len(g) ** 2 for g in groups) / n) / (k - 1)
    return float((msb - msw) / (msb + (k0 - 1) * msw))


def _normal_scores(v):
    """Latent truth for a target with heavy ties: 39.7% of the head-to-head target is
    exactly 0 WAR, and tied players are genuinely indistinguishable to the statistic, so
    they must share a latent value rather than be ordered arbitrarily.

    ndtri is used rather than the bisection this file uses elsewhere because the
    coverage loop evaluates this 60,000 times; scipy is declared shippable in this repo
    (statsmodels is not, which is why holm_family is hand-rolled).
    """
    from scipy.special import ndtri
    r = _rankavg(v)
    return np.asarray(ndtri((r - 0.5) / len(r)), dtype=float)


def make_dgp_h2h(F, seed=None, verbose=True):
    """Design-matched CLUSTERED generator for the head-to-head frame.

    k_i is drawn ONCE from the empirical rows-per-player distribution and HELD FIXED
    across every draw, exactly as make_dgp holds the 11 fold sizes fixed: otherwise the
    conditional experiment would confound a change of frame size with a redraw of the
    scored sample.

    Per player i: latent u_i (normal score of that player's target rank), one eFV grade
    a_i, k_i consensus reads c_ij.
        a_i  = pe*u_i + qa*s_i + sqrt(1-pe^2-qa^2)*e_i
        c_ij = pc*u_i + qc*s_i + g*eps_ij,   qc = sqrt(1-g^2-pc^2)
    s_i is the SHARED board component. It has to exist: rho(efv, consensus) is 0.697
    while each leg correlates with the target at about 0.33, because eFV is built from
    the consensus (blend = 0.30*consensus + 0.70*ridge, and the ridge's first feature IS
    the consensus grade). Setting qc to its maximum says the consensus's whole
    player-level non-target variance is shared with eFV, which is the closest the model
    gets to that construction.
    The target marginal is resampled CONDITIONAL ON k, so any association between how
    many vintages a player was graded on and how good he turned out survives.
    """
    seed = (SEED + SEED_OFF["h2h_cover"]) if seed is None else seed
    groups = _frame_groups(F, "clu")
    sizes = np.array([len(g) for g in groups], dtype=int)
    first = np.array([g[0] for g in groups])
    y_player = F["y"][first]
    tgt = {
        "rho_a_t": wrho(F["pa"], F["y"]),
        "rho_c_t": wrho(F["pb"], F["y"]),
        "rho_a_c": wrho(F["pa"], F["pb"]),
        "icc_c": _icc_rank(F["pb"], groups),
        "spearman_k_vs_target": wrho(sizes.astype(float), y_player),
    }
    G = len(groups)
    rs = np.random.default_rng(seed)
    kvec = sizes[rs.integers(0, G, G)]
    off = np.concatenate([[0], np.cumsum(kvec)])
    n = int(off[-1])
    rep = np.repeat(np.arange(G), kvec)
    syn_groups = [np.arange(off[i], off[i + 1]) for i in range(G)]
    # target pools conditional on k, so the k <-> outcome association is preserved
    pools = {int(k): y_player[sizes == k] for k in np.unique(sizes)}
    kpos = {int(k): np.flatnonzero(kvec == k) for k in np.unique(kvec)}

    template = scored_frame(pa=np.zeros(n), pb=np.zeros(n), y=np.zeros(n), w=None,
                            blk=None, clu=rep, target="war",
                            leg_names=("efv", "consensus"), label="h2h_synthetic")
    template["_groups_clu"] = syn_groups

    def gen(dseed, pe, pc, g, qa):
        rr = np.random.default_rng(dseed)
        y = np.empty(G, dtype=float)
        for k, pos in kpos.items():
            pool = pools.get(k, y_player)
            y[pos] = pool[rr.integers(0, len(pool), len(pos))]
        u = _normal_scores(y)
        s = rr.standard_normal(G)
        e = rr.standard_normal(G)
        eps = rr.standard_normal(n)
        qc = math.sqrt(max(0.0, 1.0 - g * g - pc * pc))
        resid = math.sqrt(max(0.0, 1.0 - pe * pe - qa * qa))
        a = pe * u + qa * s + resid * e
        c = pc * u[rep] + qc * s[rep] + g * eps
        return a[rep], c, y[rep]

    def frame_of(pa, pb, y):
        template["pa"], template["pb"], template["y"] = pa, pb, y
        return template

    def _mean(fn, pe, pc, g, qa, reps=16, base=None):
        # COMMON RANDOM NUMBERS: the same rep seeds at every bisection step, so the
        # objective is a deterministic function of the parameter and the search does not
        # chase Monte-Carlo noise. reps = 16 because one rep's Spearman carries about
        # 1/sqrt(1051) = 0.031 of cluster-level noise, so 4 reps left 0.015, which is half
        # the effect being matched.
        base = (seed + 101) if base is None else base
        return float(np.mean([fn(*gen(base + 7919 * j, pe, pc, g, qa))
                              for j in range(reps)]))

    def _bisect(fn, target, lo, hi, iters=16):
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            if fn(mid) < target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    # g first: on the latent scale the within-player consensus correlation is 1-g^2, so
    # the ICC pins g without touching anything else. Then pc, then pe (qa cannot move
    # rho(a,t) because a's loading on u is pe whatever qa is), then qa.
    g0 = _bisect(lambda gg: -_mean(lambda pa, pb, yy: _icc_rank(pb, syn_groups),
                                   0.5, 0.4, gg, 0.4), -tgt["icc_c"], 0.05, 0.95)
    pc0 = _bisect(lambda p: _mean(lambda pa, pb, yy: wrho(pb, yy), 0.5, p, g0, 0.3),
                  tgt["rho_c_t"], 0.0, math.sqrt(max(1e-9, 1 - g0 * g0)) - 1e-6)
    qc0 = math.sqrt(max(0.0, 1 - g0 * g0 - pc0 * pc0))
    pe0 = _bisect(lambda p: _mean(lambda pa, pb, yy: wrho(pa, yy), p, pc0, g0,
                                  min(0.3, math.sqrt(max(0.0, 1 - p * p)))),
                  tgt["rho_a_t"], 0.0, 0.99)
    qa_max = math.sqrt(max(0.0, 1 - pe0 * pe0)) - 1e-6
    qa0 = _bisect(lambda q: _mean(lambda pa, pb, yy: wrho(pa, pb), pe0, pc0, g0, q),
                  tgt["rho_a_c"], 0.0, qa_max)
    ach = {
        "rho_a_t": round(_mean(lambda pa, pb, yy: wrho(pa, yy), pe0, pc0, g0, qa0, reps=32), 4),
        "rho_c_t": round(_mean(lambda pa, pb, yy: wrho(pb, yy), pe0, pc0, g0, qa0, reps=32), 4),
        "rho_a_c": round(_mean(lambda pa, pb, yy: wrho(pa, pb), pe0, pc0, g0, qa0, reps=32), 4),
        "icc_c": round(_mean(lambda pa, pb, yy: _icc_rank(pb, syn_groups),
                             pe0, pc0, g0, qa0, reps=32), 4),
        "delta": round(_mean(lambda pa, pb, yy: wrho(pa, yy) - wrho(pb, yy),
                             pe0, pc0, g0, qa0, reps=32), 5),
    }
    params = {"pe": round(pe0, 4), "pc": round(pc0, 4), "g": round(g0, 4),
              "qa": round(qa0, 4), "qc": round(qc0, 4),
              "qa_at_bound": bool(qa0 > qa_max - 1e-4)}
    match = {
        "real": {k: round(float(v), 4) for k, v in tgt.items()},
        "synthetic": ach,
        "params": params,
        "n_rows": n, "n_clusters": G,
        "rows_per_cluster": round(n / G, 3),
        "cluster_sizes_frozen": {int(k): int((kvec == k).sum()) for k in np.unique(kvec)},
        "real_cluster_sizes": {int(k): int((sizes == k).sum()) for k in np.unique(sizes)},
        "limitation": ("matched on rows per player, the cluster-size distribution, the "
                       "target marginal conditional on k, both legs' rho against the "
                       "target, the two legs' rho against each other, and the consensus "
                       "within-player ICC. NOT matched: the eFV leg carries no vintage "
                       "structure at all, because in the real frame it has none."),
    }
    if verbose:
        print("=== H2H CLUSTERED DGP MATCH ===")
        for k in tgt:
            syn = ach.get(k)
            print(f"  {k:<22} real {float(tgt[k]):+.4f}   synthetic "
                  + (f"{syn:+.4f}" if syn is not None else "not matched"))
        print(f"  params {params}")
    return gen, frame_of, params, match, syn_groups


def coverage_h2h(n_check: int = N_CHECK, M: int = 300, B: int = 300, fit_sd=None,
                 write: bool = True, verbose: bool = True):
    """X2 for the head-to-head class: two-sided coverage of the CONDITIONAL estimand by
    the CLUSTER bootstrap, with the row-iid variant run beside it as a diagnostic.

    The conditional estimand: given this training corpus, what is the sampling
    distribution of the delta over redraws of the SCORED SAMPLE. In the synthetic, the
    training corpus is the eFV leg's loading pe, so each of the n_check datasets gets its
    own pe_s, held fixed across that dataset's M fresh samples AND its B bootstrap draws.
    sigma_pe is calibrated so the fit-only spread reproduces the measured fit component
    of this class's real sd (sqrt(sd_refit^2 - sd_cond^2)); with fit_sd=None it is read
    from the partb_floors block, and with no block available it is set to 0 and that is
    stated in the output.

    Gate: central binomial acceptance region for p = 0.95 at n_check, two-sided, per
    docs/EFV_GATE_STANDARD.md section 7.4. n_check = 200 keeps the upper edge strictly
    below 1.000.
    """
    t0 = time.time()
    F = cls_headtohead()
    gen, frame_of, params, match, syn_groups = make_dgp_h2h(F, verbose=verbose)
    pe0, pc0, g0, qa0 = params["pe"], params["pc"], params["g"], params["qa"]

    if fit_sd is None:
        fit_sd = 0.0
        if OUT_PATH.exists():
            art = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            c = ((art.get("partb_floors") or {}).get("cells") or {}).get("headtohead_common")
            if c and c.get("E_refit") and c.get("E_cond"):
                sr, sc = float(c["E_refit"]["sd"]), float(c["E_cond"]["sd"])
                fit_sd = math.sqrt(max(0.0, sr ** 2 - sc ** 2))
    fit_sd = float(fit_sd)

    # Calibrate sigma_pe: how far must the FITTED loading move to produce fit_sd of delta
    # scatter. The scored sample is HELD (one dataset seed) while pe varies, so this
    # isolates the fit component; averaging that sd over 8 samples keeps it from being a
    # property of one draw. Varying the seed and pe together would fold the sampling
    # variance in and set sigma_pe far too small.
    def _fit_scatter(sig, samples=8, reps=12):
        rr = np.random.default_rng(SEED + SEED_OFF["h2h_cover_sigma"])
        zs = rr.standard_normal(reps)
        sds = []
        for j in range(samples):
            ds = [frame_delta(frame_of(*gen(SEED + H2H_DGP_BASE - 1 - j,
                                            pe0 + sig * float(z), pc0, g0, qa0)))
                  for z in zs]
            sds.append(float(np.nanstd(np.asarray(ds), ddof=1)))
        return float(np.mean(sds))

    sigma_pe = 0.0
    if fit_sd > 0:
        lo, hi = 0.0, 0.30
        for _ in range(14):
            mid = 0.5 * (lo + hi)
            if _fit_scatter(mid) < fit_sd:
                lo = mid
            else:
                hi = mid
        sigma_pe = 0.5 * (lo + hi)

    rng = np.random.default_rng(SEED + SEED_OFF["h2h_cover"])
    pe_rng = np.random.default_rng(SEED + SEED_OFF["h2h_cover_pe"])
    hits = {"cluster": 0, "row": 0}
    sds = {"cluster": [], "row": []}
    true_sds, true_means, points = [], [], []
    for s in range(n_check):
        pe_s = pe0 + sigma_pe * float(pe_rng.standard_normal())
        base = SEED + H2H_DGP_BASE + s * 1000
        Fs = frame_of(*gen(base, pe_s, pc0, g0, qa0))
        point = frame_delta(Fs)
        points.append(point)
        fresh = np.asarray([frame_delta(frame_of(*gen(base + 1 + m, pe_s, pc0, g0, qa0)))
                            for m in range(M)], dtype=float)
        fresh = fresh[np.isfinite(fresh)]
        t_cond = float(fresh.mean())
        true_means.append(t_cond)
        true_sds.append(float(fresh.std(ddof=1)))
        # the observed dataset again, so the bootstrap runs on the SAME arrays the point
        # estimate came from (frame_of rebinds a shared template)
        Fs = frame_of(*gen(base, pe_s, pc0, g0, qa0))
        for name, mode in (("cluster", "cluster"), ("row", "row")):
            a = np.asarray(boot_cond_cluster(Fs, B, rng, mode=mode), dtype=float)
            a = a[np.isfinite(a)]
            sds[name].append(float(a.std(ddof=1)))
            if np.percentile(a, 2.5) <= t_cond <= np.percentile(a, 97.5):
                hits[name] += 1
        if verbose and (s + 1) % 25 == 0:
            print(f"  {s+1}/{n_check}  {time.time()-t0:.0f}s", flush=True)

    true_sd = float(np.mean(true_sds))
    legs = {}
    for name in ("cluster", "row"):
        mean_sd = float(np.mean(sds[name]))
        g = binom_gate(hits[name], n_check)
        legs[name] = {
            "resampling_unit": "player cluster" if name == "cluster" else "scored row",
            "role": ("PRIMARY, the registered estimator for this class" if name == "cluster"
                     else "DIAGNOSTIC ONLY, never a gate: it is the clustering violation"),
            "mean_bootstrap_sd": round(mean_sd, 5),
            "true_sd_of_conditional_estimand": round(true_sd, 5),
            "sd_ratio_boot_over_true": round(mean_sd / true_sd, 3),
            "sd_ratio_in_band": bool(SD_BAND[0] <= mean_sd / true_sd <= SD_BAND[1]),
            "gate_two_sided": g,
            "one_sided_gate_as_currently_coded": "PASS" if g["coverage"] >= 0.90 else "FAIL",
        }
    prim = legs["cluster"]["gate_two_sided"]["verdict"]
    out = {
        "gate": "X2 coverage, headtohead_common",
        "verdict": prim,
        "registration": ("POWER_EXTENSION_GATE.md sections 3.3 and 4.2. A class that "
                         "cannot be given an honest clustered coverage check is reported "
                         "UNFLOORED, not floored on the incumbent's registration."),
        "design": {"n_check": n_check, "M_fresh_samples": M, "B": B,
                   "n_rows": match["n_rows"], "n_clusters": match["n_clusters"],
                   "rows_per_cluster": match["rows_per_cluster"],
                   "seed": SEED + SEED_OFF["h2h_cover"],
                   "dataset_stream_base": SEED + H2H_DGP_BASE},
        "dgp_match": match,
        "conditional_estimand": {
            "truth_mean_delta": round(float(np.mean(true_means)), 5),
            "true_sd": round(true_sd, 5),
            "mean_point_delta": round(float(np.nanmean(points)), 5),
            "question": "given this training corpus, is this margin real",
            "fit_component_sd_targeted": round(fit_sd, 5),
            "sigma_pe_calibrated": round(sigma_pe, 5),
            "fit_component_note": (
                "the eFV leg is the only leg that is fitted (the consensus leg is the raw "
                "published grade), so the training corpus is represented by that leg's "
                "loading alone. That is also why POWER_EXTENSION_GATE.md section 1 "
                "pre-registers a SMALLER conditional shrink here than on the pooled cuts."
                if fit_sd > 0 else
                "NO fit component was available (partb_floors not yet in the artifact), so "
                "pe was held at its fitted value across datasets. Reported, not hidden."),
        },
        "legs": legs,
        "clustering_violation_in_coverage_terms": {
            "cluster_coverage": legs["cluster"]["gate_two_sided"]["coverage"],
            "row_iid_coverage": legs["row"]["gate_two_sided"]["coverage"],
            "row_iid_sd_ratio": legs["row"]["sd_ratio_boot_over_true"],
            "reading": ("the row variant's coverage is what a one-row-per-player simulator "
                        "would have called a pass. Publishing it is the check that "
                        "clustering was preserved."),
        },
        "elapsed_s": round(time.time() - t0, 1),
    }
    if verbose:
        for name, v in legs.items():
            gg = v["gate_two_sided"]
            print(f"  {name:<8} sd {v['mean_bootstrap_sd']:.5f} vs true "
                  f"{v['true_sd_of_conditional_estimand']:.5f} "
                  f"(ratio {v['sd_ratio_boot_over_true']}) cov {gg['coverage']:.3f} "
                  f"accept {gg['accept_coverage_band']} -> {gg['verdict']}")
        print("  X2 ->", prim)
    if write:
        merge_artifact({"x2_coverage_h2h": out})
    return out


# ===================================================================== X4 loss vs win
def x4_sign(n_sim: int = 200, B: int = 300, write: bool = True, verbose: bool = True):
    """X4: does the extension resolve LOSSES as readily as WINS.

    Part A could not answer this on real data because E_cond resolved nothing in either
    direction. It is answerable by construction on the clustered simulator: run the same
    generator with the challenger leg BETTER than the baseline and then WORSE, with the
    two true deltas matched in magnitude, and compare fire rates at each estimator's own
    floor. An instrument that fires on wins and not on losses is power laundering.
    """
    t0 = time.time()
    F = cls_headtohead()
    gen, frame_of, params, match, syn_groups = make_dgp_h2h(F, verbose=False)
    pc0, g0, qa0 = params["pc"], params["g"], params["qa"]

    def truth_at(pe, reps=120, base=None):
        # common random numbers again, and 120 reps: the arms are compared at MATCHED
        # |effect|, so the two truths have to be pinned tighter than the effect itself.
        base = (SEED + X4_DGP_BASE - 100000) if base is None else base
        return float(np.nanmean([frame_delta(frame_of(*gen(base + 977 * j, pe, pc0, g0, qa0)))
                                 for j in range(reps)]))

    def _pe_for(target_delta):
        """Solve the eFV loading that puts the TRUE delta at a named value. Both arms are
        defined this way rather than by mirroring a parameter, because the two legs have
        different noise structures (only the consensus leg carries vintage noise) and a
        mirrored parameter would not give a mirrored effect."""
        lo, hi = 0.0, 0.99
        for _ in range(18):
            mid = 0.5 * (lo + hi)
            if truth_at(mid) < target_delta:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    d0 = abs(float(frame_delta(F)))          # the real head-to-head margin, +0.033
    pe_win = _pe_for(d0)
    pe_loss = _pe_for(-d0)
    arms = {}
    for label, pe in (("win", pe_win), ("loss", pe_loss)):
        rng = np.random.default_rng(SEED + SEED_OFF["x4_sign" if label == "win" else "x4_loss"])
        pts, sd_c, sd_r = [], [], []
        for s in range(n_sim):
            Fs = frame_of(*gen(SEED + X4_DGP_BASE + s * 100 + (0 if label == "win" else 50),
                               pe, pc0, g0, qa0))
            pts.append(frame_delta(Fs))
            a = np.asarray(boot_cond_cluster(Fs, B, rng, mode="cluster"), dtype=float)
            sd_c.append(float(a[np.isfinite(a)].std(ddof=1)))
            b = np.asarray(boot_cond_cluster(Fs, B, rng, mode="row"), dtype=float)
            sd_r.append(float(b[np.isfinite(b)].std(ddof=1)))
        pts = np.asarray(pts, dtype=float)
        truth = float(np.nanmean(pts))
        arms[label] = {
            "pe": round(pe, 4), "n_sim": n_sim, "B": B,
            "true_delta": round(truth, 5),
            "mean_floor_cluster": round(float(Z95_ONE * np.mean(sd_c)), 4),
            "fire_rate_cluster": round(float(np.mean(np.abs(pts) >= Z95_ONE * np.asarray(sd_c))), 4),
            "fire_rate_row_DIAGNOSTIC": round(
                float(np.mean(np.abs(pts) >= Z95_ONE * np.asarray(sd_r))), 4),
            "sign_correct_rate": round(float(np.mean(
                (np.abs(pts) >= Z95_ONE * np.asarray(sd_c)) & (np.sign(pts) == np.sign(truth)))), 4),
        }
    fw, fl = arms["win"]["fire_rate_cluster"], arms["loss"]["fire_rate_cluster"]
    # STANDARDIZED EFFECT, added after the first run returned an asymmetric rate.
    # Matching the arms on |true delta| does NOT match them on power: the delta's sd is
    # itself a function of the eFV leg's loading, so the loss arm can end up testing a
    # slightly smaller effect against a slightly larger floor. z_true = |truth| / sd is
    # the quantity a fire rate is actually a function of, and Phi(z_true - 1.645) is the
    # normal-theory rate at this one-sided convention. Reported as a DIAGNOSTIC; the
    # pre-declared band above is not moved to accommodate it.
    diag = {}
    for k, v in arms.items():
        sd = v["mean_floor_cluster"] / Z95_ONE
        z = abs(v["true_delta"]) / sd if sd > 0 else None
        diag[k] = {
            "mean_sd": round(sd, 5),
            "z_true": (round(z, 3) if z else None),
            "normal_theory_fire_rate": (
                round(0.5 * math.erfc(-(z - Z95_ONE) / math.sqrt(2.0)), 4) if z else None),
            "observed_fire_rate": v["fire_rate_cluster"],
        }
    out = {
        "gate": "X4 the extension resolves losses as readily as wins",
        "arms": arms,
        "standardized_effect_DIAGNOSTIC": diag,
        "magnitude_matched": {
            "target_abs_delta": round(d0, 5),
            "target_source": "the real head-to-head margin on today's frame",
            "win_true_delta": arms["win"]["true_delta"],
            "loss_true_delta": arms["loss"]["true_delta"],
            "abs_gap": round(abs(abs(arms["win"]["true_delta"])
                                 - abs(arms["loss"]["true_delta"])), 5),
            "method": ("both arms are solved by bisection to put the TRUE delta at "
                       "+/- the real margin, so they are compared at equal |effect| "
                       "rather than at mirrored parameters"),
        },
        "fire_rate_ratio_loss_over_win": (round(fl / fw, 3) if fw > 0 else None),
        "verdict": ("PASS" if (fw > 0 and 0.80 <= fl / fw <= 1.25) else
                    ("FAIL: asymmetric" if fw > 0 else "UNMEASURABLE")),
        "criterion": ("PASS when the loss arm's fire rate is within 0.80x-1.25x of the win "
                      "arm's at matched |effect|. The band is stated here before the "
                      "numbers are read and is wide because n_sim = %d gives a binomial "
                      "se of about 0.035 at a rate of 0.5." % n_sim),
        "verdict_registered_clause": (
            "PASS" if (fw > 0 and fl > 0) else "REFUSED"),
        "registered_clause": (
            "POWER_EXTENSION_GATE.md section 4.4 as written: the extension is REFUSED if "
            "it resolves only wins. The 0.80-1.25 band above is this lab's own tighter "
            "operationalization of that clause, and it is NOT relaxed after the fact."),
        "real_data_leg": "see partb_floors: which cells resolve, and in which direction",
        "elapsed_s": round(time.time() - t0, 1),
    }
    if verbose:
        print("=== X4 SIGN SYMMETRY ===")
        for k, v in arms.items():
            print(f"  {k:<5} true {v['true_delta']:+.5f} floor {v['mean_floor_cluster']} "
                  f"fire {v['fire_rate_cluster']} (row diag {v['fire_rate_row_DIAGNOSTIC']})")
        print("  ->", out["verdict"])
    if write:
        merge_artifact({"x4_sign_symmetry": out})
    return out


# ===================================================================== X3 detection
def detect_classes(B: int = 600, write: bool = True, verbose: bool = True):
    """X3: does each new class detect the known-real hitter `fv` effect wherever E_refit
    does. An instrument that cannot see a known effect is not tighter, it is broken.

    The contrast is the shipped spec against the spec MINUS `fv`, rendered in each
    class's own frame geometry:
      headtohead   the eFV leg refit without `fv`, scored against `war` on the common
                   set, CLUSTER resampled. This is the only new geometry in the family.
      block_rho    the same contrast under the block instrument.
      feature_add  IS this contrast; its floors block already carries it.
      lambda_shift shares pooled_rho's frame geometry exactly (same rows, same weights,
                   same target), so its X3 is the fv contrast evaluated on the
                   lambda-shifted blend leg. Reported as a shared-geometry check, NOT as
                   an independent test of the resampler.
    """
    t0 = time.time()
    cells = {}
    # --- head-to-head, the clustered geometry
    if verbose:
        print(f"=== X3 1/3: headtohead fv-drop (B={B}) ===", flush=True)
    Fh = cls_headtohead_featdrop("fv", "hit")
    rng = np.random.default_rng(SEED + SEED_OFF["x3_detect"])
    pt = frame_delta(Fh)
    ref = boot_refit_h2h(Fh["_pool"], Fh["_pool_drop"], B, rng)
    con = boot_cond_cluster(Fh, B, rng, mode="cluster")
    row = floor_cell("x3.headtohead.fv_drop", Fh, ref, con, "player cluster", point=pt)
    row["DIAGNOSTIC_row_iid_NOT_A_GATE"] = summarize(
        boot_cond_cluster(Fh, B, rng, mode="row"), pt)
    cells["headtohead"] = row
    # --- block instrument
    #
    # POOL CHOICE, and it is load-bearing. The known-real `fv` effect is located on the
    # DEBUTED pool: EFV_GATE_STANDARD.md section 6 puts it there, and part A's `detect`
    # measured it there (debuted.ridge +0.05721 detects under all three estimators, while
    # every full-pool arm misses under all three). Running X3 on the full pool would score
    # MISSES everywhere and pass this gate vacuously. The debuted pools are also the
    # registered block instrument, n 1,645.
    if verbose:
        print(f"=== X3 2/3: block_rho fv-drop, debuted pools (B={B}) ===", flush=True)
    rng = np.random.default_rng(SEED + SEED_OFF["x3_block"])
    Fb = cls_feature_add("hit", "debuted", "fv", leg="ridge", instrument="block")
    ref = Fb["_refit_multi"](B, rng, ("ridge",))["ridge"]
    con = boot_cond_cluster(Fb, B, rng, mode="row")
    cells["block_rho"] = floor_cell("x3.block_rho.fv_drop", Fb, ref, con, "scored row")
    # --- lambda-shifted geometry
    if verbose:
        print(f"=== X3 3/3: lambda-shifted fv-drop, debuted (B={B}) ===", flush=True)
    rng = np.random.default_rng(SEED + SEED_OFF["x3_lambda"])
    lam2 = round(load_pool("hit", "debuted")["lam"] - 0.19, 10)
    Fl = cls_feature_add("hit", "debuted", "fv", leg="ridge", instrument="pooled", lam=lam2)
    ref = Fl["_refit_multi"](B, rng, ("ridge",))["ridge"]
    con = boot_cond_cluster(Fl, B, rng, mode="row")
    cells["lambda_shift_geometry"] = floor_cell(
        "x3.lambda_shifted.fv_drop", Fl, ref, con, "scored row",
        extra={"lambda_used": lam2,
               "note": "shares pooled_rho's frame geometry; not an independent resampler"})
    ok = all(bool(c["E_cond"].get("resolvable")) >= bool((c["E_refit"] or {}).get("resolvable"))
             for c in cells.values())
    out = {
        "gate": "X3 detection of the known-real hitter `fv` effect",
        "B": int(B), "seed": SEED + SEED_OFF["x3_detect"],
        "cells": cells,
        "verdict": ("PASS" if ok else
                    "FAIL: a class misses where E_refit detects"),
        "criterion": ("each class must DETECT wherever E_refit detects. A class that "
                      "detects where E_refit does not is not a failure of this gate, but "
                      "it is reported."),
        "elapsed_s": round(time.time() - t0, 1),
    }
    if verbose:
        for k, c in cells.items():
            print(f"  {k:<22} point {c['point_delta']:+.5f} refit "
                  f"{'DETECTS' if (c['E_refit'] or {}).get('resolvable') else 'MISSES'}"
                  f"({c['MDE95']})  cond "
                  f"{'DETECTS' if c['E_cond'].get('resolvable') else 'MISSES'}"
                  f"({c['MDE95_COND']})")
        print("  X3 ->", out["verdict"])
    if write:
        merge_artifact({"x3_detection_classes": out})
    return out


# ============================================ B-L2: TOST, decidability, REML, sign test
#
# WHY THIS SECTION EXISTS. Every cell in this program resolves two ways today, RESOLVED
# or NULL, and a NULL is the answer to a question nobody asked: it says the data cannot
# tell a zero effect from the observed one. The owner registered an equivalence margin
# of 0.02 Spearman, which converts a large share of those nulls into the OTHER positive
# answer: the effect is smaller than anything worth shipping. This costs zero power, it
# is a re-reading of intervals that already exist.
def tost_cell(delta, sd, margin=TOST_DELTA, alpha=0.05):
    """Three-way adjudication at a registered equivalence margin.

    The interval is the SAME one the floors use: delta +/- 1.645*sd, i.e. one-sided
    alpha 0.05 on each side, which is the two-one-sided-tests interval at this alpha.
    Using the floor's own z keeps every verdict on one scale.

      SHIP           interval entirely above +margin
      RESOLVED_LOSS  interval entirely below -margin (the mirror; a large adverse effect
                     is not UNDECIDED and must not be reported as one)
      RULED_OUT      interval entirely inside +/- margin: the effect is real-or-not but
                     it is smaller than the margin either way
      UNDECIDED      neither
    """
    if not sd or sd <= 0:
        return {"verdict": "UNMEASURABLE"}
    d, s = float(delta), float(sd)
    half = Z95_ONE * s
    lo, hi = d - half, d + half
    p_below = 0.5 * math.erfc(((margin - d) / s) / math.sqrt(2.0))     # H0: delta >= margin
    p_above = 0.5 * math.erfc(((d + margin) / s) / math.sqrt(2.0))     # H0: delta <= -margin
    if lo > margin:
        v = "SHIP"
    elif hi < -margin:
        v = "RESOLVED_LOSS"
    elif lo > -margin and hi < margin:
        v = "RULED_OUT"
    else:
        v = "UNDECIDED"
    return {"verdict": v, "margin": margin, "delta": round(d, 5), "sd": round(s, 5),
            "ci90": [round(lo, 5), round(hi, 5)],
            "p_tost": round(max(p_below, p_above), 5),
            "equivalence_established": bool(v == "RULED_OUT")}


def decidability(delta, sd_cond, sd_refit, n_rows, accrual_rows_per_year,
                 today_year=2026):
    """How much more data would decide this cell, converted to a DATE.

    Under E_cond the fits are held, so the whole sd is scored-sample variance and it
    shrinks as 1/sqrt(n): the required multiplier is (floor/|delta|)^2.

    Under E_refit part of the variance is the refit itself and does NOT shrink with test
    n. sqrt(sd_refit^2 - sd_cond^2) is that component (decomp() checked the additivity
    this leans on: reconstruction 0.906x of shipped). If |delta| is below 1.645 times it,
    the cell is PERMANENTLY UNDECIDABLE under E_refit at any n, and the honest thing is
    to retire it rather than re-test it every cycle.
    """
    out = {"n_rows": int(n_rows), "accrual_rows_per_year": round(accrual_rows_per_year, 1)}
    d = abs(float(delta))
    if sd_cond and d > 0:
        floor = Z95_ONE * float(sd_cond)
        m = (floor / d) ** 2
        yrs = (m - 1.0) * n_rows / accrual_rows_per_year if accrual_rows_per_year > 0 else None
        out["E_cond"] = {
            "n_multiplier_required": round(m, 2),
            "extra_rows_required": int(round(max(0.0, (m - 1.0) * n_rows))),
            "years_at_current_accrual": (round(yrs, 1) if yrs is not None else None),
            "decidable_by_year": (int(round(today_year + yrs)) if yrs is not None else None),
            "already_resolved": bool(m <= 1.0),
        }
    if sd_cond and sd_refit and float(sd_refit) > float(sd_cond):
        asym = Z95_ONE * math.sqrt(float(sd_refit) ** 2 - float(sd_cond) ** 2)
        out["E_refit"] = {
            "floor_asymptote_infinite_test_n": round(asym, 4),
            "permanently_undecidable": bool(d < asym),
            "reading": ("more cohorts cannot close this cell under E_refit: the refit "
                        "component of the floor does not shrink with test n"),
        }
    cond = out.get("E_cond") or {}
    ref = out.get("E_refit") or {}
    yr = cond.get("decidable_by_year")
    if ref.get("permanently_undecidable") and not cond.get("already_resolved"):
        out["triage"] = "RETIRE under E_refit; E_cond only, by %s" % (yr or "never")
    elif yr is None:
        out["triage"] = "UNKNOWN accrual"
    elif yr > 2100:
        out["triage"] = "RETIRE: not decidable this century"
    elif cond.get("already_resolved"):
        out["triage"] = "DECIDED at current n"
    else:
        out["triage"] = "RE-TEST at %d" % yr
    return out


def _reml_tau2(y, v, iters=200, tol=1e-12):
    """REML between-fold variance for a random-effects meta-analysis.

    Iteration: tau2 <- [ sum w^2 ((y-theta)^2 - v) / sum w^2 ] + 1 / sum w, with
    w = 1/(v + tau2), clamped at zero. DerSimonian-Laird is computed alongside for
    reference ONLY: it is biased low at k = 11 and this program does not ship it.
    """
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    k = len(y)
    tau2 = max(0.0, float(y.var(ddof=1) - v.mean()))
    for _ in range(iters):
        w = 1.0 / (v + tau2)
        th = float((w * y).sum() / w.sum())
        num = float((w ** 2 * ((y - th) ** 2 - v)).sum())
        new = max(0.0, num / float((w ** 2).sum()) + 1.0 / float(w.sum()))
        if abs(new - tau2) < tol:
            tau2 = new
            break
        tau2 = new
    # DerSimonian-Laird, for the comparison line only
    wf = 1.0 / v
    thf = float((wf * y).sum() / wf.sum())
    Q = float((wf * (y - thf) ** 2).sum())
    c = float(wf.sum() - (wf ** 2).sum() / wf.sum())
    dl = max(0.0, (Q - (k - 1)) / c) if c > 0 else 0.0
    return tau2, dl, Q


def reml_hksj(y, v, label=""):
    """Random-effects pooled delta with the Hartung-Knapp-Sidik-Jonkman adjustment.

    ADOPTED FOR VALIDITY, NOT POWER. It widens the interval, by swapping the normal
    quantile for t_(k-1) and rescaling the variance by the observed dispersion. At k = 11
    that is z 1.960 -> t_10 2.228 before the rescale. I-squared is deliberately NOT
    reported: at this per-fold n it sits near 0.99 mechanically and would be read as a
    finding.
    """
    from scipy.stats import t as _t
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    k = len(y)
    tau2, dl, Q = _reml_tau2(y, v)
    w = 1.0 / (v + tau2)
    th = float((w * y).sum() / w.sum())
    se_re = math.sqrt(1.0 / float(w.sum()))
    q_hk = float((w * (y - th) ** 2).sum()) / (k - 1)
    se_hk = math.sqrt(q_hk / float(w.sum()))
    tq = float(_t.ppf(0.975, k - 1))
    return {
        "label": label, "k_folds": k,
        "tau2_reml": round(tau2, 8),
        "tau2_dersimonian_laird_DO_NOT_SHIP": round(dl, 8),
        "Q": round(Q, 3),
        "pooled_delta": round(th, 5),
        "se_random_effects": round(se_re, 5),
        "se_hksj": round(se_hk, 5),
        "hksj_widening_ratio": round((se_hk * tq) / (se_re * Z95_TWO), 3),
        "t_quantile_975": round(tq, 4),
        "z_quantile_975": Z95_TWO,
        "ci95_hksj": [round(th - tq * se_hk, 5), round(th + tq * se_hk, 5)],
        "ci95_random_effects_normal_NOT_SHIPPED": [round(th - Z95_TWO * se_re, 5),
                                                   round(th + Z95_TWO * se_re, 5)],
        "i_squared": "SUPPRESSED: near 0.99 mechanically at this per-fold n",
        "hksj_q": round(q_hk, 4),
    }


def meta_regress_logn(y, v, n_train, n_train_deployed, label=""):
    """Meta-regression of the per-fold delta on log(n_train).

    THE HIGHEST-VALUE VARIANT, because the deployed model trains on ALL cohorts and is
    represented by NO fold: every fold in the chain trains on a strict prefix. If the
    delta improves with training size, the folds systematically understate the deployed
    model and the pooled estimate is the wrong summary.

    tau2 by Mandel-Paule (solve sum w e^2 = k - p), then the Knapp-Hartung variance
    inflation and a t_(k-p) interval, which is the meta-regression analogue of HKSJ.
    """
    from scipy.stats import t as _t
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    x = np.log(np.asarray(n_train, dtype=float))
    k = len(y)
    p = 2

    def _fit(tau2):
        w = 1.0 / (v + tau2)
        X = np.column_stack([np.ones(k), x])
        WX = X * w[:, None]
        A = WX.T @ X
        b = np.linalg.solve(A, WX.T @ y)
        e = y - X @ b
        return b, e, w, np.linalg.inv(A), X

    lo, hi = 0.0, max(1e-8, float(y.var(ddof=1)) * 20)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        _b, e, w, _iA, _X = _fit(mid)
        if float((w * e ** 2).sum()) > (k - p):
            lo = mid
        else:
            hi = mid
    tau2 = 0.5 * (lo + hi)
    b, e, w, iA, X = _fit(tau2)
    disp = float((w * e ** 2).sum()) / (k - p)          # Knapp-Hartung inflation
    cov = iA * disp
    tq = float(_t.ppf(0.975, k - p))
    x0 = np.array([1.0, math.log(float(n_train_deployed))])
    pred = float(x0 @ b)
    se_pred = math.sqrt(float(x0 @ cov @ x0))
    return {
        "label": label, "k_folds": k, "tau2_mandel_paule": round(tau2, 8),
        "intercept": round(float(b[0]), 5),
        "slope_per_log_n_train": round(float(b[1]), 5),
        "slope_se": round(math.sqrt(float(cov[1, 1])), 5),
        "slope_ci95_knapp_hartung": [round(float(b[1]) - tq * math.sqrt(float(cov[1, 1])), 5),
                                     round(float(b[1]) + tq * math.sqrt(float(cov[1, 1])), 5)],
        "slope_resolves": bool(abs(float(b[1])) > tq * math.sqrt(float(cov[1, 1]))),
        "n_train_range": [int(min(n_train)), int(max(n_train))],
        "n_train_deployed": int(n_train_deployed),
        "predicted_delta_at_deployed_n": round(pred, 5),
        "predicted_ci95": [round(pred - tq * se_pred, 5), round(pred + tq * se_pred, 5)],
        "extrapolation_warning": ("the deployed n_train is OUTSIDE the fold range, so this "
                                  "is an extrapolation and its interval is the honest "
                                  "width of that extrapolation, not a measurement"),
    }


def sign_enumeration(y, v=None):
    """EXHAUSTIVE sign-flip test over the folds.

    With 11 forward-chained folds there are 2^11 = 2,048 sign vectors, so the
    randomization distribution is enumerated COMPLETELY. The p-value is exact: no Monte
    Carlo error, no seed, nothing to reproduce. Null: each fold's delta is symmetric
    about zero.
    """
    y = np.asarray(y, dtype=float)
    k = len(y)
    if k > 22:
        raise ValueError("2^k enumeration refused above k = 22")
    w = np.ones(k) if v is None else 1.0 / np.asarray(v, dtype=float)
    signs = np.array([[1.0 if (i >> j) & 1 else -1.0 for j in range(k)]
                      for i in range(2 ** k)])
    stat_w = (signs * (w * y)).sum(axis=1) / w.sum()
    obs_w = float((w * y).sum() / w.sum())
    stat_u = (signs * y).sum(axis=1) / k
    obs_u = float(y.mean())
    return {
        "k_folds": k, "n_sign_vectors": int(2 ** k), "exhaustive": True,
        "observed_inverse_variance_weighted_mean": round(obs_w, 5),
        "p_two_sided_inverse_variance": round(float((np.abs(stat_w) >= abs(obs_w) - 1e-15).mean()), 5),
        "observed_unweighted_mean": round(obs_u, 5),
        "p_two_sided_unweighted": round(float((np.abs(stat_u) >= abs(obs_u) - 1e-15).mean()), 5),
        "note": ("exact by enumeration, not simulated. The two weightings are reported "
                 "because the inverse-variance weights are themselves estimated."),
    }


def fold_series(B: int = 500, verbose: bool = True):
    """The per-fold delta series the eval does not emit today, for every registered cut
    plus the head-to-head class.

    Per fold: the delta on that fold's scored rows with the fits held (E_cond geometry),
    its own bootstrap variance, its test n and its TRAIN n. The train n is what the
    meta-regression needs and it is the reason the series is worth building: the deployed
    model trains on every cohort and no fold does.
    """
    rng = np.random.default_rng(SEED + SEED_OFF["fold_series"])
    out = {}
    for key, side, pool, _rank in CUTS:
        D = load_pool(side, pool)
        r = chain_full(D, keep_fits=True)
        rows = []
        sub = {"cons": r["cons"], "blend": r["blend"], "y": r["y"], "w": r["w"]}
        for yr in np.unique(r["yr"]):
            m = np.flatnonzero(r["yr"] == yr)
            d = delta_of(sub, m)
            draws = [delta_of(sub, m[rng.integers(0, len(m), len(m))]) for _ in range(B)]
            a = np.asarray(draws, dtype=float)
            a = a[np.isfinite(a)]
            rows.append({"fold": int(yr), "n_test": int(len(m)),
                         "n_train": int((D["dy"] < yr).sum()),
                         "delta": (round(float(d), 5) if np.isfinite(d) else None),
                         "sd": (round(float(a.std(ddof=1)), 5) if len(a) > 2 else None)})
        out[key] = {"folds": rows, "B_within_fold": int(B), "n_train_deployed": int(D["n"])}
        if verbose:
            print(f"  {key}: " + " ".join(
                f"{x['fold']}:" + ("%+.4f" % x["delta"] if x["delta"] is not None else "drop")
                for x in rows))
    # head-to-head, clustered inside the fold
    F = cls_headtohead()
    P = F["_pool"]
    base, dy = 0, {}
    for s in SIDES:
        for i, d in enumerate(P[s]["dy"]):
            dy[base + i] = int(d)
        base += P[s]["n"]
    yr_row = np.array([dy[int(c)] for c in F["clu"]], dtype=int)
    groups = _frame_groups(F, "clu")
    rows = []
    for yr in np.unique(yr_row):
        gidx = [g for g in groups if yr_row[g[0]] == yr]
        if not gidx:
            continue
        m = np.concatenate(gidx)
        d = frame_delta(F, m)
        draws = []
        for _ in range(B):
            pick = rng.integers(0, len(gidx), len(gidx))
            draws.append(frame_delta(F, np.concatenate([gidx[i] for i in pick])))
        a = np.asarray(draws, dtype=float)
        a = a[np.isfinite(a)]
        rows.append({"fold": int(yr), "n_test": int(len(m)), "n_clusters": len(gidx),
                     "n_train": int(sum(int((P[s]["dy"] < yr).sum()) for s in SIDES)),
                     "delta": (round(float(d), 5) if np.isfinite(d) else None),
                     "sd": (round(float(a.std(ddof=1)), 5) if len(a) > 2 else None)})
    out["headtohead_common"] = {
        "folds": rows, "B_within_fold": int(B),
        "n_train_deployed": int(sum(P[s]["n"] for s in SIDES)),
        "unit": "player clusters resampled inside the fold",
    }
    if verbose:
        print("  headtohead: " + " ".join(
            f"{x['fold']}:" + ("%+.4f" % x["delta"] if x["delta"] is not None else "drop")
            for x in rows))
    return out


def adjudicate(B_fold: int = 500, write: bool = True, verbose: bool = True):
    """B-L2: read every floored cell back out of the artifact and adjudicate it three
    ways at the registered margin, then triage what is decidable and when.

    Runs AFTER partb_floors, from the stored floors, so the adjudication cannot move a
    floor: it re-reads intervals that already exist.
    """
    t0 = time.time()
    art = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else {}
    # CONTROLS ARE NOT CLAIMS. A multiplicity family is the set of cells a decision could
    # be made on; the feature-dependence control and the X3 detection cells are
    # instrument checks, so they are adjudicated and reported but kept OUT of the family.
    not_a_claim = ("feature_add.tool_speed.pooled.ridge",)
    cells = []
    for key, row in ((art.get("partb_floors") or {}).get("cells") or {}).items():
        cells.append({"key": key,
                      "family": ("control" if key in not_a_claim else "partb_2026_08_09"),
                      "delta": row["point_delta"],
                      "sd_cond": row["E_cond"].get("sd"),
                      "sd_refit": (row.get("E_refit") or {}).get("sd"),
                      "n_rows": row["n_rows"]})
    registered = {}
    for key, row in ((art.get("verdict") or {}).items()):
        if not isinstance(row, dict) or "cond_iid" not in row:
            continue
        registered[key] = {
            "basis": "part A registration, 2026-08-08 pools",
            "delta": row["cond_iid"]["point_delta"],
            "MDE95_COND": row["cond_iid"]["MDE95"], "MDE95": row["refit"]["MDE95"],
            "tost_E_cond": tost_cell(row["cond_iid"]["point_delta"], row["cond_iid"]["sd"]),
        }
    fs = fold_series(B_fold, verbose=verbose)
    accrual = {}
    for k, v in fs.items():
        ns = [f["n_test"] for f in v["folds"]]
        accrual[k] = float(np.median(ns)) if ns else 0.0
    default_accrual = float(np.median([a for a in accrual.values() if a > 0]))

    rows = {}
    for c in cells:
        if not c["sd_cond"]:
            rows[c["key"]] = {"family": c["family"], "verdict": "UNMEASURABLE"}
            continue
        acc = accrual.get(c["key"].replace("pooled_rho.", ""), default_accrual)
        rows[c["key"]] = {
            "family": c["family"],
            "delta": round(float(c["delta"]), 5),
            "MDE95_COND": round(Z95_ONE * float(c["sd_cond"]), 4),
            "MDE95": (round(Z95_ONE * float(c["sd_refit"]), 4) if c["sd_refit"] else None),
            "tost_E_cond": tost_cell(c["delta"], c["sd_cond"]),
            "tost_E_refit": (tost_cell(c["delta"], c["sd_refit"]) if c["sd_refit"] else None),
            "decidability": decidability(c["delta"], c["sd_cond"], c["sd_refit"],
                                         c["n_rows"], acc),
        }
    fam = [c for c in cells if c["family"] != "control" and c["sd_cond"]]
    holm = holm_family([{"key": c["key"], "delta": c["delta"], "sd": c["sd_cond"]}
                        for c in fam], alpha=0.05)
    meta = {}
    for k, v in fs.items():
        keep = [f for f in v["folds"]
                if f["delta"] is not None and f["sd"] is not None and f["sd"] > 0]
        if len(keep) < 4:
            continue
        y = [f["delta"] for f in keep]
        vv = [float(f["sd"]) ** 2 for f in keep]
        meta[k] = {
            "series": v["folds"],
            "folds_used": len(keep), "folds_dropped": len(v["folds"]) - len(keep),
            "reml_hksj": reml_hksj(y, vv, label=k),
            "meta_regression_log_n_train": meta_regress_logn(
                y, vv, [f["n_train"] for f in keep], v["n_train_deployed"], label=k),
            "sign_enumeration": sign_enumeration(y, vv),
        }
    tally = {}
    for k, r in rows.items():
        v = (r.get("tost_E_cond") or {}).get("verdict", "UNMEASURABLE")
        if rows[k]["family"] == "control":
            continue
        tally[v] = tally.get(v, 0) + 1
    out = {
        "produced_by": "tools/efv_power_lab.py adjudicate",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "equivalence_margin": TOST_DELTA,
        "margin_source": "owner registration 2026-08-08, 0.02 Spearman",
        "interval_convention": ("delta +/- 1.645*sd, the same one-sided alpha 0.05 the "
                                "floors use, which is the TOST interval at that alpha"),
        "cells": rows,
        "registered_cells_2026_08_08_for_reference": registered,
        "tally_E_cond": tally,
        "family_note": ("the Holm family is the cells a decision could be made on. The "
                        "feature-dependence control is adjudicated but excluded, because "
                        "padding a family with instrument checks makes every real cell "
                        "harder to reject for no reason."),
        "holm_family_E_cond": holm,
        "per_fold": meta,
        "accrual_rows_per_year": {k: round(v, 1) for k, v in accrual.items()},
        "accrual_note": ("median per-fold test n, i.e. one new decision-year cohort. The "
                         "date columns assume that rate continues and assume nothing about "
                         "label maturation, which is a second and slower clock."),
        "elapsed_s": round(time.time() - t0, 1),
    }
    if verbose:
        print("=== ADJUDICATION at margin", TOST_DELTA, "===")
        for k, r in rows.items():
            if "tost_E_cond" not in r:
                print(f"  {k:<34} UNMEASURABLE")
                continue
            print(f"  {k:<34} d {r['delta']:+.5f}  cond {r['tost_E_cond']['verdict']:<13} "
                  f"ci90 {r['tost_E_cond']['ci90']}  {r['decidability']['triage']}")
        print("  tally", tally)
    if write:
        merge_artifact({"adjudication_bl2": out})
    return out


# ===================================================================== driver
def merge_artifact(block: dict, path=None):
    """READ, MODIFY, WRITE. run_all writes the WHOLE artifact in one shot; a part-B
    sub-command that did the same would erase the part-A registration (`verdict`,
    `coverage`, `detection_fv`, `power`), which is the incident
    POWER_EXTENSION_GATE.md section 3.7 pre-registers against. Existing top-level keys
    are preserved in their original order; only the keys in `block` are replaced.
    """
    p = OUT_PATH if path is None else path
    cur = {}
    if p.exists():
        cur = json.loads(p.read_text(encoding="utf-8"))
    for k, v in block.items():
        cur[k] = v
    p.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    print(f"merged {sorted(block)} into {p}")
    return cur
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
    elif cmd == "verdict_general":
        verdict_general(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "parity_x1":
        parity_x1(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "h2hshape":
        h2hshape(int(a[1]) if len(a) > 1 else 2000)
    elif cmd == "floors":
        partb_floors(int(a[1]) if len(a) > 1 else 1000,
                     int(a[2]) if len(a) > 2 else 2000)
    elif cmd == "x2cover":
        coverage_h2h(int(a[1]) if len(a) > 1 else N_CHECK)
    elif cmd == "x3detect":
        detect_classes(int(a[1]) if len(a) > 1 else 600)
    elif cmd == "x4sign":
        x4_sign(int(a[1]) if len(a) > 1 else 200)
    elif cmd == "adjudicate":
        adjudicate(int(a[1]) if len(a) > 1 else 500)
    elif cmd == "partb":
        # ONE writer at a time: every sub-command read-modify-writes the same artifact,
        # so they run sequentially in this process rather than as parallel jobs.
        partb_floors(int(a[1]) if len(a) > 1 else 1000,
                     int(a[2]) if len(a) > 2 else 2000)
        detect_classes(int(a[3]) if len(a) > 3 else 600)
        coverage_h2h()
        x4_sign()
        adjudicate()
    elif cmd == "all":
        run_all(int(a[1]) if len(a) > 1 else 2000)
    else:
        print(__doc__ or "unknown mode")


if __name__ == "__main__":
    main()
