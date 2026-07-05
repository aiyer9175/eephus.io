# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Phase 7 (Tier 2) -- the upgrade-option layer.

A prospect's grade is a call option on development: a low FV is worth more than
its modal outcome because it can UPGRADE to a better grade before graduating. We
model the grade as a role-split absorbing Markov chain with an annual step:

  transient states = FV grades {35,40,45,50,55,60,65,70}
  absorbing states = graduated (reaches MLB) and out (released / washes out)

Transitions are estimated from our OWN dated grade history (prospects.db
`snapshots`, fangraphs + mlb_pipeline pooled to one grade per player per year)
with Laplace smoothing; graduation is a debut (data/debuts.json), out is an
inactive/washed-out player (data/inactive.json). We NEVER fabricate a
transition: the last observed year of a still-active, non-graduated, non-inactive
player is censored and dropped.

Valuation (payoff = the valuation set's TABLE value of the grade a player
graduates FROM):
  total     = expected payoff under the FULL chain (grade can move)
  intrinsic = expected payoff under FROZEN-grade transitions (grade cannot move;
              the player only stays, graduates, or washes out at his current grade)
  option    = total - intrinsic
  OPT%      = option / total

Low grades are long-dated out-of-the-money calls: most of their value is option.
A config-prior mode (literature-derived one-step priors, NOT estimated from our
data) is available as a labelled fallback when history is insufficient.
"""
from __future__ import annotations

import functools
import json
import sqlite3
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_DB = _HERE / "prospects.db"
_DATA = _HERE / "data"

GRADES = [35, 40, 45, 50, 55, 60, 65, 70]
_N = len(GRADES)
_GRAD, _OUT = _N, _N + 1          # absorbing column indices
_LAPLACE = 0.5                    # per-cell additive smoothing
_SOURCES = ("fangraphs", "mlb_pipeline")
_PITCHER_TOKENS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP", "CL", "P"}

# Literature-derived one-step priors (config-prior mode ONLY; anchor: a 45 FV
# position player upgrades to 50+ at roughly 20% before graduating). Clearly
# labelled as NOT estimated from our data. Used only if history is insufficient.
_CONFIG_PRIOR_UPGRADE = {35: 0.10, 40: 0.15, 45: 0.20, 50: 0.16,
                         55: 0.12, 60: 0.08, 65: 0.05, 70: 0.02}


def _snap_tier(fv: float) -> int:
    g = int(fv / 5.0 + 0.5) * 5
    return max(GRADES[0], min(GRADES[-1], g))


def _is_pitcher(position: str | None) -> bool:
    if not position:
        return False
    return any(tok in _PITCHER_TOKENS for tok in str(position).upper().split("/"))


@functools.lru_cache(maxsize=1)
def _absorbing() -> tuple[dict, dict]:
    """(debut_year_by_key, inactive_key_set) from committed data files."""
    debut = {}
    try:
        d = json.loads((_DATA / "debuts.json").read_text(encoding="utf-8"))
        d = d if isinstance(d, list) else (d.get("players") or [])
        for r in d:
            pk, dd = r.get("player_key"), r.get("debut_date")
            if pk and dd:
                try:
                    debut[pk] = int(str(dd)[:4])
                except ValueError:
                    pass
    except (OSError, ValueError):
        pass
    inactive = set()
    try:
        ia = json.loads((_DATA / "inactive.json").read_text(encoding="utf-8"))
        ia = ia if isinstance(ia, list) else (ia.get("players") or [])
        inactive = {r.get("player_key") for r in ia if r.get("player_key")}
    except (OSError, ValueError):
        pass
    return debut, inactive


def _grade_series() -> dict:
    """player_key -> {"role": is_pitcher, "years": {year: tier}} pooling the
    per-source FV to one grade per calendar year (mean FV across sources, snapped
    to the nearest tier). Role = the player's modal pitcher/hitter classification."""
    if not _DB.exists():
        return {}
    con = sqlite3.connect(str(_DB))
    try:
        q = ("SELECT player_key, position, snapshot_date, fv FROM snapshots "
             f"WHERE source IN ({','.join('?' * len(_SOURCES))}) AND fv IS NOT NULL")
        rows = con.execute(q, _SOURCES).fetchall()
    finally:
        con.close()
    # player -> year -> list of fv ; player -> pitcher-vote counters
    by_year: dict = {}
    pit_votes: dict = {}
    for pk, pos, date, fv in rows:
        if not pk or not date:
            continue
        try:
            yr = int(str(date)[:4])
            fvf = float(fv)
        except (TypeError, ValueError):
            continue
        by_year.setdefault(pk, {}).setdefault(yr, []).append(fvf)
        v = pit_votes.setdefault(pk, [0, 0])
        v[0 if _is_pitcher(pos) else 1] += 1
    out = {}
    for pk, yrs in by_year.items():
        series = {y: _snap_tier(sum(vs) / len(vs)) for y, vs in yrs.items()}
        votes = pit_votes.get(pk, [0, 1])
        out[pk] = {"role": votes[0] > votes[1], "years": series}
    return out


@functools.lru_cache(maxsize=2)
def transition_counts(is_pitcher: bool) -> np.ndarray:
    """Count matrix (n_grades x n_grades+2): grade -> {grades, graduated, out}.
    One annual step; last-year of a still-active player is censored (dropped)."""
    debut, inactive = _absorbing()
    C = np.zeros((_N, _N + 2))
    gi = {g: i for i, g in enumerate(GRADES)}
    for pk, rec in _grade_series().items():
        if rec["role"] != is_pitcher:
            continue
        years = rec["years"]
        if not years:
            continue
        ys = sorted(years)
        last = ys[-1]
        for y in ys:
            g = years[y]
            row = gi[g]
            if (y + 1) in years:                       # observed grade next year
                C[row, gi[years[y + 1]]] += 1
            elif y == last:                            # terminal event at the last year
                if pk in debut and debut[pk] >= y:
                    C[row, _GRAD] += 1
                elif pk in inactive:
                    C[row, _OUT] += 1
                # else: still active, no next obs -> censored, drop
            # gap years (y+1 unobserved, not last) -> censored, drop
    return C


def transition_matrix(is_pitcher: bool) -> np.ndarray:
    """Row-stochastic transition matrix with Laplace smoothing."""
    C = transition_counts(is_pitcher).astype(float)
    P = C + _LAPLACE
    P /= P.sum(axis=1, keepdims=True)
    return P


def _payoffs(is_pitcher: bool, set_id: str) -> np.ndarray:
    import valuation_sets as vs
    return np.array([float(vs.table_value_musd(set_id, float(g), is_pitcher) or 0.0)
                     for g in GRADES])


def option_valuation(is_pitcher: bool, set_id: str = "clemens_2026",
                     mode: str = "data") -> dict:
    """Per starting grade: total / intrinsic / option / OPT% ($M), plus the
    per-grade observation count (sample size). mode='data' estimates the chain
    from our snapshots; mode='config_prior' uses labelled literature priors."""
    payoff = _payoffs(is_pitcher, set_id)
    counts = transition_counts(is_pitcher)
    n_obs = counts.sum(axis=1)
    if mode == "config_prior":
        # Frozen graduate/out rates from data, upgrade mass from the labelled prior
        # split evenly across strictly-higher grades. Diagnostic only.
        P = transition_matrix(is_pitcher)
        for i, g in enumerate(GRADES):
            up = _CONFIG_PRIOR_UPGRADE.get(g, 0.0)
            higher = [j for j in range(_N) if j > i]
            grad, out = P[i, _GRAD], P[i, _OUT]
            stay = max(0.0, 1.0 - up - grad - out)
            row = np.zeros(_N + 2)
            row[i] = stay
            for j in higher:
                row[j] = up / len(higher)
            row[_GRAD], row[_OUT] = grad, out
            if row.sum() > 0:
                P[i] = row / row.sum()
    else:
        P = transition_matrix(is_pitcher)
    Q = P[:, :_N]
    r_grad = P[:, _GRAD]
    r_out = P[:, _OUT]
    N = np.linalg.inv(np.eye(_N) - Q)      # expected visits to each transient grade
    # total(g0) = sum_g N[g0,g] * P(graduate from g) * payoff(g)
    total = N @ (r_grad * payoff)
    # intrinsic(g0) = P(graduate | frozen at g0) * payoff(g0)
    with np.errstate(divide="ignore", invalid="ignore"):
        p_grad_frozen = np.where((r_grad + r_out) > 0, r_grad / (r_grad + r_out), 0.0)
    intrinsic = p_grad_frozen * payoff
    option = total - intrinsic
    with np.errstate(divide="ignore", invalid="ignore"):
        opt_pct = np.where(total > 0, option / total, 0.0)
    rows = {}
    for i, g in enumerate(GRADES):
        rows[g] = {"total_musd": round(float(total[i]), 2),
                   "intrinsic_musd": round(float(intrinsic[i]), 2),
                   "option_musd": round(float(option[i]), 2),
                   "opt_pct": round(float(opt_pct[i]), 4),
                   "n_obs": int(n_obs[i]),
                   "p_upgrade_annual": round(float(Q[i, i + 1:].sum()), 4),
                   "p_graduate_annual": round(float(r_grad[i]), 4),
                   "p_out_annual": round(float(r_out[i]), 4)}
    return {"role": "pitcher" if is_pitcher else "hitter", "mode": mode,
            "set_id": set_id, "grades": rows}


def data_sufficient(min_total_obs: int = 2000, min_grades_covered: int = 5) -> bool:
    """History is sufficient if we hold enough annual grade observations across
    enough grades to estimate the chain (recon: ~14.6k transitions across 2011-26)."""
    tot = 0
    covered = 0
    for is_pit in (False, True):
        c = transition_counts(is_pit)
        per = c.sum(axis=1)
        tot += int(per.sum())
        covered = max(covered, int((per >= 30).sum()))
    return tot >= min_total_obs and covered >= min_grades_covered
