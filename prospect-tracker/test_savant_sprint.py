# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Offline tests for savant_sprint (Baseball Savant sprint speed ingest).

Fully offline: an autouse fixture severs urlopen, so anything that reaches the
network fails loudly instead of silently passing on a live fetch. Fixture CSV
text is copied verbatim from real 2015/2024 responses, including the two ragged
cases the feed actually produces (blank hp_to_1b, blank position).

The `year` vs `season` parameter trap is pinned by a test because it is silent:
`season=` returns the default year with a 200, so a regression there yields one
season of data stamped as twelve rather than an error.
"""

from __future__ import annotations

import json

import pytest

import savant_sprint as ss

_HEADER = ('"last_name, first_name","player_id","team_id","team","position",'
           '"age","competitive_runs","bolts","hp_to_1b","sprint_speed"')
_WITT = '"Witt Jr., Bobby",677951,118,"KC","SS",24,"298","156","4.10","30.5"'
_BUXTON = '"Buxton, Byron",621439,142,"MIN","CF",21,"45","31",,"30.9"'   # no hp_to_1b
_UTILITY = '"Ciriaco, Pedro",465674,144,"ATL","",29,"60","18","4.10","29.3"'  # no position
_NO_SPEED = '"Ghost, Nobody",111111,144,"ATL","1B",29,"60","18","4.10",'

_CSV = "\n".join([_HEADER, _WITT, _BUXTON, _UTILITY, _NO_SPEED]) + "\n"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("test tried to hit the network")
    monkeypatch.setattr(ss.urllib.request, "urlopen", _boom)
    monkeypatch.setattr(ss, "_throttle", lambda: None)


class _Resp:
    """Minimal urlopen stand-in (context manager with .read())."""

    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


# --------------------------------------------------------------------------- #
# the silent parameter trap
# --------------------------------------------------------------------------- #
def test_endpoint_uses_year_not_season():
    """`season=` is accepted and ignored by Savant, so it must never appear."""
    assert "year={y}" in ss.BASE
    assert "season=" not in ss.BASE
    assert ss.BASE.format(y=2019).endswith("year=2019&min=10&csv=true")


def test_first_season_is_2015():
    """Sprint speed predates OAA by a season; do not inherit OAA's 2016 floor."""
    assert ss.FIRST_SEASON == 2015


def test_throttle_interval_matches_house_manners():
    assert ss._MIN_INTERVAL >= 1.0
    assert "eephus.io" in ss.UA


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def test_parse_rows_reads_the_real_columns():
    rows = {r["mlbam"]: r for r in ss.parse_rows(_CSV, 2024)}
    witt = rows[677951]
    assert witt["season"] == 2024        # stamped by us, the CSV has no year column
    assert witt["name"] == "Witt Jr., Bobby"
    assert witt["ft_s"] == 30.5
    assert witt["hp1"] == 4.10
    assert witt["runs"] == 298 and witt["bolts"] == 156
    assert witt["age"] == 24
    assert witt["pos"] == "SS" and witt["team"] == "KC"
    # Counting columns stay ints so the compact JSON carries no stray .0
    assert isinstance(witt["runs"], int) and isinstance(witt["age"], int)


def test_missing_hp_to_1b_is_absent_not_zero():
    """Home to first is only clocked on the plays that produce it (~12% blank)."""
    rows = {r["mlbam"]: r for r in ss.parse_rows(_CSV, 2015)}
    assert "hp1" not in rows[621439]
    assert rows[621439]["ft_s"] == 30.9


def test_utility_player_without_a_position_is_kept():
    """A blank position is still a real speed observation, not a bad row."""
    rows = {r["mlbam"]: r for r in ss.parse_rows(_CSV, 2015)}
    assert "pos" not in rows[465674]
    assert rows[465674]["ft_s"] == 29.3


def test_row_without_speed_is_dropped():
    rows = {r["mlbam"] for r in ss.parse_rows(_CSV, 2024)}
    assert 111111 not in rows


def test_parse_rows_survives_empty_and_junk():
    assert ss.parse_rows("", 2024) == []
    assert ss.parse_rows("   \n", 2024) == []
    assert ss.parse_rows("<html>error</html>", 2024) == []
    # A header with no data rows is legal, just empty.
    assert ss.parse_rows(_HEADER + "\n", 2024) == []


def test_num_coerces_and_fails_soft():
    assert ss._num("30.5") == 30.5
    assert ss._num(" 4.10 ") == 4.10
    assert ss._num("") is None
    assert ss._num(None) is None
    assert ss._num("n/a") is None


# --------------------------------------------------------------------------- #
# fetch: cache and fail-soft
# --------------------------------------------------------------------------- #
def test_fetch_raw_serves_cache_without_touching_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "CACHE_DIR", tmp_path)
    (tmp_path / "sprint_2024.csv").write_text(_CSV, encoding="utf-8")
    assert ss.fetch_raw(2024) == _CSV   # _no_network would explode on a fetch


def test_fetch_raw_writes_cache_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ss.urllib.request, "urlopen", lambda *a, **k: _Resp(_CSV))
    assert ss.fetch_raw(2024) == _CSV
    assert (tmp_path / "sprint_2024.csv").read_text(encoding="utf-8") == _CSV


def test_fetch_raw_falls_back_to_cache_on_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "CACHE_DIR", tmp_path)
    (tmp_path / "sprint_2024.csv").write_text(_CSV, encoding="utf-8")

    def _fail(*a, **k):
        raise ss.urllib.error.URLError("down")
    monkeypatch.setattr(ss.urllib.request, "urlopen", _fail)
    assert ss.fetch_raw(2024, force=True) == _CSV


def test_fetch_raw_never_clobbers_a_good_cache_with_an_error_page(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "CACHE_DIR", tmp_path)
    cached = tmp_path / "sprint_2024.csv"
    cached.write_text(_CSV, encoding="utf-8")
    monkeypatch.setattr(ss.urllib.request, "urlopen",
                        lambda *a, **k: _Resp("<html>503</html>"))
    assert ss.fetch_raw(2024, force=True) == _CSV
    assert cached.read_text(encoding="utf-8") == _CSV


def test_fetch_raw_returns_empty_when_there_is_nothing_to_fall_back_on(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "CACHE_DIR", tmp_path)

    def _fail(*a, **k):
        raise ss.urllib.error.URLError("down")
    monkeypatch.setattr(ss.urllib.request, "urlopen", _fail)
    assert ss.fetch_raw(2024) == ""     # fail-soft, never raises


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _build_two_seasons(monkeypatch):
    monkeypatch.setattr(ss, "fetch_raw", lambda year, force=False: _CSV)
    return ss.build(first=2023, last=2024)


def test_build_keys_by_mlbam_then_season(monkeypatch):
    p = _build_two_seasons(monkeypatch)
    assert set(p) == {"_meta", "names", "by_mlbam"}
    rec = p["by_mlbam"]["677951"]
    assert sorted(rec) == ["2023", "2024"]           # string season keys
    assert rec["2024"]["ft_s"] == 30.5
    # Identity lives in the top-level index, not repeated on every season.
    assert "mlbam" not in rec["2024"] and "name" not in rec["2024"]
    assert p["names"]["677951"] == "Witt Jr., Bobby"


def test_build_meta_counts_are_honest(monkeypatch):
    p = _build_two_seasons(monkeypatch)
    m = p["_meta"]
    assert m["first_season"] == 2023 and m["last_season"] == 2024
    assert m["years"] == [2023, 2024]
    assert m["rows_by_season"] == {"2023": 3, "2024": 3}   # the no-speed row is gone
    assert m["n_players"] == 3
    assert m["n_player_seasons"] == 6
    assert set(m["field_key"]) >= {"ft_s", "hp1", "runs", "bolts"}
    assert m["units"] == "ft/s"
    assert m["source"] and m["source_url"]


def test_meta_shape_matches_the_arm_feed():
    """The two athletic feeds land in one loader; drifting _meta keys break it."""
    arm = pytest.importorskip("savant_arm_strength")
    shared = {"source", "source_url", "generated_at", "first_season", "last_season",
              "years", "units", "field_key", "n_players", "n_player_seasons",
              "rows_by_season", "blind_spots"}
    doc = _doc()
    assert shared <= set(doc["_meta"])
    try:
        arm_meta = set(json.loads(arm.OUT.read_text(encoding="utf-8"))["_meta"])
    except (OSError, ValueError):
        pytest.skip("data/savant_arm.json not built")
    assert shared <= arm_meta


def test_build_is_fail_soft_when_every_season_is_empty(monkeypatch):
    monkeypatch.setattr(ss, "fetch_raw", lambda year, force=False: "")
    p = ss.build(first=2023, last=2024)
    assert p["by_mlbam"] == {} and p["_meta"]["n_players"] == 0


def test_current_season_waits_for_april():
    import datetime as dt
    assert ss.current_season(dt.date(2026, 2, 3)) == 2025
    assert ss.current_season(dt.date(2026, 4, 1)) == 2026


# --------------------------------------------------------------------------- #
# offline lookups
# --------------------------------------------------------------------------- #
@pytest.fixture
def _landed(tmp_path, monkeypatch):
    payload = {
        "_meta": {"first_season": 2023, "last_season": 2024},
        "names": {"677951": "Witt Jr., Bobby"},
        "by_mlbam": {"677951": {"2023": {"ft_s": 30.4, "pos": "SS"},
                                "2024": {"ft_s": 30.5, "pos": "SS"}}},
    }
    out = tmp_path / "savant_sprint.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(ss, "OUT", out)
    ss._payload.cache_clear()
    yield
    ss._payload.cache_clear()


def test_sprint_for_reads_the_landed_json(_landed):
    assert ss.sprint_for(677951, 2024)["ft_s"] == 30.5
    assert ss.sprint_for("677951", "2024") == ss.sprint_for(677951, 2024)
    assert sorted(ss.sprint_for(677951)) == ["2023", "2024"]
    assert ss.speed_for(677951, 2023) == 30.4
    assert ss.player_name(677951) == "Witt Jr., Bobby"


def test_offline_lookups_are_none_safe(_landed):
    assert ss.sprint_for(1, 2024) is None
    assert ss.sprint_for(1) == {}
    assert ss.sprint_for(677951, 1999) is None
    assert ss.speed_for(677951, 1999) is None
    assert ss.speed_for(1, 2024) is None
    assert ss.player_name(1) == ""


def test_missing_artifact_reads_as_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "OUT", tmp_path / "nope.json")
    ss._payload.cache_clear()
    try:
        assert ss.sprint_for(677951, 2024) is None
        assert ss.player_name(677951) == ""
    finally:
        ss._payload.cache_clear()


# --------------------------------------------------------------------------- #
# the landed artifact, when it is on disk
# --------------------------------------------------------------------------- #
def _doc():
    try:
        return json.loads(ss.OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip("data/savant_sprint.json not built")


def test_landed_covers_2015_through_the_current_season():
    d = _doc()
    m = d["_meta"]
    assert m["first_season"] == 2015
    assert m["last_season"] >= 2025
    seasons = set(m["rows_by_season"])
    assert {str(y) for y in range(2015, m["last_season"] + 1)} <= seasons
    # Every full season clears 400 players. 2020 was 60 games and still does.
    assert min(m["rows_by_season"].values()) >= 400


def test_landed_speeds_sit_in_the_physical_band():
    d = _doc()
    sp = [r["ft_s"] for yrs in d["by_mlbam"].values() for r in yrs.values()]
    assert len(sp) > 5000
    assert 20.0 <= min(sp) and max(sp) <= 32.0
    med = sorted(sp)[len(sp) // 2]
    assert 26.0 <= med <= 28.5, f"league median sprint speed {med} is off-book"


def test_landed_ids_are_mlbam_and_bolts_never_exceed_runs():
    d = _doc()
    for pid, yrs in d["by_mlbam"].items():
        assert pid.isdigit() and 100000 <= int(pid) <= 999999
        for r in yrs.values():
            if "bolts" in r and "runs" in r:
                assert r["bolts"] <= r["runs"]
