# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_rates - pooled rate statistics from SUMMED counting stats.

One recipe for every consumer that holds summed counts and wants the rates over
them: the multi-year window boards (tools/mlbstats_window_lab.py imports these
functions back under its own `_hitter_rates`, `_pitcher_rates` and `_pooled`
names) and the League Averages tab of /mlbstats/. A second copy of any formula
here is how a wrong number ends up under a right name, so there is none: the
counts are handed back through the shipped derivations (hitter_export plus
hem_plus for hitting; starter_export plus sem_plus, or bullpen_export plus
rem_plus, for pitching), and each rate is therefore pooled over its own named
denominator.

The `acc` dict is the lab's summed-counts accumulator: lower-case keys (`pa`,
`ab`, `h`, `2b`, `3b`, `hr`, `bb`, `ibb`, `hbp`, `sf`, `so`, `sb`, `cs` for a
hitter; `g`, `gs`, `outs`, `tbf`, `er`, `r`, `bb`, `so`, `hr`, `hbp`, `pit`,
`strk`, `cg`, `go`, `ao`, `sv`, `hld` for a pitcher). A missing count is read
as absent, exactly as the shipped row builders read it.

PURE: no network and no I/O. Moved verbatim from tools/mlbstats_window_lab.py
(LT-02 in docs/master-plan-2026-09-24-final-pass.md); test_mlbstats_rates.py
pins that the outputs did not move.
"""
from __future__ import annotations


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _r(v, nd=3):
    n = _num(v)
    return None if n is None else round(n, nd)


def hitter_rates(acc: dict) -> dict:
    """The pooled hitting rates, computed by handing the SUMMED counts back
    through the shipped derivation (hem_plus.derive_rates on a Hitter built by
    hitter_export.build_hitters).

    That is what makes every rate here pooled by its own named denominator
    without a second formula existing anywhere: AVG is H / AB over the window,
    BABIP is (H - HR) / (AB - SO - HR + SF) over the window, OBP is over
    AB + BB + HBP + SF, and OPS is the pooled OBP plus the pooled SLG rather
    than a pooled ratio of its own. Re-typing those denominators here is how a
    wrong number ends up under a right name."""
    import hem_plus
    import hitter_export as he
    row = {"mlbam": 0, "name": "", "team": "",
           "PA": acc.get("pa"), "AB": acc.get("ab"), "H": acc.get("h"),
           "2B": acc.get("2b"), "3B": acc.get("3b"), "HR": acc.get("hr"),
           "BB": acc.get("bb"), "IBB": acc.get("ibb"), "HBP": acc.get("hbp"),
           "SF": acc.get("sf"), "SO": acc.get("so"), "SB": acc.get("sb"),
           "CS": acc.get("cs")}
    hitters = he.build_hitters([row])
    if not hitters:
        return {}
    h = hitters[0]
    hem_plus.derive_rates(h)
    woba = hem_plus._raw_woba(h)
    return {"avg": _r(h.rates.get("avg")), "obp": _r(h.rates.get("obp")),
            "slg": _r(h.rates.get("slg")), "ops": _r(h.rates.get("ops")),
            "iso": _r(h.rates.get("iso")), "babip": _r(h.rates.get("babip")),
            "bb_pct": _r(h.rates.get("bb_pct"), 4),
            "k_pct": _r(h.rates.get("k_pct"), 4),
            "woba_raw": _r(woba), "_woba_den": _r(h.rates.get("woba_denom"), 1)}


def pitcher_rates(acc: dict, *, starter: bool) -> dict:
    """The pooled pitching rates, computed the same way: the summed counts are
    handed back through the shipped scorer (starter_export.build_starters plus
    sem_plus.derive_rates, or bullpen_export.build_relievers plus
    rem_plus.derive_rates), so ERA is ER / IP x 9 over the window and K% is
    SO / TBF over it.

    SKILL FIP IS NOT AMONG THEM and never can be: sem_plus.fip_skill shrinks the
    component rates toward `pool.mean_k_pct` / `mean_bb_pct` / `mean_hbp_pct` /
    `mean_hr_rate` and offsets the result by `pool.cfip`. Those are five
    parameters of one season's pool, so a window FIP would be a different
    statistic wearing the same header."""
    import bullpen_export as be
    import rem_plus
    import sem_plus
    import starter_export as se
    outs = int(acc.get("outs") or 0)
    row = {"mlbam": 0, "name": "", "team": "",
           "G": acc.get("g"), "GS": acc.get("gs"),
           "IP": f"{outs // 3}.{outs % 3}",
           "BF": acc.get("tbf"), "ER": acc.get("er"), "R": acc.get("r"),
           "BB": acc.get("bb"), "SO": acc.get("so"), "HR": acc.get("hr"),
           "HBP": acc.get("hbp"), "Pit": acc.get("pit"), "Strk": acc.get("strk"),
           "CG": acc.get("cg"), "GO": acc.get("go"), "AO": acc.get("ao"),
           "SV": acc.get("sv"), "HLD": acc.get("hld")}
    if starter:
        built = se.build_starters([row])
        if not built:
            return {}
        s = built[0]
        sem_plus.derive_rates(s)
        # HR/9 is built in the ROW, not in derive_rates (sem_plus.py:327 and
        # rem_plus.py:476 carry the same expression), and the row builder needs a
        # season pool this window does not have. Same expression, over the
        # window's own summed HR and innings.
        return {"era": _r(s.rates.get("era"), 2),
                "hr9": _r(pooled((acc.get("hr") or 0) * 9.0, outs / 3.0, 2), 2),
                "k_pct": _r(s.rates.get("k_pct"), 4),
                "bb_pct": _r(s.rates.get("bb_pct"), 4),
                "k_bb_pct": _r(s.rates.get("k_bb_pct"), 4),
                "gb_pct": _r(s.rates.get("gb_pct"), 4),
                "ip_per_gs": _r(s.rates.get("ip_per_gs"), 2),
                "strike_pct": _r(s.rates.get("strike_pct"), 4)}
    built = be.build_relievers([row], {})
    if not built:
        return {}
    r = built[0]
    rem_plus.derive_rates(r)
    return {"era": _r(r.rates.get("era"), 2),
            "hr9": _r(pooled((acc.get("hr") or 0) * 9.0, outs / 3.0, 2), 2),
            "k_pct": _r(r.rates.get("k_pct"), 4),
            "bb_pct": _r(r.rates.get("bb_pct"), 4),
            "k_bb_pct": _r(r.rates.get("k_bb_pct"), 4)}


def pooled(num: float | None, den: float | None, nd: int = 3):
    if num is None or not den:
        return None
    return round(float(num) / float(den), nd)
