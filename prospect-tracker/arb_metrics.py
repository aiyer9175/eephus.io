# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Per-player-season Arkmetric substrate for the arbitration panel.

WHY THIS EXISTS RATHER THAN A WIDER data/*_history.json
-------------------------------------------------------
The shipped history artifacts (data/hitter_history.json, starter_history.json,
bullpen_history.json) cover 2021-2025 only, and the arbitration backtest needs
2008-2026 (an 2011 arb season wants a trailing-3yr window, so the feature panel
starts three years before the label window).

The obvious move - widen HISTORY_SEASONS - was MEASURED and rejected. Those
files run about 152 KB per season on disk (hitter_history.json is 757.7 KB for
five seasons), so 27 seasons would ship a roughly 4 MB payload to browsers that
only ever render a season pill or two. The history tabs are a display surface;
the arbitration model is a fit-time consumer. They do not need the same artifact.

So the substrate is built HERE, lab-side, and memoized under .cache/arb_metrics/
rather than data/. Nothing about this module ships to the webroot.

OFFLINE BY CONSTRUCTION
-----------------------
Everything reads .cache/fa_statsapi_{hitting,pitching}_YYYY.json, which exist for
2000-2026 (27 seasons each, verified on disk). The three metric modules are pure
score_pool functions. Verified offline with sockets hard-blocked: 2008 tops at
Albert Pujols HEM+ 161, 2011 Jose Bautista 174, 2015 Bryce Harper 180, 2026
Yordan Alvarez 165.

A season's cached line NEVER changes once the season is complete, so the memo
files are permanent for past seasons. The in-progress season is re-derived on
every call (see _is_final).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

_log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache" / "arb_metrics"

# Schema version. Bump to invalidate every memo file at once.
SCHEMA = 2

# The panel window. Labels run 2011-2026; features start three seasons earlier
# so a 2011 arb row has a full trailing-3yr window.
FIRST_FEATURE_SEASON = 2008
LAST_SEASON = 2026


def _is_final(season: int) -> bool:
    """A completed season's stat line is frozen, so its memo is permanent.
    The in-progress season is not memoized."""
    return int(season) < date.today().year


def _memo_path(season: int) -> Path:
    return CACHE_DIR / f"s{int(season)}_v{SCHEMA}.json"


def _score_hitters(season: int) -> tuple[dict[int, dict], bool]:
    """({mlbam: hitter metric block}, source_loaded) for one season.

    The bool is whether the SOURCE rows loaded, not whether the block is
    non-empty. season_metrics refuses to memoize a season whose source did not
    load, which is the defect this signature exists to prevent: an early run
    with the network blocked scored hitters, failed pitchers, and wrote a
    hitters-only memo that every later run then trusted.
    """
    import hem_plus
    import hitter_export
    rows = hitter_export.load_season_hitting(season)
    if not rows:
        return {}, False
    scored = hem_plus.score_pool(hitter_export.build_hitters(rows))
    out: dict[int, dict] = {}
    for h in scored.get("hitters") or []:
        mlbam = h.get("mlbam")
        if not mlbam:
            continue
        out[int(mlbam)] = {
            "hem": _r(h.get("hem_plus")),
            "pa": _i(h.get("pa")),
            "woba": _r(h.get("woba"), 4),
            "ops": _r(h.get("ops"), 4),
            "iso": _r(h.get("iso"), 4),
            "bb_pct": _r(h.get("bb_pct"), 4),
            "k_pct": _r(h.get("k_pct"), 4),
            # Counting stats. NOT champion features - arbitration panels reward
            # them and nothing in this pipeline projects them forward, so they
            # feed the DIAGNOSTIC ceiling model only. See docs/ARBITRATION_GATE.
            "hr": _i(h.get("hr")),
            "sb": _i(h.get("sb")),
            "qual": bool(h.get("qualified")),
        }
    return out, True


def _score_pitchers(season: int) -> tuple[dict[int, dict], bool]:
    """{mlbam: pitcher metric block} for one season, both roles.

    SEM+ and REM+ are pool-relative within their own role, so a pitcher is
    scored on whichever pool he belongs to and may carry both in a swing
    season. Leverage is passed empty: gmLI needs .cache/win_prob, which only
    covers 2018+, and REM+ deliberately holds leverage OUT of the talent
    number anyway (it is deployment, not skill - the two-number design).
    """
    import bullpen_export
    import fa_sources
    import rem_plus
    import sem_plus
    import starter_export
    # NOT bullpen_export.load_season_pitching: that one is a LIVE StatsAPI call
    # (the hitter analog is disk-cached, the pitcher analog is not). Go through
    # the cached fetcher and reuse the exporter's own row mapping so the field
    # names cannot drift apart.
    splits = fa_sources.fetch_statsapi_season_stats(int(season), "pitching")
    rows = bullpen_export.rows_from_pitching_splits(splits, int(season))
    if not rows:
        return {}, False
    out: dict[int, dict] = {}
    try:
        starters = starter_export.build_starters(rows)
        for s in sem_plus.score_pool(starters).get("starters") or []:
            mlbam = s.get("mlbam")
            if not mlbam:
                continue
            out.setdefault(int(mlbam), {}).update({
                "sem": _r(s.get("sem_plus")),
                "gs": _i(s.get("gs")),
                "ip_sp": _r(s.get("ip"), 1),
            })
    except Exception as exc:                    # pragma: no cover - defensive
        _log.warning("arb_metrics: starter scoring failed for %s: %s", season, exc)
    try:
        relievers = bullpen_export.build_relievers(rows, leverage={})
        for r in rem_plus.score_pool(relievers).get("relievers") or []:
            mlbam = r.get("mlbam")
            if not mlbam:
                continue
            out.setdefault(int(mlbam), {}).update({
                "rem": _r(r.get("rem_plus")),
                "ip_rp": _r(r.get("ip"), 1),
                # Saves and holds are the classic arbitration currency for a
                # reliever. Diagnostic-only, same rule as hr/sb above.
                # NB the scored keys are "saves"/"holds", not "sv"/"hld" - the
                # short names silently read None and zeroed the whole column.
                "sv": _i(r.get("saves")),
                "hld": _i(r.get("holds")),
            })
    except Exception as exc:                    # pragma: no cover - defensive
        _log.warning("arb_metrics: reliever scoring failed for %s: %s", season, exc)
    return out, True


def _r(v, nd: int = 1):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def season_metrics(season: int, *, force: bool = False) -> dict[int, dict]:
    """{mlbam: {hem, sem, rem, pa, ip_sp, ip_rp, ...}} for one season.

    Memoized under .cache/arb_metrics/ for completed seasons. Returns {} when
    the StatsAPI cache is cold for that season rather than reaching out - this
    module is offline by construction and a caller that needs a cold season
    should warm .cache/fa_statsapi_* first.
    """
    season = int(season)
    path = _memo_path(season)
    if not force and _is_final(season) and path.exists():
        try:
            return {int(k): v for k, v in json.loads(path.read_text("utf-8")).items()}
        except (OSError, ValueError):
            _log.warning("arb_metrics: unreadable memo %s; rebuilding", path.name)

    merged: dict[int, dict] = {}
    complete = True
    for block, ok in (_score_hitters(season), _score_pitchers(season)):
        complete = complete and ok
        for mlbam, vals in block.items():
            merged.setdefault(mlbam, {}).update(vals)

    # A season is memoized only when BOTH sides loaded. A partial season that
    # gets written once is trusted forever, and a hitters-only panel would have
    # silently dropped every pitcher from the arbitration model.
    if not complete:
        _log.warning("arb_metrics: %s incomplete (one side did not load); not memoizing",
                     season)
    if merged and complete and _is_final(season):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({str(k): v for k, v in merged.items()},
                                      separators=(",", ":")), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:                  # pragma: no cover - defensive
            _log.warning("arb_metrics: could not memoize %s: %s", season, exc)
    return merged


def metric_panel(first: int = FIRST_FEATURE_SEASON,
                 last: int = LAST_SEASON,
                 *, force: bool = False, log=None) -> dict[int, dict[int, dict]]:
    """{season: {mlbam: metric block}} across the window. Seasons whose cache is
    cold are SKIPPED and reported, never silently zero-filled."""
    out: dict[int, dict[int, dict]] = {}
    missing: list[int] = []
    for y in range(int(first), int(last) + 1):
        block = season_metrics(y, force=force)
        if block:
            out[y] = block
        else:
            missing.append(y)
        if log:
            log(f"  arb_metrics: {y} -> {len(block)} players")
    if missing and log:
        log(f"  arb_metrics: NO DATA for {missing} (cold StatsAPI cache)")
    return out


def trailing(panel: dict[int, dict[int, dict]], mlbam: int, season: int,
             key: str, n: int = 3) -> float | None:
    """Playing-time-weighted mean of `key` over the n seasons ENDING at
    `season` inclusive. None when the player has no weighted exposure.

    Weight is PA for hitter metrics and innings for pitcher metrics, so a
    41-inning swing season cannot outvote a 200-inning one. Seasons the player
    missed contribute nothing rather than a zero, because an absent season is
    unobserved, not a bad performance.
    """
    wsum = 0.0
    vsum = 0.0
    for y in range(int(season) - int(n) + 1, int(season) + 1):
        row = (panel.get(y) or {}).get(int(mlbam))
        if not row:
            continue
        val = row.get(key)
        if val is None:
            continue
        if key == "hem":
            w = row.get("pa") or 0
        elif key == "sem":
            w = row.get("ip_sp") or 0
        elif key == "rem":
            w = row.get("ip_rp") or 0
        else:
            w = 1
        if not w:
            continue
        wsum += float(w)
        vsum += float(val) * float(w)
    return round(vsum / wsum, 2) if wsum else None
