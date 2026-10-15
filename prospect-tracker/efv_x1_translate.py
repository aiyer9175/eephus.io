# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV_X1_MLE_TRANSLATION: the MLE translation and reliability layer (owner decision EW3-12,
2026-10-15), built to the registration docs/efv-v2/EFV_X1_MLE_TRANSLATION.md, which was
committed alone before this module computed anything.

THREE PARTS.
  (a) translation  every affiliated season line 2005 to 2026 (MEX dropped, 2020 skipped)
                   to its MLB equivalent per stat, by a Poisson fixed-effects fit of
                   E[n] = d * pi * theta_player * lambda_league over one season's lines
                   (MLB included, lambda_MLB = 1): the chained same-player method, each
                   league's factor identified by the players seen in another league the
                   same season. pi is the team factor (two-sided team method, the
                   registration's recorded deviation for the park leg).
  (b) reliability  each translated player-season rate shrunk toward its level-and-age
                   prior by n / (n + k), k the stat's stabilization point from a method
                   of moments over the prior window (the five played seasons ending at T).
  (c) trajectory   per frame row: Marcel-weighted (5, 4, 3) reliability-weighted rates
                   over the last three played seasons, the year-over-year change and age
                   relative to level.

AS OF. Season s's league factors read season s only; the team factor reads s - 2 to s;
the constants of reference season T read the seasons at or before T; a row read at year
Y as of a cutoff reads only seasons that ended (1 October) by its read
(efv_w2_milb.last_readable_season), and features() asserts it on every season it reads.

THE READ (--dev-read). Descriptive, lv_dev and vm_dev only, through
tools/efv_v2_model_class_screen.build_inputs (its scored rows): per feature, the within
(side, vintage) Spearman of a leave-one-year-out ridge of the label percentile on the
consensus percentile plus the feature, minus consensus's, with the paired player-clustered
E_cond CI95 (efv_v2_stat.paired_delta, B 2000, seed 20261018) and a permuted twin. It
writes data/_labs/efv_x1/efv_x1_translate.json and nothing else; it selects and ships
nothing. R-LV and R-VM are never opened.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only strata are side, season, year,
league, level, team and integer age. Nothing here groups, counts or averages rows by
consensus-FV level. No served module imports this one.

Run:  python efv_x1_fetch.py               (the cache, once)
      python efv_x1_translate.py --factors (constants and diagnostics only)
      python efv_x1_translate.py --dev-read (the registered development read)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

import efv_x1_fetch as X

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv_x1"
OUT_PATH = LAB_DIR / "efv_x1_translate.json"
TOOL = "efv_x1_translate.py"
ITEM = "EFV_X1_MLE_TRANSLATION"
REGISTRATION_DOC = "docs/efv-v2/EFV_X1_MLE_TRANSLATION.md"

SIDES = ("hit", "pit")
GROUP = {"hit": "hitting", "pit": "pitching"}
SEASONS: tuple[int, ...] = X.SEASONS
MINOR_SPORTS: tuple[int, ...] = tuple(s for s in X.SPORTS if s != 1)
MLB = "MLB"
DROP_LEAGUES = frozenset({"MEX"})
LEVEL_RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5, "MLB": 6}
LEVELS_UP = ("DSL", "CPX", "A", "A+", "AA", "AAA")

STATS: dict[str, tuple[str, ...]] = {"hit": ("k", "bb", "iso", "babip", "obp", "woba"),
                                     "pit": ("k", "bb", "hr9", "gb")}
#: kind of per-unit sampling variance: proportion p(1 - p), poisson (the rate), or moment
#: (the line's own second moment minus its squared mean).
VAR_KIND = {("hit", "k"): "prop", ("hit", "bb"): "prop", ("hit", "iso"): "moment",
            ("hit", "babip"): "prop", ("hit", "obp"): "prop", ("hit", "woba"): "moment",
            ("pit", "k"): "prop", ("pit", "bb"): "prop", ("pit", "hr9"): "poisson",
            ("pit", "gb"): "prop"}
#: wOBA weights, FanGraphs scale, fixed (registration s3).
WOBA_W = {"ubb": 0.69, "hbp": 0.72, "b1": 0.89, "b2": 1.27, "b3": 1.62, "hr": 2.10}

MIN_LINK = 15
MAX_ITER = 200
TOL = 1e-9
PARK_WINDOW = 3
PARK_MIN_PAIRS = 30
PRIOR_WINDOW = 5
PRIOR_MIN_CELL = 30
K_MIN_EXPOSURE = 100
AGE_CLIP = (17, 30)
MARCEL = (5.0, 4.0, 3.0)
WINDOW_SEASONS = 3
SEASON_END_MMDD = "-10-01"

FOLD_SEED = 20261018
BOOT_SEED = 20261018
TWIN_SEED = 20261019
B_DEFAULT = 2000
RIDGE_ALPHA = 1.0
MIN_GROUP_ROWS = 20


# ---------------------------------------------------------------------------
# lines
# ---------------------------------------------------------------------------

def _n(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


def _outs(row: dict) -> float:
    if row.get("outs") is not None:
        return _n(row.get("outs"))
    whole, _, frac = str(row.get("ip") or "0").partition(".")
    try:
        return float(int(whole or 0) * 3 + (int(frac[:1]) if frac else 0))
    except ValueError:
        return 0.0


def stat_counts(row: dict, side: str) -> dict:
    """{stat: (numerator, denominator, sum of squares or None)} for one line, from
    counts. A stat whose denominator is not positive is absent."""
    g = row.get
    out: dict = {}
    if side == "hit":
        pa, ab, h = _n(g("pa")), _n(g("ab")), _n(g("h"))
        d2, d3, hr = _n(g("doubles")), _n(g("triples")), _n(g("hr"))
        bb, ibb, hbp, sf, so = _n(g("bb")), _n(g("ibb")), _n(g("hbp")), _n(g("sf")), _n(g("so"))
        b1 = max(h - d2 - d3 - hr, 0.0)
        if pa > 0:
            out["k"] = (so, pa, None)
            out["bb"] = (bb, pa, None)
        if ab > 0:
            xb = d2 + 2.0 * d3 + 3.0 * hr
            out["iso"] = (xb, ab, d2 + 4.0 * d3 + 9.0 * hr)
        bip = ab - so - hr + sf
        if bip > 0:
            out["babip"] = (max(h - hr, 0.0), bip, None)
        od = ab + bb + hbp + sf
        if od > 0:
            out["obp"] = (h + bb + hbp, od, None)
        wd = ab + bb - ibb + sf + hbp
        if wd > 0:
            ubb = max(bb - ibb, 0.0)
            w = WOBA_W
            num = (w["ubb"] * ubb + w["hbp"] * hbp + w["b1"] * b1 + w["b2"] * d2
                   + w["b3"] * d3 + w["hr"] * hr)
            sq = (w["ubb"] ** 2 * ubb + w["hbp"] ** 2 * hbp + w["b1"] ** 2 * b1
                  + w["b2"] ** 2 * d2 + w["b3"] ** 2 * d3 + w["hr"] ** 2 * hr)
            out["woba"] = (num, wd, sq)
        return out
    bf = _n(g("bf"))
    if bf > 0:
        out["k"] = (_n(g("so")), bf, None)
        out["bb"] = (_n(g("bb")), bf, None)
    outs = _outs(row)
    if outs > 0:
        out["hr9"] = (_n(g("hr")), outs / 27.0, None)
    go, ao = _n(g("go")), _n(g("ao"))
    if go + ao > 0:
        out["gb"] = (go, go + ao, None)
    return out


def exposure(row: dict, side: str) -> float:
    return _n(row.get("pa")) if side == "hit" else _n(row.get("bf"))


def league_key(row: dict) -> str:
    if int(row.get("sport") or 0) == 1:
        return MLB
    return f"{row.get('level')}|{row.get('league') or ''}"


@lru_cache(maxsize=None)
def season_lines(season: int, side: str) -> tuple:
    """Every line of the season (MLB first), MEX dropped: tuple of dicts with mlbam,
    league key, level, team, num_teams, age, exposure and the stat counts."""
    out = []
    for sport in X.SPORTS:
        for r in X.load("players", GROUP[side], sport, int(season)):
            if not r.get("mlbam") or (r.get("league") or "") in DROP_LEAGUES:
                continue
            if int(sport) != 1 and r.get("level") not in LEVEL_RANK:
                continue
            e = exposure(r, side)
            if e <= 0:
                continue
            out.append({"mlbam": int(r["mlbam"]), "lg": league_key(r),
                        "level": MLB if int(sport) == 1 else r.get("level"),
                        "team": r.get("team_id"), "nt": int(r.get("num_teams") or 1),
                        "age": r.get("age"), "exp": e, "c": stat_counts(r, side)})
    return tuple(out)


def dropped_counts() -> dict:
    """{season: {side: MEX lines dropped}} (the registration's disclosure)."""
    out: dict = {}
    for s in SEASONS:
        for side in SIDES:
            n = sum(1 for sport in MINOR_SPORTS
                    for r in X.load("players", GROUP[side], sport, s)
                    if (r.get("league") or "") in DROP_LEAGUES)
            if n:
                out.setdefault(str(s), {})[side] = n
    return out


# ---------------------------------------------------------------------------
# team (park) factors: two-sided team method, regressed by year-over-year r
# ---------------------------------------------------------------------------

def _team_counts(row: dict, side: str, stat: str, batting: bool) -> tuple | None:
    """(num, den) of a team's batting line or pitching-allowed line for one stat. A
    pitcher stat reads per batter on both sides (HR/9 as HR per batter: the batting line
    has no outs); a hitter stat on the pitching line reads batters faced as PA."""
    if side == "pit":
        if stat == "gb":
            go, ao = _n(row.get("go")), _n(row.get("ao"))
            return (go, go + ao) if go + ao > 0 else None
        den = _n(row.get("pa")) if batting else _n(row.get("bf"))
        key = {"k": "so", "bb": "bb", "hr9": "hr"}[stat]
        return (_n(row.get(key)), den) if den > 0 else None
    r = row if batting else dict(row, pa=row.get("bf"))
    v = stat_counts(r, "hit").get(stat)
    return (v[0], v[1]) if v else None


@lru_cache(maxsize=None)
def team_league(season: int) -> dict:
    """{team id: league key} for the season, read off the single-team player lines (the
    team feed carries no league); MEX teams map to None."""
    votes: dict = {}
    for sport in X.SPORTS:
        for grp in X.GROUPS:
            for r in X.load("players", grp, sport, int(season)):
                if r.get("team_id") is None or int(r.get("num_teams") or 1) != 1:
                    continue
                lk = (None if (r.get("league") or "") in DROP_LEAGUES else league_key(r))
                v = votes.setdefault(int(r["team_id"]), {})
                v[lk] = v.get(lk, 0) + 1
    return {t: max(v.items(), key=lambda kv: (kv[1], str(kv[0])))[0] for t, v in votes.items()}


@lru_cache(maxsize=None)
def team_logs(season: int, side: str, stat: str) -> dict:
    """{team id: log two-sided factor, single season, relative to its league}."""
    acc: dict = {}
    for sport in X.SPORTS:
        for batting, grp in ((True, "hitting"), (False, "pitching")):
            for r in X.load("teams", grp, sport, int(season)):
                if r.get("team_id") is None:
                    continue
                lk = MLB if int(sport) == 1 else team_league(int(season)).get(int(r["team_id"]))
                if lk is None:
                    continue
                nd = _team_counts(r, side, stat, batting)
                if not nd or nd[1] <= 0:
                    continue
                a = acc.setdefault(int(r["team_id"]), {"lk": lk})
                a["bat" if batting else "pit"] = nd
    lg: dict = {}
    for tid, a in acc.items():
        lk = a["lk"]
        for part in ("bat", "pit"):
            if part not in a:
                continue
            nd = a[part]
            s = lg.setdefault((lk, part), [0.0, 0.0])
            s[0] += nd[0]
            s[1] += nd[1]
    out = {}
    for tid, a in acc.items():
        lk = a["lk"]
        if "bat" not in a or "pit" not in a:
            continue
        logs = []
        for part in ("bat", "pit"):
            n, d = a[part]
            ln, ld = lg[(lk, part)]
            if n <= 0 or ln <= 0 or ld <= 0:
                break
            logs.append(math.log((n / d) / (ln / ld)))
        if len(logs) == 2:
            out[tid] = 0.5 * (logs[0] + logs[1])
    return out


@lru_cache(maxsize=None)
def park_r(season: int, side: str, stat: str) -> dict:
    """The year-over-year correlation of the single-season two-sided log factor of the
    same team id over consecutive played seasons at or before `season`."""
    xs, ys = [], []
    played = [s for s in SEASONS if s <= int(season)]
    for a, b in zip(played, played[1:]):
        if b - a != 1:
            continue
        la, lb = team_logs(a, side, stat), team_logs(b, side, stat)
        for k, v in la.items():
            if k in lb:
                xs.append(v)
                ys.append(lb[k])
    if len(xs) < PARK_MIN_PAIRS:
        return {"r": 0.0, "pairs": len(xs), "status": "too few pairs; no park adjustment"}
    r = float(np.corrcoef(xs, ys)[0, 1])
    return {"r": max(r, 0.0), "r_raw": r, "pairs": len(xs)}


@lru_cache(maxsize=None)
def park_factors(season: int, side: str, stat: str) -> dict:
    """{team id: pi} for the season: the mean single-season log factor over seasons
    s - 2 .. s of the same team id, times r, exponentiated."""
    r = park_r(int(season), side, stat)["r"]
    win = [s for s in SEASONS if int(season) - PARK_WINDOW < s <= int(season)]
    acc: dict = {}
    for s in win:
        for k, v in team_logs(s, side, stat).items():
            a = acc.setdefault(k, [0.0, 0])
            a[0] += v
            a[1] += 1
    return {k: math.exp(r * a[0] / a[1]) for k, a in acc.items() if a[1]}


# ---------------------------------------------------------------------------
# league factors: Poisson fixed effects, the chained same-player method
# ---------------------------------------------------------------------------

def _connected_ok(lgs: list[str], pairs: dict) -> set[str]:
    """Leagues connected to MLB through shared players."""
    adj: dict = {g: set() for g in lgs}
    for (a, b), n in pairs.items():
        if n > 0 and a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    seen, stack = set(), [MLB] if MLB in adj else []
    while stack:
        g = stack.pop()
        if g in seen:
            continue
        seen.add(g)
        stack.extend(adj[g] - seen)
    return seen


def fit_league_factors(lines, stat: str, park: dict | None = None,
                       exclude_players: frozenset = frozenset()) -> dict:
    """{"lambda": {league: factor}, "links": {league: linking players}, "identified": set,
    "iterations": int} for one season's lines and one stat. lambda_MLB = 1."""
    park = park or {}
    rows = []
    for ln in lines:
        c = ln["c"].get(stat)
        if c is None or ln["mlbam"] in exclude_players:
            continue
        pi = park.get(ln["team"], 1.0) if ln["nt"] == 1 and ln["team"] else 1.0
        rows.append((ln["mlbam"], ln["lg"], c[0], c[1] * pi))
    by_p: dict = {}
    for pid, lg, _n_, _d in rows:
        by_p.setdefault(pid, set()).add(lg)
    active = {lg for _p, lg, _n_, _d in rows}
    # iteratively drop leagues with too few linking players
    while True:
        links: dict = {g: 0 for g in active}
        pairs: dict = {}
        for pid, lgs in by_p.items():
            lgs2 = sorted(lgs & active)
            if len(lgs2) < 2:
                continue
            for g in lgs2:
                links[g] += 1
            for i, a in enumerate(lgs2):
                for b in lgs2[i + 1:]:
                    pairs[(a, b)] = pairs.get((a, b), 0) + 1
        keep = {g for g in active if links[g] >= MIN_LINK or g == MLB}
        keep &= _connected_ok(sorted(keep), pairs)
        if keep == active:
            break
        active = keep
    all_links: dict = {}
    for pid, lgs in by_p.items():
        if len(lgs) >= 2:
            for g in lgs:
                all_links[g] = all_links.get(g, 0) + 1
    lam = {g: 1.0 for g in active}
    fit = [(p, g, n, d) for p, g, n, d in rows if g in active and len(by_p[p] & active) >= 2]
    it = 0
    if fit and MLB in active:
        pids = sorted({p for p, _g, _n_, _d in fit})
        gl = sorted(active)
        pix = {p: i for i, p in enumerate(pids)}
        gix = {g: i for i, g in enumerate(gl)}
        P = np.array([pix[p] for p, _g, _n_, _d in fit])
        G = np.array([gix[g] for _p, g, _n_, _d in fit])
        N = np.array([n for _p, _g, n, _d in fit], dtype=np.float64)
        D = np.array([d for _p, _g, _n_, d in fit], dtype=np.float64)
        npl, ngl = len(pids), len(gl)
        num_p = np.bincount(P, N, npl)
        num_g = np.bincount(G, N, ngl)
        L = np.ones(ngl)
        mlb = gix[MLB]
        for it in range(1, MAX_ITER + 1):
            den_p = np.bincount(P, D * L[G], npl)
            th = np.divide(num_p, den_p, out=np.zeros(npl), where=den_p > 0)
            den_g = np.bincount(G, D * th[P], ngl)
            L_new = np.divide(num_g, den_g, out=L.copy(), where=den_g > 0)
            if L_new[mlb] > 0:
                L_new = L_new / L_new[mlb]
            ch = float(np.max(np.abs(L_new - L) / np.maximum(L, 1e-12)))
            L = L_new
            if ch < TOL:
                break
        lam = {g: float(L[gix[g]]) for g in gl}
    return {"lambda": lam, "links": all_links, "identified": set(active), "iterations": it}


@lru_cache(maxsize=None)
def season_fit(season: int, side: str, stat: str) -> dict:
    """The season's fixed-effects fit (memoized; the fallback history reads it too)."""
    return fit_league_factors(season_lines(int(season), side), stat,
                              park_factors(int(season), side, stat))


@lru_cache(maxsize=None)
def league_table(season: int, side: str, stat: str) -> dict:
    """{league: {"lambda", "links", "identified", "level", "pooled"}} for every league of
    the season, with the registration's fallback for an unidentified league."""
    lines = season_lines(int(season), side)
    park = park_factors(int(season), side, stat)
    f = season_fit(int(season), side, stat)
    pooled: dict = {}
    level_of: dict = {}
    for ln in lines:
        c = ln["c"].get(stat)
        if c is None:
            continue
        pi = park.get(ln["team"], 1.0) if ln["nt"] == 1 and ln["team"] else 1.0
        a = pooled.setdefault(ln["lg"], [0.0, 0.0])
        a[0] += c[0]
        a[1] += c[1] * pi
        level_of[ln["lg"]] = ln["level"]
    out = {}
    for g, (n, d) in pooled.items():
        out[g] = {"level": level_of[g], "pooled": (n / d) if d > 0 else None,
                  "links": f["links"].get(g, 0), "identified": g in f["identified"],
                  "lambda": f["lambda"].get(g), "den": d}
    # fallback: difficulty = lambda / pooled
    diff_level: dict = {}
    for lv in LEVELS_UP:
        num = den = 0.0
        for g, t in out.items():
            if t["level"] == lv and t["identified"] and t["pooled"] and t["lambda"]:
                num += (t["lambda"] / t["pooled"]) * t["den"]
                den += t["den"]
        if den > 0:
            diff_level[lv] = num / den
    for i, lv in enumerate(LEVELS_UP):
        if lv in diff_level:
            continue
        hist = level_difficulty_history(int(season), side, stat).get(lv)
        if hist is not None:
            diff_level[lv] = hist
            continue
        for up in LEVELS_UP[i + 1:]:
            if up in diff_level:
                diff_level[lv] = diff_level[up]
                break
    for g, t in out.items():
        if g == MLB:
            t["lambda"] = 1.0
            continue
        if not t["identified"] or not t["lambda"]:
            dl = diff_level.get(t["level"])
            t["lambda"] = (dl * t["pooled"]) if (dl and t["pooled"]) else None
            t["fallback"] = True
    return out


@lru_cache(maxsize=None)
def level_difficulty_history(season: int, side: str, stat: str) -> dict:
    """{level: den-weighted mean difficulty over EARLIER seasons where identified}."""
    acc: dict = {}
    for s in SEASONS:
        if s >= int(season):
            break
        lines = season_lines(s, side)
        park = park_factors(s, side, stat)
        f = season_fit(s, side, stat)
        pooled: dict = {}
        level_of: dict = {}
        for ln in lines:
            c = ln["c"].get(stat)
            if c is None:
                continue
            pi = park.get(ln["team"], 1.0) if ln["nt"] == 1 and ln["team"] else 1.0
            a = pooled.setdefault(ln["lg"], [0.0, 0.0])
            a[0] += c[0]
            a[1] += c[1] * pi
            level_of[ln["lg"]] = ln["level"]
        for g in f["identified"]:
            if g == MLB or g not in pooled:
                continue
            n, d = pooled[g]
            if n <= 0 or d <= 0:
                continue
            a = acc.setdefault(level_of[g], [0.0, 0.0])
            a[0] += f["lambda"][g] / (n / d) * d
            a[1] += d
    return {lv: a[0] / a[1] for lv, a in acc.items() if a[1] > 0}


@lru_cache(maxsize=None)
def mlb_rate(season: int, side: str, stat: str) -> float | None:
    n = d = 0.0
    for ln in season_lines(int(season), side):
        if ln["lg"] != MLB:
            continue
        c = ln["c"].get(stat)
        if c:
            n += c[0]
            d += c[1]
    return n / d if d > 0 else None


# ---------------------------------------------------------------------------
# player-seasons on the MLB scale (MiLB lines only)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def player_seasons(season: int, side: str) -> dict:
    """{mlbam: {"exp", "level", "age", "stats": {stat: (x_season_env, n, var_unit)}}}
    over the season's MiLB lines: x is the MLB-equivalent rate in season s's MLB
    environment, n the raw denominator, var_unit the per-unit sampling variance on the
    translated scale."""
    lines = season_lines(int(season), side)
    tabs = {st: league_table(int(season), side, st) for st in STATS[side]}
    parks = {st: park_factors(int(season), side, st) for st in STATS[side]}
    acc: dict = {}
    for ln in lines:
        if ln["lg"] == MLB:
            continue
        a = acc.setdefault(ln["mlbam"], {"exp": 0.0, "lv": {}, "age": None, "age_e": -1.0,
                                         "s": {}})
        a["exp"] += ln["exp"]
        a["lv"][ln["level"]] = a["lv"].get(ln["level"], 0.0) + ln["exp"]
        if ln["age"] is not None and ln["exp"] > a["age_e"]:
            a["age"], a["age_e"] = ln["age"], ln["exp"]
        for st, c in ln["c"].items():
            lam = (tabs[st].get(ln["lg"]) or {}).get("lambda")
            if not lam:
                continue
            pi = (parks[st].get(ln["team"], 1.0)
                  if ln["nt"] == 1 and ln["team"] else 1.0)
            s = a["s"].setdefault(st, [0.0, 0.0, 0.0, 0.0])
            s[0] += c[0]
            s[1] += c[1]
            s[2] += c[1] * pi * lam
            s[3] += c[2] if c[2] is not None else 0.0
    out = {}
    for pid, a in acc.items():
        lv = max(a["lv"].items(), key=lambda kv: (kv[1], LEVEL_RANK.get(kv[0], -1)))[0]
        stats = {}
        for st, (n, d, dd, sq) in a["s"].items():
            if d <= 0 or dd <= 0:
                continue
            raw = n / d
            x = n / dd
            f = d / dd
            kind = VAR_KIND[(side, st)]
            if kind == "prop":
                vu = raw * (1.0 - raw)
            elif kind == "poisson":
                vu = raw
            else:
                vu = max(sq / d - raw * raw, 0.0)
            stats[st] = (x, d, vu * f * f)
        try:
            age = int(a["age"]) if a["age"] is not None else None
        except (TypeError, ValueError):
            age = None
        out[pid] = {"exp": a["exp"], "level": lv, "age": age, "stats": stats}
    return out


def clear_caches() -> None:
    """Drop every memoized table (the tests re-read with later seasons hidden)."""
    for fn in (season_lines, team_league, team_logs, park_r, park_factors, season_fit,
               league_table,
               level_difficulty_history, mlb_rate, player_seasons, constants,
               level_mean_age):
        fn.cache_clear()


def env_scale(season: int, ref: int, side: str, stat: str) -> float:
    a, b = mlb_rate(int(season), side, stat), mlb_rate(int(ref), side, stat)
    return (b / a) if (a and b) else 1.0


def _played_window(T: int, n: int) -> list[int]:
    out, s = [], int(T)
    while len(out) < n and s >= SEASONS[0]:
        if s in SEASONS:
            out.append(s)
        s -= 1
    return out


def _cell(ps: dict) -> tuple:
    age = ps.get("age")
    a = None if age is None else min(max(int(age), AGE_CLIP[0]), AGE_CLIP[1])
    return (ps["level"], a)


# ---------------------------------------------------------------------------
# the reliability layer
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def constants(T: int, side: str) -> dict:
    """{stat: {"k", "tau2", "mean_var_unit", "n_rows", "mu_cell", "mu_level"}} over the
    PRIOR_WINDOW played seasons ending at T, every rate in T's MLB environment."""
    win = _played_window(int(T), PRIOR_WINDOW)
    out = {}
    for st in STATS[side]:
        rows = []
        for s in win:
            sc = env_scale(s, int(T), side, st)
            for ps in player_seasons(s, side).values():
                v = ps["stats"].get(st)
                if v is None:
                    continue
                rows.append((_cell(ps), ps["level"], v[0] * sc, v[1], v[2] * sc * sc,
                             ps["exp"]))
        cell: dict = {}
        lvl: dict = {}
        for c, lv, x, n, _vu, _e in rows:
            a = cell.setdefault(c, [0.0, 0.0, 0])
            a[0] += x * n
            a[1] += n
            a[2] += 1
            b = lvl.setdefault(lv, [0.0, 0.0])
            b[0] += x * n
            b[1] += n
        mu_level = {lv: a[0] / a[1] for lv, a in lvl.items() if a[1] > 0}
        mu_cell = {c: a[0] / a[1] for c, a in cell.items()
                   if a[1] > 0 and a[2] >= PRIOR_MIN_CELL}
        res, vs, vus = [], [], []
        for c, lv, x, n, vu, e in rows:
            if e < K_MIN_EXPOSURE or n <= 0:
                continue
            mu = mu_cell.get(c, mu_level.get(lv))
            if mu is None:
                continue
            res.append((x - mu) ** 2)
            vs.append(vu / n)
            vus.append(vu)
        tau2 = (float(np.mean(res)) - float(np.mean(vs))) if res else None
        mvu = float(np.mean(vus)) if vus else None
        k = (mvu / tau2) if (tau2 is not None and tau2 > 0 and mvu is not None) else None
        out[st] = {"k": k, "tau2": tau2, "mean_var_unit": mvu, "n_rows": len(res),
                   "seasons": win, "mu_cell": mu_cell, "mu_level": mu_level}
    return out


def shrink(x: float, n: float, k: float | None, mu: float | None) -> float:
    """(n x + k mu) / (n + k); unshrunk when k is undefined or mu is missing."""
    if k is None or mu is None or k <= 0:
        return x
    return (n * x + k * mu) / (n + k)


def reliability(n: float, k: float | None) -> float:
    if k is None or k <= 0:
        return 1.0
    return n / (n + k)


def _prior(cst: dict, ps: dict) -> float | None:
    return cst["mu_cell"].get(_cell(ps), cst["mu_level"].get(ps["level"]))


@lru_cache(maxsize=None)
def level_mean_age(season: int, side: str) -> dict:
    acc: dict = {}
    for ln in season_lines(int(season), side):
        if ln["lg"] == MLB or ln["age"] is None:
            continue
        try:
            age = float(ln["age"])
        except (TypeError, ValueError):
            continue
        a = acc.setdefault(ln["level"], [0.0, 0.0])
        a[0] += age * ln["exp"]
        a[1] += ln["exp"]
    return {lv: a[0] / a[1] for lv, a in acc.items() if a[1] > 0}


# ---------------------------------------------------------------------------
# the trajectory features of one frame row
# ---------------------------------------------------------------------------

def feature_names(side: str) -> tuple[str, ...]:
    rw = tuple(f"{st}_rw" for st in STATS[side])
    if side == "pit":
        rw += ("kbb_rw",)
    return rw + tuple(f"{st}_yoy" for st in STATS[side]) + ("age_rel_level",)


def top_season(read_year: int, cutoff: str | None) -> int:
    from efv_w2_milb import last_readable_season
    T = last_readable_season(int(read_year), cutoff)
    while T not in SEASONS and T >= SEASONS[0]:
        T -= 1
    return T


def asof_date(read_year: int, cutoff: str | None) -> str:
    return str(cutoff)[:10] if cutoff else f"{int(read_year)}-01-01"


class LookAheadError(AssertionError):
    pass


def features(mlbam, read_year: int, cutoff: str | None, side: str) -> dict:
    """{feature: value or None, "_seasons": seasons read, "_T": T} for one row."""
    names = feature_names(side)
    out: dict = {f: None for f in names}
    T = top_season(int(read_year), cutoff)
    out["_T"] = T
    out["_seasons"] = []
    if not mlbam or T < SEASONS[0]:
        return out
    asof = asof_date(int(read_year), cutoff)
    pid = int(mlbam)
    cst = constants(T, side)
    win = _played_window(T, WINDOW_SEASONS)
    got = []
    for s in win:
        # every input of the season (its lines, its league factors, the park window
        # s - 2 .. s) is dated at or before the season's end
        if f"{s}{SEASON_END_MMDD}" > asof:
            raise LookAheadError(f"season {s} ended after the as-of {asof}")
        ps = player_seasons(s, side).get(pid)
        if ps is not None:
            got.append((s, ps))
    out["_seasons"] = [s for s, _ in got]
    if not got:
        return out
    for st in STATS[side]:
        c = cst[st]
        num = den = eff = 0.0
        newest = None
        for s, ps in got:
            v = ps["stats"].get(st)
            if v is None:
                continue
            m = MARCEL[win.index(s)]
            x = v[0] * env_scale(s, T, side, st)
            num += m * v[1] * x
            den += m * v[1]
            eff += (m / MARCEL[0]) * v[1]
            if newest is None:
                newest = ps
        if den > 0 and newest is not None:
            out[f"{st}_rw"] = shrink(num / den, eff, c["k"], _prior(c, newest))
        seq = []
        for s, ps in got:
            v = ps["stats"].get(st)
            if v is None or v[1] <= 0:
                continue
            x = v[0] * env_scale(s, T, side, st)
            seq.append(shrink(x, v[1], c["k"], _prior(c, ps)))
            if len(seq) == 2:
                break
        if len(seq) == 2:
            out[f"{st}_yoy"] = seq[0] - seq[1]
    if side == "pit" and out.get("k_rw") is not None and out.get("bb_rw") is not None:
        out["kbb_rw"] = out["k_rw"] - out["bb_rw"]
    s0, ps0 = got[0]
    mean_age = level_mean_age(s0, side).get(ps0["level"])
    if ps0.get("age") is not None and mean_age is not None:
        out["age_rel_level"] = float(ps0["age"]) - mean_age
    return out


# ---------------------------------------------------------------------------
# diagnostics: held-out consecutive-level recovery
# ---------------------------------------------------------------------------

def _fold_of(pid: int, n_folds: int = 5, seed: int = FOLD_SEED) -> int:
    h = hashlib.sha256(f"{seed}:{int(pid)}".encode()).hexdigest()
    return int(h[:8], 16) % n_folds


def recovery(season: int, side: str, stat: str, lo: str = "AAA", hi: str = MLB,
             n_folds: int = 5) -> dict | None:
    """Pooled over the held-out folds: players with a `lo` line and a `hi` line the same
    season; the factors fitted without the fold translate the `lo` line onto `hi`'s
    scale. Returns the pooled actual, translated and untranslated rates at `hi`."""
    lines = season_lines(int(season), side)
    park = park_factors(int(season), side, stat)
    by_p: dict = {}
    for ln in lines:
        lvl = MLB if ln["lg"] == MLB else ln["level"]
        if lvl in (lo, hi) and ln["c"].get(stat):
            by_p.setdefault(ln["mlbam"], {}).setdefault(lvl, []).append(ln)
    pairs = {p: v for p, v in by_p.items() if lo in v and hi in v}
    if len(pairs) < 20:
        return None

    def pi_of(ln):
        return park.get(ln["team"], 1.0) if ln["nt"] == 1 and ln["team"] else 1.0
    act_n = act_d = pred_n = raw_n = 0.0
    for fold in range(n_folds):
        held = frozenset(p for p in pairs if _fold_of(p, n_folds) == fold)
        if not held:
            continue
        f = fit_league_factors(lines, stat, park, exclude_players=held)
        lam = f["lambda"]
        for p in held:
            lo_l, hi_l = pairs[p][lo], pairs[p][hi]
            if any(ln["lg"] not in lam for ln in lo_l + hi_l):
                continue
            n_lo = sum(ln["c"][stat][0] for ln in lo_l)
            d_lo = sum(ln["c"][stat][1] for ln in lo_l)
            dd_lo = sum(ln["c"][stat][1] * pi_of(ln) * lam[ln["lg"]] for ln in lo_l)
            if dd_lo <= 0 or d_lo <= 0:
                continue
            theta = n_lo / dd_lo
            for ln in hi_l:
                c = ln["c"][stat]
                act_n += c[0]
                act_d += c[1]
                pred_n += c[1] * pi_of(ln) * lam[ln["lg"]] * theta
                raw_n += c[1] * (n_lo / d_lo)
    if act_d <= 0 or act_n <= 0:
        return None
    a, p, r = act_n / act_d, pred_n / act_d, raw_n / act_d
    return {"season": int(season), "pairs": len(pairs), "actual": a, "translated": p,
            "untranslated": r, "translated_rel_err": p / a - 1.0,
            "untranslated_rel_err": r / a - 1.0}


def recovery_summary(seasons=None) -> dict:
    out: dict = {}
    seasons = seasons or [s for s in SEASONS if s <= 2026]
    for side in SIDES:
        for st in STATS[side]:
            for lo, hi in (("AAA", MLB), ("AA", "AAA"), ("A+", "AA")):
                rows = [r for s in seasons if (r := recovery(s, side, st, lo, hi))]
                if not rows:
                    continue
                act = sum(r["actual"] for r in rows)
                te = [abs(r["translated_rel_err"]) for r in rows]
                ue = [abs(r["untranslated_rel_err"]) for r in rows]
                out[f"{side}|{st}|{lo}->{hi}"] = {
                    "seasons": len(rows), "pairs": sum(r["pairs"] for r in rows),
                    "mean_abs_rel_err_translated": round(float(np.mean(te)), 4),
                    "mean_abs_rel_err_untranslated": round(float(np.mean(ue)), 4),
                    "seasons_translated_closer": sum(1 for a, b in zip(te, ue) if a < b),
                    "mean_actual": round(act / len(rows), 5)}
    return out


# ---------------------------------------------------------------------------
# artifact helpers
# ---------------------------------------------------------------------------

def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def write_json(doc: dict, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n"
    for ch in (chr(0x2014), chr(0x2013)):
        if ch in text:
            raise RuntimeError("an em-dash or en-dash reached the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)
    return out


def factors_block(T_values) -> dict:
    """Constants per (side, T), the park r per (side, stat) at the last season, the
    league factors' identification counts, and the recovery diagnostics."""
    out: dict = {"constants": {}, "park_r": {}, "identification": {}, "mex_dropped":
                 dropped_counts()}
    for side in SIDES:
        for T in sorted(set(T_values)):
            c = constants(int(T), side)
            out["constants"][f"{side}|{T}"] = {
                st: {"k": _rnd(v["k"], 2), "tau2": _rnd(v["tau2"], 8),
                     "mean_var_unit": _rnd(v["mean_var_unit"], 6), "n_rows": v["n_rows"],
                     "seasons": v["seasons"]} for st, v in c.items()}
        for st in STATS[side]:
            out["park_r"][f"{side}|{st}"] = {str(s): {k: _rnd(v, 4) if isinstance(v, float)
                                                      else v for k, v in
                                                      park_r(s, side, st).items()}
                                             for s in SEASONS}
            ident = {}
            for s in SEASONS:
                tab = league_table(s, side, st)
                ident[str(s)] = {
                    "leagues": len(tab),
                    "identified": sum(1 for t in tab.values() if t["identified"]),
                    "fallback": sorted(g for g, t in tab.items() if t.get("fallback")),
                    "lambda": {g: _rnd(t["lambda"], 5) for g, t in sorted(tab.items())},
                    "links": {g: t["links"] for g, t in sorted(tab.items())}}
            out["identification"][f"{side}|{st}"] = ident
    out["recovery"] = recovery_summary()
    return out


# ---------------------------------------------------------------------------
# the development read
# ---------------------------------------------------------------------------

def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def _pct(v: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata
    return rankdata(v, method="average") / max(len(v), 1)


def design(rows: list[dict], fname: str, vals: dict) -> tuple:
    """Per-row (u_c, z, m, u_y) inside each (side, year) group."""
    import source_backtest as SB
    cons = SB.CONSENSUS_KEY
    by_g: dict = {}
    for i, r in enumerate(rows):
        by_g.setdefault(r["group"], []).append(i)
    n = len(rows)
    uc, z, m, uy = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    for _g, ix in by_g.items():
        ix = np.asarray(ix)
        uc[ix] = _pct(np.array([rows[i]["grades"][cons] for i in ix], dtype=np.float64))
        uy[ix] = _pct(np.array([rows[i]["outcome"]["war"] for i in ix], dtype=np.float64))
        v = np.array([np.nan if vals.get(rows[i]["_rk"]) is None
                      else float(vals[rows[i]["_rk"]]) for i in ix])
        have = ~np.isnan(v)
        if have.sum() >= 2:
            mu, sd = float(np.mean(v[have])), float(np.std(v[have]))
            zz = np.where(have, (v - mu) / sd if sd > 0 else 0.0, 0.0)
        else:
            zz = np.zeros(len(ix))
        z[ix] = zz
        m[ix] = (~have).astype(float)
    return uc, z, m, uy


def loyo_score(rows: list[dict], fname: str, vals: dict) -> tuple[np.ndarray, dict]:
    """Leave-one-year-out ridge of u_y on (u_c, z, m); returns the held-out predictions
    and the per-year slopes."""
    uc, z, m, uy = design(rows, fname, vals)
    years = np.array([int(r["year"]) for r in rows])
    Xf = np.column_stack([np.ones(len(rows)), uc, z, m])
    P = np.diag([0.0, 1.0, 1.0, 1.0]) * RIDGE_ALPHA
    score = np.zeros(len(rows))
    slopes = {}
    for y in sorted(set(years.tolist())):
        tr, te = years != y, years == y
        if tr.sum() < 10:
            score[te] = uc[te]
            slopes[str(y)] = None
            continue
        A = Xf[tr].T @ Xf[tr] + P
        b = np.linalg.solve(A, Xf[tr].T @ uy[tr])
        score[te] = Xf[te] @ b
        slopes[str(y)] = [round(float(t), 5) for t in b]
    return score, slopes


def _within_rho(score, y, groups) -> float | None:
    import efv_v2_stat as S
    codes = np.asarray([str(g) for g in groups])
    keep = S.kept_groups(codes, MIN_GROUP_ROWS)
    w, _n, _g = S.within(np.asarray(score, dtype=np.float64), np.asarray(y, dtype=np.float64),
                         codes, keep)
    return w


def descriptive(rows: list[dict], vals: dict) -> dict:
    """Coverage, the feature's own within Spearman with the label and with consensus, on
    the rows that carry it."""
    import source_backtest as SB
    sel = [r for r in rows if vals.get(r["_rk"]) is not None]
    out = {"rows": len(rows), "with_value": len(sel),
           "coverage": _rnd(len(sel) / len(rows), 4) if rows else None}
    if len(sel) >= MIN_GROUP_ROWS:
        f = [float(vals[r["_rk"]]) for r in sel]
        g = [r["group"] for r in sel]
        out["within_rho_label"] = _rnd(_within_rho(f, [r["outcome"]["war"] for r in sel], g), 4)
        out["within_rho_consensus"] = _rnd(_within_rho(
            f, [r["grades"][SB.CONSENSUS_KEY] for r in sel], g), 4)
    return out


def twin_vals(rows: list[dict], vals: dict, rng) -> dict:
    by_g: dict = {}
    for r in rows:
        by_g.setdefault(r["group"], []).append(r["_rk"])
    out = {}
    for g in sorted(by_g):
        ks = by_g[g]
        v = [vals.get(k) for k in ks]
        perm = rng.permutation(len(ks))
        for i, k in enumerate(ks):
            out[k] = v[int(perm[i])]
    return out


def feature_read(rows: list[dict], fname: str, vals: dict, *, B: int, twin_rng) -> dict:
    import efv_v2_stat as S
    import source_backtest as SB
    cons = SB.CONSENSUS_KEY
    score, slopes = loyo_score(rows, fname, vals)
    d = S.paired_delta([r["key"] for r in rows], [r["group"] for r in rows],
                       [r["outcome"]["war"] for r in rows], [False] * len(rows),
                       score, [r["grades"][cons] for r in rows],
                       [r["grades"][cons] for r in rows], statistic="within", B=B,
                       seed=BOOT_SEED)
    tv = twin_vals(rows, vals, twin_rng)
    tscore, _ = loyo_score(rows, fname, tv)
    tw = S._within_pair(np.asarray(tscore, dtype=np.float64),
                        np.asarray([r["grades"][cons] for r in rows], dtype=np.float64),
                        np.asarray([r["outcome"]["war"] for r in rows], dtype=np.float64),
                        np.asarray([str(r["group"]) for r in rows]),
                        S.kept_groups(np.asarray([str(r["group"]) for r in rows]),
                                      MIN_GROUP_ROWS), np.arange(len(rows)))
    twin = None if tw[0] is None else round(tw[0] - tw[1], 5)
    return {"delta": d["delta"], "ci95": d["ci95"], "mde95": d["mde95"],
            "p_gt_0": d["p_gt_0"], "score_within": d["a"], "consensus_within": d["b"],
            "n": d["n"], "n_clusters": d["n_clusters"], "B_used": d["B_used"],
            "status": d.get("status"), "twin_delta": twin, "loyo_slopes": slopes,
            "reading": S.reading(d["ci95"]), **descriptive(rows, vals)}


def build_rows(log=print) -> dict:
    """{fid: {side: [scored row with "_rk", "_mlbam", "_cutoff"]}} for lv_dev and vm_dev,
    through tools/efv_v2_model_class_screen.build_inputs (guards first)."""
    _tools()
    import efv_v2_assemble as ASM
    import efv_v2_model as H
    import efv_v2_model_class_screen as MCS
    import efv_vintage_frame as F
    frames_lv = ASM.build_frames()
    if any(int(V) in F.RESERVED_LV for s in F.SIDES for V in frames_lv[s]):
        raise F.ReservedFrameError("lv frames carry a reserved vintage")
    orig = ASM.build_frames
    ASM.build_frames = lambda *a, **k: frames_lv
    try:
        inputs = MCS.build_inputs(log=log)
    finally:
        ASM.build_frames = orig
    out: dict = {"lv_dev": {}, "vm_dev": {}}
    for side in F.SIDES:
        lv_by = {(r["player_key"], int(V)): r for V, (rows, _l) in frames_lv[side].items()
                 for r in rows}
        rows = []
        for V, blk in inputs["frames"]["lv_dev"]["by_side"][side].items():
            if int(V) in F.RESERVED_LV:
                raise F.ReservedFrameError(f"lv_dev reaches {V}")
            for c in blk["scored"]:
                fr = lv_by.get((c["key"], int(V))) or {}
                rows.append(dict(c, _rk=(c["key"], int(V)), _mlbam=fr.get("mlbam_id"),
                                 _cutoff=(fr.get("window") or [None])[0]))
        out["lv_dev"][side] = rows
        raw = {r["player_key"]: r for r in json.loads(
            H._matrix_path(side).read_text(encoding="utf-8"))}
        mine: dict = {}
        H.pinned_inputs(side, H.matrix_training_rows(side), mine)
        rows = []
        for yr, blk in inputs["frames"]["vm_dev"]["by_side"][side].items():
            if int(yr) >= F.R_VM_FIRST_DEBUT_YEAR:
                raise F.ReservedFrameError(f"vm_dev reaches R-VM: {yr}")
            for c in blk["scored"]:
                rw = raw.get(c["key"]) or {}
                rows.append(dict(c, _rk=(c["key"], int(yr)), _mlbam=rw.get("mlbam_id"),
                                 _cutoff=(mine.get(c["key"]) or {}).get("asof_date")))
        out["vm_dev"][side] = rows
    return out


def row_features(rows: list[dict], side: str) -> tuple[dict, dict]:
    """({feature: {row key: value}}, receipt) for one frame side."""
    vals: dict = {f: {} for f in feature_names(side)}
    rec = {"rows": len(rows), "with_mlbam": 0, "with_any_line": 0, "T": {}}
    for r in rows:
        f = features(r.get("_mlbam"), int(r["year"]), r.get("_cutoff"), side)
        rec["with_mlbam"] += int(bool(r.get("_mlbam")))
        rec["with_any_line"] += int(bool(f["_seasons"]))
        rec["T"][str(f["_T"])] = rec["T"].get(str(f["_T"]), 0) + 1
        for k in vals:
            vals[k][r["_rk"]] = f.get(k)
    rec["T"] = dict(sorted(rec["T"].items()))
    return vals, rec


def flag(lv: dict, vm: dict) -> bool:
    """The registration's descriptive flag (s8)."""
    def ok(x):
        return x.get("delta") is not None
    if not (ok(lv) and ok(vm)):
        return False
    pos = lv["delta"] > 0 and vm["delta"] > 0
    lb = any(isinstance(x.get("ci95"), list) and x["ci95"][0] > 0 for x in (lv, vm))
    tw = all(x.get("twin_delta") is None or x["delta"] > x["twin_delta"] for x in (lv, vm))
    return bool(pos and lb and tw)


def dev_read(*, B: int = B_DEFAULT, log=print) -> dict:
    import efv_labels as L
    import efv_vintage_frame as F
    t0 = time.time()
    frames = build_rows(log=log)
    log(f"frames built ({round(time.time() - t0, 1)} s)")
    T_used: set = set()
    feats: dict = {}
    receipts: dict = {}
    for fid in ("lv_dev", "vm_dev"):
        for side in SIDES:
            vals, rec = row_features(frames[fid][side], side)
            feats[(fid, side)] = vals
            receipts[f"{fid}|{side}"] = rec
            T_used |= {int(t) for t in rec["T"]}
            log(f"  features {fid} {side}: {rec}")
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
           "role": "development", "descriptive": True, "adjudicates": False,
           "selects": False, "served": False,
           "owner_decision": "EW3-12 (2026-10-15), the expert eFV program, step X1",
           "registration": {"doc": REGISTRATION_DOC,
                            "commit": _git("log", "-1", "--format=%h", "--",
                                           REGISTRATION_DOC)},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"),
                    "module_sha256": _sha(Path(__file__)),
                    "fetch_sha256": _sha(ROOT / "efv_x1_fetch.py")},
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "lv_dev": "W3 (fWAR over the first three MLB seasons)",
                     "vm_dev": "career WAR to date"},
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "anchor_gate_grouping": False},
           "estimator": {"statistic": "within (side, vintage) Spearman, size-weighted, "
                                      "score minus consensus",
                         "score": "leave-one-year-out ridge (alpha 1.0) of the label "
                                  "percentile on consensus percentile, feature z, missing",
                         "B": int(B), "seed": BOOT_SEED, "clusters": "player",
                         "estimator": "E_cond", "twin_seed": TWIN_SEED,
                         "min_group_rows": MIN_GROUP_ROWS},
           "construction": {"stats": STATS, "woba_weights": WOBA_W, "min_link": MIN_LINK,
                            "park_window": PARK_WINDOW, "prior_window": PRIOR_WINDOW,
                            "prior_min_cell": PRIOR_MIN_CELL,
                            "k_min_exposure": K_MIN_EXPOSURE, "age_clip": AGE_CLIP,
                            "marcel": MARCEL, "window_seasons": WINDOW_SEASONS,
                            "dropped_leagues": sorted(DROP_LEAGUES)},
           "feature_receipts": receipts}
    log("factors and diagnostics ...")
    doc["factors"] = factors_block(T_used)
    log(f"factors done ({round(time.time() - t0, 1)} s)")
    twin_rng = np.random.default_rng(TWIN_SEED)
    reads: dict = {}
    for side in SIDES:
        for fname in feature_names(side):
            ent = {}
            for fid in ("lv_dev", "vm_dev"):
                rows = frames[fid][side]
                t1 = time.time()
                ent[fid] = feature_read(rows, fname, feats[(fid, side)][fname], B=B,
                                        twin_rng=twin_rng)
                log(f"  {side} {fname} {fid}: delta {ent[fid]['delta']} CI95 "
                    f"{ent[fid]['ci95']} twin {ent[fid]['twin_delta']} cov "
                    f"{ent[fid]['coverage']} ({round(time.time() - t1, 1)} s)")
            ent["flagged_for_x3"] = flag(ent["lv_dev"], ent["vm_dev"])
            reads[f"{side}|{fname}"] = ent
    doc["reads"] = reads
    doc["flagged_for_x3"] = sorted(k for k, v in reads.items() if v["flagged_for_x3"])
    doc["elapsed_s"] = round(time.time() - t0, 1)
    write_json(doc, OUT_PATH)
    log(f"wrote {OUT_PATH} ({doc['elapsed_s']} s)")
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--factors", action="store_true", help="constants and diagnostics")
    ap.add_argument("--dev-read", action="store_true", help="the registered development read")
    ap.add_argument("--B", type=int, default=B_DEFAULT)
    a = ap.parse_args()

    def _log(msg):
        print(msg, flush=True)
    if a.factors:
        fb = factors_block(range(2016, 2026))
        _log(json.dumps({"constants": fb["constants"], "recovery": fb["recovery"],
                         "mex_dropped": fb["mex_dropped"]}, indent=1, default=str))
    if a.dev_read:
        r = dev_read(B=a.B, log=_log)
        _log(json.dumps(r["flagged_for_x3"]))
