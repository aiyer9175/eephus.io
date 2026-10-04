# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The season people ingest's contract, offline (Part 8 lane league_team_stats,
section 8).

Nothing here touches the network: the `http_get` seam answers with the 2026
people feed the lane saved on 2026-09-30 (trimmed to the fields the module
reads, test_fixtures/mlb_people/), and the panel is the 2026 season-line ids.
What is pinned: a complete season's feed is refused, and nothing is written,
when it gives a hand to under 90 percent of the panel rows or when no panel is
on disk; a live season's short feed is written and files a red; the TTL rule.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import mlb_people as MP

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "mlb_people"
PEOPLE = json.loads((FIX / "people_2026_trim.json").read_text(encoding="utf-8"))
PANEL = json.loads((FIX / "panel_2026_ids.json").read_text(encoding="utf-8"))
COMPLETE = date(2027, 1, 15)          # 2026 is complete on this date
LIVE = date(2026, 9, 1)


def _ts(y, m, d, h=12) -> float:
    return datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()


class FakeAPI:
    def __init__(self, blob=PEOPLE):
        self.blob, self.calls = blob, []

    def __call__(self, path, params):
        assert path == "sports/1/players" and params == {"season": 2026}
        self.calls.append(params)
        return copy.deepcopy(self.blob)


class Ledger:
    def __init__(self):
        self.rows = []

    def __call__(self, source, *, ok, n_rows=0, message="", import_fallback=True):
        self.rows.append({"source": source, "ok": ok, "n_rows": n_rows, "message": message})


def _short_feed(share_kept: float) -> dict:
    """The fixture with enough panel people removed to cover about `share_kept`."""
    ids = sorted(set(PANEL["hitting"]) | set(PANEL["pitching"]))
    drop = set(ids[: int(len(ids) * (1 - share_kept))])
    return {"people": [p for p in PEOPLE["people"] if p["id"] not in drop]}


def _panel_dir(tmp_path: Path) -> Path:
    d = tmp_path / "panel"
    d.mkdir()
    for g in ("hitting", "pitching"):
        blob = {"stats": [{"splits": [{"player": {"id": i}} for i in PANEL[g]]}]}
        (d / f"fa_statsapi_{g}_2026.json").write_text(json.dumps(blob), encoding="utf-8")
    return d


def test_parse_people_columns():
    rows = MP.parse_people(PEOPLE)
    assert len(rows) == len(PEOPLE["people"]) == 1512
    abbott = next(r for r in rows if r[0] == 671096)
    assert dict(zip(MP.COLUMNS, abbott)) == {"id": 671096, "name": "Andrew Abbott", "bats": "L",
                                             "throws": "L", "birth_date": "1999-06-01", "pos": "P"}
    with pytest.raises(MP.Refused):
        MP.parse_people({"people": []})


def test_fixture_feed_covers_the_panel():
    cov = MP.coverage(MP.parse_people(PEOPLE), PANEL)
    assert cov["rows"] == len(PANEL["hitting"]) + len(PANEL["pitching"])
    assert cov["share"] >= MP.MIN_PANEL_COVERAGE


def test_panel_rows_read_from_disk(tmp_path):
    d = _panel_dir(tmp_path)
    assert MP.panel_rows(2026, d) == PANEL
    assert MP.panel_rows(2025, d) is None


def test_complete_season_writes_and_records_ok(tmp_path):
    led = Ledger()
    doc = MP.load(2026, cache_dir=tmp_path / "c", panel_dir=_panel_dir(tmp_path),
                  today=COMPLETE, now=_ts(2027, 1, 15), http_get=FakeAPI(), record=led)
    assert doc["complete"] is True and doc["n_people"] == 1512
    assert (tmp_path / "c" / "people_2026.json").exists()
    assert [r["ok"] for r in led.rows] == [True]
    h = MP.hands(2026, tmp_path / "c")
    assert h[671096] == {"bats": "L", "throws": "L"}


def test_complete_season_under_ninety_percent_is_refused(tmp_path):
    feed = _short_feed(0.85)
    assert MP.coverage(MP.parse_people(feed), PANEL)["share"] < MP.MIN_PANEL_COVERAGE
    led = Ledger()
    with pytest.raises(MP.Refused, match="under the 90% floor"):
        MP.load(2026, cache_dir=tmp_path / "c", panel=PANEL, today=COMPLETE,
                http_get=FakeAPI(feed), record=led)
    assert not (tmp_path / "c").exists()
    assert [r["ok"] for r in led.rows] == [False]


def test_complete_season_above_ninety_percent_passes(tmp_path):
    feed = _short_feed(0.95)
    doc = MP.load(2026, cache_dir=tmp_path / "c", panel=PANEL, today=COMPLETE,
                  http_get=FakeAPI(feed), record=Ledger())
    assert MP.MIN_PANEL_COVERAGE <= doc["coverage"]["share"] < 1.0


def test_complete_season_with_no_panel_is_refused(tmp_path):
    empty = tmp_path / "nopanel"
    empty.mkdir()
    with pytest.raises(MP.Refused, match="no panel"):
        MP.load(2026, cache_dir=tmp_path / "c", panel_dir=empty, today=COMPLETE,
                http_get=FakeAPI(), record=Ledger())
    assert not (tmp_path / "c").exists()


def test_refusal_keeps_the_previous_file(tmp_path):
    MP.load(2026, cache_dir=tmp_path, panel=PANEL, today=COMPLETE, now=_ts(2027, 1, 15),
            http_get=FakeAPI(), record=Ledger())
    before = (tmp_path / "people_2026.json").read_bytes()
    with pytest.raises(MP.Refused):
        MP.load(2026, force=True, cache_dir=tmp_path, panel=PANEL, today=COMPLETE,
                http_get=FakeAPI(_short_feed(0.5)), record=Ledger())
    assert (tmp_path / "people_2026.json").read_bytes() == before


def test_live_season_short_feed_is_written_and_filed_red(tmp_path):
    led = Ledger()
    doc = MP.load(2026, cache_dir=tmp_path, panel=PANEL, today=LIVE, now=_ts(2026, 9, 1),
                  http_get=FakeAPI(_short_feed(0.5)), record=led)
    assert doc["complete"] is False
    assert (tmp_path / "people_2026.json").exists()
    assert [r["ok"] for r in led.rows] == [False] and "(live)" in led.rows[0]["message"]


def test_ttl_complete_never_refetched_live_daily(tmp_path):
    MP.load(2026, cache_dir=tmp_path / "c", panel=PANEL, today=COMPLETE, now=_ts(2027, 1, 15),
            http_get=FakeAPI(), record=Ledger())
    api = FakeAPI()
    MP.load(2026, cache_dir=tmp_path / "c", panel=PANEL, today=date(2032, 1, 1),
            now=_ts(2032, 1, 1), http_get=api, record=Ledger())
    assert api.calls == []

    t0 = _ts(2026, 9, 1, 8)
    MP.load(2026, cache_dir=tmp_path / "l", panel=PANEL, today=LIVE, now=t0,
            http_get=FakeAPI(), record=Ledger())
    api = FakeAPI()
    MP.load(2026, cache_dir=tmp_path / "l", panel=PANEL, today=LIVE, now=t0 + 23 * 3600,
            http_get=api, record=Ledger())
    assert api.calls == []
    MP.load(2026, cache_dir=tmp_path / "l", panel=PANEL, today=LIVE, now=t0 + 25 * 3600,
            http_get=api, record=Ledger())
    assert len(api.calls) == 1


def test_hands_never_fetches(tmp_path):
    with pytest.raises(MP.NotCached):
        MP.hands(2026, tmp_path)
