"""C-5 DIAGNOSTIC: attribute the board-wide eFV deflation to the model or to the map.

Not a ship lane and not gated. It answers one question that three previous lanes
(C-1b five families, C-1c elite bands, C-1d fitting frames) all assumed away:

    every one of them corrected the INPUT to vf.outcome_implied_fv.
    None of them asked what that map does to a correct input.

So this lab feeds the map the TRUTH. `fv_earned = outcome_implied_fv(realized_war)`
is the grade an oracle predictor would have been served. Whatever gap remains
between that and consensus FV is attributable to the MAP, because an oracle has no
prediction error left to blame.

    total deflation  =  map term (oracle vs consensus)  +  model term (eFV vs oracle)

Reported per consensus band, plus the two mechanisms that can produce a map term:

  JENSEN     outcome_implied_fv is violently concave (about 44 FV per WAR at 0 WAR
             against 2.8 FV per WAR at FV 50-55, a 16x swing), so the mean of the
             grades is not the grade of the mean. Quantified directly as
             g(mean W) - mean g(W) inside each band.
  FLOOR      every prediction at or below 0 WAR returns exactly knot 0, so the map
             cannot express a difference there at all.

Usage:  python tools/efv_grade_space_lab.py
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

_spec = _ilu.spec_from_file_location("_band", HERE / "efv_elite_band_lab.py")
BAND = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(BAND)

import efv_score as E            # noqa: E402
import value_framework as vf     # noqa: E402

SIDES = ("hit", "pit")
FLOOR = -2.0
ART = ROOT / "data" / "xfv_grade_space_diag.json"

# Bands cut on consensus FV, a PRE-DECISION quantity. Never on the outcome and never
# on anything the model produced (the C-1c selection lesson).
BANDS = (("below_40", -1e9, 40.0), ("b40_45", 40.0, 45.0), ("b45_50", 45.0, 50.0),
         ("b50_55", 50.0, 55.0), ("ge_55", 55.0, 1e9))


def _fv(war):
    """The served grade map, elementwise, with the floor knot for non-positive WAR."""
    return np.array([float(vf.outcome_implied_fv(float(w), exposure_seasons=6))
                     for w in np.asarray(war, float)], float)


def _sensitivity():
    """dFV/dWAR along the shipped curve, so the 16x swing is measured, not asserted."""
    c = vf._outcome_curve()
    ks, vs = np.array(c["knots"], float), np.array(c["value"], float)
    out = []
    for (k0, v0), (k1, v1) in zip(zip(ks, vs), zip(ks[1:], vs[1:])):
        out.append({"fv_from": k0, "fv_to": k1,
                    "war_from": round(v0, 4), "war_to": round(v1, 4),
                    "fv_per_war": round((k1 - k0) / (v1 - v0), 2)})
    return out


def _block(cons, war, arms):
    """One band: the decomposition, in FV units."""
    n = len(cons)
    fv_earned = arms["oracle"]
    blk = {
        "n": int(n),
        "mean_consensus": round(float(cons.mean()), 3),
        "mean_realized_war": round(float(war.mean()), 4),
        # THE DECOMPOSITION
        "map_term_oracle_minus_cons": round(float(fv_earned.mean() - cons.mean()), 3),
    }
    for name, fv in arms.items():
        blk[f"mean_fv_{name}"] = round(float(fv.mean()), 3)
        blk[f"delta_{name}_minus_cons"] = round(float(fv.mean() - cons.mean()), 3)
        if name != "oracle":
            blk[f"model_term_{name}_minus_oracle"] = round(
                float(fv.mean() - fv_earned.mean()), 3)
    # JENSEN, isolated: grade of the mean against mean of the grades
    g_of_mean = float(vf.outcome_implied_fv(float(war.mean()), exposure_seasons=6))
    blk["jensen_g_of_meanW_minus_mean_gW"] = round(g_of_mean - float(fv_earned.mean()), 3)
    blk["g_of_mean_realized_war"] = round(g_of_mean, 3)
    # FLOOR: how much of each arm is pinned at the knot the map cannot resolve
    knot = float(vf._outcome_curve()["knots"][0])
    for name, fv in arms.items():
        blk[f"share_at_floor_knot_{name}"] = round(
            float(np.mean(np.abs(fv - knot) < 1e-9)), 4)
    # CURVE SELF-CONSISTENCY: does the band's realized mean reproduce the band's grade?
    c = vf._outcome_curve()
    curve_at_cons = float(np.interp(cons.mean(), c["knots"], c["value"]))
    blk["curve_war_at_mean_cons"] = round(curve_at_cons, 4)
    blk["curve_residual_realized_minus_curve"] = round(
        float(war.mean()) - curve_at_cons, 4)
    return blk


def run():
    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
                            .isoformat().replace("+00:00", "Z"),
        "lane": "C-5 diagnostic, not a gated ship lane",
        "question": "is the board-wide eFV deflation a property of the model or of "
                    "vf.outcome_implied_fv",
        "curve_hash": vf.outcome_curve_identity(),
        "curve_sensitivity_fv_per_war": _sensitivity(),
        "sides": {},
    }
    for side in SIDES:
        rows = BAND._pool_with_consensus(side)
        is_pit = side == "pit"
        cons = np.array([r["cons"] for r in rows], float)
        war = np.array([r["war"] for r in rows], float)
        arms = {
            "oracle": _fv(war),
            "A_corrected": _fv([E.apply_dispersion_correction(r["raw"], is_pit)
                                for r in rows]),
            "B_uncorrected": _fv([max(FLOOR, r["raw"]) for r in rows]),
        }
        blk = {"n_pool": len(rows), "pool": _block(cons, war, arms), "bands": {}}
        for label, lo, hi in BANDS:
            sel = (cons >= lo) & (cons < hi)
            if sel.sum() < 5:
                blk["bands"][label] = {"n": int(sel.sum()), "skipped": "too few rows"}
                continue
            blk["bands"][label] = _block(
                cons[sel], war[sel], {k: v[sel] for k, v in arms.items()})
        out["sides"][side] = blk

    ART.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _print(res):
    print(f"\ncurve {res['curve_hash']}   dFV/dWAR along the shipped map:")
    for s in res["curve_sensitivity_fv_per_war"][:9]:
        print(f"   FV {s['fv_from']:>4.1f} to {s['fv_to']:>4.1f}   "
              f"WAR {s['war_from']:>7.3f} to {s['war_to']:>7.3f}   "
              f"{s['fv_per_war']:>8.2f} FV per WAR")
    for side, blk in res["sides"].items():
        print(f"\n===== {side}   pool n={blk['n_pool']} =====")
        hdr = (f"  {'band':<10} {'n':>5} {'cons':>7} {'oracle':>7} {'MAP':>7} "
               f"{'eFV_A':>7} {'MODEL':>7} {'TOTAL':>7} {'jensen':>7} {'floorA':>7}")
        print(hdr)
        for label in ("pool",) + tuple(b[0] for b in BANDS):
            b = blk["pool"] if label == "pool" else blk["bands"].get(label) or {}
            if b.get("skipped") or not b:
                continue
            print(f"  {label:<10} {b['n']:>5} {b['mean_consensus']:>7.2f} "
                  f"{b['mean_fv_oracle']:>7.2f} {b['map_term_oracle_minus_cons']:>+7.2f} "
                  f"{b['mean_fv_A_corrected']:>7.2f} "
                  f"{b['model_term_A_corrected_minus_oracle']:>+7.2f} "
                  f"{b['delta_A_corrected_minus_cons']:>+7.2f} "
                  f"{b['jensen_g_of_meanW_minus_mean_gW']:>+7.2f} "
                  f"{b['share_at_floor_knot_A_corrected']:>7.1%}")
        p = blk["pool"]
        print(f"    uncorrected arm, pool: {p['delta_B_uncorrected_minus_cons']:+.2f} "
              f"vs consensus, {p['share_at_floor_knot_B_uncorrected']:.1%} at the floor knot")
        print(f"    curve residual, pool: realized {p['mean_realized_war']:.3f} against "
              f"curve {p['curve_war_at_mean_cons']:.3f} at mean consensus "
              f"({p['curve_residual_realized_minus_curve']:+.3f})")


if __name__ == "__main__":
    _print(run())
