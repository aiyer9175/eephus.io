# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer render test for assets/management.js (/management/).

test_mgmt_export.py pins the PAYLOAD and greps the JS for the keys it reads;
nothing rendered the page. These tests do, on a small real-shaped payload:

  - the sacrifice bunt family, live in the payload since 2026-09-07, is drawn;
  - the gate lede follows clears_null instead of asserting "No" as a literal;
  - the raw split-half line is built from the gate block's own numbers, never
    from a sentence that quotes figures of its own;
  - the MLB feed's Brier prints beside the model's when the payload has it.

Skips when py_mini_racer is unavailable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")

SAMPLE = {
    "gate_doc": "docs/IN_GAME_MANAGEMENT_GATE.md", "gate_frozen_at": "2026-09-06",
    "headline": {"sentence": "The league steals second at break-even.", "games": 100,
                 "net_dv_all_seasons_wins": -0.5, "redistributable_pool_abs_dv_wins": 12.0},
    "running_game": {
        "by_target": {"2B": {"n": 90, "success_rate": 0.75, "swing_weighted_breakeven_p": 0.753,
                             "share_of_attempts_below_their_own_breakeven": 0.5, "sum_dv_wins": -0.4}},
        "by_season": {"2026": {"n": 90, "success_rate": 0.75, "sum_dv_wins": -0.4}},
        "excluded": {"two_outs_crosses_the_boundary": 10},
        "decomposition": {"dv": "the DECISION.", "er": "the EXECUTION RESIDUAL.",
                          "identity": "DV + ER = the realized change"},
        "why_the_league_average_runner": "the runner is league average.",
        "attempt_census_sentence": "The corpus holds 100 attempts.",
        "why_two_out_attempts_are_excluded": "two estimators meet at the boundary.",
    },
    "gate": {"split_half_r": 0.1085, "null_band": [-0.15, 0.1272], "clears_null": False,
             "n_agent_seasons_in_the_split": 238, "smallest_detectable_per_attempt_sd": 0.0005,
             "variance_explained_by_season": 0.787, "variance_explained_by_team": 0.021,
             "raw_split_half_r_for_comparison": 0.7673,
             "why_season_controlled": "both halves sit in one season.",
             "why_the_raw_number_is_not_the_finding": "the RAW split-half is 0.7789 (stale).",
             "null_construction": "permuted within season.",
             "detection_floor_reading": "the smallest effect at 80 percent power.",
             "what_a_null_decides": "a team-season bounds a manager."},
    "reference": {
        "run_expectancy": [{"bases": "empty", "outs": o, "runs": r, "n": 10}
                           for o, r in ((0, 0.5), (1, 0.27), (2, 0.1))],
        "half_inning_start": {"note": "measured.", "tied_game": [
            {"inning": 1, "half": "top", "batting_team_win_prob": 0.47, "n": 100}]},
        "model": {"n_plays_fit": 1000, "seasons": ["2025", "2026"],
                  "calibration": {"brier": 0.157678, "brier_base_rate_only": 0.249754,
                                  "feed_brier": 0.157516}},
        "smoothing_costs_the_tails": "less sharp at the extremes.",
        "state_excludes": "the teams and the park.",
    },
    "teams": {"status": "built", "columns_are_style_not_skill": "style.",
              "rows": [{"team": "MIA", "season": 2026, "attempts": 10, "success_rate": 0.8,
                        "share_2B": 0.8, "share_3B": 0.2, "mean_breakeven_faced": 0.75}]},
    "sections": {
        "team_style": {"why_no_plus_metric": "noise."},
        "sacrifice_bunt": {"live": True, "sentence": "Bunting cost 127 wins.",
                           "cells": [{"bases": "empty", "outs": 0, "n_bunt": 804,
                                      "dv_per_bunt": -0.02514, "dv_total": -20.211},
                                     {"bases": "3B", "outs": 1, "n_bunt": 49,
                                      "dv_per_bunt": 0.02367, "dv_total": 1.1599}],
                           "independent_control": {"total_wins": -75.33,
                                                   "why_it_is_not_the_metric": "realized."},
                           "the_selection_problem": "NOT SOLVED, STATED.",
                           "two_outs_excluded": "two estimators."},
        "manager_attribution": {"live": False, "blocked_on": "M-MWAR-2", "why": "upper bound."},
        "bullpen_and_lineup": {"live": False, "blocked_on": "not yet measured", "why": "unmeasured."},
    },
    "what_this_page_does_not_claim": "that any manager is better than any other.",
}


def _render(section: str = "running", payload: dict | None = None, bunt_tab: bool = False) -> str:
    js = JS.replace('state = { section: "running"', 'state = { section: "%s"' % section, 1)
    assert section == "running" or js != JS, "the section default moved"
    q = ("function(sel){return String(sel).indexOf('bunt')>=0 ? {} : null;}"
         if bunt_tab else "function(){return null;}")
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v;return true;}});}
    function FT(v){return {then:function(cb){var r=cb(v);return (r&&r.then)?r:FT(r);},catch:function(){return FT(v);}};}
    var P=%s;
    var fetch=function(){return FT({ok:true,json:function(){return FT(P);}});};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:%s,querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    """ % (json.dumps(payload or SAMPLE), q)
    ctx = MiniRacer()
    ctx.eval(prelude + js)
    return ctx.eval("__html['mgmt-app-root'] || ''")


def test_the_sacrifice_bunt_family_is_drawn():
    html = _render("running")
    assert "The sacrifice bunt" in html and "Bunting cost 127 wins." in html
    assert html.count("<tr><td>empty</td>") >= 1 and "+0.0237" in html
    assert "-75.3 wins" in html and "NOT SOLVED, STATED." in html


def test_the_bunt_moves_to_its_own_tab_once_the_shell_has_one():
    assert "The sacrifice bunt" not in _render("running", bunt_tab=True)
    assert "Bunting cost 127 wins." in _render("bunt", bunt_tab=True)


def test_a_dark_bunt_section_draws_nothing():
    d = json.loads(json.dumps(SAMPLE))
    d["sections"]["sacrifice_bunt"] = {"live": False}
    assert "The sacrifice bunt" not in _render("running", d)


def test_the_gate_lede_follows_clears_null():
    assert "Inside its permutation null band" in _render("gate")
    d = json.loads(json.dumps(SAMPLE))
    d["gate"]["clears_null"] = True
    html = _render("gate", d)
    assert "Clears its permutation null." in html
    assert "Inside its permutation null band" not in html


def test_the_raw_split_half_is_read_off_the_gate_block():
    html = _render("gate")
    assert "Raw 0.7673 against 0.1085 season-controlled" in html
    assert "0.7789" not in html, "the sentence with its own stale figures is still drawn"
    d = json.loads(json.dumps(SAMPLE))
    d["gate"].pop("raw_split_half_r_for_comparison")
    assert "0.7789 (stale)" in _render("gate", d), "an older payload lost its only line"


def test_the_feed_brier_prints_beside_the_model():
    html = _render("reference")
    assert "Brier 0.1577; base rate alone 0.2498; MLB feed 0.1575." in html
    assert html.rstrip().endswith("</section>")


def test_no_dashes_in_any_section():
    for sec in ("running", "gate", "reference", "teams", "bunt"):
        html = _render(sec)
        for bad in ("&mdash;", "&ndash;", "\u2014", "\u2013", "undefined", "NaN"):
            assert bad not in html, (sec, bad)


def test_the_served_board_renders_every_section():
    p = ROOT / "data" / "management_board.json"
    if not p.exists():
        pytest.skip("management_board.json not built")
    d = json.loads(p.read_text(encoding="utf-8"))
    for sec in ("running", "gate", "reference", "teams"):
        html = _render(sec, d)
        assert html and "undefined" not in html and "NaN" not in html, sec
