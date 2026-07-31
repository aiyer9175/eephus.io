"""BIOMETRIC lane gate harness. Forward-chained folds + paired bootstrap (train AND
test, refit per draw) + row-permuted zero-information twin + permutation null band.
Scratch lab, READ-ONLY w.r.t. the repo."""
from __future__ import annotations
import sys, json, math
from collections import defaultdict
import numpy as np

ROOT = r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker"
sys.path.insert(0, ROOT + r"\tools"); sys.path.insert(0, ROOT)
import os; os.chdir(ROOT)
import efv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
import efv_lab_runner as LAB

BIO = json.load(open("tools/_arch_bio_feat.json"))
FOLDS_EXT = (2018, 2019, 2020, 2021, 2022, 2023)


def load(side):
    rows = list(LAB.data_for(side))
    for r in rows:
        b = BIO.get(side + "|" + r["player_key"]) or {}
        r["bio"] = {"bmi": b.get("bmi"), "h": b.get("h"), "w": b.get("w"),
                    "frame": b.get("frame"), "athl": b.get("athl"),
                    "levers": b.get("levers_num")}
    return rows


# ---------------------------------------------------------------------------
# bio block builders. ALL train-fold statistics only: mu/sd and any cut points
# are fit on TRAIN and applied forward to TEST. Missing -> train mean (0 after
# z) PLUS an explicit missing indicator, so "missing" is never encoded as an
# extreme value (the failure mode item E documents for efv_model._vec).
# ---------------------------------------------------------------------------

def _zfit(tr_vals):
    v = [x for x in tr_vals if x is not None]
    if len(v) < 30:
        return None
    mu = float(np.mean(v)); sd = float(np.std(v)) or 1.0
    return mu, sd


def _zap(z, x):
    if z is None or x is None:
        return 0.0
    return (x - z[0]) / z[1]


# the production / tool axes a body type is hypothesised to condition, per side.
# (a pitcher pool has no ops_rel or tool_speed, so reusing the hitter triple there
# makes the whole interaction block identically zero -- a degenerate test.)
_AXES = {"hit": ("ops_rel", "tool_speed", "tool_game_pwr"),
         "pit": ("k_rel", "tool_fb", "tool_cmd")}


def build_block(kind, tr, te, side="hit"):
    """-> (names, Xtr_block, Xte_block). Fit on tr, apply forward to te."""
    ax = _AXES[side]

    def col(rows, f):
        return [f(r) for r in rows]

    if kind == "none":
        return [], np.zeros((len(tr), 0)), np.zeros((len(te), 0))

    if kind in ("bmi", "linear", "arch_inter", "arch_strat"):
        zb = _zfit(col(tr, lambda r: r["bio"]["bmi"]))
        zh = _zfit(col(tr, lambda r: r["bio"]["h"]))
        zw = _zfit(col(tr, lambda r: r["bio"]["w"]))

        def base(rows):
            out = []
            for r in rows:
                b = r["bio"]
                miss = 1.0 if b["bmi"] is None else 0.0
                out.append([_zap(zb, b["bmi"]), _zap(zh, b["h"]), _zap(zw, b["w"]), miss])
            return np.array(out, dtype=float).reshape(len(rows), 4)

        Btr, Bte = base(tr), base(te)
        if kind == "bmi":
            return ["bmi_z", "bio_missing"], Btr[:, [0, 3]], Bte[:, [0, 3]]
        if kind == "linear":
            return ["bmi_z", "height_z", "weight_z", "bio_missing"], Btr, Bte

        if kind == "arch_inter":
            # ARCHETYPE AS INTERACTION: body type conditions WHICH skill translates.
            def inter(rows, B):
                p = np.array([[r["feats"].get(a, 0.0) for a in ax] for rows_i, r
                              in enumerate(rows)], dtype=float).reshape(len(rows), 3)
                obs = (1.0 - B[:, 3])[:, None]      # zero the interaction when bio missing
                bmi = B[:, 0][:, None]; hgt = B[:, 1][:, None]
                return np.hstack([B, bmi * p * obs, hgt * p * obs])
            names = (["bmi_z", "height_z", "weight_z", "bio_missing"] +
                     ["bmi_x_" + s for s in ax] + ["hgt_x_" + s for s in ax])
            return names, inter(tr, Btr), inter(te, Bte)

        if kind == "arch_strat":
            # ARCHETYPE AS STRATIFIER: 3 body-type buckets from TRAIN-fold BMI
            # terciles only (cut points never see a test row or any outcome),
            # then bucket dummies + bucket x production. Missing -> no dummy.
            v = [x for x in col(tr, lambda r: r["bio"]["bmi"]) if x is not None]
            if len(v) < 60:
                return [], np.zeros((len(tr), 0)), np.zeros((len(te), 0))
            q1, q2 = float(np.quantile(v, 1.0 / 3)), float(np.quantile(v, 2.0 / 3))

            def strat(rows):
                out = []
                for r in rows:
                    b = r["bio"]["bmi"]
                    d = [0.0, 0.0, 0.0]
                    if b is not None:
                        d[0 if b <= q1 else (1 if b <= q2 else 2)] = 1.0
                    ops = r["feats"].get(ax[0], 0.0)
                    spd = r["feats"].get(ax[1], 0.0)
                    out.append(d + [d[i] * ops for i in range(3)] + [d[i] * spd for i in range(3)])
                return np.array(out, dtype=float).reshape(len(rows), 9)
            names = (["lean_body", "mid_body", "heavy_body"] +
                     [n + "_x_" + ax[0] for n in ("lean", "mid", "heavy")] +
                     [n + "_x_" + ax[1] for n in ("lean", "mid", "heavy")])
            return names, strat(tr), strat(te)

    if kind == "frame":
        zf = _zfit(col(tr, lambda r: r["bio"]["frame"]))
        za = _zfit(col(tr, lambda r: r["bio"]["athl"]))
        zl = _zfit(col(tr, lambda r: r["bio"]["levers"]))

        def f(rows):
            out = []
            for r in rows:
                b = r["bio"]
                out.append([_zap(zf, b["frame"]), _zap(za, b["athl"]), _zap(zl, b["levers"]),
                            1.0 if b["frame"] is None else 0.0])
            return np.array(out, dtype=float).reshape(len(rows), 4)
        return ["frame_z", "athl_z", "levers_z", "frame_missing"], f(tr), f(te)

    raise ValueError(kind)


# ---------------------------------------------------------------------------
def _score_fold(tr, te, keys, kind, lam, side="hit"):
    names, Btr, Bte = build_block(kind, tr, te, side)
    Xtr = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in tr], dtype=float)
    Xte = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in te], dtype=float)
    if Btr.shape[1]:
        Xtr = np.hstack([Xtr, Btr]); Xte = np.hstack([Xte, Bte])
    allk = list(keys) + list(names)
    ytr = np.array([r["target_censored"] for r in tr], dtype=float)
    trd = [{"feats": {k: Xtr[i, j] for j, k in enumerate(allk)}, "target": float(ytr[i])}
           for i in range(len(ytr))]
    rg = _fit_ridge(trd, allk)
    if rg is None:
        return None
    pred = np.array([_predict(rg, {k: Xte[i, j] for j, k in enumerate(allk)})
                     for i in range(len(te))], dtype=float)
    ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
    if ols is None:
        return None
    cons = np.array([max(0.0, _pred_ols(ols, r["fv"])) for r in te], dtype=float)
    blended = lam * pred + (1 - lam) * cons
    truth = np.array([r["target_censored"] for r in te], dtype=float)
    fv = np.array([r["fv"] for r in te], dtype=float)
    return blended, pred, truth, fv


def evaluate(rows, kind, side, folds=FOLDS_EXT, lam=None, per_fold=False):
    lam = blend_lambda(side) if lam is None else lam
    keys = _feature_spec(side)[0]
    pooled_b, pooled_t, pooled_p, pooled_fv = [], [], [], []
    fold_rho = {}
    for yr in folds:
        tr = [r for r in rows if r["decision_year"] < yr and r["target_censored"] is not None]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        out = _score_fold(tr, te, keys, kind, lam, side)
        if out is None:
            continue
        b, p, t, fv = out
        if per_fold:
            fold_rho[yr] = (_spearman(list(b), list(t)), len(t))
        pooled_b += list(b); pooled_p += list(p); pooled_t += list(t); pooled_fv += list(fv)
    if len(pooled_b) < 30:
        return None
    b = np.array(pooled_b); t = np.array(pooled_t)
    p = np.array(pooled_p); fv = np.array(pooled_fv)
    res = {"n": len(b), "rho": _spearman(list(b), list(t)),
           "rho_pure": _spearman(list(p), list(t))}
    tier = np.round(fv / 5) * 5
    m45 = tier == 45
    res["t45"] = _spearman(list(b[m45]), list(t[m45])) if m45.sum() >= 12 else float("nan")
    num = den = 0.0
    for tv in np.unique(tier):
        m = tier == tv
        if m.sum() >= 12:
            r = _spearman(list(b[m]), list(t[m]))
            if r == r:
                num += r * m.sum(); den += m.sum()
    res["within_tier_wm"] = num / den if den else float("nan")
    if per_fold:
        res["per_fold"] = fold_rho
    return res


def permute_bio(rows, rng):
    """Zero-information twin: the SAME bio records, reassigned to random rows.
    Identical marginal distribution and identical missingness rate, no link to
    the player or the outcome."""
    bios = [r["bio"] for r in rows]
    idx = rng.permutation(len(rows))
    out = []
    for i, r in enumerate(rows):
        q = dict(r); q["bio"] = bios[idx[i]]
        out.append(q)
    return out
