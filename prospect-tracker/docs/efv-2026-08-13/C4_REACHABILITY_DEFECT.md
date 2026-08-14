# C-4 would have shipped a silent no-op

Found 2026-08-14 while scoping the flip. Verified against the live corpus, read
only. This is NOT in `C4_ERA_FLOOR_MEASUREMENT.md`'s five-step checklist, nor in
the `consensus.py:206-224` call-site list, and it defeats both of them.

## The claim

Flipping `consensus.GRADE_NORM_AS_OF = True`, and threading the cutoff through
every one of the other call sites, changes **nothing at all** for the pre-2017
cells the era floor was built for. The floor is unreachable in production.

## Why

`build_remapper` decides the cap per cell at `grade_normalization.py:403-407`:

    # Pre-reference cells are exempt from the cap (see the docstring): capping
    # them removes the only pool they have instead of removing a leak.
    cap = None
    if as_of_year is not None and yr >= _REFERENCE_FIRST_YEAR:
        cap = min(yr, as_of_year)

For `yr < _REFERENCE_FIRST_YEAR` the cap stays `None`, unconditionally, however
the flag is set. The era floor landed on 2026-08-13 INSIDE `_paired_dists` and is
gated on `as_of_year is not None`. It therefore never sees a non-None value for
exactly the cells it exists to repair.

The exemption was CORRECT when it was written, and it is the comment's own
reasoning that dates it: capping a pre-reference cell used to remove its only pool,
because there are no own-year pairs before FanGraphs starts in 2017. The era floor
is precisely the mechanism that makes capping those cells safe, by pooling the
earliest year the reference exists instead of dropping to nothing. So the guard now
blocks the repair that was built to retire it.

## Measured

`_paired_dists("mlb_pipeline", "hitter", yr, cap)` against the live corpus:

| cell | cap=None (what production passes) | cap=2026 (the floor firing) |
| --- | --- | --- |
| 2013 | n=4,062, offset **+4.0645** | n=309, offset **+4.2880** |
| 2016 | n=4,062, offset +4.0645 | n=309, offset +4.2880 |
| 2019 | n=395, offset +4.1519 | n=395, offset +4.1519 (identical, as designed) |

The cap=2026 column reproduces the 2026-08-13 measurement (+4.2880 on 309 pairs)
exactly, so the floor works. It is simply never called that way.

Note the pre-2017 rows also collapse to ONE pooled cell: 2013 and 2016 return the
identical n and offset, because with no own-year pairs both fall through to the
same all-years pool. That is the leak stated as a number.

## Consequence for the flip

A flip that touches only `GRADE_NORM_AS_OF` and the six construction sites would:

- move the `mlb_pipeline_international` 2021/2022/2023 hitter cells (the in-window
  piece, already documented, small),
- leave all 3,478 pre-2017 served units EXACTLY where they are,
- and produce a rebuild whose margin re-read shows no pre-2017 movement, which
  reads as "the era floor is small" when the truth is "the era floor did not run".

That is a false negative with a written record behind it, which is worse than no
flip at all.

## What the flip actually needs

Either widen the cap at `:405-407` to pass a cutoff for pre-reference cells too and
let `_paired_dists`' floor handle them, or pass `_REFERENCE_FIRST_YEAR` explicitly
for those cells. Either way `test_grade_norm_asof.py:359-362` inverts in the same
commit: it currently asserts the pre-2017 block is untouched by the cap, which is
green today only BECAUSE of this exemption.

Tripwires that must move with it: `test_grade_norm_era_floor.py:101`,
`test_grade_norm_asof.py:312` and `:331`.
