# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Talent eWAR, the pure core (talent_ewar_v1). docs/ewar/TALENT_EWAR_GATE.md.

Each measured part of WAR on FanGraphs' frame gets its own reliability, fitted once on
2010 to 2015 pairs and frozen below; each part's rate is shrunk toward the season's mean by
that reliability, re-centred to zero per season, and summed beside the realized total; a
normal-normal posterior band says how much of the season was signal.

  hitters   parts BAT, BR, FLD on plate appearances (positional, league and replacement runs
            are conventions and never shrunk)
  pitchers  parts K, BH (walks plus hit batters) and HR per batter faced, priced by FIP's
            13, 3 and 2

Pure: numpy only, no I/O.
"""
from __future__ import annotations

import math

import numpy as np

TALENT_EWAR_VERSION = "talent_ewar_v1"
GATE_DOC = "docs/ewar/TALENT_EWAR_GATE.md"
HIT_PARTS = ("BAT", "BR", "FLD")
PIT_PARTS = ("K", "BH", "HR")
FIP_W = {"K": -2.0, "BH": 3.0, "HR": 13.0}
FIT_SEASONS = (2010, 2011, 2012, 2013, 2014, 2015)
READ_SEASONS = (2016, 2017, 2018)
FIT_FLOOR = {"hit": 200.0, "pit": 200.0}        # PA; batters faced
READ_FLOOR = {"hit": 200.0, "pit": 50.0}        # PA; IP
R_CLAMP = (0.05, 0.95)
BAND_Z = 1.2816

#: Gate part 2.2, fitted once on 2010 to 2015 pairs (2026-10-16; log in
#: data/_labs/ewar_innovate/talent_ewar_fit.json) and frozen.
#: {part: {"K": K_c, "tau2": tau2_c, "sigma2": sigma2_c}}
FROZEN: dict | None = {
    "BAT": {"K": 584.641, "tau2": 0.000409697, "sigma2": 0.239526},
    "BH": {"K": 360.6759, "tau2": 0.000319457, "sigma2": 0.11522},
    "BR": {"K": 375.3511, "tau2": 2.83377e-05, "sigma2": 0.0106366},
    "FLD": {"K": 802.2204, "tau2": 4.89215e-05, "sigma2": 0.0392459},
    "HR": {"K": 1330.196, "tau2": 2.22953e-05, "sigma2": 0.0296571},
    "K": {"K": 179.3485, "tau2": 0.00186112, "sigma2": 0.333789},
}
#: B1's k per side (the swar_lab.fit_b1 rule against the side's target), frozen with FROZEN.
B1_K: dict | None = {"hit": 748.8, "pit": 230.72}


def fit_part(x0, x1, n0, n1) -> dict:
    """Gate 2.2 on deviation rates (rate minus the season mean) of pairs at the floor."""
    x0, x1, n0, n1 = (np.asarray(a, dtype=float) for a in (x0, x1, n0, n1))
    hm = 2.0 / (1.0 / n0 + 1.0 / n1)
    r_raw = float(np.corrcoef(x0, x1)[0, 1])
    r = min(max(r_raw, R_CLAMP[0]), R_CLAMP[1])
    w = hm / hm.sum()
    m0 = float((w * x0).sum())
    m1 = float((w * x1).sum())
    tau2 = float((w * (x0 - m0) * (x1 - m1)).sum())
    hmm = float(hm.mean())
    K = hmm * (1.0 - r) / r
    return {"n_pairs": int(len(x0)), "r_raw": r_raw, "r": r, "hm": hmm, "K": K,
            "tau2": max(tau2, 0.0), "sigma2": K * max(tau2, 0.0)}


def rel(n, K):
    n = np.asarray(n, dtype=float)
    return n / (n + float(K))


def hitter_departures(n, rates: dict, means: dict, frozen: dict) -> dict:
    """{part: d_c} in runs, re-centred to zero per season over the given rows (gate 2.3).
    n: PA per row; rates[c]: runs per PA; means[c]: the season mean rate."""
    n = np.asarray(n, dtype=float)
    out = {}
    for c in HIT_PARTS:
        x = np.asarray(rates[c], dtype=float)
        g = -(1.0 - rel(n, frozen[c]["K"])) * n * (x - means[c])
        g = np.where(n > 0, g, 0.0)
        out[c] = g - n * (g.sum() / n.sum() if n.sum() > 0 else 0.0)
    return out


def pitcher_departure(n, ip, rates: dict, means: dict, frozen: dict, rpw: float) -> np.ndarray:
    """D per row in wins, re-centred per season on innings (gate 2.3)."""
    n = np.asarray(n, dtype=float)
    ip = np.asarray(ip, dtype=float)
    dq = {c: -(1.0 - rel(n, frozen[c]["K"])) * (np.asarray(rates[c], dtype=float) - means[c]) for c in PIT_PARTS}
    druns = -n * (13.0 * dq["HR"] + 3.0 * dq["BH"] - 2.0 * dq["K"]) / 9.0
    druns = np.where(n > 0, druns, 0.0)
    w = druns / float(rpw)
    return w - ip * (w.sum() / ip.sum() if ip.sum() > 0 else 0.0)


def hitter_band_sd(n, frozen: dict, rpw: float) -> np.ndarray:
    n = np.asarray(n, dtype=float)
    v = sum((1.0 - rel(n, frozen[c]["K"])) * frozen[c]["tau2"] for c in HIT_PARTS)
    return n * np.sqrt(v) / float(rpw)


def pitcher_band_sd(n, frozen: dict, rpw: float) -> np.ndarray:
    n = np.asarray(n, dtype=float)
    v = {c: (1.0 - rel(n, frozen[c]["K"])) * frozen[c]["tau2"] for c in PIT_PARTS}
    return (n / 9.0) * np.sqrt(169.0 * v["HR"] + 9.0 * v["BH"] + 4.0 * v["K"]) / float(rpw)


def predictive_sd(n0, n1, part: dict) -> np.ndarray:
    """Gate 3.2: sqrt((1 - rel) tau2 + sigma2 / n(Y+1)) for one part's rate."""
    n0 = np.asarray(n0, dtype=float)
    n1 = np.asarray(n1, dtype=float)
    return np.sqrt((1.0 - rel(n0, part["K"])) * part["tau2"] + part["sigma2"] / n1)


def posterior_mean_dev(n, x_dev, K):
    return rel(n, K) * np.asarray(x_dev, dtype=float)


MARGIN = 0.02


def disposition(holm_reject: bool, gap, lo95, hi95, lo90, hi90, b1_lo95, twin_lo95, v1_agrees: bool) -> str:
    """EBR_GATE.md part 9.5's precedence (B1 required for WIN (components); no transport)."""
    if holm_reject and v1_agrees and lo95 is not None and lo95 > 0 and gap is not None and gap >= MARGIN:
        if b1_lo95 is not None and b1_lo95 > 0 and twin_lo95 is not None and twin_lo95 <= 0:
            return "WIN (components)"
        return "WIN (regression only)"
    if holm_reject and v1_agrees and lo95 is not None and lo95 > 0 and gap is not None and gap < MARGIN:
        return "SMALL WIN"
    if hi95 is not None and hi95 < 0:
        return "LOSS"
    if lo90 is not None and hi90 is not None and lo90 >= -MARGIN and hi90 <= MARGIN:
        return "EQUIVALENT"
    return "UNRESOLVED"


def finite(x) -> bool:
    return x is not None and math.isfinite(x)
