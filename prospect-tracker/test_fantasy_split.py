# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the /fantasy/ split into /dynasty/, /redraft/ and /dfs/.

Three things are worth pinning after a split like this, and they are the three
ways a split silently breaks a site:

  1. THE NEW EXPORTER RUNS OFFLINE. dfs_export builds a VALID payload with no
     network, no slate, and no corpus, carrying its own `empty_reason`. A daily
     job that raises on an off day is a daily job that stops running.

  2. THE CLIENTS STAYED HONEST. Source guards over the three new JS files: each
     fetches its own sidecar and only that; none of them carries betting copy
     (fantasy pages take no gambling disclaimer, and they must not start
     looking like they should); none carries an em-dash; and none computes an
     eFV grade locally, which is the single-basis rule that /fantasy/ once
     broke by serving two different eFV numbers on one page.

  3. THE NUMBERS DID NOT MOVE. assets/redraft.js carries a port of the scoring
     code that used to live in assets/fantasy.js. Both files are driven in a
     real JS engine over ONE fixture payload, and their rendered board scores
     are compared in all four league formats. A drift in the port fails here
     rather than quietly re-ranking somebody's league.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
JS_FILES = {
    "dynasty": ASSETS / "dynasty.js",
    "redraft": ASSETS / "redraft.js",
    "dfs": ASSETS / "dfs.js",
}
SIDECAR = {"dynasty": "/data/fantasy.json", "redraft": "/data/fantasy.json",
           "dfs": "/data/dfs.json"}
# The shared player-card overlay. It is not a board CLIENT (it fetches no
# corpus and owns no payload; the host hands it one), so it stays out of
# JS_FILES and its own contract is pinned separately. It IS held to the same
# copy and single-eFV-basis rules, which is what GUARDED is for.
CARD_JS = ASSETS / "fantasy-card.js"
# The /fantasy/ coordinator. Also not a board CLIENT: it fetches on behalf of
# the clients, renders no board and owns no column. It carries reader-facing
# copy and lives on a fantasy surface, so it is held to the same copy rules.
HUB_JS = ASSETS / "fantasy-hub.js"
GUARDED = dict(JS_FILES, card=CARD_JS, hub=HUB_JS)


def _src(name: str) -> str:
    return GUARDED[name].read_text(encoding="utf-8")


def _code(name: str) -> str:
    """Source with whole-line comments removed. The guards below are about what
    the CODE does; a comment naming the server-side function it must not
    duplicate is the documentation working, not a violation."""
    return "\n".join(ln for ln in _src(name).splitlines()
                     if not ln.lstrip().startswith("//"))


# ===========================================================================
# 1. dfs_export offline
# ===========================================================================
def _fantasy_fixture() -> dict:
    """A minimal fantasy.json: two clubs, four bats, two arms, one scoring
    fraction. Everything dfs_export reads and nothing it does not."""
    def hit(mid, name, team, pa, hr, sb):
        return {"mlbam": mid, "name": name, "side": "hit", "pos": "H", "team": team,
                "elig": ["OF"], "skill": {"hem_plus": 120, "luck_gap": 3.0},
                "fpts_fgp": 200.0,
                "ros": {"pa": pa, "ab": pa * 0.9, "h": pa * 0.25, "single": pa * 0.16,
                        "double": pa * 0.05, "triple": pa * 0.005, "hr": hr,
                        "bb": pa * 0.09, "hbp": pa * 0.01, "so": pa * 0.2,
                        "sb": sb, "cs": sb * 0.26, "r": pa * 0.13, "rbi": pa * 0.12,
                        "avg": 0.278, "obp": 0.352, "slg": 0.470}}

    def sp(mid, name, team, ip, gs, k):
        return {"mlbam": mid, "name": name, "side": "pit", "pos": "SP", "team": team,
                "elig": ["P"], "skill": {"sem_plus": 118, "luck": 0.004},
                "fpts_fgp": 150.0,
                "ros": {"role": "SP", "ip": ip, "bf": ip * 4.2, "k": k, "bb": ip * 0.3,
                        "hr": ip * 0.12, "hbp": ip * 0.03, "h": ip * 0.85,
                        "er": ip * 0.38, "era": 3.42, "whip": 1.15, "gs": gs,
                        "qs": gs * 0.5, "w": gs * 0.35, "l": gs * 0.25}}
    return {
        "season": 2026, "season_fraction": 0.70, "generated_at": "2026-08-05T00:00:00Z",
        "players": [
            hit(1, "Alpha Bat", "BOS", 260, 12, 8),
            hit(2, "Bravo Bat", "BOS", 120, 4, 1),
            hit(3, "Charlie Bat", "NYY", 250, 14, 3),
            hit(4, "Delta Bat", "NYY", 60, 1, 0),
            sp(10, "Echo Arm", "BOS", 55, 10, 60),
            sp(11, "Foxtrot Arm", "NYY", 50, 9, 52),
        ],
    }


def _games_fixture(day="2026-08-05", game_pk=1):
    return [{
        "game_pk": game_pk, "date": day, "datetime": day + "T23:05:00Z",
        "status": "Preview", "double_header": False,
        "venue": {"id": 3313, "name": "Yankee Stadium"},
        "home": {"team_id": 147, "team": "New York Yankees", "org": "NYY",
                 "probable": {"mlbam": 11, "name": "Foxtrot Arm"}},
        "away": {"team_id": 111, "team": "Boston Red Sox", "org": "BOS",
                 "probable": {"mlbam": 10, "name": "Echo Arm"}},
    }]


def test_dfs_export_empty_slate_is_a_valid_payload():
    """An off day is the common case for eight months of the year. It must
    produce a payload the page can render, not an exception and not a blank."""
    import dfs_export as dx
    p = dx.build_payload(day="2026-01-15", fantasy=_fantasy_fixture(), games=[])
    assert p["n_games"] == 0 and p["n_players"] == 0
    assert p["games"] == [] and p["players"] == []
    assert "No MLB games scheduled for 2026-01-15" in p["empty_reason"]
    # The page still needs its furniture on an empty day: scoring tables, the
    # roster templates the optimizer runs on, and the salary provenance block.
    assert p["scoring"]["dk"]["hitter"]["hr"] > 0
    assert p["scoring_catalog"] and p["roster_templates"]
    assert p["salaries"]["source"] == "user"
    json.dumps(p)      # serializable, which is the whole job


def test_dfs_export_without_a_corpus_says_so():
    import dfs_export as dx
    p = dx.build_payload(day="2026-08-05", fantasy={}, games=None)
    assert p["n_players"] == 0
    assert "projection corpus" in p["empty_reason"]


def test_dfs_export_offline_refresh_writes_and_returns_zero(tmp_path):
    """The daily wiring calls refresh(). With a stubbed empty schedule it must
    write a payload and return 0 rather than raise."""
    import dfs_export as dx
    out = tmp_path / "dfs.json"
    n = dx.refresh(log=lambda *_a, **_k: None, day="2026-01-15", games=[], out_path=out)
    assert n == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["empty_reason"] and written["players"] == []


def test_dfs_export_prices_a_stubbed_slate():
    import dfs_export as dx
    p = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(),
                         games=_games_fixture(), positions={}, park={},
                         teams_ctx={"BOS": {"offense_plus": 108, "bullpen_plus": 96},
                                    "NYY": {"offense_plus": 104, "bullpen_plus": 101}})
    assert p["empty_reason"] is None
    assert p["n_games"] == 1
    ids = {(r["mlbam"], r["side"]) for r in p["players"]}
    # Both announced starters and all four bats are priced.
    assert (10, "pit") in ids and (11, "pit") in ids
    assert {(1, "hit"), (2, "hit"), (3, "hit"), (4, "hit")} <= ids
    for r in p["players"]:
        assert r["pts"]["dk"] is not None and r["pts"]["fd"] is not None
        assert r["elig"], r
        if r["side"] == "hit":
            assert 0 < r["start_rate"] <= 1.0
            # The line is conditional on starting, so a part-time bat still
            # shows a full game's plate appearances.
            assert r["line"]["pa"] > 3.0, r


def test_dfs_hitter_line_is_conditional_on_starting():
    """Two bats short of an everyday workload over the same remaining schedule
    get the SAME per-start plate appearances and different start rates. That
    split is the whole point: the optimizer prices the line, the reader reads
    the rate."""
    import dfs_export as dx
    most, r_most = dx._hitter_line({"pa": 180.0, "h": 45.0, "ab": 162.0}, 49, 1.0)
    part, r_part = dx._hitter_line({"pa": 120.0, "h": 30.0, "ab": 108.0}, 49, 1.0)
    assert r_most > r_part
    assert abs(most["pa"] - part["pa"]) < 0.001
    assert abs(part["pa"] - dx._PA_PER_START) < 0.001


def test_dfs_everyday_bat_clamps_at_a_full_start():
    """A bat projected past the league per-start anchor is not given a start
    rate above 1.0. He gets rate 1.0 and the longer game he actually plays."""
    import dfs_export as dx
    line, rate = dx._hitter_line({"pa": 260.0, "h": 65.0, "ab": 234.0}, 49, 1.0)
    assert rate == 1.0
    assert line["pa"] > dx._PA_PER_START


def test_dfs_matchup_multiplier_moves_the_right_way():
    """A tougher opposing pitching index lowers a hitter's projection and a
    better opposing offense raises a pitcher's runs allowed."""
    import dfs_export as dx
    easy, _ = dx._hitter_line({"pa": 200.0, "hr": 10.0, "ab": 180.0}, 49, 1.15)
    hard, _ = dx._hitter_line({"pa": 200.0, "hr": 10.0, "ab": 180.0}, 49, 0.85)
    assert easy["hr"] > hard["hr"]
    assert easy["pa"] == hard["pa"]      # playing time is not a matchup term
    good = dx._pitcher_line({"gs": 10, "ip": 55.0, "k": 60.0, "er": 20.0, "h": 47.0}, 0.9)
    bad = dx._pitcher_line({"gs": 10, "ip": 55.0, "k": 60.0, "er": 20.0, "h": 47.0}, 1.1)
    assert bad["er"] > good["er"] and bad["h"] > good["h"]
    assert bad["k"] == good["k"]         # a weak lineup does not hand out strikeouts


def test_dfs_scoring_tables_are_published_and_self_consistent():
    """The client re-scores from the payload's own tables, so a weight that is
    not in the payload is a weight nobody can audit."""
    import dfs_export as dx
    t = dx.scoring_tables()
    assert set(t) == {"dk", "fd"}
    line = {"single": 1.0, "double": 1.0, "hr": 1.0, "rbi": 2.0, "r": 1.0, "bb": 1.0}
    manual = sum(line[k] * dx.DK_HITTER[k] for k in line)
    assert abs(dx.score_line(line, "dk", "hit") - manual) < 1e-6
    pit = {"ip": 6.0, "k": 7.0, "er": 2.0, "h": 5.0, "bb": 2.0, "w": 1.0}
    manual_p = sum(pit[k] * dx.DK_PITCHER[k] for k in pit)
    assert abs(dx.score_line(pit, "dk", "pit") - manual_p) < 1e-6


def test_dfs_doubleheader_does_not_duplicate_a_player():
    """Two games for one club on one day must not put the same bat in a lineup
    twice. The better matchup wins the row and the row records both games."""
    import dfs_export as dx
    games = _games_fixture(game_pk=1) + _games_fixture(game_pk=2)
    p = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(), games=games,
                         positions={}, park={}, teams_ctx={})
    keys = [(r["mlbam"], r["side"]) for r in p["players"]]
    assert len(keys) == len(set(keys)), keys
    assert all(r["games_today"] == 2 for r in p["players"])


def test_dfs_position_eligibility_has_one_definition():
    """dfs_export must not carry a second copy of the eligibility rule. One
    definition lives in fantasy_export; this module reads the answer."""
    import dfs_export as dx
    import fantasy_export as fe
    assert dx.positions_by_mlbam.__doc__
    src = (ROOT / "dfs_export.py").read_text(encoding="utf-8")
    assert "fe._elig_positions()" in src
    assert dx._MIN_ELIG_GAMES == fe._ELIG_MIN_GAMES


# ---------------------------------------------------------------------------
# 1b. The three DFS context joins (2026-08-07): park, Vegas, lineups.
# ---------------------------------------------------------------------------
def _park_index():
    """Yankee Stadium keyed the way _park_factors builds it, plus a park the
    Savant table does not cover."""
    return {3313: {"pf": 1.06, "source": "savant_mlb", "org": "NYY"},
            2529: {"pf": 1.0, "source": "no_factor_for_park", "org": "ATH"}}


def test_dfs_park_leg_labels_every_kind_of_miss():
    """Neutral is the answer for four different reasons and they are not the
    same claim. An unlabelled 1.00 makes a measured average park, a neutral
    site, an uncovered park and a failed venue map read identically."""
    import dfs_export as dx
    park = _park_index()
    assert dx._park_basis(park) == "savant_mlb"
    assert dx._park_leg(park, 3313, "savant_mlb") == (1.06, "savant_mlb")
    assert dx._park_leg(park, 2529, "savant_mlb") == (1.0, "no_factor_for_park")
    # A venue in a map that HAS the home parks is a neutral-site game...
    assert dx._park_leg(park, 999, "savant_mlb") == (1.0, "neutral_site")
    # ...and the same absence with no map is our outage, not a fact about MLB.
    assert dx._park_leg({}, 999, "venue_map_unavailable") == (1.0, "none")
    assert dx._park_basis({}) == "venue_map_unavailable"
    # The bare {venue: float} shape labs and tests inject still resolves.
    assert dx._park_leg({7: 0.95}, 7, "savant_mlb") == (0.95, "milb_park_factors")


def test_dfs_park_factor_out_of_range_is_clamped_and_said_out_loud():
    """A factor written as 108 rather than 1.08 would multiply a club's whole
    slate. Clamping it silently would then look exactly like a measured 1.45."""
    import dfs_export as dx
    pf, src = dx._park_leg({1: {"pf": 108.0, "source": "savant_mlb"}}, 1, "savant_mlb")
    assert pf == dx._PARK_PF_CLAMP[1]
    assert src.endswith("_out_of_range")


def test_dfs_park_factors_join_org_keyed_savant_through_the_venue_map():
    """fa_meta keys park factors by CLUB and a game is played at a VENUE. Only
    a club's OWN park may take its factor."""
    import dfs_export as dx
    idx = dx._park_factors(2026, raw={},
                           meta={"park_factors": {"NYY": {"runs": 106},
                                                  "BOS": {"runs": 94}}},
                           home_venues={3313: "NYY", 3: "BOS", 2529: "ATH"})
    assert idx[3313] == {"pf": 1.06, "source": "savant_mlb", "org": "NYY"}
    assert idx[3]["pf"] == 0.94
    # ATH is in the venue map and NOT in the Savant table. That is a covered
    # park with no factor, which is not the same as an uncovered venue.
    assert idx[2529] == {"pf": 1.0, "source": "no_factor_for_park", "org": "ATH"}
    # With no venue map at all the MLB legs must NOT fall back to the org.
    assert dx._park_factors(2026, raw={}, meta={"park_factors": {"NYY": {"runs": 106}}},
                            home_venues={}) == {}


def test_dfs_park_factor_multiplies_outside_the_matchup_clamp():
    """The clamps were sized against the opponent indexes while every park leg
    was 1.00. Folding the park inside them made the guard rail the operative
    term for exactly the parks that carry the most park signal."""
    import dfs_export as dx
    park = {3313: {"pf": 0.83, "source": "savant_mlb"}}
    p = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(),
                         games=_games_fixture(), positions={}, park=park,
                         teams_ctx={"BOS": {"offense_plus": 108, "bullpen_plus": 96},
                                    "NYY": {"offense_plus": 104, "bullpen_plus": 101}})
    side = p["games"][0]["home"]
    assert side["hit_mult"] == round(side["hit_matchup_mult"] * 0.83, 3)
    assert side["hit_mult"] < dx._HIT_MULT_CLAMP[0]     # the park is not clipped
    assert dx._HIT_MULT_CLAMP[0] <= side["hit_matchup_mult"] <= dx._HIT_MULT_CLAMP[1]


def test_dfs_park_composition_never_moved_a_served_number():
    """The clamp moved outside the park multiplication on 2026-08-07. Clamping
    before or after multiplying by exactly 1.0 is the same arithmetic, and 1.0
    is what every MLB park leg was until that day, so no payload ever served
    changes. This pins that equivalence rather than asserting it in a comment."""
    import dfs_export as dx
    for opp_pitch in (70.0, 85.0, 100.0, 118.0, 140.0):
        assert (dx._clamp(100.0 / opp_pitch, *dx._HIT_MULT_CLAMP) * 1.0
                == dx._clamp((100.0 / opp_pitch) * 1.0, *dx._HIT_MULT_CLAMP))


def test_dfs_est_list_drops_the_park_when_no_park_applied():
    """`est` is the row's list of display-layer legs that MOVED the line.
    Carrying "park" on a row whose park leg did nothing is the honesty list
    telling a small lie about itself."""
    import dfs_export as dx
    assert "park" in dx._est(["matchup"], "savant_mlb")
    assert "park" in dx._est(["matchup"], "milb_park_factors")
    for miss in ("none", "neutral_site", "no_factor_for_park"):
        assert "park" not in dx._est(["matchup"], miss), miss


def test_dfs_lineup_leg_has_three_states_and_pts_never_moves():
    """Posted-and-on-it, posted-and-not-on-it, and not posted. The third is the
    common case at build time and must leave the projection untouched."""
    import dfs_export as dx
    assert dx._lineup_leg(7, [], 0.62) == (None, None, 0.62, 0.62)
    assert dx._lineup_leg(7, [3, 7, 9], 0.62) == (2, "confirmed", 1.0, 0.62)
    assert dx._lineup_leg(7, [3, 9, 11], 0.62) == (None, "not_in_lineup", 0.0, 0.62)


def test_dfs_confirmed_lineup_replaces_the_start_rate_and_leaves_est():
    """A posted card is an OBSERVATION. It sets the start rate to a fact, keeps
    the projection it replaced beside it, and stops calling the number an
    estimate. `pts` is untouched: the line is already conditional on starting."""
    import dfs_export as dx
    games = _games_fixture()
    base = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(), games=games,
                            positions={}, park={}, teams_ctx={}, lineups={})
    # Bat 3 leads off for NYY; bat 4 is on the same club and not on the card.
    conf = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(), games=games,
                            positions={}, park={}, teams_ctx={},
                            lineups={1: {"home": [3], "away": []}})

    def row(p, mid):
        return [r for r in p["players"] if r["mlbam"] == mid and r["side"] == "hit"][0]

    b3, b4 = row(conf, 3), row(conf, 4)
    assert b3["lineup_spot"] == 1 and b3["lineup_status"] == "confirmed"
    assert b3["start_rate"] == 1.0 and b3["start_rate_source"] == "confirmed_lineup"
    assert b3["start_rate_projected"] == row(base, 3)["start_rate"]
    assert "start_rate" not in b3["est"]
    assert b4["lineup_status"] == "not_in_lineup" and b4["start_rate"] == 0.0
    assert "start_rate" not in b4["est"]
    # The BOS side posted nothing, so nothing about its bats changed. The
    # lineup keys are OMITTED rather than written null: an explicit null on
    # every row of a 524-row slate cost 84KB of a lazily-booted payload, and
    # `games[].lineups_posted` already carries whether the club filed at all,
    # so "no card yet" and "posted, not on it" stay distinguishable.
    b1 = row(conf, 1)
    assert "lineup_status" not in b1 and "start_rate_source" not in b1
    assert "start_rate" in b1["est"]
    assert b1["start_rate"] == row(base, 1)["start_rate"]
    # THE POINT TOTAL DOES NOT MOVE. Confirming a start changes the odds of the
    # start, not one number inside the line it is conditional on.
    for mid in (1, 2, 3, 4):
        assert row(conf, mid)["pts"] == row(base, mid)["pts"], mid
    g = conf["games"][0]
    assert g["lineups_posted"] == {"home": True, "away": False}
    assert g["home"]["lineup_posted"] is True and g["away"]["lineup_posted"] is False


def test_dfs_implied_team_totals_split_a_market_total():
    """The two implied team totals must sum to the posted total and lean the
    way the moneyline does. The split reuses the betting module's own run
    distribution, so no new distribution enters the site."""
    import dfs_export as dx
    home, away, edged = dx._split_total(9.0, 0.75, 0.4875)
    assert not edged
    assert abs((home + away) - 9.0) < 1e-6
    assert home > away
    even_h, even_a, _ = dx._split_total(9.0, 0.50, 0.4875)
    assert abs(even_h - even_a) < 0.10
    # Monotone: a bigger favourite gets more of the same total.
    big, _small, _ = dx._split_total(9.0, 0.85, 0.4875)
    assert big > home


def test_dfs_consensus_market_devigs_each_book_against_itself():
    """Taking the best home price from one book and the best away price from
    another and de-vigging the pair produces a market that does not exist. That
    fusion manufactured a 0.388 edge on /betting/ and is not repeated here."""
    import dfs_export as dx
    ev = {"books": {
        "a": {"h2h": {"home": -150, "away": 130}, "totals": {"over": {"price": -110, "point": 8.5},
                                                             "under": {"price": -110, "point": 8.5}}},
        "b": {"h2h": {"home": -160, "away": 140}, "totals": {"over": {"price": -105, "point": 9.0},
                                                             "under": {"price": -115, "point": 9.0}}},
        "c": {"h2h": {"home": -155, "away": 135}, "totals": {"over": {"price": -110, "point": 8.5},
                                                             "under": {"price": -110, "point": 8.5}}},
    }}
    mk = dx._consensus_market(ev)
    assert mk["n_books_ml"] == 3 and mk["n_books_total"] == 3
    assert mk["total"] == 8.5                       # the median line, not the longest
    # Every per-book fair probability is inside the raw pair it came from, so a
    # cross-book fusion (which would land outside every book) cannot pass here.
    assert 0.55 < mk["p_home"] < 0.65
    assert mk["total_range"] == [8.5, 9.0]
    # One book is a quote, not a market.
    assert dx._consensus_market({"books": {"a": ev["books"]["a"]}}) is None


def test_dfs_vegas_is_context_and_never_moves_a_price():
    """The market legs ride in the payload and in no multiplier. Pricing our
    own line off the moneyline would be a new model with no gate behind it."""
    import dfs_export as dx
    kw = dict(day="2026-08-05", fantasy=_fantasy_fixture(), games=_games_fixture(),
              positions={}, park={}, teams_ctx={})
    base = dx.build_payload(**kw)
    with_v = dx.build_payload(vegas={1: {"total": 9.0, "home_itt": 5.2, "away_itt": 3.8,
                                         "p_home": 0.66, "p_away": 0.34, "n_books": 7}},
                              **kw)
    assert [r["pts"] for r in with_v["players"]] == [r["pts"] for r in base["players"]]
    g = with_v["games"][0]
    assert g["vegas"]["total"] == 9.0
    assert g["home"]["vegas_itt"] == 5.2 and g["away"]["vegas_itt"] == 3.8
    hit_home = [r for r in with_v["players"]
                if r["side"] == "hit" and r["team"] == "NYY"][0]
    assert hit_home["ctx"]["vegas_itt"] == 5.2
    # A starter is graded on what the OTHER club scores, so his row carries the
    # opponent's number and not his own club's.
    pit_home = [r for r in with_v["players"]
                if r["side"] == "pit" and r["team"] == "NYY"][0]
    assert pit_home["ctx"]["vegas_opp_itt"] == 3.8
    assert with_v["integrity"]["vegas_games"] == 1


def test_dfs_vegas_refuses_a_snapshot_from_a_different_day():
    """Snapshot filenames are UTC and a slate is US-local, so a close capture
    can resolve to the wrong slate date. Clubs play three-game series, so the
    same two orgs are usually on BOTH cards and an org-only match would price
    today's board on yesterday's close. The first pitch is what separates them."""
    import dfs_export as dx
    day, games = "2026-08-05", _games_fixture(day="2026-08-05")

    # A real capture stamp, taken before the 23:05 first pitch. The in-game
    # refusal (2026-09-11) reads it; the placeholder "x" this fixture used to
    # carry would fall back to the build clock and refuse the game as started.
    def snapshot(commence, captured_at="2026-08-05T19:00:00Z"):
        return {"captured_at": captured_at, "kind": "close", "events": [{
            "id": "e", "commence_time": commence,
            "home_team": "New York Yankees", "away_team": "Boston Red Sox",
            "bookmakers": [
                {"key": bk, "title": bk, "markets": [
                    {"key": "h2h", "outcomes": [{"name": "New York Yankees", "price": -150},
                                                {"name": "Boston Red Sox", "price": 130}]},
                    {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 9.0},
                                                   {"name": "Under", "price": -110, "point": 9.0}]}]}
                for bk in ("a", "b", "c")]}]}

    import betting_ingest as bi
    real = bi.latest_snapshot
    try:
        # Same club pair, same slate date on the wrapper, first pitch a day off.
        bi.latest_snapshot = lambda **_k: snapshot("2026-08-04T23:05:00Z")
        idx, meta = dx._vegas_index(day, games)
        assert idx == {} and meta["n_rejected_on_time"] == 1
        assert "different day's board" in meta["reason"]
        # The real game, minutes apart, still joins.
        bi.latest_snapshot = lambda **_k: snapshot("2026-08-05T23:06:00Z")
        idx, meta = dx._vegas_index(day, games)
        assert set(idx) == {1} and meta["n_rejected_on_time"] == 0
        assert abs(idx[1]["home_itt"] + idx[1]["away_itt"] - 9.0) < 1e-6
    finally:
        bi.latest_snapshot = real


def test_dfs_injected_slate_stays_offline():
    """An injected slate is the caller's own, and going to the network behind
    its back for a lineup it did not ask for is how an offline path stops being
    offline. Both new joins are absent AND labelled on that path."""
    import dfs_export as dx
    p = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(),
                         games=_games_fixture(), positions={}, park={}, teams_ctx={})
    assert p["vegas_source"]["n_matched"] == 0
    assert "caller supplied the slate" in p["vegas_source"]["reason"]
    assert p["integrity"]["lineup_sides_posted"] == 0
    assert p["games"][0]["vegas"] is None
    # No market leg is written onto a row when no market resolved, and nothing
    # is lost by that: the payload states the absence once, with a reason.
    for r in p["players"]:
        assert "vegas_itt" not in r["ctx"] and "vegas_opp_itt" not in r["ctx"], r["name"]


def test_dfs_park_disclosure_does_not_outlive_what_it_describes():
    """The payload note and the client sentence both said every MLB park leg
    was neutral. The exporter now resolves them off the Savant index, and a
    disclosure that survives the thing it describes is worse than none."""
    import dfs_export as dx
    notes = " ".join(dx._NOTES).lower()
    assert "minor league ladder only" not in notes
    assert "every mlb park leg is neutral" not in notes
    assert "savant" in notes and "29 of 30" in notes
    # _code, not _src: the comment above the replacement QUOTES the sentence it
    # retired, which is the documentation working rather than a violation.
    js = _code("dfs")
    assert "no MLB park table on the site yet" not in js, (
        "assets/dfs.js still hard-codes the neutral-park sentence")
    # The client's park phrase is DERIVED from the payload's own counts.
    assert "park_sources" in js


def test_fantasy_export_elig_is_additive():
    """The shape addition must not disturb any existing reader: `pos` keeps its
    old value and `elig` is a new key."""
    import fantasy_export as fe
    players = [{"mlbam": 1, "side": "hit", "pos": "H"},
               {"mlbam": 10, "side": "pit", "pos": "SP"},
               {"mlbam": 11, "side": "pit", "pos": "RP"}]
    fe._enrich(players)
    assert players[0]["pos"] == "H"
    assert players[1]["elig"] == ["P"] and players[2]["elig"] == ["P"]
    assert "skill" in players[0] and "team" in players[0]


def _elig_from(raw: dict, season=None) -> dict:
    """_elig_positions reads from disk, so drive the rule through a temporary
    artifact rather than reaching into module internals."""
    import fantasy_export as fe
    import json as _json
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "fielding_innings.json").write_text(_json.dumps(raw), encoding="utf-8")
    old = fe.DATA_DIR
    try:
        fe.DATA_DIR = d
        return fe._elig_positions(season)
    finally:
        fe.DATA_DIR = old


def test_fantasy_export_elig_positions_rule():
    """The games floor with a modal-position fallback, exercised directly so a
    change to the rule is a deliberate act. The source is data/fielding_innings.json
    (owner decision 24, 2026-09-11): {seasons: {year: {mlbam: {POS: {g, gs, inn}}}}}."""
    raw = {"last_season": 2026, "seasons": {"2026": {
        "1": {"SS": {"g": 80, "gs": 78, "inn": 690.0}, "2B": {"g": 9, "gs": 5, "inn": 50.0},
              "LF": {"g": 2, "gs": 0, "inn": 3.0}},
        "2": {"DH": {"g": 3, "gs": 3, "inn": 0.0}},                    # modal, under floor
        "3": {"P": {"g": 30, "gs": 30, "inn": 170.0}},                 # pitcher: no hitter slot
    }}}
    out = _elig_from(raw)
    assert out[1] == ["SS", "2B"], out          # LF at 2 games is under the floor
    assert out[2] == ["UTIL"], out              # DH modal survives the floor
    assert 3 not in out                          # pitchers carry no fielding slot


def test_fantasy_elig_reads_the_newest_season_once_it_is_established():
    """Mutation: a closed season's positions bleeding into the slots of a
    player who already has a season's sample this year."""
    raw = {"seasons": {"2025": {"1": {"C": {"g": 120, "gs": 110, "inn": 950.0}}},
                       "2026": {"1": {"1B": {"g": 60, "gs": 55, "inn": 480.0}}}}}
    assert _elig_from(raw) == {1: ["1B"]}
    assert _elig_from(raw, 2025) == {1: ["C"]}
    assert _elig_from({"seasons": {}}) == {}


def test_fantasy_elig_carries_last_season_across_the_rollover():
    """refresh_current writes a new season's key the first night the feed has
    rows. Mutation: a newest-season-only read, which on opening day strips an
    everyday shortstop to whatever three games say, and a player with no games
    yet to nothing at all."""
    import fantasy_export as fe
    assert fe._ELIG_CARRY_GAMES == 20
    g = lambda n: {"g": n, "gs": n, "inn": 8.0 * n}             # noqa: E731
    raw = {"seasons": {
        "2026": {"1": {"SS": g(150), "2B": g(25), "3B": g(10)},
                 "2": {"C": g(100), "1B": g(5)},
                 "4": {"3B": g(100)},
                 "5": {"DH": g(15), "1B": g(8)}},
        "2027": {"1": {"SS": g(3)},
                 "3": {"LF": g(2)},
                 "4": {"2B": g(12), "SS": g(9)}}}}
    out = _elig_from(raw)
    assert out[1] == ["SS", "2B"], out       # 3 games now: last year's 20-game spots carry
    assert out[2] == ["C"], out              # no games yet: last year's 20-game spot
    assert out[3] == ["OF"], out             # a debut: this year's modal position
    assert out[4] == ["2B", "SS"], out       # 21 appearances: this year alone decides
    assert out[5] == ["UTIL"], out           # no games yet, nothing at 20: last modal
    # the same file read as of the closed season is the closed season alone
    assert _elig_from(raw, 2026)[1] == ["SS", "2B", "3B"]


def test_eligibility_reads_the_nightly_innings_feed_not_the_june_file():
    """Owner decision 24: fantasy eligibility (and so DFS, which delegates to
    it) reads the innings feed run_monthly refreshes nightly. The June sidecar
    nothing refreshed is not named as a source."""
    import fantasy_export as fe
    assert fe.ELIG_SOURCE == "fielding_innings.json"
    src = Path(fe.__file__).read_text(encoding="utf-8")
    assert '"mlb_fielding_positions.json"' not in src


def test_refresh_live_re_stamps_elig_from_the_innings_feed(tmp_path, monkeypatch):
    """The nightly path, end to end with the network stubbed: refresh_live
    rewrites a hitter's elig when fielding_innings.json changes, keeps pitchers
    on P, falls back to the detail position, and keeps the baked values when the
    innings artifact is gone. Mutation: elig re-stamped only by the monthly
    export (the pre-review state), or an empty read stripping every hitter."""
    import json as _json
    import fantasy_export as fe
    d = tmp_path / "data"
    d.mkdir()
    players = [
        {"mlbam": 1, "side": "hit", "pos": "H", "name": "A", "elig": ["SS"]},
        {"mlbam": 2, "side": "hit", "pos": "H", "name": "B", "elig": ["C"]},
        {"mlbam": 3, "side": "pit", "pos": "SP", "name": "C", "elig": ["P"]},
    ]
    (d / "fantasy.json").write_text(_json.dumps({"season": 2026, "players": players,
                                                 "schedule": {"games": {}}}), encoding="utf-8")
    (d / "mlb_player_detail.json").write_text(_json.dumps({"players": {
        "b": {"mlbam": 2, "pos": "1B", "team": "NYY", "name": "B"}}}), encoding="utf-8")

    def innings(block):
        (d / "fielding_innings.json").write_text(_json.dumps({"seasons": {"2026": block}}),
                                                 encoding="utf-8")

    monkeypatch.setattr(fe, "DATA_DIR", d)
    monkeypatch.setattr(fe, "OUT_PATH", d / "fantasy.json")
    monkeypatch.setattr(fe, "_active_roster_ids", lambda: {1, 2, 3})
    monkeypatch.setattr(fe, "_attach_schedule",
                        lambda payload: payload.setdefault("schedule", {}).update(
                            {"games": {"2026-09-11": []}}))
    monkeypatch.setattr(fe, "build_sections", lambda payload: {})
    monkeypatch.setattr(fe, "update_two_start_ledger",
                        lambda *a, **k: {"projected_added": 0, "grades_added": 0, "n_rows": 0})

    def served():
        doc = _json.loads((d / "fantasy.json").read_text(encoding="utf-8"))
        return {p["mlbam"]: p.get("elig") for p in doc["players"]}

    innings({"1": {"SS": {"g": 120, "gs": 118, "inn": 1000.0},
                   "3B": {"g": 30, "gs": 20, "inn": 200.0}},
             "2": {"C": {"g": 90, "gs": 85, "inn": 760.0}}})
    fe.refresh_live(log=None)
    assert served() == {1: ["SS", "3B"], 2: ["C"], 3: ["P"]}
    # the feed moves on overnight: the next refresh follows it
    innings({"1": {"2B": {"g": 140, "gs": 130, "inn": 1100.0}}})
    fe.refresh_live(log=None)
    assert served() == {1: ["2B"], 2: ["1B"], 3: ["P"]}   # 2 left the feed: detail slot
    # an absent artifact leaves the baked values standing
    (d / "fielding_innings.json").unlink()
    fe.refresh_live(log=None)
    assert served() == {1: ["2B"], 2: ["1B"], 3: ["P"]}


# ===========================================================================
# 2. Source contracts over the three clients
# ===========================================================================
@pytest.mark.parametrize("name", sorted(JS_FILES))
def test_each_client_fetches_its_own_sidecar(name):
    """ONE PAYLOAD PER CLIENT, and it is the client's own.

    The read goes through the coordinator's memoizing loader on the combined
    page, so that Redraft and Dynasty share ONE download and parse of the
    ~585KB corpus (budgeted under 600KB below) instead of two, and falls back
    to a bare fetch when the client is driven standalone. So the pin is on the call site and on the URL literals,
    not on the transport: what must never happen is a client naming a sidecar
    that is not its own, which is a second corpus starting.

    data/fantasy.json therefore appears in NO client but the two that render
    boards off it. The DFS player card reads that corpus too, and gets it from
    the host rather than by naming it here."""
    src = _src(name)
    urls = re.findall(r'DATA_URL\s*=\s*"([^"]+)"', src)
    assert urls == [SIDECAR[name]], (name, urls)
    code = _code(name)
    calls = re.findall(r"(?<!function )load\(\s*([A-Za-z_$][\w$]*)\s*\)", code)
    assert calls == ["DATA_URL"], (name, calls)
    # The loader itself is the ONLY fetch, and it takes the url it was handed.
    fetches = [f.strip() for f in re.findall(r"[^.\w]fetch\(\s*([^,)]+)", code)]
    assert fetches == ["url"], (name, fetches)
    assert sorted(set(re.findall(r'"(/data/[^"]+)"', code))) == [SIDECAR[name]], name


@pytest.mark.parametrize("name", sorted(GUARDED))
def test_no_em_or_en_dashes(name):
    src = _src(name)
    assert "—" not in src, f"{name}.js carries an em-dash"
    assert "–" not in src, f"{name}.js carries an en-dash"


@pytest.mark.parametrize("name", sorted(GUARDED))
def test_fantasy_pages_carry_no_betting_copy(name):
    """The betting rails belong to the betting surfaces. A fantasy page that
    starts carrying a gambling disclaimer is a fantasy page somebody has begun
    treating as a betting product."""
    low = _src(name).lower()
    for term in ("1-800-gambler", "21+", "sportsbook", "wager", "parlay",
                 "problem gambling", "moneyline"):
        assert term not in low, f"{name}.js carries betting copy: {term}"


@pytest.mark.parametrize("name", sorted(GUARDED))
def test_no_local_efv_basis(name):
    """THE SINGLE-BASIS RULE. Every eFV number on the site comes out of
    efv_board_scale.board_value on the server. A client that reaches for a raw
    grade field, or does arithmetic on one, has started a second basis, which
    is exactly the defect that had /fantasy/ showing one prospect two different
    eFV grades a tab apart."""
    src = _code(name)
    for bad in ("xfv_grade", "xfv_grade_quantile", "xfv_grade_realized",
                "board_value", "boardValue", "efvBoardValue"):
        assert bad not in src, f"{name}.js reaches for a raw grade field: {bad}"
    # No arithmetic on the served grade: reading and rounding only.
    for m in re.finditer(r"\.efv\s*([+\-*/])", src):
        raise AssertionError(f"{name}.js does math on the served eFV grade: {m.group(0)}")
    for m in re.finditer(r"\.fvE\s*([+\-*/])", src):
        raise AssertionError(f"{name}.js does math on the served eFV grade: {m.group(0)}")


def test_dynasty_rounds_efv_to_nearest_and_consensus_to_ceiling():
    """House grade conventions: scouting FV displays as a ceiling, eFV and
    plus-stats display to nearest."""
    src = _src("dynasty")
    assert "Math.round(c.fvE)" in src, "eFV must display to nearest"
    assert "Math.ceil(c.fv)" in src, "consensus FV must display as a ceiling"


def test_diamond_gate_is_read_but_never_asserted():
    """Every board client treats a missing gate as gating OFF, and nothing
    here may turn gating on.

    PIN UPDATED 2026-08-16 (gating-contract lane): the old pin required each
    client to read window.EEPHUS_DIAMOND itself, and the private copies that
    satisfied it read EEPHUS_DIAMOND.isMember / .previewRows, keys the config
    never defines, so a flipped flag would have capped PAYING members at 25
    rows. The clients now route through window.EephusDiamond
    (assets/eephus-diamond.js, the one authoritative contract), so the raw
    config global is banned from client CODE and the helper call is required
    instead. Comments may still name the killed ghost read; that is the
    documentation working, which is what _code() exists to allow."""
    for name in JS_FILES:
        src, code = _src(name), _code(name)
        assert "EephusDiamond" in code, f"{name}.js no longer calls the gating helper"
        assert "EEPHUS_DIAMOND" not in code, f"{name}.js reads the raw config again"
        assert "isMember" not in code, f"{name}.js grew a private membership read"
        assert "gating: true" not in src and "gating:true" not in src, name


def test_dfs_client_does_not_scrape_salaries():
    """Salaries are the user's. The client must not fetch them from anywhere."""
    src = _src("dfs")
    for bad in ("draftkings", "fanduel.com", "api.draftkings", "salaries.json"):
        assert bad not in src.lower(), f"dfs.js reaches for a salary feed: {bad}"
    assert "localStorage" in src


def test_dynasty_keeper_calculator_is_arithmetic_only():
    """The keeper tool compares a pick number against a served rank. It must
    not invent a dollar value, because no dynasty dollar curve has been fit."""
    src = _src("dynasty")
    assert "function breakEvenRound" in src
    assert "localStorage" in src
    assert re.search(r"dollar", src, re.IGNORECASE), (
        "the calculator should say out loud that it does not publish dollars")


# ===========================================================================
# 3. Scoring parity: redraft.js reproduces fantasy.js
# ===========================================================================
MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

# Hitting weights are format-independent in fantasy_scoring; pitching is not.
# Multiple players per pool so the roto z-scores are not degenerate.
PARITY_PAYLOAD = json.dumps({
    "season": 2026, "season_fraction": 0.66, "n_players": 6,
    "scoring": {
        "hitter": {"ab": -1.0, "h": 5.6, "double": 2.9, "triple": 5.7, "hr": 9.4,
                   "bb": 3.0, "hbp": 3.0, "sb": 1.9, "cs": -2.8},
        "pitcher": {"fgp": {"ip": 7.4, "k": 2.0, "h": -2.6, "bb": -3.0, "hbp": -3.0,
                            "hr": -12.3, "sv": 5.0, "hld": 4.0},
                    "sabr": {"ip": 5.0, "k": 2.0, "bb": -3.0, "hbp": -3.0,
                             "hr": -13.0, "sv": 5.0, "hld": 4.0}}},
    "scoring_catalog": [
        {"id": "fgp", "kind": "points", "label": "FanGraphs Points", "default": True},
        {"id": "sabr", "kind": "points", "label": "SABR Points"},
        {"id": "5x5", "kind": "roto", "label": "Old School (5x5)"},
        {"id": "4x4", "kind": "roto", "label": "Ottoneu Classic (4x4)"}],
    "players": [
        {"mlbam": 660271, "name": "Shohei Ohtani", "side": "hit", "pos": "DH", "team": "LAD",
         "elig": ["UTIL"], "fpts_fgp": 284.8, "skill": {"hem_plus": 168, "luck_gap": 11.0},
         "ros": {"pa": 260, "ab": 224, "h": 66, "double": 13, "triple": 1, "hr": 28,
                 "bb": 33, "hbp": 3, "sb": 9, "cs": 2, "r": 48, "rbi": 60,
                 "avg": 0.295, "obp": 0.402, "slg": 0.611}},
        {"mlbam": 592450, "name": "Aaron Judge", "side": "hit", "pos": "RF", "team": "NYY",
         "elig": ["OF"], "fpts_fgp": 260.0, "skill": {"hem_plus": 175, "luck_gap": -6.0},
         "ros": {"pa": 270, "ab": 226, "h": 71, "double": 15, "triple": 0, "hr": 25,
                 "bb": 41, "hbp": 3, "sb": 3, "cs": 1, "r": 52, "rbi": 65,
                 "avg": 0.314, "obp": 0.440, "slg": 0.628}},
        {"mlbam": 665742, "name": "Juan Soto", "side": "hit", "pos": "LF", "team": "NYM",
         "elig": ["OF"], "fpts_fgp": 240.0, "skill": {"hem_plus": 160, "luck_gap": 2.0},
         "ros": {"pa": 255, "ab": 205, "h": 60, "double": 12, "triple": 1, "hr": 18,
                 "bb": 46, "hbp": 2, "sb": 5, "cs": 2, "r": 45, "rbi": 50,
                 "avg": 0.293, "obp": 0.436, "slg": 0.541}},
        {"mlbam": 694973, "name": "Paul Skenes", "side": "pit", "pos": "SP", "team": "PIT",
         "elig": ["P"], "fpts_fgp": 210.0, "skill": {"sem_plus": 146, "luck": 0.002},
         "ros": {"ip": 62, "k": 78, "h": 47, "bb": 15, "hbp": 2, "hr": 5, "gs": 11,
                 "qs": 7, "w": 4, "era": 2.35, "whip": 1.00}},
        {"mlbam": 434378, "name": "Zack Wheeler", "side": "pit", "pos": "SP", "team": "PHI",
         "elig": ["P"], "fpts_fgp": 190.0, "skill": {"sem_plus": 131, "luck": -0.003},
         "ros": {"ip": 58, "k": 66, "h": 50, "bb": 12, "hbp": 3, "hr": 8, "gs": 10,
                 "qs": 6, "w": 4, "era": 3.10, "whip": 1.07}},
        {"mlbam": 656302, "name": "Dylan Cease", "side": "pit", "pos": "SP", "team": "SDP",
         "elig": ["P"], "fpts_fgp": 170.0, "skill": {"sem_plus": 118, "luck": 0.006},
         "ros": {"ip": 55, "k": 71, "h": 49, "bb": 22, "hbp": 2, "hr": 9, "gs": 10,
                 "qs": 5, "w": 3, "era": 3.68, "whip": 1.29}},
    ],
    "sections": {
        "ros_hitter": [660271, 592450, 665742],
        "ros_sp": [694973, 434378, 656302],
        "ros_rp": [],
        "buy_low": [{"mlbam": 660271, "side": "hit"}],
        "sell_high": [{"mlbam": 592450, "side": "hit"}],
        "closer_depth": {},
        "callup_watch": [],
        "daily_streamers": [],
        "two_start": [],
        "dynasty": [],
    },
})

PARITY_PRELUDE = """
var __html = {};
var __hashHandlers = [];
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function () { return null; };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'focus' || k === 'appendChild' || k === 'insertBefore') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'nextSibling') return null;
      if (k === 'files') return null;
      if (k === 'dataset') return {};
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function __btn(sec) {
  var hs = [];
  return { __sec: sec,
    getAttribute: function (n) {
      return (n === 'data-fantasysection' || n === 'data-redraftsection') ? sec : null; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {},
                 toggle: function () {}, contains: function () { return false; } },
    addEventListener: function (t, cb) { if (t === 'click') hs.push(cb); },
    click: function () { hs.forEach(function (h) { h({}); }); } };
}
var __btns = ['streamers','two_start','ros_sp','ros_rp','ros_hitter','buysell',
              'closers','callups','dynasty'].map(__btn);
function FT(val) { return { then: function (cb) { var r = cb(val); return (r && r.then) ? r : FT(r); },
                            catch: function () { return FT(val); } }; }
var PAYLOAD = %s;
var fetch = function () { return FT({ ok: true, json: function () { return FT(PAYLOAD); } }); };
var location = { href: '', hash: '', pathname: '/redraft/' };
var __nav = { querySelector: function () { return {}; }, appendChild: function () {},
              insertBefore: function () {} };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function (sel) { return sel === '.mlbstats-sectionnav' ? __nav : null; },
  querySelectorAll: function (sel) {
    // The redraft shell selector resolves to nothing here on purpose: the
    // module has to fall back to the fantasy-era nav, which is the tolerance
    // the split depends on while the shells land in another lane.
    return sel === '.mlbstats-sectionbtn[data-fantasysection]' ? __btns : [];
  },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var EEPHUS_GL = { wire: function () {} };
var EEPHUS_HUB = { teamLogo: function (t) { return '<i>' + t + '</i>'; },
                   links: function () { return FT({ byMlbam: {} }); } };
var window = { location: location, document: document, fetch: fetch,
               EEPHUS_HUB: EEPHUS_HUB, EEPHUS_GL: EEPHUS_GL,
               addEventListener: function (t, cb) { if (t === 'hashchange') __hashHandlers.push(cb); } };
// The module reads the BARE globals inside its window guards, exactly as a
// browser would resolve them.
function __go(hash) {
  location.hash = hash;
  __hashHandlers.forEach(function (h) { h({}); });
  return __html['redraft-app-root'] || __html['fantasy-app-root'] || '';
}
""" % PARITY_PAYLOAD

SCORE_RE = re.compile(
    r'class="mlb-metric (?:ff|rd)-strong"><span class="mlb-metric-label">[^<]*</span>([^<]*)</span>')


def _scores(html: str) -> list:
    return SCORE_RE.findall(html or "")


def _boot(js_path: Path) -> "MiniRacer":
    c = MiniRacer()
    c.eval(PARITY_PRELUDE + js_path.read_text(encoding="utf-8"))
    return c


@pytest.fixture(scope="module")
def parity_ctxs():
    return _boot(ASSETS / "fantasy.js"), _boot(ASSETS / "redraft.js")


@pytest.mark.parametrize("system", ["fgp", "sabr", "5x5", "4x4"])
@pytest.mark.parametrize("section", ["ros_hitter", "ros_sp"])
def test_redraft_scoring_matches_fantasy(parity_ctxs, section, system):
    """THE PORT CHECK. Both files render the same board from the same payload
    in the same format, through their own hash routers and their own card
    renderers, and the score column has to agree cell for cell."""
    old, new = parity_ctxs
    h = "#section=%s&sys=%s" % (section, system)
    a = _scores(old.eval("__go(%s)" % json.dumps(h)))
    b = _scores(new.eval("__go(%s)" % json.dumps(h)))
    assert a, ("the retired /fantasy/ board rendered no scores", section, system)
    assert a == b, (section, system, a, b)


def test_parity_fixture_actually_separates_the_formats(parity_ctxs):
    """A parity test over four formats is worthless if the four formats
    produce the same numbers. Pin that they do not."""
    old, _ = parity_ctxs
    seen = set()
    for system in ("fgp", "sabr", "5x5", "4x4"):
        seen.add(tuple(_scores(old.eval('__go("#section=ros_sp&sys=%s")' % system))))
    assert len(seen) == 4, seen


def test_redraft_drops_the_prospect_sections(parity_ctxs):
    """The split moved Dynasty and Call-up Watch to /dynasty/. /redraft/ must
    not carry them, and asking it for one must land on a rendered default board
    rather than a blank page."""
    src = _code("redraft")
    sections = re.search(r"var SECTIONS = \[(.*?)\];", src, re.DOTALL)
    assert sections, "redraft.js must declare its section alternation"
    names = re.findall(r'"([a-z_]+)"', sections.group(1))
    assert "dynasty" not in names and "callups" not in names, names
    assert "renderDynasty" not in src and "callup_watch" not in src
    _, new = parity_ctxs
    html = new.eval('__go("#section=dynasty")')
    assert html.strip(), "an unknown section must fall back to a rendered board"


# ===========================================================================
# 4. The DFS lineup optimizer, driven end to end
# ===========================================================================
# A pool small enough to brute-force in Python, and shaped so the greedy build
# CANNOT reach the optimum on its own: the greedy spends first on the highest
# projection at each slot and paints itself into a 24-point lineup, while the
# best legal lineup under the cap is 26. If the local-search pass ever stops
# working, this test drops from 26 to 24 and says so.
OPT_PLAYERS = [
    # (mlbam, name, side, elig, team, pts, salary)
    (1, "Ace Arm", "pit", ["P"], "AAA", 10.0, 9000),
    (2, "Cheap Arm", "pit", ["P"], "BBB", 6.0, 4000),
    (3, "Star Catcher", "hit", ["C"], "CCC", 8.0, 8000),
    (4, "Cheap Catcher", "hit", ["C"], "DDD", 3.0, 2000),
    (5, "Big Bat", "hit", ["OF"], "EEE", 9.0, 7000),
    (6, "Good Bat", "hit", ["OF"], "FFF", 7.0, 5000),
    (7, "Fine Bat", "hit", ["OF"], "GGG", 5.0, 3000),
    (8, "Punt Bat", "hit", ["OF"], "HHH", 2.0, 2000),
]
OPT_CAP = 20000
OPT_TEMPLATE = {
    "id": "mini", "label": "Mini: P, C, 2 OF", "scoring": "dk", "cap": OPT_CAP,
    "max_per_team": 2, "min_games": 1, "default": True,
    "slots": [{"slot": "P"}, {"slot": "C"}, {"slot": "OF"}, {"slot": "OF"}],
}


def _opt_payload() -> str:
    return json.dumps({
        "slate_date": "2026-08-05", "season": 2026, "n_games": 1, "n_players": len(OPT_PLAYERS),
        "empty_reason": None,
        "games": [{"game_pk": 1, "date": "2026-08-05", "venue": "Test Park",
                   "park_source": "none",
                   "home": {"org": "AAA", "probable": {"mlbam": 1, "name": "Ace Arm"}},
                   "away": {"org": "BBB", "probable": {"mlbam": 2, "name": "Cheap Arm"}}}],
        "players": [{"mlbam": m, "name": n, "side": s, "elig": e, "team": t,
                     "opp": "ZZZ", "is_home": True, "game_pk": 1,
                     "start_rate": 1.0 if s == "hit" else None,
                     "line": {}, "pts": {"dk": p, "fd": p}}
                    for (m, n, s, e, t, p, _sal) in OPT_PLAYERS],
        "scoring": {"dk": {"hitter": {}, "pitcher": {}}, "fd": {"hitter": {}, "pitcher": {}}},
        "scoring_catalog": [{"id": "dk", "label": "Classic", "default": True},
                            {"id": "fd", "label": "Full"}],
        "scoring_note": "test", "roster_templates": [OPT_TEMPLATE],
        "salaries": {"source": "user"}, "notes": [], "anchors": {"pa_per_start": 4.15},
    })


def _brute_force_best() -> float:
    """The true optimum for OPT_PLAYERS under the cap and the per-team limit."""
    import itertools
    by = {m: (elig, team, pts, sal) for (m, _n, _s, elig, team, pts, sal) in
          [(p[0], p[1], p[2], p[3], p[4], p[5], p[6]) for p in OPT_PLAYERS]}
    ps = [m for m in by if "P" in by[m][0]]
    cs = [m for m in by if "C" in by[m][0]]
    ofs = [m for m in by if "OF" in by[m][0]]
    best = 0.0
    for p in ps:
        for c in cs:
            for o1, o2 in itertools.combinations(ofs, 2):
                pick = [p, c, o1, o2]
                if len(set(pick)) != 4:
                    continue
                if sum(by[m][3] for m in pick) > OPT_CAP:
                    continue
                teams = {}
                for m in pick:
                    teams[by[m][1]] = teams.get(by[m][1], 0) + 1
                if max(teams.values()) > OPT_TEMPLATE["max_per_team"]:
                    continue
                best = max(best, sum(by[m][2] for m in pick))
    return best


APP_PRELUDE = """
var __html = {};
var __nodes = {};
var __hashHandlers = [];
var __LS = {};
var localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__LS, k) ? __LS[k] : null; },
  setItem: function (k, v) { __LS[k] = String(v); },
  removeItem: function (k) { delete __LS[k]; } };
function __mkNode(sel) {
  var hs = {};
  return { __sel: sel, value: '', checked: false, files: null,
    getAttribute: function () { return null; },
    setAttribute: function () {},
    addEventListener: function (t, cb) { (hs[t] = hs[t] || []).push(cb); },
    focus: function () {},
    __reset: function () { hs = {}; },
    __fire: function (t) { (hs[t] || []).forEach(function (c) { c({}); }); } };
}
// One node object per selector so a test can seed an input's value before the
// click that reads it, but its LISTENERS are dropped on every query: a render
// rebinds, and without the reset one click would fire N stacked handlers.
function __node(sel) {
  var n = __nodes[sel];
  if (!n) { n = __mkNode(sel); __nodes[sel] = n; }
  n.__reset();
  return n;
}
function __out() {
  return __html['dfs-app-root'] || __html['dynasty-app-root'] ||
         __html['redraft-app-root'] || __html['fantasy-app-root'] || '';
}
function __fireEvent(sel, type) {
  var n = __nodes[sel];
  if (!n) throw new Error('no node registered for ' + sel);
  n.__fire(type);
  return __out();
}
function __click(sel) { return __fireEvent(sel, 'click'); }
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function (sel) { return __node(sel); };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'focus' || k === 'appendChild' || k === 'insertBefore') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'files' || k === 'nextSibling') return null;
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function FT(val) { return { then: function (cb) { var r = cb(val); return (r && r.then) ? r : FT(r); },
                            catch: function () { return FT(val); } }; }
var PAYLOAD = %s;
var fetch = function () { return FT({ ok: true, json: function () { return FT(PAYLOAD); } }); };
var location = { href: '', hash: '', pathname: '/dfs/' };
// Ids a test declares ABSENT, so the harness can reproduce the real shell
// (the /dfs/ shell has no scoring bar; a proxy for every id would hide that
// and the inline-selector fallback would never be exercised).
var __MISSING = {};
function __hide(id) { __MISSING[id] = 1; }
var document = { readyState: 'complete',
  getElementById: function (id) { return __MISSING[id] ? null : __el(id); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var EEPHUS_GL = { wire: function () {} };
var EEPHUS_HUB = { teamLogo: function (t) { return '<i>' + t + '</i>'; },
                   links: function () { return FT({ byMlbam: {} }); } };
var window = { location: location, document: document, fetch: fetch,
               localStorage: localStorage,
               EEPHUS_HUB: EEPHUS_HUB, EEPHUS_GL: EEPHUS_GL,
               addEventListener: function (t, cb) { if (t === 'hashchange') __hashHandlers.push(cb); } };
function __go(hash) {
  location.hash = hash;
  __hashHandlers.forEach(function (h) { h({}); });
  return __out();
}
function __seedSalaries(json) { __LS['eephus.dfs.salaries'] = json; }
function __setValue(sel, v) {
  var n = __nodes[sel];
  if (!n) { n = __mkNode(sel); __nodes[sel] = n; }
  n.value = v;
}
"""


def _dfs_boot(payload_json: str, salaries: bool = False):
    """Boot assets/dfs.js over a payload, with the shell's actual furniture:
    the /dfs/ page has no scoring bar, so those ids are absent here too."""
    c = MiniRacer()
    c.eval(APP_PRELUDE % payload_json)
    c.eval("__hide('dfs-scoring'); __hide('fantasy-scoring');")
    if salaries:
        rows = {"%d|%s" % (m, s): {"salary": sal}
                for (m, _n, s, _e, _t, _p, sal) in OPT_PLAYERS}
        c.eval("__seedSalaries(%s)" % json.dumps(json.dumps(
            {"slate_date": "2026-08-05", "saved_at": "2026-08-05T00:00:00Z", "rows": rows})))
    c.eval((ASSETS / "dfs.js").read_text(encoding="utf-8"))
    return c


def _dfs_ctx():
    return _dfs_boot(_opt_payload(), salaries=True)


def test_dfs_optimizer_finds_the_best_legal_lineup():
    """End to end through the shipped client: seeded salaries, the optimizer
    tab, a real click on Optimize. The greedy build alone lands on 24 points
    here; the local-search pass has to find 26, which brute force confirms is
    the best lineup the cap and the per-team limit allow."""
    c = _dfs_ctx()
    c.eval('__go("#section=optimizer")')
    html = c.eval('__click("#dfs-run")')
    assert "projected points" in html, html[:400]
    pts = float(re.search(r"<b>([\d.]+)</b> projected points", html).group(1))
    assert pts == _brute_force_best() == 26.0, (pts, html[:600])
    used = int(re.search(r"<b>\$([\d,]+)</b> of", html).group(1).replace(",", ""))
    assert used <= OPT_CAP, used
    # Four filled slots, four distinct players (the fifth <tr> is the header).
    assert html.count("<tr><td>") == 4, html
    for who in ("Cheap Arm", "Star Catcher", "Good Bat", "Fine Bat"):
        assert who in html, (who, html[:600])


def test_dfs_optimizer_reports_missing_salaries_instead_of_guessing():
    """With no salary sheet loaded the optimizer must say what it is missing.
    Inventing a price would be the one thing this module refuses to do."""
    c = _dfs_boot(_opt_payload())
    html = c.eval('__go("#section=optimizer")')
    assert "No salaries loaded" in html, html[:400]


def test_dfs_empty_slate_renders_a_loud_state_not_a_blank_page():
    """An off day must reassure, and it must do so on the payload production
    actually emits. dfs_export._empty always stamps `empty_reason_kind`, so the
    fixture carries it too; without it this asserted the old one-message
    contract against a shape the exporter no longer produces."""
    empty = json.loads(_opt_payload())
    empty.update({"players": [], "games": [], "n_games": 0, "n_players": 0,
                  "empty_reason": "No MLB games scheduled for 2026-01-15.",
                  "empty_reason_kind": "no_games_scheduled"})
    c = _dfs_boot(json.dumps(empty))
    html = c.eval('__go("#section=pitchers")')
    assert "No games today" in html and "No MLB games scheduled" in html
    assert "Nothing is broken" in html


def test_dfs_pipeline_failure_does_not_claim_nothing_is_broken():
    """The other half of the same contract, and the reason the kinds exist. A
    schedule feed that did not answer is OUR outage, so the page must NOT tell
    the reader everything is fine, and must read as broken. An unknown kind gets
    the same treatment: silence is not a promise that we are healthy."""
    rendered = {}
    for kind in ("schedule_unavailable", None):
        broken = json.loads(_opt_payload())
        broken.update({"players": [], "games": [], "n_games": 0, "n_players": 0,
                       "empty_reason": "The schedule feed did not answer."})
        if kind:
            broken["empty_reason_kind"] = kind
        c = _dfs_boot(json.dumps(broken))
        rendered[kind] = c.eval('__go("#section=pitchers")')
        assert "Nothing is broken" not in rendered[kind], (
            f"kind={kind!r} wrongly reassures: {rendered[kind][:220]}")
    # A NAMED outage also has to LOOK like one, not merely withhold the
    # reassurance - is-broken is what styles the panel as a failure.
    assert "is-broken" in rendered["schedule_unavailable"], rendered["schedule_unavailable"][:220]
    assert "is-broken" not in rendered[None], (
        "an UNKNOWN kind must not be styled as a confirmed outage either")


def test_dfs_slate_section_renders_both_boards_and_the_selector():
    """The shell gives this page no scoring bar, so the contest-format selector
    has to ride inside the section or the reader cannot switch formats at all."""
    c = _dfs_ctx()
    html = c.eval('__go("#section=slate")')
    assert "Probable starters" in html and ">Hitters<" in html
    assert "Contest scoring" in html, html[:400]
    # Each board names its own sort state; sharing one is how a click on a
    # hitter column re-sorts the pitchers by a column they do not have.
    assert 'data-dfsboard="pitchers"' in html and 'data-dfsboard="hitters"' in html


def test_dfs_value_board_is_honest_without_salaries():
    c = _dfs_boot(_opt_payload())
    html = c.eval('__go("#section=value")')
    assert "nothing to value" in html
    assert "Name,Position,Salary" in html          # the import form is right there
    priced = _dfs_ctx().eval('__go("#section=value")')
    assert "Pts/$1k" in priced and "Ace Arm" in priced


def test_dfs_stacks_refuses_to_dress_a_sum_as_a_stack_projection():
    c = _dfs_ctx()
    html = c.eval('__go("#section=stacks")')
    assert "Top 4" in html and "Top 5" in html
    assert "correlation" in html.lower(), html[:600]
    assert "we do not model it" in html


# ---------------------------------------------------------------------------
# The context joins, rendered (2026-08-07)
# ---------------------------------------------------------------------------
def _ctx_payload(**over) -> str:
    """The optimizer payload with the three context joins populated: a resolved
    park, a Vegas total, and a posted card on one side of the game."""
    d = json.loads(_opt_payload())
    d["games"][0].update({
        "venue": "Test Park", "venue_id": 3313,
        "park_run_pf": 1.06, "park_source": "savant_mlb",
        "vegas": {"total": 9.0, "home_itt": 5.2, "away_itt": 3.8,
                  "p_home": 0.66, "p_away": 0.34, "n_books": 7},
        "lineups_posted": {"home": True, "away": False},
    })
    d["games"][0]["home"].update({"vegas_itt": 5.2, "lineup_posted": True})
    d["games"][0]["away"].update({"vegas_itt": 3.8, "lineup_posted": False})
    d["integrity"] = {"n_hitters": 6, "n_pitchers": 2, "n_probables_announced": 2,
                      "park_basis": "savant_mlb", "park_sources": {"savant_mlb": 1},
                      "vegas_games": 1, "lineup_sides_posted": 1,
                      "lineup_sides_possible": 2, "orgs_without_hitters": []}
    d["vegas_source"] = {"source": "2026-08-05-1519.json", "kind": "open",
                         "captured_at": "2026-08-05T15:19:23+00:00",
                         "n_events": 1, "n_matched": 1, "reason": None}
    for i, p in enumerate(d["players"]):
        if p["side"] != "hit":
            p["ctx"] = {"vegas_opp_itt": 3.8}
            continue
        p["ctx"] = {"vegas_itt": 5.2}
        if i == 2:                      # Star Catcher: on the posted card
            p.update({"lineup_spot": 3, "lineup_status": "confirmed",
                      "start_rate": 1.0, "start_rate_projected": 0.71,
                      "start_rate_source": "confirmed_lineup"})
        elif i == 3:                    # Cheap Catcher: posted and not on it
            p.update({"lineup_spot": None, "lineup_status": "not_in_lineup",
                      "start_rate": 0.0, "start_rate_projected": 0.44,
                      "start_rate_source": "confirmed_lineup"})
    d.update(over)
    return json.dumps(d)


def test_dfs_client_renders_the_three_context_joins():
    c = _dfs_boot(_ctx_payload())
    html = c.eval('__go("#section=slate")')
    assert "park 1.06" in html, html[:600]
    assert "total 9" in html and "5.20" in html and "3.80" in html
    assert ">Team total<" in html and ">Opp total<" in html and ">Spot<" in html
    # A confirmed start reads as a fact and a scratch reads as a scratch.
    assert "3rd" in html and "dfs-out" in html and "dfs-conf" in html
    # And the green "posted" mark rides ONLY the confirmed side. A scratch is
    # also sourced from a posted card, so an unguarded chip put a settled-fact
    # colour beside the 0% of a player who is not playing.
    star = html[html.index("Star Catcher"):]
    cheap = html[html.index("Cheap Catcher"):]
    assert "dfs-conf" in star[:400] and "dfs-conf" not in cheap[:400], cheap[:400]
    assert "dfs-out" in cheap[:400]
    # The integrity strip counts all three joins over what THIS slate needed.
    assert "Games with a park factor" in html and "Games with a Vegas total" in html
    assert "Lineups posted" in html


def test_dfs_client_park_sentence_follows_the_payload():
    """The method note used to hard-code "no MLB park table on the site yet".
    It now counts what the payload actually did, in all three states."""
    c = _dfs_boot(_ctx_payload())
    assert "the park's run index" in c.eval('__go("#section=slate")')
    none = json.loads(_ctx_payload())
    none["integrity"]["park_sources"] = {"neutral_site": 1}
    none["games"][0]["park_source"] = "neutral_site"
    html = _dfs_boot(json.dumps(none)).eval('__go("#section=slate")')
    assert "neutral on every game today" in html
    # The per-game card names WHICH neutral it is. One sentence covering an
    # average park, a neutral site and a failed lookup is how the old copy
    # managed to be wrong about all three at once.
    assert "neutral site, park factor not applied" in html
    mixed = json.loads(_ctx_payload())
    mixed["integrity"]["park_sources"] = {"savant_mlb": 9, "no_factor_for_park": 1}
    html = _dfs_boot(json.dumps(mixed)).eval('__go("#section=slate")')
    assert "9 of 10 games" in html


def test_dfs_client_says_why_a_slate_has_no_vegas_totals():
    """A column of dashes with no explanation is the failure mode. The absence
    carries its reason, and it says the budget rule out loud."""
    d = json.loads(_ctx_payload())
    d["games"][0]["vegas"] = None
    d["games"][0]["home"].pop("vegas_itt")
    d["integrity"]["vegas_games"] = 0
    d["vegas_source"] = {"source": None, "n_matched": 0,
                         "reason": "no odds snapshot is cached for this slate date"}
    html = _dfs_boot(json.dumps(d)).eval('__go("#section=slate")')
    assert "No Vegas team totals on this slate" in html
    assert "no odds snapshot is cached" in html
    assert "never fetch our own" in html


def test_dfs_client_spot_column_is_sortable_and_opens_ascending():
    """Ascending on first click, with scratches and unposted cards last: an
    ascending Spot sort that led with "out" would bury the nine rows the column
    exists to surface.

    STRUCTURAL, and the reason is a limit of this harness rather than a choice.
    The sort headers are wired through `root().querySelectorAll("[data-dfssort]")`
    and the stub's querySelectorAll returns [], so no sort control exists to
    click here and a click test would be green for the wrong reason. What is
    pinned instead is the contract the click reads: the header is emitted with
    the sort key on the hitters board, the key is in the ascending-on-first-
    click set, and a scratched bat carries NO sort value so it cannot land
    ahead of a confirmed one."""
    c = _dfs_boot(_ctx_payload())
    html = c.eval('__go("#section=slate")')
    assert 'data-dfssort="lineup" data-dfsboard="hitters"' in html, html[:800]
    js = _code("dfs")
    assert 'k === "lineup"' in js, "the Spot column does not open ascending"
    # p.lineup_spot is the sort value and a scratch has none, so "out" sorts
    # with the unknowns at the bottom in both directions.
    assert 'case "lineup": return p.lineup_spot || null;' in js


def test_dfs_client_stacks_show_the_market_total_beside_our_points():
    c = _dfs_boot(_ctx_payload())
    html = c.eval('__go("#section=stacks")')
    assert ">Team total<" in html and "5.20" in html
    assert "not priced off it" in html


def test_dfs_client_survives_a_payload_from_before_the_joins():
    """The joins are additive. A payload built by yesterday's exporter has no
    vegas, no lineup and no park_sources, and every one of those must render as
    an absence rather than an exception."""
    c = _dfs_boot(_opt_payload())
    for sec in ("slate", "stacks", "value", "optimizer"):
        html = c.eval('__go("#section=%s")' % sec)
        assert "undefined" not in html, (sec, html[:400])
        assert html.strip(), sec


# ---------------------------------------------------------------------------
# The merged /fantasy/ shell, its coordinator, and the URL migration
# ---------------------------------------------------------------------------
# The shell is read off the BUILDER, not off disk. These pins used to read
# dynasty/index.html and skip when it was absent, because the shells belonged to
# another lane; they belong to this one now, and a pin that skips on a fresh
# checkout is a pin that is green for the wrong reason.
import build_site  # noqa: E402

SUBMODULES = {"dynasty": "data-dynastysection",
              "redraft": "data-redraftsection",
              "dfs": "data-dfssection"}


@pytest.fixture(scope="module")
def fantasy_shell() -> str:
    return build_site.build_fantasy()


@pytest.mark.parametrize("name", sorted(SUBMODULES))
def test_shell_section_keys_are_known_to_the_client(name, fantasy_shell):
    """The shell's nav attribute values ARE the canonical section names: the
    client compares them directly when it paints the active tab. A tab the
    client does not know renders the fallback board under a nav announcing
    something else, which is the exact bug this pins."""
    keys = set(re.findall(SUBMODULES[name] + r'="([a-z_]+)"', fantasy_shell))
    assert keys, f"{name} declares no sections in the combined shell"
    m = re.search(r"var SECTIONS = \[(.*?)\];", _code(name), re.DOTALL)
    assert m, f"{name}.js must declare its section alternation"
    known = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert keys <= known, (name, sorted(keys - known))


def test_shell_never_exposes_the_fantasy_era_mount_ids(fantasy_shell):
    """THE TRIPLE-MOUNT GUARD, and the reason it is an assertion about an
    ABSENCE.

    Every client resolves its root, banner, control slot and nav through a
    candidate list that ends at the pre-split shared id. Across three pages
    that fallback was harmless tolerance. In ONE document it is a triple-mount:
    all three clients resolve to the same node, all three paint into it, and
    the last one to finish loading wins. Nothing about that failure looks like
    a bug in any one client, which is why the shell is what gets pinned."""
    for shared in ('id="fantasy-app-root"', 'id="fantasy-banner"',
                   'id="fantasy-scoring"', "data-fantasysection"):
        assert shared not in fantasy_shell, (
            f"the combined shell exposes {shared}: all three clients fall back "
            "to it and would mount into one node")
    # .fantasy-scoring-bar is a CLASS and is fine: three elements can share a
    # class. It is the ID candidates that collide.
    assert fantasy_shell.count("fantasy-scoring-bar") == 2


@pytest.mark.parametrize("name", sorted(SUBMODULES))
def test_each_submodule_mounts_exactly_once(name, fantasy_shell):
    for ident in (f'id="{name}-app-root"', f'id="{name}-banner"',
                  f'id="{name}-section"', f'data-fantasypanel="{name}"',
                  f'data-fantasymodule="{name}"'):
        assert fantasy_shell.count(ident) == 1, (name, ident,
                                                 fantasy_shell.count(ident))


def test_shell_lazy_loads_the_clients_and_never_scripts_them_directly(fantasy_shell):
    """data/fantasy.json is ~585KB and data/dfs.json is ~380KB. A shell with
    three <script> tags would boot all three clients, and both payloads, for a
    reader who only ever looks at one board. The clients ride data-src stamps
    that the coordinator injects on first activation instead, and only the
    coordinator is a script tag."""
    for name in SUBMODULES:
        assert re.search(r'data-src="/assets/%s\.js\?v=' % name, fantasy_shell), name
        assert not re.search(r'<script src="/assets/%s\.js' % name, fantasy_shell), (
            f"{name}.js is a script tag on the shell, so it boots eagerly")
    assert re.search(r'<script src="/assets/fantasy-hub\.js\?v=', fantasy_shell)
    # The Diamond flag and the shared card have to exist before any client runs.
    assert "diamond-config.js" in fantasy_shell
    assert "fantasy-card.js" in fantasy_shell


def test_the_default_module_is_the_only_visible_panel(fantasy_shell):
    """Before the coordinator runs, exactly one panel is on screen. Baking the
    hidden attribute on all three would leave a reader with no JS looking at a
    masthead and nothing else; baking it on none would flash three navs."""
    panels = re.findall(r'<div class="fantasy-mod" [^>]*data-fantasypanel="([a-z]+)"([^>]*)>',
                        fantasy_shell)
    assert len(panels) == 3, panels
    visible = [mod for mod, rest in panels if "hidden" not in rest]
    assert visible == ["redraft"], visible


# ---------------------------------------------------------------------------
# The coordinator, driven in a JS engine
# ---------------------------------------------------------------------------
# A stub of the combined shell: three module buttons carrying data-src, three
# panels, and per-module section buttons. There is deliberately NO
# [data-fantasysection] node, so a client that fell back to the fantasy-era nav
# would find nothing and its tabs would go dead here.
HUB_PRELUDE = r"""
var __html = {};
var __hashHandlers = [];
var __loaded = [];
var __fetches = [];
var __hidden = {};
var __selected = {};
var __clicks = {};
var __LS = {};
var localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__LS, k) ? __LS[k] : null; },
  setItem: function (k, v) { __LS[k] = String(v); },
  removeItem: function (k) { delete __LS[k]; } };
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function () { return null; };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'removeAttribute' || k === 'addEventListener'
          || k === 'removeEventListener' || k === 'focus' || k === 'appendChild'
          || k === 'insertBefore') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'files' || k === 'nextSibling') return null;
      if (k === 'dataset') return {};
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function __sbtn(mod, sec) {
  var hs = [];
  return { __sec: sec, __mod: mod,
    getAttribute: function (n) { return n === 'data-' + mod + 'section' ? sec : null; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {},
                 toggle: function () {}, contains: function () { return false; } },
    addEventListener: function (t, cb) { if (t === 'click') hs.push(cb); },
    click: function () { hs.forEach(function (h) { h({}); }); } };
}
var __sections = {
  redraft: ['streamers','two_start','ros_sp','ros_rp','ros_hitter','buysell','closers'],
  dynasty: ['dynasty','callups','keeper'],
  dfs: ['slate','value','optimizer','stacks'] };
var __sbtns = {};
Object.keys(__sections).forEach(function (m) {
  __sbtns[m] = __sections[m].map(function (s) { return __sbtn(m, s); }); });
function __tab(mod, sec) {
  var list = __sbtns[mod];
  for (var i = 0; i < list.length; i++) if (list[i].__sec === sec) list[i].click();
  return location.hash;
}
var __nosrc = {};
function __modbtn(id) {
  return {
    getAttribute: function (n) {
      if (n === 'data-fantasymodule') return id;
      if (n === 'data-src') return __nosrc[id] ? null : '/assets/' + id + '.js?v=test';
      return null; },
    setAttribute: function (n, v) { if (n === 'aria-selected') __selected[id] = (v === 'true'); },
    classList: { add: function () {}, remove: function () {},
                 toggle: function (c, on) { if (c === 'active') __selected[id] = !!on; },
                 contains: function () { return false; } },
    addEventListener: function (t, cb) { if (t === 'click') __clicks[id] = cb; } };
}
var __modbtns = ['redraft','dynasty','dfs'].map(__modbtn);
function __panel(id) {
  __hidden[id] = (id !== 'redraft');
  return { removeAttribute: function () { __hidden[id] = false; },
           setAttribute: function () { __hidden[id] = true; },
           querySelector: function (sel) {
             return sel === "[id$='-app-root']" ? __el(id + '-app-root') : null; } };
}
var __panels = { redraft: __panel('redraft'), dynasty: __panel('dynasty'), dfs: __panel('dfs') };
function FT(val) { return { then: function (cb) { var r = cb(val); return (r && r.then) ? r : FT(r); },
                            catch: function (cb) { return FT(val); } }; }
function FR(err) { return { then: function () { return FR(err); },
                            catch: function (cb) { var r = cb(err); return (r && r.then) ? r : FT(r); } }; }
var __PAYLOADS = __PAYLOADS__;
var fetch = function (u) {
  __fetches.push(u);
  var p = __PAYLOADS[u];
  if (p === undefined) return FR(new Error('HTTP 404'));
  return FT({ ok: true, json: function () { return FT(p); } });
};
var location = { href: '', hash: '', pathname: '/fantasy/' };
var history = { replaceState: function (a, b, url) { location.hash = String(url); } };
var __nav = { querySelector: function () { return {}; }, appendChild: function () {},
              insertBefore: function () {} };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function (sel) {
    var m = /\[data-fantasypanel="([a-z]+)"\]/.exec(sel);
    if (m) return __panels[m[1]] || null;
    if (sel === '.mlbstats-sectionnav') return __nav;
    return null; },
  querySelectorAll: function (sel) {
    if (sel === '[data-fantasymodule]') return __modbtns;
    var m = /data-([a-z]+)section\]$/.exec(sel);
    if (m && __sbtns[m[1]]) return __sbtns[m[1]];
    return []; },
  createElement: function (tag) {
    if (tag === 'script') {
      var rec = { onerror: null };
      Object.defineProperty(rec, 'src', {
        set: function (v) { __loaded.push(v); }, get: function () { return ''; } });
      return rec;
    }
    return __el(tag === 'div' ? 'fc-node' : 'created-' + tag); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var EEPHUS_GL = { wire: function () {} };
var EEPHUS_HUB = { teamLogo: function (t) { return '<i>' + t + '</i>'; },
                   links: function () { return FT({ byMlbam: {} }); } };
var window = { location: location, document: document, fetch: fetch,
               localStorage: localStorage,
               EEPHUS_HUB: EEPHUS_HUB, EEPHUS_GL: EEPHUS_GL,
               addEventListener: function (t, cb) { if (t === 'hashchange') __hashHandlers.push(cb); } };
function __enter(h) {
  location.hash = h;
  __hashHandlers.forEach(function (x) { x({}); });
  return location.hash;
}
function __switch(mod) { __clicks[mod](); return location.hash; }
function __root(mod) { return __html[mod + '-app-root'] || ''; }
"""

HUB_DFS_PAYLOAD = {
    "slate_date": "2026-08-05", "season": 2026, "n_games": 1, "n_players": 1,
    "empty_reason": None,
    "games": [{"game_pk": 1, "date": "2026-08-05", "venue": "Test Park",
               "park_source": "none",
               "home": {"org": "LAD", "probable": {"mlbam": 694973, "name": "Paul Skenes"}},
               "away": {"org": "PIT", "probable": None}}],
    "players": [{"mlbam": 660271, "name": "Shohei Ohtani", "side": "hit", "elig": ["UTIL"],
                 "team": "LAD", "opp": "PIT", "is_home": True, "game_pk": 1,
                 "start_rate": 1.0, "line": {}, "pts": {"dk": 11.0}}],
    "scoring": {"dk": {"hitter": {}, "pitcher": {}}},
    "scoring_catalog": [{"id": "dk", "label": "Classic", "default": True}],
    "scoring_note": "test", "roster_templates": [OPT_TEMPLATE],
    "salaries": {"source": "user"}, "notes": [], "anchors": {"pa_per_start": 4.15},
}


def _js(c, expr):
    """A JS value as a Python one. py_mini_racer hands back an opaque JSObject
    for arrays and objects, so anything structural round-trips through JSON."""
    return json.loads(c.eval("JSON.stringify(%s)" % expr))


def _hub(start_hash: str = "", modules=(), card: bool = False,
         nosrc=()) -> "MiniRacer":
    """Boot the coordinator over the stub shell at `start_hash`, then eval the
    sources of `modules` in the order the coordinator asked for them, which is
    what the injected script tags do in a browser. `nosrc` names modules whose
    bundle the shell does not carry."""
    payloads = json.dumps({"/data/fantasy.json": json.loads(PARITY_PAYLOAD),
                           "/data/dfs.json": HUB_DFS_PAYLOAD})
    c = MiniRacer()
    c.eval(HUB_PRELUDE.replace("__PAYLOADS__", payloads))
    for m in nosrc:
        c.eval("__nosrc[%s] = 1;" % json.dumps(m))
    c.eval("location.hash = %s;" % json.dumps(start_hash))
    if card:
        c.eval(CARD_JS.read_text(encoding="utf-8"))
    c.eval((ASSETS / "fantasy-hub.js").read_text(encoding="utf-8"))
    for m in modules:
        c.eval((ASSETS / ("%s.js" % m)).read_text(encoding="utf-8"))
    return c


# Every hash that has ever addressed one of these boards, and the module it has
# to land on now. FOUR generations: the pre-split /fantasy/ page (nine
# sections), the aliases that page already accepted, the three split pages, and
# the card hash. A link in any of them that stops resolving is a link somebody
# bookmarked.
LEGACY_HASHES = [
    # pre-split /fantasy/, and /redraft/ after it
    ("#section=streamers", "redraft"), ("#section=two_start", "redraft"),
    ("#section=ros_sp", "redraft"), ("#section=ros_rp", "redraft"),
    ("#section=ros_hitter", "redraft"), ("#section=buysell", "redraft"),
    ("#section=closers", "redraft"),
    # pre-split /fantasy/, and /dynasty/ after it
    ("#section=dynasty", "dynasty"), ("#section=callups", "dynasty"),
    ("#section=keeper", "dynasty"),
    # the documented pre-split aliases
    ("#section=board", "dynasty"), ("#section=pitchers", "dfs"),
    ("#section=hitters", "dfs"), ("#section=salaries", "dfs"),
    # /dfs/
    ("#section=slate", "dfs"), ("#section=value", "dfs"),
    ("#section=stacks", "dfs"), ("#section=optimizer", "dfs"),
]


@pytest.mark.parametrize("legacy,module", LEGACY_HASHES,
                         ids=[h.replace("#section=", "") for h, _m in LEGACY_HASHES])
def test_every_legacy_section_hash_lands_on_its_module(legacy, module):
    c = _hub(legacy)
    assert c.eval("location.hash").startswith("#m=%s&" % module), (
        legacy, c.eval("location.hash"))
    # And the sub-hash survives verbatim: the module's own client is what
    # normalizes an alias, and it cannot do that if the coordinator ate it.
    assert c.eval("location.hash") == "#m=%s&%s" % (module, legacy[1:])
    loaded = _js(c, "__loaded")
    assert loaded and loaded[0].startswith("/assets/%s.js" % module), loaded


@pytest.mark.parametrize("legacy,expected", [
    # A bare card link off the pre-merge Redraft board.
    ("#player=694973", "#m=redraft&player=694973"),
    # A full card link: board state and card together.
    ("#section=ros_sp&sys=sabr&player=694973",
     "#m=redraft&section=ros_sp&sys=sabr&player=694973"),
    # Sorts ride along untouched.
    ("#section=ros_hitter&hsort=hr.d", "#m=redraft&section=ros_hitter&hsort=hr.d"),
    # A dynasty lens.
    ("#section=board&lens=contend", "#m=dynasty&section=board&lens=contend"),
    # Nothing at all.
    ("", "#m=redraft"), ("#", "#m=redraft"),
    # A section nobody owns falls to the default module rather than nowhere.
    # "constructor" is the specific one worth naming: it is inherited off
    # Object.prototype, so a plain lookup in the module table would have
    # resolved it to a module and this would read "#m=function Object".
    ("#section=constructor", "#m=redraft&section=constructor"),
])
def test_legacy_hash_parameters_survive_the_namespacing(legacy, expected):
    assert _hub(legacy).eval("location.hash") == expected


def test_an_already_namespaced_hash_is_left_alone():
    c = _hub("#m=dfs&section=stacks")
    assert c.eval("location.hash") == "#m=dfs&section=stacks"
    assert _js(c, "__loaded")[0].startswith("/assets/dfs.js")


def test_only_the_named_module_is_downloaded():
    """The lazy-boot claim, measured. A reader who lands on Dynasty must not
    pay for the Redraft or DFS clients, and must not pay for data/dfs.json."""
    c = _hub("#section=callups", modules=("dynasty",))
    assert [u.split("?")[0] for u in _js(c, "__loaded")] == ["/assets/dynasty.js"]
    assert _js(c, "__fetches") == ["/data/fantasy.json"]


def test_the_client_normalizes_its_own_half_and_the_prefix_survives():
    """The two halves of the router each own their own job: the coordinator
    picks the module, the client canonicalizes the section. "board" is the
    dynasty alias, so the address bar has to end up saying dynasty AND still
    carry the module prefix."""
    c = _hub("#section=board", modules=("dynasty",))
    assert c.eval("location.hash") == "#m=dynasty&section=dynasty"
    c = _hub("#section=constructor", modules=("redraft",))
    assert c.eval("location.hash") == "#m=redraft&section=streamers"


def test_the_module_bar_switches_and_remembers_where_each_module_was():
    """Switching modules is a tab change, not a reload: a reader who checks the
    slate and comes back finds the board he left."""
    c = _hub("", modules=("redraft",))
    c.eval('__tab("redraft", "ros_rp")')
    assert c.eval("location.hash") == "#m=redraft&section=ros_rp"
    c.eval('__switch("dynasty")')
    assert c.eval("location.hash") == "#m=dynasty"
    assert _js(c, "__hidden") == {"redraft": True, "dynasty": False, "dfs": True}
    c.eval('__switch("redraft")')
    assert c.eval("location.hash") == "#m=redraft&section=ros_rp"
    assert _js(c, "__hidden") == {"redraft": False, "dynasty": True, "dfs": True}


def test_two_clients_in_one_document_do_not_fight_over_the_address_bar():
    """THE ROUTER-COLLISION GUARD. Both clients are loaded and both have a
    route handler bound. A tab click in the ACTIVE module writes the hash; the
    inactive one must not answer, and must not stamp its own vocabulary over
    the URL, which is exactly what three window-level hashchange listeners over
    three "#section=" namespaces did."""
    c = _hub("", modules=("redraft", "dynasty"))
    assert c.eval("location.hash") == "#m=redraft&section=streamers"
    # The dynasty client is loaded and idle. Its own tab buttons still exist in
    # the document; clicking one must not seize an address bar it does not own.
    c.eval('__tab("dynasty", "keeper")')
    assert c.eval("location.hash") == "#m=redraft&section=streamers"
    # Switch, and now dynasty owns it, at the tab that click selected.
    c.eval('__switch("dynasty")')
    assert c.eval("location.hash") == "#m=dynasty&section=keeper"
    c.eval('__tab("redraft", "closers")')
    assert c.eval("location.hash") == "#m=dynasty&section=keeper"


def test_the_corpus_is_downloaded_once_for_both_clients():
    """data/fantasy.json is ~585KB. Redraft and Dynasty read the same file, and
    before the merge they were two pages and two downloads. One document is one
    download, or the merge made the reader's life worse."""
    c = _hub("", modules=("redraft",))
    c.eval('__switch("dynasty")')
    assert _js(c, "__fetches") == ["/data/fantasy.json"], _js(c, "__fetches")


def test_a_reader_hash_change_reaches_the_module_it_names():
    """The Back button and a hand-edited URL both arrive here. Neither client
    listens on window any more, so if the coordinator did not dispatch, the
    address bar and the board would silently disagree."""
    c = _hub("", modules=("redraft",))
    c.eval('__enter("#m=redraft&section=ros_hitter")')
    assert "ROS Hitters" in c.eval("__root('redraft')") or c.eval("__root('redraft')")
    assert c.eval("location.hash") == "#m=redraft&section=ros_hitter"
    # Crossing into a module that has not been downloaded yet boots it.
    c.eval('__enter("#m=dfs&section=value")')
    assert [u.split("?")[0] for u in _js(c, "__loaded")] == [
        "/assets/redraft.js", "/assets/dfs.js"]


def test_the_dfs_module_reaches_the_player_card_through_the_shared_corpus():
    """THE ONE THING THE MERGE BOUGHT THAT NO SEPARATE PAGE COULD.

    The card is a lookup into data/fantasy.json, which the DFS client does not
    read and must not start reading: its sidecar is the slate. On one page the
    coordinator already holds that corpus for the other two modules, so a DFS
    row can open the card for the cost of a load that is either already done or
    is taken once, on the first card, and never for a reader who opens none."""
    c = _hub("#m=dfs&section=slate", modules=("dfs",), card=True)
    assert _js(c, "__fetches") == ["/data/dfs.json"], _js(c, "__fetches")
    board = c.eval("__root('dfs')")
    assert "Shohei Ohtani" in board
    hrefs = re.findall(r'href="(#m=dfs[^"]*player=660271)"', board)
    assert hrefs, board[:600]
    # The attribute is HTML-escaped in the markup; a browser hands the decoded
    # value to location, so the harness decodes it here rather than routing a
    # string no browser would ever produce.
    c.eval("__enter(%s)" % json.dumps(hrefs[0].replace("&amp;", "&")))
    assert "/data/fantasy.json" in _js(c, "__fetches"), _js(c, "__fetches")
    card_html = c.eval("__html['fc-node'] || ''")
    assert "Shohei Ohtani" in card_html, card_html[:400]
    # No four-format league score line here: that port lives in redraft.js and
    # a second copy would be a third implementation nobody is comparing.
    assert "FanGraphs Points" not in card_html


def test_a_client_that_never_loads_says_so_in_its_own_panel():
    """An injected script that 404s is the failure mode lazy boot introduces.
    The reader clicked a module; something has to answer him."""
    c = _hub("", modules=(), nosrc=("redraft",))
    note = c.eval("__html['redraft-app-root'] || ''")
    assert "fh-error" in note and "no client bundle" in note, note
    # The other half of the same failure: a bundle that 404s after injection.
    assert "onerror" in HUB_JS.read_text(encoding="utf-8")


def test_dfs_csv_import_matches_by_name_and_reports_misses():
    """The salary reader finds its columns by header name, joins on a folded
    name key, and tells the reader exactly what it could not place."""
    c = _dfs_boot(_opt_payload())
    c.eval('__go("#section=salaries")')
    csv = ("Position,Name,Salary,TeamAbbrev\n"
           "P,Ace Arm,9000,AAA\n"
           "C,Star Catcher,8000,CCC\n"
           "OF,\"Nobody Here\",4000,ZZZ\n")
    c.eval("__setValue('#dfs-csv-text', %s)" % json.dumps(csv))
    html = c.eval('__click("#dfs-csv-go")')
    assert "matched 2 to the slate" in html, html[:500]
    assert "Nobody Here" in html, html[:500]


# ===========================================================================
# 5. The dynasty client and its keeper calculator
# ===========================================================================
DYN_PAYLOAD = json.dumps({
    "season": 2026, "n_players": 0,
    "scoring_catalog": [], "players": [],
    "sections": {
        "dynasty": [
            {"mlbam": 101, "name": "First Kid", "org": "BOS", "pos": "SS", "eta": 2027,
             "efv": 62.4, "star": 31, "bust": 12, "surplus": 88.0, "band": [15.0, 190.0],
             "score": 9.1, "rank": 1, "tier": "Elite"},
            {"mlbam": 102, "name": "Middle Kid", "org": "SEA", "pos": "SP", "eta": 2029,
             "efv": 51.6, "star": 12, "bust": 28, "surplus": 22.0, "band": [0.0, 70.0],
             "score": 5.2, "rank": 25, "tier": "Tier 1"},
            {"mlbam": 103, "name": "Depth Kid", "org": "NYM", "pos": "OF", "eta": 2030,
             "efv": 44.2, "star": 5, "bust": 44, "surplus": 6.0, "band": [0.0, 30.0],
             "score": 2.1, "rank": 240, "tier": "Depth"},
        ],
        "callup_watch": [
            {"mlbam": 201, "name": "Almost Up", "org": "TEX", "pos": "C",
             "eta": 2026, "fv": 52.5, "fvE": 54.4},
        ],
    },
})


def _dyn_ctx():
    c = MiniRacer()
    c.eval(APP_PRELUDE % DYN_PAYLOAD)
    c.eval((ASSETS / "dynasty.js").read_text(encoding="utf-8"))
    return c


def test_dynasty_board_renders_served_grades_only():
    c = _dyn_ctx()
    html = c.eval('__go("#section=board")')
    assert "First Kid" in html and "Depth Kid" in html
    # The served rank leads and the eFV grade displays to nearest (62.4 -> 62).
    assert ">62<" in html, html[:800]
    assert "Keep by" in html


def test_dynasty_lens_is_a_preset_over_served_columns():
    """The contend and rebuild lenses re-sort the SAME board. Nothing about the
    model changes, so the eFV column must be identical under every lens."""
    c = _dyn_ctx()
    def grades(h):
        return sorted(re.findall(r'mlb-metric-label">.*?eFV.*?</span>(\d+)', c.eval(
            '__go(%s)' % json.dumps(h))))
    base = grades("#section=board")
    assert base, "the board must render an eFV column"
    assert grades("#section=board&lens=contend") == base
    assert grades("#section=board&lens=rebuild") == base


def test_dynasty_keeper_break_even_math():
    """12 teams, pick 6, a prospect the board ranks 25th: the keeper pays for
    itself from round 3 on, because pick 30 (round 3, slot 6) is the first
    pick later than his rank. At the default round 5 (pick 54) the verdict is
    keep with a +29 edge."""
    c = _dyn_ctx()
    html = c.eval('__go("#section=keeper")')
    assert "costs pick <b>54</b>" in html, html[:900]
    row = re.search(r"Middle Kid.*?</tr>", html, re.DOTALL)
    assert row, html[:1200]
    assert "R3" in row.group(0), row.group(0)
    assert "keep" in row.group(0) and "+29" in row.group(0), row.group(0)
    # No dollar valuation anywhere on the surface.
    assert "$" not in row.group(0), row.group(0)


def test_dynasty_keeper_settings_change_the_answer():
    """Editing a league setting re-renders the table off the new numbers and
    persists them, so the reader does not retype his league every visit."""
    c = _dyn_ctx()
    c.eval('__go("#section=keeper")')
    c.eval("__setValue('#dyn-k-teams', '20')")
    html = c.eval("__fireEvent('#dyn-k-teams', 'change')")
    # 20 teams, pick 6, round 5 -> pick 86 overall.
    assert "costs pick <b>86</b>" in html, html[:900]
    assert json.loads(c.eval("__LS['eephus.dynasty.keeper']"))["teams"] == 20


def test_dynasty_callup_watch_prefers_efv():
    c = _dyn_ctx()
    html = c.eval('__go("#section=callups")')
    assert "Almost Up" in html
    assert ">54<" in html, html[:800]     # eFV 54.4 to nearest, not the 53 ceiling of 52.5


def test_dynasty_empty_payload_is_a_note_not_a_blank():
    c = MiniRacer()
    c.eval(APP_PRELUDE % json.dumps({"season": 2026, "sections": {}}))
    c.eval((ASSETS / "dynasty.js").read_text(encoding="utf-8"))
    html = c.eval('__go("#section=board")')
    assert "nightly build" in html and "Nothing is broken" in html


# ===========================================================================
# 6. The scoring control is SCOPED to the tabs it can move (2026-08-07)
# ===========================================================================
# The owner reported the league-format selector as broken. It was not: it
# re-ranks 230 of 250 SP under SABR and 342 of 350 hitters under 5x5. What was
# broken was WHERE it rendered. The shell reserves a bar above the section nav
# and redraft.js filled it on all seven tabs, including the default landing tab
# (Daily Streamers), which is scored server-side in FanGraphs Points and cannot
# move. A control that visibly does nothing is indistinguishable from a broken
# one, so these pin the scoping rather than the re-ranking.
SCORED_TABS = ["ros_sp", "ros_rp", "ros_hitter"]
UNSCORED_TABS = ["streamers", "two_start", "buysell", "closers"]


def _redraft_ctx():
    c = MiniRacer()
    c.eval(PARITY_PRELUDE)
    c.eval(CARD_JS.read_text(encoding="utf-8"))
    c.eval((ASSETS / "redraft.js").read_text(encoding="utf-8"))
    return c


def _bar(c) -> str:
    return c.eval("__html['redraft-scoring'] || __html['fantasy-scoring'] || ''")


@pytest.mark.parametrize("section", SCORED_TABS)
def test_format_bar_renders_on_the_sections_it_moves(section):
    c = _redraft_ctx()
    c.eval('__go("#section=%s")' % section)
    assert "rd-scorebtn" in _bar(c), section


@pytest.mark.parametrize("section", UNSCORED_TABS)
def test_format_bar_is_absent_where_it_would_do_nothing(section):
    c = _redraft_ctx()
    c.eval('__go("#section=%s")' % section)
    assert "rd-scorebtn" not in _bar(c), (
        f"the league-format bar renders on {section}, which does not read it")


def test_leaving_a_scored_tab_clears_the_bar():
    """The bar is emptied on the way OUT, not merely skipped on the way in. A
    tab change that only re-rendered the section left the previous tab's bar
    sitting above a board that ignores it."""
    c = _redraft_ctx()
    c.eval('__go("#section=ros_sp")')
    assert "rd-scorebtn" in _bar(c)
    c.eval('__go("#section=closers")')
    assert "rd-scorebtn" not in _bar(c)


def test_ros_hitters_says_the_two_points_formats_share_one_table():
    """fantasy.json carries ONE scoring.hitter dict, because FanGraphs Points
    and SABR Points differ only on the pitching side. That is Ottoneu's rule,
    not a gap in ours, and the board says so rather than leaving a reader to
    conclude the selector is dead."""
    c = _redraft_ctx()
    html = c.eval('__go("#section=ros_hitter")')
    assert "share one hitter table" in html, html[:400]


def test_streamer_copy_does_not_point_at_a_bar_that_is_not_there():
    c = _redraft_ctx()
    html = c.eval('__go("#section=streamers")')
    assert "switch formats above" not in html


# ===========================================================================
# 7. The fantasy player card
# ===========================================================================
def test_card_is_not_a_second_corpus():
    """Its lazy fetches are tonight's slate and the two season-history boards
    behind the trend sparkline (2026-08-16), each taken only when a reader
    opens a card that needs it. The rest is a lookup into the payload the host
    already downloaded, so there is no page-per-player build and no second copy
    of fantasy.json. The history literals live HERE and nowhere else: the
    one-literal-per-client pin above keeps them out of the board clients."""
    src = _src("card")
    urls = re.findall(r'DFS_URL\s*=\s*"([^"]+)"', src)
    assert urls == ["/data/dfs.json"], urls
    assert sorted(set(re.findall(r'"(/data/[^"]+)"', _code("card")))) == [
        "/data/dfs.json", "/data/hitter_history.json", "/data/starter_history.json"]
    # ONE fetch call site (the shared lazy loader), taking the url it is handed.
    fetches = [f.strip() for f in re.findall(r"fetch\(\s*([^,)]+)", src)]
    assert fetches == ["url"], fetches
    assert "/data/fantasy.json" not in _code("card")


def test_card_does_not_carry_a_second_scoring_port():
    """The four-format line comes from the HOST, because the port lives in
    assets/redraft.js and test_redraft_scoring_matches_fantasy drives THAT file
    against the frozen assets/fantasy.js. A copy here would be a third
    implementation nobody is comparing."""
    src = _code("card")
    for bad in ("function scorePoints", "function rotoValue", "scoring.hitter",
                "scoring_catalog[", "fpts_fgp"):
        assert bad not in src, f"fantasy-card.js grew its own scoring: {bad}"
    assert "HOST.scoreLine" in src


def _card_html(c) -> str:
    """The overlay is created through document.createElement, which both JS
    harnesses register under the id 'c'."""
    return c.eval("__html['c'] || ''")


def test_card_renders_a_pitcher_with_every_format_and_his_line():
    c = _redraft_ctx()
    c.eval('__go("#section=ros_sp&player=694973")')
    assert c.eval("window.EEPHUS_FANTASY_CARD.isOpen()") is True
    html = _card_html(c)
    assert "Paul Skenes" in html
    labels = re.findall(r'fc-score-l">([^<]+)', html)
    assert labels == ["FanGraphs Points", "SABR Points",
                      "Old School (5x5)", "Ottoneu Classic (4x4)"], labels
    # The served projection, not a recomputation of it.
    assert re.search(r'fc-stat-l">IP</span>62\.0', html), html[:900]
    assert 'data-gl="sem_plus"' in html


def test_card_renders_a_hitter_with_the_luck_and_buy_signal():
    c = _redraft_ctx()
    c.eval('__go("#section=ros_hitter&player=660271")')
    html = _card_html(c)
    assert "Shohei Ohtani" in html
    assert 'data-gl="hem_plus"' in html and 'data-gl="xhem_plus"' in html
    assert "buy low" in html
    # The two POINTS formats agree on a hitter, which is the same Ottoneu fact
    # the board note states. Seeing it on the card is the point of the row.
    vals = re.findall(r'fc-score-v">([^<]+)', html)
    assert vals[0] == vals[1], vals


def test_card_never_scores_a_category_format_against_a_pool_of_one():
    """A category value is a POSITION IN A POOL. A player the served board does
    not carry has no pool, so the two roto rows are left off rather than
    computed against a pool that does not contain him. The points rows still
    render: those are a dot product and need nobody else."""
    payload = json.loads(PARITY_PAYLOAD)
    payload["sections"]["ros_sp"] = [694973, 434378]      # Cease dropped
    c = MiniRacer()
    c.eval(PARITY_PRELUDE.replace(PARITY_PAYLOAD, json.dumps(payload)))
    c.eval(CARD_JS.read_text(encoding="utf-8"))
    c.eval((ASSETS / "redraft.js").read_text(encoding="utf-8"))
    c.eval('__go("#section=ros_sp&player=656302")')
    html = _card_html(c)
    assert "Dylan Cease" in html, html[:400]
    labels = re.findall(r'fc-score-l">([^<]+)', html)
    assert labels == ["FanGraphs Points", "SABR Points"], labels


def test_card_falls_back_to_the_dynasty_row_for_a_prospect():
    """A prospect on the dynasty board has no rest-of-season record, which is
    not an error: he has not played in the majors. The card is still a card."""
    c = MiniRacer()
    c.eval(APP_PRELUDE % DYN_PAYLOAD)
    c.eval(CARD_JS.read_text(encoding="utf-8"))
    c.eval((ASSETS / "dynasty.js").read_text(encoding="utf-8"))
    c.eval('__go("#section=dynasty&player=102")')
    html = _card_html(c)
    assert "Middle Kid" in html
    # eFV 51.6 displays to NEAREST (52), served verbatim, never recomputed.
    assert re.search(r'data-gl="xfv">eFV</span></b>52<', html), html[:900]
    # The keeper break-even is this page's own arithmetic, handed in by the host.
    assert "Keep by" in html and "R3" in html


def test_card_link_carries_the_whole_board_state():
    """A card link copied out of the page has to restore the board it was
    opened from, so the href is the full hash and not a bare #player=."""
    c = _redraft_ctx()
    board = c.eval('__go("#section=ros_sp&sys=sabr")')
    hrefs = re.findall(r'href="(#[^"]*player=694973)"', board)
    assert hrefs, board[:600]
    assert "section=ros_sp" in hrefs[0] and "sys=sabr" in hrefs[0], hrefs[0]


# ===========================================================================
# 8. DFS freshness: the client self-check and the exporter's crash path
# ===========================================================================
def test_dfs_client_flags_a_past_slate_that_carries_no_stamp():
    """stale_slate is written by the PUBLISH DECISION, so it only exists on the
    paths that reached one. A run that never happened, or one that died before
    it, leaves an old payload on disk with no flag: on 2026-08-07 /dfs/ served
    the 2026-08-05 slate at full confidence for exactly that reason. A slate
    date in the past is enough to know."""
    payload = json.loads(_opt_payload())
    payload["slate_date"] = "2020-04-01"      # unambiguously behind any clock
    payload.pop("stale_slate", None)
    c = _dfs_boot(json.dumps(payload))
    html = c.eval('__go("#section=slate")')
    assert "This is the 2020-04-01 slate, not today's." in html, html[:400]
    # The exporter's own claim must NOT be borrowed here: nobody decided to keep
    # this board, the build simply never replaced it.
    assert "We kept the last board" not in html
    assert "old slate" in c.eval("__html['dfs-banner'] || ''")


def test_dfs_client_leaves_todays_slate_alone():
    import datetime
    payload = json.loads(_opt_payload())
    payload["slate_date"] = datetime.date.today().isoformat()
    c = _dfs_boot(json.dumps(payload))
    html = c.eval('__go("#section=slate")')
    assert "not today's" not in html
    assert "old slate" not in c.eval("__html['dfs-banner'] || ''")


def test_dfs_client_still_prefers_the_exporters_own_reason():
    """When the exporter DID make the call, its sentence and its checked-at
    stamp are what the reader sees. The self-check is a floor, not a rewrite."""
    payload = json.loads(_opt_payload())
    payload.update({"slate_date": "2020-04-01", "stale_slate": True,
                    "stale_reason": "the schedule feed did not answer",
                    "stale_checked_at": "2020-04-02T00:00:00Z"})
    c = _dfs_boot(json.dumps(payload))
    html = c.eval('__go("#section=slate")')
    assert "the schedule feed did not answer" in html
    assert "We kept the last board" in html
    assert "Checked 2020-04-02T00:00:00Z" in html


def _crash_refresh(monkeypatch, out, day, prev=None):
    import dfs_export as dx
    if prev is not None:
        out.write_text(json.dumps(prev), encoding="utf-8")

    def boom(**_kw):
        raise RuntimeError("simulated build crash")

    monkeypatch.setattr(dx, "build_payload", boom)
    n = dx.refresh(log=lambda *_a, **_k: None, day=day, out_path=out)
    return n, json.loads(out.read_text(encoding="utf-8"))


def test_dfs_crash_path_stamps_the_board_it_leaves_serving(tmp_path, monkeypatch):
    """The `except` around build_payload used to return 0 without touching the
    file, so a crashed run left the previous payload UNSTAMPED and the page
    served it as today's. A build that died is the same publish decision as a
    build we refused."""
    import datetime
    today = datetime.date.today()
    prev = {"slate_date": (today - datetime.timedelta(days=1)).isoformat(),
            "n_players": 42, "players": [{"mlbam": 1}]}
    n, got = _crash_refresh(monkeypatch, tmp_path / "dfs.json", today.isoformat(), prev)
    assert n == 42                       # what is SERVED, which is the old board
    assert got["stale_slate"] is True
    assert got["stale_kind"] == "build_failed"
    assert got["stale_age_days"] == 1
    assert got["stale_checked_at"]


def test_dfs_crash_path_respects_the_carry_bound(tmp_path, monkeypatch):
    """Past the bound the stale board is worse than the honest empty state, and
    the crash path gets that rule too rather than freezing /dfs/ forever."""
    import datetime
    import dfs_export as dx
    today = datetime.date.today()
    old = (today - datetime.timedelta(days=dx._MAX_STALE_CARRY_DAYS + 5)).isoformat()
    prev = {"slate_date": old, "n_players": 42, "players": [{"mlbam": 1}]}
    n, got = _crash_refresh(monkeypatch, tmp_path / "dfs.json", today.isoformat(), prev)
    assert n == 0
    assert got["empty_reason_kind"] == "build_failed"
    assert got["slate_date"] == today.isoformat()
    assert got["previous_slate_dropped"]["slate_date"] == old


def test_dfs_crash_path_with_nothing_on_disk_publishes_the_empty_state(tmp_path, monkeypatch):
    import datetime
    n, got = _crash_refresh(monkeypatch, tmp_path / "dfs.json",
                            datetime.date.today().isoformat())
    assert n == 0
    assert got["empty_reason_kind"] == "build_failed"
    assert got["players"] == []


def test_the_client_knows_the_build_failed_kind():
    """Every kind the exporter can stamp needs a headline here, or the payload
    says one thing and the page renders the generic fallback."""
    import dfs_export as dx
    src = _src("dfs")
    for kind in dx._KEEP_PREVIOUS_KINDS:
        assert kind + ":" in src, f"dfs.js has no empty-state copy for {kind}"


# ---------------------------------------------------------------------------
# The shells load the card module
# ---------------------------------------------------------------------------
def test_the_card_module_ships_before_the_clients_that_bind_to_it():
    """The combined shell loads the card module, and BEFORE the coordinator that
    binds to it: a host attaches to an API that has to already exist. Both tags
    are deferred, so document order is execution order.

    This asserts against /fantasy/ rather than the per-board shells because the
    merge turned /dynasty/ and /redraft/ into redirect stubs that load no client
    at all. A stub carrying a card module would be the bug, not the contract."""
    path = ROOT / "fantasy" / "index.html"
    if not path.exists():
        pytest.skip("fantasy/index.html is generated by build_site and is not in the tree yet")
    html = path.read_text(encoding="utf-8")
    assert re.search(r"/assets/fantasy-card\.js\?v=", html)
    assert html.index("fantasy-card.js") < html.index("fantasy-hub.js")


# ===========================================================================
# 9. Filters, pagination and the filter half of the hash grammar (2026-08-16)
# ===========================================================================
# The filter bar is a VIEW: name substring, served-elig position, served team.
# It must narrow what renders without re-scoring anything, ride the same
# validated hash grammar the boards already use, and (on DFS) govern the
# optimizer pool out loud. Redraft is driven through the hash (the parity
# prelude's querySelector returns null, so there is nothing to type into);
# DFS is driven through the shipped controls.

def _board_names(html: str) -> list[str]:
    return re.findall(r'class="mlb-name">.*?>([^<]+)</a>', html)


def test_redraft_ros_boards_render_the_filter_bar():
    c = _redraft_ctx()
    html = c.eval('__go("#section=ros_hitter")')
    assert 'id="rd-f-q"' in html and 'id="rd-f-team"' in html
    assert 'data-rdfpos="OF"' in html and 'data-rdfpos="UTIL"' in html
    # The bar sits ABOVE the tape sort bar.
    assert html.index("rd-filterbar") < html.index("ff-sortbar")
    # The SP board is all "P": a one-chip position filter is a dead control,
    # so the chips are absent while the search and team select stay.
    sp = c.eval('__go("#section=ros_sp")')
    assert 'id="rd-f-q"' in sp and "data-rdfpos" not in sp
    assert 'id="rd-f-team"' in sp


def test_redraft_name_filter_is_a_case_insensitive_substring():
    c = _redraft_ctx()
    html = c.eval('__go("#section=ros_hitter&q=JUDGE")')
    assert _board_names(html) == ["Aaron Judge"], _board_names(html)
    assert "1 of 3 rows" in html


def test_redraft_pos_chip_and_team_filter_narrow_the_board():
    c = _redraft_ctx()
    html = c.eval('__go("#section=ros_hitter&pos=OF")')
    assert _board_names(html) == ["Aaron Judge", "Juan Soto"], _board_names(html)
    # A fresh hash WITHOUT pos= clears it: the Back button undoes a filter.
    html = c.eval('__go("#section=ros_hitter&team=NYY")')
    assert _board_names(html) == ["Aaron Judge"], _board_names(html)
    html = c.eval('__go("#section=ros_hitter")')
    assert len(_board_names(html)) == 3


def test_redraft_filter_refuses_values_the_pool_does_not_carry():
    """pos and team validate against the SERVED pool, the same rule #sys=
    follows against the served scoring catalog: a stale hash degrades to no
    filter rather than to an empty board."""
    c = _redraft_ctx()
    html = c.eval('__go("#section=ros_hitter&pos=ZZ&team=QQ")')
    assert len(_board_names(html)) == 3, _board_names(html)


def test_redraft_filter_does_not_rescore_the_roto_pool():
    """THE FILTER IS A VIEW. Roto values are pooled z-scores, so the pool
    scores first and the filter narrows what renders: a filtered board must
    show the SAME value for a player as the unfiltered one."""
    c = _redraft_ctx()

    def score_of(html, name):
        card = [x for x in html.split('<div class="mlb-card') if name in x][0]
        return SCORE_RE.search(card).group(1)

    base = score_of(c.eval('__go("#section=ros_hitter&sys=5x5")'), "Aaron Judge")
    filt = score_of(c.eval('__go("#section=ros_hitter&sys=5x5&q=judge")'), "Aaron Judge")
    assert filt == base, (filt, base)


def test_redraft_buysell_takes_a_name_search():
    c = _redraft_ctx()
    html = c.eval('__go("#section=buysell&q=judge")')
    assert "Aaron Judge" in html and "Shohei Ohtani" not in html
    # The emptied side says the filter did it, not the build.
    assert "No buy-low candidate matches the name filter." in html


def test_redraft_closers_take_a_name_search():
    payload = json.loads(PARITY_PAYLOAD)
    payload["players"].append(
        {"mlbam": 621111, "name": "Relief Guy", "side": "pit", "pos": "RP", "team": "BOS",
         "elig": ["P"], "fpts_fgp": 60.0,
         "skill": {"rem_plus": 133, "gmli": 1.8, "saves": 21, "luck": -0.02},
         "ros": {"ip": 22, "k": 40, "era": 2.10, "whip": 0.95, "sv": 12}})
    payload["sections"]["closer_depth"] = {"BOS": [621111]}
    c = MiniRacer()
    c.eval(PARITY_PRELUDE.replace(PARITY_PAYLOAD, json.dumps(payload)))
    c.eval((ASSETS / "redraft.js").read_text(encoding="utf-8"))
    html = c.eval('__go("#section=closers&q=relief")')
    assert "Relief Guy" in html and "rd-team-card" in html
    html = c.eval('__go("#section=closers&q=zzz")')
    assert "No bullpen matches the name filter." in html


def test_filter_state_rides_the_validated_hash_grammar():
    """Round trip through the coordinator: the filter keys land in the module,
    narrow the board, and survive into the normalized address bar. An invalid
    value is refused AND normalized out of the URL, exactly as an invalid
    #section= is."""
    c = _hub("#m=redraft&section=ros_hitter&q=judge&team=NYY", modules=("redraft",))
    h = c.eval("location.hash")
    assert h.startswith("#m=redraft&section=ros_hitter"), h
    assert "q=judge" in h and "team=NYY" in h, h
    html = c.eval("__root('redraft')")
    assert "Aaron Judge" in html and "Shohei Ohtani" not in html
    c2 = _hub("#m=redraft&section=ros_hitter&team=QQ", modules=("redraft",))
    assert "team=" not in c2.eval("location.hash"), c2.eval("location.hash")


def test_dfs_filter_bar_narrows_both_boards_and_the_value_board():
    c = _dfs_ctx()
    html = c.eval('__go("#section=slate&q=catcher")')
    assert 'id="dfs-f-q"' in html
    assert "Star Catcher" in html and "Big Bat" not in html
    # One bar governs BOTH boards: no arm matches "catcher" and the pitcher
    # board says the filter did it.
    assert "No starter matches the current filter." in html
    html = c.eval('__go("#section=slate&pos=C")')
    assert "Star Catcher" in html and "Cheap Catcher" in html and "Big Bat" not in html
    html = c.eval('__go("#section=slate&team=EEE")')
    assert "Big Bat" in html and "Star Catcher" not in html
    priced = c.eval('__go("#section=value&q=arm")')
    assert "Ace Arm" in priced and "Star Catcher" not in priced


def test_dfs_optimizer_pool_honors_the_active_filters():
    """Owner-approved semantics: the solver sees the filtered pool, and the
    panel says so rather than quietly solving over rows the reader hid."""
    c = _dfs_ctx()
    html = c.eval('__go("#section=optimizer")')
    assert "filtering shrinks the pool" in html
    c.eval('__go("#section=optimizer&team=AAA")')
    html = c.eval('__click("#dfs-run")')
    assert "filter is active" in html
    # One club is one arm: the C and OF slots cannot fill, and the solver says
    # so instead of drafting a player the boards are hiding.
    assert "No lineup satisfies" in html
    # Clearing the filter restores the whole pool and the known optimum.
    c.eval('__go("#section=optimizer")')
    html = c.eval('__click("#dfs-run")')
    pts = float(re.search(r"<b>([\d.]+)</b> projected points", html).group(1))
    assert pts == 26.0, pts


def _pager_payload(n: int = 130) -> str:
    """A slate with n hitters so the pagination contract is exercised over a
    board that actually pages."""
    d = json.loads(_opt_payload())
    teams = ["AAA", "BBB", "CCC"]
    d["players"] = [p for p in d["players"] if p["side"] == "pit"] + [
        {"mlbam": 1000 + i, "name": "Bat %03d" % i, "side": "hit", "elig": ["OF"],
         "team": teams[i % 3], "opp": "ZZZ", "is_home": True, "game_pk": 1,
         "start_rate": 1.0, "line": {}, "pts": {"dk": 500.0 - i, "fd": 500.0 - i}}
        for i in range(n)]
    d["n_players"] = len(d["players"])
    return json.dumps(d)


def test_dfs_hitter_board_pages_at_100_and_extends():
    c = _dfs_boot(_pager_payload(130))
    html = c.eval('__go("#section=slate")')
    assert html.count("Bat ") == 100, html.count("Bat ")
    assert 'id="dfs-more-hit"' in html
    assert "Showing the top 100 of 130" in html
    html = c.eval('__click("#dfs-more-hit")')
    assert html.count("Bat ") == 130, html.count("Bat ")
    assert 'id="dfs-more-hit"' not in html


def test_dfs_filters_reset_the_pagination():
    c = _dfs_boot(_pager_payload(130))
    c.eval('__go("#section=slate")')
    c.eval('__click("#dfs-more-hit")')                    # extended to all 130
    c.eval("__setValue('#dfs-f-q', 'Bat')")
    html = c.eval("__fireEvent('#dfs-f-q', 'input')")     # filter change resets the page
    assert "Showing the top 100 of 130" in html, html[:400]
    assert html.count("Bat ") == 100


def test_dynasty_board_filters_on_name_org_eta_and_tier():
    c = _dyn_ctx()
    assert _board_names(c.eval('__go("#section=dynasty&q=middle")')) == ["Middle Kid"]
    assert _board_names(c.eval('__go("#section=dynasty&team=NYM")')) == ["Depth Kid"]
    assert _board_names(c.eval('__go("#section=dynasty&eta=2027")')) == ["First Kid"]
    assert _board_names(c.eval('__go("#section=dynasty&tier=t1")')) == ["Middle Kid"]
    # Values the served board does not carry are refused, not rendered empty.
    assert len(_board_names(c.eval('__go("#section=dynasty&team=ZZ&eta=1999&tier=t9")'))) == 3
    # The rank diamond keeps the MODEL rank through a filter: Depth Kid is
    # rank 240 whether or not he is the only card on screen.
    html = c.eval('__go("#section=dynasty&q=depth")')
    ranks = re.findall(r'class="ff-rank-i">(\d+)</span>', html)
    assert ranks == ["240"], ranks


def test_dynasty_keeper_and_callups_take_a_name_search():
    c = _dyn_ctx()
    html = c.eval('__go("#section=keeper&q=depth")')
    assert "Depth Kid" in html and "First Kid" not in html
    html = c.eval('__go("#section=callups&q=zzz")')
    assert "No call-up candidate matches the name filter." in html


# ---------------------------------------------------------------------------
# The team_next7 bake and the payload budget (2026-08-16)
# ---------------------------------------------------------------------------
def test_fantasy_team_next7_bakes_shape_and_context():
    """{org: [{d, opp, home, opp_off, opp_bp}]}, keyed by the CLUB, capped at 7
    rows, opponent context joined from _teams_context and rounded to ints. An
    opponent the context cannot resolve carries None, never a fabricated 100:
    missing is not average, the same rule the DFS matchup mark enforces."""
    import fantasy_export as fe
    sched = {"BOS": [{"d": "2026-08-17", "opp": "NYY", "home": True},
                     {"d": "2026-08-18", "opp": "NYY", "home": True},
                     {"d": "2026-08-19", "opp": "ZZZ", "home": False}] +
                    [{"d": "2026-08-%d" % (20 + i), "opp": "TBR", "home": False}
                     for i in range(6)]}
    ctx = {"NYY": {"offense_plus": 104.4, "bullpen_plus": 98.6},
           "TBR": {"offense_plus": 96.0, "bullpen_plus": 101.2}}
    out = fe._team_next7(sched, ctx)
    assert set(out) == {"BOS"}, out.keys()
    assert out["BOS"][0] == {"d": "2026-08-17", "opp": "NYY", "home": True,
                             "opp_off": 104, "opp_bp": 99}
    assert len(out["BOS"]) == 7                       # a 9-game window still caps at 7
    assert out["BOS"][2]["opp_off"] is None and out["BOS"][2]["opp_bp"] is None
    assert fe._team_next7({}, ctx) == {} and fe._team_next7(None, ctx) == {}
    # And build_sections actually wires it, off the schedule's team_sched7 leg.
    src = (ROOT / "fantasy_export.py").read_text(encoding="utf-8")
    assert 'sections["team_next7"]' in src and "team_sched7" in src


def test_fantasy_payload_stays_inside_its_budget():
    """The corpus is budgeted at 600KB (561KB before team_next7; the new
    section plus its schedule leg measure ~24KB at the 30-org worst case). The
    live file is asserted when it exists; the fixture bound always runs, so a
    fresh checkout still pins the new section's size."""
    import fantasy_export as fe
    live = ROOT / "data" / "fantasy.json"
    if live.exists():
        assert live.stat().st_size < 600 * 1024, live.stat().st_size
    full = {("ORG%02d" % i): [{"d": "2026-08-%02d" % (17 + j), "opp": "OPP",
                               "home": j % 2 == 0} for j in range(7)]
            for i in range(30)}
    ctx = {"OPP": {"offense_plus": 104.4, "bullpen_plus": 98.2}}
    blob = json.dumps(fe._team_next7(full, ctx), separators=(",", ":"))
    assert len(blob) < 20 * 1024, len(blob)


@pytest.mark.parametrize("name", ["dynasty", "redraft", "dfs"])
def test_the_retired_board_shells_are_stubs_that_load_no_client(name):
    """The merge's other half. A stub that still booted a client would mount a
    second copy of a board the combined page already owns."""
    path = ROOT / name / "index.html"
    if not path.exists():
        pytest.skip(f"{path.name} is generated by build_site and is not in the tree yet")
    html = path.read_text(encoding="utf-8")
    assert "fantasy-card.js" not in html, name
    assert "/assets/%s.js" % name not in html, name
    assert "/fantasy/" in html, name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
