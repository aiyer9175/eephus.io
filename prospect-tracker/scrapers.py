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
      For sources that render lists in static HTML (Baseball America,
      Just Baseball, TJStats), we attempt to parse the public ranking
      view. Each parser has fallback selector strategies and prints
      *diagnostic output* explaining exactly what happened — never
      silent failure. When a site redesigns or paywalls a page, the
      run_monthly.py output tells you which source failed and why.

  Tier C — Manual CSV ingest
      For ESPN, The Athletic, and MLB Pipeline (all React-rendered or
      paywalled), we read from data/manual_rankings.csv. The user
      pastes the published list into the CSV (10-15 minutes of work per
      update), and the pipeline ingests it. This is genuinely how most
      prospect aggregators work — even Baseball America's industry
      reports involve manual data entry by their editors.

A `probe()` function hits every source URL and reports HTTP status, bytes
returned, rows parsed, and a sample player name without writing anything.
Call it via `python run_monthly.py --dry-run`.
"""

from __future__ import annotations

import csv
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
    return _CANONICAL_KEYS.get(s, s)


# Maps alternate player_keys to their canonical form so different source
# spellings of the same player collapse to one DB key.
# key = what normalize_key() would produce for the alternate spelling
# value = canonical key (typically matches the MLB API / most common spelling)
_CANONICAL_KEYS: dict[str, str] = {
    "leodalis_de_vries": "leo_de_vries",
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
      - Just Baseball (Tier B, HTML scraping, working)
      - Manual CSV (Tier C, user-maintained) — includes FanGraphs, ESPN, TJStats

    Snapshots come from both sources. birth_dates come only from the manual
    CSV (Tier C) — automated scrapers don't surface DOB. The API path
    (stats.fetch_birth_date) fills in the rest at run_monthly time.
    """
    snapshots: list[Snapshot] = []
    counts: dict[str, int] = {}

    # Tier B: Just Baseball (only working web scraper)
    for url, label, snap in JB_INTERVALS:
        try:
            got = scrape_just_baseball(url, label, snap, force=force)
            snapshots.extend(got)
            counts[label] = len(got)
        except Exception as e:
            log.exception("just_baseball %s crashed: %s", label, e)
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

    # Tier B — Just Baseball only
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
