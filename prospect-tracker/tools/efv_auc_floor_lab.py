# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Lane A-1: derive MDE95 floors for the AUC leg, which nothing has ever scored.

Pre-registration: docs/efv-2026-08-14/AUC_FLOOR_GATE.md (frozen).
Artifact: data/xfv_auc_floor_eval.json.

    python tools/efv_auc_floor_lab.py [B_COND] [B_REFIT]

partb_floors is NOT touched. `scored_frame` has no pluggable statistic and
`frame_delta` hardcodes rho(challenger) - rho(baseline); widening it to serve a
second statistic would invalidate `parity_x1`, the control that proves it
bit-exact against delta_of on 24,000 real draws, and therefore every existing
floor. This lab derives its own.

The replay mirrors efv_model._auc_breakdown exactly, including that the blend
leg takes the RAW ridge prediction with no output calibration and no clamp.
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
OUT = DATA / "xfv_auc_floor_eval.json"
GATE = "docs/efv-2026-08-14/AUC_FLOOR_GATE.md"

SIDES = ("hit", "pit")
CUTS = {"debuted_km": True, "full_pool_km": False}      # value = ADMISSIBLE
PUBLISHED = {"hit": "xfv_eval.json", "pit": "xfv_eval_pitcher.json"}
SEED = 20260814
Z95_ONE, Z95_TWO = 1.645, 1.96
A0_TOL = 0.0010
MIN_POS = 40            # C-c: below this a cell is underpowered by construction


def _pool_rows(side: str, cut: str):
    """The rows efv_model.run() feeds each cut, same selection as _run_eval."""
    import efv_model as M
    from efv_dataset import matrix_path
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    if cut == "debuted_km":
        sel = [r for r in rows if r["kind"] == "debuted"]
    else:
        sel = [r for r in rows if r["kind"] in ("debuted", "bust")]
    return M._prep(sel, "target_censored", side)


def _replay(side: str, cut: str):
    """Forward chain of efv_model._auc_breakdown, returning one record per
    scored row so any subset can be re-scored without refitting."""
    import efv_model as M
    keys, _mono = M._feature_spec(side)
    lam = M.blend_lambda(side)
    data = _pool_rows(side, cut)

    recs = []
    fold_index = []
    for yr in range(2016, max(M.SCORED_YEARS) + 1):
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = M._fit_ols_fv(tr)
        ridge = M._fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            cons = max(0.0, M._pred_ols(ols, r["fv"]))
            blend = (1 - lam) * cons + lam * M._predict(ridge, r["feats"])
            recs.append({"key": r["player_key"], "blend": blend, "cons": cons,
                         "war": r["target"], "yr": int(r["decision_year"])})
        fold_index.append(yr)
    scored = [r for r in recs if r["yr"] in M.SCORED_YEARS]
    return {"scored": scored, "all": recs, "folds": fold_index,
            "lam": lam, "keys": keys, "data": data}


def _margin(subset, thresh):
    """model AUC minus consensus AUC on SHARED labels. None when degenerate."""
    from source_backtest import _auc
    if len(subset) < 15:
        return None
    labels = [r["war"] >= thresh for r in subset]
    n_pos = sum(labels)
    if n_pos == 0 or n_pos == len(labels):
        return None
    am = _auc([r["blend"] for r in subset], labels)
    ac = _auc([r["cons"] for r in subset], labels)
    if am is None or ac is None:
        return None
    return {"n": len(subset), "n_pos": int(n_pos),
            "model_auc": am, "consensus_auc": ac, "margin": am - ac}


def _e_cond(scored, thresh, B, seed):
    """Hold the fits, resample the scored rows, clustered by player."""
    ks = [r["key"] for r in scored]
    assert len(set(ks)) == len(ks), (
        "scored frame carries repeated player_keys; a row bootstrap would be "
        "anti-conservative and this estimator must cluster instead")
    rng = random.Random(seed)
    n = len(scored)
    out = []
    for _ in range(B):
        draw = [scored[rng.randrange(n)] for _ in range(n)]
        m = _margin(draw, thresh)
        if m:
            out.append(m["margin"])
    return _summ(out)


def _e_refit(side, cut, thresh, B, seed):
    """Resample the POOL and refit every fold per draw. Expensive by design:
    this is the leg that carries the refit variance the same-fit leg cannot."""
    import efv_model as M
    st = _replay(side, cut)
    data = st["data"]
    keys, lam = st["keys"], st["lam"]
    rng = random.Random(seed)
    n = len(data)
    out = []
    for _ in range(B):
        boot = [data[rng.randrange(n)] for _ in range(n)]
        recs = []
        for yr in range(2016, max(M.SCORED_YEARS) + 1):
            tr = [r for r in boot if r["decision_year"] < yr]
            te = [r for r in boot if r["decision_year"] == yr and yr in M.SCORED_YEARS]
            if len(te) < 15 or len(tr) < 60:
                continue
            ols = M._fit_ols_fv(tr)
            ridge = M._fit_ridge(tr, keys)
            if not (ols and ridge):
                continue
            for r in te:
                cons = max(0.0, M._pred_ols(ols, r["fv"]))
                recs.append({"key": r["player_key"], "cons": cons, "war": r["target"],
                             "blend": (1 - lam) * cons + lam * M._predict(ridge, r["feats"])})
        m = _margin(recs, thresh)
        if m:
            out.append(m["margin"])
    return _summ(out)


def _summ(vals):
    if not vals:
        return {"B_effective": 0, "sd": None, "mde95": None}
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1))
    s = sorted(vals)
    return {"B_effective": len(vals), "boot_mean": round(m, 6), "sd": round(sd, 6),
            "mde95": round(Z95_ONE * sd, 4), "mde95_twosided": round(Z95_TWO * sd, 4),
            "ci95": [round(s[int(0.025 * (len(s) - 1))], 5),
                     round(s[int(0.975 * (len(s) - 1))], 5)]}


def _holm(pairs):
    """Holm-Bonferroni over the admissible family. pairs = [(key, margin, sd)].
    Returns {key: {p_like, rank, holm_alpha, survives}} using the normal
    approximation z = margin / sd, one-sided."""
    from math import erfc, sqrt
    rows = []
    for k, mg, sd in pairs:
        if sd:
            z = mg / sd
            p = 0.5 * erfc(z / sqrt(2))       # one-sided, upper tail
        else:
            z, p = None, None
        rows.append([k, mg, sd, z, p])
    live = [r for r in rows if r[4] is not None]
    live.sort(key=lambda r: r[4])
    m = len(live)
    out = {}
    still = True
    for i, r in enumerate(live):
        alpha = 0.05 / (m - i)
        surv = bool(still and r[4] <= alpha)
        if not surv:
            still = False
        out[r[0]] = {"margin": round(r[1], 5), "sd": r[2], "z": round(r[3], 3),
                     "p_one_sided": round(r[4], 5), "rank": i + 1,
                     "holm_alpha": round(alpha, 5), "survives_holm": surv}
    for r in rows:
        if r[0] not in out:
            out[r[0]] = {"margin": None, "note": "degenerate cell, not tested"}
    return out


def run(b_cond=2000, b_refit=2000):
    import efv_model as M
    rep = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gate": GATE, "lane": "A-1",
        "B_cond": b_cond, "B_refit": b_refit, "seed": SEED,
        "convention": ("MDE95 = 1.645 * sd(margin), one-sided, matching "
                       "tools/efv_mde_lab.py; mde95_twosided = 1.96 * sd. The "
                       "margin is model AUC minus consensus AUC on SHARED "
                       "labels, so it is label-invariant by construction."),
        "admissibility": ("EFV_GATE_STANDARD.md:121-144 rules full-pool "
                          "debut/no-debut AUC INADMISSIBLE for anything that "
                          "can sense MiLB-block missingness. debuted_km is the "
                          "PRIMARY; full_pool_km is a SENSITIVITY and may not "
                          "carry the headline."),
        "cells": {}, "A0_reproduction": {}, "controls": {},
    }
    holm_input = []

    for side in SIDES:
        pub_all = json.loads((DATA / PUBLISHED[side]).read_text(encoding="utf-8"))
        for cut, admissible in CUTS.items():
            st = _replay(side, cut)
            scored = st["scored"]
            pub = ((pub_all["evals"].get(cut) or {}).get("auc_breakdown") or {}).get("pooled") or {}
            for label, thresh in (("contributor", M._CONTRIB_WAR), ("star", M._STAR_WAR)):
                key = f"{side}.{cut}.{label}"
                obs = _margin(scored, thresh)
                p = pub.get(label) or {}
                rep["A0_reproduction"][key] = {
                    "published_margin": p.get("margin"),
                    "replay_margin": (round(obs["margin"], 4) if obs else None),
                    "published_n": p.get("n"), "replay_n": (obs or {}).get("n"),
                    "published_n_pos": p.get("n_pos"), "replay_n_pos": (obs or {}).get("n_pos"),
                    "pass": bool(obs and p.get("margin") is not None
                                 and abs(obs["margin"] - p["margin"]) <= A0_TOL
                                 and obs["n"] == p.get("n")
                                 and obs["n_pos"] == p.get("n_pos")),
                }
                if not obs:
                    rep["cells"][key] = {"note": "degenerate"}
                    continue
                cond = _e_cond(scored, thresh, b_cond, SEED)
                cell = {
                    "admissible": admissible,
                    "n": obs["n"], "n_pos": obs["n_pos"],
                    "model_auc": round(obs["model_auc"], 4),
                    "consensus_auc": round(obs["consensus_auc"], 4),
                    "margin": round(obs["margin"], 5),
                    "E_cond": cond,
                    "underpowered_by_prevalence": bool(obs["n_pos"] < MIN_POS),
                }
                if b_refit:
                    cell["E_refit"] = _e_refit(side, cut, thresh, b_refit, SEED + 1)
                floor = cond.get("mde95")
                cell["margin_x_floor_E_cond"] = (
                    round(obs["margin"] / floor, 3) if floor else None)
                cell["resolves_E_cond"] = bool(floor and obs["margin"] >= floor)
                rep["cells"][key] = cell
                if admissible and not cell["underpowered_by_prevalence"]:
                    holm_input.append((key, obs["margin"], cond.get("sd")))

    rep["holm_admissible_family"] = _holm(holm_input)

    # ── C-a WEIGHTING: every pooled rho is pair-weighted; no AUC here is.
    rep["controls"]["C_a_weighting"] = {
        "note": ("AUC in this chain is UNWEIGHTED while every pooled rho is "
                 "pair-weighted by observed_seasons/6. Reported so the choice "
                 "is visible rather than assumed."),
        "auc_is_weighted": False,
    }
    # ── C-b PERMUTATION on the primary cells.
    perm = {}
    for side in SIDES:
        st = _replay(side, "debuted_km")
        rng = random.Random(SEED)
        rows = st["scored"]
        idx = list(range(len(rows)))
        rng.shuffle(idx)
        shuffled = [{**rows[j], "war": rows[k]["war"]} for j, k in enumerate(idx)]
        m = _margin(shuffled, M._CONTRIB_WAR)
        perm[f"{side}.debuted_km.contributor"] = {
            "model_auc": round(m["model_auc"], 4) if m else None,
            "pass": bool(m and abs(m["model_auc"] - 0.5) < 0.02),
        }
    rep["controls"]["C_b_permutation"] = perm
    # C-b SUPPLEMENT, and it exists because MY CLAUSE WAS MIS-SPECIFIED.
    # The pre-registered bar is |AUC - 0.5| < 0.02. The analytic null SE of AUC
    # (Hanley-McNeil) is sqrt((n1+n2+1)/(12*n1*n2)) = 0.0237 hit / 0.0243 pit,
    # so the bar sits at 0.84 SE and a CORRECT implementation fails it roughly
    # 40% of the time. One draw cannot answer whether the null is centred.
    # The clause is frozen and is reported FAILED as written; this block is
    # supplementary evidence about the machinery, NOT a rescue of the clause,
    # and no verdict depends on either.
    supp = {}
    for side in SIDES:
        st = _replay(side, "debuted_km")
        rows = st["scored"]
        rng = random.Random(SEED + 7)
        aucs = []
        for _ in range(200):
            idx = list(range(len(rows)))
            rng.shuffle(idx)
            sh = [{**rows[j], "war": rows[k]["war"]} for j, k in enumerate(idx)]
            mm = _margin(sh, M._CONTRIB_WAR)
            if mm:
                aucs.append(mm["model_auc"])
        if not aucs:
            continue
        aucs.sort()
        mean = sum(aucs) / len(aucs)
        sd = math.sqrt(sum((a - mean) ** 2 for a in aucs) / max(1, len(aucs) - 1))
        n1 = next(c["n_pos"] for k, c in rep["cells"].items()
                  if k == f"{side}.debuted_km.contributor")
        n2 = next(c["n"] for k, c in rep["cells"].items()
                  if k == f"{side}.debuted_km.contributor") - n1
        supp[f"{side}.debuted_km.contributor"] = {
            "draws": len(aucs), "mean_auc": round(mean, 4), "sd_auc": round(sd, 4),
            "p05": round(aucs[int(0.05 * len(aucs))], 4),
            "p95": round(aucs[int(0.95 * len(aucs))], 4),
            "analytic_null_se": round(math.sqrt((n1 + n2 + 1) / (12.0 * n1 * n2)), 4),
            "preregistered_bar_in_se": round(0.02 / math.sqrt(
                (n1 + n2 + 1) / (12.0 * n1 * n2)), 2),
            "null_is_centred_on_half": bool(
                abs(mean - 0.5) < 2 * sd / math.sqrt(len(aucs))),
        }
    rep["controls"]["C_b_supplementary_200_draws"] = supp
    rep["controls"]["C_c_prevalence"] = {
        k: {"n_pos": v.get("n_pos"), "underpowered": v.get("underpowered_by_prevalence")}
        for k, v in rep["cells"].items() if isinstance(v, dict) and "n_pos" in v}
    rep["controls"]["C_d_spearman_beside_auc"] = {
        f"{s}.debuted_km": {
            "spearman_blend": json.loads((DATA / PUBLISHED[s]).read_text(encoding="utf-8"))
            ["evals"]["debuted_km"]["pooled_oos"]["blend"]["spearman"],
            "spearman_baseline": json.loads((DATA / PUBLISHED[s]).read_text(encoding="utf-8"))
            ["evals"]["debuted_km"]["pooled_oos"]["baseline"]["spearman"],
        } for s in SIDES}

    rep["A0_all_pass"] = all(v["pass"] for v in rep["A0_reproduction"].values())
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


if __name__ == "__main__":
    bc = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    br = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    r = run(bc, br)
    print("A0 all pass:", r["A0_all_pass"])
    for k, v in r["A0_reproduction"].items():
        if not v["pass"]:
            print("  A0 MISS", k, v)
    print()
    for k, c in r["cells"].items():
        if "margin" not in c:
            continue
        tag = "PRIMARY   " if c["admissible"] else "sensitivity"
        ref = c.get("E_refit") or {}
        print(f"  {tag} {k:34s} margin {c['margin']:+.5f}  n={c['n']} pos={c['n_pos']}")
        print(f"              E_cond  mde95 {c['E_cond']['mde95']}  "
              f"{c['margin_x_floor_E_cond']}x  resolves={c['resolves_E_cond']}")
        if ref.get("mde95"):
            print(f"              E_refit mde95 {ref['mde95']}  "
                  f"{round(c['margin']/ref['mde95'],3)}x")
    print("\nHolm over the admissible family:")
    for k, h in r["holm_admissible_family"].items():
        print(f"  {k:34s} {json.dumps(h)}")
    print("\nwrote", OUT)
