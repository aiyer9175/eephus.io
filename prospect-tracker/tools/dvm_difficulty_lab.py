# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DvM+ development-difficulty lab: the frame (DVM-1) and the study (DVM-3).

DVM-3 (the second half of this file) builds what docs/dvm-difficulty-2026-09-30/
DVM_DIFFICULTY_GATE.md registers: the pairs and their censoring (section 3), the
expectation model with its shrunk interaction cells and floored spreads (section 5), the
row credits DV and D0 and the 60 to 70 against 40 to 50 ratio (section 6), the club
aggregation with the fallback tenure split (section 7), tools (section 8), the player index
(section 9), H1 (section 10), H2 (section 11), the validation arms C0, DV and D0 and the
decision rule (section 13), and the guards of sections 14 and 15. Every statistic is a
pure function of the rows it is handed. Only run_look() reads the store, and it passes the
clock first: it refuses before its registered date, on a registered look day, before the
PROSPECT_ANCHOR look record, while a pipeline or a test session runs, and a second scored
look (it re-prints the stored result instead). data/dvm_difficulty.json and
data/dvm_difficulty_eval.json are written by the look and by nothing else. Before the look,
--dry-run runs the whole reporting path on synthetic fixtures with nulls into a directory
of the caller's choosing.

The frame module (DVM-1) below is COUNTS ONLY.

Owner ask 6 (2026-09-30): weight DvM+ by how hard a grade move is to make, by origin
group (high school, college, international) and by starting grade. The design is the
Part 8 dvm_difficulty lane (dvm_difficulty.md: Part B, Part C.1 to C.4, the frame rules
F-R1 to F-R5 in C.2, the preconditions P-2 to P-4 in D.7). Owner answers Q-DVM-1 (A,
exclude the reserved 2020-2021 lists until the R-LV look record exists) and Q-DVM-4 (A,
each source's own grades, list to list) bind here.

WHAT A FRAME ROW IS. One same-source pair slot (player p, source s, start list year V,
horizon h in {1, 2}): s's latest active preseason read of p in V, where s also
published a preseason list in V + h. The preseason read rule is
efv_vintage_frame.window_bounds: the read is inside [V-01-01, min(V-05-01, debut)), with
the debut day read as efv_dataset.debut_day_for_cutoff reads it (a placeholder day moves
back to the season start). International boards, overseas boards and graduate lists are
not preseason lists. A source with no preseason list in V + h puts the slot out of frame.

WHAT THIS MODULE PUBLISHES. Counts only: preseason reads per source and list year, frame
list slots (the source published both lists) and completed same-source pairs by
source, side and start year (never by grade rung), origin coverage of the frame's START reads by side and rung (the reads are
inputs), the unknown-origin share and the P-2 check, the FanGraphs-against-acquisitions
disagreement table, level and age coverage from the outcome-blind identity by side
and list year, and the registration's power block (start reads x the pooled completion
share of the horizon, at an ASSUMED base rate and spread). It computes no grade difference, no growth statistic, no rate by rung, no
WAR, no debut or graduation quantity. A completed-pair count is never crossed with a
grade rung (that would be a completion rate by rung, F-R4).

THE FRAME RULES, ENFORCED HERE.
  F-R1  no read in list year 2020 or 2021 is loaded (EFV_V2_GATE R-LV) until the R-LV
        look record exists: excluded_list_years() is the switch, and RLV_LOOK_RECORD
        (the commit that records that look) lifts it. Amendment A-2 of the gate
        (2026-10-14) sets it to the R-LV read of 2026-10-08 (EFV_V2_GATE section 11,
        data/_labs/efv_v3/efv_v3_confirm.json); a caller that passes rlv_record=None
        still gets the exclusion (Q-DVM-1 A).
  F-R2  a debut-year preseason read of a player who debuted in 2025 or later (an R-VM
        input grade) is never loaded, and a slot whose end read would be one leaves the
        frame.
  F-R3  build_frame() refuses until the ETA_FG_BLEND_GATE look is recorded (a verdict or
        a VOID in its section 8), because the 2024 and 2025 start reads sit on that
        gate's frame; assert_growth_allowed() is the gate every growth computation must
        pass, and it also refuses until the DvM+ difficulty gate is registered.
  F-R4  no WAR, no label module, no career_war, no rate by rung; the module reads
        snapshots, players' positions, acquisitions, draft and overseas tables, the
        debut day, and the minor league caches through the outcome-blind identity.
  F-R5  no eFV input: no retrospective eFV series, no model score; the grades are the
        sources' own printed grades.
test_dvm_difficulty_frame.py pins each rule, including an AST scan of this file.

ORIGIN. Per player, first rule that classifies wins: the list-printed origin
(FanGraphs signed_from and sign_market), draft data (draft_players.player_type through
draft_canonical_keys), the overseas tables and acquisitions (method, then the school
token), the parsed MLB Pipeline report text, and the age rule last (draft year minus
birth year at least 21 means college, read from the list-printed age or the minor league
baseball age; never players.birth_date, which was attached mostly on reaching the
majors). International signees signed at 21 or older, or from NPB, KBO or CPBL, are
pro/overseas.

LEVEL AND AGE. From efv_identity's outcome-blind resolution (printed name, V, side;
never the record's stored id or birth date): the primary level of the last minor league
season before V and the baseball age in that season, falling back to the age the list
printed. A read with no minor league line is pre-pro.

THE 2026 MLB PIPELINE PRESEASON LIST (P-4). The store holds 48 reads of it (the team
lists were re-dated in place by the in-season runs), so the 2025 to 2026 step is
declared FanGraphs and Baseball America only: PIPELINE_2026_PRESEASON_DECLARED_ABSENT.

Run from prospect-tracker/:
  python tools/dvm_difficulty_lab.py --freeze
      back up prospects.db with the SQLite backup API into .cache/dvm_difficulty/
  python tools/dvm_difficulty_lab.py --counts OUT_DIR
      build the frame on the frozen copy and write frame_counts.json and
      frame_counts.txt into OUT_DIR (and a copy under .cache/dvm_difficulty/)
  python tools/dvm_difficulty_lab.py --dry-run OUT_DIR
      the whole reporting path on synthetic fixtures with nulls; writes only OUT_DIR
  python tools/dvm_difficulty_lab.py --look TASK_DIR
      THE ONE LOOK (gate section 14); refuses before its clock and a second scored look
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_identity as ID  # noqa: E402  outcome-blind name resolution (DS-03)
import milb_history as mh  # noqa: E402

CACHE_DIR = ROOT / ".cache" / "dvm_difficulty"
FROZEN_DB = "prospects_frozen.db"
FROZEN_RECEIPT = "prospects_frozen.json"
DATA_DIR = ROOT / "data"


def _rel(p) -> str:
    """A receipt path relative to the module root when it sits under it, so a published
    artifact names no build-machine path (test_published_payload_hygiene.py)."""
    try:
        return Path(p).absolute().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(p).name

ETA_GATE_DOC = "docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md"
DVM_GATE_DOC = "docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md"

#: The graders whose own list-to-list moves the study reads (Q-DVM-4 A).
SOURCES: tuple[str, ...] = ("mlb_pipeline", "fangraphs", "baseballamerica")
#: The preseason window (efv_vintage_frame.window_bounds; parity pinned in the tests).
WINDOW_START_MMDD = "-01-01"
WINDOW_END_MMDD = "-05-01"
#: interval_label tokens that are not preseason prospect lists.
NON_LIST_TOKENS: tuple[str, ...] = ("int'l", "overseas", "graduates")
#: A source published a preseason list in V when it holds at least this many reads.
MIN_LIST_READS = 100
#: P-4: the 2026 MLB Pipeline preseason list is not in the store (48 reads).
PIPELINE_2026_PRESEASON_DECLARED_ABSENT = True
HORIZONS: tuple[int, ...] = (1, 2)

#: R-LV (efv_vintage_frame.RESERVED_LV; parity pinned in the tests).
RESERVED_LV: frozenset[int] = frozenset({2020, 2021})
#: The 40-hex sha of the commit that records the R-LV look in EFV_V2_GATE.md. None until
#: that look is recorded; while None, F-R1 holds (Q-DVM-1 A). Gate amendment A-2
#: (2026-10-14): the R-LV read of 2026-10-08 under decision EW2-6, recorded in
#: EFV_V2_GATE.md section 11 and data/_labs/efv_v3/efv_v3_confirm.json by this commit.
RLV_LOOK_RECORD: str | None = "1c73c420ad68bc6a8061859c6e82757589ef20c6"
#: Where amendment A-2 reads that record: EFV_V2_GATE.md section 11 names the artifact
#: (its section 9 stays empty by section 11.2's own words), and the artifact exists.
RLV_RECORD_SECTION = "11"
RLV_RECORD_ARTIFACT = "data/_labs/efv_v3/efv_v3_confirm.json"
#: R-VM (efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR; parity pinned in the tests).
R_VM_FIRST_DEBUT_YEAR = 2025
#: The debut day a placeholder moves back to (efv_dataset.SEASON_START_MMDD).
SEASON_START_MMDD = "-04-01"

#: P-2 (dvm_difficulty.md D.7): unknown origin share ceilings.
P2_MAX_UNKNOWN_OVERALL = 0.05
P2_MAX_UNKNOWN_CELL = 0.10

RUNGS: tuple[str, ...] = ("<=35", "40", "45", "50", "55", "60", "65+")
SIDES: tuple[str, ...] = ("hit", "pit")
ORIGINS: tuple[str, ...] = ("HS", "COL", "JUCO", "IFA", "PRO", "UNK")
ROUTES: tuple[str, ...] = ("fg_print", "draft_type", "overseas", "acquisitions",
                           "pipeline_text", "age_rule", "pro_entry", "none")

PITCHER_TOKENS = frozenset({"RHP", "LHP", "P", "SP", "RP", "MIRP", "SIRP", "RHSP",
                            "LHSP", "RHRP", "LHRP"})

#: Minor league levels and the band the frame reads (dvm_difficulty.md C.4).
LEVEL_BAND = {"DSL": "DSL/CPX", "CPX": "DSL/CPX", "A": "A/A+", "A+": "A/A+",
              "AA": "AA/AAA", "AAA": "AA/AAA"}
LEVEL_RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
#: efv_dataset._TYPICAL_LEVEL_AGE (parity pinned in the tests).
TYPICAL_LEVEL_AGE = {"DSL": 18.0, "CPX": 19.0, "A": 20.0, "A+": 21.0, "AA": 22.5,
                     "AAA": 24.0}
AGE_REL_BOUND = 3.0
MIN_EXPOSURE = {"hit": 50.0, "pit": 60.0}
SIDE_GROUP = {"hit": "hitting", "pit": "pitching"}
EXPOSURE_FIELD = {"hitting": "pa", "pitching": "bf"}
FIRST_MILB_SEASON = 2005

IFA_COUNTRIES = frozenset({
    "dominican republic", "dominican", "dominican republlic", "venezuela", "cuba",
    "mexico", "panama", "colombia", "curacao", "aruba", "bahamas", "nicaragua",
    "brazil", "japan", "south korea", "korea", "taiwan", "australia", "netherlands",
    "germany", "italy", "czech republic", "south africa", "honduras", "haiti",
    "lithuania", "spain", "france", "uganda", "china", "philippines", "new zealand",
    "great britain", "united kingdom", "russia", "peru", "guatemala", "el salvador",
    "jamaica", "st. maarten", "sint maarten", "saint maarten", "u.s. virgin islands",
    "virgin islands", "bonaire", "hong kong", "austria", "sweden", "poland", "ukraine",
    "belgium", "denmark", "israel", "ghana", "nigeria", "zimbabwe", "argentina", "chile",
    "ecuador", "bolivia", "canada", "costa rica", "belize", "guam", "pakistan",
    "india", "venezuala",
})
PRO_COUNTRIES = frozenset({"japan", "south korea", "korea", "taiwan"})
IFA_MARKETS = frozenset({"J2", "Intl15", "International"})
PRO_SIGN_AGE = 21.0
#: The house HS-or-college rule (efv_dataset, tools/efv_lab_runner.py): draft year minus
#: birth year at least 21 is college; on a June 30 age that is an age of 20.5 or more.
AGE_RULE_COLLEGE_AT = 20.5

_HS_RE = re.compile(r"\b(hs|high school|academy|prep|school|schools|secondary|ss|"
                    r"home school(ed)?|homeschool(ed)?)\b", re.I)
_JUCO_RE = re.compile(r"\b(jc|cc|ccc|juco|community college|junior college)\b", re.I)
_COLLEGE_RE = re.compile(r"\b(university|univ|college|state|a&m)\b", re.I)
#: A parenthesized region after the name, e.g. "(TX)" or "(Ontario, CN)": FanGraphs prints
#: high schools this way and colleges without it.
_REGION_RE = re.compile(r"\(([^)]*)\)\s*$")


class ClockError(RuntimeError):
    """A frame build or a growth computation before its registered clock."""


# ---------------------------------------------------------------------------
# clocks and reserved frames
# ---------------------------------------------------------------------------

def _section(text: str, number: str) -> str:
    """The body of the '## <number>.' section of a gate document, '' when absent."""
    out, inside = [], False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            inside = line.startswith(f"## {number}.")
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


_RECORD_RE = re.compile(r"^\s*(\*\*)?(VERDICT:|VOID\b|Verdict[^:\n]*:\s*\**\s*VOID\b)")


def eta_look_recorded(text: str | None) -> bool:
    """True when ETA_FG_BLEND_GATE.md section 8 carries the look's record: a VERDICT
    line or a VOID record (a VOID counts as 'the ETA look record exists')."""
    body = _section(text or "", "8")
    return any(_RECORD_RE.match(ln) for ln in body.splitlines())


def _read_doc(rel: str, root: Path = ROOT) -> str | None:
    p = Path(root) / rel
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def require_eta_record(text: str | None = None) -> None:
    """F-R3: raise ClockError unless the ETA blend look is recorded."""
    if text is None:
        text = _read_doc(ETA_GATE_DOC)
    if not eta_look_recorded(text):
        raise ClockError(
            f"F-R3: {ETA_GATE_DOC} section 8 holds no recorded look (a VERDICT or a "
            "VOID); the difficulty frame reads the 2024 and 2025 listings, so it waits")


def assert_growth_allowed(eta_text: str | None = None,
                          dvm_gate_text: str | None = None) -> None:
    """The gate every growth computation passes first (DVM-3 onward). Refuses before
    the ETA look record exists, and before the DvM+ difficulty gate is registered
    (DVM-2, committed alone before any growth is read). look_frame() passes it before
    the one look; the study's statistics run only on the rows they are handed."""
    require_eta_record(eta_text)
    if dvm_gate_text is None:
        dvm_gate_text = _read_doc(DVM_GATE_DOC)
    status = [ln.strip() for ln in (dvm_gate_text or "").splitlines()
              if ln.strip().startswith("Registration status:")]
    if status != ["Registration status: REGISTERED"]:
        raise ClockError(
            f"{DVM_GATE_DOC} is not REGISTERED; no grade difference or growth statistic "
            "is computed before the registration commits")


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def excluded_list_years(record: str | None = RLV_LOOK_RECORD) -> frozenset[int]:
    """F-R1: the list years no read is loaded from. RESERVED_LV until the R-LV look
    record exists (Q-DVM-1 A); a malformed record keeps the exclusion."""
    if record is None or not _SHA_RE.match(str(record)):
        return RESERVED_LV
    return frozenset()


def is_rvm_input(vintage: int, debut_day: str | None) -> bool:
    """F-R2: the debut-year preseason read of a player who debuted in 2025 or later."""
    if not debut_day:
        return False
    try:
        dy = int(str(debut_day)[:4])
    except ValueError:
        return False
    return dy >= R_VM_FIRST_DEBUT_YEAR and int(vintage) == dy


def window_bounds(vintage: int, debut_day: str | None) -> tuple[str, str]:
    """[start, end) of the V preseason window (efv_vintage_frame.window_bounds)."""
    lo = f"{int(vintage)}{WINDOW_START_MMDD}"
    hi = f"{int(vintage)}{WINDOW_END_MMDD}"
    if debut_day and str(debut_day)[:10] < hi:
        hi = str(debut_day)[:10]
    return lo, hi


# ---------------------------------------------------------------------------
# the frozen store and the input pins
# ---------------------------------------------------------------------------

def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def freeze_db(src: Path = ROOT / "prospects.db", dest_dir: Path = CACHE_DIR) -> dict:
    """Copy the store with the SQLite backup API (a consistent snapshot even if another
    connection is open), then pin it by sha256. Never run while a pipeline writes."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / (FROZEN_DB + ".tmp")
    if tmp.exists():
        tmp.unlink()
    s = sqlite3.connect(f"file:{Path(src).as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(str(tmp))
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    final = dest_dir / FROZEN_DB
    tmp.replace(final)
    receipt = {"source": str(Path(src)), "frozen_at": _now(), "path": str(final),
               "bytes": final.stat().st_size, "sha256": sha256_file(final),
               "method": "sqlite3.Connection.backup"}
    (dest_dir / FROZEN_RECEIPT).write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    return receipt


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir_fingerprint(paths) -> dict:
    """Name, size and mtime fingerprint of a set of cache files (cheap, order-stable)."""
    h = hashlib.sha256()
    n = 0
    for p in sorted(paths):
        st = Path(p).stat()
        h.update(f"{Path(p).name}|{st.st_size}|{int(st.st_mtime)}\n".encode())
        n += 1
    return {"files": n, "fingerprint": h.hexdigest()}


DEBUT_FILES = ("debuts.json", "inactive.json", "timeseries.json")
REDATES_FILE = "debut_redates.json"


def input_pins(data_dir: Path = DATA_DIR) -> dict:
    out = {}
    for fn in DEBUT_FILES + (REDATES_FILE,):
        p = Path(data_dir) / fn
        out[fn] = sha256_file(p) if p.exists() else None
    out["milb_cache"] = _dir_fingerprint(
        p for p in Path(mh.CACHE_DIR).glob("*.json")
        if re.match(r"^(hitting|pitching)_1[1-6]_\d{4}\.json$", p.name))
    out["draft_history_cache"] = _dir_fingerprint(Path(ID.DRAFT_DIR).glob("*.json")) \
        if Path(ID.DRAFT_DIR).is_dir() else None
    return out


# ---------------------------------------------------------------------------
# debut days (window cut and R-VM only)
# ---------------------------------------------------------------------------

def _load_redates(data_dir: Path) -> dict:
    p = Path(data_dir) / REDATES_FILE
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for pk, r in ((doc or {}).get("rows") or {}).items():
        if r.get("placeholder_date"):
            out[pk] = (r["placeholder_date"],
                       r.get("debut_date") if r.get("status") == "redated" else None)
    return out


def debut_day(rec: dict, redates: dict) -> str | None:
    """efv_dataset.debut_day_for_cutoff on one record: the re-dated real day when it is
    in the same season, and a still-placeholder day moved back to the season start."""
    dd = rec.get("debut_date")
    if not dd:
        return None
    day = str(dd)[:10]
    placeholder = bool(rec.get("debut_date_is_placeholder"))
    rd = redates.get(rec.get("player_key"))
    if rd and day == rd[0]:
        if rd[1] and rd[1][:4] == day[:4]:
            day, placeholder = rd[1][:10], False
        else:
            placeholder = True
    if placeholder:
        day = min(day, f"{day[:4]}{SEASON_START_MMDD}")
    return day


def load_debut_days(data_dir: Path = DATA_DIR) -> dict[str, str]:
    """{player_key: debut day} over the universe files, first file wins (the order
    efv_vintage_frame.load_universe uses). Only the debut fields are read."""
    redates = _load_redates(data_dir)
    out: dict[str, str] = {}
    seen: set[str] = set()
    for fn in DEBUT_FILES:
        p = Path(data_dir) / fn
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        recs = doc if isinstance(doc, list) else (doc.get("players") or [])
        for r in recs:
            pk = r.get("player_key")
            if not pk or pk in seen:
                continue
            seen.add(pk)
            d = debut_day({"player_key": pk, "debut_date": r.get("debut_date"),
                           "debut_date_is_placeholder": r.get("debut_date_is_placeholder")},
                          redates)
            if d:
                out[pk] = d
    return out


# ---------------------------------------------------------------------------
# preseason reads
# ---------------------------------------------------------------------------

def _is_list_label(label: str | None) -> bool:
    lab = (label or "").lower()
    return not any(t in lab for t in NON_LIST_TOKENS)


def _extras(tools_json: str | None) -> dict:
    if not tools_json:
        return {}
    try:
        return (json.loads(tools_json) or {}).get("_extras") or {}
    except (ValueError, AttributeError):
        return {}


def load_reads(con: sqlite3.Connection, debut: dict[str, str], *,
               excluded: frozenset[int]) -> tuple[dict, set]:
    """({(source, player_key, V): read}, rvm_keys). A read is a source's latest active
    read of a player inside his V window, fv and club present, on a prospect list.
    Reads in an excluded list year are skipped before their row is kept (F-R1); an R-VM
    input keeps only its key, never its grade (F-R2)."""
    reads: dict[tuple[str, str, int], dict] = {}
    rvm: set[tuple[str, str, int]] = set()
    q = ("SELECT source, player_key, player_name, snapshot_date, fv, fv_plus, org, "
         "position, interval_label, tools_json FROM snapshots "
         f"WHERE source IN ({','.join('?' * len(SOURCES))}) AND status = 'active' "
         "AND fv IS NOT NULL AND org IS NOT NULL ORDER BY snapshot_date, id")
    for src, pk, name, d, fv, plus, org, pos, label, tj in con.execute(q, SOURCES):
        if not d or len(d) < 10:
            continue
        V = int(d[:4])
        if V in excluded:
            continue
        lo, hi = window_bounds(V, debut.get(pk))
        if not (lo <= d[:10] < hi):
            continue
        if not _is_list_label(label):
            continue
        if is_rvm_input(V, debut.get(pk)):
            rvm.add((src, pk, V))
            continue
        ex = _extras(tj)
        reads[(src, pk, V)] = {
            "date": d[:10], "fv": float(fv), "plus": bool(plus), "org": org,
            "position": pos, "name": name, "age": _num(ex.get("age")),
            "tools": _tool_grades(tj), "present": _present_grades(ex),
        }
    return reads, rvm


def _tool_grades(tools_json: str | None) -> dict[str, float]:
    """The future tool grades a read printed (DVM-3, gate section 8); {} when none."""
    try:
        doc = json.loads(tools_json) if tools_json else {}
    except ValueError:
        return {}
    out = {}
    for k, v in (doc or {}).items():
        if k == "_extras":
            continue
        x = _num(v)
        if x is not None:
            out[k] = x
    return out


def _present_grades(extras: dict) -> dict[str, float]:
    """FanGraphs present tool grades (the future-minus-present gap of section 4)."""
    pres = (extras or {}).get("present")
    if not isinstance(pres, dict):
        return {}
    return {k: x for k, x in ((k, _num(v)) for k, v in pres.items()) if x is not None}


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def published_lists(reads: dict) -> dict[tuple[str, int], int]:
    n: Counter = Counter()
    for (src, _pk, V) in reads:
        n[(src, V)] += 1
    return dict(n)


def is_published(src: str, V: int, counts: dict) -> bool:
    if src == "mlb_pipeline" and V == 2026 and PIPELINE_2026_PRESEASON_DECLARED_ABSENT:
        return False
    return counts.get((src, V), 0) >= MIN_LIST_READS


def grade_rung(fv: float, plus: bool) -> str:
    """The start rung cell: 5 x floor(G / 5) with G = fv + 2.5 x plus."""
    g = float(fv) + (2.5 if plus else 0.0)
    r = int(g // 5 * 5)
    if r <= 35:
        return "<=35"
    if r >= 65:
        return "65+"
    return str(r)


def side_of(position: str | None) -> str | None:
    """hit or pit from the printed position; a two-way player counts as a hitter."""
    if not position:
        return None
    toks = [t.strip().upper() for t in re.split(r"[/,\s]+", str(position)) if t.strip()]
    if not toks:
        return None
    if all(t in PITCHER_TOKENS for t in toks):
        return "pit"
    return "hit"


# ---------------------------------------------------------------------------
# origin
# ---------------------------------------------------------------------------

def _fg_base(signed_from: str | None) -> str:
    base = re.sub(r"\(.*?\)", "", str(signed_from or "")).strip().lower()
    return re.sub(r"\s+", " ", base)


def origin_from_fg(signed_from: str | None, market: str | None,
                   college_names: frozenset[str] = frozenset()) -> str | None:
    """The FanGraphs list-printed origin: HS, COL, JUCO, IFA or PRO (None when blank).
    A junior college token wins, then a high school token, then a college token; a
    name with a parenthesized region and no such token is a high school unless the
    bare name is printed elsewhere as a college (college_names), e.g. "Miami (OH)"."""
    sf = (signed_from or "").strip()
    base = _fg_base(sf)
    if (market or "") in IFA_MARKETS or base in IFA_COUNTRIES:
        return "PRO" if base in PRO_COUNTRIES else "IFA"
    if not sf:
        return None
    if _JUCO_RE.search(sf):
        return "JUCO"
    if _HS_RE.search(sf):
        return "HS"
    if _COLLEGE_RE.search(base):
        return "COL"
    if _REGION_RE.search(sf) and base not in college_names:
        return "HS"
    return "COL"


def fg_college_names(fg_rows: dict) -> frozenset[str]:
    """Bare FanGraphs names printed without a region and without a school token: the
    colleges, which a region suffix does not turn into a high school."""
    out = set()
    for rows in fg_rows.values():
        for _day, sf, mk, _sy, _age in rows:
            s = (sf or "").strip()
            if not s or (mk or "") in IFA_MARKETS or _REGION_RE.search(s):
                continue
            if _HS_RE.search(s) or _JUCO_RE.search(s):
                continue
            b = _fg_base(s)
            if b and b not in IFA_COUNTRIES:
                out.add(b)
    return frozenset(out)


def origin_from_draft_type(ptype: str | None) -> str | None:
    t = (ptype or "").strip().lower()
    if t.startswith("hs"):
        return "HS"
    if t.startswith("col"):
        return "COL"
    return None


def origin_from_school(school: str | None) -> str | None:
    s = (school or "").strip()
    if not s:
        return None
    if _HS_RE.search(s):
        return "HS"
    if _JUCO_RE.search(s):
        return "JUCO"
    return "COL"


_NATIONALITY = (r"dominican|venezuelan|cuban|mexican|panamanian|colombian|curacaoan|"
                r"aruban|bahamian|nicaraguan|brazilian|taiwanese|japanese|korean|"
                r"australian|dutch|german|italian|haitian|honduran|lithuanian|"
                r"south african|guatemalan|peruvian|chinese")
_COUNTRY = (r"the dominican republic|dominican republic|venezuela|cuba|mexico|panama|"
            r"colombia|cura[cç]ao|aruba|the bahamas|bahamas|nicaragua|brazil|taiwan|"
            r"japan|south korea|korea|australia|the netherlands|netherlands|germany|italy|"
            r"haiti|honduras|lithuania|south africa|guatemala|peru|china|spain")
_T_PRO = re.compile(r"\b(NPB|KBO|CPBL|Nippon Professional|Pacific League|Central League|"
                    r"Korea Baseball Organization|Chinese Professional Baseball|"
                    r"Serie Nacional|Cuban National Series|posted by|posting system)\b")
_T_IFA = re.compile(
    r"(\bout of (" + _COUNTRY + r")\b"
    r"|\bfrom (" + _COUNTRY + r")\b[^.]{0,60}\bsign"
    r"|\bsign\w*\b[^.]{0,80}\b(" + _NATIONALITY + r")\b"
    r"|\b(" + _NATIONALITY + r")\b[^.]{0,60}\b(signee|signed|sign)\b"
    r"|\binternational (amateur|free agent|signing|signee|bonus|period|class|market|"
    r"program|scouting)"
    r"|\bjuly 2\b|\bJ2\b|\b1[5-7]-year-old\b[^.]{0,60}\bsign"
    r"|\bsign\w*\b[^.]{0,60}\b(at|as a) 1[5-7]\b|\bdefect)", re.I)
#: International markers that do not depend on a signing verb: a nationality before a
#: player noun, a country's native, a first season in the United States, the summer
#: leagues only international signees play in, Latin American scouting.
_T_IFA_STRONG = re.compile(
    r"(\b(" + _NATIONALITY + r") (native|right-hander|left-hander|righty|lefty|hurler|"
    r"pitcher|shortstop|outfielder|infielder|catcher|teenager|prospect|slugger|product|"
    r"switch-hitter|backstop|third baseman|second baseman|first baseman|center fielder|"
    r"right fielder|left fielder|reliever|starter|youngster|import)\b"
    r"|\b(" + _COUNTRY + r") native\b|\bnative of (" + _COUNTRY + r")\b"
    r"|\b(United States|U\.S\.|stateside) debut\b"
    r"|\b(came|arrived|come|coming) (to|in) the (United States|U\.S\.)"
    r"|\b(Dominican|Venezuelan) Summer League\b|\bDSL\b|\bVSL\b"
    r"|\bLatin America(n)?\b)", re.I)
_T_JUCO = re.compile(r"\b(junior college|juco|community college|JC)\b", re.I)
_T_HS = re.compile(r"\b(high school|high-school|high schooler|prep (product|star|ranks|"
                   r"pitcher|shortstop|outfielder|catcher|hitter|bat|arm|right-hander|"
                   r"left-hander|lefty|righty|career|days|level)|out of (a |an )?\w+ prep\b|"
                   r"prepster|from the prep ranks)\b", re.I)
_T_COL = re.compile(r"\b(university|college|collegiate|NCAA|College World Series|"
                    r"Cape Cod|freshman|sophomore|redshirt|(junior|senior) (year|season) "
                    r"at|Division (I|II|III|1|2|3)|NAIA|nondrafted|non-drafted|undrafted|"
                    r"senior sign)\b", re.I)
#: A report that names both a high school and a college describes a high school pick
#: only when it says he signed out of high school instead of going to college.
_T_HS_SIGNED = re.compile(
    r"(signed away from|pried (him )?away from|bypass(ed|ing)? (college|his commitment|a "
    r"commitment)|forg(o|oing|went) (college|his commitment|a commitment|a scholarship)|"
    r"instead of (attending|going to|honoring|heading to|playing at|playing in)|rather than "
    r"(attending|going to|honoring|heading to|playing at)|(passed|passing) (up|on) (a |his )?"
    r"(college|scholarship|commitment)|signed (him )?out of (a |an )?([A-Z][\w.'-]* ){0,3}"
    r"high school|straight out of high school)", re.I)


#: ... and a college player when it says he went to college instead of signing.
_T_COL_ATTENDED = re.compile(
    r"(honor(ed|ing)? (his |a |the |that )?(\w+ )?commitment|went on to (attend|play|pitch|"
    r"star)|opted (to attend|for college)|instead of signing|rather than sign(ing)?|"
    r"didn't sign|did not sign|chose (college|to attend)|turned down|went unsigned|"
    r"elected to attend|(two|three|four) (years|seasons) at)", re.I)
_T_COMMIT = re.compile(r"\bcommit(ment|ted)?\b", re.I)
#: "<Name> product" and "out of <Name>": a name the store prints as a college elsewhere.
_NAMED_SCHOOL = re.compile(
    r"\b(?:the |a )?((?:[A-Z][\w.&'-]*)(?: (?:of |at )?[A-Z][\w.&'-]*){0,4}) product\b"
    r"|\bout of ((?:[A-Z][\w.&'-]*)(?: (?:of |at )?[A-Z][\w.&'-]*){0,4})"
    r"(?! (?:[Hh]igh|HS|[Pp]rep|[Aa]cademy))")


def _named_college(text: str, college_names: frozenset[str]) -> bool:
    if not college_names:
        return False
    for m in _NAMED_SCHOOL.finditer(text):
        name = (m.group(1) or m.group(2) or "").strip().lower()
        name = re.sub(r"^(the|a)\s+", "", name)
        if name in college_names:
            return True
    return False


def origin_from_report(text: str | None,
                       college_names: frozenset[str] = frozenset()) -> str | None:
    """One MLB Pipeline report's origin, or None when it says nothing or says two
    things it cannot settle. Pattern rules only; audited against the list-printed
    origin by the disagreement table. `college_names` are names the store prints as
    colleges (FanGraphs names and drafted-from schools), read in "<Name> product" and
    "out of <Name>"."""
    t = (text or "").strip()
    if not t:
        return None
    if _T_PRO.search(t):
        return "PRO"
    strong_ifa = bool(_T_IFA_STRONG.search(t))
    ifa = strong_ifa or bool(_T_IFA.search(t))
    juco = bool(_T_JUCO.search(t))
    hs = bool(_T_HS.search(t))
    col = bool(re.search(_T_COL.pattern, re.sub(_T_JUCO.pattern, " ", t, flags=re.I),
                         re.I)) or _named_college(t, college_names)
    drafted = bool(re.search(r"\b(drafted|-rounder|first-round|supplemental|"
                             r"(?<!Rule 5 )Draft)\b", t, re.I))
    if ifa and not (hs or col or juco or drafted):
        return "IFA"
    if strong_ifa and not (hs or col or juco):
        return "IFA"
    if ifa:
        return None
    if juco:
        return "JUCO"
    if hs and not col:
        # "honored his commitment ... after high school": a college player whose
        # school the store does not print as a college
        if _T_COL_ATTENDED.search(t) and not _T_HS_SIGNED.search(t):
            return "COL"
        return "HS"
    if col and not hs:
        return "COL"
    if hs and col:
        if _T_HS_SIGNED.search(t):
            return "HS"
        if _T_COL_ATTENDED.search(t):
            return "COL"
        return "HS" if _T_COMMIT.search(t) else "COL"
    return None


def _yearfrac(day: str) -> float:
    try:
        d = datetime.strptime(day[:10], "%Y-%m-%d")
    except ValueError:
        return float(day[:4]) + 0.5
    return d.year + (d.timetuple().tm_yday - 1) / 365.25


def age_rule(draft_year: int | None, ages: list[tuple]) -> str | None:
    """HS or COL from the age at the June 30 of the draft year. `ages` holds
    ("decimal", age, read_day) for a decimal list-printed age, ("int", age, season)
    for an integer age in a season (list-printed or the minor league baseball age).
    Decimal: 20.5 or older is college (draft year minus birth year at least 21).
    Integer (a floor age): 20 or older is college, 19 or younger is high school; a
    floor age of 20 is 20.0 to 20.99, where college draftees outnumber high school
    ones about four to one on the list-printed origin."""
    if not draft_year:
        return None
    D = int(draft_year)
    for kind, age, when in ages:
        if kind == "decimal":
            a = float(age) + (D + 0.5 - _yearfrac(str(when)))
            return "COL" if a >= AGE_RULE_COLLEGE_AT else "HS"
    votes = set()
    for kind, age, when in ages:
        if kind != "int":
            continue
        a = int(age) - (int(when) - D)
        if a >= 20:
            votes.add("COL")
        elif a <= 19:
            votes.add("HS")
    return votes.pop() if len(votes) == 1 else None


def load_origin_evidence(con: sqlite3.Connection, debut: dict[str, str], *,
                         excluded: frozenset[int]) -> dict:
    """Every origin input the store holds, keyed by player_key. Rows inside an excluded
    list year's preseason window and R-VM input rows are skipped, so no reserved read
    contributes even its printed origin."""
    def skip(pk: str, day: str) -> bool:
        V = int(day[:4])
        lo, hi = window_bounds(V, None)
        in_window = lo <= day[:10] < hi
        return (in_window and V in excluded) or (in_window and is_rvm_input(V, debut.get(pk)))

    fg: dict[str, list] = defaultdict(list)
    reports: dict[str, list] = defaultdict(list)
    ages: dict[str, list] = defaultdict(list)
    for src, pk, d, tj in con.execute(
            "SELECT source, player_key, snapshot_date, tools_json FROM snapshots "
            "WHERE source IN ('fangraphs', 'mlb_pipeline', 'baseballamerica') "
            "AND tools_json IS NOT NULL ORDER BY snapshot_date, id"):
        if not d or skip(pk, d):
            continue
        ex = _extras(tj)
        if src == "fangraphs":
            sf, mk = ex.get("signed_from"), ex.get("sign_market")
            if sf or mk:
                fg[pk].append((d[:10], sf, mk, ex.get("sign_year"), _num(ex.get("age"))))
        elif src == "mlb_pipeline":
            rep = ex.get("report")
            if rep:
                reports[pk].append((d[:10], rep))
        a = _num(ex.get("age"))
        if a is not None and src in ("fangraphs", "baseballamerica"):
            if abs(a - round(a)) > 1e-6:
                ages[pk].append(("decimal", a, d[:10]))
            else:
                ages[pk].append(("int", int(round(a)), int(d[:4])))
    draft_type: dict[str, str] = {}
    for milb_key, ptype in con.execute(
            "SELECT k.milb_key, d.player_type FROM draft_canonical_keys k "
            "JOIN draft_players d ON d.player_key = k.draft_key "
            "WHERE d.player_type IS NOT NULL"):
        o = origin_from_draft_type(ptype)
        if o:
            draft_type.setdefault(milb_key, o)
    for pk, ptype in con.execute(
            "SELECT promoted_key, player_type FROM draft_players "
            "WHERE promoted_key IS NOT NULL AND player_type IS NOT NULL"):
        o = origin_from_draft_type(ptype)
        if o:
            draft_type.setdefault(pk, o)
    # professional leagues only: the canonical-key table also maps amateur
    # international board entries (keys "overseas_int'l_amateur_..."), which are IFA
    overseas = {r[0] for r in con.execute(
        "SELECT promoted_key FROM overseas_players WHERE promoted_key IS NOT NULL "
        "AND UPPER(league) IN ('NPB', 'KBO', 'CPBL', 'CUBA')")}
    overseas |= {mk for ok, mk in con.execute(
        "SELECT overseas_key, milb_key FROM overseas_canonical_keys")
        if re.match(r"^overseas_(npb|kbo|cpbl|cuba)_", str(ok))}
    acq = {r[0]: {"method": r[1], "year": r[2], "school": r[3], "signing_date": r[4]}
           for r in con.execute("SELECT player_key, method, year, school, signing_date "
                                "FROM acquisitions")}
    fg_names = fg_college_names(fg)
    names = set(fg_names)
    for a in acq.values():
        if a.get("method") == "draft" and origin_from_school(a.get("school")) == "COL":
            names.add(_fg_base(a.get("school")))
    for school, ptype in con.execute(
            "SELECT school, player_type FROM draft_players WHERE school IS NOT NULL"):
        if origin_from_draft_type(ptype) == "COL":
            names.add(_fg_base(school))
    names = frozenset(n for n in names if len(n) >= 3 and n not in IFA_COUNTRIES)
    pipe: dict[str, list] = defaultdict(list)
    for pk, rows in reports.items():
        for day, rep in rows:
            o = origin_from_report(rep, names)
            if o:
                pipe[pk].append((day, o))
    return {"fg": dict(fg), "pipeline": dict(pipe), "ages": dict(ages),
            "draft_type": draft_type, "overseas": overseas, "acq": acq,
            "college_names": names, "fg_college_names": fg_names}


def _ifa_sign_age(pk: str, ev: dict) -> float | None:
    """Age at signing from the FanGraphs signing year and printed age. The acquisitions
    year is not used: on an international row it can be a later minor league contract."""
    for day, _sf, _mk, sy, age in ev["fg"].get(pk, []):
        if sy and age is not None:
            try:
                return float(age) - (_yearfrac(day) - (int(sy) + 0.5))
            except (TypeError, ValueError):
                continue
    return None


def _promote_pro(pk: str, origin: str, ev: dict) -> str:
    if origin != "IFA":
        return origin
    if pk in ev["overseas"]:
        return "PRO"
    sa = _ifa_sign_age(pk, ev)
    return "PRO" if sa is not None and sa >= PRO_SIGN_AGE else "IFA"


def classify_origin(pk: str, ev: dict, *, draft_year_hint: int | None = None,
                    milb_ages: list[tuple] | None = None,
                    pro_entry: str | None = None) -> tuple[str, str, str | None]:
    """(origin, route, evidence day or None). The first rule that classifies wins, in
    the precedence the design fixes; PRO is split off IFA afterwards."""
    for day, sf, mk, _sy, _age in ev["fg"].get(pk, []):
        o = origin_from_fg(sf, mk, ev.get("fg_college_names", frozenset()))
        if o:
            return _promote_pro(pk, o, ev), "fg_print", day
    o = ev["draft_type"].get(pk)
    if o:
        return o, "draft_type", None
    if pk in ev["overseas"]:
        return "PRO", "overseas", None
    a = ev["acq"].get(pk)
    if a:
        if a.get("method") == "international_fa":
            return _promote_pro(pk, "IFA", ev), "acquisitions", None
        if a.get("method") == "draft":
            o = origin_from_school(a.get("school"))
            if o:
                return o, "acquisitions", None
    votes = ev["pipeline"].get(pk, [])
    kinds = {o for _d, o in votes}
    if len(kinds) == 1:
        o = next(iter(kinds))
        return _promote_pro(pk, o, ev), "pipeline_text", votes[0][0]
    o = age_rule(_draft_year(a, draft_year_hint),
                 list(ev["ages"].get(pk, [])) + list(milb_ages or []))
    if o:
        return o, "age_rule", None
    if pro_entry:
        return pro_entry, "pro_entry", None
    return "UNK", "none", None


def _draft_year(acq: dict | None, hint: int | None) -> int | None:
    """The signing draft: the person's last draft selection before his first list read
    (the draft history cache, through the outcome-blind id), else the acquisitions year
    (which can hold an unsigned high school selection)."""
    if hint:
        return int(hint)
    if acq and acq.get("method") == "draft" and acq.get("year"):
        return int(acq["year"])
    return None


def pro_entry_rule(first_season: int | None, first_levels: set, first_age: float | None,
                   drafted: bool) -> str | None:
    """IFA for a person never selected in a draft (2005 on) and with no draft
    acquisition, whose first minor league season (2006 or later, so it is not the
    cache's first year) was in the Dominican Summer League or at a baseball age of 17
    or younger; amateur draftees are high school graduates. None otherwise."""
    if drafted or first_season is None or first_season < FIRST_MILB_SEASON + 1:
        return None
    if "DSL" in first_levels or (first_age is not None and first_age <= 17):
        return "IFA"
    return None


def disagreement_inputs(pk: str, ev: dict, *, draft_year_hint: int | None = None,
                        milb_ages: list[tuple] | None = None,
                        pro_entry: str | None = None) -> dict[str, str | None]:
    """Each route's own answer for one player (for the disagreement tables)."""
    out: dict[str, str | None] = {r: None for r in ROUTES if r != "none"}
    for _day, sf, mk, _sy, _age in ev["fg"].get(pk, []):
        o = origin_from_fg(sf, mk, ev.get("fg_college_names", frozenset()))
        if o:
            out["fg_print"] = o
            break
    out["draft_type"] = ev["draft_type"].get(pk)
    out["overseas"] = "PRO" if pk in ev["overseas"] else None
    a = ev["acq"].get(pk)
    if a:
        if a.get("method") == "international_fa":
            out["acquisitions"] = "IFA"
        elif a.get("method") == "draft":
            out["acquisitions"] = origin_from_school(a.get("school"))
    kinds = {o for _d, o in ev["pipeline"].get(pk, [])}
    out["pipeline_text"] = next(iter(kinds)) if len(kinds) == 1 else None
    out["age_rule"] = age_rule(_draft_year(a, draft_year_hint),
                               list(ev["ages"].get(pk, [])) + list(milb_ages or []))
    out["pro_entry"] = pro_entry
    return out


# ---------------------------------------------------------------------------
# level and age from the outcome-blind identity
# ---------------------------------------------------------------------------

def draft_years_by_person(draft_dir: Path = ID.DRAFT_DIR) -> dict[int, list[int]]:
    out: dict[int, list[int]] = defaultdict(list)
    if not Path(draft_dir).is_dir():
        return {}
    for p in sorted(Path(draft_dir).glob("*.json")):
        stem = p.stem[:4]
        if not stem.isdigit():
            continue
        try:
            picks = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for x in picks or []:
            try:
                out[int(x.get("mlbam"))].append(int(stem))
            except (TypeError, ValueError):
                continue
    return {k: sorted(set(v)) for k, v in out.items()}


def load_person_seasons(person_ids: set[int], last_season: int) -> dict:
    """{person: {group: {season: [minor league rows]}}} from the cache only (no fetch,
    never the major league sport)."""
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for season in range(FIRST_MILB_SEASON, int(last_season) + 1):
        for sport in ID.INDEX_SPORTS:
            for group in ID.GROUPS:
                for r in mh.season_splits(sport, season, group, fetch=False):
                    try:
                        pid = int(r.get("mlbam"))
                    except (TypeError, ValueError):
                        continue
                    if pid in person_ids and r.get("level") in LEVEL_RANK:
                        out[pid][group][season].append(r)
    return out


def level_age(person_seasons: dict, person: int | None, side: str, vintage: int) -> dict:
    """Primary level and baseball age of the last minor league season before V (the
    efv_dataset._milb_features rule: the highest level with at least 50 PA or 60 BF,
    else the most exposed level)."""
    if person is None:
        return {"level": None, "age": None, "season": None}
    group = SIDE_GROUP[side]
    expo = EXPOSURE_FIELD[group]
    seasons = (person_seasons.get(person) or {}).get(group) or {}
    for season in sorted((s for s in seasons if s <= int(vintage) - 1), reverse=True):
        rows = seasons[season]
        present = sorted({r["level"] for r in rows}, key=lambda lv: -LEVEL_RANK[lv])
        if not present:
            continue
        level = None
        for lv in present:
            lr = mh.level_row(rows, lv, group) or {}
            if (_num(lr.get(expo)) or 0.0) >= MIN_EXPOSURE[side]:
                level = lv
                break
        if level is None:
            level = max(present, key=lambda lv: _num((mh.level_row(rows, lv, group) or {})
                                                     .get(expo)) or 0.0)
        row = mh.level_row(rows, level, group) or {}
        return {"level": level, "age": _num(row.get("age")), "season": season}
    return {"level": None, "age": None, "season": None}


def first_pro_season(person_seasons: dict, person: int | None,
                     vintage: int) -> tuple[int | None, set, float | None]:
    """(first minor league season before V, its levels, its youngest baseball age)."""
    if person is None:
        return None, set(), None
    rows_by_season: dict[int, list] = defaultdict(list)
    for group in ID.GROUPS:
        for season, rows in ((person_seasons.get(person) or {}).get(group) or {}).items():
            if season <= int(vintage) - 1:
                rows_by_season[season].extend(rows)
    if not rows_by_season:
        return None, set(), None
    first = min(rows_by_season)
    rows = rows_by_season[first]
    ages = [a for a in (_num(r.get("age")) for r in rows) if a is not None]
    return first, {r.get("level") for r in rows}, (min(ages) if ages else None)


# ---------------------------------------------------------------------------
# the frame
# ---------------------------------------------------------------------------

def build_frame(con: sqlite3.Connection, *, debut: dict[str, str],
                eta_text: str | None = None, rlv_record: str | None = RLV_LOOK_RECORD,
                index: ID.NameIndex | None = None,
                person_seasons: dict | None = None,
                draft_years: dict[int, list[int]] | None = None) -> dict:
    """The frame: start reads, slots and completion flags, origin, side, rung, level
    and age. F-R3 first. Returns {"reads", "rvm", "lists", "starts", "slots",
    "evidence", "excluded"}; no growth is computed."""
    require_eta_record(eta_text)
    excluded = excluded_list_years(rlv_record)
    reads, rvm = load_reads(con, debut, excluded=excluded)
    lists = published_lists(reads)
    ev = load_origin_evidence(con, debut, excluded=excluded)
    pos_fallback = {pk: pos for pk, pos in con.execute(
        "SELECT player_key, position FROM players")}

    starts: dict[tuple[str, str, int], dict] = {}
    slots: list[dict] = []
    for key, rd in reads.items():
        src, pk, V = key
        if not is_published(src, V, lists):
            continue
        # A slot exists when the SOURCE published both lists: decided per (source,
        # year), never per player, so no count by rung can carry an end-read fact.
        hs = [h for h in HORIZONS
              if V + h not in excluded and is_published(src, V + h, lists)]
        if not hs:
            continue
        side = side_of(rd["position"]) or side_of(pos_fallback.get(pk))
        if side is None:
            continue
        starts[key] = {"side": side, "rung": grade_rung(rd["fv"], rd["plus"]),
                       "horizons": tuple(hs), "date": rd["date"], "name": rd["name"],
                       "list_age": rd["age"]}
        for h in hs:
            # F-R2: a slot whose end read would be an R-VM input leaves the modeling
            # frame (in_frame False); its grade was never loaded.
            slots.append({"key": key, "h": h, "completed": (src, pk, V + h) in reads,
                          "in_frame": (src, pk, V + h) not in rvm})

    # identity, level and age (outcome-blind; one index, filtered to V - 1 per read)
    if index is None:
        last = max((V for (_s, _p, V) in starts), default=2011) - 1
        index = ID.build_index(last)
    persons: dict[tuple[str, str, int], ID.Resolution] = {}
    for key, st in starts.items():
        persons[key] = ID.resolve(st["name"], key[2], index, st["side"])
    if person_seasons is None:
        ids = {r.person_id for r in persons.values() if r.person_id}
        last = max((V for (_s, _p, V) in starts), default=2011) - 1
        person_seasons = load_person_seasons(ids, last)
    if draft_years is None:
        draft_years = draft_years_by_person()

    player_person: dict[str, int] = {}
    player_first_v: dict[str, int] = {}
    player_last_v: dict[str, int] = {}
    player_milb_ages: dict[str, list] = defaultdict(list)
    for key, st in starts.items():
        res = persons[key]
        la = level_age(person_seasons, res.person_id, st["side"], key[2])
        st["id_how"] = res.how
        st["person"] = res.person_id
        if la["level"]:
            st["level_band"] = LEVEL_BAND[la["level"]]
            st["level_route"] = "milb"
        elif res.person_id:
            st["level_band"] = "pre-pro"
            st["level_route"] = "resolved_no_line"
        elif res.how == ID.HOW_NONE:
            st["level_band"] = "pre-pro"
            st["level_route"] = "no_candidate"
        else:
            st["level_band"] = None
            st["level_route"] = res.how
        if la["age"] is not None:
            st["age_route"] = "milb"
            st["age_rel"] = max(-AGE_REL_BOUND,
                                min(AGE_REL_BOUND, la["age"] - TYPICAL_LEVEL_AGE[la["level"]]))
        elif st["list_age"] is not None:
            st["age_route"] = "list"
            st["age_rel"] = None
        else:
            st["age_route"] = "missing"
            st["age_rel"] = None
        st["agemiss"] = st["age_route"] == "missing"
        st["milb_age"] = (la["age"], la["season"])
        pk = key[1]
        if res.person_id and pk not in player_person:
            player_person[pk] = res.person_id
        player_first_v[pk] = min(player_first_v.get(pk, 9999), key[2])
        player_last_v[pk] = max(player_last_v.get(pk, 0), key[2])
        if la["age"] is not None:
            player_milb_ages[pk].append(("int", int(la["age"]), int(la["season"])))

    origin: dict[str, tuple] = {}
    routes_each: dict[str, dict] = {}
    for pk in sorted({k[1] for k in starts}):
        person = player_person.get(pk)
        hint = None
        if person and draft_years.get(person):
            before = [y for y in draft_years[person] if y < player_first_v[pk]]
            hint = before[-1] if before else None
        mages = sorted(set(player_milb_ages.get(pk, [])))
        pe = None
        if person:
            a = ev["acq"].get(pk) or {}
            drafted = bool(draft_years.get(person)) or a.get("method") == "draft"
            fs, fl, fa = first_pro_season(person_seasons, person, player_last_v[pk])
            pe = pro_entry_rule(fs, fl, fa, drafted)
        origin[pk] = classify_origin(pk, ev, draft_year_hint=hint, milb_ages=mages,
                                     pro_entry=pe)
        routes_each[pk] = disagreement_inputs(pk, ev, draft_year_hint=hint, milb_ages=mages,
                                              pro_entry=pe)
    for key, st in starts.items():
        o, route, day = origin[key[1]]
        st["origin"], st["origin_route"] = o, route
        if day is None:
            st["evidence_timing"] = "undated"
        else:
            st["evidence_timing"] = "on_or_before_start" if day <= st["date"] \
                else "after_start"
    return {"reads": reads, "rvm": rvm, "lists": lists, "starts": starts,
            "slots": slots, "routes_each": routes_each, "excluded": excluded}


# ---------------------------------------------------------------------------
# counts (the only output)
# ---------------------------------------------------------------------------

def _share(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def p2_check(cells: dict[tuple[str, str], Counter]) -> dict:
    """P-2 on a {(side, rung): Counter(origin)} table of start reads."""
    tot = sum(sum(c.values()) for c in cells.values())
    unk = sum(c.get("UNK", 0) for c in cells.values())
    per = {}
    failing = []
    for side in SIDES:
        for rung in RUNGS:
            c = cells.get((side, rung), Counter())
            n = sum(c.values())
            u = c.get("UNK", 0)
            per[f"{side}|{rung}"] = {"n": n, "unknown": u, "share": _share(u, n)}
            if n and u / n > P2_MAX_UNKNOWN_CELL:
                failing.append(f"{side}|{rung}")
    overall = _share(unk, tot)
    ok = (overall is not None and overall <= P2_MAX_UNKNOWN_OVERALL) and not failing
    return {"n": tot, "unknown": unk, "share": overall, "cells": per,
            "cells_over_ceiling": failing, "holds": bool(ok),
            "ceilings": {"overall": P2_MAX_UNKNOWN_OVERALL, "cell": P2_MAX_UNKNOWN_CELL}}


def summarize(frame: dict) -> dict:
    """Counts only. A grade rung appears only beside START reads (inputs); every
    completed-pair count is by source, side and start year."""
    reads, starts, slots = frame["reads"], frame["starts"], frame["slots"]
    lists = frame["lists"]
    out: dict = {}
    out["preseason_reads_by_source_year"] = {
        src: {str(V): {"reads": n, "published": is_published(src, V, lists)}
              for (s, V), n in sorted(lists.items()) if s == src}
        for src in SOURCES}

    pairs: dict = {}
    for h in HORIZONS:
        fr = defaultdict(Counter)
        cp = defaultdict(Counter)
        for sl in slots:
            if sl["h"] != h:
                continue
            src, _pk, V = sl["key"]
            side = starts[sl["key"]]["side"]
            fr[(src, side)][V] += 1
            if sl["completed"]:
                cp[(src, side)][V] += 1
        block = {}
        for src in SOURCES:
            for side in SIDES:
                years = sorted(set(fr[(src, side)]) | set(cp[(src, side)]))
                block[f"{src}|{side}"] = {
                    str(V): {"list_slots": fr[(src, side)][V],
                             "completed_pairs": cp[(src, side)][V]} for V in years}
        tot_fr = sum(sum(c.values()) for c in fr.values())
        tot_cp = sum(sum(c.values()) for c in cp.values())
        pairs[f"{12 * h}m"] = {"by_source_side_start_year": block,
                               "total_list_slots": tot_fr, "total_completed_pairs": tot_cp}
    out["pairs"] = pairs
    out["pairs_definition"] = (
        "list_slots: start reads whose source published a preseason list in V and in "
        "V + h (decided per source and year, never per player). completed_pairs: slots "
        "with a same-source end read in V + h. Pooled over grade rungs; never by rung.")

    cov: dict = {}
    for name, keep in (("union", lambda st: True),
                       ("12m", lambda st: 1 in st["horizons"]),
                       ("24m", lambda st: 2 in st["horizons"])):
        cells: dict = defaultdict(Counter)
        by_route = Counter()
        by_side_origin = Counter()
        for key, st in starts.items():
            if not keep(st):
                continue
            cells[(st["side"], st["rung"])][st["origin"]] += 1
            by_route[st["origin_route"]] += 1
            by_side_origin[f"{st['side']}|{st['origin']}"] += 1
        cov[name] = {
            "start_reads_by_side_rung_origin": {
                f"{s}|{r}": dict(sorted(cells[(s, r)].items())) for s in SIDES for r in RUNGS},
            "start_reads_by_route": dict(sorted(by_route.items())),
            "start_reads_by_side_origin": dict(sorted(by_side_origin.items())),
            "p2": p2_check(cells),
        }
    out["origin_coverage"] = cov

    timing = Counter()
    for st in starts.values():
        timing[f"{st['origin_route']}|{st['evidence_timing']}"] += 1
    out["origin_evidence_timing"] = dict(sorted(timing.items()))

    # disagreement: each backfill route against the list-printed origin, per player
    re_each = frame["routes_each"]
    dis: dict = {}
    for route in ROUTES:
        if route in ("fg_print", "none"):
            continue
        tab = Counter()
        for pk, r in re_each.items():
            f, o = r.get("fg_print"), r.get(route)
            if f and o:
                tab[f"fg={_fold(f)}|{route}={_fold(o)}"] += 1
        agree = sum(n for k, n in tab.items()
                    if k.split("|")[0][3:] == k.split("|")[1].split("=")[1])
        both = sum(tab.values())
        dis[route] = {"players_with_both": both, "agree": agree,
                      "disagree": both - agree, "disagree_share": _share(both - agree, both),
                      "table": dict(tab.most_common())}
    out["origin_disagreement_vs_fg_print"] = dis

    lvl: dict = defaultdict(lambda: {"start_reads": 0, "id_how": Counter(),
                                     "level_band": Counter(), "level_route": Counter(),
                                     "age_route": Counter()})
    for key, st in starts.items():
        b = lvl[f"{st['side']}|{key[2]}"]
        b["start_reads"] += 1
        b["id_how"][st["id_how"]] += 1
        b["level_band"][str(st["level_band"])] += 1
        b["level_route"][st["level_route"]] += 1
        b["age_route"][st["age_route"]] += 1
    out["level_age_coverage_by_side_year"] = {
        k: {kk: (dict(sorted(vv.items())) if isinstance(vv, Counter) else vv)
            for kk, vv in v.items()} for k, v in sorted(lvl.items())}

    players = {k[1] for k in starts}
    pyears = Counter((k[1], k[2]) for k in starts)
    out["clustering"] = {
        "start_reads": len(starts), "players": len(players),
        "player_years": len(pyears),
        "sources_per_player_year": _share(len(starts), len(pyears)),
        "start_reads_per_player": _share(len(starts), len(players)),
        "start_reads_with_12m_slot": sum(1 for s in starts.values() if 1 in s["horizons"]),
        "start_reads_with_24m_slot": sum(1 for s in starts.values() if 2 in s["horizons"]),
    }
    out["power_block"] = power_block(out)
    out["frame_rules"] = {
        "excluded_list_years": sorted(frame["excluded"]),
        "rlv_look_record": RLV_LOOK_RECORD,
        "r_vm_first_debut_year": R_VM_FIRST_DEBUT_YEAR,
        "pipeline_2026_preseason_declared_absent": PIPELINE_2026_PRESEASON_DECLARED_ABSENT,
        "min_list_reads": MIN_LIST_READS,
        "horizons_years": list(HORIZONS),
        "eta_look_recorded": True,
    }
    return out


#: Planning assumptions of dvm_difficulty.md D.4 (ASSUMED, never read from an outcome).
POWER_ASSUMED_P = 0.20
POWER_ASSUMED_SD = 5.0
POWER_ALPHA = 0.05
POWER_TARGET = 0.80
H1_RUNGS: tuple[str, ...] = ("40", "45", "50", "55")
H1_FAMILY = 39
H2_FAMILY = 8


def _z(q: float) -> float:
    from statistics import NormalDist
    return NormalDist().inv_cdf(q)


def power_block(c: dict) -> dict:
    """The registration's power block (dvm_difficulty.md D.4, P-5), from counts only.
    Effective pairs = frame START reads in the cells x the POOLED completion share of
    the horizon (one number per horizon, never by rung) / sources per player-year.
    The detectable differences use the ASSUMED base rate and spread; no grade
    difference, rate or outcome enters."""
    z_pow = _z(POWER_TARGET)
    spy = c["clustering"]["sources_per_player_year"] or 1.0
    out: dict = {
        "assumptions": {"base_rate_p": POWER_ASSUMED_P, "spread_grade_points": POWER_ASSUMED_SD,
                        "alpha_two_sided": POWER_ALPHA, "power": POWER_TARGET,
                        "h1_holm_family": H1_FAMILY, "h2_holm_family": H2_FAMILY},
        "method": ("effective pairs = start reads x pooled completion share of the horizon "
                   "/ sources per player-year; before the widening from players recurring "
                   "across years. H2: two-proportion difference at the assumed base rate, "
                   "unadjusted and at the Holm-strictest alpha / 8. H1: difference in means "
                   "at the assumed spread, at the Holm-strictest alpha / 39."),
        "sources_per_player_year": spy,
    }
    for hz in ("12m", "24m"):
        blk = c["pairs"][hz]
        comp = _share(blk["total_completed_pairs"], blk["total_list_slots"]) or 0.0
        cells = c["origin_coverage"][hz]["start_reads_by_side_rung_origin"]
        per_side = {}
        for side in SIDES:
            def n_of(rungs, origins=None):
                tot = 0
                for r in rungs:
                    for o, n in cells.get(f"{side}|{r}", {}).items():
                        if origins is None or o in origins:
                            tot += n
                return tot
            n40 = n_of(("40",)) * comp / spy
            n60 = n_of(("60", "65+")) * comp / spy
            z1 = _z(1 - POWER_ALPHA / 2)
            zh = _z(1 - POWER_ALPHA / H2_FAMILY / 2)
            pq = POWER_ASSUMED_P * (1 - POWER_ASSUMED_P)
            inv = (1 / n40 + 1 / n60) if n40 and n60 else None
            h1 = {}
            for g, origins in (("HS", ("HS",)), ("COL", ("COL", "JUCO")), ("IFA", ("IFA",))):
                h1[g] = round(n_of(H1_RUNGS, origins) * comp / spy, 1)
            zh1 = _z(1 - POWER_ALPHA / H1_FAMILY / 2)
            mdd = {}
            for a, b in (("HS", "COL"), ("IFA", "COL"), ("HS", "IFA")):
                if h1[a] and h1[b]:
                    mdd[f"{a}-{b}"] = round((zh1 + z_pow) * POWER_ASSUMED_SD
                                            * (1 / h1[a] + 1 / h1[b]) ** 0.5, 2)
            per_side[side] = {
                "h2_effective_pairs_rung40": round(n40, 1),
                "h2_effective_pairs_rung60plus": round(n60, 1),
                "h2_detectable_diff_p_unadjusted": (round((z1 + z_pow) * (pq * inv) ** 0.5, 4)
                                                    if inv else None),
                "h2_detectable_diff_p_holm_strictest": (round((zh + z_pow) * (pq * inv) ** 0.5, 4)
                                                        if inv else None),
                "h1_effective_pairs_rungs_40_to_55": h1,
                "h1_detectable_gap_grade_points_holm_strictest": mdd,
            }
        out[hz] = {"pooled_completion_share": comp, "by_side": per_side}
    return out


def _fold(o: str) -> str:
    """JUCO folds into college and PRO into international for the agreement count."""
    return {"JUCO": "COL", "PRO": "IFA"}.get(o, o)


# ---------------------------------------------------------------------------
# text summary
# ---------------------------------------------------------------------------

def text_summary(c: dict) -> str:
    L = []
    L.append("DvM+ difficulty frame, counts only (DVM-1). No grade difference, growth, "
             "rate by rung, WAR, debut or graduation quantity was computed.")
    L.append("")
    L.append("Preseason reads by source and list year (published = in frame):")
    for src, years in c["preseason_reads_by_source_year"].items():
        L.append(f"  {src}: " + ", ".join(
            f"{V} {v['reads']}{'' if v['published'] else ' (not a list)'}"
            for V, v in years.items()))
    for hz, blk in c["pairs"].items():
        L.append("")
        L.append(f"{hz}: list slots {blk['total_list_slots']}, completed same-source "
                 f"pairs {blk['total_completed_pairs']}")
        for k, years in blk["by_source_side_start_year"].items():
            if not years:
                continue
            L.append(f"  {k}: " + ", ".join(
                f"{V} {v['completed_pairs']}/{v['list_slots']}" for V, v in years.items()))
    for name, cov in c["origin_coverage"].items():
        p2 = cov["p2"]
        L.append("")
        L.append(f"Origin coverage ({name} frame start reads): n {p2['n']}, unknown "
                 f"{p2['unknown']} ({p2['share']}); P-2 holds: {p2['holds']}; cells over "
                 f"the 10 percent ceiling: {', '.join(p2['cells_over_ceiling']) or 'none'}")
        L.append("  by route: " + ", ".join(f"{k} {v}" for k, v in
                                           cov["start_reads_by_route"].items()))
        for side in SIDES:
            L.append(f"  {side}: " + "; ".join(
                f"{r} n {p2['cells'][f'{side}|{r}']['n']} unk "
                f"{p2['cells'][f'{side}|{r}']['unknown']}" for r in RUNGS))
    L.append("")
    L.append("Disagreement with the FanGraphs list-printed origin (players with both):")
    for route, d in c["origin_disagreement_vs_fg_print"].items():
        L.append(f"  {route}: both {d['players_with_both']}, disagree {d['disagree']} "
                 f"({d['disagree_share']})")
    L.append("")
    L.append("Clustering: " + ", ".join(f"{k} {v}" for k, v in c["clustering"].items()))
    pb = c.get("power_block")
    if pb:
        a = pb["assumptions"]
        L.append("")
        L.append(f"Power block (counts and ASSUMED p {a['base_rate_p']}, spread "
                 f"{a['spread_grade_points']}; effective pairs = start reads x pooled "
                 f"completion / {pb['sources_per_player_year']} sources per player-year):")
        for hz in ("12m", "24m"):
            L.append(f"  {hz}: pooled completion {pb[hz]['pooled_completion_share']}")
            for side, s in pb[hz]["by_side"].items():
                L.append(f"    {side}: H2 rung 40 {s['h2_effective_pairs_rung40']} vs 60+ "
                         f"{s['h2_effective_pairs_rung60plus']}, detectable diff "
                         f"{s['h2_detectable_diff_p_unadjusted']} (Holm-strictest "
                         f"{s['h2_detectable_diff_p_holm_strictest']}); H1 rungs 40-55 "
                         + ", ".join(f"{g} {n}" for g, n in
                                     s["h1_effective_pairs_rungs_40_to_55"].items())
                         + "; detectable gap " + ", ".join(
                             f"{k} {v}" for k, v in
                             s["h1_detectable_gap_grade_points_holm_strictest"].items()))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# DVM-3: the study (gate sections 3 to 15)
# ---------------------------------------------------------------------------
#
# Every function in this part is a pure function of the rows it is handed. A row of
# the study is a dict built by pairs_from_frame() (from the frozen store, at the look
# only) or by fixture_pairs() (synthetic, for the dry run and the tests). Only
# load_club_events() and run_look() open the store, and only at the look; no function
# here reads a served artifact or any outcome.

#: storage.FV_EXPECTED_WAR, copied (the lab never imports storage; parity pinned in
#: test_dvm_difficulty_stat.py). A fixed primer table, not a realized quantity.
VALUE_TABLE: dict[int, float] = {20: 0.0, 25: 0.0, 30: 0.0, 35: 0.1, 40: 0.5, 45: 1.5,
                                 50: 3.0, 55: 6.0, 60: 12.0, 65: 17.0, 70: 25.0,
                                 75: 40.0, 80: 60.0}

#: Section 3: a dropped or exited row ends one rung below its club's lowest grade; S2
#: codes a graduate at his start grade plus one rung.
DROP_RUNG = 5.0
GRAD_S2_BUMP = 5.0
STATUSES: tuple[str, ...] = ("completed", "graduated", "dropped", "exited")
VARIANTS: tuple[str, ...] = ("primary", "S1", "S2")

#: Section 5.
MIN_B_CELL = 30
MIN_U_CELL = 20
K_U_FLOOR = 20.0
SPREAD_PSEUDO_DF = 30.0
REF_RUNG = "50"
REF_ORIGIN = "COL"
REF_LEVEL = "A/A+"
MODEL_ORIGINS: tuple[str, ...] = ("HS", "COL", "IFA", "PRO", "UNK")
LEVELS: tuple[str, ...] = ("pre-pro", "DSL/CPX", "A/A+", "AA/AAA", "unresolved")
RUNG_VALUE = {"<=35": 35.0, "40": 40.0, "45": 45.0, "50": 50.0, "55": 55.0, "60": 60.0,
              "65+": 65.0}

#: Section 7 and section 9.
K_ORG_BOUNDS = (5.0, 50.0)
MIN_PUBLISH_N = 10.0
PLAYER_STEPS = 3
PLAYER_SHRINK_K = 2.0

#: Sections 10, 11 and 13.
SEED = 20261201
BOOT_B = 2000
PERM_DRAWS = 500
ALPHA = 0.05
H1_MIN_PAIRS = 100
H2_MIN_PAIRS = 50
H2_L2 = 1.0
H2_RUNGS: tuple[str, ...] = ("<=35", "40", "45", "50", "55", "60+")
H2_TREND_RUNGS: tuple[str, ...] = ("40", "45", "50", "55", "60+")
NONINF_MARGIN = -0.05
VC_MAX = 0.20
VC_BELOW_C0 = 0.10
PIT_CORR_FLOOR = 0.9
INDEX_WINDOW_YEARS = 3
TRAITS: dict[str, tuple[str, ...]] = {
    "hit": ("FV", "hit", "game_pwr", "raw_pwr", "speed", "field", "arm"),
    "pit": ("FV", "fb", "sl", "cb", "ch", "cmd"),
}
DESCRIPTIVE_TRAITS: dict[str, tuple[str, ...]] = {"hit": ("pitch_sel", "bat_ctrl"),
                                                  "pit": ("ct",)}
#: The trait name against the key the sources print it under.
TRAIT_KEY = {"arm": "throw"}
H1_GROUPS: tuple[str, ...] = ("HS", "COL", "IFA")
H1_CONTRASTS: tuple[tuple[str, str], ...] = (("HS", "COL"), ("IFA", "COL"), ("HS", "IFA"))
ERAS = {"COMPLEMENT": ((2011, 2016), (2017, 2019), (2022, 9999)),
        "FULL": ((2011, 2016), (2017, 2021), (2022, 9999))}
VALIDATION_YEARS = {"FULL": tuple(range(2012, 2026)),
                    "COMPLEMENT": tuple(list(range(2012, 2019)) + [2023, 2024, 2025])}

#: Section 14: the clock.
LOOK_EARLIEST_FULL = "2026-12-01"
LOOK_EARLIEST_COMPLEMENT = "2027-01-31"
#: Gate amendment A-1 (2026-10-14): the owner's decision EW3-5 waives registered look
#: dates. From its date the FULL-frame look runs before LOOK_EARLIEST_FULL and is
#: recorded as an OWNER-WAIVED EARLY READ. The COMPLEMENT date, the look days and every
#: record precondition stand.
OWNER_WAIVER: dict | None = {"decision": "EW3-5", "from": "2026-10-14",
                             "waives": "LOOK_EARLIEST_FULL"}
#: Registered look days (gate section 14, plan Part 8 8.B and Part 9): never a look here.
#: 2026-12-01 is the eFV reserved read.
LOOK_DAYS: frozenset[str] = frozenset({
    "2026-10-21", "2026-10-23", "2026-10-28", "2026-11-06", "2026-11-13", "2026-11-20",
    "2026-11-24", "2026-11-25", "2026-12-01", "2026-12-03", "2026-12-08", "2026-12-10",
    "2027-01-12", "2027-10-20", "2027-11-09", "2027-11-16",
})
ANCHOR_GATE_DOC = "docs/PROSPECT_ANCHOR_GATE.md"
EFV_V2_GATE_DOC = "docs/efv-v2/EFV_V2_GATE.md"
#: VAL_4's tenure table (gate section 7, P-1). Absent at registration: the fallback reads.
VAL4_DIR = "docs/farm-attribution-2026-09-25"
#: Section 2: the frozen store and the counts a fresh copy is checked against.
FROZEN_DB_SHA256 = "7d7e56533e6c62ef3ec3d8400e079974779ea59ca533dbc0e43939f596d6a56e"
REGISTERED_COUNTS = {"start_reads": 14961, "completed_pairs_12m": 8020,
                     "completed_pairs_24m": 3205}
COUNT_TOLERANCE = 0.01
TABLE_ARTIFACT = "dvm_difficulty.json"
EVAL_ARTIFACT = "dvm_difficulty_eval.json"
LOOK_MARKER = "look_started.json"
BUSY_TOKENS: tuple[str, ...] = ("run_monthly", "nightly", "pytest")


# ---------------------------------------------------------------------------
# grades, value and rungs
# ---------------------------------------------------------------------------

def value_of(g: float) -> float:
    """W(G), the table linearly interpolated and rounded to 2 places as
    storage._fv_to_expected_war does; a grade outside 20 to 80 takes the end value."""
    v = min(80.0, max(20.0, float(g)))
    keys = sorted(VALUE_TABLE)
    for lo, hi in zip(keys, keys[1:]):
        if lo <= v <= hi:
            t = (v - lo) / (hi - lo)
            return round(VALUE_TABLE[lo] + t * (VALUE_TABLE[hi] - VALUE_TABLE[lo]), 2)
    return VALUE_TABLE[keys[-1]]


def grade_value(fv: float, plus: bool) -> float:
    """G = fv + 2.5 x fv_plus (a FanGraphs 45+ is 47.5)."""
    return float(fv) + (2.5 if plus else 0.0)


def rung_of(g: float) -> str:
    """The rung cell of a grade: 5 x floor(G / 5), with <=35 and 65+ pooled."""
    r = int(float(g) // 5 * 5)
    if r <= 35:
        return "<=35"
    if r >= 65:
        return "65+"
    return str(r)


def h2_rung(rung: str) -> str:
    """H2 reads 60 and 65+ as one cell, 60+."""
    return "60+" if rung in ("60", "65+") else rung


def fold_origin(origin: str | None) -> str:
    """The model's origin groups: junior college folds into college."""
    o = origin or "UNK"
    return "COL" if o == "JUCO" else (o if o in MODEL_ORIGINS else "UNK")


# ---------------------------------------------------------------------------
# censoring and the three frames (section 3)
# ---------------------------------------------------------------------------

def code_missing_end(g_start: float, *, debut_day: str | None, end_close: str,
                     grad_grade: float | None, club_lowest: float | None,
                     affiliated: bool | None) -> tuple[str, float | None]:
    """(status, G_end) for a slot with no same-source end read, by the rule section 3
    fixed before any growth was read.
    Graduated: the debut fell before the end window closed; G_end is the last
    same-source read before the debut (grad_grade; the caller passes the start grade
    when there is no later read). Dropped: still in affiliated ball (or not known to
    have left); G_end is one rung below the lowest grade the source printed for his
    club at V + h, never above G_start. Exited: no affiliated season in V + h - 1 or
    V + h (affiliated False); coded as dropped. With no club grade to read the row
    has no end grade (None) and leaves the frame."""
    if debut_day and str(debut_day)[:10] < end_close:
        return "graduated", float(g_start if grad_grade is None else grad_grade)
    status = "exited" if affiliated is False else "dropped"
    if club_lowest is None:
        return status, None
    return status, min(float(club_lowest) - DROP_RUNG, float(g_start))


def end_grade(pair: dict, variant: str = "primary") -> float | None:
    """The end grade a frame variant reads: primary codes every row; S1 drops every
    censored row; S2 codes a graduate at G_start + 5."""
    st = pair["status"]
    if variant == "S1" and st != "completed":
        return None
    if variant == "S2" and st == "graduated":
        return float(pair["g0"]) + GRAD_S2_BUMP
    g1 = pair.get("g1")
    return None if g1 is None else float(g1)


def end_tool(pair: dict, key: str, variant: str = "primary") -> float | None:
    """A tool's end grade (section 3, tool rows): a graduate takes the tool grade of
    his last same-source read before the debut (S1 drops him, S2 codes start + 5); a
    dropped or exited row leaves the tool frame."""
    t0 = (pair.get("tools0") or {}).get(key)
    if t0 is None:
        return None
    st = pair["status"]
    if st in ("dropped", "exited"):
        return None
    if st == "graduated":
        if variant == "S1":
            return None
        if variant == "S2":
            return float(t0) + GRAD_S2_BUMP
    t1 = (pair.get("tools1") or {}).get(key)
    return None if t1 is None else float(t1)


def analysis_rows(pairs: list[dict], *, variant: str = "primary", trait: str = "FV",
                  h: int = 1, side: str | None = None,
                  sources: tuple[str, ...] | None = None) -> list[dict]:
    """The rows one fit reads, with omega = 1 / (sources listing the player in that
    start year and horizon, inside this frame)."""
    key = TRAIT_KEY.get(trait, trait)
    out = []
    for p in pairs:
        if p["h"] != h or (side and p["side"] != side):
            continue
        if sources and p["src"] not in sources:
            continue
        if trait == "FV":
            g1 = end_grade(p, variant)
            if g1 is None:
                continue
            g0 = float(p["g0"])
            y, wv, rung, gap = g1 - g0, value_of(g1) - value_of(g0), p["rung"], None
        else:
            t0 = (p.get("tools0") or {}).get(key)
            t1 = end_tool(p, key, variant)
            if t0 is None or t1 is None:
                continue
            y, wv, rung = float(t1) - float(t0), None, rung_of(t0)
            pres = (p.get("present0") or {}).get(key)
            gap = (float(t0) - float(pres)) if (p["src"] == "fangraphs"
                                                and pres is not None) else None
        out.append({
            "src": p["src"], "pk": p["pk"], "V": int(p["V"]), "h": int(p["h"]),
            "side": p["side"], "y": float(y), "w": wv, "rung": rung,
            "fv_rung": p["rung"], "g0": float(p["g0"]),
            "origin": fold_origin(p.get("origin")), "origin_raw": p.get("origin") or "UNK",
            "level": p.get("level") or "unresolved", "age_rel": p.get("age_rel"),
            "agemiss": bool(p.get("agemiss")), "gap": gap, "status": p["status"],
            "tau": dict(p.get("tau") or {}), "trait": trait,
        })
    n_src = Counter((r["pk"], r["V"], r["h"]) for r in out)
    for r in out:
        r["omega"] = 1.0 / n_src[(r["pk"], r["V"], r["h"])]
    return out


def censoring_census(pairs: list[dict]) -> dict:
    """Censored counts pooled over side and rung (section 3; never by rung)."""
    out = {}
    for h in HORIZONS:
        c = Counter(p["status"] for p in pairs if p["h"] == h)
        out[f"{12 * h}m"] = {s: c.get(s, 0) for s in STATUSES}
    return out


# ---------------------------------------------------------------------------
# small numerics
# ---------------------------------------------------------------------------

def _wmean(x, w) -> float:
    x, w = np.asarray(x, float), np.asarray(w, float)
    sw = float(w.sum())
    return float((w * x).sum() / sw) if sw > 0 else 0.0


def _wvar(x, w) -> float:
    """Weighted variance about the weighted mean (weights normalized to their sum)."""
    x, w = np.asarray(x, float), np.asarray(w, float)
    sw = float(w.sum())
    if sw <= 0 or x.size == 0:
        return 0.0
    m = float((w * x).sum() / sw)
    return float((w * (x - m) ** 2).sum() / sw)


def _solve(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted least squares through the normal equations with a pseudo-inverse: a
    rank-deficient design keeps its estimable contrasts unique."""
    if X.shape[0] == 0 or X.shape[1] == 0:
        return np.zeros(X.shape[1])
    xtw = X.T * w
    return np.linalg.pinv(xtw @ X, rcond=1e-10, hermitian=True) @ (xtw @ y)


def round_nearest(x: float) -> int:
    """Plus stats round to nearest, halves up."""
    return int(math.floor(float(x) + 0.5))


def _rank(x) -> np.ndarray:
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def pearson(x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.size < 3 or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y) -> float | None:
    """Spearman's rho with average ranks for ties; None on fewer than 3 points or a
    constant side."""
    if len(x) < 3:
        return None
    return pearson(_rank(x), _rank(y))


def holm(pvals: list[float]) -> list[float]:
    """Holm step-down adjusted p values, monotone, capped at 1."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [1.0] * m
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * float(pvals[i])))
        adj[i] = run
    return adj


def p_two_sided(draws, B: int) -> float:
    """2 x min(share <= 0, share >= 0) over the finite draws, floored at 1/B."""
    d = np.asarray(draws, float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return 1.0
    p = 2.0 * min(float((d <= 0).mean()), float((d >= 0).mean()))
    return float(min(1.0, max(p, 1.0 / B)))


def p_one_sided_below(draws, B: int) -> float:
    """H0 'not below 0': the share of draws on or past 0, floored at 1/B."""
    d = np.asarray(draws, float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return 1.0
    return float(min(1.0, max(float((d >= 0).mean()), 1.0 / B)))


def _ci95(draws) -> list[float | None]:
    d = np.asarray(draws, float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return [None, None]
    return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]


def _cluster_codes(rows: list[dict], key: str = "pk") -> tuple[np.ndarray, int]:
    ids = {}
    codes = np.array([ids.setdefault(r[key], len(ids)) for r in rows], dtype=int)
    return codes, len(ids)


def _draw_counts(rng: np.random.Generator, n: int) -> np.ndarray:
    """One cluster bootstrap draw: how many times each cluster was drawn."""
    return np.bincount(rng.integers(0, n, n), minlength=n).astype(float)


# ---------------------------------------------------------------------------
# the expectation model (section 5)
# ---------------------------------------------------------------------------

def shrink_cells(cells: dict, s2_eps: float) -> dict:
    """The shrunk origin-by-rung interaction, from {cell: (n_c, mean residual of the
    additive fit)}:
      tau2_u = max(0, var_c(mean residual) - mean_c(s2_eps / n_c)) over cells n_c >= 20
      k_u    = max(20, s2_eps / tau2_u)
      u_hat  = n_c / (n_c + k_u) x mean residual when n_c >= 20, else 0.
    tau2_u = 0 (fewer than two eligible cells, or no excess variance) means no
    interaction survives: k_u is None and every u_hat is 0."""
    elig = [(n, m) for n, m in cells.values() if n >= MIN_U_CELL]
    tau2 = 0.0
    if len(elig) >= 2:
        means = np.array([m for _n, m in elig], float)
        noise = float(np.mean([s2_eps / n for n, _m in elig]))
        tau2 = max(0.0, float(np.var(means, ddof=1)) - noise)
    k_u = max(K_U_FLOOR, s2_eps / tau2) if tau2 > 0 else None
    u_hat = {c: ((n / (n + k_u)) * m if (k_u is not None and n >= MIN_U_CELL) else 0.0)
             for c, (n, m) in cells.items()}
    return {"u_hat": u_hat, "k_u": k_u, "tau2_u": tau2}


def shrunk_spread(n_c: int, s2_c: float, s2_side: float,
                  pseudo: float = SPREAD_PSEUDO_DF) -> float:
    """The spread floor: sqrt((nu_c s2_c + 30 s2_side) / (nu_c + 30)), nu_c = n_c - 1."""
    nu = max(int(n_c) - 1, 0)
    return math.sqrt((nu * float(s2_c) + pseudo * float(s2_side)) / (nu + pseudo))


def _features(r: dict, kind: str, own_b: set) -> list[tuple[str, float]]:
    """The design row of section 5: a[s,V], b[s,r] (or b[r] pooled when its source cell
    holds fewer than 30 pairs), c[g], d[L], e x age_rel, f x agemiss; tool rows add the
    start FV rung and the FanGraphs future-minus-present gap with its known flag.
    Reference levels (no column): rung 50, college, A/A+."""
    f = [(f"a|{r['src']}|{r['V']}", 1.0)]
    rg = r["rung"]
    if rg != REF_RUNG:
        f.append((f"b|{r['src']}|{rg}" if (r["src"], rg) in own_b else f"b|*|{rg}", 1.0))
    if r["origin"] != REF_ORIGIN:
        f.append((f"c|{r['origin']}", 1.0))
    if r["level"] != REF_LEVEL:
        f.append((f"d|{r['level']}", 1.0))
    if r.get("age_rel") is not None:
        f.append(("e|age_rel", float(r["age_rel"])))
    if r.get("agemiss"):
        f.append(("f|agemiss", 1.0))
    if kind == "tool":
        if r["fv_rung"] != REF_RUNG:
            f.append((f"t|fv_rung|{r['fv_rung']}", 1.0))
        if r.get("gap") is not None:
            f.append(("t|gap", float(r["gap"])))
            f.append(("t|gap_known", 1.0))
    return f


def _matrix(feats: list, cols: list[str]) -> np.ndarray:
    idx = {c: i for i, c in enumerate(cols)}
    X = np.zeros((len(feats), len(cols)))
    for i, f in enumerate(feats):
        for c, v in f:
            j = idx.get(c)
            if j is not None:
                X[i, j] += v
    return X


def _own_b(rows: list[dict]) -> set:
    cnt = Counter((r["src"], r["rung"]) for r in rows)
    return {k for k, n in cnt.items() if n >= MIN_B_CELL and k[1] != REF_RUNG}


def fit_expectation(rows: list[dict], *, outcome: str = "y", kind: str = "fv") -> dict:
    """Section 5 on one side's rows: the additive WLS fit (weights omega), the shrunk
    interaction cells, and the floored spread of y - E by start rung. Returns the frozen
    table as a plain dict (what data/dvm_difficulty.json carries)."""
    model = {"kind": kind, "outcome": outcome, "n": len(rows), "columns": [], "coef": {},
             "own_b": [], "a_source_mean": {}, "u": {}, "k_u": None, "tau2_u": 0.0,
             "s2_eps": 0.0, "s2_side": 0.0, "spread": {}}
    if not rows:
        return model
    own = _own_b(rows)
    feats = [_features(r, kind, own) for r in rows]
    cols = sorted({c for f in feats for c, _v in f})
    X = _matrix(feats, cols)
    y = np.array([float(r[outcome]) for r in rows])
    w = np.array([float(r["omega"]) for r in rows])
    beta = _solve(X, y, w)
    add = X @ beta
    res = y - add
    s2_eps = _wvar(res, w)
    groups: dict = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["origin"], r["rung"])].append(i)
    cells = {c: (len(ix), _wmean(res[ix], w[ix])) for c, ix in groups.items()}
    sh = shrink_cells(cells, s2_eps)
    u = np.array([sh["u_hat"][(r["origin"], r["rung"])] for r in rows])
    e2 = res - u
    s2_side = _wvar(e2, w)
    by_r: dict = defaultdict(list)
    for i, r in enumerate(rows):
        by_r[r["rung"]].append(i)
    spread = {}
    for rg in sorted(by_r, key=lambda k: RUNG_VALUE.get(k, 0.0)):
        ix = by_r[rg]
        s2c = _wvar(e2[ix], w[ix])
        spread[rg] = {"n": len(ix), "s2": s2c,
                      "s_hat": shrunk_spread(len(ix), s2c, s2_side)}
    coef = {c: float(b) for c, b in zip(cols, beta)}
    a_by_src: dict = defaultdict(list)
    for c, b in coef.items():
        if c.startswith("a|"):
            a_by_src[c.split("|")[1]].append(b)
    model.update({
        "columns": cols, "coef": coef, "own_b": sorted([list(k) for k in own]),
        "a_source_mean": {s: float(np.mean(v)) for s, v in sorted(a_by_src.items())},
        "u": {f"{g}|{rg}": {"n": cells[(g, rg)][0], "mean_residual": cells[(g, rg)][1],
                            "u_hat": sh["u_hat"][(g, rg)]} for (g, rg) in sorted(cells)},
        "k_u": sh["k_u"], "tau2_u": sh["tau2_u"], "s2_eps": s2_eps, "s2_side": s2_side,
        "spread": spread,
    })
    return model


def predict(model: dict, rows: list[dict]) -> np.ndarray:
    """E for each row from a frozen table. A source-year the fit never saw takes that
    source's mean a (the serve-time centering absorbs the rest); a source rung cell with
    no own coefficient falls back to the pooled one, then to the mean of the own cells
    at that rung."""
    coef = model.get("coef") or {}
    if not coef:
        return np.zeros(len(rows))
    own = {tuple(k) for k in model.get("own_b") or []}
    amean = model.get("a_source_mean") or {}
    afall = float(np.mean(list(amean.values()))) if amean else 0.0
    bfall: dict = defaultdict(list)
    for c, b in coef.items():
        if c.startswith("b|"):
            bfall[c.split("|")[2]].append(b)
    u = model.get("u") or {}
    out = np.zeros(len(rows))
    for i, r in enumerate(rows):
        s = 0.0
        for c, v in _features(r, model["kind"], own):
            if c in coef:
                s += coef[c] * v
            elif c.startswith("a|"):
                s += amean.get(r["src"], afall) * v
            elif c.startswith("b|"):
                vals = bfall.get(r["rung"])
                s += (float(np.mean(vals)) if vals else 0.0) * v
        s += float((u.get(f"{r['origin']}|{r['rung']}") or {}).get("u_hat", 0.0))
        out[i] = s
    return out


def spread_of(model: dict, rung: str) -> float:
    s = ((model.get("spread") or {}).get(rung) or {}).get("s_hat")
    if s:
        return float(s)
    side = math.sqrt(float(model.get("s2_side") or 0.0))
    return side if side > 0 else 1.0


def recenter(rows: list[dict], x) -> np.ndarray:
    """Serve-time centering: each (source, step end year) to an omega-weighted mean of 0."""
    x = np.asarray(x, float).copy()
    groups: dict = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["src"], r["V"] + r["h"])].append(i)
    w = np.array([r["omega"] for r in rows], float)
    for ix in groups.values():
        x[ix] -= _wmean(x[ix], w[ix])
    return x


def mid_pit_scores(rows: list[dict]) -> np.ndarray:
    """Normal score of each y at the mid-PIT of its start rung's step distribution
    (the D0 check of section 6): Phi^-1(F(y-) + P(y) / 2), omega-weighted."""
    out = np.zeros(len(rows))
    by_r: dict = defaultdict(list)
    for i, r in enumerate(rows):
        by_r[r["rung"]].append(i)
    nd = NormalDist()
    for ix in by_r.values():
        y = np.array([rows[i]["y"] for i in ix], float)
        w = np.array([rows[i]["omega"] for i in ix], float)
        tot = float(w.sum())
        for k, i in enumerate(ix):
            less = float(w[y < y[k]].sum()) / tot
            eq = float(w[y == y[k]].sum()) / tot
            p = min(max(less + eq / 2.0, 1e-9), 1 - 1e-9)
            out[i] = nd.inv_cdf(p)
    return out


def row_credits(rows: list[dict], model_y: dict, model_w: dict | None = None, *,
                center: bool = True) -> dict:
    """Section 6: DV v = w - E^W (value units) and D0 z = (y - E) / s_hat[rung], each
    re-centered per (source, step end year) when `center`."""
    y = np.array([r["y"] for r in rows], float)
    E = predict(model_y, rows)
    s = np.array([spread_of(model_y, r["rung"]) for r in rows], float)
    z = (y - E) / s if len(rows) else np.zeros(0)
    out = {"E": E, "z": recenter(rows, z) if center else z}
    if model_w is not None:
        wv = np.array([r["w"] for r in rows], float)
        EW = predict(model_w, rows)
        v = wv - EW
        out.update({"EW": EW, "v": recenter(rows, v) if center else v})
    return out


def standardized_expectation(model: dict, rows: list[dict], rung: str) -> float | None:
    """E at a start rung with origin, level, age and source held at the rows' pooled
    mix: every row's rung set to `rung`, the predictions averaged with weights omega."""
    if not rows:
        return None
    moved = [dict(r, rung=rung) for r in rows]
    return _wmean(predict(model, moved), [r["omega"] for r in rows])


def credit_ratio(ew60: float | None, ew40: float | None, e60: float | None,
                 e40: float | None, s60: float | None, s40: float | None) -> dict:
    """The owner's 60 to 70 against 40 to 50 question as a credit ratio (section 6).
    today's FV-DvM+: (W70 - W60) / (W50 - W40) = 13.0 / 2.5 = 5.2; DV: (13.0 - E^W[60]) /
    (2.5 - E^W[40]); D0: ((10 - E[60]) / s_hat[60]) / ((10 - E[40]) / s_hat[40]). A
    ratio whose denominator is at or below 0 is "undefined", with both terms printed."""
    hi = value_of(70) - value_of(60)
    lo = value_of(50) - value_of(40)

    def ratio(num, den):
        if num is None or den is None:
            return {"numerator": num, "denominator": den, "ratio": None}
        if den <= 0:
            return {"numerator": num, "denominator": den, "ratio": "undefined"}
        return {"numerator": num, "denominator": den, "ratio": num / den}

    dv = ratio(None if ew60 is None else hi - ew60, None if ew40 is None else lo - ew40)
    d0 = ratio(None if (e60 is None or not s60) else (10.0 - e60) / s60,
               None if (e40 is None or not s40) else (10.0 - e40) / s40)
    return {"today": ratio(hi, lo), "DV": dv, "D0": d0,
            "inputs": {"EW60": ew60, "EW40": ew40, "E60": e60, "E40": e40,
                       "s_hat60": s60, "s_hat40": s40}}


# ---------------------------------------------------------------------------
# clubs, tenure and the player index (sections 7 and 9)
# ---------------------------------------------------------------------------

def _day(d) -> date:
    return d if isinstance(d, date) else datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def tenure_shares(start_day, end_day, events) -> dict[str, float]:
    """The registered fallback tenure split (section 7). `events` are (day, club, kind),
    kind "read" (the club printed on any source's read that day) or "trade" (a trades
    row's to_org); the club on a day is that of the latest event dated on or before it,
    a trade beating a read on the same day. The interval is [start, end) in days; a
    zero-length interval is one day at the start. The shares sum to 1."""
    d0, d1 = _day(start_day), _day(end_day)
    if d1 <= d0:
        d1 = d0 + timedelta(days=1)
    evs = sorted(((_day(d), c, 0 if k == "read" else 1) for d, c, k in events if c),
                 key=lambda e: (e[0], e[2]))
    cur, later = None, []
    for d, c, _k in evs:
        if d <= d0:
            cur = c
        elif d < d1:
            later.append((d, c))
    if cur is None:
        cur = later[0][1] if later else "UNK"
    days: Counter = Counter()
    t = d0
    for d, c in later:
        days[cur] += (d - t).days
        t, cur = d, c
    days[cur] += (d1 - t).days
    tot = sum(days.values())
    return {c: n / tot for c, n in sorted(days.items()) if n > 0}


def club_items(rows: list[dict], values) -> list[tuple[str, float, float]]:
    """(club, tau x omega, credit) for every tenure share of every row."""
    out = []
    for r, x in zip(rows, values):
        for club, t in (r.get("tau") or {}).items():
            if t > 0:
                out.append((club, float(t) * float(r["omega"]), float(x)))
    return out


def kish_n(weights) -> float:
    """Kish effective n: (sum a)^2 / sum a^2."""
    a = np.asarray(list(weights), float)
    s2 = float((a * a).sum())
    return float(a.sum() ** 2 / s2) if s2 > 0 else 0.0


def aggregate_clubs(items, k_org: float, clubs=None) -> dict:
    """D_o (weighted mean credit), N_o (Kish) and D~_o = D_o N_o / (N_o + k_org); a
    club with no rows enters at 0 with N 0."""
    by: dict = defaultdict(list)
    for club, a, x in items:
        by[club].append((a, x))
    out = {}
    for club in sorted(set(by) | set(clubs or ())):
        rows = by.get(club) or []
        a = np.array([t[0] for t in rows], float)
        x = np.array([t[1] for t in rows], float)
        D = _wmean(x, a) if rows else 0.0
        N = kish_n(a) if rows else 0.0
        out[club] = {"D": D, "N": N, "D_shrunk": D * N / (N + k_org) if N > 0 else 0.0,
                     "sum_a": float(a.sum()) if rows else 0.0,
                     "publish": N >= MIN_PUBLISH_N}
    return out


def k_org_mom(items) -> dict:
    """k_org = s2_within / tau2_org by the method of moments, bounded to [5, 50]:
    s2_within is the pooled weighted within-club variance of the credits, tau2_org =
    max(0, var_o(D_o) - mean_o(s2_within / N_o)); tau2_org = 0 takes the upper bound."""
    by: dict = defaultdict(list)
    for club, a, x in items:
        by[club].append((a, x))
    lo, hi = K_ORG_BOUNDS
    if len(by) < 2:
        return {"k_org": hi, "s2_within": None, "tau2_org": 0.0, "clubs": len(by)}
    num = den = 0.0
    Ds, Ns = [], []
    for rows in by.values():
        a = np.array([t[0] for t in rows], float)
        x = np.array([t[1] for t in rows], float)
        D = _wmean(x, a)
        num += float((a * (x - D) ** 2).sum())
        den += float(a.sum())
        Ds.append(D)
        Ns.append(kish_n(a))
    s2w = num / den if den > 0 else 0.0
    tau2 = max(0.0, float(np.var(Ds, ddof=1)) - float(np.mean([s2w / n for n in Ns if n > 0])))
    k = (s2w / tau2) if tau2 > 0 else hi
    return {"k_org": float(min(hi, max(lo, k))), "s2_within": s2w, "tau2_org": tau2,
            "clubs": len(by)}


def plus_index(values: dict) -> dict:
    """100 + 10 x (x - mean) / sd across the clubs (population sd, as the served
    DvM+), unclamped, rounded to nearest."""
    xs = np.array(list(values.values()), float)
    if xs.size == 0:
        return {}
    sd = float(xs.std())
    m = float(xs.mean())
    return {k: round_nearest(100 + 10 * ((float(v) - m) / sd if sd > 0 else 0.0))
            for k, v in values.items()}


def player_index(steps: dict, actives) -> dict:
    """Section 9: per player the mean of his own credits over his last 3 annual steps
    (each step's sources de-duplicated by omega), shrunk n / (n + 2), published
    100 + 10 x value / sd across the actives, rounded to nearest.
    `steps`: {player: {step end year: [(omega, credit), ...]}}."""
    shrunk = {}
    for pk, by_year in steps.items():
        last = sorted(by_year)[-PLAYER_STEPS:]
        vals = []
        for yr in last:
            om = np.array([t[0] for t in by_year[yr]], float)
            cr = np.array([t[1] for t in by_year[yr]], float)
            vals.append(_wmean(cr, om))
        n = len(vals)
        shrunk[pk] = (float(np.mean(vals)) * n / (n + PLAYER_SHRINK_K)) if n else 0.0
    act = [shrunk[p] for p in actives if p in shrunk]
    sd = float(np.std(act)) if act else 0.0
    return {p: round_nearest(100 + 10 * (v / sd if sd > 0 else 0.0))
            for p, v in shrunk.items() if p in set(actives)}


# ---------------------------------------------------------------------------
# H1: traits by origin group (section 10)
# ---------------------------------------------------------------------------

class _H1Fit:
    """One (side, trait, horizon, frame) design for H1: the full model of section 5
    (Theta_direct) and the source x year plus origin x rung cell model (Theta_total)."""

    def __init__(self, rows: list[dict], kind: str):
        self.rows = rows
        self.n = len(rows)
        self.y = np.array([r["y"] for r in rows], float)
        self.w = np.array([r["omega"] for r in rows], float)
        own = _own_b(rows)
        feats = [_features(r, kind, own) for r in rows]
        self.cols = sorted({c for f in feats for c, _v in f})
        self.Xd = _matrix(feats, self.cols)
        self.ocol = {g: self.cols.index(f"c|{g}") for g in MODEL_ORIGINS
                     if f"c|{g}" in self.cols}
        sv = sorted({(r["src"], r["V"]) for r in rows})
        svi = {k: i for i, k in enumerate(sv)}
        self.rungs = sorted({r["rung"] for r in rows}, key=lambda k: RUNG_VALUE.get(k, 0))
        self.rcode = np.array([self.rungs.index(r["rung"]) for r in rows], int)
        self.ocode = np.array([MODEL_ORIGINS.index(r["origin"]) for r in rows], int)
        self.A = np.zeros((self.n, len(sv)))
        self.A[np.arange(self.n), [svi[(r["src"], r["V"])] for r in rows]] = 1.0
        rw = Counter()
        for r in rows:
            rw[r["rung"]] += r["omega"]
        tot = sum(rw.values()) or 1.0
        self.rung_weight = np.array([rw[k] / tot for k in self.rungs], float)
        self.cluster, self.nclusters = _cluster_codes(rows)
        strata: dict = defaultdict(list)
        for i, r in enumerate(rows):
            strata[(r["src"], r["V"], r["rung"])].append(i)
        self.strata = [np.array(ix, int) for ix in strata.values() if len(ix) > 1]

    def _cells(self, ocode: np.ndarray) -> np.ndarray:
        nr = len(self.rungs)
        C = np.zeros((self.n, len(MODEL_ORIGINS) * nr))
        C[np.arange(self.n), ocode * nr + self.rcode] = 1.0
        return np.hstack([self.A, C])

    def _direct_X(self, ocode: np.ndarray) -> np.ndarray:
        if ocode is self.ocode:
            return self.Xd
        X = self.Xd.copy()
        for g, j in self.ocol.items():
            X[:, j] = (ocode == MODEL_ORIGINS.index(g)).astype(float)
        return X

    def thetas(self, w: np.ndarray | None = None,
               ocode: np.ndarray | None = None) -> dict:
        """{(g1, g2): (Theta_total, Theta_direct)}; NaN where a group carries no weight."""
        w = self.w if w is None else w
        ocode = self.ocode if ocode is None else ocode
        out = {}
        if self.n == 0:
            return {c: (float("nan"), float("nan")) for c in H1_CONTRASTS}
        bd = _solve(self._direct_X(ocode), self.y, w)
        if ocode is self.ocode:
            if getattr(self, "_Xt", None) is None:
                self._Xt = self._cells(ocode)
            Xt = self._Xt
        else:
            Xt = self._cells(ocode)
        bt = _solve(Xt, self.y, w)
        nsv, nr = self.A.shape[1], len(self.rungs)
        gw = {g: float(w[ocode == MODEL_ORIGINS.index(g)].sum()) for g in MODEL_ORIGINS}
        cellw = np.zeros((len(MODEL_ORIGINS), nr))
        np.add.at(cellw, (ocode, self.rcode), w)

        def c_of(g):
            if g == REF_ORIGIN:
                return 0.0
            j = self.ocol.get(g)
            return float(bd[j]) if j is not None else float("nan")

        for g1, g2 in H1_CONTRASTS:
            if gw[g1] <= 0 or gw[g2] <= 0 or gw[REF_ORIGIN] <= 0:
                direct = float("nan")
            else:
                direct = c_of(g1) - c_of(g2)
            i1, i2 = MODEL_ORIGINS.index(g1), MODEL_ORIGINS.index(g2)
            ok = (cellw[i1] > 0) & (cellw[i2] > 0)
            if not ok.any():
                total = float("nan")
            else:
                diff = bt[nsv + i1 * nr: nsv + (i1 + 1) * nr] - bt[nsv + i2 * nr: nsv + (i2 + 1) * nr]
                rwt = self.rung_weight * ok
                total = float((diff * rwt).sum() / rwt.sum())
            out[(g1, g2)] = (total, direct)
        return out

    def bootstrap(self, B: int, rng: np.random.Generator) -> dict:
        draws = {c: np.full((B, 2), np.nan) for c in H1_CONTRASTS}
        if self.n == 0:
            return draws
        for b in range(B):
            wb = self.w * _draw_counts(rng, self.nclusters)[self.cluster]
            for c, (t, d) in self.thetas(wb).items():
                draws[c][b] = (t, d)
        return draws

    def permutation(self, draws: int, rng: np.random.Generator) -> dict:
        out = {c: np.full((draws, 2), np.nan) for c in H1_CONTRASTS}
        if self.n == 0:
            return out
        for b in range(draws):
            oc = self.ocode.copy()
            for ix in self.strata:
                oc[ix] = self.ocode[rng.permutation(ix)]
            for c, (t, d) in self.thetas(ocode=oc).items():
                out[c][b] = (t, d)
        return out


def _sign(x) -> int:
    if x is None or not np.isfinite(x) or x == 0:
        return 0
    return 1 if x > 0 else -1


def h1_verdict(estimate: float, p_holm: float, powered: bool, checks: list,
               eras: list, g1: str, g2: str) -> str:
    """The verdict word of section 10: Holm-resolved on the primary frame, the same sign
    under every check (S1, S2, Pipeline alone, FanGraphs alone) and in at least two of
    the three eras; otherwise "not resolved". A positive contrast means g1's grades rise
    more than g2's."""
    if not powered:
        return "unpowered"
    s = _sign(estimate)
    if s == 0 or not (p_holm < ALPHA):
        return "not resolved"
    if any(_sign(c) != s for c in checks):
        return "not resolved"
    if sum(1 for e in eras if _sign(e) == s) < 2:
        return "not resolved"
    return f"easier for {g1} than {g2}" if s > 0 else f"harder for {g1} than {g2}"


def run_h1(pairs: list[dict], *, frame_name: str, B: int, perms: int, seed: int,
           log=None) -> dict:
    """H1 on both horizons: two Holm families of 39 per horizon (Theta_total and
    Theta_direct); verdict words only at 12 months; the descriptive traits outside."""
    eras = ERAS[frame_name]
    out: dict = {"families": {}, "descriptive": [], "eras": [list(e) for e in eras]}
    for h in HORIZONS:
        hz = f"{12 * h}m"
        cells = []
        for side in SIDES:
            for trait in TRAITS[side] + DESCRIPTIVE_TRAITS[side]:
                kind = "fv" if trait == "FV" else "tool"
                rows = analysis_rows(pairs, variant="primary", trait=trait, h=h, side=side)
                fit = _H1Fit(rows, kind)
                point = fit.thetas()
                descriptive = trait in DESCRIPTIVE_TRAITS[side]
                rng = np.random.default_rng(seed)
                boot = None if descriptive else fit.bootstrap(B, rng)
                perm = None if descriptive else fit.permutation(perms, np.random.default_rng(seed))
                comp = Counter(r["origin"] for r in rows if r["status"] == "completed")
                checks = {}
                for name, kw in (("S1", {"variant": "S1"}), ("S2", {"variant": "S2"}),
                                 ("pipeline", {"sources": ("mlb_pipeline",)}),
                                 ("fangraphs", {"sources": ("fangraphs",)})):
                    sub = analysis_rows(pairs, trait=trait, h=h, side=side, **kw)
                    checks[name] = _H1Fit(sub, kind).thetas()
                era_pts = []
                for lo, hi in eras:
                    sub = [r for r in rows if lo <= r["V"] <= hi]
                    era_pts.append(_H1Fit(sub, kind).thetas() if sub else None)
                for g1, g2 in H1_CONTRASTS:
                    powered = comp.get(g1, 0) >= H1_MIN_PAIRS and comp.get(g2, 0) >= H1_MIN_PAIRS
                    for k, est_name in enumerate(("total", "direct")):
                        est = point[(g1, g2)][k]
                        cell = {"side": side, "trait": trait, "contrast": f"{g1}-{g2}",
                                "estimand": est_name, "estimate": est,
                                "completed_pairs": [comp.get(g1, 0), comp.get(g2, 0)],
                                "powered": powered, "rows": len(rows)}
                        cell["checks"] = {n: v[(g1, g2)][k] for n, v in checks.items()}
                        cell["eras"] = [None if e is None else e[(g1, g2)][k] for e in era_pts]
                        if descriptive:
                            out["descriptive"].append(dict(cell, horizon=hz))
                            continue
                        d = boot[(g1, g2)][:, k]
                        cell["ci95"] = _ci95(d)
                        cell["p"] = p_two_sided(d, B) if (powered and np.isfinite(est)) else 1.0
                        band = _ci95(perm[(g1, g2)][:, k])
                        cell["permutation_band95"] = band
                        cell["inside_permutation_band"] = (
                            None if band[0] is None or not np.isfinite(est)
                            else bool(band[0] <= est <= band[1]))
                        cells.append(cell)
                if log:
                    log("h1", horizon=hz, side=side, trait=trait, rows=len(rows))
        for est_name in ("total", "direct"):
            fam = [c for c in cells if c["estimand"] == est_name]
            adj = holm([c["p"] for c in fam])
            for c, a in zip(fam, adj):
                c["p_holm"] = a
                g1, g2 = c["contrast"].split("-")
                if h == 1:
                    c["verdict"] = h1_verdict(
                        c["estimate"], a, c["powered"],
                        [c["checks"][n] for n in ("S1", "S2", "pipeline", "fangraphs")],
                        c["eras"], g1, g2)
                else:
                    c["verdict"] = None
            out["families"][f"{hz}|{est_name}"] = {"size": len(fam), "cells": fam}
    return out


# ---------------------------------------------------------------------------
# H2: the next rung from a higher rung (section 11)
# ---------------------------------------------------------------------------

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -35, 35)))


def logistic_fit(X: np.ndarray, yb: np.ndarray, w: np.ndarray, pen: np.ndarray,
                 lam: float = H2_L2, beta0: np.ndarray | None = None,
                 iters: int = 100) -> np.ndarray:
    """Weighted logistic regression by Newton's method, minimizing the weighted
    negative log-likelihood plus lam / 2 x the sum of squared penalized coefficients
    (pen is 1 for a penalized column, 0 for the intercept and the rung terms)."""
    beta = np.zeros(X.shape[1]) if beta0 is None else beta0.copy()
    ridge = lam * pen + 1e-9
    for _ in range(iters):
        p = _sigmoid(X @ beta)
        g = X.T @ (w * (yb - p)) - ridge * beta
        H = (X.T * (w * p * (1 - p))) @ X + np.diag(ridge)
        step = np.linalg.solve(H, g)
        beta = beta + step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return beta


class _H2Fit:
    """One (side, horizon, frame) H2 design: intercept, start rung (reference 40),
    then the penalized covariates of section 4 (source, list year, origin, level band,
    age_rel, agemiss)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.n = len(rows)
        self.y = np.array([r["y"] for r in rows], float)
        self.w = np.array([r["omega"] for r in rows], float)
        self.hr = [h2_rung(r["rung"]) for r in rows]
        cols, pen = ["icpt"], [0.0]
        self.rung_cols = {}
        for rg in H2_RUNGS:
            if rg != "40":
                self.rung_cols[rg] = len(cols)
                cols.append(f"r|{rg}")
                pen.append(0.0)
        cats = []
        for name, vals, ref in (("s", [r["src"] for r in rows], None),
                                ("V", [str(r["V"]) for r in rows], None),
                                ("g", [r["origin"] for r in rows], REF_ORIGIN),
                                ("L", [r["level"] for r in rows], REF_LEVEL)):
            levels = sorted(set(vals))
            ref = ref if ref in levels else (levels[0] if levels else None)
            for lv in levels:
                if lv != ref:
                    cats.append((len(cols), name, lv))
                    cols.append(f"{name}|{lv}")
                    pen.append(1.0)
        self.cols = cols
        self.pen = np.array(pen + [1.0, 1.0])
        X = np.zeros((self.n, len(cols) + 2))
        X[:, 0] = 1.0
        for i, r in enumerate(rows):
            j = self.rung_cols.get(self.hr[i])
            if j is not None:
                X[i, j] = 1.0
        keyval = {"s": "src", "V": "V", "g": "origin", "L": "level"}
        for j, name, lv in cats:
            X[:, j] = [1.0 if str(r[keyval[name]]) == lv else 0.0 for r in rows]
        X[:, -2] = [float(r["age_rel"]) if r.get("age_rel") is not None else 0.0 for r in rows]
        X[:, -1] = [1.0 if r.get("agemiss") else 0.0 for r in rows]
        self.X = X
        self.origin_cols = {lv: j for j, name, lv in cats if name == "g"}
        self.cluster, self.nclusters = _cluster_codes(rows)

    def _at(self, rung: str, origin: str | None = None) -> np.ndarray:
        Xr = self.X.copy()
        for j in self.rung_cols.values():
            Xr[:, j] = 0.0
        if rung in self.rung_cols:
            Xr[:, self.rung_cols[rung]] = 1.0
        if origin is not None:
            for j in self.origin_cols.values():
                Xr[:, j] = 0.0
            if origin in self.origin_cols:
                Xr[:, self.origin_cols[origin]] = 1.0
        return Xr

    def probs(self, k: int, w: np.ndarray | None = None, beta0=None,
              origin: str | None = None) -> tuple[dict, np.ndarray]:
        """P_k(r), standardized to the side's pooled covariate mix."""
        w = self.w if w is None else w
        yb = (self.y >= 5.0 * k).astype(float)
        beta = logistic_fit(self.X, yb, w, self.pen, beta0=beta0)
        return {rg: _wmean(_sigmoid(self._at(rg, origin) @ beta), w)
                for rg in H2_RUNGS}, beta

    def drift(self, w: np.ndarray | None = None, origin: str | None = None) -> dict:
        """m(r) = E[y | r, x], the WLS analogue standardized the same way."""
        w = self.w if w is None else w
        beta = _solve(self.X, self.y, w)
        return {rg: _wmean(self._at(rg, origin) @ beta, w) for rg in H2_RUNGS}


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def h2_trend(p1: dict) -> float:
    """The least-squares slope of logit P_1 on rung (40 = 0, 45 = 1, ..., 60+ = 4)."""
    xs = np.arange(len(H2_TREND_RUNGS), dtype=float)
    ys = np.array([_logit(p1[rg]) for rg in H2_TREND_RUNGS])
    xc = xs - xs.mean()
    return float((xc * (ys - ys.mean())).sum() / (xc * xc).sum())


def h2_contrast(p2: dict) -> float:
    """The owner's contrast: P_2(60+) - P_2(40)."""
    return float(p2["60+"] - p2["40"])


def run_h2(pairs: list[dict], *, B: int, seed: int, log=None) -> dict:
    """H2 per side (FV only): trend at 12 and 24 months, the 60+ against 40 two-rung
    contrast at 24 (primary) and 12 months; one Holm family of 8 per frame; the verdict
    needs the primary, S1 and S2 frames all resolved after Holm."""
    out: dict = {"tests": [], "descriptive": {}}
    comp: dict = {}
    for h in HORIZONS:
        for side in SIDES:
            rows = analysis_rows(pairs, variant="primary", h=h, side=side)
            comp[(h, side)] = Counter(h2_rung(r["rung"]) for r in rows
                                      if r["status"] == "completed")
    by_frame: dict = {}
    for variant in VARIANTS:
        tests = []
        for side in SIDES:
            for h in HORIZONS:
                hz = f"{12 * h}m"
                rows = analysis_rows(pairs, variant=variant, h=h, side=side)
                fit = _H2Fit(rows)
                if fit.n == 0:
                    p1 = p2 = m = None
                else:
                    p1, b1 = fit.probs(1)
                    p2, b2 = fit.probs(2)
                    m = fit.drift()
                desc = {"P1": p1, "P2": p2, "m": m, "rows": fit.n}
                if variant == "primary" and fit.n:
                    by_origin = {}
                    for g in MODEL_ORIGINS:
                        n_g = Counter(h2_rung(r["rung"]) for r in rows
                                      if r["origin"] == g and r["status"] == "completed")
                        keep = [rg for rg in H2_RUNGS if n_g.get(rg, 0) >= H2_MIN_PAIRS]
                        if keep:
                            pg1, _ = fit.probs(1, origin=g, beta0=b1)
                            pg2, _ = fit.probs(2, origin=g, beta0=b2)
                            mg = fit.drift(origin=g)
                            by_origin[g] = {rg: {"P1": pg1[rg], "P2": pg2[rg], "m": mg[rg]}
                                            for rg in keep}
                    desc["by_origin"] = by_origin
                out["descriptive"][f"{variant}|{side}|{hz}"] = desc
                c = comp[(h, side)]
                trend_ok = all(c.get(rg, 0) >= H2_MIN_PAIRS for rg in H2_TREND_RUNGS)
                contrast_ok = c.get("40", 0) >= H2_MIN_PAIRS and c.get("60+", 0) >= H2_MIN_PAIRS
                td = np.full(B, np.nan)
                cd = np.full(B, np.nan)
                if fit.n and (trend_ok or contrast_ok):
                    rng = np.random.default_rng(seed)
                    for b in range(B):
                        wb = fit.w * _draw_counts(rng, fit.nclusters)[fit.cluster]
                        q1, _ = fit.probs(1, w=wb, beta0=b1)
                        q2, _ = fit.probs(2, w=wb, beta0=b2)
                        td[b] = h2_trend(q1)
                        cd[b] = h2_contrast(q2)
                for test, ok, est, d in (
                        ("trend", trend_ok, None if p1 is None else h2_trend(p1), td),
                        ("contrast", contrast_ok, None if p2 is None else h2_contrast(p2), cd)):
                    tests.append({
                        "side": side, "horizon": hz, "test": test, "estimate": est,
                        "powered": ok, "ci95": _ci95(d),
                        "p": p_one_sided_below(d, B) if (ok and est is not None) else 1.0,
                        "role": ("primary" if (test == "trend" or hz == "24m")
                                 else "secondary"),
                    })
                if log:
                    log("h2", frame=variant, side=side, horizon=hz, rows=fit.n)
        adj = holm([t["p"] for t in tests])
        for t, a in zip(tests, adj):
            t["p_holm"] = a
        by_frame[variant] = tests
    for i, t in enumerate(by_frame["primary"]):
        res = [by_frame[v][i] for v in VARIANTS]
        if not t["powered"]:
            verdict = "unpowered"
        elif all(r["p_holm"] < ALPHA for r in res):
            verdict = "list grades rise less often from higher rungs"
        else:
            verdict = "not resolved"
        out["tests"].append(dict(t, frames={v: {"estimate": by_frame[v][i]["estimate"],
                                                "p": by_frame[v][i]["p"],
                                                "p_holm": by_frame[v][i]["p_holm"]}
                                            for v in VARIANTS},
                                 verdict=verdict))
    out["family_size"] = len(by_frame["primary"])
    out["completed_pairs_by_side_rung"] = {
        f"{12 * h}m|{side}": dict(sorted(c.items())) for (h, side), c in comp.items()}
    out["caveat"] = ("A pass reads 'list grades rise less often from higher rungs', never "
                     "'developing talent is harder there' (section 11).")
    return out


# ---------------------------------------------------------------------------
# validation (section 13)
# ---------------------------------------------------------------------------

ARMS: tuple[str, ...] = ("C0", "C0_mean", "DV", "D0")
COMPOSITION: tuple[str, ...] = ("share_HS", "share_COL", "share_IFA", "mean_start_rung",
                                "mean_age_rel", "pairs")


def _scored(rows: list[dict], models: dict) -> list[dict]:
    """Rows with their credits under one year's expectation (both sides), re-centered
    per (source, step end year) over the rows scored together."""
    out = []
    for side in SIDES:
        sr = [r for r in rows if r["side"] == side]
        if not sr:
            continue
        my, mw = models[side]
        cr = row_credits(sr, my, mw, center=False)
        for r, v, z in zip(sr, cr["v"], cr["z"]):
            out.append(dict(r, v=float(v), z=float(z)))
    if out:
        v = recenter(out, [r["v"] for r in out])
        z = recenter(out, [r["z"] for r in out])
        for r, a, b in zip(out, v, z):
            r["v"], r["z"] = float(a), float(b)
    return out


def _arm_values(rows: list[dict], clubs: list[str], k_org: dict) -> dict:
    out = {}
    w_items = club_items(rows, [r["w"] for r in rows])
    sums: dict = defaultdict(float)
    for club, a, x in w_items:
        sums[club] += a * x
    out["C0"] = {c: sums.get(c, 0.0) for c in clubs}
    agg = aggregate_clubs(w_items, 1.0, clubs)
    out["C0_mean"] = {c: agg[c]["D"] for c in clubs}
    for arm, key in (("DV", "v"), ("D0", "z")):
        agg = aggregate_clubs(club_items(rows, [r[key] for r in rows]), k_org[arm], clubs)
        out[arm] = {c: agg[c]["D_shrunk"] for c in clubs}
    return out


def _composition(rows: list[dict], clubs: list[str]) -> dict:
    acc: dict = {c: defaultdict(float) for c in clubs}
    for r in rows:
        for club, t in (r.get("tau") or {}).items():
            if club not in acc:
                continue
            a = t * r["omega"]
            d = acc[club]
            d["a"] += a
            d["HS"] += a * (r["origin"] == "HS")
            d["COL"] += a * (r["origin"] == "COL")
            d["IFA"] += a * (r["origin"] == "IFA")
            d["rung"] += a * RUNG_VALUE.get(r["rung"], 0.0)
            if r.get("age_rel") is not None:
                d["age"] += a * float(r["age_rel"])
                d["age_a"] += a
    out = {k: {} for k in COMPOSITION}
    for c in clubs:
        d = acc[c]
        a = d["a"]
        out["share_HS"][c] = d["HS"] / a if a else 0.0
        out["share_COL"][c] = d["COL"] / a if a else 0.0
        out["share_IFA"][c] = d["IFA"] / a if a else 0.0
        out["mean_start_rung"][c] = d["rung"] / a if a else 0.0
        out["mean_age_rel"][c] = d["age"] / d["age_a"] if d["age_a"] else 0.0
        out["pairs"][c] = a
    return out


def _mean_stat(per_year: list) -> float | None:
    vals = [v for v in per_year if v is not None and np.isfinite(v)]
    return float(np.mean(vals)) if vals else None


def run_validation(pairs: list[dict], *, frame_name: str, k_org: dict, B: int,
                   seed: int, log=None) -> dict:
    """Section 13 on 12-month primary FV rows: arms C0, C0 as a mean, DV and D0 at
    club-years Y, each year's expectation refit leaving out list years Y-1, Y and Y+1;
    V-P1, V-P2, V-S and V-C; the club-clustered bootstrap with paired deltas; the
    decision rule."""
    rows = analysis_rows(pairs, variant="primary", h=1)
    years = VALIDATION_YEARS[frame_name]
    clubs = sorted({c for r in rows for c in (r.get("tau") or {})})
    models: dict = {}

    def model_for(Y: int) -> dict:
        if Y not in models:
            leave = {Y - 1, Y, Y + 1}
            train = [r for r in rows if r["V"] not in leave and r["V"] + r["h"] not in leave]
            models[Y] = {s: (fit_expectation([r for r in train if r["side"] == s]),
                             fit_expectation([r for r in train if r["side"] == s],
                                             outcome="w"))
                         for s in SIDES}
        return models[Y]

    per_year = {}
    for Y in years:
        sc = _scored([r for r in rows if Y - INDEX_WINDOW_YEARS < r["V"] + r["h"] <= Y + 1],
                     model_for(Y))
        win = [r for r in sc if Y - INDEX_WINDOW_YEARS < r["V"] + r["h"] <= Y]
        one = [r for r in sc if r["V"] + r["h"] == Y]
        tgt = [r for r in sc if r["V"] == Y]
        sc_next = _scored([r for r in rows if r["V"] + r["h"] == Y + 1], model_for(Y + 1))
        if not tgt:
            continue
        raw = aggregate_clubs(club_items(tgt, [r["w"] for r in tgt]), 1.0, clubs)
        res = aggregate_clubs(club_items(tgt, [r["v"] for r in tgt]), 1.0, clubs)
        per_year[Y] = {
            "idx3": _arm_values(win, clubs, k_org),
            "idx1": _arm_values(one, clubs, k_org),
            "idx1_next": _arm_values(sc_next, clubs, k_org),
            "raw": {c: raw[c]["D"] for c in clubs if raw[c]["N"] > 0},
            "resid": {c: res[c]["D"] for c in clubs if res[c]["N"] > 0},
            "comp": _composition(win, clubs),
        }
        if log:
            log("validation", year=Y, target_rows=len(tgt), window_rows=len(win))

    def stats(sample: list[str], with_vc: bool = True) -> dict:
        out = {arm: {"VP1": [], "VP2": [], "VS": [], "VC": []} for arm in ARMS}
        for Y, d in per_year.items():
            keep = [c for c in sample if c in d["raw"]]
            for arm in ARMS:
                i3 = [d["idx3"][arm][c] for c in keep]
                out[arm]["VP1"].append(spearman(i3, [d["raw"][c] for c in keep]))
                out[arm]["VP2"].append(spearman(i3, [d["resid"][c] for c in keep]))
                out[arm]["VS"].append(spearman([d["idx1"][arm][c] for c in sample],
                                               [d["idx1_next"][arm][c] for c in sample]))
                if with_vc:
                    cm = [spearman(i3, [d["comp"][k][c] for c in keep]) for k in COMPOSITION]
                    cm = [abs(x) for x in cm if x is not None]
                    out[arm]["VC"].append(max(cm) if cm else None)
        return {arm: {k: _mean_stat(v) for k, v in s.items()} for arm, s in out.items()}

    point = stats(clubs)
    rng = np.random.default_rng(seed)
    deltas = {(arm, st): np.full(B, np.nan) for arm in ("DV", "D0") for st in ("VP1", "VP2", "VS")}
    for b in range(B):
        sample = [clubs[i] for i in rng.integers(0, len(clubs), len(clubs))] if clubs else []
        s = stats(sample, with_vc=False)
        for arm in ("DV", "D0"):
            for st in ("VP1", "VP2", "VS"):
                a, c0 = s[arm][st], s["C0"][st]
                if a is not None and c0 is not None:
                    deltas[(arm, st)][b] = a - c0
    block: dict = {"years": sorted(per_year), "clubs": len(clubs), "point": point,
                   "deltas": {}}
    for st in ("VP1", "VP2", "VS"):
        ps = {arm: p_two_sided(deltas[(arm, st)], B) for arm in ("DV", "D0")}
        adj = holm([ps["DV"], ps["D0"]])
        for arm, a in zip(("DV", "D0"), adj):
            d = deltas[(arm, st)]
            fin = d[np.isfinite(d)]
            pa, pc = point[arm][st], point["C0"][st]
            block["deltas"][f"{arm}|{st}"] = {
                "delta": None if (pa is None or pc is None) else pa - pc,
                "ci95": _ci95(d),
                "lower_95_one_sided": float(np.percentile(fin, 5)) if fin.size else None,
                "p": ps[arm], "p_holm": a if st in ("VP2", "VS") else None,
            }
    block["decision"] = {arm: decide(block, arm) for arm in ("DV", "D0")}
    block["note"] = ("V-S is not validity: club composition persists, so it is read only "
                     "beside V-C.")
    return block


def decide(block: dict, arm: str = "DV") -> dict:
    """The decision rule of section 13 for one arm against C0, with the copy the
    artifact allows."""
    pt = block["point"]
    vc, vc0 = pt[arm]["VC"], pt["C0"]["VC"]
    c1 = vc is not None and (vc <= VC_MAX or (vc0 is not None and vc <= vc0 - VC_BELOW_C0))
    p1 = block["deltas"][f"{arm}|VP1"]
    c2 = p1["lower_95_one_sided"] is not None and p1["lower_95_one_sided"] > NONINF_MARGIN
    losses = [st for st in ("VP2", "VS")
              if (block["deltas"][f"{arm}|{st}"]["p_holm"] or 1.0) < ALPHA
              and (block["deltas"][f"{arm}|{st}"]["delta"] or 0.0) < 0]
    c3 = not losses
    win_p1 = (p1["p"] < ALPHA and (p1["delta"] or 0.0) > 0)
    p2 = block["deltas"][f"{arm}|VP2"]
    win_p2 = ((p2["p_holm"] or 1.0) < ALPHA and (p2["delta"] or 0.0) > 0)
    copy = []
    if win_p1:
        copy.append("predicts next-year farm growth better than the previous index")
    if win_p2:
        copy.append("predicts next year's growth above expectation better")
    if not copy:
        copy.append("difficulty-adjusted; ties the previous index on prediction")
    return {"composition_check": c1, "non_inferior_vp1": c2,
            "holm_losses": losses, "no_holm_loss": c3,
            "verdict": "SHIP CANDIDATE" if (c1 and c2 and c3) else "NO SHIP",
            "copy": copy, "composition_max": vc, "composition_max_c0": vc0}


# ---------------------------------------------------------------------------
# the whole read, on any pairs (the look's rows, or a fixture for the dry run)
# ---------------------------------------------------------------------------

def _tool_traits(side: str) -> tuple[str, ...]:
    return tuple(t for t in TRAITS[side] if t != "FV") + DESCRIPTIVE_TRAITS[side]


def run_analysis(pairs: list[dict], *, frame_name: str, B: int = BOOT_B,
                 perms: int = PERM_DRAWS, seed: int = SEED, log=None) -> tuple[dict, dict]:
    """(table, eval): the frozen table of data/dvm_difficulty.json and the read of
    data/dvm_difficulty_eval.json, computed on `pairs`. Pure; writes nothing."""
    table: dict = {"frame": frame_name, "censoring": censoring_census(pairs),
                   "value_table": {str(k): v for k, v in VALUE_TABLE.items()},
                   "models": {}, "tool_models": {}, "k_org": {}, "ratio": {}}
    credits_rows: list[dict] = []
    for h in HORIZONS:
        hz = f"{12 * h}m"
        for side in SIDES:
            rows = analysis_rows(pairs, h=h, side=side)
            my = fit_expectation(rows)
            mw = fit_expectation(rows, outcome="w")
            table["models"][f"{hz}|{side}"] = {"y": my, "w": mw}
            if rows:
                ew60 = standardized_expectation(mw, rows, "60")
                ew40 = standardized_expectation(mw, rows, "40")
                e60 = standardized_expectation(my, rows, "60")
                e40 = standardized_expectation(my, rows, "40")
                table["ratio"][f"{hz}|{side}"] = credit_ratio(
                    ew60, ew40, e60, e40, spread_of(my, "60"), spread_of(my, "40"))
            if h == 1 and rows:
                cr = row_credits(rows, my, mw)
                pit = recenter(rows, mid_pit_scores(rows))
                for r, v, z, q in zip(rows, cr["v"], cr["z"], pit):
                    credits_rows.append(dict(r, v=float(v), z=float(z), pit=float(q)))
            if log:
                log("model", horizon=hz, side=side, rows=len(rows))
    clubs = sorted({c for r in credits_rows for c in (r.get("tau") or {})})
    clubs_out = {}
    for arm, key in (("DV", "v"), ("D0", "z"), ("D0_pit", "pit")):
        items = club_items(credits_rows, [r[key] for r in credits_rows])
        k = k_org_mom(items)
        table["k_org"][arm] = k
        agg = aggregate_clubs(items, k["k_org"], clubs)
        clubs_out[arm] = agg
    table["club_frame_index"] = {
        arm: {c: {"D": a["D"], "N": a["N"], "D_shrunk": a["D_shrunk"],
                  "publish": a["publish"]} for c, a in agg.items()}
        for arm, agg in clubs_out.items() if arm != "D0_pit"}
    pit_corr = pearson([clubs_out["D0"][c]["D_shrunk"] for c in clubs],
                       [clubs_out["D0_pit"][c]["D_shrunk"] for c in clubs])
    for side in SIDES:
        for trait in _tool_traits(side):
            rows = analysis_rows(pairs, trait=trait, h=1, side=side)
            mt = fit_expectation(rows, kind="tool")
            table["tool_models"][f"{side}|{trait}"] = mt
            if rows:
                z = row_credits(rows, mt)["z"]
                table["k_org"][f"tool|{side}|{trait}"] = k_org_mom(club_items(rows, z))
    table["residuals_12m"] = [
        {"club": c, "tau": t, "pk": r["pk"], "src": r["src"], "V": r["V"],
         "step_end": r["V"] + r["h"], "side": r["side"], "omega": r["omega"],
         "v": r["v"], "z": r["z"]}
        for r in credits_rows for c, t in sorted((r.get("tau") or {}).items())]
    ev: dict = {"frame": frame_name, "seed": seed, "bootstrap_draws": B,
                "permutation_draws": perms}
    ev["d0_pit_club_correlation"] = pit_corr
    ev["d0_pit_note"] = (None if pit_corr is None or pit_corr >= PIT_CORR_FLOOR else
                         "the D0 club index and its mid-PIT normal-score version "
                         "correlate below 0.9")
    ev["h1"] = run_h1(pairs, frame_name=frame_name, B=B, perms=perms, seed=seed, log=log)
    ev["h2"] = run_h2(pairs, B=B, seed=seed, log=log)
    ev["validation"] = run_validation(
        pairs, frame_name=frame_name,
        k_org={"DV": table["k_org"]["DV"]["k_org"], "D0": table["k_org"]["D0"]["k_org"]},
        B=B, seed=seed, log=log)
    ev["ratio"] = table["ratio"]
    ev["decision"] = ev["validation"]["decision"]["DV"]
    ev["failed_arms"] = failed_arm_blocks(ev["validation"])
    return table, ev


def failed_arm_blocks(validation: dict) -> dict:
    """Section 13: every arm the decision rule does not pass, as a block of this eval
    artifact (never a new eval file): its decision, point statistics and deltas."""
    out = {}
    for arm, d in sorted((validation.get("decision") or {}).items()):
        if (d or {}).get("verdict") == "SHIP CANDIDATE":
            continue
        out[arm] = {"decision": d,
                    "point": (validation.get("point") or {}).get(arm),
                    "deltas": {k: v for k, v in (validation.get("deltas") or {}).items()
                               if str(k).split("|")[0] == arm}}
    return out


def clean_json(obj):
    """JSON-safe copy: numpy scalars to Python, NaN and infinities to None, tuple keys
    joined with '|'."""
    if isinstance(obj, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): clean_json(v)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if math.isfinite(x) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return clean_json(obj.tolist())
    return obj


def summary_lines(table: dict, ev: dict) -> list[str]:
    """The printed read. The first line names the frame."""
    L = [f"FRAME: {ev['frame']}"]
    for hz, c in table["censoring"].items():
        L.append(f"censoring {hz} (pooled over side and rung): "
                 + ", ".join(f"{k} {v}" for k, v in c.items()))
    for key, r in sorted(table["ratio"].items()):
        parts = []
        for name in ("today", "DV", "D0"):
            x = r[name]
            rv = x["ratio"]
            rv = "undefined" if rv == "undefined" else (None if rv is None else round(rv, 3))
            parts.append(f"{name} {rv} ({_fmt(x['numerator'])} / {_fmt(x['denominator'])})")
        L.append(f"60 to 70 over 40 to 50, {key}: " + "; ".join(parts))
    for fam, blk in ev["h1"]["families"].items():
        words = [f"{c['side']} {c['trait']} {c['contrast']}: {c['verdict']}"
                 for c in blk["cells"] if c.get("verdict") not in (None, "not resolved",
                                                                    "unpowered")]
        L.append(f"H1 {fam} ({blk['size']} cells): " + ("; ".join(words) or "none resolved"))
    for t in ev["h2"]["tests"]:
        L.append(f"H2 {t['side']} {t['horizon']} {t['test']}: estimate {_fmt(t['estimate'])}, "
                 f"p_holm {_fmt(t['p_holm'])}; {t['verdict']}")
    val = ev["validation"]
    for arm in ARMS:
        pt = val["point"][arm]
        L.append(f"validation {arm}: " + ", ".join(f"{k} {_fmt(v)}" for k, v in pt.items()))
    d = ev["decision"]
    L.append(f"DECISION (DV): {d['verdict']}; composition max {_fmt(d['composition_max'])} "
             f"(C0 {_fmt(d['composition_max_c0'])}); copy: {' | '.join(d['copy'])}")
    if ev.get("d0_pit_note"):
        L.append(ev["d0_pit_note"])
    return L


def _fmt(x) -> str:
    if x is None:
        return "None"
    if isinstance(x, str):
        return x
    return f"{float(x):.4f}"


# ---------------------------------------------------------------------------
# fixtures (the dry run and the tests): synthetic rows, never the store
# ---------------------------------------------------------------------------

def fixture_pairs(seed: int = SEED, players: int = 400, *, clubs: int = 30) -> list[dict]:
    """Synthetic study rows with every kind of null the look can meet: unknown origins,
    unresolved levels, missing ages, censored rows of every status, tool grades absent at
    the start or the end, split tenures. Built from a seeded generator; no store read."""
    rng = np.random.default_rng(seed)
    club_names = [f"C{i:02d}" for i in range(clubs)]
    years = [y for y in range(2011, 2027) if y not in RESERVED_LV]
    origins = ("HS", "COL", "JUCO", "IFA", "PRO", "UNK")
    tools = {"hit": ("hit", "game_pwr", "raw_pwr", "speed", "field", "throw", "pitch_sel",
                     "bat_ctrl"),
             "pit": ("fb", "sl", "cb", "ch", "cmd", "ct")}
    pairs = []
    for i in range(players):
        pk = f"p{i:04d}"
        side = SIDES[int(rng.integers(0, 2))]
        origin = origins[int(rng.choice(6, p=[0.3, 0.3, 0.05, 0.25, 0.05, 0.05]))]
        first = years[int(rng.integers(0, len(years) - 1))]
        g = float(rng.choice([35, 40, 40, 45, 45, 47.5, 50, 50, 55, 60, 65]))
        level = [None, "pre-pro", "DSL/CPX", "A/A+", "AA/AAA"][int(rng.integers(0, 5))]
        age_rel = None if rng.random() < 0.2 else float(np.clip(rng.normal(0, 1.2), -3, 3))
        home = club_names[int(rng.integers(0, clubs))]
        srcs = [s for s in SOURCES if rng.random() < 0.7] or [SOURCES[0]]
        base_tools = {k: float(rng.choice([30, 35, 40, 45, 50, 55, 60]))
                      for k in tools[side] if rng.random() < 0.85}
        for V in [y for y in years if first <= y < first + 4]:
            for h in HORIZONS:
                if V + h not in years:
                    continue
                for src in srcs:
                    st = STATUSES[int(rng.choice(4, p=[0.6, 0.1, 0.25, 0.05]))]
                    drift = float(rng.choice([-5, 0, 0, 0, 5, 10]))
                    if origin == "HS":
                        drift += float(rng.choice([0, 0, 5]))
                    if st == "completed":
                        g1 = min(80.0, max(20.0, g + drift))
                    elif st == "graduated":
                        g1 = g + float(rng.choice([0, 5]))
                    else:
                        g1 = min(g, 35.0) - DROP_RUNG
                    t0 = {k: v for k, v in base_tools.items() if rng.random() < 0.9}
                    t1 = ({k: v + float(rng.choice([-5, 0, 5])) for k, v in t0.items()
                           if rng.random() < 0.85}
                          if st in ("completed", "graduated") else None)
                    pres = ({k: v - float(rng.choice([5, 10, 15])) for k, v in t0.items()}
                            if src == "fangraphs" else {})
                    tau = {home: 1.0}
                    if rng.random() < 0.08:
                        other = club_names[int(rng.integers(0, clubs))]
                        split = float(rng.uniform(0.2, 0.8))
                        tau = {home: split, other: 1.0 - split} if other != home else tau
                    pairs.append({
                        "src": src, "pk": pk, "V": V, "h": h, "side": side,
                        "rung": rung_of(g), "g0": g, "g1": g1, "status": st,
                        "tools0": t0, "tools1": t1, "present0": pres, "origin": origin,
                        "level": level, "age_rel": age_rel, "agemiss": age_rel is None,
                        "tau": tau,
                    })
        g = min(70.0, g + float(rng.choice([0, 0, 5])))
    return pairs


def run_dry(out_dir: Path, *, B: int = 40, perms: int = 10, players: int = 400) -> dict:
    """The crash protocol's dry run (section 14): the whole reporting path on fixtures
    with nulls, written to out_dir only (never data/)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = _probe_logger(out_dir)
    pairs = fixture_pairs(players=players)
    log("dry_run_start", pairs=len(pairs))
    table, ev = run_analysis(pairs, frame_name="COMPLEMENT", B=B, perms=perms, log=log)
    table["receipt"] = {"generated_at": _now(), "fixture": True, "pairs": len(pairs)}
    ev["receipt"] = {"generated_at": _now(), "fixture": True}
    table = {"generated_at": table["receipt"]["generated_at"], **table}
    ev = {"generated_at": ev["receipt"]["generated_at"], **ev}
    (out_dir / TABLE_ARTIFACT).write_text(
        json.dumps(clean_json(table), indent=1, allow_nan=False), encoding="utf-8")
    (out_dir / EVAL_ARTIFACT).write_text(
        json.dumps(clean_json(ev), indent=1, allow_nan=False), encoding="utf-8")
    text = "\n".join(summary_lines(table, ev)) + "\n"
    (out_dir / "dry_run.txt").write_text(text, encoding="utf-8")
    log("dry_run_end")
    return {"table": table, "eval": ev, "text": text}


# ---------------------------------------------------------------------------
# the guards and the one look (sections 2, 14 and 15)
# ---------------------------------------------------------------------------

_DATED_ENTRY_RE = re.compile(r"^\s*(#{2,4}\s+|\*\*)?\(?\d{4}-\d{2}-\d{2}")


def results_recorded(text: str | None, number: str) -> bool:
    """True when the '## <number>.' results section of a gate document holds a dated
    entry (a line that opens with a date, as a heading or in bold)."""
    body = _section(text or "", number)
    return any(_DATED_ENTRY_RE.match(ln) for ln in body.splitlines())


def rlv_record_in_doc(text: str | None, root: Path = ROOT) -> bool:
    """The R-LV look record in EFV_V2_GATE.md: a dated entry in part 9, or (amendment
    A-2) its section 11 naming the confirmation artifact, which exists on disk."""
    if results_recorded(text, "9"):
        return True
    body = _section(text or "", RLV_RECORD_SECTION)
    return (Path(RLV_RECORD_ARTIFACT).name in body
            and (Path(root) / RLV_RECORD_ARTIFACT).exists())


def early_read_waived(today: str, waiver: dict | None = OWNER_WAIVER) -> bool:
    """Amendment A-1: True when the owner's waiver covers a FULL-frame look on `today`."""
    return bool(waiver) and str(today)[:10] >= str(waiver.get("from") or "9999")


def look_frame(today: str, *, eta_text: str | None, dvm_text: str | None,
               anchor_text: str | None, efv_v2_text: str | None,
               rlv_record: str | None = RLV_LOOK_RECORD,
               waiver: dict | None = OWNER_WAIVER, root: Path = ROOT) -> str:
    """The clock of section 14: "FULL" or "COMPLEMENT", or ClockError. Never on a
    registered look day; only after the ETA record, this gate's registration and the
    PROSPECT_ANCHOR look record; FULL on or after 2026-12-01 when the R-LV record exists
    (in EFV_V2_GATE AND as RLV_LOOK_RECORD, which lifts F-R1 in the frame), or earlier
    under the owner's waiver (amendment A-1, an OWNER-WAIVED EARLY READ); COMPLEMENT on
    or after 2027-01-31 when it does not."""
    today = str(today)[:10]
    if today in LOOK_DAYS:
        raise ClockError(f"{today} is a registered look day; no other look runs on it")
    assert_growth_allowed(eta_text, dvm_text)
    if not results_recorded(anchor_text, "18"):
        raise ClockError(f"{ANCHOR_GATE_DOC} section 18 holds no look record; this look "
                         "waits for it on every path (gate section 14)")
    rec_doc = rlv_record_in_doc(efv_v2_text, root)
    rec_code = excluded_list_years(rlv_record) != RESERVED_LV
    if rec_doc != rec_code:
        raise ClockError("the R-LV look record in EFV_V2_GATE and RLV_LOOK_RECORD "
                         "disagree; set the constant by a dated amendment first")
    if rec_doc:
        if today < LOOK_EARLIEST_FULL and not early_read_waived(today, waiver):
            raise ClockError(f"the FULL-frame look opens {LOOK_EARLIEST_FULL}")
        return "FULL"
    if today < LOOK_EARLIEST_COMPLEMENT:
        raise ClockError(f"no R-LV record: the COMPLEMENT-frame look opens "
                         f"{LOOK_EARLIEST_COMPLEMENT}")
    return "COMPLEMENT"


TENURE_VAL4 = "VAL_4 org calendar (dev_attribution, gate amendment A-3)"
TENURE_FALLBACK = "fallback (gate section 7)"


def tenure_source(root: Path = ROOT) -> str:
    """P-1: VAL_4's org calendar when VAL_4 is committed (its design directory exists;
    amendment A-3 adds the reader, val4_club_events), else the registered fallback."""
    if (Path(root) / VAL4_DIR).exists():
        return TENURE_VAL4
    return TENURE_FALLBACK


def _process_lines() -> list[tuple[int, str]] | None:
    """(pid, command line) of every process, from the operating system's own lister
    (PowerShell on Windows, ps elsewhere); None when the listing fails."""
    import subprocess
    if os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-Command",
               "Get-CimInstance Win32_Process | ForEach-Object "
               "{ [string]$_.ProcessId + ' ' + [string]$_.CommandLine }"]
    else:
        cmd = ["ps", "-eo", "pid=,args="]
    try:
        text = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                              check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    out = []
    for line in text.splitlines():
        head, _, rest = line.strip().partition(" ")
        if head.isdigit():
            out.append((int(head), rest))
    return out


def busy_processes(lines: list[tuple[int, str]] | None = None) -> list[str]:
    """Other processes running a pipeline, a nightly job or a test session (this
    process and its parent excluded). A failed listing counts as busy: the look does
    not run blind."""
    if lines is None:
        lines = _process_lines()
    if lines is None:
        return ["the process listing failed"]
    skip = {os.getpid(), os.getppid()}
    return [f"{pid}: {cmd[:120]}" for pid, cmd in lines
            if pid not in skip and not _SHELL_WRAPPER_RE.match(cmd or "")
            and any(t in cmd.lower() for t in BUSY_TOKENS)]


#: Gate amendment A-6 (2026-10-14): a shell wrapper (bash -c, sh -c, powershell
#: -Command) only names the command it runs, which shows in the listing as its own
#: process; a wrapper whose text merely mentions a token (a tasklist grep for "pytest")
#: is not a pipeline or a test session. A script run by a shell without -c still counts.
_SHELL_WRAPPER_RE = re.compile(
    r'^\s*(?:"(?:[^"]*[\\/])?(?:bash|sh|powershell|pwsh)(?:\.exe)?"'
    r'|(?:[^"\s]*[\\/])?(?:bash|sh|powershell|pwsh)(?:\.exe)?)'
    r'\s+(?:-NoProfile\s+)?-(?:c|Command)\b', re.I)


def stored_look(data_dir: Path = DATA_DIR) -> dict | None:
    p = Path(data_dir) / EVAL_ARTIFACT
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


class _Tee:
    def __init__(self, stream, path: Path):
        self.stream = stream
        self.f = open(path, "a", encoding="utf-8")

    def write(self, s):
        self.stream.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.stream.flush()
        self.f.flush()


def _probe_logger(task_dir: Path):
    path = Path(task_dir) / "PROBES.jsonl"

    def log(step: str, **kw):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(clean_json({"t": _now(), "step": step, **kw})) + "\n")
    return log


def _owner_question(task_dir: Path, title: str, body: str) -> None:
    (Path(task_dir) / "OWNER_QUESTION.md").write_text(
        f"# {title}\n\n{body}\n", encoding="utf-8")


def pairs_from_frame(frame: dict, *, debut: dict, club_events: dict, canon,
                     active_in) -> tuple[list[dict], Counter]:
    """The study rows from a built frame (section 3 censoring, section 7 tenures).
    club_events: {player_key: [(day, club, kind)]}; canon: the club canonicalizer;
    active_in(person, season): True, False or None (unknown) for affiliated activity."""
    reads, rvm = frame["reads"], frame["rvm"]
    lows: dict = {}
    list_low: dict = {}
    for (src, pk, V), rd in reads.items():
        g = grade_value(rd["fv"], rd["plus"])
        k = (src, V, canon(rd["org"]))
        lows[k] = min(lows.get(k, g), g)
        list_low[(src, V)] = min(list_low.get((src, V), g), g)
    census: Counter = Counter()
    out = []
    for sl in frame["slots"]:
        if not sl["in_frame"]:
            census["rvm_end_out"] += 1
            continue
        src, pk, V = sl["key"]
        h = sl["h"]
        st = frame["starts"][sl["key"]]
        rd = reads[sl["key"]]
        g0 = grade_value(rd["fv"], rd["plus"])
        close = f"{V + h}{WINDOW_END_MMDD}"
        evs = club_events.get(pk) or [(rd["date"], canon(rd["org"]), "read")]
        if sl["completed"]:
            er = reads[(src, pk, V + h)]
            status, g1, tools1, end_day = ("completed", grade_value(er["fv"], er["plus"]),
                                           er.get("tools") or {}, er["date"])
        else:
            dd = debut.get(pk)
            later = [v for v in range(V + 1, V + h + 1)
                     if (src, pk, v) in reads or (src, pk, v) in rvm]
            last = max(later) if later else None
            if dd and dd[:10] < close and last is not None and (src, pk, last) in rvm:
                census["rvm_graduate_out"] += 1
                continue
            gr = reads[(src, pk, last)] if last is not None else rd
            end_day = min(close, dd[:10]) if dd else close
            club = _club_on(evs, close)
            person = st.get("person")
            act = None
            if person:
                a1, a2 = active_in(person, V + h - 1), active_in(person, V + h)
                act = True if (a1 or a2) else (False if (a1 is False and a2 is False)
                                              else None)
            status, g1 = code_missing_end(
                g0, debut_day=dd, end_close=close, grad_grade=grade_value(gr["fv"], gr["plus"]),
                club_lowest=lows.get((src, V + h, club), list_low.get((src, V + h))),
                affiliated=act)
            tools1 = (gr.get("tools") or {}) if status == "graduated" else None
            if g1 is None:
                census["no_end_grade_out"] += 1
                continue
        census[status] += 1
        out.append({
            "src": src, "pk": pk, "V": V, "h": h, "side": st["side"], "rung": st["rung"],
            "g0": g0, "g1": g1, "status": status, "tools0": rd.get("tools") or {},
            "tools1": tools1, "present0": rd.get("present") or {},
            "origin": st.get("origin"), "level": st.get("level_band"),
            "age_rel": st.get("age_rel"), "agemiss": st.get("agemiss"),
            "tau": tenure_shares(rd["date"], end_day, evs), "person": st.get("person"),
        })
    return out, census


def _club_on(events, day: str) -> str | None:
    """The club of the latest event dated on or before `day` (a trade wins a tie)."""
    d = _day(day)
    cur = None
    for e_day, club, kind in sorted(((_day(a), b, 0 if c == "read" else 1)
                                     for a, b, c in events if b), key=lambda e: (e[0], e[2])):
        if e_day <= d:
            cur = club
    return cur


def load_club_events(con: sqlite3.Connection, players: set, debut: dict, *,
                     excluded: frozenset[int], canon) -> dict:
    """{player_key: [(day, club, kind)]}: the club printed on every read of any source
    (international and overseas boards excluded, the reserved windows and R-VM inputs
    skipped as everywhere in this lab) and every trades row's to_org."""
    out: dict = defaultdict(list)
    for pk, d, org, label in con.execute(
            "SELECT player_key, snapshot_date, org, interval_label FROM snapshots "
            "WHERE org IS NOT NULL ORDER BY snapshot_date, id"):
        if pk not in players or not d or not _is_list_label(label):
            continue
        V = int(d[:4])
        lo, hi = window_bounds(V, None)
        in_window = lo <= d[:10] < hi
        if in_window and (V in excluded or is_rvm_input(V, debut.get(pk))):
            continue
        out[pk].append((d[:10], canon(org), "read"))
    for pk, d, to_org in con.execute(
            "SELECT player_key, trade_date, to_org FROM trades WHERE to_org IS NOT NULL"):
        if pk in players and d:
            out[pk].append((str(d)[:10], canon(to_org), "trade"))
    return dict(out)


# ---------------------------------------------------------------------------
# VAL_4's org calendar as the tenure split (gate section 7, P-1; amendment A-3)
# ---------------------------------------------------------------------------

#: The club code of an unaffiliated stretch in the tenure events. Its share is dropped
#: after the split without renormalizing, so growth while unaffiliated credits nobody
#: (dev_attribution step 3; the same rule as dvm_difficulty_serve.UNAFFILIATED).
UNAFFILIATED = "__unaffiliated__"
#: The store the season affiliation map (staff_units) is read from. The frozen store
#: predates that table; it holds no grade, and its rows are pinned by a content hash at
#: the look's start and end.
LIVE_DB = ROOT / "prospects.db"


def staff_units_map(db: Path = LIVE_DB) -> tuple[dict, str | None]:
    """((team_id, season) -> club, sha256 of the rows read) through VAL_4's own loader;
    ({}, None) when the table or the store is absent (VAL_4 then resolves by name)."""
    import dev_attribution as DA  # noqa: PLC0415
    if not Path(db).exists():
        return {}, None
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        try:
            rows = sorted(con.execute(
                "SELECT team_id, season, org_code FROM staff_units WHERE team_id IS NOT "
                "NULL AND org_code IS NOT NULL").fetchall())
        except sqlite3.OperationalError:
            return {}, None
        team_org = DA.load_team_org_map(con)
    finally:
        con.close()
    digest = hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()
    return team_org, digest


def val4_club_events(con: sqlite3.Connection, players: set, debut: dict, *,
                     excluded: frozenset[int], today: str, team_org: dict) -> tuple[dict, dict]:
    """({player_key: [(day, club, "read")]}, diagnostics) from VAL_4's org calendar,
    dev_attribution.build on the store `con` reads: each tenure opens with its club on
    its start day, an unaffiliated tenure with UNAFFILIATED. The build's inputs are the
    store's own rows: the observations skip every read this lab never loads (F-R1 while
    it holds, F-R2 always); the current club is the club on the player's latest list
    read, the listed club the latest one on or before his debut; trades rows are
    de-duplicated on (date, from, to). A player VAL_4 gives no calendar keeps the
    fallback events of pairs_from_frame."""
    import dev_attribution as DA  # noqa: PLC0415
    obs: dict = defaultdict(lambda: defaultdict(dict))
    last_any: dict = {}
    last_before: dict = {}
    for pk, src, d, fv, org, status, label in con.execute(
            "SELECT player_key, source, snapshot_date, fv, org, status, interval_label "
            "FROM snapshots WHERE snapshot_date IS NOT NULL ORDER BY snapshot_date, id"):
        if pk not in players or not d:
            continue
        day = str(d)[:10]
        V = int(day[:4])
        lo, hi = window_bounds(V, None)
        if lo <= day < hi and (V in excluded or is_rvm_input(V, debut.get(pk))):
            continue
        if src in DA.GROWTH_SOURCES and status == "active" and fv is not None:
            obs[pk][src][day] = (day, float(fv), None)
        if org and _is_list_label(label):
            last_any[pk] = (day, org, status)
            dd = debut.get(pk)
            if not dd or day <= str(dd)[:10]:
                last_before[pk] = org
    observations = {pk: {s: [by_d[k] for k in sorted(by_d)] for s, by_d in srcs.items()}
                    for pk, srcs in obs.items()}
    trades: dict = defaultdict(list)
    seen: set = set()
    for pk, d, f, to in con.execute(
            "SELECT player_key, trade_date, from_org, to_org FROM trades "
            "ORDER BY trade_date, id"):
        if pk not in players or not d:
            continue
        key = (pk, str(d)[:10], f, to)
        if key in seen:
            continue
        seen.add(key)
        trades[pk].append({"trade_date": str(d)[:10], "from_org": f, "to_org": to})
    year_open = f"{str(today)[:4]}-01-01"
    infos = []
    for pk in sorted(players):
        dd = debut.get(pk)
        la = last_any.get(pk)
        if dd and str(dd)[:10] <= str(today)[:10]:
            status = "debuted"
        elif la and la[2] == "active" and la[0] >= year_open:
            status = "active"
        else:
            status = "inactive"
        infos.append(DA.PlayerInfo(pk, la[1] if la else None, status,
                                   str(dd)[:10] if dd else None, last_before.get(pk)))
    attr = DA.build(infos, trades_by_player=dict(trades), acquisitions={},
                    observations=observations,
                    transactions=DA.load_transactions(con, set(players)),
                    team_org=team_org, today=str(today)[:10], value_fn=value_of)
    out: dict = {}
    for pk in players:
        evs = [(str(t.start)[:10], t.org or UNAFFILIATED, "read")
               for t in attr.calendar(pk) or []]
        if evs:
            out[pk] = evs
    diag = dict(attr.diagnostics)
    diag["players_with_calendar"] = len(out)
    return out, diag


def val4_clean_tau(pairs: list[dict], clubs: set) -> Counter:
    """Drop the unaffiliated share and any code outside the 30 clubs from every pair's
    tau, without renormalizing (amendment A-3); returns a census of what was dropped."""
    census: Counter = Counter()
    for p in pairs:
        tau = p.get("tau") or {}
        kept = {c: float(s) for c, s in tau.items() if c in clubs and s > 0}
        if len(kept) != len(tau):
            census["pairs_with_dropped_share"] += 1
        if not kept:
            census["pairs_with_no_club"] += 1
        p["tau"] = kept
    return census


def _counts_of(frame: dict) -> dict:
    s = summarize(frame)
    return {"start_reads": s["clustering"]["start_reads"],
            "completed_pairs_12m": s["pairs"]["12m"]["total_completed_pairs"],
            "completed_pairs_24m": s["pairs"]["24m"]["total_completed_pairs"]}


def run_look(task_dir: Path, *, today: str | None = None, data_dir: Path = DATA_DIR,
             B: int = BOOT_B, perms: int = PERM_DRAWS) -> int:
    """THE ONE LOOK. Tees stdout and stderr to task_dir first; re-prints a stored result
    instead of scoring twice; refuses before its clock; pins the inputs at the start and
    the end; on any exception after scoring began, writes OWNER_QUESTION.md and stops
    (the marker it left refuses every later run)."""
    task_dir = Path(task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)
    out, err = sys.stdout, sys.stderr
    sys.stdout = _Tee(out, task_dir / "look_stdout.txt")
    sys.stderr = _Tee(err, task_dir / "look_stderr.txt")
    try:
        return _look(task_dir, today=today, data_dir=data_dir, B=B, perms=perms)
    finally:
        for t in (sys.stdout, sys.stderr):
            if isinstance(t, _Tee):
                t.f.close()
        sys.stdout, sys.stderr = out, err


def _look(task_dir: Path, *, today: str | None, data_dir: Path, B: int,
          perms: int) -> int:
    stored = stored_look(data_dir)
    if stored is not None:
        print("A scored look is stored; re-printing it. No second scored look runs.")
        print(json.dumps(stored.get("decision"), indent=1))
        return 0
    marker = CACHE_DIR / LOOK_MARKER
    if marker.exists():
        print(f"REFUSED: {marker} records a look that began scoring and wrote no result; "
              "the owner question it left is pending. No rerun.")
        return 2
    today = today or date.today().isoformat()
    frame_name = look_frame(today, eta_text=_read_doc(ETA_GATE_DOC),
                            dvm_text=_read_doc(DVM_GATE_DOC),
                            anchor_text=_read_doc(ANCHOR_GATE_DOC),
                            efv_v2_text=_read_doc(EFV_V2_GATE_DOC))
    tenure = tenure_source()
    busy = busy_processes()
    if busy:
        raise ClockError("a pipeline, nightly job or test session is running: "
                         + "; ".join(busy))
    early = frame_name == "FULL" and today < LOOK_EARLIEST_FULL
    print(f"FRAME: {frame_name}")
    if early:
        print(f"OWNER-WAIVED EARLY READ ({OWNER_WAIVER['decision']}): the look runs {today}, "
              f"before its registered {LOOK_EARLIEST_FULL} (gate amendment A-1)")
    log = _probe_logger(task_dir)
    pins_start = input_pins(data_dir)
    db = CACHE_DIR / FROZEN_DB
    sha = sha256_file(db) if db.exists() else None
    print(f"frozen store {db} sha256 {sha} (registered {FROZEN_DB_SHA256})")
    if sha != FROZEN_DB_SHA256:
        fresh = freeze_db(dest_dir=CACHE_DIR / "look_copy")
        print(f"fresh backup-API copy sha256 {fresh['sha256']}")
        db = Path(fresh["path"])
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            got = _counts_of(build_frame(con, debut=load_debut_days(data_dir),
                                         rlv_record=None))
        finally:
            con.close()
        print(f"recount on the COMPLEMENT frame: {got} (registered {REGISTERED_COUNTS})")
        bad = {k: (got[k], v) for k, v in REGISTERED_COUNTS.items()
               if abs(got[k] - v) > COUNT_TOLERANCE * v}
        if bad:
            _owner_question(task_dir, "DvM+ difficulty look stopped: the store moved",
                            f"The frozen store was missing or moved (sha {sha}); a fresh "
                            f"copy recounts {bad} against section 12. Owner: read on the "
                            "fresh copy, or restore the registered one?")
            print("STOPPED: counts differ by more than 1 percent; OWNER_QUESTION.md written")
            return 3
    db_sha = sha256_file(db)
    frozen_day = None
    receipt_p = db.parent / FROZEN_RECEIPT
    if db.name == FROZEN_DB and receipt_p.exists():
        frozen_day = (json.loads(receipt_p.read_text(encoding="utf-8")).get("frozen_at")
                      or "")[:10] or None
    team_org, units_sha = (staff_units_map() if tenure == TENURE_VAL4 else ({}, None))
    print(f"tenure source: {tenure}; staff_units sha256 {units_sha}")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"started": _now(), "frame": frame_name}), encoding="utf-8")
    try:
        log("look_start", frame=frame_name, db_sha=db_sha, tenure=tenure)
        from trades import canonical_org
        debut = load_debut_days(data_dir)
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            frame = build_frame(con, debut=debut)
            counts = summarize(frame)
            players = {k[1] for k in frame["starts"]}
            val4_diag = None
            if tenure == TENURE_VAL4:
                events, val4_diag = val4_club_events(
                    con, players, debut, excluded=frame["excluded"],
                    today=frozen_day or today, team_org=team_org)
                log("val4_calendar", **val4_diag)
            else:
                events = load_club_events(con, players, debut, excluded=frame["excluded"],
                                          canon=canonical_org)
        finally:
            con.close()
        ids = {st["person"] for st in frame["starts"].values() if st.get("person")}
        last = max((k[2] for k in frame["starts"]), default=2011) + max(HORIZONS)
        seasons = load_person_seasons(ids, min(last, date.today().year))

        def active_in(person, season):
            ps = seasons.get(person) or {}
            if not any(season in (ps.get(g) or {}) for g in ID.GROUPS):
                return False if season <= date.today().year - 1 else None
            return True

        pairs, census = pairs_from_frame(frame, debut=debut, club_events=events,
                                         canon=canonical_org, active_in=active_in)
        tau_census = None
        if tenure == TENURE_VAL4:
            import dev_attribution as DA  # noqa: PLC0415
            tau_census = dict(val4_clean_tau(pairs, set(DA._mlb30())))
        log("pairs", n=len(pairs), census=dict(census), tau_census=tau_census)
        table, ev = run_analysis(pairs, frame_name=frame_name, B=B, perms=perms, log=log)
        pins_end = input_pins(data_dir)
        units_end = staff_units_map()[1] if tenure == TENURE_VAL4 else None
        if (pins_end != pins_start or sha256_file(db) != db_sha
                or units_end != units_sha):
            raise RuntimeError("an input moved during the look (section 15)")
        receipt = {"generated_at": _now(), "today": today, "frame": frame_name,
                   "frozen_db": _rel(db), "frozen_db_sha256": db_sha,
                   "tenure_source": tenure, "frame_counts": _counts_of(frame),
                   "dvm1_counts_clustering": counts["clustering"],
                   "pair_census": dict(census),
                   "excluded_list_years": sorted(frame["excluded"]),
                   "owner_waived_early_read": early,
                   "rlv_look_record": RLV_LOOK_RECORD if frame_name == "FULL" else None,
                   "val4": ({"calendar": val4_diag, "tau_census": tau_census,
                             "calendar_as_of": frozen_day or today,
                             "staff_units_sha256": units_sha}
                            if tenure == TENURE_VAL4 else None)}
        table["frame_receipt"] = receipt
        table["input_pins"] = {"start": pins_start, "end": pins_end}
        ev["receipt"] = receipt
        # A-7: each artifact dates itself at the top level (model_registry freshness).
        table = {"generated_at": receipt["generated_at"], **table}
        ev = {"generated_at": receipt["generated_at"], **ev}
        (Path(data_dir) / TABLE_ARTIFACT).write_text(
            json.dumps(clean_json(table), indent=1, allow_nan=False), encoding="utf-8")
        (Path(data_dir) / EVAL_ARTIFACT).write_text(
            json.dumps(clean_json(ev), indent=1, allow_nan=False), encoding="utf-8")
        for line in summary_lines(table, ev):
            print(line)
        log("look_end")
        return 0
    except Exception as exc:
        _owner_question(task_dir, "DvM+ difficulty look crashed after scoring began",
                        f"{type(exc).__name__}: {exc}\n\nThe look is not rerun (gate "
                        f"section 14). The marker {marker} refuses later runs until the "
                        "owner decides.")
        raise


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------

def run_counts(out_dir: Path, db: Path | None = None) -> dict:
    db = Path(db) if db else CACHE_DIR / FROZEN_DB
    if not db.exists():
        raise SystemExit(f"no frozen store at {db}; run --freeze first")
    receipt_p = db.parent / FROZEN_RECEIPT
    receipt = json.loads(receipt_p.read_text(encoding="utf-8")) if receipt_p.exists() else {}
    sha_start = sha256_file(db)
    if receipt.get("sha256") and receipt["sha256"] != sha_start:
        raise SystemExit("the frozen store does not match its receipt")
    pins_start = input_pins()
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        frame = build_frame(con, debut=load_debut_days())
    finally:
        con.close()
    counts = summarize(frame)
    pins_end = input_pins()
    sha_end = sha256_file(db)
    counts["receipt"] = {
        "generated_at": _now(), "frozen_db": _rel(db), "frozen_db_sha256": sha_start,
        "frozen_db_sha256_end": sha_end, "frozen_at": receipt.get("frozen_at"),
        "input_pins_start": pins_start, "input_pins_end": pins_end,
        "pins_held": sha_start == sha_end and pins_start == pins_end,
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(counts, indent=1, sort_keys=False)
    (out_dir / "frame_counts.json").write_text(body, encoding="utf-8")
    (out_dir / "frame_counts.txt").write_text(text_summary(counts), encoding="utf-8")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "frame_counts.json").write_text(body, encoding="utf-8")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--counts", metavar="OUT_DIR")
    ap.add_argument("--db", default=None)
    ap.add_argument("--dry-run", metavar="OUT_DIR",
                    help="the whole reporting path on synthetic fixtures with nulls")
    ap.add_argument("--look", metavar="TASK_DIR",
                    help="THE ONE LOOK (gate section 14); refuses before its clock")
    a = ap.parse_args(argv)
    if a.look:
        return run_look(Path(a.look))
    if a.freeze:
        print(json.dumps(freeze_db(), indent=1))
    if a.counts:
        c = run_counts(Path(a.counts), a.db)
        print(text_summary(c))
    if a.dry_run:
        print(run_dry(Path(a.dry_run))["text"])
    if not (a.freeze or a.counts or a.dry_run):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
