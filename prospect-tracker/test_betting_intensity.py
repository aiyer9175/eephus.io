# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The game-intensity chip's producer (betting_intensity.py, plan Part 8 item IX-S1)
and its two renderers (assets/betting.js, assets/dfs.js), on fixtures only.

No test here reads a game, a final, a standings file or a price: every club record,
schedule, standings row, bracket and starter board below is made up in this file
(`fixture_inputs`), so no intensity value is computed for a real game. The betting
section "Game intensity: stakes, matchup quality and the postseason" binds the chip:
it is a rendering beside a price, on games not yet started only.

Pinned here: the flag is off; the block carries the lane's drafted copy verbatim and
no priced key; started, settled and postponed games get no entry; the index, band,
stakes line and labels follow intensity_core; an unannounced probable publishes no
index; a postseason game reads the bracket; the DFS block carries none of the terms
the fantasy pages ban (the DFS vocabulary test); the betting page draws the chip on a
game card and a Model Watch card only before first pitch, and the DFS slate card
draws it only on an open game.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone

import pytest

import betting_intensity as bix
import intensity_core as ic

DIVISIONS = {
    "AL_E": ["BAL", "BOS", "NYY", "TBR", "TOR"],
    "AL_C": ["CHW", "CLE", "DET", "KCR", "MIN"],
    "AL_W": ["ATH", "HOU", "LAA", "SEA", "TEX"],
    "NL_E": ["ATL", "MIA", "NYM", "PHI", "WSN"],
    "NL_C": ["CHC", "CIN", "MIL", "PIT", "STL"],
    "NL_W": ["ARI", "COL", "LAD", "SDP", "SFG"],
}
DIV_OF = {o: (dv.split("_")[0], dv) for dv, m in DIVISIONS.items() for o in m}
ORGS = sorted(DIV_OF)
LEAGUE_ID = {"AL": 103, "NL": 104}
#: Fixture club strengths (made up): a win rate against an average club.
STRENGTH = {o: 0.40 + 0.20 * (i % 7) / 6 for i, o in enumerate(ORGS)}
SEASON_START = date(2026, 3, 26)
SEASON_END = date(2026, 9, 27)
FIXTURE_SEED = 20261014
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
SLATE_DATE = "2026-09-22"
#: The made-up starter board: 40 qualified starters, ids 9001 to 9040.
BOARD = {9001 + i: 80.0 + 2.0 * i for i in range(40)}
BANNED_DFS_TERMS = ("1-800-gambler", "21+", "sportsbook", "wager", "parlay",
                    "problem gambling", "moneyline")


def _team_ids() -> dict:
    import trades
    return {org: tid for tid, org in trades._org_by_id().items()}


def _day_pairs(day: date) -> list:
    """Fifteen made-up games a day: a rotation over the thirty clubs."""
    rng = random.Random(day.toordinal())
    order = list(ORGS)
    rng.shuffle(order)
    return [(order[2 * i], order[2 * i + 1]) for i in range(15)]


def _season(D: str, slate: list | None = None):
    """(finals before D, remaining pairs from D) on the made-up schedule. `slate` pairs
    are put first on D so the fixture slate is on the remaining schedule."""
    rng = random.Random(FIXTURE_SEED)
    finals, remaining = [], list(slate or [])
    d, pk = SEASON_START, 700000
    cut = date.fromisoformat(D)
    while d <= SEASON_END:
        for h, a in _day_pairs(d):
            pk += 1
            if d < cut:
                p = ic.log5(STRENGTH[h], STRENGTH[a]) + 0.02
                hw = rng.random() < p
                finals.append({"game_pk": pk, "season": "2026", "date": d.isoformat(),
                               "home_org": h, "away_org": a,
                               "home_runs": 5 if hw else 3, "away_runs": 3 if hw else 5,
                               "innings": 9, "home_sp": None, "away_sp": None})
            else:
                remaining.append((h, a))
        d += timedelta(days=1)
    return finals, remaining


def _standings(finals: list, *, clinched=(), eliminated=(), complete=False) -> list:
    """StatsAPI-shaped standings records for the made-up season."""
    ids = _team_ids()
    wins = {o: 0 for o in ORGS}
    for r in finals:
        wins[r["home_org"] if r["home_runs"] > r["away_runs"] else r["away_org"]] += 1
    recs = []
    for lg in ("AL", "NL"):
        lg_orgs = sorted((o for o in ORGS if DIV_OF[o][0] == lg), key=lambda o: (-wins[o], o))
        champs = []
        for dv in sorted(d for d in DIVISIONS if d.startswith(lg)):
            champs.append(sorted(DIVISIONS[dv], key=lambda o: (-wins[o], o))[0])
        wc_order = [o for o in lg_orgs if o not in champs]
        for dv in sorted(d for d in DIVISIONS if d.startswith(lg)):
            members = sorted(DIVISIONS[dv], key=lambda o: (-wins[o], o))
            trs = []
            for i, o in enumerate(members):
                trs.append({
                    "team": {"id": ids[o], "name": o},
                    "divisionRank": str(i + 1), "leagueRank": str(lg_orgs.index(o) + 1),
                    "wildCardRank": (str(wc_order.index(o) + 1) if o in wc_order else None),
                    "clinched": o in clinched,
                    "eliminationNumber": "E" if o in eliminated else "5",
                    "wildCardEliminationNumber": "E" if o in eliminated else "5",
                    "wins": wins[o]})
            recs.append({"league": {"id": LEAGUE_ID[lg]}, "division": {"id": dv},
                         "teamRecords": trs})
    return recs


def fixture_inputs(D: str = SLATE_DATE, *, slate: list | None = None, clinched=(),
                   eliminated=(), postseason: list | None = None) -> dict:
    finals, remaining = _season(D, slate)
    return {"season": int(D[:4]), "slate_date": D, "finals": finals,
            "remaining_pairs": remaining,
            "standings": _standings(finals, clinched=clinched, eliminated=eliminated),
            "starter_board": dict(BOARD), "starter_board_as_of": "2026-09-21",
            "postseason": ({"series": postseason} if postseason is not None else None),
            "divisions": dict(DIV_OF)}


def fixture_games(pairs: list, *, start="2026-09-22T23:05:00Z", status="Preview",
                  probables=True, first_pk=1) -> list:
    out = []
    for i, (h, a) in enumerate(pairs):
        out.append({"game_pk": first_pk + i, "date": start[:10], "start": start,
                    "status": status, "game_type": "R",
                    "home": {"org": h, "probable": ({"mlbam": 9040 - i, "name": "Home Arm"}
                                                    if probables else None)},
                    "away": {"org": a, "probable": ({"mlbam": 9039 - i, "name": "Away Arm"}
                                                    if probables else None)},
                    "moneyline": [{"side": "home", "model_prob": 0.6, "odds": -120}]})
    return out


SLATE_PAIRS = [("NYY", "BOS"), ("SEA", "TBR"), ("LAD", "SDP")]


@pytest.fixture(scope="module")
def block():
    inputs = fixture_inputs(slate=SLATE_PAIRS, clinched=("LAD",), eliminated=("TBR",))
    return bix.build_block(fixture_games(SLATE_PAIRS), SLATE_DATE, inputs=inputs,
                           now=NOW, n_sims=2000)


# ---------------------------------------------------------------------------
# the flag and the wall
# ---------------------------------------------------------------------------
def test_the_flag_is_off():
    assert bix.SHOW_INTENSITY_CHIP is False
    assert bix.PAYLOAD_KEY == "intensity"


def test_the_block_is_built_with_no_priced_key(block):
    assert block["status"] == "built", block.get("blocker")
    assert bix.forbidden_keys(block) == []
    assert set(block["games"]) == {"1", "2", "3"}
    for g in block["games"].values():
        assert not any(k in g for k in ("model_prob", "odds", "edge", "moneyline"))
    assert block["construction"] == ic.CONSTRUCTION == "ix_v1"
    assert block["sims"] == ic.SIMS and block["seed"] == ic.SEED
    assert block["g_ref"] == ic.G_REF


def test_the_copy_is_the_lane_draft_verbatim(block):
    assert block["summary"] == "Game intensity, not priced"
    assert (block["body"] + " " + block["not_priced_sentence"]) == (
        "How much rides on this game: the change in each club's World Series odds "
        "between a win and a loss, as a multiple of an average Opening Day game, plus "
        "how strong both clubs and both listed starters are and whether it is a "
        "division game. It describes the game. No probability, edge, expected value, "
        "Kelly figure, slot, badge or record row on this page reads it.")
    assert bix.STAKES_LINE_TEMPLATE.format(mult="11") == (
        "Stakes x11 (an average Opening Day game is x1)")
    assert bix.CHIP_TEMPLATE.format(ii=56, band="high") == "Intensity 56 · high"
    assert bix.DFS_BODY == (
        "How much rides on this game for both clubs, how strong they are, and both "
        "listed starters. A club that has clinched or been eliminated is labelled; "
        "check posted lineups before lock.")


def test_no_copy_carries_a_dash_or_a_forecast_word():
    strings = [v for k, v in vars(bix).items() if k.isupper() and isinstance(v, str)]
    strings += list(bix.PHASE_ROUND.values())
    for s in strings:
        assert chr(0x2014) not in s and chr(0x2013) not in s, s
        low = s.lower()
        for w in ("luck", " due ", "regress", "trending", " will ", "clutch", "sleeper"):
            assert w not in f" {low} ", (s, w)


# ---------------------------------------------------------------------------
# the values follow intensity_core
# ---------------------------------------------------------------------------
def test_each_entry_follows_the_construction(block):
    for pk, g in block["games"].items():
        assert g["ii"] == ic.index_value(g["S"], g["Q"], g["A"], g["D"]) or abs(
            g["ii"] - ic.index_value(g["S"], g["Q"], g["A"], g["D"])) <= 1
        assert g["band"] == ic.band_of(g["ii"])
        assert g["chip"] == f"Intensity {g['ii']} · {g['band']}"
        assert g["stakes_line"].startswith("Stakes x")
        assert g["stakes_line"].endswith(" (an average Opening Day game is x1)")
        assert 0.0 <= g["S"] <= 1.0 and 0.0 <= g["Q"] <= 1.0 and 0.0 <= g["A"] <= 1.0
        assert g["missing"] == []
    # the division flag: NYY v BOS and LAD v SDP are division games, SEA v TBR is not
    assert block["games"]["1"]["D"] == 1 and "division" in block["games"]["1"]["labels"]
    assert block["games"]["2"]["D"] == 0 and "division" not in block["games"]["2"]["labels"]


def test_labels_name_clinched_and_eliminated_clubs_and_the_phase(block):
    assert "clinched: LAD" in block["games"]["3"]["labels"]
    assert "eliminated: TBR" in block["games"]["2"]["labels"]
    for g in block["games"].values():
        assert g["labels"][-1] == "Final week"     # six days left on the fixture
        sw = g["playoff_swing"]
        assert set(sw) == {"pts", "club"} and sw["club"] in (g["home"], g["away"])


def test_the_top_fifth_label_reads_the_starter_percentiles(block):
    for g in block["games"].values():
        assert ("both starters in the top fifth" in g["labels"]) == (g["A"] >= 0.8)


def test_mult_text_prints_the_lane_values():
    assert bix.mult_text(10.9) == "11"
    assert bix.mult_text(1.0) == "1"
    assert bix.mult_text(3.04) == "3"
    assert bix.mult_text(0.46) == "0.5"
    assert bix.mult_text(0.0) == "0"
    assert bix.mult_text(174.6) == "175"


# ---------------------------------------------------------------------------
# games not yet started only
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["In Progress", "Final", "Game Over", "Postponed",
                                    "Suspended", "Warmup"])
def test_a_started_settled_or_postponed_game_gets_no_entry(status):
    games = fixture_games(SLATE_PAIRS)
    games[0]["status"] = status
    blk = bix.build_block(games, SLATE_DATE, inputs=fixture_inputs(slate=SLATE_PAIRS),
                          now=NOW, n_sims=300)
    assert "1" not in blk["games"] and blk["excluded"]["1"] == f"status {status}"
    assert set(blk["games"]) == {"2", "3"}


def test_a_game_past_its_first_pitch_gets_no_entry():
    games = fixture_games(SLATE_PAIRS, start="2026-09-21T11:00:00Z")
    blk = bix.build_block(games, SLATE_DATE, inputs=fixture_inputs(slate=SLATE_PAIRS),
                          now=NOW, n_sims=300)
    assert blk["games"] == {} and len(blk["excluded"]) == 3


def test_an_unannounced_probable_publishes_no_index():
    games = fixture_games(SLATE_PAIRS, probables=False)
    blk = bix.build_block(games, SLATE_DATE, inputs=fixture_inputs(slate=SLATE_PAIRS),
                          now=NOW, n_sims=300)
    for g in blk["games"].values():
        assert g["ii"] is None and g["band"] is None and g["A"] is None
        assert g["missing"] == ["probables not posted"]
        assert g["chip"] == f"Stakes x{bix.mult_text(g['stakes_multiple'])} · probables not posted"


def test_a_starter_off_the_board_is_named_as_such():
    games = fixture_games(SLATE_PAIRS[:1])
    games[0]["home"]["probable"]["mlbam"] = 1234567
    blk = bix.build_block(games, SLATE_DATE, inputs=fixture_inputs(slate=SLATE_PAIRS[:1]),
                          now=NOW, n_sims=300)
    assert blk["games"]["1"]["missing"] == ["starter not on the board"]


def test_a_game_off_the_remaining_schedule_is_a_stated_miss():
    games = fixture_games([("NYY", "BOS")])
    inputs = fixture_inputs()
    inputs["remaining_pairs"] = [p for p in inputs["remaining_pairs"] if p != ("NYY", "BOS")]
    blk = bix.build_block(games, SLATE_DATE, inputs=inputs, now=NOW, n_sims=300)
    assert blk["games"] == {} and blk["missing_games"] == {"1": bix.NOT_ON_SCHEDULE}
    inputs["remaining_pairs"] = []
    blk = bix.build_block(games, SLATE_DATE, inputs=inputs, now=NOW, n_sims=300)
    assert blk["missing_games"] == {"1": bix.NO_SCHEDULE}


def test_an_unreadable_input_is_a_dark_block_never_a_raise():
    blk = bix.build_block(fixture_games(SLATE_PAIRS), SLATE_DATE,
                          inputs={"divisions": None, "finals": 7}, now=NOW, n_sims=300)
    assert blk["status"] == "unavailable" and blk["blocker"]
    assert blk["games"] == {}
    assert blk["summary"] == bix.SUMMARY


def test_the_block_does_not_mutate_the_slate():
    games = fixture_games(SLATE_PAIRS)
    before = json.dumps(games, sort_keys=True)
    bix.build_block(games, SLATE_DATE, inputs=fixture_inputs(slate=SLATE_PAIRS), now=NOW,
                    n_sims=300)
    assert json.dumps(games, sort_keys=True) == before


# ---------------------------------------------------------------------------
# the postseason reads the bracket
# ---------------------------------------------------------------------------
def _post_inputs(state: dict) -> tuple[dict, list]:
    """A made-up completed regular season and a bracket in postseason.parse's row
    shape: [series_id, round, best_of, club_a, club_b, wins_a, wins_b, winner,
    complete]."""
    D = "2026-10-06"
    inputs = fixture_inputs(D)
    inputs["remaining_pairs"] = []
    flags = bix._standings_flags(inputs["standings"])
    clubs = set()
    for lg in ("AL", "NL"):
        lg_orgs = [o for o in ORGS if DIV_OF[o][0] == lg]
        champs = [o for o in lg_orgs if flags[o]["division_rank"] == 1]
        wcs = sorted((o for o in lg_orgs if o not in champs),
                     key=lambda o: flags[o]["wild_card_rank"])[:3]
        clubs.update(champs + wcs)
    seeds = bix._seeds(flags, DIV_OF, clubs)
    series = []
    for lg, s in seeds.items():
        s1, s2, s3, s4, s5, s6 = s
        series.append([f"{lg}F1", 1, 3, s3, s6, 2, 0, s3, True])
        series.append([f"{lg}F2", 1, 3, s4, s5, 2, 1, s4, True])
        a, b = state.get(lg, (0, 0))
        series.append([f"{lg}D1", 2, 5, s1, s4, a, b, None, False])
        series.append([f"{lg}D2", 2, 5, s2, s3, 0, 0, None, False])
    inputs["postseason"] = {"series": series}
    return inputs, [seeds["AL"], seeds["NL"]]


def test_a_postseason_game_reads_the_series_state_and_labels_an_elimination_game():
    inputs, (al, nl) = _post_inputs({"AL": (2, 1)})
    s1, s4 = al[0], al[3]
    g = fixture_games([(s4, s1)], start="2026-10-06T20:00:00Z")
    g[0]["game_type"] = "D"
    blk = bix.build_block(g, "2026-10-06", inputs=inputs,
                          now=datetime(2026, 10, 6, 8, tzinfo=timezone.utc))
    row = blk["games"]["1"]
    assert row["game_type"] == "D"
    assert "elimination game" in row["labels"] and row["labels"][-1] == "Division Series"
    assert row["playoff_swing"] is None
    # the swing is the exact recursion's, not a draw: the same inputs give the same row
    again = bix.build_block(g, "2026-10-06", inputs=inputs,
                            now=datetime(2026, 10, 6, 8, tzinfo=timezone.utc))
    assert again["games"] == blk["games"]


def test_a_postseason_game_with_no_bracket_is_a_stated_miss():
    inputs, (al, _nl) = _post_inputs({})
    inputs["postseason"] = None
    g = fixture_games([(al[3], al[0])], start="2026-10-06T20:00:00Z")
    g[0]["game_type"] = "D"
    blk = bix.build_block(g, "2026-10-06", inputs=inputs,
                          now=datetime(2026, 10, 6, 8, tzinfo=timezone.utc))
    assert blk["games"] == {} and blk["missing_games"] == {"1": bix.NO_BRACKET}


# ---------------------------------------------------------------------------
# DFS: the same function, its own copy, none of the banned terms
# ---------------------------------------------------------------------------
def test_the_dfs_block_carries_none_of_the_terms_the_fantasy_pages_ban():
    """The DFS vocabulary test: every string the DFS surface can print, the block's
    copy and every label, is free of test_fantasy_split's banned betting terms."""
    blk = bix.build_block(fixture_games(SLATE_PAIRS), SLATE_DATE, surface="dfs",
                          inputs=fixture_inputs(slate=SLATE_PAIRS, clinched=("LAD",),
                                                eliminated=("TBR",)),
                          now=NOW, n_sims=300)
    assert blk["status"] == "built"
    assert blk["summary"] == "Game intensity" and blk["body"] == bix.DFS_BODY
    assert blk["not_priced_sentence"] is None
    texts = [blk["summary"], blk["body"], blk["talent_note"]]
    for g in blk["games"].values():
        texts += [g["chip"], g["stakes_line"]] + g["labels"] + g["missing"]
    texts += [bix.DFS_SUMMARY, bix.DFS_BODY, bix.LABEL_CLINCHED, bix.LABEL_ELIMINATED,
              bix.LABEL_SWING, bix.LABEL_ELIMINATION, bix.LABEL_ACES, bix.LABEL_DIVISION,
              bix.WHY_UNANNOUNCED, bix.WHY_OFF_BOARD, bix.CHIP_TEMPLATE,
              bix.CHIP_NO_INDEX_TEMPLATE, bix.STAKES_LINE_TEMPLATE]
    for t in texts:
        low = str(t).lower()
        for term in BANNED_DFS_TERMS:
            assert term not in low, (t, term)
    assert "clinched: LAD" in blk["games"]["3"]["labels"]
    assert "eliminated: TBR" in blk["games"]["2"]["labels"]
    # the lane's banned list is the fantasy test's own list
    assert set(BANNED_DFS_TERMS) == _fantasy_ban_terms()


def _fantasy_ban_terms() -> set:
    """The string constants of the tuple test_fantasy_split bans, read by AST."""
    import ast
    import inspect
    import textwrap
    import test_fantasy_split as tfs
    tree = ast.parse(textwrap.dedent(inspect.getsource(
        tfs.test_fantasy_pages_carry_no_betting_copy)))
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            return {e.value for e in node.iter.elts if isinstance(e, ast.Constant)}
    raise AssertionError("the banned-terms tuple was not found")


# ---------------------------------------------------------------------------
# the renderers (py_mini_racer; skipped without it)
# ---------------------------------------------------------------------------
IX_TOKEN = 'class="bt-ix"'
DFS_TOKEN = 'class="dfs-ix"'


def _betting_payload(now_iso: str, block: dict | None) -> dict:
    from test_betting import LIVE_PAYLOAD
    d = json.loads(LIVE_PAYLOAD)
    for b in d["team_bets"]:
        b["status"] = "Preview"
    if block is not None:
        d["intensity"] = block
    return d


def _betting_block(d: dict) -> dict:
    pairs = [(b["home"]["org"], b["away"]["org"]) for b in d["team_bets"]]
    bets = list(d["team_bets"])
    # the pick's game (823104, TBR at SEA) is not among the cards: the map covers it
    bets.append({"game_pk": 823104, "start": "2026-08-09T20:10:00Z", "status": "Preview",
                 "away": {"org": "TBR", "probable": None}, "home": {"org": "SEA",
                                                                    "probable": None}})
    return bix.build_block(bets, d["slate_date"],
                           inputs=fixture_inputs(d["slate_date"], slate=pairs + [("SEA", "TBR")]),
                           now=datetime(2026, 8, 9, 8, tzinfo=timezone.utc), n_sims=400)


def _betting_html(d: dict, section: str, now_iso: str) -> str:
    from test_betting import _ctx, _fetch_js, LEARNING_ARTIFACT, EVAL_ARTIFACT, CLV_EMPTY
    c = _ctx("window.EEPHUS_BETTING_NOW = %s;\n" % json.dumps(now_iso) +
             _fetch_js(main=json.dumps(d), learning=LEARNING_ARTIFACT, evald=EVAL_ARTIFACT,
                       clv=CLV_EMPTY))
    return c.eval("__show(%s)" % json.dumps(section))


@pytest.fixture(scope="module")
def betting_with_block():
    pytest.importorskip("py_mini_racer")
    d = _betting_payload("", None)
    d["intensity"] = _betting_block(d)
    return d


def test_the_betting_cards_draw_the_chip_before_first_pitch(betting_with_block):
    d = betting_with_block
    html = _betting_html(d, "teams", "2026-08-09T12:00:00Z")
    assert html.count(IX_TOKEN) == len(d["team_bets"]) == 2
    for b in d["team_bets"]:
        g = d["intensity"]["games"][str(b["game_pk"])]
        assert bix.SUMMARY in html and g["chip"] in html
    # beside the Dugout block, closed by default, carrying the drafted body
    assert "<details class=\"bt-ix\" open" not in html
    assert bix.NOT_PRICED_SENTENCE in html


def test_the_betting_cards_never_draw_the_chip_on_a_started_or_settled_game(betting_with_block):
    d = json.loads(json.dumps(betting_with_block))
    html = _betting_html(d, "teams", "2026-08-10T12:00:00Z")      # every game started
    assert IX_TOKEN not in html
    d["team_bets"][0]["status"] = "Final"
    html = _betting_html(d, "teams", "2026-08-09T12:00:00Z")
    assert html.count(IX_TOKEN) == 1
    d["team_bets"][1]["status"] = "In Progress"
    html = _betting_html(d, "teams", "2026-08-09T12:00:00Z")
    assert IX_TOKEN not in html


def test_the_model_watch_card_draws_the_chip_only_before_first_pitch(betting_with_block):
    d = json.loads(json.dumps(betting_with_block))
    pk = (d.get("pick_of_the_day") or {}).get("game_pk")
    # the pick's game is not a card on this payload, so the card has no clock: no chip
    html = _betting_html(d, "potd", "2026-08-09T12:00:00Z")
    assert IX_TOKEN not in html
    d["team_bets"].append({**json.loads(json.dumps(d["team_bets"][0])), "game_pk": pk,
                           "start": "2026-08-09T20:10:00Z"})
    html = _betting_html(d, "potd", "2026-08-09T12:00:00Z")
    assert html.count(IX_TOKEN) == 1
    html = _betting_html(d, "potd", "2026-08-09T21:00:00Z")
    assert IX_TOKEN not in html


def test_without_the_block_the_betting_page_is_unchanged():
    pytest.importorskip("py_mini_racer")
    d = _betting_payload("", None)
    html = _betting_html(d, "teams", "2026-08-09T12:00:00Z")
    assert IX_TOKEN not in html and "Game intensity" not in html


def _dfs_html(payload: dict) -> str:
    pytest.importorskip("py_mini_racer")
    import test_fantasy_split as tfs
    return tfs._dfs_boot(json.dumps(payload)).eval('__go("#section=slate")')


def _dfs_payload(block: bool = True, start: str = "2099-08-05T23:05:00Z") -> dict:
    import test_fantasy_split as tfs
    d = json.loads(tfs._ctx_payload())
    for g in d["games"]:
        g["datetime"] = start
        g["status"] = "Preview"
        # the fixture's made-up club codes are outside the thirty-club field
        g["home"]["org"], g["away"]["org"] = "NYY", "BOS"
    if block:
        pairs = [(g["home"]["org"], g["away"]["org"]) for g in d["games"]]
        games = [{"game_pk": g["game_pk"], "datetime": g["datetime"], "status": g["status"],
                  "home": g["home"], "away": g["away"]} for g in d["games"]]
        d["intensity"] = bix.build_block(
            games, SLATE_DATE, surface="dfs",
            inputs=fixture_inputs(slate=pairs, clinched=(pairs[0][0],)), now=NOW, n_sims=400)
    return d


def test_the_dfs_slate_card_draws_the_chip_on_an_open_game():
    d = _dfs_payload()
    html = _dfs_html(d)
    assert html.count(DFS_TOKEN) == len(d["games"]) == 1
    g = d["intensity"]["games"][str(d["games"][0]["game_pk"])]
    assert g["chip"] in html and bix.DFS_BODY in html
    assert f"clinched: {d['games'][0]['home']['org']}" in html
    assert bix.NOT_PRICED_SENTENCE not in html and bix.SUMMARY not in html
    low = html.lower()
    for term in BANNED_DFS_TERMS:
        assert term not in low


def test_the_dfs_slate_card_draws_no_chip_on_a_started_game_or_without_the_block():
    assert DFS_TOKEN not in _dfs_html(_dfs_payload(start="2020-08-05T23:05:00Z"))
    d = _dfs_payload()
    d["games"][0]["status"] = "Final"
    assert DFS_TOKEN not in _dfs_html(d)
    assert DFS_TOKEN not in _dfs_html(_dfs_payload(block=False))
