# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""S-XLINE: Statcast measurement upgrade for AAA stat lines feeding eFV.

Mechanism (pre-registered in docs/efv-2026-07-23/GATES.md): for AAA seasons
2023+ where the player has a qualified Savant minors aggregate row, blend the
expected-stat gap into the actual line BEFORE the level-relative feature
conversion in efv_dataset._season_rates. The correction is the (expected -
actual) gap measured WITHIN Savant, applied as a delta to the StatsAPI line,
so any cross-source level mismatch cancels by construction.

  hitters : avg/obp/slg each get + W * (x_stat - stat)_savant; ops = obp' + slg'
  pitchers: era gets a bounded multiplicative luck correction from the
            xwOBA-against relative gap: era' = era * clamp(1 + W * gap_rel)

Validated measurement clause (2026-07-23, scripts in the session scratchpad):
next-season prediction of the same stat family improves with the blend -
hitters delta rho +0.0253 CI95 [+0.0046, +0.0449] P=.991 (n=776 AAA season
pairs); pitchers xSLG-against arm +0.0511 CI95 [+0.0115, +0.0907] P=.996
(n=491). Raw EV / barrel forward features anti-correlate and are NOT used.

Rows with no coverage are byte-identical to the unadjusted path (the no-harm
gate's invariance clause). Pre-2023 seasons and non-AAA levels never adjust:
public MiLB Statcast exists only where Hawk-Eye is installed, which is AAA
parks (2023+). If MLB extends tracking to AA, coverage extends automatically
through the same season/level key with zero redesign.

Flags: default-off module constants, overridable per side by env vars
EEPHUS_XLINE_HIT / EEPHUS_XLINE_PIT ("1"/"0") read at call time so the gate
lab can toggle within one process. Flip the defaults only on gate PASS.
"""
from __future__ import annotations

import os
from functools import lru_cache

W_HIT = 0.7      # W-XLINE-W gate PASS 2026-07-24 (independently verified): M' lo95 +0.0056, point(0.7)>=point(0.5); in-matrix no-harm +0.0
W_PIT = 0.5
XLINE_HIT_DEFAULT = True    # S-XLINE gate PASS 2026-07-23: clauses M+1+2+3 (66 rows, delta 0.0)
XLINE_PIT_DEFAULT = True    # S-XLINE gate PASS 2026-07-23: clauses M+1+2+3 (68 rows, delta 0.0)
MIN_SAVANT_PA = 100         # matches the measurement study's qualification floor
FIRST_TRACKED_SEASON = 2023
ERA_MULT_LO, ERA_MULT_HI = 0.75, 1.25
# AMENDMENT 2026-07-23 (documented in GATES.md): fixed measurement-sanity caps
# on the per-stat expected-actual gaps. One post-flip breach (a .199 SLG gap on
# 174 PA moving a served grade -3.3, past the registered 3.0 bound) triggered
# the registered retract; the caps bound how hard a single partial-season gap
# can move a served grade. Round a-priori values, not tuned to any metric.
D_CAP_AVG, D_CAP_OBP, D_CAP_SLG = 0.050, 0.050, 0.100

# W-XISO (efv-2026-07-24 gate, Phase 1c): an optional FOURTH capped hitter
# delta measuring expected-power surplus - d_iso = w * cap(x_iso_gap, D_CAP_ISO)
# where x_iso = xSLG - xBA and x_iso_gap = x_iso - iso, all measured WITHIN the
# Savant aggregate so the cross-source cancellation of the other three deltas is
# preserved. Added to the (already de-lucked) SLG so ISO/SLG/OPS move together.
# Default OFF; wave-D flips XISO_HIT_DEFAULT only on gate PASS.
XISO_HIT_DEFAULT = True     # W-XISO gate PASS 2026-07-24 (independently verified): M lo95 +0.0154, p~1.0; no-harm +0.0
D_CAP_ISO = 0.060           # a-priori round cap (GATES.md W-XISO registration)


def _cap(v, cap):
    return max(-cap, min(cap, v))


def _flag(side: str) -> bool:
    env = os.environ.get("EEPHUS_XLINE_PIT" if side == "pit" else "EEPHUS_XLINE_HIT")
    if env is not None:
        return env.strip() == "1"
    return XLINE_PIT_DEFAULT if side == "pit" else XLINE_HIT_DEFAULT


def _w_hit() -> float:
    """Hitter blend weight, overridable at call time by EEPHUS_XLINE_WHIT so
    the gate lab can re-read the measurement/matrix at w=0.7 in one process
    (W-XLINE-W arm). Default is the module constant W_HIT (0.5)."""
    env = os.environ.get("EEPHUS_XLINE_WHIT")
    if env is not None:
        try:
            v = float(env)
            if v == v:
                return v
        except (TypeError, ValueError):
            pass
    return W_HIT


def _xiso_on() -> bool:
    """W-XISO fourth-delta toggle, overridable by EEPHUS_XLINE_XISO ("1"/"0").
    Default XISO_HIT_DEFAULT (OFF); wave-D flips it only on gate PASS."""
    env = os.environ.get("EEPHUS_XLINE_XISO")
    if env is not None:
        return env.strip() == "1"
    return XISO_HIT_DEFAULT


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


@lru_cache(maxsize=16)
def _gap_index(season: int, side: str) -> dict:
    """{mlbam: gap dict} for one AAA season from the cached Savant minors
    aggregates (offline; empty dict when the cache is absent)."""
    try:
        import arkmetric_forward_eval as af
        rows = af.savant_rows(season, "pitcher" if side == "pit" else "batter",
                              fetch=False)
    except Exception:
        return {}
    out = {}
    for r in rows:
        mid = _f(r.get("player_id"))
        pa = _f(r.get("pa")) or 0.0
        if mid is None or pa < MIN_SAVANT_PA:
            continue
        if side == "pit":
            woba, xwoba = _f(r.get("woba")), _f(r.get("xwoba"))
            if woba is None or xwoba is None or woba <= 0.0:
                continue
            out[int(mid)] = {"gap_rel_woba": (xwoba - woba) / max(woba, 0.200)}
        else:
            ba, xba = _f(r.get("ba")), _f(r.get("xba"))
            obp, xobp = _f(r.get("obp")), _f(r.get("xobp"))
            slg, xslg = _f(r.get("slg")), _f(r.get("xslg"))
            if None in (ba, xba, obp, xobp, slg, xslg):
                continue
            out[int(mid)] = {"d_avg": xba - ba, "d_obp": xobp - obp,
                             "d_slg": xslg - slg,
                             "d_iso_gap": (xslg - xba) - (slg - ba)}
    return out


def maybe_adjust_row(row, mlbam, season, level, side: str):
    """Return `row` unchanged, or an adjusted shallow copy when the S-XLINE
    blend applies (flag on, AAA, tracked season, qualified coverage).

    Adjusted copies also carry "_xline_note": a small ANNOTATION dict recording
    what the blend applied (post-cap deltas / clamped era multiplier), so the
    explainer surfaces can show covered players that their line was measured,
    not silently rewritten. _season_rates reads named stat keys only, so the
    note never touches a feature; it is display metadata, zero model effect.
    """
    if level != "AAA" or not season or int(season) < FIRST_TRACKED_SEASON:
        return row
    if not mlbam or not _flag("pit" if side == "pit" else "hit"):
        return row
    gaps = _gap_index(int(season), side).get(int(mlbam))
    if not gaps:
        return row
    adj = dict(row)
    if side == "pit":
        era = _f(row.get("era"))
        if era is None:
            return row
        mult = 1.0 + W_PIT * gaps["gap_rel_woba"]
        mult = min(ERA_MULT_HI, max(ERA_MULT_LO, mult))
        adj["era"] = era * mult
        adj["_xline_note"] = {"side": "pit", "season": int(season),
                              "era_mult": round(mult, 3)}
        return adj
    avg, obp, slg = _f(row.get("avg")), _f(row.get("obp")), _f(row.get("slg"))
    if None in (avg, obp, slg):
        return row
    w = _w_hit()
    d_avg = w * _cap(gaps["d_avg"], D_CAP_AVG)
    d_obp = w * _cap(gaps["d_obp"], D_CAP_OBP)
    d_slg = w * _cap(gaps["d_slg"], D_CAP_SLG)
    adj["avg"] = avg + d_avg
    adj["obp"] = obp + d_obp
    adj["slg"] = slg + d_slg
    note = {"side": "hit", "season": int(season),
            "d_avg": round(d_avg, 3), "d_obp": round(d_obp, 3),
            "d_slg": round(d_slg, 3)}
    if _xiso_on() and gaps.get("d_iso_gap") is not None:
        d_iso = w * _cap(gaps["d_iso_gap"], D_CAP_ISO)
        adj["slg"] = adj["slg"] + d_iso
        note["d_iso"] = round(d_iso, 3)
    adj["ops"] = adj["obp"] + adj["slg"]
    adj["_xline_note"] = note
    return adj
