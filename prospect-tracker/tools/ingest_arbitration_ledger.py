# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""One-time arbitration ledger ingest from MLB Trade Rumors -> data/_labs/arb_ledger.json.

The ledger is a lab file: data/_labs/ ships in neither deploy consumer, so the
MLBTR entries are not republished at a public URL (owner answer M23-3, 2026-09-25).

WHY THIS IS NOT A SCRAPER IN THE PIPELINE
Arbitration settles once a year, in January. There is nothing to poll. This is a
hand-run, permanently-cached, resumable ingest, and a test asserts that nothing
reachable from run_monthly's import graph imports this module.

OPERATIONAL CONSTRAINT, MEASURED THE HARD WAY
During planning this IP was firewalled by MLBTR at the TCP level after roughly
14 rapid requests and stayed blocked for hours. A block presents as a connection
timeout, not an HTTP status, so a retry loop looks like a slow network and
quietly converts a soft block into a hard one. Hence:

  * MIN_DELAY 8s plus jitter, single-threaded, never parallel.
  * --max-requests defaults to 6 per invocation. Run it repeatedly; it resumes.
  * The cache is PERMANENT. No TTL. An already-downloaded page is never
    re-fetched without --force-url.
  * CIRCUIT BREAKER: the first non-200 or connection error aborts the whole
    batch. Continuing after a block is what makes the block permanent.
  * URL discovery reads a handful of index pages and then crawls links out of
    ALREADY-CACHED pages for free, rather than guessing slugs. Guessing spends
    the budget on 404s, which is how the planning block happened.

WHY THE LEDGER MATTERS
The panel's arb-step reconstruction currently fails its own maximum-cut meter at
7.02% against a <1.0% criterion, and 64% of its labels come from the weakest
source with no ground truth present at all. MLBTR prints real service time
("5.045") next to the settled figure, and its player links carry Baseball
Reference ids, which are the join key to .cache/war_daily and the only bbref ids
in this tree. So this ingest supplies the label, the arb step and the identity in
one pass.

USAGE
    python tools/ingest_arbitration_ledger.py discover      # index pages only
    python tools/ingest_arbitration_ledger.py fetch         # <=6 pages, resumes
    python tools/ingest_arbitration_ledger.py build         # parse cache -> ledger
    python tools/ingest_arbitration_ledger.py check         # offline re-parse
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "mlbtr"
LEDGER_PATH = ROOT / "data" / "_labs" / "arb_ledger.json"
URLS_PATH = ROOT / "data" / "arb_source_urls.json"

log = logging.getLogger("arb_ingest")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
MIN_DELAY = 8.0
JITTER = 4.0
DEFAULT_MAX_REQUESTS = 6
TIMEOUT = 30

# Set True only inside check(); every network entry point asserts on it.
_OFFLINE = False

INDEX_URLS = (
    "https://www.mlbtraderumors.com/arbitration-projection-model",
    "https://www.mlbtraderumors.com/arbitration-eligibles",
)

_ARB_URL_RE = re.compile(
    r"https?://(?:www\.)?mlbtraderumors\.com/(\d{4})/(\d{2})/"
    r"([^\"'?#]*arbitration[^\"'?#]*\.html)", re.I)

_BREF_RE = re.compile(r"baseball-reference\.com/players/\w/(\w+?\d{2})\.s?html", re.I)
_SERVICE_RE = re.compile(r"\((\d+)\.(\d{3})\)")
# MM / M / K all occur. 38 of the 2026 tracker's 191 entries use K, so a
# MM-only regex silently drops every minimum-salary settlement - which is the
# arb-1 population the panel is thinnest on.
_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*(MM|M|K)\b", re.I)

# Outcome vocabulary, read off the real 2026 tracker rather than guessed.
#
# ORDER MATTERS. `extension` must precede `agreed`, because a multi-year
# extension line reads "agreed to a five-year, $57.5MM extension" and would
# otherwise classify as a settlement. The 2026 tracker carries exactly this
# case (Maikel Garcia, 2.168, five-year $57.5MM signed in December): the
# tracker lists arbitration-ELIGIBLE players, and some of them sign extensions
# instead of settling. Letting one through would put a $11.5MM average annual
# extension value into the label set as though it were an arb-1 award.
_OUTCOME_PATTERNS = (
    ("extension", re.compile(r"\bextension\b|\byear,?\s*\$[\d.,]+\s*(?:MM|M)\b"
                             r"(?!.*\barbitration\b)", re.I)),
    ("club_option", re.compile(r"\bclub option\b|\bexercised\b", re.I)),
    ("split_deal", re.compile(r"\bsplit deal\b|\bsplit contract\b", re.I)),
    ("exchanged", re.compile(r"no agreement reached|did not reach agreement|"
                             r"head(?:ing|ed) (?:to|for) (?:a )?hearing|"
                             r"exchanged figures", re.I)),
    ("hearing_won", re.compile(r"won .{0,20}hearing|prevailed", re.I)),
    ("hearing_lost", re.compile(r"lost .{0,20}hearing", re.I)),
    ("nontendered", re.compile(r"non-?tender", re.I)),
    ("agreed", re.compile(r"\bagreement\b|\bagreed\b|\bsettled\b", re.I)),
)

# Club headings on a tracker page, closed set, each mapped to the club code
# trades.canonical_org gives the same name (test_arb_club_process.py pins the
# agreement). A tracker groups its entries as <p><strong>Club</strong></p>
# followed by one <ul>; every entry of the 2024, 2025 and 2026 pages sits in
# such a list (30 headings on each page).
#
# ATTRIBUTION RULE (owner ask 3, lane design finance_to_fa_arb section 2.4):
# a case belongs to the club under whose heading the tracker lists the player
# on exchange day, never to the season-end club in arb_history. Tarik Skubal's
# 2026 case is a Detroit case although arb_history credits his 2026 award to
# LAD, the club of his last 2026 stint.
TRACKER_CLUB_CODES = {
    "Angels": "LAA", "Astros": "HOU", "Athletics": "ATH", "Blue Jays": "TOR",
    "Braves": "ATL", "Brewers": "MIL", "Cardinals": "STL", "Cubs": "CHC",
    "Diamondbacks": "ARI", "D-backs": "ARI", "Dodgers": "LAD", "Giants": "SFG",
    "Guardians": "CLE", "Mariners": "SEA", "Marlins": "MIA", "Mets": "NYM",
    "Nationals": "WSN", "Orioles": "BAL", "Padres": "SDP", "Phillies": "PHI",
    "Pirates": "PIT", "Rangers": "TEX", "Rays": "TBR", "Red Sox": "BOS",
    "Reds": "CIN", "Rockies": "COL", "Royals": "KCR", "Tigers": "DET",
    "Twins": "MIN", "White Sox": "CHW", "Yankees": "NYY",
}


def _heading_text(tag) -> str | None:
    """The club name when `tag` is a tracker club heading, else None."""
    if tag is None or getattr(tag, "name", None) != "p":
        return None
    text = tag.get_text(" ", strip=True)
    return text if text in TRACKER_CLUB_CODES else None


def club_headings(soup) -> list[str]:
    """Every club heading on a tracker page, in page order."""
    return [t for t in (_heading_text(p) for p in soup.find_all("p")) if t]


def entry_club(el) -> tuple[str | None, str | None]:
    """(heading, club code) for one tracker entry, or (None, None).

    The entry's list must be the element right after a club heading. A looser
    rule (the nearest heading anywhere above) would credit a reader comment or
    a closing note to the last club on the page."""
    ul = el.find_parent("ul") if el.name == "li" else None
    head = _heading_text(ul.find_previous_sibling() if ul is not None else None)
    return (head, TRACKER_CLUB_CODES[head]) if head else (None, None)


def _assert_online(what: str) -> None:
    if _OFFLINE:
        raise RuntimeError(
            f"{what} attempted while offline. check() must never touch the "
            "network; this guard exists so a silent re-fetch cannot change a "
            "scored corpus.")


def _slug(url: str) -> str:
    m = re.search(r"mlbtraderumors\.com/(.+)$", url)
    tail = (m.group(1) if m else url).strip("/")
    tail = re.sub(r"[?#].*$", "", tail)
    return re.sub(r"[^A-Za-z0-9._-]", "_", tail) or hashlib.sha1(
        url.encode()).hexdigest()[:16]


def cache_path(url: str) -> Path:
    return CACHE / f"{_slug(url)}"


def _sleep() -> None:
    time.sleep(MIN_DELAY + random.uniform(0, JITTER))


class DeadURL(Exception):
    """The page does not exist (404/410). A wrong guess, not a block.

    Distinguishing this from a block matters: a 404 means stop asking for THAT
    url, while a timeout means stop asking this HOST anything. Treating a 404 as
    a block halts the whole ingest on a slug that was never going to resolve,
    and treating a block as a 404 keeps hammering an IP that is already
    firewalled. The 2023 tracker uses a different slug from every other year and
    is exactly this case.
    """


class Blocked(Exception):
    """Connection-level failure or a throttling status. Stop everything."""


def fetch_one(url: str, *, force: bool = False, first: bool = False) -> Path:
    """Fetch one URL into the permanent cache.

    Raises DeadURL for 404/410 (skip this url, keep going) and Blocked for
    anything else (stop the batch)."""
    p = cache_path(url)
    if p.exists() and not force:
        return p
    _assert_online(f"fetch {url}")
    if not first:
        _sleep()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            body = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            RuntimeError) as exc:
        code = getattr(exc, "code", None)
        err = CACHE / f"{_slug(url)}.err.json"
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text(json.dumps({
            "url": url, "at": datetime.now(timezone.utc).isoformat(),
            "http_status": code,
            "dead": code in (404, 410),
            "error": f"{type(exc).__name__}: {exc}"}, indent=1), encoding="utf-8")
        if code in (404, 410):
            raise DeadURL(f"HTTP {code}") from exc
        raise Blocked(f"{type(exc).__name__}: {exc}") from exc
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)
    log.info("fetched %s (%d bytes)", url, len(body))
    return p


def _cached_html() -> dict[str, str]:
    """{url-ish slug: html} for everything already on disk."""
    out = {}
    if not CACHE.exists():
        return out
    for p in sorted(CACHE.glob("*")):
        if p.suffix == ".json":
            continue
        try:
            out[p.name] = p.read_text("utf-8", errors="ignore")
        except OSError:
            continue
    return out


def harvest_urls(html: str) -> set[str]:
    """Every MLBTR arbitration-post URL linked from a page."""
    out = set()
    for m in _ARB_URL_RE.finditer(html or ""):
        out.add(f"https://www.mlbtraderumors.com/{m.group(1)}/{m.group(2)}/{m.group(3)}")
    return out


def load_urls() -> dict:
    if URLS_PATH.exists():
        try:
            return json.loads(URLS_PATH.read_text("utf-8"))
        except (OSError, ValueError):
            pass
    return {"generated_at": None, "urls": []}


def save_urls(urls: set[str]) -> None:
    URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    URLS_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "note": ("Discovered MLB Trade Rumors arbitration post URLs. Committed so "
                 "discovery never repeats on another machine, and so a re-run "
                 "cannot silently change which pages a scored corpus was built "
                 "from."),
        "urls": sorted(urls),
    }, indent=1), encoding="utf-8")


def discover(max_requests: int = 4) -> set[str]:
    """Index pages + free crawl out of the existing cache."""
    known = set(load_urls().get("urls") or [])
    for name, html in _cached_html().items():
        known |= harvest_urls(html)
    spent = 0
    for u in INDEX_URLS:
        if spent >= max_requests:
            break
        try:
            p = fetch_one(u, first=(spent == 0))
        except Exception as exc:
            log.error("discover aborted at %s: %s", u, exc)
            break
        spent += 1
        known |= harvest_urls(p.read_text("utf-8", errors="ignore"))
    known |= candidate_urls()
    save_urls(known)
    return known


def _classify(text: str) -> str:
    for name, pat in _OUTCOME_PATTERNS:
        if pat.search(text):
            return name
    return "unknown"


def _money(text: str):
    """First dollar figure in the entry, in USD.

    FIRST, not max: a settlement line can carry a club option or the minors half
    of a split deal after it, and those are not the arbitration award.
    """
    m = _MONEY_RE.search(text or "")
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    unit = m.group(2).upper()
    return int(round(val * (1_000 if unit == "K" else 1_000_000)))


def parse_post(html: str, *, class_year: int, kind: str, source_url: str) -> list[dict]:
    """One MLBTR arbitration post -> entry rows.

    Entries are <li> elements carrying a Baseball Reference link, a service-time
    token in parentheses and (usually) a dollar figure. Measured on the 2026
    tracker: 191 entries, 191 with a service token, 38 whose figure is in K.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    seen: set[tuple] = set()
    out: list[dict] = []
    # Iterate ENTRIES, not links. Posts before 2023 carry the same
    # "Name (5.049) - $2.7MM" list items but link no player to Baseball
    # Reference, so a link-driven loop silently returns nothing for them - which
    # is what dropped the entire 2022 class year on the first pass.
    for li in soup.find_all(["li", "p"]):
        text = li.get_text(" ", strip=True)
        text = text.replace("\xa0", " ").replace("�", " ")
        svc = _SERVICE_RE.search(text)
        if not svc:
            continue
        a = li.find("a", href=_BREF_RE)
        bref_m = _BREF_RE.search(a.get("href") or "") if a else None
        if bref_m:
            bbref_id = bref_m.group(1)
            player_name = a.get_text(" ", strip=True)
            id_source = "bref_href"
        else:
            # Name is everything before the service parenthesis.
            bbref_id = None
            player_name = text[:svc.start()].strip(" -–—:")
            id_source = "name"
            if not player_name or len(player_name) > 40:
                continue
        key = (bbref_id or player_name.lower(), class_year)
        if key in seen:
            continue
        seen.add(key)
        bref = bref_m
        # A projection post has no outcome to classify - it is a pre-settlement
        # figure and nothing has happened yet. Running the tracker vocabulary
        # over it labels ~99% of rows "unknown" and buries the tracker's real
        # unknowns in the noise.
        outcome = "projected" if kind == "projection" else _classify(text)
        amount = _money(text)
        row = {
            "class_year": int(class_year),
            "bbref_id": bbref_id,
            "id_source": id_source,
            "player_name": player_name,
            "service_time": f"{svc.group(1)}.{svc.group(2)}",
            "service_years": int(svc.group(1)),
            "service_days": int(svc.group(2)),
            "kind": kind,
            "outcome": outcome,
            "source_url": source_url,
            "text": text[:240],
        }
        # A projection post carries a PROJECTED figure; a tracker carries the
        # SETTLED one. Conflating them would score the model against its own
        # comparator's input.
        if kind == "projection":
            row["projected_usd"] = amount
        else:
            # Only an arbitration OUTCOME becomes a label. An extension, a club
            # option or an unresolved exchange is not an award, and a split
            # deal contributes its major-league figure only.
            row["settled_usd"] = amount if outcome in (
                "agreed", "hearing_won", "hearing_lost", "split_deal") else None
            row["split_contract"] = outcome == "split_deal"
            row["figure_usd"] = amount
            # The club heading the tracker lists the player under: the
            # attribution rule above. None only when the entry sits in no
            # club list (none does on the 2024-2026 pages).
            row["club_heading"], row["club"] = entry_club(li)
        out.append(row)
    return out


def _classify_url(url: str) -> tuple[int | None, str | None]:
    """(class_year, kind) from an MLBTR arbitration URL."""
    m = re.search(r"/(\d{4})/(\d{2})/(.+)\.html", url)
    if not m:
        return None, None
    yr, _mo, slug = int(m.group(1)), m.group(2), m.group(3)
    ms = re.search(r"(\d{4})-arbitration-tracker", slug)
    if ms:
        return int(ms.group(1)), "tracker"
    mp = re.search(r"projected-arbitration-salaries-for-(\d{4})", slug)
    if mp:
        return int(mp.group(1)), "projection"
    # 2023's post used a different slug order than every other year.
    mp2 = re.search(r"projected-arbitration-salaries-(\d{4})", slug)
    if mp2:
        return int(mp2.group(1)), "projection"
    mq = re.search(r"arbitration-projections?-(\d{4})", slug)
    if mq:
        return int(mq.group(1)), "projection"
    return None, None


def candidate_urls(first: int = 2021, last: int = 2026) -> set[str]:
    """Well-founded candidate URLs for years discovery did not surface.

    NOT blind guessing. The tracker slug /{Y}/01/{Y}-arbitration-tracker.html
    was confirmed live for 2024, 2025 and 2026, and the trackers are the
    highest-value pages in the corpus: they carry the SETTLED figure and the
    service time together, which is the label and the arb step in one row.
    Each miss still costs a request against a host that firewalled this IP once,
    so the list is bounded to the years actually needed and nothing else.
    """
    out = set()
    for y in range(int(first), int(last) + 1):
        out.add(f"https://www.mlbtraderumors.com/{y}/01/{y}-arbitration-tracker.html")
    return out


def build(*, offline: bool = False) -> dict:
    """Parse everything in the cache into the committed ledger."""
    entries: list[dict] = []
    sources: dict[str, dict] = {}
    unclassified: list[str] = []
    for p in sorted(CACHE.glob("*")):
        if p.suffix in (".json",):
            continue
        html = p.read_text("utf-8", errors="ignore")
        url = None
        for cand in (load_urls().get("urls") or []):
            if _slug(cand) == p.name:
                url = cand
                break
        if url is None:
            url = f"cache:{p.name}"
        cy, kind = _classify_url(url if url.startswith("http") else p.name)
        if cy is None:
            unclassified.append(p.name)
            continue
        rows = parse_post(html, class_year=cy, kind=kind, source_url=url)
        entries.extend(rows)
        src = {
            "sha1": hashlib.sha1(html.encode("utf-8", "ignore")).hexdigest(),
            "bytes": len(html),
            "class_year": cy,
            "kind": kind,
            "n_entries": len(rows),
        }
        if kind == "tracker":
            from bs4 import BeautifulSoup
            src["club_headings"] = len(club_headings(BeautifulSoup(html, "html.parser")))
            src["n_entries_without_club"] = sum(1 for r in rows if not r.get("club"))
        if not rows:
            # A classified page that yields nothing is a FORMAT gap, not an
            # empty page, and it is recorded rather than passed over. Measured:
            # the 2021 post predates the format entirely (0 bbref links, 0
            # service tokens) and the 2022 post carries 234 service tokens but
            # links no player to Baseball Reference, so its rows would need
            # name-based identity resolution.
            n_bref = len(re.findall(r"baseball-reference\.com/players/", html))
            n_svc = len(re.findall(r"\(\d+\.\d{3}\)", html))
            src["format_gap"] = {"bbref_links": n_bref, "service_tokens": n_svc}
        sources[url] = src
    id_census = {} if offline else resolve_names(entries)
    coverage: dict[str, dict] = {}
    for e in entries:
        cy = str(e["class_year"])
        c = coverage.setdefault(cy, {"tracker": 0, "projection": 0,
                                     "with_amount": 0, "unknown_outcome": 0})
        c[e["kind"]] = c.get(e["kind"], 0) + 1
        if e.get("settled_usd") or e.get("projected_usd"):
            c["with_amount"] += 1
        if e.get("outcome") == "unknown":
            c["unknown_outcome"] += 1
    doc = {
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "produced_by": "python tools/ingest_arbitration_ledger.py build",
        "note": ("MLB Trade Rumors arbitration trackers (SETTLED figures) and "
                 "Matt Swartz projection posts (PRE-SETTLEMENT projections). The "
                 "two kinds are kept apart: a projection is a comparator, not a "
                 "label, and scoring a model against its own comparator's input "
                 "would be circular."),
        "sources": sources,
        "coverage": coverage,
        "identity_census": id_census,
        "unclassified_cache_files": unclassified,
        "entries": sorted(entries, key=lambda e: (e["class_year"],
                                                  e.get("bbref_id") or "",
                                                  e.get("player_name") or "")),
    }
    return doc


def resolve_names(entries: list[dict]) -> dict:
    """Attach an mlbam id to entries that carried no Baseball Reference link.

    Uses fa_ident.resolve_with_reason, which REFUSES to guess on ambiguity - the
    wrong-player fallback was removed from that module in 2026-07 after "Lance
    McCullers" resolved to the father, who last pitched in 1992. Rows that do
    not resolve keep mlbam None and are excluded from label use rather than
    being attached to somebody.

    The four-way reason census is returned and published, because the unresolved
    tail is not random: it concentrates in common Hispanic surnames and suffixed
    names, which correlates with signing pathway and therefore with arb-step
    timing, so a silent drop would bias the label set.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import fa_ident
    census: dict[str, int] = {}
    need = [e for e in entries if not e.get("bbref_id")]
    if not need:
        return {"attempted": 0}
    try:
        if fa_ident.index_sides_missing():
            return {"attempted": 0, "skipped": "war_daily index incomplete"}
    except Exception:
        pass
    for e in need:
        cy = int(e["class_year"])
        try:
            mlbam, reason = fa_ident.resolve_with_reason(
                e["player_name"], range(cy - 3, cy + 1))
        except Exception:
            mlbam, reason = None, "RESOLVER_ERROR"
        census[reason] = census.get(reason, 0) + 1
        if mlbam:
            e["mlbam"] = int(mlbam)
        e["id_reason"] = reason
    census["attempted"] = len(need)
    census["resolved"] = sum(1 for e in need if e.get("mlbam"))
    return census


def write_ledger(doc: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(LEDGER_PATH)


def check() -> dict:
    """Re-parse purely from cache with the network structurally disabled."""
    global _OFFLINE
    _OFFLINE = True
    try:
        return build(offline=True)
    finally:
        _OFFLINE = False


def _fetch_priority(url: str):
    """Sort key for the fetch queue. Lower is fetched first.

    The request budget is the scarce resource - this IP was firewalled once
    already - so it is spent in value order, not alphabetical order. An
    alphabetical queue spends the whole budget on 2011 single-team eligibility
    posts before reaching a single settled-figure tracker.

      1. trackers, newest first  - the SETTLED figure and the service time
                                   together, i.e. the label and the arb step
      2. projections, newest first - the Swartz comparator for GATE A6
      3. everything else          - NOT FETCHED (see cmd_fetch)
    """
    cy, kind = _classify_url(url)
    if cy is None:
        return (9, 0, url)
    rank = 0 if kind == "tracker" else 1
    return (rank, -cy, url)


def cmd_fetch(args) -> int:
    urls = set(load_urls().get("urls") or [])
    # Unclassifiable posts are single-player notes ("Red Sox avoid arbitration
    # with X"). They carry one settlement each, cost one request each, and the
    # tracker for that year already contains them. Never fetched.
    classified = [u for u in urls if _classify_url(u)[0] is not None]
    skipped = len(urls) - len(classified)

    def _is_dead(u: str) -> bool:
        p = CACHE / f"{_slug(u)}.err.json"
        if not p.exists():
            return False
        try:
            return bool(json.loads(p.read_text("utf-8")).get("dead"))
        except (OSError, ValueError):
            return False

    todo = sorted((u for u in classified
                   if not cache_path(u).exists() and not _is_dead(u)),
                  key=_fetch_priority)
    if not todo:
        print(f"nothing to fetch; every classified URL is cached "
              f"({skipped} unclassifiable posts deliberately skipped)")
        return 0
    print(f"{len(todo)} uncached classified URLs "
          f"({skipped} unclassifiable skipped); fetching at most "
          f"{args.max_requests}, trackers first")
    spent = 0
    dead = 0
    for u in todo:
        if spent >= args.max_requests:
            break
        try:
            fetch_one(u, first=(spent == 0))
        except DeadURL as exc:
            # A wrong slug guess. Costs a request, tells us the page is not
            # there, and is recorded so the next run does not retry it.
            spent += 1
            dead += 1
            print(f"  [{spent}/{args.max_requests}] DEAD ({exc}) {u}")
            continue
        except Blocked as exc:
            print(f"ABORT (circuit breaker) at {u}: {exc}")
            print("A TCP-level block looks like a timeout. Wait, then re-run.")
            return 1
        spent += 1
        print(f"  [{spent}/{args.max_requests}] {u}")
    remaining = len(todo) - spent
    print(f"fetched {spent - dead}, dead {dead}; {remaining} still uncached")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("discover", "fetch", "build", "check"))
    ap.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    ap.add_argument("--write", action="store_true",
                    help="build/check: write data/_labs/arb_ledger.json")
    args = ap.parse_args(argv)

    if args.command == "discover":
        urls = discover(max_requests=args.max_requests)
        print(f"{len(urls)} arbitration URLs known")
        for u in sorted(urls):
            cy, kind = _classify_url(u)
            mark = "cached" if cache_path(u).exists() else "      "
            print(f"  {mark}  {cy or '????'} {kind or '?':10s} {u}")
        return 0
    if args.command == "fetch":
        return cmd_fetch(args)
    doc = check() if args.command == "check" else build()
    print(f"entries: {len(doc['entries'])}")
    for cy in sorted(doc["coverage"]):
        print(f"  {cy}: {doc['coverage'][cy]}")
    if doc["unclassified_cache_files"]:
        print(f"  unclassified cache files: {doc['unclassified_cache_files']}")
    if args.write:
        write_ledger(doc)
        print(f"wrote {LEDGER_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
