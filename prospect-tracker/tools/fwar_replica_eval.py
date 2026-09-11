# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The W1.1 acceptance table: the FanGraphs WAR frame rebuilt from inputs and
scored COMPONENT BY COMPONENT against the published feed, every season 2011-2026.

GATE (plan docs/master-plan-2026-09-09-fangraphs-ewar-betting.md, W1.1): a
component clears a season when at least 99 percent of its rows sit within 1.0 run
of the published value. The acceptance table is the component table, never the
WAR total, and it publishes the row counts behind every share.

WHAT IS BUILT AND WHAT IS CONSUMED. Built from counting stats, innings and the
solved league constants (league_constants.py): wOBA, wRAA, the batting league
term, wSB, the positional adjustment (FanGraphs' ladder on innings by position,
DH innings from B-Ref `Inn` minus fielded innings, the pitcher-batting credit),
the league adjustment, replacement, RPW, FIP, the pitcher runs leg, dynamic RPW,
role replacement, the leverage multiplier and the 430 pin. CONSUMED from the
published feed, each labelled in the artifact: UBR + wGDP (need play-by-play), the
fielding column and the catcher framing residual (UZR/Statcast/framing are not on
disk), gmLI (needs play-by-play win expectancy), and the batting park factor,
BACK-SOLVED leave-one-out from the published Batting so no player's own value
enters the factor applied to him.

THE FANGRAPHS INPUTS (owner decisions 13 and 14a, 2026-09-11), all through
fg_leaderboards.py's cache and none back-solved from a published WAR, so none is
circular. The pitcher runs leg is ifFIP on FanGraphs' IFFB; the pitcher park
factor is FanGraphs' own FIP park factor per team-season (the Guts table); each
pitcher is charged the catcher framing earned on his pitches (the pitching
leaderboard's CFraming, fwar_frame convention 9, the residual no park factor
could close); and the start/relief split is FanGraphs' Start-IP. Where a season
is not cached the line falls back, input by input, to plain FIP, the leave-one-out
FIP- back-solve and B-Ref's role innings, and the artifact names what each season
had (`arm`, `runs_leg`, `pf_source`, `framing_charge`, `role_innings`). Every arm
one input apart is scored beside the default (`pitchers_arms`), so what each input
buys is its own line. Catcher framing is cross-checked against FanGraphs CFraming
in the hitter block (`framing_crosscheck`), and FanGraphs' own published pitcher
WAR against the feed's (`pitchers_published_crosscheck`).

THE PARK FACTOR IS SCORED BOTH WAYS. With IFFB, the framing charge and Start-IP
in place, the leave-one-out FIP- back-solve clears more seasons than FanGraphs'
Guts FIP factor (the Guts column as served today sits a fraction of a point
from the factor inside the published FIP-). The default line stays on the Guts
factor, the INPUT decision 14a asked for, and `pitcher_arms_summary` lists the
passing seasons of every arm so the comparison is read off the artifact rather
than a write-up.

NOTHING OF FANGRAPHS' IS REPUBLISHED. This file ships with the site's eval
artifacts, so it carries what the replica made of FanGraphs' numbers (shares,
MAE, row counts, the gap between two park-factor sources) and the sha256 of
every cached response, never FanGraphs' tables or per-player values.

WHAT IT READS (never the network): the StatsAPI caches under .cache
(statsapi_saber_{hitting,pitching}_{y}.json, fa_statsapi_{hitting,pitching}_{y}.json,
statsapi_field/fld_{y}.json, statsapi_standings_{y}.json), B-Ref's war_daily
parquets for stint PA, `Inn` and role innings, data/league_constants.json and the
FanGraphs cache .cache/fangraphs/ (fg_leaderboards.load, which never fetches;
fill it with `python fg_leaderboards.py --seasons 2011 2026`).
saber_feed.load_components is deliberately NOT called: it goes through the
scraper's TTL cache and would refetch an expired season.

Usage:
    python tools/fwar_replica_eval.py                 # print the table
    python tools/fwar_replica_eval.py --write         # write data/fwar_replica_eval.json
    python tools/fwar_replica_eval.py --out PATH      # write the artifact to PATH
    python tools/fwar_replica_eval.py --seasons 2011 2025
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
#: The tree holding .cache and data. The same as ROOT in the repo; overridable so
#: the tool can run from a scratch copy against the real caches without writing.
REPO = Path(os.environ.get("FWAR_REPO_ROOT") or ROOT)
for p in (str(REPO), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import fg_leaderboards as FG    # noqa: E402
import fwar_frame as F          # noqa: E402
import league_constants as LCM  # noqa: E402
from saber_feed import framing_residual, resolve_groups, run_value  # noqa: E402

CACHE = REPO / ".cache"
OUT_PATH = REPO / "data" / "fwar_replica_eval.json"
FG_CACHE = Path(os.environ.get("FG_CACHE_DIR") or (CACHE / "fangraphs"))

FIRST, LAST = 2011, 2026
LG_ID = {"AL": 103, "NL": 104}
#: Rows below these exposures never enter a park-factor back-solve pool: a thin
#: row carries proportionally more rounding in the published value.
PF_POOL_MIN_PA = 30
PF_POOL_MIN_IP = 20.0

HITTER_COMPONENTS = ("wraa", "batting", "wsb", "bsr", "positional", "league",
                     "replacement", "rar", "war_runs")
PITCHER_COMPONENTS = ("fip_runs", "rar", "war_runs")


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------

def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _splits(path: Path) -> list:
    blob = _json(path)
    if isinstance(blob, dict):
        return (blob.get("stats") or [{}])[0].get("splits") or []
    return blob or []


def _ip(s) -> float:
    s = str(s or "0")
    whole, _, frac = s.partition(".")
    return int(whole or 0) + int(frac or 0) / 3.0


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _mtime(path: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def counts(kind: str, season: int) -> dict:
    """{mlbam: split} from the per-player season cache (one row per player)."""
    out = {}
    for r in _splits(CACHE / f"fa_statsapi_{kind}_{season}.json"):
        pid = (r.get("player") or {}).get("id")
        if pid is not None:
            out[int(pid)] = r
    return out


def saber(kind: str, season: int) -> tuple[dict, list]:
    rows, ambiguous, _ = resolve_groups(_splits(CACHE / f"statsapi_saber_{kind}_{season}.json"))
    return rows, ambiguous


def fielding_path(season: int) -> Path:
    """The FRESHER of the two caches of the same StatsAPI season-fielding feed:
    fielding_innings' permanent copy, or the 24-hour copy the Defense board warms.
    A stale in-season innings file is what failed 2026's positional component."""
    a = CACHE / "statsapi_field" / f"fld_{season}.json"
    b = CACHE / f"statsapi_fielding_season_{season}.json"
    cands = [x for x in (a, b) if x.exists()]
    if not cands:
        return a
    return max(cands, key=lambda x: x.stat().st_mtime)


def fielding(season: int) -> dict:
    """{mlbam: {POS: innings}} season totals (StatsAPI publishes DH innings as 0)."""
    out: dict = collections.defaultdict(dict)
    for s in _splits(fielding_path(season)):
        pid = (s.get("player") or {}).get("id")
        pos = (s.get("position") or {}).get("abbreviation")
        if pid is None or not pos:
            continue
        out[int(pid)][pos] = out[int(pid)].get(pos, 0.0) + _ip((s.get("stat") or {}).get("innings"))
    return out


def standings(season: int) -> tuple[float, dict]:
    """(MLB games, {team_id: 2020 region}) from the cached standings."""
    blob = _json(CACHE / f"statsapi_standings_{season}.json") or {}
    gp = 0.0
    region = {}
    for rec in blob.get("records") or []:
        div = ((rec.get("division") or {}).get("id"))
        for t in rec.get("teamRecords") or []:
            gp += _num(t.get("gamesPlayed"))
            region[int(t["team"]["id"])] = F.REGION_OF_DIVISION.get(div)
    return gp / 2.0, region


_WD: dict = {}


def war_daily(side: str):
    if side not in _WD:
        import pandas as pd
        cols = {"bat": ["mlb_ID", "year_ID", "team_ID", "stint_ID", "lg_ID", "PA", "Inn"],
                "pit": ["mlb_ID", "year_ID", "team_ID", "stint_ID", "lg_ID", "G", "GS",
                        "IPouts", "IPouts_start", "IPouts_relief"]}[side]
        df = pd.read_parquet(CACHE / "war_daily" / f"{side}.parquet", columns=cols)
        df = df[(df.year_ID >= FIRST) & (df.year_ID <= LAST)].dropna(subset=["mlb_ID"])
        _WD[side] = df
    return _WD[side]


def stints_by_player(side: str, season: int) -> dict:
    """{mlbam: [dict(team, lg, pa|ip, ...)]} per B-Ref stint."""
    df = war_daily(side)
    out: dict = collections.defaultdict(list)
    for r in df[df.year_ID == season].itertuples(index=False):
        d = {"team": r.team_ID, "lg": r.lg_ID}
        if side == "bat":
            d.update(pa=_num(r.PA), inn=_num(r.Inn))
        else:
            d.update(g=_num(r.G), gs=_num(r.GS), outs=_num(r.IPouts),
                     outs_start=_num(r.IPouts_start), outs_relief=_num(r.IPouts_relief))
        out[int(r.mlb_ID)].append(d)
    return out


def team_map(stints: dict, rows: dict) -> dict:
    """B-Ref team code -> StatsAPI team id, by majority over single-stint,
    single-team players."""
    votes: dict = collections.defaultdict(collections.Counter)
    for pid, ss in stints.items():
        if len(ss) != 1:
            continue
        r = rows.get(pid)
        if not r or int(r.get("numTeams") or 1) != 1:
            continue
        tid = (r.get("team") or {}).get("id")
        if tid is not None:
            votes[ss[0]["team"]][int(tid)] += 1
    return {code: c.most_common(1)[0][0] for code, c in votes.items()}


def constants(season: int) -> Optional[dict]:
    blk = LCM.load().get(season)
    if blk and "woba_weights" in blk and "rpw" in blk:
        return blk
    return LCM.solve_season(season)


def fg_inputs(season: int) -> dict:
    """The FanGraphs inputs for one season from the cache (never the network):
    {"iffb": {mlbam: IFFB}, "fip_pf": {team_id: decimal}, "start_ip": {mlbam: IP},
    "pitcher_framing": {mlbam: CFraming earned on his pitches},
    "framing": {mlbam: catcher CFraming runs}, "published": {mlbam: leaderboard row},
    "provenance": {kind: {fetched_at, complete, raw_sha256} | None}}. A kind that is
    not cached is absent from the dict and None in provenance."""
    out: dict = {"provenance": {}}
    for kind in FG.KINDS:
        try:
            doc = FG.load(kind, season, FG_CACHE)
        except (FG.NotCached, FG.ShapeChanged):
            out["provenance"][kind] = None
            continue
        out["provenance"][kind] = {"fetched_at": doc["fetched_at"], "complete": doc["complete"],
                                   "n_rows": doc["n_rows"], "raw_sha256": doc["raw_sha256"]}
    if out["provenance"].get("pitching"):
        rows = FG.pitcher_rows(season, FG_CACHE)
        out["published"] = rows
        out["iffb"] = {pid: _num(r.get("IFFB")) for pid, r in rows.items()}
        out["start_ip"] = {pid: FG.fg_ip(r.get("Start-IP")) for pid, r in rows.items()
                           if r.get("Start-IP") is not None}
        out["pitcher_framing"] = FG.pitcher_framing(season, FG_CACHE)
    if out["provenance"].get("park_factors"):
        out["fip_pf"] = FG.fip_park_factors(season, FG_CACHE)
    if out["provenance"].get("fielding"):
        out["framing"] = FG.catcher_framing(season, FG_CACHE)
    return out


def _lg_key(season: int, lg: str, team_id, region: dict, fallback: int):
    """The league a stint is priced in: AL/NL, or 2020's regional group."""
    if season == 2020:
        return region.get(team_id) or LG_ID.get(lg, fallback)
    return LG_ID.get(lg, fallback)


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


# --------------------------------------------------------------------------
# Position players
# --------------------------------------------------------------------------

def framing_crosscheck(recs: dict, framing_fg: Optional[dict]) -> Optional[dict]:
    """The feed's framing residual against FanGraphs CFraming, catcher by catcher.

    The residual (rar minus the six published parts) is what the replica and
    DEM+ read; CFraming is FanGraphs' own column (owner decision 13). They are
    two reads of one number, so the check is exact agreement, not correlation:
    rows within 0.01 runs, the largest gap, and who is in one source only."""
    if framing_fg is None:
        return None
    feed = {pid: r["frm_raw"] for pid, r in recs.items()
            if r["pa"] > 0 and r["fld_pos"].get("C", 0.0) > 0 and r["frm_raw"] is not None}
    both = sorted(set(feed) & set(framing_fg))
    diffs = [abs(feed[p] - framing_fg[p]) for p in both]
    only_feed = [p for p in feed if p not in framing_fg]
    only_fg = [p for p in framing_fg if p not in feed]
    worst = sorted(both, key=lambda p: -abs(feed[p] - framing_fg[p]))[:5]
    return {
        "n_catchers_feed": len(feed), "n_catchers_fg": len(framing_fg), "n_both": len(both),
        "n_within_0_01": sum(1 for d in diffs if d <= 0.01),
        "n_within_0_1": sum(1 for d in diffs if d <= 0.1),
        "max_abs_diff": round(max(diffs), 4) if diffs else None,
        "mae": round(sum(diffs) / len(diffs), 5) if diffs else None,
        "only_in_feed": {"n": len(only_feed),
                         "max_abs_residual": round(max((abs(feed[p]) for p in only_feed), default=0.0), 3)},
        "only_in_fg": {"n": len(only_fg),
                       "max_abs_cframing": round(max((abs(framing_fg[p]) for p in only_fg), default=0.0), 3)},
        # the gap only: FanGraphs' own column is not republished here
        "worst": [{"mlbam": p, "name": recs[p]["name"], "feed_residual": round(feed[p], 3),
                   "abs_diff": round(abs(feed[p] - framing_fg[p]), 3)} for p in worst],
    }


def hitters(season: int, pf_override: Optional[dict] = None,
            framing_fg: Optional[dict] = None) -> dict:
    """Price every position-player season. `pf_override` ({team_id: PF decimal})
    replaces the same-season leave-one-out park factor; the driver passes the
    PRIOR season's factors to size what a non-circular park input costs.
    `framing_fg` ({mlbam: CFraming}) adds the framing cross-check; it never
    replaces the residual the replica prices."""
    K = constants(season)
    if not K:
        return {"error": "league constants unsolvable"}
    W = K["woba_weights"]
    scale, lgw, lgrpa, rpw = K["woba_scale"], K["lg_woba"], K["lg_r_pa"], K["rpw"]
    rows, ambiguous = saber("hitting", season)
    cnt = counts("hitting", season)
    fld = fielding(season)
    games, region = standings(season)
    lg_pa = float(K["lg_pa"])
    rep_rate = F.replacement_per_pa(games, rpw, lg_pa)
    stints_all = stints_by_player("bat", season)
    tmap = team_map(stints_all, rows)

    recs = {}
    n_pa0 = 0
    for pid, r in rows.items():
        c = cnt.get(pid)
        st = r.get("stat") or {}
        if c is None:
            continue
        cs = c.get("stat") or {}
        pa = _num(cs.get("plateAppearances"))
        team_id = (r.get("team") or {}).get("id")
        lg_row = (r.get("league") or {}).get("id")

        def g(k, cs=cs):
            return _num(cs.get(k))
        num, den = F.woba_parts(g("baseOnBalls"), g("intentionalWalks"), g("hitByPitch"),
                                g("hits"), g("doubles"), g("triples"), g("homeRuns"),
                                g("atBats"), g("sacFlies"), W)
        wo = F.woba(num, den)
        # stints: PA split by B-Ref stint shares, rescaled to the StatsAPI season PA
        ss = stints_all.get(pid) or []
        tot = sum(s["pa"] for s in ss)
        if tot > 0:
            stints = [(tmap.get(s["team"], team_id if len(ss) == 1 else None), s["lg"], pa * s["pa"] / tot)
                      for s in ss if s["pa"] > 0]
        else:
            stints = [(team_id, {103: "AL", 104: "NL"}.get(lg_row), pa)]
        stints = [(t, _lg_key(season, lg, t, region, lg_row), p) for t, lg, p in stints]
        fp = fld.get(pid, {})
        fielded = sum(fp.values())
        bref_inn = sum(s["inn"] for s in ss)
        recs[pid] = {
            "pid": pid, "name": (r.get("player") or {}).get("fullName", ""),
            "code": (r.get("position") or {}).get("code"), "team": team_id, "lg_row": lg_row,
            "multi": int(r.get("numTeams") or 1) > 1 or len(stints) > 1,
            "pa": pa, "woba": wo, "wraa": F.wraa(wo, lgw, scale, pa) if wo is not None else 0.0,
            "stints": stints, "fld_pos": fp, "dh_inn": F.dh_innings(bref_inn, fielded) if ss else 0.0,
            "sb": g("stolenBases"), "cs": g("caughtStealing"),
            "singles": g("hits") - g("doubles") - g("triples") - g("homeRuns"),
            "bb": g("baseOnBalls"), "hbp": g("hitByPitch"), "ibb": g("intentionalWalks"),
            "feed": {k: run_value(st.get(k)) for k in ("woba", "wRaa", "batting", "wSb", "baseRunning",
                                                         "fielding", "positional", "wLeague",
                                                         "replacement", "rar", "war", "ubr", "wGdp")},
            "frm_raw": framing_residual(st),
        }
        if pa <= 0:
            n_pa0 += 1
    for rec in recs.values():
        rec["is_pitcher"] = rec["code"] == "1" and set(rec["fld_pos"]) <= {"P"}

    # league non-pitcher wRC/PA per league key (stint-apportioned)
    wrc_l: dict = collections.defaultdict(float)
    pa_l: dict = collections.defaultdict(float)
    for rec in recs.values():
        if rec["is_pitcher"] or rec["pa"] <= 0 or rec["woba"] is None:
            continue
        w = F.wrc(rec["woba"], lgw, scale, lgrpa, rec["pa"])
        for t, L, p in rec["stints"]:
            wrc_l[L] += w * p / rec["pa"]
            pa_l[L] += p
    nonp = {L: wrc_l[L] / pa_l[L] for L in pa_l if pa_l[L] > 0}

    def lg_term(rec):
        return sum(F.league_batting_runs(p, lgrpa, nonp.get(L, lgrpa)) for t, L, p in rec["stints"])

    # batting park factor: leave-one-out back-solve from the published Batting
    pool = collections.defaultdict(list)
    for rec in recs.values():
        fb = rec["feed"]["batting"]
        if rec["multi"] or rec["pa"] < PF_POOL_MIN_PA or fb is None or rec["woba"] is None:
            continue
        pf = F.implied_pf(fb, rec["wraa"], lg_term(rec), lgrpa, rec["pa"])
        if pf is not None:
            pool[rec["team"]].append((rec["pid"], pf, rec["pa"]))
    team_pf = {t: sum(pf * w for _, pf, w in v) / sum(w for _, _, w in v) for t, v in pool.items()}

    def pf_for(team, exclude=None):
        v = [(pf, w) for pid, pf, w in pool.get(team, []) if pid != exclude]
        if not v:
            return None
        return sum(pf * w for pf, w in v) / sum(w for _, w in v)

    pf_sd = []
    for t, v in pool.items():
        big = [(pf, w) for _, pf, w in v if w >= 100]
        if len(big) >= 3:
            m = sum(pf * w for pf, w in big) / sum(w for _, w in big)
            pf_sd.append((sum(w * (pf - m) ** 2 for pf, w in big) / sum(w for _, w in big)) ** 0.5)
    n_pf_fallback = 0
    for rec in recs.values():
        stp = []
        for t, L, p in rec["stints"]:
            if pf_override is not None:
                pf = pf_override.get(t)
            else:
                pf = pf_for(t, exclude=rec["pid"]) if not rec["multi"] else team_pf.get(t)
            if pf is None:
                pf = 1.0
                n_pf_fallback += p > 0
            stp.append((p, pf, nonp.get(L, lgrpa)))
        rec["batting"] = F.batting_runs(rec["wraa"], stp, lgrpa)
        rec["wsb"] = F.wsb(rec["sb"], rec["cs"], rec["singles"], rec["bb"], rec["hbp"], rec["ibb"],
                           K["run_cs"], K["lg_wsb"], K["run_sb"])
        f = rec["feed"]
        rec["ubr_wgdp"] = (f["baseRunning"] - f["wSb"]) if (f["baseRunning"] is not None and f["wSb"] is not None) else 0.0
        rec["bsr"] = F.baserunning(rec["wsb"], rec["ubr_wgdp"])
        rec["fielding"] = f["fielding"] or 0.0
        caught = rec["fld_pos"].get("C", 0.0) > 0
        rec["framing"] = (rec["frm_raw"] or 0.0) if caught else 0.0
        rec["frm_noncatcher"] = None if caught else rec["frm_raw"]
        rec["replacement"] = rep_rate * rec["pa"]

    # pitcher-batting positional credit
    ppa = sum(r["pa"] for r in recs.values() if r["is_pitcher"] and r["pa"] > 0)
    pwr = sum(r["wraa"] for r in recs.values() if r["is_pitcher"] and r["pa"] > 0)
    c_rate = F.pitcher_batting_rate(pwr, ppa, rep_rate) or 0.0
    for rec in recs.values():
        rec["positional"] = (c_rate * rec["pa"] if rec["is_pitcher"]
                             else F.positional(rec["fld_pos"], rec["dh_inn"]))

    # league adjustment, one rate per league key
    lsum: dict = collections.defaultdict(float)
    lpa: dict = collections.defaultdict(float)
    for rec in recs.values():
        runs = rec["batting"] + rec["bsr"] + rec["fielding"] + rec["framing"] + rec["positional"]
        if rec["pa"] > 0:
            for t, L, p in rec["stints"]:
                lsum[L] += runs * p / rec["pa"]
                lpa[L] += p
        else:
            lsum[_lg_key(season, {103: "AL", 104: "NL"}.get(rec["lg_row"]), rec["team"], region, rec["lg_row"])] += runs
    lrate = {L: F.league_adjustment_rate(lsum[L], lpa[L]) for L in lpa}
    # isolation diagnostic: the same rate with the FEED positional in the league
    # sum, so a positional failure (stale innings) is not double-counted as a
    # league-adjustment defect
    lsum_fp: dict = collections.defaultdict(float)
    for rec in recs.values():
        runs = (rec["batting"] + rec["bsr"] + rec["fielding"] + rec["framing"]
                + (rec["feed"]["positional"] or 0.0))
        if rec["pa"] > 0:
            for t, L, p in rec["stints"]:
                lsum_fp[L] += runs * p / rec["pa"]
    lrate_fp = {L: F.league_adjustment_rate(lsum_fp[L], lpa[L]) for L in lpa}
    for rec in recs.values():
        rec["league"] = F.league_adjustment((p, lrate.get(L, 0.0)) for t, L, p in rec["stints"])
        rec["rar"] = F.hitter_rar(rec["batting"], rec["bsr"], rec["fielding"], rec["framing"],
                                  rec["positional"], rec["league"], rec["replacement"])
        rec["war"] = F.hitter_war(rec["rar"], rpw)

    league_fp_diffs = [F.league_adjustment((p, lrate_fp.get(L, 0.0)) for t, L, p in r["stints"])
                       - r["feed"]["wLeague"] for r in recs.values()
                       if r["pa"] > 0 and r["feed"]["wLeague"] is not None]
    # score
    pairs = {"wraa": "wRaa", "batting": "batting", "wsb": "wSb", "bsr": "baseRunning",
             "positional": "positional", "league": "wLeague", "replacement": "replacement",
             "rar": "rar"}
    scored = [r for r in recs.values() if r["pa"] > 0]
    drift = [r for r in scored if r["woba"] is not None and r["feed"]["woba"] is not None
             and abs(r["woba"] - r["feed"]["woba"]) > 0.002]
    drift_ids = {r["pid"] for r in drift}

    def table(sub):
        out = {}
        for comp, fk in pairs.items():
            out[comp] = F.gate_row([r[comp] - r["feed"][fk] for r in sub if r["feed"][fk] is not None])
        out["war_runs"] = F.gate_row([(r["war"] - r["feed"]["war"]) * rpw for r in sub if r["feed"]["war"] is not None])
        return out

    obs_rate = collections.defaultdict(list)
    for r in scored:
        if not r["multi"] and r["pa"] >= 50 and r["feed"]["wLeague"] is not None:
            obs_rate[r["stints"][0][1]].append(r["feed"]["wLeague"] / r["pa"])
    feed_c = _median([r["feed"]["positional"] / r["pa"] for r in scored
                      if r["is_pitcher"] and r["feed"]["positional"]])
    worst = {}
    for comp, fk in (("batting", "batting"), ("positional", "positional"), ("league", "wLeague"), ("rar", "rar")):
        cand = [(abs(r[comp] - r["feed"][fk]), r) for r in scored if r["feed"][fk] is not None]
        cand.sort(key=lambda x: -x[0])
        worst[comp] = [{"mlbam": r["pid"], "name": r["name"], "pa": r["pa"], "multi": r["multi"],
                        "replica": round(r[comp], 2), "feed": round(r["feed"][fk], 2)} for d, r in cand[:5]]
    nc = [abs(r["frm_noncatcher"]) for r in scored if r["frm_noncatcher"] is not None]
    return {
        "components": table(scored),
        "single_team": table([r for r in scored if not r["multi"]]),
        "multi_team": table([r for r in scored if r["multi"]]),
        "excluding_vintage_drift": table([r for r in scored if r["pid"] not in drift_ids]),
        "consumed": {
            "fielding": {"n": sum(1 for r in scored if r["feed"]["fielding"] is not None),
                         "source": "feed `fielding` column (UZR/Statcast/DRS-catcher mix), consumed verbatim"},
            "framing": {"n_catchers": sum(1 for r in scored if r["fld_pos"].get("C", 0) > 0),
                        "source": "rar minus the six published components, kept for players with catcher innings",
                        "max_abs_residual_on_non_catchers": round(max(nc), 3) if nc else None},
            "ubr_plus_wgdp": {"n": len(scored), "source": "feed baseRunning minus feed wSb",
                              "n_rows_where_feed_ubr_plus_wgdp_differs": sum(
                                  1 for r in scored if r["feed"]["baseRunning"] is not None
                                  and abs(r["feed"]["baseRunning"] - _num(r["feed"]["wSb"])
                                          - _num(r["feed"]["ubr"]) - _num(r["feed"]["wGdp"])) > 0.01)},
        },
        "rows": {"scored_pa_gt_0": len(scored), "pa_zero_skipped": n_pa0, "multi_team": sum(1 for r in scored if r["multi"]),
                 "vintage_drift_rows": len(drift), "ambiguous_ids": len(ambiguous),
                 "pf_fallback_to_neutral": n_pf_fallback},
        "park_factor": {"method": "leave-one-out back-solve from feed Batting, PA-weighted over single-team hitters with PA >= %d" % PF_POOL_MIN_PA,
                        "n_teams": len(team_pf),
                        "within_team_sd_pf_points_median": round(100 * statistics.median(pf_sd), 3) if pf_sd else None,
                        "within_team_sd_pf_points_max": round(100 * max(pf_sd), 3) if pf_sd else None,
                        "team_pf": {str(t): round(100 * v, 2) for t, v in sorted(team_pf.items())},
                        "_team_pf_raw": team_pf},
        "league_adjustment": {str(L): {"replica_rate": round(lrate[L], 6),
                                       "feed_rate": round(_median(obs_rate.get(L)), 6) if obs_rate.get(L) else None}
                              for L in sorted(lrate, key=str)},
        "league_with_feed_positional": F.gate_row(league_fp_diffs),
        "pitcher_batting_rate": {"replica": round(c_rate, 6), "feed": None if feed_c is None else round(feed_c, 6),
                                 "pool_pa": ppa},
        "replacement_per_pa": round(rep_rate, 6), "rpw": rpw, "mlb_games": games,
        "worst_rows": worst,
        "framing_crosscheck": framing_crosscheck(recs, framing_fg),
    }


# --------------------------------------------------------------------------
# Pitchers
# --------------------------------------------------------------------------

#: Park-factor sources the pitcher replica knows. "fg_fip" is FanGraphs' own FIP
#: park factor (the default whenever it is cached); "fip_minus" back-solves one
#: leave-one-out from the published FIP- (the pre-2026-09-11 default, kept as the
#: fallback and as a scored arm); "war_loo" back-solves from the published WAR and
#: is CIRCULAR by design, a ceiling diagnostic never used as an input.
PF_SOURCES = ("fg_fip", "fip_minus", "war_loo")


def pitchers(season: int, iffb: Optional[dict] = None, role_ip: Optional[dict] = None,
             mode: str = "role", pf_source: str = "fip_minus",
             fip_pf: Optional[dict] = None, framing: Optional[dict] = None,
             keep_rows: bool = False) -> dict:
    """Price every pitcher-season. `iffb` ({mlbam: IFFB}) switches the runs leg
    to ifFIP; `role_ip` ({mlbam: start innings}) overrides the B-Ref start-inning
    share; `mode` is "role" (convention 6) or "blended"; `pf_source` is one of
    PF_SOURCES, and "fg_fip" needs `fip_pf` ({team_id: decimal}); `framing`
    ({mlbam: CFraming runs}) charges each pitcher the framing earned on his
    pitches (fwar_frame convention 9). The driver passes the FanGraphs inputs
    whenever they are cached (see build and PITCHER_ARMS)."""
    if pf_source not in PF_SOURCES:
        raise ValueError(f"pf_source {pf_source!r} not in {PF_SOURCES}")
    if pf_source == "fg_fip" and not fip_pf:
        raise ValueError("pf_source 'fg_fip' needs the FanGraphs FIP park factors (fip_pf)")
    K = constants(season)
    if not K:
        return {"error": "league constants unsolvable"}
    rows, ambiguous = saber("pitching", season)
    cnt = counts("pitching", season)
    games, region = standings(season)
    adj = K["lg_ra9"] - K["lg_era"]
    rpw = K["rpw"]

    tot: dict = collections.defaultdict(lambda: collections.defaultdict(float))
    for pid, c in cnt.items():
        s = c.get("stat") or {}
        L = (c.get("league") or {}).get("id")
        for acc in (tot[L], tot["MLB"]):
            for k in ("homeRuns", "baseOnBalls", "hitByPitch", "strikeOuts", "outs"):
                acc[k] += _num(s.get(k))
            acc["iffb"] += _num((iffb or {}).get(pid))
    if iffb is not None:
        m = tot["MLB"]
        const = F.fip_constant(K["lg_era"], m["homeRuns"], m["baseOnBalls"], m["hitByPitch"],
                               m["strikeOuts"], m["outs"] / 3.0, m["iffb"])
    else:
        const = K["fip_constant"]
    lg_fip = {L: F.fip(a["homeRuns"], a["baseOnBalls"], a["hitByPitch"], a["strikeOuts"],
                       a["outs"] / 3.0, const, a["iffb"] if iffb is not None else 0.0)
              for L, a in tot.items()}
    plain_lg_fip = {L: F.fip(a["homeRuns"], a["baseOnBalls"], a["hitByPitch"], a["strikeOuts"],
                             a["outs"] / 3.0, K["fip_constant"]) for L, a in tot.items()}

    stints_all = stints_by_player("pit", season)
    tmap = team_map(stints_all, rows)

    # the leave-one-out FIP- back-solve: the fallback park factor, and the arm
    # the FanGraphs factor is measured against
    pool = collections.defaultdict(list)
    for pid, r in rows.items():
        st = r.get("stat") or {}
        c = cnt.get(pid)
        if c is None or int(r.get("numTeams") or 1) != 1:
            continue
        ip = _num((c.get("stat") or {}).get("outs")) / 3.0
        fm, fv = run_value(st.get("fipMinus")), run_value(st.get("fip"))
        L = (r.get("league") or {}).get("id")
        if ip < PF_POOL_MIN_IP or fm is None or fv is None or fv <= 0.5 or L not in plain_lg_fip:
            continue
        pf = F.pf_from_fip_minus(fm, fv, plain_lg_fip[L])
        if pf is not None:
            pool[(r.get("team") or {}).get("id")].append((pid, pf, ip))
    team_pf = {t: sum(pf * w for _, pf, w in v) / sum(w for _, _, w in v) for t, v in pool.items()}
    pf_sd = []
    for t, v in pool.items():
        if len(v) >= 3:
            m = sum(pf * w for _, pf, w in v) / sum(w for _, _, w in v)
            pf_sd.append((sum(w * (pf - m) ** 2 for _, pf, w in v) / sum(w for _, _, w in v)) ** 0.5)

    def pf_for(team, exclude=None):
        v = [(pf, w) for pid, pf, w in pool.get(team, []) if pid != exclude]
        return (sum(pf * w for pf, w in v) / sum(w for _, w in v)) if v else None

    recs = []
    for pid, c in cnt.items():
        s = c.get("stat") or {}
        ip = _num(s.get("outs")) / 3.0
        g, gs = _num(s.get("gamesPlayed")), _num(s.get("gamesStarted"))
        if ip <= 0 or g <= 0:
            continue
        r = rows.get(pid)
        st = (r or {}).get("stat") or {}
        L_row = (c.get("league") or {}).get("id")
        cnts = (_num(s.get("homeRuns")), _num(s.get("baseOnBalls")), _num(s.get("hitByPitch")),
                _num(s.get("strikeOuts")))
        f_val = F.fip(*cnts, ip, const, _num((iffb or {}).get(pid)) if iffb is not None else 0.0)
        # the INPUT check is always plain FIP against the published FIP, whatever
        # the runs leg: the feed publishes FIP, never ifFIP
        f_plain = F.fip(*cnts, ip, K["fip_constant"])
        # stints: park and league baseline by IP share (season counts are not split)
        ss = [x for x in stints_all.get(pid) or [] if x["outs"] > 0]
        multi = int((r or c).get("numTeams") or 1) > 1 or len(ss) > 1
        team_id = ((r or c).get("team") or {}).get("id")
        if ss and multi:
            touts = sum(x["outs"] for x in ss)
            parts = [(tmap.get(x["team"]), LG_ID.get(x["lg"], L_row), x["outs"] / touts) for x in ss]
        else:
            parts = [(team_id, L_row, 1.0)]
        lg9 = sum(((lg_fip.get(L) or lg_fip["MLB"]) + adj) * w for t, L, w in parts)
        # role innings
        outs_wd = sum(x["outs"] for x in ss)
        if role_ip is not None and pid in role_ip:
            start_ip = min(ip, role_ip[pid])
        elif outs_wd > 0:
            start_ip = ip * sum(x["outs_start"] for x in ss) / outs_wd
        else:
            start_ip = ip if gs >= g else 0.0
        g_rel = g - gs
        if gs <= 0:
            start_ip = 0.0
        if g_rel <= 0:
            start_ip = ip
        recs.append({"pid": pid, "name": (c.get("player") or {}).get("fullName", ""), "ip": ip,
                     "g": g, "gs": gs, "g_rel": g_rel, "start_ip": start_ip, "parts": parts,
                     "lg9": lg9, "gm": run_value(st.get("gmli")),
                     "team": team_id, "multi": multi, "fip": f_val, "fip_plain": f_plain,
                     "in_feed": r is not None,
                     "feed": {k: run_value(st.get(k)) for k in ("fip", "war", "rar", "gmli")}})

    def price(rec, pf):
        pfr = F.pfipr9(F.fipr9(rec["fip"], K["lg_ra9"], K["lg_era"]), pf)
        if framing is not None:
            # convention 9: the framing runs the pitcher's catchers earned on
            # his pitches are charged back to him, after the park factor
            pfr += F.framing_charge_per9(_num(framing.get(rec["pid"])), rec["ip"])
        if mode == "role":
            return [F.role_line(rec["start_ip"], rec["gs"], True, rec["lg9"], rec["lg9"], pfr, rec["gm"]),
                    F.role_line(rec["ip"] - rec["start_ip"], rec["g_rel"], False, rec["lg9"],
                                rec["lg9"], pfr, rec["gm"])]
        return [F.blended_line(rec["ip"], rec["g"], rec["gs"], rec["lg9"], rec["lg9"], pfr, rec["gm"])]

    n_pf_missing = [0]

    def pf_of(rec, lookup):
        tot_pf = 0.0
        for t, L, w in rec["parts"]:
            v = lookup(t, rec["pid"]) if not rec["multi"] else lookup(t, None)
            if v is None:
                v = 1.0
                n_pf_missing[0] += 1
            tot_pf += v * w
        return tot_pf

    def settle(lookup):
        n_pf_missing[0] = 0
        for rec in recs:
            rec["pf"] = pf_of(rec, lookup)
            rec["lines"] = price(rec, rec["pf"])
        target_ = F.replacement_totals(games)[1]
        w_ = F.warip(target_, sum(sum(ln["war0"] for ln in r["lines"]) for r in recs),
                     sum(r["ip"] for r in recs))
        for rec in recs:
            rec["war"], rec["rar"] = F.pitcher_war(rec["lines"], w_)
        return w_, target_

    def loo(t, ex):
        return pf_for(t, exclude=ex) if ex is not None else team_pf.get(t)

    if pf_source == "fg_fip":
        # FanGraphs' own factor is one number per team-season with no player in
        # it, so there is nothing to leave out: a traded pitcher carries the
        # IP-weighted factors of his stints
        wip, target = settle(lambda t, ex: fip_pf.get(t))
        pf_note = "fg_fip (FanGraphs Guts FIP park factor per team-season)"
    else:
        wip, target = settle(loo)
        pf_note = "fip_minus (leave-one-out back-solve from feed FIP-)"
    war_pf_sd: list = []
    if pf_source == "war_loo":
        # CEILING DIAGNOSTIC, circular by design: back-solve each single-team
        # pitcher's park factor from his published WAR (bisection on the priced
        # line at the settled WARIP), then apply the team's leave-one-out mean.
        imp = collections.defaultdict(list)
        for rec in recs:
            fw = rec["feed"]["war"]
            if rec["multi"] or fw is None or rec["ip"] < PF_POOL_MIN_IP:
                continue

            def gap(pf, rec=rec, fw=fw):
                return F.pitcher_war(price(rec, pf), wip)[0] - fw
            lo, hi = 0.7, 1.4
            glo, ghi = gap(lo), gap(hi)
            if glo * ghi > 0:
                continue
            for _ in range(60):
                mid = (lo + hi) / 2
                gm_ = gap(mid)
                if glo * gm_ <= 0:
                    hi, ghi = mid, gm_
                else:
                    lo, glo = mid, gm_
            imp[rec["team"]].append((rec["pid"], (lo + hi) / 2, rec["ip"]))

        def war_pf(t, ex):
            v = [(pf, w) for pid, pf, w in imp.get(t, []) if pid != ex]
            return (sum(pf * w for pf, w in v) / sum(w for _, w in v)) if v else team_pf.get(t)
        wip, target = settle(war_pf)
        pf_note = "war_loo (ceiling diagnostic, circular)"
        for t, v in imp.items():
            if len(v) >= 3:
                m = sum(pf * w for _, pf, w in v) / sum(w for _, _, w in v)
                war_pf_sd.append((sum(w * (pf - m) ** 2 for _, pf, w in v) / sum(w for _, _, w in v)) ** 0.5)
    scored = [r for r in recs if r["in_feed"]]

    def table(sub):
        return {
            "fip_runs": F.gate_row([(r["fip_plain"] - r["feed"]["fip"]) * r["ip"] / 9.0 for r in sub
                                    if r["feed"]["fip"] is not None]),
            "rar": F.gate_row([r["rar"] - r["feed"]["rar"] for r in sub if r["feed"]["rar"] is not None]),
            "war_runs": F.gate_row([(r["war"] - r["feed"]["war"]) * rpw for r in sub if r["feed"]["war"] is not None]),
        }
    wins_mae = [abs(r["war"] - r["feed"]["war"]) for r in scored if r["feed"]["war"] is not None]
    cand = sorted((r for r in scored if r["feed"]["rar"] is not None),
                  key=lambda r: -abs(r["rar"] - r["feed"]["rar"]))[:8]
    worst = [{"mlbam": r["pid"], "name": r["name"], "ip": round(r["ip"], 1), "g": r["g"], "gs": r["gs"],
              "start_ip": round(r["start_ip"], 1), "multi": r["multi"],
              # FanGraphs' factor is not republished; a back-solved one is ours
              "pf": None if pf_source == "fg_fip" else round(r["pf"], 4),
              "gmli": r["gm"], "replica_rar": round(r["rar"], 2), "feed_rar": round(r["feed"]["rar"], 2),
              "replica_war": round(r["war"], 3), "feed_war": round(r["feed"]["war"], 3)} for r in cand]
    pf_block = {"source": pf_note, "n_pf_lookups_missing_neutral": n_pf_missing[0],
                "loo_fip_minus": {"method": "leave-one-out back-solve from feed FIP-, IP-weighted over "
                                            "single-team pitchers with IP >= %g" % PF_POOL_MIN_IP,
                                  "n_teams": len(team_pf),
                                  "within_team_sd_pf_points_median":
                                      round(100 * statistics.median(pf_sd), 3) if pf_sd else None,
                                  "within_team_sd_pf_points_max": round(100 * max(pf_sd), 3) if pf_sd else None}}
    if fip_pf:
        common = sorted(set(team_pf) & set(fip_pf))
        gaps = [100 * (team_pf[t] - fip_pf[t]) for t in common]
        # FanGraphs' table itself is not republished (the cache digest is under
        # inputs.fangraphs); what the replica made of it is
        pf_block["fg_fip"] = {"n_teams": len(fip_pf),
                              "loo_minus_fg_pf_points_mae": round(sum(abs(x) for x in gaps) / len(gaps), 3)
                              if gaps else None,
                              "loo_minus_fg_pf_points_max": round(max(abs(x) for x in gaps), 3) if gaps else None}
    if war_pf_sd:
        pf_block["war_implied_within_team_sd_pf_points_median"] = round(100 * statistics.median(war_pf_sd), 3)
    out = {
        "worst_rows": worst,
        "components": table(scored),
        "single_team": table([r for r in scored if not r["multi"]]),
        "multi_team": table([r for r in scored if r["multi"]]),
        "ip_ge_50": table([r for r in scored if r["ip"] >= 50]),
        "war_wins_mae": round(sum(wins_mae) / len(wins_mae), 4) if wins_mae else None,
        "warip": round(wip, 6), "target_war": round(target, 2),
        "sum_replica_war": round(sum(r["war"] for r in recs), 2),
        "sum_feed_war": round(sum(r["feed"]["war"] or 0 for r in scored), 2),
        "rows": {"scored": len(scored), "priced_not_in_feed": len(recs) - len(scored),
                 "multi_team": sum(1 for r in scored if r["multi"]), "ambiguous_ids": len(ambiguous),
                 "iffb_missing": (sum(1 for r in recs if r["pid"] not in iffb) if iffb is not None else None)},
        "park_factor": pf_block,
        "mode": mode, "pf_source": pf_note,
        "role_innings": "FanGraphs Start-IP" if role_ip is not None else "B-Ref IPouts_start share",
        "runs_leg": "ifFIP (FanGraphs IFFB)" if iffb is not None else "plain FIP (no IFFB)",
        "framing_charge": ("FanGraphs pitcher CFraming, runs per nine after the park factor "
                           "(convention 9)") if framing is not None else None,
    }
    if keep_rows:
        # diagnostics only (never serialised): the priced rows and the pricer
        out["_rows"], out["_price"], out["_warip"] = recs, price, wip
    return out


#: The scored pitcher arms, each one input away from its neighbour, so what each
#: FanGraphs input buys is its own line of the table. (name, IFFB, park-factor
#: source, pitcher framing charge, FanGraphs Start-IP for the role split.)
PITCHER_ARMS = (
    ("plain_fip_loo_pf", False, "fip_minus", False, False),   # the W1.1 baseline (4242177b)
    ("iffb_loo_pf", True, "fip_minus", False, False),         # + IFFB
    ("iffb_fg_pf", True, "fg_fip", False, False),             # + FanGraphs FIP park factor
    ("iffb_fg_pf_framing", True, "fg_fip", True, False),      # + framing charged back (conv. 9)
    ("iffb_fg_pf_framing_fg_role", True, "fg_fip", True, True),  # + FanGraphs Start-IP: DEFAULT
    ("iffb_loo_pf_framing_fg_role", True, "fip_minus", True, True),  # the default on the LOO factor
)
DEFAULT_ARM = "iffb_fg_pf_framing_fg_role"


def arm_kwargs(fg: dict, use_iffb: bool, pfs: str, use_framing: bool,
               fg_role: bool) -> Optional[dict]:
    """pitchers() keyword arguments for one arm, or None when an input it needs
    is not cached for the season."""
    missing = ((use_iffb and "iffb" not in fg)
               or (pfs == "fg_fip" and "fip_pf" not in fg)
               or (use_framing and "pitcher_framing" not in fg)
               or (fg_role and "start_ip" not in fg))
    if missing:
        return None
    kw: dict = {"pf_source": pfs}
    if use_iffb:
        kw["iffb"] = fg["iffb"]
    if pfs == "fg_fip":
        kw["fip_pf"] = fg["fip_pf"]
    if use_framing:
        kw["framing"] = fg["pitcher_framing"]
    if fg_role:
        kw["role_ip"] = fg["start_ip"]
    return kw


def pitcher_arms(season: int, fg: dict) -> dict:
    """Every arm whose inputs are cached, scored on the same rows."""
    out = {}
    for name, *spec in PITCHER_ARMS:
        kw = arm_kwargs(fg, *spec)
        if kw is None:
            continue
        v = pitchers(season, **kw)
        if "components" not in v:
            continue
        out[name] = {"rar": v["components"]["rar"], "war_runs": v["components"]["war_runs"],
                     "war_wins_mae": v["war_wins_mae"], "rar_single_team": v["single_team"]["rar"],
                     "rar_multi_team": v["multi_team"]["rar"], "rar_ip_ge_50": v["ip_ge_50"]["rar"]}
    return out


def published_crosscheck(season: int, fg: dict) -> Optional[dict]:
    """FanGraphs' leaderboard WAR against the StatsAPI feed's war: the two
    published copies of one number. The replica is scored against the feed, so
    a disagreement here would make the target itself ambiguous."""
    pub = fg.get("published")
    if not pub:
        return None
    rows, _ = saber("pitching", season)
    diffs = []
    for pid, r in rows.items():
        fw = run_value((r.get("stat") or {}).get("war"))
        p = pub.get(pid)
        if fw is None or p is None or p.get("WAR") is None:
            continue
        diffs.append(abs(fw - float(p["WAR"])))
    return {"n_both": len(diffs), "n_feed": len(rows), "n_fg": len(pub),
            "n_within_0_01_war": sum(1 for d in diffs if d <= 0.01),
            "max_abs_war_diff": round(max(diffs), 4) if diffs else None}


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def default_pitcher_inputs(fg: dict) -> tuple[str, dict]:
    """(arm name, pitchers() keyword arguments) for the default pitcher line: the
    full FanGraphs input set where the season is cached, otherwise the richest
    arm its cache supports, down to the W1.1 fallback (plain FIP, leave-one-out
    FIP- back-solve, B-Ref role innings)."""
    order = [DEFAULT_ARM] + [a[0] for a in reversed(PITCHER_ARMS) if a[0] != DEFAULT_ARM
                             and a[2] == "fg_fip"] + ["iffb_loo_pf", "plain_fip_loo_pf"]
    spec = {a[0]: a[1:] for a in PITCHER_ARMS}
    for name in order:
        kw = arm_kwargs(fg, *spec[name])
        if kw is not None:
            return name, kw
    return "plain_fip_loo_pf", {"pf_source": "fip_minus"}


def build(seasons=None) -> dict:
    seasons = list(seasons or range(FIRST, LAST + 1))
    out_seasons = {}
    prev_pf = None
    fg_prov = {}
    for y in seasons:
        fg = fg_inputs(y)
        fg_prov[str(y)] = fg["provenance"]
        h = hitters(y, framing_fg=fg.get("framing"))
        prior = None
        if prev_pf:
            hp = hitters(y, pf_override=prev_pf)
            prior = {"batting": hp["components"]["batting"], "rar": hp["components"]["rar"],
                     "note": "Batting with the PRIOR season's back-solved team park factors, "
                             "the cost of a park input not read from the same season"}
        prev_pf = h["park_factor"].pop("_team_pf_raw", None) if "park_factor" in h else None
        arm, kw = default_pitcher_inputs(fg)
        p = pitchers(y, **kw)
        p["arm"] = arm
        blended = pitchers(y, mode="blended", **kw)
        blk = {"hitters": h, "pitchers": p, "hitters_prior_season_pf": prior,
               "pitchers_blended_line": {"rar": blended["components"]["rar"],
                                         "war_runs": blended["components"]["war_runs"],
                                         "war_wins_mae": blended["war_wins_mae"]},
               "pitchers_arms": pitcher_arms(y, fg),
               "pitchers_published_crosscheck": published_crosscheck(y, fg)}
        if y == LAST:
            blk["in_progress"] = True
        out_seasons[str(y)] = blk
    summary = {}
    for side, comps in (("hitters", HITTER_COMPONENTS), ("pitchers", PITCHER_COMPONENTS)):
        for comp in comps:
            v = {s: b[side]["components"][comp]["verdict"] for s, b in out_seasons.items()
                 if "components" in b[side]}
            summary[f"{side}.{comp}"] = {"pass": sorted(s for s, x in v.items() if x == "PASS"),
                                         "fail": sorted(s for s, x in v.items() if x == "FAIL")}
    # every pitcher arm's passing seasons, so the default line is read against
    # its neighbours (the leave-one-out park factor above all) off the artifact
    arms_summary: dict = {}
    for name, *_ in PITCHER_ARMS:
        for comp in ("rar", "war_runs"):
            v = {s: ((b.get("pitchers_arms") or {}).get(name) or {}).get(comp, {}).get("verdict")
                 for s, b in out_seasons.items()}
            v = {s: x for s, x in v.items() if x}
            if v:
                arms_summary.setdefault(name, {})[comp] = {
                    "pass": sorted(s for s, x in v.items() if x == "PASS"),
                    "fail": sorted(s for s, x in v.items() if x == "FAIL")}
    inputs = {
        "league_constants": _mtime(REPO / "data" / "league_constants.json"),
        "war_daily_bat": _mtime(CACHE / "war_daily" / "bat.parquet"),
        "war_daily_pit": _mtime(CACHE / "war_daily" / "pit.parquet"),
        "saber_hitting": {str(y): _mtime(CACHE / f"statsapi_saber_hitting_{y}.json") for y in seasons},
        "saber_pitching": {str(y): _mtime(CACHE / f"statsapi_saber_pitching_{y}.json") for y in seasons},
        "fielding": {str(y): _mtime(fielding_path(y)) for y in seasons},
        "counts_hitting": {str(y): _mtime(CACHE / f"fa_statsapi_hitting_{y}.json") for y in seasons},
        "fangraphs": fg_prov,
    }
    return {
        "generated_at": None,
        "what_this_is": ("W1.1 faithful fWAR replica scored component by component against "
                         "the published StatsAPI sabermetrics feed (FanGraphs' WAR line)"),
        "gate": {"tolerance_runs": F.TOLERANCE_RUNS, "share": F.GATE_SHARE,
                 "rule": "a component clears a season when >= 99% of its rows sit within 1.0 run"},
        "built": ["wOBA", "wRAA", "batting league term", "wSB", "positional (FG ladder, DH from B-Ref Inn, pitcher-batting credit)",
                  "league adjustment", "replacement", "RPW", "FIP and ifFIP", "pitcher runs leg", "dynamic RPW",
                  "role replacement", "leverage multiplier", "430 pin"],
        "consumed": ["UBR + wGDP (feed baseRunning - wSb)", "fielding (feed)", "catcher framing residual (feed)",
                     "gmLI (feed)", "batting park factor (LOO back-solve from feed Batting)",
                     "IFFB (FanGraphs pitching leaderboard, fg_leaderboards cache)",
                     "pitcher framing charge (FanGraphs pitching-leaderboard CFraming, convention 9)",
                     "pitcher role innings (FanGraphs Start-IP)",
                     "pitching park factor (FanGraphs Guts FIP park factor per team-season; "
                     "LOO back-solve from feed FIP- where the season is not cached)"],
        "fangraphs_inputs": {"source": "fg_leaderboards.py cache (.cache/fangraphs), never fetched by this tool",
                             "served": False,
                             "note": "owner decision 14a (2026-09-11): IFFB and the FIP park factor from "
                                     "FanGraphs; decision 13: CFraming cross-checked against the feed residual"},
        "war_runs_note": "war_runs is (replica WAR - feed WAR) times the season RPW, so both sides are gated in runs",
        "inputs": inputs,
        "seasons": out_seasons,
        "summary": summary,
        "pitcher_default_arm": DEFAULT_ARM,
        "pitcher_arms_summary": arms_summary,
    }


def _print(res: dict) -> None:
    hdr = "season side       component     n     within  share   MAE     max    verdict"
    print(hdr)
    for s, b in res["seasons"].items():
        for side, comps in (("hitters", HITTER_COMPONENTS), ("pitchers", PITCHER_COMPONENTS)):
            t = b[side].get("components") or {}
            for comp in comps:
                g = t.get(comp) or {}
                print(f"{s}   {side:9s}  {comp:12s} {g.get('n', 0):5d}  {g.get('n_within', 0):6d}  "
                      f"{g.get('share_within') if g.get('share_within') is not None else '-':6}  "
                      f"{g.get('mae') if g.get('mae') is not None else '-':6}  "
                      f"{g.get('max') if g.get('max') is not None else '-':6}  {g.get('verdict')}")
    print()
    print("pitcher arms, RAR share within 1.0 run (n)   single-team   multi-team   WAR MAE wins")
    for s, b in res["seasons"].items():
        for arm, v in (b.get("pitchers_arms") or {}).items():
            r, st, mt = v["rar"], v["rar_single_team"], v["rar_multi_team"]
            print(f"{s}   {arm:24s} {r.get('share_within')!s:7} ({r.get('n')})   "
                  f"{st.get('share_within')!s:7}      {mt.get('share_within')!s:7}     {v.get('war_wins_mae')}")
    print()
    print("framing cross-check, feed residual vs FanGraphs CFraming (catchers)")
    for s, b in res["seasons"].items():
        fc = (b.get("hitters") or {}).get("framing_crosscheck")
        if fc:
            print(f"{s}   both {fc['n_both']:4d}  within 0.01 {fc['n_within_0_01']:4d}  "
                  f"max {fc['max_abs_diff']}  only feed {fc['only_in_feed']['n']} "
                  f"(max {fc['only_in_feed']['max_abs_residual']})  only FG {fc['only_in_fg']['n']} "
                  f"(max {fc['only_in_fg']['max_abs_cframing']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", nargs="*", type=int)
    ap.add_argument("--write", action="store_true", help="write data/fwar_replica_eval.json")
    ap.add_argument("--out", help="write the artifact to this path instead")
    args = ap.parse_args(argv)
    res = build(args.seasons)
    _print(res)
    dest = Path(args.out) if args.out else (OUT_PATH if args.write else None)
    if dest:
        res["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
