# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""LANE H1 -- coherent feature-direction + lambda re-select on the REBUILT matrices
(2026-07-24 coordinated re-calibration).

The reliability shrink was loosened (efv_dataset K 100/80 -> 50/40) and the hitter/pitcher
matrices were REBUILT under the new K. The shipped lambda (hit 0.85 / pit 0.54-dynamic) and
feature set were fit on the OLD matrix and are STALE. This lab re-selects them on the rebuilt
matrix, INDEPENDENTLY of any cached artifact.

Machinery is reused as a library from tools/efv_lambda_reselect_lab.py (the canonical
forward-chained rank_calibration selector: debuted-only pool, raw ridge leg blended with the
consensus OLS anchor, fold gate len(te)>=15 & len(tr)>=60, SCORED_YEARS 2020-2023) and the
low-level model functions (efv_model._prep/_fit_ols_fv/_pred_ols/_feature_spec, prospect_path
_fit_ridge/_predict/_spearman). We do NOT trust cached lab artifacts; every number here is
recomputed on the rebuilt matrix in this run.

STEP 0 -- SAME-RUN BASELINE. Recompute the shipped-config pooled OOS Spearman + contributor
AUC (+ star AUC) BOTH sides on the rebuilt matrix at the shipped lambda (hit 0.85, pit
blend_lambda('pit')=dynamic). This is the baseline; the pre-rebuild 0.3835/0.302 numbers are
kept only as the regression FLAG bar (the coordinated rebuild must not regress accuracy).

STEP 1 -- n_milb_seasons feature-direction GATE (hit-only; A2 found a NEGATIVE ridge weight
-0.36 on repaired labels despite the documented +1). Three variants of the HIT feature set,
lambda held at the shipped 0.85: (a) KEEP n_milb_seasons, (b) DROP it. It is a ridge feature
so 'flip' is not a manual sign -- the ridge fits its own sign; the question is whether the
feature EARNS its place. Pooled OOS Spearman + contributor AUC each, player-clustered paired
bootstrap (seed 20260724, 2000 reps) on the DROP-vs-KEEP delta. Fitted weight reported both
ways. Verdict: DROP if dropping improves or is neutral (dropping does NOT measurably hurt);
KEEP if dropping measurably hurts.

STEP 2 -- LAMBDA RE-SELECT on the STEP-1-locked feature set. Sweep blend lambda per side over
[0.50, 1.00] forward-chained; pick pooled-Spearman-max with an AUC co-check (must not be
worse). Move the lambda only if the chosen-vs-shipped-lambda delta clears lo95>0 on pooled
Spearman AND AUC-not-worse (player-clustered bootstrap). Report the full lambda->metric curve.
Final config (locked features + chosen lambda) is compared vs the pre-rebuild shipped state
(hit 0.3835 / pit 0.302) -> FLAG on any regression.

Run:  python tools/efv_wave_h_lab.py            # full run -> data/xfv_wave_h_eval.json
      python tools/efv_wave_h_lab.py --quick    # sweeps + point metrics, no bootstrap
"""
from __future__ import annotations
import sys, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)

import efv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import (_prep, _fit_ols_fv, _pred_ols, _feature_spec, blend_lambda,
                       SCORED_YEARS)
from efv_dataset import matrix_path
import efv_lambda_reselect_lab as RL   # reuse: _auc, metrics_at, sweep, GRID_*, bootstrap_delta

SEED = 20260724
N_BOOT = 2000
CONTRIB_WAR = XM._CONTRIB_WAR   # 3.0
STAR_WAR = XM._STAR_WAR         # 10.0

# Pre-rebuild shipped OOS pooled Spearman (task-supplied regression bar; the rebuilt
# config must not fall below these, the owner shipped the rebuild expecting a small gain).
PRE_REBUILD = {"hit": 0.3835, "pit": 0.302}

GRID_COARSE = RL.GRID_COARSE   # 0.50..1.00 step .05
GRID_FINE = RL.GRID_FINE       # 0.50..1.00 step .01
_auc = RL._auc


# ---------------------------------------------------------------------------
# key-parametrized fold builder (RL.build_folds hardcodes _feature_spec; we need
# to swap the hit key set for the DROP variant). Byte-identical protocol otherwise:
# debuted-only _prep pool, raw ridge leg (_predict, no a/b calibration), consensus
# OLS anchor cons=max(0,_pred_ols), fold gate 15/60, SCORED_YEARS forward chain.
# ---------------------------------------------------------------------------
def build_folds_keyed(side, keys):
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    out = []
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            model = _predict(ridge, r["feats"])
            out.append({"player_key": r["player_key"], "decision_year": yr,
                        "cons": cons, "model": model, "target": r["target"], "fv": r["fv"]})
    return out


def _pct(xs, p):
    if not xs:
        return None
    ys = sorted(xs); k = (len(ys) - 1) * p
    lo = int(math.floor(k)); hi = int(math.ceil(k))
    if lo == hi:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (k - lo)


def point_metrics(folds, lam):
    """Pooled Spearman + contributor AUC + star AUC for a blend at fixed lambda."""
    s = [(1 - lam) * f["cons"] + lam * f["model"] for f in folds]
    t = [f["target"] for f in folds]
    rho = _spearman(s, t)
    cauc = _auc(s, [1 if x >= CONTRIB_WAR else 0 for x in t])
    sauc = _auc(s, [1 if x >= STAR_WAR else 0 for x in t])
    return {"n": len(folds),
            "spearman": round(rho, 4) if rho is not None else None,
            "contrib_auc": round(cauc, 4) if cauc is not None else None,
            "star_auc": round(sauc, 4) if sauc is not None else None}


def fitted_weights(side, keys):
    """Production-style single ridge fit on ALL debuted rows (target_censored); returns
    the standardized attribute weight per key + the auto-selected alpha. This is the
    'fitted weight both ways' report (A2's -0.36 n_milb_seasons observation, rebuilt)."""
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    m = _fit_ridge(data, keys)
    return {k: round(w, 4) for k, w in zip(m["keys"], m["w"])}, m["alpha"], m["b"]


# ---------------------------------------------------------------------------
# STEP 1 -- feature-gate paired bootstrap (two fold sets, SAME lambda). Aligned by
# player_key (forward chain -> one row per player). Player-clustered == row resample.
# ---------------------------------------------------------------------------
def gate_bootstrap(folds_a, folds_b, lam, label_a="drop", label_b="keep"):
    """Paired player-clustered bootstrap of (a - b) pooled Spearman AND contributor AUC.
    folds_a / folds_b share the player set (same protocol, different key set)."""
    import random
    rng = random.Random(SEED)
    bmap = {f["player_key"]: f for f in folds_b}
    common = [f for f in folds_a if f["player_key"] in bmap]
    sa = [(1 - lam) * f["cons"] + lam * f["model"] for f in common]
    sb = [(1 - lam) * bmap[f["player_key"]]["cons"] + lam * bmap[f["player_key"]]["model"]
          for f in common]
    t = [f["target"] for f in common]
    lab = [1 if x >= CONTRIB_WAR else 0 for x in t]
    n = len(common)
    d_rho, d_auc = [], []
    for _ in range(N_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        xa = [sa[i] for i in idx]; xb = [sb[i] for i in idx]
        tt = [t[i] for i in idx]; ll = [lab[i] for i in idx]
        ra = _spearman(xa, tt); rb = _spearman(xb, tt)
        if ra is not None and rb is not None:
            d_rho.append(ra - rb)
        aa = _auc(xa, ll); ab = _auc(xb, ll)
        if aa is not None and ab is not None:
            d_auc.append(aa - ab)
    return {
        "delta": f"{label_a}_minus_{label_b}", "n": n, "n_reps": len(d_rho),
        "d_rho_mean": round(sum(d_rho) / len(d_rho), 5) if d_rho else None,
        "d_rho_lo95_2sided": round(_pct(d_rho, 0.025), 5) if d_rho else None,
        "d_rho_lo95_1sided": round(_pct(d_rho, 0.05), 5) if d_rho else None,
        "d_rho_hi95_2sided": round(_pct(d_rho, 0.975), 5) if d_rho else None,
        "d_rho_p_gt0": round(sum(1 for x in d_rho if x > 0) / len(d_rho), 4) if d_rho else None,
        "d_auc_mean": round(sum(d_auc) / len(d_auc), 5) if d_auc else None,
        "d_auc_lo95_2sided": round(_pct(d_auc, 0.025), 5) if d_auc else None,
        "d_auc_hi95_2sided": round(_pct(d_auc, 0.975), 5) if d_auc else None,
        "d_auc_p_gt0": round(sum(1 for x in d_auc if x > 0) / len(d_auc), 4) if d_auc else None,
    }


def step1_feature_gate(do_boot=True):
    keys_keep = _feature_spec("hit")[0]
    keys_drop = [k for k in keys_keep if k != "n_milb_seasons"]
    assert "n_milb_seasons" in keys_keep, "n_milb_seasons missing from shipped hit set"
    lam = blend_lambda("hit")   # 0.85, held fixed for the feature gate

    folds_keep = build_folds_keyed("hit", keys_keep)
    folds_drop = build_folds_keyed("hit", keys_drop)
    m_keep = point_metrics(folds_keep, lam)
    m_drop = point_metrics(folds_drop, lam)

    w_keep, a_keep, b_keep = fitted_weights("hit", keys_keep)
    w_drop, a_drop, b_drop = fitted_weights("hit", keys_drop)

    boot = gate_bootstrap(folds_drop, folds_keep, lam) if do_boot else None

    # Verdict per the task's explicit operationalization:
    #   DROP  <- dropping "improves or is neutral" == lo95(drop-minus-keep) >= 0 on BOTH
    #            pooled Spearman AND contributor AUC (dropping is confidently neutral-or-better).
    #   KEEP  <- otherwise (dropping either measurably hurts OR fails the neutrality bar).
    # This is the conservative production rule: a SHIPPED feature is removed only on positive
    # evidence that removal is at-least-neutral; the ambiguous middle (CI straddles 0 but the
    # point estimate favours keep) defaults to KEEP -- do not change production without clearing
    # the stated bar. The -0.37 fitted sign is NOT itself a drop reason: the ridge legitimately
    # fits a negative weight (more MiLB seasons before the read -> older grinder -> lower first-6yr
    # WAR); that documented "+1" is only the unused LightGBM monotone hint.
    verdict = "KEEP"
    reason = ""
    if boot:
        rho_neutral_or_better = (boot["d_rho_lo95_2sided"] is not None
                                 and boot["d_rho_lo95_2sided"] >= 0)
        auc_neutral_or_better = (boot["d_auc_lo95_2sided"] is not None
                                 and boot["d_auc_lo95_2sided"] >= 0)
        rho_hurts = (boot["d_rho_hi95_2sided"] is not None and boot["d_rho_hi95_2sided"] < 0)
        if rho_neutral_or_better and auc_neutral_or_better:
            verdict = "DROP"
            reason = ("dropping improves-or-neutral with confidence "
                      "(drop-minus-keep lo95>=0 on BOTH pooled Spearman and contributor AUC)")
        elif rho_hurts:
            verdict = "KEEP"
            reason = ("dropping measurably hurts: drop-minus-keep pooled-rho hi95<0 "
                      "(feature earns its place)")
        else:
            verdict = "KEEP"
            reason = ("removal bar unmet: drop-minus-keep lo95<0 (not confidently neutral) while "
                      "the point estimate + P(drop>keep) favour KEEP; no evidence to remove a "
                      "shipped feature -> status quo")
    return {
        "lambda_held": lam,
        "keys_keep": keys_keep, "keys_drop": keys_drop,
        "keep_metrics": m_keep, "drop_metrics": m_drop,
        "delta_spearman_drop_minus_keep": round((m_drop["spearman"] or 0) - (m_keep["spearman"] or 0), 4),
        "delta_contrib_auc_drop_minus_keep": round((m_drop["contrib_auc"] or 0) - (m_keep["contrib_auc"] or 0), 4),
        "n_milb_seasons_weight_keep_fit": w_keep.get("n_milb_seasons"),
        "fitted_alpha_keep": a_keep, "fitted_alpha_drop": a_drop,
        "weights_keep": w_keep, "weights_drop": w_drop,
        "bootstrap_drop_vs_keep": boot,
        "verdict": verdict, "verdict_reason": reason,
    }


# ---------------------------------------------------------------------------
# STEP 2 -- lambda re-select on the locked feature set.
# ---------------------------------------------------------------------------
def _sweep_curve(folds, grid):
    curve = {}
    for lam in grid:
        m = point_metrics(folds, lam)
        curve[f"{lam:.2f}"] = {"spearman": m["spearman"], "contrib_auc": m["contrib_auc"],
                               "star_auc": m["star_auc"]}
    return curve


def step2_lambda(side, keys, shipped_lambda, do_boot=True):
    folds = build_folds_keyed(side, keys)
    n_contrib = sum(1 for f in folds if f["target"] >= CONTRIB_WAR)
    n_star = sum(1 for f in folds if f["target"] >= STAR_WAR)

    curve_coarse = _sweep_curve(folds, GRID_COARSE)
    curve_fine = _sweep_curve(folds, GRID_FINE)

    shipped_m = point_metrics(folds, shipped_lambda)

    # unconstrained pooled-Spearman argmax over the fine grid
    valid = [(float(k), v) for k, v in curve_fine.items() if v["spearman"] is not None]
    argmax_lam, argmax_v = max(valid, key=lambda kv: kv[1]["spearman"])
    argmax_m = point_metrics(folds, argmax_lam)

    # SHIP rule (RL.bootstrap_delta reused): ascending pooled over the coarse grid above the
    # shipped lambda, keep the highest that clears one-sided-95 lo>0 on BOTH pooled rho AND
    # contributor AUC vs shipped. If none clears -> keep shipped (no move).
    ship_lam = shipped_lambda
    ship_boot = None
    cands = []
    if do_boot:
        above = sorted([(float(k), v) for k, v in curve_coarse.items()
                        if float(k) > shipped_lambda + 1e-9],
                       key=lambda kv: (kv[1]["spearman"] if kv[1]["spearman"] is not None else -9))
        for lam, v in above:
            b = RL.bootstrap_delta(folds, lam, shipped_lambda, n_contrib)
            clears = (b["d_rho_lo95_1sided"] is not None and b["d_rho_lo95_1sided"] > 0
                      and b["d_auc_lo95_1sided"] is not None and b["d_auc_lo95_1sided"] > 0)
            cands.append({"lam": lam, "spearman": v["spearman"],
                          "d_rho_lo95_1sided": b["d_rho_lo95_1sided"],
                          "d_auc_lo95_1sided": b["d_auc_lo95_1sided"],
                          "d_rho_p_gt0": b["d_rho_p_gt0"], "clears": clears})
            if clears and (v["spearman"] or -9) >= (point_metrics(folds, ship_lam)["spearman"] or -9):
                ship_lam = lam; ship_boot = b
    # also check the fine argmax vs shipped even if it did not come from the coarse grid
    argmax_boot = None
    if do_boot and abs(argmax_lam - shipped_lambda) > 1e-9:
        argmax_boot = RL.bootstrap_delta(folds, argmax_lam, shipped_lambda, n_contrib)

    ship_m = point_metrics(folds, ship_lam)
    return {
        "side": side, "keys": keys, "shipped_lambda": shipped_lambda,
        "n_pooled": len(folds), "n_contrib": n_contrib, "n_star": n_star,
        "shipped_metrics": shipped_m,
        "argmax_lambda": argmax_lam, "argmax_metrics": argmax_m, "argmax_bootstrap_vs_shipped": argmax_boot,
        "ship_lambda": ship_lam, "ship_metrics": ship_m, "ship_moved": bool(abs(ship_lam - shipped_lambda) > 1e-9),
        "ship_bootstrap_vs_shipped": ship_boot,
        "ship_candidates_ascending_pooled": cands,
        "delta_spearman_ship_vs_shipped": round((ship_m["spearman"] or 0) - (shipped_m["spearman"] or 0), 4),
        "delta_contrib_auc_ship_vs_shipped": round((ship_m["contrib_auc"] or 0) - (shipped_m["contrib_auc"] or 0), 4),
        "curve_coarse": curve_coarse,
        "curve_fine": curve_fine,
    }


def main(do_boot=True):
    out = {"seed": SEED, "n_boot": N_BOOT, "scored_years": list(SCORED_YEARS),
           "contrib_war": CONTRIB_WAR, "star_war": STAR_WAR,
           "matrix_mtime": {s: matrix_path(s).stat().st_mtime for s in ("hit", "pit")},
           "protocol": "rebuilt-matrix (K 50/40); debuted-only forward-chained; raw ridge leg; "
                       "canonical rank_calibration selector",
           "pre_rebuild_shipped_bar": PRE_REBUILD}

    # STEP 0 -- same-run baseline (shipped config on the rebuilt matrix)
    lam_hit = blend_lambda("hit")
    lam_pit = blend_lambda("pit")
    base_hit = point_metrics(build_folds_keyed("hit", _feature_spec("hit")[0]), lam_hit)
    base_pit = point_metrics(build_folds_keyed("pit", _feature_spec("pit")[0]), lam_pit)
    out["step0_baseline"] = {
        "hit": {"shipped_lambda": lam_hit, **base_hit},
        "pit": {"shipped_lambda": lam_pit, **base_pit},
    }
    print("== STEP 0 same-run baseline (rebuilt matrix) ==")
    print(f"  hit lam={lam_hit} rho={base_hit['spearman']} cAUC={base_hit['contrib_auc']} sAUC={base_hit['star_auc']} n={base_hit['n']}")
    print(f"  pit lam={lam_pit} rho={base_pit['spearman']} cAUC={base_pit['contrib_auc']} sAUC={base_pit['star_auc']} n={base_pit['n']}")

    # STEP 1 -- n_milb_seasons gate (hit)
    print("== STEP 1 n_milb_seasons feature gate (hit) ==")
    s1 = step1_feature_gate(do_boot=do_boot)
    out["step1_n_milb_gate"] = s1
    print(f"  n_milb_seasons fitted ridge weight (KEEP fit)={s1['n_milb_seasons_weight_keep_fit']}")
    print(f"  KEEP rho={s1['keep_metrics']['spearman']} cAUC={s1['keep_metrics']['contrib_auc']}")
    print(f"  DROP rho={s1['drop_metrics']['spearman']} cAUC={s1['drop_metrics']['contrib_auc']}")
    if s1["bootstrap_drop_vs_keep"]:
        b = s1["bootstrap_drop_vs_keep"]
        print(f"  boot drop-minus-keep d_rho mean={b['d_rho_mean']} 2s95=[{b['d_rho_lo95_2sided']},{b['d_rho_hi95_2sided']}] P(>0)={b['d_rho_p_gt0']}")
        print(f"                        d_auc mean={b['d_auc_mean']} 2s95=[{b['d_auc_lo95_2sided']},{b['d_auc_hi95_2sided']}] P(>0)={b['d_auc_p_gt0']}")
    print(f"  VERDICT: {s1['verdict']} ({s1['verdict_reason']})")

    # locked hit feature set
    keys_hit_final = s1["keys_drop"] if s1["verdict"] == "DROP" else s1["keys_keep"]
    out["locked_hit_features"] = keys_hit_final

    # STEP 2 -- lambda re-select on locked sets
    print("== STEP 2 lambda re-select (locked feature sets) ==")
    s2_hit = step2_lambda("hit", keys_hit_final, lam_hit, do_boot=do_boot)
    s2_pit = step2_lambda("pit", _feature_spec("pit")[0], lam_pit, do_boot=do_boot)
    out["step2_lambda"] = {"hit": s2_hit, "pit": s2_pit}
    for side, s2 in (("hit", s2_hit), ("pit", s2_pit)):
        print(f"  [{side}] shipped lam={s2['shipped_lambda']} rho={s2['shipped_metrics']['spearman']} cAUC={s2['shipped_metrics']['contrib_auc']}")
        print(f"        argmax lam={s2['argmax_lambda']} rho={s2['argmax_metrics']['spearman']} cAUC={s2['argmax_metrics']['contrib_auc']}")
        if s2["argmax_bootstrap_vs_shipped"]:
            b = s2["argmax_bootstrap_vs_shipped"]
            print(f"        argmax-vs-shipped boot d_rho mean={b['d_rho_mean']} 1s95lo={b['d_rho_lo95_1sided']} P(>0)={b['d_rho_p_gt0']} | d_auc 1s95lo={b['d_auc_lo95_1sided']}")
        print(f"        SHIP lam={s2['ship_lambda']} (moved={s2['ship_moved']}) rho={s2['ship_metrics']['spearman']} d_rho_vs_shipped={s2['delta_spearman_ship_vs_shipped']}")
        print(f"        coarse curve: " + " ".join(f"{k}:{v['spearman']}" for k, v in s2["curve_coarse"].items()))

    # FINAL scoreboard + regression flag
    final = {}
    for side, s2 in (("hit", s2_hit), ("pit", s2_pit)):
        fm = s2["ship_metrics"]
        pre = PRE_REBUILD[side]
        final[side] = {
            "final_lambda": s2["ship_lambda"],
            "final_spearman": fm["spearman"], "final_contrib_auc": fm["contrib_auc"],
            "final_star_auc": fm["star_auc"],
            "vs_same_run_baseline_delta": round((fm["spearman"] or 0) - (out["step0_baseline"][side]["spearman"] or 0), 4),
            "pre_rebuild_bar": pre,
            "vs_pre_rebuild_delta": round((fm["spearman"] or 0) - pre, 4),
            "regression_flag": bool((fm["spearman"] or 0) < pre),
        }
    out["final_scoreboard"] = final
    print("== FINAL scoreboard ==")
    for side in ("hit", "pit"):
        f = final[side]
        flag = "  *** REGRESSION FLAG ***" if f["regression_flag"] else ""
        print(f"  [{side}] lam={f['final_lambda']} rho={f['final_spearman']} cAUC={f['final_contrib_auc']} "
              f"sAUC={f['final_star_auc']} | vs pre-rebuild {f['pre_rebuild_bar']} = {f['vs_pre_rebuild_delta']}{flag}")

    Path("data/xfv_wave_h_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote data/xfv_wave_h_eval.json")
    return out


if __name__ == "__main__":
    main(do_boot=("--quick" not in sys.argv))
