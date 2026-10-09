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
    python tools/ingest_arbitration_ledger.py recapture --date 2026-10-09
                                                            # one dated re-capture

DATED RE-CAPTURES (task Q9_17, plan row FAA-3)
The January pages above are permanent and their sha1 values in the ledger stay
reproducible, so a later look at the same URLs never overwrites them. A
re-capture is written under its own dated key, .cache/mlbtr/recapture/<date>/,
with a receipts.json naming each request (URL, fetch time, status, bytes,
sha1). One invocation fetches RECAPTURE_URLS (the three trackers and the three
"Players Exchange Filing Figures" posts, six requests) under the same limits as
fetch: 8 s delay plus jitter, at most --max-requests (6), and the first non-200
or connection error aborts the batch. A dated key that already holds a receipt
is never fetched again. build reads every dated key and adds, to the January
tracker rows only, the re-captured outcome and club, a hearing block when a
hearing line fires, and the filed figures; no entry is added or removed.

The capture plan from this winter on: an exchange-day capture in January 2027
(the evening of the filing deadline) and a post-hearing capture in February 2027
(after the last hearing), each under its own dated key. MLBTR does not write
hearing results into these pages: the 2026-10-09 re-capture found no hearing
line on any of the six, although the 2024 and 2025 trackers were last modified
2024-09-21 and 2025-09-12 and the 2024 filing post 2024-07-22, months after
those winters' hearings. The February capture must therefore name the
hearing-result posts it reads as URLs of their own.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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

# The one dated re-capture's six URLs: the three exchange-day trackers and the
# three filing-figure posts each tracker links to (2024's carries a different
# title, "Requested Salary Figures For 22 Players ...").
RECAPTURE_DIR = CACHE / "recapture"
RECAPTURE_URLS = (
    "https://www.mlbtraderumors.com/2024/01/2024-arbitration-tracker.html",
    "https://www.mlbtraderumors.com/2025/01/2025-arbitration-tracker.html",
    "https://www.mlbtraderumors.com/2026/01/2026-arbitration-tracker.html",
    "https://www.mlbtraderumors.com/2024/01/requested-salary-figures-for-22-"
    "players-who-didnt-reach-agreements-by-arbitration-filing-deadline.html",
    "https://www.mlbtraderumors.com/2025/01/17-players-exchange-filing-figures.html",
    "https://www.mlbtraderumors.com/2026/01/18-players-exchange-filing-figures.html",
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
    # The hearing classes precede `exchanged`: a tracker line updated after a
    # hearing keeps its exchange-day words ("No agreement reached, likely
    # heading to hearing. Won hearing"), and the later fact must win.
    ("hearing_won", re.compile(r"won .{0,20}hearing|prevailed", re.I)),
    ("hearing_lost", re.compile(r"lost .{0,20}hearing", re.I)),
    ("exchanged", re.compile(r"no agreement reached|did not reach agreement|"
                             r"head(?:ing|ed) (?:to|for) (?:a )?hearing|"
                             r"exchanged figures", re.I)),
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


def fetch_one(url: str, *, force: bool = False, first: bool = False,
              dest: Path | None = None) -> Path:
    """Fetch one URL into the permanent cache (or into `dest`, a dated
    re-capture directory, when given).

    Raises DeadURL for 404/410 (skip this url, keep going) and Blocked for
    anything else (stop the batch)."""
    p = cache_path(url) if dest is None else dest / _slug(url)
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
        err = (CACHE if dest is None else dest) / f"{_slug(url)}.err.json"
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


# --------------------------------------------------------------------------- #
# Dated re-captures and the filing-figure posts (task Q9_17, plan row FAA-3)
# --------------------------------------------------------------------------- #

_FILING_SLUG_RE = re.compile(r"filing-figures|filing-deadline", re.I)
# The club as the subject of a hearing verb: the word right before it.
_CLUB_SUBJECT_RE = re.compile(
    r"\b(?:team|club|" + "|".join(re.escape(n) for n in TRACKER_CLUB_CODES)
    + r")\s+$", re.I)


def hearing_result(text: str) -> str | None:
    """'player_won', 'club_won' or None for one tracker line.

    Tracker lines are written about the player ("Filed at ...", "$4MM
    agreement"), so "won his hearing" is a player win and "lost his hearing" a
    club win; a line whose subject is the club ("Tigers won the hearing")
    reverses that. The vocabulary is Cot's Contracts' (player_won / club_won),
    so the 2011-2023 backfill and the trackers read alike."""
    cls = _classify(text)
    if cls not in ("hearing_won", "hearing_lost"):
        return None
    m = re.search(r"\b(?:won|lost|prevailed)\b", text, re.I)
    subject_is_club = bool(m and _CLUB_SUBJECT_RE.search(text[:m.start()]))
    player_won = (cls == "hearing_won") != subject_is_club
    return "player_won" if player_won else "club_won"


def _recapture_kind(url: str) -> tuple[int | None, str | None]:
    """(class_year, kind) for a re-captured URL: 'tracker' or 'filing'."""
    cy, kind = _classify_url(url)
    if kind == "tracker":
        return cy, kind
    m = re.search(r"/(\d{4})/(\d{2})/(.+)\.html", url)
    if m and _FILING_SLUG_RE.search(m.group(3)):
        # A filing post goes up on exchange day, in January of the class year.
        return int(m.group(1)), "filing"
    return None, None


def parse_filing_post(html: str, *, class_year: int, source_url: str) -> list[dict]:
    """One "Players Exchange Filing Figures" post -> one row per exchanged case.

    Two layouts. 2025 and 2026: a plain club heading paragraph, then
    "Name (5.114): Filed at $32MM, team filed at $19MM". 2024: no headings and no
    service time, "Name: $4.8MM in desired salary. <strong>Angels</strong>
    offered $4.3MM". The player's figure is the first dollar figure and the
    club's the second; the club is the heading above the list, else the club
    named inside the line."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find(class_="entry-content") or soup
    out: list[dict] = []
    for li in body.find_all("li"):
        # A player link is a Baseball Reference page, or a Baseball Reference
        # search link when the name is ambiguous (2024 Jose Suarez and Jacob
        # Webb, 2026 Dylan Lee and Bryce Miller); the latter joins by name.
        a = li.find("a", href=re.compile(r"baseball-reference\.com/", re.I))
        if a is None:
            continue
        bref = _BREF_RE.search(a.get("href") or "")
        text = li.get_text(" ", strip=True).replace("\xa0", " ")
        figs = [m for m in _MONEY_RE.finditer(text)]
        if len(figs) < 2:
            continue
        ul = li.find_parent("ul")
        prev = ul.find_previous_sibling() if ul is not None else None
        head = None
        if prev is not None and prev.name == "p":
            t = prev.get_text(" ", strip=True)
            head = t if t in TRACKER_CLUB_CODES else None
        if head is None:
            for st in li.find_all("strong"):
                t = st.get_text(" ", strip=True)
                if t in TRACKER_CLUB_CODES:
                    head = t
                    break
        if head is None:
            # 2024 Vladimir Guerrero Jr.: "$19.9MM. Blue Jays $18.05MM", the
            # club in plain text between the two figures.
            mid = text[figs[0].end():figs[1].start()]
            for name in sorted(TRACKER_CLUB_CODES, key=len, reverse=True):
                if re.search(r"\b" + re.escape(name) + r"\b", mid):
                    head = name
                    break
        svc = _SERVICE_RE.search(text)
        out.append({
            "class_year": int(class_year),
            "bbref_id": bref.group(1) if bref else None,
            "player_name": a.get_text(" ", strip=True),
            "service_time": f"{svc.group(1)}.{svc.group(2)}" if svc else None,
            "club_heading": head,
            "club": TRACKER_CLUB_CODES.get(head) if head else None,
            "player_usd": _money(figs[0].group(0)),
            "club_usd": _money(figs[1].group(0)),
            "source_url": source_url,
            "text": text[:240],
        })
    return out


def load_recaptures() -> list[dict]:
    """Every dated re-capture on disk, oldest first, parsed but not joined."""
    out = []
    if not RECAPTURE_DIR.exists():
        return out
    for d in sorted(p for p in RECAPTURE_DIR.iterdir() if p.is_dir()):
        rp = d / "receipts.json"
        if not rp.exists():
            continue
        receipts = json.loads(rp.read_text("utf-8"))
        pages = []
        for req in receipts.get("requests") or []:
            if req.get("status") != 200:
                continue
            p = d / req["file"]
            html = p.read_text("utf-8", errors="ignore")
            cy, kind = _recapture_kind(req["url"])
            if kind == "tracker":
                rows = parse_post(html, class_year=cy, kind="tracker",
                                  source_url=req["url"])
            elif kind == "filing":
                rows = parse_filing_post(html, class_year=cy, source_url=req["url"])
            else:
                rows = []
            mod = re.search(r'dateModified"\s*:\s*"([^"]+)"', html)
            pages.append({"url": req["url"], "class_year": cy, "kind": kind,
                          "rows": rows, "html": html,
                          "sha1_bytes": req.get("sha1_bytes"),
                          "page_modified": mod.group(1) if mod else None})
        out.append({"date": d.name, "receipts": receipts, "pages": pages})
    return out


def apply_recaptures(entries: list[dict], captures: list[dict]) -> dict:
    """Add the re-capture fields to the exchange-day tracker rows, in place.

    Every tracker row gains `hearing`: None unless a hearing line fires on the
    exchange-day page or on a re-capture, else {"result", "capture", "text"}.
    A row the re-captured tracker lists gains `recaptured` (date, outcome,
    club). An exchanged row the filing post lists gains `filing` (player and
    club figures, the club the post names). Nothing else on a row changes: the
    exchange-day outcome, figure and club stay the record, and no entry is
    added or removed, so every consumer of the ledger reads what it read."""
    def key(cy, bref, name):
        return (int(cy), bref or (name or "").lower())

    tracker = {key(e["class_year"], e.get("bbref_id"), e.get("player_name")): e
               for e in entries if e.get("kind") == "tracker"}
    by_name: dict[tuple, list] = {}
    for e in tracker.values():
        by_name.setdefault((int(e["class_year"]), (e.get("player_name") or "").lower()),
                           []).append(e)

    def find(r):
        # Baseball Reference id first; else the name, only when exactly one
        # tracker row of that winter carries it.
        e = tracker.get(key(r["class_year"], r.get("bbref_id"), r.get("player_name")))
        if e is None:
            hits = by_name.get((int(r["class_year"]), (r.get("player_name") or "").lower()))
            e = hits[0] if hits and len(hits) == 1 else None
        return e

    for e in tracker.values():
        res = hearing_result(e.get("text") or "")
        e["hearing"] = ({"result": res, "capture": "exchange_day",
                         "text": e.get("text")} if res else None)
    block: dict[str, dict] = {}
    for cap in captures:
        srcs: dict[str, dict] = {}
        for page in cap["pages"]:
            s = {"class_year": page["class_year"], "kind": page["kind"],
                 "sha1_bytes": page["sha1_bytes"],
                 "page_modified": page["page_modified"],
                 "n_rows": len(page["rows"]), "n_joined": 0}
            if page["kind"] == "tracker":
                from bs4 import BeautifulSoup
                s["club_headings"] = len(club_headings(
                    BeautifulSoup(page["html"], "html.parser")))
                s.update(n_outcome_changed=0, n_club_changed=0, n_hearing_lines=0)
                for r in page["rows"]:
                    e = find(r)
                    if e is None:
                        continue
                    s["n_joined"] += 1
                    e["recaptured"] = {"on": cap["date"], "outcome": r["outcome"],
                                       "club": r.get("club")}
                    s["n_outcome_changed"] += r["outcome"] != e["outcome"]
                    s["n_club_changed"] += r.get("club") != e.get("club")
                    res = hearing_result(r.get("text") or "")
                    if res:
                        s["n_hearing_lines"] += 1
                        e["hearing"] = {"result": res, "capture": cap["date"],
                                        "text": r.get("text")}
            elif page["kind"] == "filing":
                s.update(n_club_differs_from_tracker=0, unjoined=[])
                for r in page["rows"]:
                    e = find(r)
                    if e is None:
                        s["unjoined"].append(r["player_name"])
                        continue
                    s["n_joined"] += 1
                    e["filing"] = {"player_usd": r["player_usd"],
                                   "club_usd": r["club_usd"], "club": r["club"],
                                   "on": cap["date"], "source_url": r["source_url"]}
                    s["n_club_differs_from_tracker"] += r["club"] != e.get("club")
            srcs[page["url"]] = s
        block[cap["date"]] = {
            "receipts": f".cache/mlbtr/recapture/{cap['date']}/receipts.json",
            "aborted": cap["receipts"].get("aborted"),
            "sources": srcs,
        }
    return block


def cots_backfill() -> dict:
    """The 2011-2023 arbitration backfill read off the Cot's Contracts club
    sheets of the one scripted capture (owner answers ARB-CLUB-1 (b) and
    X05-20 (b), task COTS_CAPTURE_DEFERRALS), with that capture's receipts.

    Never fetches: it reads tools/ingest_cots.py's cached sheets and receipts
    only. PARTIAL by construction (a case appears only for a player still on a
    club sheet at the capture date). The club is the one the sheet's note names
    ("re-signed by Houston", "won arbitration case with Houston"), the club the
    player settled or went to a hearing with; the sheet he sits on today is
    kept beside it. `exchanged` is True when figures are listed or a hearing was
    held, None when the note lists no figures (the sheet does not say)."""
    spec = importlib.util.spec_from_file_location(
        "ingest_cots", ROOT / "tools" / "ingest_cots.py")
    cots = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cots)
    files = cots.newest_files()
    if not files:
        return {"available": False, "reason": "no Cot's capture in .cache/cots"}
    receipts = cots._load_receipts()
    by_file = {s.get("file"): s for s in (receipts.get("sheets") or [])
               + (receipts.get("drops") or [])}
    cases, cited = [], []
    for slug, fp in sorted(files.items()):
        rec = by_file.get(fp.name) or {}
        cited.append({"sheet": slug, "url": rec.get("url"),
                      "fetched_at": rec.get("fetched_at"), "file": fp.name,
                      "bytes": rec.get("bytes"), "sha256": rec.get("sha256"),
                      "source": rec.get("source")})
        for p in cots.parse_sheet(fp.read_text(encoding="utf-8", errors="replace"), slug):
            cases += cots.arbitration_events(p)
    cots._club_codes(cases)
    lo, hi = cots.BACKFILL_FIRST, cots.BACKFILL_LAST
    rows, seen = [], set()
    for c in cases:
        if not c["season"] or not lo <= c["season"] <= hi:
            continue
        k = (c["player"], c["season"], c["kind"])
        if k in seen:
            continue
        seen.add(k)
        hearing = c["kind"] == "hearing"
        figures = c["player_figure_usd"] is not None
        rows.append({
            "class_year": int(c["season"]), "player_name": c["player"],
            "club": c.get("club"), "club_raw": c["club_raw"], "sheet": c["sheet"],
            "process": "hearing" if hearing else "settled",
            "exchanged": True if (hearing or figures) else None,
            "hearing": {"result": c["result"]} if hearing else None,
            "filing": ({"player_usd": c["player_figure_usd"],
                        "club_usd": c["club_figure_usd"]} if figures else None),
            "date": c["date"],
        })
    rows.sort(key=lambda r: (r["class_year"], r["club"] or "", r["player_name"]))
    return {
        "available": True,
        "attribution": cots.ATTRIBUTION,
        "source_url": cots.BASE,
        "window": [lo, hi],
        "note": ("PARTIAL by construction: only players still on a Cot's club "
                 "sheet at the capture date carry their history. Lab only; "
                 "docs/ARBITRATION_GATE.md section 13b does not read it unless a "
                 "dated amendment says so."),
        # The capture run's own record, without its User-Agent string.
        "capture": {k: v for k, v in ((receipts.get("captures") or [{}])[0]).items()
                    if k != "user_agent"},
        "receipts": cited,
        "n_cases": len(rows),
        "rows": rows,
    }


def build(*, offline: bool = False) -> dict:
    """Parse everything in the cache into the committed ledger."""
    entries: list[dict] = []
    sources: dict[str, dict] = {}
    unclassified: list[str] = []
    for p in sorted(CACHE.glob("*")):
        if p.suffix in (".json",) or p.is_dir():
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
    recaptures = apply_recaptures(entries, load_recaptures())
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
        "recaptures": recaptures,
        "cots_backfill": cots_backfill(),
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


def _receipts_path(date: str) -> Path:
    return RECAPTURE_DIR / date / "receipts.json"


def cmd_recapture(date: str, max_requests: int) -> int:
    """One dated re-capture of RECAPTURE_URLS under .cache/mlbtr/recapture/<date>/."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        print("--date YYYY-MM-DD is required")
        return 2
    if _receipts_path(date).exists():
        print(f"refused: {date} already holds a receipt; a dated key is captured once")
        return 2
    if len(RECAPTURE_URLS) > max_requests:
        print(f"refused: {len(RECAPTURE_URLS)} URLs exceed --max-requests {max_requests}")
        return 2
    dest = RECAPTURE_DIR / date
    dest.mkdir(parents=True, exist_ok=True)
    run = {"captured_on": date, "user_agent": UA,
           "limits": {"min_delay_s": MIN_DELAY, "jitter_s": JITTER,
                      "max_requests": max_requests},
           "requests": [], "aborted": None}
    for i, u in enumerate(RECAPTURE_URLS):
        # Taken before fetch_one's polite delay: when the request was queued.
        at = datetime.now(timezone.utc).isoformat()
        try:
            p = fetch_one(u, first=(i == 0), dest=dest)
        except (DeadURL, Blocked) as exc:
            # Circuit breaker: the first non-200 ends the batch, a 404 included.
            run["requests"].append({"url": u, "requested_at": at, "status": None,
                                    "error": f"{type(exc).__name__}: {exc}"})
            run["aborted"] = f"at {u}: {exc}"
            print(f"ABORT (circuit breaker) at {u}: {exc}")
            break
        body = p.read_bytes()
        run["requests"].append({
            "url": u, "requested_at": at, "status": 200, "file": p.name,
            "bytes": len(body),
            "sha1_bytes": hashlib.sha1(body).hexdigest()})
        print(f"  [{i + 1}/{len(RECAPTURE_URLS)}] {u} ({len(body)} bytes)")
    _receipts_path(date).write_text(json.dumps(run, indent=1), encoding="utf-8")
    return 1 if run["aborted"] else 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("discover", "fetch", "build", "check",
                                        "recapture"))
    ap.add_argument("--date", help="recapture: the dated cache key, YYYY-MM-DD")
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
    if args.command == "recapture":
        return cmd_recapture(args.date, args.max_requests)
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
