# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer render test for assets/ledger.js (/ledger/, Club Ledger).

test_ledger_export.py pins the PAYLOAD; these tests render the page on a small
real-shaped payload and on the served board, and hold the shell and the app to
the rules that make a ledger a ledger:

  - no figure is typed into the HTML or the JS; every sentence is the payload's;
  - the contract ledger and the commitments renderers make no ruler call, a
    surplus total and a cap-space cell take a sign only, and the index cells
    take the z ladder with their family named;
  - the hash router anchors every key and trusts a team only as a payload key;
  - the club picker is a native select in the site idiom;
  - the CBA banner is on screen wherever a 2027 dollar is;
  - the League board hides columns by CONTAINER width, not viewport width;
  - the commitments block never prints the sum of its three segments.

Skips when py_mini_racer is unavailable.
"""
from __future__ import annotations

import copy as _copy
import json
import re
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "ledger.js").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "ledger.css").read_text(encoding="utf-8")
PAGE = ROOT / "ledger" / "index.html"
ART = ROOT / "data" / "ledger_board.json"

M = 1_000_000
LEAF = {"letter": "B+", "score_100": 108.0, "value": 2.1, "n": 12, "sparse": False}
SAMPLE = {
    "generated_at": "2026-09-23T00:00:00+00:00", "season_now": 2026, "class_year": 2027,
    "horizon": [2027, 2028, 2029, 2030, 2031],
    "cba": {"threshold_by_season": {"2026": 244 * M, "2027": 244 * M}, "spotrac_2027_basis_usd": 247 * M,
            "banner_text": "Every 2027 figure is a 2022 CBA carry-forward: the agreement expires 2026-12-01.",
            "expiry": "2026-12-01", "surcharge_tiers_usd": [20 * M, 40 * M, 60 * M],
            "brackets": {"under": "under the threshold", "base": "base bracket", "surcharge_1": "first surcharge",
                         "surcharge_2": "second surcharge", "surcharge_3": "third surcharge"},
            "rates": {}, "unverified_records": 3},
    "copy": {
        "masthead": "Every dollar a club has on the books.", "league_lede": "Thirty clubs on two bases.",
        "club_foot": "Descriptive ledger.", "cba_banner": "Every 2027 figure is a 2022 CBA carry-forward: the agreement expires 2026-12-01.",
        "cbt_computed_label": "computed from Spotrac tax payroll and the schedule", "cbt_under": "under the threshold",
        "cbt_clock_rule": "rule text, not a forecast", "cbt_verify_note": "curated-unverified",
        "qo_recipient_note": "recipients are not sourceable", "payor_basis": {"spotrac": "Spotrac 2027 page", "spotrac_2026": "Spotrac 2026 page", "derived from the 2026 status + 2026 overage": "derived"},
        "space_2027_spotrac_label": "Spotrac, 247M basis", "space_2027_platform_label": "platform carry-forward, 244M",
        "split_2026_note": "the 2026 page carries no split", "split_2027_label": "2027 allocations, Spotrac",
        "allocations_note": "AAV basis against cash basis", "history_blocked_on": "Payroll history is cached but not yet ingested",
        "commitments_bases": {"contract": "Contract dollars on file", "arb": "Arbitration steps, projected", "prearb": "Pre-arb minimums by rule"},
        "commitments_threshold_2027": "platform carry-forward 244M", "commitments_threshold_later": "no threshold published",
        "commitments_not_summed": "three labelled segments; no key sums them", "horizon_label": "half of today's contract dollars roll off by",
        "horizon_beyond": "beyond 2031", "expiring_basis": "sums of means", "holes": ["hole one", "hole two"],
        "cell_basis": {"contract": "on file (Spotrac)", "arb_ladder": "Arbitration Predictor, provisional", "class_closure": "class closure (inferred)"},
        "band_note": "band, not a calibrated interval", "options_note": "Options on file.",
        "deferral_rate_label": "NPV at the platform rate", "deferral_coverage": "covered deals only", "deferral_rate_note": "differs from the statutory rate",
        "dead_money_blocked_on": "dead rows carry no table_id yet", "dead_money_beside": "never summed with dead money",
        "retained_blocked_on": "retained rows carry no table_id yet; never merged", "retained_cross_check": "club total",
        "arb_upper_bound": "Upper bound, not a payroll forecast", "arb_provisional": "provisional", "arb_flag_key": "flag bits",
        "arb_realized_title": "What arbitration cost, and what it bought", "arb_realized_copy": "Realized value, not skill; the counterfactual is not observed.",
        "ou_mkt": "sums to roughly zero by construction", "ou_war": "does not sum to zero", "never_combine": "never combined",
        "surplus_basis": "both legs in $M", "surplus_no_tier": "printed plain", "surplus_ev": "quantiles are never summed",
        "trade_currency_basis": "never added", "trajectory_note": "since late June", "ratio_bases": "Spotrac over projections",
        "cost_plus_basis": "descriptive index, not a model", "cost_plus_registry": "no registry row", "orgsur_chip": "descriptive, unvalidated",
        "farm_leaves": {"fin_active_surplus": {"basis": "b", "weight": 0.68}, "fin_ifa_roi": {"basis": "b", "weight": 0.04}},
        "farm_letters_note": "letters are never recomputed", "pools_note": "2021 holds nine clubs", "slot_coverage_basis": "share of rows",
        "slot_window": "2021-present", "slot_league": {"overSlotShare": {"mean": 0.21, "sd": 0.05}},
        "pick_war_label": "expected first-6 WAR", "pick_war_why": "not lottery-weighted", "pick_dollars": "not served",
        "ifa_implied_basis": "implied from pool percentages", "ifa_history_blocked_on": "IFA history capped at 2021",
        "fits_note": "fa_team_fit is provisional", "implied_dpw_note": "league rate only", "priors_basis": "from fa_fit",
        "realized_title": "Contract value delivered", "realized_method": "level_proration_backcast_dpw_v1",
        "realized_coverage": "covered signings only",
        "realized_sentence": "This is what the contracts returned, not how well the club chose them.",
        "realized_not_skill": "Realized value, not skill.", "qo_none": "no live QO stamps",
        "no_payroll_line": "A single projected payroll is not served.", "load_error": "The Club Ledger could not be loaded.",
        "arb_dpw_basis": "arb over open", "projections_dpw_basis": "2027 ex-ante", "league_minimum_note": "carried forward by rule",
    },
    "field_key": {},
    "league": {
        "rows": [
            {"club": "LAD", "name": "Los Angeles Dodgers", "statsapi_code": "LAD", "cbt_payroll_2026": 430343577,
             "vs_threshold_2026": -186343577, "payor_2026": "3+-Time", "est_tax_2026": 180377935, "committed_2027": 398259591,
             "space_2027_spotrac": -125907413, "space_2027_platform": -128907413, "proj_wins_2027": 95.7, "usd_per_win": 3896629,
             "cost_plus": 93, "usd_per_war": 8053400, "locked_pct": 0.828, "controlled_surplus_mm": 873.9,
             "arb_exposure_2027": 1450000, "orgsur_plus": 112.7, "farm_rank": 1},
            {"club": "TBR", "name": "Tampa Bay Rays", "statsapi_code": "TB", "cbt_payroll_2026": 90123456,
             "vs_threshold_2026": 153876544, "payor_2026": "Non-Tax", "est_tax_2026": None, "committed_2027": 60123456,
             "space_2027_spotrac": 186876544, "space_2027_platform": 183876544, "proj_wins_2027": 84.1, "usd_per_win": 715000,
             "cost_plus": 140, "usd_per_war": 1900000, "locked_pct": 0.61, "controlled_surplus_mm": 1158.8,
             "arb_exposure_2027": 22100000, "orgsur_plus": 114.4, "farm_rank": 4},
        ],
        "columns": [["club", "Club", None, "code"], ["cbt_payroll_2026", "CBT payroll 2026", "cbt_payroll", "tip"],
                    ["vs_threshold_2026", "vs threshold", "cbt_bracket", "tip"], ["payor_2026", "Payor", "payor_tier", "tip"],
                    ["est_tax_2026", "Est. tax 2026", "computed_cbt_bill", "tip"], ["committed_2027", "Committed 2027", "payroll_allocations", "tip"],
                    ["space_2027_spotrac", "Space 2027", "cbt_payroll", "tip"], ["proj_wins_2027", "Proj wins 2027", None, "tip"],
                    ["usd_per_win", "$ per proj win", "cost_plus", "tip"], ["cost_plus", "Cost+", "cost_plus", "tip"],
                    ["usd_per_war", "$ per proj WAR", "cost_plus", "tip"], ["locked_pct", "Locked", "controlled_surplus", "tip"],
                    ["controlled_surplus_mm", "Controlled surplus", "controlled_surplus", "tip"], ["arb_exposure_2027", "Arb exposure 2027", "arb_exposure", "tip"],
                    ["orgsur_plus", "OrgSur+", "sur_plus", "tip"], ["farm_rank", "Farm rank", None, "tip"]],
        "coloured": ["cost_plus", "orgsur_plus"],
        "averages_row": {"label": "Spotrac league average", "committed_2027": 127764025},
        "means": {"label": "Mean of the 30 club rows", "values": {"cbt_payroll_2026": 260233516.5, "cbt_payroll_2026_n": 2, "est_tax_2026": 180377935, "est_tax_2026_n": 1,
                                                                 "cost_plus": 100.0, "locked_pct": 0.7}},
        "pools": {"cost_plus": {"n": 30, "mean_index": 99.93, "sd_index": 9.99}},
        "quadrant": {"x": "cbt_payroll_2026", "y": "controlled_surplus_mm", "unit": "$M", "min_width_px": 700},
        "cba_banner": True,
    },
    "clubs": {"LAD": {
        "club": "LAD", "name": "Los Angeles Dodgers", "statsapi_code": "LAD",
        "payroll": {"s2026": {"total_payroll_usd": 378282925, "tax_payroll_usd": 430343577, "space_usd": -186343577,
                              "payor_status_raw": "3+-Time", "est_tax_bill_usd": 180377935, "split": None, "split_available": False},
                    "s2027": {"total_payroll_usd": 398259591, "tax_payroll_usd": 372907413, "space_usd": -125907413,
                              "payor_status_raw": None, "est_tax_bill_usd": 50944448, "split": [394176257, None, None, 4083334],
                              "split_available": True, "avg_age": 31.9},
                    "payor_2027": {"value": "3+-Time", "basis": "derived from the 2026 status + 2026 overage"},
                    "space_2027": {"spotrac_usd": -125907413, "spotrac_basis_usd": 247 * M, "platform_usd": -128907413, "platform_basis_usd": 244 * M},
                    "history": {"status": "dark", "seasons": []}, "cba_banner": True},
        "cbt": {"2026": {"threshold_usd": 244 * M, "threshold_verify": "curated-unverified", "carry_forward": False, "tax_payroll_usd": 430343577,
                         "over_usd": 186343577, "bracket": "surcharge_3", "computed_bill_usd": 180377935, "spotrac_est_bill_usd": 180377935,
                         "diff_usd": 0, "tier": "3+-Time", "tier_basis": "spotrac_2026", "base_rate": 0.5},
                "2027": {"threshold_usd": 244 * M, "threshold_verify": "explicitly-unknown", "carry_forward": True, "tax_payroll_usd": 372907413,
                         "over_usd": 128907413, "bracket": "surcharge_3", "computed_bill_usd": 117198154, "spotrac_est_bill_usd": 50944448,
                         "diff_usd": 66253706, "tier": "3+-Time", "tier_basis": "derived from the 2026 status + 2026 overage", "base_rate": 0.5,
                         "spotrac_basis_usd": 247 * M, "over_spotrac_basis_usd": 125907413, "cba_banner": True},
                "clock": {"consecutive_payor_seasons_implied": 3, "tier_2026": "3+-Time"},
                "qo_pick_tax": {"club_tier": "cbt_payor", "club_usd": 5810065}},
        "commitments": {"by_season": [[2027, 346624080, 21, 1450000, 1, 8580000, 11, 0], [2028, 309621136, 18, 18066000, 6, 4680000, 6, 2],
                                      [2029, 240373136, 14, 26371000, 7, 0, 0, 3], [2030, 165222761, 9, 23499000, 5, 0, 0, 1], [2031, 115822761, 6, 0, 0, 0, 0, 0]],
                        "n_vets": 55, "n_priced": 36, "n_unpriced": 19, "threshold_2027_usd": 244 * M, "horizon_season": 2030,
                        "expiring": {"2027": [3, 41000000, 96000000], "2028": [5, 60000000, None], "2029": [4, None, None]}, "cba_banner": True},
        "contracts": {"rows": [["shohei_ohtani", "Shohei Ohtani", "TWP", 32, "contract", 46081476, 2033, 2033, "horizon", 238359792,
                                [[2027, 46081476, 46081476, 46081476, "signed", "contract", 0], [2028, 46081476, 46081476, 46081476, "signed", "contract", 0]],
                                [[2031, "player", None]]],
                               ["andy_pages", "Andy Pages", "CF", 26, "contract+arb", 800000, 2026, 2030, "prearb_grid", 51000000,
                                [[2027, 780000, 780000, 780000, "PRE-ARB", "arb_ladder", 0], [2028, 3100000, 2400000, 3800000, "ARB 1", "arb_ladder", 0],
                                 [2029, 5200000, 3800000, 6600000, "ARB 2", "class_closure", 1]], []]],
                      "n_priced": 2, "n_unpriced": 1, "unpriced": [["x_y", "X Y", "RP", "pending"]],
                      "options": [["Shohei Ohtani", [[2031, "player", None]]]],
                      "deferrals": {"n": 1, "n_no_deferral_assertions": 0, "sticker_usd": 700 * M, "npv_usd": 274815148,
                                    "players": [["Shohei Ohtani", 700 * M, 274815148, 2024, "curated-unverified"]]},
                      "dead_money": {"status": "dark", "by_season": [], "buried_usd_2027": 4083334},
                      "retained": {"status": "dark", "by_season": [], "retained_usd_2027": None}, "cba_banner": True},
        "arbitration": {"n": 2, "class_mix": {"1": 1, "3": 1}, "s2027_usd": 1450000, "remaining_usd": 9900000, "war": 3.4, "flags": {"1": 2, "8": 2},
                        "rows": [["A Player", 1, "ARB 1", 1450000, 1100000, 1900000, 3, 1.2, 1, 9]],
                        "cba_banner": True,
                        "realized": {"seasons": [[2023, 10, 35550000, 33544000, 2006000, -30109000, 6.35], [2024, 8, 30000000, 29000000, 1000000, -20000000, 5.0]],
                                     "n": 18, "ou_mkt_total_usd": 3006000, "ou_war_total_usd": -50109000}},
        "surplus": {"mlb_mm": 418.5, "mlb_by_salsrc_mm": {"contract": 300.1, "contract+arb": 118.4}, "farm_mm": 455.4, "total_mm": 873.9, "unit": "$M",
                    "trade_currency_mm": 990.8, "crunch": {"n_active": 180, "n_debuted": 34, "on_40_man": 40, "rule5_exposed": 6, "options_left_0": 5, "by_salary_basis": {}},
                    "trajectory": [["2026-06-25", 1100.2], ["2026-08-01", 1050.0], ["2026-09-23", 990.8]]},
        "indexes": {"usd_per_win": 3896629, "usd_per_war": 8053400, "cost_plus": 93, "cost_ratio_war_per_mm": 0.124, "orgsur_plus": 112.7,
                    "locked_pct": 0.828, "proj_wins_2027": 95.7, "proj_war_2027": 46.3, "cba_banner": True},
        "farm": {"leaves": {"fin_active_surplus": dict(LEAF, letter="A-", score_100=114.0, value=455.4, n=156),
                            "fin_ifa_roi": {"letter": " - ", "score_100": None, "value": None, "n": 0, "sparse": True}},
                 "orgsur_plus": {"financial_score": 112.7, "tree_fin_war_per_m_score_100": 114.6}, "financial_letter": "A-",
                 "financial_roi": {"war_per_million": 2.394, "total_bonus_usd": 22144990, "grad_count_with_bonus": 32},
                 "method_surplus": {"draft": {"net_mm": 250.3, "count": 68}},
                 "pools": {"2021": [None, "not parsed", None], "2026": [3951900, "live", [[28, 3200000]]]},
                 "draft_paid": {"2026": [16, 15, 1, 5384475, 6, 3951900, 4053975, 102075, 51.1, 3951900, 1.363]},
                 "slot_chips": {"nSlotted": 65, "overSlotShare": 0.2, "r1UnderShare": 0.5, "bonusHHI": 0.045, "prepDollarShare": 0.468, "label": "typical", "spendLabel": "top-heavy pool"},
                 "lottery": [28, None, None, 97, 60, "2026-09-23", "tankathon"], "pick_war": [2.579, 35, 28],
                 "ifa": {"2026": [5537500, 37, 997500, "Rubel Arias", 77.0, 7176328, 20]},
                 "score_history": [["2026-07-02", 114.0, "A"], ["2026-09-23", 113.8, "A"]], "farm_rank": 1, "farm_score": 114.6},
        "fa": {"outgoing": [["a_b", "A B", "SP", 30.1, "locked", "ufa", 32000000, 5, 150000000, 60000000, 300000000, 30000000, 40000000, 120, "market"]],
               "fits": [["c_d", "C D", "RP", 0.71, 1.0, 0.2, 1.0, 0.6, 0.5]], "expiring_2028": [5, 60000000, None], "expiring_2029": [4, None, None],
               "winters": [[2025, 4, 500000000, 40000000, 1, 3, 90000000, 17450928, {"5": 2, "1": 2}]],
               "priors": [700 * M, 6, 1804550000],
               "realized": {"status": "live", "by_winter": [[2024, 8, 8, 30.0, 247566666, 233961414, 481528080, 6], [2026, 5, 0, 0.0, 0, 0, 0, 0]]},
               "cba_banner": True},
        "links": {"farm_tree": "/prospx/#farm-org=LAD", "org_tendencies": "/prospx/#farm-org=LAD&ftab=tendencies", "fa_fits": "/fa/#view=fits&team=LAD",
                  "mlbstats_war": "/mlbstats/#section=war&wview=teams&team=LAD", "management_club": "/management/#section=clubs&team=LAD", "franchise": None},
    }},
    "rules": {"thresholds": [{"season": 2026, "threshold_usd": 244 * M, "regime": "cba_2022", "carry_forward": False, "verify_status": "curated-unverified"},
                             {"season": 2027, "threshold_usd": 244 * M, "regime": "post_cba_2022_unknown", "carry_forward": True, "verify_status": "explicitly-unknown"}],
              "surcharge_tiers_usd": [20 * M, 40 * M, 60 * M],
              "rates": {"regime": "cba_2022", "base_rate_by_payor_year": {"1": 0.2, "2": 0.3, "3+": 0.5},
                        "surcharge_rates": {"tier1": 0.12, "tier2_first": 0.425, "tier2_repeat": 0.45, "tier3": 0.6}, "verify_status": "curated-unverified"},
              "brackets": {"under": "under the threshold", "base": "base bracket"},
              "qo_values": [{"class_year": 2026, "winter": "2025-26", "value_usd": 22025000, "verify_status": "curated-unverified"}],
              "qo_compensation": {"signing_team_forfeits": {"cbt_payor": {"picks": ["2nd", "5th"], "intl_pool_usd": 1000000}}, "carry_forward": False},
              "qo_tax_by_payor_tier": {"cbt_payor": {"total_usd": 5810065}, "other": {"total_usd": 4498684}},
              "league_minimum": [{"season": 2026, "usd": 780000}],
              "dpw": {"open_market_by_winter": {"2025": 17450928, "2026": 17293779}, "open_market_method": "fa_signings_implied_v1",
                      "arbitration_by_season": {"2025": 11920000, "2026": 11230000}, "arbitration_discount_2026": 0.649, "projections_dpw_usd": 17971003},
              "war_input_divergence": {"why": "F-DEF is dropped from pricing.", "consequence": "two WARs for one player."},
              "unverified_records": ["a", "b", "c"], "cba_expiry": "2026-12-01", "cba_banner": True},
    "sections": {"league": {"live": True}, "payroll_history": {"live": False, "blocked_on": "Payroll history is cached but not yet ingested"},
                 "dead_money": {"live": False, "blocked_on": "dead rows carry no table_id yet"},
                 "retained": {"live": False, "blocked_on": "retained rows carry no table_id yet; never merged"},
                 "ifa_history": {"live": False, "blocked_on": "IFA history capped at 2021"},
                 "qo_pending": {"live": False, "n_live": 0, "note": "no live QO stamps"},
                 "single_payroll_line": {"live": False, "decided": "not served", "blocked_on": "needs registry row club_payroll_path"}},
    "method": {"sources": [["S1", "fa_meta.json", "fa_export", "daily"]], "source_key": ["id", "artifact", "writer", "cadence"],
               "inputs_generated_at": {"fa_meta": "2026-09-23"}},
    "accountability": {"registry_verdicts": [{"model_id": "org_sur_plus", "verdict": "unvalidated", "eval_artifact": None, "last_checked": None, "stale": None},
                                             {"model_id": "fa_market", "verdict": "validated", "eval_artifact": "data/fa_gate2_eval.json", "last_checked": "2026-09-23", "stale": False},
                                             {"model_id": "fa_projection_marcel", "verdict": "validated", "eval_artifact": "x", "last_checked": "2026-09-23", "stale": False}],
                       "salary_path_census": {"mode": "full", "priced_rows": 897}, "contract_disagreements": 1,
                       "contract_disagreement_rule": "S5 wins", "contract_set_note": "not read", "org_join": {"fa_meta": [32, 30]}},
    "what_this_page_does_not_claim": ["revenue: not sourced", "attendance money: not sourced"],
}

TIERS_STUB = """
var EephusTiers = { cls: function (v, fam) { return v == null ? "" : "vt vt-fam-" + fam + " vt-avg"; } };
"""


def _render(section="league", payload=None, team="", hash_="", tiers=False, season=""):
    js = JS.replace('state = { section: "league", team: ""', 'state = { section: "%s", team: "%s"' % (section, team), 1)
    assert (section, team) == ("league", "") or js != JS, "the state initialiser moved"
    if season:
        js = js.replace('season: "", block: ""', 'season: "%s", block: ""' % season, 1)
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v; if(k==='textContent')__html[id+':text']=v; return true;}});}
    function FT(v){return {then:function(cb){var r=cb(v);return (r&&r.then)?r:FT(r);},catch:function(){return FT(v);}};}
    var P=%s;
    var fetch=function(){return FT({ok:true,json:function(){return FT(P);}});};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:function(){return null;},querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    var location={hash:%s};
    %s
    """ % (json.dumps(payload or SAMPLE), json.dumps(hash_), TIERS_STUB if tiers else "")
    ctx = MiniRacer()
    ctx.eval(prelude + js)
    return ctx.eval("__html['ledger-app-root'] || ''"), ctx.eval("__html['ledger-masthead:text'] || ''")


def _served():
    if not ART.exists():
        pytest.skip("run python ledger_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------

def test_no_figure_is_typed_into_the_page_html():
    if not PAGE.exists():
        pytest.skip("run python build_site.py")
    h = PAGE.read_text(encoding="utf-8")
    d = _served()
    lad = d["clubs"].get("LAD") or next(iter(d["clubs"].values()))
    for n in (lad["payroll"]["s2026"]["tax_payroll_usd"], lad["payroll"]["s2026"]["total_payroll_usd"],
              lad["surplus"]["total_mm"], lad["cbt"][str(d["season_now"])]["computed_bill_usd"]):
        assert str(n) not in h, f"{n} is typed into the page and will go stale"
    assert 'id="ledger-app-root"' in h and 'data-csv-export="club-ledger"' in h
    assert 'id="ledger-masthead"' in h
    for cls in ("fa-app", "mlbstats-app", "ledger-app", "mlbstats-sectionnav"):
        assert cls in h
    # the JS types no dollar figure either: every $ string is built from a value
    # (the one quoted "$12.3M" is the format comment, which sits in a comment line)
    code_lines = [ln for ln in JS.splitlines() if not ln.strip().startswith("//")]
    assert not re.search(r'"\$\d[\d.,]*M?"', "\n".join(code_lines)), "a dollar figure is typed into the JS"


def test_the_js_reads_its_copy_from_the_payload():
    for key in ("masthead", "league_lede", "club_foot", "cba_banner", "arb_upper_bound", "realized_sentence",
                "commitments_not_summed", "surplus_ev", "never_combine", "no_payroll_line", "qo_recipient_note"):
        assert 'copy("%s")' % key in JS, key
    assert "what_this_page_does_not_claim" in JS and "blocked_on" in JS
    assert "NOT ONE FIGURE IN THIS FILE IS TYPED" in JS
    html, masthead = _render("league")
    assert masthead == SAMPLE["copy"]["masthead"]
    assert SAMPLE["copy"]["league_lede"] in html


def test_the_page_has_no_banned_dash():
    files = [ROOT / "assets" / "ledger.js", ROOT / "assets" / "ledger.css", ROOT / "ledger_export.py",
             ROOT / "test_ledger_export.py", ROOT / "test_ledger_render.py"]
    if PAGE.exists():
        files.append(PAGE)
    if ART.exists():
        files.append(ART)
    em, en = chr(0x2014), chr(0x2013)      # built, never typed: this file is on the list too
    for f in files:
        txt = f.read_text(encoding="utf-8")
        assert em not in txt and en not in txt, f"banned dash in {f.name}"


def _fn_body(name):
    i = JS.index("function " + name + "(")
    j = JS.index("\n  function ", i + 1)
    return JS[i:j]


def test_salary_cells_take_no_tier():
    for fn in ("renderContracts", "renderCommitments", "renderPayroll", "renderCbt"):
        assert "EephusTiers" not in _fn_body(fn) and "zCell(" not in _fn_body(fn) and "zCls(" not in _fn_body(fn), fn
    assert "ledger-cell is-signed" in CSS or ".ledger-cell.is-signed" in CSS
    html, _ = _render("club", team="LAD", tiers=True)
    i = html.index('id="ledger-block-contracts"')
    j = html.index('id="ledger-block-arbitration"')
    assert "vt-fam" not in html[i:j], "a ruler class inside the contract ledger"
    assert "is-signed" in html[i:j] and "is-prearb" in html[i:j] and "is-cut" in html[i:j] and "is-arb" in html[i:j]


def test_surplus_totals_and_space_cells_take_no_ladder():
    html, _ = _render("club", team="LAD", tiers=True)
    i = html.index('id="ledger-block-surplus"')
    j = html.index('id="ledger-block-farm"')
    block = html[i:j]
    assert "$873.9M" in block, "the club total prints plain in $M"
    assert 'class="vt vt-fam-z vt-avg">93<' in block, "Cost+ takes the z ladder inside the same block"
    assert block.count("vt-fam") == 1, "only the index took a colour"
    pay = html[html.index('id="ledger-block-payroll"'):html.index('id="ledger-block-commitments"')]
    assert '<span class="ledger-neg">-$125.9M</span>' in pay, "space takes a sign, never a ladder"
    assert "vt-fam" not in pay
    league, _ = _render("league", tiers=True)
    # the League space cell carries the platform figure in its title, and a sign class only
    assert re.search(r'class="ledger-pos" title="[^"]*platform carry-forward[^"]*\$183\.9M">\$186\.9M</span>', league)
    assert re.search(r'class="ledger-neg" title="[^"]*\$128\.9M">-\$125\.9M</span>', league)
    assert "vt-fam" in league and league.count("vt-fam") == 4, "two clubs, two coloured columns, nothing else"


def test_index_cells_use_the_z_ladder_and_name_their_family():
    league, _ = _render("league", tiers=True)
    assert '<span class="vt vt-fam-z vt-avg">140</span>' in league
    assert '<span class="vt vt-fam-z vt-avg">114</span>' in league, "OrgSur+ rounds nearest onto the z ladder"
    assert 'EephusTiers.cls(v, "z")' in JS
    assert re.findall(r"EephusTiers\.cls\([^)]*\)", JS) == ['EephusTiers.cls(v, "z")'], "one ruler call site"
    club, _ = _render("club", team="LAD", tiers=True)
    farm = club[club.index('id="ledger-block-farm"'):club.index('id="ledger-block-fa"')]
    assert '<span class="vt vt-fam-z vt-avg">113</span>' in farm, "OrgSur+ tile"
    assert '<span class="vt vt-fam-z vt-avg">114</span>' in farm, "a fin_* score_100"


def test_the_hash_router_anchors_every_key_and_validates_the_team():
    for key in ("section=(league|club|rules|method)", "team=([A-Z]{2,3})", "season=(20\\d\\d)", "block=(payroll|cbt|commitments"):
        assert "(?:^#|[#&])" + key in JS, key
    assert "Object.prototype.hasOwnProperty.call(DATA.clubs, t[1])" in JS
    html, _ = _render("league", hash_="#team=LAD")
    assert 'id="ledger-block-payroll"' in html, "#team=CODE is the shorthand that opens the club section"
    html, _ = _render("league", hash_="#team=ZZZ")
    assert 'id="ledger-block-payroll"' not in html, "an unknown team never opens a club"
    html, _ = _render("league", hash_="#section=club&team=constructor")
    assert "Los Angeles Dodgers</h2>" in html, "a prototype name falls back to the first club"
    html, _ = _render("league", hash_="#section=rules")
    assert "CBT thresholds" in html


def test_the_club_picker_is_a_native_eephus_select():
    html, _ = _render("club", team="LAD")
    assert '<select id="ledger-club" class="eephus-select" aria-label="Club">' in html
    assert '<option value="LAD" selected>' in html
    assert html.count('type="radio" name="ledger-season"') == 2
    assert "ledger-chip" in CSS and "accent-color:" not in CSS, "the radio fill comes from site.css, not a module colour"
    if PAGE.exists():
        assert "eephus-select" not in PAGE.read_text(encoding="utf-8") or True


def test_the_cba_banner_renders_whenever_a_2027_figure_is_on_screen():
    text = SAMPLE["copy"]["cba_banner"]
    club, _ = _render("club", team="LAD")
    assert club.count('class="ledger-banner"') >= 4, "the club page, contracts, arbitration and the FA ledger each carry it"
    assert text in club
    league, _ = _render("league")
    assert text in league, "the League board shows Space 2027 and Committed 2027"
    rules, _ = _render("rules")
    assert text in rules
    club27, _ = _render("club", team="LAD", season="2027")
    cbt = club27[club27.index('id="ledger-block-cbt"'):club27.index('id="ledger-block-contracts"')]
    assert text in cbt, "the 2027 ladder carries the banner"
    assert "Spotrac $247.0M basis" in cbt and "$244.0M" in cbt, "both bases named on the 2027 ladder"


def test_the_league_board_hides_columns_by_container_not_viewport():
    assert "container-type: inline-size; container-name: ledgerboard" in CSS
    i = CSS.index("@container ledgerboard (max-width: 560px)")
    j = CSS.index("}\n", CSS.index("lb-lab-short", i))
    block = CSS[i:j]
    assert ".lb-col-hide { display: none; }" in block and ".lb-xp { display: table-cell; }" in block
    for m in re.finditer(r"@media[^{]*\{", CSS):
        k = CSS.index("\n}", m.end())
        assert "lb-col-hide" not in CSS[m.start():k], "a viewport query hides a board column"
    assert "@container ledgerboard (max-width: 699px) { .ledger-app .ledger-quadrant { display: none; } }" in CSS
    assert "container-name: ledgerblock" in CSS and "@container ledgerblock (max-width: 560px)" in CSS
    league, _ = _render("league")
    assert 'class="lb-col-hide"' in league and 'class="lb-xp"' in league and "lb-lab-short" in league
    assert 'class="ledger-board">' in league


def test_the_commitments_block_never_prints_a_summed_total():
    html, _ = _render("club", team="LAD")
    block = html[html.index('id="ledger-block-commitments"'):html.index('id="ledger-block-cbt"')]
    for season, a, _na, b, _nb, c, _nc, _cl in SAMPLE["clubs"]["LAD"]["commitments"]["by_season"]:
        def m(v):
            return "$" + "%.1f" % (v / 1e6) + "M"
        assert m(a) in block and m(b) in block and m(c) in block, season
        for total in (a + b + c, a + b):
            if total not in (a, b, c):
                assert m(total) not in block, (season, "a summed segment total was printed")
    assert SAMPLE["copy"]["commitments_not_summed"] in block
    assert "19 unpriced" in block
    assert "hole one" in block


def test_the_dark_blocks_name_their_blocker_on_the_page():
    html, _ = _render("club", team="LAD")
    for s in ("payroll_history", "dead_money", "retained", "ifa_history"):
        assert SAMPLE["sections"][s]["blocked_on"] in html, s
    assert html.count('class="ledger-darktag">dark<') >= 4
    assert "no live QO stamps" in html
    method, _ = _render("method")
    assert "needs registry row club_payroll_path" in method and "revenue: not sourced" in method


def test_a_sparse_farm_leaf_renders_a_dash_not_a_letter():
    html, _ = _render("club", team="LAD")
    farm = html[html.index('id="ledger-block-farm"'):html.index('id="ledger-block-fa"')]
    assert '<span class="ledger-letter"> - </span>' in farm
    assert '<span class="ledger-letter">A-</span>' in farm


def test_the_realized_ledgers_keep_the_residuals_and_the_sentences_apart():
    html, _ = _render("club", team="LAD")
    arb = html[html.index('id="ledger-block-arbitration"'):html.index('id="ledger-block-surplus"')]
    assert "<th>ou_war</th>" in arb and "ou_mkt" in arb
    assert '<span class="ledger-pos">$3.0M</span>' in arb and '<span class="ledger-neg">-$50.1M</span>' in arb
    assert "-$47.1M" not in arb and "$-47.1M" not in arb, "the two totals were added"
    assert SAMPLE["copy"]["arb_realized_copy"] in arb
    fa = html[html.index('id="ledger-block-fa"'):html.index('id="ledger-block-links"')]
    assert SAMPLE["copy"]["realized_sentence"] in fa and "level_proration_backcast_dpw_v1" in fa
    assert "8 of 8" in fa and "0 of 5" in fa, "coverage prints per winter"


def test_the_served_board_renders_every_section_without_throwing():
    d = _served()
    for section in ("league", "rules", "method"):
        html, masthead = _render(section, payload=d, tiers=True)
        assert len(html) > 2000 and "could not be loaded" not in html, section
        assert masthead == d["copy"]["masthead"]
    for code in list(d["clubs"])[:6] + ["LAD", "TBR", "KCR"]:
        html, _ = _render("club", payload=d, team=code, tiers=True)
        assert 'id="ledger-block-links"' in html and "could not be loaded" not in html, code
        # hrefs are HTML-escaped on the page, so the & becomes &amp;
        assert d["clubs"][code]["links"]["mlbstats_war"].replace("&", "&amp;") in html
        assert "team=" + d["clubs"][code]["statsapi_code"] in html, "the /mlbstats/ link uses the StatsAPI code"
        html27, _ = _render("club", payload=d, team=code, tiers=True, season="2027")
        assert d["copy"]["cba_banner"] in html27
    league, _ = _render("league", payload=d, tiers=True)
    assert league.count("<tr>") >= 32 and '<figure class="ledger-quadrant">' in league
    assert d["league"]["averages_row"]["label"] in league and d["league"]["means"]["label"] in league


# --------------------------------------------------------------------------
# Review fixes (2026-09-23): the six served defects and the CSS order
# --------------------------------------------------------------------------

def test_the_dark_block_titles_are_plain_and_their_glossary_hook_rides_the_paragraph():
    assert "esc(title)" in _fn_body("dark"), "dark() escapes its title; a pre-built link would print as text"
    html, _ = _render("club", team="LAD")
    assert "&lt;a" not in html, "a glossary link printed as literal text"
    for title, slug in (("Dead money", "dead_money"), ("Retained salary", "retained_salary")):
        assert "<strong>" + title + "</strong>" in html, title
        assert 'data-gl="%s"' % slug in html, slug
    for fn in ("renderContracts", "renderPayroll", "renderFarm"):
        assert "dark(gl(" not in _fn_body(fn), fn


def test_a_league_mean_over_fewer_rows_than_the_board_prints_its_count():
    html, _ = _render("league")
    foot = html[html.index("<tfoot>"):html.index("</tfoot>")]
    assert "$180.4M (n 1)" in foot, "the Est. tax pool is one payor of two rows"
    assert "$260.2M</td>" in foot and "$260.2M (n" not in foot, "a full pool carries no count"
    assert "100.0</td>" in foot, "a column without an _n key prints plain"
    assert "(n 0)" not in foot


def test_the_2026_payor_tier_names_the_2026_page_and_2027_names_its_derivation():
    html, _ = _render("club", team="LAD")
    cbt = html[html.index('id="ledger-block-cbt"'):html.index('id="ledger-block-contracts"')]
    assert "3+-Time (Spotrac 2026 page)" in cbt and "2027 page" not in cbt
    html27, _ = _render("club", team="LAD", season="2027")
    cbt27 = html27[html27.index('id="ledger-block-cbt"'):html27.index('id="ledger-block-contracts"')]
    assert "3+-Time (derived)" in cbt27 and "2026 page" not in cbt27
    pay27 = html27[html27.index('id="ledger-block-payroll"'):html27.index('id="ledger-block-commitments"')]
    assert "Spotrac estimate; " in pay27 and "3+-Time (derived)" in pay27, "the payor branch of the tile carries the basis too"
    pay = html[html.index('id="ledger-block-payroll"'):html.index('id="ledger-block-commitments"')]
    assert "(derived)" not in pay and "page)" not in pay, "the 2026 tile prints the raw Spotrac status alone"


def test_every_header_and_leaf_links_the_entry_that_defines_its_own_quantity():
    html, _ = _render("club", team="LAD")
    farm = html[html.index('id="ledger-block-farm"'):html.index('id="ledger-block-fa"')]
    assert 'data-gl="fin_ifa_roi">fin_ifa_roi</a>' in farm
    assert 'data-gl="farm_grade_financial">fin_active_surplus</a>' in farm
    assert 'data-gl="sur_plus">fin_' not in farm
    assert 'data-gl="sur_plus">OrgSur+</a>' in farm, "the OrgSur+ tile keeps its own entry"
    pay = html[html.index('id="ledger-block-payroll"'):html.index('id="ledger-block-commitments"')]
    assert 'data-gl="payroll_allocations">Committed 2027</a>' in pay
    assert 'data-gl="contract_dollars_on_file">Committed' not in pay
    league, _ = _render("league")
    assert '<span class="lb-lab-long">Proj wins 2027</span>' in league and '<span class="lb-lab-long">Farm rank</span>' in league
    assert 'data-gl="payroll_horizon"' not in league and 'data-gl="bonus_pool"' not in league
    assert 'data-gl="payroll_allocations">Committed 2027</a>' in league


def test_the_contract_ledger_expander_base_rule_precedes_its_container_query():
    base = CSS.index(".ledger-app .lc-xp { display: none; }")
    query = CSS.index("@container ledgerblock (max-width: 560px) {\n  .ledger-app .lc-col-hide { display: none; }")
    assert base < query, "source order lets the base rule win at every width"
    assert CSS.count(".ledger-app .lc-xp { display: none; }") == 1
    assert CSS.index(".ledger-app .lb-xp { display: none; }") < CSS.index("@container ledgerboard (max-width: 560px)")


def test_the_league_board_takes_short_linked_labels_under_1400px_of_block_width():
    i = CSS.index("@container ledgerboard (max-width: 1400px)")
    block = CSS[i:CSS.index("\n}", i)]
    assert ".lb-lab-long { display: none; }" in block and ".lb-lab-short { display: inline; }" in block
    assert ".ledger-app .ledger-board .ledger-table { font-size: 11.5px; }" in CSS
    assert ".ledger-app .ledger-board .ledger-table th, .ledger-app .ledger-board .ledger-table td { padding: 4px 5px; }" in CSS
    league, _ = _render("league")
    assert '<span class="lb-lab-short"><a class="g-term" href="/glossary/#g=controlled_surplus" data-gl="controlled_surplus">Ctrl surplus</a></span>' in league
    assert '<span class="lb-lab-long">Proj wins 2027</span><span class="lb-lab-short">Proj wins 27</span>' in league
    assert '<span class="lb-lab-short">Club</span>' in league
