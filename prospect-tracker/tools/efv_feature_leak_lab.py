# eFV feature-leak + as-of-anchor lab (LANE D wave 2, 2026-08-07b).
#
# REGISTRATION: docs/efv-2026-08-07b/FEATURE_LEAK_GATE.md, written in full (sections 0-4)
# BEFORE this file existed. Section 5 of that doc is the only part appended after a run.
#
# PART A. Does a shipped feature carry the debuted/bust label through GROUP SEPARATION?
#   The sharp instrument is PERMUTE-WITHIN-KIND: shuffling a column inside `debuted` and
#   inside `bust` separately destroys the individual signal while preserving the between
#   -group separation. A feature that keeps its accuracy under that permutation was
#   working through the label, not through the player.
#
# PART B. Is the AS-OF ANCHOR itself outcome-selected? decision_year is debut_year for
#   debuted rows and last_list_year + 1 for busts, so the cutoff that decides which MiLB
#   seasons a row may see is chosen BY THE LABEL. Part B measures the mechanism
#   descriptively and then re-anchors debuted rows onto the BUST rule (label-blind) and
#   scores the difference-in-differences against the debuted-only cut, which cannot host
#   a group-separation leak and is therefore the information-loss yardstick.
#
# READ-ONLY on efv_model.py and efv_dataset.py. The fit/metric primitives are IMPORTED
# from tools/efv_mde_lab.py, never reimplemented. The POOL loader is local (base_pool)
# rather than tools/efv_cohort_floor_lab.load_pool, because Part B has to build the same
# pool from MODIFIED rows and that loader only reads the matrix from disk; parity of the
# local loader against the shipped artifacts is asserted in `repro` mode.
#
# Run: python tools/efv_feature_leak_lab.py repro          parity, no writes
#      python tools/efv_feature_leak_lab.py desc           membership + Part B mechanism
#      python tools/efv_feature_leak_lab.py parta [B]      Part A arms + paired bootstrap
#      python tools/efv_feature_leak_lab.py partb [B]      Part B anchor arms + DiD
#      python tools/efv_feature_leak_lab.py all [B]        everything, writes the ledger
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np   # noqa: E402  after the thread-count pins, as in efv_mde_lab.py

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                                             # noqa: E402 read-only
import efv_dataset as DS                                          # noqa: E402 read-only
from efv_mde_lab import ridge_fit, ridge_pred, ols_fit, wrho      # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_feature_leak_eval.json"
GATE_DOC = "docs/efv-2026-08-07b/FEATURE_LEAK_GATE.md"
SEED = 20260807
SIDES = ("hit", "pit")
Z95_TWO = 1.96
R_PERM_POINT = 50            # permutations averaged for a permutation arm's POINT estimate
PRIMARY_FAMILY_M = 16        # section 1.3: 2 features x hit x 2 frames x 4 arms

# Section 1.2: the OLD bar, printed beside every contrast for continuity. NOT the bar.
LEGACY_MDE95 = {"hit": 0.044, "pit": 0.0436}     # data/xfv_mde_floor.json weighted, 1-sided

# Section 2.1 arm menu, per feature.
FULL_ARMS = ("A1_drop", "A2_perm_all", "A3_perm_within_kind",
             "A3b_perm_within_kind_year", "A4_kind_mean")
CONTROL_ARMS = ("A2_perm_all", "A3_perm_within_kind")

# feature -> (side, role, arms). Roles: primary | negative_control | instrument_control.
PART_A_PLAN = {
    "hit": [("n_milb_seasons", "primary", FULL_ARMS),
            ("milb_missing", "negative_control", FULL_ARMS),
            ("fv", "instrument_control", CONTROL_ARMS)],
    "pit": [("seasons_at_level", "primary_exploratory", FULL_ARMS),
            ("age", "small_weight_control", FULL_ARMS),
            ("fv", "instrument_control", CONTROL_ARMS)],
}


# --------------------------------------------------------------------- pools
def base_pool(side: str, rows=None) -> dict:
    """The FULL eval pool (debuted + busts minus recent busts) with a `deb` mask, so the
    debuted_km cut is a mask on the same array and a bootstrap draw pairs both cuts.

    Mirrors tools/efv_cohort_floor_lab.load_pool(side, 'full'); reproduced here only
    because Part B needs to build the same pool from MODIFIED rows.
    """
    if rows is None:
        from efv_dataset import matrix_path
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        rows = raw
    keep = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    prep = E._prep(keep, "target_censored", side)
    keys, _mono = E._feature_spec(side)
    return {
        "side": side, "keys": list(keys),
        "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "deb": np.array([r["kind"] == "debuted" for r in prep], dtype=bool),
        "lam": E.blend_lambda(side),
        "n": len(prep),
    }


def subset(D: dict, sel) -> dict:
    out = dict(D)
    for k in ("X", "y", "w", "fv", "dy", "deb"):
        out[k] = D[k][sel]
    out["n"] = len(out["y"])
    return out


# --------------------------------------------------------------------- one pass
def chain(D: dict, X=None, cut: str = "full"):
    """Forward-chained consensus + blend on one pool. Structurally identical to
    efv_mde_lab.chain / efv_cohort_floor_lab.chain; `X` overrides the design matrix and
    `cut` restricts BOTH train and test to debuted rows for the debuted_km frame."""
    X = D["X"] if X is None else X
    y, w, fv, dy, deb = D["y"], D["w"], D["fv"], D["dy"], D["deb"]
    if cut == "debuted":
        m = deb
        X, y, w, fv, dy = X[m], y[m], w[m], fv[m], dy[m]
    lam = D["lam"]
    C, B, T, W = [], [], [], []
    for yr in E.SCORED_YEARS:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fv[tr], y[tr])
        rg = ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        C.append(cons)
        B.append((1 - lam) * cons + lam * ridge_pred(rg, X[te]))
        T.append(y[te])
        W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (C, B, T, W))


def legs(r):
    if r is None:
        return None
    c, b, t, w = r
    return {"n": int(len(t)), "consensus": float(wrho(c, t, w)),
            "blend": float(wrho(b, t, w))}


# --------------------------------------------------------------------- Part A arms
def _perm_groups(groups, rng):
    """Permutation index that shuffles only WITHIN each group."""
    out = np.arange(len(groups))
    for g in np.unique(groups):
        idx = np.flatnonzero(groups == g)
        if len(idx) > 1:
            out[idx] = idx[rng.permutation(len(idx))]
    return out


def arm_X(D: dict, feat: str, arm: str, rng, cut: str = "full"):
    """Design matrix for one arm. Column edits are applied on the FULL pool rows so that
    within-kind permutation has both kinds available; the `cut` mask is applied later
    inside chain(). A4's within-kind means are computed on the rows being fit."""
    j = D["keys"].index(feat)
    X = D["X"]
    if arm == "A1_drop":
        return np.delete(X, j, axis=1)
    Xn = X.copy()
    col = Xn[:, j]
    deb = D["deb"]
    if arm == "A2_perm_all":
        Xn[:, j] = col[rng.permutation(len(col))]
    elif arm == "A3_perm_within_kind":
        Xn[:, j] = col[_perm_groups(deb.astype(int), rng)]
    elif arm == "A3b_perm_within_kind_year":
        g = deb.astype(np.int64) * 100000 + D["dy"].astype(np.int64)
        Xn[:, j] = col[_perm_groups(g, rng)]
    elif arm == "A4_kind_mean":
        v = col.copy()
        for m in (deb, ~deb):
            if m.sum() > 0:
                v[m] = float(col[m].mean())
        Xn[:, j] = v
    else:
        raise ValueError(arm)
    return Xn


def _arm_specs(side):
    out = []
    for feat, role, arms in PART_A_PLAN[side]:
        for a in arms:
            out.append((feat, role, a))
    return out


def part_a(B: int = 1000, verbose: bool = True):
    """Point estimates for every arm, then a paired bootstrap of every contrast."""
    rng = np.random.default_rng(SEED)
    res = {}
    for side in SIDES:
        D = base_pool(side)
        specs = _arm_specs(side)
        # ---- point estimates -------------------------------------------------
        point = {}
        for cut in ("full", "debuted"):
            base = legs(chain(D, None, cut))
            point[cut] = {"A0_shipped": base, "arms": {}}
            for feat, role, arm in specs:
                if arm == "A1_drop":
                    lg = legs(chain(D, arm_X(D, feat, arm, rng), cut))
                    spread = None
                elif arm == "A4_kind_mean" and cut == "debuted":
                    lg = legs(chain(D, arm_X(D, feat, arm, rng), cut))
                    spread = None
                else:
                    vals, lgs = [], []
                    reps = 1 if arm == "A4_kind_mean" else R_PERM_POINT
                    # deterministic stream id: Python's str hash is per-process
                    # randomized, so it must never seed a reproducible artifact.
                    sid = (FULL_ARMS.index(arm) + 1) * 101 + len(feat) * 7
                    for r in range(reps):
                        prng = np.random.default_rng(SEED + 977 * r + sid)
                        lg1 = legs(chain(D, arm_X(D, feat, arm, prng), cut))
                        lgs.append(lg1)
                        vals.append(lg1["blend"])
                    lg = {"n": lgs[0]["n"],
                          "consensus": lgs[0]["consensus"],
                          "blend": float(np.mean(vals))}
                    spread = {"perm_reps": reps, "blend_sd": float(np.std(vals, ddof=1))
                              if reps > 1 else 0.0,
                              "blend_min": float(np.min(vals)),
                              "blend_max": float(np.max(vals))}
                key = f"{feat}|{arm}"
                point[cut]["arms"][key] = {
                    "feature": feat, "role": role, "arm": arm,
                    "legs": lg, "perm_spread": spread,
                    "d_blend": lg["blend"] - base["blend"],
                    "d_margin": ((lg["blend"] - lg["consensus"])
                                 - (base["blend"] - base["consensus"])),
                }
                if verbose:
                    print(f"  [{side}/{cut}] {key:<44} blend {lg['blend']:.5f} "
                          f"d {lg['blend'] - base['blend']:+.5f}", flush=True)
        # ---- paired bootstrap ------------------------------------------------
        draws = {f"{cut}|{feat}|{arm}": []
                 for cut in ("full", "debuted") for feat, _r, arm in specs}
        t0 = time.time()
        used = 0
        for i in range(B):
            sel = rng.integers(0, D["n"], D["n"])
            S = subset(D, sel)
            ok = True
            for cut in ("full", "debuted"):
                base = chain(S, None, cut)
                if base is None:
                    ok = False
                    break
                b0 = wrho(base[1], base[2], base[3])
                for feat, _role, arm in specs:
                    r = chain(S, arm_X(S, feat, arm, rng), cut)
                    if r is None:
                        continue
                    draws[f"{cut}|{feat}|{arm}"].append(
                        float(wrho(r[1], r[2], r[3]) - b0))
            if ok:
                used += 1
            if verbose and (i + 1) % 100 == 0:
                print(f"    {side} boot {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
        # ---- summarise -------------------------------------------------------
        for cut in ("full", "debuted"):
            for feat, _role, arm in specs:
                a = np.array(draws[f"{cut}|{feat}|{arm}"], dtype=float)
                a = a[np.isfinite(a)]
                rec = point[cut]["arms"][f"{feat}|{arm}"]
                if len(a) < 20:
                    rec["boot"] = {"B_used": int(len(a)), "insufficient": True}
                    continue
                sd = float(a.std(ddof=1))
                p_raw = float(2 * min((a > 0).mean(), (a < 0).mean()))
                rec["boot"] = {
                    "B_used": int(len(a)),
                    "sd": sd,
                    "mde95_paired": Z95_TWO * sd,
                    "ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))],
                    "boot_mean_d": float(a.mean()),
                    "p_two_sided_raw": p_raw,
                    "p_bonferroni_m16": float(min(1.0, p_raw * PRIMARY_FAMILY_M)),
                    "resolvable_paired": bool(abs(rec["d_blend"]) >= Z95_TWO * sd),
                    "resolvable_legacy_floor": bool(abs(rec["d_blend"]) >= LEGACY_MDE95[side]),
                    "legacy_mde95_for_reference": LEGACY_MDE95[side],
                    "margin_over_paired_floor": (abs(rec["d_blend"]) / (Z95_TWO * sd)
                                                 if sd > 0 else None),
                }
        # self-check (standing rule E): the consensus leg depends only on `fv`, never on
        # the design matrix, so a feature arm must move the model-minus-consensus margin
        # by EXACTLY the amount it moves the blend rho. If this ever trips, every
        # "margin" sentence in the write-up is wrong.
        worst = 0.0
        for cut in ("full", "debuted"):
            for rec in point[cut]["arms"].values():
                worst = max(worst, abs(rec["d_blend"] - rec["d_margin"]))
        res[side] = {"n_pool": D["n"], "n_debuted": int(D["deb"].sum()),
                     "lambda": D["lam"], "B_used": used, "cuts": point,
                     "selfcheck_max_abs_d_blend_minus_d_margin": worst}
    return res


def verdict_part_a(res):
    """Section 2.3 registered verdicts, applied mechanically."""
    out = {}
    for side, R in res.items():
        for cut, P in R["cuts"].items():
            by_feat = {}
            for key, rec in P["arms"].items():
                by_feat.setdefault(rec["feature"], {})[rec["arm"]] = rec

            def _d(f, a):
                r = by_feat.get(f, {}).get(a)
                return None if r is None else r["d_blend"]

            def _m(f, a):
                r = by_feat.get(f, {}).get(a)
                b = (r or {}).get("boot") or {}
                return b.get("mde95_paired")

            for feat, arms in by_feat.items():
                have = set(arms)
                v = "NOT_EVALUATED"
                why = ""
                if {"A1_drop", "A2_perm_all", "A3_perm_within_kind"} <= have:
                    d1, d2, d3 = (_d(feat, "A1_drop"), _d(feat, "A2_perm_all"),
                                  _d(feat, "A3_perm_within_kind"))
                    m1, m2, m3 = (_m(feat, "A1_drop"), _m(feat, "A2_perm_all"),
                                  _m(feat, "A3_perm_within_kind"))
                    d3b, m3b = _d(feat, "A3b_perm_within_kind_year"), _m(feat, "A3b_perm_within_kind_year")
                    d4, m4 = _d(feat, "A4_kind_mean"), _m(feat, "A4_kind_mean")
                    if any(x is None for x in (d1, d2, d3, m1, m2, m3)):
                        out[f"{side}|{cut}|{feat}"] = {
                            "verdict": "NO_FLOOR",
                            "why": "bootstrap did not produce a paired floor for every arm"}
                        continue
                    inert = (abs(d1) < m1 and abs(d2) < m2 and abs(d3) < m3)
                    leak = (d3b is not None and d4 is not None
                            and abs(d3) < m3 and abs(d3b) < m3b
                            and d2 <= -m2 and abs(d4) < m4)
                    clean = d3 <= -m3
                    if leak:
                        v, why = "LEAK", "A3/A3b/A4 null, A2 negative"
                    elif clean:
                        v, why = "CLEAN", "A3 costs accuracy beyond its own floor"
                    elif inert:
                        v, why = "INERT", "A1/A2/A3 all inside their own floors"
                    else:
                        v, why = "AMBIGUOUS", "no registered pattern matched"
                elif {"A2_perm_all", "A3_perm_within_kind"} <= have:
                    d3, m3 = _d(feat, "A3_perm_within_kind"), _m(feat, "A3_perm_within_kind")
                    if d3 is None or m3 is None:
                        v, why = "NO_FLOOR", "bootstrap did not produce a paired floor"
                    else:
                        v = "SENSITIVE" if d3 <= -m3 else "NOT_SENSITIVE"
                        why = ("instrument-sensitivity control (A3 on `fv`): SENSITIVE means "
                               "the instrument can detect destroyed individual signal on "
                               "this cut. NOT_SENSITIVE means NO A3 result on this cut is "
                               "interpretable, per gate section 2.2.")
                out[f"{side}|{cut}|{feat}"] = {"verdict": v, "why": why}
    return out


# --------------------------------------------------------------------- Part B
def _first_season(decision_year: int, cutoff) -> int:
    """The loop bound efv_dataset._milb_features:717-722 actually uses. Copied, not
    called, because the builder does not expose it. Kept byte-faithful to the source."""
    fs = int(decision_year) - 1
    if cutoff:
        try:
            cy, cm = int(str(cutoff)[:4]), int(str(cutoff)[5:7])
            fs = min(fs, cy if cm >= 10 else cy - 1)
        except (ValueError, IndexError):
            pass
    return fs


def part_b_desc():
    """Section 3.1. Is the wave-1 P(bust | stale) separation a WINDOW asymmetry or a
    DEFINITIONAL offset in decision_year? Measured on the shipped matrices."""
    from efv_dataset import matrix_path
    out = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        rows = [r for r in raw if r["kind"] in ("debuted", "bust") and r.get("milb")]
        rec = []
        for r in rows:
            dy = E._decision_year(r)
            fs = _first_season(dy, r.get("cutoff"))
            ms = int(r["milb"]["milb_season"])
            cy = int(str(r.get("cutoff") or "0")[:4] or 0)
            rec.append({"bust": r["kind"] == "bust",
                        "stale": float(r["milb"]["stale"]),
                        "win_lag": float(fs - ms),
                        "cut_lag": float(cy - ms) if cy else None,
                        "first_season": fs, "milb_season": ms,
                        "n_milb_seasons": float(r["milb"]["n_milb_seasons"])})
        bust = np.array([x["bust"] for x in rec])

        def table(key):
            v = np.array([x[key] for x in rec if x[key] is not None], dtype=float)
            bb = np.array([x["bust"] for x in rec if x[key] is not None])
            t = {}
            for u in sorted(set(v.tolist())):
                m = v == u
                t[str(int(u)) if float(u).is_integer() else str(u)] = {
                    "n": int(m.sum()), "p_bust": float(bb[m].mean())}
            return {"cells": t,
                    "mean_debuted": float(v[~bb].mean()), "mean_bust": float(v[bb].mean()),
                    "kind_mean_gap": float(v[bb].mean() - v[~bb].mean())}

        tabs = {k: table(k) for k in ("stale", "win_lag", "cut_lag")}

        # IDENTITY 1: is the whole `stale` separation just the decision_year offset?
        # stale = decision_year - 1 - milb_season, and decision_year is cutoff_year for
        # a debuted row but cutoff_year + 1 for a bust, so `stale` should equal
        # cut_lag - 1[debuted]: the LABEL is arithmetically subtracted into the key.
        id1_ok = sum(1 for x in rec
                     if x["cut_lag"] is not None
                     and abs(x["stale"] - (x["cut_lag"] - (0.0 if x["bust"] else 1.0))) < 1e-9)
        id1_n = sum(1 for x in rec if x["cut_lag"] is not None)
        # IDENTITY 2: is the feature WINDOW a function of the cutoff year alone, the
        # same rule for both kinds? first_season should equal cutoff_year - 1.
        id2 = {}
        for x in rec:
            if x["cut_lag"] is None:
                continue
            cy = x["first_season"] - int(x["win_lag"]) + int(x["cut_lag"])   # = cutoff_year
            id2[("bust" if x["bust"] else "debuted", x["first_season"] - (cy - 1))] = \
                id2.get(("bust" if x["bust"] else "debuted", x["first_season"] - (cy - 1)), 0) + 1

        wl = tabs["win_lag"]
        material = (abs(wl["kind_mean_gap"]) >= 0.25
                    or any(c["n"] >= 50 and not (0.05 <= c["p_bust"] <= 0.95)
                           for c in wl["cells"].values()))
        nms = np.array([x["n_milb_seasons"] for x in rec])
        out[side] = {
            "n": len(rec),
            "n_debuted": int((~bust).sum()), "n_bust": int(bust.sum()),
            "tables": tabs,
            "n_milb_seasons": {"mean_debuted": float(nms[~bust].mean()),
                               "mean_bust": float(nms[bust].mean()),
                               "kind_mean_gap": float(nms[bust].mean() - nms[~bust].mean())},
            "identity_stale_is_cutlag_minus_label": {
                "matches": id1_ok, "n": id1_n,
                "rate": (id1_ok / id1_n) if id1_n else None,
                "claim": ("stale == cut_lag - 1[kind == debuted]. `stale` is not a "
                          "measurement of feature freshness, it is cut_lag with the "
                          "LABEL subtracted into it by the decision_year convention.")},
            "identity_window_is_cutoff_year_minus_1": {
                "first_season_minus_cutoff_year_plus_1_by_kind":
                    {f"{k[0]}|{k[1]}": v for k, v in sorted(id2.items())},
                "claim": ("first_season == cutoff_year - 1 for both kinds. After the "
                          "2026-07-24 as-of repair the MiLB feature WINDOW is a function "
                          "of the cutoff DATE alone and the rule is identical for busts "
                          "and debuted rows.")},
            "registered_verdict": ("REAL_WINDOW_ASYMMETRY" if material else "DEFINITIONAL"),
            "criterion": ("|win_lag kind-mean gap| >= 0.25 seasons, OR any win_lag cell "
                          "with n >= 50 and P(bust) outside [0.05, 0.95]"),
        }
    return out


def part_b_rows(side: str):
    """Build the four Part B row sets. Debuted rows only are re-anchored, onto the BUST
    rule (decision_year = asof_year + 1, cutoff = asof_date). Bust rows untouched.

    Returns (rowsets, meta). meta carries the parity assertion and treated_fraction, both
    registered preconditions in section 3.2."""
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    parity_ok = parity_tot = 0
    treated = 0
    n_deb = 0
    n_deb_all = sum(1 for r in raw if r["kind"] == "debuted")
    B0, B1a, B1b, B1c = [], [], [], []
    for r in raw:
        if r["kind"] != "debuted" or not r.get("milb"):
            for L in (B0, B1a, B1b, B1c):
                L.append(r)
            continue
        n_deb += 1
        # parity: does the SHIPPED anchor reproduce the stored block?
        shipped = DS._milb_features(r.get("mlbam_id"), int(r["debut_year"]),
                                    r.get("birth_date"), side, cutoff=r.get("cutoff"))
        parity_tot += 1
        if shipped and all(abs(float(shipped.get(k, 0) or 0)
                               - float(r["milb"].get(k, 0) or 0)) < 1e-9
                           for k in ("milb_season", "n_milb_seasons", "level_rank",
                                     "seasons_at_level")):
            parity_ok += 1
        asof = r.get("asof_date")
        if not asof:
            for L in (B0, B1a, B1b, B1c):
                L.append(r)
            continue
        alt_dy = int(str(asof)[:4]) + 1
        alt = DS._milb_features(r.get("mlbam_id"), alt_dy, r.get("birth_date"),
                                side, cutoff=asof)
        changed = alt is None or any(
            (alt.get(k) is None) != (r["milb"].get(k) is None)
            or (alt.get(k) is not None
                and abs(float(alt[k]) - float(r["milb"].get(k) or 0.0)) > 1e-9)
            for k in ("milb_season", "n_milb_seasons", "level_rank", "obp_rel",
                      "k_rel", "age_rel_level", "seasons_at_level"))
        if changed:
            treated += 1
        B0.append(r)
        ra = dict(r)
        ra["milb"] = alt if alt is not None else r["milb"]
        B1a.append(ra)
        rb = dict(ra)
        rb["debut_year"] = alt_dy          # _decision_year reads debut_year for debuted
        B1b.append(rb)
        rc = dict(r)
        rc["debut_year"] = alt_dy
        B1c.append(rc)
    meta = {"n_debuted_with_milb": n_deb, "n_debuted_all": n_deb_all,
            "parity_rows": parity_tot, "parity_matches": parity_ok,
            "parity_rate": (parity_ok / parity_tot) if parity_tot else None,
            "treated_rows": treated,
            "treated_fraction": (treated / n_deb) if n_deb else None,
            "treated_fraction_denominator": ("debuted rows that carry a milb block, i.e. "
                                             "the rows a re-anchor CAN move"),
            "treated_fraction_of_all_debuted": (treated / n_deb_all) if n_deb_all else None}
    return {"B0": B0, "B1a": B1a, "B1b": B1b, "B1c": B1c}, meta


def part_b(B: int = 1000, verbose: bool = True):
    rng = np.random.default_rng(SEED + 5)
    out = {}
    for side in SIDES:
        rowsets, meta = part_b_rows(side)
        if meta["parity_rate"] is not None and meta["parity_rate"] < 0.98:
            out[side] = {"meta": meta, "aborted":
                         "parity precondition failed: the shipped anchor does not "
                         "reproduce the stored milb block, so a re-anchor is not "
                         "attributable to the anchor"}
            continue
        pools = {k: base_pool(side, rows=v) for k, v in rowsets.items()}
        point = {}
        for arm, D in pools.items():
            point[arm] = {cut: legs(chain(D, None, cut)) for cut in ("full", "debuted")}
            if verbose:
                print(f"  [{side}] {arm:<5} full {point[arm]['full']['blend']:.5f} "
                      f"deb {point[arm]['debuted']['blend']:.5f}", flush=True)
        b0 = point["B0"]
        contrasts = {}
        for arm in ("B1a", "B1b", "B1c"):
            contrasts[arm] = {
                "d_full": point[arm]["full"]["blend"] - b0["full"]["blend"],
                "d_debuted": point[arm]["debuted"]["blend"] - b0["debuted"]["blend"],
            }
            contrasts[arm]["did"] = contrasts[arm]["d_full"] - contrasts[arm]["d_debuted"]
        # paired bootstrap: ONE draw over the B0 pool index, applied to every arm pool
        # (the arms are row-aligned by construction, so index i is the same player).
        n = pools["B0"]["n"]
        assert all(p["n"] == n for p in pools.values()), "Part B pools are not row-aligned"
        draws = {a: {"d_full": [], "d_debuted": [], "did": []}
                 for a in ("B1a", "B1b", "B1c")}
        t0 = time.time()
        for i in range(B):
            sel = rng.integers(0, n, n)
            base = {cut: chain(subset(pools["B0"], sel), None, cut)
                    for cut in ("full", "debuted")}
            if any(v is None for v in base.values()):
                continue
            bb = {cut: wrho(base[cut][1], base[cut][2], base[cut][3]) for cut in base}
            for arm in draws:
                S = subset(pools[arm], sel)
                vv = {}
                for cut in ("full", "debuted"):
                    r = chain(S, None, cut)
                    vv[cut] = None if r is None else wrho(r[1], r[2], r[3])
                if any(v is None or not np.isfinite(v) for v in vv.values()):
                    continue
                df = vv["full"] - bb["full"]
                dd = vv["debuted"] - bb["debuted"]
                draws[arm]["d_full"].append(float(df))
                draws[arm]["d_debuted"].append(float(dd))
                draws[arm]["did"].append(float(df - dd))
            if verbose and (i + 1) % 200 == 0:
                print(f"    {side} partB boot {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
        for arm in draws:
            for k in ("d_full", "d_debuted", "did"):
                a = np.array(draws[arm][k], dtype=float)
                a = a[np.isfinite(a)]
                if len(a) < 20:
                    contrasts[arm][k + "_boot"] = {"B_used": int(len(a)), "insufficient": True}
                    continue
                sd = float(a.std(ddof=1))
                p_raw = float(2 * min((a > 0).mean(), (a < 0).mean()))
                contrasts[arm][k + "_boot"] = {
                    "B_used": int(len(a)), "sd": sd, "mde95_paired": Z95_TWO * sd,
                    "ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))],
                    "boot_mean": float(a.mean()), "p_two_sided_raw": p_raw,
                    "resolvable_paired": bool(abs(contrasts[arm][k]) >= Z95_TWO * sd),
                }
        # registered verdict, section 3.3
        for arm in ("B1a", "B1b", "B1c"):
            did = contrasts[arm]["did"]
            bt = contrasts[arm].get("did_boot") or {}
            m = bt.get("mde95_paired")
            if meta["treated_fraction"] is not None and meta["treated_fraction"] < 0.10:
                v = "UNDERPOWERED (treated_fraction < 0.10)"
            elif m is None:
                v = "UNDERPOWERED (bootstrap did not resolve)"
            elif m > 0.02:
                v = "UNDERPOWERED (DiD floor exceeds 0.02 blend-rho units)"
            elif did <= -m:
                v = "ANCHOR-LEAK candidate (DiD negative beyond its own floor)"
            elif abs(did) < m:
                v = "ANCHOR-CLEAN (DiD inside its own floor)"
            else:
                v = "DiD POSITIVE beyond floor (re-anchor HELPS the full pool)"
            contrasts[arm]["registered_verdict"] = v
        out[side] = {"meta": meta, "point": point, "contrasts": contrasts}
    return out


# --------------------------------------------------------------------- repro
def repro(verbose: bool = True):
    """Parity: the replica must reproduce the shipped artifact rho on BOTH cuts."""
    rows = {}
    for side in SIDES:
        D = base_pool(side)
        art = ROOT / "data" / ("xfv_eval_pitcher.json" if side == "pit" else "xfv_eval.json")
        ev = json.loads(art.read_text(encoding="utf-8")).get("evals") or {}
        for cut, key in (("full", "full_pool_km"), ("debuted", "debuted_km")):
            lg = legs(chain(D, None, cut))
            po = (ev.get(key) or {}).get("pooled_oos") or {}
            ship = {"n": ((po.get("blend") or {}).get("n")),
                    "consensus": ((po.get("baseline") or {}).get("spearman")),
                    "blend": ((po.get("blend") or {}).get("spearman"))}
            rows[f"{side}.{key}"] = {"replica": lg, "artifact": ship,
                                     "source": f"data/{art.name} evals.{key}.pooled_oos",
                                     "blend_abs_diff": (abs(lg["blend"] - ship["blend"])
                                                        if ship["blend"] is not None else None)}
            if verbose:
                print(f"  {side} {key:<14} replica n={lg['n']} cons={lg['consensus']:.5f} "
                      f"blend={lg['blend']:.5f} | artifact n={ship['n']} "
                      f"cons={ship['consensus']} blend={ship['blend']}")
    return rows


def membership():
    h = [k for k, _ in E._FEATURES_HIT]
    p = [k for k, _ in E._FEATURES_PIT]
    src = (ROOT / "efv_model.py").read_text(encoding="utf-8")
    src2 = (ROOT / "efv_score.py").read_text(encoding="utf-8")
    return {
        "_FEATURES_HIT": h, "_FEATURES_PIT": p,
        "confirmed_by": "import efv_model, set membership on the live lists",
        "checks": {k: {"in_hit": k in h, "in_pit": k in p}
                   for k in ("stale", "milb_season", "decision_year",
                             "n_milb_seasons", "milb_missing", "seasons_at_level")},
        "stale_string_in_efv_model_py": ('"stale"' in src or "'stale'" in src),
        "stale_string_in_efv_score_py": ('"stale"' in src2 or "'stale'" in src2),
        "served_fit_train_frame": ("efv_model.fit_production_stack trains on the FULL pool "
                                   "(debuted + busts minus bust_recent), so the group "
                                   "separation is present in the SERVED fit; "
                                   "_run_eval('debuted_km') trains debuted-only and cannot "
                                   "see it"),
    }


# --------------------------------------------------------------------- driver
def run_all(B: int = 1000):
    t0 = time.time()
    print("=== MEMBERSHIP ===")
    mem = membership()
    print(json.dumps(mem["checks"], indent=1))
    print("=== REPRO (parity vs shipped artifacts) ===")
    rp = repro()
    print("=== PART B DESC (anchor mechanism) ===")
    bd = part_b_desc()
    for s, v in bd.items():
        print(f"  {s}: {v['registered_verdict']}  win_lag gap "
              f"{v['tables']['win_lag']['kind_mean_gap']:+.3f}  stale gap "
              f"{v['tables']['stale']['kind_mean_gap']:+.3f}")
    print("=== PART A (feature arms) ===")
    pa = part_a(B)
    va = verdict_part_a(pa)
    print(json.dumps(va, indent=1))
    print("=== PART B (anchor arms) ===")
    pb = part_b(B)
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "python tools/efv_feature_leak_lab.py all",
        "registration": (GATE_DOC + " sections 0-4, written in full before this lab "
                         "existed and before any accuracy number was computed"),
        "lane": "D wave 2: feature-level label leak + as-of anchor selection (plan item E1)",
        "seed": SEED,
        "B_requested": int(B),
        "estimator": ("forward-chained over efv_model.SCORED_YEARS (11 folds), "
                      "pair-weighted Spearman, primitives imported from "
                      "tools/efv_mde_lab.py; paired bootstrap resamples the WHOLE pool "
                      "and refits BOTH arms on the same draw; MDE95 = 1.96 * sd(contrast), "
                      "two-sided"),
        "self_added_threshold": (
            "PRIMARY BAR IS THE PAIRED-CONTRAST MDE95, not the model-vs-consensus "
            "MDE95_POOLED_RHO (0.044 hit / 0.0436 pit) that earlier drop gates used. "
            "Two fits of the same model differing in one column share nearly all their "
            "sampling variability, so the model-vs-consensus floor is far too WIDE here, "
            "and a too-wide floor is the PERMISSIVE direction for the NULL verdicts this "
            "lane produces (standing rule F). Both are reported on every contrast: see "
            "resolvable_paired vs resolvable_legacy_floor."),
        "elapsed_s": round(time.time() - t0, 1),
        "membership": mem,
        "repro": rp,
        "part_b_desc": bd,
        "part_a": pa,
        "part_a_verdicts": va,
        "part_b": pb,
    }
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote", OUT_PATH)
    print("elapsed", round(time.time() - t0, 1), "s")
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "repro"
    nb = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    if mode == "repro":
        print(json.dumps(membership()["checks"], indent=1))
        repro()
    elif mode == "desc":
        print(json.dumps(part_b_desc(), indent=1))
    elif mode == "parta":
        r = part_a(nb)
        print(json.dumps(verdict_part_a(r), indent=1))
    elif mode == "partb":
        print(json.dumps(part_b(nb), indent=1))
    elif mode == "all":
        run_all(nb)
    else:
        print("modes: repro | desc | parta [B] | partb [B] | all [B]")
