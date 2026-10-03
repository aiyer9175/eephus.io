# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV scoreboard strata: the ONLY module that defines a matrix dimension.

EFV3_D1 (SP/efv3/EFV3_PLAN.md section 6; SP/efv3/LANE_D.md 3.1 and 3.5). The
scoreboard matrix (FRAME x CELL x COMPARATOR x STATISTIC) reads its cells from here
and nowhere else. Every dimension is a function of facts known at the read and of
NO grade level: a row's side, its listed position, the level it played at in the
season before the list, its age at the list year, the list year, how the player
was acquired, and whether the two scored sources disagreed by ten FV or more.

Pure functions. The module imports nothing from the repository (no label module,
no WAR source, no frame builder) and reads no outcome key: the AST test in
test_efv_strata.py pins that no function reads a key matching
(war|target|consensus_fv|fv_|grade|rank|tier|bust|reached|debut_year) except
`source_disagreement`, which reads exactly grades["fangraphs"] and
grades["mlb_pipeline"] and compares their absolute difference with
DISAGREEMENT_GAP_FV. The one grade-derived dimension is a DIFFERENCE of two
sources, never a level, and the page discloses it as grade-derived.

Rows. `assign(frame_id, row, record)` takes the matrix's own row for the frame and
the universe record behind it:

  vm frames (vm2, vm_pros, bust_inclusive): `row` is source_backtest's common row
    (`year` is the base year, the preseason read of the debut year; `grades`; the
    precomputed `archetype` from source_backtest._archetype) plus, when the producer
    attaches them, `side` and the eFV matrix row's outcome-blind `milb` block;
    `record` supplies position and birth date.
  lv frames (lv_dev, lv_res): `row` is an efv_vintage_frame row (`vintage`, `side`,
    `position`, `birth_date`, `milb`, `grades`, `is_college`, `is_ifa`,
    `acq_known_at_v`); `record` is optional.

Level at list is the V-1 level from the outcome-blind MiLB block: the block's
`milb_level` when its `milb_season` precedes the base year, otherwise "none" (the
lv block is built with cutoff V-01-01, so its season always precedes V; on vm the
matrix row's block can run into the debut season and is then not a fact known at
the read).

Reserved frames (R-LV list vintages 2020 and 2021; R-VM debut cohorts 2025 and
later) are never built or read here: this module builds nothing and reads no file.
Every frame builder calls efv_vintage_frame.guard_score_request itself.
"""
from __future__ import annotations

#: The matrix dimensions, in page order. Adding one is a registration, not an edit.
DIMENSIONS: tuple[str, ...] = ("side", "position_family", "level_at_list", "age_band",
                               "list_year", "archetype", "source_disagreement")

#: What may never become a dimension (docs/PROSPECT_ANCHOR_GATE.md; LANE_D.md 3.5).
BANNED_DIMENSIONS: tuple[str, ...] = (
    "consensus FV", "eFV grade", "any rater's FV", "tier", "top-N rank",
    "bonus band expressed through FV", "debuted", "reached", "label status")

#: The one sentence under which an FV-tier dimension could ever be added.
AMENDMENT_RULE = (
    "An FV-tier dimension may be added only by a dated amendment citing the anchor "
    "look record (docs/PROSPECT_ANCHOR_GATE.md section 18), after the later of "
    "2026-11-20 and 14 days after the fWAR epoch's step Z entry.")

#: The value an assigner returns when the fact is not known at the read.
UNKNOWN = "unknown"

#: List years the program can ever read (the first development vintage onward).
FIRST_LIST_YEAR = 2011
LAST_LIST_YEAR = 2040

#: The declared cells per dimension. An assigner returns one of these or UNKNOWN;
#: age_band lists "unknown" because it is a scored cell there (LANE_D.md F4).
CELLS: dict[str, tuple[str, ...]] = {
    "side": ("hit", "pit"),
    "position_family": ("C", "IF", "OF"),
    "level_at_list": ("AAA", "AA", "A+", "A", "CPX", "DSL", "none"),
    "age_band": ("<=18", "19-20", "21-22", "23-24", ">=25", UNKNOWN),
    "list_year": tuple(str(y) for y in range(FIRST_LIST_YEAR, LAST_LIST_YEAR + 1)),
    "archetype": ("hs_bat", "hs_arm", "college_bat", "college_arm", "intl_bat",
                  "intl_arm", "unknown_bat", "unknown_arm"),
    "source_disagreement": ("gap_10_plus", "gap_under_10"),
}

#: Dimensions defined on one side only: position family is a hitter dimension
#: (LANE_D.md F5: the pitcher position cell is the pitcher side cell). `assign`
#: leaves such a dimension out of a row on the other side.
DIMENSION_SIDE: dict[str, str] = {"position_family": "hit"}

#: Dimensions the page must disclose as derived from grades (a difference, not a level).
DISCLOSED_DIMENSIONS: tuple[str, ...] = ("source_disagreement",)

#: The FV gap at or above which the two scored sources count as disagreeing.
DISAGREEMENT_GAP_FV = 10

#: Frame id -> row convention (see the module docstring).
FRAME_KIND: dict[str, str] = {"vm2": "vm", "vm_pros": "vm", "bust_inclusive": "vm",
                              "lv_dev": "lv", "lv_res": "lv"}

_PITCH_POS = frozenset({"P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP", "CP", "CL"})
_TWO_WAY_POS = frozenset({"TWP"})
_IF_POS = frozenset({"1B", "2B", "3B", "SS", "IF", "INF", "UT", "UTIL", "DH", "MI", "CI"})
_OF_POS = frozenset({"OF", "LF", "CF", "RF"})
_LEVEL_SYNONYMS = {"ROK": "CPX", "RK": "CPX", "R": "CPX", "HIGH-A": "A+", "LOW-A": "A"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _first(row, record, key):
    """The row's value for `key`, else the record's, else None."""
    v = (row or {}).get(key)
    if v is None:
        v = (record or {}).get(key)
    return v


def _pos_token(row, record) -> str:
    return str(_first(row, record, "position") or "").upper().split("/")[0].strip()


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _year_of(v):
    """The four-digit year at the head of a date or year string, else None."""
    s = str(v or "")[:4]
    return int(s) if s.isdigit() else None


def base_year(frame_id: str, row: dict):
    """The year the row was read at: `vintage` on lv frames, `year` on vm frames."""
    kind = frame_kind(frame_id)
    return _int_or_none((row or {}).get("vintage" if kind == "lv" else "year"))


def frame_kind(frame_id: str) -> str:
    try:
        return FRAME_KIND[frame_id]
    except KeyError:
        raise ValueError(f"unknown frame id {frame_id!r}; known: {sorted(FRAME_KIND)}") from None


# ---------------------------------------------------------------------------
# assigners (one per dimension; each returns a declared cell or UNKNOWN)
# ---------------------------------------------------------------------------

def side(row: dict, record: dict | None = None) -> str:
    """hit or pit: the frame's side when the row carries it, else by position."""
    s = (row or {}).get("side")
    if s in CELLS["side"]:
        return s
    pos = _pos_token(row, record)
    if not pos or pos in _TWO_WAY_POS:
        return UNKNOWN
    if pos in _PITCH_POS:
        return "pit"
    if pos in _IF_POS or pos in _OF_POS or pos == "C":
        return "hit"
    return UNKNOWN


def position_family(row: dict, record: dict | None = None) -> str:
    """C, IF or OF from the listed position (a hitter dimension; see DIMENSION_SIDE)."""
    pos = _pos_token(row, record)
    if pos == "C":
        return "C"
    if pos in _IF_POS:
        return "IF"
    if pos in _OF_POS:
        return "OF"
    return UNKNOWN


def level_at_list(row: dict, year) -> str:
    """The V-1 level from the outcome-blind MiLB block, "none" without one."""
    block = (row or {}).get("milb")
    if not isinstance(block, dict):
        return "none"
    season = _int_or_none(block.get("milb_season"))
    y = _int_or_none(year)
    if season is None or y is None or season >= y:
        return "none"
    raw = str(block.get("milb_level") or "").upper().strip()
    if not raw:
        return "none"
    raw = _LEVEL_SYNONYMS.get(raw, raw)
    return raw if raw in CELLS["level_at_list"] else UNKNOWN


def age_band(row: dict, record: dict | None, year) -> str:
    """Base year minus birth year, banded; "unknown" without a birth date."""
    by = _year_of(_first(row, record, "birth_date"))
    y = _int_or_none(year)
    if by is None or y is None:
        return UNKNOWN
    age = y - by
    if age <= 18:
        return "<=18"
    if age <= 20:
        return "19-20"
    if age <= 22:
        return "21-22"
    if age <= 24:
        return "23-24"
    return ">=25"


def list_year(year) -> str:
    y = _int_or_none(year)
    if y is None or not (FIRST_LIST_YEAR <= y <= LAST_LIST_YEAR):
        return UNKNOWN
    return str(y)


def vm_archetype(record: dict | None) -> str | None:
    """source_backtest._archetype, restated here so the module imports nothing: the
    acquisition method and the draft-year age split a record into hs, college or
    intl by bat or arm; None when the method or the age is not known."""
    rec = record or {}
    pos = str(rec.get("position") or "").upper().split("/")[0]
    if pos in _TWO_WAY_POS:
        return None
    arm_or_bat = "arm" if pos in _PITCH_POS else "bat"
    acq = rec.get("acquisition") or {}
    method = acq.get("method")
    if method == "international_fa":
        origin = "intl"
    elif method == "draft":
        by, yr = str(rec.get("birth_date") or "")[:4], acq.get("year")
        if not (by.isdigit() and yr):
            return None
        origin = "hs" if (int(yr) - int(by)) <= 19 else "college"
    else:
        return None
    return f"{origin}_{arm_or_bat}"


def archetype(frame_id: str, row: dict, record: dict | None = None,
              row_side: str | None = None) -> str:
    """hs, college or intl by bat or arm; unknown_bat or unknown_arm when the
    acquisition is not known at the read. vm rows carry source_backtest's own
    archetype (or it is restated from the record); lv rows use the sidecar flags
    is_college, is_ifa and acq_known_at_v."""
    kind = frame_kind(frame_id)
    s = row_side if row_side in CELLS["side"] else side(row, record)
    suffix = "arm" if s == "pit" else "bat"
    if kind == "vm":
        if "archetype" in (row or {}):
            a = (row or {}).get("archetype")
        else:
            a = vm_archetype(record)
        return a if a in CELLS["archetype"] else f"unknown_{suffix}"
    r = row or {}
    if r.get("is_college"):
        origin = "college"
    elif r.get("is_ifa"):
        origin = "intl"
    elif r.get("acq_known_at_v"):
        origin = "hs"
    else:
        origin = UNKNOWN
    return f"{origin}_{suffix}"


def source_disagreement(row: dict) -> str:
    """gap_10_plus when the two scored sources differ by DISAGREEMENT_GAP_FV or more,
    gap_under_10 when they differ by less, unknown when either did not grade the
    row. The only function here that reads a grade, and it reads exactly two."""
    grades = (row or {}).get("grades") or {}
    fg, mp = grades.get("fangraphs"), grades.get("mlb_pipeline")
    try:
        gap = abs(float(fg) - float(mp))
    except (TypeError, ValueError):
        return UNKNOWN
    if gap != gap:                       # NaN on either side
        return UNKNOWN
    return "gap_10_plus" if gap >= DISAGREEMENT_GAP_FV else "gap_under_10"


# ---------------------------------------------------------------------------
# the row assignment
# ---------------------------------------------------------------------------

def assign(frame_id: str, row: dict, record: dict | None = None) -> dict[str, str]:
    """{dimension: cell} for one row. A dimension defined on one side only
    (DIMENSION_SIDE) is left out of a row on the other side."""
    year = base_year(frame_id, row)
    s = side(row, record)
    out = {"side": s}
    if DIMENSION_SIDE["position_family"] == s:
        out["position_family"] = position_family(row, record)
    out["level_at_list"] = level_at_list(row, year)
    out["age_band"] = age_band(row, record, year)
    out["list_year"] = list_year(year)
    out["archetype"] = archetype(frame_id, row, record, s)
    out["source_disagreement"] = source_disagreement(row)
    return out


def applies(dimension: str, row_side: str) -> bool:
    """Whether `dimension` is defined for a row on `row_side`."""
    want = DIMENSION_SIDE.get(dimension)
    return want is None or want == row_side


def is_cell(dimension: str, value) -> bool:
    """True when `value` is one of the dimension's declared cells or UNKNOWN."""
    return value == UNKNOWN or value in CELLS[dimension]


def count_cells(frame_id: str, rows, records=None) -> dict[str, dict[str, dict[str, int]]]:
    """{dimension: {cell: {"all": n, "hit": n, "pit": n}}}: counts only, no
    statistic, no grade read beyond source_disagreement's two."""
    out: dict[str, dict[str, dict[str, int]]] = {d: {} for d in DIMENSIONS}
    for i, row in enumerate(rows):
        rec = None
        if records is not None:
            rec = records[i] if isinstance(records, (list, tuple)) else records.get(
                (row or {}).get("player_key") or (row or {}).get("key"))
        cells = assign(frame_id, row, rec)
        s = cells["side"]
        for dim, cell in cells.items():
            c = out[dim].setdefault(cell, {"all": 0, "hit": 0, "pit": 0})
            c["all"] += 1
            if s in ("hit", "pit"):
                c[s] += 1
    return out
