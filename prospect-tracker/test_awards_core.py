"""awards_core.py: the selection rules on a fixture world (AWARDS_2_RULES_CORE; AWARDS_PLAN
6 'Invariants and tests' rows I1, I2, I4, I8, I10).

test_fixtures/awards/core/ is a synthetic 2026 season cut in the shapes of the served files
(stint-frame records per side, data/ewar.json players[mlbam][season], the war board's
players[] and teams[], a rookies.json season block, StatsAPI standings and the served
team_outlook current block). It carries a cross-league pitcher shaped like Skubal 2026
(3.10 AL plus 2.19 NL pitching), a two-way player, a hitter traded across leagues, a 7.05
that the board prints as 7.0, a -0.04 that must print 0.0, two MVP ties broken by WPA, two
Cy Young ties broken by IP, two rookies removed by the days proxy alone, and 30 clubs whose
earned WAR sums to 999.0 and whose wins sum to 2430. No test opens a socket.
"""
from __future__ import annotations

import json
import random
import socket
from pathlib import Path

import pytest

import awards_core as A

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "awards" / "core"
SEASON = 2026
PROV = "ewar_v2"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an awards_core test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def world():
    w = {k: _load(f"{k}_{SEASON}.json") for k in
         ("stint_bat", "stint_pit", "ewar", "board", "rookies", "wpa", "skill_raw",
          "standings", "team_outlook")}
    w["rows"] = A.league_split({"bat": w["stint_bat"], "pit": w["stint_pit"]},
                               season=SEASON, war_provider=PROV)
    w["wpa"] = {int(k): v for k, v in w["wpa"].items()}
    w["skill_raw"] = {int(k): v for k, v in w["skill_raw"].items()}
    w["ballots"] = {}
    for lg in A.LEAGUES:
        w["ballots"][("MVP", lg)] = A.mvp_ballot(w["rows"], lg, SEASON, wpa=w["wpa"])
        w["ballots"][("CY", lg)] = A.cy_young_ballot(w["rows"], lg, SEASON, skill_raw=w["skill_raw"])
        w["ballots"][("ROY", lg)] = A.rookie_ballot(w["rows"], lg, SEASON, rookies=w["rookies"],
                                                    wpa=w["wpa"])
        w["ballots"][("MOY", lg)] = A.manager_ballot(
            w["standings"]["clubs"], w["team_outlook"]["team_outlook"], w["board"]["teams"],
            lg, SEASON, war_provider=PROV)
    return w


# --- constants and pins -----------------------------------------------------------------

def test_flag_label_and_ballot_rules():
    assert A.AWARDS_LIVE is False
    assert A.MODULE_LABEL == "Awards / HoF"
    assert A.BALLOT_RULES["MVP"] == {"n": 10, "points": [14, 9, 8, 7, 6, 5, 4, 3, 2, 1]}
    assert A.BALLOT_RULES["CY"] == {"n": 5, "points": [7, 4, 3, 2, 1]}
    assert A.BALLOT_RULES["ROY"] == {"n": 3, "points": [5, 3, 1]}
    assert A.BALLOT_RULES["MOY"] == {"n": 3, "points": [5, 3, 1]}
    for v in A.BALLOT_RULES.values():
        assert len(v["points"]) == v["n"]
    assert A.ballot_rules_payload() == A.BALLOT_RULES
    assert A.ballot_rules_payload() is not A.BALLOT_RULES


def test_score_display_equals_blank_free_on_10000_random_values():
    from war_board_export import _blank_free
    rng = random.Random(20261003)
    values = [rng.uniform(-12.0, 12.0) for _ in range(10000)]
    values += [7.05, -0.04, 0.04, -0.05, 0.05, 2.25, -2.25, 0.0, -0.0, 6.04, 5.29, 9.83]
    for v in values:
        got, want = A.score_display(v), _blank_free(v)
        assert got == want and str(got) == str(want), v
    assert A.score_display(None) is None and _blank_free(None) is None
    assert str(A.score_display(-0.04)) == "0.0"


def test_copied_constants_pin_to_their_homes():
    import war_board_export as W
    import awards_rookies as R
    from rate_stabilization import REPLACEMENT_WINS
    assert A.ROY_MIN_PA == W.QUAL_MIN_PA
    assert A.ROY_MIN_IP == W.QUAL_MIN_IP
    assert A.ROOKIE_PRIOR_AB_MAX == R.PRIOR_AB_MAX
    assert A.ROOKIE_PRIOR_IP_MAX == R.PRIOR_IP_MAX
    assert A.ROOKIE_PROXY_DAYS_MAX == R.PROXY_DAYS_MAX
    assert A.ROOKIE_NEAR_TOKEN == R.NEAR_TOKEN
    assert A.REPLACEMENT_WINS == REPLACEMENT_WINS == 47.7


def test_floors_scale_by_scheduled_games():
    assert A.scheduled_games(2026) == 162 and A.scheduled_games(2020) == 60
    assert A.floors("MVP", 2026) == {"pa": 252, "ip": 81, "g": 162}
    assert A.floors("CY", 2026)["ip"] == 41
    assert A.floors("MVP", 2020) == {"pa": 93, "ip": 30, "g": 60}
    assert A.floors("CY", 2020)["ip"] == 15
    assert A.floors("ROY", 2026) == {"pa": 100, "ip": 30, "g": 162}
    assert A.floors("MOY", 2026) == {"pa": None, "ip": None, "g": 162}
    assert "252" in A.floor_label("MVP", 2026) and "81" in A.floor_label("MVP", 2026)
    assert "93" in A.floor_label("MVP", 2020) and "60 games" in A.floor_label("MVP", 2020)


# --- I1: the league split reconciles to the provider artifact and the board ------------

def test_i1_league_shares_sum_to_the_side_totals(world):
    from war_board_export import _blank_free
    totals = A.side_totals(world["rows"])
    board = {p["mlbam"]: p for p in world["board"]["players"]}
    checked = 0
    for mlbam, seasons in world["ewar"]["players"].items():
        cell = seasons[str(SEASON)]
        t = totals[int(mlbam)]
        assert abs(t["bat"] - cell.get("ewb", 0.0)) <= 0.005, mlbam
        assert abs(t["pit"] - cell.get("ewp", 0.0)) <= 0.005, mlbam
        assert _blank_free(t["bat"] + t["pit"]) == board[int(mlbam)]["war"], mlbam
        checked += 1
    assert checked == len(board) == 33
    # the 7.05 prints 7.0 (never a half-up 7.1) and the -0.04 prints 0.0 (never -0.0)
    assert board[900001]["war"] == 7.0 and abs(totals[900001]["bat"] - 7.05) < 1e-9
    assert str(board[900009]["war"]) == "0.0"


def test_i1_every_ballot_row_prints_through_score_display(world):
    from war_board_export import _blank_free
    n = 0
    for b in world["ballots"].values():
        for r in b["top"]:
            assert r["score_display"] == _blank_free(r["score"]) == A.score_display(r["score"])
            n += 1
    assert n == 2 * (10 + 5 + 3 + 3)


def test_league_split_skips_other_seasons_and_needs_a_provider(world):
    assert all(r["war_provider"] == PROV for r in world["rows"])
    morrow = [r for r in world["rows"] if r["mlbam"] == 900001]
    assert len(morrow) == 1 and morrow[0]["pa"] == 650      # the 2025 row is not folded in
    with pytest.raises(ValueError):
        A.league_split({"bat": world["stint_bat"], "pit": world["stint_pit"]},
                       season=SEASON, war_provider="")


# --- I2: the sides -----------------------------------------------------------------------

def test_i2_cy_pit_is_the_pitcher_side_and_mvp_total_is_the_board_total(world):
    from war_board_export import _blank_free
    ewar = world["ewar"]["players"]
    board = {p["mlbam"]: p for p in world["board"]["players"]}
    for lg in A.LEAGUES:
        for r in world["ballots"][("CY", lg)]["top"]:
            if "split_season" in r["flags"]:
                continue
            assert abs(r["pit"] - ewar[str(r["mlbam"])][str(SEASON)]["ewp"]) < 1e-9
            assert r["bat"] == 0.0 or r["mlbam"] == 900004
        for r in world["ballots"][("MVP", lg)]["top"]:
            if "split_season" in r["flags"]:
                continue
            assert _blank_free(r["bat"] + r["pit"]) == board[r["mlbam"]]["war"]
    # the two-way player: both sides summed before rounding (3.24 + 2.80 = 6.04 -> 6.0)
    twp = next(r for r in world["ballots"][("MVP", "AL")]["top"] if r["mlbam"] == 900004)
    assert twp["bat"] == 3.24 and twp["pit"] == 2.80 and twp["score_display"] == 6.0


# --- I10: the Skubal-shaped split and deterministic ties ------------------------------------

def test_i10_cross_league_pitcher_yields_two_league_rows(world):
    rows = [r for r in world["rows"] if r["mlbam"] == 900010]
    assert [r["league"] for r in rows] == ["AL", "NL"]
    al, nl = rows
    assert abs(al["pit"] - 3.10) < 1e-9 and abs(nl["pit"] - 2.19) < 1e-9
    assert al["split_season"] and nl["split_season"]
    assert al["share"] == nl["share"] == {"AL": {"bat": 0.0, "pit": 3.10}, "NL": {"bat": 0.0, "pit": 2.19}}
    assert al["clubs"] == ["DET"] and nl["clubs"] == ["LAD"]
    assert abs(al["ip"] - 290 / 3) < 1e-3 and abs(nl["ip"] - 62.0) < 1e-9
    cy_al = world["ballots"][("CY", "AL")]["top"]
    me = next(r for r in cy_al if r["mlbam"] == 900010)
    assert me["rank"] == 3 and me["score_display"] == 3.1 and "split_season" in me["flags"]
    assert A.split_label(me, PROV) == "Split season: 3.1 eWAR v2 in the AL and 2.2 eWAR v2 in the NL."
    # the traded hitter is a candidate in each league with that league's share only
    lane = {r["league"]: r for r in world["rows"] if r["mlbam"] == 900008}
    assert lane["NL"]["bat"] == 2.0 and lane["AL"]["bat"] == 1.5
    assert A.side_totals(world["rows"])[900008]["bat"] == 3.5


def test_i10_ties_break_in_the_stated_order(world):
    mvp = world["ballots"][("MVP", "AL")]
    tied = [r for r in mvp["top"] if "tie" in r["flags"]]
    assert [r["mlbam"] for r in tied] == [900006, 900005]       # WPA 3.0 before WPA 2.0
    assert tied[0]["rank"] == 7 and tied[1]["rank"] == 8
    assert mvp["tiebreak_sentence"] == "Tied on the rule: Benji Ortiz, Arlo Finch at 4.5; ordered by in-league WPA."
    cy = world["ballots"][("CY", "AL")]
    tied = [r for r in cy["top"] if "tie" in r["flags"]]
    assert [r["mlbam"] for r in tied] == [900015, 900014]       # 110 IP before 100 IP
    assert world["ballots"][("MVP", "NL")]["tiebreak_sentence"] is None


def test_i10_synthetic_ties_are_deterministic_and_fall_to_mlbam():
    rows = []
    for mlbam in (3, 1, 2):
        rows.append({"mlbam": mlbam, "name": f"P{mlbam}", "league": "AL", "bat": 4.0, "pit": 0.0,
                     "pa": 400, "ip": 0.0, "clubs": ["BOS"], "split_season": False, "share": None,
                     "war_provider": PROV})
    out = A.mvp_ballot(rows, "AL", SEASON, wpa={})
    assert [r["mlbam"] for r in out["top"]] == [1, 2, 3]
    assert all("tie" in r["flags"] for r in out["top"])
    assert out["lead"] == "1st and 2nd are tied on the rule; ordered by in-league WPA."
    # WPA first, then id; the input order never matters
    out2 = A.mvp_ballot(list(reversed(rows)), "AL", SEASON, wpa={2: 1.0})
    assert [r["mlbam"] for r in out2["top"]] == [2, 1, 3]
    assert A.mvp_ballot(rows, "AL", SEASON, wpa={2: 1.0}) == out2
    # Cy Young: score, IP, skill raw, id
    pit = [dict(r, bat=0.0, pit=3.0, pa=0, ip=100.0) for r in rows]
    pit[0]["ip"] = 100.0
    out3 = A.cy_young_ballot(pit, "AL", SEASON, skill_raw={3: 120.0, 1: 110.0})
    assert [r["mlbam"] for r in out3["top"]] == [3, 1, 2]     # equal IP: SEM+ raw, missing last


# --- the rules on the fixture podiums ----------------------------------------------------

def test_mvp_ballots_run_to_ten_and_apply_the_floor(world):
    for lg in A.LEAGUES:
        top = world["ballots"][("MVP", lg)]["top"]
        assert len(top) == 10 and [r["rank"] for r in top] == list(range(1, 11))
    al = world["ballots"][("MVP", "AL")]
    assert [r["mlbam"] for r in al["top"][:3]] == [900001, 900002, 900003]
    assert 900007 not in {r["mlbam"] for r in al["top"]}          # 200 PA is under 252
    assert al["lead"] == "1st leads 2nd by 0.3 eWAR v2."
    assert al["floor"] == {"pa": 252, "ip": 81, "g": 162}
    nl = world["ballots"][("MVP", "NL")]
    assert nl["top"][0]["mlbam"] == 900020 and nl["top"][0]["score_display"] == 9.8
    assert nl["top"][2]["mlbam"] == 900022 and nl["top"][2]["pos"] is None
    assert nl["lead"] == "1st leads 2nd by 2.5 eWAR v2."


def test_cy_young_pitching_side_only(world):
    al = world["ballots"][("CY", "AL")]["top"]
    assert len(al) == 5 and al[0]["mlbam"] == 900011 and al[0]["score_display"] == 6.5
    assert 900016 not in {r["mlbam"] for r in al}                 # 30 IP is under 41
    for r in al:
        assert r["score"] == r["pit"]
    nl = world["ballots"][("CY", "NL")]["top"]
    assert nl[0]["mlbam"] == 900022 and nl[3]["mlbam"] == 900010 and nl[3]["score_display"] == 2.2


def test_rookie_ballot_uses_the_block_and_lists_the_days_proxy_removals(world):
    al = world["ballots"][("ROY", "AL")]
    assert [r["mlbam"] for r in al["top"]] == [900001, 900007, 900016]
    assert A.ROOKIE_NEAR_TOKEN in al["top"][2]["flags"]
    assert al["excluded"] == [{"mlbam": 900013, "name": "Rafa Ortega",
                               "reason": "roster days 53 over 45 (estimate); near_45_day_line",
                               "proxy_days": 53}]
    assert A.excluded_label(al["excluded"][0]) == "Outside the rookie test: Rafa Ortega (45-day estimate: 53 days)."
    nl = world["ballots"][("ROY", "NL")]
    assert [r["mlbam"] for r in nl["top"]] == [900024, 900025, 900026]
    assert [e["mlbam"] for e in nl["excluded"]] == [900027]
    assert nl["floor"] == {"pa": 100, "ip": 30, "g": 162}
    # a player with no row in the block is not a rookie (over the lines) and is not listed
    assert 900002 not in {r["mlbam"] for r in al["top"]} | {e["mlbam"] for e in al["excluded"]}
    assert A.rookie_status(world["rookies"])[900013]["near"] is True


# --- I4: Manager of the Year on club-seasons -------------------------------------------------

def test_i4_manager_scores_decompose_and_sum_to_zero(world):
    scores = A.manager_scores(world["standings"]["clubs"], world["team_outlook"]["team_outlook"],
                              world["board"]["teams"], SEASON, war_provider=PROV)
    assert len(scores) == 30 and all(r["score"] is not None for r in scores)
    pyth = {t["team"]: t["current"]["pythagPct"] * t["current"]["gamesPlayed"]
            for t in world["team_outlook"]["team_outlook"]}
    from trades import canonical_org
    for r in scores:
        assert abs(r["parts"]["sequencing"] + r["parts"]["runs_vs_player_value"] - r["score"]) < 1e-9
        assert abs(r["pythag_w"] - pyth[canonical_org(r["club"])]) < 1e-9
        assert abs(r["parts"]["sequencing"] - (r["w"] - r["pythag_w"])) < 1e-9
        expected = (A.REPLACEMENT_WINS + r["war_earned"]) * r["gp"] / 162
        assert abs(r["score"] - (r["w"] - expected)) < 1e-9
    assert abs(sum(r["score"] for r in scores)) < 0.5
    # the dialects join: standings TB, team_outlook TBR, the board TB -> one club TBR
    tb = next(r for r in scores if r["club"] == "TBR")
    assert tb["club_code"] == "TB" and tb["war_earned"] is not None and tb["pythag_w"] is not None


def test_i4_manager_ballot_orders_by_score_then_sequencing_then_code(world):
    al = world["ballots"][("MOY", "AL")]
    assert len(al["top"]) == 3 and al["n_pool"] == 15 and al["unscored"] == []
    assert al["top"][0]["club"] == "TBR" and al["top"][0]["score_display"] == 7.0
    assert al["lead"] == "1st leads 2nd by 2.5 wins."
    nl = world["ballots"][("MOY", "NL")]
    assert nl["top"][0]["club"] == "CIN" and nl["top"][0]["w"] < nl["top"][0]["l"]   # no floor: a losing club leads
    for r in al["top"] + nl["top"]:
        parts = r["parts"]
        assert parts["sequencing_display"] == A.score_display(parts["sequencing"])
        assert r["links"] == {"management": f"/management/#team={r['club']}",
                              "franchise": f"/franchise/#team={r['club']}"}
    # ties: equal score falls to W minus Pythagorean W, then the club code
    st = [{"club": "AAA", "league": "AL", "w": 81, "l": 81}, {"club": "BBB", "league": "AL", "w": 81, "l": 81}]
    to = [{"team": "AAA", "current": {"pythagPct": 0.5, "gamesPlayed": 162}},
          {"team": "BBB", "current": {"pythagPct": 0.48, "gamesPlayed": 162}}]
    out = A.manager_ballot(st, to, {"AAA": 33.3, "BBB": 33.3}, "AL", SEASON, war_provider=PROV)
    assert [r["club"] for r in out["top"]] == ["BBB", "AAA"]
    assert all("tie" in r["flags"] for r in out["top"])
    out2 = A.manager_ballot(st, to[:1], {"AAA": 33.3, "BBB": 33.3}, "AL", SEASON, war_provider=PROV)
    assert out2["unscored"] == [{"club": "BBB", "missing": ["pythag"]}] and len(out2["top"]) == 1


# --- I8: the projection pair refuses a provider mismatch ---------------------------------------

NEXT_ROWS = [
    {"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 1.1, "war_next": 3.05, "pa": 600, "ip": 0},
    {"mlbam": 2, "name": "B", "club_code": "NYM", "war_realized": 9.8, "war_next": 5.81, "pa": 700, "ip": 0},
    {"mlbam": 3, "name": "C", "club_code": "SEA", "war_realized": 0.4, "war_next": 2.14, "pa": 0, "ip": 90},
    {"mlbam": 4, "name": "D", "club_code": "TEX", "war_realized": 4.0, "war_next": 1.0, "pa": 100, "ip": 10},
]


def test_i8_next_pair_refuses_on_a_provider_mismatch_both_ways():
    with pytest.raises(A.ProviderMismatch):
        A.next_rise(NEXT_ROWS, SEASON, bundle_provider="ewar_v2", realized_provider="fwar")
    with pytest.raises(A.ProviderMismatch):
        A.next_drop(NEXT_ROWS, SEASON, bundle_provider="fwar", realized_provider="ewar_v2")
    with pytest.raises(A.ProviderMismatch):
        A.next_rise(NEXT_ROWS, SEASON, bundle_provider="ewar_v2", realized_provider=None)
    assert issubclass(A.ProviderMismatch, ValueError)


def test_next_pair_on_matching_providers():
    rise = A.next_rise(NEXT_ROWS, SEASON, bundle_provider="ewar_v2", realized_provider="ewar_v2")
    assert rise["id"] == "next_rise" and rise["title"] == "Largest projected rise for 2027"
    assert rise["war_provider"] == "ewar_v2" and rise["n_pool"] == 3        # D is under the floor
    assert [r["id"] for r in rise["rows"]] == [1, 3, 2]
    assert rise["rows"][0]["from"] == 1.1 and rise["rows"][0]["to"] == 3.05
    assert abs(rise["rows"][0]["value"] - 1.95) < 1e-9 and rise["rows"][0]["value_display"] == "+1.9"
    drop = A.next_drop(NEXT_ROWS, SEASON, bundle_provider="ewar_v2", realized_provider="ewar_v2")
    assert [r["id"] for r in drop["rows"]] == [2, 3, 1] and drop["rows"][0]["value_display"] == "-4.0"
    assert "eWAR v2" in rise["definition"] and "2027" in rise["definition"]


# --- the board superlatives -----------------------------------------------------------------

def test_glove_relief_contact_and_pitching_changes_apply_their_floors():
    fielders = [
        {"mlbam": 1, "name": "A", "team": "DET", "pos": "C", "inn": 995.7, "qualified": True,
         "dem_plus": 136, "dem_plus_raw": 136.05, "def_runs": 25.2},
        {"mlbam": 2, "name": "B", "team": "CHC", "pos": "CF", "inn": 399.0, "qualified": False,
         "dem_plus": 140, "dem_plus_raw": 140.2, "def_runs": 9.0},
        {"mlbam": 3, "name": "C", "team": "KC", "pos": "SS", "inn": 1200.0, "qualified": True,
         "dem_plus": 128, "dem_plus_raw": 128.28, "def_runs": 20.1},
    ]
    g = A.glove(fielders, SEASON)
    assert [r["id"] for r in g["rows"]] == [1, 3] and g["rows"][0]["value_display"] == 136
    assert g["rows"][0]["value"] == 136.05 and g["rows"][0]["pos"] == "C" and g["kind"] == "index"
    assert g["registry"] == "dem_plus" and g["war_provider"] is None
    relievers = [
        {"mlbam": 1, "name": "A", "team": "SD", "rem_plus": 195, "rem_plus_raw": 194.7, "qualified": True,
         "ip": 70.0, "gmli": 1.9, "wpa": 5.37, "saves": 38},
        {"mlbam": 2, "name": "B", "team": "MIN", "rem_plus": 180, "rem_plus_raw": 180.0, "qualified": True,
         "ip": 39.9, "gmli": 1.9, "wpa": 2.0, "saves": 10},
        {"mlbam": 3, "name": "C", "team": "NYY", "rem_plus": 170, "rem_plus_raw": 170.0, "qualified": True,
         "ip": 60.0, "gmli": 1.1, "wpa": 1.0, "saves": 0},
        {"mlbam": 4, "name": "D", "team": "ATL", "rem_plus": 150, "rem_plus_raw": 148.4, "qualified": True,
         "ip": 61.0, "gmli": 1.2, "wpa": 2.5, "saves": 3},
    ]
    r = A.relief(relievers, SEASON)
    assert [x["id"] for x in r["rows"]] == [1, 4] and r["rows"][1]["gmli"] == 1.2
    hitters = [
        {"mlbam": 1, "name": "A", "team": "PHI", "pa": 600, "luck_gap": 0.042, "xwoba": 0.38, "woba": 0.338},
        {"mlbam": 2, "name": "B", "team": "TB", "pa": 650, "luck_gap": -0.056, "xwoba": 0.30, "woba": 0.356},
        {"mlbam": 3, "name": "C", "team": "SF", "pa": 299, "luck_gap": 0.090, "xwoba": 0.40, "woba": 0.31},
        {"mlbam": 4, "name": "D", "team": "COL", "pa": 500, "luck_gap": 0.010, "xwoba": 0.33, "woba": 0.32},
    ]
    ca = A.contact_ahead(hitters, SEASON)
    assert [x["id"] for x in ca["rows"]] == [1, 4, 2] and ca["rows"][0]["xwoba_minus_woba"] == 0.042
    assert ca["rows"][0]["value_display"] == "+0.042" and ca["kind"] == "signed"
    ra = A.results_ahead(hitters, SEASON)
    assert [x["id"] for x in ra["rows"]] == [2, 4, 1] and ra["rows"][0]["value_display"] == "-0.056"
    clubs = [
        {"club": "TBR", "season": 2026, "n_pitching_change": 522, "mwpa_pitching_change": 8.953},
        {"club": "ATL", "season": 2026, "n_pitching_change": 480, "mwpa_pitching_change": 8.451},
        {"club": "SDP", "season": 2026, "n_pitching_change": 99, "mwpa_pitching_change": 9.9},
        {"club": "CIN", "season": 2025, "n_pitching_change": 609, "mwpa_pitching_change": 10.0},
    ]
    pc = A.pitching_changes(clubs, SEASON)
    assert [x["id"] for x in pc["rows"]] == ["ctbr", "catl"] and pc["rows"][0]["value_display"] == "+8.95"
    assert pc["rows"][0]["links"] == {"management": "/management/#team=TBR", "franchise": "/franchise/#team=TBR"}
    assert pc["registry"] == "mgmt_decision_ledger"
    # top_n caps the list
    many = [dict(fielders[0], mlbam=i, dem_plus_raw=130.0 + i) for i in range(10)]
    assert len(A.glove(many, SEASON)["rows"]) == A.SL_TOP_N == 5


def test_midrank_percentiles_share_ties():
    assert A.midrank_percentiles([1, 2, 2, 3]) == [12.5, 50.0, 50.0, 87.5]
    assert A.midrank_percentiles([]) == []
    assert A.midrank_percentiles([5]) == [50.0]


def test_prospect_pair_on_open_cohorts_flags_the_floor_grade():
    frames = {"lv_first": 2020, "vm_first": 2025}
    rows = [
        {"mlbam": 1, "name": "A", "club_code": "BOS", "player_key": "a", "debut_season": 2017,
         "efv_at_debut": 20.0, "war": 4.0, "pa": 600, "ip": 0},
        {"mlbam": 2, "name": "B", "club_code": "NYY", "player_key": "b", "debut_season": 2018,
         "efv_at_debut": 60.0, "war": 1.0, "pa": 500, "ip": 0},
        {"mlbam": 3, "name": "C", "club_code": "SEA", "player_key": "c", "debut_season": 2019,
         "efv_at_debut": 45.0, "war": 2.5, "pa": 0, "ip": 150},
        {"mlbam": 4, "name": "D", "club_code": "TEX", "player_key": "d", "debut_season": 2016,
         "efv_at_debut": 50.0, "war": 6.0, "pa": 200, "ip": 0},          # under the floor
    ]
    above = A.prospect_above(rows, SEASON, war_provider=PROV, frames=frames)
    assert above["n_pool"] == 3 and [r["id"] for r in above["rows"]] == [1, 3, 2]
    a = above["rows"][0]
    assert a["flags"] == ["graded_at_floor"] and a["from"] < a["to"]
    assert abs(a["value"] - (a["to"] - a["from"])) < 1e-9 and a["links"]["prospx"] == "/prospx/#player=a"
    assert above["registry"] == "xfv_backgrade" and above["war_provider"] == PROV
    below = A.prospect_below(rows, SEASON, war_provider=PROV, frames=frames)
    assert [r["id"] for r in below["rows"]] == [2, 3, 1]
    assert "consensus" not in json.dumps(above).lower()
