# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The In-Game Management decision ledger (mgmt_decisions.py), pinned.

THE FIVE THINGS THE LANE MUST NOT GET WRONG (spec section 0), each a test here:

  1. THE LEADERBOARD IS REALIZED VALUE, NOT SKILL, and the payload says so verbatim.
  2. THE AGENT IS THE CLUB-SEASON until the manager ledger lands.
  3. WINDOW VALUE IS AN ENDPOINT DIFFERENCE, never a sum of wpa_home rows; the chain
     breaks on a published share of plays at a published tolerance.
  4. THE STATE THE MANAGER DECIDED FROM IS PRE-PLAY, with notna() base occupancy
     (bool(NaN) is True) and a null LI on the leadoff plate appearance carried as null.
  5. THE FAMILY BOUNDARY IS WHAT THE CORPUS CAN NAME: the removed pitcher is derived,
     every defensive switch classifies, a pinch hitter charged to the departed batter is
     flagged and kept, a pinch runner's window ends with the half, an intentional walk's
     covers the on-deck plate appearance, a defensive sub's is stored and never summed.

Most tests run on a nine-plate-appearance synthetic game so they need no corpus; the
served-artifact tests read data/management_decisions.json (produced by the same module;
catalog pin for management_baseline.json and the shard family mgmt_decisions/*.json)
and skip when it is absent. Nothing here writes under data/.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import mgmt_decisions as MD  # noqa: E402

ART = ROOT / "data" / "management_decisions.json"
BOARD = ROOT / "data" / "management_board.json"
BASELINE = ROOT / "data" / "management_baseline.json"
SHARDS = ROOT / "data" / "mgmt_decisions"
CORPUS = ROOT / ".cache" / "pbp_corpus"
NAN = float("nan")


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("run python mgmt_decisions.py")
    d = json.loads(ART.read_text(encoding="utf-8"))
    if d.get("status") != "built":
        pytest.skip(f"ledger not built: {d.get('status')}")
    return d


@pytest.fixture(scope="module")
def board():
    if not BOARD.exists():
        pytest.skip("run python mgmt_export.py")
    return json.loads(BOARD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shard_payload(art):
    """One schema-2 shard as written (2025, the first club in the index)."""
    idx = (art.get("shards") or {}).get("index") or []
    if not idx:
        pytest.skip("no shards on this build")
    pick = [e for e in idx if e["season"] == 2025] or idx
    p = SHARDS / f"{pick[0]['season']}-{pick[0]['club']}.json"
    if not p.exists():
        pytest.skip(f"{p.name} not on disk")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shard(shard_payload):
    """The same shard through the one reader: header plus the schema-1 rows that
    mgmt_shards.expand (the Python twin of expandShard in management.js) rebuilds."""
    import mgmt_shards
    d = {k: v for k, v in shard_payload.items() if k != "families"}
    d["rows"] = mgmt_shards.expand(shard_payload)
    return d


# --------------------------------------------------------------------------
# the synthetic game: one game, nine plate appearances, every family once
# --------------------------------------------------------------------------

def _plays():
    """wp_home_before = 50 + 2k, wp_home_after = 51 + 2k, so consecutive plays never
    chain (a one-point gap between every pair) and a window (i, j) is worth exactly
    1 + 2(j - i) points to the home club."""
    import pandas as pd
    rows = [
        # ab half inn batter pitcher etype event ob oa on1 on2 on3 runs hs as li
        (0, "top", 1, 201, 100, "field_out", "Flyout", 0, 1, NAN, NAN, NAN, 0, 0, 0, NAN),
        (1, "top", 1, 202, 100, "strikeout", "Strikeout", 1, 2, NAN, NAN, NAN, 0, 0, 0, 0.8),
        (2, "top", 1, 203, 100, "field_out", "Groundout", 2, 3, NAN, NAN, NAN, 0, 0, 0, 0.7),
        (3, "bottom", 1, 101, 300, "single", "Single", 0, 0, NAN, NAN, NAN, 0, 0, 0, 0.9),
        (4, "bottom", 1, 102, 300, "sac_bunt", "Sac Bunt", 0, 1, 199.0, NAN, NAN, 0, 0, 0, 1.1),
        (5, "bottom", 1, 103, 300, "field_out", "Groundout", 1, 2, NAN, 199.0, NAN, 0, 0, 0, 1.2),
        (6, "top", 2, 201, 110, "field_out", "Flyout", 0, 1, NAN, NAN, NAN, 0, 0, 0, 0.9),
        (7, "top", 2, 202, 110, "intent_walk", "Intent Walk", 1, 1, NAN, NAN, NAN, 0, 0, 0, 1.0),
        (8, "top", 2, 203, 120, "strikeout", "Strikeout", 1, 2, 202.0, NAN, NAN, 0, 0, 0, 1.3),
    ]
    out = []
    for (ab, half, inn, b, p, et, ev, ob, oa, o1, o2, o3, runs, hs, as_, li) in rows:
        out.append({"game_pk": 1, "season": 2099, "half": half, "inning": inn, "at_bat_index": ab,
                    "batter_id": b, "bat_side": "R", "pitcher_id": p, "pitch_hand": "L",
                    "event_type": et, "event": ev, "rbi": 0, "away_score": as_, "home_score": hs,
                    "outs_after": oa, "balls": 0, "strikes": 0, "leverage_index": li, "drama_index": 0.0,
                    "wp_home_before": 50.0 + 2 * ab, "wp_home_after": 51.0 + 2 * ab, "wpa_home": 1.0,
                    "outs_before": ob, "on_first": o1, "on_second": o2, "on_third": o3,
                    "runs_scored_on_play": runs})
    return pd.DataFrame(out)


def _events():
    import pandas as pd
    base = {"game_pk": 1, "season": 2099, "type": "action", "event": "", "base": NAN,
            "position_code": None, "batting_order": None, "replaced_player_id": NAN, "is_substitution": False}
    rows = [
        {**base, "at_bat_index": 0, "index": 0, "event_type": "mound_visit", "description": "Mound Visit.", "player_id": NAN},
        {**base, "at_bat_index": 4, "index": 0, "event_type": "offensive_substitution", "position_code": "12",
         "description": "Offensive Substitution: Pinch-runner PR replaces Batter One.", "player_id": 199.0,
         "replaced_player_id": 101.0, "base": 1.0, "batting_order": "101", "is_substitution": True},
        {**base, "at_bat_index": 6, "index": 0, "event_type": "pitching_substitution", "position_code": "1",
         "description": "Pitching Change: Reliever B replaces Starter A.", "player_id": 110.0, "is_substitution": True},
        {**base, "at_bat_index": 6, "index": 1, "event_type": "defensive_substitution", "position_code": "9",
         "description": "Defensive Substitution: Glove replaces right fielder Batter Three, batting 3rd, playing right field.",
         "player_id": 130.0, "replaced_player_id": 103.0, "batting_order": "301", "is_substitution": True},
        {**base, "at_bat_index": 8, "index": 0, "event_type": "pitching_substitution", "position_code": "1",
         "description": "Pitching Change: Reliever C replaces Reliever B.", "player_id": 120.0, "is_substitution": True},
        {**base, "at_bat_index": 8, "index": 1, "event_type": "offensive_substitution", "position_code": "11",
         "description": "Offensive Substitution: Pinch-hitter PH replaces Away Three.", "player_id": 250.0,
         "replaced_player_id": 203.0, "batting_order": "301", "is_substitution": True},
    ]
    return pd.DataFrame(rows)


def _pitches():
    import pandas as pd
    rows = []
    for ab in range(9):
        for n in range(3):
            rows.append({"game_pk": 1, "at_bat_index": ab, "call_code": "L" if (ab == 5 and n == 0) else "S", "is_pitch": True})
    return pd.DataFrame(rows)


NAMES = {100: "Starter A", 110: "Reliever B", 120: "Reliever C", 199: "PR", 250: "PH", 101: "Batter One",
         103: "Batter Three", 202: "Away Two", 203: "Away Three", 130: "Glove"}
TMAP = {1: {"home": "NYY", "away": "BOS", "season": 2099}}


@pytest.fixture(scope="module")
def ctx():
    return MD.SeasonCtx(2099, _plays(), _events(), _pitches(), TMAP)


@pytest.fixture(scope="module")
def rows(ctx):
    out, _meta = MD.build_season(ctx, NAMES, {1: "2099-04-01"}, attempts=None, bunt_cells={(0, 1): -0.02})
    return out


def _one(rows, family, **match):
    got = [r for r in rows if r["family"] == family and all(r.get(k) == v for k, v in match.items())]
    assert got, f"no {family} row matching {match}"
    return got[0]


# --------------------------------------------------------------------------
# 3. the window is an endpoint difference
# --------------------------------------------------------------------------

def test_window_value_is_an_endpoint_difference_not_a_row_sum(rows):
    """Fixture with a chain break on every pair of plays: the reliever's stint covers
    plate appearances 6 and 7, whose wpa_home rows sum to 2 points while the endpoints
    move 3 (62.0 before the first to 65.0 after the last)."""
    r = _one(rows, "pitching_change", kind="starter_hook")
    assert r["win_len"] == 2
    assert r["mwpa"] == pytest.approx(0.03)
    row_sum = 2 * 1.0 / 100.0
    assert r["mwpa"] != pytest.approx(row_sum)
    assert MD.window_mwpa(50.0, 70.0, True) == pytest.approx(0.20)
    assert MD.window_mwpa(None, 70.0, True) is None


def test_per_play_wpa_identity_holds_and_games_start_at_fifty_and_end_at_zero_or_hundred(art):
    """Every complete season: identity exact, every game 50.0 to 0 or 100. The current
    season may hold a game still open at the corpus rebuild (suspended, or in progress
    on the last day); it is counted and its windows close at its last play."""
    partial = {r["season"] for r in art["clubs"]["rows"] if r.get("partial")}
    for season, cb in art["chain_break"]["by_season"].items():
        assert cb["per_play_identity_max_abs_error"] < 1e-9, season
        assert cb["games_start_at_fifty"] is True, season
        if int(season) in partial:
            assert cb["games_not_terminal"] <= 5, (season, cb["games_not_terminal"])
        else:
            assert cb["games_end_at_zero_or_hundred"] is True, season
            assert cb["games_not_terminal"] == 0, season


def test_the_chain_break_share_is_published(art, board):
    """3.04 percent of 2025 plays do not chain at a 1e-9 tolerance; the share is
    tolerance-dependent, so the constant travels beside it."""
    assert MD.CHAIN_TOL == 1e-9
    cb = art["chain_break"]
    assert cb["tolerance"] == MD.CHAIN_TOL
    s25 = cb["by_season"].get("2025")
    if s25 is None:
        pytest.skip("2025 not in the corpus")
    assert 0.0300 <= s25["share_of_plays_not_chained"] <= 0.0310
    assert s25["max_gap_points"] == pytest.approx(32.1, abs=0.05)
    assert s25["row_sum_misses_median_points"] == pytest.approx(2.3, abs=0.1)
    served = board["decisions"]["chain_break"]
    assert served["tolerance"] == MD.CHAIN_TOL
    assert served["by_season"]["2025"]["share_of_plays_not_chained"] == s25["share_of_plays_not_chained"]


def test_sign_flips_to_the_deciding_club_in_both_halves(rows):
    assert MD.deciding_club_is_home("top", "bat") is False
    assert MD.deciding_club_is_home("bottom", "bat") is True
    assert MD.deciding_club_is_home("top", "field") is True
    assert MD.deciding_club_is_home("bottom", "field") is False
    assert MD.window_mwpa(40.0, 60.0, True) == pytest.approx(0.2)
    assert MD.window_mwpa(40.0, 60.0, False) == pytest.approx(-0.2)
    # the pinch hitter bats for the AWAY club in the top of the second: the home
    # club's win probability rose one point over the plate appearance, so the
    # deciding club's realized value is minus one hundredth of a win
    ph = _one(rows, "pinch_hit")
    assert ph["club"] == "BOS" and ph["home"] is False
    assert ph["mwpa"] == pytest.approx(-0.01)
    pc = _one(rows, "pitching_change", kind="starter_hook")
    assert pc["club"] == "NYY" and pc["home"] is True and pc["mwpa"] > 0


# --------------------------------------------------------------------------
# 5. the family boundary
# --------------------------------------------------------------------------

def test_the_removed_pitcher_is_the_previous_pitcher_of_the_same_side(rows, art):
    """Derived: the pitcher of the same fielding side's previous plate appearance,
    never the other side's (the away club's pitcher threw the bottom of the first in
    between). MEASURED 2026-09-23: replaced_player_id on a pitching change names the
    LINEUP-SLOT occupant leaving on a double switch, so agreement is checked against
    the description's replaces-NAME clause on every row, and against the field only
    where the description says replacing pitcher NAME."""
    hook = _one(rows, "pitching_change", kind="starter_hook")
    assert hook["out_id"] == 100 and hook["in_id"] == 110
    assert hook["pitch_count"] == 9 and hook["tto"] == 1
    second = _one(rows, "pitching_change", kind="reliever_change")
    assert second["out_id"] == 110 and second["in_id"] == 120
    rp = art["removed_pitcher"]
    assert rp["description_checked"] > 100000
    assert rp["description_agreement_rate"] >= 0.99
    assert rp["replacing_pitcher_clause_rows"] > 0
    assert rp["replacing_pitcher_clause_agree"] >= 0.999 * rp["replacing_pitcher_clause_rows"]
    assert rp["field_names_lineup_occupant"] > 0, "the double-switch fact is published"
    assert "double switch" in rp["derivation"]


def test_defensive_switch_rows_are_all_classified(art):
    """525 + 1,874 + 2,641 = 5,040 on 2025, no row left unclassified."""
    sw = art["switch_classification"]
    assert sw["unclassified"] == 0
    assert sw["dh_retained"] + sw["position_move"] + sw["stayed_in_field"] + sw.get("substitution_text", 0) == sw["n"]
    ev_path = CORPUS / "events" / "2025" / "events-2025.parquet"
    if not ev_path.exists():
        pytest.skip("2025 events not on this machine")
    import pandas as pd
    ev = pd.read_parquet(ev_path, columns=["event_type", "description"])
    c = MD.classify_switches(ev)
    assert (c["dh_retained"], c["position_move"], c["stayed_in_field"], c["n"]) == (525, 1874, 2641, 5040)
    assert c["unclassified"] == 0


def test_a_between_innings_change_reads_the_next_half_first_play(rows):
    hook = _one(rows, "pitching_change", kind="starter_hook")
    assert (hook["half"], hook["inning"], hook["outs"], hook["base"]) == ("top", 2, 0, 0)
    assert hook["ab"] == 6


def test_starter_hook_is_the_first_change_for_that_side(rows):
    pcs = sorted((r for r in rows if r["family"] == "pitching_change"), key=lambda r: r["ab"])
    assert [r["kind"] for r in pcs] == ["starter_hook", "reliever_change"]
    assert "opener" not in pcs[0]["flags"]


def test_pinch_hitter_credited_to_prior_is_flagged_not_dropped(rows):
    ph = _one(rows, "pinch_hit")
    assert ph["in_id"] == 250 and ph["out_id"] == 203
    assert "credited_to_prior" in ph["flags"]
    assert ph["slot"] == 3
    assert ph["win_len"] == 1


def test_pinch_runner_window_ends_with_the_half_inning(rows):
    pr = _one(rows, "pinch_run")
    assert pr["ab"] == 4 and pr["win_len"] == 2, "entry to the half's last play"
    assert pr["in_id"] == 199 and pr["out_id"] == 101
    assert "advanced" in pr["flags"] and "scored" not in pr["flags"] and "out_on_bases" not in pr["flags"]
    assert pr["kind"] == "on_1B"


def test_intentional_walk_window_covers_the_on_deck_plate_appearance(rows):
    ibb = _one(rows, "intentional_walk")
    assert ibb["win_len"] == 2 and ibb["ab"] == 7
    assert ibb["ondeck_id"] == 203
    assert ibb["mwpa"] == pytest.approx(0.03)
    assert ibb["walk_only_mwpa"] == pytest.approx(0.01)
    assert ibb["club"] == "NYY"
    assert "forces_run" not in ibb["flags"]


def test_defensive_sub_windows_are_stored_and_never_summed(rows, art):
    ds = _one(rows, "defensive_sub")
    assert ds["win_len"] == 3, "to the end of the game"
    assert ds["mwpa"] is not None
    assert "defensive_sub" not in MD.SUMMED_FAMILIES
    import pandas as pd
    led = pd.DataFrame([{k: r.get(k) for k in ("id", "date", "game_pk", "ab", "season", "club", "family",
                                              "kind", "li", "mwpa", "pitch_count", "inherited",
                                              "inherited_scored", "first_pa_mwpa")} for r in rows])
    crow = MD.club_rows(led, TMAP)[0]
    assert "mwpa_defensive_sub" not in crow
    assert crow["n_defensive_sub"] == 1
    for r in art["clubs"]["rows"]:
        assert "mwpa_defensive_sub" not in r
    assert art["families"]["defensive_sub"]["summed"] is False
    assert "defensive_sub" in art["clubs"]["not_summed"]


def test_bunt_attempts_come_from_pitch_codes_and_results(rows, art):
    sac = _one(rows, "bunt", kind="sac_bunt")
    assert sac["ab"] == 4 and sac["dv_cell"] == pytest.approx(-0.02)
    assert "sign_proxy" in sac["flags"]
    ab_ = _one(rows, "bunt", kind="bunt_attempt_abandoned")
    assert ab_["ab"] == 5 and "attempt_codes" in ab_["flags"]
    assert set(art["families"]["bunt"]["kinds"]) >= {"sac_bunt", "bunt_out", "bunt_attempt_abandoned"}
    assert MD.BUNT_CODES == ("L", "M", "O")


# --------------------------------------------------------------------------
# 1. realized value, not skill; 2. the agent
# --------------------------------------------------------------------------

def test_every_family_publishes_its_counterfactual_sentence(art):
    for f in MD.FAMILIES:
        assert f in art["families"], f
        s = art["families"][f]["counterfactual_sentence"]
        # the counted-only families say so in a short sentence; the valued ones
        # name what would be needed to price the alternative
        assert s and len(s) > (15 if f in MD.COUNTED_ONLY else 40), f
        assert s == MD.COUNTERFACTUAL[f]


def test_the_realized_sentence_says_not_skill_verbatim(art, board):
    s = MD.REALIZED_SENTENCE
    assert s.startswith("Realized value, not skill.")
    assert "not a measure of how well he chose" in s
    assert art["realized_sentence"] == s
    assert board["decisions"]["realized_sentence"] == s
    assert board["clubs"]["columns_are_realized_not_skill"] == s
    assert board["decisions"]["plus_metric"] is False
    assert board["decisions"]["no_cross_family_total"] is True


def test_the_steal_row_is_valued_on_the_steal_itself(shard, art):
    """Audit MH-01. The steal happens between two plays; the feed's plate-appearance
    row starts after it, so that row's endpoint difference is the batter's result with
    the steal left out. The steal's realized value is realized_delta (DV + ER), it has
    no play window and no DVS, and the payload no longer calls the feed figure a second
    estimator of the same quantity."""
    steals = [r for r in shard["rows"] if r["family"] == "steal"]
    assert steals, "no steal rows in the shard"
    for r in steals:
        assert "dv" in r and "er" in r and "realized_delta" in r and "mwpa" in r
        assert abs(r["dv"] + r["er"] - r["realized_delta"]) < 1e-3
        assert abs(r["mwpa"] - r["realized_delta"]) < 6e-5, r
        assert r.get("dvs") is None and not r.get("window") and r["win_len"] == 0
    bunts = [r for r in shard["rows"] if r["family"] == "bunt"]
    assert any("dv_cell" in r for r in bunts), "no bunt row carries the league DV cell"
    assert all("mwpa" in r for r in bunts)
    fam = art["families"]["steal"]
    assert "two_realized_estimators" not in fam
    assert "realized_delta" in fam["realized_source"]["mwpa"]
    assert "plate appearance" not in fam["window_rule"].split(";")[0]
    assert "two estimators" not in fam["counterfactual_sentence"]
    assert "steal" not in art["single_pa_caveat"].split(". ")[0]


def test_a_steal_is_priced_from_its_attempt_not_from_the_feed_row(ctx):
    """Synthetic: the feed row at ab 4 moves +1 point for the home club, the attempt's
    realized change is -0.05. The row must carry -0.05, the attempt's figure."""
    import pandas as pd
    att = pd.DataFrame([{"season": 2099, "game_pk": 1, "at_bat_index": 4, "target": "2B",
                         "success": False, "dv": 0.004, "er": -0.054,
                         "realized_delta": -0.05, "breakeven_p": 0.7}])
    rows = MD.finalise(ctx, MD.detect_steals(ctx, att), NAMES, {1: "2099-04-01"})
    assert len(rows) == 1
    r = rows[0]
    assert r["mwpa"] == pytest.approx(-0.05)
    assert r["mwpa"] != pytest.approx(ctx.mwpa(ctx.pos[(1, 4)], ctx.pos[(1, 4)], True))
    assert r["win_len"] == 0 and r.get("window") in (None, [])


def test_steal_mwpa_tracks_the_steal_on_every_shard(art):
    """Over every served shard: the steal column agrees with the steal's own change
    (it was Pearson -0.011, sign agreement 0.49, with successes averaging a loss)."""
    import mgmt_shards
    idx = (art.get("shards") or {}).get("index") or []
    if not idx:
        pytest.skip("no shards on this build")
    mw, rd, ok = [], [], []
    for e in idx:
        p = SHARDS / f"{e['season']}-{e['club']}.json"
        if not p.exists():
            continue
        for r in mgmt_shards.expand(json.loads(p.read_text(encoding="utf-8"))):
            if r["family"] == "steal" and r.get("mwpa") is not None:
                mw.append(r["mwpa"])
                rd.append(r["realized_delta"])
                ok.append(bool(r.get("success")))
    assert len(mw) > 1000
    n = len(mw)
    mx, my = sum(mw) / n, sum(rd) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(mw, rd))
    sxx = sum((a - mx) ** 2 for a in mw)
    syy = sum((b - my) ** 2 for b in rd)
    assert sxy / math.sqrt(sxx * syy) > 0.99
    succ = [a for a, s in zip(mw, ok) if s]
    caught = [a for a, s in zip(mw, ok) if not s]
    assert sum(succ) / len(succ) > 0 and sum(caught) / len(caught) < 0


def test_pre_play_score_and_notna_bases_are_used(ctx):
    """bool(NaN) is True. A row with first base EMPTY (NaN) and second occupied reads
    base code 2, never 3 or 7, and the score is the pre-play one."""
    import pandas as pd
    pl = _plays()
    pl.loc[pl["at_bat_index"] == 5, ["home_score", "runs_scored_on_play"]] = [1, 1]
    c = MD.SeasonCtx(2099, pl, _events(), _pitches(), TMAP)
    i = c.pos[(1, 5)]
    st = c.state(i)
    assert st["base"] == 2
    assert st["sd_home"] == 0, "post-play score 1-0 minus the run scored on the play"
    assert MD.base_code(NAN, 5.0, NAN) == 2
    assert MD.base_code(1.0, 2.0, 3.0) == 7
    assert MD.base_code(None, NAN, NAN) == 0


def test_li_null_on_leadoff_is_carried_as_null(rows, art):
    mv = _one(rows, "mound_visit")
    assert mv["ab"] == 0
    assert mv.get("li") is None, "null LI is carried as null, never 0"
    assert "null on the leadoff" in art["units"]["li"]


def test_floors_are_published_and_applied(art):
    assert art["floors"] == MD.FLOORS
    assert art["games_floor"] == MD.GAMES_FLOOR
    for r in art["clubs"]["rows"]:
        for f in MD.SUMMED_FAMILIES:
            if r[f"n_{f}"] < MD.FLOORS[f]:
                assert r[f"mwpa_{f}"] is None, (r["club"], r["season"], f)
            if r[f"mwpa_{f}"] is not None:
                assert r[f"n_{f}"] >= MD.FLOORS[f], (r["club"], r["season"], f)


def test_no_plus_sign_and_no_tier_on_any_realized_column(art):
    js = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")
    assert "EephusTiers" not in js
    for r in art["clubs"]["rows"]:
        for k in r:
            assert "plus" not in k and "tier" not in k, k
    assert art["plus_metric"] is False
    assert art["clubs"]["plus_metric"] is False if "plus_metric" in art["clubs"] else True


def test_the_agent_sentence_travels_until_managers_land(art, board):
    assert art["agent_sentence"] == MD.AGENT_SENTENCE
    assert "club-season until the manager ledger lands" in MD.AGENT_SENTENCE
    assert board["clubs"]["agent_sentence"] == MD.AGENT_SENTENCE
    if not board["managers"]["live"]:
        assert board["managers"]["agent_sentence"] == MD.AGENT_SENTENCE
    for r in art["clubs"]["rows"]:
        assert r["agent"] == "club-season"


def test_the_baseline_artifact_is_dated_and_the_shard_family_is_named(art):
    """The catalog pins data/management_baseline.json and the mgmt_decisions/*.json
    shard family on this file; both carry a stamp of their own."""
    if not BASELINE.exists():
        pytest.skip("run python mgmt_decisions.py")
    b = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert b["generated_at"] and b["produced_by"] == "mgmt_baseline.py"
    assert art["shards"]["path_template"] == "/data/mgmt_decisions/{season}-{club}.json"
    assert art["baseline_artifact"] == "data/management_baseline.json"


# --------------------------------------------------------------------------
# the compacted shard (schema 2, 2026-09-23): 157 MB of dict rows became 41.5 MB
# --------------------------------------------------------------------------

def test_shard_schema_2_round_trips_the_synthetic_rows(rows):
    """compact_season then expand reproduces the schema-1 rows exactly, in the shard
    order (date, game_pk, ab, idx), for the home club of the synthetic game; the
    rows carry ids, codes and coded windows only, and the header the legends."""
    import mgmt_shards as S
    club = rows[0]["club"]
    mine = [r for r in rows if r["club"] == club]
    payload = S.compact_season(mine, 2099, club, "2099-04-02T00:00:00+00:00")
    assert payload["schema_version"] == 2 and payload["n"] == len(mine) and payload["club"] == club
    back = S.expand(json.loads(json.dumps(payload)))
    assert back == [S.compact_row(r) for r in sorted(mine, key=S._sort_key)]
    for k in ("games", "names", "events", "kinds", "flags", "legend", "schema_note", "generated_at"):
        assert k in payload, k
    pc = payload["families"]["pitching_change"]
    assert pc["keys"][:9] == ["game_pk", "ab", "idx", "half", "inning", "outs", "base", "score_diff", "li"]
    for k in ("date", "opp", "home", "in_name", "out_name", "win_len", "family", "id"):
        assert k not in pc["keys"], k
    # the fixture breaks the chain on every pair of plays, so every coded play
    # carries wp_before; a chained play would carry [event, wp_after] alone
    wi = pc["keys"].index("window")
    for arr in pc["rows"]:
        assert all(len(p) == 3 for p in arr[wi]), arr[wi]
    assert payload["games"] == {"1": ["2099-04-01", "BOS" if club == "NYY" else "NYY", 1 if club == "NYY" else 0]}
    assert payload["names"]["110"] == "Reliever B"


def test_the_shard_header_carries_schema_2_the_legends_n_and_a_stamp(shard_payload, art):
    d = shard_payload
    assert d["schema_version"] == 2 and d["produced_by"] == "mgmt_shards.py" and d["generated_at"]
    assert d["n"] == sum(len(b["rows"]) for b in d["families"].values())
    for k in ("games", "names", "events", "kinds", "flags", "legend", "schema_note"):
        assert k in d, k
    assert d["legend"]["half"] == ["top", "bottom"]
    for f, b in d["families"].items():
        assert f in MD.FAMILIES, f
        assert b["keys"][:3] == ["game_pk", "ab", "idx"], f
        for k in ("date", "opp", "home", "win_len", "in_name", "out_name", "pitcher_name", "family", "id"):
            assert k not in b["keys"], (f, k)
    assert art["shards"]["schema_note"].startswith("schema 2")
    e = [x for x in art["shards"]["index"] if x["season"] == d["season"] and x["club"] == d["club"]][0]
    assert e["n"] == d["n"]


def test_realized_pitching_change_mwpa_recomputed_from_the_compacted_shard_matches_the_board(shard, art, board):
    """Each pitching change's mWPA is the endpoint difference of its decoded window
    (sign to the deciding club, never a row sum), the plays are consecutive plate
    appearances, and the club-season's per-family sum is the board's
    mwpa_pitching_change column: the compaction lost no value."""
    pc_all = [r for r in shard["rows"] if r["family"] == "pitching_change"]
    valued = [r for r in pc_all if r.get("mwpa") is not None]
    assert valued
    total = 0.0
    for r in valued:
        w = r["window"]
        s = 1 if r["home"] else -1
        assert r["win_len"] == len(w) > 0
        assert round(s * (w[-1][3] - w[0][2]) / 100, 4) == r["mwpa"], r
        assert [p[0] for p in w] == [w[0][0] + k for k in range(len(w))]
        assert r["first_pa_mwpa"] == round(s * (w[0][3] - w[0][2]) / 100, 4)
        total += r["mwpa"]
    for src in (art, board):
        club = [c for c in src["clubs"]["rows"] if c["club"] == shard["club"] and c["season"] == shard["season"]][0]
        assert club["n_pitching_change"] == len(pc_all)
        if len(valued) >= MD.FLOORS["pitching_change"]:
            assert club["mwpa_pitching_change"] == pytest.approx(total, abs=5.1e-4)
        else:
            assert club["mwpa_pitching_change"] is None


def test_the_shard_set_fits_the_tracking_budget(art):
    """157.07 MB of schema-1 shards became 41.50 MB on 2026-09-23 (240 shards, 298,701
    rows, every row equal after the round trip); the set stays well under the 60 MB
    line set for tracking it in git."""
    idx = art["shards"]["index"]
    total = sum(e["bytes"] for e in idx)
    assert total < 60_000_000, total
    assert total / len(idx) < 300_000
