# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DvM+ development-difficulty lab: the FRAME module only (DVM-1). COUNTS ONLY.

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
        (the commit that records that look) is None, so a pair with an endpoint in
        either year cannot exist (Q-DVM-1 A).
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
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_identity as ID  # noqa: E402  outcome-blind name resolution (DS-03)
import milb_history as mh  # noqa: E402

CACHE_DIR = ROOT / ".cache" / "dvm_difficulty"
FROZEN_DB = "prospects_frozen.db"
FROZEN_RECEIPT = "prospects_frozen.json"
DATA_DIR = ROOT / "data"

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
#: that look is recorded; while None, F-R1 holds (Q-DVM-1 A).
RLV_LOOK_RECORD: str | None = None
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
    (DVM-2, committed alone before any growth is read). This module calls no growth
    computation; the guard is here so the lab that does inherits it."""
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
        }
    return reads, rvm


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
        "generated_at": _now(), "frozen_db": str(db), "frozen_db_sha256": sha_start,
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
    a = ap.parse_args(argv)
    if a.freeze:
        print(json.dumps(freeze_db(), indent=1))
    if a.counts:
        c = run_counts(Path(a.counts), a.db)
        print(text_summary(c))
    if not (a.freeze or a.counts):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
