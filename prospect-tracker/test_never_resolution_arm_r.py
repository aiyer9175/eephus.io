# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ARM R, the never-MLB resolution fix, flagged and default OFF.

docs/efv-2026-10-02/BUST2_GATE.md registers it; plan 3.2 records the three resolution
routes; FWAR_LABEL_EPOCH_GATE.md part 6 admits it as clause (i) factor F3.

The load-bearing property is that OFF is the incumbent to the byte, because the epoch
attributes every moved number to a named factor and a flag leaking into a default build
would destroy that attribution. The fixture half of that pin is here (no matrix build,
no DB, no cache read); the real-data half is the two temp builds the flag's commit
records. Everything else is the arm's own behaviour on synthetic rows.
"""

from __future__ import annotations

import copy
import inspect
from pathlib import Path

import pytest

import efv_dataset as ed
import milb_history as mh

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# the flags
# ---------------------------------------------------------------------------

def test_arm_r_defaults_off_and_the_label_key_is_the_served_series():
    assert ed.NEVER_RESOLUTION_ARM_R is False
    assert ed.LABEL_SEASONS_KEY == "seasons"
    assert ed.NEVER_RESOLUTION_AGE == 27
    assert ed.NEVER_RESOLUTION_STALE_LIST_YEARS == 5
    assert ed.BUST2_MLB_SUM_WAR == 3.0
    assert ed.NEVER_RESOLUTION_ROUTES == ("no_affiliated_line", "age_27", "stale_list")


@pytest.fixture
def arm_r():
    old = ed.NEVER_RESOLUTION_ARM_R
    ed.NEVER_RESOLUTION_ARM_R = True
    try:
        yield
    finally:
        ed.NEVER_RESOLUTION_ARM_R = old


# ---------------------------------------------------------------------------
# the three routes
# ---------------------------------------------------------------------------

def _affiliated(lines: dict):
    """An injectable lookup: {(mlbam, season): True} for rows with an affiliated line."""
    def _f(mlbam, season):
        return bool(lines.get((int(mlbam), int(season))))
    return _f


LATEST = [2026, 2025, 2024]


def test_route_1_no_affiliated_line_in_either_of_the_two_latest_seasons():
    aff = _affiliated({(7, 2024): True})           # played in 2024, nothing since
    assert ed.never_resolution(7, "2001-01-01", 2023, LATEST, 2025, aff) == "no_affiliated_line"
    # a line in EITHER of the two latest seasons keeps him censored (under 27, id known)
    aff2 = _affiliated({(7, 2025): True})
    assert ed.never_resolution(7, "2001-01-01", 2023, LATEST, 2025, aff2) is None
    aff3 = _affiliated({(7, 2026): True})
    assert ed.never_resolution(7, "2001-01-01", 2023, LATEST, 2025, aff3) is None


def test_route_1_needs_an_id_and_two_seasons_on_disk():
    aff = _affiliated({})
    # no id: the lookup cannot be made, and a young row with no id is censored
    assert ed.never_resolution(None, "2001-01-01", 2023, LATEST, 2025, aff) is None
    # one season on disk: "either of the two latest" cannot be read
    assert ed.never_resolution(7, "2001-01-01", 2023, [2026], 2025, aff) is None
    assert ed.never_resolution(7, "2001-01-01", 2023, [], 2025, aff) is None


def test_route_2_age_27_on_july_1_of_resolved_through():
    aff = _affiliated({(7, 2025): True, (7, 2026): True})   # still playing
    # born 1998-07-01: 27 on 2025-07-01 exactly
    assert ed.never_resolution(7, "1998-07-01", 2025, LATEST, 2025, aff) == "age_27"
    # born 1998-07-02: 26 on 2025-07-01, still affiliated -> censored
    assert ed.never_resolution(7, "1998-07-02", 2025, LATEST, 2025, aff) is None
    # the clock is RESOLVED_THROUGH: the same row resolves at RT 2026
    assert ed.never_resolution(7, "1998-07-02", 2025, LATEST, 2026, aff) == "age_27"
    # no id but a birth date: the age route alone decides
    assert ed.never_resolution(None, "1990-05-05", 2025, LATEST, 2025, aff) == "age_27"


def test_route_3_stale_list_only_with_neither_id_nor_birth_date():
    aff = _affiliated({})
    assert ed.never_resolution(None, None, 2020, LATEST, 2025, aff) == "stale_list"
    assert ed.never_resolution(None, None, 2021, LATEST, 2025, aff) is None
    # an id or a birth date takes the row off this route
    assert ed.never_resolution(None, "2004-01-01", 2020, LATEST, 2025, aff) is None
    # (an id with no line in the window resolves by route 1, not route 3)
    assert ed.never_resolution(9, None, 2020, LATEST, 2025, aff) == "no_affiliated_line"
    aff_playing = _affiliated({(9, 2026): True})
    assert ed.never_resolution(9, None, 2020, LATEST, 2025, aff_playing) is None
    assert ed.never_resolution(None, None, None, LATEST, 2025, aff) is None


def test_age_on_july_1_handles_bad_dates():
    assert ed._age_on_july_1("1998-07-01", 2025) == 27
    assert ed._age_on_july_1("1998-07-02", 2025) == 26
    assert ed._age_on_july_1(None, 2025) is None
    assert ed._age_on_july_1("1998", 2025) is None
    assert ed._age_on_july_1("1998-13-01", 2025) is None


def test_milb_seasons_on_disk_reads_minor_sport_caches_only(tmp_path, monkeypatch):
    for name in ("hitting_1_2026.json", "pitching_1_2027.json",     # MLB only: ignored
                 "hitting_11_2026.json", "pitching_14_2025.json", "hitting_16_2023.json",
                 "notes.json", "hitting_x_2024.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    monkeypatch.setattr(mh, "CACHE_DIR", tmp_path)
    assert ed.milb_seasons_on_disk() == [2026, 2025, 2023]


# ---------------------------------------------------------------------------
# the application to built rows: flag-off identity, flag-on marks
# ---------------------------------------------------------------------------

def _bust(pk, *, mlbam=None, birth=None, cutoff="2022-08-01", recent=False):
    return {"player_key": pk, "kind": "bust", "debut_year": None, "is_pitcher": False,
            "cutoff": cutoff, "target_resolved": 0.0, "target_censored": 0.0,
            "censored": False, "weight": 0.5 if recent else 1.0,
            "observed_seasons": 6, "bust_recent": recent, "mlbam_id": mlbam,
            "birth_date": birth, "position": "SS", "consensus_fv_raw": 40.0}


def _debuted(pk, target):
    return {"player_key": pk, "kind": "debuted", "debut_year": 2017, "is_pitcher": False,
            "cutoff": "2017-06-01", "target_resolved": target, "target_censored": target,
            "censored": False, "weight": 1.0, "observed_seasons": 6, "mlbam_id": 1,
            "birth_date": "1995-01-01", "position": "SS", "consensus_fv_raw": 50.0}


def _fixture_rows():
    return [
        _debuted("d_neg", -1.4),                                   # negative label, kept
        _debuted("d_star", 12.0),
        _bust("b_playing", mlbam=11, birth="2002-03-03", cutoff="2025-07-01", recent=True),
        _bust("b_gone", mlbam=12, birth="2002-03-03", cutoff="2023-07-01"),
        _bust("b_old", mlbam=13, birth="1996-01-01", cutoff="2025-07-01", recent=True),
        _bust("b_noid_old", birth="1990-01-01", cutoff="2024-07-01", recent=True),
        _bust("b_nothing_stale", cutoff="2019-07-01"),
        _bust("b_nothing_recent", cutoff="2022-07-01"),
        _bust("b_still_young_noid", birth="2004-01-01", cutoff="2020-07-01"),
    ]


_LINES = {(11, 2026): True, (11, 2025): True, (13, 2026): True}


@pytest.fixture
def fixture_cache(monkeypatch):
    monkeypatch.setattr(ed, "milb_seasons_on_disk", lambda: [2026, 2025, 2024])
    monkeypatch.setattr(ed, "_has_affiliated_line", _affiliated(_LINES))
    monkeypatch.setattr(ed, "RESOLVED_THROUGH", 2025)


def test_flag_off_touches_nothing_and_reads_nothing(monkeypatch):
    """The identity pin on a fixture: rows and accounting come back equal, and the
    on-disk window is never even listed."""
    assert ed.NEVER_RESOLUTION_ARM_R is False

    def _boom():
        raise AssertionError("the flag-off path listed the MiLB cache")
    monkeypatch.setattr(ed, "milb_seasons_on_disk", _boom)
    monkeypatch.setattr(ed, "_has_affiliated_line", lambda *_a: (_ for _ in ()).throw(
        AssertionError("the flag-off path read an affiliated line")))
    rows = _fixture_rows()
    before = copy.deepcopy(rows)
    acct = {"bust_recent_flagged": 3, "bust_kept": 7}
    ed._apply_never_resolution(rows, acct)
    assert rows == before
    assert acct == {"bust_recent_flagged": 3, "bust_kept": 7}
    assert not any("arm_r_resolved_by" in r for r in rows)


def test_build_matrix_calls_the_arm_once_before_the_sidecars():
    src = inspect.getsource(ed.build_matrix)
    assert src.count("_apply_never_resolution(rows, acct)") == 1
    assert src.index("_apply_never_resolution(rows, acct)") < src.index("_load_sidecars(")


def test_flag_on_marks_every_route_and_the_censored_exclusion(arm_r, fixture_cache):
    rows = _fixture_rows()
    acct = {"bust_recent_flagged": 3}
    ed._apply_never_resolution(rows, acct)
    by = {r["player_key"]: r for r in rows}
    # debuted rows are untouched, the negative label included (no L1 flooring)
    assert by["d_neg"]["target_resolved"] == -1.4 and "arm_r_resolved_by" not in by["d_neg"]
    # CENSORED-NEVER: still affiliated, under 27, id known -> excluded like bust_recent
    assert by["b_playing"]["arm_r_resolved_by"] is None
    assert by["b_playing"]["bust_recent"] is True and by["b_playing"]["weight"] == 0.5
    # route 1
    assert by["b_gone"]["arm_r_resolved_by"] == "no_affiliated_line"
    assert by["b_gone"]["bust_recent"] is False and by["b_gone"]["weight"] == 1.0
    # route 2: playing in 2026 but 29 on 2025-07-01; was bust_recent, now resolved
    assert by["b_old"]["arm_r_resolved_by"] == "age_27"
    assert by["b_old"]["bust_recent"] is False and by["b_old"]["weight"] == 1.0
    assert by["b_noid_old"]["arm_r_resolved_by"] == "age_27"
    # route 3: neither id nor birth date, last list 2019 <= 2020
    assert by["b_nothing_stale"]["arm_r_resolved_by"] == "stale_list"
    # neither id nor birth date and listed 2022: unknowable -> censored, though the
    # incumbent rule had it resolved at full weight
    assert by["b_nothing_recent"]["arm_r_resolved_by"] is None
    assert by["b_nothing_recent"]["bust_recent"] is True
    # a birth date but no id, 21 years old: censored (no route can read him)
    assert by["b_still_young_noid"]["arm_r_resolved_by"] is None
    # the target never moves
    assert all(r["target_resolved"] == 0.0 and r["target_censored"] == 0.0
               for r in rows if r["kind"] == "bust")
    c = acct["arm_r"]
    assert c["milb_seasons_on_disk_window"] == [2026, 2025]
    assert c["resolved_through"] == 2025
    assert c["bust_rows"] == 7 and c["censored_never"] == 3
    assert c["resolved_no_affiliated_line"] == 1
    assert c["resolved_age_27"] == 2 and c["resolved_stale_list"] == 1
    assert c["resolved_to_censored"] == 2          # b_nothing_recent, b_still_young_noid
    assert c["censored_to_resolved"] == 2          # b_old, b_noid_old
    assert acct["bust_recent_flagged"] == 3


def test_censored_never_rows_are_excluded_by_the_pool_filter_every_consumer_uses(
        arm_r, fixture_cache):
    """The exclusion rides `bust_recent`, the marker efv_model's pools filter on."""
    rows = _fixture_rows()
    ed._apply_never_resolution(rows, {})
    pool = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    kept = {r["player_key"] for r in pool}
    assert kept == {"d_neg", "d_star", "b_gone", "b_old", "b_noid_old", "b_nothing_stale"}
    import efv_model as em
    src = inspect.getsource(em)
    assert 'not (r["kind"] == "bust" and r.get("bust_recent"))' in src


# ---------------------------------------------------------------------------
# the label series key
# ---------------------------------------------------------------------------

def test_label_seasons_default_reads_the_served_series_and_counts_no_fallback():
    assert ed._label_seasons({"seasons": {"2019": 1.0}, "seasons_ewar_v2": {"2019": 9.0}}) == (
        {"2019": 1.0}, 0)
    assert ed._label_seasons({}) == ({}, 0)
    assert ed._label_seasons({"seasons": None}) == ({}, 0)


def test_label_seasons_key_reads_the_incumbent_and_counts_the_fallback(monkeypatch):
    monkeypatch.setattr(ed, "LABEL_SEASONS_KEY", "seasons_ewar_v2")
    assert ed._label_seasons({"seasons": {"2019": 1.0}, "seasons_ewar_v2": {"2019": 9.0}}) == (
        {"2019": 9.0}, 0)
    # an empty incumbent dict is an answer, not a fallback
    assert ed._label_seasons({"seasons": {"2019": 1.0}, "seasons_ewar_v2": {}}) == ({}, 0)
    # a row the rebase never reached keeps `seasons` as its incumbent, counted
    assert ed._label_seasons({"seasons": {"2019": 1.0}}) == ({"2019": 1.0}, 1)
    assert ed._label_seasons({"seasons": {"2019": 1.0}, "seasons_ewar_v2": None}) == (
        {"2019": 1.0}, 1)


# ---------------------------------------------------------------------------
# the categories
# ---------------------------------------------------------------------------

def test_bust2_categories_read_off_the_row():
    assert ed.bust2_category(_debuted("a", 2.999)) == "BUST-MLB"
    assert ed.bust2_category(_debuted("a", 3.0)) == "NON-BUST"
    assert ed.bust2_category(_debuted("a", -2.0)) == "BUST-MLB"
    cens = dict(_debuted("a", 4.0), censored=True)
    assert ed.bust2_category(cens) == "UNRESOLVED-MLB"
    assert ed.bust2_category(_bust("b")) == "BUST-NEVER"
    assert ed.bust2_category(_bust("b", recent=True)) == "CENSORED-NEVER"
    assert ed.bust2_category({"kind": "active"}) == "NOT-LABELLED"
    assert ed.is_resolved_row(_debuted("a", 1.0)) and ed.is_resolved_row(_bust("b"))
    assert not ed.is_resolved_row(cens) and not ed.is_resolved_row(_bust("b", recent=True))
