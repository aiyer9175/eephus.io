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

import json
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
# /pal/ carried its own COPY of the board banding function until 2026-09-16.
# It calls the shared value ruler now, so the harness evaluates that first.
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")
JS = TIERS_JS + (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")

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
   "tools":{"fb":60,"sl":55,"cmd":40},"starter_shape":18.0,"arsenal_depth":2,"role":"SP","lean":"RP",
   "mismatch":true,"mismatch_margin":22.0}],
 "prospect_watch_rule":{"fv_min":40.0,"margin_min":10.0,"cap":60,"n_mismatches":3,"n_qualified":1,
   "n_shown":1,"n_below_margin":2,"n_over_cap":0,"cap_binding":false,
   "best_margin_below_threshold":8.0,"swing_band":20.0,
   "severity_cuts":[{"key":"severe","min_margin":20.0,"label":"a full swing band past the boundary","n":1},
                    {"key":"marked","min_margin":15.0,"label":"three quarters of the band past the boundary","n":0},
                    {"key":"modest","min_margin":10.0,"label":"half the band past the boundary, the listing floor","n":0}]},
 "tier_rule":{
   "rp2sp":{"direction":"rp2sp","n_rows":1,"fit_min":85.2,"fit_median":85.2,"fit_max":85.2,"tiers":[
     {"rank":1,"min_fit":70.0,"label":"Starter Upside","n":1,
      "premium_label":"Prime Starter Convert","premium_flag":"successful","n_premium":0},
     {"rank":2,"min_fit":55.0,"label":"Worth a Look","n":0},
     {"rank":3,"min_fit":42.0,"label":"Fringe Fit","n":0},
     {"rank":4,"min_fit":null,"label":"Reliever Profile","n":0}]},
   "sp2rp":{"direction":"sp2rp","n_rows":1,"fit_min":78.0,"fit_median":78.0,"fit_max":78.0,"tiers":[
     {"rank":1,"min_fit":55.0,"label":"Bullpen Upside","n":1},
     {"rank":2,"min_fit":45.0,"label":"Relief Fit","n":0},
     {"rank":3,"min_fit":35.0,"label":"Marginal Move","n":0},
     {"rank":4,"min_fit":null,"label":"Keep Starting","n":0}]}},
 "n_prospects":1960,
 "backtest":{"n_labeled":44,"spearman_prefit_vs_held":0.223,"relief_k_bump_measured":0.022,
   "per_direction":{"SP->RP":{"n_war":61,"rho_prefit_vs_war_delta":0.295,"n_held":22,"rho_prefit_vs_held":0.43},
                    "RP->SP":{"n_war":25,"rho_prefit_vs_war_delta":-0.216,"n_held":13,"rho_prefit_vs_held":0.134}},
   "war_basis":{"provider":"ewar_v2","series":"eWAR v2: the Baseball-Reference run frame with pitching re-priced on FIP within role","source":"war_source.stint_frame('pit') on war_source.DEFAULT_PROVIDER","stamped":"2026-09-05","n_seasons":156,"available":true,"provider_known":true},
   "gate":{"artifact":"data/pal_eval.json","generated_at":"2026-07-15","basis_provider":"bwar","basis_series":"bWAR: the Baseball-Reference run frame, pitchers priced on the runs they actually allowed","rule":"rho(FIT,war_delta) >= rho(best baseline) AND gap lo95 > -0.01","same_basis_as_live":false,"per_direction":{"SP->RP":{"pass":true,"n_gate":61,"rho_fit_war_delta":0.2916,"best_baseline":"kbb_pre","best_baseline_rho":-0.097,"gap_lo95":0.0745},"RP->SP":{"pass":false,"n_gate":25,"rho_fit_war_delta":-0.2062,"best_baseline":"neg_era_pre","best_baseline_rho":0.1023,"gap_lo95":-0.7517}}},
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


def _render_payload(hash_: str, payload: str) -> str:
    """Same shell, an arbitrary payload. Used to prove the STALE-payload
    fallbacks, which is the only way to see them: a current export always
    carries the rule blocks."""
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_).replace(f"var SAMPLE={SAMPLE};", f"var SAMPLE={payload};") + JS)
    return ctx.eval("__html['pal-app-root'] || ''")


def test_rp2sp_view():
    # EXPLICIT hash. The default tab moved to sp2rp (the direction that passes
    # its gate), so _render("") renders the SP->RP board and this test would be
    # asserting against the wrong section. What the default IS gets its own
    # test below, so moving it again fails there and not here.
    html = _render("#rp2sp")
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
    # The chip carries TWO measurements on TWO bases and must keep them apart:
    # the live rho is labelled with the series backtest.war_basis stamps, the
    # verdict beside it with the gate's own n and the series the gate ran on.
    # Asserting the labels is what makes this a test of DERIVED copy rather
    # than of two literal strings (see the flip test below).
    assert "(n=61, eWAR v2)" in html and "(n=25, eWAR v2)" in html
    assert "(gate n=61, bWAR basis)" in html
    assert "(gate n=25, bWAR basis)" in html
    assert "Converted Guy" in html
    assert "Hit" in html                              # held-role label
    # WAR produced by the conversion: before -> after with the delta
    assert "WAR before" in html                       # column header
    assert "3.2" in html and "+2.4" in html           # post WAR + gain
    # arsenal shift: CH was added in the move
    assert "+CH" in html


def test_scorecard_verdicts_are_read_from_the_payload_not_hard_coded():
    """The card used to print "validated vs baselines" / "does not validate
    ranking" as literal strings keyed to the direction, so it went on reporting
    the bWAR-era gate after the live rhos moved to the eWAR v2 series and
    nothing failed. Flip the gate in the payload and the copy must flip with
    it; remove the gate and the card must refuse to assert either way."""
    flipped = json.loads(SAMPLE)
    g = flipped["backtest"]["gate"]["per_direction"]
    g["SP->RP"]["pass"], g["RP->SP"]["pass"] = False, True
    html = _render_payload("#history", json.dumps(flipped))
    assert "does not validate ranking" in html and "validated vs baselines" in html
    # SP->RP is the first chip printed, so a flipped gate puts the FAIL word
    # ahead of the PASS word. Hard-coded copy cannot move.
    assert html.index("does not validate ranking") < html.index("validated vs baselines")
    nogate = json.loads(SAMPLE)
    nogate["backtest"].pop("gate")
    html2 = _render_payload("#history", json.dumps(nogate))
    assert "gate verdict not in this payload" in html2
    assert "validated vs baselines" not in html2
    assert "does not validate ranking" not in html2
    # and with no war_basis the live rho must lose its series label rather than
    # inherit one: two different unavailabilities, two different silences.
    nobasis = json.loads(SAMPLE)
    nobasis["backtest"].pop("war_basis")
    html3 = _render_payload("#history", json.dumps(nobasis))
    assert "(n=61)" in html3 and "eWAR v2" not in html3


def test_the_converter_percentile_reads_as_an_ordinal():
    """The chip typed a literal "th" after the number and printed "72th"."""
    html = _render("#history")
    assert "72nd</b> pct of the field" in html
    assert "72th" not in html


def test_default_tab_is_the_direction_whose_gate_passes():
    """Owner default, 2026-09-06: the lab opens on SP->RP, the direction the
    pre-registered gate validates, not RP->SP, the one it does not. This is the
    only place the default is pinned -- every board test drives its hash -- so
    flipping the page back to leading with its weakest claim fails here."""
    default = _render("")
    assert "Power Starter" in default, "no-hash load is not the SP->RP board"
    assert "Deep Reliever" not in default
    assert "Deep Reliever" in _render("#rp2sp"), "the RP->SP board is unreachable"


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
# Candidate TIERS come from the payload, never from constants in the renderer
# (lane K1/K2, 2026-08-07). The failure this guards is silent: a legend that
# states a cut the export is not applying, which is exactly how the SP->RP top
# tier came to advertise a 70+ band on a scale whose live maximum is 62.8.
# ---------------------------------------------------------------------------

def test_tier_cuts_are_read_from_the_payload_per_direction():
    rp = _render("#rp2sp")
    sp = _render("#sp2rp")
    # SP->RP carries its OWN cuts. Its FIT is a need-gated score that tops out
    # near 60, so a shared 70 cut left the advertised top tier permanently empty.
    assert "Bullpen Upside</b> (55.0+" in sp
    assert "Relief Fit</b> (45.0+" in sp
    assert "Marginal Move</b> (35.0+" in sp
    assert "below 35.0" in sp
    assert "(70.0+" not in sp, "SP->RP legend is quoting the RP->SP cuts again"
    # RP->SP keeps 70/55/42: the histogram annotation and the `successful` split
    # both depend on that top cut.
    assert "Worth a Look</b> (55.0+" in rp
    assert "Fringe Fit</b> (42.0+" in rp
    # membership counts ship with the cuts, so an empty tier is visible
    assert "(55.0+, 1)" in sp


def test_tier_chip_is_coloured_by_TIER_not_by_direction():
    """The colour channel used to encode which tab the reader had already
    clicked (all cyan on one, all orange on the other), which is zero bits about
    the tier. Chips now carry a rank class and the severity ramp lives in CSS."""
    rp = _render("#rp2sp")
    sp = _render("#sp2rp")
    assert "pal-tier--t1" in rp
    assert "pal-tier--t1" in sp          # a top-tier chip on BOTH tabs
    for stale in ("pal-tier--rp2sp", "pal-tier--sp2rp"):
        assert stale not in rp and stale not in sp, stale


def test_stale_payload_falls_back_to_the_old_shared_cuts_not_to_a_blank():
    """A payload built before tier_rule shipped must degrade to the previous
    rendering. It also must not print membership counts it does not have."""
    import json
    d = json.loads(SAMPLE)
    d.pop("tier_rule")
    html = _render_payload("#sp2rp", json.dumps(d))
    assert "Bullpen Upside</b> (70.0+)" in html      # old shared cut, no count
    assert "Power Starter" in html                    # and the table still renders


def test_sp2rp_shareable_board_carries_the_tier_column():
    """rp2sp has shipped a Tier column since it was built. Without one on
    sp2rp the two shareable graphics disagreed about what a PAL board is."""
    assert "sp2rpBoardSpec" in JS
    spec = JS[JS.index("function sp2rpBoardSpec"):JS.index("// ---- sections")]
    assert 'tierTitle(r, "sp2rp")' in spec
    assert '{ label: "Tier"' in spec


# ---------------------------------------------------------------------------
# Prospect-watch SEVERITY (lane K3). The margin was printed as plain text with
# no tiering, so a full-band mismatch read the same as one at the listing floor.
# ---------------------------------------------------------------------------

def test_prospect_watch_renders_a_severity_chip_from_the_payload_cuts():
    html = _render("#prospects")
    assert "pal-sev--severe" in html                  # 22.0 is a full band past
    assert "severe</b> at 20.0+" in html              # the legend states the cut
    assert "marked</b> at 15.0+" in html
    assert "modest</b> at 10.0+" in html


def test_severity_chip_degrades_to_the_plain_margin_on_a_stale_payload():
    import json
    d = json.loads(SAMPLE)
    d["prospect_watch_rule"].pop("severity_cuts")
    html = _render_payload("#prospects", json.dumps(d))
    assert "past the band" in html                    # the old wording survives
    assert "pal-sev--severe" not in html, "invented a severity band with no cuts"


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


# ---------------------------------------------------------------------------
# CATALOG PIN for pal.json. data_catalog.py names this file as the shape pin;
# every other test here reads SAMPLE, so nothing mentioned the served artifact
# and the /sources/ row rendered no receipt.
def test_pal_json_carries_the_shape_the_catalog_promises():
    """pal.json: both conversion directions plus the pitch-mix change history."""
    p = ROOT / "data" / "pal.json"
    if not p.exists():
        pytest.skip("pal.json not built in this tree")
    d = json.loads(p.read_text(encoding="utf-8"))
    for k in ("rp2sp", "sp2rp", "pitch_mix_changes"):
        assert k in d, f"pal.json lost {k}; the catalog row promises it"
