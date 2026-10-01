# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""CollegeSavant opens on its newest season, names every pool, and lists rows
behind a default sample qualifier.

Final-pass finding M03-10 (2026-09-24) and owner answers M19-2 / M19-3
(2026-09-25). Each season payload is a different pool (hitters 2024 national,
3,607 rows; 2025 a 184-row Big Ten file with no team or PA column; pitchers
2026 842 arms at a median of 73 pitches), and CS+ is z-scored within the
active season. The owner chose: open on the NEWEST season, labelled; the
season picker names each pool's scope (national or Big Ten only), size, team
count and median PA or pitches; the CS+ copy names the pool; a data stamp says
when the files arrived; and the leaderboards and home widgets list rows at or
above the pool's median PA or pitches by default, with the number in the
control. A pool with no PA column says the qualifier is unavailable.
"""
from __future__ import annotations

import re

import pytest

from test_collegesavant_board_flags import CAP, EVAL, PROSPECTS, TRANS, CS

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer


def _hit(name, year, team, pa=100):
    pa_field = "" if pa is None else ',"pa":%d' % pa
    return ('{"hitter_name":"%s","team":"%s","year":%d,"k_pct":20%s,"bb_pct":9,'
            '"xwoba":0.36,"average_exit_velocity":90,"90th_percentile_exit_velocity":104,'
            '"max_exit_velocity":110,"swing_pct":45,"chase_pct":25,"whiff_pct":20,'
            '"zone_swing_pct":65,"zone_contact_pct":85,"o_contact_pct":60,'
            '"sweet_spot_pct":35,"barrel_pct":10,"hard_hit_pct":45}' % (name, team, year, pa_field))


def _pit(i, year, team, pc):
    return ('{"pitcher_id":"%d","pitcher_name":"Arm, N%d","team":"%s","year":%d,'
            '"pitch_count":%d,"stuff_plus":110,"avg_fastball_velo":93,"avg_ivb":17,'
            '"avg_extension":6.1,"avg_release_height":6.0,"xwoba_against":0.3,'
            '"average_exit_velocity":87,"barrel_pct":6,"hard_hit_pct":38,"k_pct":25,'
            '"bb_pct":8,"chase_pct":28,"z_contact_pct":82,"swinging_strike_pct":11}'
            % (i, i, team, year, pc))


def _boot(app, data):
    ctx = MiniRacer()
    ctx.eval(CAP.replace("__DATA__", data).replace("__T__", TRANS)
             .replace("__E__", EVAL).replace("__P__", PROSPECTS))
    ctx.eval((CS / "team_names.js").read_text(encoding="utf-8"))
    ctx.eval((CS / app).read_text(encoding="utf-8"))
    return ctx


def _go(ctx, route):
    ctx.eval("location.hash='%s';window.location.hash=location.hash;render();" % route)
    return ctx.eval("__html['app']||''")


# Hitters: 2025 is a Big Ten file with no PA column; 2024 is national with PA.
HITTERS = ([_hit("A, One", 2025, "MIN_GOL", None), _hit("A, Two", 2025, "IU", None)]
           + [_hit("B, N%d" % i, 2024, t, pa)
              for i, (t, pa) in enumerate([("GEO_BUL", 20), ("TEX_LON", 60), ("OSU_BUC", 150)])])
PITCHERS = ([_pit(1, 2026, "TEX_LON", 70), _pit(2, 2026, "OSU_BUC", 80), _pit(3, 2026, "GEO_BUL", 30)]
            + [_pit(10 + i, 2024, t, pc)
               for i, (t, pc) in enumerate([("GEO_BUL", 100), ("TEX_LON", 300), ("OSU_BUC", 500)])])


def test_hitter_default_is_newest_and_options_name_the_pool():
    ctx = _boot("app.js", "HITTER_DATA:[" + ",".join(HITTERS) + "]")
    assert ctx.eval("state.year") == 2025
    html = _go(ctx, "#/")
    assert "2025 · Big Ten only · 2 hitters, 2 teams, no PA column</option>" in html, html[:2000]
    assert "2024 · national · 3 hitters, 3 teams, median 60 PA</option>" in html
    assert "Data through: the CollegeSavant files received 2026-06-11" in html


def test_pitcher_default_is_newest_and_options_name_the_pool():
    ctx = _boot("pitcher_app.js", "PITCHER_DATA:[" + ",".join(PITCHERS) + "]")
    assert ctx.eval("state.year") == 2026
    html = _go(ctx, "#/")
    assert "2026 · national · 3 arms, 3 teams, median 70 pitches</option>" in html, html[:2000]
    assert "2024 · national · 3 arms, 3 teams, median 300 pitches</option>" in html
    assert "a cut taken during the 2026 season" in html


def _rows(html):
    return re.findall(r'class="proj-name" href="#/player/\d{4}/([^"]+)"', html)


def test_hitter_qualifier_defaults_to_pool_median_and_says_when_unavailable():
    ctx = _boot("app.js", "HITTER_DATA:[" + ",".join(HITTERS) + "]")
    html = _go(ctx, "#/leaders/cs_plus/2024")
    assert 'value="60" data-min-pa' in html and "median 60" in html
    assert sorted(_rows(html)) == ["b-n1", "b-n2"], _rows(html)
    assert "60+ PA (default: the 2024 pool median)" in html
    ctx.eval("state.minPA = 0; renderLeaderboard();")
    assert len(_rows(ctx.eval("__html['app']"))) == 3
    html = _go(ctx, "#/leaders/cs_plus/2025")
    assert "Min PA: unavailable for 2025 (no PA column)" in html
    assert "data-min-pa" not in html
    assert len(_rows(html)) == 2
    assert "the 2025 pool has no PA column, so every hitter is listed" in html


def test_pitcher_qualifier_defaults_to_pool_median_and_resets_on_season_change():
    ctx = _boot("pitcher_app.js", "PITCHER_DATA:[" + ",".join(PITCHERS) + "]")
    html = _go(ctx, "#/leaders/stuff_plus/2026")
    assert 'value="70" data-min-pitch' in html
    assert len(_rows(html)) == 2
    ctx.eval("state.minPitch = 0; renderLeaderboard();")
    assert len(_rows(ctx.eval("__html['app']"))) == 3
    html = _go(ctx, "#/leaders/stuff_plus/2024")
    assert 'value="300" data-min-pitch' in html
    assert len(_rows(html)) == 2


def test_no_fixed_pool_claims_left():
    for app in ("app.js", "pitcher_app.js"):
        src = (CS / app).read_text(encoding="utf-8")
        assert "CS+ 100 = D1 average" not in src
        assert "college average, +10" not in src and "college pitcher average, +10" not in src
        assert "largestPoolYear" not in src
