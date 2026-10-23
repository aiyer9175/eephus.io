# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PE-H old-seasons read (docs/ewar-v3/EWAR_PEH_OLD_SEASONS_GATE.md, owner decision
EW3-50): one registered read of the hitter pitch-economy part PE-H, defined exactly as
docs/ebr-2026-09-30/EBR_GATE.md part 11.4.3 defines it, on predictor seasons 2002 to
2014 (outcome seasons 2003 to 2015), which no PE-H number had touched.

    python tools/peh_old_seasons_lab.py --build-inputs    # corpus, runner record, season tables
    python tools/peh_old_seasons_lab.py --dry-run         # fixtures with nulls, a temp dir only
    python -u tools/peh_old_seasons_lab.py --read         # THE READ, once

WHAT IS FIXED, BY REGISTRATION (gate part 3). The part, its frozen constants
(pitch_economy DELTA_TTO, K_CL, K_P) and its arithmetic (pitch_economy_lab's walk,
class means and residuals; swar_targets.pe_h_deltas) are the skill look's, unchanged.
The target is wRAA(Y+1) + W(Y+1) per PA (rate cell) and in runs (total cell); B0 is
wRAA(Y); hitters 200 PA in both seasons; the Spearman gap, convention v2 primary (a
player-clustered, season-stratified bootstrap on the within-outcome-season z target)
with convention v1 required to agree in sign, swar_lab's own cell code
(prep_primary, finish_primary, decide_family); the Holm family {PE-H rate, PE-H
total}; B1 at the look's frozen k (427 PA); the twin; the sensitivity guard on
wRAA(Y+1) alone; the team guard of 11.2.4 on the club-seasons 2003 to 2015. B = 4,000
and seed 20261023 for every bootstrap. A club-clustered companion interval (franchises
of the Y+1 club drawn with replacement) is printed beside each cell, and a pass needs
its lo95 above 0 on the rate cell as well.

CONTROLS (gate part 4), on the real frame, before the real cells: the null comparator
(an all-zero delta) must not read WIN or SMALL WIN on either cell, and a planted delta
(half of each pair's own Y+1 target deviation, in Y's exposure) must read WIN
(components) on both cells with its twin failing. A failed control stops the read
before any real cell is scored and writes a VOID record.

INPUTS. Caches only, never fetched by the read: the winProbability payloads
(.cache/win_prob_hist for 2011 to 2015, .cache/win_prob_old for 2002 to 2010, the
latter written by tools/fetch_win_prob_old.py); the play-by-play corpus and the runner
record this tool builds from them under .cache/peh_old/ (2011 to 2015 runner record:
.cache/pbp_runners, as eBR built it); eBR's frozen RE24 pool and RE288's frozen count
pool; the StatsAPI season lines and start and relief split lines; the frozen fWAR
vintage (data/fwar_vintage.json); data/league_constants.json; the cached StatsAPI
standings; war_source's last-good Baseball-Reference stint cache. The read WRITES only
its record (docs/ewar-v3/peh_old_seasons_eval.json); nothing under data/ moves.

CRASH PROTOCOL. The operator tees stdout and stderr to the writer's output directory.
An exception after scoring began writes a VOID record and exits 3; no rerun.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import math
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pitch_economy as pe  # noqa: E402
import swar_lab as L  # noqa: E402
import swar_targets as T  # noqa: E402

LAB_VERSION = "peh_old_seasons_lab/1"
GATE_DOC = "docs/ewar-v3/EWAR_PEH_OLD_SEASONS_GATE.md"
RECORD_PATH = ROOT / "docs" / "ewar-v3" / "peh_old_seasons_eval.json"

CACHE = ROOT / ".cache"
OLD_ROOT = CACHE / "peh_old"
CORPUS_OLD = OLD_ROOT / "corpus"
RECORD_OLD = OLD_ROOT / "runners"
TABLES_PATH = OLD_ROOT / "season_tables.json"
HIST_SRC = CACHE / "win_prob_hist"
OLD_SRC = CACHE / "win_prob_old"
RECORD_LIVE = CACHE / "pbp_runners"
VINTAGE = ROOT / "data" / "fwar_vintage.json"
LEAGUE_CONSTANTS = ROOT / "data" / "league_constants.json"
COUNT_VALUE = ROOT / "data" / "count_value.json"

# --------------------------------------------------------------------------
# registered parameters (gate part 3)
# --------------------------------------------------------------------------
SEASONS = tuple(range(2002, 2016))
PREDICTOR_SEASONS = tuple(range(2002, 2015))
RUNNER_LIVE_SEASONS = (2011, 2012, 2013, 2014, 2015)       # eBR's record already holds these
BOOT = 4000
SEED = 20261023
TWIN_SEED = SEED + 101
CLUB_SEED = SEED + 202
PLANT_SHARE = 0.5
K_B1_PEH = L.B1_K_AMENDED["peh"]                          # 427 PA, frozen at the look
K_B1_SECONDARY = L.B1_K["hit"]                            # 662 PA, the secondary estimand's
#: Season admission (gate part 3.3): the RE288 identity share and the pitch and
#: game coverage a season must reach, else it leaves the frame on both sides.
MIN_IDENTITY_SHARE = 0.999
MIN_PITCH_COVERAGE = 0.99
MIN_GAME_COVERAGE = 0.99
MIN_PREDICTOR_SEASONS = 6
#: The bWAR stint frames' club codes of 2002 to 2015 that the StatsAPI standings key
#: under the franchise's current code (ewar._CLUB_TO_BREF), and the one club the
#: standings reader cannot name (the Montreal Expos, 2002 to 2004).
STANDINGS_KEY = {"ANA": "LAA", "FLA": "MIA", "TBD": "TBR", "MON": "WSN"}
EXTRA_CLUB_NAMES = {"Expos": "WSN"}
#: Solved-weight receipt tolerances (gate part 3.2).
TOL_SCALE = 0.0005
TOL_WEIGHT = 0.002

PART = L.PART_PE_H
RATE, CUM = L.RATE, L.CUM
CELLS = {"PE-H rate": RATE, "PE-H total": CUM}


class ReadStop(RuntimeError):
    """A precondition failed before scoring began: nothing is written."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _p(log: Callable, *a) -> None:
    log(*a)


def _f(v, nd=4) -> str:
    return "None" if v is None else f"{v:+.{nd}f}"


def _r(v, nd=5):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return round(f, nd) if math.isfinite(f) else None


# ==========================================================================
# inputs: the corpus, the runner record and the season tables (no PE-H number)
# ==========================================================================
def source_of(season: int) -> Path:
    return HIST_SRC if int(season) >= 2011 else OLD_SRC


def record_of(season: int) -> Path:
    return RECORD_LIVE if int(season) in RUNNER_LIVE_SEASONS else RECORD_OLD


def scheduled_paths(season: int) -> tuple[list[Path], int]:
    """The payloads of a season's listed final games present on disk, and the count listed."""
    src = source_of(season)
    sched = json.loads((src / "schedule" / f"{int(season)}.json").read_text(encoding="utf-8"))
    paths = [src / f"{int(pk)}.json" for pk, _d in sched]
    return [p for p in paths if p.exists()], len(sched)


def build_corpus(seasons: Iterable[int], log: Callable = print) -> dict:
    import build_pbp_corpus as BPC
    out = {}
    for s in seasons:
        paths, n_listed = scheduled_paths(s)
        man = BPC.build(source_of(s), CORPUS_OLD, seasons=[int(s)], paths_by_season={int(s): paths},
                        force=True)
        out[str(s)] = {"listed": n_listed, "payloads": len(paths),
                       "rows": (man["seasons"].get(str(s)) or {}).get("rows")}
        log(f"  corpus {s}: {len(paths)}/{n_listed} payloads, rows {out[str(s)]['rows']}")
    return out


def build_runners(seasons: Iterable[int], log: Callable = print, workers: int = 4) -> dict:
    import build_runner_moves as BRM
    man = BRM.load_manifest(RECORD_OLD)
    out = {}
    for s in seasons:
        if int(s) in RUNNER_LIVE_SEASONS:
            continue
        blk = BRM.build_season(int(s), out_dir=RECORD_OLD, source=OLD_SRC, workers=workers,
                               allow_refetch=False, man=man)
        rc = blk.get("receipts") or {}
        out[str(s)] = {"games_present": blk.get("games_present"), "games_scheduled": blk.get("games_scheduled"),
                       "I1": (rc.get("I1") or {}).get("pass"), "I2": (rc.get("I2") or {}).get("pass"),
                       "I3": (rc.get("I3") or {}).get("pass")}
        log(f"  runner record {s}: {out[str(s)]}")
    man["schema_version"] = BRM.SCHEMA_VERSION
    man["built_at"] = man["generated_at"] = _now()
    man["source_cache"] = str(OLD_SRC)
    BRM.write_manifest(RECORD_OLD, man)
    return out


def load_record_pa(season: int):
    import pandas as pd
    rec = record_of(season)
    man = json.loads((rec / "manifest.json").read_text(encoding="utf-8"))
    blk = (man.get("seasons") or {}).get(str(int(season)))
    if not blk:
        raise ReadStop(f"the runner record lacks {season}")
    return pd.read_parquet(rec / blk["files"]["pa"]), blk


def season_table(season: int, pa=None) -> dict:
    """RE24_s (eBR's shrink toward its frozen pool) and RE288_s = RE24_s + lambda_s x the
    frozen pooled count departure, exactly as tools/build_count_value.py builds a season."""
    import build_count_value as BCV
    import count_value as cv
    import ebr
    pool24 = BCV.load_ebr_pool()
    pool_cv = json.loads(BCV.pool_path().read_text(encoding="utf-8"))
    cv.check_frozen_pool(pool_cv)
    if pa is None:
        pa, _ = load_record_pa(season)
    raw24 = ebr.season_raw(pa)
    re24 = ebr.shrunk_table(raw24, pool24["re_pool"], float(pool24["K"]), int(season))
    lam = float(ebr.season_lambda(raw24, pool24["re_pool"]))
    d_pool = {c: float(pool_cv["d_pool"][c]) for c in cv.CELLS}
    t288 = cv.assemble(re24, cv.pooled_departure(d_pool, lam))
    return {"lambda": lam, "re24": {c: float(v) for c, v in re24.items()},
            "re288": {c: float(v) for c, v in t288.items()},
            "re24_sha256": ebr.table_sha(re24), "re288_sha256": cv.table_sha(t288),
            "count_monotone_violations": len(cv.count_monotone_violations(t288))}


def table_receipt(season: int = 2019) -> dict:
    """The season-table path reproduces data/count_value.json's own table of a pool season."""
    import build_count_value as BCV
    pa = BCV.load_season(season)["pa"]
    mine = season_table(season, pa)
    doc = json.loads(COUNT_VALUE.read_text(encoding="utf-8"))
    blk = doc["by_season"][str(season)]
    d288 = max(abs(round(mine["re288"][c], 4) - float(blk["re288"][c])) for c in blk["re288"])
    d24 = max(abs(round(mine["re24"][c], 4) - float(blk["re24"][c])) for c in blk["re24"])
    return {"season": season, "max_abs_re288": d288, "max_abs_re24": d24,
            "lambda": mine["lambda"], "lambda_count_value": blk.get("lambda"),
            "pass": bool(d288 <= 1e-4 and d24 <= 1e-4)}


def build_tables(seasons: Iterable[int], log: Callable = print) -> dict:
    rec = table_receipt()
    log(f"  table receipt (2019 rebuilt by this path against data/count_value.json): {rec}")
    if not rec["pass"]:
        raise ReadStop(f"the season-table path does not reproduce data/count_value.json: {rec}")
    out = {"generated_at": _now(), "receipt": rec, "seasons": {}}
    for s in seasons:
        out["seasons"][str(s)] = season_table(s)
        log(f"  season table {s}: lambda {out['seasons'][str(s)]['lambda']:.4f}, "
            f"monotone violations {out['seasons'][str(s)]['count_monotone_violations']}")
    TABLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TABLES_PATH.write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    return out


# ==========================================================================
# the season's solved weights (gate part 3.2)
# ==========================================================================
def _vintage() -> dict:
    if not hasattr(_vintage, "_doc"):
        _vintage._doc = json.loads(VINTAGE.read_text(encoding="utf-8"))
    return _vintage._doc


def vintage_group(season: int, group: str) -> dict:
    """{mlbam: {field: value}} of one group of the frozen fWAR vintage."""
    doc = _vintage()
    blk = ((doc.get("seasons") or {}).get(str(int(season))) or {}).get(group) or {}
    fields = blk.get("fields") or (doc.get("fields") or {}).get(group) or []
    out = {}
    for pid, row in (blk.get("rows") or {}).items():
        out[int(pid)] = dict(zip(fields, row))
    return out


def _vintage_saber_rows(season: int) -> list:
    rows = []
    for pid, r in vintage_group(season, "hitting").items():
        rows.append({"player": {"id": pid}, "numTeams": r.get("numTeams"),
                     "stat": {"woba": r.get("woba"), "wRaa": r.get("wRaa")}})
    return rows


@contextlib.contextmanager
def _saber_from_vintage():
    import league_constants as lc
    keep = lc._saber_rows
    lc._saber_rows = _vintage_saber_rows
    try:
        yield lc
    finally:
        lc._saber_rows = keep


def solve_from_vintage(season: int) -> Optional[dict]:
    """league_constants.solve_season with the vintage's woba and wRaa rows in place of
    the sabermetrics cache (the same StatsAPI feed, frozen)."""
    with _saber_from_vintage() as lc:
        return lc.solve_season(int(season))


def weights_receipt(seasons=(2011, 2012, 2013, 2014, 2015)) -> dict:
    art = json.loads(LEAGUE_CONSTANTS.read_text(encoding="utf-8"))["seasons"]
    out = {"seasons": {}, "pass": True}
    for s in seasons:
        a, v = art.get(str(s)) or {}, solve_from_vintage(s) or {}
        if not a or not v or "woba_weights" not in v:
            out["seasons"][str(s)] = {"pass": False, "why": "unsolved"}
            out["pass"] = False
            continue
        ds = abs(float(a["woba_scale"]) - float(v["woba_scale"]))
        dl = abs(float(a["lg_woba"]) - float(v["lg_woba"]))
        dw = max(abs(float(a["woba_weights"][k]) - float(v["woba_weights"][k])) for k in a["woba_weights"])
        ok = ds <= TOL_SCALE and dl <= TOL_SCALE and dw <= TOL_WEIGHT
        out["seasons"][str(s)] = {"d_scale": round(ds, 5), "d_lg_woba": round(dl, 5), "d_weight_max": round(dw, 5),
                                  "pass": ok}
        out["pass"] = out["pass"] and ok
    return out


def season_weights(season: int) -> dict:
    """{weights, scale, lg_woba, source}: the artifact's solve from 2011, the vintage's before."""
    art = json.loads(LEAGUE_CONSTANTS.read_text(encoding="utf-8"))["seasons"]
    blk = art.get(str(int(season)))
    src = "data/league_constants.json"
    if not blk or "woba_weights" not in blk:
        blk = solve_from_vintage(season)
        src = "solved from the frozen vintage's woba and wRaa (league_constants.solve_season)"
    if not blk or "woba_weights" not in blk:
        raise ReadStop(f"no solved weights for {season}")
    return {"weights": dict(blk["woba_weights"]), "scale": float(blk["woba_scale"]),
            "lg_woba": float(blk["lg_woba"]), "source": src}


# ==========================================================================
# one season's rows (same-season quantities only)
# ==========================================================================
def season_wear(season: int) -> dict:
    """w_s and its inputs, as swar_targets.Readers.pitch_economy_wear computes it."""
    import league_constants as lc
    import pitch_economy_lab as pel
    tot = lc.league_totals(int(season)) or {}
    if not tot:
        raise ReadStop(f"league totals for {season} are missing")
    lines = pel.pit_lines(int(season))
    sprp = pel.sprp_lines(int(season))
    rf = pel.role_fip(lines, float(tot["fip_constant"]))
    lr = pel.league_role(sprp)
    t9s = pe.t9(float(tot["lg_pa"]) / (float(tot["lg_ip"]) * 3.0), pe.DELTA_TTO)
    w = pe.wear_price(rf["RP"], rf["SP"], t9s, lr["SP"]["l_ppo"])
    p_lines = sum(v["pitches"] for v in lines.values())
    p_split = sum(v[r]["pitches"] for v in sprp.values() for r in v)
    return {"w": float(w), "f_rp": rf["RP"], "f_sp": rf["SP"], "t9": t9s, "l_ppo_sp": lr["SP"]["l_ppo"],
            "rpw": float(tot["rpw"]), "split_pitch_share": (p_split / p_lines if p_lines else None),
            "line_pitches": p_lines}


def load_corpus(season: int, pa_record) -> dict:
    import pandas as pd
    s = int(season)
    plays = pd.read_parquet(CORPUS_OLD / "plays" / str(s) / f"plays-{s}.parquet",
                            columns=["game_pk", "at_bat_index", "pitcher_id", "outs_before", "outs_after"])
    pit = pd.read_parquet(CORPUS_OLD / "pitches" / str(s) / f"pitches-{s}.parquet",
                          columns=["game_pk", "at_bat_index", "pitch_number", "call_code"])
    ev = pd.read_parquet(CORPUS_OLD / "events" / str(s) / f"events-{s}.parquet",
                         columns=["game_pk", "at_bat_index", "index", "type", "description"])
    pa = pa_record[["game_pk", "at_bat_index", "half", "batter_id", "is_pa", "event_type", "outs_before",
                    "on_first", "on_second", "on_third", "end_on_first", "end_on_second", "end_on_third",
                    "end_outs", "runs_scored_on_play", "states_json"]]
    return {"pa": pa, "plays": plays, "pitches": pit, "events": ev}


def season_hitters(season: int, tables: Mapping, log: Callable = print) -> dict:
    """PE-H's residuals of one season (11.4.3) with its receipts, as
    swar_targets.Readers.pitch_economy_hitters computes them, on this read's corpus."""
    import pitch_economy_lab as pel
    pa_rec, blk = load_record_pa(season)
    d = load_corpus(season, pa_rec)
    tb = tables["seasons"][str(int(season))]
    w = pel.walk_corpus_season(int(season), d, tb["re288"], tb["re24"], {})
    hit = pel.hit_lines(int(season))
    pbat = {p for p, h in hit.items() if h["pos"] == "P"}
    clbar, pbar = pel.class_means(w["rows"])
    res = pel.hitter_residuals(w["rows"], clbar, pbar, pbat)
    corpus_pitches = int(len(d["pitches"]))
    rc = blk.get("receipts") or {}
    i3 = rc.get("I3") or {}
    games_listed = int(blk.get("games_scheduled") or 0)
    games_present = int(blk.get("games_present") or 0)
    n_cancel = len(i3.get("cancelled_no_play") or [])
    return {"resid": {int(b): {k: h[k] for k in ("n", "clres", "m", "pres")} for b, h in res.items()},
            "pa": {int(b): h["pa"] for b, h in hit.items() if h["pos"] != "P"},
            "pbat": sorted(int(p) for p in pbat),
            "receipt": dict(w["receipt"], corpus_pitches=corpus_pitches,
                            games_listed=games_listed, games_present=games_present,
                            games_cancelled=n_cancel,
                            game_coverage=(games_present / max(1, games_listed - n_cancel))),
            "class_means": {"cl": clbar, "p": pbar}}


def season_rows(season: int, tables: Mapping, log: Callable = print) -> tuple[dict, dict]:
    """({hit: {mlbam: row}, pit: {mlbam: row}}, the season's receipt). Hitter rows carry
    pa, wraa, W, d {peh, peh_cl, peh_p}, fwar, rpw, pitcher_batter; pitcher rows fwar, ip."""
    import pitch_economy_lab as pel
    s = int(season)
    wt = season_weights(s)
    wear = season_wear(s)
    hl = pel.hit_lines(s)
    vh, vp = vintage_group(s, "hitting"), vintage_group(s, "pitching")
    peh = season_hitters(s, tables, log)
    dd = T.pe_h_deltas(peh["resid"], peh["pa"], wear["w"], pe.K_CL, pe.K_P)
    rc = peh["receipt"]
    rc["pitch_coverage"] = rc["corpus_pitches"] / wear["line_pitches"] if wear["line_pitches"] else None
    hit = {}
    for m in sorted(set(hl) | set(vh)):
        h = hl.get(m)
        pa = float(h["pa"]) if h else 0.0
        woba = pel.woba_of(h, wt["weights"]) if h else None
        pb = bool(h and h["pos"] == "P")
        res = peh["resid"].get(m) or {}
        fw = (vh.get(m) or {}).get("war")
        hit[m] = {"pa": pa, "wraa": (None if woba is None else (woba - wt["lg_woba"]) / wt["scale"] * pa),
                  "W": float(wear["w"]) * float(res.get("pres") or 0.0),
                  "d": {"peh": 0.0 if pb else float(dd["peh"].get(m, 0.0)),
                        "peh_cl": 0.0 if pb else float(dd["cl"].get(m, 0.0)),
                        "peh_p": 0.0 if pb else float(dd["p"].get(m, 0.0))},
                  "fwar": None if fw is None else float(fw), "rpw": wear["rpw"], "pitcher_batter": pb}
    pl = pel.pit_lines(s)
    pit = {}
    for m in sorted(set(pl) | set(vp)):
        fw = (vp.get(m) or {}).get("war")
        ip = (pl.get(m) or {}).get("ip")
        pit[m] = {"fwar": None if fw is None else float(fw), "ip": ip}
    zero = abs(sum(v["d"]["peh"] for v in hit.values()))
    receipt = {"season": s, "weights_source": wt["source"], "w": wear["w"], "rpw": wear["rpw"],
               "split_pitch_share": wear["split_pitch_share"], "hitters": len(hit), "pitchers": len(pit),
               "re288_identity_share": rc.get("identity_share"), "pitch_coverage": rc["pitch_coverage"],
               "game_coverage": rc["game_coverage"], "pa_walked": rc.get("pa"),
               "no_pitch": rc.get("no_pitch"), "zero_sum_abs": zero,
               "admitted": bool((rc.get("identity_share") or 0) >= MIN_IDENTITY_SHARE
                                and (rc["pitch_coverage"] or 0) >= MIN_PITCH_COVERAGE
                                and rc["game_coverage"] >= MIN_GAME_COVERAGE)}
    return {L.HIT: hit, L.PIT: pit}, receipt


# ==========================================================================
# the club side (team guard and the club-clustered interval)
# ==========================================================================
def standings(seasons: Iterable[int]) -> dict:
    """ewar.standings, with the one club its name map cannot read (the Expos) added."""
    import ewar
    out = ewar.standings(list(seasons))
    for y in seasons:
        p = ewar.CACHE_DIR / f"statsapi_standings_{int(y)}.json"
        if not p.exists():
            continue
        blob = json.loads(p.read_text(encoding="utf-8"))
        for rec in blob.get("records") or []:
            for tr in rec.get("teamRecords") or []:
                name = ((tr.get("team") or {}).get("name") or "").strip()
                for k, tid in EXTRA_CLUB_NAMES.items():
                    if name.endswith(k) and tid not in out.get(int(y), {}):
                        out.setdefault(int(y), {})[tid] = {
                            "w": int(tr.get("wins") or 0), "l": int(tr.get("losses") or 0),
                            "rs": float(tr.get("runsScored")) if tr.get("runsScored") is not None else None,
                            "ra": float(tr.get("runsAllowed")) if tr.get("runsAllowed") is not None else None}
    return out


def normalize_team_exposure(team_exp: Mapping) -> dict:
    out: dict = {}
    for k, blk in team_exp.items():
        nb: dict = {}
        for t, e in blk.items():
            t2 = STANDINGS_KEY.get(str(t), str(t))
            nb[t2] = nb.get(t2, 0.0) + float(e)
        out[k] = nb
    return out


def club_of(team_exp: Mapping, side: str, season: int, mid: int) -> str:
    """The franchise of a player's club with the most exposure in `season`."""
    blk = team_exp.get((side, int(season), int(mid))) or {}
    if not blk:
        return f"none|{int(mid)}"
    t = max(sorted(blk), key=lambda k: blk[k])
    return T.franchise(t)


# ==========================================================================
# scoring (pure, on in-memory structures; the dry run feeds fixtures)
# ==========================================================================
def frame_pairs(rows: Mapping[int, dict], seasons: Iterable[int]) -> list[dict]:
    return L.component_pairs(rows, "peh", seasons, {int(y): {} for y in rows})


def secondary_pairs(rows: Mapping[int, dict], seasons: Iterable[int]) -> list[dict]:
    """11.2.5's secondary estimand on this frame: B0 fWAR(Y), test fWAR(Y) + d_PEH / RPW_Y,
    target fWAR(Y+1); hitters 200 PA in both seasons; m the season's PA-weighted fWAR rate."""
    out = []
    for y in seasons:
        a, b = (rows.get(int(y)) or {}).get(L.HIT) or {}, (rows.get(int(y) + 1) or {}).get(L.HIT) or {}
        num = den = 0.0
        for r in a.values():
            if r.get("pa", 0) >= L.MIN_PA and r.get("fwar") is not None:
                num += r["fwar"]
                den += r["pa"]
        m = num / den if den else None
        for mid in sorted(a):
            r0, r1 = a[mid], b.get(mid)
            if r1 is None or r0.get("pa", 0) < L.MIN_PA or r1.get("pa", 0) < L.MIN_PA:
                continue
            if r0.get("fwar") is None or r1.get("fwar") is None or not r0.get("rpw"):
                continue
            out.append({"mlbam": mid, "y": int(y), "n0": float(r0["pa"]), "n1": float(r1["pa"]),
                        "b0": float(r0["fwar"]), "tgt": float(r1["fwar"]), "b0r": None, "m": m,
                        "tests": {"peh": float(r0["fwar"]) + float(r0["d"]["peh"]) / float(r0["rpw"])}})
    return out


def with_tests(pairs: list[dict], fn: Callable[[dict], float]) -> list[dict]:
    return [dict(p, tests={"peh": float(fn(p))}) for p in pairs]


def planted(pairs: list[dict], share: Optional[float] = None) -> list[dict]:
    """b0 + share x n0 x (tgt / n1 - the outcome season's PA-weighted mean target rate)."""
    share = PLANT_SHARE if share is None else float(share)
    tot: dict = {}
    for p in pairs:
        a = tot.setdefault(p["y"], [0.0, 0.0])
        a[0] += p["tgt"]
        a[1] += p["n1"]
    mean = {y: v[0] / v[1] for y, v in tot.items() if v[1] > 0}
    return with_tests(pairs, lambda p: p["b0"] + share * p["n0"] * (p["tgt"] / p["n1"] - mean[p["y"]]))


def club_interval(rec: dict, clubs: Mapping[tuple, str], boot: int, seed: int) -> dict:
    """The cell's gap over B0 under franchises drawn with replacement (the Y+1 club of
    each pair, all of a franchise's pairs together), on the v2 target."""
    fa = rec.get("_fa")
    if fa is None:
        return {"n_franchises": 0, "lo95": None, "hi95": None, "sd": None}
    labs = [clubs.get((int(y) + 1, int(m)), f"none|{m}") for m, y in zip(fa["players"], fa["strata"])]
    draws = L.cluster_draws(labs, [0] * len(labs), boot, seed)
    d = L._rho_draws_multi({"test": fa["series"]["test"], "b0": fa["series"]["b0"]},
                           fa["target_v2"], fa["lab"], draws)
    g = L.gap_summary(d["test"], d["b0"])
    return {"n_franchises": len(set(labs)), "lo95": g["lo95"], "hi95": g["hi95"], "sd": g["sd"],
            "half_width95": g["half_width95"], "mde95": g["mde95"]}


def score_family(pairs_by_cell: Mapping[str, list], boot: int, seed: int, twin_seed: int,
                 k_b1: float, part: str = PART) -> dict:
    """Both cells of one family through swar_lab's own cell code; Holm k = 2."""
    fam = {}
    for i, (cell, kind) in enumerate(CELLS.items()):
        rec = L.prep_primary(part, cell, [("pe_h", pairs_by_cell[cell], "peh")], kind, k_b1, boot, seed,
                             twin_seed + i)
        fam[cell] = L.finish_primary(rec)
    L.decide_family(fam)
    return fam


def _public(rec: Mapping) -> dict:
    return {k: (_r(v) if isinstance(v, float) else v) for k, v in rec.items() if not k.startswith("_")}


def team_guard(rows: Mapping[int, dict], seasons: Iterable[int], team_exp: Mapping, stand: Mapping,
               bwar: Mapping, boot: int, seed: int) -> dict:
    """11.2.4's guard of PE-H (hitter side; runs scored, run differential, wins) on the
    club-seasons Y+1, through swar_targets.team_guard, B and the seed of this read."""
    ys = [int(y) for y in seasons]
    clubs = sorted({(y + 1, t) for y in ys for t in (stand.get(y + 1) or {})})
    if not clubs:
        raise ReadStop("the team guard has no club-season with standings")
    def num(v):
        return np.nan if v is None else float(v)
    outcomes = {
        "runs_scored": np.array([num(stand[s][t].get("rs")) for s, t in clubs], float),
        "runs_allowed": np.array([-num(stand[s][t].get("ra")) for s, t in clubs], float),
        "run_differential": np.array([num(stand[s][t].get("rs")) - num(stand[s][t].get("ra"))
                                      for s, t in clubs], float),
        "wins": np.array([float(stand[s][t]["w"]) for s, t in clubs], float),
    }
    players = sorted({m for y in ys for side in (L.HIT, L.PIT) for m in ((rows.get(y) or {}).get(side) or {})})
    nxt = {side: {(s, m): e for (sd, s, m), e in team_exp.items() if sd == side} for side in (L.HIT, L.PIT)}

    def mat(side, value_of):
        vals, expo = {}, {}
        for y in ys:
            for m, r in ((rows.get(y) or {}).get(side) or {}).items():
                vals[(y, m)] = value_of(m, y, r)
                expo[(y, m)] = r.get(L.EXPOSURE[side])
        return T.roster_matrix(vals, expo, nxt[side], players, clubs)

    bkey = {L.HIT: "bat", L.PIT: "pit"}
    base = {side: {"frame": mat(side, lambda m, y, r: r.get("fwar")),
                   "ref": mat(side, lambda m, y, r, s=side: (bwar.get((m, y)) or {}).get(bkey[s]))}
            for side in (L.HIT, L.PIT)}

    def part_value(m, y, r):
        fw, d, rpw = r.get("fwar"), (r.get("d") or {}).get("peh"), r.get("rpw")
        if fw is None:
            return None
        return fw if (d is None or not rpw) else fw + d / rpw

    part_m = mat(L.HIT, part_value)
    mats = {L.HIT: {"frame": base[L.HIT]["frame"], "ref": base[L.HIT]["ref"], "part": part_m},
            L.PIT: {"frame": base[L.PIT]["frame"], "ref": base[L.PIT]["ref"], "part": base[L.PIT]["frame"]}}
    g = T.team_guard(mats, outcomes, T.OUTCOMES_HIT, clubs, boot=boot, seed=seed)
    # coverage receipt: the share of the frame's Y+1 PA that lands on a standings club
    tot = hit = 0.0
    cset = set(clubs)
    for (side, s, m), blk in team_exp.items():
        if side != L.HIT or (s - 1) not in ys:
            continue
        for t, e in blk.items():
            tot += e
            hit += e if (s, t) in cset else 0.0
    g["club_seasons"] = len(clubs)
    g["pa_share_on_standings_clubs"] = (hit / tot) if tot else None
    return g


def admission(fam: Mapping, club: Mapping, sens: Mapping, guard: Mapping) -> dict:
    """Gate part 5: the rate cell WIN (components) with the club-clustered lo95 above 0,
    the total cell not LOSS, the sensitivity guard not LOSS, the team guard NON-INFERIOR."""
    rate, tot = fam["PE-H rate"], fam["PE-H total"]
    club_ok = (club.get("PE-H rate") or {}).get("lo95")
    ok = (rate["disposition"] == L.WIN_COMPONENTS and club_ok is not None and club_ok > 0.0
          and tot["disposition"] != L.LOSS and not sens.get("loss", True)
          and bool(guard.get("non_inferior")))
    return {"passes": bool(ok),
            "reason": (f"PE-H rate {rate['disposition']} (club lo95 {_f(club_ok)}), PE-H total "
                       f"{tot['disposition']}, sensitivity not LOSS {not sens.get('loss', True)}, "
                       f"team guard {'NON-INFERIOR' if guard.get('non_inferior') else 'not non-inferior'}"),
            "served": False,
            "next": ("OWNER QUESTION (gate part 6): the read passed; PE-H stays dark until the owner answers"
                     if ok else "not admitted: eWAR carries no pitch-economy term (EBR_GATE.md 11.4.5)")}


def score(rows: Mapping[int, dict], seasons: Iterable[int], team_exp: Mapping, stand: Mapping,
          bwar: Mapping, boot: int = BOOT, log: Callable = print) -> dict:
    """The whole read on in-memory rows, in the registered order: census and floors,
    controls, cells, club intervals, sensitivity, team guard, secondary, admission."""
    seasons = tuple(int(s) for s in seasons)
    out: dict = {"seasons": list(seasons)}
    pairs = frame_pairs(rows, seasons)
    if len(pairs) < 50:
        raise ReadStop(f"the frame holds {len(pairs)} pairs")
    clubs = {(int(p["y"]) + 1, int(p["mlbam"])): club_of(team_exp, L.HIT, int(p["y"]) + 1, int(p["mlbam"]))
             for p in pairs}
    by_season = {}
    for p in pairs:
        by_season[str(p["y"])] = by_season.get(str(p["y"]), 0) + 1
    out["census"] = {"pairs": len(pairs), "players": len({p["mlbam"] for p in pairs}),
                     "pairs_by_predictor_season": by_season,
                     "franchises": len(set(clubs.values()))}
    _p(log, f"[read] FRAME: {len(pairs)} pairs, {out['census']['players']} players, "
            f"{out['census']['franchises']} franchises; by predictor season {by_season}")
    # --- floors first: n and the minimum detectable effect, before any gap
    real = {c: pairs for c in CELLS}
    prepped = {}
    for i, (cell, kind) in enumerate(CELLS.items()):
        prepped[cell] = L.prep_primary(PART, cell, [("pe_h", pairs, "peh")], kind, K_B1_PEH, boot, SEED,
                                       TWIN_SEED + i)
    out["floors"] = {c: dict(r["floors"], n_pairs=r["n_pairs"]) for c, r in prepped.items()}
    _p(log, f"[read] FLOORS (convention v2, B = {boot}, seed {SEED}; MDE95 = 1.645 sd; no gap is printed here)")
    for c, f in out["floors"].items():
        _p(log, f"  {c:11s} n {f['n_pairs']:5d}  sd {_f(f['sd'])}  half-width {_f(f['half_width95'])}  "
                f"MDE95 {_f(f['mde95'])}")
    # --- controls
    ctrl = {}
    for name, ps in (("null", with_tests(pairs, lambda p: p["b0"])), ("planted", planted(pairs))):
        fam = score_family({c: ps for c in CELLS}, boot, SEED, TWIN_SEED, K_B1_PEH)
        ctrl[name] = {c: {"disposition": r["disposition"], "gap": _r(r.get("gap")), "lo95": _r(r.get("lo95")),
                          "twin_lo95": _r(r.get("twin_lo95")), "b1_lo95": _r(r.get("b1_lo95"))}
                      for c, r in fam.items()}
        _p(log, f"[read] CONTROL {name}: " + "; ".join(f"{c} {v['disposition']} gap {_f(v['gap'])} "
                                                        f"twin lo95 {_f(v['twin_lo95'])}"
                                                        for c, v in ctrl[name].items()))
    null_ok = all(v["disposition"] not in (L.WIN_COMPONENTS, L.WIN_REGRESSION, L.SMALL_WIN)
                  for v in ctrl["null"].values())
    plant_ok = all(v["disposition"] == L.WIN_COMPONENTS and v["twin_lo95"] is not None and v["twin_lo95"] <= 0
                   for v in ctrl["planted"].values())
    out["controls"] = dict(ctrl, null_passes=null_ok, planted_passes=plant_ok)
    if not (null_ok and plant_ok):
        out["void"] = True
        out["void_reason"] = f"a control failed (null passes {null_ok}, planted passes {plant_ok})"
        _p(log, f"[read] VOID: {out['void_reason']}; no real cell is scored")
        return out
    # --- the real cells
    fam = {c: L.finish_primary(r) for c, r in prepped.items()}
    L.decide_family(fam)
    club = {c: club_interval(fam[c], clubs, boot, CLUB_SEED) for c in CELLS}
    _p(log, "[read] CELLS (against B0 = wRAA(Y); target wRAA(Y+1) + W(Y+1); Holm k = 2)")
    for c, r in fam.items():
        _p(log, f"  {c:11s} n {r['n_pairs']:5d} gap {_f(r.get('gap'))} [{_f(r.get('lo95'))}, {_f(r.get('hi95'))}] "
                f"90% [{_f(r.get('lo90'))}, {_f(r.get('hi90'))}] p {_f(r.get('p_one_sided'))} holm "
                f"{r.get('holm_reject')} | vs B1 lo95 {_f(r.get('b1_lo95'))} | twin lo95 {_f(r.get('twin_lo95'))} "
                f"| v1 {_f(r.get('v1_gap'))} | club [{_f(club[c]['lo95'])}, {_f(club[c]['hi95'])}] "
                f"({club[c]['n_franchises']} franchises) => {r['disposition']}")
    # --- the sensitivity guard: the rate cell on wRAA(Y+1) alone, the same bootstrap
    sp = [dict(p, tgt=p["tgt_alt"]) for p in pairs if p.get("tgt_alt") is not None]
    srec = L.finish_primary(L.prep_primary(PART, "PE-H rate on wRAA alone", [("pe_h", sp, "peh")], RATE,
                                           K_B1_PEH, boot, SEED, TWIN_SEED + 5))
    sens = {"gap": _r(srec.get("gap")), "lo95": _r(srec.get("lo95")), "hi95": _r(srec.get("hi95")),
            "loss": bool(srec.get("hi95") is not None and srec["hi95"] < 0.0), "n_pairs": srec.get("n_pairs")}
    _p(log, f"[read] SENSITIVITY (rate cell on wRAA(Y+1) alone): gap {_f(sens['gap'])} "
            f"[{_f(sens['lo95'])}, {_f(sens['hi95'])}] LOSS {sens['loss']}")
    # --- the terms one at a time, beside, no weight
    terms = {t: {"rate_gap": _r(L.point_gap_frames([("h", pairs, t)], RATE, K_B1_PEH)),
                 "total_gap": _r(L.point_gap_frames([("h", pairs, t)], CUM, K_B1_PEH))}
             for t in ("peh_cl", "peh_p")}
    _p(log, f"[read] BESIDE (no weight): the terms one at a time {terms}")
    # --- the team guard
    guard = team_guard(rows, seasons, team_exp, stand, bwar, boot, SEED)
    _p(log, f"[read] TEAM GUARD (B = {boot} each, seed {SEED}; {guard['club_seasons']} club-seasons, "
            f"{guard['n_franchises']} franchises; Y+1 PA on a standings club {_f(guard['pa_share_on_standings_clubs'])})")
    for oname, o in guard["outcomes"].items():
        _p(log, f"  {oname:16s} player sd {_f(o['player'].get('sd'))} club sd {_f(o['club'].get('sd'))} | dT "
                f"{_f(o['dT'])} lower player {_f(o['player'].get('lower'))} club {_f(o['club'].get('lower'))} => "
                f"{'NON-INFERIOR' if o['non_inferior'] else 'not non-inferior'}")
    _p(log, f"  guard: {'NON-INFERIOR' if guard['non_inferior'] else 'NOT NON-INFERIOR'}"
            + (" (underpowered: a half-width above 0.02)" if guard.get("underpowered") else ""))
    # --- the secondary estimand (decides nothing)
    sec_pairs = secondary_pairs(rows, seasons)
    sec = score_family({c: sec_pairs for c in CELLS}, boot, SEED, TWIN_SEED + 50, K_B1_SECONDARY)
    _p(log, "[read] SECONDARY (published fWAR(Y+1); decides nothing): "
            + "; ".join(f"{c} {r['disposition']} gap {_f(r.get('gap'))} n {r.get('n_pairs')}" for c, r in sec.items()))
    adm = admission(fam, club, sens, guard)
    _p(log, f"[read] ADMISSION: {'PASS' if adm['passes'] else 'not admitted'} ({adm['reason']}); {adm['next']}")
    out.update({"cells": {c: _public(r) for c, r in fam.items()}, "club_clustered": club,
                "sensitivity": sens, "terms_one_at_a_time": terms,
                "team_guard": guard, "secondary": {c: _public(r) for c, r in sec.items()},
                "admission": adm, "void": False})
    return out


# ==========================================================================
# the record
# ==========================================================================
def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float):
        return round(o, 6) if math.isfinite(o) else None
    return o


def write_record(rec: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_jsonable(rec), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def real_inputs(log: Callable = print) -> dict:
    """Every input of the read, read and checked before scoring begins."""
    if not TABLES_PATH.exists():
        raise ReadStop(f"the season tables are absent: run --build-inputs ({TABLES_PATH})")
    tables = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
    if not (tables.get("receipt") or {}).get("pass"):
        raise ReadStop("the season-table receipt did not pass")
    wr = weights_receipt()
    _p(log, f"[inputs] solved-weights receipt (vintage solve against data/league_constants.json, 2011 to 2015): "
            f"pass {wr['pass']}")
    if not wr["pass"]:
        raise ReadStop(f"the vintage weight solve does not reproduce the artifact: {wr}")
    rows, receipts = {}, {}
    for s in SEASONS:
        if str(s) not in tables["seasons"]:
            raise ReadStop(f"no season table for {s}")
        rows[s], receipts[str(s)] = season_rows(s, tables, log)
        rc = receipts[str(s)]
        _p(log, f"[inputs] {s}: hitters {rc['hitters']}, identity {rc['re288_identity_share']}, pitch coverage "
                f"{_f(rc['pitch_coverage'])}, game coverage {_f(rc['game_coverage'])}, w {_f(rc['w'], 6)}, "
                f"zero-sum {rc['zero_sum_abs']:.2e}, admitted {rc['admitted']}")
        if rc["zero_sum_abs"] > 1e-6:
            raise ReadStop(f"{s}: d_PEH does not sum to zero ({rc['zero_sum_abs']})")
    keep = [s for s in SEASONS if receipts[str(s)]["admitted"]]
    preds = [y for y in PREDICTOR_SEASONS if y in keep and (y + 1) in keep]
    if len(preds) < MIN_PREDICTOR_SEASONS:
        raise ReadStop(f"only {len(preds)} predictor seasons survive the season rules: {preds}")
    texp = normalize_team_exposure(T.Readers().team_exposure())
    stand = standings([y + 1 for y in preds])
    miss = {y + 1: 30 - len(stand.get(y + 1) or {}) for y in preds if len(stand.get(y + 1) or {}) != 30}
    if miss:
        raise ReadStop(f"standings short of 30 clubs: {miss}")
    import war_source
    meta = {"vintage_id": _vintage().get("vintage_id"), "vintage_sha256": _sha(VINTAGE),
            "league_constants_sha256": _sha(LEAGUE_CONSTANTS), "season_tables_sha256": _sha(TABLES_PATH),
            "count_value_sha256": _sha(COUNT_VALUE),
            "bwar_cache_sha256": {s: T.sha256_of(war_source._cache_path(s)) for s in ("bat", "pit")},
            "frozen_constants": {"DELTA_TTO": pe.DELTA_TTO, "K_CL": pe.K_CL, "K_P": pe.K_P,
                                 "B1_k_peh": K_B1_PEH, "B1_k_secondary": K_B1_SECONDARY}}
    return {"rows": rows, "receipts": receipts, "predictors": preds, "team_exp": texp, "standings": stand,
            "bwar": L.LabInputs().bwar(), "weights_receipt": wr, "tables_receipt": tables["receipt"], "meta": meta}


def run_read(out_path: Path = RECORD_PATH, boot: int = BOOT, log: Callable = print,
             inputs: Optional[dict] = None, allow_rerun: bool = False) -> dict:
    if Path(out_path).exists() and not allow_rerun:
        raise ReadStop(f"the read ran already ({out_path}); it runs once")
    started = _now()
    inp = inputs if inputs is not None else real_inputs(log)
    rec = {"lab": LAB_VERSION, "gate": GATE_DOC, "started_at": started, "boot": boot, "seed": SEED,
           "predictor_seasons": inp["predictors"], "season_receipts": inp["receipts"],
           "weights_receipt": inp["weights_receipt"], "tables_receipt": inp["tables_receipt"],
           "input_meta": inp["meta"],
           "cited_not_rescored": {
               "look_2026_10_19": {"frame": "predictor seasons 2021 to 2024", "pairs": 1071,
                                   "rate": "SMALL WIN, gap +0.01304 (+0.00604 to +0.02029)",
                                   "total": "SMALL WIN, gap +0.01341 (+0.00659 to +0.02069)",
                                   "guard": "NON-INFERIOR", "admitted": False},
               "holdout_2026_10_21": {"frame": "predictor season 2025", "pairs": 263,
                                      "rate": "EQUIVALENT, gap +0.00216 (-0.01311 to +0.01624)",
                                      "total": "EQUIVALENT, gap -0.00226 (-0.01899 to +0.01375)",
                                      "guard": "NON-INFERIOR", "admitted": False}}}
    try:
        res = score(inp["rows"], inp["predictors"], inp["team_exp"], inp["standings"], inp["bwar"], boot, log)
    except ReadStop:
        raise
    except Exception:  # noqa: BLE001 - the crash protocol: VOID, no rerun
        rec.update({"void": True, "void_reason": "exception after scoring began",
                    "traceback": traceback.format_exc(), "finished_at": _now()})
        write_record(rec, out_path)
        raise
    rec.update(res)
    rec["finished_at"] = _now()
    write_record(rec, out_path)
    _p(log, f"[read] record written: {out_path}")
    return rec


# ==========================================================================
# the dry run: fixtures with nulls, a temp dir only
# ==========================================================================
def fixture_inputs(seed: int = 7, n_hit: int = 300, n_pit: int = 120, plant: float = 0.0) -> dict:
    """Synthetic rows for 2002 to 2015 with nulls: a hitter's true batting rate drives
    wRAA in every season; the delta carries `plant` of the true rate's departure from
    the season's wRAA, plus noise."""
    rng = np.random.default_rng(seed)
    th = rng.normal(0.0, 0.03, n_hit)
    rows, texp = {}, {}
    teams = sorted(set(STANDINGS_KEY.values()) | {"BOS", "NYY", "CHC", "STL", "SEA", "OAK"})
    for y in SEASONS:
        hit, pit = {}, {}
        for i in range(n_hit):
            mid = 1000 + i
            pa = float(rng.integers(120, 700))
            wraa = float(th[i] * pa + rng.normal(0, 6.0))
            d = plant * (th[i] * pa - wraa) + float(rng.normal(0, 0.5))
            hit[mid] = {"pa": pa, "wraa": (None if (i == 5 and y == 2006) else wraa),
                        "W": float(rng.normal(0, 0.4)), "d": {"peh": d, "peh_cl": d / 2, "peh_p": d / 2},
                        "fwar": (None if (i == 9 and y == 2008) else wraa / 9.8 + float(rng.normal(0, 0.3))),
                        "rpw": 9.8, "pitcher_batter": i == 7}
            texp[(L.HIT, y, mid)] = {teams[i % len(teams)]: pa}
        for j in range(n_pit):
            mid = 5000 + j
            ip = float(rng.integers(20, 200))
            pit[mid] = {"fwar": float(rng.normal(1.0, 1.0)), "ip": (None if j == 3 else ip)}
            texp[(L.PIT, y, mid)] = {teams[j % len(teams)]: ip}
        # zero-sum per season, as the real delta is
        tot_d = sum(r["d"]["peh"] for r in hit.values())
        tot_pa = sum(r["pa"] for r in hit.values())
        for r in hit.values():
            r["d"]["peh"] -= r["pa"] * tot_d / tot_pa
        rows[y] = {L.HIT: hit, L.PIT: pit}
    stand = {y: {t: {"w": int(rng.integers(60, 100)), "l": 70, "rs": float(rng.integers(600, 850)),
                     "ra": float(rng.integers(600, 850))} for t in teams} for y in SEASONS}
    return {"rows": rows, "predictors": list(PREDICTOR_SEASONS), "team_exp": texp, "standings": stand,
            "bwar": {}, "receipts": {}, "weights_receipt": {"fixture": True}, "tables_receipt": {"fixture": True},
            "meta": {"fixture": True}}


def dry_run(log: Callable = print, boot: int = 200, tmp_dir: Optional[Path] = None) -> dict:
    """The whole reporting path on fixtures with nulls, twice: a null delta (the read's
    real cells must not read WIN) and a planted one (they must), the controls inside
    each run as the read runs them. Writes only under a temporary directory."""
    tmp = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="peh_old_dry_"))
    out = {}
    for name, plant in (("null_delta", 0.0), ("planted_delta", 0.8)):
        rec = run_read(tmp / f"{name}.json", boot=boot, log=log, inputs=fixture_inputs(plant=plant))
        out[name] = {"void": rec.get("void"), "controls_null": rec["controls"]["null_passes"],
                     "controls_planted": rec["controls"]["planted_passes"],
                     "rate": (rec.get("cells") or {}).get("PE-H rate", {}).get("disposition"),
                     "total": (rec.get("cells") or {}).get("PE-H total", {}).get("disposition"),
                     "admission": (rec.get("admission") or {}).get("passes")}
        log(f"[dry run] {name}: {out[name]}")
    return out


def preflight(seasons: Iterable[int], log: Callable = print) -> dict:
    """The input path on real seasons, receipts only: the weights and table receipts and
    each season's identity share, coverage, w_s and zero-sum check. No pair is formed and
    no per-player value or statistic is printed."""
    tables = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
    out = {"weights_receipt": weights_receipt(), "tables_receipt": tables.get("receipt"), "seasons": {}}
    log(f"[preflight] weights receipt pass {out['weights_receipt']['pass']}; tables receipt pass "
        f"{(out['tables_receipt'] or {}).get('pass')}")
    for s in seasons:
        _rows, rc = season_rows(int(s), tables, log)
        out["seasons"][str(s)] = rc
        log(f"[preflight] {s}: hitters {rc['hitters']}, pitchers {rc['pitchers']}, identity "
            f"{rc['re288_identity_share']}, pitch coverage {_f(rc['pitch_coverage'])}, game coverage "
            f"{_f(rc['game_coverage'])}, split pitch share {_f(rc['split_pitch_share'])}, zero-sum "
            f"{rc['zero_sum_abs']:.2e}, admitted {rc['admitted']}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build-inputs", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--read", action="store_true")
    g.add_argument("--preflight", default=None, help="a comma list of seasons: receipts only")
    ap.add_argument("--seasons", default=None, help="--build-inputs only: a comma list (default 2002-2015)")
    ap.add_argument("--skip", default="", help="--build-inputs only: corpus,runners,tables to skip")
    ap.add_argument("--out", default=str(RECORD_PATH))
    a = ap.parse_args(argv)
    if a.dry_run:
        dry_run()
        return 0
    if a.preflight:
        preflight([int(x) for x in a.preflight.split(",")])
        return 0
    if a.build_inputs:
        seasons = [int(x) for x in a.seasons.split(",")] if a.seasons else list(SEASONS)
        skip = set(x for x in a.skip.split(",") if x)
        if "runners" not in skip:
            build_runners(seasons)
        if "corpus" not in skip:
            build_corpus(seasons)
        if "tables" not in skip:
            # the tables file is rebuilt whole, over every season whose record exists
            have = [s for s in SEASONS if (record_of(s) / "manifest.json").exists()
                    and str(s) in (json.loads((record_of(s) / "manifest.json").read_text(encoding="utf-8"))
                                   .get("seasons") or {})]
            build_tables(have)
        return 0
    try:
        run_read(Path(a.out))
    except ReadStop as exc:
        print(f"STOP: {exc}")
        return 2
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
