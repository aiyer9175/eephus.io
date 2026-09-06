# eFV driver-candidate gate lab (LANE C, 2026-08-07).
#
# WHY THIS FILE EXISTS. tools/efv_lab_runner.py can APPEND a feature and report a
# point Spearman, and that is all it can do: unweighted rho, no bootstrap, no
# control, no null band, no block-rho. docs/EFV_GATE_STANDARD.md section 2 requires
# four things this codebase has repeatedly shipped without, so every arm in lane C
# runs through here instead. The fold arithmetic is tools/efv_mde_lab.py's numpy
# replica, which carries verified bit-parity with the shipped efv_model._run_eval
# chain (see its parity mode), so a delta measured here is a delta on the served
# protocol and not on a lookalike.
#
# WHAT IT ADDS OVER efv_mde_lab: candidate feature columns (drawn from the raw
# matrix row, from a joined sidecar, or from an expression over the feature
# vector), lambda overrides and lambda bands, test-pool restriction by consensus
# FV, and a paired bootstrap of the DELTA BETWEEN TWO FEATURE SETS rather than
# between the model and its consensus baseline. Those are different statistic
# classes with different floors (EFV_GATE_STANDARD section 1a vs section 3) and
# gating one against the other's number is the specific error this lab exists to
# stop.
#
# THE AUC LEG (added 2026-09-06, lane A-CLAIM-11). Until this edit `gate()` scored
# rank ONLY, so every one of the 39 closed feature arms (D-1's 26 free keys, D-2's
# 13 _extras arms) was adjudicated on rank alone while EFV_GATE_STANDARD section 3
# says the gate is TWO metrics. `side_stats` now also returns contributor AUC
# (realized censored WAR >= efv_model._CONTRIB_WAR) and star AUC (>= _STAR_WAR),
# and because both are computed inside the SAME side_stats call on the SAME chain
# output, the AUC delta rides the SAME bootstrap draw as the rho delta: the legs
# are paired, not independently resampled, and their difference is a statistic
# with its own sampling distribution rather than two runs compared by eye.
#
# WHAT THE AUC LEG MAY AND MAY NOT DO. Contributor AUC is the CO-PRIMARY. It can
# VETO an arm that clears the rho floor (a negative AUC delta beyond its own
# floor) and it can sit inside a jointly sized Holm family. It can NEVER credit an
# arm that fails the rho floor: an AUC-only win is a NULL BY RULE, because the AUC
# cells are the ones that flatter this model most and the carve-out already caught
# six archetype arms reading as wins on AUC while rank was flat or negative. Star
# AUC is a LABELLED SENSITIVITY with no verdict weight at all (46 pitcher stars in
# the registered debuted_km cell against an E_cond floor of 0.0397,
# data/xfv_auc_floor_eval.json). `two_metric_verdict()` is the only place the rule
# is coded, and it refuses to emit a star verdict.
#
# A MISSING INPUT IS ITS OWN VERDICT (added 2026-09-06 after review). The verdict
# vocabulary is closed and it separates DECISIONS from ABSENCES: PASS, VETO_ON_AUC,
# NULL, NULL_AUC_ONLY and NULL_HOLM are decisions; NOT_ADJUDICATED_NO_RHO_FLOOR,
# NOT_ADJUDICATED_NO_AUC_FLOOR and NOT_ADJUDICATED_NO_HOLM are absences. A gate that
# spells an absence the way it spells a cleared bar is not a gate, and the AUC-floor
# case is reachable today because data/xfv_driver_floors.json predates the AUC leg.
# Holm is a FAMILY correction and therefore cannot be formed inside a per-arm loop:
# every mode measures its arms first and forms verdicts afterwards in one place,
# apply_holm_verdicts(), which is the only writer of g["verdict"].
#
# Run: python tools/efv_driver_lab.py floor [B]     re-derive the feature-add and
#                                                   lambda-shift MDE95 on the
#                                                   current 11-fold basis
#      python tools/efv_driver_lab.py auc [B]       A-CLAIM-11 instrument proof:
#                                                   in-run AUC floors + the
#                                                   zero-information twins
#      python tools/efv_driver_lab.py sb [B]        C1a  sb_rate_rel
#      python tools/efv_driver_lab.py pos           C1b  positions_played census
#      python tools/efv_driver_lab.py handbuild     C2   sidecar build (network)
#      python tools/efv_driver_lab.py hand [B]      C2   handedness gate
#      python tools/efv_driver_lab.py pairs [B]     C3   gated threshold pairs
#      python tools/efv_driver_lab.py elite [B]     C4   elite-band probes
#      python tools/efv_driver_lab.py lam [B]       C5   lambda re-sweep
#      python tools/efv_driver_lab.py wrc [B]       C6   wRC+ add-arm re-run
#
# Every mode writes its ledger under data/xfv_driver_*.json. Those names are
# deliberately outside the data/*_eval*.json glob: an eval artifact owes a
# model_registry.json row and this lane does not own that file.
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                                          # noqa: E402  read-only
import efv_mde_lab as M                                        # noqa: E402  fold arithmetic

SEED = 20260807
SIDES = ("hit", "pit")
DATA = ROOT / "data"
# The raw people join lives in .cache, not data/. Top-level data/*.json is PUBLISHED
# (deploy/publish_paths.txt), and 6,840 rows of handedness that nothing serves would
# ship to the web for no reason. It is a rebuildable fetch input, not evidence: the
# evidence is data/xfv_driver_handedness.json, which carries the join's provenance and
# per-code counts, and `handbuild` reconstructs this file in about ten seconds.
HAND_SIDECAR = ROOT / ".cache" / "xfv_handedness.json"

# Outcome bars for the AUC leg, READ from efv_model rather than restated here, so a
# label epoch cannot silently desync this lab from the served scoreboard. They read
# 3.0 / 10.0 today (efv_model.py:631-632).
CONTRIB_WAR = float(E._CONTRIB_WAR)
STAR_WAR = float(E._STAR_WAR)

# The gate's statistic vector. Order is the reporting order, not a precedence.
# `auc_star` is present so it is MEASURED and VISIBLE; it is excluded from every
# verdict by two_metric_verdict(), which is the only function allowed to decide.
GATE_KEYS = ("rho", "block_rho", "auc_contrib", "auc_star")
PRIMARY_KEYS = ("rho", "block_rho", "auc_contrib")
SENSITIVITY_KEYS = ("auc_star",)


# --------------------------------------------------------------------- pools
def load_pool(side: str, extras=None) -> dict:
    """The debuted-KM eval pool for one side, plus any candidate columns.

    `extras` is a list of {"name", "get", "impute"}. `get(raw_row, feats)` returns
    the candidate value or None; `impute` is "zero" (the neutral centre of a
    level-relative rate, and what a shipped _vec default would do) or "mean" (the
    observed-row mean, which is what "neutral imputation, no missing indicator"
    means for an indicator column: an imputed row standardizes to exactly 0 and
    therefore cannot carry missingness into the fit as a level shift).
    """
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in raw if r["kind"] == "debuted"]
    by_key = {r["player_key"]: r for r in deb}
    prep = E._prep(deb, "target_censored", side)
    keys, mono = E._feature_spec(side)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    D = {
        "side": side, "keys": list(keys), "mono": mono, "X": X,
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "pk": [r["player_key"] for r in prep],
        "lam": E.blend_lambda(side),
        "n": len(prep),
        "ex_names": [], "cov": {},
    }
    ex_cols = []
    for spec in (extras or []):
        vals, obs = [], []
        for r in prep:
            v = spec["get"](by_key[r["player_key"]], r["feats"])
            obs.append(v is not None)
            vals.append(float(v) if v is not None else math.nan)
        v = np.array(vals, dtype=float)
        o = np.array(obs, dtype=bool)
        fill = 0.0 if spec.get("impute", "zero") == "zero" else (
            float(v[o].mean()) if o.any() else 0.0)
        v[~o] = fill
        ex_cols.append(v)
        D["ex_names"].append(spec["name"])
        D["cov"][spec["name"]] = {
            "observed": int(o.sum()), "n": len(v), "frac": round(float(o.mean()), 4),
            "impute": spec.get("impute", "zero"), "impute_value": round(fill, 6),
            "observed_mean": round(float(v[o].mean()), 5) if o.any() else None,
            "observed_sd": round(float(v[o].std()), 5) if o.any() else None,
        }
    D["EX"] = np.array(ex_cols).T if ex_cols else np.zeros((D["n"], 0))
    return D


def with_permuted(D: dict, name: str, rng) -> dict:
    """A zero-information twin of one candidate column: the SAME marginal, the row
    link destroyed. Gate standard control 2. Returned as a new column appended to
    EX so the candidate and its control are scored by identical code."""
    i = D["ex_names"].index(name)
    col = D["EX"][:, i].copy()
    col = col[rng.permutation(len(col))]
    out = dict(D)
    out["EX"] = np.hstack([D["EX"], col[:, None]])
    out["ex_names"] = D["ex_names"] + [name + "__perm"]
    return out


# --------------------------------------------------------------------- chain
def chain(D, ex=(), sel=None, years=None, lam=None, lam_band=None,
          fv_min=None, fv_max=None):
    """One forward-chained pass. `ex` = indices into D['EX'] to append to the
    feature matrix. Returns (year, cons, blend, target, weight) or None.

    `lam_band` = {"band": [lo, hi], "dip": d} reproduces efv_lab_runner's
    tier-aware trust: lambda scales by (1 - d) inside the band. A NEGATIVE dip is
    a band RAISE, which is what the C4a elite-conviction arm asks for.
    `fv_min`/`fv_max` restrict the SCORED rows only; the training frame is never
    restricted, so an elite-cohort read is an eval restriction, not a new model.
    """
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    base_lam = D["lam"] if lam is None else float(lam)
    if sel is None:
        sel = np.arange(D["n"])
    Xf = D["X"][sel]
    if len(ex):
        Xf = np.hstack([Xf, D["EX"][np.ix_(sel, list(ex))]])
    y, w, fv, dy = D["y"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = M.ols_fit(fv[tr], y[tr])
        rg = M.ridge_fit(Xf[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        if fv_min is not None or fv_max is not None:
            keep = np.ones(len(te), dtype=bool)
            if fv_min is not None:
                keep &= fv[te] >= fv_min
            if fv_max is not None:
                keep &= fv[te] < fv_max
            te = te[keep]
            if len(te) == 0:
                continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = M.ridge_pred(rg, Xf[te])
        if lam_band:
            lo, hi = lam_band["band"]
            lam_row = np.where((fv[te] >= lo) & (fv[te] < hi),
                               base_lam * (1.0 - lam_band["dip"]), base_lam)
        else:
            lam_row = np.full(len(te), base_lam)
        YR.append(np.full(len(te), yr))
        C.append(cons)
        B.append((1 - lam_row) * cons + lam_row * mod)
        T.append(y[te])
        W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def auc(scores, labels):
    """ROC AUC by the Mann-Whitney U statistic, average ranks for ties.

    A numpy replica of source_backtest._auc, which is what efv_model._auc_breakdown
    calls, so the leg measures the served statistic and not a lookalike; the parity
    check against the shipped function is `auc_mode`'s control A0 and it must be
    re-run whenever this changes. NaN, never a number, on a degenerate label vector:
    a fold or a bootstrap draw with no positives has no AUC and must drop out of the
    bootstrap rather than contribute a 0.5.

    UNWEIGHTED, deliberately. Every pooled rho in this lab is pair-weighted by
    observed_seasons/6 and this is not. That asymmetry is inherited from the served
    chain (EFV_GATE_STANDARD section 7.6 control C-a) and is reported rather than
    quietly fixed: a weighted AUC would be a different statistic from the one the
    scoreboard publishes, and the point of this leg is to gate on the published one.
    """
    lab = np.asarray(labels, dtype=bool)
    n1 = int(lab.sum())
    n2 = int(len(lab) - n1)
    if n1 == 0 or n2 == 0 or len(lab) < 15:
        return float("nan")
    r = M._rankavg(np.asarray(scores, dtype=float))
    u = float(r[lab].sum()) - n1 * (n1 + 1) / 2.0
    return u / (n1 * n2)


def side_stats(r, weighted=True):
    """Pooled pair-weighted rho, the SIDE's own block-rho, and the two AUC legs, all
    on identical rows.

    Block-rho here is restricted to this side's (cohort-year) blocks. The joint
    both-sides instrument in EFV_GATE_STANDARD section 3 is the right one for a
    MODEL-vs-consensus claim; for a one-sided feature add it dilutes the candidate
    with a side the candidate cannot touch, so the floor and the effect are both
    measured on the side-restricted form and the two are never mixed.

    `auc_contrib` and `auc_star` are the discrimination legs on the SAME rows and
    the SAME resample as the two rank legs. The population is the debuted pool
    (load_pool keeps kind == "debuted"), which is the population the section-3
    carve-out rules ADMISSIBLE: the inadmissible full-pool debut / no-debut cell is
    unreachable from this lab by construction, because no full_pool frame is ever
    built here. Both AUC legs are also reported for the consensus baseline so a
    reader can see whether an arm moved the model or moved the shared label mix.
    """
    yr, cons, blend, tgt, w = r
    ww = w if weighted else None
    bb = M.block_norm(yr, blend)
    bt = M.block_norm(yr, tgt)
    bc = M.block_norm(yr, cons)
    lab_c = tgt >= CONTRIB_WAR
    lab_s = tgt >= STAR_WAR
    return {
        "n": int(len(tgt)),
        "rho": M.wrho(blend, tgt, ww),
        "cons_rho": M.wrho(cons, tgt, ww),
        "block_rho": M.wrho(bb, bt, ww),
        "cons_block_rho": M.wrho(bc, bt, ww),
        "auc_contrib": auc(blend, lab_c),
        "auc_star": auc(blend, lab_s),
        "cons_auc_contrib": auc(cons, lab_c),
        "cons_auc_star": auc(cons, lab_s),
        "n_pos_contrib": int(lab_c.sum()),
        "n_pos_star": int(lab_s.sum()),
    }


def fold_rhos(r, weighted=True):
    yr, cons, blend, tgt, w = r
    out = {}
    for u in np.unique(yr):
        m = yr == u
        if int(m.sum()) < 12:
            continue
        out[int(u)] = M.wrho(blend[m], tgt[m], w[m] if weighted else None)
    return out


def fold_aucs(r, thresh=None):
    """Per-fold contributor AUC. A fold whose test year has no positive (or no
    negative) has no AUC and is absent from the dict rather than imputed."""
    thresh = CONTRIB_WAR if thresh is None else float(thresh)
    yr, _cons, blend, tgt, _w = r
    out = {}
    for u in np.unique(yr):
        m = yr == u
        if int(m.sum()) < 15:
            continue
        a = auc(blend[m], tgt[m] >= thresh)
        if np.isfinite(a):
            out[int(u)] = a
    return out


# --------------------------------------------------------------------- gate
def gate(D, cand_ex, ctrl_ex=None, base_ex=(), B=2000, n_perm=200,
         lam=None, lam_band=None, base_lam=None, fv_min=None, seed=SEED,
         perm_col=None, tag="", years=None):
    """The full EFV_GATE_STANDARD battery for one candidate against one baseline.

    Returns point deltas on the four gate statistics (pooled rho, side block-rho,
    contributor AUC, star AUC), a paired bootstrap of every delta (train AND test
    resampled, refit every draw) whose sd IS the floor for that statistic class, a
    zero-information control delta, a permutation null band on rho AND on
    contributor AUC, and the per-fold sign count over the 11 forward-chained splits.

    PAIRING IS THE POINT. One `sel` per draw feeds both the baseline chain and the
    candidate chain, and one side_stats call per chain produces all four statistics,
    so rho and AUC move together across draws. Resampling the two legs separately
    would give each leg an honest marginal sd and a meaningless joint reading, and
    the conjunction rule in EFV_GATE_STANDARD section 3 is a joint reading.

    This function does NOT decide anything. It reports. two_metric_verdict() is the
    only place a verdict is formed, and it is the only place that knows star AUC
    carries no weight.
    """
    t0 = time.time()
    base = chain(D, base_ex, lam=base_lam, fv_min=fv_min, years=years)
    cand = chain(D, cand_ex, lam=lam, lam_band=lam_band, fv_min=fv_min, years=years)
    if base is None or cand is None:
        return {"tag": tag, "error": "no fold survived"}
    sb, sc = side_stats(base), side_stats(cand)

    def _num(v, nd=5):
        v = float(v)
        return round(v, nd) if np.isfinite(v) else None

    point = {k: _num(sc[k] - sb[k]) for k in GATE_KEYS}
    fb, fc = fold_rhos(base), fold_rhos(cand)
    folds = sorted(set(fb) & set(fc))
    fold_delta = {int(y): round(fc[y] - fb[y], 4) for y in folds}
    wins = sum(1 for y in folds if fc[y] > fb[y])
    ab, ac = fold_aucs(base), fold_aucs(cand)
    afolds = sorted(set(ab) & set(ac))
    fold_auc_delta = {int(y): round(ac[y] - ab[y], 4) for y in afolds}
    auc_wins = sum(1 for y in afolds if ac[y] > ab[y])

    ctrl = None
    if ctrl_ex is not None:
        cc = chain(D, ctrl_ex, lam=lam, lam_band=lam_band, fv_min=fv_min, years=years)
        if cc is not None:
            sx = side_stats(cc)
            ctrl = {k: _num(sx[k] - sb[k]) for k in GATE_KEYS}

    rng = np.random.default_rng(seed)
    boot = {k: [] for k in GATE_KEYS}
    for _ in range(B):
        sel = rng.integers(0, D["n"], D["n"])
        rb = chain(D, base_ex, sel=sel, lam=base_lam, fv_min=fv_min, years=years)
        rc = chain(D, cand_ex, sel=sel, lam=lam, lam_band=lam_band, fv_min=fv_min, years=years)
        if rb is None or rc is None:
            continue
        a, b = side_stats(rb), side_stats(rc)
        for k in boot:
            d = b[k] - a[k]
            if np.isfinite(d):
                boot[k].append(d)

    def _summ(vals, pt):
        a = np.array(vals, dtype=float)
        a = a[np.isfinite(a)]
        sd = float(a.std(ddof=1)) if len(a) > 2 else float("nan")
        ok = pt is not None and np.isfinite(sd)
        # A degenerate bootstrap leaves sd = nan: fewer than 3 finite draws, which the
        # AUC legs can reach when resamples lose their positives and auc() returns nan
        # by design. json.dumps then writes a bare NaN token, which is not JSON and
        # which strict readers reject, so the whole ledger becomes unreadable rather
        # than merely uninformative. None is the honest encoding of "not estimable"
        # and it round-trips. `point` was already guarded this way; these three were
        # not, and they are the three a floor is read out of.
        sd_ok = bool(np.isfinite(sd))
        return {
            "B_used": int(len(a)), "point": (None if pt is None else round(float(pt), 5)),
            "boot_mean": round(float(a.mean()), 5) if len(a) else None,
            "sd": round(sd, 5) if sd_ok else None,
            "mde95_onesided": round(1.645 * sd, 4) if sd_ok else None,
            "mde95_twosided": round(1.96 * sd, 4) if sd_ok else None,
            "x_floor": round(abs(pt) / (1.645 * sd), 3) if (ok and sd > 0) else None,
            "ci95": [round(float(np.percentile(a, 2.5)), 5),
                     round(float(np.percentile(a, 97.5)), 5)] if len(a) else None,
            "p_gt_0": round(float((a > 0).mean()), 4) if len(a) else None,
            "resolvable": bool(abs(pt) >= 1.645 * sd) if (ok and sd > 0) else False,
        }

    out = {
        "tag": tag,
        "n_pool": D["n"], "n_scored_base": sb["n"], "n_scored_cand": sc["n"],
        "baseline": {k: _num(v) for k, v in sb.items() if k != "n"},
        "candidate": {k: _num(v) for k, v in sc.items() if k != "n"},
        "delta": point,
        "control_delta": ctrl,
        "folds_scored": len(folds), "fold_rho_wins": wins,
        "fold_delta": fold_delta,
        "fold_auc_scored": len(afolds), "fold_auc_wins": auc_wins,
        "fold_auc_delta": fold_auc_delta,
        "bootstrap": {k: _summ(boot[k], point[k]) for k in boot},
        "coverage": D["cov"],
        "auc_leg": {
            "labels": {"contributor_war": CONTRIB_WAR, "star_war": STAR_WAR,
                       "source": "efv_model._CONTRIB_WAR / _STAR_WAR"},
            "population": ("debuted pool only (load_pool keeps kind == 'debuted'); the "
                           "full-pool debut / no-debut cell the EFV_GATE_STANDARD "
                           "section 3 carve-out rules INADMISSIBLE is not built here"),
            "n_pos_contributor": sb["n_pos_contrib"], "n_pos_star": sb["n_pos_star"],
            "prevalence_contributor": round(sb["n_pos_contrib"] / max(1, sb["n"]), 4),
            "prevalence_star": round(sb["n_pos_star"] / max(1, sb["n"]), 4),
            "weighting": "UNWEIGHTED, unlike the pair-weighted rho legs (control C-a)",
            "paired_with_rho": True,
            "estimator": ("E_refit: the whole pool is resampled, ridge and consensus OLS "
                          "refit every draw. There is no E_cond leg in this lab, so a "
                          "claim taken from it must NAME E_refit (section 7.1)."),
            "clustering": ("row-level i.i.d. resampling is admissible here because the "
                           "driver pool carries exactly one row per player_key (839 hit / "
                           "981 pit, zero repeats, measured 2026-09-06). The 1.519x "
                           "anti-conservative narrowing that forced clustered resampling "
                           "on the head-to-head frame is a property of THAT frame."),
            "star_role": ("LABELLED SENSITIVITY, NO VERDICT WEIGHT. Reported so it is "
                          "visible; two_metric_verdict() refuses to score it."),
            "conjunction_rule": ("contributor AUC is CO-PRIMARY: it may VETO an arm that "
                                 "clears the rho floor and may sit in a jointly sized Holm "
                                 "family, and it may NEVER credit an arm that fails the rho "
                                 "floor. An AUC-only win is a NULL BY RULE."),
        },
        "elapsed_s": round(time.time() - t0, 1),
    }

    if perm_col is not None and n_perm:
        draws, adraws = [], []
        prng = np.random.default_rng(seed + 7)
        i = D["ex_names"].index(perm_col)
        col0 = D["EX"][:, i].copy()
        for _ in range(n_perm):
            D2 = dict(D)
            EX2 = D["EX"].copy()
            EX2[:, i] = col0[prng.permutation(len(col0))]
            D2["EX"] = EX2
            rc = chain(D2, cand_ex, lam=lam, lam_band=lam_band, fv_min=fv_min, years=years)
            if rc is None:
                continue
            s = side_stats(rc)
            d = s["rho"] - sb["rho"]
            if np.isfinite(d):
                draws.append(d)
            da = s["auc_contrib"] - sb["auc_contrib"]
            if np.isfinite(da):
                adraws.append(da)
        a = np.array(draws)
        out["permutation_null"] = {
            "draws": int(len(a)),
            "mean": round(float(a.mean()), 5),
            "sd": round(float(a.std(ddof=1)), 5),
            "p95": round(float(np.percentile(a, 95)), 5),
            # p = P(a draw with the row link broken matches or beats the candidate),
            # +1/+1 so a zero count reports the resolution of the run, not 0.
            "p_value": round((float((a >= point["rho"]).sum()) + 1) / (len(a) + 1), 4),
        }
        # The SAME permuted fits, read on the AUC leg. Not a second experiment: one
        # set of row-link-broken draws answers both instruments, which is also why
        # the two p-values are not independent and must not be combined.
        b = np.array(adraws)
        if len(b) > 2 and point["auc_contrib"] is not None:
            out["permutation_null_auc_contrib"] = {
                "draws": int(len(b)),
                "mean": round(float(b.mean()), 5),
                "sd": round(float(b.std(ddof=1)), 5),
                "p95": round(float(np.percentile(b, 95)), 5),
                "p_value": round((float((b >= point["auc_contrib"]).sum()) + 1)
                                 / (len(b) + 1), 4),
                "shares_draws_with": "permutation_null (rho); the two p are not independent",
            }
    return out


# --------------------------------------------------------------------- verdict
def two_metric_verdict(delta, floors, holm_survives=None, tag=""):
    """THE CONJUNCTION RULE, coded once. EFV_GATE_STANDARD section 3.

    `delta`  a gate() delta dict. Needs "rho"; reads "block_rho", "auc_contrib"
             and "auc_star" when present.
    `floors` {"rho": .., "block_rho": .., "auc_contrib": ..}, MDE95 ONE-SIDED,
             derived in the SAME run on the SAME frame. A constant lifted out of a
             document is not a floor for this frame: every published AUC floor in
             the standard is a MODEL-VS-CONSENSUS margin, and this lab measures a
             FEATURE-ADD delta, which is a different statistic class.

             A MISSING FLOOR IS NOT A WAIVER. Pass None for a leg whose floor was
             not derived, and that leg is UNADJUDICATED rather than neutral: a
             missing contributor-AUC floor DISARMS the co-primary veto, so the arm
             was decided on rank alone and the verdict says exactly that
             (NOT_ADJUDICATED_NO_AUC_FLOOR). This branch used to emit "PASS", which
             is the most dangerous shape a gate can have: an absence of evidence
             wearing the string a cleared gate wears. It is reachable today, because
             data/xfv_driver_floors.json (generated 2026-08-14T22:39:54Z, re-read
             this session) carries MDE95_pooled_rho and MDE95_block_rho only.
    `holm_survives`
             True, False or None. None is NOT "no correction needed": an arm that
             would otherwise pass and was never handed a family decision reads
             NOT_ADJUDICATED_NO_HOLM. Holm is a FAMILY correction, so it cannot
             exist inside a per-arm loop; modes measure every arm first and form
             verdicts afterwards through apply_holm_verdicts().

    The rule, in one sentence each:
      - rho is the gate. An arm that does not clear the rho floor is a NULL.
      - contributor AUC is CO-PRIMARY and it VETOES: an arm that clears rho but
        loses on AUC beyond the AUC floor is a FAIL, because it bought its rank
        with discrimination it does not have.
      - contributor AUC NEVER CREDITS. An arm that fails rho and clears AUC is a
        NULL BY RULE, reported as NULL_AUC_ONLY so the reading is on the record
        rather than lost. The AUC cells flatter this model more than the rank
        cells do, and the most flattering cell of all (full-pool debut / no-debut)
        is the one the carve-out already ruled inadmissible after six archetype
        arms read as wins there while rank was flat or negative.
      - star AUC is a sensitivity. It gets a row and no verdict, at any sign, at
        any magnitude.
      - AN ABSENCE IS NOT A DECISION. Three states say the rule COULD NOT BE
        APPLIED rather than what it decided: NOT_ADJUDICATED_NO_RHO_FLOOR,
        NOT_ADJUDICATED_NO_AUC_FLOOR and NOT_ADJUDICATED_NO_HOLM. None of the
        three is a pass, none is a null, and none may ever collapse into "PASS".
        `not_adjudicated` in the output lists every input that was missing.
    """
    def _leg(key):
        d = delta.get(key)
        f = (floors or {}).get(key)
        if d is None:
            return {"delta": None, "floor": f, "state": "not measured"}
        if not f:
            return {"delta": d, "floor": None, "state": "no floor derived"}
        return {"delta": d, "floor": round(float(f), 4),
                "x_floor": round(abs(d) / float(f), 3),
                "clears": bool(d >= float(f)),
                "adverse_beyond_floor": bool(d <= -float(f)),
                "state": ("clears" if d >= float(f)
                          else "adverse beyond floor" if d <= -float(f) else "inside floor")}

    rho = _leg("rho")
    blk = _leg("block_rho")
    aucc = _leg("auc_contrib")
    rho_clears = bool(rho.get("clears"))
    auc_clears = bool(aucc.get("clears"))
    auc_veto = bool(aucc.get("adverse_beyond_floor"))
    UNMEASURED = ("no floor derived", "not measured")
    # Every input this verdict needed and did not get. A PASS is only a PASS when the
    # list is empty, and the list ships in the output so the gap is on the record
    # instead of being recoverable only by reading this function.
    missing = []
    if aucc["state"] in UNMEASURED:
        missing.append("contributor AUC: " + aucc["state"])
    if holm_survives is None:
        missing.append("Holm family survival: not supplied")

    if rho["state"] in UNMEASURED:
        # NOT a null. An arm whose rho floor was never derived on this frame has not
        # been adjudicated at all, and saying "null" would bank an unmeasured result.
        verdict = "NOT_ADJUDICATED_NO_RHO_FLOOR"
    elif not rho_clears:
        # rho is the gate and it failed. That is a DECISION, not an absence, whatever
        # the other legs did or could not do.
        verdict = "NULL_AUC_ONLY" if auc_clears else "NULL"
    elif auc_veto:
        verdict = "VETO_ON_AUC"
    elif holm_survives is False:
        # Also a decision: the family correction killed it. A missing AUC floor cannot
        # rescue an arm here, because contributor AUC may never credit.
        verdict = "NULL_HOLM"
    elif aucc["state"] in UNMEASURED:
        # THE CO-PRIMARY VETO WAS NEVER ARMED. rho cleared alone and nothing could have
        # vetoed it, because the AUC leg had no floor (or no delta) on this frame. An
        # absence of evidence on the second metric must never be spelled the way a
        # cleared gate is spelled, so it gets its own verdict and never collapses
        # into PASS.
        verdict = "NOT_ADJUDICATED_NO_AUC_FLOOR"
    elif holm_survives is None:
        # The family correction never reached this verdict. Same class of hole: the
        # arm was not adjudicated against its family, so it did not pass.
        verdict = "NOT_ADJUDICATED_NO_HOLM"
    else:
        verdict = "PASS"

    out = {
        "tag": tag,
        "verdict": verdict,
        "rho": rho, "block_rho": blk, "auc_contributor": aucc,
        "auc_star": {"delta": delta.get("auc_star"),
                     "role": "LABELLED SENSITIVITY",
                     "verdict_weight": 0,
                     "why": ("the pitcher star cell carries 46 positives against an "
                             "E_cond floor of 0.0397 in data/xfv_auc_floor_eval.json; "
                             "a leg that cannot resolve its own null cannot adjudicate "
                             "anyone else's arm")},
        "holm_survives": holm_survives,
        "holm_state": ("survives the family correction" if holm_survives is True
                       else "does NOT survive the family correction"
                       if holm_survives is False
                       else "NOT SUPPLIED: no family correction reached this verdict"),
        "not_adjudicated": missing,
        "block_sign_agrees_with_rho": (
            None if (rho["delta"] is None or blk["delta"] is None)
            else bool((rho["delta"] >= 0) == (blk["delta"] >= 0))),
        "rule": ("rho is the gate; contributor AUC may veto and may never credit; "
                 "star AUC carries no verdict weight"),
    }
    if verdict == "NULL_AUC_ONLY":
        out["note"] = ("AUC cleared its floor and rho did not. This is a NULL BY RULE, "
                       "not a win and not a partial win. Recorded because the reading "
                       "is evidence about the arm, and because six archetype arms in "
                       "the 2026-07-25 program would have shipped on exactly this "
                       "signature.")
    if verdict == "VETO_ON_AUC":
        out["note"] = ("rho cleared its floor and contributor AUC is adverse beyond its "
                       "own floor. The AUC leg vetoes: the arm reorders the board "
                       "without discriminating the outcome it claims to predict.")
    if verdict == "NOT_ADJUDICATED_NO_AUC_FLOOR":
        out["note"] = ("rho cleared its floor and the CO-PRIMARY COULD NOT BE "
                       "ADJUDICATED: no contributor-AUC floor was derived on this "
                       "frame, so the veto was never armed and this arm was decided on "
                       "rank ALONE. NOT a pass. Derive the floor on this frame "
                       "(`python tools/efv_driver_lab.py floor`, or read A1 out of "
                       "`auc` mode) and re-form the verdict. Never substitute a "
                       "published constant: every published AUC floor in the standard "
                       "is a model-vs-consensus margin, a different statistic class.")
    if verdict == "NOT_ADJUDICATED_NO_HOLM":
        out["note"] = ("rho cleared its floor and NO HOLM FAMILY DECISION reached this "
                       "verdict, so the multiplicity correction this arm shares with "
                       "its family was computed for someone and never applied to it. "
                       "NOT a pass. A mode must build the jointly sized family first "
                       "and form its verdicts through apply_holm_verdicts().")
    return out


def holm_family(rows):
    """Holm-Bonferroni, one-sided normal approximation, over a family sized by the
    rows PASSED IN. rows = [(key, delta, sd)].

    Sizing is the whole point and it is why this exists as a function. When the AUC
    leg is entered as a co-primary the family is BOTH legs of every arm, so m
    doubles and the step-1 alpha halves. Entering a second instrument for free
    would be running the family twice and reporting whichever half won."""
    from math import erfc, sqrt
    live = [[k, d, sd, d / sd, 0.5 * erfc((d / sd) / sqrt(2))]
            for k, d, sd in rows if sd and d is not None]
    live.sort(key=lambda r: r[4])
    m, still, out = len(live), True, {}
    for i, r in enumerate(live):
        alpha = 0.05 / (m - i)
        surv = bool(still and r[4] <= alpha)
        if not surv:
            still = False
        out[r[0]] = {"delta": round(r[1], 5), "sd": round(r[2], 5), "z": round(r[3], 3),
                     "p_one_sided": round(r[4], 5), "rank": i + 1,
                     "holm_alpha": round(alpha, 5), "survives_holm": surv}
    return out, m


def apply_holm_verdicts(arms, holm_joint, tag_prefix=""):
    """SECOND PASS. Form the stored verdict for every arm once the family exists.

    Holm is a family correction: it is not defined until every arm in the family has
    run, so a verdict formed inside the per-arm measuring loop cannot have consulted
    it. Before this function existed both driver modes called two_metric_verdict()
    inside the loop with holm_survives at its default and built holm_joint AFTERWARDS,
    so the correction was computed and then never read by any verdict any arm carried.

    This is the ONLY place a mode writes g["verdict"]. Each arm is handed the survival
    flag of its OWN rho leg out of the JOINTLY sized family (EFV_GATE_STANDARD section
    3.1 rule 3: m counts both legs of every arm, so entering the AUC leg doubles the
    family rather than buying a second attempt). An arm with no row in that family
    gets holm_survives=None, which two_metric_verdict() reads as
    NOT_ADJUDICATED_NO_HOLM and never as a pass.

    `arms` rows must carry "floors_used", written by the loop that measured them, so
    the floors a verdict is formed against are the ones that arm was measured against.
    """
    for key, g in arms.items():
        row = (holm_joint or {}).get(f"{key}.rho")
        g["holm_joint_row"] = f"{key}.rho" if row is not None else None
        g["verdict"] = two_metric_verdict(
            g["delta"], g.get("floors_used") or {},
            holm_survives=(None if row is None else bool(row.get("survives_holm"))),
            tag=f"{tag_prefix}{key}")
    return {k: g["verdict"]["verdict"] for k, g in arms.items()}


# --------------------------------------------------------------------- live
def live_move(side: str, extras, ex_idx, base_ex=()):
    """Bound the SERVED move a candidate would cause, on the live scoring pool.

    The col_x_k lesson (efv_model.py:351-358) is that a sparse mostly-zero gated
    column standardizes against a near-degenerate distribution and hands
    thin-sample players extreme LIVE boosts, which no OOS rank metric on a
    debuted pool can see. So the production stack is fit twice on the full
    training pool and both fits score the live matrix.

    Served eFV is a function of rank_war's ORDER, so the reported bound is rank
    movement first and the WAR delta second.
    """
    from efv_dataset import matrix_path
    train_raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    live_path = DATA / ("xfv_live_hitter_matrix.json" if side == "hit"
                        else "xfv_live_pitcher_matrix.json")
    live_raw = json.loads(live_path.read_text(encoding="utf-8"))
    is_pit = side == "pit"
    pool = [r for r in train_raw if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    tr = E._prep(pool, "target_censored", side)
    by_key_tr = {r["player_key"]: r for r in pool}
    keys, _m = E._feature_spec(side)
    lam = E.blend_lambda(side)

    def _cols(prep_rows, raw_map):
        cols = []
        for spec in extras:
            vals, obs = [], []
            for r in prep_rows:
                v = spec["get"](raw_map.get(r["player_key"], {}), r["feats"])
                obs.append(v is not None)
                vals.append(float(v) if v is not None else math.nan)
            v = np.array(vals, dtype=float)
            o = np.array(obs, dtype=bool)
            fill = 0.0 if spec.get("impute", "zero") == "zero" else (
                float(v[o].mean()) if o.any() else 0.0)
            v[~o] = fill
            cols.append(v)
        return (np.array(cols).T if cols else np.zeros((len(prep_rows), 0)))

    Xtr = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in tr], dtype=float)
    Etr = _cols(tr, by_key_tr)
    ytr = np.array([r["target"] for r in tr], dtype=float)
    wtr = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in tr]), 1e-3, None)
    fvtr = np.array([r["fv"] for r in tr], dtype=float)

    # Live rows carry no target, so _prep (which drops target-less rows) cannot be
    # used here; the feature side is built directly the way efv_score.run_live does.
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
    by_key_lv = {r["player_key"]: r for r in live_rows}
    Elv = _cols([{"player_key": r["player_key"], "feats": f}
                 for r, f in zip(live_rows, live_feats)], by_key_lv)
    live_fv = np.array(live_fv, dtype=float)

    def _score(ex):
        Xa = np.hstack([Xtr, Etr[:, list(ex)]]) if len(ex) else Xtr
        Xb = np.hstack([Xlv, Elv[:, list(ex)]]) if len(ex) else Xlv
        rg = M.ridge_fit(Xa, ytr, wtr)
        o = M.ols_fit(fvtr, ytr)
        raw_tr = M.ridge_pred(rg, Xa)
        cal = E._fit_linear_calibration(list(zip(raw_tr.tolist(), ytr.tolist())))
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        mod = np.maximum(-2.0, a + b * M.ridge_pred(rg, Xb))
        cons = np.maximum(0.0, o[0] + o[1] * live_fv)
        return (1 - lam) * cons + lam * mod

    s0 = _score(base_ex)
    s1 = _score(ex_idx)
    r0 = M._rankavg(s0)
    r1 = M._rankavg(s1)
    d = s1 - s0
    shift = np.abs(r1 - r0)
    order = np.argsort(-shift)[:10]
    return {
        "side": side, "n_live": int(len(s0)),
        "rank_spearman_old_new": round(float(M.wrho(s0, s1)), 5),
        "max_abs_rank_shift": int(shift.max()),
        "p99_abs_rank_shift": int(np.percentile(shift, 99)),
        "median_abs_rank_shift": float(np.median(shift)),
        "max_abs_war_delta": round(float(np.abs(d).max()), 4),
        "p99_abs_war_delta": round(float(np.percentile(np.abs(d), 99)), 4),
        "top_movers": [{"player_key": live_rows[i]["player_key"],
                        "fv": round(float(live_fv[i]), 1),
                        "rank_shift": int(shift[i]),
                        "war_delta": round(float(d[i]), 3)} for i in order],
    }


def _write(name: str, obj: dict):
    p = DATA / name
    obj.setdefault("generated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    obj.setdefault("produced_by", "tools/efv_driver_lab.py")
    p.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    print("wrote", p)


# --------------------------------------------------------------------- column getters
def get_milb(key, default=None):
    def _g(raw, feats):
        m = raw.get("milb") or {}
        v = m.get(key)
        return None if v is None else float(v)
    return _g


def get_expr(fn):
    def _g(raw, feats):
        return fn(raw, feats)
    return _g


def _thr(v, t):
    return 1.0 if (v is not None and v >= t) else 0.0


# --------------------------------------------------------------------- modes
def floor_mode(B=2000):
    """Re-derive the FEATURE-ADD and LAMBDA-SHIFT floors on the current basis.

    A feature-add floor is the sampling sd of (statistic with one more column)
    minus (statistic without it) under the paired bootstrap. Measured with a
    pure-noise column: N(0,1), seeded, zero information by construction, so the
    point delta is also the zero-information control for the whole statistic
    class. Three independent noise seeds per side bound the stability of the floor
    itself.

    FOUR floors now come out of the same noise arms, not two: pooled rho, side
    block-rho, contributor AUC and star AUC. They are derived from the SAME draws,
    which is what makes the conjunction rule readable; and they are derived HERE,
    on this frame, because every AUC floor published in EFV_GATE_STANDARD is a
    model-vs-consensus margin on a different statistic class. Quoting one of those
    at a feature add is the section 1a-vs-3 error this lab exists to stop.
    """
    out = {"purpose": ("feature-add and lambda-shift MDE95 on the 11-fold pair-weighted "
                       "basis. The registered 0.017 hit / 0.016 pit feature-add floor and "
                       "the 0.0076-0.011 / 0.005-0.008 lambda floors are 4-fold-basis "
                       "numbers (EFV_GATE_STANDARD.md section 1b) and must not be used to "
                       "gate an 11-fold result. The two AUC floors are feature-add floors "
                       "too: the AUC numbers in EFV_GATE_STANDARD section 7 and in "
                       "data/xfv_auc_floor_eval.json are model-vs-consensus margins on a "
                       "different frame and must not be used to gate a driver arm."),
           "basis": {"scored_years": list(E.SCORED_YEARS),
                     "lambda": {s: E.blend_lambda(s) for s in SIDES}},
           "protocol": ("paired bootstrap, train AND test resampled together, ridge and "
                        "consensus OLS refit on every draw, baseline and candidate scored "
                        "on identical rows. MDE95 one-sided = 1.645 sd."),
           "B": int(B), "seed": SEED, "feature_add": {}, "lambda_shift": {}}
    for side in SIDES:
        D = load_pool(side)
        n = D["n"]
        out["feature_add"][side] = {}
        for k, s in enumerate((0, 1, 2)):
            rng = np.random.default_rng(SEED + 1000 + s)
            noise = rng.standard_normal(n)
            D2 = dict(D)
            D2["EX"] = noise[:, None]
            D2["ex_names"] = [f"noise{s}"]
            D2["cov"] = {}
            g = gate(D2, cand_ex=(0,), B=B, n_perm=0, tag=f"{side}:noise{s}")
            out["feature_add"][side][f"noise_seed_{s}"] = {
                "point_rho": g["delta"]["rho"], "point_block": g["delta"]["block_rho"],
                "point_auc_contrib": g["delta"]["auc_contrib"],
                "point_auc_star": g["delta"]["auc_star"],
                "rho": g["bootstrap"]["rho"], "block_rho": g["bootstrap"]["block_rho"],
                "auc_contrib": g["bootstrap"]["auc_contrib"],
                "auc_star": g["bootstrap"]["auc_star"],
                "fold_rho_wins": g["fold_rho_wins"], "folds": g["folds_scored"],
                "fold_auc_wins": g["fold_auc_wins"], "auc_folds": g["fold_auc_scored"],
                "auc_prevalence": {"contributor": g["auc_leg"]["prevalence_contributor"],
                                   "star": g["auc_leg"]["prevalence_star"],
                                   "n_pos_contributor": g["auc_leg"]["n_pos_contributor"],
                                   "n_pos_star": g["auc_leg"]["n_pos_star"]},
            }
        arms = [v for k, v in out["feature_add"][side].items()
                if k.startswith("noise_seed_")]
        for stat, label in (("rho", "MDE95_pooled_rho"), ("block_rho", "MDE95_block_rho"),
                            ("auc_contrib", "MDE95_auc_contributor"),
                            ("auc_star", "MDE95_auc_star")):
            sds = [a[stat]["sd"] for a in arms if a[stat].get("sd") is not None]
            out["feature_add"][side][label] = round(1.645 * max(sds), 4) if sds else None
        out["feature_add"][side]["note"] = ("MDE95 quoted at the MAX of three noise seeds: "
                                            "the floor is a bound, so the conservative seed "
                                            "is the one that binds.")
        out["feature_add"][side]["auc_note"] = (
            "MDE95_auc_contributor is the CO-PRIMARY floor and it may veto, never credit. "
            "MDE95_auc_star is derived so the sensitivity row can be READ against "
            "something, and it is not a pass bar: no arm passes or fails on star AUC.")

        # lambda shift: the smallest move the pins could make and be seen.
        base = E.blend_lambda(side)
        out["lambda_shift"][side] = {"base_lambda": base}
        for step in (0.05, 0.10):
            g = gate(D, cand_ex=(), base_ex=(), B=B, n_perm=0,
                     lam=base + step, base_lam=base, tag=f"{side}:lam+{step}")
            out["lambda_shift"][side][f"plus_{step}"] = {
                "point_rho": g["delta"]["rho"], "rho": g["bootstrap"]["rho"]}
    _write("xfv_driver_floors.json", out)
    print(json.dumps({s: {"feature_add_MDE95_rho": out["feature_add"][s]["MDE95_pooled_rho"],
                          "feature_add_MDE95_block": out["feature_add"][s]["MDE95_block_rho"],
                          "feature_add_MDE95_auc_contributor":
                              out["feature_add"][s]["MDE95_auc_contributor"],
                          "feature_add_MDE95_auc_star_SENSITIVITY_ONLY":
                              out["feature_add"][s]["MDE95_auc_star"]}
                      for s in SIDES}, indent=1))
    return out


def sb_mode(B=2000):
    """C1a: sb_rate_rel, the pre-authorized re-test.

    The 2026-08-05 run (docs/efv-sb-athleticism-2026-08-05) measured +0.0076 at
    0.45x the then-current 0.017 floor on the RETIRED 4-fold basis and no-shipped
    it. This is the same column on the 11-fold basis, which is the only condition
    under which the arm was re-opened.
    """
    extras = [{"name": "sb_rate_rel", "get": get_milb("sb_rate_rel"), "impute": "zero"}]
    D = load_pool("hit", extras)
    rng = np.random.default_rng(SEED + 99)
    D2 = with_permuted(D, "sb_rate_rel", rng)
    g = gate(D2, cand_ex=(0,), ctrl_ex=(1,), B=B, n_perm=200,
             perm_col="sb_rate_rel", tag="C1a:sb_rate_rel:hit")
    g["live"] = live_move("hit", extras, (0,))
    g["prior_run"] = {"doc": "docs/efv-sb-athleticism-2026-08-05/RESULTS.md",
                      "basis": "4-fold unweighted, n 353",
                      "delta_rho": 0.0076, "x_floor_then": 0.45,
                      "verdict_then": "NO-SHIP (sub-floor null)"}
    _write("xfv_driver_sb_rate.json", g)
    print(json.dumps({k: g[k] for k in ("delta", "control_delta", "fold_rho_wins",
                                        "folds_scored", "permutation_null")}, indent=1))
    print(json.dumps(g["bootstrap"], indent=1))
    return g


def pos_mode():
    """C1b: the positions_played census coverage check.

    This is a PRECONDITION test, not a gate. POS_PREMIUM_USES_OBSERVED is blocked
    by a leak-shaped coverage split (definition correlated with the label), and
    the block lifts only if the rebuilt census closes the debuted-minus-bust gap.
    If it has not, the consumers stay gated and no fit is run: gating a feature
    whose definition still tracks the label would be measuring the leak.
    """
    import fielding_positions as FP
    from efv_dataset import matrix_path
    obs = FP.load_observed_positions(DATA / "positions_played.json")
    out = {"census": {"path": "data/positions_played.json",
                      "players": len(obs),
                      "mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime((DATA / "positions_played.json").stat().st_mtime))},
           "coverage": {}}
    seasons = DATA / "positions_played_seasons.json"
    if seasons.exists():
        out["census"]["seasons_sidecar"] = {
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seasons.stat().st_mtime)),
            "bytes": seasons.stat().st_size}
    raw = json.loads(matrix_path("hit").read_text(encoding="utf-8"))
    groups = {"all": raw,
              "debuted": [r for r in raw if r["kind"] == "debuted"],
              "bust": [r for r in raw if r["kind"] == "bust"]}
    for g, rows in groups.items():
        cov = sum(1 for r in rows if obs.get(r["player_key"]))
        out["coverage"][g] = {"n": len(rows), "covered": cov,
                              "frac": round(cov / len(rows), 4) if rows else None}
    live = json.loads((DATA / "xfv_live_hitter_matrix.json").read_text(encoding="utf-8"))
    livehit = [r for r in live if not r.get("is_pitcher")]
    cov = sum(1 for r in livehit if obs.get(r["player_key"]))
    out["coverage"]["live"] = {"n": len(livehit), "covered": cov,
                               "frac": round(cov / len(livehit), 4) if livehit else None}
    d = out["coverage"]["debuted"]["frac"]
    b = out["coverage"]["bust"]["frac"]
    out["label_gap"] = {"debuted_minus_bust": round(d - b, 4),
                        "prior_2026_07_30": {"train": 0.318, "debuted": 0.051, "bust": 0.527,
                                             "live": 0.930}}
    # what the flip would change, on rows where the observation exists
    flips = {"gain": 0, "lose": 0, "same": 0}
    for r in raw:
        p_obs = obs.get(r["player_key"])
        if not p_obs:
            continue
        a = E._pos_premium(r.get("position"), "hit")
        b2 = E._pos_premium(p_obs, "hit")
        flips["gain" if b2 > a else "lose" if b2 < a else "same"] += 1
    out["flip_counts_train"] = flips

    # THE ROUTE THE PLAN ASSUMED WAS ALREADY WIRED. data/positions_played_seasons.json
    # is the leak-free rebuild (league-wide, per-season, no debut filter) but
    # efv_model._observed_pos_map reads the OLD career-to-date positions_played.json,
    # so the flag is still gated on the artifact whose coverage is 5.1% on debuted
    # rows. Measure what the as-of route would actually deliver, here, rather than
    # quoting docs/efv-2026-07-30/POSITION_CENSUS_ASOF.md section 4.
    census = FP.load_season_census()
    bind = json.loads((DATA / "fielding_census_ids.json").read_text(encoding="utf-8"))
    mlbam_by_key, asof_by_key = {}, {}
    for r in raw:
        pk = r["player_key"]
        mid = (bind.get("matrix", {}).get(pk) or {}).get("mlbam") or r.get("mlbam_id")
        if mid:
            mlbam_by_key[pk] = int(mid)
        if r.get("asof_date"):
            asof_by_key[pk] = r["asof_date"]
    asof_obs = FP.observed_positions_as_of(census, asof_by_key, mlbam_by_key)
    asof_cov = {}
    for g, rows in groups.items():
        cov = sum(1 for r in rows if asof_obs.get(r["player_key"]))
        idc = sum(1 for r in rows if mlbam_by_key.get(r["player_key"]))
        asof_cov[g] = {"n": len(rows), "covered": cov,
                       "frac": round(cov / len(rows), 4) if rows else None,
                       "id_resolved": idc,
                       "frac_of_id_resolved": round(
                           sum(1 for r in rows if asof_obs.get(r["player_key"]))
                           / idc, 4) if idc else None}
    out["asof_route"] = {
        "census": "data/positions_played_seasons.json via fielding_positions.observed_positions_as_of",
        "id_bindings": "data/fielding_census_ids.json (census-scoped, not a global id override)",
        "coverage": asof_cov,
        "label_gap_debuted_minus_bust": round(
            asof_cov["debuted"]["frac"] - asof_cov["bust"]["frac"], 4),
        "label_gap_conditional_on_id": round(
            (asof_cov["debuted"]["frac_of_id_resolved"] or 0)
            - (asof_cov["bust"]["frac_of_id_resolved"] or 0), 4),
        "consumer_today": ("efv_model._observed_pos_map reads data/positions_played.json, "
                           "the OLD career-to-date pre-debut artifact; the as-of census is "
                           "not wired into the model at all"),
    }
    afl = {"gain": 0, "lose": 0, "same": 0}
    for r in raw:
        p_obs = asof_obs.get(r["player_key"])
        if not p_obs:
            continue
        a = E._pos_premium(r.get("position"), "hit")
        b2 = E._pos_premium(p_obs, "hit")
        afl["gain" if b2 > a else "lose" if b2 < a else "same"] += 1
    out["asof_route"]["flip_counts_train"] = afl
    _write("xfv_driver_pos_census.json", out)
    print(json.dumps(out, indent=1))
    return out


# --------------------------------------------------------------------- handedness
def hand_build():
    """C2 sidecar: batSide / pitchHand for every matrix row carrying an mlbam id.

    StatsAPI /people accepts a personIds batch and answers for minor leaguers,
    which the sports/1/players season roster used by hitter_export/pal_export
    does NOT (it is the MLB roster for one season and would miss every prospect
    who never debuted). Written once to data/xfv_handedness.json and read from
    disk thereafter: the gate must be re-runnable without the network.
    """
    import feed_cache
    from efv_dataset import matrix_path
    ids = set()
    srcs = [matrix_path("hit"), matrix_path("pit"),
            DATA / "xfv_live_hitter_matrix.json", DATA / "xfv_live_pitcher_matrix.json"]
    for p in srcs:
        for r in json.loads(p.read_text(encoding="utf-8")):
            if r.get("mlbam_id"):
                ids.add(int(r["mlbam_id"]))
    ids = sorted(ids)
    print(f"{len(ids)} distinct mlbam ids across 4 matrices")
    out = {}
    CH = 250
    for i in range(0, len(ids), CH):
        batch = ids[i:i + CH]
        r = feed_cache.SESSION.get("https://statsapi.mlb.com/api/v1/people",
                                   params={"personIds": ",".join(str(x) for x in batch)},
                                   timeout=60)
        r.raise_for_status()
        for p in r.json().get("people", []):
            pid = p.get("id")
            if pid is None:
                continue
            out[str(int(pid))] = {
                "bats": (p.get("batSide") or {}).get("code"),
                "throws": (p.get("pitchHand") or {}).get("code"),
            }
        print(f"  {min(i+CH, len(ids))}/{len(ids)} resolved={len(out)}", flush=True)
        time.sleep(0.3)
    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "produced_by": "tools/efv_driver_lab.py handbuild",
               "source": "statsapi /api/v1/people?personIds= (batch 250)",
               "purpose": ("handedness IDENTITY join for the C2 gate. NOT platoon-split "
                           "production, which is a banned feature family (W-PLATOON)."),
               "n_ids_requested": len(ids), "n_resolved": len(out),
               "codes": {"bats": {}, "throws": {}},
               "people": out}
    for k in ("bats", "throws"):
        for v in out.values():
            c = v.get(k) or "none"
            payload["codes"][k][c] = payload["codes"][k].get(c, 0) + 1
    HAND_SIDECAR.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("wrote", HAND_SIDECAR, payload["codes"])
    return payload


def _hand_map():
    d = json.loads(HAND_SIDECAR.read_text(encoding="utf-8"))
    return d["people"], d


def hand_mode(B=2000):
    """C2 gate. Pitcher is_lhp first (owner default (a)), hitter bats-side second.

    STOP CLAUSE, pre-registered: mlbam-id coverage is 54-62% on train rows against
    99.3-99.6% live and it correlates with bust status, so the arm FAILS if the
    indicator's information reduces to id-missingness. The operational test is the
    id-missingness twin: a 0/1 column that fires exactly where the handedness
    column was imputed, scored the same way. If the twin scores as well as the
    candidate, the candidate is measuring who has an id.
    """
    people, meta = _hand_map()

    def bats(code):
        def _g(raw, feats):
            mid = raw.get("mlbam_id")
            if mid is None:
                return None
            p = people.get(str(int(mid)))
            if not p or not p.get("bats"):
                return None
            return 1.0 if p["bats"] == code else 0.0
        return _g

    def is_lhp(raw, feats):
        mid = raw.get("mlbam_id")
        if mid is None:
            return None
        p = people.get(str(int(mid)))
        if not p or not p.get("throws"):
            return None
        return 1.0 if p["throws"] == "L" else 0.0

    def id_missing(raw, feats):
        mid = raw.get("mlbam_id")
        ok = mid is not None and (people.get(str(int(mid))) or {}).get("throws" if raw.get("is_pitcher") else "bats")
        return 0.0 if ok else 1.0

    res = {"stop_clause": ("neutral imputation, NO missing indicator; the arm FAILS if the "
                           "id-missingness twin reproduces the candidate's margin"),
           "sidecar": {k: meta[k] for k in ("generated_at", "n_ids_requested",
                                            "n_resolved", "codes")},
           "arms": {}}

    # arm (a): pitcher is_lhp
    ex_p = [{"name": "is_lhp", "get": is_lhp, "impute": "mean"},
            {"name": "id_missing", "get": id_missing, "impute": "zero"}]
    Dp = load_pool("pit", ex_p)
    rng = np.random.default_rng(SEED + 11)
    Dp2 = with_permuted(Dp, "is_lhp", rng)
    g = gate(Dp2, cand_ex=(0,), ctrl_ex=(2,), B=B, n_perm=200,
             perm_col="is_lhp", tag="C2a:is_lhp:pit")
    gm = gate(Dp, cand_ex=(1,), B=max(200, B // 4), n_perm=0, tag="C2a:id_missing_twin:pit")
    g["id_missingness_twin"] = {"delta": gm["delta"], "bootstrap_rho": gm["bootstrap"]["rho"]}
    g["live"] = live_move("pit", ex_p[:1], (0,))
    res["arms"]["a_is_lhp_pit"] = g

    # arm (b): hitter bats side, L and S indicators (R is the reference level)
    ex_h = [{"name": "bats_l", "get": bats("L"), "impute": "mean"},
            {"name": "bats_s", "get": bats("S"), "impute": "mean"},
            {"name": "id_missing", "get": id_missing, "impute": "zero"}]
    Dh = load_pool("hit", ex_h)
    rng = np.random.default_rng(SEED + 12)
    Dh2 = with_permuted(Dh, "bats_l", rng)
    gh = gate(Dh2, cand_ex=(0, 1), ctrl_ex=(3, 1), B=B, n_perm=200,
              perm_col="bats_l", tag="C2b:bats_side:hit")
    ghm = gate(Dh, cand_ex=(2,), B=max(200, B // 4), n_perm=0, tag="C2b:id_missing_twin:hit")
    gh["id_missingness_twin"] = {"delta": ghm["delta"], "bootstrap_rho": ghm["bootstrap"]["rho"]}
    gh["live"] = live_move("hit", ex_h[:2], (0, 1))
    res["arms"]["b_bats_side_hit"] = gh

    _write("xfv_driver_handedness.json", res)
    for k, v in res["arms"].items():
        print(k, json.dumps({"delta": v["delta"], "control": v["control_delta"],
                             "twin": v["id_missingness_twin"]["delta"],
                             "folds": f"{v['fold_rho_wins']}/{v['folds_scored']}",
                             "mde": v["bootstrap"]["rho"]["mde95_onesided"],
                             "perm_p": (v.get("permutation_null") or {}).get("p_value")}))
    return res


# --------------------------------------------------------------------- gated pairs
_PAIRS = [
    # (id, side, name, getter, rationale). Registered BEFORE any fit; five arms,
    # no post-hoc additions, no threshold search.
    ("P1", "hit", "pwr60_x_contact",
     lambda raw, f: _thr(raw.get("tool_game_pwr"), 60) * (-f.get("k_rel", 0.0)),
     "power at or above 60 crossed with contact (negated strikeout rate)"),
    ("P2", "hit", "hit60_x_obp",
     lambda raw, f: _thr(raw.get("tool_hit"), 60) * f.get("obp_rel", 0.0),
     "hit tool at or above 60 crossed with on-base skill"),
    ("P3", "hit", "pwr60_x_hit55",
     lambda raw, f: _thr(raw.get("tool_game_pwr"), 60) * _thr(raw.get("tool_hit"), 55),
     "the two-way bat: power 60+ AND hit 55+"),
    ("P4", "pit", "fb60_x_k",
     lambda raw, f: _thr(raw.get("tool_fb"), 60) * f.get("k_rel", 0.0),
     "fastball at or above 60 crossed with strikeout rate"),
    ("P5", "pit", "fb60_x_cmd55",
     lambda raw, f: _thr(raw.get("tool_fb"), 60) * _thr(raw.get("tool_cmd"), 55),
     "velocity with command: fastball 60+ AND command 55+"),
]


def pairs_mode(B=1000):
    """C3: pre-registered threshold interactions, with the MANDATORY live clause.

    The col_x_k reversion is the precedent: a sparse gated column can win on the
    debuted OOS pool and still be unshippable, because standardizing a mostly-zero
    column against its own near-degenerate sd hands thin-sample players extreme
    live boosts. So every arm reports its live rank movement whether or not it
    clears the rank gate, and a live blow-up is disqualifying on its own.
    """
    out = {"registration": ("five threshold interactions, fixed before any fit; no "
                            "threshold search, no post-hoc arms"),
           "live_clause": ("mandatory: the served-move bound is reported for every arm "
                           "and a live blow-up disqualifies regardless of rank"),
           "arms": {}}
    for pid, side, name, fn, why in _PAIRS:
        extras = [{"name": name, "get": get_expr(fn), "impute": "zero"}]
        D = load_pool(side, extras)
        col = D["EX"][:, 0]
        rng = np.random.default_rng(SEED + hash(pid) % 1000)
        D2 = with_permuted(D, name, rng)
        g = gate(D2, cand_ex=(0,), ctrl_ex=(1,), B=B, n_perm=200,
                 perm_col=name, tag=f"C3:{pid}:{name}:{side}")
        g["rationale"] = why
        g["column"] = {"nonzero": int((col != 0).sum()), "n": int(len(col)),
                       "frac_nonzero": round(float((col != 0).mean()), 4),
                       "mean": round(float(col.mean()), 5),
                       "sd": round(float(col.std()), 5)}
        g["live"] = live_move(side, extras, (0,))
        out["arms"][pid] = g
        print(pid, name, side, json.dumps(
            {"delta": g["delta"], "ctrl": g["control_delta"],
             "folds": f"{g['fold_rho_wins']}/{g['folds_scored']}",
             "mde": g["bootstrap"]["rho"]["mde95_onesided"],
             "nonzero": g["column"]["frac_nonzero"],
             "live_max_rank_shift": g["live"]["max_abs_rank_shift"],
             "live_rho": g["live"]["rank_spearman_old_new"]}), flush=True)
    _write("xfv_driver_gated_pairs.json", out)
    return out


# --------------------------------------------------------------------- elite band
def elite_mode(B=1000):
    """C4: the two elite-conviction arms, both pre-registered as probably
    unresolvable (FV>=55 is 105 hit / 59 pit matrix rows).

    (a) a lambda band RAISE restricted to FV>=55 (negative dip = more model trust
        where the owner's conviction ask lives)
    (b) an elite-cohort-RESTRICTED eval: train on everything, score only FV>=55,
        which is the read that answers "does the model order the top tier"

    Monotone tail transforms are NOT here and must not be added: they are
    committed losses AND Spearman is invariant to them by construction, so they
    cannot move this gate in either direction.
    """
    out = {"registration": ("both arms pre-registered as probably unresolvable; the "
                            "FV>=55 band is smaller than the t45 cohort whose floors "
                            "are already 0.055 hit / 0.10 pit"),
           "banned": "no monotone tail transform (committed loss; Spearman-invariant)",
           "arms": {}}
    for side in SIDES:
        D = load_pool(side)
        base = E.blend_lambda(side)
        n_elite = int((D["fv"] >= 55).sum())
        out["arms"].setdefault(side, {})["pool"] = {
            "n": D["n"], "n_fv55plus": n_elite,
            "base_lambda": base,
        }
        # (a) band raise
        for dip in (-0.20, -0.40):
            room = (base * (1 - dip))
            g = gate(D, cand_ex=(), base_ex=(), B=B, n_perm=0,
                     lam_band={"band": [55.0, 100.0], "dip": dip}, base_lam=base,
                     tag=f"C4a:{side}:band55_dip{dip}")
            g["effective_lambda_in_band"] = round(min(room, 1.0), 4)
            out["arms"][side][f"a_band_raise_dip{dip}"] = {
                "delta": g["delta"], "bootstrap": g["bootstrap"],
                "fold_rho_wins": g["fold_rho_wins"], "folds": g["folds_scored"],
                "effective_lambda_in_band": g["effective_lambda_in_band"]}
        # (b) elite-restricted eval of the model against consensus
        r = chain(D, fv_min=55.0)
        if r is None:
            out["arms"][side]["b_elite_eval"] = {"error": "no fold survived at fv_min 55"}
            continue
        s = side_stats(r)
        rng = np.random.default_rng(SEED + 31)
        draws = []
        for _ in range(B):
            sel = rng.integers(0, D["n"], D["n"])
            rr = chain(D, sel=sel, fv_min=55.0)
            if rr is None:
                continue
            ss = side_stats(rr)
            d = ss["rho"] - ss["cons_rho"]
            if np.isfinite(d):
                draws.append(d)
        a = np.array(draws)
        sd = float(a.std(ddof=1))
        out["arms"][side]["b_elite_eval"] = {
            "n_scored": s["n"],
            "consensus_rho": round(s["cons_rho"], 5), "blend_rho": round(s["rho"], 5),
            "delta": round(s["rho"] - s["cons_rho"], 5),
            "sd": round(sd, 5), "mde95_onesided": round(1.645 * sd, 4),
            "resolvable": bool(abs(s["rho"] - s["cons_rho"]) >= 1.645 * sd),
            "B_used": int(len(a)),
            "note": ("model-vs-consensus inside the elite band; compare to the 0.0440 hit / "
                     "0.0436 pit full-pool floor to see what restricting the pool costs"),
        }
        print(side, json.dumps(out["arms"][side]["b_elite_eval"]))
    _write("xfv_driver_elite_band.json", out)
    return out


# --------------------------------------------------------------------- lambda
def lam_mode(B=1000):
    """C5: lambda re-sweep per side on the 11-fold weighted basis.

    The reopening rule is written into efv_model.py:480-483: a pin moves only on a
    value that clears a freshly measured lambda-shift MDE95 on pooled rho. So the
    floor is measured in the same run as the sweep, from the same bootstrap, and
    the churn cost is quoted beside any candidate move.
    """
    out = {"reopening_rule": "efv_model.py:480-483 (pins move only on a floor-clearing win)",
           "sides": {}}
    grid = [0.35, 0.40, 0.45, 0.50, 0.55, 0.57, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    for side in SIDES:
        D = load_pool(side)
        base = E.blend_lambda(side)
        curve = {}
        for L in grid:
            r = chain(D, lam=L)
            s = side_stats(r)
            curve[f"{L:.2f}"] = {"rho": round(s["rho"], 5),
                                 "block_rho": round(s["block_rho"], 5)}
        best = max(curve, key=lambda k: curve[k]["rho"])
        g = gate(D, cand_ex=(), base_ex=(), B=B, n_perm=0,
                 lam=float(best), base_lam=base, tag=f"C5:{side}:lam{best}")
        out["sides"][side] = {
            "base_lambda": base, "curve": curve, "argmax_lambda": float(best),
            "argmax_minus_base": g["delta"],
            "bootstrap": g["bootstrap"],
            "band_span_rho": round(max(v["rho"] for v in curve.values())
                                   - min(v["rho"] for v in curve.values()), 5),
        }
        print(side, "base", base, "argmax", best,
              "delta", g["delta"], "mde95", g["bootstrap"]["rho"]["mde95_onesided"])
    _write("xfv_driver_lambda_sweep.json", out)
    return out


# --------------------------------------------------------------------- wRC+
def extras_census_mode(_B=0):
    """D-2 STEP 0: the coverage census, run BEFORE any arm and committed.

    WHY THIS EXISTS AND WHY IT IS ITS OWN STEP. The registered pitcher-stuff
    gate returned delta EXACTLY 0.0 on all three ship conditions because
    `train_covered_rows_all_folds` was 0: with no covered TRAINING rows the
    candidate arm is identical to the baseline BY CONSTRUCTION, and a reader
    could log "stuff does not predict" as a measured result. This mode prints
    the number that would have made that impossible, per fold, per side.

    Writes data/xfv_driver_extras_census.json (outside the eval glob).
    """
    import sqlite3
    from efv_dataset import matrix_path
    TOOLS = {"hit": ("hit", "game_pwr", "raw_pwr", "speed", "field", "throw"),
             "pit": ("fb", "cmd", "sl", "cb", "ch")}
    FIELDS = ["risk", "sits", "tops", "rpm_fb", "rpm_break", "height", "weight",
              "eta_year", "levers", "athl", "frame", "perf", "sign_market", "bonus"]
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    snaps = {}
    for pk, sd, tj in con.execute(
            "select player_key, snapshot_date, tools_json from snapshots "
            "where source='fangraphs' and tools_json is not null"):
        snaps.setdefault(pk, []).append((sd, tj))
    for pk in snaps:
        snaps[pk].sort()

    out = {"gate": "docs/efv-2026-08-14/EXTRAS_DRIVER_GATE.md", "lane": "D-2",
           "source": "snapshots.tools_json._extras, source='fangraphs'",
           "sides": {}}
    for side in SIDES:
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        prep = E._prep([r for r in rows if r["kind"] == "debuted"],
                       "target_censored", side)
        gaps, fieldcov = {}, {f: 0 for f in FIELDS}
        for r in prep:
            cand = [(sd, tj) for sd, tj in snaps.get(r["player_key"], [])
                    if int(sd[:4]) <= r["decision_year"]]
            r["_cov"] = bool(cand)
            r["_gap"] = None
            if not cand:
                continue
            t = json.loads(cand[-1][1])
            ex = t.get("_extras") or {}
            p = ex.get("present") or {}
            pairs = [(t[k], p[k]) for k in TOOLS[side]
                     if t.get(k) is not None and p.get(k) is not None]
            if pairs:
                r["_gap"] = sum(f - pr for f, pr in pairs) / len(pairs)
                gaps[r["player_key"]] = r["_gap"]
            for f in FIELDS:
                if ex.get(f) not in (None, "", {}):
                    fieldcov[f] += 1
        n = len(prep)
        folds = []
        for Y in E.SCORED_YEARS:
            tr = [r for r in prep if r["decision_year"] < Y]
            te = [r for r in prep if r["decision_year"] == Y]
            if len(te) < 15 or len(tr) < 60:
                continue
            folds.append({"test_year": Y, "n_train": len(tr),
                          "train_covered": sum(r["_cov"] for r in tr),
                          "n_test": len(te),
                          "test_covered": sum(r["_cov"] for r in te)})
        trainable = [f["test_year"] for f in folds if f["train_covered"] >= 40]
        vals = list(gaps.values())
        out["sides"][side] = {
            "n_train_rows": n,
            "any_predecision_snapshot": sum(r["_cov"] for r in prep),
            "gap_computable": len(vals),
            "gap_coverage": round(len(vals) / n, 4),
            "gap_mean": round(sum(vals) / len(vals), 4) if vals else None,
            "gap_sd": round((sum((v - sum(vals) / len(vals)) ** 2
                                 for v in vals) / len(vals)) ** 0.5, 4) if vals else None,
            "field_coverage": {f: round(c / n, 4) for f, c in fieldcov.items()},
            "folds": folds,
            "folds_with_zero_trainable_coverage":
                [f["test_year"] for f in folds if f["train_covered"] == 0],
            "first_trainable_fold_ge40": trainable[0] if trainable else None,
            "admissible_scored_years": trainable,
        }
        print(f"=== {side} n={n} gap on {len(vals)} ({len(vals)/n:.3f}) ===")
        for f in folds:
            tag = "  ZERO TRAINABLE COVERAGE" if f["train_covered"] == 0 else ""
            print(f"   {f['test_year']}  train {f['n_train']:>4} cov {f['train_covered']:>4}"
                  f"   test {f['n_test']:>4} cov {f['test_covered']:>4}{tag}")
        print(f"   admissible scored years: {trainable}")
    (DATA / "xfv_driver_extras_census.json").write_text(json.dumps(out, indent=1),
                                                        encoding="utf-8")
    print("\nwrote data/xfv_driver_extras_census.json")
    return out


EXTRAS_YEARS = (2019, 2020, 2021, 2022, 2023, 2024)


def _extras_join(side):
    """{player_key: parsed _extras} from the newest PRE-DECISION FanGraphs
    snapshot, keyed to each matrix row's own decision year."""
    import sqlite3
    from efv_dataset import matrix_path
    TOOLS = {"hit": ("hit", "game_pwr", "raw_pwr", "speed", "field", "throw"),
             "pit": ("fb", "cmd", "sl", "cb", "ch")}[side]
    RISK = {"low": 0.0, "med": 1.0, "medium": 1.0, "high": 2.0}

    def _num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def _velo(x):
        if x is None:
            return None
        s = str(x)
        if "-" in s:
            a, b = s.split("-", 1)
            a, b = _num(a), _num(b)
            return None if (a is None or b is None) else (a + b) / 2.0
        return _num(s)

    def _height(x):
        # "6' 1" -> 73.0 inches
        if not x:
            return None
        s = str(x).replace('"', "").strip()
        if "'" not in s:
            return _num(s)
        ft, _, inch = s.partition("'")
        ft, inch = _num(ft), _num(inch.strip() or 0)
        return None if ft is None else ft * 12.0 + (inch or 0.0)

    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    snaps = {}
    for pk, sd, tj in con.execute(
            "select player_key, snapshot_date, tools_json from snapshots "
            "where source='fangraphs' and tools_json is not null"):
        snaps.setdefault(pk, []).append((sd, tj))
    for pk in snaps:
        snaps[pk].sort()

    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    prep = E._prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    out = {}
    for r in prep:
        dy = r["decision_year"]
        cand = [(sd, tj) for sd, tj in snaps.get(r["player_key"], []) if int(sd[:4]) <= dy]
        if not cand:
            continue
        t = json.loads(cand[-1][1])
        ex = t.get("_extras") or {}
        p = ex.get("present") or {}
        pairs = [(t[k], p[k]) for k in TOOLS
                 if t.get(k) is not None and p.get(k) is not None]
        rpm = _num(ex.get("rpm_fb"))
        out[r["player_key"]] = {
            # THE HEADLINE: how much growth the scout projects, in grade points.
            "tool_gap": (sum(f - pr for f, pr in pairs) / len(pairs)) if pairs else None,
            "risk_ord": RISK.get(str(ex.get("risk") or "").strip().lower()),
            "height_in": _height(ex.get("height")),
            "weight": _num(ex.get("weight")),
            # proximity, not a calendar year: a raw year would be collinear with
            # the fold index, which is the C1 defect in another costume.
            "eta_delta": (None if ex.get("eta_year") is None
                          else _num(ex["eta_year"]) - dy),
            "sits_mid": _velo(ex.get("sits")),
            "tops": _velo(ex.get("tops")),
            # C2: a literal 0 is MISSING spin, not zero spin.
            "rpm_fb": (None if (rpm is None or rpm == 0) else rpm),
        }
    return out


def extras_mode(B=2000):
    """D-2: the _extras drivers, on the SIX-fold frame the census allows.

    Gate docs/efv-2026-08-14/EXTRAS_DRIVER_GATE.md. The 11-fold floors are
    forbidden here by name (C0); this mode derives its own on EXTRAS_YEARS.
    """
    ARMS = {"hit": ["tool_gap", "risk_ord", "height_in", "weight", "eta_delta"],
            "pit": ["tool_gap", "risk_ord", "height_in", "weight", "eta_delta",
                    "sits_mid", "tops", "rpm_fb"]}
    out = {"gate": "docs/efv-2026-08-14/EXTRAS_DRIVER_GATE.md", "lane": "D-2",
           "B": B, "seed": SEED, "scored_years": list(EXTRAS_YEARS),
           "frame_note": ("SIX folds, not eleven. Four folds have ZERO trainable "
                          "coverage and would contribute a by-construction zero; "
                          "see data/xfv_driver_extras_census.json."),
           "floors": {}, "arms": {}, "skipped": {}}

    for side in SIDES:
        join = _extras_join(side)
        # ── C0: the floor, derived HERE on the reduced frame, 3 noise seeds.
        noise = []
        for s in range(3):
            rng = np.random.default_rng(SEED + 4400 + s)
            D = load_pool(side, [{"name": "noise",
                                  "get": (lambda r, f, _r=rng: float(_r.normal())),
                                  "impute": "zero"}])
            g = gate(D, cand_ex=(0,), B=B, n_perm=0, tag=f"D-2:noise{s}:{side}",
                     years=EXTRAS_YEARS)
            noise.append({"seed": s, "point_rho": g["delta"]["rho"],
                          "mde95": g["bootstrap"]["rho"]["mde95_onesided"],
                          "point_auc_contrib": g["delta"]["auc_contrib"],
                          "mde95_auc_contrib":
                              g["bootstrap"]["auc_contrib"]["mde95_onesided"],
                          "point_auc_star": g["delta"]["auc_star"],
                          "mde95_auc_star": g["bootstrap"]["auc_star"]["mde95_onesided"]})
            print(f"  [floor] {side} noise{s} point {g['delta']['rho']:+.5f} "
                  f"mde95 {g['bootstrap']['rho']['mde95_onesided']}  "
                  f"auc {g['delta']['auc_contrib']:+.5f} "
                  f"mde95 {g['bootstrap']['auc_contrib']['mde95_onesided']}", flush=True)
        floor = max(n["mde95"] for n in noise)
        floor_auc = max(n["mde95_auc_contrib"] for n in noise)
        floor_auc_star = max(n["mde95_auc_star"] for n in noise)
        out["floors"][side] = {"MDE95_pooled_rho": floor,
                               "MDE95_auc_contributor": floor_auc,
                               "MDE95_auc_star": floor_auc_star,
                               "noise_arms": noise,
                               "convention": "MAX of three noise seeds; a floor is a bound",
                               "auc_star_note": ("derived for READING the sensitivity row; "
                                                 "it is not a pass bar and no arm is "
                                                 "adjudicated on it")}

        for i, key in enumerate(ARMS[side]):
            def _get(raw, feats, _k=key, _j=join):
                v = _j.get(raw.get("player_key"), {}).get(_k)
                return None if v is None else float(v)
            D = load_pool(side, [{"name": key, "get": _get, "impute": "zero"}])
            cov = D["cov"][key]
            if cov["observed"] < 100 or not cov["observed_sd"]:
                out["skipped"][f"{side}.{key}"] = (
                    f"coverage {cov['observed']} sd {cov['observed_sd']}")
                continue
            rng = np.random.default_rng(SEED + 4500 + 13 * i + (0 if side == "hit" else 1))
            D2 = with_permuted(D, key, rng)
            g = gate(D2, cand_ex=(0,), ctrl_ex=(1,), B=B, n_perm=200,
                     perm_col=key, tag=f"D-2:{key}:{side}", years=EXTRAS_YEARS)
            g["coverage"] = cov
            g["floor_rho"] = floor
            g["floor_auc_contrib"] = floor_auc
            # MEASURE HERE, ADJUDICATE AFTER THE FAMILY EXISTS. The loop records the
            # floors this arm was measured against; apply_holm_verdicts() forms the
            # verdict below, once holm_joint is built.
            g["floors_used"] = {"rho": floor, "auc_contrib": floor_auc}
            out["arms"][f"{side}.{key}"] = g
            print(f"  {side}.{key:12s} d_rho {g['delta']['rho']:+.5f} "
                  f"d_block {g['delta']['block_rho']:+.5f} "
                  f"d_auc {g['delta']['auc_contrib']:+.5f} "
                  f"ctrl {g['control_delta']['rho']:+.5f} "
                  f"folds {g['fold_rho_wins']}/{g['folds_scored']} "
                  f"cov {cov['frac']} floor {floor}/{floor_auc} "
                  "verdict pending Holm", flush=True)

    fam = [(k, g["delta"]["rho"], g["bootstrap"]["rho"]["sd"])
           for k, g in out["arms"].items() if g["bootstrap"]["rho"].get("sd")]
    from math import erfc, sqrt
    rows_ = sorted(([k, d, sd, d / sd, 0.5 * erfc((d / sd) / sqrt(2))]
                    for k, d, sd in fam), key=lambda r: r[4])
    m, still, holm = len(rows_), True, {}
    for i, r in enumerate(rows_):
        alpha = 0.05 / (m - i)
        surv = bool(still and r[4] <= alpha)
        if not surv:
            still = False
        holm[r[0]] = {"d_rho": round(r[1], 5), "sd": round(r[2], 5), "z": round(r[3], 3),
                      "p_one_sided": round(r[4], 5), "rank": i + 1,
                      "holm_alpha": round(alpha, 5), "survives_holm": surv}
    out["holm"], out["holm_family_size"] = holm, m
    # The JOINT family: rho AND contributor AUC for every arm, sized over both legs.
    # The rho-only family above is kept UNCHANGED so the closed D-2 ledger stays
    # comparable; this block is the one the conjunction rule reads, and it is
    # bigger, which is the conservative direction.
    jrows = []
    for k, g in out["arms"].items():
        for leg, stat in (("rho", "rho"), ("auc_contrib", "auc_contrib")):
            b = (g.get("bootstrap") or {}).get(stat) or {}
            if b.get("sd"):
                jrows.append((f"{k}.{leg}", g["delta"][stat], b["sd"]))
    out["holm_joint"], out["holm_joint_family_size"] = holm_family(jrows)
    out["holm_joint_note"] = ("rho and contributor AUC legs pooled into ONE family. A "
                              "surviving AUC cell whose rho cell fails is still a NULL: "
                              "Holm survival is necessary, never sufficient, and the "
                              "conjunction rule outranks it.")
    # THE VERDICT PASS. Every verdict in this artifact is formed here, after the family
    # exists, so the stored verdict is the Holm-corrected one.
    out["verdicts"] = apply_holm_verdicts(out["arms"], out["holm_joint"], "D-2:")
    out["verdict_basis"] = ("formed by apply_holm_verdicts() AFTER holm_joint, each arm "
                            "on its own rho leg in the jointly sized family")
    out["n_arms"] = len(out["arms"])
    (DATA / "xfv_driver_extras.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote data/xfv_driver_extras.json  arms={out['n_arms']} "
          f"skipped={len(out['skipped'])} holm_family={m}")
    print("SURVIVES HOLM:", [k for k, h in holm.items() if h["survives_holm"]] or "NONE")
    print("VERDICTS (Holm-corrected):", json.dumps(out["verdicts"]))
    return out


def freekeys_mode(B=2000):
    """D-1: sweep the keys efv_model._vec ALREADY EMITS that neither feature
    list consumes. Gate docs/efv-2026-08-14/FREE_KEYS_SWEEP_GATE.md.

    Zero plumbing by construction: the candidate value is read straight out of
    the same `feats` dict the shipped ridge is built from, so nothing is joined,
    fetched or imputed from a new source. A key a side ALREADY ships is skipped
    rather than duplicated, and the skip is recorded.
    """
    CAND = {
        "both": ["fv_trend", "n_sources", "fv_stddev", "prod_trend", "pos_prem",
                 "pick_overall", "bonus_log", "il_stints_pre"],
        "hit": ["bb_rel", "tool_game_pwr", "tool_field", "peak_obp_rel", "iso_rel"],
        "pit": ["tool_cmd", "tool_sl", "tool_ch", "era_rel", "starter_shape",
                "arsenal_depth"],
    }
    # game_pwr for HITTERS is a REGISTERED REPEAT (efv_model.py:110-111,267-268):
    # its omission IS the power-overpricing correction and it has been rejected
    # three times. Clause D4.6 puts a 2x bar on it.
    REPEATS = {("hit", "tool_game_pwr"), ("hit", "iso_rel")}

    out = {"gate": "docs/efv-2026-08-14/FREE_KEYS_SWEEP_GATE.md", "lane": "D-1",
           "B": B, "seed": SEED, "arms": {}, "skipped": {}, "floors": {}}
    floors = json.loads((DATA / "xfv_driver_floors.json").read_text(encoding="utf-8"))
    for s in SIDES:
        fa = floors["feature_add"][s]
        # The floor is quoted at the MAX of three noise seeds by the producer's
        # own convention: a floor is a BOUND, so the conservative seed binds.
        out["floors"][s] = {
            "rho": fa["MDE95_pooled_rho"],
            "block": fa["MDE95_block_rho"],
            # None when the floors artifact predates the AUC leg, which is the state
            # on disk today. That does NOT leave the AUC row merely un-barred while
            # the arm passes on rank: with no bar the co-primary veto cannot fire, so
            # two_metric_verdict() returns NOT_ADJUDICATED_NO_AUC_FLOOR and the arm is
            # unadjudicated. Re-run `efv_driver_lab.py floor` to gate on AUC. Never
            # substitute a constant.
            "auc_contrib": fa.get("MDE95_auc_contributor"),
            "auc_star": fa.get("MDE95_auc_star"),
            "floors_generated_at": floors.get("generated_at"),
        }
        if fa.get("MDE95_auc_contributor") is None:
            out["floors"][s]["auc_floor_missing"] = (
                "data/xfv_driver_floors.json was produced before the AUC leg existed; "
                "re-run `python tools/efv_driver_lab.py floor 2000` before adjudicating "
                "any arm on AUC")
        out["floors"][s]["noise_band_rho"] = sorted(
            v["point_rho"] for v in fa.values()
            if isinstance(v, dict) and "point_rho" in v)

    for side in SIDES:
        shipped = set(E._feature_spec(side)[0])
        want = CAND["both"] + CAND[side]
        for i, key in enumerate(want):
            if key in shipped:
                out["skipped"][f"{side}.{key}"] = "already shipped on this side"
                continue
            def _get(raw, feats, _k=key):
                v = feats.get(_k)
                return None if v is None else float(v)
            try:
                D = load_pool(side, [{"name": key, "get": _get, "impute": "zero"}])
            except Exception as exc:                             # noqa: BLE001
                out["skipped"][f"{side}.{key}"] = f"pool build failed: {exc}"
                continue
            cov = D["cov"][key]
            if cov["observed"] == 0 or cov["observed_sd"] in (None, 0.0):
                out["skipped"][f"{side}.{key}"] = (
                    f"degenerate column: observed={cov['observed']} sd={cov['observed_sd']}")
                continue
            rng = np.random.default_rng(SEED + 900 + 17 * i + (0 if side == "hit" else 1))
            D2 = with_permuted(D, key, rng)
            g = gate(D2, cand_ex=(0,), ctrl_ex=(1,), B=B, n_perm=200,
                     perm_col=key, tag=f"D-1:{key}:{side}")
            g["coverage"] = cov
            g["registered_repeat"] = bool((side, key) in REPEATS)
            g["floor_rho"] = out["floors"][side]["rho"]
            g["floor_block"] = out["floors"][side]["block"]
            g["floor_auc_contrib"] = out["floors"][side]["auc_contrib"]
            # MEASURE HERE, ADJUDICATE AFTER THE FAMILY EXISTS. auc_contrib is None
            # whenever the floors artifact predates the AUC leg, which is the state on
            # disk today, and the verdict below reads that as
            # NOT_ADJUDICATED_NO_AUC_FLOOR rather than as a pass.
            g["floors_used"] = {"rho": g["floor_rho"], "block_rho": g["floor_block"],
                                "auc_contrib": g["floor_auc_contrib"]}
            out["arms"][f"{side}.{key}"] = g
            print(f"  {side}.{key:16s} d_rho {g['delta']['rho']:+.5f} "
                  f"d_block {g['delta']['block_rho']:+.5f} "
                  f"d_auc {g['delta']['auc_contrib']:+.5f} "
                  f"ctrl {g['control_delta']['rho']:+.5f} "
                  f"folds {g['fold_rho_wins']}/{g['folds_scored']} "
                  f"floor {g['floor_rho']} verdict pending Holm", flush=True)

    # D3 HOLM over the WHOLE family, both sides pooled into one family.
    fam = []
    for k, g in out["arms"].items():
        sd = ((g.get("bootstrap") or {}).get("rho") or {}).get("sd")
        if sd:
            fam.append((k, g["delta"]["rho"], sd))
    from math import erfc, sqrt
    rows = [[k, d, sd, d / sd, 0.5 * erfc((d / sd) / sqrt(2))] for k, d, sd in fam]
    rows.sort(key=lambda r: r[4])
    m = len(rows)
    still = True
    holm = {}
    for i, r in enumerate(rows):
        alpha = 0.05 / (m - i)
        surv = bool(still and r[4] <= alpha)
        if not surv:
            still = False
        holm[r[0]] = {"d_rho": round(r[1], 5), "sd": round(r[2], 5),
                      "z": round(r[3], 3), "p_one_sided": round(r[4], 5),
                      "rank": i + 1, "holm_alpha": round(alpha, 5),
                      "survives_holm": surv}
    out["holm_family_size"] = m
    out["holm"] = holm
    # JOINT family, both legs of every arm, both sides. The rho-only family above is
    # unchanged so the closed D-1 ledger stays comparable.
    jrows = []
    for k, g in out["arms"].items():
        for stat in ("rho", "auc_contrib"):
            b = (g.get("bootstrap") or {}).get(stat) or {}
            if b.get("sd"):
                jrows.append((f"{k}.{stat}", g["delta"][stat], b["sd"]))
    out["holm_joint"], out["holm_joint_family_size"] = holm_family(jrows)
    out["holm_joint_note"] = ("rho and contributor AUC legs pooled into ONE family. A "
                              "surviving AUC cell whose rho cell fails is still a NULL: "
                              "Holm survival is necessary, never sufficient, and the "
                              "conjunction rule outranks it.")
    # THE VERDICT PASS. Every verdict in this artifact is formed here, after the family
    # exists, so the stored verdict is the Holm-corrected one.
    out["verdicts"] = apply_holm_verdicts(out["arms"], out["holm_joint"], "D-1:")
    out["verdict_basis"] = ("formed by apply_holm_verdicts() AFTER holm_joint, each arm "
                            "on its own rho leg in the jointly sized family")
    out["n_arms"] = len(out["arms"])
    out["n_skipped"] = len(out["skipped"])
    (DATA / "xfv_driver_freekeys.json").write_text(json.dumps(out, indent=1),
                                                   encoding="utf-8")
    print(f"\nwrote data/xfv_driver_freekeys.json  arms={out['n_arms']} "
          f"skipped={out['n_skipped']} holm_family={m}")
    surv = [k for k, h in holm.items() if h["survives_holm"]]
    print("SURVIVES HOLM:", surv or "NONE")
    print("VERDICTS (Holm-corrected):", json.dumps(out["verdicts"]))
    return out


def auc_mode(B=2000, write=True):
    """A-CLAIM-11: prove the AUC leg before any arm is adjudicated on it.

    An instrument that has never been shown to return a null on a known-null input
    is not evidence, it is a number. So this mode runs the leg on inputs whose
    answer is known in advance and reports whether it gave that answer:

      A0  PARITY. The numpy `auc()` against source_backtest._auc, the function the
          served scoreboard calls, on the real scored frame at both bars. Exact to
          1e-12 or the leg is measuring a lookalike.
      A1  FLOORS. Three N(0,1) noise columns per side, the construction floor_mode
          already uses. Zero information by construction, so their point deltas are
          the zero-information control for the statistic class and the max of their
          bootstrap sds is the floor. Derived HERE, on this frame, every run.
      A2  ZERO-INFORMATION TWIN. A REAL column (`fv_trend`, a free key, no join and
          no network) row-permuted: identical marginal, row link destroyed. Its AUC
          delta must sit inside the A1 floor. This is the check the lane owes: a
          twin that cleared the floor would mean the floor is too small and every
          AUC verdict built on it is unsafe.
      A3  LABEL-PERMUTATION CENTRING AND WIDTH. Shuffle the WAR labels across the
          scored rows and read the model's contributor AUC over K = 2000 draws. The
          mean must sit within |z| <= 3 of 0.50 and the empirical sd within
          [0.90, 1.10] of the analytic Hanley-McNeil null SE. Both bars are
          two-sided, because a one-sided width check reads an over-wide null as
          PASS and over-wide is the permissive direction here. The frozen bar in
          tools/efv_auc_floor_lab.py, |AUC - 0.5| < 0.02 on ONE draw, is 0.84 null
          SE and fails a CORRECT implementation about 40% of the time.
      A4  RULE TABLE. two_metric_verdict() driven over the TEN corners the rule
          actually has, so it is readable as behaviour and not only as prose: SIX
          conjunction corners (rho clears with AUC concurring, silent or adverse;
          rho fails with AUC clearing or silent; star alone), THREE not-adjudicated
          corners (no rho floor, no contributor-AUC floor, no Holm decision) and
          the Holm corner itself. The count is checked against A4_expected, which
          carries the same ten keys, so a corner cannot be added without
          registering what it must return.

    What this mode does NOT do: adjudicate any driver arm, or claim the AUC leg has
    power. It measures the floor and shows the instrument returns nulls on nulls.
    """
    from source_backtest import _auc as SB_AUC
    out = {"lane": "A-CLAIM-11", "gate": "docs/EFV_GATE_STANDARD.md section 3",
           "B": int(B), "seed": SEED,
           "basis": {"scored_years": list(E.SCORED_YEARS),
                     "lambda": {s: E.blend_lambda(s) for s in SIDES},
                     "labels": {"contributor_war": CONTRIB_WAR, "star_war": STAR_WAR}},
           "A0_parity": {}, "A1_floors": {}, "A2_zero_information_twin": {},
           "A3_label_permutation": {}, "A4_rule_table": {}}

    # ── A0 parity, and the frame census that every later number is read against.
    for side in SIDES:
        D = load_pool(side)
        r = chain(D)
        _yr, _cons, blend, tgt, _w = r
        cell = {}
        for label, bar in (("contributor", CONTRIB_WAR), ("star", STAR_WAR)):
            lab = (tgt >= bar)
            mine = auc(blend, lab)
            theirs = SB_AUC(blend.tolist(), lab.tolist())
            cell[label] = {"n": int(len(tgt)), "n_pos": int(lab.sum()),
                           "prevalence": round(float(lab.mean()), 4),
                           "auc_numpy": round(float(mine), 8),
                           "auc_source_backtest": round(float(theirs), 8),
                           "abs_diff": float(abs(mine - theirs)),
                           "pass": bool(abs(mine - theirs) < 1e-12)}
        # A0b: one row per player, so the i.i.d. row bootstrap under the AUC leg is
        # not the anti-conservative resampling that section 7.6 caught on the
        # clustered head-to-head frame. Asserted, not assumed.
        cell["frame"] = {"pool_rows": D["n"], "unique_player_keys": len(set(D["pk"])),
                         "one_row_per_player": bool(len(set(D["pk"])) == D["n"])}
        out["A0_parity"][side] = cell
        print(f"A0 {side}: contrib n_pos {cell['contributor']['n_pos']} "
              f"auc {cell['contributor']['auc_numpy']:.6f} parity "
              f"{cell['contributor']['pass']}; star n_pos {cell['star']['n_pos']} "
              f"parity {cell['star']['pass']}", flush=True)

    # ── A1 floors from three noise seeds per side.
    for side in SIDES:
        D = load_pool(side)
        n = D["n"]
        arms = []
        for s in (0, 1, 2):
            rng = np.random.default_rng(SEED + 1000 + s)
            D2 = dict(D)
            D2["EX"] = rng.standard_normal(n)[:, None]
            D2["ex_names"] = [f"noise{s}"]
            D2["cov"] = {}
            g = gate(D2, cand_ex=(0,), B=B, n_perm=0, tag=f"A1:{side}:noise{s}")
            arms.append({"seed": s,
                         "point": {k: g["delta"][k] for k in GATE_KEYS},
                         "sd": {k: g["bootstrap"][k]["sd"] for k in GATE_KEYS},
                         "mde95": {k: g["bootstrap"][k]["mde95_onesided"]
                                   for k in GATE_KEYS}})
            print(f"A1 {side} noise{s}  d_rho {g['delta']['rho']:+.5f}  "
                  f"d_auc {g['delta']['auc_contrib']:+.5f}  "
                  f"mde95_auc {g['bootstrap']['auc_contrib']['mde95_onesided']}",
                  flush=True)
        floors = {k: round(max(a["mde95"][k] for a in arms), 4) for k in GATE_KEYS}
        inside = {k: all(abs(a["point"][k]) < floors[k] for a in arms) for k in GATE_KEYS}
        out["A1_floors"][side] = {
            "MDE95": floors, "noise_arms": arms,
            "convention": "MAX of three noise seeds, one-sided 1.645 sd; a floor is a bound",
            "noise_point_inside_own_floor": inside,
            "star_is_not_a_bar": ("MDE95.auc_star is derived so the sensitivity row can be "
                                  "read; no arm passes or fails on it"),
        }

    # ── A2 the zero-information twin, on a real column.
    TWIN_KEY = "fv_trend"
    for side in SIDES:
        def _get(raw, feats, _k=TWIN_KEY):
            v = feats.get(_k)
            return None if v is None else float(v)
        D = load_pool(side, [{"name": TWIN_KEY, "get": _get, "impute": "zero"}])
        rng = np.random.default_rng(SEED + 8800 + (0 if side == "hit" else 1))
        D2 = with_permuted(D, TWIN_KEY, rng)
        # index 1 is the PERMUTED column: the twin is the candidate here, not the
        # control. The real column is scored beside it so the pair is readable.
        gt = gate(D2, cand_ex=(1,), B=B, n_perm=0, tag=f"A2:{side}:{TWIN_KEY}__perm")
        gr = gate(D2, cand_ex=(0,), B=B, n_perm=0, tag=f"A2:{side}:{TWIN_KEY}")
        fl = out["A1_floors"][side]["MDE95"]
        v = two_metric_verdict(gt["delta"], {"rho": fl["rho"], "block_rho": fl["block_rho"],
                                             "auc_contrib": fl["auc_contrib"]},
                               tag=f"A2:{side}:twin")
        out["A2_zero_information_twin"][side] = {
            "column": TWIN_KEY,
            "coverage": D["cov"][TWIN_KEY],
            "twin_delta": gt["delta"],
            "twin_bootstrap_auc": gt["bootstrap"]["auc_contrib"],
            "real_column_delta": gr["delta"],
            "floors_used": fl,
            "twin_auc_inside_floor": bool(
                gt["delta"]["auc_contrib"] is not None
                and abs(gt["delta"]["auc_contrib"]) < fl["auc_contrib"]),
            "twin_rho_inside_floor": bool(
                gt["delta"]["rho"] is not None and abs(gt["delta"]["rho"]) < fl["rho"]),
            "twin_verdict": v,
            "reading": ("the twin must land INSIDE the floor on both legs. A twin that "
                        "cleared it would mean the floor is too small and every verdict "
                        "built on it is unsafe."),
        }
        print(f"A2 {side} twin d_auc {gt['delta']['auc_contrib']:+.5f} vs floor "
              f"{fl['auc_contrib']}  inside="
              f"{out['A2_zero_information_twin'][side]['twin_auc_inside_floor']}  "
              f"verdict {v['verdict']}", flush=True)

    # ── A3 label permutation: is the AUC null centred on 0.5, and is it as WIDE as
    # theory says. K = 2000, and the bar is |z| <= 3 two-sided on the mean.
    #
    # THE BAR WAS RE-SIZED ONCE, BEFORE ANY ARM RAN, AND HERE IS WHY. The first
    # specification was |mean - 0.5| < 2 SEM at K = 200. It FAILED on the hitter
    # side at z = 2.47. Re-measured at K = 4000 on three seeds the hitter mean sits
    # at |z| = 0.44 / 1.08 / 0.25 and the pitcher at 1.52 / 1.02 / 0.80, so the null
    # is centred and the K = 200 failure was the bar, not the instrument: a 2-SEM
    # two-sided bar false-fails 4.6% of the time per side by construction, which
    # over two sides and every future run manufactures failures. Sized at |z| <= 3
    # it false-fails 0.27% per side. The width check is two-sided on purpose
    # (EFV_GATE_STANDARD section 7.4: a one-sided coverage gate reads over-wide as
    # PASS, and over-wide is the permissive direction for a program whose product
    # is null verdicts).
    K_PERM = 2000
    for side in SIDES:
        D = load_pool(side)
        _yr, _cons, blend, tgt, _w = chain(D)
        lab = tgt >= CONTRIB_WAR
        n1 = int(lab.sum())
        n2 = int(len(lab) - n1)
        se = math.sqrt((n1 + n2 + 1) / (12.0 * n1 * n2))
        prng = np.random.default_rng(SEED + 4242)
        draws = np.array([auc(blend, lab[prng.permutation(len(lab))])
                          for _ in range(K_PERM)])
        mean = float(draws.mean())
        sd = float(draws.std(ddof=1))
        sem = sd / math.sqrt(len(draws))
        z = (mean - 0.5) / sem
        ratio = sd / se
        out["A3_label_permutation"][side] = {
            "draws": int(len(draws)), "mean_auc": round(mean, 6),
            "sd_auc": round(sd, 5),
            "analytic_null_se_hanley_mcneil": round(se, 5),
            "sd_over_analytic": round(ratio, 4),
            "z_of_mean": round(float(z), 3),
            "p05": round(float(np.percentile(draws, 5)), 5),
            "p95": round(float(np.percentile(draws, 95)), 5),
            "centred_on_half": bool(abs(z) <= 3.0),
            "width_matches_theory": bool(0.90 <= ratio <= 1.10),
            "bar": ("two-sided: |z of the mean| <= 3 over K = 2000 draws, AND empirical "
                    "sd within [0.90, 1.10] of the Hanley-McNeil analytic null SE"),
        }
        print(f"A3 {side} label-permuted AUC mean {mean:.6f} z {z:+.2f} "
              f"sd/analytic {ratio:.4f} "
              f"centred={out['A3_label_permutation'][side]['centred_on_half']} "
              f"width={out['A3_label_permutation'][side]['width_matches_theory']}",
              flush=True)

    # ── A4 the rule, driven as behaviour.
    F = {"rho": 0.020, "block_rho": 0.015, "auc_contrib": 0.020}
    for name, d in (
            ("rho_clears_auc_concurs", {"rho": 0.030, "block_rho": 0.020,
                                        "auc_contrib": 0.030, "auc_star": 0.090}),
            ("rho_clears_auc_silent", {"rho": 0.030, "block_rho": 0.020,
                                       "auc_contrib": 0.001, "auc_star": -0.090}),
            ("rho_clears_auc_adverse", {"rho": 0.030, "block_rho": 0.020,
                                        "auc_contrib": -0.030, "auc_star": 0.090}),
            ("rho_fails_auc_clears", {"rho": 0.005, "block_rho": 0.002,
                                      "auc_contrib": 0.050, "auc_star": 0.200}),
            ("rho_fails_auc_silent", {"rho": 0.005, "block_rho": 0.002,
                                      "auc_contrib": 0.001, "auc_star": 0.0}),
            ("star_alone_enormous", {"rho": 0.000, "block_rho": 0.000,
                                     "auc_contrib": 0.000, "auc_star": 0.400})):
        # holm_survives is stated EXPLICITLY so these six corners read the conjunction
        # rule and nothing else. The Holm corners are driven separately below.
        out["A4_rule_table"][name] = two_metric_verdict(
            d, F, holm_survives=True, tag=name)["verdict"]
    # The three NOT-ADJUDICATED corners. None of them may read as a null and none of
    # them may read as a pass: an arm nobody could adjudicate has not been adjudicated,
    # and the verdict string is the only place a reader learns which of the two it is.
    CLEARS = {"rho": 0.030, "block_rho": 0.020, "auc_contrib": 0.030}
    out["A4_rule_table"]["no_rho_floor_derived"] = two_metric_verdict(
        CLEARS, {"rho": None, "auc_contrib": 0.020},
        holm_survives=True, tag="no_rho_floor")["verdict"]
    # THE CORNER THAT IS REACHABLE TODAY. data/xfv_driver_floors.json was generated
    # 2026-08-14T22:39:54Z and carries MDE95_pooled_rho and MDE95_block_rho only, so
    # freekeys_mode hands the AUC leg a None floor on BOTH sides. Until this edit that
    # arm read "PASS": a disarmed co-primary veto wearing the string of a cleared gate.
    out["A4_rule_table"]["rho_clears_no_auc_floor"] = two_metric_verdict(
        CLEARS, {"rho": 0.020, "block_rho": 0.015, "auc_contrib": None},
        holm_survives=True, tag="no_auc_floor")["verdict"]
    out["A4_rule_table"]["rho_clears_holm_not_supplied"] = two_metric_verdict(
        CLEARS, F, tag="no_holm")["verdict"]
    # And the Holm corner itself, which is what makes the family correction visible in
    # a stored verdict rather than computed after the verdicts and discarded.
    out["A4_rule_table"]["rho_clears_holm_fails"] = two_metric_verdict(
        CLEARS, F, holm_survives=False, tag="holm_fails")["verdict"]
    out["A4_expected"] = {
        "rho_clears_auc_concurs": "PASS", "rho_clears_auc_silent": "PASS",
        "rho_clears_auc_adverse": "VETO_ON_AUC",
        "rho_fails_auc_clears": "NULL_AUC_ONLY", "rho_fails_auc_silent": "NULL",
        "star_alone_enormous": "NULL",
        "no_rho_floor_derived": "NOT_ADJUDICATED_NO_RHO_FLOOR",
        "rho_clears_no_auc_floor": "NOT_ADJUDICATED_NO_AUC_FLOOR",
        "rho_clears_holm_not_supplied": "NOT_ADJUDICATED_NO_HOLM",
        "rho_clears_holm_fails": "NULL_HOLM"}
    out["A4_pass"] = bool(out["A4_rule_table"] == out["A4_expected"])
    out["A4_corners"] = len(out["A4_expected"])
    # The invariant behind the whole table, asserted separately so it cannot be lost in
    # a future edit of the expected dict: no absence of evidence spells itself PASS.
    out["A4_absence_never_reads_as_pass"] = bool(all(
        out["A4_rule_table"][k] != "PASS" for k in
        ("no_rho_floor_derived", "rho_clears_no_auc_floor",
         "rho_clears_holm_not_supplied")))

    out["all_controls_pass"] = bool(
        all(c[lbl]["pass"] for c in out["A0_parity"].values()
            for lbl in ("contributor", "star"))
        and all(c["frame"]["one_row_per_player"] for c in out["A0_parity"].values())
        # A1: the noise arms carry zero information by construction, so every one of
        # their four point deltas has to land inside its own floor on both sides. It
        # was measured and reported from the first run and was NOT a conjunct, while
        # EFV_GATE_STANDARD section 3.1 asserted it in prose. A control the document
        # claims and the code does not check is not a control.
        and all(all(v["noise_point_inside_own_floor"].values())
                for v in out["A1_floors"].values())
        and all(v["twin_auc_inside_floor"] and v["twin_rho_inside_floor"]
                for v in out["A2_zero_information_twin"].values())
        and all(v["centred_on_half"] and v["width_matches_theory"]
                for v in out["A3_label_permutation"].values())
        and out["A4_pass"] and out["A4_absence_never_reads_as_pass"])
    if write:
        _write("xfv_driver_auc_floors.json", out)
    print("\nA4 rule table", json.dumps(out["A4_rule_table"]), "pass", out["A4_pass"])
    print("ALL CONTROLS PASS:", out["all_controls_pass"])
    for s in SIDES:
        print(f"  {s} floors {json.dumps(out['A1_floors'][s]['MDE95'])}")
    return out


def wrc_mode(B=1000):
    """C6: ONE re-run of the wRC+ A2 ADD arm on the 11-fold basis.

    The join, the imputation posture (0 for unjoined rows, ship-faithful because
    the shipped sibling rates are exactly 0 for a milb-missing player) and the
    a-priori null are the frozen tools/efv_wrc_lab.py protocol; only the fold
    basis and the uncertainty machinery change. The park-adjusted variant is NOT
    built: that layer is a measured M-FAIL.
    """
    import wrc_rates
    from efv_dataset import matrix_path
    idx, _lg = wrc_rates.build_index()
    mat = json.loads(matrix_path("hit").read_text(encoding="utf-8"))
    joined = {}
    for m in mat:
        milb = m.get("milb") or {}
        mid, ms, ml = m.get("mlbam_id"), milb.get("milb_season"), milb.get("milb_level")
        if mid is None or ms is None or ml is None:
            continue
        hit = idx.get((int(mid), int(ms), ml))
        if hit is not None:
            joined[m["player_key"]] = float(hit["wrc_rel"])

    def get_wrc(raw, feats):
        return joined.get(raw.get("player_key"))

    extras = [{"name": "wrc_rel", "get": get_wrc, "impute": "zero"}]
    D = load_pool("hit", extras)
    rng = np.random.default_rng(SEED + 61)
    D2 = with_permuted(D, "wrc_rel", rng)
    g = gate(D2, cand_ex=(0,), ctrl_ex=(1,), B=B, n_perm=200,
             perm_col="wrc_rel", tag="C6:wrc_rel_add:hit")
    g["protocol"] = {"frozen_source": "tools/efv_wrc_lab.py (A2 add arm)",
                     "join": "exact (mlbam_id, milb.milb_season, milb.milb_level)",
                     "impute": "0 for unjoined rows (ship-faithful)",
                     "a_priori_null": ("the decomposed k/bb/iso/obp/ops block already carries "
                                       "the linear-weight information"),
                     "attempts": "ONE. marginal = FAIL.",
                     "park_layer": "NOT built (W2 M-FAIL stands, wrc_rates.py:23)"}
    g["join_coverage"] = {"joined_matrix_rows": len(joined), "matrix_rows": len(mat)}
    _write("xfv_driver_wrc.json", g)
    print(json.dumps({k: g[k] for k in ("delta", "control_delta", "fold_rho_wins",
                                        "folds_scored", "permutation_null",
                                        "join_coverage")}, indent=1))
    print(json.dumps(g["bootstrap"], indent=1))
    return g


_MODES = {"floor": floor_mode, "sb": sb_mode, "pos": pos_mode,
          "handbuild": hand_build, "hand": hand_mode, "pairs": pairs_mode,
          "elite": elite_mode, "lam": lam_mode, "wrc": wrc_mode,
          "freekeys": freekeys_mode, "extras_census": extras_census_mode,
          "extras": extras_mode, "auc": auc_mode}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "floor"
    if mode not in _MODES:
        print("modes:", " | ".join(_MODES))
        sys.exit(1)
    t0 = time.time()
    fn = _MODES[mode]
    if mode in ("pos", "handbuild"):
        fn()
    else:
        fn(int(sys.argv[2]) if len(sys.argv) > 2
           else (2000 if mode in ("floor", "sb", "auc") else 1000))
    print("elapsed", round(time.time() - t0, 1), "s")
