# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - Hitter Leaderboards sidecar (data/hitter_leaderboards.json).

The hitter analog of bullpen_export.py / starter_export.py. Assembles the HEM+
hitter board + team Offense+ from the MLB StatsAPI season HITTING leaderboard
(fa_sources.fetch_statsapi_season_stats, which is cached per season). No leverage
or durability walk: HEM+ is a pure offensive-rate skill index (shrunk wOBA, 100 =
average qualified hitter); volume (PA), baserunning (SB), and the rate slash line
ride as context columns.

Feeds hem_plus.score_pool(), which anchors HEM+ to the hitter pool and rolls up
team offenses. Also builds the yearly hitter-history file for the /mlbstats/
history tabs.

Run: `python hitter_export.py [season]`  or  `python hitter_export.py history`.
Wired into run_monthly (best-effort). NETWORK-GATED + BEST-EFFORT: nothing
fetches at import; any pull failure logs and returns 0 rather than aborting.
"""
from __future__ import annotations

import functools
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import hem_plus
from hem_plus import Hitter
from bullpen_export import _team_abbrev_map, _num
import fa_sources

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "hitter_leaderboards.json"
HISTORY_PATH = DATA_DIR / "hitter_history.json"
EVAL_PATH = DATA_DIR / "hem_plus_eval.json"
MULTIYR_PATH = DATA_DIR / "hem_plus_multiyear_eval.json"
HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]


def _join_hem_plus_3yr(hitters: list[dict]) -> int:
    """Stamp hem_plus_3yr / percentile / tag from the multi-year artifact
    (tools/hem_plus_lab.py). Companion SKILL column; missing artifact or unmatched
    player -> fields absent, column renders blank. Returns rows stamped."""
    try:
        players = json.loads(MULTIYR_PATH.read_text(encoding="utf-8"))["proposed_values"]["players"]
    except (OSError, ValueError, KeyError):
        return 0
    n = 0
    for h in hitters:
        p = players.get(str(h.get("mlbam") or ""))
        if not p:
            continue
        h["hem_plus_3yr"] = p.get("hem_plus_3yr")
        h["hem_plus_3yr_pct"] = p.get("pct")
        h["hem_plus_3yr_tag"] = p.get("tag")
        if h["hem_plus_3yr"] is not None:
            n += 1
    return n


@functools.lru_cache(maxsize=1)
def _tmap() -> dict:
    """Team id -> abbreviation, fetched once (offline-safe: {} on failure)."""
    return _team_abbrev_map()


def load_season_hitting(season: int) -> list[dict]:
    """All MLB hitters' season lines from the StatsAPI hitting leaderboard
    (playerPool 'all'), via the cached fa_sources fetcher. One flat row per
    player. [] on any failure (offline / API change)."""
    try:
        rows = fa_sources.fetch_statsapi_season_stats(int(season), "hitting")
    except Exception as e:
        _log.warning("StatsAPI season hitting (%s) failed: %s", season, e)
        return []
    if not rows:
        return []
    tmap = _tmap()
    out = []
    for r in rows:
        st = r.get("stat") or {}
        pl = r.get("player") or {}
        tm = r.get("team") or {}
        pid = pl.get("id")
        if not pid:
            continue
        tid = tm.get("id") if isinstance(tm, dict) else None
        out.append({
            "mlbam": int(pid), "name": pl.get("fullName", ""),
            "team": (tmap.get(tid) or ""),
            "PA": st.get("plateAppearances"), "AB": st.get("atBats"), "H": st.get("hits"),
            "2B": st.get("doubles"), "3B": st.get("triples"), "HR": st.get("homeRuns"),
            "BB": st.get("baseOnBalls"), "IBB": st.get("intentionalWalks"),
            "HBP": st.get("hitByPitch"), "SF": st.get("sacFlies"), "SO": st.get("strikeOuts"),
            "SB": st.get("stolenBases"), "CS": st.get("caughtStealing"),
            "RBI": st.get("rbi"), "R": st.get("runs"),
        })
    return out


def build_hitters(rows: list[dict]) -> list[Hitter]:
    """StatsAPI season rows -> Hitter records."""
    out: list[Hitter] = []
    for r in rows:
        mlbam = r.get("mlbam")
        if mlbam is None:
            continue
        out.append(Hitter(
            key=str(mlbam), name=str(r.get("name", "")), team=str(r.get("team", "")),
            mlbam=int(mlbam),
            pa=_num(r.get("PA")) or 0.0, ab=_num(r.get("AB")) or 0.0, h=_num(r.get("H")) or 0.0,
            doub=_num(r.get("2B")) or 0.0, trip=_num(r.get("3B")) or 0.0, hr=_num(r.get("HR")) or 0.0,
            bb=_num(r.get("BB")) or 0.0, ibb=_num(r.get("IBB")) or 0.0, hbp=_num(r.get("HBP")) or 0.0,
            sf=_num(r.get("SF")) or 0.0, so=_num(r.get("SO")) or 0.0,
            sb=_num(r.get("SB")) or 0.0, cs=_num(r.get("CS")) or 0.0,
            rbi=_num(r.get("RBI")) or 0.0, r=_num(r.get("R")) or 0.0,
        ))
    return out


def _join_xhem_plus(hitters: list[dict], season: int) -> int:
    """Stamp xhem_plus (the HEM+ ratio scale on Savant xwOBA -- 'deserved offense')
    + luck_gap (xHEM+ minus HEM+) onto tracked hitters. xwOBA forward-predicts next-
    year wOBA better than actual wOBA (validated: tools/xhem_plus_lab.py), so this is
    a companion 'deserved-offense' read. MLB-only + min-BBE gated, so it stamps only
    the tracked subset; missing -> fields absent (column blank). Best-effort."""
    try:
        import mlb_player_export as mpe
        rows = mpe._savant("expected", int(season), "batter")
    except Exception:
        return 0
    # xwOBA needs a minimum sample: a 1-PA player who homered shows est_woba ~0.8,
    # which is noise, not deserved talent. Gate the join (and the pool anchor) at a
    # real Savant PA sample. xwOBA is already de-luck'd, so no further shrink.
    _XHEM_MIN_PA = 100.0
    xw = {}
    for r in rows:
        try:
            mid = int(r["player_id"]); ew = float(r["est_woba"]); pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if pa >= _XHEM_MIN_PA and ew > 0:
            xw[mid] = (ew, pa)
    if not xw:
        return 0
    # PA-weighted pool mean xwOBA anchors the ratio so the tracked pool averages 100.
    dtot = sum(pa for _, pa in xw.values())
    pool = (sum(x * pa for x, pa in xw.values()) / dtot) if dtot else None
    if not pool:
        return 0
    n = 0
    for h in hitters:
        ent = xw.get(int(h["mlbam"])) if h.get("mlbam") is not None else None
        if not ent:
            continue
        # Same widened scale as HEM+ (hem_plus.HEM_SPREAD_GAIN), so xHEM+ and HEM+
        # are on ONE ruler and luck_gap = xHEM+ - HEM+ stays meaningful.
        h["xhem_plus"] = int(round(100.0 + hem_plus.HEM_SPREAD_GAIN * (100.0 * ent[0] / pool - 100.0)))
        h["xwoba"] = round(ent[0], 3)
        if h.get("hem_plus") is not None:
            h["luck_gap"] = h["xhem_plus"] - h["hem_plus"]   # + = under-performing his contact
        n += 1
    return n


def _join_fwdhem_plus(hitters: list[dict], hem_raw: dict, season: int) -> int:
    """Stamp fwdhem_plus ('xHEM+ Blend') onto tracked hitters: the validated T1-3
    forward blend, 0.7 * z(Savant est_woba) + 0.3 * z(unrounded HEM+ core), z-scored
    within the season over the joined pool, then mapped back onto the HEM+ ratio
    display scale (the joined pool's own HEM+ mean/spread), so it reads on the same
    ruler as HEM+/xHEM+. Forward-beats xwOBA-alone at predicting next-year wOBA
    (validated: tools/xhem_plus_lab.py X-H5, x_h5_blend block of
    data/xhem_plus_eval.json). Same Savant gating as xHEM+ (MLB-only, min 100
    Savant PA), so it stamps only the tracked subset; missing -> field absent
    (column blank). `hem_raw` is {mlbam: unrounded hem_plus_raw} from the scored
    Hitter objects (display rounding never enters the blend). Best-effort."""
    try:
        import mlb_player_export as mpe
        rows = mpe._savant("expected", int(season), "batter")
    except Exception:
        return 0
    _FWDHEM_MIN_PA = 100.0     # same sample gate as the xHEM+ join
    W_XWOBA, W_HEM = 0.7, 0.3  # T1-3 pre-registered weights
    xw = {}
    for r in rows:
        try:
            mid = int(r["player_id"]); ew = float(r["est_woba"]); pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if pa >= _FWDHEM_MIN_PA and ew > 0:
            xw[mid] = ew
    # joined pool: tracked hitters with BOTH a real Savant sample and a HEM core
    pool = {m: (ew, hem_raw[m]) for m, ew in xw.items() if hem_raw.get(m) is not None}
    if len(pool) < 2:
        return 0

    def _mu_sd(vals):
        k = len(vals)
        mu = sum(vals) / k
        sd = (sum((v - mu) ** 2 for v in vals) / (k - 1)) ** 0.5
        return mu, sd

    mu_x, sd_x = _mu_sd([v[0] for v in pool.values()])
    mu_h, sd_h = _mu_sd([v[1] for v in pool.values()])
    if not sd_x or not sd_h:
        return 0
    blend = {m: W_XWOBA * (ew - mu_x) / sd_x + W_HEM * (hp - mu_h) / sd_h
             for m, (ew, hp) in pool.items()}
    # A 0.7/0.3 blend of two unit-z legs has pool sd < 1 (the legs are not
    # perfectly correlated), so re-standardize the blend over the pool before
    # mapping back onto the HEM+ ratio display scale via the pool's own HEM+
    # location/spread. Both steps are monotone, so the validated forward
    # RANKING is exactly the shipped ranking; only the display width changes.
    _, sd_b = _mu_sd(list(blend.values()))
    if not sd_b:
        return 0
    n = 0
    for h in hitters:
        z = blend.get(int(h["mlbam"])) if h.get("mlbam") is not None else None
        if z is None:
            continue
        h["fwdhem_plus"] = int(round(mu_h + sd_h * (z / sd_b)))
        n += 1
    return n


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
    fs = j.get("forward_spearman_vs_wOBA_next") or {}
    v = j.get("verdict") or {}
    return {
        "status": v.get("status") or "provisional",
        "n_pairs": j.get("n_forward_pairs"),
        "seasons": len(j.get("seasons") or []),
        "rho_hem_plus": fs.get("hem_plus"),
        "rho_woba": fs.get("raw_woba"),
        "rho_ops": fs.get("ops"),
        "rho_avg": fs.get("avg"),
        "disclaimer": ("HEM+ predicts next-year offensive rate (wOBA) out of sample. Volume "
                       "(PA), baserunning (SB), and the slash line are shown as context "
                       "because HEM+ is offensive-rate skill, not counting or speed value."),
    }


@functools.lru_cache(maxsize=4)
def load_bat_side(season: int) -> dict:
    """{mlbam: 'L'|'R'|'S'} for every MLB player, one bulk StatsAPI call. Feeds the
    handedness-aware lineup construction (build_batting_order). Best-effort: {} on
    any failure, so lineups fall back to the HEM+-only order."""
    try:
        import bullpen_export as be
        data = be._get_json("sports/1/players", {"season": int(season)})
    except Exception as e:   # noqa: BLE001 - best-effort, network/parse anything
        log = logging.getLogger(__name__)
        log.warning("batSide fetch failed: %s", e)
        return {}
    out = {}
    for p in data.get("people", []):
        bs = (p.get("batSide") or {}).get("code")
        if p.get("id") and bs:
            out[int(p["id"])] = bs
    return out


def export(season: Optional[int] = None, *, out_path: Optional[Path] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    """Build data/hitter_leaderboards.json and return the hitter count."""
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  hitters: loading {season} StatsAPI season hitting...")
    rows = load_season_hitting(season)
    if not rows:
        log(f"  hitters: no hitting data for {season} (source blocked or empty); skipping")
        return 0
    hitters = build_hitters(rows)
    # Stamp bat side (L/R/S) before scoring so team_offense can construct the
    # handedness-staggered vs-LHP / vs-RHP orders. Best-effort bulk call.
    bat_side = load_bat_side(season)
    if bat_side:
        n_bs = 0
        for h in hitters:
            bs = bat_side.get(int(h.mlbam)) if h.mlbam is not None else None
            if bs:
                h.bats = bs
                n_bs += 1
        log(f"  hitters: bat side stamped for {n_bs} hitters")
    scored = hem_plus.score_pool(hitters)
    n_h3 = _join_hem_plus_3yr(scored["hitters"])
    if n_h3:
        log(f"  hitters: 3-year HEM+ joined for {n_h3} hitters")
    n_xh = _join_xhem_plus(scored["hitters"], season)
    if n_xh:
        log(f"  hitters: xHEM+ (Savant deserved offense) joined for {n_xh} hitters")
    # UNROUNDED HEM+ core off the scored Hitter objects (score_pool mutates in
    # place), so the blend never sees display rounding.
    _hem_raw = {int(h.mlbam): h.hem_plus_raw for h in hitters
                if h.mlbam is not None and h.hem_plus_raw is not None}
    n_fh = _join_fwdhem_plus(scored["hitters"], _hem_raw, season)
    if n_fh:
        log(f"  hitters: fwdHEM+ (xHEM+ Blend forward column) joined for {n_fh} hitters")

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "verdict": _verdict(), "backtest": _backtest(),
        "pool": scored["pool"], "hitters": scored["hitters"], "teams": scored["teams"],
    }
    n = len(scored["hitters"])
    log(f"  hitters: {n} hitters ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(scored['teams'])} team offenses")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  hitters: wrote {out_path.name}")
    return n


_HISTORY_FIELDS = ("mlbam", "name", "team", "hem_plus", "tier", "pa", "ab", "hr", "bb",
                   "sb", "woba", "avg", "obp", "slg", "ops", "iso", "bb_pct", "k_pct",
                   "babip", "qualified")


def export_history(seasons=None, *, out_path: Optional[Path] = None,
                   write: bool = True, log=print) -> dict:
    """Build data/hitter_history.json - per-season qualified-hitter boards for the
    /mlbstats/ yearly history tabs. One cached StatsAPI call per season."""
    seasons = list(seasons or HISTORY_SEASONS)
    out_path = out_path or HISTORY_PATH
    hist = {}
    for y in seasons:
        log(f"  hitter-history: {y}...")
        rows = load_season_hitting(y)
        if not rows:
            log(f"  hitter-history: no data for {y}; skipping")
            continue
        scored = hem_plus.score_pool(build_hitters(rows))
        board = [{k: s.get(k) for k in _HISTORY_FIELDS}
                 for s in scored["hitters"] if s.get("qualified")]
        board.sort(key=lambda s: (s.get("hem_plus") or -999), reverse=True)
        hist[str(y)] = {"season": y, "n_qualified": len(board), "hitters": board}
        log(f"  hitter-history: {y} -> {len(board)} qualified")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Per-season qualified-hitter boards for the yearly history tabs. HEM+ is the "
                 "pure offensive-rate skill index (100 = average qualified hitter, shrunk wOBA); "
                 "the slash line and volume columns are context."),
        "history": hist,
    }
    if write and hist:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  hitter-history: wrote {out_path.name} ({len(hist)} seasons)")
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        _yrs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
        export_history(_yrs)
    else:
        _season = int(sys.argv[1]) if len(sys.argv) > 1 else None
        export(_season)
