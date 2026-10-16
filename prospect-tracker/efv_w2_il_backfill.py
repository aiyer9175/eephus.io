# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4 wave 2, the injured-list family on real coverage (EFV4_IL_BACKFILL_FROM_TX_CACHE;
owner 2026-10-08, decisions EW2-8 to EW2-12; research s2.2).

WHY. The injury family was COVERAGE-STARVED (data/xfv_injury_history_eval.json): the
repo's il_history table starts in 2017 and holds 5 to 115 stints a year before 2026, so
the resolved cohort carried 2 hitter and 0 pitcher pre-cutoff stints. Its revival
trigger is "at least 100 pre-cutoff stints on the resolved debuted cohort". The
league-wide transactions feed already on disk (.cache/mlb_transactions/tx_YYYY_MM.json.gz,
efv_drivers.LEAGUE_TX_FIRST, complete from efv_drivers.LEAGUE_TX_FULL_FROM = 2009) holds
every affiliated placement on and activation from the disabled or injured list, each
with person.id. This module parses it into a stint table and screens five as-of
columns. No fetch: the cache is read, never written.

THE STINT TABLE (build_table, data/_labs/efv_w2/milb_il_stints.json). Every IL row of
the feed (description matching "(disabled|injured) list") becomes one event, read in
(announced date, transaction id) order per person.id:

    placed       "... placed <pos> <name> on the N-day (disabled|injured) list
                 [retroactive to <date>]": opens a stint at effectiveDate (the
                 retroactive day when given), list N (7, 10, 15, 60, full season).
                 An earlier stint still open is closed at this start ("next_placement").
    transferred  "... transferred ... from the A list to the B list": marks the open
                 stint severe when B is the 60-day or full-season list (dated by the
                 transfer's announcement); with no open stint it opens one there.
    activated    "... (activated|reinstated) ... from the ... list": closes the open
                 stint at its effectiveDate; with none open it is an orphan (counted).
    released     a REL, RET, DFA or DEC transaction of the person closes an open stint.

A stint carries its start, the announced placement day, the list, the severe flag and
the day it became known, the end, the day the end was announced and how it ended.

THE COLUMNS, read for a person id as of a cutoff day C (the protection_asof rule: a
list vintage V reads C = V-01-01; a vintage-matched matrix row reads C = the earlier of
its matrix cutoff and the decision year's 1 January). Only facts ANNOUNCED strictly
before C enter. The window is the LOOKBACK_SEASONS seasons ending with the season that
holds the day before C, cut at 2009-01-01 (the feed's first complete year):

    il_stints_pre      stints placed inside the window
    il_days_pre        regular-season days on the list inside the window (each stint
                       from its start to its end, or to C when the end was not
                       announced before C, intersected with 1 April to 30 September of
                       each year), log1p. A stint whose end is not an announced
                       activation (a release, a later placement, or no end before C)
                       counts only through 30 September of its placement year: 17
                       percent of stints close on a later placement and 11 percent on
                       a release, the signature of an activation the feed missed
    il_60day_pre       stints placed on, or transferred before C to, the 60-day or
                       full-season list
    il_open_at_read    1 when a stint placed in the window's last season had no end
                       announced before C (a known fact at the read; an activation
                       after C is never read)
    il_recurrent_pre   1 when il_stints_pre is at least 2

A row without an outcome-blind id reads None on every column (the lab imputes it at the
fold's has-block training mean); a resolved id with no stint reads 0. The absence of a
value ("il_absent") is read only by the DS-03 balance probe; it never enters any head.

ID. A list-vintage row reads its OUTCOME-BLIND `mlbam_id` (efv_identity through
efv_vintage_frame), never `record_mlbam_id`. A vintage-matched row reads the matrix id,
as the base V2 reads it there (the efv_w2_milb convention; disclosed in the artifact).

ARMS (15, one wave-2 family): each column offered to the TIMING head of both sides and
to the pitcher SKILL head, through the screening lab's machinery (efv_v2_model.fit_v2
extra=..., DS-06 admission inside every fold). A pitcher timing column is offered only
in a fold whose base has a usable pitcher skill head (owner DS-Q2).

READS. dev_read: lv_dev (list vintages 2017 to 2019 through the lab's Frame and
measure_arm: admission per fold, the permuted twin, the DS-03 balance probe) and vm_dev
(frame version vm2, DS-16's rows, base parity asserted), each against the V2 base and
against PROSPX consensus, E_cond CI95. spent_read: R-LV (list vintages 2020 and 2021)
and R-VM (the 2025 debut cohort) through tools/efv_v3_backtest.build_reserved on the
committed gate's sha, which the owner's waiver read once on 2026-10-08; every block there
is labelled SPENT_LABEL and nothing is chosen or tuned on it. The ground-truth study of
the injury eval is re-run first (ground_truth_rerun): pre-cutoff stints on the resolved
debuted matrix cohort, against its trigger of 100.

BANS. No served number moves; no flag; the displayed PROSPX consensus never changes.
Nothing here groups, counts or averages anything by consensus-FV level
(docs/PROSPECT_ANCHOR_GATE.md): the only summaries are counts by side, year and vintage.
No column builder reads a label, a realized value or a debut. List vintages 2020 and
2021 and the 2025 cohort raise through efv_vintage_frame unless the committed gate sha is
handed in (spent_read only). Selects and adjudicates nothing (EW2-10).

Run:  python efv_w2_il_backfill.py --build-table
      python efv_w2_il_backfill.py --ground-truth
      python efv_w2_il_backfill.py --dev-read
      python efv_w2_il_backfill.py --spent-read --gate-sha SHA
      python efv_w2_il_backfill.py --ledger --ledger-path PATH
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import math
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import efv_drivers as DRV
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv_w2"
TABLE_PATH = LAB_DIR / "milb_il_stints.json"
OUT_PATH = LAB_DIR / "efv_w2_il_backfill.json"
TOOL = "efv_w2_il_backfill.py"
MODULE = "efv_w2_il_backfill"
ITEM = "EFV4_IL_BACKFILL_FROM_TX_CACHE"
WAVE = 2
MODEL_PREFIX = "efv_v2_screen:wave2:"

#: Declared 2026-10-08 before any read; no constant was tuned on any frame.
LOOKBACK_SEASONS = 4
SEASON_OPEN_MMDD = (4, 1)
SEASON_CLOSE_MMDD = (10, 1)
SEVERE_LISTS = frozenset({"60", "full"})
CLOSE_CODES = frozenset({"REL", "RET", "DFA", "DEC"})
RECURRENT_MIN = 2
COLUMNS: tuple[str, ...] = ("il_stints_pre", "il_days_pre", "il_60day_pre",
                            "il_open_at_read", "il_recurrent_pre")
TRANSFORM = {"il_days_pre": "log1p"}
SPENT_LABEL = "spent frame, read after the 10-08 confirmation"
#: The ground-truth trigger of data/xfv_injury_history_eval.json.
REVIVAL_TRIGGER_STINTS = 100

_SHORT = {"il_stints_pre": "stints", "il_days_pre": "days", "il_60day_pre": "sixty",
          "il_open_at_read": "open", "il_recurrent_pre": "recur"}
_HEADS = (("timing", "hit"), ("timing", "pit"), ("skill", "pit"))
ARMS: tuple[dict, ...] = tuple(
    {"name": f"w2i_{_SHORT[c]}_{'time' if h == 'timing' else 'skill'}_{s}", "stat": c,
     "side": s, "head": h, "kind": "column", "retest": False,
     "column": {"source": "module", "module": MODULE, "attr": "screen_column", "arg": c}}
    for h, s in _HEADS for c in COLUMNS)


# ---------------------------------------------------------------------------
# parsing the cached feed
# ---------------------------------------------------------------------------

_LIST_WORD = r"(?:disabled|injured) list"
_IL_ROW = re.compile(_LIST_WORD, re.I)
_LIST_TYPE = re.compile(r"(\d+)[- ]day\s+" + _LIST_WORD + r"|(full)[- ]season\s+" + _LIST_WORD
                        + r"|(seven)-day\s+" + _LIST_WORD, re.I)
_TRANSFER = re.compile(r"\btransferred\b", re.I)
_ACTIVATE = re.compile(r"\b(?:activated|reinstated)\b.*?\bfrom the\b", re.I)
_PLACE = re.compile(r"\bplaced\b.*?\bon the\b", re.I)
_RETRO = re.compile(r"retroactive to\s+([A-Za-z]+\.?\s+\d{1,2},\s+\d{4})", re.I)


def list_types(desc: str) -> list[str]:
    """The list kinds a description names, in order: "7", "10", "15", "60", "full", or
    "na" for a bare "injured list"."""
    out = [("7" if m.group(3) else (m.group(1) or "full").lower())
           for m in _LIST_TYPE.finditer(desc or "")]
    if not out and _IL_ROW.search(desc or ""):
        out = ["na"]
    return out


def classify(desc: str, code: str) -> tuple[str | None, list[str]]:
    """(event kind, list kinds) of one transaction: "transfer", "activate", "place",
    "close" (a release-type code), or None."""
    d = desc or ""
    if _IL_ROW.search(d):
        lists = list_types(d)
        if _TRANSFER.search(d):
            return "transfer", lists
        if _ACTIVATE.search(d):
            return "activate", lists
        if _PLACE.search(d):
            return "place", lists
        return None, lists
    if str(code or "") in CLOSE_CODES:
        return "close", []
    return None, []


def _day(v) -> str | None:
    s = str(v or "")[:10]
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None


def _retro_day(desc: str) -> str | None:
    m = _RETRO.search(desc or "")
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace("Sept ", "Sep ")
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def events_from_feed(transactions: list[dict]) -> dict[int, list[tuple]]:
    """{person id: [(announced day, tx id, kind, lists, effective day, team id)]} for
    the IL and release-type rows of a list of feed transactions (unsorted)."""
    out: dict[int, list[tuple]] = {}
    for t in transactions:
        pid = (t.get("person") or {}).get("id")
        ann = _day(t.get("date")) or _day(t.get("effectiveDate"))
        if not pid or not ann:
            continue
        desc = t.get("description") or ""
        kind, lists = classify(desc, t.get("typeCode"))
        if kind is None:
            continue
        eff = _day(t.get("effectiveDate")) or ann
        if kind == "place":
            eff = _day(t.get("effectiveDate")) or _retro_day(desc) or ann
        team = (t.get("toTeam") or t.get("fromTeam") or {}).get("id")
        out.setdefault(int(pid), []).append(
            (ann, int(t.get("id") or 0), kind, tuple(lists), eff, team))
    return out


def stints_from_events(events: list[tuple]) -> tuple[list[dict], int]:
    """(stints, orphan activations) of one person's events (module docstring)."""
    stints: list[dict] = []
    orphans = 0
    cur: dict | None = None

    def close(ev, how):
        nonlocal cur
        cur.update(end=max(ev[4], cur["start"]), end_announced=ev[0], how=how)
        stints.append(cur)
        cur = None

    for ev in sorted(events, key=lambda e: (e[0], e[1])):
        ann, _tid, kind, lists, eff, team = ev
        if kind == "place":
            if cur is not None:
                close((ann, 0, "", (), min(eff, ann), None), "next_placement")
            lt = lists[0] if lists else "na"
            sev = lt in SEVERE_LISTS
            cur = {"start": min(eff, ann), "placed": ann, "list": lt, "severe": sev,
                   "severe_announced": ann if sev else None, "end": None,
                   "end_announced": None, "how": None, "team": team,
                   "start_inferred": False}
        elif kind == "transfer":
            to = lists[-1] if lists else "na"
            if cur is None:
                cur = {"start": min(eff, ann), "placed": ann,
                       "list": lists[0] if lists else "na", "severe": False,
                       "severe_announced": None, "end": None, "end_announced": None,
                       "how": None, "team": team, "start_inferred": True}
            if to in SEVERE_LISTS and not cur["severe"]:
                cur["severe"], cur["severe_announced"] = True, ann
        elif kind == "activate":
            if cur is None:
                orphans += 1
            else:
                close(ev, "activated")
        elif kind == "close" and cur is not None:
            close(ev, "released")
    if cur is not None:
        stints.append(cur)
    return stints, orphans


TABLE_COLUMNS = ("pid", "start", "placed", "list", "severe", "severe_announced", "end",
                 "end_announced", "how", "team", "start_inferred")


def read_feed(tx_dir: Path = DRV.TX_DIR, last_year: int | None = None) -> tuple[dict, dict]:
    """(events by person, receipt) over every cached month."""
    last = int(last_year or datetime.now(timezone.utc).year)
    months = DRV.league_tx_months(last, tx_dir)
    events: dict[int, list[tuple]] = {}
    per_year: dict = {}
    present = [ym for ym, ok in months.items() if ok]
    for ym in present:
        y, m = (int(p) for p in ym.split("-"))
        with gzip.open(DRV.league_tx_path(y, m, tx_dir), "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        txs = doc.get("transactions") or []
        c = per_year.setdefault(str(y), {"transactions": 0, "il_rows": 0})
        c["transactions"] += len(txs)
        c["il_rows"] += sum(1 for t in txs if _IL_ROW.search(t.get("description") or ""))
        for pid, evs in events_from_feed(txs).items():
            events.setdefault(pid, []).extend(evs)
    receipt = {"dir": ".cache/mlb_transactions", "months_on_disk": len(present),
               "first_month": present[0] if present else None,
               "last_month": present[-1] if present else None,
               "complete_from": DRV.LEAGUE_TX_FULL_FROM, "per_year": per_year}
    return events, receipt


def build_table(*, tx_dir: Path = DRV.TX_DIR, out: Path | None = TABLE_PATH,
                last_year: int | None = None) -> dict:
    """Parse the cached feed into the stint table; write it when `out` is given."""
    events, receipt = read_feed(tx_dir, last_year)
    rows = []
    orphans = 0
    by_year: dict = {}
    for pid in sorted(events):
        st, orph = stints_from_events(events[pid])
        orphans += orph
        for s in st:
            rows.append([pid, s["start"], s["placed"], s["list"], int(s["severe"]),
                         s["severe_announced"], s["end"], s["end_announced"], s["how"],
                         s["team"], int(s["start_inferred"])])
            c = by_year.setdefault(s["placed"][:4], {"stints": 0, "severe": 0,
                                                      "closed": 0, "persons": set()})
            c["stints"] += 1
            c["severe"] += int(s["severe"])
            c["closed"] += int(s["end"] is not None)
            c["persons"].add(pid)
    rows.sort(key=lambda r: (r[0], r[2], r[1]))
    per_year = {y: {"stints": c["stints"], "severe": c["severe"], "closed": c["closed"],
                    "persons": len(c["persons"])} for y, c in sorted(by_year.items())}
    doc = {"schema": 1, "item": ITEM, "produced_by": f"{TOOL} --build-table",
           "source": receipt, "orphan_activations": orphans, "n_stints": len(rows),
           "n_persons": len({r[0] for r in rows}), "per_placed_year": per_year,
           "columns": list(TABLE_COLUMNS), "rows": rows}
    if out is not None:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("{\n")
            head = {k: v for k, v in doc.items() if k != "rows"}
            for k, v in head.items():
                fh.write(f" {json.dumps(k)}: {json.dumps(v, separators=(',', ':'))},\n")
            fh.write(' "rows": [\n')
            for i, r in enumerate(rows):
                fh.write("  " + json.dumps(r, separators=(",", ":"))
                         + (",\n" if i < len(rows) - 1 else "\n"))
            fh.write(" ]\n}\n")
        tmp.replace(out)
    return doc


# ---------------------------------------------------------------------------
# the stint index and the as-of columns
# ---------------------------------------------------------------------------

_INDEX: dict = {}


def index_from_rows(rows: list[list]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in rows:
        s = dict(zip(TABLE_COLUMNS, r))
        out.setdefault(int(s["pid"]), []).append(s)
    for v in out.values():
        v.sort(key=lambda s: (s["placed"], s["start"]))
    return out


def stint_index(path: Path = TABLE_PATH) -> dict[int, list[dict]]:
    """{person id: stints sorted by announced placement} from the table (memoized)."""
    key = str(path)
    if key not in _INDEX:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        _INDEX.clear()
        _INDEX[key] = index_from_rows(doc["rows"])
    return _INDEX[key]


def _d(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def season_days(a: date, b: date) -> int:
    """Days of [a, b) inside 1 April to 30 September of each year."""
    if b <= a:
        return 0
    n = 0
    for y in range(a.year, b.year + 1):
        lo = max(a, date(y, *SEASON_OPEN_MMDD))
        hi = min(b, date(y, *SEASON_CLOSE_MMDD))
        if hi > lo:
            n += (hi - lo).days
    return n


def window(cutoff: str) -> tuple[date, date, int] | None:
    """(window start, cutoff, last season) of a read, or None when the last season
    precedes the feed's first complete year."""
    cut = _d(cutoff)
    last = (cut - timedelta(days=1)).year
    if last < DRV.LEAGUE_TX_FULL_FROM:
        return None
    first = max(last - LOOKBACK_SEASONS + 1, DRV.LEAGUE_TX_FULL_FROM)
    return date(first, 1, 1), cut, last


#: EFV_PIT_DRIFT_REBASE R1 (docs/efv-v2/EFV_PIT_DRIFT_REBASE.md section 3): the months of a
#: winter carry-over (a severe stint activated from 1 October, re-placed by 30 April).
CARRY_END_FROM_MONTH = 10
CARRY_START_TO_MONTH = 4


def _known(day, cut: date) -> bool:
    return bool(day) and _d(day) < cut


def new_episode(s: dict, prev: dict | None, cut: date) -> bool:
    """R1's training definition of a 60-day count: False for a severe stint that is not a
    new injury episode as the training-era feed recorded one. A DUPLICATE ended by a
    following placement on its own start day (the feed reported one placement twice); a
    CARRY-OVER placed from 1 January to 30 April when `prev`, the person's previous
    counted severe stint, ended by activation from 1 October of the year before. Only
    facts announced before `cut` are read."""
    if (s.get("how") == "next_placement" and s.get("end") == s.get("start")
            and _known(s.get("end_announced"), cut)):
        return False
    if prev is not None and prev.get("how") == "activated" and prev.get("end") \
            and _known(prev.get("end_announced"), cut):
        pe, ps = _d(prev["end"]), _d(s["start"])
        if (pe.month >= CARRY_END_FROM_MONTH and ps.year == pe.year + 1
                and ps.month <= CARRY_START_TO_MONTH):
            return False
    return True


def asof(person_id, cutoff: str, index: dict | None = None, *, episodes: bool = False) -> dict:
    """The five columns of one person read as of `cutoff` (module docstring), raw
    (untransformed). None on every column without an id or a covered window. With
    `episodes` (the served read under efv5_combined.DRIFT_REBASE_ON only) il_60day_pre
    counts injury episodes (new_episode); every other column is unchanged."""
    out = {c: None for c in COLUMNS}
    try:
        pid = int(person_id) if person_id is not None else None
    except (TypeError, ValueError):
        pid = None
    w = window(cutoff)
    if pid is None or w is None:
        return out
    lo, cut, last = w
    idx = stint_index() if index is None else index
    n = sev = days = 0
    open_at = 0
    prev_sev = None
    for s in idx.get(pid, ()):
        placed = _d(s["placed"])
        if placed >= cut:
            break
        if placed < lo:
            continue
        n += 1
        if s["severe"] and s["severe_announced"] and _d(s["severe_announced"]) < cut:
            if not episodes or new_episode(s, prev_sev, cut):
                sev += 1
                prev_sev = s
        known_end = (_d(s["end"]) if s["end"] and s["end_announced"]
                     and _d(s["end_announced"]) < cut else None)
        end = min(known_end or cut, cut)
        if known_end is None or s["how"] != "activated":
            # no announced activation: never assumed to span a winter
            end = min(end, date(placed.year, *SEASON_CLOSE_MMDD))
        days += season_days(max(_d(s["start"]), lo), end)
        if known_end is None and placed.year == last:
            open_at = 1
    out.update({"il_stints_pre": float(n), "il_days_pre": float(days),
                "il_60day_pre": float(sev), "il_open_at_read": float(open_at),
                "il_recurrent_pre": float(n >= RECURRENT_MIN)})
    return out


def transformed(stat: str, v):
    if v is None:
        return None
    return math.log1p(float(v)) if TRANSFORM.get(stat) == "log1p" else float(v)


def lv_cutoff(vintage: int) -> str:
    return f"{int(vintage)}-01-01"


def lv_reads(side: str, frames: dict, *, gate_sha: str | None = None,
             index: dict | None = None) -> dict:
    """{(V, player_key): raw columns} on the side's list-vintage frame rows, each read on
    its OUTCOME-BLIND `mlbam_id` as of V-01-01. A reserved vintage raises unless the
    committed gate sha is handed in."""
    out = {}
    for V, (rows, _l) in sorted((frames.get(side) or {}).items()):
        F.guard_score_request(int(V), gate_sha=gate_sha, purpose="w2 il column")
        for r in rows:
            out[(int(V), r["player_key"])] = asof(r.get("mlbam_id"), lv_cutoff(V), index)
    return out


_LV_MEMO: dict = {}


def screen_column(stat: str, side: str, frames: dict) -> dict:
    """The screening lab's builder hook (column source "module", arg = column):
    {(V, player_key): value | None} on the side's list-vintage frame rows."""
    if stat not in COLUMNS:
        raise ValueError(f"{stat} is not an IL column")
    key = (side, id(frames))
    if key not in _LV_MEMO:
        _LV_MEMO.clear()
        _LV_MEMO[key] = lv_reads(side, frames)
    return {slot: transformed(stat, p.get(stat)) for slot, p in _LV_MEMO[key].items()}


def vm_cutoff(raw: dict, year: int) -> str:
    """The earlier of the matrix cutoff and 1 January of the row's decision year."""
    jan = f"{int(year)}-01-01"
    c = _day((raw or {}).get("cutoff"))
    return min(c, jan) if c else jan


def vm_reads(side: str, data: list[dict], raw_by_key: dict, *, allow_reserved: bool = False,
             index: dict | None = None) -> dict:
    """{player_key: raw columns} on the vintage-matched matrix rows, read on the matrix
    id as of vm_cutoff. A 2025 or later decision year is skipped unless allow_reserved
    (spent_read, after efv_vintage_frame.guard_vm_request opened on the gate sha)."""
    out = {}
    for d in data:
        y = int(d["decision_year"])
        if y >= F.R_VM_FIRST_DEBUT_YEAR and not allow_reserved:
            continue
        raw = raw_by_key.get(d["player_key"]) or {}
        out[d["player_key"]] = asof(raw.get("mlbam_id"), vm_cutoff(raw, y), index)
    return out


def coverage(values: dict) -> dict:
    """{str(year): {"rows", "with_value", "with_stint"}} of {(year, key): columns}."""
    out: dict = {}
    for (y, _k), p in values.items():
        c = out.setdefault(str(y), {"rows": 0, "with_value": 0, "with_stint": 0})
        c["rows"] += 1
        v = p.get("il_stints_pre")
        c["with_value"] += int(v is not None)
        c["with_stint"] += int(bool(v))
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# the ground-truth study, re-run first (data/xfv_injury_history_eval.json step 1)
# ---------------------------------------------------------------------------

def ground_truth_rerun(*, index: dict | None = None) -> dict:
    """Pre-cutoff stints on the resolved (kind "debuted") matrix cohort, the eval's own
    definition (stints announced strictly before the row's matrix cutoff, the whole feed
    from 2009), and under this family's own read (vm_cutoff, LOOKBACK_SEASONS), by side
    and cutoff year, against the trigger of 100. Decision years 2025 and later are not
    read. Counts only."""
    import efv_v2_model as H
    idx = stint_index() if index is None else index
    out = {"trigger": (f"at least {REVIVAL_TRIGGER_STINTS} pre-cutoff stints on the "
                       "resolved debuted cohort (data/xfv_injury_history_eval.json "
                       "revival_trigger)"),
           "eval_before": {"hit_debuted_with_il_pre": 2, "pit_debuted_with_il_pre": 0},
           "sides": {}}
    cleared = True
    for side in F.SIDES:
        raw = json.loads(H._matrix_path(side).read_text(encoding="utf-8"))
        dy = {r["player_key"]: int(r["decision_year"]) for r in H.matrix_training_rows(side)}
        blk = {"debuted_rows": 0, "rows_with_il_pre": 0, "stints_pre": 0,
               "rows_with_il_family_read": 0, "stints_family_read": 0, "by_cutoff_year": {}}
        for r in raw:
            y = dy.get(r["player_key"])
            if r.get("kind") != "debuted" or y is None or y >= F.R_VM_FIRST_DEBUT_YEAR:
                continue
            blk["debuted_rows"] += 1
            pid = r.get("mlbam_id")
            cut = _day(r.get("cutoff"))
            n_all = 0
            if pid is not None and cut:
                n_all = sum(1 for s in idx.get(int(pid), ())
                            if DRV.LEAGUE_TX_FULL_FROM <= int(s["placed"][:4])
                            and s["placed"] < cut)
            fam = asof(pid, vm_cutoff(r, y), idx).get("il_stints_pre") or 0.0
            blk["rows_with_il_pre"] += int(n_all > 0)
            blk["stints_pre"] += n_all
            blk["rows_with_il_family_read"] += int(fam > 0)
            blk["stints_family_read"] += int(fam)
            c = blk["by_cutoff_year"].setdefault(str(cut[:4]) if cut else "none",
                                                 {"rows": 0, "with_il_pre": 0, "stints": 0})
            c["rows"] += 1
            c["with_il_pre"] += int(n_all > 0)
            c["stints"] += n_all
        blk["by_cutoff_year"] = dict(sorted(blk["by_cutoff_year"].items()))
        blk["trigger_cleared"] = blk["stints_pre"] >= REVIVAL_TRIGGER_STINTS
        cleared = cleared and blk["trigger_cleared"]
        out["sides"][side] = blk
    out["trigger_cleared_both_sides"] = cleared
    out["oos_bar"] = ("the family is then re-tested out of sample exactly as every "
                      "wave-2 column: forward-chained folds, DS-06 admission inside each "
                      "fold on training vintages only, E_cond CI95 on the development "
                      "frames (dev_read)")
    return out


# ---------------------------------------------------------------------------
# the development read (lv_dev through the screening lab's Frame; vm_dev at vm2)
# ---------------------------------------------------------------------------

NOTE = ("eFV v4 wave 2 (EFV4 IL backfill), development read only: selects and "
        "adjudicates nothing")


def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def _cand(arm: dict) -> dict:
    out = {k: arm[k] for k in ("name", "side", "head", "kind", "retest", "column")}
    out["what"] = f"{arm['stat']}: MiLB injured-list history as of the read ({MODULE})"
    return out


def lv_read(arms, *, B: int, log=print) -> dict:
    """Every arm on lv_dev (list vintages 2017 to 2019) through the lab's own Frame and
    measure_arm, plus the il_absent DS-03 probe per side. No floor and no permutation
    null: a development read forms no verdict."""
    _tools()
    import efv_screen_lab as LAB
    t0 = time.time()
    frame, frames = LAB.real_frame()
    log(f"lv_dev frame built in {time.time() - t0:.0f} s")
    base_vs_cons = {}
    for s in F.SIDES:
        order = {}
        for V in frame.folds:
            for pk, idx in frame.base(s, V)["order"].items():
                order[(V, pk)] = idx
        base_vs_cons[s] = LAB._vs_consensus(frame, (s,), order, B=B)
    out = {"frame": {"id": "lv_dev", "folds": list(frame.folds), "counts": frame.counts,
                     "w_star_dev": frame.w_star, "label": frame.label},
           "coverage": {}, "il_absent_probe": {}, "arms": {}}
    for s in F.SIDES:
        reads = lv_reads(s, frames)
        out["coverage"][s] = coverage(reads)
        slots = frame.slots(s)
        vals = {k: p.get("il_stints_pre") for k, p in reads.items()}
        ind = LAB._missing_indicator(vals, slots)
        out["il_absent_probe"][s] = LAB.balance_probe(frame, s, ind,
                                                      seed=LAB._seed_for(f"il_absent:{s}"))
        log(f"  il_absent {s}: {out['il_absent_probe'][s].get('verdict')} "
            f"{out['il_absent_probe'][s].get('partial')} {out['il_absent_probe'][s].get('ci95')}")
    for arm in arms:
        t1 = time.time()
        values = screen_column(arm["stat"], arm["side"], frames)
        a = LAB.measure_arm(frame, _cand(arm), values, {}, B=B, n_perm=0,
                            base_vs_cons=base_vs_cons)
        a.pop("_order", None)
        a.pop("permutation_null", None)
        a["tag"] = f"SCREEN-W{WAVE}:{arm['side']}.{arm['head']}.{arm['name']}"
        a["model_id"] = f"{MODEL_PREFIX}{arm['name']}:{arm['side']}"
        a["frame"]["note"] = NOTE
        out["arms"][arm["name"]] = a
        w = a["within"]
        vc = a["frame"]["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        log(f"  lv {arm['name']}: admitted {a['admitted_folds']}/{a['n_folds']}, within vs "
            f"V2 {w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
            f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out


def _vm_attach(rows: list[dict], key: str | None, values: dict) -> list[dict]:
    if key is None:
        return rows
    return [dict(r, v2=dict(r["v2"], **{key: values.get(r["player_key"])})) for r in rows]


def vm_orders(side: str, data: list[dict], weights: dict, years, *, head: str | None = None,
              key: str | None = None, values: dict | None = None) -> tuple[dict, dict]:
    """V2 on the vintage-matched frame exactly as efv_v2_model.v2_vm_scores(timing_pin=
    True) scores it (efv_w2_milb.vm_orders), with one screening column attached to every
    row and offered to `head` when `key` is given."""
    import efv_drivers as DRV2
    import efv_v2_model as H
    mine: dict = {}
    pinned = H.pinned_inputs(side, data, mine)
    panel = DRV2.load_bio_panel()
    vals = values or {}
    order, folds = {}, {}
    for yr in years:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < H.MIN_TEST_ROWS or len(tr) < H.MIN_TRAIN_ROWS:
            continue
        te2 = []
        for r in te:
            pin = pinned.get(r["player_key"])
            if pin is None:
                continue
            extra = {"bmi": DRV2.bmi_asof(r["player_key"],
                                          mine[r["player_key"]].get("asof_date"), panel)}
            te2.append(dict(r, feats=pin["feats"], fv=pin["fv"], extra=extra,
                            v2=H.v2_row(pin["feats"], extra)))
        tr_x, te_x = _vm_attach(tr, key, vals), _vm_attach(te2, key, vals)
        model = H.fit_v2(tr_x, side, frame="vm", weights=weights,
                         extra=({head: (key,)} if key else None))
        hd = (model.get(head) or {}) if key else {}
        adm = ((hd.get("admission") or {}).get(key) or {}) if key else {}
        offered = not (key and head == "timing" and side == "pit"
                       and model.get("timing") is None)
        if key and offered and not adm:
            # the head kept no record (no key of it was admitted): the rule's own check
            adm = H.admission_for_key(tr_x, key,
                                      target="u_y" if head == "skill" else "reached",
                                      has_block_only=head == "skill")
        folds[str(yr)] = {"n_train": len(tr_x), "n_test": len(te_x),
                          "offered": offered if key else None,
                          "admitted": (bool(adm.get("admitted")) and bool(
                              key in (hd.get("keys") or []))) if key else None,
                          "reason": adm.get("reason") if key else None,
                          "per_vintage_signs": adm.get("per_vintage_signs") if key else None,
                          "head_keys": list(hd.get("keys") or []) if key else None,
                          "consensus_only": model["consensus_only"]}
        for p in H.predict_v2(model, te_x):
            order[p["player_key"]] = p["order_idx"]
    return order, folds


def vm_read(arms, *, B: int, log=print) -> dict:
    """Every arm on vm_dev at frame version vm2: DS-16's rows and base order
    (tools/efv_v2_dev_read.v2_vm_dev), then per arm the same forward-chained V2 with the
    column offered to its head. The base is recomputed and must equal DS-16's."""
    import efv_v2_model as H
    import efv_w2_milb as W2M
    _tools()
    import efv_v2_dev_read as DR
    t0 = time.time()
    weights = H.load_weights()
    rows, meta = DR.v2_vm_dev(DATA_DIR, weights)
    years = meta["fold_years"]
    if any(int(y) >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm years reach R-VM: {years}")
    log(f"vm_dev rows built in {time.time() - t0:.0f} s ({len(rows)} rows)")
    out = {"frame": {"id": "vm_dev", "frame_version": "vm2", "window": meta["window"],
                     "fold_years": years, "dropped": meta["dropped"],
                     "population_rows": meta["population_rows"],
                     "id": "matrix mlbam_id, as the base V2 reads it on this frame"},
           "coverage": {}, "parity": {}, "arms": {}}
    key = f"{H.V2_SCREEN_PREFIX}cand"
    for s in F.SIDES:
        data = H.matrix_training_rows(s)
        raw = json.loads(H._matrix_path(s).read_text(encoding="utf-8"))
        raw_by_key = {r["player_key"]: r for r in raw}
        reads = vm_reads(s, data, raw_by_key)
        side_rows = [c for c in rows if c["side"] == s]
        base, _f0 = vm_orders(s, data, weights, years)
        mism = sum(1 for c in side_rows
                   if base.get(c["key"]) is None
                   or abs(base[c["key"]] - float(c["grades"][DR.V2_KEY])) > 1e-9)
        out["parity"][s] = {"rows": len(side_rows), "mismatched_base_order": mism}
        if mism:
            raise RuntimeError(f"vm base parity failed on {s}: {mism} rows")
        scored = {c["key"] for c in side_rows}
        dy = {d["player_key"]: int(d["decision_year"]) for d in data
              if int(d["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR}
        out["coverage"][s] = {
            "train_rows": coverage({(dy[k], k): p for k, p in reads.items()}),
            "scored_rows": coverage({(dy[k], k): p for k, p in reads.items() if k in scored})}
        for arm in [a for a in arms if a["side"] == s]:
            t1 = time.time()
            vals = {k: transformed(arm["stat"], p.get(arm["stat"])) for k, p in reads.items()}
            cand, folds = vm_orders(s, data, weights, years, head=arm["head"], key=key,
                                    values=vals)
            blk = W2M._vm_block(side_rows, cand, B=B)
            blk["note"] = NOTE
            out["arms"][arm["name"]] = {
                "name": arm["name"], "side": s, "head": arm["head"], "folds": folds,
                "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
                "n_folds": len(folds), "frame": blk}
            w = blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            vc = blk["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
            log(f"  vm {arm['name']}: admitted "
                f"{out['arms'][arm['name']]['admitted_folds']}/{len(folds)}, within vs V2 "
                f"{w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
                f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out


def _git(*args) -> str | None:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _write(doc: dict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if chr(0x2014) in text or chr(0x2013) in text:
        raise ValueError("an em or en dash reached the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)


def table_receipt(path: Path = TABLE_PATH) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"path": "data/_labs/efv_w2/milb_il_stints.json", "sha256": _sha(path),
            "n_stints": doc["n_stints"], "n_persons": doc["n_persons"],
            "orphan_activations": doc["orphan_activations"],
            "per_placed_year": doc["per_placed_year"], "source": doc["source"]}


def construction() -> dict:
    return {"columns": list(COLUMNS), "transform": TRANSFORM,
            "lookback_seasons": LOOKBACK_SEASONS,
            "season_window": "1 April to 30 September",
            "severe_lists": sorted(SEVERE_LISTS), "close_codes": sorted(CLOSE_CODES),
            "recurrent_min": RECURRENT_MIN,
            "as_of": ("facts announced strictly before the cutoff: V-01-01 on a list "
                      "vintage (efv_drivers.protection_asof rule); the earlier of the "
                      "matrix cutoff and 1 January of the decision year on a matrix row"),
            "id": ("list vintage: the outcome-blind mlbam_id (efv_identity), never "
                   "record_mlbam_id; matrix row: the matrix id, as base V2 reads it"),
            "missing": ("no id: None on every column (imputed at the fold's has-block "
                        "mean by the lab); il_absent is a DS-03 balance probe only")}


def dev_read(*, B: int | None = None, out: Path = OUT_PATH, log=print) -> dict:
    """The ground-truth re-run, then the development read of every arm on lv_dev and
    vm_dev; writes the artifact (a spent block already there is kept)."""
    import efv_labels as L
    import efv_v2_model as H
    import efv_v2_stat as S
    _tools()
    import efv_screen_lab as LAB
    B = S.B_DEFAULT if B is None else int(B)
    LAB.guards()
    t0 = time.time()
    prev = json.loads(Path(out).read_text(encoding="utf-8")) if Path(out).exists() else {}
    doc = {"schema": 1, "item": ITEM,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "produced_by": TOOL, "wave": WAVE, "role": "development",
           "adjudicates": False, "selects": False, "exploratory": False, "note": NOTE,
           "owner_decision": ("EW2-8 to EW2-12 (2026-10-08): new sources only; choose on "
                              "development frames only; the reserved frames are spent"),
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "id": LAB.label_id()},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool": TOOL,
                    "module_sha256": _sha(Path(__file__)),
                    "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py")},
           "assembly_sha256": _sha(H.ASSEMBLY_PATH),
           "estimator": {"name": "E_cond", "B": B, "seed": S.SEED_DEFAULT,
                         "clusters": "player", "statistic": S.STAT_LABEL[S.PRIMARY]},
           "construction": construction(), "stint_table": table_receipt(),
           "arms_declared": [{k: a[k] for k in ("name", "stat", "side", "head")}
                             for a in ARMS],
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "lv_folds": list(LAB.FOLDS), "anchor_gate_grouping": False}}
    doc["ground_truth_rerun"] = ground_truth_rerun()
    log(f"ground truth: {json.dumps({s: (b['debuted_rows'], b['rows_with_il_pre'], b['stints_pre']) for s, b in doc['ground_truth_rerun']['sides'].items()})}")
    doc["lv_dev"] = lv_read(ARMS, B=B, log=log)
    doc["vm_dev"] = vm_read(ARMS, B=B, log=log)
    if prev.get("spent"):
        doc["spent"] = prev["spent"]
    doc["summary"] = summary(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    _write(doc, out)
    log(f"wrote {out} in {doc['elapsed_s']} s")
    return doc


# ---------------------------------------------------------------------------
# the spent read: R-LV and R-VM, read once on 2026-10-08 under the owner's waiver
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def registered_v3_columns():
    """This family's arms as efv_v3.W2_COLUMNS entries for the life of the block (the
    v3 machinery's own "add" path), removed afterwards; efv_v3.py is not edited."""
    import efv_v2_model as H
    import efv_v3 as V3
    added = []
    try:
        for a in ARMS:
            if a["name"] in V3.W2_COLUMNS:
                raise RuntimeError(f"{a['name']} already in efv_v3.W2_COLUMNS")
            V3.W2_COLUMNS[a["name"]] = {"side": a["side"], "head": a["head"],
                                        "module": MODULE, "arg": a["stat"],
                                        "key": f"{H.V2_SCREEN_PREFIX}{a['name']}"}
            added.append(a["name"])
        yield V3.W2_COLUMNS
    finally:
        for n in added:
            V3.W2_COLUMNS.pop(n, None)


def build_reserved_capturing(gate_sha: str, *, log=print):
    """tools/efv_v3_backtest.build_reserved at V2 (base_config), with the frame rows it
    builds kept so each training and test row can be read on its own id."""
    _tools()
    import efv_v2_assemble as ASM
    import efv_v3 as V3
    import efv_v3_backtest as BT
    got = {"dev": None, "res": {}}
    orig_bf, orig_fb = ASM.build_frames, F.build_frame

    def bf(*a, **k):
        got["dev"] = orig_bf(*a, **k)
        return got["dev"]

    def fb(side, V, **k):
        rows = orig_fb(side, V, **k)
        got["res"][(side, int(V))] = rows
        return rows
    ASM.build_frames, F.build_frame = bf, fb
    try:
        inp = BT.build_reserved(V3.base_config(), gate_sha=gate_sha, log=log)
    finally:
        ASM.build_frames, F.build_frame = orig_bf, orig_fb
    return inp, got


def spent_values(inp, got: dict, *, gate_sha: str) -> tuple[dict, dict]:
    """({fid: {side: {arm name: {(year, key, kind): value}}}}, coverage) on the reserved
    frames' training and test rows."""
    import efv_v2_model as H
    cols: dict = {"lv_res": {s: {} for s in F.SIDES}, "vm_pros": {s: {} for s in F.SIDES}}
    cov: dict = {"lv_res": {}, "vm_pros": {}}
    for s in F.SIDES:
        frames_lv = {V: (rows, None) for V, (rows, _l) in (got["dev"] or {}).get(s, {}).items()}
        for (side, V), rows in got["res"].items():
            if side == s:
                frames_lv[int(V)] = (rows, None)
        reads = lv_reads(s, {s: frames_lv}, gate_sha=gate_sha)
        res_reads = {k: p for k, p in reads.items() if k[0] in F.RESERVED_LV}
        cov["lv_res"][s] = coverage(res_reads)
        raw = json.loads(H._matrix_path(s).read_text(encoding="utf-8"))
        vm_r = vm_reads(s, H.matrix_training_rows(s), {r["player_key"]: r for r in raw},
                        allow_reserved=True)
        Y = F.R_VM_FIRST_DEBUT_YEAR
        te_keys = {c["key"] for c in inp.frames["vm_pros"]["by_side"][s][Y]["scored"]}
        cov["vm_pros"][s] = coverage({(Y, k): vm_r[k] for k in te_keys if k in vm_r})
        for a in [x for x in ARMS if x["side"] == s]:
            st = a["stat"]
            lv_v, vm_v = {}, {}
            for V, blk in inp.frames["lv_res"]["by_side"][s].items():
                for kind in ("train", "test"):
                    for r in blk[kind]:
                        y = int(r["decision_year"])
                        lv_v[(y, r["player_key"], kind)] = transformed(
                            st, (reads.get((y, r["player_key"])) or {}).get(st))
            for _y, blk in inp.frames["vm_pros"]["by_side"][s].items():
                for kind in ("train", "test"):
                    for r in blk[kind]:
                        y = int(r["decision_year"])
                        vm_v[(y, r["player_key"], kind)] = transformed(
                            st, (vm_r.get(r["player_key"]) or {}).get(st))
            cols["lv_res"][s][a["name"]] = lv_v
            cols["vm_pros"][s][a["name"]] = vm_v
    return cols, cov


def spent_read(gate_sha: str, *, B: int | None = None, out: Path = OUT_PATH,
               log=print) -> dict:
    """Every arm on R-LV and R-VM against the V2 base and PROSPX consensus (E_cond
    CI95), labelled SPENT_LABEL. Written into the artifact's `spent` block only; never
    a progress-ledger row; nothing is chosen on it."""
    import efv_v2_stat as S
    import efv_v3 as V3
    _tools()
    import efv_v3_backtest as BT
    B = S.B_DEFAULT if B is None else int(B)
    if not F.gate_sha_committed(gate_sha):
        raise F.ReservedFrameError(f"{gate_sha!r} is not the committed registration")
    t0 = time.time()
    inp, got = build_reserved_capturing(gate_sha, log=log)
    parity = BT.assert_v3_base_parity(inp, BT.FRAMES_RES)
    log(f"reserved frames built, V2 base parity {parity} ({time.time() - t0:.0f} s)")
    blk_out = {"label": SPENT_LABEL, "role": "spent", "selects": False,
               "adjudicates": False, "chooses_nothing": True,
               "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "gate": {"doc": F.GATE_DOC, "sha": gate_sha, "guards": inp.guards},
               "label_id": inp.label, "base_parity": parity,
               "estimator": {"name": "E_cond", "B": B, "seed": BT.SEED,
                             "clusters": "player"},
               "frames": {}, "arms": {}}
    with registered_v3_columns():
        cols, cov = spent_values(inp, got, gate_sha=gate_sha)
        inp.cols = cols
        base_rows = {fid: inp.rows_with(fid, inp.orders(fid, V3.base_config())[0])
                     for fid in BT.FRAMES_RES}
        for fid in BT.FRAMES_RES:
            blk_out["frames"][fid] = {
                "n_by_side": BT._n_side(base_rows[fid]), "coverage": cov[fid],
                "efv_v2_base_vs_prospx_consensus": {
                    s: BT.paired([c for c in base_rows[fid] if c["side"] == s],
                                 BT.V2_KEY, BT.CONS, "within", B=B)
                    for s in F.SIDES}}
        for a in ARMS:
            t1 = time.time()
            cfg = V3.base_config()
            cfg["add"][a["side"]][a["head"]].append(a["name"])
            V3.validate_config(cfg)
            key = V3.W2_COLUMNS[a["name"]]["key"]
            arm_out = {"name": a["name"], "side": a["side"], "head": a["head"],
                       "label": SPENT_LABEL, "frames": {}}
            for fid in BT.FRAMES_RES:
                orders, rec = inp.orders(fid, cfg, sides=(a["side"],))
                rows = inp.rows_with(fid, orders, sides=(a["side"],))
                hk = "skill_keys" if a["head"] == "skill" else "timing_keys"
                folds = {f: {"admitted": key in (r.get(hk) or []),
                             "head_keys": r.get(hk), "consensus_only": r["consensus_only"]}
                         for f, r in rec.items()}
                legs = {}
                for name, b_key in (("candidate_vs_efv_v2_base", BT.V2_KEY),
                                    ("candidate_vs_prospx_consensus", BT.CONS)):
                    legs[name] = {("spearman" if st == "within" else st):
                                  BT.paired(rows, BT.V3_KEY, b_key, st, B=B)
                                  for st in ("within", "pooled", "auc")}
                arm_out["frames"][fid] = {
                    "n": len(rows), "folds": folds,
                    "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
                    "n_folds": len(folds), "deltas": legs, "label": SPENT_LABEL}
                w = legs["candidate_vs_efv_v2_base"]["spearman"]
                vc = legs["candidate_vs_prospx_consensus"]["spearman"]
                log(f"  {fid} {a['name']}: admitted {arm_out['frames'][fid]['admitted_folds']}"
                    f"/{len(folds)}, vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus "
                    f"{vc.get('delta')} {vc.get('ci95')} ({time.time() - t1:.0f} s)")
            blk_out["arms"][a["name"]] = arm_out
    blk_out["elapsed_s"] = round(time.time() - t0, 1)
    doc = json.loads(Path(out).read_text(encoding="utf-8")) if Path(out).exists() else {}
    doc["spent"] = blk_out
    doc["summary"] = summary(doc)
    _write(doc, out)
    log(f"wrote the spent block into {out} in {blk_out['elapsed_s']} s")
    return doc


# ---------------------------------------------------------------------------
# summary and the progress ledger (development rows only)
# ---------------------------------------------------------------------------

def summary(doc: dict) -> list[dict]:
    """One line per arm: per frame rows, admitted folds, within delta vs V2 and vs
    consensus with CI95 (spent frames carry SPENT_LABEL). Copies only."""
    out = []
    for arm in doc.get("arms_declared") or [{k: a[k] for k in ("name", "stat", "side", "head")}
                                            for a in ARMS]:
        n = arm["name"]
        row = {"arm": n, "side": arm["side"], "head": arm["head"], "stat": arm["stat"]}
        for fid in ("lv_dev", "vm_dev"):
            a = ((doc.get(fid) or {}).get("arms") or {}).get(n)
            if not a:
                continue
            d = a["frame"]["deltas"]
            v2 = d["candidate_vs_efv_v2_base"]["spearman"]
            vc = d["candidate_vs_prospx_consensus"]["spearman"]
            row[fid] = {"n": a["frame"]["n"],
                        "admitted_folds": f"{a['admitted_folds']}/{a['n_folds']}",
                        "vs_v2": [v2.get("delta"), v2.get("ci95")],
                        "vs_consensus": [vc.get("delta"), vc.get("ci95")]}
        sp = (((doc.get("spent") or {}).get("arms") or {}).get(n) or {}).get("frames") or {}
        for fid, f in sp.items():
            v2 = f["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            vc = f["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
            row[fid] = {"n": f["n"], "label": SPENT_LABEL,
                        "admitted_folds": f"{f['admitted_folds']}/{f['n_folds']}",
                        "vs_v2": [v2.get("delta"), v2.get("ci95")],
                        "vs_consensus": [vc.get("delta"), vc.get("ci95")]}
        out.append(row)
    return out


def ledger_docs(doc: dict) -> list[dict]:
    """One development document per (arm, development frame) in the shape
    efv_progress.build_dev_rows reads. The spent block never becomes a row."""
    out = []
    for arm in doc.get("arms_declared") or []:
        for fid in ("lv_dev", "vm_dev"):
            a = ((doc.get(fid) or {}).get("arms") or {}).get(arm["name"])
            if not a:
                continue
            out.append({"role": "development",
                        "model_id": f"{MODEL_PREFIX}{arm['name']}:{arm['side']}",
                        "generated_at": doc.get("generated_at"),
                        "label": doc.get("label") or {}, "code": doc.get("code") or {},
                        "screening": {"wave": f"{WAVE} ({fid})", "exploratory": False,
                                      "development_only": True, "adjudicates": False,
                                      "selects": False, "head": arm["head"],
                                      "statistic_column": arm["stat"],
                                      "admitted_folds": a["admitted_folds"],
                                      "n_folds": a["n_folds"]},
                        "frames": {fid: a["frame"]}})
    return out


def update_ledger(doc: dict | None = None, *, path: Path = OUT_PATH, ledger_path=None,
                  out_path=None, trigger: str = "efv_change") -> dict:
    """Append this module's development rows (and only them) to data/efv_progress.json
    through efv_progress.build_dev_rows and commit_rows. Idempotent."""
    import efv_progress as P
    doc = doc if doc is not None else json.loads(Path(path).read_text(encoding="utf-8"))
    now_dt = datetime.now(timezone.utc)
    now_iso = P._now_iso(now_dt)
    src = [{"path": P._rel(Path(path)), "generated_at": doc.get("generated_at"),
            "sha256": _sha(path)}]
    cands = []
    for d in ledger_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now_dt.date().isoformat(),
                                  trigger=trigger, now_iso=now_iso,
                                  frames=tuple(d["frames"]), raters=P.SCREEN_RATERS,
                                  deltas=P.SCREEN_DELTAS, statistic_fields=True)
    if not cands:
        return {"appended": [], "status": "no development rows"}
    res = P.commit_rows(cands, out_path=out_path, ledger_path=ledger_path,
                        sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--build-table", action="store_true", help="parse the cached feed")
    ap.add_argument("--ground-truth", action="store_true", help="print the trigger re-run")
    ap.add_argument("--dev-read", action="store_true", help="the development read")
    ap.add_argument("--spent-read", action="store_true", help="the spent-frame read")
    ap.add_argument("--gate-sha", default="", help="the committed gate sha (spent read)")
    ap.add_argument("--ledger", action="store_true",
                    help="append this module's development rows from the artifact")
    ap.add_argument("--ledger-path", default=None,
                    help="durable ledger path (default: efv_progress's own)")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args()
    if a.build_table:
        t0 = time.time()
        d = build_table()
        print(json.dumps({k: v for k, v in d.items() if k not in ("rows", "source")},
                         indent=1), f"{time.time() - t0:.1f} s")
    if a.ground_truth:
        print(json.dumps(ground_truth_rerun(), indent=1))
    if a.dev_read:
        print(json.dumps(dev_read(B=a.B, out=Path(a.out))["summary"], indent=1))
    if a.spent_read:
        if not a.gate_sha:
            ap.error("--spent-read needs --gate-sha")
        print(json.dumps(spent_read(a.gate_sha, B=a.B, out=Path(a.out))["summary"], indent=1))
    if a.ledger:
        print(json.dumps(update_ledger(path=Path(a.out), ledger_path=a.ledger_path),
                         indent=1))
