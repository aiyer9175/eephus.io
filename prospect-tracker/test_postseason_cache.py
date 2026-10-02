"""postseason.py: the one postseason results source (F-SCORE plan FS-1, FS_1B).

Fixtures under test_fixtures/postseason/ are trimmed from the public StatsAPI
probes of 2026-09-30 (/api/v1/schedule/postseason/series, seasons 2000, 2012,
2020, 2021, 2025 and 2026 in progress) and from the standings caches of 2012
and 2026. No test makes a network call.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import socket
import subprocess
from datetime import date
from pathlib import Path

import pytest

import postseason as ps
import trades  # noqa: F401  (imports ssl before a test replaces socket.socket)

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "postseason"

CHAMPION = {2000: "NYY", 2012: "SFG", 2020: "LAD", 2021: "ATL", 2025: "LAD"}
PENNANTS = {2000: {"NYY", "NYM"}, 2012: {"SFG", "DET"}, 2020: {"LAD", "TBR"},
            2021: {"ATL", "HOU"}, 2025: {"LAD", "TOR"}}


def _body(season: int) -> dict:
    return json.loads((FIX / f"probe_postseason_series_{season}.json").read_text(encoding="utf-8"))


def _parse(season: int, body: dict | None = None) -> dict:
    return ps.parse(body if body is not None else _body(season), season)


def _counts(parsed: dict) -> tuple:
    reached = [v["round_reached"] for v in parsed["clubs"].values()]
    return tuple(sum(1 for r in reached if r >= k) for k in range(1, 6))


def _envelope(season: int, body: dict, complete: bool, fetched_at: str = "2026-09-30T12:00:00+00:00"):
    return {"season": season, "fetched_at": fetched_at, "complete": complete, "body": body}


@pytest.fixture
def no_network(monkeypatch):
    """Any socket opened by the code under test fails the test."""
    def _refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(ps, "_http_get", _refuse)


# --------------------------------------------------------------------------
# identities on complete seasons
# --------------------------------------------------------------------------

@pytest.mark.parametrize("season", sorted(CHAMPION))
def test_one_champion_and_two_pennants_per_complete_season(season):
    p = _parse(season)
    assert p["complete"] is True
    champs = [c for c, v in p["clubs"].items() if v["round_reached"] == 5]
    pennants = {c for c, v in p["clubs"].items() if v["round_reached"] >= 4}
    assert champs == [CHAMPION[season]]
    assert pennants == PENNANTS[season]
    assert ps.identity_failures(p) == []


@pytest.mark.parametrize("season,expected", [
    (2000, (8, 8, 4, 2, 1)), (2012, (10, 8, 4, 2, 1)), (2020, (16, 8, 4, 2, 1)),
    (2021, (10, 8, 4, 2, 1)), (2025, (12, 8, 4, 2, 1)),
])
def test_round_counts_follow_the_format(season, expected):
    p = _parse(season)
    assert _counts(p) == expected == ps.format_for(season)["round_counts"]
    assert _counts(p)[0] == ps.format_for(season)["berths"]


def test_format_table_by_era():
    assert ps.format_for(2011)["round_counts"] == (8, 8, 4, 2, 1)
    assert ps.format_for(2019)["round_counts"] == (10, 8, 4, 2, 1)
    assert ps.format_for(2021)["round_counts"] == (10, 8, 4, 2, 1)
    assert ps.format_for(2020)["round_counts"] == (16, 8, 4, 2, 1)
    assert ps.format_for(2022)["round_counts"] == (12, 8, 4, 2, 1)
    with pytest.raises(ps.PostseasonError):
        ps.format_for(1999)


def test_2012_round_one_is_read_from_the_schedule_not_the_standings(tmp_path):
    p = _parse(2012)
    assert _counts(p)[0] == 10
    standings = json.loads((FIX / "statsapi_standings_2012.json").read_text(encoding="utf-8"))
    clinched = sum(1 for r in standings["records"] for t in r["teamRecords"] if t["clinched"])
    assert clinched == 8
    assert ps.identity_failures(p) == []
    shutil.copy(FIX / "statsapi_standings_2012.json", tmp_path / "statsapi_standings_2012.json")
    notes = ps.feed_notes(p, cache_dir=tmp_path)
    assert notes == ["feed note 2012: the postseason schedule has 10 round-1 clubs, "
                     "the standings 8 clinched rows"]


def test_each_club_in_at_most_one_series_per_round():
    for season in CHAMPION:
        p = _parse(season)
        for per in p["per_round"].values():
            assert max(per.values()) == 1


def test_a_broken_complete_bracket_raises_on_load(tmp_path):
    body = _body(2025)
    body["series"].remove(next(s for s in body["series"] if s["series"]["gameType"] == "L"))
    (tmp_path / "statsapi_postseason_2025.json").write_text(
        json.dumps(_envelope(2025, body, True)), encoding="utf-8")
    with pytest.raises(ps.PostseasonIdentityError):
        ps.load(2025, cache_dir=tmp_path, tracked_dir=tmp_path / "none")


# --------------------------------------------------------------------------
# the parser's rules
# --------------------------------------------------------------------------

def test_placeholders_are_dropped_in_the_live_bracket():
    p = _parse(2026)
    assert p["complete"] is False
    assert {5528, 5513, 2710} <= set(p["placeholders"])
    assert len(p["clubs"]) == 30
    named = {c for r in p["series"] for c in (r[3], r[4]) if c}
    assert named <= set(p["clubs"])
    assert all(isinstance(c, str) and len(c) == 3 for c in named)
    assert sum(1 for v in p["clubs"].values() if v["round_reached"] >= 1) == 12


def test_a_placeholder_never_resolves_through_its_name():
    body = _body(2026)
    names = {((g["teams"][side]["team"].get("id")), g["teams"][side]["team"].get("name"))
             for s in body["series"] for g in s["games"] for side in ("home", "away")}
    assert (5528, "HOU/CWS") in names
    p = ps.parse(body, 2026)
    d1 = [r for r in p["series"] if r[1] == 2]
    assert all(r[4] is None for r in d1)


def test_postponed_and_suspended_games_count_nothing():
    base = _parse(2025)
    body = _body(2025)
    ws = next(s for s in body["series"] if s["series"]["gameType"] == "W")
    finals = [g for g in ws["games"] if g["status"]["codedGameState"] == "F"]
    postponed = finals[0]
    postponed["status"] = {"abstractGameState": "Final", "codedGameState": "D"}
    suspended = finals[1]
    suspended["status"] = {"abstractGameState": "Live", "codedGameState": "U"}
    p = ps.parse(body, 2025)
    row0 = next(r for r in base["series"] if r[1] == 4)
    row1 = next(r for r in p["series"] if r[1] == 4)
    assert row1[5] + row1[6] == row0[5] + row0[6] - 2


def test_a_postponed_record_beside_its_final_twin_is_not_double_counted():
    p = _parse(2020)
    f7 = next(r for r in p["series"] if r[0] == "F_7")
    assert f7[2] == 3 and max(f7[5], f7[6]) == 2 and f7[7] is not None
    body = _body(2020)
    ent = next(s for s in body["series"] if s["series"]["id"] == "F_7")
    dead = [g for g in ent["games"] if g["status"]["codedGameState"] == "D"]
    assert dead and dead[0]["status"]["abstractGameState"] == "Final"


def test_a_series_is_won_at_half_its_length_plus_one():
    p = _parse(2012)
    wc = [r for r in p["series"] if r[1] == 1]
    assert wc and all(r[2] == 1 and max(r[5], r[6]) == 1 and r[8] for r in wc)
    ds = [r for r in p["series"] if r[1] == 2]
    assert all(r[2] == 5 and max(r[5], r[6]) == 3 for r in ds)


def test_byes_only_in_seasons_with_a_first_round():
    byes = lambda y: sorted(c for c, v in _parse(y)["clubs"].items() if v["bye"])
    assert byes(2026) == ["CLE", "LAD", "MIL", "TBR"]
    assert byes(2000) == []
    assert byes(2020) == []
    assert len(byes(2012)) == 6
    assert len(byes(2025)) == 4


def test_in_progress_marks_the_clubs_still_alive():
    p = _parse(2026)
    alive = {c for c, v in p["clubs"].items() if v["in_progress"]}
    assert {"CLE", "LAD", "MIL", "TBR"} <= alive
    assert len(alive) == 12
    assert not any(v["in_progress"] for v in _parse(2025)["clubs"].values())


def test_tiebreaker_games_are_not_a_round():
    body = _body(2000)
    tie = copy.deepcopy(body["series"][0])
    tie["series"] = {"id": "R_115_53", "gameType": "R"}
    for g in tie["games"]:
        g["gameType"] = "R"
        g["seriesDescription"] = "Regular Season"
    body["series"].append(tie)
    assert ps.parse(body, 2000)["series"] == _parse(2000)["series"]


def test_an_entry_holding_two_series_is_split_by_club_pair():
    """2003's feed lists two division series under one id (D_2: SFG-MIA and
    ATH-BOS); the parser splits by the clubs each game names."""
    body = _body(2000)
    ds = [s for s in body["series"] if s["series"]["gameType"] == "D"]
    first, second = ds[0], ds[1]
    first["games"].extend(second["games"])
    body["series"].remove(second)
    p = ps.parse(body, 2000)
    assert ps.identity_failures(p) == []
    assert _counts(p) == (8, 8, 4, 2, 1)
    assert sum(1 for r in p["series"] if r[1] == 2) == 4


def test_a_body_without_series_is_refused():
    with pytest.raises(ps.PostseasonError):
        ps.parse({"copyright": "x"}, 2025)


def test_the_trimmed_copy_parses_like_the_full_body():
    for season in (2000, 2012, 2020, 2021, 2025, 2026):
        body = _body(season)
        full = ps.parse(body, season)
        again = ps.parse(ps.trim_body(body), season)
        assert (again["series"], again["clubs"]) == (full["series"], full["clubs"])


# --------------------------------------------------------------------------
# fetch: the freeze, the once-a-day rule, the regular-season gate
# --------------------------------------------------------------------------

def test_a_frozen_season_is_never_refetched(tmp_path, no_network):
    p = tmp_path / "statsapi_postseason_2025.json"
    p.write_text(json.dumps(_envelope(2025, _body(2025), True)), encoding="utf-8")
    before = p.read_bytes()
    got = ps.fetch(2025, cache_dir=tmp_path, today=date(2026, 10, 2))
    assert got["action"] == "skipped" and got["reason"] == "frozen"
    assert p.read_bytes() == before


def test_the_live_season_waits_for_the_regular_season_to_end(tmp_path, no_network):
    got = ps.fetch(2026, cache_dir=tmp_path, today=date(2026, 9, 20),
                   regular_season_end="2026-09-27")
    assert (got["action"], got["reason"]) == ("skipped", "regular season not over")
    assert ps.fetch_decision(2026, None, date(2026, 9, 28), None) == (
        False, "no regular-season end date on disk")
    assert ps.fetch_decision(2027, None, date(2026, 10, 2), None) == (False, "future season")
    assert not (tmp_path / "statsapi_postseason_2026.json").exists()


def test_the_live_season_is_fetched_at_most_once_a_day(tmp_path):
    calls = []

    def fake_get(url):
        calls.append(url)
        return _body(2026)

    got = ps.fetch(2026, cache_dir=tmp_path, today=date(2026, 9, 30),
                   regular_season_end="2026-09-27", http_get=fake_get)
    assert got["action"] == "fetched" and got["complete"] is False
    doc = json.loads((tmp_path / "statsapi_postseason_2026.json").read_text(encoding="utf-8"))
    assert set(doc) == {"season", "fetched_at", "complete", "body"}
    doc["fetched_at"] = "2026-09-30T12:00:00+00:00"
    (tmp_path / "statsapi_postseason_2026.json").write_text(json.dumps(doc), encoding="utf-8")
    again = ps.fetch(2026, cache_dir=tmp_path, today=date(2026, 9, 30),
                     regular_season_end="2026-09-27", http_get=fake_get)
    assert (again["action"], again["reason"]) == ("skipped", "fetched today")
    nxt = ps.fetch(2026, cache_dir=tmp_path, today=date(2026, 10, 1),
                   regular_season_end="2026-09-27", http_get=fake_get)
    assert nxt["action"] == "fetched"
    assert len(calls) == 2
    assert all(u.endswith("season=2026") and "schedule/postseason/series" in u for u in calls)


def test_no_refetch_before_the_first_postseason_game(tmp_path, no_network):
    body = _body(2026)
    (tmp_path / "statsapi_postseason_2026.json").write_text(
        json.dumps(_envelope(2026, body, False, "2026-09-28T12:00:00+00:00")), encoding="utf-8")
    got = ps.fetch(2026, cache_dir=tmp_path, today=date(2026, 9, 28),
                   regular_season_end="2026-09-27")
    assert (got["action"], got["reason"]) == ("skipped", "fetched today")
    first = ps._first_game_date(body)
    assert first == "2026-09-29"
    ok, reason = ps.fetch_decision(2026, _envelope(2026, body, False, "2026-09-27T12:00:00+00:00"),
                                   date(2026, 9, 28), "2026-09-27")
    assert (ok, reason) == (False, "first postseason game not yet played")


def test_a_failed_fetch_leaves_yesterdays_file(tmp_path):
    p = tmp_path / "statsapi_postseason_2026.json"
    p.write_text(json.dumps(_envelope(2026, _body(2026), False, "2026-09-30T12:00:00+00:00")),
                 encoding="utf-8")
    before = p.read_bytes()
    with pytest.raises(ps.PostseasonError):
        ps.fetch(2026, cache_dir=tmp_path, today=date(2026, 10, 1),
                 regular_season_end="2026-09-27", http_get=lambda url: {"copyright": "x"})
    assert p.read_bytes() == before
    assert ps.rejected_path(2026, tmp_path).exists()


# --------------------------------------------------------------------------
# load: the tracked copy first for a completed season
# --------------------------------------------------------------------------

def test_load_reads_the_tracked_copy_for_a_completed_season(tmp_path):
    tracked = tmp_path / "tracked"
    tracked.mkdir()
    (tracked / "statsapi_postseason_2025.json").write_text(
        json.dumps(_envelope(2025, ps.trim_body(_body(2025)), True)), encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "statsapi_postseason_2025.json").write_text(
        json.dumps(_envelope(2025, {"series": []}, True)), encoding="utf-8")
    p = ps.load(2025, cache_dir=cache, tracked_dir=tracked)
    assert p["source"] == "tracked"
    assert [c for c, v in p["clubs"].items() if v["round_reached"] == 5] == ["LAD"]


def test_load_reads_the_live_season_from_the_cache(tmp_path):
    (tmp_path / "statsapi_postseason_2026.json").write_text(
        json.dumps(_envelope(2026, _body(2026), False)), encoding="utf-8")
    p = ps.load(2026, cache_dir=tmp_path, tracked_dir=tmp_path / "none")
    assert p["source"] == "cache" and p["complete"] is False
    assert ps.load(2024, cache_dir=tmp_path, tracked_dir=tmp_path / "none") is None


def test_the_repository_tracked_copy_loads_with_its_identities():
    for season in range(2000, 2026):
        p = ps.load(season, tracked_dir=ps.TRACKED, cache_dir=ROOT / "no_cache_here")
        assert p is not None and p["source"] == "tracked" and p["complete"], season


# --------------------------------------------------------------------------
# the tracked set, the deploy consumers, the daily step
# --------------------------------------------------------------------------

def test_the_tracked_set_is_in_git_and_ships_in_neither_deploy_consumer():
    try:
        out = subprocess.run(["git", "ls-files", "data/_labs/postseason"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    expected = [f"data/_labs/postseason/statsapi_postseason_{y}.json" for y in range(2000, 2026)]
    assert sorted(out) == expected
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    workflow = (ROOT.parent / ".github" / "workflows"
                / "deploy-prospect-tracker.yml").read_text(encoding="utf-8")
    for text in (nightly, workflow):
        assert "_labs" not in text and "postseason/" not in text
    manifest = (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    assert "_labs" not in manifest and "postseason" not in manifest


def test_division_champions_2026_names_atl_never_phi(tmp_path):
    shutil.copy(FIX / "statsapi_standings_2026.json", tmp_path / "statsapi_standings_2026.json")
    champs = ps.division_champions(2026, cache_dir=tmp_path)
    assert champs[204] == "ATL"
    assert "PHI" not in champs.values()


def test_run_daily_wires_d8p_right_after_trade_detection():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    labels = re.findall(r'with _step\("([^"]+)"', src)
    assert labels.count("d8p. Postseason series cache") == 1
    assert not any(l.startswith("d8p") and l != "d8p. Postseason series cache" for l in labels)
    i = labels.index("d8. Trade detection")
    assert labels[i + 1] == "d8p. Postseason series cache"
    block = src[src.index('with _step("d8p. Postseason series cache"'):
                src.index('with _step("d8b.')]
    assert '_record_ingest("postseason_cache", True' in block
    assert '_record_ingest("postseason_cache", False' in block


def test_postseason_cache_is_watched_below_franchise_export():
    import run_monthly
    order = list(run_monthly.SCHEDULED_EXPORTS)
    assert order.index("postseason_cache") > order.index("franchise_export") > order.index("mgmt_export")
    assert run_monthly._ingest_kind("postseason_cache") == "export"
