# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""League-wide season stats from the MLB StatsAPI, cached to disk —
the historical level/rate source the local DB never had.

career_stats payloads only reach back to each player's graduation
window, so vintage-level reconstruction (which level was this prospect
at in 2018?) is impossible from local data for most of the pool. The
StatsAPI `/api/v1/stats` endpoint returns EVERY player's season line
per (sport, season, group) in one call, keyed by mlbam id — 7 sports ×
~12 seasons ≈ a few hundred cached requests for the entire affiliated
ladder 2014-present, league context included.

Consumers (model-audit Phase 4b):
  eta_backtest.py        vintage level + OPS/ERA for debuted players
  prospect_path.py       pre-debut MiLB rates + league norms (WS-7)
  arkmetric_forward_eval SC+/Stuff+ graduates' first MLB seasons
  overseas refit         MLB-side league OPS context

Cache: .cache/milb_stats/{group}_{sport}_{season}.json (gitignored,
fetched once, reused by every monthly rerun). Pure read-only consumer —
never touches the prospect DB.
"""

from __future__ import annotations

import json
import logging
import statistics
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache" / "milb_stats"
# Past-season milb caches are final and live forever; the CURRENT season refreshes once its
# cache file ages past this TTL so the eFV model's stats track in-season production instead
# of freezing on the season's first fetch (the bulk per-sport fetch is cheap).
_SEASON_TTL_SEC = 20 * 3600

BASE = "https://statsapi.mlb.com/api/v1/stats"
_UA = {"User-Agent": "Mozilla/5.0"}

# sportId -> platform level label. Pre-2021 short-season A (15) folds to
# A; rookie ball (16) splits DSL vs CPX by league name (Arizona / Gulf
# Coast / Pioneer / Appalachian complexes all map CPX, the post-2021
# convention eta.py documents).
SPORT_LEVEL = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A",
               15: "A", 16: "CPX"}
MINOR_SPORTS = (11, 12, 13, 14, 15, 16)
ALL_SPORTS = (1,) + MINOR_SPORTS
_LEVEL_RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5, "MLB": 6}


def _fetch(url: str) -> dict:
    import urllib.request
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _level16(league: str) -> str:
    """sportId-16 (rookie/complex) level by LEAGUE: DSL and VSL are the
    foreign (Latin American) complex leagues — a distinct, much
    lower-offense environment that must be normed on its own; everything
    else (GCL/AZL/ACL/FCL/PIO/APP) is US complex -> CPX. The cached MLB
    StatsAPI league name for the Dominican Summer League is literally
    'DSL' (not 'Dominican'), so the old `"Dominican" in league` substring
    check never fired and folded every DSL season into CPX — making DSL
    norms unavailable and mis-norming DSL-heavy (int'l-bat) prospects."""
    return "DSL" if (league or "").strip().upper() in ("DSL", "VSL") else "CPX"


def _relevel(rows: list[dict], sport_id: int) -> list[dict]:
    """Re-derive the sportId-16 level from the stored league name so the
    DSL/CPX split is correct even on rows CACHED before the fix (the lean
    row carries `league`, so we recompute `level` on read — no re-fetch)."""
    if sport_id == 16:
        for r in rows:
            r["level"] = _level16(r.get("league") or "")
    return rows


def season_splits(sport_id: int, season: int, group: str,
                  fetch: bool = True) -> list[dict]:
    """All player season lines for one (sport, season, group), cached.
    group: 'hitting' | 'pitching'. Returns [] when uncached and
    fetch=False (cache-only consumers stay offline-safe)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{group}_{sport_id}_{season}.json"
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            cached = None
    if cached is not None:
        import time as _time
        from datetime import date as _date
        # Current-season cache goes stale after the TTL so the MODEL re-pulls in-season
        # production; past seasons are final (cache forever). fetch=False consumers
        # (e.g. league_norms) always use the cache.
        stale = (fetch and season >= _date.today().year
                 and (_time.time() - path.stat().st_mtime) >= _SEASON_TTL_SEC)
        # SCHEMA MIGRATION, 2026-07-31. A hitting cache written before the wOBA
        # components were added carries the old lean shape, and past seasons cache
        # FOREVER, so a pure TTL would never heal them. Treat a component-less
        # hitting row as stale so the refetch happens once, per file, on whatever
        # box runs next. Self-healing beats a manual delete, because the deploy box
        # has its own cache and nobody would remember to clear it there.
        if not stale and fetch and group == "hitting" and cached:
            probe = next((r for r in cached if (r.get("pa") or 0)), None)
            if probe is not None and probe.get("h") is None:
                stale = True
                log.info("milb_stats: %s sport=%s season=%s predates the wOBA "
                         "components; refetching once", group, sport_id, season)
        if not stale:
            return _relevel(cached, sport_id)
    if not fetch:
        return _relevel(cached, sport_id) if cached is not None else []
    splits: list[dict] = []
    offset = 0
    while True:
        url = (f"{BASE}?stats=season&group={group}&season={season}"
               f"&sportIds={sport_id}&playerPool=ALL&limit=2000&offset={offset}")
        try:
            d = _fetch(url)
        except Exception as e:                                # noqa: BLE001
            log.warning("milb_stats fetch failed %s/%s/%s: %s",
                        group, sport_id, season, e)
            # transient failure -> keep the prior (stale) cache rather than empty
            return _relevel(cached, sport_id) if cached is not None else splits
        block = (d.get("stats") or [{}])[0]
        page = block.get("splits") or []
        splits.extend(page)
        total = block.get("totalSplits") or len(splits)
        offset += len(page)
        if not page or offset >= total:
            break
    # lean rows: identity + level + the rate/exposure fields we consume
    lean = []
    for s in splits:
        st = s.get("stat") or {}
        league = (s.get("league") or {}).get("name") or ""
        level = _level16(league) if sport_id == 16 else SPORT_LEVEL.get(sport_id, "?")
        row = {"mlbam": (s.get("player") or {}).get("id"),
               "name": (s.get("player") or {}).get("fullName"),
               "season": season, "level": level, "league": league,
               "age": st.get("age")}
        if group == "hitting":
            row.update({
                "pa": st.get("plateAppearances"), "ab": st.get("atBats"),
                "ops": st.get("ops"), "obp": st.get("obp"),
                "slg": st.get("slg"), "avg": st.get("avg"),
                "so": st.get("strikeOuts"), "bb": st.get("baseOnBalls"),
                "hr": st.get("homeRuns"),
                # wOBA COMPONENTS, added 2026-07-31. The same response already
                # carried every one of these and the lean row dropped them, which is
                # why wrc_rates.py had to read a separate .cache/milb_full_stats/
                # tree that NOTHING in this repo produces: one reader, no writer, and
                # already stale on 53.3% of rows. Keeping them here retires that
                # orphan and costs no extra request.
                #
                # These are COUNTS, not rates, so they are additive across the stint
                # rows the feed returns and cannot be reconstructed from ops/obp/slg.
                # 1B is derived (h - 2b - 3b - hr) rather than stored.
                "h": st.get("hits"), "doubles": st.get("doubles"),
                "triples": st.get("triples"), "ibb": st.get("intentionalWalks"),
                "hbp": st.get("hitByPitch"), "sf": st.get("sacFlies"),
                "sb": st.get("stolenBases"),
            })
        else:
            row.update({
                "ip": st.get("inningsPitched"), "bf": st.get("battersFaced"),
                "era": st.get("era"), "so": st.get("strikeOuts"),
                "bb": st.get("baseOnBalls"), "g": st.get("gamesPlayed"),
                "gs": st.get("gamesStarted"),
            })
        lean.append(row)
    if not lean and cached is not None:
        return _relevel(cached, sport_id)        # empty refetch -> keep prior cache
    path.write_text(json.dumps(lean, separators=(",", ":")), encoding="utf-8")
    log.info("milb_stats cached %s sport=%s season=%s: %d rows",
             group, sport_id, season, len(lean))
    return lean


def warm_cache(seasons: range, sports=ALL_SPORTS) -> None:
    for season in seasons:
        for sport in sports:
            for group in ("hitting", "pitching"):
                season_splits(sport, season, group)


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=64)
def player_index(season: int, group: str, fetch: bool = True) -> dict[int, list[dict]]:
    """{mlbam: [season rows across the ladder]} for one season+group."""
    out: dict[int, list[dict]] = {}
    for sport in ALL_SPORTS:
        for r in season_splits(sport, season, group, fetch=fetch):
            if r.get("mlbam"):
                out.setdefault(int(r["mlbam"]), []).append(r)
    return out


def highest_level(rows: list[dict], include_mlb: bool = False) -> str | None:
    best = None
    for r in rows:
        lv = r.get("level")
        if lv == "MLB" and not include_mlb:
            continue
        if lv in _LEVEL_RANK and (best is None or
                                  _LEVEL_RANK[lv] > _LEVEL_RANK[best]):
            best = lv
    return best


def level_row(rows: list[dict], level: str, group: str) -> dict | None:
    """The largest-exposure row at `level` (a player can repeat a level
    across two teams in one season)."""
    expo = "pa" if group == "hitting" else "bf"
    cands = [r for r in rows if r.get("level") == level]
    if not cands:
        return None
    return max(cands, key=lambda r: _f(r.get(expo)) or 0)


@lru_cache(maxsize=256)
def league_norms(season: int, level: str, group: str,
                 fetch: bool = True) -> dict | None:
    """Exposure-filtered league medians for rate translation: hitters
    {ops, obp, k_pct, bb_pct, iso}, pitchers {era, k_pct, bb_pct}. None when
    the level-season has too few qualifying lines."""
    rows: list[dict] = []
    for sport, lv in SPORT_LEVEL.items():
        if lv == level or (level in ("DSL", "CPX") and sport == 16):
            rows.extend(r for r in season_splits(sport, season, group, fetch=fetch)
                        if r.get("level") == level)
    vals: dict[str, list[float]] = {}
    n = 0
    for r in rows:
        if group == "hitting":
            pa = _f(r.get("pa")) or 0
            if pa < 100:
                continue
            n += 1
            ab, so, bb = _f(r.get("ab")), _f(r.get("so")), _f(r.get("bb"))
            slg, avg, ops = _f(r.get("slg")), _f(r.get("avg")), _f(r.get("ops"))
            obp = _f(r.get("obp"))
            if ops is not None:
                vals.setdefault("ops", []).append(ops)
            if obp is not None:
                vals.setdefault("obp", []).append(obp)
            if so is not None and pa:
                vals.setdefault("k_pct", []).append(so / pa)
            if bb is not None and pa:
                vals.setdefault("bb_pct", []).append(bb / pa)
            if slg is not None and avg is not None:
                vals.setdefault("iso", []).append(slg - avg)
        else:
            bf = _f(r.get("bf")) or 0
            if bf < 100:
                continue
            n += 1
            era, so, bb = _f(r.get("era")), _f(r.get("so")), _f(r.get("bb"))
            if era is not None:
                vals.setdefault("era", []).append(era)
            if so is not None and bf:
                vals.setdefault("k_pct", []).append(so / bf)
            if bb is not None and bf:
                vals.setdefault("bb_pct", []).append(bb / bf)
    if n < 30:
        return None
    out = {k: round(statistics.median(v), 4) for k, v in vals.items()} | {"n": n}
    # AUDIT FIX 2026-07-14: mid-season norms for the CURRENT season embed
    # seasonal/selection drift - five weeks into a DSL season only the
    # early-everyday regulars clear the 100-PA qualifier, so the "level
    # median" ran 0.06-0.10 OPS hot at the low levels (DSL .829 vs a stable
    # .70-.73 multi-year band) and every prospect's rel-rates read cool.
    # Stabilize by blending with the PRIOR season's full norm, weighted by
    # qualified count: w = n_cur / (n_cur + n_prior). Converges to the pure
    # current-season norm as the season fills in; past seasons never blend.
    from datetime import date as _date
    if season == _date.today().year:
        prior = league_norms(season - 1, level, group, fetch=False)
        if prior:
            n_prior = prior.get("n") or 0
            if n_prior > 0:
                w = n / (n + n_prior)
                blended = {}
                for k, v in out.items():
                    if k != "n" and prior.get(k) is not None:
                        blended[k] = round(w * v + (1 - w) * prior[k], 4)
                    elif k != "n":
                        blended[k] = v
                out = blended | {"n": n, "norm_prior_blend_w": round(w, 3)}
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    warm_cache(range(2014, 2027))
    print("AA hitting norms 2019:", league_norms(2019, "AA", "hitting"))
    print("AAA pitching norms 2023:", league_norms(2023, "AAA", "pitching"))
