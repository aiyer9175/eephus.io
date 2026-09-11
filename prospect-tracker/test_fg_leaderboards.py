# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FanGraphs fetcher's contract, offline (owner decisions 13 and 14a).

Nothing here touches the network: every fetch goes through the `http_get` seam
with a synthetic body. What is pinned: a response is validated BEFORE it is
cached and a shape change is refused without touching the previous file; a
complete season is fetched once and a live one expires; readers never fetch;
the transport never spoofs a browser User-Agent; and no served module imports
the fetcher.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import fg_leaderboards as FG

ROOT = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Synthetic responses
# --------------------------------------------------------------------------

def _pit_row(i: int, season: int = 2025, **over) -> dict:
    row = {"xMLBAMID": 600000 + i, "playerid": 10000 + i, "Season": season,
           "TeamName": "DET", "teamid": 6, "IP": 60.1, "G": 60.0, "GS": 0.0, "TBF": 250.0,
           "IFFB": 6.0, "FB": 60.0, "HR": 7.0, "BB": 20.0, "IBB": 1.0, "HBP": 2.0,
           "SO": 65.0, "FIP": 3.9, "FIP-": 95.0, "ERA": 3.7, "WAR": 0.6, "RAR": 6.0,
           "Start-IP": None, "Relief-IP": 60.1, "gmLI": 1.1, "CFraming": 0.4,
           "PlayerName": "x", "pb_stuff": 101.0}
    row.update(over)
    return row


def _pit_blob(n: int = 500, season: int = 2025, **over) -> dict:
    data = [_pit_row(i, season) for i in range(n)]
    for k, v in over.items():
        data[0][k] = v
    return {"data": data, "totalCount": len(data), "dateRange": "", "sortStat": "WAR"}


def _fld_blob(season: int = 2025) -> dict:
    data = []
    for i in range(1000):
        pos = "C" if i < 100 else "SS"
        data.append({"xMLBAMID": 500000 + i, "playerid": 20000 + i, "Season": season,
                     "Pos": pos, "TeamName": "SEA", "teamid": 11, "Inn": 900.0,
                     "CFraming": (3.5 if pos == "C" else None), "OAA": 1})
    return {"data": data, "totalCount": len(data)}


def _pf_blob(season: int = 2025, **over) -> list:
    names = [n for n in FG.FG_CLUB_TO_TEAM_ID
             if n not in ("D-backs", "Indians", "Cleveland")]
    assert len(names) == 30
    rows = [{"Season": season, "Team": n, "Basic (5yr)": 100.0, "1yr": 100.0, "3yr": 100.0,
             "HR": 100.0, "SO": 100.0, "BB": 100.0, "IFFB": 100.0, "FIP": 99.5,
             "1B": 100.0} for n in names]
    rows[0].update(over)
    return rows


def _seam(body, calls: list, status: int = 200):
    raw = json.dumps(body).encode("utf-8")

    def get(url, params):
        calls.append((url, dict(params)))
        return status, raw, url + "?season=" + str(params.get("season"))
    return get


# --------------------------------------------------------------------------
# Validation refuses, never repairs
# --------------------------------------------------------------------------

def test_a_well_formed_pitching_page_is_kept_to_its_columns():
    rows = FG.validate_pitching(_pit_blob(), 2025)
    assert len(rows) == 500
    assert set(rows[0]) == set(FG.PITCHING_COLUMNS), "only the named columns are cached"


@pytest.mark.parametrize("mutate, why", [
    (lambda b: b["data"][3].pop("IFFB"), "a column went missing"),
    (lambda b: b["data"][3].update(Season=2024), "a row from another season"),
    (lambda b: b.update(totalCount=b["totalCount"] + 1), "the season did not fit one page"),
    (lambda b: b["data"][3].update(IFFB=900.0), "more infield flies than batters faced"),
    (lambda b: b["data"][3].update(xMLBAMID=b["data"][4]["xMLBAMID"]), "an id twice (split rows)"),
    (lambda b: [r.update(CFraming=None) for r in b["data"]], "framing column gone"),
    (lambda b: [r.update(IFFB=0.0) for r in b["data"]], "league infield-fly rate out of band"),
    (lambda b: b["data"][3].update(IP=None), "a required value is null"),
])
def test_pitching_shape_changes_are_refused(mutate, why):
    blob = _pit_blob()
    mutate(blob)
    with pytest.raises(FG.ShapeChanged):
        FG.validate_pitching(blob, 2025)


def test_park_factors_map_every_club_and_refuse_an_unknown_one():
    rows = FG.validate_park_factors(_pf_blob(), 2025)
    assert len({r["team_id"] for r in rows}) == 30
    with pytest.raises(FG.ShapeChanged, match="unmapped club"):
        FG.validate_park_factors(_pf_blob(Team="Sacramento"), 2025)
    with pytest.raises(FG.ShapeChanged, match="outside"):
        FG.validate_park_factors(_pf_blob(FIP=0.995), 2025)   # a decimal, not points
    with pytest.raises(FG.ShapeChanged, match="30"):
        FG.validate_park_factors(_pf_blob()[:29], 2025)


def test_every_name_a_club_has_carried_maps_to_one_franchise():
    """Cleveland is 'Indians' to 2021's table, 'Cleveland' in 2021 and
    'Guardians' after; all three are one StatsAPI id, and 2021 was the season a
    live pull refused, which is the refusal working."""
    ids = FG.FG_CLUB_TO_TEAM_ID
    assert ids["Indians"] == ids["Cleveland"] == ids["Guardians"] == 114
    assert len(set(ids.values())) == 30


def test_fielding_needs_catchers_with_framing():
    rows = FG.validate_fielding(_fld_blob(), 2025)
    assert sum(1 for r in rows if r["Pos"] == "C") == 100
    blob = _fld_blob()
    for r in blob["data"]:
        r["CFraming"] = None
    with pytest.raises(FG.ShapeChanged, match="CFraming"):
        FG.validate_fielding(blob, 2025)


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------

def test_fetch_validates_then_caches_and_a_complete_season_is_fetched_once(tmp_path):
    calls: list = []
    get = _seam(_pit_blob(), calls)
    doc = FG.fetch("pitching", 2025, cache_dir=tmp_path, http_get=get, today=date(2026, 9, 11))
    assert doc["complete"] is True and doc["season"] == 2025 and doc["n_rows"] == 500
    assert len(doc["raw_sha256"]) == 64 and doc["url"].startswith(FG.LEADERS_URL)
    again = FG.fetch("pitching", 2025, cache_dir=tmp_path, http_get=get)
    assert len(calls) == 1, "a complete season is never refetched without force"
    assert again["fetched_at"] == doc["fetched_at"]
    FG.fetch("pitching", 2025, cache_dir=tmp_path, http_get=get, force=True)
    assert len(calls) == 2


def test_a_live_season_expires_after_its_ttl(tmp_path):
    calls: list = []
    get = _seam(_pit_blob(season=2026), calls)
    doc = FG.fetch("pitching", 2026, cache_dir=tmp_path, http_get=get, today=date(2026, 9, 11))
    assert doc["complete"] is False
    FG.fetch("pitching", 2026, cache_dir=tmp_path, http_get=get)
    assert len(calls) == 1, "inside the TTL the live file is reused"
    p = FG.cache_path("pitching", 2026, tmp_path)
    old = json.loads(p.read_text(encoding="utf-8"))
    old["fetched_at"] = (datetime.now(timezone.utc)
                         - timedelta(seconds=FG.LIVE_TTL_S + 60)).isoformat(timespec="seconds")
    p.write_text(json.dumps(old), encoding="utf-8")
    FG.fetch("pitching", 2026, cache_dir=tmp_path, http_get=get)
    assert len(calls) == 2, "an expired live file is refetched"


def test_a_refused_response_leaves_the_previous_cache_untouched(tmp_path):
    calls: list = []
    FG.fetch("pitching", 2026, cache_dir=tmp_path, http_get=_seam(_pit_blob(season=2026), calls))
    p = FG.cache_path("pitching", 2026, tmp_path)
    before = p.read_bytes()
    bad = _pit_blob(season=2026)
    bad["data"][0].pop("IFFB")
    with pytest.raises(FG.ShapeChanged):
        FG.fetch("pitching", 2026, cache_dir=tmp_path, http_get=_seam(bad, calls), force=True)
    assert p.read_bytes() == before
    with pytest.raises(RuntimeError, match="HTTP 403"):
        FG.fetch("pitching", 2026, cache_dir=tmp_path, force=True,
                 http_get=_seam({"x": 1}, calls, status=403))
    assert p.read_bytes() == before


def test_readers_read_the_cache_and_never_fetch(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a reader reached the network")
    monkeypatch.setattr(FG, "_http_get", boom)
    with pytest.raises(FG.NotCached):
        FG.pitcher_iffb(2025, tmp_path)
    calls: list = []
    FG.fetch("pitching", 2025, cache_dir=tmp_path, http_get=_seam(_pit_blob(), calls))
    FG.fetch("park_factors", 2025, cache_dir=tmp_path, http_get=_seam(_pf_blob(), calls))
    FG.fetch("fielding", 2025, cache_dir=tmp_path, http_get=_seam(_fld_blob(), calls))
    assert FG.pitcher_iffb(2025, tmp_path)[600000] == 6.0
    assert FG.pitcher_framing(2025, tmp_path)[600000] == pytest.approx(0.4)
    pf = FG.fip_park_factors(2025, tmp_path)
    assert len(pf) == 30 and all(v == pytest.approx(0.995) for v in pf.values()), "points -> decimal"
    assert FG.catcher_framing(2025, tmp_path)[500000] == pytest.approx(3.5)
    assert set(FG.catcher_framing(2025, tmp_path)) == {500000 + i for i in range(100)}


def test_season_complete_is_november_first():
    assert FG.season_complete(2026, date(2026, 10, 31)) is False
    assert FG.season_complete(2026, date(2026, 11, 1)) is True
    assert FG.season_complete(2025, date(2026, 3, 1)) is True


# --------------------------------------------------------------------------
# Transport and blast radius
# --------------------------------------------------------------------------

def test_the_transport_never_spoofs_a_browser_user_agent(monkeypatch):
    """A spoofed browser User-Agent is what draws FanGraphs' Cloudflare
    challenge; the default client passes (measured 2026-09-09 and 2026-09-11)."""
    import requests
    seen = {}

    class R:
        status_code, content, url = 200, b"[]", "u"

    def fake_get(url, **kw):
        seen.update(kw)
        return R()
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(FG, "MIN_INTERVAL_S", 0.0)
    FG._http_get(*FG.request_for("pitching", 2025))
    assert "headers" not in seen, "no header override, so no User-Agent spoof"
    monkeypatch.undo()
    assert FG.MIN_INTERVAL_S >= 1.0, "one request per second at most"


def test_one_request_returns_a_whole_season():
    url, params = FG.request_for("pitching", 2025)
    assert url == FG.LEADERS_URL and params["stats"] == "pit" and params["qual"] == 0
    assert params["season"] == params["season1"] == 2025 and params["pageitems"] >= 2500
    assert FG.request_for("fielding", 2025)[1]["stats"] == "fld"
    url, params = FG.request_for("park_factors", 2025)
    assert url == FG.GUTS_URL and params == {"type": "pf", "teamid": 0, "season": 2025}


def test_no_served_module_imports_the_fetcher():
    """The FanGraphs inputs feed the replica eval and nothing on the site. A
    served reader is a separate, measured change, and this is where it shows."""
    allowed = {"fg_leaderboards.py", "test_fg_leaderboards.py", "fwar_replica_eval.py",
               "test_fwar_frame.py"}
    pat = re.compile(r"^\s*(import|from)\s+fg_leaderboards\b|import_module\(\s*['\"]fg_leaderboards",
                     re.M)
    hits = []
    for p in list(ROOT.glob("*.py")) + list(ROOT.glob("tools/*.py")) + list(ROOT.glob("scripts/*.py")):
        if p.name in allowed:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(text):
            hits.append(str(p.relative_to(ROOT)))
    assert not hits, f"fg_leaderboards imported by {hits}"
