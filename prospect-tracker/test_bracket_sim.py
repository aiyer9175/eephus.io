# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The postseason bracket simulator (bracket_sim.py, method bracket_v1) on
FIXTURE brackets only (docs/betting-2026-10/BRACKET_SIM_GATE.md section 14: no
test computes a number from the real 2026 bracket).

What is pinned here:
  1. the series recursion: a 2-0 Wild Card lead is decided, a 3-3 seventh game
     is the game-seven probability, the best-of-three closed form;
  2. the bracket state: a decided series advances it, a sweep that removes the
     if-necessary games changes nothing, a placeholder never resolves;
  3. the 6.3 checks: P(title) totals 1, P(pennant) totals 1 per league, round
     sums equal the series counts, nothing rises from round to round;
  4. the board conditions of 3.1, each named when it fails;
  5. the forward record: first write wins, append-only, chain-hashed, the write
     guard refuses an edit, a shorter record or an earlier date, the replay test;
  6. the daily step end to end under tmp paths, including the crash protocol.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import bracket_sim as bs  # noqa: E402

UTC = dt.timezone.utc

# ---------------------------------------------------------------------------
# a fixture league: 30 clubs, final standings, a posted bracket
# ---------------------------------------------------------------------------
DIVS = {
    (103, 201): [("TBR", 139, 98, 64), ("NYY", 147, 93, 69), ("BOS", 111, 88, 74),
                 ("BAL", 110, 80, 82), ("TOR", 141, 78, 84)],
    (103, 202): [("CLE", 114, 90, 72), ("CHW", 145, 86, 76), ("MIN", 142, 77, 85),
                 ("DET", 116, 76, 86), ("KCR", 118, 70, 92)],
    (103, 200): [("HOU", 117, 85, 77), ("TEX", 140, 80, 82), ("SEA", 136, 76, 86),
                 ("ATH", 133, 64, 98), ("LAA", 108, 62, 100)],
    (104, 204): [("ATL", 144, 92, 70), ("PHI", 143, 88, 74), ("MIA", 146, 80, 82),
                 ("WSN", 120, 77, 85), ("NYM", 121, 74, 88)],
    (104, 205): [("MIL", 158, 100, 62), ("CHC", 112, 89, 73), ("PIT", 134, 82, 80),
                 ("STL", 138, 77, 85), ("CIN", 113, 75, 87)],
    (104, 203): [("LAD", 119, 97, 65), ("SDP", 135, 91, 71), ("ARI", 109, 86, 76),
                 ("SFG", 137, 65, 97), ("COL", 115, 58, 104)],
}
TEAM_ID = {org: tid for rows in DIVS.values() for org, tid, _w, _lost in rows}
VENUE = {org: 9000 + i for i, org in enumerate(sorted(TEAM_ID))}


def standings_records(divs=None):
    recs = []
    for (lg, dv), rows in (divs or DIVS).items():
        trs = []
        for i, (org, tid, w, lost) in enumerate(rows):
            trs.append({"team": {"id": tid, "name": org}, "wins": w, "losses": lost,
                        "divisionRank": str(i + 1), "clinchIndicator": "y" if i == 0 else None})
        recs.append({"league": {"id": lg}, "division": {"id": dv}, "teamRecords": trs})
    return recs


#: (series id, round, league, description, higher-seed source, lower-seed source)
#: a source is a club code or ("winner", series id)
LAYOUT = [
    ("F_1", "F", "AL", "AL Wild Card Series", "HOU", "CHW"),
    ("F_2", "F", "AL", "AL Wild Card Series", "NYY", "BOS"),
    ("F_3", "F", "NL", "NL Wild Card Series", "ATL", "PHI"),
    ("F_4", "F", "NL", "NL Wild Card Series", "SDP", "CHC"),
    ("D_1", "D", "AL", "AL Division Series", "TBR", ("winner", "F_2")),
    ("D_2", "D", "AL", "AL Division Series", "CLE", ("winner", "F_1")),
    ("D_3", "D", "NL", "NL Division Series", "MIL", ("winner", "F_4")),
    ("D_4", "D", "NL", "NL Division Series", "LAD", ("winner", "F_3")),
    ("L_1", "L", "AL", "AL Championship Series", ("winner", "D_1"), ("winner", "D_2")),
    ("L_2", "L", "NL", "NL Championship Series", ("winner", "D_3"), ("winner", "D_4")),
    ("W_1", "W", None, "World Series", ("winner", "L_1"), ("winner", "L_2")),
]
SEED = {"TBR": 1, "CLE": 2, "HOU": 3, "NYY": 4, "BOS": 5, "CHW": 6,
        "MIL": 1, "LAD": 2, "ATL": 3, "SDP": 4, "CHC": 5, "PHI": 6}
WPCT = {o: (w, lost) for rows in DIVS.values() for o, _t, w, lost in rows}


#: Each round's game k is dated ROUND_BASE + k days.
ROUND_BASE = {"F": dt.date(2026, 9, 28), "D": dt.date(2026, 10, 3),
              "L": dt.date(2026, 10, 11), "W": dt.date(2026, 10, 20)}


def _team(org):
    return {"id": TEAM_ID[org], "name": org, "venue": {"id": VENUE[org]}}


def _placeholder(name, pid):
    return {"id": pid, "name": name}


def build_payloads(results: dict, *, drop_unneeded: bool = True, extra: dict | None = None):
    """(series payload, schedule payload) for the fixture bracket.

    `results` maps a series id to the winners of its played games, in order.
    An unneeded if-necessary game is deleted (MLB's practice) unless
    drop_unneeded is False."""
    winners = {}
    out_series, all_games = [], []
    pk = 700000
    for sid, rnd, lg, desc, hi_src, lo_src in LAYOUT:
        def resolve(src, slot):
            if isinstance(src, str):
                return src
            w = winners.get(src[1])
            return w
        hi, lo = resolve(hi_src, "hi"), resolve(lo_src, "lo")
        if rnd == "D" and lo is None:
            f = next(x for x in LAYOUT if x[0] == lo_src[1])
            lo_team = _placeholder(f"{f[4]}/{f[5]}", 5500 + int(sid[-1]))
        elif lo is None:
            lo_team = _placeholder(f"{lg or ''} Lower Seed".strip(), 5600 + len(out_series))
        else:
            lo_team = _team(lo)
        if rnd in ("L", "W") and (hi is None or lo is None):
            hi_team = _placeholder(f"{lg or ''} Higher Seed".strip(), 5700 + len(out_series))
            lo_team = _placeholder(f"{lg or ''} Lower Seed".strip(), 5600 + len(out_series))
            hi = lo = None
        else:
            if rnd in ("L", "W") and hi and lo:
                if rnd == "L" and SEED[lo] < SEED[hi]:
                    hi, lo = lo, hi
                if rnd == "W":
                    a, b = WPCT[hi], WPCT[lo]
                    if b[0] * (a[0] + a[1]) > a[0] * (b[0] + b[1]):
                        hi, lo = lo, hi
                lo_team = _team(lo)
            hi_team = _team(hi)
        played = list(results.get(sid) or [])
        need = bs.ROUND_NEED[rnd]
        length = bs.ROUND_LENGTH[rnd]
        wins = {}
        games = []
        decided_at = None
        for k in range(1, length + 1):
            host_hi = bs.HOST_TABLE[rnd][k - 1] == 1
            home, away = (hi_team, lo_team) if host_hi else (lo_team, hi_team)
            day = (ROUND_BASE[rnd] + dt.timedelta(days=k)).isoformat()
            g = {"gamePk": pk, "gameType": rnd, "seriesGameNumber": k, "gamesInSeries": length,
                 "seriesDescription": desc, "officialDate": day,
                 "gameDate": f"{day}T23:00:00Z",
                 "ifNecessary": "Y" if k > need else "N",
                 "venue": {"id": home.get("venue", {}).get("id", 3000 + k)},
                 "status": {"codedGameState": "S"},
                 "teams": {"home": {"team": home}, "away": {"team": away}}}
            pk += 1
            if k <= len(played):
                w = played[k - 1]
                g["status"] = {"codedGameState": "F"}
                g["teams"]["home"]["isWinner"] = home.get("name") == w
                g["teams"]["away"]["isWinner"] = away.get("name") == w
                g["teams"]["home"]["score"] = 5 if home.get("name") == w else 2
                g["teams"]["away"]["score"] = 5 if away.get("name") == w else 2
                wins[w] = wins.get(w, 0) + 1
                if wins[w] >= need and decided_at is None:
                    decided_at = k
                    winners[sid] = w
            if decided_at is not None and k > decided_at and drop_unneeded:
                continue
            games.append(g)
        out_series.append({"series": {"id": sid}, "games": games})
        all_games.extend(games)
    sched = {"dates": [{"date": "x", "games": [copy.deepcopy(g) for g in all_games]}]}
    return {"series": out_series}, sched


def elo_games():
    """A tiny regular season over all 30 clubs, so the walk has every club."""
    orgs = sorted(TEAM_ID)
    rows = []
    for i, h in enumerate(orgs):
        a = orgs[(i + 1) % len(orgs)]
        rows.append({"game_pk": 1000 + i, "date": f"2026-04-{1 + i % 28:02d}", "home_org": h,
                     "away_org": a, "home_runs": 3 + (i % 3), "away_runs": 2 + (i % 4)})
    return rows


NOW = dt.datetime(2026, 10, 12, 7, 10, tzinfo=UTC)


def make_state(results, board=None, *, drop_unneeded=True):
    sp, sc = build_payloads(results, drop_unneeded=drop_unneeded)
    series = bs.parse_bracket(sp, sc)
    seeding = bs.derive_seeds(series, standings_records())
    structure = bs.build_structure(series, seeding)
    head = bs.build_header(2026, NOW, "local", structure, games=elo_games())
    entry = bs.build_entry(series, seeding, structure, board, head["elo"]["ratings"],
                           as_of="2026-10-12", now=NOW, machine="local")
    return series, seeding, structure, head, entry


WC_OPEN = {"F_1": ["CHW", "CHW"], "F_2": ["NYY", "NYY"], "F_3": ["ATL", "PHI"],
           "F_4": ["SDP", "SDP"]}


# ---------------------------------------------------------------------------
# 1. the series recursion
# ---------------------------------------------------------------------------
def test_best_of_three_matches_its_closed_form():
    p = 0.6
    games = [[k, "AAA", p, "prior", "", None] for k in (1, 2, 3)]
    got = bs.series_win_prob(games, "AAA", 2, 0, 0)
    assert abs(got - p * p * (3 - 2 * p)) < 1e-15
    assert abs(bs.series_win_prob(games, "BBB", 2, 0, 0) - (1 - got)) < 1e-15


def test_a_three_three_seventh_game_is_the_game_seven_probability():
    games = [[k, "AAA" if k in (1, 2, 6, 7) else "BBB", 0.5 + k / 100, "prior", "", None]
             for k in range(1, 8)]
    assert bs.series_win_prob(games, "AAA", 4, 3, 3) == games[6][2]
    assert bs.series_win_prob(games, "BBB", 4, 3, 3) == 1.0 - games[6][2]


def test_a_two_nil_wild_card_lead_is_decided_and_never_simulated():
    series, _sd, structure, _h, entry = make_state(WC_OPEN)
    f4 = next(s for s in structure if s["id"] == "F_4")
    assert f4["decided"] and f4["winner"] == "SDP" and f4["loser"] == "CHC"
    assert f4["wins"] == {"CHC": 0, "SDP": 2}
    assert not any(r["series"] == "F_4" for r in entry["inputs"])
    out = entry["outputs"]["clubs"]
    assert out["SDP"]["adv"]["F"] == 1.0
    assert all(v == 0.0 for v in out["CHC"]["adv"].values())


def test_a_decided_series_advances_the_state():
    _s, _sd, st_a, _h, a = make_state(WC_OPEN)
    _s, _sd, st_b, _h, b = make_state({**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"]})
    d4a = next(s for s in st_a if s["id"] == "D_4")
    d4b = next(s for s in st_b if s["id"] == "D_4")
    assert d4a["posted_clubs"] == ["LAD"] and d4a["placeholders"] == ["ATL/PHI"]
    assert d4b["posted_clubs"] == ["ATL", "LAD"]
    pa, pb = a["outputs"]["clubs"], b["outputs"]["clubs"]
    assert 0.0 < pa["PHI"]["adv"]["F"] < 1.0
    assert pb["ATL"]["adv"]["F"] == 1.0
    assert all(v == 0.0 for v in pb["PHI"]["adv"].values())
    assert pb["PHI"]["status"] == "eliminated" and pb["PHI"]["eliminated_in"] == "F"
    # D_4 is now one posted pair, not a pair per possible opponent
    assert len([r for r in b["inputs"] if r["series"] == "D_4"]) == 1
    assert len([r for r in a["inputs"] if r["series"] == "D_4"]) == 2


def test_a_played_game_moves_the_series_start_state():
    _s, _sd, _st, _h, a = make_state({**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"]})
    _s, _sd, _st, _h, b = make_state({**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"],
                                      "D_4": ["LAD"]})
    ra = next(r for r in a["inputs"] if r["series"] == "D_4")
    rb = next(r for r in b["inputs"] if r["series"] == "D_4")
    assert ra["start"] == [0, 0] and [g[0] for g in ra["variants"][0]["games"]] == [1, 2, 3, 4, 5]
    assert rb["pair"] == ["LAD", "ATL"] and rb["start"] == [1, 0]
    assert [g[0] for g in rb["variants"][0]["games"]] == [2, 3, 4, 5]


def test_a_sweep_that_removes_the_if_necessary_games_changes_nothing():
    res = {**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"], "D_1": ["TBR", "TBR", "TBR"]}
    _s, _sd, st_a, _h, a = make_state(res, drop_unneeded=True)
    _s, _sd, st_b, _h, b = make_state(res, drop_unneeded=False)
    d1a = next(s for s in st_a if s["id"] == "D_1")
    d1b = next(s for s in st_b if s["id"] == "D_1")
    assert len(d1a["games"]) == 3 and len(d1b["games"]) == 5
    assert d1a["decided"] and d1a["winner"] == "TBR"
    assert json.dumps(a["outputs"], sort_keys=True) == json.dumps(b["outputs"], sort_keys=True)
    # the swept series is never simulated, so its deleted games are never needed
    assert not any(r["series"] == "D_1" for r in a["inputs"])


def test_a_placeholder_never_resolves_and_an_unknown_club_crashes():
    sp, sc = build_payloads(WC_OPEN)
    series = bs.parse_bracket(sp, sc)
    w = next(s for s in series if s["id"] == "W_1")
    assert w["posted_clubs"] == [] and w["placeholders"]
    bad = copy.deepcopy(sp)
    bad["series"][0]["games"][0]["teams"]["home"]["team"] = {"id": 424242, "name": "Springfield Isotopes"}
    with pytest.raises(bs.BracketCrash, match="does not resolve"):
        bs.parse_bracket(bad, {"dates": []})


# ---------------------------------------------------------------------------
# 2. seeds and the format
# ---------------------------------------------------------------------------
def test_seeds_are_read_off_the_bracket_and_agree_with_the_standings():
    _s, seeding, _st, _h, _e = make_state(WC_OPEN)
    assert seeding["seeds"]["AL"] == {"1": "TBR", "2": "CLE", "3": "HOU", "4": "NYY",
                                      "5": "BOS", "6": "CHW"}
    assert seeding["seeds"]["NL"] == {"1": "MIL", "2": "LAD", "3": "ATL", "4": "SDP",
                                      "5": "CHC", "6": "PHI"}


def test_a_seed_that_disagrees_with_the_standings_crashes():
    divs = copy.deepcopy(DIVS)
    # TEX now out-records the sixth seed and is not in the bracket
    divs[(103, 200)][1] = ("TEX", 140, 95, 67)
    sp, sc = build_payloads(WC_OPEN)
    series = bs.parse_bracket(sp, sc)
    with pytest.raises(bs.BracketCrash, match="out-records seed 6|division champions|worse record"):
        bs.derive_seeds(series, standings_records(divs))


def test_hosts_follow_the_format_table():
    _s, _sd, _st, _h, e = make_state({**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"]})
    l1 = [r for r in e["inputs"] if r["series"] == "L_1"]
    for r in l1:
        x, y = r["pair"]
        hf = x if SEED[x] < SEED[y] else y
        v = r["variants"][0]
        assert v["home_field"] == hf
        hosts = [g[1] for g in v["games"]]
        other = y if hf == x else x
        assert hosts == [hf, hf, other, other, other, hf, hf]
    w = [r for r in e["inputs"] if r["series"] == "W_1"]
    for r in w:
        x, y = r["pair"]
        (wx, lx), (wy, ly) = WPCT[x], WPCT[y]
        c = wx * (wy + ly) - wy * (wx + lx)
        if c == 0:
            assert [v["weight"] for v in r["variants"]] == [0.5, 0.5]
        else:
            assert r["variants"][0]["home_field"] == (x if c > 0 else y)


def test_an_equal_record_world_series_weights_home_field_one_half():
    divs = copy.deepcopy(DIVS)
    divs[(104, 205)][0] = ("MIL", 158, 98, 64)          # MIL now level with TBR
    sp, sc = build_payloads(WC_OPEN)
    series = bs.parse_bracket(sp, sc)
    seeding = bs.derive_seeds(series, standings_records(divs))
    structure = bs.build_structure(series, seeding)
    head = bs.build_header(2026, NOW, "local", structure, games=elo_games())
    e = bs.build_entry(series, seeding, structure, None, head["elo"]["ratings"],
                       as_of="2026-10-12", now=NOW, machine="local")
    tie = [r for r in e["inputs"] if r["series"] == "W_1" and set(r["pair"]) == {"TBR", "MIL"}]
    assert len(tie) == 1 and [v["weight"] for v in tie[0]["variants"]] == [0.5, 0.5]
    assert any(t["pair"] == ["TBR", "MIL"] for t in e["ws_home_ties"])
    assert e["outputs"]["checks"]["passed"]


def test_the_prior_is_the_literature_elo_with_its_home_term():
    assert abs(bs.elo_win_prob(1500.0, 1500.0, 24.0) - 1 / (1 + 10 ** (-0.06))) < 1e-15
    assert abs(bs.elo_win_prob(1500.0, 1500.0, 24.0) - 0.5345) < 1e-4
    assert bs.elo_win_prob(1500.0, 1500.0, 0.0) == 0.5


# ---------------------------------------------------------------------------
# 3. the 6.3 checks
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("results", [
    {},
    WC_OPEN,
    {**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"], "D_1": ["NYY", "TBR"], "D_4": ["ATL"]},
    {"F_1": ["CHW", "CHW"], "F_2": ["NYY", "NYY"], "F_3": ["PHI", "PHI"], "F_4": ["SDP", "SDP"],
     "D_1": ["TBR"] * 3, "D_2": ["CHW"] * 3, "D_3": ["MIL"] * 3, "D_4": ["PHI"] * 3,
     "L_1": ["TBR", "CHW", "TBR", "CHW", "TBR", "CHW"], "L_2": ["MIL"] * 4},
])
def test_totals_hold_on_every_state(results):
    _s, _sd, _st, _h, e = make_state(results)
    clubs = e["outputs"]["clubs"]
    assert len(clubs) == 12
    assert e["outputs"]["checks"]["passed"], e["outputs"]["checks"]
    title = math.fsum(c["adv"]["W"] for c in clubs.values())
    assert abs(title - 1.0) < 1e-5            # stored to six decimals
    for lg in ("AL", "NL"):
        assert abs(math.fsum(c["adv"]["L"] for c in clubs.values() if c["league"] == lg) - 1.0) < 1e-5
    for c in clubs.values():
        seq = [c["adv"][r] for r in bs.ROUNDS if r in c["adv"]]
        assert all(seq[i + 1] <= seq[i] + 1e-6 for i in range(len(seq) - 1))
        assert c["pennant_pct"] == c["adv"]["L"] and c["ws_pct"] == c["adv"]["W"]


def test_a_failed_check_is_a_crash_not_a_number():
    _s, seeding, structure, _h, e = make_state(WC_OPEN)
    bent = copy.deepcopy(e["inputs"])
    f3 = next(r for r in bent if r["series"] == "F_3")
    for g in f3["variants"][0]["games"]:
        g[2] = 2.0                                          # not a probability
    got = bs.outputs_from(structure, bent, seeding)
    assert not got["checks"]["passed"]


# ---------------------------------------------------------------------------
# 4. the board conditions of 3.1
# ---------------------------------------------------------------------------
def _card(pk, home, away, p=0.61, gt="F"):
    return {"game_pk": pk, "game_type": gt, "postseason_label": "never graded on a postseason game",
            "home": {"org": home}, "away": {"org": away}, "model": {"p_home": p}}


def _f3_game3_pk():
    sp, _sc = build_payloads(WC_OPEN)
    f3 = next(s for s in sp["series"] if s["series"]["id"] == "F_3")
    return next(g["gamePk"] for g in f3["games"] if g["seriesGameNumber"] == 3)


def test_the_board_number_is_taken_verbatim_when_every_condition_holds():
    pk = _f3_game3_pk()
    board = {"generated_at": "2026-10-12T07:00:00+00:00", "team_bets": [_card(pk, "ATL", "PHI")]}
    _s, _sd, _st, _h, e = make_state(WC_OPEN, board)
    r = next(r for r in e["inputs"] if r["series"] == "F_3")
    g = r["variants"][0]["games"][0]
    assert g[:4] == [3, "ATL", 0.61, "board"] and g[5] == pk
    assert g[4] == {"board_generated_at": "2026-10-12T07:00:00+00:00",
                    "postseason_label": "never graded on a postseason game"}


@pytest.mark.parametrize("card,cond", [
    (lambda pk: _card(pk, "PHI", "ATL"), "condition 3"),
    (lambda pk: _card(pk, "ATL", "PHI", gt="R"), "condition 2"),
    (lambda pk: _card(pk, "ATL", "PHI", p=1.0), "condition 4"),
    (lambda pk: _card(pk + 99999, "ATL", "PHI"), "condition 1"),
])
def test_a_failed_board_condition_falls_to_the_prior_and_is_named(card, cond):
    pk = _f3_game3_pk()
    board = {"generated_at": "x", "team_bets": [card(pk)]}
    _s, _sd, _st, _h, e = make_state(WC_OPEN, board)
    g = next(r for r in e["inputs"] if r["series"] == "F_3")["variants"][0]["games"][0]
    assert g[3] == "prior" and g[4].startswith(cond), g


def test_a_hypothetical_game_reads_the_prior():
    _s, _sd, _st, _h, e = make_state(WC_OPEN)
    g = next(r for r in e["inputs"] if r["series"] == "W_1")["variants"][0]["games"][0]
    assert g[3] == "prior" and g[5] is None and g[4] == "no posted game with both clubs"


# ---------------------------------------------------------------------------
# 5. the forward record
# ---------------------------------------------------------------------------
@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "RECORD_PATH", tmp_path / "cache" / "record.json")
    monkeypatch.setattr(bs, "RECORD_DERIVED_PATH", tmp_path / "data" / "bracket_sim_record.json")
    monkeypatch.setattr(bs, "OUT_PATH", tmp_path / "data" / "bracket_sim.json")
    monkeypatch.setattr(bs, "FETCH_CACHE_DIR", tmp_path / "fetch")
    monkeypatch.setattr(bs, "BOARD_PATH", tmp_path / "data" / "betting.json")
    monkeypatch.setattr(bs, "FUTURES_PATH", tmp_path / "data" / "futures.json")
    monkeypatch.setattr(bs, "STANDINGS_DIR", tmp_path)
    (tmp_path / "statsapi_standings_2026.json").write_text(
        json.dumps({"records": standings_records()}), encoding="utf-8")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "futures.json").write_text(json.dumps({
        "generated_at": "2026-10-12T07:00:00+00:00", "season": 2026,
        "as_of_note": "As of the end of the regular season (2026-10-12): stamp"}), encoding="utf-8")
    import betting_model as bm
    monkeypatch.setattr(bm, "completed_games", lambda season=None, refresh=True: elo_games())
    return tmp_path


def _fetcher(results):
    sp, sc = build_payloads(results)

    def f(url, params):
        return copy.deepcopy(sp if url == bs.SERIES_URL else sc)
    return f


def _boom(url, params):
    raise OSError("network down")


def test_first_run_freezes_the_header_and_one_entry(paths):
    got = bs.run(now=NOW, fetch=_fetcher(WC_OPEN), machine="local")
    assert got["ok"] and got["wrote_entry"] and got["state"] == "live"
    rec = json.loads(bs.RECORD_PATH.read_text(encoding="utf-8"))
    assert bs.RECORD_DERIVED_PATH.read_text(encoding="utf-8") == bs.RECORD_PATH.read_text(encoding="utf-8")
    head = rec["header"]
    assert head["elo"]["n_games"] == 30 and len(head["elo"]["ratings"]) == 30
    assert head["decided_at_start"] == [{"series": "F_1", "winner": "CHW", "loser": "HOU"},
                                        {"series": "F_2", "winner": "NYY", "loser": "BOS"},
                                        {"series": "F_4", "winner": "SDP", "loser": "CHC"}]
    assert [e["as_of"] for e in rec["entries"]] == ["2026-10-12"]
    assert rec["entries"][0]["machine"] == "local" and rec["entries"][0]["late"] is False
    doc = json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    assert doc["serve"]["on"] is True and doc["as_of"] == "2026-10-12"
    assert doc["label"] == "implied, no market"
    assert doc["serve"]["line"] == ("Pennant and World Series: implied by the postseason "
                                    "bracket simulator as of 2026-10-12, no market.")
    assert "Division, Playoffs, Bye, Proj W and Win band" in doc["serve"]["division_columns_note"]
    assert doc["record"]["n_days"] == 1 and doc["record"]["n_scored"] == 0
    # the page serves the frozen entry, number for number
    frozen = rec["entries"][0]["outputs"]["clubs"]
    for c in doc["clubs"]:
        assert c["ws_pct"] == frozen[c["team"]]["ws_pct"]


def test_a_same_day_rerun_writes_nothing(paths):
    bs.run(now=NOW, fetch=_fetcher(WC_OPEN), machine="local")
    before = bs.RECORD_PATH.read_bytes()
    later = NOW + dt.timedelta(hours=10)
    got = bs.run(now=later, fetch=_fetcher({**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"]}),
                 machine="local")
    assert got["wrote_entry"] is False and got["ok"]
    assert bs.RECORD_PATH.read_bytes() == before
    doc = json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    assert doc["as_of"] == "2026-10-12"
    assert next(c for c in doc["clubs"] if c["team"] == "PHI")["ws_pct"] > 0


def test_the_record_is_append_only_and_chained(paths):
    bs.run(now=NOW, fetch=_fetcher(WC_OPEN), machine="local")
    bs.run(now=NOW + dt.timedelta(days=1), fetch=_fetcher({**WC_OPEN, "F_3": ["ATL", "PHI", "ATL"]}),
           machine="box")
    rec = json.loads(bs.RECORD_PATH.read_text(encoding="utf-8"))
    e0, e1 = rec["entries"]
    assert e0["prev_sha256"] == rec["header"]["sha256"] and e1["prev_sha256"] == e0["sha256"]
    assert [e["machine"] for e in rec["entries"]] == ["local", "box"]
    bs.verify_record(rec)
    for e in rec["entries"]:
        assert bs.replay(e), "a stored entry does not reproduce from its own inputs"


def test_the_write_guard_refuses_an_edit_a_shorter_record_and_an_earlier_date(paths):
    bs.run(now=NOW, fetch=_fetcher(WC_OPEN), machine="local")
    rec = json.loads(bs.RECORD_PATH.read_text(encoding="utf-8"))
    edited = copy.deepcopy(rec)
    edited["entries"][0]["outputs"]["clubs"]["ATL"]["ws_pct"] = 0.5
    with pytest.raises(bs.BracketCrash):
        bs.verify_record(edited)
    shorter = {"header": rec["header"], "entries": []}
    with pytest.raises(bs.BracketCrash, match="not one more"):
        bs.guard_append(rec, shorter)
    earlier = bs.crash_entry("2026-10-11", NOW, "local", "x")
    with pytest.raises(bs.BracketCrash):
        bs.append_entry(rec, earlier)
    same = bs.crash_entry("2026-10-12", NOW, "local", "x")
    with pytest.raises(bs.BracketCrash):
        bs.append_entry(rec, same)
    assert json.loads(bs.RECORD_PATH.read_text(encoding="utf-8")) == rec


def test_replay_reproduces_outputs_byte_for_byte_and_catches_a_drift():
    _s, _sd, _st, _h, e = make_state({**WC_OPEN, "D_3": ["MIL", "SDP"]})
    assert bs.replay(e)
    drift = copy.deepcopy(e)
    drift["inputs"][0]["variants"][0]["games"][0][2] += 0.01
    assert not bs.replay(drift)


def test_a_crash_writes_a_crash_entry_with_no_numbers_and_the_page_says_so(paths):
    bs.run(now=NOW, fetch=_fetcher(WC_OPEN), machine="local")
    # next day, the network is down; games were scheduled before now
    got = bs.run(now=NOW + dt.timedelta(days=1), fetch=_boom, machine="local")
    assert not got["ok"] and got["state"] == "not_updated"
    rec = json.loads(bs.RECORD_PATH.read_text(encoding="utf-8"))
    crash = rec["entries"][-1]
    assert crash["kind"] == "crash" and "network down" in crash["reason"]
    assert "outputs" not in crash and "inputs" not in crash
    doc = json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    assert doc["serve"]["on"] is False and doc["clubs"] == []
    assert doc["serve"]["not_updated_note"] == "The postseason odds did not update on 2026-10-13."
    assert doc["record"]["n_crash_days"] == 1


def test_a_crash_before_the_next_game_serves_the_last_good_entry(paths):
    # the next unplayed game (F_3 game 3) starts 2026-10-01T23:00Z
    early = dt.datetime(2026, 9, 30, 7, 10, tzinfo=UTC)
    bs.run(now=early, fetch=_fetcher(WC_OPEN), machine="local")
    got = bs.run(now=early + dt.timedelta(days=1), fetch=_boom, machine="local")
    assert got["state"] == "last_good"
    doc = json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    assert doc["serve"]["on"] is True and doc["as_of"] == "2026-09-30"


def test_the_flag_off_keeps_the_record_running_dark(paths, monkeypatch):
    monkeypatch.setattr(bs, "SERVE_BRACKET_SIM", False)
    got = bs.run(now=NOW, fetch=_fetcher(WC_OPEN), machine="local")
    assert got["wrote_entry"]
    doc = json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    assert doc["serve"]["on"] is False and doc["serve"]["state"] == "off"


def test_no_bracket_posted_is_idle_and_writes_no_entry(paths):
    got = bs.run(now=NOW, fetch=lambda u, p: {"series": []} if u == bs.SERIES_URL else {"dates": []},
                 machine="local")
    assert got["state"] == "idle" and got["ok"] and not bs.RECORD_PATH.exists()


def test_the_world_series_final_is_the_last_entry(paths):
    done = {"F_1": ["CHW", "CHW"], "F_2": ["NYY", "NYY"], "F_3": ["PHI", "PHI"],
            "F_4": ["SDP", "SDP"], "D_1": ["TBR"] * 3, "D_2": ["CHW"] * 3, "D_3": ["MIL"] * 3,
            "D_4": ["PHI"] * 3, "L_1": ["TBR"] * 4, "L_2": ["MIL"] * 4, "W_1": ["MIL"] * 4}
    got = bs.run(now=NOW, fetch=_fetcher(done), machine="local")
    assert got["state"] == "final"
    doc = json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    mil = next(c for c in doc["clubs"] if c["team"] == "MIL")
    assert mil["ws_pct"] == 1.0 and mil["status"] == "champion"
    got2 = bs.run(now=NOW + dt.timedelta(days=1), fetch=_boom, machine="local")
    assert got2["state"] == "final" and not got2["wrote_entry"]
    assert len(json.loads(bs.RECORD_PATH.read_text(encoding="utf-8"))["entries"]) == 1


# ---------------------------------------------------------------------------
# 6. what the payload never carries
# ---------------------------------------------------------------------------
BANNED_KEYS = {"pennants", "titles", "edge", "kelly", "ev", "fair", "american",
               "implied_american", "price", "odds_american", "decimal_odds"}


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def test_the_payload_carries_no_price_edge_or_forbidden_key(paths):
    bs.run(now=NOW, fetch=_fetcher(WC_OPEN), machine="local")
    doc = json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    rec = json.loads(bs.RECORD_PATH.read_text(encoding="utf-8"))
    for blob in (doc, rec):
        bad = {k for k in _keys(blob) if k.lower() in BANNED_KEYS or "american" in k.lower()}
        assert not bad, bad
