# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV pick family: the draft-pick column for the screening lab (EFV3_B4;
SP/efv3/EFV3_PLAN.md s4, LANE_B.md F-B7 and the D1 rule in s3).

WHAT THIS BUILDS. For every F-LV row (efv_vintage_frame.build_frame) the overall draft
pick that was KNOWN at the row's list vintage V, and from it one column per side for
the screening lab's timing head:

    pick_overall_time_<side>   log1p(pick), the D-1 bonus_log transform, on the rows
                               with a pick known at V; None (pick_missing 1.0) elsewhere

The column is a NAMED RE-TEST of the closed F-VM arm D-1:pick_overall (data/
xfv_arm_ledger.json: hit -0.00171 against a floor of 0.0194, pit -0.00759 against
0.0172, neither cleared) on a frame it was never read on (lv_dev, list vintages),
counted under its own name in the lab's family. TIMING HEAD ONLY: DRIVER_SYSTEM_V2 D4
keeps pick and bonus out of every rank feature (docs/efv-v2/PROGRAM.md D4, "pick and
bonus stay CLOSED as rank features (D-1 null) and enter only the PA/IP head"). The
column is handed to the lab's candidate list (tools/efv_screen_lab.py) and to nothing
else: no served number, no ledger row, no progress row.

THE JOIN (LANE_B s3, D1). The pick is read from .cache/draft_history/<year>.json
({pick, mlbam, name}; the 2005 to 2018 classes on disk, never fetched) on the row's
OUTCOME-BLIND id `mlbam_id` (the efv_identity resolution the frame keys every input
on; the record's stored id is audit only and is never read here), taking the LATEST
draft year STRICTLY BELOW V: a July pick in year V is after the window and never joins
a V row, and a player drafted twice (unsigned, then re-drafted) carries the pick he
signed on. When no draft_history pick is known at V the acquisitions sidecar's
pick_overall stands in, only when the frame marked it acq_known_at_v (its acquisition
year is below V); otherwise the row is missing with pick_missing 1.0. The missingness
indicator goes through the DS-03 balance probe (tools/efv_pick_balance.py, and the lab
on every run); the coverage receipt is by (side, vintage) and nothing finer.

BANS. No bonus column (there is no pre-2017 bonus source); no seasons_at_level on
either side (owner DS-Q2); no reserved list vintage (2020 and 2021 raise through
efv_vintage_frame's guard) and no 2025 or later debut cohort (the lab and the probe
tool drop them; this module reads no debut). This module reads no WAR, debut, label or
major league column: the labels the lab and the probe tool join never pass through it.
Nothing groups, counts or averages rows by consensus-FV level
(docs/PROSPECT_ANCHOR_GATE.md); the only summary is a count by (side, vintage).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import efv_vintage_frame as F

ROOT = Path(__file__).parent
#: The draft classes on disk: {pick, mlbam, name} per overall pick, one file a year.
DRAFT_DIR = ROOT / ".cache" / "draft_history"
#: The transform the column carries (the D-1 bonus_log transform).
TRANSFORM = "log1p"
#: The missingness indicator the DS-03 probe reads.
INDICATOR = "pick_missing"
#: Where a row's pick came from.
SOURCE_DRAFT = "draft_history"
SOURCE_SIDECAR = "sidecar"
#: The head the column is offered to, per DRIVER_SYSTEM_V2 D4. Never "skill".
HEAD = "timing"
#: The closed F-VM arm this column re-tests (data/xfv_arm_ledger.json, lane D-1).
RETEST_OF = "D-1:pick_overall"


def column_name(side: str) -> str:
    if side not in F.SIDES:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    return f"pick_overall_time_{side}"


# ---------------------------------------------------------------------------
# the draft classes
# ---------------------------------------------------------------------------

def draft_years_on_disk(draft_dir: Path | str | None = None) -> list[int]:
    """The draft years with a file in `draft_dir` (DRAFT_DIR when None, read at call
    time), ascending. [] when absent."""
    d = Path(DRAFT_DIR if draft_dir is None else draft_dir)
    if not d.is_dir():
        return []
    return sorted(int(p.stem[:4]) for p in d.glob("*.json") if p.stem[:4].isdigit())


def load_draft_picks(draft_dir: Path | str | None = None) -> dict[int, dict[int, int]]:
    """{mlbam: {draft year: overall pick}} off the on-disk files only (DRAFT_DIR when
    None, read at call time); never a fetch. A row without an id or a pick is skipped;
    a same-year duplicate keeps the lower pick (the one he was taken at)."""
    out: dict[int, dict[int, int]] = {}
    d = Path(DRAFT_DIR if draft_dir is None else draft_dir)
    for year in draft_years_on_disk(d):
        try:
            picks = json.loads((d / f"{year}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for x in picks or []:
            pid, pick = x.get("mlbam"), x.get("pick")
            if pid is None or pick is None:
                continue
            try:
                pid, pick = int(pid), int(pick)
            except (TypeError, ValueError):
                continue
            by = out.setdefault(pid, {})
            if year not in by or pick < by[year]:
                by[year] = pick
    return out


def pick_at_vintage(person_id, vintage: int, picks: dict[int, dict[int, int]]
                    ) -> tuple[int | None, int | None]:
    """(pick, draft year) for the LATEST draft year strictly below V on the id, or
    (None, None). A pick in year V or later is not known at the V read."""
    V = int(vintage)
    if person_id is None:
        return None, None
    try:
        pid = int(person_id)
    except (TypeError, ValueError):
        return None, None
    years = [y for y in (picks.get(pid) or {}) if int(y) < V]
    if not years:
        return None, None
    y = max(years)
    return int(picks[pid][y]), int(y)


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------

def pick_for_row(row: dict, picks: dict[int, dict[int, int]]) -> dict:
    """The pick fields for one F-LV row:

        pick_overall_at_v   the overall pick known at V, or None
        pick_draft_year     the draft year it was taken in (below V), or None
        pick_source         "draft_history", "sidecar" or None
        pick_missing        1.0 when no pick is known at V, else 0.0
        pick_log1p          log1p(pick), the column's value, or None
        pick_sidecar_agrees True / False when both sources carry a pick, else None

    The join is on the row's outcome-blind id (`mlbam_id`); the sidecar pick is read
    only when the frame marked the acquisition known at V (its year below V)."""
    V = int(row["vintage"])
    F.guard_score_request(V, purpose="pick")
    pick, year = pick_at_vintage(row.get("mlbam_id"), V, picks)
    source = SOURCE_DRAFT if pick is not None else None
    sidecar = None
    ay = row.get("acq_year")
    if row.get("acq_known_at_v") and (ay is None or int(ay) < V):
        sc = row.get("pick_overall")
        if sc is not None:
            try:
                sidecar = int(sc)
            except (TypeError, ValueError):
                sidecar = None
    if pick is None and sidecar is not None:
        pick, year, source = sidecar, (int(ay) if ay is not None else None), SOURCE_SIDECAR
    return {"pick_overall_at_v": pick, "pick_draft_year": year, "pick_source": source,
            INDICATOR: 1.0 if pick is None else 0.0,
            "pick_log1p": None if pick is None else math.log1p(float(pick)),
            "pick_sidecar_agrees": (None if (source != SOURCE_DRAFT or sidecar is None)
                                    else bool(sidecar == pick))}


def attach_pick(rows: list[dict], picks: dict[int, dict[int, int]] | None = None
                ) -> list[dict]:
    """Each F-LV row with its pick fields attached, as new dicts. Reserved vintages
    raise before any read."""
    picks = load_draft_picks() if picks is None else picks
    out = []
    for r in rows:
        F.guard_score_request(int(r["vintage"]), purpose="pick")
        out.append(dict(r, **pick_for_row(r, picks)))
    return out


def screen_column(side: str, frames: dict, *, picks: dict | None = None) -> dict:
    """The lab's column: {(V, player_key): log1p(pick) | None} over the side's frames
    ({side: {V: (rows, ...)}}, the efv_v2_assemble.build_frames shape). Only the rows
    are read; whatever else a frame tuple carries is never touched here."""
    if side not in F.SIDES:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    picks = load_draft_picks() if picks is None else picks
    out: dict = {}
    for V, entry in sorted((frames.get(side) or {}).items()):
        V = int(V)
        F.guard_score_request(V, purpose="pick column")
        rows = entry[0] if isinstance(entry, (tuple, list)) else entry
        for r in rows:
            out[(V, r["player_key"])] = pick_for_row(r, picks)["pick_log1p"]
    return out


# ---------------------------------------------------------------------------
# the coverage receipt
# ---------------------------------------------------------------------------

def coverage_receipt(rows_by_side: dict[str, dict[int, list[dict]]],
                     draft_dir: Path | str | None = None) -> dict:
    """Counts by (side, vintage) and nothing else: rows, rows with a resolved id, rows
    joining a draft_history pick dated before V, rows whose pick came from the sidecar
    alone, rows the sidecar knows a pick for, rows with any pick, rows missing, the
    draft-year distribution of the joined picks, the latest draft year joined (always
    below V), the median pick, and the agreement of the two sources where both carry
    a pick."""
    draft_dir = Path(DRAFT_DIR if draft_dir is None else draft_dir)
    years = draft_years_on_disk(draft_dir)
    try:
        where = draft_dir.relative_to(ROOT).as_posix()
    except ValueError:
        try:
            where = draft_dir.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            where = draft_dir.name
    out: dict = {"by_side_vintage": {}, "transform": TRANSFORM, "head": HEAD,
                 "retest_of": RETEST_OF, "indicator": INDICATOR,
                 "draft_files": {"dir": where, "years": years,
                                 "first": years[0] if years else None,
                                 "last": years[-1] if years else None}}
    for side, by_v in rows_by_side.items():
        for V, rows in sorted(by_v.items()):
            V = int(V)
            joined = [r for r in rows if r.get("pick_source") == SOURCE_DRAFT]
            yrs: dict[str, int] = {}
            for r in joined:
                y = str(r["pick_draft_year"])
                yrs[y] = yrs.get(y, 0) + 1
            pk = sorted(r["pick_overall_at_v"] for r in rows if not r[INDICATOR])
            both = [r for r in joined if r.get("pick_sidecar_agrees") is not None]
            blk = {"rows": len(rows),
                   "id_resolved": sum(1 for r in rows if r.get("mlbam_id") is not None),
                   "draft_history_pre_v": len(joined),
                   "sidecar_only": sum(1 for r in rows if r.get("pick_source") == SOURCE_SIDECAR),
                   "sidecar_known": sum(1 for r in rows if r.get("acq_known_at_v")
                                        and r.get("pick_overall") is not None),
                   "with_pick": len(pk),
                   "missing": sum(1 for r in rows if r[INDICATOR]),
                   "draft_years": dict(sorted(yrs.items())),
                   "max_draft_year": (max(int(y) for y in yrs) if yrs else None),
                   "median_pick": (pk[len(pk) // 2] if pk else None),
                   "sidecar_both": len(both),
                   "sidecar_agrees": sum(1 for r in both if r["pick_sidecar_agrees"]),
                   "sidecar_disagrees": sum(1 for r in both if not r["pick_sidecar_agrees"])}
            if blk["max_draft_year"] is not None and blk["max_draft_year"] >= V:
                raise ValueError(f"a pick dated at or after V joined a {side} {V} row")
            out["by_side_vintage"][f"{side}:{V}"] = blk
    return out
