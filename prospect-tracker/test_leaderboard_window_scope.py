# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX window leaderboards and Splits say what the game-log slice covers.

WHY THIS EXISTS (census M02-07, 2026-09-25, two verifiers CONFIRMED). The nightly
d5e build pulls game logs for the top 200 prospects by board rank only (186 with a
game log), yet the Last 7d / 14d / 30d / Custom boards printed no scope (the 30-day
OPS board shows 117 rows beside 2,544 on the full-season board), and the Splits panel
told the other ~4,475 players that "date-windowed splits cover the active pool with an
MLBAM id". Window rows also carried no org, so the Org cell printed "-" on every row.

Contract pinned here:
  * the builder records `limit` and `n_candidates` in the slice;
  * the window caption, the empty state and the Splits message read the slice scope
    through lbSliceScopeText, and no copy claims full-pool coverage;
  * window rows carry the prospect's org;
  * the caption count equals the slice's own player count.
"""
from __future__ import annotations

import json
import re
import tempfile
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def test_no_copy_claims_full_pool_coverage():
    src = _src()
    assert "cover the active pool with an MLBAM id" not in src
    assert src.count("lbSliceScopeText()") >= 4  # caption (x2), empty state, Splits
    pool = _function_source(src, "_lbWindowPool")
    assert "r.org = p.org" in pool


def test_builder_records_its_coverage():
    import tools.build_leaderboard_gamelogs as blg
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        boot, out = tmp / "timeseries.json", tmp / "leaderboard_gamelogs.json"
        boot.write_text(json.dumps({"players": [
            {"player_key": f"p{i}", "mlbam_id": 100 + i, "overall_rank": i} for i in range(1, 6)
        ]}), encoding="utf-8")
        saved = (blg.BOOT, blg.OUT, blg._pull_one)
        try:
            blg.BOOT, blg.OUT = boot, out
            blg._pull_one = lambda p, *a, **k: (p["player_key"], {"is_pitcher": False,
                                                                  "games": [{"d": "2026-09-01"}]})
            blg.build(season=2026, limit=3, workers=1)
        finally:
            blg.BOOT, blg.OUT, blg._pull_one = saved
        doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["limit"] == 3 and doc["n_candidates"] == 3 and len(doc["players"]) == 3


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval("var DATA = {};")
    ctx.eval(_function_source(_src(), "lbSliceScopeText"))
    return ctx


def test_scope_text_counts_the_slice(js):
    js.eval('DATA.leaderboard_gamelogs = {limit: 200, players: {a: {}, b: {}, c: {}}};')
    assert js.eval("lbSliceScopeText()").startswith("covers the top 200 prospects by board rank (3 with a game log)")
    js.eval('DATA.leaderboard_gamelogs = {players: {a: {}}};')
    assert js.eval("lbSliceScopeText()").startswith("covers the 1 prospects in the game-log slice")
    js.eval('DATA.leaderboard_gamelogs = null;')
    assert js.eval("lbSliceScopeText()") == ""


def test_served_slice_caption_matches_its_player_count(js):
    from conftest import load_data_doc
    gl = load_data_doc("leaderboard_gamelogs.json")
    if not gl or not gl.get("players"):
        pytest.skip("data/leaderboard_gamelogs.json not built")
    js.eval("DATA.leaderboard_gamelogs = %s;" % json.dumps({k: v for k, v in gl.items() if k != "players"}
                                                          | {"players": {k: 1 for k in gl["players"]}}))
    txt = js.eval("lbSliceScopeText()")
    assert f"({len(gl['players']):,} with a game log)" in txt or f"the {len(gl['players']):,} prospects" in txt
