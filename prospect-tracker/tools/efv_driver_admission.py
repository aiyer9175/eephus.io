# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-06: the driver admission rule, run over every V2 candidate driver
(docs/efv-v2/DRIVER_SYSTEM_V2.md s4.1 principle 3, s5 DS-06).

THE RULE (lane I1, p4). For each training vintage (decision year), regress the target
percentile on [1, consensus percentile, z(driver)] and read the driver's t. A driver
enters a head only when at least two vintages give a t, every t has the same sign, and
the mean |t| is at least 1. One flipped sign refuses it. The rule lives in
efv_v2_model (admission_t, admission_check, admission_for_key) and runs inside every
V2 fit (fit_skill_head, fit_timing_head), so each fold admits on its own training years.

WHAT THIS TOOL WRITES. data/xfv_driver_admission.json: per candidate driver, the t and
the sign in every training vintage, the mean |t|, the verdict on the whole training
window (decision years before the reserved R-VM cohorts) and the verdict inside every
forward-chained fold (efv_model.SCORED_YEARS). tools/efv_arm_ledger.py reads it, so the
program's arm ledger carries each driver's per-vintage signs next to its gate, and each
driver checked here counts toward the program's probe total.

FRAME. The v1 training matrices (the vintage-matched debut-year reads), the only
labelled training cohorts the V2 heads fit on today. Skill drivers are read on has-block
rows only (DS-04). Timing drivers are read on REACHED over every row, no-block rows at
the has-block means; the block-absence flag is not a candidate here, because matrix ids
are not outcome-blind (DS-03). The pitcher K-rate candidate is read on the same matrices
for the record; DS-10 re-runs it on list vintages inside each fold
(tools/efv_v2_assemble.py). The pitcher BMI re-test (as of each row's own read, dated
FanGraphs board archives) is read here too. The PV-12 Pipeline-revision slot has no
matrix row (its first anchor is 2021-10-15 and the matrices carry no pre-grade
prediction), so it is checked on the list-vintage frame only.

Development only: it fits nothing that is served and scores no frame. It never reads a
decision year at or after efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR, and it groups nothing
by consensus-FV level (consensus enters as a within-year percentile).

Run:  python tools/efv_driver_admission.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as V1  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

OUT = ROOT / "data" / "xfv_driver_admission.json"


def candidates() -> list[tuple[str, str, str, str, bool]]:
    """(side, head, key, target, has_block_only) for every V2 candidate driver."""
    out = []
    for side in F.SIDES:
        skill = [k for k in H.skill_candidates(side) if k != H.V2_PL_REV_KEY]
        for k in skill:
            out.append((side, "skill", k, "u_y", True))
        for k in H.timing_keys(side):
            out.append((side, "timing", k, "reached", False))
    return out


def training(side: str) -> list[dict]:
    return [r for r in H.matrix_training_rows(side)
            if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]


def run() -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    data = {side: training(side) for side in F.SIDES}
    arms = {}
    for side, head, key, target, hb in candidates():
        rows = data[side]
        full = H.admission_for_key(rows, key, target=target, has_block_only=hb)
        by_fold = {}
        for yr in V1.SCORED_YEARS:
            tr = [r for r in rows if r["decision_year"] < yr]
            if not tr:
                continue
            chk = H.admission_for_key(tr, key, target=target, has_block_only=hb)
            by_fold[str(yr)] = {"admitted": chk["admitted"],
                                "n_valid_vintages": chk["n_valid_vintages"],
                                "reason": chk["reason"]}
        tag = f"DS-06:{side}.{head}.{key}"
        arms[tag] = {
            "tag": tag, "side": side, "head": head, "driver": key, "target": target,
            "rows": "has_block" if hb else "all (no-block rows at the has-block means)",
            "verdict": "ADMITTED" if full["admitted"] else "REFUSED",
            "per_vintage_signs": full["per_vintage_signs"],
            "t_by_vintage": full["t_by_vintage"],
            "vintages_without_t": full["vintages_without_t"],
            "mean_abs_t": full["mean_abs_t"], "n_valid_vintages": full["n_valid_vintages"],
            "admitted": full["admitted"], "reason": full["reason"],
            "by_fold": by_fold,
            "n_folds_admitted": sum(1 for v in by_fold.values() if v["admitted"]),
        }
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_driver_admission.py",
        "role": "development",
        "adjudicates": "which V2 candidate drivers the rule admits on the training cohorts",
        "rule": {"min_rows_per_vintage": H.ADMIT_MIN_ROWS,
                 "min_vintages": H.ADMIT_MIN_VINTAGES,
                 "min_mean_abs_t": H.ADMIT_MIN_MEAN_ABS_T,
                 "statistic": ("t of z(driver) in OLS target_pct ~ 1 + consensus_pct + "
                               "z(driver), one training vintage at a time"),
                 "admit": "one sign in every vintage with a t, and mean |t| >= 1",
                 "source": "lane I1 p4; DRIVER_SYSTEM_V2.md s4.1 principle 3"},
        "frame": ("v1 training matrices, decision years before "
                  f"{F.R_VM_FIRST_DEBUT_YEAR}; skill drivers on has-block rows, timing "
                  "drivers on every row"),
        "code": {"commit": commit},
        "scrapped": H.V2_SCRAPPED,
        "arms": arms,
        "n_arms": len(arms),
        "admitted": sorted(t for t, a in arms.items() if a["admitted"]),
        "refused": sorted(t for t, a in arms.items() if not a["admitted"]),
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    doc = run()
    for tag, a in doc["arms"].items():
        print(f"{a['verdict']:9s} {tag:40s} signs {a['per_vintage_signs']} "
              f"mean|t| {a['mean_abs_t']}  folds admitted {a['n_folds_admitted']}")
    if "--dry-run" not in argv:
        OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
