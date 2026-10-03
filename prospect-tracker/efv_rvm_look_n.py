# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The R-VM look sizes (EFV3_A6; docs/efv-v2/EFV_V2_GATE.md s2.2, PROGRAM.md s2.5).
COUNTS AND ARITHMETIC ONLY.

R-VM is the prospective vintage-matched frame: the 2025 debut cohort and later
(efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR), read at three group-sequential looks. Its
size at each look was written as "about 210" per cohort before anyone counted it. This
module counts it, per frame rule and per side, from data/debuts.json points alone:

    window      efv_vintage_frame.window_bounds(debut year, debut date): the debut
                year's preseason window, closed at the debut day.
    vm2 rule    every SCORED_SOURCES rater (FanGraphs and MLB Pipeline) published a
                grade at a point inside the window: the common-set rule
                source_backtest applies to the headline frame vm2. This is the
                CEILING of the vm2 look: vm2 also drops rows eFV cannot score and
                rows whose pinned read falls outside the window.
    consensus   a point inside the window carries a consensus grade (the
                consensus-present rule, frame version vm3 in LANE_A.md G2).

A grade is tested for PRESENCE only (`is not None`); no grade value is read, compared
or grouped, and no WAR, label, score or outcome is read. Whether a player was graded in
his debut year's preseason window is a fact fixed before that season's games, so the
count reads nothing the look will score. Side routing is efv_dataset._rec_is_pitcher,
the identity rule the frames use; a record it cannot route is counted as `unknown`.

The floor arithmetic is the gate's own tool, ported from the program synthesis probe
[S] (`scratchpad/efv2/S_program/probe_power_plan.py`, cited in PROGRAM.md s2.5): mde95
0.0303 at n 812 ([SB] head_to_head_verdict), scaled by sqrt(812 / n), and the
Lan-DeMets O'Brien-Fleming one-sided alpha 0.05 boundaries z 3.205 / 2.141 / 1.694 for
three equally spaced looks. delta_needed(n, z) = z x sd x sqrt(812 / n) with
sd = 0.0303 / 1.645. At n 210 it returns 0.0596 and 0.1161, the figures [S] printed.

Nothing here groups by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md).

Run:  python efv_rvm_look_n.py          (prints the counts and floors as JSON)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Callable, Iterable

import efv_dataset as D
import efv_vintage_frame as F
import source_backtest as SB

ROOT = Path(__file__).parent
DEBUTS = ROOT / "data" / "debuts.json"

#: The frame rules a look can be sized under (EFV_V2_GATE.md s2.2).
RULES: tuple[str, ...] = ("vm2", "consensus_present")
#: The rule the R-VM look uses: vm2, the headline frame (lane A E3-Q1, recommended
#: option taken by default 2026-10-02).
LOOK_RULE = "vm2"
SIDES: tuple[str, ...] = ("hit", "pit", "unknown")

#: The gate's tool constants ([S], PROGRAM.md s2.5): the reference floor and its n.
MDE_REF, N_REF, Z95 = 0.0303, 812, 1.645
#: Lan-DeMets O'Brien-Fleming, one-sided alpha 0.05, looks at 1/3, 2/3, 1 ([S]).
OBF_Z: tuple[float, float, float] = (3.205, 2.141, 1.694)


def _year(s) -> int | None:
    try:
        return int(str(s)[:4])
    except (TypeError, ValueError):
        return None


def _side(rec: dict, is_pitcher: Callable[[dict], bool | None]) -> str:
    p = is_pitcher(rec)
    return "unknown" if p is None else ("pit" if p else "hit")


def window_presence(rec: dict, year: int,
                    scored_sources: Iterable[str] = SB.SCORED_SOURCES) -> dict[str, bool]:
    """{rule: True when the record qualifies} for the `year` preseason window."""
    lo, hi = F.window_bounds(year, str(rec.get("debut_date") or "")[:10] or None)
    cons, srcs = False, set()
    for p in rec.get("points") or []:
        sd = str(p.get("snapshot_date") or "")[:10]
        if not (lo <= sd < hi):
            continue
        if p.get("consensus_fv") is not None:
            cons = True
        for s, ps in (p.get("per_source") or {}).items():
            if (ps or {}).get("fv_published") is not None:
                srcs.add(s)
    return {"vm2": set(scored_sources) <= srcs, "consensus_present": cons}


def cohort_counts(debuts: Iterable[dict], year: int, *,
                  scored_sources: Iterable[str] = SB.SCORED_SOURCES,
                  is_pitcher: Callable[[dict], bool | None] = D._rec_is_pitcher) -> dict:
    """Counts for one debut cohort: {'debuts': {side: n, 'total': n},
    rule: {side: n, 'total': n}}. Pure: reads each record's debut_date, its points'
    snapshot dates and grade presence, and the side routing fields."""
    srcs = tuple(scored_sources)
    out = {k: {s: 0 for s in SIDES} for k in ("debuts",) + RULES}
    for rec in debuts:
        if _year(rec.get("debut_date")) != int(year):
            continue
        side = _side(rec, is_pitcher)
        out["debuts"][side] += 1
        for rule, ok in window_presence(rec, int(year), srcs).items():
            out[rule][side] += int(ok)
    for v in out.values():
        v["total"] = sum(v[s] for s in SIDES)
    return out


def mde95(n: int) -> float:
    """The gate's tool: mde95 at n, sqrt-scaled from 0.0303 at 812."""
    return round(MDE_REF * math.sqrt(N_REF / int(n)), 4)


def delta_needed(n: int, z: float) -> float:
    """The gate's tool: the delta that clears boundary z at n."""
    return round(z * (MDE_REF / Z95) * math.sqrt(N_REF / int(n)), 4)


def look_sizes(debuts: list[dict], first: int = F.R_VM_FIRST_DEBUT_YEAR,
               looks: int = 3) -> dict:
    """Cumulative n per look and rule over the cohorts that exist in `debuts`
    (a cohort with no debuts yet contributes None, not 0)."""
    per = {first + i: cohort_counts(debuts, first + i) for i in range(looks)}
    out = {}
    for rule in RULES:
        cum, rows = 0, []
        for i in range(looks):
            c = per[first + i]
            if c["debuts"]["total"] == 0:
                rows.append(None)
                continue
            cum += c[rule]["total"]
            rows.append(cum)
        out[rule] = rows
    return {"cohorts": {str(k): v for k, v in per.items()}, "cumulative_n": out}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    debuts = json.loads(DEBUTS.read_text(encoding="utf-8"))
    sizes = look_sizes(debuts)
    look1 = sizes["cohorts"][str(F.R_VM_FIRST_DEBUT_YEAR)]
    floors = {rule: {"n": look1[rule]["total"], "mde95": mde95(look1[rule]["total"]),
                     "delta_needed_look1": delta_needed(look1[rule]["total"], OBF_Z[0])}
              for rule in RULES}
    print(json.dumps({"debuts_json_sha256": sha256(DEBUTS), "records": len(debuts),
                      "look_rule": LOOK_RULE, "sizes": sizes, "look1_floors": floors,
                      "obf_z": list(OBF_Z), "reserved_vm_pins": F.reserved_vm_pins()},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
