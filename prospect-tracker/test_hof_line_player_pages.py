# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Hall of Fame line on MLB player pages (wiring W05, task Q9_25).

The /projections/#player= overview prints one line for a player on the /hof/
shelf's Cooperstown Watch or Not Yet Eligible band: career WAR, WAR7, JAWS,
WAA+, WAR ink and the band, linking to /hof/, on the shelf's B-Ref bWAR basis.

What is pinned:
  (a) the line's numbers ARE the shelf's numbers for the same B-Ref id, copied
      verbatim, joined to MLBAM through the war_daily ids (no name matching);
  (b) only the two bands with live players join; the Eligible band never does;
  (c) a shelf on any other WAR basis, a missing shelf or a missing bridge
      prints no line rather than a mislabelled one;
  (d) no JAWS standard, position average or forecast is printed, and the line
      links to /hof/ and says Hall of Fame (AWARDS_PLAN section 3);
  (e) the served data/mlb_player_detail.json, when it carries the line, agrees
      with data/hof_board.json row for row (gitignored and rebuilt nightly, so
      this layer skips when the artifact predates the line).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import hof_data
import mlb_player_export as mpe

ROOT = Path(__file__).parent
DETAIL = ROOT / "data" / "mlb_player_detail.json"
SHELF = ROOT / "data" / "hof_board.json"
JS = ROOT / "assets" / "projections.js"

_BASIS = {"war": "Baseball-Reference bWAR, war_daily, the same file they publish from"}


def _row(pid, name, war, war7, jaws, waa_pos, ink, first, last, seasons):
    return {"id": pid, "name": name, "first": first, "last": last, "seasons": seasons,
            "war": war, "waa": waa_pos - 0.1, "war7": war7, "jaws": jaws,
            "waa_pos": waa_pos, "ink": ink, "pos": "OF",
            "pos_basis": "fielding_components", "monitor": None, "standards": None,
            "induction": "none", "induction_year": None, "induction_route": None}


_SHELF_FIX = {
    "basis": _BASIS,
    "leaderboard": [_row("ruthba01", "Babe Ruth", 182.6, 84.4, 133.5, 134.5, 47.0,
                         1914, 1935, 22)],
    "watch": [_row("troutmi01", "Mike Trout", 91.7, 64.8, 78.2, 66.0, 21.0,
                   2011, 2026, 16),
              _row("nobodyx01", "No Bridge", 30.1, 25.0, 27.6, 10.0, 0.0,
                   2014, 2026, 13)],
    "not_yet_eligible": [_row("pujolal01", "Albert Pujols", 101.2, 61.7, 81.4,
                              70.1, 23.0, 2001, 2022, 22)],
}
_XWALK_FIX = {"545361": "troutmi01", "405395": "pujolal01", "121578": "ruthba01"}


@pytest.fixture()
def shelf(tmp_path, monkeypatch):
    def _write(blob):
        (tmp_path / "hof_board.json").write_text(json.dumps(blob), encoding="utf-8")
    monkeypatch.setattr(mpe, "DATA_DIR", tmp_path)
    monkeypatch.setattr(hof_data, "crosswalk_bbref_mlbam", lambda: dict(_XWALK_FIX))
    return _write


def test_the_line_is_the_shelf_row_verbatim(shelf):
    shelf(_SHELF_FIX)
    idx = mpe._hof_index()
    assert set(idx) == {545361, 405395}
    trout = idx[545361]
    assert trout["id"] == "troutmi01" and trout["band"] == "watch"
    assert trout["basis"] == "B-Ref bWAR"
    src = _SHELF_FIX["watch"][0]
    for k in mpe.HOF_FIELDS:
        assert trout[k] == src[k], k
    assert idx[405395]["band"] == "not_yet_eligible"
    assert idx[405395]["jaws"] == 81.4


def test_the_eligible_band_and_an_unbridged_id_never_join(shelf):
    shelf(_SHELF_FIX)
    idx = mpe._hof_index()
    assert 121578 not in idx                       # Ruth is on the Eligible band
    assert all(v["id"] != "nobodyx01" for v in idx.values())


def test_a_shelf_on_another_basis_prints_no_line(shelf):
    shelf({**_SHELF_FIX, "basis": {"war": "eWAR v2"}})
    assert mpe._hof_index() == {}


def test_a_missing_shelf_or_bridge_prints_no_line(shelf, monkeypatch):
    assert mpe._hof_index() == {}                  # no file written yet
    shelf(_SHELF_FIX)

    def _boom():
        raise RuntimeError("no parquet")
    monkeypatch.setattr(hof_data, "crosswalk_bbref_mlbam", _boom)
    assert mpe._hof_index() == {}


def _hof_line_source() -> str:
    js = JS.read_text(encoding="utf-8")
    start = js.index("function hofLine(p)")
    end = js.index("\n  }\n", start)
    return js[start:end]


def test_the_renderer_prints_no_standard_and_links_to_hof():
    body = _hof_line_source()
    assert 'href="/hof/"' in body
    assert "/awards/" not in body
    assert "Hall of Fame" in body
    assert "B-Ref bWAR" in body
    for word in ("standard", "average", "median", "pace", "projected", "likely",
                 "will ", "chance", "odds", "—", "–"):
        assert word not in body.lower(), word
    js = JS.read_text(encoding="utf-8")
    assert "hofLine(p)" in js[js.index("function overviewPanel("):js.index("function hofLine(p)")]


def _served():
    if not DETAIL.exists() or not SHELF.exists():
        pytest.skip("data/mlb_player_detail.json or data/hof_board.json is absent")
    d = json.loads(DETAIL.read_text(encoding="utf-8"))
    if "hof" not in (d.get("coverage") or {}):
        pytest.skip("the served payload predates the Hall of Fame line; re-run "
                    "mlb_player_export")
    return d, json.loads(SHELF.read_text(encoding="utf-8"))


def test_the_served_line_equals_the_shelf_for_the_same_bbref_id():
    d, hb = _served()
    rows = {r["id"]: (band, r) for band in mpe.HOF_BANDS for r in hb.get(band) or []}
    n = 0
    for p in d["players"].values():
        h = p.get("hof")
        if not h:
            continue
        band, src = rows[h["id"]]
        assert h["band"] == band, h["id"]
        assert h["basis"] == "B-Ref bWAR"
        for k in mpe.HOF_FIELDS:
            assert h[k] == src[k], (h["id"], k)
        # the same man: the bridge maps this card's MLBAM id to this B-Ref id
        assert hof_data.crosswalk_bbref_mlbam().get(str(p["mlbam"])) == h["id"]
        n += 1
    assert n == d["coverage"]["hof"]
    assert n > 200
    # no position standard or other comparison rides in the block
    allowed = {"id", "band", "basis", *mpe.HOF_FIELDS}
    for p in d["players"].values():
        assert set(p.get("hof") or {}) <= allowed
