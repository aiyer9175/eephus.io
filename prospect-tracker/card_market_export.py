# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""card_market_export.py - data/card_market.json for the /cards/ module.

WHAT THIS PUBLISHES
-------------------
Per watchlist card, three derived numbers and one label:

  1. THE EEPHUS CARD INDEX - a grade-mix adjusted trimmed median of the sold
     comps inside a rolling window (INDEX_WINDOW_DAYS). Arithmetic in full:

       a. Keep comps with sold_date inside (as_of - W, as_of].
       b. Grade-adjust each price onto the card's own grade bucket:
            adjusted = price * GRADE_FACTORS[target] / GRADE_FACTORS[sold_grade]
          A comp whose grade is not in the table is DROPPED, not guessed.
       c. Trimmed median: drop adjusted prices outside TRIM_LOW_MULT to
          TRIM_HIGH_MULT times the window's RAW median, then take the median of
          what is left. The trim is by value rather than by count on purpose;
          trimmed_median's docstring says why in full.
       d. Publish on a coarse grid (see _publish_round). The grid is
          deliberate: a median of an odd sample can coincide with one observed
          sale price, and this module's whole posture is that it publishes a
          statistic, not a listing.
     Fewer than MIN_COMPS comps in the window -> index is null with a stated
     reason. A null index is a visible empty cell on the page, never a zero.

  2. TREND - the same index computed over the PRIOR window, and the percent
     change between them. Null when either leg is null.

  3. THE BUY SIGNAL - a gap between where the player ranks on TALENT and where
     his card ranks on PRICE, both as percentiles inside the watchlist. Talent
     is the shared dynasty_blend eFV composite, the same module and weights
     fantasy_export._dynasty_prospects ranks with; price is the Card Index.

       gap = talent_percentile - market_percentile        (both 0-100)

WHY v1 IS A SCREEN AND SAYS SO
------------------------------
`screen: true` is in the payload and the label is on the page. There is no
price-history backtest: the module has no price history yet, because we are
only now starting to keep one (card_index_history). The signal thresholds
(BUY_GAP / FADE_GAP) are CONVENTIONS chosen for legibility, not fitted values,
and the payload says that in words. This follows the PAL RP->SP precedent: ship
the screen, label it a screen, accumulate the data that could one day validate
it, and never let a screen wear a forecast's clothes.

WHAT NEVER LEAVES
-----------------
No raw comps. No sale prices, sale dates, listing titles, listing ids, source
URLs or per-listing anything. `load_comps` already drops the local-only fields,
and test_card_market asserts the absence on the built payload. Raw comps stay in
prospects.db (gitignored) forever.

WHY THE BOARD IS EMPTY, PUBLISHED
---------------------------------
`meta.ingest` states which of three very different things a zero-priced board
means: nothing has been ingested yet (honest, and the state /cards/ shipped in),
the ingest RAN and understood nothing (a parser regression), or every request
was refused before a page came back (a blocked source, which is what eBay does
to this module today). parse_sold_html is deliberately built to yield zero rows
on layout drift, and a blocked fetch stores nothing either, which makes all
three byte-identical in the comp store; so the counters that separate them ride
into the payload and the two broken cases file an ingest-health RED through
bullpen_export._ingest_red. Counts and our own ingest dates only: no sale price,
no sale date, nothing that would smuggle a comp in as diagnostics.

ONE eFV BASIS
-------------
Every eFV read goes through fantasy_export._board_grade, which is
efv_board_scale.board_value plus the standing fallback chain. No copy of the
scale coefficients exists here and no second basis is introduced.

Run: `python card_market_export.py` (add `--eval` to refresh the
pre-registration artifact). Best-effort: a missing input degrades to a loud
empty payload, never an exception into the pipeline.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import card_prices_ingest as ci
import dynasty_blend

log = logging.getLogger("card_market_export")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "card_market.json"
EVAL_PATH = DATA_DIR / "card_market_eval.json"

# ── index parameters (the documented constants) ─────────────────────────────
INDEX_WINDOW_DAYS = 45
PRIOR_WINDOW_DAYS = 45          # the window immediately before the current one
MIN_COMPS = 5
# Trim band, as multiples of the window's raw median. Sales outside it are
# dropped before the median is taken. See trimmed_median for why the trim is by
# value and not by count.
TRIM_LOW_MULT = 0.20
TRIM_HIGH_MULT = 5.00
HISTORY_POINTS = 26             # index history points carried into the payload

# Grade multipliers relative to a PSA 10. Hobby-standard ordering, deliberately
# COARSE: they exist to stop a raw-card sale from dragging a PSA 10 index down,
# not to price grades precisely. They are a stated convention, published in the
# payload's method block so a reader can disagree with a number they can see.
GRADE_FACTORS = {
    "PSA 10": 1.00,
    "BGS 9.5": 0.72,
    "SGC 10": 0.85,
    "CGC 10": 0.80,
    "PSA 9": 0.42,
    "BGS 9": 0.38,
    "SGC 9": 0.36,
    "PSA 8": 0.24,
    "RAW": 0.28,
}

# Signal bands. CONVENTIONS, not fitted thresholds. There is no backtest to fit
# them on; inventing a number and calling it measured is the thing this shop
# does not do.
BUY_GAP = 20.0
FADE_GAP = -20.0

# The talent blend lives in dynasty_blend (imported above), shared with
# fantasy_export._dynasty_prospects. Until 2026-08-16 this file carried a CLONE
# of the weights, introduced with a comment promising "same weights, same
# inputs, stated here in full so the two cannot silently disagree" - and they
# had already silently disagreed: this clone decayed ETA proximity at 0.25 per
# year against the fantasy module's 0.18, and the parity test hand-computed its
# expectation from the clone's own constants, pinning the clone against itself.
# Converging on 0.18 moved only the talent-percentile column of unpriced cards
# (0 cards were priced on the day of the fix). The import replaces the promise
# with a mechanism.
#
# _board_grade is imported plainly (2026-08-16): the except arm that used to sit
# here re-implemented the board-grade fallback chain, a third copy of logic this
# module exists to not duplicate, and it had never once run. If fantasy_export
# cannot import, that is a pipeline failure to surface, not to paper over with a
# quietly divergent shim.
from fantasy_export import _board_grade


def _load_json(name: str, data_dir: Path | None = None):
    p = (data_dir or DATA_DIR) / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("card market: %s unreadable", name)
        return None


# ── the index arithmetic ────────────────────────────────────────────────────
def _median(xs):
    n = len(xs)
    if not n:
        return None
    s = sorted(xs)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def trim(values, lo_mult: float = TRIM_LOW_MULT, hi_mult: float = TRIM_HIGH_MULT):
    """Drop values outside [lo_mult, hi_mult] x the raw median. Returns the kept
    list (sorted). See trimmed_median for why the trim is by VALUE, not by count."""
    xs = [float(v) for v in (values or []) if v is not None]
    m0 = _median(xs)
    if m0 is None or m0 <= 0:
        return sorted(xs)
    lo, hi = m0 * lo_mult, m0 * hi_mult
    return sorted(v for v in xs if lo <= v <= hi)


def trimmed_median(values, lo_mult: float = TRIM_LOW_MULT, hi_mult: float = TRIM_HIGH_MULT):
    """THE index estimator: trim, then median.

    WHY THE TRIM IS BY VALUE AND NOT BY COUNT, which is worth stating because
    the obvious implementation is wrong: symmetric COUNT trimming cannot move a
    median. Dropping k values from each tail leaves the middle order statistics
    exactly where they were, so a "10 percent trimmed median" is byte-identical
    to a plain median at every n. It would have been decorative arithmetic.

    What actually contaminates card comps is not a count of extremes, it is
    off-card sales that survive the query: a five-dollar lot of base cards, a
    reprint, a mis-parsed price, a different parallel. Those arrive in CLUSTERS,
    which is exactly the case a plain median does not handle. So the trim is a
    band around the raw median: keep sales inside [lo_mult, hi_mult] x median,
    then take the median of what is left. On a fixture of three $5 lots plus
    four real $100-ish sales, the plain median is $100 and this is $101, because
    the lots are gone rather than half-counted.

    Deterministic, and the test pins it against a hand-computed fixture."""
    kept = trim(values, lo_mult, hi_mult)
    return _median(kept)


def grade_adjust(price: float, sold_grade: str, target_grade: str):
    """Move one sale onto the card's own grade bucket. None when either grade is
    outside the table: an unknown grade is dropped, never assumed."""
    f_sold = GRADE_FACTORS.get((sold_grade or "").strip().upper().replace("PSA10", "PSA 10"))
    f_target = GRADE_FACTORS.get((target_grade or "").strip().upper())
    if not f_sold or not f_target:
        return None
    return float(price) * (f_target / f_sold)


def _publish_round(v):
    """The published grid. Coarse on purpose (see the module docstring): a
    published index is a statistic about a market, not a quotation of a sale."""
    if v is None:
        return None
    v = float(v)
    if v < 100:
        return round(v)
    if v < 1000:
        return int(round(v / 5.0) * 5)
    return int(round(v / 25.0) * 25)


def card_index(comps, target_grade: str, as_of: date,
               window_days: int = INDEX_WINDOW_DAYS, offset_days: int = 0) -> dict:
    """The Card Index for ONE card over ONE window.

    `offset_days` shifts the window back, which is how the prior-window leg is
    computed with the same code path (offset=window_days)."""
    hi = as_of - timedelta(days=offset_days)
    lo = hi - timedelta(days=window_days)
    adj, n_win, n_dropped = [], 0, 0
    for c in (comps or []):
        try:
            d = date.fromisoformat(str(c.get("sold_date"))[:10])
        except (TypeError, ValueError):
            continue
        if not (lo < d <= hi):
            continue
        n_win += 1
        a = grade_adjust(c.get("price_usd"), c.get("grade"), target_grade)
        if a is None:
            n_dropped += 1
            continue
        adj.append(a)
    kept = trim(adj)
    if len(kept) < MIN_COMPS:
        return {"index": None, "n": len(kept), "n_window": n_win,
                "n_grade_dropped": n_dropped, "n_trimmed": len(adj) - len(kept),
                "reason": "thin" if n_win else "no comps",
                "window": [lo.isoformat(), hi.isoformat()]}
    raw = _median(kept)
    return {"index": _publish_round(raw), "index_exact": raw, "n": len(kept),
            "n_window": n_win, "n_grade_dropped": n_dropped,
            "n_trimmed": len(adj) - len(kept), "reason": None,
            "window": [lo.isoformat(), hi.isoformat()]}


def percentile_ranks(pairs) -> dict:
    """{key: 0-100 percentile} over (key, value) pairs; None values excluded.
    Ties share the midpoint rank, so two identical prices cannot be called a
    gap. Single-item pools get 50.0 (a percentile of one is meaningless)."""
    vals = [(k, float(v)) for k, v in pairs if v is not None]
    n = len(vals)
    if n == 0:
        return {}
    if n == 1:
        return {vals[0][0]: 50.0}
    vals.sort(key=lambda kv: kv[1])
    out, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and vals[j + 1][1] == vals[i][1]:
            j += 1
        mid = (i + j) / 2.0
        pct = round(100.0 * mid / (n - 1), 1)
        for t in range(i, j + 1):
            out[vals[t][0]] = pct
        i = j + 1
    return out


def talent_score(xr: dict, eta_year=None, season: int | None = None):
    """The eFV talent composite, through the SHARED dynasty_blend module: the
    same function objects fantasy_export._dynasty_prospects ranks with, so the
    two surfaces cannot silently disagree about the arithmetic again.

    Returns (score, displayed_efv). Both legs are THE board number via
    _board_grade: since the 2026-08-16 driver swap the blend drives on the same
    grade the row displays (the retired quantile survives only inside
    _board_grade's own fallback chain), so /cards/ scores and shows the same
    eFV basis as PROSPX and /fantasy/."""
    if not isinstance(xr, dict):
        return (None, None)
    season = season or date.today().year
    grade = _board_grade(xr)
    if grade is None:
        return (None, None)
    pb = xr.get("p_bucket") or {}
    star = pb.get("star") or 0.0
    bust = xr.get("p_bust")
    if bust is None:
        bust = pb.get("bust") or 0.0
    score = dynasty_blend.blend_score(
        grade, star, bust,
        dynasty_blend.eta_proximity(eta_year, season),
        dynasty_blend.surplus_norm(xr.get("surplus_mm")))
    return (round(score, 1), grade)


def signal_for(gap):
    if gap is None:
        return "unpriced"
    if gap >= BUY_GAP:
        return "buy"
    if gap <= FADE_GAP:
        return "fade"
    return "hold"


# ── ingest state: why is this board empty? ──────────────────────────────────
# THE DISTINCTION THIS SECTION EXISTS FOR. Until 2026-08-05 the /cards/ board
# served 40 tracked cards and 0 priced, forever, because card_prices_ingest had
# no scheduled caller anywhere: run_monthly ran only the export, and the
# EEPHUS_CARD_SCRAPE flag armed a scraper nothing invoked. The board looked
# exactly the way it will look on the night the parser breaks.
#
# Those three are not the same thing and must never publish the same way:
#
#   "no comps yet"        nothing has been ingested. Legitimate, honest, and the
#                         state the page already states in words.
#   "ran and parsed none" the scrape fetched pages and understood zero sales.
#                         parse_sold_html is BUILT to yield nothing on layout
#                         drift (that is its whole design, chosen over a
#                         selector parse that would yield plausible garbage), so
#                         this is the expected shape of a marketplace redesign,
#                         and it must be loud rather than quiet.
#   "nothing came back"   every request errored before a page arrived. Measured
#                         2026-08-06: eBay 403s this module on both armed nights,
#                         22 attempted and 22 errors, identically for the honest
#                         module UA and for a plain browser UA. A different
#                         parser cannot fix a page that was never served, so this
#                         is the one state that says the SOURCE has to change.
#
# The loud half of parse_sold_html currently lives in a log line, and a log line
# on a nightly box is not a signal anybody sees. So the counters ride into the
# artifact, and the second case files an ingest-health RED through the sanctioned
# bullpen_export path.
#
# A batch this size or larger that parsed nothing at all is drift, not a quiet
# market: forty tracked cards do not go simultaneously silent, and three is the
# smallest batch where "every single one had no sales" stops being plausible.
PARSE_REGRESSION_MIN_CARDS = 3
# The same floor, for the same reason, applied one step further upstream: a batch
# where every single request failed before a page came back. Below three attempts
# "they all failed" is a coincidence; at or above it, it is a wall. Aliased rather
# than re-typed so the two thresholds cannot drift into disagreeing about how many
# failures constitute a pattern.
FETCH_BLOCKED_MIN_CARDS = PARSE_REGRESSION_MIN_CARDS
# How long the store may go without a new row before the page says so. Longer
# than the 7-day long-tail cadence and shorter than the 45-day index window, so
# it fires while the index is still computable rather than after it has already
# gone null.
STALE_INGEST_DAYS = 14

INGEST_STATES = {
    "no_comps_yet": (
        "No comps have been ingested yet, so every index is null by construction. "
        "This is the honest empty state, not a failure."),
    "ingest_ran_empty": (
        "An ingest ran and stored nothing. Too few pages were read to call it a "
        "parser regression, so it is reported rather than flagged."),
    "parse_regression": (
        "The scrape fetched pages and parsed ZERO sales from all of them. The "
        "parser is built to yield nothing on layout drift, so this is a parser "
        "regression until proven otherwise, not a quiet market."),
    "fetch_blocked": (
        f"Every one of at least {FETCH_BLOCKED_MIN_CARDS} scrape requests failed "
        "before a page came back. Nothing was fetched, so no parser change can "
        "help: the source is refusing the fetcher and the board stays dark until "
        "a reachable source is wired."),
    "drop_parse_empty": (
        "The newest CSV drop parsed zero usable rows. That is a column-contract "
        "break, not an empty market; see docs/diamond-cards.md section 3."),
    "stale": (
        f"Comps are on file but nothing new has been stored in {STALE_INGEST_DAYS} "
        "days. The scheduled ingest is not reaching the store."),
    "ok": "Comps are being ingested on schedule.",
}

# The states that mean SOMETHING BROKE, as opposed to the ones that mean nothing
# has happened yet. Only these file a RED, because an ingest-health line that
# fires on the honest empty state teaches everyone to ignore it.
INGEST_RED_STATES = ("parse_regression", "drop_parse_empty", "fetch_blocked")


def _ingest_red(source: str, message: str) -> None:
    """File a card-ingest failure into the ingest-health RED ledger.

    Reuses bullpen_export._ingest_red rather than growing a third mechanism: it
    is the sanctioned template from the 2026-08-05 silent-empty sweep, and it
    already carries the "reporting must never break a board" posture. Imported
    lazily so this module never pays for bullpen_export's feed_cache import on a
    build that has no ingest news to file."""
    try:
        from bullpen_export import _ingest_red as _red
        _red(source, message)
    except Exception:                      # noqa: BLE001 - reporting never breaks a board
        log.debug("card market: could not file the ingest anomaly for %s", source,
                  exc_info=True)


def ingest_state(store: dict | None = None, scrape: dict | None = None,
                 drops: dict | None = None, armed: bool = False,
                 today: date | None = None) -> dict:
    """Classify why the store looks the way it does. Pure function of its inputs.

    Ordered most-diagnostic first: a parse regression outranks an empty store,
    because when both are true the regression is the thing that needs fixing and
    the empty store is only its symptom."""
    today = today or date.today()
    store = store or {}
    drops = drops or {}
    n_comps = int(store.get("comps") or 0)
    last_in = store.get("last_ingest_on")
    days_since = None
    if last_in:
        try:
            days_since = (today - date.fromisoformat(str(last_in)[:10])).days
        except ValueError:
            days_since = None

    attempted = int((scrape or {}).get("cards_attempted") or 0)
    fetched = int((scrape or {}).get("cards_fetched") or 0)
    errors = int((scrape or {}).get("fetch_errors") or 0)
    parsed = int((scrape or {}).get("rows_parsed") or 0)
    drop_files = int(drops.get("files") or 0)
    drop_last_parsed = drops.get("last_rows_parsed")

    # A WHOLLY BLOCKED FETCHER OUTRANKS EVERY OTHER READING, and it is checked
    # first because it is the most upstream one: nothing was read, so nothing
    # downstream of the read can be diagnosed from this run. Until 2026-08-07 this
    # case had no state of its own - fetch_errors was not even read here - so two
    # nights of 22 attempted / 0 fetched / 22 errors classified as
    # ingest_ran_empty with red:false, and the board could have stayed dark
    # forever while reporting the honest empty state. It is mutually exclusive
    # with parse_regression by construction (that one needs pages that came back).
    if (attempted >= FETCH_BLOCKED_MIN_CARDS and fetched <= 0
            and errors >= attempted):
        state = "fetch_blocked"
    elif fetched >= PARSE_REGRESSION_MIN_CARDS and parsed <= 0:
        state = "parse_regression"
    elif drop_files and drop_last_parsed is not None and int(drop_last_parsed) <= 0:
        state = "drop_parse_empty"
    elif n_comps <= 0:
        # Nothing on file. Whether that is honest depends entirely on whether
        # anything ever tried: a store that has never been written to is the
        # designed initial state, a store that something wrote nothing into is a
        # different sentence and gets a different one.
        state = "no_comps_yet" if (scrape is None and not drop_files) else "ingest_ran_empty"
    elif days_since is not None and days_since > STALE_INGEST_DAYS:
        state = "stale"
    else:
        state = "ok"

    out = {
        "state": state,
        "why": INGEST_STATES[state],
        "red": state in INGEST_RED_STATES,
        "scrape_armed": bool(armed),
        "comps_on_file": n_comps,
        "cards_with_comps": int(store.get("cards") or 0),
        "last_ingest_on": last_in,
        "days_since_ingest": days_since,
        "parse_regression_min_cards": PARSE_REGRESSION_MIN_CARDS,
        "drops": {
            "files": drop_files,
            "rows_parsed": int(drops.get("rows_parsed") or 0),
            "rows_stored": int(drops.get("rows_stored") or 0),
            "last_rows_parsed": drop_last_parsed,
            "last_ingested_on": drops.get("last_ingested_on"),
        },
        # None means no scrape has EVER run on this box, which is itself the
        # answer to "why is the board empty" and reads better than zeros.
        "last_scrape": dict(scrape) if scrape else None,
    }
    return out


def collect_ingest_facts(con=None, today: date | None = None) -> dict:
    """Read the ingest facts out of the comp store and classify them.

    Best-effort in the module's house style: an unreadable store must not stop
    the export, so a failure here publishes an explicitly unknown state rather
    than an implicitly healthy one."""
    try:
        store = ci.store_health(con=con)
        scrape = ci.last_scrape_run(con=con)
        drops = ci.drop_health(con=con)
    except Exception:
        log.exception("card market: ingest ledger unreadable")
        return {"state": "unknown", "red": False, "scrape_armed": False,
                "why": ("The ingest ledger could not be read, so no claim is made "
                        "about why the board looks the way it does.")}
    return ingest_state(store, scrape, drops, armed=ci.scrape_enabled(), today=today)


# ── payload ─────────────────────────────────────────────────────────────────
DISCLAIMER = {
    "screen": ("This is a screen, not investment advice and not a validated "
               "forecast. No price-history backtest exists yet."),
    "derived": ("Every price on this page is a derived statistic: a grade-mix "
                "adjusted trimmed median of public sold prices, published on a "
                "coarse grid. Individual sales, listings and sellers are not "
                "republished."),
    "collectible": ("Trading cards are collectibles. Values move on scarcity, "
                    "grading, condition and taste as much as on performance."),
}

# EVERY PROSE VALUE IN HERE IS PAGE COPY, not a label. cards.js renderMethod
# prints index / talent / gap / sources verbatim into their own <p> directly
# under an <h2>, so a value that reads as a fragment in the source renders as a
# fragment on the page. Four of them did: the Method tab opened with
# "grade-mix adjusted trimmed median of sold comps..." in lowercase under the
# heading, with no closing period, and three more like it. Full sentences,
# capitalized, terminated. `publish_grid` is the exception and stays a lowercase
# noun phrase because it renders INSIDE a parenthetical, mid-sentence.
METHOD = {
    "index": ("The Card Index is a grade-mix adjusted trimmed median of sold comps "
              f"in a rolling {INDEX_WINDOW_DAYS}-day window. The trim is by VALUE, not "
              f"by count: sales outside {TRIM_LOW_MULT:g}x to {TRIM_HIGH_MULT:g}x the "
              "window's raw median are dropped before the median is taken, because "
              "symmetric count-trimming cannot move a median at all, while lot listings "
              "and mis-parsed prices arrive in clusters."),
    "grade_factors": GRADE_FACTORS,
    "min_comps": MIN_COMPS,
    "window_days": INDEX_WINDOW_DAYS,
    "prior_window_days": PRIOR_WINDOW_DAYS,
    "trim_band": [TRIM_LOW_MULT, TRIM_HIGH_MULT],
    "publish_grid": "nearest $1 under $100, nearest $5 under $1,000, nearest $25 above",
    "talent": ("Talent is the shared dynasty_blend eFV composite, the same "
               "arithmetic that ranks the /fantasy/ Dynasty board: the board "
               f"grade, plus {dynasty_blend.W_STAR:.0f} x P(star), minus "
               f"{abs(dynasty_blend.W_BUST):.0f} x P(bust), plus "
               f"{dynasty_blend.W_ETA:.0f} x ETA proximity, plus "
               f"{dynasty_blend.W_SURPLUS:.0f} x normalized surplus."),
    "efv_basis": ("Every eFV on this page comes from efv_board_scale.board_value "
                  "through fantasy_export._board_grade, one basis site-wide."),
    "gap": ("The gap is the talent percentile minus the market percentile, both "
            "computed WITHIN TIER (prospect cards against prospect cards, MLB cards "
            "against MLB cards), because a forward eFV and a debuted player's cohort "
            "grade are not the same quantity."),
    "bands": {"buy": BUY_GAP, "fade": FADE_GAP,
              "note": ("These are CONVENTIONS chosen for legibility, not fitted "
                       "thresholds. There is no backtest to fit them on yet.")},
    "sources": ("Comps come from manual CSV drops and, when explicitly enabled, "
                "throttled reads of publicly visible sold listings. Raw comps are "
                "stored locally and never republished."),
}


def _eta_by_key(ts) -> dict:
    out = {}
    for pl in ((ts or {}).get("players") or []):
        k = pl.get("player_key")
        if not k:
            continue
        eta = pl.get("eta")
        y = eta.get("year") if isinstance(eta, dict) else (eta if isinstance(eta, int) else None)
        out[k] = y
    return out


def index_history(card_ids, con=None, limit: int = HISTORY_POINTS) -> dict:
    """{card_id: [{d, v}]} from card_index_history. These are OUR derived index
    values, so they are safe to publish; no comp ever appears here."""
    ids = list(card_ids or [])
    if not ids:
        return {}

    def _q(c):
        c.executescript(ci.SCHEMA)
        out: dict = {}
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            q = ("SELECT card_id, as_of, index_usd FROM card_index_history "
                 f"WHERE card_id IN ({','.join('?' * len(chunk))}) "
                 "AND index_usd IS NOT NULL ORDER BY as_of")
            for r in c.execute(q, chunk):
                out.setdefault(r["card_id"], []).append({"d": r["as_of"], "v": r["index_usd"]})
        return {k: v[-limit:] for k, v in out.items()}

    if con is not None:
        return _q(con)
    with ci._connect() as c:
        return _q(c)


def record_history(rows, as_of: date, con=None) -> int:
    """Append today's index for every PRICED card. INSERT OR REPLACE on
    (card_id, as_of) so a same-day re-export corrects itself instead of
    duplicating; yesterday's rows are never touched.

    Null-index rows are skipped as of 2026-08-16. Eleven days of daily exports
    on a zero-priced board had appended 440 all-NULL history rows: no index, no
    information, just one row per card per day recording that nothing was
    known. index_history already refuses them at read time (index_usd IS NOT
    NULL), so they fed no page; what they would have fed is the eventual
    forward-return eval, which would have had to re-discover and filter them.
    A card's history now starts on the day it first has a price."""
    rows = [r for r in (rows or []) if r.get("index_usd") is not None]
    if not rows:
        return 0

    def _w(c):
        c.executescript(ci.SCHEMA)
        c.executemany(
            "INSERT OR REPLACE INTO card_index_history (card_id, as_of, index_usd, n_comps, window_days) "
            "VALUES (?,?,?,?,?)",
            [(r["card_id"], as_of.isoformat(), r.get("index_usd"), r.get("index_n") or 0,
              INDEX_WINDOW_DAYS) for r in rows])
        return len(rows)

    if con is not None:
        return _w(con)
    with ci._connect() as c:
        return _w(c)


def build_payload(watchlist: dict, comps_by_card: dict, xfv: dict | None = None,
                  ts: dict | None = None, as_of: date | None = None,
                  history: dict | None = None, ingest: dict | None = None) -> dict:
    """The served payload. Pure function of its inputs so the tests can build it
    from fixtures with no DB and no artifacts.

    `ingest` is the ingest_state() block. It stays a parameter rather than a DB
    read so this function keeps no side channel: a caller with no ledger to
    report publishes null, which says "no claim made", not "healthy"."""
    as_of = as_of or date.today()
    season = as_of.year
    by_player = (xfv or {}).get("by_player") if isinstance(xfv, dict) else {}
    by_player = by_player if isinstance(by_player, dict) else {}
    eta = _eta_by_key(ts)

    rows = []
    for c in (watchlist.get("cards") or []):
        cid = c.get("card_id")
        if not cid:
            continue
        pk = c.get("player_key")
        target = c.get("grade_bucket") or "PSA 10"
        comps = comps_by_card.get(cid) or []
        cur = card_index(comps, target, as_of, INDEX_WINDOW_DAYS, 0)
        prior = card_index(comps, target, as_of, PRIOR_WINDOW_DAYS, INDEX_WINDOW_DAYS)
        xr = by_player.get(pk) if pk else None
        # ETA comes off the watchlist entry (stamped at build time) so this
        # export never parses timeseries.json; a caller may still pass one.
        score, efv = talent_score(xr, eta.get(pk) or c.get("eta"), season)
        trend = None
        if cur["index"] is not None and prior["index"]:
            trend = round(100.0 * (cur["index"] / prior["index"] - 1.0), 1)
        rows.append({
            "card_id": cid,
            "player_key": pk,
            "name": c.get("player_name"),
            "mlbam": c.get("mlbam"),
            "org": c.get("org"),
            "pos": c.get("position"),
            "tier": c.get("tier"),
            "set": c.get("set_desc"),
            "parallel": c.get("parallel"),
            "grade": target,
            "hot": bool(c.get("hot")),
            "efv": round(efv, 1) if efv is not None else None,
            # 'active' = a forward eFV; 'debuted' = the retrospective cohort
            # grade. The page labels the second so a reader is never shown a
            # backward-looking number as a forecast.
            "efv_kind": (xr or {}).get("kind"),
            "talent_score": score,
            "index_usd": cur["index"],
            "index_n": cur["n"],
            "index_reason": cur["reason"],
            "index_window": cur["window"],
            "prior_index_usd": prior["index"],
            "trend_pct": trend,
            "comp_count_total": len(comps),
            "history": (history or {}).get(cid) or [],
        })

    # PERCENTILES ARE COMPUTED WITHIN TIER, and that is not a detail. eFV is a
    # prospect model: an active prospect's grade is a forward talent estimate,
    # while a debuted player's row is the retrospective grade of a cohort member.
    # Ranking the two against each other would compare two different quantities
    # (the Quantity A vs Quantity B trap the FV framework keeps warning about),
    # so a prospect card is screened against prospect cards and an MLB card
    # against MLB cards. Prices split the same way for the same reason: a modern
    # prospect auto and a decade-old flagship rookie are not one market.
    tal, mkt = {}, {}
    tiers = sorted({(r.get("tier") or "other") for r in rows})
    for tier in tiers:
        sub = [r for r in rows if (r.get("tier") or "other") == tier]
        tal.update(percentile_ranks([(r["card_id"], r["talent_score"]) for r in sub]))
        mkt.update(percentile_ranks([(r["card_id"], r["index_usd"]) for r in sub]))
    for r in rows:
        t, m = tal.get(r["card_id"]), mkt.get(r["card_id"])
        r["talent_pct"] = t
        r["market_pct"] = m
        gap = round(t - m, 1) if (t is not None and m is not None) else None
        r["gap"] = gap
        r["signal"] = signal_for(gap)
    rows.sort(key=lambda r: (-(r["gap"] if r["gap"] is not None else -1e9), r["card_id"]))

    priced = sum(1 for r in rows if r["index_usd"] is not None)
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of.isoformat(),
        "version": 1,
        "screen": True,
        "screen_label": "Screen, not a validated signal",
        "method": METHOD,
        "disclaimer": DISCLAIMER,
        "meta": {
            "n_cards": len(rows),
            "n_priced": priced,
            "n_unpriced": len(rows) - priced,
            "min_comps": MIN_COMPS,
            "watchlist_generated_at": watchlist.get("generated_at"),
            "raw_comps_published": False,
            # WHY the board looks the way it does. n_priced = 0 has two very
            # different causes and this block is the only place the page can
            # tell them apart; see the ingest-state section above. Counts and
            # our own ingest dates only - no sale date, no price, nothing that
            # would make this a comp in disguise.
            "ingest": ingest,
        },
        "cards": rows,
    }


def eval_stub(payload: dict | None = None) -> dict:
    """The PRE-REGISTRATION artifact. Not an eval: there is nothing to evaluate
    yet. It states, before any data exists, what would have to be true for the
    screen to become a validated signal, so the bar cannot be moved later."""
    p = payload or {}
    meta = p.get("meta") or {}
    return {
        "model_id": "card_market_index",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "screen",
        "verdict": "unvalidated",
        "why": ("No price-history backtest exists. The module began accumulating "
                "its own index history at first export; until a forward window "
                "closes there is no out-of-sample test to run, and none is claimed."),
        "coverage": {"cards": meta.get("n_cards"), "priced": meta.get("n_priced"),
                     "as_of": p.get("as_of")},
        "pre_registration": {
            "target": ("forward 90-day percent change in the published Card Index "
                       "for each watchlist card"),
            "candidate": "the gap (talent percentile minus market percentile) at t0",
            "baselines": ["zero-information control (gap permuted across cards)",
                          "momentum carry (the card's own prior-window trend)",
                          "eFV level alone"],
            "metric": "Spearman rho of gap vs forward return, plus decile spread",
            "ship_bar": ("beat BOTH baselines out of sample on rho, with the "
                         "zero-information control excluded from the bootstrap CI, "
                         "on at least 3 of 4 forward windows"),
            "earliest_possible_run": ("two full non-overlapping forward windows after "
                                      "the first export with n_priced >= 30"),
            "if_it_fails": ("the ledger records the refusal and the page keeps the "
                            "screen label; the index itself is descriptive and "
                            "survives a failed signal gate"),
        },
        "notes": ("Thresholds BUY_GAP=+20 / FADE_GAP=-20 are display conventions, "
                  "not fitted values, and must be refit or dropped if this gate ever runs."),
    }


def export(out_path: Path | str | None = None, as_of: date | None = None,
           data_dir: Path | None = None, con=None, write_eval: bool = False) -> dict:
    """Build and write data/card_market.json. Best-effort: any missing input
    yields a payload with an honest empty state instead of an exception."""
    d = data_dir or DATA_DIR
    as_of = as_of or date.today()
    wl = ci.load_watchlist(d / "card_watchlist.json")
    ids = [c.get("card_id") for c in (wl.get("cards") or []) if c.get("card_id")]
    try:
        comps = ci.load_comps(ids, con=con)
    except Exception:
        log.exception("card market: comp store unreadable, exporting with zero comps")
        comps = {}
    try:
        hist = index_history(ids, con=con)
    except Exception:
        log.exception("card market: index history unreadable")
        hist = {}
    ingest = collect_ingest_facts(con=con, today=as_of)
    # No timeseries.json read: ETA is stamped onto the watchlist at build time,
    # which keeps this export off the 73MB parse and out of the OOM window.
    payload = build_payload(wl, comps, _load_json("xfv.json", d), None,
                            as_of=as_of, history=hist, ingest=ingest)
    try:
        record_history(payload["cards"], as_of, con=con)
        # index_history was read BEFORE today's row existed, so fold today in.
        # Without this the very first export ships an empty sparkline on a card
        # that does have an index, which reads as "no data" when the truth is
        # "one point".
        stamp = as_of.isoformat()
        for r in payload["cards"]:
            if r.get("index_usd") is None:
                continue
            h = r.setdefault("history", [])
            if not any(pt.get("d") == stamp for pt in h):
                h.append({"d": stamp, "v": r["index_usd"]})
    except Exception:
        log.exception("card market: could not record index history")
    p = Path(out_path) if out_path else (d / OUT_PATH.name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    if write_eval:
        (d / EVAL_PATH.name).write_text(json.dumps(eval_stub(payload), indent=1) + "\n",
                                        encoding="utf-8")
    log.info("card market: %d cards, %d priced -> %s (ingest: %s)",
             payload["meta"]["n_cards"], payload["meta"]["n_priced"], p,
             ingest.get("state"))
    # FILED AFTER THE WRITE, DELIBERATELY. The index itself is descriptive and
    # correct even when the tap is broken - what is wrong is the input, not the
    # arithmetic - so the artifact is published first and the alarm raised
    # second. Refusing to publish here would hide the very block that explains
    # the problem. Same posture as bullpen_export.guard_nonempty_block: keep
    # serving, make the failure visible.
    if ingest.get("red"):
        sc = ingest.get("last_scrape") or {}
        if ingest["state"] == "fetch_blocked":
            msg = (f"card scrape attempted {sc.get('cards_attempted')} cards on "
                   f"{sc.get('ran_on')} and every request failed "
                   f"({sc.get('fetch_errors')} errors, 0 pages fetched); the source "
                   f"is refusing the fetcher, so this is a SOURCE problem and no "
                   f"parser or watchlist change can clear it")
            _ingest_red("card_scrape", msg)
        elif ingest["state"] == "parse_regression":
            msg = (f"card scrape fetched {sc.get('cards_fetched')} pages on "
                   f"{sc.get('ran_on')} and parsed 0 sales from all of them; the "
                   f"parser yields nothing on layout drift, so treat this as a "
                   f"marketplace redesign rather than a quiet market")
            _ingest_red("card_scrape", msg)
        else:
            dr = ingest.get("drops") or {}
            msg = (f"the newest CSV drop (ingested {dr.get('last_ingested_on')}) "
                   f"parsed 0 usable rows out of {dr.get('files')} file(s) on "
                   f"file; check the column contract in docs/diamond-cards.md")
            _ingest_red("card_drops", msg)
        log.error("card market: INGEST %s - %s", ingest["state"].upper(), msg)
    return payload


def main(argv=None) -> int:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Card Market export (derived index only)")
    ap.add_argument("--out", help="output path (default data/card_market.json)")
    ap.add_argument("--eval", action="store_true",
                    help="also write data/card_market_eval.json (the pre-registration)")
    a = ap.parse_args(argv)
    p = export(a.out, write_eval=a.eval)
    _ing = p["meta"].get("ingest") or {}
    print(json.dumps({"cards": p["meta"]["n_cards"], "priced": p["meta"]["n_priced"],
                      "screen": p["screen"], "ingest": _ing.get("state"),
                      "ingest_why": _ing.get("why")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
