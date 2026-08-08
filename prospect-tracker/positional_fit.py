# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Positional-conversion model -> data/positional_fit.json.

THE QUESTION
    "Randy Arozarena is a horrible outfielder this season; he is extremely likely
    to be converted to 1B/DH. Which hitters would be more valuable at a different
    position?"

THE ANSWER SHAPE
    A hitter's value per 650 PA at position p is

        V(i, p) = BAT(i)  +  FIELD(i, p)  +  LADDER(p)

    The bat is position-independent, so it cancels out of every COMPARISON between
    positions: the ranking of positions for a player depends only on FIELD + LADDER.
    The bat is still carried, because it sets whether the player is worth a roster
    spot at the bottom of the spectrum at all.

    FIELD(i, p) is the piece that has to be modelled, because a player is only ever
    measured at the one or two positions he actually played. The model is

        rate(i, p) = D(p) + s(p) * z(i)          [FRP per 1000 defensive innings]

    z(i) is a latent glove in standard units, D(p) is how much easier it is to
    accumulate fielding runs at p (Savant centres OAA WITHIN position, so D is only
    identified from players who played two positions in the same season), and s(p)
    is how much a glove is WORTH at p. s(p) is the interaction that makes a move
    player-specific: a poor glove loses far more at shortstop (s = 5.5 runs per
    1000 innings per unit of z) than at first base (s = 2.3), so moving him down
    recovers real runs, while an average glove recovers nothing and just eats the
    positional-adjustment loss.

THREE THINGS THIS MODEL DOES THAT THE NAIVE VERSION DOES NOT
    1. The positional ladder is RE-ESTIMATED from Baseball-Reference's own
       construction rather than taken from the folklore table, on a rolling
       six-season window that a forward-chained gate chose over the retired
       2012-onward pool (see LADDER_WINDOW_SEASONS). The folklore ladder is wrong
       by about 4.1 runs at 1B and treats 2B/3B/CF as one rung when the current
       window says 5.12 / 3.62 / 4.14.
    2. Single-season OAA is shrunk toward league average with a per-position
       reliability constant measured from year-over-year persistence. First base is
       the least reliable read in baseball (k = 2539 innings), shortstop the most
       (k = 874), so an identical raw OAA means very different things.
    3. The naive "worse fielders gain more from moving" regression is mostly
       REGRESSION TO THE MEAN, not a real interaction. Section INTERACTION of the
       report shows the observed slope is predicted, to within its bootstrap CI, by
       measurement error alone. The model therefore runs the interaction off the
       SHRUNK glove, not the raw one.

WHAT IS OUT OF SCOPE
    Catcher. Savant's OAA leaderboard returns zero rows at C in every season, and
    the catcher-framing leaderboard did not answer probes. Catchers are carried in
    the payload with a c_out_of_scope flag and are never offered a move.

Run:  python positional_fit.py                # build data/positional_fit.json
      python positional_fit.py --report       # fit + print every fitted number
      python positional_fit.py --validate     # historical-conversion backtest
      python positional_fit.py --player 668227
"""
from __future__ import annotations

import argparse
import datetime as _dt
import itertools
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "positional_fit.json"

# Positions Savant OAA covers. C has no OAA; DH has no defense.
OAA_POSITIONS = ("1B", "2B", "3B", "SS", "LF", "CF", "RF")
LADDER_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
IDX = {p: i for i, p in enumerate(OAA_POSITIONS)}

FIRST_OAA_SEASON = 2016
LADDER_EARLIEST_SEASON = 2000  # BRef runs_position goes back this far
# The SHIPPED ladder window, as a ROLLING count of the most recent seasons
# rather than a pinned first year. Era drift in these coefficients is larger
# than their own sampling CIs (2021-2026 reads SS 9.44 and 2B 5.17 against the
# retired 2012-2026 fit's 8.92 and 4.73, on CI half-widths of about 0.21), so a
# long pool averages two different tables instead of measuring one precisely.
#
# SIX IS GATED, NOT CHOSEN. docs/gate-2026-08-07-positional-ladder-recency.md
# pre-registered a forward-chained test (fit on seasons <= T-1, predict season
# T's runs_position per 650 PA) with the last-six-seasons window as the primary
# challenger, because 2018-onward was already a published sensitivity in this
# artifact and so introduced no new tuned parameter. Result, in
# data/positional_ladder_recency_eval.json: dMAE 0.097 runs per 650 PA in the
# challenger's favour, cluster-bootstrap CI95 [0.0789, 0.1145], better in 3 of 3
# held-out seasons, against a permuted-label control at -5.31. One attempt, one
# window, no re-tuning after the fact.
#
# The cost is paid in precision: about 2,000 fitted rows instead of 4,968, so
# the CIs widen. The window sensitivities below (2000, 2012, 2018) are published
# so a reader can price that trade rather than take it on faith.
LADDER_WINDOW_SEASONS = 6
# The window this replaced, kept as a NAME so the recency lab can reproduce the
# champion it was scored against and so the published sensitivities can show
# what the change was worth. It is not the shipped window any more; read
# fit.ladder.seasons off the artifact for that.
LADDER_RETIRED_FIRST_SEASON = 2012
LADDER_SENSITIVITY_WINDOWS = (LADDER_EARLIEST_SEASON, LADDER_RETIRED_FIRST_SEASON, 2018)
# ARTIFACT COUPLING, settled. This block used to warn that the on-disk artifact
# was still the 2012-2026 fit and that a regen would break two pins in
# test_positional_fit at once. THAT REGEN LANDED: data/positional_fit.json now
# reads fit.ladder.seasons [2021, 2026] and n_player_seasons 2023, the served
# slim view (data/positional_fit_ui.json) was rebuilt with it, and the test was
# rebased off any absolute first season onto a SPAN check against
# LADDER_WINDOW_SEASONS with a row floor of 1,800. Nothing here pins 2012 any
# more, so a future regen moves the window on its own without a code change.
#
# The dead alias that used to sit on this line, LADDER_FIRST_SEASON = 2012, is
# DELETED rather than deprecated: with the pins rebased it had no reader left in
# the tree, and a name that reads like "the window this model fits" while
# holding a retired value is exactly what made the warning above go stale
# unnoticed. LADDER_RETIRED_FIRST_SEASON carries the 2012 constant and has a
# live reader in LADDER_SENSITIVITY_WINDOWS, so nothing was lost.
MIN_PAIR_INN = 100.0           # innings at BOTH positions to count as a conversion pair
MIN_RELIABILITY_INN = 300.0    # innings floor for the year-over-year reliability fit
LADDER_MIN_PA = 200
WOBA_SCALE = 1.15              # fa_config.yaml projection.woba_scale
BAT_REGRESS_PA = 300.0         # regress wOBA toward league at this many PA
RECENCY = (1.0, 0.62, 0.38)    # weight on lag 0 / 1 / 2 seasons of glove evidence
FLAG_SIGMA = 1.0               # a move must clear this many SE of its own gain to flag
FLAG_MIN_GAIN = 3.0            # ...and this many runs per 650 PA
HEADLINE_MIN_PA = 250          # headline lists are regulars only
HEADLINE_MIN_INN = 400.0


# ============================================================== data loading
def _load(name: str) -> dict:
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"positional_fit: cannot read data/{name} ({exc}). "
                         f"Run savant_oaa.py and fielding_innings.py first.")


class Feeds:
    """Every input this model reads, joined on (mlbam, season)."""

    def __init__(self):
        self.oaa = _load("savant_oaa.json")
        self.inn = _load("fielding_innings.json")
        self.defhist = _load("mlb_def_history.json")["rows"]
        self.names = dict(self.oaa.get("names", {}))
        self._corpus = None

    # -- Savant OAA x StatsAPI innings -> per-position RATES
    def rates(self) -> dict:
        """(mlbam, season) -> {POS: {'rate','oaa_rate','inn','frp','oaa'}}"""
        out: dict = defaultdict(dict)
        seasons = self.inn.get("seasons", {})
        for mid, byyr in self.oaa.get("by_mlbam", {}).items():
            for y, byp in byyr.items():
                inns = seasons.get(y, {}).get(mid, {})
                for p, rec in byp.items():
                    if p.startswith("_"):
                        continue
                    inn = float((inns.get(p) or {}).get("inn", 0.0))
                    if inn <= 0:
                        continue
                    out[(int(mid), int(y))][p] = {
                        "rate": rec.get("frp", 0.0) * 1000.0 / inn,
                        "oaa_rate": rec.get("oaa", 0.0) * 1000.0 / inn,
                        "inn": inn,
                        "frp": rec.get("frp", 0.0),
                        "oaa": rec.get("oaa", 0.0),
                    }
        return dict(out)

    def innings(self, mlbam, season) -> dict:
        return self.inn.get("seasons", {}).get(str(season), {}).get(str(mlbam), {})

    def primary_position(self, mlbam, season, exclude_dh=True):
        rec = self.innings(mlbam, season)
        cand = {p: v for p, v in rec.items()
                if p != "P" and not (exclude_dh and p == "DH")}
        if not cand:
            return None
        return max(cand.items(), key=lambda kv: (kv[1]["inn"], kv[1]["g"]))[0]

    # -- fa corpus: age, PA, wOBA, and the league wOBA context
    def corpus(self):
        if self._corpus is None:
            try:
                import fa_projection as fp
                c = fp.build_corpus()
            except Exception as exc:                      # noqa: BLE001 - fail soft
                print(f"  [warn] corpus unavailable ({exc}); bat term will be 0")
                self._corpus = ({}, {})
                return self._corpus
            hit = {}
            for r in c["hit"]:
                hit[(int(r["mlbam"]), int(r["season"]))] = r
            self._corpus = (hit, c["league"])
        return self._corpus


# =============================================== 1. the positional adjustment
_FIELDERS = tuple(p for p in LADDER_POSITIONS if p != "DH")


def _ladder_design(feeds: Feeds, first: int, last: int, min_pa: int):
    """(X innings-share matrix, y runs_position/650PA, keys, inn_per_pa)."""
    ipp = []
    for k, v in feeds.defhist.items():
        m, y = k.split(":")
        if v["pa"] < 400 or not (first <= int(y) <= last):
            continue
        tot = sum(x["inn"] for p, x in feeds.innings(m, y).items() if p != "P")
        if tot > 0:
            ipp.append(tot / v["pa"])
    inn_per_pa = statistics.median(ipp) if ipp else 1.98

    rows, keys = [], []
    for k, v in feeds.defhist.items():
        m, y = k.split(":")
        if v["pa"] < min_pa or not (first <= int(y) <= last):
            continue
        byp = feeds.innings(m, y)
        if not byp:
            continue
        ex = {p: float((byp.get(p) or {}).get("inn", 0.0)) for p in LADDER_POSITIONS}
        fielded = sum(ex[p] for p in _FIELDERS)
        ex["DH"] = max(0.0, v["pa"] * inn_per_pa - fielded)
        tot = sum(ex.values())
        if tot <= 0:
            continue
        rows.append(([ex[p] / tot for p in LADDER_POSITIONS],
                     v["runs_position"] / v["pa"] * 650.0))
        keys.append((int(m), int(y)))
    return (np.array([r[0] for r in rows]), np.array([r[1] for r in rows]),
            keys, inn_per_pa)


def _recentre(beta, exposure):
    """Impose the exposure-weighted sum-to-zero identification.

    WHY THIS EXISTS. Every row of innings shares sums to 1, so X @ 1 = 1 and the
    OLS residuals are orthogonal to that column sum: the exposure-weighted sum of
    the coefficients equals mean(y) EXACTLY. mean(y) is the league's own average
    runs_position per 650 PA, which BRef ran at about -1 run through 2021 and ~0
    from 2022. So the fitted ladder's level is whatever the source data's level
    happened to be in the fitted window - it is a property of the window, not of
    the positions. Subtracting it makes the convention explicit and stable: the
    zero is 'the average defensive position of a qualified player-season', with
    every fitted player-season counted once. Say it that way and not 'weighted by
    the innings the league deploys': `exposure` is the column mean of the per-row
    innings SHARES, so a 200 PA season and a 700 PA season carry equal weight.
    See the note above `ident` in fit_ladder for what a true innings weighting
    would change (-0.0401 runs) and why the level is not worth re-weighting."""
    return beta - float(exposure @ beta)


def fit_ladder(feeds: Feeds, first=None, last=None,
               min_pa=LADDER_MIN_PA, boot=200, seed=11):
    """Recover the positional adjustment in runs per 650 PA.

    `first` defaults to the rolling LADDER_WINDOW_SEASONS window ending at
    `last`; pass it explicitly only to reproduce a retired window.

    This is an INVERSION, not a free fit. Baseball-Reference builds runs_position
    as a per-inning rate summed over the positions a player actually played, so
    regressing runs_position per 650 PA on the player's innings SHARES (no
    intercept) recovers the per-position constants BRef used. There is one free
    parameter per position and thousands of observations, so there is no
    overfitting surface: the diagnostic that matters is R-squared, and it is 0.98.

    DH carries no innings, so its exposure is the residual: a player's PA imply a
    total defensive-inning opportunity, and whatever he did not field, he did not
    field. That residual column is what identifies the DH rung.

    THE SUM QUESTION, answered once so it stops recurring. Three different sums
    are published in `identification` and only ONE of them is zero by
    construction:
      * exposure-weighted - zero, imposed. This is the identified quantity.
      * equal weight over all nine rungs - NOT zero, and should not be. Weighting
        DH like a fielding position asserts DH is a ninth of league exposure; it
        is 7.2% (pre-2022 the NL had no DH at all), so the big negative DH rung
        gets over-counted and the sum goes negative.
      * equal weight over the eight FIELDING rungs - NOT zero either, and this is
        the one that reads wrong. It is arithmetically forced: with the
        exposure-weighted sum at zero, S8 = -8 * w_DH * L_DH / (1 - w_DH), which
        at w_DH = 0.072 and L_DH = -13.7 is about +8.5. The folklore table gets
        S8 = 0 only because it silently normalises DH out of the pool. The
        folklore-comparable reading ships as `values_fielder_centred`.
    """
    last = last or feeds.inn.get("last_season")
    if first is None:
        first = max(LADDER_EARLIEST_SEASON, last - LADDER_WINDOW_SEASONS + 1)
    X, y, keys, inn_per_pa = _ladder_design(feeds, first, last, min_pa)
    n = len(y)
    exposure = X.mean(axis=0)
    raw, *_ = np.linalg.lstsq(X, y, rcond=None)
    # r2 / residuals describe the UNCENTRED least-squares fit, which is the fit;
    # the recentring below is a reporting convention, not a different model.
    resid = y - X @ raw
    r2 = 1.0 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()
    level = float(exposure @ raw)
    beta = _recentre(raw, exposure)

    rng = random.Random(seed)
    draws = []
    for _ in range(max(0, boot)):
        pick = [rng.randrange(n) for _ in range(n)]
        b, *_ = np.linalg.lstsq(X[pick], y[pick], rcond=None)
        draws.append(_recentre(b, X[pick].mean(axis=0)))
    draws = np.array(draws) if draws else None

    eras, span = {}, (last - first + 1) // 4
    for i in range(4):
        lo = first + i * span
        hi = last if i == 3 else lo + span - 1
        sel = [j for j, (_, yy) in enumerate(keys) if lo <= yy <= hi]
        if len(sel) > 200:
            b, *_ = np.linalg.lstsq(X[sel], y[sel], rcond=None)
            eras[f"{lo}-{hi}"] = {p: round(float(v), 2) for p, v in
                                  zip(LADDER_POSITIONS, _recentre(b, X[sel].mean(axis=0)))}

    values = {p: round(float(v), 2) for p, v in zip(LADDER_POSITIONS, beta)}
    s_field = sum(values[p] for p in _FIELDERS)
    # WHAT "exposure" IS, stated exactly, because the prose used to overclaim it.
    # `exposure` is X.mean(axis=0): the mean over fitted rows of each position's
    # share of THAT ROW's innings. Every qualified player-season therefore counts
    # once, whether it is 200 PA or 700. That is NOT "weighted by the innings the
    # league actually deploys" - a genuine innings weighting would weight each row
    # by its own inning total, and it is a different set of weights.
    #
    # MEASURED, so the difference is priced rather than asserted (2021-2026,
    # n=2023): the shipped per-row-share weighting puts the recentred ladder's
    # sum at -1.1e-16, machine zero, and the same ladder under a true
    # innings weighting sums to -0.0401 runs per 650 PA. The rungs' own bootstrap
    # CI95 half-widths run 0.315 (CF) to 0.430 (DH), so that gap is an eighth of
    # the narrowest of them.
    #
    # We do NOT re-weight, and the small gap is not the reason. The reason is
    # that this level is UNIDENTIFIED and nothing reads it: recentring shifts
    # every rung by one constant, so every position-to-position gap, which is the
    # entire content of a positional adjustment, is bit-identical under any
    # choice of weights. Re-weighting would move a number no consumer uses and
    # invalidate the pinned artifact for nothing.
    ident = {
        "convention": "exposure-weighted sum-to-zero",
        "zero_means": ("the average defensive position of a qualified player-season, "
                       "every fitted player-season counted once: the weights are the "
                       "column means of the per-row innings shares, not league innings "
                       "totals"),
        "sum_exposure_weighted": round(float(exposure @ beta), 6),
        "sum_equal_weight_9": round(sum(values.values()), 3),
        "sum_equal_weight_fielders": round(s_field, 3),
        "exposure_share": {p: round(float(exposure[i]), 4)
                           for i, p in enumerate(LADDER_POSITIONS)},
        "uncentred_level_runs": round(level, 4),
        "uncentred_level_equals": "mean(runs_position per 650 PA) over the fitted rows",
        "values_fielder_centred": {p: round(values[p] - s_field / len(_FIELDERS), 2)
                                   for p in LADDER_POSITIONS},
        "why_equal_weight_sums_are_not_zero": (
            "DH is %.1f%% of exposure, not a ninth, so equal-weighting the nine rungs "
            "over-counts the DH penalty; and with the exposure-weighted sum pinned at "
            "zero the eight fielding rungs must sum to -8 x w_DH x L_DH / (1 - w_DH). "
            "Only the exposure-weighted sum is a constraint - the other two are "
            "consequences of it." % (100 * float(exposure[LADDER_POSITIONS.index("DH")]))),
    }
    # Window sensitivity. Published, not chosen: era drift exceeds the sampling CIs,
    # so a reader needs to see how much of any rung is the window. The retired
    # 2012 window is kept in this list on purpose - it is what shipped until
    # 2026-08-07, so the difference between it and the current rung is the size
    # of the gated change, readable off the artifact without a git history.
    sens = {}
    for w_first in LADDER_SENSITIVITY_WINDOWS:
        if w_first == first:
            continue
        Xw, yw, _kw, _ipp = _ladder_design(feeds, w_first, last, min_pa)
        if len(yw) < 500:
            continue
        bw, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
        bw = _recentre(bw, Xw.mean(axis=0))
        vw = {p: round(float(v), 2) for p, v in zip(LADDER_POSITIONS, bw)}
        sens[f"{w_first}-{last}"] = {
            "n": len(yw), "values": vw,
            "sum_equal_weight_9": round(sum(vw.values()), 3),
            "sum_equal_weight_fielders": round(sum(vw[p] for p in _FIELDERS), 3)}
    return {
        "units": "runs per 650 PA, relative to the league average defensive position",
        "method": ("least squares of BRef runs_position/650PA on innings shares, no "
                   "intercept, recentred to exposure-weighted sum zero"),
        "dh_exposure_spec": "residual: max(0, PA x inn_per_pa - fielded innings)",
        "n_player_seasons": n, "seasons": [first, last], "min_pa": min_pa,
        "window_seasons": last - first + 1,
        "window_basis": ("rolling LADDER_WINDOW_SEASONS, gated forward-chained "
                         "2026-08-07 (data/positional_ladder_recency_eval.json)"),
        "inn_per_pa": round(inn_per_pa, 4),
        "r2": round(float(r2), 4), "resid_sd": round(float(resid.std()), 3),
        "values": values,
        "identification": ident,
        "ci95": {p: [round(float(np.percentile(draws[:, i], 2.5)), 2),
                     round(float(np.percentile(draws[:, i], 97.5)), 2)]
                 for i, p in enumerate(LADDER_POSITIONS)} if draws is not None else {},
        "era_splits": eras,
        "window_sensitivity": sens,
        "folklore_ladder": {"C": 12.5, "SS": 7.5, "CF": 2.5, "2B": 2.5, "3B": 2.5,
                            "RF": -7.5, "LF": -7.5, "1B": -12.5, "DH": -17.5},
    }


# ================================================ 2. the conversion matrix (D)
def _solve_D(pairs):
    """Weighted least squares on within-player-season rate DIFFERENCES.

    Each observation is one player, one season, two positions: the same glove, the
    same year, the same body. Everything about the player differences out, which is
    why this is the only clean way to identify D. A soft sum-to-zero row fixes the
    otherwise-arbitrary level.
    """
    if len(pairs) < len(OAA_POSITIONS):
        return np.zeros(len(OAA_POSITIONS))
    X, y, w = [], [], []
    for a, b, dy, wt in pairs:
        v = np.zeros(len(OAA_POSITIONS))
        v[IDX[b]] = 1.0
        v[IDX[a]] = -1.0
        X.append(v)
        y.append(dy)
        w.append(wt)
    X = np.array(X)
    y = np.array(y)
    sw = np.sqrt(np.array(w))
    Xa = np.vstack([X * sw[:, None], np.ones((1, len(OAA_POSITIONS))) * 50.0])
    ya = np.concatenate([y * sw, [0.0]])
    beta, *_ = np.linalg.lstsq(Xa, ya, rcond=None)
    return beta


def _pairs_from(obs, adj=None):
    """obs: {(mlbam,season): {POS: {...}}} -> [(a, b, rate_b - rate_a, weight)]"""
    out = []
    for k, d in obs.items():
        for a, b in itertools.combinations(sorted(d), 2):
            dy = d[b]["rate"] - d[a]["rate"]
            if adj is not None:
                dy -= adj(k, a, b)
            out.append((a, b, dy,
                        2.0 / (1.0 / d[a]["inn"] + 1.0 / d[b]["inn"])))
    return out


def fit_signal(obs, min_inn=MIN_RELIABILITY_INN):
    """Signal SD s(p) and reliability constant k(p), per position.

    A single-season fielding rate is signal plus noise. Year-over-year persistence
    at the SAME position, at a matched exposure, splits the two: the observed
    variance times the persistence is the signal variance, and the exposure that
    makes reliability one half is the shrinkage constant k.

    HONEST CAVEAT: year-over-year persistence also absorbs real year-to-year
    change in the player (aging, injury, a new positional assignment), so it is a
    LOWER bound on within-season reliability. The model therefore over-shrinks
    slightly, which is the conservative direction for a small-sample metric: it
    makes the model flag FEWER moves than the truth, not more.
    """
    out = {}
    for p in OAA_POSITIONS:
        xs = [v[p]["rate"] for v in obs.values()
              if p in v and v[p]["inn"] >= min_inn]
        px, py, hm = [], [], []
        for (m, y), d1 in obs.items():
            if p not in d1 or d1[p]["inn"] < min_inn:
                continue
            d2 = obs.get((m, y + 1))
            if not d2 or p not in d2 or d2[p]["inn"] < min_inn:
                continue
            px.append(d1[p]["rate"])
            py.append(d2[p]["rate"])
            hm.append(2.0 / (1.0 / d1[p]["inn"] + 1.0 / d2[p]["inn"]))
        if len(px) < 30 or len(xs) < 30:
            out[p] = {"n": len(xs), "obs_sd": None, "yoy_r": None,
                      "signal_sd": 4.0, "k_inn": 1200.0, "n_pairs": len(px)}
            continue
        r = float(np.corrcoef(px, py)[0, 1])
        r = min(max(r, 0.05), 0.95)
        sd = statistics.pstdev(xs)
        hmm = statistics.mean(hm)
        out[p] = {"n": len(xs), "n_pairs": len(px),
                  "obs_sd": round(sd, 3), "yoy_r": round(r, 4),
                  "hm_inn": round(hmm, 0),
                  "signal_sd": round(sd * math.sqrt(r), 3),
                  "k_inn": round(hmm * (1 - r) / r, 0)}
    return out


def _shrunk_z(obs_row, D, sig, season=None, aging=None, target_season=None):
    """Posterior mean and SE of the latent glove z from one player's reads.

    Each read contributes precision innings/k. The prior is the league, z ~ N(0,1).
    A read at 1B carries a third of the precision of the same innings at SS,
    because the first-base signal is weaker relative to its noise.
    """
    num = den = 0.0
    for p, rec in obs_row.items():
        s = sig[p]["signal_sd"]
        k = sig[p]["k_inn"]
        if s <= 0 or k <= 0:
            continue
        zp = (rec["rate"] - D[p]) / s
        prec = rec["inn"] / k
        num += prec * zp
        den += prec
    return num / (1.0 + den), 1.0 / math.sqrt(1.0 + den)


def fit_difficulty(obs, sig, boot=400, perm=300, seed=23, iters=3):
    """Position difficulty D, corrected for who takes the second position.

    Pass 1 is the raw within-player pair fit. It has one bias: the players who
    play both shortstop and first base are not a random sample of gloves, and the
    s(p) interaction means their mean difference is not the population's. Passes
    2 and 3 estimate each player's shrunk glove and subtract the s(p)*z part
    before re-fitting, which removes that selection.
    """
    multi = {k: d for k, d in obs.items() if len(d) >= 2}
    D = {p: 0.0 for p in OAA_POSITIONS}
    for _ in range(iters):
        def adj(k, a, b, _D=D):
            z, _ = _shrunk_z(multi[k], _D, sig)
            return (sig[b]["signal_sd"] - sig[a]["signal_sd"]) * z
        beta = _solve_D(_pairs_from(multi, adj=adj))
        D = {p: float(beta[IDX[p]]) for p in OAA_POSITIONS}
    raw = _solve_D(_pairs_from(multi))

    rng = random.Random(seed)
    keys = list(multi)
    draws = []
    for _ in range(boot):
        samp = {(i,): multi[keys[rng.randrange(len(keys))]] for i in range(len(keys))}
        draws.append(_solve_D(_pairs_from(samp)))
    draws = np.array(draws)

    # zero-information control + permutation null: shuffle the POSITION LABELS
    # inside each player-season. Same gloves, same innings, no positional content.
    nulls = []
    for _ in range(perm):
        samp = {}
        for i, k in enumerate(keys):
            d = multi[k]
            ps = list(d)
            vals = [d[p] for p in ps]
            rng.shuffle(ps)
            samp[(i,)] = dict(zip(ps, vals))
        nulls.append(_solve_D(_pairs_from(samp)))
    nulls = np.array(nulls)

    eras = {}
    for lo, hi in ((2016, 2018), (2019, 2020), (2021, 2023), (2024, 2026)):
        sub = {k: v for k, v in multi.items() if lo <= k[1] <= hi}
        pr = _pairs_from(sub)
        if len(pr) > 100:
            b = _solve_D(pr)
            eras[f"{lo}-{hi}"] = {"n_pairs": len(pr),
                                  "D": {p: round(float(b[IDX[p]]), 2)
                                        for p in OAA_POSITIONS}}
    return {
        "units": "fielding runs prevented per 1000 defensive innings",
        "interpretation": "higher D = easier to accumulate fielding runs there",
        "n_player_seasons_multi": len(multi),
        "n_pairs": len(_pairs_from(multi)),
        "min_pair_innings": MIN_PAIR_INN,
        "values": {p: round(D[p], 3) for p in OAA_POSITIONS},
        "values_uncorrected": {p: round(float(raw[IDX[p]]), 3) for p in OAA_POSITIONS},
        "ci95": {p: [round(float(np.percentile(draws[:, IDX[p]], 2.5)), 2),
                     round(float(np.percentile(draws[:, IDX[p]], 97.5)), 2)]
                 for p in OAA_POSITIONS},
        "boot_sd": {p: round(float(draws[:, IDX[p]].std()), 3) for p in OAA_POSITIONS},
        "perm_null95": {p: round(float(np.percentile(np.abs(nulls[:, IDX[p]]), 95)), 3)
                        for p in OAA_POSITIONS},
        "era_splits": eras,
    }


def interaction_check(obs, D, sig, seed=31, boot=600):
    """Is the naive 'bad fielders gain more from moving' slope real, or noise?

    Regressing (rate_b - rate_a) on rate_a puts rate_a on both sides, so
    measurement error alone forces a negative slope. Under the model the expected
    slope is

        rel_a * (s_b/s_a - 1)  -  (1 - rel_a)

    where rel_a is the reliability of the observed rate at a. If the observed slope
    lands on that prediction, the naive regression is measuring noise, and the real
    interaction is only the s_b/s_a term. This is the model's own falsification
    test, and it is reported whichever way it comes out.
    """
    rng = random.Random(seed)
    rows = []
    for a, b in (("SS", "2B"), ("SS", "3B"), ("CF", "LF"), ("CF", "RF"),
                 ("2B", "1B"), ("3B", "1B"), ("LF", "1B"), ("RF", "1B"),
                 ("2B", "3B"), ("LF", "RF")):
        xs, ys, rels = [], [], []
        for d in obs.values():
            if a in d and b in d and d[a]["inn"] >= 150 and d[b]["inn"] >= 150:
                xs.append(d[a]["rate"] - D[a])
                ys.append(d[b]["rate"] - d[a]["rate"])
                rels.append(d[a]["inn"] / (d[a]["inn"] + sig[a]["k_inn"]))
        if len(xs) < 25:
            continue
        x = np.array(xs)
        yv = np.array(ys)
        slope = float(np.polyfit(x, yv, 1)[0])
        bs = []
        for _ in range(boot):
            pick = [rng.randrange(len(x)) for _ in range(len(x))]
            bs.append(float(np.polyfit(x[pick], yv[pick], 1)[0]))
        rel = statistics.mean(rels)
        pred = rel * (sig[b]["signal_sd"] / sig[a]["signal_sd"] - 1.0) - (1.0 - rel)
        lo, hi = np.percentile(bs, 2.5), np.percentile(bs, 97.5)
        rows.append({"move": f"{a}->{b}", "n": len(x),
                     "observed_slope": round(slope, 3),
                     "ci95": [round(float(lo), 3), round(float(hi), 3)],
                     "mean_reliability_at_a": round(rel, 3),
                     "predicted_by_measurement_error": round(pred, 3),
                     "prediction_inside_ci": bool(lo <= pred <= hi)})
    inside = sum(1 for r in rows if r["prediction_inside_ci"])
    return {
        "claim_under_test": "the raw 'worse gloves gain more' slope is regression to the mean",
        "n_moves": len(rows), "n_predicted_inside_ci": inside,
        "verdict": ("measurement error explains the naive slope; the model uses the "
                    "SHRUNK glove and the s(p) ratio only"
                    if inside >= max(1, len(rows) // 2) else
                    "measurement error does NOT fully explain the naive slope; a "
                    "residual interaction may be real and is NOT modelled"),
        "rows": rows,
    }


def fit_feasibility(feeds: Feeds, ladder, first=FIRST_OAA_SEASON, last=None,
                    min_inn=400.0, min_next_inn=200.0, min_count=8, tol=0.5):
    """Which moves are actually AVAILABLE, measured from real position changes.

    The conversion matrix is estimated on players who played two positions in one
    season. That population is SELECTED: the left fielders who also played
    shortstop are the ones who could. Handing the raw matrix a random left fielder
    and asking what he would do at short is an extrapolation the data cannot
    support, and left unguarded the model says every corner outfielder in baseball
    should play shortstop, because the positional adjustment there is 15 runs
    richer and the measured difficulty gap is only 2.

    So the candidate set is restricted to moves that the league actually makes.
    A move a -> b is offered when

      * b == a, or b == DH (any hitter can DH), or
      * the player has real measured innings at b himself, or
      * b is at or below a on the positional-adjustment ladder (within `tol` runs)
        AND at least `min_count` regulars actually made that move in the window.

    The ladder condition is what blocks the up-spectrum extrapolation; the count
    condition is what blocks the moves nobody makes. Both are measured here, not
    asserted.
    """
    last = last or feeds.inn.get("last_season")
    counts: dict = defaultdict(lambda: defaultdict(int))
    base: dict = defaultdict(int)
    for y in range(first, last):
        for mid, byp in feeds.inn.get("seasons", {}).get(str(y), {}).items():
            if sum(v["inn"] for p, v in byp.items() if p != "P") < min_inn:
                continue
            a = feeds.primary_position(mid, y)
            b = feeds.primary_position(mid, y + 1)
            if a is None or b is None:
                continue
            if sum(v["inn"] for p, v in feeds.innings(mid, y + 1).items()
                   if p != "P") < min_next_inn:
                continue
            counts[a][b] += 1
            base[a] += 1
    allowed = {}
    for a in OAA_POSITIONS:
        ok = {a, "DH"}
        for b in OAA_POSITIONS:
            if b == a:
                continue
            if (ladder["values"][b] <= ladder["values"][a] + tol
                    and counts[a][b] >= min_count):
                ok.add(b)
        allowed[a] = sorted(ok)
    return {
        "method": "observed season-to-season primary-position changes among regulars",
        "seasons": [first, last], "min_innings": min_inn,
        "min_next_innings": min_next_inn,
        "min_count_to_offer": min_count, "ladder_tolerance_runs": tol,
        "n_by_from": dict(base),
        "counts": {a: dict(counts[a]) for a in sorted(counts)},
        "shares": {a: {b: round(c / base[a], 4) for b, c in counts[a].items()}
                   for a in sorted(counts) if base[a]},
        "allowed": allowed,
    }


def fit_aging(obs, D, sig, min_inn=200.0, seed=37, boot=500):
    """Does the glove decline with age? Paired same-position seasons, by age."""
    pts = []
    for (m, y), d1 in obs.items():
        d2 = obs.get((m, y + 1))
        if not d2:
            continue
        for p in d1:
            if p not in d2 or d1[p]["inn"] < min_inn or d2[p]["inn"] < min_inn:
                continue
            s = sig[p]["signal_sd"]
            if s <= 0:
                continue
            pts.append((m, y, ((d2[p]["rate"] - D[p]) - (d1[p]["rate"] - D[p])) / s,
                        min(d1[p]["inn"], d2[p]["inn"])))
    return pts


# ==================================================== 3. per-player estimates
def _bat_runs(hit, league, mid, target_season):
    """Offensive runs above average per 650 PA, exposure-weighted over 3 seasons.

    The corpus stores components, not wOBA, so the wOBA is reassembled with
    fa_projection's own inverter (read-only use of a shared module). This is a
    CONTEXT number: it sets whether a player is worth a first-base job at all. It
    is position-independent and therefore cancels out of every position COMPARISON.
    """
    try:
        import fa_projection as fp
    except Exception:                                   # noqa: BLE001
        return None, 0.0
    lg = league.get(target_season) or league.get(target_season - 1) or {}
    lg_woba = lg.get("woba") or 0.315
    num = den = 0.0
    pa0 = 0.0
    for lag, w in enumerate((5.0, 4.0, 3.0)):
        s = target_season - lag
        r = hit.get((mid, s))
        if not r or not r.get("pa"):
            continue
        lgs = league.get(s) or lg
        try:
            woba = fp._assemble_hitter(
                {**r, "babip": r.get("babip") or lgs.get("babip")},
                league, s)["woba_proj"]
        except Exception:                               # noqa: BLE001
            continue
        num += w * r["pa"] * woba
        den += w * r["pa"]
        if lag == 0:
            pa0 = r["pa"]
    if den <= 0:
        return None, pa0
    woba = (num + BAT_REGRESS_PA * lg_woba) / (den + BAT_REGRESS_PA)
    return (woba - lg_woba) / WOBA_SCALE * 650.0, pa0


def estimate_players(feeds: Feeds, ladder, diff, sig, feas, target_season,
                     age_slope=0.0, min_inn=200.0):
    """Value per 650 PA at every FEASIBLE position, for every qualified hitter."""
    D = diff["values"]
    D_sd = diff["boot_sd"]
    obs_all = feeds.rates()
    hit, league = feeds.corpus()
    inn650 = ladder["inn_per_pa"] * 650.0

    def baseline_gain(a, b):
        """What an AVERAGE glove (z = 0) gains moving a -> b. The league-wide part."""
        if a is None or b is None or a == b:
            return 0.0
        fa = 0.0 if a == "DH" else D[a] * inn650 / 1000.0
        fb = 0.0 if b == "DH" else D[b] * inn650 / 1000.0
        return (fb + ladder["values"][b]) - (fa + ladder["values"][a])

    # who is in the universe: fielded or batted in the target season
    universe = set()
    for mid, byp in feeds.inn.get("seasons", {}).get(str(target_season), {}).items():
        tot = sum(v["inn"] for p, v in byp.items() if p != "P")
        games = sum(v["g"] for v in byp.values())
        if tot >= min_inn or games >= 20:
            universe.add(int(mid))

    rows = []
    for mid in sorted(universe):
        byp = feeds.innings(mid, target_season)
        if "P" in byp and len(byp) == 1:
            continue
        cur = feeds.primary_position(mid, target_season)
        is_c = cur == "C"

        # --- glove evidence: up to three seasons, recency weighted, aged forward
        num = den = 0.0
        evidence = []
        for lag, w in enumerate(RECENCY):
            s = target_season - lag
            row = obs_all.get((mid, s))
            if not row:
                continue
            for p, rec in row.items():
                sd = sig[p]["signal_sd"]
                k = sig[p]["k_inn"]
                if sd <= 0 or k <= 0 or rec["inn"] < 30:
                    continue
                zp = (rec["rate"] - D[p]) / sd + age_slope * lag
                prec = w * rec["inn"] / k
                num += prec * zp
                den += prec
                evidence.append({"season": s, "pos": p, "inn": round(rec["inn"], 1),
                                 "oaa": rec["oaa"], "frp": rec["frp"],
                                 "rate": round(rec["rate"], 2), "z_read": round(zp, 2)})
        z = num / (1.0 + den)
        z_se = 1.0 / math.sqrt(1.0 + den)

        # --- bat context (position-independent; does not affect the ranking)
        bat, pa_tot = _bat_runs(hit, league, mid, target_season)
        age = None
        for lag in range(3):
            r = hit.get((mid, target_season - lag))
            if r and r.get("age") is not None:
                age = r["age"] + lag
                break

        # --- feasible candidate set (see fit_feasibility)
        measured = {e["pos"] for e in evidence if e["inn"] >= 100}
        cand = set(feas["allowed"].get(cur, ["DH"])) | measured | {"DH"}
        if cur in OAA_POSITIONS:
            cand.add(cur)

        # --- value at each candidate position
        vals = {}
        for p in sorted(cand):
            if p == "DH":
                vals["DH"] = {"field": 0.0, "ladder": ladder["values"]["DH"],
                              "def_total": round(ladder["values"]["DH"], 2),
                              "feasible": True}
                continue
            if p not in OAA_POSITIONS:
                continue
            field = (D[p] + sig[p]["signal_sd"] * z) * inn650 / 1000.0
            vals[p] = {"field": round(field, 2), "ladder": ladder["values"][p],
                       "def_total": round(field + ladder["values"][p], 2),
                       "feasible": True}

        best = max(vals, key=lambda p: vals[p]["def_total"])
        cur_key = cur if cur in vals else None
        gain = (vals[best]["def_total"] - vals[cur_key]["def_total"]) if cur_key else None

        def _se(a, b):
            """SE of the gain from a to b: glove uncertainty transported through the
            s(p) difference, plus the bootstrap SE of both D rungs and both ladder
            rungs. It does NOT include idiosyncratic conversion risk (see caveats)."""
            sb = sig[b]["signal_sd"] if b != "DH" else 0.0
            sa = sig[a]["signal_sd"] if a != "DH" else 0.0
            db = D_sd[b] if b != "DH" else 0.0
            da = D_sd[a] if a != "DH" else 0.0
            lb = (ladder["ci95"][b][1] - ladder["ci95"][b][0]) / 3.92
            la = (ladder["ci95"][a][1] - ladder["ci95"][a][0]) / 3.92
            return math.sqrt((abs(sb - sa) * z_se * inn650 / 1000.0) ** 2
                             + ((da ** 2 + db ** 2) * (inn650 / 1000.0) ** 2)
                             + la ** 2 + lb ** 2)

        gain_se = _se(cur_key, best) if (cur_key and best != cur_key) else None

        # DEMOTION vs PROMOTION are different products and must be scored apart.
        # A promotion needs the job to be open and the player to be able to handle
        # it; a demotion is a decision the club can make unilaterally, and it is the
        # one the owner's question is about ("horrible outfielder -> 1B/DH").
        down_pos = down_gain = down_se = None
        up_pos = up_gain = None
        if cur_key:
            cur_lad = ladder["values"][cur_key]
            downs = {p: v for p, v in vals.items()
                     if ladder["values"][p] < cur_lad - 0.5}
            ups = {p: v for p, v in vals.items()
                   if ladder["values"][p] > cur_lad + 0.5}
            if downs:
                down_pos = max(downs, key=lambda p: downs[p]["def_total"])
                down_gain = downs[down_pos]["def_total"] - vals[cur_key]["def_total"]
                down_se = _se(cur_key, down_pos)
            if ups:
                up_pos = max(ups, key=lambda p: ups[p]["def_total"])
                up_gain = ups[up_pos]["def_total"] - vals[cur_key]["def_total"]

        flagged = bool(cur_key and best != cur_key and gain is not None
                       and gain >= FLAG_MIN_GAIN and gain_se
                       and gain >= FLAG_SIGMA * gain_se and not is_c)
        flagged_down = bool(down_gain is not None and down_gain >= FLAG_MIN_GAIN
                            and down_se and down_gain >= FLAG_SIGMA * down_se
                            and not is_c)
        rows.append({
            "mlbam": mid,
            "name": feeds.names.get(str(mid), ""),
            "season": target_season,
            "age": age,
            "current_pos": cur,
            "innings": {p: round(v["inn"], 1) for p, v in byp.items() if p != "P"},
            "pa": round(pa_tot, 0) if pa_tot else None,
            "glove_z": round(z, 3),
            "glove_z_se": round(z_se, 3),
            "glove_runs_per_650_at_current": (
                vals[cur_key]["field"] if cur_key else None),
            "bat_runs_per_650": round(bat, 2) if bat is not None else None,
            "by_position": vals,
            "best_pos": None if is_c else best,
            "gain_runs_per_650": None if is_c or gain is None else round(gain, 2),
            "gain_se": None if gain_se is None else round(gain_se, 2),
            "demotion_pos": None if is_c else down_pos,
            "demotion_gain": None if is_c or down_gain is None else round(down_gain, 2),
            "demotion_se": None if down_se is None else round(down_se, 2),
            # How much of the demotion gain is THIS PLAYER rather than a constant
            # every player at his position would get. The league-wide part rests on
            # the difficulty matrix; the player part rests on his own glove.
            "demotion_gain_player_part": (
                None if (is_c or down_gain is None) else round(
                    down_gain - baseline_gain(cur_key, down_pos), 2)),
            "demotion_gain_league_part": (
                None if (is_c or down_gain is None) else round(
                    baseline_gain(cur_key, down_pos), 2)),
            "promotion_pos": None if is_c else up_pos,
            "promotion_gain": None if is_c or up_gain is None else round(up_gain, 2),
            "flagged_misplaced": flagged,
            "flagged_demotion": flagged_down,
            "c_out_of_scope": is_c,
            "evidence": evidence[:8],
        })
    return rows


# ======================================================= 4. historical backtest
def conversion_accuracy(feeds: Feeds, sig, first=2017, last=None,
                        min_inn=200.0, prior_inn_cap=50.0, seed=61, boot=1000):
    """THE PRIMARY VALIDATION. Does the conversion actually convert?

    The model's claim is not "this player will be moved". Clubs decide that, for
    reasons that include contracts and roster geometry. The model's claim is: IF a
    player moves from a to b, here is the fielding rate he will post at b.

    So: find every player who was a regular at a in season t and a regular at a
    DIFFERENT position b in season t+1, having barely played b before. Predict his
    b rate using only pre-move information and a difficulty matrix refit on
    seasons <= t. Score against four references on the identical rows:

      carry_over   assume the rate transfers unchanged (the naive answer)
      d_shift      shift by the difficulty gap only, no glove rescaling
      league_avg   assume he is average at the new position
      permuted     ZERO-INFORMATION CONTROL: the same pipeline with the glove
                   reads shuffled between players

    Reported with MAE, RMSE, correlation, a paired bootstrap, a permutation null,
    and per-season splits.
    """
    last = last or (feeds.inn.get("last_season") - 1)
    obs_all = feeds.rates()
    rng = random.Random(seed)
    rows = []
    for t in range(first, last + 1):
        train = {k: v for k, v in obs_all.items() if k[1] <= t}
        multi = {k: d for k, d in train.items() if len(d) >= 2}
        if len(multi) < 100:
            continue
        beta = _solve_D(_pairs_from(multi))
        Dt = {p: float(beta[IDX[p]]) for p in OAA_POSITIONS}
        for (mid, s), row in obs_all.items():
            if s != t:
                continue
            nxt = obs_all.get((mid, t + 1))
            if not nxt:
                continue
            src = {p: v for p, v in row.items() if v["inn"] >= min_inn}
            if not src:
                continue
            for b, nv in nxt.items():
                if nv["inn"] < min_inn or b in src:
                    continue
                # he must not already have real experience at b
                prior = sum(obs_all.get((mid, y), {}).get(b, {}).get("inn", 0.0)
                            for y in range(t - 2, t + 1))
                if prior > prior_inn_cap:
                    continue
                a = max(src, key=lambda p: src[p]["inn"])
                z, _ = _shrunk_z(src, Dt, sig)
                rows.append({
                    "mlbam": mid, "season": t, "from": a, "to": b,
                    "actual": nv["rate"], "inn_to": nv["inn"], "z": z,
                    "src": src, "Dt": Dt,
                    "model": Dt[b] + sig[b]["signal_sd"] * z,
                    "carry_over": src[a]["rate"],
                    "d_shift": src[a]["rate"] - Dt[a] + Dt[b],
                    "league_avg": Dt[b]})
    if len(rows) < 30:
        return {"error": "too few clean conversions", "n": len(rows)}

    # zero-information control: shuffle the glove reads between movers, per season
    for t in sorted({r["season"] for r in rows}):
        sub = [r for r in rows if r["season"] == t]
        zs = [r["z"] for r in sub]
        rng.shuffle(zs)
        for r, zz in zip(sub, zs):
            r["permuted"] = r["Dt"][r["to"]] + sig[r["to"]]["signal_sd"] * zz

    arms = ("model", "carry_over", "d_shift", "league_avg", "permuted")

    def mae(rs, a):
        return statistics.mean(abs(r[a] - r["actual"]) for r in rs)

    def rmse(rs, a):
        return math.sqrt(statistics.mean((r[a] - r["actual"]) ** 2 for r in rs))

    out = {"n_conversions": len(rows),
           "min_innings_each_side": min_inn,
           "prior_innings_cap_at_destination": prior_inn_cap,
           "weighted_note": "unweighted; every conversion counts once",
           "mae": {a: round(mae(rows, a), 3) for a in arms},
           "rmse": {a: round(rmse(rows, a), 3) for a in arms},
           "corr_with_actual": {
               a: round(float(np.corrcoef([r[a] for r in rows],
                                          [r["actual"] for r in rows])[0, 1]), 4)
               for a in arms}}

    n = len(rows)
    diffs = {a: [] for a in arms if a != "model"}
    for _ in range(boot):
        pick = [rows[rng.randrange(n)] for _ in range(n)]
        m = mae(pick, "model")
        for a in diffs:
            diffs[a].append(mae(pick, a) - m)
    out["mae_advantage_over"] = {
        a: {"mean": round(float(np.mean(v)), 4),
            "ci95": [round(float(np.percentile(v, 2.5)), 4),
                     round(float(np.percentile(v, 97.5)), 4)],
            "beats": bool(np.percentile(v, 2.5) > 0)}
        for a, v in diffs.items()}

    # permutation null on the model's own MAE advantage over carry_over
    nulls = []
    for _ in range(400):
        zs = [r["z"] for r in rows]
        rng.shuffle(zs)
        pred = [r["Dt"][r["to"]] + sig[r["to"]]["signal_sd"] * zz
                for r, zz in zip(rows, zs)]
        m = statistics.mean(abs(p - r["actual"]) for p, r in zip(pred, rows))
        nulls.append(mae(rows, "carry_over") - m)
    out["perm_null95_mae_advantage"] = round(float(np.percentile(nulls, 95)), 4)

    out["by_season"] = {}
    for t in sorted({r["season"] for r in rows}):
        sub = [r for r in rows if r["season"] == t]
        if len(sub) < 10:
            continue
        out["by_season"][t] = {"n": len(sub),
                               **{f"mae_{a}": round(mae(sub, a), 3) for a in arms}}
    out["n_time_splits"] = len(out["by_season"])
    adv = [v["mae_carry_over"] - v["mae_model"] for v in out["by_season"].values()]
    if adv:
        out["season_advantage_mean"] = round(float(np.mean(adv)), 4)
        out["season_advantage_sd"] = round(float(np.std(adv)), 4)
        out["season_advantage_positive_in"] = f"{sum(1 for a in adv if a > 0)}/{len(adv)}"
    out["by_move"] = {}
    for (a, b) in sorted({(r["from"], r["to"]) for r in rows}):
        sub = [r for r in rows if r["from"] == a and r["to"] == b]
        if len(sub) < 10:
            continue
        out["by_move"][f"{a}->{b}"] = {
            "n": len(sub), "mae_model": round(mae(sub, "model"), 3),
            "mae_carry_over": round(mae(sub, "carry_over"), 3),
            "mean_actual": round(statistics.mean(r["actual"] for r in sub), 2)}

    # DIRECT TEST OF THE DIFFICULTY GAP. The matrix says a mover's rate should
    # shift by D(to) - D(from). Across-season movers are an INDEPENDENT sample
    # from the within-season pairs D was fit on, so this is the one place the gap
    # can be checked out of sample. Reported per destination, with its own CI.
    out["difficulty_gap_out_of_sample"] = {}
    for b in sorted({r["to"] for r in rows}):
        sub = [r for r in rows if r["to"] == b]
        if len(sub) < 8:
            continue
        xs = [r["actual"] - r["carry_over"] for r in sub]
        bs = [statistics.mean([xs[rng.randrange(len(xs))] for _ in xs])
              for _ in range(2000)]
        out["difficulty_gap_out_of_sample"][f"->{b}"] = {
            "n": len(sub),
            "observed_rate_change": round(statistics.mean(xs), 2),
            "ci95": [round(float(np.percentile(bs, 2.5)), 2),
                     round(float(np.percentile(bs, 97.5)), 2)],
            "model_predicted_gap": round(
                statistics.mean(r["Dt"][r["to"]] - r["Dt"][r["from"]] for r in sub), 2)}
        d = out["difficulty_gap_out_of_sample"][f"->{b}"]
        d["prediction_inside_ci"] = bool(d["ci95"][0] <= d["model_predicted_gap"]
                                         <= d["ci95"][1])
    return out


def _auc(scores, labels):
    """Rank AUC with tie handling. Returns None if a class is empty."""
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    rp = sum(r for r, l in zip(ranks, labels) if l)
    n1, n0 = len(pos), len(neg)
    return (rp - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def backtest(feeds: Feeds, ladder, sig, feas, first=2017, last=None,
             min_inn=400.0, min_next_inn=200.0, seed=53, boot=1000):
    """Would the model have flagged the players the league actually moved?

    DESIGN. For every season t the difficulty matrix is refit on seasons <= t
    ONLY, every regular is scored with data available at the end of t, and the
    label comes from t+1: did his primary position move DOWN the positional
    ladder (a real demotion, more than half a run of positional adjustment)?

    That label is the one the model is actually making a claim about. "Did he
    change position at all" is a much noisier target, because most changes are
    lateral (left field to right field) and carry no value content, and some are
    promotions the model is deliberately forbidden from predicting.

    FOUR ARMS, all scored on the identical rows:
      model        the shrunk-glove gain to the best feasible position
      control      ZERO-INFORMATION: the same machinery with the glove reads
                   shuffled between players inside the season
      ladder_only  no glove at all, only the player's current position
      raw_oaa      the unshrunk OAA rate at the current position, sign flipped
                   (the naive answer: "he has bad OAA, move him")

    Metric is rank AUC, reported with a paired bootstrap over players, per-season
    values for the time-split requirement, and a permutation null.
    """
    last = last or (feeds.inn.get("last_season") - 1)
    obs_all = feeds.rates()
    rng = random.Random(seed)
    inn650 = ladder["inn_per_pa"] * 650.0
    lad = ladder["values"]

    def score_row(row, Dt, cur):
        """-> (best-of-all gain, best-DOWN gain, best-UP gain, down pick, z)"""
        z, _ = _shrunk_z(row, Dt, sig)
        cand = set(feas["allowed"].get(cur, ["DH"])) | {
            p for p, v in row.items() if v["inn"] >= 100} | {"DH", cur}
        vals = {}
        for p in cand:
            if p == "DH":
                vals["DH"] = lad["DH"]
            elif p in OAA_POSITIONS:
                vals[p] = (Dt[p] + sig[p]["signal_sd"] * z) * inn650 / 1000.0 + lad[p]
        here = vals.get(cur)
        if here is None:
            here = max(vals.values())
        best = max(vals, key=lambda p: vals[p])
        downs = {p: v for p, v in vals.items() if lad[p] < lad[cur] - 0.5}
        ups = {p: v for p, v in vals.items() if lad[p] > lad[cur] + 0.5}
        dpick = max(downs, key=lambda p: downs[p]) if downs else None
        return (vals[best] - here,
                (downs[dpick] - here) if dpick else -99.0,
                (max(ups.values()) - here) if ups else -99.0,
                dpick, z)

    records = []
    for t in range(first, last + 1):
        train = {k: v for k, v in obs_all.items() if k[1] <= t}
        multi = {k: d for k, d in train.items() if len(d) >= 2}
        if len(multi) < 100:
            continue
        beta = _solve_D(_pairs_from(multi))
        Dt = {p: float(beta[IDX[p]]) for p in OAA_POSITIONS}

        cand_rows = []
        for (mid, s), row in obs_all.items():
            if s != t:
                continue
            cur = feeds.primary_position(mid, t)
            if cur not in OAA_POSITIONS:
                continue
            if sum(v["inn"] for v in row.values()) < min_inn:
                continue
            nxt = feeds.primary_position(mid, t + 1)
            if nxt is None:
                continue
            if sum(v["inn"] for p, v in feeds.innings(mid, t + 1).items()
                   if p != "P") < min_next_inn:
                continue
            cand_rows.append((mid, cur, nxt, row))
        if len(cand_rows) < 30:
            continue

        shuffled = [c[3] for c in cand_rows]
        rng.shuffle(shuffled)
        for (mid, cur, nxt, row), ctl in zip(cand_rows, shuffled):
            g, gd, gu, dpick, z = score_row(row, Dt, cur)
            gc, gdc, guc, _, _ = score_row(ctl, Dt, cur)
            raw = -(row[cur]["rate"] if cur in row else 0.0)
            records.append({
                "mlbam": mid, "season": t, "from": cur, "to": nxt,
                "moved_down": bool(lad[nxt] < lad[cur] - 0.5),
                "moved_up": bool(lad[nxt] > lad[cur] + 0.5),
                "moved": nxt != cur,
                "model": gd, "control": gdc, "ladder_only": -lad[cur],
                "raw_oaa": raw,
                "model_up": gu, "control_up": guc,
                "best_of_all": g, "best": dpick, "z": z})

    if not records:
        return {"error": "no scoreable rows"}

    labels = [r["moved_down"] for r in records]
    arms = ("model", "control", "ladder_only", "raw_oaa")
    out = {"n_scored": len(records),
           "n_moved_down": sum(labels),
           "n_moved_any": sum(r["moved"] for r in records),
           "base_rate_moved_down": round(sum(labels) / len(records), 4),
           "auc": {a: (round(_auc([r[a] for r in records], labels), 4)
                       if _auc([r[a] for r in records], labels) is not None else None)
                   for a in arms}}

    # paired bootstrap over players, refitting nothing (D is already per-season)
    diffs = {a: [] for a in arms if a != "model"}
    n = len(records)
    for _ in range(boot):
        pick = [records[rng.randrange(n)] for _ in range(n)]
        lab = [r["moved_down"] for r in pick]
        am = _auc([r["model"] for r in pick], lab)
        if am is None:
            continue
        for a in diffs:
            ax = _auc([r[a] for r in pick], lab)
            if ax is not None:
                diffs[a].append(am - ax)
    out["model_minus"] = {
        a: {"mean": round(float(np.mean(v)), 4),
            "ci95": [round(float(np.percentile(v, 2.5)), 4),
                     round(float(np.percentile(v, 97.5)), 4)]}
        for a, v in diffs.items() if v}

    # permutation null on the headline AUC: shuffle the labels
    nulls = []
    for _ in range(500):
        lab = labels[:]
        rng.shuffle(lab)
        v = _auc([r["model"] for r in records], lab)
        if v is not None:
            nulls.append(abs(v - 0.5))
    out["perm_null95_auc_minus_half"] = round(float(np.percentile(nulls, 95)), 4)

    # per-season time splits
    out["by_season"] = {}
    for t in sorted({r["season"] for r in records}):
        sub = [r for r in records if r["season"] == t]
        lab = [r["moved_down"] for r in sub]
        out["by_season"][t] = {
            "n": len(sub), "n_moved_down": sum(lab),
            "auc_model": (round(_auc([r["model"] for r in sub], lab), 4)
                          if _auc([r["model"] for r in sub], lab) is not None else None),
            "auc_control": (round(_auc([r["control"] for r in sub], lab), 4)
                            if _auc([r["control"] for r in sub], lab) is not None else None)}
    aucs = [v["auc_model"] for v in out["by_season"].values() if v["auc_model"]]
    if aucs:
        out["season_auc_mean"] = round(float(np.mean(aucs)), 4)
        out["season_auc_sd"] = round(float(np.std(aucs)), 4)
        out["n_time_splits"] = len(aucs)

    # precision / recall of the shipped flag rule, at the shipped threshold
    fl = [r for r in records if r["model"] >= FLAG_MIN_GAIN]
    tp = sum(1 for r in fl if r["moved_down"])
    out["flag_rule"] = {
        "threshold_runs": FLAG_MIN_GAIN,
        "n_flagged": len(fl),
        "precision": round(tp / len(fl), 4) if fl else None,
        "recall": round(tp / sum(labels), 4) if sum(labels) else None,
        "lift_over_base_rate": (round((tp / len(fl)) / (sum(labels) / len(records)), 3)
                                if fl and sum(labels) else None)}
    ctl_fl = [r for r in records if r["control"] >= FLAG_MIN_GAIN]
    ctl_tp = sum(1 for r in ctl_fl if r["moved_down"])
    out["flag_rule_control"] = {
        "n_flagged": len(ctl_fl),
        "precision": round(ctl_tp / len(ctl_fl), 4) if ctl_fl else None,
        "recall": round(ctl_tp / sum(labels), 4) if sum(labels) else None}

    # among players who DID move down, is the realized position the model's pick?
    dn = [r for r in records if r["moved_down"]]
    out["destination_top1"] = {
        "n": len(dn),
        "model": round(statistics.mean(1.0 if r["best"] == r["to"] else 0.0
                                       for r in dn), 4) if dn else None,
        "control": None}
    out["label_definition"] = ("moved_down = the StatsAPI most-innings position in "
                               "t+1 sits lower on the fitted positional ladder than "
                               "the one in t, by more than 0.5 runs per 650 PA. The "
                               "scored quantity is the DEMOTION gain, not the "
                               "best-of-all gain: a promotion needs the job to be "
                               "open, a demotion does not.")
    # the promotion side, scored on its own label
    up_lab = [r["moved_up"] for r in records]
    if any(up_lab):
        out["promotion_side"] = {
            "n_moved_up": sum(up_lab),
            "auc_model_up": round(_auc([r["model_up"] for r in records], up_lab), 4),
            "auc_control_up": round(_auc([r["control_up"] for r in records], up_lab), 4),
        }
    return out


# ================================================================== assembly
def fit_all(feeds: Feeds, target_season=None, verbose=True):
    target_season = target_season or feeds.inn.get("last_season")
    if verbose:
        print("fitting positional ladder ...")
    ladder = fit_ladder(feeds)
    obs_all = feeds.rates()
    obs = {k: {p: v for p, v in d.items() if v["inn"] >= MIN_PAIR_INN}
           for k, d in obs_all.items()}
    obs = {k: d for k, d in obs.items() if d}
    if verbose:
        print("fitting reliability / signal ...")
    sig = fit_signal(obs)
    if verbose:
        print("fitting position difficulty ...")
    diff = fit_difficulty(obs, sig)
    D = diff["values"]
    if verbose:
        print("measuring which moves the league actually makes ...")
    feas = fit_feasibility(feeds, ladder)
    if verbose:
        print("running the interaction falsification test ...")
    inter = interaction_check(obs, D, sig)

    # aging: slope of the standardized glove change per year of age
    pts = fit_aging(obs, D, sig)
    hit, _ = feeds.corpus()
    ages, dz, ws = [], [], []
    for m, y, d, w in pts:
        r = hit.get((m, y))
        if r and r.get("age"):
            ages.append(float(r["age"]))
            dz.append(d)
            ws.append(w)
    aging = {"n": len(ages)}
    if len(ages) > 100:
        a = np.array(ages)
        dd = np.array(dz)
        w = np.array(ws)
        mean_dz = float((w * dd).sum() / w.sum())
        A = np.vstack([np.ones_like(a), a - a.mean()]).T * np.sqrt(w)[:, None]
        beta, *_ = np.linalg.lstsq(A, dd * np.sqrt(w), rcond=None)
        rng = random.Random(71)
        bs = []
        for _ in range(500):
            pick = [rng.randrange(len(a)) for _ in range(len(a))]
            b2, *_ = np.linalg.lstsq(A[pick], (dd * np.sqrt(w))[pick], rcond=None)
            bs.append(b2)
        bs = np.array(bs)
        aging.update({
            "mean_delta_z_per_year": round(mean_dz, 4),
            "mean_delta_ci95": [round(float(np.percentile(bs[:, 0], 2.5)), 4),
                                round(float(np.percentile(bs[:, 0], 97.5)), 4)],
            "age_interaction_per_year": round(float(beta[1]), 5),
            "age_interaction_ci95": [round(float(np.percentile(bs[:, 1], 2.5)), 5),
                                     round(float(np.percentile(bs[:, 1], 97.5)), 5)],
            "mean_age": round(float(np.mean(a)), 1),
            "applied": abs(mean_dz) > 0.01,
        })
    # A read from `lag` seasons ago is carried FORWARD to the target season, so it
    # moves by the mean per-year change (which is negative: gloves decline).
    age_slope = aging.get("mean_delta_z_per_year", 0.0) if aging.get("applied") else 0.0

    # conversion matrix in served units
    inn650 = ladder["inn_per_pa"] * 650.0
    matrix = {}
    for a in OAA_POSITIONS:
        matrix[a] = {}
        for b in OAA_POSITIONS:
            matrix[a][b] = {
                "d_field_per_1000inn": round(D[b] - D[a], 2),
                "glove_scale": round(sig[b]["signal_sd"] / sig[a]["signal_sd"], 3),
                "d_ladder_per_650pa": round(ladder["values"][b] - ladder["values"][a], 2),
                "net_for_average_glove_per_650pa": round(
                    (D[b] - D[a]) * inn650 / 1000.0
                    + ladder["values"][b] - ladder["values"][a], 2)}
        matrix[a]["DH"] = {
            "d_field_per_1000inn": None, "glove_scale": 0.0,
            "d_ladder_per_650pa": round(ladder["values"]["DH"] - ladder["values"][a], 2),
            "net_for_average_glove_per_650pa": round(
                -(D[a] + 0.0) * inn650 / 1000.0
                + ladder["values"]["DH"] - ladder["values"][a], 2)}
    return {"ladder": ladder, "signal": sig, "difficulty": diff,
            "feasibility": feas, "conversion_matrix": matrix,
            "interaction_check": inter,
            "aging": aging, "age_slope": age_slope,
            "target_season": target_season, "inn_per_650pa": round(inn650, 1)}


def build(target_season=None, with_backtest=True) -> dict:
    feeds = Feeds()
    f = fit_all(feeds)
    ts = target_season or f["target_season"]
    print("estimating players ...")
    rows = estimate_players(feeds, f["ladder"], f["difficulty"], f["signal"],
                            f["feasibility"], ts, age_slope=f["age_slope"])
    print("backtesting against real position changes ...")
    val = (backtest(feeds, f["ladder"], f["signal"], f["feasibility"])
           if with_backtest else {})
    conv = conversion_accuracy(feeds, f["signal"]) if with_backtest else {}

    # Headline lists cover REGULARS only. A backup with 120 innings has a glove
    # estimate that is almost all prior, so his "gain" is a statement about the
    # ladder, not about him.
    def qualified(r):
        tot = sum(r["innings"].values())
        return (not r["c_out_of_scope"]) and (
            (r["pa"] or 0) >= HEADLINE_MIN_PA or tot >= HEADLINE_MIN_INN)

    reg = [r for r in rows if qualified(r)]
    for r in rows:
        r["qualified"] = qualified(r)
    flagged = [r for r in reg if r["flagged_misplaced"]]
    flagged.sort(key=lambda r: -(r["gain_runs_per_650"] or 0))
    demotions = [r for r in reg if r["flagged_demotion"]]
    demotions.sort(key=lambda r: -(r["demotion_gain"] or 0))
    promotions = [r for r in reg if r["flagged_misplaced"]
                  and r["promotion_pos"] and r["best_pos"] == r["promotion_pos"]]
    promotions.sort(key=lambda r: -(r["promotion_gain"] or 0))

    def slim(r):
        return {k: r[k] for k in
                ("mlbam", "name", "age", "current_pos", "pa", "best_pos",
                 "gain_runs_per_650", "gain_se", "demotion_pos", "demotion_gain",
                 "demotion_se", "demotion_gain_player_part",
                 "demotion_gain_league_part", "promotion_pos", "promotion_gain", "glove_z",
                 "glove_z_se", "glove_runs_per_650_at_current", "bat_runs_per_650")}
    return {
        "model": "positional_fit_v1",
        "generated_at": _dt.date.today().isoformat(),
        "target_season": ts,
        "value_identity": "value per 650 PA = bat + fielding(position) + positional adjustment",
        "sources": ["data/savant_oaa.json", "data/fielding_innings.json",
                    "data/mlb_def_history.json", ".cache/fa_corpus.pkl"],
        "out_of_scope": ["C (no Savant OAA)", "P"],
        "caveats": [
            "The difficulty matrix D is identified ONLY on players who played two "
            "positions in the same season. That population is selected, and the "
            "correction applied here (subtracting the s(p)*glove part before "
            "refitting) is a model-based correction, not a randomisation.",
            "The single largest league-wide claim the model makes is that a corner "
            "outfielder gains runs by moving to first base. Roughly 2 runs per 650 "
            "PA of every corner-outfield demotion is this constant, and the "
            "out-of-sample check on across-season movers into 1B is consistent in "
            "sign but far too thin to confirm it. Read the player-specific part of "
            "the gain, not the total, when the total is close to the threshold.",
            "Catcher has no Savant OAA in any season and is never scored.",
            "Year-over-year persistence is a LOWER bound on within-season "
            "reliability, so the glove is over-shrunk and the model under-flags.",
            "The gain SE covers glove, difficulty and ladder uncertainty. It does "
            "NOT cover idiosyncratic conversion risk (a specific player's hands, "
            "arm, or instincts failing to transfer), which is unmeasurable here.",
            "Playing time is priced per 650 PA. A demotion that also costs the "
            "player playing time, or that is blocked by an incumbent, is a roster "
            "question this model does not answer.",
        ],
        "flag_rule": {"min_gain_runs_per_650": FLAG_MIN_GAIN, "min_sigma": FLAG_SIGMA,
                      "headline_min_pa": HEADLINE_MIN_PA,
                      "headline_min_innings": HEADLINE_MIN_INN},
        "fit": {k: v for k, v in f.items() if k != "target_season"},
        "validation": val,
        "conversion_accuracy": conv,
        "n_players": len(rows),
        "n_qualified": len(reg),
        "n_flagged": len(flagged),
        "n_flagged_demotion": len(demotions),
        "top_misplaced": [slim(r) for r in flagged[:40]],
        "top_demotions": [slim(r) for r in demotions[:40]],
        "top_promotions": [slim(r) for r in promotions[:40]],
        "players": rows,
    }


# ===================================================================== report
def _report(payload):
    f = payload["fit"]
    L = f["ladder"]
    print("\n" + "=" * 74)
    print("POSITIONAL ADJUSTMENT (runs per 650 PA), recovered from BRef")
    print("=" * 74)
    print(f"n={L['n_player_seasons']}  seasons {L['seasons'][0]}-{L['seasons'][1]}  "
          f"R2={L['r2']}  resid sd={L['resid_sd']}  innings/PA={L['inn_per_pa']}")
    print(f"{'pos':<5}{'fitted':>9}{'95% CI':>18}{'folklore':>10}{'error':>9}")
    for p in LADDER_POSITIONS:
        v = L["values"][p]
        c = L["ci95"][p]
        s = L["folklore_ladder"][p]
        print(f"{p:<5}{v:>9.2f}{'[%6.2f,%6.2f]' % (c[0], c[1]):>18}{s:>10.1f}{v - s:>+9.2f}")
    print("\nera splits:")
    for k, v in L["era_splits"].items():
        print("  " + k + "  " + " ".join(f"{p} {v[p]:+.2f}" for p in LADDER_POSITIONS))

    S = f["signal"]
    print("\n" + "=" * 74)
    print("GLOVE SIGNAL AND RELIABILITY, per position")
    print("=" * 74)
    print(f"{'pos':<5}{'n':>6}{'obs sd':>9}{'YoY r':>8}{'signal sd':>11}{'k (inn)':>10}"
          f"{'rel@1300':>10}")
    for p in OAA_POSITIONS:
        s = S[p]
        rel = 1300.0 / (1300.0 + s["k_inn"])
        print(f"{p:<5}{s['n']:>6}{s['obs_sd']:>9.2f}{s['yoy_r']:>8.3f}"
              f"{s['signal_sd']:>11.2f}{s['k_inn']:>10.0f}{rel:>10.2f}")

    Dd = f["difficulty"]
    print("\n" + "=" * 74)
    print("POSITION DIFFICULTY D (fielding runs per 1000 innings)")
    print("=" * 74)
    print(f"within-player-season pairs: {Dd['n_pairs']} from "
          f"{Dd['n_player_seasons_multi']} multi-position player-seasons")
    print(f"{'pos':<5}{'D':>8}{'95% CI':>18}{'perm null95':>13}{'uncorrected':>13}")
    for p in OAA_POSITIONS:
        c = Dd["ci95"][p]
        print(f"{p:<5}{Dd['values'][p]:>8.2f}{'[%6.2f,%6.2f]' % (c[0], c[1]):>18}"
              f"{Dd['perm_null95'][p]:>13.2f}{Dd['values_uncorrected'][p]:>13.2f}")
    print("\nera splits:")
    for k, v in Dd["era_splits"].items():
        print(f"  {k} (n_pairs={v['n_pairs']:>4})  "
              + " ".join(f"{p} {v['D'][p]:+.2f}" for p in OAA_POSITIONS))

    I = f["interaction_check"]
    print("\n" + "=" * 74)
    print("INTERACTION FALSIFICATION TEST")
    print("=" * 74)
    print(f"{I['claim_under_test']}")
    print(f"{'move':<10}{'n':>6}{'obs slope':>11}{'95% CI':>18}"
          f"{'pred by noise':>15}{'inside':>8}")
    for r in I["rows"]:
        print(f"{r['move']:<10}{r['n']:>6}{r['observed_slope']:>11.3f}"
              f"{'[%6.3f,%6.3f]' % tuple(r['ci95']):>18}"
              f"{r['predicted_by_measurement_error']:>15.3f}"
              f"{'yes' if r['prediction_inside_ci'] else 'NO':>8}")
    print(f"\n{I['n_predicted_inside_ci']}/{I['n_moves']} predicted by measurement error alone")
    print(f"VERDICT: {I['verdict']}")

    A = f["aging"]
    print("\n" + "=" * 74)
    print("DEFENSIVE AGING (standardized glove change per season)")
    print("=" * 74)
    if A.get("mean_delta_z_per_year") is None:
        print("  not fit (n too small)")
    else:
        print(f"  n={A['n']} paired same-position seasons, mean age {A['mean_age']}")
        print(f"  mean delta z per year = {A['mean_delta_z_per_year']:+.4f} "
              f"CI {A['mean_delta_ci95']}")
        print(f"  age interaction       = {A['age_interaction_per_year']:+.5f} "
              f"per year of age, CI {A['age_interaction_ci95']}")
        print(f"  applied to forecasts: {A['applied']}")

    M = f["conversion_matrix"]
    print("\n" + "=" * 74)
    print("CONVERSION MATRIX -- net runs per 650 PA for an AVERAGE glove (z = 0)")
    print("=" * 74)
    cols = list(OAA_POSITIONS) + ["DH"]
    print(f"{'from\\to':<9}" + "".join(f"{c:>8}" for c in cols))
    for a in OAA_POSITIONS:
        print(f"{a:<9}" + "".join(
            f"{M[a][b]['net_for_average_glove_per_650pa']:>8.1f}" for b in cols))
    print("\nglove-scale factor s(to)/s(from) -- the player-specific part:")
    print(f"{'from\\to':<9}" + "".join(f"{c:>8}" for c in cols))
    for a in OAA_POSITIONS:
        print(f"{a:<9}" + "".join(f"{M[a][b]['glove_scale']:>8.2f}" for b in cols))

    F = f.get("feasibility") or {}
    if F:
        print("\n" + "=" * 74)
        print("FEASIBLE MOVES -- measured from real primary-position changes")
        print("=" * 74)
        for a in OAA_POSITIONS:
            sh = F["shares"].get(a, {})
            top = " ".join(f"{b}:{100 * v:.0f}%" for b, v in
                           sorted(sh.items(), key=lambda kv: -kv[1]) if v >= 0.01)
            print(f"  {a:<3} n={F['n_by_from'].get(a, 0):>4}  offered "
                  f"{','.join(F['allowed'][a]):<26} observed {top}")

    C = payload.get("conversion_accuracy") or {}
    if C and "mae" in C:
        print("\n" + "=" * 74)
        print("PRIMARY VALIDATION -- does the conversion actually convert?")
        print("=" * 74)
        print(f"  {C['n_conversions']} clean conversions: a regular at one position "
              f"in t, a regular at a NEW position in t+1")
        print(f"  (>= {C['min_innings_each_side']:.0f} innings each side, "
              f"<= {C['prior_innings_cap_at_destination']:.0f} prior innings at the "
              f"destination)")
        print(f"\n  {'arm':<12}{'MAE':>8}{'RMSE':>8}{'corr':>8}"
              f"{'MAE advantage of model':>32}")
        for a in ("model", "carry_over", "d_shift", "league_avg", "permuted"):
            adv = C.get("mae_advantage_over", {}).get(a)
            ds = (f"{adv['mean']:+.3f}  CI {adv['ci95']}" if adv else "")
            print(f"  {a:<12}{C['mae'][a]:>8.3f}{C['rmse'][a]:>8.3f}"
                  f"{C['corr_with_actual'][a]:>8.3f}{ds:>32}")
        print(f"\n  permutation null on the MAE advantage over carry_over: "
              f"{C['perm_null95_mae_advantage']}")
        print(f"  time splits: n={C['n_time_splits']}  mean advantage "
              f"{C.get('season_advantage_mean')} sd {C.get('season_advantage_sd')}  "
              f"positive in {C.get('season_advantage_positive_in')}")
        for t, m in sorted(C["by_season"].items()):
            print(f"    {t}: n={m['n']:>3} model {m['mae_model']:>6.3f}  "
                  f"carry {m['mae_carry_over']:>6.3f}  dshift {m['mae_d_shift']:>6.3f}  "
                  f"lgavg {m['mae_league_avg']:>6.3f}  perm {m['mae_permuted']:>6.3f}")
        if C.get("difficulty_gap_out_of_sample"):
            print("\n  OUT-OF-SAMPLE check on the difficulty gap "
                  "(across-season movers, an independent sample):")
            print(f"    {'to':<6}{'n':>4}{'observed change':>18}{'95% CI':>18}"
                  f"{'model gap':>11}{'inside':>8}")
            for k, m in sorted(C["difficulty_gap_out_of_sample"].items(),
                               key=lambda kv: -kv[1]["n"]):
                print(f"    {k:<6}{m['n']:>4}{m['observed_rate_change']:>18.2f}"
                      f"{'[%5.2f,%5.2f]' % tuple(m['ci95']):>18}"
                      f"{m['model_predicted_gap']:>11.2f}"
                      f"{'yes' if m['prediction_inside_ci'] else 'NO':>8}")
        if C.get("by_move"):
            print("\n  by move (n >= 10):")
            for k, m in sorted(C["by_move"].items(), key=lambda kv: -kv[1]["n"]):
                print(f"    {k:<9} n={m['n']:>3}  model {m['mae_model']:>6.2f}  "
                      f"carry {m['mae_carry_over']:>6.2f}  "
                      f"mean actual rate {m['mean_actual']:>+6.2f}")

    V = payload.get("validation") or {}
    if V and "auc" in V:
        print("\n" + "=" * 74)
        print("VALIDATION -- can the model see a demotion coming?")
        print("=" * 74)
        print(f"  {V['label_definition']}")
        print(f"  n scored {V['n_scored']} regular seasons, {V['n_moved_any']} changed "
              f"position, {V['n_moved_down']} moved DOWN "
              f"(base rate {V['base_rate_moved_down']})")
        print(f"\n  {'arm':<14}{'AUC':>8}{'model minus arm':>30}")
        for a in ("model", "control", "ladder_only", "raw_oaa"):
            if a not in V["auc"]:
                continue
            d = V.get("model_minus", {}).get(a)
            ds = (f"{d['mean']:+.4f}  CI {d['ci95']}" if d else "")
            print(f"  {a:<14}{V['auc'][a]:>8.4f}{ds:>30}")
        print(f"\n  permutation null on |AUC - 0.5|: {V['perm_null95_auc_minus_half']}")
        print(f"  season splits: n={V.get('n_time_splits')} mean AUC "
              f"{V.get('season_auc_mean')} sd {V.get('season_auc_sd')}")
        for t, m in sorted(V["by_season"].items()):
            print(f"    {t}: n={m['n']:>4} down={m['n_moved_down']:>3} "
                  f"model {m['auc_model']}  control {m['auc_control']}")
        fr = V["flag_rule"]
        fc = V["flag_rule_control"]
        print(f"\n  flag rule (gain >= {fr['threshold_runs']} runs/650 PA):")
        print(f"    model   flagged {fr['n_flagged']:>4}  precision {fr['precision']}  "
              f"recall {fr['recall']}  lift {fr['lift_over_base_rate']}")
        print(f"    control flagged {fc['n_flagged']:>4}  precision {fc['precision']}  "
              f"recall {fc['recall']}")
        dt = V["destination_top1"]
        print(f"  among the {dt['n']} who moved down, the model's top pick was the "
              f"realized destination {dt['model']} of the time")

    def _tbl(title, key_pos, key_gain, key_se, items, n=15):
        print("\n" + "=" * 74)
        print(title)
        print("=" * 74)
        print(f"{'player':<23}{'age':>4}{'PA':>5}{'now':>5}{'to':>5}{'gain':>7}"
              f"{'+/-':>6}{'player':>8}{'league':>8}{'gloveZ':>8}"
              f"{'runs@now':>10}{'bat':>7}")
        for r in items[:n]:
            se = r.get(key_se)
            pp = r.get("demotion_gain_player_part")
            lp = r.get("demotion_gain_league_part")
            print(f"{r['name'][:22]:<23}{(r['age'] or 0):>4}{int(r['pa'] or 0):>5}"
                  f"{r['current_pos'] or '':>5}{r[key_pos] or '':>5}"
                  f"{(r[key_gain] or 0):>7.1f}{(se if se is not None else 0):>6.1f}"
                  f"{(pp if pp is not None else 0):>8.1f}"
                  f"{(lp if lp is not None else 0):>8.1f}"
                  f"{r['glove_z']:>8.2f}"
                  f"{(r['glove_runs_per_650_at_current'] or 0):>10.1f}"
                  f"{(r['bat_runs_per_650'] if r['bat_runs_per_650'] is not None else 0):>7.1f}")
        if not items:
            print("  (none)")

    _tbl(f"TOP DEMOTION CANDIDATES ({payload['target_season']}) -- the owner's "
         f"question.\n{payload['n_flagged_demotion']} flagged of "
         f"{payload['n_qualified']} regulars. Gain is runs per 650 PA.",
         "demotion_pos", "demotion_gain", "demotion_se", payload["top_demotions"])
    _tbl(f"TOP PROMOTION CANDIDATES ({payload['target_season']}) -- worth more UP "
         f"the spectrum,\nBUT only if the job is open and he has real innings there.",
         "promotion_pos", "promotion_gain", "gain_se", payload["top_promotions"])


def _player_report(payload, mlbam):
    row = next((r for r in payload["players"] if r["mlbam"] == int(mlbam)), None)
    if not row:
        print(f"no row for mlbam {mlbam}")
        return
    print(f"\n{row['name']}  (mlbam {row['mlbam']}, age {row['age']}, "
          f"{row['season']})")
    print(f"  innings: {row['innings']}")
    print(f"  glove z = {row['glove_z']:+.2f} +/- {row['glove_z_se']:.2f}  "
          f"(0 = league average, 1 = one SD better)")
    print(f"  bat = {row['bat_runs_per_650']} runs per 650 PA")
    print("  evidence:")
    for e in row["evidence"]:
        print(f"    {e['season']} {e['pos']:<3} {e['inn']:>7.1f} inn  "
              f"OAA {e['oaa']:>+5.0f}  FRP {e['frp']:>+5.0f}  "
              f"rate {e['rate']:>+6.2f}/1000inn  -> z {e['z_read']:+.2f}")
    print(f"  {'pos':<5}{'field':>9}{'ladder':>9}{'def total':>11}{'vs now':>9}")
    cur = row["current_pos"]
    base = row["by_position"].get(cur, {}).get("def_total")
    for p, v in sorted(row["by_position"].items(),
                       key=lambda kv: -kv[1]["def_total"]):
        mark = "  <- current" if p == cur else ""
        d = f"{v['def_total'] - base:>+9.2f}" if base is not None else " " * 9
        print(f"  {p:<5}{v['field']:>9.2f}{v['ladder']:>9.2f}"
              f"{v['def_total']:>11.2f}{d}{mark}")
    print(f"  best = {row['best_pos']}, gain {row['gain_runs_per_650']} "
          f"+/- {row['gain_se']} runs per 650 PA, flagged={row['flagged_misplaced']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--player", type=int, default=None)
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    payload = build(target_season=a.season, with_backtest=True)
    if not a.no_write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        print(f"wrote {OUT} -- {payload['n_players']} players, "
              f"{payload['n_flagged']} flagged")
    if a.report or a.validate:
        _report(payload)
    if a.player:
        _player_report(payload, a.player)


if __name__ == "__main__":
    main()
