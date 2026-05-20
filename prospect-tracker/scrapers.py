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
    # hit, game_pwr, raw_pwr, speed, field, throw (hitters)
    # fb, sl, cb, ch, cmd (pitchers). Missing tools stay absent so we
    # don't confuse "didn't publish" with "graded 0".
    tools: dict[str, float] | None = None


# Tool taxonomy — canonical keys used everywhere downstream (consensus,
# storage, UI). Sources map their own labels onto these via the
# per-scraper translation tables (e.g. PIPELINE_TOOL_KEY below).
HITTER_TOOL_KEYS = ("hit", "game_pwr", "raw_pwr", "speed", "field", "throw")
PITCHER_TOOL_KEYS = ("fb", "sl", "cb", "ch", "cmd")
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


def _parse_pipeline_tools(bio_text: str) -> dict[str, float] | None:
    """Pull tool grades from an MLB Pipeline bio's Scouting grades line.

    Format observed:
        Scouting grades: Hit: 55 | Power: 60 | Run: 45 | Arm: 50 |
        Field: 55 | Overall: 55
    The Overall: token is already parsed separately for FV; we ignore
    it here and capture every other "Label: NN" pair, mapping via
    PIPELINE_TOOL_KEY. Returns None when no tools were recognized.
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
    for label, val in re.findall(r'([A-Za-z][A-Za-z ]+?):\s*(\d+)', seg):
        key = PIPELINE_TOOL_KEY.get(label.strip().lower())
        if not key:
            continue
        try:
            grade = float(val)
        except ValueError:
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

    rows: list[Snapshot] = []
    current_fv: float | None = None
    seen_ranks: set[int] = set()

    for _, h in candidates:
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
        rows.append(Snapshot(
            source="espn", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=pos, org=org, rank=rank, fv=current_fv,
            status="active",
        ))

    log.info("espn %s -> %d players%s", label, len(rows),
             " (TIER B working)" if rows else " (TIER B FAILED — selectors stale)")
    return rows


# --- Just Baseball --------------------------------------------------------
# JB renders prospects as <h2> or <h3> blocks. Each starts with "<rank>. <Name>"
# and the FV grade appears in the following paragraph as "Future Value: 55".

JB_INTERVALS = [
    ("https://www.justbaseball.com/prospects/top-100-mlb-prospects/",
     "JB 2026 Preseason", "2026-03-04"),
]


def scrape_just_baseball(url: str, label: str, snap_date: str,
                         force: bool = False) -> list[Snapshot]:
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
    # Scan all heading levels — JB has used both h2 and h3 over time.
    for h in soup.find_all(["h2", "h3", "h4"]):
        text = h.get_text(" ", strip=True)
        # "100. Player Name" or "100. Player Name, OF, Yankees"
        m = re.match(r"^(\d{1,3})\.\s+([A-Z][\w'\-]+(?:\s+[A-Z][\w'\-\.]+)+)", text)
        if not m:
            continue
        rank = int(m.group(1))
        if not (1 <= rank <= 200):
            continue
        name = m.group(2).strip()
        if name in seen_names:
            continue
        seen_names.add(name)
        # Look for FV in next ~6 siblings
        fv = None
        cur = h
        for _ in range(8):
            cur = cur.find_next_sibling()
            if cur is None:
                break
            sib_text = cur.get_text(" ", strip=True) if hasattr(cur, "get_text") else str(cur)
            fv_m = re.search(r"(?:Future Value|FV|F\.V\.)[:\s]+([0-9]+\+?)", sib_text)
            if fv_m:
                fv = _parse_fv(fv_m.group(1))
                break
        rows.append(Snapshot(
            source="just_baseball", snapshot_date=snap_date, interval_label=label,
            player_key=normalize_key(name), player_name=name,
            position=None, org=None, rank=rank, fv=fv, status="active",
        ))
    log.info("just_baseball %s -> %d players%s", label, len(rows),
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
                        force: bool = False) -> list[Snapshot]:
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
            rank=rank,
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
                rank=rank,
                fv=None,
                status="active",
            ))
        i = max(j + 1, i + 1)

    log.info("mlb_international %s -> %d players", label, len(rows))
    return rows


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
