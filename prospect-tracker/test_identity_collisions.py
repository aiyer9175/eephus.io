# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Merged-identity guards (the "Jesus Flores" class).

Two real, distinct humans:

    mlbam 837965  Jesus Flores  b. 2008-11-06  C  DSL Rangers Blue, age 17.7
    mlbam 808222  Jesus Flores  b. 2005-03-16  P  Wisconsin (MIL) A+, age 21.4

The board carried ONE record for them: player_key "jesus_flores",
mlbam_id null, position DH, displayed org MIL, snapshot org TEX, level A+,
birth_date 2005-03-16 (the PITCHER's), scored on the hitter side while its
entire fielding log is 80 games at P.

The existing guards could not see it. scrapers.split_key_for_mlbam returns
None on a null mlbam_id in its first line; mlbam_ingest._collision_safe_key
only forks when the slug is already durably bound to a different id;
consensus._prune_collision_cluster needs two dated snapshots and this
record has one. The tests in test_mlbam_key_collision.py cover those three
seams and all still pass - they were never wrong, they were blind.

This module is the OUTPUT-side guard: it checks the built artifacts for the
shape a merge leaves behind, so the class is caught even when every ingest
guard stays silent.

Layout:
  1. Synthetic reconstruction of the exact trigger case. These are the
     "would have caught it" tests: they run the detectors over a hand-built
     fixture of the two humans and assert each detector fires.
  2. Negative controls, so the detectors are not just always-on alarms.
  3. Ratchet tests over the REAL build artifacts against an enumerated
     baseline of the defects known on 2026-07-24. New merges fail; repairs
     are free (the assertion is a subset check, not equality).

NOTHING here writes to prospects.db or to any build artifact. The report is
written to a tmp_path in tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import identity_audit as ia


# ---------------------------------------------------------------------------
# 1. The trigger case, reconstructed
# ---------------------------------------------------------------------------

# Two roster rows straight from data/rosters_by_org.json as it stood on
# 2026-07-24: the pitcher's row carries our player_key, the catcher's row
# carries player_key null (untracked, and uningestible while the slug is
# taken).
FLORES_ROSTER = [
    {"mlbam_id": 808222, "fullName": "Jesus Flores", "position": "P",
     "age": 21.4, "team_name": "Wisconsin Timber Rattlers",
     "player_key": "jesus_flores", "org": "MIL", "level": "A+"},
    {"mlbam_id": 837965, "fullName": "Jesus Flores", "position": "C",
     "age": 17.7, "team_name": "DSL Rangers Blue",
     "player_key": None, "org": "TEX", "level": "DSL"},
]

# The single merged board record.
FLORES_BOARD = [{
    "player_key": "jesus_flores", "mlbam_id": None, "position": "DH",
    "org": "MIL", "current_level": "A+", "birth_date": "2005-03-16",
    "age": 21.4, "overall_rank": 1519, "scope": "active",
}]

# data/positions_played.json: a pure pitcher's fielding log.
FLORES_FIELDING = {"jesus_flores": {"by_pos": {"P": {"g": 80, "gs": 16}},
                                    "versa": ["P"]}}

# player_photos: BOTH ids point at the one key.
FLORES_PHOTOS = {808222: "jesus_flores", 837965: "jesus_flores"}

# The minting snapshot came from the catcher's DSL Rangers hitting split.
FLORES_SNAPSHOT_ORGS = {"jesus_flores": "TEX"}


def _flores_report():
    return ia.audit(board_rows=FLORES_BOARD, roster_rows=FLORES_ROSTER,
                    photo_bindings=FLORES_PHOTOS,
                    positions_played=FLORES_FIELDING,
                    snapshot_orgs=FLORES_SNAPSHOT_ORGS)


def test_c1_flags_two_humans_sharing_one_unidentified_key():
    """Requirement 1a: one name, two distinct mlbam ids, one player_key."""
    hits = ia.find_unsplit_collisions(
        FLORES_ROSTER, {p["player_key"]: p for p in FLORES_BOARD})
    assert len(hits) == 1
    hit = hits[0]
    assert hit["slug"] == "jesus_flores"
    assert hit["status"] == "unattributed"
    assert hit["n_humans"] == 2
    assert hit["board_mlbam_id"] is None
    assert [m["mlbam_id"] for m in hit["members"]] == [808222, 837965]


def test_c2_flags_key_bound_to_two_mlbam_ids():
    hits = ia.find_double_bound_keys(FLORES_PHOTOS)
    assert hits == [{"check": "C2", "player_key": "jesus_flores",
                     "mlbam_ids": [808222, 837965]}]


def test_c3_flags_placed_player_with_no_id():
    hits = ia.find_unresolved_active(FLORES_BOARD)
    assert [h["player_key"] for h in hits] == ["jesus_flores"]
    assert hits[0]["current_level"] == "A+"


def test_c4_flags_hitter_card_with_a_pitchers_fielding_log():
    """Requirement 2: position inconsistent with the side of the ball."""
    hits = ia.find_side_conflicts(FLORES_BOARD, FLORES_FIELDING)
    assert len(hits) == 1
    assert hits[0]["board_position"] == "DH"
    assert hits[0]["claimed_side"] == "H"
    assert hits[0]["fielded_side"] == "P"
    assert hits[0]["fielded_games"] == 80


def test_c6_flags_snapshot_org_vs_displayed_org():
    """Requirement 2: the snapshot that minted the row says TEX, the roster
    join that fills it says MIL. Two humans, two clubs, one card."""
    hits = ia.find_org_splits(FLORES_BOARD, FLORES_SNAPSHOT_ORGS)
    assert len(hits) == 1
    assert hits[0]["snapshot_org"] == "TEX"
    assert hits[0]["displayed_org"] == "MIL"


# The three served debuted rows census M02-11 found on 2026-09-24, as they
# stood in data/debuts.json: each key's position came from another human's
# board rows, each stat line from the bound id.
M02_11_DEBUTED = [
    {"player_key": "jose_rodriguez", "position": "SS", "mlbam_id": 692064,
     "scope": "graduated", "statline": {"is_pitcher": True}},
    {"player_key": "michael_massey", "position": "RHP", "mlbam_id": 686681,
     "scope": "graduated", "statline": {"is_pitcher": False}},
    {"player_key": "carlos_rodriguez", "position": "OF", "mlbam_id": 692230,
     "scope": "graduated", "statline": {"is_pitcher": True},
     "sabermetrics": {"is_pitcher": True}},
]


def test_c4b_flags_debuted_rows_whose_position_and_stat_lines_disagree():
    hits = ia.find_debuted_side_conflicts(M02_11_DEBUTED)
    assert [h["player_key"] for h in hits] == [
        "carlos_rodriguez", "jose_rodriguez", "michael_massey"]
    by_key = {h["player_key"]: h for h in hits}
    assert by_key["jose_rodriguez"]["claimed_side"] == "H"
    assert by_key["jose_rodriguez"]["stat_side"] == "P"
    assert by_key["michael_massey"]["claimed_side"] == "P"
    assert by_key["carlos_rodriguez"]["stat_fields"] == ["sabermetrics", "statline"]
    report = ia.audit(board_rows=M02_11_DEBUTED, roster_rows=[])
    assert report["summary"]["c4b_debuted_side_conflicts"] == 3
    assert set(report["critical_player_keys"]) == {
        "carlos_rodriguez", "jose_rodriguez", "michael_massey"}
    # Graduates are not on the active board, so none is critical-active.
    assert report["critical_active_player_keys"] == []


def test_c4b_is_quiet_once_the_rows_are_split():
    split = [dict(M02_11_DEBUTED[0], position="RHP"),
             dict(M02_11_DEBUTED[1], position="2B"),
             dict(M02_11_DEBUTED[2], position="RHP")]
    assert ia.find_debuted_side_conflicts(split) == []


def test_c4b_two_way_players_are_never_flagged():
    rows = [
        {"player_key": "shohei_ohtani", "position": "RHP", "scope": "graduated",
         "statline": {"is_pitcher": False}},
        {"player_key": "some_two_way_rookie", "position": "TWP",
         "scope": "graduated", "statline": {"is_pitcher": False}},
    ]
    assert ia.find_debuted_side_conflicts(rows) == []
    assert "shohei_ohtani" in ia.KNOWN_TWO_WAY_DEBUTED


def test_c4b_needs_every_stat_line_to_disagree_and_reads_debuted_rows_only():
    mixed = [{"player_key": "converted", "position": "SS", "scope": "graduated",
              "statline": {"is_pitcher": True},
              "sabermetrics": {"is_pitcher": False}}]
    assert ia.find_debuted_side_conflicts(mixed) == []
    no_line = [{"player_key": "no_line", "position": "SS", "scope": "graduated"}]
    assert ia.find_debuted_side_conflicts(no_line) == []
    # An active row is C4's job (the fielding census), not C4b's.
    active = [dict(M02_11_DEBUTED[0], scope="active")]
    assert ia.find_debuted_side_conflicts(active) == []


def test_c6_ignores_the_pipeline_placeholder_org():
    """MLB Pipeline prints "Office of the Commissioner" for a player between
    clubs. On 2026-09-24 it flagged myles_bailey (CHC 1B, a 2026 draftee)
    as an org split; the placeholder is no club and must never witness one."""
    board = [{"player_key": "myles_bailey", "mlbam_id": None, "org": "CHC",
              "current_level": "A", "scope": "active"}]
    assert ia.find_org_splits(
        board, {"myles_bailey": "Office of the Commissioner"}) == []
    # A real club on the snapshot still fires.
    assert len(ia.find_org_splits(board, {"myles_bailey": "MIL"})) == 1


def test_frankenstein_composite_fires_on_the_trigger_case():
    report = _flores_report()
    assert report["frankenstein_records"] == ["jesus_flores"]
    assert report["critical_active_player_keys"] == ["jesus_flores"]
    s = report["summary"]
    assert (s["c1_unattributed"], s["c2_double_bound"],
            s["c3_unresolved_active"], s["c4_side_conflicts"],
            s["c6_org_splits"]) == (1, 1, 1, 1, 1)


def test_birthdate_conflict_fires_when_the_wrong_id_is_bound():
    """Requirement 1b: a built record's birth_date must be consistent with
    the mlbam id attached to it.

    This is the check that catches the NAIVE repair. If someone binds the
    catcher's id 837965 to the incumbent key without also correcting the
    biography, the record claims a 2005 birth_date while StatsAPI reports
    that id as 17.7 years old. C5 returns 0 on the real tree today, so it
    is a live invariant rather than a baselined defect."""
    naive = [dict(FLORES_BOARD[0], mlbam_id=837965)]
    hits = ia.find_birthdate_conflicts(
        naive, FLORES_ROSTER, as_of=__import__("datetime").date(2026, 7, 24))
    assert len(hits) == 1
    assert hits[0]["mlbam_id"] == 837965
    assert hits[0]["roster_age"] == 17.7
    assert hits[0]["age_from_birth_date"] == pytest.approx(21.36, abs=0.05)
    assert abs(hits[0]["delta_years"]) > ia.AGE_TOLERANCE_YEARS


def test_correct_split_clears_every_detector():
    """The repair the audit prescribes: the incumbent (the pitcher, who owns
    all the history under this key) KEEPS "jesus_flores"; the newcomer gets
    a brand new discriminated key. Running the detectors over that end state
    must produce nothing, so a real fix turns these tests green."""
    roster = [
        dict(FLORES_ROSTER[0], player_key="jesus_flores"),
        dict(FLORES_ROSTER[1], player_key="jesus_flores_837965"),
    ]
    board = [
        {"player_key": "jesus_flores", "mlbam_id": 808222, "position": "P",
         "org": "MIL", "current_level": "A+", "birth_date": "2005-03-16",
         "overall_rank": 1519, "scope": "active"},
        {"player_key": "jesus_flores_837965", "mlbam_id": 837965,
         "position": "C", "org": "TEX", "current_level": "DSL",
         "birth_date": "2008-11-06", "overall_rank": None, "scope": "active"},
    ]
    report = ia.audit(
        board_rows=board, roster_rows=roster,
        photo_bindings={808222: "jesus_flores", 837965: "jesus_flores_837965"},
        positions_played=FLORES_FIELDING,
        snapshot_orgs={"jesus_flores": "MIL", "jesus_flores_837965": "TEX"},
        as_of=__import__("datetime").date(2026, 7, 24))
    assert report["critical_player_keys"] == []
    assert report["frankenstein_records"] == []
    # The slug is still a collision, but a correctly SPLIT one.
    assert report["summary"]["c1_split"] == 1
    assert report["summary"]["c1_unattributed"] == 0
    # The incumbent key was preserved: no history was re-keyed.
    assert "jesus_flores" in {p["player_key"] for p in board}


# ---------------------------------------------------------------------------
# 2. Negative controls
# ---------------------------------------------------------------------------

def test_unassigned_signee_is_not_a_c3_defect():
    """250 of the 256 id-less active rows are 2026 draftees / IFA signings
    with no level yet. Those are not merges and must stay quiet."""
    rows = [{"player_key": "brand_new_signee", "mlbam_id": None,
             "position": "SS", "org": "SFG", "current_level": None,
             "scope": "active"}]
    assert ia.find_unresolved_active(rows) == []


def test_graduated_and_inactive_rows_are_not_c3_defects():
    """The graduated / inactive slices are 30 to 70 percent id-less by
    construction (pre-2015 cohorts predate the id map)."""
    rows = [{"player_key": "old_timer", "mlbam_id": None, "position": "1B",
             "org": "NYY", "current_level": "AAA", "scope": "inactive"}]
    assert ia.find_unresolved_active(rows) == []


def test_position_change_does_not_trip_the_side_check():
    """A catcher who has also played first base is not a side conflict."""
    board = [{"player_key": "moved_off_c", "mlbam_id": 1, "position": "1B",
              "scope": "active"}]
    played = {"moved_off_c": {"by_pos": {"C": {"g": 200}, "1B": {"g": 40}}}}
    assert ia.find_side_conflicts(board, played) == []


def test_two_way_player_does_not_trip_the_side_check():
    board = [{"player_key": "two_way", "mlbam_id": 2, "position": "DH",
              "scope": "active"}]
    played = {"two_way": {"by_pos": {"P": {"g": 20}, "DH": {"g": 60}}}}
    assert ia.find_side_conflicts(board, played) == []


def test_tiny_fielding_sample_does_not_trip_the_side_check():
    """A position player mopping up in a blowout is not an identity defect."""
    board = [{"player_key": "mop_up", "mlbam_id": 3, "position": "3B",
              "scope": "active"}]
    played = {"mop_up": {"by_pos": {"P": {"g": 2}}}}
    assert ia.find_side_conflicts(board, played) == []


def test_org_split_check_ignores_identified_players():
    """Over the real tree, 1572 of 4467 active rows disagree on org because
    of ordinary trades and promotions. Requiring a null id is what makes C6
    a 2-row signal instead of a 1572-row alarm."""
    board = [{"player_key": "traded_guy", "mlbam_id": 12345, "org": "SDP",
              "current_level": "AA", "scope": "active"}]
    assert ia.find_org_splits(board, {"traded_guy": "MIA"}) == []


def test_roster_age_stamping_noise_does_not_trip_the_birthdate_check():
    """Roster ages imply an as-of date spread of about +/-0.09y around the
    build date. The 1.0y tolerance sits far outside that."""
    import datetime
    board = [{"player_key": "normal_guy", "mlbam_id": 99, "scope": "active",
              "birth_date": "2005-03-16"}]
    roster = [{"mlbam_id": 99, "fullName": "Normal Guy", "age": 21.3}]
    assert ia.find_birthdate_conflicts(
        board, roster, as_of=datetime.date(2026, 7, 24)) == []


def test_single_human_slug_is_never_a_collision():
    roster = [{"mlbam_id": 700000, "fullName": "Konnor Griffin",
               "player_key": "konnor_griffin"}]
    assert ia.find_unsplit_collisions(roster, {}) == []


def test_already_split_slug_reports_clean():
    """The established pattern (joshua_flores__sa3069242, and the 53
    automatic forks minted by mlbam_ingest) must not be flagged."""
    roster = [
        {"mlbam_id": 111, "fullName": "Joshua Flores",
         "player_key": "joshua_flores"},
        {"mlbam_id": 222, "fullName": "Joshua Flores",
         "player_key": "joshua_flores__sa3069242"},
    ]
    board = {"joshua_flores": {"player_key": "joshua_flores", "mlbam_id": 111},
             "joshua_flores__sa3069242": {
                 "player_key": "joshua_flores__sa3069242", "mlbam_id": 222}}
    hits = ia.find_unsplit_collisions(roster, board)
    assert [h["status"] for h in hits] == ["split"]


def test_position_kind_classification():
    assert ia.position_kind("SIRP") == "P"
    assert ia.position_kind("RHP") == "P"
    assert ia.position_kind("DH") == "H"
    assert ia.position_kind("CF") == "H"
    assert ia.position_kind(None) is None
    assert ia.position_kind("???") is None


# ---------------------------------------------------------------------------
# 3. Ratchet over the real build artifacts
# ---------------------------------------------------------------------------

# Enumerated on 2026-07-24 from the tree as built. These are the merged
# identities that EXIST today; the tests below assert that nothing NEW
# joins them. Removing a key from this list as it gets repaired is the
# intended direction of travel. This is a subset assertion, never an
# equality assertion, so a repair never has to touch the test to stay green.
#
# Provenance: identity_audit.build() reproduces, independently, the counts
# the audit measured by hand - 12 unattributed merges (C1), 11 keys double
# bound in player_photos (C2), and the 6 id-less-but-placed active rows
# (C3), with jesus_flores present in all three.
KNOWN_MERGED_ACTIVE = frozenset({
    # jack_natili added 2026-08-04. The ONLY entry here that is NOT two humans on
    # one key: it is the INVERSE, one human on two ACTIVE board keys, and it is
    # baselined because the repair is out of reach rather than because the
    # evidence is thin.
    #   mlbam 814385  Jack Natili  b.2005-03-10  USA  C  draftYear 2026  ACL Rockies
    # He is published TWICE. "jackson_natili" is rank 160, carries 814385, and owns
    # the FanGraphs C/COL rows 2026-07-23 and 2026-08-02 (org rank 8, FV 45).
    # "jack_natili" is rank 332, carries NO id, and owns the 2026-08-04
    # draft_signing row (C/COL, FV 45); the roster join gives it level CPX, and an
    # id-less active row WITH a level is exactly C3. Same birth_date, position, org
    # and FV on both keys, and StatsAPI spells 814385 "Jack Natili" while FanGraphs
    # spells him "Jackson Natili" - one human, two source spellings.
    # Not repairable from the identity-binding lane: moving 814385 onto the draft
    # slug is precisely what the id-side guards added 2026-08-04
    # (storage.bind_player_ids and draft_promotion._harvest) refuse to do, and
    # they are correct to - "two spellings of one identity is a merge decision".
    # The real fix is the michael_oliveto treatment, a scrapers._CANONICAL_KEYS
    # entry collapsing jack_natili onto jackson_natili so a future FanGraphs drop
    # cannot re-fracture him, plus a merge of the two records. That is a key
    # re-map, which this repair class never does -> OWNER DECISION.
    "jack_natili",
    "alexander_de_los_santos",   # C2  808167 / 822195
    "carlos_gonzalez",           # C1 C2 C3 C4 C6  801262 / 808712
    "christian_rodriguez",       # C2  691010 / 815184
    "david_hernandez",           # C2  829967 / 830395
    "jesus_flores",              # C1 C2 C3 C4 C6  808222 / 837965 (trigger)
    "jesus_perez",               # C1  829777 / 829895
    "jose_perez",                # C2  699077 / 814545
    "juan_medina",               # C2  821265 / 839782
    "luis_carrasco",             # C2  682918 / 816263 (highest ranked, #448)
    "luis_leon",                 # C2  828783 / 830020
    "michael_braswell_iii",      # C3 C4
    "michael_oliveto__sa3069256",  # C3
    "neomar_urbina",             # C3
    "omar_calcurian",            # C3 C4
    "robinson_martinez",         # C2  660822 / 842067
    "ryan_brown",                # C2  688664 / 811286
})

# The graduated / inactive slices carry the rest of the class. They are
# still published surfaces, so they are ratcheted too, just separately.
KNOWN_MERGED_INACTIVE = frozenset({
    # drew_smith added 2026-07-31. Two genuinely different humans on one slug:
    # mlbam 622098 (RHP, 32.8, MIN AAA) and 805021 (3B, 23.1, SFG CPX). C1
    # unattributed -- the board record is INACTIVE, carries a null mlbam id and the
    # pitcher's RHP position, and c3_unresolved_active / critical_active_player_keys
    # are both 0, so nothing served is affected. Baselined as a real unresolved
    # identity, not as a suppressed regression: it needs an mlbam_id_overrides entry
    # plus a slug split, which is identity-resolution work rather than a test fix.
    "drew_smith",
    "aaron_brown", "adrian_hernandez", "alexander_campos", "anderson_franco",
    "david_rodriguez", "enmanuel_rodriguez", "jesus_lopez", "jorge_rodriguez",
    "jose_carlos_urena", "jose_gomez", "jose_martinez", "jose_rondon",
    "junior_garcia", "luis_garcia", "luis_valdez", "manuel_rodriguez",
    "michael_perez", "miguel_gomez",
    # C7 adjudication queue, added 2026-08-10 when the name-variant detector
    # first ran. These are SURFACED, not new: each is one human whose history
    # sits under two spellings, and every pair predates the detector. The
    # C1-C6 gates cannot see this class because the two keys carry different
    # slugs. Four originally-queued names already left the list the sanctioned
    # ways: jaiden_lore and zachary_root via PLAYER_KEY_ALIASES (the Root pair
    # binds ONE mlbam id, 702539, on both keys), and edwin_jimenez plus
    # luis_ramon_king because their pairs bind two DISTINCT mlbam ids, which
    # is two humans (the Kings are b.2007-12-04 KCR twins, ids 830428/830443)
    # and which C7 now auto-resolves. Each remaining entry leaves the same
    # ways: an alias verified on two independent signals, or a
    # distinct-mlbam-id proof. Do NOT bulk-alias them: the two-signal rule
    # exists because a wrong alias merges two humans.
    "alex_santos", "ben_cowles", "bj_murray_jr", "dennis_colleran",
    "dennis_colleran__noid", "dominic_keegan",
    "jared_jones__sa3034881", "javi_vaz", "jay_allen",
    "leonardo_bernal__noid", "lonnie_jr_white",
    "zach_thornton__noid",
})


@pytest.fixture(scope="module")
def live_report():
    board = ia.load_board_rows()
    roster = ia.load_roster_rows()
    if not board or not roster:
        pytest.skip("data/timeseries.json or data/rosters_by_org.json not built")
    # Mirrors build() exactly, C7 included: this fixture is what the
    # committed-artifact staleness test compares against, so a detector
    # present in one and not the other reads as spurious staleness.
    try:
        from consensus import PLAYER_KEY_ALIASES as aliases
    except Exception:
        aliases = {}
    return ia.audit(board_rows=board, roster_rows=roster,
                    photo_bindings=ia.load_photo_bindings(),
                    positions_played=ia.load_positions_played(),
                    snapshot_orgs=ia.load_snapshot_orgs(),
                    players_rows=ia.load_players_rows(),
                    aliases=aliases)


def test_no_new_merged_identity_on_the_active_board(live_report):
    """THE GATE. Any active board record newly showing the merge signature
    fails here, with the key named."""
    found = set(live_report["critical_active_player_keys"])
    new = sorted(found - KNOWN_MERGED_ACTIVE)
    assert not new, (
        "New merged identities on the active board: " + ", ".join(new) +
        ". Each is one player_key covering two different humans. See "
        "data/identity_collisions.json for the mlbam ids, and split the "
        "NEWCOMER onto a discriminated key - never re-key the incumbent.")


def test_no_new_merged_identity_anywhere(live_report):
    found = set(live_report["critical_player_keys"])
    new = sorted(found - KNOWN_MERGED_ACTIVE - KNOWN_MERGED_INACTIVE)
    assert not new, "New merged identities: " + ", ".join(new)


def test_no_two_mlbam_ids_ever_share_one_player_key_on_the_roster(live_report):
    """A hard invariant, not a baselined defect: this is 0 today and there
    is no legitimate reason for it to be anything else. Two ids literally
    carrying the same player_key means the roster join fused them."""
    assert live_report["summary"]["c1_shared_key"] == 0


def test_no_birth_date_contradicts_its_bound_mlbam_id(live_report):
    """A hard invariant. The audit's cleanest result: over every record
    where an mlbam id IS bound, zero birth dates disagree with StatsAPI by
    more than a year. The identity layer is correct wherever it has an id,
    which is exactly why the fix is identity resolution and not data."""
    assert live_report["birthdate_conflicts"] == []


def test_no_debuted_row_serves_another_humans_side(live_report):
    """A hard invariant (C4b, census M02-11): no served debuted row whose board
    position is on one side of the ball while every stat line of its bound id
    is on the other, outside the two-way allow-list. 3 on 2026-09-24
    (jose_rodriguez, michael_massey, carlos_rodriguez), 0 after the split."""
    hits = {r["player_key"]: r["board_position"]
            for r in live_report["debuted_side_conflicts"]}
    assert not hits, (
        "Debuted rows serving another human's side of the ball: " +
        ", ".join(f"{k} ({v})" for k, v in sorted(hits.items())) +
        ". Split the other human's board rows onto his own key by mlbam id "
        "(tools/repair_identity_split_2026_09_30.py is the pattern).")


def test_frankenstein_records_are_all_known(live_report):
    """Unidentified AND placed AND fielding on the wrong side. The tightest
    signature; 3 records today, all already known."""
    new = sorted(set(live_report["frankenstein_records"]) - KNOWN_MERGED_ACTIVE)
    assert not new, "New Frankenstein records: " + ", ".join(new)


def test_jesus_flores_is_bound_to_the_pitcher_and_nobody_else():
    """The trigger case, pinned at the canonical binding table itself.

    Repaired 2026-07-25 (tools/repair_identity_bindings.py G1): the key
    belongs to 808222, the Venezuelan RHP born 2005-03-16 who has pitched
    for the Brewers system every season since 2023 and is at Wisconsin
    (A+) now. 837965 is a DIFFERENT human - a catcher born 2008-11-06 in
    the DSL Rangers Blue system - who was fused onto the same key because
    player_photos constrains uniqueness on mlbam_id ALONE. He is carried
    separately as mlbam_837965 on the ungraded eFV surface; minting him a
    board record is an owner decision, not this test's business.

    This asserts the DB, not the report, so it holds the moment the repair
    lands rather than waiting for the next export to refresh the sidecars.
    """
    bindings = ia.load_photo_bindings()
    if not bindings:
        pytest.skip("prospects.db unavailable")
    assert bindings.get(808222) == "jesus_flores", (
        "the pitcher must own the key he has always owned")
    assert bindings.get(837965) != "jesus_flores", (
        "the DSL catcher (b.2008-11-06) is bound to the A+ pitcher's key "
        "(b.2005-03-16) again - the original Jesus Flores merge")
    on_key = sorted(mid for mid, key in bindings.items() if key == "jesus_flores")
    assert on_key == [808222], f"jesus_flores is bound to {on_key}, expected [808222]"


def test_no_player_key_is_bound_to_two_mlbam_ids(live_report):
    """C2 was 11 keys on 2026-07-25 and is 0 after the repair. Unlike the
    KNOWN_MERGED_* ratchets this is a hard invariant: player_photos is the
    canonical mlbam_id<->player_key table, and a key carrying two ids means
    two humans are fused wherever anything reads that table (the durable
    id fallback in the export, the mlbam_ingest collision guard, the TJStats
    exact-id join)."""
    doubled = {r["player_key"]: r["mlbam_ids"]
               for r in live_report["double_bound_keys"]}
    assert not doubled, (
        "player_key(s) bound to more than one mlbam id: " +
        ", ".join(f"{k} -> {v}" for k, v in sorted(doubled.items())) +
        ". Unbind the id whose StatsAPI birthDate does NOT match "
        "players.birth_date; never re-key the incumbent.")


def test_shadowed_slug_population_does_not_grow_unnoticed(live_report):
    """Not a defect list: 131 slugs where our record is correctly bound to
    one human and the OTHER human simply never gets a row. Each is one
    name-only ingest away from becoming a merge, so the count is watched.
    Raise the ceiling deliberately when a J2 class lands, do not delete it."""
    assert live_report["summary"]["c1_shadowed"] <= 160, (
        "Shadowed collision slugs grew past the watch ceiling: "
        f"{live_report['summary']['c1_shadowed']}")


# ---------------------------------------------------------------------------
# 4. The report artifact
# ---------------------------------------------------------------------------

def test_report_artifact_is_written_and_well_formed(tmp_path, live_report):
    """build(write=True) must produce a JSON report a build step can publish.
    Written to tmp_path so the suite never touches the real artifact."""
    out = tmp_path / "identity_collisions.json"
    report = ia.build(write=True, path=out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["summary"]["board_rows"] > 0
    for section in ("critical_player_keys", "critical_active_player_keys",
                    "frankenstein_records", "unsplit_collisions",
                    "double_bound_keys", "unresolved_active",
                    "side_conflicts", "debuted_side_conflicts",
                    "birthdate_conflicts", "org_splits",
                    "shadowed_slugs"):
        assert section in doc, section
    # Deterministic against the fixture-built report from the same tree.
    assert doc["summary"]["critical_player_keys"] == \
        live_report["summary"]["critical_player_keys"]


def test_committed_report_matches_a_fresh_run(live_report):
    """If data/identity_collisions.json is present, it must not be stale
    relative to the artifacts it describes."""
    path = Path(ia.REPORT_PATH)
    if not path.exists():
        pytest.skip("data/identity_collisions.json not built yet")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["critical_player_keys"] == live_report["critical_player_keys"]


def test_audit_never_writes_to_prospects_db():
    """Structural guard: the module opens the DB read-only, so running the
    report can never need a backup. Asserted on the source text because the
    connection string is the thing that must not regress."""
    import re
    src = Path(ia.__file__).read_text(encoding="utf-8")
    assert "?mode=ro" in src
    # Every SQL string in the module must be a SELECT, and no mutating verb
    # may appear in any SQL string literal.
    sql_literals = re.findall(r'"((?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|'
                              r'ALTER|REPLACE)[^"]*)"', src, re.IGNORECASE)
    assert sql_literals, "no SQL found; the guard would be vacuous"
    for stmt in sql_literals:
        assert stmt.upper().startswith("SELECT"), stmt
    # And the write API itself is never called.
    assert "commit()" not in src
    assert "executemany" not in src
