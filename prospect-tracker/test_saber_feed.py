# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""saber_feed: the one loader for FanGraphs' served WAR components."""
from __future__ import annotations

import pytest

import saber_feed as S


def _row(pid, n=1, **stat):
    return {"player": {"id": pid, "fullName": f"p{pid}"}, "numTeams": n, "stat": stat}


def test_a_percentage_string_is_never_a_run_value():
    assert S.run_value("1.000") is None
    assert S.run_value(6.41) == pytest.approx(6.41)
    assert S.run_value(True) is None
    assert S.run_value(float("nan")) is None


def test_a_stint_group_resolves_to_its_unique_season_total():
    rows, amb, multi = S.resolve_groups([_row(1, 1, fielding=1.0), _row(1, 2, fielding=3.0)])
    assert rows[1]["stat"]["fielding"] == 3.0 and not amb and multi == 1


def test_two_season_totals_refuse_the_id():
    rows, amb, _ = S.resolve_groups([_row(1, 2, fielding=1.0), _row(1, 2, fielding=3.0)])
    assert 1 not in rows and amb == [1]


def test_the_framing_residual_is_rar_minus_the_six_components():
    st = {"batting": -16.19, "baseRunning": -2.62, "fielding": 5.49, "positional": 8.83,
          "wLeague": 1.27, "replacement": 13.77, "rar": 31.55}
    assert S.framing_residual(st) == pytest.approx(21.00, abs=0.01)
    st.pop("wLeague")
    assert S.framing_residual(st) is None


def test_the_hitter_board_reads_the_same_url():
    import hitter_export
    assert hitter_export._SABER_URL == S.SABER_URL


# --------------------------------------------------------------------------
# the pitching group (fWAR label epoch precondition E3 part 2), offline
# --------------------------------------------------------------------------

def test_the_hitting_url_and_key_are_unchanged_and_pitching_sits_beside_them():
    assert S.SABER_URL == ("https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics"
                           "&group=hitting&season={season}&sportId=1&playerPool=All&limit=2000")
    assert S.cache_key(2025) == "statsapi_saber_hitting_2025"
    assert S.SABER_URLS["hitting"] is S.SABER_URL
    assert S.SABER_PITCHING_URL == S.SABER_URL.replace("group=hitting", "group=pitching")
    assert S.cache_key(2025, "pitching") == S.pitching_cache_key(2025) == "statsapi_saber_pitching_2025"
    with pytest.raises(ValueError):
        S.cache_key(2025, "fielding")


def _pit(pid, n=1, **stat):
    return {"player": {"id": pid, "fullName": f"p{pid}"}, "team": {"id": 116},
            "numTeams": n, "stat": stat}


_PIT_PAYLOAD = {"copyright": "x", "stats": [{"splits": [
    _pit(669373, war=6.69904, rar=59.5996, fip=2.44913, xfip=2.664, ra9War=7.11358,
         gmli=0.872581, exli=1.23344, pli=0.946464, inli=0.939099, eraMinus=53.5967,
         fipMinus=57.2276, md=0.0, sd=0.0),
    _pit(518876, 2, war=3.173633, rar=30.38166, fip=3.76),
    _pit(1, war="1.5", rar=10.0),              # a string WAR: refused, row dropped
    _pit(2, rar=3.0),                          # no WAR at all: dropped before grouping
]}]}


def test_the_pitching_reader_keeps_the_feed_values_and_refuses_strings(monkeypatch):
    import json
    seen = {}

    def fake_fetch(url, key, accept_json=False):
        seen.update(url=url, key=key)
        return type("FR", (), {"status": 200, "body": json.dumps(_PIT_PAYLOAD)})()
    import scrapers
    monkeypatch.setattr(scrapers, "_fetch", fake_fetch)
    meta = S.load_pitching_components(2025)
    assert seen == {"url": S.SABER_PITCHING_URL.format(season=2025),
                    "key": "statsapi_saber_pitching_2025"}
    v = meta["values"]
    assert set(v) == {669373, 518876}
    sk = v[669373]
    assert sk["war"] == 6.69904 and sk["fip"] == 2.44913 and sk["gmli"] == 0.872581
    assert sk["eraMinus"] == 53.5967 and sk["md"] == 0.0 and sk["num_teams"] == 1
    assert v[518876]["num_teams"] == 2 and v[518876]["xfip"] is None
    assert meta["n_rows"] == 4 and meta["n_players"] == 2 and meta["n_multi_team"] == 1
    assert meta["group"] == "pitching"


def test_the_pitching_reader_returns_empty_meta_on_a_failed_fetch(monkeypatch):
    import scrapers
    monkeypatch.setattr(scrapers, "_fetch", lambda url, key, accept_json=False:
                        type("FR", (), {"status": 503, "body": ""})())
    meta = S.load_pitching_components(2025)
    assert meta["values"] == {} and meta["n_rows"] == 0


def test_the_hitting_fetch_still_reads_the_hitting_url_and_key(monkeypatch):
    import json
    seen = {}

    def fake_fetch(url, key, accept_json=False):
        seen.update(url=url, key=key, accept_json=accept_json)
        return type("FR", (), {"status": 200, "body": json.dumps(
            {"stats": [{"splits": [_row(7, 1, fielding=1.25, rar=3.0, war=0.4)]}]})})()
    import scrapers
    monkeypatch.setattr(scrapers, "_fetch", fake_fetch)
    meta = S.load_components(2024)
    assert seen == {"url": S.SABER_URL.format(season=2024), "key": "statsapi_saber_hitting_2024",
                    "accept_json": True}
    assert meta["values"][7]["fld"] == 1.25 and meta["values"][7]["war"] == 0.4


def test_parse_splits_reads_every_body_shape():
    import json
    body = json.dumps(_PIT_PAYLOAD)
    assert len(S.parse_splits(body)) == 4
    assert len(S.parse_splits(body.encode("utf-8"))) == 4
    assert len(S.parse_splits(_PIT_PAYLOAD)) == 4
    assert S.parse_splits('{"copyright": "x", "stats": []}') == []
