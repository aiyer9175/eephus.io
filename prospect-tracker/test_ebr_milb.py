# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ebr_milb.py and tools/build_ebr_milb.py: level-relative eBR for the minor leagues
(task EBR_Q6B_MILB_CARDS, owner answer EBR-Q6 (b)).

Synthetic frames only: the plan (which pool and which K a level-season is shrunk
toward), the event-typed steal normalisation, the outcome backoff layer, the W
sub-total, the identity receipts, the split-half and continuity aggregates, the
card payload's filters, and the isolation pins. Nothing here reads the runner
record, a cache or the network.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_ebr_milb as B  # noqa: E402
import ebr  # noqa: E402
import ebr_milb as M  # noqa: E402


# --------------------------------------------------------------------------
# synthetic raw cells
# --------------------------------------------------------------------------
def _raw(scale: float, n: int = 4000, jitter: float = 0.0) -> dict:
    """24 monotone cells of runs-to-end: more runners, fewer outs."""
    base = {0: 0.5, 1: 0.9, 2: 1.1, 3: 1.4, 4: 1.3, 5: 1.7, 6: 1.9, 7: 2.3}
    out_f = {0: 1.0, 1: 0.55, 2: 0.25}
    cells = {}
    for b in range(8):
        for o in (0, 1, 2):
            cells[f"{b}|{o}"] = {"n": n, "mean": base[b] * out_f[o] * scale + jitter * ((b + o) % 3 - 1) * 0.01,
                                 "var": 1.4}
    return cells


def _units():
    return {("aaa", 2026): _raw(1.00, jitter=1), ("aa", 2026): _raw(1.05, jitter=2),
            ("single_a", 2025): _raw(0.95, jitter=1), ("single_a", 2026): _raw(1.02, jitter=3),
            ("single_a", 2024): _raw(0.99, jitter=2)}


# --------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------
def test_a_level_with_several_seasons_is_shrunk_toward_its_own_pool():
    plan = M.make_plan(_units())
    for s in (2024, 2025, 2026):
        p = plan[("single_a", s)]
        assert p["pool_kind"] == "level" and p["k_source"] == "level"
        assert sorted(p["pool_units"]) == [("single_a", 2024), ("single_a", 2025), ("single_a", 2026)]
    assert plan[("single_a", 2024)]["pool"] == plan[("single_a", 2026)]["pool"]


def test_a_level_with_one_season_is_shrunk_toward_that_seasons_all_milb_table():
    raw = _units()
    plan = M.make_plan(raw)
    p = plan[("aaa", 2026)]
    assert p["pool_kind"] == "season_all" and p["k_source"] == "all_milb"
    assert sorted(p["pool_units"]) == [("aa", 2026), ("aaa", 2026), ("single_a", 2026)]
    want = ebr.pool_table({u: raw[u] for u in p["pool_units"]})
    assert p["pool"] == want
    assert plan[("aa", 2026)]["K"] == p["K"]
    assert plan[("aa", 2026)]["pool"] == p["pool"]


def test_k_is_inside_the_clip_and_a_lone_unit_refuses():
    plan = M.make_plan(_units())
    for p in plan.values():
        assert ebr.K_CLIP[0] <= p["K"] <= ebr.K_CLIP[1]
    with pytest.raises(ebr.EbrRefusal):
        M.make_plan({("aaa", 2026): _raw(1.0)})


def test_the_shrunk_table_of_a_unit_is_monotone():
    plan = M.make_plan(_units())
    raw = _units()
    for u, p in plan.items():
        t = ebr.shrunk_table(raw[u], p["pool"], p["K"], M.unit_key(u))
        assert len(t) == 24 and not ebr.monotone_violations(t)


def test_unit_keys_round_trip():
    assert M.parse_unit_key(M.unit_key(("high_a", 2026))) == ("high_a", 2026)


# --------------------------------------------------------------------------
# steals typed by event but not by movement reason
# --------------------------------------------------------------------------
def _rn(rows):
    cols = ("event_type", "movement_reason", "start", "end", "is_out")
    return pd.DataFrame(rows, columns=cols)


def test_an_event_typed_steal_goes_on_the_steal_reason():
    rn = _rn([("stolen_base_2b", "r_adv_play", "1B", "2B", False),      # the feed's miss
              ("stolen_base_2b", "r_stolen_base_2b", "1B", "2B", False),  # already right
              ("stolen_base_2b", "r_adv_play", "2B", "3B", False),      # second runner of a double steal
              ("stolen_base_2b", "r_adv_play", None, "2B", False),      # duplicate entry, no start
              ("stolen_base_3b", "r_adv_play", "2B", "3B", False),
              ("stolen_base_home", "r_adv_throw", "3B", "score", False),
              ("stolen_base_2b", "r_adv_play", "1B", None, True),       # an out
              ("single", "r_adv_play", "1B", "2B", False)])
    out, n = M.normalise_runners(rn)
    assert n == 3
    assert list(out["movement_reason"]) == ["r_stolen_base_2b", "r_stolen_base_2b", "r_adv_play",
                                            "r_adv_play", "r_stolen_base_3b", "r_stolen_base_home",
                                            "r_adv_play", "r_adv_play"]
    assert list(rn["movement_reason"])[0] == "r_adv_play"   # the input is not changed


# --------------------------------------------------------------------------
# the backoff layer
# --------------------------------------------------------------------------
class _Op(dict):
    pass


def _op(y=2):
    return {"c": "H", "k": 1, "o": 0, "L": "x", "y": y, "levels": [None, None, None, ("H", 1, 0, "x")]}


def test_without_level_counts_the_backoff_is_the_core_backoff():
    opps = [_op(2)] * 30 + [_op(3)] * 10
    pool = {"H|1": {"2": 50, "3": 50}, "H|1|0": {"2": 50, "3": 50}, "H|1|0|x": {"2": 50, "3": 50}}
    a = ebr.Backoff(opps, pool).pi(opps[0])
    b = M.MilbBackoff(opps, pool, None).pi(opps[0])
    assert a == b


def test_level_counts_move_the_pooled_prior_toward_the_level():
    opps = [_op(2)]
    pool = {"H|1": {"2": 100, "3": 100}, "H|1|0": {"2": 100, "3": 100}, "H|1|0|x": {"2": 100, "3": 100}}
    level = {"H|1|0|x": {"2": 400, "3": 10}}
    base = M.MilbBackoff(opps, pool, None)._pool_pi("H", 1, 0, "x")
    lvl = M.MilbBackoff(opps, pool, level)._pool_pi("H", 1, 0, "x")
    assert lvl[2] > base[2] and lvl[3] < base[3]
    assert abs(sum(lvl.values()) - 1.0) < 1e-9


# --------------------------------------------------------------------------
# W: balls in the dirt
# --------------------------------------------------------------------------
def test_dirt_advances_are_counted_and_never_in_the_parts():
    table = {f"{b}|{o}": 0.5 for b in range(8) for o in (0, 1, 2)}
    table.update({"2|0": 1.0, "4|0": 1.2})
    rn = pd.DataFrame([
        dict(game_pk=1, at_bat_index=3, play_index=2, runner_id=10, event_type="wild_pitch", is_out=False,
             start="1B", end="2B", is_batter=False, base_before_group=1, outs_before_group=0,
             base_after_group=2, outs_after_group=0, runs_group=0),
        dict(game_pk=1, at_bat_index=3, play_index=2, runner_id=11, event_type="wild_pitch", is_out=False,
             start="2B", end="3B", is_batter=False, base_before_group=1, outs_before_group=0,
             base_after_group=2, outs_after_group=0, runs_group=0),
        dict(game_pk=1, at_bat_index=5, play_index=1, runner_id=10, event_type="single", is_out=False,
             start="1B", end="2B", is_batter=False, base_before_group=1, outs_before_group=0,
             base_after_group=2, outs_after_group=0, runs_group=0),
    ])
    by, league = M.dirt_advances(rn, table)
    assert set(by) == {10, 11} and by[10][0] == 1 and by[11][0] == 1
    assert league["advances"] == 2
    assert "w" in M.FIELDS and "w" not in ebr.PARTS and "w_n" not in ebr.PARTS


# --------------------------------------------------------------------------
# identity receipts
# --------------------------------------------------------------------------
def _frames(sb=3, cs=1, extra_sb=0):
    rn = pd.DataFrame({"runner_id": [1] * sb + [2] * cs + [3] * extra_sb,
                       "movement_reason": ["r_stolen_base_2b"] * sb + ["r_caught_stealing_2b"] * cs
                                          + ["r_stolen_base_2b"] * extra_sb})
    pa = pd.DataFrame({"batter_id": [1, 2, 3], "event_type": ["single", "grounded_into_double_play", "walk"],
                       "is_pa": [True, True, True]})
    return pa, rn


def _official(sb1=3, cs2=1, sb3=0):
    return {"players": {"1": {"sb": sb1, "cs": 0, "gidp": 0, "pa": 1},
                        "2": {"sb": 0, "cs": cs2, "gidp": 1, "pa": 1},
                        "3": {"sb": sb3, "cs": 0, "gidp": 0, "pa": 1}}}


def test_identity_passes_when_the_record_matches_the_official_lines():
    pa, rn = _frames()
    r = B.identity_lines(pa, rn, _official())
    assert r["I1"]["pass"] and r["I1"]["exact"] and r["I2"]["pass"] and r["I2"]["exact"]


def test_identity_tolerates_a_scorer_gap_inside_the_bounds_and_reports_it_inexact():
    pa, rn = _frames(sb=1500, extra_sb=1)
    off = _official(sb1=1500, sb3=2)           # 1501 against 1502 league steals
    off["players"].update({str(100 + i): {"sb": 1, "cs": 0, "gidp": 0, "pa": 1} for i in range(300)})
    rn = pd.concat([rn, pd.DataFrame({"runner_id": [100 + i for i in range(300)],
                                      "movement_reason": ["r_stolen_base_2b"] * 300})], ignore_index=True)
    off["players"]["1"]["sb"] = 1500
    r = B.identity_lines(pa, rn, off)
    assert r["I1"]["pass"] and not r["I1"]["exact"]
    assert r["I2"]["pass"] and not r["I2"]["exact"] and r["I2"]["sb_cs_mismatch"] == 1


def test_identity_fails_when_many_players_differ_or_no_lines_exist():
    pa, rn = _frames()
    bad = _official()
    bad["players"]["1"]["sb"] = 9
    assert not B.identity_lines(pa, rn, bad)["I1"]["pass"]
    assert B.identity_lines(pa, rn, None)["I1"]["pass"] is None


def test_record_counts_keys_on_the_movement_reason():
    pa, rn = _frames()
    c = B.record_counts(pa, rn)
    assert c[1]["sb"] == 3 and c[2]["cs"] == 1 and c[2]["gidp"] == 1


# --------------------------------------------------------------------------
# aggregates: split half and continuity
# --------------------------------------------------------------------------
def test_split_half_reports_a_correlation_and_its_step_up():
    credits = []
    for m in range(40):
        for g in range(1, 21):
            credits.append((m, 1, g, "sb", (m % 7 - 3) * 0.1 + (0.02 if g % 2 else -0.02)))
    r = B.split_half(credits, {m: 200 for m in range(40)})
    assert r["n"] == 40 and r["r"] > 0.9 and r["spearman_brown"] >= r["r"]
    assert B.split_half(credits, {m: 10 for m in range(40)})["r"] is None


def test_continuity_pairs_players_with_150_pa_at_two_levels_only():
    F = {f: i for i, f in enumerate(M.FIELDS)}

    def row(mid, lv, season, pa, ebr_v):
        r = [0] * len(M.FIELDS)
        r[F["mlbam"]], r[F["level"]], r[F["season"]], r[F["pa"]], r[F["ebr"]] = mid, lv, season, pa, ebr_v
        return r
    rows = []
    for m in range(1, 12):
        rows += [row(m, "aa", 2026, 200, m * 0.3), row(m, "aaa", 2026, 200, m * 0.2)]
    rows += [row(99, "aa", 2026, 200, 1.0), row(99, "aaa", 2026, 100, 1.0)]     # under the floor
    rows += [row(50, "aa", 2025, 200, 1.0), row(50, "aa", 2026, 200, 1.0)]       # one level a season
    out = B.continuity(rows)
    assert out["aaa|aa"]["n"] == 11 or out["aa|aaa"]["n"] == 11
    assert out["all_pairs"]["n"] == 11


# --------------------------------------------------------------------------
# the card payload
# --------------------------------------------------------------------------
def _sub_and_eval():
    F = list(M.FIELDS)

    def row(mid, lv, season, pa, sb, pk, xa, xo, dp, e):
        d = dict(mlbam=mid, level=lv, season=season, pa=pa, starts_on_base=0, opp_sb=0, opp_xb=0, opp_dp=0,
                 sb=sb, pk=pk, xb_adv=xa, xb_oob=xo, dp=dp, ebr=e, w_n=2, w=0.31)
        return [d[f] for f in F]
    sub = {"generated_at": "2026-10-19T00:00:00+00:00",
           "rows": [row(7, "aaa", 2026, 400, 1.0, 0.2, 0.5, -0.3, -0.1, 1.3),
                    row(7, "single_a", 2025, 149, 0.5, 0, 0, 0, 0, 0.5),
                    row(8, "rookie", 2026, 300, 0, 0, 0, 0, 0, 0.0),
                    row(9, "aa", 2026, 300, 0.2, 0, 0.1, 0, 0, 0.3)],
           "units": {"aaa|2026": {"games": 10, "players_150": 1, "complete": False},
                     "aa|2026": {"games": 10, "players_150": 1, "complete": False},
                     "rookie|2026": {"games": 10, "players_150": 1, "complete": False},
                     "single_a|2025": {"games": 10, "players_150": 0, "complete": True}}}
    ev = {"identity": {"aaa|2026": {"all_pass": True}, "aa|2026": {"all_pass": True},
                       "rookie|2026": {"all_pass": False}, "single_a|2025": {"all_pass": True}}}
    return sub, ev


def test_the_payload_holds_only_passing_units_at_150_pa_or_more():
    sub, ev = _sub_and_eval()
    p = B.served_payload(sub, ev)
    assert set(p["by_mlbam"]) == {"7", "9"}
    assert p["by_mlbam"]["7"] == [["aaa", 2026, 400, 1.2, 0.2, -0.1, 1.3, 1.95, 2, 0.3]]
    assert "rookie|2026" not in p["units"] and p["display_pa"] == 150
    assert p["fields"][:3] == ["level", "season", "pa"]


def test_the_payload_names_no_grade_and_no_fv():
    sub, ev = _sub_and_eval()
    text = json.dumps(B.served_payload(sub, ev)).lower()
    assert "fv" not in re.findall(r"[a-z]+", text) and "efv" not in text and "consensus" not in text


def test_rate_per_600():
    assert M.rate600(1.3, 400) == 1.95 and M.rate600(1.0, 0) is None


# --------------------------------------------------------------------------
# isolation and the dark default
# --------------------------------------------------------------------------
FITTED = ("efv_", "proj_", "fa_", "arb_", "betting_")


def test_no_fitted_consumer_imports_or_reads_ebr_milb():
    files = sorted(list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")))
    bad = []
    for p in files:
        if p.name.startswith(FITTED) or p.name == "leaderboard_vintages.py":
            t = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"ebr_milb|milb_preview", t):
                bad.append(p.name)
    assert bad == []
    assert B.isolation_scan()["pass"]


def test_the_preview_is_never_written_under_data(tmp_path):
    with pytest.raises(ebr.EbrRefusal):
        B.write_preview({}, {}, B.ROOT / "data")
    B.write_preview({"a": 1}, {"b": 2}, tmp_path / "milb_preview")
    assert (tmp_path / "milb_preview" / "ebr_milb.json").exists()
    assert B.PREVIEW_DIR.name == "milb_preview" and B.PREVIEW_DIR.parent.name == "ebr"


def test_the_core_has_no_forecast_or_grade_word_in_its_numbers_and_is_display_only():
    src = (ROOT / "ebr_milb.py").read_text(encoding="utf-8")
    assert "never an eFV input" in src
    assert "—" not in src and "–" not in src


# --------------------------------------------------------------------------
# the flag: one module, one card constant, one commit (dark until the flip)
# --------------------------------------------------------------------------
def test_the_card_flag_mirrors_the_module_flag_and_fetches_only_when_on():
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    m = re.search(r"const MILB_EBR_CARD_ON = (true|false);", html)
    assert m, "the card's level-relative eBR flag is missing"
    assert (m.group(1) == "true") is M.MILB_EBR_LIVE
    body = html[html.index("function ensureMilbEbr()"):]
    body = body[:body.index(chr(10) + "}" + chr(10)) + 3]
    assert body.index("if (!_MILB_EBR_UI") < body.index('fetch("/data/ebr_milb.json"'), "the fetch is gated"
    card = html[html.index("function milbEbrCard(p)"):]
    card = card[:card.index(chr(10) + "}" + chr(10)) + 3]
    assert card.index("if (!_MILB_EBR_UI") < card.index("ensureMilbEbr()"), "the card is gated before it loads"
    assert "isPit" in card, "position players only"


def test_the_served_files_exist_exactly_when_the_flag_is_on():
    for name in ("ebr_milb.json", "ebr_milb_eval.json"):
        assert (ROOT / "data" / name).exists() is M.MILB_EBR_LIVE, name


def test_the_card_reads_no_grade_and_sits_in_the_signals_section_only():
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    card = html[html.index("function milbEbrCard(p)"):]
    card = card[:card.index(chr(10) + "}" + chr(10)) + 3]
    assert not re.search(r"efv|\bfv\b|consensus|rank|sort", card, re.I)
    assert "defHomeHtml, milbFieldingHtml, milbEbrHtml].filter(Boolean)" in html
    assert html.count("milbEbrCard(") == 2        # the definition and the one call
