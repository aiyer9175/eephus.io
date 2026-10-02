# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The companion salary legs of the projected $/WAR path (VAL_5, DESIGN_v2 I5,
rows 2 and 18; owner decision OD-4).

The ONE place the $/WAR path reads salary_path: the CBA league-minimum table
(salary_path.league_min_table / league_min_usd) and the league-wide arbitration
salary index (salary_path.arb_deflator_series). The dpw_path writer
(fa_market.build_dpw_path_block) calls it only while the committed block switch
fa_market.WRITE_DPW_PATH_BLOCK is on, and writes the result into the block as
salary_index; value_framework then reads the block, never salary_path.

So while the block switch and SERVE_DPW_PATH are off (every commit before the
fWAR epoch's step Z) no value_framework consumer reads anything salary_path
computes, which is what test_salary_path_must_not_move.py holds. Once the flip
turns unified mode on, the minimum and arbitration seasons the value_framework
side prices DO follow these two salary_path tables through the block: that is
the owner's OD-4 answer, and the flip notes it in docs/ARBITRATION_GATE.md
section 11 beside the tender cliff.
"""

from __future__ import annotations

import math

import dpw_path as dp


def _log_slope(series: dict) -> float | None:
    """exp(b) - 1 of the OLS of ln(value) on year; None with fewer than 4 points."""
    ys = sorted(series)
    if len(ys) < 4:
        return None
    n = float(len(ys))
    mx = sum(ys) / n
    my = sum(math.log(series[y]) for y in ys) / n
    num = sum((y - mx) * (math.log(series[y]) - my) for y in ys)
    den = sum((y - mx) ** 2 for y in ys)
    return math.exp(num / den) - 1.0 if den > 0 else None


def salary_index_block(base_season: int, path: dict[int, float], mode: str, through: int) -> dict:
    """The companion legs (OD-4): tabled minimum seasons read the table, season B
    keeps what salary_path serves, untabled seasons after s_T = max(B, last
    tabled) follow the mode; the arbitration index likewise after its own last
    tabled season. Never overrides a CBA-tabled number."""
    import salary_path as sp
    table = {int(k): float(v) for k, v in sp.league_min_table().items()}
    last_tab = max(table) if table else base_season
    s_t = max(int(base_season), last_tab)
    g_min = _log_slope(table)
    defl = sp.arb_deflator_series() or {}
    g_arb = _log_slope({int(k): float(v) for k, v in defl.items() if float(v) > 0})
    s_t_arb = max(int(base_season), max(defl) if defl else int(base_season))
    first = min(min(table) if table else base_season, min(path))
    p_at = lambda s: dp.interpolate_level(path, s, 0.0)   # noqa: E731
    lmin, arb = {}, {}
    for s in range(first, int(through) + 1):
        if s <= s_t:
            lmin[s] = float(sp.league_min_usd(s))
        elif mode == "neutral_follow_path":
            lmin[s] = lmin[s_t] * p_at(s) / p_at(s_t)
        elif mode == "own_trends":
            lmin[s] = lmin[s_t] * (1.0 + (g_min or 0.0)) ** (s - s_t)
        else:
            lmin[s] = lmin[s_t]
        if s <= s_t_arb:
            arb[s] = 1.0
        elif mode == "neutral_follow_path":
            arb[s] = p_at(s) / p_at(s_t_arb)
        elif mode == "own_trends":
            arb[s] = (1.0 + (g_arb or 0.0)) ** (s - s_t_arb)
        else:
            arb[s] = 1.0
    return {"mode": mode, "last_tabled_min_season": last_tab, "s_T": s_t,
            "last_tabled_arb_season": max(defl) if defl else None, "s_T_arb": s_t_arb,
            "league_min_growth": g_min, "arb_growth": g_arb,
            "league_min_by_season": {str(k): v for k, v in lmin.items()},
            "arb_index_scale_by_season": {str(k): v for k, v in arb.items()},
            "rule": "tabled; B as salary_path serves; then the mode"}
