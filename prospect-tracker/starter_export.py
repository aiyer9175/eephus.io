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
# reuse the reliever board's StatsAPI loader (season pitching) and the shared
# WAR-rate machinery (bullpen_export is the base of the /mlbstats/ export chain)
from bullpen_export import (load_season_pitching, ip_to_float, _num,
                            score_war_rate, join_war_rate_3yr,
                            guard_nonempty_block, team_basis_meta, basis_rows_for,
                            _active_mlbam_ids,
                            WAR_RATE_POOL_MIN_IP, WAR_RATE_DISPLAY_MIN_SP_IP)

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "starter_leaderboards.json"
HISTORY_PATH = DATA_DIR / "starter_history.json"
MULTIYR_PATH = DATA_DIR / "sem_plus_multiyear_eval.json"
EVAL_PATH = DATA_DIR / "sem_plus_eval.json"
HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]


def _war_source_vintage() -> dict:
    """The served eWAR build stamp, or a stated absence. Never raises: a board
    that cannot report its vintage must still render (audit F10-02)."""
    try:
        import war_source as _ws
        return _ws.ewar_vintage()
    except Exception as e:   # noqa: BLE001 - reporting must not take a board down
        return {"artifact_generated_at": None, "stale": None,
                "reason": f"war_source.ewar_vintage unavailable ({type(e).__name__})"}


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


def _join_sem_plus_3yr(starters: list[dict]) -> dict:
    """Stamp sem_plus_3yr / percentile / tag from the multi-year artifact
    (tools/sem_plus_lab.py). Companion SKILL column; missing artifact or
    unmatched player -> fields absent, column renders blank.

    VINTAGE, NOT PIPELINE OUTPUT (mirrors bullpen_export._join_rem_plus_3yr):
    the values are read VERBATIM from a FROZEN lab artifact, so a row can show a
    same-day 1-year SEM+ beside a 3-year SEM+ frozen weeks earlier, and a
    starter who entered the pool after the lab ran is blank. Returns the
    artifact's vintage block so the payload can carry it and the frontend can
    disclose it instead of the divergence being silent."""
    meta = {"source": MULTIYR_PATH.name, "n_stamped": 0, "available": False}
    try:
        art = json.loads(MULTIYR_PATH.read_text(encoding="utf-8"))
        pv = art["proposed_values"]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return meta
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
    meta.update({
        "available": True,
        "n_stamped": n,
        "generated_at": art.get("generated_at"),
        "season": pv.get("season"),
        "window": pv.get("window"),
        "n_in_artifact": len(players),
        "note": ("3-year SEM+ is FROZEN lab output read verbatim from "
                 f"{MULTIYR_PATH.name}, not recomputed by this run. It is as of "
                 "generated_at, NOT as of this board's as_of date, and starters "
                 "who joined the pool after that date have no value."),
    })
    return meta


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


def _join_war_ip_plus(starters: list[dict], season: int) -> dict:
    """STARTER-anchored WAR/IP+: 100 = the average starter's pitching eWAR per
    inning (FIP re-priced within role from the 2026-09 epoch), on the 100 + 10z scale (convention 3, ten points per pool sigma).

    Deliberately a SEPARATE metric from the reliever-anchored WAR/IP+ in
    bullpen_export, exactly as SEM+ and REM+ are separate rather than one pooled
    pitcher index. A starter and a reliever do not sit in one WAR-per-inning
    population: relievers bank more WAR per inning at the same talent because
    they pitch in shorter bursts, so pooling them would rank every setup man
    above every number-three starter (ARKMETRIC_SCALE_CONVENTIONS.md:77). The
    anchor pool is named in the column title and in the glossary entry.

    Best-effort: WAR unavailable or degenerate -> nothing stamped, column
    blank."""
    return score_war_rate(
        starters, season, side="pit", denom_key="ip",
        pool_min=WAR_RATE_POOL_MIN_IP, display_min=WAR_RATE_DISPLAY_MIN_SP_IP,
        out_key="war_ip_plus", anchor="starters with 20+ IP")


def _join_war_ip_plus_3yr(starters: list[dict]) -> dict:
    """Frozen trailing-window WAR/IP+ on the starter block of
    data/war_rate_plus_multiyear_eval.json. Vintage, not pipeline output: see
    bullpen_export.join_war_rate_3yr for the full disclosure contract."""
    return join_war_rate_3yr(starters, "sp", "war_ip_plus_3yr", "starters")


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
    # TODAY'S ROTATION, not everyone who started a game this year. 78 of 226
    # rotation slots (34.5%) were held by arms off an active roster.
    active_ids = _active_mlbam_ids(int(season))
    scored = sem_plus.score_pool(build_starters(rows), active_ids=active_ids)
    s3_meta = _join_sem_plus_3yr(scored["starters"])
    if s3_meta.get("n_stamped"):
        log(f"  starters: 3-year SEM+ joined for {s3_meta['n_stamped']} starters "
            f"(frozen lab vintage {s3_meta.get('generated_at')})")
    n_xs = _join_xsem_plus(scored["starters"], season)
    if n_xs:
        log(f"  starters: xSEM+ (Savant deserved run prevention) joined for {n_xs} starters")
    wr_meta = _join_war_ip_plus(scored["starters"], season)
    if wr_meta.get("available"):
        log(f"  starters: WAR/IP+ (starter-anchored) joined for "
            f"{wr_meta['n_stamped']} starters (pool {wr_meta['pool_n']})")
    elif wr_meta.get("refused"):
        log(f"  starters: WAR/IP+ refused ({wr_meta['refused']})")
    wr3_meta = _join_war_ip_plus_3yr(scored["starters"])
    if wr3_meta.get("n_stamped"):
        log(f"  starters: 3-year WAR/IP+ joined for {wr3_meta['n_stamped']} starters "
            f"(frozen lab vintage {wr3_meta.get('generated_at')})")

    # ZERO-TEAM ROLLUP GUARD. The `if not rows` check above protects the starter
    # rows and protected nothing else: a blanked team code leaves every row intact
    # and empties scored["teams"], which publishes 0 rotations over the 30 that
    # were there and drops Rotation+ to a flat 100. See guard_nonempty_block.
    teams, rollup_meta = guard_nonempty_block(
        scored["teams"], out_path, key="teams", source="starter_leaderboards",
        label="starters", log=log)

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "verdict": _verdict(), "backtest": _backtest(),
        # Vintage of the FROZEN 3-year SEM+ column (see _join_sem_plus_3yr).
        "multiyear": s3_meta,
        # WAR/IP+ scale block (starter anchor pool + measured pool parameters)
        # and the vintage of its FROZEN 3-year companion.
        "war_rate": wr_meta,
        # WHICH BUILD the served eWAR numerator comes from, and whether it has
        # fallen behind the frame under it (audit F10-02 / F11-01). data/ewar.json
        # is hand-built; nothing in the pipeline rebuilds it, so a current-season
        # WAR can sit at the artifact date while the innings beside it are current.
        "ewar_vintage": _war_source_vintage(),
        "multiyear_war_rate": wr3_meta,
        # Which club a row's `team` names, how many rows were repointed, and how
        # many serve a blank team (see bullpen_export.team_basis_meta), plus the
        # zero-rollup guard's verdict for this run.
        "team_basis": team_basis_meta(rows, label=f"pitching {season}"),
        "roster_filter": {
            "applied": active_ids is not None,
            "n_active_roster_ids": (len(active_ids) if active_ids is not None else None),
            "n_dropped_from_constructions": sum(
                int(t.get("n_off_roster_dropped") or 0) for t in (scored.get("teams") or [])),
            "basis": "StatsAPI rosterType=active (26-man)",
            "scope": ("the constructed rotation ladder ONLY; Rotation+ and the other "
                      "aggregates stay on the full season pool"),
            "on_failure": "a failed fetch filters nothing rather than blanking the charts",
        },
        "team_rollup": rollup_meta,
        "pool": scored["pool"], "starters": scored["starters"], "teams": teams,
    }
    n = len(scored["starters"])
    log(f"  starters: {n} starters ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(teams)} rotations")
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
    basis_rows: list[dict] = []
    for y in seasons:
        log(f"  starter-history: {y}...")
        rows = load_season_pitching(y)
        if not rows:
            log(f"  starter-history: no data for {y}; skipping")
            continue
        scored = sem_plus.score_pool(build_starters(rows))
        qual = [s for s in scored["starters"] if s.get("qualified")]
        basis_rows.extend(basis_rows_for(qual, rows))
        board = [{k: s.get(k) for k in _HISTORY_FIELDS} for s in qual]
        board.sort(key=lambda s: (s.get("sem_plus") or -999), reverse=True)
        hist[str(y)] = {"season": y, "n_qualified": len(board), "starters": board}
        log(f"  starter-history: {y} -> {len(board)} qualified")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Per-season qualified-starter boards for the yearly history tabs. SEM+ is "
                 "the pure-skill starter run-prevention index (100 = average qualified "
                 "starter); durability columns are context."),
        "team_basis": team_basis_meta(basis_rows, label="starter history",
                                      scope="history"),
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
