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

WHAT THIS DOES NOT FIX, stated so the next reader does not assume it did. The
WEIGHTS are still the frozen 2013 set (`fa_config.yaml assembly.woba_weights`,
mirrored in hem_plus and wrc_rates), and a season-specific scale paired with
season-invariant weights is an improvement, not coherence. Pairing both to the
same season is the W1.0 lane. The residual after this repair is about 1.5 percent
and belongs to the separate league-divisor question (audit F01-04), which must NOT
ship with this one: the scale alone closes the measured width gap, and stacking
the divisor change on top would overshoot the column.

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


def _pa_by_player(season: int) -> dict[int, float]:
    """{mlbam: season PA}. The sabermetrics feed carries no PA, so it is joined
    from the hitting cache the same pipeline already writes."""
    out: dict[int, float] = {}
    path = CACHE_DIR / f"fa_statsapi_hitting_{int(season)}.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(rows, dict):
        rows = (rows.get("stats") or [{}])[0].get("splits") or []
    for r in rows or []:
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
    path = CACHE_DIR / f"statsapi_saber_hitting_{int(season)}.json"
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        splits = (blob["stats"][0].get("splits") or [])
    except (KeyError, IndexError, TypeError):
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
    return {"season": int(season), "n": n, "woba_scale": round(scale, 4),
            "lg_woba": round(-(my - slope * mx) * scale, 4), "r": round(r, 8),
            "source": "solved from statsapi sabermetrics woba + wRaa identity"}


def load() -> dict:
    """{season: block} from the committed artifact. {} when it is absent, which
    every caller must treat as "keep your own fallback"."""
    try:
        blob = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {int(k): v for k, v in (blob.get("seasons") or {}).items()}


def woba_scale(season: int, default: Optional[float] = None) -> Optional[float]:
    """The solved wOBA scale for `season`, else the nearest EARLIER solved season,
    else `default`.

    Nearest-earlier rather than nearest: a projection for a future season must not
    borrow a constant from a season that has not been played."""
    tbl = load()
    if not tbl:
        return default
    if season in tbl:
        return tbl[season].get("woba_scale", default)
    earlier = [s for s in tbl if s <= season]
    if not earlier:
        return default
    return tbl[max(earlier)].get("woba_scale", default)


def build(first: int = 2015, last: int = 2026, write: bool = False) -> dict:
    """Solve every season in range and optionally write the artifact."""
    seasons = {}
    for s in range(int(first), int(last) + 1):
        blk = solve_season(s)
        if blk:
            seasons[str(s)] = blk
    out = {
        "generated_at": None,
        "what_this_is": ("per-season league constants SOLVED from MLB's published "
                         "sabermetrics feed, not fitted and not typed"),
        "identity": "wRAA = ((wOBA - lgwOBA) / wOBAScale) * PA",
        "min_pa": MIN_PA, "min_rows": MIN_ROWS, "min_r": MIN_R,
        "not_fixed_here": ("the wOBA WEIGHTS are still the frozen 2013 set; a "
                           "season-specific scale on season-invariant weights is an "
                           "improvement, not coherence (W1.0 owns pairing them)"),
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
        print(f"{s}  scale {blk['woba_scale']:.4f}  lgwOBA {blk['lg_woba']:.4f}  "
              f"n {blk['n']:4d}  r {blk['r']:.8f}")
    if "--write" in sys.argv:
        print("wrote", OUT_PATH)
