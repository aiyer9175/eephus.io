# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""As-of grade normalization (2026-08-09).

`_paired_dists` pools a thin (source, role, year) cell across ALL years for the
role, including years LATER than the cycle being mapped, and `build_remapper`
inherited it. Measured on the 2026-08-09 DB: 3,577 of 14,788 normalized
(source, player, role, year) units (24.19%) are served by a pooled cell, and 99
of them are actually contaminated inside the 2017+ window, all of them
mlb_pipeline_international hitters: 25 in 2021 (+6.9875 FV once the cap drops
that cell to the mlb_pipeline alias), 40 in 2022 (+1.3692) and 34 in 2023
(+0.7912). Every other (source, role, year) cell from 2017 on already clears
n_pair >= 30.

The DB numbers move with the corpus, so they are NOT asserted here. This module
pins the MECHANISM on a synthetic corpus whose arithmetic is exact, plus the two
invariants that must hold whatever the corpus says: as_of_year=None reproduces
today's mapping cell for cell, and the pre-2017 block stays blocked (a strict cap
there would drop the offset on 3,478 mlb_pipeline units, ~+3.9 FV each, which is
a bigger basis move than the leak it repairs).

2026-08-09b adds the three things that block made possible and nothing named:

  * a cutoff below _REFERENCE_FIRST_YEAR RAISES. Before the guard,
    build_remapper(as_of_year=2013) served the exempt 2013 cell off 3,982 pooled
    pairs, 100% of them 2017-2026, while every 2017+ cell emptied and fell to raw.
    A pre-reference cutoff inverts the intent instead of truncating the corpus.
  * a cell LATER than the cutoff CARRIES FORWARD rather than dropping to raw, and
    the test asserts which of the three values it lands on.
  * quantile_map, drift_row and normalized_consensus take the cutoff too, so the
    analysis views cannot describe a different scale than the board.
"""
from __future__ import annotations

import pytest

import consensus
import grade_normalization as gn

# FanGraphs reference grades on the 5-point FV lattice.
_FG = [40.0, 45.0, 50.0, 55.0, 60.0]


def _corpus() -> dict:
    """{(role, year): {player_key: {source: fv}}}, shaped like production.

      2015  mlb_pipeline only, NO FanGraphs row at all (the pre-reference era)
      2017  40 pairs: mlb_pipeline +4, thin_src +2
      2018  40 pairs mlb_pipeline +4; thin_src on 5 of them, pipeline_intl on 3
      2019  40 pairs: mlb_pipeline +4, thin_src +12, pipeline_intl +8

    thin_src 2018 is the leak: its own overlap is 5 pairs, so it pools, and the
    pool it reaches today is dominated by a 2019 cycle that grades +12 instead of
    +2. pipeline_intl 2018 is the alias case: 3 own pairs, and the only thing that
    lifts its pool over min_n is the 2019 cycle.
    """
    out: dict = {}

    def put(year, pk, **grades):
        out.setdefault(("hitter", year), {})[pk] = dict(grades)

    for i in range(40):
        put(2015, f"pre{i}", mlb_pipeline=_FG[i % 5] + 4.0)          # no reference
    for i in range(40):
        fg = _FG[i % 5]
        put(2017, f"a{i}", fangraphs=fg, mlb_pipeline=fg + 4.0, thin_src=fg + 2.0)
    for i in range(40):
        fg = _FG[i % 5]
        g = {"fangraphs": fg, "mlb_pipeline": fg + 4.0}
        if i < 5:
            g["thin_src"] = fg + 2.0
        if i < 3:
            g["mlb_pipeline_international"] = fg + 8.0
        put(2018, f"b{i}", **g)
    for i in range(40):
        fg = _FG[i % 5]
        put(2019, f"c{i}", fangraphs=fg, mlb_pipeline=fg + 4.0,
            thin_src=fg + 12.0, mlb_pipeline_international=fg + 8.0)
    return out


@pytest.fixture
def synthetic(monkeypatch):
    """Swap the DB-backed corpus for the synthetic one. _paired_dists is lru_cached
    and the cache is module-global, so it is cleared on BOTH sides: a synthetic
    entry left behind would be read by the DB-backed tests in this file and in
    test_grade_normalization.py."""
    gn._paired_dists.cache_clear()
    monkeypatch.setattr(gn, "_all_latest", _corpus)
    yield _corpus()
    gn._paired_dists.cache_clear()


def _offset(source, role, year, as_of_year=None):
    """The scale offset the remapper would apply, or None when the cell has no
    usable pairs. _apply_offset subtracts it, so remap(fv) = fv - offset."""
    src, ref, _pooled = gn._paired_dists(source, role, year, as_of_year)
    if len(src) == 0:
        return None
    return float(src.mean() - ref.mean())


# ---------------------------------------------------------------------------
# 1. a thin cell must not reach into a later cycle
# ---------------------------------------------------------------------------
def test_thin_cell_pools_no_pair_from_a_later_year(synthetic):
    # own overlap is 5 pairs, under _MIN_N = 30, so the cell pools either way.
    assert len(gn._pairs("thin_src", "hitter", 2018)) == 5
    all_src, _all_ref, all_pooled = gn._paired_dists("thin_src", "hitter", 2018)
    asof_src, _asof_ref, asof_pooled = gn._paired_dists("thin_src", "hitter", 2018, 2018)
    assert all_pooled and asof_pooled
    # 2017 (40) + 2018 (5) + 2019 (40) = 85 today; the cap removes exactly 2019.
    assert len(all_src) == 85
    assert len(asof_src) == 45
    # and the 2019 grades themselves are gone, not merely outnumbered: the 2019
    # cycle is the only place thin_src grades +12, i.e. FV 52 through 72.
    assert max(asof_src) == 62.0            # 60 + 2, the 2017/2018 scale
    assert max(all_src) == 72.0             # 60 + 12, the 2019 scale


# ---------------------------------------------------------------------------
# 2. the offset moves by the computed amount, not by an unpinned amount
# ---------------------------------------------------------------------------
def test_asof_offset_differs_by_the_measured_amount(synthetic):
    # today: (40 pairs at +2) + (5 at +2) + (40 at +12) over 85 = 570/85
    off_all = _offset("thin_src", "hitter", 2018)
    off_asof = _offset("thin_src", "hitter", 2018, 2018)
    assert off_all == pytest.approx(570.0 / 85.0, abs=1e-9)      # 6.7058823...
    assert off_asof == pytest.approx(2.0, abs=1e-9)
    # the mapped grade rises by the difference (remap subtracts the offset)
    remap_all = gn.build_remapper()
    remap_asof = gn.build_remapper(as_of_year=2019)
    got_all = remap_all(50.0, "thin_src", "SS", 2018)
    got_asof = remap_asof(50.0, "thin_src", "SS", 2018)
    assert got_all == pytest.approx(50.0 - 570.0 / 85.0, abs=1e-9)
    assert got_asof == pytest.approx(48.0, abs=1e-9)
    assert got_asof - got_all == pytest.approx(570.0 / 85.0 - 2.0, abs=1e-9)  # +4.70588
    # cells that already clear min_n on their own overlap do NOT move.
    for yr in (2017, 2019):
        assert remap_asof(50.0, "thin_src", "SS", yr) == pytest.approx(
            remap_all(50.0, "thin_src", "SS", yr), abs=1e-12)


def test_thin_intl_cell_drops_to_the_alias_and_the_fallback_is_asserted(synthetic):
    # Production shape: mlb_pipeline_international 2021 has 18 own pairs and only
    # clears min_n by pooling 2022-2026, so the cap deletes the cell and the grade
    # falls to the canonical outlet's cell (+6.9875 FV on 25 IFA hitters).
    aliases = {"mlb_pipeline_international": "mlb_pipeline"}
    remap_all = gn.build_remapper(aliases=aliases)
    remap_asof = gn.build_remapper(aliases=aliases, as_of_year=2019)
    # own cell today: 3 (2018) + 40 (2019) = 43 pooled pairs, all at +8
    assert len(gn._paired_dists("mlb_pipeline_international", "hitter", 2018)[0]) == 43
    assert remap_all(50.0, "mlb_pipeline_international", "SS", 2018) == pytest.approx(42.0)
    # capped: 3 pairs, under min_n even after pooling, so build_remapper drops the
    # cell. Assert WHICH fallback fired: the mlb_pipeline alias cell (offset +4),
    # not the raw scale (which would be 50.0 and would silently look "fixed").
    assert len(gn._paired_dists("mlb_pipeline_international", "hitter", 2018, 2018)[0]) == 3
    got = remap_asof(50.0, "mlb_pipeline_international", "SS", 2018)
    assert got == pytest.approx(46.0, abs=1e-9)
    assert got == pytest.approx(remap_asof(50.0, "mlb_pipeline", "SS", 2018), abs=1e-12)
    assert got != 50.0
    # without an alias map the same cell falls to RAW, and that is asserted too.
    assert gn.build_remapper(as_of_year=2019)(
        50.0, "mlb_pipeline_international", "SS", 2018) == 50.0


# ---------------------------------------------------------------------------
# 3. pre-2017 stays blocked
# ---------------------------------------------------------------------------
def test_pre_reference_cells_are_exempt_from_the_cap(synthetic):
    remap_all = gn.build_remapper()
    remap_asof = gn.build_remapper(as_of_year=2019)
    # A strict cap WOULD strip the offset: there is no reference row in or before
    # 2015, so the capped pool is empty and the grade would pass through raw.
    assert _offset("mlb_pipeline", "hitter", 2015, 2015) is None
    assert len(gn._pairs("mlb_pipeline", "hitter", 2015)) == 0
    # The exemption keeps the all-year pool, so nothing moves. On the real corpus
    # this is 3,478 mlb_pipeline units that would otherwise jump ~+3.9 FV.
    assert _offset("mlb_pipeline", "hitter", 2015) == pytest.approx(4.0, abs=1e-9)
    assert remap_asof(50.0, "mlb_pipeline", "SS", 2015) == pytest.approx(46.0, abs=1e-9)
    assert remap_asof(50.0, "mlb_pipeline", "SS", 2015) == pytest.approx(
        remap_all(50.0, "mlb_pipeline", "SS", 2015), abs=1e-12)
    assert gn._REFERENCE_FIRST_YEAR == 2017


def test_a_pre_reference_cutoff_raises_instead_of_leaking(synthetic):
    """The exemption makes as_of_year NOT a corpus truncation, so a cutoff below the
    first reference year is refused rather than silently served.

    Measured on the 2026-08-09 DB before the guard, at as_of_year=2013: ALL 120 of the
    2017+ cells emptied and fell to raw, while 66 exempt pre-2017 cells survived on
    pools that are 100% later than the cutoff (mlb_pipeline hitter 2013: 3,982 pairs,
    every one 2017-2026). The only surviving offsets would have been entirely future,
    which is a worse leak than the one the cap closes. The synthetic corpus shows the
    same shape: the 2015 cell is exempt and keeps its pool while 2017+ empties.
    """
    for bad in (2011, 2013, 2016):
        with pytest.raises(ValueError) as exc:
            gn.build_remapper(as_of_year=bad)
        assert "_REFERENCE_FIRST_YEAR" in str(exc.value)
    # the first legal cutoff is the reference year itself, and it builds.
    assert gn.build_remapper(as_of_year=gn._REFERENCE_FIRST_YEAR) is not None
    # _paired_dists is NOT guarded: it is the primitive the strict-cap counterfactual
    # above probes, and guarding it would delete that measurement.
    assert _offset("mlb_pipeline", "hitter", 2015, 2015) is None


def test_a_cell_later_than_the_cutoff_carries_forward_and_does_not_drop_to_raw(synthetic):
    """cap = min(cell_year, as_of_year) leaves a later cell no own-year pairs, so the
    thin-cell fallback pools every cycle at or before the cutoff. That is carry-forward,
    not a drop to raw, and the difference is asserted three ways.

    thin_src grades +2 in 2017/2018 and +12 in 2019. Cut at 2018, the 2019 cell is
    served by the 2017+2018 pool (45 pairs, offset 2.0). On the real corpus the same
    mechanism gives build_remapper(as_of_year=2019) remap(50, mlb_pipeline, SS, 2026)
    = 45.7388 off a 1,076-pair 2017-2019 pool, against 46.4069 uncapped and 50.0 raw.
    """
    remap_all = gn.build_remapper()
    remap_cf = gn.build_remapper(as_of_year=2018)
    assert len(gn._pairs("thin_src", "hitter", 2019, 2018)) == 0     # nothing of its own
    src, _ref, pooled = gn._paired_dists("thin_src", "hitter", 2019, 2018)
    assert pooled and len(src) == 45                                 # 40 (2017) + 5 (2018)
    assert remap_cf(50.0, "thin_src", "SS", 2019) == pytest.approx(48.0, abs=1e-9)
    assert remap_all(50.0, "thin_src", "SS", 2019) == pytest.approx(38.0, abs=1e-9)
    assert remap_cf(50.0, "thin_src", "SS", 2019) != 50.0            # NOT the raw scale
    # It cannot fire in production: consensus passes the newest year in the corpus, so
    # no cell is ever later than the cutoff.
    newest = max(y for (_r, y) in gn._all_latest())
    assert remap_all(50.0, "thin_src", "SS", 2019) == pytest.approx(
        gn.build_remapper(as_of_year=newest)(50.0, "thin_src", "SS", 2019), abs=1e-12)


# ---------------------------------------------------------------------------
# 4. the default is inert
# ---------------------------------------------------------------------------
def test_as_of_year_none_is_identical_to_todays_behaviour(synthetic):
    base = gn.build_remapper(aliases=consensus.SOURCE_ALIASES)
    explicit_none = gn.build_remapper(aliases=consensus.SOURCE_ALIASES, as_of_year=None)
    capped = gn.build_remapper(aliases=consensus.SOURCE_ALIASES, as_of_year=2019)
    grid = [(fv, src, yr)
            for fv in (30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0)
            for src in ("mlb_pipeline", "mlb_pipeline_international", "thin_src",
                        "fangraphs", "performance_ingest", "no_such_source")
            for yr in (2015, 2017, 2018, 2019, 2020)]
    moved: dict = {}
    for fv, src, yr in grid:
        a = base(fv, src, "SS", yr)
        assert explicit_none(fv, src, "SS", yr) == a          # exact, not approx
        if capped(fv, src, "SS", yr) != a:
            moved[(src, yr)] = moved.get((src, yr), 0) + 1
    # Non-vacuous, and the moved set is pinned rather than counted: thin_src 2018
    # is the thin-cell leak, and both pipeline_intl cells only ever cleared min_n
    # by borrowing the 2019 cycle. 9 grades on the probe lattice each.
    assert moved == {("thin_src", 2018): 9,
                     ("mlb_pipeline_international", 2017): 9,
                     ("mlb_pipeline_international", 2018): 9}

    # _pairs and _paired_dists carry the same guarantee.
    for yr in (2015, 2017, 2018, 2019):
        assert gn._pairs("thin_src", "hitter", yr) == gn._pairs("thin_src", "hitter", yr, None)
        a_src, a_ref, a_p = gn._paired_dists("thin_src", "hitter", yr)
        b_src, b_ref, b_p = gn._paired_dists("thin_src", "hitter", yr, None)
        assert list(a_src) == list(b_src) and list(a_ref) == list(b_ref) and a_p == b_p
    # and so do the three analysis views.
    for yr in (2015, 2017, 2018, 2019):
        assert gn.quantile_map(50.0, "thin_src", "hitter", yr) == \
            gn.quantile_map(50.0, "thin_src", "hitter", yr, None)
        assert gn.drift_row("thin_src", "hitter", yr) == \
            gn.drift_row("thin_src", "hitter", yr, None)


# ---------------------------------------------------------------------------
# 4b. the analysis views are on the SAME basis as the live consensus
# ---------------------------------------------------------------------------
def test_the_analysis_views_take_the_same_cutoff_the_board_does(synthetic, monkeypatch):
    """quantile_map, drift_row and normalized_consensus used to ignore as_of_year, so if
    consensus.GRADE_NORM_AS_OF were flipped the drift table and the normalized_consensus
    diff would have reported a DIFFERENT SCALE than the board they describe. Pinned on
    the thin_src 2018 cell, whose two bases differ by 570/85 - 2 = 4.70588 FV."""
    remap = gn.build_remapper(as_of_year=2018)
    assert gn.quantile_map(50.0, "thin_src", "hitter", 2018, 2018) == pytest.approx(48.0)
    assert gn.quantile_map(50.0, "thin_src", "hitter", 2018, 2018) == pytest.approx(
        remap(50.0, "thin_src", "SS", 2018), abs=1e-12)
    assert gn.quantile_map(50.0, "thin_src", "hitter", 2018) == pytest.approx(
        50.0 - 570.0 / 85.0, abs=1e-9)

    # drift_row reports the pool it actually used, so its n moves with the cutoff.
    assert gn.drift_row("thin_src", "hitter", 2018)["n"] == 85
    assert gn.drift_row("thin_src", "hitter", 2018, 2018)["n"] == 45

    # normalized_consensus threads it straight through to quantile_map. Its grade source
    # is a separate DB query, stubbed here so the arithmetic stays exact.
    monkeypatch.setattr(gn, "_latest_player_grades",
                        lambda year: {"x": {"role": "hitter", "sources": {"thin_src": 50.0}}})
    capped = gn.normalized_consensus(2018, min_sources=1, as_of_year=2018)
    uncapped = gn.normalized_consensus(2018, min_sources=1)
    assert capped["x"]["norm_consensus"] == pytest.approx(48.0)
    assert uncapped["x"]["norm_consensus"] == pytest.approx(round(50.0 - 570.0 / 85.0, 2))
    assert capped["x"]["raw_consensus"] == uncapped["x"]["raw_consensus"] == 50.0


# ---------------------------------------------------------------------------
# 5. the consensus wiring, which is where a basis change would escape
# ---------------------------------------------------------------------------
def test_consensus_defaults_to_no_cap_and_passes_the_corpus_year_when_flipped(monkeypatch):
    # OFF by default: enabling it moves consensus_fv_raw, which is eFV's dominant
    # feature AND its baseline. Measured 2026-08-09 over the 98 affected players:
    # 183 of 1,401 historical points move (mean +1.3407 FV), the served latest
    # point moves for 11 players (mean +0.8927 FV) and 6 displayed grades flip.
    assert consensus.GRADE_NORM_AS_OF is False

    from scrapers import Snapshot
    seen: list = []

    def spy(aliases=None, years=None, as_of_year=None):
        seen.append(as_of_year)
        return lambda fv, source, position, year: fv      # identity remapper

    monkeypatch.setattr(gn, "build_remapper", spy)
    snaps = [
        Snapshot(source="fangraphs", snapshot_date="2019-04-01", interval_label="2019",
                 player_key="x", player_name="X", position="SS", org="LAD", rank=None,
                 fv=55.0, status="active", tools=None),
        Snapshot(source="mlb_pipeline", snapshot_date="2024-04-01", interval_label="2024",
                 player_key="x", player_name="X", position="SS", org="LAD", rank=None,
                 fv=50.0, status="active", tools=None),
    ]
    consensus.build_timeseries(snaps, normalize=True)
    assert seen == [None]

    monkeypatch.setattr(consensus, "GRADE_NORM_AS_OF", True)
    consensus.build_timeseries(snaps, normalize=True)
    # newest snapshot year in the pool, so every cell caps at its own year. Taken
    # from the data and never from the clock, so a rebuild is reproducible.
    assert seen == [None, 2024]


# ---------------------------------------------------------------------------
# 6. the same two invariants against the REAL corpus
# ---------------------------------------------------------------------------
def test_real_corpus_default_is_inert_and_pre_2017_is_untouched():
    if not gn._all_latest():
        pytest.skip("prospects.db not present")
    gn._paired_dists.cache_clear()
    base = gn.build_remapper(aliases=consensus.SOURCE_ALIASES)
    explicit_none = gn.build_remapper(aliases=consensus.SOURCE_ALIASES, as_of_year=None)
    # 2026 is the newest cycle in the corpus, i.e. the pure per-cell as-of table.
    capped = gn.build_remapper(aliases=consensus.SOURCE_ALIASES, as_of_year=2026)
    probes = [(fv, src, pos, yr)
              for fv in (35.0, 45.0, 55.0)
              for src, pos in (("mlb_pipeline", "SS"), ("mlb_pipeline", "RHP"),
                               ("baseballamerica", "SS"), ("espn", "SS"),
                               ("tjstats", "RHP"), ("just_baseball", "SS"))
              for yr in range(2011, 2027)]
    for fv, src, pos, yr in probes:
        assert explicit_none(fv, src, pos, yr) == base(fv, src, pos, yr)
        if yr < gn._REFERENCE_FIRST_YEAR:
            # the pre-reference block: 3,478 mlb_pipeline units, and the cap must
            # not touch a single one of them.
            assert capped(fv, src, pos, yr) == base(fv, src, pos, yr)
    gn._paired_dists.cache_clear()
