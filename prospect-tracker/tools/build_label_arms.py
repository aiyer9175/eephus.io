# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Build the four label arms of the eWAR label epoch (E0-E3) into separate matrices.

Appendix A of docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md froze two label-definition
fixes and the arm plan that isolates them:

    arm  label window                imputation for milb_unavailable rows
    E0   calendar (incumbent)        floor (incumbent)
    E1   service-aligned (A1)        floor
    E2   calendar                    neutral has-MiLB train mean (A2)
    E3   service-aligned             neutral

E0 is the arm the cross-label matrix and clause (a)'s hitter regen control read; E3 is
the candidate served frame. Each arm is the SAME build with a named difference: the two
flags are `efv_dataset.SERVICE_ALIGNED_WINDOW` (audit F03) and
`efv_model.NEUTRAL_MILB_IMPUTE` (audit F04), both default False.

WHAT THIS WRITES. One matrix per arm per side, under a suffixed name in data/_labs/
(data/_labs/xfv_hitter_matrix__E1.json and so on), so no arm overwrites another and
NONE of them overwrites the canonical data/xfv_hitter_matrix.json. The arms carry the
label side of the fit, so they sit one level below data/: both deploy consumers ship
data/*.json at depth one only (pinned by test_publish_manifest.py). It calls
efv_dataset.build_matrix directly and never efv_dataset.run, which is the function that
would write the canonical path.

WHAT A2 DOES NOT CHANGE. The A2 flag changes the imputation applied INSIDE a ridge fit
(efv_model._fit_ridge computes the has-MiLB mean on that fold's TRAIN rows), not the
matrix. So E2's rows are identical to E0's and E3's to E1's by construction; the arm
files are still written per arm so the fitter reads one path per arm and the flag state
is recorded beside the rows. The imputation census below counts the rows whose FEATURE
VECTOR would move, and reports the shift with a whole-matrix has-MiLB mean, which is a
CENSUS number: it is not the value any fold actually imputes, because a fold imputes at
its own train mean.

Importing this module does nothing. Run:
    python tools/build_label_arms.py --arm E0 --side hit
    python tools/build_label_arms.py --arm all --side pit
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ed          # noqa: E402
import efv_model as em            # noqa: E402

# arm -> (SERVICE_ALIGNED_WINDOW, NEUTRAL_MILB_IMPUTE)
ARMS = {
    "E0": (False, False),
    "E1": (True, False),
    "E2": (False, True),
    "E3": (True, True),
}

_LABEL_KEYS = ("target_resolved", "target_censored", "weight", "observed_seasons",
               "censored")


LABS_DIR = "_labs"


def arm_path(side: str, arm: str) -> Path:
    """Suffixed copy of the canonical matrix name under data/_labs/. Never the canonical
    path itself, and never data/ depth one, which ships to the webroot."""
    p = ed.matrix_path(side)
    return p.parent / LABS_DIR / f"{p.stem}__{arm}{p.suffix}"


def build_arm(side: str, arm: str):
    """(rows, acct) for one arm. Sets both flags for the duration and restores them."""
    win, imp = ARMS[arm]
    old = (ed.SERVICE_ALIGNED_WINDOW, em.NEUTRAL_MILB_IMPUTE)
    try:
        ed.SERVICE_ALIGNED_WINDOW = win
        em.NEUTRAL_MILB_IMPUTE = imp
        return ed.build_matrix(side)
    finally:
        ed.SERVICE_ALIGNED_WINDOW, em.NEUTRAL_MILB_IMPUTE = old


def _by_key(rows):
    return {(r["player_key"], r["kind"]): r for r in rows}


def _census_mean(rows, key: str):
    """Whole-matrix has-MiLB mean of one MiLB-block key. CENSUS ONLY (see the module
    docstring): a fold imputes at its own train mean, never at this one."""
    vals = []
    for r in rows:
        m = r.get("milb")
        if not m or r.get("milb_unavailable"):
            continue
        v = m.get(key)
        if v is not None:
            vals.append(float(v))
    return statistics.mean(vals) if vals else None


def census(rows, acct, side: str, arm: str, base_rows=None) -> dict:
    """Row counts, label movement against E0, window shifts and imputation reach."""
    win, imp = ARMS[arm]
    debuted = [r for r in rows if r["kind"] == "debuted"]
    unavail = [r for r in rows if r.get("milb_unavailable")]
    out = {
        "arm": arm, "side": side,
        "service_aligned_window": win, "neutral_milb_impute": imp,
        "rows": len(rows), "debuted": len(debuted),
        "busts": sum(1 for r in rows if r["kind"] == "bust"),
        # from the build's own accounting, so the count is the builder's, not a re-read
        "window_shifted": acct.get("debuted_window_shifted", 0),
        # A2 moves exactly the milb_unavailable rows, and only while its flag is on
        "imputation_changed": len(unavail) if imp else 0,
        "milb_unavailable_rows": len(unavail),
    }
    lr = _census_mean(rows, "level_rank")
    if imp and lr is not None:
        # the incumbent value for these rows is raw 0.0, so the mean IS the shift
        out["census_level_rank_has_milb_mean"] = round(lr, 3)
    if base_rows is None:
        out["vs_E0"] = "unavailable (this IS E0, or no E0 rows to compare)"
        return out
    base = _by_key(base_rows)
    moved, w_moved, only_in_arm = 0, 0, 0
    deltas, label_deltas = [], []
    for r in rows:
        b = base.get((r["player_key"], r["kind"]))
        if b is None:
            only_in_arm += 1
            continue
        d = float(r["target_censored"]) - float(b["target_censored"])
        deltas.append(d)
        if d:
            label_deltas.append(d)
        if any(r.get(k) != b.get(k) for k in _LABEL_KEYS):
            moved += 1
        if r.get("weight") != b.get("weight"):
            w_moved += 1
    out["rows_moved_vs_E0"] = moved
    out["label_moved_vs_E0"] = len(label_deltas)
    out["weight_moved_vs_E0"] = w_moved
    out["rows_only_in_arm"] = only_in_arm
    out["rows_only_in_E0"] = len(base) - (len(rows) - only_in_arm)
    out["mean_label_change"] = round(statistics.mean(deltas), 4) if deltas else 0.0
    out["mean_label_change_on_moved"] = (round(statistics.mean(label_deltas), 4)
                                         if label_deltas else 0.0)
    return out


def _print_census(c: dict) -> None:
    print(f"--- arm {c['arm']} ({c['side']}) "
          f"window={'service' if c['service_aligned_window'] else 'calendar'} "
          f"impute={'neutral' if c['neutral_milb_impute'] else 'floor'}")
    for k, v in c.items():
        if k in ("arm", "side", "service_aligned_window", "neutral_milb_impute"):
            continue
        print(f"    {k:32s} {v}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", required=True, choices=[*ARMS, "all"])
    ap.add_argument("--side", default="hit", choices=("hit", "pit"))
    ap.add_argument("--no-write", action="store_true",
                    help="census only; write no arm matrix")
    ap.add_argument("--verify-e0", action="store_true",
                    help="report whether the E0 rows reproduce the canonical matrix")
    a = ap.parse_args(argv)

    arms = list(ARMS) if a.arm == "all" else [a.arm]
    # every delta column is against E0, so E0 is built first whenever it is needed
    if "E0" not in arms:
        arms = ["E0", *arms]
    base_rows, rc = None, 0
    for arm in arms:
        rows, acct = build_arm(a.side, arm)
        if arm == "E0":
            base_rows = rows
            if a.verify_e0:
                p = ed.matrix_path(a.side)
                same = (p.exists()
                        and json.loads(p.read_text(encoding="utf-8")) == rows)
                print(f"verify-e0 {a.side}: E0 reproduces {p.name}: {same}")
                if not same:
                    rc = 1
        if not a.no_write:
            out = arm_path(a.side, arm)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
            print(f"wrote {out} ({len(rows)} rows)")
        _print_census(census(rows, acct, a.side, arm,
                             None if arm == "E0" else base_rows))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
