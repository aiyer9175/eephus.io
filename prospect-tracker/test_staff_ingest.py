# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Staff Gems stage 0: the gate registration is present, and the fetch half of staff_ingest.py
(date bisection, rate limit, stop rule, cache) behaves on saved fixtures. No network: every test
runs on test_fixtures/staff/*.json (live StatsAPI responses of 2026-10-03, pseudonymized) through a
fake opener, and urllib is blocked."""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import staff_ingest as si  # noqa: E402

GATE = ROOT / "docs" / "staff-gems" / "STAFF_GEMS_GATE.md"
DESIGN = ROOT / "docs" / "staff-gems" / "DESIGN.md"
FIX = ROOT / "test_fixtures" / "staff"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*a, **k):
        raise AssertionError("network access in a test")
    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeAPI:
    """Serves the StatsAPI paths staff_ingest asks for from fixture teams; anything else is a 404."""

    def __init__(self, teams: list[dict], clubs: list[dict] | None = None, copyright: str = ""):
        self.teams = {t["team_id"]: t for t in teams}
        self.clubs = clubs or []
        self.copyright = copyright
        self.urls: list[str] = []
        self.headers: list[dict] = []

    def _roster_on(self, t: dict, day: str) -> list[dict]:
        segs = t["segments"]
        if day < segs[0]["from"]:
            return segs[0]["roster"]
        for s in segs:
            if s["from"] <= day <= s["to"]:
                return s["roster"]
        return segs[-1]["roster"]

    def __call__(self, url: str, headers: dict) -> tuple[int, bytes]:
        self.urls.append(url)
        self.headers.append(headers)
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        body = None
        m = re.fullmatch(r"/api/v1/teams/(\d+)/coaches", u.path)
        if m and int(m.group(1)) in self.teams:
            t = self.teams[int(m.group(1))]
            if "season" in q and int(q["season"]) == t["season"]:
                body = {"copyright": self.copyright, "roster": t["season_roster"]}
            elif "date" in q:
                body = {"copyright": self.copyright, "roster": self._roster_on(t, q["date"])}
        elif u.path == "/api/v1/schedule":
            sport, season = int(q["sportId"]), int(q["season"])
            days: dict[str, list] = {}
            for t in self.teams.values():
                if t["sport_id"] == sport and t["season"] == season:
                    for d in t["game_dates"]:
                        days.setdefault(d, []).append(
                            {"gameType": "R", "status": {"codedGameState": "F"},
                             "teams": {"away": {"team": {"id": t["team_id"]}}, "home": {"team": {"id": 1}}}})
            body = {"dates": [{"date": d, "games": g} for d, g in sorted(days.items())]}
        elif u.path == "/api/v1/teams" and q.get("sportId") == "1":
            body = {"teams": self.clubs}
        elif u.path == "/api/v1/teams/affiliates":
            body = {"teams": [{"id": t["team_id"], "name": t["name"], "sport": {"id": t["sport_id"]},
                               "parentOrgId": t["org_id"]} for t in self.teams.values()]}
        if body is None:
            return 404, b""
        return 200, json.dumps(body).encode("utf-8")


def _fetcher(tmp_path: Path, api, **kw) -> si.Fetcher:
    return si.Fetcher(cache_dir=tmp_path / "staff", opener=api, sleep=lambda s: None, **kw)


def _t(fx: dict, team_id: int) -> dict:
    return next(t for t in fx["teams"] if t["team_id"] == team_id)


# --- the registration ------------------------------------------------------------------------------

def test_the_gate_is_registered_with_its_clauses():
    assert GATE.exists() and DESIGN.exists()
    g = re.sub(r"\s+", " ", GATE.read_text(encoding="utf-8"))
    for s in ("committed ALONE, before any staff spell has met a grade pair",
              "2,000 permutations, seed 20261003",
              "permute staff labels within (org, level, season) cells, holding each cell's exposure fixed",
              "Leg 2, the pre-tenure placebo",
              "Fewer than 30 movers: UNPOWERED",
              "The detection floor, by injection",
              "Holm-corrected at family alpha 0.05",
              "PASS for a role** = leg 1 clears its Holm threshold AND leg 2 is powered and does NOT clear",
              "At least 12 distinct players with 30 or more active days",
              "Benjamini-Hochberg at q = 0.10",
              "NEVER the per-snapshot eFV series",
              "ONLY IF the R-LV look record exists when the look runs",
              "2027-01-31 on the COMPLEMENT frame",
              "aggregate statistics only, NO person id",
              "style fields only: attempts, the share of steals of second and third, and the break-even faced",
              "at least 4 distinct persons with no person over half of the cell's exposure",
              "`config/staff_optout.json` or `.cache/staff/optout.json`, never under `data/`",
              "**A null is the likely result**",
              "25,802 on 5,375 players"):
        assert s in g, s
    assert chr(0x2014) not in g and chr(0x2013) not in g


# --- deciding where to bisect ------------------------------------------------------------------------

def _row(pid: int, job: str) -> dict:
    return {"person": {"id": pid}, "jobId": job}


def test_bisection_targets_follow_the_three_triggers():
    assert si.bisection_targets({1: [_row(1, "MNGR"), _row(2, "COAT")]}) == {}
    assert si.bisection_targets({1: [_row(1, "MNGR"), _row(2, "MNGR")]}) == {1: ["job_two_holders"]}
    assert si.bisection_targets({1: [_row(1, "COAB"), _row(1, "NTRM")]}) == {1: ["person_two_jobs"]}
    t = si.bisection_targets({1: [_row(1, "COAT")], 2: [_row(1, "COAT")], 3: [_row(9, "MNGR")]})
    assert t == {1: ["person_two_teams"], 2: ["person_two_teams"]}
    # duplicates collapse (the 1960 list carries one manager twice)
    assert si.bisection_targets({1: [_row(1, "MNGR"), _row(1, "MNGR")]}) == {}


# --- the saved fixtures --------------------------------------------------------------------------------

def test_wsh_2025_manager_change_resolves_to_the_day(tmp_path):
    fx = _fixture("wsh_2025.json")
    t = _t(fx, 120)
    assert si.bisection_targets({120: t["season_roster"]}) == {120: ["job_two_holders", "person_two_jobs"]}
    api = FakeAPI(fx["teams"], copyright=fx["copyright"])
    f = _fetcher(tmp_path, api)
    r = si.resolve_team(f, 120, 2025, t["game_dates"], t["season_roster"])
    assert r["resolution"] == "day" and r["error"] is None
    assert (r["first_game"], r["last_game"]) == ("2025-03-27", "2025-09-28")
    first = r["changes"][0]
    assert (first["last_day_before"], first["first_day_after"]) == ("2025-07-06", "2025-07-07")
    assert [900001, "MNGR"] in first["ended"] and [900003, "COAB"] in first["ended"]
    assert first["started"] == [[900003, "NTRM"]]
    second = r["changes"][1]
    assert (second["last_day_before"], second["first_day_after"]) == ("2025-07-07", "2025-07-08")
    assert second["ended"] == [[900002, "CATC"]] and second["started"] == [[900002, "COAB"]]
    assert len(r["changes"]) == 2 and r["unexplained"] == []
    assert f.requests == len(r["probes"]) <= 16


def test_the_2019_trenton_to_gcl_hitting_coach_move(tmp_path):
    fx = _fixture("nyy_2019_trenton_gcl.json")
    tr, gcl = _t(fx, 567), _t(fx, 475)
    targets = si.bisection_targets({567: tr["season_roster"], 475: gcl["season_roster"]})
    assert targets == {567: ["person_two_teams"], 475: ["person_two_teams"]}
    f = _fetcher(tmp_path, FakeAPI(fx["teams"], copyright=fx["copyright"]))
    r_tr = si.resolve_team(f, 567, 2019, tr["game_dates"], tr["season_roster"])
    assert r_tr["changes"] == [{"last_day_before": "2019-06-23", "first_day_after": "2019-06-24",
                                "ended": [[900002, "COAT"]], "started": []}]
    r_gcl = si.resolve_team(f, 475, 2019, gcl["game_dates"], gcl["season_roster"])
    assert r_gcl["changes"] == [] and r_gcl["first_game"] == "2019-06-24"
    assert [900002, "COAT"] in r_gcl["probes"]["2019-06-24"]
    # Trenton lists no hitting coach after the move
    assert not any(j == "COAT" for _, j in r_tr["probes"][r_tr["last_game"]])


def test_the_season_union_equals_the_union_of_the_bisected_states(tmp_path):
    for name in ("wsh_2025.json", "nyy_2019_trenton_gcl.json"):
        fx = _fixture(name)
        f = _fetcher(tmp_path / name, FakeAPI(fx["teams"]))
        for t in fx["teams"]:
            r = si.resolve_team(f, t["team_id"], t["season"], t["game_dates"], t["season_roster"])
            union = {tuple(p) for s in r["probes"].values() for p in s}
            assert union == set(si.assignments(t["season_roster"])), (name, t["team_id"])


def test_fixtures_carry_no_real_identity():
    for p in FIX.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        for t in d["teams"]:
            rows = list(t["season_roster"]) + [r for s in t["segments"] for r in s["roster"]]
            for r in rows:
                assert 900000 < r["person"]["id"] < 901000
                assert r["person"]["fullName"].startswith("Staff Person ")
                assert "jerseyNumber" not in r


# --- request discipline ----------------------------------------------------------------------------------

def test_rate_limit_and_a_descriptive_user_agent(tmp_path):
    fx = _fixture("wsh_2025.json")
    t = _t(fx, 120)
    now = [0.0]
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    api = FakeAPI(fx["teams"])
    f = si.Fetcher(cache_dir=tmp_path / "staff", opener=api, clock=lambda: now[0], sleep=sleep)
    si.resolve_team(f, 120, 2025, t["game_dates"], t["season_roster"])
    gaps = [b - a for a, b in zip(f.request_times, f.request_times[1:])]
    assert gaps and min(gaps) >= 1 / 3 - 1e-9
    assert si.MIN_INTERVAL_S == pytest.approx(1 / 3)
    ua = api.headers[0]["User-Agent"]
    assert "eephus.io" in ua and "staff history" in ua and "@" not in ua


def test_the_run_stops_on_repeated_non_200(tmp_path):
    calls = []

    def failing(url, headers):
        calls.append(url)
        return 500, b""

    f = _fetcher(tmp_path, failing)
    assert si.team_season_staff(f, 1, 2019) is None
    assert si.team_season_staff(f, 2, 2019) is None
    with pytest.raises(si.FetchStopped):
        si.team_season_staff(f, 3, 2019)
    assert len(calls) == 6  # one retry each on a 5xx
    assert not (tmp_path / "staff" / "raw").exists()  # nothing cached from a failure
    m = si.run_fetch([2019, 2020, 2021], _fetcher(tmp_path / "b", failing), cache_dir=tmp_path / "b", log=lambda s: None)
    assert m["status"].startswith("stopped:")


def test_a_404_is_not_retried_and_the_budget_stops_the_run(tmp_path):
    f = _fetcher(tmp_path, FakeAPI([]), max_requests=2)
    assert si.team_season_staff(f, 5, 2019) is None and f.requests == 1
    assert si.team_season_staff(f, 6, 2019) is None
    with pytest.raises(si.FetchStopped):
        si.team_season_staff(f, 7, 2019)


def test_the_cache_resumes_without_a_request(tmp_path):
    fx = _fixture("wsh_2025.json")
    t = _t(fx, 120)
    f1 = _fetcher(tmp_path, FakeAPI(fx["teams"]))
    r1 = si.resolve_team(f1, 120, 2025, t["game_dates"], t["season_roster"])
    f2 = _fetcher(tmp_path, lambda u, h: (_ for _ in ()).throw(AssertionError(u)))
    r2 = si.resolve_team(f2, 120, 2025, t["game_dates"], t["season_roster"])
    assert r1 == r2 and f2.requests == 0 and f2.cache_hits == f1.requests


def test_a_season_end_to_end_writes_only_the_cache(tmp_path):
    fx = _fixture("nyy_2019_trenton_gcl.json")
    clubs = [{"id": 147, "name": "New York Yankees", "sport": {"id": 1}}]
    api = FakeAPI(fx["teams"], clubs=clubs, copyright=fx["copyright"])
    cache = tmp_path / "staff"
    m = si.run_fetch([2019], _fetcher(tmp_path, api), cache_dir=cache, log=lambda s: None)
    assert m["status"] == "complete"
    idx = json.loads((cache / "index" / "season_2019.json").read_text(encoding="utf-8"))
    by = {b["team_id"]: b for b in idx["bisections"]}
    assert set(by) == {567, 475}
    assert by[567]["changes"][0]["last_day_before"] == "2019-06-23"
    teams = {t["team_id"]: t for t in idx["teams"]}
    assert teams[567]["first_game"] == "2019-04-05" and teams[475]["org_id"] == 147
    assert idx["missing_staff_lists"] == [147]  # the fake knows no club staff: a 404, recorded
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written and all(cache in p.parents for p in written)
    assert "data" not in {p.name for p in tmp_path.rglob("*") if p.is_dir()}


def test_the_cache_is_gitignored_and_never_data():
    assert si.CACHE_DIR == ROOT / ".cache" / "staff"
    assert (si.FIRST_SEASON, si.LAST_SEASON) == (2008, 2026)
    src = (ROOT / "staff_ingest.py").read_text(encoding="utf-8")
    assert "prospects.db" not in src.replace("never prospects.db", "")
    assert chr(0x2014) not in src and chr(0x2013) not in src
