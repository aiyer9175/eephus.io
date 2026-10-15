# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Runs per win fitted from team outcomes, the pure core.
docs/ewar/RPW_GATE.md (rpw_fit_v1, task EWAR_RPW_FIT, owner decision EW3-24).

WHAT IT DECIDES. Whether a conversion fitted on club wins replaces the FanGraphs
closed form 9 x (R / IP) x 1.5 + 3 (league_constants.league_totals rpw, the
incumbent) as eWAR v3's runs per win. Only eWAR v3 can change; fwar_frame keeps
FanGraphs' conversion and eWAR v2 keeps Baseball-Reference's.

THE CANDIDATES (gate part 2). Linear ones predict W_hat = G / 2 + RD / RPW:
  a  the closed form, nothing fitted
  b  Pythagenpat, W_hat = G RS^x / (RS^x + RA^x), x = ((RS + RA) / G)^z, z on a grid
  c  W - G / 2 = beta RD through the origin, RPW = 1 / beta
  d  W - G / 2 = RD (b0 + b1 (L - 9) + b2 (T - L) + b3 (PF - 1)), RPW = 1 / (...)
  e  Baseball-Reference's recovered values (ewar.runs_per_win), nothing fitted
References r0 (G / 2) and r1 (Pythagenpat at 0.287) decide nothing.

THE ESTIMAND (gate parts 3 and 4). Leave one season out over the primary frame
(2016 to 2019 and 2021 to 2026); MAE in wins decides, RMSE is reported. A paired
bootstrap over the held-out team-season errors (one index matrix, B 2000, seed
20261025) gives lo95 of MAE(a) - MAE(c); PRIMARY PASS when it is above 0. The team
guard of EBR_GATE 11.2.4 is not computed here (PRIMARY PASS, GUARD PENDING).

THE PITCHER LEG (gate part 5). Arm L converts every pitching run at the league
constant; arm D converts each pitcher's runs at FanGraphs' per-pitcher form on runs
allowed. Reported, deciding nothing.

Pure: numpy only, no network, no writes. tools/build_rpw_fit.py reads the caches and
writes data/rpw_fit.json.
"""
from __future__ import annotations

import math

import numpy as np

RPW_FIT_VERSION = "rpw_fit_v1"
GATE_DOC = "docs/ewar/RPW_GATE.md"
PRIMARY_SEASONS: tuple[int, ...] = (2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
SENSITIVITY_SEASON = 2020
ALL_SEASONS: tuple[int, ...] = tuple(range(2016, 2027))
CLUBS_PER_SEASON = 30

BOOT_B = 2000
BOOT_SEED = 20261025
Z_GRID = (0.1, 0.5, 0.0005)
PYTHAGENPAT_FIXED = 0.287
ENV_CENTER = 9.0
ARM_L_TOL = 1e-9
CHALLENGERS: tuple[str, ...] = ("b", "c", "d", "e")
LINEAR = frozenset({"a", "c", "d", "e"})
NAMES = {
    "a": "FanGraphs closed form 9 x (R/IP) x 1.5 + 3 (incumbent)",
    "b": "Pythagenpat, exponent z fitted",
    "c": "slope of wins on run differential",
    "d": "run environment: league and club runs per game, park",
    "e": "Baseball-Reference recovered values (ewar.runs_per_win)",
    "r0": "reference: no run differential (G / 2)",
    "r1": "reference: Pythagenpat at the fixed exponent 0.287",
}


class RpwRefusal(RuntimeError):
    """A build that must not write: the message names the season and the cause."""


# ------------------------------------------------------------------ the frame
def check_season(season: int, clubs: list[dict]) -> None:
    """Gate part 6 refusal 1: 30 clubs, runs scored equal runs allowed, wins equal losses."""
    if len(clubs) != CLUBS_PER_SEASON:
        raise RpwRefusal(f"{season}: {len(clubs)} clubs in the standings, expected 30")
    rs = sum(c["rs"] for c in clubs)
    ra = sum(c["ra"] for c in clubs)
    w = sum(c["w"] for c in clubs)
    lo = sum(c["l"] for c in clubs)
    if rs != ra:
        raise RpwRefusal(f"{season}: league runs scored {rs} differ from runs allowed {ra}")
    if w != lo:
        raise RpwRefusal(f"{season}: league wins {w} differ from losses {lo}")


def league_rpg(clubs: list[dict]) -> float:
    """L_s: league runs per game, both clubs = 2 x sum RS / sum G."""
    g = sum(c["w"] + c["l"] for c in clubs)
    return 2.0 * sum(c["rs"] for c in clubs) / g


def frame(rows: list[dict]) -> dict:
    """Column arrays over team-season rows. Each row carries season, club, w, l, rs,
    ra, pf, rpw_fg (the incumbent), rpw_bref (candidate e) and L (league runs per
    game). The order of `rows` is kept."""
    f = {k: np.array([r[k] for r in rows], dtype=float)
         for k in ("w", "l", "rs", "ra", "pf", "rpw_fg", "rpw_bref", "L")}
    f["season"] = np.array([int(r["season"]) for r in rows])
    f["club"] = [r["club"] for r in rows]
    f["g"] = f["w"] + f["l"]
    f["rd"] = f["rs"] - f["ra"]
    f["t"] = (f["rs"] + f["ra"]) / f["g"]
    return f


def subset(f: dict, mask: np.ndarray) -> dict:
    out = {}
    for k, v in f.items():
        out[k] = [x for x, m in zip(v, mask) if m] if isinstance(v, list) else v[mask]
    return out


# --------------------------------------------------------------- predictions
def linear_wins(g, rd, rpw):
    return np.asarray(g, float) / 2.0 + np.asarray(rd, float) / np.asarray(rpw, float)


def pythag_wins(rs, ra, g, z: float):
    rs = np.asarray(rs, float)
    ra = np.asarray(ra, float)
    g = np.asarray(g, float)
    x = ((rs + ra) / g) ** z
    # RS^x / (RS^x + RA^x) = 1 / (1 + (RA / RS)^x), stable for large x
    return g / (1.0 + np.exp(x * (np.log(ra) - np.log(rs))))


def fit_pythag_z(rs, ra, g, w) -> float:
    """z minimizing the summed squared wins error over the grid 0.1000 to 0.5000,
    step 0.0005; a tie takes the smaller z (gate part 2(b))."""
    lo, hi, step = Z_GRID
    n = int(round((hi - lo) / step)) + 1
    w = np.asarray(w, float)
    best_z, best_sse = None, math.inf
    for k in range(n):
        z = round(lo + k * step, 4)
        sse = float(np.sum((pythag_wins(rs, ra, g, z) - w) ** 2))
        if sse < best_sse:
            best_z, best_sse = z, sse
    return float(best_z)


def pythag_marginal_rpw(rs, ra, g, z: float):
    """2 / (W(RS + 0.5, RA - 0.5) - W(RS - 0.5, RA + 0.5)): runs of differential per win
    at the club's own run environment (RS + RA, so x, held fixed)."""
    rs = np.asarray(rs, float)
    ra = np.asarray(ra, float)
    up = pythag_wins(rs + 0.5, ra - 0.5, g, z)
    dn = pythag_wins(rs - 0.5, ra + 0.5, g, z)
    return 2.0 / (up - dn)


def pythag_league_rpw(L: float, z: float) -> float:
    """At RS = RA the marginal runs per win is 4 r / x with r = L / 2, so 2 L^(1 - z)."""
    return 2.0 * float(L) ** (1.0 - float(z))


def fit_slope(rd, g, w) -> float:
    """beta of W - G / 2 = beta RD, least squares through the origin."""
    rd = np.asarray(rd, float)
    y = np.asarray(w, float) - np.asarray(g, float) / 2.0
    return float(np.sum(rd * y) / np.sum(rd * rd))


def env_design(rd, L, t, pf) -> np.ndarray:
    rd = np.asarray(rd, float)
    L = np.asarray(L, float)
    return np.column_stack([rd, rd * (L - ENV_CENTER), rd * (np.asarray(t, float) - L),
                            rd * (np.asarray(pf, float) - 1.0)])


def fit_env(rd, L, t, pf, g, w) -> list[float]:
    """(b0, b1, b2, b3) of gate part 2(d), least squares with no intercept."""
    X = env_design(rd, L, t, pf)
    y = np.asarray(w, float) - np.asarray(g, float) / 2.0
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return [float(c) for c in coef]


def env_wins_per_run(coef, L, t, pf):
    b0, b1, b2, b3 = coef
    L = np.asarray(L, float)
    return b0 + b1 * (L - ENV_CENTER) + b2 * (np.asarray(t, float) - L) + b3 * (np.asarray(pf, float) - 1.0)


def env_league_rpw(coef, L: float) -> float:
    return 1.0 / (coef[0] + coef[1] * (float(L) - ENV_CENTER))


# ------------------------------------------------------------ the candidates
def fit(cand: str, f: dict) -> dict:
    """The candidate's parameters fitted on frame `f` ({} when it fits nothing)."""
    if cand == "b":
        return {"z": fit_pythag_z(f["rs"], f["ra"], f["g"], f["w"])}
    if cand == "c":
        beta = fit_slope(f["rd"], f["g"], f["w"])
        return {"beta": beta, "rpw": 1.0 / beta}
    if cand == "d":
        return {"coef": fit_env(f["rd"], f["L"], f["t"], f["pf"], f["g"], f["w"])}
    return {}


def team_rpw(cand: str, params: dict, f: dict):
    """RPW_i per row for a linear candidate."""
    n = len(f["g"])
    if cand == "a":
        return np.asarray(f["rpw_fg"], float)
    if cand == "e":
        return np.asarray(f["rpw_bref"], float)
    if cand == "c":
        return np.full(n, 1.0 / params["beta"])
    if cand == "d":
        return 1.0 / env_wins_per_run(params["coef"], f["L"], f["t"], f["pf"])
    raise ValueError(f"{cand} is not linear")


def predict(cand: str, params: dict, f: dict):
    if cand == "r0":
        return np.asarray(f["g"], float) / 2.0
    if cand == "r1":
        return pythag_wins(f["rs"], f["ra"], f["g"], PYTHAGENPAT_FIXED)
    if cand == "b":
        return pythag_wins(f["rs"], f["ra"], f["g"], params["z"])
    return linear_wins(f["g"], f["rd"], team_rpw(cand, params, f))


def league_rpw(cand: str, params: dict, L: float, bref_season: float | None = None,
               fg_season: float | None = None) -> float | None:
    """The league-environment runs per win a candidate supplies for a season (gate part 4)."""
    if cand == "a":
        return fg_season
    if cand == "b":
        return pythag_league_rpw(L, params["z"])
    if cand == "c":
        return 1.0 / params["beta"]
    if cand == "d":
        return env_league_rpw(params["coef"], L)
    if cand == "e":
        return bref_season
    return None


def loso(f: dict, cands=("a", "b", "c", "d", "e", "r0", "r1")) -> dict:
    """Held-out predictions per candidate: {cand: {"pred": array, "fits": {season: params},
    "void": bool}} in the row order of `f` (gate part 3)."""
    seasons = sorted(set(int(s) for s in f["season"]))
    out = {}
    for cand in cands:
        pred = np.full(len(f["g"]), np.nan)
        fits = {}
        void = False
        for h in seasons:
            test = f["season"] == h
            params = fit(cand, subset(f, ~test))
            fits[h] = params
            ft = subset(f, test)
            if cand in ("c", "d"):
                r = team_rpw(cand, params, ft)
                if not np.all(np.isfinite(r)) or np.any(r <= 0):
                    void = True
            pred[test] = predict(cand, params, ft)
        if cand not in ("c", "d") and not np.all(np.isfinite(pred)):
            raise RpwRefusal(f"candidate {cand}: a non-finite prediction")
        out[cand] = {"pred": pred, "fits": fits, "void": void}
    return out


def mae(err) -> float:
    return float(np.mean(np.abs(err)))


def rmse(err) -> float:
    return float(np.sqrt(np.mean(np.asarray(err, float) ** 2)))


# ---------------------------------------------------------------- bootstrap
def boot_index(n: int, b: int = BOOT_B, seed: int = BOOT_SEED) -> np.ndarray:
    """The one index matrix of gate part 4, drawn once."""
    return np.random.default_rng(seed).integers(0, n, size=(b, n))


def contrast(err_inc, err_c, idx: np.ndarray) -> dict:
    """dMAE = MAE(incumbent) - MAE(challenger) on the held-out errors and its paired
    bootstrap over the rows of `idx`. Positive favours the challenger."""
    ai = np.abs(np.asarray(err_inc, float))
    ac = np.abs(np.asarray(err_c, float))
    point = float(ai.mean() - ac.mean())
    draws = ai[idx].mean(axis=1) - ac[idx].mean(axis=1)
    si = np.asarray(err_inc, float) ** 2
    sc = np.asarray(err_c, float) ** 2
    rm = np.sqrt(si[idx].mean(axis=1)) - np.sqrt(sc[idx].mean(axis=1))
    return {"d_mae": point,
            "sd": float(np.std(draws, ddof=1)),
            "lo95": float(np.percentile(draws, 5)),
            "hi95": float(np.percentile(draws, 95)),
            "p_le_0": float(np.mean(draws <= 0.0)),
            "d_rmse": float(math.sqrt(si.mean()) - math.sqrt(sc.mean())),
            "d_rmse_lo95": float(np.percentile(rm, 5)),
            "d_rmse_hi95": float(np.percentile(rm, 95))}


def holm(pvals: dict, alpha: float = 0.05) -> dict:
    """Holm step-down over the challengers' bootstrap p (reported, deciding nothing)."""
    order = sorted(pvals, key=lambda k: (pvals[k], k))
    m = len(order)
    out, stopped = {}, False
    for j, k in enumerate(order):
        thr = alpha / (m - j)
        rej = (not stopped) and pvals[k] <= thr
        if not rej:
            stopped = True
        out[k] = {"p": pvals[k], "threshold": thr, "rejects": rej}
    return out


def verdict(contrasts: dict, voids: dict) -> dict:
    """Gate part 4: PRIMARY PASS when lo95 > 0; the largest point dMAE carries forward
    (a tie takes the earlier letter); the team guard is pending, never computed here."""
    passing = [c for c in CHALLENGERS
               if not voids.get(c) and contrasts[c]["lo95"] > 0.0]
    if not passing:
        return {"status": "INCUMBENT HOLDS", "candidate": "a", "passing": []}
    best = sorted(passing, key=lambda c: (-contrasts[c]["d_mae"], c))[0]
    return {"status": "PRIMARY PASS, GUARD PENDING", "candidate": best, "passing": passing}


def pitcher_verdict(c: dict) -> str:
    if c["lo95"] > 0.0:
        return "beats"
    if c["hi95"] < 0.0:
        return "does worse"
    return "does not separate"


# ----------------------------------------------------------- the pitcher leg
def dynamic_rpw_runs(ipg, ra, g, lg_ra9):
    """FanGraphs' per-pitcher form on runs allowed (gate part 5):
    (((18 - ipg) lgRA9 + 9 RA / G) / 18 + 2) x 1.5, where 9 RA / G = ipg x RA9. Equals
    fwar_frame.dynamic_rpw(ip, g, lg_ra9, RA9) whenever the pitcher has an out."""
    ipg = np.asarray(ipg, float)
    return (((18.0 - ipg) * np.asarray(lg_ra9, float)
             + 9.0 * np.asarray(ra, float) / np.asarray(g, float)) / 18.0 + 2.0) * 1.5


def pitcher_arms(f: dict, stints: list[dict], lg_ra9: dict) -> dict:
    """Arms L and D for every row of `f`.

    `stints`: one dict per pitching stint with season, club, pid, g, outs, ra; the
    pitcher's season totals (all his stints) set ipg and RA for dRPW. `lg_ra9`:
    {season: league RA9}. Refuses when a club's stint runs differ from its standings
    runs allowed, or when arm L departs from candidate (a)."""
    tot: dict = {}
    for s in stints:
        k = (int(s["season"]), s["pid"])
        a = tot.setdefault(k, [0.0, 0.0, 0.0])
        a[0] += float(s["g"])
        a[1] += float(s["outs"])
        a[2] += float(s["ra"])
    by_club: dict = {}
    for s in stints:
        season = int(s["season"])
        gp, outs_p, ra_p = tot[(season, s["pid"])]
        ipg = (outs_p / 3.0) / gp if gp > 0 else 0.0
        lg = float(lg_ra9[season])
        d = float(dynamic_rpw_runs(ipg, ra_p if gp > 0 else 0.0, gp if gp > 0 else 1.0, lg))
        ip = float(s["outs"]) / 3.0
        p = lg * ip / 9.0 - float(s["ra"])
        acc = by_club.setdefault((season, s["club"]), {"ip": 0.0, "ra": 0.0, "p": 0.0, "pd": 0.0})
        acc["ip"] += ip
        acc["ra"] += float(s["ra"])
        acc["p"] += p
        acc["pd"] += p / d
    n = len(f["g"])
    arm_l = np.empty(n)
    arm_d = np.empty(n)
    for i in range(n):
        season = int(f["season"][i])
        acc = by_club.get((season, f["club"][i]))
        if acc is None or abs(acc["ra"] - f["ra"][i]) > 1e-9:
            got = None if acc is None else acc["ra"]
            raise RpwRefusal(f"{season} {f['club'][i]}: stint runs allowed {got} differ "
                             f"from the standings' {f['ra'][i]:.0f}")
        lg = float(lg_ra9[season])
        off = f["rs"][i] - lg * acc["ip"] / 9.0
        rpw = f["rpw_fg"][i]
        arm_l[i] = f["g"][i] / 2.0 + (off + acc["p"]) / rpw
        arm_d[i] = f["g"][i] / 2.0 + off / rpw + acc["pd"]
    ref = linear_wins(f["g"], f["rd"], f["rpw_fg"])
    worst = float(np.max(np.abs(arm_l - ref))) if n else 0.0
    if worst > ARM_L_TOL:
        raise RpwRefusal(f"arm L departs from candidate (a) by {worst:.3g} wins")
    return {"L": arm_l, "D": arm_d, "arm_l_max_abs_vs_a": worst}
