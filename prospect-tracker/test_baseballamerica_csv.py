# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the Baseball America board ingest.

Every test here corresponds to a failure this repo has ALREADY had, on some
other source. The point of the file is that a BA import cannot reintroduce
one of them quietly.
"""
from __future__ import annotations

import re

import pytest

import baseballamerica_csv as ba
from consensus import _ORG_LIST_LABEL_RE


# --------------------------------------------------------------------------
# The org-list label. This is the one that has actually cost the board before.
# --------------------------------------------------------------------------

def test_org_list_label_matches_the_guard_that_stops_rank_implied_fv():
    """Bryan Sanchez sorted 19th overall on zero published FVs because a
    2021 Nationals Top-30 label did not match the org-list check, so rank 30
    fed implied_fv_from_rank and inflated to FV 55. A BA org board is the same
    shape and would make every number-one org prospect an FV 70."""
    board = ba.parse_board(_full_board(30), _META)
    label = board["meta"]["interval_label"]
    assert label == "Baseball America 2026 Blue Jays Top 30"
    assert _ORG_LIST_LABEL_RE.search(label), (
        f"{label!r} does not match the org-list guard, so its ranks would feed "
        f"implied_fv_from_rank")
    assert ba.validate_org_label(label) is None


@pytest.mark.parametrize("n", [3, 29, 31, 100])
def test_a_board_whose_size_the_guard_does_not_accept_is_refused_loudly(n):
    """The guard accepts only Top 10/20/25/30. A board that parsed to 29 or 31
    rows would build a label it does not match, and the fallthrough is silent
    and board-wide. Refusing is the whole point; padding the label to 30 would
    be the wrong fix."""
    label = f"Baseball America 2026 Blue Jays Top {n}"
    reason = ba.validate_org_label(label)
    assert reason and "implied_fv_from_rank" in reason


def test_the_guard_check_reads_the_live_regex_not_a_copy_of_its_sizes():
    """A copied list of accepted sizes is exactly what failed last time. If
    someone widens or narrows _ORG_LIST_LABEL_RE, this module must follow
    automatically."""
    import inspect
    src = inspect.getsource(ba.validate_org_label)
    assert "_ORG_LIST_LABEL_RE" in src
    for size in (10, 20, 25, 30):
        assert ba.validate_org_label(f"Baseball America 2026 Blue Jays Top {size}") is None


def test_a_global_top_100_label_would_not_be_treated_as_an_org_list():
    """The guard is deliberately narrow (Top 10/20/25/30 only). Confirm it does
    NOT fire on the Top 100 shape the tree already stores for this source, so
    this test cannot pass for the wrong reason."""
    assert not _ORG_LIST_LABEL_RE.search("Baseball America 2026-06-03 Top 100")


def test_source_string_matches_the_rows_already_in_the_database():
    """A second spelling reads as a second outlet to consensus and to
    source_backtest. The tree already carries 100 rows under this exact name."""
    assert ba.SOURCE == "baseballamerica"


# --------------------------------------------------------------------------
# Structure. A partial board is never ingested.
# --------------------------------------------------------------------------

def test_rank_lines_anchor_and_prose_numbers_do_not():
    """Anchoring on the headshot line drops rows (3 of 30 Orioles and 4 of 30
    Blue Jays have none). Anchoring loosely picks up prose: the real board says
    'the Blue Jays at pick No. 20\\.' inside a Track Record paragraph."""
    board = ba.parse_board(_BOARD, _META)
    assert [r["rank"] for r in board["rows"]] == [1, 2, 3]
    assert [r["player_name"] for r in board["rows"]] == [
        "Trey Yesavage", "Arjun Nimmala", "JoJo Parker"]


def test_non_contiguous_ranks_are_refused_rather_than_ingested_partially():
    broken = _BOARD.replace("3\\. JoJo Parker", "5\\. JoJo Parker")
    with pytest.raises(ba.BoardFormatError, match="contiguous"):
        ba.parse_board(broken, _META)


def test_a_header_count_that_disagrees_with_the_rows_is_refused():
    with pytest.raises(ba.BoardFormatError, match="partial board"):
        ba.parse_board("30 players\n" + _BOARD, _META)


def test_optional_fields_are_optional():
    """Previous Rank is on all 30 Orioles rows and absent from all 30 Blue Jays
    rows; Age is missing on 1-2 per board. Requiring either rejects a valid
    board."""
    board = ba.parse_board(_BOARD, _META)
    assert all(r["previous_rank"] is None for r in board["rows"])
    assert board["rows"][0]["age"] == 22


# --------------------------------------------------------------------------
# The grades.
# --------------------------------------------------------------------------

def test_fv_is_the_adjusted_grade_and_the_raw_grade_is_kept_beside_it():
    """Owner instruction: FV is the Adjusted Grade, never the raw one. Both are
    stored, because raw+risk resolves 11 cells against adjusted's 4-5 and
    because adjusted is a function of rank while raw is not."""
    row = ba.parse_board(_BOARD, _META)["rows"][0]
    assert row["fv"] == 55.0
    assert row["ba_raw_grade"] == 60.0
    assert row["ba_risk"] == "Mild"


def test_the_adjusted_grade_identity_is_recomputed_not_trusted():
    board = ba.parse_board(_BOARD, _META)
    assert all(r["adjusted_identity_ok"] for r in board["rows"])
    assert board["rows"][1]["adjusted_expected"] == 45.0  # 60 High, penalty 15


def test_a_board_that_breaks_the_identity_is_reported_not_silently_accepted():
    """A board that stops obeying adjusted = raw - penalty(risk) is a format
    change. Finding out later from a drifted FV is the expensive version."""
    tampered = _BOARD.replace("Adjusted Grade: 55", "Adjusted Grade: 50", 1)
    row = ba.parse_board(tampered, _META)["rows"][0]
    assert row["adjusted_identity_ok"] is False
    assert row["adjusted_expected"] == 55.0 and row["fv"] == 50.0


def test_risk_penalty_ladder():
    assert [ba.risk_penalty(r) for r in
            ("Low", "Mild", "Average", "High", "Extreme")] == [0, 5, 10, 15, 20]
    assert ba.risk_penalty(None) is None
    assert ba.risk_penalty("Unheard Of") is None


def test_a_row_with_no_adjusted_grade_is_rank_only_and_never_falls_back_to_raw():
    """A raw grade sitting in an FV column is a scale error no downstream layer
    can detect."""
    no_adj = _BOARD.replace("Adjusted Grade: 55\n", "", 1)
    row = ba.parse_board(no_adj, _META)["rows"][0]
    assert row["fv"] is None
    assert row["ba_raw_grade"] == 60.0


# --------------------------------------------------------------------------
# Tools.
# --------------------------------------------------------------------------

def test_tools_map_onto_the_canonical_keys_the_rest_of_the_tree_uses():
    from scrapers import ALL_TOOL_KEYS
    board = ba.parse_board(_BOARD, _META)
    yesavage, nimmala = board["rows"][0], board["rows"][1]
    assert yesavage["tools"] == {"fb": 60.0, "sl": 55.0, "ch": 70.0, "cmd": 50.0}
    assert nimmala["tools"] == {"hit": 45.0, "game_pwr": 55.0, "speed": 55.0,
                                "field": 55.0, "throw": 60.0}
    for row in board["rows"]:
        assert set(row["tools"]) <= set(ALL_TOOL_KEYS)


def test_split_and_sweeper_follow_the_just_baseball_precedent_already_in_the_tree():
    """scrapers.JB_TOOL_KEY already decided both for another source: splitter
    rides the changeup slot, sweeper rides the slider slot. Diverging here would
    make a BA splitter grade incomparable with a JB splitter grade inside the
    consensus, which is the whole purpose of a canonical vocabulary."""
    from scrapers import JB_TOOL_KEY
    assert ba.BA_TOOL_KEY["split"] == JB_TOOL_KEY["splitter"] == "ch"
    assert ba.BA_TOOL_KEY["sweeper"] == JB_TOOL_KEY["sweeper"] == "sl"


def test_the_untouched_ba_labels_are_kept_so_the_folding_stays_reversible():
    row = ba.parse_board(_BOARD, _META)["rows"][0]
    assert row["ba_tools_raw"]["split"] == 70.0
    assert row["ba_tools_raw"]["control"] == 50.0


def test_a_tool_slot_collision_is_surfaced_and_never_silently_overwritten():
    """A pitcher graded for both Changeup and Split would otherwise have one
    overwrite the other depending on dict order, invisibly."""
    both = _BOARD.replace("Scouting Grades: Fastball: 60 | Slider: 55 | Split: 70 | Control: 50",
                          "Scouting Grades: Fastball: 60 | Changeup: 45 | Split: 70 | Control: 50")
    row = ba.parse_board(both, _META)["rows"][0]
    assert row["tools"]["ch"] == 45.0
    assert any(i["kind"] == "slot_collision" for i in row["tool_issues"])


# --------------------------------------------------------------------------
# Dating. Boards are dated by CONTENT, never by label.
# --------------------------------------------------------------------------

def test_a_preseason_board_carrying_in_season_prose_is_refused():
    """The real hazard, caught on a real file: a board named for Preseason 2026
    carried mid-season content (2 of 30 said 'through mid-May', 4 said 'this
    year', 12 referenced 2026 in-season)."""
    dirty = _BOARD.replace(
        "Track Record: Over three seasons",
        "Track Record: Through mid-May he has hit .310 this year. Over three seasons")
    ev = ba.scan_content_dates(dirty, 2026)
    assert ev["in_season_count"] >= 2
    _, refusals = ba.resolve_snapshot_date(dict(_META), ev)
    assert refusals and "preseason" in refusals[0]


def test_the_genuinely_preseason_board_is_not_refused():
    """The discriminator has to be in-season PHRASING, not month names. This
    board says a player 'made his major league debut on Sept. 15' two
    paragraphs from 'enters 2026', and a naive month-plus-year scanner invents
    a phantom 2026-09-15 and rejects a good file."""
    ev = ba.scan_content_dates(_BOARD, 2026)
    assert ev["in_season_count"] == 0
    date_str, refusals = ba.resolve_snapshot_date(dict(_META), ev)
    assert refusals == []
    assert date_str == "2026-02-15"


def test_a_snapshot_date_earlier_than_an_explicit_in_content_date_is_refused():
    dated = _BOARD.replace("The Future: Yesavage enters 2026",
                           "The Future: As of June 12, 2026 he is healthy. Yesavage enters 2026")
    ev = ba.scan_content_dates(dated, 2026)
    assert ev["latest_explicit_date"] == "2026-06-12"
    _, refusals = ba.resolve_snapshot_date(dict(_META), ev)
    assert any("EARLIER than an explicit date" in r for r in refusals)


def test_an_explicit_publication_date_in_the_filename_beats_the_convention():
    meta = ba.parse_filename("ba__2026__preseason__blue-jays__2026-02-03.md")
    assert meta["pubdate"] == "2026-02-03"
    date_str, refusals = ba.resolve_snapshot_date(meta, ba.scan_content_dates(_BOARD, 2026))
    assert date_str == "2026-02-03" and refusals == []


def test_the_pre_2017_scale_hazard_is_stamped():
    """FanGraphs in this database starts 2017-02-15, so a pre-2017 BA board has
    no contemporaneous reference for grade_normalization and the thin-cell
    fallback pools across FUTURE years. That is leak D1 on a new source."""
    meta = ba.parse_filename("ba__2015__preseason__blue-jays.md")
    date_str, _ = ba.resolve_snapshot_date(meta, ba.scan_content_dates("", 2015))
    assert date_str < "2017-02-15"


# --------------------------------------------------------------------------
# Filename. It is load-bearing, not cosmetic.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "ba__2026__preseason__blue-jays.md",
    "ba__2025__midseason__red-sox.md",
    "ba__2024__offseason__white-sox.md",
    "ba__2026__preseason__d-backs.md",
])
def test_valid_filenames_parse_including_hyphenated_clubs(name):
    """Double underscores are what let a hyphenated club slug survive."""
    assert ba.parse_filename(name) is not None


@pytest.mark.parametrize("name", [
    "ba__2026__preseason__blue_jays.md",     # single underscore in the team
    "ba__2026__spring__blue-jays.md",        # not a board
    "ba__2026__preseason__gothams.md",       # not a club
    "orioles.md",
])
def test_malformed_filenames_are_refused(name):
    assert ba.parse_filename(name) is None


def test_club_table_is_not_duplicated_in_this_module():
    """One club table in the tree. A second copy drifts the first time a club
    renames, which has already happened once (the Athletics dropped Oakland)."""
    src = (ba.__file__ and open(ba.__file__, encoding="utf-8").read()) or ""
    assert "from build_site import ORG_NAMES" in src
    assert not re.search(r'"BAL"\s*:\s*"Orioles"', src)


# --------------------------------------------------------------------------
# Identity. Never guess.
# --------------------------------------------------------------------------

def test_snapshots_are_only_built_for_rows_with_a_settled_identity():
    """A confident wrong resolution is worse than a missing row, and this repo
    has three recorded incidents to prove it."""
    board = ba.parse_board(_BOARD, {**_META, "snapshot_date": "2026-02-15"})
    board["meta"]["interval_label"] = "Baseball America 2026 Blue Jays Top 3"
    for r in board["rows"]:
        r["player_key"] = None
    assert ba.to_snapshots(board) == []
    board["rows"][0]["player_key"] = "trey_yesavage"
    snaps = ba.to_snapshots(board)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.source == "baseballamerica" and s.rank == 1 and s.fv == 55.0
    assert s.org == "TOR" and s.position == "RHP"
    assert s.tools["_extras"]["ba_raw_grade"] == 60.0
    assert s.tools["_extras"]["ba_risk"] == "Mild"


def test_multi_position_keeps_the_primary_and_the_full_string():
    multi = _BOARD.replace("\nSS\n", "\nSS / 2B\n", 1)
    row = ba.parse_board(multi, _META)["rows"][1]
    assert row["position"] == "SS" and row["position_full"] == "SS / 2B"


# --------------------------------------------------------------------------
# Fixtures. A trimmed but UNEDITED slice of the real Blue Jays board, so the
# parser is tested against what BA actually emits. Do not tidy it.
# --------------------------------------------------------------------------

_META = {"season": 2026, "board": "preseason", "team_slug": "blue-jays",
         "org": "TOR", "team_name": "Blue Jays", "pubdate": None}


def _full_board(n: int) -> str:
    """Grow the real 3-row slice to a full-size board by repeating its last
    entry. Only the ROW COUNT matters to the tests that use this; the field
    parsing is covered against the unedited slice."""
    head = _BOARD.rstrip("\n")
    tail = []
    for rank in range(4, n + 1):
        tail.append(
            f"{rank}\\. Filler Player{rank}\nOF\n\n"
            f"Ht: 6'0\" | Wt: 190 | B-T: R-R\n\nAge: 21\n\n"
            f"BA Grade/Risk: 45/Mild\n\nAdjusted Grade: 40\n\n"
            f"Scouting Grades: Hit: 45 | Power: 45 | Run: 50 | Field: 50 | Arm: 50")
    return head + "\n" + "\n".join(tail) + "\n"

_BOARD = """Expand all
Collapse all
Headshot of Trey Yesavage
1\\. Trey Yesavage
RHP

Ht: 6'4" | Wt: 225 | B-T: R-R

Age: 22

BA Grade/Risk: 60/Mild

Adjusted Grade: 55

Track Record: Over three seasons at East Carolina, Yesavage went from a reliever to a key piece of the rotation. After Yesavage ranked as the No. 11 player in the 2024 class, questions around his medicals dropped him to the Blue Jays at pick No. 20\\. He signed for a little over $4.75 million and made his major league debut on Sept. 15\\.

The Future: Yesavage enters 2026 as an American League Rookie of the Year frontrunner and key part of the rotation.

Scouting Grades: Fastball: 60 | Slider: 55 | Split: 70 | Control: 50
Headshot of Arjun Nimmala
2\\. Arjun Nimmala
SS

Ht: 6'1" | Wt: 170 | B-T: R-R

Age: 20

BA Grade/Risk: 60/High

Adjusted Grade: 45

The Future: Nimmala will look to find more consistency at the plate in 2026. Double-A is next.

Scouting Grades: Hit: 45 | Power: 55 | Run: 55 | Field: 55 | Arm: 60
3\\. JoJo Parker
SS

Ht: 6'2" | Wt: 200 | B-T: L-R

Age: 19

BA Grade/Risk: 60/High

Adjusted Grade: 45

The Future: Parker projects as an above-average regular at third base.

Scouting Grades: Hit: 55 | Power: 55 | Run: 50 | Field: 50 | Arm: 55
"""
