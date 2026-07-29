# SCRATCH LAB (sweep lane: STRUCTURE / missing-interaction / functional-form audit).
# READ-ONLY w.r.t. shipped code. Builds on tools/_frontier_ablate.py (the numpy replica of
# the production fit config under the Foundation "recommended evaluator").
#
# Gate: docs/EFV_GATE_STANDARD.md
#   MDE95 block-rho 0.0149 | per-side pooled rho 0.017 hit / 0.016 pit
#   required: paired bootstrap (train+test, refit per draw), zero-information control
#             (row-permuted twin of the SAME column), permutation null band,
#             effect averaged over >= 4 independent time splits.
#
# Modes:
#   python tools/_sweep_structure.py point            point estimates + per-fold + perm band
#   python tools/_sweep_structure.py boot [B]         paired refit bootstrap over all arms
#   python tools/_sweep_structure.py pd               partial-dependence / functional form
#   python tools/_sweep_structure.py speed            tool_speed standalone + proxy audit
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import efv_model as E                                            # noqa: E402  read-only
from _frontier_ablate import (ridge_fit, ridge_pred, ols_fit, lincal,  # noqa: E402
                              rho, _rankavg, ORIGINS)

OUT = HERE / "_sweep_out"
OUT.mkdir(exist_ok=True)

SEED = 20260725
# LIVE served blend lambdas (efv_model.blend_lambda): hit 0.70 (churn-trade ship), pit 0.54.
LAM = {"hit": 0.70, "pit": 0.54}
KEYS = {s: E._feature_spec(s)[0] for s in ("hit", "pit")}

# every raw feature name we may need to build a candidate from
RAW_HIT = ["fv", "obp_rel", "k_rel", "peak_k_rel", "age_rel_level", "n_milb_seasons",
           "tool_hit", "tool_speed", "milb_missing", "is_ifa", "is_college", "ops_rel",
           "age", "level_rank", "tool_field", "tool_game_pwr", "iso_rel", "pos_prem",
           "peak_obp_rel", "prod_trend", "pick_overall", "n_sources"]
RAW_PIT = ["fv", "peak_k_rel", "k_rel", "bb_rel", "age_rel_level", "x_era_k", "tool_fb",
           "age", "level_rank", "n_milb_seasons", "era_rel", "milb_missing", "pos_prem",
           "is_college", "is_ifa", "prod_trend"]
RAW = {"hit": RAW_HIT, "pit": RAW_PIT}


# --------------------------------------------------------------------------- data
def load(side: str):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    raw = json.loads((ROOT / "data" / fn).read_text(encoding="utf-8"))
    prep = E._prep(raw, "target_censored", side)
    assert len(prep) == len(raw)
    names = list(RAW[side])
    X = np.array([[r["feats"].get(k, 0.0) for k in names] for r in prep], dtype=float)
    y = np.array([r["target"] for r in prep], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], dtype=float)
    dy = np.array([r["decision_year"] for r in prep], dtype=int)
    deb = np.array([r["kind"] == "debuted" for r in prep])
    keep = np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                     for r, o in zip(prep, raw)])
    # ---- derived columns for the MISSING-BLOCK arms -------------------------
    # 52% (hit) / 54% (pit) of training rows carry NO milb block at all: efv_model._vec
    # falls back to g(m.get(k)) == 0.0, so level_rank and n_milb_seasons are imputed at
    # their FLOOR (z ~ -0.84 against the pooled distribution), not at a neutral value,
    # and milb_missing is deliberately 0 for the milb_unavailable rows. Neutral-impute
    # constants are measured on PRE-2020 observed rows only (strictly forward-clean).
    has = np.array([bool(r.get("milb")) for r in raw])
    pre = has & (dy < min(ORIGINS))
    extra = {}
    for k in ("level_rank", "n_milb_seasons"):
        j = names.index(k)
        mu = float(X[pre, j].mean()) if pre.sum() > 30 else float(X[has, j].mean())
        v = X[:, j].copy()
        v[~has] = mu
        extra[k + "_neutral"] = v
        extra["_mu_" + k] = mu
    extra["milb_obs"] = has.astype(float)
    ja, jl = names.index("age"), names.index("level_rank")
    lvn = extra["level_rank_neutral"]
    agv = X[:, ja]
    lc = float(lvn[pre].mean()) if pre.sum() > 30 else float(lvn[has].mean())
    ac = float(agv[pre].mean()) if pre.sum() > 30 else float(agv[has].mean())
    prod = (lvn - lc) * (agv - ac)
    prod[~has] = 0.0                      # neutral on rows with no milb block
    extra["lvl_x_age_obs"] = prod
    for nm, v in extra.items():
        if nm.startswith("_mu_"):
            continue
        names = names + [nm]
        X = np.column_stack([X, v])
    return dict(side=side, X=X, y=y, w=w, fv=fv, dy=dy, deb=deb, keep=keep, has=has,
                names=names, idx={k: i for i, k in enumerate(names)},
                mu_lvl=extra["_mu_level_rank"], mu_nms=extra["_mu_n_milb_seasons"],
                base=[names.index(k) for k in KEYS[side]],
                pk=[r["player_key"] for r in prep])


D = {s: load(s) for s in ("hit", "pit")}


def col(side, name):
    return D[side]["X"][:, D[side]["idx"][name]]


def cen(v):
    """center (feature-only, no label) so the product is a clean interaction against
    the main effects that are already in the model."""
    return v - v.mean()


# --------------------------------------------------------------------------- arms
# Every candidate below states its HYPOTHESIS before it is tested. Failures are reported.
CAND = {"hit": {}, "pit": {}}
HYP = {}


def add(side, name, hypothesis, cols_fn, extra_main=()):
    """cols_fn -> list of (colname, vector). extra_main = shipped-set additions needed
    for the interaction to be interpretable (e.g. level_rank main effect on pitchers)."""
    CAND[side][name] = (cols_fn, tuple(extra_main))
    HYP[(side, name)] = hypothesis


# ---- (a) THE PRE-REGISTERED PRIMARY: level_rank x age -----------------------
add("hit", "lvl_x_age",
    "Proximity-to-majors credit should be DISCOUNTED for age: a 24yo and a 20yo in AAA "
    "must not receive identical level_rank credit (the Bradfield case). Expect a NEGATIVE "
    "fitted weight on level x age.",
    lambda s: [("lvl_x_age", cen(col(s, "level_rank")) * cen(col(s, "age")))])
add("hit", "lvl_x_agerel",
    "Same hypothesis using the level-relative age clock instead of absolute age.",
    lambda s: [("lvl_x_agerel", cen(col(s, "level_rank")) * cen(col(s, "age_rel_level")))])
add("pit", "lvl_main",
    "CONTEXT ARM (pitchers have no shipped level_rank): does the main effect alone earn "
    "its place before any interaction is considered?",
    lambda s: [], extra_main=("level_rank",))
add("pit", "lvl_x_age",
    "Same as hitters: level credit discounted by age. Requires the level_rank main effect, "
    "so this arm adds BOTH (main + interaction) and is compared against lvl_main too.",
    lambda s: [("lvl_x_age", cen(col(s, "level_rank")) * cen(col(s, "age")))],
    extra_main=("level_rank",))
add("pit", "lvl_x_agerel",
    "Level credit discounted by level-relative age (pitchers).",
    lambda s: [("lvl_x_agerel", cen(col(s, "level_rank")) * cen(col(s, "age_rel_level")))],
    extra_main=("level_rank",))

# ---- (b) theory-motivated interaction sweep --------------------------------
add("hit", "age_x_prod",
    "AGE x PRODUCTION: being old is forgivable when the bat is genuinely playing, and "
    "compounding when it is not. A linear age term prices the clock identically for a "
    "26yo mashing AAA and a 26yo repeating it.",
    lambda s: [("age_x_obp", cen(col(s, "age")) * cen(col(s, "obp_rel")))])
add("pit", "age_x_prod",
    "AGE x PRODUCTION for arms: age priced identically for a 24yo missing bats and a 24yo "
    "with league-average stuff results.",
    lambda s: [("age_x_pk", cen(col(s, "age")) * cen(col(s, "peak_k_rel")))])

add("hit", "lvl_x_prod",
    "LEVEL x PRODUCTION: a given rate line is more informative the closer to MLB it was "
    "produced (less level/park/competition noise, shorter extrapolation). The model "
    "currently treats +1 SD obp_rel in Low-A and in AAA as the same evidence.",
    lambda s: [("lvl_x_obp", cen(col(s, "level_rank")) * cen(col(s, "obp_rel")))])
add("pit", "lvl_x_prod",
    "LEVEL x PRODUCTION for arms (same reliability argument, on peak K-rate).",
    lambda s: [("lvl_x_pk", cen(col(s, "level_rank")) * cen(col(s, "peak_k_rel")))],
    extra_main=("level_rank",))

add("hit", "tool_x_prod_spd",
    "TOOL x PRODUCTION (the Bradfield speed case): does an elite tool matter MORE (it is "
    "the residual carrying case when the bat has not shown up) or LESS (a tool with no "
    "production is empty athleticism)? Directional prior: LESS, i.e. a positive "
    "speed x production interaction.",
    lambda s: [("spd_x_obp", cen(col(s, "tool_speed")) * cen(col(s, "obp_rel")))])
add("hit", "tool_x_prod_hit",
    "Same question for the hit tool: does scouted hit grade need production confirmation?",
    lambda s: [("hit_x_obp", cen(col(s, "tool_hit")) * cen(col(s, "obp_rel")))])
add("pit", "tool_x_prod",
    "Same for tool_fb x peak K-rate. PRECEDENT: fb_x_k was tested and REVERTED 2026-06-24 "
    "on robustness grounds; re-measured here only to bound it under the current gate.",
    lambda s: [("fb_x_pk", cen(col(s, "tool_fb")) * cen(col(s, "peak_k_rel")))])

add("hit", "exp_x_rate",
    "EXPOSURE x RATE RELIABILITY: rate features are shrunk per-season at source but the "
    "ridge still reads a 1-season rate and a 6-season rate as equally trustworthy. An "
    "n_milb_seasons x rate term lets the model DISCOUNT thin-record rates. Expect a "
    "positive weight (rates count more with more exposure).",
    lambda s: [("exp_x_obp", cen(col(s, "n_milb_seasons")) * cen(col(s, "obp_rel"))),
               ("exp_x_k", cen(col(s, "n_milb_seasons")) * cen(col(s, "k_rel")))])
add("pit", "exp_x_rate",
    "Same reliability argument for arms (n_milb_seasons is NOT a shipped pitcher feature, "
    "so this arm adds the main effect too).",
    lambda s: [("exp_x_pk", cen(col(s, "n_milb_seasons")) * cen(col(s, "peak_k_rel"))),
               ("exp_x_bb", cen(col(s, "n_milb_seasons")) * cen(col(s, "bb_rel")))],
    extra_main=("n_milb_seasons",))

# ---- (c) functional form ----------------------------------------------------
add("hit", "age_hinge",
    "FUNCTIONAL FORM: the age penalty should ACCELERATE (a 25yo A-ball bat is not 'one more "
    "year' worse than a 24yo). Add one-sided hinges at 22 and 24 on top of the linear term.",
    lambda s: [("age_h22", np.maximum(0.0, col(s, "age") - 22.0)),
               ("age_h24", np.maximum(0.0, col(s, "age") - 24.0))])
add("pit", "age_hinge",
    "Same accelerating-age hypothesis for arms.",
    lambda s: [("age_h22", np.maximum(0.0, col(s, "age") - 22.0)),
               ("age_h24", np.maximum(0.0, col(s, "age") - 24.0))])
add("hit", "agerel_hinge",
    "FUNCTIONAL FORM on the level-relative clock: penalty for being OLD for level should "
    "accelerate while being young for level saturates.",
    lambda s: [("agerel_hp", np.maximum(0.0, col(s, "age_rel_level"))),
               ("agerel_hp2", np.maximum(0.0, col(s, "age_rel_level") - 1.5))])
add("pit", "agerel_hinge",
    "Same for arms.",
    lambda s: [("agerel_hp", np.maximum(0.0, col(s, "age_rel_level"))),
               ("agerel_hp2", np.maximum(0.0, col(s, "age_rel_level") - 1.5))])
add("hit", "fv_hinge",
    "FUNCTIONAL FORM on the dominant prior: WAR is convex in FV (a 60 is worth much more "
    "than 2x a 50). A linear FV term under-prices the top of the board.",
    lambda s: [("fv_h50", np.maximum(0.0, col(s, "fv") - 50.0)),
               ("fv_h55", np.maximum(0.0, col(s, "fv") - 55.0))])
add("pit", "fv_hinge",
    "Same convex-FV hypothesis for arms.",
    lambda s: [("fv_h50", np.maximum(0.0, col(s, "fv") - 50.0)),
               ("fv_h55", np.maximum(0.0, col(s, "fv") - 55.0))])

# ---- (d) tool_speed --------------------------------------------------------
add("hit", "drop_tool_speed",
    "ABLATION: is tool_speed earning its +0.501 contribution, or is it a proxy for "
    "up-the-middle defensive value / athleticism better captured directly?",
    lambda s: [], extra_main=())          # handled specially (drop)
add("hit", "speed_to_posprem",
    "PROXY TEST: replace tool_speed with the up-the-middle position premium.",
    lambda s: [], extra_main=())
add("hit", "speed_plus_field",
    "PROXY TEST: add tool_field beside tool_speed. If speed is standing in for defense, "
    "the direct defensive grade should absorb it.",
    lambda s: [], extra_main=("tool_field",))
add("hit", "speed_plus_posprem",
    "PROXY TEST: add pos_prem beside tool_speed.",
    lambda s: [], extra_main=("pos_prem",))

# ---- MISSING-BLOCK arms (the imputation-floor defect) -----------------------
for _s in ("hit", "pit"):
    add(_s, "lvl_neutral_impute",
        "IMPUTATION FLOOR: level_rank is imputed at 0.0 (its floor, z ~ -0.84) for the "
        "half of the pool with no milb block, and milb_missing is deliberately 0 on those "
        "rows, so the shipped +0.43 level_rank weight is partly fitting a DECISION-YEAR "
        "gradient (milb coverage runs 0% in 2012-14 to 85% in 2024). Re-impute at the "
        "observed pre-2020 mean, the _TOOL_IMPUTE precedent, so missing stays neutral.",
        lambda s: [])
    add(_s, "nms_neutral_impute",
        "Same floor-impute defect on n_milb_seasons (also imputed at 0.0, z ~ -0.80).",
        lambda s: [])
    add(_s, "both_neutral_impute",
        "level_rank and n_milb_seasons both re-imputed at their observed means.",
        lambda s: [])
    add(_s, "milb_obs_ind",
        "Add an honest missing-block indicator so the ridge can separate the "
        "no-milb-data population from a genuine complex-league line.",
        lambda s: [], extra_main=("milb_obs",))
    add(_s, "neutral_plus_ind",
        "Both fixes together: neutral imputes + the missing-block indicator.",
        lambda s: [])
    add(_s, "lvl_x_age_obs",
        "The level x age interaction built ONLY on rows with an observed milb block "
        "(neutral 0 elsewhere), on top of the neutral imputes. The naive centred product "
        "is dominated by the 52%/54% imputed mass sitting at its centre, which is why the "
        "plain lvl_x_age arm cannot express the empirically measured surface.",
        lambda s: [])

SPECIAL = {
    "drop_tool_speed": ("drop", "tool_speed"),
    "speed_to_posprem": ("swap", ("tool_speed", "pos_prem")),
    "lvl_neutral_impute": ("swap", ("level_rank", "level_rank_neutral")),
    "nms_neutral_impute": ("swap", ("n_milb_seasons", "n_milb_seasons_neutral")),
    "both_neutral_impute": ("swapn", [("level_rank", "level_rank_neutral"),
                                      ("n_milb_seasons", "n_milb_seasons_neutral")]),
    "neutral_plus_ind": ("swapn", [("level_rank", "level_rank_neutral"),
                                   ("n_milb_seasons", "n_milb_seasons_neutral")],
                         ["milb_obs"]),
    "lvl_x_age_obs": ("swapn", [("level_rank", "level_rank_neutral"),
                                ("n_milb_seasons", "n_milb_seasons_neutral")],
                      ["milb_obs", "lvl_x_age_obs"]),
}
# pitchers have neither level_rank nor n_milb_seasons in the shipped set, so the swap
# arms are meaningless there: the missing-block defect reaches them only through
# age_rel_level / rate imputes. Keep only the indicator + the level arms.
for _a in ("lvl_neutral_impute", "nms_neutral_impute", "both_neutral_impute",
           "neutral_plus_ind", "lvl_x_age_obs"):
    CAND["pit"].pop(_a, None)


# --------------------------------------------------------------------------- scoring
def build(side, arm, perm_rng=None):
    """Return (X_arm, colnames) for one arm. perm_rng != None -> row-permute EVERY
    candidate-constructed column (the zero-information twin: identical marginal)."""
    d = D[side]
    base_names = list(KEYS[side])
    if arm == "base":
        return d["X"][:, d["base"]], base_names
    sp = SPECIAL.get(arm)
    if sp and sp[0] == "drop":
        nm = [k for k in base_names if k != sp[1]]
        return d["X"][:, [d["idx"][k] for k in nm]], nm
    if sp and sp[0] == "swap":
        nm = [(sp[1][1] if k == sp[1][0] else k) for k in base_names]
        return d["X"][:, [d["idx"][k] for k in nm]], nm
    if sp and sp[0] == "swapn":
        mp = dict(sp[1])
        nm = [mp.get(k, k) for k in base_names] + list(sp[2] if len(sp) > 2 else [])
        return d["X"][:, [d["idx"][k] for k in nm]], nm
    fn, extra = CAND[side][arm]
    nm = base_names + list(extra)
    Xb = d["X"][:, [d["idx"][k] for k in nm]]
    built = fn(side)
    if not built:
        return Xb, nm
    n = len(d["y"])
    cols = []
    for cname, v in built:
        if perm_rng is not None:
            v = v[perm_rng.permutation(n)]
        cols.append(v)
        nm = nm + [cname]
    return np.column_stack([Xb] + cols), nm


def score(side, Xa, sel=None, origins=ORIGINS, test_frame="debuted"):
    """Forward-chained production-replica scores. Returns (blockid, pred, target, deb)."""
    d = D[side]
    y, w, fv, dy, deb, keep = d["y"], d["w"], d["fv"], d["dy"], d["deb"], d["keep"]
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = Xa[sel], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps = deb[sel], keep[sel]
    lam = LAM[side]
    B, P, T, DB = [], [], [], []
    for yr in origins:
        tr = np.flatnonzero(keeps & (dys < yr))
        te = np.flatnonzero((debs if test_frame == "debuted" else keeps) & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fvs[tr], ys[tr])
        rg = ridge_fit(Xs[tr], ys[tr], ws[tr])
        if o is None or rg is None:
            continue
        a, b = lincal(ridge_pred(rg, Xs[tr]), ys[tr])
        mod = np.maximum(-2.0, a + b * ridge_pred(rg, Xs[te]))
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        B.append(np.full(len(te), yr))
        P.append((1 - lam) * cons + lam * mod)
        T.append(ys[te])
        DB.append(debs[te])
    if not P:
        return None
    return (np.concatenate(B), np.concatenate(P), np.concatenate(T), np.concatenate(DB))


def blockrho(parts):
    PP, TT = [], []
    for b, p, t in parts:
        for yr in np.unique(b):
            m = b == yr
            if m.sum() < 8:
                continue
            n = int(m.sum())
            PP.append((_rankavg(p[m]) - 0.5) / n)
            TT.append((_rankavg(t[m]) - 0.5) / n)
    if not PP:
        return float("nan")
    return rho(np.concatenate(PP), np.concatenate(TT))


def auc(pred, lab):
    lab = np.asarray(lab, dtype=bool)
    if lab.all() or (~lab).any() is False or lab.sum() == 0 or (~lab).sum() == 0:
        return float("nan")
    r = _rankavg(pred)
    n1, n0 = int(lab.sum()), int((~lab).sum())
    return float((r[lab].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def metrics(side, arm, sel=None, perm_rng=None, base_other=None):
    """Full metric bundle for one arm on one side."""
    Xa, _nm = build(side, arm, perm_rng=perm_rng)
    r = score(side, Xa, sel=sel)
    if r is None:
        return None
    b, p, t, _ = r
    out = {"rho": rho(p, t), "n": len(t)}
    parts = [(b, p, t)]
    if base_other is not None:
        parts.append(base_other)
    out["block"] = blockrho(parts)
    out["per_fold"] = {int(yr): rho(p[b == yr], t[b == yr]) for yr in np.unique(b)}
    rf = score(side, Xa, sel=sel, test_frame="full")
    out["auc"] = auc(rf[1], rf[3]) if rf is not None else float("nan")
    return out


ARMS = {s: ["base"] + list(CAND[s]) for s in ("hit", "pit")}


# --------------------------------------------------------------------------- modes
def mode_point(n_perm=25):
    print("=== eFV STRUCTURE SWEEP: point estimates, per-fold, permutation null band ===")
    print("gate: block-rho MDE95 0.0149 | pooled rho MDE95 0.017 hit / 0.016 pit")
    print(f"lam hit={LAM['hit']} pit={LAM['pit']}  origins={ORIGINS}\n")
    res = {}
    base_r = {}
    for s in ("hit", "pit"):
        Xb, _ = build(s, "base")
        rr = score(s, Xb)
        base_r[s] = (rr[0], rr[1], rr[2])
    for s in ("hit", "pit"):
        other = base_r["pit" if s == "hit" else "hit"]
        b0 = metrics(s, "base", base_other=other)
        res[s] = {"base": b0}
        print(f"--- {s.upper()}  base: rho {b0['rho']:.4f}  block {b0['block']:.4f} "
              f"auc {b0['auc']:.4f}  n={b0['n']}")
        print(f"{'arm':<20} {'d_rho':>8} {'d_block':>8} {'d_auc':>8} "
              f"{'folds+':>7} {'perm_mean':>10} {'perm_band95':>18} {'vs band':>8}")
        for arm in ARMS[s]:
            if arm == "base":
                continue
            m = metrics(s, arm, base_other=other)
            if m is None:
                print(f"{arm:<20}  FIT FAILED")
                continue
            d_rho = m["rho"] - b0["rho"]
            d_blk = m["block"] - b0["block"]
            d_auc = m["auc"] - b0["auc"]
            folds = {yr: m["per_fold"][yr] - b0["per_fold"][yr] for yr in b0["per_fold"]}
            npos = sum(1 for v in folds.values() if v > 0)
            # zero-information control: row-permuted twin of the SAME constructed column(s).
            # Arms with no constructed column (pure main-effect adds / drops / swaps) have
            # no permutable column: their control is the noise-column band reported below.
            pr, pra = [], []
            if CAND[s].get(arm) and CAND[s][arm][0](s):
                for j in range(n_perm):
                    mp = metrics(s, arm, perm_rng=np.random.default_rng(SEED + 977 * j),
                                 base_other=other)
                    if mp:
                        pr.append(mp["block"] - b0["block"])
                        pra.append(mp["auc"] - b0["auc"])
            # The permuted twin keeps any extra MAIN effect the arm adds and destroys only
            # the constructed interaction, so the band is centred on the main-effect cost,
            # not on zero. Compare the candidate against the BAND, not against 0.
            pm = float(np.mean(pr)) if pr else float("nan")
            lo = float(np.percentile(pr, 2.5)) if pr else float("nan")
            hi = float(np.percentile(pr, 97.5)) if pr else float("nan")
            flag = "" if not pr else ("OUT" if (d_blk < lo or d_blk > hi) else "in-band")
            res[s][arm] = {"d_rho": d_rho, "d_block": d_blk, "d_auc": d_auc,
                           "folds": folds, "perm": pr,
                           "rho": m["rho"], "block": m["block"], "auc": m["auc"]}
            print(f"{arm:<20} {d_rho:+8.4f} {d_blk:+8.4f} {d_auc:+8.4f} "
                  f"{npos:>4}/{len(folds)} {pm:+10.4f} [{lo:+7.4f},{hi:+7.4f}] {flag:>8}")
            if pra:
                alo, ahi = np.percentile(pra, [2.5, 97.5])
                aflag = "OUT" if (d_auc < alo or d_auc > ahi) else "in-band"
                print(f"{'':<20}      auc perm band [{alo:+.4f},{ahi:+.4f}] "
                      f"mean {np.mean(pra):+.4f} -> {aflag}")
        print()
    json.dump({s: {a: {k: (v if not isinstance(v, dict) else
                           {str(x): y for x, y in v.items()})
                       for k, v in d.items()} for a, d in res[s].items()}
               for s in res}, open(OUT / "structure_point.json", "w"), indent=1)
    return res


def mode_boot(B=1000):
    """Paired bootstrap: resample players WITHIN (side, decision_year) over the WHOLE pool
    (train AND test), refit every arm on the same replicate. Replicate 0 = point estimate."""
    print(f"=== PAIRED REFIT BOOTSTRAP  B={B} (train AND test resampled, refit per draw) ===")
    strata = {s: [np.flatnonzero(D[s]["dy"] == v) for v in np.unique(D[s]["dy"])]
              for s in ("hit", "pit")}
    rng = np.random.default_rng(SEED)
    store = {s: {a: {"rho": [], "block": [], "auc": []} for a in ARMS[s]}
             for s in ("hit", "pit")}
    Xarm = {s: {a: build(s, a)[0] for a in ARMS[s]} for s in ("hit", "pit")}
    t0 = time.time()
    for bi in range(B + 1):
        if bi == 0:
            sel = {s: np.arange(len(D[s]["y"])) for s in ("hit", "pit")}
        else:
            sel = {s: np.concatenate([rng.choice(ix, size=len(ix), replace=True)
                                      for ix in strata[s]]) for s in ("hit", "pit")}
        raw = {}
        for s in ("hit", "pit"):
            raw[s] = {}
            for a in ARMS[s]:
                r = score(s, Xarm[s][a], sel=sel[s])
                rf = score(s, Xarm[s][a], sel=sel[s], test_frame="full")
                raw[s][a] = None if r is None else (
                    r[0], r[1], r[2], (auc(rf[1], rf[3]) if rf is not None else float("nan")))
        for s in ("hit", "pit"):
            o = "pit" if s == "hit" else "hit"
            bo = raw[o]["base"]
            for a in ARMS[s]:
                r = raw[s][a]
                if r is None:
                    for k in ("rho", "block", "auc"):
                        store[s][a][k].append(float("nan"))
                    continue
                store[s][a]["rho"].append(rho(r[1], r[2]))
                store[s][a]["block"].append(
                    blockrho([r[:3]] + ([bo[:3]] if bo else [])))
                store[s][a]["auc"].append(r[3])
        if bi % 100 == 0:
            print(" ", bi, round(time.time() - t0, 1), "s", flush=True)
    json.dump(store, open(OUT / "structure_boot.json", "w"))
    report_boot(store)


def report_boot(store=None):
    if store is None:
        store = json.load(open(OUT / "structure_boot.json"))
    print("\n=== PAIRED BOOTSTRAP: delta vs base (draw-paired) ===")
    for s in ("hit", "pit"):
        mde = 0.017 if s == "hit" else 0.016
        print(f"\n--- {s.upper()}   (block MDE95 0.0149 | pooled rho MDE95 {mde})")
        print(f"{'arm':<20} {'d_block':>9} {'CI95':>20} {'P>0':>6} "
              f"{'d_rho':>9} {'CI95':>20} {'P>0':>6} "
              f"{'d_auc':>9} {'CI95':>20} {'P>0':>6} {'VERDICT':>9}")
        base = {k: np.array(store[s]["base"][k], dtype=float)
                for k in ("block", "rho", "auc")}
        for a in store[s]:
            if a == "base":
                continue
            cells, res = [], []
            for k, floor in (("block", 0.0149), ("rho", mde), ("auc", None)):
                d = np.array(store[s][a][k], dtype=float) - base[k]
                pt = d[0]
                d = d[1:]
                d = d[~np.isnan(d)]
                lo, hi = np.percentile(d, [2.5, 97.5])
                p = float((d > 0).mean())
                cells.append(f"{pt:+9.4f} [{lo:+7.4f},{hi:+7.4f}] {p:6.3f}")
                res.append(lo * hi > 0 and (floor is None or abs(pt) > floor))
            verdict = "RESOLVED" if (res[0] or res[1]) else (
                "AUC-only" if res[2] else "NULL")
            print(f"{a:<20} " + " ".join(cells) + f" {verdict:>9}")


# --------------------------------------------------------------------------- (c) shape
def mode_pd():
    """Partial-dependence style read: forward-chained OOF residual (realized - predicted)
    binned by the raw feature. A linear term that fits the shape leaves a FLAT residual
    profile; curvature in the profile is what a spline would recover."""
    print("=== FUNCTIONAL FORM: forward-chained OOF residual profiles ===")
    print("(residual = realized WAR - blended prediction, debuted test rows, 2020-2024)")
    for s in ("hit", "pit"):
        Xb, _ = build(s, "base")
        r = score(s, Xb)
        b, p, t, _ = r
        # rebuild the aligned test-row index so we can attach raw features
        idx = []
        keep, dy, deb = D[s]["keep"], D[s]["dy"], D[s]["deb"]
        for yr in ORIGINS:
            tr = np.flatnonzero(keep & (dy < yr))
            te = np.flatnonzero(deb & (dy == yr))
            if len(te) < 15 or len(tr) < 60:
                continue
            idx.append(te)
        idx = np.concatenate(idx)
        assert len(idx) == len(t)
        resid = t - p
        print(f"\n--- {s.upper()}  n={len(t)}")
        feats = (["age", "age_rel_level", "level_rank", "fv", "obp_rel", "tool_speed"]
                 if s == "hit" else ["age", "age_rel_level", "level_rank", "fv", "peak_k_rel"])
        for f in feats:
            v = D[s]["X"][idx, D[s]["idx"][f]]
            qs = np.unique(np.quantile(v, [0, .2, .4, .6, .8, 1.0]))
            if len(qs) < 4:
                continue
            print(f"  {f:<15}", end="")
            cells = []
            for i in range(len(qs) - 1):
                m = (v >= qs[i]) & (v <= qs[i + 1] if i == len(qs) - 2 else v < qs[i + 1])
                if m.sum() < 20:
                    cells.append(("", 0))
                    continue
                cells.append((f"[{qs[i]:.1f},{qs[i+1]:.1f}) n={int(m.sum())} "
                              f"res={resid[m].mean():+.2f}", int(m.sum())))
            print("  ".join(c[0] for c in cells if c[0]))
        # curvature test: is the residual profile monotone-curved in age?
        for f in (["age", "age_rel_level"]):
            v = D[s]["X"][idx, D[s]["idx"][f]]
            vc = v - v.mean()
            q = vc ** 2
            q = q - q.mean()
            den = math.sqrt(float((q * q).sum()) * float((resid - resid.mean()) @ (resid - resid.mean())))
            c = float((q * (resid - resid.mean())).sum() / den) if den > 0 else float("nan")
            print(f"  corr(resid, ({f}-mean)^2) = {c:+.4f}")


# --------------------------------------------------------------------------- (d) speed
def mode_speed():
    print("=== tool_speed AUDIT ===")
    s = "hit"
    d = D[s]
    y, deb = d["y"], d["deb"]
    sp = col(s, "tool_speed")
    obs = np.array([True] * len(sp))
    print(f"n={len(sp)}  tool_speed mean {sp.mean():.2f} sd {sp.std():.2f} "
          f"(impute value {E._TOOL_IMPUTE['tool_speed']})")
    n_imp = int((sp == E._TOOL_IMPUTE["tool_speed"]).sum())
    print(f"rows exactly at the impute constant: {n_imp} ({100*n_imp/len(sp):.1f}%)")
    print("\nmarginal Spearman with target_censored (full pool / debuted only):")
    for f in ("tool_speed", "tool_hit", "tool_field", "pos_prem", "fv", "obp_rel",
              "level_rank", "age"):
        v = col(s, f)
        print(f"  {f:<14} full {rho(v, y):+.4f}   debuted {rho(v[deb], y[deb]):+.4f}")
    print("\ncorrelation of tool_speed with candidate proxies (Spearman):")
    for f in ("pos_prem", "tool_field", "tool_hit", "fv", "age", "level_rank"):
        print(f"  tool_speed vs {f:<12} {rho(sp, col(s, f)):+.4f}")
    # partial (residualized on the rest of the shipped block)
    Xb = d["X"][:, [d["idx"][k] for k in KEYS[s] if k != "tool_speed"]]
    mu, sd = Xb.mean(0), Xb.std(0)
    sd[sd == 0] = 1
    Z = np.column_stack([np.ones(len(y)), (Xb - mu) / sd])
    def resid(v):
        beta, *_ = np.linalg.lstsq(Z, v, rcond=None)
        return v - Z @ beta
    print("\nPARTIAL correlation given the rest of the shipped hitter block:")
    for f in ("tool_speed", "pos_prem", "tool_field"):
        print(f"  {f:<14} partial-Spearman(resid_x, resid_y) = "
              f"{rho(resid(col(s, f)), resid(y)):+.4f}")
    del obs


def mode_pdfull():
    """Same residual profile on the FULL-POOL frame (debuted + busts as test rows).
    The debuted-only frame conditions on the outcome an age feature is meant to predict,
    so it is structurally unable to score the age clock. This is the unconditioned read."""
    print("=== FUNCTIONAL FORM on the FULL POOL (busts included as test rows) ===")
    for s in ("hit", "pit"):
        Xb, _ = build(s, "base")
        r = score(s, Xb, test_frame="full")
        b, p, t, deb = r
        idx = []
        keep, dy = D[s]["keep"], D[s]["dy"]
        for yr in ORIGINS:
            tr = np.flatnonzero(keep & (dy < yr))
            te = np.flatnonzero(keep & (dy == yr))
            if len(te) < 15 or len(tr) < 60:
                continue
            idx.append(te)
        idx = np.concatenate(idx)
        assert len(idx) == len(t), (len(idx), len(t))
        resid = t - p
        print(f"\n--- {s.upper()} n={len(t)} (debuted {int(deb.sum())})")
        feats = (["age", "age_rel_level", "level_rank", "tool_speed"] if s == "hit"
                 else ["age", "age_rel_level", "level_rank"])
        for f in feats:
            v = D[s]["X"][idx, D[s]["idx"][f]]
            qs = np.unique(np.quantile(v, [0, .2, .4, .6, .8, 1.0]))
            if len(qs) < 4:
                continue
            out = []
            for i in range(len(qs) - 1):
                m = (v >= qs[i]) & (v <= qs[i + 1] if i == len(qs) - 2 else v < qs[i + 1])
                if m.sum() < 20:
                    continue
                out.append(f"[{qs[i]:.1f},{qs[i+1]:.1f}) n={int(m.sum())} "
                           f"res={resid[m].mean():+.2f} deb={deb[m].mean():.2f}")
            print(f"  {f:<15}" + "  ".join(out))


def mode_agesign():
    """DEFECT-2 ROOT CAUSE TEST. Hypothesis: the served pitcher ridge fits age at
    +0.0589 (declared -1) because _FEATURES_PIT OMITS every variable that carries
    'how far along the development path is this arm' - level_rank, n_milb_seasons,
    is_college. Age is the only column left to absorb them, so it inherits their
    POSITIVE sign. The hitter set contains all three and fits age NEGATIVE.
    Prediction: adding any of them to pitchers drives the age weight negative;
    removing them from hitters drives the hitter age weight positive."""
    print("=== AGE-SIGN OMITTED-VARIABLE TEST ===")
    print(HYP.get(("x", "x"), ""), end="")
    for s, adds, drops in (("pit", ["level_rank", "n_milb_seasons", "is_college",
                                    "milb_missing"], []),
                           ("hit", [], ["level_rank", "n_milb_seasons", "is_college"])):
        d = D[s]
        tr = np.flatnonzero(d["keep"])
        base_names = list(KEYS[s])
        def wfit(names):
            X = d["X"][:, [d["idx"][k] for k in names]]
            rg = ridge_fit(X[tr], d["y"][tr], d["w"][tr])
            return dict(zip(names, rg[2]))
        w0 = wfit(base_names)
        print(f"\n--- {s.upper()}  shipped set: age = {w0['age']:+.4f} "
              f"(declared monotone -1)   n={len(tr)}")
        for a in adds:
            w = wfit(base_names + [a])
            print(f"   + {a:<16} age {w0['age']:+.4f} -> {w['age']:+.4f}   "
                  f"({a} w={w[a]:+.4f})")
        if adds:
            w = wfit(base_names + adds)
            print(f"   + ALL              age {w0['age']:+.4f} -> {w['age']:+.4f}")
        for dr in drops:
            nm = [k for k in base_names if k != dr]
            w = wfit(nm)
            print(f"   - {dr:<16} age {w0['age']:+.4f} -> {w['age']:+.4f}")
        if drops:
            nm = [k for k in base_names if k not in drops]
            w = wfit(nm)
            print(f"   - ALL              age {w0['age']:+.4f} -> {w['age']:+.4f}")
        # marginal vs partial, for the record
        y = d["y"]
        print(f"   marginal Spearman(age, WAR) full pool {rho(col(s,'age'), y):+.4f}"
              f"   debuted-only {rho(col(s,'age')[d['deb']], y[d['deb']]):+.4f}")
        print(f"   Spearman(age, level_rank) {rho(col(s,'age'), col(s,'level_rank')):+.4f}"
              f"   Spearman(age, n_milb_seasons) "
              f"{rho(col(s,'age'), col(s,'n_milb_seasons')):+.4f}")
        # per-fold stability of the sign flip
        if s == "pit":
            print("   per-origin refit (train = decision_year < Y), age weight:")
            for yr in ORIGINS:
                t2 = np.flatnonzero(d["keep"] & (d["dy"] < yr))
                if len(t2) < 60:
                    continue
                def wf(names):
                    X = d["X"][:, [d["idx"][k] for k in names]]
                    rg = ridge_fit(X[t2], y[t2], d["w"][t2])
                    return dict(zip(names, rg[2]))
                a0 = wf(base_names)["age"]
                a1 = wf(base_names + ["level_rank"])["age"]
                a2 = wf(base_names + ["level_rank", "n_milb_seasons"])["age"]
                print(f"     {yr}: shipped {a0:+.4f} | +level_rank {a1:+.4f} "
                      f"| +level_rank+n_milb {a2:+.4f}   (n_train={len(t2)})")


def mode_residstrata():
    """THE DECISIVE (a) TEST. mode_strata measures the raw level x age surface, but the
    shipped model may already reproduce it through fv + age + age_rel_level + level_rank.
    What matters is whether the interaction survives IN THE OOF RESIDUAL. Full-pool frame
    (no debut-collider conditioning), weighted OLS slope of residual on age within level
    strata, bootstrapped contrast."""
    print("=== RESIDUAL level x age INTERACTION (does the shipped model already price it?) ===")
    for s in ("hit", "pit"):
        Xb, _ = build(s, "base")
        r = score(s, Xb, test_frame="full")
        b, p, t, deb = r
        idx, keep, dy = [], D[s]["keep"], D[s]["dy"]
        for yr in ORIGINS:
            if len(np.flatnonzero(keep & (dy < yr))) < 60 or \
               len(np.flatnonzero(keep & (dy == yr))) < 15:
                continue
            idx.append(np.flatnonzero(keep & (dy == yr)))
        idx = np.concatenate(idx)
        resid = t - p
        lv, ag = D[s]["X"][idx, D[s]["idx"]["level_rank"]], D[s]["X"][idx, D[s]["idx"]["age"]]
        has = D[s]["has"][idx]
        w = D[s]["w"][idx]
        rng = np.random.default_rng(SEED)
        print(f"\n--- {s.upper()} n={len(resid)} (milb-observed {int(has.sum())})")
        for frame, msk in (("ALL rows", np.ones(len(resid), bool)),
                           ("milb-observed only", has)):
            def sl(m, ix=None):
                a, tt, ww = ag[m], resid[m], w[m]
                if ix is not None:
                    a, tt, ww = a[ix], tt[ix], ww[ix]
                mx = np.average(a, weights=ww)
                my = np.average(tt, weights=ww)
                v = float((ww * (a - mx) ** 2).sum())
                return float((ww * (a - mx) * (tt - my)).sum()) / v if v > 0 else np.nan
            hi = msk & (lv >= 5)
            mid = msk & (lv >= 2) & (lv < 4)
            if hi.sum() < 40 or mid.sum() < 40:
                print(f"  {frame}: too few rows")
                continue
            nh, nl = int(hi.sum()), int(mid.sum())
            d0 = sl(hi) - sl(mid)
            ds = np.array([sl(hi, rng.integers(0, nh, nh)) - sl(mid, rng.integers(0, nl, nl))
                           for _ in range(2000)])
            ci = np.percentile(ds, [2.5, 97.5])
            print(f"  {frame:<20} resid-slope AAA {sl(hi):+.3f} (n={nh}) | "
                  f"A/A+ {sl(mid):+.3f} (n={nl}) | contrast {d0:+.3f} "
                  f"CI95 [{ci[0]:+.3f},{ci[1]:+.3f}] P(<0)={float((ds<0).mean()):.3f}")


def mode_strata():
    """EMPIRICAL RECOVERY of the level x age surface (the positional-ladder method:
    measure the shape instead of assuming it). If the age->outcome slope is materially
    different across levels, an interaction is warranted regardless of what a collinear
    ridge product does. Full pool, so the debut collider is not conditioned on."""
    print("=== EMPIRICAL level_rank x age SURFACE (full pool, no debut conditioning) ===")
    for s in ("hit", "pit"):
        d = D[s]
        y, deb, lv, ag = d["y"], d["deb"], col(s, "level_rank"), col(s, "age")
        w = d["w"]
        print(f"\n--- {s.upper()}  n={len(y)}")
        print(f"{'level':<8} {'n':>5} {'age p25/50/75':>18} {'deb%':>6} "
              f"{'meanWAR':>8} {'slope WAR/yr':>13} {'boot CI95':>20} {'rho(age,WAR)':>13}")
        rng = np.random.default_rng(SEED)
        for lo, hi, lab in ((0, 2, "0-1 cx/DSL"), (2, 4, "2-3 A/A+"),
                            (4, 5, "4 AA"), (5, 6, "5 AAA")):
            m = (lv >= lo) & (lv < hi)
            if m.sum() < 40:
                continue
            a, t = ag[m], y[m]
            q = np.percentile(a, [25, 50, 75])
            # weighted OLS slope of WAR on age within the stratum
            def slope(ix):
                aa, tt, ww = a[ix], t[ix], w[m][ix]
                mx = np.average(aa, weights=ww)
                my = np.average(tt, weights=ww)
                v = float((ww * (aa - mx) ** 2).sum())
                return float((ww * (aa - mx) * (tt - my)).sum()) / v if v > 0 else np.nan
            b0 = slope(np.arange(int(m.sum())))
            bs = np.array([slope(rng.integers(0, int(m.sum()), int(m.sum())))
                           for _ in range(2000)])
            ci = np.percentile(bs, [2.5, 97.5])
            print(f"{lab:<8} {int(m.sum()):>5} "
                  f"{q[0]:>6.1f}/{q[1]:.1f}/{q[2]:.1f}   {100*deb[m].mean():>5.1f} "
                  f"{t.mean():>8.2f} {b0:>13.3f} [{ci[0]:+7.3f},{ci[1]:+7.3f}] "
                  f"{rho(a, t):>13.4f}")
        # is the slope DIFFERENT across levels? bootstrap the AAA-minus-lowA contrast
        m_hi = lv >= 5
        m_lo = (lv >= 2) & (lv < 4)
        if m_hi.sum() > 40 and m_lo.sum() > 40:
            def sl(mask, ix=None):
                a, t, ww = ag[mask], y[mask], w[mask]
                if ix is not None:
                    a, t, ww = a[ix], t[ix], ww[ix]
                mx = np.average(a, weights=ww)
                my = np.average(t, weights=ww)
                v = float((ww * (a - mx) ** 2).sum())
                return float((ww * (a - mx) * (t - my)).sum()) / v if v > 0 else np.nan
            d0 = sl(m_hi) - sl(m_lo)
            nh, nl = int(m_hi.sum()), int(m_lo.sum())
            ds = np.array([sl(m_hi, rng.integers(0, nh, nh)) - sl(m_lo, rng.integers(0, nl, nl))
                           for _ in range(2000)])
            ci = np.percentile(ds, [2.5, 97.5])
            print(f"  CONTRAST slope(AAA) - slope(A/A+) = {d0:+.3f} "
                  f"CI95 [{ci[0]:+.3f},{ci[1]:+.3f}]  P(<0)={float((ds<0).mean()):.3f}")
            print("  (a NEGATIVE contrast is what the 'discount level credit for age' "
                  "hypothesis predicts)")
        # measured typical PROSPECT age by level, for the record
        print("  measured age quantiles are the PROSPECT population, not the level "
              "population; compare to efv_dataset._TYPICAL_LEVEL_AGE (owned by another lane)")


def mode_weights():
    """Standardized ridge weights on the PRODUCTION fit pool (full pool minus recent
    busts, KM weights) for base and each candidate arm. A correctly-signed but
    unresolvable weight is a different finding from a zero or wrong-signed one."""
    print("=== FITTED STANDARDIZED RIDGE WEIGHTS (production pool, full window) ===")
    for s in ("hit", "pit"):
        d = D[s]
        tr = np.flatnonzero(d["keep"])
        Xb, nb = build(s, "base")
        rg = ridge_fit(Xb[tr], d["y"][tr], d["w"][tr])
        wb = dict(zip(nb, rg[2]))
        print(f"\n--- {s.upper()} base (n={len(tr)})")
        print("   " + "  ".join(f"{k}={v:+.4f}" for k, v in wb.items()))
        for arm in CAND[s]:
            if arm in SPECIAL:
                continue
            Xa, na = build(s, arm)
            if len(na) == len(nb):
                continue
            rg2 = ridge_fit(Xa[tr], d["y"][tr], d["w"][tr])
            wa = dict(zip(na, rg2[2]))
            new = [k for k in na if k not in wb]
            print(f"  {arm:<18} new: " +
                  ", ".join(f"{k}={wa[k]:+.4f}" for k in new))
            moved = sorted(((abs(wa[k] - wb[k]), k) for k in wb if k in wa),
                           reverse=True)[:3]
            print(f"{'':<20} shifted: " +
                  ", ".join(f"{k} {wb[k]:+.4f}->{wa[k]:+.4f}" for _, k in moved))


def mode_bradfield():
    """CORRECTNESS read: what would the candidate age-interaction do to the specific
    live rows that motivated the sweep? Uses the live matrix if present."""
    p = ROOT / "data" / "xfv_live_matrix.json"
    if not p.exists():
        print("no data/xfv_live_matrix.json; skipping live read")
        return
    live = json.loads(p.read_text(encoding="utf-8"))
    print(f"live rows: {len(live)}")
    names = [r.get("name") or r.get("player_key") for r in live]
    for want in ("bradfield", "sloan", "arias"):
        for r, nm in zip(live, names):
            if want in str(nm).lower():
                m = r.get("milb") or {}
                print(f"  {nm}: level_rank={m.get('level_rank')} age={m.get('age')} "
                      f"age_rel_level={m.get('age_rel_level')} "
                      f"fv={r.get('consensus_fv_raw')} pit={r.get('is_pitcher')}")


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "point"
    t0 = time.time()
    if m == "point":
        mode_point(int(sys.argv[2]) if len(sys.argv) > 2 else 25)
    elif m == "boot":
        mode_boot(int(sys.argv[2]) if len(sys.argv) > 2 else 1000)
    elif m == "reportboot":
        report_boot()
    elif m == "pd":
        mode_pd()
    elif m == "speed":
        mode_speed()
    elif m == "weights":
        mode_weights()
    elif m == "brad":
        mode_bradfield()
    elif m == "pdfull":
        mode_pdfull()
    elif m == "agesign":
        mode_agesign()
    elif m == "strata":
        mode_strata()
    elif m == "residstrata":
        mode_residstrata()
    print("elapsed", round(time.time() - t0, 1), "s")
