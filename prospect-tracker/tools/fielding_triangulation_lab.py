# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fielding triangulation: the fit (once) and the read (once).

Registered in docs/ewar/FIELDING_TRIANGULATION_GATE.md before any number existed;
every choice below is that document's. The pure core is fielding_triangulation.py.

    python tools/fielding_triangulation_lab.py --dry-run   # fixtures with nulls; writes nothing
    python tools/fielding_triangulation_lab.py fit         # data seasons 2016 to 2018 only;
                                                           # writes data/_labs/fielding_triangulation_fit.json
    python tools/fielding_triangulation_lab.py read        # the one read; reads the frozen fit;
                                                           # writes data/fielding_triangulation_eval.json

  L1  next season's fielding runs from a system the candidate did not read (leave one
      system out: DRS with UZR, Statcast, UZR), the mean of three Spearman gaps against a
      single incumbent that does not read the target's system.
  L2  next season's club runs allowed beyond FIP, roster-weighted club sums of the
      player's rate in Y times his innings with the club in Y+1, against FanGraphs
      fielding (the vintage's Fld + Frm).
  Holm k 2, twins permuted within (position, season), PASS / PARTIAL / FAIL, and the
  eligibility of S3t for the eWAR v3 skill look (gate part 5.5).

The loaders are injectable (Inputs), so test_fielding_triangulation.py dry-runs the
whole reporting path on fixtures with nulls and a planted ladder of readings before
the real read.
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
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dem_plus                                   # noqa: E402  (K_INN by reference)
import fielding_triangulation as FT               # noqa: E402

FIT_OUT = ROOT / "data" / "_labs" / "fielding_triangulation_fit.json"
EVAL_OUT = ROOT / "data" / "fielding_triangulation_eval.json"
WAR_DAILY = ROOT / ".cache" / "war_daily" / "bat.parquet"
VINTAGE = ROOT / "data" / "fwar_vintage.json"

SEASONS = tuple(range(2016, 2027))
PRED_SEASONS = tuple(range(2019, 2026))          # Y; outcome Y+1 in 2020 to 2026
UZR_LAST = 2024
FRAME_MIN_INN = 300.0
B = 2000
SEED = 20261016
TWIN_SEED = 20261017
ALPHA = 0.05
NI_MARGIN = -0.02
MDE_Z = 1.645
CARRIES_SHARE = 0.10

#: L1's three systems (gate part 5.2): (target series, T configuration, comparator series)
SYSTEMS = {
    "DRS": ("drs", "X_DRS", "frp"),
    "Statcast": ("frp", "X_SC", "drs"),
    "UZR": ("uzr", "X_UZR", "frp"),
}
#: the SDR reading that matches each system's configuration (part 5.6)
SDR_FOR = {"DRS": "sdr_no_drs", "Statcast": "sdr_no_statcast", "UZR": "sdr_no_drs"}
RUN_COLS = FT.SERIES + ("cframing", "bfrp", "tfrp")
COMP_COL = {"framing": "cframing", "blocking": "bfrp", "throwing": "tfrp"}


@dataclass
class Inputs:
    rows: pd.DataFrame        # player_id, season, pos, inn and the runs of RUN_COLS (NaN = absent)
    split: pd.DataFrame       # season, player_id, teamid, inn (non-pitcher positions)
    team: dict                # season -> DataFrame teamid, R, FIP, IP
    vintage: pd.DataFrame     # player_id, season, fld, frm, pa
    rfield: pd.DataFrame      # player_id, season, runs_field, inn
    meta: dict = field(default_factory=dict)


def _r(v, k=4):
    return None if v is None or not np.isfinite(v) else round(float(v), k)


def _spearman(x, y):
    import sdr_eval_gate as G                     # noqa: PLC0415
    return G.spearman(x, y)


# ---------------------------------------------------------------------------
# preparation: centred rates, the catcher components
# ---------------------------------------------------------------------------

def prepare(rows: pd.DataFrame) -> pd.DataFrame:
    """Every row with x_<series> (non-catcher rows) and x_<component> (catcher rows),
    centred within (position, season) as gate part 3.1 fixes."""
    r = rows.copy()
    nc = r[r.pos != FT.CATCHER]
    c = r[r.pos == FT.CATCHER].copy()
    nc = FT.centred_rates(nc, FT.SERIES)
    for comp, col in COMP_COL.items():
        c[comp] = c[col]
    c = FT.centred_rates(c, FT.CATCHER_COMPONENTS)
    for s in FT.SERIES:
        c[f"x_{s}"] = np.nan
    for comp in FT.CATCHER_COMPONENTS:
        nc[f"x_{comp}"] = np.nan
    return pd.concat([nc, c], ignore_index=True)


def fit(inp: Inputs) -> dict:
    """The one fit: data seasons 2016 to 2018 only."""
    P = prepare(inp.rows[inp.rows.season.isin(FT.FIT_SEASONS)])
    out = {"positions": {}, "catcher": None}
    for pos in FT.NONC_POS:
        m = FT.fit_position(P[P.pos == pos])
        m["weights_full"] = {str(n): FT.weights(m, n, [s for s in FT.CONFIGS["FULL"] if s in m["series"]])
                             for n in (500, 1000)}
        out["positions"][pos] = m
    out["catcher"] = FT.fit_catcher(P[P.pos == FT.CATCHER])
    return out


def apply_fit(fitd: dict, P: pd.DataFrame) -> pd.DataFrame:
    """T rates for each configuration on non-catcher rows, T_C runs on catcher rows,
    and the equal-weight blend of each configuration's readings (reported)."""
    P = P.copy()
    for cfg in FT.CONFIGS:
        P[f"T_{cfg}"] = np.nan
        P[f"EQ_{cfg}"] = np.nan
    P["T_C"] = np.nan
    for pos in FT.NONC_POS:
        m = P.pos == pos
        model = fitd["positions"][pos]
        for cfg, series in FT.CONFIGS.items():
            P.loc[m, f"T_{cfg}"] = FT.t_rates(model, P[m], series)
    mc = P.pos == FT.CATCHER
    P.loc[mc, "T_C"] = FT.catcher_runs(fitd["catcher"], P[mc])
    # equal-weight blend: mean z over present readings, in FRP's runs (reported only)
    nc = P[P.pos != FT.CATCHER]
    sd = {}
    for s in FT.SERIES:
        sd[s] = nc.groupby(["pos", "season"])[f"x_{s}"].transform("std")
    sd_frp = sd["frp"]
    for cfg, series in FT.CONFIGS.items():
        zs = np.column_stack([(nc[f"x_{s}"] / sd[s].replace(0, np.nan)).to_numpy(float) for s in series])
        with np.errstate(invalid="ignore"):
            zbar = np.nanmean(np.where(np.isfinite(zs), zs, np.nan), axis=1)
        P.loc[nc.index, f"EQ_{cfg}"] = np.nan_to_num(zbar) * sd_frp.fillna(0).to_numpy(float)
    return P


# ---------------------------------------------------------------------------
# L1: the forward leg
# ---------------------------------------------------------------------------

def _ps_rate(rows: pd.DataFrame, col: str) -> pd.Series:
    """Innings-weighted mean of a rate over a player-season's rows where it is present."""
    x = rows[col].to_numpy(float)
    ok = np.isfinite(x)
    d = pd.DataFrame({"player_id": rows.player_id.to_numpy(), "season": rows.season.to_numpy(),
                      "wx": np.where(ok, x * rows.inn.to_numpy(float), 0.0),
                      "w": np.where(ok, rows.inn.to_numpy(float), 0.0)})
    g = d.groupby(["player_id", "season"])[["wx", "w"]].sum()
    return (g.wx / g.w.where(g.w > 0)).rename(col)


def l1_frame(P: pd.DataFrame, t_cols=None) -> pd.DataFrame:
    """Player-season rates over frame rows (non-catcher, 300+ innings), joined Y to Y+1."""
    fr = P[(P.pos != FT.CATCHER) & (P.inn >= FRAME_MIN_INN)].copy()
    cols = [f"x_{s}" for s in FT.SERIES] + [f"T_{c}" for c in FT.CONFIGS] + [f"EQ_{c}" for c in FT.CONFIGS]
    cols += list(t_cols or [])
    ps = pd.concat([_ps_rate(fr, c) for c in cols], axis=1)
    # S3 (DEM+'s shrink of FanGraphs fielding), reported: rel x FRP rate
    k = fr.pos.map(dem_plus.K_INN).astype(float)
    kk = pd.DataFrame({"player_id": fr.player_id, "season": fr.season, "ki": k * fr.inn, "inn": fr.inn})
    g = kk.groupby(["player_id", "season"])[["ki", "inn"]].sum()
    rel = g.inn / (g.inn + g.ki / g.inn)
    ps["S3"] = ps["x_frp"] * rel
    ps["inn"] = g.inn
    pos_inn = fr.groupby(["player_id", "season", "pos"]).inn.sum().reset_index()
    prim = pos_inn.sort_values("inn").groupby(["player_id", "season"]).tail(1).set_index(
        ["player_id", "season"]).pos
    ps["primary"] = prim
    ps = ps.reset_index()
    nxt = ps.copy()
    nxt["season"] = nxt.season - 1
    return ps[ps.season.isin(PRED_SEASONS)].merge(nxt, on=["player_id", "season"],
                                                  suffixes=("", "_n")).reset_index(drop=True)


def _sys_cols(sysname: str):
    tgt, cfg, comp = SYSTEMS[sysname]
    return f"T_{cfg}", f"x_{comp}", f"x_{tgt}_n"


def _sys_mask(pr: pd.DataFrame, sysname: str, extra=()) -> np.ndarray:
    tc, cc, yc = _sys_cols(sysname)
    m = pr[tc].notna() & pr[cc].notna() & pr[yc].notna()
    for e in extra:
        m &= pr[e].notna()
    if sysname == "UZR":
        m &= (pr.season + 1) <= UZR_LAST
    return m.to_numpy()


def _gap(pr, idx, sysname, a_col, b_col):
    m = _sys_mask(pr, sysname, (a_col, b_col))[idx]
    q = pr.iloc[idx[m]]
    _, _, yc = _sys_cols(sysname)
    ra, rb = _spearman(q[a_col], q[yc]), _spearman(q[b_col], q[yc])
    return None if ra is None or rb is None else ra - rb


def _boot_idx(groups: np.ndarray, b: int, seed: int):
    uniq, inv = np.unique(groups, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(len(uniq))]
    rng = np.random.default_rng(seed)
    for _ in range(b):
        pick = rng.integers(0, len(members), len(members))
        yield np.concatenate([members[k] for k in pick]) if len(members) else np.array([], int)


def _summ(draws) -> dict:
    d = np.asarray([x for x in draws if x is not None and np.isfinite(x)], float)
    if not len(d):
        return {"n_draws": 0, "sd": None, "lb95": None, "ub95": None, "p_one_sided": None,
                "mde95": None, "half_width95": None}
    lb, ub = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
    return {"n_draws": int(len(d)), "sd": _r(d.std(ddof=1)), "lb95": _r(lb), "ub95": _r(ub),
            "p_one_sided": _r(float(np.mean(d <= 0)), 5), "mde95": _r(MDE_Z * d.std(ddof=1)),
            "half_width95": _r((ub - lb) / 2.0)}


def pair_cell(pr: pd.DataFrame, pairs: dict, b: int, seed: int, systems=tuple(SYSTEMS)) -> dict:
    """The mean over systems of rho(a) - rho(b) on each system's target, with one
    player-clustered bootstrap. pairs: system -> (a column, b column)."""
    idx0 = np.arange(len(pr))
    per = {}
    for s in systems:
        a, bb = pairs[s]
        m = _sys_mask(pr, s, (a, bb))
        q = pr[m]
        _, _, yc = _sys_cols(s)
        ra, rb = _spearman(q[a], q[yc]), _spearman(q[bb], q[yc])
        per[s] = {"n_pairs": int(m.sum()), "rho_a": _r(ra), "rho_b": _r(rb),
                  "gap": _r(ra - rb) if None not in (ra, rb) else None,
                  "target": f"{SYSTEMS[s][0]} per inning, Y+1"}
    gaps = [per[s]["gap"] for s in systems if per[s]["gap"] is not None]
    point = float(np.mean([pr_ for pr_ in gaps])) if len(gaps) == len(systems) else None
    draws = []
    for idx in _boot_idx(pr.player_id.to_numpy(), b, seed):
        gs = [_gap(pr, idx, s, *pairs[s]) for s in systems]
        draws.append(np.nan if any(g is None for g in gs) else float(np.mean(gs)))
    # exact point recomputed unrounded
    exact = []
    for s in systems:
        g = _gap(pr, idx0, s, *pairs[s])
        exact.append(g)
    point = float(np.mean(exact)) if all(g is not None for g in exact) else None
    return {"per_system": per, "gap_point": _r(point), **_summ(draws)}


def l1_read(pr: pd.DataFrame, b: int, seed: int) -> dict:
    pairs = {s: (f"T_{SYSTEMS[s][1]}", f"x_{SYSTEMS[s][2]}") for s in SYSTEMS}
    return pair_cell(pr, pairs, b, seed)


# ---------------------------------------------------------------------------
# L2: the team leg
# ---------------------------------------------------------------------------

def _club_target(team: dict) -> pd.DataFrame:
    import sdr_eval_gate as G                     # noqa: PLC0415

    class _T:
        pass
    t = _T()
    t.team = team
    return G.club_target(t)


def player_rates_y(inp: Inputs, P: pd.DataFrame, tcol: str = "T_FULL") -> pd.DataFrame:
    """Per player-season (every rated row, every position): T, the base, SDR, S3, rfield."""
    r = P.copy()
    nonc = r.pos != FT.CATCHER
    r["t_runs"] = np.where(nonc, r[tcol].fillna(0.0) * r.inn / FT.PER, r["T_C"].fillna(0.0))
    r["sdr_runs_c"] = np.where(nonc, r["x_sdr"].fillna(0.0) * r.inn / FT.PER, 0.0)
    r["caught"] = (~nonc) & (r.inn > 0)
    r["k_inn"] = r.pos.map(dem_plus.K_INN).astype(float) * r.inn
    g = r.groupby(["player_id", "season"]).agg(inn=("inn", "sum"), t_runs=("t_runs", "sum"),
                                               sdr_runs=("sdr_runs_c", "sum"),
                                               caught=("caught", "any"), k_inn=("k_inn", "sum"))
    g = g.reset_index()
    v = inp.vintage[["player_id", "season", "fld", "frm"]]
    g = g.merge(v, on=["player_id", "season"], how="left")
    g["b0_runs"] = g.fld.fillna(0.0) + np.where(g.caught, g.frm.fillna(0.0), 0.0)
    g["rate_T"] = np.where(g.inn > 0, g.t_runs / g.inn, 0.0)
    g["rate_B0"] = np.where(g.inn > 0, g.b0_runs / g.inn, 0.0)
    g["rate_SDR"] = np.where(g.inn > 0, g.sdr_runs / g.inn, 0.0)
    rel = g.inn / (g.inn + np.where(g.inn > 0, g.k_inn / g.inn.where(g.inn > 0, 1.0), 0.0))
    g["rate_S3"] = g.rate_B0 * rel
    rf = inp.rfield[["player_id", "season", "runs_field", "inn"]].rename(columns={"inn": "rf_inn"})
    g = g.merge(rf, on=["player_id", "season"], how="left")
    g["rate_RF"] = np.where(g.rf_inn > 0, g.runs_field / g.rf_inn.where(g.rf_inn > 0, 1.0), 0.0)
    g["rate_RF"] = g.rate_RF.fillna(0.0)
    return g


def l2_contrib(inp: Inputs, rates: pd.DataFrame) -> pd.DataFrame:
    """(season Y, teamid, player_id, n_next) with the player's Y rates; Y+1 innings with c."""
    sp = inp.split.copy()
    sp = sp[sp.season.isin([y + 1 for y in PRED_SEASONS])]
    sp = sp.groupby(["season", "teamid", "player_id"], as_index=False).inn.sum()
    sp = sp.rename(columns={"inn": "n_next"})
    sp["season"] = sp.season - 1
    keep = ["player_id", "season", "rate_T", "rate_B0", "rate_SDR", "rate_S3", "rate_RF"]
    c = sp.merge(rates[keep], on=["player_id", "season"], how="left")
    for k in keep[2:]:
        c[k] = c[k].fillna(0.0)
    return c


def _club_z(contrib: pd.DataFrame, col: str, w=None) -> pd.DataFrame:
    v = contrib[col].to_numpy(float) * contrib.n_next.to_numpy(float)
    if w is not None:
        v = v * w
    s = pd.DataFrame({"season": contrib.season.to_numpy(), "teamid": contrib.teamid.to_numpy(), "v": v})
    s = s.groupby(["season", "teamid"], as_index=False).v.sum()
    s["z"] = s.groupby("season").v.transform(
        lambda x: (x - x.mean()) / x.std(ddof=1) if x.std(ddof=1) > 0 else x * 0)
    return s


def _club_pairs(contrib, target, col, w=None):
    s = _club_z(contrib, col, w)
    t = target.copy()
    t["season"] = t.season - 1
    return s.merge(t, on=["season", "teamid"], how="inner")


def l2_read(inp: Inputs, rates: pd.DataFrame, b: int, seed: int, cols=("rate_T", "rate_B0")) -> dict:
    target = _club_target(inp.team)
    contrib = l2_contrib(inp, rates)
    a, bb = cols
    Pa, Pb = _club_pairs(contrib, target, a), _club_pairs(contrib, target, bb)
    ra, rb = _spearman(Pa.z, Pa.target), _spearman(Pb.z, Pb.target)
    players = np.unique(contrib.player_id.to_numpy())
    pos_of = {p: i for i, p in enumerate(players)}
    pidx = contrib.player_id.map(pos_of).to_numpy()
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(b):
        w = np.bincount(rng.integers(0, len(players), len(players)),
                        minlength=len(players)).astype(float)[pidx]
        x1, x2 = _club_pairs(contrib, target, a, w), _club_pairs(contrib, target, bb, w)
        r1, r2 = _spearman(x1.z, x1.target), _spearman(x2.z, x2.target)
        draws.append(np.nan if None in (r1, r2) else r1 - r2)
    fr = Pa[["season", "teamid", "z", "target"]].rename(columns={"z": "za"}).merge(
        Pb[["season", "teamid", "z"]].rename(columns={"z": "zb"}), on=["season", "teamid"])
    cl = []
    for idx in _boot_idx(fr.teamid.to_numpy(), b, seed):
        q = fr.iloc[idx]
        r1, r2 = _spearman(q.za, q.target), _spearman(q.zb, q.target)
        cl.append(np.nan if None in (r1, r2) else r1 - r2)
    gap = None if None in (ra, rb) else ra - rb
    ps, cs = _summ(draws), _summ(cl)
    ni = (gap is not None and ps["sd"] is not None and cs["sd"] is not None
          and gap - MDE_Z * ps["sd"] > NI_MARGIN and gap - MDE_Z * cs["sd"] > NI_MARGIN)
    no20 = {k: _r(_spearman(v[(v.season != 2019) & (v.season != 2020)].z,
                            v[(v.season != 2019) & (v.season != 2020)].target))
            for k, v in ((a, Pa), (bb, Pb))}
    return {"n_club_pairs": int(len(Pa)), "rho": {a: _r(ra), bb: _r(rb)}, "gap_point": _r(gap),
            **ps, "club_clustered_beside": cs, "non_inferior": bool(ni),
            "without_2020_pairs": no20}


# ---------------------------------------------------------------------------
# twins, Holm, the read
# ---------------------------------------------------------------------------

def holm(ps: dict, alpha: float = ALPHA) -> dict:
    import sdr_eval_gate as G                     # noqa: PLC0415
    return G.holm(ps, alpha)


def twin_P(P: pd.DataFrame, frame_only: bool) -> pd.DataFrame:
    """T's row rates permuted within (position, season), seed TWIN_SEED, one draw per
    configuration; L1's twin permutes among its frame rows, L2's among every rated row."""
    Q = P.copy()
    nonc = Q.pos != FT.CATCHER
    sel = nonc & ((Q.inn >= FRAME_MIN_INN) if frame_only else True)
    idx = np.flatnonzero(sel.to_numpy())
    for cfg in FT.CONFIGS:
        col = f"T_{cfg}"
        vals = Q[col].to_numpy(float).copy()
        vals[idx] = FT.permute_within(vals[idx], Q.iloc[idx][["pos", "season"]].reset_index(drop=True),
                                      TWIN_SEED)
        Q[col] = vals
    if not frame_only:
        ci = np.flatnonzero((~nonc).to_numpy())
        if len(ci):
            inn = Q.inn.to_numpy(float)[ci]
            rate = np.where(inn > 0, Q.T_C.to_numpy(float)[ci] / np.where(inn > 0, inn, 1.0), 0.0)
            rate = FT.permute_within(rate, Q.iloc[ci][["pos", "season"]].reset_index(drop=True), TWIN_SEED)
            tc = Q.T_C.to_numpy(float).copy()
            tc[ci] = rate * inn
            Q["T_C"] = tc
    return Q


def _passes(c: dict, hk: dict) -> bool:
    return bool(c.get("gap_point") is not None and c["gap_point"] > 0 and c.get("lb95") is not None
                and c["lb95"] > 0 and hk["rejects"])


def per_position(P: pd.DataFrame, b: int, seed: int) -> dict:
    """Row-level pairs (same player and position, 300+ innings both seasons): the three
    gaps of L1 and SDR alone minus T, per position (reported)."""
    fr = P[(P.pos != FT.CATCHER) & (P.inn >= FRAME_MIN_INN)]
    nxt = fr.copy()
    nxt["season"] = nxt.season - 1
    pr = fr[fr.season.isin(PRED_SEASONS)].merge(nxt, on=["player_id", "season", "pos"],
                                                suffixes=("", "_n")).reset_index(drop=True)
    out = {}
    for pos in FT.NONC_POS:
        q = pr[pr.pos == pos].reset_index(drop=True)
        tri = pair_cell(q, {s: (f"T_{SYSTEMS[s][1]}", f"x_{SYSTEMS[s][2]}") for s in SYSTEMS}, b, seed)
        sdr = pair_cell(q, {s: (f"x_{SDR_FOR[s]}", f"T_{SYSTEMS[s][1]}") for s in SYSTEMS}, b, seed)
        out[pos] = {"n_row_pairs": int(len(q)), "triangulation_vs_single": tri, "sdr_minus_triangulation": sdr}
    return out


def catcher_cell(P: pd.DataFrame, b: int, seed: int) -> dict:
    c = P[P.pos == FT.CATCHER].copy()
    c["b0_runs"] = c.frp.fillna(0.0) + c.cframing.fillna(0.0)
    c = FT.centred_rates(c, ("b0_runs", "drs"))         # amendment A1: centred within season
    c = c[c.inn >= FRAME_MIN_INN].copy()
    c["t_rate"] = c.T_C / c.inn * FT.PER
    c["b0_rate"] = c.x_b0_runs
    c["drs_rate"] = c.x_drs
    nxt = c[["player_id", "season", "drs_rate"]].copy()
    nxt["season"] = nxt.season - 1
    q = c[c.season.isin(PRED_SEASONS)].merge(nxt, on=["player_id", "season"], suffixes=("", "_n"))
    q = q.dropna(subset=["t_rate", "b0_rate", "drs_rate_n"]).reset_index(drop=True)
    ra, rb = _spearman(q.t_rate, q.drs_rate_n), _spearman(q.b0_rate, q.drs_rate_n)
    draws = []
    for idx in _boot_idx(q.player_id.to_numpy(), b, seed):
        x = q.iloc[idx]
        r1, r2 = _spearman(x.t_rate, x.drs_rate_n), _spearman(x.b0_rate, x.drs_rate_n)
        draws.append(np.nan if None in (r1, r2) else r1 - r2)
    return {"n_pairs": int(len(q)), "target": "DRS per inning at C, Y+1",
            "rho": {"T_C": _r(ra), "base_FRP_plus_CFraming": _r(rb)},
            "gap_point": _r(None if None in (ra, rb) else ra - rb), **_summ(draws)}


def agreement(P: pd.DataFrame) -> dict:
    fr = P[(P.pos != FT.CATCHER) & (P.inn >= FRAME_MIN_INN) & P.season.isin(range(2019, 2027))]
    return {s: {"n": int(fr[f"x_{s}"].notna().sum()),
                "spearman_same_season": _r(_spearman(fr["T_FULL"], fr[f"x_{s}"]))} for s in FT.SERIES}


def face_validity(P: pd.DataFrame, names: dict, season: int, n: int = 10) -> dict:
    d = P[P.season == season].copy()
    d["t_runs"] = np.where(d.pos != FT.CATCHER, d.T_FULL * d.inn / FT.PER, d.T_C)
    def rec(r):
        return {"player": names.get(int(r.player_id), str(int(r.player_id))),
                "player_id": int(r.player_id), "innings": round(float(r.inn), 1),
                "t_runs": round(float(r.t_runs), 1)}

    out = {}
    for pos in FT.NONC_POS + (FT.CATCHER,):
        g = d[d.pos == pos].sort_values("t_runs", ascending=False)
        out[pos] = {"n": int(len(g)), "top": [rec(r) for r in g.head(n).itertuples()],
                    "bottom": [rec(r) for r in g.tail(n).iloc[::-1].itertuples()]}
    return {"season": season, "by_position": out}


def weights_table(fitd: dict) -> dict:
    out = {}
    for pos, m in fitd["positions"].items():
        w = m["weights_full"]["1000"]
        out[pos] = {
            "loadings": dict(zip(m["series"], [_r(x, 3) for x in m["lambda"]])),
            "w_1000": {s: _r(v["w"], 4) for s, v in w.items()},
            "share_abs_1000": {s: _r(v["share_abs"], 3) for s, v in w.items()},
            "carries_weight": sorted(s for s, v in w.items() if v["share_abs"] >= CARRIES_SHARE),
            "w_500": {s: _r(v["w"], 4) for s, v in m["weights_full"]["500"].items()},
            "dropped": m["dropped"], "dem_plus": "nested in FRP (gate part 2)",
        }
    return out


def evaluate(inp: Inputs, fitd: dict, b: int = B, log=print, names=None) -> dict:
    P = apply_fit(fitd, prepare(inp.rows))
    pr = l1_frame(P)
    P1t = twin_P(P, frame_only=True)
    pr_t = l1_frame(P1t)
    rates = player_rates_y(inp, P[P.season.isin(PRED_SEASONS)])
    rates_t = player_rates_y(inp, twin_P(P, frame_only=False)[lambda d: d.season.isin(PRED_SEASONS)])

    l1 = l1_read(pr, b, SEED)
    l2 = l2_read(inp, rates, b, SEED)
    # floors first
    log("FLOORS (bootstrap sd, 95% half-width, MDE95 = 1.645 sd; no gap printed here)")
    for k, c in (("L1", l1), ("L2", l2)):
        log(f"  {k}: sd {c['sd']}  half-width {c['half_width95']}  MDE95 {c['mde95']}")
    l1t = l1_read(pr_t, b, SEED)
    l2t = l2_read(inp, rates_t, b, SEED)
    h = holm({"L1": l1.get("p_one_sided"), "L2": l2.get("p_one_sided")})
    ht = holm({"L1": l1t.get("p_one_sided"), "L2": l2t.get("p_one_sided")})
    legs = {}
    for k, c, ct in (("L1", l1, l1t), ("L2", l2, l2t)):
        tw = _passes(ct, ht[k])
        legs[k] = {**c, "holm": h[k],
                   "twin": {"gap_point": ct.get("gap_point"), "lb95": ct.get("lb95"),
                            "ub95": ct.get("ub95"), "p_one_sided": ct.get("p_one_sided"),
                            "passes_rule": tw},
                   "passes": _passes(c, h[k]) and not tw}
    n_pass = sum(1 for v in legs.values() if v["passes"])
    verdict = {2: "PASS", 1: "PARTIAL", 0: "FAIL"}[n_pass]
    eligible = bool(legs["L1"]["passes"] and l2["non_inferior"])

    # reported beside
    sdr_alone = pair_cell(pr, {s: (f"x_{SDR_FOR[s]}", f"T_{SYSTEMS[s][1]}") for s in SYSTEMS}, b, SEED)
    s3 = pair_cell(pr, {s: ("S3", f"x_{SYSTEMS[s][2]}") for s in ("DRS", "UZR")}, b, SEED,
                   systems=("DRS", "UZR"))
    s3_vs_t = pair_cell(pr, {s: (f"T_{SYSTEMS[s][1]}", "S3") for s in ("DRS", "UZR")}, b, SEED,
                        systems=("DRS", "UZR"))
    eq = pair_cell(pr, {s: (f"EQ_{SYSTEMS[s][1]}", f"x_{SYSTEMS[s][2]}") for s in SYSTEMS}, b, SEED)
    t_vs_eq = pair_cell(pr, {s: (f"T_{SYSTEMS[s][1]}", f"EQ_{SYSTEMS[s][1]}") for s in SYSTEMS}, b, SEED)
    no20 = pr[(pr.season != 2019) & (pr.season != 2020)].reset_index(drop=True)
    l1_no20 = pair_cell(no20, {s: (f"T_{SYSTEMS[s][1]}", f"x_{SYSTEMS[s][2]}") for s in SYSTEMS}, 0, SEED)
    l2_beside = {k: l2_read(inp, rates, 0, SEED, cols=(f"rate_{k}", "rate_B0"))["rho"]
                 for k in ("SDR", "S3", "RF")}
    return {
        "legs": legs, "holm": h, "verdict": verdict,
        "s3t_eligible_for_skill_look": eligible,
        "eligibility_rule": "L1 passes AND L2 NON-INFERIOR (gate part 5.5)",
        "reported": {
            "weights_by_position": weights_table(fitd),
            "catcher_K": {k: {kk: (_r(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                          for k, v in fitd["catcher"].items()},
            "sdr_alone_minus_triangulation": sdr_alone,
            "s3_vs_single_DRS_UZR": s3, "triangulation_minus_s3_DRS_UZR": s3_vs_t,
            "equal_weight_blend_vs_single": eq, "triangulation_minus_equal_weight": t_vs_eq,
            "l1_without_2020_pairs": {"n_pairs": int(len(no20)), "per_system": l1_no20["per_system"],
                                      "gap_point": l1_no20["gap_point"]},
            "l2_rho_beside": l2_beside,
            "per_position": per_position(P, b, SEED),
            "catchers": catcher_cell(P, b, SEED),
            "same_season_agreement": agreement(P),
            "face_validity": face_validity(P, names or {}, int(P.season.max())),
        },
        "counts": {"rows": int(len(P)), "l1_pairs": int(len(pr)), "l1_players": int(pr.player_id.nunique()),
                   "l2_rates_rows": int(len(rates))},
    }


# ---------------------------------------------------------------------------
# real inputs
# ---------------------------------------------------------------------------

def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_real() -> tuple[Inputs, dict]:
    import sdr_eval_gate as G                     # noqa: PLC0415
    import sdr_inhouse as S                       # noqa: PLC0415
    import saber_feed                             # noqa: PLC0415
    import sdr_intake                             # noqa: PLC0415
    rows, split, team, shas, names = [], [], {}, {}, {}
    for s in SEASONS:
        fp = S.RAW / f"fg_field_full_{s}.csv"
        f = pd.read_csv(fp)
        shas[fp.name] = _sha(fp)
        f["player_id"] = pd.to_numeric(f.xMLBAMID, errors="coerce")
        f = f[f.player_id.notna() & (f.Pos != "P")].copy()
        f["player_id"] = f.player_id.astype(int)
        for pid, nm in zip(f.player_id, f.PlayerName):
            names[int(pid)] = str(nm)
        d = pd.DataFrame({"player_id": f.player_id, "season": s, "pos": f.Pos,
                          "inn": f.Inn.map(G.fg_ip),
                          "drs": pd.to_numeric(f.DRS, errors="coerce"),
                          "uzr": pd.to_numeric(f.UZR, errors="coerce"),
                          "oaa": pd.to_numeric(f.OAA, errors="coerce"),
                          "frp": pd.to_numeric(f.FRP, errors="coerce"),
                          "cframing": pd.to_numeric(f.CFraming, errors="coerce"),
                          "bfrp": pd.to_numeric(f.bFRP, errors="coerce"),
                          "tfrp": pd.to_numeric(f.tFRP, errors="coerce")})
        d = d[d.pos.isin(FT.NONC_POS + (FT.CATCHER,))]
        rows.append(d)
        sp_path = S.RAW / f"fg_field_split_{s}.csv"
        sp = pd.read_csv(sp_path)
        shas[sp_path.name] = _sha(sp_path)
        sp["player_id"] = pd.to_numeric(sp.xMLBAMID, errors="coerce")
        sp = sp[sp.player_id.notna() & (sp.Pos != "P")].copy()
        split.append(pd.DataFrame({"season": s, "player_id": sp.player_id.astype(int),
                                   "teamid": pd.to_numeric(sp.teamid, errors="coerce"),
                                   "inn": sp.Inn.map(G.fg_ip)}).dropna(subset=["teamid"]))
        tp = S.RAW / f"fg_team_pit_{s}.csv"
        team[s] = pd.read_csv(tp)
        shas[tp.name] = _sha(tp)
    R = pd.concat(rows, ignore_index=True)
    if R.duplicated(["player_id", "season", "pos"]).any():
        raise SystemExit("duplicate player-season-position rows in the FanGraphs fielding cache")
    drop_path = sdr_intake.newest_accepted("sdr_defense_card")
    drop = pd.read_csv(drop_path)
    shas["sdr_drop"] = _sha(drop_path)
    sdr = drop[["player_id", "season", "primary_position", "sdr_runs"]].rename(
        columns={"primary_position": "pos", "sdr_runs": "sdr"})
    R = R.merge(sdr, on=["player_id", "season", "pos"], how="left", validate="one_to_one")
    for v, col in (("no_drs", "sdr_no_drs"), ("no_statcast", "sdr_no_statcast")):
        parts = []
        for s in SEASONS:
            p = S.REPORTS / f"06_defense_plus_{s}__{v}.csv"
            if p.exists():
                x = pd.read_csv(p).rename(columns={"id": "player_id", "Pos": "pos", "dplus_runs": col})
                x["season"] = s
                parts.append(x[["player_id", "season", "pos", col]])
                shas[p.name] = _sha(p)
        vv = pd.concat(parts, ignore_index=True)
        R = R.merge(vv, on=["player_id", "season", "pos"], how="left", validate="one_to_one")
    # the frozen vintage: Fld, Frm, PA
    blob = json.loads(VINTAGE.read_text(encoding="utf-8"))
    F = blob["fields"]["hitting"]
    vrows = []
    for s in SEASONS:
        hit = ((blob.get("seasons") or {}).get(str(s)) or {}).get("hitting") or {}
        for pid, arr in (hit.get("rows") or {}).items():
            st = dict(zip(F, arr))
            vrows.append({"player_id": int(pid), "season": s, "fld": st.get("fielding"),
                          "frm": saber_feed.framing_residual(st), "pa": st.get("plateAppearances")})
    vint = pd.DataFrame(vrows)
    wd = pd.read_parquet(WAR_DAILY)
    wd["player_id"] = pd.to_numeric(wd.mlb_ID, errors="coerce")
    wd["season"] = pd.to_numeric(wd.year_ID, errors="coerce")
    for c in ("runs_field", "Inn"):
        wd[c] = pd.to_numeric(wd[c], errors="coerce")
    wd = wd.dropna(subset=["player_id", "season"])
    rf = wd.groupby(["player_id", "season"], as_index=False).agg(
        runs_field=("runs_field", lambda x: x.sum(min_count=1)), inn=("Inn", "sum"))
    rf = rf.astype({"player_id": int, "season": int})
    meta = {"inputs_sha256": shas, "fwar_vintage_id": blob.get("vintage_id"),
            "fwar_vintage_sha256": _sha(VINTAGE),
            "sdr_drop": str(drop_path.relative_to(ROOT)).replace("\\", "/"),
            "war_daily_bat": {"sha256": _sha(WAR_DAILY), "modified": datetime.fromtimestamp(
                WAR_DAILY.stat().st_mtime, timezone.utc).isoformat()},
            "fetch_manifest": ".cache/sdr/fetch_manifest.json"}
    return Inputs(rows=R, split=pd.concat(split, ignore_index=True), team=team, vintage=vint,
                  rfield=rf, meta=meta), names


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def run_fit(write: bool = True) -> dict:
    inp, _ = load_real()
    fitd = fit(inp)
    doc = {"generated_at": date.today().isoformat(),
           "registration": "docs/ewar/FIELDING_TRIANGULATION_GATE.md part 3",
           "read_kind": "OWNER-WAIVED EARLY READ (owner decision EW3-5)",
           "fit_seasons": list(FT.FIT_SEASONS), "cross_years": list(FT.CROSS_YEARS),
           "floors": {"same_min_inn": FT.SAME_MIN_INN, "cross_min_inn": FT.CROSS_MIN_INN,
                      "catcher_pair_min_inn": FT.CATCHER_PAIR_MIN_INN,
                      "min_same_rows": FT.MIN_SAME_ROWS, "min_cross_pairs": FT.MIN_CROSS_PAIRS,
                      "psi_floor": FT.PSI_FLOOR},
           "inputs": inp.meta, **fitd}
    doc = _jsonable(doc)
    if write:
        FIT_OUT.parent.mkdir(parents=True, exist_ok=True)
        FIT_OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def run_read(write: bool = True, b: int = B) -> dict:
    if not FIT_OUT.exists():
        raise SystemExit("no frozen fit: run the fit first")
    fitd = json.loads(FIT_OUT.read_text(encoding="utf-8"))
    inp, names = load_real()
    res = evaluate(inp, fitd, b=b, names=names)
    doc = {"generated_at": date.today().isoformat(), "status": "measured",
           "read_kind": "OWNER-WAIVED EARLY READ (owner decision EW3-5)",
           "registration": "docs/ewar/FIELDING_TRIANGULATION_GATE.md",
           "question": ("does a reliability-weighted triangulation of SDR, OAA, DRS, UZR and FanGraphs "
                        "fielding rank next season's fielding runs from a system it did not read, and "
                        "next season's club runs allowed beyond FIP, better than FanGraphs fielding"),
           "fit": {"path": "data/_labs/fielding_triangulation_fit.json", "sha256": _sha(FIT_OUT)},
           "inputs": inp.meta,
           "frame": {"predictor_seasons": list(PRED_SEASONS), "frame_min_inn": FRAME_MIN_INN,
                     "uzr_last_target": UZR_LAST, "bootstrap_b": b, "seed": SEED,
                     "twin_seed": TWIN_SEED, "alpha_holm": ALPHA, "ni_margin": NI_MARGIN},
           **res}
    doc = _jsonable(doc)
    if write:
        EVAL_OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=("fit", "read"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--b", type=int, default=B)
    a = ap.parse_args(argv)
    if a.dry_run:
        from test_fielding_triangulation import fixture_inputs  # noqa: PLC0415
        inp = fixture_inputs()
        fitd = fit(inp)
        res = evaluate(inp, fitd, b=40)
        print(json.dumps({"verdict": res["verdict"], "eligible": res["s3t_eligible_for_skill_look"],
                          "L1": res["legs"]["L1"]["gap_point"], "L2": res["legs"]["L2"]["gap_point"]},
                         indent=1))
        return 0
    if a.cmd == "fit":
        doc = run_fit()
        print(json.dumps({p: {"series": m["series"], "dropped": m["dropped"]}
                          for p, m in doc["positions"].items()}, indent=1))
        return 0
    if a.cmd == "read":
        doc = run_read(b=a.b)
        print(json.dumps({"verdict": doc["verdict"], "eligible": doc["s3t_eligible_for_skill_look"]},
                         indent=1))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
