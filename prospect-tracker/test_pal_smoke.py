# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer smoke test for assets/pal.js (Alchemy Lab).

Stubs the DOM + a synchronous fetch so init() renders each section, then asserts
real content (candidate tables, the need-gated SP->RP verdict, the backtest
scorecard, the pitch-add recommendation). Skips when py_mini_racer is absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")

SAMPLE = """{
 "season":2026,"n_conversions":95,"verdict":"provisional",
 "rp2sp":[{"mlbam":1,"name":"Deep Reliever","team":"NYY","fit":85.2,"n_pitches":4,"ip":50,"k_pct":0.28,
   "bb_pct":0.05,"fb_velo":94,"proj_velo":93,"fb_pct":0.5,"platoon_split":0.05,
   "components":{"arsenal_depth":100,"command":90,"fb_reliance_inv":80,"stuff_quality":70,"platoon_neutrality":88,"survivability":60},
   "flags":[],"arsenal":[{"pitch":"FF","usage":0.3,"whiff":0.15,"est_woba":0.30},{"pitch":"SL","usage":0.25,"whiff":0.30,"est_woba":0.28}],
   "pitch_add":{"add":"Changeup","target":"RHB","reason":"no offspeed pitch","priority":"medium"}}],
 "sp2rp":[{"mlbam":2,"name":"Power Starter","team":"SD","fit":78.0,"relief_upside":85,"starter_era":5.10,"n_pitches":2,
   "best_whiff":0.40,"proj_velo":100,"fb_velo":98,"proj_relief_rem_plus":150,
   "components":{"stuff_upside":80,"putaway":90,"velo_leverage":70,"tto_leakage":75,"conversion_need":82},
   "flags":[{"key":"putaway","label":"late-inning weapon"},{"key":"struggling_sp","label":"struggling as a starter"}]}],
 "history":[{"mlbam":3,"name":"Converted Guy","team":"KC","direction":"RP->SP","year":2023,
   "pre":{"season":2022,"g":60,"gs":0,"ip":65,"k_pct":0.28,"era":3.5},"post":{"season":2023,"g":30,"gs":28,"ip":160,"k_pct":0.24,"era":3.8},
   "pre_war":0.8,"post_war":3.2,"war_delta":2.4,
   "pitch_mix":{"before":[{"pitch":"FF","usage":0.6},{"pitch":"SL","usage":0.35}],"after":[{"pitch":"FF","usage":0.45},{"pitch":"SL","usage":0.3},{"pitch":"CH","usage":0.2}]},
   "held":true,"pre_fit":80.5,"success":true}],
 "pitch_mix_changes":[{"mlbam":3,"name":"Converted Guy","team":"KC","direction":"RP->SP","year":2023,
   "before":[{"pitch":"FF","usage":0.6}],"after":[{"pitch":"FF","usage":0.4},{"pitch":"CH","usage":0.2}]}],
 "pitch_add":[{"mlbam":1,"name":"Deep Reliever","team":"NYY","fit":85.2,"n_pitches":4,
   "arsenal":[{"pitch":"FF","usage":0.3}],"platoon_split":0.05,
   "rec":{"add":"Changeup","target":"RHB","reason":"no offspeed pitch","priority":"medium"}}],
 "reverse_platoon":[{"mlbam":9,"name":"Reverse Guy","team":"TB","role":"RP","p_throws":"R",
   "own_ops":0.720,"opp_ops":0.560,"split":0.160,"reverse_index":0.160,"reverse":true,"extreme":true,
   "weak_hand":"RHB","min_tbf":120}],
 "prospect_watch":[{"name":"Thin Starter Prospect","org":"LAD","position":"SP","fv":50,
   "tools":{"fb":60,"sl":55,"cmd":40},"starter_shape":27.0,"arsenal_depth":2,"role":"SP","lean":"RP","mismatch":true}],
 "n_prospects":1960,
 "backtest":{"n_labeled":44,"spearman_prefit_vs_held":0.223,"relief_k_bump_measured":0.022,
   "per_direction":{"SP->RP":{"n_war":61,"rho_prefit_vs_war_delta":0.295,"n_held":22,"rho_prefit_vs_held":0.43},
                    "RP->SP":{"n_war":25,"rho_prefit_vs_war_delta":-0.216,"n_held":13,"rho_prefit_vs_held":0.134}},
   "converter_median_fit_pool_pctile":72,"disclaimer":"A screen, not a success-probability model."}
}"""


def _prelude(hash_: str) -> str:
    return f"""
    var __html={{}};
    function __el(id){{return new Proxy(function(){{return __el(id);}},{{
      get:function(t,k){{ if(k==='innerHTML')return __html[id]||'';
        if(k==='classList')return {{add:function(){{}},remove:function(){{}},toggle:function(){{}},contains:function(){{return false;}}}};
        if(k==='querySelectorAll')return function(){{return [];}};
        if(k==='getAttribute')return function(){{return null;}};
        if(k==='setAttribute'||k==='addEventListener'||k==='removeEventListener')return function(){{}};
        if(k==='querySelector'||k==='closest')return function(){{return __el(id+'q');}};
        if(k==='value'||k==='textContent')return ''; return __el(id);}},
      set:function(t,k,v){{if(k==='innerHTML')__html[id]=v;return true;}}, apply:function(){{return __el(id);}}}});}}
    function FT(val){{return {{then:function(cb){{var r=cb(val);return (r&&r.then)?r:FT(r);}},catch:function(cb){{return FT(val);}}}};}}
    var SAMPLE={SAMPLE};
    var fetch=function(){{return FT({{ok:true,json:function(){{return FT(SAMPLE);}}}});}};
    var history={{replaceState:function(){{}}}};
    var location={{hash:'{hash_}'}};
    var document={{readyState:'complete',getElementById:function(id){{return __el(id);}},
      querySelector:function(){{return __el('q');}},querySelectorAll:function(){{return [];}},
      createElement:function(){{return __el('c');}},addEventListener:function(){{}},
      body:__el('body'),documentElement:__el('de'),head:__el('head')}};
    var window={{location:location,document:document,history:history,fetch:fetch,
      EEPHUS_GL:{{wire:function(){{}}}},EEPHUS_HUB:{{teamLogo:function(){{return '<img>';}}}},
      addEventListener:function(){{}},setTimeout:function(){{}}}};
    var navigator={{userAgent:'smoke'}};
    """


def _render(hash_: str) -> str:
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_) + JS)
    return ctx.eval("__html['pal-app-root'] || ''")


def test_rp2sp_view():
    html = _render("")
    assert "mlbstats-table" in html and "Deep Reliever" in html
    assert "pal-fit" in html and ">85.2<" in html


def test_sp2rp_need_gated_view():
    html = _render("#sp2rp")
    assert "Power Starter" in html
    assert "struggling as a starter" in html          # the need flag renders
    assert "5.10" in html                             # SP ERA column


def test_history_scorecard_view():
    html = _render("#history")
    assert "pal-scorecard" in html
    # per-direction chips (the pooled sign-check is retired from the UI)
    assert "0.223" not in html
    assert "0.295" in html and "validated vs baselines" in html
    assert "-0.216" in html and "does not validate ranking" in html
    assert "Converted Guy" in html
    assert "Hit" in html                              # held-role label
    # WAR produced by the conversion: before -> after with the delta
    assert "WAR before" in html                       # column header
    assert "3.2" in html and "+2.4" in html           # post WAR + gain
    # arsenal shift: CH was added in the move
    assert "+CH" in html


def test_pitchadd_view():
    html = _render("#pitchadd")
    assert "Deep Reliever" in html
    assert "ADD Changeup" in html


def test_platoon_radar_view():
    html = _render("#platoon")
    assert "Reverse Guy" in html
    assert "reverse" in html.lower()


def test_prospect_watch_view():
    html = _render("#prospects")
    assert "Thin Starter Prospect" in html
    assert "profiles as a reliever" in html


# ---------------------------------------------------------------------------
# F-02: fetch failure must paint a visible error state (not the misleading
# "being computed" message), with a retry affordance.
# ---------------------------------------------------------------------------

def test_fetch_failure_renders_error_state():
    ctx = MiniRacer()
    err_fetch = ("var fetch=function(){return {then:function(){return this;},"
                 "catch:function(cb){cb(new Error('network down'));return this;}};};")
    ctx.eval(_prelude("") + err_fetch + JS)
    html = ctx.eval("__html['pal-app-root'] || ''")
    assert "Data failed to load" in html
    assert "nightly build is mid-run" in html
    assert "pal-retry" in html               # the retry affordance exists
    assert 'role="alert"' in html


def test_null_payload_still_reads_as_not_exported():
    ctx = MiniRacer()
    ok_null = ("var fetch=function(){return FT({ok:true,"
               "json:function(){return FT(null);}});};")
    ctx.eval(_prelude("") + ok_null + JS)
    html = ctx.eval("__html['pal-app-root'] || ''")
    assert "being computed" in html
    assert "Data failed to load" not in html


# ---------------------------------------------------------------------------
# Per-position defensive history (owner ask 1, 2026-07-30)
# ---------------------------------------------------------------------------

def test_position_history_is_served_with_its_trust_column():
    """The evidence log was computed and deliberately not served. It is served
    now because ask 1 wanted "which position has he performed best at" -- but it
    is only answerable next to the sample-size read, so `rel` ships with it or
    not at all. Forty innings in right field and nine hundred at first are not
    comparable readings of a player even though both print an OAA."""
    import json
    from pathlib import Path
    p = Path(__file__).parent / "data" / "positional_fit_ui.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    withhist = [r for r in doc["rows"] if r.get("hist")]
    assert withhist, "no player carries a position history"
    for r in withhist[:40]:
        for e in r["hist"]:
            assert {"season", "pos", "inn", "z"} <= set(e), e
            assert "rel" in e, "history row shipped without its trust column"
            if e["rel"] is not None:
                assert 0.0 < e["rel"] <= 1.0, e


def test_history_trust_tracks_the_fitted_stabilization_constants():
    """`rel` must be innings/(innings + k_inn) using the model's OWN fitted
    per-position constants, not a constant. Centre field stabilizes at 632
    innings and first base at 2,539, so the same innings must NOT yield the same
    trust at both."""
    import json
    from pathlib import Path
    root = Path(__file__).parent
    ui = json.loads((root / "data" / "positional_fit_ui.json").read_text(encoding="utf-8"))
    sig = json.loads((root / "data" / "positional_fit.json").read_text(encoding="utf-8"))["fit"]["signal"]
    checked = 0
    for r in ui["rows"]:
        for e in (r.get("hist") or []):
            k = (sig.get(e["pos"]) or {}).get("k_inn")
            if not k or e["rel"] is None:
                continue
            assert abs(e["rel"] - e["inn"] / (e["inn"] + k)) < 1e-3, (e, k)
            checked += 1
    assert checked > 50, f"only {checked} history rows verified"


def test_history_renders_with_the_trust_column_labelled():
    """A trust number nobody explains is worse than none: the panel has to say
    what it means, or a reader will compare z columns across positions."""
    js = (__import__("pathlib").Path(__file__).parent / "assets" / "pal.js").read_text(encoding="utf-8")
    assert "function pfHistory" in js
    assert "Where he has played" in js
    assert "stabilization constant" in js


def test_rng_plus_is_outfield_only_and_never_admits_an_infield_position():
    """Rng+ (legs) is the surviving half of owner ask 1, and its whole content is
    the RESTRICTION. Sprint speed predicts OAA per 1000 innings in the outfield
    (CF r=+0.428, LF +0.416) and measures a flat zero on the dirt (SS -0.020,
    3B -0.004), so a speed meter on an infield destination would show the reader
    a measured nothing.

    RIGHT FIELD is excluded on purpose even though it clears the headline bar
    (+0.269 [+0.167,+0.365]): its pure-corner subgroup, right fielders with under
    100 career CF innings, is r=+0.075 [-0.111,+0.256] and cannot clear zero, so
    the RF signal is carried by displaced centre fielders. LF survives the same
    test (+0.359 [+0.163,+0.528]).

    This test exists because the failure mode is SILENT: a producer change that
    widened the whitelist would put a meter on shortstop rows and nothing else
    would complain."""
    import json
    from pathlib import Path
    doc = json.loads((Path(__file__).parent / "data" / "positional_fit_ui.json")
                     .read_text(encoding="utf-8"))
    meta = doc.get("rngMeta")
    assert meta, "rngMeta missing; the Position Fit payload lost its Rng+ block"
    ship = meta["shipPositions"]
    assert set(ship) == {"LF", "CF"}, (
        f"Rng+ whitelist is {ship}. Only LF and CF are measured-positive with a "
        "pure-corner subgroup that clears zero. Widening this needs the "
        "per-position r re-measured first, not a code change.")
    for bad in ("1B", "2B", "3B", "SS", "C", "DH", "RF"):
        assert bad not in ship, f"{bad} must never carry a range meter"
    # Every whitelisted position ships the correlation that justifies it, so the
    # tooltip can cite a number instead of asserting one.
    for pos in ship:
        r = (meta.get("r") or {}).get(pos)
        assert r and r.get("r", 0) > 0.15, (pos, r)
        assert r["ci95"][0] > 0.15, (
            f"{pos} CI lower bound {r['ci95'][0]} must be ABOVE +0.15. A CI that "
            "merely EXCLUDES +0.15 is also satisfied by one lying entirely below "
            "it, which would admit SS and 3B.")
    # Percentile pools must be real, not a handful of players.
    for pos, pool in (meta.get("pools") or {}).items():
        assert pos in ship, f"pool built for {pos}, which does not ship"
        assert pool["n"] >= 20, pool
        assert pool["p10"] <= pool["p50"] <= pool["p90"], pool


def test_rng_plus_is_display_only_and_never_reaches_the_model():
    """OAA already contains the legs, so a sprint term in the conversion model
    would double-count. This is the same argument that rejected the arm feature
    (CONVERSION_ARM_GATE_VERDICT.md). The meter is allowed to be a display, and
    only a display."""
    import json
    import re
    from pathlib import Path
    root = Path(__file__).parent
    src = (root / "positional_fit.py").read_text(encoding="utf-8")
    assert not re.search(r"\bsavant_sprint\b|\bsprint_for\b|\bspeed_for\b", src), (
        "positional_fit.py imported the sprint feed. Rng+ is display-only; OAA "
        "already contains the legs.")
    doc = json.loads((root / "data" / "positional_fit_ui.json").read_text(encoding="utf-8"))
    for r in doc["rows"]:
        g = r.get("rng")
        if not g:
            continue
        assert {"plus", "fts", "season"} <= set(g), g
        # A read must never be silently invented for a player with no tracking.
        assert g["fts"] and g["plus"], g
