"""LANE-P2: persist the POOLED FV-to-outcome curve that eFV's grade map inverts.

Pre-registration: docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md (PART 1, committed before
the first production edit). Phase-1 input: docs/efv-2026-07-30/FV_OUTCOME_CURVES_GATE.md.
Artifact: data/fv_outcome_curves_pooled.json   Registry row: fv_outcome_pooled_grade

WHY THIS EXISTS AND WHY IT IS THREE SCREENS LONG INSTEAD OF THIRTY.

Phase 1 fit per-side curves and persisted them to data/fv_outcome_curves.json. It ALSO fit
the pooled (side-neutral) curve -- twice, once per fold for the `empirical_pooled` bake-off
arm and once on the full primary pool for the pooled column of its board-mix table -- but
never persisted that object, because Phase 1 shipped nothing. The owner then read Phase 1's
own reject criteria (the side split is a NULL against a side-label-permuted control, and the
entire top-100 pitcher move 6 -> 17 is attributable to the split) and chose the POOLED refit
only. So the one curve the ship needs is the one curve that was not written down.

This module does not re-implement the fit. It imports tools/fv_outcome_curves_lab.py and
calls the SAME fit_war_curve on the SAME pooled primary pool with the SAME prior expression
Phase 1 used (lab.run: `fit_war_curve(pooled, lambda fv: 0.5 * (priors["hit"](fv) +
priors["pit"](fv)))`), adds the player-clustered bootstrap band, and writes it out with a
content hash. Reproducing the fit rather than copying its numbers is the point: if the lab's
pipeline ever changes, this artifact regenerates from the changed pipeline and the content
hash moves, which moves storage.board_basis_fingerprint() and fails the suite until a human
decides the board's grade scale really did change.

READ-ONLY on every production module. Writes exactly one file, data/fv_outcome_curves_pooled.json.

Run:  python tools/fv_outcome_curve_pooled.py
      python tools/fv_outcome_curve_pooled.py --no-write
      python tools/fv_outcome_curve_pooled.py --fast     (B=200 bootstrap draws, for a smoke check)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import fv_outcome_curves_lab as lab                                   # noqa: E402

OUT = ROOT / "data" / "fv_outcome_curves_pooled.json"


def curve_hash(curve: dict) -> str:
    """SHA-1 over the (knot, value) pairs at 6dp -- the IDENTITY of the grade scale.

    storage.board_basis_fingerprint() names this hash, so any change to the curve (a
    refit, a different prior, a different pool) changes the board's recorded basis and
    the suite fails until BOARD_RANK_BASIS_EPOCH is bumped in the same commit. Only the
    shipped `value` list is hashed: n_cell / w_prior / CI bands are provenance, and a
    bootstrap seed change must not read as a board re-rank."""
    payload = ";".join(f"{k:.6f}:{v:.6f}" for k, v in zip(curve["knots"], curve["value"]))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def build(b_boot: int = lab.B_BOOT) -> dict:
    pool, checks = lab.load_pool()
    vintage = lab.verify_vintage()
    priors = {s: lab._prior_clemens(s) for s in ("hit", "pit")}
    unc = {s: [r for r in pool[s] if not r["censored"]] for s in ("hit", "pit")}
    pooled_rows = unc["hit"] + unc["pit"]

    # The pooled prior is the 50/50 average of the two per-side Clemens columns, exactly
    # as lab.run builds it. Averaging the PRIOR (rather than pooling a single published
    # table) keeps the pooled fit on the same prior scale as the per-side fits, so the
    # pooled-vs-per-side comparison Phase 1 reported is a comparison of the DATA split and
    # not of two different priors.
    def prior(fv: float) -> float:
        return 0.5 * (priors["hit"](fv) + priors["pit"](fv))

    curve = lab.fit_war_curve(pooled_rows, prior)
    curve.update(lab.bootstrap_curve(pooled_rows, prior, b=b_boot))

    # Re-assert the two properties the production inversion depends on, here rather than
    # in a comment: strictly increasing (so the inverse is single-valued) and anchored at
    # zero (so a non-positive predicted WAR reads exactly the FV20 floor, which is what
    # the retired realized_implied_fv did too).
    vals = curve["value"]
    strict = all(b > a for a, b in zip(vals, vals[1:]))
    assert strict, "pooled curve is not strictly increasing -- the inverse would be a set"
    assert abs(vals[0]) < 1e-9, f"pooled curve does not start at 0.0 WAR (got {vals[0]})"

    return {
        "line": "LANE-P2: the POOLED FV-to-outcome curve the eFV grade map inverts",
        "generated_at": date.today().isoformat(),
        "lab": "tools/fv_outcome_curve_pooled.py (imports tools/fv_outcome_curves_lab.py)",
        "pre_registration": "docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md",
        "phase1_source": "docs/efv-2026-07-30/FV_OUTCOME_CURVES_GATE.md + data/fv_outcome_curves.json",
        "plan": "docs/master-plan-2026-07-30-fv-calibration.md (Phase 2, POOLED variant)",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "registry_row": "fv_outcome_pooled_grade",
        "changes_served_output": True,
        "curve_hash": curve_hash(curve),
        "consumed_by": ("value_framework.outcome_implied_fv -> efv_score xfv_grade "
                        "(run / run_live / run_backgrade / score_history); named by "
                        "storage.board_basis_fingerprint()"),
        "schema": {
            "curve": ("E[first-6yr total label WAR | consensus FV], SIDES POOLED. Parallel "
                      "per-knot lists: knots, isotonic (raw PAVA fit), cell_mean (raw mean "
                      "of the +/-1.25 FV cell), prior (50/50 average of the two Clemens "
                      "2026 per-side columns), n_cell, w_prior (K/(K+n_cell), K=30), shrunk, "
                      "value (the SHIPPED curve: shrunk, re-PAVA'd at weight n_cell+K, then "
                      "forced to a strict +0.01 WAR minimum per knot step), ci90_lo/hi "
                      "(player-clustered bootstrap, full refit on each draw), extrapolation."),
            "curve.value[0:3]": ("FV 20 / 25 / 30 are BELOW THE DATA FLOOR and are NOT a "
                                 "measurement. They are the production concave re-spread "
                                 "value(35) * ((fv-20)/15) ** (1/0.45), the exact inverse of "
                                 "value_framework._LOWEND_FG_EXP, so keeping the incumbent "
                                 "low-end display granularity is a no-op against this curve. "
                                 "No grade below about 45 is outcome-calibrated."),
            "curve_hash": ("SHA-1(12) over the (knot, value) pairs at 6dp. The board's grade "
                           "scale identity; storage.board_basis_fingerprint() names it so a "
                           "curve change cannot reach the board without an epoch bump."),
            "top_end_is_prior": ("From FV 57.5 up the pooled cell n is 8/23/2/12/2/1 and "
                                 "w_prior runs 0.57 to 0.97: those knots are the Clemens 2026 "
                                 "table, not our measurement. Phase 1's C4 verdict carries "
                                 "over unchanged."),
        },
        "pool": {
            "rows": len(pooled_rows),
            "hit": len(unc["hit"]), "pit": len(unc["pit"]),
            "definition": "censored == False, both sides pooled (Phase 1 PRIMARY pool)",
            "x": "consensus_fv (== matrix consensus_fv_raw, PRE-DEBUT vintage)",
            "y": "realized_war_6yr (== matrix target_censored, the label efv_score scores)",
            "identity_checks": checks,
            "vintage_verification": vintage,
        },
        "method": {
            "fit": "tools/fv_outcome_curves_lab.fit_war_curve, unmodified",
            "prior": "0.5 * (clemens_hit + clemens_pit), each with the lab's declared "
                     "linear ramp to 0.0 below the table's bottom published row",
            "k_shrink": lab.K_SHRINK, "cell_halfwidth": lab.CELL_HALFWIDTH,
            "eps_step": lab.EPS_STEP, "knots": lab.KNOTS,
            "bootstrap": {"b": b_boot, "seed": lab.SEED,
                          "note": "player-clustered == row bootstrap here (0 cross-side key "
                                  "overlap, asserted in the lab)"},
            "strictly_increasing": strict,
            "monotone_repair_max_move": curve["monotone_repair_max_move"],
        },
        "curve": curve,
    }


def report(art: dict) -> None:
    c = art["curve"]
    print(f"pooled FV->outcome curve  n={art['pool']['rows']}  hash={art['curve_hash']}")
    print(f"{'FV':>6} {'n':>5} {'w_pri':>6} {'cell':>8} {'iso':>8} {'prior':>8} "
          f"{'VALUE':>9} {'ci90':>17}")
    for i, k in enumerate(c["knots"]):
        cm = c["cell_mean"][i]
        print(f"{k:6.1f} {c['n_cell'][i]:5d} {c['w_prior'][i]:6.3f} "
              f"{('-' if cm is None else f'{cm:8.3f}'):>8} {c['isotonic'][i]:8.3f} "
              f"{c['prior'][i]:8.3f} {c['value'][i]:9.4f} "
              f"{c['ci90_lo'][i]:8.3f} -{c['ci90_hi'][i]:8.3f}")
    print("monotone repair max move:", round(c["monotone_repair_max_move"], 4))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--fast", action="store_true", help="B=200 bootstrap draws (smoke check)")
    a = ap.parse_args()
    art = build(b_boot=200 if a.fast else lab.B_BOOT)
    report(art)
    if not a.no_write:
        OUT.write_text(json.dumps(art, indent=1), encoding="utf-8")
        print("wrote", OUT)


if __name__ == "__main__":
    main()
