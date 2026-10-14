# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tool-implied production (TIP): the grade-to-stat tables of
docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part 1.2, built by
TL_4_TOOL_LAB_BUILD (PLAN Part 9 section 9.4.2; LANE_C.md section 2.1).

Every table here is a pure function of the rows passed in. Nothing in this module
opens a file, a database or a cache: the caller declares the rows (the gate names
them per use) and the table remembers the ids it was fit on so a scorer can assert
that it never reads a row of its own fit set (Part 1.2 step 2).

The six readers of Part 1.2:

    fit_tables / tip_mat / tip_f3   step 1 and step 3: per-grade-bin medians, bins of
                                    5 points, bins under THIN_N rows dropped as thin,
                                    weighted isotonic smoothing (PAVA, weight = bin n,
                                    oriented by the stat's expected sign), linear
                                    interpolation at each bin's grade_mean, held flat
                                    beyond the first and the last non-thin bin.
    tip_now                         step 6: the maturity table read at a FanGraphs
                                    present grade; never averaged into the future grade.
    tip_level                       step 5, point in time: AAA = MLB plus the
                                    within-player AAA-minus-MLB offset measured on
                                    seasons up to V - 1; below AAA league-relative from
                                    level_norms.compute_level_norms with an explicit
                                    as-of date of December 31 of V - 1, labelled
                                    uncalibrated. Raises when any input season is at or
                                    after V, or is 2026 or later (round 4, leakage 2).
    tip_first                       step 4: a hook on LANE B's aging service
                                    (aging_v3.AgingModel.component_curve, aging="v2",
                                    U3 and U6). It raises ServiceMissing when the service
                                    is not importable or has no model; it never carries a
                                    local aging curve.

No table reads data/tool_grade_tables.json (Part 6), and no function here groups,
filters or weights anything by a future-value grade: the bins are TOOL grade bins
(docs/PROSPECT_ANCHOR_GATE.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: A grade bin with fewer rows than this is THIN and dropped (TOOL_GRADE_TABLES
#: '### 1.3'; gate Part 1.2 step 1 and Part 3.5).
THIN_N = 15
GRADE_MIN = 20
GRADE_MAX = 80
#: TIP_first moves a stat from the arrival age to this age (Part 1.2 step 4).
MATURITY_AGE = 27
#: The first season no point-in-time build may read (round 4, leakage 2).
FIRST_FORBIDDEN_SEASON = 2026

#: Stats whose expected direction with the grade is DOWN (the grade orders the stat
#: non-increasing). Everything else is oriented non-decreasing. A caller may override
#: with `sign` on fit_tables.
LOWER_IS_BETTER = frozenset({"k_pct", "bb_pct_pit", "chase_pct"})

#: Level-context stats: career-row field and the level_norms perf keys per side.
_LEVEL_STAT = {
    "iso": {"field": "iso", "hit": "avg_iso", "pit": None},
    "avg": {"field": "avg", "hit": "avg_avg", "pit": None},
    "k_pct": {"field": "k_pct", "hit": "avg_k_pct", "pit": "avg_pitcher_k_pct"},
    "k_pct_pit": {"field": "k_pct", "hit": None, "pit": "avg_pitcher_k_pct"},
    "bb_pct": {"field": "bb_pct", "hit": "avg_bb_pct", "pit": "avg_pitcher_bb_pct"},
    "bb_pct_pit": {"field": "bb_pct", "hit": None, "pit": "avg_pitcher_bb_pct"},
}
_UNCALIBRATED = "uncalibrated"


class ServiceMissing(RuntimeError):
    """tip_first was called without LANE B's aging service (U6)."""


class TipInputError(ValueError):
    """A point-in-time build was handed a season it may not read."""


def _f(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def bin_of(g) -> int | None:
    """The 5-point tool grade bin, `round(g / 5) * 5`, clipped to [20, 80]."""
    g = _f(g)
    if g is None:
        return None
    return int(min(GRADE_MAX, max(GRADE_MIN, round(g / 5.0) * 5)))


def pava(values, weights, increasing: bool = True) -> list[float]:
    """Weighted pool-adjacent-violators: the isotonic fit of `values` under
    `weights`, non-decreasing when `increasing`, else non-increasing."""
    vals = [float(v) for v in values]
    wts = [float(w) for w in weights]
    if len(vals) != len(wts):
        raise ValueError("values and weights differ in length")
    if not vals:
        return []
    if not increasing:
        vals = [-v for v in vals]
    blocks: list[list[float]] = []      # [mean, weight, count]
    for v, w in zip(vals, wts):
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            m2, w2, c2 = blocks.pop()
            m1, w1, c1 = blocks.pop()
            wt = w1 + w2
            blocks.append([(m1 * w1 + m2 * w2) / wt if wt else (m1 + m2) / 2.0, wt, c1 + c2])
    out: list[float] = []
    for m, _w, c in blocks:
        out.extend([m] * c)
    if not increasing:
        out = [-v for v in out]
    return out


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


@dataclass(frozen=True)
class TipTable:
    """A fitted grade-to-stat table (Part 1.2 step 1). Immutable; a pure function of
    the rows it was fit on, whose ids it keeps for the never-score-your-own-fit-set
    assertion (step 2)."""

    tool: str
    stat: str
    frame: str
    sign: int
    n_rows: int
    n_skipped: int
    bins: tuple            # one dict per bin: bin, n, median, grade_mean, thin, values
    knots: tuple           # grade_mean of each non-thin bin, ascending
    values: tuple          # the PAVA-smoothed medians at the knots
    fit_ids: frozenset
    max_season: int | None
    max_debut_year: int | None

    @property
    def computable(self) -> bool:
        return bool(self.knots)

    def read(self, g) -> float | None:
        """Linear interpolation between the smoothed values at the knots, held flat
        beyond the first and the last non-thin bin. None when no bin survived."""
        g = _f(g)
        if g is None or not self.knots:
            return None
        g = min(GRADE_MAX, max(GRADE_MIN, g))
        ks, vs = self.knots, self.values
        if g <= ks[0]:
            return float(vs[0])
        if g >= ks[-1]:
            return float(vs[-1])
        for i in range(1, len(ks)):
            if g <= ks[i]:
                lo, hi = ks[i - 1], ks[i]
                t = 0.0 if hi == lo else (g - lo) / (hi - lo)
                return float(vs[i - 1] + t * (vs[i] - vs[i - 1]))
        return float(vs[-1])            # unreachable; kept for completeness

    def bin_row(self, g) -> dict | None:
        b = bin_of(g)
        for row in self.bins:
            if row["bin"] == b:
                return row
        return None

    def bin_percentile(self, g, value) -> float | None:
        """The mid-rank percentile of `value` among the fit values in the grade bin of
        `g` (the PIT of Part 2.1; 0.5 is on grade). None in a thin or absent bin."""
        row = self.bin_row(g)
        v = _f(value)
        if row is None or row["thin"] or v is None:
            return None
        xs = row["values"]
        below = sum(1 for x in xs if x < v)
        ties = sum(1 for x in xs if x == v)
        return (below + 0.5 * ties) / len(xs)

    def assert_not_fit_on(self, row_id) -> None:
        if row_id in self.fit_ids:
            raise TipInputError(
                f"table {self.tool}/{self.stat}/{self.frame} would score row {row_id!r} "
                "of its own fit set (gate Part 1.2 step 2)")

    def to_dict(self) -> dict:
        return {
            "tool": self.tool, "stat": self.stat, "frame": self.frame,
            "orientation": "non_increasing" if self.sign < 0 else "non_decreasing",
            "n_rows": self.n_rows, "n_skipped": self.n_skipped,
            "thin_n": THIN_N, "computable": self.computable,
            "bins": [{k: v for k, v in b.items() if k != "values"} for b in self.bins],
            "knots": list(self.knots), "values": list(self.values),
            "max_season": self.max_season, "max_debut_year": self.max_debut_year,
        }


def fit_tables(rows, tool: str, stat: str, frame: str, *, sign: int | None = None,
               thin_n: int = THIN_N) -> TipTable:
    """Fit one TIP table on `rows`: iterables of dicts carrying `grade` (the tool
    grade, unrounded) and `value` (the stat), optionally `id`, `season` and
    `debut_year`. Rows with a missing grade or value are skipped and counted.

    Steps (Part 1.2 step 1): bins of round(g / 5) * 5; per bin n, the median of its
    values (one value per row, unweighted) and grade_mean (the mean unrounded grade);
    bins under `thin_n` dropped as thin; the non-thin medians smoothed by weighted
    isotonic regression (PAVA, weight = n) in the stat's expected direction; read by
    linear interpolation at the knots and flat beyond them. No extrapolation."""
    if sign is None:
        sign = -1 if stat in LOWER_IS_BETTER else 1
    by_bin: dict[int, list[tuple[float, float]]] = {}
    ids = set()
    n_rows = n_skipped = 0
    max_season = None
    max_debut = None
    for r in rows:
        g, v = _f(r.get("grade")), _f(r.get("value"))
        if g is None or v is None:
            n_skipped += 1
            continue
        b = bin_of(g)
        by_bin.setdefault(b, []).append((g, v))
        n_rows += 1
        rid = r.get("id")
        if rid is not None:
            ids.add(rid)
        s = r.get("season")
        if s is not None:
            max_season = int(s) if max_season is None else max(max_season, int(s))
        d = r.get("debut_year")
        if d is not None:
            max_debut = int(d) if max_debut is None else max(max_debut, int(d))
    bins = []
    for b in sorted(by_bin):
        pairs = by_bin[b]
        vals = [v for _g, v in pairs]
        bins.append({
            "bin": b, "n": len(pairs),
            "median": _median(vals),
            "grade_mean": sum(g for g, _v in pairs) / len(pairs),
            "thin": len(pairs) < thin_n,
            "values": tuple(vals),
        })
    kept = [b for b in bins if not b["thin"]]
    kept.sort(key=lambda b: b["grade_mean"])
    knots = tuple(b["grade_mean"] for b in kept)
    smoothed = tuple(pava([b["median"] for b in kept], [b["n"] for b in kept],
                          increasing=(sign > 0)))
    for b, s in zip(kept, smoothed):
        b["smoothed"] = s
    for b in bins:
        b.setdefault("smoothed", None)
    return TipTable(tool=tool, stat=stat, frame=frame, sign=sign, n_rows=n_rows,
                    n_skipped=n_skipped, bins=tuple(bins), knots=knots, values=smoothed,
                    fit_ids=frozenset(ids), max_season=max_season, max_debut_year=max_debut)


def tip_mat(rows, tool: str, stat: str, **kw) -> TipTable:
    """Step 1, the maturity table: the caller passes the MLB age-26-and-over rows
    where the row set supports it, else the full-season rows."""
    return fit_tables(rows, tool, stat, "maturity", **kw)


def tip_f3(rows, tool: str, stat: str, **kw) -> TipTable:
    """Step 3: the table fit on the TAG exposure frame, each row's value pooled over
    the player's first three MLB seasons strictly after his board year."""
    return fit_tables(rows, tool, stat, "f3", **kw)


def tip_now(table: TipTable, present_grade) -> float | None:
    """Step 6: the maturity table read at a FanGraphs present grade
    (snapshots.tools_json._extras.present). Its own input, never averaged into the
    future grade."""
    return table.read(present_grade)


# ---------------------------------------------------------------------------
# step 5: level context, point in time
# ---------------------------------------------------------------------------
def _assert_seasons_before(vintage: int, seasons, what: str) -> None:
    v = int(vintage)
    bad = sorted({int(s) for s in seasons if s is not None
                  and (int(s) >= v or int(s) >= FIRST_FORBIDDEN_SEASON)})
    if bad:
        raise TipInputError(
            f"{what}: seasons {bad} may not enter a build for vintage {v} "
            f"(every input season must be at most {v - 1} and before "
            f"{FIRST_FORBIDDEN_SEASON}; gate Part 1.2 step 5)")


def _row_stat(r: dict, stat: str) -> float | None:
    spec = _LEVEL_STAT[stat]
    v = _f(r.get(spec["field"]))
    if v is None and stat == "iso":
        slg, avg = _f(r.get("slg")), _f(r.get("avg"))
        if slg is not None and avg is not None:
            v = slg - avg
    return v


def _row_exposure(r: dict) -> float:
    for k in ("pa", "ab", "bf", "ip"):
        v = _f(r.get(k))
        if v:
            return v
    return 1.0


def aaa_offset_within_player(career_stats: dict, stat: str, side: str,
                             vintage: int) -> dict:
    """The within-player AAA-minus-MLB offset of `stat` on seasons up to V - 1:
    for every player with both an AAA and an MLB line, his exposure-weighted AAA
    value minus his exposure-weighted MLB value, averaged across players. Never
    data/tool_grade_tables.json's concurrent 2023-onward offset."""
    is_pit = side == "pit"
    diffs = []
    for _pk, rows in (career_stats or {}).items():
        aaa, mlb = [], []
        for r in rows or []:
            if bool(r.get("is_pitcher")) != is_pit:
                continue
            s = r.get("season")
            if s is None:
                continue
            _assert_seasons_before(vintage, [s], "aaa_offset_within_player")
            v = _row_stat(r, stat)
            if v is None:
                continue
            w = _row_exposure(r)
            if r.get("level") == "AAA":
                aaa.append((v, w))
            elif r.get("level") == "MLB":
                mlb.append((v, w))
        if aaa and mlb:
            a = sum(v * w for v, w in aaa) / sum(w for _v, w in aaa)
            m = sum(v * w for v, w in mlb) / sum(w for _v, w in mlb)
            diffs.append(a - m)
    n = len(diffs)
    return {"stat": stat, "side": side, "n_players": n,
            "offset": (sum(diffs) / n) if n else None,
            "through_season": int(vintage) - 1}


def tip_level(table: TipTable, grade, level: str, vintage: int, *, stat: str,
              side: str, career_stats: dict, birth_dates: dict,
              seasons_window: int | None = None) -> dict:
    """Step 5, point in time for an eFV vintage V.

    `table`         the TIP table fit on MLB seasons up to V - 1 of players who
                    debuted before V (its rows carry `season` and `debut_year`, which
                    this function checks).
    `career_stats`  {player_key: [season rows]} with level, season, is_pitcher, the
                    stat fields and an exposure field, ALREADY filtered by the caller
                    to seasons up to V - 1. This function raises on any season at or
                    after V, or 2026 or later: it never filters silently.
    `birth_dates`   {player_key: 'YYYY-MM-DD'} for level_norms.

    At AAA: TIP_MLB plus the within-player AAA-minus-MLB offset measured on the
    rows. Below AAA: TIP_MLB divided by the MLB mean of the stat, times the
    level-season mean from level_norms.compute_level_norms called with an explicit
    as-of date of December 31 of V - 1 (never its default of today), labelled
    uncalibrated."""
    v = int(vintage)
    if stat not in _LEVEL_STAT:
        raise TipInputError(f"no level context is defined for stat {stat!r}")
    if _LEVEL_STAT[stat].get(side) is None:
        raise TipInputError(f"stat {stat!r} has no level context on side {side!r}")
    if table.max_season is not None:
        _assert_seasons_before(v, [table.max_season], "tip_level table rows")
    if table.max_debut_year is not None and table.max_debut_year >= v:
        raise TipInputError(
            f"tip_level table rows include a player who debuted in {table.max_debut_year}, "
            f"not before vintage {v}")
    seasons = [r.get("season") for rows in (career_stats or {}).values()
               for r in rows or [] if r.get("season") is not None]
    _assert_seasons_before(v, seasons, "tip_level career rows")
    as_of = date(v - 1, 12, 31)
    mlb_value = table.read(grade)
    out = {"tool": table.tool, "stat": stat, "side": side, "level": level, "vintage": v,
           "as_of": as_of.isoformat(), "grade": _f(grade), "tip_mlb": mlb_value,
           "value": None, "label": None, "inputs": {"table_rows": table.n_rows,
                                                   "table_max_season": table.max_season}}
    if mlb_value is None:
        out["label"] = "no table"
        return out
    if level == "MLB":
        out["value"] = mlb_value
        out["label"] = "calibrated"
        return out
    if level == "AAA":
        off = aaa_offset_within_player(career_stats, stat, side, v)
        out["inputs"]["aaa_offset"] = off
        if off["offset"] is None:
            out["label"] = "no within-player AAA offset on the rows"
            return out
        out["value"] = mlb_value + off["offset"]
        out["label"] = "calibrated"
        return out
    import level_norms
    kw = {"today": as_of}
    if seasons_window is not None:
        kw["seasons_window"] = int(seasons_window)
    norms = level_norms.compute_level_norms(career_stats, birth_dates, **kw)
    key = _LEVEL_STAT[stat][side]
    lvl = ((norms.get(level) or {}).get("perf") or {}).get(key)
    mlb = ((norms.get("MLB") or {}).get("perf") or {}).get(key)
    out["inputs"]["level_norm"] = lvl
    out["inputs"]["mlb_norm"] = mlb
    out["inputs"]["norms_as_of"] = as_of.isoformat()
    if lvl is None or not mlb:
        out["label"] = f"{_UNCALIBRATED}: no level norm"
        return out
    out["value"] = mlb_value / float(mlb) * float(lvl)
    out["label"] = _UNCALIBRATED
    return out


# ---------------------------------------------------------------------------
# step 4: the first-season hook on LANE B's aging service
# ---------------------------------------------------------------------------
def _curve_value(curve: dict, age: int) -> float:
    """The delta moving INTO `age`, at the nearest supported age (the reading rule
    of fa_projection.curve_delta)."""
    if not curve:
        return 0.0
    ages = sorted(int(a) for a in curve)
    a = min(ages, key=lambda x: abs(x - age))
    c = curve[str(a)] if str(a) in curve else curve[a]
    return float(c.get("delta_smooth", c.get("delta", 0.0)) or 0.0)


def tip_first(table: TipTable, grade, arrival_age, *, side: str, comp: str,
              bucket: str | None = None, model=None, aging: str = "v2") -> dict:
    """Step 4: TIP_mat plus the stat-specific age change from the arrival age to 27,
    supplied by aging_v3.AgingModel.component_curve (U3, U6: aging="v2" until
    docs/AGING_V3_GATE.md records a pass). Raises ServiceMissing when aging_v3 is
    not importable or carries no model; never a local aging curve. Where the
    service has no curve for `comp`, the table's first-season read is returned and
    the row says so."""
    if aging != "v2":
        raise ValueError("tip_first takes aging='v2' until docs/AGING_V3_GATE.md records a pass (U6)")
    try:
        import aging_v3
    except ImportError as e:                                   # pragma: no cover
        raise ServiceMissing("aging_v3 (LANE B's aging service) is not importable") from e
    if aging_v3 is None or not hasattr(aging_v3, "AgingModel"):
        raise ServiceMissing("aging_v3 (LANE B's aging service) is not importable")
    if model is None:
        try:
            model = aging_v3.served_model()
        except Exception as e:                                 # AgingV3Unavailable
            raise ServiceMissing(f"aging_v3 has no model to read: {e}") from e
    base = table.read(grade)
    a = _f(arrival_age)
    out = {"tool": table.tool, "stat": table.stat, "grade": _f(grade), "arrival_age": a,
           "to_age": MATURITY_AGE, "aging": aging, "base": base, "delta": 0.0,
           "value": base, "note": None}
    if base is None or a is None:
        out["note"] = "no table value or no arrival age"
        return out
    try:
        # aging_v3.AgingModel.component_curve: the v2 component curves under every arm
        curve = model.component_curve(side, comp, bucket)
    except KeyError:
        out["note"] = ("first-season frame read directly: the aging service carries "
                       f"no curve for {comp!r}")
        return out
    if bucket is None and isinstance(curve, dict) and curve and \
            all(isinstance(v, dict) for v in curve.values()) and \
            set(curve) <= {"C", "H", "SP", "RP"}:
        curve = curve.get("H" if side == "hit" else "SP") or next(iter(curve.values()))
    if not curve:
        out["note"] = ("first-season frame read directly: the aging service carries "
                       f"no curve for {comp!r}")
        return out
    a_int = int(round(a))
    delta = 0.0
    if a_int < MATURITY_AGE:
        for age in range(a_int + 1, MATURITY_AGE + 1):
            delta += _curve_value(curve, age)
    elif a_int > MATURITY_AGE:
        for age in range(MATURITY_AGE + 1, a_int + 1):
            delta -= _curve_value(curve, age)
    out["delta"] = delta
    out["value"] = base + delta
    return out
