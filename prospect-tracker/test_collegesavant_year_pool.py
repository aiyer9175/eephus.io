# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""CollegeSavant opens on its largest season pool and names every pool.

Final-pass finding M03-10 (2026-09-24). The hitter page opened on 2025, a
184-row Big Ten file with no team or PA column, and the pitcher page on 2026,
842 arms at a median of 73 pitches with no K/BB columns, while 2024 holds the
national TrackMan set (3,607 hitters, 4,485 arms). CS+ is z-scored within the
active season, and the copy called 100 "the college average" or "D1 average"
on every pool. The default season is now the largest pool, each season option
names its size (and team count, and for pitchers the median pitch count), and
the CS+ copy names the pool it is relative to.
"""
from __future__ import annotations

import pytest

from test_collegesavant_board_flags import CAP, EVAL, PROSPECTS, TRANS, CS

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer


def _hit(name, year, team):
    return ('{"hitter_name":"%s","team":"%s","year":%d,"k_pct":20,"pa":100,"bb_pct":9,'
            '"xwoba":0.36,"average_exit_velocity":90,"90th_percentile_exit_velocity":104,'
            '"max_exit_velocity":110,"swing_pct":45,"chase_pct":25,"whiff_pct":20,'
            '"zone_swing_pct":65,"zone_contact_pct":85,"o_contact_pct":60,'
            '"sweet_spot_pct":35,"barrel_pct":10,"hard_hit_pct":45}' % (name, team, year))


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


def test_hitter_default_is_largest_pool_and_options_name_it():
    rows = [_hit("A, One", 2025, "")] + [_hit(f"B, N{i}", 2024, t)
                                         for i, t in enumerate(["GEO_BUL", "TEX_LON", "OSU_BUC"])]
    ctx = _boot("app.js", "HITTER_DATA:[" + ",".join(rows) + "]")
    assert ctx.eval("state.year") == 2024
    ctx.eval("location.hash='#/leaders/cs_plus/2024';window.location.hash=location.hash;render();")
    html = ctx.eval("__html['app']||''")
    assert "2024 · 3 hitters, 3 teams</option>" in html, html[:2000]
    assert "2025 · 1 hitter</option>" in html


def test_pitcher_default_is_largest_pool_and_options_name_it():
    rows = ([_pit(1, 2026, "TEX_LON", 70), _pit(2, 2026, "OSU_BUC", 80)]
            + [_pit(10 + i, 2024, t, 300) for i, t in enumerate(["GEO_BUL", "TEX_LON", "OSU_BUC"])])
    ctx = _boot("pitcher_app.js", "PITCHER_DATA:[" + ",".join(rows) + "]")
    assert ctx.eval("state.year") == 2024
    ctx.eval("location.hash='#/leaders/stuff_plus/2024';window.location.hash=location.hash;render();")
    html = ctx.eval("__html['app']||''")
    assert "2024 · 3 arms, 3 teams, median 300 pitches</option>" in html, html[:2000]
    assert "2026 · 2 arms, 2 teams, median 80 pitches</option>" in html


def test_no_fixed_pool_claims_left():
    for app in ("app.js", "pitcher_app.js"):
        src = (CS / app).read_text(encoding="utf-8")
        assert "CS+ 100 = D1 average" not in src
        assert "college average, +10" not in src and "college pitcher average, +10" not in src
