"""C-1c: is the elite deflation a defect, or is eFV right?

Gate: docs/efv-2026-08-13/ELITE_POWERED_LANE_GATE.md, pre-registered before any
estimator was compared.

Three arms against REALIZED first-6-season WAR on a band selected by CONSENSUS FV
(a pre-decision quantity), plus the same comparison on the outcome-selected cut so
the selection effect the gate predicts is visible rather than argued.

Usage:  python tools/efv_elite_band_lab.py [B]
"""
from __future__ import annotations

import datetime as _dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

_spec = _ilu.spec_from_file_location("_lab", HERE / "efv_dispersion_repair_lab.py")
LAB = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(LAB)

import efv_model as M            # noqa: E402
import efv_score as E            # noqa: E402
import value_framework as vf     # noqa: E402

SIDES = ("hit", "pit")
FLOOR = -2.0
TS = 6
PRIMARY_BAND = 50.0
SECONDARY_BAND = 55.0
MIN_PRIMARY_ROWS = 150
ART = ROOT / "data" / "xfv_elite_band_eval.json"
MATRIX = {"hit": "xfv_hitter_matrix.json", "pit": "xfv_pitcher_matrix.json"}


def _pool_with_consensus(side):
    """The scored pool, carrying consensus_fv_raw so a band can be cut on it.

    NO JOIN. `_prep` already emits `decision_year` and `fv` (which IS
    consensus_fv_raw, efv_model.py:1305-1316), so the band anchor travels with the
    row. An earlier draft re-joined from the matrix by player_key and had to reason
    about emission order; carrying the field is strictly safer and the field was
    there all along.

    Otherwise this reproduces LAB._pool's forward chaining exactly: same guards
    (>=15 test, >=60 train), same train-only output calibration, same pre-clamp
    `raw`. It is not reused directly only because _pool does not emit `fv`.
    """
    raw = json.loads((ROOT / "data" / MATRIX[side]).read_text(encoding="utf-8"))
    keep = [r for r in raw if not (r.get("kind") == "bust" and r.get("bust_recent"))]
    prepped = M._prep(keep, "target_censored", side)
    keys = M._feature_spec(side)[0]

    out = []
    for yr in M.SCORED_YEARS:
        tr = [r for r in prepped if r["decision_year"] < yr]
        te = [r for r in prepped if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ridge = LAB._fit_ridge(tr, keys)
        if not ridge:
            continue
        cal = LAB._fit_linear_calibration(
            [(LAB._predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)   # dict, not tuple
        for r in te:
            out.append({
                "player_key": r["player_key"],
                "fold": yr,
                "raw": a + b * LAB._predict(ridge, r["feats"]),
                "war": r["target"],
                "cons": float(r["fv"]),
            })
    return out


def _arms(rows, side):
    """A corrected, B uncorrected, C consensus-implied, all in WAR units."""
    is_pit = side == "pit"
    war = np.array([r["war"] for r in rows], float)
    A = np.array([E.apply_dispersion_correction(r["raw"], is_pit) for r in rows], float)
    B = np.array([max(FLOOR, r["raw"]) for r in rows], float)
    # C: read the pooled outcome curve FORWARD at the consensus grade
    curve = vf._outcome_curve()
    ks, vs = curve["knots"], curve["value"]
    C = np.array([float(np.interp(r["cons"], ks, vs)) for r in rows], float)
    return war, {"A_corrected": A, "B_uncorrected": B, "C_consensus": C}


def _metrics(war, arm):
    err = arm - war
    return {
        "mae": round(float(np.mean(np.abs(err))), 4),
        "bias": round(float(np.mean(err)), 4),
        "spearman": round(float(_spearman(arm, war)), 4),
    }


def _spearman(x, y):
    def rk(v):
        o = np.argsort(v, kind="mergesort")
        r = np.empty(len(v), float)
        r[o] = np.arange(len(v), dtype=float)
        return r
    a, b = rk(x), rk(y)
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _paired(war, a, b, B, rng):
    """Paired bootstrap on MAE(A) - MAE(B). Negative means A is closer."""
    n = len(war)
    obs = float(np.mean(np.abs(a - war)) - np.mean(np.abs(b - war)))
    draws = []
    for _ in range(B):
        i = rng.integers(0, n, n)
        draws.append(float(np.mean(np.abs(a[i] - war[i])) - np.mean(np.abs(b[i] - war[i]))))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"delta_mae_A_minus_B": round(obs, 4),
            "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "excludes_zero": bool(lo > 0 or hi < 0),
            "favours": ("A_corrected" if hi < 0 else
                        "B_uncorrected" if lo > 0 else "neither")}


def run(B: int = 2000):
    rng = np.random.default_rng(7)
    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
                            .isoformat().replace("+00:00", "Z"),
        "gate": "docs/efv-2026-08-13/ELITE_POWERED_LANE_GATE.md",
        "B": B, "primary_band": PRIMARY_BAND, "sides": {},
    }
    for side in SIDES:
        rows = _pool_with_consensus(side)
        war, arms = _arms(rows, side)
        cons = np.array([r["cons"] for r in rows], float)
        blk = {"n_pool": len(rows)}

        # sanity control: on the FULL pool the correction must beat uncorrected
        blk["control_full_pool"] = {
            k: _metrics(war, v) for k, v in arms.items()}
        blk["control_full_pool"]["paired_A_vs_B"] = _paired(
            war, arms["A_corrected"], arms["B_uncorrected"], B, rng)

        for label, sel in (
            ("primary_cons_ge_50", cons >= PRIMARY_BAND),
            ("secondary_cons_ge_55", cons >= SECONDARY_BAND),
            ("biased_outcome_top_decile", war >= np.percentile(war, 90)),
        ):
            if sel.sum() < 5:
                blk[label] = {"n": int(sel.sum()), "skipped": "too few rows"}
                continue
            sub = {k: v[sel] for k, v in arms.items()}
            blk[label] = {"n": int(sel.sum())}
            blk[label].update({k: _metrics(war[sel], v) for k, v in sub.items()})
            blk[label]["paired_A_vs_B"] = _paired(
                war[sel], sub["A_corrected"], sub["B_uncorrected"], B, rng)
        out["sides"][side] = blk

    ART.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = run(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
    for side, blk in res["sides"].items():
        print(f"\n===== {side}  (pool n={blk['n_pool']}) =====")
        for label in ("control_full_pool", "primary_cons_ge_50",
                      "secondary_cons_ge_55", "biased_outcome_top_decile"):
            b = blk.get(label) or {}
            if b.get("skipped"):
                print(f"  {label}: {b['skipped']}")
                continue
            n = b.get("n", blk["n_pool"])
            print(f"  {label}  n={n}")
            for arm in ("A_corrected", "B_uncorrected", "C_consensus"):
                m = b.get(arm)
                if m:
                    print(f"      {arm:16s} MAE {m['mae']:7.4f}   bias {m['bias']:+8.4f}"
                          f"   rho {m['spearman']:+.4f}")
            p = b.get("paired_A_vs_B")
            if p:
                print(f"      paired A-B MAE {p['delta_mae_A_minus_B']:+.4f} "
                      f"CI{p['ci95']}  -> {p['favours']}")
