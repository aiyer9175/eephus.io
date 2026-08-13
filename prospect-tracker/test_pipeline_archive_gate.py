"""Pins for the MLB Pipeline archive-loop guards (2026-08-14).

Both guards exist because a full audit of every vintage label 2011-2026 found two
distinct defects that the archive loop ingested in silence.
"""
from __future__ import annotations

from datetime import date

import scrapers as S


class _Row:
    def __init__(self, rank, name="Somebody", fv=55.0, org="NYY"):
        self.rank, self.player_name, self.fv, self.org = rank, name, fv, org


def _board(n, start=1):
    return [_Row(i) for i in range(start, start + n)]


def test_archive_gate_rejects_a_short_wrong_list_payload():
    """THE defect. On 2026-06-22 the 2011, 2014 and 2016 Top-100 pages parsed from a
    cache holding the YANKEES ORG BOARD: 10, 20 and 30 rows, ranks 1..N, real names,
    full FV. Internally consistent, so no consistency check can see it. The size floor
    is the only discriminator, and there was no floor at all on this loop."""
    for n, yr in ((10, 2011), (20, 2014), (30, 2016)):
        problems = S.validate_pipeline_archive_board(_board(n), yr)
        assert problems, f"a {n}-row payload was accepted as a Top-100 board"
        assert "floor" in problems[0]


def test_archive_gate_accepts_the_thinnest_legitimate_board():
    """2011 is published as a Top 50 at ~38% FV coverage and 2012 runs ~73% FV with the
    remainder rank-only. The LIVE gate requires 90 rows and 80% FV, so reusing it here
    would refuse two real boards. This pin is why the archive gate is separate."""
    assert not S.validate_pipeline_archive_board(_board(50), 2011)
    low_fv = _board(100)
    for r in low_fv[38:]:
        r.fv = None
    assert not S.validate_pipeline_archive_board(low_fv, 2012), (
        "archive gate rejected a legitimately rank-only board; it must not inherit "
        "the live gate's FV-coverage clause")


def test_archive_gate_still_catches_duplicate_ranks_and_bad_spans():
    dup = _board(100) + [_Row(1)]
    assert any("duplicate ranks" in p for p in S.validate_pipeline_archive_board(dup, 2015))
    off = _board(100, start=7)
    assert any("rank span" in p for p in S.validate_pipeline_archive_board(off, 2015))


def test_archive_intervals_still_cover_every_past_year():
    """The current-year skip must not silently drop the backfill."""
    years = {y for _u, _l, _s, y in S.MLB_PIPELINE_INTERVALS}
    this_year = date.today().year
    for y in range(2011, this_year):
        assert y in years, f"archive interval lost year {y}"


def test_the_current_year_archive_page_is_not_treated_as_archival():
    """/prospects/{y}/top100/ is FROZEN for a past year and the LIVE board for the
    current one. Scraping the current year through the archive loop writes today's
    board under the preseason label with a hardcoded {y}-01-22 date, and because
    insert_snapshots upserts on (source, interval_label, player_key) a newcomer
    INSERTS rather than updates. Measured before the guard: 139 rows for 100 ranks on
    the 2026 Top 100, ten of them players drafted that June, and 1,249 rows against 900
    across the 2026 org boards, while every prior year was clean.

    Pinned as source text: the guard is a `continue`, and there is no cheap way to
    observe a skipped network fetch without performing one."""
    import inspect
    src = inspect.getsource(S.scrape_all)
    assert "if year >= _this_year:" in src, (
        "the archive loop no longer skips the current year; the preseason label will "
        "accrete live-board rows again")
    assert src.index("_this_year = date.today().year") < src.index("if year >= _this_year:")
    assert "validate_pipeline_archive_board(got, year)" in src, (
        "the archive loop lost its health gate; a wrong-list payload would ingest "
        "silently, which is exactly how 2011, 2014 and 2016 were polluted")
