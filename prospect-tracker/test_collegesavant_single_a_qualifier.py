# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Projected Single-A board lists rows behind the median qualifier.

Owner answer M19CS-2 (2026-10-01): the default sample qualifier that
de2639b6 gave the CollegeSavant leaderboards and home widgets (rows at or
above the season pool's median PA or pitch count) also filters the Projected
Single-A board, which ranks by CS+ and let 35-PA hitters and 54-pitch arms
lead it. The reader keeps the same Min PA / Min pitches control (0 lists every
projected row), the board prints the qualifier sentence, and the Team
Tendencies averages stay unfiltered.
"""
from __future__ import annotations

import json
import re

import pytest

from test_collegesavant_board_flags import CS
from test_collegesavant_year_pool import _boot, _go, _hit, _pit

pytest.importorskip("py_mini_racer")

# One team per side so Team Tendencies (3-row minimum) shows the full count.
HITTERS = ([_hit("A, One", 2025, "MIN_GOL", None), _hit("A, Two", 2025, "IU", None)]
           + [_hit("B, N%d" % i, 2024, "GEO_BUL", pa) for i, pa in enumerate([20, 60, 150])])
PITCHERS = [_pit(i, 2026, "TEX_LON", pc) for i, pc in enumerate([30, 70, 80])]


def _with_projections(ctx, players):
    slugs = ctx.eval("JSON.stringify(state.%s.map(function(p){return p.slug;}))" % players)
    trans = {s: {"single_a": {"k_pct": {"exp": 22.0, "lo": 15.0, "hi": 29.0},
                              "bb_pct": {"exp": 9.0, "lo": 5.0, "hi": 13.0}}}
             for s in json.loads(slugs)}
    ctx.eval("window.CS_TRANSLATION.translations = %s;" % json.dumps(trans))
    return ctx


def _board(html):
    i = html.index("Projected Single-A board")
    return html[i:]


def _rows(html):
    return re.findall(r'class="proj-name" href="#/player/\d{4}/([^"]+)"', _board(html))


def test_hitter_board_defaults_to_the_pool_median_and_the_toggle_lists_all():
    ctx = _with_projections(_boot("app.js", "HITTER_DATA:[" + ",".join(HITTERS) + "]"), "allPlayers")
    ctx.eval("setActiveYear(2024);")
    html = _go(ctx, "#/projections")
    assert 'value="60" data-min-pa' in html and "median 60" in html, html[:1500]
    assert sorted(_rows(html)) == ["b-n1", "b-n2"], _rows(html)
    assert "2 of 3 hitters with a projection listed, 2024: 60+ PA (default: the 2024 pool median)" in html
    assert "2 hitters listed" in html
    # The toggle: Min PA 0 lists every projected hitter, as on the leaderboards.
    ctx.eval("state.minPA = 0; renderProjections();")
    html = ctx.eval("__html['app']")
    assert len(_rows(html)) == 3
    assert "3 of 3 hitters with a projection listed, 2024: no PA minimum (the 2024 pool median is 60 PA)" in html
    assert 'value="0" data-min-pa' in html


def test_hitter_board_without_a_pa_column_lists_every_row_and_says_so():
    ctx = _with_projections(_boot("app.js", "HITTER_DATA:[" + ",".join(HITTERS) + "]"), "allPlayers")
    html = _go(ctx, "#/projections")
    assert ctx.eval("state.year") == 2025
    assert "Min PA: unavailable for 2025 (no PA column)" in html
    assert len(_rows(html)) == 2
    assert "the 2025 pool has no PA column, so every hitter is listed" in html


def test_pitcher_board_defaults_to_the_pool_median_and_the_toggle_lists_all():
    ctx = _with_projections(_boot("pitcher_app.js", "PITCHER_DATA:[" + ",".join(PITCHERS) + "]"), "allPitchers")
    html = _go(ctx, "#/projections")
    assert ctx.eval("state.year") == 2026
    assert 'value="70" data-min-pitch' in html and "median 70" in html
    assert len(_rows(html)) == 2
    assert "2 of 3 pitchers with a projection listed, 2026: 70+ pitches (default: the 2026 pool median)" in html
    ctx.eval("state.minPitch = 0; renderProjections();")
    html = ctx.eval("__html['app']")
    assert len(_rows(html)) == 3
    assert "3 of 3 pitchers with a projection listed, 2026: no pitch minimum" in html


def test_the_reader_control_is_wired_on_the_board():
    for app, attr, key in (("app.js", "data-min-pa", "minPA"), ("pitcher_app.js", "data-min-pitch", "minPitch")):
        src = (CS / app).read_text(encoding="utf-8")
        body = src[src.index("function renderProjections()"):]
        body = body[:body.index(chr(10) + "}" + chr(10))]
        assert "qualifierControl(qual)" in body and "passesQualifier(x.p, qual)" in body
        assert f'querySelector("[{attr}]")' in body and f"state.{key} = Number(e.target.value) || 0; renderProjections();" in body


def test_team_tendencies_stay_unfiltered():
    ctx = _boot("app.js", "HITTER_DATA:[" + ",".join(HITTERS) + "]")
    ctx.eval("setActiveYear(2024);")
    html = _go(ctx, "#/teams")
    assert "3 batters" in html, html[:2000]
    ctx = _boot("pitcher_app.js", "PITCHER_DATA:[" + ",".join(PITCHERS) + "]")
    html = _go(ctx, "#/teams")
    assert "3 arms" in html, html[:2000]
