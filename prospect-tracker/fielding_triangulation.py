# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fielding triangulation (fielding_triangulation_v1), the pure core.

Registered in docs/ewar/FIELDING_TRIANGULATION_GATE.md (parts 3 and 4) before any
number existed. Each published fielding system (SDR, OAA, DRS, UZR and FanGraphs'
fielding runs at the position, FRP) is read as a noisy reading of one latent
fielding skill per position:

  rates      x_s,r = 1000 * runs / innings, centred within (position, season)
  signal     lambda from the leading eigenpair of the cross-season covariance C
             (noise is independent across seasons whatever data two readings share)
  total      Sigma(n) = A + Psi * 1000 / n, A and Psi by a least-squares fit of the
             same-season products x_s x_t on 1000 / n
  the row    T_rate = lambda_FRP * lambda_a' Sigma_aa(n)^-1 x_a over the readings a
             present on the row: the best linear predictor of the row's next-season
             FanGraphs fielding rate at its own innings

Catchers (OAA and UZR do not rate them) are valued on SDR's catcher components,
framing, blocking and throwing, each shrunk by its own reliability (B1's rule).

The eWAR v3 part S3t (gate part 4): g = T_i - the base's fielding, re-centred per PA
per season over hitters (swar.recentre).

PURE: no network, no file I/O. tools/fielding_triangulation_lab.py loads the caches,
fits once (data/_labs/fielding_triangulation_fit.json) and runs the one read.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional

import numpy as np
import pandas as pd

#: The seven series fitted jointly (gate part 3.2). FRP is the reference scale.
SERIES = ("sdr", "sdr_no_drs", "sdr_no_statcast", "oaa", "drs", "uzr", "frp")
REF = "frp"

#: The configurations of gate part 3.5. A configuration uses sub-blocks of the one fit.
CONFIGS = {
    "FULL": ("sdr", "oaa", "drs", "uzr", "frp"),
    "X_DRS": ("sdr_no_drs", "oaa", "frp"),
    "X_UZR": ("sdr_no_drs", "oaa", "frp"),
    "X_SC": ("sdr_no_statcast", "drs", "uzr"),
}

NONC_POS = ("1B", "2B", "3B", "SS", "LF", "CF", "RF")
CATCHER = "C"
#: SDR's catcher components (gate part 3.6): framing CFraming, blocking bFRP, throwing tFRP.
CATCHER_COMPONENTS = ("framing", "blocking", "throwing")

FIT_SEASONS = (2016, 2017, 2018)
CROSS_YEARS = (2016, 2017)          # predictor seasons of the fit's cross-season pairs
SAME_MIN_INN = 100.0
CROSS_MIN_INN = 200.0
CATCHER_PAIR_MIN_INN = 300.0
MIN_SAME_ROWS = 30
MIN_CROSS_PAIRS = 20
PSI_FLOOR = 0.001
R_CLAMP = (0.05, 0.95)
PER = 1000.0


class FitStop(Exception):
    """A registered precondition of the fit failed; nothing is written."""


# ---------------------------------------------------------------------------
# rates
# ---------------------------------------------------------------------------

def centred_rates(rows: pd.DataFrame, cols: Iterable[str], group=("pos", "season"),
                  inn: str = "inn") -> pd.DataFrame:
    """x_<c> = 1000 * c / inn, minus the innings-weighted mean of that rate over the
    rows of its (position, season) where c is present. NaN where c is absent."""
    out = rows.copy()
    n = out[inn].astype(float).to_numpy()
    for c in cols:
        y = pd.to_numeric(out[c], errors="coerce").astype(float)
        x = np.where(n > 0, PER * y.to_numpy() / np.where(n > 0, n, 1.0), np.nan)
        out[f"x_{c}"] = x
        ok = np.isfinite(x)
        w = np.where(ok, n, 0.0)
        tmp = pd.DataFrame({"g0": out[group[0]].to_numpy(), "g1": out[group[1]].to_numpy(),
                            "wx": np.where(ok, w * np.nan_to_num(x), 0.0), "w": w})
        sums = tmp.groupby(["g0", "g1"])[["wx", "w"]].transform("sum")
        mean = np.where(sums.w > 0, sums.wx / sums.w.where(sums.w > 0, 1.0), 0.0)
        out[f"x_{c}"] = np.where(ok, x - mean, np.nan)
    return out


# ---------------------------------------------------------------------------
# the fit (gate part 3)
# ---------------------------------------------------------------------------

def _psd(m: np.ndarray, floor: float) -> np.ndarray:
    m = 0.5 * (m + m.T)
    w, v = np.linalg.eigh(m)
    w = np.maximum(w, floor)
    return (v * w) @ v.T


def cross_pairs(rows: pd.DataFrame, years: Iterable[int], min_inn: float) -> pd.DataFrame:
    """Same player, same position, seasons Y and Y+1, both at min_inn or more."""
    a = rows[rows.season.isin(list(years)) & (rows.inn >= min_inn)]
    b = rows[rows.inn >= min_inn].copy()
    b["season"] = b.season - 1
    return a.merge(b, on=["player_id", "season", "pos"], suffixes=("", "_n"))


def fit_position(rows_p: pd.DataFrame, series: Iterable[str] = SERIES,
                 fit_seasons: Iterable[int] = FIT_SEASONS,
                 cross_years: Iterable[int] = CROSS_YEARS) -> dict:
    """One position's model from its rows (columns player_id, season, pos, inn and
    x_<s> for each series). Reads no season outside fit_seasons."""
    series = list(series)
    fit_seasons = list(fit_seasons)
    rows_p = rows_p[rows_p.season.isin(fit_seasons)]
    same = rows_p[rows_p.inn >= SAME_MIN_INN]
    pairs = cross_pairs(rows_p, [y for y in cross_years if y + 1 in fit_seasons], CROSS_MIN_INN)
    dropped: dict[str, str] = {}

    def n_same(s, t):
        return int((same[f"x_{s}"].notna() & same[f"x_{t}"].notna()).sum())

    def n_cross(s, t):
        return int((pairs[f"x_{s}"].notna() & pairs[f"x_{t}_n"].notna()).sum())

    keep = list(series)
    if REF not in keep:
        raise FitStop("the reference series FRP is not in the fit")
    # series floors: same-season rows and cross-season pairs against FRP
    for s in list(keep):
        if s == REF:
            continue
        if n_same(s, s) < MIN_SAME_ROWS:
            dropped[s] = f"{n_same(s, s)} same-season rows (< {MIN_SAME_ROWS})"
            keep.remove(s)
        elif min(n_cross(s, REF), n_cross(REF, s)) < MIN_CROSS_PAIRS:
            dropped[s] = f"{min(n_cross(s, REF), n_cross(REF, s))} cross-season pairs against FRP (< {MIN_CROSS_PAIRS})"
            keep.remove(s)
    if n_same(REF, REF) < MIN_SAME_ROWS or n_cross(REF, REF) < MIN_CROSS_PAIRS:
        raise FitStop("FRP fails its own floors at this position")
    # pair floor: the series with fewer rows of the pair leaves (ties: the later one)
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(keep):
            for t in keep[i + 1:]:
                if n_same(s, t) < MIN_SAME_ROWS:
                    loser = s if (n_same(s, s), -keep.index(s)) < (n_same(t, t), -keep.index(t)) else t
                    if loser == REF:
                        loser = t if loser == s else s
                    dropped[loser] = f"{n_same(s, t)} same-season rows with {t if loser == s else s}"
                    keep.remove(loser)
                    changed = True
                    break
            if changed:
                break
    k = len(keep)
    C = np.full((k, k), np.nan)
    nC = np.zeros((k, k), int)
    for i, s in enumerate(keep):
        for j, t in enumerate(keep):
            m = pairs[f"x_{s}"].notna() & pairs[f"x_{t}_n"].notna()
            nC[i, j] = int(m.sum())
            if m.sum():
                C[i, j] = float(np.mean(pairs.loc[m, f"x_{s}"] * pairs.loc[m, f"x_{t}_n"]))
    if not np.all(np.isfinite(C)):
        raise FitStop("a cross-season covariance entry has no pair")
    C = 0.5 * (C + C.T)
    e, v = np.linalg.eigh(C)
    lam = np.sqrt(max(e[-1], 0.0)) * v[:, -1]
    if lam.sum() < 0:
        lam = -lam
    A = np.zeros((k, k))
    Psi = np.zeros((k, k))
    nA = np.zeros((k, k), int)
    for i, s in enumerate(keep):
        for j, t in enumerate(keep):
            if j < i:
                continue
            m = same[f"x_{s}"].notna() & same[f"x_{t}"].notna()
            y = (same.loc[m, f"x_{s}"] * same.loc[m, f"x_{t}"]).to_numpy(float)
            X = np.column_stack([np.ones(int(m.sum())), PER / same.loc[m, "inn"].to_numpy(float)])
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            A[i, j] = A[j, i] = coef[0]
            Psi[i, j] = Psi[j, i] = coef[1]
            nA[i, j] = nA[j, i] = int(m.sum())
    A_raw, Psi_raw = A.copy(), Psi.copy()
    A = _psd(A, 0.0)
    tr = float(np.trace(Psi))
    Psi = _psd(Psi, PSI_FLOOR * tr / k if tr > 0 else 1e-6)
    return {
        "series": keep, "dropped": dropped,
        "lambda": lam.tolist(), "C": C.tolist(), "A": A.tolist(), "Psi": Psi.tolist(),
        "A_raw": A_raw.tolist(), "Psi_raw": Psi_raw.tolist(),
        "n_same_rows": nA.tolist(), "n_cross_pairs": nC.tolist(),
        "n_rows_fit": int(len(same)), "n_pairs_fit": int(len(pairs)),
        "eigenvalues_C": [float(x) for x in e[::-1]],
    }


def fit_catcher(rows_c: pd.DataFrame, fit_seasons: Iterable[int] = FIT_SEASONS,
                cross_years: Iterable[int] = CROSS_YEARS) -> dict:
    """K_k per catcher component by B1's rule (gate part 3.6). rows_c carries
    x_<component> centred within season over catcher rows."""
    fit_seasons = list(fit_seasons)
    rows_c = rows_c[rows_c.season.isin(fit_seasons)]
    pairs = cross_pairs(rows_c, [y for y in cross_years if y + 1 in fit_seasons],
                        CATCHER_PAIR_MIN_INN)
    out = {}
    for comp in CATCHER_COMPONENTS:
        m = pairs[f"x_{comp}"].notna() & pairs[f"x_{comp}_n"].notna()
        q = pairs[m]
        if len(q) < 3 or q[f"x_{comp}"].std() == 0 or q[f"x_{comp}_n"].std() == 0:
            out[comp] = {"r": None, "r_clamped": None, "hm": None, "K": None, "n_pairs": int(len(q))}
            continue
        r = float(np.corrcoef(q[f"x_{comp}"], q[f"x_{comp}_n"])[0, 1])
        rc = min(max(r, R_CLAMP[0]), R_CLAMP[1])
        hm = float(np.mean(2.0 / (1.0 / q.inn.to_numpy(float) + 1.0 / q.inn_n.to_numpy(float))))
        K = float(round(hm * (1.0 - rc) / rc))
        out[comp] = {"r": r, "r_clamped": rc, "hm": hm, "K": K, "n_pairs": int(len(q))}
    return out


# ---------------------------------------------------------------------------
# the row (gate part 3.4)
# ---------------------------------------------------------------------------

def _arrays(model: Mapping) -> tuple[list, np.ndarray, np.ndarray, np.ndarray]:
    return (list(model["series"]), np.asarray(model["lambda"], float),
            np.asarray(model["A"], float), np.asarray(model["Psi"], float))


def t_rate(model: Mapping, x: Mapping[str, float], n: float, config: Iterable[str]) -> float:
    """T_rate of one row: lambda_FRP * lambda_a' Sigma_aa(n)^-1 x_a, 0 when a is empty."""
    series, lam, A, Psi = _arrays(model)
    ref = lam[series.index(REF)]
    idx = [series.index(s) for s in config
           if s in series and x.get(s) is not None and np.isfinite(x.get(s))]
    if not idx or not n or n <= 0:
        return 0.0
    S = A[np.ix_(idx, idx)] + Psi[np.ix_(idx, idx)] * PER / float(n)
    xa = np.array([x[series[i]] for i in idx], float)
    return float(ref * lam[idx] @ np.linalg.solve(S, xa))


def t_rates(model: Mapping, rows: pd.DataFrame, config: Iterable[str]) -> np.ndarray:
    """T_rate for every row of one position (columns inn and x_<s>)."""
    config = list(config)
    cols = [f"x_{s}" for s in config]
    present = [c for c in cols if c in rows.columns]
    X = rows[present].to_numpy(float) if present else np.zeros((len(rows), 0))
    names = [c[2:] for c in present]
    n = rows.inn.to_numpy(float)
    out = np.empty(len(rows))
    for i in range(len(rows)):
        out[i] = t_rate(model, {s: X[i, j] for j, s in enumerate(names)}, n[i], config)
    return out


def weights(model: Mapping, n: float, config: Iterable[str] = CONFIGS["FULL"]) -> dict:
    """w(n) = lambda_FRP * Sigma_aa(n)^-1 lambda_a with every configured reading present:
    T_rate = w . x. Also each reading's share of the absolute weights."""
    series, lam, A, Psi = _arrays(model)
    ref = lam[series.index(REF)]
    idx = [series.index(s) for s in config if s in series]
    S = A[np.ix_(idx, idx)] + Psi[np.ix_(idx, idx)] * PER / float(n)
    w = ref * np.linalg.solve(S, lam[idx])
    tot = float(np.abs(w).sum()) or 1.0
    return {series[i]: {"w": float(wi), "share_abs": float(abs(wi) / tot)} for i, wi in zip(idx, w)}


def catcher_runs(fit_c: Mapping, rows_c: pd.DataFrame) -> np.ndarray:
    """T_C per catcher row: sum over components of (centred runs) * n / (n + K_k);
    a missing component or an unfitted K contributes 0."""
    n = rows_c.inn.to_numpy(float)
    out = np.zeros(len(rows_c))
    for comp in CATCHER_COMPONENTS:
        K = (fit_c.get(comp) or {}).get("K")
        col = f"x_{comp}"
        if K is None or col not in rows_c.columns:
            continue
        x = rows_c[col].to_numpy(float)
        ok = np.isfinite(x) & (n > 0)
        out += np.where(ok, np.nan_to_num(x) * n / PER * n / (n + K), 0.0)
    return out


# ---------------------------------------------------------------------------
# the eWAR v3 part S3t (gate part 4)
# ---------------------------------------------------------------------------

def part_g(t_runs: float, fld: float, frm: Optional[float], caught: bool) -> float:
    """g_fldt,i = T_i - (Fld_i + Frm_i if he caught, else Fld_i): dem_plus.fld_total."""
    base = float(fld or 0.0) + (float(frm or 0.0) if caught else 0.0)
    return float(t_runs) - base


def season_part(rows: Mapping[int, Mapping]) -> dict[int, dict]:
    """One season's hitters: {mlbam: {t_runs, fld, frm, caught, pa, pitcher_batter}}
    -> {mlbam: {g, d}}, d re-centred per PA over the season's hitters (swar.recentre),
    pitcher-batters at 0 outside the re-centring."""
    import swar                                    # noqa: PLC0415 (pure)
    g, pa = {}, {}
    for mid, r in rows.items():
        if r.get("pitcher_batter"):
            continue
        g[mid] = part_g(r.get("t_runs") or 0.0, r.get("fld") or 0.0, r.get("frm"),
                        bool(r.get("caught")))
        pa[mid] = float(r.get("pa") or 0.0)
    d = swar.recentre(g, pa)
    out = {}
    for mid, r in rows.items():
        if r.get("pitcher_batter"):
            out[mid] = {"g": 0.0, "d": 0.0}
        else:
            out[mid] = {"g": g[mid], "d": float(d.get(mid, 0.0))}
    return out


def permute_within(values: np.ndarray, groups: pd.DataFrame, seed: int) -> np.ndarray:
    """The twin: values permuted within each group (position, season), one draw."""
    rng = np.random.default_rng(seed)
    out = np.asarray(values, float).copy()
    for _, idx in groups.groupby(list(groups.columns)).indices.items():
        out[idx] = out[idx][rng.permutation(len(idx))]
    return out
