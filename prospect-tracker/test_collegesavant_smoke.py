# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Execution smoke test for the CollegeSavant vanilla-JS apps.

CollegeSavant ships hand-written JS with no build step and no JS test runner, so
a load-time crash (a temporal-dead-zone reference, an undefined call) ships
silently until someone opens the page. This runs each app in V8 with a stubbed
DOM and a few sample rows: it loads the script, runs init() (data parse +
percentiles + CS+), and drives both render branches, asserting nothing throws.

Skips when py_mini_racer is unavailable so it never blocks a machine without it;
add `py_mini_racer` to requirements so CI runs it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

CS = Path(__file__).parent / "collegesavant"

HITTER_ROWS = """[
 {"hitter_name":"Test, Alpha","year":2024,"team":"TEX_LON","xwoba":0.40,"average_exit_velocity":90,"90th_percentile_exit_velocity":104,"max_exit_velocity":110,"swing_pct":45,"chase_pct":25,"whiff_pct":20,"zone_swing_pct":65,"zone_contact_pct":85,"o_contact_pct":60,"sweet_spot_pct":35,"barrel_pct":10,"hard_hit_pct":45,"k_pct":18,"bb_pct":10},
 {"hitter_name":"Test, Beta","year":2024,"team":"CAL_FUL","xwoba":0.35,"average_exit_velocity":88,"90th_percentile_exit_velocity":101,"max_exit_velocity":107,"swing_pct":48,"chase_pct":30,"whiff_pct":25,"zone_swing_pct":70,"zone_contact_pct":80,"o_contact_pct":55,"sweet_spot_pct":33,"barrel_pct":7,"hard_hit_pct":40,"k_pct":24,"bb_pct":8},
 {"hitter_name":"Test, Gamma","year":2024,"team":"OSU_BUC","xwoba":0.45,"average_exit_velocity":93,"90th_percentile_exit_velocity":106,"max_exit_velocity":113,"swing_pct":42,"chase_pct":20,"whiff_pct":15,"zone_swing_pct":62,"zone_contact_pct":90,"o_contact_pct":65,"sweet_spot_pct":37,"barrel_pct":14,"hard_hit_pct":52,"k_pct":12,"bb_pct":14}
]"""

PITCHER_ROWS = """[
 {"pitcher_id":"1","pitcher_name":"Arm, Alpha","team":"TEX_LON","year":2024,"pitch_count":300,"stuff_plus":120,"avg_fastball_velo":94,"avg_ivb":18,"avg_extension":6.2,"avg_release_height":6.0,"xwoba_against":0.28,"average_exit_velocity":86,"barrel_pct":5,"hard_hit_pct":35,"k_pct":28,"bb_pct":7,"chase_pct":30,"z_contact_pct":80,"swinging_strike_pct":13},
 {"pitcher_id":"2","pitcher_name":"Arm, Beta","team":"OSU_BUC","year":2024,"pitch_count":280,"stuff_plus":105,"avg_fastball_velo":91,"avg_ivb":15,"avg_extension":6.0,"avg_release_height":6.2,"xwoba_against":0.34,"average_exit_velocity":89,"barrel_pct":8,"hard_hit_pct":42,"k_pct":20,"bb_pct":10,"chase_pct":24,"z_contact_pct":86,"swinging_strike_pct":9},
 {"pitcher_id":"3","pitcher_name":"Arm, Gamma","team":"CAL_FUL","year":2024,"pitch_count":320,"stuff_plus":135,"avg_fastball_velo":96,"avg_ivb":20,"avg_extension":6.5,"avg_release_height":5.9,"xwoba_against":0.24,"average_exit_velocity":84,"barrel_pct":3,"hard_hit_pct":30,"k_pct":33,"bb_pct":6,"chase_pct":34,"z_contact_pct":76,"swinging_strike_pct":16}
]"""


def _prelude(kind: str) -> str:
    data_var = "HITTER_DATA" if kind == "hitter" else "PITCHER_DATA"
    rows = HITTER_ROWS if kind == "hitter" else PITCHER_ROWS
    extra = "" if kind == "hitter" else "window.PITCHER_PITCH_DATA=[]; window.PITCH_SHAPES_2024={}; window.PITCH_SHAPES_2025={};"
    return f"""
    var __errors=[];
    var console={{log:function(){{}},warn:function(){{}},error:function(){{__errors.push(Array.prototype.join.call(arguments,' '));}}}};
    function __el(){{
      return new Proxy(function(){{return __el();}},{{
        get:function(t,k){{
          if(k==='innerHTML') return '';
          if(k==='style') return {{}};
          if(k==='classList') return {{add:function(){{}},remove:function(){{}},toggle:function(){{}},contains:function(){{return false;}}}};
          if(k==='value'||k==='textContent') return '';
          if(k==='selectionStart') return 0;
          if(k==='dataset') return {{}};
          if(k==='querySelectorAll') return function(){{return [];}};
          if(k==='getAttribute') return function(){{return null;}};
          if(k==='addEventListener'||k==='removeEventListener'||k==='setAttribute'||k==='appendChild'||k==='remove'||k==='focus'||k==='setSelectionRange'||k==='scrollIntoView') return function(){{}};
          if(k==='querySelector'||k==='closest') return function(){{return __el();}};
          if(k===Symbol.toPrimitive) return function(){{return '';}};
          return __el();
        }},
        set:function(){{return true;}}, apply:function(){{return __el();}}
      }});
    }}
    var location={{hash:'#/',search:'',href:'http://x/'}};
    var localStorage={{getItem:function(){{return null;}},setItem:function(){{}},removeItem:function(){{}}}};
    var document={{querySelector:function(){{return __el();}},querySelectorAll:function(){{return [];}},getElementById:function(){{return __el();}},createElement:function(){{return __el();}},addEventListener:function(){{}},body:__el(),documentElement:__el(),head:__el()}};
    var CS_TRANSLATION={{translations:{{
      "test-alpha":{{side:"hit",single_a:{{k_pct:{{exp:22,lo:15,hi:29}},bb_pct:{{exp:11,lo:6,hi:16,low_confidence:true}},ops:{{exp:0.75,lo:0.6,hi:0.9,experimental:true}}}}}},
      "arm-alpha":{{side:"pit",single_a:{{k_pct:{{exp:25,lo:18,hi:32}},bb_pct:{{exp:9,lo:4,hi:14,low_confidence:true}}}}}}
    }}}};
    var window={{{data_var}: {rows}, CS_TRANSLATION:CS_TRANSLATION, B1G_TEAMS:{{}}, B1G_TEAMS_PITCHERS:{{}}, location:location, localStorage:localStorage, document:document, addEventListener:function(){{}}, removeEventListener:function(){{}}, matchMedia:function(){{return {{matches:false,addEventListener:function(){{}},addListener:function(){{}}}};}}, requestAnimationFrame:function(){{}}, setTimeout:function(){{}}, clearTimeout:function(){{}}, devicePixelRatio:1, innerWidth:1200, scrollTo:function(){{}}, EEPHUS_GL:null, EEPHUS_HUB:null}};
    {extra}
    var navigator={{userAgent:'smoke'}};
    var requestAnimationFrame=window.requestAnimationFrame, setTimeout=window.setTimeout;
    """


@pytest.mark.parametrize("app,kind", [("app.js", "hitter"), ("pitcher_app.js", "pitcher")])
def test_collegesavant_app_loads_and_renders(app, kind):
    ctx = MiniRacer()
    shared = ""
    if kind == "hitter":
        shared = (CS / "team_names.js").read_text(encoding="utf-8") + "\n"
    code = _prelude(kind) + shared + (CS / app).read_text(encoding="utf-8")
    # Load + init() must not throw (catches TDZ / undefined-reference crashes).
    ctx.eval(code)
    # Home, leaderboard, AND the player page (which builds CS+ + the Single-A
    # translation block) must all render without throwing.
    player = "test-alpha" if kind == "hitter" else "arm-alpha"
    for h in ["#/", "#/leaders/k_pct/2024", "#/leaders/cs_plus/2024", f"#/player/2024/{player}"]:
        ctx.eval(f"location.hash='{h}'; window.location.hash='{h}'; render();")


def test_shared_team_resolver_resolves_codes():
    ctx = MiniRacer()
    ctx.eval((CS / "team_names.js").read_text(encoding="utf-8"))
    assert ctx.eval('formatTeamName("TEX_LON")') == "Texas Longhorns"
    assert ctx.eval('formatTeamName("OSU_BUC")') == "Ohio State Buckeyes"
    # Unknown codes fall back to a clean title-case, never a raw underscore code.
    assert "_" not in ctx.eval('formatTeamName("ZZZ_QQQ")')
