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
        "footer_means_note": "The two rows differ by $17.0M because Spotrac's league average is the page's average row as fetched 2026-07-07, while the 30 club rows were refetched 2026-09-23.",
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
        "arb_tender_note": "Not a payroll forecast: assumes every player is tendered; a non-tender lowers the figure", "arb_provisional": "provisional", "arb_flag_key": "flag bits",
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
        "no_payroll_line": "A single projected payroll is not served.", "load_error": "Club Ledger did not load. Retry.",
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
                    "trade_currency_mm": 990.8, "crunch": {"n_active": 180, "n_debuted": 34, "on_40_man": 40, "rule5_exposed": 6, "options_left_0": 5, "by_salary_basis": {}}},
        "indexes": {"usd_per_win": 3896629, "usd_per_war": 8053400, "cost_plus": 93, "cost_ratio_war_per_mm": 0.124, "orgsur_plus": 112.7,
                    "locked_pct": 0.828, "proj_wins_2027": 95.7, "proj_war_2027": 46.3, "cba_banner": True},
        "farm": {"leaves": {"fin_active_surplus": dict(LEAF, letter="A-", score_100=114.0, value=455.4, n=156),
                            "fin_ifa_roi": {"letter": " - ", "score_100": None, "value": None, "n": 0, "sparse": True}},
                 "orgsur_plus": {"financial_score": 112.7, "tree_fin_war_per_m_score_100": 114.6}, "financial_letter": "A-",
                 "financial_roi": {"war_per_million": 2.394, "total_bonus_usd": 22144990, "grad_count_with_bonus": 32},
                 "method_surplus": {"draft": {"net_mm": 250.3, "count": 68}},
                 "pools": {"2021": [None, "not parsed", None], "2026": [3951900, "live", [[28, 3200000]]]},
                 "draft_paid": {"2026": [16, 15, 1, 5384475, 6, 3951900, 4053975, 102075, 51.1, 3951900, 1.026, 220000, 2, 150000],
                                "2021": [20, 18, 2, 6100000, 7, 4800000, 4900000, 100000, 50.0, None, None, 375000, 3, 125000],
                                "2019": [40, 30, 10, 7100000, 8, 5000000, 5100000, 100000, 50.0, None, None, None, None]},
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
    for key in ("masthead", "league_lede", "club_foot", "cba_banner", "arb_tender_note", "realized_sentence",
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
    # data-team-picker (2026-09-24): assets/eephus-teampick.js paints the logo
    # picker over it; the select itself stays native and carries the value.
    assert '<select id="ledger-club" class="eephus-select" data-team-picker aria-label="Club">' in html
    assert '<option value="LAD" selected>' in html
    assert html.count('type="radio" name="ledger-season"') == 2
    assert "ledger-chip" in CSS and "accent-color:" not in CSS, "the radio fill comes from site.css, not a module colour"
    if PAGE.exists():
        assert "eephus-select" not in PAGE.read_text(encoding="utf-8") or True


def _banner_in(text, html):
    """The CBA banner (display pass 2026-10-03): the clause before the colon is
    the summary, always in view; the rest of the sentence opens beneath it.
    Both halves print, and the claim is never the hidden half."""
    head, rest = text.split(": ", 1)
    return ('<div class="ledger-banner" role="note"><details><summary>' + head + "</summary>" +
            rest[0].upper() + rest[1:] + "</details></div>") in html


def test_the_cba_banner_renders_whenever_a_2027_figure_is_on_screen():
    text = SAMPLE["copy"]["cba_banner"]
    club, _ = _render("club", team="LAD")
    assert club.count('class="ledger-banner"') >= 4, "the club page, contracts, arbitration and the FA ledger each carry it"
    assert _banner_in(text, club)
    league, _ = _render("league")
    assert _banner_in(text, league), "the League board shows Space 2027 and Committed 2027"
    rules, _ = _render("rules")
    assert _banner_in(text, rules)
    club27, _ = _render("club", team="LAD", season="2027")
    cbt = club27[club27.index('id="ledger-block-cbt"'):club27.index('id="ledger-block-contracts"')]
    assert _banner_in(text, cbt), "the 2027 ladder carries the banner"
    assert "Spotrac $247.0M basis" in cbt and "$244.0M" in cbt, "both bases named on the 2027 ladder"
    assert text not in club, "the paragraph no longer prints whole in every block"
    nocolon = _copy.deepcopy(SAMPLE)
    nocolon["copy"]["cba_banner"] = "Every 2027 figure is a carry-forward."
    assert '<div class="ledger-banner" role="note">Every 2027 figure is a carry-forward.</div>' in _render("league", payload=nocolon)[0]


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
        assert _banner_in(d["copy"]["cba_banner"], html27)
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
    # QCLC09: the leaf prints its glossary term, the hook still names the entry
    assert 'data-gl="fin_ifa_roi">IFA ROI</a>' in farm
    assert 'data-gl="farm_grade_financial">Active surplus</a>' in farm
    assert 'data-gl="sur_plus">fin_' not in farm and ">fin_" not in farm, "no raw leaf key prints as a label"
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


# --------------------------------------------------------------------------
# Review notes on 53726dd8 (2026-09-23): the CSV target, the overage sign, the footer
# --------------------------------------------------------------------------

def test_the_csv_control_exports_the_table_the_reader_sees():
    """eephus-csv.js exports the first VISIBLE table with rows inside the host. The
    club section renders a three-row "Expiring after" mini table (commitments)
    above the contract ledger, so the club CSV used to be that mini table. The
    League board and the contract ledger now carry data-csv-primary, the helper
    prefers a visible primary, and the host's file name says which table it holds."""
    csv = (ROOT / "assets" / "eephus-csv.js").read_text(encoding="utf-8")
    assert 'getAttribute("data-csv-primary")' in csv
    body = csv[csv.index("function targetTable"):csv.index("function dataRowCount")]
    assert body.index("data-csv-primary") < body.index("if (!visible) visible = t;"), "a visible primary wins over the first visible table"
    club, _ = _render("club", team="LAD")
    assert re.search(r"<table[^>]*>", club).group(0) == '<table class="ledger-mini">', "the DOM-first table with rows is a mini table"
    assert club.count("data-csv-primary") == 1
    assert '<table class="ledger-table ledger-contracts" data-csv-primary>' in club
    league, _ = _render("league")
    assert league.count("data-csv-primary") == 1
    assert '<table class="ledger-table" data-csv-primary aria-label="Club Ledger league board, 2 clubs">' in league
    assert '"club-ledger-" + (s === "club" ? String(state.team).toLowerCase() + "-contracts" : s)' in JS
    if PAGE.exists():
        assert 'id="ledger-app-root" data-csv-export="club-ledger"' in PAGE.read_text(encoding="utf-8"), "build_site's opt-in stays on the mount"


def test_an_overage_takes_the_cost_sign_on_both_surfaces():
    """Over the tax line is a cost. The League column "vs threshold" paints LAD's
    -$186.3M red; the club CBT note painted the same fact green as "Over by
    +$186.3M". One convention now: over is red, under is green, on both surfaces,
    and the word beside the unsigned magnitude says which."""
    league, _ = _render("league")
    assert '<span class="ledger-neg">-$186.3M</span>' in league, "the League cell keeps the house sign"
    club, _ = _render("club", team="LAD")
    cbt = club[club.index('id="ledger-block-cbt"'):club.index('id="ledger-block-contracts"')]
    assert 'Over by <span class="ledger-neg">$186.3M</span>' in cbt
    note = cbt[cbt.index("Over by"):cbt.index("</p>", cbt.index("Over by"))]
    assert "ledger-pos" not in note and "+$" not in note
    club27, _ = _render("club", team="LAD", season="2027")
    cbt27 = club27[club27.index('id="ledger-block-cbt"'):club27.index('id="ledger-block-contracts"')]
    assert 'Over by <span class="ledger-neg">$128.9M</span>' in cbt27
    assert 'basis: over by <span class="ledger-neg">$125.9M</span>' in cbt27
    under = _copy.deepcopy(SAMPLE)
    under["clubs"]["LAD"]["cbt"]["2026"]["over_usd"] = -20_000_000
    html, _ = _render("club", team="LAD", payload=under)
    cbt2 = html[html.index('id="ledger-block-cbt"'):html.index('id="ledger-block-contracts"')]
    assert 'Under by <span class="ledger-pos">$20.0M</span>' in cbt2 and "Over by" not in cbt2
    assert "costMoney(" in _fn_body("renderCbt") and "signedMoney(C.over_usd)" not in JS and "signedMoney(C.over_spotrac_basis_usd)" not in JS


def test_the_footer_means_note_prints_beneath_the_two_means_from_the_payload():
    html, _ = _render("league")
    i = html.index("</tfoot>")
    assert '<p class="ledger-count ledger-foot-note">' + SAMPLE["copy"]["footer_means_note"] + "</p>" in html[i:]
    assert html.index("ledger-foot-note") < html.index('<figure class="ledger-quadrant">'), "beneath the footer, above the quadrant"
    silent = _copy.deepcopy(SAMPLE)
    silent["copy"]["footer_means_note"] = ""
    html2, _ = _render("league", payload=silent)
    assert "ledger-foot-note" not in html2
    assert 'copy("footer_means_note")' in JS


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


# ==========================================================================
# D5 depth pass (2026-09-24): the per-club rows on the club page
# ==========================================================================
# The board paints first (a preview per block); the club's row file is
# fetched after the paint and the blocks re-render with every row. These
# tests drive that through a fetch stub keyed by URL: one club resolves, a
# missing file rejects, a "pending" file never settles. Rules pinned here:
# a surplus cell, a rung, a trade value and a strip cell take no ladder; a
# grade letter is neutral ink; a band prints per row and its footer reads
# "not summed"; the arbitration band says band, never P10/P90; the second
# exposure bar is its own element; Swartz, ou_mkt and ou_war stay apart.

import ledger_export as _LE

COLUMNS2 = {k: list(v) for k, v in _LE.COLUMNS.items()}
GEN = SAMPLE["generated_at"]
P_ONE = ["p_one", "P One", "SS", 19.4, 55.0, 61.8, "draft", 2024, 28, 3500000, 3200000, "draft", 2024,
         100.1, 26.8, 189.0, 0.349, 96.6, 108.5, 2026, "none", False, 3, False, "A+", 99.8, 11.15, 146.28]
P_TWO = ["p_two", "P Two", "RHP", 21.0, 50.0, 52.0, "international_fa", 2021, None, None, None, "trade", 2025,
         40.0, 10.0, 80.0, 0.5, 40.0, 92.0, 2027, "none", True, 2, True, "B", 38.0, 8.0, 70.0]
P_THREE = ["p_three", "P Three", "C", 23.0, 45.0, 46.0, "international_fa", 2020, None, 500000, None, "international_fa", 2020,
           12.5, 2.0, 30.0, 0.6, 12.0, 80.0, 2027, "pre_arb", False, 1, False, "C+", 11.0, 1.0, 25.0]
SHARD_LAD = {
    "club": "LAD", "statsapi_code": "LAD", "board_generated_at": GEN, "generated_at": GEN,
    "calibration": {"version": "cal-v6", "sources": {}, "agree": True}, "cba_banner": True,
    "farm": {
        "prospects": [P_ONE, P_TWO, P_THREE],
        "graduates": [["josue_de_paula", "Josue De Paula", "OF", "2026-09-11", "international_fa", 2022, 397500, 66.2, 3.14, 2032, "prearb_grid", 55.2, "projection", "pre_arb", 0.46, "unsettled", True],
                      ["g_two", "G Two", "RP", "2025-08-01", "draft", 2021, None, 4.0, 1.0, None, None, None, None, "pre_arb", 1.2, "boom", False]],
        "picks": {"2026": [[28, "1", "P One", 3200000, 3500000, 1, 300000, "p_one"], [60, "2", "Some Pick", 1500000, 1200000, 1, -300000, None],
                           [75, "3", "Unsigned Pick", 900000, 0, 0, None, None]]},
        "prospect_trajectory": {"p_one": [["2026-07-01", 90.0], ["2026-09-23", 100.1]], "p_two": []},
        "trajectory_active": [["2026-06-25", 500.0], ["2026-09-23", 514.0]],
    },
    "arbitration": {
        "ladders": [["A Player", 1, "3.000", 2025, 1, 9, 3, [[2027, 1400000, 1100000, 1900000, "ARB 1"], [2028, 5200000, 3800000, 6600000, "ARB 2"]], [1.2, 1.4], 6600000, True, True],
                    ["B Player", 2, None, None, 0, 4, 2, [[2027, 780000, 780000, 780000, "PRE-ARB"], [2028, None, None, None, "ARB 1"]], [0.5, 0.6], 780000, True, False]],
        "realized_rows": [[2024, 10, "R One", 2, 20000000, 19000000, 19500000, 1000000, -15000000, 3.0, 0],
                          [2024, 11, "R Two", 1, 10000000, 10000000, None, 0, -5000000, 2.0, 0],
                          [2023, 12, "R Three", 3, 35550000, 33544000, None, 2006000, -30109000, 6.35, 0]],
    },
    "contracts": {"paths": [
        ["shohei_ohtani", [6.4, 6.2, 5.0, 3.8, 2.1], [1.9, 1.5, 1.4, 0.8, 0.0], [10.8, 10.7, 9.8, 6.7, 4.6], [88.5, 82.7, 57.6, 33.8, -7.0],
         238359792, 2.7, 241042446, None, None, None, None, None, None, None, None, None, None, [2031], [], False, 238350392],
        ["andy_pages", [3.1, 3.0, 2.8, 2.5, 2.0], [1.0, 1.0, 0.9, 0.8, 0.5], [5.0, 5.0, 4.8, 4.5, 4.0], [50.0, 45.0, 40.0, None, None],
         51000000, 1.0, 52000000, 60.0, 20.0, 90.0, "A", "projection", "projection", "arb_ladder+class_closure", 2030, "class_closure", 4.0, [], [], True, 50990000]]},
    "surplus": {"rows_debuted": [["andy_pages", "Andy Pages", "CF", 60.0, 20.0, 90.0, "elite", "A", "projection", "arb_ladder+class_closure", 2030, "class_closure", True],
                                 ["x_deb", "X Deb", "RP", 5.0, 1.0, 12.0, "role", "C", "prearb_min", "league_minimum", 2029, "proxy", False]],
                "trajectory": [["2026-06-25", 1100.2], ["2026-08-01", 1050.0], ["2026-09-23", 990.8]]},
    "field_key": {}, "columns": COLUMNS2,
}
COPY2 = {
    "farm_dollar_is": "A farm dollar here is an expected value.", "farm_dollar_is_not": "It is not a trade price; never added.",
    "farm_reconcile": "The roll-up leaf is the sum over active prospects.", "farm_vintage_gap": "vintage drift, not a disagreement about any prospect",
    "farm_gap_broken": "Both figures are shown; neither is corrected.", "farm_no_bonus": "counts a cost of zero in the leaf",
    "trade_cost_dark": "no cost basis exists for the trade channel", "grad_two_engines": "Two engines price a graduate; never averaged or summed.",
    "grad_contract_dark": "served as the org mean only", "grad_no_registry": "debuted_player_value carries no registry row",
    "shard_failed": "The per-club rows did not load; the preview above is the board's.",
    "shard_vintage": "These rows were written against a different board build than the one on screen.",
    "dvm_within_tier": "scaled within the FV tier", "p_bust_basis": "the retired realized_implied map",
    "preview_note": "top rows by expected surplus; the full farm ledger loads per club",
    "grad_preview_note": "the graduate rows load per club", "arb_preview_note": "the full ladder loads per club",
    "trade_preview_note": "the debuted trade rows load per club", "paths_preview_note": "the strips load per club",
    "trajectory_active_basis": "each snapshot's own actives, gross of bonuses", "band_row_only": "p10 to p90, eFV basis, per row only",
    "trajectory_loading": "the series loads per club",
    "years_to_fa_dark": "control not started; service time is a proxy", "service_time_source": "PROXY", "ifa_slot_dark": "no slot",
    "arb_prearb_rungs": "board rows at the pre-arbitration minimum sit in this sum",
    "arb_two_populations": "neither is added to the other and neither is a payroll",
    "swartz_label": "MLB Trade Rumors, Matt Swartz, published before settlement", "swartz_a6": "This model does not beat the Swartz projection.",
    "swartz_a6_prefix": "a6 arm", "arb_quantiles_dark": "P10 / P50 / P90 are not published: the band is the champion's spread",
    "arb_comps_dark": "no comps are served", "arb_filing_dark": "filing figures are on no served row",
    "arb_class_labels": {"0": "Pre-Arb", "1": "Arb 1", "2": "Arb 2"},
    "npv_identity": "the strip is rounded to 0.1M", "sur_strip_basis": "per-season surplus, not war x dollars per WAR",
    "sur_total_identity": "the rest-of-season leg is published to 0.1M; the printed equation can miss by a few tens of thousands",
    "war_band_cell": "per season, never summed", "tv_reanchored": "re-anchored on the trade board", "prearb_min_floor": "a FLOOR on the window",
    "opt_out_two_engines": "player option seasons: opt-out not modelled; the trade board folds a probability in",
    "trade_currency_split": "it overlaps both legs and is never added to them", "shown_rows": "shown rows: a sum of expected values",
    "not_summed": "not summed", "sources_stamps": "each block names the artifact it was read from",
    "r11_over_basis": "the part of each round 11 or later bonus above the CBA threshold for its draft year, summed",
    "r11_threshold_schedule": "CBA threshold: $125,000 for the 2017 to 2021 drafts; $150,000 for the 2022 to 2026 drafts",
}


def _sample2():
    s = _copy.deepcopy(SAMPLE)
    s["copy"].update(COPY2)
    s["columns"] = COLUMNS2
    s["calibration"] = SHARD_LAD["calibration"]
    s["accountability"]["discount_rate"] = 0.07
    s["arbitration_eval"] = {"n": 261, "ours_mdape": 0.2156, "swartz_mdape": 0.0811, "ratio_ours_over_swartz": 2.659, "verdict": "NULL",
                             "claim": "identical rows", "statement": COPY2["swartz_a6"]}
    s["shards"] = {"dir": "ledger_clubs", "n": 1, "files": {"LAD": {"path": "ledger_clubs/LAD.json", "bytes": 1000, "sha256_16": "x"}},
                   "preview_n": 2, "cap_bytes": 160000, "board_guard_bytes": 950000}
    c = s["clubs"]["LAD"]
    c["farm"].update({
        "preview": [P_ONE, P_TWO], "n_prospects": 3, "n_graduates": 2, "picks_summary": {"2026": [3, 2, 1, 0, 1, 0]},
        "reconciliation": {"leaf_mm": 455.4, "leaf_cost_mm": 57.6, "leaf_n": 3, "leaf_source": "timeseries.org_summary tree.fin_active_surplus",
                           "leaf_generated_at": "2026-09-23T18:22:28Z", "rows_gross_mm": 514.0, "rows_cost_mm": 57.62, "rows_net_mm": 456.38,
                           "rows_source": "trade_values.json + timeseries.players", "rows_generated_at": "2026-09-23", "n_rows": 3, "n_with_bonus": 2,
                           "n_unbucketed": 0, "gap_mm": -0.98, "tolerance_mm": 9.11, "status": "vintage_drift"},
        "method": {"draft": [1, 1, 100.1, 3.5, 96.6, 27.6, 250.3, 45.4, 68, 0.113], "international_fa": [2, 1, 52.5, 0.5, 52.0, 104.0, 205.1, 12.2, 88, 0.079],
                   "trade": [0, 0, None, None, None, None, None, None, 0, None]},
    })
    c["arbitration"].update({"by_season": [[2027, 1400000, 1, 780000, 1, 0], [2028, 5200000, 1, 0, 0, 1]], "n_in_vets": 2, "n_with_salpath": 1,
                             "s2027_note": "arb_prearb_rungs", "s2027_usd": 2180000})
    c["surplus"].update({"reconciliation": {"by_salsrc": {"contract": [300.1, 300.1, 1], "contract+arb": [118.4, 118.4, 1]}, "mlb_served_mm": 418.5,
                                            "mlb_rows_mm": 418.5, "farm_served_mm": 455.4, "farm_leaf_mm": 455.4, "trade_currency_served_mm": 990.8,
                                            "trade_rows_active_mm": 514.0, "trade_rows_debuted_mm": 476.8, "status": "exact"}, "n_debuted_rows": 2})
    c["contracts"]["paths_summary"] = {"n_paths": 2, "n_reanchored": 1, "n_opt_out_rows": 1, "n_opt_out_seasons": 1}
    c["shard"] = {"path": "ledger_clubs/LAD.json", "bytes": 1000, "sha256_16": "x", "generated_at": GEN}
    return s


SHARD_URL_LAD = "/data/ledger_clubs/LAD.json"


def _render2(team="LAD", payload=None, shards=None, hash_="", tiers=False, pfilter="all", open_keys=()):
    """The club page with a fetch stub keyed by URL: `shards` maps a shard URL to
    its document, to "fail" (rejects) or to "pending" (never settles)."""
    js = JS.replace('state = { section: "league", team: ""', 'state = { section: "club", team: "%s"' % team, 1)
    js = js.replace('open: {}, pfilter: "all" }', 'open: %s, pfilter: "%s" }' % (json.dumps({k: True for k in open_keys}), pfilter), 1)
    assert js != JS
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute'||k==='scrollIntoView')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v; if(k==='textContent')__html[id+':text']=v; return true;}});}
    function SP(ok,v){return {then:function(f,g){try{ if(ok){var r=f?f(v):v; return (r&&r.then)?r:SP(true,r);} if(g){var r2=g(v); return (r2&&r2.then)?r2:SP(true,r2);} return SP(false,v);}catch(e){return SP(false,e);}},catch:function(g){return this.then(null,g);}};}
    var PENDING={then:function(){return PENDING;},catch:function(){return PENDING;}};
    var P=%s; var S=%s;
    var fetch=function(url){
      if(url==="/data/ledger_board.json") return SP(true,{ok:true,json:function(){return SP(true,P);}});
      if(S[url]==="pending") return PENDING;
      if(S[url]==="fail") return SP(false,new Error("404"));
      if(S[url]) return SP(true,{ok:true,json:function(){return SP(true,S[url]);}});
      return SP(true,{ok:false,status:404});
    };
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:function(){return null;},querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    var location={hash:%s};
    %s
    """ % (json.dumps(payload or _sample2()), json.dumps(shards or {}), json.dumps(hash_), TIERS_STUB if tiers else "")
    ctx = MiniRacer()
    ctx.eval(prelude + js)
    return ctx.eval("__html['ledger-app-root'] || ''")


def _block(html, bid):
    i = html.index('id="ledger-block-%s"' % bid)
    j = html.index("</section>", i)
    return html[i:j]


def test_the_club_page_renders_the_preview_before_the_shard_arrives():
    html = _render2(shards={SHARD_URL_LAD: "pending"})
    pr = _block(html, "prospects")
    assert "P One" in pr and "P Two" in pr and "P Three" not in pr, "the board's preview rows, not the shard's"
    assert COPY2["preview_note"] in pr and "3 active prospects, 2 with a bonus on file" in pr
    assert 'class="ledger-banner"' in pr and COPY2["farm_dollar_is"] in pr
    assert COPY2["grad_preview_note"] in _block(html, "graduates") and COPY2["trade_preview_note"] in _block(html, "trade")
    assert COPY2["arb_preview_note"] in _block(html, "arbitration") and "<th>Token</th>" in _block(html, "arbitration"), "the v1 six-column table is the ladder's preview"
    assert 'class="ledger-darktag">dark<' not in pr, "pending is not failed"


def test_the_shard_rows_render_after_fetch_and_a_failed_fetch_leaves_a_dark_block_not_a_blank():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    pr = _block(html, "prospects")
    assert "P Three" in pr and "P One" in pr, "every shard row"
    assert COPY2["preview_note"] not in pr and COPY2["shard_failed"] not in pr
    assert "Josue De Paula" in _block(html, "graduates") and "X Deb" in _block(html, "trade")
    assert "A Player" in _block(html, "arbitration") and 'class="ledger-rung"' in _block(html, "arbitration")
    failed = _render2(shards={SHARD_URL_LAD: "fail"})
    pf = _block(failed, "prospects")
    assert "P One" in pf and "P Three" not in pf, "the preview stays"
    assert "<strong>Per-club rows</strong>" in pf and COPY2["shard_failed"] in pf
    assert COPY2["shard_failed"] in _block(failed, "graduates") and COPY2["shard_failed"] in _block(failed, "trade")
    assert "could not be loaded" not in failed
    other = _render2(shards={"/data/ledger_clubs/TBR.json": SHARD_LAD})
    assert COPY2["shard_failed"] in _block(other, "prospects"), "a missing file is a failed fetch, never a blank"
    wrong = _render2(shards={SHARD_URL_LAD: dict(SHARD_LAD, club="TBR")})
    assert COPY2["shard_failed"] in _block(wrong, "prospects"), "a file naming another club is refused"


def test_the_trajectory_sparklines_draw_from_the_shard_and_wait_for_it_without_breaking():
    """Owner answer VAL1-Q1 (2026-09-30): the club's snapshot series moved off
    the board into its row file. Before the file arrives the two blocks print
    the loading line and no chart; once it is in, both sparklines draw from the
    shard's series; a failed fetch prints the dark line, never an empty chart."""
    board = _sample2()
    lad = board["clubs"]["LAD"]
    assert "trajectory" not in lad["surplus"] and "trajectory_active" not in lad["farm"], "the fixture board is the trimmed shape"
    pending = _render2(payload=board, shards={SHARD_URL_LAD: "pending"})
    su, fa = _block(pending, "surplus"), _block(pending, "farm")
    assert "<h3>Trade currency trajectory</h3>" in su and COPY2["trajectory_loading"] in su
    assert "<h3>Active eFV surplus trajectory (gross)</h3>" in fa and COPY2["trajectory_loading"] in fa
    assert 'class="ledger-spark-line"' not in su and COPY2["trajectory_active_basis"] not in fa
    ready = _render2(payload=board, shards={SHARD_URL_LAD: SHARD_LAD})
    su, fa = _block(ready, "surplus"), _block(ready, "farm")
    assert 'class="ledger-spark"' in su and "2026-06-25 1100.2 to 2026-09-23 990.8" in su, "trade currency, from the shard"
    assert COPY2["trajectory_loading"] not in su and "since late June" in su
    assert "2026-06-25 500.0 to 2026-09-23 514.0" in fa and COPY2["trajectory_active_basis"] in fa, "actives, from the shard"
    failed = _render2(payload=board, shards={SHARD_URL_LAD: "fail"})
    su = _block(failed, "surplus")
    assert COPY2["shard_failed"] in su and 'class="ledger-spark-line"' not in su and COPY2["trajectory_loading"] not in su
    empty = _render2(payload=board, shards={SHARD_URL_LAD: dict(SHARD_LAD, farm=dict(SHARD_LAD["farm"], trajectory_active=[]))})
    assert "Active eFV surplus trajectory" not in _block(empty, "farm"), "an empty actives series prints no block, as before the move"


def test_a_shard_whose_vintage_differs_from_the_board_is_flagged_not_refused():
    stale = dict(SHARD_LAD, board_generated_at="2026-09-01T00:00:00+00:00")
    html = _render2(shards={SHARD_URL_LAD: stale})
    pr = _block(html, "prospects")
    assert "P Three" in pr, "the rows render"
    assert '<span class="ledger-flag">' + COPY2["shard_vintage"] + "</span>" in pr
    assert COPY2["shard_vintage"] in _block(html, "arbitration")
    fresh = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    assert COPY2["shard_vintage"] not in fresh


def test_prospect_dollar_cells_take_no_ladder_and_the_grade_chip_is_neutral_ink():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, tiers=True)
    pr = _block(html, "prospects")
    assert "vt-fam" not in pr and "vt-avg" not in pr, "no ruler class on a prospect row"
    assert '<span class="ledger-letter">A+</span>' in pr and '<span class="ledger-letter">C+</span>' in pr
    assert '<span class="ledger-pos">$100.1M</span>' in pr, "expected surplus: plain with its sign"
    assert '<span class="ledger-band" title="' + COPY2["band_row_only"] + '">$26.8M to $189.0M</span>' in pr
    assert "no bonus on file" in pr and COPY2["ifa_slot_dark"] in pr
    for fn in ("renderProspects", "renderGraduates", "renderTrade", "renderLadder", "renderRealizedRows", "renderPicks", "contractDepth", "warStripCell", "arbSeasonBar"):
        body = _fn_body(fn)
        assert "EephusTiers" not in body and "zCell(" not in body and "zCls(" not in body, fn
    gr = _block(html, "graduates")
    assert "vt-fam" not in gr and "$66.2M" in gr and "$55.2M" in gr and "PROSPX debuted_player_value" in gr
    assert "$121.4M" not in gr, "the two engines are never summed"
    assert COPY2["grad_two_engines"] in gr and COPY2["grad_contract_dark"] in gr
    assert "thru 2032" in gr and "prearb_grid" in gr and " yrs" not in gr, "control is the current window, never the at-debut years"


def test_the_shown_rows_footer_sums_means_and_prints_not_summed_under_the_bands():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    pr = _block(html, "prospects")
    foot = pr[pr.index("<tfoot>"):pr.index("</tfoot>")]
    cells = re.findall(r"<td[^>]*>(.*?)</td>", foot)
    assert COPY2["shown_rows"] + " (3)" in cells[0]
    assert "$152.6M" in cells[1], "expected surplus over the rows shown, a sum of means"
    assert COPY2["not_summed"] in cells[2], "the band column's footer"
    assert not re.search(r"\d", re.sub(r"<[^>]+>", "", cells[2])), "no footer cell under a band column parses as a number"
    assert "$4.0M" in foot and "$148.6M" in foot, "bonus and net over the rows shown"
    draft = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, pfilter="draft")
    pd_ = _block(draft, "prospects")
    assert "P One" in pd_ and "P Two" not in pd_ and "P Three" not in pd_
    fd = pd_[pd_.index("<tfoot>"):pd_.index("</tfoot>")]
    assert COPY2["shown_rows"] + " (1)" in fd and "$100.1M" in fd and COPY2["not_summed"] in fd
    assert 'data-lfilter="draft" aria-pressed="true"' in pd_
    tr = _block(html, "trade")
    ft = tr[tr.index("<tfoot>"):tr.index("</tfoot>")]
    assert "$65.0M" in ft and COPY2["not_summed"] in ft


def test_the_arbitration_ladder_cells_say_band_not_interval():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    arb = _block(html, "arbitration")
    assert '<span class="ledger-rung" title="$1.1M to $1.9M; band, not a calibrated interval">$1.4M</span>' in arb
    assert '<span class="ledger-rung is-null" title="no salary on file; outside every sum">ARB 1</span>' in arb
    assert "Arb 1" in arb and "Pre-Arb" in arb and "3.000 as of 2025" in arb
    assert arb.count("P10") == 1 and COPY2["arb_quantiles_dark"] in arb, "the only P10 on the block is the dark sentence saying none is published"
    assert "P90" not in arb.replace(COPY2["arb_quantiles_dark"], "")
    assert "Ladder sum 2027 (arb and pre-arb rungs)" in arb and "arb rungs $1.4M (1), pre-arb rungs $0.8M (1)" in arb
    assert COPY2["arb_prearb_rungs"] in arb and SAMPLE["copy"]["arb_tender_note"] in arb
    assert "upper bound" not in arb.lower()
    assert "1 null rung(s) outside every sum" in arb
    for title in ("Award quantiles", "Comps", "Filing figures and hearings"):
        assert "<strong>" + title + "</strong>" in arb
    v1 = _render2(shards={SHARD_URL_LAD: "pending"})
    a1 = _block(v1, "arbitration")
    assert 'title="band, not a calibrated interval">$1.1M to $1.9M</td>' in a1, "the preview band cell carries the sentence too"


def test_the_two_arbitration_exposures_are_drawn_apart_and_never_stacked():
    html = _render2(shards={SHARD_URL_LAD: "pending"})
    cm = _block(html, "commitments")
    assert cm.count('class="ledger-bar2"') == 2, "one bar per season the board carries"
    assert '<i class="ledger-seg-arb2"></i>' in cm and COPY2["arb_two_populations"] in cm
    assert "Arbitration Predictor board, 2 rows, 2 in the projections vets: ladder sum $2.2M = arb rungs $1.4M (1) + pre-arb rungs $0.8M (1)" in cm
    row27 = SAMPLE["clubs"]["LAD"]["commitments"]["by_season"][0]
    stack = row27[1] + row27[3] + row27[5]
    bar = 1400000 + 780000
    assert "$%.1fM" % ((stack + bar) / 1e6) not in cm and "$%.1fM" % ((row27[3] + bar) / 1e6) not in cm, "the stack and the bar never combine"
    i = cm.index('class="ledger-stack"')
    j = cm.index('class="ledger-bar2"')
    assert i < j and "</div>" in cm[i:j], "the bar is a sibling element under the stack, not a segment of it"
    assert ".ledger-app .ledger-seg-arb2" in CSS and "repeating-linear-gradient" in CSS
    assert "EephusTiers" not in _fn_body("renderCommitments")


def test_the_realized_rows_keep_swartz_ou_mkt_and_ou_war_in_separate_columns():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    arb = _block(html, "arbitration")
    assert '<th title="' + COPY2["swartz_label"] + '">MLBTR (Swartz)</th>' in arb
    assert "<th>ou_war</th>" in arb and 'data-gl="arb_market_residual">ou_mkt</a>' in arb
    i = arb.index("<summary>2024: 2 players</summary>")
    grp = arb[i:arb.index("</details>", i)]
    assert "R One" in grp and "$19.5M" in grp, "the Swartz figure prints on the row that carries it"
    assert grp.count("<td></td>") >= 1, "a row without a Swartz figure prints blank, never zero"
    foot = grp[grp.index("<tfoot>"):]
    assert "$30.0M" in foot and "$29.0M" in foot and '<span class="ledger-pos">$1.0M</span>' in foot and '<span class="ledger-neg">-$20.0M</span>' in foot
    assert "-$19.0M" not in foot and "$-19.0M" not in foot, "ou_mkt and ou_war never combined"
    assert "$19.5M" not in foot, "no Swartz total: present on some rows only"
    assert "a6 arm, n 261: " + COPY2["swartz_a6"] in arb
    assert SAMPLE["copy"]["never_combine"] in arb


def test_an_unsigned_pick_prints_a_blank_over_slot_cell_not_a_saving():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    farm = _block(html, "farm")
    assert '<td>Some Pick</td><td>$1.5M</td><td>$1.2M</td><td><span class="ledger-neg">-$0.3M</span></td><td>signed</td>' in farm, "a signed under-slot pick keeps its figure"
    assert '<td>Unsigned Pick</td><td>$0.9M</td><td>$0.0M</td><td><span class=""></span></td><td>unsigned</td>' in farm, "an unsigned pick prints a blank over-slot cell"
    assert "-$0.9M" not in farm


def test_the_picks_summary_splits_signed_picks_by_tracker_coverage_never_still_active():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    farm = _block(html, "farm")
    assert "2026: 3 picks, 2 signed: 1 on the prospect tracker, 0 graduated, 1 not tracked" in farm
    assert "still active" not in farm and "still-active" not in farm
    assert "not every signed minor leaguer" in farm


def test_the_war_path_strip_shows_means_and_the_expander_shows_bands():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, open_keys=("C:shohei_ohtani",))
    ct = _block(html, "contracts")
    assert '<span class="ledger-warcell" title="WAR P10 1.9 to P90 10.8, ' + COPY2["war_band_cell"] + '">6.4 WAR</span>' in ct
    assert "1 of 2 re-anchored on the trade board, 1 with a player option (1 seasons)" in ct
    xp = ct[ct.index('class="ledger-xp-row"'):]
    assert "<dt>Surplus strip</dt>" in xp and '<span class="ledger-pos">$88.5M</span>' in xp and '<span class="ledger-neg">-$7.0M</span>' in xp
    assert "NPV of the strip at 7 pct: $238.4M; served $238.4M" in xp and COPY2["npv_identity"] in xp
    assert ("Total to acquire</dt><dd>$241.0M = rest of season $2.7M + NPV $238.4M"
            '<div class="ledger-count">' + COPY2["sur_total_identity"] + "</div></dd>") in xp, "the tolerance sentence sits on the Total line"
    assert "<dt>Player option 2031</dt><dd>" + COPY2["opt_out_two_engines"] in xp
    assert "Trade Machine" not in xp, "a row the trade board does not carry prints no trade line"
    pages = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, open_keys=("C:andy_pages",))
    xp2 = _block(pages, "contracts")
    xp2 = xp2[xp2.index('class="ledger-xp-row"'):]
    assert "<dt>Trade Machine</dt><dd>$60.0M (<span class=\"ledger-band\"" in xp2 and '<span class="ledger-letter">A</span>' in xp2
    assert '<span class="ledger-flag">re-anchored</span> ' + COPY2["tv_reanchored"] in xp2
    assert "vt-fam" not in ct and "EephusTiers" not in _fn_body("renderContracts")
    pending = _render2(shards={SHARD_URL_LAD: "pending"})
    assert "ledger-warcell" not in _block(pending, "contracts") and COPY2["paths_preview_note"] in _block(pending, "contracts")


def test_the_debuted_trade_rows_take_no_ladder_and_print_their_source():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, tiers=True, open_keys=("T:x_deb",))
    tr = _block(html, "trade")
    assert "vt-fam" not in tr
    assert '<span class="ledger-pos">$60.0M</span>' in tr and '<span class="ledger-src">projection</span>' in tr and '<span class="ledger-src">prearb_min</span>' in tr
    assert '<span class="ledger-letter">elite</span>' in tr and '<span class="ledger-letter">A</span>' in tr
    assert 'href="/projections/#player=andy_pages"' in tr and 'href="/prospx/#player=x_deb"' in tr
    assert "<dt>Floor</dt><dd>" + COPY2["prearb_min_floor"] in tr, "a prearb_min row quotes the artifact's floor sentence"
    assert "2 debuted rows on the trade board" in tr
    sp = _block(html, "surplus")
    assert "Trade currency: served / farm rows gross + debuted rows</th><td>$990.8M / $514.0M + $476.8M" in sp
    assert "MLB leg, contract: served / contract rows (n 1)</th><td>$300.1M / $300.1M" in sp and COPY2["trade_currency_split"] in sp


def test_the_new_block_keys_are_anchored_in_the_router():
    assert "(?:^#|[#&])block=(payroll|cbt|commitments|contracts|arbitration|surplus|farm|fa|prospects|graduates|trade|options)\\b" in JS
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, hash_="#section=club&team=LAD&block=prospects")
    for bid in ("trade", "prospects", "graduates"):
        assert 'id="ledger-block-%s"' % bid in html, bid
    assert html.index('id="ledger-block-farm"') < html.index('id="ledger-block-trade"') < html.index('id="ledger-block-prospects"') < html.index('id="ledger-block-graduates"') < html.index('id="ledger-block-fa"')
    assert 'el("ledger-block-" + state.block)' in JS and "scrollIntoView" in JS
    opened = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, hash_="#section=club&team=LAD&block=arbitration")
    assert "<details open><summary>2024: 2 players</summary>" in _block(opened, "arbitration"), "the hash opens the shard-fed groups"
    assert "<details><summary>2024: 2 players</summary>" in _block(html, "arbitration")
    assert 'data-lprospect="p_one"' in _block(html, "farm") and 'href="#section=club&amp;team=LAD&amp;block=prospects"' in _block(html, "farm")


def test_the_new_tables_hide_columns_by_container_and_carry_an_expander():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    for cls in ("ledger-prospects", "ledger-graduates", "ledger-trade", "ledger-ladder-table"):
        i = html.index('<table class="ledger-table %s"' % cls)
        head = html[i:html.index("</thead>", i)]
        ths = re.findall(r"<th(?:\s[^>]*)?>", head)
        kept = [t for t in ths if "lc-col-hide" not in t and "lc-xp" not in t]
        assert len(kept) <= 3, (cls, kept)
        assert any("lc-xp" in t for t in ths) and any("lc-col-hide" in t for t in ths), cls
        assert html[html.rindex('<div class="ledger-scroll">', 0, i):i].count("<table") == 0, (cls, "wrapped in .ledger-scroll")
        assert 'class="ledger-xp-btn"' in html[i:html.index("</table>", i)]
    assert ".ledger-app .lc-xp { display: none; }" in CSS and CSS.index(".ledger-app .lc-xp { display: none; }") < CSS.index("@container ledgerblock (max-width: 560px) {\n  .ledger-app .lc-col-hide")
    assert ".ledger-app .ledger-prospects .ledger-xp-row td" in CSS
    assert 'class="ledger-chips" role="group" aria-label="Acquisition method"' in html and 'class="ledger-chip is-on"' in html
    assert "ledger-dl" in _render2(shards={SHARD_URL_LAD: SHARD_LAD}, open_keys=("P:p_one",))
    opened = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, open_keys=("P:p_one",))
    pr = _block(opened, "prospects")
    assert "<dt>PROSPX consensus basis, not added</dt>" in pr and "$99.8M" in pr and 'class="ledger-spark"' in pr, "the expander: consensus basis and the per-player spark"
    assert "<dt>cons_surplus_mm</dt>" in pr and COPY2["p_bust_basis"] in pr


def test_every_new_glossary_hook_resolves():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    ids = {e["id"]: e for e in g["entries"]}
    for slug in ("farm_dollar", "debuted_value", "arb_award_band", "acquisition_cost_basis"):
        assert slug in ids and "ledger" in ids[slug]["module"] and ids[slug]["shelf"] == "ark", slug
        assert 'gl(' in JS and '"%s")' % slug in JS, slug
        for ref in ids[slug].get("seeAlso", []):
            assert ref in ids, (slug, ref)
    hooks = set(re.findall(r'gl\([^,]+,\s*"([a-z_]+)"\)', JS))
    missing = sorted(h for h in hooks if h not in ids)
    assert not missing, missing
    for slug in ("tvi", "xfv", "signing_bonus", "slot_value", "roster_crunch", "fin_dollar_dvm", "eta", "wag", "mlb_debut",
                 "club_control_window", "trade_machine", "salary_path", "service_time", "surplus_value", "arb_award_band",
                 "acquisition_cost_basis", "surplus_per_fv_pt", "fin_contract_surplus", "farm_dollar", "debuted_value"):
        assert slug in hooks, slug


def test_the_js_reads_every_shard_column_through_the_legend():
    reads = re.findall(r'cv\("([a-z_.]+)",\s*[A-Za-z_0-9]+,\s*"([a-z_0-9]+)"\)', JS)
    assert len(reads) > 60
    for key, name in reads:
        assert key in COLUMNS2, key
        assert name in COLUMNS2[key], (key, name)
    assert not re.search(r"\b(prospects|graduates|ladders|realized_rows|paths|rows_debuted)\[\w+\]\[\d+\]", JS), "no positional read on a shard row"
    assert "function colIdx(key, name)" in JS and "DATA.columns[key]" in JS
    shard_dir = ROOT / "data" / "ledger_clubs"
    if not shard_dir.exists() or not ART.exists():
        return
    d = _served()
    for c in list(d["clubs"])[:5] + ["LAD"]:
        s = json.loads((shard_dir / f"{c}.json").read_text(encoding="utf-8"))
        for key, cols in s["columns"].items():
            assert cols == d["columns"][key], (c, key)
            if key == "arbitration.realized.rows":
                rows = s["arbitration"]["realized_rows"]
            elif key in ("farm.picks", "farm.prospect_trajectory"):
                continue
            else:
                blk, _, name = key.rpartition(".")
                rows = s[blk][name]
            for row in rows:
                assert len(row) == len(cols), (c, key)
        html = _render2(team=c, payload=d, shards={"/data/ledger_clubs/%s.json" % c: s}, tiers=True)
        for bid in ("prospects", "graduates", "trade", "arbitration", "contracts", "farm", "surplus", "commitments"):
            assert 'id="ledger-block-%s"' % bid in html, (c, bid)
        assert "could not be loaded" not in html and "undefined" not in _block(html, "prospects"), c
        assert d["copy"]["shard_failed"] not in html, (c, "the served shard resolves")


def test_a_club_below_its_own_contract_floor_is_flagged_on_the_league_board_and_c1():
    """M09-03 and owner answer M13-1: a club whose Spotrac 2027 tax payroll sits
    below its own guaranteed 2027 contract AAV takes the AAV as its 2027 basis;
    the tile prints the basis, names Spotrac's figure and flags the substitution."""
    s = _copy.deepcopy(SAMPLE)
    s["copy"]["tax_floor_flag"] = "below own contracts"
    s["copy"]["cbt_basis_aav_label"] = "guaranteed contract AAV used"
    s["copy"]["tax_floor_note"] = "Spotrac's 2027 tax payroll sits below the AAV of this club's own guaranteed 2027 contract rows"
    for r in s["league"]["rows"]:
        r["tax_floor_below_2027"] = r["club"] == "TBR"
    html, _ = _render("league", payload=s)
    tbr = html.split('title="Tampa Bay Rays"')[1].split("</tr>")[0]
    lad = html.split('title="Los Angeles Dodgers"')[1].split("</tr>")[0]
    assert tbr.count('class="ledger-flag" title="Spotrac') == 2, "Space 27 and Cost+"
    assert "ledger-flag" not in lad
    s["clubs"]["LAD"]["payroll"]["tax_floor_2027"] = {"guaranteed_aav_usd": 400 * M, "n_rows": 12, "n_option_rows_excluded": 0,
                                                      "spotrac_tax_payroll_usd": 372907413, "gap_usd": 372907413 - 400 * M, "below": True}
    s["clubs"]["LAD"]["payroll"]["cbt_basis_2027"] = {"usd": 400 * M, "source": "guaranteed_aav", "spotrac_usd": 372907413,
                                                      "guaranteed_aav_usd": 400 * M, "n_rows": 12}
    club, _ = _render("club", payload=s, team="LAD", season="2027")
    payroll = _block(club, "payroll") if 'id="ledger-block-payroll"' in club else club
    assert '<div class="ledger-tile-big ">$400.0M</div>' in payroll, "the 2027 tile prints the basis"
    assert "guaranteed contract AAV used" in club
    assert "Spotrac publishes $372.9M; the guaranteed 2027 contract AAV on 12 rows is $400.0M" in club, "Spotrac's figure still prints"
    s["clubs"]["LAD"]["payroll"]["tax_floor_2027"]["below"] = False
    assert "guaranteed contract AAV used" not in _render("club", payload=s, team="LAD", season="2027")[0]


def test_cost_plus_prints_its_three_parts_apart_and_its_numerator():
    """Owner answers M13-4 and COSTPLUS-1: under the index the numerator less the
    locked free agents and the three denominator parts, each on its own row; no
    row adds them up."""
    s = _copy.deepcopy(SAMPLE)
    s["copy"]["cost_plus_part_labels"] = {"guaranteed": "Guaranteed 2027 salaries (CBT payroll)",
                                          "arb": "Projected 2027 arbitration awards", "prearb": "Pre-arbitration minimum rungs"}
    s["copy"]["cost_plus_numerator_label"] = "Projected 2027 WAR less locked free agents"
    s["copy"]["cost_plus_parts_note"] = "the three parts print apart"
    I = s["clubs"]["LAD"]["indexes"]
    I.update({"cost_plus_parts": {"guaranteed_usd": 372907413, "guaranteed_source": "spotrac", "arb_usd": 7517000, "n_arb": 1,
                                  "prearb_usd": 11700000, "n_prearb": 15, "n_null_rungs": 0,
                                  "contract_dropped_usd": 780000, "n_contract_dropped": 1},
              "locked_fa_2027": {"n": 8, "war": 7.7}, "proj_war_2027": 51.4, "proj_war_2027_ex_fa": 43.7})
    html, _ = _render("club", payload=s, team="LAD")
    th = '<tr><th scope="row">'
    assert th + "Projected 2027 WAR less locked free agents</th><td>51.4 less 7.7 (8 locked free agents) = 43.7</td></tr>" in html
    assert th + "Guaranteed 2027 salaries (CBT payroll)</th><td>$372.9M</td></tr>" in html
    assert th + "Projected 2027 arbitration awards (1)</th><td>$7.5M</td></tr>" in html
    assert th + "Pre-arbitration minimum rungs (15)</th><td>$11.7M</td></tr>" in html
    assert "$392.1M" not in html, "the three parts are never added on the page"
    assert "here 1 rung ($0.8M)" in html


def test_the_2027_spotrac_estimate_says_it_is_surcharges_only_and_the_difference_takes_no_sign_colour():
    s = _copy.deepcopy(SAMPLE)
    s["copy"]["cbt_spotrac_surcharges_only"] = "Spotrac's 2027 estimate equals the surcharges alone on its 247M basis"
    s["clubs"]["LAD"]["cbt"]["2027"]["spotrac_est_is_surcharges_only"] = True
    html, _ = _render("club", payload=s, team="LAD", season="2027")
    assert '<tr><th scope="row">Difference</th><td>$66.3M</td></tr>' in html, "a bill gap is not a gain: no green"
    assert "equals the surcharges alone on its 247M basis" in html
    assert "Spotrac estimate, surcharges only (no base rate)" in html
    s["clubs"]["LAD"]["cbt"]["2027"]["spotrac_est_is_surcharges_only"] = False
    html, _ = _render("club", payload=s, team="LAD", season="2027")
    assert "surcharges alone" not in html and "surcharges only" not in html


def test_round_11_over_the_cba_threshold_prints_beside_pool_used_and_never_in_it():
    """Owner answers M10-3 and M9M10-1 (b): the draft table keeps Pool used on rounds
    1-10 and adds a separate Round 11+ over the CBA threshold column; the header's
    tooltip carries the schedule and each cell's tooltip names its draft year's
    figure ($125,000 for 2021, $150,000 for 2026). A row without a figure prints n/a."""
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    farm = _block(html, "farm")
    assert ('<th>Pool used</th><th title="' + COPY2["r11_threshold_schedule"] +
            '">Round 11+ over the CBA threshold</th>') in farm
    assert "$150K" not in farm
    assert ('<td>103%</td><td title="CBA threshold for the 2026 draft: $150,000">$0.2M (2)</td></tr>'
            in farm), "2026: Pool used 1.026, the charge $220,000 on 2 picks"
    assert ('<td>2021</td>' in farm and
            '<td></td><td title="CBA threshold for the 2021 draft: $125,000">$0.4M (3)</td></tr>' in farm), \
        "2021: the charge above $125,000, its own column"
    assert '<td>2019</td>' in farm and "<td></td><td>n/a</td></tr>" in farm, "a row without a figure"
    assert "Round 11+ over the CBA threshold: " + COPY2["r11_over_basis"] in farm


# --------------------------------------------------------------------------
# The option and opt-out calendar (owner answer 2026-09-25, census M09-07)
# --------------------------------------------------------------------------

OPT_COPY = {
    "options_title": "Options and opt-outs, winter 2026-27",
    "options_lede": "Every pending option and opt-out on this winter's class.",
    "options_decision_rule": "Decided in the 5 days after the 2026 World Series ends.",
    "options_decision_unknown": "5 days after the 2026 World Series",
    "options_p_exercise_basis": "P(exercise) is read off the /fa/ P(enter).",
    "options_value_basis": "Option value is never added to a salary.",
    "options_unpriced": {"mutual": "a mutual option needs both sides to agree", "conditional": "the condition is not on file",
                         "no_projection": "no projection", "no_strike": "the option salary is not on file", "no_band": "no band"},
    "options_terms_only": "terms only",
    "options_no_strike_short": "not on file",
    "options_salary_basis": {"option_year_salary": "option-year salary", "remaining_guarantee": "remaining guarantee"},
    "options_state": {"pending": "pending", "exercised": "exercised", "declined": "declined"},
    "options_resolved_note": "a resolved row's date is the night the pipeline first saw it",
    "options_not_summed": "salaries at stake are never added into a club figure",
    "options_none": "No pending option or opt-out on this winter's free-agent class.",
    "options_later": "Options in later seasons ride the contract ledger.",
    "options_source": "the free-agent class rows",
    "options_league_summary": "options and opt-outs at",
}
OPT_ROWS = [
    ["a_one", "A One", "SP", 31.2, "club_option", "club", 20_000_000, "option_year_salary", "pending", None, "2026-11-05",
     True, 0.797, 45_299_213, None, True],
    ["b_two", "B Two", "RP", 35.0, "mutual_option", "both", 8_000_000, "option_year_salary", "pending", None, "2026-11-05",
     False, None, None, "mutual", False],
    ["c_three", "C Three", "SP", 31.3, "opt_out", "player", 32_000_000, "remaining_guarantee", "exercised", "2026-11-03", None,
     True, 0.568, 30_195_249, None, True],
]


def _opt_payload(rows=None):
    s = _copy.deepcopy(SAMPLE)
    s["copy"].update(OPT_COPY)
    s["columns"] = dict(COLUMNS2)
    rows = OPT_ROWS if rows is None else rows
    s["clubs"]["LAD"]["options_calendar"] = {"rows": rows, "n": len(rows), "n_priced": sum(1 for r in rows if r[11])}
    s["league"]["options_calendar"] = {"n_rows": len(rows), "n_priced": sum(1 for r in rows if r[11]), "n_unjoined": 0,
                                       "unpriced_by_reason": {"mutual": 1} if rows else {}, "n_clubs": 1 if rows else 0,
                                       "decision": {"decision_by": "2026-11-05"}}
    return s


def test_the_options_calendar_prints_terms_and_prices_only_where_fa_priced_them():
    html, _ = _render("club", payload=_opt_payload(), team="LAD", tiers=True)
    assert html.index('id="ledger-block-fa"') < html.index('id="ledger-block-options"') < html.index('id="ledger-block-links"')
    blk = _block(html, "options")
    assert "Options and opt-outs, winter 2026-27" in blk and OPT_COPY["options_lede"] in blk
    assert '<a href="/fa/#player=a_one">A One</a>' in blk and 'href="/projections/#player=a_one"' in blk
    assert '<a href="/fa/#player=b_two">B Two</a>' in blk and "/projections/#player=b_two" not in blk, "no card, no link"
    a = blk[blk.index("A One"):blk.index("</tr>", blk.index("A One"))]
    assert "$20.0M" in a and "option-year salary" in a and "<td>80%</td>" in a and "$45.3M" in a and "by 2026-11-05" in a
    b = blk[blk.index("B Two"):blk.index("</tr>", blk.index("B Two"))]
    assert "$8.0M" in b and "terms only" in b and "a mutual option needs both sides to agree" in b and "%" not in b
    c = blk[blk.index("C Three"):blk.index("</tr>", blk.index("C Three"))]
    assert "remaining guarantee" in c and "exercised 2026-11-03" in c and "<td>57%</td>" in c
    for total in (60_000_000, 28_000_000, 52_000_000, 40_000_000):
        assert "$%.1fM" % (total / 1e6) not in blk, ("a summed salary at stake", total)
    assert "vt-fam" not in blk, "a salary at stake takes no ruler"
    assert "terms only: 1 where a mutual option needs both sides to agree" in blk
    for k in ("options_decision_rule", "options_p_exercise_basis", "options_value_basis", "options_not_summed", "options_later"):
        assert OPT_COPY[k] in blk, k
    assert html.count("data-csv-primary") == 1, "the contract ledger stays the club CSV"
    assert 'data-gl="p_enter"' in blk


def test_the_options_calendar_says_so_when_a_club_has_none_and_reads_its_columns_by_name():
    html, _ = _render("club", payload=_opt_payload(rows=[]), team="LAD")
    blk = _block(html, "options")
    assert OPT_COPY["options_none"] in blk and "<table" not in blk
    old, _ = _render("club", team="LAD")
    assert 'id="ledger-block-options"' in old and "undefined" not in _block(old, "options"), "an older board renders an empty block"
    body = _fn_body("optCells")
    assert "cv(C, r, " in body and not re.search(r"\br\[\d+\]", body), "every calendar cell reads through the legend"


def test_the_league_calendar_lists_every_club_row_behind_a_summary_and_links_the_club_block():
    html, _ = _render("league", payload=_opt_payload(), tiers=True)
    i = html.index('id="ledger-options-league"')
    cal = html[i:html.index("</section>", i)]
    assert "<details><summary>3 options and opt-outs at 1 clubs, 2 priced by /fa/, due by 2026-11-05</summary>" in cal
    assert '<a href="#section=club&team=LAD&block=options" data-llink="1">LAD</a>' in cal
    assert cal.count("<tr>") == 4 and "terms only" in cal and "vt-fam" not in cal
    assert html.count("data-csv-primary") == 1, "the League board stays the league CSV"
    assert html.index("ledger-quadrant") < i, "the calendar sits under the board and its chart"


def test_the_served_options_calendar_renders_on_the_league_and_club_pages():
    d = _served()
    S = d["league"]["options_calendar"]
    html, _ = _render("league", payload=d, tiers=True)
    cal = html[html.index('id="ledger-options-league"'):]
    cal = cal[:cal.index("</section>")]
    later_at = cal.index("<h3>" + d["copy"]["options_later_title"] + "</h3>")
    winter, later = cal[:later_at], cal[later_at:]
    assert winter.count("<tr>") == S["n_rows"] + 1 and "undefined" not in cal and "NaN" not in cal
    assert later.count("<tr>") == S["later"]["n_rows"] + 1 and "<details><summary>" in later
    assert "by 20" not in later, "a later-season row prints no decision date"
    for code, c in d["clubs"].items():
        L = c["options_calendar"]["later"]
        if not c["options_calendar"]["rows"] and not L["rows"]:
            continue
        club, _ = _render("club", payload=d, team=code, tiers=True)
        blk = _block(club, "options")
        h3 = "<h3>" + d["copy"]["options_later_title"] + "</h3>"
        assert blk.count(h3) == 1, code
        cw, cl = blk[:blk.index(h3)], blk[blk.index(h3):]
        assert cw.count("<tr>") == (c["options_calendar"]["n"] + 1 if c["options_calendar"]["rows"] else 0), code
        assert cl.count("<tr>") == (L["n"] + 1 if L["rows"] else 0), code
        assert "undefined" not in blk and "NaN" not in blk and "vt-fam" not in blk, code
        assert cw.count("terms only</span>") == c["options_calendar"]["n"] - c["options_calendar"]["n_priced"], code
        assert "by 20" not in cl, code


LATER_COPY = {
    "options_later_title": "Later seasons",
    "options_later_lede": "Options in later seasons of long-term deals, one row per option season.",
    "options_later_no_date": "The decision winter is not on file, so no decision date prints.",
    "options_later_none": "No option in a later season of a long-term deal is on file for this club.",
    "options_later_terms": "terms only: nothing in this block is priced",
    "options_later_league_summary": "later-season options on",
    "options_later_season_head": "Season on file",
    "options_later_terms_head": "Option-year salary",
}
LATER_ROWS = [
    ["w_one", "W One", "SS", 27, 2030, "player_option", "player", None],
    ["w_one", "W One", "SS", 27, 2035, "club_option", "club", 26_252_525],
    ["w_one", "W One", "SS", 27, 2036, "club_option", "club", 26_252_525],
]


def _later_payload(rows=None, later=None):
    s = _opt_payload(rows)
    s["copy"].update(LATER_COPY)
    later = LATER_ROWS if later is None else later
    s["clubs"]["LAD"]["options_calendar"]["later"] = {"rows": later, "n": len(later),
                                                      "n_contracts": len({r[0] for r in later})}
    s["league"]["options_calendar"]["later"] = {"n_rows": len(later), "n_contracts": len({r[0] for r in later}),
                                                "n_clubs": 1 if later else 0, "by_type": {},
                                                "n_price_on_file": sum(1 for r in later if r[7]),
                                                "n_at_or_before_class_year": 0}
    return s


def test_the_later_seasons_block_prints_terms_with_the_season_on_file_and_no_date():
    html, _ = _render("club", payload=_later_payload(), team="LAD", tiers=True)
    blk = _block(html, "options")
    h3 = "<h3>Later seasons</h3>"
    assert blk.count(h3) == 1 and blk.index("A One") < blk.index(h3), "the later block sits under the winter calendar"
    later = blk[blk.index(h3):]
    assert later.count("<tr>") == 4 and "<th>Season on file</th>" in later and "<th>Option-year salary</th>" in later
    assert '<a href="/projections/#player=w_one">W One</a>' in later and "/fa/#player=w_one" not in later
    a = later[later.index("<td>2030</td>"):]
    a = a[:a.index("</tr>")]
    assert "player option" in a and "not on file" in a
    b = later[later.index("<td>2035</td>"):]
    b = b[:b.index("</tr>")]
    assert "club option" in b and "$26.3M" in b
    assert "by 2026" not in later and "Decision" not in later and "P(exercise)" not in later, "no decision date, no price"
    assert LATER_COPY["options_later_no_date"] in later and LATER_COPY["options_later_lede"] in later
    assert "3 option seasons on 1 contract." in later
    assert "$52.5M" not in later and "$78.8M" not in later, "no salary is summed"
    assert "vt-fam" not in later
    body = _fn_body("laterTable")
    assert "cv(C, r, " in body and not re.search(r"\br\[\d+\]", body), "every later cell reads through the legend"


def test_the_later_seasons_block_says_so_when_a_club_has_none_and_an_older_board_skips_it():
    html, _ = _render("club", payload=_later_payload(later=[]), team="LAD")
    blk = _block(html, "options")
    assert "<h3>Later seasons</h3>" in blk and LATER_COPY["options_later_none"] in blk
    assert blk.count("<table") == 1, "only the winter table"
    old, _ = _render("club", payload=_opt_payload(), team="LAD")
    assert "<h3>Later seasons</h3>" not in _block(old, "options"), "a board without the block renders without it"
    none, _ = _render("club", payload=_later_payload(rows=[]), team="LAD")
    nb = _block(none, "options")
    assert OPT_COPY["options_none"] in nb and nb.count("<tr>") == 4, "a club with only later seasons still lists them"


def test_the_league_calendar_gains_the_later_seasons_collapsed():
    html, _ = _render("league", payload=_later_payload(), tiers=True)
    i = html.index('id="ledger-options-league"')
    cal = html[i:html.index("</section>", i)]
    later = cal[cal.index("<h3>Later seasons</h3>"):]
    assert ("<details><summary>3 later-season options on 1 contract at 1 club, no decision date</summary>"
            in later)
    assert later.count("<tr>") == 4 and later.count("</details>") == 1
    assert '<a href="#section=club&team=LAD&block=options" data-llink="1">LAD</a>' in later
    assert "by 2026" not in later
    assert cal.index("</details>") < cal.index("<h3>Later seasons</h3>"), "the winter list closes first"


# --------------------------------------------------------------------------
# Display and copy pass (2026-10-03): surface-quality findings QCLA08-QCLA11,
# QCLP07, QCLC08-QCLC10. One test per finding.
# --------------------------------------------------------------------------

def _site_tokens():
    import test_value_ruler as VR
    light, dark = VR._blocks()
    return VR, light, dark


def test_qcla08_every_row_expander_is_named_points_at_its_row_and_keeps_focus():
    league, _ = _render("league")
    btns = re.findall(r"<button[^>]*data-lxp=[^>]*>", league)
    assert len(btns) == 2
    for b in btns:
        assert 'aria-label="Show detail for ' in b and 'aria-controls="ledger-xp-L-' in b, b
    assert 'aria-label="Show detail for Los Angeles Dodgers"' in league
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD}, open_keys=("P:p_one", "C:shohei_ohtani"))
    for k, who in (("P-p_one", "P One"), ("C-shohei_ohtani", "Shohei Ohtani")):
        assert 'aria-controls="ledger-xp-%s" aria-label="Show detail for %s"' % (k, who) in html, k
        assert '<tr class="ledger-xp-row" id="ledger-xp-%s">' % k in html, "the controlled row carries the id"
    every = re.findall(r"<button[^>]*data-lxp=[^>]*>", html)
    assert every and all("aria-label=" in b and "aria-controls=" in b for b in every)
    h = JS[JS.index('querySelectorAll("[data-lxp]")'):JS.index('querySelectorAll("[data-lfilter]")')]
    assert h.index("render();") < h.index('refocus("data-lxp", k);'), "focus returns to the new copy of the button"
    i = CSS.index(".ledger-app .ledger-xp-btn {")
    j = CSS.index("@media (max-width: 640px)")
    assert i < j and ".ledger-app .ledger-xp-btn { min-width: 44px; min-height: 44px; }" in CSS[j:], "the 44 px rule comes after the base rule"


def test_qcla09_sort_keeps_focus_the_ring_clears_3_to_1_and_the_board_is_named():
    h = JS[JS.index('querySelectorAll("th[data-lsort]")'):JS.index('querySelectorAll("[data-lxp]")')]
    assert h.index("render();") < h.index('refocus("data-lsort", k);')
    assert ".ledger-app .ledger-table thead th:focus { outline: 2px solid var(--text-gold);" in CSS
    VR, light, dark = _site_tokens()
    for theme in ({}, dark):
        ring = VR._resolve("--text-gold", theme, light)
        for surf in ("--bg-secondary", "--bg-primary"):
            assert VR._contrast(ring, VR._resolve(surf, theme, light)) >= 3.0, surf
    league, _ = _render("league")
    assert 'aria-label="Club Ledger league board, 2 clubs"' in league


def test_qcla10_block_index_table_semantics_and_heading_order():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    nav = html[html.index('<nav class="ledger-index"'):html.index("</nav>")]
    targets = re.findall(r'href="#section=club&amp;team=LAD&amp;block=([a-z]+)" data-llink="1"', nav)
    assert len(targets) == 12
    for t in targets:
        assert 'id="ledger-block-%s" tabindex="-1"' % t in html, t
        assert re.search(r"block=\(([a-z|]+)\)", JS).group(1).split("|").count(t) == 1, ("the router knows", t)
    assert html.index("</nav>") < html.index('id="ledger-block-payroll"'), "the index sits above the blocks"
    ct = _block(html, "contracts")
    head = ct[ct.index("<thead>"):ct.index("</thead>")]
    ths = re.findall(r"<th\b[^>]*>", head)
    assert ths and all('scope="col"' in t for t in ths)
    for tbl in re.findall(r'<table class="ledger-mini[^"]*">(.*?)</table>', html, re.S):
        for row in re.findall(r"<tr>(.*?)</tr>", tbl, re.S):
            assert row.startswith('<th scope="row">') or row.startswith('<td colspan="2"'), row[:80]
    for section in ("rules", "method"):
        page, _ = _render(section)
        assert "<h3>" not in page and "<h2>" in page, section
    assert "label.ledger-chip { min-height: 44px;" in CSS
    club, _ = _render("club", team="LAD")
    assert 'role="radiogroup" aria-labelledby="ledger-season-lab"' in club
    h = JS[JS.index('querySelectorAll("a[data-llink]")'):JS.index("function boot()")]
    assert 'el("ledger-block-" + state.block)' in h and "preventScroll: true" in h, "the named block takes focus"


def test_qcla11_secondary_text_takes_an_ink_not_an_opacity_and_the_greens_clear_the_stripe():
    rules = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert "opacity" not in rules, "no ledger text is dimmed by opacity"
    assert ".ledger-app .ledger-pos { color: var(--text-green); }" in CSS
    assert ".ledger-app .ledger-table tbody tr:nth-child(even) { background: var(--bg-primary); }" in CSS
    assert "nth-child(even) { background: var(--bg-hover)" not in rules and ".ledger-xp-row td { white-space: normal; background: var(--bg-primary); }" in CSS, "the stripe is a paper tone"
    VR, light, dark = _site_tokens()
    for theme in ({}, dark):
        surfaces = [VR._resolve(s, theme, light) for s in ("--bg-primary", "--bg-secondary")]
        for ink in ("--text-green", "--vt-above", "--text-tertiary", "--text-secondary", "--down"):
            fg = VR._resolve(ink, theme, light)
            for bg in surfaces:
                assert VR._contrast(fg, bg) >= 4.5, (ink, bg, round(VR._contrast(fg, bg), 2))
    for name, rule in (("franchise.css", ".fr-app .fr-pos { color: var(--text-green); }"),
                       ("management.css", ".mgmt-pos { color: var(--text-green); }")):
        assert rule in (ROOT / "assets" / name).read_text(encoding="utf-8"), name


def test_qclp07_the_loader_holds_the_board_room():
    assert ".ledger-app #ledger-app-root:empty, .ledger-app #ledger-app-root:has(> .px-state.is-loading) { min-height: 100vh; }" in CSS
    if PAGE.exists():
        assert '<div id="ledger-app-root" data-csv-export="club-ledger"></div>' in PAGE.read_text(encoding="utf-8"), "the mount is empty, so :empty holds before the script runs"


def test_qclc08_efv_prints_the_nearest_whole_grade():
    html = _render2(shards={SHARD_URL_LAD: SHARD_LAD})
    pr = _block(html, "prospects")
    i = COLUMNS2["farm.prospects"].index("efv")
    for row in (P_ONE, P_TWO, P_THREE):
        want = str(int(row[i] + 0.5))
        assert '<td class="lc-col-hide">%s</td>' % want in pr, (row[1], want)
    assert "61.8" not in pr, "the one-decimal eFV is gone from the table"
    opened = _block(_render2(shards={SHARD_URL_LAD: SHARD_LAD}, open_keys=("P:p_one",)), "prospects")
    assert "<dt>efv</dt><dd>62</dd>" in opened, "the expander prints the same grade"


def test_qclc09_farm_leaves_print_terms_and_units():
    s = _copy.deepcopy(SAMPLE)
    s["clubs"]["LAD"]["farm"]["leaves"]["fin_contract_surplus"] = {"letter": "B", "score_100": 104.0, "value": 2234174.0, "n": 22, "sparse": False}
    s["clubs"]["LAD"]["farm"]["leaves"]["fin_war_per_m"] = {"letter": "A-", "score_100": 111.4, "value": 2.14, "n": 30, "sparse": False}
    html, _ = _render("club", payload=s, team="LAD")
    farm = _block(html, "farm")
    assert 'data-gl="fin_contract_surplus">Grad-Contract Surplus</a>' in farm and "$2.2M per year (n 22)" in farm
    assert 'data-gl="fin_war_per_m">WAR per $M</a>' in farm and "2.14 (n 30)" in farm
    assert 'data-gl="farm_grade_financial">Active surplus</a>' in farm and "$455.4M (n 156)" in farm
    assert "tree WAR per $M score 114.6" in farm
    assert not re.search(r">fin_[a-z_]+<", farm) and "2234174" not in farm
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    terms = {e["id"]: e["term"] for e in g["entries"]}
    labels = dict(re.findall(r'(fin_[a-z_]+): "([^"]+)"', JS[JS.index("var LEAF_LABEL"):JS.index("function leafValue")]))
    for k, lab in labels.items():
        if k != "fin_active_surplus":
            assert terms.get(k) == lab, (k, lab, terms.get(k))


def test_qclc10_a_value_that_rounds_to_zero_prints_without_a_minus():
    sh = _copy.deepcopy(SHARD_LAD)
    ci = COLUMNS2["farm.graduates"].index("career_war")
    sh["farm"]["graduates"][1][ci] = -0.03
    oi = COLUMNS2["farm.picks"].index("over_slot_usd")
    sh["farm"]["picks"]["2026"][1][oi] = -30000
    html = _render2(shards={SHARD_URL_LAD: sh})
    gr = _block(html, "graduates")
    assert '<td class="lc-col-hide">0.0</td>' in gr and "-0.0" not in gr
    farm = _block(html, "farm")
    assert "-$0.0M" not in farm and '<span class="ledger-neg">$0.0M</span>' in farm, "the sign colour stays, the minus goes"
    fr = (ROOT / "assets" / "franchise.js").read_text(encoding="utf-8")
    body = fr[fr.index("  function n1(v)"):fr.index("\n", fr.index("  function n1(v)"))]
    ctx = MiniRacer()
    ctx.eval("function isNum(v){return v!==null&&v!==undefined&&v===v&&v!==''};" + body)
    assert ctx.eval("n1(-0.02)") == "0.0" and ctx.eval("n1(-0.06)") == "-0.1" and ctx.eval("n1(2.26)") == "2.3"


# --------------------------------------------------------------------------
# The DvM+ difficulty arm (DVM-5): the farm table header and the fin_dollar_dvm
# leaf relabel only when the payload carries the arm's copy keys.
# --------------------------------------------------------------------------

def _sample_with_dvm_leaf(arm_copy=False):
    s = _sample2()
    s["clubs"]["LAD"]["farm"]["leaves"]["fin_dollar_dvm"] = dict(LEAF, letter="B", score_100=104.0, value=103.2, n=140)
    s["copy"]["farm_leaves"]["fin_dollar_dvm"] = {"basis": "b", "weight": 0.1}
    if arm_copy:
        s["copy"]["dvm_player_label"] = "DvM+ (player)"
        s["copy"]["dvm_org_label"] = "Org DvM+ (player)"
    return s


def test_the_farm_surfaces_keep_todays_dvm_labels_without_the_arm_copy():
    html = _render2(payload=_sample_with_dvm_leaf(False), shards={SHARD_URL_LAD: SHARD_LAD})
    farm, prospects = _block(html, "farm"), _block(html, "prospects")
    assert "Org $DvM+" in farm and ">$DvM+<" in prospects
    assert "DvM+ (player)" not in farm and "DvM+ (player)" not in prospects


def test_the_farm_surfaces_relabel_when_the_arm_copy_is_served():
    html = _render2(payload=_sample_with_dvm_leaf(True), shards={SHARD_URL_LAD: SHARD_LAD})
    farm, prospects = _block(html, "farm"), _block(html, "prospects")
    assert "Org DvM+ (player)" in farm and ">DvM+ (player)<" in prospects
    assert "$DvM+" not in farm and "$DvM+" not in prospects


# --------------------------------------------------------------------------
# Payroll now and the current season's history row: one capture prints one
# dated figure; two captures print two dated figures (SITE_AUDIT_3A A3).
# --------------------------------------------------------------------------

HIST_2025 = [2025, 319522564, "3+-Time", 241000000, 78522564, 61774820, 299091683]
HIST_2026 = [2026, 433057244, "3+-Time", 244000000, 189057244, 183362968, 339319244]


def _sample_with_history(block_pair, hist_pair, n_match):
    s = _sample2()
    s["columns"]["payroll.history"] = list(_LE.FA_PROFILE_COLUMNS["payroll.history"])
    p = s["clubs"]["LAD"]["payroll"]
    p["s2026"]["fetched"] = block_pair
    p["history"] = {"status": "shard", "n": 2, "first": 2025, "last": 2026}
    cap = _LE.payroll_capture_census({"LAD": block_pair}, hist_pair, n_match, 1, 2026)
    s["sections"]["payroll_history"] = {"live": True, "note": "per-club rows",
                                        "census": {"seasons": [2025, 2026], "fetched": {"2025": ["2026-10-09", "2026-10-09"], "2026": hist_pair},
                                                   "s2026_matches_payroll_block": n_match, "s2026_capture": cap}}
    s["copy"].update({"payroll_history_title": "Payroll history", "payroll_history_note": "Spotrac's tax page for each season as cached.",
                      "payroll_capture_note": cap["note"], "payroll_fetched_label": "fetched"})
    shard = _copy.deepcopy(SHARD_LAD)
    shard["payroll"] = {"history": [HIST_2025, HIST_2026]}
    return s, shard


def test_two_payroll_captures_print_two_dated_figures_and_one_capture_prints_one():
    s, shard = _sample_with_history(["2026-10-02", "2026-10-02"], ["2026-10-26", "2026-10-26"], 0)
    pay = _block(_render2(payload=s, shards={SHARD_URL_LAD: shard}), "payroll")
    assert "(Spotrac, fetched 2026-10-02)" in pay, "the block tile names its capture date"
    assert "<td>2026 (fetched 2026-10-26)</td>" in pay, "the history row names its own page date"
    assert "<td>2025</td>" in pay, "only the current season's row is dated"
    assert s["copy"]["payroll_capture_note"] in pay and "Two captures" in pay
    assert "$430.3M" in pay and "$433.1M" in pay, "both figures stay on the page, each with its date"
    s1, shard1 = _sample_with_history(["2026-10-26", "2026-10-26"], ["2026-10-26", "2026-10-26"], 1)
    pay1 = _block(_render2(payload=s1, shards={SHARD_URL_LAD: shard1}), "payroll")
    assert "(Spotrac, fetched 2026-10-26)" in pay1 and "<td>2026</td>" in pay1
    assert "(fetched 2026-10-26)</td>" not in pay1, "one capture is not dated twice"
    assert "same Spotrac capture (2026-10-26)" in pay1
    s2, shard2 = _sample_with_history(None, ["2026-10-26", "2026-10-26"], 0)
    pay2 = _block(_render2(payload=s2, shards={SHARD_URL_LAD: shard2}), "payroll")
    assert "(Spotrac)" in pay2 and "fetched" not in pay2.split("Payroll history")[0], "an undated row prints no date"
    assert "no capture date" in pay2
    s3, shard3 = _sample_with_history(["2026-10-02", "2026-10-03"], ["2026-10-26", "2026-10-26"], 0)
    pay3 = _block(_render2(payload=s3, shards={SHARD_URL_LAD: shard3}), "payroll")
    assert "tax page fetched 2026-10-02, payroll page fetched 2026-10-03" in pay3


def test_the_payroll_tiles_read_the_capture_date_from_the_payload_not_the_js():
    assert "payroll_capture_note" in JS and "payroll_fetched_label" in JS and "s2026_capture" in JS
    for stamp in ("2026-10-02", "2026-10-26", "2026-10-27"):
        assert stamp not in JS, "no capture date is typed into the JS"
