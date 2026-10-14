# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Baserunning section's payload contract (baserunning_export.py; the eWAR
v3 plan's EBR_2_BUILD_DARK; docs/ebr-2026-09-30/EBR_GATE.md parts 2.7, 3 and 4).

Two layers:
  * fixtures: the record counts on a hand-built play (a single with the man on
    first to third, a steal on the strikeout pitch, a caught stealing for the
    third out, a pickoff, a tag-up, a double with an error-aided advance, a
    double play) and the row assembly on dicts;
  * the artifact: the preview under .cache/baserunning/preview/ (data/ once
    MLBSTATS_BASERUNNING_LIVE flips), read when it is present and never built
    here. The gate document's identity receipts I1 to I7 stand in for
    baserunning.md's 97/90/97 shares: SB and CS exact, GIDP at 97 percent.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import pytest

import baserunning_export as BE

ROOT = Path(__file__).parent
PREVIEW = ROOT / ".cache" / "baserunning" / "preview"
LIVE = (ROOT / "data" / BE.OUT_NAME).exists() and BE.MLBSTATS_BASERUNNING_LIVE
BOARD = (ROOT / "data" / BE.OUT_NAME) if LIVE else (PREVIEW / BE.OUT_NAME)
HISTORY = (ROOT / "data" / BE.HISTORY_NAME) if LIVE else (PREVIEW / BE.HISTORY_NAME)
EVAL = (ROOT / "data" / BE.EVAL_NAME) if LIVE else (PREVIEW / BE.EVAL_NAME)
JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
RATES = {"sb_pct": ("sb", lambda r: r.get("sb", 0) + r.get("cs", 0), BE.FLOORS["sb_pct"]),
         "att_rate": (lambda r: sum(r.get(k, 0) for k in ("sb2", "sb3", "cs2", "cs3")),
                      lambda r: r.get("opp_sb2", 0) + r.get("opp_sb3", 0), BE.FLOORS["att_rate"]),
         "xbt_pct": ("xbt", "xbt_opp", BE.FLOORS["xbt"]),
         "tag_pct": (lambda r: r.get("tag", [0, 0])[0], lambda r: r.get("tag", [0, 0])[1], BE.FLOORS["tag"]),
         "gidp_pct": ("gidp_pbp", "gdp_opp", BE.FLOORS["gidp"])}
FORBIDDEN_KEYS = {"ubr", "wgdp", "wGdp", "fv", "efv", "grade"}


# --------------------------------------------------------------------------- #
# fixtures: the record counts
# --------------------------------------------------------------------------- #
def _pa(**kw):
    base = dict(game_pk=1, season=2025, at_bat_index=0, batter_id=10, bat_team_id=100, is_pa=True,
                on_first=None, on_second=None, on_third=None, fp_on_first=None, fp_on_second=None,
                fp_on_third=None, fp_outs=0, event_type="strikeout", trajectory=None, in_play_index=None,
                outs_before=0)
    base.update(kw)
    return base


def _rn(**kw):
    base = dict(game_pk=1, season=2025, at_bat_index=0, play_index=0, seq=0, runner_id=None, is_batter=False,
                bat_team_id=100, start=None, end=None, is_out=False, movement_reason=None, error_credit=False)
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def counts():
    pd = pytest.importorskip("pandas")
    pa = [
        # 0: runner 20 on first at the start (a steal chance); he steals second on the strikeout pitch.
        _pa(at_bat_index=0, on_first=20, fp_on_first=20, event_type="strikeout"),
        # 1: single; runner 20 on second (not a 1st-3rd chance) scores; batter 11 to first.
        _pa(at_bat_index=1, batter_id=11, on_second=20, fp_on_second=20, event_type="single",
            trajectory="line_drive", in_play_index=2),
        # 2: single; runner 11 on first goes first to third.
        _pa(at_bat_index=2, batter_id=12, on_first=11, fp_on_first=11, event_type="single",
            trajectory="ground_ball", in_play_index=1),
        # 3: fly ball, runner 11 on third tags and scores; runner 12 on first is blocked by nobody
        #    (a runner on first has no tag class), one out at the final pitch.
        _pa(at_bat_index=3, batter_id=13, on_first=12, on_third=11, fp_on_first=12, fp_on_third=11, fp_outs=1,
            event_type="sac_fly", trajectory="fly_ball", in_play_index=0),
        # 4: runner 12 on first is picked off (no attempt).
        _pa(at_bat_index=4, batter_id=14, on_first=12, fp_outs=2, event_type="field_out"),
        # 5: a new inning: runner 30 on first caught stealing for the third out, under two out at the
        #    final pitch: a double-play chance for batter 15 that ended in a double play.
        _pa(at_bat_index=5, batter_id=15, on_first=30, fp_on_first=30, fp_outs=1, outs_before=1,
            event_type="grounded_into_double_play", trajectory="ground_ball", in_play_index=3),
        # 6: double; runner 31 on first advances on a throwing error: left out of both sides.
        _pa(at_bat_index=6, batter_id=16, on_first=31, fp_on_first=31, event_type="double",
            trajectory="line_drive", in_play_index=1),
        # 7: double; runner 32 on first is thrown out at home trying to score.
        _pa(at_bat_index=7, batter_id=17, on_first=32, on_second=None, fp_on_first=32, event_type="double",
            trajectory="fly_ball", in_play_index=0),
        # 8: single; runner 33 on first is blocked: the runner on second held at third.
        _pa(at_bat_index=8, batter_id=18, on_first=33, on_second=34, fp_on_first=33, fp_on_second=34,
            event_type="single", trajectory="ground_ball", in_play_index=0),
    ]
    rn = [
        _rn(at_bat_index=0, play_index=5, runner_id=20, start="1B", end="2B", movement_reason="r_stolen_base_2b"),
        _rn(at_bat_index=1, play_index=2, runner_id=20, start="2B", end="score", movement_reason="r_adv_play"),
        _rn(at_bat_index=1, play_index=2, seq=1, runner_id=11, is_batter=True, end="1B"),
        _rn(at_bat_index=2, play_index=1, runner_id=11, start="1B", end="3B", movement_reason="r_adv_play"),
        _rn(at_bat_index=2, play_index=1, seq=1, runner_id=12, is_batter=True, end="1B"),
        _rn(at_bat_index=3, play_index=0, runner_id=11, start="3B", end="score", movement_reason="r_adv_play"),
        _rn(at_bat_index=3, play_index=0, seq=1, runner_id=13, is_batter=True, is_out=True),
        _rn(at_bat_index=4, play_index=1, runner_id=12, start="1B", is_out=True, movement_reason="r_pickoff_1b"),
        _rn(at_bat_index=5, play_index=3, runner_id=30, start="1B", is_out=True, movement_reason="r_force_out"),
        _rn(at_bat_index=5, play_index=3, seq=1, runner_id=15, is_batter=True, is_out=True),
        _rn(at_bat_index=6, play_index=1, runner_id=31, start="1B", end="3B", movement_reason="r_adv_play"),
        _rn(at_bat_index=6, play_index=1, seq=1, runner_id=31, start="3B", end="score", movement_reason="r_adv_throw",
            error_credit=True),
        _rn(at_bat_index=7, play_index=0, runner_id=32, start="1B", is_out=True, movement_reason="r_thrown_out"),
        _rn(at_bat_index=8, play_index=0, runner_id=34, start="2B", end="3B", movement_reason="r_adv_play"),
        _rn(at_bat_index=8, play_index=0, seq=1, runner_id=33, start="1B", end="2B", movement_reason="r_adv_force"),
    ]
    return BE.record_counts(pd.DataFrame(pa), pd.DataFrame(rn))


def test_steal_counts_key_on_movement_reason(counts):
    r = counts["runners"]
    assert r[20]["sb2"] == 1 and r[20]["cs2"] == 0 and r[20]["opp_sb2"] == 1
    assert r[30]["cs2"] == 0, "a force out is not a caught stealing"
    assert r[12]["pk1"] == 1 and r[12]["oob"] == 0, "a pickoff is neither an attempt nor an out on the bases"


def test_extra_bases_tag_ups_blocked_chances_and_errors(counts):
    r = counts["runners"]
    assert r[11]["x13"] == [1, 1], "first to third on a single is one chance taken"
    assert r[20]["x2h"] == [1, 1], "second to home on a single is one chance taken"
    assert r[11]["tag3h"] == [1, 1], "tagging from third on a caught fly ball"
    assert r[31]["x1h"] == [0, 0] and r[31]["adv_err"] == 1, "an error-aided advance is counted on neither side"
    assert r[32]["x1h"] == [0, 1] and r[32]["oob"] == 1, "thrown out trying is a chance not taken and an out on the bases"
    assert r[33]["x13"] == [0, 0], "a chance blocked by the runner ahead holding third is no chance"


def test_double_play_chances_and_team_rollup(counts):
    r = counts["runners"]
    assert r[15]["gdp_opp"] == 1 and r[15]["gidp_pbp"] == 1
    t = counts["teams"][100]
    assert t["sb2"] == 1 and t["pk1"] == 1 and t["oob"] == 1 and t["gidp_pbp"] == 1
    assert t["x13"] == [1, 1] and t["x2h"] == [1, 2] and t["x1h"] == [0, 1], "runner 34 held at third: a chance not taken"
    assert counts["runner_team"][11][100] >= 2, "a runner votes for his batting club on every start on base"


# --------------------------------------------------------------------------- #
# fixtures: rows and rates on dicts
# --------------------------------------------------------------------------- #
def _sub(mid, **parts):
    base = {"mlbam": mid, "season": 2025, "pa": 400, "starts_on_base": 120, "opp_sb": 60, "opp_xb": 40,
            "opp_dp": 50, "sb": 0.0, "pk": 0.0, "xb_adv": 0.0, "xb_oob": 0.0, "dp": 0.0, "ebr": 0.0, "stints": None}
    base.update(parts)
    base["ebr"] = round(base["sb"] + base["pk"] + base["xb_adv"] + base["xb_oob"] + base["dp"], 3)
    return base


def _rows(counts=None):
    c = counts or {"runners": {}, "teams": {}, "runner_team": {}}
    official = {1: {"name": "Fast Runner", "team_id": 147, "pos": "CF", "pa": 600, "sb": 30, "cs": 5, "gidp": 4},
                2: {"name": "Slow Bat", "team_id": 111, "pos": "1B", "pa": 150, "sb": 0, "cs": 1, "gidp": 20},
                3: {"name": "No Chance", "team_id": 111, "pos": "P", "pa": 0, "sb": 0, "cs": 0, "gidp": 0}}
    sub = {1: _sub(1, sb=2.5, pk=-0.5, xb_adv=3.0, xb_oob=-0.25, dp=1.0),
           2: _sub(2, pa=150, sb=-0.4, xb_adv=-1.0, dp=-2.0)}
    published = {"values": {1: {"bsr": 7.0, "wsb": 3.0}, 2: {"bsr": -3.5, "wsb": -0.5}}}
    savant = {"brv": {1: {"runner_runs_tot": 6.0, "runner_runs_XB": 3.5, "runner_runs_SBX": 2.5}},
              "steal": {1: {"runs_stolen_on_running_act": 2.0, "r_primary_lead": 11.5, "r_secondary_lead": 15.0}}}
    sprint = {1: {"ft_s": 29.6, "runs": 150, "bolts": 20, "hp1": 4.1}, 2: {"ft_s": 25.0, "runs": 40}}
    return BE.build_rows(2025, official=official, counts=c, sub_rows=sub, published=published, savant=savant,
                         sprint=sprint, tmap={147: "NYY", 111: "BOS"}, links={"1": {"prospx": "fast_runner"}},
                         debuts={1: "2024-04-02"})


def test_rows_carry_the_display_parts_and_the_published_columns():
    rows = {r["mlbam"]: r for r in _rows()}
    r = rows[1]
    assert (r["ebr_sb"], r["ebr_xb"], r["ebr_dp"], r["ebr"]) == (2.0, 2.75, 1.0, 5.75)
    assert r["ebr_oob"] == -0.75
    assert (r["bsr"], r["wsb"], r["bsr_rest"]) == (7.0, 3.0, 4.0)
    assert (r["brv"], r["brv_xb"], r["brv_sb"], r["sav_steal_runs"], r["lead_p"]) == (6.0, 3.5, 2.5, 2.0, 11.5)
    assert r["sprint"] == 29.6 and r["sprint_pct"] == 75 and r["recent_debut"] is True
    assert r["qualified"] is True and rows[2]["qualified"] is False
    assert r["team"] == "NYY" and r["pos"] == "CF"
    assert 3 not in rows, "a season line with no plate appearance and no chance is not a row"
    assert "prospx" not in r, "the PROSPX chip comes from the links map the page loads"


def test_a_rate_is_absent_below_its_floor_and_equals_its_ratio_above_it():
    rows = {r["mlbam"]: r for r in _rows()}
    r = rows[1]
    assert r["sb_pct"] == round(30 / 35, 3)
    assert rows[2]["sb_pct"] is None, "one attempt is under the five-attempt floor"
    assert r["att_rate"] is None and r["xbt_pct"] is None and r["gidp_pct"] is None, "no record chances"


def test_the_sprint_percentile_counts_ties_half_among_tracked_runners():
    pct = BE._percentiles({1: 29.6, 2: 25.0, 3: 27.0, 4: 27.0})
    assert pct == {1: 88, 2: 13, 3: 50, 4: 50}, "the share below with ties counted half (the drawer's pctRank)"


def test_the_breakeven_is_the_run_expectancy_crossing():
    cells = {f"{b}|{o}": [1.0, 100] for b in range(8) for o in (0, 1, 2)}
    cells["1|0"] = [0.9, 100]; cells["2|0"] = [1.1, 100]; cells["0|1"] = [0.3, 100]
    cells["1|1"] = [0.5, 100]; cells["2|1"] = [0.7, 100]; cells["0|2"] = [0.1, 100]
    cells["1|2"] = [0.2, 100]; cells["2|2"] = [0.3, 100]
    # p* = (RE(1B,0) - RE(empty,1)) / (RE(2B,0) - RE(empty,1)) = 0.6 / 0.8 at 0 out, and so on
    p0 = (0.9 - 0.3) / (1.1 - 0.3)
    p1 = (0.5 - 0.1) / (0.7 - 0.1)
    p2 = (0.2 - 0.0) / (0.3 - 0.0)
    assert BE._breakeven(cells, (1,), 2) == round((p0 + p1 + p2) / 3, 4)


def test_nothing_here_computes_a_year_to_year_or_forward_statistic():
    src = (ROOT / "baserunning_export.py").read_text(encoding="utf-8")
    for token in ("persistence", "split_half", "Spearman", "y + 1", "season + 1", "next season", "forecast"):
        assert token not in src.replace("not a forecast", ""), token
    import ast
    names = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module.split(".")[0])
            names |= {a.name for a in n.names}
    assert not (names & {"ebr", "build_ebr", "ebr_gate"}), "the exporter reads the substrate file, never the core"
    assert 'st.get("ubr")' not in src and 'st.get("wGdp")' not in src


def test_the_frame_sentence_is_derived_from_the_served_provider_never_typed_on_the_page():
    note = BE._ewar_baserunning_note()
    assert note.endswith(".") and len(note) > 20
    assert note not in JS, "assets/mlbstats.js types no WAR frame; it reads frame.ewar_note"
    assert BE._war_provider() in ("ewar_v2", "fwar", "bwar", ""), BE._war_provider()


def test_bem_plus_rides_only_on_a_recorded_pass(tmp_path):
    empty = tmp_path / "gate.md"
    empty.write_text("### 12.1 The outcome look\n\nEMPTY.\n\n### 12.2 x\n", encoding="utf-8")
    assert BE.bem_plus_status(empty)["served"] is False
    passed = tmp_path / "gate2.md"
    passed.write_text("### 12.1 The outcome look\n\n2026-11-17: BEM+ gate X-B1 PASS.\n\n### 12.2 x\n", encoding="utf-8")
    assert BE.bem_plus_status(passed)["served"] is True
    gate = ROOT / "docs" / "ebr-2026-09-30" / "EBR_GATE.md"
    assert BE.bem_plus_status(gate)["served"] is False, "part 12.1 is EMPTY at this commit"


def test_data_is_never_written_while_the_flag_is_off(tmp_path, monkeypatch):
    monkeypatch.setattr(BE, "MLBSTATS_BASERUNNING_LIVE", False)
    assert BE.out_dir() == BE.PREVIEW_DIR
    with pytest.raises(BE.BaserunningRefusal):
        BE._write_json(BE.DATA_DIR / "baserunning_probe.json", {"x": 1})
    assert not (BE.DATA_DIR / "baserunning_probe.json").exists()
    BE._write_json(tmp_path / "ok.json", {"x": 1})
    assert json.loads((tmp_path / "ok.json").read_text(encoding="utf-8")) == {"x": 1}


# --------------------------------------------------------------------------- #
# the artifact (skips when absent; never built here)
# --------------------------------------------------------------------------- #
def _board():
    if not BOARD.exists():
        pytest.skip(f"{BOARD.name} not built")
    return json.loads(BOARD.read_text(encoding="utf-8"))


def _history():
    if not HISTORY.exists():
        pytest.skip(f"{HISTORY.name} not built")
    return json.loads(HISTORY.read_text(encoding="utf-8"))


def _eval():
    if not EVAL.exists():
        pytest.skip(f"{EVAL.name} not built")
    return json.loads(EVAL.read_text(encoding="utf-8"))


def _walk_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys(v, out)


def test_top_level_shape_and_flag():
    d = _board()
    for k in ("schema", "generated_at", "season", "as_of", "verdict", "frame", "flag", "bem_plus", "sources",
              "values", "qualify", "league", "team_basis", "runners", "teams", "n_qualified"):
        assert k in d, k
    assert d["verdict"] == "descriptive"
    assert d["flag"] == {"MLBSTATS_BASERUNNING_LIVE": BE.MLBSTATS_BASERUNNING_LIVE}
    assert d["qualify"]["min_pa"] == BE.QUALIFY_MIN_PA and d["qualify"]["floors"] == BE.FLOORS
    assert d["frame"]["ewar_note"].endswith(".") and d["frame"]["war_provider"]
    keys = set()
    _walk_keys(d, keys)
    assert not (keys & FORBIDDEN_KEYS), keys & FORBIDDEN_KEYS
    assert d["sources"]["published"]["not_read"] == ["ubr", "wGdp"]


def test_every_published_block_has_its_source_date_and_join_rate():
    s = _board()["sources"]
    pub = s["published"]
    assert pub["source"] and pub["fetched_at"] and pub["n_joined"] > 0
    assert pub["hit_rate_eligible"] >= 0.97 and pub["n_ambiguous"] == 0
    for b in ("savant_brv", "savant_steal"):
        assert s[b]["source_url"].startswith("https://baseballsavant.mlb.com/") and s[b]["fetched_at"]
        assert s[b]["n_joined"] > 0 and s[b]["n_joined"] <= s[b]["n_source_rows"]
        assert "/leaderboard/baserunning?" not in s[b]["source_url"], "the season-inert board is never read"
    assert s["sprint"]["fetched_at"] and s["sprint"]["min_runs"] == BE.SPRINT_MIN_RUNS
    assert s["ebr"]["ebr_version"] == "ebr_v1" and s["ebr"]["re24_sha256"] and s["ebr"]["K"]


def test_the_identity_receipts_hold_on_the_season_served():
    d = _board()
    rec = d["sources"]["runner_moves"]["receipts"]
    for k in ("I1", "I2", "I3"):
        assert rec[k]["pass"] is True, (k, rec[k])
    assert rec["I2"]["sb"]["exact_share"] == 1.0 and rec["I2"]["cs"]["exact_share"] == 1.0
    assert rec["I2"]["gidp"]["exact_share"] >= BE.I2_GIDP_MIN_SHARE
    # I1 from the rows themselves: steals keyed on movementReason equal the official total.
    rows = d["runners"]
    assert sum(r.get("sb2", 0) + r.get("sb3", 0) + r.get("sbh", 0) for r in rows) == d["league"]["sb"]
    assert sum(r.get("cs2", 0) + r.get("cs3", 0) + r.get("csh", 0) for r in rows) == d["league"]["cs"]
    ev = _eval()
    for s, blk in ev["identity"].items():
        for k in ("I4", "I5", "I6", "I7", "I9"):
            assert blk[k]["pass"] is True, (s, k)
    for s, cov in ev["coverage"].items():
        assert cov["share"] >= 0.99, (s, cov)


def test_rows_sum_their_parts_carry_each_rate_with_its_terms_and_honour_the_floors():
    d = _board()
    for r in d["runners"]:
        if "ebr" in r:
            assert abs(r["ebr"] - (r["ebr_sb"] + r["ebr_xb"] + r["ebr_dp"])) <= 0.011, r["name"]
            assert abs(r["ebr"]) <= 30
        for key, (num_, den, floor) in RATES.items():
            n = num_(r) if callable(num_) else r.get(num_, 0)
            m = den(r) if callable(den) else r.get(den, 0)
            if m >= floor and m > 0:
                assert r.get(key) == round(n / m, 3), (r["name"], key)
            else:
                assert key not in r, (r["name"], key, "a rate under its floor is absent")
        assert "sprint_pct" not in r or "sprint" in r
        assert isinstance(r["qualified"], bool) and r["qualified"] == (r["pa"] >= BE.QUALIFY_MIN_PA)
    assert d["n_qualified"] == sum(1 for r in d["runners"] if r["qualified"])
    for k in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp"):
        assert abs(d["league"]["ebr_sum"][k]) <= BE.LEAGUE_SUM_TOL, k


def test_team_blocks_carry_both_bases_and_the_earned_basis_sums_to_zero():
    d = _board()
    assert len(d["teams"]) == 30
    for t in d["teams"]:
        assert set(t["roster"]) == set(t["earned"]), t["team"]
        assert t["team_ebr"] == t["roster"]["team_ebr"], "the flat keys are the roster basis the tab shows"
        assert "team_war" not in t and "war" not in t, "no eWAR on the team board (the Team Defense rule)"
    for k in ("team_ebr", "team_ebr_sb", "team_ebr_xb", "team_ebr_dp"):
        assert abs(sum(t["earned"][k] for t in d["teams"])) <= 0.1, k
    assert d["team_basis"]["basis"] in ("current_roster", "stats_earned")


def test_the_war_column_ships_with_its_stamp_and_its_frame_sentence():
    d = _board()
    has = any("war" in r for r in d["runners"])
    assert has == ("ewar_vintage" in d)
    if has:
        j = d["sources"]["ewar_join"]
        assert j["available"] is True and j["n_stamped"] >= 0.5 * j["n_with_id"]
        assert d["frame"]["war_provider"] == BE._war_provider()
        assert d["frame"]["ewar_note"] == BE._ewar_baserunning_note()


def test_the_values_block_carries_the_gate_tables_and_the_break_evens():
    v = _board()["values"]
    assert len(v["re24"]) == 24 and all(set(c) == {"re", "n"} for c in v["re24"].values())
    assert v["re24_sha256"] and 0.5 < v["breakeven_sb2"] < 0.95 and 0.5 < v["breakeven_sb3"] < 0.95
    assert set(v["steal"]["per_opportunity"]) == {"1B", "2B", "3B"}
    assert v["gidp"]["rate"] is not None and v["gidp"]["table"]


def test_history_seasons_are_the_runner_record_seasons_with_positional_rows():
    h = _history()
    sub = json.loads(((ROOT / "data" / BE.SUBSTRATE_NAME) if LIVE else (PREVIEW / BE.SUBSTRATE_NAME)).read_text(encoding="utf-8"))
    live = _board()["season"]
    assert h["seasons"] == [s for s in sub["seasons"] if s != live and s in BE.HISTORY_SEASONS]
    assert h["fields"] == list(BE.HISTORY_FIELDS)
    assert h["ebr_version"] == "ebr_v1" and h["frozen_digests"]
    ix = {f: i for i, f in enumerate(h["fields"])}
    for s, blk in h["history"].items():
        assert blk["runners"], s
        for row in blk["runners"]:
            assert len(row) == len(h["fields"]), s
            assert row[ix["qualified"]] is True and row[ix["pa"]] >= BE.QUALIFY_MIN_PA
            if row[ix["ebr"]] is not None:
                assert abs(row[ix["ebr"]] - (row[ix["ebr_sb"]] + row[ix["ebr_xb"]] + row[ix["ebr_dp"]])) <= 0.011
        assert len(blk["teams"]) == 30 and all("team_ebr" in t for t in blk["teams"])
        for k in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp"):
            assert abs(blk["league"]["ebr_sum"][k]) <= BE.LEAGUE_SUM_TOL, (s, k)
        assert blk["sources"]["ebr"]["re24_sha256"]
    keys = set()
    _walk_keys(h, keys)
    assert not (keys & FORBIDDEN_KEYS)


def test_payloads_sit_inside_their_budgets():
    for path, budget in ((BOARD, BE.BUDGET_LIVE), (HISTORY, BE.BUDGET_HISTORY)):
        if not path.exists():
            pytest.skip(f"{path.name} not built")
        raw = path.read_bytes()
        assert len(raw) <= budget[0], (path.name, len(raw))
        assert len(gzip.compress(raw, 9)) <= budget[1], (path.name, len(gzip.compress(raw, 9)))


def test_the_eval_carries_the_ewar_link_and_the_board_receipts_and_no_runs_correlation():
    ev = _eval()
    for s, blk in ev["ewar_link"].items():
        assert set(blk["ebr_sums"]) == {"sb", "xb", "dp"}
        assert blk["fangraphs"]["counterparts"]["sb"] == "wSb"
    bb = ev["baserunning_board"]["by_season"]
    assert bb and all("reproduction" in v for v in bb.values())
    txt = json.dumps(ev)
    assert not re.search(r"r_off_[A-Za-z_]*runs|runs_scored|wins", txt), "no correlation against runs or wins is served"
