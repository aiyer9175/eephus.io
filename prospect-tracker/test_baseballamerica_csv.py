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


@pytest.mark.parametrize("slug,team", [
    ("angels", "Angels"), ("astros", "Astros"), ("athletics", "Athletics"),
    ("blue-jays", "Blue Jays"), ("braves", "Braves"), ("brewers", "Brewers"),
    ("cardinals", "Cardinals"), ("cubs", "Cubs"), ("d-backs", "Diamondbacks"),
    ("dodgers", "Dodgers"), ("giants", "Giants"), ("guardians", "Guardians"),
    ("mariners", "Mariners"), ("marlins", "Marlins"), ("mets", "Mets"),
    ("nationals", "Nationals"), ("orioles", "Orioles"), ("padres", "Padres"),
    ("phillies", "Phillies"), ("pirates", "Pirates"), ("rangers", "Rangers"),
    ("rays", "Rays"), ("red-sox", "Red Sox"), ("reds", "Reds"),
    ("rockies", "Rockies"), ("royals", "Royals"), ("tigers", "Tigers"),
    ("twins", "Twins"), ("white-sox", "White Sox"), ("yankees", "Yankees"),
])
def test_all_thirty_clubs_build_a_label_the_org_list_guard_matches(slug, team):
    """A FULL SLATE, not a sample. The guard is the only thing keeping a team
    Top 30 out of implied_fv_from_rank, and it is matched by a regex anchored to
    end of string, so a single club whose name renders differently would drop
    that org's ranks through and make its number-one prospect a rank-implied
    FV 70. All 30 are checked, including the four hyphenated slugs and the
    Athletics, whose club name changed once already."""
    meta = ba.parse_filename(f"ba__2026__midseason__{slug}__2026-08-01.md")
    assert meta is not None, f"{slug} did not parse as a club slug"
    assert meta["team_name"] == team
    board = ba.parse_board(_full_board(30), meta)
    label = board["meta"]["interval_label"]
    assert label == f"Baseball America 2026 Midseason {team} Top 30"
    assert _ORG_LIST_LABEL_RE.search(label)
    assert ba.validate_org_label(label) is None
    # The label is also read for the org, so the qualifier must not displace the
    # club name for any of the 30.
    from trades import canonical_org
    assert canonical_org(label), f"{label!r} no longer resolves to an org"


def test_a_second_board_in_one_season_does_not_upsert_onto_the_first():
    """CAUGHT BEFORE ANY WRITE, 2026-08-09. insert_ba_snapshots conflicts on
    (source, interval_label, player_key) and its DO UPDATE overwrites
    snapshot_date, rank and fv. Under a season-only label the 2026 midseason
    slate and the 2026 preseason slate are the SAME KEY, so ingesting the second
    rewrites the first in place rather than adding a vintage beside it.

    Measured on the real drop: 259 of the 383 stored 2026-02-15 rows across all
    13 boards present in both slates, FV changing on 99 of them, mean |delta|
    2.10 FV and max 15.0. The 2026 preseason vintage would have gone from 383
    rows to 124 with nothing reporting it."""
    pre = ba.parse_board(_full_board(30), {**_META, "board": "preseason"})
    mid = ba.parse_board(_full_board(30), {**_META, "board": "midseason"})
    off = ba.parse_board(_full_board(30), {**_META, "board": "offseason"})
    labels = [b["meta"]["interval_label"] for b in (pre, mid, off)]
    assert len(set(labels)) == 3, f"boards share an upsert key: {labels}"
    for lab in labels:
        assert _ORG_LIST_LABEL_RE.search(lab), f"{lab!r} lost the org-list guard"
        assert ba.validate_org_label(lab) is None


def test_the_preseason_label_keeps_its_stored_form_so_52_boards_are_not_orphaned():
    """The bare form is what four vintages and 52 boards are already stored
    under. Changing it would make the next preseason drop insert duplicates
    beside them instead of upserting onto them. Relabelling those rows is a
    migration with its own gate, not a side effect of this ingest."""
    pre = ba.parse_board(_full_board(30), {**_META, "board": "preseason"})
    assert pre["meta"]["interval_label"] == "Baseball America 2026 Blue Jays Top 30"


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


def test_a_large_rank_gap_is_refused_as_a_truncated_paste():
    """Two of five ranks absent is not a publishing quirk."""
    broken = _BOARD.replace("3\\. JoJo Parker", "5\\. JoJo Parker")
    with pytest.raises(ba.BoardFormatError, match="truncated paste"):
        ba.parse_board(broken, _META)


def test_the_same_player_twice_is_always_refused():
    """ONE PLAYER at TWO ranks is the Jack Natili failure (ranks 155 and 320,
    surplus double counted at $16.7M plus $3.8M). This never becomes legal.

    Split out of the old `test_duplicate_ranks_are_always_refused` on
    2026-08-10. That test asserted a blanket rule, and the blanket was wrong in
    one direction: see the sibling test below. The hazard it was actually
    written for is this one, and it is unchanged."""
    dupe = _BOARD.replace("3\\. JoJo Parker", "2\\. JoJo Parker")
    # Make BOTH rank-2 rows the same human, which is the double-count shape.
    dupe = re.sub(r"^2\\\. (?!JoJo Parker)\S.*$", "2\\\\. JoJo Parker", dupe,
                  count=1, flags=re.M)
    with pytest.raises(ba.BoardFormatError, match="SAME player twice"):
        ba.parse_board(dupe, _META)


def test_two_different_players_at_one_rank_ingest_with_a_named_warning():
    """BA printing one rank number on TWO DIFFERENT players is a publisher
    typo, not a double count, and refusing it threw away a whole board.

    The real case: the 2025 Braves board, 31 blocks, header "31 players",
    ranks 1..30 with 26 on both Trent Harris and Carter Holton. Two distinct
    humans.

    Neither is renumbered. Which of them is "really" 27 is not recoverable from
    the file, and rank is the one field the board exists to publish, so
    inferring an order would be fabricating it. Both keep the rank BA printed
    and the defect is named in the artifact.

    The label must still read Top 30, NOT Top 31: taking the row count would
    leave consensus._ORG_LIST_LABEL_RE unmatched, drop the ranks into
    implied_fv_from_rank and reproduce the Bryan Sanchez failure by a route
    nobody would look for."""
    # Reproduce the Braves shape exactly: 31 blocks, ranks 1..30, one number
    # printed on two DIFFERENT players. Built by inserting an extra block at 26
    # rather than by renumbering, so the board still reaches rank 30.
    extra = ("26\\. Second Player26\nOF\n\n"
             "Ht: 6'0\" | Wt: 190 | B-T: R-R\n\nAge: 21\n\n"
             "BA Grade/Risk: 45/Mild\n\nAdjusted Grade: 40\n\n"
             "Scouting Grades: Hit: 45 | Power: 45 | Run: 50 | Field: 50 | Arm: 50\n")
    full = _full_board(30)
    dupe = full.replace("27\\. Filler Player27", extra + "27\\. Filler Player27")
    board = ba.parse_board(dupe, _META)
    meta = board["meta"]
    assert meta["n_players"] == 31, "both players are kept"
    assert meta["duplicate_rank"], "the defect must be named, not swallowed"
    assert "26" in meta["duplicate_rank"]
    assert any("duplicate_rank_distinct_players" in w
               for w in meta["parse_warnings"])
    # The label keeps org-list protection: Top 30, never Top 31.
    assert meta["board_size"] == 30
    assert meta["interval_label"].endswith("Top 30")
    assert ba.validate_org_label(meta["interval_label"]) is None
    # Both humans survive to the snapshot layer at the rank BA printed.
    ranks26 = [r["rank"] for r in board["rows"] if r["rank"] == 26]
    assert len(ranks26) == 2


def test_one_missing_rank_is_kept_verbatim_and_still_labels_as_a_top_30():
    """The real 2023 Twins board: 29 players across ranks 1..30 with slot 18
    vacant, and BA's own header says 29 where every other board says 30.

    The published ranks are kept as published. Renumbering 19..30 down to
    18..29 would close the gap but invent ranks BA never issued, and rank is
    the whole reason this data is worth having. Labelling it "Top 29" would
    also leave consensus._ORG_LIST_LABEL_RE unmatched and drop its ranks into
    implied_fv_from_rank, which is the Bryan Sanchez failure."""
    board = ba.parse_board(_full_board(30).replace("18\\. Filler Player18\n", ""), _META)
    meta = board["meta"]
    assert meta["n_players"] == 29
    assert meta["missing_ranks"] == [18]
    assert meta["interval_label"] == "Baseball America 2026 Blue Jays Top 30"
    assert ba.validate_org_label(meta["interval_label"]) is None
    assert [r["rank"] for r in board["rows"]][16:19] == [17, 19, 20]


def test_a_header_count_that_disagrees_with_the_rows_is_refused():
    with pytest.raises(ba.BoardFormatError, match="partial board"):
        ba.parse_board("30 players\n" + _BOARD, _META)


# --------------------------------------------------------------------------
# The unpopulated header counter. Both directions are pinned, because the
# carve-out is only safe if it stays narrow.
# --------------------------------------------------------------------------

def test_a_header_claiming_zero_over_contiguous_ranks_is_accepted_and_flagged():
    """Real case, the 2026 midseason Padres board: line 1 read "0 players" where
    all 29 sibling boards read "30 players", over 30 contiguous rank lines with
    full grades. BA renders that counter from a script, so a paste taken before
    it populated captures the zero.

    Zero is not a count 30 rows could be a truncation of, so it carries no
    information about completeness, and contiguous ranks 1..N are the
    independent evidence that nothing is missing. It is accepted, and it is
    stamped so the artifact says so rather than passing in silence."""
    board = ba.parse_board("0 players\n" + _full_board(30), _META)
    assert board["meta"]["n_players"] == 30
    assert board["meta"]["declared_players"] == 0
    assert board["meta"]["header_count_unpopulated"] is True
    assert any("header_count_unpopulated" in w
               for w in board["meta"]["parse_warnings"])


def test_a_genuine_count_disagreement_is_still_refused_even_over_contiguous_ranks():
    """25-vs-30 is the case the carve-out must NOT swallow. Both numbers are
    real and they disagree, so one of them is wrong about the board. Contiguity
    does not rescue it: this board's ranks are contiguous 1..30 and it still
    refuses."""
    with pytest.raises(ba.BoardFormatError, match="claims 25 players but 30"):
        ba.parse_board("25 players\n" + _full_board(30), _META)


@pytest.mark.parametrize("declared", [1, 25, 29, 31, 100])
def test_every_nonzero_header_mismatch_still_refuses(declared):
    """The carve-out keys on the claim being EXACTLY 0. Any other disagreement,
    above or below the parsed count, refuses exactly as before."""
    with pytest.raises(ba.BoardFormatError, match="partial board"):
        ba.parse_board(f"{declared} players\n" + _full_board(30), _META)


def test_a_zero_header_over_NON_contiguous_ranks_is_still_refused():
    """The carve-out needs BOTH halves. A zero header over a board with a hole
    in it has no independent evidence of completeness, so the strict guard has
    to keep firing. This is the mutation that proves the second condition is
    load-bearing rather than decorative."""
    holed = _full_board(30).replace("18\\. Filler Player18\n", "")
    with pytest.raises(ba.BoardFormatError, match="claims 0 players but 29"):
        ba.parse_board("0 players\n" + holed, _META)


def test_a_clean_board_is_never_flagged_as_having_an_unpopulated_header():
    """So the flag cannot pass for the wrong reason."""
    board = ba.parse_board("30 players\n" + _full_board(30), _META)
    assert board["meta"]["header_count_unpopulated"] is False
    assert board["meta"]["parse_warnings"] == []


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


@pytest.mark.parametrize("season,expected", [
    (2022, "raw"), (2023, "raw"), (2024, "raw"), (2025, "raw"),
    (2026, "adjusted"), (2027, "adjusted"),
])
def test_the_fv_basis_switches_at_the_season_ba_introduced_adjusted_grades(season, expected):
    """BA introduced the Grade/Risk-to-Adjusted-Grade system for 2026. Measured
    in this corpus: an Adjusted Grade line appears on 390 of 390 rows in 2026
    and 0 of 1,140 in 2023-2025. So each era has exactly one FV-equivalent and
    using the BA Grade before 2026 is not a fallback, it is the only grade that
    existed."""
    assert ba.fv_basis(season) == expected


def test_a_pre_2026_board_takes_the_raw_grade_as_its_fv():
    meta = {**_META, "season": 2025}
    row = ba.parse_board(_BOARD.replace("Adjusted Grade: 55\n", "", 1), meta)["rows"][0]
    assert row["fv"] == 60.0 and row["ba_raw_grade"] == 60.0
    assert row["fv_basis"] == "raw"


def test_a_2026_board_still_takes_the_adjusted_grade_and_not_the_raw_one():
    """The eras must not bleed. A 2026 row has both numbers present and the
    adjusted one is 15 points lower here, so picking the wrong field is a
    15-point FV error that nothing downstream could detect."""
    row = ba.parse_board(_BOARD, _META)["rows"][1]
    assert row["ba_raw_grade"] == 60.0
    assert row["fv"] == 45.0
    assert row["fv_basis"] == "adjusted"


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


@pytest.mark.parametrize("line,expect_slot,expect_variant", [
    # The native pitch first, which is the order BA used on all 35 colliding
    # rows of the 2026 midseason drop.
    ("Fastball: 60 | Slider: 45 | Sweeper: 55 | Control: 50", ("sl", 45.0), ("sweeper", 55.0)),
    # The SAME row with the two pitches swapped. Under the old first-wins rule
    # this put the sweeper's 55 into `sl` and evicted the real slider.
    ("Fastball: 60 | Sweeper: 55 | Slider: 45 | Control: 50", ("sl", 45.0), ("sweeper", 55.0)),
    ("Fastball: 60 | Changeup: 40 | Split: 55 | Control: 50", ("ch", 40.0), ("split", 55.0)),
    ("Fastball: 60 | Split: 55 | Changeup: 40 | Control: 50", ("ch", 40.0), ("split", 55.0)),
])
def test_the_pitch_that_owns_the_slot_keeps_it_whatever_order_ba_printed_them(
        line, expect_slot, expect_variant):
    """THE ACTUAL DEFECT, and it was latent rather than live. Slot ownership used
    to be first-wins in file order. On the 2026 midseason drop the native pitch
    happened to be printed first on 35 of 35 colliding rows, so the shipped
    result was right by luck; a board printing Sweeper first would have put a
    sweeper grade in `sl` board-wide with nothing downstream able to tell.

    A real slider keeps `sl` and a real changeup keeps `ch` in BOTH orders, and
    the displaced grade is returned rather than discarded."""
    tools, raw, issues, variants = ba._map_tools(line)
    slot, grade = expect_slot
    assert tools[slot] == grade
    label, vgrade = expect_variant
    assert variants[slot] == {label: vgrade}
    coll = [i for i in issues if i["kind"] == "slot_collision"]
    assert len(coll) == 1
    assert coll[0]["kept"] == grade and coll[0]["dropped"] == vgrade
    assert coll[0]["label"] == label


def test_the_displaced_pitch_grade_reaches_the_snapshot_and_is_not_lost():
    """Nothing BA published is discarded. The variant rides `_extras`, the same
    channel ba_raw_grade already uses, keyed by the slot it was displaced from."""
    both = _BOARD.replace("Slider: 55 | Split: 70", "Slider: 55 | Sweeper: 40 | Split: 70")
    board = ba.parse_board(both, {**_META, "snapshot_date": "2026-02-15"})
    board["meta"]["interval_label"] = "Baseball America 2026 Blue Jays Top 3"
    board["rows"][0]["player_key"] = "trey_yesavage"
    for r in board["rows"][1:]:
        r["player_key"] = None
    snap = ba.to_snapshots(board)[0]
    assert snap.tools["sl"] == 55.0                      # the real slider keeps the slot
    assert snap.tools["_extras"]["ba_tool_variants"] == {"sl": {"sweeper": 40.0}}
    assert snap.tools["_extras"]["ba_tools_raw"]["sweeper"] == 40.0


def test_no_new_top_level_tools_key_is_minted_for_a_folded_pitch():
    """A `sw` key would enter numeric tool aggregation as if it were a sixth
    pitch (consensus.py skips exactly `_extras` and nothing else), and it would
    break this module's own role inference, which tests
    set(tools) <= set(PITCHER_TOOL_KEYS). So the variant stays inside _extras."""
    from scrapers import ALL_TOOL_KEYS
    tools, _raw, _issues, variants = ba._map_tools(
        "Fastball: 60 | Slider: 45 | Sweeper: 55 | Split: 50 | Changeup: 40")
    assert set(tools) <= set(ALL_TOOL_KEYS)
    assert set(tools) == {"fb", "sl", "ch"}
    assert variants == {"sl": {"sweeper": 55.0}, "ch": {"split": 50.0}}


def test_two_labels_agreeing_on_one_grade_are_not_reported_as_a_collision():
    """Same number under two names loses no information. The variant is still
    recorded, but a collision report would be noise."""
    tools, _raw, issues, variants = ba._map_tools("Slider: 50 | Sweeper: 50")
    assert tools["sl"] == 50.0
    assert variants == {"sl": {"sweeper": 50.0}}
    assert not [i for i in issues if i["kind"] == "slot_collision"]


def test_slot_resolution_is_deterministic_and_not_a_function_of_input_order():
    """Fixed seeds and no iteration order from a set. Every permutation of the
    same grades must produce byte-identical output."""
    import itertools, json
    parts = ["Fastball: 60", "Slider: 45", "Sweeper: 55", "Control: 50"]
    outs = set()
    for perm in itertools.permutations(parts):
        tools, _raw, issues, variants = ba._map_tools(" | ".join(perm))
        outs.add(json.dumps([tools, issues, variants], sort_keys=True))
    assert len(outs) == 1, f"{len(outs)} distinct results across 24 permutations"


# --------------------------------------------------------------------------
# FORMAT DRIFT. Every case below is a real variation measured across the 52
# owner-supplied 2023-2026 org boards, and every one of them silently lost a
# whole season's worth of a field before it was handled.
# --------------------------------------------------------------------------

def test_the_scouting_grades_colon_is_optional():
    """11 of 13 2026 boards write 'Scouting Grades Hit: 45 | ...' with no
    colon. Requiring it lost their tools entirely, same season, same
    publisher."""
    nocolon = _BOARD.replace("Scouting Grades: Fastball:", "Scouting Grades Fastball:")
    row = ba.parse_board(nocolon, _META)["rows"][0]
    assert row["tools"] == {"fb": 60.0, "sl": 55.0, "ch": 70.0, "cmd": 50.0}


def test_the_2023_period_separator_parses():
    """2023 separates tools with a markdown-escaped period rather than a pipe:
    'Hitting: 60\\. Power: 60\\. Speed: 55\\. Fielding: 50\\. Arm: 45\\.'
    Splitting on the pipe returned nothing for the whole season."""
    line = "Scouting Grades: Hitting: 60\\. Power: 60\\. Speed: 55\\. Fielding: 50\\. Arm: 45\\."
    board = _BOARD.replace(
        "Scouting Grades: Hit: 45 | Power: 55 | Run: 55 | Field: 55 | Arm: 60", line)
    row = ba.parse_board(board, _META)["rows"][1]
    assert row["tools"] == {"hit": 60.0, "game_pwr": 60.0, "speed": 55.0,
                            "field": 50.0, "throw": 45.0}


@pytest.mark.parametrize("label,canonical", [
    ("Hitting", "hit"), ("Fielding", "field"), ("Speed", "speed"),
    ("Throw", "throw"), ("Splitter", "ch"), ("Comtrol", "cmd"), ("CUT", "ct"),
])
def test_label_variants_and_ba_typos_map_to_canonical_keys(label, canonical):
    """BA's own labels drift by season and include two real typos, Comtrol and
    FIeld. Dropping those rows' grades to keep a tidy table is the wrong
    trade: a human wrote them and the grade is still a grade."""
    tools, raw, issues, _variants = ba._map_tools(f"{label}: 55")
    assert tools == {canonical: 55.0}
    assert not [i for i in issues if i["kind"] == "unmapped_label"]


@pytest.mark.parametrize("line,expect_risk", [
    ("BA Grade/Risk: 60/High", "High"),        # 2023 and 2026
    ("BA Grade/Risk: 60/High.", "High"),       # 2025 adds a trailing period
    ("BA Grade: 60/High", "High"),             # 2024 renames the field
    ("BA Grade/Risk: 60/Very High", "Very High"),   # two-word label
])
def test_the_grade_field_survives_every_season_spelling(line, expect_risk):
    """Four seasons, four spellings. A single-word risk capture truncated
    'Very High' to 'Very' on 11 boards, and the anchored form rejected 2025's
    trailing period, dropping its raw grade from 390 rows to 2."""
    board = _BOARD.replace("BA Grade/Risk: 60/Mild", line)
    row = ba.parse_board(board, _META)["rows"][0]
    assert row["ba_raw_grade"] == 60.0
    assert row["ba_risk"] == expect_risk


def test_the_older_risk_vocabulary_is_known_but_carries_no_invented_penalty():
    """2023-2025 use Low/Medium/High/Very High/Extreme; 2026 uses
    Low/Mild/Average/High/Extreme. The 2026 ladder is verified exactly (390 of
    390). The older one cannot be verified, because those seasons publish no
    Adjusted Grade to solve against, so no penalty is guessed for it."""
    assert {"medium", "very high"} <= ba.KNOWN_RISK_LABELS
    assert ba.risk_penalty("Medium") is None
    assert ba.risk_penalty("Very High") is None
    assert ba.risk_penalty("Average") == 10.0


def test_a_row_with_no_adjusted_grade_is_not_counted_as_an_identity_failure():
    """Not checkable is a different fact from checked-and-wrong. Collapsing
    them reported 927 phantom failures across the 2023-2025 boards, which
    publish a raw grade and a risk but no adjusted grade at all."""
    no_adj = _BOARD.replace("Adjusted Grade: 55\n", "", 1)
    row = ba.parse_board(no_adj, _META)["rows"][0]
    assert row["adjusted_identity_ok"] is None
    # The expectation is still computed and stored, so the row stays auditable.
    assert row["adjusted_expected"] == 55.0
    assert row["fv"] is None and row["ba_raw_grade"] == 60.0


# --------------------------------------------------------------------------
# Dating. Boards are dated by CONTENT, never by label.
# --------------------------------------------------------------------------

def test_in_season_prose_warns_and_does_not_block():
    """DEMOTED FROM A REFUSAL, on evidence. This shipped as a hard refusal on
    the strength of one known-bad file, and then refused 39 of 52 genuinely
    preseason org boards. Every hit that could be read by hand was legitimate:
    a preseason board describing the season just finished ("Through April and
    May, he produced an OPS of .621") or projecting the one about to start
    ("in the Dominican Summer League later this year"). Those are the two
    things a preseason board is for, so the phrasing cannot separate them from
    a mis-dated file, and density does not either (the known-bad file carried
    6 markers, a genuine 2023 board carries 5)."""
    dirty = _BOARD.replace(
        "Track Record: Over three seasons",
        "Track Record: Through mid-May he has hit .310 this year. Over three seasons")
    ev = ba.scan_content_dates(dirty, 2026)
    assert ev["in_season_count"] >= 2
    _, refusals, warnings = ba.resolve_snapshot_date(dict(_META), ev)
    assert refusals == [], "in-season prose must not block ingestion"
    assert warnings and "in-season prose marker" in warnings[0]


def test_the_genuinely_preseason_board_is_not_flagged_at_all():
    """The board says a player 'made his major league debut on Sept. 15' two
    paragraphs from 'enters 2026'. A month-plus-year scanner would invent a
    phantom 2026-09-15 and reject a good file."""
    ev = ba.scan_content_dates(_BOARD, 2026)
    assert ev["in_season_count"] == 0
    date_str, refusals, warnings = ba.resolve_snapshot_date(dict(_META), ev)
    assert refusals == [] and warnings == []
    assert date_str == "2026-02-15"


def test_a_snapshot_date_earlier_than_an_explicit_in_content_date_is_refused():
    """The one date check that DOES still refuse, because it is unambiguous:
    an explicit 'June 12, 2026' inside a board dated 2026-02-15 is a
    contradiction, not a turn of phrase. Zero false positives across 52 real
    boards."""
    dated = _BOARD.replace("The Future: Yesavage enters 2026",
                           "The Future: As of June 12, 2026 he is healthy. Yesavage enters 2026")
    ev = ba.scan_content_dates(dated, 2026)
    assert ev["latest_explicit_date"] == "2026-06-12"
    _, refusals, _w = ba.resolve_snapshot_date(dict(_META), ev)
    assert any("EARLIER than an explicit date" in r for r in refusals)


def test_a_future_year_in_the_prose_is_not_a_refusal():
    """Removed rather than softened. Scouting prose names future years
    constantly (Rule 5 eligibility, free agency, club control), and refusing on
    it cost 17 of 52 boards. One real board legitimately mentions 2034."""
    fut = _BOARD.replace("The Future: Yesavage enters 2026",
                         "The Future: He is under club control through 2034. Yesavage enters 2026")
    ev = ba.scan_content_dates(fut, 2026)
    assert ev["max_year_referenced"] == 2034
    _, refusals, _w = ba.resolve_snapshot_date(dict(_META), ev)
    assert refusals == []


def test_an_explicit_publication_date_in_the_filename_beats_the_convention():
    meta = ba.parse_filename("ba__2026__preseason__blue-jays__2026-02-03.md")
    assert meta["pubdate"] == "2026-02-03"
    date_str, refusals, _w = ba.resolve_snapshot_date(meta, ba.scan_content_dates(_BOARD, 2026))
    assert date_str == "2026-02-03" and refusals == []


def test_the_pre_2017_scale_hazard_is_stamped():
    """FanGraphs in this database starts 2017-02-15, so a pre-2017 BA board has
    no contemporaneous reference for grade_normalization and the thin-cell
    fallback pools across FUTURE years. That is leak D1 on a new source."""
    meta = ba.parse_filename("ba__2015__preseason__blue-jays.md")
    date_str, _r, _w = ba.resolve_snapshot_date(meta, ba.scan_content_dates("", 2015))
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


def test_the_short_name_spellings_resolve_through_the_alias_table_only():
    """BA prints "Eric Booth" where the database holds "Eric Booth Jr.", and 15
    rows of the 2026 midseason drop are that shape. They are settled through
    consensus.PLAYER_KEY_ALIASES, which canonicalises at READ time and is undone
    by deleting its entry, NEVER through a DB key remap. That prohibition has
    three recorded incidents behind it, and the Jack Natili survey also found the
    remap would have thrown on 23 of 30 rows because both keys held snapshots on
    the same dates under PK(player_key, snapshot_date)."""
    import inspect
    from consensus import PLAYER_KEY_ALIASES
    src = inspect.getsource(ba.resolve_identities)
    assert "PLAYER_KEY_ALIASES" in src, "resolution must read the shared table"

    # BEHAVIOURAL, not just structural. A source-text assertion survives the
    # lookup being deleted while the import and the comment stay behind, which a
    # mutation run demonstrated, so the resolution itself is exercised here.
    out = ba.resolve_identities(
        [{"rank": 1, "player_name": "Eric Booth"},
         {"rank": 2, "player_name": "Eli Serrano"}], "BAL")
    assert out["n_unresolved"] == 0, out["unresolved"]
    keys = {r["player_name"]: r["player_key"] for r in out["resolved"]}
    assert keys["Eric Booth"] == "eric_booth_jr"
    assert keys["Eli Serrano"] == "eli_serrano_iii"
    assert all(r["resolution"].startswith("alias_key") for r in out["resolved"])

    for short, full in [("eric_booth", "eric_booth_jr"),
                        ("eli_serrano", "eli_serrano_iii"),
                        ("james_tibbs", "james_tibbs_iii"),
                        ("miguel_sime", "miguel_sime_jr"),
                        ("enrique_bradfield", "enrique_bradfield_jr")]:
        assert PLAYER_KEY_ALIASES[short]["player_key"] == full


def test_the_three_names_that_failed_the_admission_bar_stay_unresolved():
    """A confident wrong resolution is worse than a missing row. BA's Pirates
    rank 7 "Triston Gray" is one letter from the database's `tristan_gray` and
    is a different human: 22 against 30, R-R against L-R, PIT against a player
    last seen at TBR in 2023. BA's own capsule says "Gray, whose first name is
    Triston". If any of these three ever gets an alias it has to be argued on
    evidence, not inherited from this drop."""
    from consensus import PLAYER_KEY_ALIASES
    for k in ("triston_gray", "michael_addari", "kyle_jones"):
        assert k not in PLAYER_KEY_ALIASES


def test_every_alias_target_names_the_player_the_database_already_stores():
    """CANONICAL_PLAYER_NAMES is built from this table and overrides the served
    display name, so a typo in a value silently renames a player on the board."""
    from consensus import PLAYER_KEY_ALIASES
    for short, alias in PLAYER_KEY_ALIASES.items():
        assert alias["player_key"] and alias["player_name"]
        assert alias["player_key"] != short, f"{short} aliases to itself"
        # No chains: an alias target must not itself be an alias source, or the
        # single read-time canonicalisation pass would leave it half-resolved.
        assert alias["player_key"] not in PLAYER_KEY_ALIASES


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


# ==========================================================================
# AMATEUR DRAFT BOARDS. A different format, a different table, and the one
# place where a mistake reaches the served prospect board.
# ==========================================================================

_DRAFT_META = {"season": 2027, "class_year": 2027, "board": "draft",
               "team_slug": "top-100", "pubdate": "2026-07-15", "org": None,
               "team_name": None, "scope": "Top 100", "scope_extent": 100,
               "pool": None, "rank_is_global": True, "is_global": False,
               "is_draft": True, "snapshot_date": "2026-07-15"}

# An UNEDITED slice of the real 2027 boards, including the paste artifact that
# broke the first version of this parser. Do not tidy it.
_DRAFT_BOARD = """3 players
Expand all
Collapse all
1\\. Dylan Seward
SS

Ht: 6'0" | Wt: 175 | B-T: B-R

School: Norco (Calif.) HS
Committed/Drafted: Tennessee
Age At Draft: 18.8

Seward is a quick-twitch, explosive athlete with a well-rounded blend of skills.
2\\. Gavin Kelly
C / 2B

Ht: 6'0" | Wt: 175 | B-T: R-R

School: West Virginia
Committed/Drafted: Never Drafted
Age At Draft: 21.6

Kelly flashed impressive hitting traits and defensive versatility as a freshman.
3\\. Kyle Alivo
RHP

Ht: 6'1" | Wt: 175 | B-T: R-R

School: Iowa
Committed/Drafted:

A two-way player for Iowa whose future lies on the mound, Alivo had surgery.
"""


def _draft_board(meta=None):
    return ba.parse_draft_board(_DRAFT_BOARD, {**_DRAFT_META, **(meta or {})})


# --------------------------------------------------------------------------
# THE HARD REQUIREMENT. An amateur must never reach the active prospect pool.
# --------------------------------------------------------------------------

def test_a_draft_board_writes_zero_rows_to_snapshots(tmp_path, monkeypatch):
    """An amateur in `snapshots` joins the active prospect pool, and from there
    consensus FV, the prospect board and the trade machine.

    This drives the REAL entry point (ingest_drops with apply=True) rather than
    a helper, because this repo has a recorded case of a "load-bearing" test
    that passed with its own module deleted. Everything below the CLI runs:
    filename parsing, dating, parse_draft_board, key minting, the storage
    writer.
    """
    import storage

    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "ba__2027__draft__top-100__2026-07-15.md").write_text(
        _DRAFT_BOARD, encoding="utf-8")
    monkeypatch.setattr(ba, "PROCESSED_DIR", tmp_path / "processed")

    with storage.connect() as con:
        before = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    report = ba.ingest_drops(apply=True, inbox=inbox)
    assert report["results"][0]["status"] == "PARSED", report["results"][0]
    assert report["results"][0]["target_table"] == "draft_snapshots"

    with storage.connect() as con:
        after = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        drafted = con.execute("SELECT COUNT(*) FROM draft_snapshots").fetchone()[0]
    assert after == before == 0, "a draft board reached the active prospect pool"
    assert drafted == 3, "the draft rows did not reach draft_snapshots"


def test_the_ingest_branches_on_the_board_and_cannot_fall_through(tmp_path, monkeypatch):
    """The pro path and the draft path must not share a writer. If the branch
    ever falls through, a draft board silently takes to_snapshots()."""
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "ba__2027__draft__hs-top-150__2026-07-17.md").write_text(
        _DRAFT_BOARD, encoding="utf-8")
    monkeypatch.setattr(ba, "PROCESSED_DIR", tmp_path / "processed")

    called = []
    monkeypatch.setattr(ba, "insert_ba_snapshots",
                        lambda s: called.append(s) or 0)
    ba.ingest_drops(apply=True, inbox=inbox)
    assert called == [], "the pro snapshot writer ran on a draft board"


def test_a_pro_board_still_runs_through_the_same_entry_point(tmp_path, monkeypatch):
    """REGRESSION. Adding the draft branch to ingest_drops read board["is_draft"]
    with a hard subscript, which a PRO board does not carry, so the first real
    --apply crashed with KeyError on file one. Nothing was written, but the whole
    walk aborted. The draft tests could not catch it: they only ever fed the
    walker a draft board."""
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "ba__2026__midseason__top-100__2026-08-05.md").write_text(
        _GLOBAL_BOARD, encoding="utf-8")
    monkeypatch.setattr(ba, "PROCESSED_DIR", tmp_path / "processed")

    report = ba.ingest_drops(apply=True, inbox=inbox)
    assert report["results"][0]["status"] == "PARSED", report["results"][0]
    assert report["results"][0]["target_table"] == "snapshots"


def test_both_board_kinds_walk_together_without_either_aborting(tmp_path, monkeypatch):
    """The real inbox holds both kinds at once. One raising takes the other
    down, because the walk is a single loop."""
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "ba__2026__midseason__top-100__2026-08-05.md").write_text(
        _GLOBAL_BOARD, encoding="utf-8")
    (inbox / "ba__2027__draft__top-100__2026-07-15.md").write_text(
        _DRAFT_BOARD, encoding="utf-8")
    monkeypatch.setattr(ba, "PROCESSED_DIR", tmp_path / "processed")

    report = ba.ingest_drops(apply=True, inbox=inbox)
    assert [r["status"] for r in report["results"]] == ["PARSED", "PARSED"]
    assert {r["target_table"] for r in report["results"]} == {
        "snapshots", "draft_snapshots"}
    with storage.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM draft_snapshots").fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0


def test_the_draft_source_string_can_never_be_read_as_the_pro_feed():
    assert ba.DRAFT_SOURCE == "baseballamerica_draft"
    assert ba.DRAFT_SOURCE != ba.SOURCE


# --------------------------------------------------------------------------
# Rank-only. BA publishes no amateur grades and none may be invented.
# --------------------------------------------------------------------------

def test_a_draft_board_is_rank_only_and_never_fabricates_a_grade():
    """BA Grade/Risk, Adjusted Grade and Scouting Grades appear on 0 of 500 rows
    across the five real boards. Absent is recorded as absent."""
    board = _draft_board()
    assert board["meta"]["grades_found"] == {}
    assert board["meta"]["fv_basis"] == "none_published"
    for r in board["rows"]:
        assert r["fv"] is None and r["ba_risk"] is None and r["tools"] == {}


@pytest.mark.parametrize("season", [2025, 2026, 2027, 2028])
def test_the_era_rule_is_moot_on_a_draft_board_under_both_readings(season):
    """fv_basis picks "adjusted" from 2026 and "raw" before it. On an amateur
    board BOTH are None, because neither field is published, so there is no
    reading of the era rule under which a grade could be fabricated."""
    board = _draft_board({"class_year": season, "season": season})
    assert ba.fv_basis(season) in ("adjusted", "raw")
    assert all(r["fv"] is None for r in board["rows"])
    assert all(r["ba_raw_grade"] is None for r in board["rows"])


def test_the_draft_parser_never_consults_the_era_rule():
    """It records fv_basis as "none_published" but must never CALL fv_basis(),
    which would hand it "adjusted" or "raw" and invite a fallback."""
    import inspect
    src = inspect.getsource(ba.parse_draft_board)
    assert "fv_basis(" not in src
    assert '"fv_basis": "none_published"' in src


def test_a_draft_board_that_starts_publishing_grades_is_refused(tmp_path):
    """Reading an amateur grade as FV is a modelling decision with its own gate.
    It must not arrive as a silently populated column."""
    graded = _DRAFT_BOARD.replace(
        "Age At Draft: 18.8", "Age At Draft: 18.8\n\nBA Grade/Risk: 55/High")
    path = tmp_path / "ba__2027__draft__top-100__2026-07-15.md"
    path.write_text(graded, encoding="utf-8")
    board = ba.process_file(path, resolve=False)
    assert board["meta"]["grades_found"]
    assert any("own gate" in r for r in board["refusals"])


# --------------------------------------------------------------------------
# The scope-local rank. The draft-side twin of the org-list guard.
# --------------------------------------------------------------------------

def test_a_scoped_boards_rank_is_withheld_from_the_rank_column():
    """draft_export._consensus averages the latest rank per SOURCE, so a College
    Top 50's rank 1 and an HS Top 100's rank 1 would both be read as the first
    pick of the class. Neither is. The published rank survives at
    _extras.ba_scope_rank, so nothing BA published is discarded."""
    board = _draft_board({"scope": "HS Top 150", "scope_extent": 150,
                          "pool": "HS", "rank_is_global": False})
    ba.resolve_draft_identities(board["rows"], 2027)
    rows = ba.to_draft_rows(board)
    assert [r["rank"] for r in rows] == [None, None, None]
    assert [r["tools"]["_extras"]["ba_scope_rank"] for r in rows] == [1, 2, 3]
    assert all(r["tools"]["_extras"]["ba_rank_is_global"] is False for r in rows)


def test_a_mixed_boards_rank_is_kept_because_it_orders_the_whole_class():
    board = _draft_board()
    ba.resolve_draft_identities(board["rows"], 2027)
    rows = ba.to_draft_rows(board)
    assert [r["rank"] for r in rows] == [1, 2, 3]


@pytest.mark.parametrize("slug,expect_global", [
    ("top-100", True), ("top-250", True),
    ("college-top-100", False), ("college-top-50", False),
    ("hs-top-150", False), ("hs-top-100", False),
])
def test_every_registered_scope_declares_whether_its_rank_is_global(slug, expect_global):
    _label, _extent, pool = ba.DRAFT_SCOPES[slug]
    assert ba.scope_rank_is_global(pool) is expect_global


def test_the_two_pool_restricted_scopes_would_both_claim_rank_one():
    """The concrete failure, stated as a test: a College Top 50 and an HS Top
    100 each open at rank 1 and the two players are different humans."""
    col = _draft_board({"scope": "College Top 50", "scope_extent": 50,
                        "pool": "COL", "rank_is_global": False})
    hs = _draft_board({"scope": "HS Top 100", "scope_extent": 100,
                       "pool": "HS", "rank_is_global": False})
    for b in (col, hs):
        ba.resolve_draft_identities(b["rows"], 2028)
    assert col["rows"][0]["rank"] == hs["rows"][0]["rank"] == 1
    assert all(r["rank"] is None for r in ba.to_draft_rows(col))
    assert all(r["rank"] is None for r in ba.to_draft_rows(hs))


# --------------------------------------------------------------------------
# The label. Derived from the SCOPE, never from the row count.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name,label", [
    ("ba__2027__draft__top-100__2026-07-15.md",
     "Baseball America 2027 Draft Top 100"),
    ("ba__2027__draft__college-top-100__2026-05-20.md",
     "Baseball America 2027 Draft College Top 100"),
    ("ba__2027__draft__hs-top-150__2026-07-17.md",
     "Baseball America 2027 Draft HS Top 150"),
    ("ba__2028__draft__college-top-50__2026-05-20.md",
     "Baseball America 2028 Draft College Top 50"),
    ("ba__2028__draft__hs-top-100__2026-07-31.md",
     "Baseball America 2028 Draft HS Top 100"),
])
def test_the_five_real_boards_build_distinct_labels(name, label):
    """The scope is IN the label, so the boards cannot collide on the
    (source, interval_label, player_key) upsert key."""
    meta = ba.parse_filename(name)
    assert meta is not None and meta["is_draft"]
    board = ba.parse_draft_board(
        _DRAFT_BOARD, {**meta, "snapshot_date": meta["pubdate"]})
    assert board["meta"]["interval_label"] == label


def test_the_five_real_boards_do_not_collide_on_the_upsert_key():
    labels = set()
    for name in ("ba__2027__draft__top-100__2026-07-15.md",
                 "ba__2027__draft__college-top-100__2026-05-20.md",
                 "ba__2027__draft__hs-top-150__2026-07-17.md",
                 "ba__2028__draft__college-top-50__2026-05-20.md",
                 "ba__2028__draft__hs-top-100__2026-07-31.md"):
        meta = ba.parse_filename(name)
        board = ba.parse_draft_board(
            _DRAFT_BOARD, {**meta, "snapshot_date": meta["pubdate"]})
        labels.add(board["meta"]["interval_label"])
    assert len(labels) == 5


def test_a_top_150_that_parsed_fewer_rows_does_not_relabel_itself():
    """The org-board label collision, on the draft side. Size comes from the
    scope registry, not from len(rows)."""
    meta = ba.parse_filename("ba__2027__draft__hs-top-150__2026-07-17.md")
    board = ba.parse_draft_board(
        _DRAFT_BOARD, {**meta, "snapshot_date": "2026-07-17"})
    assert len(board["rows"]) == 3
    assert board["meta"]["board_size"] == 150
    assert board["meta"]["interval_label"].endswith("HS Top 150")


def test_the_label_shape_matches_the_other_draft_sources():
    """Stored convention: "ESPN 2026 Draft Top 150",
    "MLB Pipeline 2026 Draft Top 250"."""
    label = _draft_board()["meta"]["interval_label"]
    assert re.match(r"^Baseball America \d{4} Draft .+$", label)


# --------------------------------------------------------------------------
# The key. A format mismatch orphans every row on promotion.
# --------------------------------------------------------------------------

def test_the_draft_key_is_built_by_the_shared_builder_not_formatted_locally():
    """draft_promotion.draft_canonical_keys reads this exact shape. A local
    f-string would drift the first time the builder changes."""
    import inspect
    src = inspect.getsource(ba.resolve_draft_identities)
    assert "draft_player_key" in src

    out = ba.resolve_draft_identities(
        [{"rank": 1, "player_name": "Garrett Wright"}], 2026)
    assert out["resolved"][0]["player_key"] == "draft_2026_garrett_wright"


def test_two_classes_do_not_share_a_key():
    a = ba.resolve_draft_identities([{"rank": 1, "player_name": "Nico Partida"}], 2027)
    b = ba.resolve_draft_identities([{"rank": 1, "player_name": "Nico Partida"}], 2028)
    assert a["resolved"][0]["player_key"] != b["resolved"][0]["player_key"]


def test_a_within_board_key_collision_is_reported_not_silently_upserted():
    """Two humans on one key would upsert onto each other under the conflict
    target and the second would overwrite the first with nothing to show."""
    out = ba.resolve_draft_identities(
        [{"rank": 1, "player_name": "Jon Smith"},
         {"rank": 2, "player_name": "Jon Smith"}], 2027)
    assert len(out["key_collisions"]) == 1
    assert out["key_collisions"][0]["ranks"] == [1, 2]


def test_a_draft_row_never_resolves_against_the_pro_players_table():
    """Amateurs live in their own key namespace precisely so a high schooler
    never collides with a pro of the same name until draft_promotion links them
    deliberately."""
    import inspect
    src = inspect.getsource(ba.resolve_draft_identities)
    assert "screen_identity" not in src and "FROM players" not in src


# --------------------------------------------------------------------------
# The commit field: three spellings, two quantities.
# --------------------------------------------------------------------------

def test_a_draft_history_value_never_reaches_college_commit():
    """"Never Drafted" and "Reds 25 (19)" are prior-draft history, not a college
    commitment, and college_commit is a column every consumer reads as a school
    name."""
    rows = _draft_board()["rows"]
    kelly = rows[1]
    assert kelly["commit_raw"] == "Never Drafted"
    assert kelly["commit_kind"] == "draft_history"
    assert kelly["college_commit"] is None


@pytest.mark.parametrize("value,kind", [
    ("Never Drafted", "draft_history"),
    ("Never Drafred", "draft_history"),            # BA typo, real, 1 row
    ("Never Draftes", "draft_history"),            # BA typo, real, 1 row
    ("Reds ’25 (19)", "draft_history"),
    ("Natioanls ’25 (19)", "draft_history"),  # BA typo, real, 1 row
    ("D-backs ’24 (18)", "draft_history"),
    ("Tennessee", "commit"),
    ("Texas A\\&M", "commit"),
    ("Uncommitted", "uncommitted"),
    ("", None),
])
def test_the_commit_value_decides_the_quantity_not_the_label(value, kind):
    """The mixed board writes "Committed/Drafted" over BOTH quantities, 54 rows
    of draft history and 46 commitments, so the label cannot decide."""
    got, _cleaned = ba._classify_commit("Committed/Drafted", value)
    assert got == kind


def test_the_markdown_ampersand_escape_is_undone():
    """Texas A\\&M and Texas A&M must not be two different schools."""
    _kind, cleaned = ba._classify_commit("Committed", "Texas A\\&M")
    assert cleaned == "Texas A&M"


def test_uncommitted_maps_to_null_and_survives_in_extras():
    """No 'Uncommitted' sentinel exists in any stored draft row, but the
    published fact is not discarded."""
    board = _draft_board({"pool": "HS", "rank_is_global": False,
                          "scope": "HS Top 150", "scope_extent": 150})
    board["rows"][0]["commit_kind"] = "uncommitted"
    board["rows"][0]["commit_raw"] = "Uncommitted"
    board["rows"][0]["college_commit"] = None
    ba.resolve_draft_identities(board["rows"], 2027)
    row = ba.to_draft_rows(board)[0]
    assert row["college_commit"] is None
    assert row["tools"]["_extras"]["ba_commit_raw"] == "Uncommitted"


def test_an_empty_commit_field_does_not_swallow_the_following_line():
    """REGRESSION, and it was doing real damage. The space class matched a
    NEWLINE, so a field BA published EMPTY walked past the end of its line.
    Measured before the fix: the 2027 Top 100 rank 92 (Kyle Alivo) captured a
    whole scouting paragraph as his commit value and an Iowa college pitcher
    was typed HSp, and the HS Top 150 rank 126 (Kam Smith) got the literal
    string "Age At Draft: 18.7" written into college_commit."""
    alivo = _draft_board()["rows"][2]
    assert alivo["player_name"] == "Kyle Alivo"
    assert alivo["commit_raw"] is None and alivo["college_commit"] is None
    assert alivo["school"] == "Iowa"
    assert alivo["pool"] == "COL", "a college pitcher was typed as a high schooler"


def test_an_empty_school_field_does_not_swallow_the_following_line():
    board = ba.parse_draft_board(
        _DRAFT_BOARD.replace("School: Iowa", "School:"), _DRAFT_META)
    assert board["rows"][2]["school"] is None


def test_a_school_line_inside_prose_cannot_register_as_the_field():
    board = ba.parse_draft_board(
        _DRAFT_BOARD.replace("Alivo had surgery.",
                             "Alivo had surgery. School: Not This One."),
        _DRAFT_META)
    assert board["rows"][2]["school"] == "Iowa"


# --------------------------------------------------------------------------
# player_type. The BOARD-level fact wins, and overrides are counted.
# --------------------------------------------------------------------------

def test_player_type_uses_the_shared_canonicaliser():
    import inspect
    src = inspect.getsource(ba.parse_draft_board)
    assert "_canon_player_type" in src
    assert set(r["player_type"] for r in _draft_board()["rows"]) <= {
        "COLh", "COLp", "HSh", "HSp"}


def test_the_board_level_pool_beats_an_untagged_high_school():
    """BA does not tag every high school with an "HS" token, and the school
    string is exactly what _canon_player_type falls back on when handed no
    player_type. Across the two real HS boards that fallback mistypes 40 rows as
    college; on the mixed board it mistypes 9 more."""
    board = _draft_board({"pool": "HS", "rank_is_global": False,
                          "scope": "HS Top 150", "scope_extent": 150})
    kelly = board["rows"][1]
    assert kelly["school"] == "West Virginia"       # no HS token at all
    assert kelly["pool"] == "HS" and kelly["pool_basis"] == "board"
    assert kelly["player_type"] == "HSh"


def test_the_board_pool_is_passed_in_and_not_left_to_the_school_fallback():
    """_canon_player_type resolves its pool from the player_type argument BEFORE
    it falls back on the school string. Handing it the board pool is the whole
    mechanism, so a refactor that stops passing it must fail here."""
    from draft_export import _canon_player_type
    assert _canon_player_type("HS", "West Virginia", "C / 2B") == "HSh"
    assert _canon_player_type(None, "West Virginia", "C / 2B") == "COLh"


def test_a_board_level_override_is_counted_and_never_silent():
    """A silent override of a board-level truth is how a mislabeled cohort gets
    built."""
    board = _draft_board({"pool": "HS", "rank_is_global": False,
                          "scope": "HS Top 150", "scope_extent": 150})
    assert board["pool_disagreements"], "an override went unreported"
    kinds = {d["kind"] for d in board["pool_disagreements"]}
    assert "row_inference" in kinds or "school_token" in kinds
    assert all(d["board_pool"] == "HS" for d in board["pool_disagreements"])


def test_the_mixed_board_infers_per_row_from_the_commit_value():
    """On the real mixed board this is defined on 100 of 100 rows and agrees
    with Age At Draft on 100 of 100 where age exists (HS tops out at 19.2,
    college starts at 20.8), while the school string disagrees on 9."""
    rows = _draft_board()["rows"]
    assert rows[0]["pool"] == "HS" and rows[0]["pool_basis"] == "commit_value"
    assert rows[1]["pool"] == "COL" and rows[1]["pool_basis"] == "commit_value"


@pytest.mark.parametrize("age,expect", [(17.9, "HS"), (19.2, "HS"),
                                        (20.8, "COL"), (21.6, "COL")])
def test_age_at_draft_corroborates_the_pool_where_the_commit_field_is_empty(age, expect):
    pool, basis = ba.classify_pool(None, None, age)
    assert pool == expect and basis == "age"


def test_the_school_token_is_only_ever_the_last_resort_and_is_named():
    pool, basis = ba.classify_pool(None, None, None, "COL")
    assert pool == "COL" and basis == "school_fallback"


# --------------------------------------------------------------------------
# Optional fields. A parser that requires one drops rows silently.
# --------------------------------------------------------------------------

def test_every_optional_draft_field_is_optional():
    """Measured presence over the five real boards: Age At Draft 632 of 650,
    Headshot of sporadic, and the commit field absent under any given spelling
    on four of five boards. Requiring any of them rejects a valid board."""
    stripped = "\n".join(
        line for line in _DRAFT_BOARD.splitlines()
        if not line.startswith(("Age At Draft:", "Committed", "Drafted:")))
    board = ba.parse_draft_board(stripped, _DRAFT_META)
    assert len(board["rows"]) == 3
    assert all(r["age_at_draft"] is None for r in board["rows"])


def test_the_parsed_row_count_must_equal_the_declared_count():
    """The guard the org path already has. A parser that quietly requires an
    optional field produces a SHORT board, and this is what turns that into a
    refusal instead of a silent partial ingest."""
    with pytest.raises(ba.BoardFormatError, match="Refusing a partial board"):
        ba.parse_draft_board(_DRAFT_BOARD.replace("3 players", "9 players"),
                             _DRAFT_META)


def test_a_repeated_field_block_yields_one_row_and_the_first_value():
    """Real paste artifact: rank 94 of the 2027 Top 100 (Noah Franco) carries
    its School / Committed / Age lines TWICE, which is why that board greps to
    101 School lines over 100 rows. The .md is left exactly as pasted."""
    doubled = _DRAFT_BOARD.replace(
        "School: West Virginia\nCommitted/Drafted: Never Drafted\nAge At Draft: 21.6",
        "School: West Virginia\nCommitted/Drafted: Never Drafted\nAge At Draft: 21.6\n\n"
        "School: West Virginia\nCommitted/Drafted: Never Drafted\nAge At Draft: 21.6")
    board = ba.parse_draft_board(doubled, _DRAFT_META)
    assert len(board["rows"]) == 3
    assert board["rows"][1]["school"] == "West Virginia"
    assert board["rows"][1]["age_at_draft"] == 21.6


def test_a_headshot_line_belongs_to_the_next_player_not_the_previous_one():
    board = ba.parse_draft_board(
        _DRAFT_BOARD.replace("2\\. Gavin Kelly",
                             "Headshot of Gavin Kelly\n2\\. Gavin Kelly"),
        _DRAFT_META)
    assert len(board["rows"]) == 3
    assert board["rows"][1]["player_name"] == "Gavin Kelly"


# --------------------------------------------------------------------------
# Filename semantics. Different from an org board in both fields.
# --------------------------------------------------------------------------

def test_the_first_field_is_the_draft_class_year_not_a_list_season():
    meta = ba.parse_filename("ba__2028__draft__college-top-50__2026-05-20.md")
    assert meta["class_year"] == 2028
    assert meta["pubdate"] == "2026-05-20"
    assert meta["pool"] == "COL" and meta["scope_extent"] == 50


def test_a_draft_board_without_a_publication_date_is_refused(tmp_path):
    """There is no defensible convention date for a draft board: a class is
    ranked continuously, so any fixed date would be wrong by months, and
    snapshot_date is what the whole as-of chain keys on. That is the MLB
    Pipeline {y}-01-22 failure that froze 829 prospects on January grades."""
    path = tmp_path / "ba__2027__draft__top-100.md"
    path.write_text(_DRAFT_BOARD, encoding="utf-8")
    board = ba.process_file(path, resolve=False)
    assert any("publication date" in r for r in board["refusals"])


def test_the_trailing_date_becomes_the_snapshot_date(tmp_path):
    path = tmp_path / "ba__2027__draft__top-100__2026-07-15.md"
    path.write_text(_DRAFT_BOARD, encoding="utf-8")
    board = ba.process_file(path, resolve=False)
    assert board["meta"]["snapshot_date"] == "2026-07-15"


def test_an_unregistered_scope_is_refused_rather_than_guessed():
    assert ba.parse_filename("ba__2027__draft__top-77__2026-07-15.md") is None


def test_a_draft_filename_never_resolves_to_a_club():
    """"top-100" sits in the slug position on both an org-board filename and a
    draft one. The board field is what separates them."""
    draft = ba.parse_filename("ba__2027__draft__top-100__2026-07-15.md")
    pro = ba.parse_filename("ba__2026__midseason__top-100__2026-08-05.md")
    assert draft["is_draft"] and not pro.get("is_draft")
    assert pro["is_global"] and not draft["is_global"]


# --------------------------------------------------------------------------
# The pro GLOBAL board. The club line shadows the position line.
# --------------------------------------------------------------------------

_GLOBAL_BOARD = """2 players
Expand all
Headshot of Jesus Made
1\\. Jesus Made
Milwaukee Brewers
SS

Ht: 6'1" | Wt: 187 | B-T: S-R

Age: 18

BA Grade/Risk: 70/Average

Adjusted Grade: 60

Scouting Grades: Hit: 70 | Power: 60 | Run: 60 | Field: 50 | Arm: 70
2\\. Kade Anderson
Seattle Mariners
LHP

Ht: 6'2" | Wt: 175 | B-T: L-L

Age: 21

BA Grade/Risk: 60/Mild

Adjusted Grade: 55

Scouting Grades: Fastball: 60 | Slider: 55 | Control: 50
"""

_GLOBAL_META = {"season": 2026, "board": "midseason", "team_slug": "top-100",
                "org": None, "team_name": None, "scope": "Top 100",
                "is_global": True, "pubdate": "2026-08-05",
                "snapshot_date": "2026-08-05"}


def test_the_club_line_does_not_shadow_the_position_on_a_global_board():
    """REGRESSION. The old rule read the FIRST non-blank line of a block and
    broke unconditionally, so "Milwaukee Brewers" failed the position regex and
    position stayed None on 75 of 100 rows of the real 2026 midseason Top 100.
    Only the 25 pitchers survived, and only because the tool-based role
    inference rebuilt RHP/LHP from their pitch grades."""
    rows = ba.parse_board(_GLOBAL_BOARD, _GLOBAL_META)["rows"]
    assert rows[0]["position"] == "SS", "the hitter lost his position"
    assert rows[1]["position"] == "LHP"


def test_a_null_position_would_disarm_the_side_of_ball_identity_check():
    """Why the position loss was not cosmetic. side_of_ball(None) is None, so
    screen_identity's pitcher-versus-hitter check silently no-ops, and that is
    the check that caught the Garrett Wright merge."""
    assert ba.side_of_ball(None) is None
    assert ba.side_of_ball("SS") == "H" and ba.side_of_ball("LHP") == "P"


def test_a_global_board_carries_its_org_per_row():
    """A global list has no org of its own, so the club line is the only org
    there is and an org-less pro row is worse than useless on the board."""
    board = ba.parse_board(_GLOBAL_BOARD, _GLOBAL_META)
    assert [r["row_org"] for r in board["rows"]] == ["MIL", "SEA"]
    for r in board["rows"]:
        r["player_key"] = "k%d" % r["rank"]
    assert [s.org for s in ba.to_snapshots(board)] == ["MIL", "SEA"]


@pytest.mark.parametrize("club,org", [
    ("Milwaukee Brewers", "MIL"), ("Boston Red Sox", "BOS"),
    ("Chicago White Sox", "CHW"), ("Athletics", "ATH"),
    ("Arizona Diamondbacks", "ARI"), ("Toronto Blue Jays", "TOR"),
    ("Not A Club", None), (None, None),
])
def test_the_club_line_maps_through_the_shared_club_table(club, org):
    assert ba._club_to_org(club) == org


def test_an_unmappable_club_on_a_global_board_is_refused(tmp_path):
    """A new club spelling would otherwise ingest every row using it with org
    NULL, silently."""
    path = tmp_path / "ba__2026__midseason__top-100__2026-08-05.md"
    path.write_text(_GLOBAL_BOARD.replace("Milwaukee Brewers", "Milwaukee Brewer"),
                    encoding="utf-8")
    board = ba.process_file(path, resolve=False)
    assert any("cannot map" in r for r in board["refusals"])


def test_an_org_board_is_unaffected_by_the_club_line_rule():
    """The org path opens a block with the position and must stay byte-identical.
    Verified separately against all 30 archived 2026 midseason boards, 900 rows,
    zero diffs."""
    rows = ba.parse_board(_BOARD, _META)["rows"]
    assert [r["position"] for r in rows] == ["RHP", "SS", "SS"]
    assert all(r["row_org"] is None for r in rows)


def test_the_position_scan_stops_before_the_physical_line():
    """Bounding the scan is what keeps a short all-caps token inside prose from
    registering as a position."""
    board = ba.parse_board(
        _GLOBAL_BOARD.replace("Age: 18", "Age: 18\n\nOF"), _GLOBAL_META)
    assert board["rows"][0]["position"] == "SS"
