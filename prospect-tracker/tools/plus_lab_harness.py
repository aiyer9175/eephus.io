# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""plus_lab_harness - Harness v2 shared by the +stat labs (REM+/SEM+/HEM+/xHEM+
family: tools/rem_plus_lab.py, tools/sem_plus_lab.py, tools/hem_plus_lab.py,
tools/xhem_plus_lab.py).

Harness v2 changes (T1-7, pre-registered 2026-07-15):

  (1) TARGET CONVENTION v2: the forward target is the WITHIN-OUTCOME-SEASON
      z-score of the year-Y+1 outcome (-RA9 for pitchers, wOBA for hitters).
      Pooling raw Y+1 outcomes across seasons leaves an era term in the target
      (a 2019 RA9 and a 2022 RA9 are not on the same scale); z-scoring within
      the outcome season removes it. Measured worth ~+0.005-0.010 rho to the
      raw baselines. v1 (raw pooled target) stays side by side for one
      transition cycle.

  (2) UNROUNDED PREDICTORS: labs must read the *_raw float scores (e.g.
      hem_plus_raw), never the shipped display rounding (int(round()) /
      3-decimal display fields). Rounding is a display convention only.

  (3) PLAYER-CLUSTERED, SEASON-STRATIFIED BOOTSTRAP (v2 CIs): the same player
      contributes up to ~11 Y->Y+1 pairs; iid pair resampling treats them as
      independent and understates CI width. v2 resamples PLAYERS (all of a
      player's pairs enter/leave a replicate together), stratified by each
      player's first predictor season so the era/cohort composition of every
      replicate matches the sample. CIs are expected to be WIDER - that is the
      point. v1 CIs (legacy iid pair bootstrap, identical draw construction to
      the original labs) stay side by side.

  (4) COMPLETE-SEASON PAIRS ONLY: a Y->Y+1 pair is dropped unless the OUTCOME
      season is complete (past Nov 15). Today that drops 2025->2026 pairs whose
      target is a mid-2026 partial season (the shipped sem_plus_eval.json
      n=702 defect, and the 0.2363-vs-0.2254 REM+ two-incumbent drift).

  (5) DUAL-CONVENTION ARTIFACTS: every lab emits BOTH conventions side by side
      under results_by_convention with a primary_convention field ("v1" for
      this transition cycle - shipped verdicts were established under v1 and
      STAND). Future gates must pre-declare their convention.

This module is pure (no network, no I/O). All stochastic steps are seeded by
the caller.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date

HARNESS_VERSION = 2

# a season counts as complete after this month/day (regular season + any
# make-up games are long over; mirrors the split-half end date convention)
SEASON_COMPLETE_MONTH_DAY = (11, 15)

# OWNER-WAIVED EARLY READ OVERRIDE (owner 2026-10-14, EW3-5 and EW3-6). The
# (11, 15) default above is a CONVENTION and it never changes. A lab that the
# owner re-armed early passes an explicit as-of override, by environment
# variable or by its own --season-complete-asof flag (which sets the same
# variable), of the form "YYYY:YYYY-MM-DD[,YYYY:YYYY-MM-DD...]": season YYYY
# counts complete once today reaches the named date. Every use is LOGGED to
# stderr once per season and is written into convention_meta() so the
# artifact carries it; a read taken under it is recorded as an owner-waived
# early read in its registration, never as the registered date's read.
SEASON_COMPLETE_ASOF_ENV = "PLUS_LAB_SEASON_COMPLETE_ASOF"
_OVERRIDE_LOGGED: set = set()


def parse_season_complete_asof(spec: str | None) -> dict[int, date]:
    """{season: as-of date} from the override spec; {} when unset or blank.
    A malformed entry raises, so a typo never silently widens a pair set."""
    out: dict[int, date] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        season, _, asof = part.partition(":")
        out[int(season)] = date.fromisoformat(asof.strip())
    return out


def set_season_complete_asof(spec: str | None) -> dict[int, date]:
    """Install `spec` as the process-wide override (the labs' flag path) and
    return the parsed map. An empty spec clears it."""
    parsed = parse_season_complete_asof(spec)
    if parsed:
        os.environ[SEASON_COMPLETE_ASOF_ENV] = spec.strip()
    else:
        os.environ.pop(SEASON_COMPLETE_ASOF_ENV, None)
    return parsed


def season_complete_override() -> dict[int, date]:
    """The override in force, read from the environment at call time."""
    return parse_season_complete_asof(os.environ.get(SEASON_COMPLETE_ASOF_ENV))


def season_complete_override_meta() -> dict | None:
    """The override block an artifact carries, or None when the default
    convention (Nov 15) was the only rule in force."""
    ov = season_complete_override()
    if not ov:
        return None
    return {
        "env": SEASON_COMPLETE_ASOF_ENV,
        "seasons": {str(y): d.isoformat() for y, d in sorted(ov.items())},
        "default_month_day": list(SEASON_COMPLETE_MONTH_DAY),
        "authority": ("owner 2026-10-14 (EW3-5, EW3-6): registered look days are "
                      "waived; the 2026 regular season ended in late September and "
                      "the labs read regular-season outcomes; reads taken under this "
                      "override are OWNER-WAIVED EARLY READS"),
    }


# --------------------------------------------------------------------------- #
# (4) complete-season gating
# --------------------------------------------------------------------------- #
def season_complete(year: int, today: date | None = None) -> bool:
    """True when season `year` is fully in the books (past Nov 15 of `year`).
    Used to drop Y->Y+1 pairs whose OUTCOME season is still being played.
    An explicit override (see SEASON_COMPLETE_ASOF_ENV) replaces the Nov 15
    rule for the seasons it names and is logged once per season."""
    t = today or date.today()
    asof = season_complete_override().get(int(year))
    if asof is not None:
        if int(year) not in _OVERRIDE_LOGGED:
            _OVERRIDE_LOGGED.add(int(year))
            print(f"season_complete OVERRIDE: season {int(year)} treated as complete "
                  f"as of {asof.isoformat()} ({SEASON_COMPLETE_ASOF_ENV}; the "
                  f"default stays {SEASON_COMPLETE_MONTH_DAY}); owner-waived early "
                  "read (owner 2026-10-14)", file=sys.stderr)
        return t >= asof
    m, d = SEASON_COMPLETE_MONTH_DAY
    return t >= date(int(year), m, d)


# --------------------------------------------------------------------------- #
# (1) within-outcome-season z-score target
# --------------------------------------------------------------------------- #
def zscore_within(groups: list, values: list) -> list:
    """z-score `values` within each group label (the outcome season). Monotone
    within a season, so it only changes how seasons pool - which is the point:
    it removes the between-season era term from the target. Groups with a
    degenerate spread (n<2 or sd=0) fall back to 0.0 (never happens for a real
    season pool)."""
    if len(groups) != len(values):
        raise ValueError("groups/values length mismatch")
    by_g: dict = {}
    for g, v in zip(groups, values):
        by_g.setdefault(g, []).append(v)
    stats = {}
    for g, vs in by_g.items():
        n = len(vs)
        mu = sum(vs) / n
        sd = (sum((v - mu) ** 2 for v in vs) / (n - 1)) ** 0.5 if n > 1 else 0.0
        stats[g] = (mu, sd)
    out = []
    for g, v in zip(groups, values):
        mu, sd = stats[g]
        out.append((v - mu) / sd if sd else 0.0)
    return out


# --------------------------------------------------------------------------- #
# stats helpers (identical algorithm to rem_plus_backtest._spearman/_ci; kept
# local so the harness stays import-light and pure)
# --------------------------------------------------------------------------- #
def spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return None

    def _ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    vy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def ci(vals):
    if not vals:
        return None
    vals = sorted(vals)
    return {"mean": round(sum(vals) / len(vals), 4),
            "lo95": round(vals[int(0.025 * len(vals))], 4),
            "hi95": round(vals[int(0.975 * len(vals)) - 1], 4)}


# --------------------------------------------------------------------------- #
# bootstraps: v1 legacy iid + (3) v2 player-clustered season-stratified
# --------------------------------------------------------------------------- #
def iid_boot_gaps(primary, baselines: dict, tgt, boot: int, seed: int) -> dict:
    """LEGACY (v1) bootstrap: iid pair resample. Draw construction is identical
    to the original labs' _boot_gap_ci (rng.randrange(n) x n per rep, one rng
    stream), so a single-baseline call reproduces the legacy numbers exactly on
    the same pair set. Returns {baseline_name: ci(rho_primary - rho_baseline)}."""
    n = len(tgt)
    rng = random.Random(seed)
    gaps = {k: [] for k in baselines}
    for _ in range(boot):
        samp = [rng.randrange(n) for _ in range(n)]
        st = [tgt[i] for i in samp]
        rp = spearman([primary[i] for i in samp], st)
        if rp is None:
            continue
        for k, series in baselines.items():
            rb = spearman([series[i] for i in samp], st)
            if rb is not None:
                gaps[k].append(rp - rb)
    return {k: ci(v) for k, v in gaps.items()}


def cluster_boot_gaps(primary, baselines: dict, tgt, players, pred_seasons,
                      boot: int, seed: int) -> dict:
    """v2 bootstrap: PLAYER-clustered, season-stratified.

    - CLUSTER = player: all of a player's Y->Y+1 pairs enter/leave a replicate
      together (players repeat up to ~11x as pairs; iid resampling understates
      the CI width).
    - STRATA = the player's FIRST predictor season in the pair set: each
      replicate draws len(stratum) players with replacement from each stratum,
      so the era/cohort composition of every replicate matches the sample.

    Deterministic given `seed`. Returns {baseline_name: ci(gap)}; expect WIDER
    intervals than iid_boot_gaps - that is the design intent."""
    if not (len(primary) == len(tgt) == len(players) == len(pred_seasons)):
        raise ValueError("parallel array length mismatch")
    by_player: dict = {}
    first_season: dict = {}
    for i, p in enumerate(players):
        by_player.setdefault(p, []).append(i)
        s = pred_seasons[i]
        if p not in first_season or s < first_season[p]:
            first_season[p] = s
    strata: dict = {}
    for p, s in first_season.items():
        strata.setdefault(s, []).append(p)
    # deterministic iteration order
    strata = {s: sorted(strata[s], key=str) for s in sorted(strata)}
    rng = random.Random(seed)
    gaps = {k: [] for k in baselines}
    for _ in range(boot):
        idx: list = []
        for s in strata:
            pl = strata[s]
            m = len(pl)
            for _ in range(m):
                idx.extend(by_player[pl[rng.randrange(m)]])
        st = [tgt[i] for i in idx]
        rp = spearman([primary[i] for i in idx], st)
        if rp is None:
            continue
        for k, series in baselines.items():
            rb = spearman([series[i] for i in idx], st)
            if rb is not None:
                gaps[k].append(rp - rb)
    return {k: ci(v) for k, v in gaps.items()}


def cluster_summary(players, pred_seasons) -> dict:
    """Descriptive block for the artifact: how clustered is the pair set."""
    by_player: dict = {}
    for p in players:
        by_player[p] = by_player.get(p, 0) + 1
    counts = sorted(by_player.values(), reverse=True)
    n = len(players)
    return {
        "n_pairs": n,
        "n_players": len(by_player),
        "max_pairs_per_player": counts[0] if counts else 0,
        "mean_pairs_per_player": round(n / len(by_player), 2) if by_player else None,
        "n_strata_first_pred_season": len(set(
            min(s for p2, s in zip(players, pred_seasons) if p2 == p)
            for p in by_player)) if by_player else 0,
    }


# --------------------------------------------------------------------------- #
# (5) dual-convention artifact scaffolding
# --------------------------------------------------------------------------- #
def convention_meta(target_v1: str, target_v2: str,
                    primary: str = "v1") -> dict:
    """The conventions block every harness-v2 artifact carries. primary stays
    'v1' for this transition cycle: shipped verdicts were established under v1
    and STAND; future gates must pre-declare their convention up front."""
    return {
        "harness_version": HARNESS_VERSION,
        "primary_convention": primary,
        "v1": {
            "target": target_v1,
            "bootstrap": "iid pair resample (legacy; 2000 reps, seeded)",
            "note": "legacy convention; the shipped gate verdicts were established here",
        },
        "v2": {
            "target": target_v2 + " (within-OUTCOME-season z-score removes the era term)",
            "bootstrap": ("player-clustered (all of a player's pairs move together), "
                          "season-stratified (players stratified by first predictor "
                          "season); 2000 reps, seeded; CIs are wider by design"),
            "note": "transition-cycle companion; future gates must pre-declare v1 or v2",
        },
        "pair_rule": ("Y->Y+1 pairs kept only when the OUTCOME season is complete "
                      "(past Nov 15). Partial-year targets (e.g. mid-2026) are a "
                      "defect, dropped under BOTH conventions."),
        "season_complete_override": season_complete_override_meta(),
        "predictors": "unrounded *_raw model scores (display rounding never enters evals)",
        "interpretation_rules": [
            "existing VALIDATED ships STAND even if v2 weakens them; a reversal is "
            "flagged to the owner, not auto-reverted",
            "ledgered NO-SHIPs are re-baselined under v2 but never revived by v2 alone",
            "X-R2 / X-S2 flips are not promised",
        ],
    }
