# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The park-matched xHEM+ part (EBR_GATE.md 11.12, owner decision EW3-52): the pure core.

WHY. FanGraphs' batting runs carry a park term, (1 - PF) * lgR/PA * PA per stint on
the Basic (5yr) factor. The xHEM+ arm of candidate part 4 (S1x, part 9.4) swaps
actual wOBA for the re-levelled Savant xwOBA and keeps that term; xwOBA carries only
part of a park's effect, so the swap charges a run-friendly park a second time
(11.12.1). The re-specified part subtracts, per arm, the share b of fWAR's park term
that the arm's own rate re-introduces, so the park is removed once:

    P_i     = sum over stints t of (1 - PF_t) * lgR/PA * PA_i,t      (fwar_frame.park_runs)
    g_pm,i  = g_batx,i - b_arm(i) * P_i
    d_pm,i  = g_pm,i re-centred per season over the rule's rows (pitcher-batters out)
    x_pm,i  = LAMBDA * d_pm,i / RPW*_s

b is fitted once on 2016 to 2019 (fit_share) and frozen below with its fit log
(docs/ebr-2026-09-30/xhem_parkmatch_fit.json, written by tools/xhem_park_terms.py
--fit). Nothing here reads a file, fetches or writes; tools/xhem_park_terms.py reads
the caches, tools/build_ewar_v3.py carries the part behind ewar_v3's flags, and
tools/xhem_parkmatch_lab.py is the one read. This module never relates a delta to a
next-season quantity.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence

import fwar_frame as F

#: Seasons the share b is fitted on (11.12.2): outside the read's deciding seasons
#: (2021 to 2025) and the park-pattern check's (2021 to 2026); 2020 out.
FIT_SEASONS = (2016, 2017, 2018, 2019)
#: The arms of S1x's rows (part 9.4): the xHEM+ arm and the HEM+ arm standing in.
ARMS = ("xhem", "hem")
#: b is a share of fWAR's park term: clamped to [0, 1].
B_RANGE = (0.0, 1.0)

#: The frozen shares (11.12.2), equal to the fit log's `b` per arm (pinned by
#: test_xhem_parkmatch.py). Fitted 2026-10-26 on the swar preview of 2026-10-22
#: (xHEM+ arm 1,417 rows, se 0.0876; HEM+ arm 1,116 rows, se 0.2428).
B_FROZEN: Optional[Mapping[str, float]] = {"xhem": 0.46773, "hem": 0.093828}

#: The park-pattern check (11.12.4).
CHECK_SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
SLOPE_TOL = 0.05                 # wins per PF point, either side of 0
NAMED_Z = 1.96
NEUTRAL_PF = (97.0, 103.0)       # PF points of the club-seasons sd_n is read on
#: The named parks: (label, StatsAPI club id, seasons).
NAMED_PARKS = (("Coors Field (COL)", 115, (2021, 2022, 2023, 2024, 2025, 2026)),
               ("Sutter Health Park, Sacramento (ATH)", 133, (2025, 2026)))
SLOPE_BOOT = 2000
SLOPE_SEED = 20261026
#: The read (11.12.3).
NONINF_MARGIN = 0.02


class ParkMatchStop(RuntimeError):
    """A precondition of the re-specified part failed: nothing is built."""


def park_term(stints: Iterable[tuple[float, float]], lg_r_pa: float) -> float:
    """P_i = sum over (pa_t, pf_t) of (1 - pf_t) * lgR/PA * pa_t, fwar_frame.park_runs
    per stint, PF as a decimal. Negative in a run-friendly park."""
    return float(sum(F.park_runs(float(pa), float(lg_r_pa), float(pf)) for pa, pf in stints))


def stint_pa(pa: float, bref_stints: Sequence[Mapping], tmap: Mapping, row_team) -> list[tuple]:
    """[(club id, PA)]: the season PA split by B-Ref stint PA shares, stint teams
    mapped to StatsAPI ids (tools/fwar_replica_eval.hitters' rule: a single-stint
    player whose B-Ref code is unmapped takes the row's team; no stint, the row's
    team takes every PA)."""
    tot = sum(float(s.get("pa") or 0.0) for s in bref_stints)
    if tot > 0:
        return [(tmap.get(s["team"], row_team if len(bref_stints) == 1 else None),
                 float(pa) * float(s["pa"]) / tot) for s in bref_stints if float(s.get("pa") or 0.0) > 0]
    return [(row_team, float(pa))]


def fit_share(rows: Iterable[Mapping], seasons: Iterable[int] = FIT_SEASONS) -> dict:
    """b for one arm: the PA-weighted least-squares slope of g / PA on P / PA with
    one intercept per season (within-season weighted demeaning), over rows with
    PA > 0 in `seasons`. Each row: {"season", "pa", "g", "P"}. Returns the raw slope,
    the clamped b, n and the slope's weighted-residual standard error."""
    keep = set(int(s) for s in seasons)
    by: dict = {}
    for r in rows:
        s, pa = int(r["season"]), float(r.get("pa") or 0.0)
        if s not in keep or pa <= 0 or r.get("g") is None or r.get("P") is None:
            continue
        by.setdefault(s, []).append((pa, float(r["g"]) / pa, float(r["P"]) / pa))
    sxy = sxx = 0.0
    n = 0
    resid: list = []
    for s, v in by.items():
        w = sum(a for a, _, _ in v)
        mx = sum(a * x for a, _, x in v) / w
        my = sum(a * y for a, y, _ in v) / w
        for a, y, x in v:
            sxy += a * (x - mx) * (y - my)
            sxx += a * (x - mx) ** 2
            n += 1
        resid.append((v, mx, my))
    if n < 3 or sxx <= 0:
        return {"n": n, "slope": None, "b": None, "se": None, "seasons": sorted(by)}
    slope = sxy / sxx
    ssr = sum(a * ((y - my) - slope * (x - mx)) ** 2 for v, mx, my in resid for a, y, x in v)
    dof = max(1, n - 1 - len(by))
    se = (ssr / dof / sxx) ** 0.5
    b = min(B_RANGE[1], max(B_RANGE[0], slope))
    return {"n": n, "slope": slope, "b": b, "se": se, "seasons": sorted(by)}


def recentre(g: Mapping[int, float], pa: Mapping[int, float], exclude: Iterable[int] = ()) -> dict:
    """d_i = g_i - PA_i * sum(g) / sum(PA) over the rows inside the rule; a row in
    `exclude` (a pitcher-batter) carries 0 and sits outside both sums (swar.recentre's
    rule)."""
    out_rule = set(int(i) for i in exclude)
    inside = [i for i in g if int(i) not in out_rule]
    tot = sum(float(pa.get(i) or 0.0) for i in inside)
    c = (sum(float(g[i]) for i in inside) / tot) if tot > 0 else 0.0
    return {i: (0.0 if int(i) in out_rule else float(g[i]) - float(pa.get(i) or 0.0) * c) for i in g}


def pm_deltas(rows: Mapping[int, Mapping], park: Mapping[int, float], b: Mapping[str, float]) -> dict:
    """d_pm per hitter-season of one season. `rows`: {mlbam: {"d": S1x's re-centred
    d_batx (runs), "pa", "arm": "xhem" or "hem", "pb": pitcher-batter}}; `park`:
    {mlbam: P}. Because re-centring is linear, re-centring d_batx - b P equals
    re-centring g_batx - b P. A rule row with PA > 0 and no park term stops."""
    if b is None or any(a not in b or b[a] is None for a in ARMS):
        raise ParkMatchStop("the shares b are not frozen (xhem_parkmatch.B_FROZEN)")
    g: dict = {}
    pa: dict = {}
    pbs = []
    missing = []
    for m, r in rows.items():
        pa[m] = float(r.get("pa") or 0.0)
        if r.get("pb"):
            pbs.append(m)
            g[m] = 0.0
            continue
        p = park.get(m)
        if p is None:
            if pa[m] > 0:
                missing.append(m)
            p = 0.0
        arm = "xhem" if r.get("arm") == "xhem" else "hem"
        g[m] = float(r.get("d") or 0.0) - float(b[arm]) * float(p)
    if missing:
        raise ParkMatchStop(f"{len(missing)} hitter-seasons with PA have no park term (first {sorted(missing)[:3]})")
    return recentre(g, pa, pbs)


def ols_slope(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    """The OLS slope of y on x; None with fewer than 3 points or no spread in x."""
    if len(x) < 3:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx <= 0:
        return None
    return sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx


def club_changes(x: Mapping[int, float], stints: Mapping[int, Sequence[tuple]]) -> dict:
    """{club id: sum over hitters of x_i * PA_i,t / PA_i} for one season; a hitter
    with no stint PA adds nothing."""
    out: dict = {}
    for m, v in x.items():
        st = [(t, p) for t, p in (stints.get(m) or []) if p and p > 0]
        tot = sum(p for _, p in st)
        if tot <= 0:
            continue
        for t, p in st:
            out[t] = out.get(t, 0.0) + float(v) * p / tot
    return out


def park_pattern(clubs: Sequence[Mapping], tol: float = SLOPE_TOL, z: float = NAMED_Z,
                 neutral: tuple = NEUTRAL_PF, named=NAMED_PARKS) -> dict:
    """The park-pattern check (11.12.4) on club-season rows {"season", "club",
    "pf_pts", "c"} (the check's seasons only): the slope of c on PF points, the
    named parks' means against 1.96 sd_n / sqrt(n), and PASS."""
    xs = [float(r["pf_pts"]) for r in clubs]
    ys = [float(r["c"]) for r in clubs]
    slope = ols_slope(xs, ys)
    # `neutral` is on the Guts scale (100 = a neutral park); pf_pts is 100 * (PF - 1)
    neu = [float(r["c"]) for r in clubs if neutral[0] <= 100.0 + float(r["pf_pts"]) <= neutral[1]]
    sd_n = None
    if len(neu) >= 3:
        mu = sum(neu) / len(neu)
        sd_n = (sum((v - mu) ** 2 for v in neu) / (len(neu) - 1)) ** 0.5
    parks = []
    for label, club, seasons in named:
        vals = [float(r["c"]) for r in clubs if r["club"] == club and int(r["season"]) in seasons]
        mean = (sum(vals) / len(vals)) if vals else None
        band = (z * sd_n / len(vals) ** 0.5) if (vals and sd_n is not None) else None
        parks.append({"park": label, "club": club, "n": len(vals), "mean": mean, "band": band,
                      "inside": bool(mean is not None and band is not None and abs(mean) <= band)})
    slope_in = bool(slope is not None and -tol <= slope <= tol)
    return {"n_club_seasons": len(clubs), "slope": slope, "tolerance": tol, "slope_inside": slope_in,
            "sd_neutral": sd_n, "n_neutral": len(neu), "named": parks,
            "pass": bool(slope_in and all(p["inside"] for p in parks))}
