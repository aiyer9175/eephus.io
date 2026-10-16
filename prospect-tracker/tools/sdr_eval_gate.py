# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The SDR gates, read once: G-A (docs/sdr-2026-08-18/SDR_EVAL_GATE.md) and G-C
(MILB_SDR_EVAL_GATE.md), on the in-house drop (tools/sdr_inhouse.py).

Every choice below was fixed in the gates' Amendment 2026-10-15 before this file
existed and before the drop was built:

  C1  player-season self-persistence: Spearman of rate(Y) with rate(Y+1) for SDR,
      B-Ref rfield and FanGraphs-hosted OAA on one pair set; SDR must beat both at
      the point and clear a player-clustered LB95 over the better one.
  C2  club sums (runs over frame innings, allocated by club innings) in Y against
      next-season runs allowed residualized on club FIP runs; same rule, the
      bootstrap player-clustered (outcomes fixed), club-clustered beside.
  Holm over C1 and C2; a noise twin (sdr_runs permuted within position-season)
  per clause must fail.
  C3  same-season agreement (reported).  C4  top and bottom 15 by position.
  C5  the EW3-23 leg, EBR_GATE.md 11.2.2's leave-one-system-out rule (deciding for
      that read).  C6  UZR(Y+1), the series none of the three reads (reported).
  A5  per-position cells (reported).

G-C is recorded NOT RUN when the census holds no MiLB row (the amendment's rule);
its artifact carries the census and the in-house 15_milb_translation matrix.

The loaders are injectable (Inputs) so test_sdr_eval_gate.py dry-runs the whole
reporting path on fixtures with nulls before the real read.

Usage:
    python tools/sdr_eval_gate.py --dry-run     # fixtures, writes nothing
    python tools/sdr_eval_gate.py               # the read; writes data/sdr_eval.json
                                                # and data/milb_sdr_eval.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

OUT_GA = ROOT / "data" / "sdr_eval.json"
OUT_GC = ROOT / "data" / "milb_sdr_eval.json"
CENSUS = ROOT / "data" / "sdr_census.json"
WAR_DAILY = ROOT / ".cache" / "war_daily" / "bat.parquet"

POS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
PRED_SEASONS = tuple(range(2017, 2026))       # predictor seasons Y; outcome Y+1
UZR_LAST_TARGET = 2024
B = 2000
SEED = 20261015
TWIN_SEED = 20261016
ALPHA = 0.05


@dataclass
class Inputs:
    drop: pd.DataFrame                          # the accepted contract drop
    fg: dict                                    # season -> FG combined fielding rows
    split: dict                                 # season -> FG split-by-club rows
    rfield: pd.DataFrame                        # player_id, season, runs_field, inn
    team: dict                                  # season -> teamid, R, FIP, IP
    variants: dict = field(default_factory=dict)   # name -> DataFrame(player_id, season, Pos, sdr_runs)
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# small statistics
# ---------------------------------------------------------------------------

def _rank(a: np.ndarray) -> np.ndarray:
    return pd.Series(a).rank(method="average").to_numpy()


def spearman(x, y) -> float | None:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return None
    rx, ry = _rank(x[ok]), _rank(y[ok])
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _r(v, k=4):
    return None if v is None or not np.isfinite(v) else round(float(v), k)


def fg_ip(x) -> float:
    """FanGraphs innings: 1234.1 means 1234 and one third."""
    x = float(x)
    whole = int(x)
    return whole + round((x - whole) * 10) / 3.0


# ---------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------

def player_seasons(inp: Inputs, sdr_rows: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (player_id, season) over the player's frame rows."""
    d = (sdr_rows if sdr_rows is not None else inp.drop)[
        ["player_id", "season", "primary_position", "innings", "sdr_runs"]].copy()
    d = d.rename(columns={"primary_position": "Pos"})
    fgs = []
    for s, f in inp.fg.items():
        g = f.copy()
        g["season"] = int(s)
        fgs.append(g)
    fg = pd.concat(fgs, ignore_index=True) if fgs else pd.DataFrame(
        columns=["player_id", "season", "Pos"])
    cols = ["OAA", "DRS", "FRP", "UZR", "Defense"]
    for c in cols:
        if c not in fg.columns:
            fg[c] = np.nan
    d = d.merge(fg[["player_id", "season", "Pos"] + cols], on=["player_id", "season", "Pos"],
                how="left", validate="one_to_one")
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["oaa_inn"] = np.where(d.OAA.notna(), d.innings, 0.0)
    d["uzr_inn"] = np.where(d.UZR.notna(), d.innings, 0.0)
    g = d.groupby(["player_id", "season"])
    ps = pd.DataFrame({
        "inn": g.innings.sum(),
        "sdr": g.sdr_runs.sum(min_count=1),
        "oaa": g.OAA.sum(min_count=1), "oaa_inn": g.oaa_inn.sum(),
        "drs": g.DRS.sum(min_count=1), "frp": g.FRP.sum(min_count=1),
        "uzr": g.UZR.sum(min_count=1), "uzr_inn": g.uzr_inn.sum(),
        "defense": g.Defense.sum(min_count=1),
        "is_c_only": g.Pos.agg(lambda x: set(x) == {"C"}),
    }).reset_index()
    ps["sdr_rate"] = ps.sdr / ps.inn
    ps["oaa_rate"] = np.where(ps.oaa_inn > 0, ps.oaa / ps.oaa_inn.replace(0, np.nan), np.nan)
    ps["drs_rate"] = ps.drs / ps.inn
    ps["frp_rate"] = ps.frp / ps.inn
    ps["uzr_rate"] = np.where(ps.uzr_inn > 0, ps.uzr / ps.uzr_inn.replace(0, np.nan), np.nan)
    ps["defense_rate"] = ps.defense / ps.inn
    rf = inp.rfield.copy()
    rf["rfield_rate"] = np.where(rf.inn > 0, rf.runs_field / rf.inn.replace(0, np.nan), np.nan)
    ps = ps.merge(rf[["player_id", "season", "rfield_rate"]], on=["player_id", "season"],
                  how="left")
    for name, v in inp.variants.items():
        vv = v.merge(d[["player_id", "season", "Pos", "innings"]],
                     on=["player_id", "season", "Pos"], how="inner")
        gv = vv.groupby(["player_id", "season"])
        rate = (gv.sdr_runs.sum(min_count=1) / gv.innings.sum()).rename(f"{name}_rate")
        ps = ps.merge(rate.reset_index(), on=["player_id", "season"], how="left")
    return ps


def pairs(ps: pd.DataFrame, seasons=PRED_SEASONS) -> pd.DataFrame:
    a = ps[ps.season.isin(seasons)]
    b = ps.copy()
    b["season"] = b.season - 1
    return a.merge(b, on=["player_id", "season"], suffixes=("", "_n"))


def permute_sdr(drop: pd.DataFrame, seed: int, col: str = "sdr_runs",
                pos_col: str = "primary_position") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = drop.copy()
    vals = out[col].to_numpy(copy=True)
    for _, idx in out.groupby([pos_col, "season"]).indices.items():
        vals[idx] = vals[rng.permutation(idx)]
    out[col] = vals
    return out


# ---------------------------------------------------------------------------
# bootstrap machinery
# ---------------------------------------------------------------------------

def _cluster_index(groups: np.ndarray):
    uniq, inv = np.unique(groups, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(len(uniq))]
    return uniq, members


def boot_spearman(cols: dict, groups: np.ndarray, stat, b: int = B, seed: int = SEED):
    """Player-clustered bootstrap of stat(rhos) where rhos maps a name to the
    Spearman of the (x, y) arrays in cols. Returns the array of stat draws."""
    _, members = _cluster_index(groups)
    rng = np.random.default_rng(seed)
    n = len(members)
    out = np.empty(b)
    for i in range(b):
        pick = rng.integers(0, n, n)
        idx = np.concatenate([members[k] for k in pick]) if n else np.array([], int)
        rh = {k: spearman(x[idx], y[idx]) for k, (x, y) in cols.items()}
        out[i] = stat(rh)
    return out


def beat_both(rho_sdr, rho_a, rho_b, draws) -> dict:
    """C1's rule on a point estimate and bootstrap draws of d."""
    valid = draws[np.isfinite(draws)]
    lb = float(np.percentile(valid, 2.5)) if len(valid) else None
    ub = float(np.percentile(valid, 97.5)) if len(valid) else None
    p = float(np.mean(valid <= 0)) if len(valid) else None
    beats = (rho_sdr is not None and rho_a is not None and rho_b is not None
             and rho_sdr > rho_a and rho_sdr > rho_b)
    return {"beats_both_at_point": bool(beats), "lb95": _r(lb), "ub95": _r(ub),
            "p_one_sided": _r(p, 5), "lb_above_0": bool(lb is not None and lb > 0)}


def holm(ps: dict, alpha: float = ALPHA) -> dict:
    items = sorted((v, k) for k, v in ps.items() if v is not None)
    m = len(items)
    rej = {}
    stop = False
    for i, (p, k) in enumerate(items):
        thr = alpha / (m - i)
        ok = (not stop) and p <= thr
        rej[k] = {"p": p, "threshold": round(thr, 5), "rejects": bool(ok)}
        if not ok:
            stop = True
    for k, v in ps.items():
        if v is None:
            rej[k] = {"p": None, "threshold": None, "rejects": False}
    return rej


# ---------------------------------------------------------------------------
# C1
# ---------------------------------------------------------------------------

C1_METRICS = {"sdr": "sdr_rate", "rfield": "rfield_rate", "oaa": "oaa_rate"}


def c1_frame(ps: pd.DataFrame) -> pd.DataFrame:
    p = pairs(ps)
    need = [c for m in C1_METRICS.values() for c in (m, m + "_n")]
    return p.dropna(subset=need).reset_index(drop=True)


def c1_read(ps: pd.DataFrame, b: int = B, seed: int = SEED) -> dict:
    p = c1_frame(ps)
    rho = {k: spearman(p[c], p[c + "_n"]) for k, c in C1_METRICS.items()}
    if any(v is None for v in rho.values()):
        return {"n_pairs": int(len(p)), "rho": {k: _r(v) for k, v in rho.items()},
                "status": "not computable"}
    better = "rfield" if rho["rfield"] >= rho["oaa"] else "oaa"
    cols = {k: (p[c].to_numpy(float), p[c + "_n"].to_numpy(float))
            for k, c in C1_METRICS.items()}
    draws = boot_spearman(cols, p.player_id.to_numpy(),
                          lambda r: (r["sdr"] - r[better]) if None not in (r["sdr"], r[better])
                          else np.nan, b=b, seed=seed)
    rule = beat_both(rho["sdr"], rho["rfield"], rho["oaa"], draws)
    no2020 = p[(p.season != 2019) & (p.season != 2020)]
    return {
        "n_pairs": int(len(p)), "n_players": int(p.player_id.nunique()),
        "predictor_seasons": sorted(int(s) for s in p.season.unique()),
        "rho": {k: _r(v) for k, v in rho.items()},
        "better_incumbent": better, "d_point": _r(rho["sdr"] - rho[better]),
        **rule,
        "without_2020_pairs": {
            "n_pairs": int(len(no2020)),
            "rho": {k: _r(spearman(no2020[c], no2020[c + "_n"])) for k, c in C1_METRICS.items()},
        },
    }


# ---------------------------------------------------------------------------
# C2
# ---------------------------------------------------------------------------

C2_METRICS = {"sdr": "sdr_rate", "rfield": "rfield_rate", "oaa": "oaa_rate"}


def club_target(inp: Inputs) -> pd.DataFrame:
    rows = []
    for s, t in inp.team.items():
        t = t.copy()
        t["ip"] = t.IP.map(fg_ip)
        t["fipr"] = pd.to_numeric(t.FIP, errors="coerce") * t.ip / 9.0
        t["R"] = pd.to_numeric(t.R, errors="coerce")
        t = t.dropna(subset=["fipr", "R"])
        if len(t) < 3:
            continue
        b1, b0 = np.polyfit(t.fipr, t.R, 1)
        e = t.R - (b0 + b1 * t.fipr)
        z = e / e.std(ddof=1) if e.std(ddof=1) > 0 else e * 0
        for tid, zz in zip(t.teamid, z):
            rows.append({"teamid": int(tid), "season": int(s), "target": float(-zz)})
    return pd.DataFrame(rows, columns=["teamid", "season", "target"])


def club_contrib(inp: Inputs, ps: pd.DataFrame) -> pd.DataFrame:
    """Long table (season, teamid, player_id, share, inn_frame) over frame rows."""
    frame = inp.drop[["player_id", "season", "primary_position"]].rename(
        columns={"primary_position": "Pos"})
    out = []
    for s, sp in inp.split.items():
        sp = sp[["player_id", "Pos", "teamid", "Inn"]].copy()
        sp["season"] = int(s)
        sp = sp.merge(frame[frame.season == int(s)], on=["player_id", "season", "Pos"],
                      how="inner")
        if not len(sp):
            continue
        g = sp.groupby(["player_id", "teamid"], as_index=False).Inn.sum()
        tot = g.groupby("player_id").Inn.transform("sum")
        g["share"] = np.where(tot > 0, g.Inn / tot, 0.0)
        g["season"] = int(s)
        out.append(g[["season", "teamid", "player_id", "share"]])
    c = pd.concat(out, ignore_index=True) if out else pd.DataFrame(
        columns=["season", "teamid", "player_id", "share"])
    return c.merge(ps[["player_id", "season", "inn"] + list(C2_METRICS.values())],
                   on=["player_id", "season"], how="left")


def _club_sums(contrib: pd.DataFrame, rate_col: str, weights=None) -> pd.DataFrame:
    v = (contrib[rate_col].fillna(0.0) * contrib.inn * contrib.share).to_numpy()
    if weights is not None:
        v = v * weights
    s = pd.DataFrame({"season": contrib.season, "teamid": contrib.teamid, "v": v})
    s = s.groupby(["season", "teamid"], as_index=False).v.sum()
    s["z"] = s.groupby("season").v.transform(
        lambda x: (x - x.mean()) / x.std(ddof=1) if x.std(ddof=1) > 0 else x * 0)
    return s


def c2_pairs(contrib, target, rate_col, weights=None):
    s = _club_sums(contrib, rate_col, weights)
    s = s[s.season.isin(PRED_SEASONS)].copy()
    t = target.copy()
    t["season"] = t.season - 1
    return s.merge(t, on=["season", "teamid"], how="inner")


def c2_read(inp: Inputs, ps: pd.DataFrame, b: int = B, seed: int = SEED) -> dict:
    target = club_target(inp)
    contrib = club_contrib(inp, ps)
    P = {k: c2_pairs(contrib, target, c) for k, c in C2_METRICS.items()}
    rho = {k: spearman(P[k].z, P[k].target) for k in P}
    n = int(len(P["sdr"]))
    if any(v is None for v in rho.values()):
        return {"n_club_pairs": n, "rho": {k: _r(v) for k, v in rho.items()},
                "status": "not computable"}
    better = "rfield" if rho["rfield"] >= rho["oaa"] else "oaa"
    # player-clustered: draw players, recompute every club sum, outcomes fixed
    players = np.unique(contrib.player_id.to_numpy())
    pos_of = {p: i for i, p in enumerate(players)}
    pidx = contrib.player_id.map(pos_of).to_numpy()
    rng = np.random.default_rng(seed)
    draws = np.empty(b)
    for i in range(b):
        w = np.bincount(rng.integers(0, len(players), len(players)),
                        minlength=len(players)).astype(float)[pidx]
        rs = {}
        for k in (["sdr", better]):
            pp = c2_pairs(contrib, target, C2_METRICS[k], weights=w)
            rs[k] = spearman(pp.z, pp.target)
        draws[i] = (rs["sdr"] - rs[better]) if None not in rs.values() else np.nan
    rule = beat_both(rho["sdr"], rho["rfield"], rho["oaa"], draws)
    # club-clustered, reported beside
    fr = P["sdr"][["season", "teamid", "z", "target"]].rename(columns={"z": "z_sdr"})
    fr = fr.merge(P[better][["season", "teamid", "z"]].rename(columns={"z": "z_inc"}),
                  on=["season", "teamid"])
    cl = boot_spearman({"sdr": (fr.z_sdr.to_numpy(), fr.target.to_numpy()),
                        "inc": (fr.z_inc.to_numpy(), fr.target.to_numpy())},
                       fr.teamid.to_numpy(),
                       lambda r: (r["sdr"] - r["inc"]) if None not in r.values() else np.nan,
                       b=b, seed=seed)
    clv = cl[np.isfinite(cl)]
    no2020 = {k: P[k][(P[k].season != 2019) & (P[k].season != 2020)] for k in P}
    return {
        "n_club_pairs": n, "rho": {k: _r(v) for k, v in rho.items()},
        "better_incumbent": better, "d_point": _r(rho["sdr"] - rho[better]),
        **rule,
        "club_clustered_beside": {
            "lb95": _r(np.percentile(clv, 2.5)) if len(clv) else None,
            "ub95": _r(np.percentile(clv, 97.5)) if len(clv) else None},
        "without_2020_pairs": {k: _r(spearman(v.z, v.target)) for k, v in no2020.items()},
    }


# ---------------------------------------------------------------------------
# C3, C4
# ---------------------------------------------------------------------------

def c3_read(ps: pd.DataFrame) -> dict:
    out = {}
    for name, col, seasons in (("rfield", "rfield_rate", None),
                               ("uzr", "uzr_rate", range(2017, UZR_LAST_TARGET + 1)),
                               ("fg_defense", "defense_rate", None)):
        d = ps if seasons is None else ps[ps.season.isin(list(seasons))]
        d = d.dropna(subset=["sdr_rate", col])
        out[name] = {"n": int(len(d)), "spearman_same_season": _r(spearman(d.sdr_rate, d[col]))}
    out["note"] = ("Reported, never gated. FG fFld 0.28 and prospect_def_value 0.68 belong to "
                   "the prospect frame; prospect_def_value has no MLB player-season value, so "
                   "neither is recomputed here.")
    return out


def c4_read(drop: pd.DataFrame, season: int, n: int = 15) -> dict:
    d = drop[drop.season == season]
    out = {}
    for pos in POS:
        g = d[d.primary_position == pos].sort_values("sdr_runs", ascending=False)
        rec = lambda r: {"player": r.player_name, "player_id": int(r.player_id),
                         "innings": round(float(r.innings), 1),
                         "sdr_runs": round(float(r.sdr_runs), 1)}
        out[pos] = {"n": int(len(g)), "top": [rec(r) for r in g.head(n).itertuples()],
                    "bottom": [rec(r) for r in g.tail(n).iloc[::-1].itertuples()]}
    return {"season": season, "by_position": out}


# ---------------------------------------------------------------------------
# C5, C6
# ---------------------------------------------------------------------------

def c5_read(ps: pd.DataFrame, ps_twin: pd.DataFrame | None, b: int = B,
            seed: int = SEED) -> dict:
    def frame(x):
        p = c1_frame(x)
        return p.dropna(subset=["no_drs_rate", "no_statcast_rate", "drs_rate_n",
                                "frp_rate_n"]).reset_index(drop=True)

    def gaps(p, idx=None):
        q = p if idx is None else p.iloc[idx]
        r1 = spearman(q.no_drs_rate, q.drs_rate_n)
        i1 = spearman(q.oaa_rate, q.drs_rate_n)
        r2 = spearman(q.no_statcast_rate, q.frp_rate_n)
        i2 = spearman(q.rfield_rate, q.frp_rate_n)
        if None in (r1, i1, r2, i2):
            return None, {}
        return 0.5 * ((r1 - i1) + (r2 - i2)), {
            "drs_system": {"sdr_without_drs": _r(r1), "oaa": _r(i1), "gap": _r(r1 - i1),
                           "target": "FanGraphs DRS per inning, Y+1"},
            "statcast_system": {"sdr_without_statcast": _r(r2), "rfield": _r(i2),
                                "gap": _r(r2 - i2), "target": "FRP per inning, Y+1"}}

    def boot(p):
        _, members = _cluster_index(p.player_id.to_numpy())
        rng = np.random.default_rng(seed)
        out = np.empty(b)
        for i in range(b):
            pick = rng.integers(0, len(members), len(members))
            idx = np.concatenate([members[k] for k in pick])
            g, _ = gaps(p, idx)
            out[i] = np.nan if g is None else g
        return out[np.isfinite(out)]

    p = frame(ps)
    g, parts = gaps(p)
    if g is None:
        return {"n_pairs": int(len(p)), "status": "not computable"}
    dr = boot(p)
    lb, ub = float(np.percentile(dr, 2.5)), float(np.percentile(dr, 97.5))
    disp = "WIN" if lb > 0 else ("LOSS" if ub < 0 else "UNRESOLVED")
    twin = None
    if ps_twin is not None:
        pt = frame(ps_twin)
        gt, _ = gaps(pt)
        if gt is not None:
            dt = boot(pt)
            tlb = float(np.percentile(dt, 2.5))
            twin = {"gap": _r(gt), "lb95": _r(tlb), "clears": bool(tlb > 0)}
    if disp == "WIN" and twin and twin["clears"]:
        disp = "UNRESOLVED (twin also clears)"
    return {"n_pairs": int(len(p)), "gap_point": _r(g), "lb95": _r(lb), "ub95": _r(ub),
            "per_system": parts, "twin": twin, "disposition": disp}


def c6_read(ps: pd.DataFrame, b: int = B, seed: int = SEED) -> dict:
    p = c1_frame(ps)
    p = p[p.season + 1 <= UZR_LAST_TARGET].dropna(subset=["uzr_rate_n"]).reset_index(drop=True)
    rho = {k: spearman(p[c], p.uzr_rate_n) for k, c in C1_METRICS.items()}
    if any(v is None for v in rho.values()):
        return {"n_pairs": int(len(p)), "status": "not computable"}
    better = "rfield" if rho["rfield"] >= rho["oaa"] else "oaa"
    cols = {k: (p[c].to_numpy(float), p.uzr_rate_n.to_numpy(float))
            for k, c in C1_METRICS.items()}
    draws = boot_spearman(cols, p.player_id.to_numpy(),
                          lambda r: (r["sdr"] - r[better]) if None not in (r["sdr"], r[better])
                          else np.nan, b=b, seed=seed)
    return {"n_pairs": int(len(p)), "predictor_seasons": sorted(int(s) for s in p.season.unique()),
            "rho_vs_uzr_next": {k: _r(v) for k, v in rho.items()}, "better_incumbent": better,
            "d_point": _r(rho["sdr"] - rho[better]),
            **beat_both(rho["sdr"], rho["rfield"], rho["oaa"], draws)}


# ---------------------------------------------------------------------------
# A5 per position
# ---------------------------------------------------------------------------

def per_position(inp: Inputs, ps: pd.DataFrame, b: int = B, seed: int = SEED) -> dict:
    d = inp.drop.rename(columns={"primary_position": "Pos"})
    fgs = []
    for s, f in inp.fg.items():
        g = f[["player_id", "Pos", "OAA", "UZR"]].copy()
        g["season"] = int(s)
        fgs.append(g)
    fg = pd.concat(fgs, ignore_index=True)
    d = d.merge(fg, on=["player_id", "season", "Pos"], how="left")
    d["sdr_rate"] = d.sdr_runs / d.innings
    d["oaa_rate"] = pd.to_numeric(d.OAA, errors="coerce") / d.innings
    d["uzr_rate"] = pd.to_numeric(d.UZR, errors="coerce") / d.innings
    d["framing_rate"] = d.framing_runs / d.innings
    d["blocking_rate"] = d.blocking_runs / d.innings
    d = d.merge(ps[["player_id", "season", "rfield_rate"]], on=["player_id", "season"],
                how="left")
    nxt = d.copy()
    nxt["season"] = nxt.season - 1
    pr = d[d.season.isin(PRED_SEASONS)].merge(nxt, on=["player_id", "season", "Pos"],
                                              suffixes=("", "_n"))
    out = {}
    for pos in POS:
        q = pr[pr.Pos == pos]
        mets = {"sdr": "sdr_rate", "rfield": "rfield_rate"}
        if pos != "C":
            mets["oaa"] = "oaa_rate"
        q = q.dropna(subset=[c for m in mets.values() for c in (m, m + "_n")]).reset_index(drop=True)
        rho = {k: spearman(q[c], q[c + "_n"]) for k, c in mets.items()}
        cell = {"n_pairs": int(len(q)), "self_persistence": {k: _r(v) for k, v in rho.items()}}
        inc = [k for k in mets if k != "sdr" and rho.get(k) is not None]
        if rho.get("sdr") is not None and inc:
            better = max(inc, key=lambda k: rho[k])
            cols = {k: (q[mets[k]].to_numpy(float), q[mets[k] + "_n"].to_numpy(float))
                    for k in ("sdr", better)}
            dr = boot_spearman(cols, q.player_id.to_numpy(),
                               lambda r: (r["sdr"] - r[better]) if None not in r.values() else np.nan,
                               b=b, seed=seed)
            dr = dr[np.isfinite(dr)]
            cell.update({"better_incumbent": better, "d_point": _r(rho["sdr"] - rho[better]),
                         "lb95": _r(np.percentile(dr, 2.5)) if len(dr) else None,
                         "ub95": _r(np.percentile(dr, 97.5)) if len(dr) else None})
        if pos != "C":
            u = q[q.season + 1 <= UZR_LAST_TARGET].dropna(subset=["uzr_rate_n"])
            cell["c6_vs_uzr_next"] = {"n_pairs": int(len(u)), **{
                k: _r(spearman(u[c], u.uzr_rate_n)) for k, c in mets.items()}}
        else:
            for comp in ("framing_rate", "blocking_rate"):
                cq = pr[(pr.Pos == "C")].dropna(subset=[comp, comp + "_n"])
                cell[f"{comp.split('_')[0]}_self_persistence"] = {
                    "n_pairs": int(len(cq)), "rho": _r(spearman(cq[comp], cq[comp + "_n"]))}
        out[pos] = cell
    return out


# ---------------------------------------------------------------------------
# the read
# ---------------------------------------------------------------------------

def evaluate(inp: Inputs, b: int = B) -> dict:
    ps = inp_ps = player_seasons(inp)
    twin_drop = permute_sdr(inp.drop, TWIN_SEED)
    twin_variants = {k: permute_sdr(v, TWIN_SEED, pos_col="Pos") for k, v in inp.variants.items()}
    inp_twin = Inputs(drop=twin_drop, fg=inp.fg, split=inp.split, rfield=inp.rfield,
                      team=inp.team, variants=twin_variants, meta=inp.meta)
    ps_twin = player_seasons(inp_twin)

    c1 = c1_read(ps, b=b)
    c2 = c2_read(inp, ps, b=b)
    c1t = c1_read(ps_twin, b=b)
    c2t = c2_read(inp_twin, ps_twin, b=b)
    h = holm({"C1": c1.get("p_one_sided"), "C2": c2.get("p_one_sided")})
    tw = holm({"C1": c1t.get("p_one_sided"), "C2": c2t.get("p_one_sided")})

    def passes(c, hk):
        return bool(c.get("beats_both_at_point") and c.get("lb_above_0") and hk["rejects"])

    clauses = {}
    for k, c, ct in (("C1", c1, c1t), ("C2", c2, c2t)):
        twin_pass = passes(ct, tw[k])
        clauses[k] = {**c, "holm": h[k],
                      "twin": {"rho": ct.get("rho"), "d_point": ct.get("d_point"),
                               "lb95": ct.get("lb95"), "passes_rule": twin_pass},
                      "passes": passes(c, h[k]) and not twin_pass}
    n_pass = sum(1 for v in clauses.values() if v["passes"])
    verdict = {2: "PASS", 1: "PARTIAL", 0: "FAIL"}[n_pass]
    return {
        "clauses": clauses, "verdict": verdict,
        "C3": c3_read(ps), "C4": c4_read(inp.drop, int(inp.drop.season.max())),
        "C5": c5_read(ps, ps_twin, b=b) if inp.variants else {"status": "no variants"},
        "C6": c6_read(ps, b=b), "per_position": per_position(inp, ps, b=b),
    }


# ---------------------------------------------------------------------------
# real inputs
# ---------------------------------------------------------------------------

def _sha_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_real() -> Inputs:
    import sdr_inhouse as S                          # noqa: PLC0415
    import sdr_intake                                # noqa: PLC0415
    drop_path = sdr_intake.newest_accepted("sdr_defense_card")
    if drop_path is None:
        raise SystemExit("no accepted sdr_defense_card drop; run sdr_intake --accept first")
    drop = pd.read_csv(drop_path)
    fg, split, team = {}, {}, {}
    for s in sorted(drop.season.unique()):
        f = pd.read_csv(S.RAW / f"fg_field_full_{s}.csv").rename(columns={"xMLBAMID": "player_id"})
        f["player_id"] = pd.to_numeric(f.player_id, errors="coerce")
        f = f[f.player_id.notna() & f.Pos.isin(POS)].copy()
        f["player_id"] = f.player_id.astype(int)
        fg[int(s)] = f
        sp = pd.read_csv(S.RAW / f"fg_field_split_{s}.csv").rename(columns={"xMLBAMID": "player_id"})
        sp["player_id"] = pd.to_numeric(sp.player_id, errors="coerce")
        sp = sp[sp.player_id.notna() & sp.Pos.isin(POS)].copy()
        sp["player_id"] = sp.player_id.astype(int)
        split[int(s)] = sp
        team[int(s)] = pd.read_csv(S.RAW / f"fg_team_pit_{s}.csv")
    wd = pd.read_parquet(WAR_DAILY)
    wd["player_id"] = pd.to_numeric(wd.mlb_ID, errors="coerce")
    wd["season"] = pd.to_numeric(wd.year_ID, errors="coerce")
    for c in ("runs_field", "Inn"):
        wd[c] = pd.to_numeric(wd[c], errors="coerce")
    wd = wd.dropna(subset=["player_id", "season"])
    rf = wd.groupby(["player_id", "season"], as_index=False).agg(
        runs_field=("runs_field", lambda x: x.sum(min_count=1)), inn=("Inn", "sum"))
    rf = rf.astype({"player_id": int, "season": int})
    variants = {}
    for v in ("no_drs", "no_statcast"):
        parts = []
        for s in sorted(drop.season.unique()):
            p = S.REPORTS / f"06_defense_plus_{s}__{v}.csv"
            if p.exists():
                x = pd.read_csv(p).rename(columns={"id": "player_id", "dplus_runs": "sdr_runs"})
                x["season"] = int(s)
                parts.append(x[["player_id", "season", "Pos", "sdr_runs"]])
        if parts:
            variants[v] = pd.concat(parts, ignore_index=True)
    meta = {
        "drop": {"path": str(drop_path.relative_to(ROOT)).replace("\\", "/"),
                 "sha256": _sha_file(drop_path), "rows": int(len(drop))},
        "war_daily_bat": {"path": ".cache/war_daily/bat.parquet", "sha256": _sha_file(WAR_DAILY),
                          "modified": datetime.fromtimestamp(WAR_DAILY.stat().st_mtime,
                                                             timezone.utc).isoformat()},
        "fetch_manifest": ".cache/sdr/fetch_manifest.json",
        "run_manifest": ".cache/sdr/run_manifest.json",
    }
    return Inputs(drop=drop, fg=fg, split=split, rfield=rf, team=team, variants=variants,
                  meta=meta)


def milb_artifact() -> dict:
    import sdr_inhouse as S                          # noqa: PLC0415
    census = json.loads(CENSUS.read_text(encoding="utf-8")) if CENSUS.exists() else {}
    st = (census.get("streams") or {}).get("sdr_defense_card") or {}
    levels = (st.get("census") or {}).get("rows_by_level") or {}
    milb_rows = sum(v for k, v in levels.items() if k != "MLB")
    tm = S.REPORTS / "15_milb_transition.csv"
    matrix = None
    if tm.exists():
        t = pd.read_csv(tm, index_col=0)
        matrix = {str(i): {str(c): (None if pd.isna(v) else round(float(v) * 100, 1))
                           for c, v in r.items()} for i, r in t.iterrows()}
    hold = {}
    mp = S.DP_HOME / "data" / "processed" / "milb_translation.parquet"
    n_usable = None
    if mp.exists():
        m = pd.read_parquet(mp)
        m = m[m.milb_pos.notna() & (m.total >= 20)]
        n_usable = int(len(m))
        for p in ["C", "SS", "CF", "2B", "3B"]:
            sub = m[m.milb_pos == p]
            if len(sub) >= 8:
                hold[p] = {"n": int(len(sub)), "holds_pct": round(float((sub.mlb_pos == p).mean()) * 100, 1)}
    return {
        "generated_at": date.today().isoformat(),
        "status": "not run" if milb_rows == 0 else "census holds MiLB rows: run the clauses",
        "read_kind": "OWNER-WAIVED EARLY READ (owner decision EW3-5)",
        "registration": "docs/sdr-2026-08-18/MILB_SDR_EVAL_GATE.md",
        "amendment": "Amendment 2026-10-15",
        "question": ("does pre-debut MiLB SDR predict MLB defensive value, vs the FG field grade "
                     "and prospect_def_value re-run on this frame"),
        "census": {"rows_by_level": levels, "milb_rows": int(milb_rows),
                   "source": "data/sdr_census.json"},
        "why_not_run": ("Will's method emits no MiLB defensive runs: 15_milb_translation reads "
                        "position history only (AAA, else AA, primary position by games started) "
                        "and 26_prospect_prior is a scouting-grade and body-frame prior, not a "
                        "minor-league measurement. C1 to C3 have no predictor. This is not a "
                        "finding that MiLB SDR fails to predict."),
        "context_15_milb_translation": {
            "note": ("Will's stage run unedited on cached StatsAPI fielding lines "
                     "(tools/sdr_inhouse.py milb). Descriptive; licenses no claim."),
            "cohort_rule": "MLB position players, first MLB season 2015 or later, 100+ career GS at the primary position",
            "n_usable": n_usable,
            "transition_pct_milb_to_mlb": matrix,
            "position_hold": hold,
            "disclosed_difference": ("Will's usage spine came from his playing_time_model, which "
                                     "is not in the repo; the spine here is StatsAPI MLB fielding "
                                     "games started 2000 to 2026 (DH included), so the cohort "
                                     "differs from his 2026-06-18 run (462 players there)."),
        },
        "licenses": "no public MiLB SDR claim",
    }


def run(write: bool = True, b: int = B) -> dict:
    inp = load_real()
    res = evaluate(inp, b=b)
    doc = {
        "generated_at": date.today().isoformat(),
        "status": "measured",
        "read_kind": "OWNER-WAIVED EARLY READ (owner decision EW3-5)",
        "registration": "docs/sdr-2026-08-18/SDR_EVAL_GATE.md",
        "amendment": "Amendment 2026-10-15 (owner decisions EW3-18, EW3-23)",
        "question": "MLB SDR vs rfield vs OAA/FRP on forward legs (self-persistence, next-season team runs allowed)",
        "inputs": inp.meta,
        "frame": {"seasons": sorted(int(s) for s in inp.drop.season.unique()),
                  "positions": POS, "innings_floor": 300,
                  "predictor_seasons": list(PRED_SEASONS), "bootstrap_b": b,
                  "seed": SEED, "twin_seed": TWIN_SEED, "alpha_holm": ALPHA},
        **res,
    }
    if write:
        OUT_GA.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        OUT_GC.write_text(json.dumps(milb_artifact(), indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="run the reporting path on fixtures with nulls; writes nothing")
    ap.add_argument("--b", type=int, default=B)
    a = ap.parse_args(argv)
    if a.dry_run:
        from test_sdr_eval_gate import fixture_inputs  # noqa: PLC0415
        res = evaluate(fixture_inputs(), b=50)
        print(json.dumps({"verdict": res["verdict"],
                          "C1": res["clauses"]["C1"].get("rho"),
                          "C5": res["C5"].get("disposition")}, indent=1))
        return 0
    doc = run(b=a.b)
    print(json.dumps({"verdict": doc["verdict"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
