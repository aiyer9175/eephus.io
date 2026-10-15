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


def _line(pid, pa, n=1):
    return {"player": {"id": pid, "fullName": f"h{pid}"}, "team": {"id": 116},
            "numTeams": n, "stat": {"plateAppearances": pa, "atBats": max(pa - 5, 0)}}


def _season_payloads(season: int):
    hit = [_hit(1000 + i, round(0.1 * i, 3)) for i in range(12)]
    hit += [_hit(7, 1.25, n=1), _hit(7, 2.5, n=2)]        # a traded hitter: season total wins
    hit += [_hit(8, "1.5")]                               # a string WAR: refused to null
    pit = [_pit(2000 + i, round(0.2 * i, 3)) for i in range(10)]
    pit += [_pit(7, 0.4)]                                 # the two-way player
    lines = [_line(1000 + i, 10 * i) for i in range(12)]   # 1000 has 0 PA: zero, not null
    lines += [_line(7, 400, n=2), _line(8, 33)]            # the traded hitter's season total
    lines += [_line(9, 4)]                                 # a line with no sabermetrics row
    return {"hitting": _body(hit), "pitching": _body(pit), "pa_line": _body(lines)}


class FakeFetch:
    def __init__(self, overrides=None):
        self.calls: list[str] = []
        self.overrides = overrides or {}

    def __call__(self, url):
        self.calls.append(url)
        group = ("pa_line" if "stats=season&" in url
                 else "pitching" if "group=pitching" in url else "hitting")
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
    assert fetch.calls == [u.format(season=s) for s in (2024, 2025)
                           for u in (saber_feed.SABER_URLS["hitting"], FV.PA_LINE_URL,
                                     saber_feed.SABER_URLS["pitching"])]
    assert all(u.startswith("https://statsapi.mlb.com/api/v1/stats?stats=")
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
    assert row["plateAppearances"] == 400                       # the season line's total
    assert dict(zip(hit["fields"], hit["rows"]["1000"]))["plateAppearances"] == 0
    assert dict(zip(hit["fields"], hit["rows"]["8"]))["war"] is None   # a string is refused
    assert dict(zip(hit["fields"], hit["rows"]["8"]))["plateAppearances"] == 33
    assert hit["n_string_refused"] == 1 and hit["n_multi_team"] == 1
    pj = hit["pa_join"]
    assert pj["url"] == FV.PA_LINE_URL.format(season=2025) and pj["http_status"] == 200
    assert len(pj["raw_sha256"]) == 64 and pj["fetched_at"] == "2026-10-05T12:00:00+00:00"
    assert pj["n_rows"] == 14 and pj["n_joined"] == 14 and pj["unjoined_ids"] == []
    assert pj["n_lines_not_in_rows"] == 1                       # id 9 has a line, no row
    assert pj["pa_sum_rows"] == sum(10 * i for i in range(12)) + 400 + 33
    assert pj["pa_sum_lines"] == pj["pa_sum_rows"] + 4
    prow = dict(zip(pit["fields"], pit["rows"]["2003"]))
    assert prow["fip"] == 3.9 and prow["gmli"] == 0.9 and prow["eraMinus"] == 95.0
    pres = FV.field_presence(blob)["2025"]
    assert pres["hitting"]["share"]["plateAppearances"] == 1.0
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
    assert "calls 6 (at most)" in text and "PLAN ONLY" in text
    assert FV.PA_LINE_URL.format(season=2025) in text
    assert not out.exists()
    assert BUILD.parse_seasons("2011,2013-2014") == [2011, 2013, 2014]


def test_the_vintage_never_ships():
    lines = (HERE / "deploy" / "data_exclude.txt").read_text(encoding="utf-8").splitlines()
    assert "fwar_vintage.json" in [ln.strip() for ln in lines]
    assert FV.VINTAGE_PATH.name == "fwar_vintage.json"
    assert FV.VINTAGE_PATH.parent.name == "data"


# --------------------------------------------------------------------------- pre-2011 (E3 part 5)
_EMPTY = FV.FetchResponse(200, b'{"copyright": "x", "stats": []}')


def test_the_pre_2011_path_accepts_2000_to_2010_in_22_calls_pitching_first():
    fetch = FakeFetch()
    blob = _freeze(None, range(2000, 2011), fetch=fetch)
    assert len(fetch.calls) == 33                     # O4's 22 plus one PA line per hitting group
    assert "group=pitching" in fetch.calls[0] and "season=2000" in fetch.calls[0]   # the probe
    assert [("pitching" in u) for u in fetch.calls[:2]] == [True, False]
    assert sorted(blob["seasons"], key=int) == [str(s) for s in range(2000, 2011)]
    with pytest.raises(FV.FreezeError, match="before the first accepted season 2000"):
        _freeze(None, [1999])


def test_an_empty_pre_2011_pitching_answer_is_recorded_absent_with_its_response():
    over = {(s, "pitching"): _EMPTY for s in range(2000, 2011)}
    blob = _freeze(None, list(range(2009, 2011)) + [2011], fetch=FakeFetch(over))
    gb = blob["seasons"]["2009"]["pitching"]
    assert gb["status"] == "absent" and gb["rows"] == {} and gb["n_rows"] == 0
    assert gb["http_status"] == 200 and gb["response"] == _EMPTY.body.decode()
    assert gb["response_truncated"] is False and len(gb["raw_sha256"]) == 64
    assert gb["fetched_at"] and gb["url"].endswith("limit=2000") and "season=2009" in gb["url"]
    assert blob["seasons"]["2009"]["hitting"]["status"] == "frozen"
    assert blob["seasons"]["2009"]["basis"] == "mixed"
    assert blob["seasons"]["2011"]["basis"] == "fwar"
    assert FV.verify(blob) == []
    # the reader serves fWAR only on fwar seasons; the stamp says mixed for a cohort touching 2009
    assert FV.fwar_seasons(blob) == [2011] and FV.mixed_seasons(blob) == [2009, 2010]
    assert not any(s == 2009 for _, s in FV.side_targets(blob, "bat"))
    assert FV.war_basis([2011], blob) == "fwar"
    assert FV.war_basis([2009, 2011], blob) == "mixed"
    assert FV.war_basis([2008], blob) == "mixed"            # never recorded is not fwar
    # an absent block is frozen like any other: never refetched, never overwritten
    with pytest.raises(FV.FreezeError, match="never overwritten"):
        _freeze(blob, [2009])
    # both groups absent: the season's basis is 'absent'
    both = {(2005, g): _EMPTY for g in ("pitching", "hitting")}
    assert _freeze(None, [2005], fetch=FakeFetch(both))["seasons"]["2005"]["basis"] == "absent"


def test_only_a_clean_empty_answer_means_absent():
    with pytest.raises(FV.FreezeError, match="no rows"):            # 2011+: empty is a failure
        _freeze(None, [2011], fetch=FakeFetch({(2011, "pitching"): _EMPTY}))
    with pytest.raises(FV.FreezeError, match="HTTP 404"):           # pre-2011 non-200 fails
        _freeze(None, [2005], fetch=FakeFetch({(2005, "pitching"): FV.FetchResponse(404, b"")}))
    with pytest.raises(FV.FreezeError, match="under MIN_ROWS"):      # partial fails
        _freeze(None, [2005], fetch=FakeFetch(
            {(2005, "pitching"): FV.FetchResponse(200, _body([_pit(1, 0.1)]))}))


def test_the_rule_is_written_into_the_builder_docstring():
    doc = FV.__doc__
    assert "THE PRE-2011 PATH" in doc and "22" in doc and "war_basis: mixed" in doc
    assert "PITCHING FIRST" in doc and "RECORDED AS ABSENT" in doc
    assert "--freeze 2000-2026" in FV.BUILD_CMD


# --------------------------------------------------------------------------- plate appearances (2026-10-15)
@pytest.mark.parametrize("resp, msg", [
    (FV.FetchResponse(503, b""), "PA line: HTTP 503"),
    (FV.FetchResponse(200, b"not json"), "PA line: unparseable"),
    (FV.FetchResponse(200, _body([])), "PA line: the feed returned no rows"),
])
def test_a_failed_pa_line_fails_the_whole_run(resp, msg):
    with pytest.raises(FV.FreezeError, match=msg):
        _freeze(None, [2025], fetch=FakeFetch({(2025, "pa_line"): resp}))


def test_pa_from_lines_resolves_totals_sums_stints_and_refuses_the_rest():
    lines = [_line(1, 100), _line(2, 300, n=2), _line(2, 120), _line(2, 180),
             _line(3, 50), _line(3, 70),                 # two stints and no total: summed
             _line(4, 10, n=2), _line(4, 11, n=2),       # two totals: refused
             dict(_line(5, 12), stat={"plateAppearances": "12"})]   # a string PA: refused
    pa, rec = FV.pa_from_lines(lines)
    assert pa == {1: 100, 2: 300, 3: 120}
    assert rec["n_summed"] == 1 and rec["refused_ids"] == [4, 5]
    assert rec["n_line_rows"] == 9 and rec["n_line_players"] == 5 and rec["pa_sum_lines"] == 520


def test_apply_pa_moves_only_the_pa_column_and_rehashes():
    blob = _freeze(None, [2025])
    hit = blob["seasons"]["2025"]["hitting"]
    i = hit["fields"].index("plateAppearances")
    bare = dict(hit, rows={m: v[:i] + [None] + v[i + 1:] for m, v in hit["rows"].items()})
    bare.pop("pa_join")
    bare["content_sha256"] = FV.group_content_sha(bare)
    again = FV.apply_pa(bare, {7: 400}, {"pa_sum_lines": 400})
    assert again["content_sha256"] != bare["content_sha256"]
    for m, v in again["rows"].items():
        assert v[:i] + v[i + 1:] == bare["rows"][m][:i] + bare["rows"][m][i + 1:]
    assert again["rows"]["7"][i] == 400 and again["rows"]["1000"][i] is None
    assert len(again["pa_join"]["unjoined_ids"]) == 13
    assert FV.apply_pa({"status": "absent", "rows": {}}, {}, {}) == {"status": "absent", "rows": {}}


def test_war_lineage_chains_only_war_identical_amendments():
    blob = {"vintage_id": "c", "amendments": [
        {"previous_vintage_id": "a", "vintage_id": "b", "war_identical": True},
        {"previous_vintage_id": "b", "vintage_id": "c", "war_identical": True}]}
    assert FV.war_lineage(blob) == ["c", "b", "a"]
    blob["amendments"][0]["war_identical"] = False
    assert FV.war_lineage(blob) == ["c", "b"]
    assert FV.war_lineage({"vintage_id": "x"}) == ["x"]


def test_the_committed_vintage_carries_pa_on_every_hitting_row():
    if not FV.VINTAGE_PATH.exists():
        pytest.skip("needs data/fwar_vintage.json")
    blob = json.loads(FV.VINTAGE_PATH.read_text(encoding="utf-8"))
    assert FV.verify(blob) == []
    pres = FV.field_presence(blob)
    assert all(pres[str(s)]["hitting"]["share"]["plateAppearances"] == 1.0
               for s in range(2011, 2027))
    am = blob["amendments"][-1]
    assert am["task"] == "EWAR_P0_VINTAGE_PA" and am["war_identical"] is True
    assert am["previous_vintage_id"] == "2026-10-02-0341299c20ec"
    assert FV.war_lineage(blob) == [blob["vintage_id"], "2026-10-02-0341299c20ec"]
    for s, lg in am["league_pa"].items():
        assert lg["pa_rows"] == lg["pa_lines"] == lg["pa_teams"] and lg["n_teams"] == 30, s
