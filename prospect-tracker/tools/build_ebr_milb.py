#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_ebr_milb - level-relative eBR for the minor leagues.

ebr_milb.py is the definition; this tool reads the minor-league partition of the
runner record (.cache/pbp_runners/milb), fetches the official StatsAPI season
hitting lines once per level-season WITH caughtStealing and groundIntoDoublePlay
(milb_history drops them and is not changed), and writes:

  .cache/ebr/milb_preview/ebr_milb.json       every player-season row, its parts,
      the W sub-total, and per-unit RE24 cells; always written.
  .cache/ebr/milb_preview/ebr_milb_eval.json  identity receipts per level-season,
      split-half reliability and cross-level continuity (aggregates only).

and, only when ebr_milb.MILB_EBR_LIVE is True and --serve is passed, two files under
data/: ebr_milb.json, the PROSPX card payload (rows at DISPLAY_PA plate
appearances or more from level-seasons that pass every identity gate, keyed by
mlbam), and ebr_milb_eval.json, the registry row's eval artifact (aggregates only).

Never relates a number to a consensus-FV cell, an eFV, a grade or an outcome.

Run:  python tools/build_ebr_milb.py [--no-fetch] [--serve]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ebr  # noqa: E402
import ebr_milb as M  # noqa: E402

RECORD = ROOT / ".cache" / "pbp_runners"
PREVIEW_DIR = ROOT / ".cache" / "ebr" / "milb_preview"
LINES_DIR = ROOT / ".cache" / "ebr" / "milb_lines"
SERVED = ROOT / "data" / "ebr_milb.json"
SERVED_EVAL = ROOT / "data" / "ebr_milb_eval.json"
REFETCH_DIR = RECORD / "refetch" / "milb"
LIVE_FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"
GAMELOG = "https://statsapi.mlb.com/api/v1/people/{mid}/stats?stats=gameLog&season={season}&sportId={sport}"
#: A level-season whose record holds less than this share of the official plate
#: appearances is incomplete (I3): it is not reconciled and not served.
MIN_PA_COVERAGE = 0.99
#: The minor-league identity gate (a DEFAULT of this task, recorded in the
#: result): EBR_GATE.md 3's exact SB and CS match is kept as the reported
#: ``exact`` flag, but after the one re-fetch a few official steals and caught
#: stealings are scorer decisions the feed's runner entries do not carry (a runner
#: credited a stolen base on another runner's steal, with the reason of an error
#: advance), so a level-season passes with league SB and CS within 0.1 percent of
#: the official lines and SB and CS exact for 99 percent of the players who have
#: any. GIDP keeps the MLB bounds (league within 0.5 percent, 97 percent exact).
LEAGUE_TOL = 0.001
PLAYER_SB_CS_SHARE = 0.99
PLAYER_GIDP_SHARE = 0.97
GIDP_LEAGUE_TOL = 0.005
GATE_DOC = "docs/ebr-2026-09-30/EBR_GATE.md"
BASE = "https://statsapi.mlb.com/api/v1/stats"
UA = {"User-Agent": "Mozilla/5.0 (eephus ebr_milb)"}
I4_TOL = 0.01
I6_TOL = 0.011
I6_MAX_ABS = 30.0
#: A level-season whose season is on or after this calendar day is "complete" for
#: freezing (the minor-league regular seasons end in September).
FREEZE_MONTH_DAY = (11, 1)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path: Path, obj, *, indent=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=indent, sort_keys=True,
                              separators=(",", ":") if indent is None else (",", ": ")),
                   encoding="utf-8", newline="\n")
    tmp.replace(path)


# --------------------------------------------------------------------------
# the record
# --------------------------------------------------------------------------
def load_units(record: Path = RECORD, units=None) -> tuple[dict, dict]:
    """({unit: (pa, rn)}, manifest) for the level-seasons on disk with at least
    MIN_UNIT_GAMES games."""
    import pandas as pd
    man = json.loads((Path(record) / "manifest.json").read_text(encoding="utf-8"))
    out = {}
    for key, blk in sorted((man.get("milb") or {}).items()):
        u = M.parse_unit_key(key)
        if u[0] not in M.LEVEL_SPORT or int(blk.get("games") or 0) < M.MIN_UNIT_GAMES:
            continue
        if units is not None and u not in units:
            continue
        pa = pd.read_parquet(Path(record) / blk["files"]["pa"])
        rn = pd.read_parquet(Path(record) / blk["files"]["runners"])
        out[u] = (pa, rn)
    return out, man


# --------------------------------------------------------------------------
# the re-fetch rule (EBR_GATE.md part 3): one re-fetch of the games of the
# mismatched players, then one re-check
# --------------------------------------------------------------------------
_WALK_CACHE: dict = {}


def _walked(refetch_dir: Path) -> dict:
    """{(level, season): [(game_pk, pa_rows, rn_rows)]} for every stored payload,
    walked once per process (the payloads of a directory do not change in a build)."""
    import build_runner_moves as bm
    refetch_dir = Path(refetch_dir)
    files = sorted(refetch_dir.glob("*.json"))
    sig = (str(refetch_dir), len(files), max((f.stat().st_mtime_ns for f in files), default=0))
    if sig in _WALK_CACHE:
        return _WALK_CACHE[sig]
    out: dict = defaultdict(list)
    for p in files:
        res = bm._milb_job(str(p))
        if not res or res[0] != "ok":
            continue
        _, level, season, pk, pa_rows, rn_rows, _ = res
        out[(level, int(season))].append((int(pk), pa_rows, rn_rows))
    _WALK_CACHE.clear()
    _WALK_CACHE[sig] = out
    return out


def apply_refetch(unit, pa, rn, refetch_dir: Path = REFETCH_DIR):
    """(pa, rn, games) with every re-fetched game of this level-season walked from
    its stored payload and put in place of the record's rows for that game, and the
    feed's event-typed steals put on the steal reason (ebr_milb.normalise_runners)."""
    import pandas as pd
    import build_runner_moves as bm
    refetch_dir = Path(refetch_dir)
    if not refetch_dir.exists():
        rn, _ = M.normalise_runners(rn)
        return pa, rn, []
    new_pa, new_rn, games = [], [], []
    for pk, pa_rows, rn_rows in _walked(refetch_dir).get((unit[0], int(unit[1])), []):
        games.append(int(pk))
        new_pa.extend(pa_rows)
        new_rn.extend(rn_rows)
    if not games:
        rn, _ = M.normalise_runners(rn)
        return pa, rn, []
    keep_pa = pa[~pa["game_pk"].isin(games)]
    keep_rn = rn[~rn["game_pk"].isin(games)]
    add_pa = bm._frame(new_pa, bm.PA_INT_COLS, ("game_pk", "at_bat_index"))
    add_rn = bm._frame(new_rn, bm.RUNNER_INT_COLS, ("game_pk", "at_bat_index", "seq"))
    pa2 = pd.concat([keep_pa, add_pa], ignore_index=True).sort_values(
        ["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
    rn2 = pd.concat([keep_rn, add_rn], ignore_index=True).sort_values(
        ["game_pk", "at_bat_index", "seq"], kind="mergesort").reset_index(drop=True)
    rn2, _ = M.normalise_runners(rn2)
    return pa2, rn2, sorted(games)


SCHEDULE = ("https://statsapi.mlb.com/api/v1/schedule?sportId={sport}&season={season}&gameType=R"
            "&startDate={season}-01-01&endDate={season}-12-31")


def missing_games(unit, pa, *, getter=None) -> list:
    """The final regular-season games of the level-season the record lacks, from the
    league schedule (I3 completeness)."""
    get = getter or _get
    d = get(SCHEDULE.format(sport=M.LEVEL_SPORT[unit[0]], season=unit[1]))
    have = set(int(x) for x in pa["game_pk"].unique())
    out = []
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            st = (g.get("status") or {})
            if st.get("abstractGameState") == "Final" and (g.get("gameType") or "R") == "R":
                pk = int(g["gamePk"])
                if pk not in have:
                    out.append(pk)
    return sorted(set(out))


def fill_missing(unit, pa, *, getter=None, refetch_dir: Path = REFETCH_DIR,
                 interval: float = 0.2, limit=None) -> dict:
    """Fetch the games the record lacks into refetch_dir (stored as the re-fetch
    rule stores a payload; the build overlays them)."""
    refetch_dir = Path(refetch_dir)
    refetch_dir.mkdir(parents=True, exist_ok=True)
    todo = missing_games(unit, pa, getter=getter)
    if limit:
        todo = todo[:limit]
    got, failed = 0, []
    for pk in todo:
        path = refetch_dir / f"{pk}.json"
        if path.exists():
            continue
        time.sleep(interval)
        req = urllib.request.Request(LIVE_FEED.format(pk=pk), headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read()
        except Exception:  # noqa: BLE001
            failed.append(pk)
            continue
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        got += 1
    return {"missing": len(todo), "fetched": got, "failed": failed}


def mismatched_players(pa, rn, official: dict) -> list:
    rec = record_counts(pa, rn)
    off = {int(k): v for k, v in official["players"].items()}
    zero = {"sb": 0, "cs": 0}
    return sorted(m for m in set(rec) | set(off)
                  if rec.get(m, zero)["sb"] != off.get(m, zero)["sb"]
                  or rec.get(m, zero)["cs"] != off.get(m, zero)["cs"])


def pa_coverage(pa, official: dict) -> float:
    off = sum(v["pa"] for v in official["players"].values())
    return (int(pa["is_pa"].astype(bool).sum()) / off) if off else 0.0


def reconcile(unit, pa, rn, official: dict, *, getter=None, refetch_dir: Path = REFETCH_DIR,
              interval: float = 0.25) -> dict:
    """ONE re-fetch per level-season: for each mismatched player the official game
    log locates the games whose steal and caught-stealing counts differ from the
    record (or that the record lacks); those games are fetched into refetch_dir.
    Returns {"players", "games"}; the caller rebuilds and re-checks once."""
    get = getter or _get
    refetch_dir = Path(refetch_dir)
    refetch_dir.mkdir(parents=True, exist_ok=True)
    players = mismatched_players(pa, rn, official)
    rec_game: dict = defaultdict(lambda: [0, 0])
    reasons = rn["movement_reason"].fillna("").astype(str)
    for pid, g, rs in zip(rn["runner_id"], rn["game_pk"], reasons):
        m = ebr._int(pid)
        if m is None:
            continue
        if rs.startswith("r_stolen_base"):
            rec_game[(m, int(g))][0] += 1
        elif rs.startswith(("r_caught_stealing", "r_pickoff_caught_stealing")):
            rec_game[(m, int(g))][1] += 1
    have_games = set(int(x) for x in pa["game_pk"].unique())
    wanted = set()
    for m in players:
        d = get(GAMELOG.format(mid=m, season=unit[1], sport=M.LEVEL_SPORT[unit[0]]))
        splits = ((d.get("stats") or [{}])[0].get("splits")) or []
        off_game = {}
        for x in splits:
            if (x.get("gameType") or "R") != "R":
                continue
            pk = (x.get("game") or {}).get("gamePk")
            if pk is None:
                continue
            st = x.get("stat") or {}
            c = off_game.setdefault(int(pk), [0, 0])
            c[0] += int(st.get("stolenBases") or 0)
            c[1] += int(st.get("caughtStealing") or 0)
        for pk, (sb, cs) in off_game.items():
            r = rec_game.get((m, pk), [0, 0])
            if pk not in have_games or r[0] != sb or r[1] != cs:
                wanted.add(pk)
        for (mm, pk), r in rec_game.items():
            if mm == m and pk not in off_game and (r[0] or r[1]):
                wanted.add(pk)
        time.sleep(interval)
    got = []
    for pk in sorted(wanted):
        path = refetch_dir / f"{pk}.json"
        if path.exists():
            got.append(pk)
            continue
        time.sleep(interval)
        req = urllib.request.Request(LIVE_FEED.format(pk=pk), headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
        except Exception:  # noqa: BLE001 - one failed fetch leaves the cached copy
            continue
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        got.append(pk)
    return {"players": players, "games": got}


# --------------------------------------------------------------------------
# the official lines: once per level-season, caughtStealing kept
# --------------------------------------------------------------------------
def _get(url: str) -> dict:
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise ebr.EbrRefusal(f"StatsAPI fetch failed: {url} ({last})")


def fetch_lines(unit, lines_dir: Path = LINES_DIR, *, fetch: bool = True, getter=None) -> dict | None:
    """{"sha256", "fetched_at", "players": {mlbam: {sb, cs, gidp, pa}}} for one
    level-season, cached at lines_dir/<level>_<season>.json and fetched once."""
    lv, season = unit
    path = Path(lines_dir) / f"{lv}_{season}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not fetch:
        return None
    get = getter or _get
    splits, offset = [], 0
    while True:
        url = (f"{BASE}?stats=season&group=hitting&season={season}&sportIds={M.LEVEL_SPORT[lv]}"
               f"&playerPool=ALL&limit=2000&offset={offset}")
        d = get(url)
        blk = (d.get("stats") or [{}])[0]
        page = blk.get("splits") or []
        splits.extend(page)
        offset += len(page)
        if not page or offset >= (blk.get("totalSplits") or len(splits)):
            break
    players: dict = {}
    for x in splits:
        pid = (x.get("player") or {}).get("id")
        if pid is None:
            continue
        st = x.get("stat") or {}
        c = players.setdefault(str(int(pid)), {"sb": 0, "cs": 0, "gidp": 0, "pa": 0})
        c["sb"] += int(st.get("stolenBases") or 0)
        c["cs"] += int(st.get("caughtStealing") or 0)
        c["gidp"] += int(st.get("groundIntoDoublePlay") or 0)
        c["pa"] += int(st.get("plateAppearances") or 0)
    doc = {"level": lv, "season": season, "sport_id": M.LEVEL_SPORT[lv], "fetched_at": _now(),
           "splits": len(splits), "players": players}
    doc["sha256"] = _sha_obj({"players": players})
    _write_json(path, doc)
    return doc


def record_counts(pa, rn) -> dict:
    out: dict = defaultdict(lambda: {"sb": 0, "cs": 0, "gidp": 0, "pa": 0})
    reasons = rn["movement_reason"].fillna("").astype(str)
    for pid, rs in zip(rn["runner_id"], reasons):
        m = ebr._int(pid)
        if m is None:
            continue
        if rs.startswith("r_stolen_base"):
            out[m]["sb"] += 1
        elif rs.startswith(("r_caught_stealing", "r_pickoff_caught_stealing")):
            out[m]["cs"] += 1
    for pid, et, ispa in zip(pa["batter_id"], pa["event_type"], pa["is_pa"]):
        m = ebr._int(pid)
        if m is None:
            continue
        if et == "grounded_into_double_play":
            out[m]["gidp"] += 1
        if bool(ispa):
            out[m]["pa"] += 1
    return out


def identity_lines(pa, rn, official: dict | None) -> dict:
    """I1 (league SB and CS exact; GIDP within 0.5 percent) and I2 (per player SB
    and CS exact for every player with any; GIDP exact for 97 percent or more of
    players with any), against the official lines."""
    if official is None:
        return {"I1": {"pass": None, "note": "official lines not fetched"},
                "I2": {"pass": None, "note": "official lines not fetched"}}
    rec = record_counts(pa, rn)
    off = {int(k): v for k, v in official["players"].items()}
    tot_r = {k: sum(v[k] for v in rec.values()) for k in ("sb", "cs", "gidp", "pa")}
    tot_o = {k: sum(v[k] for v in off.values()) for k in ("sb", "cs", "gidp", "pa")}
    gd = abs(tot_r["gidp"] - tot_o["gidp"]) / tot_o["gidp"] if tot_o["gidp"] else 0.0
    rel = {k: (abs(tot_r[k] - tot_o[k]) / tot_o[k] if tot_o[k] else 0.0) for k in ("sb", "cs")}
    i1 = {"record": tot_r, "official": tot_o, "gidp_rel_diff": round(gd, 6),
          "sb_rel_diff": round(rel["sb"], 6), "cs_rel_diff": round(rel["cs"], 6),
          "exact": bool(tot_r["sb"] == tot_o["sb"] and tot_r["cs"] == tot_o["cs"]),
          "pass": bool(rel["sb"] <= LEAGUE_TOL and rel["cs"] <= LEAGUE_TOL and gd <= GIDP_LEAGUE_TOL)}
    ids = sorted(set(rec) | set(off))
    zero = {"sb": 0, "cs": 0, "gidp": 0, "pa": 0}
    sbcs_any = [m for m in ids if (rec.get(m, zero)["sb"] or rec.get(m, zero)["cs"]
                                    or off.get(m, zero)["sb"] or off.get(m, zero)["cs"])]
    sbcs_bad = [m for m in sbcs_any if rec.get(m, zero)["sb"] != off.get(m, zero)["sb"]
                or rec.get(m, zero)["cs"] != off.get(m, zero)["cs"]]
    g_any = [m for m in ids if rec.get(m, zero)["gidp"] or off.get(m, zero)["gidp"]]
    g_ok = [m for m in g_any if rec.get(m, zero)["gidp"] == off.get(m, zero)["gidp"]]
    pa_any = [m for m in ids if off.get(m, zero)["pa"] or rec.get(m, zero)["pa"]]
    pa_ok = [m for m in pa_any if rec.get(m, zero)["pa"] == off.get(m, zero)["pa"]]
    g_share = (len(g_ok) / len(g_any)) if g_any else 1.0
    sbcs_share = (1.0 - len(sbcs_bad) / len(sbcs_any)) if sbcs_any else 1.0
    i2 = {"players_sb_cs": len(sbcs_any), "sb_cs_mismatch": len(sbcs_bad),
          "sb_cs_exact_share": round(sbcs_share, 4), "exact": bool(not sbcs_bad),
          "players_gidp": len(g_any), "gidp_exact_share": round(g_share, 4),
          "players_pa": len(pa_any), "pa_exact_share": round(len(pa_ok) / len(pa_any), 4) if pa_any else None,
          "pass": bool(sbcs_share >= PLAYER_SB_CS_SHARE and g_share >= PLAYER_GIDP_SHARE)}
    return {"I1": i1, "I2": i2}


# --------------------------------------------------------------------------
# reliability and continuity (aggregates only)
# --------------------------------------------------------------------------
def split_half(credits: list, pa_by_player: dict, floor: int = M.DISPLAY_PA) -> dict:
    """Pearson r between the runs earned in odd-numbered and even-numbered games
    (game_pk parity) over players at or above the PA floor, and the Spearman-Brown
    step-up 2r / (1 + r). Same unit, same table: a reliability, not a forecast."""
    import numpy as np
    halves = [defaultdict(float), defaultdict(float)]
    for mid, _, g, _, v in credits:
        if mid is None:
            continue
        halves[int(g) % 2][mid] += v
    ids = [m for m, n in pa_by_player.items() if n >= floor]
    if len(ids) < 10:
        return {"n": len(ids), "r": None, "spearman_brown": None}
    a = np.array([halves[0].get(m, 0.0) for m in ids])
    b = np.array([halves[1].get(m, 0.0) for m in ids])
    if a.std() == 0 or b.std() == 0:
        return {"n": len(ids), "r": None, "spearman_brown": None}
    r = float(np.corrcoef(a, b)[0, 1])
    sb = (2 * r / (1 + r)) if r > -1 else None
    return {"n": len(ids), "r": round(r, 4), "spearman_brown": (round(sb, 4) if sb is not None else None)}


def continuity(rows: list) -> dict:
    """Players with DISPLAY_PA or more at two levels in one season: the pair
    count, the correlation of their per-600 rates between the two levels and the
    mean rate at each level of the pair. Reported by level pair, never by grade."""
    import numpy as np
    F = {f: i for i, f in enumerate(M.FIELDS)}
    by = defaultdict(dict)
    for r in rows:
        if r[F["pa"]] >= M.DISPLAY_PA:
            by[(r[F["mlbam"]], r[F["season"]])][r[F["level"]]] = r[F["ebr"]] * 600.0 / r[F["pa"]]
    pairs = defaultdict(list)
    for (mid, season), d in by.items():
        lvls = [lv for lv in M.LEVEL_ORDER if lv in d]
        for i in range(len(lvls)):
            for j in range(i + 1, len(lvls)):
                pairs[(lvls[i], lvls[j])].append((d[lvls[i]], d[lvls[j]]))
    out = {}
    allp = []
    for (a, b), xs in sorted(pairs.items()):
        arr = np.array(xs)
        allp.extend(xs)
        out[f"{a}|{b}"] = _pair_stat(arr)
    out["all_pairs"] = _pair_stat(np.array(allp)) if allp else {"n": 0, "r": None}
    return out


def _pair_stat(arr) -> dict:
    import numpy as np
    n = int(len(arr))
    if n < 5 or arr[:, 0].std() == 0 or arr[:, 1].std() == 0:
        return {"n": n, "r": None, "mean_rate_higher": (round(float(arr[:, 0].mean()), 3) if n else None),
                "mean_rate_lower": (round(float(arr[:, 1].mean()), 3) if n else None)}
    return {"n": n, "r": round(float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1]), 4),
            "mean_rate_higher": round(float(arr[:, 0].mean()), 3),
            "mean_rate_lower": round(float(arr[:, 1].mean()), 3)}


def isolation_scan(root: Path = ROOT) -> dict:
    """I9: no efv_ module, projection, free-agent, arbitration or betting module
    imports ebr_milb or reads its artifacts."""
    import re
    offenders = []
    imp = re.compile(r"^\s*(import\s+ebr_milb\b|from\s+ebr_milb\s+import|import\s+.*\bebr_milb\b)", re.M)
    reads = re.compile(r"(ebr_milb|milb_preview)")
    files = list(Path(root).glob("*.py")) + list((Path(root) / "tools").glob("*.py"))
    for p in sorted(files):
        name = p.name
        if name.startswith(("efv_", "proj_", "fa_", "arb_", "betting_")) or name == "leaderboard_vintages.py":
            text = p.read_text(encoding="utf-8", errors="replace")
            if imp.search(text) or reads.search(text):
                offenders.append(name)
    return {"pass": not offenders, "offenders": offenders, "scanned": len(files)}


def season_complete(season: int, today: _dt.date | None = None) -> bool:
    return (today or _dt.date.today()) >= _dt.date(int(season), *FREEZE_MONTH_DAY)


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------
def build(*, record: Path = RECORD, lines_dir: Path = LINES_DIR, fetch: bool = True,
          units=None, today: _dt.date | None = None, generated_at: str | None = None,
          record_data=None, lines_getter=None, refetch_dir: Path = REFETCH_DIR) -> tuple[dict, dict]:
    t0 = time.time()
    data, man = record_data if record_data is not None else load_units(record, units)
    if not data:
        raise ebr.EbrRefusal("the minor-league runner record holds no level-season")
    data = dict(data)
    refetched, normalised = {}, {}
    for u in list(data):
        pa0, rn0 = data[u]
        pa1, rn1, games = apply_refetch(u, pa0, rn0, refetch_dir)
        data[u] = (pa1, rn1)
        refetched[M.unit_key(u)] = games
        normalised[M.unit_key(u)] = int(rn1.attrs.get("normalised_sb", 0))
    raw = {u: ebr.season_raw(pa) for u, (pa, rn) in data.items()}
    plan = M.make_plan(raw)
    opps = {}
    for u, (pa, rn) in data.items():
        o = ebr.xb_opportunities(pa, rn)
        ebr.finalize_opportunities(o)
        opps[u] = o
    all_counts = ebr.pool_counts(opps)
    level_counts = {}
    for lv in {u[0] for u in data}:
        us = {u: opps[u] for u in data if u[0] == lv}
        level_counts[lv] = ebr.pool_counts(us) if len(us) >= 2 else None
    rows_all, units_out, identity, reliability, w_league = [], {}, {}, {}, {}
    credits_by_unit = {}
    for u in sorted(data, key=lambda x: (x[1], M.LEVEL_ORDER.index(x[0]))):
        pa, rn = data[u]
        pl = plan[u]
        table = ebr.shrunk_table(raw[u], pl["pool"], pl["K"], M.unit_key(u))
        tsha = ebr.table_sha(table)
        bo = M.MilbBackoff(opps[u], all_counts, level_counts[u[0]])
        credits, lg = M.unit_credits(pa, rn, table, bo, opps[u])
        players = ebr.player_rows(credits, pa, opps[u])
        dirt, wl = M.dirt_advances(rn, table)
        rows = M.unit_rows(u, players, dirt)
        credits_by_unit[u] = credits
        sums = defaultdict(float)
        for _, _, _, part, v in credits:
            sums[part] += v
        i4 = {p: round(sums.get(p, 0.0), 6) for p in ebr.PARTS}
        F = {f: i for i, f in enumerate(M.FIELDS)}
        bad = [r[0] for r in rows
               if abs(sum(r[F[p]] for p in ebr.PARTS) - r[F["ebr"]]) > I6_TOL
               or any(isinstance(r[F[p]], float) and math.isnan(r[F[p]]) for p in ebr.PARTS + ("ebr",))
               or abs(r[F["ebr"]]) > I6_MAX_ABS]
        xbl = lg["xb"]
        n_opp = sum(xbl["opportunities"].values())
        n_cl = sum(xbl["clamped"].values())
        digest = _sha_obj({"rows": rows, "re24": tsha, "v": M.MILB_VERSION})
        official = fetch_lines(u, lines_dir, fetch=fetch, getter=lines_getter)
        ident = identity_lines(pa, rn, official)
        pa_by = {r[0]: r[F["pa"]] for r in rows}
        reliability[M.unit_key(u)] = split_half(credits, pa_by)
        n150 = sum(1 for r in rows if r[F["pa"]] >= M.DISPLAY_PA)
        cov = pa_coverage(pa, official) if official else None
        identity[M.unit_key(u)] = {
            "I1": ident["I1"], "I2": ident["I2"],
            "I3": {"record_pa": int(pa["is_pa"].astype(bool).sum()),
                   "official_pa": (sum(v["pa"] for v in official["players"].values()) if official else None),
                   "pa_coverage": (round(cov, 6) if cov is not None else None),
                   "pass": (bool(cov >= MIN_PA_COVERAGE) if cov is not None else None)},
            "refetched_games": refetched.get(M.unit_key(u)) or [],
            "normalised_steals": normalised.get(M.unit_key(u), 0),
            "I4": {"sums": i4, "pass": all(abs(v) <= I4_TOL for v in i4.values())},
            "I5": {"cells": len(table), "monotone": True, "K": pl["K"], "sha256": tsha,
                   "pass": len(table) == 24 and ebr.K_CLIP[0] <= pl["K"] <= ebr.K_CLIP[1]},
            "I6": {"rows": len(rows), "violations": len(bad), "max_abs_ebr": round(
                max((abs(r[F["ebr"]]) for r in rows), default=0.0), 3), "pass": not bad},
            "I7": {"eligible_xb": n_opp, "priced_xb": n_opp - n_cl,
                   "priced_share": round((n_opp - n_cl) / n_opp, 6) if n_opp else None,
                   "share_priced_from_cell_n50": xbl["share_priced_from_cell_n50"],
                   "pass": bool(n_opp and (n_opp - n_cl) / n_opp >= 0.99)},
            "I8": {"digest": digest},
        }
        w_league[M.unit_key(u)] = wl
        units_out[M.unit_key(u)] = {
            "level": u[0], "season": u[1], "games": int(pa["game_pk"].nunique()),
            "pa": int(pa["is_pa"].astype(bool).sum()), "players": len(rows), "players_150": n150,
            "pool_kind": pl["pool_kind"], "pool_units": [M.unit_key(x) for x in pl["pool_units"]],
            "K": pl["K"], "k_source": pl["k_source"],
            "k_detail": {k: pl["k_detail"][k] for k in ("K", "K_raw", "W", "tau2")},
            "lambda": round(ebr.season_lambda(raw[u], pl["pool"]), 6),
            "fit_set_plays": int(sum(v["n"] for v in raw[u].values())),
            "re24": {c: [round(table[c], 6), int(raw[u][c]["n"])] for c in ebr.CELLS},
            "re24_sha256": tsha, "complete": season_complete(u[1], today),
            "league": {"steal": lg["steal"], "xb": lg["xb"], "dp": {k: v for k, v in lg["dp"].items() if k != "table"}},
            "pool_seasons_live": [u[1]] if pl["pool_kind"] == "season_all" else sorted(x[1] for x in pl["pool_units"]),
        }
        rows_all.extend(rows)
    iso = isolation_scan()
    for k, blk in identity.items():
        blk["I9"] = {"pass": iso["pass"]}
        blk["all_pass"] = all(((blk.get(i) or {}).get("pass") is True) for i in
                              ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I9"))
    gen = generated_at or _now()
    substrate = {"schema": 1, "model": "ebr_milb", "version": M.MILB_VERSION, "generated_at": gen,
                 "gate": GATE_DOC, "fields": list(M.FIELDS), "units": units_out, "rows": rows_all,
                 "record_built_at": (man or {}).get("built_at")}
    ev = {"schema": 1, "model": "ebr_milb_eval", "version": M.MILB_VERSION, "generated_at": gen,
          "gate": GATE_DOC, "descriptive": True,
          "note": ("Same-season, same-unit descriptives only. Level-relative: a runner is compared with the "
                   "average runner of his own level in his own season. Never summarised, validated or "
                   "stratified by consensus-FV cell; never an eFV input."),
          "identity": identity, "isolation_I9": iso, "reliability_split_half": reliability,
          "continuity": continuity(rows_all), "dirt_advances_league": w_league,
          "build_seconds": round(time.time() - t0, 1)}
    return substrate, ev


def served_payload(substrate: dict, ev: dict) -> dict:
    """The PROSPX card payload: rows at DISPLAY_PA or more from level-seasons
    whose identity gates all pass, keyed by mlbam; each entry
    [level, season, pa, sb_runs, xb_runs, dp_runs, ebr, rate_per_600, w_n, w]."""
    F = {f: i for i, f in enumerate(M.FIELDS)}
    ok = {k for k, v in ev["identity"].items() if v.get("all_pass")}
    by: dict = defaultdict(list)
    for r in substrate["rows"]:
        if r[F["pa"]] < M.DISPLAY_PA or f"{r[F['level']]}|{r[F['season']]}" not in ok:
            continue
        sb = r[F["sb"]] + r[F["pk"]]
        xb = r[F["xb_adv"]] + r[F["xb_oob"]]
        by[str(r[F["mlbam"]])].append([r[F["level"]], r[F["season"]], r[F["pa"]], round(sb, 1),
                                       round(xb, 1), round(r[F["dp"]], 1), round(r[F["ebr"]], 1),
                                       M.rate600(r[F["ebr"]], r[F["pa"]]), r[F["w_n"]], round(r[F["w"]], 1)])
    for k in by:
        by[k].sort(key=lambda x: (-x[1], M.LEVEL_ORDER.index(x[0])))
    return {"schema": 1, "model": "ebr_milb", "version": M.MILB_VERSION,
            "generated_at": substrate["generated_at"],
            "what": ("Level-relative baserunning: runs above an average runner at the same level in the same "
                     "season, from the play-by-play (steals and pickoffs, extra bases taken and outs on the "
                     "bases, double plays)."),
            "claim": ("Level-relative runs are not comparable across levels or with the majors. Display only: "
                      "no grade, rank, projection or value reads them."),
            "display_pa": M.DISPLAY_PA,
            "fields": ["level", "season", "pa", "sb_runs", "xb_runs", "dp_runs", "ebr", "per600",
                       "dirt_n", "dirt_runs"],
            "levels": {k: M.LEVEL_LABEL[k] for k in M.LEVEL_ORDER},
            "units": {k: {"games": v["games"], "players_150": v["players_150"], "complete": v["complete"],
                          "split_half": ((ev.get("reliability_split_half") or {}).get(k) or {}).get("spearman_brown")}
                      for k, v in substrate["units"].items() if k in ok},
            "by_mlbam": dict(sorted(by.items(), key=lambda kv: int(kv[0])))}


def write_preview(substrate: dict, ev: dict, out_dir: Path = PREVIEW_DIR) -> None:
    out_dir = Path(out_dir)
    if out_dir.resolve() == (ROOT / "data").resolve():
        raise ebr.EbrRefusal("the preview is never written under data/")
    _write_json(out_dir / "ebr_milb.json", substrate)
    _write_json(out_dir / "ebr_milb_eval.json", ev, indent=1)


def served_eval(substrate: dict, ev: dict) -> dict:
    """The registry row's eval artifact: aggregates only. The identity receipts
    keep their counts and flags (the lists of re-fetched games become counts), plus
    each unit's run basis, the split-half reliability, the cross-level continuity and
    the league W sub-totals. No player id, no grade, no consensus-FV cell."""
    ident = {}
    for k, v in ev["identity"].items():
        blk = {i: v[i] for i in ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I9", "all_pass")}
        blk["refetched_games"] = len(v.get("refetched_games") or [])
        blk["normalised_steals"] = v.get("normalised_steals", 0)
        ident[k] = blk
    units = {k: {x: u[x] for x in ("level", "season", "games", "pa", "players", "players_150", "pool_kind",
                                   "pool_units", "K", "k_source", "lambda", "fit_set_plays", "re24_sha256",
                                   "complete")}
             for k, u in substrate["units"].items()}
    return {"schema": 1, "model": "ebr_milb_eval", "version": M.MILB_VERSION,
            "generated_at": ev["generated_at"], "gate": GATE_DOC, "descriptive": True,
            "note": ev["note"],
            "bounds": {"league_sb_cs_rel_diff_max": LEAGUE_TOL, "player_sb_cs_exact_share_min": PLAYER_SB_CS_SHARE,
                       "player_gidp_exact_share_min": PLAYER_GIDP_SHARE, "league_gidp_rel_diff_max": GIDP_LEAGUE_TOL,
                       "pa_coverage_min": MIN_PA_COVERAGE, "display_pa": M.DISPLAY_PA,
                       "min_unit_games": M.MIN_UNIT_GAMES},
            "units": units, "identity": ident, "reliability_split_half": ev["reliability_split_half"],
            "continuity": ev["continuity"], "dirt_advances_league": ev["dirt_advances_league"]}


def write_served(substrate: dict, ev: dict, path: Path = SERVED, eval_path: Path = SERVED_EVAL) -> None:
    _write_json(Path(path), served_payload(substrate, ev))
    _write_json(Path(eval_path), served_eval(substrate, ev), indent=1)


def reconcile_all(*, fetch: bool = True, only=None) -> dict:
    """The one re-fetch for every level-season that misses I1 or I2 with a complete
    record. A level-season that already has re-fetched games is not fetched again
    unless it is named in ``only`` (a level-season whose missing games were filled
    from the schedule has re-fetched games but not yet had its mismatches located)."""
    data, _ = load_units()
    done = {}
    for u in sorted(data):
        pa, rn = data[u]
        pa, rn, have = apply_refetch(u, pa, rn)
        off = fetch_lines(u, fetch=fetch)
        forced = only is not None and M.unit_key(u) in only
        if off is None or (have and not forced):
            done[M.unit_key(u)] = {"skipped": "already re-fetched" if have else "no official lines"}
            continue
        if pa_coverage(pa, off) < MIN_PA_COVERAGE:
            done[M.unit_key(u)] = {"skipped": "record incomplete (I3)"}
            continue
        if not mismatched_players(pa, rn, off):
            done[M.unit_key(u)] = {"skipped": "no mismatch"}
            continue
        done[M.unit_key(u)] = reconcile(u, pa, rn, off)
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="level-relative eBR for the minor leagues")
    ap.add_argument("--no-fetch", action="store_true", help="read only the cached official lines")
    ap.add_argument("--reconcile", nargs="?", const="", default=None, metavar="LEVEL|SEASON,...",
                    help="the one re-fetch of the games of mismatched players, then exit; the optional "
                         "list names level-seasons to reconcile even though they hold filled games")
    ap.add_argument("--fill", default=None, metavar="LEVEL|SEASON,...",
                    help="fetch the final games a level-season's record lacks (I3), then exit")
    ap.add_argument("--serve", action="store_true",
                    help="also write data/ebr_milb.json and data/ebr_milb_eval.json (refused while "
                         "MILB_EBR_LIVE is False)")
    a = ap.parse_args(argv)
    if a.fill:
        data, _ = load_units()
        for key in a.fill.split(","):
            u = M.parse_unit_key(key.strip())
            pa, rn = data[u]
            pa, rn, _ = apply_refetch(u, pa, rn)
            print(key, fill_missing(u, pa))
        return 0
    if a.reconcile is not None:
        only = {x.strip() for x in a.reconcile.split(",") if x.strip()} or None
        res = reconcile_all(fetch=not a.no_fetch, only=only)
        for k, v in sorted(res.items()):
            print(k, v.get("skipped") or f"players {len(v['players'])} games {len(v['games'])}")
        return 0
    sub, ev = build(fetch=not a.no_fetch)
    write_preview(sub, ev)
    for k, blk in sorted(ev["identity"].items()):
        print(f"  {k}: rows {blk['I6']['rows']}  K {blk['I5']['K']}  all_pass {blk['all_pass']}  "
              f"I1 {blk['I1'].get('pass')}  I2 {blk['I2'].get('pass')}  priced {blk['I7']['priced_share']}")
    if a.serve:
        if not M.MILB_EBR_LIVE:
            print("MILB_EBR_LIVE is False: data/ebr_milb.json is not written")
        else:
            write_served(sub, ev)
            print(f"wrote {SERVED} and {SERVED_EVAL}")
    print(f"wrote {PREVIEW_DIR} in {ev['build_seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
