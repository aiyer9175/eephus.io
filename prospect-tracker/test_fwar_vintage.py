# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The frozen fWAR vintage builder and reader (fWAR label epoch, E3 part 1).

Offline: every fetch is a fake fetcher, every write goes to tmp_path, and the
scraper cache is booby-trapped so a builder that read a .cache payload fails.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

import fwar_vintage as FV
import saber_feed

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import build_fwar_vintage as BUILD  # noqa: E402

AFTER = dt.date(2026, 10, 5)


def _hit(pid, war, n=1, **extra):
    stat = {"war": war, "rar": 9.5, "batting": 1.0, "baseRunning": 0.5,
            "fielding": -0.25, "positional": 2.5, "wLeague": 0.1, "replacement": 5.0,
            "wSb": 0.3, "ubr": -0.4, "wGdp": 0.2, "woba": 0.321, "wRaa": 1.5,
            "wRc": 40.0, "wRcPlus": 104.0, "spd": 4.2}
    stat.update(extra)
    return {"player": {"id": pid, "fullName": f"h{pid}"}, "team": {"id": 116},
            "numTeams": n, "stat": stat}


def _pit(pid, war, n=1, **extra):
    stat = {"war": war, "rar": 9.0, "fip": 3.9, "xfip": 4.0, "ra9War": 1.2,
            "gmli": 0.9, "exli": 1.1, "pli": 0.95, "inli": 0.93, "eraMinus": 95.0,
            "fipMinus": 97.0, "md": 0.0, "sd": 0.0}
    stat.update(extra)
    return {"player": {"id": pid, "fullName": f"p{pid}"}, "team": {"id": 116},
            "numTeams": n, "stat": stat}


def _body(splits) -> bytes:
    return json.dumps({"copyright": "x", "stats": [{"splits": splits}]}).encode("utf-8")


def _season_payloads(season: int):
    hit = [_hit(1000 + i, round(0.1 * i, 3)) for i in range(12)]
    hit += [_hit(7, 1.25, n=1), _hit(7, 2.5, n=2)]        # a traded hitter: season total wins
    hit += [_hit(8, "1.5")]                               # a string WAR: refused to null
    pit = [_pit(2000 + i, round(0.2 * i, 3)) for i in range(10)]
    pit += [_pit(7, 0.4)]                                 # the two-way player
    return {"hitting": _body(hit), "pitching": _body(pit)}


class FakeFetch:
    def __init__(self, overrides=None):
        self.calls: list[str] = []
        self.overrides = overrides or {}

    def __call__(self, url):
        self.calls.append(url)
        group = "pitching" if "group=pitching" in url else "hitting"
        season = int(url.split("season=")[1].split("&")[0])
        if (season, group) in self.overrides:
            return self.overrides[(season, group)]
        return FV.FetchResponse(200, _season_payloads(season)[group])


@pytest.fixture(autouse=True)
def _small_feed(monkeypatch):
    """Small fake payloads, no pauses, no scraper cache, no memoised vintage."""
    monkeypatch.setattr(FV, "MIN_ROWS", 5)
    monkeypatch.setattr(FV, "_CACHE", None)

    def _trap(*a, **k):
        raise AssertionError("the vintage builder read the scraper cache")
    import scrapers
    monkeypatch.setattr(scrapers, "_fetch", _trap)
    yield


def _freeze(existing, seasons, fetch=None, today=AFTER, stamp="2026-10-05T12:00:00+00:00",
            **kw):
    return FV.freeze_seasons(existing, seasons, fetch=fetch or FakeFetch(), today=today,
                             now=lambda: stamp, pause=lambda s: None, **kw)


# --------------------------------------------------------------------------- refusals
def test_an_incomplete_season_is_refused_and_nothing_is_fetched():
    fetch = FakeFetch()
    with pytest.raises(FV.FreezeError, match="in progress"):
        _freeze(None, [2025, 2026], fetch=fetch, today=dt.date(2026, 9, 20))
    with pytest.raises(FV.FreezeError, match="has not been played"):
        _freeze(None, [2027], fetch=fetch)
    with pytest.raises(FV.FreezeError, match="regular-season end is not registered"):
        _freeze(None, [2027], fetch=fetch, today=dt.date(2027, 10, 5))
    assert fetch.calls == []
    # the last day of the regular season is still in progress; the day after is not
    assert FV.season_complete(2026, dt.date(2026, 9, 27))[0] is False
    assert FV.season_complete(2026, dt.date(2026, 9, 28))[0] is True


def test_a_frozen_season_is_never_overwritten():
    first = _freeze(None, [2024])
    fetch = FakeFetch()
    with pytest.raises(FV.FreezeError, match="never overwritten"):
        _freeze(first, [2024, 2025], fetch=fetch)
    assert fetch.calls == []
    # a new season beside the frozen one leaves the frozen block byte-identical
    both = _freeze(first, [2025], stamp="2026-10-06T00:00:00+00:00")
    assert both["seasons"]["2024"] == first["seasons"]["2024"]
    assert sorted(both["seasons"]) == ["2024", "2025"]
    # the escape hatch exists and is explicit
    again = _freeze(first, [2024], refreeze=True, stamp="2026-10-07T00:00:00+00:00")
    assert again["seasons"]["2024"]["fetched_at"] == "2026-10-07T00:00:00+00:00"


@pytest.mark.parametrize("resp, msg", [
    (FV.FetchResponse(503, b""), "HTTP 503"),
    (FV.FetchResponse(200, b"not json"), "unparseable"),
    (FV.FetchResponse(200, _body([])), "no rows"),
    (FV.FetchResponse(200, _body([_pit(1, 0.1)])), "under MIN_ROWS"),
    (FV.FetchResponse(200, _body([_pit(i, 0.1) for i in range(2000)])), "cap"),
])
def test_any_failed_call_fails_the_whole_run(resp, msg):
    fetch = FakeFetch({(2025, "pitching"): resp})
    with pytest.raises(FV.FreezeError, match=msg):
        _freeze(None, [2024, 2025], fetch=fetch)


def test_the_builder_fetches_both_groups_from_statsapi_and_never_the_cache():
    fetch = FakeFetch()
    _freeze(None, [2024, 2025], fetch=fetch)   # the autouse trap guards scrapers._fetch
    assert fetch.calls == [saber_feed.SABER_URLS[g].format(season=s)
                           for s in (2024, 2025) for g in ("hitting", "pitching")]
    assert all(u.startswith("https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics")
               for u in fetch.calls)


# --------------------------------------------------------------------------- the artifact
def test_fetched_at_url_group_and_hashes_are_recorded():
    blob = _freeze(None, [2025])
    sb = blob["seasons"]["2025"]
    for g in ("hitting", "pitching"):
        gb = sb[g]
        assert gb["fetched_at"] == "2026-10-05T12:00:00+00:00"
        assert gb["group"] == g and gb["status"] == "frozen" and gb["http_status"] == 200
        assert gb["url"] == saber_feed.SABER_URLS[g].format(season=2025)
        assert len(gb["raw_sha256"]) == 64 and len(gb["content_sha256"]) == 64
    assert sb["fetched_at"] == "2026-10-05T12:00:00+00:00"
    assert sb["basis"] == "fwar"
    assert blob["schema"] == FV.SCHEMA
    assert blob["vintage_id"].startswith("2026-10-05-") and len(blob["vintage_id"]) == 23
    assert FV.verify(blob) == []


def test_hashes_are_stable_and_name_the_content():
    a = _freeze(None, [2024, 2025])
    b = _freeze(None, [2025, 2024])
    assert a["vintage_id"] == b["vintage_id"]
    assert a["seasons"]["2025"]["content_sha256"] == b["seasons"]["2025"]["content_sha256"]
    # a JSON round trip (the committed file) keeps every hash
    rt = json.loads(json.dumps(a))
    assert FV.verify(rt) == []
    # one changed value moves the group, season and vintage hashes, and verify sees a tamper
    changed = FakeFetch({(2025, "pitching"): FV.FetchResponse(200, _body(
        [_pit(2000 + i, round(0.2 * i, 3)) for i in range(9)] + [_pit(2009, 9.9), _pit(7, 0.4)]))})
    c = _freeze(None, [2024, 2025], fetch=changed)
    assert c["seasons"]["2024"]["content_sha256"] == a["seasons"]["2024"]["content_sha256"]
    assert c["seasons"]["2025"]["content_sha256"] != a["seasons"]["2025"]["content_sha256"]
    assert c["vintage_id"] != a["vintage_id"]
    rt["seasons"]["2025"]["pitching"]["rows"]["2001"][0] = 5.0
    assert any("2025 pitching" in p for p in FV.verify(rt))


def test_rows_keep_the_feed_values_the_eb4_fields_and_the_pitching_fields():
    blob = _freeze(None, [2025])
    hit = blob["seasons"]["2025"]["hitting"]
    pit = blob["seasons"]["2025"]["pitching"]
    assert hit["fields"][:8] == ["war", "rar", "batting", "baseRunning", "fielding",
                                 "positional", "wLeague", "replacement"]
    for f in ("wSb", "ubr", "wGdp", "plateAppearances", "numTeams"):
        assert f in hit["fields"]
    assert pit["fields"] == list(saber_feed.PITCHING_FIELDS) + ["numTeams"]
    row = dict(zip(hit["fields"], hit["rows"]["7"]))
    assert row["war"] == 2.5 and row["numTeams"] == 2          # the season total, not a stint
    assert row["wSb"] == 0.3 and row["ubr"] == -0.4 and row["wGdp"] == 0.2
    assert row["plateAppearances"] is None                      # not carried: never invented
    assert dict(zip(hit["fields"], hit["rows"]["8"]))["war"] is None   # a string is refused
    assert hit["n_string_refused"] == 1 and hit["n_multi_team"] == 1
    prow = dict(zip(pit["fields"], pit["rows"]["2003"]))
    assert prow["fip"] == 3.9 and prow["gmli"] == 0.9 and prow["eraMinus"] == 95.0
    pres = FV.field_presence(blob)["2025"]
    assert pres["hitting"]["share"]["plateAppearances"] == 0.0
    assert pres["pitching"]["share"]["fip"] == 1.0


def test_write_is_atomic_and_load_reads_it_back(tmp_path):
    blob = _freeze(None, [2025])
    p = FV.write(blob, tmp_path / "fwar_vintage.json")
    assert not list(tmp_path.glob("*.tmp*"))
    assert FV.load(p) == blob
    assert p.read_bytes().endswith(b"\n") and b"\r\n" not in p.read_bytes()


# --------------------------------------------------------------------------- the reader
def test_the_reader_maps_serve_each_side_and_the_season_total():
    blob = _freeze(None, [2025])
    bat = FV.side_targets(blob, "bat")
    pit = FV.side_targets(blob, "pit")
    assert bat[(7, 2025)] == 2.5 and pit[(7, 2025)] == 0.4
    assert (8, 2025) not in bat                                  # refused WAR serves nothing
    tot = FV.season_totals(blob)
    assert tot[(7, 2025)] == pytest.approx(2.9)                  # two groups summed
    assert tot[(2003, 2025)] == pytest.approx(0.6)
    assert FV.fwar_seasons(blob) == [2025] and FV.mixed_seasons(blob) == []


def test_available_and_load_use_the_memo_seam(monkeypatch, tmp_path):
    monkeypatch.setattr(FV, "VINTAGE_PATH", tmp_path / "absent.json")
    assert FV.available() is False
    monkeypatch.setattr(FV, "_CACHE", {"seasons": {}})
    assert FV.available() is True and FV.load() == {"seasons": {}}


# --------------------------------------------------------------------------- the CLI
def test_the_cli_plans_without_network_or_write(tmp_path, capsys, monkeypatch):
    out = tmp_path / "v.json"
    monkeypatch.setattr(FV, "http_fetch", lambda url: pytest.fail("network in a plan"))
    assert BUILD.main(["--freeze", "2024-2025", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "calls 4" in text and "PLAN ONLY" in text
    assert not out.exists()
    assert BUILD.parse_seasons("2011,2013-2014") == [2011, 2013, 2014]


def test_the_vintage_never_ships():
    lines = (HERE / "deploy" / "data_exclude.txt").read_text(encoding="utf-8").splitlines()
    assert "fwar_vintage.json" in [ln.strip() for ln in lines]
    assert FV.VINTAGE_PATH.name == "fwar_vintage.json"
    assert FV.VINTAGE_PATH.parent.name == "data"
