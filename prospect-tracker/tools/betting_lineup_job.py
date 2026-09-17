"""Capture posted lineup cards, in the dark. Self-gating. Zero Odds API credits.

WHY THIS EXISTS. Section 5j of docs/diamond-betting.md registers a candidate
that prices tonight's nine against tonight's starter. Its evidence is a record
of WHAT WAS POSTED AND WHEN, and that record cannot be rebuilt after the fact:
StatsAPI serves the card that stands now, never the card that stood at 18:40Z,
and the completed feed knows only who actually batted. So the capture has to
run while the cards are posting or the candidate has nothing to read, whatever
is decided about it later. This job is phase 1 of 5j's three phases: it
captures, and it does nothing else.

WHAT IT DELIBERATELY DOES NOT DO. It computes no candidate, no delta, no
probability and no price. It imports no pricer (`betting_model`,
`betting_export`, `betting_ingest`, `betting_credits`, `dfs_export`), and a test
pins that no served module imports this one. It spends nothing: the only
endpoint it touches is the public StatsAPI `/schedule`, which is free. Serving a
posted card is 5j phase 3 and needs a PASS, a flag and an owner flip; none of
that is here.

THE SHAPE, WHICH IS THE CLOSE JOB'S. Cron it `*/15 * * * *` under `TZ=UTC` and
let it decide. Every window decision is made HERE, against UTC instants read off
the schedule, which is correct under any box timezone, and the box timezone is
undocumented (tools/betting_close_job.py carries that measurement and the
2026-08-09 owner decision behind it). It exits 0 on every legitimate no-op,
stamps a heartbeat on every invocation including refusals, and offers `--why`
and `--selfcheck`.

THE GATE READS THIS JOB'S OWN SLATE, AND THAT IS THE ONE REAL DESIGN CHOICE
HERE. The obvious pre-call gate is `data/fantasy.json`'s schedule block, the
list `betting_export.resolve_slate` reads. It was measured unusable for this
purpose on 2026-09-17, the day this job was written, in three separate ways:

  * IT CAN BE EMPTY WHILE THE SLATE IS NOT. The 19:31:22Z build that day wrote
    `schedule.games = []` because `fantasy_schedule.fetch_probables` is
    best-effort and returns `[]` on any failure, while StatsAPI had a full card
    for the same date; a rebuild at 20:46:49Z filled it with 39 games. That is
    the property, not the outage: an empty list and a real off day are the same
    object downstream, and nothing says which one happened. A job gated on that
    list would have exited before its call on every invocation of that hour and
    stamped a healthy heartbeat each time. 5j's
    Leg M excludes games by looking for GAPS in this heartbeat, so a day of
    clean no-ops leaves no gap and the games are dropped as "no capture row"
    rather than flagged as an outage. That is the failure the close job's
    heartbeat exists to make impossible, rebuilt one layer up.
  * IT IS REGULAR-SEASON ONLY. `fetch_probables` defaults `game_type="R"`, so
    that list can never hold an F, D, L or W game. 5j requires this job to ask
    for all five so postseason cards are captured. An R-only gate in front of an
    R,F,D,L,W call makes the postseason hydration decorative and takes the job
    dark in October.
  * IT IS TRACKED, AND THE BOX REVERTS IT. `deploy/nightly-build.sh` runs
    `git checkout -- .` before the build. 5j cites that same line as the reason
    the capture store lives under `.cache/`; the gate must not sit on the
    revertible side of it.

So this job keeps its own day slate, under `.cache/lineup_captures/`, written
from its own single call, covering R, F, D, L and W, and refreshed at least
hourly. The gate is then a fact this job established itself, and an unusable
slate is LOUD (`no_local_slate`, `slate_stale`, `fetch_failed`), never a quiet
exit: those decisions are non-zero from `main` and from `--selfcheck`.

THE REFRESH ARITHMETIC. The slate is refreshed whenever it is older than
`SLATE_REFRESH_MINUTES` (60), so it is never more than an hour stale, while the
acting window `[LINEUP_WINDOW_MIN_LEAD, LINEUP_WINDOW_MAX_LEAD]` is 170 minutes
wide. A game therefore cannot cross the whole window unseen: at worst the slate
is an hour old when a game enters it, leaving 110 minutes of window. A game
added or moved earlier by more than that is picked up at the next refresh,
which is at most an hour away, and the heartbeat says which invocation refreshed.

ONE CALL PER INVOCATION, AND THE COUNTER IS ON THE FETCH. `fetch_schedule` is
the only thing in this file that touches the network, and it counts its own
calls in `CALLS`, so the count covers every caller and not just `run`. The call
asks for a three-UTC-day span (yesterday, today, tomorrow) in one request. That
is not generosity: a west-coast game at 02:10Z carries the PREVIOUS day's
`officialDate`, and a 23:50Z invocation looks forward into the next UTC date, so
a single-date call would silently skip one of two in-window games whose
`officialDate`s differ. The span makes `officialDate` a field to read rather
than a choice to make.

WHAT IT WRITES, AND WHERE. One file per acting invocation, named
`<UTC date>-<HHMM>.json` under `.cache/lineup_captures/`, created exclusively:
a second write in the same minute raises `FileExistsError`, exactly like the
odds and weather stores, because a capture is evidence about what was knowable
at an instant and a later copy must never replace an earlier one. Nothing in
this job ever opens an existing capture file for writing. The store, the slate,
the heartbeat and the run log all live under `.cache/`, which the nightly
`git checkout -- .` cannot touch.

THE RUN LOG EXISTS BECAUSE LEG M ASKS FOR SOMETHING A SINGLE-ROW HEARTBEAT
CANNOT ANSWER. 5j excludes a game unless "the job's heartbeat shows no gap
longer than 30 minutes between T-180 and T-5 minutes for the game". A last-run
file, which is what the close job keeps, is overwritten every 15 minutes and can
never show a gap. So every invocation also appends one line to
`runlog-<UTC date>.jsonl`. The heartbeat stays as well, in the close job's
shape, because `--selfcheck` asks a different question: has the SCHEDULER ever
reached this job on this machine.

THE STARTING NINE IS NOT THE `battingOrder` ARRAY. `starting_nine` reads the
completed feed's per-player `battingOrder` CODES and keeps the nine whose code
ends in `00` (100, 200, ... 900); a substitute in the sixth slot is coded 601 and
is correctly dropped. `liveData.boxscore.teams[side].battingOrder` is the CURRENT
occupant of each slot, substitutes included, and differs from the true starting
nine on 78.8% of completed sides (5j, R4 count A). The reader lives here because
5j names it as this job's, and it reads identities only: no run, score, result or
price is read from the feed, and nothing in this job relates any identity to any
outcome.

TWO THINGS THIS FILE DOES NOT OWN, RECORDED SO A READER DOES NOT GO LOOKING.
The fetch helper lives HERE, not beside `fantasy_schedule.fetch_lineups` as 5j's
Capture paragraph says, because it needs its own cache clock and its own game
types and `fantasy_schedule`'s helpers are shared with the fantasy build. And
the correction 5j owes to the `fetch_lineups` docstring (its "verified 2026-08-07"
claim covers the posted card's ORDER, not the completed feed's array) is NOT made
here: that file is outside this change.

    python tools/betting_lineup_job.py             # the cron entry point
    python tools/betting_lineup_job.py --why       # the local gate's opinion, no call
    python tools/betting_lineup_job.py --selfcheck # has the scheduler reached it here
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

log = logging.getLogger("betting_lineup_job")

# --------------------------------------------------------------------------
# where everything lives. ALL of it under .cache/, none of it tracked.
# --------------------------------------------------------------------------
STORE = ROOT / ".cache" / "lineup_captures"
HEARTBEAT_PATH = STORE / "heartbeat.json"
SLATE_PATH = STORE / "slate.json"

#: A capture file, and nothing else in the directory, matches this. Readers of
#: the store must select on it: the slate, the heartbeat and the run logs share
#: the directory on purpose (one directory is one thing to back up, and 5j says
#: to back the store up with the vintages) and none of them is a capture.
CAPTURE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}\.json$")

SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"

#: R, F, D, L, W: regular season plus wild card, division, league and world
#: series. 5j requires all five so postseason cards are captured. Coverage only;
#: whether postseason games are GRADED is 5j's own question (owner decision O20).
GAME_TYPES = "R,F,D,L,W"

#: THE ACTING WINDOW (POLICY, 5j, from R4 count B). A game 10 to 180 minutes
#: from first pitch is one whose card may post at any moment: 42 of 42 sides had
#: posted inside an hour, 46 of 48 at 60 to 120 minutes and 51 of 58 at 120 to
#: 180. Outside it the job makes no call unless the slate needs refreshing.
LINEUP_WINDOW_MIN_LEAD = 10
LINEUP_WINDOW_MAX_LEAD = 180

#: THE REFUSAL BOUNDARY (POLICY, 5j, the 5h MIN_LEAD_HOURS idiom). A row closer
#: than this to first pitch is refused and never written. After first pitch the
#: card is no longer a forecast of anything: it is the lineup that is batting,
#: and Leg M's rule that neither arm may know a change the price could not have
#: seen depends on every stored row predating first pitch by a real margin.
MIN_LEAD_MINUTES = 5

#: How old the job's own slate may be before the next invocation refreshes it.
#: See THE REFRESH ARITHMETIC in the module docstring.
SLATE_REFRESH_MINUTES = 60

#: How old it may be before staleness is an ERROR rather than a refresh. Six
#: hours of failed refreshes is not a quiet day, it is an outage, and Leg M
#: needs to be able to see it.
SLATE_HARD_STALE_MINUTES = 360

#: Hours to shift a UTC instant back by to get the UTC dates a call must span.
#: See ONE CALL PER INVOCATION in the module docstring.
SPAN_DAYS_BACK = 1
SPAN_DAYS_FORWARD = 1

#: Decisions that mean the job could not establish what it needed. Non-zero from
#: `main`, and `--selfcheck` reports them as a bad install state.
LOUD_DECISIONS = ("no_local_slate", "slate_stale", "fetch_failed")


# --------------------------------------------------------------------------
# the fetch. THE ONLY NETWORK IN THIS FILE, and it counts itself.
# --------------------------------------------------------------------------
#: Calls made by this process, by whoever made them. The counter is on the
#: helper rather than inside `run` on purpose: a counter inside `run` cannot see
#: a call made by a diagnosis, a test double or a future caller, and the
#: one-call-per-invocation rule is a claim about the PROCESS, not about `run`.
CALLS = {"n": 0, "urls": []}


def reset_calls() -> None:
    """Zero the call counter. For tests and for a long-lived diagnosis."""
    CALLS["n"] = 0
    CALLS["urls"] = []


def fetch_schedule(start_date: str, end_date: str, *, timeout: int = 30) -> dict:
    """One StatsAPI `/schedule` GET, hydrated with lineups AND probables.

    Raises on any failure; the caller decides what a failure degrades to (here:
    a loud heartbeat, never a silent no-op).

    THE TWO HYDRATES SHARE ONE CALL, which is why this job needs no second
    request. Confirmed against the live endpoint on 2026-09-17: a three-day
    span returned every game with `lineups.homePlayers`/`awayPlayers` in batting
    order once posted AND `teams.<side>.probablePitcher.id`. The cached
    `fantasy_schedule.fetch_lineups` files carry no probable at all, which is
    what 5j means when it says that helper cannot serve this.

    It uses the house session when `feed_cache` imports (that session retries
    429s), and falls back to the standard library otherwise, because a cron
    entry point must not fail on an import."""
    params = {"sportId": 1, "startDate": start_date, "endDate": end_date,
              "gameType": GAME_TYPES, "hydrate": "lineups,probablePitcher"}
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
def _parse_stamp(s: str | None) -> datetime | None:
    """An ISO stamp off the schedule or the store, normalized to aware UTC."""
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
    """The UTC dates one call must cover. See ONE CALL PER INVOCATION."""
    d = now.astimezone(timezone.utc).date()
    return ((d - timedelta(days=SPAN_DAYS_BACK)).isoformat(),
            (d + timedelta(days=SPAN_DAYS_FORWARD)).isoformat())


# --------------------------------------------------------------------------
# the slate this job owns
# --------------------------------------------------------------------------
def parse_games(payload: dict) -> list[dict]:
    """The schedule payload, flattened to the fields this job reads.

    `posted_ids` is the card IN BATTING ORDER as StatsAPI returns it. There is
    no per-game `posted` flag, deliberately, for the reason
    `fantasy_schedule.fetch_lineups` gives: a side is the unit, and one club
    files while the other has not."""
    out: list[dict] = []
    for d in (payload or {}).get("dates", []) or []:
        for g in d.get("games", []) or []:
            pk = g.get("gamePk")
            if not pk:
                continue
            status = g.get("status") or {}
            lu = g.get("lineups") or {}
            teams = g.get("teams") or {}
            row = {
                "game_pk": int(pk),
                "game_type": g.get("gameType"),
                "official_date": g.get("officialDate") or d.get("date"),
                "first_pitch": g.get("gameDate"),
                "abstract_state": status.get("abstractGameState"),
                "status": status.get("detailedState"),
                "double_header": g.get("doubleHeader") not in (None, "N"),
                "sides": {},
            }
            for side, key in (("home", "homePlayers"), ("away", "awayPlayers")):
                obj = teams.get(side) or {}
                team = obj.get("team") or {}
                pp = obj.get("probablePitcher") or {}
                players = lu.get(key) or []
                row["sides"][side] = {
                    "team_id": team.get("id"),
                    "team": team.get("name"),
                    "posted_ids": [int(p["id"]) for p in players if p.get("id")],
                    "probable_id": int(pp["id"]) if pp.get("id") else None,
                }
            out.append(row)
    return out


def _org(name: str | None) -> str | None:
    """MLB team name -> the site's 3-letter org code, best effort.

    Lazy and forgiving: `trades` is heavy and an org code that will not resolve
    must not be the reason a capture does not happen. `team_id` is on the row
    regardless, so a null `org` costs a join, not the evidence."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:                                     # noqa: BLE001
        return None


def read_slate(path: Path | None = None) -> dict | None:
    """The slate this job last wrote, or None when there is none here."""
    p = path or SLATE_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return None


def write_slate(games: list[dict], now: datetime, span: tuple[str, str],
                *, path: Path | None = None) -> None:
    """Replace the slate. It is a CACHE, not evidence: unlike a capture it may
    be overwritten, because it only ever decides whether to make a free call."""
    p = path or SLATE_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_at": _iso(now), "span": list(span),
                   "game_types": GAME_TYPES, "games": games}
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:                                     # noqa: BLE001
        log.warning("betting_lineup_job: could not write the slate cache; the "
                    "next invocation will refresh it", exc_info=True)


def lead_minutes(game: dict, now: datetime) -> float | None:
    """Minutes from `now` to this game's first pitch, or None with no stamp."""
    fp = _parse_stamp(game.get("first_pitch"))
    if fp is None:
        return None
    return (fp - now).total_seconds() / 60.0


def is_pregame(game: dict) -> bool:
    """A game that has not started and is still expected to.

    Postponed, suspended and cancelled games carry a detailed state that says
    so while the abstract state can still read Preview, so both are checked.
    A capture for a game that will not be played is not evidence about a price,
    and 5j's Leg M would have to exclude it anyway."""
    if (game.get("abstract_state") or "") != "Preview":
        return False
    detail = (game.get("status") or "").lower()
    return not any(w in detail for w in ("postpon", "cancel", "suspend", "delay"))


def in_window(game: dict, now: datetime) -> bool:
    """Is this game inside the acting window right now?"""
    if not is_pregame(game):
        return False
    lead = lead_minutes(game, now)
    return (lead is not None
            and LINEUP_WINDOW_MIN_LEAD <= lead <= LINEUP_WINDOW_MAX_LEAD)


def capturable(game: dict, now: datetime) -> bool:
    """May a row be WRITTEN for this game right now?

    Wider at the bottom than the acting window and no wider at the top: a game
    that triggered the call at lead 11 is still capturable at lead 6 on the same
    invocation, and the refusal boundary at `MIN_LEAD_MINUTES` is the only floor.
    The top stays at `LINEUP_WINDOW_MAX_LEAD` because that is the registered
    window, and a probable that churns twelve hours out would otherwise write a
    row every fifteen minutes for a card nobody has filed."""
    if not is_pregame(game):
        return False
    lead = lead_minutes(game, now)
    return (lead is not None
            and MIN_LEAD_MINUTES <= lead <= LINEUP_WINDOW_MAX_LEAD)


# --------------------------------------------------------------------------
# the decision. PURE: reads the slate, spends nothing, writes nothing.
# --------------------------------------------------------------------------
def decide(now: datetime | None = None, slate: dict | None = None,
           *, slate_path: Path | None = None) -> dict:
    """Should this invocation call StatsAPI, and why?

    Returns the decision AND the reasoning, so `--why` and the real run cannot
    disagree. `slate` is passed in by tests; otherwise it is read from disk."""
    now = now or datetime.now(timezone.utc)
    if slate is None:
        slate = read_slate(slate_path)
    out: dict = {"now": _iso(now), "call": False, "error": False,
                 "decision": "", "reason": ""}

    if not slate:
        out.update(call=True, decision="no_local_slate",
                   reason=("this job has never written a slate here, so the gate has "
                           "nothing to read. Calling once to establish one, and saying "
                           "so rather than exiting quietly: a gate that cannot answer "
                           "is an outage, not an off day"))
        return out

    fetched = _parse_stamp(slate.get("fetched_at"))
    age = None if fetched is None else (now - fetched).total_seconds() / 60.0
    out["slate_fetched_at"] = slate.get("fetched_at")
    out["slate_age_minutes"] = None if age is None else round(age, 1)
    out["slate_games"] = len(slate.get("games") or [])

    if age is None or age < 0:
        out.update(call=True, decision="no_local_slate",
                   reason=(f"the slate carries an unusable fetch stamp "
                           f"({slate.get('fetched_at')!r}); refreshing it"))
        return out

    span = tuple(slate.get("span") or ())
    want = span_for(now)
    if span != want:
        out.update(call=True, decision="slate_refresh",
                   reason=(f"the slate spans {span or '(none)'} and this invocation "
                           f"needs {want}; the UTC date has rolled"))
        return out

    if age > SLATE_HARD_STALE_MINUTES:
        # Loud, and it still calls: the repair and the alarm are the same act.
        out.update(call=True, error=True, decision="slate_stale",
                   reason=(f"the slate is {age:.0f} minutes old, past the "
                           f"{SLATE_HARD_STALE_MINUTES}-minute hard limit. Something has "
                           f"been failing the refresh for hours, which Leg M must be able "
                           f"to see rather than read as a quiet day"))
        return out

    games = slate.get("games") or []
    acting = [g for g in games if in_window(g, now)]
    out["in_window"] = len(acting)
    if acting:
        out.update(call=True, decision="capture",
                   reason=(f"{len(acting)} game(s) are {LINEUP_WINDOW_MIN_LEAD} to "
                           f"{LINEUP_WINDOW_MAX_LEAD} minutes from first pitch"))
        out["next_first_pitch"] = min(g.get("first_pitch") or "" for g in acting)
        return out

    if age >= SLATE_REFRESH_MINUTES:
        out.update(call=True, decision="slate_refresh",
                   reason=(f"no game is in the window, and the slate is {age:.0f} minutes "
                           f"old (limit {SLATE_REFRESH_MINUTES}); refreshing so a game "
                           f"added or moved cannot cross the window unseen"))
        return out

    if not games:
        out.update(decision="slate_empty",
                   reason=("this job's own call found no game in the span. An off day or "
                           "a break reads exactly like this, so it is not an error, but "
                           "it is named rather than folded into the ordinary no-op"))
        return out
    upcoming = [g for g in games
                if is_pregame(g) and (lead_minutes(g, now) or -1) > LINEUP_WINDOW_MAX_LEAD]
    nxt = min((lead_minutes(g, now) or 0) for g in upcoming) if upcoming else None
    out.update(decision="idle",
               reason=("no game is in the window"
                       + (f"; the next first pitch is {nxt:.0f} minutes out"
                          if nxt is not None else " and none is still to come today")))
    return out


# --------------------------------------------------------------------------
# what has already been captured, so a row is written only on a CHANGE
# --------------------------------------------------------------------------
def capture_files(store: Path | None = None) -> list[Path]:
    """Every capture file in the store, oldest name first. Only files matching
    `CAPTURE_NAME_RE` are captures."""
    d = store or STORE
    try:
        return sorted(p for p in d.iterdir() if CAPTURE_NAME_RE.match(p.name))
    except (OSError, FileNotFoundError):
        return []


def last_states(now: datetime, store: Path | None = None) -> dict:
    """{(game_pk, side): row} from the newest rows on disk, over the span this
    invocation covers.

    Read from the capture files themselves rather than from an index, because
    an index is a second copy of evidence and would have to be kept honest. The
    volume this scans is a couple of days of files, which is tens of files of
    tens of rows."""
    start, end = span_for(now)
    out: dict = {}
    for p in capture_files(store):
        if not (start <= p.name[:10] <= end):
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                 # noqa: BLE001
            log.warning("betting_lineup_job: capture %s will not parse; treating its "
                        "rows as unseen", p.name)
            continue
        for row in doc.get("rows", []) or []:
            key = (row.get("game_pk"), row.get("side"))
            prev = out.get(key)
            if prev is None or str(row.get("captured_at")) >= str(prev.get("captured_at")):
                out[key] = row
    return out


def changed_rows(games: list[dict], now: datetime, seen: dict) -> tuple[list[dict], dict]:
    """The rows this invocation should write, and a count of what it refused.

    A ROW PER SIDE WHOSE POSTED STATE CHANGED, and posted state is the CARD OR
    THE PROBABLE. Both halves matter and the second is easy to lose: a probable
    change on a side that has not yet filed a card is a change in posted state
    under 5j's wording, and dropping it would drop precisely the case R4's
    count C is about. Such a row is written with `posted_ids` empty, which is
    self-describing: the card is not filed and the probable is named.

    The first sighting of a side counts as a change only when there is
    something to record (a card, a probable, or both). A side with neither is
    not a posted state."""
    rows: list[dict] = []
    refused = {"late": 0, "not_pregame": 0, "out_of_window": 0, "no_stamp": 0}
    for g in games:
        lead = lead_minutes(g, now)
        if lead is None:
            refused["no_stamp"] += 1
            continue
        if not is_pregame(g):
            refused["not_pregame"] += 1
            continue
        if lead < MIN_LEAD_MINUTES:
            # THE REFUSAL. Never written, on any path. See MIN_LEAD_MINUTES.
            refused["late"] += 1
            continue
        if lead > LINEUP_WINDOW_MAX_LEAD:
            refused["out_of_window"] += 1
            continue
        for side, s in (g.get("sides") or {}).items():
            posted = list(s.get("posted_ids") or [])
            probable = s.get("probable_id")
            if not posted and probable is None:
                continue
            prev = seen.get((g["game_pk"], side))
            if prev is not None:
                if (list(prev.get("posted_ids") or []) == posted
                        and prev.get("probable_id") == probable):
                    continue
            rows.append({
                "game_pk": g["game_pk"],
                "game_type": g.get("game_type"),
                "side": side,
                "org": _org(s.get("team")),
                "team_id": s.get("team_id"),
                "posted_ids": posted,
                "probable_id": probable,
                "captured_at": _iso(now),
                "first_pitch": g.get("first_pitch"),
                "lead_minutes": round(lead, 1),
                "status": g.get("status"),
            })
    return rows, refused


def write_capture(rows: list[dict], now: datetime, *, store: Path | None = None) -> Path:
    """Write one immutable capture file and return its path.

    An existing file at the target path is a HARD STOP, not an overwrite: the
    same rule the odds snapshots (`betting_ingest.write_snapshot`) and the
    weather forecasts follow, for the same reason. `open(..., "x")` makes the
    check and the create one operation, so two processes in the same minute
    cannot both believe they are the first."""
    d = store or STORE
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{now.astimezone(timezone.utc).strftime('%Y-%m-%d-%H%M')}.json"
    payload = {
        "captured_at": _iso(now),
        "source": "statsapi /schedule hydrate=lineups,probablePitcher",
        "game_types": GAME_TYPES,
        "job": "betting_lineup_job",
        "rows": rows,
    }
    with open(path, "x", encoding="utf-8") as fh:        # raises FileExistsError
        json.dump(payload, fh, indent=1)
    return path


# --------------------------------------------------------------------------
# telemetry: the heartbeat (does the scheduler reach us) and the run log (gaps)
# --------------------------------------------------------------------------
def write_heartbeat(d: dict, *, path: Path | None = None) -> None:
    """Record that the job RAN, whatever it decided. Best effort and silent on
    failure: telemetry must never be the reason a capture does not happen."""
    p = path or HEARTBEAT_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_run_utc": _iso(datetime.now(timezone.utc)),
            "decision": d.get("decision"),
            "reason": d.get("reason"),
            "called": bool(d.get("call")),
            "error": bool(d.get("error")),
            "in_window": d.get("in_window"),
            "slate_games": d.get("slate_games"),
            "slate_age_minutes": d.get("slate_age_minutes"),
            "rows_written": d.get("rows_written"),
            "refused": d.get("refused"),
            "capture_file": d.get("capture_file"),
        }
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:                                     # noqa: BLE001
        log.warning("betting_lineup_job: could not write the heartbeat; the capture "
                    "is unaffected", exc_info=True)


def read_heartbeat(path: Path | None = None) -> dict | None:
    """The last recorded invocation, or None when the job has never run here."""
    p = path or HEARTBEAT_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return None


def runlog_path(now: datetime, *, store: Path | None = None) -> Path:
    return (store or STORE) / f"runlog-{now.astimezone(timezone.utc).date().isoformat()}.jsonl"


def append_runlog(d: dict, now: datetime, *, store: Path | None = None) -> None:
    """One line per invocation, append only.

    THIS IS WHAT LEG M READS. A last-run heartbeat is overwritten every fifteen
    minutes and can never show the gap 5j's exclusion rule looks for. Best
    effort, same posture as the heartbeat."""
    try:
        p = runlog_path(now, store=store)
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"at": _iso(now), "decision": d.get("decision"),
                           "called": bool(d.get("call")), "error": bool(d.get("error")),
                           "in_window": d.get("in_window"),
                           "rows_written": d.get("rows_written")},
                          separators=(",", ":"))
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:                                     # noqa: BLE001
        log.warning("betting_lineup_job: could not append the run log; the capture "
                    "is unaffected", exc_info=True)


# --------------------------------------------------------------------------
# the completed-feed reader (5j names it here; it reads identities only)
# --------------------------------------------------------------------------
def starting_nine(feed: dict, side: str) -> list[int]:
    """The nine who STARTED for `side`, off the completed feed, in slot order.

    THE CODE, NEVER THE ARRAY. Each player under
    `liveData.boxscore.teams[side].players` carries its own `battingOrder` code:
    `100` is the starting leadoff hitter, `101` the first man to bat in that
    slot after him, `601` a substitute in the sixth. The nine whose code ends in
    `00` are the starters. `liveData.boxscore.teams[side].battingOrder` is a
    different object: it is the CURRENT occupant of each slot when the feed was
    written, and it differs from the true starting nine on 3,464 of 4,394
    completed sides, 78.8% (5j, R4 count A).

    Reads identities only. No run, score, result, inning or price is read from
    the feed here, and nothing in this job relates an identity to an outcome.

    Returns however many starters the feed carries; a caller that needs nine
    checks the length rather than being handed a padded list."""
    players = (((feed or {}).get("liveData") or {}).get("boxscore") or {}) \
        .get("teams", {}).get(side, {}).get("players") or {}
    found: list[tuple[int, int]] = []
    for p in players.values():
        code = str(p.get("battingOrder") or "")
        if len(code) != 3 or not code.isdigit() or not code.endswith("00"):
            continue
        slot = int(code[0])
        pid = ((p.get("person") or {}).get("id"))
        if slot and pid:
            found.append((slot, int(pid)))
    found.sort()
    return [pid for _, pid in found]


# --------------------------------------------------------------------------
# the invocation
# --------------------------------------------------------------------------
def run(now: datetime | None = None, *, store: Path | None = None,
        slate_path: Path | None = None, fetch=None) -> dict:
    """One invocation: decide, at most one call, write what changed.

    THE CAPTURE IS COMPUTED FROM THE FRESH RESPONSE, never from the slate. The
    slate's only job is deciding whether to make the call; every window, lead
    and refusal that reaches a written row is recomputed against the instants in
    the response. A stale slate can therefore cost a call or save one, and can
    never put a wrong number in the store."""
    now = now or datetime.now(timezone.utc)
    store = store or STORE
    slate_path = slate_path or (store / SLATE_PATH.name)
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
        # LOUD. A failed call inside the window is a missed capture, and a
        # missed capture that exits 0 is the silent failure this whole design is
        # built against. Leg M must be able to read it off the run log.
        log.exception("betting_lineup_job: the schedule call failed")
        d["error"] = True
        d["decision"] = "fetch_failed"
        d["reason"] = (f"the StatsAPI /schedule call for {span[0]}..{span[1]} failed "
                       f"({type(exc).__name__}). Nothing was captured on this invocation")
        return d

    games = parse_games(payload)
    write_slate(games, now, span, path=slate_path)
    d["slate_games"] = len(games)
    d["in_window"] = sum(1 for g in games if in_window(g, now))

    rows, refused = changed_rows(games, now, last_states(now, store))
    d["refused"] = refused
    if not rows:
        if d["gate_decision"] == "capture":
            d["decision"] = "no_change"
            d["reason"] = ("the call was made and no side's card or probable had changed "
                           "since its last capture row")
        else:
            # The gate called to ESTABLISH or REFRESH the slate, and it did.
            # `error` is deliberately left as the gate set it: an invocation that
            # repaired a six-hour staleness still reports the hours that were
            # lost, and only the NEXT invocation reads clean.
            d["decision"] = "slate_refreshed"
            d["reason"] = (f"the slate was refreshed from this job's own call "
                           f"({len(games)} game(s) in {span[0]}..{span[1]}); the gate "
                           f"had said: {d['gate_decision']}")
        return d

    try:
        path = write_capture(rows, now, store=store)
    except FileExistsError:
        # Two invocations in one minute. The store is immutable by design, so
        # the second one loses rather than overwriting evidence. Not an error:
        # the first invocation's file is the honest record of that minute.
        d["decision"] = "same_minute_collision"
        d["reason"] = ("a capture file for this minute already exists; captures are "
                       "immutable, so this invocation wrote nothing")
        return d
    d["rows_written"] = len(rows)
    d["capture_file"] = path.name
    d["decision"] = "captured"
    d["reason"] = f"{len(rows)} side(s) changed posted state"
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--why", action="store_true",
                    help="report what the LOCAL GATE sees and exit. Makes no "
                         "network call and writes nothing")
    ap.add_argument("--selfcheck", action="store_true",
                    help="print the install state: whether this machine has ever "
                         "run the job, when, and what it last decided")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")

    if args.selfcheck:
        # THE POST-INSTALL CHECK, and it asks a different question from --why.
        # --why reads the same on a box where nothing is scheduled; this reads
        # the heartbeat, which only the SCHEDULER can have stamped.
        hb = read_heartbeat()
        print(f"lineup job    : {Path(__file__).resolve()}")
        print(f"capture store : {STORE}")
        print(f"heartbeat     : {HEARTBEAT_PATH}")
        print(f"captures held : {len(capture_files())}")
        if not hb:
            print("scheduler     : NEVER RUN on this machine. Nothing has executed "
                  "this job here, so no cron or task is reaching it.")
            print("               Linux: add the */15 line to "
                  "deploy/betting-crontab.example's install and `crontab -e`.")
            return 1
        print(f"scheduler     : last ran {hb.get('last_run_utc')} UTC")
        print(f"last decision : {hb.get('decision')} - {hb.get('reason')}")
        print(f"last capture  : {hb.get('capture_file')} "
              f"({hb.get('rows_written')} row(s))")
        if hb.get("decision") in LOUD_DECISIONS or hb.get("error"):
            print("state         : BAD. The last invocation could not establish what it "
                  "needed, so the capture is not running correctly here.")
            return 1
        return 0

    if args.why:
        # STRICTLY OFFLINE, AND IT SAYS SO. This reports the local gate's
        # opinion, which is what the job would decide before making any call.
        # It is not a report of what StatsAPI holds, and on a box whose slate is
        # stale it will say that instead of hiding it.
        d = decide()
        print(f"{d['decision']}: {d['reason']}")
        print(f"  {'; '.join(f'{k}={v}' for k, v in d.items() if k != 'reason')}")
        print("  (--why reads this job's own slate cache only. It makes no network "
              "call, spends nothing and writes nothing, so it reports the GATE, "
              "not the schedule.)")
        return 0

    try:
        d = run()
    except Exception:
        log.exception("betting_lineup_job: the invocation failed")
        return 1

    verdict = "FAIL" if d.get("error") else ("CAPTURE" if d.get("rows_written") else "skip")
    print(f"{verdict}: {d['decision']}: {d['reason']}")
    if args.verbose:
        print(f"  {'; '.join(f'{k}={v}' for k, v in d.items() if k != 'reason')}")

    # Stamped after the work, unlike the close job's, because this job's own
    # decision fields (rows written, what it refused) are the thing worth
    # recording and they do not exist until the work is done. A run that dies
    # before here is a crash, which is a non-zero exit and a traceback in the
    # log, not a silent no-op.
    write_heartbeat(d)
    append_runlog(d, datetime.now(timezone.utc))

    if d.get("error"):
        log.error("betting_lineup_job: %s", d["reason"])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
