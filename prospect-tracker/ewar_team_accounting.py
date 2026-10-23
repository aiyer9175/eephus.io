# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR team accounting read, the pure core.
docs/ewar-v3/EWAR_TEAM_ACCOUNTING_GATE.md (task EWAR_TEAM_ACCOUNTING, owner EW3-50).

WHAT IT ASKS. Per club-season, does a WAR series summed over the club's players,
plus the series' own replacement baseline, track the club's wins and run
differential (deciding), runs scored by the bat side and runs allowed by the pit
side (reported)? The candidate is eWAR realized; fWAR (also the no-change null)
and bWAR are the comparators. Same season only: nothing here forecasts.

THE PIECES.
  Design       club-seasons (season, club, franchise, games, outcomes) and the
               player index of the player-clustered bootstrap.
  Series       per side a (players x club-seasons) matrix of allocated values in
               wins, plus a runs-per-win vector over club-seasons.
  Departure    rows that carry a pitching departure (player, season, club shares,
               value): the permutation null and the planted check move only these.
  score        the cells, the three bootstraps, the dispositions and the PASS rule
               of gate parts 4 to 7, for any candidate and comparators (the
               yardstick EWAR_PITCHING_BLEND reuses, gate part 12).
  planted      gate part 6's planted check on a design, reading no real outcome.
  miss_table   gate part 8, descriptive.

Pure: numpy only, no network, no file access. tools/ewar_team_accounting_lab.py
reads the inputs and writes the record.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np

VERSION = "ewar_team_accounting_v1"
GATE_DOC = "docs/ewar-v3/EWAR_TEAM_ACCOUNTING_GATE.md"
PRIMARY_SEASONS: tuple[int, ...] = (2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
SENSITIVITY_SEASON = 2020
CLUBS_PER_SEASON = 30

BOOT_B = 4000
SEED = 20261023
PERM_N = 1000
Z = 1.645
PLAYER_CHUNK = 250

UNALLOCATED_MAX_WINS = 1.0
SUM_TOL = 1e-6
FIXED_REPLACEMENT_PER_GAME = 0.5 - 1000.0 / 4860.0

PLANTED_REPS = 20
PLANTED_B = 500
PLANTED_PERM = 200
PLANTED_SIGMA_RD = 40.0
PLANTED_SIGMA_RD_ALT = 60.0
PLANTED_SIGMA_W = 4.0
PLANTED_PASS_MIN = 16
PLANTED_FAKE_MAX = 1

DECIDING: tuple[str, ...] = ("wins", "rd")
REPORTED: tuple[str, ...] = ("rs", "ra")
OUTCOMES: tuple[str, ...] = DECIDING + REPORTED
BOOTS: tuple[str, ...] = ("season", "club", "player")
SIDES: tuple[str, ...] = ("bat", "pit")


class AccountingRefusal(RuntimeError):
    """A refusal of gate part 3: the message names the season and the cause."""


# ---------------------------------------------------------------- structures
@dataclass
class Design:
    season: np.ndarray            # (C,) int
    club: list                    # (C,) str
    franchise: np.ndarray         # (C,) int code
    g: np.ndarray                 # (C,) games
    w: np.ndarray                 # (C,) wins
    rs: np.ndarray                # (C,) runs scored
    ra: np.ndarray                # (C,) runs allowed
    players: list                 # (P,) player keys
    seasons: tuple = field(default=())

    def __post_init__(self):
        self.season = np.asarray(self.season, int)
        self.franchise = np.asarray(self.franchise, int)
        for k in ("g", "w", "rs", "ra"):
            setattr(self, k, np.asarray(getattr(self, k), float))
        if not self.seasons:
            self.seasons = tuple(sorted({int(s) for s in self.season}))
        self.s_idx = np.array([self.seasons.index(int(s)) for s in self.season])
        # (C, S) indicator: club-season to season
        self.ind = np.zeros((len(self.season), len(self.seasons)))
        self.ind[np.arange(len(self.season)), self.s_idx] = 1.0

    @property
    def n(self) -> int:
        return len(self.season)

    @property
    def rd(self) -> np.ndarray:
        return self.rs - self.ra

    def outcome(self, name: str) -> np.ndarray:
        return {"wins": self.w, "rd": self.rd, "rs": self.rs, "ra": self.ra}[name]


@dataclass
class Series:
    bat: np.ndarray               # (P, C)
    pit: np.ndarray               # (P, C)
    rpw: np.ndarray               # (C,)

    def sums(self) -> tuple[np.ndarray, np.ndarray]:
        return self.bat.sum(axis=0), self.pit.sum(axis=0)


@dataclass
class Departure:
    """Rows carrying a pitching departure: player index, season, club shares (R, C)
    and the value (wins). The permutation null and the planted check move values
    among rows of the same season only."""
    player: np.ndarray            # (R,) int
    season: np.ndarray            # (R,) int
    shares: np.ndarray            # (R, C)
    value: np.ndarray             # (R,)

    def club_sums(self, values: Optional[np.ndarray] = None) -> np.ndarray:
        v = self.value if values is None else values
        return v @ self.shares

    def player_matrix(self, n_players: int, values: Optional[np.ndarray] = None) -> np.ndarray:
        v = self.value if values is None else values
        out = np.zeros((n_players, self.shares.shape[1]))
        np.add.at(out, self.player, self.shares * v[:, None])
        return out

    def permute(self, rng: np.random.Generator) -> np.ndarray:
        """One within-season permutation of the values (the season sums hold)."""
        out = self.value.copy()
        for s in np.unique(self.season):
            ix = np.flatnonzero(self.season == s)
            out[ix] = self.value[ix[rng.permutation(len(ix))]]
        return out


def with_departure(base: Series, dep: Departure, values: np.ndarray,
                   rpw: Optional[np.ndarray] = None) -> Series:
    """base plus the departure on the pit side."""
    return Series(bat=base.bat, pit=base.pit + dep.player_matrix(base.pit.shape[0], values),
                  rpw=base.rpw if rpw is None else np.asarray(rpw, float))


# --------------------------------------------------------------- predictions
def _season_rate(design: Design, x: np.ndarray) -> np.ndarray:
    """Per club-season, the season's sum of x over its sum of games; x is (C,) or (b, C)."""
    num = x @ design.ind
    den = design.g @ design.ind
    return (num / den)[..., design.s_idx]


def predictions(design: Design, bat: np.ndarray, pit: np.ndarray, rpw: np.ndarray) -> dict:
    """Gate part 4. bat and pit are club sums, (C,) or (b, C)."""
    t = bat + pit
    g = design.g
    above = t - _season_rate(design, t) * g
    r_s = (design.rs @ design.ind / (g @ design.ind))[design.s_idx]
    return {
        "wins": g / 2.0 + above,
        "rd": rpw * above,
        "rs": r_s * g + rpw * (bat - _season_rate(design, bat) * g),
        "ra": r_s * g - rpw * (pit - _season_rate(design, pit) * g),
    }


def fixed_baseline_wins(design: Design, bat: np.ndarray, pit: np.ndarray) -> np.ndarray:
    return FIXED_REPLACEMENT_PER_GAME * design.g + bat + pit


def errors(design: Design, s: Series) -> dict:
    bat, pit = s.sums()
    pred = predictions(design, bat, pit, s.rpw)
    return {o: design.outcome(o) - pred[o] for o in OUTCOMES}


def rmse(e: np.ndarray, w: Optional[np.ndarray] = None) -> float:
    if w is None:
        return float(math.sqrt(np.mean(np.asarray(e, float) ** 2)))
    return float(math.sqrt(np.sum(w * e ** 2) / np.sum(w)))


def rsq(y: np.ndarray, e: np.ndarray) -> float:
    y = np.asarray(y, float)
    sst = float(np.sum((y - y.mean()) ** 2))
    return float(1.0 - np.sum(np.asarray(e, float) ** 2) / sst) if sst > 0 else float("nan")


def point_cells(design: Design, series: Mapping[str, Series]) -> dict:
    out = {}
    for k, s in series.items():
        e = errors(design, s)
        out[k] = {o: {"rmse": rmse(e[o]), "rsq": rsq(design.outcome(o), e[o])} for o in OUTCOMES}
        bat, pit = s.sums()
        out[k]["wins_fixed_baseline"] = {
            "rmse": rmse(design.w - fixed_baseline_wins(design, bat, pit)),
            "rsq": rsq(design.w, design.w - fixed_baseline_wins(design, bat, pit))}
    return out


# ---------------------------------------------------------------- bootstraps
def season_weights(design: Design, b: int, rng: np.random.Generator) -> np.ndarray:
    k = len(design.seasons)
    draws = rng.integers(0, k, size=(b, k))
    cnt = np.stack([np.bincount(r, minlength=k) for r in draws])
    return cnt[:, design.s_idx].astype(float)


def club_weights(design: Design, b: int, rng: np.random.Generator) -> np.ndarray:
    codes = np.unique(design.franchise)
    k = len(codes)
    pos = np.searchsorted(codes, design.franchise)
    draws = rng.integers(0, k, size=(b, k))
    cnt = np.stack([np.bincount(r, minlength=k) for r in draws])
    return cnt[:, pos].astype(float)


def player_counts(n_players: int, b: int, rng: np.random.Generator):
    """Yield (chunk, P) multiplicity counts, PLAYER_CHUNK replicates at a time,
    in a fixed order so the draw does not depend on anything but the seed."""
    done = 0
    while done < b:
        m = min(PLAYER_CHUNK, b - done)
        idx = rng.integers(0, n_players, size=(m, n_players))
        flat = (idx + (np.arange(m)[:, None] * n_players)).ravel()
        yield np.bincount(flat, minlength=m * n_players).reshape(m, n_players).astype(float)
        done += m


def boot_rmse(design: Design, series: Mapping[str, Series], kind: str, b: int,
              seed: int) -> dict:
    """{series: {outcome: (b,) RMSE}} under one bootstrap kind; one draw per
    replicate shared by every series (paired)."""
    rng = np.random.default_rng(seed)
    out = {k: {o: [] for o in OUTCOMES} for k in series}
    if kind in ("season", "club"):
        wts = season_weights(design, b, rng) if kind == "season" else club_weights(design, b, rng)
        den = wts.sum(axis=1)
        for k, s in series.items():
            e = errors(design, s)
            for o in OUTCOMES:
                out[k][o] = np.sqrt((wts @ (e[o] ** 2)) / den)
        return out
    if kind != "player":
        raise ValueError(kind)
    n_players = len(design.players)
    mats = {k: (s.bat, s.pit, s.rpw) for k, s in series.items()}
    for cnt in player_counts(n_players, b, rng):
        for k, (mb, mp, rpw) in mats.items():
            pred = predictions(design, cnt @ mb, cnt @ mp, rpw)
            for o in OUTCOMES:
                e = design.outcome(o)[None, :] - pred[o]
                out[k][o].append(np.sqrt(np.mean(e ** 2, axis=1)))
    return {k: {o: np.concatenate(v[o]) for o in OUTCOMES} for k, v in out.items()}


def _summ(d: float, draws: np.ndarray) -> dict:
    sd = float(np.std(draws, ddof=1)) if len(draws) > 1 else float("nan")
    return {"d": d, "sd": sd, "lo": d - Z * sd, "hi": d + Z * sd,
            "p2_5": float(np.percentile(draws, 2.5)), "p97_5": float(np.percentile(draws, 97.5))}


# ----------------------------------------------------------------- the rule
def disposition(cells: Mapping) -> str:
    """Gate part 7, per comparator: cells[outcome][kind] = {"lo", "hi", ...}."""
    if all(cells[o][k]["lo"] > 0 for o in DECIDING for k in BOOTS):
        return "WIN"
    if any(all(cells[o][k]["hi"] < 0 for k in BOOTS) for o in DECIDING):
        return "LOSS"
    return "UNRESOLVED"


def perm_null(design: Design, base: Series, dep: Departure, rpw: np.ndarray, n: int,
              seed: int) -> dict:
    """{outcome: (n,) d(F)} for the candidate base + permuted departure at rpw."""
    rng = np.random.default_rng(seed)
    eb = errors(design, base)
    bat, pit = base.sums()
    out = {o: np.empty(n) for o in DECIDING}
    for i in range(n):
        vals = dep.permute(rng)
        pred = predictions(design, bat, pit + dep.club_sums(vals), rpw)
        for o in DECIDING:
            out[o][i] = rmse(eb[o]) - rmse(design.outcome(o) - pred[o])
    return out


def score(design: Design, series: Mapping[str, Series], cand: str, comparators: Sequence[str],
          *, boot_b: int = BOOT_B, seed: int = SEED, dep: Optional[Departure] = None,
          null_key: Optional[str] = None, perm_n: int = PERM_N, planted_pass: Optional[bool] = None,
          reported: Sequence[str] = (), log=None) -> dict:
    """The cells, bootstraps, dispositions and PASS of gate parts 4 to 7.

    series   every series to score (the candidate, the comparators, reported ones)
    cand     the candidate's key; comparators: keys the rule reads (F, B)
    dep      the candidate's departure from series[null_key] (the permutation null);
             None skips the null (reported as not run, and PASS is then impossible)
    planted_pass  the planted check's result; None means not run (PASS impossible)
    reported the keys scored against the comparators on the same draws, deciding nothing
    """
    pts = point_cells(design, series)
    boots = {}
    for i, kind in enumerate(BOOTS):
        boots[kind] = boot_rmse(design, series, kind, boot_b, seed)
        if log:
            sds = {c: {o: round(float(np.std(boots[kind][c][o] - boots[kind][cand][o], ddof=1)), 4)
                       for o in OUTCOMES} for c in comparators}
            log(f"bootstrap {kind}: B {boot_b}, sd of d by comparator and outcome {sds}")
    cells = {}
    for c in comparators:
        cells[c] = {}
        for o in OUTCOMES:
            d = pts[c][o]["rmse"] - pts[cand][o]["rmse"]
            cells[c][o] = {k: _summ(d, boots[k][c][o] - boots[k][cand][o]) for k in BOOTS}
    disp = {c: disposition(cells[c]) for c in comparators}
    rep_cells = {}
    for r in reported:
        rep_cells[r] = {}
        for c in comparators:
            rep_cells[r][c] = {}
            for o in OUTCOMES:
                d = pts[c][o]["rmse"] - pts[r][o]["rmse"]
                rep_cells[r][c][o] = {k: _summ(d, boots[k][c][o] - boots[k][r][o]) for k in BOOTS}
        rep_cells[r]["disposition_reported"] = {c: disposition(rep_cells[r][c]) for c in comparators}
    null = None
    if dep is not None and null_key is not None:
        dist = perm_null(design, series[null_key], dep, series[cand].rpw, perm_n, seed)
        null = {}
        for o in DECIDING:
            d = pts[null_key][o]["rmse"] - pts[cand][o]["rmse"]
            q95 = float(np.percentile(dist[o], 95))
            null[o] = {"d_vs_null": d, "perm_q95": q95, "perm_mean": float(np.mean(dist[o])),
                       "perm_max": float(np.max(dist[o])), "cleared": bool(d > q95), "n": perm_n}
    null_ok = bool(null) and all(null[o]["cleared"] for o in DECIDING)
    wins_all = all(disp[c] == "WIN" for c in comparators)
    if planted_pass is False:
        verdict = "UNRESOLVED (the design did not recover a planted departure)"
    elif wins_all and null_ok and planted_pass:
        verdict = "PASS"
    else:
        verdict = "NOT PASS"
    return {"points": pts, "cells": cells, "dispositions": disp, "reported": rep_cells,
            "permutation_null": null,
            "null_cleared": null_ok, "planted_pass": planted_pass, "verdict": verdict,
            "boot_b": boot_b, "seed": seed}


# --------------------------------------------------------------- planted check
def synthetic_design(design: Design, t_star: np.ndarray, rpw: np.ndarray, rng: np.random.Generator,
                     sigma_rd: float, sigma_w: float) -> Design:
    """Synthetic outcomes from a true club sum; reads only design.g and the season grid."""
    g = design.g
    above = t_star - _season_rate(design, t_star) * g
    rd = rpw * above + rng.normal(0.0, sigma_rd, size=len(g))
    w = g / 2.0 + rd / rpw + rng.normal(0.0, sigma_w, size=len(g))
    base = 4.5 * g
    return replace(design, w=w, rs=base + rd / 2.0, ra=base - rd / 2.0)


def planted(design: Design, f: Series, dep: Departure, *, reps: int = PLANTED_REPS,
            boot_b: int = PLANTED_B, perm_n: int = PLANTED_PERM, sigma_rd: float = PLANTED_SIGMA_RD,
            sigma_w: float = PLANTED_SIGMA_W, seed: int = SEED, log=None) -> dict:
    """Gate part 6. Every series at F's runs per win. Reads no real outcome:
    design.w, rs and ra are replaced before anything is scored."""
    rng = np.random.default_rng(seed)
    truth_pass = fake_pass = 0
    rows = []
    for r in range(reps):
        tv, fv, rv = dep.permute(rng), dep.permute(rng), dep.permute(rng)
        bat, pit = f.sums()
        t_star = bat + pit + dep.club_sums(tv)
        syn = synthetic_design(design, t_star, f.rpw, rng, sigma_rd, sigma_w)
        bseed = int(rng.integers(0, 2 ** 31 - 1))
        ser = {"F": f, "T": with_departure(f, dep, tv), "X": with_departure(f, dep, fv),
               "R": with_departure(f, dep, rv)}
        dt = Departure(dep.player, dep.season, dep.shares, tv)
        dx = Departure(dep.player, dep.season, dep.shares, fv)
        st = score(syn, {k: ser[k] for k in ("F", "R", "T")}, "T", ("F", "R"), boot_b=boot_b,
                   seed=bseed, dep=dt, null_key="F", perm_n=perm_n, planted_pass=True)
        sx = score(syn, {k: ser[k] for k in ("F", "R", "X")}, "X", ("F", "R"), boot_b=boot_b,
                   seed=bseed, dep=dx, null_key="F", perm_n=perm_n, planted_pass=True)
        truth_pass += st["verdict"] == "PASS"
        fake_pass += sx["verdict"] == "PASS"
        rows.append({"rep": r, "truth": st["verdict"], "fake": sx["verdict"],
                     "truth_d_wins_vs_F": st["cells"]["F"]["wins"]["season"]["d"],
                     "fake_d_wins_vs_F": sx["cells"]["F"]["wins"]["season"]["d"]})
        if log:
            log(f"planted rep {r + 1}/{reps} (sd {sigma_rd:g} runs): truth {st['verdict']}, "
                f"fake {sx['verdict']}")
    # the thresholds are 16 of 20 and 1 of 20, scaled when a dry run uses fewer replicates
    ok = (truth_pass >= math.ceil(PLANTED_PASS_MIN * reps / PLANTED_REPS)
          and fake_pass <= math.floor(PLANTED_FAKE_MAX * reps / PLANTED_REPS))
    return {"sigma_rd": sigma_rd, "sigma_w": sigma_w, "reps": reps, "boot_b": boot_b,
            "perm_n": perm_n, "truth_pass": truth_pass, "fake_pass": fake_pass,
            "planted_pass": ok, "rows": rows}


def identity_check(design: Design, f: Series) -> dict:
    """F scored as its own candidate: d = 0 exactly on every cell and no PASS."""
    sc = score(design, {"F": f, "F0": f}, "F", ("F0",), boot_b=50, seed=SEED, planted_pass=True)
    zero = all(sc["cells"]["F0"][o][k]["d"] == 0.0 for o in OUTCOMES for k in BOOTS)
    return {"all_d_zero": zero, "verdict": sc["verdict"], "ok": zero and sc["verdict"] != "PASS"}


# ----------------------------------------------------------------- part 8
def _pearson(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def miss_table(design: Design, series: Mapping[str, Series], factors: Mapping[str, np.ndarray],
               top_n: int = 10) -> dict:
    """Residuals beside club-season factors; NaN factor values are left out per factor."""
    out = {}
    for k, s in series.items():
        e = errors(design, s)
        rec = {}
        for o in OUTCOMES:
            res = e[o]
            per = {}
            cols = []
            for name, fx in factors.items():
                fx = np.asarray(fx, float)
                ok = np.isfinite(fx)
                x, y = fx[ok], res[ok]
                if len(x) < 3:
                    per[name] = None
                    continue
                r = _pearson(x, y)
                slope = (float(np.mean((x - x.mean()) * (y - y.mean())) / np.var(x))
                         if np.var(x) > 0 else None)
                lo_cut, hi_cut = np.percentile(x, [100 / 3, 200 / 3])
                top = np.abs(y[x >= hi_cut]).mean() if np.any(x >= hi_cut) else float("nan")
                bot = np.abs(y[x <= lo_cut]).mean() if np.any(x <= lo_cut) else float("nan")
                per[name] = {"r": r, "slope": slope, "abs_top_minus_bottom": float(top - bot),
                             "n": int(ok.sum())}
                cols.append(name)
            ok_all = np.all(np.column_stack([np.isfinite(np.asarray(factors[c], float))
                                             for c in cols]), axis=1) if cols else np.zeros(0, bool)
            joint = None
            if cols and ok_all.sum() > len(cols) + 2:
                xm = np.column_stack([np.ones(int(ok_all.sum()))]
                                     + [np.asarray(factors[c], float)[ok_all] for c in cols])
                y = res[ok_all]
                beta, *_ = np.linalg.lstsq(xm, y, rcond=None)
                fit = xm @ beta
                sst = float(np.sum((y - y.mean()) ** 2))
                joint = float(1.0 - np.sum((y - fit) ** 2) / sst) if sst > 0 else None
            rec[o] = {"factors": per, "joint_rsq": joint, "rmse": rmse(res)}
        order = np.argsort(-np.abs(e["wins"]))[:top_n]
        rec["largest_wins_misses"] = [
            {"season": int(design.season[i]), "club": design.club[i],
             "wins": float(design.w[i]), "residual": float(e["wins"][i])} for i in order]
        out[k] = rec
    return out


# ------------------------------------------------------------ frame helpers
def allocation_shares(stints: Iterable[tuple], exposure_floor: float = 0.0) -> dict:
    """{club: share} for one player-season-side from (club, exposure, games) stints:
    by exposure, else by games, else equally (gate part 3)."""
    st = list(stints)
    if not st:
        return {}
    for idx in (1, 2):
        tot = sum(max(0.0, float(x[idx] or 0.0)) for x in st)
        if tot > exposure_floor:
            out: dict = {}
            for x in st:
                out[x[0]] = out.get(x[0], 0.0) + max(0.0, float(x[idx] or 0.0)) / tot
            return out
    out = {}
    for x in st:
        out[x[0]] = out.get(x[0], 0.0) + 1.0 / len(st)
    return out


def check_standings(season: int, clubs: Mapping[str, Mapping]) -> None:
    """Refusal 1."""
    if len(clubs) != CLUBS_PER_SEASON:
        raise AccountingRefusal(f"{season}: {len(clubs)} clubs in the standings, expected 30")
    rs = sum(c["rs"] for c in clubs.values())
    ra = sum(c["ra"] for c in clubs.values())
    w = sum(c["w"] for c in clubs.values())
    lo = sum(c["l"] for c in clubs.values())
    if rs != ra:
        raise AccountingRefusal(f"{season}: league runs scored {rs} differ from runs allowed {ra}")
    if w != lo:
        raise AccountingRefusal(f"{season}: league wins {w} differ from losses {lo}")


def to_jsonable(x, nd: int = 6):
    if isinstance(x, dict):
        return {str(k): to_jsonable(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v, nd) for v in x]
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return None if not math.isfinite(f) else round(f, nd)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.ndarray):
        return to_jsonable(x.tolist(), nd)
    return x
