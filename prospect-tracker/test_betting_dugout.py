# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_dugout: the Dugout context block, built from the management board and
read into no price.

Exporter side, offline. The board is a FIXTURE under tmp_path (the checkout's
data/management_board.json is never read by these tests and never written), and the
sidecar-isolation redirect applies because the module matches "betting*.py".

What these tests exist to catch, each named in a docstring: a read of a per-club
decision ledger file; an import that makes the seam two-way; a sentence typed instead
of copied; a value rescaled (100+10z) or rounded; a key that carries "dv" or
"decision" (the management gate's rule); a cross-family total or the not-summed
family; a read of a priced key or a mutation of the bets; a raise into the exporter;
a carried board described by the wrong list (review defect M2).
"""
from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path

import pytest

import betting_dugout as bd

ROOT = Path(__file__).resolve().parent
SRC = (ROOT / "betting_dugout.py").read_text(encoding="utf-8")

# The served shape, cut down: units carry the four served keys (mwpa, dvs, li, z) so
# the M1 assertion below is on the real shape, not a friendly one.
STYLE_SENTENCE = ("Style, not skill: each is a signed z-score across the thirty club-seasons "
                  "of its season, sign as measured. Not an index, no ladder, no plus sign; a "
                  "frequency has no good direction, and these repeat because they are policy.")
REALIZED_SENTENCE = ("Realized value, not skill. Each figure is the win probability that "
                     "actually moved after the decision, credited to the club that made it.")
AGENT_SENTENCE = ("The agent is the club-season until the manager ledger lands; a club that "
                  "changed managers during a season is one row here and two in reality.")
OVERLAP_NOTE = "No cross-family total exists on any row. Per-family sums only."
UNITS = {"mwpa": "wins, realized value, not skill (wp percentage points divided by 100)",
         "dvs": "wins above state, realized, selection not removed",
         "li": "leverage index, MLB feed basis; null on the leadoff plate appearance",
         "z": "signed style z-score, not an index, not skill"}
FLOORS = {"pitching_change": 100, "pinch_hit": 40, "pinch_run": 15, "intentional_walk": 8,
          "bunt": 20, "steal": 30, "defensive_sub": 30}
FAMILY_LABELS = {"pitching_change": "Pitching changes", "pinch_hit": "Pinch hitters",
                 "pinch_run": "Pinch runners", "defensive_sub": "Defensive subs",
                 "intentional_walk": "Intentional walks", "bunt": "Bunts", "steal": "Steals"}


def _row(club, season, **over):
    r = {"club": club, "season": season, "agent": "club-season", "games": 141,
         "n_all": 1345, "n_pitching_change": 469, "n_pinch_hit": 110, "n_pinch_run": 29,
         "n_defensive_sub": 132, "n_intentional_walk": 12, "n_bunt": 65, "n_steal": 86,
         "n_mound_visit": 432, "n_ejection": 10, "mean_li": 1.485, "share_li_high": 0.431,
         "mwpa_pitching_change": 5.573, "mwpa_pinch_hit": -1.181, "mwpa_pinch_run": 1.738,
         "mwpa_intentional_walk": 0.087, "mwpa_bunt": -0.826, "mwpa_steal": 0.367,
         "mwpa_defensive_sub": 0.5,
         "hook_median_pitches": 90.0, "pen_per_game": 3.326, "bench_per_game": 0.986,
         "ibb_per_game": 0.085, "visit_per_game": 3.064,
         "best": {"id": "822709:61:2", "family": "pitching_change", "game_pk": 822709,
                  "ab": 61, "mwpa": 0.867, "date": "2026-07-10"},
         "worst": {"id": "824744:70:0", "family": "pitching_change", "game_pk": 824744,
                   "ab": 70, "mwpa": -0.789, "date": "2026-06-28"},
         "partial": True, "z_hook": 0.51, "z_pen": 0.45, "z_bench": -0.64,
         "z_ibb": -0.59, "z_visit": 0.33}
    r.update(over)
    return r


def board_fixture() -> dict:
    return {
        "generated_at": "2026-09-24T03:04:58+00:00",
        "decisions": {
            "status": "built",
            "corpus_built_at": "2026-09-06T07:04:19+00:00",
            "through_by_season": {"2025": "2025-09-28", "2026": "2026-09-04"},
            "families": {f: {"label": lab, "floor": FLOORS[f]} for f, lab in FAMILY_LABELS.items()},
            "realized_sentence": REALIZED_SENTENCE,
            "agent_sentence": AGENT_SENTENCE,
            "overlap_note": OVERLAP_NOTE,
            "units": dict(UNITS),
            "no_cross_family_total": True,
            "dvs_note": "a sentence that must never travel",
            "li_note": "another",
        },
        "clubs": {
            "status": "built",
            "rows": [
                _row("NYY", 2026),
                _row("ATH", 2026, mwpa_intentional_walk=None, n_intentional_walk=3,
                     z_hook=-0.6, z_pen=-1.2),
                _row("MIA", 2026),
                _row("CHC", 2026),
                _row("NYY", 2025, z_hook=1.9),
            ],
            "statsapi_codes": {"NYY": "NYY", "ATH": "ATH", "MIA": "MIA", "CHC": "CHC",
                               "ARI": "AZ", "KCR": "KC"},
            "not_summed": ["defensive_sub"],
            "agent_sentence": AGENT_SENTENCE,
            "style_sentence": STYLE_SENTENCE,
            "plus_metric": False,
            "floors": dict(FLOORS),
            "games_floor": 40,
        },
    }


def _hook(board):
    board["decisions"]["families"]["pitching_change"]["hook_pitch_count"] = {
        "median": 89.0, "p10": 64.0, "p90": 102.0, "n": 37964}
    return board


@pytest.fixture
def board():
    return _hook(board_fixture())


@pytest.fixture
def data_dir(tmp_path, board):
    (tmp_path / "management_board.json").write_text(json.dumps(board), encoding="utf-8")
    return tmp_path


SENTINEL = 0.123456789


def _bet(pk, away, home, **priced):
    """A bet carrying every PRICED_KEY at every level with a sentinel value."""
    side = {"side": "home", "label": home}
    side.update({k: SENTINEL for k in bd.PRICED_KEYS})
    b = {"game_pk": pk, "away": {"org": away, "probable": None},
         "home": {"org": home, "probable": None},
         "model": {k: SENTINEL for k in bd.PRICED_KEYS},
         "moneyline": [dict(side), dict(side, side="away", label=away)],
         "runline": None, "total": {"line": 9.0, "sides": [dict(side)]}}
    b.update({k: SENTINEL for k in bd.PRICED_KEYS})
    b.update(priced)
    return b


BETS = [_bet(824625, "MIA", "CHC"), _bet(824626, "ATH", "NYY")]


def _keys(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


# ---------------------------------------------------------------------------
# the wall, on the module's own text
# ---------------------------------------------------------------------------
def test_the_block_is_built_from_the_board_and_never_the_shards(tmp_path, board):
    """A per-club ledger file sits beside the board with bytes that are not JSON; a
    reader that opened it would raise. The source of the module names neither the
    ledger directory nor the word for its files."""
    (tmp_path / "management_board.json").write_text(json.dumps(board), encoding="utf-8")
    shard_dir = tmp_path / "mgmt_decisions"
    shard_dir.mkdir()
    (shard_dir / "2026-NYY.json").write_bytes(b"\x00not json\xff")
    blk = bd.build_block(BETS, "2026-09-23", data_dir=tmp_path)
    assert blk["status"] == "built", blk["blocker"]
    assert "mgmt_decisions" not in SRC
    assert "shards" not in SRC


def test_the_module_imports_nothing_from_betting_or_management():
    tree = ast.parse(SRC)
    banned = ("betting_", "leaderboard_vintages", "mgmt_", "management", "trades", "storage")
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            assert not any(n.startswith(b) for b in banned), (
                f"betting_dugout imports {n}: the seam must stay one way")


def test_the_not_priced_sentence_is_the_module_constant_and_has_no_dash(data_dir):
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    assert blk["not_priced_sentence"] == bd.NOT_PRICED_SENTENCE
    assert blk["head"] == bd.HEAD
    em, en = chr(0x2014), chr(0x2013)
    for name, val in vars(bd).items():
        if isinstance(val, str) and not name.startswith("__"):
            assert em not in val and en not in val, name
        if isinstance(val, tuple):
            for item in val:
                for part in (item if isinstance(item, tuple) else (item,)):
                    if isinstance(part, str):
                        assert em not in part and en not in part, (name, part)


# ---------------------------------------------------------------------------
# verbatim sentences, unchanged values
# ---------------------------------------------------------------------------
def test_the_three_board_sentences_travel_verbatim(data_dir, board):
    """M1: the served units dict carries `dvs`, a forbidden key that would put the one
    DVS sentence on a price card; only mwpa and z travel."""
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    assert blk["realized_sentence"] == board["decisions"]["realized_sentence"]
    assert blk["style_sentence"] == board["clubs"]["style_sentence"]
    assert blk["agent_sentence"] == board["clubs"]["agent_sentence"]
    assert blk["overlap_note"] == board["decisions"]["overlap_note"]
    assert blk["units"]["mwpa"] == UNITS["mwpa"]
    assert blk["units"]["z"] == UNITS["z"]
    assert set(blk["units"]) == {"mwpa", "z"}
    dumped = json.dumps(blk)
    assert UNITS["dvs"] not in dumped and UNITS["li"] not in dumped
    assert "a sentence that must never travel" not in dumped


def test_style_and_realized_values_are_the_boards_values_unchanged(data_dir, board):
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    nyy = blk["clubs"]["NYY"]
    row = next(r for r in board["clubs"]["rows"] if r["club"] == "NYY" and r["season"] == 2026)
    for k, _lab, _basis in bd.STYLE_COLUMNS:
        assert nyy["style"][k] == row[k]
        assert nyy["style"][k] != 100 + 10 * row[k]
    for k, _lab, _unit, _dec in bd.RATE_COLUMNS:
        assert nyy["rates"][k] == row[k]
    for f in bd.REALIZED_FAMILIES:
        assert nyy["realized"][f"mwpa_{f}"] == row[f"mwpa_{f}"]
        assert nyy["counts"][f"n_{f}"] == row[f"n_{f}"]
    ath = blk["clubs"]["ATH"]
    assert ath["realized"]["mwpa_intentional_walk"] is None    # null stays null
    assert ath["counts"]["n_intentional_walk"] == 3
    assert ath["style"]["z_pen"] == -1.2
    assert nyy["games"] == 141 and nyy["partial"] is True
    assert blk["league"] == {"hook_median_pitches": 89.0, "hook_p10": 64.0,
                             "hook_p90": 102.0, "hook_n": 37964}
    assert blk["floors"] == {f: FLOORS[f] for f in bd.REALIZED_FAMILIES}
    assert blk["games_floor"] == 40
    assert blk["plus_metric"] is False and blk["no_cross_family_total"] is True
    assert blk["through"] == "2026-09-04" and blk["corpus_built_at"] == "2026-09-06T07:04:19+00:00"
    assert blk["source_label"] == bd.SOURCE_TEMPLATE.format(
        season=2026, through="2026-09-04", corpus_built_at="2026-09-06T07:04:19+00:00")
    assert blk["below_floor_template"] == bd.BELOW_FLOOR_TEMPLATE
    assert [c["key"] for c in blk["style_columns"]] == [k for k, _l, _b in bd.STYLE_COLUMNS]
    assert [c["key"] for c in blk["rate_columns"]] == [k for k, _l, _u, _d in bd.RATE_COLUMNS]
    assert [f["key"] for f in blk["realized_families"]] == list(bd.REALIZED_FAMILIES)
    assert blk["realized_families"][0] == {"key": "pitching_change", "label": "Pitching changes",
                                           "floor": 100}


# ---------------------------------------------------------------------------
# keys: the management gate's rule, no total, no not-summed family
# ---------------------------------------------------------------------------
def test_no_key_in_the_block_contains_dv_or_decision(data_dir):
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    for k in _keys(blk):
        assert "dv" not in k and "decision" not in k, k
    assert bd.forbidden_keys(blk) == []


def test_no_cross_family_total_and_no_defensive_sub_realized(data_dir):
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    keys = _keys(blk)
    assert not any(re.fullmatch(r"mwpa_(total|all|sum)", k) for k in keys)
    assert "mwpa_defensive_sub" not in keys and "n_defensive_sub" not in keys
    for bad in ("best", "worst", "dvs", "defensive_sub", "hook_hist", "managers",
                "gate_verdict", "mwpa_mound_visit"):
        assert bad not in keys, bad
    assert all(f["key"] != "defensive_sub" for f in blk["realized_families"])


# ---------------------------------------------------------------------------
# the bets: three keys read, nothing copied, nothing mutated
# ---------------------------------------------------------------------------
def test_the_block_reads_only_orgs_and_game_pk_off_the_bets_and_mutates_nothing(data_dir):
    bets = copy.deepcopy(BETS)
    before = copy.deepcopy(bets)
    blk = bd.build_block(bets, "2026-09-23", data_dir=data_dir)
    assert bets == before
    keys = _keys(blk)
    for k in bd.PRICED_KEYS:
        assert k not in keys, k
    assert str(SENTINEL) not in json.dumps(blk)
    assert "0.1234" not in json.dumps(blk)


# ---------------------------------------------------------------------------
# dark states, each named
# ---------------------------------------------------------------------------
def test_a_missing_board_is_a_dark_block_with_its_blocker(tmp_path):
    blk = bd.build_block(BETS, "2026-09-23", data_dir=tmp_path)
    assert blk["status"] == "unavailable"
    assert blk["blocker"] == bd.BOARD_ABSENT
    assert blk["clubs"] == {}
    assert set(blk["games"]) == {"824625", "824626"}
    assert blk["not_priced_sentence"] == bd.NOT_PRICED_SENTENCE
    assert blk["head"] == bd.HEAD
    assert bd.load_board(tmp_path) is None


def test_an_unreadable_board_is_a_dark_block_too(tmp_path):
    (tmp_path / "management_board.json").write_bytes(b"\xff{not json")
    blk = bd.build_block(BETS, "2026-09-23", data_dir=tmp_path)
    assert blk["status"] == "unavailable" and blk["blocker"] == bd.BOARD_ABSENT


def test_a_clubs_block_not_built_names_its_status(tmp_path, board):
    board["clubs"]["status"] = "skipped: no corpus"
    (tmp_path / "management_board.json").write_text(json.dumps(board), encoding="utf-8")
    blk = bd.build_block(BETS, "2026-09-23", data_dir=tmp_path)
    assert blk["status"] == "unavailable"
    assert blk["blocker"] == bd.CLUBS_NOT_BUILT.format(status="skipped: no corpus")
    assert blk["games"] and blk["clubs"] == {}


def test_a_club_without_a_season_row_carries_the_row_note_and_still_links(data_dir):
    bets = BETS + [_bet(824627, "XXX", "NYY")]
    blk = bd.build_block(bets, "2026-09-23", data_dir=data_dir)
    x = blk["clubs"]["XXX"]
    assert x["row_note"] == bd.NO_ROW_TEMPLATE.format(season=2026, club="XXX")
    assert x["style"] is None and x["rates"] is None and x["shape"] is None
    assert x["counts"] is None and x["realized"] is None
    assert x["link"] == "/management/#section=clubs&team=XXX"
    assert x["link_label"] == "Open XXX on In-Game Management"
    assert blk["status"] == "built" and blk["season_rows_present"] is True


def test_a_season_with_no_rows_sets_season_rows_present_false_and_the_note(data_dir):
    blk = bd.build_block(BETS, "2027-04-02", data_dir=data_dir)
    assert blk["status"] == "built"
    assert blk["season"] == 2027
    assert blk["season_rows_present"] is False
    assert blk["season_note"] == bd.SEASON_ABSENT.format(season=2027)
    assert blk["through"] is None
    for c in blk["clubs"].values():
        assert c["row_note"] == bd.NO_ROW_TEMPLATE.format(season=2027, club=c["club"])


def test_build_block_never_raises_into_the_exporter(data_dir):
    """A board that is JSON but not the expected shape yields a dark block, not a
    traceback in betting_export.build."""
    (data_dir / "management_board.json").write_text('{"clubs": "not a dict"}', encoding="utf-8")
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    assert blk["status"] == "unavailable" and blk["blocker"]
    blk2 = bd.build_block([{"nonsense": 1}, None, {"game_pk": 5}], None, data_dir=data_dir)
    assert blk2["status"] == "unavailable" and blk2["games"] == {}


# ---------------------------------------------------------------------------
# the games map, the carried board, the links, the dark shape line
# ---------------------------------------------------------------------------
def test_the_games_map_covers_every_slate_game_with_site_codes(data_dir):
    bets = BETS + [_bet(824628, "KCR", "ARI")]
    blk = bd.build_block(bets, "2026-09-23", data_dir=data_dir)
    assert len(blk["games"]) == len(bets)
    for g in blk["games"].values():
        for side in ("away", "home"):
            assert re.fullmatch(r"[A-Z]{2,3}", g[side]), g
    assert blk["games"]["824626"] == {"away": "ATH", "home": "NYY"}
    assert "OAK" not in json.dumps(blk["games"])
    # the board's StatsAPI code rides beside the site code, never in place of it
    assert blk["clubs"]["KCR"]["statsapi_code"] == "KC" and blk["clubs"]["KCR"]["club"] == "KCR"
    assert set(blk["clubs"]) == {"MIA", "CHC", "ATH", "NYY", "KCR", "ARI"}


def test_a_carried_board_builds_the_block_for_the_carried_slate(data_dir):
    """M2: on a carried night _carry_previous_board replaces payload["team_bets"] with
    the previous slate and payload["slate_date"] with the previous date while the
    local `bets` is tonight's empty list. The block must describe the payload's list."""
    prev = [_bet(900000 + i, "MIA", "CHC") for i in range(12)]
    payload = {"team_bets": prev, "slate_date": "2025-09-28", "n_games": 12}
    tonight_bets: list = []
    blk = bd.build_block(payload["team_bets"], payload["slate_date"], data_dir=data_dir)
    assert len(blk["games"]) == 12
    assert blk["season"] == 2025
    assert blk["clubs"]["MIA"]["row_note"]                  # no 2025 MIA row in the fixture
    wrong = bd.build_block(tonight_bets, payload["slate_date"], data_dir=data_dir)
    assert wrong["games"] == {} and wrong["clubs"] == {}   # the property the seam must never have


def test_every_link_is_site_relative(data_dir):
    hygiene = pytest.importorskip("test_betting_publish_hygiene")
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    dumped = json.dumps(blk)
    for pat in hygiene.ABS_PATH_PATTERNS:
        assert not re.search(pat, dumped), pat
    assert blk["source"].startswith("/")
    for c in blk["clubs"].values():
        assert c["link"].startswith("/management/#section=clubs&team=")
        if c["drill_link"] is not None:
            assert c["drill_link"].startswith("/management/#section=decisions&team=")
            assert "{family}" in c["drill_link"]


def test_the_shape_names_its_dark_line(data_dir):
    blk = bd.build_block(BETS, "2026-09-23", data_dir=data_dir)
    for c in blk["clubs"].values():
        assert c["shape"]["li_at_entry"] is None
        assert c["shape"]["li_at_entry_blocker"] == bd.SHAPE_DARK_SENTENCE
        assert c["shape"]["league_hook_median_pitches"] == 89.0
        assert c["shape"]["hook_median_pitches"] == c["rates"]["hook_median_pitches"]
    assert blk["shape_dark_sentence"] == bd.SHAPE_DARK_SENTENCE


def test_the_block_stays_small_against_the_payload(data_dir):
    """Thirty clubs at the served shape must stay well under the payload: one request
    for the pick tab, no sidecar fetch."""
    bets = [_bet(700000 + i, "MIA", "CHC") for i in range(15)]
    blk = bd.build_block(bets, "2026-09-23", data_dir=data_dir)
    assert len(json.dumps(blk)) < 60_000
