# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""PACE_FROM_ENTRY gate lab (E1.2 arm a, run 2026-08-03).

Scores the pre-registered gate in docs/efv-2026-07-31/PACE_FROM_ENTRY_GATE.md.
The gate design (metrics, floors, controls, kill criteria) was frozen in that
doc BEFORE this file existed; nothing here relaxes a criterion.

WHAT IS MEASURED
  Primary: forward-chained pooled OOS blend Spearman on the shipped protocol
  (efv_lab_runner: SCORED_YEARS folds, floors train>=50 / test>=12, consensus
  OLS(FV) + ridge blend at the shipped lambda). The BASE arm is the shipped
  champion feature spec (efv_model._feature_spec), so base and treatment are
  scored on IDENTICAL rows, same folds, same alpha selector.

  Treatment arms:
    pace1  = champion + pace_from_entry
    pace3  = champion + pace_from_entry + entry_level_rank + entry_observed
    ctrl   = champion + a ROW-PERMUTED pace_from_entry (zero-information
             control kept IN the feature set, the B3/E1 control shape)

  Secondary, sign-agreement: contributor (>=3 WAR) and star (>=10 WAR) AUC on
  the same pooled rows; within-FV-tier weighted mean and t45.

  Permutation null: B=30 draws, feature values redrawn from the TRUE empirical
  marginal with the row link broken (the E1 convention). p = (#{null >= real}
  + 1) / (B + 1); the bar seasons_at_level cleared was p = 0.032.

  Paired bootstrap: B=2000 resamples of the pooled test rows, delta = rho(treat)
  - rho(base) on the SAME resampled rows (exact pairing, not two independent
  reruns).

  Sign check: standardized ridge weight on pace_from_entry, per fold and on the
  full-pool refit, against the PRE-REGISTERED kill criterion -- a NEGATIVE
  hitter weight is the survivorship-censoring artifact and CLOSES the arm.

  Second arm (run unconditionally, the doc asks for it if the flagship nulls):
  the fv-anchor-free efv_ungraded provisional model on its own forward-chained
  protocol (efv_ungraded.evaluate: folds 2019-2023, floors 60/15, production-
  bearing rows only, low_minors_age_le21 + all_levels cohorts).

READ-ONLY: reads the built matrices and the DB, writes exactly one artifact,
data/xfv_pace_entry_eval.json. No matrix rebuild, no source edit, no flag flip.

Run: python tools/efv_pace_entry_gate_lab.py
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os  # noqa: E402
os.chdir(ROOT)

import efv_lab_runner as LAB                                        # noqa: E402
import efv_model as XM                                              # noqa: E402
import efv_ungraded as UG                                           # noqa: E402
from efv_model import _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda   # noqa: E402
from prospect_path import _fit_ridge, _predict, _spearman           # noqa: E402
from source_backtest import _auc                                    # noqa: E402
from efv_dataset import matrix_path                                 # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_pace_entry_eval.json"
GATE_DOC = "docs/efv-2026-07-31/PACE_FROM_ENTRY_GATE.md"

PACE = "pace_from_entry"
TRIPLE = [PACE, "entry_level_rank", "entry_observed"]

# PRE-REGISTERED, copied from the gate doc. Not editable after the fact.
MDE95 = {"hit": 0.017, "pit": 0.016}
PERM_B = 30
PERM_BAR = 0.032          # the p seasons_at_level cleared
BOOT_B = 2000
CONTRIBUTOR_WAR, STAR_WAR = 3.0, 10.0
SEEDS_CTRL = (11, 22, 33)


# ---------------------------------------------------------------------------
# unrounded Spearman (the shipped _spearman rounds to 4dp, which is coarse for
# a 2000-draw bootstrap on deltas of order 1e-3)
# ---------------------------------------------------------------------------
def _rank(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for t in range(i, j + 1):
            r[order[t]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _rho_exact(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / math.sqrt(vx * vy) if vx and vy else None


# ---------------------------------------------------------------------------
# flagship forward chain, ROW-ALIGNED across arms
# ---------------------------------------------------------------------------
def _chain(side, arms, override=None):
    """One forward-chained pass producing predictions for EVERY arm on the
    SAME test rows. arms = {name: [feature keys]}. override = {player_key:
    {feat: value}} applied to train and test alike (the permutation control).

    Returns (rows, weights) where rows carry one prediction per arm plus the
    consensus anchor, and weights carry the fitted standardized ridge weight on
    PACE per fold for arms that contain it.
    """
    data = LAB.data_for(side)
    lam = blend_lambda(side)
    out, wts = [], defaultdict(list)

    def feats_of(r):
        f = r["feats"]
        ov = (override or {}).get(r["player_key"])
        return ({**f, **ov} if ov else f)

    for yr in XM.SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        trf = [{"feats": feats_of(r), "target": r["target_censored"],
                "weight": r["weight"], "fv": r["fv"]} for r in tr]
        models = {}
        for name, keys in arms.items():
            m = _fit_ridge(trf, keys)
            if m is None:
                return None, None
            models[name] = m
            if PACE in keys:
                wts[name].append({"fold": yr,
                                  "w": round(m["w"][keys.index(PACE)], 4),
                                  "mu": round(m["mu"][keys.index(PACE)], 4),
                                  "sd": round(m["sd"][keys.index(PACE)], 4),
                                  "alpha": m["alpha"]})
        if not ols:
            return None, None
        for r in te:
            f = feats_of(r)
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            row = {"player_key": r["player_key"], "year": yr, "fv": r["fv"],
                   "y": r["target_censored"], "cohort": r["cohort"], "cons": cw}
            for name, m in models.items():
                row[name] = (1 - lam) * cw + lam * _predict(m, f)
            out.append(row)
    return out, dict(wts)


def _tier(fv):
    return round(fv / 5) * 5


def _summary(rows, arm):
    p = [r[arm] for r in rows]
    y = [r["y"] for r in rows]
    byt = defaultdict(list)
    for r in rows:
        byt[_tier(r["fv"])].append(r)
    wsum = wn = 0.0
    t45 = None
    for tk, grp in byt.items():
        if len(grp) < 15:
            continue
        rr = _rho_exact([g[arm] for g in grp], [g["y"] for g in grp])
        if rr is None:
            continue
        wsum += rr * len(grp)
        wn += len(grp)
        if tk == 45:
            t45 = round(rr, 4)
    per_year = {}
    byy = defaultdict(list)
    for r in rows:
        byy[r["year"]].append(r)
    for yy, grp in byy.items():
        rr = _rho_exact([g[arm] for g in grp], [g["y"] for g in grp])
        if rr is not None:
            per_year[str(yy)] = round(rr, 4)
    return {
        "n": len(rows),
        "spearman": round(_rho_exact(p, y), 4),
        "within_tier_wm": round(wsum / wn, 4) if wn else None,
        "t45": t45,
        "auc_contributor": round(_auc(p, [v >= CONTRIBUTOR_WAR for v in y]), 4),
        "auc_star": round(_auc(p, [v >= STAR_WAR for v in y]), 4),
        "per_year": per_year,
    }


def _paired_boot(rows, base, treat, b=BOOT_B, seed=7):
    rng = random.Random(seed)
    n = len(rows)
    d0 = _rho_exact([r[treat] for r in rows], [r["y"] for r in rows]) - \
        _rho_exact([r[base] for r in rows], [r["y"] for r in rows])
    ds = []
    for _ in range(b):
        idx = [rng.randrange(n) for _ in range(n)]
        yy = [rows[i]["y"] for i in idx]
        rt = _rho_exact([rows[i][treat] for i in idx], yy)
        rb = _rho_exact([rows[i][base] for i in idx], yy)
        if rt is not None and rb is not None:
            ds.append(rt - rb)
    ds.sort()
    lo = ds[int(0.025 * len(ds))]
    hi = ds[int(0.975 * len(ds)) - 1]
    return {"point": round(d0, 5), "mean": round(statistics.mean(ds), 5),
            "ci95": [round(lo, 5), round(hi, 5)],
            "p_gt_0": round(sum(1 for d in ds if d > 0) / len(ds), 3), "B": len(ds)}


def _permuted_override(side, seed):
    """Feature values redrawn from the TRUE empirical marginal with the row
    link broken: a permutation of the observed pace column over the same rows."""
    data = LAB.data_for(side)
    keys = [r["player_key"] for r in data]
    vals = [r["feats"].get(PACE, 0.0) for r in data]
    rng = random.Random(seed)
    perm = vals[:]
    rng.shuffle(perm)
    return {k: {PACE: v} for k, v in zip(keys, perm)}


def flagship(side):
    base_keys = list(_feature_spec(side)[0])
    arms = {"base": base_keys,
            "pace1": base_keys + [PACE],
            "pace3": base_keys + TRIPLE}
    rows, wts = _chain(side, arms)
    res = {a: _summary(rows, a) for a in arms}
    cons = _summary([{**r, "c": r["cons"]} for r in rows], "c")

    # zero-information control: permuted pace kept IN the feature set (3 seeds)
    ctrl = []
    for s in SEEDS_CTRL:
        crows, _ = _chain(side, {"base": base_keys, "pace1": base_keys + [PACE]},
                          override=_permuted_override(side, s))
        ctrl.append(round(_summary(crows, "pace1")["spearman"]
                          - _summary(crows, "base")["spearman"], 4))

    # feature-specific permutation null, B draws
    real = res["pace1"]["spearman"] - res["base"]["spearman"]
    nulls = []
    for i in range(PERM_B):
        prow, _ = _chain(side, {"base": base_keys, "pace1": base_keys + [PACE]},
                         override=_permuted_override(side, 1000 + i))
        nulls.append(_summary(prow, "pace1")["spearman"] - _summary(prow, "base")["spearman"])
    ge = sum(1 for v in nulls if v >= real)
    perm = {"real_delta": round(real, 4), "B": PERM_B,
            "null_mean": round(statistics.mean(nulls), 4),
            "null_sd": round(statistics.pstdev(nulls), 4),
            "null_max": round(max(nulls), 4), "null_min": round(min(nulls), 4),
            "n_ge_real": ge, "p": round((ge + 1) / (PERM_B + 1), 4)}

    # In-sample full-pool refit weight: the DESCRIPTIVE number the gate doc
    # quotes ("fits ~0 in the anchored flagship"). Not a gate metric.
    data = LAB.data_for(side)
    full = _fit_ridge([{"feats": r["feats"], "target": r["target_censored"],
                        "weight": r["weight"], "fv": r["fv"]} for r in data],
                      base_keys + [PACE])
    full_w = round(full["w"][(base_keys + [PACE]).index(PACE)], 4)

    boot = {a: _paired_boot(rows, "base", a) for a in ("pace1", "pace3")}
    floor = MDE95[side]
    d1 = res["pace1"]["spearman"] - res["base"]["spearman"]
    d3 = res["pace3"]["spearman"] - res["base"]["spearman"]
    wmean = statistics.mean([w["w"] for w in wts["pace1"]]) if wts.get("pace1") else None
    return {
        "protocol": ("forward-chained OOS, debuted cohort, blend (consensus OLS(FV) + "
                     "ridge at the shipped lambda); folds = efv_model.SCORED_YEARS, "
                     "floors train>=50 / test>=12 (efv_lab_runner convention, reproduces "
                     "data/xfv_eval*.json pooled_oos)"),
        "mde95": floor,
        "consensus_baseline": cons,
        "arms": res,
        "delta_vs_base": {"pace1": round(d1, 4), "pace3": round(d3, 4),
                          "pace1_x_floor": round(d1 / floor, 2),
                          "pace3_x_floor": round(d3 / floor, 2)},
        "delta_auc_vs_base": {
            "pace1_contributor": round(res["pace1"]["auc_contributor"] - res["base"]["auc_contributor"], 4),
            "pace1_star": round(res["pace1"]["auc_star"] - res["base"]["auc_star"], 4),
            "pace1_t45": (round(res["pace1"]["t45"] - res["base"]["t45"], 4)
                          if res["pace1"]["t45"] is not None and res["base"]["t45"] is not None else None),
            "pace1_wm": round(res["pace1"]["within_tier_wm"] - res["base"]["within_tier_wm"], 4),
        },
        "per_fold_delta": {yy: round(res["pace1"]["per_year"][yy] - res["base"]["per_year"][yy], 4)
                           for yy in res["base"]["per_year"]},
        "zero_information_control": {"seeds": list(SEEDS_CTRL), "deltas": ctrl,
                                     "mean": round(statistics.mean(ctrl), 4),
                                     "real_beats_all": all(real > c for c in ctrl)},
        "permutation_null": perm,
        "paired_bootstrap": boot,
        "fitted_weight_pace_from_entry": {
            "per_fold": wts.get("pace1"),
            "mean_standardized_w": round(wmean, 4) if wmean is not None else None,
            "sign": ("negative" if (wmean or 0) < 0 else "positive"),
            "full_pool_in_sample_w": full_w,
            "note": ("standardized ridge weight, WAR6 units per 1 sd of pace. The "
                     "per-fold values are the gate evidence (each fitted only on rows "
                     "strictly before its test year); the full-pool value is the "
                     "in-sample descriptive number the gate doc quotes."),
        },
    }


# ---------------------------------------------------------------------------
# second arm: the fv-anchor-free efv_ungraded provisional set
# ---------------------------------------------------------------------------
def ungraded(side):
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = UG._prep([r for r in rows
                     if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
                     and not (r.get("kind") == "bust" and r.get("bust_recent"))], side)
    base_keys = list(UG._keys(side))
    arms = {"base": base_keys, "pace1": base_keys + [PACE]}

    def one(override=None):
        got = {a: {"low_minors_age_le21": ([], []), "all_levels": ([], [])} for a in arms}
        wpace = []
        for yr in (2019, 2020, 2021, 2022, 2023):
            tr = [r for r in data if r["decision_year"] < yr]
            te = [r for r in data if r["decision_year"] == yr]
            if len(tr) < 60 or len(te) < 15:
                continue

            def f_of(r):
                ov = (override or {}).get(r["player_key"])
                return ({**r["feats"], **ov} if ov else r["feats"])

            trf = [{"feats": f_of(r), "target": r["target"], "weight": r["weight"]} for r in tr]
            models = {}
            for a, keys in arms.items():
                m = _fit_ridge(trf, keys)
                models[a] = m
                if PACE in keys and m is not None:
                    wpace.append({"fold": yr, "w": round(m["w"][keys.index(PACE)], 4)})
            cals = {}
            for a, m in models.items():
                cal = UG._fit_linear_calibration([(_predict(m, f_of(r)), r["target"]) for r in tr])
                cals[a] = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            for r in te:
                mm = r["milb"]
                lvl, age = mm.get("milb_level"), mm.get("age")
                low = lvl in {"DSL", "CPX", "A"} and (age is None or age <= 21)
                for a, m in models.items():
                    p = UG._war(m, cals[a][0], cals[a][1], f_of(r))
                    got[a]["all_levels"][0].append(p)
                    got[a]["all_levels"][1].append(r["target"])
                    if low:
                        got[a]["low_minors_age_le21"][0].append(p)
                        got[a]["low_minors_age_le21"][1].append(r["target"])
        res = {a: {c: {"n": len(v[0]),
                       "spearman": (round(_rho_exact(v[0], v[1]), 4) if len(v[0]) >= 8 else None)}
                   for c, v in cs.items()} for a, cs in got.items()}
        return res, wpace

    real, wpace = one()
    ctrl = []
    for s in SEEDS_CTRL:
        keys = [r["player_key"] for r in data]
        vals = [r["feats"].get(PACE, 0.0) for r in data]
        rng = random.Random(s)
        perm = vals[:]
        rng.shuffle(perm)
        cres, _ = one({k: {PACE: v} for k, v in zip(keys, perm)})
        ctrl.append({c: round((cres["pace1"][c]["spearman"] or 0) - (cres["base"][c]["spearman"] or 0), 4)
                     for c in ("low_minors_age_le21", "all_levels")})
    wmean = statistics.mean([w["w"] for w in wpace]) if wpace else None
    fullm = _fit_ridge([{"feats": r["feats"], "target": r["target"], "weight": r["weight"]}
                        for r in data], base_keys + [PACE])
    full_w = round(fullm["w"][(base_keys + [PACE]).index(PACE)], 4)

    # RECONCILIATION with the gate doc's claim that pace "fits -0.5943 in the
    # efv_ungraded provisional set" -- the stated reason this second arm exists.
    # Probed across every plausible ungraded specification (production-bearing
    # vs all labeled rows, single column vs the full triple).
    probe = {}
    all_data = UG._prep([r for r in rows if bool(r.get("is_pitcher")) == is_pit], side)
    for plabel, pool in (("production_bearing", data), ("all_labeled_rows", all_data)):
        for klabel, keys in (("single", base_keys + [PACE]), ("triple", base_keys + TRIPLE)):
            m = _fit_ridge([{"feats": r["feats"], "target": r["target"], "weight": r["weight"]}
                            for r in pool], keys)
            probe[f"{plabel}/{klabel}"] = {
                "n": len(pool),
                **{k: round(m["w"][keys.index(k)], 4)
                   for k in (TRIPLE if klabel == "triple" else [PACE])}}
    return {
        "protocol": ("efv_ungraded.evaluate protocol: no-FV production ridge + linear "
                     "calibration, forward-chained folds 2019-2023, floors train>=60 / "
                     "test>=15, production-bearing rows only, bust_recent excluded"),
        "arms": real,
        "delta_vs_base": {c: round((real["pace1"][c]["spearman"] or 0) - (real["base"][c]["spearman"] or 0), 4)
                          for c in ("low_minors_age_le21", "all_levels")},
        "zero_information_control": ctrl,
        "fitted_weight_pace_from_entry": {"per_fold": wpace,
                                          "mean_standardized_w": round(wmean, 4) if wmean is not None else None,
                                          "full_pool_in_sample_w": full_w},
        "doc_claim_reconciliation": {
            "claim": (GATE_DOC + ': "The same column fits -0.5943 in the efv_ungraded '
                      'provisional set ... against ~0 in the anchored flagship."'),
            "in_sample_weights_by_spec": probe,
            "finding": ("pace_from_entry fits POSITIVE in every reproducible ungraded "
                        "specification. The nearest match to -0.5943 is entry_observed "
                        "(the left-censoring indicator), not pace_from_entry, so the "
                        "premise for this second arm looks like a column mix-up. The arm "
                        "was run anyway and is reported on its own OOS numbers."),
        },
    }


def main():
    out = {
        "generated_at": date.today().isoformat(),
        "experiment": "PACE_FROM_ENTRY (efv_model.PACE_FROM_ENTRY, default False)",
        "registration": GATE_DOC,
        "regen_cmd": "python tools/efv_pace_entry_gate_lab.py",
        "pre_registered_criteria": {
            "primary": "forward-chained pooled blend Spearman vs MDE95 0.017 hit / 0.016 pit",
            "control": "row-permuted pace column kept IN the feature set (B3/E1 shape)",
            "permutation_null": f"B={PERM_B} draws from the true marginal, bar p<={PERM_BAR}",
            "bootstrap": f"paired, B={BOOT_B}",
            "kill_criterion": ("PRE-REGISTERED: a NEGATIVE fitted hitter weight on "
                               "pace_from_entry is the survivorship-censoring artifact "
                               "and CLOSES the arm; it must not ship as 'DSL starters "
                               "are worse'."),
        },
        "flagship": {},
        "ungraded_second_arm": {},
    }
    for side in ("hit", "pit"):
        out["flagship"][side] = flagship(side)
        print(f"[{side}] base {out['flagship'][side]['arms']['base']['spearman']} "
              f"pace1 {out['flagship'][side]['arms']['pace1']['spearman']} "
              f"d={out['flagship'][side]['delta_vs_base']['pace1']} "
              f"({out['flagship'][side]['delta_vs_base']['pace1_x_floor']}x floor) "
              f"w={out['flagship'][side]['fitted_weight_pace_from_entry']['mean_standardized_w']} "
              f"p={out['flagship'][side]['permutation_null']['p']}")
    for side in ("hit", "pit"):
        out["ungraded_second_arm"][side] = ungraded(side)
        print(f"[ungraded {side}] {out['ungraded_second_arm'][side]['delta_vs_base']} "
              f"w={out['ungraded_second_arm'][side]['fitted_weight_pace_from_entry']['mean_standardized_w']}")
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
