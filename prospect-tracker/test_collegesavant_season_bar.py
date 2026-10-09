# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Each CollegeSavant app header prints its dataset badge and one season
picker, both computed from the season file the app loaded (REDESIGN_collegesavant,
site-pass plan 5.3).

The hitter app serves the 2025 Big Ten file (184 hitters, no PA column) while
the pitcher app serves the 2026 national file (842 arms), and before this the
season showed only in the data line under the title. The header now carries a
badge ("2025 · Big Ten · archive" / "2026 · national") and the season picker
that used to be repeated in each view's toolbar. These tests pin that:
  - the page markup holds only an empty slot, no season, scope or count;
  - the badge follows the data: a synthetic file of another season and scope
    prints that season and scope, so nothing in the header is a literal;
  - "archive" marks a season older than the year the files were received;
  - the picker lists the seasons the file holds, newest first and selected,
    and no view toolbar repeats it;
  - a season picked on either app is recalled for the session when the other
    app's file holds it, and a fresh session opens on the newest season.
"""
from __future__ import annotations

import re

import pytest

from test_collegesavant_board_flags import CAP, EVAL, PROSPECTS, TRANS, CS

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

PAGES = {"app.js": CS / "index.html", "pitcher_app.js": CS / "pitcher_index.html"}


def _hit(name, year, team):
    return ('{"hitter_name":"%s","team":"%s","year":%d,"pa":120,"k_pct":20,"bb_pct":9,'
            '"xwoba":0.36,"average_exit_velocity":90,"90th_percentile_exit_velocity":104,'
            '"max_exit_velocity":110,"swing_pct":45,"chase_pct":25,"whiff_pct":20,'
            '"zone_swing_pct":65,"zone_contact_pct":85,"o_contact_pct":60,'
            '"sweet_spot_pct":35,"barrel_pct":10,"hard_hit_pct":45}' % (name, team, year))


def _pit(i, year, team):
    return ('{"pitcher_id":"%d","pitcher_name":"Arm, N%d","team":"%s","year":%d,'
            '"pitch_count":90,"stuff_plus":110,"avg_fastball_velo":93,"avg_ivb":17,'
            '"avg_extension":6.1,"avg_release_height":6.0,"xwoba_against":0.3,'
            '"average_exit_velocity":87,"barrel_pct":6,"hard_hit_pct":38}' % (i, i, team, year))


def _boot(app, rows, stored=None):
    key = "HITTER_DATA" if app == "app.js" else "PITCHER_DATA"
    ctx = MiniRacer()
    ctx.eval(CAP.replace("__DATA__", "%s:[%s]" % (key, ",".join(rows))).replace("__T__", TRANS)
             .replace("__E__", EVAL).replace("__P__", PROSPECTS))
    if stored is not None:
        ctx.eval("var __ss={'collegesavant.season':'%s'};window.sessionStorage={"
                 "getItem:function(k){return __ss[k]||null;},setItem:function(k,v){__ss[k]=v;}};"
                 % stored)
    ctx.eval((CS / "team_names.js").read_text(encoding="utf-8"))
    ctx.eval((CS / "cs_season.js").read_text(encoding="utf-8"))
    ctx.eval((CS / app).read_text(encoding="utf-8"))
    return ctx


def _go(ctx, route):
    ctx.eval("location.hash='%s';window.location.hash=location.hash;render();" % route)
    return ctx.eval("__html['app']||''"), ctx.eval("__html['[data-cs-season]']||''")


def _badge(bar):
    m = re.search(r'<span class="cs-dataset[^"]*" data-cs-dataset title="([^"]*)">([^<]*)</span>', bar)
    assert m, bar
    return m.group(2), m.group(1)


def _cs_bar(page):
    html = page.read_text(encoding="utf-8")
    m = re.search(r'<div class="cs-bar">(.*?)\n    </div>\n', html.replace("\r\n", "\n"), re.DOTALL)
    assert m, page.name
    return html, m.group(1)


@pytest.mark.parametrize("app", sorted(PAGES))
def test_page_markup_holds_an_empty_slot_and_loads_the_shared_script(app):
    html, bar = _cs_bar(PAGES[app])
    assert '<div class="cs-season" data-cs-season></div>' in bar, bar
    # No season, scope or pool count is written into the header markup.
    text = re.sub(r"<!--.*?-->", "", bar, flags=re.DOTALL)
    assert not re.search(r"\b20\d\d\b", text), text
    for word in ("Big Ten", "national", "archive"):
        assert word not in text, word
    # The shared script loads before the app script that calls it.
    i = html.index('<script src="cs_season.js?v=')
    assert i < html.index('<script src="%s?v=' % app)


@pytest.mark.parametrize("app,rows,want", [
    ("app.js", [_hit("A, One", 2025, "MIN_GOL"), _hit("A, Two", 2025, "IU")], "2025 · Big Ten · archive"),
    ("app.js", [_hit("B, One", 2031, "TEX_LON"), _hit("B, Two", 2031, "GEO_BUL")], "2031 · national"),
    ("pitcher_app.js", [_pit(1, 2026, "TEX_LON"), _pit(2, 2026, "OSU_BUC")], "2026 · national"),
    ("pitcher_app.js", [_pit(1, 2022, "IU"), _pit(2, 2022, "NEB")], "2022 · Big Ten · archive"),
])
def test_badge_prints_from_the_loaded_file(app, rows, want):
    ctx = _boot(app, rows)
    _, bar = _go(ctx, "#/")
    text, title = _badge(bar)
    assert text == want, bar
    year = want[:4]
    assert title.startswith("The %s pool: " % year), title
    assert ("Archive: a finished season" in title) == want.endswith("archive"), title


def test_badge_follows_the_season_the_reader_picks():
    ctx = _boot("app.js", [_hit("A, One", 2025, "MIN_GOL"), _hit("A, Two", 2025, "IU"),
                           _hit("B, One", 2024, "TEX_LON"), _hit("B, Two", 2024, "IU")])
    _, bar = _go(ctx, "#/")
    assert _badge(bar)[0] == "2025 · Big Ten · archive"
    _, bar = _go(ctx, "#/leaders/cs_plus/2024")
    assert _badge(bar)[0] == "2024 · national · archive"


@pytest.mark.parametrize("app,rows,years", [
    ("app.js", [_hit("A, One", 2025, "IU"), _hit("B, One", 2024, "TEX_LON")], [2025, 2024]),
    ("pitcher_app.js", [_pit(1, 2026, "TEX_LON"), _pit(2, 2024, "IU"), _pit(3, 2025, "NEB")],
     [2026, 2025, 2024]),
])
def test_one_picker_lists_the_file_seasons_newest_first(app, rows, years):
    ctx = _boot(app, rows)
    first = ctx.eval("(state.players || state.pitchers)[0].slug")
    for route in ("#/", "#/leaders/cs_plus/%d" % years[0], "#/teams", "#/projections",
                  "#/player/%d/%s" % (years[0], first)):
        html, bar = _go(ctx, route)
        opts = re.findall(r'<option value="(\d{4})"( selected)?>', bar)
        assert [int(y) for y, _ in opts] == years, (route, bar)
        assert [int(y) for y, sel in opts if sel] == [years[0]], (route, bar)
        assert "data-cs-season-select" in bar
        # The view toolbars no longer repeat the season picker.
        assert "year-select" not in html, (route, html[:600])


@pytest.mark.parametrize("app,rows,stored,want", [
    ("app.js", [_hit("A, One", 2025, "IU"), _hit("B, One", 2024, "TEX_LON")], "2024", 2024),
    ("app.js", [_hit("A, One", 2025, "IU"), _hit("B, One", 2024, "TEX_LON")], "2026", 2025),
    ("pitcher_app.js", [_pit(1, 2026, "TEX_LON"), _pit(2, 2024, "IU")], "2024", 2024),
    ("pitcher_app.js", [_pit(1, 2026, "TEX_LON"), _pit(2, 2024, "IU")], None, 2026),
])
def test_session_season_is_shared_when_the_file_holds_it(app, rows, stored, want):
    ctx = _boot(app, rows, stored)
    assert ctx.eval("state.year") == want
    _, bar = _go(ctx, "#/")
    assert _badge(bar)[0].startswith(str(want))
