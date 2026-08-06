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
    python card_prices_ingest.py --scheduled             # THE pipeline/cron entry point
    python card_prices_ingest.py --drops                 # ingest every un-ingested drop
    python card_prices_ingest.py --csv path/to/file.csv  # ingest one file
    python card_prices_ingest.py --scrape --hot          # needs EEPHUS_CARD_SCRAPE=1
    python card_prices_ingest.py --build-watchlist       # regenerate data/card_watchlist.json
    python card_prices_ingest.py --stats                 # what is in the store

SCHEDULING
----------
`run_scheduled_ingest()` is the ONE entry point the pipeline and the box crontab
both call, so the two cannot drift apart about what the cadence is. It reads
CADENCE, not its caller: drops every run, the hot list daily, a full sweep on
`CADENCE['full_sweep_weekday']`. It is safe to invoke twice in a day (the
run ledger below refuses a second fetch of the same scope on the same date), so
the belt-and-braces cron entry and the nightly pipeline step can both exist,
exactly like the leaderboard-vintage snapshot they sit next to.
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
    # Python weekday(), so 6 = Sunday. The long tail is ALSO covered by
    # due_cards' 7-day rule, but that rule spreads the tail across whichever
    # nights each card happens to age out on, which makes "did the sweep
    # actually complete" unanswerable. Pinning the sweep to one weekday makes
    # the 60-day guarantee above checkable: a missed Sunday is one visible gap,
    # not a diffuse drift.
    "full_sweep_weekday": 6,
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

-- SCRAPE RUN LEDGER. Two jobs, and the second one is the important one.
--
--   (1) Idempotency at the RUN level: PK (ran_on, scope) is what lets the
--       nightly pipeline step and the belt-and-braces cron entry both exist
--       without fetching the same pages twice in a night.
--   (2) It is the ONLY durable record that a scrape ran at all. parse_sold_html
--       is built to yield ZERO rows on layout drift, which means a broken parser
--       and a genuinely quiet market write exactly the same thing to card_comps:
--       nothing. Without these counters the export cannot tell "no comps yet"
--       (legitimate, and the state /cards/ has been in since it shipped) from
--       "the scrape fetched 12 pages and parsed 0 sales" (a parser regression).
--       cards_fetched vs rows_parsed is that distinction, and
--       card_market_export.ingest_state reads it to publish which one is true.
CREATE TABLE IF NOT EXISTS card_scrape_runs (
    ran_on          TEXT NOT NULL,       -- ISO yyyy-mm-dd
    scope           TEXT NOT NULL,       -- 'hot' | 'full' | 'adhoc'
    ran_at          TEXT NOT NULL,       -- ISO timestamp of the latest attempt that day
    cards_attempted INTEGER NOT NULL DEFAULT 0,
    cards_fetched   INTEGER NOT NULL DEFAULT 0,   -- pages that came back at all
    cards_zero_rows INTEGER NOT NULL DEFAULT 0,   -- fetched but parsed nothing
    fetch_errors    INTEGER NOT NULL DEFAULT 0,
    rows_parsed     INTEGER NOT NULL DEFAULT 0,
    rows_stored     INTEGER NOT NULL DEFAULT 0,   -- new rows; 0 with rows_parsed>0 is HEALTHY (re-seen sales)
    PRIMARY KEY (ran_on, scope)
);
CREATE INDEX IF NOT EXISTS idx_card_scrape_runs ON card_scrape_runs(ran_on);
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


def store_health(con=None) -> dict:
    """The PUBLISHABLE subset of store_stats: counts plus the date WE last stored
    something. Deliberately not store_stats itself, which reports first_sale and
    last_sale - those are sale dates, and a sale date is one of the raw facts
    this module refuses to publish, aggregate or not. `last_ingest_on` is our own
    operational timestamp, so it carries the same "is the tap on?" information
    without quoting anybody's sale."""
    def _q(c):
        c.executescript(SCHEMA)
        r = c.execute("SELECT COUNT(*) n, COUNT(DISTINCT card_id) cards, "
                      "MAX(substr(ingested_at,1,10)) last_in FROM card_comps").fetchone()
        return {"comps": r["n"] or 0, "cards": r["cards"] or 0,
                "last_ingest_on": r["last_in"]}
    if con is not None:
        return _q(con)
    with _connect() as c:
        return _q(c)


def record_scrape_run(stats: dict, con=None, today: date | None = None) -> dict:
    """Stamp one scrape attempt into card_scrape_runs.

    INSERT OR REPLACE on (ran_on, scope) so a same-day re-run corrects its own
    row rather than accumulating; yesterday's row is never touched, exactly like
    card_index_history's (card_id, as_of)."""
    today = today or date.today()
    row = {
        "ran_on": today.isoformat(),
        "scope": str(stats.get("scope") or "adhoc"),
        "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cards_attempted": int(stats.get("cards") or 0),
        "cards_fetched": int(stats.get("cards_fetched") or 0),
        "cards_zero_rows": int(stats.get("cards_zero_rows") or 0),
        "fetch_errors": int(stats.get("fetch_errors") or 0),
        "rows_parsed": int(stats.get("parsed") or 0),
        "rows_stored": int(stats.get("stored") or 0),
    }

    def _w(c):
        c.executescript(SCHEMA)
        c.execute(
            "INSERT OR REPLACE INTO card_scrape_runs (ran_on, scope, ran_at, "
            "cards_attempted, cards_fetched, cards_zero_rows, fetch_errors, "
            "rows_parsed, rows_stored) VALUES (?,?,?,?,?,?,?,?,?)",
            (row["ran_on"], row["scope"], row["ran_at"], row["cards_attempted"],
             row["cards_fetched"], row["cards_zero_rows"], row["fetch_errors"],
             row["rows_parsed"], row["rows_stored"]))
    if con is not None:
        _w(con)
    else:
        with _connect() as c:
            _w(c)
    return row


def last_scrape_run(scope: str | None = None, con=None) -> dict | None:
    """The newest recorded scrape attempt, or None when none was ever recorded.
    None is itself an answer: it means no scrape has EVER run on this box, which
    is what the export publishes as the legitimate empty state."""
    def _q(c):
        c.executescript(SCHEMA)
        q = ("SELECT ran_on, scope, ran_at, cards_attempted, cards_fetched, "
             "cards_zero_rows, fetch_errors, rows_parsed, rows_stored "
             "FROM card_scrape_runs")
        args: tuple = ()
        if scope:
            q += " WHERE scope = ?"
            args = (scope,)
        q += " ORDER BY ran_on DESC, ran_at DESC LIMIT 1"
        r = c.execute(q, args).fetchone()
        return dict(r) if r is not None else None
    if con is not None:
        return _q(con)
    with _connect() as c:
        return _q(c)


def drop_health(con=None) -> dict:
    """What the CSV drop path has done, from card_drop_files.

    `last_rows_parsed` is the newest file's rows_seen, which parse_drop_csv sets
    to the number of rows it actually understood. Zero on a file that exists is
    the drop-side twin of a zero-row scrape: the operator dropped something and
    the parser read none of it, which is a column-contract break, not an empty
    market. Filenames are NOT returned: they are not raw comps, but they are also
    not needed to answer the question, and the narrowest surface wins."""
    def _q(c):
        c.executescript(SCHEMA)
        n = c.execute("SELECT COUNT(*) n, SUM(rows_seen) seen, SUM(rows_stored) stored "
                      "FROM card_drop_files").fetchone()
        last = c.execute("SELECT rows_seen, rows_stored, substr(ingested_at,1,10) d "
                         "FROM card_drop_files ORDER BY ingested_at DESC, filename DESC "
                         "LIMIT 1").fetchone()
        return {
            "files": n["n"] or 0,
            "rows_parsed": n["seen"] or 0,
            "rows_stored": n["stored"] or 0,
            "last_rows_parsed": (last["rows_seen"] if last is not None else None),
            "last_rows_stored": (last["rows_stored"] if last is not None else None),
            "last_ingested_on": (last["d"] if last is not None else None),
        }
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
        return {"files": [], "stored": 0, "parsed": 0}
    files = sorted(d.glob("card_comps_*.csv"))
    res = [ingest_csv(f, watchlist, con=con) for f in files]
    # `parsed` rather than only `stored`: on every run after the first, a drop
    # file re-reads to stored=0 because every row is already on file, and a
    # caller that only sees stored=0 cannot tell that from a file the parser
    # could not read. parsed is the number that says the tap worked.
    return {"files": res, "stored": sum(r["stored"] for r in res),
            "parsed": sum(r["parsed"] for r in res)}


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


def scrape_cards(cards, fetch=None, throttle=None, con=None, source_host="marketplace",
                 scope: str = "adhoc", record: bool = True, today: date | None = None) -> dict:
    """Fetch sold comps for `cards`. Refuses to run unless EEPHUS_CARD_SCRAPE=1.

    `fetch` is injected in tests (fixtures only).

    THE COUNTERS ARE THE POINT, not a nicety. parse_sold_html is designed to
    yield zero rows on layout drift, and a zero-row scrape writes exactly what a
    quiet market writes: nothing. So this returns cards_fetched (pages that came
    back) alongside parsed (sales understood), and stamps both into
    card_scrape_runs when `record`. cards_fetched > 0 with parsed == 0 across a
    whole batch is a parser regression and card_market_export publishes it as
    one; without these two numbers side by side that case is indistinguishable
    from the honest empty state and would go on looking healthy forever."""
    cards = list(cards or [])
    if fetch is None and not scrape_enabled():
        log.warning("card scrape requested but %s is not 1; refusing (use the CSV drop path)",
                    SCRAPE_ENV_FLAG)
        return {"enabled": False, "cards": 0, "stored": 0, "parsed": 0,
                "cards_fetched": 0, "cards_zero_rows": 0, "fetch_errors": 0,
                "scope": scope, "reason": "flag off"}
    fetch = fetch or _default_fetch
    thr = throttle or Throttle()
    stored = total = fetched = zero_rows = errors = 0
    for c in cards:
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
            errors += 1
            log.exception("card scrape: fetch failed for %s", cid)
            continue
        fetched += 1
        rows = parse_sold_html(html)
        if not rows:
            zero_rows += 1
            log.warning("card scrape: zero rows parsed for %s (layout change or no sales)", cid)
        comps = [Comp(card_id=cid,
                      listing_hash=listing_fingerprint(cid, r["sold_date"], r["price"], r["grade"], r["title"]),
                      sold_date=r["sold_date"], price_usd=r["price"], grade=r["grade"],
                      source=f"scrape:{source_host}", player_key=c.get("player_key"),
                      mlbam=c.get("mlbam"), title=r["title"]) for r in rows]
        ins, _dup = store_comps(comps, con=con)
        stored += ins
        total += len(comps)
    if fetched and zero_rows == fetched:
        # The batch-level statement of the same warning the loop logs per card.
        # ERROR because "every page we could read contained no sale we could
        # read" is a parser fact, and it is the sentence somebody scanning a
        # nightly log needs to see without counting warnings.
        log.error("card scrape: fetched %d pages and parsed ZERO sales from all of "
                  "them - treat this as layout drift until proven otherwise", fetched)
    out = {"enabled": True, "cards": len(cards), "parsed": total, "stored": stored,
           "cards_fetched": fetched, "cards_zero_rows": zero_rows,
           "fetch_errors": errors, "scope": scope}
    # A run that attempted nothing (nothing was due) is NOT recorded: it would
    # replace the day's real counters with zeros and make the newest ledger row
    # say "fetched nothing" about a scrape that never intended to fetch.
    if record and (fetched or errors):
        record_scrape_run(out, con=con, today=today)
    return out


# ── the scheduled run (ONE entry point for the pipeline and the crontab) ────
def scrape_scope_for(today: date | None = None) -> str:
    """'full' on the sweep weekday, 'hot' otherwise. The module decides, so the
    box schedule stays a dumb 'call this every night' and cannot encode a second
    opinion about the cadence."""
    today = today or date.today()
    return "full" if today.weekday() == int(CADENCE["full_sweep_weekday"]) else "hot"


def run_scheduled_ingest(today: date | None = None, con=None, fetch=None,
                         drops_dir: Path | str | None = None,
                         watchlist: dict | None = None, log_fn=None) -> dict:
    """THE nightly ingest. Drops always, then the scrape when it is armed and due.

    Called by run_monthly (step 6g-pre and daily step 9f) and by the box crontab
    (deploy/betting-crontab.example). Both call the SAME function on purpose:
    when the cadence lives in one place, a cron line and a pipeline step cannot
    quietly disagree about what "daily" meant.

    SAFE TO RUN TWICE IN A DAY, which is what makes that pair legal. A monthly
    night runs this at step 6g-pre and then again in the chained daily tail
    fifteen minutes later; the crontab entry may add a third. The drop path is
    already idempotent at the row and file level, and the scrape is guarded by
    card_scrape_runs: a scope already fetched today is skipped rather than
    re-fetched, so no marketplace sees the same page twice in a night no matter
    how many callers fire.

    NO-OPS SAFELY WITH THE FLAG UNSET, which is the state of every box today:
    the drop path runs (it needs no network), the scrape reports enabled=False
    with a stated reason, and nothing raises."""
    today = today or date.today()
    say = log_fn or log.info
    out: dict = {"date": today.isoformat(), "scope": scrape_scope_for(today)}

    try:
        drops = ingest_drops(drops_dir, watchlist, con=con)
    except Exception:
        log.exception("card ingest: drop pass failed")
        drops = {"files": [], "stored": 0, "parsed": 0, "error": True}
    out["drops"] = drops
    if drops.get("files"):
        say("card drops: %d file(s), %d rows parsed, %d new"
            % (len(drops["files"]), drops.get("parsed") or 0, drops.get("stored") or 0))

    scope = out["scope"]
    if fetch is None and not scrape_enabled():
        out["scrape"] = {"enabled": False, "scope": scope, "cards": 0, "parsed": 0,
                         "stored": 0, "reason": f"{SCRAPE_ENV_FLAG} is not 1"}
        say("card scrape: not armed (%s unset); drops are the only input tonight"
            % SCRAPE_ENV_FLAG)
        return out

    prior = last_scrape_run(scope, con=con)
    if prior and prior.get("ran_on") == today.isoformat():
        out["scrape"] = {"enabled": True, "scope": scope, "cards": 0, "parsed": 0,
                         "stored": 0, "skipped": True,
                         "reason": f"scope '{scope}' already fetched today"}
        say("card scrape: scope '%s' already ran today (%d pages, %d sales); skipping"
            % (scope, prior.get("cards_fetched") or 0, prior.get("rows_parsed") or 0))
        return out

    wl = watchlist if watchlist is not None else load_watchlist()
    cards = list(wl.get("cards") or [])
    if scope == "hot":
        cards = [c for c in cards if c.get("hot")]
    try:
        cards = due_cards({"cards": cards}, today=today, last_seen=last_seen_map(con=con))
    except Exception:
        log.exception("card ingest: could not read the last-seen map; scraping the "
                      "whole %s list rather than skipping the night", scope)
    if not cards:
        out["scrape"] = {"enabled": True, "scope": scope, "cards": 0, "parsed": 0,
                         "stored": 0, "skipped": True,
                         "reason": "no card is due under CADENCE"}
        say("card scrape: nothing due in scope '%s' tonight" % scope)
        return out

    try:
        out["scrape"] = scrape_cards(cards, fetch=fetch, con=con, scope=scope, today=today)
    except Exception:
        log.exception("card scrape: crashed; the drop path already ran")
        out["scrape"] = {"enabled": True, "scope": scope, "cards": len(cards),
                         "parsed": 0, "stored": 0, "error": True}
    s = out["scrape"]
    say("card scrape (%s): %d due, %d fetched, %d parsed, %d new, %d zero-row, %d errors"
        % (scope, s.get("cards") or 0, s.get("cards_fetched") or 0, s.get("parsed") or 0,
           s.get("stored") or 0, s.get("cards_zero_rows") or 0, s.get("fetch_errors") or 0))
    return out


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
    ap.add_argument("--scheduled", action="store_true",
                    help="the nightly run: drops + the due scrape under CADENCE "
                         "(what run_monthly and the crontab both call)")
    ap.add_argument("--drops", action="store_true", help="ingest every data/drops/card_comps_*.csv")
    ap.add_argument("--csv", help="ingest ONE csv file")
    ap.add_argument("--scrape", action="store_true", help=f"scrape (needs {SCRAPE_ENV_FLAG}=1)")
    ap.add_argument("--hot", action="store_true", help="scrape only the hot list")
    ap.add_argument("--build-watchlist", action="store_true", help="regenerate data/card_watchlist.json")
    ap.add_argument("--stats", action="store_true", help="what is in the comp store")
    a = ap.parse_args(argv)
    did = False
    if a.scheduled:
        print(json.dumps(run_scheduled_ingest(), indent=1))
        did = True
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
        # Recorded under the SCHEDULED scope name, not 'adhoc', so a hand-run
        # scrape suppresses tonight's automatic one instead of doubling it. A
        # manual pull is still a real pull as far as the marketplace is concerned.
        print(json.dumps(scrape_cards(cards, scope="hot" if a.hot else "full"), indent=1))
        did = True
    if a.stats or not did:
        print(json.dumps(store_stats(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
