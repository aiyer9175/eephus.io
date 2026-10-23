# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR pitching blend read's pure core (task EWAR_PITCHING_BLEND, owner EW3-50).

docs/ewar-v3/EWAR_PITCHING_BLEND_GATE.md. A pitcher-season's FanGraphs FIP-based runs
(F9) and Baseball-Reference's runs-allowed-based runs (B9), both runs prevented above
average per 9 innings, are blended with a weight w(IP, role) from within-season
split-half reliability (odd and even appearances) and the cross-source covariance:
the latent-variable weight on runs-allowed talent, fitted in forward-chained folds.

This module reads nothing and writes nothing: tools/ewar_pitching_blend_lab.py
assembles the inputs. Everything here is numpy on arrays the lab hands in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional, Sequence

import numpy as np

VERSION = "ewar_pitching_blend_v1"
GATE_DOC = "docs/ewar-v3/EWAR_PITCHING_BLEND_GATE.md"

SEED = 20261023
BOOT_B = 4000
Z = 1.645
ALPHA = 0.05

FIT_SEASONS: tuple[int, ...] = (2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
PREDICTOR_SEASONS: tuple[int, ...] = (2017, 2018, 2021, 2022, 2023, 2024)
PAIR_FLOOR_IP = 50.0
SPLIT_MIN_IP = 10.0
CELL_MIN = 30
BAND_EDGES: tuple[float, ...] = (20.0, 40.0, 100.0)          # bands 0-20, 20-40, 40-100, 100+
BAND_NAMES: tuple[str, ...] = ("0-20", "20-40", "40-100", "100+")
ROLES: tuple[str, ...] = ("SP", "RP")
SP_SHARE = 0.5
MARGIN_RUNS = 1.0
BOOTS_I: tuple[str, ...] = ("player", "club")
COMPARATORS_I: tuple[str, ...] = ("F9", "B9")
W_EPS = 1e-9

# the planted check (gate part 8)
PLANTED_REPS = 20
PLANTED_B = 500
PLANTED_PASS_MIN = 16
PLANTED_FAKE_MAX = 1
PLANTED_ALPHA = 0.025
PLANTED_W_TOL = 0.10
PLANTED_RHO = 0.75
PLANTED_SD_TF = {"SP": 0.5, "RP": 0.7}
PLANTED_SD_U = {"SP": 0.3, "RP": 0.4}
PLANTED_SIGMA_F = 2.7
PLANTED_SIGMA_B = 5.0
PLANTED_ERR_CORR = 0.5
PLANTED_SIGMA_T = 5.0


class BlendRefusal(RuntimeError):
    """A refusal of gate part 10: the message names the season and the cause."""


# ------------------------------------------------------------------ helpers
def band_of(ip) -> np.ndarray:
    """The IP band index of each value (a value below 10 IP takes band 0)."""
    return np.searchsorted(np.asarray(BAND_EDGES), np.asarray(ip, float), side="right")


def role_code(gs, gp) -> np.ndarray:
    """0 for SP (games started over games pitched at least 0.5), 1 for RP."""
    gs = np.asarray(gs, float)
    gp = np.asarray(gp, float)
    share = np.where(gp > 0, gs / np.where(gp > 0, gp, 1.0), 0.0)
    return np.where(share >= SP_SHARE, 0, 1)


def centre_within_season(x: np.ndarray, ip: np.ndarray, season: np.ndarray,
                         mask: Optional[np.ndarray] = None) -> np.ndarray:
    """x minus its season's IP-weighted mean over the rows of `mask` (finite x)."""
    x = np.asarray(x, float)
    out = np.full_like(x, np.nan)
    m0 = np.isfinite(x) & (np.asarray(ip, float) > 0)
    if mask is not None:
        m0 &= mask
    for s in np.unique(season):
        ms = (season == s) & m0
        if not ms.any():
            continue
        mu = float(np.sum(ip[ms] * x[ms]) / np.sum(ip[ms]))
        sel = (season == s) & np.isfinite(x)
        out[sel] = x[sel] - mu
    return out


def phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def p_upper(stat: float, sd: float) -> float:
    """One-sided p of stat > 0 under a normal approximation with the bootstrap sd."""
    if not (math.isfinite(stat) and math.isfinite(sd)) or sd <= 0:
        return 0.0 if (math.isfinite(stat) and stat > 0 and sd == 0) else 1.0
    return 1.0 - phi(stat / sd)


def holm(ps: Mapping[str, float], alpha: float = ALPHA) -> dict:
    """Holm step-down over the named p-values: {name: rejected}."""
    order = sorted(ps, key=lambda k: ps[k])
    out = {k: False for k in ps}
    m = len(order)
    for i, k in enumerate(order):
        if ps[k] <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out


# ------------------------------------------------------------------ rows
@dataclass
class Rows:
    """Pitcher-seasons. f9 and b9 are centred within season (NaN where absent).
    The split columns are NaN where the row has no split (part 3)."""
    season: np.ndarray
    player: np.ndarray            # MLBAM id
    role: np.ndarray              # 0 SP, 1 RP
    ip: np.ndarray
    f9: np.ndarray
    b9: np.ndarray
    ip_o: np.ndarray
    ip_e: np.ndarray
    f_o: np.ndarray
    f_e: np.ndarray
    b_o: np.ndarray
    b_e: np.ndarray

    def __post_init__(self):
        for k in ("season", "player", "role"):
            setattr(self, k, np.asarray(getattr(self, k), int))
        for k in ("ip", "f9", "b9", "ip_o", "ip_e", "f_o", "f_e", "b_o", "b_e"):
            setattr(self, k, np.asarray(getattr(self, k), float))
        self.band = band_of(self.ip)

    @property
    def n(self) -> int:
        return len(self.season)

    def both(self) -> np.ndarray:
        return np.isfinite(self.f9) & np.isfinite(self.b9) & (self.ip > 0)

    def split(self) -> np.ndarray:
        return (self.both() & (self.ip >= SPLIT_MIN_IP) & (self.ip_o > 0) & (self.ip_e > 0)
                & np.isfinite(self.f_o) & np.isfinite(self.f_e)
                & np.isfinite(self.b_o) & np.isfinite(self.b_e))

    def with_values(self, **kw) -> "Rows":
        d = {k: getattr(self, k) for k in ("season", "player", "role", "ip", "f9", "b9",
                                             "ip_o", "ip_e", "f_o", "f_e", "b_o", "b_e")}
        d.update(kw)
        return Rows(**d)


# ------------------------------------------------------------------ moments
def error_moments(r: Rows, mask: np.ndarray) -> dict:
    """Gate part 3: per-inning error covariance from the split rows of `mask`."""
    m = mask & r.split()
    n = int(m.sum())
    if n == 0:
        return {"n": 0, "sigma_e": None}
    h = 1.0 / r.ip_o[m] + 1.0 / r.ip_e[m]
    df = r.f_o[m] - r.f_e[m]
    db = r.b_o[m] - r.b_e[m]
    sh = float(np.sum(h))
    se = np.array([[np.sum(df * df), np.sum(df * db)], [np.sum(df * db), np.sum(db * db)]]) / sh
    return {"n": n, "sigma_e": se}


def signal_moments(r: Rows, mask: np.ndarray, cell_id: np.ndarray, sigma_e: np.ndarray) -> dict:
    """Gate part 4: the season values' covariance, centred within (season, cell),
    minus the error covariance at the rows' mean 1 / IP; eigenvalues clamped at 0."""
    m = mask & r.both()
    n = int(m.sum())
    if n < 3:
        return {"n": n, "sigma_obs": None, "sigma_t": None, "mean_inv_ip": None}
    x = np.column_stack([r.f9[m], r.b9[m]])
    grp = r.season[m] * 100 + cell_id[m]
    xc = x.copy()
    groups = np.unique(grp)
    for g in groups:
        sel = grp == g
        xc[sel] -= x[sel].mean(axis=0)
    dof = max(1, n - len(groups))
    so = (xc.T @ xc) / dof
    minv = float(np.mean(1.0 / r.ip[m]))
    st = so - sigma_e * minv
    st = 0.5 * (st + st.T)
    vals, vecs = np.linalg.eigh(st)
    st = (vecs * np.clip(vals, 0.0, None)) @ vecs.T
    return {"n": n, "sigma_obs": so, "sigma_t": st, "mean_inv_ip": minv}


def weight(sigma_t: np.ndarray, sigma_e: np.ndarray, ip) -> np.ndarray:
    """Gate part 4: w = beta_F / (beta_F + beta_B), beta the best linear predictor
    of T_B from (F, B) at IP; clamped to [0, 1]; 1 when the sum is not positive."""
    ip = np.atleast_1d(np.asarray(ip, float))
    out = np.ones(len(ip))
    c = sigma_t[:, 1]
    for i, v in enumerate(ip):
        if not (v > 0):
            continue
        a = sigma_t + sigma_e / v
        try:
            beta = np.linalg.solve(a, c)
        except np.linalg.LinAlgError:
            continue
        s = float(beta[0] + beta[1])
        if s <= W_EPS:
            out[i] = 1.0
        else:
            out[i] = float(min(1.0, max(0.0, beta[0] / s)))
    return out


@dataclass
class Model:
    """The fitted moments of one fold: per (role, band) the error and signal
    covariances actually used, and where they came from (cell or role pool)."""
    train: tuple
    cells: dict = field(default_factory=dict)      # (role, band) -> {...}

    def weights(self, role: np.ndarray, ip: np.ndarray) -> np.ndarray:
        role = np.asarray(role, int)
        ip = np.asarray(ip, float)
        bands = band_of(ip)
        out = np.ones(len(ip))
        for (ro, b), c in self.cells.items():
            sel = (role == ro) & (bands == b)
            if sel.any():
                out[sel] = weight(c["sigma_t"], c["sigma_e"], ip[sel])
        return out

    def table(self, ip_median: Optional[Mapping] = None) -> list:
        rows = []
        for (ro, b), c in sorted(self.cells.items()):
            med = (ip_median or {}).get((ro, b))
            w_med = None if med is None else float(weight(c["sigma_t"], c["sigma_e"], [med])[0])
            rows.append({"role": ROLES[ro], "band": BAND_NAMES[b], "source": c["source"],
                         "n_split": c["n_split"], "n_season": c["n_season"],
                         "sigma2_F": float(c["sigma_e"][0, 0]), "sigma2_B": float(c["sigma_e"][1, 1]),
                         "sigma_FB": float(c["sigma_e"][0, 1]),
                         "T_FF": float(c["sigma_t"][0, 0]), "T_BB": float(c["sigma_t"][1, 1]),
                         "T_FB": float(c["sigma_t"][0, 1]), "ip_median": med, "w_at_median": w_med})
        return rows


def fit(r: Rows, train_seasons: Iterable[int]) -> Model:
    """Gate parts 3 and 4 on the training seasons."""
    train = tuple(sorted(int(s) for s in train_seasons))
    in_train = np.isin(r.season, train)
    model = Model(train=train)
    cell_id = r.role * 10 + r.band
    pooled = {}
    for ro in range(len(ROLES)):
        mrole = in_train & (r.role == ro)
        em = error_moments(r, mrole)
        if em["sigma_e"] is None or em["n"] < CELL_MIN:
            raise BlendRefusal(f"fold {train}: role {ROLES[ro]} has {em['n']} split rows")
        se = em["sigma_e"]
        if np.any(np.linalg.eigvalsh(se) <= 0):
            raise BlendRefusal(f"fold {train}: role {ROLES[ro]} error covariance is not positive definite")
        sm = signal_moments(r, mrole, cell_id, se)
        if sm["sigma_t"] is None:
            raise BlendRefusal(f"fold {train}: role {ROLES[ro]} has too few season rows")
        pooled[ro] = {"sigma_e": se, "sigma_t": sm["sigma_t"], "n_split": em["n"], "n_season": sm["n"]}
    for ro in range(len(ROLES)):
        for b in range(len(BAND_NAMES)):
            mc = in_train & (r.role == ro) & (r.band == b)
            em = error_moments(r, mc)
            n_season = int((mc & r.both()).sum())
            ok = (em["sigma_e"] is not None and em["n"] >= CELL_MIN and n_season >= CELL_MIN
                  and bool(np.all(np.linalg.eigvalsh(em["sigma_e"]) > 0)))
            if ok:
                sm = signal_moments(r, mc, cell_id, em["sigma_e"])
                ok = sm["sigma_t"] is not None
            if ok:
                model.cells[(ro, b)] = {"sigma_e": em["sigma_e"], "sigma_t": sm["sigma_t"],
                                        "n_split": em["n"], "n_season": sm["n"], "source": "cell"}
            else:
                p = pooled[ro]
                model.cells[(ro, b)] = {"sigma_e": p["sigma_e"], "sigma_t": p["sigma_t"],
                                        "n_split": p["n_split"], "n_season": p["n_season"],
                                        "source": f"role pool ({em['n']} split, {n_season} season rows in cell)"}
    return model


def forward_weights(r: Rows, predictor_seasons: Sequence[int], fit_seasons: Sequence[int] = FIT_SEASONS,
                    models: Optional[dict] = None) -> np.ndarray:
    """w per row of each predictor season from the fold fitted on the seasons before it
    (rows of other seasons NaN). `models` collects the folds."""
    w = np.full(r.n, np.nan)
    for y in predictor_seasons:
        train = [s for s in fit_seasons if s < y]
        mdl = fit(r, train)
        if models is not None:
            models[int(y)] = mdl
        sel = r.season == y
        w[sel] = mdl.weights(r.role[sel], r.ip[sel])
    return w


def blend(f9: np.ndarray, b9: np.ndarray, w: np.ndarray) -> np.ndarray:
    """blend9 = w F9 + (1 - w) B9; F9 where B9 is absent."""
    b = np.where(np.isfinite(b9), b9, f9)
    return w * f9 + (1.0 - w) * b


def cell_medians(r: Rows, mask: np.ndarray) -> dict:
    out = {}
    for ro in range(len(ROLES)):
        for b in range(len(BAND_NAMES)):
            sel = mask & (r.role == ro) & (r.band == b) & r.both()
            if sel.any():
                out[(ro, b)] = float(np.median(r.ip[sel]))
    return out


# ------------------------------------------------------------------ test (i)
@dataclass
class Pairs:
    """(Y, Y + 1) pairs: the predictor season, the player, the club code, the target
    (runs prevented in Y + 1, i.e. -RA9*) and one value per series."""
    season: np.ndarray
    player: np.ndarray
    club: np.ndarray
    target: np.ndarray
    series: dict

    def __post_init__(self):
        self.season = np.asarray(self.season, int)
        self.player = np.asarray(self.player, int)
        self.club = np.asarray(self.club, int)
        self.target = np.asarray(self.target, float)
        self.series = {k: np.asarray(v, float) for k, v in self.series.items()}
        self.seasons = tuple(sorted({int(s) for s in self.season}))
        self.s_ix = {s: np.flatnonzero(self.season == s) for s in self.seasons}

    @property
    def n(self) -> int:
        return len(self.season)


def _rank(x: np.ndarray) -> np.ndarray:
    """Average ranks (ties averaged)."""
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    ranks = np.empty(len(x), float)
    if len(x) == 0:
        return ranks
    diff = np.concatenate(([True], xs[1:] != xs[:-1], [True]))
    starts = np.flatnonzero(diff[:-1])
    ends = np.flatnonzero(diff[1:]) + 1
    avg = (starts + ends - 1) / 2.0 + 1.0
    ranks[order] = np.repeat(avg, ends - starts)
    return ranks


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float(np.dot(a, a)) * float(np.dot(b, b)))
    return float(np.dot(a, b) / den) if den > 0 else float("nan")


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    return _pearson(_rank(x), _rank(y))


def rho_pooled(p: Pairs, key: str, mult: Optional[np.ndarray] = None) -> float:
    """The pair-weighted mean over predictor seasons of the within-season Spearman of
    series `key` with the target; `mult` is a bootstrap multiplicity per pair."""
    num = 0.0
    den = 0.0
    x = p.series[key]
    for s, ix in p.s_ix.items():
        if mult is not None:
            ix = np.repeat(ix, mult[ix].astype(int))
        if len(ix) < 3:
            continue
        r = spearman(x[ix], p.target[ix])
        if math.isfinite(r):
            num += len(ix) * r
            den += len(ix)
    return num / den if den > 0 else float("nan")


def rho_by_season(p: Pairs, key: str) -> dict:
    return {int(s): {"n": int(len(ix)), "rho": spearman(p.series[key][ix], p.target[ix])}
            for s, ix in p.s_ix.items()}


def boot_multiplicity(p: Pairs, kind: str, b: int, seed: int):
    """Yield (b,) multiplicity vectors per pair, one draw per replicate shared by every series."""
    rng = np.random.default_rng(seed)
    codes = p.player if kind == "player" else p.club
    u, inv = np.unique(codes, return_inverse=True)
    k = len(u)
    for _ in range(b):
        cnt = np.bincount(rng.integers(0, k, size=k), minlength=k)
        yield cnt[inv]


def test_i(p: Pairs, cand: str = "blend", comparators: Sequence[str] = COMPARATORS_I,
           reported: Sequence[str] = (), boot_b: int = BOOT_B, seed: int = SEED,
           boots: Sequence[str] = BOOTS_I, log: Optional[Callable] = None) -> dict:
    """Gate part 5: rho per series, the gaps, the bootstraps' sd and the p-values."""
    keys = [cand] + [k for k in list(comparators) + list(reported) if k != cand]
    pts = {k: rho_pooled(p, k) for k in keys}
    draws = {}
    for kind in boots:
        acc = {k: np.empty(boot_b) for k in keys}
        for i, mult in enumerate(boot_multiplicity(p, kind, boot_b, seed)):
            for k in keys:
                acc[k][i] = rho_pooled(p, k, mult)
        draws[kind] = acc
        if log:
            log(f"bootstrap {kind}: B {boot_b}, sd of the gap " + ", ".join(
                f"{c} {float(np.std(acc[cand] - acc[c], ddof=1)):.4f}" for c in keys if c != cand))
    cells = {}
    pvals = []
    for c in keys:
        if c == cand:
            continue
        g = pts[cand] - pts[c]
        cells[c] = {"gap": g, "boot": {}}
        for kind in boots:
            d = draws[kind][cand] - draws[kind][c]
            sd = float(np.std(d, ddof=1)) if boot_b > 1 else float("nan")
            pv = p_upper(g, sd)
            cells[c]["boot"][kind] = {"sd": sd, "lo": g - Z * sd, "hi": g + Z * sd,
                                      "p2_5": float(np.percentile(d, 2.5)),
                                      "p97_5": float(np.percentile(d, 97.5)), "p": pv}
            if c in comparators:
                pvals.append(pv)
    p_i = max(pvals) if pvals else 1.0
    return {"rho": pts, "cells": cells, "p_i": p_i, "boot_b": boot_b, "seed": seed,
            "n_pairs": p.n, "by_season": {k: rho_by_season(p, k) for k in keys}}


# ------------------------------------------------------------------ test (ii)
def departure_wins(f9: np.ndarray, b9: np.ndarray, w: np.ndarray, ip: np.ndarray,
                   rpw: np.ndarray, season: np.ndarray, carry: np.ndarray) -> np.ndarray:
    """Gate part 6: D = d - IP * sum(d) / sum(IP) per season over the `carry` rows
    (non-nopp pitchers); d = (1 - w)(B9 - F9) IP / 9 / RPW, 0 where B9 is absent."""
    d = np.where(np.isfinite(b9) & carry, (1.0 - w) * (b9 - f9) * ip / 9.0 / rpw, 0.0)
    out = np.zeros(len(d))
    for s in np.unique(season):
        m = (season == s) & carry
        if not m.any():
            continue
        out[m] = d[m] - ip[m] * float(np.sum(d[m])) / float(np.sum(ip[m]))
    return out


def test_ii(cells_ra: Mapping[str, Mapping], d: float, margin: float = MARGIN_RUNS) -> dict:
    """Gate part 6 from the yardstick's runs-allowed cell against K*: per bootstrap
    {sd}; NON-INFERIOR when d - 1.645 sd > -margin under every bootstrap."""
    out = {"d": d, "margin": margin, "boot": {}}
    ps = []
    ok = True
    for kind, c in cells_ra.items():
        sd = float(c["sd"])
        lo = d - Z * sd
        pv = p_upper(d + margin, sd)
        out["boot"][kind] = {"sd": sd, "lo": lo, "p": pv, "non_inferior": bool(lo > -margin)}
        ok &= lo > -margin
        ps.append(pv)
    out["non_inferior"] = bool(ok)
    out["p_ii"] = max(ps) if ps else 1.0
    return out


def decide(p_i: float, p_ii: float, planted_pass: Optional[bool], identity_ok: Optional[bool]) -> dict:
    """Gate part 7."""
    rej = holm({"i": p_i, "ii": p_ii})
    if planted_pass is False:
        verdict = "UNRESOLVED (the design did not recover a planted blend)"
    elif rej["i"] and rej["ii"] and planted_pass and identity_ok:
        verdict = "ADOPT"
    else:
        verdict = "NOT ADOPT"
    return {"p_i": p_i, "p_ii": p_ii, "holm_rejects": rej, "planted_pass": planted_pass,
            "identity_ok": identity_ok, "verdict": verdict}


# ------------------------------------------------------------------ the planted check
@dataclass
class PlantedDesign:
    """The real design without any run value: rows (season, player, role, ip, half
    IP, which rows have a split and a second source), and the pairs (row in Y, row
    in Y + 1, club code)."""
    rows: Rows
    pair_y: np.ndarray
    pair_y1: np.ndarray
    pair_club: np.ndarray
    seasons: tuple = FIT_SEASONS


def _ar_paths(players: np.ndarray, seasons: Sequence[int], rho: float, rng: np.random.Generator,
              persistent: bool) -> dict:
    """{(player, season): standard normal} following an AR(1) path per player over the
    seasons in order (one step per calendar season), or independent draws."""
    out = {}
    all_s = list(range(min(seasons), max(seasons) + 2))
    for pl in np.unique(players):
        z = rng.standard_normal()
        for s in all_s:
            if persistent:
                if s != all_s[0]:
                    z = rho * z + math.sqrt(1.0 - rho * rho) * rng.standard_normal()
                out[(int(pl), s)] = z
            else:
                out[(int(pl), s)] = rng.standard_normal()
    return out


def oracle_weight(role: int, ip: float) -> float:
    r = ROLES[role]
    sf2 = PLANTED_SD_TF[r] ** 2
    su2 = PLANTED_SD_U[r] ** 2
    st = np.array([[sf2, sf2], [sf2, sf2 + su2]])
    c = PLANTED_ERR_CORR * PLANTED_SIGMA_F * PLANTED_SIGMA_B
    se = np.array([[PLANTED_SIGMA_F ** 2, c], [c, PLANTED_SIGMA_B ** 2]])
    return float(weight(st, se, [ip])[0])


def simulate(pd_: PlantedDesign, world: str, rng: np.random.Generator) -> tuple[Rows, np.ndarray]:
    """One replicate of a planted world on the real design: (rows with simulated
    season and half values, target per pair as runs prevented in Y + 1)."""
    r = pd_.rows
    players = r.player
    seasons = sorted({int(s) for s in r.season})
    tf = _ar_paths(players, seasons, PLANTED_RHO, rng, True)
    u = _ar_paths(players, seasons, PLANTED_RHO, rng, world == "truth")
    sd_tf = np.array([PLANTED_SD_TF[ROLES[k]] for k in r.role])
    sd_u = np.array([PLANTED_SD_U[ROLES[k]] for k in r.role])
    t_f = sd_tf * np.array([tf[(int(p), int(s))] for p, s in zip(players, r.season)])
    t_u = sd_u * np.array([u[(int(p), int(s))] for p, s in zip(players, r.season)])
    cov = PLANTED_ERR_CORR * PLANTED_SIGMA_F * PLANTED_SIGMA_B
    se = np.array([[PLANTED_SIGMA_F ** 2, cov], [cov, PLANTED_SIGMA_B ** 2]])
    chol = np.linalg.cholesky(se)

    def errs(ip):
        e = rng.standard_normal((len(ip), 2)) @ chol.T
        s = 1.0 / np.sqrt(np.where(ip > 0, ip, np.inf))
        return e[:, 0] * s, e[:, 1] * s

    ef, eb = errs(r.ip)
    f9 = t_f + ef
    b9 = np.where(np.isfinite(r.b9), t_f + t_u + eb, np.nan)
    has = np.isfinite(r.ip_o) & np.isfinite(r.ip_e) & (r.ip_o > 0) & (r.ip_e > 0)
    efo, ebo = errs(np.where(has, r.ip_o, 0.0))
    efe, ebe = errs(np.where(has, r.ip_e, 0.0))
    f_o = np.where(has, t_f + efo, np.nan)
    f_e = np.where(has, t_f + efe, np.nan)
    b_o = np.where(has, t_f + t_u + ebo, np.nan)
    b_e = np.where(has, t_f + t_u + ebe, np.nan)
    f9 = centre_within_season(f9, r.ip, r.season)
    b9 = centre_within_season(b9, r.ip, r.season)
    rows = r.with_values(f9=f9, b9=b9, f_o=f_o, f_e=f_e, b_o=b_o, b_e=b_e)
    # the target: runs prevented in Y + 1
    y1 = pd_.pair_y1
    true_next = t_f[y1] + (t_u[y1] if world == "truth" else 0.0)
    et = rng.standard_normal(len(y1)) * PLANTED_SIGMA_T / np.sqrt(r.ip[y1])
    return rows, true_next + et


def planted_pairs(pd_: PlantedDesign, rows: Rows, target: np.ndarray, w: np.ndarray) -> Pairs:
    y = pd_.pair_y
    return Pairs(season=rows.season[y], player=rows.player[y], club=pd_.pair_club, target=target,
                 series={"blend": blend(rows.f9[y], rows.b9[y], w[y]), "F9": rows.f9[y], "B9": rows.b9[y]})


def planted(pd_: PlantedDesign, *, reps: int = PLANTED_REPS, boot_b: int = PLANTED_B,
            seed: int = SEED, log: Optional[Callable] = None) -> dict:
    """Gate part 8: the truth and fake worlds, `reps` replicates each."""
    rng = np.random.default_rng(seed)
    out = {"truth": [], "fake": [], "w_abs_diff": []}
    pred = tuple(sorted({int(s) for s in pd_.rows.season[pd_.pair_y]}))
    for rep in range(reps):
        for world in ("truth", "fake"):
            rows, target = simulate(pd_, world, rng)
            w = forward_weights(rows, pred, pd_.seasons)
            res = test_i(planted_pairs(pd_, rows, target, w), boot_b=boot_b,
                         seed=int(rng.integers(0, 2 ** 31 - 1)))
            passed = bool(res["p_i"] <= PLANTED_ALPHA)
            out[world].append({"p_i": res["p_i"], "pass": passed,
                               "gap_F9": res["cells"]["F9"]["gap"], "gap_B9": res["cells"]["B9"]["gap"]})
            if world == "truth":
                mdl = fit(rows, pd_.seasons)
                med = cell_medians(rows, np.ones(rows.n, bool))
                diffs = [abs(float(weight(c["sigma_t"], c["sigma_e"], [med[k]])[0]) - oracle_weight(k[0], med[k]))
                         for k, c in mdl.cells.items() if k in med]
                out["w_abs_diff"].append(float(np.mean(diffs)) if diffs else float("nan"))
        if log:
            log(f"planted replicate {rep + 1}/{reps}: truth p {out['truth'][-1]['p_i']:.4f} "
                f"fake p {out['fake'][-1]['p_i']:.4f} w diff {out['w_abs_diff'][-1]:.4f}")
    t_pass = sum(1 for x in out["truth"] if x["pass"])
    f_pass = sum(1 for x in out["fake"] if x["pass"])
    wd = float(np.nanmean(out["w_abs_diff"])) if out["w_abs_diff"] else float("nan")
    out.update({"truth_pass": t_pass, "fake_pass": f_pass, "w_mean_abs_diff": wd,
                "planted_pass": bool(t_pass >= PLANTED_PASS_MIN and f_pass <= PLANTED_FAKE_MAX
                                     and math.isfinite(wd) and wd <= PLANTED_W_TOL),
                "reps": reps, "boot_b": boot_b})
    return out


def identity_check(p: Pairs, boot_b: int = 200, seed: int = SEED) -> dict:
    """Gate part 8: the blend with every w = 1 is F9; every gap draw is zero."""
    q = Pairs(season=p.season, player=p.player, club=p.club, target=p.target,
              series={"blend": p.series["F9"], "F9": p.series["F9"], "B9": p.series["B9"]})
    res = test_i(q, boot_b=boot_b, seed=seed)
    c = res["cells"]["F9"]
    zero = c["gap"] == 0.0 and all(v["sd"] == 0.0 for v in c["boot"].values())
    return {"gap_F9": c["gap"], "all_zero": bool(zero), "p_i": res["p_i"],
            "ok": bool(zero and res["p_i"] > PLANTED_ALPHA)}


def to_jsonable(x, nd: int = 6):
    if isinstance(x, dict):
        return {str(k): to_jsonable(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v, nd) for v in x]
    if isinstance(x, np.ndarray):
        return [to_jsonable(v, nd) for v in x.tolist()]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        f = float(x)
        return None if not math.isfinite(f) else round(f, nd)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x
