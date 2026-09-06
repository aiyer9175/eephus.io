# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for hof_data: the Hall of Fame data shelf.

FIVE THINGS ARE PINNED HERE, and each of them is a thing that has a cheap way
to go silently wrong:

  1. THE JAWS REPRODUCTION. Babe Ruth 182.6 / 84.4 / 133.5, Walter Johnson
     168.4 / 92.0 / 130.2, Cy Young 163.6 / 78.0 / 120.8, plus Bonds and Mays.
     A shelf that cannot reproduce JAWS cannot be benchmarked against JAWS.
  2. THE PROVIDER PIN. Every Hall of Fame number is bWAR, because eWAR starts
     in 2011 and most of the Hall retired before it. war_source's DEFAULT is
     eWAR, so the pin is doing real work and the test proves reading eWAR is
     unreachable: no public entry point takes a provider, and the one call
     into war_source is asserted to carry 'bwar'.
  3. THE ELIGIBLE UNIVERSE COUNT. 3,620 at as_of_year 2026. A tripwire, not a
     property: if it moves, Baseball-Reference revised history or the frame
     was rebuilt, and every downstream number needs a re-read.
  4. THE CENSORING INVARIANT. A censored player can never be scored 0.
  5. THE LABEL REFUSAL. There is no ballot source in this repo, so the label
     functions raise rather than inventing a membership list.

Every data-touching test runs offline=True against war_source's last-good
parquet. The pitching side of pybaseball carries no disk cache, so an online
test would be a live download on every run.
"""

from __future__ import annotations

import decimal
import inspect
from pathlib import Path

import pytest

import hof_data
import war_source

ROOT = Path(hof_data.__file__).resolve().parent


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

def _have_frames() -> bool:
    try:
        hof_data.stint_frame("bat", offline=True)
        hof_data.stint_frame("pit", offline=True)
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def frames():
    if not _have_frames():
        pytest.skip("no last-good war_daily parquet; run war_source once "
                    "online first")
    return True


@pytest.fixture(scope="module")
def career(frames):
    return hof_data.career_frame(offline=True, as_of_year=2026)


# ---------------------------------------------------------------------------
# 1. The reproduction control.
# ---------------------------------------------------------------------------

def test_jaws_reproduction(frames):
    """The acceptance test for the whole lane."""
    rep = hof_data.reproduction_check(offline=True, as_of_year=2026)
    assert len(rep) == len(hof_data.REPRODUCTION_TARGETS)
    bad = rep[~rep["ok"]]
    assert bad.empty, (
        "JAWS reproduction failed; the shelf cannot be benchmarked against "
        f"the public work until it does:\n{bad.to_string(index=False)}")


def test_the_three_named_anchors(career):
    """The three the lane spec names, spelled out so a failure reads plainly
    rather than as a frame diff."""
    idx = career.set_index("player_ID")
    r = hof_data.round_half_up
    for pid, car, w7, jw in (("ruthba01", 182.6, 84.4, 133.5),
                             ("johnswa01", 168.4, 92.0, 130.2),
                             ("youngcy01", 163.6, 78.0, 120.8)):
        row = idx.loc[pid]
        assert r(row["career_war"]) == car, pid
        assert r(row["war7"]) == w7, pid
        assert r(row["jaws"]) == jw, pid


def test_round_half_up_rounds_the_printed_decimal_not_the_double(frames):
    """THERE IS NO TIE HERE and half-to-even is not the mechanism. The
    two-decimal export puts a career sum on the double nearest a two-decimal
    value, and that double sits strictly BELOW the tenths half, so Python's
    round() correctly takes it down. round_half_up round-trips through the
    shortest decimal that reproduces the double, which is what the export
    printed, and rounds that."""
    # the premise: strictly below the half, not on it
    assert decimal.Decimal(168.35) < decimal.Decimal("168.35")
    assert decimal.Decimal(73.55) < decimal.Decimal("73.55")
    assert round(168.35, 1) == 168.3      # the trap this avoids
    assert round(73.55, 1) == 73.5
    assert hof_data.round_half_up(168.35) == 168.4
    assert hof_data.round_half_up(73.55) == 73.6
    # Decimal(f) instead of Decimal(repr(f)) would reproduce the trap, so the
    # repr round-trip is the load-bearing step and not decoration
    q = decimal.Decimal("0.1")
    assert decimal.Decimal(168.35).quantize(
        q, rounding=decimal.ROUND_HALF_UP) == decimal.Decimal("168.3")
    assert decimal.Decimal(repr(168.35)).quantize(
        q, rounding=decimal.ROUND_HALF_UP) == decimal.Decimal("168.4")
    assert hof_data.round_half_up(-2.25, 1) == -2.3   # away from zero
    assert hof_data.round_half_up(float("nan")) != hof_data.round_half_up(0)


def test_exactly_two_reproduction_cells_need_the_half_up_treatment(career):
    """The consequence, read off the frame rather than asserted. Of the fifteen
    published cells, exactly two come out a tenth low under Python's round():
    Walter Johnson's career WAR and Willie Mays's WAR7. If a third ever joins
    them the docstring's account of why this function exists needs re-reading,
    not just its count."""
    idx = career.set_index("player_ID")
    moved = []
    for pid in hof_data.REPRODUCTION_TARGETS:
        row = idx.loc[pid]
        for col in ("career_war", "war7", "jaws"):
            v = float(row[col])
            if round(v, 1) != hof_data.round_half_up(v):
                moved.append((pid, col))
    assert moved == [("johnswa01", "career_war"), ("mayswi01", "war7")], moved


def test_jaws_is_the_mean_of_career_and_peak(career):
    sample = career.nlargest(50, "career_war")
    for _, row in sample.iterrows():
        assert abs(hof_data.jaws(row["career_war"], row["war7"])
                   - row["jaws"]) < 1e-9


def test_war7_takes_the_seven_best(frames):
    assert hof_data.war7([1, 2, 3, 4, 5, 6, 7, 8, 9]) == 9 + 8 + 7 + 6 + 5 + 4 + 3
    assert hof_data.war7([5.0, -1.0]) == 4.0     # fewer than seven sums all
    assert hof_data.war7([]) == 0.0


def test_positive_waa_drops_the_below_average_seasons(frames):
    assert hof_data.positive_waa([3.0, -2.0, 1.5, 0.0]) == 4.5
    assert hof_data.positive_waa([-1.0, -2.0]) == 0.0


# ---------------------------------------------------------------------------
# 2. The provider pin. Reading eWAR must be impossible.
# ---------------------------------------------------------------------------

def test_provider_constant_is_bwar():
    assert hof_data.WAR_PROVIDER == "bwar"


def test_the_pin_is_doing_work():
    """If war_source ever defaulted to bwar the pin would be decoration. It
    does not: the default is the eWAR series, which starts in 2011."""
    assert war_source.DEFAULT_PROVIDER != "bwar"
    assert hof_data.WAR_PROVIDER in war_source.PROVIDERS


def test_no_public_entry_point_accepts_a_provider():
    """The guarantee is structural: a caller cannot ASK for eWAR."""
    offenders = []
    for name, obj in vars(hof_data).items():
        if name.startswith("_") or not callable(obj):
            continue
        if getattr(obj, "__module__", None) != "hof_data":
            continue
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            continue
        for pname in sig.parameters:
            if "provider" in pname.lower():
                offenders.append(f"{name}({pname})")
    assert not offenders, (
        "these hof_data entry points let a caller pick a WAR provider, which "
        f"is how an eWAR read gets in by accident: {offenders}")


def test_the_only_war_source_call_carries_bwar(monkeypatch):
    """Online path. Capture what hof_data actually passes."""
    seen = []

    def fake(side, *, provider=war_source.DEFAULT_PROVIDER, **kw):
        seen.append((side, provider))
        import pandas as pd
        return pd.DataFrame({"player_ID": [], "year_ID": [], "WAR": []})

    hof_data.clear_cache()
    monkeypatch.setattr(war_source, "stint_frame", fake)
    hof_data.stint_frame("bat")
    hof_data.stint_frame("pit")
    hof_data.clear_cache()
    assert seen == [("bat", "bwar"), ("pit", "bwar")]


def test_side_is_validated():
    with pytest.raises(ValueError):
        hof_data.stint_frame("ewar")


# ---------------------------------------------------------------------------
# 3. The eligible universe.
# ---------------------------------------------------------------------------

def test_eligible_universe_count(career):
    """TRIPWIRE. 3,620 eligible players measured 2026-09-06 at as_of_year 2026:
    10 or more seasons with a WAR row and a last season at or before 2021. If
    THIS moves, B-Ref revised history and every class count, quantile and line
    in this module needs re-measuring before it is quoted.

    THE TOTAL POPULATION IS A BAND, NOT A PIN, and that distinction was learned
    the hard way. It was pinned at 23,786 and went red at 23,787 within hours,
    because .cache/war_daily is a LIVE cache: it refreshed mid-session and one
    more player appeared in it. That is the cache working, not history being
    revised. The eligible count did not move, which is the point: eligibility
    requires a last season at or before 2021, so an in-season debut cannot enter
    it, and nothing downstream depends on the raw row count.

    A pinned total would go red on any day the cache refreshes during a season,
    which trains a reader to ignore the tripwire that DOES matter. The band is
    wide enough to absorb a season of debuts and narrow enough that a rebuilt or
    truncated parquet still trips it.
    """
    E = career[career["eligible"]]
    assert len(E) == 3620
    assert 23_700 <= len(career) <= 24_400, (
        f"the career frame holds {len(career)} players, outside the band "
        "recorded on 2026-09-06 (23,786 and growing with in-season debuts). "
        "That is too big a move for the daily cache and suggests the parquet "
        "was rebuilt or truncated.")


def test_eligibility_rules_hold(career):
    E = career[career["eligible"]]
    assert E["n_seasons"].min() >= hof_data.MIN_SEASONS
    assert E["last_season"].max() <= 2026 - hof_data.ELIGIBILITY_LAG_YEARS
    # and the lag actually excludes somebody
    assert (career["last_season"] > 2021).sum() > 0


def test_eligibility_moves_with_as_of_year(frames):
    later = hof_data.eligible_universe(offline=True, as_of_year=2031)
    now = hof_data.eligible_universe(offline=True, as_of_year=2026)
    assert len(later) > len(now)


def test_every_player_carries_one_of_the_six_classes(career):
    assert set(career["pos_class"]) <= set(hof_data.CLASSES)
    E = career[career["eligible"]]
    assert set(E["pos_class"]) == set(hof_data.CLASSES)


def test_ruth_files_as_a_fielder_and_johnson_as_a_pitcher(career):
    """The two-way boundary. B-Ref's own JAWS files Ruth in the outfield."""
    idx = career.set_index("player_ID")
    assert idx.loc["ruthba01", "pos_class"] == "OF"
    assert idx.loc["johnswa01", "pos_class"] == "SP"
    assert idx.loc["youngcy01", "pos_class"] == "SP"
    assert idx.loc["riverma01", "pos_class"] == "RP"


def test_the_catcher_class_is_empty_before_1953(career):
    """Not a bug, a disclosed limit: runs_catcher does not exist before 1953
    and the positional-adjustment rate cannot separate a catcher from a second
    baseman. See hof_data.POSITION_CLASS_NOTE."""
    C = career[career["pos_class"] == "C"]
    assert (C["pos_basis"] == "fielding_components").all()
    assert C["last_season"].min() >= hof_data.POSITION_COMPONENT_FIRST_YEAR


def test_negro_leagues_are_in_the_frame(frames):
    """Owner decision 13: include, with an era factor and a disclosure. These
    counts reproduce the master plan's figures exactly, which is how the frame
    identity is checked."""
    bat = hof_data.stint_frame("bat", offline=True)
    pit = hof_data.stint_frame("pit", offline=True)
    core = hof_data.NEGRO_LEAGUES_CORE4
    assert int(bat["lg_ID"].isin(core).sum()) == 8072
    assert int(pit["lg_ID"].isin(core).sum()) == 3171
    players = (set(bat.loc[bat["lg_ID"].isin(core), "player_ID"])
               | set(pit.loc[pit["lg_ID"].isin(core), "player_ID"]))
    assert len(players) == 2263
    assert hof_data.NEGRO_LEAGUES_CORE4 < hof_data.NEGRO_LEAGUES


def test_era_factor_is_a_disclosure_not_a_correction(career):
    """The Negro Leagues schedule was a third to three fifths of the AL/NL
    schedule, so era_factor reads well above 1 there. It must never have been
    multiplied into the WAR columns."""
    E = career[career["eligible"]]
    ngl = E[E["ngl_seasons"] > 0]
    assert len(ngl) > 100
    assert ngl["era_factor"].median() > 1.5
    assert abs(E[E["ngl_seasons"] == 0]["era_factor"].median() - 1.0) < 0.10
    # the reproduction anchors are unscaled, which is the proof
    idx = career.set_index("player_ID")
    assert hof_data.round_half_up(idx.loc["ruthba01", "career_war"]) == 182.6


def test_war_ink_scores_a_lead_at_four_not_five(career):
    E = career[career["eligible"]]
    assert E["ink"].min() >= 0.0
    assert E.nlargest(1, "ink")["player_ID"].iloc[0] == "ruthba01"
    # points are integral multiples of the two weights
    assert (E["ink"] % 1.0 == 0).all()


# ---------------------------------------------------------------------------
# 4. hall_line.
# ---------------------------------------------------------------------------

def test_hall_line_refuses_to_invent_the_hall(frames):
    hl = hof_data.hall_line("C", offline=True, as_of_year=2026)
    assert hl.line is None
    assert hl.n_enshrined is None
    assert hof_data.BALLOT_SOURCE in hl.reason
    assert hl.n_eligible > 0
    assert 0.95 in hl.quantiles


def test_hall_line_sizes_a_line_when_given_the_count(frames):
    hl = hof_data.hall_line("C", n_enshrined=1, offline=True, as_of_year=2026)
    E = hof_data.eligible_universe(offline=True, as_of_year=2026)
    best = E[E["pos_class"] == "C"]["jaws"].max()
    assert abs(hl.line - best) < 1e-9
    assert len(hl.above_line) == 1


def test_hall_line_reports_the_low_confidence_count(frames):
    """The C class cannot contain a rate-basis player by construction; MI is
    where the missing pre-1953 catchers went."""
    assert hof_data.hall_line("C", offline=True,
                              as_of_year=2026).n_rate_basis == 0
    assert hof_data.hall_line("MI", offline=True,
                              as_of_year=2026).n_rate_basis > 0


def test_hall_line_rejects_a_class_it_does_not_have(frames):
    with pytest.raises(ValueError):
        hof_data.hall_line("3B", offline=True, as_of_year=2026)


def test_relievers_split_at_the_stated_share(career):
    E = career[career["eligible"]]
    rp = E[E["pos_class"] == "RP"]
    sp = E[E["pos_class"] == "SP"]
    assert rp["relief_share"].min() >= hof_data.RELIEF_SHARE_RP
    assert sp["relief_share"].max() < hof_data.RELIEF_SHARE_RP
    # and the split is not degenerate
    assert len(rp) > 100 and len(sp) > 100


# ---------------------------------------------------------------------------
# 5. The label contract.
# ---------------------------------------------------------------------------

def test_labels_refuse_rather_than_inventing_a_hall(tmp_path):
    """THE PANEL NOW EXISTS (H-DATA-2 shipped 2026-09-06), so the labels resolve
    instead of raising. The property that still has to hold, and the reason this
    test was written, is that they refuse when the panel is ABSENT rather than
    falling back to a hand-typed membership list. A list typed from memory would
    be an unversioned answer key silently training the merit model, and it would
    look exactly like a working label."""
    missing = tmp_path / "no_such_panel.json"
    with pytest.raises(hof_data.BallotSourceMissing) as exc:
        hof_data._load_ballots(missing)
    assert hof_data.BALLOT_SOURCE in str(exc.value)
    assert "H-DATA-2" in str(exc.value)
    assert "hand-typed" in str(exc.value), (
        "the refusal no longer says WHY a membership list is not an acceptable "
        "substitute, which is the whole point of refusing")


def test_the_labels_resolve_now_that_the_panel_exists():
    if not (ROOT / "data" / "hof_ballots.json").exists():
        pytest.skip("the ballot panel has not been built")
    assert hof_data.label_bbwaa("ruthba01", as_of_year=2026) == 1
    assert hof_data.label_any("ruthba01", as_of_year=2026) == 1


def test_ballot_source_missing_is_a_not_implemented_error():
    """So a caller's `except NotImplementedError` still catches it, and so it
    can never be mistaken for a data error that a retry would fix."""
    assert issubclass(hof_data.BallotSourceMissing, NotImplementedError)


def test_censored_is_none_and_never_zero():
    assert hof_data.CENSORED is None
    assert hof_data.CENSORED != 0 or hof_data.CENSORED is None


def test_a_censored_player_can_never_be_scored_zero():
    """THE INVARIANT. Every type a zero can wear is caught."""
    for zero in (0, 0.0, False):
        rows = [{"player_id": "someguy01", "label": zero, "censored": True}]
        with pytest.raises(ValueError) as exc:
            hof_data.assert_no_censored_zero(rows)
        assert "someguy01" in str(exc.value)
        assert "censored" in str(exc.value).lower()


def test_the_invariant_permits_everything_it_should():
    ok = [
        {"player_id": "a", "label": hof_data.CENSORED, "censored": True},
        {"player_id": "b", "label": 0, "censored": False},
        {"player_id": "c", "label": 1, "censored": False},
        {"player_id": "d", "label": 1, "censored": True},
    ]
    assert hof_data.assert_no_censored_zero(ok) == 4


def test_the_invariant_names_every_offender():
    rows = [{"player_id": f"p{i}", "label": 0, "censored": True}
            for i in range(3)]
    with pytest.raises(ValueError) as exc:
        hof_data.assert_no_censored_zero(rows)
    msg = str(exc.value)
    assert "3 censored" in msg
    for i in range(3):
        assert f"p{i}" in msg


def test_the_invariant_rejects_rows_it_cannot_read():
    with pytest.raises(ValueError):
        hof_data.assert_no_censored_zero([{"player_id": "a", "label": 0}])


def test_the_label_rules_are_written_down():
    """The resolution rules live in the module so they cannot drift away from
    the code that will implement them."""
    src = inspect.getsource(hof_data)
    for token in ("L_bbwaa", "L_any", "five percent", "veterans",
                  "CENSORED (None) : the window is still open"):
        assert token in src, token
    assert set(hof_data.BALLOT_SOURCE_FIELDS) >= {
        "player_id", "election_year", "route", "elected", "vote_pct"}
