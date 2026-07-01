# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - Bullpen Leaderboards sidecar (data/bullpen_leaderboards.json).

Assembles the REM+ reliever board + team Bullpen+ + depth charts from REACHABLE
sources (FanGraphs is 403-blocked here):

  SKILL CORE   MLB StatsAPI season pitching leaderboard (playerPool=all) - one
               combined season line per pitcher with the proper team, holds,
               inherited runners, and every FIP input (K/BB/HBP/HR/IP/BF).
               Traded players come back as a single total under their most
               recent club, so there is no same-city ambiguity or multi-stint
               fragmentation (the trap Baseball-Reference's city-name Tm has).
  SwStr%       optional enrichment from pybaseball.pitching_stats_bref (StatsAPI
               has no swinging-strike count); best-effort, null when unavailable.
  LEVERAGE     mlb_leverage.fetch_season_leverage - gmLI / WPA / WPA-LI / SD / MD
               self-computed from the StatsAPI winProbability feed, joined by
               MLBAM id.

These feed rem_plus.score_pool(), which filters to true relievers, anchors REM+
to the reliever pool (100 = average), and rolls up team bullpens.

Run: `python bullpen_export.py [season] [leverage_game_limit]`. Also wired into
run_monthly (best-effort). NETWORK-GATED + BEST-EFFORT: nothing fetches at
import; any pull failure logs and returns 0 rather than aborting the caller.
`leverage_game_limit` caps the winProbability walk for a fast partial refresh
(the skill core stays full-season; only the Impact columns are partial, which
the coverage block discloses)."""
from __future__ import annotations

import functools
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import feed_cache  # hardened, 429-retrying requests session
import rem_plus
from rem_plus import Reliever

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "bullpen_leaderboards.json"
EVAL_PATH = DATA_DIR / "rem_plus_eval.json"

STATSAPI = "https://statsapi.mlb.com/api/v1"


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def ip_to_float(ip) -> float:
    """Convert MLB IP notation (X.1 = X+1/3, X.2 = X+2/3) to true decimal."""
    v = _num(ip)
    if v is None:
        return 0.0
    whole = int(v)
    outs = round((v - whole) * 10)
    if outs >= 3:  # guard against a true-decimal input sneaking in
        return v
    return whole + outs / 3.0


# --------------------------------------------------------------------------- #
# data pulls (network-gated: only run inside export())
# --------------------------------------------------------------------------- #
def _get_json(path: str, params: dict) -> dict:
    resp = feed_cache.SESSION.get(f"{STATSAPI}/{path}", params=params, timeout=45)
    resp.raise_for_status()
    return resp.json()


@functools.lru_cache(maxsize=1)
def _team_abbrev_map() -> dict:
    try:
        data = _get_json("teams", {"sportId": 1})
        return {t["id"]: t.get("abbreviation") for t in data.get("teams", [])}
    except Exception as e:
        _log.warning("team abbreviation map fetch failed: %s", e)
        return {}


def load_season_pitching(season: int) -> list[dict]:
    """All MLB pitchers' season lines from the StatsAPI leaderboard (playerPool
    'all' so relievers are included). One combined row per player. [] on any
    failure (offline / API change)."""
    try:
        data = _get_json("stats", {
            "stats": "season", "group": "pitching", "season": int(season),
            "sportId": 1, "gameType": "R", "playerPool": "all", "limit": 3000})
    except Exception as e:
        _log.warning("StatsAPI season pitching (%s) failed: %s", season, e)
        return []
    stats = data.get("stats") or []
    if not stats:
        return []
    tmap = _team_abbrev_map()
    out = []
    for s in stats[0].get("splits", []):
        st = s.get("stat") or {}
        pl = s.get("player") or {}
        tm = s.get("team") or {}
        pid = pl.get("id")
        if not pid:
            continue
        # drop position players pitching mop-up (their primary position is not P)
        pos = (s.get("position") or {}).get("abbreviation")
        if pos and pos != "P":
            continue
        out.append({
            "mlbam": int(pid), "name": pl.get("fullName", ""),
            "team": tmap.get(tm.get("id")) or "",
            "G": st.get("gamesPitched"), "GS": st.get("gamesStarted"),
            "SV": st.get("saves"), "HLD": st.get("holds"),
            "IP": st.get("inningsPitched"), "ER": st.get("earnedRuns"),
            "R": st.get("runs"), "BB": st.get("baseOnBalls"),
            "SO": st.get("strikeOuts"), "HR": st.get("homeRuns"),
            "HBP": st.get("hitByPitch"), "BF": st.get("battersFaced"),
            "Pit": st.get("numberOfPitches"),
            "IR": st.get("inheritedRunners"), "IRS": st.get("inheritedRunnersScored"),
        })
    return out


def load_bref_swstr(season: int) -> dict:
    """Optional SwStr% enrichment from Baseball-Reference (StatsAPI has no
    swinging-strike count). {mlbam: swstr_pct}; {} on any failure."""
    try:
        import pybaseball as pyb
        df = pyb.pitching_stats_bref(int(season))
    except Exception as e:
        _log.warning("bref SwStr enrichment unavailable: %s", e)
        return {}
    out: dict = {}
    try:
        for r in df.to_dict("records"):
            mid = r.get("mlbID")
            # bref StS is already the swinging-strike RATE (e.g. 0.19), not a count
            sts_rate = _num(r.get("StS"))
            if mid is None or sts_rate is None:
                continue
            try:
                out[int(float(mid))] = round(sts_rate, 4)
            except (TypeError, ValueError):
                continue
    except Exception as e:
        _log.warning("bref SwStr parse failed: %s", e)
    return out


def build_relievers(rows: list[dict], leverage: dict, swstr: Optional[dict] = None) -> list[Reliever]:
    """StatsAPI season rows -> Reliever records, joined to leverage (by MLBAM id)
    and the optional SwStr% enrichment."""
    swstr = swstr or {}
    out: list[Reliever] = []
    for r in rows:
        mlbam = r.get("mlbam")
        if mlbam is None:
            continue
        pit = _num(r.get("Pit")) or 0.0
        sw = swstr.get(mlbam)
        sts = (sw * pit) if (sw is not None and pit) else 0.0
        rel = Reliever(
            key=str(mlbam), name=str(r.get("name", "")), team=str(r.get("team", "")),
            mlbam=int(mlbam),
            g=_num(r.get("G")) or 0.0, gs=_num(r.get("GS")) or 0.0,
            ip=ip_to_float(r.get("IP")), tbf=_num(r.get("BF")) or 0.0,
            so=_num(r.get("SO")) or 0.0, bb=_num(r.get("BB")) or 0.0,
            hbp=_num(r.get("HBP")) or 0.0, hr=_num(r.get("HR")) or 0.0,
            er=_num(r.get("ER")) or 0.0, r=_num(r.get("R")) or 0.0,
            pit=pit, sts=sts,
            sv=_num(r.get("SV")) or 0.0, hld=_num(r.get("HLD")) or 0.0,
        )
        lev = leverage.get(int(mlbam))
        if lev:
            rel.gmli = lev.get("gmli")
            rel.wpa = lev.get("wpa")
            rel.wpa_li = lev.get("wpa_li")
            rel.sd = lev.get("sd")
            rel.md = lev.get("md")
            rel.entry_inning = lev.get("entry_inning")
        out.append(rel)
    return out


def _verdict() -> str:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        v = (j.get("verdict") or {})
        return v.get("status") or "provisional"
    except Exception:
        return "provisional"


def _backtest() -> dict:
    """Compact accountability card from data/rem_plus_eval.json - the forward
    chained out-of-sample backtest that earned REM+ its validated verdict. Shown
    to users on /mlbstats/ so a validated model advertises its rigor."""
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    fs = j.get("forward_spearman_vs_RA9_next") or {}
    gap = (j.get("gap_ci_vs_RA9_next") or {}).get("vs_era") or {}
    mk = j.get("market_check_aav") or {}
    v = j.get("verdict") or {}
    return {
        "status": v.get("status") or "provisional",
        "n_pairs": j.get("n_forward_pairs"),
        "seasons": len(j.get("seasons") or []),
        "rho_rem_plus": fs.get("rem_plus"),
        "rho_fip": fs.get("raw_fip"),
        "rho_era": fs.get("era"),
        "gap_vs_era_lo95": gap.get("lo95"),
        "market_rho": mk.get("rho_leverage_weighted_vs_aav"),
        "disclaimer": ("REM+ predicts next-year run prevention out of sample. Leverage (gmLI, WPA, "
                       "Shutdowns minus Meltdowns) rides separate Impact columns because it is "
                       "assigned by the manager, not a repeatable skill."),
    }


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def export(season: Optional[int] = None, *, leverage_limit: Optional[int] = None,
           out_path: Optional[Path] = None, write: bool = True, log=print,
           today: Optional[str] = None) -> int:
    """Build data/bullpen_leaderboards.json and return the reliever count."""
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  bullpen: loading {season} StatsAPI season pitching...")
    rows = load_season_pitching(season)
    if not rows:
        log(f"  bullpen: no pitching data for {season} (source blocked or empty); skipping")
        return 0
    swstr = load_bref_swstr(season)  # best-effort SwStr% enrichment

    log(f"  bullpen: computing leverage from StatsAPI winProbability"
        + (f" (first {leverage_limit} games)" if leverage_limit else " (full season)") + "...")
    try:
        import mlb_leverage
        leverage, coverage = mlb_leverage.fetch_season_leverage(
            season, limit=leverage_limit,
            progress=lambda i, n: (log(f"    leverage {i}/{n} games") if i % 200 == 0 else None))
    except Exception as e:
        _log.warning("leverage walk failed: %s", e)
        leverage, coverage = {}, {"games": 0, "games_total": 0}

    relievers = build_relievers(rows, leverage, swstr)
    scored = rem_plus.score_pool(relievers)

    payload = {
        "generated_at": today,
        "season": season,
        "as_of": today,
        "coverage": {
            "games": coverage.get("games", 0),
            "expected": coverage.get("games_total", 0),
            "note": ("gmLI / WPA / SD-MD reflect the games walked so far; REM+ skill is "
                     "full-season. Coverage fills toward complete as the feed cache accrues."),
        },
        "verdict": _verdict(),
        "backtest": _backtest(),
        "pool": scored["pool"],
        "relievers": scored["relievers"],
        "teams": scored["teams"],
    }

    n = len(scored["relievers"])
    log(f"  bullpen: {n} relievers ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(scored['teams'])} team pens; leverage {coverage.get('games', 0)}/"
        f"{coverage.get('games_total', 0)} games")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        try:
            shown = out_path.relative_to(Path(__file__).parent)
        except ValueError:
            shown = out_path.name
        log(f"  bullpen: wrote {shown}")
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _season = int(sys.argv[1]) if len(sys.argv) > 1 else None
    _limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    export(_season, leverage_limit=_limit)
