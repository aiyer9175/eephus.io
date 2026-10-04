# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Staff history ingest from the MLB StatsAPI coaches endpoint (Staff Gems stage 0, the fetch half).

Design: docs/staff-gems/DESIGN.md (section 7, stage 0). Gate: docs/staff-gems/STAFF_GEMS_GATE.md,
registered before this fetch ran. Source registry entry: statsapi_coaches (legal_risk ambiguous).

WHAT IT FETCHES, raw, into .cache/staff/ only (gitignored; never data/, never prospects.db):
  for every season 2008 to 2026
    teams?sportId=1&season=Y                    the MLB clubs
    teams/affiliates?teamIds=<all clubs>&season=Y   every affiliate, complex, DSL and pseudo-team
    schedule?sportId=S&season=Y&gameType=R      one call per level, for each team's first and last game
    teams/{id}/coaches?season=Y                 every holder of every job in the season
  and, ONLY where a team-season's list shows a job with two holders, a person with two jobs, or a
  person on two teams of one organization, date bisection with teams/{id}/coaches?date=D between
  the team's first and last game, to the day.

WHAT IT NEVER DOES. It reads no grade, no player, no outcome and no database; it computes no
development number for any person; it writes nothing under data/ and publishes nothing. Parsing
the cache into tables is stage 1 (staff_identity.py and the parse half, not built here).

Request discipline: at most 3 requests a second, a descriptive User-Agent, one retry on a
transient failure, and the run STOPS after 3 consecutive non-200 answers. Every response is cached
on first success, so a stopped run resumes where it left off. MLBAM's notice permits only
"individual, non-commercial, non-bulk use"; this one-time fetch is bulk use, which is why the
registry rates the source ambiguous (owner answer SG-Q2 chose it with that rating).

Run: python staff_ingest.py --fetch [--seasons 2008-2026] [--max-requests N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "staff"

BASE_URL = "https://statsapi.mlb.com"
USER_AGENT = ("eephus.io-prospect-tracker/1.0 (+https://eephus.io; staff history ingest, "
              "one-time research fetch, at most 3 requests a second)")
FIRST_SEASON = 2008
LAST_SEASON = 2026
MIN_INTERVAL_S = 1.0 / 3.0
MAX_CONSECUTIVE_FAILURES = 3
RETRY_PAUSE_S = 2.0
DEFAULT_MAX_REQUESTS = 25_000
TIMEOUT_S = 30
SCHEDULE_FIELDS = "dates,date,games,gameType,status,codedGameState,teams,away,home,team,id"
PLAYED_STATES = ("F",)

Opener = Callable[[str, dict], "tuple[int, bytes]"]


class FetchStopped(RuntimeError):
    """Raised when the run must stop: repeated non-200 answers or the request budget."""


def _urllib_opener(url: str, headers: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return int(r.status), r.read()
    except urllib.error.HTTPError as e:
        return int(e.code), b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b""


class Fetcher:
    """Rate-limited, caching GET of StatsAPI paths. A response is cached under
    <cache_dir>/raw/<kind>/<key>.json on its first 200 and served from there after."""

    def __init__(self, cache_dir: Path = CACHE_DIR, opener: Opener | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 min_interval: float = MIN_INTERVAL_S,
                 max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
                 max_requests: int | None = None, log: Callable[[str], None] | None = None):
        self.cache_dir = Path(cache_dir)
        self.opener = opener or _urllib_opener
        self.clock, self.sleep = clock, sleep
        self.min_interval = min_interval
        self.max_consecutive_failures = max_consecutive_failures
        self.max_requests = max_requests
        self.log = log or (lambda s: None)
        self.requests = 0
        self.cache_hits = 0
        self.consecutive_failures = 0
        self.failed: list[dict] = []
        self.request_times: list[float] = []
        self._last: float | None = None

    def _path(self, kind: str, key: str) -> Path:
        return self.cache_dir / "raw" / kind / f"{key}.json"

    def _wait(self) -> None:
        if self._last is not None:
            gap = self.clock() - self._last
            if gap < self.min_interval:
                self.sleep(self.min_interval - gap)
        self._last = self.clock()

    def _request(self, url: str) -> tuple[int, bytes]:
        if self.max_requests is not None and self.requests >= self.max_requests:
            raise FetchStopped(f"request budget of {self.max_requests} reached")
        self._wait()
        self.requests += 1
        self.request_times.append(self._last)
        return self.opener(url, {"User-Agent": USER_AGENT, "Accept": "application/json"})

    def get(self, kind: str, key: str, path: str) -> dict | None:
        f = self._path(kind, key)
        if f.exists():
            self.cache_hits += 1
            return json.loads(f.read_text(encoding="utf-8"))["body"]
        url = BASE_URL + path
        status, body = self._request(url)
        if status != 200 and (status == 0 or status == 429 or status >= 500):
            self.sleep(RETRY_PAUSE_S)
            status, body = self._request(url)
        if status != 200:
            self.consecutive_failures += 1
            self.failed.append({"url": url, "status": status})
            self.log(f"non-200 ({status}) {url}")
            if self.consecutive_failures >= self.max_consecutive_failures:
                raise FetchStopped(f"{self.consecutive_failures} consecutive non-200 answers, last {status} {url}")
            return None
        self.consecutive_failures = 0
        payload = json.loads(body)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"url": url, "status": status,
                                   "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                   "body": payload}, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, f)
        return payload


# --- the endpoints ---------------------------------------------------------------------------

def season_clubs(f: Fetcher, season: int) -> list[dict] | None:
    d = f.get("teams_mlb", str(season), f"/api/v1/teams?sportId=1&season={season}")
    return None if d is None else list(d.get("teams") or [])


def season_affiliates(f: Fetcher, season: int, club_ids: Iterable[int]) -> list[dict] | None:
    ids = ",".join(str(i) for i in sorted(club_ids))
    d = f.get("affiliates", str(season), f"/api/v1/teams/affiliates?teamIds={ids}&season={season}")
    return None if d is None else list(d.get("teams") or [])


def season_schedule(f: Fetcher, sport_id: int, season: int) -> dict[int, list[str]] | None:
    """{team_id: sorted dates of played regular-season games} for one level and season."""
    d = f.get("schedule", f"{sport_id}_{season}",
              f"/api/v1/schedule?sportId={sport_id}&season={season}&gameType=R&fields={SCHEDULE_FIELDS}")
    if d is None:
        return None
    out: dict[int, set[str]] = defaultdict(set)
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            if (g.get("status") or {}).get("codedGameState") not in PLAYED_STATES:
                continue
            for side in ("away", "home"):
                tid = (((g.get("teams") or {}).get(side) or {}).get("team") or {}).get("id")
                if tid is not None:
                    out[int(tid)].add(day["date"])
    return {k: sorted(v) for k, v in out.items()}


def team_season_staff(f: Fetcher, team_id: int, season: int) -> list[dict] | None:
    d = f.get("coaches_season", f"{team_id}_{season}", f"/api/v1/teams/{team_id}/coaches?season={season}")
    return None if d is None else list(d.get("roster") or [])


def team_staff_on(f: Fetcher, team_id: int, day: str) -> list[dict] | None:
    d = f.get("coaches_date", f"{team_id}_{day}", f"/api/v1/teams/{team_id}/coaches?date={day}")
    return None if d is None else list(d.get("roster") or [])


# --- deciding where to bisect ------------------------------------------------------------------

def assignments(rows: Iterable[dict]) -> frozenset:
    """The (MLBAM person id, jobId) pairs of a staff list; duplicates collapse (the 1960 Yankees list
    carries one manager twice)."""
    out = set()
    for r in rows or []:
        pid = (r.get("person") or {}).get("id")
        if pid is not None:
            out.add((int(pid), str(r.get("jobId") or "")))
    return frozenset(out)


def bisection_targets(staff_by_team: dict[int, list[dict]]) -> dict[int, list[str]]:
    """For ONE organization-season ({team_id: season staff rows}): the teams whose list needs date
    bisection, each with its reasons. A job with two holders, a person with two jobs on one team,
    or a person on two teams of the organization."""
    reasons: dict[int, list[str]] = defaultdict(list)
    teams_of_person: dict[int, set[int]] = defaultdict(set)
    for tid, rows in staff_by_team.items():
        pairs = assignments(rows)
        holders: dict[str, set[int]] = defaultdict(set)
        jobs: dict[int, set[str]] = defaultdict(set)
        for pid, job in pairs:
            holders[job].add(pid)
            jobs[pid].add(job)
            teams_of_person[pid].add(tid)
        if any(len(v) > 1 for v in holders.values()):
            reasons[tid].append("job_two_holders")
        if any(len(v) > 1 for v in jobs.values()):
            reasons[tid].append("person_two_jobs")
    for pid, tids in teams_of_person.items():
        if len(tids) > 1:
            for tid in tids:
                if "person_two_teams" not in reasons[tid]:
                    reasons[tid].append("person_two_teams")
    return {k: v for k, v in reasons.items() if v}


def _days(first: str, last: str) -> list[str]:
    a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def _pairs_json(s: Iterable) -> list[list]:
    return [[p, j] for p, j in sorted(s)]


def resolve_team(f: Fetcher, team_id: int, season: int, game_dates: list[str],
                 season_rows: list[dict]) -> dict:
    """Date bisection for one team-season, over calendar days from its first to its last played
    game. Probes both ends; if the season list holds an assignment neither end shows, probes an
    interior grid (halves, quarters, eighths) until it appears; then bisects every interval whose
    ends differ down to adjacent days. A change is reported as (last day before, first day after)."""
    out = {"team_id": team_id, "season": season,
           "first_game": game_dates[0] if game_dates else None,
           "last_game": game_dates[-1] if game_dates else None,
           "resolution": "season", "probes": {}, "changes": [], "unexplained": [], "error": None}
    if not game_dates:
        out["error"] = "no played games"
        return out
    days = _days(game_dates[0], game_dates[-1])
    n = len(days)
    state: dict[int, frozenset] = {}

    class _Failed(Exception):
        pass

    def probe(i: int) -> frozenset:
        if i not in state:
            rows = team_staff_on(f, team_id, days[i])
            if rows is None:
                raise _Failed(days[i])
            state[i] = assignments(rows)
        return state[i]

    season_set = assignments(season_rows)
    try:
        probe(0)
        probe(n - 1)
        for k in (2, 4, 8):
            if season_set <= frozenset().union(*state.values()):
                break
            for j in range(1, k):
                probe(j * (n - 1) // k)

        changes = []

        def bis(lo: int, hi: int) -> None:
            if state[lo] == state[hi]:
                return
            if hi - lo == 1:
                changes.append((lo, hi))
                return
            mid = (lo + hi) // 2
            probe(mid)
            bis(lo, mid)
            bis(mid, hi)

        anchors = sorted(state)
        for a, b in zip(anchors, anchors[1:]):
            bis(a, b)
    except _Failed as e:
        out["error"] = f"date probe failed on {e.args[0]}"
        out["probes"] = {days[i]: _pairs_json(s) for i, s in sorted(state.items())}
        return out
    seen = frozenset().union(*state.values())
    out["resolution"] = "day"
    out["probes"] = {days[i]: _pairs_json(s) for i, s in sorted(state.items())}
    out["changes"] = [{"last_day_before": days[lo], "first_day_after": days[hi],
                       "ended": _pairs_json(state[lo] - state[hi]),
                       "started": _pairs_json(state[hi] - state[lo])}
                      for lo, hi in sorted(changes)]
    out["unexplained"] = _pairs_json(season_set - seen)
    return out


# --- one season, and the run ---------------------------------------------------------------------

def _org_of(team: dict) -> int:
    sport = (team.get("sport") or {}).get("id")
    if sport == 1:
        return int(team["id"])
    return int(team.get("parentOrgId") or team["id"])


def fetch_season(f: Fetcher, season: int, log: Callable[[str], None] = lambda s: None) -> dict:
    """Fetch one season into the cache and return its index (ids, dates, bisection results)."""
    clubs = season_clubs(f, season)
    if clubs is None:
        return {"season": season, "error": "MLB club list failed"}
    club_ids = [int(t["id"]) for t in clubs]
    teams = season_affiliates(f, season, club_ids)
    if teams is None:
        return {"season": season, "error": "affiliates list failed"}
    by_id: dict[int, dict] = {}
    for t in list(clubs) + list(teams):
        by_id.setdefault(int(t["id"]), t)
    sports = sorted({(t.get("sport") or {}).get("id") for t in by_id.values()} - {None})
    games: dict[int, list[str]] = {}
    for sp in sports:
        sched = season_schedule(f, int(sp), season)
        for tid, dates in (sched or {}).items():
            games[tid] = dates
    staff: dict[int, list[dict] | None] = {}
    for tid in sorted(by_id):
        staff[tid] = team_season_staff(f, tid, season)
    by_org: dict[int, dict[int, list[dict]]] = defaultdict(dict)
    for tid, t in by_id.items():
        if staff.get(tid):
            by_org[_org_of(t)][tid] = staff[tid]
    targets: dict[int, list[str]] = {}
    for org, group in by_org.items():
        targets.update(bisection_targets(group))
    resolved = []
    for tid in sorted(targets):
        r = resolve_team(f, tid, season, games.get(tid, []), staff[tid] or [])
        r["reasons"] = targets[tid]
        resolved.append(r)
    log(f"season {season}: {len(by_id)} teams, {sum(1 for v in staff.values() if v)} with staff, "
        f"{len(targets)} bisected, {f.requests} requests so far")
    return {
        "season": season,
        "teams": [{"team_id": tid, "name": t.get("name"), "sport_id": (t.get("sport") or {}).get("id"),
                   "org_id": _org_of(t), "first_game": (games.get(tid) or [None])[0],
                   "last_game": (games.get(tid) or [None])[-1],
                   "staff_rows": None if staff.get(tid) is None else len(staff[tid])}
                  for tid, t in sorted(by_id.items())],
        "missing_staff_lists": [tid for tid, v in sorted(staff.items()) if v is None],
        "bisections": resolved,
    }


def run_fetch(seasons: Iterable[int], f: Fetcher, cache_dir: Path = CACHE_DIR,
              log: Callable[[str], None] = print) -> dict:
    cache_dir = Path(cache_dir)
    (cache_dir / "index").mkdir(parents=True, exist_ok=True)
    manifest = {"source": "statsapi_coaches", "user_agent": USER_AGENT,
                "min_interval_s": round(f.min_interval, 4),
                "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "seasons": [], "status": "running"}
    try:
        for y in seasons:
            idx = fetch_season(f, y, log)
            (cache_dir / "index" / f"season_{y}.json").write_text(
                json.dumps(idx, separators=(",", ":")), encoding="utf-8")
            manifest["seasons"].append({"season": y, "error": idx.get("error"),
                                        "teams": len(idx.get("teams") or []),
                                        "bisected": len(idx.get("bisections") or []),
                                        "missing_staff_lists": len(idx.get("missing_staff_lists") or [])})
        manifest["status"] = "complete"
    except FetchStopped as e:
        manifest["status"] = f"stopped: {e}"
        log(manifest["status"])
    manifest.update({"finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                     "requests": f.requests, "cache_hits": f.cache_hits, "failed": f.failed})
    if len(f.request_times) > 1:
        gaps = [b - a for a, b in zip(f.request_times, f.request_times[1:])]
        manifest["min_gap_s"] = round(min(gaps), 4)
    (cache_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def _parse_seasons(text: str) -> list[int]:
    if "-" in text:
        a, b = text.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in text.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fetch", action="store_true", help="fetch the staff history into .cache/staff/")
    ap.add_argument("--seasons", default=f"{FIRST_SEASON}-{LAST_SEASON}")
    ap.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    a = ap.parse_args(argv)
    if not a.fetch:
        ap.print_help()
        return 2
    f = Fetcher(max_requests=a.max_requests, log=lambda s: print(s, flush=True))
    m = run_fetch(_parse_seasons(a.seasons), f, log=lambda s: print(s, flush=True))
    print(json.dumps({k: m[k] for k in ("status", "requests", "cache_hits")}), flush=True)
    return 0 if m["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
