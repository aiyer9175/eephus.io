# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV training through the 2026 season: the fold matrices and the receipt
(docs/efv-v2/EFV_2026_TRAINING.md, task EFV_2026_FOLD_TRAINING, owner EW3-13).

The registration was committed alone before this module existed. This module does two
things and reads no rater score:

    --build    writes the TRAINING-ONLY fold matrices
               (efv_vintage_frame.fold_matrix_path): efv_dataset.build_matrix with
               DEBUT_YEARS widened to 2011 through TRAIN_THROUGH_SEASON, every other rule
               unchanged. It refuses to write unless every row the build shares with the
               served matrix is identical to the served row, no served row is missing, and
               every added row is a debuted row of a cohort the served bound leaves out.
               The served matrices are never written.
    --report   writes data/_labs/efv2026/efv_2026_fold_training.json: the training pool by
               decision year with the flag off and on, the rows gained per side, and the
               minimum detectable effect of the forward-chained development read rescaled
               by the sqrt rule on the pair-weight mass (registration s5). Counts and
               arithmetic only; nothing is fitted or scored.

The flag efv_vintage_frame.EFV_TRAIN_THROUGH_2026 stays False here; the report turns it on
only inside flag_on() and restores it.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only groups are side, decision year and
row kind. Nothing here groups, counts or averages rows by consensus-FV level;
test_efv_2026_fold.py scans this source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import efv_dataset as D
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
LAB_DIR = ROOT / "data" / "_labs" / "efv2026"
REPORT_PATH = LAB_DIR / "efv_2026_fold_training.json"
MDE_FLOOR_PATH = ROOT / "data" / "xfv_mde_floor.json"
DOC = F.TRAINING_DOC
#: The forward-chained development read's first scored year (efv_model.SCORED_YEARS[0]).
DEV_FIRST_YEAR = 2014


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode().strip() if r.returncode == 0 else None


def _canon(row: dict) -> str:
    return json.dumps(row, sort_keys=True)


# ---------------------------------------------------------------------------
# the fold matrices
# ---------------------------------------------------------------------------

def build_fold(side: str, *, served: list[dict] | None = None,
               builder=None) -> tuple[list[dict], dict]:
    """(rows, receipt) for the side's fold matrix. `builder` (tests) stands in for
    efv_dataset.build_matrix; it is called with DEBUT_YEARS widened. Raises ValueError when
    the build disagrees with the served matrix on any shared row."""
    served = (json.loads(D.matrix_path(side).read_text(encoding="utf-8"))
              if served is None else served)
    builder = D.build_matrix if builder is None else builder
    old = D.DEBUT_YEARS
    D.DEBUT_YEARS = tuple(range(old[0], int(F.TRAIN_THROUGH_SEASON) + 1))
    try:
        rows, _acct = builder(side)
    finally:
        D.DEBUT_YEARS = old
    by_served = {r["player_key"]: r for r in served}
    keys = [r["player_key"] for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{side}: the widened build repeats a player_key")
    built = set(keys)
    missing = sorted(k for k in by_served if k not in built)
    changed = sorted(r["player_key"] for r in rows
                     if r["player_key"] in by_served
                     and _canon(r) != _canon(by_served[r["player_key"]]))
    added = [r for r in rows if r["player_key"] not in by_served]
    stray = sorted(r["player_key"] for r in added
                   if r.get("kind") != "debuted"
                   or int(r.get("debut_year") or 0) <= old[-1]
                   or int(r.get("debut_year") or 0) > int(F.TRAIN_THROUGH_SEASON))
    if missing or changed or stray:
        raise ValueError(f"{side}: the widened build disagrees with the served matrix "
                         f"(missing {missing[:5]} of {len(missing)}, changed {changed[:5]} of "
                         f"{len(changed)}, stray additions {stray[:5]} of {len(stray)}); "
                         f"rebuild the served matrix first (python efv_dataset.py)")
    by_year: dict[str, int] = {}
    for r in added:
        y = str(int(r["debut_year"]))
        by_year[y] = by_year.get(y, 0) + 1
    receipt = {"served_rows": len(served), "fold_rows": len(rows), "added_rows": len(added),
               "added_by_debut_year": dict(sorted(by_year.items())),
               "shared_rows_identical": True,
               "served_debut_years": [old[0], old[-1]],
               "fold_debut_years": [old[0], int(F.TRAIN_THROUGH_SEASON)]}
    return rows, receipt


def write_fold(log=print) -> dict:
    """Build and write both fold matrices; {side: receipt with path and sha256}."""
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for side in F.SIDES:
        rows, rec = build_fold(side)
        p = F.fold_matrix_path(side)
        p.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        rec.update({"path": p.relative_to(ROOT).as_posix(), "sha256": _sha(p),
                    "served_sha256": _sha(D.matrix_path(side))})
        out[side] = rec
        log(f"  fold matrix {side}: {rec}")
    return out


# ---------------------------------------------------------------------------
# the report: rows gained and the minimum detectable effect
# ---------------------------------------------------------------------------

@contextmanager
def flag_on():
    """EFV_TRAIN_THROUGH_2026 on for the block, restored after."""
    old = F.EFV_TRAIN_THROUGH_2026
    F.EFV_TRAIN_THROUGH_2026 = True
    try:
        yield
    finally:
        F.EFV_TRAIN_THROUGH_2026 = old


def pool_counts(side: str) -> dict:
    """The production training pool of the side under the current flag:
    {"end": first excluded year, "n": rows, "by_year": {year: {kind: n}},
     "keys": set of (year, player_key)}."""
    import efv_v2_model as H
    end = F.train_end_year()
    rows = [r for r in H.training_rows(side) if int(r["decision_year"]) < end]
    by: dict[str, dict[str, int]] = {}
    for r in rows:
        b = by.setdefault(str(int(r["decision_year"])), {})
        b[r["kind"]] = b.get(r["kind"], 0) + 1
    return {"end": end, "n": len(rows), "by_year": dict(sorted(by.items())),
            "keys": {(int(r["decision_year"]), r["player_key"]) for r in rows}}


def dev_mass(rows: list[dict], first: int, last: int) -> dict:
    """Debuted rows with decision (debut) year in [first, last] and their pair-weight mass
    (sum of observed_seasons / 6, the floor's row weight)."""
    sel = [r for r in rows if r.get("kind") == "debuted"
           and first <= int(r["debut_year"]) <= last]
    w = sum(float(r.get("observed_seasons") or 0) / float(D.TARGET_SEASONS) for r in sel)
    return {"years": [first, last], "n": len(sel), "w": round(w, 3)}


def mde_rescale(floor: dict, before: dict, after: dict) -> dict:
    """The published weighted floor rescaled by sqrt(W_before / W_after) (mass version) and
    sqrt(n_before / n_after) (row-count version)."""
    out = {}
    for k in ("mde95", "mde95_onesided"):
        b = float(floor[k])
        out[k] = {"before": b,
                  "after_mass": round(b * math.sqrt(before["w"] / after["w"]), 4),
                  "after_rows": round(b * math.sqrt(before["n"] / after["n"]), 4)}
    out["ratio_mass"] = round(after["w"] / before["w"], 4)
    out["ratio_rows"] = round(after["n"] / before["n"], 4)
    return out


def report(log=print) -> dict:
    floor = json.loads(MDE_FLOOR_PATH.read_text(encoding="utf-8"))
    sides = {}
    for side in F.SIDES:
        off = pool_counts(side)
        with flag_on():
            on = pool_counts(side)
            fold_rows = json.loads(F.training_matrix_path(side).read_text(encoding="utf-8"))
        served_rows = json.loads(D.matrix_path(side).read_text(encoding="utf-8"))
        gained = on["keys"] - off["keys"]
        lost = off["keys"] - on["keys"]
        g_by: dict[str, int] = {}
        for y, _k in gained:
            g_by[str(y)] = g_by.get(str(y), 0) + 1
        before = dev_mass(served_rows, DEV_FIRST_YEAR, int(F.R_VM_FIRST_DEBUT_YEAR) - 1)
        after = dev_mass(fold_rows, DEV_FIRST_YEAR, int(F.TRAIN_THROUGH_SEASON))
        sides[side] = {
            "pool_flag_off": {k: v for k, v in off.items() if k != "keys"},
            "pool_flag_on": {k: v for k, v in on.items() if k != "keys"},
            "rows_gained": len(gained), "rows_gained_by_year": dict(sorted(g_by.items())),
            "rows_lost": len(lost),
            "max_decision_year_on": max(y for y, _k in on["keys"]),
            "dev_read_before": before, "dev_read_after": after,
            "mde": mde_rescale(floor["weighted"][side], before, after),
        }
        log(f"  {side}: +{len(gained)} rows {sides[side]['rows_gained_by_year']}, "
            f"mde {sides[side]['mde']}")
    ok, why = F.label_window_closed(F.TRAIN_THROUGH_SEASON)
    doc = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        .replace("+00:00", "Z"),
        "produced_by": "efv_2026_fold.py --report",
        "registration": DOC,
        "role": "development",
        "adjudicates": "nothing; counts and arithmetic on a published sd, no rater scored",
        "flag": {"name": "efv_vintage_frame.EFV_TRAIN_THROUGH_2026",
                 "served_value": bool(F.EFV_TRAIN_THROUGH_2026),
                 "train_through_season": int(F.TRAIN_THROUGH_SEASON),
                 "train_end_year_off": F.train_end_year(flag=False),
                 "train_end_year_on": F.train_end_year(flag=True)},
        "label_window": {"season": int(F.TRAIN_THROUGH_SEASON), "closed": ok, "reason": why,
                         "resolved_through": int(D.RESOLVED_THROUGH)},
        "guards": {"r_vm_first_debut_year": int(F.R_VM_FIRST_DEBUT_YEAR),
                   "reserved_lv": sorted(F.RESERVED_LV),
                   "reserved_vm_pins": F.reserved_vm_pins(),
                   "anchor_gate": "nothing grouped by consensus-FV level "
                                  "(docs/PROSPECT_ANCHOR_GATE.md)"},
        "mde_basis": {"path": "data/xfv_mde_floor.json", "sha256": _sha(MDE_FLOOR_PATH),
                      "generated_at": floor.get("generated_at"), "weighting": "weighted",
                      "rule": "mde95_after = mde95_before x sqrt(W_before / W_after) "
                              "(PROGRAM.md s2.5, LABEL_HORIZON_2026.md s3); row-count "
                              "version sqrt(n_before / n_after)",
                      "note": "arithmetic on a published sd, not a measured floor; the "
                              "opened rows serve development selection only and are never "
                              "a claim frame"},
        "sides": sides,
        "code": {"commit": _git_commit(), "tool_sha256": _sha(Path(__file__))},
    }
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    log(f"wrote {REPORT_PATH.relative_to(ROOT).as_posix()}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", action="store_true", help="write the fold matrices")
    ap.add_argument("--report", action="store_true", help="write the receipt")
    a = ap.parse_args(argv)
    if not (a.build or a.report):
        ap.error("name --build and/or --report")
    if a.build:
        write_fold()
    if a.report:
        report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
