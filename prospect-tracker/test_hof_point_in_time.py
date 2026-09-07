# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""H-PRED-2. A frame that claims to be point-in-time has to be checked, not asserted.

`career_frame(as_of_year=Y)` reads like it answers "what did this career look like
in Y". It does not: `as_of_year` gates ELIGIBILITY only, and every feature on the
row is the FULL career. Ask it about 1995 and it hands you Barry Bonds' 162.8 WAR.
Fine for a shelf, fatal for a predictor, because a model trained on ballot year Y
with features containing Y+15 is not forward-chained, it is reading the answer.

`season_cutoff` closes it, on three surfaces that all had to move together:
  * the season aggregates,
  * `_position_inputs`, which summed the whole career off both stint frames, so
    relief_share knew how a pitcher's career ENDED,
  * and `_CAREER_CACHE`, whose key did not contain the cutoff, so the first
    full-career call would have poisoned every point-in-time call after it with
    a perfectly well-formed frame and no error anywhere.

THE CENTRAL TEST TRUNCATES INDEPENDENTLY. Comparing the parameter against itself
would prove nothing, so the reference path feeds pre-filtered frames through the
UNPARAMETERISED code and the two are compared row for row.
"""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

import hof_data as hd

CUTOFFS = (1985, 1995, 2005)
# Careers that straddle every cutoff, so truncation has real work to do.
PROBES = ("bondsba01", "ripkeca01", "clemero02", "johnswa01", "riverma01")


@pytest.fixture(autouse=True)
def _clean():
    hd.clear_cache()
    yield
    hd.clear_cache()


def _offline_or_skip():
    try:
        hd.season_frame(offline=True)
    except Exception as e:                              # noqa: BLE001
        pytest.skip(f"no offline WAR frame on this machine: {e}")
    return True


def test_as_of_equals_a_physically_truncated_frame():
    """The property, checked against an INDEPENDENT truncation.

    The reference builds its frame by pre-filtering season_frame and both stint
    frames and running the code path that knows nothing about a cutoff. If the
    parameter and the physical truncation ever disagree, one of them is wrong and
    this says which rows.
    """
    _offline_or_skip()
    cut = 1995
    got = hd.career_frame(offline=True, as_of_year=cut, season_cutoff=cut)

    full_seasons = hd.season_frame(offline=True)
    ref_seasons = full_seasons[
        pd.to_numeric(full_seasons["year_ID"], errors="coerce") <= cut].copy()
    full_pos = {s: hd.stint_frame(s, offline=True) for s in ("bat", "pit")}
    ref_pos = {s: f[pd.to_numeric(f["year_ID"], errors="coerce") <= cut].copy()
               for s, f in full_pos.items()}

    hd.clear_cache()
    real_season_frame, real_stint_frame = hd.season_frame, hd.stint_frame
    hd.season_frame = lambda **kw: ref_seasons.copy()
    hd.stint_frame = lambda side, **kw: ref_pos[side].copy()
    try:
        ref = hd.career_frame(offline=True, as_of_year=cut)   # NO cutoff argument
    finally:
        hd.season_frame, hd.stint_frame = real_season_frame, real_stint_frame
        hd.clear_cache()

    assert set(got["player_ID"]) == set(ref["player_ID"]), (
        "the parameterised frame and a physically truncated one disagree on WHICH "
        "players exist at the cutoff")
    a = got.set_index("player_ID").sort_index()
    b = ref.set_index("player_ID").sort_index()
    for col in ("career_war", "war7", "jaws", "career_waa", "waa_pos", "ink",
                "n_seasons", "first_season", "last_season", "pa", "ipouts",
                "pos_class", "relief_share"):
        if col not in a.columns or col not in b.columns:
            continue
        if a[col].dtype.kind in "fc":
            bad = (a[col].fillna(-999.0) - b[col].fillna(-999.0)).abs() > 1e-9
        else:
            bad = a[col].fillna("~") != b[col].fillna("~")
        assert not bad.any(), (
            f"{col} differs on {int(bad.sum())} player(s) between the cutoff "
            f"parameter and a physically truncated frame, e.g. "
            f"{list(a.index[bad][:5])}")


def test_the_cutoff_actually_removes_the_future():
    """A cutoff that changed nothing would pass the equality test above."""
    _offline_or_skip()
    full = hd.career_frame(offline=True).set_index("player_ID")
    early = hd.career_frame(offline=True, as_of_year=1995,
                            season_cutoff=1995).set_index("player_ID")
    probes = [p for p in PROBES if p in full.index and p in early.index]
    if not probes:
        pytest.skip("probe players absent from this WAR frame")
    moved = [p for p in probes
             if float(early.loc[p, "career_war"]) < float(full.loc[p, "career_war"]) - 1e-9]
    assert moved, (
        f"no probe career shrank at a 1995 cutoff, so the cutoff is not removing "
        f"seasons: {[(p, float(full.loc[p, 'career_war']), float(early.loc[p, 'career_war'])) for p in probes]}")
    for p in probes:
        assert int(early.loc[p, "last_season"]) <= 1995, (
            f"{p} carries a season after the cutoff")
        assert float(early.loc[p, "career_war"]) <= float(full.loc[p, "career_war"]) + 1e-9


def test_the_cache_key_carries_the_cutoff():
    """The leak that would have been hardest to see.

    _CAREER_CACHE was keyed on (offline, as_of_year). A full-career call followed
    by a point-in-time call at the same as_of_year would have returned the FULL
    career for the point-in-time question: a well-formed frame, the wrong answer,
    no error anywhere.
    """
    _offline_or_skip()
    full = hd.career_frame(offline=True, as_of_year=1995)                 # warms the cache
    early = hd.career_frame(offline=True, as_of_year=1995, season_cutoff=1995)
    assert full["career_war"].sum() > early["career_war"].sum() + 1.0, (
        "the cutoff call returned the cached full-career frame, so the cache key "
        "does not distinguish them")
    # and the reverse order must be just as safe
    hd.clear_cache()
    early2 = hd.career_frame(offline=True, as_of_year=1995, season_cutoff=1995)
    full2 = hd.career_frame(offline=True, as_of_year=1995)
    assert abs(early2["career_war"].sum() - early["career_war"].sum()) < 1e-6
    assert abs(full2["career_war"].sum() - full["career_war"].sum()) < 1e-6


def test_position_class_is_point_in_time_too():
    """relief_share is a CAREER quantity, and that is exactly the leak."""
    _offline_or_skip()
    pos_full = hd._position_inputs(offline=True)
    pos_early = hd._position_inputs(offline=True, season_cutoff=1995)
    common = pos_full.index.intersection(pos_early.index)
    assert len(common) > 100
    ip_full = pd.to_numeric(pos_full.loc[common, "ipouts"], errors="coerce").fillna(0.0)
    ip_early = pd.to_numeric(pos_early.loc[common, "ipouts"], errors="coerce").fillna(0.0)
    assert (ip_early <= ip_full + 1e-6).all(), (
        "a truncated position frame carries MORE exposure than the full one")
    assert ip_early.sum() < ip_full.sum(), (
        "truncating to 1995 removed no pitching exposure, so _position_inputs is "
        "ignoring the cutoff and pos_class still knows how careers ended")


def test_as_of_returns_none_before_a_career_starts():
    """"Had not played yet" and "played and was worth nothing" are different."""
    _offline_or_skip()
    assert hd.as_of("bondsba01", 1900, offline=True) is None
    row = hd.as_of("bondsba01", 1995, offline=True)
    if row is None:
        pytest.skip("bondsba01 absent from this WAR frame")
    assert int(row["last_season"]) <= 1995
    assert float(row["career_war"]) > 0.0


def test_as_of_is_monotone_in_the_cutoff():
    """Career WAR cannot fall as the window widens; WAR7 and ink cannot either.

    A cutoff before the player debuted returns None, which is the CORRECT answer
    and not a reason to abandon the check: the loop keeps going and asserts over
    the cutoffs where he existed. A first version skipped the whole test on the
    first None, so it silently tested nothing for any player who debuted after
    the earliest cutoff, which is most of them.
    """
    _offline_or_skip()
    seen = []
    for cut in CUTOFFS:
        row = hd.as_of("bondsba01", cut, offline=True)
        if row is None:
            continue          # had not played yet; not a failure
        seen.append((cut, float(row["career_war"]), float(row["war7"]),
                     float(row["ink"])))
    if len(seen) < 2:
        pytest.skip("bondsba01 exists at fewer than two cutoffs in this frame")
    for (c0, *prev), (c1, *cur) in zip(seen, seen[1:]):
        for name, a, b in zip(("career_war", "war7", "ink"), prev, cur):
            assert b >= a - 1e-9, (
                f"{name} FELL from {a} at cutoff {c0} to {b} at cutoff {c1}")
    assert seen[-1][1] > seen[0][1], (
        "career WAR did not grow at all across the cutoffs, so the window is "
        "not actually widening")
