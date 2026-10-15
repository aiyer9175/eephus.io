# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The surrogate guard (docs/efv-v2/SURROGATE_2026_GATE.md s2.3, precondition Q4; task
SG_2 of the efv2026 plan, item N7).

A guard BESIDE the R-LV guard, never through it. efv_vintage_frame.py is not edited
and nothing here calls efv_vintage_frame.guard_score_request: once EFV_V2_GATE.md is
REGISTERED, gate_sha_committed accepts any ancestor whose tree carries that file
marked REGISTERED, so the surrogate gate's own REGISTERED sha would open R-LV if it
were handed over. This module therefore refuses R-LV (V 2020 and 2021) for EVERY
purpose and EVERY sha before it looks at any sha.

What it holds:

    gate_sha_committed_for(gate_sha, gate_doc)
        A PURE predicate built from efv_vintage_frame._SHA_RE, _git_ok, _git_show and
        gate_doc_registered: True only for a 40-hex commit sha that is an ancestor of
        HEAD and whose tree carries `gate_doc` with the status line reading exactly
        REGISTERED. No memo, no side effect.
    gate_header_records(gate_sha, key)
        One owner answer (for example "OQ2") read from the REGISTERED surrogate gate's
        header at that sha: the header is the text above the first line reading
        exactly "---", and the answer is a line of the form
            Owner answer (efv2026 OQ2): B. ...
        (an "at <when>" phrase may sit between "answer" and the bracket; the letter
        may be bold). None for a draft, an absent key or two lines that disagree.
    look_records()
        The recorded look ids, read ONLY from data/efv_v2_gate.json (absent today):
        an entry of its "looks" or "releases" list (or mapping) counts when its id is
        one of RECORD_IDS and it carries a non-empty "recorded_at". Nothing else may
        claim a record: a caller that hands guard_surrogate_read or
        withhold_reserved_vm an id the file does not hold is refused.
    guard_surrogate_read(vintage, *, gate_sha, look_records, purpose)
        The frame schedule of s2.3, by purpose:
            transfer          V 2011-2019 at REGISTERED; V 2022 only with R-VM look 1;
                              V 2023, 2024, 2025 and 2026 never.
            lv2026_surrogate  V 2026 only with R-VM look 2 AND the header's OQ2 = B.
            lv2026_long_run   V 2026 only with looks 1, 2 and 3 and the OQ6 release.
        Everything else refuses. A V 2026 read also refuses while the ETA look record
        (eta_look_recorded) is absent.
    eta_look_recorded()
        True when data/eta_eval.json carries the block fg_blend_gate_2026_09_25 with
        its decision; require_eta_look() refuses otherwise. Every function that would
        compute a 2026 outcome calls it first.
    withhold_reserved_vm(rows, *, look_records, purpose)
        B9b rule 2 (EFV_V2_GATE.md s5), by REFUSING, never by dropping: a row whose
        player debuted in 2025 or later inside its frame's window needs the record of
        the R-VM look that owns its cohort (2025: look 1, 2026: look 2, 2027: look 3;
        2028 and 2029: the OQ6 release; later cohorts have no release). Without it the
        call raises ReservedFrameError naming the count per cohort; with it every row
        comes back, the reserved ones marked `reserved_vm_event_only`.
    blocked_day(today=None)
        Refuses on 2026-10-23, 2026-11-06, 2026-11-13 and 2026-11-20, on the eFV
        reserved-read day (the date data/efv_v2_gate.json records once it exists,
        else the dates STATUS.md records) and while a session marker of another gate's
        look (`look_started.json` under a .cache subdirectory) is present.

Nothing here reads a frame row's grade, a label or an outcome, and nothing here groups
anything by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

import efv_vintage_frame as F
from efv_vintage_frame import RESERVED_LV, ReservedFrameError

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

#: The registration this guard opens on (relative to this directory). Never GATE_DOC.
SURROGATE_GATE_DOC = "docs/efv-v2/SURROGATE_2026_GATE.md"
#: The only file that may claim a look record (EV-13's look runner writes it), for
#: looks 2 and 3 and the OQ6 release.
GATE_RECORD_NAME = "efv_v2_gate.json"
#: R-VM look 1 is held by the EW2-6 same-day backtest record of 2026-10-08 (the 2025
#: cohort read once, EFV_V2_GATE.md s11), not by GATE_RECORD_NAME (amended 2026-10-15).
LOOK_1_RECORD_NAME = "_labs/efv_v3/efv_v3_confirm.json"
LOOK_1_RECORD_ITEM = "EFV3_W3_SELECT_CONFIRM"
#: The ETA FanGraphs-blend look (precondition Q1): no 2026 outcome before its record.
ETA_EVAL_NAME = "eta_eval.json"
ETA_LOOK_BLOCK = "fg_blend_gate_2026_09_25"
#: The STATUS.md the reserved-read day is read from before the record exists.
STATUS_DOC = "docs/efv-v2/STATUS.md"

PURPOSES = ("transfer", "lv2026_surrogate", "lv2026_long_run")

LOOK_1 = "rvm_look_1"
LOOK_2 = "rvm_look_2"
LOOK_3 = "rvm_look_3"
OQ6_RELEASE = "oq6_release"
RECORD_IDS = frozenset({LOOK_1, LOOK_2, LOOK_3, OQ6_RELEASE})

#: The transfer frames read at REGISTERED (s2.1); V 2022 waits for look 1.
TRANSFER_OPEN = frozenset(range(2011, 2020))
TRANSFER_AFTER_LOOK_1 = 2022
#: The prospective frame (s2.2).
LV_2026 = 2026

#: The R-VM debut cohort -> the record that releases it (PROG:142, GATE:61-62; OQ6
#: for the cohorts no R-VM look owns). A cohort missing here has no release at all.
COHORT_RELEASE = {2025: LOOK_1, 2026: LOOK_2, 2027: LOOK_3,
                  2028: OQ6_RELEASE, 2029: OQ6_RELEASE}
#: Seasons after V a debut counts as inside the frame's window, by purpose: the
#: transfer read takes S(V) and R3 (debut V..V+3), the surrogate read of lv_2026 takes
#: season V only, the long-run label reads R3 at RT 2029 and W3 at RT 2031 take debuts
#: V..V+3 (efv_labels.W_DEBUT_WINDOW, asserted equal by the tests).
DEBUT_WINDOW_SEASONS = {"transfer": 3, "lv2026_surrogate": 0, "lv2026_long_run": 3}
RESERVED_VM_STATUS = "reserved_vm_event_only"

#: Registered look days on which no surrogate lab, look or frame fetch runs (Q7).
#: EMPTY since 2026-10-15: the owner waived every registered look day on 2026-10-14
#: (decision EW3-5, "we don't have to wait for anything"); the four days it held
#: (2026-10-23, 2026-11-06, 2026-11-13, 2026-11-20) no longer block. The session
#: marker check below still refuses while another gate's look is running.
LOOK_DAYS: frozenset[str] = frozenset()
#: The reserved read's scheduled day in PROGRAM.md, the floor when STATUS.md names none.
RESERVED_READ_DEFAULT = "2026-12-01"
#: A look runner writes this file into its own .cache subdirectory when scoring
#: begins (tools/dvm_difficulty_lab.LOOK_MARKER); this gate's own directory is skipped.
LOOK_MARKER = "look_started.json"
OWN_CACHE_DIR = "efv_surrogate"

_ISO = r"(\d{4}-\d{2}-\d{2})"
_ANSWER_RE = re.compile(
    r"^Owner answer\b[^(\n]*\(efv2026 (OQ\d+)\):\s*\**\s*([A-Z])\b")


class BlockedDayError(RuntimeError):
    """A surrogate read, lab or look asked for on a blocked day."""


# ---------------------------------------------------------------------------
# the committed gate
# ---------------------------------------------------------------------------

def gate_sha_committed_for(gate_sha: str | None, gate_doc: str) -> bool:
    """True only for a full 40-hex commit sha that is an ancestor of HEAD and whose
    tree carries `gate_doc` marked REGISTERED (efv_vintage_frame.gate_doc_registered).
    Pure: nothing is cached and nothing is written."""
    if not isinstance(gate_sha, str) or not F._SHA_RE.match(gate_sha):
        return False
    if not isinstance(gate_doc, str) or not gate_doc:
        return False
    if not F._git_ok("cat-file", "-e", f"{gate_sha}^{{commit}}"):
        return False
    if not F._git_ok("cat-file", "-e", f"{gate_sha}:./{gate_doc}"):
        return False
    if not F.gate_doc_registered(F._git_show(f"{gate_sha}:./{gate_doc}")):
        return False
    return F._git_ok("merge-base", "--is-ancestor", gate_sha, "HEAD")


def _header(text: str) -> str:
    out = []
    for ln in (text or "").splitlines():
        if ln.strip() == "---":
            break
        out.append(ln)
    return "\n".join(out)


def header_answer(text: str | None, key: str) -> str | None:
    """The owner answer letter for `key` (for example "OQ2") in a gate text's header,
    or None when absent or when two header lines disagree."""
    found = set()
    for ln in _header(text or "").splitlines():
        m = _ANSWER_RE.match(ln.strip())
        if m and m.group(1) == key:
            found.add(m.group(2))
    return found.pop() if len(found) == 1 else None


def gate_header_records(gate_sha: str | None, key: str) -> str | None:
    """One owner answer read from the REGISTERED surrogate gate's header at `gate_sha`.
    None unless that sha carries SURROGATE_GATE_DOC marked REGISTERED."""
    if not gate_sha_committed_for(gate_sha, SURROGATE_GATE_DOC):
        return None
    return header_answer(F._git_show(f"{gate_sha}:./{SURROGATE_GATE_DOC}"), key)


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _entries(block) -> list[dict]:
    if isinstance(block, dict):
        return [dict(v, id=v.get("id", k)) for k, v in block.items() if isinstance(v, dict)]
    if isinstance(block, list):
        return [e for e in block if isinstance(e, dict)]
    return []


def _recorded_entries(doc) -> list[dict]:
    if not isinstance(doc, dict):
        return []
    out = []
    for name in ("looks", "releases"):
        for e in _entries(doc.get(name)):
            rid = e.get("id")
            at = e.get("recorded_at")
            if rid in RECORD_IDS and isinstance(at, str) and at.strip():
                out.append(e)
    return out


def look_1_recorded() -> bool:
    """True when the EW2-6 confirm record holds R-VM look 1: the reserved one-read
    record of LOOK_1_RECORD_ITEM, stamped, whose guards read the 2025 cohort."""
    doc = _read_json(DATA_DIR / LOOK_1_RECORD_NAME)
    if not isinstance(doc, dict):
        return False
    guards = (doc.get("gate") or {}).get("guards") if isinstance(doc.get("gate"), dict) else None
    cohorts = (guards or {}).get("r_vm_cohort_read") if isinstance(guards, dict) else None
    at = doc.get("generated_at")
    return (doc.get("item") == LOOK_1_RECORD_ITEM and doc.get("role") == "reserved"
            and doc.get("one_read") is True and isinstance(at, str) and bool(at.strip())
            and isinstance(cohorts, list) and 2025 in cohorts)


def look_records() -> frozenset[str]:
    """The recorded look and release ids: look 1 from the EW2-6 confirm record
    (LOOK_1_RECORD_NAME), everything else only from data/efv_v2_gate.json. Empty
    while both are absent."""
    doc = _read_json(DATA_DIR / GATE_RECORD_NAME)
    ids = {e["id"] for e in _recorded_entries(doc)}
    if look_1_recorded():
        ids.add(LOOK_1)
    return frozenset(ids)


def _checked_records(claimed) -> frozenset[str]:
    """The caller's records, refused when any is not held by the record file."""
    claimed = frozenset(claimed or ())
    extra = sorted(claimed - look_records())
    if extra:
        raise ReservedFrameError(
            f"look records {extra} are not in data/{GATE_RECORD_NAME} or, for look 1, "
            f"data/{LOOK_1_RECORD_NAME}; only those files may claim a record "
            "(SURROGATE_2026_GATE.md s2.3).")
    return claimed


def eta_look_recorded() -> bool:
    """True when data/eta_eval.json carries the ETA FanGraphs-blend look's block with
    its decision (SURROGATE_2026_GATE.md Q1)."""
    doc = _read_json(DATA_DIR / ETA_EVAL_NAME)
    blk = doc.get(ETA_LOOK_BLOCK) if isinstance(doc, dict) else None
    return isinstance(blk, dict) and bool(blk.get("decision"))


def require_eta_look() -> None:
    """Refuse any computation of a 2026 outcome while the ETA look record is absent."""
    if not eta_look_recorded():
        raise ReservedFrameError(
            f"no 2026 outcome before the ETA look's record (data/{ETA_EVAL_NAME} block "
            f"{ETA_LOOK_BLOCK}; SURROGATE_2026_GATE.md Q1).")


# ---------------------------------------------------------------------------
# the read guard
# ---------------------------------------------------------------------------

def _refuse(vintage: int, purpose: str, why: str):
    raise ReservedFrameError(
        f"surrogate {purpose} read of V {vintage} refused: {why} "
        "(SURROGATE_2026_GATE.md s2.3).")


def guard_surrogate_read(vintage: int, *, gate_sha: str | None = None,
                         look_records=(), purpose: str) -> None:
    """Raise ReservedFrameError unless the surrogate gate's schedule opens V for this
    purpose. R-LV refuses first, for every purpose and every sha."""
    v = int(vintage)
    if v in RESERVED_LV:
        raise ReservedFrameError(
            f"list vintage {v} is reserved (R-LV, RESERVED_LV={sorted(RESERVED_LV)}); "
            "the surrogate gate never reads it, for any purpose or sha "
            "(SURROGATE_2026_GATE.md s2.3).")
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}, got {purpose!r}")
    if not gate_sha_committed_for(gate_sha, SURROGATE_GATE_DOC):
        _refuse(v, purpose, f"needs the sha of the commit carrying {SURROGATE_GATE_DOC} "
                            f"marked REGISTERED, got {gate_sha!r}")
    recs = _checked_records(look_records)
    if purpose == "transfer":
        if v in TRANSFER_OPEN:
            return
        if v == TRANSFER_AFTER_LOOK_1:
            if LOOK_1 in recs:
                return
            _refuse(v, purpose, f"V {v} waits for the record of {LOOK_1}")
        _refuse(v, purpose, "the transfer read takes V 2011-2019 and V 2022 only")
    if v != LV_2026:
        _refuse(v, purpose, f"purpose {purpose} reads V {LV_2026} only")
    if purpose == "lv2026_surrogate":
        if LOOK_2 not in recs:
            _refuse(v, purpose, f"waits for the record of {LOOK_2}")
        if gate_header_records(gate_sha, "OQ2") != "B":
            _refuse(v, purpose, "the gate header does not record efv2026 OQ2 = B")
    else:
        missing = [r for r in (LOOK_1, LOOK_2, LOOK_3, OQ6_RELEASE) if r not in recs]
        if missing:
            _refuse(v, purpose, f"waits for the records {missing}")
    require_eta_look()


def _debut_year(row: dict) -> int | None:
    y = row.get("debut_year")
    if y is None:
        d = row.get("debut_date")
        y = d[:4] if isinstance(d, str) and len(d) >= 4 else None
    try:
        return int(y) if y is not None else None
    except (TypeError, ValueError):
        return None


def withhold_reserved_vm(rows, *, look_records=(), purpose: str):
    """B9b rule 2 by refusal. Returns (rows, released) where every input row comes
    back (copied) and `released` counts the reserved rows per debut cohort; raises
    ReservedFrameError, naming the count per cohort, while any in-window 2025-or-later
    debutant lacks its owning record. Never drops a row."""
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}, got {purpose!r}")
    recs = _checked_records(look_records)
    span = DEBUT_WINDOW_SEASONS[purpose]
    lacking: dict[int, int] = {}
    released: dict[int, int] = {}
    out = []
    for row in rows:
        r = dict(row)
        v = int(r["vintage"])
        if v in RESERVED_LV:
            raise ReservedFrameError(f"a row of reserved list vintage {v} reached the "
                                     "surrogate path (R-LV)")
        dy = _debut_year(r)
        if dy is not None and dy >= F.R_VM_FIRST_DEBUT_YEAR and v <= dy <= v + span:
            rec = COHORT_RELEASE.get(dy)
            if rec is None or rec not in recs:
                lacking[dy] = lacking.get(dy, 0) + 1
            else:
                released[dy] = released.get(dy, 0) + 1
                r["status"] = RESERVED_VM_STATUS
                r["release_record"] = rec
                if purpose == "lv2026_long_run":
                    r["label_released"] = True
                else:
                    r["mlb_stat_read"] = False
        out.append(r)
    if lacking:
        named = ", ".join(f"{c}: {n}" for c, n in sorted(lacking.items()))
        raise ReservedFrameError(
            f"{sum(lacking.values())} in-window R-VM debut rows lack their owning record "
            f"(per cohort {named}); the read waits whole, no row is dropped "
            "(EFV_V2_GATE.md B9b rule 2; SURROGATE_2026_GATE.md s8.1).")
    return out, dict(sorted(released.items()))


# ---------------------------------------------------------------------------
# blocked days
# ---------------------------------------------------------------------------

def _dates_in(value) -> set[str]:
    vals = value if isinstance(value, list) else [value]
    out = set()
    for x in vals:
        if isinstance(x, str):
            m = re.match(_ISO, x.strip())
            if m:
                out.add(m.group(1))
    return out


def reserved_read_days() -> frozenset[str]:
    """The eFV reserved-read day(s): from data/efv_v2_gate.json once it exists (its
    `reserved_read_date` and the day of every recorded look), else from STATUS.md (the
    day a decision moved the read to and the day it replaced), never empty."""
    doc = _read_json(DATA_DIR / GATE_RECORD_NAME)
    days: set[str] = set()
    if isinstance(doc, dict):
        days |= _dates_in(doc.get("reserved_read_date"))
        for e in _recorded_entries(doc):
            days |= _dates_in(e.get("recorded_at"))
    if not days:
        try:
            text = (ROOT / STATUS_DOC).read_text(encoding="utf-8")
        except OSError:
            text = ""
        for m in re.finditer(r"\(" + _ISO + r"\) replaced the " + _ISO
                             + r" reserved read", text):
            days |= {m.group(1), m.group(2)}
        for m in re.finditer(r"only then can R-LV[^.]*?not before " + _ISO, text):
            days.add(m.group(1))
    return frozenset(days or {RESERVED_READ_DEFAULT})


def marker_start_day(path: Path) -> str | None:
    """The local calendar day on which a look marker records its look started (its
    `started` ISO time, read in local time), or None when it records no readable start."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    s = doc.get("started") if isinstance(doc, dict) else None
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        t = _dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is not None:
        t = t.astimezone()
    return t.date().isoformat()


def look_session_markers(today: str | None = None) -> list[str]:
    """Look markers another gate's runner left under .cache (one level deep) that mark a
    look session open on `today` (an ISO date). A marker whose recorded start falls on an
    EARLIER day belongs to a finished session (the DvM+ runner keeps its marker for good as
    its spent-look record), so it does not block; a marker with no readable start, or
    any marker when `today` is None, still does (amended 2026-10-15, task SG_8: Q7 refuses
    a session that runs another gate's look, never a calendar day)."""
    cache = ROOT / ".cache"
    found = []
    try:
        entries = [e for e in cache.iterdir() if e.is_dir()]
    except OSError:
        return found
    for d in sorted(entries):
        if d.name == OWN_CACHE_DIR:
            continue
        marker = d / LOOK_MARKER
        if marker.exists():
            started = marker_start_day(marker)
            if today is not None and started is not None and started < str(today)[:10]:
                continue
            found.append(f".cache/{d.name}/{LOOK_MARKER}")
    return found


def blocked_day_reason(today=None) -> str | None:
    """Why `today` (an ISO date, a date, or None for the local date) is blocked, or
    None when it is open."""
    if today is None:
        today = _dt.date.today()
    day = today.isoformat() if isinstance(today, _dt.date) else str(today)[:10]
    if day in LOOK_DAYS:
        return f"{day} is a registered look day"
    # The reserved-read day no longer blocks: EW2-6 (2026-10-08) replaced the read
    # with the same-day backtest and EW3-5 (2026-10-14) waived the registered days.
    markers = look_session_markers(day)
    if markers:
        return "another gate's look session is open: " + ", ".join(markers)
    return None


def blocked_day(today=None) -> None:
    """Refuse (BlockedDayError) on a blocked day; return None on an open one."""
    why = blocked_day_reason(today)
    if why:
        raise BlockedDayError(f"surrogate work refused: {why} (SURROGATE_2026_GATE.md Q7).")
