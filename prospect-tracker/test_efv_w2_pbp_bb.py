# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the batted-ball columns and the park correction (efv_w2_pbp_bb.py,
EFV4_PBP_BATTED_BALL_BUNDLE).

1. The reduction: balls in play are X, D or E with a non-bunt trajectory; plate
   appearances leave out baserunning ends and sacrifice bunts; park counts split home and
   road; the centre line is the centre fielder's median coordX; spray needs a hand, and
   a switch hitter bats opposite the pitcher.
2. As of: only seasons that ended before the read, never past the season cap, from the
   floor up, at most MAX_SEASONS seasons; z inside the (sport, season) pool; shrink by
   D / (D + K); no id gives None.
3. The park correction: home-minus-road on-base share shrunk by the smaller count, read
   at the MiLB block's season and level; adjust_rows is the identity while the flag is
   off, so the served fit is untouched; nothing served imports the module.
4. The arms: seven skill-head columns registered in the screening lab's wave 2 without
   touching wave 1, buildable through column_values; the v3 menu is left as it was.
5. Bans: nothing grouped by consensus-FV level, no served exporter imported, no
   em-dash, no column builder reads a label, WAR or debut; the fetch window holds.
6. The artifact, when present: development role, the frozen label, the park arm's
   parity, every spent block labelled, ledger rows only for the development frames.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_screen_lab as LAB  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_pbp_bb as M  # noqa: E402

SRC = ROOT / "efv_w2_pbp_bb.py"
BAT, BAT2, PIT, PIT_L = 900101, 900102, 800201, 800202


def _game(home, away, pas, pitches, pk=1):
    return {"gamePk": pk, "home": home, "away": away, "pa": pas, "pitches": pitches}


def _cf_balls(n, x=128.0):
    """n plate appearances by BAT2 off PIT, each a fly ball fielded by the centre
    fielder at coordX x (ab indexes from 1000)."""
    pas = [[1000 + i, BAT2, PIT, "field_out", 1, 1] for i in range(n)]
    pitches = [[1000 + i, 1, "X", 0, 0, 0, 0, "fly_ball", "medium", "8", x, 60.0]
               for i in range(n)]
    return pas, pitches


@pytest.fixture
def game():
    pas = [[0, BAT, PIT, "single", 1, 1],
           [1, BAT, PIT, "walk", 1, 1],
           [2, BAT, PIT, "field_out", 1, 1],
           [3, BAT, PIT_L, "sac_bunt", 1, 1],
           [4, BAT, PIT, "caught_stealing_2b", 1, 1],
           [5, BAT, PIT_L, "field_out", 2, 1]]
    pitches = [[0, 1, "D", 0, 0, 0, 0, "line_drive", "hard", "7", 90.0, 120.0],
               [1, 1, "B", 0, 0, 1, 0, None, None, None, None, None],
               [2, 1, "F", 0, 0, 0, 1, "fly_ball", None, None, 140.0, 80.0],
               [2, 2, "X", 0, 1, 0, 1, "ground_ball", "medium", "6", 110.0, 160.0],
               [3, 1, "X", 0, 0, 0, 0, "bunt_grounder", "soft", "1", 126.0, 190.0],
               [5, 1, "X", 0, 0, 0, 0, "popup", "hard", "4", 150.0, 150.0]]
    cp, cpi = _cf_balls(120)
    return _game(10, 20, pas + cp, pitches + cpi)


# ---------------------------------------------------------------------------
# 1. the reduction
# ---------------------------------------------------------------------------

def test_balls_in_play_and_plate_appearances(game):
    d = M.aggregate_pool(11, 2016, games=[game])
    b = dict(zip(M.BAT_COLS, d["bat"][str(BAT)]))
    # 4 plate appearances (sac bunt and caught stealing leave), 2 on base
    assert (b["pa"], b["ob"]) == (4, 2)
    # balls in play: the line drive, the ground ball, the popup (the foul with a
    # trajectory and the bunt are out)
    assert (b["bip"], b["ld"], b["gb"], b["pu"], b["fb"], b["hard"]) == (3, 1, 1, 1, 0, 2)
    p = dict(zip(M.PIT_COLS, d["pit"][str(PIT)]))
    assert (p["bip"], p["ld"], p["gb"]) == (2 + 120, 1, 1)
    assert d["census"]["traj_not_in_play"] == 1 and d["census"]["bunts"] == 1
    assert d["x0"] == 128.0 and d["x0_n"] == 120
    assert d["hands"] is False and b["spray"] == 0


def test_park_counts_split_home_and_road(game):
    d = M.aggregate_pool(11, 2016, games=[game])
    # 124 plate appearances in the game (4 by BAT, 120 by BAT2), all at club 10's park
    assert d["park"]["10"] == [124, 2, 0, 0]
    assert d["park"]["20"] == [0, 0, 124, 2]
    assert d["batpark"][str(BAT)] == {"10": 4}


def test_spray_needs_a_hand_and_a_switch_hitter_bats_opposite(game):
    hands = {str(BAT): {"bats": "S", "throws": "R"}, str(PIT): {"bats": "R", "throws": "R"},
             str(PIT_L): {"bats": "L", "throws": "L"}, str(BAT2): {"bats": None}}
    d = M.aggregate_pool(11, 2016, games=[game], hands=hands)
    b = dict(zip(M.BAT_COLS, d["bat"][str(BAT)]))
    # vs PIT (right-handed) the switch hitter bats left: x 90 and 110 are left of 128,
    # so opposite; vs PIT_L he bats right: x 150 is right of 128, so opposite
    assert (b["spray"], b["pull"], b["oppo"], b["oppo_hard"]) == (3, 0, 3, 2)
    assert dict(zip(M.BAT_COLS, d["bat"][str(BAT2)]))["spray"] == 0


def test_pull_side_and_hand_rules():
    assert M.bat_side("R", "L") == "R" and M.bat_side("S", "L") == "R"
    assert M.bat_side("S", None) is None and M.bat_side(None, "R") is None
    assert M.pull_of("R", 100.0, 128.0) == 1 and M.pull_of("R", 150.0, 128.0) == 0
    assert M.pull_of("L", 150.0, 128.0) == 1 and M.pull_of("L", 128.0, 128.0) is None
    assert M.pull_of("L", 150.0, None) is None
    assert M.is_pa("single") and not M.is_pa("pickoff_1b") and not M.is_pa(None)
    assert M.is_bip("E", "line_drive") and not M.is_bip("F", "line_drive")
    assert not M.is_bip("X", "bunt_popup")


# ---------------------------------------------------------------------------
# 2. as of
# ---------------------------------------------------------------------------

def _pool(sport, season, bat=None, pit=None, park=None, batpark=None):
    """A reduced pool with 40 average hitters (ld 20 of 100) and 40 pitchers."""
    b = {str(1000 + i): [100, 30, 100, 45, 20 + (i % 3) - 1, 28, 7, 2, 0, 0, 0, 0]
         for i in range(40)}
    p = {str(2000 + i): [100, 100, 45 + (i % 3) - 1, 20, 28, 7] for i in range(40)}
    b.update(bat or {})
    p.update(pit or {})
    return {"v": M.AGG_VERSION, "sport": sport, "season": season, "hands": False,
            "x0": 128.0, "x0_n": 500, "bat": b, "pit": p, "park": park or {},
            "batpark": batpark or {}, "census": {}}


@pytest.fixture
def pools():
    hot = [100, 30, 100, 45, 30, 20, 5, 2, 0, 0, 0, 0]          # ld 30 of 100
    M.set_pools([_pool(12, 2015, bat={str(BAT): hot}),
                 _pool(12, 2016, bat={str(BAT): hot}),
                 _pool(12, 2017, bat={str(BAT): hot}),
                 _pool(13, 2017, bat={str(BAT): [10, 3, 10, 4, 3, 2, 1, 0, 0, 0, 0, 0]})])
    yield
    M.set_pools([])


def test_the_walk_is_as_of_capped_floored_and_two_seasons(pools):
    p = M.profile(BAT, 2018, None, "hit", 2014, season_cap=2022)
    assert p["_seasons"] == [2017, 2016]          # the 10-ball A+ line does not qualify
    # a cutoff before October of 2017 makes 2016 the last readable season
    p2 = M.profile(BAT, 2018, "2017-06-01", "hit", 2014, season_cap=2022)
    assert p2["_seasons"] == [2016, 2015]
    assert M.profile(BAT, 2018, None, "hit", 2014, season_cap=2016)["_seasons"] == [2016, 2015]
    assert M.profile(BAT, 2018, None, "hit", 2017, season_cap=2022)["_seasons"] == [2017]
    assert M.profile(BAT, 2016, None, "hit", 2014, season_cap=2022)["_seasons"] == [2015]


def test_the_value_is_a_pool_z_shrunk_by_its_denominator(pools):
    nm = M._norm(12, 2016, "ld_h")
    assert nm is not None and nm[2] == 41
    z = (0.30 - nm[0]) / nm[1]
    p = M.profile(BAT, 2018, None, "hit", 2014, season_cap=2022)
    assert p["ld_h"] == pytest.approx(z * 200.0 / (200.0 + M.STATS["ld_h"]["k"]))
    assert p["pull_h"] is None                     # no spray counts without hands
    assert M.profile(None, 2018, None, "hit", 2014, season_cap=2022)["ld_h"] is None
    assert M.profile("x", 2018, None, "hit", 2014, season_cap=2022)["ld_h"] is None


def test_a_thin_pool_norms_nothing(pools):
    M.set_pools([{**_pool(11, 2016), "bat": {str(BAT): [100] * 12}}])
    assert M._norm(11, 2016, "ld_h") is None
    assert M.profile(BAT, 2017, None, "hit", 2014, season_cap=2022)["ld_h"] is None


def test_lv_profiles_read_the_outcome_blind_id_and_reserved_vintages_raise(pools):
    rows = [{"player_key": "x", "mlbam_id": BAT, "record_mlbam_id": 1, "vintage": 2018,
             "window": ["2018-01-15", "2018-05-01"], "milb_floor": 2014},
            {"player_key": "y", "mlbam_id": None, "record_mlbam_id": BAT, "vintage": 2018,
             "window": ["2018-01-15", "2018-05-01"], "milb_floor": 2014}]
    out = M.lv_profiles("hit", {"hit": {2018: (rows, [{}, {}])}})
    assert out[(2018, "x")]["ld_h"] is not None and out[(2018, "y")]["ld_h"] is None
    with pytest.raises(F.ReservedFrameError):
        M.lv_profiles("hit", {"hit": {2020: ([dict(rows[0], vintage=2020)], [{}])}})
    assert M.DEV_SEASON_CAP < F.R_VM_FIRST_DEBUT_YEAR - 1 == M.SPENT_SEASON_CAP


# ---------------------------------------------------------------------------
# 3. the park correction and the flag
# ---------------------------------------------------------------------------

def test_the_park_correction_reads_the_block_season_and_level():
    park = {"10": [4000, 1600, 4000, 1200], "20": [4000, 1200, 4000, 1600]}
    M.set_pools([_pool(12, 2016, park=park, batpark={str(BAT): {"10": 300, "20": 100}})])
    try:
        e = M._effects(12, 2016)
        assert e["10"] == pytest.approx(0.1 * 4000 / (4000 + M.K_PARK_PA))
        assert e["20"] == pytest.approx(-e["10"])
        want = (300 * e["10"] + 100 * e["20"]) / 400 * (400 / (400 + M.K_OBP_PA))
        assert M.park_correction(BAT, 2016, "AA", season_cap=2022) == pytest.approx(want)
        assert M.park_correction(BAT, 2016, "AAA", season_cap=2022) is None
        assert M.park_correction(BAT, 2016, "AA", season_cap=2015) is None
        assert M.park_correction(BAT, 2016, "CPX", season_cap=2022) is None
        assert M.park_correction(BAT + 9, 2016, "AA", season_cap=2022) is None
    finally:
        M.set_pools([])


def test_adjust_rows_is_the_identity_while_the_flag_is_off():
    assert M.PARK_ADJUST_OBP_REL is False
    rows = [{"decision_year": 2017, "player_key": "x", "v2": {"obp_rel": 0.02}},
            {"decision_year": 2017, "player_key": "y", "v2": {"obp_rel": None}}]
    corr = {(2017, "x", "train"): 0.005, (2017, "y", "train"): 0.004}
    assert M.adjust_rows(rows, corr, "train") is rows
    assert M.adjust_rows(rows, corr, "train", on=False) is rows
    out = M.adjust_rows(rows, corr, "train", on=True)
    assert out[0]["v2"]["obp_rel"] == pytest.approx(0.015) and out[1] is rows[1]
    assert rows[0]["v2"]["obp_rel"] == 0.02                       # inputs untouched
    assert M.adjust_rows(rows, corr, "test", on=True)[0] is rows[0]


def test_nothing_served_imports_the_module():
    served = ("efv_v2_model.py", "efv_v2_serve.py", "efv_dataset.py", "efv_model.py",
              "efv_score.py", "efv_export.py", "efv_v3.py", "build_site.py",
              "run_monthly.py", "proj_export.py")
    for name in served:
        p = ROOT / name
        if p.exists():
            assert "efv_w2_pbp_bb" not in p.read_text(encoding="utf-8", errors="ignore"), name


def test_the_park_twin_permutes_within_year_and_part():
    corr = {(2017, "a", "train"): 0.1, (2017, "b", "train"): 0.2,
            (2017, "c", "test"): 0.3, (2018, "d", "train"): None}
    tw = M.permuted_corrections(corr, seed=7)
    assert tw[(2017, "c", "test")] == 0.3 and tw[(2018, "d", "train")] is None
    assert sorted([tw[(2017, "a", "train")], tw[(2017, "b", "train")]]) == [0.1, 0.2]


# ---------------------------------------------------------------------------
# 4. the arms and their registration
# ---------------------------------------------------------------------------

def test_the_arms_are_seven_skill_columns_registered_in_wave_two():
    names = [a["name"] for a in M.ARMS]
    assert names == ["w2b_ld_h", "w2b_pu_h", "w2b_pull_h", "w2b_oppo_hard_h", "w2b_gb_p",
                     "w2b_ld_against_p", "w2b_pu_p"]
    for a in M.ARMS:
        assert a["head"] == "skill" and a["side"] in F.SIDES and not a["retest"]
        assert a["column"]["source"] == "module" and a["column"]["arg"] == a["stat"]
        assert M.STATS[a["stat"]]["side"] == a["side"]
    assert M.PARK_ARM["kind"] == "replace" and M.PARK_ARM["name"] not in names
    assert "efv_w2_pbp_bb" in LAB.WAVE2_ARM_MODULES
    assert set(names) <= {a["name"] for a in LAB.wave2_candidates()}
    assert [c["name"] for c in LAB.CANDIDATES][:2] == ["txt_skill_hit", "txt_skill_pit"]
    assert LAB.registration_echo()["family_size"] == 7


def test_the_lab_builds_an_arm_through_its_own_column_values(pools):
    M._LV_MEMO.clear()
    rows = [{"player_key": "x", "mlbam_id": BAT, "vintage": 2018,
             "window": ["2018-01-15", "2018-05-01"], "milb_floor": 2014}]
    frames = {"hit": {2018: (rows, [{}])}}
    arm = next(a for a in M.ARMS if a["name"] == "w2b_ld_h")
    vals = LAB.column_values(arm, frames)
    assert set(vals) == {(2018, "x")} and vals[(2018, "x")] > 0
    M._LV_MEMO.clear()
    with pytest.raises(ValueError):
        M.screen_column("gb_p", "hit", frames)
    with pytest.raises(ValueError):
        M.screen_column("ld_later", "hit", frames)


def test_registered_columns_leave_the_v3_menu_as_it_was():
    import efv_v3 as V3
    before = dict(V3.W2_COLUMNS)
    with M.registered_columns():
        cfg = V3.base_config()
        cfg["add"]["pit"]["skill"].append("w2b_gb_p")
        V3.validate_config(cfg)
        assert V3.W2_COLUMNS["w2b_gb_p"]["key"].startswith("scr_")
    assert V3.W2_COLUMNS == before


# ---------------------------------------------------------------------------
# 5. bans
# ---------------------------------------------------------------------------

_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin", "by_consensus", "per_fv", "per_consensus")
_SERVED_EXPORTERS = {"efv_export", "efv_v2_serve", "efv_score", "build_site", "proj_export",
                     "export_trade_values", "efv_alerts", "run_monthly"}


def test_no_consensus_level_grouping_no_exporter_no_emdash():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            low = name.lower()
            assert not any(t in low for t in _BANNED_TOKENS), name
            assert not fv_group.search(low), name
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED_TOKENS), node.value
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            assert not {m.split(".")[0] for m in mods} & _SERVED_EXPORTERS, mods
    assert "\u2014" not in src and "\u2013" not in src
    for fn in ("aggregate_pool", "profile", "_norm", "park_correction", "_effects",
               "lv_profiles", "screen_column", "adjust_rows"):
        body = ast.get_source_segment(src, next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn))
        for banned in ("efv_labels", "w3", "war", "debut", "target", "reached"):
            assert banned not in body.lower(), (fn, banned)


def test_the_fetch_window_is_closed_from_six_to_eleven_utc():
    def at(h):
        return datetime(2026, 10, 9, h, 30, tzinfo=timezone.utc)
    assert M.fetch_window_open(at(11))[0] and M.fetch_window_open(at(20))[0]
    assert not M.fetch_window_open(at(6))[0] and not M.fetch_window_open(at(10))[0]
    assert not M.fetch_window_open(datetime(2026, 10, 12, 15, tzinfo=timezone.utc))[0]
    assert M.CACHE_DIR.name == "efv4_pbp_bb"


# ---------------------------------------------------------------------------
# 6. the artifact
# ---------------------------------------------------------------------------

def _artifact():
    if not M.OUT_PATH.exists():
        pytest.skip("read not run on this tree")
    return json.loads(M.OUT_PATH.read_text(encoding="utf-8"))


def test_the_artifact_is_a_development_read_on_the_frozen_label():
    d = _artifact()
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["selects"] is False and d["exploratory"] is False
    assert d["label"]["provider"] == "fwar"
    assert d["label"]["id"].startswith("fwar@2026-10-02")
    assert d["lv_dev"]["frame"]["folds"] == [2017, 2018, 2019]
    assert all(int(y) < F.R_VM_FIRST_DEBUT_YEAR for y in d["vm_dev"]["frame"]["fold_years"])
    for side, by_stat in d["lv_dev"]["coverage"].items():
        for cov in by_stat.values():
            assert not ({"2020", "2021"} & set(cov)), side
    for name, a in d["lv_dev"]["arms"].items():
        for comp in ("candidate_vs_efv_v2_base", "candidate_vs_prospx_consensus"):
            leg = a["frame"]["deltas"][comp]["spearman"]
            assert leg["delta"] is not None and len(leg["ci95"]) == 2, name
    assert d["park"]["flag_default"] is False
    for fid, a in d["park"]["frames"].items():
        assert a["parity_off"]["reproduces"] is True and a["parity_off"]["differ"] == 0


def test_every_spent_block_is_labelled_and_lands_no_ledger_row():
    d = _artifact()
    sp = d.get("spent")
    if not sp:
        pytest.skip("no spent read in the artifact")
    assert sp["note"] == M.SPENT_NOTE
    assert set(sp["frames"]) == {"lv_res", "vm_pros"}
    for fid, blk in sp["frames"].items():
        assert blk["frame"]["note"] == M.SPENT_NOTE
        for a in blk["arms"].values():
            assert a["frame"]["note"] == M.SPENT_NOTE
    docs = M.ledger_docs(d)
    read = [a for a in d["arms_declared"] if a["name"] in d["lv_dev"]["arms"]
            or a["name"] == M.PARK_ARM["name"]]
    assert len(docs) == 2 * len(read)
    for doc in docs:
        assert doc["role"] == "development"
        assert doc["model_id"].startswith(M.MODEL_PREFIX)
        assert set(doc["frames"]) <= {"lv_dev", "vm_dev"}
