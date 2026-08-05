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

Player props are NOT pulled. They live behind the per-event endpoint
(/v4/sports/{sport}/events/{eventId}/odds), which costs credits PER EVENT: a
15-game slate with two prop markets is 30 credits a day, which burns the free
tier in about two weeks. The module ships MODEL FAIR LINES for props instead,
with no book comparison, until a paid tier is approved (see docs/diamond-betting.md).

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
from datetime import datetime, timezone
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
    reason the daily call is 3 credits and not 1."""
    return max(1, len(tuple(markets))) * max(1, len(tuple(regions)))


# ---------------------------------------------------------------------------
# immutable snapshot cache
# ---------------------------------------------------------------------------
def snapshot_path(when: datetime | None = None) -> Path:
    when = when or datetime.now(timezone.utc)
    return CACHE_DIR / f"{when.strftime('%Y-%m-%d')}-{when.strftime('%H%M')}.json"


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
        if on_date and meta["date"] != on_date:
            continue
        wrap = load_snapshot(meta["path"])
        if not wrap:
            continue
        if kind and wrap.get("kind") != kind:
            continue
        wrap.setdefault("_path", str(meta["path"]))
        return wrap
    return None


def closing_snapshot(on_date: str) -> dict | None:
    """The close-kind snapshot for a slate date, or None. CLV grading is
    absent - not guessed - until this exists."""
    return latest_snapshot(kind="close", on_date=on_date)


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
        "props": "model fair lines only; the per-event props endpoint is not on the free-tier budget",
        "note": ("odds feed not configured: set EEPHUS_ODDS_API_KEY on the build box"
                 if not configured() else "odds feed configured"),
    }
    status.update(extra or {})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=1), encoding="utf-8")
    return status


def run(kind: str = "open", *, session=None, when: datetime | None = None) -> dict:
    """One ingest pass. Returns the status dict it wrote.

    Best-effort by construction: an unset key, a dead API, or a duplicate
    snapshot path all degrade to a status sidecar and a log line. This never
    raises into the pipeline."""
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


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB odds snapshot (The Odds API free tier).")
    ap.add_argument("--snapshot", choices=KINDS, help="pull one snapshot (costs credits)")
    ap.add_argument("--status", action="store_true", help="write/print the status sidecar only")
    args = ap.parse_args()

    if args.snapshot:
        print(json.dumps(run(args.snapshot), indent=1))
    else:
        st = write_status()
        print(json.dumps(st, indent=1))
        if not st["configured"]:
            print(f"\n  set {ENV_KEY} to enable the feed. "
                  f"One snapshot costs {credits_for()} of 500 monthly credits.")
