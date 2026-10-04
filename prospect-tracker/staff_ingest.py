# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Staff history ingest from the MLB StatsAPI coaches endpoint (Staff Gems stages 0 and 1: the fetch half and the parse half).

Design: docs/staff-gems/DESIGN.md (section 7, stages 0 and 1). Gate: docs/staff-gems/STAFF_GEMS_GATE.md,
registered before the fetch ran. Source registry entry: statsapi_coaches (legal_risk ambiguous).

STAGE 0, --fetch. WHAT IT FETCHES, raw, into .cache/staff/ only (gitignored; never data/):
  for every season 2008 to 2026
    teams?sportId=1&season=Y                    the MLB clubs
    teams/affiliates?teamIds=<all clubs>&season=Y   every affiliate, complex, DSL and pseudo-team
    schedule?sportId=S&season=Y&gameType=R      one call per level, for each team's first and last game
    teams/{id}/coaches?season=Y                 every holder of every job in the season
  and, ONLY where a team-season's list shows a job with two holders, a person with two jobs, or a
  person on two teams of one organization, date bisection with teams/{id}/coaches?date=D between
  the team's first and last game, to the day. The fetch reads no grade, no player, no outcome and
  no database.

STAGE 1, --parse (hand-run; not wired into run_monthly until stage 3). It first takes the house
database backup (<db>.bak-staff-<date>, sqlite3 backup API, integrity-checked; no backup, no
write), then parses the cache into the stage 1 tables through storage.replace_staff_tables:
persons (one per MLBAM id, staff_identity.py), spells (person x team x season x jobId, to the day
where the fetch bisected, else the season), units (team-seasons, org offseasons, the 2020 org
unit), the role map's review queue (config/staff_roles.yaml; no role is ever guessed), and player
location spells (day resolution from the transactions cache, season resolution from career rows
weighted by games). It reads no grade and no outcome, joins no development or outcome number to
any person, and writes nothing under data/.

Request discipline: at most 3 requests a second, a descriptive User-Agent, one retry on a
transient failure, and the run STOPS after 3 consecutive non-200 answers. Every response is cached
on first success, so a stopped run resumes where it left off. MLBAM's notice permits only
"individual, non-commercial, non-bulk use"; this one-time fetch is bulk use, which is why the
registry rates the source ambiguous (owner answer SG-Q2 chose it with that rating).

Run: python staff_ingest.py --fetch [--seasons 2008-2026] [--max-requests N]
     python staff_ingest.py --parse
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


# --- stage 1: the parse half ---------------------------------------------------------------------
#
# Reads .cache/staff/ (raw responses and the per-season indexes the fetch wrote) and the database's
# own player_transactions and career_stats caches, and writes the stage 1 tables through
# storage.replace_staff_tables. Pure builders first (tested on fixtures), the database write last.

ROLE_MAP_PATH = ROOT / "config" / "staff_roles.yaml"
CREDITED_ROLES = ("manager", "hitting", "pitching", "defense")
CONTEXT_ROLES = ("first_base", "third_base")
ROLE_VALUES = CREDITED_ROLES + CONTEXT_ROLES + ("excluded", "review")
MILB_SPORTS = (11, 12, 13, 14, 15, 16, 5442)
SPORT_LEVEL = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A", 16: "CPX", 5442: "CPX"}
NO_MILB_SEASONS = (2020,)
LOCATION_KINDS = ("mlb", "affiliate")
EXIT_TYPE_CODES = frozenset({"REL", "RET", "DFA"})


def norm_title(title: str | None) -> str:
    """A title as the role map keys it: whitespace collapsed, case folded."""
    return " ".join(str(title or "").split()).casefold()


class RoleMap:
    """config/staff_roles.yaml: pairs, then job codes, then titles for by_title codes, else the
    review queue. An unmapped job code or title is NEVER given a guessed role."""

    def __init__(self, doc: dict):
        self.jobs: dict[str, str] = {str(k).strip().upper(): str(v) for k, v in (doc.get("jobs") or {}).items()}
        self.titles: dict[str, str] = {norm_title(k): str(v) for k, v in (doc.get("titles") or {}).items()}
        self.pairs: dict[tuple[str, str], str] = {
            (str(p["job"]).strip().upper(), norm_title(p["title"])): str(p["role"]) for p in (doc.get("pairs") or [])}
        bad = sorted({v for v in self.jobs.values() if v not in ROLE_VALUES + ("by_title",)}
                     | {v for v in self.titles.values() if v not in ROLE_VALUES}
                     | {v for v in self.pairs.values() if v not in ROLE_VALUES})
        if bad:
            raise ValueError(f"role map names unknown roles: {bad}")
        if set((doc.get("roles") or {})) != set(CREDITED_ROLES + CONTEXT_ROLES):
            raise ValueError("role map 'roles' must list exactly the credited and context roles")

    @classmethod
    def load(cls, path: Path = ROLE_MAP_PATH) -> "RoleMap":
        import yaml
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})

    def classify(self, job_id: str | None, title: str | None) -> tuple[str, str]:
        """(role, rule): rule is pair, job, title, unmapped_job or unmapped_title."""
        job = str(job_id or "").strip().upper()
        t = norm_title(title)
        if (job, t) in self.pairs:
            return self.pairs[(job, t)], "pair"
        jr = self.jobs.get(job)
        if jr is None:
            return "review", "unmapped_job"
        if jr != "by_title":
            return jr, "job"
        tr = self.titles.get(t)
        if tr is None:
            return "review", "unmapped_title"
        return tr, "title"


def job_title_census(cache_dir: Path = CACHE_DIR) -> list[list]:
    """[[jobId, title, rows]] over every season staff list in the cache: job codes and titles
    only, no person. The committed copy (test_fixtures/staff/census/job_title_census.json) is what the
    role-map totality test checks."""
    n: dict[tuple[str, str], int] = defaultdict(int)
    for f in sorted((Path(cache_dir) / "raw" / "coaches_season").glob("*.json")):
        for r in (json.loads(f.read_text(encoding="utf-8")).get("body") or {}).get("roster") or []:
            n[(str(r.get("jobId") or "").strip().upper(), str(r.get("title") or "").strip())] += 1
    return [[j, t, c] for (j, t), c in sorted(n.items())]


def _read_raw(cache_dir: Path, kind: str, key: str) -> dict | None:
    f = Path(cache_dir) / "raw" / kind / f"{key}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _cached_seasons(cache_dir: Path) -> list[int]:
    out = []
    for f in sorted((Path(cache_dir) / "index").glob("season_*.json")):
        try:
            out.append(int(f.stem.split("_", 1)[1]))
        except ValueError:
            continue
    return out


def _unit_level(sport_id, league: str | None, name: str | None) -> str | None:
    level = SPORT_LEVEL.get(sport_id)
    if level == "CPX":
        low = (league or "").lower()
        nm = (name or "").strip().upper()
        if "dominican" in low or "venezuelan" in low or nm.startswith(("DSL ", "VSL ")):
            return "DSL"
    return level


def _day(d: str, plus: int = 0) -> str:
    return (dt.date.fromisoformat(d) + dt.timedelta(days=plus)).isoformat()


def _org_code(org_id: int | None) -> str | None:
    if org_id is None:
        return None
    from trades import canonical_org_from_id   # lazy: the fetch half needs none of this
    return canonical_org_from_id(int(org_id))


def build_units(cache_dir: Path, seasons: Iterable[int]) -> list[dict]:
    """Team units (MLB club, affiliate or pseudo-team, per season) and organization units (one
    offseason per org per winter, last affiliate game to the next first game; 2020, with no minor
    league season, as one org-level unit for the calendar year)."""
    units: list[dict] = []
    window: dict[int, dict[int, tuple[str, str]]] = defaultdict(dict)
    seasons = sorted(seasons)
    for y in seasons:
        idx = json.loads((Path(cache_dir) / "index" / f"season_{y}.json").read_text(encoding="utf-8"))
        league: dict[int, str | None] = {}
        for kind in ("teams_mlb", "affiliates"):
            raw = _read_raw(cache_dir, kind, str(y))
            for t in ((raw or {}).get("body") or {}).get("teams") or []:
                league.setdefault(int(t["id"]), (t.get("league") or {}).get("name"))
        for t in idx.get("teams") or []:
            tid, sport = int(t["team_id"]), t.get("sport_id")
            kind = "mlb" if sport == 1 else ("affiliate" if sport in MILB_SPORTS else "pseudo")
            org_id = int(t["org_id"])
            units.append({"unit_id": f"T{tid}_{y}", "kind": kind, "season": y, "team_id": tid,
                          "team_name": t.get("name"), "org_id": org_id, "org_code": _org_code(org_id),
                          "sport_id": sport, "level": _unit_level(sport, league.get(tid), t.get("name")),
                          "league": league.get(tid), "start_date": t.get("first_game"),
                          "end_date": t.get("last_game")})
            if kind == "affiliate" and t.get("first_game"):
                lo, hi = window[org_id].get(y, (t["first_game"], t["last_game"]))
                window[org_id][y] = (min(lo, t["first_game"]), max(hi, t["last_game"]))
    orgs = sorted({u["org_id"] for u in units if u["kind"] == "mlb"})
    for org in orgs:
        for y in seasons:
            base = {"season": y, "team_id": None, "team_name": None, "org_id": org,
                    "org_code": _org_code(org), "sport_id": None, "level": None, "league": None}
            if y in NO_MILB_SEASONS:
                units.append({**base, "unit_id": f"ORG{y}_{org}", "kind": "org_2020",
                              "start_date": f"{y}-01-01", "end_date": f"{y}-12-31"})
                continue
            w = window[org].get(y)
            if w is None:
                continue
            if (y - 1) in NO_MILB_SEASONS and (y - 1) in seasons:
                units.append({**base, "season": y - 1, "unit_id": f"OFF_{org}_{y - 1}", "kind": "offseason",
                              "start_date": f"{y}-01-01", "end_date": _day(w[0], -1)})
            nxt = window[org].get(y + 1)
            if (y + 1) in NO_MILB_SEASONS:
                end = f"{y}-12-31"
            elif nxt is not None:
                end = _day(nxt[0], -1)
            else:
                end = None       # the next season is not in the cache yet: an open winter
            units.append({**base, "unit_id": f"OFF_{org}_{y}", "kind": "offseason",
                          "start_date": _day(w[1], 1), "end_date": end})
    return units


def _segments(b: dict) -> list[tuple[str, str, frozenset]] | None:
    """The constant-staff segments of one day-resolved team-season, from its probes and changes;
    None if two probes inside one segment disagree (then the team falls back to season spells)."""
    probes = {d: frozenset((int(p), str(j)) for p, j in pairs) for d, pairs in (b.get("probes") or {}).items()}
    changes = b.get("changes") or []
    starts = [b["first_game"]] + [c["first_day_after"] for c in changes]
    ends = [c["last_day_before"] for c in changes] + [b["last_game"]]
    out = []
    for s, e in zip(starts, ends):
        states = {v for d, v in probes.items() if s <= d <= e}
        if len(states) != 1:
            return None
        out.append((s, e, states.pop()))
    return out


def build_spells(cache_dir: Path, seasons: Iterable[int], units: list[dict],
                 role_map: RoleMap) -> tuple[list[dict], list[dict], dict]:
    """(spells, staff rows with season, counts). One spell per person, team, season and job code,
    and per held interval when the team-season was date-bisected. Every spell carries the MLBAM id;
    a staff row without one is counted and dropped."""
    from staff_identity import person_id_of
    team_unit = {(u["team_id"], u["season"]): u for u in units if u.get("team_id") is not None}
    spells: list[dict] = []
    rows_out: list[dict] = []
    counts = defaultdict(int)
    for y in sorted(seasons):
        idx = json.loads((Path(cache_dir) / "index" / f"season_{y}.json").read_text(encoding="utf-8"))
        bis = {int(b["team_id"]): b for b in idx.get("bisections") or []}
        for t in idx.get("teams") or []:
            tid = int(t["team_id"])
            raw = _read_raw(cache_dir, "coaches_season", f"{tid}_{y}")
            if raw is None:
                counts["missing_staff_lists"] += 1
                continue
            roster = (raw.get("body") or {}).get("roster") or []
            if not roster:
                continue
            counts["team_seasons_with_staff"] += 1
            unit = team_unit[(tid, y)]
            assign: dict[tuple[int, str], dict] = {}
            for r in roster:
                counts["staff_rows"] += 1
                pid = person_id_of(r)
                if pid is None:
                    counts["rows_without_mlbam_id"] += 1
                    continue
                rows_out.append({**r, "season": y, "team_id": tid})
                key = (pid, str(r.get("jobId") or "").strip().upper())
                if key in assign:
                    counts["duplicate_rows"] += 1
                    if not str(assign[key].get("title") or "").strip() and str(r.get("title") or "").strip():
                        assign[key] = r
                    continue
                assign[key] = r
            b = bis.get(tid)
            segs = None
            note = "not_bisected"
            if b is not None:
                if b.get("error") or b.get("resolution") != "day":
                    note = "no_games" if not t.get("first_game") else "bisect_error"
                else:
                    segs = _segments(b)
                    if segs is None:
                        note = "bisect_inconsistent"
            elif not t.get("first_game"):
                note = "no_games"
            for (pid, job), r in sorted(assign.items()):
                role, rule = role_map.classify(job, r.get("title"))
                base = {"person_id": pid, "team_id": tid, "season": y, "unit_id": unit["unit_id"],
                        "org_id": unit["org_id"], "org_code": unit["org_code"], "level": unit["level"],
                        "job_id": job, "job": r.get("job"), "title": str(r.get("title") or "").strip(),
                        "role": role, "role_rule": rule, "fetched_at": raw.get("fetched_at")}
                held: list[list[str]] = []
                for s, e, state in segs or []:
                    if (pid, job) in state:
                        if held and held[-1][1] == _day(s, -1):
                            held[-1][1] = e
                        else:
                            held.append([s, e])
                if segs is not None and held:
                    for s, e in held:
                        spells.append({**base, "start_date": s, "end_date": e, "resolution": "day",
                                       "resolution_note": None})
                    counts["spells_day"] += len(held)
                else:
                    spells.append({**base, "start_date": t.get("first_game"), "end_date": t.get("last_game"),
                                   "resolution": "season",
                                   "resolution_note": "unexplained" if segs is not None else note})
                    counts["spells_season"] += 1
    return spells, rows_out, dict(counts)


def role_review_queue(spells: list[dict]) -> list[dict]:
    """The review queue: one row per (job code, title) whose role is review, with how many
    assignments, persons and seasons it covers."""
    agg: dict[tuple[str, str], dict] = {}
    seen: set[tuple] = set()
    for s in spells:
        if s["role"] != "review":
            continue
        k = (s["job_id"], s["title"])
        a = agg.setdefault(k, {"job_id": k[0], "title": k[1],
                                "reason": "explicit_review" if s["role_rule"] in ("pair", "title") else s["role_rule"],
                                "n_rows": 0, "_persons": set(), "first_season": s["season"],
                                "last_season": s["season"]})
        ak = (s["person_id"], s["team_id"], s["season"], s["job_id"])
        if ak not in seen:
            seen.add(ak)
            a["n_rows"] += 1
        a["_persons"].add(s["person_id"])
        a["first_season"] = min(a["first_season"], s["season"])
        a["last_season"] = max(a["last_season"], s["season"])
    out = []
    for k in sorted(agg):
        a = agg[k]
        a["n_persons"] = len(a.pop("_persons"))
        out.append(a)
    return out


def persons_from(rows: list[dict], spells: list[dict]) -> tuple[list[dict], list[dict]]:
    from staff_identity import build_persons
    by_id, rejects = build_persons(rows)
    n = defaultdict(int)
    for s in spells:
        n[s["person_id"]] += 1
    out = []
    for pid in sorted(by_id):
        p = by_id[pid]
        out.append({**p, "n_spells": n.get(pid, 0), "source": "statsapi_coaches"})
    return out, rejects


# --- player location spells --------------------------------------------------------------------

def location_maps(units: list[dict]) -> dict[int, dict[int, dict]]:
    """{season: {team_id: unit}} for MLB clubs and affiliates (pseudo-teams hold no location)."""
    out: dict[int, dict[int, dict]] = defaultdict(dict)
    for u in units:
        if u["kind"] in LOCATION_KINDS:
            out[u["season"]][u["team_id"]] = u
    return out


def _accept_move(tx: dict, unit: dict) -> bool:
    """The same filters derive_level_changes applies to a level move (spring training, rehab,
    exhibition and placeholder rows never move a player; a move to an MLB club needs a real
    promotion verb)."""
    import stats as st
    desc = (tx.get("description") or "").lower()
    if any(p in desc for p in st._NON_LEVEL_CHANGE_PHRASES) or st._is_exhibition_team(desc):
        return False
    names = (unit.get("team_name"), tx.get("to_team_name"), tx.get("from_team_name"))
    if any(st._is_placeholder_team(n) or st._is_exhibition_team(n) for n in names):
        return False
    if unit["level"] == "MLB" and not any(v in desc for v in st._REAL_MLB_PROMOTION_VERBS):
        return False
    return True


def _year_map(maps: dict[int, dict[int, dict]], year: int) -> dict[int, dict]:
    if year in maps:
        return maps[year]
    ys = sorted(maps)
    if not ys:
        return {}
    return maps[ys[0]] if year < ys[0] else maps[ys[-1]]


def _il_marks(txs: list[dict], maps: dict[int, dict[int, dict]], as_of: str) -> list[tuple[str, str, str, int | None]]:
    """Sorted, disjoint (start, end, status, rehab_team) marks: IL days, with the days after a
    rehab assignment inside the same stint marked rehab at the rehab club."""
    import stats as st
    marks = []
    rehabs = []
    for tx in txs:
        if st._REHAB_RE.search(tx.get("description") or "") and tx.get("date"):
            rehabs.append((str(tx["date"])[:10], tx.get("to_team_id")))
    for stint in st._walk_il_stints(txs):
        s = str(stint.get("since") or "")[:10]
        if not s:
            continue
        e = _day(str(stint["until"])[:10], -1) if stint.get("until") else as_of
        if e < s:
            continue
        inside = sorted((d, t) for d, t in rehabs if s <= d <= e)
        cur = s
        for i, (d, team) in enumerate(inside):
            if d > cur:
                marks.append((cur, _day(d, -1), "il", None))
            r_end = _day(inside[i + 1][0], -1) if i + 1 < len(inside) else e
            unit = _year_map(maps, int(d[:4])).get(int(team)) if team else None
            marks.append((d, r_end, "rehab", int(team) if unit else None))
            cur = _day(r_end, 1)
        if cur <= e:
            marks.append((cur, e, "il", None))
    marks.sort()
    out = []
    for m in marks:            # a later stint that overlaps an earlier one is clipped, never doubled
        if out and m[0] <= out[-1][1]:
            if m[1] <= out[-1][1]:
                continue
            m = (_day(out[-1][1], 1), m[1], m[2], m[3])
        out.append(m)
    return out


def day_locations(player_key: str, txs: list[dict], maps: dict[int, dict[int, dict]],
                  as_of: str) -> tuple[list[dict], dict]:
    """Day-resolution location spells from one player's transactions, cut at each Dec 31 and
    resolved against that season's team map. Status active, il or rehab. Never overlapping."""
    import stats as st
    counts = defaultdict(int)
    events = sorted((tx for tx in txs or [] if tx.get("date")),
                    key=lambda tx: (str(tx["date"])[:10], int(tx.get("id") or 0)))
    raw: list[tuple[int, str, str]] = []
    cur: int | None = None
    start = ""

    def close(day: str) -> None:
        nonlocal cur
        if cur is not None and day > start:
            raw.append((cur, start, _day(day, -1)))
        cur = None

    for tx in events:
        d = str(tx["date"])[:10]
        if d > as_of:
            break
        code = str(tx.get("type_code") or "")
        if code in EXIT_TYPE_CODES:
            close(d)
            continue
        to_id = tx.get("to_team_id")
        ymap = _year_map(maps, int(d[:4]))
        unit = ymap.get(int(to_id)) if to_id else None
        if unit is not None and code in st._LEVEL_AFFECTING_TYPE_CODES and _accept_move(tx, unit):
            if int(to_id) != cur:
                close(d)
                cur, start = int(to_id), d
            continue
        if cur is not None and to_id:
            cur_unit = ymap.get(cur)
            new_org = unit["org_id"] if unit is not None else None
            if cur_unit is not None and new_org is not None and new_org != cur_unit["org_id"]:
                close(d)          # a new organization with no placement: location unknown until one
                counts["org_change_gaps"] += 1
    close(_day(as_of, 1))
    marks = _il_marks(events, maps, as_of)
    out: list[dict] = []
    for team, s, e in raw:
        for y in range(max(int(s[:4]), FIRST_SEASON), min(int(e[:4]), LAST_SEASON) + 1):
            ps, pe = max(s, f"{y}-01-01"), min(e, f"{y}-12-31")
            if ps > pe:
                continue
            unit = maps.get(y, {}).get(team)
            if unit is None:
                counts["pieces_without_team_in_season"] += 1
                continue
            cursor = ps
            for ms, me, status, rteam in marks:
                if me < cursor or ms > pe:
                    continue
                if ms > cursor:
                    out.append(_loc(player_key, unit, cursor, _day(ms, -1), "active"))
                seg_s, seg_e = max(ms, cursor), min(me, pe)
                ru = maps.get(y, {}).get(rteam) if (status == "rehab" and rteam) else None
                out.append(_loc(player_key, ru or unit, seg_s, seg_e, status if (status != "rehab" or ru) else "il"))
                cursor = _day(seg_e, 1)
                if cursor > pe:
                    break
            if cursor <= pe:
                out.append(_loc(player_key, unit, cursor, pe, "active"))
    return out, dict(counts)


def _loc(player_key: str, unit: dict, s: str, e: str, status: str) -> dict:
    return {"player_key": player_key, "season": int(s[:4]), "team_id": unit["team_id"],
            "unit_id": unit["unit_id"], "org_id": unit["org_id"], "org_code": unit["org_code"],
            "level": unit["level"], "start_date": s, "end_date": e, "status": status,
            "resolution": "day", "weight": 1.0, "n_candidates": 1, "source": "transactions"}


def season_locations(player_key: str, career: list[dict], maps: dict[int, dict[int, dict]],
                     skip_seasons: set[int]) -> list[dict]:
    """Season-resolution location rows from career rows (season, level, org, games; per-org stints
    when a level holds two), weighted by games, for every season 2008 to 2026 the player has no
    day-resolution spell in. The team is named only when the org has exactly one team at that
    level that season; otherwise team_id is NULL and n_candidates says how many it could be."""
    by_season: dict[int, list[tuple[str, str, int]]] = defaultdict(list)
    for r in career or []:
        try:
            y = int(r.get("season"))
        except (TypeError, ValueError):
            continue
        if y < FIRST_SEASON or y > LAST_SEASON or y in skip_seasons:
            continue
        for part in (r.get("stints") or [r]):
            level = part.get("level") or r.get("level")
            org = part.get("org") or r.get("org")
            if not level or not org:
                continue
            by_season[y].append((level, org, int(part.get("games") or 0)))
    out = []
    for y, parts in sorted(by_season.items()):
        total = sum(g for _, _, g in parts)
        for level, org, games in parts:
            cands = [u for u in maps.get(y, {}).values() if u["level"] == level and u["org_code"] == org]
            u = cands[0] if len(cands) == 1 else None
            org_ids = {c["org_id"] for c in cands} or {m["org_id"] for m in maps.get(y, {}).values()
                                                         if m["kind"] == "mlb" and m["org_code"] == org}
            out.append({"player_key": player_key, "season": y,
                        "team_id": u["team_id"] if u else None, "unit_id": u["unit_id"] if u else None,
                        "org_id": next(iter(org_ids)) if len(org_ids) == 1 else None, "org_code": org,
                        "level": level, "start_date": u["start_date"] if u else None,
                        "end_date": u["end_date"] if u else None, "status": "active",
                        "resolution": "season",
                        "weight": round(games / total, 6) if total else round(1 / len(parts), 6),
                        "n_candidates": len(cands), "source": "career"})
    return out


def build_locations(transactions: dict[str, list[dict]], tx_fetched: dict[str, str],
                    career: dict[str, list[dict]], units: list[dict],
                    today: str | None = None) -> tuple[list[dict], dict]:
    maps = location_maps(units)
    today = today or dt.date.today().isoformat()
    out: list[dict] = []
    counts = defaultdict(int)
    day_players, season_players = set(), set()
    for key in sorted(set(transactions) | set(career)):
        rows: list[dict] = []
        if transactions.get(key):
            as_of = str(tx_fetched.get(key) or today)[:10]
            rows, c = day_locations(key, transactions[key], maps, min(as_of, today))
            for k, v in c.items():
                counts[k] += v
        day_seasons = {r["season"] for r in rows}
        srows = season_locations(key, career.get(key) or [], maps, day_seasons)
        if rows:
            day_players.add(key)
        if srows:
            season_players.add(key)
        out.extend(rows)
        out.extend(srows)
    counts.update({"location_rows_day": sum(1 for r in out if r["resolution"] == "day"),
                   "location_rows_season": sum(1 for r in out if r["resolution"] == "season"),
                   "players_with_day_rows": len(day_players),
                   "players_with_season_rows": len(season_players),
                   "players_season_rows_only": len(season_players - day_players),
                   "players_located": len(day_players | season_players),
                   "season_rows_team_unresolved": sum(1 for r in out if r["resolution"] == "season"
                                                      and r["team_id"] is None)})
    return out, dict(counts)


# --- the run -------------------------------------------------------------------------------------

def backup_database(db_path: Path, tag: str = "staff") -> Path:
    """The house backup: a WAL-safe copy through the sqlite3 backup API, named
    <db>.bak-<tag>-<date> beside the database; never overwrites an existing backup."""
    import sqlite3
    db_path = Path(db_path)
    stamp = dt.date.today().isoformat()
    dst = db_path.with_name(f"{db_path.name}.bak-{tag}-{stamp}")
    if dst.exists():
        dst = db_path.with_name(f"{db_path.name}.bak-{tag}-{dt.datetime.now().strftime('%Y-%m-%d-%H%M%S')}")
    src = sqlite3.connect(str(db_path))
    try:
        out = sqlite3.connect(str(dst))
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    chk = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
    try:
        ok = chk.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        chk.close()
    if ok != "ok":
        raise RuntimeError(f"backup {dst} failed its integrity check: {ok}")
    return dst


def parse_cache(cache_dir: Path = CACHE_DIR, role_map: RoleMap | None = None,
                seasons: Iterable[int] | None = None) -> dict:
    """Everything the stage 1 staff tables hold, built from the cache alone (no database)."""
    role_map = role_map or RoleMap.load()
    seasons = sorted(seasons) if seasons is not None else _cached_seasons(cache_dir)
    units = build_units(cache_dir, seasons)
    spells, rows, counts = build_spells(cache_dir, seasons, units, role_map)
    persons, rejects = persons_from(rows, spells)
    review = role_review_queue(spells)
    from staff_identity import shared_names
    by_id = {p["person_id"]: p for p in persons}
    roles = defaultdict(int)
    rules = defaultdict(int)
    for s in spells:
        roles[s["role"]] += 1
        rules[s["role_rule"]] += 1
    counts.update({"seasons": len(seasons), "units": len(units),
                   "units_by_kind": dict(sorted(_count(u["kind"] for u in units).items())),
                   "persons": len(persons), "spells": len(spells), "rows_rejected": len(rejects),
                   "spells_by_role": dict(sorted(roles.items())),
                   "spells_by_rule": dict(sorted(rules.items())),
                   "role_review_keys": len(review),
                   "names_shared_by_two_or_more_persons": len(shared_names(by_id))})
    return {"units": units, "spells": spells, "persons": persons, "role_review": review,
            "counts": counts}


def _count(items: Iterable) -> dict:
    out: dict = defaultdict(int)
    for i in items:
        out[i] += 1
    return out


def run_parse(cache_dir: Path = CACHE_DIR, role_map_path: Path = ROLE_MAP_PATH, backup: bool = True,
              log: Callable[[str], None] = print) -> dict:
    """Back up the database, parse the cache, build location spells, replace the stage 1 tables."""
    import storage
    if backup:
        dst = backup_database(storage.DB_PATH)
        log(f"backup: {dst}")
    parsed = parse_cache(cache_dir, RoleMap.load(role_map_path))
    locs, lcounts = build_locations(storage.load_player_transactions(),
                                    storage.load_player_transactions_meta(),
                                    storage.load_career_stats(), parsed["units"])
    counts = {**parsed["counts"], **lcounts}
    run_id = storage.replace_staff_tables(
        persons=parsed["persons"], units=parsed["units"], spells=parsed["spells"],
        role_review=parsed["role_review"], identity_review=[], locations=locs,
        cache_dir=str(Path(cache_dir)), role_map=str(Path(role_map_path).name), counts=counts)
    counts["run_id"] = run_id
    log(json.dumps(counts, sort_keys=True))
    return counts


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
    ap.add_argument("--parse", action="store_true",
                    help="stage 1: back up the database, then parse .cache/staff/ into the staff tables")
    a = ap.parse_args(argv)
    if a.parse and not a.fetch:
        run_parse(log=lambda s: print(s, flush=True))
        return 0
    if not a.fetch:
        ap.print_help()
        return 2
    f = Fetcher(max_requests=a.max_requests, log=lambda s: print(s, flush=True))
    m = run_fetch(_parse_seasons(a.seasons), f, log=lambda s: print(s, flush=True))
    print(json.dumps({k: m[k] for k in ("status", "requests", "cache_hits")}), flush=True)
    return 0 if m["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
