# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""C-4 era floor pins.

Measurement: docs/efv-2026-08-13/C4_ERA_FLOOR_MEASUREMENT.md.

A cell earlier than `_REFERENCE_FIRST_YEAR` has no own-year pairs, because the
reference scale does not exist before 2017-02-15, so it falls through to the
thin-cell pool and takes an offset estimated from cycles ENTIRELY LATER than the
grade being normalized. The era floor bounds that pool at the reference's first
year: the closest era that can be measured, instead of a decade of later drift.

Two properties are guarded here and they pull in opposite directions, which is
why both are needed. The floor must bite when the as-of cap is on, and it must be
COMPLETELY INERT while the cap is off, because `consensus.GRADE_NORM_AS_OF` is
still False and flipping it is a basis change on eFV's dominant feature that owes
its own rebuild and margin re-read.
"""
from __future__ import annotations

import pytest

import grade_normalization as GN

RF = GN._REFERENCE_FIRST_YEAR
PRE = RF - 4          # a pre-reference cell year that exists in the corpus
SRC = "mlb_pipeline"  # the only source that serves pre-2017 units


def _offset(source, role, year, as_of):
    src, ref, pooled = GN._paired_dists(source, role, year, as_of)
    if not len(src):
        return None, pooled, 0
    return float(src.mean() - ref.mean()), pooled, len(src)


def test_the_floor_is_inert_while_the_as_of_cap_is_off():
    """With as_of_year None the pool must still reach every year.

    This is the property that makes landing the mechanism safe ahead of the flip.
    `cap` collapses to None, so both the loop guard and the recursive _pairs call
    reduce to exactly what they were.
    """
    off, pooled, n = _offset(SRC, "hitter", PRE, None)
    assert off is not None and pooled, "pre-reference cell should still pool"
    off_era, _p, n_era = _offset(SRC, "hitter", PRE, 2026)
    assert n > n_era, (
        f"uncapped pool ({n}) must be larger than the era-floored pool ({n_era}); "
        f"if they match, the floor is firing when the cap is off")


def test_the_floor_bites_when_the_cap_is_on():
    """A pre-reference cell must be estimated from the reference's FIRST year."""
    for role in ("hitter", "pitcher"):
        off_all, _pa, n_all = _offset(SRC, role, PRE, 2026)
        assert off_all is not None, f"{role} pre-reference cell lost its offset"
        # the era-floored pool is exactly the reference's own first year
        off_2017, _p2, n_2017 = _offset(SRC, role, RF, RF)
        assert n_all == n_2017, (
            f"{role}: era-floored pool n={n_all} should equal the {RF} cell's "
            f"n={n_2017}")
        assert abs(off_all - off_2017) < 1e-9


def test_the_floor_keeps_the_cell_above_the_min_n_bar():
    """The floor must not starve the cell it is protecting.

    Dropping below _MIN_N would send the cell to the RAW scale, which reinstates
    the ~4 FV bias the normalization exists to remove, and would be a far worse
    outcome than the leak.
    """
    for role in ("hitter", "pitcher"):
        _off, _pooled, n = _offset(SRC, role, PRE, 2026)
        assert n >= GN._MIN_N, f"{role} era-floored pool n={n} under _MIN_N={GN._MIN_N}"


def test_post_reference_cells_are_untouched_by_the_floor():
    """The floor is scoped to cells BELOW the reference's first year."""
    for year in (RF + 2, RF + 6):
        a, _pa, _na = _offset(SRC, "hitter", year, None)
        b, _pb, _nb = _offset(SRC, "hitter", year, 2026)
        if a is None or b is None:
            pytest.skip(f"no {year} cell in this corpus")
        assert abs(a - b) < 1e-9, (
            f"{year} moved ({a} vs {b}); the era floor must only reach cells "
            f"earlier than {RF}")


def test_the_served_flag_is_ON_and_the_floor_is_therefore_live():
    """RETIRED TRIPWIRE, inverted 2026-08-14 when the flip landed.

    This asserted `GRADE_NORM_AS_OF is False` while the mechanism waited for its
    flip. It has now happened, together with the other remapper call sites, the
    fingerprint term that lets the movement engine see it, and the rebuild.

    It is inverted rather than deleted, and asserts the CONSEQUENCE rather than the
    flag, because a pin on the flag alone would have gone green again the moment
    someone set it back to True without the era floor being reachable. That exact
    shape of false green is what C4_REACHABILITY_DEFECT.md records: the floor was
    built, tested and unreachable for three days.
    """
    import consensus
    assert consensus.GRADE_NORM_AS_OF is True

    # and the floor must actually FIRE: a pre-reference cell under the cap must
    # pool strictly fewer pairs than the uncapped one, or the flip is a no-op
    yr = GN._REFERENCE_FIRST_YEAR - 4
    capped, _r, _p = GN._paired_dists("mlb_pipeline", "hitter", yr,
                                      GN._REFERENCE_FIRST_YEAR)
    uncapped, _r2, _p2 = GN._paired_dists("mlb_pipeline", "hitter", yr, None)
    assert len(capped) and len(uncapped), "no pairs at all; corpus changed"
    assert len(capped) < len(uncapped), (
        "the pre-reference cell pools the same set capped as uncapped, so the era "
        "floor is not firing and the flip is a silent no-op")
