# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Offline tests for savant_arm_strength. No network: every test feeds fixture
CSV text straight to the parser, or monkeypatches fetch_raw."""
from __future__ import annotations

import savant_arm_strength as sa

# Trimmed from the real 2025 response. Row 1 is Salvador Perez, whose presence
# is the proof that primary_position=2 does not mean the throws came from behind
# the plate. Row 2 covers a player with reads at two positions plus the INF
# rollup. Row 3 has a blank primary_position_name, which the code map fills.
HEADER = ('"fielder_name","player_id","team_name","primary_position",'
          '"primary_position_name","total_throws","total_throws_1b",'
          '"total_throws_2b","total_throws_3b","total_throws_ss",'
          '"total_throws_lf","total_throws_cf","total_throws_rf",'
          '"total_throws_inf","total_throws_of","max_arm_strength","arm_1b",'
          '"arm_2b","arm_3b","arm_ss","arm_lf","arm_cf","arm_rf","arm_inf",'
          '"arm_of","arm_overall"')
FIXTURE = "\n".join([
    HEADER,
    '"Perez, Salvador","521692","NA","2",,"114","114","0","0","0","0","0","0",'
    '"0","0","70.4","70.2",,,,,,,,,"70.2"',
    '"Turner, Justin","457759","NA","3","Third Baseman","124","119","0","5",'
    '"0","0","0","0","5","0","75.7","73.8",,"74.9",,,,,"74.1",,"73.8"',
    '"Nobody, Blank","999001","NA","6",,"200","0","0","0","200","0","0","0",'
    '"200","0","88.1",,,,"84.2",,,,"84.2",,"84.2"',
]) + "\n"


def test_parse_shape_and_stamped_season():
    rows = sa.parse_rows(FIXTURE, 2025)
    assert len(rows) == 3
    r = rows[0]
    assert r["mlbam"] == 521692
    # The CSV carries no year column at all, so the season must come from us.
    assert r["season"] == 2025
    assert r["name"] == "Perez, Salvador"
    assert r["all"] == 70.2
    assert r["max"] == 70.4
    assert r["n"] == 114


def test_per_position_split_is_sparse():
    rows = {r["mlbam"]: r for r in sa.parse_rows(FIXTURE, 2025)}
    perez = rows[521692]
    # Only positions he actually threw from appear; zero-throw columns are dropped.
    assert perez["arm"] == {"1B": 70.2}
    assert perez["thr"] == {"1B": 114}
    turner = rows[457759]
    assert turner["arm"] == {"1B": 73.8, "3B": 74.9, "INF": 74.1}
    assert turner["thr"] == {"1B": 119, "3B": 5, "INF": 5}


def test_primary_position_name_falls_back_to_code():
    rows = {r["mlbam"]: r for r in sa.parse_rows(FIXTURE, 2025)}
    # Blank primary_position_name, present in the live feed for catchers.
    assert rows[521692]["primary"] == "Catcher"
    assert rows[999001]["primary"] == "Shortstop"
    assert rows[457759]["primary"] == "Third Baseman"  # given name wins


def test_build_url_uses_year_not_season():
    # The whole point. `season=` is accepted and silently ignored by Savant, so
    # a URL carrying it would return the default year under every loop index.
    url = sa.build_url(2021)
    assert "year=2021" in url
    assert "season=" not in url
    assert sa.build_url(2020) != sa.build_url(2021)


def test_build_stamps_each_year_distinctly(monkeypatch):
    # Same bytes every call, exactly what the `season=` bug would produce. The
    # keys must still be the requested years, because we stamp them.
    monkeypatch.setattr(sa, "fetch_raw", lambda year, force=False: FIXTURE)
    payload = sa.build(first=2023, last=2025)
    assert set(payload["by_mlbam"]["521692"]) == {"2023", "2024", "2025"}
    assert payload["_meta"]["rows_by_season"] == {"2023": 3, "2024": 3, "2025": 3}
    assert payload["_meta"]["n_players"] == 3
    assert payload["_meta"]["n_player_seasons"] == 9


def test_meta_keys(monkeypatch):
    monkeypatch.setattr(sa, "fetch_raw", lambda year, force=False: FIXTURE)
    meta = sa.build(first=2024, last=2025)["_meta"]
    for key in ("source", "source_url", "generated_at", "first_season",
                "last_season", "years", "rows_by_season", "n_players",
                "n_player_seasons", "n_player_position_reads"):
        assert key in meta, key
    assert meta["years"] == [2024, 2025]
    assert meta["units"] == "mph"


def test_fail_soft_on_bad_payload(monkeypatch):
    for junk in ("", "   ", "<html><body>404 not found</body></html>",
                 "no,such,columns\n1,2,3\n"):
        assert sa.parse_rows(junk, 2025) == []
    # A whole season failing must not abort the loop or the payload.
    def flaky(year, force=False):
        return FIXTURE if year == 2025 else ""
    monkeypatch.setattr(sa, "fetch_raw", flaky)
    payload = sa.build(first=2023, last=2025)
    assert payload["_meta"]["rows_by_season"] == {"2023": 0, "2024": 0, "2025": 3}
    assert payload["_meta"]["years"] == [2025]
    assert set(payload["by_mlbam"]["521692"]) == {"2025"}


def test_fail_soft_on_partial_rows():
    # A row with an unparseable player_id is skipped, the rest survive.
    broken = "\n".join([HEADER,
                        '"Bad, Row","notanid","NA","6",,"1",,,,,,,,,,,,,,,,,,,,',
                        FIXTURE.splitlines()[1]]) + "\n"
    rows = sa.parse_rows(broken, 2025)
    assert [r["mlbam"] for r in rows] == [521692]


def test_arm_for_offline_lookup(monkeypatch):
    monkeypatch.setattr(sa, "_payload", lambda: {
        "by_mlbam": {"457759": {"2025": {"all": 73.8, "arm": {"1B": 73.8, "3B": 74.9}}}},
        "names": {"457759": "Turner, Justin"},
    })
    assert sa.arm_for(457759, 2025, "3B") == 74.9
    assert sa.arm_for(457759, 2025, "ss") is None       # not thrown from
    assert sa.arm_for(111, 2025, "3B") is None          # unknown player
    assert sa.arm_for(111, 2025) == {}
    assert sa.arm_for(457759, 2025)["all"] == 73.8
    assert sa.player_name(457759) == "Turner, Justin"
