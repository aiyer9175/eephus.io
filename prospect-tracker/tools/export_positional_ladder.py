# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
export_positional_ladder.py - publish the fitted defensive positional
adjustments to `positional-adjustments/` for Will's eWAR and SDR work.

READ-ONLY BY CONSTRUCTION. This slices `data/positional_fit.json`; it never
refits. positional_fit.fit_ladder is THE ladder (prospect_def_value.py states
the one-owner rule, and two independently refitted ladders once disagreed by
0.35 runs), so an exporter that computed its own copy would be a second owner
by the back door. If the artifact is missing this refuses rather than building
one.

BOTH BASES SHIP, NAMED. This is the module's recurring failure mode and the
export is the likeliest place to repeat it:

  * `values` is the exposure-weighted-zero column. Every internal valuation
    runs on it, and it is the one that matches the Baseball-Reference frame
    eWAR rides. USE THIS ONE unless you have a reason not to.
  * `values_fielder_centred` is the folklore-comparable column: the eight
    fielding rungs sum to zero and DH sits outside the sum. Display convention.

They differ by a single constant, so every GAP between two positions is
identical in both. Shipping one column without naming its basis is what
produced the "the ladder does not sum to zero" report the identification block
exists to answer, so the identification block ships with it.

THE THREE SUMS, because a receiver will otherwise "fix" one of them:
  * exposure-weighted over all nine rungs = 0, imposed by the fit.
  * equal-weight over nine rungs = -1.87, and SHOULD NOT be zero: DH is about
    9% of exposure, not a ninth, so equal-weighting over-counts its penalty.
  * equal-weight over the eight fielders on the model column = +11.83, which is
    forced arithmetically once the weighted sum is pinned.

Usage:
    python tools/export_positional_ladder.py            # write the bundle
    python tools/export_positional_ladder.py --check    # verify, write nothing
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "data" / "positional_fit.json"
OUT_DIR = ROOT.parent / "positional-adjustments"

#: Bumped by hand when the SHAPE changes, not when the numbers move. A refit is
#: a new `generated_at`, not a new schema version.
SCHEMA_VERSION = "1.0.0"

POS_ORDER = ("C", "SS", "2B", "3B", "CF", "LF", "RF", "1B", "DH")


def build(artifact: Path = ARTIFACT) -> dict:
    if not artifact.exists():
        raise SystemExit(f"FATAL: {artifact} not found. This exporter slices the "
                         "committed artifact and deliberately cannot refit it; "
                         "run positional_fit.py first.")
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    L = (doc.get("fit") or {}).get("ladder") or {}
    if not L.get("values"):
        raise SystemExit("FATAL: artifact carries no fit.ladder.values")

    ident = L.get("identification") or {}
    fb = L.get("folklore_basis") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_artifact": "prospect-tracker/data/positional_fit.json",
        "source_generated_at": doc.get("generated_at"),
        "model_id": "positional_ladder",
        "what_this_is": (
            "Defensive positional adjustments re-estimated from "
            "Baseball-Reference's own construction rather than taken from the "
            "folklore table. Least squares of BRef runs_position per 650 PA on "
            "per-row innings shares, no intercept, recentred so the "
            "exposure-weighted sum over all nine positions is zero."),
        "important": (
            "This is an INVERSION, not an independent measure of defensive "
            "difficulty. A rung reads as what Baseball-Reference PRICES that "
            "position at. For work that rides the bWAR frame (eWAR) that is the "
            "feature; for a from-scratch defensive model it is a constraint."),
        "units": L.get("units"),
        "method": L.get("method"),
        "bases": {
            "primary": "values",
            "values": {
                "basis": "exposure_weighted_zero",
                "use_for": ("everything that rides the bWAR frame, including "
                            "eWAR; this is what every internal valuation uses"),
                "values": {p: L["values"].get(p) for p in POS_ORDER
                           if L["values"].get(p) is not None},
            },
            "values_fielder_centred": {
                "basis": "fielder_centred_zero",
                "use_for": ("comparison against the published folklore table, "
                            "whose eight fielders also sum to zero with DH "
                            "outside it"),
                "values": {p: (ident.get("values_fielder_centred") or {}).get(p)
                           for p in POS_ORDER
                           if (ident.get("values_fielder_centred") or {}).get(p) is not None},
            },
            "note": ("the two differ by one constant, so every gap between two "
                     "positions is identical in both"),
        },
        "identification": ident,
        "ci95": L.get("ci95"),
        "fit": {
            "seasons": L.get("seasons"),
            "window_seasons": L.get("window_seasons"),
            "window_basis": L.get("window_basis"),
            "n_player_seasons": L.get("n_player_seasons"),
            "min_pa": L.get("min_pa"),
            "r2": L.get("r2"),
            "resid_sd": L.get("resid_sd"),
            "inn_per_pa": L.get("inn_per_pa"),
            "dh_exposure_spec": L.get("dh_exposure_spec"),
        },
        # The reliability constants ewar.py already consumes. SDR shrinkage will
        # want an equivalent, and they are the part of positional_fit Will's
        # fielding work actually touches.
        "signal_k_inn": {p: ((doc.get("fit") or {}).get("signal") or {}).get(p, {}).get("k_inn")
                         for p in POS_ORDER
                         if ((doc.get("fit") or {}).get("signal") or {}).get(p, {}).get("k_inn") is not None},
        "era_splits": L.get("era_splits"),
        "window_sensitivity": L.get("window_sensitivity"),
        "folklore_comparison": {
            "folklore_ladder_as_quoted": L.get("folklore_ladder"),
            "basis": fb,
            "read_this": (
                "the folklore table is quoted per full defensive season and "
                "ours per 650 PA of exposure, so subtracting them directly "
                "overstates folklore by about 14 percent. Both the raw and the "
                "rescaled comparison are published and neither is presented as "
                "the answer: the convention is ambiguous across sources, and "
                "the folklore ladder is FanGraphs/Tango while this fit inverts "
                "Baseball-Reference."),
        },
    }


def write(payload: dict, out_dir: Path = OUT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    p_json = out_dir / "positional_ladder_v1.json"
    p_json.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    written.append(p_json)

    # CSV carries BOTH columns and their CI, because a one-column CSV is the
    # shape that loses the basis.
    p_csv = out_dir / "positional_ladder_v1.csv"
    prim = payload["bases"]["values"]["values"]
    fc = payload["bases"]["values_fielder_centred"]["values"]
    ci = payload.get("ci95") or {}
    with p_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["position", "runs_per_650pa_exposure_weighted",
                    "runs_per_650pa_fielder_centred", "ci95_low", "ci95_high"])
        for p in POS_ORDER:
            if prim.get(p) is None:
                continue
            lo, hi = (ci.get(p) or [None, None])[:2] or (None, None)
            w.writerow([p, prim.get(p), fc.get(p), lo, hi])
    written.append(p_csv)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="build and validate, write nothing")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    payload = build()
    prim = payload["bases"]["values"]["values"]
    fc = payload["bases"]["values_fielder_centred"]["values"]
    if len(prim) != 9:
        raise SystemExit(f"FATAL: expected 9 rungs, got {sorted(prim)}")
    # The export must not be the place a basis silently collapses: the two
    # columns have to differ by ONE constant across every position.
    shifts = {round(prim[p] - fc[p], 6) for p in prim if fc.get(p) is not None}
    if len(shifts) != 1:
        raise SystemExit(f"FATAL: the two bases differ by more than one "
                         f"constant ({sorted(shifts)}); they are not the same "
                         f"ladder and must not ship as one export")
    print(f"ladder ok: 9 rungs, bases differ by a single constant "
          f"{shifts.pop():+.4f}")
    if args.check:
        print("--check: nothing written")
        return 0
    for p in write(payload, args.out):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
