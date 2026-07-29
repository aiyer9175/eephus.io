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


def _pairs(source: str, role: str, year: int) -> list[tuple[float, float]]:
    """(source_fv, reference_fv) for players graded by BOTH the source and the
    reference in a (role, year) cycle -- the overlap that controls for coverage."""
    m = _all_latest().get((role, year), {})
    return [(d[source], d[REFERENCE]) for d in m.values()
            if source in d and REFERENCE in d]


@functools.lru_cache(maxsize=256)
def _paired_dists(source: str, role: str, year: int) -> tuple:
    """(source_sorted, reference_sorted, pooled_flag) over the SAME players. When
    the cycle overlap is thinner than min_n, pool the overlap across all years for
    that source and role (flagged). Comparing a source to FanGraphs on the same
    players separates a genuine scale bias from a coverage difference (a top-only
    source is not treated as 'hot' just because it skips the low tiers)."""
    pairs = _pairs(source, role, year)
    pooled = False
    if len(pairs) < _MIN_N:
        allp: list = []
        for (r, y) in list(_all_latest().keys()):
            if r == role:
                allp.extend(_pairs(source, r, y))
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


def quantile_map(fv: float, source: str, role: str, year: int) -> float | None:
    """Map a source grade onto the FanGraphs FV scale by matching quantiles on the
    two sources' PAIRED (same-player) distributions. The reference maps to itself.
    None if there is no usable overlap distribution."""
    if fv is None:
        return None
    if source == REFERENCE or source in _SYNTHETIC_SOURCES:
        return float(fv)
    src, ref, _pooled = _paired_dists(source, role, year)
    if len(src) == 0 or len(ref) == 0 or not _mappable(src, ref):
        return None
    return _apply_offset(float(fv), src, ref)


def drift_row(source: str, role: str, year: int) -> dict | None:
    """Per (source, role, cycle) drift on the OVERLAP with FanGraphs: the source's
    raw grade median vs the FanGraphs grade median for the same players, and the
    median mapping shift. `material` flags a scale that grades materially hot or
    cold relative to FanGraphs (a genuine scale bias, coverage controlled for)."""
    src, ref, pooled = _paired_dists(source, role, year)
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


def build_remapper(years: list[int] | None = None, aliases: dict | None = None):
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
    the raw scale) when it does not. Passing aliases=None keeps the old behaviour."""
    latest = _all_latest()
    sources: set[str] = set()
    for players in latest.values():
        for d in players.values():
            sources.update(d.keys())
    table: dict = {}
    for (role, yr) in list(latest.keys()):
        if years is not None and yr not in years:
            continue
        for src in sources:
            if src == REFERENCE or src in _SYNTHETIC_SOURCES:
                continue
            s_sorted, r_sorted, _pooled = _paired_dists(src, role, yr)
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


def normalized_consensus(year: int, min_sources: int = 2) -> dict:
    """Per player in a cycle: the RAW mean of per-source grades vs the mean of
    the NORMALIZED (FanGraphs-scale) grades, and the difference. Deterministic
    and reproducible. Only players with >= min_sources sources are included."""
    players = {}
    for pk, rec in _latest_player_grades(year).items():
        role = rec["role"]
        raws, norms, used = [], [], []
        for src, fv in rec["sources"].items():
            raws.append(fv)
            nm = quantile_map(fv, src, role, year)
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
