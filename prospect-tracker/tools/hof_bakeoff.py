#!/usr/bin/env python
"""The public benchmark bake-off: what bar does a Hall of Fame model have to clear?

Clauses frozen first in docs/HOF_BAKEOFF_GATE.md. This module REFUSES to run without
that document, because a battery that can run before its own gate is written is not
gated by it.

WHAT IT SETTLES. Every later Hall of Fame model needs a bar, and the bar has to come
from the public work rather than from nothing. This scores Baseball-Reference's own
HoF Monitor and HoF Standards against our WAR shelf on the same rows, twice: raw for
discrimination, and Platt-calibrated per fold for calibration.

The honest expectation is that we lose. HoF Monitor is built from batting titles, MVP
shares, All-Star selections and postseason play, none of which is in our feature set.

FOUR THINGS THAT LOOK REASONABLE AND ARE WRONG, each guarded here:

  1. READING THE SHELF WITHOUT COLLAPSING IT. The file ships one row per ballot
     APPEARANCE, 4,278 rows over 1,322 players. The metric values are constant per
     player, so the collapse is lossless, and skipping it silently reweights every
     player by how many years he lingered on the ballot.
  2. SELECTING RESOLVED ROWS BY TRUTHINESS. The label columns are float64 and a
     censored player carries NaN. `bool(nan)` is True, so `if label:` admits every
     censored player as an inductee.
  3. IMPUTING A MISSING PUBLIC COLUMN. A zero HoF Monitor for Roberto Clemente
     guarantees a misranking, and a NaN is worse: numpy sorts NaN last, so a positive
     with a missing score is awarded the TOP rank.
  4. ASSERTING POOLED POST-PLATT AUC EQUALS POOLED RAW AUC. Platt is monotone WITHIN a
     fold. A pooled vector built from many fold-specific maps is not one monotone map,
     so a correct implementation fails that check. The per-fold version is the real
     guard; the pooled shift is published as a measured quantity.

Deterministic and offline.  python tools/hof_bakeoff.py [--fast] [--label bbwaa]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hof_data as hd                                        # noqa: E402
from source_backtest import (                                # noqa: E402
    _CLAIM_MIN_ROWS as MIN_ROWS,
    _CLAIM_MIN_CLUSTERS as MIN_CLUSTERS,
    _Z95, _auc_np, _ranks_np, _numpy, _cluster_layout, _cluster_draw,
)
sys.path.insert(0, str(ROOT / "tools"))
from efv_power_lab import holm_family                        # noqa: E402

GATE_DOC = ROOT / "docs" / "HOF_BAKEOFF_GATE.md"
BENCH = ROOT / "data" / "hof_public_benchmarks.json"
OUT = ROOT / "data" / "hof_bakeoff_eval.json"

SEED = 20260906
B_BOOT = 2000
BURN_IN_MIN_ROWS = 150
BURN_IN_MIN_PER_CLASS = 25
FOLD_WIDTH_YEARS = 5
ECE_BINS = 10
LOGIT_CLIP = 30.0
RIDGE = 1e-3

REFERENCE_ARM = "JAWS"

PUBLIC_ARMS = ("hof_monitor", "hof_standard", "WAR_career", "WAR_peak7", "JAWS")
INHOUSE_ARMS = ("career_war", "war7", "jaws", "career_waa", "waa_pos", "ink")
ALL_ARMS = PUBLIC_ARMS + INHOUSE_ARMS

DISTINCT_METRICS = ("hof_monitor", "hof_standard", "career_war", "war7",
                    "jaws", "career_waa", "waa_pos", "ink")
"""EIGHT, NOT ELEVEN. JAWS/jaws, WAR_career/career_war and WAR_peak7/war7 are the
scraped and in-house versions of the same three quantities. Counting them separately
overstates the family, makes Holm needlessly conservative on the comparisons that
matter, and pollutes the argmax candidate set. The pairs ship as a reproduction check
instead."""

REJECTED_ARMS = {
    "JAWS_pos": (
        "LABEL-DERIVED. It is the mean JAWS of the Hall of Famers at that position as "
        "of the scrape, so it is computed FROM the outcome and includes players "
        "sitting in our own test folds. It ships as a STRING, which makes it look "
        "like a harmless identifier, and JAWS minus JAWS_pos is the most "
        "natural-looking normalization available. Admissible as a position "
        "identifier, NEVER as a score and NEVER as a normalizer."),
    "bref_hof_marker_as_of_scrape": (
        "A PERFECT LEAK, and not what its name suggests: it is a flag on LOSING rows "
        "only. Never join, feature or cross-check on it."),
    "black_ink": (
        "DOES NOT EXIST in this repo. hof_data.war_ink is an in-house metric ranking "
        "ONE thing, WAR, hitters and pitchers in one pool per league-season, and it "
        "ships as the in-house arm `ink`. Never presented as the public Black Ink."),
    "gray_ink": "DOES NOT EXIST in this repo.",
    "hall_rating": "DOES NOT EXIST in this repo. Prose only.",
    "wwar": "DOES NOT EXIST in this repo. Prose only.",
    "keltner": "DOES NOT EXIST in this repo.",
}


def frozen_at() -> str:
    """The gate doc's freeze line, or a refusal. A battery that can run without its
    own clauses is not gated by them."""
    if not GATE_DOC.exists():
        try:
            shown = GATE_DOC.relative_to(ROOT)
        except ValueError:
            # relative_to RAISES on a path outside the repo, so the refusal path
            # itself crashed with a confusing ValueError under a monkeypatched
            # doc. A guard that fails differently depending on where the missing
            # file is not-located is not a guard.
            shown = GATE_DOC
        raise RuntimeError(
            f"{shown} does not exist. The clauses are frozen "
            "before the battery runs, not after it, and this refusal is what makes "
            "that true rather than customary.")
    for line in GATE_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("Frozen "):
            return line.strip()
    raise RuntimeError("the gate doc carries no freeze line")


# --------------------------------------------------------------------------
# frame
# --------------------------------------------------------------------------

def collapse_shelf(rows) -> dict:
    """4,278 ballot-appearance rows to {player_id: metrics} over 1,322 players.

    LOSSLESS, and measured rather than assumed: 0 of 1,322 players carry a metric
    that varies across their appearances. The check runs every time, because a
    future scrape that broke it would otherwise reweight every player by how many
    years he lingered on the ballot.
    """
    by: dict = {}
    varied = []
    for r in rows:
        pid = r.get("player_id")
        if not pid:
            continue
        keep = {m: r.get(m) for m in PUBLIC_ARMS}
        prev = by.get(pid)
        if prev is None:
            by[pid] = keep
        elif prev != keep and pid not in varied:
            varied.append(pid)
    if varied:
        raise RuntimeError(
            f"{len(varied)} players carry shelf metrics that vary across ballot "
            f"appearances (e.g. {varied[:5]}), so collapsing is no longer lossless "
            "and the unit of observation has to be re-decided before anything is "
            "scored")
    return by


def bakeoff_frame(label: str, *, offline: bool = True, as_of_year: int = 2026):
    """One row per PLAYER, resolved label only, joined to the collapsed shelf."""
    col = f"label_{label}"
    rf = hd.resolution_frame(offline=offline, as_of_year=as_of_year)
    # `.notna()` then `== 1.0`. NEVER truthiness: the column is float64, a censored
    # row is NaN, and bool(nan) is True.
    res = rf[rf[col].notna()].copy()
    res["y"] = (res[col] == 1.0)
    shelf = collapse_shelf(json.loads(BENCH.read_text(encoding="utf-8"))["rows"])
    for m in PUBLIC_ARMS:
        res[m] = [(shelf.get(p) or {}).get(m) for p in res["player_ID"]]
    res["_has_shelf"] = [p in shelf for p in res["player_ID"]]
    return res


def common_support(frame, label: str, arms=ALL_ARMS):
    """(intersection, drop accounting). Public columns are NEVER imputed."""
    import pandas as pd                                       # noqa: F401
    ok = frame.copy()
    miss = {}
    keep = None
    for a in arms:
        good = ok[a].notna()
        miss[a] = int((~good).sum())
        keep = good if keep is None else (keep & good)
    kept = ok[keep]
    drop = ok[~keep]
    routes = {}
    for v in drop["res_route_any"].fillna("none"):
        routes[str(v)] = routes.get(str(v), 0) + 1
    n_pos = int(drop["y"].sum())
    acct = {
        "n_read": int(len(ok)),
        "n_kept": int(len(kept)),
        "n_dropped": int(len(drop)),
        "per_arm_n_missing": miss,
        "dropped_positive": n_pos,
        "dropped_negative": int(len(drop) - n_pos),
        "dropped_names": sorted(str(x) for x in drop["name"]) if len(drop) < 60 else [],
        "dropped_route_census": routes,
        "sums": bool(len(kept) + len(drop) == len(ok)),
        # THE RULE IS ROUTE CONCENTRATION, NOT A PERCENTAGE. A 90 percent
        # positive-share threshold would not fire on 17 of 274, which is exactly
        # the case it would exist for.
        "pooled_comparison_refused": bool(
            len(drop) > 0 and (n_pos == len(drop) or n_pos == 0)),
        "why_refused_if_it_is": (
            "every dropped row falls on one side of the outcome, so the hole is "
            "perfectly correlated with what is being predicted and the pooled "
            "comparison on this label is a statement about a different population"),
    }
    return kept, acct


# --------------------------------------------------------------------------
# folds
# --------------------------------------------------------------------------

def burn_in_year(frame, label: str):
    """The first year by which the training pool has enough rows AND enough of BOTH
    classes. A burn-in that counts rows alone can hand fold 1 a training set with no
    positives, which fits nothing and reports a number anyway."""
    col = f"res_year_{label}"
    years = sorted({int(y) for y in frame[col].dropna()})
    for y in years:
        sub = frame[frame[col] <= y]
        pos = int(sub["y"].sum())
        if len(sub) >= BURN_IN_MIN_ROWS and pos >= BURN_IN_MIN_PER_CLASS \
                and (len(sub) - pos) >= BURN_IN_MIN_PER_CLASS:
            return y
    return None


def folds(frame, label: str, burn: int):
    col = f"res_year_{label}"
    hi = int(frame[col].max())
    out = []
    k = 1
    while True:
        lo = burn + 1 + FOLD_WIDTH_YEARS * (k - 1)
        up = burn + FOLD_WIDTH_YEARS * k
        if lo > hi:
            break
        test = frame[(frame[col] >= lo) & (frame[col] <= up)]
        train = frame[frame[col] < lo]
        # EMPTY BLOCKS ARE KEPT. Dropping them made the published block list
        # jump straight from one five-year window to another six years later,
        # which reads as a broken forward chain to anybody checking it. An empty
        # block contributes nothing to any statistic; it is carried so the chain
        # is contiguous by construction and a gap in the panel is visible as a
        # zero rather than as a missing row.
        out.append({"k": k, "lo": lo, "hi": up,
                    "n_train": int(len(train)), "n_test": int(len(test)),
                    "train_pos": int(train["y"].sum()),
                    "test_pos": int(test["y"].sum()),
                    "train_base_rate": (round(float(train["y"].mean()), 4)
                                        if len(train) else None),
                    "_train": train, "_test": test})
        k += 1
    return out


# --------------------------------------------------------------------------
# Platt
# --------------------------------------------------------------------------

def platt_fit(scores, y, *, ridge=RIDGE, max_iter=100):
    """L2-penalised Newton-IRLS with step halving, standardized on TRAINING rows only.

    NOT A BARE HESSIAN RIDGE. Adding lambda*I to the Hessian makes it invertible and
    does NOT bound the coefficients: under separation the maximum-likelihood estimate
    is at infinity and undamped Newton overflows on the way there. The penalty is
    applied to the GRADIENT as well, which is what actually bounds the fit, and any
    step that increases deviance is halved.
    """
    np = _numpy()
    s = np.asarray(scores, dtype=np.float64)
    t = np.asarray(y, dtype=np.float64)
    mu = float(s.mean())
    sd = float(s.std(ddof=0)) or 1.0
    z = (s - mu) / sd
    X = np.column_stack([np.ones_like(z), z])
    w = np.zeros(2)

    def dev(w_):
        e = np.clip(X @ w_, -LOGIT_CLIP, LOGIT_CLIP)
        p = 1.0 / (1.0 + np.exp(-e))
        p = np.clip(p, 1e-12, 1 - 1e-12)
        return float(-2.0 * np.sum(t * np.log(p) + (1 - t) * np.log(1 - p))
                     + ridge * float(w_ @ w_))

    cur = dev(w)
    for _ in range(max_iter):
        e = np.clip(X @ w, -LOGIT_CLIP, LOGIT_CLIP)
        p = 1.0 / (1.0 + np.exp(-e))
        g = X.T @ (p - t) + ridge * w
        W = np.clip(p * (1 - p), 1e-9, None)
        H = X.T @ (X * W[:, None]) + ridge * np.eye(2)
        try:
            step = np.linalg.solve(H, g)
        except Exception:                                     # noqa: BLE001
            break
        lam = 1.0
        for _ in range(30):
            cand = w - lam * step
            d = dev(cand)
            if d <= cur + 1e-12:
                w, cur = cand, d
                break
            lam *= 0.5
        else:
            break
        if float(np.max(np.abs(lam * step))) < 1e-10:
            break
    return {"a": float(w[0]), "b": float(w[1]), "mu": mu, "sd": sd}


def platt_apply(fit, scores):
    np = _numpy()
    z = (np.asarray(scores, dtype=np.float64) - fit["mu"]) / (fit["sd"] or 1.0)
    e = np.clip(fit["a"] + fit["b"] * z, -LOGIT_CLIP, LOGIT_CLIP)
    return 1.0 / (1.0 + np.exp(-e))


def brier(p, y):
    np = _numpy()
    return float(np.mean((np.asarray(p) - np.asarray(y, dtype=np.float64)) ** 2))


def log_loss(p, y, eps=1e-6):
    np = _numpy()
    q = np.clip(np.asarray(p), eps, 1 - eps)
    t = np.asarray(y, dtype=np.float64)
    return float(-np.mean(t * np.log(q) + (1 - t) * np.log(1 - q)))


def ece(p, y, bins=ECE_BINS, scheme="quantile"):
    np = _numpy()
    q = np.asarray(p, dtype=np.float64)
    t = np.asarray(y, dtype=np.float64)
    if scheme == "quantile":
        edges = np.quantile(q, np.linspace(0, 1, bins + 1))
        edges[0] -= 1e-9
        edges[-1] += 1e-9
    else:
        edges = np.linspace(0.0, 1.0, bins + 1)
    tot, n = 0.0, q.size
    for i in range(bins):
        m = (q > edges[i]) & (q <= edges[i + 1])
        c = int(m.sum())
        if c:
            tot += c * abs(float(q[m].mean()) - float(t[m].mean()))
    return float(tot / n) if n else float("nan")


def pair_counts(scores, y):
    """Concordant, discordant and tied pairs, and the AUC rebuilt from them. Published
    because an AUC on a low-cardinality arm can be most of the way to a coin without
    looking like one, and the tie share is what says so."""
    np = _numpy()
    s = np.asarray(scores, dtype=np.float64)
    t = np.asarray(y, dtype=bool)
    pos, neg = s[t], s[~t]
    if not pos.size or not neg.size:
        return {}
    d = pos[:, None] - neg[None, :]
    c = int((d > 0).sum())
    dis = int((d < 0).sum())
    tie = int((d == 0).sum())
    n = c + dis + tie
    return {"concordant": c, "discordant": dis, "tied": tie, "n_pairs": n,
            "auc_from_pairs": round((c + 0.5 * tie) / n, 6) if n else None,
            "tied_pair_share": round(tie / n, 6) if n else None,
            "somers_d": round((c - dis) / n, 6) if n else None,
            "gamma": round((c - dis) / (c + dis), 6) if (c + dis) else None,
            "n_distinct": int(np.unique(s).size)}


# --------------------------------------------------------------------------
# floors
# --------------------------------------------------------------------------

def _floor_shell(label, n, k, why):
    return {"label": label, "n": n, "n_clusters": k, "estimator": "E_cond",
            "derived_in_run": False, "status": why, "mde95": None}


def _econd_floor_stat(label, cluster_ids, pa, pb, y, stat, *, B=B_BOOT, seed=SEED,
                      higher_is_better=True):
    """Player-clustered E_cond bootstrap of stat(pa) - stat(pb).

    A SECOND FLOOR FUNCTION because source_backtest._econd_floor branches only
    between AUC and Spearman, and the calibration deltas here are Brier, log loss and
    calibration error. It reuses _cluster_layout and _cluster_draw so the resampler is
    literally the same code, and mirrors the key set and the convention string so the
    two floors are comparable. It does NOT mirror `statistic`: that key stays honest
    or the artifact lies about what was floored.
    """
    np = _numpy()
    n = len(cluster_ids)
    nk = len(set(cluster_ids))
    if np is None:
        return _floor_shell(label, n, nk, "not derived: numpy unavailable")
    if n < MIN_ROWS or nk < MIN_CLUSTERS:
        return _floor_shell(label, n, nk, "not derived: frame below the floor gate")
    A = np.asarray(pa, dtype=np.float64)
    Bv = np.asarray(pb, dtype=np.float64)
    Y = np.asarray(y, dtype=np.float64)
    ids = {k: i for i, k in enumerate(dict.fromkeys(cluster_ids))}
    order, starts, lens = _cluster_layout(np, [ids[k] for k in cluster_ids])
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(B):
        idx = _cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        yy = Y[idx]
        if yy.sum() == 0 or yy.sum() == yy.size:
            continue
        try:
            xa, xb = stat(A[idx], yy), stat(Bv[idx], yy)
        except Exception:                                     # noqa: BLE001
            continue
        if xa is None or xb is None or not (math.isfinite(xa) and math.isfinite(xb)):
            continue
        diffs.append(xa - xb)
    if len(diffs) < 50:
        return _floor_shell(label, n, nk, "not derived: too few usable draws")
    pa_, pb_ = stat(A, Y), stat(Bv, Y)
    d = np.asarray(diffs, dtype=np.float64)
    sd = float(d.std(ddof=1))
    q = np.quantile(d, [0.025, 0.975])
    return {
        "label": label, "n": n, "n_clusters": nk, "estimator": "E_cond",
        "derived_in_run": True, "resampling_unit": "player cluster",
        "produced_by": "tools/hof_bakeoff._econd_floor_stat",
        "B": B, "B_used": len(diffs), "seed": seed,
        "higher_is_better": bool(higher_is_better),
        "point_delta": round(float(pa_ - pb_), 6),
        "boot_mean_delta": round(float(d.mean()), 6),
        "sd": round(sd, 6),
        "mde95": round(_Z95 * sd, 5),
        "ci95": [round(float(q[0]), 5), round(float(q[1]), 5)],
        "convention": "MDE95 = 1.645 * sd(delta), one-sided",
    }


def _auc_stat(s, y):
    np = _numpy()
    return _auc_np(np, np.asarray(s, dtype=np.float64), np.asarray(y, dtype=bool))


def _verdict(delta, mde95, *, higher_is_better=True, estimator="E_cond"):
    if delta is None or mde95 is None:
        return f"not derived ({estimator})"
    if abs(delta) <= mde95:
        return f"not resolvable at this power ({estimator}, MDE95 {mde95})"
    better = (delta > 0) if higher_is_better else (delta < 0)
    return (f"{'the arm' if better else 'the comparator'} separates "
            f"({estimator}, MDE95 {mde95})")


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def _discrimination(frame, arms, B, seed):
    np = _numpy()
    y = np.asarray(frame["y"].tolist(), dtype=bool)
    keys = list(frame["player_ID"])
    per_arm = {}
    for a in arms:
        s = np.asarray(frame[a].tolist(), dtype=np.float64)
        per_arm[a] = {"auc": round(_auc_np(np, s, y), 6), **pair_counts(s, y)}
    argmax_public = max(PUBLIC_ARMS, key=lambda a: per_arm[a]["auc"])

    fam = {}
    for comp, comp_name in ((REFERENCE_ARM, "pre_designated_reference"),
                            (argmax_public, "resampled_public_argmax")):
        cells, cellmap = [], {}
        for a in DISTINCT_METRICS:
            if a == comp:
                continue
            fl = _econd_floor_stat(f"auc.{comp_name}.{a}", keys,
                                   frame[a].tolist(), frame[comp].tolist(),
                                   frame["y"].tolist(), _auc_stat, B=B, seed=seed)
            cellmap[a] = {
                "arm": a, "comparator": comp,
                "auc_arm": per_arm[a]["auc"],
                "auc_comparator": per_arm[comp]["auc"],
                "floor_E_cond_in_run": fl,
                "verdict": _verdict(fl.get("point_delta"), fl.get("mde95")),
            }
            if fl.get("mde95") is not None:
                cells.append({"key": a, "delta": fl["point_delta"], "sd": fl["sd"]})
        holm = holm_family(cells) if cells else {}
        fam[comp_name] = {
            "comparator": comp,
            "family_size_k": len(cells),
            "cells": cellmap,
            "holm": holm,
            "carries_the_ranking_claim": comp_name == "resampled_public_argmax",
        }

    repro = {}
    for pub_, own in (("JAWS", "jaws"), ("WAR_career", "career_war"),
                      ("WAR_peak7", "war7")):
        a = np.asarray(frame[pub_].tolist(), dtype=np.float64)
        b = np.asarray(frame[own].tolist(), dtype=np.float64)
        d = np.abs(a - b)
        repro[f"{pub_}_vs_{own}"] = {
            "n": int(d.size),
            "n_exact_to_a_tenth": int((np.round(d, 1) == 0).sum()),
            "max_abs_difference": round(float(d.max()), 4),
            "mean_abs_difference": round(float(d.mean()), 4),
        }
    return {"per_arm": per_arm, "public_argmax": argmax_public,
            "families": fam, "reproduction_check": repro}


def _calibration(fs, arms, B, seed):
    np = _numpy()
    pooled = {a: {"p": [], "y": [], "raw": [], "keys": []} for a in arms}
    per_fold_invariance = []
    horizon_violations = 0
    for f in fs:
        tr, te = f["_train"], f["_test"]
        if not len(te) or tr["y"].sum() == 0 or tr["y"].sum() == len(tr):
            continue
        # GUARD 5: a training row whose last season falls at or after the fold cut
        # carries WAR earned after its own cut. It cannot move the raw AUC leg but it
        # contaminates the Platt fit, so it is counted rather than assumed away.
        horizon_violations += int((tr["last_season"] >= f["lo"]).sum())
        for a in arms:
            fit = platt_fit(tr[a].tolist(), tr["y"].tolist())
            p = platt_apply(fit, te[a].tolist())
            yv = np.asarray(te["y"].tolist(), dtype=bool)
            raw = np.asarray(te[a].tolist(), dtype=np.float64)
            if yv.sum() and yv.sum() != yv.size:
                # GUARD 3: PER-FOLD, never pooled. Platt is monotone inside a fold, so
                # this must hold to 1e-9. The pooled version is deliberately absent.
                per_fold_invariance.append(
                    abs(_auc_np(np, p, yv) - _auc_np(np, raw, yv)))
            pooled[a]["p"].extend(list(p))
            pooled[a]["y"].extend(list(te["y"]))
            pooled[a]["raw"].extend(list(te[a]))
            pooled[a]["keys"].extend(list(te["player_ID"]))

    levels, shifts = {}, {}
    for a in arms:
        P = pooled[a]
        if not P["p"]:
            continue
        levels[a] = {
            "brier": round(brier(P["p"], P["y"]), 6),
            "log_loss": round(log_loss(P["p"], P["y"]), 6),
            "ece_quantile10": round(ece(P["p"], P["y"], scheme="quantile"), 6),
            "ece_equalwidth10": round(ece(P["p"], P["y"], scheme="equal"), 6),
            "is_a_fold_mixture_not_an_arm_calibration": True,
        }
        yv = np.asarray(P["y"], dtype=bool)
        shifts[a] = round(
            _auc_np(np, np.asarray(P["p"]), yv)
            - _auc_np(np, np.asarray(P["raw"], dtype=np.float64), yv), 6)

    ref = max(levels, key=lambda a: -levels[a]["brier"]) if levels else None
    deltas = {}
    if ref:
        for a in levels:
            if a == ref:
                continue
            P, Q = pooled[a], pooled[ref]
            for name, fn, hib in (("brier", brier, False),
                                  ("log_loss", log_loss, False),
                                  ("ece_quantile10",
                                   lambda p, y: ece(p, y, scheme="quantile"), False)):
                fl = _econd_floor_stat(f"cal.{name}.{a}", P["keys"], P["p"], Q["p"],
                                       P["y"], fn, B=B, seed=seed,
                                       higher_is_better=hib)
                deltas.setdefault(a, {})[name] = {
                    "vs": ref,
                    "floor_E_cond_in_run": fl,
                    "verdict": _verdict(fl.get("point_delta"), fl.get("mde95"),
                                        higher_is_better=hib),
                    "estimator_note": (
                        "E_cond. This lane refits a Platt map per fold, so the "
                        "calibration claim is the CONDITIONAL one: it does not carry "
                        "the refit variance an E_refit floor would."),
                }

    # HOLM PER STATISTIC, because the gate's own clause is phrased "under Holm" and a
    # count of cells clearing their bare floors cannot answer it. One family per
    # statistic: the three statistics are three different questions about the same
    # arms, not one family of thirty.
    holm = {}
    for name in ("brier", "log_loss", "ece_quantile10"):
        cells = []
        for a, blk in deltas.items():
            fl = (blk.get(name) or {}).get("floor_E_cond_in_run") or {}
            if fl.get("mde95") is not None:
                cells.append({"key": a, "delta": fl["point_delta"], "sd": fl["sd"]})
        if cells:
            holm[name] = holm_family(cells)
    n_clear = sum(1 for st in holm.values()
                  for c in (st.get("cells") or []) if c.get("reject_holm"))
    n_cells = sum(len(st.get("cells") or []) for st in holm.values())

    return {
        "holm_by_statistic": holm,
        "n_cells_clearing_holm": n_clear,
        "n_cells": n_cells,
        "reference_arm_lowest_brier": ref,
        "levels": levels,
        "pooled_calibrated_minus_raw_auc": shifts,
        "why_the_pooled_shift_is_published_not_asserted_zero": (
            "Platt is monotone WITHIN a fold. A pooled vector built from many "
            "fold-specific maps is not one monotone map, so a correct implementation "
            "moves the pooled AUC. The per-fold invariance below is the real guard "
            "and the pooled shift is a measured property of fold-map heterogeneity."),
        "per_fold_auc_invariance_max_abs": (
            round(max(per_fold_invariance), 12) if per_fold_invariance else None),
        "per_fold_auc_invariance_n_checks": len(per_fold_invariance),
        "training_rows_with_a_season_at_or_after_their_fold_cut": horizon_violations,
        "deltas": deltas,
    }


def run(*, offline=True, as_of_year=2026, labels=("bbwaa", "any"), B=B_BOOT,
        seed=SEED, write=True) -> dict:
    frozen = frozen_at()
    hd.clear_cache()
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "tools/hof_bakeoff.py",
        "gate_doc": "docs/HOF_BAKEOFF_GATE.md",
        "gate_frozen": frozen,
        "seed": seed, "B": B,
        "as_of_year": as_of_year,
        "arms": {"public": list(PUBLIC_ARMS), "in_house": list(INHOUSE_ARMS),
                 "distinct_metrics_for_holm": list(DISTINCT_METRICS),
                 "rejected": REJECTED_ARMS},
        "primary_label": "bbwaa",
        "why_bbwaa_is_primary": (
            "label_any's censoring is OUTCOME-DEPENDENT: induction resolves a one "
            "immediately while non-induction requires the window close plus the "
            "committee horizon, so recent strata contribute positives and no "
            "negatives. Either one on its own would disqualify it from a headline."),
        "labels": {},
    }
    for lab in labels:
        fr = bakeoff_frame(lab, offline=offline, as_of_year=as_of_year)
        kept, acct = common_support(fr, lab)
        burn = burn_in_year(kept, lab)
        fs = folds(kept, lab, burn) if burn else []
        disc = _discrimination(kept, ALL_ARMS, B, seed)
        test_pool = kept[kept[f"res_year_{lab}"] > burn] if burn else kept.iloc[0:0]
        disc_test = (_discrimination(test_pool, ALL_ARMS, B, seed)
                     if len(test_pool) >= MIN_ROWS else
                     {"status": "test pool below the floor gate"})
        cal = _calibration(fs, ALL_ARMS, B, seed) if fs else {
            "status": "no folds: burn-in never satisfied"}
        out["labels"][lab] = {
            "frame": {
                "predicate": (
                    "one row per player, resolved label only (notna then == 1.0), "
                    "inner-joined to the collapsed public shelf, reduced to the "
                    "complete-case intersection over every arm"),
                "n_scored": int(len(kept)),
                "n_positive": int(kept["y"].sum()),
                "base_rate": round(float(kept["y"].mean()), 4),
                "drop_accounting": acct,
                "population_note": (
                    "this is NOT the eligible universe. It is almost exactly the set "
                    "of players a screening committee already put on a "
                    "Baseball-Reference ballot page, so an AUC here is discrimination "
                    "among candidates that committee already advanced."),
            },
            "folds": {
                "burn_in_year": burn,
                "n_folds": len(fs),
                "n_folds_with_test_rows": sum(1 for f in fs if f["n_test"]),
                "width_years": FOLD_WIDTH_YEARS,
                "blocks": [{k: v for k, v in f.items() if not k.startswith("_")}
                           for f in fs],
                "why_a_block_can_fall_after_the_as_of_year": (
                    "label_any resolves at the induction year for an inductee and "
                    "at the writers' resolution plus the committee horizon for "
                    "everybody else, and this module's resolution_year uses the "
                    "next-panel-election rule where the shipped window close does "
                    "not. A row the shipped label calls resolved today can "
                    "therefore carry a resolution year in the future. Those rows "
                    "are scored in the block their resolution year names; the "
                    "block list is contiguous and an empty window shows as a "
                    "zero rather than as a missing row."),
                "the_discrimination_leg_fits_nothing": (
                    "AUC on pooled test predictions of raw scores is identical to AUC "
                    "on those rows' raw scores. The folds exist for the calibration "
                    "leg only, and the published bar is on the FULL resolved "
                    "common-support frame, which is fold-free."),
            },
            "discrimination_full_frame": disc,
            "discrimination_test_pool": disc_test,
            "calibration": cal,
        }
    # THE SHELF-HOLE COUNT IS READ OFF THE RUN, never typed. It was a literal
    # "seventeen" until the 2026-09-24 ledger repair moved it to twenty-one.
    a_any = ((out["labels"].get("any") or {}).get("frame") or {}).get("drop_accounting")
    if a_any and a_any["n_dropped"]:
        out["why_bbwaa_is_primary"] = out["why_bbwaa_is_primary"].replace(
            " Either one on its own",
            f" Its shelf hole is also {a_any['dropped_positive']} positives and "
            f"{a_any['dropped_negative']} negatives. Either one on its own")
    if write:
        OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="B=300")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--label", default=None)
    a = ap.parse_args(argv)
    labs = (a.label,) if a.label else ("bbwaa", "any")
    d = run(B=300 if a.fast else B_BOOT, labels=labs, write=not a.dry_run)
    for lab, blk in d["labels"].items():
        f, disc = blk["frame"], blk["discrimination_full_frame"]
        print(f"\n=== label_{lab}: n={f['n_scored']} pos={f['n_positive']} "
              f"base={f['base_rate']} ===")
        if f["drop_accounting"]["n_dropped"]:
            da = f["drop_accounting"]
            print(f"  dropped {da['n_dropped']} "
                  f"({da['dropped_positive']} pos / {da['dropped_negative']} neg)"
                  f"{'  POOLED COMPARISON REFUSED' if da['pooled_comparison_refused'] else ''}")
        for arm, c in sorted(disc["per_arm"].items(), key=lambda kv: -kv[1]["auc"]):
            print(f"  {arm:14s} AUC {c['auc']:.4f}  ties {c.get('tied_pair_share', 0):.4f}  "
                  f"distinct {c.get('n_distinct')}")
        print(f"  public argmax: {disc['public_argmax']}")
        for name, fam in disc["families"].items():
            print(f"  -- vs {fam['comparator']} ({name}, k={fam['family_size_k']})")
            for arm, c in fam["cells"].items():
                fl = c["floor_E_cond_in_run"]
                if fl.get("mde95") is None:
                    continue
                print(f"     {arm:14s} d={fl['point_delta']:+.5f} "
                      f"mde95={fl['mde95']}  {c['verdict']}")
        cal = blk["calibration"]
        if cal.get("levels"):
            print(f"  per-fold AUC invariance max |diff|: "
                  f"{cal['per_fold_auc_invariance_max_abs']} over "
                  f"{cal['per_fold_auc_invariance_n_checks']} checks")
    if not a.dry_run:
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
