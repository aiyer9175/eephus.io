# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Lane S-1: re-measure served-vs-blend against a floor derived HERE.

Pre-registration: docs/efv-2026-08-14/SERVE_BASIS_REMEASURE_GATE.md (frozen).
Artifact: data/xfv_serve_basis_eval.json.

    python tools/efv_serve_basis_lab.py [B_COND] [B_REFIT]

Supersedes clause G2 of docs/efv-2026-08-07b/SERVE_PATH_INTEGRITY.md, which
gated on MDE95_POOLED_RHO = 0.044. That is the E_refit floor for the
MODEL-vs-CONSENSUS contest, where two DIFFERENT fits are compared. Served vs
blend is a PAIRED SAME-FIT contrast (identical ridge, identical rows, identical
folds, only the post-fit transform differs), so the refit variance that
dominates 0.044 is not in the contrast at all.

The fold replay deliberately mirrors tools/efv_board_serve_probe.py::_serve_arms
so S0 can reproduce BOTH the published eval arms and that lane's served figure.
What is new here is the single-affine arms and the floor derivation.
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
OUT = DATA / "xfv_serve_basis_eval.json"
GATE = "docs/efv-2026-08-14/SERVE_BASIS_REMEASURE_GATE.md"

SIDES = ("hit", "pit")
PUBLISHED = {"hit": "xfv_eval.json", "pit": "xfv_eval_pitcher.json"}
SERVE_PATH_EVAL = "xfv_serve_path_eval.json"

BOOT_SEED = 20260814
PERM_SEED = 20260814
Z95_ONE, Z95_TWO = 1.645, 1.96
S0_TOL = 0.0010
EQUIV_DELTA = 0.02          # TOST indifference margin, EFV_GATE_STANDARD s
COVER_LO, COVER_HI = 0.90, 0.98   # two-sided: over-coverage fails like under


# ─────────────────────────────────────────────────────────────────────────────
# THE FOLD REPLAY
# ─────────────────────────────────────────────────────────────────────────────
def _replay(side: str) -> dict:
    """Forward-chained replay of efv_model._run_eval's debuted_km folds.

    Emits per-test-row channels so every arm is scored on the IDENTICAL rows in
    the IDENTICAL order. The single-affine arms need a second pass, because
    their calibration is not known until every fold's train set has been seen.
    """
    import efv_model as M
    import value_framework as vf
    import efv_score as _es
    from efv_dataset import matrix_path
    from prospect_path import _fit_linear_calibration, _spearman

    keys, _mono = M._feature_spec(side)
    lam = M.blend_lambda(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = M._prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)

    knot = _es._outcome_floor_knot()

    # PASS 1: fit each fold, keep the raw ridge prediction per test row.
    folds = []
    bad_slope = []
    within_fold_affine_ok = True
    earliest_train = None
    for yr in M.SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = M._fit_ols_fv(train)
        ridge = M._fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(M._predict(ridge, r["feats"]), r["target"])
                                       for r in train])
        a_f, b_f = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        if b_f <= 0:
            bad_slope.append(yr)
        if earliest_train is None:
            # A2a's calibration: the FIRST fold's train window, the largest
            # leak-free sample that precedes every scored row.
            earliest_train = [(M._predict(ridge, r["feats"]), r["target"]) for r in train]
        recs = []
        for r in test:
            recs.append({
                "key": r["player_key"],
                "w": float(r.get("weight") or 1.0),
                "t": r["target"],
                "cons": max(0.0, M._pred_ols(ols, r["fv"])),
                "pred": M._predict(ridge, r["feats"]),
                "a_f": a_f, "b_f": b_f,
            })
        # Within-fold affine invariance: a strictly increasing affine cannot
        # move Spearman INSIDE a fold. Measured so the pooled C-c failure can
        # be attributed rather than guessed at.
        _p = [x["pred"] for x in recs]
        _t = [x["t"] for x in recs]
        if len(_p) >= 8 and _spearman(_p, _t) != _spearman([a_f + b_f * v for v in _p], _t):
            within_fold_affine_ok = False
        folds.append(recs)

    flat = [r for f in folds for r in f]

    # PASS 2: the two SINGLE-affine calibrations.
    cal_a = _fit_linear_calibration(earliest_train or [])
    a0, b0 = (cal_a["a"], cal_a["b"]) if cal_a else (0.0, 1.0)
    cal_full = _fit_linear_calibration([(r["pred"], r["t"]) for r in flat])
    aF, bF = (cal_full["a"], cal_full["b"]) if cal_full else (0.0, 1.0)

    def _grade(war):
        g = vf.outcome_implied_fv(max(-2.0, war), exposure_seasons=6)
        return None if g is None else round(g, 1)

    for r in flat:
        a_f, b_f, pred, cons = r["a_f"], r["b_f"], r["pred"], r["cons"]
        # A0 IS THE PUBLISHED ARM AND IT TAKES THE RAW RIDGE PREDICTION.
        # efv_model._run_eval:1534 is
        #   (1-lam)*max(0, _pred_ols(ols, fv)) + lam*_predict(ridge, feats)
        # with NO output calibration and NO -2.0 clamp on the model leg. My
        # first replay calibrated and clamped it, which reproduced hitters
        # inside tolerance (0.3936 vs 0.3933) and MISSED pitchers (0.2552 vs
        # 0.2584). S0 is a blocking clause precisely so a wrong replay cannot
        # become a finding; it caught this one.
        # NOTE efv_score.oos_grades uses a DIFFERENT blend, with the
        # calibrated and clamped leg. Two blends exist under one name; this
        # lane scores the one the eval publishes.
        r["A0_blend"] = (1 - lam) * cons + lam * pred
        r["A1_served_foldcal"] = _grade(a_f + b_f * pred)
        r["A2a_served_prodcal"] = _grade(a0 + b0 * pred)
        r["A2b_served_leaked"] = _grade(aF + bF * pred)
        # A3 is the CLEAN counterfactual of A0: the identical quantity pushed
        # through the grade map, so the difference is map plus rounding and
        # nothing else. tools/efv_board_serve_probe.py grades the CALIBRATED
        # blend instead, which mixes the calibration back in; that arm answers
        # a different question and is not comparable to A0.
        r["A3_blend_graded"] = _grade((1 - lam) * cons + lam * pred)
        r["A4_ridge"] = pred
        r["A5_baseline"] = cons
        r["affine_single_unclamped"] = a0 + b0 * pred

    return {
        "side": side, "lambda": lam, "rows": flat, "folds": folds, "knot": knot,
        "single_affine": {"a": round(a0, 6), "b": round(b0, 6),
                          "n_fit": len(earliest_train or [])},
        "leaked_affine": {"a": round(aF, 6), "b": round(bF, 6), "n_fit": len(flat)},
        "folds_with_nonpositive_calibration_slope": bad_slope,
        "within_fold_affine_invariance_holds": within_fold_affine_ok,
        "n_players": len({r["key"] for r in flat}),
        "n_rows": len(flat),
    }


ARMS = ("A0_blend", "A1_served_foldcal", "A2a_served_prodcal", "A2b_served_leaked",
        "A3_blend_graded", "A4_ridge", "A5_baseline")


def _rho(rows, arm) -> float | None:
    from prospect_path import _score
    pairs = [(r[arm], r["t"]) for r in rows if r.get(arm) is not None]
    wts = [r["w"] for r in rows if r.get(arm) is not None]
    if not pairs:
        return None
    return (_score(pairs, wts) or {}).get("spearman")


# ─────────────────────────────────────────────────────────────────────────────
# S1  THE FLOOR, DERIVED HERE
# ─────────────────────────────────────────────────────────────────────────────
def _e_cond(rows, arm_a, arm_b, B, seed) -> dict:
    """E_cond: hold the fit, resample the SCORED rows only, clustered by player.

    The matrices are one row per player, asserted rather than assumed, so a
    player cluster IS a row here. The assert is the guard that keeps this
    honest if a future matrix ever carries two rows for one key.
    """
    keys = [r["key"] for r in rows]
    assert len(set(keys)) == len(keys), (
        "matrix carries repeated player_keys; a row bootstrap would be "
        "anti-conservative and this estimator must cluster instead")
    rng = random.Random(seed)
    n = len(rows)
    deltas = []
    for _ in range(B):
        draw = [rows[rng.randrange(n)] for _ in range(n)]
        ra, rb = _rho(draw, arm_a), _rho(draw, arm_b)
        if ra is not None and rb is not None:
            deltas.append(ra - rb)
    return _summarize(deltas)


def _summarize(deltas) -> dict:
    if not deltas:
        return {"B_effective": 0, "sd": None, "mde95": None}
    m = sum(deltas) / len(deltas)
    sd = math.sqrt(sum((d - m) ** 2 for d in deltas) / max(1, len(deltas) - 1))
    s = sorted(deltas)
    return {
        "B_effective": len(deltas),
        "boot_mean": round(m, 6),
        "sd": round(sd, 6),
        "mde95": round(Z95_ONE * sd, 4),
        "mde95_twosided": round(Z95_TWO * sd, 4),
        "ci95": [round(s[int(0.025 * (len(s) - 1))], 5),
                 round(s[int(0.975 * (len(s) - 1))], 5)],
    }


def _verdict(delta, floor) -> dict:
    if delta is None or not floor:
        return {"verdict": "UNMEASURED"}
    margin = abs(delta) / floor
    if delta < -floor:
        v = "SERVED LOSES"
    elif delta > floor:
        v = "SERVED WINS"
    else:
        v = "not resolvable at this power"
    return {"delta": round(delta, 5), "mde95": floor,
            "margin_x_floor": round(margin, 3), "verdict": v}


def run(b_cond: int = 2000) -> dict:
    import efv_model as M
    rep = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gate": GATE,
        "lane": "S-1",
        "estimator_note": ("MDE95 = 1.645 * sd(delta), one-sided, matching "
                           "tools/efv_mde_lab.py. mde95_twosided = 1.96 * sd is "
                           "reported beside it. E_cond is the PRE-REGISTERED "
                           "PRIMARY because the contrast is same-fit by "
                           "construction."),
        "B_cond": b_cond,
        "seeds": {"bootstrap": BOOT_SEED, "permutation": PERM_SEED},
        "sides": {},
    }
    serve_pub = json.loads((DATA / SERVE_PATH_EVAL).read_text(encoding="utf-8"))

    for side in SIDES:
        st = _replay(side)
        rows = st["rows"]
        rhos = {a: _rho(rows, a) for a in ARMS}

        pub = json.loads((DATA / PUBLISHED[side]).read_text(encoding="utf-8"))
        pub = pub["evals"]["debuted_km"]["pooled_oos"]
        g3 = serve_pub["clauses"]["G3_attribution"][side]["rho"]

        s0 = {
            "published_baseline": pub["baseline"]["spearman"],
            "replay_baseline": rhos["A5_baseline"],
            "published_blend": pub["blend"]["spearman"],
            "replay_blend": rhos["A0_blend"],
            "published_ridge": pub["ridge"]["spearman"],
            "replay_ridge": rhos["A4_ridge"],
            "published_n": pub["blend"]["n"],
            "replay_n": st["n_rows"],
            "serve_path_2026_08_08_served": g3["served_grade"],
            "replay_served_foldcal": rhos["A1_served_foldcal"],
        }
        def _near(a, b):
            return a is not None and b is not None and abs(a - b) <= S0_TOL
        s0["pass_current_eval"] = bool(
            _near(s0["published_baseline"], s0["replay_baseline"])
            and _near(s0["published_blend"], s0["replay_blend"])
            and _near(s0["published_ridge"], s0["replay_ridge"])
            and s0["published_n"] == s0["replay_n"])
        # The 2026-08-08 figure was computed on a DIFFERENT basis (pre C-4/C-7),
        # so it is reported as drift, not gated. Recording it is what lets a
        # reader tell a basis move from a replay defect.
        s0["drift_vs_2026_08_08_served"] = (
            None if not _near(0, 0) or g3["served_grade"] is None
            or rhos["A1_served_foldcal"] is None
            else round(rhos["A1_served_foldcal"] - g3["served_grade"], 5))

        # ── S1 floors, for BOTH gated contrasts
        floors = {}
        for name, (a, b) in {
            "A4_ridge_vs_A0_blend": ("A4_ridge", "A0_blend"),
            "A2a_served_vs_A0_blend": ("A2a_served_prodcal", "A0_blend"),
        }.items():
            floors[name] = {"E_cond": _e_cond(rows, a, b, b_cond, BOOT_SEED)}

        # ── S2 verdicts
        d_ridge = (rhos["A4_ridge"] - rhos["A0_blend"]
                   if None not in (rhos["A4_ridge"], rhos["A0_blend"]) else None)
        d_a2a = (rhos["A2a_served_prodcal"] - rhos["A0_blend"]
                 if None not in (rhos["A2a_served_prodcal"], rhos["A0_blend"]) else None)
        s2 = {
            "A2a_vs_blend": _verdict(d_a2a, floors["A2a_served_vs_A0_blend"]["E_cond"]["mde95"]),
            "A4_vs_blend": _verdict(d_ridge, floors["A4_ridge_vs_A0_blend"]["E_cond"]["mde95"]),
            "served_below_consensus_bar": (
                None if None in (rhos["A2a_served_prodcal"], rhos["A5_baseline"])
                else bool(rhos["A2a_served_prodcal"] < rhos["A5_baseline"])),
            "served_minus_consensus": (
                None if None in (rhos["A2a_served_prodcal"], rhos["A5_baseline"])
                else round(rhos["A2a_served_prodcal"] - rhos["A5_baseline"], 5)),
        }
        # TOST: a gap whose CI sits wholly inside +/- EQUIV_DELTA is RULED OUT.
        ci = floors["A2a_served_vs_A0_blend"]["E_cond"].get("ci95")
        if ci and d_a2a is not None:
            lo, hi = d_a2a + (ci[0] - floors["A2a_served_vs_A0_blend"]["E_cond"]["boot_mean"]), \
                     d_a2a + (ci[1] - floors["A2a_served_vs_A0_blend"]["E_cond"]["boot_mean"])
            s2["tost"] = {"delta_margin": EQUIV_DELTA,
                          "ci95_centered": [round(lo, 5), round(hi, 5)],
                          "ruled_out_as_material": bool(lo > -EQUIV_DELTA and hi < EQUIV_DELTA)}

        # ── S4 controls
        rng = random.Random(PERM_SEED)
        perm_rows = []
        for f in st["folds"]:
            sub = [r for r in rows if r["key"] in {x["key"] for x in f}]
            vals = [r["A2a_served_prodcal"] for r in sub]
            idx = list(range(len(sub)))
            rng.shuffle(idx)
            for j, k in enumerate(idx):
                perm_rows.append({**sub[j], "A2a_served_prodcal": vals[k]})
        knot = st["knot"]
        served_vals = [r["A2a_served_prodcal"] for r in rows
                       if r["A2a_served_prodcal"] is not None]
        from prospect_path import _spearman
        c1_unclamped = _spearman([r["affine_single_unclamped"] for r in rows],
                                 [r["t"] for r in rows])
        c1_ridge = _spearman([r["A4_ridge"] for r in rows], [r["t"] for r in rows])
        controls = {
            "C1_affine_invariance": {
                "rho_single_affine_unclamped": round(c1_unclamped, 6),
                "rho_ridge": round(c1_ridge, 6),
                "equal_to_4dp": round(c1_unclamped, 4) == round(c1_ridge, 4),
                "rho_A2a_served": rhos["A2a_served_prodcal"],
                "collapse_gap_vs_ridge": (
                    None if None in (rhos["A2a_served_prodcal"], rhos["A4_ridge"])
                    else round(rhos["A2a_served_prodcal"] - rhos["A4_ridge"], 5)),
                "folds_with_nonpositive_slope": st["folds_with_nonpositive_calibration_slope"],
                "within_fold_affine_invariance_holds": st["within_fold_affine_invariance_holds"],
                "note": ("THE HYPOTHESIS. Under ONE global affine the served grade is "
                         "non-decreasing in the ridge prediction, so rho(A2a) should "
                         "equal rho(A4) up to 1dp rounding ties. A large gap REFUTES "
                         "the collapse and the gate falls back to gating A2a directly."),
            },
            "C2_permutation": {"rho": round(_rho(perm_rows, "A2a_served_prodcal") or 0.0, 4),
                               "pass": abs(_rho(perm_rows, "A2a_served_prodcal") or 0.0) < 0.05},
            "C3_tie_mass": {
                "floor_knot": knot,
                "share_at_floor": (round(sum(1 for v in served_vals
                                             if abs(v - knot) <= 1e-9) / len(served_vals), 4)
                                   if served_vals else None),
                "distinct_served_values": len(set(served_vals)),
                "gate": 0.50,
            },
            "C4_basis_drift": {
                "board_basis_fingerprint": _fingerprint(),
                "matrix_mtimes": _matrix_mtimes(),
                "published_eval_generated_at": json.loads(
                    (DATA / PUBLISHED[side]).read_text(encoding="utf-8")).get("generated_at"),
            },
        }

        rep["sides"][side] = {
            "n_rows": st["n_rows"], "n_players": st["n_players"], "lambda": st["lambda"],
            "single_affine": st["single_affine"], "leaked_affine": st["leaked_affine"],
            "rho": {a: (round(v, 5) if v is not None else None) for a, v in rhos.items()},
            "S0_reproduction": s0,
            "S1_floors": floors,
            "S2_verdict": s2,
            "S3_attribution": {
                "dropped_consensus_leg_A4_minus_A0": (
                    None if d_ridge is None else round(d_ridge, 5)),
                "tie_clamp_round_cost_A3_minus_A0": (
                    None if None in (rhos["A3_blend_graded"], rhos["A0_blend"])
                    else round(rhos["A3_blend_graded"] - rhos["A0_blend"], 5)),
                "separable_at_floor": None,   # filled below once floors are known
            },
            "S4_controls": controls,
            "A2b_leaks": True,
        }
        sep = rep["sides"][side]["S3_attribution"]
        f = floors["A4_ridge_vs_A0_blend"]["E_cond"]["mde95"]
        if f and None not in (sep["dropped_consensus_leg_A4_minus_A0"],
                              sep["tie_clamp_round_cost_A3_minus_A0"]):
            sep["separable_at_floor"] = bool(
                abs(sep["dropped_consensus_leg_A4_minus_A0"]
                    - sep["tie_clamp_round_cost_A3_minus_A0"]) > f)

    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


def _fingerprint():
    try:
        import efv_score as es
        return es.board_basis_fingerprint()
    except Exception:
        return None


def _matrix_mtimes():
    from efv_dataset import matrix_path
    out = {}
    for s in SIDES:
        try:
            p = matrix_path(s)
            out[s] = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            out[s] = None
    return out


if __name__ == "__main__":
    b = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    r = run(b)
    for side, s in r["sides"].items():
        print(f"\n=== {side}  n={s['n_rows']} players={s['n_players']} lam={s['lambda']} ===")
        for a, v in s["rho"].items():
            print(f"   {a:24s} {v}")
        print("  S0 reproduction pass:", s["S0_reproduction"]["pass_current_eval"])
        print("  C1 collapse gap (A2a - A4):",
              s["S4_controls"]["C1_affine_invariance"]["collapse_gap_vs_ridge"],
              "| unclamped==ridge to 4dp:",
              s["S4_controls"]["C1_affine_invariance"]["equal_to_4dp"])
        print("  S2 A2a vs blend:", json.dumps(s["S2_verdict"]["A2a_vs_blend"]))
        print("  S2 A4 vs blend :", json.dumps(s["S2_verdict"]["A4_vs_blend"]))
        print("  served below consensus bar:", s["S2_verdict"]["served_below_consensus_bar"],
              s["S2_verdict"]["served_minus_consensus"])
        print("  C3 tie mass:", json.dumps(s["S4_controls"]["C3_tie_mass"]))
    print("\nwrote", OUT)
