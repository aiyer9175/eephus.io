# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - Starter Leaderboards sidecar (data/starter_leaderboards.json).

The starter analog of bullpen_export.py. Assembles the SEM+ starter board + team
Rotation+ from the SAME reachable source (MLB StatsAPI season pitching leaderboard;
FanGraphs is 403-blocked here). No leverage walk: starters are not leverage-
deployed, so SEM+ is a pure-skill FIP index with durability (IP/GS/average start
length) shown as context. No SwStr% here: the Starter record carries no such
field (the reliever board's bref enrichment was never plumbed through).

Feeds sem_plus.score_pool(), which filters to true starters, anchors SEM+ to the
starter pool (100 = average qualified starter), and rolls up team rotations. Also
builds the yearly starter-history file for the /mlbstats/ history tabs.

Run: `python starter_export.py [season]`  or  `python starter_export.py history`.
Wired into run_monthly (best-effort). NETWORK-GATED + BEST-EFFORT: nothing
fetches at import; any pull failure logs and returns 0 rather than aborting.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import sem_plus
from sem_plus import Starter
# reuse the reliever board's StatsAPI loader (season pitching)
from bullpen_export import load_season_pitching, ip_to_float, _num

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "starter_leaderboards.json"
HISTORY_PATH = DATA_DIR / "starter_history.json"
MULTIYR_PATH = DATA_DIR / "sem_plus_multiyear_eval.json"
EVAL_PATH = DATA_DIR / "sem_plus_eval.json"
HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]


def build_starters(rows: list[dict], swstr: Optional[dict] = None) -> list[Starter]:
    """StatsAPI season rows -> Starter records. `swstr` is accepted for
    legacy positional callers (tools/*) but IGNORED: Starter has no SwStr
    field, so the export no longer pays for the bref pull."""
    out: list[Starter] = []
    for r in rows:
        mlbam = r.get("mlbam")
        if mlbam is None:
            continue
        out.append(Starter(
            key=str(mlbam), name=str(r.get("name", "")), team=str(r.get("team", "")),
            mlbam=int(mlbam),
            g=_num(r.get("G")) or 0.0, gs=_num(r.get("GS")) or 0.0,
            ip=ip_to_float(r.get("IP")), tbf=_num(r.get("BF")) or 0.0,
            so=_num(r.get("SO")) or 0.0, bb=_num(r.get("BB")) or 0.0,
            hbp=_num(r.get("HBP")) or 0.0, hr=_num(r.get("HR")) or 0.0,
            er=_num(r.get("ER")) or 0.0, r=_num(r.get("R")) or 0.0,
            pit=_num(r.get("Pit")) or 0.0, strikes=_num(r.get("Strk")) or 0.0,
            cg=_num(r.get("CG")) or 0.0,
            go=_num(r.get("GO")) or 0.0, ao=_num(r.get("AO")) or 0.0,
        ))
    return out


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
    fs = j.get("forward_spearman_vs_RA9_next") or {}
    v = j.get("verdict") or {}
    return {
        "status": v.get("status") or "provisional",
        "n_pairs": j.get("n_forward_pairs"),
        "seasons": len(j.get("seasons") or []),
        "rho_sem_plus": fs.get("sem_plus"),
        "rho_fip": fs.get("raw_fip"),
        "rho_era": fs.get("era"),
        "disclaimer": ("SEM+ predicts next-year run prevention out of sample. Durability "
                       "(innings, games started, average start length) is shown as context "
                       "because it is workload, not run-prevention rate."),
    }


def _join_sem_plus_3yr(starters: list[dict]) -> int:
    """Stamp sem_plus_3yr / percentile / tag from the multi-year artifact
    (tools/sem_plus_lab.py). Companion SKILL column; missing artifact or
    unmatched player -> fields absent, column renders blank. Returns rows
    stamped."""
    try:
        pv = json.loads(MULTIYR_PATH.read_text(encoding="utf-8"))["proposed_values"]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return 0
    n = 0
    for s in starters:
        p = players.get(str(s.get("mlbam") or ""))
        if not p:
            continue
        s["sem_plus_3yr"] = p.get("sem_plus_3yr")
        s["sem_plus_3yr_pct"] = p.get("pct")
        s["sem_plus_3yr_tag"] = p.get("tag")
        if s["sem_plus_3yr"] is not None:
            n += 1
    return n


_XSEM_MIN_PA = 150.0   # min Savant batters-faced for a stable xwOBA-allowed read (starters face more)


def _join_xsem_plus(starters: list[dict], season: int) -> int:
    """Stamp xSEM+ (deserved run prevention on Savant expected wOBA-allowed) + Luck
    onto tracked starters. Mirror of bullpen_export._join_xrem_plus, anchored over
    the STARTER board so 100 = the average starter.

    HONEST FRAMING (loss ledger): Statcast xwOBA-allowed was tested against FIP for
    SEM+ and did NOT win, so SEM+ stays FIP-based. xSEM+ is a COMPANION deserved-
    suppression read plus a luck residual, NOT a more predictive replacement.
    Inverts the ratio (lower allowed xwOBA = higher +). Luck = actual minus expected
    wOBA-allowed (positive = unlucky). Best-effort."""
    try:
        import mlb_player_export as mpe
        rows = mpe._savant("expected", int(season), "pitcher")
    except Exception:   # noqa: BLE001 - best-effort
        return 0
    board = {int(s["mlbam"]) for s in starters if s.get("mlbam") is not None}
    xw: dict[int, tuple[float, float]] = {}
    luck_by: dict[int, float] = {}
    for r in rows:
        try:
            mid = int(r["player_id"]); ew = float(r["est_woba"]); pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if mid not in board or pa < _XSEM_MIN_PA or ew <= 0:
            continue
        xw[mid] = (ew, pa)
        try:
            luck_by[mid] = round(float(r["woba"]) - ew, 3)
        except (TypeError, ValueError, KeyError):
            pass
    if not xw:
        return 0
    dtot = sum(pa for _, pa in xw.values())
    pool = (sum(x * pa for x, pa in xw.values()) / dtot) if dtot else None
    if not pool:
        return 0
    n = 0
    for s in starters:
        ent = xw.get(int(s["mlbam"])) if s.get("mlbam") is not None else None
        if not ent:
            continue
        s["xsem_plus"] = int(round(100.0 * pool / ent[0]))   # INVERTED: lower allowed = higher
        s["xwoba_against"] = round(ent[0], 3)
        mid = int(s["mlbam"])
        if mid in luck_by:
            s["luck"] = luck_by[mid]
        n += 1
    return n


def export(season: Optional[int] = None, *, out_path: Optional[Path] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    """Build data/starter_leaderboards.json and return the starter count."""
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  starters: loading {season} StatsAPI season pitching...")
    rows = load_season_pitching(season)
    if not rows:
        log(f"  starters: no pitching data for {season} (source blocked or empty); skipping")
        return 0
    scored = sem_plus.score_pool(build_starters(rows))
    n_s3 = _join_sem_plus_3yr(scored["starters"])
    if n_s3:
        log(f"  starters: 3-year SEM+ joined for {n_s3} starters")
    n_xs = _join_xsem_plus(scored["starters"], season)
    if n_xs:
        log(f"  starters: xSEM+ (Savant deserved run prevention) joined for {n_xs} starters")

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "verdict": _verdict(), "backtest": _backtest(),
        "pool": scored["pool"], "starters": scored["starters"], "teams": scored["teams"],
    }
    n = len(scored["starters"])
    log(f"  starters: {n} starters ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(scored['teams'])} rotations")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  starters: wrote {out_path.name}")
    return n


_HISTORY_FIELDS = ("mlbam", "name", "team", "sem_plus", "role", "ip", "g", "gs",
                   "tbf", "cg", "era", "fip", "k_pct", "bb_pct", "k_bb_pct",
                   "gb_pct", "ip_per_gs", "hr9", "qualified")


def export_history(seasons=None, *, out_path: Optional[Path] = None,
                   write: bool = True, log=print) -> dict:
    """Build data/starter_history.json - per-season qualified-starter boards for
    the /mlbstats/ yearly history tabs. One StatsAPI call per season, no walk."""
    seasons = list(seasons or HISTORY_SEASONS)
    out_path = out_path or HISTORY_PATH
    hist = {}
    for y in seasons:
        log(f"  starter-history: {y}...")
        rows = load_season_pitching(y)
        if not rows:
            log(f"  starter-history: no data for {y}; skipping")
            continue
        scored = sem_plus.score_pool(build_starters(rows))
        board = [{k: s.get(k) for k in _HISTORY_FIELDS}
                 for s in scored["starters"] if s.get("qualified")]
        board.sort(key=lambda s: (s.get("sem_plus") or -999), reverse=True)
        hist[str(y)] = {"season": y, "n_qualified": len(board), "starters": board}
        log(f"  starter-history: {y} -> {len(board)} qualified")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Per-season qualified-starter boards for the yearly history tabs. SEM+ is "
                 "the pure-skill starter run-prevention index (100 = average qualified "
                 "starter); durability columns are context."),
        "history": hist,
    }
    if write and hist:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  starter-history: wrote {out_path.name} ({len(hist)} seasons)")
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        _yrs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
        export_history(_yrs)
    else:
        _season = int(sys.argv[1]) if len(sys.argv) > 1 else None
        export(_season)
