# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_ingest.py - the odds feed for the /betting/ module.

ONE source, ONE call a day, on The Odds API free tier (500 credits/month).

CREDIT ARITHMETIC (this is why the shape of the call is fixed):
    a credit = markets x regions, per request.
    markets = h2h, spreads, totals  -> 3
    regions = us                    -> 1
    so one snapshot costs 3 credits.

    open snapshot  1/day x 3 =  ~93 credits/month
    close snapshot 1/day x 3 =  ~93 credits/month
    total                       ~186 of 500, with headroom for retries and
                                for the odd manual pull.

Player props are NOT pulled on the daily snapshot. They live behind the
per-event endpoint (/v4/sports/{sport}/events/{eventId}/odds), which costs
credits PER EVENT: a 15-game slate with two prop markets is 30 credits a day,
which burns the free tier in about two weeks. The module ships MODEL FAIR
LINES for props instead, with no book comparison, until a paid tier is
approved (see docs/diamond-betting.md).

PROPS MODE (2026-08-16, docs/diamond-betting.md section 7c, pre-registered).
`run("props", event_ids=[...])` pulls the four owner-approved prop markets for
a HAND-PICKED few events, and it is DOUBLE-ARMED: it fires only when BOTH
EEPHUS_ODDS_API_KEY and EEPHUS_PROPS_CREDITS (the owner's monthly props
credit cap) are set. Either one absent leaves the machinery inert with the
reason in the status sidecar. Spend is metered in
.cache/odds/props_spend.json per calendar month and the guard runs BEFORE
every request: a pull that would breach the cap is refused, not reconciled.

WHAT THIS MODULE DOES
    * With EEPHUS_ODDS_API_KEY set: one snapshot of the MLB board, written
      IMMUTABLY to .cache/odds/<date>-<hhmm>.json. An existing file is never
      rewritten - a snapshot is a point-in-time record and a rewrite would
      silently destroy the odds-at-post evidence the public record depends on.
    * Without a key: a loud no-op that still writes data/betting_status.json,
      so the page can say "odds feed not configured" instead of rendering an
      empty board with no explanation.
    * Parsing (raw API shape -> the normalized event records the model reads)
      is a PURE function of bytes, so every test runs on the committed fixture
      at test_fixtures/odds_api_mlb_sample.json and NEVER touches the network.

CLOSING LINES / CLV
    Grading a pick against the closing line needs a second snapshot taken near
    first pitch. `closing_window()` returns the UTC minute of the earliest
    first pitch on a slate; the box should schedule the close snapshot a few
    minutes before it. That scheduling is DOCUMENTED, not cronned here: this
    module never installs a timer, it only tells the caller when to run.

CLI:
    python betting_ingest.py --status        # what is configured, what is cached
    python betting_ingest.py --snapshot open # costs 3 credits, needs the key
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("betting_ingest")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "odds"
STATUS_PATH = DATA_DIR / "betting_status.json"
FIXTURE_PATH = ROOT / "test_fixtures" / "odds_api_mlb_sample.json"

API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "baseball_mlb"
MARKETS = ("h2h", "spreads", "totals")
REGIONS = ("us",)
ODDS_FORMAT = "american"          # decimal is derived; american is what books post
ENV_KEY = "EEPHUS_ODDS_API_KEY"

# Snapshot kinds. "open" is the daily morning board; "close" is the near-first-
# pitch capture that CLV grading needs. The kind lives INSIDE the file (the
# filename is date-time only) so a cache directory can be read back without
# parsing filenames for semantics.
KINDS = ("open", "close")

_SNAP_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{4})\.json$")

# ---------------------------------------------------------------------------
# props mode (2026-08-16, docs/diamond-betting.md section 7c)
# ---------------------------------------------------------------------------
#: The four owner-approved prop markets. Key names verified against The Odds
#: API market list (the-odds-api.com/sports-odds-data/betting-markets.html) on
#: 2026-08-16; they are the documented MLB player-prop keys, not guesses.
PROPS_MARKETS = ("pitcher_strikeouts", "batter_total_bases",
                 "batter_hits", "batter_home_runs")

#: The SECOND arming variable. The team key alone is the 500-credit team
#: budget; props bill per event against a SEPARATE owner-approved monthly
#: number, and the machinery never assumes one.
ENV_PROPS_CREDITS = "EEPHUS_PROPS_CREDITS"

#: The props snapshot kind. Deliberately NOT in KINDS: write_snapshot's
#: date-time filename and latest_snapshot's resolution are the team feed's,
#: and a props capture must never be resolvable as a board snapshot.
PROPS_KIND = "props"

#: The calendar-month spend ledger the hard guard reads and writes.
PROPS_SPEND_PATH = CACHE_DIR / "props_spend.json"

_PROPS_SNAP_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-props-(.+)\.json$")


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
def api_key() -> str | None:
    """The Odds API key from the environment, or None. Never logged, never
    written to any artifact (the status sidecar records only whether one
    exists)."""
    k = (os.environ.get(ENV_KEY) or "").strip()
    return k or None


def configured() -> bool:
    return api_key() is not None


def credits_for(markets=MARKETS, regions=REGIONS) -> int:
    """The Odds API bills markets x regions per request. This is the whole
    reason the daily call is 3 credits and not 1.

    AN EMPTY MARKET OR REGION TUPLE COSTS NOTHING, because there is no request
    to make. The `max(1, ...)` floors exist so a one-market call is not free,
    and they used to apply to the empty case as well: credits_for((), ("us",))
    returned 1. That is not a rounding quirk, it is a live trap for any capture
    job that ships INERT with an empty market tuple and is armed later.
    `betting_credits.check` short-circuits only at `cost <= 0`, so such a job
    would clear its own guard, issue a request asking for nothing, and book a
    real credit every time it ran.

    Zero markets means no call. The floors still apply to every non-empty case,
    so the daily 3 and the props arithmetic are unchanged.
    """
    m, r = tuple(markets), tuple(regions)
    if not m or not r:
        return 0
    return max(1, len(m)) * max(1, len(r))


def props_credits_cap() -> int | None:
    """The owner's monthly props credit cap, or None while it is unset.

    None is a STATE, not a default: docs/diamond-betting.md 7c pre-registers
    that the machinery never assumes a budget, so an unparseable value is
    treated as unset (and logged) rather than rounded to anything."""
    raw = (os.environ.get(ENV_PROPS_CREDITS) or "").strip()
    if not raw:
        return None
    try:
        cap = int(raw)
    except ValueError:
        log.warning("betting_ingest: %s=%r is not an integer; props stay inert",
                    ENV_PROPS_CREDITS, raw)
        return None
    return cap if cap > 0 else None


def props_armed() -> bool:
    """BOTH variables or nothing. See section 7c: the key alone is the team
    budget, and a cap with no key has nothing to spend."""
    return configured() and props_credits_cap() is not None


def props_disarmed_reason() -> str | None:
    """The exact sentence the payload carries while props are inert, naming
    every missing variable so the page never renders an unexplained blank."""
    missing = []
    if not configured():
        missing.append(ENV_KEY)
    if props_credits_cap() is None:
        missing.append(ENV_PROPS_CREDITS)
    if not missing:
        return None
    return ("props machinery is inert: " + " and ".join(missing) +
            (" are" if len(missing) > 1 else " is") + " not set. Both "
            f"{ENV_KEY} and {ENV_PROPS_CREDITS} must be set before a "
            "per-event props pull can spend a credit.")


def props_credits_for(markets=PROPS_MARKETS, regions=REGIONS) -> int:
    """Markets x regions PER EVENT: 4 x 1 = 4 credits for every event pulled,
    which is the whole reason the monthly cap and the hard guard exist."""
    return credits_for(markets, regions)


# ---------------------------------------------------------------------------
# immutable snapshot cache
# ---------------------------------------------------------------------------
def snapshot_path(when: datetime | None = None) -> Path:
    when = when or datetime.now(timezone.utc)
    return CACHE_DIR / f"{when.strftime('%Y-%m-%d')}-{when.strftime('%H%M')}.json"


def _day_delta(a: str, b: str) -> int:
    """Whole days between two ISO dates, or a large number when either is
    unparseable so the caller simply skips that file."""
    try:
        return (date.fromisoformat(a) - date.fromisoformat(b)).days
    except ValueError:
        return 10 ** 6


def list_snapshots() -> list[dict]:
    """[{path, date, hhmm}] for every cached snapshot, oldest first. Reads
    filenames only, so it is cheap enough to call on every export."""
    if not CACHE_DIR.exists():
        return []
    out = []
    for p in sorted(CACHE_DIR.glob("*.json")):
        m = _SNAP_NAME.match(p.name)
        if m:
            out.append({"path": p, "date": m.group(1), "hhmm": m.group(2)})
    return out


def load_snapshot(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("betting_ingest: unreadable snapshot %s", path)
        return None


def latest_snapshot(kind: str | None = None, on_date: str | None = None) -> dict | None:
    """The newest cached snapshot wrapper, optionally filtered by kind/date.
    Returns None when nothing is cached (the normal state before a key exists)."""
    for meta in reversed(list_snapshots()):
        # Cheap pre-filter on the filename, widened by a day on each side
        # because a slate's capture can land under the neighbouring UTC date.
        # The authoritative comparison is the wrapper's own slate_date below.
        if on_date and abs(_day_delta(meta["date"], on_date)) > 1:
            continue
        wrap = load_snapshot(meta["path"])
        if not wrap:
            continue
        if kind and wrap.get("kind") != kind:
            continue
        if on_date:
            # Snapshots written before slate_date existed fall back to the
            # filename date, so an old cache still resolves exactly as it did.
            if (wrap.get("slate_date") or meta["date"]) != on_date:
                continue
        wrap.setdefault("_path", str(meta["path"]))
        return wrap
    return None


def closing_snapshot(on_date: str) -> dict | None:
    """The close-kind snapshot for a slate date, or None. CLV grading is
    absent - not guessed - until this exists."""
    return latest_snapshot(kind="close", on_date=on_date)


def slate_date_of(events, when: datetime | None = None) -> str:
    """The US slate date this capture belongs to.

    THE UTC-MIDNIGHT BUG THIS CLOSES (2026-08-06). Snapshot FILENAMES are stamped
    with the UTC capture date, but a slate is identified by its US-local
    officialDate. A West Coast game with a 10:10pm ET first pitch closes around
    01:55 UTC the NEXT day, so its close snapshot lands under tomorrow's filename
    while the slate it belongs to is today.

    Two things then break, both silently. `closing_snapshot(slate)` filters on
    the filename date and never finds it, so CLV for that slate is unrecoverable
    and the grader reports "the close job did not fire" when it did. And the
    once-per-slate guard in tools/betting_close_job.py asks the same question, so
    it can fire a SECOND paid snapshot for a slate already captured, against a
    500 credit monthly budget at 3 credits a call.

    Derived from the EARLIEST commence_time in the capture, converted to US
    Eastern, because that is what MLB's officialDate follows. Falls back to the
    UTC capture date when there are no events to read, which is the old
    behaviour and is correct for an empty board."""
    stamps = []
    for ev in (events or []):
        if not isinstance(ev, dict):
            continue
        ct = ev.get("commence_time")
        if not ct:
            continue
        try:
            stamps.append(datetime.fromisoformat(str(ct).replace("Z", "+00:00")))
        except ValueError:
            continue
    when = when or datetime.now(timezone.utc)
    if not stamps:
        return when.strftime("%Y-%m-%d")
    # US Eastern without a tz database dependency: MLB's official date rolls at
    # local midnight, and every in-season slate sits in EDT (UTC-4). Using a
    # fixed offset is deliberate, since the alternative is a zoneinfo lookup
    # that is not guaranteed present on the box.
    return (min(stamps) - timedelta(hours=4)).strftime("%Y-%m-%d")


def write_snapshot(payload: list | dict, *, kind: str, when: datetime | None = None,
                   credits: dict | None = None) -> Path:
    """Write ONE snapshot, immutably. An existing file at the target path is a
    hard stop, not an overwrite: the odds-at-post record is evidence and a
    rewrite destroys it silently."""
    if kind not in KINDS:
        raise ValueError(f"unknown snapshot kind {kind!r}")
    when = when or datetime.now(timezone.utc)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(when)
    if path.exists():
        raise FileExistsError(
            f"snapshot {path.name} already exists; snapshots are immutable. "
            "Wait a minute or pass an explicit `when`.")
    wrapper = {
        "captured_at": when.replace(microsecond=0).isoformat(),
        # The SLATE this capture belongs to, which is not always the UTC date in
        # the filename. Every date-filtered read keys off this.
        "slate_date": slate_date_of(payload if isinstance(payload, list) else
                                    (payload or {}).get("events"), when),
        "kind": kind,
        "sport": SPORT_KEY,
        "markets": list(MARKETS),
        "regions": list(REGIONS),
        "odds_format": ODDS_FORMAT,
        "credits": credits or {},
        "events": payload,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(wrapper), encoding="utf-8")
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# props snapshots + the monthly spend ledger (2026-08-16, section 7c)
# ---------------------------------------------------------------------------
def props_snapshot_path(event_id: str, when: datetime | None = None) -> Path:
    when = when or datetime.now(timezone.utc)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(event_id))
    return CACHE_DIR / f"{when.strftime('%Y-%m-%d')}-props-{safe}.json"


def list_props_snapshots(on_date: str | None = None) -> list[dict]:
    """[{path, date, event_id}] for every cached props capture, oldest first.
    A separate walk from list_snapshots on purpose: the team name pattern does
    not match these files and must never start to."""
    if not CACHE_DIR.exists():
        return []
    out = []
    for p in sorted(CACHE_DIR.glob("*-props-*.json")):
        m = _PROPS_SNAP_NAME.match(p.name)
        if not m:
            continue
        if on_date and m.group(1) != on_date:
            continue
        out.append({"path": p, "date": m.group(1), "event_id": m.group(2)})
    return out


def write_props_snapshot(payload: dict, *, event_id: str,
                         when: datetime | None = None,
                         credits: dict | None = None) -> Path:
    """One per-event props capture, immutable like every other snapshot: an
    existing file is a hard stop because it is odds-at-post evidence, and for
    props it is also SPENT MONEY that a rewrite would double-charge."""
    when = when or datetime.now(timezone.utc)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = props_snapshot_path(event_id, when)
    if path.exists():
        raise FileExistsError(
            f"props snapshot {path.name} already exists; snapshots are "
            "immutable and this event's credits are already spent today")
    wrapper = {
        "captured_at": when.replace(microsecond=0).isoformat(),
        "kind": PROPS_KIND,
        "sport": SPORT_KEY,
        "event_id": str(event_id),
        "markets": list(PROPS_MARKETS),
        "regions": list(REGIONS),
        "odds_format": ODDS_FORMAT,
        "credits": credits or {},
        "event": payload,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(wrapper), encoding="utf-8")
    tmp.replace(path)
    return path


def _props_month(when: datetime | None = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m")


def load_props_spend(path: Path | None = None,
                     when: datetime | None = None) -> dict:
    """The CURRENT month's spend row. A new month starts at zero; the old
    months stay in `history` so the arithmetic can be audited later."""
    p = Path(path or PROPS_SPEND_PATH)
    month = _props_month(when)
    obj = None
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("betting_ingest: unreadable %s; the props spend ledger "
                        "restarts at zero for %s, which is the LOOSE direction, "
                        "so the monthly cap should be re-checked by hand",
                        p.name, month)
    if not isinstance(obj, dict):
        obj = {"month": month, "spent": 0, "pulls": [], "history": []}
    if obj.get("month") != month:
        hist = obj.get("history") or []
        if obj.get("month"):
            hist.append({"month": obj.get("month"), "spent": obj.get("spent", 0)})
        obj = {"month": month, "spent": 0, "pulls": [], "history": hist}
    obj.setdefault("spent", 0)
    obj.setdefault("pulls", [])
    obj.setdefault("history", [])
    return obj


def save_props_spend(ledger: dict, path: Path | None = None) -> None:
    p = Path(path or PROPS_SPEND_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=1), encoding="utf-8")
    tmp.replace(p)


def _book_shared_credits(cost: int, note: str) -> None:
    """Charge the SHARED tier ledger beside the props-only one. Never raises.

    Two ledgers is not duplication. props_spend.json answers "how much of the
    owner's props allowance is left"; betting_credits answers "how much of the
    500-credit month is left across every job". A props pull consumes both, and
    either can be the binding one."""
    try:
        import betting_credits as _bc
        _bc.record("props", int(cost), note=str(note))
    except Exception:                                     # noqa: BLE001
        log.warning("betting_ingest: could not book %s props credits to the "
                    "shared tier ledger", cost, exc_info=True)


def props_budget_check(next_cost: int, *, cap: int | None = None,
                       ledger: dict | None = None, path: Path | None = None,
                       when: datetime | None = None) -> tuple[bool, str]:
    """(ok, reason) BEFORE a request. The refusal carries the arithmetic,
    because a guard that only says no cannot be argued with or audited."""
    cap = cap if cap is not None else props_credits_cap()
    if cap is None:
        return False, (f"{ENV_PROPS_CREDITS} is not set; no props budget "
                       "exists to spend against")
    led = ledger if ledger is not None else load_props_spend(path, when)
    spent = int(led.get("spent") or 0)
    if spent + int(next_cost) > cap:
        return False, (f"refused BEFORE the request: {spent} of {cap} monthly "
                       f"props credits are spent and this pull costs "
                       f"{int(next_cost)}, which would breach the cap")
    return True, (f"{spent} of {cap} spent this month; this pull costs "
                  f"{int(next_cost)}")


def record_props_spend(cost: int, *, event_id: str, path: Path | None = None,
                       when: datetime | None = None) -> dict:
    led = load_props_spend(path, when)
    led["spent"] = int(led.get("spent") or 0) + int(cost)
    led["pulls"].append({
        "at": (when or datetime.now(timezone.utc)).replace(microsecond=0).isoformat(),
        "event_id": str(event_id), "cost": int(cost)})
    save_props_spend(led, path)
    return led


# ---------------------------------------------------------------------------
# the one network call
# ---------------------------------------------------------------------------
def fetch_snapshot(*, session=None, timeout: int = 30) -> tuple[list, dict]:
    """(events, credits) straight from The Odds API. Raises when no key is set.

    NOTHING in the test suite calls this. Tests read the committed fixture, so
    a green suite has never spent a credit."""
    key = api_key()
    if not key:
        raise RuntimeError(f"{ENV_KEY} is not set; refusing to call the odds API")
    if session is None:
        import feed_cache
        session = feed_cache.SESSION
    url = f"{API_BASE}/sports/{SPORT_KEY}/odds"
    resp = session.get(url, params={
        "apiKey": key,
        "regions": ",".join(REGIONS),
        "markets": ",".join(MARKETS),
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": "iso",
    }, timeout=timeout)
    resp.raise_for_status()
    headers = getattr(resp, "headers", {}) or {}
    credits = {
        "cost": credits_for(),
        "used": _as_int(headers.get("x-requests-used")),
        "remaining": _as_int(headers.get("x-requests-remaining")),
        "last": _as_int(headers.get("x-requests-last")),
    }
    return resp.json(), credits


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_props_event(event_id: str, *, session=None, timeout: int = 30
                      ) -> tuple[dict, dict]:
    """(event, credits) from the per-event odds endpoint, PROPS_MARKETS only.

    Raises without a key exactly as fetch_snapshot does. The BUDGET guard is
    NOT here: it belongs to run("props", ...), before this is ever called,
    because a fetch function that silently consults a ledger is a fetch
    function whose cost depends on hidden state."""
    key = api_key()
    if not key:
        raise RuntimeError(f"{ENV_KEY} is not set; refusing to call the odds API")
    if session is None:
        import feed_cache
        session = feed_cache.SESSION
    url = f"{API_BASE}/sports/{SPORT_KEY}/events/{event_id}/odds"
    resp = session.get(url, params={
        "apiKey": key,
        "regions": ",".join(REGIONS),
        "markets": ",".join(PROPS_MARKETS),
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": "iso",
    }, timeout=timeout)
    resp.raise_for_status()
    headers = getattr(resp, "headers", {}) or {}
    credits = {
        "cost": props_credits_for(),
        "used": _as_int(headers.get("x-requests-used")),
        "remaining": _as_int(headers.get("x-requests-remaining")),
        "last": _as_int(headers.get("x-requests-last")),
    }
    return resp.json(), credits


# ---------------------------------------------------------------------------
# normalization (pure; every test runs through here)
# ---------------------------------------------------------------------------
def _org(name: str | None) -> str | None:
    """Team name -> the site's canonical 3-letter org code, the same one
    fantasy_schedule and data/fa_meta.json park factors use. Lazy import:
    trades.py is heavy and the parser runs in tests."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:                                            # pragma: no cover
        return None


def american_to_decimal(price) -> float | None:
    """American price -> decimal (total return per 1 staked). -110 -> 1.909."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return 1.0 + (p / 100.0 if p > 0 else 100.0 / abs(p))


def decimal_to_american(dec) -> int | None:
    try:
        d = float(dec)
    except (TypeError, ValueError):
        return None
    if d <= 1.0:
        return None
    return int(round((d - 1.0) * 100)) if d >= 2.0 else int(round(-100.0 / (d - 1.0)))


def implied_prob(price_american) -> float | None:
    """RAW implied probability, vig included. This is NOT a fair probability;
    de-vigging lives in betting_model.devig and the two must never be confused."""
    d = american_to_decimal(price_american)
    return None if not d else 1.0 / d


def parse_events(raw) -> list[dict]:
    """The Odds API /odds response -> normalized event records.

    Accepts either the bare API list or a snapshot wrapper written by
    write_snapshot. One record per game:

        {event_id, commence_time, home_team, away_team, home_org, away_org,
         books: {book_key: {title, last_update,
                            h2h:    {home: price, away: price},
                            spreads:{home: {price, point}, away: {...}},
                            totals: {over: {price, point}, under: {...}}}}}

    Prices stay AMERICAN (what the book posted). Decimal conversion is the
    caller's, so the stored number always matches the screenshot."""
    if isinstance(raw, dict):
        raw = raw.get("events") or []
    out: list[dict] = []
    for ev in raw or []:
        if not isinstance(ev, dict):
            continue
        home, away = ev.get("home_team"), ev.get("away_team")
        rec = {
            "event_id": ev.get("id"),
            "commence_time": ev.get("commence_time"),
            "home_team": home,
            "away_team": away,
            "home_org": _org(home),
            "away_org": _org(away),
            "books": {},
        }
        for bk in ev.get("bookmakers") or []:
            if not isinstance(bk, dict) or not bk.get("key"):
                continue
            entry = {"title": bk.get("title"), "last_update": bk.get("last_update")}
            for mk in bk.get("markets") or []:
                key = (mk or {}).get("key")
                outcomes = (mk or {}).get("outcomes") or []
                if key == "h2h":
                    got = {}
                    for o in outcomes:
                        if o.get("name") == home:
                            got["home"] = o.get("price")
                        elif o.get("name") == away:
                            got["away"] = o.get("price")
                    if len(got) == 2:
                        entry["h2h"] = got
                elif key == "spreads":
                    got = {}
                    for o in outcomes:
                        side = "home" if o.get("name") == home else ("away" if o.get("name") == away else None)
                        if side:
                            got[side] = {"price": o.get("price"), "point": o.get("point")}
                    if len(got) == 2:
                        entry["spreads"] = got
                elif key == "totals":
                    got = {}
                    for o in outcomes:
                        nm = (o.get("name") or "").lower()
                        if nm in ("over", "under"):
                            got[nm] = {"price": o.get("price"), "point": o.get("point")}
                    if len(got) == 2:
                        entry["totals"] = got
            if len(entry) > 2:            # something beyond title/last_update
                rec["books"][bk["key"]] = entry
        if rec["home_org"] and rec["away_org"]:
            out.append(rec)
        else:
            log.warning("betting_ingest: unmapped teams %r vs %r", away, home)
    return out


def parse_props_snapshot(raw) -> dict | None:
    """A per-event props response (or its snapshot wrapper) -> one normalized
    record. PURE function of bytes, like parse_events, so every test runs on a
    fixture and never touches the network.

        {event_id, commence_time, home_team, away_team, home_org, away_org,
         books: {book_key: {title, last_update,
                            markets: {market_key: {player_name:
                                {over: {price, point}, under: {price, point}}}}}}}

    The Odds API shapes a props market as Over/Under outcomes whose
    `description` is the player's name; grouping by that name is what turns a
    flat outcome list into one two-sided quote per player. A player with only
    one side at a book is kept as-is; the market-view stage decides what an
    incomplete quote is worth, exactly as it does for the team markets."""
    if isinstance(raw, dict) and "event" in raw:
        raw = raw.get("event")
    if not isinstance(raw, dict):
        return None
    rec = {
        "event_id": raw.get("id"),
        "commence_time": raw.get("commence_time"),
        "home_team": raw.get("home_team"),
        "away_team": raw.get("away_team"),
        "home_org": _org(raw.get("home_team")),
        "away_org": _org(raw.get("away_team")),
        "books": {},
    }
    for bk in raw.get("bookmakers") or []:
        if not isinstance(bk, dict) or not bk.get("key"):
            continue
        entry = {"title": bk.get("title"), "last_update": bk.get("last_update"),
                 "markets": {}}
        for mk in bk.get("markets") or []:
            mkey = (mk or {}).get("key")
            if mkey not in PROPS_MARKETS:
                continue
            players: dict = {}
            for o in (mk or {}).get("outcomes") or []:
                side = (o.get("name") or "").lower()
                player = o.get("description")
                if side not in ("over", "under") or not player:
                    continue
                players.setdefault(player, {})[side] = {
                    "price": o.get("price"), "point": o.get("point")}
            if players:
                entry["markets"][mkey] = players
        if entry["markets"]:
            rec["books"][bk["key"]] = entry
    return rec


def best_price(event: dict, market: str, side: str) -> dict | None:
    """The best available American price for one side of one market across the
    books in the snapshot, with the book that posted it.

    "Best" is the LONGEST price (highest decimal return), which is the only
    definition a bettor cares about. Ties keep the first book seen, so the
    output is stable for a fixed snapshot."""
    best = None
    for bkey, b in (event.get("books") or {}).items():
        m = b.get(market)
        if not isinstance(m, dict):
            continue
        cell = m.get(side)
        price = cell.get("price") if isinstance(cell, dict) else cell
        dec = american_to_decimal(price)
        if dec is None:
            continue
        if best is None or dec > best["decimal"]:
            best = {"book": bkey, "book_title": b.get("title"), "price": price,
                    "decimal": round(dec, 4),
                    "point": (cell.get("point") if isinstance(cell, dict) else None),
                    "last_update": b.get("last_update")}
    return best


def closing_window(games: list[dict]) -> str | None:
    """UTC ISO minute of the EARLIEST first pitch on a slate, from the schedule
    records fantasy_schedule emits. The box schedules the close snapshot a few
    minutes before this; nothing here installs a timer."""
    stamps = sorted(g.get("datetime") for g in (games or []) if g.get("datetime"))
    return stamps[0] if stamps else None


# ---------------------------------------------------------------------------
# status sidecar
# ---------------------------------------------------------------------------
def write_status(extra: dict | None = None) -> dict:
    """data/betting_status.json - what the page needs to explain itself.

    Written on EVERY run, key or no key. The unconfigured case is the whole
    point: an empty board with no explanation reads as a broken page, and
    "odds feed not configured" reads as a build state."""
    snaps = list_snapshots()
    latest = latest_snapshot()
    status = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "configured": configured(),
        "provider": "The Odds API (free tier)",
        "sport": SPORT_KEY,
        "markets": list(MARKETS),
        "regions": list(REGIONS),
        "credits_per_snapshot": credits_for(),
        "monthly_budget": 500,
        "planned_monthly_credits": credits_for() * 2 * 31,
        "n_snapshots_cached": len(snaps),
        "latest_snapshot": (latest or {}).get("captured_at"),
        "latest_kind": (latest or {}).get("kind"),
        "latest_credits": (latest or {}).get("credits") or {},
        "props": ("model fair lines plus the per-event value machinery (section 7c); "
                  "armed" if props_armed() else
                  props_disarmed_reason() or "props state unknown"),
        "props_armed": props_armed(),
        "props_credits_cap": props_credits_cap(),
        "props_credits_per_event": props_credits_for(),
        "props_spent_this_month": (load_props_spend().get("spent")
                                   if PROPS_SPEND_PATH.exists() else 0),
        "note": ("odds feed not configured: set EEPHUS_ODDS_API_KEY on the build box"
                 if not configured() else "odds feed configured"),
    }
    status.update(extra or {})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=1), encoding="utf-8")
    return status


def run(kind: str = "open", *, session=None, when: datetime | None = None,
        event_ids: list | None = None, spend_path: Path | None = None) -> dict:
    """One ingest pass. Returns the status dict it wrote.

    Best-effort by construction: an unset key, a dead API, or a duplicate
    snapshot path all degrade to a status sidecar and a log line. This never
    raises into the pipeline.

    kind="props" is the per-event mode (2026-08-16, section 7c): one request
    per event in `event_ids`, PROPS_MARKETS only, DOUBLE-ARMED on
    EEPHUS_ODDS_API_KEY and EEPHUS_PROPS_CREDITS, and the monthly budget
    guard runs BEFORE every single request. `spend_path` is injectable so the
    guard is testable without touching the real ledger."""
    if kind == PROPS_KIND:
        return _run_props(event_ids or [], session=session, when=when,
                          spend_path=spend_path)
    if not configured():
        log.warning("betting_ingest: %s not set - no odds pulled (page will say so)", ENV_KEY)
        return write_status({"last_run": "no-op (no api key)"})
    try:
        events, credits = fetch_snapshot(session=session)
    except Exception as exc:
        log.exception("betting_ingest: odds fetch failed")
        return write_status({"last_run": f"fetch failed: {exc}"})
    try:
        path = write_snapshot(events, kind=kind, when=when, credits=credits)
    except FileExistsError as exc:
        log.warning("betting_ingest: %s", exc)
        return write_status({"last_run": f"skipped: {exc}"})
    log.info("betting_ingest: wrote %s (%d events, %d credits)",
             path.name, len(events or []), credits.get("cost") or 0)
    return write_status({"last_run": f"ok: {path.name}"})


def _run_props(event_ids: list, *, session=None, when: datetime | None = None,
               spend_path: Path | None = None) -> dict:
    """The props pass. Every refusal is a status line, never an exception into
    the pipeline, and the budget guard runs before EACH request so a list of
    events cannot ride one approval past the cap."""
    if not props_armed():
        why = props_disarmed_reason()
        log.warning("betting_ingest: %s", why)
        return write_status({"last_run": f"props no-op: {why}"})
    if not event_ids:
        return write_status({"last_run": "props no-op: no event_ids given"})
    cap = props_credits_cap()
    cost = props_credits_for()
    pulled, refused, results = 0, 0, []
    for eid in event_ids:
        ok, reason = props_budget_check(cost, cap=cap, path=spend_path, when=when)
        if ok:
            # TWO BUDGETS, BOTH BINDING. The check above is the props cap the
            # owner sets (EEPHUS_PROPS_CREDITS); this one is the shared monthly
            # tier the props pull competes for with the open capture, the close
            # capture and futures. Props can be inside its own cap and still
            # unaffordable, which is the case the shared ledger exists to catch.
            try:
                import betting_credits as _bc
                ok, _tier_reason = _bc.check("props", cost)
                if not ok:
                    reason = _tier_reason
            except Exception:                             # noqa: BLE001
                log.warning("betting_ingest: shared credit ledger unusable; "
                            "the props cap still applies", exc_info=True)
        if not ok:
            refused += 1
            results.append({"event_id": str(eid), "ok": False, "reason": reason})
            log.warning("betting_ingest: props pull for %s %s", eid, reason)
            continue
        try:
            event, credits = fetch_props_event(eid, session=session)
        except Exception as exc:                              # noqa: BLE001
            # The request FAILED but it was SENT, so the credits are spent on
            # the provider's meter whatever came back; the ledger charges it
            # so the guard can never under-count against the cap.
            record_props_spend(cost, event_id=eid, path=spend_path, when=when)
            _book_shared_credits(cost, f"props {eid} fetch failed")
            results.append({"event_id": str(eid), "ok": False,
                            "reason": f"fetch failed: {exc}"})
            log.exception("betting_ingest: props fetch failed for %s", eid)
            continue
        record_props_spend(credits.get("cost") or cost, event_id=eid,
                           path=spend_path, when=when)
        _book_shared_credits(credits.get("cost") or cost, f"props {eid}")
        try:
            path = write_props_snapshot(event, event_id=eid, when=when,
                                        credits=credits)
            results.append({"event_id": str(eid), "ok": True, "path": path.name})
            pulled += 1
        except FileExistsError as exc:
            results.append({"event_id": str(eid), "ok": False,
                            "reason": str(exc)})
            log.warning("betting_ingest: %s", exc)
    led = load_props_spend(spend_path, when)
    return write_status({
        "last_run": (f"props: pulled {pulled} of {len(event_ids)} event(s), "
                     f"{refused} refused by the budget guard"),
        "props_pulls": results,
        "props_spent_this_month": led.get("spent"),
    })


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB odds snapshot (The Odds API free tier).")
    ap.add_argument("--snapshot", choices=KINDS, help="pull one snapshot (costs credits)")
    ap.add_argument("--props-events", default=None, dest="props_events",
                    help="comma-separated event ids for a per-event props pull "
                         "(needs BOTH arming variables; see section 7c)")
    ap.add_argument("--status", action="store_true", help="write/print the status sidecar only")
    args = ap.parse_args()

    if args.props_events:
        ids = [e.strip() for e in args.props_events.split(",") if e.strip()]
        print(json.dumps(run(PROPS_KIND, event_ids=ids), indent=1))
    elif args.snapshot:
        print(json.dumps(run(args.snapshot), indent=1))
    else:
        st = write_status()
        print(json.dumps(st, indent=1))
        if not st["configured"]:
            print(f"\n  set {ENV_KEY} to enable the feed. "
                  f"One snapshot costs {credits_for()} of 500 monthly credits.")
