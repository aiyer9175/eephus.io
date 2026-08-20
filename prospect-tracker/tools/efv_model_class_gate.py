# V3 model-class re-adjudication lab (registered 2026-08-19).
#
# Gate: docs/efv-2026-08-19/MODEL_CLASS_READJUDICATION_GATE.md. Clauses were frozen
# before this file existed; this lab implements them and nothing else.
#
# Arms, per side (hit, pit), against the shipped ridge reproduced bit-exact:
#   A0  reproduction control. The lab's ridge path must reproduce the shipped
#       per-fold OOS predictions bit-exact (tolerance 1e-9 on pooled rho) or
#       NOTHING below it is read.
#   A1  monotone LightGBM, the existing efv_model._fit_lgbm_mono configuration,
#       called by IMPORT and never re-tuned.
#   A2  ensemble = mean(ridge, monotone-lgbm) OOS predictions.
#
# Frame: the current 11-fold pair-weighted chain, identical rows per side as the
# shipped eval (data/xfv_eval.json / xfv_eval_pitcher.json basis), debuted_km.
# Arms are compared at the MODEL LEG; lambda is not touched.
#
# Statistics: pooled Spearman rho delta (arm minus ridge), player-clustered paired
# bootstrap, B=2000, E_cond primary, floors derived ON THIS FRAME before any arm
# is read. E_refit secondary at B=200 refit draws (reduced-B penalty disclosed).
# Family {hit,pit} x {A1,A2}, Holm. Diagnostics S3 (pooled MAE + tail MAE) are
# non-gating but ship-blocking. Controls: C-a = A0; C-b = zero-information twin
# (A1 trained on row-permuted features must not clear its floor); C-c = fold
# coverage (every fold contributes OOS rows for every arm).
#
# Run:  python tools/efv_model_class_gate.py all [B_cond] [B_refit]
#
# Everything reuses the SHIPPED machinery by import: efv_model._prep /
# _feature_spec / _fit_lgbm_mono / _pred_lgbm / _run_eval, prospect_path._fit_ridge
# / _predict / _score, and tools/efv_mde_lab's numpy replica (ridge_fit/ridge_pred/
# wrho), whose bit-parity with the shipped chain A0 re-verifies here rather than
# assuming. The artifact is written incrementally so a crash loses nothing.
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np
import warnings

warnings.filterwarnings("ignore", message="X does not have valid feature names")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                      # noqa: E402  read-only, shipped chain
import prospect_path as PP                 # noqa: E402  shipped ridge + scorer
import efv_mde_lab as M                    # noqa: E402  numpy replica, parity re-checked in A0

SEED = 20260819
SIDES = ("hit", "pit")
DATA = ROOT / "data"
OUT = DATA / "xfv_model_class_readjudication_eval.json"
GATE_DOC = "docs/efv-2026-08-19/MODEL_CLASS_READJUDICATION_GATE.md"
A0_TOL = 1e-9
ALPHA = 0.05
Z95_ONE = 1.645
CELLS = [("hit", "A1"), ("hit", "A2"), ("pit", "A1"), ("pit", "A2")]


# --------------------------------------------------------------------- artifact
def _load_artifact() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {
        "gate_doc": GATE_DOC,
        "registered": "2026-08-19, clauses frozen before the lab existed",
        "produced_by": "tools/efv_model_class_gate.py",
        "seed": SEED,
        "purpose": ("V3: one registered re-adjudication of the model class (monotone "
                    "LightGBM and ridge+lgbm ensemble vs the shipped ridge) on the "
                    "current 11-fold pair-weighted debuted_km basis. The prior "
                    "model-class close lived on the retired 4-fold basis."),
    }


def _write_artifact(art: dict):
    art["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    OUT.write_text(json.dumps(art, indent=1), encoding="utf-8")


# --------------------------------------------------------------------- pool
def load_side(side: str) -> dict:
    """The debuted-KM eval pool, exactly efv_model.run()'s construction."""
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(deb, "target_censored", side)
    keys, mono = E._feature_spec(side)
    return {
        "side": side, "prep": prep, "keys": list(keys), "mono": mono,
        "X": np.array([[r["feats"][k] for k in keys] for r in prep], dtype=float),
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.array([float(r.get("weight", 1.0) or 1.0) for r in prep], dtype=float),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "pk": [r["player_key"] for r in prep],
        "lam": E.blend_lambda(side),
        "n": len(prep),
    }


def wmae(p, y, w):
    sw = float(w.sum())
    return float(np.sum(np.abs(p - y) * w) / sw) if sw > 0 else float("nan")


# --------------------------------------------------------------------- point chain
def point_chain(S: dict, log_pace: bool = False) -> dict:
    """The shipped fold loop, row for row: per fold fit ridge (prospect_path.
    _fit_ridge) and A1 (efv_model._fit_lgbm_mono, untouched config), score the
    test cohort row-wise through the SAME functions _run_eval calls
    (prospect_path._predict, efv_model._pred_lgbm). A2 = mean of the two legs.

    Also runs the numpy-replica ridge (efv_mde_lab.ridge_fit/ridge_pred) on the
    same folds so A0 can measure replica-vs-shipped parity on THIS run instead of
    citing efv_mde_lab's parity mode.
    """
    prep, keys, mono = S["prep"], S["keys"], S["mono"]
    dy = S["dy"]
    pooled = {"yr": [], "idx": [], "ridge": [], "ridge_vec": [], "lgbm": [],
              "lgbm_batch": [], "ens": [], "y": [], "w": []}
    folds = []
    first_pair_logged = False
    for yr in E.SCORED_YEARS:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        train = [prep[i] for i in tr]
        t0 = time.time()
        ridge = PP._fit_ridge(train, keys)
        gbm = E._fit_lgbm_mono(train, keys, mono)
        t_pair = time.time() - t0
        if log_pace and not first_pair_logged:
            print(f"[pace] {S['side']} first fold pair (ridge+lgbm fit, "
                  f"n_train {len(tr)}): {t_pair:.2f}s", flush=True)
            first_pair_logged = True
        rg_vec = M.ridge_fit(S["X"][tr], S["y"][tr], np.clip(S["w"][tr], 1e-3, None))
        cover = {"yr": int(yr), "n_train": int(len(tr)), "n_test": int(len(te)),
                 "ridge": ridge is not None, "lgbm": gbm is not None}
        folds.append(cover)
        if ridge is None or gbm is None:
            continue
        rp = np.array([PP._predict(ridge, prep[i]["feats"]) for i in te], dtype=float)
        rv = M.ridge_pred(rg_vec, S["X"][te])
        lp = np.array([E._pred_lgbm(gbm, prep[i]["feats"]) for i in te], dtype=float)
        lb = np.asarray(gbm["model"].predict(S["X"][te]), dtype=float)
        pooled["yr"].append(np.full(len(te), yr))
        pooled["idx"].append(te)
        pooled["ridge"].append(rp)
        pooled["ridge_vec"].append(rv)
        pooled["lgbm"].append(lp)
        pooled["lgbm_batch"].append(lb)
        pooled["ens"].append((rp + lp) / 2.0)
        pooled["y"].append(S["y"][te])
        pooled["w"].append(S["w"][te])
    out = {k: np.concatenate(v) for k, v in pooled.items() if v}
    out["folds"] = folds
    return out


# --------------------------------------------------------------------- A0
def run_a0(art: dict, pools: dict, chains: dict) -> bool:
    """C-a. Three legs, all required, per side:
      1. pooled + per-year ridge scores from this lab's fold loop must EQUAL the
         shipped chain's own output (efv_model._run_eval, called by import, same
         rows, same process) on n / spearman / mae / n_effective, and the lgbm and
         ensemble legs must equal it too (that pins A1/A2 to the shipped protocol).
      2. |pooled rho(row-wise shipped ridge path) - pooled rho(numpy replica
         ridge path)| <= 1e-9: the registered tolerance, measured on THIS run.
      3. batch lgbm predictions must equal row-wise _pred_lgbm to 1e-9 (max abs
         pred diff), which is what licenses batch predict in the bootstrap legs.
    The on-disk eval artifacts are compared and any drift disclosed; the binding
    comparison is the in-process shipped chain on identical rows.
    """
    a0 = {"tolerance_pooled_rho": A0_TOL, "sides": {}, "passed": None}
    ok_all = True
    for side in SIDES:
        S, C = pools[side], chains[side]
        re = E._run_eval(S["prep"], "A0 reproduction", S["keys"], S["mono"],
                         S["lam"], side=side, cut="debuted_km")
        po = re["pooled_oos"]
        lab_scores = {}
        legs = {"ridge": C["ridge"], "lgbm": C["lgbm"], "ensemble": C["ens"]}
        legs_ok = {}
        for name, pred in legs.items():
            pairs = list(zip(pred.tolist(), C["y"].tolist()))
            sc = PP._score(pairs, C["w"].tolist())
            lab_scores[name] = sc
            ship = po[name]
            legs_ok[name] = all(sc.get(k) == ship.get(k)
                                for k in ("n", "n_effective", "spearman", "mae"))
        per_year_ok = True
        for f in C["folds"]:
            yv = str(f["yr"])
            m = C["yr"] == f["yr"]
            if not m.any():
                continue
            pairs = list(zip(C["ridge"][m].tolist(), C["y"][m].tolist()))
            sc = PP._score(pairs, C["w"][m].tolist())
            ship = (re["per_year"].get(yv) or {}).get("ridge") or {}
            if sc.get("spearman") != ship.get("spearman") or sc.get("n") != ship.get("n"):
                per_year_ok = False
        rho_row = M.wrho(C["ridge"], C["y"], C["w"])
        rho_vec = M.wrho(C["ridge_vec"], C["y"], C["w"])
        replica_gap = abs(rho_row - rho_vec)
        pred_gap = float(np.max(np.abs(C["ridge"] - C["ridge_vec"])))
        lgbm_gap = float(np.max(np.abs(C["lgbm"] - C["lgbm_batch"])))
        disk_name = "xfv_eval.json" if side == "hit" else "xfv_eval_pitcher.json"
        disk = json.loads((DATA / disk_name).read_text(encoding="utf-8"))
        dr = disk["evals"]["debuted_km"]["pooled_oos"]["ridge"]
        disk_cmp = {
            "artifact": f"data/{disk_name}", "generated_at": disk.get("generated_at"),
            "disk_ridge": {k: dr.get(k) for k in ("n", "spearman", "mae")},
            "lab_ridge": {k: lab_scores["ridge"].get(k) for k in ("n", "spearman", "mae")},
            "match": all(dr.get(k) == lab_scores["ridge"].get(k)
                         for k in ("n", "spearman", "mae")),
        }
        side_ok = (all(legs_ok.values()) and per_year_ok
                   and replica_gap <= A0_TOL and lgbm_gap <= A0_TOL)
        ok_all = ok_all and side_ok
        a0["sides"][side] = {
            "n_scored": int(len(C["y"])),
            "lab_pooled": lab_scores,
            "run_eval_pooled": {k: po[k] for k in ("ridge", "lgbm", "ensemble")},
            "legs_equal_run_eval": legs_ok,
            "per_year_ridge_equal": per_year_ok,
            "pooled_rho_rowwise_unrounded": rho_row,
            "pooled_rho_replica_unrounded": rho_vec,
            "replica_pooled_rho_gap": replica_gap,
            "replica_max_abs_pred_gap": pred_gap,
            "lgbm_batch_max_abs_pred_gap": lgbm_gap,
            "disk_artifact_comparison": disk_cmp,
            "passed": side_ok,
        }
        print(f"[A0] {side}: legs_equal={legs_ok} per_year={per_year_ok} "
              f"replica_rho_gap={replica_gap:.2e} lgbm_batch_gap={lgbm_gap:.2e} "
              f"disk_match={disk_cmp['match']} -> "
              f"{'PASS' if side_ok else 'FAIL'}", flush=True)
    a0["passed"] = ok_all
    art["A0"] = a0
    _write_artifact(art)
    return ok_all


# --------------------------------------------------------------------- C-c
def run_cc(art: dict, chains: dict) -> bool:
    cc = {"rule": "every fold contributes OOS rows for every arm (no silent drops)",
          "sides": {}, "passed": None}
    ok = True
    for side in SIDES:
        folds = chains[side]["folds"]
        bad = [f["yr"] for f in folds if not (f["ridge"] and f["lgbm"])]
        cc["sides"][side] = {"folds_scored": [f["yr"] for f in folds],
                             "folds_missing_an_arm": bad}
        ok = ok and not bad
    cc["passed"] = ok
    art["C_c_fold_coverage"] = cc
    _write_artifact(art)
    print(f"[C-c] fold coverage: {'PASS' if ok else 'FAIL'} "
          f"{ {s: cc['sides'][s]['folds_missing_an_arm'] for s in SIDES} }", flush=True)
    return ok


# --------------------------------------------------------------------- E_cond floors
def run_cond(art: dict, chains: dict, B: int) -> dict:
    """Player-clustered paired bootstrap, fits held fixed, scored rows resampled.
    The pool carries exactly one row per player_key on both sides (verified and
    recorded), so resampling rows IS resampling players. Floors (1.645 * sd of the
    delta draws) are computed and WRITTEN before any point delta is computed."""
    draws = {}
    fl = {"estimator": "E_cond (fits held, scored players resampled, paired)",
          "B": int(B), "seed": SEED,
          "clustering": "player_key; one row per player on the scored frame "
                        "(uniqueness verified below), so row resampling is "
                        "player-clustered resampling",
          "cells": {}}
    for side in SIDES:
        C = chains[side]
        m = len(C["y"])
        tail_thr = float(np.quantile(C["y"], 0.9))
        tail = C["y"] >= tail_thr
        rng = np.random.default_rng(SEED + (0 if side == "hit" else 1))
        d = {("%s_%s" % (side, a)): {"rho": [], "mae": [], "tail": []}
             for a in ("A1", "A2")}
        arms = {"A1": C["lgbm"], "A2": C["ens"]}
        for _ in range(B):
            idx = rng.integers(0, m, m)
            y, w = C["y"][idx], C["w"][idx]
            r_ridge = M.wrho(C["ridge"][idx], y, w)
            mae_ridge = wmae(C["ridge"][idx], y, w)
            tm = tail[idx]
            for a, pred in arms.items():
                key = f"{side}_{a}"
                d[key]["rho"].append(M.wrho(pred[idx], y, w) - r_ridge)
                d[key]["mae"].append(wmae(pred[idx], y, w) - mae_ridge)
                if int(tm.sum()) >= 8:
                    d[key]["tail"].append(
                        wmae(pred[idx][tm], y[tm], w[tm])
                        - wmae(C["ridge"][idx][tm], y[tm], w[tm]))
        for key, v in d.items():
            a = np.asarray(v["rho"], dtype=float)
            a = a[np.isfinite(a)]
            sd = float(a.std(ddof=1))
            fl["cells"][key] = {
                "B_used": int(len(a)), "sd": round(sd, 6),
                "mde95_onesided": round(Z95_ONE * sd, 5),
                "tail_threshold_war": round(tail_thr, 3),
                "n_tail": int(tail.sum()),
            }
        draws[side] = d
        print(f"[E_cond floors] {side}: " + json.dumps(
            {k: fl["cells"][k]["mde95_onesided"] for k in fl["cells"]
             if k.startswith(side)}), flush=True)
    fl["derived_before_arms_read"] = True
    art["floors_E_cond"] = fl
    _write_artifact(art)   # floors on disk before any point delta is computed
    return draws


# --------------------------------------------------------------------- C-b twin
def run_twin(art: dict, pools: dict, chains: dict) -> bool:
    """Zero-information twin: A1 trained on row-permuted features (the feature
    vectors shuffled across the WHOLE pool, targets left in place, seeded), scored
    through the same fold loop. It must NOT clear the side's A1 E_cond floor on
    the win side; if it does the harness is broken and nothing is read."""
    tw = {"rule": "twin delta must be < +MDE95(side A1); a clearing twin voids the run",
          "sides": {}, "passed": None}
    ok = True
    for side in SIDES:
        S, C = pools[side], chains[side]
        rng = np.random.default_rng(SEED + 700 + (0 if side == "hit" else 1))
        perm = rng.permutation(S["n"])
        Xp = S["X"][perm]
        prep = S["prep"]
        dy = S["dy"]
        preds, ys, ws = [], [], []
        for yr in E.SCORED_YEARS:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 15 or len(tr) < 60:
                continue
            ptrain = [{"feats": prep[perm[i]]["feats"], "target": prep[i]["target"],
                       "weight": prep[i]["weight"]} for i in tr]
            gbm = E._fit_lgbm_mono(ptrain, S["keys"], S["mono"])
            if gbm is None:
                continue
            preds.append(np.asarray(gbm["model"].predict(Xp[te]), dtype=float))
            ys.append(S["y"][te])
            ws.append(S["w"][te])
        p = np.concatenate(preds)
        y = np.concatenate(ys)
        w = np.concatenate(ws)
        delta = M.wrho(p, y, w) - M.wrho(C["ridge"], C["y"], C["w"])
        floor = art["floors_E_cond"]["cells"][f"{side}_A1"]["mde95_onesided"]
        cleared = bool(delta >= floor)
        ok = ok and not cleared
        tw["sides"][side] = {"twin_delta_rho": round(float(delta), 5),
                             "floor_A1": floor, "cleared_floor": cleared}
        print(f"[C-b] {side}: twin delta {delta:+.5f} vs floor {floor} -> "
              f"{'BROKEN' if cleared else 'clean'}", flush=True)
    tw["passed"] = ok
    art["C_b_zero_information_twin"] = tw
    _write_artifact(art)
    return ok


# --------------------------------------------------------------------- points + Holm + S3
def _p_one_sided_win(delta: float, sd: float) -> float:
    if sd <= 0:
        return 1.0
    return 0.5 * math.erfc((delta / sd) / math.sqrt(2.0))


def _ci95(vals) -> list:
    a = np.asarray(vals, dtype=float)
    a = a[np.isfinite(a)]
    return [round(float(np.percentile(a, 2.5)), 5),
            round(float(np.percentile(a, 97.5)), 5)]


def run_points(art: dict, chains: dict, draws: dict):
    cells = {}
    for side in SIDES:
        C = chains[side]
        rho_ridge = M.wrho(C["ridge"], C["y"], C["w"])
        mae_ridge = wmae(C["ridge"], C["y"], C["w"])
        tail_thr = art["floors_E_cond"]["cells"][f"{side}_A1"]["tail_threshold_war"]
        tail = C["y"] >= tail_thr
        for a, pred in (("A1", C["lgbm"]), ("A2", C["ens"])):
            key = f"{side}_{a}"
            d = draws[side][key]
            sd = art["floors_E_cond"]["cells"][key]["sd"]
            floor = art["floors_E_cond"]["cells"][key]["mde95_onesided"]
            rho_arm = M.wrho(pred, C["y"], C["w"])
            delta = float(rho_arm - rho_ridge)
            mae_arm = wmae(pred, C["y"], C["w"])
            mae_delta = float(mae_arm - mae_ridge)
            mae_ci = _ci95(d["mae"])
            tail_delta = float(wmae(pred[tail], C["y"][tail], C["w"][tail])
                               - wmae(C["ridge"][tail], C["y"][tail], C["w"][tail]))
            tail_ci = _ci95(d["tail"])
            mae_viol = bool(mae_ci[0] > 0)
            tail_viol = bool(tail_ci[0] > 0)
            cells[key] = {
                "side": side, "arm": a,
                "arm_desc": ("monotone LightGBM, _fit_lgbm_mono config untouched"
                             if a == "A1" else "mean(ridge, monotone-lgbm) OOS predictions"),
                "n": int(len(C["y"])),
                "rho_ridge": round(float(rho_ridge), 5),
                "rho_arm": round(float(rho_arm), 5),
                "delta_rho": round(delta, 5),
                "E_cond": {
                    "sd": sd, "mde95_onesided": floor,
                    "ci95_delta": _ci95(d["rho"]),
                    "x_floor": round(abs(delta) / floor, 3) if floor > 0 else None,
                    "resolvable": bool(abs(delta) >= floor),
                    "verdict": ("RESOLVABLE " + ("WIN" if delta > 0 else "LOSS")
                                if abs(delta) >= floor else "NULL"),
                },
                "p_one_sided_win": round(_p_one_sided_win(delta, sd), 6),
                "S3": {
                    "mae_ridge": round(mae_ridge, 4), "mae_arm": round(mae_arm, 4),
                    "mae_delta": round(mae_delta, 4), "mae_delta_ci95": mae_ci,
                    "mae_worse_beyond_ci": mae_viol,
                    "tail_mae_delta": round(tail_delta, 4),
                    "tail_mae_delta_ci95": tail_ci,
                    "tail_worse_beyond_ci": tail_viol,
                    "tail_definition": "top decile of realized WAR on the scored frame",
                    "pass": not (mae_viol or tail_viol),
                },
            }
    # Holm step-down over the 4-cell family, one-sided win p-values.
    ps = sorted(((cells[k]["p_one_sided_win"], k) for k in cells))
    k_fam = len(ps)
    holm_reject = {}
    still = True
    steps = []
    for i, (p, key) in enumerate(ps):
        thr = ALPHA / (k_fam - i)
        rej = bool(still and p <= thr)
        if not rej:
            still = False
        holm_reject[key] = rej
        steps.append({"cell": key, "p": p, "threshold": round(thr, 6), "reject": rej})
    for key in cells:
        c = cells[key]
        c["holm_reject"] = holm_reject[key]
        c["ship"] = bool(c["delta_rho"] > 0 and c["E_cond"]["resolvable"]
                         and holm_reject[key] and c["S3"]["pass"])
    art["cells"] = cells
    art["holm"] = {"family": [f"{s}_{a}" for s, a in CELLS], "alpha": ALPHA,
                   "procedure": "Holm step-down, one-sided win p = 1-Phi(delta/sd_cond)",
                   "steps": steps,
                   "survivors": [k for k in cells if holm_reject[k]]}
    _write_artifact(art)
    for key in sorted(cells):
        c = cells[key]
        print(f"[cell {key}] delta {c['delta_rho']:+.5f} floor "
              f"{c['E_cond']['mde95_onesided']} x_floor {c['E_cond']['x_floor']} "
              f"E_cond {c['E_cond']['verdict']} holm_reject={c['holm_reject']} "
              f"S3_pass={c['S3']['pass']} ship={c['ship']}", flush=True)


# --------------------------------------------------------------------- E_refit
def run_refit(art: dict, pools: dict, B: int):
    """Secondary estimator: resample the pool (one row per player), refit ridge and
    lgbm on every draw, forward-chained, deltas at the model leg. B=200 registered;
    the reduced-B penalty is disclosed (~1/sqrt(2B) relative sd error, ~5% at 200).
    Pace clause: beyond ~75 min projected, drop to B=100 and disclose; if still
    infeasible, record NOT COMPLETED with the measured pace."""
    ref = {"estimator": "E_refit (pool resampled, ridge+lgbm refit per draw)",
           "B_registered": 200,
           "reduced_B_penalty": "bootstrap sd carries ~1/sqrt(2B) relative error, "
                                "~5% at B=200, ~7% at B=100",
           "seed": SEED, "cells": {}}
    t_probe0 = time.time()
    per_draw = {}
    all_draws = {f"{s}_{a}": [] for s in SIDES for a in ("A1", "A2")}

    def one_draw(S, rng):
        sel = rng.integers(0, S["n"], S["n"])
        Xb, yb = S["X"][sel], S["y"][sel]
        wb, dyb = S["w"][sel], S["dy"][sel]
        prep = S["prep"]
        R, L, Y, W = [], [], [], []
        for yr in E.SCORED_YEARS:
            trm = np.flatnonzero(dyb < yr)
            tem = np.flatnonzero(dyb == yr)
            if len(tem) < 15 or len(trm) < 60:
                continue
            rg = M.ridge_fit(Xb[trm], yb[trm], np.clip(wb[trm], 1e-3, None))
            train = [prep[j] for j in sel[trm]]
            gbm = E._fit_lgbm_mono(train, S["keys"], S["mono"])
            if rg is None or gbm is None:
                continue
            R.append(M.ridge_pred(rg, Xb[tem]))
            L.append(np.asarray(gbm["model"].predict(Xb[tem]), dtype=float))
            Y.append(yb[tem])
            W.append(wb[tem])
        if not R:
            return None
        r = np.concatenate(R)
        lg = np.concatenate(L)
        y = np.concatenate(Y)
        w = np.concatenate(W)
        base = M.wrho(r, y, w)
        return (M.wrho(lg, y, w) - base, M.wrho((r + lg) / 2.0, y, w) - base)

    rngs = {s: np.random.default_rng(SEED + 500 + i) for i, s in enumerate(SIDES)}
    # pace probe: one draw per side
    for s in SIDES:
        t0 = time.time()
        d = one_draw(pools[s], rngs[s])
        per_draw[s] = time.time() - t0
        if d is not None:
            all_draws[f"{s}_A1"].append(d[0])
            all_draws[f"{s}_A2"].append(d[1])
    proj_min = (per_draw["hit"] + per_draw["pit"]) * (B - 1) / 60.0
    print(f"[pace] E_refit per draw: hit {per_draw['hit']:.2f}s pit "
          f"{per_draw['pit']:.2f}s; projected {proj_min:.1f} min for B={B}", flush=True)
    B_used = B
    if proj_min > 75:
        B_used = 100
        proj2 = (per_draw["hit"] + per_draw["pit"]) * (B_used - 1) / 60.0
        print(f"[pace] projection beyond 75 min: dropping to B={B_used} "
              f"(projected {proj2:.1f} min), disclosed", flush=True)
        if proj2 > 75:
            ref["status"] = "NOT COMPLETED"
            ref["measured_pace_s_per_draw"] = {k: round(v, 2) for k, v in per_draw.items()}
            ref["why"] = (f"pace projects {proj2:.1f} min even at B=100; the gate "
                          f"forbids substituting a different estimator")
            art["E_refit"] = ref
            _write_artifact(art)
            return
    for s in SIDES:
        for b in range(B_used - 1):
            d = one_draw(pools[s], rngs[s])
            if d is None:
                continue
            all_draws[f"{s}_A1"].append(d[0])
            all_draws[f"{s}_A2"].append(d[1])
            if (b + 2) % 50 == 0:
                print(f"[E_refit] {s}: {b + 2}/{B_used} draws, "
                      f"{time.time() - t_probe0:.0f}s elapsed", flush=True)
    ref["B_used"] = B_used
    ref["B_disclosure"] = ("B=200 as registered" if B_used == 200 else
                           f"reduced to B={B_used} under the registered pace clause")
    for key, vals in all_draws.items():
        a = np.asarray(vals, dtype=float)
        a = a[np.isfinite(a)]
        sd = float(a.std(ddof=1))
        point = art["cells"][key]["delta_rho"]
        ref["cells"][key] = {
            "B_used": int(len(a)), "sd": round(sd, 6),
            "mde95_onesided": round(Z95_ONE * sd, 5),
            "point_delta": point,
            "resolvable": bool(abs(point) >= Z95_ONE * sd),
            "verdict": ("RESOLVABLE " + ("WIN" if point > 0 else "LOSS")
                        if abs(point) >= Z95_ONE * sd else "NULL"),
            "role": "secondary, reported beside the registered E_cond primary, "
                    "never substituted",
        }
        print(f"[E_refit {key}] sd {sd:.5f} floor {Z95_ONE * sd:.5f} point {point:+.5f} "
              f"-> {ref['cells'][key]['verdict']}", flush=True)
    ref["elapsed_min"] = round((time.time() - t_probe0) / 60.0, 1)
    art["E_refit"] = ref
    _write_artifact(art)


# --------------------------------------------------------------------- verdict
def run_verdict(art: dict):
    cells = art["cells"]
    ships = [k for k in sorted(cells) if cells[k]["ship"]]
    all_null = not ships
    v = {
        "ships": ships,
        "all_null": all_null,
        "cells_summary": {k: {"delta_rho": cells[k]["delta_rho"],
                              "E_cond": cells[k]["E_cond"]["verdict"],
                              "holm_reject": cells[k]["holm_reject"],
                              "S3_pass": cells[k]["S3"]["pass"],
                              "ship": cells[k]["ship"]} for k in sorted(cells)},
    }
    if all_null:
        v["statement"] = (
            "ALL FOUR CELLS ARE NULL UNDER THE REGISTERED PRIMARY. Per the frozen "
            "permanent-close pre-commitment: the model class on the current feature "
            "set and label pool is CLOSED alongside the feature frontier. The combined "
            "reopen burden is the LABEL POOL (RESOLVED_THROUGH 2026), not another "
            "architecture. No third adjudication on these labels. No cell that failed "
            "Holm or its E_cond floor may be quoted as a win.")
    else:
        v["statement"] = (
            "Cells " + ", ".join(ships) + " cleared the E_cond floor under Holm and "
            "passed S3. Shipping still requires the registered flag plus the serve "
            "chain touched at all four scoring sites and epoch/fingerprint discipline "
            "(ship rule, frozen). Every other cell is NULL and must not be quoted as "
            "a win.")
    art["verdict"] = v
    _write_artifact(art)
    print("[verdict] " + json.dumps(v["cells_summary"]))
    print("[verdict] " + v["statement"], flush=True)


# --------------------------------------------------------------------- main
def main(B_cond: int = 2000, B_refit: int = 200):
    t0 = time.time()
    art = _load_artifact()
    art["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    art["B_cond"] = B_cond
    print(f"=== V3 model-class re-adjudication (B_cond={B_cond}, "
          f"B_refit={B_refit}, seed={SEED}) ===", flush=True)
    pools = {s: load_side(s) for s in SIDES}
    frame = {}
    for s in SIDES:
        S = pools[s]
        frame[s] = {"n_pool": S["n"], "n_keys": len(S["keys"]),
                    "lambda_pinned_untouched": S["lam"],
                    "player_key_unique": len(set(S["pk"])) == S["n"]}
    art["frame"] = {"basis": "current 11-fold pair-weighted chain, debuted_km, "
                             "model leg only", "sides": frame}
    _write_artifact(art)
    chains = {s: point_chain(pools[s], log_pace=True) for s in SIDES}
    for s in SIDES:
        art["frame"]["sides"][s]["n_scored"] = int(len(chains[s]["y"]))
        art["frame"]["sides"][s]["folds"] = chains[s]["folds"]

    if not run_a0(art, pools, chains):
        art["verdict"] = {"all_null": None, "ships": [],
                          "statement": "A0 FAILED: the lab did not reproduce the "
                                       "shipped ridge path. NOTHING below A0 was read. "
                                       "No arm result exists."}
        _write_artifact(art)
        print("A0 FAILED. STOPPING: nothing below A0 is read.", flush=True)
        return 1
    if not run_cc(art, chains):
        art["verdict"] = {"all_null": None, "ships": [],
                          "statement": "C-c FAILED: an arm silently dropped a fold. "
                                       "Harness invalid; no arm result exists."}
        _write_artifact(art)
        print("C-c FAILED. STOPPING.", flush=True)
        return 1
    draws = run_cond(art, chains, B_cond)
    if not run_twin(art, pools, chains):
        art["verdict"] = {"all_null": None, "ships": [],
                          "statement": "C-b FAILED: the zero-information twin cleared "
                                       "its floor, the harness is broken, nothing is "
                                       "read. No arm result exists."}
        _write_artifact(art)
        print("C-b FAILED. STOPPING.", flush=True)
        return 1
    run_points(art, chains, draws)
    run_refit(art, pools, B_refit)
    run_verdict(art)
    art["elapsed_min"] = round((time.time() - t0) / 60.0, 1)
    _write_artifact(art)
    print(f"wrote {OUT} ({art['elapsed_min']} min)", flush=True)
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    bc = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    br = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    if mode != "all":
        print("mode: all [B_cond] [B_refit]")
        sys.exit(2)
    sys.exit(main(bc, br))
