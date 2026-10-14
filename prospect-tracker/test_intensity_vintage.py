# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The game-intensity dark builder (intensity_vintage.py and its seam in
leaderboard_vintages), pinned to its section by TITLE and column names, never by a
letter or a literal schema number.

docs/diamond-betting.md, "Game intensity: stakes, matchup quality and the
postseason": team columns ix_elo, ix_po_pct, ix_ws_pct, ix_proj_wins; a game block
ix_games keyed by game_pk for the three dates after the vintage; a basis per record;
six rules (old records None; inputs_as_of never fills; a game missing from its pricing
vintage's block is a stated null; N1 never reconstructs; a construction change is
recorded the same day; postseason nights accrue). Its "### Builder landed" amendment
names the schema number and the construction hash.

Every fixture is synthetic: no real game is read, computed, related to an outcome or
priced here. Simulation counts are small so the file runs in seconds.
"""
from __future__ import annotations

import ast
import functools
import random
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import betting_model as bm
import intensity_core as ic
import intensity_vintage as iv
import leaderboard_vintages as lv
from test_betting_intensity_registration import TITLE, _norm, _section

ROOT = Path(__file__).resolve().parent
_REAL_BUILD_COLUMNS = iv.build_columns

V = "2026-08-20"                       # the fixture vintage date
VP = "2026-10-20"                      # the postseason fixture's vintage date
SIMS = 200
SEED = 7

SECTION_GAME_FIELDS = ("date", "game_type", "series_state", "dpo_h", "dpo_a", "dws_h",
                       "dws_a", "G", "G_se", "S", "Q", "A", "home_sp", "away_sp", "D",
                       "R", "ii")
SECTION_BASIS_KEYS = ("simulations", "seed", "schedule_source", "remaining_pairs",
                      "standings_games_read", "postseason_format", "g_ref",
                      "construction_hash")


# ---------------------------------------------------------------------------
# fixtures: a synthetic thirty-club season
# ---------------------------------------------------------------------------
def _divisions() -> dict:
    import proj_current as pc
    return {o: (dv.split("_")[0], dv) for dv, members in pc._DIVISIONS.items()
            for o in members}


def _ids() -> dict:
    from trades import _org_by_id
    return {org: tid for tid, org in dict(_org_by_id()).items()}


def _days(d0: str, k: int) -> str:
    return (date.fromisoformat(d0) + timedelta(days=k)).isoformat()


def _regular_inputs(*, extra_finals: list | None = None) -> dict:
    """120 finals before V, 60 scheduled games from V on (three a day), one game
    dated before V the results cache never booked, a postponed listing, and the
    three window dates listed with probables."""
    rng = random.Random(11)
    divs = _divisions()
    orgs = sorted(divs)
    finals, schedule, pk = [], [], 700000
    for k in range(120):
        h, a = rng.sample(orgs, 2)
        d = _days("2026-08-01", k // 7)
        pk += 1
        hr, ar = rng.randint(0, 9), rng.randint(0, 9)
        if hr == ar:
            hr += 1
        finals.append({"game_pk": pk, "season": "2026", "date": d, "home_org": h,
                       "away_org": a, "home_runs": hr, "away_runs": ar})
        schedule.append({"game_pk": pk, "date": d, "game_type": "R", "home": h,
                         "away": a, "state": "Final", "coded": "F"})
    pk += 1                                       # dated before V, never booked
    schedule.append({"game_pk": pk, "date": "2026-08-19", "game_type": "R",
                     "home": "NYY", "away": "BOS", "state": "Final", "coded": "F"})
    listed = []
    for k in range(60):
        h, a = rng.sample(orgs, 2)
        d = _days(V, k // 3)
        pk += 1
        schedule.append({"game_pk": pk, "date": d, "game_type": "R", "home": h,
                         "away": a, "state": "Scheduled", "coded": "S"})
        if d in iv.window(V):
            listed.append({"game_pk": pk, "date": d, "game_type": "R", "home": h,
                           "away": a, "state": "Scheduled", "coded": "S",
                           "home_sp": 1000 + k, "away_sp": 2000 + k})
    # a listing postponed at capture (skipped) and one outside the window (dropped)
    listed[0] = dict(listed[0], home_sp=None)
    schedule.append({"game_pk": 799001, "date": _days(V, 2), "game_type": "R",
                     "home": "SEA", "away": "TEX", "state": "Postponed", "coded": "D"})
    listed.append({"game_pk": 799001, "date": _days(V, 2), "game_type": "R",
                   "home": "SEA", "away": "TEX", "state": "Postponed", "coded": "D",
                   "home_sp": None, "away_sp": None})
    listed.append({"game_pk": 799002, "date": _days(V, 5), "game_type": "R",
                   "home": "SEA", "away": "TEX", "state": "Scheduled", "coded": "S",
                   "home_sp": None, "away_sp": None})
    # a listed game the season schedule does not carry: a stated null
    listed.append({"game_pk": 799003, "date": _days(V, 1), "game_type": "R",
                   "home": "LAD", "away": "SFG", "state": "Scheduled", "coded": "S",
                   "home_sp": 1, "away_sp": 2})
    return {"season": 2026, "divisions": divs,
            "finals": finals + list(extra_finals or []),
            "season_schedule": schedule, "listed": listed,
            "schedule_source": iv.SOURCE_LIVE, "post_finals": None, "standings": []}


def _board(inputs: dict) -> dict:
    out = {}
    for g in inputs["listed"]:
        for k in ("home_sp", "away_sp"):
            if g.get(k) is not None and g[k] >= 1000:
                out[g[k]] = 80.0 + (g[k] % 50)
    return out


def _standings(seeds: dict, divs: dict) -> list:
    """StatsAPI-shaped standings records: seeds 1 to 3 division winners, 4 to 6 the
    wild cards, everyone else after them."""
    ids = _ids()
    out = []
    for lg, league_id in (("AL", 103), ("NL", 104)):
        order = list(seeds[lg]) + sorted(o for o in divs if divs[o][0] == lg
                                         and o not in seeds[lg])
        recs = []
        for i, o in enumerate(order):
            recs.append({"team": {"id": ids[o], "name": o},
                         "divisionRank": "1" if i < 3 else "3",
                         "leagueRank": str(i + 1),
                         "wildCardRank": None if i < 3 else str(i - 2)})
        out.append({"league": {"id": league_id}, "teamRecords": recs})
    return out


def _postseason_inputs(*, through_round: str, ws_state=(3, 3)) -> tuple[dict, dict]:
    """A finished regular season (every scheduled game booked), final standings, and
    postseason finals in which the higher seed wins every series before
    `through_round`; the World Series stands at `ws_state` when through_round is W."""
    divs = _divisions()
    orgs = sorted(divs)
    rng = random.Random(5)
    finals, schedule, pk = [], [], 600000
    for k in range(400):
        h, a = rng.sample(orgs, 2)
        pk += 1
        hr, ar = rng.randint(0, 9), rng.randint(0, 9)
        if hr == ar:
            hr += 1
        d = _days("2026-04-01", k // 15)
        finals.append({"game_pk": pk, "season": "2026", "date": d, "home_org": h,
                       "away_org": a, "home_runs": hr, "away_runs": ar})
        schedule.append({"game_pk": pk, "date": d, "game_type": "R", "home": h,
                         "away": a, "state": "Final", "coded": "F"})
    al = sorted(o for o in orgs if divs[o][0] == "AL")
    nl = sorted(o for o in orgs if divs[o][0] == "NL")
    seeds = {"AL": tuple(al[:6]), "NL": tuple(nl[:6])}
    post, gpk, d = [], 900000, "2026-10-01"

    def play(a, b, n_a, n_b):
        nonlocal gpk, d
        for _ in range(n_a):
            gpk += 1
            post.append({"game_pk": gpk, "date": d, "home": a, "away": b, "winner": a})
        for _ in range(n_b):
            gpk += 1
            post.append({"game_pk": gpk, "date": d, "home": a, "away": b, "winner": b})
        d = _days(d, 1)

    pennants = []
    for lg in ("AL", "NL"):
        s1, s2, s3, s4, s5, s6 = seeds[lg]
        play(s3, s6, 2, 0)
        play(s4, s5, 2, 0)
        play(s1, s4, 3, 0)
        play(s2, s3, 3, 0)
        if through_round == "L":
            continue
        play(s1, s2, 4, 0)
        pennants.append(s1)
    listed = []
    if through_round == "W":
        a, b = pennants
        play(a, b, ws_state[0], ws_state[1])
        listed.append({"game_pk": 990001, "date": _days(VP, 1), "game_type": "W",
                       "home": a, "away": b, "state": "Scheduled", "coded": "S",
                       "home_sp": 1001, "away_sp": 1002})
    else:
        lg = "AL"
        s1, s2 = seeds[lg][:2]
        listed.append({"game_pk": 990002, "date": _days(VP, 1), "game_type": "L",
                       "home": s1, "away": s2, "state": "Scheduled", "coded": "S",
                       "home_sp": 1001, "away_sp": 1002})
    # a postseason final dated on the vintage date: strictly-before drops it
    late = {"game_pk": 999999, "date": VP, "home": listed[0]["home"],
            "away": listed[0]["away"], "winner": listed[0]["away"]}
    inputs = {"season": 2026, "divisions": divs, "finals": finals,
              "season_schedule": schedule, "listed": listed,
              "schedule_source": iv.SOURCE_LIVE, "post_finals": post + [late],
              "standings": _standings(seeds, divs)}
    return inputs, seeds


# ---------------------------------------------------------------------------
# 1. the section, the names and the schema number, by title
# ---------------------------------------------------------------------------
def _landed() -> str:
    sec = _section()
    m = re.search(r"^### Builder landed (20\d\d-\d\d-\d\d)[^\n]*\n(.*?)(?=^### |\Z)", sec,
                  flags=re.M | re.S)
    assert m, f"the section titled {TITLE!r} has no dated '### Builder landed' amendment"
    return _norm(m.group(0))


def test_the_builder_landed_amendment_names_the_schema_number_the_code_carries():
    text = _landed()
    nums = {int(n) for n in re.findall(r"\bschema (\d+)\b", text)}
    assert lv.IX_SCHEMA in nums, (
        f"the amendment must name the schema the builder rides; code says {lv.IX_SCHEMA}")
    assert lv.IX_SCHEMA <= lv.SCHEMA
    for col in lv.IX_TEAM_COLUMNS + (lv.IX_GAMES_KEY,):
        assert f"`{col}`" in text, col
    assert "intensity_vintage.py" in text and "leaderboard_vintages" in text


def test_the_section_names_the_construction_hash_the_code_carries():
    """Rule 5: a construction change is recorded in the section the same day. The hash
    covers intensity_core.py; editing the core without a dated amendment naming the
    new hash fails here."""
    h = iv.construction_hash()
    assert re.fullmatch(r"[0-9a-f]{16}", h)
    assert f"`{h}`" in _section(), (
        f"intensity_core.py hashes to {h}; record the construction change in the "
        f"section by a dated amendment naming it")


def test_the_columns_are_the_registered_names_in_every_copy():
    cols = ("ix_elo", "ix_po_pct", "ix_ws_pct", "ix_proj_wins")
    assert lv.IX_TEAM_COLUMNS == cols == iv.TEAM_COLUMNS == bm.DARK_IX_TEAM_COLUMNS
    assert lv.IX_GAMES_KEY == iv.GAMES_KEY == "ix_games"
    # the starter-workload team column is appended after the intensity block
    through6 = tuple(c for c in lv.TEAM_COLUMNS if c not in lv.SW_TEAM_COLUMNS)
    assert through6[-len(cols):] == cols
    assert bm.DARK_TEAM_COLUMNS_BY_SCHEMA[lv.IX_SCHEMA] == cols
    sec = _section()
    for c in cols + ("ix_games",):
        assert f"`{c}`" in sec
    for c in cols:
        assert c in lv.FEATURE_SOURCES


def test_the_game_fields_and_the_basis_keys_are_the_sections_list():
    assert set(SECTION_GAME_FIELDS) <= set(iv.GAME_FIELDS)
    inputs = _regular_inputs()
    got = iv.build_from_inputs(inputs, V, _board(inputs), n_sims=SIMS, seed=SEED)
    for k in SECTION_BASIS_KEYS:
        assert k in got["basis"], k
    for e in got["games"].values():
        assert set(e) == set(iv.GAME_FIELDS)
    defaults = iv.build_columns.__kwdefaults__
    assert defaults["n_sims"] == ic.SIMS and defaults["seed"] == ic.SEED
    assert got["basis"]["g_ref"] == ic.G_REF
    assert iv.DAYS_AHEAD == 3


def test_the_construction_hash_ignores_line_endings(tmp_path):
    src = (ROOT / "intensity_core.py").read_bytes().replace(b"\r\n", b"\n")
    lf, crlf = tmp_path / "lf.py", tmp_path / "crlf.py"
    lf.write_bytes(src)
    crlf.write_bytes(src.replace(b"\n", b"\r\n"))
    assert iv.construction_hash(lf) == iv.construction_hash(crlf) == iv.construction_hash()
    lf.write_bytes(src + b"# an edit\n")
    assert iv.construction_hash(lf) != iv.construction_hash()


# ---------------------------------------------------------------------------
# 2. the build on a synthetic regular season
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def regular():
    inputs = _regular_inputs()
    return inputs, iv.build_from_inputs(inputs, V, _board(inputs), n_sims=SIMS, seed=SEED)


def test_the_block_holds_the_three_dates_after_the_vintage_and_nothing_else(regular):
    inputs, got = regular
    win = iv.window(V)
    assert win == [_days(V, 1), _days(V, 2), _days(V, 3)]
    want = {str(g["game_pk"]) for g in inputs["listed"]
            if g["date"] in win and g["state"] not in iv.SKIPPED_STATES}
    assert set(got["games"]) == want
    assert "799002" not in got["games"], "a game four days out is not in the block"
    assert "799001" not in got["games"], "a listing postponed at capture is skipped"
    assert got["basis"]["window"] == [win[0], win[-1]]


def test_the_regular_season_entries_are_the_construction(regular):
    inputs, got = regular
    stated = got["games"]["799003"]
    assert stated["null_reason"] == iv.NOT_ON_SCHEDULE and stated["ii"] is None
    first = got["games"][str(inputs["listed"][0]["game_pk"])]
    assert first["A"] is None and first["ii"] is None
    assert first["a_note"] == iv.A_UNANNOUNCED and first["S"] is not None
    n_full = 0
    for e in got["games"].values():
        if e["null_reason"]:
            continue
        assert 0.0 <= e["S"] <= 1.0 and 0.0 <= e["Q"] <= 1.0
        assert e["G"] == pytest.approx(e["dws_h"] + e["dws_a"], abs=2e-6)
        assert e["G_se"] is not None and e["G_se"] >= 0
        assert e["dpo_h"] is not None and e["series_state"] is None
        assert e["R"] is None and e["D"] in (0, 1)
        assert e["S"] == pytest.approx(ic.stakes_score(e["G"]), abs=2e-6)
        if e["A"] is not None:
            assert e["ii"] == ic.index_value(e["S"], e["Q"], e["A"], e["D"])
            n_full += 1
    assert n_full >= 5
    assert got["basis"]["mode"] == iv.MODE_REGULAR
    assert got["basis"]["schedule_source"] == iv.SOURCE_LIVE
    assert got["basis"]["computed_games"] + got["basis"]["stated_null_games"] == \
        len(got["games"])


def test_the_team_columns_add_up(regular):
    inputs, got = regular
    vals = got["values"]
    assert set(vals["ix_elo"]) == set(_divisions())
    assert sum(vals["ix_po_pct"].values()) == pytest.approx(12.0, abs=1e-6)
    assert sum(vals["ix_ws_pct"].values()) == pytest.approx(1.0, abs=1e-6)
    booked = [r for r in inputs["finals"] if r["date"] < V]
    remaining = got["basis"]["remaining_pairs"]
    assert sum(vals["ix_proj_wins"].values()) == pytest.approx(len(booked) + remaining,
                                                               abs=0.05)
    assert got["basis"]["unbooked_before_vintage"] == 1
    ratings = ic.elo_ratings_before(booked, V)
    for o, r in vals["ix_elo"].items():
        assert r == pytest.approx(ratings.get(o, ic.ELO_BASE), abs=0.006)


def test_strictly_before_no_final_on_or_after_the_vintage_date_moves_anything(regular):
    """A final dated V or later (an absurd score, a club it would flip) changes no
    value, no entry and no count."""
    _, base = regular
    late = [{"game_pk": 880000 + k, "season": "2026", "date": _days(V, k),
             "home_org": "NYY", "away_org": "BOS", "home_runs": 30, "away_runs": 0}
            for k in range(4)]
    inputs = _regular_inputs(extra_finals=late)
    got = iv.build_from_inputs(inputs, V, _board(inputs), n_sims=SIMS, seed=SEED)
    assert got["values"] == base["values"]
    assert got["games"] == base["games"]
    assert got["basis"] == base["basis"]


def test_the_build_is_deterministic_at_a_seed(regular):
    inputs, got = regular
    again = iv.build_from_inputs(_regular_inputs(), V, _board(inputs), n_sims=SIMS,
                                 seed=SEED)
    assert again["games"] == got["games"] and again["values"] == got["values"]


def test_a_fallback_schedule_is_named_and_carries_no_probables():
    inputs = _regular_inputs()
    win = iv.window(V)
    inputs["listed"] = [dict(g, home_sp=None, away_sp=None)
                        for g in inputs["season_schedule"] if g["date"] in win]
    inputs["schedule_source"] = iv.SOURCE_FALLBACK
    got = iv.build_from_inputs(inputs, V, {}, n_sims=50, seed=SEED)
    assert got["basis"]["schedule_source"] == iv.SOURCE_FALLBACK
    assert all(e["ii"] is None and e["A"] is None for e in got["games"].values())


def test_an_unreadable_schedule_is_a_stated_null_for_every_game():
    inputs = _regular_inputs()
    inputs["season_schedule"] = None
    got = iv.build_from_inputs(inputs, V, {}, n_sims=50, seed=SEED)
    assert got["basis"]["status"] == "unavailable"
    assert got["values"]["ix_po_pct"] == {} and got["values"]["ix_elo"]
    assert all(e["null_reason"] == iv.NO_SCHEDULE for e in got["games"].values())


# ---------------------------------------------------------------------------
# 3. postseason nights accrue, on the exact bracket
# ---------------------------------------------------------------------------
def test_a_world_series_game_seven_is_the_top_of_the_scale():
    inputs, seeds = _postseason_inputs(through_round="W", ws_state=(3, 3))
    got = iv.build_from_inputs(inputs, VP, {1001: 120.0, 1002: 110.0, 1003: 90.0},
                               n_sims=SIMS, seed=SEED)
    assert got["basis"]["mode"] == iv.MODE_POSTSEASON
    e = got["games"]["990001"]
    assert e["null_reason"] is None
    assert e["G"] == pytest.approx(2.0) and e["S"] == pytest.approx(1.0)
    assert e["G_se"] == 0.0 and e["dpo_h"] is None and e["dpo_a"] is None
    assert e["series_state"]["round"] == "W" and e["series_state"]["game_number"] == 7
    assert sorted(e["series_state"]["wins"].values()) == [3, 3], (
        "the final dated on the vintage date did not enter the series state")
    assert got["values"]["ix_ws_pct"][e["home"]] + got["values"]["ix_ws_pct"][e["away"]] \
        == pytest.approx(1.0)


def test_a_postseason_game_matches_the_core_recursion():
    inputs, seeds = _postseason_inputs(through_round="L")
    got = iv.build_from_inputs(inputs, VP, {}, n_sims=SIMS, seed=SEED)
    e = got["games"]["990002"]
    finals = [r for r in inputs["finals"] if r["date"] < VP]
    wins = {o: 0 for o in _divisions()}
    for r in finals:
        wins[r["home_org"] if r["home_runs"] > r["away_runs"] else r["away_org"]] += 1
    talent = ic.talent_from_ratings(ic.elo_ratings_before(finals, VP), sorted(wins))
    state = iv._series_state([f for f in inputs["post_finals"] if f["date"] < VP])
    want = ic.postseason_stakes(seeds, wins, talent, e["home"], e["away"], fmt="six",
                                series_state=state)
    assert e["G"] == pytest.approx(want["G"], abs=2e-6)
    assert e["ii"] is None and e["a_note"] == iv.A_OFF_BOARD
    po = got["values"]["ix_po_pct"]
    assert sum(po.values()) == 12.0 and set(po.values()) == {0.0, 1.0}
    assert sum(got["values"]["ix_ws_pct"].values()) == pytest.approx(1.0, abs=1e-5)
    assert got["basis"]["postseason_finals_read"] == len(inputs["post_finals"]) - 1


def test_seeds_come_from_the_standings_or_not_at_all():
    inputs, seeds = _postseason_inputs(through_round="L")
    assert iv.seeds_from_standings(inputs["standings"], _divisions(), "six") == seeds
    inputs["standings"] = []
    got = iv.build_from_inputs(inputs, VP, {}, n_sims=SIMS, seed=SEED)
    assert got["values"]["ix_po_pct"] == {} and got["values"]["ix_ws_pct"] == {}
    assert got["games"]["990002"]["null_reason"] == iv.NO_SEEDS


# ---------------------------------------------------------------------------
# 4. the seam in leaderboard_vintages: live only, never reconstructed
# ---------------------------------------------------------------------------
def _boards(data: Path):
    import json
    orgs = ("NYY", "SEA", "BOS")
    (data / "hitter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-08-19",
        "teams": [{"team": o, "offense_plus": 100 + i} for i, o in enumerate(orgs)],
        "hitters": []}), encoding="utf-8")
    (data / "starter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-08-19",
        "teams": [{"team": o, "rotation_plus": 100, "starter_ip": 500.0} for o in orgs],
        "starters": [{"mlbam": 1001, "team": "NYY", "sem_plus": 120, "qualified": True,
                      "ip_per_gs": 5.5, "role": "SP"}]}), encoding="utf-8")
    (data / "bullpen_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-08-19",
        "teams": [{"team": o, "bullpen_plus": 100, "relief_ip": 300.0} for o in orgs],
        "relievers": []}), encoding="utf-8")


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    """No network and no feed scan for the other builders; the boards in tmp."""
    import betting_usage
    import pal_export
    monkeypatch.setattr(pal_export, "load_pitch_hand", lambda season: {})
    monkeypatch.setattr(betting_usage, "build_schema4_team_columns",
                        lambda *a, **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                         for c in lv.SCHEMA4_TEAM_COLUMNS})
    monkeypatch.setattr(betting_usage, "build_pitcher_schema4", lambda *a, **k: {})
    monkeypatch.setattr(betting_usage, "build_schema5_team_columns",
                        lambda *a, **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                         for c in lv.SCHEMA5_PH_TALLY_COLUMNS})
    data = tmp_path / "data"
    data.mkdir()
    _boards(data)
    return data


def _today_inputs():
    """The regular fixture moved onto today's date, so the live clock captures it."""
    today = lv._today()
    shift = (date.fromisoformat(today) - date.fromisoformat(V)).days
    inputs = _regular_inputs()

    def mv(d):
        return (date.fromisoformat(d) + timedelta(days=shift)).isoformat()
    for r in inputs["finals"]:
        r["date"] = mv(r["date"])
    for key in ("season_schedule", "listed"):
        inputs[key] = [dict(g, date=mv(g["date"])) for g in inputs[key]]
    inputs["season"] = int(today[:4])
    return inputs


def test_a_live_snapshot_tonight_captures_the_columns_and_the_block(quiet, tmp_path,
                                                                    monkeypatch):
    monkeypatch.setattr(iv, "build_columns", functools.partial(
        _REAL_BUILD_COLUMNS, inputs=_today_inputs(), n_sims=SIMS, seed=SEED))
    res = lv.snapshot(data_dir=quiet, vintage_dir=tmp_path / "store")
    rec = res["record"]
    assert res["written"] and rec["schema"] == lv.SCHEMA
    assert [c for c in rec["team_columns"]
            if c not in lv.SW_TEAM_COLUMNS][-4:] == list(lv.IX_TEAM_COLUMNS)
    row = lv.team_row(rec, "NYY")
    for c in lv.IX_TEAM_COLUMNS:
        assert row[c] is not None, c
        assert rec["feature_basis"][c]["n"] == 3
        assert rec["feature_basis"][c]["basis"].startswith("game-intensity builder")
    blk = lv.ix_games_block(rec)
    assert blk and all(set(e) == set(iv.GAME_FIELDS) for e in blk.values())
    assert rec[lv.IX_BASIS_KEY]["construction_hash"] == iv.construction_hash()
    assert rec["feature_basis"][lv.IX_GAMES_KEY]["n"] == sum(
        1 for e in blk.values() if e["null_reason"] is None)
    pk = next(iter(blk))
    assert lv.ix_game(rec, pk) == blk[pk]
    stated = lv.ix_game(rec, 123)
    assert stated["ii"] is None and stated["null_reason"] == lv.IX_MISSING_GAME
    # the dark columns reach the assembled inputs, standardized and unread
    teams = bm.team_inputs_from_vintage(rec)
    assert teams["NYY"]["ix_elo"] == row["ix_elo"] and "z_ix_elo" in teams["NYY"]


@pytest.mark.parametrize("how", ["another date", "git backfill", "direct reduction"])
def test_n1_never_reconstructs_an_ix_column(quiet, tmp_path, monkeypatch, how):
    calls = []
    monkeypatch.setattr(iv, "build_columns", lambda **kw: calls.append(kw) or {})
    if how == "another date":
        rec = lv.snapshot(on_date="2026-08-20", data_dir=quiet,
                          vintage_dir=tmp_path / "s")["record"]
    elif how == "git backfill":
        rec = lv.snapshot(data_dir=quiet, vintage_dir=tmp_path / "s",
                          provenance={"source": lv.PROVENANCE_BACKFILL})["record"]
    else:
        rec = lv.reduce_current(on_date=lv._today(), data_dir=quiet)
    assert calls == []
    row = lv.team_row(rec, "NYY")
    assert all(row[c] is None for c in lv.IX_TEAM_COLUMNS)
    for c in lv.IX_TEAM_COLUMNS:
        assert rec["feature_basis"][c] == {"basis": lv.IX_NOT_LIVE, "n": 0}
    assert rec[lv.IX_GAMES_KEY] is None and lv.ix_games_block(rec) is None
    assert lv.ix_game(rec, 1)["null_reason"] == lv.IX_NOT_LIVE


def test_a_failing_builder_costs_its_columns_a_stated_null_never_the_snapshot(
        quiet, tmp_path, monkeypatch):
    def boom(**kw):
        raise RuntimeError("no")
    monkeypatch.setattr(iv, "build_columns", boom)
    res = lv.snapshot(data_dir=quiet, vintage_dir=tmp_path / "s")
    rec = res["record"]
    assert res["written"] and lv.team_row(rec, "NYY")["offense_plus"] is not None
    assert rec["feature_basis"]["ix_elo"]["basis"].startswith(
        "ABSENT: the game-intensity builder raised RuntimeError")
    assert rec[lv.IX_GAMES_KEY] is None


def test_unreadable_inputs_are_a_stated_null(quiet, tmp_path):
    """conftest returns no inputs; the real builder says so and writes no value."""
    rec = lv.snapshot(data_dir=quiet, vintage_dir=tmp_path / "s")["record"]
    assert rec["feature_basis"]["ix_elo"]["basis"] == iv.NO_INPUTS
    assert rec[lv.IX_BASIS_KEY]["status"] == "unavailable"
    assert lv.ix_game(rec, 1)["null_reason"] == iv.NO_INPUTS


# ---------------------------------------------------------------------------
# 5. old records return None; inputs_as_of never fills from live files
# ---------------------------------------------------------------------------
def _schema5_record() -> dict:
    cols = [c for c in lv.TEAM_COLUMNS if c not in lv.IX_TEAM_COLUMNS]
    row = [100.0, 100.0, 100.0, 500.0, 300.0] + [None] * (len(cols) - 5)
    return {"schema": 5, "vintage_date": "2026-09-20", "covers_through": "2026-09-20",
            "team_columns": cols, "pitcher_columns": list(lv.PITCHER_COLUMNS),
            "teams": {"NYY": list(row), "BOS": list(row)}, "pitchers": {},
            "feature_basis": {"xwoba_14": {"basis": "x", "n": 0}}}


def test_an_old_record_returns_none_for_every_ix_column():
    rec = _schema5_record()
    row = lv.team_row(rec, "NYY")
    assert all(row[c] is None for c in lv.IX_TEAM_COLUMNS)
    assert lv.ix_games_block(rec) is None and lv.ix_game(rec, 1) is None
    fb = lv.feature_basis(rec)
    for c in lv.IX_TEAM_COLUMNS + (lv.IX_GAMES_KEY,):
        assert fb[c]["basis"].startswith("ABSENT: schema 5 record predates the column")
        assert fb[c]["n"] == 0
    teams = bm.team_inputs_from_vintage(rec)
    assert all(teams["NYY"][c] is None and teams["NYY"]["z_" + c] is None
               for c in lv.IX_TEAM_COLUMNS)


def test_inputs_as_of_never_fills_an_ix_column_from_live_files(tmp_path, monkeypatch):
    monkeypatch.setattr(lv, "VINTAGE_DIR", tmp_path / "empty")
    lv.reset_cache()
    bm._VINTAGE_CACHE.clear()
    try:
        live = bm.inputs_as_of("2026-06-01")
        assert live["source"] == "live-leaderboards"
        rows = [r for k, r in live["teams"].items() if not k.startswith("_")]
        for r in rows:
            for c in lv.IX_TEAM_COLUMNS:
                assert r[c] is None and r["z_" + c] is None
        assert "ix_games" not in live
        none = bm.inputs_as_of("2026-06-01", allow_fallback=False)
        assert none["teams"] == {}
    finally:
        lv.reset_cache()
        bm._VINTAGE_CACHE.clear()


# ---------------------------------------------------------------------------
# 6. no served path reads ix_, by AST and by string
# ---------------------------------------------------------------------------
#: The modules allowed to name an ix_ column or block: the store, the builder, and
#: betting_model's one DARK tuple (checked node by node below).
ALLOWED = {"leaderboard_vintages.py", "intensity_vintage.py"}
IX_NAMES = ("ix_elo", "ix_po_pct", "ix_ws_pct", "ix_proj_wins", "ix_games", "ix_basis")
IX_SYMBOLS = ("IX_TEAM_COLUMNS", "IX_GAMES_KEY", "IX_BASIS_KEY", "ix_games_block",
              "ix_game", "DARK_IX_TEAM_COLUMNS", "intensity_vintage")
_IX_CONST = re.compile(r"^ix_(?!v\d+$)[a-z]")


def _modules() -> list[Path]:
    out = []
    for base, pat in ((ROOT, "*.py"), (ROOT / "tools", "*.py"), (ROOT / "assets", "*.js")):
        for p in sorted(base.glob(pat)):
            if p.name.startswith("test_") or p.name == "conftest.py":
                continue
            out.append(p)
    return out


def _bm_dark_tuple_nodes(tree: ast.AST) -> set:
    """Every node inside betting_model's DARK_IX_TEAM_COLUMNS assignment."""
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "DARK_IX_TEAM_COLUMNS"):
            return set(ast.walk(node))
    raise AssertionError("betting_model has no DARK_IX_TEAM_COLUMNS tuple")


def test_no_served_path_reads_an_ix_column_by_ast():
    offenders = []
    for p in _modules():
        if p.suffix != ".py" or p.name in ALLOWED:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        inside = _bm_dark_tuple_nodes(tree) if p.name == "betting_model.py" else set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and _IX_CONST.match(node.value) and node not in inside):
                offenders.append(f"{p.name}:{node.lineno} {node.value!r}")
            if isinstance(node, ast.Attribute) and node.attr in IX_SYMBOLS:
                offenders.append(f"{p.name}:{node.lineno} .{node.attr}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                if any(n.split(".")[0] == "intensity_vintage" for n in names):
                    offenders.append(f"{p.name}:{node.lineno} imports intensity_vintage")
        if p.name == "betting_model.py":
            uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
                    and n.id == "DARK_IX_TEAM_COLUMNS"]
            assert len(uses) == 3, "the tuple is defined and enters only the two DARK maps"
    assert not offenders, offenders


def test_no_served_path_names_an_ix_column_by_string():
    offenders = []
    for p in _modules():
        if p.name in ALLOWED:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if p.name == "betting_model.py":
            # the one tuple, removed by its own source segment, then nothing remains
            tree = ast.parse(src)
            node = next(n for n in tree.body if isinstance(n, ast.Assign)
                        and isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id == "DARK_IX_TEAM_COLUMNS")
            src = src.replace(ast.get_source_segment(src, node), "")
        for name in IX_NAMES:
            if re.search(r"\b" + name + r"\b", src):
                offenders.append(f"{p.relative_to(ROOT).as_posix()} names {name}")
        if re.search(r"\bintensity_vintage\b", src):
            offenders.append(f"{p.relative_to(ROOT).as_posix()} names intensity_vintage")
    assert not offenders, offenders


def test_only_the_store_imports_the_builder():
    tree = ast.parse((ROOT / "leaderboard_vintages.py").read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree) if isinstance(n, ast.Import)
               and any(a.name == "intensity_vintage" for a in n.names)]
    assert len(imports) == 1
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
             and isinstance(n.value, ast.Name) and n.value.id == "intensity_vintage"]
    assert [c.attr for c in calls] == ["build_columns"]
    src = (ROOT / "intensity_vintage.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    served = {"betting_model", "betting_export", "betting_intensity", "dfs_export",
              "fantasy_export", "proj_export", "leaderboard_vintages", "build_site"}
    assert not (mods & served), mods & served
