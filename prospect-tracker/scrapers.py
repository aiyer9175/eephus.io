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
from dataclasses import dataclass, asdict
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
    status: str  # active | graduated | injured_list | off_list
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


# Tool taxonomy — canonical keys used everywhere downstream (consensus,
# storage, UI). Sources map their own labels onto these via the
# per-scraper translation tables (e.g. PIPELINE_TOOL_KEY below).
# pitch_sel and bat_ctrl are FG-published 20-80 grades treated as
# first-class hitter tools so they aggregate cross-source and feed
# composite_off / Tools+ rather than living in _extras.
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
# key = what normalize_key() would produce for the alternate spelling
# value = canonical key (typically matches the MLB API / most common spelling)
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
}


def _parse_fv(raw) -> float | None:
    """Accepts '70', '55+', '50/55' (PV/FV), 70 (int/float). Returns float."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    raw = str(raw).strip()
    if not raw:
        return None
    if "/" in raw:  # PV/FV format
        raw = raw.split("/")[-1].strip()
    if raw.endswith("+"):
        try:
            return float(raw[:-1]) + 2.5
        except ValueError:
            return None
    try:
        return float(raw)
    except ValueError:
        return None


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


def _fetch(url: str, cache_key: str, force: bool = False,
           accept_json: bool = False) -> FetchResult:
    """Fetch a URL with on-disk caching and rate limiting."""
    cache_path = CACHE_DIR / f"{cache_key}.{'json' if accept_json else 'html'}"
    if cache_path.exists() and not force:
        body = cache_path.read_text(encoding="utf-8")
        log.info("cache hit: %s (%d bytes)", cache_key, len(body))
        return FetchResult(body=body, status=200, from_cache=True, url=url)

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
]


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
    # complicate _fetch's signature.
    if cache_path.exists() and not force:
        body = cache_path.read_text(encoding="utf-8")
        log.info("cache hit: %s (%d bytes)", cache_key, len(body))
        fr = FetchResult(body=body, status=200, from_cache=True, url=url)
    else:
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
        rows.append(Snapshot(
            source="espn", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=pos, org=org, rank=rank, fv=current_fv,
            status="active", tools=tools,
        ))

    log.info("espn %s -> %d players%s", label, len(rows),
             " (TIER B working)" if rows else " (TIER B FAILED — selectors stale)")
    return rows


# --- Just Baseball --------------------------------------------------------
# JB renders prospects as <h2> or <h3> blocks. Each starts with "<rank>. <Name>"
# and the FV grade appears in the following paragraph as "Future Value: 55".
# Per-player tool grades live in a <figure class="wp-block-table"> table
# immediately after the heading. Header row carries column labels (variable
# per pitcher — Sweeper vs Slider, Splitter vs Changeup), value row carries
# present/future grade pairs. We always take the FUTURE grade.

JB_INTERVALS = [
    ("https://www.justbaseball.com/prospects/top-100-mlb-prospects/",
     "JB 2026 Preseason", "2026-03-04"),
]

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


def _parse_jb_tool_table(table_html) -> tuple[dict[str, float] | None, float | None]:
    """Parse one JB wp-block-table into (tools_dict, fv).

    Header row → labels (lowercased, stripped). Value row → "pres/fut"
    grade pairs (or singletons). For each (header, value) pair we map
    header to canonical key via JB_TOOL_KEY and keep the future grade
    if it parses to a valid 20-80 number. The FV column is returned
    separately (parsed as singleton, may carry "+" suffix).
    """
    if table_html is None:
        return None, None
    if isinstance(table_html, str):
        sub = BeautifulSoup(table_html, "html.parser")
        table = sub.find("table")
    else:
        table = table_html if getattr(table_html, "name", None) == "table" else table_html.find("table")
    if not table:
        return None, None
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None, None
    headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    values = [c.get_text(" ", strip=True) for c in rows[1].find_all(["td", "th"])]
    if not headers or len(values) < len(headers):
        return None, None
    tools: dict[str, float] = {}
    fv: float | None = None
    for hdr, raw in zip(headers, values):
        hdr_norm = hdr.strip().rstrip(".").rstrip()
        if hdr_norm in ("fv", "f.v.", "future value"):
            fv = _parse_fv(raw)
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
    return (tools or None), fv


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
        table = section.find("table")
        if table:
            tools, fv = _parse_jb_tool_table(table)
        # FV fallback — prose-style "Future Value: 55" if it ever returns.
        if fv is None:
            sect_text = section.get_text(" ", strip=True)
            fv_m = re.search(r"(?:Future Value|F\.V\.)[:\s]+([0-9]+\+?)", sect_text)
            if fv_m:
                fv = _parse_fv(fv_m.group(1))
        if tools:
            n_with_tools += 1
        rows.append(Snapshot(
            source="just_baseball", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=position, org=org, rank=rank, fv=fv, status="active",
            tools=tools,
        ))
    log.info("just_baseball %s -> %d players (%d with tools)%s", label, len(rows), n_with_tools,
             " (TIER B working)" if rows else " (TIER B FAILED — selectors stale)")
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
    for y in (2021, 2022, 2023, 2024, 2025, 2026)
]

MLB_INTERNATIONAL_INTERVALS = [
    ("https://www.mlb.com/milb/prospects/international/",
     "MLB Pipeline 2026 International",
     date.today().isoformat(),
     2026)
]


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
    "yankees", "red-sox", "blue-jays", "orioles", "rays",
    "white-sox", "guardians", "tigers", "royals", "twins",
    "astros", "athletics", "angels", "mariners", "rangers",
    # NL East / Central / West
    "braves", "marlins", "mets", "phillies", "nationals",
    "cubs", "reds", "brewers", "pirates", "cardinals",
    "diamondbacks", "rockies", "dodgers", "padres", "giants",
)
MLB_PIPELINE_ORG_YEARS = (2025, 2026)

MLB_PIPELINE_ORG_INTERVALS = [
    (f"https://www.mlb.com/prospects/{y}/{slug}",
     f"MLB Pipeline {y} {slug.replace('-', ' ').title()} Top 30",
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
    if cache_path.exists() and not force:
        body = cache_path.read_text(encoding="utf-8")
        log.info("cache hit: %s (%d bytes)", cache_key, len(body))
    else:
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
                m2 = re.search(r'Overall:\s*(\d+)', bio.group(1))
                if m2:
                    overall = float(m2.group(1))
                    bio_text = bio.group(1)
                    break
        # Fallback: any bio with an Overall grade line.
        if overall is None:
            for bio in bios:
                m2 = re.search(r'Overall:\s*(\d+)', bio.group(1))
                if m2:
                    overall = float(m2.group(1))
                    bio_text = bio.group(1)
                    break

        # Tool grades — the Scouting grades line carries tool grades
        # ahead of the Overall: token. Parse each "Name: NN" pair and
        # map onto our canonical tool keys (Run → speed, Power →
        # game_pwr, etc.). The full line varies in length by source
        # snapshot; we don't require every tool, just take what's there.
        tools = _parse_pipeline_tools(bio_text) if bio_text else None

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
             " (TIER B working)" if rows else " (TIER B FAILED — selectors stale)")
    return rows


def scrape_mlb_international(url: str, label: str, snap_date: str, year: int,
                             force: bool = False) -> list[Snapshot]:
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
        if not org:
            # The IFA merge is intentionally stateside/affiliate-aware:
            # players without a current roster assignment stay out until
            # MLB exposes a team for them.
            continue
        overall = None
        overall_m = re.search(r'Overall:\s*(\d+)', chunk)
        if overall_m:
            overall = float(overall_m.group(1))
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
    Returns an empty dict on fetch failure. Returns a partial result
    when the article is in the inline-prose format (older years) — the
    caller can check len(team_pools) to gauge coverage.
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
    log.info("mlb_draft_pool %d: %d team pools, %d pick values",
             year, len(team_pools), len(pick_values))
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
    parsed are silently skipped — caller logs the years actually on file.
    """
    from trades import canonical_org
    out: dict[int, dict] = {}
    for year in years:
        data = scrape_mlb_draft_pool(year, force=force)
        if not data:
            continue
        canonical_pools: dict[str, int] = {}
        for raw, usd in (data.get("team_pools") or {}).items():
            code = _DRAFT_POOL_NAME_OVERRIDES.get(raw) or canonical_org(raw)
            if not code or len(code) > 4:
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
            csv_path.open(encoding=enc).read()
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
                rows.append(Snapshot(
                    source=(r.get("source") or "manual").strip(),
                    snapshot_date=(r.get("snapshot_date") or "").strip(),
                    interval_label=(r.get("interval_label") or "Manual").strip(),
                    player_key=key,
                    player_name=name,
                    position=(r.get("position") or "").strip() or None,
                    org=(r.get("org") or "").strip() or None,
                    rank=int(rank) if rank else None,
                    fv=_parse_fv(fv_raw),
                    status=(r.get("status") or "active").strip(),
                    tools=tools,
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
    CSV (Tier C) — automated scrapers don't surface DOB. The API path
    (stats.fetch_birth_date) fills in the rest at run_monthly time.
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
            got = scrape_mlb_international(url, label, snap, year, force=force)
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

    # Tier B — Just Baseball
    for url, label, snap in JB_INTERVALS:
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
        got = scrape_mlb_international(url, label, snap, year, force=force)
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
