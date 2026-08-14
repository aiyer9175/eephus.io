# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Phase 8 (Tier 2) -- cross-source grade normalization.

Different outlets grade on scales that do not line up with FanGraphs FV. Rather
than assume any equivalence, we DISTRIBUTION-MATCH each source's grade
distribution onto the FanGraphs FV distribution, per role, per ranking cycle
(year) -- the same quantile-mapping the FanGraphs methodology post used to make
old Baseball America ordinals comparable to modern FVs. A source grade at
quantile q of its own distribution is remapped to the FanGraphs FV at quantile q.

Raw and normalized grades are kept side by side; a normalized consensus is the
mean of the normalized per-source grades (so a hot or cold grader is de-biased by
the shape of its whole distribution, not just a single offset). Drift tables
report, per source per cycle, how far the mapping moves the scale, flagging
sources with material drift.

ADOPTED (2026-07): the LIVE consensus is now the normalized scale. build_remapper()
precomputes the mapping once and consensus.build_timeseries applies it per source
BEFORE aggregation (preserving every consensus discipline: source weights, the
single-source FV-35 pull, dropped-off shrinkage, rank-implied fallback, forward-
fill, candlesticks) -- gated by consensus.ADOPT_NORMALIZED_CONSENSUS. The per-
source published grades on the card are untouched; only the consensus scale moves.
Still reproducible and diff-able (normalized_consensus below is the analysis view).

No fabricated grades: a (source, role, cycle) cell below `min_n` falls back to the
source's pooled all-year distribution (flagged), and a cell with no FanGraphs
reference is skipped.

AS-OF (2026-08-09)
------------------
That pooled fallback reads the FUTURE. `_paired_dists` pools a thin cell across
ALL years for the role, so the 2021 mapping was estimated partly off 2024 to 2026
pairs, and `build_remapper` inherited it. Measured on the 2026-08-09 DB: 3,577 of
14,788 normalized (source, player, role, year) units, 24.19%, are served by a
pooled cell. Only 99 of them are actually contaminated in the 2017+ window, since
every (source, role, year) cell from 2017 on already clears n_pair >= 30 EXCEPT
mlb_pipeline_international hitter 2021 (18), 2022 (19) and 2023 (28), plus that
list's pitcher cells, which are so thin (1 to 4 pairs) that even the all-year pool
misses min_n and they already fall to the mlb_pipeline alias cell.

`as_of_year` (threaded through _pairs, _paired_dists, build_remapper and the three
analysis views) caps every cell at min(cell_year, as_of_year), so a cell can never
pool a cycle that had not happened yet. Default None reproduces the pre-2026-08-09
behaviour exactly. Effect of turning it on, in FV: +6.9875 on the 25
mlb_pipeline_international hitter 2021 units (that cell loses its own pool and drops
to the mlb_pipeline alias cell), +1.3692 on the 40 in 2022, +0.7912 on the 34 in 2023.

THE AS-OF VIEW IS YEAR GRANULAR: it does not remove within-cycle pooling, and the
size of what it leaves behind is measured, not hand-waved. On the 2026-08-09 DB,
10,361 of 30,911 (source, player, year) groups carrying an FV (33.52%) hold more
than one dated snapshot, so a February point is still normalized against a cell
built from that cycle's LATEST grades, December included. The bound is small but
not zero: the grade itself moves inside the cycle on 789 of those 10,361 groups
(7.62%; mean |last - first| 0.4338 FV, max 15.0), and refitting every min_n-clearing
cell from each source's FIRST dated grade instead of its latest moves the offset on
32 of 39 cells, mean 0.2760 FV, max 1.9118 FV (espn pitcher 2025, +2.3529 ->
+0.4412). Closing that needs a DATE-granular cap, which is its own lane.

PRE-2017 IS DELIBERATELY NOT FIXED. FanGraphs, the REFERENCE scale, has no row
before 2017-02-15, so the 3,478 mlb_pipeline units in 2011 through 2016 have
n_pair = 0 and there is no as-of reference to pool against AT ALL. A strict as-of
would drop their offset entirely: +3.89 to +3.91 FV on all 3,478, a much larger
basis move than the leak it repairs, so cells earlier than _REFERENCE_FIRST_YEAR
keep today's all-year pooling. Correcting them is its own gated lane, not a side
effect of this one.

THAT EXEMPTION MEANS as_of_year IS NOT A CORPUS TRUNCATION, SO A CUTOFF BELOW
_REFERENCE_FIRST_YEAR NOW RAISES (2026-08-09b). Measured on the 2026-08-09 DB by
building the table at as_of_year=2013: ALL 120 of the 2017+ cells empty (cap 2013,
no reference row at or before 2016) and fall to raw, while 66 pre-2017 cells
survive on their uncapped pools, and those pools are 100% LATER than the cutoff -
mlb_pipeline hitter 2013 is estimated off 3,982 pairs, every one from 2017 through
2026, i.e. 4 to 13 years after it, and the pitcher cell off 3,325 the same way. A
pre-reference cutoff therefore INVERTS the intent: the only cells that keep an
offset are the ones whose offset is entirely future, a strictly worse leak than
the 99-unit one the cap closes. A docstring caveat is skippable and an exception
is not, so this is a ValueError rather than a documented footgun. The 3,478
pre-2017 SERVED units (all mlb_pipeline; the other pre-2017 cells exist in the
table but no player is graded by those sources that early) keep the uncapped pool
at any LEGAL cutoff. That is the exemption, unchanged.

A cell LATER than the cutoff is NOT dropped, it CARRIES FORWARD. cap =
min(cell_year, as_of_year) leaves it no own-year pairs, and the thin-cell fallback
then pools every cycle at or before the cutoff. Measured: build_remapper(
as_of_year=2019) maps remap(50, mlb_pipeline, SS, 2026) to 45.7388 off a 1,076-pair
2017-2019 pool, against 46.4069 under the uncapped table and 50.0 raw. Carry-forward
is the right as-of answer (it is the last mapping a 2019 observer could have fitted,
where raw would reinstate a known ~+4 FV bias), and it never fires in production:
consensus passes the newest year in the corpus, so no cell is later than the cutoff.
"""
from __future__ import annotations

import functools
import sqlite3
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_DB = _HERE / "prospects.db"

REFERENCE = "fangraphs"          # the scale everything is mapped onto
_MIN_N = 30                      # below this, pool the source across years (flagged)
# First year the REFERENCE exists: min(snapshot_date) for fangraphs is 2017-02-15
# (24,503 rows, 24,501 with an FV). Earlier cells have n_pair = 0 and no as-of
# reference at all, so they are exempt from the as-of cap. See the module docstring.
_REFERENCE_FIRST_YEAR = 2017
_MATERIAL_DRIFT_FV = 2.0         # |median shift| >= this FV is "material"
_PITCHER_TOKENS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP", "CL", "P"}

# Internal synthetic anchors, not outlets with a grading scale. performance_ingest
# hands EVERY auto-tracked player the same provisional FV 35 floor, so its "grade
# distribution" is a constant: quantile-matching it against the (selection-biased)
# overlap of players who later earned real grades maps that floor onto the overlap's
# FanGraphs tail -- the 2026 pitcher cell sent 35 -> 45 for 2,525 unlisted arms and
# manufactured board top-100 pitchers out of complex-league statlines. Synthetic
# sources pass through RAW, always.
_SYNTHETIC_SOURCES = {"performance_ingest", "draft_signing"}


def _mappable(src, ref) -> bool:
    """A quantile map needs rank information on BOTH sides. A constant paired
    distribution has no quantiles to match: every input collapses to one point of
    the other side's distribution, which fabricates grades ("no fabricated grades"
    is this module's contract). Degenerate cells fall back to the raw scale."""
    return len(np.unique(src)) >= 2 and len(np.unique(ref)) >= 2


def _is_pitcher(position: str | None) -> bool:
    if not position:
        return False
    return any(tok in _PITCHER_TOKENS for tok in str(position).upper().split("/"))


@functools.lru_cache(maxsize=1)
def _all_latest() -> dict:
    """{(role, year): {player_key: {source: fv}}} -- each source's latest FV for a
    player in a cycle. The building block for PAIRED (overlap) distributions."""
    if not _DB.exists():
        return {}
    con = sqlite3.connect(str(_DB))
    try:
        rows = con.execute(
            "SELECT source, player_key, position, snapshot_date, fv FROM snapshots "
            "WHERE fv IS NOT NULL").fetchall()
    finally:
        con.close()
    # (role, year, player, source) -> (date, fv), keep latest
    tmp: dict = {}
    for src, pk, pos, date, fv in rows:
        if not src or not pk or not date:
            continue
        try:
            yr = int(str(date)[:4]); fvf = float(fv)
        except (TypeError, ValueError):
            continue
        role = "pitcher" if _is_pitcher(pos) else "hitter"
        k = (role, yr, pk, src)
        if k not in tmp or date > tmp[k][0]:
            tmp[k] = (date, fvf)
    out: dict = {}
    for (role, yr, pk, src), (_d, fvf) in tmp.items():
        out.setdefault((role, yr), {}).setdefault(pk, {})[src] = fvf
    return out


def _pairs(source: str, role: str, year: int,
           as_of_year: int | None = None) -> list[tuple[float, float]]:
    """(source_fv, reference_fv) for players graded by BOTH the source and the
    reference in a (role, year) cycle -- the overlap that controls for coverage.

    `as_of_year` is the knowledge cutoff: a cycle later than the cutoff had not
    been published yet, so it contributes nothing. None = every cycle (default)."""
    if as_of_year is not None and year > as_of_year:
        return []
    m = _all_latest().get((role, year), {})
    return [(d[source], d[REFERENCE]) for d in m.values()
            if source in d and REFERENCE in d]


@functools.lru_cache(maxsize=256)
def _paired_dists(source: str, role: str, year: int,
                  as_of_year: int | None = None) -> tuple:
    """(source_sorted, reference_sorted, pooled_flag) over the SAME players. When
    the cycle overlap is thinner than min_n, pool the overlap across all years for
    that source and role (flagged). Comparing a source to FanGraphs on the same
    players separates a genuine scale bias from a coverage difference (a top-only
    source is not treated as 'hot' just because it skips the low tiers).

    `as_of_year` bounds that pool to cycles <= the cutoff. Without it the pool
    reads the future: measured 2026-08-09, the mlb_pipeline_international hitter
    2021 cell (n_pair 18) was estimated off 182 pooled pairs that run through 2026.
    None (default) keeps the all-year pool, i.e. the pre-2026-08-09 behaviour."""
    pairs = _pairs(source, role, year, as_of_year)
    pooled = False
    if len(pairs) < _MIN_N:
        # ERA FLOOR (2026-08-13, docs/efv-2026-08-13/C4_ERA_FLOOR_MEASUREMENT.md).
        # A cell earlier than _REFERENCE_FIRST_YEAR has NO own-year pairs, because
        # the reference scale does not exist before 2017-02-15, so it falls through
        # to this pool and gets an offset estimated from cycles that are ENTIRELY
        # LATER than the grade being normalized: mlb_pipeline hitter 2013 is built
        # from 3,982 pairs, every one of them 2017 through 2026.
        #
        # Bounding the pool at the reference's FIRST year uses the closest era that
        # can be measured at all, instead of importing a decade of later drift. The
        # offset falls over time (+4.175 in 2017 to +3.269 in 2026, about 7.7 sigma),
        # so the all-year pool systematically understates what a contemporaneous
        # observer would have measured. Measured effect of the floor, 2026-08-13:
        # mlb_pipeline hitter +4.0457 -> +4.2880 (309 pairs) and pitcher +3.7429 ->
        # +4.0603 (282 pairs), both clearing _MIN_N. About a third of an FV on the
        # 3,478 served pre-2017 units, which are all mlb_pipeline; no other source
        # grades players that early, and none of them can form a 2017 cell at all.
        #
        # INERT UNTIL THE AS-OF CAP IS ON. Gated on `as_of_year is not None` so that
        # with consensus.GRADE_NORM_AS_OF False, today's state, this reproduces the
        # previous behaviour cell for cell. The flip is what turns it on, and the
        # flip is a basis change on eFV's dominant feature that needs its own
        # rebuild and margin re-read.
        cap = as_of_year
        if as_of_year is not None and year < _REFERENCE_FIRST_YEAR:
            cap = min(as_of_year, _REFERENCE_FIRST_YEAR)
        allp: list = []
        for (r, y) in list(_all_latest().keys()):
            if r == role and (cap is None or y <= cap):
                allp.extend(_pairs(source, r, y, cap))
        if len(allp) >= _MIN_N:
            pairs, pooled = allp, True
    if not pairs:
        return np.array([]), np.array([]), pooled
    src = np.sort(np.array([p[0] for p in pairs], dtype=float))
    ref = np.sort(np.array([p[1] for p in pairs], dtype=float))
    return src, ref, pooled


def _apply_offset(fv: float, src, ref) -> float:
    """CONTINUOUS per-source scale correction (2026-07-24, docs/EFV_FRONTIER_AUDIT.md).

    REPLACES a discrete quantile map that was a near-IDENTITY in production. The old
    path did `q = np.interp(fv, src, linspace(0,1,len(src)))` on the 5-point FV lattice;
    with ties np.interp resolves to the UPPER edge of each block, and mapping that
    quantile back through an equally-discrete reference returns the input grade. Measured
    live: map(40)=40, map(45)=45, map(55)=55 while MLB Pipeline actually runs +4.367 FV
    points hotter than the FanGraphs reference on the SAME players (SE 0.089, n_pair
    1,864, ~49 sigma). The layer was removing ~0.7% of a real 4-point bias.

    The bias is a pure SCALE offset, not an information difference: the outcome-equivalence
    offsets (+4.45 hit / +4.49 pit) match the raw mean gap, and the WAR-per-FV slopes are
    near-equal (FG 0.4204 vs MP 0.4499). So the correction is a shift, applied continuously.

    A discrete MID-RANK quantile remap was tested and REJECTED: it collapses distinct
    grades (40 and 45 land together, 50 -> 46.25), destroys injectivity, and turns the
    22-block cross-split negative. This offset is strictly order-preserving.

    Clamped to the 20-80 scouting scale. Degenerate cells never reach here (see _mappable)."""
    offset = float(np.mean(src) - np.mean(ref))
    if not np.isfinite(offset):
        return float(fv)
    return float(min(80.0, max(20.0, fv - offset)))


def quantile_map(fv: float, source: str, role: str, year: int,
                 as_of_year: int | None = None) -> float | None:
    """Map a source grade onto the FanGraphs FV scale by matching quantiles on the
    two sources' PAIRED (same-player) distributions. The reference maps to itself.
    None if there is no usable overlap distribution.

    `as_of_year` is threaded so this analysis view reports the SAME scale the live
    consensus is on. It was not, and that was a latent divergence: if
    consensus.GRADE_NORM_AS_OF is ever flipped, an untreaded view would keep
    publishing the uncapped mapping beside a capped board. Default None, so the
    caller opts in exactly as build_remapper's caller does."""
    if fv is None:
        return None
    if source == REFERENCE or source in _SYNTHETIC_SOURCES:
        return float(fv)
    src, ref, _pooled = _paired_dists(source, role, year, as_of_year)
    if len(src) == 0 or len(ref) == 0 or not _mappable(src, ref):
        return None
    return _apply_offset(float(fv), src, ref)


def drift_row(source: str, role: str, year: int,
              as_of_year: int | None = None) -> dict | None:
    """Per (source, role, cycle) drift on the OVERLAP with FanGraphs: the source's
    raw grade median vs the FanGraphs grade median for the same players, and the
    median mapping shift. `material` flags a scale that grades materially hot or
    cold relative to FanGraphs (a genuine scale bias, coverage controlled for).

    `as_of_year` capped for the same reason quantile_map is: the drift table has to
    describe the mapping the board actually applied. Default None."""
    src, ref, pooled = _paired_dists(source, role, year, as_of_year)
    if len(src) == 0:
        return None
    if source == REFERENCE:
        med = float(np.median(src))
        return {"source": source, "role": role, "year": year, "n": int(len(src)),
                "median_raw": round(med, 1), "median_fg_overlap": round(med, 1),
                "median_shift": 0.0, "pooled": pooled, "material": False}
    med_raw = float(np.median(src))         # source's grades on the overlap
    med_fg = float(np.median(ref))          # FanGraphs' grades on the SAME players
    shift = med_fg - med_raw                 # how far the source sits from FanGraphs
    return {"source": source, "role": role, "year": year, "n": int(len(src)),
            "median_raw": round(med_raw, 1), "median_fg_overlap": round(med_fg, 1),
            "median_shift": round(shift, 2), "pooled": pooled,
            "material": abs(shift) >= _MATERIAL_DRIFT_FV}


def _latest_player_grades(year: int) -> dict:
    """{player_key: {"role": role, "sources": {source: fv}}} using each source's
    latest FV for the given cycle year."""
    if not _DB.exists():
        return {}
    con = sqlite3.connect(str(_DB))
    try:
        rows = con.execute(
            "SELECT source, player_key, position, snapshot_date, fv FROM snapshots "
            "WHERE fv IS NOT NULL AND substr(snapshot_date,1,4)=?", (str(year),)).fetchall()
    finally:
        con.close()
    latest: dict = {}
    for src, pk, pos, date, fv in rows:
        if not src or not pk or not date:
            continue
        try:
            fvf = float(fv)
        except (TypeError, ValueError):
            continue
        role = "pitcher" if _is_pitcher(pos) else "hitter"
        rec = latest.setdefault(pk, {"role": role, "sources": {}})
        prev = rec["sources"].get(src)
        if prev is None or date > prev[0]:
            rec["sources"][src] = (date, fvf)
    return {pk: {"role": rec["role"],
                 "sources": {s: v[1] for s, v in rec["sources"].items()}}
            for pk, rec in latest.items()}


def build_remapper(years: list[int] | None = None, aliases: dict | None = None,
                   as_of_year: int | None = None):
    """Precompute the per-(source, role, cycle) quantile-mapping distributions in a
    SINGLE DB pass and return a PURE closure remap(fv, source, position, year) -> fv
    on the FanGraphs scale. Lets consensus.py ADOPT the normalized consensus without
    importing this module's DB layer per point.

    Contract: the reference source (FanGraphs) maps to itself; a (source, role,
    year) cell with no usable overlap falls back to the RAW fv (never drops the
    source). Role is derived from position with the same pitcher-token rule the
    paired distributions were built under, so a grade is remapped against its own
    role's distribution. Deterministic given the DB contents.

    `aliases` (2026-07-25) mirrors consensus.SOURCE_ALIASES: {alias -> canonical}.
    An outlet that publishes several lists is ONE editorial voice for consensus
    purposes, but its lists are not always ONE SCALE. MLB Pipeline's International
    Top 50 grades the same player, in the same week, +7.279 FV [+6.438, +8.075]
    hotter than that outlet's own main lists (n 147 player-cycles, 6 of 6 cycles
    positive), while every OTHER pair of co-published Pipeline lists agrees to
    0.035 FV mean absolute on 1,564 same-date rows. So a list gets its own cell
    when one is measurable, and falls back to its canonical outlet's cell (NOT to
    the raw scale) when it does not. Passing aliases=None keeps the old behaviour.

    `as_of_year` (2026-08-09) closes the pooled-fallback leak: each cell is built
    at cap = min(cell_year, as_of_year), so the 2021 mapping cannot be estimated
    off 2024-2026 pairs. None (default) is today's behaviour, cell for cell.

    IT IS NOT A CORPUS TRUNCATION, because cells earlier than _REFERENCE_FIRST_YEAR
    are EXEMPT and keep the all-year pool (the reference does not exist before
    2017-02-15, and a strict cap would silently drop the offset on 3,478
    mlb_pipeline units, +3.89 to +3.91 FV each). Two consequences, both measured on
    the 2026-08-09 DB and both spelled out because the earlier wording promised a
    backtest view this argument does not deliver:

      * as_of_year < _REFERENCE_FIRST_YEAR RAISES. At as_of_year=2013 all 120 of the
        2017+ cells emptied and fell to raw while 66 exempt pre-2017 cells survived
        on pools that are 100% later than the cutoff (mlb_pipeline hitter 2013: 3,982
        pairs, all 2017-2026), so the only surviving offsets would be entirely
        future. See the module docstring.
      * a cell LATER than the cutoff CARRIES FORWARD rather than dropping to raw:
        it has no own-year pairs under the cap, so the thin-cell fallback pools
        every cycle at or before the cutoff. build_remapper(as_of_year=2019) maps
        remap(50, mlb_pipeline, SS, 2026) to 45.7388 off a 1,076-pair 2017-2019
        pool (uncapped table 46.4069, raw 50.0). Intended: that is the newest
        mapping the cutoff could have fitted. It cannot fire in production, where
        consensus passes the newest year in the corpus."""
    if as_of_year is not None and as_of_year < _REFERENCE_FIRST_YEAR:
        raise ValueError(
            f"as_of_year={as_of_year} is before _REFERENCE_FIRST_YEAR="
            f"{_REFERENCE_FIRST_YEAR}: the pre-reference exemption would serve those "
            "cells a pool that is 100% LATER than the cutoff (3,982 pairs, all "
            "2017-2026, for mlb_pipeline hitter 2013) while every 2017+ cell fell "
            "to raw. Cap at _REFERENCE_FIRST_YEAR or later.")
    latest = _all_latest()
    sources: set[str] = set()
    for players in latest.values():
        for d in players.values():
            sources.update(d.keys())
    table: dict = {}
    for (role, yr) in list(latest.keys()):
        if years is not None and yr not in years:
            continue
        # PRE-REFERENCE CELLS GET THE ERA FLOOR, not the exemption (changed
        # 2026-08-14). The exemption that stood here was correct WHEN IT WAS
        # WRITTEN, and its own reasoning is what dates it: capping a pre-2017 cell
        # used to remove the only pool it had, because the reference scale has no
        # row before 2017-02-15 and there are no own-year pairs to fall back on.
        #
        # The era floor landed 2026-08-13 inside _paired_dists precisely to make
        # capping those cells safe, by pooling the EARLIEST year the reference
        # exists instead of dropping to nothing. But it is gated on
        # `as_of_year is not None`, and this branch handed it None for exactly the
        # cells it was built for, so it could never fire. Flipping
        # consensus.GRADE_NORM_AS_OF alone would therefore have shipped a silent
        # no-op: all 3,478 pre-2017 served units would not have moved, the margin
        # re-read would have shown nothing, and that would have been recorded as
        # "the era floor is small" when the truth is "the era floor did not run".
        #
        # Measured, mlb_pipeline hitter, live corpus:
        #   2013  cap None -> n 4,062 offset +4.0645   (the leak: pooled 2017-2026)
        #   2013  cap set  -> n   309 offset +4.2880   (own-era, matches the
        #                                               2026-08-13 measurement)
        # Post-reference cells are byte-identical either way (2019: 395/+4.1519).
        cap = None
        if as_of_year is not None:
            cap = (min(yr, as_of_year) if yr >= _REFERENCE_FIRST_YEAR
                   else _REFERENCE_FIRST_YEAR)
        for src in sources:
            if src == REFERENCE or src in _SYNTHETIC_SOURCES:
                continue
            s_sorted, r_sorted, _pooled = _paired_dists(src, role, yr, cap)
            if not (len(s_sorted) and len(r_sorted) and _mappable(s_sorted, r_sorted)):
                continue
            if len(s_sorted) < _MIN_N:
                # _paired_dists pools a thin cycle across years, but when the POOLED
                # overlap is ALSO under min_n it hands back the thin cell anyway. An
                # offset estimated off a handful of players is not a measurement, and
                # the module's contract is "no fabricated grades". Drop the cell and
                # let the alias / raw fallback below carry the grade instead.
                continue
            table[(src, role, yr)] = (s_sorted, r_sorted)

    alias_map = dict(aliases or {})

    def remap(fv, source, position, year):
        if fv is None:
            return None
        if source == REFERENCE:
            return float(fv)
        try:
            yr = int(year)
        except (TypeError, ValueError):
            return float(fv)
        role = "pitcher" if _is_pitcher(position) else "hitter"
        ent = table.get((source, role, yr))
        if not ent:
            canon = alias_map.get(source)
            if canon and canon != source:
                # This list has no measurable cell of its own: use its outlet's.
                ent = table.get((canon, role, yr))
        if not ent:
            return float(fv)          # no usable overlap -> raw fallback (never drop)
        src, ref = ent
        return _apply_offset(float(fv), src, ref)

    return remap


def normalized_consensus(year: int, min_sources: int = 2,
                         as_of_year: int | None = None) -> dict:
    """Per player in a cycle: the RAW mean of per-source grades vs the mean of
    the NORMALIZED (FanGraphs-scale) grades, and the difference. Deterministic
    and reproducible. Only players with >= min_sources sources are included.

    `as_of_year` passes straight to quantile_map so this diff view and the live
    board can be put on one basis. Default None."""
    players = {}
    for pk, rec in _latest_player_grades(year).items():
        role = rec["role"]
        raws, norms, used = [], [], []
        for src, fv in rec["sources"].items():
            raws.append(fv)
            nm = quantile_map(fv, src, role, year, as_of_year)
            if nm is not None:
                norms.append(nm)
                used.append(src)
        if len(raws) < min_sources or not norms:
            continue
        raw_c = float(np.mean(raws))
        norm_c = float(np.mean(norms))
        players[pk] = {"role": role, "n_sources": len(used), "sources": used,
                       "raw_consensus": round(raw_c, 2),
                       "norm_consensus": round(norm_c, 2),
                       "diff": round(norm_c - raw_c, 2)}
    return players
