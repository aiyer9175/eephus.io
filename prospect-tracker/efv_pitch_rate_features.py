# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV pitch-rate family: P/PA and P/BF as candidate eFV drivers, the SIDECAR (owner ask
19 of 2026-09-30; plan Part 8 lane pitch_metrics, pitch_metrics.md s7; Q10_10).

WHAT THIS BUILDS. For every F-LV row (efv_vintage_frame.build_frame) one pre-declared
column per side, never a column in a pinned matrix:

    ppa_rel   hitters. Over the up-to-MAX_SEASONS most recent USABLE pre-V seasons in
              which the player has a line with PA >= HIT_MIN_PA at a level, each such
              (level, season) line gives d = ln(P/PA / L(level, season)), L the pooled
              level-season anchor. The column is the PA-weighted mean of d, shrunk by
              PA / (PA + K_SHRINK) on the total PA of the lines read (the W-PLATOON
              K = 100 precedent).
    pbf_rel   pitchers. The same on P/BF of the majority-role line (the role with more
              batters faced at that level-season) against its ROLE anchor, with
              BF >= PIT_MIN_BF. P/BF, not P/IP, because P/BF carries the stable part.

No sign is predicted: the admission rule (DS-06, docs/efv-v2/EFV_V2_GATE.md s4.2) asks
for sign stability, not a direction, and the admission itself is Q10_11's.

SOURCE. pitch_rates.player_lines and pitch_rates.league_rates (the repo's ONE definition
of the rates, the anchors and the tracking guard; their own cache .cache/pitch_rates,
never .cache/milb_stats, never .cache/milb_platoon, never a career row). A level-season
outside "usable" gives no rate and no anchor, so it can never enter a row. The person
id is the row's OUTCOME-BLIND id `mlbam_id` (efv_identity, DS-03); the record's stored
id is audit only and is never read here. Only seasons up to V - 1 are read (the V
season starts after the V preseason window closes).

MISSINGNESS (bug B3, docs/efv-v2/DRIVER_SYSTEM_V2.md s2). Has-block is tied to level by
construction (for V 2017 the pre-V blocks are AAA, AA and A 2016 only; complex and DSL
lines are untracked before 2024), so a row with no qualifying line carries None, is
imputed at the has-block TRAIN mean (impute_at_train_mean), and no absence flag is
emitted for any head. `has_block` exists only for the coverage count and the balance
probe.

BANS. This module reads no WAR, label, outcome or major league column, and no debut:
the R-VM drop (2025 and later debut cohorts) is the probe tool's
(tools/efv_pitch_rate_sidecar.py), before any count. Reserved list vintages 2020 and
2021 raise through efv_vintage_frame's guard. Nothing groups, counts or averages rows
by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md): the only summaries are counts by
(side, vintage) and correlations with other pre-V MiLB rate columns.
"""
from __future__ import annotations

import math

import efv_vintage_frame as F
import pitch_rates as P

#: The shrink constant on total exposure (PA or BF): value x n / (n + K_SHRINK).
K_SHRINK = 100.0
#: The exposure floor a (level, season) line must reach to be read.
HIT_MIN_PA = 50
PIT_MIN_BF = 60
#: The most recent qualifying pre-V seasons read.
MAX_SEASONS = 3
#: The first MiLB season the pitch-rate producer holds.
FIRST_SEASON = P.MILB_FIRST
#: The levels read (the producer's own MiLB levels; never MLB).
LEVELS = tuple(P.MILB_LEVELS)
#: The column per side.
COLUMNS = {"hit": "ppa_rel", "pit": "pbf_rel"}
#: The rate each column is built on, per side.
RATES = {"hit": "p_pa", "pit": "p_bf"}


def column_name(side: str) -> str:
    if side not in F.SIDES:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    return COLUMNS[side]


# ---------------------------------------------------------------------------
# the producer's lines and anchors, memoized per (season, level)
# ---------------------------------------------------------------------------

class RateSource:
    """pitch_rates.player_lines and league_rates for one process, read from the
    producer's cache only (fetch=False), each (season, level) read once."""

    def __init__(self, lines=None, anchors=None):
        self._lines_fn = lines or (lambda s, lv: P.player_lines(s, lv, fetch=False))
        self._anchor_fn = anchors or (lambda lv, s: P.league_rates(lv, s, fetch=False))
        self._lines: dict = {}
        self._anchors: dict = {}

    def lines(self, season: int, level: str) -> dict:
        k = (int(season), level)
        if k not in self._lines:
            raw = self._lines_fn(int(season), level) or {}
            self._lines[k] = {int(pid): ln for pid, ln in raw.items() if pid is not None}
        return self._lines[k]

    def anchors(self, season: int, level: str) -> dict:
        k = (int(season), level)
        if k not in self._anchors:
            self._anchors[k] = self._anchor_fn(level, int(season)) or {}
        return self._anchors[k]


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def hit_line(line: dict | None, anchors: dict) -> tuple[float, float, float] | None:
    """(PA, P/PA, anchor P/PA) for one hitter (level, season) line, or None when the
    line or the anchor is not readable (untracked level-season, missing pitches, PA
    below the floor)."""
    h = (line or {}).get("hit")
    if not h:
        return None
    pa = _int(h.get("pa")) or 0
    rate = h.get("p_pa")
    anchor = ((anchors or {}).get("hit") or {}).get("p_pa")
    if pa < HIT_MIN_PA or not rate or not anchor:
        return None
    return float(pa), float(rate), float(anchor)


def pit_line(line: dict | None, anchors: dict) -> tuple[float, float, float, str] | None:
    """(BF, P/BF, role anchor P/BF, role) for one pitcher (level, season) line, on the
    majority-role line pitch_rates chose (its sp or rp split, or the season line on the
    producer's season-line fallback), or None when not readable."""
    p = (line or {}).get("pit")
    if not p:
        return None
    role = p.get("role")
    if role not in ("SP", "RP"):
        return None
    if p.get("basis") == P.BASIS_ROLE:
        src = p.get("sp" if role == "SP" else "rp") or {}
    else:
        src = p.get("season_line") or {}
    bf = _int(src.get("bf")) or 0
    rate = p.get("p_bf")
    anchor = ((anchors or {}).get("sp" if role == "SP" else "rp") or {}).get("p_bf")
    if bf < PIT_MIN_BF or not rate or not anchor:
        return None
    return float(bf), float(rate), float(anchor), role


def feature(person_id, vintage: int, side: str, source: RateSource) -> dict:
    """The column for one (person, V, side):

        value      the shrunk PA- (or BF-) weighted mean of ln(rate / anchor), or None
        has_block  True when at least one (level, season) line qualified
        exposure   total PA (BF) of the lines read
        seasons    the pre-V seasons read, newest first (at most MAX_SEASONS)
        lines      [[season, level, exposure, d], ...] for audit (d to 6 places)

    Seasons walk down from V - 1 to FIRST_SEASON; a season enters when it holds at
    least one qualifying line, and every qualifying level line of that season is read.
    """
    V = int(vintage)
    F.guard_score_request(V, purpose="pitch rate feature")
    if side not in F.SIDES:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    pid = _int(person_id)
    out = {"value": None, "has_block": False, "exposure": 0, "seasons": [], "lines": []}
    if pid is None:
        return out
    read = []
    for season in range(V - 1, FIRST_SEASON - 1, -1):
        got = []
        for lv in LEVELS:
            ln = source.lines(season, lv).get(pid)
            if ln is None:
                continue
            a = source.anchors(season, lv)
            q = hit_line(ln, a) if side == "hit" else pit_line(ln, a)
            if q is None:
                continue
            exp, rate, anchor = q[0], q[1], q[2]
            got.append((season, lv, exp, math.log(rate / anchor)))
        if got:
            read.append(season)
            out["lines"].extend(got)
        if len(read) >= MAX_SEASONS:
            break
    if not out["lines"]:
        return out
    tot = sum(e for _s, _lv, e, _d in out["lines"])
    mean_d = sum(e * d for _s, _lv, e, d in out["lines"]) / tot
    out["value"] = mean_d * tot / (tot + K_SHRINK)
    out["has_block"] = True
    out["exposure"] = int(tot)
    out["seasons"] = read
    out["lines"] = [[s, lv, int(e), round(d, 6)] for s, lv, e, d in out["lines"]]
    return out


def attach(rows: list[dict], source: RateSource | None = None) -> list[dict]:
    """Each F-LV row's feature, keyed like the row ({"player_key", "vintage", "side",
    "id_resolved", **feature}). The join is on the row's outcome-blind `mlbam_id`; reserved vintages
    raise before any read."""
    source = source or RateSource()
    out = []
    for r in rows:
        V = int(r["vintage"])
        F.guard_score_request(V, purpose="pitch rate feature")
        f = feature(r.get("mlbam_id"), V, r["side"], source)
        out.append({"player_key": r["player_key"], "vintage": V, "side": r["side"],
                    "id_resolved": r.get("mlbam_id") is not None, **f})
    return out


# ---------------------------------------------------------------------------
# imputation (DS-04): absence at the has-block TRAIN mean, no flag
# ---------------------------------------------------------------------------

def impute_at_train_mean(values: dict, train_keys) -> dict:
    """{key: value} with every None replaced by the mean of the NON-None values whose
    key is in `train_keys` (the fold's training rows). No absence flag is returned:
    under DS-04 and bug B3 none may enter a head. Raises when the training rows hold
    no value, so a fold cannot silently impute zero."""
    train = [values[k] for k in train_keys if values.get(k) is not None]
    if not train:
        raise ValueError("no has-block training row to impute from")
    m = sum(train) / len(train)
    return {k: (m if v is None else v) for k, v in values.items()}


# ---------------------------------------------------------------------------
# step (a): coverage, counts only
# ---------------------------------------------------------------------------

def coverage(feats_by_side: dict[str, dict[int, list[dict]]]) -> dict:
    """Counts by (side, vintage) and nothing else: rows, rows with an outcome-blind id,
    rows with a block, rows by the number of seasons read, and the (level, season)
    lines read by level. No outcome, no grade."""
    out: dict = {}
    for side, by_v in feats_by_side.items():
        for V, feats in sorted(by_v.items()):
            V = int(V)
            F.guard_score_request(V, purpose="pitch rate coverage")
            n_seasons = {str(k): 0 for k in range(1, MAX_SEASONS + 1)}
            by_level = {lv: 0 for lv in LEVELS}
            for f in feats:
                if f["has_block"]:
                    n_seasons[str(len(f["seasons"]))] += 1
                    for _s, lv, _e, _d in f["lines"]:
                        by_level[lv] += 1
            blk = {"rows": len(feats),
                   "id_resolved": sum(1 for f in feats if f.get("id_resolved")),
                   "has_block": sum(1 for f in feats if f["has_block"]),
                   "by_n_seasons": n_seasons,
                   "lines_by_level": by_level}
            blk["has_block_share"] = (round(blk["has_block"] / blk["rows"], 4)
                                      if blk["rows"] else None)
            out[f"{side}:{V}"] = blk
    return out


# ---------------------------------------------------------------------------
# step (d): descriptive correlations with other pre-V MiLB rate columns
# ---------------------------------------------------------------------------

def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    return pearson(_ranks(xs), _ranks(ys))


def correlations(pairs: list[tuple[int, float, float]]) -> dict:
    """Descriptive correlations of the column with one other column over rows that
    carry both: pairs are (V, column value, other value). Pooled Pearson and Spearman
    and the per-vintage Spearman. No outcome enters."""
    xs = [p[1] for p in pairs]
    ys = [p[2] for p in pairs]
    per_v: dict = {}
    for V in sorted({p[0] for p in pairs}):
        F.guard_score_request(int(V), purpose="pitch rate correlation")
        sub = [p for p in pairs if p[0] == V]
        rho = spearman([p[1] for p in sub], [p[2] for p in sub])
        per_v[str(V)] = {"n": len(sub), "spearman": None if rho is None else round(rho, 4)}
    pr, sr = pearson(xs, ys), spearman(xs, ys)
    return {"n": len(pairs),
            "pearson": None if pr is None else round(pr, 4),
            "spearman": None if sr is None else round(sr, 4),
            "by_vintage_spearman": per_v}
