# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Per-season league constants, SOLVED rather than typed.

WHY THIS MODULE EXISTS (audit F01-03, 2026-09-10, and the first piece of the
league-constants table the FanGraphs-frame plan calls for in W1.0).

Four modules carried four private copies of the wOBA machinery and one of them,
`fa_config.yaml assembly.woba_scale`, was pinned at 1.15 for every season from
2000 to 2026. The reference says the opposite in as many words: "the exact wOBA
scale value varies on a year-to-year basis in order to set wOBA on the same scale
as league-average OBP". Measured, 1.15 is 7.2 percent low against 2026, and the
served projected wRC+ column was that much too wide on 3,205 rows, 748 of them off
by 3 or more points and the worst by 10.2.

THE SCALE IS NOT A FITTED PARAMETER. It is recoverable EXACTLY from MLB's own
sabermetrics feed, which publishes `woba` and `wRaa` per player. Those two satisfy

    wRAA = ((wOBA - lgwOBA) / wOBAScale) * PA

so regressing wRaa/PA on wOBA returns slope 1/scale and intercept -lgwOBA/scale.
Measured r over six seasons: 1.00000000, 1.00000000, 1.00000000, 1.00000000,
0.99999998, 0.99998231. That is an identity being read back, not a model being
estimated, which is why this module SOLVES and does not fit.

    season  scale   lgwOBA
    2021    1.2086  0.3144
    2022    1.2588  0.3097
    2023    1.2041  0.3184
    2024    1.2425  0.3102
    2025    1.2317  0.3131
    2026    1.2400  0.3164

THE WEIGHTS ARE SOLVABLE THE SAME WAY (W1.0, 2026-09-11). The feed's `woba` is
published to six decimals, and wOBA is by definition

    wOBA = (wBB*uBB + wHBP*HBP + w1B*1B + w2B*2B + w3B*3B + wHR*HR) / (AB + BB - IBB + SF + HBP)

so wOBA times the denominator is linear in six counts with the six weights as the
only unknowns. Solved per season, 2011 through 2025 reproduce the published Guts
weights to the third decimal on every weight, the largest residual on any kept
row being 0.0004 wOBA-points-times-PA, which is the six-decimal rounding. The one
wrinkle is vintage: in a season still being played, the counting-stat cache and the
sabermetrics cache are fetched minutes apart and a player who batted in between no
longer satisfies the identity. Those rows are trimmed, never averaged in, and the
solve refuses rather than serves if the kept rows do not fit exactly.

THE LEAGUE TOTALS carry the rest of the frame's per-season constants, each checked
against the Guts table to its printed precision for 2011 through 2025:
runs per win (FanGraphs' closed form 9*(R/IP)*1.5 + 3), the FIP constant
(league ERA minus the FIP numerator per inning, walks INCLUDING intentional ones,
which is the only reading that reproduces the table), runs per caught stealing
(-(2*R/outs + 0.075)), runs per stolen base (0.2 by convention), and R/PA.

SERVED VERSUS SOLVED. The artifact now carries every solvable season, but
`woba_scale()` reads only seasons from `SERVED_FROM` on, which is where the
served table started when the scale repair shipped. Letting 2015 through 2020
reach the projection corpus is correct (those seasons still read 1.15 today, so
the corpus mixes two scales) but it moves served projections, so it is a measured
change of its own and not a side effect of adding columns.

WHAT THIS DOES NOT FIX, stated so the next reader does not assume it did. The
weights are now SOLVED here but no consumer reads them yet: fa_config.yaml,
hem_plus and wrc_rates still carry the frozen 2013 set, and pointing them here is
the consumer half of W1.0. The residual after the scale repair is about 1.5
percent and belongs to the separate league-divisor question (audit F01-04), which
must NOT ship with it: the scale alone closes the measured width gap, and
stacking the divisor change on top would overshoot the column.

The solved values land in data/league_constants.json so a consumer reads one
artifact rather than re-solving, and so the numbers are reviewable.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache"
OUT_PATH = ROOT / "data" / "league_constants.json"

#: Minimum plate appearances for a row to enter the solve. The identity holds on
#: every row; thin rows are dropped only because a rounded published wOBA carries
#: proportionally more noise there.
MIN_PA = 50.0

#: Below this many usable rows the season is not solvable and the caller keeps its
#: own fallback rather than being handed a number built from nothing.
MIN_ROWS = 30

#: The identity must come back essentially exact. Anything below this means the
#: feed changed shape or the join is wrong, and a silent bad constant is worse
#: than no constant.
MIN_R = 0.999

#: The first season a consumer reads through `woba_scale()`. The served table
#: began here when the scale repair shipped; earlier seasons are solved and
#: published in the artifact but reach no consumer until that move is measured.
SERVED_FROM = 2021

#: The six wOBA events in the order the weights are solved and published.
WEIGHT_KEYS = ("ubb", "hbp", "1b", "2b", "3b", "hr")

#: A kept row must satisfy the weight identity to within this many
#: wOBA-points-times-PA. Six-decimal rounding leaves about 0.0004 at 600 PA; one
#: plate appearance of vintage drift leaves about 0.7. The gap is three orders of
#: magnitude, so the threshold does not need tuning.
WEIGHT_TOL = 0.01

#: FanGraphs convention, not solved: a stolen base is worth 0.2 runs every season.
RUN_SB = 0.2


def _season_rows(kind: str, season: int) -> list:
    """The per-player season rows of one cached StatsAPI season file, [] when the
    file is absent or unreadable."""
    path = CACHE_DIR / f"fa_statsapi_{kind}_{int(season)}.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(rows, dict):
        rows = (rows.get("stats") or [{}])[0].get("splits") or []
    return rows or []


def _saber_rows(season: int) -> list:
    path = CACHE_DIR / f"statsapi_saber_hitting_{int(season)}.json"
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        return blob["stats"][0].get("splits") or []
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return []


def _pa_by_player(season: int) -> dict[int, float]:
    """{mlbam: season PA}. The sabermetrics feed carries no PA, so it is joined
    from the hitting cache the same pipeline already writes."""
    out: dict[int, float] = {}
    rows = _season_rows("hitting", season)
    for r in rows:
        pid = (r.get("player") or {}).get("id")
        if pid is None:
            continue
        try:
            out[int(pid)] = out.get(int(pid), 0.0) + float(
                (r.get("stat") or {}).get("plateAppearances") or 0)
        except (TypeError, ValueError):
            continue
    return out


def solve_season(season: int) -> Optional[dict]:
    """Solve (wOBA scale, league wOBA) for one season, or None if unsolvable.

    Multi-stint rows are dropped rather than summed: the feed publishes a rate
    per stint and a PA total per player, so mixing them would pair a partial rate
    with a whole-season denominator. `numTeams` is the feed's own marker for it."""
    splits = _saber_rows(season)
    if not splits:
        return None
    pam = _pa_by_player(season)
    xs: list[float] = []
    ys: list[float] = []
    for r in splits:
        try:
            if int(r.get("numTeams") or 1) != 1:
                continue
        except (TypeError, ValueError):
            continue
        pid = (r.get("player") or {}).get("id")
        st = r.get("stat") or {}
        try:
            w = float(st["woba"])
            wr = float(st["wRaa"])
        except (KeyError, TypeError, ValueError):
            continue
        pa = pam.get(int(pid)) if pid is not None else None
        if not pa or pa < MIN_PA:
            continue
        xs.append(w)
        ys.append(wr / pa)
    n = len(xs)
    if n < MIN_ROWS:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    slope = sxy / sxx
    if slope <= 0:
        return None
    r = sxy / ((sxx * syy) ** 0.5)
    if r < MIN_R:
        _log.warning("league constants %s: identity came back at r=%.6f, below "
                     "%.3f; refusing the solve rather than serving it", season, r, MIN_R)
        return None
    scale = 1.0 / slope
    blk = {"season": int(season), "n": n, "woba_scale": round(scale, 4),
           "lg_woba": round(-(my - slope * mx) * scale, 4), "r": round(r, 8),
           "source": "solved from statsapi sabermetrics woba + wRaa identity"}
    w = solve_weights(season)
    if w:
        blk.update(w)
    t = league_totals(season)
    if t:
        blk.update(t)
    return blk


def _woba_counts(st: dict) -> Optional[tuple[list[float], float]]:
    """([uBB, HBP, 1B, 2B, 3B, HR], wOBA denominator) from one hitting stat row."""
    def f(k):
        return float(st.get(k) or 0)
    try:
        bb, ibb, hbp = f("baseOnBalls"), f("intentionalWalks"), f("hitByPitch")
        h, d, t, hr = f("hits"), f("doubles"), f("triples"), f("homeRuns")
        ab, sf = f("atBats"), f("sacFlies")
    except (TypeError, ValueError):
        return None
    return [bb - ibb, hbp, h - d - t - hr, d, t, hr], ab + bb - ibb + sf + hbp


def solve_weights(season: int) -> Optional[dict]:
    """Solve the six wOBA weights for one season from the definitional identity,
    or None when the season does not solve exactly.

    Joins the sabermetrics `woba` to the counting-stat row for the same player,
    single-team seasons only (a stint rate against a season count is a different
    quantity). Rows that no longer satisfy the identity because the two caches
    were fetched at different moments of a live season are trimmed iteratively,
    starting loose and tightening to WEIGHT_TOL, and the solve refuses unless every
    kept row fits to WEIGHT_TOL."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a hard dependency elsewhere
        return None
    hit: dict = {}
    seen: dict = {}
    for r in _season_rows("hitting", season):
        pid = (r.get("player") or {}).get("id")
        if pid is None:
            continue
        seen[pid] = seen.get(pid, 0) + 1
        hit[pid] = r.get("stat") or {}
    xs, ys = [], []
    for r in _saber_rows(season):
        try:
            if int(r.get("numTeams") or 1) != 1:
                continue
        except (TypeError, ValueError):
            continue
        pid = (r.get("player") or {}).get("id")
        if seen.get(pid) != 1:
            continue
        w = (r.get("stat") or {}).get("woba")
        got = _woba_counts(hit.get(pid) or {})
        if w is None or got is None:
            continue
        counts, den = got
        if den < MIN_PA:
            continue
        try:
            ys.append(float(w) * den)
        except (TypeError, ValueError):
            continue
        xs.append(counts)
    if len(ys) < MIN_ROWS:
        return None
    X = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    keep = np.ones(len(y), dtype=bool)
    b = None
    for _ in range(25):
        b = np.linalg.lstsq(X[keep], y[keep], rcond=None)[0]
        resid = np.abs(y - X @ b)
        thr = max(WEIGHT_TOL, float(np.median(resid[keep])))
        nxt = resid <= thr
        if nxt.sum() < MIN_ROWS:
            return None
        if (nxt == keep).all():
            break
        keep = nxt
    resid = np.abs(y - X @ b)
    if int(keep.sum()) < MIN_ROWS or float(resid[keep].max()) > WEIGHT_TOL:
        _log.warning("league constants %s: wOBA weights did not solve exactly "
                     "(kept %d, worst %.4f); refusing", season, int(keep.sum()),
                     float(resid[keep].max()))
        return None
    return {"woba_weights": {k: round(float(v), 4) for k, v in zip(WEIGHT_KEYS, b)},
            "weights_rows": int(keep.sum()), "weights_rows_trimmed": int((~keep).sum()),
            "weights_worst_residual": round(float(resid[keep].max()), 5)}


def league_totals(season: int) -> Optional[dict]:
    """League run environment for one season from the per-player season caches.

    Rows are one per player (a traded player's row is his season total), so the
    league total is the plain sum; checked against the Guts table, the sums
    reproduce R/PA, runs per win, the FIP constant and runCS to the printed digit
    for every complete season 2011 through 2025."""
    prow = _season_rows("pitching", season)
    hrow = _season_rows("hitting", season)
    if not prow or not hrow:
        return None
    pk = ("runs", "earnedRuns", "outs", "homeRuns", "baseOnBalls", "hitByPitch",
          "strikeOuts", "battersFaced")
    hk = ("stolenBases", "caughtStealing", "hits", "doubles", "triples", "homeRuns",
          "baseOnBalls", "intentionalWalks", "hitByPitch", "plateAppearances")
    P = {k: 0.0 for k in pk}
    H = {k: 0.0 for k in hk}
    for rows, keys, acc in ((prow, pk, P), (hrow, hk, H)):
        for r in rows:
            st = r.get("stat") or {}
            for k in keys:
                try:
                    acc[k] += float(st.get(k) or 0)
                except (TypeError, ValueError):
                    continue
    if P["outs"] <= 0 or P["battersFaced"] <= 0:
        return None
    ip = P["outs"] / 3.0
    r_ip = P["runs"] / ip
    era = 9.0 * P["earnedRuns"] / ip
    fip_num = (13.0 * P["homeRuns"] + 3.0 * (P["baseOnBalls"] + P["hitByPitch"])
               - 2.0 * P["strikeOuts"]) / ip
    run_cs = -(2.0 * P["runs"] / P["outs"] + 0.075)
    singles = H["hits"] - H["doubles"] - H["triples"] - H["homeRuns"]
    wsb_den = singles + H["baseOnBalls"] + H["hitByPitch"] - H["intentionalWalks"]
    lg_wsb = ((H["stolenBases"] * RUN_SB + H["caughtStealing"] * run_cs) / wsb_den
              if wsb_den > 0 else None)
    return {"lg_r_pa": round(P["runs"] / P["battersFaced"], 5),
            "lg_ra9": round(9.0 * r_ip, 4), "lg_era": round(era, 4),
            "rpw": round(9.0 * r_ip * 1.5 + 3.0, 4),
            "fip_constant": round(era - fip_num, 4),
            "run_sb": RUN_SB, "run_cs": round(run_cs, 4),
            "lg_wsb": None if lg_wsb is None else round(lg_wsb, 5),
            "lg_runs": int(P["runs"]), "lg_pa": int(P["battersFaced"]),
            "lg_ip": round(ip, 1)}


def load() -> dict:
    """{season: block} from the committed artifact. {} when it is absent, which
    every caller must treat as "keep your own fallback"."""
    try:
        blob = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {int(k): v for k, v in (blob.get("seasons") or {}).items()}


def served() -> dict:
    """The seasons a consumer may read: the artifact from SERVED_FROM on."""
    return {s: v for s, v in load().items() if s >= SERVED_FROM}


def constants(season: int) -> Optional[dict]:
    """The solved block for `season`, else the nearest EARLIER served season,
    else None. Same nearest-earlier rule as `woba_scale`."""
    tbl = served()
    if season in tbl:
        return tbl[season]
    earlier = [s for s in tbl if s <= season]
    return tbl[max(earlier)] if earlier else None


def woba_scale(season: int, default: Optional[float] = None) -> Optional[float]:
    """The solved wOBA scale for `season`, else the nearest EARLIER solved season,
    else `default`.

    Nearest-earlier rather than nearest: a projection for a future season must not
    borrow a constant from a season that has not been played."""
    blk = constants(season)
    if not blk:
        return default
    return blk.get("woba_scale", default)


def build(first: int = 2011, last: int = 2026, write: bool = False) -> dict:
    """Solve every season in range and optionally write the artifact."""
    seasons = {}
    for s in range(int(first), int(last) + 1):
        blk = solve_season(s)
        if blk:
            seasons[str(s)] = blk
    out = {
        "generated_at": None,
        "what_this_is": ("per-season league constants SOLVED from MLB's published "
                         "sabermetrics feed and season totals, not fitted and not typed"),
        "identity": "wRAA = ((wOBA - lgwOBA) / wOBAScale) * PA",
        "weights_identity": ("wOBA * (AB + BB - IBB + SF + HBP) = "
                             "wBB*uBB + wHBP*HBP + w1B*1B + w2B*2B + w3B*3B + wHR*HR"),
        "totals": ("rpw = 9*(R/IP)*1.5 + 3; fip_constant = lgERA - "
                   "(13*HR + 3*(BB+HBP) - 2*K)/IP with BB including IBB; "
                   "run_cs = -(2*R/outs + 0.075); run_sb = 0.2 by convention"),
        "min_pa": MIN_PA, "min_rows": MIN_ROWS, "min_r": MIN_R,
        "weight_tol": WEIGHT_TOL, "served_from": SERVED_FROM,
        "not_fixed_here": ("the weights are solved here but no consumer reads them "
                           "yet; fa_config, hem_plus and wrc_rates still carry the "
                           "frozen 2013 set (the consumer half of W1.0)"),
        "seasons": seasons,
    }
    if write:
        from datetime import datetime, timezone
        out["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        OUT_PATH.write_text(json.dumps(out, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    import sys
    res = build(write="--write" in sys.argv)
    for s, blk in sorted(res["seasons"].items()):
        w = blk.get("woba_weights") or {}
        print(f"{s}  scale {blk['woba_scale']:.4f}  lgwOBA {blk['lg_woba']:.4f}  "
              f"n {blk['n']:4d}  r {blk['r']:.8f}  "
              + " ".join(f"{k}={w[k]:.3f}" for k in WEIGHT_KEYS if k in w)
              + f"  rpw {blk.get('rpw')}  cFIP {blk.get('fip_constant')}  "
              f"runCS {blk.get('run_cs')}")
    if "--write" in sys.argv:
        print("wrote", OUT_PATH)
