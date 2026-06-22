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


def season_splits(sport_id: int, season: int, group: str,
                  fetch: bool = True) -> list[dict]:
    """All player season lines for one (sport, season, group), cached.
    group: 'hitting' | 'pitching'. Returns [] when uncached and
    fetch=False (cache-only consumers stay offline-safe)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{group}_{sport_id}_{season}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    if not fetch:
        return []
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
            return splits
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
        level = SPORT_LEVEL.get(sport_id, "?")
        if sport_id == 16 and "Dominican" in league:
            level = "DSL"
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
            })
        else:
            row.update({
                "ip": st.get("inningsPitched"), "bf": st.get("battersFaced"),
                "era": st.get("era"), "so": st.get("strikeOuts"),
                "bb": st.get("baseOnBalls"), "g": st.get("gamesPlayed"),
                "gs": st.get("gamesStarted"),
            })
        lean.append(row)
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
    return {k: round(statistics.median(v), 4) for k, v in vals.items()} | {"n": n}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    warm_cache(range(2014, 2027))
    print("AA hitting norms 2019:", league_norms(2019, "AA", "hitting"))
    print("AAA pitching norms 2023:", league_norms(2023, "AAA", "pitching"))
