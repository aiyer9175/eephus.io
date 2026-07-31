# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV surrogate-label maps (Stage 1 of the surrogate-label program).

The label-horizon trap: the 2019-2023 debut cohorts have rich features but a
censored first-6yr-WAR label. This module fits leakage-clean Stage-1 maps that turn
a fast-resolving SHORT-horizon outcome into a first-6yr-WAR-equivalent, calibrated on
the DEEP historical window (resolved 2011-2018 cohorts), so those recent cohorts can
train against an observed surrogate instead of a KM rate-projection guess.

Ladder rungs (coarsest to finest), each its own map to first-6yr WAR:
  reached_mlb   never-debuted -> 0 (busts already carry this; degenerate for debuted)
  survived_aa   reached Double-A y/n  (for the undebuted-active EXPANSION, not the
                current debuted+bust matrix where it is degenerate)
  mle           realized next-level line (translation layer; expansion)
  war_k         WAR through debut + (k-1) seasons -> first-6yr WAR   <- the OPERATIVE
                rung for the current matrix (measured Spearman: k=3 -> 0.880, k=2 -> 0.742)

Only war_k is non-degenerate on the current train/eval matrix (every debuted row
reached MLB; every bust is 0). The other rungs are fit here and exposed for the
matrix expansion that adds undebuted-active prospects. Maps are monotone (PAVA
isotonic) so the WAR-equivalent never inverts the surrogate's rank.

Pure: no I/O, no network. Callers pass rows + a {player_key: {season:war}} map.
"""

from __future__ import annotations

TARGET_SEASONS = 6
WAR_K = 3                 # finest rung uses WAR through debut+2 (3 seasons)
WAR_K_MIN = 2             # fall back to a 2-season map when only 2 are observed


def _war_through(seasons: dict, dy: int, k: int) -> float:
    """Summed bWAR over debut year .. debut+k-1 (observed seasons only)."""
    return sum(float(seasons.get(dy + i, 0.0)) for i in range(k))


def _observed_span(seasons: dict, dy: int) -> int:
    """How many of the first-6 windows have a realized season entry (contiguous
    from the debut year). Used to pick the finest resolvable WAR rung."""
    n = 0
    for i in range(TARGET_SEASONS):
        if (dy + i) in seasons:
            n = i + 1
        else:
            break
    return n


def _pava(pairs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pool-adjacent-violators isotonic regression. pairs = (x, y) sorted by x;
    returns (x, fitted_y) monotone non-decreasing in x."""
    if not pairs:
        return []
    pts = sorted(pairs, key=lambda p: p[0])
    # blocks: [sum_y, count, x_right]
    blocks = [[y, 1, x] for x, y in pts]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] / blocks[i][1] > blocks[i + 1][0] / blocks[i + 1][1]:
            blocks[i][0] += blocks[i + 1][0]
            blocks[i][1] += blocks[i + 1][1]
            blocks[i][2] = blocks[i + 1][2]
            del blocks[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    out = []
    for s, c, xr in blocks:
        out.append((xr, s / c))
    return out


class _IsoMap:
    """Monotone step map from a PAVA fit, with flat extrapolation + linear interp."""

    def __init__(self, knots: list[tuple[float, float]]):
        self.knots = knots or [(0.0, 0.0)]

    def __call__(self, x: float) -> float:
        ks = self.knots
        if x <= ks[0][0]:
            return ks[0][1]
        if x >= ks[-1][0]:
            return ks[-1][1]
        for i in range(1, len(ks)):
            if x <= ks[i][0]:
                x0, y0 = ks[i - 1]
                x1, y1 = ks[i]
                if x1 == x0:
                    return y1
                w = (x - x0) / (x1 - x0)
                return y0 + w * (y1 - y0)
        return ks[-1][1]


def fit_maps(resolved_rows: list[dict], cw: dict) -> dict:
    """Fit the Stage-1 WAR-k maps on the RESOLVED cohort only (leakage-clean: the
    caller passes strictly-resolved rows, typically decision-year <= 2018, and the
    maps are applied forward to >= 2019). resolved_rows carry player_key + debut_year
    + target_resolved. cw = {player_key: {season:war}}. Returns {'war3','war2',
    'resid_var3','resid_var2','n'}."""
    p3, p2 = [], []
    for r in resolved_rows:
        pk, dy, t6 = r.get("player_key"), r.get("debut_year"), r.get("target_resolved")
        s = cw.get(pk)
        if not s or dy is None or t6 is None:
            continue
        p3.append((_war_through(s, dy, 3), float(t6)))
        p2.append((_war_through(s, dy, 2), float(t6)))
    m3 = _IsoMap(_pava(p3))
    m2 = _IsoMap(_pava(p2))

    def _resid_var(pairs, m):
        if len(pairs) < 5:
            return None
        errs = [(y - m(x)) for x, y in pairs]
        mu = sum(errs) / len(errs)
        return sum((e - mu) ** 2 for e in errs) / (len(errs) - 1)

    return {"war3": m3, "war2": m2,
            "resid_var3": _resid_var(p3, m3), "resid_var2": _resid_var(p2, m2),
            "n": len(p3)}


def surrogate_equiv(row: dict, cw: dict, maps: dict) -> tuple[float | None, float]:
    """The first-6yr-WAR-equivalent for one row, plus a variance weight in (0,1].

    Resolved rows keep their true label (weight 1). Censored debuted rows map their
    finest observed WAR rung (3-season if >= 3 observed, else 2-season) through the
    Stage-1 map; the weight is the inverse of that rung's residual variance, floored,
    so a noisier surrogate is down-weighted. Busts stay 0 (weight 1). Returns
    (war_equiv, weight); war_equiv is None when no rung has resolved."""
    if row.get("kind") == "bust":
        return 0.0, 1.0
    if not row.get("censored"):
        t = row.get("target_resolved")
        return (float(t) if t is not None else None), 1.0
    pk, dy = row.get("player_key"), row.get("debut_year")
    s = cw.get(pk)
    if not s or dy is None:
        return None, 0.0
    span = _observed_span(s, dy)
    if span >= 3:
        eq = maps["war3"](_war_through(s, dy, 3))
        rv = maps.get("resid_var3")
    elif span >= 2:
        eq = maps["war2"](_war_through(s, dy, 2))
        rv = maps.get("resid_var2")
    else:
        return None, 0.0
    # inverse-variance weight, normalized to the resolved var (~1.0) and floored so
    # a surrogate row still contributes; shrinks a high-variance rung toward its mean.
    w = 1.0 if not rv else max(0.35, min(1.0, 1.0 / (1.0 + rv / 6.0)))
    return float(eq), float(w)
