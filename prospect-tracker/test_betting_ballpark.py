"""Ballpark awareness for /betting/ (docs/diamond-betting.md section 5i).

WHAT THESE TESTS PROTECT, in the order a regression would hurt:

  1. THE FLAG IS OFF AND OFF MEANS BYTE-IDENTICAL. SERVE_ATH_PARK moves served
     prices and the value side of a total. With it False, park_index() and the
     vintage park read return exactly what they returned before 2026-09-11.
  2. THE ATHLETICS' FACTOR IS DERIVED, NOT TYPED. The served value under the
     flag is the measured Savant row shrunk by the measured reliability ratio;
     the constants reproduce the documented 1.1919 and follow the row's PA.
  3. THE SHORT WINDOW CAN NEVER OVERWRITE A 3-SEASON FACTOR, and reaches only
     the listed clubs, so the flag's measured effect cannot grow by itself.
  4. DARK MEANS DARK. The park-by-hand candidate and the schema-5 capture
     exist in the vintage record and in one helper each; nothing served reads
     them.
  5. THE PROPS HAND ARMS ADD KEYS AND MOVE NOTHING. A0 to A3 are what they
     were; a hand arm with nothing to read prices exactly like A3.
"""
from __future__ import annotations

import inspect
import itertools
import json
import math

import pytest

import betting_model as bm
import betting_props_dark as B
import leaderboard_vintages as lv

SHORT_ROW = {"runs": 121, "woba": 110, "hr": 121, "n_pa": 34287,
             "year_range": "2025-2026", "venue": "Sutter Health Park"}


def _meta(tmp_path, *, short=None, by_hand=None, park_factors=None):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    meta = {"park_factors": park_factors if park_factors is not None else
            {"NYY": {"woba": 101, "hr": 118, "runs": 102},
             "SEA": {"woba": 92, "hr": 98, "runs": 85}}}
    if short is not None:
        meta["park_factors_short_window"] = short
    if by_hand is not None:
        meta["park_factors_by_hand"] = by_hand
    (data / "fa_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return data


# ===========================================================================
# 1. SERVE_ATH_PARK: off, and off is byte-identical
# ===========================================================================
def test_the_athletics_flag_ships_off():
    """TRIPWIRE. Flipping this moves served prices (section 5i-A). The flip is
    one commit with MODEL_VERSION bumped and --context re-run; change this
    assertion in that commit and nowhere else."""
    assert bm.SERVE_ATH_PARK is False
    assert bm.SHORT_WINDOW_PARK_ORGS == frozenset({"ATH"})


def test_park_index_is_unchanged_with_the_flag_off(tmp_path, monkeypatch):
    data = _meta(tmp_path, short={"orgs": {"ATH": SHORT_ROW}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    assert bm.park_index() == {"NYY": 1.02, "SEA": 0.85}


def test_the_flag_adds_the_shrunk_athletics_factor(tmp_path, monkeypatch):
    data = _meta(tmp_path, short={"orgs": {"ATH": SHORT_ROW}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", True)
    idx = bm.park_index()
    assert idx["ATH"] == 1.1919
    assert idx["NYY"] == 1.02 and idx["SEA"] == 0.85


def test_the_flag_with_no_short_window_block_changes_nothing(tmp_path, monkeypatch):
    """An fa_meta written before the sibling existed: the A's stay neutral."""
    data = _meta(tmp_path)
    monkeypatch.setattr(bm, "DATA_DIR", data)
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", True)
    assert bm.park_index() == {"NYY": 1.02, "SEA": 0.85}


def test_the_short_window_never_overwrites_a_three_season_factor(tmp_path, monkeypatch):
    data = _meta(tmp_path, short={"orgs": {"ATH": SHORT_ROW,
                                           "NYY": dict(SHORT_ROW, runs=150)}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", True)
    assert bm.park_index()["NYY"] == 1.02


def test_only_the_listed_clubs_reach_a_price(tmp_path, monkeypatch):
    """A club that moves next year does not silently join the flag's effect."""
    data = _meta(tmp_path, park_factors={"NYY": {"runs": 102}},
                 short={"orgs": {"ATH": SHORT_ROW, "SEA": SHORT_ROW}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", True)
    assert set(bm.park_index()) == {"NYY", "ATH"}


# ===========================================================================
# 2. the factor is derived from measured constants
# ===========================================================================
def test_the_constants_reproduce_the_documented_factor():
    assert bm.short_window_park_value(SHORT_ROW) == 1.1919
    # The decomposition's own check: the sample-implied single-season
    # reliability against the direct season-to-season correlation 0.6221.
    assert round(bm.park_index_reliability(bm.PARK_INDEX_NOISE_REF_PA), 4) == 0.6238
    assert round(bm.park_index_reliability(34287), 4) == 0.7638
    assert round(bm.park_index_reliability(bm.PARK_INDEX_3YR_REF_PA), 4) == 0.836


def test_the_factor_follows_its_own_sample():
    thin = bm.short_window_park_value(dict(SHORT_ROW, n_pa=9000))
    thick = bm.short_window_park_value(dict(SHORT_ROW, n_pa=50000))
    assert 1.0 < thin < bm.short_window_park_value(SHORT_ROW) < thick <= 1.21


def test_a_long_window_is_never_stretched_past_its_raw_index():
    assert bm.short_window_park_value({"runs": 110, "n_pa": 10_000_000}) == 1.10


def test_a_row_with_no_sample_or_no_index_prices_nothing():
    assert bm.short_window_park_value({"runs": 121, "n_pa": 0}) is None
    assert bm.short_window_park_value({"n_pa": 34287}) is None
    assert bm.short_window_park_value(None) is None
    assert bm.short_window_parks(None) == {}


# ===========================================================================
# 3. the vintage path reads the record's own dated block and nothing else
# ===========================================================================
def test_the_vintage_park_read_is_unchanged_with_the_flag_off():
    rec = {"parks": {"NYY": 1.02}, "parks_short_window": {"ATH": SHORT_ROW}}
    assert bm.parks_from_vintage(rec) == {"NYY": 1.02}


def test_the_vintage_park_read_takes_the_record_s_block_under_the_flag(monkeypatch):
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", True)
    rec = {"parks": {"NYY": 1.02}, "parks_short_window": {"ATH": SHORT_ROW}}
    assert bm.parks_from_vintage(rec) == {"NYY": 1.02, "ATH": 1.1919}
    # A record that predates the block keeps the A's neutral: never filled
    # from today's fa_meta.
    assert bm.parks_from_vintage({"parks": {"NYY": 1.02}}) == {"NYY": 1.02}
    # And no park column at all is still the None sentinel.
    assert bm.parks_from_vintage({"parks_short_window": {"ATH": SHORT_ROW}}) is None


# ===========================================================================
# 4. park by bat side: the candidate, the capture, and darkness
# ===========================================================================
def test_the_hand_reliabilities_are_the_pre_registered_ones():
    assert bm.PARK_HAND_SPLIT_RELIABILITY == {"runs": 0.0191, "hr": 0.3293}
    assert B.HR_HAND_SPLIT_RELIABILITY == bm.PARK_HAND_SPLIT_RELIABILITY["hr"]


def test_the_lineup_park_candidate_is_the_registered_formula():
    bh = {"L": 1.10, "R": 0.90}
    rel = bm.PARK_HAND_SPLIT_RELIABILITY["runs"]
    assert bm.lineup_park_factor(1.0, bh, 1.0) == pytest.approx(1.0 + rel * 0.10)
    assert bm.lineup_park_factor(1.0, bh, 0.0) == pytest.approx(1.0 - rel * 0.10)
    assert bm.lineup_park_factor(1.0, bh, 0.5) == pytest.approx(1.0)
    # The swapped twin is the same function at 1 - s.
    s = 0.7
    a, b = bm.lineup_park_factor(1.0, bh, s), bm.lineup_park_factor(1.0, bh, 1 - s)
    assert (a - 1.0) == pytest.approx(-(b - 1.0))


def test_the_lineup_park_candidate_never_guesses():
    assert bm.lineup_park_factor(None, {"L": 1.1, "R": 0.9}, 0.5) is None
    assert bm.lineup_park_factor(1.0, None, 0.5) is None
    assert bm.lineup_park_factor(1.0, {"L": 1.1}, 0.5) is None
    assert bm.lineup_park_factor(1.0, {"L": 1.1, "R": 0.9}, None) is None
    assert bm.lineup_park_factor(1.0, {"L": 1.1, "R": 0.9}, 1.5) is None


def _order(bats):
    return [{"slot": i + 1, "bats": b, "hem_plus": 100, "pa": 400}
            for i, b in enumerate(bats)]


def test_a_switch_hitter_turns_around_against_the_starter():
    team = {"orders": {"vr": _order(["S", "R", "R", "R", "R", "R", "R", "R", "R"]),
                       "vl": _order(["S", "L", "L", "L", "L", "L", "L", "L", "L"])}}
    w1 = lv.LINEUP_SLOT_PA[1]
    tot = sum(lv.LINEUP_SLOT_PA.values())
    # Against a right-hander the switch hitter bats left: the only lefty.
    assert lv.lhb_share_from_orders(team, "R") == round(w1 / tot, 4)
    # Against a left-hander he bats right, and the other eight are lefties.
    assert lv.lhb_share_from_orders(team, "L") == round((tot - w1) / tot, 4)


def test_an_unreadable_slot_is_skipped_and_a_thin_order_is_null():
    seven = _order(["L", "L", "R", "R", "R", "R", "R", None, "?"])
    team = {"orders": {"vr": seven, "vl": seven}}
    w = lv.LINEUP_SLOT_PA
    expect = (w[1] + w[2]) / sum(w[s] for s in range(1, 8))
    assert lv.lhb_share_from_orders(team, "R") == round(expect, 4)
    six = _order(["L", "L", "R", "R", "R", "R", None, None, None])
    assert lv.lhb_share_from_orders({"orders": {"vr": six}}, "R") is None
    assert lv.lhb_share_from_orders({}, "R") is None


def test_a_down_bat_side_lens_is_a_stated_null_for_every_club():
    blob = {"bat_side": {"available": False},
            "teams": [{"team": "NYY", "orders": {"vr": _order(["L"] * 9),
                                                  "vl": _order(["L"] * 9)}}]}
    mix = lv.build_lineup_hand_mix(blob)
    for col in lv.SCHEMA5_PARK_TEAM_COLUMNS:
        assert mix[col]["values"] == {}
        assert mix[col]["basis"].startswith("ABSENT")


def test_one_pa_by_slot_table_on_the_site():
    import betting_export as be
    assert lv.LINEUP_SLOT_PA == be.SLOT_PA
    assert lv.LINEUP_HAND_MIN_SLOTS == lv.LINEUP_MIN_JOINED_SLOTS


def test_schema5_columns_are_registered():
    """The 5i pair leads the schema-5 block; 5f and 5g ride the same bump
    (docs/diamond-betting.md 5f, "Shared bump") and are appended after it."""
    assert lv.SCHEMA == 5
    assert set(lv.SCHEMA5_TEAM_COLUMNS) < set(lv.TEAM_COLUMNS)
    assert lv.TEAM_COLUMNS[-len(lv.SCHEMA5_TEAM_COLUMNS):] == lv.SCHEMA5_TEAM_COLUMNS
    assert lv.SCHEMA5_TEAM_COLUMNS[:2] == lv.SCHEMA5_PARK_TEAM_COLUMNS
    assert lv.SCHEMA5_PARK_TEAM_COLUMNS == ("lhb_share_vr", "lhb_share_vl")
    for c in lv.SCHEMA5_TEAM_COLUMNS:
        assert c in lv.FEATURE_SOURCES


def _fake_boards(data):
    orgs = ("NYY", "SEA")
    (data / "hitter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-09-10",
        "bat_side": {"available": True},
        "teams": [{"team": o, "offense_plus": 100 + i, "orders": {
            "vr": _order(["L", "L", "S", "R", "R", "R", "R", "R", "R"]),
            "vl": _order(["L", "R", "S", "R", "R", "R", "R", "R", "R"])}}
            for i, o in enumerate(orgs)],
        "hitters": []}), encoding="utf-8")
    (data / "starter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-09-10",
        "teams": [{"team": o, "rotation_plus": 100, "starter_ip": 500.0} for o in orgs],
        "starters": [{"mlbam": 101, "team": "NYY", "sem_plus": 105, "ip_per_gs": 5.5,
                      "role": "SP"}]}), encoding="utf-8")
    (data / "bullpen_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-09-10",
        "teams": [{"team": o, "bullpen_plus": 100, "relief_ip": 300.0} for o in orgs],
        "relievers": []}), encoding="utf-8")


@pytest.fixture
def _quiet_builders(monkeypatch):
    """No network and no feed scan: the hand join, the schema-4 builders and the
    schema-5 pinch-hit tally are stubbed, because this test is about the 5i
    capture alone (conftest already stubs the team-fielding loader)."""
    import betting_usage
    import pal_export
    monkeypatch.setattr(pal_export, "load_pitch_hand", lambda season: {101: "R"})
    monkeypatch.setattr(betting_usage, "build_schema4_team_columns",
                        lambda *a, **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                         for c in lv.SCHEMA4_TEAM_COLUMNS})
    monkeypatch.setattr(betting_usage, "build_pitcher_schema4",
                        lambda *a, **k: {})
    monkeypatch.setattr(betting_usage, "build_schema5_team_columns",
                        lambda *a, **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                         for c in lv.SCHEMA5_PH_TALLY_COLUMNS})


def test_the_snapshot_captures_the_schema5_block(tmp_path, _quiet_builders):
    data = _meta(tmp_path, short={"orgs": {"ATH": SHORT_ROW}},
                 by_hand={"L": {"NYY": {"runs": 106, "hr": 119, "n_pa": 27265}},
                          "R": {"NYY": {"runs": 100, "hr": 117, "n_pa": 28601}}})
    _fake_boards(data)
    rec = lv.reduce_current(on_date="2026-09-11", data_dir=data)
    assert rec["schema"] == 5
    row = lv.team_row(rec, "NYY")
    assert row["lhb_share_vr"] is not None and row["lhb_share_vl"] is not None
    assert row["lhb_share_vr"] > row["lhb_share_vl"], (
        "the switch hitter bats left against a right-hander")
    assert rec["parks_by_hand"] == {"NYY": {"L": 1.06, "R": 1.0,
                                            "hr_L": 1.19, "hr_R": 1.17}}
    assert rec["parks_short_window"]["ATH"]["runs"] == 121
    assert rec["parks_short_window"]["ATH"]["n_pa"] == 34287
    fb = rec["feature_basis"]
    assert fb["lhb_share_vr"]["n"] == 2 and fb["park_by_hand"]["n"] == 1
    assert fb["park_short_window"]["n"] == 1
    # The core park column is untouched by the siblings: ATH is not in it.
    assert "ATH" not in rec["parks"]
    assert bm.parks_by_hand_from_vintage(rec) == rec["parks_by_hand"]


def test_absent_siblings_are_stated_nulls_not_empty_blocks(tmp_path, _quiet_builders):
    data = _meta(tmp_path)
    _fake_boards(data)
    rec = lv.reduce_current(on_date="2026-09-11", data_dir=data)
    assert rec["parks_by_hand"] is None and rec["parks_short_window"] is None
    assert rec["feature_basis"]["park_by_hand"]["basis"].startswith("ABSENT")
    assert bm.parks_by_hand_from_vintage(rec) is None


def test_an_older_record_reads_none_for_the_schema5_columns():
    cols = [c for c in lv.TEAM_COLUMNS if c not in lv.SCHEMA5_TEAM_COLUMNS]
    rec = {"schema": 4, "team_columns": cols,
           "teams": {"NYY": [100.0, 100.0, 100.0, 500.0, 300.0] + [None] * (len(cols) - 5)}}
    row = lv.team_row(rec, "NYY")
    assert row["lhb_share_vr"] is None and row["lhb_share_vl"] is None
    assert bm.parks_by_hand_from_vintage(rec) is None


def test_nothing_served_reads_the_dark_park_terms():
    """The candidate has ONE definition and no served caller. A served function
    that starts reading it has shipped a feature around its gate."""
    import betting_export as be
    served = [bm.expected_runs, bm.game_probabilities, bm._design_rows,
              bm.fit_coefficients, bm.park_index, be.team_bets]
    for fn in served:
        src = inspect.getsource(fn)
        for name in ("lineup_park_factor", "parks_by_hand", "lhb_share"):
            assert name not in src, f"{fn.__name__} reads the dark term {name}"
    assert "lineup_park_factor" not in inspect.getsource(be)
    assert "parks_by_hand" not in inspect.getsource(be)


# ===========================================================================
# 5. the Savant fetcher and the FA-side siblings
# ===========================================================================
class _FR:
    def __init__(self, body):
        self.status, self.body = 200, body


def test_the_default_fetch_is_byte_identical(monkeypatch):
    import fa_sources
    seen = []

    def fake(url, key, force=False):
        seen.append((url, key))
        return _FR("var data = [];")

    monkeypatch.setattr(fa_sources, "_fetch", fake)
    fa_sources.fetch_savant_park_factors(2026, "L")
    fa_sources.fetch_savant_park_factors(2026, "", rolling="2")
    assert seen[0] == ("https://baseballsavant.mlb.com/leaderboard/statcast-park-factors"
                       "?type=year&year=2026&batSide=L&stat=index_wOBA&condition=All"
                       "&rolling=", "savant_pf_2026_L")
    assert seen[1][0].endswith("&rolling=2") and seen[1][1] == "savant_pf_2026_all_r2"


def _savant_rows(*rows):
    return [{"name_display_club": club, "venue_name": venue, "index_runs": str(runs),
             "index_woba": "100", "index_hr": str(hr), "n_pa": str(n),
             "year_range": yr} for club, venue, runs, hr, n, yr in rows]


def test_the_short_window_block_carries_only_the_dropped_clubs(monkeypatch):
    import fa_fit
    import fa_sources

    def fake(year, bat_side="", force=False, rolling=""):
        rows = [("Yankees", "Yankee Stadium", 102, 118, 55865, "2024-2026")]
        if rolling == "2":
            rows += [("Athletics", "Sutter Health Park", 121, 121, 34287, "2025-2026")]
            rows[0] = ("Yankees", "Yankee Stadium", 104, 120, 37000, "2025-2026")
        return _savant_rows(*rows)

    monkeypatch.setattr(fa_sources, "fetch_savant_park_factors", fake)
    fa_fit.park_factors.cache_clear()
    try:
        blk = fa_fit.park_factors_short_window(2026)
        assert set(blk["orgs"]) == {"ATH"}
        assert blk["orgs"]["ATH"]["runs"] == 121 and blk["orgs"]["ATH"]["n_pa"] == 34287
        assert blk["rolling"] == 2
        hand = fa_fit.park_factors_by_hand(2026)
        assert hand["L"]["NYY"]["n_pa"] == 55865 and "R" in hand
    finally:
        fa_fit.park_factors.cache_clear()


# ===========================================================================
# 6. the props hand arms and the total-bases ladder
# ===========================================================================
def test_effective_bat_side():
    assert B.effective_bat_side("L", None) == "L"
    assert B.effective_bat_side("R", "R") == "R"
    assert B.effective_bat_side("S", "R") == "L"
    assert B.effective_bat_side("S", "L") == "R"
    assert B.effective_bat_side("S", None) is None
    assert B.effective_bat_side(None, "R") is None


BY_HAND = {"L": {"NYY": {"hr": 130}}, "R": {"NYY": {"hr": 100}}}
PF = {"NYY": {"hr": 118}}


def test_the_hand_index_is_the_shrunk_registered_formula():
    rel = B.HR_HAND_SPLIT_RELIABILITY
    v, ok = B._park_hr_index_hand("NYY", "L", BY_HAND, PF)
    assert ok and v == pytest.approx(1.18 + rel * (1.30 - 1.18))
    s, ok = B._park_hr_index_hand("NYY", "L", BY_HAND, PF, swap=True)
    assert ok and s == pytest.approx(1.18 + rel * (1.00 - 1.18))


def test_a_hand_arm_with_nothing_to_read_prices_like_the_all_hands_arm():
    for side, bh, org in (("L", None, "NYY"), (None, BY_HAND, "NYY"),
                          ("L", BY_HAND, "ATH")):
        v, ok = B._park_hr_index_hand(org, side, bh, PF)
        assert not ok and v == B._park_hr_index(org, PF)


def test_the_hr_ladder_adds_arms_and_moves_none():
    """A0 to A3 are computed exactly as before the hand arms existed; with no
    by-hand block the two new arms equal A3."""
    rows = [{"game_pk": 1, "date": "2026-05-01", "player_id": 7, "pa": 4, "hr": 1,
             "org": "NYY", "opp": "SEA", "home_org": "NYY", "bat_side": "L"},
            {"game_pk": 2, "date": "2026-05-02", "player_id": 7, "pa": 4, "hr": 0,
             "org": "NYY", "opp": "SEA", "home_org": "NYY", "bat_side": "L"}]
    old = B._walk_forward(rows, B._hr_price(PF), trials_key="pa", event_key="hr")
    new = B._walk_forward(rows, B._hr_price(PF, BY_HAND), trials_key="pa", event_key="hr")
    for o, n in zip(old, new):
        for arm in ("A0_league", "A1_unshrunk", "A2_eb", "A3_eb_park"):
            assert o["priced"].get(arm) == n["priced"].get(arm)
        if o["priced"]:
            assert o["priced"]["A4_eb_park_hand"] == o["priced"]["A3_eb_park"]
            assert n["priced"]["A4_eb_park_hand"] > n["priced"]["A3_eb_park"]
            assert n["priced"]["A4_swap"] < n["priced"]["A3_eb_park"]


def test_a_hand_leg_with_nothing_to_read_is_not_scored_as_a_null():
    """With no by-hand block every hand arm equals the arm it extends, and a
    scored leg would publish a zero-width null that looks like a finding."""
    import numpy as np
    rows = [{"game_pk": g, "date": "2026-06-01", "home_org": "NYY", "bat_side": "L",
             "y": g % 2, "priced": {"A3_eb_park": 0.10, "A4_eb_park_hand": 0.12,
                                    "A4_swap": 0.09}} for g in range(1, 5)]
    off = B._hand_legs(np, rows, None, PF, "A3_eb_park", "A4_eb_park_hand", "A4_swap")
    assert off["hand_leg"] is None and off["hand_twin_leg"] is None
    assert off["hand_absent_reason"].startswith("NOT SCORED")
    assert off["hand_coverage"]["with_hand_index"] == 0
    on = B._hand_legs(np, rows, BY_HAND, PF, "A3_eb_park", "A4_eb_park_hand", "A4_swap")
    assert "paired_delta_vs_A3_eb_park" in on["hand_leg"]["A4_eb_park_hand"]
    assert "paired_delta_vs_A4_swap" in on["hand_twin_leg"]["A4_eb_park_hand"]
    assert on["hand_coverage"]["with_hand_index"] == 4


def test_the_tb_tail_is_exact():
    """Brute force over every outcome sequence of three PAs."""
    probs = {0: 0.55, 1: 0.2, 2: 0.15, 3: 0.03, 4: 0.07}
    brute = 0.0
    for seq in itertools.product(probs, repeat=3):
        if sum(seq) > 1.5:
            brute += math.prod(probs[s] for s in seq)
    assert B.p_tb_over_1_5(probs[1], probs[0], 3) == pytest.approx(brute, abs=1e-12)
    assert B.p_tb_over_1_5(0.2, 0.55, 0) == 0.0


def test_the_tb_ladder_prices_before_it_folds():
    """THE LEAK TEST for the new ladder: the first date is priced from an empty
    accumulator, so it carries no arms at all."""
    rows = [{"game_pk": 1, "date": "2026-05-01", "player_id": 7, "pa": 4, "hr": 2,
             "b1": 1, "b2": 0, "b3": 0, "home_org": "NYY", "bat_side": "R"},
            {"game_pk": 2, "date": "2026-05-02", "player_id": 7, "pa": 4, "hr": 0,
             "b1": 0, "b2": 0, "b3": 0, "home_org": "NYY", "bat_side": "R"}]
    out = B._walk_forward_tb(rows, B._tb_price(PF, BY_HAND))
    assert out[0]["priced"] == {}
    p = out[1]["priced"]
    assert set(p) == {"C0_league", "C2_eb", "C3_eb_park", "C4_eb_park_hand", "C4_swap"}
    # The park only ever raises the HR rate at a 1.18 park, so C3 > C2.
    assert p["C3_eb_park"] > p["C2_eb"]


def _synthetic_tables():
    rows = []
    for d, date in enumerate(("2026-05-01", "2026-05-05", "2026-05-20", "2026-05-25")):
        for p in range(6):
            rows.append({"game_pk": 100 + d, "date": date, "player_id": p,
                         "org": "NYY", "opp": "SEA", "home_org": "NYY",
                         "pa": 4, "hr": (p + d) % 3 == 0, "b1": 1, "b2": p % 2,
                         "b3": 0, "bat_side": "L" if p % 2 else "R"})
    for r in rows:
        r["hr"] = int(r["hr"])
    return {"batters": rows, "starters": [], "skipped": {"no_feed": 0},
            "n_games": 4}


def test_the_driver_runs_both_ladders_and_refuses_an_unreadable_hand(tmp_path, monkeypatch):
    """The whole run() on a synthetic frame, never the real feeds: the new arms
    are not scored against a real outcome before section 5i-C is committed."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "fa_meta.json").write_text(
        json.dumps({"park_factors": {"NYY": {"hr": 118}}}), encoding="utf-8")
    monkeypatch.setattr(B, "ROOT", tmp_path)
    monkeypatch.setattr(B, "build_tables", lambda **k: _synthetic_tables())
    art = B.run(write=False)
    hr, tb = art["home_runs"], art["total_bases"]
    assert hr["hand_leg"] is None and "NOT SCORED" in hr["hand_absent_reason"]
    assert tb["hand_leg"] is None and tb["line"] == B.TB_LINE
    assert set(tb["arms"]) == {"C0_league", "C2_eb", "C3_eb_park"}
    assert "C3_eb_park" in tb["structure_leg"]
    # The pre-existing HR blocks keep exactly their arm sets.
    assert set(hr["arms"]) == {"A0_league", "A1_unshrunk", "A2_eb", "A3_eb_park"}
    assert set(hr["structure_leg"]) == {"A2_eb", "A3_eb_park"}
    # And with the sibling present the legs are scored.
    (tmp_path / "data" / "fa_meta.json").write_text(json.dumps({
        "park_factors": {"NYY": {"hr": 118}},
        "park_factors_by_hand": {"L": {"NYY": {"hr": 130}}, "R": {"NYY": {"hr": 100}}}}),
        encoding="utf-8")
    art = B.run(write=False)
    assert art["home_runs"]["hand_coverage"]["with_hand_index"] > 0
    assert "A4_eb_park_hand" in art["home_runs"]["hand_leg"]
    assert "C4_eb_park_hand" in art["total_bases"]["hand_twin_leg"]
    assert art["coverage"]["park_by_hand_orgs"] == {"L": 1, "R": 1}


def test_build_tables_reads_the_side_off_the_feed(monkeypatch):
    feed = {
        "gameData": {"players": {
            "ID1": {"batSide": {"code": "S"}}, "ID2": {"batSide": {"code": "L"}},
            "ID9": {"pitchHand": {"code": "R"}}, "ID8": {"pitchHand": {"code": "L"}}}},
        "liveData": {"boxscore": {"teams": {
            "home": {"batters": [1], "pitchers": [8], "players": {
                "ID1": {"stats": {"batting": {"plateAppearances": 4, "hits": 3,
                                              "doubles": 1, "triples": 0,
                                              "homeRuns": 1}}}}},
            "away": {"batters": [2], "pitchers": [9], "players": {
                "ID2": {"stats": {"batting": {"plateAppearances": 4, "hits": 0}}}}}}}}}
    monkeypatch.setattr(B, "_feed", lambda pk: feed)
    t = B.build_tables(games=[{"game_pk": 5, "date": "2026-06-01",
                               "home_org": "NYY", "away_org": "SEA"}])
    by = {r["player_id"]: r for r in t["batters"]}
    # Home switch hitter faces the away starter (ID9, a right-hander): bats left.
    assert by[1]["bat_side"] == "L"
    assert (by[1]["b1"], by[1]["b2"], by[1]["b3"], by[1]["hr"]) == (1, 1, 0, 1)
    assert by[2]["bat_side"] == "L"
