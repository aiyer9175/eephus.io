"""Capture the home-plate umpire assignment, in the dark. Self-gating. Zero Odds API credits.

WHY THIS EXISTS. The docs/diamond-betting.md section "The home-plate umpire: a
dark pregame assignment capture" (long form docs/BETTING_UMPIRE_GATE.md)
registers a dark umpire family whose evidence is a record of WHO WAS NAMED TO
WORK THE PLATE AND WHEN THAT WAS KNOWABLE. That record cannot be rebuilt after
the fact: the schedule serves the assignment that stands now, and a completed
feed knows only who did work the plate, which is dated after the game. Its
capture time rule counts an assignment only when a row here was captured
strictly before the slate's price vintage, so the capture has to run while the
assignments are being published or the family has nothing to read. This job
captures, and it does nothing else.

WHAT IT DELIBERATELY DOES NOT DO. It computes no candidate, no umpire rate, no
effect, no probability and no price. It reads no game feed, no score, no
result, no line and no price. It imports no pricer (`betting_model`,
`betting_export`, `betting_ingest`, `betting_credits`), no settle, scores or
results module and no management module, and a test pins that no served module
imports this one. Every field it stores is named in `ROW_FIELDS`; the schedule
payload's scores, winners and line scores are dropped at parse time, so no
outcome field sits beside an assignment in anything this job writes. It spends
nothing: the only endpoint it touches is the public StatsAPI `/schedule`.

THE SHAPE IS THE LINEUP JOB'S (tools/betting_lineup_job.py), with its own
store, because that job's test forbids any module importing it. Cron it
`*/15 * * * *` under `TZ=UTC` and let it decide. It keeps its own slate under
`.cache/umpire_captures/`, written from its own single call covering R, F, D, L
and W; an unusable slate is LOUD (`no_local_slate`, `slate_stale`,
`fetch_failed`), never a quiet exit.

THE WINDOW. A game is watched from 36 hours before first pitch
(`WINDOW_MAX_LEAD_MINUTES`) to the refusal boundary 5 minutes before it
(`MIN_LEAD_MINUTES`). The publication lead is not measured yet (the section's
one probe saw a plate umpire at warmup and none 48 hours out), so the window is
wide on purpose: the earliest sighting is the fact the registration needs, and
the open odds snapshot it is compared against is taken at 13:10 UTC. While any
game is in the window the job calls when its slate is at least
`CAPTURE_INTERVAL_MINUTES` (30) old, so publication is bracketed to within
about half an hour; outside it the slate refreshes hourly.

ONE CALL PER INVOCATION, COUNTED ON THE FETCH. `fetch_schedule` is the only
network in this file and counts its own calls in `CALLS`. It asks for the UTC
dates D-1 to D+2 in one request, because a 36-hour look-ahead can cross two UTC
dates and a west-coast game carries the previous `officialDate`.

WHAT A ROW IS. One row per game whose plate assignment CHANGED since its last
row: the first sighting with a plate umpire, a different umpire, or a
retraction (`hp_umpire_id` null after an assignment had been recorded). A game
seen with no plate umpire writes no row; the job notes the instant in its
`unassigned.json` cache, and the game's next row carries it as
`last_unassigned_at`, so publication lies after that instant and at or before
`captured_at`. That cache may be overwritten; captures may not.

WHAT IT WRITES, AND WHERE. One file per invocation that has rows, named
`<UTC date>-<HHMM>.json` under `.cache/umpire_captures/`, created exclusively:
a second write in the same minute raises `FileExistsError` and the invocation
writes nothing. The slate, the unassigned cache, the heartbeat and a per-day
append-only run log share the directory and never match `CAPTURE_NAME_RE`.
Everything lives under `.cache/`, which the nightly `git checkout -- .` cannot
touch.

    python tools/betting_umpire_job.py             # the cron entry point
    python tools/betting_umpire_job.py --why       # the local gate's opinion, no call
    python tools/betting_umpire_job.py --selfcheck # has the scheduler reached it here
    python tools/betting_umpire_job.py --store DIR # one local run into another store
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("betting_umpire_job")

# --------------------------------------------------------------------------
# where everything lives. ALL of it under .cache/, none of it tracked.
# --------------------------------------------------------------------------
STORE = ROOT / ".cache" / "umpire_captures"
HEARTBEAT_NAME = "heartbeat.json"
SLATE_NAME = "slate.json"
UNASSIGNED_NAME = "unassigned.json"

#: A capture file, and nothing else in the directory, matches this.
CAPTURE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}\.json$")

SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"

#: Regular season plus wild card, division, league and world series.
GAME_TYPES = "R,F,D,L,W"

#: The ONE hydrate. Never linescore, decisions or anything else that would put
#: a score beside an assignment in the response this job reads.
HYDRATE = "officials"

#: The official whose assignment is captured.
HOME_PLATE = "Home Plate"

#: The capture schema the registration names.
CAPTURE_SCHEMA = "umpire_capture/1"

#: Every field a capture row carries, in order, and nothing else. A test pins
#: this list to the registration text.
ROW_FIELDS = ("game_pk", "game_type", "official_date", "first_pitch", "captured_at",
              "lead_minutes", "status", "double_header", "home_team_id",
              "away_team_id", "venue_id", "hp_umpire_id", "hp_umpire_name", "crew",
              "last_unassigned_at")

#: Keys that would be an outcome, a line or a price. None may appear anywhere in
#: anything this job writes; tests walk every written file for them.
OUTCOME_KEYS = ("score", "scores", "isWinner", "winner", "loser", "runs", "linescore",
                "decisions", "result", "results", "leagueRecord", "seriesStatus",
                "total", "over", "under", "odds", "price", "edge", "moneyline")

#: THE WINDOW (POLICY, the registration's long form U-2).
WINDOW_MAX_LEAD_MINUTES = 36 * 60
MIN_LEAD_MINUTES = 5

#: How old the slate may be before an in-window invocation calls again.
CAPTURE_INTERVAL_MINUTES = 30
#: How old it may be before an idle invocation refreshes it.
SLATE_REFRESH_MINUTES = 60
#: How old it may be before staleness is an ERROR rather than a refresh.
SLATE_HARD_STALE_MINUTES = 360

SPAN_DAYS_BACK = 1
SPAN_DAYS_FORWARD = 2

#: How far back the store is read for each game's last row and the unassigned
#: cache is kept: wider than the window plus the span.
STATE_LOOKBACK_DAYS = 4

LOUD_DECISIONS = ("no_local_slate", "slate_stale", "fetch_failed")


# --------------------------------------------------------------------------
# the fetch. THE ONLY NETWORK IN THIS FILE, and it counts itself.
# --------------------------------------------------------------------------
CALLS = {"n": 0, "urls": []}


def reset_calls() -> None:
    """Zero the call counter. For tests and for a long-lived diagnosis."""
    CALLS["n"] = 0
    CALLS["urls"] = []


def schedule_params(start_date: str, end_date: str) -> dict:
    return {"sportId": 1, "startDate": start_date, "endDate": end_date,
            "gameType": GAME_TYPES, "hydrate": HYDRATE}


def fetch_schedule(start_date: str, end_date: str, *, timeout: int = 30) -> dict:
    """One StatsAPI `/schedule` GET hydrated with officials. Raises on any
    failure; the caller makes a failure loud. Uses the house session when
    `feed_cache` imports (it retries 429s), else the standard library."""
    params = schedule_params(start_date, end_date)
    url = SCHEDULE_API + "?" + urllib.parse.urlencode(params)
    CALLS["n"] += 1
    CALLS["urls"].append(url)
    try:
        import feed_cache
        session = feed_cache.SESSION
    except Exception:                                     # noqa: BLE001
        session = None
    if session is not None:
        resp = session.get(SCHEDULE_API, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    with urllib.request.urlopen(url, timeout=timeout) as fh:
        return json.loads(fh.read().decode("utf-8"))


# --------------------------------------------------------------------------
# instants
# --------------------------------------------------------------------------
def _parse_stamp(s) -> datetime | None:
    """An ISO stamp off the schedule or the store, as aware UTC."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def span_for(now: datetime) -> tuple[str, str]:
    """The UTC dates one call covers."""
    d = now.astimezone(timezone.utc).date()
    return ((d - timedelta(days=SPAN_DAYS_BACK)).isoformat(),
            (d + timedelta(days=SPAN_DAYS_FORWARD)).isoformat())


# --------------------------------------------------------------------------
# the parse: an ALLOWLIST, so a score in the payload never reaches a file
# --------------------------------------------------------------------------
def _int_or_none(v):
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def parse_games(payload: dict) -> list[dict]:
    """The schedule payload, flattened to the fields this job reads and nothing
    else. Scores, `isWinner`, records and series status are never copied."""
    out: list[dict] = []
    for d in (payload or {}).get("dates", []) or []:
        for g in d.get("games", []) or []:
            pk = _int_or_none(g.get("gamePk"))
            if not pk:
                continue
            status = g.get("status") or {}
            teams = g.get("teams") or {}
            crew, hp_id, hp_name = [], None, None
            for o in g.get("officials") or []:
                otype = o.get("officialType")
                person = o.get("official") or {}
                oid = _int_or_none(person.get("id"))
                crew.append({"type": otype, "id": oid})
                if otype == HOME_PLATE and oid is not None and hp_id is None:
                    hp_id, hp_name = oid, person.get("fullName")
            out.append({
                "game_pk": pk,
                "game_type": g.get("gameType"),
                "official_date": g.get("officialDate") or d.get("date"),
                "first_pitch": g.get("gameDate"),
                "abstract_state": status.get("abstractGameState"),
                "status": status.get("detailedState"),
                "double_header": g.get("doubleHeader") not in (None, "N"),
                "home_team_id": _int_or_none(((teams.get("home") or {}).get("team") or {}).get("id")),
                "away_team_id": _int_or_none(((teams.get("away") or {}).get("team") or {}).get("id")),
                "venue_id": _int_or_none((g.get("venue") or {}).get("id")),
                "hp_umpire_id": hp_id,
                "hp_umpire_name": hp_name,
                "crew": crew,
            })
    return out


# --------------------------------------------------------------------------
# small JSON caches under the store (overwritable, never evidence)
# --------------------------------------------------------------------------
def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return None


def _write_json_atomic(p: Path, payload) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def read_slate(path: Path) -> dict | None:
    return _read_json(path)


def write_slate(games: list[dict], now: datetime, span: tuple[str, str], *, path: Path) -> None:
    """Replace the slate. A cache that only decides whether to make a free call."""
    try:
        _write_json_atomic(path, {"fetched_at": _iso(now), "span": list(span),
                                  "game_types": GAME_TYPES, "games": games})
    except Exception:                                     # noqa: BLE001
        log.warning("betting_umpire_job: could not write the slate cache", exc_info=True)


def read_unassigned(path: Path) -> dict:
    doc = _read_json(path)
    return dict(doc) if isinstance(doc, dict) else {}


def write_unassigned(state: dict, now: datetime, *, path: Path) -> None:
    """Keep only entries inside the lookback, then replace the file."""
    cut = now - timedelta(days=STATE_LOOKBACK_DAYS)
    kept = {k: v for k, v in state.items()
            if (_parse_stamp(v) or cut) > cut}
    try:
        _write_json_atomic(path, kept)
    except Exception:                                     # noqa: BLE001
        log.warning("betting_umpire_job: could not write the unassigned cache", exc_info=True)


# --------------------------------------------------------------------------
# the window
# --------------------------------------------------------------------------
def lead_minutes(game: dict, now: datetime) -> float | None:
    fp = _parse_stamp(game.get("first_pitch"))
    return None if fp is None else (fp - now).total_seconds() / 60.0


def is_pregame(game: dict) -> bool:
    """Not started and still expected to be played."""
    if (game.get("abstract_state") or "") != "Preview":
        return False
    detail = (game.get("status") or "").lower()
    return not any(w in detail for w in ("postpon", "cancel", "suspend", "delay"))


def in_window(game: dict, now: datetime) -> bool:
    if not is_pregame(game):
        return False
    lead = lead_minutes(game, now)
    return lead is not None and MIN_LEAD_MINUTES <= lead <= WINDOW_MAX_LEAD_MINUTES


# --------------------------------------------------------------------------
# the decision. PURE: reads the slate, spends nothing, writes nothing.
# --------------------------------------------------------------------------
def decide(now: datetime | None = None, slate: dict | None = None,
           *, slate_path: Path | None = None) -> dict:
    """Should this invocation call StatsAPI, and why?"""
    now = now or datetime.now(timezone.utc)
    if slate is None:
        slate = read_slate(slate_path or (STORE / SLATE_NAME))
    out: dict = {"now": _iso(now), "call": False, "error": False,
                 "decision": "", "reason": ""}
    if not slate:
        out.update(call=True, decision="no_local_slate",
                   reason=("this job has never written a slate here; calling once to "
                           "establish one, and saying so"))
        return out

    fetched = _parse_stamp(slate.get("fetched_at"))
    age = None if fetched is None else (now - fetched).total_seconds() / 60.0
    out["slate_fetched_at"] = slate.get("fetched_at")
    out["slate_age_minutes"] = None if age is None else round(age, 1)
    out["slate_games"] = len(slate.get("games") or [])
    if age is None or age < 0:
        out.update(call=True, decision="no_local_slate",
                   reason=f"the slate carries an unusable fetch stamp "
                          f"({slate.get('fetched_at')!r}); refreshing it")
        return out

    span, want = tuple(slate.get("span") or ()), span_for(now)
    if span != want:
        out.update(call=True, decision="slate_refresh",
                   reason=f"the slate spans {span or '(none)'} and this invocation "
                          f"needs {want}; the UTC date has rolled")
        return out
    if age > SLATE_HARD_STALE_MINUTES:
        out.update(call=True, error=True, decision="slate_stale",
                   reason=f"the slate is {age:.0f} minutes old, past the "
                          f"{SLATE_HARD_STALE_MINUTES}-minute hard limit")
        return out

    games = slate.get("games") or []
    acting = [g for g in games if in_window(g, now)]
    out["in_window"] = len(acting)
    if acting and age >= CAPTURE_INTERVAL_MINUTES:
        out.update(call=True, decision="capture",
                   reason=f"{len(acting)} game(s) are {MIN_LEAD_MINUTES} minutes to "
                          f"{WINDOW_MAX_LEAD_MINUTES // 60} hours from first pitch and the "
                          f"slate is {age:.0f} minutes old")
        return out
    if acting:
        out.update(decision="too_soon",
                   reason=f"{len(acting)} game(s) are in the window and the last call "
                          f"was {age:.0f} minutes ago (interval {CAPTURE_INTERVAL_MINUTES})")
        return out
    if age >= SLATE_REFRESH_MINUTES:
        out.update(call=True, decision="slate_refresh",
                   reason=f"no game is in the window and the slate is {age:.0f} minutes "
                          f"old (limit {SLATE_REFRESH_MINUTES})")
        return out
    if not games:
        out.update(decision="slate_empty",
                   reason="this job's own call found no game in the span (an off day, "
                          "a break or the offseason)")
        return out
    out.update(decision="idle", reason="no game is in the window")
    return out


# --------------------------------------------------------------------------
# what has already been captured, so a row is written only on a CHANGE
# --------------------------------------------------------------------------
def capture_files(store: Path | None = None) -> list[Path]:
    d = store or STORE
    try:
        return sorted(p for p in d.iterdir() if CAPTURE_NAME_RE.match(p.name))
    except (OSError, FileNotFoundError):
        return []


def last_states(now: datetime, store: Path | None = None) -> dict:
    """{game_pk: newest row} over the capture files inside the lookback."""
    cut = (now.astimezone(timezone.utc).date() - timedelta(days=STATE_LOOKBACK_DAYS)).isoformat()
    out: dict = {}
    for p in capture_files(store):
        if p.name[:10] < cut:
            continue
        doc = _read_json(p)
        if not isinstance(doc, dict):
            log.warning("betting_umpire_job: capture %s will not parse; its rows "
                        "are treated as unseen", p.name)
            continue
        for row in doc.get("rows", []) or []:
            pk = row.get("game_pk")
            prev = out.get(pk)
            if prev is None or str(row.get("captured_at")) >= str(prev.get("captured_at")):
                out[pk] = row
    return out


def changed_rows(games: list[dict], now: datetime, seen: dict,
                 unassigned: dict) -> tuple[list[dict], dict, dict]:
    """The rows to write, the refusal counts, and the updated unassigned cache.

    The cache passed in is not mutated."""
    rows: list[dict] = []
    refused = {"late": 0, "not_pregame": 0, "out_of_window": 0, "no_stamp": 0}
    state = dict(unassigned)
    for g in games:
        lead = lead_minutes(g, now)
        if lead is None:
            refused["no_stamp"] += 1
            continue
        if not is_pregame(g):
            refused["not_pregame"] += 1
            continue
        if lead < MIN_LEAD_MINUTES:
            refused["late"] += 1          # THE REFUSAL. Never written, on any path.
            continue
        if lead > WINDOW_MAX_LEAD_MINUTES:
            refused["out_of_window"] += 1
            continue
        pk, hp = g["game_pk"], g.get("hp_umpire_id")
        prev = seen.get(pk)
        key = str(pk)
        changed = (hp is not None) if prev is None else (prev.get("hp_umpire_id") != hp)
        if changed:
            rows.append({
                "game_pk": pk,
                "game_type": g.get("game_type"),
                "official_date": g.get("official_date"),
                "first_pitch": g.get("first_pitch"),
                "captured_at": _iso(now),
                "lead_minutes": round(lead, 1),
                "status": g.get("status"),
                "double_header": bool(g.get("double_header")),
                "home_team_id": g.get("home_team_id"),
                "away_team_id": g.get("away_team_id"),
                "venue_id": g.get("venue_id"),
                "hp_umpire_id": hp,
                "hp_umpire_name": g.get("hp_umpire_name") if hp is not None else None,
                "crew": [{"type": c.get("type"), "id": c.get("id")}
                         for c in (g.get("crew") or [])],
                "last_unassigned_at": state.get(key),
            })
        if hp is None:
            state[key] = _iso(now)
    return rows, refused, state


def write_capture(rows: list[dict], now: datetime, *, store: Path | None = None) -> Path:
    """One immutable capture file. An existing file is a HARD STOP."""
    d = store or STORE
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{now.astimezone(timezone.utc).strftime('%Y-%m-%d-%H%M')}.json"
    payload = {
        "schema": CAPTURE_SCHEMA,
        "captured_at": _iso(now),
        "source": f"statsapi /schedule hydrate={HYDRATE}",
        "game_types": GAME_TYPES,
        "job": "betting_umpire_job",
        "rows": [{k: r.get(k) for k in ROW_FIELDS} for r in rows],
    }
    with open(path, "x", encoding="utf-8") as fh:        # raises FileExistsError
        json.dump(payload, fh, indent=1)
    return path


# --------------------------------------------------------------------------
# telemetry: the heartbeat and the per-day run log
# --------------------------------------------------------------------------
def write_heartbeat(d: dict, *, store: Path | None = None) -> None:
    try:
        _write_json_atomic((store or STORE) / HEARTBEAT_NAME, {
            "last_run_utc": _iso(datetime.now(timezone.utc)),
            "decision": d.get("decision"), "reason": d.get("reason"),
            "called": bool(d.get("call")), "error": bool(d.get("error")),
            "in_window": d.get("in_window"), "slate_games": d.get("slate_games"),
            "slate_age_minutes": d.get("slate_age_minutes"),
            "rows_written": d.get("rows_written"), "refused": d.get("refused"),
            "capture_file": d.get("capture_file"),
        })
    except Exception:                                     # noqa: BLE001
        log.warning("betting_umpire_job: could not write the heartbeat", exc_info=True)


def read_heartbeat(store: Path | None = None) -> dict | None:
    return _read_json((store or STORE) / HEARTBEAT_NAME)


def append_runlog(d: dict, now: datetime, *, store: Path | None = None) -> None:
    try:
        p = (store or STORE) / f"runlog-{now.astimezone(timezone.utc).date().isoformat()}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"at": _iso(now), "decision": d.get("decision"),
                           "called": bool(d.get("call")), "error": bool(d.get("error")),
                           "in_window": d.get("in_window"),
                           "rows_written": d.get("rows_written")},
                          separators=(",", ":"))
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:                                     # noqa: BLE001
        log.warning("betting_umpire_job: could not append the run log", exc_info=True)


# --------------------------------------------------------------------------
# the invocation
# --------------------------------------------------------------------------
def run(now: datetime | None = None, *, store: Path | None = None, fetch=None) -> dict:
    """One invocation: decide, at most one call, write what changed. Every
    window, lead and refusal that reaches a row is recomputed from the fresh
    response, never from the slate."""
    now = now or datetime.now(timezone.utc)
    store = store or STORE
    slate_path, unassigned_path = store / SLATE_NAME, store / UNASSIGNED_NAME
    fetch = fetch or fetch_schedule

    d = decide(now, slate_path=slate_path)
    d["gate_decision"] = d["decision"]
    d["rows_written"] = 0
    if not d["call"]:
        return d

    span = span_for(now)
    try:
        payload = fetch(span[0], span[1])
    except Exception as exc:                              # noqa: BLE001
        log.exception("betting_umpire_job: the schedule call failed")
        d.update(error=True, decision="fetch_failed",
                 reason=f"the StatsAPI /schedule call for {span[0]}..{span[1]} failed "
                        f"({type(exc).__name__}); nothing was captured")
        return d

    games = parse_games(payload)
    write_slate(games, now, span, path=slate_path)
    d["slate_games"] = len(games)
    d["in_window"] = sum(1 for g in games if in_window(g, now))

    rows, refused, state = changed_rows(games, now, last_states(now, store),
                                        read_unassigned(unassigned_path))
    d["refused"] = refused
    if rows:
        try:
            path = write_capture(rows, now, store=store)
        except FileExistsError:
            d["decision"] = "same_minute_collision"
            d["reason"] = ("a capture file for this minute already exists; captures are "
                           "immutable, so this invocation wrote nothing")
            return d
        d["rows_written"] = len(rows)
        d["capture_file"] = path.name
        d["decision"] = "captured"
        d["reason"] = f"{len(rows)} game(s) changed plate assignment"
    elif d["gate_decision"] == "capture":
        d["decision"] = "no_change"
        d["reason"] = "the call was made and no game's plate assignment had changed"
    else:
        d["decision"] = "slate_refreshed"
        d["reason"] = (f"the slate was refreshed ({len(games)} game(s) in "
                       f"{span[0]}..{span[1]}); the gate had said: {d['gate_decision']}")
    write_unassigned(state, now, path=unassigned_path)
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--why", action="store_true",
                    help="report what the LOCAL GATE sees; no network call, no write")
    ap.add_argument("--selfcheck", action="store_true",
                    help="print the install state off the heartbeat")
    ap.add_argument("--store", type=Path, default=None,
                    help="capture store directory (default .cache/umpire_captures)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    store = args.store or STORE

    if args.selfcheck:
        hb = read_heartbeat(store)
        print(f"umpire job    : {Path(__file__).resolve()}")
        print(f"capture store : {store}")
        print(f"captures held : {len(capture_files(store))}")
        if not hb:
            print("scheduler     : NEVER RUN on this machine; no cron or task reaches it")
            return 1
        print(f"scheduler     : last ran {hb.get('last_run_utc')} UTC")
        print(f"last decision : {hb.get('decision')} - {hb.get('reason')}")
        if hb.get("decision") in LOUD_DECISIONS or hb.get("error"):
            print("state         : BAD. The last invocation could not establish what it needed.")
            return 1
        return 0

    if args.why:
        d = decide(slate_path=store / SLATE_NAME)
        print(f"{d['decision']}: {d['reason']}")
        print("  (--why reads this job's own slate cache only: no network call, no "
              "write, so it reports the GATE, not the schedule.)")
        return 0

    try:
        d = run(store=store)
    except Exception:
        log.exception("betting_umpire_job: the invocation failed")
        return 1
    verdict = "FAIL" if d.get("error") else ("CAPTURE" if d.get("rows_written") else "skip")
    print(f"{verdict}: {d['decision']}: {d['reason']}")
    if args.verbose:
        print(f"  {'; '.join(f'{k}={v}' for k, v in d.items() if k != 'reason')}")
    write_heartbeat(d, store=store)
    append_runlog(d, datetime.now(timezone.utc), store=store)
    return 2 if d.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
