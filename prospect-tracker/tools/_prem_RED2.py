# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ADVERSARIAL RE-DERIVATION 2: the shrinkage arm on a CLEAN split, production spec.

Fixes three specification defects in tools/_prem_shrink_lab.py:
  1. trains on the FULL labeled pool (debuted + non-recent busts), as production does
  2. applies the linear output calibration to the model leg, as production does
  3. fits the consensus OLS anchor on the same full pool, as production does
and adds two leakage checks the original lane did not run:
  4. an OUTCOME-BLIND stratum grid beside the brief's outcome-derived cut
  5. rho on the FULL labeled OOS set (busts included) beside debuted-only

Per-stratum lambda is estimated by an inner forward chain inside TRAIN only.
Read-only. Prints only.
"""
from __future__ import annotations
import json, random, sys, statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import efv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import (_fit_ols_fv, _pred_ols, blend_lambda, _feature_spec,
                       _prep, _fit_linear_calibration)
from efv_dataset import matrix_path

LAM_GRID = [round(0.05 * i, 2) for i in range(21)]
MIN_STRAT_N = 25
INNER_MIN_TR, INNER_MIN_TE = 50, 8


def load(side):
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(full, "target_censored", side)
    by = {r["player_key"]: r for r in full}
    out = []
    for d in data:
        src = by[d["player_key"]]
        m = src.get("milb") if isinstance(src.get("milb"), dict) else {}
        lr, arl, ops = m.get("level_rank"), m.get("age_rel_level"), m.get("ops_rel")
        # (i) the brief's cut -- DERIVED FROM RESOLVED OUTCOMES (contaminated)
        strat_brief = None
        if lr is not None and arl is not None:
            strat_brief = ("HIGH" if lr >= 5 else ("MID" if lr >= 4 else "LOW")) + "/" + \
                          ("OLD" if arl >= 0 else "YOUNG") + "/" + \
                          ("BELOW" if (ops is not None and ops < 0) else "ABOVE")
        # (ii) OUTCOME-BLIND grid: level x acquisition x seasons-in-system.
        #      None of these cuts was chosen by looking at realized WAR.
        strat_blind = None
        if lr is not None:
            acq = "COL" if d["feats"].get("is_college") else ("IFA" if d["feats"].get("is_ifa") else "HS")
            ns = m.get("n_milb_seasons")
            sb = "SHORT" if (ns is None or ns <= 2) else ("MID" if ns <= 4 else "LONG")
            strat_blind = ("HIGH" if lr >= 5 else ("MID" if lr >= 4 else "LOW")) + "/" + acq + "/" + sb
        d["kind"] = src["kind"]
        d["served"] = bool(m.get("milb_level"))
        d["strat_brief"] = strat_brief
        d["strat_blind"] = strat_blind
        d["is_target"] = (m.get("milb_level") == "AAA" and (m.get("age") or 0) >= 23.5
                          and (m.get("ops_rel") or 0) < 0)
        out.append(d)
    return out


def fit(tr, keys):
    ridge = _fit_ridge(tr, keys)
    ols = _fit_ols_fv(tr)
    if not (ridge and ols):
        return None
    cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    return {"ridge": ridge, "ols": ols, "a": a, "b": b}


def legs(f, r):
    cw = max(0.0, _pred_ols(f["ols"], r["fv"]))
    mw = max(-2.0, f["a"] + f["b"] * _predict(f["ridge"], r["feats"]))
    return cw, mw


def inner_oof(tr, keys, skey):
    years = sorted({r["decision_year"] for r in tr})
    oof = []
    for y in years:
        itr = [r for r in tr if r["decision_year"] < y]
        ite = [r for r in tr if r["decision_year"] == y]
        if len(itr) < INNER_MIN_TR or len(ite) < INNER_MIN_TE:
            continue
        f = fit(itr, keys)
        if not f:
            continue
        for r in ite:
            cw, mw = legs(f, r)
            oof.append((mw, cw, r["target"], r.get(skey)))
    return oof


def lam_map(oof, lam_g, mode, param):
    by = defaultdict(list)
    for mw, cw, y, s in oof:
        if s is None:
            continue
        by[s].append((mw, cw, y))
    lams, diag = {}, {}
    for s, g in by.items():
        if len(g) < MIN_STRAT_N:
            continue
        ys = [y for _, _, y in g]
        if mode == "hier":
            best, bl = None, lam_g
            for l in LAM_GRID:
                rr = _spearman([(1 - l) * cw + l * mw for mw, cw, _ in g], ys)
                if rr is not None and (best is None or rr > best):
                    best, bl = rr, l
            k = float(param)
            lams[s] = (len(g) * bl + k * lam_g) / (len(g) + k)
            diag[s] = {"n": len(g), "lamhat": bl}
        else:
            rp = _spearman([mw - cw for mw, cw, _ in g], ys)
            lams[s] = lam_g * (1.0 - float(param)) if (rp is not None and rp <= 0) else lam_g
            diag[s] = {"n": len(g), "rho_prem": None if rp is None else round(rp, 4)}
    return lams, diag


def run_arm(side, folds, mode, param, skey="strat_brief", rand_seed=None, rows=None,
            collect=False):
    keys = _feature_spec(side)[0]
    lam_g = blend_lambda(side)
    if mode == "global":
        lam_g = float(param)
    if rows is None:
        rows = load(side)
    rand = {}
    if rand_seed is not None:
        rnd = random.Random(rand_seed)
        lab = [r for r in rows if r.get(skey) is not None]
        ls = [r[skey] for r in lab]
        rnd.shuffle(ls)
        for r, l in zip(lab, ls):
            rand[r["player_key"]] = l
    res, log = [], {}
    for yr in folds:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(tr) < 60 or len(te) < 15:
            continue
        f = fit(tr, keys)
        if not f:
            continue
        lams = {}
        if mode != "global":
            key_used = skey
            if rand_seed is not None:
                for r in tr:
                    r["_rs"] = rand.get(r["player_key"])
                key_used = "_rs"
            lams, diag = lam_map(inner_oof(tr, keys, key_used), lam_g,
                                 "hier" if mode == "hier" else "gate", param)
            if collect:
                log[yr] = diag
        for r in te:
            cw, mw = legs(f, r)
            s = rand.get(r["player_key"]) if rand_seed is not None else r.get(skey)
            l = lam_g if mode == "global" else lams.get(s, lam_g)
            res.append({"b": (1 - l) * cw + l * mw, "y": r["target"], "kind": r["kind"],
                        "served": r["served"], "is_target": r["is_target"],
                        "lam": l, "fv": r["fv"], "strat": r.get(skey)})
    return res, log


def summarize(res):
    deb = [x for x in res if x["kind"] == "debuted"]
    srv = [x for x in res if x["served"]]
    tgt = [x for x in res if x["is_target"]]
    def rho(s):
        return None if len(s) < 15 else _spearman([x["b"] for x in s], [x["y"] for x in s])
    return {"n_all": len(res), "rho_all": rho(res),
            "n_deb": len(deb), "rho_deb": rho(deb),
            "n_srv": len(srv), "rho_srv": rho(srv),
            "n_tgt": len(tgt), "rho_tgt": rho(tgt),
            "mean_lam": round(st.mean(x["lam"] for x in res), 4)}


def main():
    side = "hit"
    rows = load(side)
    print("pool", len(rows), "debuted", sum(1 for r in rows if r["kind"] == "debuted"))
    for label, folds in (("SHIPPED FOLDS 2020-2023", XM.SCORED_YEARS),
                         ("EXTENDED FOLDS 2018-2023", (2018, 2019, 2020, 2021, 2022, 2023))):
        print("\n" + "=" * 96)
        print(label)
        arms = [("BASE lam=0.70", "global", 0.70, "strat_brief", None),
                ("GLOB lam=0.50", "global", 0.50, "strat_brief", None),
                ("GLOB lam=1.00", "global", 1.00, "strat_brief", None),
                ("GLOB lam=0.00", "global", 0.00, "strat_brief", None),
                ("HIER k=25 BRIEF strata", "hier", 25, "strat_brief", None),
                ("HIER k=25 BLIND strata", "hier", 25, "strat_blind", None),
                ("HIER k=25 RANDOM ctrl", "hier", 25, "strat_brief", 11),
                ("GATE dip=0.5 BRIEF", "gate", 0.5, "strat_brief", None),
                ("GATE dip=0.5 BLIND", "gate", 0.5, "strat_blind", None),
                ("GATE dip=0.5 RANDOM ctrl", "gate", 0.5, "strat_brief", 11)]
        print(f"  {'arm':<26s} {'rho_all':>8s} {'rho_deb':>8s} {'rho_srv':>8s} "
              f"{'rho_tgt':>8s} {'n_tgt':>5s} {'meanlam':>8s}")
        for nm, mode, prm, sk, sd in arms:
            res, _ = run_arm(side, folds, mode, prm, skey=sk, rand_seed=sd, rows=rows)
            s = summarize(res)
            def f(v): return "   n/a " if v is None else f"{v:8.4f}"
            print(f"  {nm:<26s} {f(s['rho_all'])} {f(s['rho_deb'])} {f(s['rho_srv'])} "
                  f"{f(s['rho_tgt'])} {s['n_tgt']:5d} {s['mean_lam']:8.4f}")


if __name__ == "__main__":
    raise SystemExit(main())
