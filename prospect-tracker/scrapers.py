# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
Scrapers — honest v3.2 rewrite.

The previous version of this module shipped HTML-selector guesses for seven
sources without verifying any of them against real pages. That was wrong.
Most prospect-list sites are either client-rendered React apps (FanGraphs,
ESPN, MLB Pipeline), paywalled (Baseball America, The Athletic), or both.
A naive requests+BeautifulSoup approach will return zero rows for nearly
all of them. There is a reason no open-source baseball library has solved
this problem (see pybaseball PR #397, opened Jan 2024, never merged).

This rewrite is divided into three tiers and is honest about what works:

  Tier A — Working JSON ingestion
      FanGraphs exposes The Board's underlying data via a JSON endpoint
      that bypasses the React shell. This is the only source where a
      script can reliably get current data without manual intervention.

  Tier B — Best-effort HTML scraping
      For sources that render lists in static HTML (ESPN, Just Baseball,
      MLB Pipeline's archived /milb/prospects/<year>/top100/ pages), we
      parse the public ranking view. Each parser has fallback selector
      strategies and prints *diagnostic output* explaining exactly what
      happened — never silent failure. When a site redesigns or paywalls
      a page, the run_monthly.py output tells you which source failed
      and why.

  Tier C — Manual CSV ingest
      For The Athletic (paywall + dynamic) and as a fallback for any
      Tier B parser that fails, we read from data/manual_rankings.csv.
      The user pastes the published list into the CSV (10-15 minutes
      of work per update), and the pipeline ingests it.

A `probe()` function hits every source URL and reports HTTP status, bytes
returned, rows parsed, and a sample player name without writing anything.
Call it via `python run_monthly.py --dry-run`.
"""

from __future__ import annotations

import bisect
import csv
import html
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, asdict, replace as _dataclass_replace
from datetime import date
from pathlib import Path
from typing import Iterable, Callable

import requests as _requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Shared persistent Session with retries and connection pooling for scraper HTTP calls.
SESSION = _requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)

# Proxy object named 'requests' so tests/patches referencing scrapers.requests.get still work.
class _ReqProxy:
    def get(self, *args, **kwargs):
        return SESSION.get(*args, **kwargs)
    def __getattr__(self, name):
        return getattr(_requests, name)

requests = _ReqProxy()
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
MANUAL_CSV = Path(__file__).parent / "manual_rankings.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; prospect-stock-tracker/3.2; "
        "personal hobby project; contact: you@example.com)"
    ),
    "Accept": "text/html,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
RATE_LIMIT_SECONDS = 0.5


@dataclass
class Snapshot:
    source: str
    snapshot_date: str
    interval_label: str
    player_key: str
    player_name: str
    position: str | None
    org: str | None
    rank: int | None
    fv: float | None
    status: str  # active | debuted | injured_list | off_list
    # Per-source 20-80 tool grades. Canonical keys (any subset of):
    # hit, game_pwr, raw_pwr, speed, field, throw, pitch_sel, bat_ctrl (hitters)
    # fb, sl, cb, ch, cmd (pitchers). Missing tools stay absent so we
    # don't confuse "didn't publish" with "graded 0".
    # May also carry an `_extras` dict (sibling, not a tool grade) for
    # source-specific non-grade metadata — FanGraphs ships height,
    # weight, bats, throws, sits, tops, fb_type, tj_date, frame, athl,
    # perf, levers, arm, delivery, contact_style, hard_hit_pct, etc.
    # under _extras so they ride per_source.tools._extras through to UI.
    tools: dict | None = None
    # v26 — True when the source published a "+" upside marker on this FV
    # (e.g., "55+"). Numeric `fv` is the bare tier value (55, not 57.5);
    # the upside signal is preserved separately and aggregated into the
    # consensus point so the displayed FV gets a "+" suffix.
    fv_plus: bool = False


@dataclass
class DraftSnapshot:
    """Amateur prospect snapshot. Parallel to Snapshot but draft-scoped.
    No `org` field — amateurs aren't in an MLB pipeline. School / commit
    take its place, and `draft_year` partitions snapshots by class so the
    same name across classes never collides."""
    source: str            # 'espn_draft' | 'mlb_pipeline_draft' | 'fangraphs' | 'manual'
    snapshot_date: str
    interval_label: str
    player_key: str        # draft_<year>_<name_slug>
    player_name: str
    position: str | None
    school: str | None
    college_commit: str | None
    player_type: str | None  # 'HSh'|'HSp'|'COLh'|'COLp'
    draft_year: int
    rank: int | None
    fv: float | None
    risk: str | None
    status: str            # 'draft_active' | 'drafted' | 'unsigned' | 'transferred'
    tools: dict | None = None
    fv_plus: bool = False  # v26 — "+" upside marker from source string


# Tool taxonomy — canonical keys used everywhere downstream (consensus,
# storage, UI). Sources map their own labels onto these via the
# per-scraper translation tables (e.g. PIPELINE_TOOL_KEY below).
# pitch_sel and bat_ctrl are FG-published 20-80 grades treated as
# first-class hitter tools so they aggregate cross-source and feed
# composite_off / Tool composites rather than living in _extras.
HITTER_TOOL_KEYS = ("hit", "game_pwr", "raw_pwr", "speed", "field", "throw",
                    "pitch_sel", "bat_ctrl")
# `ct` (cutter) is a distinct pitch family Just Baseball grades separately.
# FG and MLB Pipeline today fold it into FB; the consensus is fine with
# sparse keys, so prospects without a published cutter grade simply lack
# the slot.
PITCHER_TOOL_KEYS = ("fb", "sl", "cb", "ch", "cmd", "ct")
ALL_TOOL_KEYS = HITTER_TOOL_KEYS + PITCHER_TOOL_KEYS


def fix_mojibake(text: str) -> str:
    """Attempt to fix common UTF-8/Latin-1 encoding corruption (mojibake).

    Example: 'Jes\xfds' (UTF-8 'Jesús' misinterpreted as Latin-1) → 'Jesús'
    """
    if not text:
        return text
    if '\ufffd' in text or '\x00' in text:
        try:
            # Encode as Latin-1 (the wrong interpretation), decode as UTF-8
            text = text.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    # Collapse runs of whitespace to one space and trim ends
    return re.sub(r'\s+', ' ', text).strip()


# Patterns that surface in scraped writeups but aren't actual scouting
# narrative — page navigation, "Watch the video" link tails, and section
# headers stripped of their structure when HTML → text conversion
# flattens them. Centralized here so every source path strips the same
# cruft consistently. Apply via `_clean_report_prose()` before storing
# any writeup into a Snapshot's tools._extras.report field.
_NAVIGATION_PREFIXES = (
    "Fantasy baseball home page",
    "Draft Guide today",
    "Reliever depth chart",
    "Latest stories",
    "More stories",
    "Read more from",
)

# Trailing tails — newspaper/web "more from..." link blocks. Match
# from " >> " or "  >> " through end-of-string.
_TRAILING_LINK_TAIL_RE = re.compile(
    r"\s*>>\s*(?:Video Scouting Report|Watch the highlights?|Read more|"
    r"Click here|Watch the video|Full scouting report|See the video).*$",
    re.IGNORECASE | re.DOTALL,
)

# Leading section-header noise FG sometimes ships when its HTML
# splits a player block awkwardly — "Scouting Report: Hits ..." gets
# the literal "Scouting Report: " prefix that's redundant with the
# panel header in our UI.
_LEADING_HEADER_RE = re.compile(
    r"^(?:Scouting\s+Report|Tools\s+and\s+Background|Player\s+Bio|Bio)\s*:?\s*",
    re.IGNORECASE,
)

# Leading writeup-source label noise — MLB Pipeline draft + overseas
# scrapes prepend "Video scouting report »" (or •, —, :, etc.) before
# the actual prose. The » (U+00BB) is the most common form in the
# stored draft data; bullets and dashes appear in newer scrapes.
# Character class also includes the U+FFFD replacement char that shows
# up when latin-1 / utf-8 decode mojibakes the separator.
_LEADING_VIDEO_REPORT_RE = re.compile(
    r"^Video\s+scouting\s+report\s*[•‣◦·–—:\-»«›‹>?�]+\s*",
    re.IGNORECASE,
)

# Leading scouting-BIO line — several sources (Just Baseball most visibly)
# prepend a pipe-delimited vitals line before the prose, e.g.:
#   "Height/Weight: 6'1", 190 | Bat/Throw: S/R | IFA: $950K - 2024 (MIL) | ETA: 2027"
# It duplicates the structured bio our UI already renders above the writeup,
# so it's noise inside the narrative. We detect it structurally (a leading
# line carrying known vitals labels, usually pipe-separated) rather than
# matching one source's exact wording, so every source is handled the same.
# Each field label is "Label:" — count >=2 (or a pipe + >=1) to fire, which
# real prose never trips.
_BIO_FIELD_LABEL_RE = re.compile(
    r"(?:Height\s*/\s*Weight|Ht\s*/\s*Wt|Bat\s*/\s*Throw|Bats?\s*/\s*Throws?"
    r"|ETA|IFA|Drafted|Draft|Signed|Signing|Bonus|Age|DOB|Born|Position|Pos"
    r"|Weight|Height)\s*:",
    re.IGNORECASE,
)


def _clean_report_prose(text: str | None) -> str | None:
    """Centralized writeup cleaner — strips page-navigation cruft,
    trailing 'video link' tails, leading section headers, and other
    formatting artifacts that bleed through during HTML→text scrape.
    Returns None when the cleaned text is empty / too short to be a
    real scouting report (cuts down on degenerate outputs).

    Idempotent — re-running on already-cleaned text is a no-op."""
    if not text:
        return None
    s = text

    # 0. Owner copy rule (2026-06-11, enforced site-wide by
    # tools/strip_emdashes.py): no em-dashes in user-facing prose. Source
    # writeups arrive with them; swap to the house plain hyphen at the
    # ingest boundary so generated exports never trip the copy check.
    s = s.replace(" — ", " - ").replace("—", " - ").replace("  ", " ")

    # 1. Encoding fix only — explicitly DO NOT call fix_mojibake because
    # its whitespace pass collapses runs of newlines (including the
    # `\n\n` paragraph separators downstream renderers rely on).
    if '�' in s or '\x00' in s:
        try:
            s = s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    if not s:
        return None

    # 2. Strip leading navigation cruft: if any _NAVIGATION_PREFIXES
    #    token appears within the first 300 chars AND is followed by
    #    `>>` within 50 chars, drop everything up through that `>>`.
    head = s[:400]
    for prefix in _NAVIGATION_PREFIXES:
        idx = head.find(prefix)
        if idx >= 0:
            tail = s[idx:]
            # Look for the >> within 100 chars after the prefix
            m = re.search(r">>", tail[:200])
            if m:
                cut = idx + m.end()
                s = s[cut:].lstrip()
                break

    # 3. Generic fallback: if `>>` appears within the first 250 chars
    #    AND the preceding text contains a hint of navigation
    #    (very short sentences ending with a bullet `•` or capital
    #    "Top 100" etc.), strip up to the `>>`. This catches the
    #    Nolan McLean variant ("Draft Guide today! >> ...").
    m = re.search(r">>", s[:250])
    if m and ("•" in s[:m.start()] or "Draft Guide" in s[:m.start()]
             or "Top 100" in s[:m.start()]):
        s = s[m.end():].lstrip()

    # 4. Strip trailing video / read-more tails.
    s = _TRAILING_LINK_TAIL_RE.sub("", s).rstrip()

    # 5. Strip leading section header artifacts.
    s = _LEADING_HEADER_RE.sub("", s).lstrip()
    s = _LEADING_VIDEO_REPORT_RE.sub("", s).lstrip()

    # 5b. Strip a leading scouting-bio line (Height/Weight | Bat/Throw |
    #     IFA/Draft | ETA ...). Look only at the first line; drop it (through
    #     the following blank line / newline) when it carries >=2 vitals
    #     labels, or a pipe plus >=1 - structural so it generalizes across
    #     sources without matching prose. Loop in case two bio lines stack.
    for _ in range(2):
        nl = s.find("\n")
        first_line = s if nl < 0 else s[:nl]
        n_fields = len(_BIO_FIELD_LABEL_RE.findall(first_line))
        looks_bio = n_fields >= 2 or ("|" in first_line and n_fields >= 1)
        if not looks_bio:
            break
        s = (s[nl + 1:] if nl >= 0 else "").lstrip("\n").lstrip()

    # 6. Collapse non-breaking space + double spaces.
    s = s.replace(" ", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()

    if len(s) < 15:
        return None
    return s


def _backfill_writeup_cleanup(
    paths: tuple[str, ...] = (
        "data/scout_reports.json",
        "data/draft_timeseries.json",
        "data/overseas_timeseries.json",
    ),
) -> dict[str, tuple[int, int]]:
    """One-shot pass that re-applies `_clean_report_prose` to every
    writeup already stored on disk. The scrapers all call the cleaner
    at scrape time, but writeups ingested BEFORE the cleaner was wired
    in (or before any later regex tweaks) still carry cruft like
    "Video scouting report" or "Read the full report >>". This walks
    every known writeup field in each JSON file in place.

    Returns {path: (cleaned, total)} for logging."""
    import json
    import pathlib

    results: dict[str, tuple[int, int]] = {}

    def _maybe_clean(obj: dict, key: str, ctr: list[int]) -> None:
        """Re-clean obj[key] if it's a non-trivial string."""
        v = obj.get(key)
        if not isinstance(v, str) or not v.strip():
            return
        ctr[1] += 1
        cleaned = _clean_report_prose(v)
        if cleaned is not None and cleaned != v:
            obj[key] = cleaned
            ctr[0] += 1
        elif cleaned is None and len(v) >= 15:
            # Cleaner rejected the string outright — leave the original
            # in place rather than dropping the writeup entirely.
            pass

    def _walk_tool_grades(prospects: list) -> tuple[int, int]:
        """Per-prospect: scan tool_grades[*]._extras + each snapshot's
        points[].tools._extras for writeup fields. The per-snapshot
        path is where the draft/overseas sources actually carry their
        prose — tool_grades is the latest-grade flat view."""
        ctr = [0, 0]
        EXTRAS_KEYS = ("report", "writeup", "bio", "scouting_report", "prose")

        def _scan_extras(extras: dict) -> None:
            if not isinstance(extras, dict):
                return
            for k in EXTRAS_KEYS:
                _maybe_clean(extras, k, ctr)

        for p in prospects or []:
            if not isinstance(p, dict):
                continue
            tg = p.get("tool_grades") or {}
            for sub in tg.values() if isinstance(tg, dict) else []:
                if isinstance(sub, dict):
                    _scan_extras(sub.get("_extras") or {})
            # Per-snapshot writeups — draft + overseas attach the
            # historical prose to each `points[].tools._extras` so the
            # report-cleaner needs to walk every snapshot, not just the
            # latest tool_grades summary.
            for snap in (p.get("points") or []):
                if not isinstance(snap, dict):
                    continue
                tools = snap.get("tools") or {}
                if isinstance(tools, dict):
                    _scan_extras(tools.get("_extras") or {})
            # A handful of draft sources lift the report up to the
            # prospect object directly — clean those too.
            for k in EXTRAS_KEYS:
                _maybe_clean(p, k, ctr)
        return tuple(ctr)  # type: ignore[return-value]

    for path_str in paths:
        path = pathlib.Path(path_str)
        if not path.exists():
            print(f"  skip (missing): {path_str}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  skip (parse failed): {path_str} — {exc}")
            continue

        cleaned = 0
        total = 0

        if path.name == "scout_reports.json":
            # Shape: { player_key: { source: [ {date, label, text, hash}, ... ] } }
            for sources in data.values() if isinstance(data, dict) else []:
                if not isinstance(sources, dict):
                    continue
                for entries in sources.values():
                    if not isinstance(entries, list):
                        continue
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        ctr = [0, 0]
                        _maybe_clean(entry, "text", ctr)
                        cleaned += ctr[0]
                        total += ctr[1]
        elif path.name == "draft_timeseries.json":
            for cls in (data.get("classes") or []):
                c, t = _walk_tool_grades(cls.get("prospects") or [])
                cleaned += c
                total += t
        elif path.name == "overseas_timeseries.json":
            for league in (data.get("leagues") or []):
                c, t = _walk_tool_grades(league.get("prospects") or [])
                cleaned += c
                total += t

        if cleaned:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        results[path_str] = (cleaned, total)
        print(f"  {path_str}: cleaned {cleaned} of {total} writeups")

    return results


# FanGraphs board CSVs encode draft eligibility INSIDE the Name column
# rather than in a column of its own: a single TRAILING asterisk marks a
# draft-eligible sophomore and a leading "**" marks a senior. That is a
# source-format footnote, not part of the human's name, and it leaked all
# the way to the served board. Measured in prospects.db before this fix
# (distinct names per table, trailing "*" / leading "**"):
#   snapshots        4 / 0   (Derek Curiel, Ty Head, Chris Rembert,
#                             Sawyer Strosnider; 7 rows)
#   players          3 / 0   (3 rows)
#   draft_snapshots  5 / 42  (51 rows)
#   draft_players    0 / 38  (38 rows)
# The 42 leading-"**" draft_snapshots names are the 2018-2020 classes
# ("**Jake Mangum", "**Noah Song") and they are exactly the 42 that
# reached draft_timeseries.json.
#
# fix_mojibake() is the only cleaner the CSV paths apply (fangraphs_csv.py
# :304, draft_csv.py:134, overseas_csv.py:129) and it is a latin-1 round
# trip plus whitespace collapse, so it has no concept of a marker and
# carried the character straight into Snapshot.player_name.
#
# What the strip costs, scoped to where it was actually measured. On the
# three ACTIVE-BOARD rows the marker is redundant: the FanGraphs board path
# stores class standing structurally on tools._extras (fangraphs_csv.py
# :760-763 carries sign_year, sign_market, signed_from and age), and all
# four were measured present on each of those three rows, so sophomore /
# senior is recoverable without the asterisk.
#
# That argument does NOT extend to the 42 leading-"**" DRAFT rows, and the
# claim is deliberately not made for them. draft_csv.py:255-256 builds its
# own _extras from age, height, weight, bats, throws, fg_player_id, trend,
# pick_overall, pick_team, top_100 and video_url -- no sign_year, no
# sign_market, no signed_from. For those rows the marker is the only place
# the senior flag was recorded, and stripping it drops that bit. Accepted:
# it is a source-format footnote on a 2018-2020 draft display name, the
# FanGraphs CSV can re-supply it, and a footnote character rendering inside
# a human's name on the served board is the larger defect.
#
# Unaffected either way: normalize_key() below drops every non-alphanumeric,
# so the player_key was always clean, which is exactly why no identity guard
# ever tripped on this in the first place.
#
# Deliberately conservative: only asterisk runs at the very START or the
# very END are removed. An asterisk sitting INSIDE a name would be a
# different and unknown case, so it is left alone rather than guessed at.
# Measured: zero such rows across snapshots, players, draft_snapshots and
# draft_players. A name that is nothing BUT markers is also returned
# untouched, since blanking a display name is worse than showing the mark.
_NAME_MARKER_RE = re.compile(r"^\*+\s*|\s*\*+$")


def strip_name_markers(name: str) -> str:
    """Strip FanGraphs draft-eligibility asterisk markers off a display name.

    Leading "**" (senior) and trailing "*" (draft-eligible sophomore) go;
    an interior asterisk stays. Applied at the DB read boundary in
    storage.load_all_snapshots(), so it is durable even if a fresh
    FanGraphs drop re-mints a dirty row into the snapshots table.
    """
    if not name or "*" not in name:
        return name
    # Trim the ends FIRST. The marker anchors on the true start/end of the
    # string, so a stray leading space ("  **Noah Song") would otherwise
    # leave the marker in place and make the function non-idempotent.
    cleaned = _NAME_MARKER_RE.sub("", re.sub(r"\s+", " ", name).strip())
    return cleaned.strip() or name


def normalize_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return canonical_player_key(s)


def canonical_player_key(player_key: str) -> str:
    """Collapse known alternate player keys onto the canonical key."""
    return _CANONICAL_KEYS.get(player_key, player_key)


# Maps alternate player_keys to their canonical form so different source
# spellings of the same player collapse to one DB key.
# key = what normalize_key() would produce for the alternate spelling, OR an
#       ingest-minted suffix fork of the canonical key (see the oliveto note)
# value = canonical key (typically matches the MLB API / most common spelling)
#
# Applied in storage.load_all_snapshots() on EVERY snapshot read, which is the
# path consensus.build_timeseries consumes, so an entry here is durable even if
# an ingest re-mints the alternate key into the snapshots table.
_CANONICAL_KEYS: dict[str, str] = {
    "leodalis_de_vries": "leo_de_vries",
    # Josuar Gonzalez (SFG SS) has appeared under three spellings across
    # sources/cycles. Just Baseball used "Josuar De Jesus" without a team;
    # collapsing prevents the null-org duplicate from surfacing on the farm page.
    "josuar_de_jesus": "josuar_gonzalez",
    "josuar_de_jesus_gonzalez": "josuar_gonzalez",
    # JoJo Parker (TOR 3B/SS). TJStats pre-season + Just Baseball listed him as
    # "Joseph Parker" without a team; FanGraphs uses "JoJo Parker" (TOR).
    "joseph_parker": "jojo_parker",
    # MLB/Statcast and current rosters use the suffix/nickname forms below.
    # Some ranking/editorial sources omit the suffix or use the given name,
    # which otherwise creates a headshot-less duplicate card.
    "george_lombard": "george_lombard_jr",
    "leonardo_bernal": "leo_bernal",
    # Michael Oliveto (DET C, mlbam 834672, b.2007-02-03). ONE human who was
    # spread across THREE keys, the inverse of the _SPLIT_KEYS cases below.
    # fangraphs_csv._canonical_owners() scores the FanGraphs PIDs seen for a
    # slug by (cycle_count, max_fv). Oliveto appeared once with pid None (the
    # 2025-07-31 board, before he had a FanGraphs minor-league page) and once
    # with pid "sa3069256" (2026-02-12): a 1-1 tie on both terms. The None
    # entry sorted first, canonical_pid came back None, and the
    # "__all_noid__" sentinel suffixed EVERY row, so neither snapshot kept
    # the bare key. A later cycle that saw only "sa3069256" had nothing to
    # tie against and wrote the bare key.
    # Proof they are one human: the "2026tradedeadline" snapshot sitting on
    # the BARE key carries _extras.fg_player_id_str == "sa3069256".
    # Merged into the bare key by tools/repair_michael_oliveto_merge.py;
    # these entries stop a future CSV drop from re-fracturing him.
    "michael_oliveto__noid": "michael_oliveto",
    "michael_oliveto__sa3069256": "michael_oliveto",
}


# The OPPOSITE direction of _CANONICAL_KEYS: two DIFFERENT humans whose
# names normalize to the same slug. Keyed by (colliding slug, mlbam_id of
# the newcomer) -> the discriminated key the newcomer's rows live under.
# Consulted wherever a player key is resolved WITH an MLBAM id in hand
# (stats.resolve_mlbam_id / stats.bulk_resolve_ids cache bindings,
# mlbam_ingest discovery). Name-only resolution keeps the plain slug,
# which stays with the incumbent identity.
_SPLIT_KEYS: dict[tuple[str, int], str] = {
    # The 2026 DSL Giants OF signee Jose Valdez (mlbam 838649, b. 2009)
    # collides with the retired Tigers RHP Jose A. Valdez (MLB debut
    # 2015) — both slug to "jose_a_valdez". The retiree keeps the plain
    # slug (his Pipeline 2014-2016 snapshots + bbref career_war live
    # there); the signee's rows live under the split key.
    ("jose_a_valdez", 838649): "jose_valdez_sfg",
    # The Angels OF Carlos Castillo (mlbam 837825, b. 2008-09-15)
    # collides with the Pirates RHP Carlos Castillo (mlbam 807962,
    # b. 2006-02-04) - both slug to "carlos_castillo". The pitcher is the
    # incumbent (FanGraphs SP/PIT snapshots 2024-02-14 and 2024-08-01,
    # the A+ PIT career line, the milb headshot); the outfielder arrived
    # on the 2026-07-23 trade-deadline board and lives under the split
    # key. Found by test_identity_collisions on 2026-07-29.
    ("carlos_castillo", 837825): "carlos_castillo_laa",
}


def split_key_for_mlbam(player_key: str, mlbam_id) -> str | None:
    """Return the discriminated key for (slug, mlbam_id) when this MLBAM id
    is a known slug-collision newcomer (see _SPLIT_KEYS), else None.

    `player_key` is collapsed through canonical_player_key first so
    alternate spellings of the colliding slug hit the map too."""
    if mlbam_id is None:
        return None
    try:
        mid = int(mlbam_id)
    except (TypeError, ValueError):
        return None
    return _SPLIT_KEYS.get((canonical_player_key(player_key), mid))


def _parse_fv(raw) -> float | None:
    """Accepts '70', '55+', '50/55' (PV/FV), 70 (int/float). Returns float.

    v26 — '+' grades are now returned as the bare tier value (55+ → 55).
    The earlier +2.5 interpolation inflated numeric FV in a way that
    obscured tier boundaries. The upside signal is preserved separately
    via `_parse_fv_full` (returns (value, has_plus)) for callers that
    need to flag it on the snapshot.
    """
    fv, _plus = _parse_fv_full(raw)
    return fv


def _parse_fv_full(raw) -> tuple[float | None, bool]:
    """Same parser as `_parse_fv` but also returns whether the source's
    string carried a trailing '+' upside marker.

    Used by FV (not tool-grade) call sites where we want to flag the
    snapshot as having upside without inflating the numeric grade. A
    '55+' returns (55.0, True); a '55' returns (55.0, False); a '50/55'
    PV/FV string returns (55.0, False) — the slash is a published
    pair, not an upside marker.
    """
    if raw is None:
        return None, False
    if isinstance(raw, (int, float)):
        return float(raw), False
    raw = str(raw).strip()
    if not raw:
        return None, False
    # PV/FV format — take the right side (the FV). Some older Pipeline
    # bios use the 2-8 scouting shorthand ("4/5") instead of 20-80
    # ("40/50"); scale those single-digit grades before returning.
    if "/" in raw:
        parts = [p.strip() for p in raw.split("/") if p.strip()]
        if len(parts) >= 2 and all(re.fullmatch(r"\d(?:\+)?", p) for p in parts[:2]):
            right = parts[-1].rstrip("+")
            return float(right) * 10.0, parts[-1].endswith("+")
        raw = parts[-1] if parts else raw
    has_plus = raw.endswith("+")
    if has_plus:
        raw = raw[:-1]
    try:
        fv = float(raw)
    except ValueError:
        return None, False
    # JB table extraction can occasionally concatenate the preceding
    # future tool grade with the FV cell ("55" + "60" => "560"). Recover
    # the trailing 20-80 grade when that shape is obvious; otherwise
    # reject out-of-scale FVs so they cannot poison consensus.
    if fv > 80 and raw.isdigit() and len(raw) >= 3:
        tail = float(raw[-2:])
        if 20 <= tail <= 80:
            fv = tail
    if 2 <= fv <= 8:
        fv *= 10.0
    if fv < 20 or fv > 80:
        return None, False
    return fv, has_plus


# MLB Pipeline labels its tool grades with words/abbreviations that
# differ from our canonical short keys. This table is the single point
# of translation; anything not in here is silently dropped (e.g.,
# "Splitter" — future addition).
PIPELINE_TOOL_KEY = {
    "hit": "hit",
    "power": "game_pwr", "raw power": "raw_pwr",
    "run": "speed", "speed": "speed",
    "arm": "throw", "throw": "throw",
    "field": "field", "fielding": "field",
    "fastball": "fb", "fb": "fb",
    "slider": "sl", "sl": "sl",
    "curveball": "cb", "curve": "cb", "cb": "cb",
    "changeup": "ch", "change": "ch", "ch": "ch",
    "control": "cmd", "command": "cmd", "ctl": "cmd",
}


# ESPN tool labels → canonical tool keys. Mirrors PIPELINE_TOOL_KEY but
# matches the long-form labels ESPN ships in its prospect commentary
# (e.g. "Game Power" instead of "Power", "Fielding" instead of "Field").
ESPN_TOOL_KEY: dict[str, str] = {
    "hit":          "hit",
    "game power":   "game_pwr",
    "raw power":    "raw_pwr",
    "power":        "game_pwr",   # ambiguous fallback when ESPN ships only "Power"
    "speed":        "speed",
    "run":          "speed",
    "fielding":     "field",
    "field":        "field",
    "throwing":     "throw",
    "arm":          "throw",
    # Pitcher tools — same regex captures them if ESPN ever switches to a
    # mixed pitcher/hitter section format. Currently their pitcher tool
    # lines look like "Fastball: 60/70" rather than the hitter Hit/Power
    # block but the helper handles both shapes.
    "fastball":     "fb",
    "slider":       "sl",
    "curveball":    "cb",
    "curve":        "cb",
    "changeup":     "ch",
    "change":       "ch",
    "command":      "cmd",
    "control":      "cmd",
}


def _parse_espn_tools(commentary_text: str) -> dict[str, float] | None:
    """Pull tool grades from an ESPN prospect's commentary block.

    ESPN historically shipped tools as 'Label: PV/FV' (left=present,
    right=future). The 2025+ articles dropped that structured format
    in favor of prose ("plus runner", "70 raw power") — when no
    structured pairs are found, we fall through to the prose parser.
    Out-of-range values (< 20 or > 80) are dropped silently.
    """
    if not commentary_text:
        return None
    tools: dict[str, float] = {}
    # Match 'Label: 45/50' (capture FV = group 2) OR 'Label: 50'
    # (capture FV = group 3). Trailing (?![\d/]) prevents "55/6" inside
    # "55/60" from being interpreted as FV=6.
    pattern = re.compile(
        r"([A-Za-z][A-Za-z ]+?):\s*(?:\d+\s*/\s*(\d+)|(\d+))(?![\d/])"
    )
    for m in pattern.finditer(commentary_text):
        label = m.group(1).strip().lower()
        key = ESPN_TOOL_KEY.get(label)
        if not key:
            continue
        fv_str = m.group(2) or m.group(1) and m.group(3)
        if not fv_str:
            continue
        try:
            grade = float(fv_str)
        except (TypeError, ValueError):
            continue
        if grade < 20 or grade > 80:
            continue
        tools[key] = grade
    if tools:
        return tools
    # Fall through: ESPN now publishes tools as prose. Try the prose
    # extractor — quality is lower but McDaniel's narrative still
    # encodes opinions worth feeding into consensus (per-source
    # tooltip discloses prose-estimated provenance).
    return _parse_espn_prose_tools(commentary_text)


# Descriptor → 20-80 grade. Includes hyphenated and non-hyphenated
# variants ("plus-plus" / "double-plus" / "above-average" / "above average").
ESPN_DESCRIPTOR_GRADE: dict[str, float] = {
    "plus-plus": 70.0, "double-plus": 70.0, "elite": 70.0,
    "80-grade": 80.0, "80 grade": 80.0,
    "plus": 60.0,
    "above-average": 55.0, "above average": 55.0, "solid-average": 55.0,
    "average": 50.0, "solid average": 50.0,
    "below-average": 45.0, "below average": 45.0, "fringe": 45.0,
    "well-below": 35.0, "well below": 35.0,
    "30-grade": 30.0, "30 grade": 30.0,
}

# Tool noun → canonical key. Ordered so longest phrases win
# ("raw power" beats "power"); the prose parser iterates this list and
# takes the first match for each key. Each tuple is (noun, key, allow_pre).
# `allow_pre`: True means "<descriptor> <noun>" works (e.g., "plus runner");
# False means only "<NN>-grade <noun>" works (e.g., "70-grade arm" for
# nouns whose adjective form is ambiguous with general English).
ESPN_PROSE_TOOL_NOUN: list[tuple[str, str, bool]] = [
    ("raw power",   "raw_pwr", True),
    ("game power",  "game_pwr", True),
    ("power",       "game_pwr", True),     # fallback when only "power" appears
    ("hit tool",    "hit",      True),
    ("contact tool","hit",      True),
    ("runner",      "speed",    True),
    ("run tool",    "speed",    True),
    ("speed",       "speed",    True),
    ("defender",    "field",    True),
    ("defense",     "field",    True),
    ("glove",       "field",    True),
    ("arm",         "throw",    False),    # "his arm" is too generic for adj match
    ("throwing",    "throw",    True),
    ("fastball",    "fb",       True),
    ("slider",      "sl",       True),
    ("sweeper",     "sl",       True),
    ("curveball",   "cb",       True),
    ("curve",       "cb",       True),
    ("changeup",    "ch",       True),
    ("splitter",    "ch",       True),
    ("cutter",      "ct",       True),
    ("command",     "cmd",      True),
    ("control",     "cmd",      True),
]


def _velocity_to_fb_grade(sits_min: float, sits_max: float | None,
                          peak: float | None) -> float | None:
    """Map a fastball velocity band to an approximate FB grade.

    Conservative scouting rule of thumb (McDaniel's own writing):
      sits 90-92 → 50,  93-95 → 55,  94-97 → 60,  96-99 → 65,  98+ → 70.
    Anchor on the upper end of the sits band; if missing, anchor on peak.
    """
    anchor = sits_max if sits_max is not None else (peak if peak is not None else sits_min)
    if anchor is None:
        return None
    if anchor >= 99: return 70.0
    if anchor >= 97: return 65.0
    if anchor >= 95: return 60.0
    if anchor >= 93: return 55.0
    if anchor >= 90: return 50.0
    if anchor >= 87: return 45.0
    return 40.0


# Pre-compiled regexes for the prose parser.
_ESPN_PROSE_VELO_RE = re.compile(
    r"(\d{2,3})\s*[-–]\s*(\d{2,3})\s*(?:mph)?\s*fastball"
    r"(?:[^.]{0,80}peaks?\s*(?:at)?\s*(\d{2,3}))?",
    re.IGNORECASE,
)
# Numeric grade pattern: "70-grade fastball" / "70 grade fastball" / "70 raw power".
# The trailing `\s+` is required so we don't match "2024 draft" or "19 yo"
# — only a digits-then-tool-noun sequence. The noun is mapped to a
# canonical key via ESPN_PROSE_TOOL_NOUN; unknown nouns are silently dropped.
_ESPN_PROSE_NUMERIC_RE = re.compile(
    r"\b(\d{2})(?:[\s-]?grade)?\s+([a-z][a-z ]{2,15})", re.IGNORECASE,
)


def _parse_espn_prose_tools(commentary_text: str) -> dict[str, float] | None:
    """Best-effort prose parser for ESPN tool grades.

    Extracts:
      - "<NN>-grade <noun>" patterns (e.g., "70 raw power")
      - "<descriptor> <noun>" within a 15-char window (e.g., "plus runner")
      - Fastball velocity bands ("94-98 mph fastball") → FB grade
    Returns dict[key→grade] or None when nothing parseable found. First
    match per tool wins (rest are downgraded since the narrative
    typically opens with the loudest tool).
    """
    if not commentary_text:
        return None
    text = commentary_text
    tools: dict[str, float] = {}

    # Pass 1: "NN-grade noun" patterns ("70 raw power", "60-grade fastball").
    for m in _ESPN_PROSE_NUMERIC_RE.finditer(text):
        grade = float(m.group(1))
        if grade < 20 or grade > 80:
            continue
        noun_chunk = m.group(2).lower().strip()
        for noun, key, _ in ESPN_PROSE_TOOL_NOUN:
            if noun_chunk.startswith(noun):
                if key not in tools:
                    tools[key] = grade
                break

    # Pass 2: "<descriptor> <noun>" within close proximity. Build a single
    # mega-regex per noun for speed.
    desc_alt = "|".join(re.escape(d) for d in ESPN_DESCRIPTOR_GRADE)
    for noun, key, allow_pre in ESPN_PROSE_TOOL_NOUN:
        if not allow_pre or key in tools:
            continue
        # "<descriptor>[ space + up to 2 short words ] <noun>" — keep the
        # window tight so unrelated descriptors elsewhere in the paragraph
        # don't bleed in. Allows for "above-average to plus defender" by
        # also matching "plus defender" inside the same span.
        pat = re.compile(
            rf"\b({desc_alt})\b(?:[\s\w]{{0,20}}?)\b{re.escape(noun)}\b",
            re.IGNORECASE,
        )
        m = pat.search(text)
        if m:
            desc = m.group(1).lower()
            grade = ESPN_DESCRIPTOR_GRADE.get(desc)
            if grade is not None:
                tools[key] = grade

    # Pass 3: velocity → fb grade (only when fb wasn't already captured).
    if "fb" not in tools:
        velo_m = _ESPN_PROSE_VELO_RE.search(text)
        if velo_m:
            try:
                lo = float(velo_m.group(1))
                hi = float(velo_m.group(2))
                peak = float(velo_m.group(3)) if velo_m.group(3) else None
                fb_grade = _velocity_to_fb_grade(lo, hi, peak)
                if fb_grade is not None:
                    tools["fb"] = fb_grade
            except (TypeError, ValueError):
                pass

    return tools or None


def _clean_pipeline_writeup(bio_text: str) -> str | None:
    """Extract the narrative prose from an MLB Pipeline bio's contentText.

    Pipeline bios mix the structured "Scouting grades: Hit: ... | Overall: NN"
    line with the prospect's narrative paragraph(s). We:
      1. Promote JSON-escaped `\\n` to real newlines so paragraph breaks
         survive (BeautifulSoup parsing later collapses them otherwise).
      2. Unescape HTML entities and strip any leftover tags Pipeline ships
         around the prose (<p>, <em>, etc).
      3. Fix UTF-8 mojibake from the upstream cache.
      4. Drop the Scouting grades line — tools already parsed it.
      5. Collapse runs of whitespace within paragraphs but preserve
         paragraph breaks (`\\n\\n`).

    Returns the cleaned prose, or None if nothing meaningful remains.
    """
    if not bio_text:
        return None
    raw = bio_text.replace("\\n", "\n").replace("\\t", " ")
    raw = html.unescape(raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Drop the Scouting grades line in its entirety. Done BEFORE
    # `fix_mojibake` because the latter normalizes runs of whitespace
    # (including newlines) into single spaces, which would collapse
    # the `\n\n` paragraph separators we rely on below.
    raw = re.sub(r"Scouting grades:[^\n]*Overall:\s*\d+\s*\n?", "", raw,
                 count=1, flags=re.IGNORECASE)
    # Split paragraphs first, THEN clean each one. fix_mojibake runs
    # per-paragraph so its space-collapsing only affects within-paragraph
    # runs, leaving the paragraph boundary intact.
    paragraphs = []
    for p in raw.split("\n\n"):
        p = fix_mojibake(p)
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            paragraphs.append(p)
    return "\n\n".join(paragraphs) or None


def _parse_pipeline_tools(bio_text: str) -> dict[str, float] | None:
    """Pull tool grades from an MLB Pipeline bio's Scouting grades line.

    Format observed:
        Scouting grades: Hit: 55 | Power: 60 | Run: 45 | Arm: 50 |
        Field: 55 | Overall: 55
    Some bios ship a PV/FV pair ("Hit: 55/60") for borderline prospects.
    When that happens, the right-hand integer (the future value) is the
    authoritative grade. The Overall: token is parsed separately for FV
    and ignored here; we capture every other "Label: NN" or "Label: NN/MM"
    pair and map via PIPELINE_TOOL_KEY. Returns None when no tools were
    recognized.
    """
    if not bio_text:
        return None
    # Look for "Scouting grades:" preamble so we don't accidentally
    # match "Hit: " inside narrative prose elsewhere in the bio. Allow
    # the preamble token to be absent on older snapshots — fall back to
    # scanning the whole bio for the canonical pipe-delimited segment.
    seg = bio_text
    m = re.search(r'Scouting grades:\s*(.+)', bio_text, flags=re.IGNORECASE)
    if m:
        seg = m.group(1)
    tools: dict[str, float] = {}
    # Two-arm pattern: PV/FV (group 2 = FV) OR single value (group 3).
    # The trailing (?![\d/]) lookahead prevents matching "Hit: 55/6" as
    # FV=6 when the real text is "Hit: 55/60" — the slash + digit must
    # not be followed by another digit or slash.
    pattern = re.compile(
        r"([A-Za-z][A-Za-z ]+?):\s*(?:\d+\s*/\s*(\d+)|(\d+))(?![\d/])"
    )
    for m in pattern.finditer(seg):
        label = m.group(1).strip().lower()
        key = PIPELINE_TOOL_KEY.get(label)
        if not key:
            continue
        fv_str = m.group(2) or m.group(3)
        try:
            grade = float(fv_str)
        except (TypeError, ValueError):
            continue
        if grade < 20 or grade > 80:
            continue
        tools[key] = grade
    return tools or None


def _parse_csv_tools(row: dict, line_no: int = 0) -> dict[str, float] | None:
    """Pull 20-80 tool grades from a manual_rankings.csv row.

    Reads any of the canonical tool columns
    (hit, game_pwr, raw_pwr, speed, field, throw, fb, sl, cb, ch, cmd).
    Empty cells are dropped; values outside [20, 80] are logged and
    dropped (not clamped) so transcription typos surface instead of
    quietly degrading the dataset. Returns None when no tools were
    provided on this row, matching the Snapshot.tools=None convention
    for "source didn't publish".
    """
    tools: dict[str, float] = {}
    for key in ALL_TOOL_KEYS:
        v = (row.get(key) or "").strip()
        if not v:
            continue
        grade = _parse_fv(v)
        if grade is None:
            log.warning("manual_rankings line %d: unparseable %s=%r",
                        line_no, key, v)
            continue
        if grade < 20 or grade > 80:
            log.warning("manual_rankings line %d: %s=%s out of [20,80] range",
                        line_no, key, grade)
            continue
        tools[key] = grade
    return tools or None


# ---------------------------------------------------------------------------
# HTTP helper with diagnostic logging
# ---------------------------------------------------------------------------

class FetchResult:
    """Carries both the response body and metadata about the fetch."""
    def __init__(self, body: str, status: int, from_cache: bool, url: str):
        self.body = body
        self.status = status
        self.from_cache = from_cache
        self.url = url
        self.bytes = len(body)

    def __repr__(self):
        return (f"FetchResult(url={self.url!r}, status={self.status}, "
                f"bytes={self.bytes}, cached={self.from_cache})")


_SCRAPER_CURRENT_YEAR_TTL_SECONDS = 24 * 3600  # 24h — current-year pages
_SCRAPER_PRIOR_YEAR_TTL_SECONDS   = 30 * 24 * 3600  # 30d — historical pages

def _cache_ttl_for_key(cache_key: str) -> int:
    """v23 — Year-aware TTL for scout-ranking cache entries.

    Prior-year pages (MLB Pipeline 2024 Top 100, FG 2024report) carry
    historical data that doesn't change → keep their disk-cache fresh
    for 30 days (basically permanent within a run).

    Current-year pages (MLB Pipeline 2026 Top 100, FG 2026updated)
    actively re-publish mid-season — the user wants the most-recent
    grades surfaced every run. 24h TTL means a daily run always
    refreshes; a same-day re-run reuses cache.

    Falls back to current-year TTL (24h) when the cache_key doesn't
    encode a year token — safer to over-refresh than to serve stale.
    """
    import re as _re_local
    from datetime import date as _date_local
    # The live MLB Pipeline draft board (mlb.com/milb/prospects/draft) re-ranks
    # semi-regularly through the spring, so always re-scrape the CURRENT draft
    # year — every run_monthly surfaces the latest board. Prior-year draft
    # boards are historical and stay on the long cache.
    if cache_key.startswith("mlb_pipeline_draft_"):
        m_dr = _re_local.search(r"(20\d{2})", cache_key)
        if m_dr and int(m_dr.group(1)) >= _date_local.today().year:
            return 0
    m = _re_local.search(r"(20\d{2})", cache_key)
    if m:
        try:
            yr = int(m.group(1))
            return _SCRAPER_CURRENT_YEAR_TTL_SECONDS if yr >= _date_local.today().year \
                   else _SCRAPER_PRIOR_YEAR_TTL_SECONDS
        except ValueError:
            pass
    return _SCRAPER_CURRENT_YEAR_TTL_SECONDS


def _fetch(url: str, cache_key: str, force: bool = False,
           accept_json: bool = False) -> FetchResult:
    """Fetch a URL with on-disk caching and rate limiting."""
    cache_path = CACHE_DIR / f"{cache_key}.{'json' if accept_json else 'html'}"
    if cache_path.exists() and not force:
        # v23 — Year-aware TTL gate. Prior to v23 these caches were
        # infinite-lived, so mid-season FV / scout updates would sit
        # in the disk cache forever and never re-fetch. Now a stale
        # cache (older than TTL for its year) falls through to a
        # network refetch.
        age_seconds = time.time() - cache_path.stat().st_mtime
        ttl = _cache_ttl_for_key(cache_key)
        if age_seconds <= ttl:
            body = cache_path.read_text(encoding="utf-8")
            log.info("cache hit: %s (%d bytes, age %.0fh, ttl %.0fh)",
                     cache_key, len(body), age_seconds / 3600, ttl / 3600)
            return FetchResult(body=body, status=200, from_cache=True, url=url)
        log.info("cache stale: %s (age %.0fh > ttl %.0fh) — refetching",
                 cache_key, age_seconds / 3600, ttl / 3600)

    log.info("fetching: %s", url)
    time.sleep(RATE_LIMIT_SECONDS)
    headers = dict(HEADERS)
    if accept_json:
        headers["Accept"] = "application/json"
    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as e:
        log.error("network error fetching %s: %s", url, e)
        return FetchResult(body="", status=0, from_cache=False, url=url)

    if resp.status_code != 200:
        log.warning("non-200 from %s: HTTP %d (%d bytes)",
                    url, resp.status_code, len(resp.text))
        return FetchResult(body=resp.text, status=resp.status_code,
                          from_cache=False, url=url)

    cache_path.write_text(resp.text, encoding="utf-8")
    return FetchResult(body=resp.text, status=200, from_cache=False, url=url)


# ===========================================================================
# Rolling-page capture discipline (content-hash gate)
# ===========================================================================
# WHY THIS EXISTS
# ---------------
# Several sources publish a ROLLING permalink: one URL whose content the
# outlet silently rewrites in place (Just Baseball's /prospects/top-100-mlb-
# prospects/, MLB Pipeline's /milb/prospects/international/). Two failure
# modes come out of pinning such a page to a FIXED interval_label:
#
#   1. `insert_snapshots` upserts on (source, interval_label, player_key),
#      so a rewritten page OVERWRITES the rank/fv of every player that
#      survives from the previous edition while INSERTING the newcomers.
#      The stored interval becomes a chimera of two boards carrying the
#      OLD date: measured 2026-07-31, 'JB 2026 Preseason' held 126 rows
#      with 26 duplicate ranks (two #1s: Konnor Griffin FV70 from the real
#      March list beside Jesus Made FV60 from the June rewrite).
#   2. Stamping snapshot_date with date.today() on a fixed label re-dates
#      the WHOLE interval on every run (the upsert sets snapshot_date =
#      excluded.snapshot_date), which erases point-in-time history, fakes
#      permanent freshness, and silently migrates rows across the
#      per-(source, role, YEAR) cycles grade_normalization keys on
#      substr(snapshot_date,1,4).
#
# THE DISCIPLINE
# --------------
#   * date-stamp the label (the tjstats.scrape_live_board pattern) so each
#     genuinely-new edition lands in its own point-in-time interval, OR
#     hold the stored date stable when the board has not moved;
#   * gate the write on a CONTENT FINGERPRINT so an unchanged page writes
#     nothing at all, instead of minting a new interval every single run.
#
# The fingerprint is derived from the STORED rows, so it needs no extra
# table and is identical on the deploy box (single writer, same DB).

def board_fingerprint(rows: Iterable) -> str:
    """Stable content hash of a parsed board.

    Keyed on (player_key, rank, fv) only: those are the fields the board
    IS. Writeups and tool grids are deliberately excluded because outlets
    routinely re-edit prose without re-ranking anyone, and a prose-only
    diff must not mint a new point-in-time interval."""
    import hashlib
    parts = sorted(
        f"{getattr(r, 'player_key', '')}|{getattr(r, 'rank', None)}|"
        f"{getattr(r, 'fv', None)}"
        for r in rows
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def stored_board_fingerprint(source: str, interval_label: str) -> tuple[str | None, str | None]:
    """(fingerprint, snapshot_date) of a stored interval, or (None, None).

    Read-only; any DB problem degrades to (None, None) so a scraper still
    runs on a machine with no database."""
    try:
        from storage import connect
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, rank, fv, snapshot_date FROM snapshots "
                "WHERE source = ? AND interval_label = ?",
                (source, interval_label)).fetchall()
    except Exception:                                    # noqa: BLE001
        return None, None
    if not rows:
        return None, None
    import hashlib
    parts = sorted(f"{r[0]}|{r[1]}|{r[2]}" for r in rows)
    fp = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return fp, rows[0][3]


def latest_stored_board(source: str) -> tuple[str | None, str | None, str | None]:
    """(interval_label, snapshot_date, fingerprint) of a source's most
    recently dated stored interval, or (None, None, None).

    This is what the rolling-page gate compares against: "is the page I
    just parsed the same board I already have on file?" Comparing against
    the NEWEST interval (not a fixed label) is what lets the gate stay
    correct after a repair script re-labels or splits an old interval."""
    try:
        from storage import connect
        with connect() as con:
            row = con.execute(
                "SELECT interval_label, snapshot_date FROM snapshots "
                "WHERE source = ? ORDER BY snapshot_date DESC, interval_label DESC "
                "LIMIT 1", (source,)).fetchone()
    except Exception:                                    # noqa: BLE001
        return None, None, None
    if not row:
        return None, None, None
    label, snap_date = row[0], row[1]
    fp, _ = stored_board_fingerprint(source, label)
    return label, snap_date, fp


# ===========================================================================
# Tier B — Best-effort HTML scraping
# ===========================================================================
# These parsers attempt multiple selector strategies and log what they
# find. They WILL break when sites redesign — that's expected. The runtime
# logging tells you what failed so you can fix the selector.
# ===========================================================================



# --- ESPN (Kiley McDaniel Top 100) ----------------------------------------
# ESPN's preseason/midseason Top 100 article is server-rendered HTML with a
# clean structure: every prospect lives in an <h2> with the literal pattern
# "RANK. NAME, POS, TEAM". FV grades appear as their own <h2> tier headers
# ("65 FV tier", "60 FV tier", etc.) that introduce a block of ranks.
#
# This is McDaniel's flagship list and arguably the single highest-signal
# source we ingest — his FV grades are the explicit anchor for several
# competing sources, so getting him scraped (not just CSV-imported) is a
# meaningful upgrade. The article's content_tier meta tag reads "free",
# so no ESPN+ login is required.
#
# Failure mode: ESPN's bot filter rejects generic user-agents. The default
# project UA gets a CloudFront challenge; using a real-browser UA returns
# the same HTML a logged-out reader would see.

ESPN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}

ESPN_INTERVALS = [
    ("https://www.espn.com/mlb/story/_/id/47684202/top-100-mlb-prospects-2026-"
     "kiley-mcdaniel-konnor-griffin-kevin-mcgonigle-jesus-made",
     "ESPN 2026 Preseason", "2026-01-27"),
    # Kiley McDaniel's mid-season 2025 update. Same HTML shape as the
    # preseason article (h2 FV-tier headers + numbered rank/name/pos/team
    # lines) so the existing parser handles it without changes — the URL
    # just gets added to the list of intervals we walk.
    ("https://www.espn.com/mlb/story/_/id/46017620/2025-mlb-prospect-rankings-update-"
     "kiley-mcdaniel-konnor-griffin-kevin-mcgonigle-jesus-made",
     "ESPN 2025 In-Season", "2025-08-20"),
    # 2026 in-season top-50 update. Shorter ranking pool (1-50 instead
    # of 1-100) but the parser's rank gate (`1 <= rank <= 100`) passes
    # all rank-50 entries unchanged. Writeup extraction + tool parsing
    # work identically.
    ("https://www.espn.com/mlb/story/_/id/48825315/top-50-2026-mlb-prospects-rankings-update-"
     "jesus-made-leo-de-vries-colt-emerson",
     "ESPN 2026 In-Season", "2026-05-22"),
]

# ESPN publishes each McDaniel prospect list as a NEW dated article at a new
# numeric id, with no index page and no feed we can subscribe an ingest to.
# So ESPN_INTERVALS above needs a code edit per list, and until someone makes
# that edit the new list is silently missed - which reads exactly like a
# healthy source (the old URLs keep parsing fine).
#
# This probe closes the SILENCE, not the ingest. It never adds a URL and never
# writes a snapshot: article ids are not stable identifiers of editorial
# intent (ESPN ships prospect-adjacent features constantly), so auto-ingesting
# whatever the news feed surfaces would be a data-integrity hazard. It logs a
# prompt and lands in data/ingest_health.json for a human to action.
ESPN_NEWS_FEED = ("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/"
                  "news?limit=50")
# Headline must look like a RANKING publication, not a mailbag or a prospect
# feature. Both halves must hit.
_ESPN_RANKING_HEADLINE = re.compile(
    r"(top[\s\-]?\d{2,3}|rankings?|prospect\s+rankings)", re.I)
_ESPN_PROSPECT_HEADLINE = re.compile(r"prospect", re.I)
_ESPN_ARTICLE_ID_RE = re.compile(r"/id/(\d+)/")


def known_espn_article_ids() -> set[str]:
    """Numeric article ids already wired into ESPN_INTERVALS."""
    out: set[str] = set()
    for url, _label, _snap in ESPN_INTERVALS:
        m = _ESPN_ARTICLE_ID_RE.search(url)
        if m:
            out.add(m.group(1))
    return out


def probe_espn_new_prospect_article(force: bool = False) -> dict:
    """Detect a McDaniel prospect-ranking article we have NOT wired up.

    Returns {"candidates": [{id, headline, url, published}], "checked": n}.
    Never raises, never ingests, never edits ESPN_INTERVALS. An empty
    candidate list means "nothing new that looks like a ranking list"."""
    known = known_espn_article_ids()
    try:
        fr = _fetch(ESPN_NEWS_FEED, "espn_news_feed", force=force, accept_json=True)
        if fr.status != 200 or not fr.body:
            return {"error": f"HTTP {fr.status}", "candidates": [], "checked": 0}
        payload = json.loads(fr.body)
    except Exception as e:                                    # noqa: BLE001
        return {"error": str(e), "candidates": [], "checked": 0}

    articles = payload.get("articles") or []
    candidates: list[dict] = []
    for a in articles:
        headline = str(a.get("headline") or a.get("title") or "")
        if not (_ESPN_PROSPECT_HEADLINE.search(headline)
                and _ESPN_RANKING_HEADLINE.search(headline)):
            continue
        links = a.get("links") or {}
        url = ((links.get("web") or {}).get("href")
               or (links.get("api") or {}).get("news", {}).get("href") or "")
        aid = str(a.get("id") or "")
        if not aid:
            m = _ESPN_ARTICLE_ID_RE.search(url)
            aid = m.group(1) if m else ""
        if not aid or aid in known:
            continue
        candidates.append({"id": aid, "headline": headline,
                           "url": url.split("?")[0],
                           "published": a.get("published")})
    if candidates:
        log.warning("ESPN: %d prospect-ranking article(s) on the news feed are "
                    "NOT in ESPN_INTERVALS. Add the URL + label + publish date "
                    "to scrapers.ESPN_INTERVALS to ingest:", len(candidates))
        for c in candidates:
            log.warning("  ESPN candidate id=%s %r %s", c["id"], c["headline"],
                        c["url"])
    else:
        log.info("ESPN: news feed carries no unwired prospect-ranking article "
                 "(%d headlines checked)", len(articles))
    return {"candidates": candidates, "checked": len(articles)}

# Stripper for the structured preamble ESPN ships before the writeup
# prose. Each prospect's article block looks like:
#   1. Konnor Griffin, SS, Pittsburgh Pirates
#   Age: 19 | Bats: Right | Throws: Right
#   Hit: 45/50 Game Power: 50/65 Raw Power: 60/70 Speed: 70/70 ...
#   Reminds me of: <comp> | Type: <tier> | <prose paragraph>
# After HTML strip + whitespace collapse, all of that becomes one long
# space-separated line. _parse_espn_tools already ingested every "Label:
# 45/50" pair; the report panel only needs the narrative. We strip the
# rank line + Age/Bats/Throws + tool-grade pairs in order. "Reminds me
# of:" and "Type:" carry meaningful prose (comp + tier) so they stay.
_ESPN_BIO_HEADER = re.compile(
    r"^\s*(?:Age|Bats|Throws)\s*:\s*\S+\s*\|?\s*", re.IGNORECASE
)
_ESPN_TOOL_LABEL = re.compile(
    r"^\s*(?:Hit|Game\s+Power|Raw\s+Power|Power|Speed|Run|Fielding|"
    r"Field|Throwing|Arm|Fastball|Curveball|Slider|Changeup|Splitter|"
    r"Sweeper|Cutter|Sinker|Command|Control)\s*:\s*\d+(?:\s*/\s*\d+)?\s*\|?\s*",
    re.IGNORECASE,
)


def scrape_espn_top100(url: str, label: str, snap_date: str,
                       force: bool = False) -> list[Snapshot]:
    """
    Parse one ESPN Top 100 article and return Snapshot rows.

    Algorithm:
      1. Walk the article body's <h2> tags in document order.
      2. "<N> FV tier" headers reset `current_fv` for the block below.
      3. "<rank>. <name>, <pos>, <full team>" headers emit a Snapshot,
         tagged with the most recent FV tier.

    Cleaning:
      - Org names are canonicalized via trades.canonical_org so "Pittsburgh
        Pirates" → "PIT", matching the rest of the pipeline.
      - Position is preserved as the raw label ("SS", "RHP", "CF", etc.)
        because age-vs-level scoring keys on these.
      - Names are passed through fix_mojibake so accented characters survive
        the cached HTML round-trip.
    """
    from trades import canonical_org

    if date.fromisoformat(snap_date) > date.today():
        return []
    cache_key = "espn_" + re.sub(r"[^a-z0-9]+", "_", label.lower())
    cache_path = CACHE_DIR / f"{cache_key}.html"

    # Custom-UA fetch — _fetch() uses the project UA which CloudFront
    # rejects for ESPN. Inline the cache-aware path here rather than
    # complicate _fetch's signature. v23 — year-aware TTL gate.
    fr = None
    if cache_path.exists() and not force:
        age_seconds = time.time() - cache_path.stat().st_mtime
        ttl = _cache_ttl_for_key(cache_key)
        if age_seconds <= ttl:
            body = cache_path.read_text(encoding="utf-8")
            log.info("cache hit: %s (%d bytes, age %.0fh, ttl %.0fh)",
                     cache_key, len(body), age_seconds / 3600, ttl / 3600)
            fr = FetchResult(body=body, status=200, from_cache=True, url=url)
        else:
            log.info("cache stale: %s (age %.0fh > ttl %.0fh) — refetching",
                     cache_key, age_seconds / 3600, ttl / 3600)
    if fr is None:
        log.info("fetching: %s", url)
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, headers=ESPN_HEADERS, timeout=30)
        except requests.RequestException as e:
            log.error("network error fetching %s: %s", url, e)
            return []
        if resp.status_code != 200:
            log.warning("espn %s: HTTP %d (%d bytes)",
                        label, resp.status_code, len(resp.text))
            return []
        cache_path.write_text(resp.text, encoding="utf-8")
        fr = FetchResult(body=resp.text, status=200, from_cache=False, url=url)

    body = fr.body
    # Restrict to the article body so we skip page-header h2s ("Editor's
    # Picks") and sidebar marketing blocks.
    start = body.find('class="article-body"')
    if start < 0:
        log.warning("espn %s: article-body div not found", label)
        return []
    body = body[start:]

    # ESPN ships three layouts across these articles:
    #   * Preseason — every block is an <h2>, including FV-tier headers
    #     and the rank lines themselves. The original scraper assumed
    #     this shape.
    #   * In-season updates, top-of-list — FV-tier headers are still
    #     <h2> (often wrapped in <strong>), but the rank lines for the
    #     headline tier move into <p><strong>...</strong></p>
    #     paragraphs followed by a few description paragraphs.
    #   * In-season updates, lower tiers — multiple rank lines packed
    #     into a single <p>, separated by <br/>. No <strong> wrapper,
    #     no per-prospect commentary.
    #
    # We collect (offset, text) candidates from every shape, then sort
    # by offset so an FV-tier header always resets the running tier
    # before the rank lines below it land.
    candidates: list[tuple[int, str]] = []
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", body, re.DOTALL):
        candidates.append((m.start(), m.group(1)))
    # <p><strong>…</strong>… — first-child <strong> means we don't
    # accidentally pick up inline-bolded phrases inside body paragraphs.
    for m in re.finditer(
        r"<p[^>]*>\s*(?:<[^>]+>\s*){0,2}<strong>(.*?)</strong>",
        body, re.DOTALL,
    ):
        candidates.append((m.start(), m.group(1)))
    # <p>…<br/>…<br/>…</p> — each line between <br/> tags is a
    # candidate. Used by the 55/50 FV tier "list" sections in the
    # in-season updates. We grab the paragraph body, split on <br/>,
    # and emit one candidate per fragment so the rank-line regex picks
    # up "14. JJ Wetherholt, SS, St. Louis Cardinals" cleanly. Lazy
    # `.*?` matches nested anchors/spans without over-running the
    # paragraph boundary.
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", body, re.DOTALL):
        pblock = m.group(1)
        if "<br" not in pblock:
            continue
        # Split on <br/> variants. Each fragment is a candidate; the
        # offset is the paragraph's start (we lose the within-block
        # position but tier headers always precede the paragraph).
        for frag in re.split(r"<br\s*/?>", pblock):
            candidates.append((m.start(), frag))
    candidates.sort(key=lambda c: c[0])

    fv_header = re.compile(r"^\s*(\d{2,3})\+?\s*FV\s*tier", re.IGNORECASE)
    rank_line = re.compile(
        r"^\s*(\d{1,3})\.\s+([^,]+?),\s*([^,]+?),\s*(.+?)\s*$"
    )

    # First pass: identify which candidates are rank lines, so the
    # commentary slice can use ONLY rank-line offsets as boundaries
    # (inline-bolded fragments inside body paragraphs were truncating
    # commentary to a few chars, starving the prose parser).
    rank_offsets: list[int] = []
    for (off, h) in candidates:
        text = re.sub(r"<[^>]+>", "", h)
        text = fix_mojibake(text)
        if rank_line.match(text):
            rank_offsets.append(off)
    rank_offsets.append(len(body))  # sentinel for the last player

    rows: list[Snapshot] = []
    current_fv: float | None = None
    seen_ranks: set[int] = set()

    for i, (off, h) in enumerate(candidates):
        text = re.sub(r"<[^>]+>", "", h)
        text = fix_mojibake(text)
        if not text:
            continue
        fm = fv_header.match(text)
        if fm:
            current_fv = float(fm.group(1))
            continue
        rm = rank_line.match(text)
        if not rm:
            continue
        rank = int(rm.group(1))
        if not (1 <= rank <= 100) or rank in seen_ranks:
            continue
        seen_ranks.add(rank)
        name = rm.group(2).strip()
        pos  = rm.group(3).strip() or None
        team = rm.group(4).strip()
        org  = canonical_org(team) or team
        # Tool-grade capture: the article body between this rank line's
        # offset and the NEXT RANK LINE's offset is the player's full
        # commentary block. ESPN's preseason format used to ship tool
        # lines ("Hit: 45/50") inside; 2025+ articles ship descriptive
        # prose ("plus runner", "94-98 mph fastball"). _parse_espn_tools
        # handles structured lines and falls through to the prose parser
        # when none are present.
        try:
            next_off = rank_offsets[rank_offsets.index(off) + 1]
        except (ValueError, IndexError):
            next_off = len(body)
        commentary = body[off:next_off]
        # Decode common HTML entities so "&amp;" doesn't break label matches.
        commentary = html.unescape(re.sub(r"<[^>]+>", " ", commentary))
        commentary = fix_mojibake(commentary)
        tools = _parse_espn_tools(commentary)
        # Writeup cleanup:
        #   1. Find the literal "rank. name, pos, team" string and slice
        #      past it. Using the already-parsed fields makes this
        #      tolerant of the multi-word team names ("Pittsburgh
        #      Pirates", "St. Louis Cardinals") that broke earlier
        #      regex-only attempts.
        #   2. Chip off leading Age/Bats/Throws + tool-grade pairs.
        #      _parse_espn_tools already captured those; the report only
        #      wants the narrative.
        #   3. Collapse the runs of whitespace tag-stripping left behind.
        prose = re.sub(r"\s+", " ", commentary).strip()
        rank_prefix = f"{rank}. {name}, {pos}, {team}" if pos else f"{rank}. {name}, {team}"
        idx = prose.find(rank_prefix)
        if idx >= 0:
            prose = prose[idx + len(rank_prefix):]
        # Loop the front-strippers — each .sub() peels off at most one
        # leading label/pair, so iterate until a pass produces no change.
        while True:
            stripped = _ESPN_BIO_HEADER.sub("", prose, count=1)
            stripped = _ESPN_TOOL_LABEL.sub("", stripped, count=1)
            if stripped == prose:
                break
            prose = stripped
        prose = re.sub(r"\s+", " ", prose).strip()
        if prose and len(prose) > 60:
            tools = tools or {}
            cleaned = _clean_report_prose(prose)
            if cleaned:
                tools.setdefault("_extras", {})["report"] = cleaned[:8000]
        rows.append(Snapshot(
            source="espn", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=pos, org=org, rank=rank, fv=current_fv,
            status="active", tools=tools,
        ))

    log.info("espn %s -> %d players%s", label, len(rows),
             "" if rows else " (parser returned 0 rows — page structure may have changed; check cached HTML)")
    return rows


# --- Just Baseball --------------------------------------------------------
# JB renders prospects as <h2> or <h3> blocks. Each starts with "<rank>. <Name>"
# and the FV grade appears in the following paragraph as "Future Value: 55".
# Per-player tool grades live in a <figure class="wp-block-table"> table
# immediately after the heading. Header row carries column labels (variable
# per pitcher — Sweeper vs Slider, Splitter vs Changeup), value row carries
# present/future grade pairs. We always take the FUTURE grade.

# The Just Baseball board lives on ONE rolling permalink that JB rewrites in
# place (preseason -> midseason -> ...). It is NOT a dated archive URL.
JB_ROLLING_URL = "https://www.justbaseball.com/prospects/top-100-mlb-prospects/"
JB_SOURCE = "just_baseball"
JB_LIVE_LABEL_PREFIX = "JB Live"          # -> "JB Live 2026-07-31"

# FIXED-DATE ARCHIVE INTERVALS ONLY. Deliberately EMPTY.
#
# This list used to pin the rolling permalink above to the fixed label
# 'JB 2026 Preseason' at the fixed date 2026-03-04. JB then rewrote the page
# to its midseason board, and because insert_snapshots upserts on
# (source, interval_label, player_key) the stored March interval absorbed the
# June board: 126 rows, 26 DUPLICATE ranks, still dated 2026-03-04, with
# Jesus Made (FV 60, June #1) sitting on rank 1 next to Konnor Griffin
# (FV 70, the real March #1). Every subsequent JB edition would smear it
# further. See run_just_baseball_live() for the replacement path and
# tools/repair_jb_chimera.py for the repair of what is already stored.
#
# Add an entry here ONLY for a URL that is a permanent dated archive (one
# that JB will never rewrite). scrape_all still walks this list, so such an
# entry keeps working with no other change.
JB_INTERVALS: list[tuple[str, str, str]] = []

# JB column header → canonical tool key. Lowercased headers — Splitter
# rides the ch slot, Sweeper rides the sl slot (variants of those pitch
# families). Cutter gets its own canonical key (PITCHER_TOOL_KEYS extended).
JB_TOOL_KEY: dict[str, str] = {
    # hitters
    "hit":               "hit",
    "plate disc":        "pitch_sel",
    "plate disc.":       "pitch_sel",
    "plate discipline":  "pitch_sel",
    "bat ctrl":          "bat_ctrl",
    "bat control":       "bat_ctrl",
    "game power":        "game_pwr",
    "raw power":         "raw_pwr",
    "power":             "game_pwr",
    "run":               "speed",
    "speed":             "speed",
    "field":             "field",
    "fielding":          "field",
    "arm":               "throw",
    "throwing":          "throw",
    # pitchers
    "fastball":          "fb",
    "fb":                "fb",
    "slider":            "sl",
    "sweeper":           "sl",       # sweeper = slider variant
    "curveball":         "cb",
    "curve":             "cb",
    "changeup":          "ch",
    "splitter":          "ch",       # splitter rides the changeup slot
    "cutter":            "ct",
    "command":           "cmd",
    "control":           "cmd",
}


def _parse_jb_tool_table(table_html) -> tuple[dict[str, float] | None, float | None, bool]:
    """Parse one JB wp-block-table into (tools_dict, fv, fv_plus).

    Header row → labels (lowercased, stripped). Value row → "pres/fut"
    grade pairs (or singletons). For each (header, value) pair we map
    header to canonical key via JB_TOOL_KEY and keep the future grade
    if it parses to a valid 20-80 number. The FV column is returned
    separately along with an upside flag (True when source wrote "55+").
    """
    if table_html is None:
        return None, None, False
    if isinstance(table_html, str):
        sub = BeautifulSoup(table_html, "html.parser")
        table = sub.find("table")
    else:
        table = table_html if getattr(table_html, "name", None) == "table" else table_html.find("table")
    if not table:
        return None, None, False
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None, None, False
    headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    values = [c.get_text(" ", strip=True) for c in rows[1].find_all(["td", "th"])]
    if not headers or len(values) < len(headers):
        return None, None, False
    tools: dict[str, float] = {}
    fv: float | None = None
    fv_plus = False
    for hdr, raw in zip(headers, values):
        hdr_norm = hdr.strip().rstrip(".").rstrip()
        if hdr_norm in ("fv", "f.v.", "future value"):
            fv, fv_plus = _parse_fv_full(raw)
            continue
        key = JB_TOOL_KEY.get(hdr_norm) or JB_TOOL_KEY.get(hdr.strip())
        if not key:
            continue
        # "55/60" → take the right side; "60" → take as-is.
        m = re.search(r"(\d{1,2})(?:\s*/\s*(\d{1,2}))?", raw)
        if not m:
            continue
        fut = m.group(2) or m.group(1)
        try:
            grade = float(fut)
        except (TypeError, ValueError):
            continue
        if grade < 20 or grade > 80:
            continue
        tools[key] = grade
    return (tools or None), fv, fv_plus


# Heading format example: "1. Konnor Griffin – SS – Pittsburgh Pirates"
# Dash variants: en-dash (–), em-dash (—), or regular hyphen-minus (-).
_JB_HEADING_RE = re.compile(
    r"^(\d{1,3})\.\s+(.+?)\s+[–—\-]\s+([\w/,\.]+)\s+[–—\-]\s+(.+?)\s*$"
)


def scrape_just_baseball(url: str, label: str, snap_date: str,
                         force: bool = False) -> list[Snapshot]:
    from trades import canonical_org

    if date.fromisoformat(snap_date) > date.today():
        return []
    cache_key = "jb_" + re.sub(r"[^a-z0-9]+", "_", label.lower())
    fr = _fetch(url, cache_key, force=force)
    if fr.status != 200:
        log.error("just_baseball %s: HTTP %d", label, fr.status)
        return []
    soup = BeautifulSoup(fr.body, "html.parser")

    rows: list[Snapshot] = []
    seen_names: set[str] = set()
    n_with_tools = 0
    # Each prospect lives in <section class="toc-list__entry">. The
    # section contains exactly one heading and one wp-block-table tools
    # grid — much more reliable than chasing siblings across the
    # article's flat content.
    for section in soup.find_all("section", class_="toc-list__entry"):
        hdr = section.find(["h1", "h2", "h3", "h4"])
        if not hdr:
            continue
        text = hdr.get_text(" ", strip=True)
        m = _JB_HEADING_RE.match(text)
        if not m:
            # Fall back to the older "100. Player Name" pattern so we
            # don't drop prospects when the dashed format isn't present.
            simple = re.match(r"^(\d{1,3})\.\s+([A-Z][\w'\-]+(?:\s+[A-Z][\w'\-\.]+)+)", text)
            if not simple:
                continue
            rank = int(simple.group(1))
            name = simple.group(2).strip()
            position = None
            org_full = None
        else:
            rank = int(m.group(1))
            name = m.group(2).strip()
            position = m.group(3).strip().split(",")[0]  # take primary position
            org_full = m.group(4).strip()
        if not (1 <= rank <= 200) or name in seen_names:
            continue
        seen_names.add(name)
        org = canonical_org(org_full) if org_full else None
        # Tools + FV from the section's table.
        tools = None
        fv = None
        fv_plus = False
        table = section.find("table")
        if table:
            tools, fv, fv_plus = _parse_jb_tool_table(table)
        # FV fallback — prose-style "Future Value: 55" if it ever returns.
        if fv is None:
            sect_text = section.get_text(" ", strip=True)
            fv_m = re.search(r"(?:Future Value|F\.V\.)[:\s]+([0-9]+\+?)", sect_text)
            if fv_m:
                fv, fv_plus = _parse_fv_full(fv_m.group(1))
        if tools:
            n_with_tools += 1
        # Writeup — grab paragraph children only so we skip the heading
        # (rank/name/pos already captured) and the wp-block-table (tool
        # grades already captured). Paragraph breaks preserved with \n\n
        # so the frontend can split-on-blank-lines if needed. Mojibake
        # fix runs per paragraph so its whitespace normalization can't
        # collapse the paragraph separators.
        paragraphs = [
            fix_mojibake(par.get_text(" ", strip=True))
            for par in section.find_all("p")
            if par.get_text(strip=True)
        ]
        prose = "\n\n".join(p for p in paragraphs if p).strip()
        if prose and len(prose) > 60:
            tools = tools or {}
            cleaned = _clean_report_prose(prose)
            if cleaned:
                tools.setdefault("_extras", {})["report"] = cleaned[:8000]
        rows.append(Snapshot(
            source="just_baseball", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=position, org=org, rank=rank, fv=fv, status="active",
            tools=tools, fv_plus=fv_plus,
        ))
    log.info("just_baseball %s -> %d players (%d with tools)%s", label, len(rows), n_with_tools,
             "" if rows else " (parser returned 0 rows — page structure may have changed; check cached HTML)")
    return rows


def validate_jb_board(rows: list[Snapshot]) -> list[str]:
    """Health gate for the JB rolling capture (the tjstats.health_check /
    validate_pipeline_live_board pattern). Refuse to ingest a degraded parse
    so a silent JB redesign surfaces loudly instead of minting a half-empty
    point-in-time interval. Returns human-readable problems (empty = healthy).

    The duplicate-rank check is the specific tripwire that would have caught
    the 2026 chimera on the very first bad run."""
    problems: list[str] = []
    if len(rows) < 90:
        problems.append(f"jb: only {len(rows)} parsed rows (expected ~100)")
        return problems
    ranks = [s.rank for s in rows if s.rank is not None]
    if len(set(ranks)) != len(ranks):
        dupes = sorted({r for r in ranks if ranks.count(r) > 1})
        problems.append(f"jb: duplicate ranks {dupes[:10]}")
    if not ranks or min(ranks) != 1 or max(ranks) > 110:
        problems.append(f"jb: rank span {min(ranks) if ranks else '-'}"
                        f"..{max(ranks) if ranks else '-'}")
    fv_cov = sum(1 for s in rows if s.fv is not None) / len(rows)
    if fv_cov < 0.8:
        problems.append(f"jb: FV coverage {fv_cov:.0%} (<80%, the wp-block-table "
                        "grid may have moved)")
    return problems


def run_just_baseball_live(snap_date: str | None = None,
                           force: bool = False) -> dict:
    """Capture the Just Baseball rolling board CORRECTLY (defect fix, 2026-07-31).

    Three rules, each of which the old fixed-label path broke:

      1. DATE-STAMP THE LABEL. Every genuinely-new edition lands in its own
         interval "JB Live <capture date>", so a rewrite can never overwrite
         the previous board's ranks. Same-day re-runs upsert in place.
      2. CONTENT-HASH GATE. JB's permalink serves the same board for months.
         Without a gate, date-stamping alone would mint a fresh 100-row
         interval EVERY run and flood the consensus with duplicate editions.
         We fingerprint (player_key, rank, fv) and write nothing when it
         matches the newest stored JB board.
      3. HEALTH GATE. A degraded parse is never written (validate_jb_board).

    Returns {"live": {...}} on ingest, {"unchanged": {...}} when the board
    has not moved, {"health": [problems]} when the gate refuses,
    {"error": "..."} on fetch/parse failure. Never raises."""
    from storage import insert_snapshots

    snap_date = snap_date or date.today().isoformat()
    label = f"{JB_LIVE_LABEL_PREFIX} {snap_date}"
    try:
        rows = scrape_just_baseball(JB_ROLLING_URL, label, snap_date, force=force)
    except Exception as e:                                    # noqa: BLE001
        return {"error": f"fetch/parse failed: {e}"}
    if not rows:
        return {"error": "parser returned 0 rows (page structure may have changed)"}
    problems = validate_jb_board(rows)
    if problems:
        return {"health": problems}

    fp = board_fingerprint(rows)
    prev_label, prev_date, prev_fp = latest_stored_board(JB_SOURCE)
    # Also compare against THIS label directly, so a same-day re-run after a
    # repair (which may have left a newer-dated interval on file) is still a
    # no-op rather than a rewrite.
    same_label_fp, _ = stored_board_fingerprint(JB_SOURCE, label)
    if fp in (prev_fp, same_label_fp) and (prev_fp or same_label_fp):
        log.info("just_baseball: board unchanged vs %s (%s) - no write",
                 prev_label, prev_date)
        return {"unchanged": {"n_players": len(rows), "matched_label": prev_label,
                              "matched_date": prev_date, "fingerprint": fp}}

    n = insert_snapshots(rows)
    log.info("just_baseball live: %d players ingested @ %s as %r (board CHANGED "
             "vs %s)", len(rows), snap_date, label, prev_label or "nothing on file")
    return {"live": {"n_players": len(rows), "n_upserts": n, "label": label,
                     "captured_at": snap_date, "fingerprint": fp,
                     "prev_label": prev_label}}


# FanGraphs org-list tool-label → canonical key. The org Top-N articles render
# each prospect as a TheBoard "tool-item" card with a present/future grade
# table; map FG's full-word labels onto the same canonical keys every other
# source uses so the grades aggregate cross-source. Velocity ("Sits/Tops") and
# bio fields are NOT 20-80 tool grades and are skipped.
FG_TOOL_KEY = {
    "hit": "hit",
    "game power": "game_pwr", "power": "game_pwr",
    "raw power": "raw_pwr",
    "run": "speed", "speed": "speed",
    "fielding": "field", "field": "field",
    "throw": "throw", "throws": "throw", "arm": "throw",
    "pitch selection": "pitch_sel", "selection": "pitch_sel",
    "bat control": "bat_ctrl",
    "fastball": "fb", "sinker": "fb",
    "slider": "sl",
    "curveball": "cb", "curve": "cb",
    "changeup": "ch", "change": "ch",
    "cutter": "ct",
    "command": "cmd", "control": "cmd",
}

# Heading inside each .tool-item: "1. Konnor Griffin , SS".
_FG_HEAD_RE = re.compile(r"^\s*(\d{1,3})\.\s+(.+?)\s*,\s*([A-Za-z0-9/]+)\s*$")
# FV-tier section header: "70 FV Prospects" / "45+ FV Prospects".
_FG_TIER_RE = re.compile(r"^\s*(\d{2})(\+)?\s*FV\b", re.I)


def _parse_fg_tool_table(table) -> dict[str, float] | None:
    """Parse a FanGraphs 2-row tool table (header-label row + present/future
    value row, e.g. 'Hit' → '40/60'). Returns canonical-keyed FUTURE grades,
    range-validated via sanitize_fv. Bio/velocity columns are skipped."""
    trs = table.find_all("tr")
    if len(trs) < 2:
        return None
    headers = [c.get_text(" ", strip=True).lower() for c in trs[0].find_all(["td", "th"])]
    values = [c.get_text(" ", strip=True) for c in trs[1].find_all(["td", "th"])]
    if not headers or not values:
        return None
    tools: dict[str, float] = {}
    for hdr, raw in zip(headers, values):
        key = FG_TOOL_KEY.get(hdr.strip())
        if not key:
            continue
        # "40/60" → future 60; "70" → 70. Two-digit grades only (skips velo).
        m = re.search(r"(\d{2})(?:\s*/\s*(\d{2}))?", raw)
        if not m:
            continue
        try:
            grade = float(m.group(2) or m.group(1))
        except ValueError:
            continue
        if 20.0 <= grade <= 80.0:   # range-validate (drop typos/velocity), as JB tools do
            tools[key] = grade
    return tools or None


def scrape_fangraphs_org_list(url: str, label: str, snap_date: str,
                              org: str, force: bool = False) -> list[Snapshot]:
    """Scrape a FanGraphs org Top-N prospect article (TheBoard 'tool-item'
    cards): FV (bio table, falling back to the FV-tier header), present/future
    tool grades, and the prose writeup. Stored under source='fangraphs'.

    `org` is the canonical org code stamped on every prospect — org lists
    don't repeat the team per player. Mirrors scrape_just_baseball's contract.
    """
    if date.fromisoformat(snap_date) > date.today():
        return []
    cache_key = "fg_" + re.sub(r"[^a-z0-9]+", "_", label.lower())
    fr = _fetch(url, cache_key, force=force)
    if fr.status != 200:
        log.error("fangraphs %s: HTTP %d", label, fr.status)
        return []
    soup = BeautifulSoup(fr.body, "html.parser")
    rows: list[Snapshot] = []
    seen: set[str] = set()
    n_with_tools = 0
    for item in soup.select("div.tool-item"):
        hdr = item.find(["h2", "h3", "h4"])
        if not hdr:
            continue
        m = _FG_HEAD_RE.match(hdr.get_text(" ", strip=True))
        if not m:
            continue
        rank = int(m.group(1))
        name = m.group(2).strip()
        position = m.group(3).strip().split("/")[0]
        if not (1 <= rank <= 200) or name in seen:
            continue
        seen.add(name)
        # FV-tier header preceding this card → tier FV + '+' marker.
        tier_fv = None
        fv_plus = False
        for prev in hdr.find_all_previous(["h1", "h2", "h3", "h4"]):
            tm = _FG_TIER_RE.match(prev.get_text(" ", strip=True))
            if tm:
                tier_fv = float(tm.group(1))
                fv_plus = bool(tm.group(2))
                break
        # Bio table FV (preferred) + the tool-grade table(s).
        fv = None
        tools: dict | None = None
        for tbl in item.find_all("table"):
            cells = [c.get_text(" ", strip=True) for c in tbl.find_all(["td", "th"])]
            low = [c.lower() for c in cells]
            if "fv" in low:                       # bio key/value table
                i = low.index("fv")
                if i + 1 < len(cells):
                    fvv, fp = _parse_fv_full(cells[i + 1])
                    if fvv is not None:
                        fv = fvv
                    fv_plus = fv_plus or fp
                continue
            t = _parse_fg_tool_table(tbl)          # tool-grade table
            if t:
                tools = {**(tools or {}), **t}
        if fv is None and tier_fv is not None and 20.0 <= tier_fv <= 80.0:
            fv = tier_fv
        if tools:
            n_with_tools += 1
        # Writeup — prose paragraphs inside the card.
        paragraphs = [fix_mojibake(p.get_text(" ", strip=True))
                      for p in item.find_all("p") if p.get_text(strip=True)]
        prose = "\n\n".join(p for p in paragraphs if p).strip()
        if prose and len(prose) > 60:
            tools = tools or {}
            cleaned = _clean_report_prose(prose)
            if cleaned:
                tools.setdefault("_extras", {})["report"] = cleaned[:8000]
        rows.append(Snapshot(
            source="fangraphs", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=position, org=org, rank=rank, fv=fv, status="active",
            tools=tools, fv_plus=fv_plus,
        ))
    log.info("fangraphs %s -> %d players (%d with tools)%s", label, len(rows), n_with_tools,
             "" if rows else " (parser returned 0 rows — page structure may have changed)")
    return rows


# --- MLB Pipeline (mlb.com/milb/prospects/<year>/top100/) -----------------
# Each year's archived Top 100 page is server-rendered HTML with the full
# ranking embedded as an Apollo Client cache (HTML-encoded JSON inside the
# page body). Per prospect we recover rank, name, position, current MLB org,
# and the 20-80 "Overall" scouting grade — which the rest of this pipeline
# treats as FV. MLBAM person ID is also available via the player ref.
#
# Failure modes:
#   - The default project UA gets HTTP 406; a real-browser UA returns
#     the same HTML a logged-out reader would see (same workaround used
#     for ESPN above).
#   - The "current MLB org" reflects today's roster, not the player's
#     org at the time the historical list was published. Pipeline updates
#     these pages over time; treat the org as "as of scrape" rather than
#     a true season-end snapshot. The rank and FV are the historical
#     payload — those stay anchored.
#   - 2021's page returns 99 records, not 100. The original list had 100;
#     one record is simply not in the Apollo cache. Emit what's there.

MLB_PIPELINE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# (url, label, snapshot_date, year) — the year drives which prospectBio
# entry to read scout grades from (each player has multiple year-tagged bios).
MLB_PIPELINE_INTERVALS = [
    (f"https://www.mlb.com/milb/prospects/{y}/top100/",
     f"MLB Pipeline {y} Top 100",
     f"{y}-01-22",
     y)
    # 2011-2026 — mlb.com serves these year-keyed pages directly (era-correct,
    # with per-year bios carrying the point-in-time scouting grades). The
    # 2011-2016 backfill (eFV initiative, 2026-06-21) adds FULLY-RESOLVED
    # cohorts — the binding constraint for the outcome-grounded model. Coverage
    # by year: 2013-2016 full Top 100 with ~99% FV+tools; 2012 Top 100 ~73% FV
    # (rest rank-only -> rank-implied FV); 2011 is a Top 50 with ~38% FV.
    for y in range(2011, 2027)
]

# MLB Pipeline's international class page is a ROLLING permalink like JB's:
# one URL, rewritten in place, no per-year archive. snapshot_date is
# therefore resolved at SCRAPE time (None = "resolve me") instead of being
# frozen into the module constant.
#
# THE DEFECT THIS REPLACES: this entry used to carry
# `date.today().isoformat()`, and because insert_snapshots' upsert does
# `snapshot_date = excluded.snapshot_date` on a FIXED label, all 50 rows were
# re-dated on EVERY monthly run (measured 2026-07-31: all 50 sat at
# 2026-07-31). Three consequences, all silent:
#   * point-in-time history is destroyed - the interval can only ever be
#     "today", so the Time Machine has no international board before today;
#   * permanent freshness illusion - the rows look newly published every run
#     even when Pipeline has not touched the page since January;
#   * YEAR-CYCLE MIGRATION - grade_normalization builds per-(source, role,
#     year) offsets keyed on substr(snapshot_date,1,4), so on the first run
#     after New Year the whole 2026 international class would silently jump
#     into the 2027 normalization cohort and be de-biased against the wrong
#     year's grader baseline.
#
# The fallback date matches the sibling backfilled years (2021-2025 are all
# {y}-01-15, the date the international signing period opens), so a board
# with nothing on file is dated era-correctly and identically on every
# machine instead of "whenever this box happened to run".
MLB_INTERNATIONAL_FALLBACK_DATE = "{year}-01-15"
MLB_INTERNATIONAL_SOURCE = "mlb_pipeline_international"

MLB_INTERNATIONAL_INTERVALS = [
    ("https://www.mlb.com/milb/prospects/international/",
     "MLB Pipeline 2026 International",
     None,        # resolved by resolve_international_snapshot_date()
     2026)
]


def resolve_international_snapshot_date(label: str, year: int) -> str:
    """Provisional snapshot_date for the rolling international page.

    Returns the date ALREADY on file for this interval when rows exist, so a
    re-scrape cannot re-date them. The caller
    (scrape_mlb_international_stable) advances the date only after it has
    proved the parsed board differs from what is stored."""
    _fp, stored_date = stored_board_fingerprint(MLB_INTERNATIONAL_SOURCE, label)
    if stored_date:
        return stored_date
    return MLB_INTERNATIONAL_FALLBACK_DATE.format(year=year)


def scrape_mlb_international_stable(url: str, label: str, year: int,
                                    force: bool = False) -> list[Snapshot]:
    """scrape_mlb_international with the rolling-page date discipline applied.

    Parse once, fingerprint, then decide the date:
      * board matches what is stored -> keep the STORED date (no re-dating,
        no freshness illusion, no year-cycle migration);
      * board changed (or nothing on file) -> advance to today, which is a
        real publication event;
      * parse degraded (0 rows) -> emit nothing, leaving the stored board
        and its date untouched.
    """
    provisional = resolve_international_snapshot_date(label, year)
    rows = scrape_mlb_international(url, label, provisional, year, force=force)
    if not rows:
        log.error("mlb_international %s: parser returned 0 rows - leaving the "
                  "stored board untouched", label)
        return []
    stored_fp, stored_date = stored_board_fingerprint(MLB_INTERNATIONAL_SOURCE, label)
    fp = board_fingerprint(rows)
    if stored_fp is not None and fp == stored_fp:
        log.info("mlb_international %s: board unchanged, holding snapshot_date %s",
                 label, stored_date)
        return rows            # already carries `provisional` == stored_date
    new_date = date.today().isoformat() if stored_fp is not None else provisional
    if new_date != provisional:
        log.info("mlb_international %s: board CHANGED, advancing snapshot_date "
                 "%s -> %s", label, provisional, new_date)
        rows = [_dataclass_replace(r, snapshot_date=new_date) for r in rows]
    return rows


# MLB Pipeline per-org top-30 lists. Same Apollo Cache structure as the
# Top-100 page (verified empirically — URL pattern `mlb.com/prospects/
# <year>/<slug>` returns 200 with the same RankedPlayerEntity records).
# Each org publishes ~25-30 prospect bios; tools come through the same
# `Scouting grades:` line that _parse_pipeline_tools already handles.
# Coverage boost: 30 orgs × 25 prospects × 2 years ≈ 1500 additional
# Snapshot rows, most of which overlap with FG → massive lift in
# multi-source consensus opportunity.
MLB_PIPELINE_ORG_SLUGS = (
    # AL East / Central / West
    # NOTE — MLB.com's org-page slugs are NOT all hyphenated: `red-sox`,
    # `blue-jays`, `white-sox`, `diamondbacks` all 200 but return zero
    # Apollo entities (silent 404 SPA). The correct slugs for those are
    # the concatenated short forms `redsox`, `bluejays`, `whitesox`,
    # `dbacks`. Verified empirically Nov 2026 across all six year-keyed
    # /prospects/{year}/{slug} pages.
    "yankees", "redsox", "bluejays", "orioles", "rays",
    "whitesox", "guardians", "tigers", "royals", "twins",
    "astros", "athletics", "angels", "mariners", "rangers",
    # NL East / Central / West
    "braves", "marlins", "mets", "phillies", "nationals",
    "cubs", "reds", "brewers", "pirates", "cardinals",
    "dbacks", "rockies", "dodgers", "padres", "giants",
)
MLB_PIPELINE_ORG_YEARS = tuple(range(2011, 2027))

# Display labels — concatenated slugs (dbacks/redsox/bluejays/whitesox)
# need explicit pretty names so interval_label still reads "Diamondbacks"
# / "Red Sox" / etc. for downstream auditing + UI consumers.
MLB_PIPELINE_ORG_LABELS = {
    "dbacks":    "Diamondbacks",
    "redsox":    "Red Sox",
    "bluejays":  "Blue Jays",
    "whitesox":  "White Sox",
}

def _slug_to_label(slug: str) -> str:
    if slug in MLB_PIPELINE_ORG_LABELS:
        return MLB_PIPELINE_ORG_LABELS[slug]
    return slug.replace("-", " ").title()

MLB_PIPELINE_ORG_INTERVALS = [
    (f"https://www.mlb.com/prospects/{y}/{slug}",
     f"MLB Pipeline {y} {_slug_to_label(slug)} Top 30",
     f"{y}-01-22",
     y,
     f"mlb_pipeline_{y}_org_{slug.replace('-', '_')}")
    for y in MLB_PIPELINE_ORG_YEARS
    for slug in MLB_PIPELINE_ORG_SLUGS
]


def _apollo_entities(text: str, typename: str):
    """Yield (id, body_slice) for each top-level Apollo entity of typename.

    Apollo cache keys look like `"Typename:ID":{...}`. To prevent fields from
    one record bleeding into the next via a too-wide scan window, we clip each
    body at the next entity-start boundary in the document.
    """
    boundary_starts = sorted(
        m.start() for m in re.finditer(
            r'"[A-Z][A-Za-z]+:[A-Za-z0-9_\-]+":\{', text
        )
    )
    boundary_starts.append(len(text))
    target_re = re.compile(rf'"{re.escape(typename)}:(\d+)":\{{')
    for m in target_re.finditer(text):
        i = m.start()
        nxt = bisect.bisect_right(boundary_starts, i)
        j = boundary_starts[nxt] if nxt < len(boundary_starts) else len(text)
        yield m.group(1), text[i:j]


def scrape_mlb_pipeline(url: str, label: str, snap_date: str, year: int,
                        force: bool = False,
                        cache_key: str | None = None) -> list[Snapshot]:
    """Parse one archived MLB.com Top 100 page into Snapshot rows.

    Algorithm:
      1. Fetch HTML with a real-browser UA (project UA gets 406).
      2. html.unescape the body so the embedded JSON becomes plain text.
      3. Build name + current-team lookups by walking Apollo Person and Team
         entities (each clipped to its own record window). Affiliate teams
         carry parentOrgName so a Triple-A roster spot resolves to the
         parent MLB org via canonical_org().
      4. Walk RankedPlayerEntity records in document order. Each carries:
           - "rank": N
           - "player": {"__ref": "Person:ID"}     → MLBAM ID
           - "position": "SS/3B" / "RHP" / etc.
           - "prospectBio": [ {contentText, contentTitle}, ... ]
         Pick the bio whose contentTitle equals str(year); within its HTML,
         the line "Scouting grades: ... | Overall: NN" carries the FV.
    """
    from trades import canonical_org

    if date.fromisoformat(snap_date) > date.today():
        return []

    if cache_key is None:
        cache_key = f"mlb_pipeline_{year}_top100"
    cache_path = CACHE_DIR / f"{cache_key}.html"
    # v23 — Year-aware TTL gate (shared with _fetch). Current-year
    # pages refresh every 24h; prior-year pages stay cached 30d.
    body = None
    if cache_path.exists() and not force:
        age_seconds = time.time() - cache_path.stat().st_mtime
        ttl = _cache_ttl_for_key(cache_key)
        if age_seconds <= ttl:
            body = cache_path.read_text(encoding="utf-8")
            log.info("cache hit: %s (%d bytes, age %.0fh, ttl %.0fh)",
                     cache_key, len(body), age_seconds / 3600, ttl / 3600)
        else:
            log.info("cache stale: %s (age %.0fh > ttl %.0fh) — refetching",
                     cache_key, age_seconds / 3600, ttl / 3600)
    if body is None:
        log.info("fetching: %s", url)
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, headers=MLB_PIPELINE_HEADERS, timeout=30)
        except requests.RequestException as e:
            log.error("network error fetching %s: %s", url, e)
            return []
        if resp.status_code != 200:
            log.warning("mlb_pipeline %s: HTTP %d (%d bytes)",
                        label, resp.status_code, len(resp.text))
            return []
        body = resp.text
        cache_path.write_text(body, encoding="utf-8")

    text = html.unescape(body)

    persons: dict[str, dict] = {}
    for pid, p_body in _apollo_entities(text, "Person"):
        first = re.search(r'"useName":"([^"]*)"', p_body)
        last  = re.search(r'"useLastName":"([^"]*)"', p_body)
        ar    = re.search(r'"activeRoster":\{"__ref":"Team:(\d+)"\}', p_body)
        full  = f"{(first.group(1) if first else '').strip()} " \
                f"{(last.group(1) if last else '').strip()}".strip()
        persons[pid] = {
            "name": fix_mojibake(full),
            "team_id": ar.group(1) if ar else None,
        }

    teams: dict[str, tuple[str | None, str | None]] = {}
    for tid, t_body in _apollo_entities(text, "Team"):
        name_m = re.search(r'"name":"([^"]*)"', t_body)
        par_m  = re.search(r'"parentOrgName":(null|"([^"]*)")', t_body)
        parent = par_m.group(2) if (par_m and par_m.group(2)) else None
        teams[tid] = (
            name_m.group(1) if name_m else None,
            parent,
        )

    def _resolve_org(pid: str) -> str | None:
        p = persons.get(pid)
        if not p:
            return None
        tid = p.get("team_id")
        if not tid or tid not in teams:
            return None
        name, parent = teams[tid]
        target = parent or name
        if not target:
            return None
        return canonical_org(target) or target

    rows: list[Snapshot] = []
    starts = [m.start() for m in re.finditer(
        re.escape('{"__typename":"RankedPlayerEntity",'), text)]
    year_str = str(year)
    seen_ranks: set[int] = set()
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else s + 200_000
        chunk = text[s:e]
        rank_m   = re.search(r'"rank":(\d+)', chunk)
        person_m = re.search(r'"player":\{"__ref":"Person:(\d+)"\}', chunk)
        pos_m    = re.search(r'"position":"([^"]+)"', chunk)
        if not (rank_m and person_m):
            continue
        rank = int(rank_m.group(1))
        if rank in seen_ranks:
            continue
        seen_ranks.add(rank)
        pid = person_m.group(1)
        position = pos_m.group(1) if pos_m else None

        bios = list(re.finditer(
            r'"contentText":"((?:[^"\\]|\\.)*)","contentTitle":"([^"]*)"', chunk))
        overall: float | None = None
        bio_text: str | None = None
        # Prefer the bio whose contentTitle matches the page year.
        for bio in bios:
            if bio.group(2) == year_str:
                m2 = re.search(r'Overall:\s*([0-9]+(?:\s*/\s*[0-9]+)?\+?)', bio.group(1))
                if m2:
                    overall, _overall_plus = _parse_fv_full(m2.group(1))
                    bio_text = bio.group(1)
                    break
        # Fallback: any bio with an Overall grade line.
        if overall is None:
            for bio in bios:
                m2 = re.search(r'Overall:\s*([0-9]+(?:\s*/\s*[0-9]+)?\+?)', bio.group(1))
                if m2:
                    overall, _overall_plus = _parse_fv_full(m2.group(1))
                    bio_text = bio.group(1)
                    break

        # Tool grades — the Scouting grades line carries tool grades
        # ahead of the Overall: token. Parse each "Name: NN" pair and
        # map onto our canonical tool keys (Run → speed, Power →
        # game_pwr, etc.). The full line varies in length by source
        # snapshot; we don't require every tool, just take what's there.
        tools = _parse_pipeline_tools(bio_text) if bio_text else None

        # Writeup — bio_text is the prospect's full bio prose from the
        # Apollo cache. It carries the narrative paragraph plus a
        # "Scouting grades: ... | Overall: NN" line which we already
        # parsed for tools. Strip the grades line + any embedded HTML
        # (Pipeline sometimes wraps paragraphs in <p>/<em>), then keep
        # the rest as the report. JSON-escaped newlines (`\\n`) are
        # promoted to real newlines so paragraph breaks survive.
        prose = _clean_pipeline_writeup(bio_text) if bio_text else None
        if prose and len(prose) > 60:
            tools = tools or {}
            cleaned = _clean_report_prose(prose)
            if cleaned:
                tools.setdefault("_extras", {})["report"] = cleaned[:8000]

        p = persons.get(pid, {})
        name = p.get("name") or f"Person {pid}"
        rows.append(Snapshot(
            source="mlb_pipeline", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=position, org=_resolve_org(pid),
            rank=rank, fv=overall, status="active",
            tools=tools,
        ))

    log.info("mlb_pipeline %s -> %d players%s", label, len(rows),
             "" if rows else " (parser returned 0 rows — page structure may have changed; check cached HTML)")
    return rows


def validate_pipeline_live_board(rows: list[Snapshot]) -> list[str]:
    """Health gate for the LIVE Pipeline capture (the tjstats.health_check
    pattern): refuse to ingest a degraded parse so a silent MLB.com
    redesign surfaces loudly instead of polluting the time series with a
    near-empty or grade-less board. Returns human-readable problems
    (empty = healthy)."""
    problems: list[str] = []
    if len(rows) < 90:
        problems.append(f"top100: only {len(rows)} parsed rows")
        return problems
    ranks = [s.rank for s in rows if s.rank is not None]
    if len(set(ranks)) != len(ranks):
        problems.append("top100: duplicate ranks")
    if not ranks or min(ranks) != 1 or max(ranks) > 105:
        problems.append(f"top100: rank span {min(ranks) if ranks else '-'}"
                        f"..{max(ranks) if ranks else '-'}")
    n = len(rows)
    fv_cov = sum(1 for s in rows if s.fv is not None) / n
    if fv_cov < 0.8:
        problems.append(f"top100: FV coverage {fv_cov:.0%} (<80% — grades "
                        "line may have moved)")
    org_cov = sum(1 for s in rows if s.org) / n
    if org_cov < 0.7:
        problems.append(f"top100: org coverage {org_cov:.0%} (<70% — Apollo "
                        "Team refs may have changed)")
    placeholder = sum(1 for s in rows if s.player_name.startswith("Person "))
    if placeholder > 2:
        problems.append(f"top100: {placeholder} unresolved player names")
    return problems


def validate_pipeline_org_boards(org_rows: dict[str, list[Snapshot]]) -> list[str]:
    """Health gate for the daily per-team Top-30 capture, the sibling of
    validate_pipeline_live_board. Refuse to re-stamp the org boards if the
    parse comes back degraded, so a silent MLB.com redesign surfaces loudly
    instead of freezing every team board at a near-empty scrape. Requires at
    least 25 of the ~30 orgs to return >= 20 players each. Returns
    human-readable problems (empty = healthy)."""
    MIN_HEALTHY_ORGS = 25
    MIN_PLAYERS_PER_ORG = 20
    problems: list[str] = []
    healthy = [slug for slug, rows in org_rows.items()
               if len(rows) >= MIN_PLAYERS_PER_ORG]
    if len(healthy) < MIN_HEALTHY_ORGS:
        thin = sorted((len(rows), slug) for slug, rows in org_rows.items())
        problems.append(
            f"org top30: only {len(healthy)}/{len(org_rows)} orgs returned "
            f">= {MIN_PLAYERS_PER_ORG} players (need {MIN_HEALTHY_ORGS}); "
            "thinnest: " + ", ".join(f"{slug}={n}" for n, slug in thin[:6]))
    return problems


def run_mlb_pipeline_org_live(snap_date: str | None = None) -> dict:
    """Daily LIVE capture of MLB Pipeline's 30 per-team Top-30 boards
    (step d0b, right after run_mlb_pipeline_live).

    The monthly backfill (MLB_PIPELINE_ORG_INTERVALS) writes each org's board
    to ONE fixed preseason interval ("MLB Pipeline {y} {Team} Top 30", snap
    {y}-01-22). Pipeline re-ranks and re-grades the org boards through the
    season (graduations, FV moves, and the whole current-year draft class
    joining post-signing), but that single frozen January point never moves.
    So consensus reads a stale preseason vintage for the ~800 prospects who
    sit in a team Top 30 but not the daily-fresh Live Top 100.

    This capture re-scrapes the current /prospects/{year}/{slug} pages and
    re-stamps the SAME per-team label with TODAY's date: insert_snapshots'
    (source, interval_label, player_key) conflict key upserts the January row
    in place, bumping snapshot_date to today, so consensus reads the current
    vintage. force is left False so the 24h current-year cache TTL governs --
    one fetch per page per day, cache-hit on same-day re-runs (polite pacing).

    A parse-health gate (validate_pipeline_org_boards) refuses to write if the
    boards come back degraded, so an MLB.com redesign can't silently freeze
    every org at a near-empty scrape.

    Returns {"orgs": {...}} on ingest, {"health": [problems]} when the gate
    refuses, {"error": "..."} on a fatal failure."""
    from storage import insert_snapshots

    snap_date = snap_date or date.today().isoformat()
    year = int(snap_date[:4])

    org_rows: dict[str, list[Snapshot]] = {}
    all_rows: list[Snapshot] = []
    errors: dict[str, str] = {}
    for slug in MLB_PIPELINE_ORG_SLUGS:
        url = f"https://www.mlb.com/prospects/{year}/{slug}"
        label = f"MLB Pipeline {year} {_slug_to_label(slug)} Top 30"
        cache_key = f"mlb_pipeline_{year}_org_{slug.replace('-', '_')}"
        try:
            rows = scrape_mlb_pipeline(url, label, snap_date, year,
                                       cache_key=cache_key)
        except Exception as e:                                # noqa: BLE001
            log.warning("mlb_pipeline org live %s crashed: %s", slug, e)
            errors[slug] = str(e)
            org_rows[slug] = []
            continue
        org_rows[slug] = rows
        all_rows.extend(rows)

    problems = validate_pipeline_org_boards(org_rows)
    if problems:
        if errors:
            problems.append(f"fetch/parse errors: {errors}")
        return {"health": problems}

    n = insert_snapshots(all_rows)
    n_orgs = sum(1 for rows in org_rows.values() if rows)
    log.info("mlb_pipeline org live: %d players across %d orgs ingested @ %s",
             len(all_rows), n_orgs, snap_date)
    return {"orgs": {"n_players": len(all_rows), "n_orgs": n_orgs,
                     "n_upserts": n, "snap_date": snap_date,
                     "errors": errors}}


def run_mlb_pipeline_live(snap_date: str | None = None) -> dict:
    """Daily LIVE capture of MLB Pipeline's current Top 100 (the TJStats
    pattern, step d0b in run_daily). The monthly scrape writes each year's
    board to ONE fixed preseason interval ("MLB Pipeline {y} Top 100",
    snap 01-22), so in-season re-ranks/FV changes overwrite that single
    point instead of accruing history. This capture force-fetches the
    current page and writes a DATE-STAMPED interval — a same-day re-run
    upserts in place (insert_snapshots' (source, interval_label,
    player_key) conflict key); a new day creates a new point-in-time row,
    giving the Time Machine and the consensus the same daily resolution
    TJStats gets. Vintage discipline holds: backtests key on the earliest
    same-year snapshot, which stays the preseason archive page.

    Returns {"live": {...}} on ingest, {"health": [problems]} when the
    gate refuses, {"error": "..."} on fetch/parse failure."""
    from storage import insert_snapshots

    snap_date = snap_date or date.today().isoformat()
    year = int(snap_date[:4])
    url = f"https://www.mlb.com/milb/prospects/{year}/top100/"
    label = f"MLB Pipeline Live {snap_date}"
    try:
        rows = scrape_mlb_pipeline(url, label, snap_date, year, force=True)
    except Exception as e:                                    # noqa: BLE001
        return {"error": f"fetch/parse failed: {e}"}
    problems = validate_pipeline_live_board(rows)
    if problems:
        return {"health": problems}
    n = insert_snapshots(rows)
    log.info("mlb_pipeline live: %d players ingested @ %s", len(rows), snap_date)
    return {"live": {"n_players": len(rows), "n_upserts": n,
                     "label": label, "captured_at": snap_date}}


def scrape_mlb_international(url: str, label: str, snap_date: str, year: int,
                             force: bool = False,
                             skip_unaffiliated: bool = True) -> list[Snapshot]:
    """Parse MLB Pipeline's international ranking table.

    The static page exposes rank/name/position but not signing org. We emit
    org=None here and let the monthly export merge these rows with the MiLB
    roster index; only players with an actual affiliate team get an org.
    """
    if date.fromisoformat(snap_date) > date.today():
        return []

    cache_key = f"mlb_pipeline_{year}_international"
    fr = _fetch(url, cache_key, force=force)
    if fr.status != 200 or not fr.body:
        return []

    text = html.unescape(fr.body)
    from trades import canonical_org

    persons: dict[str, dict] = {}
    for pid, p_body in _apollo_entities(text, "Person"):
        first = re.search(r'"useName":"([^"]*)"', p_body)
        last = re.search(r'"useLastName":"([^"]*)"', p_body)
        ar = re.search(r'"activeRoster":\{"__ref":"Team:(\d+)"\}', p_body)
        pos = re.search(
            r'"primaryPosition":\{[^}]*"abbreviation":"([^"]+)"',
            p_body,
        )
        full = f"{(first.group(1) if first else '').strip()} " \
               f"{(last.group(1) if last else '').strip()}".strip()
        persons[pid] = {
            "name": fix_mojibake(full),
            "team_id": ar.group(1) if ar else None,
            "position": pos.group(1) if pos else None,
        }

    teams: dict[str, str | None] = {}
    for tid, t_body in _apollo_entities(text, "Team"):
        par_m = re.search(r'"parentOrgName":(null|"([^"]*)")', t_body)
        parent = par_m.group(2) if (par_m and par_m.group(2)) else None
        teams[tid] = canonical_org(parent) if parent else None

    apollo_rows: list[Snapshot] = []
    starts = [m.start() for m in re.finditer(
        re.escape('{"__typename":"RankedPlayerEntity",'), text)]
    seen_ranks: set[int] = set()
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else s + 200_000
        chunk = text[s:e]
        rank_m = re.search(r'"rank":(\d+)', chunk)
        person_m = re.search(r'"player":\{"__ref":"Person:(\d+)"\}', chunk)
        pos_m = re.search(r'"position":"([^"]+)"', chunk)
        if not (rank_m and person_m):
            continue
        rank = int(rank_m.group(1))
        if rank in seen_ranks or rank > 50:
            continue
        seen_ranks.add(rank)
        person = persons.get(person_m.group(1), {})
        name = person.get("name")
        if not name:
            continue
        org = teams.get(person.get("team_id"))
        if not org and skip_unaffiliated:
            # The IFA merge is intentionally stateside/affiliate-aware:
            # players without a current roster assignment stay out until
            # MLB exposes a team for them. (The historical backfill passes
            # skip_unaffiliated=False and classifies these rows itself -
            # unaffiliated names on the intl list are often KBO/NPB pros
            # who belong in the Overseas section, not dropped.)
            continue
        overall = None
        overall_m = re.search(r'Overall:\s*([0-9]+(?:\s*/\s*[0-9]+)?\+?)', chunk)
        if overall_m:
            overall, _overall_plus = _parse_fv_full(overall_m.group(1))
        apollo_rows.append(Snapshot(
            source="mlb_pipeline_international",
            snapshot_date=snap_date,
            interval_label=label,
            player_key=normalize_key(name),
            player_name=name,
            position=pos_m.group(1) if pos_m else person.get("position"),
            org=org,
            # The Pipeline International list ranks players 1-50 within the
            # IFA class only — it is NOT comparable to the overall Top-100
            # rank emitted by scrape_mlb_pipeline. Surfacing rank here would
            # make a #1 IFA (real FV ~55) look like a #1 prospect overall
            # (rank-implied FV ~70). Strip it so only the explicit Overall
            # FV contributes to consensus.
            rank=None,
            fv=overall,
            status="active",
        ))

    if apollo_rows:
        log.info("mlb_international %s -> %d players", label, len(apollo_rows))
        return apollo_rows

    soup = BeautifulSoup(fr.body, "html.parser")
    lines = [
        fix_mojibake(line)
        for line in soup.get_text("\n").splitlines()
        if fix_mojibake(line)
    ]

    start = None
    for i, line in enumerate(lines):
        if line.lower().startswith("rank player position"):
            start = i + 1
            break
        if (
            line.lower() == "rank"
            and i + 2 < len(lines)
            and lines[i + 1].lower() == "player"
            and lines[i + 2].lower() == "position"
        ):
            start = i + 1
            while start < len(lines) and not re.fullmatch(r"\d{1,3}", lines[start]):
                start += 1
            break
    if start is None:
        log.warning("mlb_international %s: ranking header not found", label)
        return []

    rows: list[Snapshot] = []
    valid_positions = {
        "P", "RHP", "LHP", "SP", "RP", "C", "1B", "2B", "3B", "SS",
        "OF", "LF", "CF", "RF",
    }
    i = start
    while i < len(lines):
        line = lines[i]
        low = line.lower()
        if low.startswith("show full list") or low.startswith("prospect headlines"):
            break
        if not re.fullmatch(r"\d{1,3}", line):
            i += 1
            continue

        rank = int(line)
        if rank > 50:
            i += 1
            continue

        name = None
        pos = None
        j = i + 1
        while j < len(lines):
            candidate = lines[j]
            cand_low = candidate.lower()
            if re.fullmatch(r"\d{1,3}", candidate):
                break
            if cand_low.startswith("image:") or cand_low.startswith("photo headshot"):
                j += 1
                continue
            if name is None:
                name = candidate
            else:
                m = re.match(r"^([A-Z]{1,3})(?:\b|/)", candidate)
                if m and m.group(1) in valid_positions:
                    pos = m.group(1)
                    break
            j += 1

        if name and pos:
            rows.append(Snapshot(
                source="mlb_pipeline_international",
                snapshot_date=snap_date,
                interval_label=label,
                player_key=normalize_key(name),
                player_name=name,
                position=pos,
                org=None,
                # Same as the Apollo branch above — the IFA list rank is
                # not the same scale as overall Top-100 rank, so we don't
                # let it leak into rank-implied FV.
                rank=None,
                fv=None,
                status="active",
            ))
        i = max(j + 1, i + 1)

    log.info("mlb_international %s -> %d players", label, len(rows))
    return rows


# --- Draft prospect scrapers (ESPN + MLB Pipeline) -----------------------
# Amateur draft class scrapers. Parallel to scrape_espn_top100 /
# scrape_mlb_pipeline but emit DraftSnapshot (no org, has school +
# draft_year + player_type).
#
# Both reuse the existing HTML walkers — ESPN's h2-tier + rank-line
# parsing and MLB.com's Apollo-cache walker — which is why the new
# functions are mostly bookkeeping rather than parser code.


def _draft_player_key(draft_year: int, name: str) -> str:
    """Local copy of draft_csv.draft_player_key to avoid a circular
    import (draft_csv imports from scrapers)."""
    return f"draft_{draft_year}_{normalize_key(name)}"


ESPN_DRAFT_INTERVALS = [
    # Kiley McDaniel's mid-cycle 2026 draft Top 150.
    ("https://www.espn.com/mlb/story/_/id/48778463/2026-mlb-draft-rankings-update-top-150-prospects",
     "ESPN 2026 Draft Top 150", "2026-05-20", 2026),
]


def scrape_espn_draft(url: str, label: str, snap_date: str, draft_year: int,
                      force: bool = False) -> list[DraftSnapshot]:
    """Parse one ESPN draft prospect article.

    Same h2-tier + rank-line structure as `scrape_espn_top100`, but the
    rank line format is `<N>. <name>, <pos>, <school>` (school instead
    of MLB team). Tool-prose extraction and writeup capture reuse the
    existing helpers (`_parse_espn_tools`, `_ESPN_BIO_HEADER`,
    `_ESPN_TOOL_LABEL`).
    """
    if date.fromisoformat(snap_date) > date.today():
        return []
    cache_key = "espn_draft_" + re.sub(r"[^a-z0-9]+", "_", label.lower())
    cache_path = CACHE_DIR / f"{cache_key}.html"

    # v23 — year-aware TTL gate.
    body = None
    if cache_path.exists() and not force:
        age_seconds = time.time() - cache_path.stat().st_mtime
        ttl = _cache_ttl_for_key(cache_key)
        if age_seconds <= ttl:
            body = cache_path.read_text(encoding="utf-8")
            log.info("cache hit: %s (%d bytes, age %.0fh, ttl %.0fh)",
                     cache_key, len(body), age_seconds / 3600, ttl / 3600)
        else:
            log.info("cache stale: %s (age %.0fh > ttl %.0fh) — refetching",
                     cache_key, age_seconds / 3600, ttl / 3600)
    if body is None:
        log.info("fetching: %s", url)
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, headers=ESPN_HEADERS, timeout=30)
        except requests.RequestException as e:
            log.error("network error fetching %s: %s", url, e)
            return []
        if resp.status_code != 200:
            log.warning("espn_draft %s: HTTP %d", label, resp.status_code)
            return []
        cache_path.write_text(resp.text, encoding="utf-8")
        body = resp.text

    start = body.find('class="article-body"')
    if start < 0:
        log.warning("espn_draft %s: article-body div not found", label)
        return []
    body = body[start:]

    # Same candidate collection as scrape_espn_top100.
    candidates: list[tuple[int, str]] = []
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", body, re.DOTALL):
        candidates.append((m.start(), m.group(1)))
    for m in re.finditer(
        r"<p[^>]*>\s*(?:<[^>]+>\s*){0,2}<strong>(.*?)</strong>",
        body, re.DOTALL,
    ):
        candidates.append((m.start(), m.group(1)))
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", body, re.DOTALL):
        pblock = m.group(1)
        # br-split list: each fragment between <br/> is a candidate.
        # Solo-rank paragraphs (no <br/>): the whole paragraph is a candidate.
        if "<br" in pblock:
            for frag in re.split(r"<br\s*/?>", pblock):
                candidates.append((m.start(), frag))
        else:
            candidates.append((m.start(), pblock))
    candidates.sort(key=lambda c: c[0])

    fv_header = re.compile(r"^\s*(\d{2,3})\+?\s*FV\s*tier", re.IGNORECASE)
    # Rank line: "1. Roch Cholowsky (21.3), SS, UCLA"
    # or         "2. Grady Emerson (18.4), SS, Fort Worth Christian HS (TX), Texas commit"
    # Groups: (1) rank, (2) name+age, (3) pos, (4) school/commit chunk
    rank_line = re.compile(
        r"^\s*(\d{1,3})\.\s+(.+?),\s*([A-Za-z0-9/]+?),\s*(.+?)\s*$"
    )
    # Strip the "(age.x)" suffix the article appends to every name.
    _age_paren = re.compile(r"\s*\(\d{1,2}(?:\.\d+)?\)\s*$")
    # College-commit suffix on HS players: ", <School> commit"
    _commit_re = re.compile(r"^(.+?)\s*,\s*(.+?)\s+commit\s*$", re.IGNORECASE)

    rank_offsets: list[int] = []
    for (off, h) in candidates:
        text = re.sub(r"<[^>]+>", "", h)
        text = fix_mojibake(text)
        if rank_line.match(text):
            rank_offsets.append(off)
    rank_offsets.append(len(body))

    rows: list[DraftSnapshot] = []
    current_fv: float | None = None
    seen_ranks: set[int] = set()

    for (off, h) in candidates:
        text = re.sub(r"<[^>]+>", "", h)
        text = fix_mojibake(text)
        if not text:
            continue
        fm = fv_header.match(text)
        if fm:
            current_fv = float(fm.group(1))
            continue
        rm = rank_line.match(text)
        if not rm:
            continue
        rank = int(rm.group(1))
        if not (1 <= rank <= 200) or rank in seen_ranks:
            continue
        seen_ranks.add(rank)
        name = rm.group(2).strip()
        name = _age_paren.sub("", name).strip()
        pos  = rm.group(3).strip() or None
        school = rm.group(4).strip()
        # Pull college commit out of the school chunk for HS players.
        commit = None
        cm = _commit_re.match(school)
        if cm:
            school = cm.group(1).strip()
            commit = cm.group(2).strip()

        # Commentary slice → tools + writeup
        try:
            next_off = rank_offsets[rank_offsets.index(off) + 1]
        except (ValueError, IndexError):
            next_off = len(body)
        commentary = body[off:next_off]
        commentary = html.unescape(re.sub(r"<[^>]+>", " ", commentary))
        commentary = fix_mojibake(commentary)
        tools = _parse_espn_tools(commentary)

        prose = re.sub(r"\s+", " ", commentary).strip()
        rank_prefix = f"{rank}. {name}, {pos}, {school}" if pos else f"{rank}. {name}, {school}"
        idx = prose.find(rank_prefix)
        if idx >= 0:
            prose = prose[idx + len(rank_prefix):]
        while True:
            stripped = _ESPN_BIO_HEADER.sub("", prose, count=1)
            stripped = _ESPN_TOOL_LABEL.sub("", stripped, count=1)
            if stripped == prose:
                break
            prose = stripped
        prose = re.sub(r"\s+", " ", prose).strip()
        if prose and len(prose) > 60:
            tools = tools or {}
            cleaned = _clean_report_prose(prose)
            if cleaned:
                tools.setdefault("_extras", {})["report"] = cleaned[:8000]

        # Heuristic player_type from school string.
        ptype = None
        if re.search(r"\bHS\b", school, re.IGNORECASE) or "High School" in school:
            ptype = "HS"
        elif school:
            ptype = "COL"
        # Add h/p suffix from position
        if ptype:
            ptype += "p" if pos and any(p in pos.upper() for p in ("SP", "RP", "RHP", "LHP")) else "h"

        rows.append(DraftSnapshot(
            source="espn_draft", snapshot_date=snap_date, interval_label=label,
            player_key=_draft_player_key(draft_year, name),
            player_name=name, position=pos, school=school,
            college_commit=commit, player_type=ptype, draft_year=draft_year,
            rank=rank, fv=current_fv, risk=None, status="draft_active",
            tools=tools,
        ))

    log.info("espn_draft %s -> %d players%s", label, len(rows),
             "" if rows else " (parser returned 0 rows — page structure may have changed; check cached HTML)")
    return rows


MLB_PIPELINE_DRAFT_INTERVALS = [
    ("https://www.mlb.com/milb/prospects/draft",
     "MLB Pipeline 2026 Draft Top 250",
     date.today().isoformat(),
     2026),
]

# Prior-year MLB Pipeline draft boards (frozen pre-draft rankings) live at the
# year-scoped URL /milb/prospects/<year>/draft/. Backfilled so the draft-source
# accuracy backtest (draft_source_backtest.py) has a SECOND multi-year rater to
# score FanGraphs against — without resolved historical grades from a second
# source there is nothing to weight. The page's "draft"-titled writeup carries
# that year's pre-draft Overall grade (the year-titled bios on these pages are
# post-draft re-grades, so the same draft-first bio rule as the live board is
# correct). Dated to {year}-07-01 (pre-draft) to sit in the right draft class;
# prior-year pages stay on the 30d historical cache. 2018 is the first year MLB
# Pipeline published a scrapable draft board in this shape.
MLB_PIPELINE_DRAFT_HISTORY_INTERVALS = [
    (f"https://www.mlb.com/milb/prospects/{_y}/draft/",
     f"MLB Pipeline {_y} Draft Top 250",
     f"{_y}-07-01",
     _y)
    for _y in range(2018, date.today().year)
]


def scrape_mlb_pipeline_draft(url: str, label: str, snap_date: str,
                              draft_year: int,
                              force: bool = False) -> list[DraftSnapshot]:
    """Parse MLB Pipeline's amateur draft prospect rankings page.

    Same Apollo cache pattern as `scrape_mlb_pipeline` (Top 100). Schools
    live on the Person entity in `colleges[0].name` / `highschools[0].name`
    instead of `activeRoster.parentOrgName`.
    """
    if date.fromisoformat(snap_date) > date.today():
        return []

    cache_key = f"mlb_pipeline_draft_{draft_year}"
    cache_path = CACHE_DIR / f"{cache_key}.html"
    # v23 — year-aware TTL gate.
    body = None
    if cache_path.exists() and not force:
        age_seconds = time.time() - cache_path.stat().st_mtime
        ttl = _cache_ttl_for_key(cache_key)
        if age_seconds <= ttl:
            body = cache_path.read_text(encoding="utf-8")
            log.info("cache hit: %s (%d bytes, age %.0fh, ttl %.0fh)",
                     cache_key, len(body), age_seconds / 3600, ttl / 3600)
        else:
            log.info("cache stale: %s (age %.0fh > ttl %.0fh) — refetching",
                     cache_key, age_seconds / 3600, ttl / 3600)
    if body is None:
        log.info("fetching: %s", url)
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, headers=MLB_PIPELINE_HEADERS, timeout=30)
        except requests.RequestException as e:
            log.error("network error fetching %s: %s", url, e)
            return []
        if resp.status_code != 200:
            log.warning("mlb_pipeline_draft %s: HTTP %d", label, resp.status_code)
            return []
        body = resp.text
        cache_path.write_text(body, encoding="utf-8")

    text = html.unescape(body)

    persons: dict[str, dict] = {}
    for pid, p_body in _apollo_entities(text, "Person"):
        first = re.search(r'"useName":"([^"]*)"', p_body)
        last  = re.search(r'"useLastName":"([^"]*)"', p_body)
        full  = f"{(first.group(1) if first else '').strip()} " \
                f"{(last.group(1) if last else '').strip()}".strip()
        # School: prefer colleges[0].name, else highschools[0].name + state suffix.
        school = None
        col_m = re.search(r'"colleges":\[\{[^}]*"name":"([^"]+)"', p_body)
        if col_m:
            school = col_m.group(1)
        else:
            hs_m = re.search(
                r'"highschools":\[\{[^}]*"name":"([^"]+)"'
                r'(?:[^}]*"state":"([^"]+)")?', p_body)
            if hs_m:
                base = hs_m.group(1)
                state = hs_m.group(2)
                school = f"{base} HS ({state})" if state else f"{base} HS"
        age_m = re.search(r'"currentAge":(\d+)', p_body)
        pos_m = re.search(r'"primaryPosition":\{[^}]*"abbreviation":"([^"]+)"', p_body)
        persons[pid] = {
            "name":   fix_mojibake(full),
            "school": school,
            "age":    int(age_m.group(1)) if age_m else None,
            "position": pos_m.group(1) if pos_m else None,
        }

    rows: list[DraftSnapshot] = []
    starts = [m.start() for m in re.finditer(
        re.escape('{"__typename":"RankedPlayerEntity",'), text)]
    seen_ranks: set[int] = set()
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else s + 200_000
        chunk = text[s:e]
        rank_m   = re.search(r'"rank":(\d+)', chunk)
        person_m = re.search(r'"player":\{"__ref":"Person:(\d+)"\}', chunk)
        pos_m    = re.search(r'"position":"([^"]+)"', chunk)
        if not (rank_m and person_m):
            continue
        rank = int(rank_m.group(1))
        if rank in seen_ranks:
            continue
        seen_ranks.add(rank)
        pid = person_m.group(1)
        person = persons.get(pid, {})
        name = person.get("name")
        if not name:
            continue
        position = pos_m.group(1) if pos_m else person.get("position")

        # Bio + tools + writeup from prospectBio (same shape as top-100)
        bios = list(re.finditer(
            r'"contentText":"((?:[^"\\]|\\.)*)","contentTitle":"([^"]*)"', chunk))
        # Pick the CURRENT board's writeup. MLB Pipeline titles the live draft
        # bio with the generic token "draft"/"Draft"; a prospect who appeared in
        # an EARLIER draft also carries an older bio titled by that year
        # ("2023"). The live grade/tools are the "draft"-titled one, so prefer
        # it, then a bio titled with the draft year, then anything.
        #   Matching on str(draft_year) never hits (the current board is not
        #   year-titled), and blindly taking bios[0] grabbed the stale
        #   prior-draft grade for re-entrants — e.g. Roch Cholowsky read 2023's
        #   Overall 50 instead of 2026's Overall 65 (26 of the top 200 were
        #   affected, all biased low).
        _yr = str(draft_year)
        def _bio_rank(bio):
            t = (bio.group(2) or "").strip().lower()
            return 0 if t == "draft" else 1 if t == _yr else 2
        bios_ranked = sorted(bios, key=_bio_rank)
        overall: float | None = None
        bio_text: str | None = None
        for bio in bios_ranked:
            m2 = re.search(r'Overall:\s*([0-9]+(?:\s*/\s*[0-9]+)?\+?)', bio.group(1))
            if m2:
                overall, _overall_plus = _parse_fv_full(m2.group(1))
                bio_text = bio.group(1)
                break
        # No bio carried an Overall grade — still keep the best-priority writeup
        # so tools/prose extraction has something to work with.
        if bio_text is None and bios_ranked:
            bio_text = bios_ranked[0].group(1)

        tools = _parse_pipeline_tools(bio_text) if bio_text else None
        prose = _clean_pipeline_writeup(bio_text) if bio_text else None
        if prose and len(prose) > 60:
            tools = tools or {}
            cleaned = _clean_report_prose(prose)
            if cleaned:
                tools.setdefault("_extras", {})["report"] = cleaned[:8000]
        if person.get("age") is not None:
            tools = tools or {}
            tools.setdefault("_extras", {})["age"] = person["age"]

        school = person.get("school")
        ptype = None
        if school:
            if "HS" in school or "High School" in school:
                ptype = "HS"
            else:
                ptype = "COL"
            ptype += "p" if position and any(p in position.upper() for p in ("SP", "RP", "RHP", "LHP", "P")) else "h"

        rows.append(DraftSnapshot(
            source="mlb_pipeline_draft", snapshot_date=snap_date,
            interval_label=label,
            player_key=_draft_player_key(draft_year, name),
            player_name=name, position=position, school=school,
            college_commit=None, player_type=ptype, draft_year=draft_year,
            rank=rank, fv=overall, risk=None, status="draft_active",
            tools=tools,
        ))

    log.info("mlb_pipeline_draft %s -> %d players%s", label, len(rows),
             "" if rows else " (parser returned 0 rows — page structure may have changed; check cached HTML)")
    return rows


def scrape_all_draft(force: bool = False, history: bool = True) -> list[DraftSnapshot]:
    """Run all draft scrapers, return their combined output.

    `history` includes the prior-year MLB Pipeline draft boards (frozen, 30d
    cache) so the source-accuracy backtest has resolved multi-source classes;
    pass history=False to scrape only the live current-year boards.
    """
    out: list[DraftSnapshot] = []
    for url, label, snap, year in ESPN_DRAFT_INTERVALS:
        try:
            out.extend(scrape_espn_draft(url, label, snap, year, force=force))
        except Exception as e:
            log.exception("espn_draft %s crashed: %s", label, e)
    pipeline_intervals = list(MLB_PIPELINE_DRAFT_INTERVALS)
    if history:
        pipeline_intervals += MLB_PIPELINE_DRAFT_HISTORY_INTERVALS
    for url, label, snap, year in pipeline_intervals:
        try:
            out.extend(scrape_mlb_pipeline_draft(url, label, snap, year, force=force))
        except Exception as e:
            log.exception("mlb_pipeline_draft %s crashed: %s", label, e)
    log.info("scrape_all_draft: %d total draft snapshots", len(out))
    return out


# --- MLB Draft results via Stats API (post-draft per-pick + signing bonus) -
# MLB exposes the full draft history via statsapi.mlb.com/api/v1/draft/<year>.
# Each pick carries person, team, pickNumber, pickRound, signingBonus,
# pickValue (slot), and a scoutingReport blurb. No HTML scraping needed.

MLB_DRAFT_API_TEMPLATE = "https://statsapi.mlb.com/api/v1/draft/{year}"


def _draft_tracker_school(sc) -> str | None:
    """School string from a draft-API pick's `school` object. The API gives
    {name, state, city, country} for every pick across every round - far
    deeper than the ~200-row MLB Pipeline boards. For high schools (and prep
    academies) we append the state tag "(ST)" so the HS Details geography
    section can read the home state on older classes; college names are left
    plain (they carry no HS marker, so they never get tagged)."""
    if not isinstance(sc, dict):
        return None
    name = sc.get("name")
    if not name:
        return None
    state = sc.get("state")
    if (state and re.search(r"\bHS\b|High School|\bAcademy\b|\bPrep\b", name)
            and not re.search(r"\([A-Z]{2}\)\s*$", name)):
        return f"{name} ({state})"
    return name


def scrape_mlb_draft_tracker(year: int, force: bool = False) -> list[dict]:
    """Pull one year's draft results from the MLB Stats API.

    Returns a list of dicts compatible with `storage.upsert_draft_results`.
    Covers every round + pick + signing bonus + slot value. Unsigned
    picks have `signingBonus=null` and surface as `signed=0`."""
    url = MLB_DRAFT_API_TEMPLATE.format(year=year)
    cache_key = f"mlb_draft_api_{year}"
    fr = _fetch(url, cache_key, force=force, accept_json=True)
    if fr.status != 200 or not fr.body:
        log.info("mlb_draft_tracker %d: no data (HTTP %d)", year, fr.status)
        return []
    try:
        payload = json.loads(fr.body)
    except json.JSONDecodeError:
        log.warning("mlb_draft_tracker %d: non-JSON response", year)
        return []

    from trades import canonical_org
    rows: list[dict] = []
    rounds = (payload.get("drafts") or {}).get("rounds") or []
    for r_block in rounds:
        round_label = str(r_block.get("round") or "")
        for p in r_block.get("picks") or []:
            pick_overall = p.get("pickNumber")
            if not pick_overall:
                continue
            person = p.get("person") or {}
            name = fix_mojibake(person.get("fullName") or "")
            if not name:
                continue
            team_full = (p.get("team") or {}).get("name") or ""
            org = canonical_org(team_full) or team_full or None
            if not org:
                continue
            bonus = p.get("signingBonus")
            try:
                bonus_int = int(float(bonus)) if bonus is not None else None
            except (TypeError, ValueError):
                bonus_int = None
            slot = p.get("pickValue")
            # pickValue is often a string like "$8,950,000".
            slot_int = None
            if slot is not None:
                s = re.sub(r"[^\d]", "", str(slot))
                if s:
                    try:
                        slot_int = int(s)
                    except ValueError:
                        pass
            # is_signed: explicit flag preferred, else infer from bonus.
            is_signed_raw = p.get("isSigned")
            if is_signed_raw is True:
                signed = 1
            elif is_signed_raw is False:
                signed = 0
            else:
                signed = 1 if bonus_int else 0
            rows.append({
                "draft_year":   year,
                "pick_overall": pick_overall,
                "round_label":  p.get("pickRound") or round_label or None,
                "pick_in_round": p.get("roundPickNumber"),
                "team":         org,
                "player_key":   _draft_player_key(year, name),
                "player_name":  name,
                "school":       _draft_tracker_school(p.get("school")),
                "slot_usd":     slot_int,
                "bonus_usd":    bonus_int,
                "signed":       signed,
                "source":       "mlb_stats_api",
            })

    log.info("mlb_draft_tracker %d: %d picks parsed (%d signed)",
             year, len(rows), sum(1 for r in rows if r.get("signed")))
    return rows


# --- Spotrac draft order + slot values -----------------------------------
# Spotrac publishes the live MLB draft order with per-pick slot values
# (Slotted Bonus) ahead of the draft. More current than MLB.com's
# pool articles, which lag until late spring. Same real-browser UA
# trick we use for ESPN — the default project UA gets 403.
#
# Page shape: the first <table> on `/mlb/draft/_/year/<year>` has 625
# rows, one per pick across all 20 rounds, with columns:
#   Round | Pick | Team | (logo) | Player | Pos | Age | Bat/Throw |
#   Pre-Draft Team | Slotted Bonus
# Pre-draft, Player/Pos/Age are empty; Slotted Bonus is populated for
# every pick that has a slot value (R1-R10 ~ all picks; later rounds
# get a flat $150,000-ish under-slot value).

SPOTRAC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _normalize_round_label(raw: str) -> str | None:
    """Map Spotrac's round-cell text to a canonical round_label.

    Examples it handles:
      "1" → "1"     "2" → "2"     "10" → "10"
      "1A" / "1a" / "1-A" / "Comp Round A" / "Competitive Balance A" → "1A"
      "1B" / "Comp Round B" / "Competitive Balance B"               → "1B"
      "2A" / "Comp Round A" within round 2 → "2A"  (best-effort)
    Returns None when the text is empty or unparseable."""
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    # Plain integer round.
    try:
        return str(int(s))
    except ValueError:
        pass
    # Comp-pick variants. Look for a round-prefix digit + A/B suffix.
    m = re.match(r"^\s*(\d+)\s*[-\s]?\s*([ABab])\b", s)
    if m:
        return f"{m.group(1)}{m.group(2).upper()}"
    # "Comp Round A" / "Competitive Balance A" with no explicit round prefix.
    if re.search(r"\bComp(?:etitive)?\b.*\bA\b", s, re.IGNORECASE):
        return "1A"
    if re.search(r"\bComp(?:etitive)?\b.*\bB\b", s, re.IGNORECASE):
        return "1B"
    # Last resort — return the raw label upper-cased to preserve info.
    return s.upper()[:4]


def scrape_spotrac_draft_order(year: int, force: bool = False) -> list[dict]:
    """Parse Spotrac's MLB draft page → draft_order rows ready for
    `storage.upsert_draft_order`.

    Each row: draft_year, pick_overall, round_label, pick_in_round,
    team, slot_usd, source='spotrac'."""
    from trades import canonical_org

    url = f"https://www.spotrac.com/mlb/draft/_/year/{year}"
    cache_key = f"spotrac_draft_{year}"
    cache_path = CACHE_DIR / f"{cache_key}.html"
    if cache_path.exists() and not force:
        body = cache_path.read_text(encoding="utf-8")
        log.info("cache hit: %s (%d bytes)", cache_key, len(body))
    else:
        log.info("fetching: %s", url)
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, headers=SPOTRAC_HEADERS, timeout=30)
        except requests.RequestException as e:
            log.error("network error fetching %s: %s", url, e)
            return []
        if resp.status_code != 200:
            log.warning("spotrac_draft_order %d: HTTP %d", year, resp.status_code)
            return []
        body = resp.text
        cache_path.write_text(body, encoding="utf-8")

    soup = BeautifulSoup(body, "html.parser")
    # Take the first table that has both a 'Round' and 'Slotted Bonus'
    # header — that's the master pick list. Other tables on the page
    # are per-round subsets that duplicate the data.
    master = None
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if not rows:
            continue
        headers = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        if "round" in headers and "slotted bonus" in headers:
            master = t
            break
    if master is None:
        log.warning("spotrac_draft_order %d: master table not found", year)
        return []

    out: list[dict] = []
    body_rows = master.find_all("tr")[1:]
    # Track running pick number per round. Spotrac labels rounds as
    # "1", "2", … for the regular rounds and "1A", "1B", "Comp Round
    # A", "1-A", etc. for competitive-balance picks. We preserve the
    # canonical label in `round_label` (text) but still track a
    # numeric continuity counter so `pick_in_round` resets cleanly
    # when the canonical label changes.
    last_label: str | None = None
    pick_in_round = 0
    for r in body_rows:
        cells = [c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])]
        if len(cells) < 10:
            continue
        round_raw = cells[0].strip()
        pick_raw  = cells[1].strip()
        team_raw  = cells[2].strip()
        slot_raw  = cells[9].strip()
        if not pick_raw:
            continue
        try:
            pick = int(pick_raw)
        except ValueError:
            continue
        round_label = _normalize_round_label(round_raw) if round_raw else last_label
        if round_label is None:
            continue
        if round_label != last_label:
            last_label = round_label
            pick_in_round = 0
        pick_in_round += 1
        team_code = canonical_org(team_raw) or team_raw or None
        if not team_code:
            continue
        slot_int = None
        if slot_raw and slot_raw not in {"-", "—", ""}:
            digits = re.sub(r"[^\d]", "", slot_raw)
            if digits:
                try:
                    slot_int = int(digits)
                except ValueError:
                    slot_int = None
        out.append({
            "draft_year":    year,
            "pick_overall":  pick,
            "round_label":   round_label,
            "pick_in_round": pick_in_round,
            "team":          team_code,
            "slot_usd":      slot_int,
            "source":        "spotrac",
        })

    log.info("spotrac_draft_order %d: %d picks parsed (%d with slot values)",
             year, len(out), sum(1 for r in out if r.get("slot_usd")))
    return out


# --- Tankathon lottery odds ----------------------------------------------
# Tankathon's MLB page shows the projected lottery position for the
# *next* MLB Draft based on current standings. Under the 2022 CBA the
# top 6 picks are lottery-determined for the non-playoff teams, so
# the "Odds" column is each team's % chance of landing #1 overall.

TANKATHON_URL = "https://www.tankathon.com/mlb"

# "42 - 67" (the Record column). The SPACES around the dash are load-bearing:
# the L10 column on the same row reads "3-7" and would otherwise match, which
# would store a team's last-ten record as its season record.
_TANK_RECORD_RE = re.compile(r"^(\d{1,3})\s+-\s+(\d{1,3})$")
_TANK_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _parse_pct_cell(raw: str) -> float | None:
    """'17.95 %' -> 17.95; '' / '--' / anything unparseable -> None."""
    if not raw:
        return None
    m = _TANK_PCT_RE.search(raw)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_record_cell(cells: list[str]) -> tuple[int | None, int | None]:
    """(wins, losses) from the Record column, or (None, None).

    Index 2 is the Record column on the measured layout; we validate the
    shape rather than trusting the position, and only fall back to a scan of
    the other cells if index 2 does not look like a W - L record."""
    candidates = ([cells[2]] if len(cells) > 2 else []) + list(cells)
    for c in candidates:
        m = _TANK_RECORD_RE.match((c or "").strip())
        if m:
            try:
                return int(m.group(1)), int(m.group(2))
            except ValueError:
                return None, None
    return None, None


def scrape_tankathon_lottery(year: int, force: bool = False) -> list[dict]:
    """Parse Tankathon's MLB page → draft_lottery_odds rows for the
    FULL projected first-round order (not just the top-6 lottery
    slots). `year` is the draft year the projection applies to.

    Output row shape:
      {draft_year, team, pick_pos, odds_pct (nullable past pick 6),
       odds_top6_pct, wins, losses,
       round_label ('1' or '1A'/'1B' for comp picks),
       snapshot_date, source='tankathon'}

    Lottery slots carry a real `odds_pct` (% chance at the #1 pick) AND
    `odds_top6_pct` (% chance of landing anywhere in the lottery's top 6).
    Deterministic slots carry None for both. Comp-round picks are labeled
    '1A' or '1B' depending on Tankathon's row classifier.

    CELL INDEXING - READ BEFORE EDITING. The header row and the data rows
    have DIFFERENT lengths, so positional indexing has to be anchored to the
    correct end. Measured against .cache/tankathon_mlb.html (2026-07-31):

      header (10): Pick | Team | Record Rec | Win% Pct | GB | Streak | L10 |
                   Top 6 | #1 OVR | ''
      data   ( 9): 1 | Colorado COL | 42 - 67 | .385 | -- | Lost 4 | 3-7 |
                   86.3 % | 17.95 %

    The header carries a trailing empty cell the data rows do not, so
    aligning by header index is off by one at the tail. We therefore index
    the two odds columns from the END of the DATA row: cells[-1] = '#1 OVR',
    cells[-2] = 'Top 6'. The previous implementation scanned for the LAST
    cell containing '%', which happened to be right for '#1 OVR' but gave no
    way to reach 'Top 6' at all.

    GUARDS:
      * Playoff-team rows (projected picks 19-30) carry EMPTY odds cells;
        so do lottery-ineligible non-playoff teams (SF at 10 and PIT at 15
        on the measured page - a team cannot receive a lottery pick in
        consecutive years / revenue-sharing rules). Empty parses to None,
        never to 0.0.
      * Comp-balance picks come from a SIDEBAR widget, not this table. They
        are renumbered to synthetic pick_pos 31-42 and carry round_label
        '1A'/'1B' with wins/losses/odds all None. Filter them out of any
        standings math by round_label - their pick_pos is NOT a real slot.
    """
    from trades import canonical_org

    cache_key = "tankathon_mlb"
    cache_path = CACHE_DIR / f"{cache_key}.html"
    # v23 — TTL gate. Tankathon's lottery projection changes daily as
    # standings move, so the default 24h TTL keeps it fresh.
    body = None
    if cache_path.exists() and not force:
        age_seconds = time.time() - cache_path.stat().st_mtime
        ttl = _cache_ttl_for_key(cache_key)
        if age_seconds <= ttl:
            body = cache_path.read_text(encoding="utf-8")
            log.info("cache hit: %s (%d bytes, age %.0fh, ttl %.0fh)",
                     cache_key, len(body), age_seconds / 3600, ttl / 3600)
        else:
            log.info("cache stale: %s (age %.0fh > ttl %.0fh) — refetching",
                     cache_key, age_seconds / 3600, ttl / 3600)
    if body is None:
        log.info("fetching: %s", TANKATHON_URL)
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(TANKATHON_URL, headers=SPOTRAC_HEADERS, timeout=20)
        except requests.RequestException as e:
            log.error("network error fetching tankathon: %s", e)
            return []
        if resp.status_code != 200:
            log.warning("tankathon_lottery: HTTP %d", resp.status_code)
            return []
        body = resp.text
        cache_path.write_text(body, encoding="utf-8")

    soup = BeautifulSoup(body, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("tankathon_lottery: no table on page")
        return []

    out: list[dict] = []
    today = date.today().isoformat()
    seen_pos: set[int] = set()  # de-dup if Tankathon repeats a row
    rows = table.find_all("tr")
    for r in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        pos_raw = cells[0].strip()
        team_raw = cells[1].strip()
        # Odds columns, indexed from the END of the data row (see the
        # docstring's cell map): last = '#1 OVR', second-to-last = 'Top 6'.
        # Both are '' on playoff rows and on lottery-ineligible teams.
        odds_raw = cells[-1].strip() if len(cells) >= 2 else ""
        top6_raw = cells[-2].strip() if len(cells) >= 3 else ""
        if not pos_raw or not team_raw:
            continue
        # Team cell format: "LA Angels LAA" — the abbreviation is the
        # last all-caps token. Fall back to the raw string if not found.
        tokens = team_raw.split()
        team_code = None
        for tok in reversed(tokens):
            if re.fullmatch(r"[A-Z]{2,4}", tok):
                team_code = tok
                break
        team_code = canonical_org(team_code or team_raw) or team_code or team_raw
        if not team_code:
            continue
        # Parse pick position. Tankathon labels comp picks like "27a" /
        # "27b" — keep the numeric prefix as pick_pos and surface the
        # suffix in round_label.
        m_pos = re.match(r"(\d+)\s*([ab])?", pos_raw, re.IGNORECASE)
        if not m_pos:
            continue
        try:
            pos = int(m_pos.group(1))
        except ValueError:
            continue
        suffix = (m_pos.group(2) or "").upper()
        if pos in seen_pos and not suffix:
            continue
        seen_pos.add(pos)

        # Round label — top-30 are first round; comp picks get the
        # suffix; if a row's position is past 30 with no suffix it's the
        # start of round 2 (Tankathon's projection sometimes extends).
        if suffix:
            round_label = f"1{suffix}"
        elif pos <= 30:
            round_label = "1"
        else:
            round_label = "2"

        # Parse odds. Lottery-eligible rows carry a real %; playoff rows and
        # ineligible teams have a dash or blank and we store None (NOT 0.0:
        # "no published chance" and "a published 0%" are different claims).
        odds = _parse_pct_cell(odds_raw)
        top6 = _parse_pct_cell(top6_raw)
        wins, losses = _parse_record_cell(cells)

        out.append({
            "draft_year":    year,
            "team":          team_code,
            "pick_pos":      pos,
            "odds_pct":      odds,
            "odds_top6_pct": top6,
            "wins":          wins,
            "losses":        losses,
            "round_label":   round_label,
            "snapshot_date": today,
            "source":        "tankathon",
        })

    # Competitive Balance picks live OUTSIDE the main projected-order
    # table as a sidebar widget. Each row reads `{pos} | {team name} |
    # Competitive Balance`. The 12 comp picks split 6+6 into Round A
    # (after round 1, real MLB pick_pos 31-36) and Round B (after round
    # 2, real pick_pos ~37-42 by this site's convention; MLB places
    # Round B after round 2 around pick 66 but Tankathon collapses
    # both into a single block).
    # We renumber the comp picks 31, 32, ... so they don't collide on
    # the (draft_year, team, pick_pos) primary key with the regular
    # first-round picks above. The first 6 get round_label "1A", the
    # next 6 get "1B".
    comp_els = soup.find_all(string=lambda s: s and "Competitive Balance" in s)
    seen_comp = set()  # de-dup if Tankathon ever repeats a row
    comp_rows: list[dict] = []
    for el in comp_els:
        parent = el.parent.parent if el.parent and el.parent.parent else None
        if parent is None:
            continue
        texts = [s.strip() for s in parent.stripped_strings]
        if len(texts) < 3 or texts[-1] != "Competitive Balance":
            continue
        try:
            site_pos = int(texts[0])
        except ValueError:
            continue
        team_name = texts[1]
        key = (site_pos, team_name)
        if key in seen_comp:
            continue
        seen_comp.add(key)
        # Resolve team code from the team name (Tankathon shows the
        # short label here, e.g., "NY Mets", "Cleveland"). Use
        # canonical_org as the lookup which understands common variants.
        team_code = canonical_org(team_name) or team_name
        comp_rows.append({"site_pos": site_pos, "team_code": team_code})

    # Renumber: first 6 → pick_pos 31-36 (Round A); next 6 → 37-42 (B).
    for i, r in enumerate(comp_rows):
        new_pos = 31 + i
        out.append({
            "draft_year":    year,
            "team":          r["team_code"],
            "pick_pos":      new_pos,
            "odds_pct":      None,
            # Comp picks are a SIDEBAR widget with no standings columns, and
            # their pick_pos is a synthetic renumbering (31-42) that does not
            # correspond to a real draft slot. Everything standings-derived
            # stays None so no consumer can average them into a real number.
            "odds_top6_pct": None,
            "wins":          None,
            "losses":        None,
            "round_label":   "1A" if i < 6 else "1B",
            "snapshot_date": today,
            "source":        "tankathon",
        })

    n_lottery = sum(1 for r in out if r["odds_pct"] is not None)
    n_top6 = sum(1 for r in out if r.get("odds_top6_pct") is not None)
    n_rec = sum(1 for r in out if r.get("wins") is not None)
    n_comp = sum(1 for r in out if r["round_label"] in {"1A", "1B"})
    log.info("tankathon_lottery (draft %d): %d projected picks (%d with #1 odds, "
             "%d with top-6 odds, %d with W-L, %d comp)",
             year, len(out), n_lottery, n_top6, n_rec, n_comp)
    return out


# --- MLB Draft bonus pool articles ----------------------------------------
# Each year MLB.com publishes an article enumerating every team's draft
# bonus pool + every numbered pick's slot value. URL slug varies by year
# (the article author + editorial conventions shifted between 2021 and
# 2026), so we keep a per-year URL table rather than templating.
#
# Content format also shifts:
#   * 2024-2026 use structured "Bonus pools by team" + "First Round"
#     Markdown blocks with one "<team>: $<amount>" line per entry. Both
#     team pools and per-pick values are reliably parseable.
#   * 2022-2023 use inline prose ("the Tigers ($14,253,800), Rangers
#     ($12,641,000), ...") — partial coverage of the top ~10-12 teams
#     by pool size. Pick values are surfaced in a separate prose block
#     that's harder to parse.
#   * 2021 is prose-only with even fewer enumerated teams.
#
# The scraper handles all three shapes: structured headings first,
# inline-prose pattern as a fallback. Years where only partial data is
# available log how many teams + picks landed so the caller can decide
# what to do with the gaps.

_MLB_DRAFT_POOL_URLS: dict[int, str] = {
    2021: "https://www.mlb.com/news/2021-mlb-draft-bonus-slots",
    2022: "https://www.mlb.com/news/mlb-draft-2022-bonus-pools-pick-values",
    2023: "https://www.mlb.com/news/mlb-draft-2023-bonus-pools-pick-values",
    2024: "https://www.mlb.com/news/mlb-draft-2024-bonus-pick-values",
    2025: "https://www.mlb.com/news/mlb-draft-2025-bonus-pick-values",
    2026: "https://www.mlb.com/news/mlb-draft-2026-bonus-pool-pick-values",
}


def _parse_structured_team_pools(body: str) -> dict[str, int]:
    """Parse a structured team-pool list. MLB.com uses several heading
    variants across years:
        * "**Bonus pools by team**"  (2024, 2025)
        * "**Bonus pools by club:**" (2023)
        * "**Bonus pools**"          (2026)
    All appear as Markdown headings wrapped in `**...**` in the article
    body, so a regex anchored on the `**` form skips identically-worded
    navigation links elsewhere on the page. Parses the following
    "<TeamShortName>: $<amount>" lines until the next `**` subheading.
    Returns {team_name: usd}."""
    pattern = re.compile(r'\*\*Bonus pool[s]?(?:[^*]*?)\*\*')
    pools: dict[str, int] = {}
    for hm in pattern.finditer(body):
        section_start = hm.end()
        end = body.find("**", section_start)
        section = body[section_start:end if end > 0 else section_start + 5000]
        for m in re.finditer(r'([A-Z][A-Za-z\.\- ]+?):\s*\$([0-9,]+)', section):
            name = m.group(1).strip()
            if len(name) > 25 or len(name) < 3:
                continue
            try:
                amount = int(m.group(2).replace(",", ""))
            except ValueError:
                continue
            pools[name] = amount
        if pools:
            return pools
    return {}


def _parse_inline_team_pools(body: str) -> dict[str, int]:
    """Parse inline-prose pool mentions for older-format articles. Looks
    for patterns like "Pirates ($14,394,000)" or "the Tigers
    ($14,253,800)". Partial coverage (only the teams the prose explicitly
    enumerates), but better than nothing for 2021-2023."""
    pools: dict[str, int] = {}
    for m in re.finditer(r'([A-Z][A-Za-z\.\- ]{2,20})\s*\(\$([0-9,]+)\)', body):
        name = m.group(1).strip()
        try:
            amount = int(m.group(2).replace(",", ""))
        except ValueError:
            continue
        # Filter likely-non-team strings.
        if any(t in name.lower() for t in ("pick", "round", "season", "draft", "year", "lottery", "incentive")):
            continue
        if amount < 500_000 or amount > 30_000_000:
            continue
        pools[name] = amount
    return pools


def _parse_structured_pick_values(body: str) -> list[dict]:
    r"""Parse per-pick lines from the structured 2024+ format. Each pick
    appears as "N\. <Team>: $<amount>" (the backslash-escape in front of
    the period is a Markdown artifact)."""
    picks: list[dict] = []
    pattern = re.compile(
        r'(\d{1,3})\\?\.\s*([A-Z][A-Za-z\.\- ]+?):\s*\$([0-9,]+)'
    )
    for m in pattern.finditer(body):
        try:
            pick_overall = int(m.group(1))
        except ValueError:
            continue
        if pick_overall < 1 or pick_overall > 700:
            continue
        name = m.group(2).strip()
        if len(name) > 25:
            continue
        try:
            amount = int(m.group(3).replace(",", ""))
        except ValueError:
            continue
        picks.append({
            "pick_overall": pick_overall,
            "slot_usd":     amount,
            "team":         name,
        })
    # Dedup duplicates that can arise from the same pick being mentioned
    # twice in adjacent sub-sections — keep the FIRST occurrence.
    seen = set()
    out: list[dict] = []
    for p in picks:
        if p["pick_overall"] in seen:
            continue
        seen.add(p["pick_overall"])
        out.append(p)
    return out


def scrape_mlb_draft_pool(year: int, force: bool = False) -> dict:
    """Fetch + parse one year's MLB.com draft bonus-pool article.

    Returns:
        {
          "year":        int,
          "team_pools":  {team_short_name: usd, ...},
          "pick_values": [{pick_overall, slot_usd, team}, ...],
        }
    Returns an empty dict on fetch failure AND on a parse that yielded
    nothing at all. Returns a partial result when the article is in the
    inline-prose format (older years) - the caller can check
    len(team_pools) to gauge coverage.

    TRUTHY-EMPTY FIX (2026-08-05). This used to return
    `{"year": y, "team_pools": {}, "pick_values": []}` on a total parse
    miss. That dict is TRUTHY, so `build_draft_pools`' `if not data:
    continue` guard never fired, and the year was published as
    "0 bonus pools, 0 slot values" - a club with no draft budget - rather
    than as "we could not read this article". It logged at info, so
    nothing looked wrong. Measured on the served cache: 2021 parses 9 team
    pools and 0 pick values (21 clubs read as having no bonus pool at all)
    and 2022 parses 30 and 0. A wholly-failed parse now returns {} so the
    caller skips the year, and partial coverage warns instead of informs.
    """
    url = _MLB_DRAFT_POOL_URLS.get(year)
    if not url:
        log.warning("mlb_draft_pool: no URL on file for %d", year)
        return {}
    cache_key = f"mlb_draft_pool_{year}"
    fr = _fetch(url, cache_key, force=force)
    if fr.status != 200 or not fr.body:
        log.warning("mlb_draft_pool %d: fetch failed (status=%d)", year, fr.status)
        return {}
    body = fr.body
    # Structured-format parse first; fall back to inline prose.
    team_pools = _parse_structured_team_pools(body)
    if not team_pools:
        team_pools = _parse_inline_team_pools(body)
    pick_values = _parse_structured_pick_values(body)
    if not team_pools and not pick_values:
        log.error("mlb_draft_pool %d: article fetched OK (%d bytes) but parsed "
                  "0 team pools and 0 pick values - the page format most likely "
                  "changed; skipping the year rather than publishing it as a "
                  "class with no bonus money", year, len(body))
        return {}
    log.info("mlb_draft_pool %d: %d team pools, %d pick values",
             year, len(team_pools), len(pick_values))
    # Partial coverage is a real state for the 2021-2023 prose articles, but it
    # is also what a silently-broken parser looks like, so it must be visible.
    if len(team_pools) < 30:
        log.warning("mlb_draft_pool %d: only %d of 30 clubs resolved a bonus "
                    "pool - the remaining %d publish with no pool",
                    year, len(team_pools), 30 - len(team_pools))
    if not pick_values:
        log.warning("mlb_draft_pool %d: 0 pick slot values parsed - every pick "
                    "in this class publishes without a slot", year)
    return {"year": year, "team_pools": team_pools, "pick_values": pick_values}


# Short-name overrides for team strings the MLB.com articles use that
# canonical_org() doesn't recognize on its own. Currently the only
# stragglers: "D-backs" (2022 article uses the dash-prefixed short
# form instead of "Diamondbacks"). Add new entries here as future
# articles surface different formatting.
_DRAFT_POOL_NAME_OVERRIDES: dict[str, str] = {
    "D-backs": "ARI",
}


def build_draft_pools(years, force: bool = False) -> dict:
    """Aggregate per-year draft pools into the canonical-key layout the
    frontend expects:

        {
          year: {
            "team_pools":  {ORG: usd, ...},     # ORG = canonical 3-letter
            "pick_values": [{pick_overall, slot_usd, team}, ...],
          },
          ...
        }

    Team names from the article are canonicalized through `canonical_org`
    (with a few short-name overrides). Years where no pools could be
    parsed are skipped, with a warning - an absent year is honest, a year
    present with an empty pool map reads downstream as "these clubs had no
    bonus money". Caller logs the years actually on file.
    """
    from trades import canonical_org
    out: dict[int, dict] = {}
    for year in years:
        data = scrape_mlb_draft_pool(year, force=force)
        if not data:
            continue
        canonical_pools: dict[str, int] = {}
        n_pool_dropped = 0
        for raw, usd in (data.get("team_pools") or {}).items():
            code = _DRAFT_POOL_NAME_OVERRIDES.get(raw) or canonical_org(raw)
            if not code or len(code) > 4:
                n_pool_dropped += 1
                continue
            canonical_pools[code] = usd
        canonical_picks: list[dict] = []
        for pv in (data.get("pick_values") or []):
            raw = pv.get("team")
            code = _DRAFT_POOL_NAME_OVERRIDES.get(raw) or (canonical_org(raw) if raw else None)
            canonical_picks.append({
                "pick_overall": pv.get("pick_overall"),
                "slot_usd":     pv.get("slot_usd"),
                "team":         code or raw,
            })
        if n_pool_dropped:
            log.warning("draft_pools %d: %d parsed pool row(s) did not "
                        "canonicalize to an org code and were dropped",
                        year, n_pool_dropped)
        if not canonical_pools and not canonical_picks:
            # Same reasoning as the parser guard: an empty-but-present year is
            # indistinguishable downstream from a real zero. Leave the year off.
            log.warning("draft_pools %d: nothing survived canonicalization - "
                        "omitting the year entirely rather than serving it as a "
                        "class with no bonus pools", year)
            continue
        out[year] = {
            "team_pools":  canonical_pools,
            "pick_values": canonical_picks,
        }
    return out


# ===========================================================================
# Tier C — Manual CSV ingest
# ===========================================================================
#
# For sources that can't be reliably scraped — ESPN (React + paywall),
# MLB Pipeline (React), The Athletic (paywall + dynamic), and as a
# fallback for any Tier B parser that fails — read from a CSV the user
# maintains by hand.
#
# CSV columns:
#   source, snapshot_date, interval_label, player_name, position, org,
#   rank, fv, status
#
# Example row:
#   espn,2026-01-27,ESPN 2026 Preseason,Konnor Griffin,SS/OF,PIT,1,65,active
#
# Realistic update workflow: every couple of weeks, the user spends
# ~10 minutes copy-pasting a new list into the CSV. This is how every
# manual prospect aggregator that exists actually works.
# ---------------------------------------------------------------------------

def load_manual_rankings(csv_path: Path = MANUAL_CSV) -> tuple[list[Snapshot], dict[str, str]]:
    """
    Read the manual rankings CSV.

    Returns:
      (snapshots, birth_dates) where
        snapshots is the list of Snapshot rows, and
        birth_dates is {player_key: 'YYYY-MM-DD'} for any rows that
        included a birth_date column. Most CSV rows won't (it's an
        optional column); we keep the first non-empty value seen per
        player and ignore the rest.
    """
    if not csv_path.exists():
        log.info("manual_rankings: no CSV at %s (this is fine)", csv_path)
        return [], {}
    rows: list[Snapshot] = []
    birth_dates: dict[str, str] = {}
    # Try UTF-8 first; fall back to latin-1 (common Windows export encoding).
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with csv_path.open(encoding=enc) as _probe:
                _probe.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        enc = "latin-1"  # last resort
    with csv_path.open(encoding=enc) as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader, start=2):  # start=2 to match line numbers
            try:
                name = (r.get("player_name") or "").strip()
                if not name:
                    continue
                name = fix_mojibake(name)
                rank = r.get("rank", "").strip()
                fv_raw = r.get("fv", "").strip()
                key = normalize_key(name)
                # Optional birth_date column. Format: YYYY-MM-DD.
                bd = (r.get("birth_date") or "").strip()
                if bd and key not in birth_dates:
                    birth_dates[key] = bd
                # Optional 20-80 tool grade columns. Empty cells stay
                # absent — sources that don't publish a given tool simply
                # omit the column value. Anything outside [20,80] is
                # treated as a typo and skipped (not clamped) so the user
                # notices the error.
                tools = _parse_csv_tools(r, line_no=i)
                fv_val, fv_has_plus = _parse_fv_full(fv_raw)
                rows.append(Snapshot(
                    source=(r.get("source") or "manual").strip(),
                    snapshot_date=(r.get("snapshot_date") or "").strip(),
                    interval_label=(r.get("interval_label") or "Manual").strip(),
                    player_key=key,
                    player_name=name,
                    position=(r.get("position") or "").strip() or None,
                    org=(r.get("org") or "").strip() or None,
                    rank=int(rank) if rank else None,
                    fv=fv_val,
                    status=(r.get("status") or "active").strip(),
                    tools=tools,
                    fv_plus=fv_has_plus,
                ))
            except (ValueError, KeyError) as e:
                log.warning("manual_rankings line %d: %s", i, e)
                continue
    log.info("manual_rankings: %d rows, %d with birth dates",
             len(rows), len(birth_dates))
    return rows, birth_dates


# ===========================================================================
# Orchestration & diagnostic probe
# ===========================================================================

def scrape_all(force: bool = False) -> tuple[list[Snapshot], dict[str, str]]:
    """
    Run enabled scrapers, log a summary, return (snapshots, birth_dates).

    Active sources:
      - ESPN (Tier B, HTML scraping, Kiley McDaniel's Top 100)
      - Just Baseball (Tier B, HTML scraping)
      - MLB Pipeline (Tier B, archived /milb/prospects/<year>/top100/)
      - Manual CSV (Tier C, user-maintained) — FanGraphs, TJStats, others

    Snapshots come from all sources. birth_dates come only from the manual
    CSV (Tier C) — automated scrapers don't surface DOB. The bulk
    PlayerIndex resolve in run_monthly (stats.bulk_resolve_ids) fills in
    the rest from the MLB Stats API people-index payload.
    """
    snapshots: list[Snapshot] = []
    counts: dict[str, int] = {}

    # Tier B: ESPN (Kiley McDaniel Top 100, server-rendered HTML)
    for url, label, snap in ESPN_INTERVALS:
        try:
            got = scrape_espn_top100(url, label, snap, force=force)
            snapshots.extend(got)
            counts[label] = len(got)
        except Exception as e:
            log.exception("espn %s crashed: %s", label, e)
            counts[label] = -1

    # Tier B: Just Baseball
    for url, label, snap in JB_INTERVALS:
        try:
            got = scrape_just_baseball(url, label, snap, force=force)
            snapshots.extend(got)
            counts[label] = len(got)
        except Exception as e:
            log.exception("just_baseball %s crashed: %s", label, e)
            counts[label] = -1

    # Tier B: MLB Pipeline (archived top-100 pages, one per year)
    for url, label, snap, year in MLB_PIPELINE_INTERVALS:
        try:
            got = scrape_mlb_pipeline(url, label, snap, year, force=force)
            snapshots.extend(got)
            counts[label] = len(got)
        except Exception as e:
            log.exception("mlb_pipeline %s crashed: %s", label, e)
            counts[label] = -1

    # Tier B: MLB Pipeline per-org top-30 lists. Reuses the same Apollo
    # walker as the Top-100; expands coverage from ~600 to ~2100 Pipeline
    # snapshots, dramatically increasing multi-source consensus overlap.
    # ~60 fetches first run (rate-limited by RATE_LIMIT_SECONDS in _fetch);
    # subsequent runs are cache-hits.
    org_total = 0
    org_with_tools = 0
    for url, label, snap, year, cache_key in MLB_PIPELINE_ORG_INTERVALS:
        try:
            got = scrape_mlb_pipeline(url, label, snap, year,
                                       force=force, cache_key=cache_key)
            snapshots.extend(got)
            org_total += len(got)
            org_with_tools += sum(1 for s in got if s.tools)
        except Exception as e:
            log.exception("mlb_pipeline org %s crashed: %s", label, e)
    counts["mlb_pipeline_orgs"] = org_total
    log.info("mlb_pipeline org pages: %d snapshots across %d (org, year) pairs, %d with tools",
             org_total, len(MLB_PIPELINE_ORG_INTERVALS), org_with_tools)

    # Tier B: MLB Pipeline international class. Org is merged later from
    # resolved affiliate rosters so only signed/assigned players surface
    # on a team page.
    for url, label, snap, year in MLB_INTERNATIONAL_INTERVALS:
        try:
            # snap is None for the rolling permalink -> the stable-date wrapper
            # resolves it (holds the stored date unless the board changed).
            got = (scrape_mlb_international_stable(url, label, year, force=force)
                   if snap is None else
                   scrape_mlb_international(url, label, snap, year, force=force))
            snapshots.extend(got)
            counts[label] = len(got)
        except Exception as e:
            log.exception("mlb_international %s crashed: %s", label, e)
            counts[label] = -1

    # Tier C: Manual CSV (FanGraphs, ESPN, TJStats, MLB Pipeline, etc.)
    csv_birth_dates: dict[str, str] = {}
    try:
        manual, csv_birth_dates = load_manual_rankings()
        snapshots.extend(manual)
        counts["manual_csv"] = len(manual)
    except Exception as e:
        log.exception("manual ingest crashed: %s", e)
        counts["manual_csv"] = -1

    # Summary
    log.info("=" * 60)
    log.info("SCRAPE SUMMARY")
    log.info("=" * 60)
    for label, n in counts.items():
        marker = "[OK]" if n > 0 else ("[CRASH]" if n < 0 else "[empty]")
        log.info("  %-30s %s (%d)", label, marker, n)
    log.info("=" * 60)
    log.info("Total snapshots: %d", len(snapshots))
    log.info("CSV birth dates: %d", len(csv_birth_dates))
    return snapshots, csv_birth_dates


def probe(force: bool = False) -> None:
    """
    Hit enabled sources and print a diagnostic summary. No DB writes.

    Use this to find out exactly which sources work in your environment:
        python run_monthly.py --dry-run
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print()
    print("Probing enabled sources (no DB writes)...")
    print("-" * 70)

    # Tier B — ESPN
    for url, label, snap in ESPN_INTERVALS:
        print(f"\n[ESPN] {label}")
        print(f"  URL: {url}")
        got = scrape_espn_top100(url, label, snap, force=force)
        print(f"  Parser found: {len(got)} players")
        if got:
            top = got[0]
            print(f"  Sample: {top.player_name} (rank {top.rank}, fv {top.fv}, org {top.org})")

    # Tier B - Just Baseball. JB_INTERVALS holds only fixed-date ARCHIVE
    # urls (normally empty); the live board rides the rolling permalink, so
    # probe both.
    for url, label, snap in list(JB_INTERVALS) + [
            (JB_ROLLING_URL, f"{JB_LIVE_LABEL_PREFIX} (rolling)",
             date.today().isoformat())]:
        print(f"\n[Just Baseball] {label}")
        print(f"  URL: {url}")
        cache_key = "probe_" + re.sub(r"[^a-z0-9]+", "_", label.lower())
        fr = _fetch(url, cache_key, force=force)
        print(f"  HTTP {fr.status} · {fr.bytes} bytes · cached={fr.from_cache}")
        if fr.status == 200 and fr.bytes > 1000:
            num_digits_dot = len(re.findall(r"\b[1-9]\d?\.\s+[A-Z]", fr.body))
            num_table_rows = fr.body.count("<tr")
            print(f"  Numeric '<n>. <Name>' patterns: {num_digits_dot}")
            print(f"  <tr> elements: {num_table_rows}")
            got = scrape_just_baseball(url, label, snap, force=False)
            print(f"  Parser found: {len(got)} players")
            if got:
                print(f"  Sample: {got[0].player_name} (rank {got[0].rank}, fv {got[0].fv})")
        else:
            print(f"  FAIL: HTTP {fr.status}")

    # Tier B — MLB Pipeline (per-year archived top 100)
    for url, label, snap, year in MLB_PIPELINE_INTERVALS:
        print(f"\n[MLB Pipeline] {label}")
        print(f"  URL: {url}")
        got = scrape_mlb_pipeline(url, label, snap, year, force=force)
        print(f"  Parser found: {len(got)} players")
        if got:
            top = got[0]
            print(f"  Sample: {top.player_name} (rank {top.rank}, fv {top.fv}, org {top.org})")

    # Tier B — MLB Pipeline international rankings
    for url, label, snap, year in MLB_INTERNATIONAL_INTERVALS:
        print(f"\n[MLB Pipeline International] {label}")
        print(f"  URL: {url}")
        got = (scrape_mlb_international_stable(url, label, year, force=force)
               if snap is None else
               scrape_mlb_international(url, label, snap, year, force=force))
        print(f"  Parser found: {len(got)} players")
        if got:
            top = got[0]
            print(f"  Sample: {top.player_name} (rank {top.rank}, org {top.org})")

    # Tier C: Manual CSV
    print(f"\n[Manual CSV] manual_rankings.csv")
    print(f"  Path: {MANUAL_CSV}")
    if MANUAL_CSV.exists():
        rows, birth_dates = load_manual_rankings()
        print(f"  Loaded {len(rows)} rows · {len(birth_dates)} with birth dates")
        if rows:
            sources = sorted(set(r.source for r in rows))
            print(f"  Sources represented: {sources}")
    else:
        print(f"  No CSV present. Create one with these columns:")
        print(f"    source,snapshot_date,interval_label,player_name,position,org,rank,fv,status[,birth_date]")

    print("\n" + "-" * 70)
    print("Probe complete.")
    print()


def snapshots_to_records(snapshots: Iterable[Snapshot]) -> list[dict]:
    return [asdict(s) for s in snapshots]
