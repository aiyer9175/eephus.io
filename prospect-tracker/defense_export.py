# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - Defense Leaderboards sidecar (data/defense_leaderboards.json).

The fielding analog of hitter_export.py. Assembles the DEM+ fielder board and
team DEM+ from three MLB StatsAPI reads, all bulk and all cached:

  * `stats=sabermetrics&group=hitting`, the same cache key the hitter board's
    published wRC+ column already warms every night. Its `fielding` is
    FanGraphs' served fielding runs (Statcast range and arm, catcher blocking and
    throwing), EXCLUDING framing; `positional` is FanGraphs' positional
    adjustment. Both are read verbatim.
  * catcher FRAMING, which the feed does not publish as a field but does carry
    inside `rar`: framing = rar - (batting + baseRunning + fielding + positional
    + wLeague + replacement). On 2025 that residual equals FanGraphs CFraming on
    111 of 111 catchers and is zero on all 654 non-catchers.
  * `stats=season&group=fielding`, innings by position (the exposure) and the
    putouts / assists / errors that give fielding percentage, the naive baseline.

TWO KEYS NAMED `fielding`. The fielding group's `fielding` is fielding
PERCENTAGE as a string ("1.000"); the sabermetrics group's is fielding RUNS as a
float. This module reads runs only from the sabermetrics group and computes
percentage from putouts, assists and errors, so the two can never be confused.

DEM+ is the only number here the site computes (dem_plus.py). Every run column
is published. NETWORK-GATED + BEST-EFFORT: nothing fetches at import, and a
failed pull returns 0 without writing.

Run: `python defense_export.py [season]`  or  `python defense_export.py history`.
"""
from __future__ import annotations

import functools
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import dem_plus
from dem_plus import Fielder, DEF_POSITIONS
from bullpen_export import (_team_abbrev_map, guard_nonempty_block, team_basis_meta,
                            basis_rows_for, _active_mlbam_ids, _ingest_red)

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = Path(__file__).parent / ".cache"
OUT_PATH = DATA_DIR / "defense_leaderboards.json"
HISTORY_PATH = DATA_DIR / "defense_history.json"
EVAL_PATH = DATA_DIR / "dem_plus_eval.json"
MULTIYR_PATH = DATA_DIR / "dem_plus_multiyear_eval.json"
HITTER_BOARD = DATA_DIR / "hitter_leaderboards.json"

#: 2016 is the first season of the one Statcast fielding frame FanGraphs made
#: retroactive; earlier seasons are UZR and are never pooled with these.
HISTORY_SEASONS = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

#: If fewer than this share of fielders with 200+ C innings carry a nonzero
#: framing residual, the feed's composition has changed (MLB added framing as a
#: field, so the residual went to zero) and every framing value is dropped.
FRAMING_MIN_CATCHER_SHARE = 0.5
FRAMING_CATCHER_MIN_INN = 200.0

_FIELDING_URL = ("https://statsapi.mlb.com/api/v1/stats?stats=season&group=fielding"
                 "&season={season}&sportId=1&playerPool=All&limit=6000")


@functools.lru_cache(maxsize=1)
def _tmap() -> dict:
    return _team_abbrev_map()


def _fetch_json(url: str, key: str) -> Optional[dict]:
    """One cached GET through the shared scraper cache (24h TTL on a current-year
    key, 30 days on a past one). None on any failure."""
    try:
        from scrapers import _fetch       # network-gated: nothing fetches at import
        fr = _fetch(url, key, accept_json=True)
        if fr.status != 200 or not fr.body:
            _log.warning("%s: fetch failed (status=%s)", key, fr.status)
            return None
        return json.loads(fr.body)
    except Exception as e:   # noqa: BLE001 - best-effort
        _log.warning("%s: unavailable (%s)", key, e)
        return None


def _cache_mtime(key: str) -> Optional[str]:
    p = CACHE_DIR / f"{key}.json"
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(
            timespec="seconds")
    except OSError:
        return None


@functools.lru_cache(maxsize=16)
def load_published_fielding(season: int) -> dict:
    """FanGraphs' published fielding, framing and positional runs for one season,
    keyed by MLBAM id, through the shared sabermetrics loader (saber_feed: the
    stint guard and the framing residual live there). Never raises."""
    import saber_feed
    meta = saber_feed.load_components(int(season))
    meta["fetched_at"] = _cache_mtime(saber_feed.cache_key(season))
    return meta


def _innings_to_float(v) -> float:
    from fielding_innings import innings_to_float
    return innings_to_float(v)


@functools.lru_cache(maxsize=16)
def load_season_innings(season: int) -> dict:
    """{"players": {mlbam: {"inn": {pos: innings}, "po", "a", "e", "name",
    "team_id"}}, "max_games", "fetched_at", "source"} from the StatsAPI season
    fielding feed. A closed season reads fielding_innings' permanent cache when
    present; the live season goes through the 24-hour scraper cache."""
    season = int(season)
    doc = None
    fetched_at = None
    src = "statsapi season fielding (bulk)"
    p = CACHE_DIR / "statsapi_field" / f"fld_{season}.json"
    # A closed season always reads fielding_innings' permanent cache. The live
    # season reads it too when the nightly refresh (run_monthly d9b1) wrote it in
    # the last 24 hours, so the feed is fetched once a night, not twice.
    fresh = False
    try:
        fresh = (datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) < 24 * 3600
    except OSError:
        fresh = False
    if season < date.today().year or fresh:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            fetched_at = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(
                timespec="seconds")
        except (OSError, ValueError):
            doc = None
    if doc is None:
        key = f"statsapi_fielding_season_{season}"
        doc = _fetch_json(_FIELDING_URL.format(season=season), key)
        fetched_at = _cache_mtime(key)
    out: dict[int, dict] = {}
    max_g = 0
    for block in (doc or {}).get("stats") or []:
        for sp in block.get("splits") or []:
            try:
                pid = int(sp["player"]["id"])
                pos = sp["position"]["abbreviation"]
            except (KeyError, TypeError, ValueError):
                continue
            if pos not in DEF_POSITIONS:
                continue
            st = sp.get("stat") or {}
            rec = out.setdefault(pid, {"inn": {}, "po": 0.0, "a": 0.0, "e": 0.0,
                                       "name": (sp.get("player") or {}).get("fullName", ""),
                                       "team_id": (sp.get("team") or {}).get("id")})
            rec["inn"][pos] = rec["inn"].get(pos, 0.0) + _innings_to_float(st.get("innings"))
            for k, sk in (("po", "putOuts"), ("a", "assists"), ("e", "errors")):
                try:
                    rec[k] += float(st.get(sk) or 0)
                except (TypeError, ValueError):
                    pass
            try:
                max_g = max(max_g, int(st.get("games") or st.get("gamesPlayed") or 0))
            except (TypeError, ValueError):
                pass
    return {"players": out, "max_games": max_g, "fetched_at": fetched_at,
            "source": src, "n_fielders": len(out)}


def _identity_rows(season: int, pids: set) -> list[dict]:
    """Name and CURRENT team for every fielder, from the hitter pipeline's own
    season rows so the three boards share one team basis. A fielder with no
    hitting row falls back to the fielding feed's name and team."""
    try:
        from hitter_export import load_season_hitting
        rows = load_season_hitting(int(season))
    except Exception as e:   # noqa: BLE001
        _log.warning("defense: hitting rows unavailable (%s)", e)
        rows = []
    return [r for r in rows if r.get("mlbam") in pids]


def build_fielders(season: int, *, log=print) -> tuple[list[Fielder], list[dict], dict]:
    """Join published runs, innings and identity by MLBAM id only."""
    pub = load_published_fielding(season)
    inn = load_season_innings(season)
    vals = pub.get("values") or {}
    players = inn.get("players") or {}
    ids = set(vals) & set(players)
    ident = {r["mlbam"]: r for r in _identity_rows(season, ids)}
    tmap = _tmap()
    out: list[Fielder] = []
    basis_rows: list[dict] = []
    for pid in sorted(ids):
        v, p = vals[pid], players[pid]
        idr = ident.get(pid)
        if idr is None:
            idr = {"mlbam": pid, "name": v.get("name") or p.get("name") or "",
                   "team": tmap.get(v.get("team_id") or p.get("team_id")) or ""}
        basis_rows.append(idr)
        out.append(Fielder(
            key=str(pid), name=str(idr.get("name") or ""), team=str(idr.get("team") or ""),
            mlbam=int(pid), inn_by_pos=dict(p["inn"]), fld_runs=float(v["fld"]),
            frm_runs=v.get("frm"), pos_runs=v.get("pos"),
            putouts=p["po"], assists=p["a"], errors=p["e"]))
    return out, basis_rows, {"published": pub, "innings": inn}


def framing_check(fielders: list[Fielder], *, log=print, file_red: bool = True) -> dict:
    """The framing tripwire. Strips the residual from non-catchers (it is the
    feed's rounding there) and, if too few catchers carry one, from everybody."""
    n_c = n_c_frm = n_wo_c = 0
    for f in fielders:
        c_inn = float((f.inn_by_pos or {}).get("C") or 0)
        has = f.frm_runs is not None and abs(f.frm_runs) > dem_plus.FRAMING_EPS
        if c_inn >= FRAMING_CATCHER_MIN_INN:
            n_c += 1
            n_c_frm += int(has)
        if has and c_inn <= 0:
            n_wo_c += 1
        if c_inn <= 0 or not has:
            f.frm_runs = None
    share = (n_c_frm / n_c) if n_c else None
    ok = share is not None and share >= FRAMING_MIN_CATCHER_SHARE
    reason = None
    if not ok:
        reason = (f"{n_c_frm} of {n_c} catchers with {int(FRAMING_CATCHER_MIN_INN)}+ C "
                  f"innings carry a framing residual (floor "
                  f"{FRAMING_MIN_CATCHER_SHARE:.0%}); the feed's run line changed shape")
        for f in fielders:
            f.frm_runs = None
        if file_red:
            _ingest_red("defense_published_fielding",
                        f"framing unavailable: {reason}. Catcher DEM+ reads fielding "
                        f"without framing this run.")
        if callable(log):
            log(f"  defense: FRAMING UNAVAILABLE ({reason})")
    return {"framing_available": ok, "n_catchers_c200": n_c,
            "n_catchers_with_framing": n_c_frm,
            "n_framing_without_c_innings": n_wo_c,
            "reason": reason}


def _join_hem_plus(rows: list[dict], season: int) -> int:
    """HEM+ beside DEM+ so the glove-versus-bat chart has both numbers."""
    try:
        doc = json.loads(HITTER_BOARD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if int(doc.get("season") or 0) != int(season):
        return 0
    by = {h.get("mlbam"): h.get("hem_plus") for h in doc.get("hitters") or []}
    n = 0
    for r in rows:
        v = by.get(r.get("mlbam"))
        if v is not None:
            r["hem_plus"] = v
            n += 1
    return n


def _join_dem_plus_3yr(rows: list[dict]) -> dict:
    """Frozen 3-year DEM+ from the lab's multi-year artifact (the
    _join_hem_plus_3yr contract: vintage, not pipeline output)."""
    meta = {"source": MULTIYR_PATH.name, "n_stamped": 0, "available": False}
    try:
        art = json.loads(MULTIYR_PATH.read_text(encoding="utf-8"))
        pv = art["proposed_values"]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return meta
    n = 0
    for r in rows:
        p = players.get(str(r.get("mlbam") or ""))
        if not p:
            continue
        r["dem_plus_3yr"] = p.get("dem_plus_3yr")
        r["dem_plus_3yr_pct"] = p.get("pct")
        r["dem_plus_3yr_tag"] = p.get("tag")
        n += int(p.get("dem_plus_3yr") is not None)
    meta.update({"available": True, "n_stamped": n,
                 "generated_at": art.get("generated_at"),
                 "season": pv.get("season"), "window": pv.get("window"),
                 "n_in_artifact": len(players),
                 "note": (f"3-year DEM+ is FROZEN lab output read verbatim from "
                          f"{MULTIYR_PATH.name}, as of generated_at, not this board's "
                          f"as_of. Fielders who joined the pool since have no value.")})
    return meta


def _frame_meta() -> dict:
    return {
        "basis": "FanGraphs' served fielding runs, read verbatim from MLB StatsAPI sabermetrics",
        "components": ("Statcast range and arm (retroactive to 2016), catcher blocking "
                       "and throwing, and catcher framing"),
        "framing_derivation": ("rar minus batting, baseRunning, fielding, positional, "
                               "wLeague and replacement; matches FanGraphs CFraming "
                               "exactly on the seasons checked"),
        "not_ewar": ("eWAR fielding is Baseball-Reference DRS (fielding_blend_w 0.0), a "
                     "different frame; it is not on this board"),
        "claim": ("parity with the fWAR fielding frame, framing included; DEM+ is a "
                  "steadier read of that published series, not a better measure of it"),
    }


def _scale_meta(pool: dict) -> dict:
    return {"convention": "100 + 10z", "per_sigma": dem_plus.DEM_PER_SIGMA,
            "rate_basis": "runs per 1,000 defensive innings (C, 1B, 2B, 3B, SS, LF, CF, RF)",
            "pool_min_inn": dem_plus.POOL_MIN_INN,
            "qualify_min_inn": dem_plus.QUALIFY_MIN_INN,
            "pool_n": pool.get("n"), "pool_mean_rate": pool.get("mean_rate"),
            "pool_sd_rate": pool.get("sd_rate"),
            "k_inn": dict(dem_plus.K_INN),
            "k_source": ("frozen from the pre-registered fit window, predictor seasons "
                         "2016 to 2018 (docs/dem-plus-2026-09-11/DEM_PLUS_GATE.md); LF "
                         "keeps the positional_fit constant"),
            "note": ("dem_plus_raw = 100 + 10 * (rate_1000_shrunk - pool_mean_rate) / "
                     "pool_sd_rate: 10 points = 1 SD of the pool's SHRUNK rates (the "
                     "WAR/PA+ ruler, not the HEM+/REM+/SEM+ ratio ruler).")}


def _verdict() -> str:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        return (j.get("verdict") or {}).get("status") or "provisional"
    except Exception:
        return "provisional"


def _backtest() -> dict:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    fs = j.get("forward_spearman_vs_rate_next") or {}
    v = j.get("verdict") or {}
    return {
        "status": v.get("status") or "provisional",
        "n_pairs": j.get("n_forward_pairs"),
        "seasons": len(j.get("seasons") or []),
        "rho_dem_plus": fs.get("dem_plus"),
        "rho_raw_rate": fs.get("raw_rate"),
        "rho_fld_pct": fs.get("fld_pct"),
        "rho_innings": fs.get("innings"),
        "disclaimer": ("DEM+ is scored against next season's published fielding rate. "
                       "Positional credit and innings are context: DEM+ is glove per "
                       "inning, not positional value."),
    }


def _roster_filter_meta(teams: list, active_ids) -> dict:
    return {
        "applied": active_ids is not None,
        "n_active_roster_ids": (len(active_ids) if active_ids is not None else None),
        "n_dropped_from_constructions": sum(int(t.get("n_off_roster_dropped") or 0)
                                            for t in teams),
        "basis": "StatsAPI rosterType=active (26-man)",
        "scope": ("the constructed alignment ONLY. Team DEM+ and the run totals stay on "
                  "the full season pool."),
        "on_failure": "a failed roster fetch filters nothing",
    }


def score_season(season: int, *, active_ids=None, log=print,
                 file_red: bool = True) -> Optional[dict]:
    fielders, basis_rows, src = build_fielders(season, log=log)
    if not fielders:
        return None
    fr = framing_check(fielders, log=log, file_red=file_red)
    scored = dem_plus.score_pool(fielders, active_ids, season=int(season))
    return {"scored": scored, "basis_rows": basis_rows, "src": src, "framing": fr,
            "fielders": fielders}


def export(season: Optional[int] = None, *, out_path: Optional[Path] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    """Build data/defense_leaderboards.json and return the fielder count."""
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()
    log(f"  defense: loading {season} published fielding and innings...")
    active_ids = _active_mlbam_ids(int(season))
    res = score_season(season, active_ids=active_ids, log=log)
    if not res:
        log(f"  defense: no fielding data for {season} (source blocked or empty); skipping")
        return 0
    scored, src, fr = res["scored"], res["src"], res["framing"]
    pub, inn = src["published"], src["innings"]
    n_hem = _join_hem_plus(scored["fielders"], season)
    d3 = _join_dem_plus_3yr(scored["fielders"])
    teams, rollup_meta = guard_nonempty_block(
        scored["teams"], out_path, key="teams", source="defense_leaderboards",
        label="defense", log=log)
    pub_meta = {
        "available": bool(pub.get("values")), "source": pub.get("source"),
        "season": season, "fetched_at": pub.get("fetched_at"),
        "n_feed_rows": pub.get("n_rows"), "n_feed_players": pub.get("n_players"),
        "n_multi_team": pub.get("n_multi_team"), "n_ambiguous": pub.get("n_ambiguous"),
        "ambiguous_ids": pub.get("ambiguous_ids"), "n_board": len(scored["fielders"]),
        **fr,
        "note": ("Fielding, framing and positional runs are FanGraphs' PUBLISHED values, "
                 "read verbatim from MLB's bulk season-total feed and joined by MLBAM id. "
                 "This site computes none of them; DEM+ is the index it computes."),
    }
    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "verdict": _verdict(), "backtest": _backtest(),
        "frame": _frame_meta(),
        "published_fielding": pub_meta,
        "innings": {"source": inn.get("source"), "fetched_at": inn.get("fetched_at"),
                    "max_games": inn.get("max_games"), "n_fielders": inn.get("n_fielders"),
                    "note": ("Defensive innings by position from MLB's season fielding "
                             "feed, converted from baseball thirds at ingest.")},
        "scale": _scale_meta(scored["pool"]),
        "multiyear": d3,
        "team_rollup_framing": {
            "included": dem_plus.TEAM_ROLLUP_FRAMING,
            "note": ("Team DEM+ and the club run totals roll over non-catchers until the "
                     "betting program's pre-registered catcher-framing read is recorded; "
                     "each catcher's own DEM+ still includes his framing.")
                    if not dem_plus.TEAM_ROLLUP_FRAMING else
                    "Team DEM+ includes catchers and their framing."},
        "hem_plus_join": {"n_stamped": n_hem,
                          "note": "HEM+ joined from hitter_leaderboards.json for the glove-versus-bat chart"},
        "team_basis": team_basis_meta(basis_rows_for(scored["fielders"], res["basis_rows"]),
                                      label=f"fielding {season}"),
        "roster_filter": _roster_filter_meta(scored["teams"], active_ids),
        "team_rollup": rollup_meta,
        "pool": scored["pool"], "fielders": scored["fielders"], "teams": teams,
    }
    n = len(scored["fielders"])
    log(f"  defense: {n} fielders ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(teams)} team defenses; framing "
        f"{'on' if fr['framing_available'] else 'OFF'} "
        f"({fr['n_catchers_with_framing']}/{fr['n_catchers_c200']} catchers)")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  defense: wrote {out_path.name}")
    return n


_HISTORY_FIELDS = ("mlbam", "name", "team", "pos", "inn", "dem_plus", "tier",
                   "fld_runs", "frm_runs", "fld_total", "pos_runs", "def_runs",
                   "rate_1000", "fld_pct", "qualified")


def export_history(seasons=None, *, out_path: Optional[Path] = None,
                   write: bool = True, log=print) -> dict:
    """data/defense_history.json: per-season qualified-fielder boards."""
    seasons = list(seasons or HISTORY_SEASONS)
    out_path = out_path or HISTORY_PATH
    hist = {}
    basis_rows: list[dict] = []
    for y in seasons:
        log(f"  defense-history: {y}...")
        res = score_season(y, log=log, file_red=False)
        if not res:
            log(f"  defense-history: no data for {y}; skipping")
            continue
        qual = [r for r in res["scored"]["fielders"] if r.get("qualified")]
        basis_rows.extend(basis_rows_for(qual, res["basis_rows"]))
        board = [{k: r.get(k) for k in _HISTORY_FIELDS if r.get(k) is not None}
                 for r in qual]
        board.sort(key=lambda r: (r.get("dem_plus") or -999), reverse=True)
        hist[str(y)] = {"season": y, "n_qualified": len(board), "fielders": board,
                        "framing_available": res["framing"]["framing_available"]}
        log(f"  defense-history: {y} -> {len(board)} qualified")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Qualified fielders by season. DEM+: sample-shrunk fielding rate, "
                 "100 + 10z against that season's pool. Run columns are FanGraphs' "
                 "published values as fetched; FanGraphs can revise them."),
        "team_basis": team_basis_meta(basis_rows, label="defense history", scope="history"),
        "history": hist,
    }
    if write and hist:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  defense-history: wrote {out_path.name} ({len(hist)} seasons)")
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        _yrs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
        export_history(_yrs)
    else:
        _season = int(sys.argv[1]) if len(sys.argv) > 1 else None
        export(_season)
