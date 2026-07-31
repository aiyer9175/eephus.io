# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Derived tool-grade measurement tables (master plan 2026-07-30 Phase 4).

WHAT      For every scouting tool where this tree holds an observation of the
          physical quantity the grade names, fit the empirical mapping
          grade -> measured outcome, with n / median / IQR / bootstrap CI on
          the median per grade, and audit the mapping against the published
          bands of FanGraphs, Baseball America and MLB Pipeline.

WHY       The published tables are copied everywhere and tested nowhere. The
          three outlets disagree by ~2 mph on fastball velocity and 4-6 HR on
          game power (docs/reference/FANGRAPHS_FV_FRAMEWORK.md X2/X3) and MLB
          Pipeline publishes no measurement table at all, so our own table is
          the only audit that exists for one third of the industry.

GATES     Pre-registered in docs/efv-2026-07-30/TOOL_GRADE_TABLES.md BEFORE the
          first table was fitted. Read section 1 there before reading a number
          out of this artifact.

SCOPE     DERIVED REFERENCE TABLES ONLY. This lab imports no production module,
          writes no served artifact, and changes no scoring path. Every use of
          these tables inside consensus weighting or eFV scoring needs its own
          gate.

DATA      grades      data/debuts.json           last PRE-DEBUT tools_consensus
                      data/timeseries.json       latest tools_consensus (actives)
          MLB         .cache/savant_mlb/statcast_batter_*.csv     EV / hard-hit / barrels
                      .cache/savant_mlb/expected_batter_*.csv     PA / BA / wOBA / xwOBA
                      .cache/savant_oaa/oaa_all_*.csv             OAA / fielding runs
                      .cache/fa_statsapi_hitting_*.json           HR / SB / AVG / PA
                      .cache/fa_statsapi_pitching_*.json          BB / K / BF / GS
                      .cache/velo_arsenal_*.json                  fastball velocity
                      data/fielding_innings.json                  innings by position
          upper minors
                      .cache/savant_minors/{batter,pitcher}_*.csv tracked-park aggregates
                      data/aaa_physics.json                       per-pitch-type velocity

RUN       python tools/tool_grade_tables_lab.py            (report only)
          python tools/tool_grade_tables_lab.py --write    (+ data/tool_grade_tables.json)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
DATA = ROOT / "data"
OUT_PATH = DATA / "tool_grade_tables.json"

SEED = 20260730
BOOT = 2000
THIN_N = 15                      # pre-registered thin-cell floor
MLB_PA_FLOOR = 150               # career frame
MLB_PA_FULLSEASON = 350          # full-season frame
AAA_PA_FLOOR = 100               # per season
MLB_BBE_FLOOR = 50               # per season, Statcast batted-ball events
MLB_BF_FLOOR = 100               # career batters faced
FULLTIME_INN = 700.0             # fielding innings at the primary position

MLB_YEARS = tuple(range(2016, 2027))
MINORS_YEARS = (2023, 2024, 2025, 2026)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _f(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace(",", "")
    if s in ("", "-", "--", ".---", "-.--", "null", "NA", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ip_to_outs(v):
    """StatsAPI inningsPitched '12.1' = 12 innings 1 out."""
    f = _f(v)
    if f is None:
        return None
    whole = int(f)
    frac = round((f - whole) * 10)
    return whole * 3 + min(frac, 2)


def _wmean(pairs):
    """pairs of (value, weight); None values skipped."""
    num = den = 0.0
    for v, w in pairs:
        if v is None or w is None or w <= 0:
            continue
        num += v * w
        den += w
    return (num / den) if den > 0 else None


def _pctl(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return float(s[lo] + (s[hi] - s[lo]) * (pos - lo))


def _boot_median_ci(xs, rng, boot=BOOT, lo=2.5, hi=97.5):
    if len(xs) < 3:
        return None, None
    n = len(xs)
    meds = []
    for _ in range(boot):
        samp = [xs[rng.randrange(n)] for _ in range(n)]
        meds.append(statistics.median(samp))
    meds.sort()
    return (round(_pctl(meds, lo / 100.0), 4), round(_pctl(meds, hi / 100.0), 4))


def _boot_mean_ci(xs, rng, boot=BOOT):
    if len(xs) < 3:
        return None, None
    n = len(xs)
    ms = []
    for _ in range(boot):
        ms.append(sum(xs[rng.randrange(n)] for _ in range(n)) / n)
    ms.sort()
    return (round(_pctl(ms, 0.025), 4), round(_pctl(ms, 0.975), 4))


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def _spearman(a, b):
    if len(a) < 4:
        return None
    ra, rb = _rank(a), _rank(b)
    ma = sum(ra) / len(ra)
    mb = sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return None if da == 0 or db == 0 else num / (da * db)


def _boot_spearman_ci(a, b, rng, boot=600):
    n = len(a)
    if n < 10:
        return None, None
    rs = []
    for _ in range(boot):
        idx = [rng.randrange(n) for _ in range(n)]
        r = _spearman([a[i] for i in idx], [b[i] for i in idx])
        if r is not None:
            rs.append(r)
    if len(rs) < 20:
        return None, None
    rs.sort()
    return round(_pctl(rs, 0.025), 4), round(_pctl(rs, 0.975), 4)


def _bin_grade(g):
    if g is None:
        return None
    return int(min(80, max(20, round(float(g) / 5.0) * 5)))


# ---------------------------------------------------------------------------
# grade loaders
# ---------------------------------------------------------------------------

def load_grade_pools():
    """(mlb_pool, aaa_pool) keyed by int mlbam id.

    mlb_pool = debuted players, grade = LAST PRE-DEBUT tools_consensus point.
    aaa_pool = active prospects (latest point) + the same pre-debut grades for
    debuted players, so the AAA arm sees both sides of the graduation line.
    """
    deb = json.loads((DATA / "debuts.json").read_text(encoding="utf-8"))
    ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))

    def rec_entry(rec, pt):
        tc = pt.get("tools_consensus") or {}
        per = {}
        for src, blk in (pt.get("per_source") or {}).items():
            tl = (blk or {}).get("tools") or {}
            g = {k: _f(v) for k, v in tl.items() if k != "_extras" and _f(v) is not None}
            if g:
                per[src] = g
        return {
            "player_key": rec.get("player_key"),
            "name": rec.get("player_name"),
            "position": rec.get("position"),
            # FanGraphs role designations in this tree: P / RHP / LHP / SP / RP
            # plus the reliever sub-designations SIRP (single-inning) and MIRP
            # (multi-inning). Anything else is a position player.
            "is_pitcher": (rec.get("position") or "") in (
                "P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP"),
            "grade_date": pt.get("snapshot_date"),
            "debut_date": rec.get("debut_date"),
            "tools": {k: _f(v) for k, v in tc.items() if _f(v) is not None},
            "per_source": per,
        }

    mlb_pool = {}
    for rec in deb:
        mid = rec.get("mlbam_id")
        if not mid:
            continue
        dd = rec.get("debut_date")
        chosen = None
        for pt in (rec.get("points") or []):
            d = pt.get("snapshot_date")
            if dd and d and d >= dd:
                continue
            if pt.get("tools_consensus"):
                chosen = pt
        if chosen is not None:
            mlb_pool[int(mid)] = rec_entry(rec, chosen)

    aaa_pool = dict(mlb_pool)
    for rec in ts.get("players") or []:
        mid = rec.get("mlbam_id")
        if not mid:
            continue
        chosen = None
        for pt in (rec.get("points") or []):
            if pt.get("tools_consensus"):
                chosen = pt
        if chosen is not None:
            aaa_pool[int(mid)] = rec_entry(rec, chosen)
    return mlb_pool, aaa_pool


# ---------------------------------------------------------------------------
# measurement loaders
# ---------------------------------------------------------------------------

def _csv_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_mlb_batter_statcast():
    """{pid:int -> [season blocks]} EV / hard-hit / barrels, MLB."""
    out = defaultdict(list)
    for y in MLB_YEARS:
        for r in _csv_rows(CACHE / "savant_mlb" / f"statcast_batter_{y}.csv"):
            pid = _f(r.get("player_id"))
            bbe = _f(r.get("attempts"))
            if pid is None or bbe is None or bbe < MLB_BBE_FLOOR:
                continue
            out[int(pid)].append({
                "season": y, "bbe": bbe,
                "ev_avg": _f(r.get("avg_hit_speed")),
                "ev50": _f(r.get("ev50")),
                "ev_max": _f(r.get("max_hit_speed")),
                "hardhit_pct": _f(r.get("ev95percent")),
                "barrel_bbe_pct": _f(r.get("brl_percent")),
                "barrel_pa_pct": _f(r.get("brl_pa")),
            })
    return out


def load_mlb_batter_expected():
    out = defaultdict(list)
    for y in MLB_YEARS:
        for r in _csv_rows(CACHE / "savant_mlb" / f"expected_batter_{y}.csv"):
            pid = _f(r.get("player_id"))
            pa = _f(r.get("pa"))
            if pid is None or pa is None:
                continue
            out[int(pid)].append({"season": y, "pa": pa,
                                  "xba": _f(r.get("est_ba")),
                                  "xwoba": _f(r.get("est_woba")),
                                  "woba": _f(r.get("woba"))})
    return out


def load_mlb_oaa():
    out = defaultdict(list)
    for y in MLB_YEARS:
        p = CACHE / "savant_oaa" / f"oaa_all_{y}.csv"
        if not p.exists():
            p = CACHE / "savant_oaa" / f"oaa_{y}.csv"
        for r in _csv_rows(p):
            pid = _f(r.get("player_id"))
            if pid is None:
                continue
            out[int(pid)].append({
                "season": y,
                "pos": (r.get("primary_pos_formatted") or "").strip(),
                "frp": _f(r.get("fielding_runs_prevented")),
                "oaa": _f(r.get("outs_above_average")),
                "succ_diff": _f(r.get("diff_success_rate_formatted")),
            })
    return out


def load_fielding_innings():
    """{pid:int -> {season:int -> {pos: inn}}} MLB fielding innings."""
    d = json.loads((DATA / "fielding_innings.json").read_text(encoding="utf-8"))
    out = defaultdict(dict)
    for season, byp in (d.get("seasons") or {}).items():
        for pid, byq in byp.items():
            try:
                out[int(pid)][int(season)] = {k: _f((v or {}).get("inn"))
                                             for k, v in byq.items()}
            except (TypeError, ValueError):
                continue
    return out


def load_mlb_season_hitting():
    out = defaultdict(list)
    for y in range(2000, 2027):
        p = CACHE / f"fa_statsapi_hitting_{y}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for blk in d.get("stats") or []:
            for sp in blk.get("splits") or []:
                pid = ((sp.get("player") or {}).get("id"))
                st = sp.get("stat") or {}
                pa = _f(st.get("plateAppearances"))
                if pid is None or not pa:
                    continue
                out[int(pid)].append({
                    "season": y, "pa": pa, "ab": _f(st.get("atBats")),
                    "age": _f(st.get("age")),
                    "h": _f(st.get("hits")), "hr": _f(st.get("homeRuns")),
                    "sb": _f(st.get("stolenBases")), "cs": _f(st.get("caughtStealing")),
                    "triples": _f(st.get("triples")), "bb": _f(st.get("baseOnBalls")),
                    "so": _f(st.get("strikeOuts")),
                })
    return out


def load_mlb_season_pitching():
    out = defaultdict(list)
    for y in range(2000, 2027):
        p = CACHE / f"fa_statsapi_pitching_{y}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for blk in d.get("stats") or []:
            for sp in blk.get("splits") or []:
                pid = ((sp.get("player") or {}).get("id"))
                st = sp.get("stat") or {}
                bf = _f(st.get("battersFaced"))
                if pid is None or not bf:
                    continue
                out[int(pid)].append({
                    "season": y, "bf": bf, "age": _f(st.get("age")),
                    "bb": _f(st.get("baseOnBalls")), "so": _f(st.get("strikeOuts")),
                    "g": _f(st.get("gamesPlayed")), "gs": _f(st.get("gamesStarted")),
                    "outs": _ip_to_outs(st.get("inningsPitched")),
                })
    return out


def load_velo_arsenal():
    out = {}
    for y in range(2017, 2027):
        p = CACHE / f"velo_arsenal_{y}.json"
        if not p.exists():
            continue
        out[y] = {int(k): float(v) for k, v in
                  json.loads(p.read_text(encoding="utf-8")).items()}
    return out


def load_pitcher_hand():
    """{pid:int -> 'L'|'R'} from the cached AAA per-pitcher pitch CSVs."""
    hand = {}
    d = CACHE / "aaa_pitches"
    if not d.exists():
        return hand
    for name in os.listdir(d):
        if not name.endswith(".csv"):
            continue
        pid = name.split("_")[0]
        if not pid.isdigit() or int(pid) in hand:
            continue
        try:
            with (d / name).open(encoding="utf-8") as f:
                rdr = csv.DictReader(f)
                for r in rdr:
                    t = (r.get("p_throws") or "").strip()
                    if t in ("L", "R"):
                        hand[int(pid)] = t
                        break
        except OSError:
            continue
    return hand


def load_minors_batter():
    out = defaultdict(list)
    for y in MINORS_YEARS:
        for r in _csv_rows(CACHE / "savant_minors" / f"batter_{y}.csv"):
            pid = _f(r.get("player_id"))
            pa = _f(r.get("pa"))
            if pid is None or pa is None or pa < AAA_PA_FLOOR:
                continue
            trip = _f(r.get("triples"))
            out[int(pid)].append({
                "season": y, "pa": pa,
                "ev_avg": _f(r.get("launch_speed")),
                "ev_adj": _f(r.get("hyper_speed")),
                "hardhit_pct": _f(r.get("hardhit_percent")),
                "barrel_bbe_pct": _f(r.get("barrels_per_bbe_percent")),
                "barrel_pa_pct": _f(r.get("barrels_per_pa_percent")),
                "whiff_pct": _f(r.get("swing_miss_percent")),
                "xba": _f(r.get("xba")), "xwoba": _f(r.get("xwoba")),
                "iso": _f(r.get("iso")), "ba": _f(r.get("ba")),
                "k_pct": _f(r.get("k_percent")), "bb_pct": _f(r.get("bb_percent")),
                "triples_per_600": (None if trip is None else trip / pa * 600.0),
            })
    return out


def load_minors_pitcher():
    out = defaultdict(list)
    for y in MINORS_YEARS:
        for r in _csv_rows(CACHE / "savant_minors" / f"pitcher_{y}.csv"):
            pid = _f(r.get("player_id"))
            pa = _f(r.get("pa"))
            if pid is None or pa is None or pa < AAA_PA_FLOOR:
                continue
            out[int(pid)].append({
                "season": y, "pa": pa,
                "velo_all": _f(r.get("velocity")),
                "whiff_pct": _f(r.get("swing_miss_percent")),
                "k_pct": _f(r.get("k_percent")), "bb_pct": _f(r.get("bb_percent")),
                "spin": _f(r.get("spin_rate")), "ext": _f(r.get("release_extension")),
            })
    return out


_FB_TYPES = ("FF", "SI", "FC")


def load_aaa_physics():
    """{pid:int -> [ {season, fb_velo, fb_type, fb_astuff, spin, ivb, astuff_pool} ]}"""
    d = json.loads((DATA / "aaa_physics.json").read_text(encoding="utf-8"))
    out = defaultdict(list)
    for pid, byseason in (d.get("players") or {}).items():
        for season, blk in byseason.items():
            bt = (blk or {}).get("by_type") or {}
            best = None
            for t in _FB_TYPES:
                row = bt.get(t)
                if not row or row.get("velo") is None:
                    continue
                use = _f(row.get("usage")) or 0.0
                if best is None or use > best[1]:
                    best = (t, use, row)
            if best is None:
                continue
            t, _use, row = best
            max3 = max((_f(bt[x].get("velo")) for x in _FB_TYPES
                        if bt.get(x) and _f(bt[x].get("velo")) is not None),
                       default=None)
            out[int(pid)].append({
                "season": int(season), "fb_type": t,
                "fb_velo_max3": max3,
                "fb_velo": _f(row.get("velo")),
                "fb_astuff": _f(row.get("astuff")),
                "fb_spin": _f(row.get("spin")),
                "fb_ivb": _f(row.get("ivb")),
                "n_pitches": _f(row.get("n_pitches")),
                "astuff_pool": _f((blk or {}).get("astuff_pool")),
            })
    return out


# ---------------------------------------------------------------------------
# per-player measurement assembly
# ---------------------------------------------------------------------------

def mlb_hitter_measures(pid, sc, exp, seas, oaa, finn):
    """One dict of MLB-context measurements for one hitter, or None."""
    rows = seas.get(pid) or []
    pa_tot = sum(r["pa"] or 0 for r in rows)
    m = {"mlb_pa": pa_tot, "mlb_seasons": len(rows)}
    if pa_tot >= MLB_PA_FLOOR:
        ab = sum(r["ab"] or 0 for r in rows)
        h = sum(r["h"] or 0 for r in rows)
        m["avg_career"] = (h / ab) if ab else None
        m["hr_per600_career"] = sum(r["hr"] or 0 for r in rows) / pa_tot * 600.0
        m["sb_per600_career"] = sum(r["sb"] or 0 for r in rows) / pa_tot * 600.0
        m["sbatt_per600_career"] = (sum((r["sb"] or 0) + (r["cs"] or 0)
                                        for r in rows) / pa_tot * 600.0)
        m["triples_per600_career"] = sum(r["triples"] or 0 for r in rows) / pa_tot * 600.0
        m["k_pct_career"] = sum(r["so"] or 0 for r in rows) / pa_tot * 100.0
        m["bb_pct_career"] = sum(r["bb"] or 0 for r in rows) / pa_tot * 100.0
    full = [r for r in rows if (r["pa"] or 0) >= MLB_PA_FULLSEASON]
    if full:
        best = max(full, key=lambda r: r["pa"])
        m["fullseason_pa"] = best["pa"]
        m["fullseason_season"] = best["season"]
        m["avg_fullseason"] = ((best["h"] or 0) / best["ab"]) if best["ab"] else None
        m["hr_per600_fullseason"] = (best["hr"] or 0) / best["pa"] * 600.0
        m["sb_per600_fullseason"] = (best["sb"] or 0) / best["pa"] * 600.0
        m["k_pct_fullseason"] = (best["so"] or 0) / best["pa"] * 100.0
    # age-26+ frame: closest available stand-in for "at maturity"
    mature = [r for r in rows if (r.get("age") or 0) >= 26 and (r["pa"] or 0) >= 300]
    if mature:
        mpa = sum(r["pa"] for r in mature)
        m["hr_per600_age26"] = sum(r["hr"] or 0 for r in mature) / mpa * 600.0
        mab = sum(r["ab"] or 0 for r in mature)
        m["avg_age26"] = (sum(r["h"] or 0 for r in mature) / mab) if mab else None
        m["age26_pa"] = mpa
    # Statcast tracking
    srows = sc.get(pid) or []
    if srows:
        w = [(r, r["bbe"]) for r in srows]
        for k in ("ev_avg", "ev50", "hardhit_pct", "barrel_bbe_pct", "barrel_pa_pct"):
            m[k] = _wmean([(r[k], wt) for r, wt in w])
        mx = [r["ev_max"] for r in srows if r["ev_max"] is not None]
        m["ev_max"] = max(mx) if mx else None
        m["mlb_bbe"] = sum(r["bbe"] for r in srows)
    erows = exp.get(pid) or []
    if erows:
        m["xba"] = _wmean([(r["xba"], r["pa"]) for r in erows])
        m["xwoba"] = _wmean([(r["xwoba"], r["pa"]) for r in erows])
        m["woba"] = _wmean([(r["woba"], r["pa"]) for r in erows])
    # fielding: full-time seasons only, primary position from the OAA row
    orows = oaa.get(pid) or []
    ft = []
    for r in orows:
        inn = ((finn.get(pid) or {}).get(r["season"]) or {}).get(r["pos"])
        if inn is None or inn < FULLTIME_INN:
            continue
        ft.append((r, inn))
    if ft:
        m["frp_fulltime"] = statistics.median([r["frp"] for r, _ in ft
                                               if r["frp"] is not None] or [0.0])
        m["oaa_fulltime"] = statistics.median([r["oaa"] for r, _ in ft
                                               if r["oaa"] is not None] or [0.0])
        m["frp_per1000inn"] = _wmean([(r["frp"] / inn * 1000.0, inn)
                                      for r, inn in ft if r["frp"] is not None])
        m["succ_diff"] = _wmean([(r["succ_diff"], inn) for r, inn in ft
                                 if r["succ_diff"] is not None])
        m["fielding_fulltime_seasons"] = len(ft)
        m["fielding_pos"] = ft[-1][0]["pos"]
    return m


def mlb_pitcher_measures(pid, seas, velo, hand):
    rows = seas.get(pid) or []
    bf = sum(r["bf"] or 0 for r in rows)
    m = {"mlb_bf": bf, "mlb_seasons": len(rows)}
    if bf >= MLB_BF_FLOOR:
        m["bb_pct_career"] = sum(r["bb"] or 0 for r in rows) / bf * 100.0
        m["k_pct_career"] = sum(r["so"] or 0 for r in rows) / bf * 100.0
        g = sum(r["g"] or 0 for r in rows)
        gs = sum(r["gs"] or 0 for r in rows)
        m["gs_share"] = (gs / g) if g else None
        m["role"] = "SP" if (g and gs / g >= 0.5) else "RP"
    vs = [(y, velo[y][pid]) for y in sorted(velo) if pid in velo[y]]
    if vs:
        m["fb_velo_first"] = vs[0][1]
        m["fb_velo_max"] = max(v for _y, v in vs)
        m["fb_velo_mean"] = sum(v for _y, v in vs) / len(vs)
        m["fb_velo_seasons"] = len(vs)
    if pid in hand:
        m["throws"] = hand[pid]
    return m


def _agg_seasons(rows, keys, wkey="pa"):
    out = {}
    for k in keys:
        out[k] = _wmean([(r.get(k), r.get(wkey)) for r in rows])
    out["n_seasons"] = len(rows)
    out["w_total"] = sum(r.get(wkey) or 0 for r in rows)
    return out


# ---------------------------------------------------------------------------
# table builder
# ---------------------------------------------------------------------------

def build_cells(pairs, rng, decimals=2):
    """pairs = [(unrounded_grade, measurement, player_key)] -> per-grade cells."""
    by = defaultdict(list)
    for g, v, pk in pairs:
        b = _bin_grade(g)
        if b is None or v is None:
            continue
        by[b].append((float(g), float(v), pk))
    cells = {}
    for b in sorted(by):
        rows = by[b]
        xs = [v for _g, v, _p in rows]
        n = len(xs)
        cell = {
            "n": n,
            "grade_mean": round(sum(g for g, _v, _p in rows) / n, 2),
            "median": round(statistics.median(xs), decimals),
            "p25": round(_pctl(xs, 0.25), decimals),
            "p75": round(_pctl(xs, 0.75), decimals),
            "min": round(min(xs), decimals),
            "max": round(max(xs), decimals),
            "thin": n < THIN_N,
        }
        if n >= THIN_N:
            lo, hi = _boot_median_ci(xs, rng)
            cell["ci95_median"] = [None if lo is None else round(lo, decimals),
                                   None if hi is None else round(hi, decimals)]
        else:
            cell["ci95_median"] = None
        cells[str(b)] = cell
    return cells


def _ols_slope(xs, ys):
    n = len(xs)
    if n < 4:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def build_table(pairs, rng, unit, decimals=2, higher_is_better=True, notes=None):
    cells = build_cells(pairs, rng, decimals)
    gs = [g for g, v, _p in pairs if v is not None]
    vs = [v for _g, v, _p in pairs if v is not None]
    rho = _spearman(gs, vs)
    rlo, rhi = _boot_spearman_ci(gs, vs, rng)
    solid = [int(k) for k, c in cells.items() if not c["thin"]]
    mono = None
    if len(solid) >= 3:
        seq = [cells[str(k)]["median"] for k in sorted(solid)]
        inc = sum(1 for a, b in zip(seq, seq[1:]) if b > a)
        mono = round(inc / max(1, len(seq) - 1), 3)
    # the FanGraphs distributional claim (framework doc X1): 10 grade points is
    # supposed to be one standard deviation of the measured quantity.
    sd = statistics.pstdev(vs) if len(vs) > 2 else None
    slope = _ols_slope(gs, vs)
    per10 = None if slope is None else slope * 10.0
    ratio = None
    if sd and per10 is not None and sd > 0:
        ratio = abs(per10) / sd
    verdict = "signal"
    if rho is None:
        verdict = "not computable"
    elif abs(rho) < 0.20:
        verdict = ("DESCRIPTIVE ONLY: |rho| < 0.20, the grade does not order this "
                   "measurement in our data (pre-registration section 1.9)")
    return {
        "unit": unit,
        "n_players": len(vs),
        "spearman_grade_vs_measure": None if rho is None else round(rho, 4),
        "spearman_ci95": [rlo, rhi],
        "signal_verdict": verdict,
        "monotone_step_share": mono,
        "higher_is_better": higher_is_better,
        "n_solid_cells": len(solid),
        "population_sd": None if sd is None else round(sd, decimals + 1),
        "measured_change_per_10_grade": None if per10 is None
        else round(per10, decimals + 1),
        "sd_per_10_grade_ratio": None if ratio is None else round(ratio, 3),
        "cells": cells,
        "notes": notes or [],
    }


# ---------------------------------------------------------------------------
# published bands (verbatim from docs/reference/FANGRAPHS_FV_FRAMEWORK.md)
# ---------------------------------------------------------------------------
# Values are [lo, hi] intervals; a published point value is [v, v].

PUBLISHED = {
    "fb_velo_sp": {
        "unit": "mph, average fastball velocity, starters",
        "fangraphs_2014": {80: [97, 97], 75: [96, 96], 70: [95, 95], 65: [94, 94],
                           60: [93, 93], 55: [92, 92], 50: [90, 91], 45: [89, 89],
                           40: [88, 88], 35: [87, 87], 30: [86, 86]},
        "smith_2013_sp": {80: [97, 97], 70: [95, 95], 60: [93, 93], 50: [91, 91],
                          40: [88, 88], 30: [86, 86], 20: [84, 84]},
        "baseball_america": {80: [98, 103], 70: [97, 97], 65: [96, 96], 60: [95, 95],
                             55: [94, 94], 50: [93, 93], 45: [92, 92], 40: [90, 91],
                             30: [88, 89], 20: [80, 87]},
        "mlb_pipeline": None,
    },
    "fb_velo_rp": {
        "unit": "mph, average fastball velocity, relievers",
        "smith_2013_rp": {80: [100, 100], 70: [97, 97], 60: [95, 95], 50: [92, 92],
                          40: [89, 89], 30: [86, 86], 20: [84, 84]},
        "baseball_america": {80: [99, 105], 70: [98, 99], 65: [97, 98], 60: [96, 97],
                             55: [95, 96], 50: [94, 95], 45: [93, 94], 40: [91, 93],
                             30: [89, 91], 20: [80, 89]},
        "fangraphs_2014": None,
        "mlb_pipeline": None,
        "notes": ["BA publishes only the starter table plus 'add 1-2 mph for relievers';"
                  " the BA reliever row here is the starter band plus 1 to 2 mph."],
    },
    "hr_per600": {
        "unit": "home runs per full MLB season (600 PA)",
        "fangraphs_2014": {80: [40, 55], 75: [35, 40], 70: [30, 35], 65: [27, 30],
                           60: [23, 27], 55: [19, 22], 50: [15, 18], 45: [12, 15],
                           40: [8, 12], 35: [5, 8], 30: [3, 5]},
        "baseball_america": {80: [40, 55], 70: [34, 39], 60: [28, 33], 55: [23, 27],
                             50: [19, 22], 45: [14, 18], 40: [10, 13], 30: [5, 9],
                             20: [0, 4]},
        "mlb_pipeline": None,
    },
    "avg": {
        "unit": "MLB batting average",
        "fangraphs_2014": {80: [.320, .320], 75: [.310, .310], 70: [.300, .300],
                           65: [.290, .290], 60: [.280, .280], 55: [.270, .270],
                           50: [.260, .260], 45: [.250, .250], 40: [.240, .240],
                           35: [.230, .230], 30: [.220, .220]},
        "baseball_america": {80: [.315, .400], 70: [.295, .314], 60: [.275, .294],
                             55: [.265, .274], 50: [.255, .264], 45: [.245, .254],
                             40: [.235, .244], 30: [.215, .234], 20: [.150, .214]},
        "smith_2013": {80: [.336, .336], 70: [.313, .313], 60: [.290, .290],
                       50: [.267, .267], 40: [.244, .244], 30: [.221, .221],
                       20: [.199, .199]},
        "mlb_pipeline": None,
    },
    "sb_per_season": {
        "unit": "stolen bases per MLB season",
        "smith_2013": {80: [38, 38], 70: [29, 29], 60: [19, 19], 50: [9, 9],
                       30: [-10, -10], 20: [-20, -20]},
        "fangraphs_2014": None,   # FG publishes seconds, not SB
        "baseball_america": None,  # BA publishes seconds, not SB
        "mlb_pipeline": None,
    },
    "bb_pct_sp": {
        "unit": "MLB walk rate, percent, starters (lower is better)",
        "smith_2013_sp": {80: [1.7, 1.7], 70: [3.7, 3.7], 60: [5.7, 5.7],
                          50: [7.8, 7.8], 40: [9.8, 9.8], 30: [11.8, 11.8],
                          20: [13.9, 13.9]},
        "fangraphs_2014": None,
        "baseball_america": None,
        "mlb_pipeline": None,
    },
    "bb_pct_rp": {
        "unit": "MLB walk rate, percent, relievers (lower is better)",
        "smith_2013_rp": {80: [2.0, 2.0], 70: [4.4, 4.4], 60: [6.8, 6.8],
                          50: [9.2, 9.2], 40: [11.6, 11.6], 30: [13.9, 13.9],
                          20: [16.3, 16.3]},
        "fangraphs_2014": None,
        "baseball_america": None,
        "mlb_pipeline": None,
    },
    "fielding_runs": {
        "unit": "defensive runs per full MLB season",
        "smith_2013_uzr150": {80: [22.8, 22.8], 70: [15.7, 15.7], 60: [8.7, 8.7],
                              50: [1.6, 1.6], 40: [-5.4, -5.4], 30: [-12.5, -12.5],
                              20: [-19.6, -19.6]},
        "smith_2013_fld3": {80: [17.9, 17.9], 70: [12.4, 12.4], 60: [6.9, 6.9],
                            50: [1.5, 1.5], 40: [-4.0, -4.0], 30: [-9.5, -9.5],
                            20: [-14.9, -14.9]},
        "fangraphs_2014": None,
        "baseball_america": None,
        "mlb_pipeline": None,
    },
}


def audit(table, key, lower_is_better=False):
    """Compare a derived table against every published band for that quantity."""
    pub = PUBLISHED.get(key) or {}
    rows = []
    for outlet, bands in pub.items():
        if outlet in ("unit", "notes"):
            continue
        if bands is None:
            rows.append({"outlet": outlet, "status": "no published band",
                         "grade": None, "published": None, "ours": None,
                         "gap": None})
            continue
        for g, band in sorted(bands.items()):
            cell = (table.get("cells") or {}).get(str(g))
            if cell is None:
                rows.append({"outlet": outlet, "grade": g, "published": band,
                             "ours": None, "gap": None,
                             "status": "no measured cell"})
                continue
            if cell["thin"]:
                rows.append({"outlet": outlet, "grade": g, "published": band,
                             "ours": cell["median"], "n": cell["n"], "gap": None,
                             "status": "thin, excluded from audit"})
                continue
            ci = cell.get("ci95_median") or [None, None]
            med = cell["median"]
            lo, hi = band
            mid = (lo + hi) / 2.0
            gap = round(med - mid, 3)
            if ci[0] is None:
                status = "no CI"
            elif hi < ci[0] or lo > ci[1]:
                status = "DISAGREE"
            else:
                ciw = ci[1] - ci[0]
                bw = hi - lo
                status = "agree (uninformative: band wider than CI)" \
                    if bw > ciw else "agree"
            rows.append({"outlet": outlet, "grade": g, "published": band,
                         "ours": med, "ci95": ci, "n": cell["n"],
                         "gap_ours_minus_theirs": gap, "status": status})
    # slope comparison: measured units per 10 grade points, ours vs each outlet,
    # over the grades where both sides have a value and our cell is solid.
    slopes = {}
    ours_by_g = {int(g): c["median"] for g, c in (table.get("cells") or {}).items()
                 if not c["thin"] and c["median"] is not None}
    for outlet, bands in pub.items():
        if outlet in ("unit", "notes") or bands is None:
            continue
        shared = sorted(set(bands) & set(ours_by_g))
        if len(shared) < 3:
            slopes[outlet] = {"n_shared_grades": len(shared), "status": "too thin"}
            continue
        pub_mid = [(bands[g][0] + bands[g][1]) / 2.0 for g in shared]
        ours = [ours_by_g[g] for g in shared]
        sp = _ols_slope([float(g) for g in shared], pub_mid)
        so = _ols_slope([float(g) for g in shared], ours)
        slopes[outlet] = {
            "n_shared_grades": len(shared),
            "grades": shared,
            "published_per_10_grade": None if sp is None else round(sp * 10, 3),
            "ours_per_10_grade": None if so is None else round(so * 10, 3),
            "ours_over_published": (None if not sp or so is None
                                    else round(so / sp, 3)),
        }
    return {"published_unit": pub.get("unit"), "published_notes": pub.get("notes"),
            "lower_is_better": lower_is_better, "slope_comparison": slopes,
            "rows": rows}


def load_source_grades_db():
    """{player_key -> {source -> {tool -> [(snapshot_date, grade)]}}} from the
    prospects.db snapshot history (2011-2026), the only place the per-source tool
    grades survive for old vintages; the timeseries points prune them."""
    import sqlite3
    path = ROOT / "prospects.db"
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    if not path.exists():
        return out
    con = sqlite3.connect(str(path))
    try:
        q = ("select source, player_key, snapshot_date, tools_json from snapshots "
             "where tools_json is not null and tools_json != ''")
        for src, pk, sd, tj in con.execute(q):
            if not pk or not src:
                continue
            try:
                d = json.loads(tj)
            except (TypeError, ValueError):
                continue
            if not isinstance(d, dict):
                continue
            for tool, g in d.items():
                if tool == "_extras":
                    continue
                gv = _f(g)
                if gv is not None:
                    out[pk][src][tool].append((sd or "", gv))
    finally:
        con.close()
    return out


# ---------------------------------------------------------------------------
# context offset: within-player AAA minus MLB
# ---------------------------------------------------------------------------

def context_offset(pairs, rng, decimals=2):
    """pairs = [(aaa_value, mlb_value)] -> offset block."""
    d = [a - b for a, b in pairs if a is not None and b is not None]
    if len(d) < 3:
        return {"n": len(d), "mean": None, "median": None, "ci95_mean": None,
                "usable": False}
    lo, hi = _boot_mean_ci(d, rng)
    return {"n": len(d),
            "mean": round(sum(d) / len(d), decimals),
            "median": round(statistics.median(d), decimals),
            "ci95_mean": [None if lo is None else round(lo, decimals),
                          None if hi is None else round(hi, decimals)],
            "usable": len(d) >= 30}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    rng = random.Random(SEED)

    mlb_pool, aaa_pool = load_grade_pools()
    sc = load_mlb_batter_statcast()
    exp = load_mlb_batter_expected()
    seas_h = load_mlb_season_hitting()
    seas_p = load_mlb_season_pitching()
    oaa = load_mlb_oaa()
    finn = load_fielding_innings()
    velo = load_velo_arsenal()
    hand = load_pitcher_hand()
    mb = load_minors_batter()
    mp = load_minors_pitcher()
    phys = load_aaa_physics()

    # ---- per-player measurement rows -------------------------------------
    MLBM, AAAM = {}, {}
    for pid, rec in mlb_pool.items():
        if rec["is_pitcher"]:
            MLBM[pid] = mlb_pitcher_measures(pid, seas_p, velo, hand)
        else:
            MLBM[pid] = mlb_hitter_measures(pid, sc, exp, seas_h, oaa, finn)
    for pid, rec in aaa_pool.items():
        if rec["is_pitcher"]:
            rows = mp.get(pid) or []
            m = _agg_seasons(rows, ("velo_all", "whiff_pct", "k_pct", "bb_pct",
                                    "spin", "ext")) if rows else {}
            prows = phys.get(pid) or []
            if prows:
                m["fb_velo_aaa"] = _wmean([(r["fb_velo"], r["n_pitches"])
                                           for r in prows])
                m["fb_velo_aaa_max3"] = _wmean([(r["fb_velo_max3"], r["n_pitches"])
                                                for r in prows])
                m["fb_astuff_aaa"] = _wmean([(r["fb_astuff"], r["n_pitches"])
                                             for r in prows])
                m["astuff_pool_aaa"] = _wmean([(r["astuff_pool"], r["n_pitches"])
                                               for r in prows])
                m["fb_spin_aaa"] = _wmean([(r["fb_spin"], r["n_pitches"])
                                           for r in prows])
                m["fb_ivb_aaa"] = _wmean([(r["fb_ivb"], r["n_pitches"])
                                          for r in prows])
                m["fb_type_aaa"] = prows[-1]["fb_type"]
            AAAM[pid] = m
        else:
            rows = mb.get(pid) or []
            AAAM[pid] = _agg_seasons(rows, ("ev_avg", "ev_adj", "hardhit_pct",
                                            "barrel_bbe_pct", "barrel_pa_pct",
                                            "whiff_pct", "xba", "xwoba", "iso",
                                            "ba", "k_pct", "bb_pct",
                                            "triples_per_600")) if rows else {}

    def pairs(pool, meas, tool, mkey, filt=None):
        out = []
        for pid, rec in pool.items():
            g = (rec.get("tools") or {}).get(tool)
            if g is None:
                continue
            m = meas.get(pid) or {}
            v = m.get(mkey)
            if v is None:
                continue
            if filt and not filt(rec, m):
                continue
            out.append((g, v, rec["player_key"]))
        return out

    T = {}

    # ================= RAW POWER =========================================
    T["raw_pwr__mlb_ev_avg"] = build_table(
        pairs(mlb_pool, MLBM, "raw_pwr", "ev_avg"), rng,
        "mph, average exit velocity, MLB", 2,
        notes=["MLB context. BBE-weighted across all MLB seasons, 50 BBE floor "
               "per season. No published outlet band exists in EV units."])
    T["raw_pwr__mlb_ev50"] = build_table(
        pairs(mlb_pool, MLBM, "raw_pwr", "ev50"), rng,
        "mph, average of the top half of batted balls, MLB", 2)
    T["raw_pwr__mlb_ev_max"] = build_table(
        pairs(mlb_pool, MLBM, "raw_pwr", "ev_max"), rng,
        "mph, max exit velocity, MLB", 2,
        notes=["Career max, so it rises with MLB playing time; read the p25/p75 "
               "spread, not the level."])
    T["raw_pwr__mlb_hardhit_pct"] = build_table(
        pairs(mlb_pool, MLBM, "raw_pwr", "hardhit_pct"), rng,
        "percent of batted balls at 95+ mph, MLB", 2)
    T["raw_pwr__aaa_ev_avg"] = build_table(
        pairs(aaa_pool, AAAM, "raw_pwr", "ev_avg"), rng,
        "mph, average exit velocity, upper minors", 2,
        notes=["Upper-minors tracked parks 2023-2026, concurrent frame."])
    T["raw_pwr__aaa_ev_adj"] = build_table(
        pairs(aaa_pool, AAAM, "raw_pwr", "ev_adj"), rng,
        "mph, adjusted (hyper) exit velocity, upper minors", 2)
    T["raw_pwr__aaa_hardhit_pct"] = build_table(
        pairs(aaa_pool, AAAM, "raw_pwr", "hardhit_pct"), rng,
        "percent of batted balls at 95+ mph, upper minors", 2)

    # ================= GAME POWER ========================================
    T["game_pwr__mlb_hr_per600_career"] = build_table(
        pairs(mlb_pool, MLBM, "game_pwr", "hr_per600_career"), rng,
        "home runs per 600 MLB PA, career frame", 2,
        notes=["150 career PA floor. BA's stated framing is a career average, so "
               "this is the BA-comparable frame; FanGraphs says 'at maturity', "
               "which this frame understates for a young pool."])
    T["game_pwr__mlb_hr_per600_fullseason"] = build_table(
        pairs(mlb_pool, MLBM, "game_pwr", "hr_per600_fullseason"), rng,
        "home runs per 600 PA in the player's highest-PA MLB season", 2,
        notes=["350 PA floor on the season. Highest-PA season, not highest-HR "
               "season, so the rate is not selected on the outcome."])
    T["game_pwr__mlb_hr_per600_age26"] = build_table(
        pairs(mlb_pool, MLBM, "game_pwr", "hr_per600_age26"), rng,
        "home runs per 600 PA, age 26+ seasons only", 2,
        notes=["Closest stand-in for the published 'at maturity' frame."])
    T["game_pwr__mlb_barrel_bbe_pct"] = build_table(
        pairs(mlb_pool, MLBM, "game_pwr", "barrel_bbe_pct"), rng,
        "barrels per batted ball, percent, MLB", 2)
    T["game_pwr__mlb_barrel_pa_pct"] = build_table(
        pairs(mlb_pool, MLBM, "game_pwr", "barrel_pa_pct"), rng,
        "barrels per PA, percent, MLB", 2)
    T["game_pwr__aaa_iso"] = build_table(
        pairs(aaa_pool, AAAM, "game_pwr", "iso"), rng,
        "isolated power, upper minors", 3)
    T["game_pwr__aaa_barrel_pa_pct"] = build_table(
        pairs(aaa_pool, AAAM, "game_pwr", "barrel_pa_pct"), rng,
        "barrels per PA, percent, upper minors", 2)

    # ================= HIT ===============================================
    T["hit__mlb_avg_career"] = build_table(
        pairs(mlb_pool, MLBM, "hit", "avg_career"), rng,
        "MLB batting average, career frame", 3,
        notes=["150 career PA floor."])
    T["hit__mlb_avg_fullseason"] = build_table(
        pairs(mlb_pool, MLBM, "hit", "avg_fullseason"), rng,
        "MLB batting average in the player's highest-PA season", 3)
    T["hit__mlb_avg_age26"] = build_table(
        pairs(mlb_pool, MLBM, "hit", "avg_age26"), rng,
        "MLB batting average, age 26+ seasons only", 3)
    T["hit__mlb_xba"] = build_table(
        pairs(mlb_pool, MLBM, "hit", "xba"), rng,
        "MLB expected batting average", 3)
    T["hit__mlb_k_pct"] = build_table(
        pairs(mlb_pool, MLBM, "hit", "k_pct_career"), rng,
        "MLB strikeout rate, percent", 2, higher_is_better=False)
    T["hit__aaa_whiff_pct"] = build_table(
        pairs(aaa_pool, AAAM, "hit", "whiff_pct"), rng,
        "whiff per swing, percent, upper minors", 2, higher_is_better=False)
    T["hit__aaa_k_pct"] = build_table(
        pairs(aaa_pool, AAAM, "hit", "k_pct"), rng,
        "strikeout rate, percent, upper minors", 2, higher_is_better=False)
    T["hit__aaa_xba"] = build_table(
        pairs(aaa_pool, AAAM, "hit", "xba"), rng,
        "expected batting average, upper minors", 3)
    T["hit__aaa_xwoba"] = build_table(
        pairs(aaa_pool, AAAM, "hit", "xwoba"), rng,
        "expected wOBA, upper minors", 3)

    # ================= SPEED =============================================
    T["speed__mlb_sb_per600"] = build_table(
        pairs(mlb_pool, MLBM, "speed", "sb_per600_career"), rng,
        "stolen bases per 600 MLB PA, career frame", 2,
        notes=["PROXY, not a run time. No sprint speed, 60-yard or home-to-first "
               "measurement exists anywhere in this tree, so the FanGraphs and BA "
               "speed tables (both in seconds) are NOT auditable here."])
    T["speed__mlb_sb_per600_fullseason"] = build_table(
        pairs(mlb_pool, MLBM, "speed", "sb_per600_fullseason"), rng,
        "stolen bases per 600 PA in the highest-PA MLB season", 2)
    T["speed__mlb_sbatt_per600"] = build_table(
        pairs(mlb_pool, MLBM, "speed", "sbatt_per600_career"), rng,
        "stolen base attempts per 600 MLB PA", 2)
    T["speed__mlb_triples_per600"] = build_table(
        pairs(mlb_pool, MLBM, "speed", "triples_per600_career"), rng,
        "triples per 600 MLB PA", 2)
    T["speed__aaa_triples_per600"] = build_table(
        pairs(aaa_pool, AAAM, "speed", "triples_per_600"), rng,
        "triples per 600 PA, upper minors", 2)

    # ================= FIELD =============================================
    T["field__mlb_frp_fulltime"] = build_table(
        pairs(mlb_pool, MLBM, "field", "frp_fulltime"), rng,
        "Statcast fielding runs prevented, median full-time MLB season", 2,
        notes=["Full-time = 700+ innings at the OAA primary position "
               "(data/fielding_innings.json). Range/positioning only: catcher "
               "framing and throwing are outside OAA, and OAA has no 1B-specific "
               "or catcher-defence component here."])
    T["field__mlb_oaa_fulltime"] = build_table(
        pairs(mlb_pool, MLBM, "field", "oaa_fulltime"), rng,
        "outs above average, median full-time MLB season", 2)
    T["field__mlb_frp_per1000inn"] = build_table(
        pairs(mlb_pool, MLBM, "field", "frp_per1000inn"), rng,
        "fielding runs prevented per 1000 innings, MLB", 2)

    # ================= PITCHER FASTBALL ==================================
    def sp_only(rec, m):
        return m.get("role") == "SP"

    def rp_only(rec, m):
        return m.get("role") == "RP"

    T["fb__mlb_velo_first_sp"] = build_table(
        pairs(mlb_pool, MLBM, "fb", "fb_velo_first", sp_only), rng,
        "mph, MLB fastball velocity, first qualifying season, starters", 2,
        notes=["Savant arsenal fastball = max of the FF / SI / FC average "
               "velocities, so a two-fastball pitcher reads at his harder one. "
               "First season, not max, so the number is not inflated by career "
               "length. Role from career GS/G >= 0.50."])
    T["fb__mlb_velo_max_sp"] = build_table(
        pairs(mlb_pool, MLBM, "fb", "fb_velo_max", sp_only), rng,
        "mph, MLB fastball velocity, career max season, starters", 2)
    T["fb__mlb_velo_first_rp"] = build_table(
        pairs(mlb_pool, MLBM, "fb", "fb_velo_first", rp_only), rng,
        "mph, MLB fastball velocity, first qualifying season, relievers", 2)
    T["fb__mlb_velo_first_all"] = build_table(
        pairs(mlb_pool, MLBM, "fb", "fb_velo_first"), rng,
        "mph, MLB fastball velocity, first qualifying season, all roles", 2)
    T["fb__aaa_velo"] = build_table(
        pairs(aaa_pool, AAAM, "fb", "fb_velo_aaa"), rng,
        "mph, upper-minors primary fastball velocity", 2,
        notes=["Primary fastball = the highest-usage of FF / SI / FC in "
               "data/aaa_physics.json, so this is a single-pitch average, not "
               "the max-of-three the MLB arsenal column uses."])
    T["fb__aaa_astuff"] = build_table(
        pairs(aaa_pool, AAAM, "fb", "fb_astuff_aaa"), rng,
        "aStuff+ of the primary fastball, upper minors (100 = AAA average)", 2)
    T["fb__mlb_k_pct"] = build_table(
        pairs(mlb_pool, MLBM, "fb", "k_pct_career"), rng,
        "MLB strikeout rate, percent", 2)

    # ================= COMMAND / CONTROL =================================
    T["cmd__mlb_bb_pct_sp"] = build_table(
        pairs(mlb_pool, MLBM, "cmd", "bb_pct_career", sp_only), rng,
        "MLB walk rate, percent, starters", 2, higher_is_better=False,
        notes=["Sign inversion: a HIGHER command grade should read a LOWER walk "
               "rate, so a positive Spearman here would be a defect."])
    T["cmd__mlb_bb_pct_rp"] = build_table(
        pairs(mlb_pool, MLBM, "cmd", "bb_pct_career", rp_only), rng,
        "MLB walk rate, percent, relievers", 2, higher_is_better=False)
    T["cmd__aaa_bb_pct"] = build_table(
        pairs(aaa_pool, AAAM, "cmd", "bb_pct"), rng,
        "upper-minors walk rate, percent", 2, higher_is_better=False)

    # ================= SECONDARY PITCHES =================================
    for tool in ("sl", "cb", "ch"):
        T[f"{tool}__mlb_k_pct"] = build_table(
            pairs(mlb_pool, MLBM, tool, "k_pct_career"), rng,
            "MLB strikeout rate, percent", 2,
            notes=["Indirect: no per-pitch MLB shape measurement is joined here, "
                   "so this reads the pitch grade against a whole-arsenal "
                   "outcome."])
        T[f"{tool}__aaa_whiff_pct"] = build_table(
            pairs(aaa_pool, AAAM, tool, "whiff_pct"), rng,
            "whiff per swing, percent, upper minors, whole arsenal", 2)

    # ---- audits ----------------------------------------------------------
    A = {
        "fb_velo_sp": audit(T["fb__mlb_velo_first_sp"], "fb_velo_sp"),
        "fb_velo_sp_max": audit(T["fb__mlb_velo_max_sp"], "fb_velo_sp"),
        "fb_velo_rp": audit(T["fb__mlb_velo_first_rp"], "fb_velo_rp"),
        "hr_per600_career": audit(T["game_pwr__mlb_hr_per600_career"], "hr_per600"),
        "hr_per600_fullseason": audit(T["game_pwr__mlb_hr_per600_fullseason"],
                                      "hr_per600"),
        "hr_per600_age26": audit(T["game_pwr__mlb_hr_per600_age26"], "hr_per600"),
        "avg_career": audit(T["hit__mlb_avg_career"], "avg"),
        "avg_fullseason": audit(T["hit__mlb_avg_fullseason"], "avg"),
        "avg_age26": audit(T["hit__mlb_avg_age26"], "avg"),
        "sb_per_season": audit(T["speed__mlb_sb_per600_fullseason"], "sb_per_season"),
        "bb_pct_sp": audit(T["cmd__mlb_bb_pct_sp"], "bb_pct_sp", True),
        "bb_pct_rp": audit(T["cmd__mlb_bb_pct_rp"], "bb_pct_rp", True),
        "fielding_runs": audit(T["field__mlb_frp_fulltime"], "fielding_runs"),
    }

    # ---- context offsets, within player ----------------------------------
    def off(mkey_aaa, mkey_mlb, dec=2, side=None):
        """side: None = any, 'hit' = hitters only, 'pit' = pitchers only.
        The side filter is load-bearing for k_pct / bb_pct, where both sides
        carry the SAME key name and pooling them is meaningless."""
        pr = []
        for pid in set(AAAM) & set(MLBM):
            if side is not None:
                isp = (aaa_pool.get(pid) or {}).get("is_pitcher")
                if side == "pit" and not isp:
                    continue
                if side == "hit" and isp:
                    continue
            a = (AAAM.get(pid) or {}).get(mkey_aaa)
            b = (MLBM.get(pid) or {}).get(mkey_mlb)
            if a is not None and b is not None:
                pr.append((a, b))
        return context_offset(pr, rng, dec)

    CTX = {
        "ev_avg": off("ev_avg", "ev_avg", 2, "hit"),
        "hardhit_pct": off("hardhit_pct", "hardhit_pct", 2, "hit"),
        "barrel_bbe_pct": off("barrel_bbe_pct", "barrel_bbe_pct", 2, "hit"),
        "barrel_pa_pct": off("barrel_pa_pct", "barrel_pa_pct", 2, "hit"),
        "xba": off("xba", "xba", 3, "hit"),
        "xwoba": off("xwoba", "xwoba", 3, "hit"),
        "ba_vs_avg_career": off("ba", "avg_career", 3, "hit"),
        "k_pct_hitters": off("k_pct", "k_pct_career", 2, "hit"),
        "bb_pct_hitters": off("bb_pct", "bb_pct_career", 2, "hit"),
        "fb_velo": off("fb_velo_aaa", "fb_velo_first", 2, "pit"),
        "fb_velo_like_for_like": off("fb_velo_aaa_max3", "fb_velo_first", 2, "pit"),
        "k_pct_pitchers": off("k_pct", "k_pct_career", 2, "pit"),
        "bb_pct_pitchers": off("bb_pct", "bb_pct_career", 2, "pit"),
    }
    # the fastball-definition control: the MLB arsenal column is max(FF, SI, FC)
    # while our AAA primary fastball is the highest-USAGE of the three, so part
    # of the AAA-minus-MLB velocity offset is definitional, not contextual.
    defn = [(m.get("fb_velo_aaa_max3"), m.get("fb_velo_aaa")) for m in AAAM.values()
            if m.get("fb_velo_aaa_max3") is not None and m.get("fb_velo_aaa")
            is not None]
    CTX["_fb_definition_max3_minus_primary"] = context_offset(defn, rng)

    # ---- published-adjustment audit: the lefty and reliever deltas -------
    def grade_adjusted_contrast(pool, meas, tool, mkey, split_fn):
        """Mean measurement difference between two groups, matched on grade bin,
        so the contrast is not a grade-composition artifact."""
        by = defaultdict(lambda: defaultdict(list))
        for pid, rec in pool.items():
            g = _bin_grade((rec.get("tools") or {}).get(tool))
            m = meas.get(pid) or {}
            v = m.get(mkey)
            side = split_fn(rec, m)
            if g is None or v is None or side is None:
                continue
            by[g][side].append(v)
        diffs, wts, nA, nB = [], [], 0, 0
        labels = set()
        for g, blk in by.items():
            ks = sorted(blk)
            if len(ks) != 2:
                continue
            a, b = ks
            labels.add((a, b))
            if len(blk[a]) < 5 or len(blk[b]) < 5:
                continue
            w = min(len(blk[a]), len(blk[b]))
            diffs.append(statistics.median(blk[b]) - statistics.median(blk[a]))
            wts.append(w)
            nA += len(blk[a])
            nB += len(blk[b])
        if not diffs:
            return {"status": "no matched grade bins"}
        tot = sum(wts)
        return {"contrast": ("%s minus %s" % (sorted(labels)[0][1],
                                              sorted(labels)[0][0])
                             if labels else None),
                "grade_matched_mean_diff": round(
                    sum(d * w for d, w in zip(diffs, wts)) / tot, 3),
                "n_bins": len(diffs), "n_group_a": nA, "n_group_b": nB}

    ADJ = {
        "lefty_velocity_mlb": grade_adjusted_contrast(
            mlb_pool, MLBM, "fb", "fb_velo_first",
            lambda rec, m: m.get("throws") if m.get("throws") in ("L", "R") else None),
        "reliever_velocity_mlb": grade_adjusted_contrast(
            mlb_pool, MLBM, "fb", "fb_velo_first",
            lambda rec, m: m.get("role") if m.get("role") in ("SP", "RP") else None),
        "_published": {
            "lefty": "FanGraphs (Smith W2) and Baseball America both prescribe "
                     "subtracting 1 mph from every velocity threshold for "
                     "left-handers, i.e. LHP measured velocity should sit about "
                     "1 mph BELOW RHP at the same grade.",
            "reliever": "Baseball America prescribes adding 1 to 2 mph for "
                        "relievers; Smith W2's published reliever table sits 1 to "
                        "3 mph above his starter table. Both imply RP measured "
                        "velocity should sit 1 to 2 mph ABOVE SP at the same grade.",
            "caveat": "Our role split is REALIZED MLB usage (career GS/G), not the "
                      "role the grade was written for, so most of our RP group are "
                      "prospects scouted as starters who ended up in relief. That "
                      "population is velocity-selected downward relative to a "
                      "scouted reliever, and the contrast should be read as a "
                      "lower bound on the true role adjustment.",
        },
    }

    # ---- INV-1 measurement-implied grade ---------------------------------
    def implied_grade(table, value):
        """Invert a derived table: nearest solid cell median, linear between."""
        pts = sorted((int(g), c["median"]) for g, c in (table["cells"] or {}).items()
                     if not c["thin"] and c["median"] is not None)
        if len(pts) < 3 or value is None:
            return None
        asc = pts[-1][1] >= pts[0][1]
        seq = pts if asc else [(g, -v) for g, v in pts]
        val = value if asc else -value
        # enforce monotone medians by cumulative max so the inverse is a function
        mono = []
        run = None
        for g, v in seq:
            run = v if run is None else max(run, v)
            mono.append((g, run))
        if val <= mono[0][1]:
            return float(mono[0][0])
        if val >= mono[-1][1]:
            return float(mono[-1][0])
        for (g0, v0), (g1, v1) in zip(mono, mono[1:]):
            if v0 <= val <= v1:
                if v1 == v0:
                    return float(g0)
                return float(g0 + (g1 - g0) * (val - v0) / (v1 - v0))
        return None

    INV1_SPEC = [
        ("raw_pwr", "raw_pwr__mlb_ev_avg", MLBM, "ev_avg", mlb_pool),
        ("game_pwr", "game_pwr__mlb_hr_per600_fullseason", MLBM,
         "hr_per600_fullseason", mlb_pool),
        ("hit", "hit__mlb_avg_fullseason", MLBM, "avg_fullseason", mlb_pool),
        ("speed", "speed__mlb_sb_per600_fullseason", MLBM,
         "sb_per600_fullseason", mlb_pool),
        ("field", "field__mlb_frp_fulltime", MLBM, "frp_fulltime", mlb_pool),
        ("fb", "fb__mlb_velo_first_all", MLBM, "fb_velo_first", mlb_pool),
        ("cmd", "cmd__mlb_bb_pct_sp", MLBM, "bb_pct_career", mlb_pool),
        ("raw_pwr_aaa", "raw_pwr__aaa_ev_avg", AAAM, "ev_avg", aaa_pool),
        ("game_pwr_aaa", "game_pwr__aaa_barrel_pa_pct", AAAM,
         "barrel_pa_pct", aaa_pool),
        ("hit_aaa", "hit__aaa_k_pct", AAAM, "k_pct", aaa_pool),
        ("speed_aaa", "speed__aaa_triples_per600", AAAM,
         "triples_per_600", aaa_pool),
        ("fb_aaa", "fb__aaa_velo", AAAM, "fb_velo_aaa", aaa_pool),
        ("cmd_aaa", "cmd__aaa_bb_pct", AAAM, "bb_pct", aaa_pool),
    ]
    INV1 = {}
    implied_store = {}
    for label, tkey, meas, mkey, pool in INV1_SPEC:
        tool = label.replace("_aaa", "")
        gs, ims = [], []
        for pid, rec in pool.items():
            g = (rec.get("tools") or {}).get(tool)
            v = (meas.get(pid) or {}).get(mkey)
            if g is None or v is None:
                continue
            im = implied_grade(T[tkey], v)
            if im is None:
                continue
            gs.append(float(g))
            ims.append(im)
            implied_store.setdefault(label, {})[pid] = im
        if len(gs) < 20:
            INV1[label] = {"n": len(gs), "verdict": "NOT COMPUTABLE (n < 20)"}
            continue
        rho = _spearman(gs, ims)
        rlo, rhi = _boot_spearman_ci(gs, ims, rng)
        diff = [i - g for g, i in zip(gs, ims)]
        far = sum(1 for d in diff if abs(d) >= 10) / len(diff)
        ok_rho = rho is not None and 0.25 <= rho <= 0.85
        ok_far = 0.05 <= far <= 0.40
        INV1[label] = {
            "n": len(gs), "spearman_implied_vs_scout": round(rho, 4),
            "spearman_ci95": [rlo, rhi],
            "mean_implied_minus_scout": round(sum(diff) / len(diff), 3),
            "share_two_grades_apart": round(far, 4),
            "gate_rho_in_0.25_0.85": ok_rho,
            "gate_flagrate_in_5_40pct": ok_far,
            "verdict": "PASS" if (ok_rho and ok_far) else "FAIL",
        }

    # ---- INV-2 per-source drift index ------------------------------------
    # Per-source grades come from the prospects.db snapshot history, not from the
    # timeseries points: the points prune per_source tool blocks on old vintages
    # (only ~150 debuted players retain one), while the DB keeps 2011-2026.
    src_db = load_source_grades_db()

    def src_grade(player_key, source, tool, before=None):
        """Latest grade for (source, tool), optionally strictly before a date."""
        rows = ((src_db.get(player_key) or {}).get(source) or {}).get(tool) or []
        cand = [(d, g) for d, g in rows if not before or (d and d < before)]
        if not cand:
            return None
        return max(cand)[1]

    INV2 = {}
    SRC_SPEC = [
        # tool, implied-table label, pool, pre-date rule
        ("raw_pwr", "raw_pwr", mlb_pool, True),
        ("game_pwr", "game_pwr", mlb_pool, True),
        ("hit", "hit", mlb_pool, True),
        ("speed", "speed", mlb_pool, True),
        ("field", "field", mlb_pool, True),
        ("fb", "fb", mlb_pool, True),
        ("cmd", "cmd", mlb_pool, True),
        ("raw_pwr@aaa", "raw_pwr_aaa", aaa_pool, False),
        ("game_pwr@aaa", "game_pwr_aaa", aaa_pool, False),
        ("hit@aaa", "hit_aaa", aaa_pool, False),
        ("fb@aaa", "fb_aaa", aaa_pool, False),
        ("cmd@aaa", "cmd_aaa", aaa_pool, False),
    ]
    for spec_name, label, pool, pre in SRC_SPEC:
        tool = spec_name.split("@")[0]
        imp = implied_store.get(label) or {}
        if not imp:
            INV2[spec_name] = {"verdict": "NOT COMPUTABLE (no implied grades)"}
            continue
        by_src = defaultdict(list)
        paired = defaultdict(list)
        for pid, rec in pool.items():
            im = imp.get(pid)
            if im is None:
                continue
            pk = rec.get("player_key")
            before = rec.get("debut_date") if pre else None
            got = {}
            for source in ("fangraphs", "mlb_pipeline", "tjstats",
                           "just_baseball", "espn"):
                g = src_grade(pk, source, tool, before)
                if g is not None:
                    by_src[source].append(g - im)
                    got[source] = g
            if "fangraphs" in got and "mlb_pipeline" in got:
                paired["fangraphs_minus_pipeline"].append(
                    got["fangraphs"] - got["mlb_pipeline"])
        blk = {}
        for source, ds in sorted(by_src.items()):
            if len(ds) < 100:
                blk[source] = {
                    "n": len(ds),
                    "status": "below the 100-player floor, not computable",
                    "mean_drift": round(sum(ds) / len(ds), 3) if ds else None}
                continue
            lo, hi = _boot_mean_ci(ds, rng)
            blk[source] = {"n": len(ds), "mean_drift": round(sum(ds) / len(ds), 3),
                           "median_drift": round(statistics.median(ds), 3),
                           "ci95_mean": [lo, hi], "status": "computed"}
        usable = {s: v for s, v in blk.items() if v.get("status") == "computed"}
        verdict = "NOT COMPUTABLE (fewer than two sources above floor)"
        if len(usable) >= 2:
            items = sorted(usable.items(), key=lambda kv: kv[1]["mean_drift"])
            a, b = items[0], items[-1]
            gap = b[1]["mean_drift"] - a[1]["mean_drift"]
            sep = (a[1]["ci95_mean"][1] is not None
                   and b[1]["ci95_mean"][0] is not None
                   and a[1]["ci95_mean"][1] < b[1]["ci95_mean"][0])
            verdict = ("PASS" if (sep and abs(gap) >= 1.0) else "FAIL")
            blk["_contrast"] = {"low": a[0], "high": b[0],
                                "gap_grade_points": round(gap, 3),
                                "ci_disjoint": bool(sep),
                                "gate_gap_ge_1.0": bool(abs(gap) >= 1.0)}
        # paired head-to-head on the players BOTH outlets graded: removes the
        # population-composition confound the unpaired drift carries.
        for pname, ds in paired.items():
            if len(ds) < 30:
                blk["_paired_" + pname] = {"n": len(ds), "status": "thin"}
                continue
            lo, hi = _boot_mean_ci(ds, rng)
            blk["_paired_" + pname] = {
                "n": len(ds), "mean": round(sum(ds) / len(ds), 3),
                "median": round(statistics.median(ds), 3), "ci95_mean": [lo, hi],
                "excludes_zero": bool(lo is not None and hi is not None
                                      and (lo > 0 or hi < 0))}
        blk["verdict"] = verdict
        INV2[spec_name] = blk
    INV2["_baseballamerica"] = {
        "status": "NOT COMPUTABLE",
        "reason": "Baseball America contributes rank and FV to this tree but no "
                  "tool grades at all: zero BA tool rows across the whole "
                  "snapshot history. A BA drift index cannot be computed, so BA's "
                  "published bands can only be audited against our measurements, "
                  "never against BA's own grades."}

    # ---- INV-3 per-tool grade aging curves -------------------------------
    INV3 = {}
    deb_raw = json.loads((DATA / "debuts.json").read_text(encoding="utf-8"))
    ts_raw = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))
    hist = defaultdict(lambda: defaultdict(list))   # tool -> key -> [(date, grade)]
    for rec in list(deb_raw) + list(ts_raw.get("players") or []):
        pk = rec.get("player_key")
        for pt in (rec.get("points") or []):
            d = pt.get("snapshot_date")
            tc = pt.get("tools_consensus") or {}
            if not d:
                continue
            for tool, g in tc.items():
                gv = _f(g)
                if gv is not None:
                    hist[tool][pk].append((d, gv))
    for tool, byp in sorted(hist.items()):
        per_year = []
        n_ok = 0
        for pk, series in byp.items():
            s = sorted(set(series))
            if len(s) < 3:
                continue
            y0 = int(s[0][0][:4]) + (int(s[0][0][5:7]) - 1) / 12.0
            y1 = int(s[-1][0][:4]) + (int(s[-1][0][5:7]) - 1) / 12.0
            if y1 - y0 < 2.0:
                continue
            n_ok += 1
            per_year.append((s[-1][1] - s[0][1]) / (y1 - y0))
        if n_ok < 200:
            INV3[tool] = {"n_players": n_ok,
                          "status": "below the 200-player floor"}
            continue
        lo, hi = _boot_mean_ci(per_year, rng)
        INV3[tool] = {"n_players": n_ok,
                      "mean_grade_change_per_year": round(sum(per_year) / len(per_year), 3),
                      "median_grade_change_per_year": round(statistics.median(per_year), 3),
                      "ci95_mean": [lo, hi],
                      "excludes_zero": bool(lo is not None and hi is not None
                                            and (lo > 0 or hi < 0))}
    any_sig = any(v.get("excludes_zero") for v in INV3.values() if isinstance(v, dict))
    n_pass = sum(1 for v in INV3.values()
                 if isinstance(v, dict) and v.get("n_players", 0) >= 200)
    INV3["_verdict"] = ("PASS" if (n_pass >= 1 and any_sig) else "FAIL")

    payload = {
        "generated_at": "2026-07-30",
        "harness": "tools/tool_grade_tables_lab.py",
        "registration": "docs/efv-2026-07-30/TOOL_GRADE_TABLES.md section 1 "
                        "(written before the first table was fitted)",
        "contract": "DERIVED REFERENCE TABLES ONLY. No served number, no scoring "
                    "path, no consensus weight reads this artifact. Any such use "
                    "is a separate gated lane.",
        "method": {
            "grain": "one row per player; season values aggregated by "
                     "PA/BF/BBE weight before binning",
            "grade_binning": "nearest 5, clipped to [20, 80]; grade_mean carries "
                             "the unrounded bin centre",
            "thin_cell_floor": THIN_N,
            "bootstrap": {"resamples": BOOT, "seed": SEED,
                          "unit": "player", "interval": "95 percent percentile"},
            "floors": {"mlb_career_pa": MLB_PA_FLOOR,
                       "mlb_fullseason_pa": MLB_PA_FULLSEASON,
                       "mlb_career_bf": MLB_BF_FLOOR,
                       "mlb_season_bbe": MLB_BBE_FLOOR,
                       "aaa_season_pa": AAA_PA_FLOOR,
                       "fielding_fulltime_innings": FULLTIME_INN},
        },
        "pools": {
            "P_MLB": {"n": len(mlb_pool),
                      "grade_frame": "last pre-debut tools_consensus point",
                      "source": "data/debuts.json"},
            "P_AAA": {"n": len(aaa_pool),
                      "grade_frame": "latest tools_consensus point (actives), "
                                     "pre-debut point (debuted)",
                      "source": "data/timeseries.json + data/debuts.json"},
        },
        "tables": T,
        "audit_vs_published": A,
        "audit_published_adjustments": ADJ,
        "context_offset_aaa_minus_mlb": CTX,
        "inv1_measurement_implied_grade": INV1,
        "inv2_source_drift_index": INV2,
        "inv3_grade_aging": INV3,
        "no_measurement": {
            "throw": "No arm-strength observation exists anywhere in this tree: "
                     "no throw velocity, no catcher pop time, no outfield "
                     "assist-runs split. Baseball America's catcher pop-time table "
                     "is the only published arm scale in measured units and it is "
                     "unauditable here.",
            "pitch_sel": "No plate-discipline decomposition is joined at the "
                         "player-season grain in either context; BB% is a "
                         "consequence, not the tool.",
            "bat_ctrl": "No bat tracking for the minors (bat_speed and "
                        "swing_length are present as columns in the savant minors "
                        "export and empty in every row) and no MLB bat-tracking "
                        "join keyed to prospect grades.",
            "delivery": "Not a measured quantity; arm angle and extension exist "
                        "in data/aaa_physics.json but neither is what the grade "
                        "names.",
            "athl": "No measurement.",
            "frame": "Height and weight exist as FanGraphs extras; the grade is "
                     "not a height-weight function and no body-composition "
                     "measurement exists.",
            "speed_run_time": "PARTIAL. No sprint speed, no 60-yard time, no "
                              "home-to-first time anywhere in the tree, so both "
                              "published speed tables (seconds) are unauditable. "
                              "Stolen bases and triples are outcome proxies and "
                              "are reported as proxies.",
        },
    }

    # ---- report ----------------------------------------------------------
    print("POOLS  P-MLB %d graded players   P-AAA %d" % (len(mlb_pool), len(aaa_pool)))
    print()
    for name, t in T.items():
        solid = t["n_solid_cells"]
        print("%-38s n=%-5d rho=%-8s solid=%-2d sd/10g=%-7s %s" % (
            name, t["n_players"],
            "n/a" if t["spearman_grade_vs_measure"] is None
            else "%.3f" % t["spearman_grade_vs_measure"], solid,
            t["sd_per_10_grade_ratio"], t["unit"]))
    print()
    print("=== DESCRIPTIVE-ONLY TABLES (|rho| < 0.20) ===")
    for name, t in T.items():
        if t["signal_verdict"].startswith("DESCRIPTIVE"):
            print("   %-38s rho=%s" % (name, t["spearman_grade_vs_measure"]))
    print()
    for name, t in T.items():
        if t["n_solid_cells"] < 2:
            continue
        print("== %s  [%s]  rho %.3f %s" % (
            name, t["unit"], t["spearman_grade_vs_measure"] or 0.0,
            t["spearman_ci95"]))
        for g in sorted(t["cells"], key=lambda x: int(x)):
            c = t["cells"][g]
            print("   %2s n=%-4d med=%-8s IQR %s-%s  CI %s%s" % (
                g, c["n"], c["median"], c["p25"], c["p75"],
                c["ci95_median"], "  THIN" if c["thin"] else ""))
        print()
    print("=== AUDIT ===")
    for key, blk in A.items():
        print("-- %s  [%s]" % (key, blk["published_unit"]))
        for r in blk["rows"]:
            if r.get("grade") is None:
                print("   %-22s %s" % (r["outlet"], r["status"]))
                continue
            if r["status"].startswith("no measured") or "thin" in r["status"]:
                continue
            print("   %-22s g=%-3s pub=%-14s ours=%-9s gap=%-8s %s" % (
                r["outlet"], r["grade"], r["published"], r["ours"],
                r.get("gap_ours_minus_theirs"), r["status"]))
        for outlet, s in (blk.get("slope_comparison") or {}).items():
            if s.get("status"):
                continue
            print("   SLOPE %-16s pub/10g=%-8s ours/10g=%-8s ratio=%s" % (
                outlet, s["published_per_10_grade"], s["ours_per_10_grade"],
                s["ours_over_published"]))
        print()
    print("=== PUBLISHED-ADJUSTMENT AUDIT ===")
    for k, v in ADJ.items():
        if k.startswith("_"):
            continue
        print("   %-24s %s" % (k, json.dumps(v)))
    print()
    print("=== CONTEXT OFFSET (AAA minus MLB, within player) ===")
    for k, v in CTX.items():
        print("   %-20s n=%-5d mean=%-9s median=%-9s CI %s  usable=%s" % (
            k, v["n"], v["mean"], v["median"], v.get("ci95_mean"), v["usable"]))
    print()
    print("=== INV-1 measurement-implied grade ===")
    for k, v in INV1.items():
        print("   %-14s %s" % (k, json.dumps(v)))
    print()
    print("=== INV-2 source drift ===")
    for k, v in INV2.items():
        print("   %-14s %s" % (k, json.dumps(v)))
    print()
    print("=== INV-3 grade aging ===")
    for k, v in INV3.items():
        print("   %-14s %s" % (k, json.dumps(v)))

    if args.write:
        OUT_PATH.write_text(json.dumps(payload, indent=1, sort_keys=False),
                            encoding="utf-8")
        print("\nwrote %s" % OUT_PATH)
    return payload


if __name__ == "__main__":
    main()
