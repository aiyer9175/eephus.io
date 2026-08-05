# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""card_prices_ingest.py - raw sold-price comps for the Card Market module.

WHAT LEAVES THIS FILE, AND WHAT NEVER DOES
------------------------------------------
This module stores RAW comps. It publishes nothing. The only public output of
the card lane is card_market_export.py's derived index (a grade-mix adjusted
trimmed median plus a trend), and the test suite asserts that no raw comp row,
price, sale date, listing title or listing id ever reaches data/card_market.json.
Raw comps live in prospects.db forever (marketplaces expire their own sold
windows at 90 days, so the local store is the only durable copy) and they are
never committed to git: prospects.db is gitignored, and so is every *.csv drop.

TWO INPUT PATHS, ONE STORAGE
----------------------------
(a) CSV DROP - the first-class path, cloned from the FanGraphs board runbook.
    Drop a file at data/drops/card_comps_YYYY-MM-DD.csv with the columns
    documented in docs/diamond-cards.md and run `python card_prices_ingest.py
    --drops`. This path needs no network, no scraper and no ToS exposure. It is
    also the seam a licensed feed plugs into: SportsCardsPro sells a documented
    CSV price-guide product, and swapping it in is a file drop, not a rewrite.

(b) SCRAPER - OFF BY DEFAULT. `EEPHUS_CARD_SCRAPE=1` is required to arm it, and
    even armed it throttles to one request every MIN_REQUEST_INTERVAL seconds
    (5.0), sends an honest identifying User-Agent, and parses defensively (a
    layout change yields zero rows and a loud log, never a crash and never
    garbage prices).

    TOS FRAGILITY, STATED PLAINLY: public sold-listing pages are not an API.
    Post-hiQ, scraping public data is not a computer-fraud problem, but it is
    breach-of-contract exposure under a marketplace's terms of service, and the
    markup can change any day. That is exactly why this module is shaped so the
    scraper is the OPTIONAL half: the CSV drop is an equal input, the derived
    index is the only thing published, and docs/diamond-cards.md documents the
    licensed swap. If the scraper breaks or has to be switched off, the module
    keeps working off drops with no code change.

IDENTITY
--------
Watchlist entries resolve through stats.bulk_resolve_ids, NOT
stats.resolve_mlbam_id. The single-player entry point poisons a negative-id
cache on a miss, which is the defect that left a whole draft class statless in
2026-08; the bulk path resolves against the season player index in one pass and
is the repo's standing convention for batch identity.

IMMUTABILITY
------------
card_comps is append-only by construction: every write is INSERT OR IGNORE on a
primary key of (card_id, listing_hash), where listing_hash is a content
fingerprint of the sale. Re-ingesting the same drop file is a no-op. Nothing in
this module UPDATEs or DELETEs a comp row.

CLI
---
    python card_prices_ingest.py --drops                 # ingest every un-ingested drop
    python card_prices_ingest.py --csv path/to/file.csv  # ingest one file
    python card_prices_ingest.py --scrape --hot          # needs EEPHUS_CARD_SCRAPE=1
    python card_prices_ingest.py --build-watchlist       # regenerate data/card_watchlist.json
    python card_prices_ingest.py --stats                 # what is in the store
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("card_prices_ingest")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DROPS_DIR = DATA_DIR / "drops"
WATCHLIST_PATH = DATA_DIR / "card_watchlist.json"

# ── scraper posture ─────────────────────────────────────────────────────────
SCRAPE_ENV_FLAG = "EEPHUS_CARD_SCRAPE"
MIN_REQUEST_INTERVAL = 5.0          # seconds between requests, hard floor
REQUEST_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (compatible; eephus.io card-index/1.0; "
    "derived price index for a baseball analytics site, no raw listing republication; "
    "contact: arkndjl@gmail.com)"
)
# The sold-listing search endpoint. Kept as ONE overridable constant so a host
# change, or a decision to point at a licensed feed, is a single edit. Empty by
# default in a fresh checkout would be a silent no-op, so it carries the
# documented target and the flag above is what actually arms it.
SEARCH_URL_TEMPLATE = os.environ.get(
    "EEPHUS_CARD_SCRAPE_URL",
    "https://www.ebay.com/sch/i.html?_nkw={query}&_sacat=0&LH_Sold=1&LH_Complete=1&_ipg=60",
)

# Cadence config lives here, not in run_monthly: the box schedules the CLI, the
# module owns what "hot" and "long tail" mean. See docs/diamond-cards.md.
CADENCE = {
    "hot_daily": True,              # entries flagged hot: refresh daily
    "long_tail_days": 7,            # everyone else: weekly
    "full_sweep_days": 60,          # a full sweep must land inside the 90-day
                                    # sold window or comps expire unseen
}

GRADE_BUCKETS = ("PSA 10", "PSA 9", "BGS 9.5", "SGC 10", "RAW")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ── schema ──────────────────────────────────────────────────────────────────
# Created HERE rather than in storage.SCHEMA on purpose: the card lane is a new
# module with its own lifecycle, and CREATE TABLE IF NOT EXISTS through the
# shared connection gives the same result without editing a 16k-line file that
# five other lanes are also touching this wave.
SCHEMA = """
CREATE TABLE IF NOT EXISTS card_comps (
    card_id      TEXT NOT NULL,        -- watchlist card id (player|set|grade)
    listing_hash TEXT NOT NULL,        -- content fingerprint of ONE sale
    sold_date    TEXT NOT NULL,        -- ISO yyyy-mm-dd
    price_usd    REAL NOT NULL,
    grade        TEXT NOT NULL,        -- grade AS SOLD (may differ from the card's target bucket)
    source       TEXT NOT NULL,        -- 'csv_drop:<file>' | 'scrape:<host>'
    player_key   TEXT,
    mlbam        INTEGER,
    title        TEXT,                 -- listing title, LOCAL ONLY, never published
    ingested_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (card_id, listing_hash)
);
CREATE INDEX IF NOT EXISTS idx_card_comps_card ON card_comps(card_id, sold_date);
CREATE INDEX IF NOT EXISTS idx_card_comps_date ON card_comps(sold_date);

-- The module's OWN derived history. The whole reason v1 ships as a screen is
-- that no price-history backtest exists; this table is how one becomes possible.
-- Written by card_market_export, one row per card per export day.
CREATE TABLE IF NOT EXISTS card_index_history (
    card_id      TEXT NOT NULL,
    as_of        TEXT NOT NULL,        -- ISO yyyy-mm-dd
    index_usd    REAL,                 -- NULL when the window was too thin
    n_comps      INTEGER NOT NULL DEFAULT 0,
    window_days  INTEGER NOT NULL,
    PRIMARY KEY (card_id, as_of)
);
CREATE INDEX IF NOT EXISTS idx_card_index_hist ON card_index_history(card_id, as_of);

-- Drop-file ledger, so re-running --drops is idempotent at the FILE level too
-- (the row level is already idempotent through listing_hash).
CREATE TABLE IF NOT EXISTS card_drop_files (
    filename     TEXT PRIMARY KEY,
    sha1         TEXT NOT NULL,
    rows_seen    INTEGER NOT NULL,
    rows_stored  INTEGER NOT NULL,
    ingested_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _connect():
    """The shared storage connection. Imported lazily so a test can point the
    whole module at a temp DB by monkeypatching storage.DB_PATH."""
    import storage
    return storage.connect()


def ensure_tables(con=None) -> None:
    """Create the card tables if they are absent. Safe to call on every run."""
    if con is not None:
        con.executescript(SCHEMA)
        return
    with _connect() as c:
        c.executescript(SCHEMA)


# ── ids and fingerprints ────────────────────────────────────────────────────
def slug(s: str | None) -> str:
    return _SLUG_RE.sub("-", (s or "").strip().lower()).strip("-")


def card_id(player_key: str, set_desc: str, grade_bucket: str) -> str:
    """THE card identity. One string so the DB, the watchlist, the payload and
    the page all key on the same thing."""
    return f"{slug(player_key)}|{slug(set_desc)}|{slug(grade_bucket)}"


def listing_fingerprint(card: str, sold_date: str, price: float, grade: str,
                        title: str | None = None, listing_id: str | None = None) -> str:
    """Content hash of ONE sale. listing_id wins when the source supplies one
    (two identical-looking sales on the same day at the same price are two
    sales); otherwise the tuple of the sale's own facts is the identity, which
    makes a re-drop of the same file a no-op."""
    basis = listing_id.strip() if (listing_id and listing_id.strip()) else "|".join(
        [card, sold_date, f"{float(price):.2f}", grade, (title or "").strip().lower()])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


@dataclass
class Comp:
    """One raw sold comp. LOCAL ONLY. Nothing of this shape is ever published."""
    card_id: str
    listing_hash: str
    sold_date: str
    price_usd: float
    grade: str
    source: str
    player_key: str | None = None
    mlbam: int | None = None
    title: str | None = None


# ── watchlist ───────────────────────────────────────────────────────────────
def load_watchlist(path: Path | str | None = None) -> dict:
    """The curated watchlist. Returns {'cards': []} when absent so every caller
    degrades to a loud empty state rather than an exception."""
    p = Path(path) if path else WATCHLIST_PATH
    if not p.exists():
        log.warning("card watchlist missing at %s", p)
        return {"version": 1, "cards": []}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.exception("card watchlist unreadable at %s", p)
        return {"version": 1, "cards": []}
    if not isinstance(doc, dict) or not isinstance(doc.get("cards"), list):
        return {"version": 1, "cards": []}
    return doc


def resolve_identities(watchlist: dict, resolver=None, season: int | None = None) -> dict:
    """Fill missing mlbam ids on watchlist entries via stats.bulk_resolve_ids.

    NOT resolve_mlbam_id: the single-player entry point writes a negative-id
    cache entry on a miss and a later good lookup then reads the poisoned cache
    (the 2026-08-03 draft-class outage). Injectable `resolver` so the tests can
    stub it without touching the network.

    Returns {player_key: mlbam} for the keys this call resolved."""
    cards = watchlist.get("cards") or []
    need = []
    seen = set()
    for c in cards:
        k, n = c.get("player_key"), c.get("player_name")
        if not k or c.get("mlbam") or k in seen:
            continue
        seen.add(k)
        need.append((k, n or k.replace("_", " ").title(), c.get("position")))
    if not need:
        return {}
    if resolver is None:
        import stats
        resolver = stats.bulk_resolve_ids
    try:
        ids, _birth, _idx = resolver(need, season=season)
    except Exception:
        log.exception("card watchlist: bulk_resolve_ids failed, leaving ids unresolved")
        return {}
    ids = {k: int(v) for k, v in (ids or {}).items() if v}
    for c in cards:
        mid = ids.get(c.get("player_key"))
        if mid and not c.get("mlbam"):
            c["mlbam"] = mid
    return ids


def due_cards(watchlist: dict, today: date | None = None, last_seen: dict | None = None) -> list:
    """Which watchlist cards are due for a refresh under CADENCE.

    hot cards every day; everyone else every CADENCE['long_tail_days']. A card
    with no recorded fetch is always due. `last_seen` is {card_id: iso date}."""
    today = today or date.today()
    last_seen = last_seen or {}
    out = []
    for c in (watchlist.get("cards") or []):
        cid = c.get("card_id")
        if not cid:
            continue
        prev = last_seen.get(cid)
        if not prev:
            out.append(c)
            continue
        try:
            age = (today - date.fromisoformat(str(prev)[:10])).days
        except ValueError:
            out.append(c)
            continue
        limit = 1 if c.get("hot") else int(CADENCE["long_tail_days"])
        if age >= limit:
            out.append(c)
    return out


def last_seen_map(con=None) -> dict:
    """{card_id: max ingested date} so due_cards can schedule."""
    def _q(c):
        c.executescript(SCHEMA)
        rows = c.execute(
            "SELECT card_id, MAX(substr(ingested_at,1,10)) AS d FROM card_comps GROUP BY card_id"
        ).fetchall()
        return {r["card_id"]: r["d"] for r in rows}
    if con is not None:
        return _q(con)
    with _connect() as c:
        return _q(c)


# ── storage ─────────────────────────────────────────────────────────────────
def store_comps(comps, con=None) -> tuple[int, int]:
    """Append comps. Returns (inserted, skipped_as_duplicate).

    INSERT OR IGNORE against PK (card_id, listing_hash) is the whole
    immutability story: a comp can be added, never rewritten, never removed."""
    comps = list(comps or [])
    if not comps:
        return (0, 0)

    def _write(c):
        c.executescript(SCHEMA)
        before = c.execute("SELECT COUNT(*) AS n FROM card_comps").fetchone()["n"]
        c.executemany(
            "INSERT OR IGNORE INTO card_comps "
            "(card_id, listing_hash, sold_date, price_usd, grade, source, player_key, mlbam, title) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(x.card_id, x.listing_hash, x.sold_date, float(x.price_usd), x.grade,
              x.source, x.player_key, x.mlbam, x.title) for x in comps],
        )
        after = c.execute("SELECT COUNT(*) AS n FROM card_comps").fetchone()["n"]
        ins = after - before
        return (ins, len(comps) - ins)

    if con is not None:
        return _write(con)
    with _connect() as c:
        return _write(c)


def load_comps(card_ids=None, con=None) -> dict:
    """{card_id: [ {sold_date, price_usd, grade}, ... ]} for the model.

    Deliberately drops title/listing_hash/source on the way out: the export
    never needs them, so they cannot leak into a payload by accident."""
    def _q(c):
        c.executescript(SCHEMA)
        if card_ids:
            ids = list(card_ids)
            out: dict = {}
            for i in range(0, len(ids), 400):
                chunk = ids[i:i + 400]
                q = ("SELECT card_id, sold_date, price_usd, grade FROM card_comps "
                     f"WHERE card_id IN ({','.join('?' * len(chunk))})")
                for r in c.execute(q, chunk):
                    out.setdefault(r["card_id"], []).append(
                        {"sold_date": r["sold_date"], "price_usd": r["price_usd"], "grade": r["grade"]})
            return out
        out = {}
        for r in c.execute("SELECT card_id, sold_date, price_usd, grade FROM card_comps"):
            out.setdefault(r["card_id"], []).append(
                {"sold_date": r["sold_date"], "price_usd": r["price_usd"], "grade": r["grade"]})
        return out

    if con is not None:
        return _q(con)
    with _connect() as c:
        return _q(c)


def store_stats(con=None) -> dict:
    def _q(c):
        c.executescript(SCHEMA)
        r = c.execute("SELECT COUNT(*) n, COUNT(DISTINCT card_id) cards, "
                      "MIN(sold_date) lo, MAX(sold_date) hi FROM card_comps").fetchone()
        return {"comps": r["n"], "cards": r["cards"], "first_sale": r["lo"], "last_sale": r["hi"]}
    if con is not None:
        return _q(con)
    with _connect() as c:
        return _q(c)


# ── (a) CSV drop path ───────────────────────────────────────────────────────
# Column contract, documented in docs/diamond-cards.md. Aliases exist because a
# licensed export will not use our names; unknown extra columns are ignored.
CSV_ALIASES = {
    "card_id": ("card_id", "cardid", "card"),
    "player_key": ("player_key", "playerkey", "player"),
    "set_desc": ("set_desc", "set", "set_parallel", "description", "card_desc"),
    "grade": ("grade", "grade_bucket", "gradebucket", "condition"),
    "sold_date": ("sold_date", "date", "sale_date", "solddate"),
    "price_usd": ("price_usd", "price", "sale_price", "amount"),
    "title": ("title", "listing_title", "name"),
    "listing_id": ("listing_id", "id", "item_id", "listingid"),
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", (h or "").strip().lower().replace(" ", "_"))


def _col_map(fieldnames) -> dict:
    have = {_norm_header(f): f for f in (fieldnames or [])}
    out = {}
    for canon, aliases in CSV_ALIASES.items():
        for a in aliases:
            if a in have:
                out[canon] = have[a]
                break
    return out


def _parse_price(v) -> float | None:
    if v is None:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if not s or s in ("-", "."):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f > 0 else None


def _parse_date(v) -> str | None:
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d %b %Y", "%b %d, %Y",
                "%b %d %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_drop_csv(path: Path | str, watchlist: dict | None = None) -> list:
    """Parse ONE drop file into Comp rows. Unparseable rows are skipped with a
    count, never guessed at: a bad price is a dropped row, not a zero."""
    p = Path(path)
    wl = watchlist if watchlist is not None else load_watchlist()
    by_id = {c.get("card_id"): c for c in (wl.get("cards") or []) if c.get("card_id")}
    # A drop may name a card by (player_key, set_desc, grade) instead of card_id.
    by_triple = {(c.get("player_key"), slug(c.get("set_desc")), slug(c.get("grade_bucket"))): c
                 for c in (wl.get("cards") or [])}
    src = f"csv_drop:{p.name}"
    out, skipped = [], 0
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        rdr = csv.DictReader(fh)
        cols = _col_map(rdr.fieldnames)
        if "price_usd" not in cols or "sold_date" not in cols:
            log.error("drop %s: missing required price/date columns (saw %s)", p.name, rdr.fieldnames)
            return []
        for row in rdr:
            def g(k):
                c = cols.get(k)
                return row.get(c) if c else None
            price = _parse_price(g("price_usd"))
            sold = _parse_date(g("sold_date"))
            if price is None or not sold:
                skipped += 1
                continue
            grade = (g("grade") or "RAW").strip().upper().replace("PSA10", "PSA 10")
            cid = (g("card_id") or "").strip()
            pk = (g("player_key") or "").strip() or None
            entry = by_id.get(cid) if cid else None
            if entry is None and pk:
                entry = by_triple.get((pk, slug(g("set_desc")), slug(grade)))
            if entry is not None:
                cid = entry["card_id"]
            elif not cid:
                if not pk:
                    skipped += 1
                    continue
                # A known player, an unlisted parallel. Keep the sale under its
                # own descriptor rather than discarding real evidence; the export
                # only reads watchlist card_ids, so an off-list id is stored and
                # simply not published until the watchlist names it.
                cid = card_id(pk, g("set_desc") or "unspecified", grade)
            title = (g("title") or "").strip() or None
            out.append(Comp(
                card_id=cid,
                listing_hash=listing_fingerprint(cid, sold, price, grade, title, g("listing_id")),
                sold_date=sold, price_usd=price, grade=grade, source=src,
                player_key=(entry or {}).get("player_key") or pk,
                mlbam=(entry or {}).get("mlbam"), title=title,
            ))
    if skipped:
        log.info("drop %s: %d rows skipped (unparseable price/date/card)", p.name, skipped)
    return out


def ingest_csv(path: Path | str, watchlist: dict | None = None, con=None) -> dict:
    comps = parse_drop_csv(path, watchlist)
    ins, dup = store_comps(comps, con=con)
    p = Path(path)
    sha = hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else ""

    def _ledger(c):
        c.executescript(SCHEMA)
        c.execute("INSERT OR REPLACE INTO card_drop_files (filename, sha1, rows_seen, rows_stored) "
                  "VALUES (?,?,?,?)", (p.name, sha, len(comps), ins))
    if con is not None:
        _ledger(con)
    else:
        with _connect() as c:
            _ledger(c)
    return {"file": p.name, "parsed": len(comps), "stored": ins, "duplicates": dup}


def ingest_drops(drops_dir: Path | str | None = None, watchlist: dict | None = None,
                 con=None) -> dict:
    d = Path(drops_dir) if drops_dir else DROPS_DIR
    if not d.exists():
        log.info("no drops directory at %s", d)
        return {"files": [], "stored": 0}
    files = sorted(d.glob("card_comps_*.csv"))
    res = [ingest_csv(f, watchlist, con=con) for f in files]
    return {"files": res, "stored": sum(r["stored"] for r in res)}


# ── (b) scraper path (OFF by default) ───────────────────────────────────────
def scrape_enabled() -> bool:
    return os.environ.get(SCRAPE_ENV_FLAG, "").strip() == "1"


_PRICE_RE = re.compile(r"[$]\s?([0-9][0-9,]*\.?[0-9]{0,2})")
_SOLD_RE = re.compile(r"sold\s+(?:item\s+)?([A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})", re.IGNORECASE)
_GRADE_RE = re.compile(r"\b(PSA|BGS|SGC|CGC)\s?(10|9\.5|9|8\.5|8)\b", re.IGNORECASE)
_ITEM_SPLIT = re.compile(r"<li[^>]*class=\"[^\"]*s-item[^\"]*\"", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_sold_html(html: str) -> list:
    """RESILIENT parse of a sold-listings results page -> [{title, price, sold_date, grade}].

    Deliberately NOT a DOM/selector parse. Selectors are the first thing a
    marketplace redesign breaks, and a half-matched selector yields plausible
    garbage. This walks item blocks and requires BOTH a price and a sale date in
    the same block, so a layout change produces zero rows (visible in the log)
    rather than wrong prices. Zero rows is a designed outcome, not a failure."""
    if not html:
        return []
    out = []
    for block in _ITEM_SPLIT.split(html)[1:]:
        text = _TAG_RE.sub(" ", block)
        text = re.sub(r"^[^A-Za-z0-9$]+", "", re.sub(r"\s+", " ", text).strip())
        pm = _PRICE_RE.search(text)
        dm = _SOLD_RE.search(text)
        if not pm or not dm:
            continue
        price = _parse_price(pm.group(1))
        sold = _parse_date(dm.group(1).replace(",", ""))
        if price is None or not sold:
            continue
        gm = _GRADE_RE.search(text)
        grade = f"{gm.group(1).upper()} {gm.group(2)}" if gm else "RAW"
        title = text[:180].strip()
        out.append({"title": title, "price": price, "sold_date": sold, "grade": grade})
    return out


class Throttle:
    """One request per MIN_REQUEST_INTERVAL seconds. Injectable clock/sleeper so
    the tests prove the interval without spending it."""

    def __init__(self, interval: float = MIN_REQUEST_INTERVAL, clock=time.monotonic, sleeper=time.sleep):
        self.interval = max(float(interval), MIN_REQUEST_INTERVAL)
        self._clock, self._sleep, self._last = clock, sleeper, None

    def wait(self) -> float:
        now = self._clock()
        if self._last is None:
            self._last = now
            return 0.0
        gap = self.interval - (now - self._last)
        if gap > 0:
            self._sleep(gap)
            self._last = self._clock()
            return gap
        self._last = now
        return 0.0


def _default_fetch(url: str) -> str:
    import requests
    r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                   "Accept": "text/html,*/*",
                                   "Accept-Language": "en-US,en;q=0.9"},
                     timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def scrape_cards(cards, fetch=None, throttle=None, con=None, source_host="marketplace") -> dict:
    """Fetch sold comps for `cards`. Refuses to run unless EEPHUS_CARD_SCRAPE=1.

    `fetch` is injected in tests (fixtures only). Nothing here runs during the
    build: the flag is off, and the pipeline calls the drop path."""
    if fetch is None and not scrape_enabled():
        log.warning("card scrape requested but %s is not 1; refusing (use the CSV drop path)",
                    SCRAPE_ENV_FLAG)
        return {"enabled": False, "cards": 0, "stored": 0, "reason": "flag off"}
    fetch = fetch or _default_fetch
    thr = throttle or Throttle()
    stored = total = 0
    for c in list(cards or []):
        cid = c.get("card_id")
        if not cid:
            continue
        query = c.get("query") or " ".join(
            x for x in (c.get("player_name"), c.get("set_desc"), c.get("grade_bucket")) if x)
        url = SEARCH_URL_TEMPLATE.format(query=query.replace(" ", "+"))
        thr.wait()
        try:
            html = fetch(url)
        except Exception:
            log.exception("card scrape: fetch failed for %s", cid)
            continue
        rows = parse_sold_html(html)
        if not rows:
            log.warning("card scrape: zero rows parsed for %s (layout change or no sales)", cid)
        comps = [Comp(card_id=cid,
                      listing_hash=listing_fingerprint(cid, r["sold_date"], r["price"], r["grade"], r["title"]),
                      sold_date=r["sold_date"], price_usd=r["price"], grade=r["grade"],
                      source=f"scrape:{source_host}", player_key=c.get("player_key"),
                      mlbam=c.get("mlbam"), title=r["title"]) for r in rows]
        ins, _dup = store_comps(comps, con=con)
        stored += ins
        total += len(comps)
    return {"enabled": True, "cards": len(list(cards or [])), "parsed": total, "stored": stored}


# ── watchlist generator ─────────────────────────────────────────────────────
# Card descriptors by tier. A prospect's tradeable card is the Bowman Chrome
# prospect auto; a graduated star's is the flagship rookie. These are the two
# descriptors the hobby actually quotes, which is what makes a per-card index
# meaningful at all.
_PROSPECT_SET = "Bowman Chrome Prospect Auto"
_MLB_SET = "Topps Chrome Rookie Refractor"
_DEFAULT_GRADE = "PSA 10"


def build_watchlist(n_prospects: int = 30, n_mlb: int = 10, data_dir: Path | None = None) -> dict:
    """Regenerate data/card_watchlist.json from the LIVE eFV board.

    Prospect side: data/xfv.json ranked by efv_board_scale.board_value (THE board
    number, the one-basis rule), joined to timeseries.json for name / org / mlbam.
    MLB side: the marquee names off the committed hitter + starter leaderboards.

    Hand-editable afterwards: this is a CURATED list, and the generator exists so
    the curation starts from the board instead of from taste."""
    d = data_dir or DATA_DIR
    from efv_board_scale import board_value

    def _load(name):
        p = d / name
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except (json.JSONDecodeError, OSError):
            return None

    xfv = _load("xfv.json") or {}
    ts = _load("timeseries.json") or {}
    by_player = xfv.get("by_player") if isinstance(xfv, dict) else {}
    ident = {}
    for pl in (ts.get("players") or []):
        k = pl.get("player_key")
        if k:
            ident[k] = pl
    ranked = []
    for k, rec in (by_player or {}).items():
        if not isinstance(rec, dict) or rec.get("kind") != "active":
            continue
        v = board_value(rec)
        p = ident.get(k)
        if v is None or not p or not p.get("mlbam_id"):
            continue
        ranked.append((v, k, rec, p))
    ranked.sort(key=lambda r: (-r[0], r[1]))

    cards = []
    for i, (v, k, rec, p) in enumerate(ranked[:n_prospects]):
        cid = card_id(k, _PROSPECT_SET, _DEFAULT_GRADE)
        e = p.get("eta")
        # ETA is stamped HERE, at build time, so card_market_export never has to
        # parse the 73MB timeseries.json for forty players. The watchlist is
        # regenerated whenever the board moves, which is the same cadence the
        # ETA moves on.
        eta_year = e.get("year") if isinstance(e, dict) else (e if isinstance(e, int) else None)
        cards.append({
            "card_id": cid, "player_key": k, "player_name": p.get("player_name"),
            "mlbam": p.get("mlbam_id"), "org": p.get("org"), "position": p.get("position"),
            "side": rec.get("side"), "tier": "prospect", "eta": eta_year,
            "set_desc": _PROSPECT_SET, "parallel": "Base Refractor",
            "grade_bucket": _DEFAULT_GRADE,
            "hot": i < 12,
            "board_efv_at_build": round(float(v), 1),
        })

    marquee = []
    for fname, key, stat in (("hitter_leaderboards.json", "hitters", "hem_plus"),
                             ("starter_leaderboards.json", "starters", "sem_plus")):
        rows = (_load(fname) or {}).get(key) or []
        rows = [r for r in rows if r.get("mlbam") and r.get("name") and r.get(stat) is not None]
        rows.sort(key=lambda r: -float(r[stat]))
        marquee.extend(rows[:max(0, n_mlb // 2)])
    for r in marquee:
        pk = slug(r["name"]).replace("-", "_")
        cid = card_id(pk, _MLB_SET, _DEFAULT_GRADE)
        cards.append({
            "card_id": cid, "player_key": pk, "player_name": r["name"],
            "mlbam": int(r["mlbam"]), "org": r.get("team"), "position": None,
            "side": "P" if "sem_plus" in r else "H", "tier": "mlb",
            "set_desc": _MLB_SET, "parallel": "Base Refractor",
            "grade_bucket": _DEFAULT_GRADE, "hot": True,
        })

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "card_prices_ingest.build_watchlist",
        "basis": ("prospect rows: top of the live eFV board by "
                  "efv_board_scale.board_value on data/xfv.json (kind=active), joined to "
                  "timeseries.json for identity; MLB rows: HEM+ / SEM+ leaders off the "
                  "committed leaderboards"),
        "note": ("Curated list. Regenerate with `python card_prices_ingest.py "
                 "--build-watchlist`, then hand-edit freely: a set/parallel descriptor is a "
                 "hobby judgement, not a model output."),
        "cadence": dict(CADENCE),
        "grade_buckets": list(GRADE_BUCKETS),
        "cards": cards,
    }


def write_watchlist(doc: dict, path: Path | str | None = None) -> Path:
    p = Path(path) if path else WATCHLIST_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return p


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Card comps ingest (CSV drop + optional scraper)")
    ap.add_argument("--drops", action="store_true", help="ingest every data/drops/card_comps_*.csv")
    ap.add_argument("--csv", help="ingest ONE csv file")
    ap.add_argument("--scrape", action="store_true", help=f"scrape (needs {SCRAPE_ENV_FLAG}=1)")
    ap.add_argument("--hot", action="store_true", help="scrape only the hot list")
    ap.add_argument("--build-watchlist", action="store_true", help="regenerate data/card_watchlist.json")
    ap.add_argument("--stats", action="store_true", help="what is in the comp store")
    a = ap.parse_args(argv)
    did = False
    if a.build_watchlist:
        doc = build_watchlist()
        p = write_watchlist(doc)
        print(f"watchlist: {len(doc['cards'])} cards -> {p}")
        did = True
    if a.csv:
        print(json.dumps(ingest_csv(a.csv), indent=1))
        did = True
    if a.drops:
        print(json.dumps(ingest_drops(), indent=1))
        did = True
    if a.scrape:
        wl = load_watchlist()
        cards = [c for c in (wl.get("cards") or []) if (c.get("hot") or not a.hot)]
        cards = due_cards({"cards": cards}, last_seen=last_seen_map())
        print(json.dumps(scrape_cards(cards), indent=1))
        did = True
    if a.stats or not did:
        print(json.dumps(store_stats(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
