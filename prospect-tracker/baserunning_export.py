# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - the Baserunning section (owner ask 2026-09-30; the eWAR v3
plan's EBR_2_BUILD_DARK; part8/baserunning.md sections 2 and 4.3 as the gate
document docs/ebr-2026-09-30/EBR_GATE.md amends them).

THREE KINDS OF NUMBER, labelled on every header the page draws:
  OFFICIAL    SB, CS, GIDP, PA and R from the StatsAPI season hitting lines
              (playerPool=All, fa_sources.fetch_statsapi_season_stats).
  PUBLISHED, NOT COMPUTED HERE
              FanGraphs' BsR and wSB as MLB's sabermetrics feed publishes them
              (saber_feed.resolve_groups, the stint guard; `ubr` and `wGdp` are
              never read: since 2016 the served BsR is wSB plus Statcast's
              extra-base runs with no double-play part, so those two fields
              describe nothing on a modern row) and Baseball Savant's
              baserunning and basestealing run values, sprint speed, bolts,
              home to first and leads (savant_running, savant_sprint).
  OURS        eBR and its parts, READ from the eBR substrate tools/build_ebr.py
              writes (.cache/ebr/preview/ebr.json): no eBR arithmetic happens
              here, no RE24 is fit here and no MIN_RE_N refusal exists here.
              The by-base steal splits, chances, extra bases taken, tag-ups,
              outs on the bases and double-play chances are COUNTS read off the
              runner record (.cache/pbp_runners), steals keyed on MLB's
              movementReason, never on eventType.

THE eWAR CONTEXT COLUMN reads the displayed WAR through the served provider
(bullpen_export.served_war_basis: eWAR v2 under the owner's EPOCH-Q4 answer) by
the defense_export._stamp_war route, and the frame sentence the column's title
carries is DERIVED from that artifact (_ewar_baserunning_note), never typed on
the page.

DARK. While MLBSTATS_BASERUNNING_LIVE is False every file here lands under
.cache/baserunning/preview/ and nothing under data/ is written (plan Part 8
8.A: a new data/ file ships to the webroot). The flip (EBR_2F_FLIP) turns the
flag, re-runs this exporter into data/ and lands the registry and glossary rows.

DESCRIPTIVE. Same-season numbers only. No year-to-year, split-half or forward
statistic of eBR or of any part is computed here (tools/ebr_gate.py alone does
that, once, on its day), nothing relates a baserunning number to runs scored,
wins or a price, and no betting or fitted module reads a file written here.

Run:  python baserunning_export.py [season]   or   python baserunning_export.py history
"""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import json
import logging
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
PREVIEW_DIR = CACHE_DIR / "baserunning" / "preview"
RECORD_DIR = CACHE_DIR / "pbp_runners"
SUBSTRATE_PREVIEW = CACHE_DIR / "ebr" / "preview" / "ebr.json"
EVAL_PREVIEW = CACHE_DIR / "ebr" / "preview" / "ebr_eval.json"
GATE_DOC = ROOT / "docs" / "ebr-2026-09-30" / "EBR_GATE.md"

#: The section's flag (plan Part 8 8.A, class 2). Flipped by EBR_2F_FLIP.
MLBSTATS_BASERUNNING_LIVE = True
#: The MLB player card's skills.br block (integration.md 3.1), read by
#: mlb_player_export._skill_index off the served board. False until
#: EBR_2F_FLIP, which flipped both flags in one commit (test_ebr_flags.py).
CARD_BASERUNNING_LIVE = True

OUT_NAME = "baserunning_leaderboards.json"
HISTORY_NAME = "baserunning_history.json"
SUBSTRATE_NAME = "ebr.json"
EVAL_NAME = "ebr_eval.json"

#: The seasons with a complete runner record, the history file's seasons (the
#: live season is the board). 2020 has no play-by-play on disk (EBR-Q4).
HISTORY_SEASONS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]

#: The backfilled seasons 2011 to 2017 and 2020 (owner answer EBR-Q4 (b); task
#: EBR_Q4B_HISTORY_BACKFILL) sit in the eBR preview beside the served seasons.
#: While this flag is False every read of the preview here drops them, so the
#: served substrate and eval keep the seasons they had; they reach data/ only
#: by a one-commit re-flip that names the seasons, rows and files it adds.
EBR_BACKFILL_SEASONS_LIVE = False
EBR_BACKFILL_SEASONS = (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2020)
#: The season-keyed blocks of the preview's substrate and eval.
_SEASON_KEYED = ("fg_basis", "re24", "league", "identity", "league_sums", "coverage", "agreement",
                 "arms", "ewar_link")

#: Qualified = the hitter board's rule, so the two boards agree.
QUALIFY_MIN_PA = 200
#: Display floors (baserunning.md 2.3): below a floor the rate is absent.
FLOORS = {"sb_pct": 5, "att_rate": 20, "xbt": 10, "cls": 5, "tag": 5, "gidp": 20}
SPRINT_MIN_RUNS = 10

#: Payload budgets (baserunning.md 4.3), raw bytes and gzip -9 bytes.
BUDGET_LIVE = (600 * 1024, 90 * 1024)
BUDGET_HISTORY = (1300 * 1024, 180 * 1024)

#: An identity miss blocks a season (EBR_GATE.md part 3): SB and CS exact for
#: every player with any, GIDP exact for 97 percent of players with any.
I2_GIDP_MIN_SHARE = 0.97
#: League parts must sum to zero (baserunning.md 4.1; the gate's I4 is 0.01).
LEAGUE_SUM_TOL = 0.05

OOB_REASONS = frozenset(("r_thrown_out", "r_out_stretching", "r_out_returning",
                         "r_doubled_off", "r_rundown", "r_runner_out"))
AIR_EVENTS = frozenset(("field_out", "sac_fly", "double_play", "sac_fly_double_play"))
_BASE_NUM = {"1B": 1, "2B": 2, "3B": 3}
_SCORE = ("score", "4B")


class BaserunningRefusal(RuntimeError):
    """A build that must not publish: the message names the season and the cause."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def out_dir() -> Path:
    """data/ only once the flag is flipped; the preview directory until then."""
    return DATA_DIR if MLBSTATS_BASERUNNING_LIVE else PREVIEW_DIR


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _isna(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v) in ("<NA>", "nan")


def _int(v):
    return None if _isna(v) else int(v)


def _num(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _r1(v):
    return None if v is None else round(float(v), 1)


def _r3(v):
    return None if v is None else round(float(v), 3)


def _rate(num_, den, floor):
    """A rate only with its numerator and denominator on the row and the
    denominator at or above the floor; absent otherwise (null, never zero)."""
    if den is None or den < floor or den <= 0:
        return None
    return round(num_ / den, 3)


def _mtime_iso(path: Path) -> Optional[str]:
    try:
        ts = Path(path).stat().st_mtime
    except OSError:
        return None
    return _dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, obj, *, indent=1) -> int:
    path = Path(path)
    if DATA_DIR in path.parents and not MLBSTATS_BASERUNNING_LIVE:
        raise BaserunningRefusal(f"{path.name}: data/ is not written while MLBSTATS_BASERUNNING_LIVE is False")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, indent=indent, separators=(",", ":") if indent is None else (",", ": "))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(path)
    return len(raw.encode("utf-8"))


def _sizes(obj, indent=1) -> tuple[int, int]:
    raw = json.dumps(obj, indent=indent, separators=(",", ":") if indent is None else (",", ": ")).encode("utf-8")
    return len(raw), len(gzip.compress(raw, 9))


# --------------------------------------------------------------------------- #
# the eBR substrate and eval (read, never computed here)
# --------------------------------------------------------------------------- #
def without_backfill(doc):
    """The eBR preview's substrate or eval without the backfilled seasons
    (EBR_BACKFILL_SEASONS) while EBR_BACKFILL_SEASONS_LIVE is False; key order kept."""
    if EBR_BACKFILL_SEASONS_LIVE or not isinstance(doc, dict):
        return doc
    hs = {str(y) for y in EBR_BACKFILL_SEASONS}

    def keyed(d):
        return {k: v for k, v in d.items() if str(k) not in hs} if isinstance(d, dict) else d

    def listed(v):
        return [y for y in v if str(y) not in hs] if isinstance(v, list) else v
    out = dict(doc)
    for k in _SEASON_KEYED:
        if k in out:
            out[k] = keyed(out[k])
    if "seasons" in out:
        out["seasons"] = listed(out["seasons"])
    if isinstance(out.get("stamps"), dict) and "re24_sha256" in out["stamps"]:
        out["stamps"] = dict(out["stamps"], re24_sha256=keyed(out["stamps"]["re24_sha256"]))
    if isinstance(out.get("cadence"), dict):
        cad = dict(out["cadence"])
        if "frozen_digests" in cad:
            cad["frozen_digests"] = keyed(cad["frozen_digests"])
        if "frozen_seasons" in cad:
            cad["frozen_seasons"] = listed(cad["frozen_seasons"])
        out["cadence"] = cad
    F = out.get("fields")
    if isinstance(out.get("rows"), list) and isinstance(F, list) and "season" in F:
        i = F.index("season")
        out["rows"] = [r for r in out["rows"] if str(r[i]) not in hs]
    return out


def load_substrate(path: Path = SUBSTRATE_PREVIEW) -> dict:
    sub = without_backfill(_read_json(path))
    if not isinstance(sub, dict) or not sub.get("rows") or sub.get("ebr_version") is None:
        raise BaserunningRefusal(f"the eBR substrate is absent or empty at {path}; run tools/build_ebr.py first")
    return sub


def substrate_by_season(sub: dict) -> dict[int, dict[int, dict]]:
    """{season: {mlbam: {part: runs, pa, starts_on_base, opp_*, stints}}}."""
    F = sub["fields"]
    ix = {f: F.index(f) for f in F}
    out: dict[int, dict[int, dict]] = defaultdict(dict)
    for r in sub["rows"]:
        d = {f: r[ix[f]] for f in F}
        out[int(d["season"])][int(d["mlbam"])] = d
    return out


def display_parts(d: dict) -> dict:
    """The gate document's display parts (2.7) from a substrate row."""
    sb = (d.get("sb") or 0.0) + (d.get("pk") or 0.0)
    xb = (d.get("xb_adv") or 0.0) + (d.get("xb_oob") or 0.0)
    dp = d.get("dp") or 0.0
    return {"ebr": round(sb + xb + dp, 3), "ebr_sb": round(sb, 3), "ebr_xb": round(xb, 3),
            "ebr_dp": round(dp, 3),
            # The published sub-total of part 2.7: outs on the bases (eXB_oob + ePK).
            "ebr_oob": round((d.get("xb_oob") or 0.0) + (d.get("pk") or 0.0), 3)}


# --------------------------------------------------------------------------- #
# the runner record: counts (never run values)
# --------------------------------------------------------------------------- #
def load_record_season(season: int, record: Path = RECORD_DIR):
    """(pa, rn, manifest block) for one MLB season of the runner record."""
    import pandas as pd
    man = _read_json(Path(record) / "manifest.json") or {}
    blk = (man.get("seasons") or {}).get(str(int(season)))
    if not blk:
        return None, None, None
    pa = pd.read_parquet(Path(record) / blk["files"]["pa"])
    rn = pd.read_parquet(Path(record) / blk["files"]["runners"])
    blk = dict(blk, built_at=man.get("built_at"))
    return pa, rn, blk


def _blank_counts() -> dict:
    return {"sb2": 0, "sb3": 0, "sbh": 0, "cs2": 0, "cs3": 0, "csh": 0,
            "pk1": 0, "pk2": 0, "pk3": 0, "opp_sb2": 0, "opp_sb3": 0, "opp_sbh": 0,
            "x13": [0, 0], "x2h": [0, 0], "x1h": [0, 0], "tag3h": [0, 0], "tag23": [0, 0],
            "oob": 0, "adv_err": 0, "gdp_opp": 0, "gidp_pbp": 0, "starts": 0}


def _end_of(entries: list, k: int):
    """A runner's end from his entries in play order: 'out', 4 (scored), a base
    number, or his own base when he has no entry (held). 'err' when his
    advance carried an error credit (left out of both sides, counted in adv_err)."""
    if not entries:
        return k
    if any(bool(e.error_credit) for e in entries):
        return "err"
    if any(bool(e.is_out) for e in entries):
        return "out"
    end = entries[-1].end
    if end in _SCORE:
        return 4
    if end in _BASE_NUM:
        return _BASE_NUM[end]
    return k


def record_counts(pa, rn) -> dict:
    """{"runners": {mlbam: counts}, "teams": {team_id: counts},
    "runner_team": {mlbam: {team_id: starts on base + PA}}} for one season.
    Every number is a count from MLB's play-by-play (baserunning.md 2.2)."""
    runners: dict[int, dict] = defaultdict(_blank_counts)
    teams: dict[int, dict] = defaultdict(_blank_counts)
    runner_team: dict[int, dict] = defaultdict(lambda: defaultdict(int))

    def bump(mid, team, key, taken=None):
        for d in (runners[mid], teams[team] if team is not None else None):
            if d is None:
                continue
            if taken is None:
                d[key] += 1
            else:
                d[key][1] += 1
                d[key][0] += int(taken)

    # Steals, caught stealing, pickoffs and outs on the bases: the runner entries.
    reasons = rn["movement_reason"].fillna("").astype(str).tolist()
    cols = (rn["runner_id"].tolist(), rn["bat_team_id"].tolist(), rn["is_out"].tolist())
    for reason, rid, team, is_out in zip(reasons, *cols):
        rid, team = _int(rid), _int(team)
        if rid is None:
            continue
        # Every entry votes for the batting club, so a runner who never began
        # a plate appearance on base (a pinch runner retired before the next
        # batter) still resolves an earned club.
        runner_team[rid][team] += 1
        if not reason:
            continue
        if reason.startswith("r_stolen_base_"):
            bump(rid, team, {"2b": "sb2", "3b": "sb3", "home": "sbh"}.get(reason.rsplit("_", 1)[-1], "sb2"))
        elif reason.startswith(("r_caught_stealing_", "r_pickoff_caught_stealing_")):
            bump(rid, team, {"2b": "cs2", "3b": "cs3", "home": "csh"}.get(reason.rsplit("_", 1)[-1], "cs2"))
        elif reason in ("r_pickoff_1b", "r_pickoff_2b", "r_pickoff_3b") and bool(is_out):
            bump(rid, team, "pk" + reason[-2])
        elif reason in OOB_REASONS and bool(is_out):
            bump(rid, team, "oob")

    by_pa: dict = defaultdict(list)
    for e in rn.itertuples(index=False):
        by_pa[(e.game_pk, e.at_bat_index)].append(e)

    for p in pa.itertuples(index=False):
        if not bool(p.is_pa):
            continue
        team = _int(p.bat_team_id)
        batter = _int(p.batter_id)
        on1, on2, on3 = _int(p.on_first), _int(p.on_second), _int(p.on_third)
        if batter is not None:
            runner_team[batter][team] += 1
        # Chances at the start of the plate appearance (the pre-play state).
        if on1 is not None:
            runner_team[on1][team] += 1
            bump(on1, team, "starts")
            if on2 is None:
                bump(on1, team, "opp_sb2")
        if on2 is not None:
            runner_team[on2][team] += 1
            bump(on2, team, "starts")
            if on3 is None:
                bump(on2, team, "opp_sb3")
        if on3 is not None:
            runner_team[on3][team] += 1
            bump(on3, team, "starts")
            bump(on3, team, "opp_sbh")
        # Double-play chances at the final pitch: a runner on first, under two out.
        f1 = _int(p.fp_on_first)
        fo = _int(p.fp_outs) or 0
        if batter is not None and f1 is not None and fo < 2:
            bump(batter, team, "gdp_opp")
            if p.event_type == "grounded_into_double_play":
                bump(batter, team, "gidp_pbp")
        if _isna(p.in_play_index):
            continue
        ip = int(p.in_play_index)
        ents = sorted((e for e in by_pa.get((p.game_pk, p.at_bat_index), ()) if int(e.play_index) >= ip),
                      key=lambda e: e.seq)
        by_runner: dict = defaultdict(list)
        for e in ents:
            if not _isna(e.runner_id):
                by_runner[int(e.runner_id)].append(e)
        fon = {1: f1, 2: _int(p.fp_on_second), 3: _int(p.fp_on_third)}
        ends = {k: _end_of(by_runner.get(fon[k], []), k) for k in (1, 2, 3) if fon[k] is not None}
        et = p.event_type
        traj = None if _isna(p.trajectory) else str(p.trajectory)

        def blocked_ahead(k):
            # A runner ahead who ended ON third held the base the trailing
            # runner needed; home cannot be held. The chance is not counted.
            return any(ends.get(j) == 3 for j in (2, 3) if j > k and fon.get(j) is not None)

        def record(k, key, taken_when):
            rid = fon[k]
            end = ends[k]
            if end == "err":
                bump(rid, team, "adv_err")
                return
            if blocked_ahead(k):
                return
            bump(rid, team, key, taken=(end in taken_when))

        if et in ("single", "double"):
            if et == "single":
                if fon[1] is not None:
                    record(1, "x13", (3, 4))
                if fon[2] is not None:
                    record(2, "x2h", (4,))
            else:
                if fon[1] is not None:
                    record(1, "x1h", (4,))
        elif traj == "fly_ball" and et in AIR_EVENTS and fo < 2:
            if fon[3] is not None:
                record(3, "tag3h", (4,))
            if fon[2] is not None:
                record(2, "tag23", (3, 4))
    return {"runners": dict(runners), "teams": dict(teams),
            "runner_team": {k: dict(v) for k, v in runner_team.items()}}


# --------------------------------------------------------------------------- #
# the comparators (display columns, credited; never a model input)
# --------------------------------------------------------------------------- #
def load_official(season: int) -> tuple[dict[int, dict], dict]:
    """{mlbam: official line} from the StatsAPI season hitting leaderboard
    (playerPool=All), one row per player; a traded player carries the season
    total. Offline-safe: an unreachable feed returns ({}, note)."""
    import fa_sources
    try:
        rows = fa_sources.fetch_statsapi_season_stats(int(season), "hitting")
    except Exception as e:  # noqa: BLE001
        _log.warning("StatsAPI season hitting (%s) failed: %s", season, e)
        rows = []
    out: dict[int, dict] = {}
    for r in rows or []:
        pl = r.get("player") or {}
        st = r.get("stat") or {}
        pid = pl.get("id")
        if pid is None:
            continue
        tm = r.get("team") or {}
        out[int(pid)] = {
            "name": pl.get("fullName", ""), "team_id": tm.get("id") if isinstance(tm, dict) else None,
            "pos": (r.get("position") or {}).get("abbreviation"),
            "pa": int(st.get("plateAppearances") or 0), "sb": int(st.get("stolenBases") or 0),
            "cs": int(st.get("caughtStealing") or 0), "gidp": int(st.get("groundIntoDoublePlay") or 0),
            "r": int(st.get("runs") or 0), "g": int(st.get("gamesPlayed") or 0),
        }
    cache = CACHE_DIR / f"fa_statsapi_hitting_{int(season)}.json"
    return out, {"source": "statsapi season hitting (playerPool=All)",
                 "fetched_at": _mtime_iso(cache), "n_rows": len(out)}


def load_published(season: int) -> dict:
    """FanGraphs' BsR and wSB per MLBAM from MLB's sabermetrics feed, through
    the stint guard. `ubr` and `wGdp` are never read."""
    import saber_feed
    meta = {"source": "statsapi sabermetrics (FanGraphs BsR, wSB)", "available": False,
            "n_feed_players": 0, "n_joined": 0, "n_eligible": 0, "hit_rate_eligible": None,
            "n_multi_team": 0, "n_ambiguous": 0, "ambiguous_ids": [], "not_read": ["ubr", "wGdp"],
            "note": ("PUBLISHED, NOT COMPUTED HERE. FanGraphs' baserunning runs as MLB's feed "
                     "publishes them, joined by MLBAM id; a traded player reads one season line. "
                     "Since 2016 the served BsR is wSB plus Statcast's extra-base runner runs with "
                     "no double-play part, so the feed's ubr and wGdp fields are not read."),
            "values": {}}
    splits = saber_feed.fetch_splits(int(season)) or []
    if not splits:
        return meta
    rows, ambiguous, n_multi = saber_feed.resolve_groups(splits)
    vals: dict[int, dict] = {}
    for pid, row in rows.items():
        st = row.get("stat") or {}
        bsr = saber_feed.run_value(st.get("baseRunning"))
        wsb = saber_feed.run_value(st.get("wSb"))
        if bsr is None and wsb is None:
            continue
        vals[int(pid)] = {"bsr": bsr, "wsb": wsb}
    meta.update({"available": bool(vals), "n_feed_players": len(rows), "n_multi_team": n_multi,
                 "n_ambiguous": len(ambiguous), "ambiguous_ids": ambiguous, "values": vals,
                 "fetched_at": _mtime_iso(CACHE_DIR / f"statsapi_saber_hitting_{int(season)}.json")})
    return meta


def load_savant(season: int, *, offline: bool = True) -> dict:
    """Savant's two run-value boards for the season, from savant_running's cache."""
    import savant_running
    try:
        sv = savant_running.load(int(season), offline=offline)
    except Exception as e:  # noqa: BLE001
        _log.warning("savant running %s unavailable (%s)", season, e)
        sv = {"brv": {}, "steal": {}, "fetched_at": {}}
    return {"brv": sv.get("brv") or {}, "steal": sv.get("steal") or {},
            "fetched_at": sv.get("fetched_at") or {},
            "urls": {b: savant_running.BOARDS[b].format(y=int(season)) for b in savant_running.BOARDS}}


def load_sprint(season: int) -> tuple[dict[int, dict], dict]:
    """{mlbam: sprint row} for the season. The live season's CSV cache
    (savant_sprint's own, refreshed by the nightly through savant_running
    .sprint_rows) wins over data/savant_sprint.json, which this module never
    writes (the Alchemy Lab's Rng+ reads it)."""
    import savant_sprint
    out: dict[int, dict] = {}
    src = None
    csv_path = savant_sprint._cache_path(int(season))
    if csv_path.exists():
        try:
            for r in savant_sprint.parse_rows(csv_path.read_text(encoding="utf-8-sig"), int(season)):
                out[int(r["mlbam"])] = r
            src = csv_path
        except (OSError, ValueError, KeyError):
            out = {}
    if not out:
        blob = _read_json(DATA_DIR / "savant_sprint.json") or {}
        for mid, by in (blob.get("by_mlbam") or {}).items():
            v = (by or {}).get(str(int(season))) if isinstance(by, dict) else None
            if isinstance(v, dict) and v.get("ft_s") is not None:
                out[int(mid)] = dict(v)
        src = DATA_DIR / "savant_sprint.json" if out else None
    return out, {"source": "Baseball Savant sprint speed leaderboard",
                 "source_url": savant_sprint.BASE.format(y=int(season)) if hasattr(savant_sprint, "BASE") else None,
                 "fetched_at": _mtime_iso(src) if src else None, "min_runs": SPRINT_MIN_RUNS}


def load_links() -> dict:
    """PROSPX card keys and graduates by MLBAM (fail-soft)."""
    pl = _read_json(DATA_DIR / "player_links.json") or {}
    return pl.get("byMlbam") or {}


def load_debuts() -> tuple[dict[int, str], Optional[str]]:
    """{mlbam: debut_date} from data/debuts.json (fail-soft)."""
    d = _read_json(DATA_DIR / "debuts.json")
    recs = d if isinstance(d, list) else ((d or {}).get("records") or (d or {}).get("debuts") or [])
    out: dict[int, str] = {}
    gen = (d or {}).get("generated_at") if isinstance(d, dict) else None
    for r in recs or []:
        mid, dd = r.get("mlbam_id"), r.get("debut_date")
        if mid is not None and dd:
            out[int(mid)] = str(dd)
    return out, gen


def _war_provider() -> str:
    """The provider the displayed WAR column reads (the display door,
    bullpen_export.served_war_basis), named in the payload so a reader of the
    file knows which series the column is."""
    try:
        from bullpen_export import served_war_basis
        return (served_war_basis() or {}).get("war_provider") or ""
    except Exception:  # noqa: BLE001
        return ""


def _ewar_baserunning_note() -> str:
    """The ONE sentence the eWAR column's title says about the baserunning
    frame inside the displayed WAR, DERIVED from the served provider and its
    artifact (the defense_export._ewar_fielding_note rule), never typed on the
    page. The provider is the display door (bullpen_export.served_war_basis:
    eWAR v2 under EPOCH-Q4); its artifact's `baserunning_source` sentence rides
    verbatim when it exists, else the frame is read off the artifact's own
    field key (eWAR v2 carries Baseball-Reference's runs_br and runs_dp inside
    bWAR, untouched: ewar.py THE FRAME)."""
    try:
        from bullpen_export import served_war_basis
        prov = (served_war_basis() or {}).get("war_provider") or ""
    except Exception:  # noqa: BLE001 - absence is a reportable state
        prov = ""
    if prov == "ewar_v2":
        try:
            import ewar as _ewar
            doc = _ewar.load() or {}
        except Exception:  # noqa: BLE001
            doc = {}
        meta = doc.get("meta") or {}
        src_ = meta.get("baserunning_source")
        if isinstance(src_, str) and src_.strip():
            s = src_.strip()
            return s if (s[:1].isupper() and s.endswith(".")) else "Its baserunning comes from " + s + "."
        fk = doc.get("field_key") or {}
        if "rr" in fk and "rd" in fk and not meta.get("swap_baserunning"):
            return ("Its baserunning is Baseball-Reference's (runs_br and runs_dp carried inside "
                    "bWAR), a different frame from eBR and BsR.")
        return "The frame behind eWAR's baserunning could not be read from data/ewar.json this run."
    if prov == "fwar":
        return "Its baserunning is FanGraphs' published BsR, the column beside eBR here."
    if prov:
        return f"Its baserunning frame is the served provider's ({prov})."
    return "The frame behind eWAR's baserunning could not be read this run."


def _stamp_war(rows: list[dict], season: int) -> dict:
    """Whole-player WAR on the displayed series, by the Defense board's route."""
    try:
        from defense_export import _stamp_war as _dsw
        return _dsw(rows, int(season))
    except Exception as e:  # noqa: BLE001 - a context column never takes a board down
        _log.warning("baserunning eWAR unavailable (%s)", e)
        return {"available": False, "refused": f"WAR route unavailable: {e}", "n_stamped": 0,
                "n_rows": len(rows), "n_with_id": 0, "n_covered": 0, "n_two_sided": 0,
                "basis": "bat + pit, summed unrounded and rounded once"}


def bem_plus_status(gate_doc: Path = GATE_DOC) -> dict:
    """BEM+ is served only when the gate document's part 12.1 records a PASS
    (EBR_GATE.md 5.8; owner answer EBR-Q3 (a)). Read, never decided here."""
    try:
        txt = Path(gate_doc).read_text(encoding="utf-8")
    except OSError:
        return {"served": False, "reason": "gate document unreadable"}
    m = re.search(r"### 12\.1(.*?)(?:### 12\.2|\Z)", txt, re.S)
    block = m.group(1) if m else ""
    if re.search(r"BEM\+[^\n]*\bPASS\b", block) and "EMPTY" not in block[:200]:
        return {"served": True, "reason": "EBR_GATE.md part 12.1 records a BEM+ PASS"}
    return {"served": False, "reason": "EBR_GATE.md part 12.1 records no BEM+ PASS"}


# --------------------------------------------------------------------------- #
# rows
# --------------------------------------------------------------------------- #
def _percentiles(vals: dict[int, float]) -> dict[int, int]:
    """Mid-rank percentile among every tracked player, nearest whole number."""
    if not vals:
        return {}
    xs = sorted(vals.values())
    n = len(xs)
    out = {}
    from bisect import bisect_left, bisect_right
    for mid, v in vals.items():
        below = bisect_left(xs, v)
        eq = bisect_right(xs, v) - below
        out[mid] = int(math.floor((below + eq / 2) / n * 100 + 0.5))
    return out


def _row_rates(r: dict) -> None:
    r["sb_pct"] = _rate(r["sb"], (r["sb"] + r["cs"]), FLOORS["sb_pct"])
    r["att_rate"] = _rate(r["sb2"] + r["sb3"] + r["cs2"] + r["cs3"], r["opp_sb2"] + r["opp_sb3"], FLOORS["att_rate"])
    r["xbt"] = r["x13"][0] + r["x2h"][0] + r["x1h"][0]
    r["xbt_opp"] = r["x13"][1] + r["x2h"][1] + r["x1h"][1]
    r["xbt_pct"] = _rate(r["xbt"], r["xbt_opp"], FLOORS["xbt"])
    r["tag"] = [r["tag3h"][0] + r["tag23"][0], r["tag3h"][1] + r["tag23"][1]]
    r["tag_pct"] = _rate(r["tag"][0], r["tag"][1], FLOORS["tag"])
    r["gidp_pct"] = _rate(r["gidp_pbp"], r["gdp_opp"], FLOORS["gidp"])


def build_rows(season: int, *, official: dict[int, dict], counts: dict, sub_rows: dict[int, dict],
               published: dict, savant: dict, sprint: dict[int, dict], tmap: dict,
               links: dict, debuts: dict[int, str]) -> list[dict]:
    """One row per runner with an official line or an eBR row this season."""
    pct = _percentiles({m: float(v["ft_s"]) for m, v in sprint.items()
                        if v.get("ft_s") is not None and (v.get("runs") or 0) >= SPRINT_MIN_RUNS})
    pub = published.get("values") or {}
    ids = set(official) | set(sub_rows)
    rows = []
    for mid in sorted(ids):
        off = official.get(mid) or {}
        c = counts["runners"].get(mid) or _blank_counts()
        d = sub_rows.get(mid) or {}
        lk = links.get(str(mid)) or {}
        name = off.get("name") or lk.get("name") or ""
        team = tmap.get(off.get("team_id")) or ""
        if not team and d.get("stints") is None and counts["runner_team"].get(mid):
            tid = max(counts["runner_team"][mid].items(), key=lambda kv: kv[1])[0]
            team = tmap.get(tid) or ""
        r = {"mlbam": mid, "name": name, "team": team, "pos": off.get("pos") or lk.get("pos"),
             "pa": int(off.get("pa") or d.get("pa") or 0),
             "sb": int(off.get("sb") or 0), "cs": int(off.get("cs") or 0),
             "gidp": int(off.get("gidp") or 0),
             "starts_on_base": int(d.get("starts_on_base") or c["starts"] or 0)}
        if r["pa"] == 0 and not d and not c["starts"]:
            continue                      # a season line with no plate appearance and no chance
        r["qualified"] = r["pa"] >= QUALIFY_MIN_PA
        for k in ("sb2", "sb3", "sbh", "cs2", "cs3", "csh", "pk1", "pk2", "pk3", "opp_sb2", "opp_sb3",
                  "opp_sbh", "x13", "x2h", "x1h", "tag3h", "tag23", "oob", "adv_err", "gdp_opp", "gidp_pbp"):
            r[k] = list(c[k]) if isinstance(c[k], list) else int(c[k])
        r["pk"] = r["pk1"] + r["pk2"] + r["pk3"]
        _row_rates(r)
        if d:
            r.update(display_parts(d))
        pb = pub.get(mid)
        if pb:
            r["bsr"] = _r1(pb.get("bsr"))
            r["wsb"] = _r1(pb.get("wsb"))
            r["bsr_rest"] = (round(pb["bsr"] - pb["wsb"], 1)
                             if pb.get("bsr") is not None and pb.get("wsb") is not None else None)
        sv = (savant.get("brv") or {}).get(mid)
        if sv:
            r["brv"] = _r1(sv.get("runner_runs_tot"))
            r["brv_xb"] = _r1(sv.get("runner_runs_XB"))
            r["brv_sb"] = _r1(sv.get("runner_runs_SBX"))
        st = (savant.get("steal") or {}).get(mid)
        if st:
            r["sav_steal_runs"] = _r1(st.get("runs_stolen_on_running_act"))
            r["lead_p"] = _r1(st.get("r_primary_lead"))
            r["lead_s"] = _r1(st.get("r_secondary_lead"))
        sp = sprint.get(mid)
        if sp and sp.get("ft_s") is not None:
            r["sprint"] = _r1(sp.get("ft_s"))
            r["sprint_pct"] = pct.get(mid)
            r["bolts"] = sp.get("bolts")
            r["hp1"] = sp.get("hp1")
            r["runs_comp"] = sp.get("runs")
        # The PROSPX chip itself comes from the links map the page already
        # loads (gradChip); the row carries only the count's input.
        r["_prospx"] = bool(lk.get("prospx"))
        dd = debuts.get(mid)
        r["recent_debut"] = bool(dd and int(dd[:4]) in (int(season), int(season) - 1))
        rows.append(r)
    return rows


def _sum(rows, key):
    return round(sum((r.get(key) or 0.0) for r in rows), 1)


def _team_block(team: str, rows: list[dict], cnt: Optional[dict] = None) -> dict:
    """One club's baserunning on one basis: sums of the season values of the
    runners it holds (roster) or the record's own per-club counts (earned)."""
    c = cnt or {}

    def tot(key):
        if cnt is not None:
            v = c.get(key)
            return v if not isinstance(v, list) else v
        if key in ("x13", "x2h", "x1h", "tag3h", "tag23"):
            return [sum(r[key][0] for r in rows), sum(r[key][1] for r in rows)]
        return sum(int(r.get(key) or 0) for r in rows)
    sb = tot("sb") if cnt is None else (c["sb2"] + c["sb3"] + c["sbh"])
    cs = tot("cs") if cnt is None else (c["cs2"] + c["cs3"] + c["csh"])
    xbt = sum(tot(k)[0] for k in ("x13", "x2h", "x1h"))
    xbt_opp = sum(tot(k)[1] for k in ("x13", "x2h", "x1h"))
    tag = sum(tot(k)[0] for k in ("tag3h", "tag23"))
    tag_opp = sum(tot(k)[1] for k in ("tag3h", "tag23"))
    att = (tot("sb2") + tot("sb3") + tot("cs2") + tot("cs3"))
    att_opp = tot("opp_sb2") + tot("opp_sb3")
    sp_w = sp_n = 0.0
    for r in rows:
        if r.get("sprint") is not None and (r.get("starts_on_base") or 0) > 0:
            sp_w += r["sprint"] * r["starts_on_base"]
            sp_n += r["starts_on_base"]
    return {"team": team, "n_runners": len(rows),
            "team_ebr": _sum(rows, "ebr"), "team_ebr_sb": _sum(rows, "ebr_sb"),
            "team_ebr_xb": _sum(rows, "ebr_xb"), "team_ebr_dp": _sum(rows, "ebr_dp"),
            "team_sb": int(sb), "team_cs": int(cs),
            "team_sb_pct": _rate(sb, sb + cs, FLOORS["sb_pct"]),
            "team_att_rate": _rate(att, att_opp, FLOORS["att_rate"]),
            "team_xbt_pct": _rate(xbt, xbt_opp, FLOORS["xbt"]),
            "team_tag_pct": _rate(tag, tag_opp, FLOORS["tag"]),
            "team_oob": int(tot("oob")),
            "team_gidp_pct": _rate(tot("gidp_pbp"), tot("gdp_opp"), FLOORS["gidp"]),
            "team_sprint": (round(sp_w / sp_n, 1) if sp_n else None),
            "team_bsr": _sum(rows, "bsr") if any(r.get("bsr") is not None for r in rows) else None,
            "team_brv": _sum(rows, "brv") if any(r.get("brv") is not None for r in rows) else None}


def build_teams(rows: list[dict], counts: dict, sub_rows: dict[int, dict], tmap: dict) -> list[dict]:
    """Both club bases (baserunning.md 2.7): `roster` sums the season values of
    the runners each club holds today; `earned` credits every event to the
    club he ran for, from the record's own batting-team field and the
    substrate's per-club stints. Earned team eBR sums to zero over the league."""
    by_roster: dict[str, list] = defaultdict(list)
    for r in rows:
        if r.get("team"):
            by_roster[r["team"]].append(r)
    # Earned: per-club eBR parts from the stints (multi-club) or the runner's
    # one club (the record's modal batting team).
    earned_parts: dict[int, dict] = defaultdict(lambda: defaultdict(float))
    earned_rows: dict[int, list] = defaultdict(list)
    by_id = {r["mlbam"]: r for r in rows}
    for mid, d in sub_rows.items():
        stints = d.get("stints")
        if stints:
            for st in stints:
                tid = st[0]
                if tid is None:
                    continue
                parts = {"sb": st[2], "pk": st[3], "xb_adv": st[4], "xb_oob": st[5], "dp": st[6]}
                dp_ = display_parts(parts)
                for k in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp"):
                    earned_parts[tid][k] += dp_[k]
                earned_rows[tid].append(mid)
        else:
            rt = counts["runner_team"].get(mid) or {}
            tid = max(rt.items(), key=lambda kv: kv[1])[0] if rt else None
            if tid is None:
                continue
            dp_ = display_parts(d)
            for k in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp"):
                earned_parts[tid][k] += dp_[k]
            earned_rows[tid].append(mid)
    teams = []
    codes = set(by_roster) | {tmap.get(t) for t in counts["teams"] if tmap.get(t)}
    for code in sorted(c for c in codes if c):
        roster = _team_block(code, by_roster.get(code, []))
        tid = next((t for t, a in tmap.items() if a == code), None)
        cnt = counts["teams"].get(tid) if tid is not None else None
        e_rows = [by_id[m] for m in earned_rows.get(tid, []) if m in by_id] if tid is not None else []
        earned = _team_block(code, e_rows, cnt or _blank_counts())
        # 3 dp on the earned parts, so the league-sum-zero identity is exact.
        for k in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp"):
            earned["team_" + k] = round(earned_parts.get(tid, {}).get(k, 0.0), 3) if tid is not None else 0.0
        earned["n_runners"] = len(earned_rows.get(tid, [])) if tid is not None else 0
        teams.append({"team": code, "roster": roster, "earned": earned,
                      # The flat keys are the roster basis, the one the Team
                      # sub-tab shows (bullpen_export.TEAM_BASIS, every team tab).
                      **{k: v for k, v in roster.items() if k != "team"}})
    teams.sort(key=lambda t: (t.get("team_ebr") if t.get("team_ebr") is not None else -999), reverse=True)
    return teams


# --------------------------------------------------------------------------- #
# league and values (the gate's own tables, read; arithmetic on them only)
# --------------------------------------------------------------------------- #
def _breakeven(re_cells: dict, from_bits: tuple, target: int) -> Optional[float]:
    """The RE24 break-even success rate for a steal of `target` from the states
    in `from_bits`, weighted by the fit-set plays in each from-state. Pure
    arithmetic on the league table: p* = (RE(before) - RE(after CS)) /
    (RE(after SB) - RE(after CS))."""
    num_ = den = 0.0
    for b in from_bits:
        for o in (0, 1, 2):
            cell = re_cells.get(f"{b}|{o}")
            if not cell:
                continue
            re0, n = cell[0], cell[1]
            origin = target - 1
            b1 = (b & ~(1 << (origin - 1))) | (1 << (target - 1)) if target < 4 else (b & ~(1 << (origin - 1)))
            runs = 1.0 if target == 4 else 0.0
            after_sb = runs + re_cells[f"{b1}|{o}"][0]
            b_cs = b & ~(1 << (origin - 1))
            after_cs = re_cells[f"{b_cs}|{o + 1}"][0] if o + 1 < 3 else 0.0
            if after_sb - after_cs <= 0:
                continue
            p = (re0 - after_cs) / (after_sb - after_cs)
            num_ += p * n
            den += n
    return round(num_ / den, 4) if den else None


def build_values(season: int, sub: dict) -> dict:
    s = str(int(season))
    re_cells = ((sub.get("re24") or {}).get(s) or {}).get("cells") or {}
    lg = (sub.get("league") or {}).get(s) or {}
    steal = lg.get("steal") or {}
    xb = lg.get("xb") or {}
    dp = lg.get("dp") or {}
    n_dp = sum(v.get("opportunities", 0) for v in (dp.get("table") or {}).values())
    g_dp = sum(v.get("gidp", 0) for v in (dp.get("table") or {}).values())
    return {"re24": {c: {"re": v[0], "n": v[1]} for c, v in re_cells.items()},
            "re24_sha256": ((sub.get("re24") or {}).get(s) or {}).get("sha256"),
            "steal": {"per_opportunity": {"1B": (steal.get("m_sb") or {}).get("1"),
                                          "2B": (steal.get("m_sb") or {}).get("2"),
                                          "3B": (steal.get("m_sb") or {}).get("3")},
                      "pickoff_per_start": {"1B": (steal.get("m_pk") or {}).get("1"),
                                            "2B": (steal.get("m_pk") or {}).get("2"),
                                            "3B": (steal.get("m_pk") or {}).get("3")},
                      "attempts": steal.get("attempts"), "pickoffs": steal.get("pickoffs")},
            "breakeven_sb2": _breakeven(re_cells, (1, 5), 2) if re_cells else None,
            "breakeven_sb3": _breakeven(re_cells, (2, 3), 3) if re_cells else None,
            "advance": {"class_mean_before_centring": xb.get("class_mean_before_centring"),
                        "opportunities": xb.get("opportunities")},
            "gidp": {"rate": (round(g_dp / n_dp, 4) if n_dp else None), "table": dp.get("table")}}


def build_league(season: int, rows: list[dict], counts: dict, sprint: dict[int, dict]) -> dict:
    tot = _blank_counts()
    for c in counts["teams"].values():
        for k, v in c.items():
            if isinstance(v, list):
                tot[k][0] += v[0]
                tot[k][1] += v[1]
            else:
                tot[k] += v
    sb = sum(r["sb"] for r in rows)
    cs = sum(r["cs"] for r in rows)
    starts = tot["starts"] or 0
    sp = sorted(float(v["ft_s"]) for v in sprint.values()
                if v.get("ft_s") is not None and (v.get("runs") or 0) >= SPRINT_MIN_RUNS)
    n = len(sp)
    mean = (sum(sp) / n) if n else None
    sd = (math.sqrt(sum((x - mean) ** 2 for x in sp) / (n - 1)) if n > 1 else None)
    med = (sp[n // 2] if n % 2 else (sp[n // 2 - 1] + sp[n // 2]) / 2) if n else None
    xbt = sum(tot[k][0] for k in ("x13", "x2h", "x1h"))
    xbt_opp = sum(tot[k][1] for k in ("x13", "x2h", "x1h"))
    return {"season": int(season), "sb": int(sb), "cs": int(cs),
            "sb_pct": _rate(sb, sb + cs, 1),
            "att_rate": {"2B": _rate(tot["sb2"] + tot["cs2"], tot["opp_sb2"], 1),
                         "3B": _rate(tot["sb3"] + tot["cs3"], tot["opp_sb3"], 1)},
            "xbt_pct": _rate(xbt, xbt_opp, 1),
            "cls": {"s1_3": tot["x13"], "s2_h": tot["x2h"], "d1_h": tot["x1h"]},
            "tag": {"f3_H": tot["tag3h"], "f2_3": tot["tag23"]},
            "oob_per_100_starts": (round(100.0 * tot["oob"] / starts, 3) if starts else None),
            "pk_per_100_starts": (round(100.0 * (tot["pk1"] + tot["pk2"] + tot["pk3"]) / starts, 3) if starts else None),
            "gidp_pct": _rate(tot["gidp_pbp"], tot["gdp_opp"], 1),
            "starts_on_base": int(starts),
            "sprint": {"mean": (round(mean, 2) if mean is not None else None),
                       "median": (round(med, 2) if med is not None else None),
                       "sd": (round(sd, 3) if sd is not None else None), "n": n},
            # Published as the check (each part sums to zero over every runner).
            "ebr_sum": {k: round(sum((r.get(k) or 0.0) for r in rows), 3)
                        for k in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp")}}


# --------------------------------------------------------------------------- #
# one season, end to end
# --------------------------------------------------------------------------- #
def _tmap() -> dict:
    try:
        from bullpen_export import _team_abbrev_map
        return _team_abbrev_map() or {}
    except Exception as e:  # noqa: BLE001
        _log.warning("team abbreviation map unavailable (%s)", e)
        return {}


def _identity_check(season: int, blk: dict, rows: list[dict]) -> None:
    """A completed season serves only when the record reproduces the official
    counts (EBR_GATE.md part 3: I1, I2, I3) and the parts sum to zero."""
    rec = (blk or {}).get("receipts") or {}
    if bool((blk or {}).get("complete")):
        for key in ("I1", "I2", "I3"):
            if (rec.get(key) or {}).get("pass") is not True:
                raise BaserunningRefusal(f"season {season}: identity gate {key} did not pass in the runner record")
        gidp = ((rec.get("I2") or {}).get("gidp") or {}).get("exact_share")
        if gidp is not None and gidp < I2_GIDP_MIN_SHARE:
            raise BaserunningRefusal(f"season {season}: GIDP exact on {gidp:.4f} of players, under {I2_GIDP_MIN_SHARE}")
    for k in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp"):
        s = sum((r.get(k) or 0.0) for r in rows)
        if abs(s) > LEAGUE_SUM_TOL:
            raise BaserunningRefusal(f"season {season}: {k} sums to {s:.3f} over the league, not zero")


def build_season(season: int, *, sub: Optional[dict] = None, sub_by: Optional[dict] = None,
                 savant_offline: bool = True, log=print, stamp_war: bool = True) -> Optional[dict]:
    """The board block for one season: rows, teams, league, values, sources.
    None when the season has no runner record."""
    season = int(season)
    sub = sub or load_substrate()
    sub_by = sub_by if sub_by is not None else substrate_by_season(sub)
    sub_rows = sub_by.get(season) or {}
    pa, rn, blk = load_record_season(season)
    if pa is None:
        log(f"  baserunning: no runner record for {season}; skipping")
        return None
    counts = record_counts(pa, rn)
    official, off_meta = load_official(season)
    published = load_published(season)
    savant = load_savant(season, offline=savant_offline)
    sprint, sprint_meta = load_sprint(season)
    tmap = _tmap()
    links = load_links()
    debuts, debuts_gen = load_debuts()
    rows = build_rows(season, official=official, counts=counts, sub_rows=sub_rows, published=published,
                      savant=savant, sprint=sprint, tmap=tmap, links=links, debuts=debuts)
    _identity_check(season, blk, rows)
    teams = build_teams(rows, counts, sub_rows, tmap)
    league = build_league(season, rows, counts, sprint)
    values = build_values(season, sub)
    war_meta = _stamp_war(rows, season) if stamp_war else {"available": False, "n_stamped": 0}
    n_elig = sum(1 for r in rows if r["pa"] >= 100)
    n_pub = sum(1 for r in rows if r.get("bsr") is not None and r["pa"] >= 100)
    pub_meta = {k: v for k, v in published.items() if k != "values"}
    pub_meta.update({"n_joined": sum(1 for r in rows if r.get("bsr") is not None),
                     "n_eligible": n_elig, "hit_rate_eligible": (round(n_pub / n_elig, 4) if n_elig else None)})
    n_sprint = sum(1 for r in rows if r.get("sprint") is not None)
    sp_vals = [float(v["ft_s"]) for v in sprint.values()
               if v.get("ft_s") is not None and (v.get("runs") or 0) >= SPRINT_MIN_RUNS]
    sprint_meta.update({"pool_n": len(sp_vals),
                        "pool_mean": (round(sum(sp_vals) / len(sp_vals), 2) if sp_vals else None),
                        "pool_sd": league["sprint"]["sd"], "n_joined": n_sprint})
    rows.sort(key=lambda r: (r.get("ebr") if r.get("ebr") is not None else -999), reverse=True)
    stamps = sub.get("stamps") or {}
    return {
        "season": season, "complete": bool((blk or {}).get("complete")),
        "rows": rows, "teams": teams, "league": league, "values": values,
        # The record's counts, kept for the caller (never serialized).
        "_counts": counts, "_tmap": tmap,
        "sources": {
            "official": off_meta,
            "published": pub_meta,
            "savant_brv": {"source_url": savant["urls"].get("brv"), "season": season,
                           "fetched_at": (savant.get("fetched_at") or {}).get("brv"),
                           "n_source_rows": len(savant.get("brv") or {}),
                           "n_joined": sum(1 for r in rows if r.get("brv") is not None)},
            "savant_steal": {"source_url": savant["urls"].get("steal"), "season": season,
                             "fetched_at": (savant.get("fetched_at") or {}).get("steal"),
                             "n_source_rows": len(savant.get("steal") or {}),
                             "n_joined": sum(1 for r in rows if r.get("sav_steal_runs") is not None)},
            "sprint": sprint_meta,
            "runner_moves": {"built_at": (blk or {}).get("built_at"), "games": (blk or {}).get("games_present"),
                             "games_scheduled": (blk or {}).get("games_scheduled"),
                             "frozen": (blk or {}).get("frozen"),
                             "collisions": ((blk or {}).get("counters") or {}).get("group_collisions"),
                             "receipts": {k: ((blk or {}).get("receipts") or {}).get(k) for k in ("I1", "I2", "I3")}},
            "ebr": {"ebr_version": sub.get("ebr_version"), "generated_at": sub.get("generated_at"),
                    "live_built_at": sub.get("live_built_at"), "gate": sub.get("gate"),
                    "re24_sha256": values.get("re24_sha256"), "K": stamps.get("K"), "kappa": stamps.get("kappa"),
                    "pool_seasons": stamps.get("pool_seasons"), "pool_sha256": stamps.get("pool_sha256"),
                    "n_rows": len(sub_rows)},
            "prospx": {"n_card": sum(1 for r in rows if r.pop("_prospx", False)),
                       "n_recent_debut": sum(1 for r in rows if r.get("recent_debut")),
                       "debuts_generated_at": debuts_gen},
            "ewar_join": war_meta,
        },
    }


#: The history file's row fields, POSITIONAL (the war_seasons.json design: a
#: keyed row per runner-season put the file at 3.4 MB against its 1.3 MB /
#: 180 KB budget). Qualified runners only, the named views' columns (the
#: per-class taken/chances cells and the by-base splits stay on the live
#: board), eBR parts at 2 dp with eBR their exact rounded sum.
HISTORY_FIELDS = ("mlbam", "name", "team", "pos", "pa", "qualified", "sb", "cs", "sb_pct", "gidp", "pk",
                  "att_rate", "xbt", "xbt_opp", "xbt_pct", "tag_pct", "oob", "gidp_pct", "starts_on_base",
                  "ebr", "ebr_sb", "ebr_xb", "ebr_dp", "bsr", "wsb", "bsr_rest", "brv", "brv_xb", "brv_sb",
                  "sprint", "sprint_pct", "war")
_HISTORY_PARTS = ("ebr_sb", "ebr_xb", "ebr_dp")


def _slim_row(r: dict, keys=None) -> dict:
    """A row without its absent values: null, False and an empty [taken, chances]
    pair are dropped (the page prints the null marker for a missing key); a
    zero COUNT and a zero run value stay, because 0 is a number here."""
    out = {}
    for k in (keys or r.keys()):
        v = r.get(k)
        if v is None or (isinstance(v, list) and v == [0, 0]) or (v is False and k == "recent_debut"):
            continue
        out[k] = v
    return out


def _history_row(r: dict) -> list:
    o = dict(r)
    if all(o.get(k) is not None for k in _HISTORY_PARTS):
        for k in _HISTORY_PARTS:
            o[k] = round(o[k], 2)
        o["ebr"] = round(sum(o[k] for k in _HISTORY_PARTS), 2)
    return [o.get(k) for k in HISTORY_FIELDS]


# --------------------------------------------------------------------------- #
# the payloads
# --------------------------------------------------------------------------- #
def _team_basis_meta(rows, scope):
    try:
        from bullpen_export import team_basis_meta
        return team_basis_meta(rows, label="baserunning", scope=scope)
    except Exception:  # noqa: BLE001
        return {"basis": "current_roster", "scope": scope, "n_rows": len(rows)}


def _apply_current_team(rows, label):
    try:
        from bullpen_export import apply_current_team
        return apply_current_team(rows, label=label)
    except Exception:  # noqa: BLE001
        return 0


def build_payload(season: Optional[int] = None, *, log=print, savant_offline: bool = True,
                  today: Optional[str] = None) -> dict:
    season = int(season or _dt.date.today().year)
    today = today or _dt.date.today().isoformat()
    sub = load_substrate()
    sub_by = substrate_by_season(sub)
    if season not in sub_by:
        raise BaserunningRefusal(f"season {season} is not in the eBR substrate ({sorted(sub_by)})")
    blk = build_season(season, sub=sub, sub_by=sub_by, savant_offline=savant_offline, log=log)
    if blk is None:
        raise BaserunningRefusal(f"season {season}: no runner record")
    rows = blk["rows"]
    moved = _apply_current_team(rows, "baserunning")
    # The club rollup follows the roster basis after the remap, like every
    # other team tab; the earned basis inside each club block does not move.
    teams = build_teams(rows, blk.pop("_counts"), sub_by[season], blk.pop("_tmap"))
    has_war = any("war" in r for r in rows)
    ewar_stamp = {}
    if has_war:
        try:
            from war_source import safe_ewar_vintage
            ewar_stamp = {"ewar_vintage": safe_ewar_vintage(as_of=today)}
        except Exception:  # noqa: BLE001
            ewar_stamp = {}
    bem = bem_plus_status()
    payload = {
        "schema": 1, "generated_at": today, "season": season, "as_of": today,
        "verdict": "descriptive",
        "frame": {"ewar_note": _ewar_baserunning_note(), "war_provider": _war_provider()},
        "flag": {"MLBSTATS_BASERUNNING_LIVE": MLBSTATS_BASERUNNING_LIVE},
        "bem_plus": bem,
        "sources": blk["sources"],
        "values": blk["values"],
        "qualify": {"min_pa": QUALIFY_MIN_PA, "floors": dict(FLOORS), "sprint_min_runs": SPRINT_MIN_RUNS},
        "league": blk["league"],
        "team_basis": _team_basis_meta(rows, "current"),
        "n_moved_to_current_club": moved,
        "fields_note": "rows are keyed; the history file's rows are positional by its `fields`",
        "runners": [_slim_row(r) for r in rows],
        "teams": teams,
        "n_qualified": sum(1 for r in rows if r.get("qualified")),
        **ewar_stamp,
        "note": ("eBR is computed from MLB's play-by-play (tools/build_ebr.py); every count is official "
                 "or from the runner record; BsR and wSB are FanGraphs' published values from MLB's "
                 "feed; BRV, sprint speed and leads are Baseball Savant's. Descriptive: what happened "
                 "this season, not a forecast."),
    }
    return payload


def build_history(seasons=None, *, log=print, savant_offline: bool = True, today: Optional[str] = None) -> dict:
    seasons = list(seasons or HISTORY_SEASONS)
    today = today or _dt.date.today().isoformat()
    sub = load_substrate()
    sub_by = substrate_by_season(sub)
    hist, ewar_join, basis_rows = {}, {}, []
    for y in seasons:
        if int(y) not in sub_by:
            log(f"  baserunning-history: {y} not in the eBR substrate; skipping")
            continue
        blk = build_season(int(y), sub=sub, sub_by=sub_by, savant_offline=savant_offline, log=log)
        if blk is None:
            continue
        rows = blk["rows"]
        _apply_current_team(rows, f"baserunning history {y}")
        basis_rows.extend(rows)
        raw = blk["sources"]["ewar_join"]
        ewar_join[str(y)] = {"season": int(y), "side": "bat + pit", "n_rows": raw.get("n_rows"),
                             "n_with_id": raw.get("n_with_id"), "n_covered": raw.get("n_covered"),
                             "n_stamped": raw.get("n_stamped"), "available": raw.get("available", False),
                             "n_two_sided": raw.get("n_two_sided"), "basis": raw.get("basis"),
                             **({"refused": raw["refused"]} if raw.get("refused") else {})}
        kept = [_history_row(r) for r in rows if r.get("qualified")]
        teams = [{"team": t["team"], **{k: v for k, v in t.items() if k.startswith("team_")}}
                 for t in blk["teams"]]
        hist[str(y)] = {"season": int(y), "n_qualified": sum(1 for r in rows if r.get("qualified")),
                        "runners": kept, "teams": teams, "league": blk["league"],
                        "values": {k: blk["values"][k] for k in ("breakeven_sb2", "breakeven_sb3", "re24_sha256")},
                        "sources": {k: blk["sources"][k] for k in ("official", "runner_moves", "ebr")}}
        log(f"  baserunning-history: {y} -> {len(kept)} runners, {hist[str(y)]['n_qualified']} qualified")
    payload = {
        "schema": 1, "generated_at": today, "seasons": [int(y) for y in hist],
        "note": ("Qualified runners by season from the eBR substrate and the runner record, rows "
                 "positional by `fields`. eBR is runs above average on that season's run expectancy "
                 "(parts at 2 dp, eBR their sum); BsR and wSB are FanGraphs' published values as "
                 "fetched; BRV and sprint speed are Baseball Savant's. Team rows are the roster "
                 "basis. Descriptive."),
        "fields": list(HISTORY_FIELDS),
        "ebr_version": sub.get("ebr_version"),
        "frozen_digests": (sub.get("cadence") or {}).get("frozen_digests"),
        "team_basis": _team_basis_meta(basis_rows, "history"),
        "ewar_join": ewar_join,
        "frame": {"ewar_note": _ewar_baserunning_note()},
        **({"ewar_vintage": _safe_vintage(today)}
           if any(r[HISTORY_FIELDS.index("war")] is not None
                  for y in hist.values() for r in y["runners"]) else {}),
        "history": hist,
    }
    return payload


def _safe_vintage(today):
    try:
        from war_source import safe_ewar_vintage
        return safe_ewar_vintage(as_of=today)
    except Exception:  # noqa: BLE001
        return None


def build_eval(payload: dict, history: Optional[dict] = None) -> dict:
    """The served eval of the `ebr` and `team_ebr` rows: the builder's own
    descriptive eval (identity receipts, league sums, coverage, agreement,
    ewar_link; a look block it carries rides along verbatim) plus this board's
    join and reproduction receipts. Never a year-to-year number."""
    ev = without_backfill(_read_json(EVAL_PREVIEW)) or {}
    if not ev:
        raise BaserunningRefusal(f"the eBR eval is absent at {EVAL_PREVIEW}; run tools/build_ebr.py first")
    for s, cov in (ev.get("coverage") or {}).items():
        if cov.get("pass") is False:
            raise BaserunningRefusal(f"season {s}: eBR covers {cov.get('share')} of the feed's hitting rows "
                                     f"with a nonzero baseRunning, under 0.99")
    board = {}
    blocks = {str(payload["season"]): payload}
    for s, h in ((history or {}).get("history") or {}).items():
        blocks[s] = h
    for s, blk in sorted(blocks.items()):
        src = blk.get("sources") or {}
        rows = blk.get("runners") or []
        board[s] = {"n_rows": len(rows), "n_qualified": blk.get("n_qualified"),
                    "published_hit_rate_eligible": (src.get("published") or {}).get("hit_rate_eligible"),
                    "published_n_ambiguous": (src.get("published") or {}).get("n_ambiguous"),
                    "savant_brv_joined": (src.get("savant_brv") or {}).get("n_joined"),
                    "sprint_joined": (src.get("sprint") or {}).get("n_joined"),
                    "ewar_stamped": (src.get("ewar_join") or {}).get("n_stamped"),
                    "reproduction": (src.get("runner_moves") or {}).get("receipts"),
                    "ebr_sum": (blk.get("league") or {}).get("ebr_sum")}
    out = dict(ev)
    if "look" in out:
        sl = _served_look(out["look"])
        if sl is None:
            out.pop("look")
        else:
            out["look"] = sl
    out["baserunning_board"] = {"note": "Join rates and official-count reproduction per season on the "
                                        "Baserunning section's payloads; descriptive.",
                                "flag": {"MLBSTATS_BASERUNNING_LIVE": MLBSTATS_BASERUNNING_LIVE},
                                "by_season": board}
    return out


#: The comparative sentence the gate document's part 6.3 licenses, by the Leg E
#: and E-DP dispositions. UNDECIDED carries none. A twin that is not
#: RESOLVED_LOSS makes the look VOID (part 6.5): no sentence.
_REPEAT_VERB = {"SHIP": "repeats more from one season to the next than",
                "RULED OUT": "repeats about as much from one season to the next as",
                "RESOLVED_LOSS": "repeats less from one season to the next than"}


def _served_look(look: Optional[dict]) -> Optional[dict]:
    """The look block as served: dispositions, guard pass flags, floors, NOISE
    flags and the identity receipts, and nothing else (plan Part 8 8.A). No
    year-to-year difference, correlation or rho is carried; those stay in the
    gate document's part 12.1 and .cache/ebr/preview/."""
    if not isinstance(look, dict) or not isinstance(look.get("result"), dict):
        return None
    r = look["result"]

    def disp(k):
        return (r.get(k) or {}).get("disposition")

    def floors(k):
        f = (r.get(k) or {}).get("floors") or {}
        return {x: f.get(x) for x in ("half_width", "ship_needs_d_above", "resolved_loss_needs_d_below",
                                      "ruled_out_reachable")}

    bem = r.get("bem_plus") or {}
    return {
        "status": look.get("status"), "commit": look.get("commit"),
        "waived_early_read": look.get("waived_early_read"),
        "finished_at": look.get("finished_at"),
        "dispositions": {k: disp(k) for k in ("leg_e", "leg_e_twin", "e_dp", "e_dp_twin")},
        "floors": {k: floors(k) for k in ("leg_e", "leg_e_twin", "e_dp", "e_dp_twin")},
        "guards": {"twin_guard_pass": (r.get("leg_t") or {}).get("leg_t_pass"),
                   "double_play_guard_pass": (r.get("leg_t") or {}).get("dp2_pass"),
                   "dp_plumbing_floor_pass": (r.get("dp1") or {}).get("pass"),
                   "dp_plumbing_floor_permuted_clears": (r.get("dp1_permuted") or {}).get("floor_clear")},
        "noise_flags": dict((r.get("reliability") or {}).get("noise") or {}),
        "bem_plus": {"pass": bem.get("pass"), "clauses": dict(bem.get("clauses") or {})},
        "identity_receipts": dict(look.get("stamps") or {}),
    }


def repeat_copy(served_look: Optional[dict]) -> dict:
    """The one comparative sentence per leg, derived from the served look's
    dispositions (EBR_GATE.md 6.3); an empty string when none is licensed."""
    out = {"eBR": "", "DP": ""}
    d = (served_look or {}).get("dispositions") or {}
    for key, leg, twin, other in (("eBR", "leg_e", "leg_e_twin", "FanGraphs' BsR"),
                                  ("DP", "e_dp", "e_dp_twin", "Baseball-Reference's double-play runs")):
        verb = _REPEAT_VERB.get(d.get(leg))
        if verb and d.get(twin) == "RESOLVED_LOSS":
            out[key] = f"{verb} {other} on the same runners"
    return out


def _guard_teams(fresh, out_path, log):
    try:
        from bullpen_export import guard_nonempty_block
        return guard_nonempty_block(fresh, out_path, key="teams", source="baserunning_export",
                                    label="baserunning", log=log)
    except Exception:  # noqa: BLE001
        return fresh, {"key": "teams", "n": len(fresh), "stale": False}


def export(season: Optional[int] = None, *, out: Optional[Path] = None, write: bool = True,
           log=print, savant_offline: bool = True, with_history: bool = False,
           today: Optional[str] = None) -> int:
    """Build the live board (and, with_history, the history file), the substrate
    copy and the eval, into out_dir() (the preview while dark). Returns the
    runner count. Refuses rather than publishing on an identity miss, a league
    sum off zero, an empty club block or a payload over its budget."""
    d = Path(out) if out else out_dir()
    payload = build_payload(season, log=log, savant_offline=savant_offline, today=today)
    teams, meta = _guard_teams(payload["teams"], d / OUT_NAME, log)
    payload["teams"] = teams
    payload["team_rollup"] = meta
    raw, gz = _sizes(payload, indent=None)
    if raw > BUDGET_LIVE[0] or gz > BUDGET_LIVE[1]:
        raise BaserunningRefusal(f"live payload {raw} B raw / {gz} B gzip is over its budget {BUDGET_LIVE}")
    history = build_history(log=log, savant_offline=savant_offline, today=today) if with_history else None
    if history is not None:
        hraw, hgz = _sizes(history, indent=None)
        if hraw > BUDGET_HISTORY[0] or hgz > BUDGET_HISTORY[1]:
            raise BaserunningRefusal(f"history payload {hraw} B raw / {hgz} B gzip is over its budget {BUDGET_HISTORY}")
    ev = build_eval(payload, history)
    payload["repeat_copy"] = repeat_copy(ev.get("look"))
    if write:
        n = _write_json(d / OUT_NAME, payload, indent=None)
        log(f"  baserunning: wrote {d / OUT_NAME} ({n} B raw, {gz} B gzip, {len(payload['runners'])} runners)")
        if history is not None:
            n = _write_json(d / HISTORY_NAME, history, indent=None)
            log(f"  baserunning: wrote {d / HISTORY_NAME} ({n} B raw, {hgz} B gzip, {len(history['history'])} seasons)")
        sub = load_substrate()
        _write_json(d / SUBSTRATE_NAME, sub, indent=None)
        _write_json(d / EVAL_NAME, ev)
        log(f"  baserunning: wrote {d / SUBSTRATE_NAME} and {d / EVAL_NAME}")
    return len(payload["runners"])


def export_history(seasons=None, *, out: Optional[Path] = None, write: bool = True, log=print,
                   savant_offline: bool = True, today: Optional[str] = None) -> dict:
    d = Path(out) if out else out_dir()
    history = build_history(seasons, log=log, savant_offline=savant_offline, today=today)
    hraw, hgz = _sizes(history, indent=None)
    if hraw > BUDGET_HISTORY[0] or hgz > BUDGET_HISTORY[1]:
        raise BaserunningRefusal(f"history payload {hraw} B raw / {hgz} B gzip is over its budget {BUDGET_HISTORY}")
    if write and history["history"]:
        n = _write_json(d / HISTORY_NAME, history, indent=None)
        log(f"  baserunning-history: wrote {d / HISTORY_NAME} ({n} B raw, {hgz} B gzip)")
    return history


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "history":
        export_history()
        return 0
    season = int(argv[0]) if argv else None
    export(season, with_history=("--with-history" in argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
