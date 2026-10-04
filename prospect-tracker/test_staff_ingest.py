# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Staff Gems stages 0 and 1: the gate registration is present; the fetch half of staff_ingest.py
(date bisection, rate limit, stop rule, cache) behaves on saved fixtures; and the parse half (the
role map, spells, units, location spells, the database write) holds its rules: the role map is
total and never guesses, every row carries an MLBAM id, bisected changes land on the right days,
and the season union equals the union of the bisected spells. No network: every test runs on
test_fixtures/staff/*.json (live StatsAPI responses of 2026-10-03, pseudonymized) through a fake
opener, urllib is blocked, and every database is a temporary file."""
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
    # stage 1 writes the database ONLY through storage.replace_staff_tables, after the backup;
    # nothing is ever written under data/
    assert not re.search(r"""/\s*["']data["']""", src) and "data/" not in src.replace("never data/", "").replace(
        "nothing under data/", "")
    assert set(re.findall(r"storage\.(\w+)", src)) == {
        "DB_PATH", "load_player_transactions", "load_player_transactions_meta", "load_career_stats",
        "replace_staff_tables"}
    assert src.count("sqlite3.connect(") == 3  # the backup's source, copy and integrity check only
    assert chr(0x2014) not in src and chr(0x2013) not in src


# --- stage 1: the role map ------------------------------------------------------------------------

CENSUS = FIX / "census" / "job_title_census.json"
ROLE_MAP = ROOT / "config" / "staff_roles.yaml"


def test_the_role_map_is_total_over_every_job_and_title_ever_listed():
    import yaml
    rm = si.RoleMap.load(ROLE_MAP)
    doc = yaml.safe_load(ROLE_MAP.read_text(encoding="utf-8"))
    census = json.loads(CENSUS.read_text(encoding="utf-8"))["pairs"]
    assert len(census) > 500 and sum(n for _, _, n in census) > 24_000
    by_title_jobs = {j for j, v in rm.jobs.items() if v == "by_title"}
    for job, title, _ in census:
        # every job code is mapped explicitly, and every title under a generic code too
        assert job in rm.jobs, job
        if job in by_title_jobs:
            assert si.norm_title(title) in rm.titles or (job, si.norm_title(title)) in rm.pairs, (job, title)
        role, rule = rm.classify(job, title)
        assert role in si.ROLE_VALUES and rule in ("pair", "job", "title"), (job, title, role, rule)
    # the thirteen codes the design names, and the gate's four credited roles
    for job, role in {"MNGR": "manager", "COAT": "hitting", "COAH": "hitting", "COAA": "hitting",
                      "COAP": "pitching", "COPA": "pitching", "COAU": "pitching", "DEFC": "defense",
                      "COA1": "first_base", "COA3": "third_base", "COAB": "excluded",
                      "BCAT": "excluded", "COAC": "by_title"}.items():
        assert doc["jobs"][job] == role, job
    assert si.CREDITED_ROLES == ("manager", "hitting", "pitching", "defense")
    assert rm.classify("NTRM", "Interim Manager") == ("manager", "job")
    assert rm.classify("COAC", "Coach") == ("excluded", "title")


def test_an_unmapped_job_or_title_is_never_given_a_guessed_role():
    rm = si.RoleMap.load(ROLE_MAP)
    # a title that CONTAINS a mapped title is still unmapped: no similarity, no substring
    assert rm.classify("COAC", "Hitting Coach Extraordinaire") == ("review", "unmapped_title")
    assert rm.classify("COAC", "Pitching  COACH ") == ("review", "unmapped_title")
    assert rm.classify("COAC", "  Hitting   COACH ") == ("hitting", "title")  # whitespace and case only
    assert rm.classify("ZZZZ", "Pitching Coach") == ("review", "unmapped_job")
    assert rm.classify(None, None) == ("review", "unmapped_job")
    # a title that contradicts its job code is decided by the pair, not the code
    assert rm.classify("COAP", "Complex Hitting Lead") == ("review", "pair")
    assert rm.classify("MNGR", "Honorary Manager") == ("excluded", "pair")
    with pytest.raises(ValueError):
        si.RoleMap({"roles": {r: "credited" for r in si.CREDITED_ROLES + si.CONTEXT_ROLES},
                    "jobs": {"XXXX": "hitting_guess"}})


# --- stage 1: parsing the cache --------------------------------------------------------------------

def _fixture_cache(tmp_path: Path) -> Path:
    """A cache written by the real fetch from the two saved fixtures (2019 and 2025)."""
    cache = tmp_path / "staff"
    for name, clubs in (("nyy_2019_trenton_gcl.json", [{"id": 147, "name": "New York Yankees", "sport": {"id": 1}}]),
                        ("wsh_2025.json", [{"id": 120, "name": "Washington Nationals", "sport": {"id": 1}}])):
        fx = _fixture(name)
        api = FakeAPI(fx["teams"], clubs=clubs, copyright=fx["copyright"])
        f = si.Fetcher(cache_dir=cache, opener=api, sleep=lambda s: None)
        m = si.run_fetch([fx["teams"][0]["season"]], f, cache_dir=cache, log=lambda s: None)
        assert m["status"] == "complete"
    return cache


def _spells(parsed, team_id, season):
    return [s for s in parsed["spells"] if s["team_id"] == team_id and s["season"] == season]


def test_every_spell_carries_an_mlbam_id_and_a_row_without_one_creates_nothing(tmp_path):
    cache = _fixture_cache(tmp_path)
    f = cache / "raw" / "coaches_season" / "567_2019.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["body"]["roster"].append({"person": {"fullName": "Staff Person 01"}, "jobId": "COAP",
                                "job": "Pitching Coach", "title": "Pitching Coach"})
    d["body"]["roster"].append({"person": {"id": "not-an-id", "fullName": "Staff Person 77"},
                                "jobId": "COAT", "title": "Hitting Coach"})
    f.write_text(json.dumps(d), encoding="utf-8")
    p = si.parse_cache(cache, si.RoleMap.load(ROLE_MAP))
    assert p["counts"]["rows_without_mlbam_id"] == 2
    ids = {q["person_id"] for q in p["persons"]}
    assert ids and all(isinstance(i, int) and 900000 < i < 901000 for i in ids)
    assert all(s["person_id"] in ids for s in p["spells"])
    assert "Staff Person 77" not in {n for q in p["persons"] for n in q["names"]}
    # and the writer refuses a spell whose id is unknown
    with pytest.raises(ValueError):
        import storage
        storage.replace_staff_tables(persons=[], units=[], spells=[p["spells"][0]], role_review=[],
                                     identity_review=[], locations=[], cache_dir="x", role_map="y",
                                     counts={})


def test_the_wsh_2025_change_lands_on_its_days_in_the_spells(tmp_path):
    p = si.parse_cache(_fixture_cache(tmp_path), si.RoleMap.load(ROLE_MAP))
    sp = {(s["person_id"], s["job_id"], s["start_date"], s["end_date"]): s for s in _spells(p, 120, 2025)}
    assert all(s["resolution"] == "day" for s in sp.values())
    assert (900001, "MNGR", "2025-03-27", "2025-07-06") in sp
    assert (900003, "COAB", "2025-03-27", "2025-07-06") in sp
    assert (900003, "NTRM", "2025-07-07", "2025-09-28") in sp
    assert (900002, "CATC", "2025-07-07", "2025-07-07") not in sp
    assert (900002, "COAB", "2025-07-08", "2025-09-28") in sp
    assert sp[(900001, "MNGR", "2025-03-27", "2025-07-06")]["role"] == "manager"
    assert sp[(900003, "NTRM", "2025-07-07", "2025-09-28")]["role"] == "manager"
    assert sp[(900002, "COAB", "2025-07-08", "2025-09-28")]["role"] == "excluded"
    # a job held across both changes stays one spell, never split at a change it did not take part in
    unchanged = [s for s in sp.values() if s["person_id"] not in (900001, 900002, 900003)]
    assert unchanged and all((s["start_date"], s["end_date"]) == ("2025-03-27", "2025-09-28") for s in unchanged)


def test_the_2019_trenton_to_gcl_move_lands_on_its_days_in_the_spells(tmp_path):
    p = si.parse_cache(_fixture_cache(tmp_path), si.RoleMap.load(ROLE_MAP))
    tr = [s for s in _spells(p, 567, 2019) if s["person_id"] == 900002]
    gcl = [s for s in _spells(p, 475, 2019) if s["person_id"] == 900002]
    assert [(s["job_id"], s["start_date"], s["end_date"], s["resolution"]) for s in tr] == [
        ("COAT", "2019-04-05", "2019-06-23", "day")]
    assert [(s["job_id"], s["start_date"], s["resolution"]) for s in gcl] == [("COAT", "2019-06-24", "day")]
    assert tr[0]["role"] == gcl[0]["role"] == "hitting"
    assert tr[0]["level"] == "AA" and gcl[0]["level"] == "CPX" and tr[0]["org_id"] == gcl[0]["org_id"] == 147


def test_the_season_union_equals_the_union_of_the_bisected_spells(tmp_path):
    cache = _fixture_cache(tmp_path)
    p = si.parse_cache(cache, si.RoleMap.load(ROLE_MAP))
    for name in ("wsh_2025.json", "nyy_2019_trenton_gcl.json"):
        for t in _fixture(name)["teams"]:
            got = {(s["person_id"], s["job_id"]) for s in _spells(p, t["team_id"], t["season"])}
            assert got == set(si.assignments(t["season_roster"])), (name, t["team_id"])
    # every day spell sits inside its team's first and last game, and a person's spells in one
    # job never overlap
    units = {u["unit_id"]: u for u in p["units"]}
    seen: dict = {}
    for s in p["spells"]:
        u = units[s["unit_id"]]
        assert u["start_date"] <= s["start_date"] <= s["end_date"] <= u["end_date"]
        for a, b in seen.get((s["person_id"], s["job_id"], s["unit_id"]), []):
            assert s["end_date"] < a or s["start_date"] > b
        seen.setdefault((s["person_id"], s["job_id"], s["unit_id"]), []).append((s["start_date"], s["end_date"]))


def test_a_list_assignment_no_probe_shows_keeps_a_season_spell_marked_unexplained(tmp_path):
    cache = _fixture_cache(tmp_path)
    f = cache / "raw" / "coaches_season" / "120_2025.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["body"]["roster"].append({"person": {"id": 900099, "fullName": "Staff Person 99"},
                                "jobId": "COAP", "job": "Pitching Coach", "title": "Pitching Coach"})
    f.write_text(json.dumps(d), encoding="utf-8")
    p = si.parse_cache(cache, si.RoleMap.load(ROLE_MAP))
    s = [x for x in _spells(p, 120, 2025) if x["person_id"] == 900099]
    assert [(x["resolution"], x["resolution_note"], x["start_date"], x["end_date"]) for x in s] == [
        ("season", "unexplained", "2025-03-27", "2025-09-28")]


def test_units_cover_teams_offseasons_and_the_2020_org_unit(tmp_path):
    p = si.parse_cache(_fixture_cache(tmp_path), si.RoleMap.load(ROLE_MAP))
    u = {x["unit_id"]: x for x in p["units"]}
    assert u["T567_2019"]["kind"] == "affiliate" and u["T567_2019"]["level"] == "AA"
    assert u["T475_2019"]["level"] == "CPX" and u["T120_2025"]["kind"] == "mlb"
    off = u["OFF_147_2019"]
    # the next season, 2020, played no minor league games: the winter closes on Dec 31
    assert (off["kind"], off["start_date"], off["end_date"]) == ("offseason", "2019-09-03", "2019-12-31")
    assert "OFF_120_2025" not in u           # an org with no affiliate game has no winter unit
    assert "ORG2020_147" not in u            # 2020 is not in this cache
    assert si._unit_level(16, "Dominican Summer League", "DSL Yankees") == "DSL"
    assert si._unit_level(16, None, "VSL Rays") == "DSL" and si._unit_level(15, None, "x") == "A"
    units = si.build_units(_season_cache(tmp_path / "s", {2019: "2019-09-02", 2020: None, 2021: "2021-05-04"}),
                           [2019, 2020, 2021])
    by = {x["unit_id"]: x for x in units}
    assert (by["OFF_147_2019"]["start_date"], by["OFF_147_2019"]["end_date"]) == ("2019-09-03", "2019-12-31")
    assert (by["ORG2020_147"]["start_date"], by["ORG2020_147"]["end_date"]) == ("2020-01-01", "2020-12-31")
    assert (by["OFF_147_2020"]["start_date"], by["OFF_147_2020"]["end_date"]) == ("2021-01-01", "2021-05-03")


def _season_cache(cache: Path, last_games: dict) -> Path:
    """A minimal cache index: one club (147) and one AA affiliate per season."""
    (cache / "index").mkdir(parents=True)
    for y, last in last_games.items():
        first = None if last is None else f"{y}-04-05" if y != 2021 else "2021-05-04"
        teams = [{"team_id": 147, "name": "Club", "sport_id": 1, "org_id": 147, "first_game": first,
                  "last_game": last, "staff_rows": 0},
                 {"team_id": 567, "name": "Affiliate", "sport_id": 12, "org_id": 147, "first_game": first,
                  "last_game": last, "staff_rows": 0}]
        (cache / "index" / f"season_{y}.json").write_text(json.dumps({"season": y, "teams": teams,
                                                                       "bisections": []}), encoding="utf-8")
    return cache


# --- stage 1: player location spells ------------------------------------------------------------------

def _units_for_locations() -> list[dict]:
    out = []
    for y in (2021, 2022):
        for tid, sport, org, level in ((147, 1, 147, "MLB"), (567, 12, 147, "AA"), (475, 16, 147, "CPX"),
                                       (120, 1, 120, "MLB"), (436, 14, 120, "A")):
            out.append({"unit_id": f"T{tid}_{y}", "kind": "mlb" if sport == 1 else "affiliate", "season": y,
                        "team_id": tid, "team_name": f"Team {tid}", "org_id": org,
                        "org_code": {147: "NYY", 120: "WSN"}[org], "sport_id": sport, "level": level,
                        "league": None, "start_date": f"{y}-04-06", "end_date": f"{y}-09-20"})
    return out


def _tx(d, code, desc, to=None, frm=None, i=0):
    return {"date": d, "type_code": code, "description": desc, "to_team_id": to, "from_team_id": frm,
            "to_team_name": "", "from_team_name": "", "id": i}


def test_day_locations_follow_moves_il_rehab_and_org_changes():
    maps = si.location_maps(_units_for_locations())
    txs = [
        _tx("2021-05-01", "ASG", "SS Player A assigned to Team 475.", to=475, i=1),
        _tx("2021-07-01", "ASG", "SS Player A assigned to Team 567 from Team 475.", to=567, frm=475, i=2),
        _tx("2021-07-10", "SC", "Team 567 placed SS Player A on the 7-day injured list.", to=567, i=3),
        _tx("2021-07-20", "ASG", "SS Player A sent on a rehab assignment to Team 475.", to=475, i=4),
        _tx("2021-07-25", "SC", "Team 567 activated SS Player A from the 7-day injured list.", to=567, i=5),
        _tx("2022-02-20", "ASG", "SS Player A assigned to Team 147 as a non-roster invitee to spring training.", to=147, i=6),
        _tx("2022-06-01", "TR", "Team 147 traded SS Player A to Team 120.", to=120, i=7),
        _tx("2022-06-04", "ASG", "SS Player A assigned to Team 436.", to=436, i=8),
        _tx("2022-08-01", "REL", "Team 120 released SS Player A.", to=120, i=9),
    ]
    rows, counts = si.day_locations("player_a", txs, maps, "2022-09-30")
    got = [(r["team_id"], r["start_date"], r["end_date"], r["status"]) for r in rows]
    assert got == [
        (475, "2021-05-01", "2021-06-30", "active"),
        (567, "2021-07-01", "2021-07-09", "active"),
        (567, "2021-07-10", "2021-07-19", "il"),
        (475, "2021-07-20", "2021-07-24", "rehab"),
        (567, "2021-07-25", "2021-12-31", "active"),   # cut at Dec 31 ...
        (567, "2022-01-01", "2022-05-31", "active"),   # ... and the spring invite is not a move
        (436, "2022-06-04", "2022-07-31", "active"),   # the trade left a gap until the placement
    ]
    assert counts["org_change_gaps"] == 1
    assert all(r["resolution"] == "day" and r["weight"] == 1.0 and r["source"] == "transactions" for r in rows)
    assert {r["level"] for r in rows} == {"CPX", "AA", "A"}


def test_season_locations_weight_by_games_and_never_guess_a_team():
    units = _units_for_locations()
    units.append({**units[2], "unit_id": "T476_2021", "team_id": 476})      # a second NYY complex team
    maps = si.location_maps(units)
    career = [{"season": 2021, "level": "AA", "org": "NYY", "games": 60},
              {"season": 2021, "level": "CPX", "org": "NYY", "games": 20},
              {"season": 2022, "level": "A", "org": "NYY", "games": 0,
               "stints": [{"level": "A", "org": "NYY", "games": 30}, {"level": "A", "org": "WSN", "games": 10}]},
              {"season": 2007, "level": "AA", "org": "NYY", "games": 50}]
    rows = si.season_locations("player_b", career, maps, skip_seasons=set())
    by = {(r["season"], r["level"], r["org_code"]): r for r in rows}
    assert by[(2021, "AA", "NYY")]["weight"] == 0.75 and by[(2021, "AA", "NYY")]["team_id"] == 567
    cpx = by[(2021, "CPX", "NYY")]
    assert cpx["weight"] == 0.25 and cpx["team_id"] is None and cpx["n_candidates"] == 2
    assert by[(2022, "A", "WSN")]["team_id"] == 436 and by[(2022, "A", "WSN")]["weight"] == 0.25
    assert by[(2022, "A", "NYY")]["team_id"] is None and by[(2022, "A", "NYY")]["n_candidates"] == 0
    assert all(r["season"] >= 2008 and r["resolution"] == "season" for r in rows)
    # a season that has day rows is not doubled by career rows
    assert si.season_locations("player_b", career, maps, skip_seasons={2021, 2022}) == []


def test_build_locations_prefers_day_rows_and_falls_back_to_career_rows():
    units = _units_for_locations()
    tx = {"p1": [_tx("2021-05-01", "ASG", "P1 assigned to Team 567.", to=567, i=1)]}
    career = {"p1": [{"season": 2021, "level": "AA", "org": "NYY", "games": 40},
                     {"season": 2022, "level": "AA", "org": "NYY", "games": 40}],
              "p2": [{"season": 2022, "level": "A", "org": "WSN", "games": 12}]}
    rows, counts = si.build_locations(tx, {"p1": "2021-08-31 10:00:00"}, career, units, today="2026-10-03")
    p1 = [r for r in rows if r["player_key"] == "p1"]
    assert [(r["season"], r["resolution"]) for r in p1] == [(2021, "day"), (2022, "season")]
    assert p1[0]["end_date"] == "2021-08-31"     # an open spell ends on the day its payload was fetched
    assert counts["players_with_day_rows"] == 1 and counts["players_season_rows_only"] == 1


# --- stage 1: the database write and the backup ---------------------------------------------------------

def test_the_parse_writes_the_tables_idempotently_after_a_backup(tmp_path, monkeypatch):
    import sqlite3
    import storage
    db = tmp_path / "prospects_test.db"
    monkeypatch.setattr(storage, "DB_PATH", db)
    storage.init_db()
    storage.upsert_player_transactions({"p1": [_tx("2019-05-01", "ASG", "P1 assigned to Trenton.", to=567, i=1)]})
    cache = _fixture_cache(tmp_path)
    c1 = si.run_parse(cache, ROLE_MAP, backup=True, log=lambda s: None)
    baks = [b for b in sorted(tmp_path.glob("prospects_test.db.bak-staff-*"))
            if not b.name.endswith(("-wal", "-shm"))]
    assert len(baks) == 1
    con = sqlite3.connect(baks[0])
    assert con.execute("SELECT name FROM sqlite_master WHERE name='staff_spells'").fetchone() is None
    con.close()
    c2 = si.run_parse(cache, ROLE_MAP, backup=False, log=lambda s: None)
    assert {k: v for k, v in c1.items() if k != "run_id"} == {k: v for k, v in c2.items() if k != "run_id"}
    spells = storage.load_staff_table("staff_spells")
    assert len(spells) == c1["spells"] and all(s["person_id"] for s in spells)
    assert len(storage.load_staff_table("staff_persons")) == c1["persons"]
    locs = storage.load_staff_table("player_location_spells")
    assert [(r["player_key"], r["team_id"], r["start_date"]) for r in locs] == [("p1", 567, "2019-05-01")]
    assert len(storage.load_staff_table("staff_parse_runs")) == 2
    # nothing outside the temporary directory, and nothing under any data/ directory
    assert not any(p.name == "data" for p in tmp_path.rglob("*") if p.is_dir())


def test_no_backup_means_no_write(tmp_path, monkeypatch):
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "prospects_test.db")
    storage.init_db()

    def _fail(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(si, "backup_database", _fail)
    with pytest.raises(OSError):
        si.run_parse(_fixture_cache(tmp_path), ROLE_MAP, backup=True, log=lambda s: None)
    assert storage.load_staff_table("staff_spells") == []
    assert storage.load_staff_table("staff_parse_runs") == []


def test_the_parse_reads_no_grade_and_no_outcome():
    src = (ROOT / "staff_ingest.py").read_text(encoding="utf-8")
    parse = src[src.index("# --- stage 1: the parse half"):]
    for banned in ("snapshots", "fv", "career_war", "war", "efv", "consensus", "statlines", "ops",
                   "fv_to_6yr_avg_war", "tool"):
        assert not re.search(rf"\b{banned}\b", parse), banned
    # the only career-row fields read are where and how much the player played
    body = src[src.index("def season_locations"):src.index("def build_locations")]
    assert set(re.findall(r"""(?:\br|\bpart)\.get\("(\w+)"\)""", body)) == {
        "season", "level", "org", "games", "stints"}
