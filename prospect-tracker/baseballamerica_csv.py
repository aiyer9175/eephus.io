# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Baseball America board ingest. Owner-pasted markdown, NOT a scraper.

BA boards are licensed subscription material. Paywall circumvention was asked
about and DECLINED (plan Lane K4); the sanctioned acquisition paths are an
owner paste into data/baseballamerica_imports/inbox/ and a licensing email.
Nothing in this module fetches anything. It reads files a human put on disk.

The material is used ONLY as eFV / consensus TRAINING input and is never
displayed. The drop tree is gitignored and, because deploy/nightly-build.sh
rsyncs only data/*.json at depth 1, it cannot reach the public webroot either.

WHAT BA PUBLISHES, verified against two real boards (2026 preseason Orioles
and Blue Jays, 30 players each, 60 rows total):

    30 players
    Expand all
    Headshot of Trey Yesavage          <- OPTIONAL, see below
    1\\. Trey Yesavage                  <- the anchor. markdown-escaped dot.
    RHP
    Ht: 6'4" | Wt: 225 | B-T: R-R
    Age: 22
    BA Grade/Risk: 60/Mild
    Adjusted Grade: 55
    Previous Rank: 2                   <- OPTIONAL, see below
    Track Record: ...
    Scouting Report: ...
    The Future: ...
    Scouting Grades: Fastball: 60 | Slider: 55 | Split: 70 | Control: 50

ANCHOR ON THE RANK LINE, NOT THE HEADSHOT LINE. 3 of 30 Orioles and 4 of 30
Blue Jays rows have no "Headshot of" line at all, so anchoring there silently
drops rows. The rank line is present on 60 of 60. It is matched only at the
start of a line, which is what keeps prose like "the Blue Jays at pick No.
20\\." from registering as a rank.

FIELDS THAT LOOK REQUIRED AND ARE NOT. Previous Rank is on all 30 Orioles rows
and absent from all 30 Blue Jays rows. Age is missing on 1-2 per board.
Scouting Report and The Future are missing on some. Requiring any of them
rejects a valid board.

THE FILENAME IS LOAD-BEARING, not cosmetic. The Blue Jays file carries no
season, board or team header anywhere in its body, so season / board / team
come from the name and nowhere else. See the inbox README for the spec.

ADJUSTED GRADE IS A COMPUTED FIELD. Deterministic on both boards with zero
exceptions in 60 rows:

    adjusted = raw - penalty(risk),  Low 0, Mild 5, Average 10, High 15, Extreme 20

Owner instruction stands: `fv` takes the Adjusted Grade, never the raw grade.
But raw and risk are BOTH stored under _extras, for two reasons. The pair
resolves 11 distinct cells against adjusted's 4-5, so it is strictly finer.
And adjusted is a FUNCTION OF RANK (monotone non-increasing in rank on both
boards, perfect contiguous tiers) while raw is not, so adjusted alone would
feed a model something close to a re-encoding of the rank column.

This module RECOMPUTES adjusted from raw and risk and reports every row where
the identity fails, rather than trusting it. A board that stops obeying the
identity is a format change, and finding out from a silent drift later is the
expensive version.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from scrapers import Snapshot, fix_mojibake, normalize_key, strip_name_markers

log = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
DROP_DIR = _BASE / "data" / "baseballamerica_imports"
INBOX_DIR = DROP_DIR / "inbox"
PROCESSED_DIR = DROP_DIR / "processed"

# The source string already in prospects.db. Do NOT mint a variant: the tree
# carries 100 rows under exactly this name (Baseball America 2026-06-03 Top
# 100, snapshot_date 2026-06-03) plus 41 under baseballamerica_statcast_by_age,
# and a second spelling would read as a second outlet to consensus and to
# source_backtest.
SOURCE = "baseballamerica"

BOARDS = ("preseason", "midseason", "offseason")

_REPORT_MAX_CHARS = 8000


# ---------------------------------------------------------------------------
# Risk -> adjusted-grade penalty
# ---------------------------------------------------------------------------

# Measured on 60 of 60 rows across two boards, zero exceptions. Ordered so the
# report can print the ladder. "Extreme" was not observed on either board and
# is carried from BA's published risk vocabulary; a row that uses it will be
# checked by the same identity as every other row, so a wrong guess here shows
# up as an identity failure rather than as a silently wrong FV.
RISK_PENALTY: dict[str, float] = {
    "low": 0.0,
    "mild": 5.0,
    "average": 10.0,
    "high": 15.0,
    "extreme": 20.0,
}


def risk_penalty(risk: str | None) -> float | None:
    if not risk:
        return None
    return RISK_PENALTY.get(risk.strip().lower())


# ---------------------------------------------------------------------------
# Tool vocabulary
# ---------------------------------------------------------------------------

# BA's Scouting Grades labels -> this repo's canonical tool keys
# (scrapers.HITTER_TOOL_KEYS / PITCHER_TOOL_KEYS).
#
# The two genuinely ambiguous labels are Split and Sweeper, and the tree has
# ALREADY DECIDED BOTH for another source: scrapers.JB_TOOL_KEY:1639 maps
# splitter onto the changeup slot and :1635 maps sweeper onto the slider slot,
# with the reasoning written at :1611-1613 ("variants of those pitch
# families"). Following that precedent is what makes a BA splitter grade
# comparable with a Just Baseball splitter grade inside the consensus, which
# is the entire purpose of a canonical vocabulary. The audit plan proposed
# minting a new `sw` key instead; that was written without sight of
# JB_TOOL_KEY and is not followed here. See the SPLIT/SWEEPER note in
# _map_tools for what is preserved so the decision stays reversible.
#
# KNOWN INCONSISTENCY, reported not silently inherited: tjstats writes a
# distinct `sp` key on 210 rows and `ct` on 279, so splitter currently lands in
# `ch` from Just Baseball and in `sp` from tjstats. `sp` is not in
# PITCHER_TOOL_KEYS, so consumers iterating the canonical tuple skip it. That
# is a pre-existing defect in the tool taxonomy, it is not created here, and it
# is worth an owner decision separately from this ingest.
BA_TOOL_KEY: dict[str, str] = {
    # hitters
    "hit": "hit",
    "power": "game_pwr",       # BA publishes ONE power grade; FG splits raw/game
    "run": "speed",
    "speed": "speed",
    "field": "field",
    "fielding": "field",
    "arm": "throw",
    # pitchers
    "fastball": "fb",
    "slider": "sl",
    "sweeper": "sl",           # sweeper = slider variant (JB precedent)
    "curveball": "cb",
    "curve": "cb",
    "changeup": "ch",
    "split": "ch",             # splitter = changeup variant (JB precedent)
    "splitter": "ch",
    "cutter": "ct",
    "control": "cmd",
    "command": "cmd",
}

# BA's single `Power` maps onto game_pwr rather than raw_pwr. Recorded because
# it is a real modelling choice and not an obvious one: BA's power grade is a
# projection of production, which is what game power means here, whereas
# raw_pwr is the physical ceiling. A future re-read of BA power as raw_pwr
# would change what tool_hit-style features see, so it needs its own gate.
BA_POWER_TARGET = "game_pwr"


# ---------------------------------------------------------------------------
# Filename
# ---------------------------------------------------------------------------

# ba__{season}__{board}__{team}[__{YYYY-MM-DD}].md
# Double underscores so a team slug containing a hyphen ("blue-jays",
# "red-sox", "white-sox", "d-backs") can never be mistaken for a boundary.
_FILENAME_RE = re.compile(
    r"^ba__(?P<season>\d{4})__(?P<board>[a-z]+)__(?P<team>[a-z0-9-]+?)"
    r"(?:__(?P<pubdate>\d{4}-\d{2}-\d{2}))?\.md$"
)


def _org_lookup() -> tuple[dict[str, str], dict[str, str]]:
    """(team_slug -> org code, org code -> nickname).

    Derived from build_site.ORG_NAMES so there is exactly one club table in
    the tree. A second hardcoded copy here would drift the first time a club
    renames, which has already happened once (Athletics dropped "Oakland"
    mid-2024 and spotrac.py:266-268 carries the scar).
    """
    from build_site import ORG_NAMES
    slug_to_org = {}
    for code, nickname in ORG_NAMES.items():
        slug = nickname.lower().replace(" ", "-")
        slug_to_org[slug] = code
    # BA and casual usage both shorten Diamondbacks. Accept it rather than
    # bounce a correctly-named file.
    if "diamondbacks" in slug_to_org:
        slug_to_org.setdefault("d-backs", slug_to_org["diamondbacks"])
        slug_to_org.setdefault("dbacks", slug_to_org["diamondbacks"])
    return slug_to_org, dict(ORG_NAMES)


def parse_filename(name: str) -> dict | None:
    """Parse a drop filename into its board identity, or None if malformed."""
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    board = m.group("board")
    if board not in BOARDS:
        return None
    slug_to_org, org_names = _org_lookup()
    team_slug = m.group("team")
    org = slug_to_org.get(team_slug)
    if org is None:
        return None
    return {
        "season": int(m.group("season")),
        "board": board,
        "team_slug": team_slug,
        "org": org,
        "team_name": org_names[org],
        "pubdate": m.group("pubdate"),
    }


# ---------------------------------------------------------------------------
# Content dating. Boards are dated by CONTENT, never by label.
# ---------------------------------------------------------------------------

# THE HAZARD THIS EXISTS FOR, caught on a real file. The first board pasted
# during this program was named for "Preseason 2026" and carried mid-season
# content: 2 of 30 rows said "through mid-May", 4 said "this year", 12
# referenced 2026 in-season. The owner spotted it independently and replaced
# the file. The Blue Jays board is genuinely preseason (0 and 0).
#
# WHY THIS IS NOT A MONTH SCANNER. A naive "find a month name, find a year"
# rule refuses the GOOD board: the Blue Jays lead row says Yesavage "made his
# major league debut on Sept. 15" (a 2025 fact) two paragraphs from "Yesavage
# enters 2026" (a forward-looking one), and pairing those yields a phantom
# 2026-09-15. The discriminator that actually separated the two files was
# in-season PHRASING, so that is what is matched here.
_IN_SEASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bthrough (?:mid-|early |late )?(?:January|February|March|April|May|June|July|"
     r"August|September|October|Jan\.|Feb\.|Mar\.|Apr\.|Jun\.|Jul\.|Aug\.|Sept\.|Oct\.)",
     "through-a-month"),
    (r"\bthis (?:year|season)\b", "this-year"),
    (r"\bso far this (?:year|season)\b", "so-far-this-season"),
    (r"\bentering play\b", "entering-play"),
    (r"\bthus far\b", "thus-far"),
    (r"\bhas (?:hit|posted|struck out|thrown|pitched)[^.]{0,60}\bthis (?:year|season)\b",
     "production-this-season"),
)

_EXPLICIT_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan\.|Feb\.|Mar\.|Apr\.|Jun\.|Jul\.|Aug\.|Sept\.|Sep\.|Oct\.|Nov\.|Dec\.)"
    r"\s+(\d{1,2})(?:\\?\.)?,?\s+(\d{4})\b"
)

_MONTH_NUM = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def scan_content_dates(text: str, season: int) -> dict:
    """Report every in-content signal about when a board was actually written.

    Returns the evidence; it does not decide. The caller pairs this with the
    board label, because the failure mode is a MISMATCH between the two and
    neither one alone can show it.
    """
    in_season: list[dict] = []
    for pattern, tag in _IN_SEASON_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            line = text[line_start:line_end if line_end != -1 else len(text)]
            in_season.append({
                "tag": tag,
                "match": m.group(0),
                "excerpt": line.strip()[:200],
            })

    explicit: list[dict] = []
    for m in _EXPLICIT_DATE_RE.finditer(text):
        mon = _MONTH_NUM.get(m.group(1).lower().rstrip("."))
        if not mon:
            continue
        try:
            d = date(int(m.group(3)), mon, int(m.group(2)))
        except ValueError:
            continue
        explicit.append({"iso": d.isoformat(), "match": m.group(0)})

    season_refs = sorted({int(y) for y in re.findall(r"\b(20\d{2})\b", text)})

    return {
        "in_season_markers": in_season,
        "in_season_count": len(in_season),
        "explicit_dates": explicit,
        "latest_explicit_date": max((e["iso"] for e in explicit), default=None),
        "years_referenced": season_refs,
        "max_year_referenced": max(season_refs) if season_refs else None,
        "season_labelled": season,
    }


def resolve_snapshot_date(meta: dict, evidence: dict) -> tuple[str | None, list[str]]:
    """(snapshot_date, refusals). A non-empty refusal list means DO NOT INGEST.

    snapshot_date is what the whole as-of chain keys on: consensus picks the
    latest point strictly before a player's decision date and the eFV training
    matrix inherits that, so a wrong date does not merely mislabel a row, it
    can move the row across a decision boundary. There is a recorded failure of
    exactly this kind in this repo (the MLB Pipeline org backfill hardcoded
    {y}-01-22 for every season, which froze 829 prospects on January grades
    until 2026-07-24), which is why a season-level convention is a FALLBACK
    that gets RECORDED as a convention, never a measurement.
    """
    refusals: list[str] = []
    season = meta["season"]
    board = meta["board"]

    # Convention fallbacks. Recorded as conventions in the artifact.
    convention = {
        "preseason": f"{season}-02-15",
        "midseason": f"{season}-07-01",
        "offseason": f"{season - 1}-11-15",
    }[board]
    snapshot_date = meta.get("pubdate") or convention
    basis = "filename" if meta.get("pubdate") else "convention"

    # A preseason board must not contain in-season prose.
    if board == "preseason" and evidence["in_season_count"] > 0:
        tags = sorted({m["tag"] for m in evidence["in_season_markers"]})
        refusals.append(
            f"board is labelled preseason but carries {evidence['in_season_count']} "
            f"in-season prose markers ({', '.join(tags)}). Boards are dated by "
            f"content, never by label. Re-export the correct board, or rename the "
            f"file to the board it actually is and add the real publication date."
        )

    # No snapshot_date may precede a date the content itself states.
    latest = evidence["latest_explicit_date"]
    if latest and latest > snapshot_date:
        refusals.append(
            f"snapshot_date {snapshot_date} ({basis}) is EARLIER than an explicit "
            f"date in the board's own text ({latest}). Add the real publication "
            f"date to the filename."
        )

    # A board cannot have been written before the season it discusses.
    max_year = evidence["max_year_referenced"]
    if max_year and max_year > season:
        refusals.append(
            f"board is labelled season {season} but references {max_year}. "
            f"Check the file is the board you think it is."
        )

    return snapshot_date, refusals


# ---------------------------------------------------------------------------
# Board parsing
# ---------------------------------------------------------------------------

# Markdown escapes the rank dot: "1\. Trey Yesavage". Anchored at line start,
# which is what keeps "at pick No. 20\." inside a Track Record paragraph from
# matching. The name is captured loosely and cleaned afterwards.
_RANK_LINE_RE = re.compile(r"^(\d{1,3})\\?\.\s+(\S.*?)\s*$")
_HEADER_COUNT_RE = re.compile(r"^(\d{1,3})\s+players\s*$", re.IGNORECASE)
_GRADE_RISK_RE = re.compile(r"BA Grade\s*/\s*Risk:\s*(\d{2})\s*/\s*([A-Za-z]+)")
_ADJUSTED_RE = re.compile(r"Adjusted Grade:\s*(\d{2})")
_PREV_RANK_RE = re.compile(r"Previous Rank:\s*(\d{1,3})")
_AGE_RE = re.compile(r"^Age:\s*(\d{1,2})\s*$", re.MULTILINE)
_PHYS_RE = re.compile(
    r"Ht:\s*([0-9]'[0-9]{1,2}\")\s*\|\s*Wt:\s*(\d{2,3})\s*\|\s*B-T:\s*([A-Z])-([A-Z])")
_SCOUT_GRADES_RE = re.compile(r"Scouting Grades:\s*(.+?)\s*$", re.MULTILINE)
_PROSE_RE = {
    "track_record": re.compile(r"^Track Record:\s*(.+?)\s*$", re.MULTILINE),
    "report": re.compile(r"^Scouting Report:\s*(.+?)\s*$", re.MULTILINE),
    "future": re.compile(r"^The Future:\s*(.+?)\s*$", re.MULTILINE),
}
# "RHP", "SS", "OF / C", "1B / 3B". The position line is the first short,
# all-caps-ish line after the rank line.
_POSITION_RE = re.compile(r"^([A-Z0-9]{1,3}(?:\s*/\s*[A-Z0-9]{1,3})*)\s*$")


class BoardFormatError(ValueError):
    """The file is not a board this parser will ingest. Never partial."""


def _clean_name(raw: str) -> str:
    """BA names are clean UTF-8 on both probed boards, but the same defences
    the FanGraphs path needs are cheap and this is an untrusted paste."""
    return strip_name_markers(fix_mojibake(raw)).strip()


def _split_blocks(text: str) -> list[tuple[int, str, str]]:
    """[(rank, raw_name, block_text)] in file order."""
    lines = text.splitlines()
    anchors: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = _RANK_LINE_RE.match(line)
        if not m:
            continue
        name = m.group(2)
        # A rank line's name is a person, not a sentence. Prose lines that
        # begin with a number are excluded by length and by punctuation.
        if len(name) > 60 or name.endswith((".", ",", ":", ";")):
            continue
        anchors.append((i, int(m.group(1)), name))
    out = []
    for idx, (line_no, rank, name) in enumerate(anchors):
        end = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(lines)
        # Drop a trailing "Headshot of X" line: it belongs to the NEXT player.
        block_lines = lines[line_no + 1:end]
        while block_lines and block_lines[-1].strip().startswith("Headshot of "):
            block_lines.pop()
        out.append((rank, name, "\n".join(block_lines)))
    return out


def _map_tools(raw_grades: str) -> tuple[dict, dict, list[dict]]:
    """(canonical tools, raw BA labels, collisions).

    SPLIT / SWEEPER: both fold onto an existing canonical slot per the Just
    Baseball precedent, and the untouched BA label is ALWAYS kept in
    _extras.ba_tools_raw. That is what keeps the decision reversible: if the
    owner later rules that a splitter deserves its own key, every ingested row
    can be re-derived from the raw block without re-pasting a single board.
    Discarding the label and keeping only the folded value is the version that
    cannot be undone, so it is not done.

    Collisions are surfaced, never silently resolved. A pitcher graded for both
    Changeup and Split would otherwise have one overwrite the other depending
    on dict order, and which one survived would be invisible.
    """
    tools: dict[str, float] = {}
    raw: dict[str, float] = {}
    collisions: list[dict] = []
    for part in raw_grades.split("|"):
        if ":" not in part:
            continue
        label, _, value = part.partition(":")
        label = label.strip().lower()
        value = value.strip()
        if not re.fullmatch(r"\d{2}", value):
            continue
        grade = float(value)
        raw[label] = grade
        key = BA_TOOL_KEY.get(label)
        if key is None:
            collisions.append({"kind": "unmapped_label", "label": label, "grade": grade})
            continue
        if key in tools and tools[key] != grade:
            collisions.append({
                "kind": "slot_collision", "label": label, "canonical": key,
                "kept": tools[key], "dropped": grade,
            })
            continue
        tools[key] = grade
    return tools, raw, collisions


def parse_board(text: str, meta: dict) -> dict:
    """Parse one pasted board. Raises BoardFormatError rather than ingest a
    partial board: a board missing rows is a board whose ranks mean something
    different, and rank is the quantity this ingest exists to capture."""
    declared = None
    for line in text.splitlines()[:20]:
        m = _HEADER_COUNT_RE.match(line.strip())
        if m:
            declared = int(m.group(1))
            break

    blocks = _split_blocks(text)
    if not blocks:
        raise BoardFormatError(
            "no rank lines found. The anchor is a line starting with a number "
            "and an escaped dot, e.g. '1\\. Trey Yesavage'. Was the file tidied "
            "before pasting? Paste it raw.")

    ranks = [b[0] for b in blocks]
    expected = list(range(1, len(blocks) + 1))
    if ranks != expected:
        missing = sorted(set(expected) - set(ranks))
        dupes = sorted({r for r in ranks if ranks.count(r) > 1})
        raise BoardFormatError(
            f"ranks are not a contiguous 1..{len(blocks)}. "
            f"got {ranks[:12]}{'...' if len(ranks) > 12 else ''}, "
            f"missing {missing[:8]}, duplicated {dupes[:8]}")
    if declared is not None and declared != len(blocks):
        raise BoardFormatError(
            f"board header claims {declared} players but {len(blocks)} rank "
            f"lines parsed. Refusing a partial board.")

    rows: list[dict] = []
    for rank, raw_name, block in blocks:
        name = _clean_name(raw_name)
        if not name:
            raise BoardFormatError(f"rank {rank} has an empty name")

        position = None
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            pm = _POSITION_RE.match(s)
            if pm:
                position = pm.group(1)
            break

        gr = _GRADE_RISK_RE.search(block)
        adj = _ADJUSTED_RE.search(block)
        prev = _PREV_RANK_RE.search(block)
        age = _AGE_RE.search(block)
        phys = _PHYS_RE.search(block)
        grades = _SCOUT_GRADES_RE.search(block)

        raw_grade = float(gr.group(1)) if gr else None
        risk = gr.group(2) if gr else None
        adjusted = float(adj.group(1)) if adj else None

        tools, ba_tools_raw, tool_issues = ({}, {}, [])
        if grades:
            tools, ba_tools_raw, tool_issues = _map_tools(grades.group(1))

        # Recompute rather than trust. See the module docstring.
        expected_adj = None
        identity_ok = None
        pen = risk_penalty(risk)
        if raw_grade is not None and pen is not None:
            expected_adj = raw_grade - pen
            identity_ok = (adjusted is not None and adjusted == expected_adj)

        prose = {}
        for field, rx in _PROSE_RE.items():
            pm = rx.search(block)
            if pm:
                prose[field] = pm.group(1).strip()[:_REPORT_MAX_CHARS]

        rows.append({
            "rank": rank,
            "player_name": name,
            # "OF / C" -> OF. A multi-position line lists the primary first on
            # both probed boards; the full string is preserved beside it so a
            # later positional-fit consumer is not stuck with the truncation.
            "position": position.split("/")[0].strip() if position else None,
            "position_full": position,
            "ba_raw_grade": raw_grade,
            "ba_risk": risk,
            "fv": adjusted,          # owner instruction: FV is the ADJUSTED grade
            "adjusted_expected": expected_adj,
            "adjusted_identity_ok": identity_ok,
            "previous_rank": int(prev.group(1)) if prev else None,
            "age": int(age.group(1)) if age else None,
            "height": phys.group(1) if phys else None,
            "weight": int(phys.group(2)) if phys else None,
            "bats": phys.group(3) if phys else None,
            "throws": phys.group(4) if phys else None,
            "tools": tools,
            "ba_tools_raw": ba_tools_raw,
            "tool_issues": tool_issues,
            **prose,
        })

    n = len(rows)
    return {
        "meta": {
            **meta,
            "n_players": n,
            "declared_players": declared,
            # THE TRAP. consensus._ORG_LIST_LABEL_RE is
            # r"\bTop\s+(?:10|20|25|30)\b\s*$" and it is the only thing keeping
            # an org list out of implied_fv_from_rank. Get this label wrong and
            # every number-one org prospect becomes a rank-implied FV 70. That
            # is the Bryan Sanchez failure: his only signal was rank 30 on a
            # 2021 Nationals Top-30, the legacy check missed the label format,
            # and he sorted 19th overall on zero published FVs. The existing
            # convention this matches is literally
            # "MLB Pipeline 2011 Angels Top 30".
            "interval_label": f"Baseball America {meta['season']} "
                              f"{meta['team_name']} Top {declared or n}",
        },
        "rows": rows,
    }


def validate_org_label(label: str) -> str | None:
    """Return a refusal reason if this label would NOT be seen as an org list.

    Checked against the LIVE regex rather than a copy of the sizes it accepts,
    because a copy is exactly what failed last time. _ORG_LIST_LABEL_RE matches
    only Top 10 / 20 / 25 / 30, so a board that parsed to 29 or 31 rows would
    build a label the guard does not match, its ranks would fall through to
    implied_fv_from_rank, and the number-one org prospect would become FV 70 on
    zero published grades. That failure is silent, board-wide, and has happened:
    Bryan Sanchez sorted 19th overall off rank 30 on a 2021 Nationals Top-30.

    Loud refusal is the whole point. Do not "fix" a refusal by padding the
    label to 30; fix the paste.
    """
    from consensus import _ORG_LIST_LABEL_RE
    if _ORG_LIST_LABEL_RE.search(label):
        return None
    return (
        f"interval_label {label!r} is NOT matched by consensus._ORG_LIST_LABEL_RE, "
        f"so this board's ranks would feed implied_fv_from_rank and its top "
        f"prospect would become a rank-implied FV 70. The guard accepts only "
        f"Top 10, 20, 25 and 30. Check the paste is a complete org board.")


# ---------------------------------------------------------------------------
# Identity. Resolve against what exists; never guess.
# ---------------------------------------------------------------------------

def resolve_identities(rows: list[dict], org: str) -> dict:
    """Attach a player_key to every row this can settle UNAMBIGUOUSLY.

    A confident wrong resolution is worse than a missing row, and this repo has
    three recorded incidents to prove it: joe_jr_gray resolved to Connor Joe,
    william_jr_bergolla to William Contreras, and Jack Natili reached the
    served board twice at ranks 155 and 320 with his surplus double counted.
    So the ladder resolves onto keys that already exist and reports everything
    else for a human. Minting is opt-in and lives in ingest_drops.
    """
    import storage
    with storage.connect() as con:
        known = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT player_key, player_name, org FROM players")}

    resolved, unresolved, org_mismatch = [], [], []
    for r in rows:
        key = normalize_key(r["player_name"])
        if key in known:
            db_name, db_org = known[key]
            r["player_key"] = key
            r["resolution"] = "exact_key"
            if db_org and db_org != org:
                # Not necessarily wrong: a player traded between the board's
                # publication and today has a different current org. Reported
                # so a genuine name collision cannot hide inside the noise.
                r["resolution"] = "exact_key_org_mismatch"
                org_mismatch.append({"rank": r["rank"], "name": r["player_name"],
                                     "player_key": key, "board_org": org,
                                     "db_org": db_org, "db_name": db_name})
            resolved.append(r)
        else:
            r["player_key"] = None
            r["resolution"] = "unresolved"
            unresolved.append({"rank": r["rank"], "name": r["player_name"],
                               "would_be_key": key, "board_org": org})
    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "org_mismatch": org_mismatch,
        "n_resolved": len(resolved),
        "n_unresolved": len(unresolved),
    }


def to_snapshots(board: dict) -> list[Snapshot]:
    """Rows with a settled identity -> Snapshot objects."""
    meta = board["meta"]
    out: list[Snapshot] = []
    for r in board["rows"]:
        if not r.get("player_key"):
            continue
        extras = {
            # The pair the owner instruction says to keep beside the FV. This
            # mirrors what consensus already does, where per_source.fv_published
            # keeps the untouched published grade next to fv_adjusted.
            "ba_raw_grade": r["ba_raw_grade"],
            "ba_risk": r["ba_risk"],
            "ba_board": meta["board"],
            "ba_previous_rank": r["previous_rank"],
            "position_full": r["position_full"],
            "age": r["age"],
            "height": r["height"],
            "weight": r["weight"],
            "bats": r["bats"],
            "throws": r["throws"],
            # Untouched BA tool labels, so the split/sweeper folding decision
            # stays reversible without re-pasting the board.
            "ba_tools_raw": r["ba_tools_raw"] or None,
            "report": r.get("report"),
        }
        extras = {k: v for k, v in extras.items() if v is not None and v != ""}
        tools = dict(r["tools"])
        if extras:
            tools["_extras"] = extras
        out.append(Snapshot(
            source=SOURCE,
            snapshot_date=meta["snapshot_date"],
            interval_label=meta["interval_label"],
            player_key=r["player_key"],
            player_name=r["player_name"],
            position=r["position"],
            org=meta["org"],
            rank=r["rank"],
            # A row whose Adjusted Grade is missing is ingested RANK-ONLY. It
            # does NOT fall back to the raw grade: a raw grade sitting in an FV
            # column is a scale error no downstream layer can detect.
            fv=r["fv"],
            status="active",
            tools=tools or None,
            fv_plus=False,
        ))
    return out


# ---------------------------------------------------------------------------
# Drop-folder walk
# ---------------------------------------------------------------------------

_CSV_COLUMNS = (
    "season", "board", "org", "team_name", "snapshot_date", "interval_label",
    "rank", "player_name", "player_key", "resolution", "position",
    "position_full", "fv", "ba_raw_grade", "ba_risk", "adjusted_expected",
    "adjusted_identity_ok", "previous_rank", "age", "height", "weight",
    "bats", "throws", "tools_json", "ba_tools_raw_json",
)


def _write_normalized_csv(board: dict, path: Path) -> None:
    meta = board["meta"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_CSV_COLUMNS))
        w.writeheader()
        for r in board["rows"]:
            w.writerow({
                "season": meta["season"], "board": meta["board"],
                "org": meta["org"], "team_name": meta["team_name"],
                "snapshot_date": meta["snapshot_date"],
                "interval_label": meta["interval_label"],
                "rank": r["rank"], "player_name": r["player_name"],
                "player_key": r.get("player_key") or "",
                "resolution": r.get("resolution") or "",
                "position": r["position"] or "",
                "position_full": r["position_full"] or "",
                "fv": r["fv"] if r["fv"] is not None else "",
                "ba_raw_grade": r["ba_raw_grade"] if r["ba_raw_grade"] is not None else "",
                "ba_risk": r["ba_risk"] or "",
                "adjusted_expected": r["adjusted_expected"] if r["adjusted_expected"] is not None else "",
                # None means "not checkable" (no risk published), which is a
                # different fact from False ("checked and it broke"). Kept
                # distinct in the CSV rather than collapsed to a blank.
                "adjusted_identity_ok": ("" if r["adjusted_identity_ok"] is None
                                         else int(r["adjusted_identity_ok"])),
                "previous_rank": r["previous_rank"] if r["previous_rank"] is not None else "",
                "age": r["age"] if r["age"] is not None else "",
                "height": r["height"] or "", "weight": r["weight"] or "",
                "bats": r["bats"] or "", "throws": r["throws"] or "",
                "tools_json": json.dumps(r["tools"], sort_keys=True) if r["tools"] else "",
                "ba_tools_raw_json": json.dumps(r["ba_tools_raw"], sort_keys=True) if r["ba_tools_raw"] else "",
            })


def process_file(path: Path, *, resolve: bool = True) -> dict:
    """Parse one drop file end to end. Never writes to the DB."""
    meta = parse_filename(path.name)
    if meta is None:
        raise BoardFormatError(
            f"filename {path.name!r} does not match "
            f"ba__{{season}}__{{board}}__{{team}}[__{{YYYY-MM-DD}}].md with a "
            f"known board ({'/'.join(BOARDS)}) and a known club slug. The "
            f"filename is load-bearing: one probed board carried no season, "
            f"board or team anywhere in its body.")

    text = path.read_text(encoding="utf-8")
    evidence = scan_content_dates(text, meta["season"])
    snapshot_date, refusals = resolve_snapshot_date(meta, evidence)
    meta["snapshot_date"] = snapshot_date
    meta["snapshot_date_basis"] = "filename" if meta.get("pubdate") else "convention"

    board = parse_board(text, meta)
    board["content_evidence"] = evidence
    board["refusals"] = refusals

    label_problem = validate_org_label(board["meta"]["interval_label"])
    if label_problem:
        refusals.append(label_problem)

    # Adjusted-grade identity audit over the whole board.
    broken = [r for r in board["rows"] if r["adjusted_identity_ok"] is False]
    board["adjusted_identity_failures"] = [
        {"rank": r["rank"], "name": r["player_name"], "raw": r["ba_raw_grade"],
         "risk": r["ba_risk"], "published_adjusted": r["fv"],
         "expected_adjusted": r["adjusted_expected"]} for r in broken]

    board["tool_issues"] = [
        {"rank": r["rank"], "name": r["player_name"], **issue}
        for r in board["rows"] for issue in r["tool_issues"]]

    # PRE-2017 SCALE HAZARD. grade_normalization corrects each source onto the
    # FanGraphs FV scale, keyed by (source, role, cycle-year), REFERENCE
    # "fangraphs". FanGraphs in this database starts 2017-02-15, so a pre-2017
    # BA board has no contemporaneous reference and the thin-cell fallback
    # pools the overlap across ALL years INCLUDING FUTURE ONES
    # (grade_normalization.py:120-127). That is leak D1 of the audit plan,
    # reproduced on a new source. The parser stamps the era and refuses to
    # guess; choosing a basis is a modelling decision with its own gate.
    board["pre_fangraphs_era"] = snapshot_date < "2017-02-15"

    if resolve:
        board["identity"] = resolve_identities(board["rows"], meta["org"])
    return board


def ingest_drops(*, apply: bool = False, resolve: bool = True,
                 inbox: Path | None = None) -> dict:
    """Walk the inbox. Parse, report, and only write to the DB under apply."""
    inbox = inbox or INBOX_DIR
    files = sorted(p for p in inbox.glob("ba__*.md"))
    results, wrote = [], 0
    for path in files:
        entry: dict = {"file": path.name}
        try:
            board = process_file(path, resolve=resolve)
        except BoardFormatError as exc:
            entry.update({"status": "REFUSED", "reason": str(exc)})
            results.append(entry)
            continue

        entry.update({
            "status": "REFUSED" if board["refusals"] else "PARSED",
            "meta": board["meta"],
            "refusals": board["refusals"],
            "n_rows": len(board["rows"]),
            "adjusted_identity_failures": board["adjusted_identity_failures"],
            "tool_issues": board["tool_issues"],
            "pre_fangraphs_era": board["pre_fangraphs_era"],
            "content_evidence": {
                "in_season_count": board["content_evidence"]["in_season_count"],
                "latest_explicit_date": board["content_evidence"]["latest_explicit_date"],
                "years_referenced": board["content_evidence"]["years_referenced"],
            },
        })
        if resolve:
            ident = board["identity"]
            entry["identity"] = {
                "n_resolved": ident["n_resolved"],
                "n_unresolved": ident["n_unresolved"],
                "unresolved": ident["unresolved"],
                "org_mismatch": ident["org_mismatch"],
            }

        out_csv = PROCESSED_DIR / (path.stem + ".csv")
        _write_normalized_csv(board, out_csv)
        entry["normalized_csv"] = str(out_csv.relative_to(_BASE))

        if apply and not board["refusals"]:
            import storage
            snaps = to_snapshots(board)
            wrote += storage.insert_snapshots(snaps)
            entry["inserted"] = len(snaps)
            archived = PROCESSED_DIR / path.name
            shutil.move(str(path), str(archived))
            entry["archived_to"] = str(archived.relative_to(_BASE))
        results.append(entry)

    return {"files": len(files), "results": results, "rows_written": wrote,
            "applied": apply}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write parsed boards into prospects.db and archive the "
                         "source file (default is a dry run that only reports)")
    ap.add_argument("--no-resolve", action="store_true",
                    help="skip identity resolution (parse-only smoke test)")
    ap.add_argument("--inbox", default=None)
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = ingest_drops(apply=args.apply, resolve=not args.no_resolve,
                          inbox=Path(args.inbox) if args.inbox else None)

    if args.json:
        print(json.dumps(report, indent=1, default=str))
        return 1 if any(r["status"] == "REFUSED" for r in report["results"]) else 0

    print(f"{report['files']} board file(s) in the inbox\n")
    refused = 0
    for r in report["results"]:
        print(f"--- {r['file']}: {r['status']}")
        if r["status"] == "REFUSED" and "reason" in r:
            refused += 1
            print(f"    {r['reason']}")
            continue
        m = r.get("meta", {})
        print(f"    {m.get('team_name')} {m.get('season')} {m.get('board')}, "
              f"{r['n_rows']} rows, snapshot_date {m.get('snapshot_date')} "
              f"({m.get('snapshot_date_basis')})")
        print(f"    label: {m.get('interval_label')!r}")
        for msg in r.get("refusals") or []:
            refused += 1
            print(f"    REFUSED: {msg}")
        if r.get("pre_fangraphs_era"):
            print("    NOTE pre-2017: no contemporaneous FanGraphs reference to "
                  "normalize against. Basis is a gated modelling decision.")
        for f in r.get("adjusted_identity_failures") or []:
            print(f"    ADJUSTED-GRADE IDENTITY BROKE at rank {f['rank']} "
                  f"({f['name']}): {f['raw']} - penalty({f['risk']}) = "
                  f"{f['expected_adjusted']}, board published {f['published_adjusted']}")
        for t in r.get("tool_issues") or []:
            print(f"    TOOL {t['kind']} at rank {t['rank']} ({t['name']}): {t}")
        ident = r.get("identity")
        if ident:
            print(f"    identity: {ident['n_resolved']} resolved, "
                  f"{ident['n_unresolved']} unresolved")
            for u in ident["unresolved"]:
                print(f"      UNRESOLVED rank {u['rank']}: {u['name']} "
                      f"(would be {u['would_be_key']})")
            for o in ident["org_mismatch"]:
                print(f"      ORG MISMATCH rank {o['rank']}: {o['name']} "
                      f"board {o['board_org']} vs db {o['db_org']}")
        print(f"    normalized csv -> {r['normalized_csv']}")
    if report["applied"]:
        print(f"\nwrote {report['rows_written']} snapshot rows")
    else:
        print("\nDRY RUN. Nothing was written to prospects.db. Re-run with --apply.")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
