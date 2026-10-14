"""Ballpark awareness for /betting/ (docs/diamond-betting.md section 5i).

WHAT THESE TESTS PROTECT, in the order a regression would hurt:

  1. THE FLAG IS ON (owner decision 2, 2026-09-11) AND OFF STILL MEANS
     BYTE-IDENTICAL. SERVE_ATH_PARK moves served prices and the value side of a
     total. With it False, park_index() and the vintage park read return exactly
     what they returned before 2026-09-11, so the flag is a one-line rollback.
  1b. THE VENUE AUDIT (every club, 2021-2026, off the cached StatsAPI feeds and
     Savant's single-season pages). The Rays played 2025 at George M.
     Steinbrenner Field and all 72 of their 2026 home games at Tropicana Field,
     so the 2024-2026 Tropicana row holds two seasons; it prices shrunk by its
     own sample, the same way as the Athletics' Sutter Health Park row, and a
     short row can only ever move a factor toward neutral. The team fit and the
     DFS park leg read the same venue-correct table.
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
# 1. SERVE_ATH_PARK: on, and off is still byte-identical
# ===========================================================================
def test_the_short_window_park_flag_ships_on():
    """TRIPWIRE. The flag went live on 2026-09-11 (owner decision 2, with the
    Rays added by the venue audit) in ONE commit with MODEL_VERSION bumped and
    --context re-run. Change this assertion only in a commit that moves the
    flag, the club list and the ledger key together."""
    assert bm.SERVE_ATH_PARK is True
    assert bm.SHORT_WINDOW_PARK_ORGS == frozenset({"ATH", "TBR"})
    assert bm.MODEL_VERSION != "betting_runs_v1", (
        "serving the short-window parks without a MODEL_VERSION bump pools two "
        "pricers in every ledger")


def test_park_index_is_unchanged_with_the_flag_off(tmp_path, monkeypatch):
    data = _meta(tmp_path, short={"orgs": {"ATH": SHORT_ROW}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", False)
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
def test_the_vintage_park_read_is_unchanged_with_the_flag_off(monkeypatch):
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", False)
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
# 3b. the venue audit: the Rays' two-season Tropicana row
# ===========================================================================
TROP_ROW = {"runs": 94, "woba": 97, "hr": 105, "n_pa": 34828, "year_range": "2024-2026",
            "venue": "Tropicana Field", "window": "default"}


def test_the_rays_three_season_row_is_shrunk_by_its_own_sample(tmp_path, monkeypatch):
    """Tropicana's 2024-2026 row holds 2024 and 2026 only (2025 was played at
    Steinbrenner Field), so it prices like the short sample it is."""
    data = _meta(tmp_path, park_factors={"NYY": {"runs": 102}, "TBR": {"runs": 94}},
                 short={"orgs": {"ATH": SHORT_ROW, "TBR": TROP_ROW}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    idx = bm.park_index()
    assert idx["TBR"] == bm.short_window_park_value(TROP_ROW) == 0.945
    assert idx["ATH"] == 1.1919 and idx["NYY"] == 1.02
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", False)
    assert bm.park_index() == {"NYY": 1.02, "TBR": 0.94}


def test_a_short_row_carrying_another_number_is_refused(tmp_path, monkeypatch):
    """The short row may only shrink the served factor by that factor's OWN
    sample. A row with a different index is another measurement and never
    replaces a 3-season factor."""
    data = _meta(tmp_path, park_factors={"TBR": {"runs": 94}},
                 short={"orgs": {"TBR": dict(TROP_ROW, runs=110)}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    assert bm.park_index() == {"TBR": 0.94}


@pytest.mark.parametrize("runs", [80, 94, 100, 106, 121, 130])
@pytest.mark.parametrize("n_pa", [5_000, 17_577, 34_828, 54_034, 90_000])
def test_a_short_row_only_ever_moves_a_factor_toward_neutral(runs, n_pa):
    raw = runs / 100.0
    got = bm.short_window_parks({"orgs": {"TBR": {"runs": runs, "n_pa": n_pa}}},
                                measured={"TBR": raw})["TBR"]
    assert min(1.0, raw) - 1e-9 <= got <= max(1.0, raw) + 1e-9


def test_the_vintage_path_shrinks_the_rays_from_the_record_s_own_block(monkeypatch):
    rec = {"parks": {"TBR": 0.94, "NYY": 1.02}, "parks_short_window": {"TBR": TROP_ROW}}
    assert bm.parks_from_vintage(rec) == {"TBR": 0.945, "NYY": 1.02}
    # A record written before the block keeps the raw 3-season factor.
    assert bm.parks_from_vintage({"parks": {"TBR": 0.94}}) == {"TBR": 0.94}


def test_the_listed_clubs_are_the_ones_the_served_block_carries():
    """THE SERVED STATE, AND IT FAILS RATHER THAN SKIPS. data/fa_meta.json is
    what the board, the refit and DFS read, and the nightly checkout reverts it
    to its committed copy before any of them run, so a committed file without
    the block leaves the flag doing nothing while the rows say v2. The explicit
    list and the measured block must also agree: a club that moves and lands in
    the block without joining the list (or a listed club the block no longer
    carries) fails here rather than pricing one way on the board and another in
    the audit. And the block's own venue check must find every club at the park
    it plays in."""
    p = bm.ROOT / "data" / "fa_meta.json"
    meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    blk = meta.get("park_factors_short_window")
    if not bm.SERVE_ATH_PARK:
        pytest.skip("SERVE_ATH_PARK is off; nothing is promised")
    assert isinstance(blk, dict) and isinstance(blk.get("orgs"), dict), (
        "SERVE_ATH_PARK is on but data/fa_meta.json carries no "
        "park_factors_short_window block: run `python fa_export.py --park-blocks` "
        "and commit data/fa_meta.json")
    assert set(blk["orgs"]) == set(bm.SHORT_WINDOW_PARK_ORGS)
    assert bm.short_window_parks_missing(meta) == []
    vc = blk.get("venue_check") or {}
    assert vc.get("status") == "checked", vc
    assert vc.get("mismatch") == {}, vc["mismatch"]
    assert all(r.get("venue_match") is True for r in blk["orgs"].values())


def test_a_row_at_another_venue_never_prices(tmp_path, monkeypatch):
    """fa_fit's venue check marks a row whose Savant venue is not where the club
    plays; the consumer refuses it outright, on the live and the vintage path."""
    bad = dict(SHORT_ROW, venue_match=False)
    data = _meta(tmp_path, short={"orgs": {"ATH": bad}})
    monkeypatch.setattr(bm, "DATA_DIR", data)
    assert "ATH" not in bm.park_index()
    assert bm.parks_from_vintage({"parks": {"NYY": 1.02},
                                  "parks_short_window": {"ATH": bad}}) == {"NYY": 1.02}
    ok = dict(SHORT_ROW, venue_match=True)
    assert bm.short_window_parks({"orgs": {"ATH": ok}}) == {"ATH": 1.1919}


def test_a_listed_club_the_block_cannot_price_is_named_and_logged(tmp_path, monkeypatch):
    meta = {"park_factors": {"TBR": {"runs": 94}}}
    assert bm.short_window_parks_missing(meta) == ["ATH", "TBR"]
    meta["park_factors_short_window"] = {"orgs": {"ATH": SHORT_ROW, "TBR": TROP_ROW}}
    assert bm.short_window_parks_missing(meta) == []
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", False)
    assert bm.short_window_parks_missing({}) == []
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", True)
    data = _meta(tmp_path)                      # no short-window block on disk
    monkeypatch.setattr(bm, "DATA_DIR", data)
    monkeypatch.setattr(bm, "_SHORT_PARK_WARNED", set())
    said = []
    monkeypatch.setattr(bm.log, "warning", lambda msg, *a: said.append(msg % a))
    assert bm.park_index() == {"NYY": 1.02, "SEA": 0.85}
    bm.park_index()
    hits = [m for m in said if "park_factors_short_window" in m]
    assert len(hits) == 1 and "ATH, TBR" in hits[0], said


def test_the_team_fit_reads_the_venue_correct_row(monkeypatch):
    import fa_fit
    base = {"NYY": {"woba": 101, "hr": 118, "runs": 102},
            "TBR": {"woba": 97, "hr": 105, "runs": 94}}
    monkeypatch.setattr(fa_fit, "park_factors", lambda season, bat_side="": base)
    monkeypatch.setattr(fa_fit, "_short_window_rows",
                        lambda season: {"ATH": dict(SHORT_ROW, window="rolling=2"),
                                        "TBR": TROP_ROW})
    k_ath = bm.short_window_shrink(SHORT_ROW["n_pa"])
    k_tbr = bm.short_window_shrink(TROP_ROW["n_pa"])
    ath = fa_fit.venue_park_row("ATH", 2026)
    assert ath == {"woba": round(100 + k_ath * 10, 1), "hr": round(100 + k_ath * 21, 1),
                   "runs": round(100 + k_ath * 21, 1)}
    assert fa_fit.venue_park_row("TBR", 2026)["runs"] == round(100 - k_tbr * 6, 1)
    assert fa_fit.venue_park_row("NYY", 2026) == base["NYY"]
    hitter = {"position": "CF", "bat_throw": "R/R"}
    assert fa_fit.park_component(hitter, "ATH", 2026)["score"] > 0.7
    monkeypatch.setattr(bm, "SERVE_ATH_PARK", False)
    assert fa_fit.venue_park_row("ATH", 2026) is None
    assert fa_fit.park_component(hitter, "ATH", 2026)["score"] == pytest.approx(0.5)


def test_the_dfs_park_leg_prices_the_same_venue_correct_table():
    import dfs_export as dx
    meta = {"park_factors": {"NYY": {"runs": 106}, "TBR": {"runs": 94}},
            "park_factors_short_window": {"orgs": {"ATH": SHORT_ROW, "TBR": TROP_ROW}}}
    idx = dx._park_factors(2026, raw={}, meta=meta,
                           home_venues={3313: "NYY", 12: "TBR", 2529: "ATH"})
    # The source is the one the page counts and labels as an applied park; the
    # short window rides beside it with its sample and the unshrunk factor.
    assert idx[3313] == {"pf": 1.06, "source": "savant_mlb", "org": "NYY"}
    assert idx[12] == {"pf": 0.945, "source": "savant_mlb", "org": "TBR", "window": "short",
                       "pf_raw": 0.94, "n_pa": 34828}
    assert idx[2529] == {"pf": 1.1919, "source": "savant_mlb", "org": "ATH",
                         "window": "short", "pf_raw": None, "n_pa": 34287}
    assert bm.park_index_from_meta(meta) == {"NYY": 1.06, "TBR": 0.945, "ATH": 1.1919}
    assert dx._park_leg(idx, 2529, "savant_mlb") == (1.1919, "savant_mlb")
    assert "park" in dx._est(["matchup"], "savant_mlb")
    assert dx._park_window(idx, 12) == "short" and dx._park_window(idx, 3313) is None
    assert dx._park_basis(idx) == "savant_mlb"
    # Every source the exporter can write is one the page knows (assets/dfs.js
    # counts and labels an applied park by exactly these two names).
    js = (bm.ROOT / "assets" / "dfs.js").read_text(encoding="utf-8")
    for src in dx._PARK_APPLIED:
        assert f'"{src}"' in js or f".{src}" in js, src


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


def test_the_hand_mix_weights_are_the_frozen_literal():
    """5i-B's weights are a REGISTERED LITERAL (docs/diamond-betting.md 5i,
    amendment 2026-09-17), not a read of whatever the served props table holds
    this month. What stood here was `lv.LINEUP_SLOT_PA == be.SLOT_PA`, which is
    stop item X4 in executable form: it pinned a dark column's constant to a
    served constant, so a repair of the served table would have moved the dark
    column's input membership without anyone writing it down. The nine numbers
    below are what every vintage's lhb_share_vr and lhb_share_vl were built
    with and what they stay built with."""
    assert lv.LINEUP_SLOT_PA == {1: 4.65, 2: 4.55, 3: 4.45, 4: 4.35, 5: 4.25,
                                 6: 4.15, 7: 4.05, 8: 3.95, 9: 3.85}
    assert sum(lv.LINEUP_SLOT_PA.values()) == 38.25
    assert lv.LINEUP_HAND_MIN_SLOTS == lv.LINEUP_MIN_JOINED_SLOTS


def test_schema5_columns_are_registered():
    """The 5i pair leads the schema-5 block; 5f and 5g ride the same bump
    (docs/diamond-betting.md 5f, "Shared bump") and are appended after it."""
    assert lv.SCHEMA >= 5
    assert set(lv.SCHEMA5_TEAM_COLUMNS) < set(lv.TEAM_COLUMNS)
    # Later schemas append after the schema-5 block (the game-intensity columns
    # since 2026-10-14), so the block is pinned as the tail of the columns
    # through schema 5, never by a literal schema number.
    through5 = tuple(c for c in lv.TEAM_COLUMNS
                     if c not in lv.IX_TEAM_COLUMNS + lv.SW_TEAM_COLUMNS)
    assert through5[-len(lv.SCHEMA5_TEAM_COLUMNS):] == lv.SCHEMA5_TEAM_COLUMNS
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
    assert rec["schema"] == lv.SCHEMA
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
    """(club, venue, runs, hr, n_pa, year_range[, venue_id]) -> Savant rows."""
    out = []
    for r in rows:
        club, venue, runs, hr, n, yr = r[:6]
        row = {"name_display_club": club, "venue_name": venue, "index_runs": str(runs),
               "index_woba": "100", "index_hr": str(hr), "n_pa": str(n),
               "year_range": yr}
        if len(r) > 6:
            row["venue_id"] = str(r[6])
        out.append(row)
    return out


@pytest.fixture
def _no_statsapi(monkeypatch):
    """The venue check's StatsAPI half, off the network: no map unless a test
    passes one."""
    import fa_fit
    monkeypatch.setattr(fa_fit, "_home_venue_ids", lambda season: None)


def test_the_short_window_block_carries_only_the_dropped_clubs(monkeypatch, _no_statsapi):
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
        assert blk["orgs"]["ATH"]["window"] == "rolling=2"
        assert blk["orgs"]["ATH"]["venue_match"] is None
        assert blk["venue_check"]["status"] == "unavailable"
        assert blk["rolling"] == 2
        hand = fa_fit.park_factors_by_hand(2026)
        assert hand["L"]["NYY"]["n_pa"] == 55865 and "R" in hand
    finally:
        fa_fit.park_factors.cache_clear()


_HOME_2026 = {"NYY": 3313, "STL": 2889, "DET": 2394, "TBR": 12, "ATH": 2529}


def _fake_2026(year, bat_side="", force=False, rolling=""):
    rows = [("Yankees", "Yankee Stadium", 102, 118, 55865, "2024-2026", 3313),
            ("Cardinals", "Busch Stadium", 94, 76, 52539, "2024-2026", 2889),
            ("Tigers", "Comerica Park", 100, 100, 53975, "2024-2026", 2394),
            ("Rays", "Tropicana Field", 94, 105, 34828, "2024-2026", 12)]
    if rolling == "2":
        rows = [("Athletics", "Sutter Health Park", 121, 121, 34287, "2025-2026", 2529),
                ("Rays", "Tropicana Field", 98, 112, 15145, "2025-2026", 12)]
    return _savant_rows(*rows)


def test_the_short_window_block_carries_a_short_sample_default_row(monkeypatch):
    """The 2026-09-11 shape: the default view carries Tropicana on 0.645 of the
    median sample. Its own row lands in the block, labelled `default`; a row
    near the median does not; and every row is at the venue StatsAPI says the
    club plays in."""
    import fa_fit
    import fa_sources

    monkeypatch.setattr(fa_sources, "fetch_savant_park_factors", _fake_2026)
    fa_fit.park_factors.cache_clear()
    try:
        blk = fa_fit.park_factors_short_window(2026, home_venues=_HOME_2026)
        assert set(blk["orgs"]) == {"ATH", "TBR"}
        tbr = blk["orgs"]["TBR"]
        # The DEFAULT view's own row (94 on 34,828), never the rolling=2 one.
        assert (tbr["runs"], tbr["n_pa"], tbr["window"]) == (94, 34828, "default")
        assert (tbr["venue_id"], tbr["statsapi_venue_id"], tbr["venue_match"]) == (12, 12, True)
        assert blk["orgs"]["ATH"]["venue_match"] is True
        assert blk["default_view_median_n_pa"] == (52539 + 53975) / 2
        assert blk["short_sample_pa_share"] == fa_fit.SHORT_SAMPLE_PA_SHARE
        vc = blk["venue_check"]
        assert (vc["status"], vc["n_default_rows"], vc["n_match"]) == ("checked", 4, 4)
        assert vc["mismatch"] == {} and vc["absent_from_default_view"] == ["ATH"]
        assert blk["refused"] == {}
    finally:
        fa_fit.park_factors.cache_clear()


def test_a_club_that_moved_never_prices_at_the_park_it_left(monkeypatch):
    """The venue rule, not only the sample rule: were the Rays listed at
    Steinbrenner Field (2523) by StatsAPI while Savant's short row named
    Tropicana, the row is refused, named in `refused`, and the venue check
    reports the mismatch."""
    import fa_fit
    import fa_sources

    monkeypatch.setattr(fa_sources, "fetch_savant_park_factors", _fake_2026)
    fa_fit.park_factors.cache_clear()
    try:
        blk = fa_fit.park_factors_short_window(2026, home_venues=dict(_HOME_2026, TBR=2523))
        assert set(blk["orgs"]) == {"ATH"}
        assert blk["refused"]["TBR"]["venue_id"] == 12
        assert blk["refused"]["TBR"]["statsapi_venue_id"] == 2523
        assert blk["venue_check"]["mismatch"] == {
            "TBR": {"savant_venue": "Tropicana Field", "savant_venue_id": 12,
                    "statsapi_venue_id": 2523}}
    finally:
        fa_fit.park_factors.cache_clear()


def test_the_park_blocks_refresh_rewrites_only_their_own_keys(tmp_path, monkeypatch):
    """fa_export.refresh_park_siblings: the two sibling blocks are rebuilt, every
    other key is left as it was, and a builder that fails keeps the block on
    disk rather than writing a null over a served park."""
    import fa_export
    import fa_fit
    path = tmp_path / "fa_meta.json"
    meta = {"class_year": 2027, "park_factors": {"NYY": {"runs": 102}},
            "teams": [{"org": "NYY"}], "park_factors_by_hand": {"old": True}}
    path.write_text(json.dumps(meta), encoding="utf-8")
    new_blk = {"season": 2026, "orgs": {"ATH": SHORT_ROW}}
    seen = []
    monkeypatch.setattr(fa_fit, "park_factors_short_window",
                        lambda season: seen.append(season) or new_blk)

    def boom(season):
        raise OSError("savant down")

    monkeypatch.setattr(fa_fit, "park_factors_by_hand", boom)
    got = fa_export.refresh_park_siblings(path, log_fn=lambda *_a: None)
    assert seen == [2026] and got["season"] == 2026 and got["written"] is True
    assert got["blocks"] == {"park_factors_short_window": "refreshed",
                             "park_factors_by_hand": "kept"}
    out = json.loads(path.read_text(encoding="utf-8"))
    assert out["park_factors_short_window"] == new_blk
    assert out["park_factors_by_hand"] == {"old": True}
    assert {k: out[k] for k in ("class_year", "park_factors", "teams")} == {
        k: meta[k] for k in ("class_year", "park_factors", "teams")}
    again = fa_export.refresh_park_siblings(path, log_fn=lambda *_a: None)
    assert again["written"] is False
    assert again["blocks"]["park_factors_short_window"] == "unchanged"


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
