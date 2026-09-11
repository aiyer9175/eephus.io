# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_model.py - MLB game probabilities from the site's own surfaces.

THE POINT: everything a book prices, this platform already measures. Team
offense is HEM+ rolled up to `offense_plus`; the rotation is SEM+ rolled up to
`rotation_plus` with the listed probable's own SEM+ available per start; the
bullpen is REM+ rolled up to `bullpen_plus`; park run environment is the same
Savant index the FA engine reads out of data/fa_meta.json. No new data source
is invented here. The model is a run-scoring regression on those four inputs
plus home field, and a Poisson-difference margin on top of it.

THE SCORING MODEL (two rows per game, one per scoring side)

    runs_S = b0 + b1*z_off_S + b2*z_prev_O + b3*park + b4*home

      z_off_S    the scoring team's offense_plus, standardized across the 30
                 teams for the season.
      z_prev_O   the OPPONENT's run prevention for THIS game: the listed
                 probable's SEM+ for the share of the game a starter covers
                 (ip_per_gs / 9), the opponent's bullpen_plus for the rest,
                 standardized on the team-level prevention distribution. With
                 no probable announced, the opponent's rotation_plus stands in.
      park       the home park's Savant runs index / 100 - 1 (0 = neutral).
      home       1 when S bats last.

    The coefficients are FIT, not assumed (`fit_coefficients`), on completed
    games read out of the existing .cache/game_feeds StatsAPI feed cache. That
    matters: a plus-stat sigma is not a run, and guessing the conversion is
    where a model like this usually goes wrong. When no fit is available the
    module falls back to literature priors (LITERATURE_COEFFS) and says so in
    `coefficients()["source"]`.

    Expected runs go into a Poisson-difference (Skellam) margin, computed by
    direct convolution so there is no scipy dependency in the serving path.
    That gives the moneyline (P(margin > 0), with the measured extra-innings
    home rate splitting the tie mass), the runline (P(margin >= 2)), and the
    total (Poisson on the run sum).

    THE TIE MASS IS READ IN ONE PLACE, `split_tie_atom` (L14-01, 2026-09-11).
    The moneyline splits it by the measured extra-innings home rate. Until
    2026-09-11 the runline gave the whole of it to BOTH +1.5 sides, which
    asserts that no game that goes to extra innings is ever won by two or more;
    since owner decision 4 the runline reads the measured split of the same
    atom, coherent with the moneyline by construction. See
    SERVE_RUNLINE_TIE_SPLIT.

WHAT THIS MODEL IS NOT, AND THE PAGE SAYS SO
    THE RUN DISTRIBUTION IS WRONG, not soft. Poisson asserts var = mean;
    measured over 3,532 scoring-side rows it is 2.3385, and the margin carries
    2.3748x the Skellam-implied variance. P(|margin| >= 5) is 0.2990 in the
    games and 0.1390 in the model. Runline and total probabilities therefore
    sit far too close to the middle, and the moneyline is the least exposed of
    the three only because `diff_shrink` was fitted to absorb it there.

    A one-parameter NB2 correction was built and PRE-REGISTERED against a
    four-criterion held-out gate (docs/diamond-betting.md section 11a). The
    verdict is INDETERMINATE, not a pass: the amended criterion 2 clears the
    bar at split quantiles 0.6 and 0.7 and misses it at 0.8, and a verdict that
    moves with the split point is a verdict about the split point. It is not
    served. Until a correction passes, the runline and the total are excluded
    from both published slots and from the public record, enforced by
    `market_is_publishable` rather than asserted here.

    AMENDED 2026-08-14, and the amendment is the honest half. This paragraph
    previously also claimed the exclusion covered the PAPER BET LEDGER, and
    for months NONE of the three was implemented at all: the published pick of
    the day was a runline and 78 percent of shadow rows were runline or total.
    The slots and the record are now genuinely excluded. The ledger is
    deliberately NOT, because it is the instrument that accumulates the settled
    outcomes needed to resolve the dispersion gate, and excluding them there
    would delete the only evidence that could ever lift the exclusion. Owner
    decision 2026-08-14. See SERVE_RUN_DISPERSION and market_is_publishable.

    AMENDED 2026-09-05, owner decision: the published slots are NO LONGER locked
    to the moneyline. Every market the board prices (moneyline, runline, total,
    and player props once the props pull is armed) is eligible for both slots
    and for the public record; the slot finds the best side under its own rule
    across all of them. The dispersion caveat and the section 7b ledger evidence
    now ride the published ROW as disclosure instead of barring the market. See
    SLOT_MARKET_POLICY; the theory leg is still measured and still published.

    Worse, and this is the reason the module ships UNVALIDATED: the team
    inputs are SEASON-TO-DATE aggregates. Backtesting 2026 games against
    August's leaderboards means the features already contain the outcomes
    being predicted. `backtest()` runs, reports honest numbers, and labels
    them contaminated. Nothing here unlocks a published pick. A pick ships
    only once vintage-dated team inputs exist and a clean out-of-sample
    number does.

THE VINTAGE PATH (leaderboard_vintages.py), which is how that gets fixed.
    `inputs_as_of(date)` returns the team, pitcher AND park inputs from the
    newest nightly snapshot whose knowledge cutoff is STRICTLY BEFORE that date,
    so nothing that happened on or after the game can reach its features. A
    snapshot written before the park column existed returns `parks: None`, and
    the vintage backtest prices those games on a NEUTRAL park rather than on the
    live index; it never silently borrows today's number for a past game. Until
    the nightly snapshot has been running long enough, there is no such
    vintage for any date, and the read falls back to the live leaderboards
    with `contaminated: True` and a logged warning. Nothing in this module
    silently looks forward.

    `backtest()` therefore reports TWO modes and labels both: the contaminated
    mode (the old numbers, in-sample and forward-split) and the vintage mode,
    which grades only the games it can grade honestly and starts at n = 0. The
    vintage sample is what gates `min_edge`; see VINTAGE_MIN_GRADED_GAMES for
    the threshold and the measurement behind it.

    THE COEFFICIENT FIT IS FITTING NOISE, AND THE REPAIR DID NOT PAY (2026-09-06,
    docs/diamond-betting.md section 7e). On the vintage fit half (305 games, 610
    design rows) b1, the scoring team's OWN offense, comes back at -0.037205:
    the fit says a better offense scores fewer runs, at r2 = 0.003, and
    `diff_shrink` then lands at 1.28, expanding what a shrink parameter exists
    to contract. A sign-constrained ridge shrunk toward LITERATURE_COEFFS was
    built and gated (`ridge_fit_gate`, RIDGE_FIT_GATE_CRITERIA). On the served
    window it repairs every symptom, b1 to +0.041543, b3 0.594771 to 3.157603,
    diff_shrink to 1.08, and grades 0.00062 of Brier WORSE. The gate verdict is
    INDETERMINATE, one split of three, so SERVE_RIDGE_FIT is False and the OLS
    keeps serving. The finding underneath is about the FEATURE: at the
    constrained optimum the own-offense term is pinned to exactly zero at every
    gate split, so on vintage features it is not paying for itself. This module
    does NOT claim the fit is sound. It claims the fit is measured and that the
    obvious repair was measured too and lost.

    WHAT THE MODEL IS WORTH PER MARKET, MEASURED, AND IT IS NOT MUCH (B-OBJ,
    section 7e). `per_market_objective` scores every market the board prices
    against the de-vigged market open on the same games. On the 2026-09-06
    vintage eval window all three FAIL the accuracy leg: moneyline -0.011093
    paired Brier against the open (lb95 -0.020556), runline -0.004859
    (lb95 -0.017432), total -0.024015 (lb95 -0.040268). The total is worse than
    its own base rate at t = -2.537. The moneyline is the only market that beats
    a constant. Under the lexicographic objective (accuracy first) no market may
    set a threshold and the ROI leg never had to be consulted. The block is DARK
    and nothing served reads it; see PER_MARKET_SURFACE.

DE-VIGGING (`devig`) uses the PROPORTIONAL method: each side's raw implied
probability divided by the book's overround. It is the standard, it is
transparent, and it is the one an edge number can be audited against.
Shin and the power/additive methods shift favourite-longshot weight around;
they are not used, and swapping one in would change every edge on the page,
so the method name travels in the payload.

CLI:
    python betting_model.py --context      # league constants + fitted coefficients
    python betting_model.py --backtest     # both modes, both labelled
    python betting_model.py --gate         # the min_edge gate state, one screen
    python betting_model.py --ridge        # the section 7e fit gate + window probe
    python betting_model.py --game NYM CLE # one matchup, hand-checkable
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("betting_model")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
FEED_CACHE = ROOT / ".cache" / "game_feeds"
GAME_CACHE = ROOT / ".cache" / "betting"
CONTEXT_PATH = DATA_DIR / "betting_model_context.json"
EVAL_PATH = DATA_DIR / "betting_model_eval.json"

# THE LEDGER KEY. Every calibration, shadow and record row carries it, and a
# ledger that pools two pricers under one version measures a mixture nobody
# priced. v2 (2026-09-11, owner decisions 2, 4 and 23, ONE bump for all three
# pricer changes, which shipped together): the short-sample parks are served
# (SERVE_ATH_PARK: the Athletics at Sutter Health Park and the Rays' Tropicana
# row shrunk by its own sample), the runline reads the measured split of the
# tie atom (SERVE_RUNLINE_TIE_SPLIT), and two-way starters enter the SEM+
# starter pool the probable's price is read from (starter_export). v1 rows
# stay v1; nothing re-labels them. Two artifacts carry the v2 state and the
# nightly checkout reverts both to their committed copies: data/fa_meta.json's
# `park_factors_short_window` block (without it the parks price as v1; logged,
# see `park_index`) and data/betting_model_context.json (the coefficients; a v1
# context beside this pricer is stamped on every record row as
# `context_version`, see betting_export.context_version_note).
MODEL_VERSION = "betting_runs_v2"

# Share of a game the listed starter is expected to cover when the pitcher has
# no measured ip_per_gs. 5.2 IP is roughly the 2026 league average start.
DEFAULT_SP_SHARE = 5.2 / 9.0

# Fallbacks for a checkout with no feed cache. Sourced from published league
# run environments (2023-2025 MLB sat at 4.3-4.6 R/G per team, home teams won
# 52-54%), NOT from anything measured here. `coefficients()["source"]` says
# which set is live, and the page prints it.
LITERATURE_COEFFS = {
    "b0": 4.45,      # league runs per team per game
    "b1": 0.32,      # runs per sigma of team offense
    "b2": -0.32,     # runs per sigma of opponent run prevention
    "b3": 3.20,      # runs per unit of park index deviation (1.10 park -> +0.32)
    "b4": 0.09,      # home field, in runs, per side
    "source": "literature-priors",
    "n_rows": 0,
}
LITERATURE_TIE_HOME = 0.50       # home win rate once a game reaches extras
# Shrink strength for the extra-innings home rate. A season carries ~140 extra
# inning games, whose raw rate swings +/- 4 points on noise alone, so the
# measured value is shrunk toward a coin flip on a 100-game prior.
TIE_SHRINK_K = 100.0

# --- the regulation-tie atom (L14-01, 2026-09-11) ----------------------------
# The margin distribution puts mass on d == 0, a game level after nine. MLB has
# no ties, so every market priced off the margin has to say what that atom
# becomes, and until 2026-09-11 the moneyline and the runline said two different
# things about the SAME atom inside the same function, silently:
#
#   moneyline  P(d > 0) + p_tie * extra_inning_home_rate, the rate measured on
#              this season's extra-inning games and shrunk toward a coin flip.
#   runline    P(d >= 2) for home -1.5 and P(d <= -2) for away -1.5, so the
#              whole atom is a +1.5 cover for BOTH sides. That is the unstated
#              claim P(final margin >= 2 | the game went to extras) == 0.
#
# The completed-game cache the context is fitted on measures that conditional
# directly, and `build_context` now publishes it as
# `extra_inning_runline_split_fitted`. Read 2026-09-11 off the 2,200-game cache:
# 193 extra-inning games, the home side won 93 of them and won by two or more in
# 10, the away side won 100 and won by two or more in 51. The asymmetry is the
# walk-off: the home team stops batting the moment it leads in the bottom of an
# inning and the away team does not. So the served runline OVERSTATES every
# +1.5 side by p_tie times the other side's two-run-plus share of the tie, and
# understates the -1.5 side of the same pair by exactly as much. A home +1.5
# carries the larger error.
#
# `split_tie_atom` is now the ONE reader of the atom: the moneyline, the
# runline, and dfs_export's implied team totals all go through it. With this
# flag False it reproduces every shipped number BIT FOR BIT, because the
# runline's split is (0, 0), the whole-atom construction, now named instead of
# implied. With it True the runline reads the served split, built so it is
# coherent with the moneyline by construction: P(home by 2+ | tie) is
# tie_home * P(home by 2+ | home wins in extras), and the away side likewise
# with 1 - tie_home, so the runline can never say a side wins by two in extras
# more often than the moneyline says it wins in extras at all.
#
# SERVED SINCE 2026-09-11, OWNER DECISION 4 ("reprice now"), ahead of the gate
# below, which it does not replace. It moves served prices, so it shipped in ONE
# commit with the MODEL_VERSION bump (betting_runs_v2), the lab wiring and the
# tests, and it was measured first. On the 2026-09-11 slate (15 games, 86 priced
# rows, the 17:35 UTC snapshot, re-priced on the leaderboards as rebuilt at 22:41
# UTC, the old and the new pricer on identical inputs), with the served
# coefficients held: all 28 runline rows on the 14 games with a runline move, by
# 0.00628 to 0.03668, every +1.5 side DOWN and every -1.5 side UP by the same
# amount; the moneyline and the total do not move. One value side flips (LAA at
# WSN, away +1.5 to home -1.5). Floor-clearing sides 23 -> 21 (CHW at STL home
# +1.5, 0.69211 -> 0.65757, and CLE at MIN home +1.5, 0.69375 -> 0.65707, fall
# under 0.06); the Pick of the Day is unchanged (PHI at ATL, ATL moneyline
# 0.75424). Over the 27 cached odds snapshots re-priced on today's inputs (425
# games, 2,540 rows): 840 runline rows move, 34 value sides flip, floor-clearing
# sides 605 -> 553, and the published slot changes on 8 of 27 slates, every one
# of them a +1.5 runline pick that the split prices under the floor or below
# another side (2026-09-10: CHW +1.5 edge 0.09332 gives way to PIT at CHW Over
# 7.5).
#
# IT CHANGES THE SECTION 11a DISPERSION GATE'S VERDICT, LEG BY LEG, and the
# registry text that quotes it goes stale on the next nightly backtest. The gate
# grades NB2 against Poisson on the runline as the board prices it, so with the
# split served both arms price the split (`_lab_runline_split`), and the split
# takes most of what NB2 was being credited for on the runline. Measured on the
# 2,200 cached games, amended both-sides criterion, t at split quantiles 0.6 /
# 0.7 / 0.8:
#   v1 pricer            runline 3.196 / 2.086 / 2.221 PASS at all three; total
#                        2.271 / 1.334 / 0.049; verdict INDETERMINATE (0.6 only)
#   the split alone      runline 0.482 / -0.127 / 0.540 FAIL at all three; total
#                        unchanged; verdict FAIL
#   the parks alone      runline 3.186 / 2.043 / 2.203; total 2.614 / 1.841 / 0.517;
#                        verdict INDETERMINATE (0.6 and 0.7)
#   two-way alone        runline 3.189 / 2.076 / 2.212; total 2.309 / 1.381 / 0.080;
#                        verdict INDETERMINATE (0.6 only)
#   v2, all three        runline 0.473 / -0.116 / 0.540 FAIL; total 2.645 / 1.876 /
#                        0.539; verdict FAIL
# So dispersion moves from INDETERMINATE to FAIL, and it did not ship before and
# does not ship now. The total leg's gain (0.7: t 1.334 -> 1.876, now past 1.645)
# comes from the PARK REPAIR, a pricer-input change (the split alone leaves it
# identical); it is the registered 11a gate re-run on its own schedule, not a
# look at the B-TOTAL lane, and B-TOTAL's own criteria are untouched by it.
#
# THE GATE STILL OWNS THE SUCCESSOR. The runline has a registered successor lane
# (B-RUNLINE, docs/master-plan-2026-09-05-opus.md: a margin kernel with an
# explicit walk-off redistribution, held-out runline both-sides log loss at
# t >= 1.645 at ALL of 0.6 / 0.7 / 0.8 plus the ledger arm on the canonical
# games). This correction is a strict subset of that direction; the gate decides
# whether the kernel replaces it, and it must still be gated JOINTLY with the
# one-run band (observed P(|margin| == 1) 0.2721 against Poisson's 0.2503,
# section 11a), because moving atom mass off d == +/-1 runs the opposite way to
# that error. It is NOT the closed symmetric NB2 arm: it widens nothing, it
# reassigns one atom.
#
# THE ATOM IS NOT A CALIBRATED P(EXTRA INNINGS). At the league run environment
# (4.4841 runs a side) the Poisson tie atom is 0.1352, against an observed
# extras rate of 0.0877 (193 of 2,200). An empirical extras conditional applied
# to an inflated atom moves the runline toward the observed margin
# distribution; it does not calibrate it.
#
# WHAT SHIPPED WITH IT, the flip procedure this constant used to list: (1) the
# owner's call stands in for the gate's ship; (2) MODEL_VERSION is bumped, because
# the settled runline rows in the shadow ledger and every runline row in the
# calibration ledger were priced by the whole-atom construction; (3) the labs
# that READ a runline probability (the section 11a dispersion arms and the
# backtest's per-market grade) price it on their FIT window's own split through
# `_lab_runline_split`, and the dispersion gate is re-run on the next
# `--dispersion`; (4) this constant, test_betting_runline_tie_atom.py and the
# served `extra_inning_runline_split` context key (written by the next
# `--context`) move together; (5) the row disclosure (`tie_atom`) now records
# `split_served: True` with a zero shift, and `tie_atom_caveat` returns None,
# because the price IS the split. False restores the whole-atom construction
# bit for bit.
SERVE_RUNLINE_TIE_SPLIT = True

# --- run dispersion --------------------------------------------------------
# THE DEFECT THE MODULE SHIPPED WITH, measured 2026-08-09 on all 1,766 cached
# completed games (3,532 scoring-side rows). Poisson asserts var = mean. Team
# runs come in at mean 4.4853, var 10.4889, so var/mean = 2.3385. The margin is
# worse because the error compounds across two sides: observed margin variance
# 21.3057 against a Skellam-implied 8.9714, a ratio of 2.3748. In tail terms,
# P(|margin| >= 5) is 0.2990 in the games and 0.1390 under the model the games
# were priced by. That is not a caveat about softness, it is the wrong
# distribution: the model is short 2.15x of the mass that decides every runline.
#
# It is NOT lambda heterogeneity. Under a Poisson mixture var(Y) = E[lam] +
# var(lam), and the model's own lambdas have sd 0.6128 across the 3,532 rows,
# so var(lam) = 0.3755 of the 6.0036 of excess variance: 6.25%. The other
# 93.75% is within-game clumping, which is a scoring-process fact (a rally
# scores runs in a correlated burst) and no amount of better features touches
# it.
#
# NB2 is the one-parameter answer: var = lam + alpha*lam^2, with r = 1/alpha
# the size parameter. Conditional MLE given the model's own per-row lambda
# lands alpha = 0.28425 (r = 3.5181) and buys +725.71 nats of held-in
# log-likelihood over Poisson for that single parameter. Whether it SHIPS is
# not a function of that number: the pre-registered four-criterion gate in
# docs/diamond-betting.md section 11a decides it, on a held-out half. It did
# not ship. See SERVE_RUN_DISPERSION.
RUN_DISPERSION_MIN_ALPHA = 1e-4
RUN_DISPERSION_MAX_ALPHA = 2.0
# Whether the fitted alpha is SERVED. `build_context` always measures it and
# always publishes the measurement; this flag is the only thing that lets it
# reach a price. Set from the section 11 gate, never from a fit statistic.
#
# FALSE, AND THE REASON IS "INDETERMINATE", NOT "FAILED". Run 2026-08-09 on the
# 1,775-game completed cache, under the criterion actually in force:
# DISPERSION_GATE_CRITERIA as amended, criterion 2 scored on BOTH runline sides
# (RUNLINE_SIDE_AMENDMENT), and the verdict taken from
# `dispersion_gate_sensitivity` across DISPERSION_SPLIT_QUANTILES rather than
# from any single split. The persisted grid is
# data/betting_model_eval.json -> run_dispersion.sensitivity.
#
#   split  date        n_fit  n_eval   home d/t          away d/t         both d/t
#   0.6    2026-06-14   1054     721   -0.003628 -0.972  +0.015004 3.860  +0.011376 3.069 PASS
#   0.7    2026-06-27   1223     552   -0.003280 -0.769  +0.015018 3.367  +0.011738 2.799 PASS
#   0.8    2026-07-11   1413     362   -0.004701 -0.886  +0.011155 2.034  +0.006454 1.224 FAIL
#
# The other three criteria pass at all three splits. So the amended criterion 2
# passes at 0.6 and 0.7 and misses the t >= 1.645 bar at 0.8, where the delta is
# still POSITIVE (+0.006454) and it is the standard error that runs out: n_eval
# drops from 721 to 362. Under the ship rule declared before the sweep ran -
# every quantile or nothing - that is INDETERMINATE, and indeterminate does not
# ship. The flag stays False.
#
# TWO THINGS THIS SUPERSEDES, both of which pointed the other way:
#   * The FIRST reading of this gate was home-side only and reported the runline
#     at -0.003075, t = -0.717. That is the `home` column above and it is a real
#     number, but "margin >= 2" names neither side, alpha moves both tails at
#     once, and the defect was stated in absolute margin everywhere it was
#     measured. The home reading is not the estimand. It FAILS at all three
#     splits; the away reading PASSES at all three.
#   * The pre-registered single split, 0.7, now PASSES all four criteria under
#     the amended criterion 2. If the verdict were taken from that one split the
#     flag would be True. It is not taken from one split, on purpose, and that
#     rule was fixed in DISPERSION_SPLIT_QUANTILES before the sweep ran.
#
# WHY THE HOME SIDE LOSES, AND IT IS MECHANICAL RATHER THAN A SAMPLE-SIZE
# PROBLEM: NB2 fixes the tail and OVERCORRECTS THE MIDDLE. On the 1,775-game
# cache priced from the served context, P(|margin| >= 5) goes 0.1390 -> 0.2897
# against 0.2986 observed, which is the repair, and P(|margin| = 1) goes
# 0.2503 -> 0.1917 against 0.2721 observed, which is worse than what it
# replaced. Real baseball concentrates at one run because a tied home ninth ends
# the moment the run scores, so the home team's two-run-plus tail is clipped in
# a way the away team's is not - the eval half bears that out, home -1.5 lands
# 0.3442 of the time against away -1.5 at 0.3768. No product of two INDEPENDENT
# count distributions can represent that asymmetry, and the runline is priced
# exactly on the band NB2 damages.
#
# Criterion 3 (total over 9.0, +0.010709 at t = +2.545) and criterion 4
# (+0.2190 nats/row) are kept on the record for whoever tries next: the
# dispersion is REAL and NB2 does capture it for the TOTAL, where the two sides
# add and the walk-off structure does not bite. A correction scoped to the
# total, or a bivariate model with a one-run atom, is the live direction. A
# wider symmetric margin is not.
#
# TO FLIP THIS FLAG: re-run `dispersion_gate_sensitivity`, get `ship` True (all
# three quantiles), and change this constant, the tripwire in
# test_betting_dispersion.py and the persisted `run_dispersion` block in the
# same commit. The three move together or not at all.
SERVE_RUN_DISPERSION = False

# ── THE EXCLUSION THIS MODULE HAS ALWAYS DOCUMENTED AND NEVER IMPLEMENTED ────
# The docstring at the top of this file has said, since the dispersion gate came
# back INDETERMINATE, that the runline and the total are excluded from the
# published slots, the public record and the paper ledger until a correction
# passes. NOTHING IMPLEMENTED IT. The only consequence was
# betting_export.POISSON_CAVEAT, a string attached to the row.
#
# Measured 2026-08-14, which is why this is a P0 and not a tidy-up:
#   - the published pick of the day WAS a runline, edge 0.123, model prob 0.725
#   - the shadow ledger held 62 of 80 rows (78%) in runline + total
#   - those two markets' own graded Brier is 0.26301 and 0.26522, both WORSE
#     than a flat 0.500, which is exactly what the underdispersed Skellam
#     predicts and what the INDETERMINATE gate declined to fix
# So the module was publishing its most confident number on the markets it had
# itself measured as its least reliable, under a docstring promising the
# opposite.
DISPERSION_SENSITIVE_MARKETS = ("runline", "total")

#: SLOT MARKET POLICY (owner decision 2026-09-05, docs/diamond-betting.md 7d).
#:   "any"               every market the board prices is eligible for both published
#:                       slots and for the public record: moneyline, runline, total, and
#:                       player props when the props pull is armed. The dispersion caveat
#:                       (runline / total) and the section 7b ledger evidence travel ON
#:                       THE ROW as disclosure; neither bars a market.
#:   "dispersion_gated"  the 2026-08-14 behaviour: runline and total excluded from the
#:                       slots and the record until SERVE_RUN_DISPERSION flips, and a
#:                       ledger-closed market fills no slot.
#: The owner's instruction, in intent: the Pick of the Day is not locked to the moneyline;
#: spread, moneyline, totals and props are all allowed, find the best pick. The selection
#: RULE is unchanged by this constant (highest model probability in the price band for the
#: headline slot, best EV at a long price for the other); making the rule reliability-
#: aware across markets of different measured calibration is the registered accuracy-and-
#: ROI bake-off lane, not a silent edit here.
SLOT_MARKET_POLICY = "any"


def market_theory_ok(market: str | None) -> bool:
    """The DISPERSION LEG alone: False for a market whose prices depend on the margin
    distribution while the correction is not served. Independent of SLOT_MARKET_POLICY
    on purpose: the policy decides whether a row may PUBLISH, this decides what the
    publishability table SAYS about the theory, and the two must not blur."""
    if SERVE_RUN_DISPERSION:
        return True
    return str(market or "").lower() not in DISPERSION_SENSITIVE_MARKETS


def market_is_dispersion_sensitive(market: str | None) -> bool:
    """True when a published row on this market must carry the Poisson caveat: the
    market is priced off the margin distribution and the correction is unserved."""
    return not market_theory_ok(market)


def market_is_publishable(market: str | None) -> bool:
    """False for a market whose prices depend on the margin distribution while
    the dispersion correction is not served.

    Scope is the PUBLISHING seam only: the two slots and the public record,
    where a pick is a CLAIM. The paper ledger deliberately keeps recording
    these rows, and that is an amendment to the docstring's third clause made
    with its reason stated rather than silently: the shadow ledger is the
    instrument that accumulates the settled runline and total outcomes needed
    to ever RESOLVE the dispersion gate. Excluding them there would remove the
    only evidence that could lift this exclusion, so the ledger would freeze
    the model in its current state forever. Owner decision 2026-08-14.

    Flips itself off automatically if SERVE_RUN_DISPERSION is ever set True, so
    this cannot outlive the defect it guards.

    AMENDED 2026-09-05: under SLOT_MARKET_POLICY "any" every market is publishable
    and the caveat rides the row (market_is_dispersion_sensitive). The theory leg
    is still answered by market_theory_ok for the publishability table.
    """
    if SLOT_MARKET_POLICY == "any":
        return True
    return market_theory_ok(market)
# The gate itself, verbatim, so the artifact carries its own pre-registration
# and a reader never has to trust that the doc and the code agree. Written into
# docs/diamond-betting.md section 11a BEFORE the gate was run.
#
# THIS IS THE ORIGINAL TEXT AND IT IS KEPT UNEDITED. Criterion 2 says "margin
# >= 2" and does not say WHOSE margin. That is an under-specification, it is
# load-bearing, and it is not fixed by pretending the original said something
# else. See DISPERSION_GATE_CRITERIA below for the amendment and
# RUNLINE_SIDE_AMENDMENT for the argument.
DISPERSION_GATE_CRITERIA_V1 = (
    "fit {coefficients, alpha, diff_shrink, home_field_runs_adj} on the fit half of a "
    "70% date split; on the HELD-OUT half all four must hold: (1) home win, paired "
    "Brier, non-inferiority, one-sided 95% lower bound on delta >= -0.001; (2) margin "
    ">= 2, paired log loss, delta > 0 at t >= 1.645; (3) total over 9.0, paired log "
    "loss, delta > 0 at t >= 1.645; (4) runs both sides, out-of-sample log-likelihood "
    "per row, NB > Poisson. Moneyline is non-inferiority because diff_shrink already "
    "absorbs its calibration and NB must not be credited for beating it there."
)

# WHICH RUNLINE SIDE CRITERION 2 SCORES. Decided 2026-08-09, and the decision
# changes the verdict, so the argument is written here rather than implied by
# the code that implements it.
#
# THE AMBIGUITY IS REAL. The board publishes four runline prices per game:
# p_home_minus_1_5, p_away_minus_1_5, p_home_plus_1_5, p_away_plus_1_5. They are
# TWO binary events, because p_home_plus_1_5 == 1 - p_away_minus_1_5 and
# p_away_plus_1_5 == 1 - p_home_minus_1_5, and log loss is invariant under
# complementation. The two distinct events are the two TAILS of one margin
# distribution: home margin >= +2, and home margin <= -2. "margin >= 2" names
# neither. The first implementation scored the home tail only.
#
# THE DECISION IS BOTH SIDES, and the argument is about the estimand, not about
# the number it returns:
#
#   1. The criterion exists to decide whether a distribution SHAPE may be served
#      to the runline market. The runline market is both sides. Every board row
#      carries all four prices, every one of them is a published probability,
#      and a criterion that scores one of the two events measures less than what
#      ships. An estimand should be the loss on what is published.
#   2. alpha is ONE symmetric widening parameter. It moves both tails at once
#      and by construction cannot move only the home one. Reading its effect off
#      a single tail measures half the effect and throws away half the data for
#      no gain in interpretability.
#   3. The DEFECT this correction was built for was stated symmetrically and in
#      absolute terms everywhere it was measured: P(|margin| >= 5) 0.1390 vs
#      0.2990, P(|margin| >= 2) 0.6171 vs 0.7276, P(|margin| == 1) 0.2503 vs
#      0.2724. A test for a symmetric defect that reads one tail is not the test
#      the defect asked for.
#   4. The home-only reading is not a neutral default. It is home-referenced
#      because the rest of the module is, which is a naming convention, not a
#      measurement decision.
#
# AND THE CHOICE FLIPS THE GATE. On the pre-registered 70% split the home tail
# fails criterion 2 and the away tail and the both-sides sum pass it, with the
# other three criteria passing under every reading. That is stated up front so
# nobody has to discover it: this is a specification that decides a verdict, and
# picking it after seeing the numbers is exactly the failure mode. The reasoning
# above is why both-sides is right, and it would be the same argument if
# both-sides had failed.
#
# THE VERDICT IS DECIDED BY ROBUSTNESS, NOT BY ONE SPLIT. `dispersion_gate_
# sensitivity` runs every side against split quantiles 0.6, 0.7 and 0.8 and the
# gate ships only if the honest specification holds across all of them. If it
# does not, the gate is INDETERMINATE and dispersion stays off. See
# SERVE_RUN_DISPERSION for what that sweep returned.
RUNLINE_SIDE_AMENDMENT = "both"
RUNLINE_SIDES = ("home", "away", "both")
_RUNLINE_SIDE_LABEL = {
    "home": "home margin >= 2, i.e. home -1.5 / away +1.5",
    "away": "home margin <= -2, i.e. away -1.5 / home +1.5",
    "both": "both sides, per-game sum of the two log losses",
}
# The split quantiles the verdict must hold across. 0.7 is the pre-registered
# one and the other two bracket it. Fixed here so the sweep cannot be widened
# or narrowed after the fact to reach a verdict.
DISPERSION_SPLIT_QUANTILES = (0.6, 0.7, 0.8)

# The amended pre-registration, criterion 2 now unambiguous. V1 is kept above,
# unedited, because an amendment that overwrites the text it amends is not an
# amendment.
DISPERSION_GATE_CRITERIA = (
    "fit {coefficients, alpha, diff_shrink, home_field_runs_adj} on the fit half of a "
    "70% date split; on the HELD-OUT half all four must hold: (1) home win, paired "
    "Brier, non-inferiority, one-sided 95% lower bound on delta >= -0.001; (2) THE "
    "RUNLINE, BOTH SIDES, scored as the per-game SUM of the log loss on home margin "
    ">= 2 and the log loss on home margin <= -2 (equivalently home -1.5 and away -1.5; "
    "the +1.5 sides are their complements and score identically), paired, delta > 0 at "
    "t >= 1.645; (3) total over 9.0, paired log loss, delta > 0 at t >= 1.645; "
    "(4) runs both sides, out-of-sample log-likelihood per row, NB > Poisson. "
    "Moneyline is non-inferiority because diff_shrink already absorbs its calibration "
    "and NB must not be credited for beating it there. AMENDED 2026-08-09: V1 said "
    "only 'margin >= 2' and did not name a side, the first run scored the home side "
    "alone, and the side changes the verdict; see RUNLINE_SIDE_AMENDMENT. The verdict "
    "is taken from `dispersion_gate_sensitivity`, which requires the amended criterion "
    "to hold at split quantiles 0.6, 0.7 and 0.8, not from any single split."
)

# --- probability calibration (B5, Platt) -----------------------------------
# p' = sigmoid(a * logit(p) + b), two parameters, order-preserving. The gate it
# must clear was pre-registered in docs/diamond-betting.md section 11b BEFORE
# this code existed and before any number was looked at, and the criteria ride
# here verbatim so the artifact never depends on the doc staying honest.
#
# THE PRE-REGISTERED EXPECTATION, written before the first fit: Platt repairs
# RESPONSE SCALE (overconfidence, inversion at the extremes). It cannot
# manufacture discrimination and it is NOT expected to open the skill gate;
# a model whose ordering carries nothing converges TOWARD the constant
# baseline under a scale repair, and converging toward the baseline is a
# finding. diff_shrink is already fitted on the fit half by log loss, so most
# of the response scale is absorbed before Platt sees a probability, and a
# fitted (a, b) near (1, 0) is the honest likely outcome.
#
# TO FLIP THIS FLAG: both arms of `prob_calibration_gate` must pass, and the
# flag, the persisted `prob_calibration` block in betting_model_eval.json and
# the tripwire in test_betting_platt.py change in the SAME commit - the
# SERVE_RUN_DISPERSION three-move-together pattern. The ledger arm cannot
# count before PROB_CALIBRATION_LEDGER_MIN_GAMES settled canonical moneyline
# games exist (49 on 2026-08-16), so the flag cannot flip today whatever the
# vintage arm returns. Serving scope is the MONEYLINE ONLY; the runline and
# the total stay behind the dispersion gate (section 11a) regardless.
SERVE_PROB_CALIBRATION = False
PROB_CALIBRATION_SPLIT_QUANTILES = (0.6, 0.7, 0.8)
PROB_CALIBRATION_LEDGER_MIN_GAMES = 100
PROB_CALIBRATION_GATE_CRITERIA = (
    "fit (a, b) of p' = sigmoid(a*logit(p) + b) by MLE on the fit half only; on the "
    "held-out half BOTH must hold: (1) paired per-game Brier delta, identity minus "
    "Platt, > 0 at one-sided t >= 1.645; (2) paired log loss delta not worse on the "
    "point estimate (>= 0). Splits at date quantiles 0.6, 0.7 and 0.8, ALL THREE or "
    "nothing, fit half >= 100 games and eval half >= 50 or the split cannot pass. "
    "Arm 1 is the vintage-gradable sample with {coefficients, tie, diff_shrink, "
    "home_adj} refit on each fit half; arm 2 is the calibration ledger's settled "
    "canonical-side moneyline games, ACTIVE only at n >= 100, same splits and "
    "criteria in settled order. Ship requires BOTH arms; serving is moneyline only."
)

# --- the vintage gate ------------------------------------------------------
# How many games the VINTAGE-mode backtest must grade before `min_edge` may be
# fitted at all. This number is measured, not picked to look serious.
#
# The claim a published pick rests on is that the model beats the home-field
# baseline out of sample. Grade that as a paired Brier difference, one game per
# pair. When this floor was derived, the forward split (2026-06-24 onward,
# n = 521, coefficient leakage removed but feature leakage still present) gave
# +0.005794 at a paired sd of 0.08647, so t = 1.529, and detecting a margin
# that size at one-sided 95% needs
#
#     n = (1.645 * 0.08647 / 0.005794)^2 = 603 games
#
# rounded to 600.
#
# THOSE THREE NUMBERS HAVE ALREADY DRIFTED AND WILL KEEP DRIFTING, and the
# constant does NOT follow them. The same split on the 1,766-game cache reads
# n = 543, delta +0.006624, sd 0.07994, t = 1.931, n_for_95 = 394; a reading
# taken between the two said n = 543, delta 0.007866, t = 2.332, n_for_95 = 270.
# Re-deriving the floor from whichever value the artifact happens to hold is
# how a sample-size requirement becomes a function of the result it is meant to
# discipline: every month the contaminated margin looks better, the bar it has
# to clear gets lower. The number is pinned at 600.
#
# 600 IS THE RIGHT ORDER FOR A REASON THAT DOES NOT MOVE: a clean margin will
# be SMALLER than a contaminated one, and a smaller margin needs a larger
# sample, so a floor derived from the contaminated estimate is a LOWER BOUND on
# what the honest test will need. That is now measured rather than asserted.
# The vintage mode grades 211 games at a paired skill of -0.001224 (t = -0.332):
# the honest margin is not merely smaller, it is on the wrong side of zero, and
# no finite n_for_95 exists for a negative effect. 600 games makes the test
# possible. It does not make it pass, and nothing in the current honest sample
# suggests it will.
#
# 600 is also a FLOOR on the sample, not a substitute for the test:
# `min_edge_gate` still requires the paired difference to clear zero at
# one-sided 95% on that sample, and still requires a graded price history to
# sweep the threshold on.
#
# At the measured 2026 rate of 13.1 completed games per calendar date, 600
# games is about 46 slate days of nightly snapshots.
VINTAGE_MIN_GRADED_GAMES = 600
# Below these the vintage mode reports counts only and no metrics: 100 games is
# 200 design rows, the same floor `fit_coefficients` already enforces, and 50
# eval games is the floor the existing forward split uses.
VINTAGE_MIN_FIT_GAMES = 100
VINTAGE_MIN_EVAL_GAMES = 50
# The fit half is a TARGET SIZE, not a share, and that is a deliberate choice
# about how long this takes. A 60/40 split would put 40% of the archive in the
# eval half, so reaching 600 graded games would need 1,500 gradable ones, about
# 115 slate days. The fit half does not need to be large: five coefficients and
# two one-parameter corrections are comfortably estimated on 300 games (600
# design rows, three times the floor `fit_coefficients` enforces). Anchoring
# the fit at 300 and giving everything later to the eval window reaches 600
# graded games at ~900 gradable, about 69 slate days. The fit window stays
# anchored at the earliest dates as the archive grows, which drifts the eval
# window further from the fit over time: that is the conservative direction,
# it makes the test harder rather than easier.
VINTAGE_FIT_TARGET_GAMES = 300
# ...but never more than half the covered DATES, so a young archive still
# produces an eval window instead of one enormous fit.
VINTAGE_FIT_MAX_DATE_SHARE = 0.5
# One-sided 95% normal critical value, used for both the Brier-skill gate and
# the ROI lower bound in the min_edge sweep.
Z_95_ONE_SIDED = 1.645


# --- B-ML-FIT: the coefficient fit, and the sign that says it is noise -----
# MEASURED 2026-09-06, reproduced in session on the same window the artifact
# holds (data/betting_model_eval.json -> vintage.coefficients). The vintage fit
# half is 305 games / 610 design rows and OLS returns
#
#     b0 4.345387   b1 -0.037205   b2 -0.096479   b3 0.594771   b4 0.149360
#     rmse 3.288484   r2 0.003049   and then diff_shrink 1.28
#
# b1 is the SCORING TEAM'S OWN OFFENSE and it is NEGATIVE: on this window the
# fit says a better offense scores fewer runs. The contaminated 4,248-row fit
# puts the same term at +0.260319 (in_sample.coefficients.b1), so the sign is
# not a property of the feature; it is 610 rows at r2 = 0.003 being read as a
# slope. `diff_shrink` then comes back at 1.28, which EXPANDS a differential
# that a parameter named "shrink" exists to contract, because the linear
# predictor has almost no spread left of its own to take out.
#
# THE REPAIR IS SHRINKAGE, NOT FEATURES. Fit the same five coefficients as a
# ridge pulled toward LITERATURE_COEFFS, with the three signs the run-scoring
# model asserts a priori held as hard constraints: own offense up, opponent
# prevention down, park up. The penalty is chosen on the FIT half alone, by
# moneyline log loss on an inner date split of that half, and never on the eval
# window.
#
# THE FAMILY DOES NOT CONTAIN THE INCUMBENT ON THIS WINDOW, and that is worth
# stating because the opposite is the natural assumption about a ridge. Penalty
# 0 reproduces the OLS to 1e-14 only when the OLS is already sign-feasible;
# where it is not, the CONSTRAINT still moves it. Measured on the vintage fit
# half, at penalty 0 the constrained fit pins b1 to exactly 0 and returns
# b0 4.346304, b2 -0.096682, b3 0.576559, b4 0.147895, which is not the OLS.
# b1 leaves the boundary only at penalty 0.3 and above. So the grid cannot
# return the incumbent here, and the gate compares two genuinely different fits
# rather than a fit against a shrunken copy of itself.
#
# NOTHING HERE SHIPS ON THAT ARGUMENT. RIDGE_FIT_GATE_CRITERIA is the
# pre-registration, `ridge_fit_gate` is the measurement, and SERVE_RIDGE_FIT is
# set from its verdict and from nothing else.
RIDGE_PENALIZED_TERMS = ("b1", "b2", "b3", "b4")   # b0 is a run level, not a slope
RIDGE_SIGN_CONSTRAINTS = {"b1": 1, "b2": -1, "b3": 1}
# Log spaced, with 0.0 first so the weakest member of the family is on the grid
# and an inner split that wants no shrinkage at all says so by returning it. 0.0
# is NOT the incumbent wherever the sign constraints bind; see above.
RIDGE_PENALTY_GRID = (0.0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
RIDGE_INNER_SPLIT_Q = 0.75
RIDGE_MIN_INNER_FIT_GAMES = 60
RIDGE_MIN_INNER_EVAL_GAMES = 30
RIDGE_FIT_GATE_CRITERIA = (
    "fit both arms on the fit half of a date split and score both on the held-out "
    "half, with {extra-innings tie rate, diff_shrink, home_field_runs_adj} re-solved "
    "SEPARATELY for each arm on its own fit half, so a tuned incumbent is never "
    "graded against an untuned challenger. The ridge penalty is chosen inside the "
    "fit half by moneyline log loss on an inner date split at RIDGE_INNER_SPLIT_Q; "
    "the eval half is never consulted for it. At split quantiles 0.6, 0.7 and 0.8, "
    "ALL THREE or nothing: (1) NON-INFERIORITY, paired per-game Brier, ridge minus "
    "OLS, one-sided 95% lower bound >= -0.001; (2) SUPERIORITY over the literature "
    "Elo tier (tools/betting_elo, the section 6 ladder's results-only floor), paired "
    "per-game Brier, ridge better at t >= 1.645; (3) paired log loss delta not worse "
    "on the point estimate (>= 0). Fit half >= 100 games and eval half >= 50 or the "
    "split cannot pass. Coefficients and diff_shrink are persisted at every split, "
    "so a verdict that rides on one window is visible as one."
)
# Whether the ridge fit is SERVED. Set from `ridge_fit_gate`, never from a fit
# statistic and never from the sign of b1 alone: a wrong-signed coefficient is a
# reason to BUILD the challenger, not a reason to ship it.
#
# FALSE, AND THE VERDICT IS "INDETERMINATE". Measured 2026-09-06 by
# `ridge_fit_gate` on the 792-game vintage-gradable sample (grid persisted at
# data/betting_model_eval.json -> ridge_fit, table in
# docs/diamond-betting.md section 7e):
#
#   split  cut         n_fit n_eval  brier delta  lb95       ll delta    checks
#   0.6    2026-08-13    469    323   -0.000221   -0.000774  -0.000442   1 of 3
#   0.7    2026-08-19    548    244   -0.000203   -0.000553  -0.000411   1 of 3
#   0.8    2026-08-25    627    165   +0.000213   -0.000611  +0.000432   3 of 3
#
# One of three splits passes, so the grid is mixed and the incumbent keeps
# serving. THE INTERESTING PART IS THE SERVED WINDOW. On the shipped cut
# (2026-08-01, fit 305 / eval 487) the ridge at penalty 0.3 repairs every
# symptom that motivated it: b1 goes -0.037205 -> +0.041543 (sign correct, and
# the constraint is NOT binding there), b3 goes 0.594771 -> 3.157603 (the
# literature prior is 3.20), diff_shrink 1.28 -> 1.08, home adjustment
# -0.0443 -> +0.0063. The eval Brier goes 0.24460 -> 0.24522, delta -0.000617
# at t = -0.812, lb95 -0.001868: worse, not significantly so, and below the
# registered non-inferiority bar. The wrong sign is real and repairing it buys
# nothing measurable, which is a finding about the FEATURE, not about the
# solver: at the constrained optimum the own-offense term is pinned to exactly
# zero at every gate split, so on vintage features that column is not paying
# for itself at any penalty the inner split chose.
SERVE_RIDGE_FIT = False
# Whether the vintage fit window GROWS with the archive instead of being anchored
# at VINTAGE_FIT_TARGET_GAMES. Anchored, every new slate goes to the eval window
# and the fit stays at ~300 games forever; grown, the split is the date share and
# both halves grow. The accounting cost is measured, not assumed: on the
# 2026-09-06 archive (792 gradable games over 59 dates) anchoring gives fit 305 /
# eval 487 and growing gives fit 384 / eval 408, so growth buys 79 fit games and
# pays 79 eval games, one for one off the VINTAGE_MIN_GRADED_GAMES clock.
#
# FALSE, AND THE ACCURACY COST IS THE REASON, not the accounting one.
# `fit_window_probe` answers this the only way it can be answered, by holding
# the EVAL window and varying only the fit (the two windows are complements, so
# the two shipped configurations are not paired and cannot be compared
# directly). Paired per-game Brier, anchored minus grown, positive means grown
# is better:
#
#   split  cut         fit 305 vs   n_eval   delta       t       lb95
#   0.6    2026-08-13  469             323   -0.002789  -2.107  -0.004967
#   0.7    2026-08-19  548             244   -0.000133  -0.162  -0.001482
#   0.8    2026-08-25  627             165   +0.001750  +0.867  -0.001570
#
# The grown fit is WORSE at 0.6, a coin flip at 0.7 and better at 0.8 on the
# point estimate, but it MISSES the -0.001 non-inferiority bar at ALL THREE
# splits: the lb95 column is -0.004967, -0.001482 and -0.001570, and every one
# of those sits below -0.001. The split where growth looks best is no exception,
# because 165 eval games do not buy an interval tight enough to clear the bar
# from a +0.001750 point estimate.
#
# It is worse while looking healthier: the grown fit at 0.6 carries b3 = 2.83
# against the anchored
# 0.59, i.e. a park coefficient much nearer the literature prior, and still
# grades 0.00279 of Brier worse on the same 323 games. Coefficient plausibility
# and out-of-sample accuracy point in OPPOSITE directions on this sample, and
# the flag follows the accuracy.
VINTAGE_FIT_WINDOW_GROWS = False


# --- BET1: the total level, and why most value totals are Overs (2026-09-11) --
# THE OWNER'S QUESTION was whether a board where most value bets are Overs is a
# bug or a feature. It is a bug, and it is not the one the 2026-09-05 plan named.
#
# THE SKEW IS SYSTEMATIC, not one slate. Re-pricing every cached open capture in
# .cache/odds/ on the served context and the dated vintage (26 slates with a
# completed game, 425 games): the model fair total sits a mean +0.604 runs above
# the posted line (median +0.65), above it on 26 of 26 slates, and positive-edge
# totals split 323 Over to 102 Under (232 to 44 at the 0.06 floor). The served
# 2026-09-11 board reads +0.893 and 13 Overs of 15. The calibration ledger's
# as-served rows, inverted through the served Poisson, read +0.652 on 18 of 18
# slates and 155 Over to 46 Under.
#
# THE MEAN IS NOT THE CAUSE. On the vintage FIT half (305 games before the
# 2026-08-01 split, served coefficients on dated features) the model's mean total
# is 8.8649 against 8.8066 actual, a level bias of +0.058 runs. In-sample over all
# 2,200 games it is 0.000 by the OLS identity. b0 is not too high, and the
# prevention and park terms pull the fit-half level DOWN (-0.081 and -0.053),
# not up. A mean recentre moves the total 0.058 runs and does almost nothing.
#
# THE CAUSE IS THE POISSON CENTRE. Real run totals have var/mean 2.35 on the same
# 305 games (median 8, mean 8.81). A Poisson with the RIGHT mean puts its middle
# at that mean, while the real distribution, skewed by blowouts, splits about a
# run lower, and a book posts its line where the real distribution splits. So a
# correctly levelled Poisson compares its mean against the market's median and
# calls the Over: on the fit half, P(over 8.5) is 0.5206 served against 0.4328
# observed, and 0.5131 even after the mean recentre.
#
# THIS FLAG IS THE LEVEL HALF OF THE REPAIR AND ONLY THAT. One additive constant
# on the Poisson total mean, fitted on the vintage fit half alone by the summed
# over/under log loss at the fixed line grid TOTAL_LEVEL_LINES (the lines
# B-TOTAL named). It prices the TOTAL ONLY: the margin distribution, the
# moneyline and the runline are built from the unshifted lambdas and are
# byte-identical with the flag on or off, and `fair_total` stays lam_home +
# lam_away (the expected runs). A Poisson cannot be calibrated at every line by
# one shift, because its shape is wrong: the fitted constant is a compromise
# between 7.5 (wants about -0.6) and 10.5 (wants a positive shift). The shape
# half is the total-scoped dispersion lane (B-TOTAL stage 2), not this flag.
TOTAL_LEVEL_LINES = (7.5, 8.5, 9.5, 10.5)
# The search interval for the constant, in runs. Wide enough that the fit never
# sits on it on any window this module has seen (the fit-half answer is -0.23).
TOTAL_LEVEL_BOUNDS = (-3.0, 3.0)
# The pre-registration, verbatim, written before any eval-window outcome was
# scored under either arm (the fit half had been read; that is what it is for).
TOTAL_LEVEL_GATE_CRITERIA = (
    "the recentre is one additive constant delta (runs) on the Poisson total mean; "
    "the margin, the moneyline and the runline are computed from the unshifted "
    "lambdas and may not move. CENTRE arm (the candidate): delta = argmin of the "
    "summed over/under log loss at the fixed line grid (7.5, 8.5, 9.5, 10.5), equal "
    "weights, over the fit half, golden-section on [-3, 3]. MEAN arm (the 2026-09-05 "
    "plan's literal candidate): delta = mean actual total minus mean model total on "
    "the fit half. Splits: the anchored served split (_vintage_cut_index) AND the "
    "date quantiles 0.6, 0.7, 0.8 of the vintage-gradable dates; every split refits "
    "{coefficients, tie_home, diff_shrink, home_adj} on its own fit half as the "
    "vintage lab does, fits delta on that same fit half, and scores the eval half. "
    "On each split's EVAL half BOTH must hold, at ALL FOUR splits or the verdict is "
    "not ship: (1) paired per-game total log loss summed over the same grid, "
    "incumbent (delta 0) minus recentred, > 0 at one-sided t >= 1.645; (2) paired "
    "per-game log loss at EACH grid line not worse on the point estimate for at least "
    "three of the four lines. Structural and asserted by test, not measured: "
    "moneyline and runline byte-identical with the flag on and off. Fit half >= 100 "
    "games and eval half >= 50 or the split cannot pass. Diagnostics, never "
    "criteria, because the market is a diagnostic target and never an input: model "
    "P(over) at the posted line minus the realised over rate on eval games with a "
    "cached open capture, and the Over/Under split of positive-edge totals on every "
    "cached slate."
)
# Whether the fitted recentre is SERVED. Set from `total_level_gate`, never from
# the size of the Over skew. FALSE: see docs/diamond-betting.md section 7f for
# the gate grid.
#
# WHAT FLIPPING IT CHANGES, measured 2026-09-11 with the fit-half constant
# -0.2315 runs:
#   * every total side's model probability, edge, EV and Kelly (Over down,
#     Under up), and `total_level_runs` / `total_price_mean` on the model row;
#   * which total side is "value" on some games, and so the best-value badge and
#     the published slots whenever a total was, or becomes, their best row;
#   * NOTHING on the moneyline or the runline, to the bit.
#
# TO FLIP IT, in ONE commit: (1) `total_level_gate` returns ship; (2) this
# constant, the tripwire in test_betting_total_level.py and section 7f move
# together; (3) MODEL_VERSION is bumped, because every settled total row in the
# shadow and calibration ledgers was priced without the recentre and a ledger
# that pools two pricers under one version measures a mixture nobody priced;
# (4) `python betting_model.py --context` is re-run so `total_level` is written
# (the served key is null until then and a flip alone moves nothing).
SERVE_TOTAL_LEVEL = False

# ── THE TOTAL'S SHAPE (section 7g, 2026-09-11) ──────────────────────────────
# The shape half of the Over-lean repair. The Over, Under and push are priced off
# the total of two independent NB2 sides sharing ONE dispersion alpha_T, at the
# model's own unshifted lambdas. The margin distribution, and so the moneyline and
# the runline, come from the served first pass and cannot move. alpha_T is fitted
# on the vintage fit half alone by the same grid log loss 7f uses.
TOTAL_DISPERSION_BOUNDS = (1e-4, 2.0)
TOTAL_DISPERSION_GATE_CRITERIA = (
    "docs/diamond-betting.md section 7g, verbatim in intent: two independent NB2 "
    "sides with one alpha_T price the TOTAL only, at unshifted lambdas; the margin, "
    "the moneyline and the runline come from the served pass and may not move. "
    "alpha_T = argmin of the summed over/under log loss at (7.5, 8.5, 9.5, 10.5) on "
    "each split's fit half, golden-section on [0.0001, 2.0]. Splits: anchored plus "
    "date quantiles 0.6, 0.7, 0.8; every split refits the pricer on its own fit "
    "half. On each eval half BOTH, at ALL FOUR splits: (1) paired grid log loss, "
    "Poisson minus candidate, > 0 at one-sided t >= 1.645; (2) per-line log loss "
    "not worse on the point estimate at >= 3 of 4 lines. Fit >= 100 and eval >= 50 "
    "games or the split cannot pass. Market diagnostics are never criteria."
)
# Whether the fitted alpha_T is SERVED. Set from `total_dispersion_gate`, never
# from the size of the lean, and a flip is the owner's call even on a PASS.
# Flipping it moves every total side's probability, edge, EV and Kelly, which
# total side is value on some games, and the slots whenever a total is their best
# row; the moneyline and the runline do not move. With it, in ONE commit: bump
# MODEL_VERSION, move the tripwire in test_betting_total_dispersion.py, re-run
# `--context` so `total_dispersion_alpha` is written.
SERVE_TOTAL_DISPERSION = False

# ── THE TOTAL'S MEDIAN (section 7h, 2026-09-11) ─────────────────────────────
# Two parameters on the Poisson SURVIVAL function: S'(k) = sigmoid(a*logit(S(k))
# + b) for every integer k, a valid distribution whenever a > 0. At a half-point
# line this is exactly the Platt map of P(over), so (a, b) are fitted with
# `fit_platt` on the fit half's pooled grid outcomes. The margin pass, the
# moneyline and the runline cannot move.
TOTAL_CALIBRATION_GATE_CRITERIA = (
    "docs/diamond-betting.md section 7h: S'(k) = sigmoid(a*logit(S(k)) + b) on the "
    "served Poisson TOTAL survival function at unshifted lambdas; (a, b) by MLE of "
    "the Over outcomes pooled over (7.5, 8.5, 9.5, 10.5) on each split's fit half "
    "(fit_platt); a <= 0 refused. Splits: anchored plus date quantiles 0.6, 0.7, "
    "0.8, each refitting the pricer on its own fit half. On each eval half BOTH, at "
    "ALL FOUR splits: (1) paired grid log loss, Poisson minus candidate, > 0 at "
    "one-sided t >= 1.645; (2) per-line log loss not worse on the point estimate at "
    ">= 3 of 4 lines. Fit >= 100, eval >= 50. The moneyline and the runline may not "
    "move. Market diagnostics are never criteria."
)
# Served only from the 7h gate and only by the owner; the 7f flip checklist.
SERVE_TOTAL_CALIBRATION = False


# ---------------------------------------------------------------------------
# small io helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _data(name: str):
    return _load_json(DATA_DIR / name)


def _org(name: str | None) -> str | None:
    """Anything team-shaped -> the canonical 3-letter org code. The site runs
    TWO code sets: the leaderboards carry StatsAPI abbreviations (SD, SF, TB,
    KC, AZ, CWS, WSH, ATH) while park factors and fantasy_schedule carry the
    Baseball-Reference style (SDP, SFG, TBR, KCR, ARI, CHW, WSN, ATH).
    canonical_org maps the first onto the second, so EVERY join in this module
    goes through it. Mixing the two silently drops eight clubs."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:                                            # pragma: no cover
        return None


def _mean_sd(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    if not n:
        return 0.0, 1.0
    mu = sum(xs) / n
    var = sum((x - mu) ** 2 for x in xs) / n
    return mu, (math.sqrt(var) or 1.0)


# ---------------------------------------------------------------------------
# team + pitcher inputs off the committed leaderboards
# ---------------------------------------------------------------------------
# THE DARK CAPTURE COLUMNS, ONE TUPLE PER SCHEMA, named here so the assembly has
# a stable key set even before any record carries them. Each is pinned equal to
# leaderboard_vintages.SCHEMA<n>_TEAM_COLUMNS by test_leaderboard_vintages, which
# is the one-source-of-truth guard the lazy import cannot give.
#
# Until 2026-09-11 only the schema-3 tuple existed here, so the nine schema-4
# columns (docs/diamond-betting.md 5d) were stored in every vintage and never
# reached the standardization seam; the 5d harness needs that read path before
# its look, and section 5f registered the generalization in the schema-5 bump.
# A record written under a lower schema reads None for every higher-schema
# column (team_inputs_from_vintage goes by the record's own column list), and
# absent is never zero.
#
# DARK MEANS DARK. These reach the assembled team inputs and their z-scores are
# computed by the same standardization as everything else, and then NOTHING
# served reads them: not expected_runs, not game_prevention_z, not a slot, not
# a record row. A candidate wanting a price goes through the protocol in
# docs/diamond-betting.md section 5c, gate section first.
DARK3_TEAM_COLUMNS = ("xwoba_14", "xwoba_30", "off_vs_lhp", "off_vs_rhp",
                      "lineup_strength", "star_out")
DARK4_TEAM_COLUMNS = ("pen_b2b_arms", "pen_arms_avail", "pen_ip_l3",
                      "pen_plus_avail", "rest_days", "games_in_l7",
                      "wx_temp_climo", "wx_wind_out_climo", "catch_frame_rate")
DARK5_TEAM_COLUMNS = ("lhb_share_vr", "lhb_share_vl",                     # 5i-B
                      "lineup_dis_vs_lhp", "lineup_dis_vs_rhp",           # 5f
                      "bench_adv_vs_lhp", "bench_adv_vs_rhp",
                      "ph_share", "pen_lhp_share",
                      "team_fld_runs")                                    # 5g
DARK_TEAM_COLUMNS_BY_SCHEMA = {3: DARK3_TEAM_COLUMNS, 4: DARK4_TEAM_COLUMNS,
                               5: DARK5_TEAM_COLUMNS}
DARK_TEAM_COLUMNS = DARK3_TEAM_COLUMNS + DARK4_TEAM_COLUMNS + DARK5_TEAM_COLUMNS
DARK_PITCHER_COLUMNS = ("throws",)


def _assemble_team_inputs(off: dict, rots: dict, pens: dict,
                          starter_ip: dict, relief_ip: dict,
                          extras: dict | None = None) -> dict:
    """The standardization, written ONCE.

    The live path and the vintage path both land here, which is the point: a
    z-score computed one way on today's leaderboards and another way on a
    stored snapshot would make the backtest incomparable to the served model
    for a reason nobody would ever see.

    `extras` is the dark capture, {org: {column: value | None}} over
    DARK_TEAM_COLUMNS (every schema's tuple). Every assembled row carries every
    dark column (None when absent, never zero) plus its z, standardized over the
    teams that HAVE the value; the served model reads none of them. Both paths hand the same shape
    in, so the live and vintage key sets cannot drift."""
    orgs = sorted(set(off) & set(pens) & set(rots))
    if not orgs:
        # LOG THE COUNTS, not the outcome. The board published "team
        # leaderboards have not been built yet" while all three leaderboards
        # held 30 clubs, because this is an INTERSECTION: one source that parses
        # to zero orgs, or a code-set mismatch that makes the sets disjoint,
        # empties it with every file on disk fully populated. The three counts
        # are the only thing that separates those cases, so they go in the log
        # and (through `team_inputs_detail`) onto the page.
        log.error("betting_model: team inputs are EMPTY - the intersection of the "
                  "three team leaderboards is 0 orgs (offense %d, rotation %d, "
                  "bullpen %d). Every game on the board will fail to price.",
                  len(off), len(rots), len(pens))
        return {}
    # Team run prevention = rotation and bullpen weighted by their ACTUAL
    # innings split, not a guessed 60/40. The split moves several points a year
    # and moves more than that for an opener-heavy staff.
    prev = {}
    for o in orgs:
        sip, rip = starter_ip.get(o, 0.0), relief_ip.get(o, 0.0)
        w = sip / (sip + rip) if (sip + rip) > 0 else DEFAULT_SP_SHARE
        prev[o] = w * rots[o] + (1.0 - w) * pens[o]

    off_mu, off_sd = _mean_sd([off[o] for o in orgs])
    prev_mu, prev_sd = _mean_sd([prev[o] for o in orgs])
    # Dark-column scales, one per column, over the teams that carry a value.
    # A column that is null everywhere (the xwOBA pair tonight) simply has no
    # scale and every z comes back None; nothing is imputed.
    ex = extras or {}
    ex_scale: dict[str, dict] = {}
    for col in DARK_TEAM_COLUMNS:
        vals = [ex[o][col] for o in orgs
                if isinstance(ex.get(o), dict) and ex[o].get(col) is not None]
        if len(vals) >= 2:
            mu, sd = _mean_sd(vals)
            ex_scale[col] = {"mu": mu, "sd": sd, "n": len(vals)}
    out = {}
    for o in orgs:
        sip, rip = starter_ip.get(o, 0.0), relief_ip.get(o, 0.0)
        row = {
            "org": o,
            "offense_plus": off[o],
            "rotation_plus": rots[o],
            "bullpen_plus": pens[o],
            "prev_plus": prev[o],
            "sp_ip_share": (sip / (sip + rip)) if (sip + rip) > 0 else DEFAULT_SP_SHARE,
            "z_off": (off[o] - off_mu) / off_sd,
            "z_prev": (prev[o] - prev_mu) / prev_sd,
        }
        eo = ex.get(o) if isinstance(ex.get(o), dict) else {}
        for col in DARK_TEAM_COLUMNS:
            v = eo.get(col)
            row[col] = v
            sc = ex_scale.get(col)
            row["z_" + col] = ((v - sc["mu"]) / sc["sd"]
                               if (v is not None and sc) else None)
        out[o] = row
    out["_scale"] = {"off_mu": off_mu, "off_sd": off_sd,
                     "prev_mu": prev_mu, "prev_sd": prev_sd,
                     "extras": ex_scale}
    return out


def team_inputs_detail() -> dict:
    """{"teams": {...}, "sources": {...}} - the live team inputs AND the
    per-leaderboard org counts that produced them.

    THE COUNTS EXIST SO A BLANK BOARD CAN BE DIAGNOSED RATHER THAN GUESSED AT.
    `team_inputs` returns the INTERSECTION of three org sets, so "empty" has at
    least three distinct causes (a missing file, a source that parsed to zero
    rows, and two code sets that do not overlap) and they need different fixes.
    Reporting only the outcome cost this module a published false diagnosis;
    see `betting_export.team_input_failure_reason`."""
    files = {"offense": "hitter_leaderboards.json",
             "rotation": "starter_leaderboards.json",
             "bullpen": "bullpen_leaderboards.json"}
    blobs = {k: _data(v) for k, v in files.items()}

    lv = _vintage_module()
    # The schema-5 tally columns on the LIVE path come off the nightly capture's
    # memo alone (betting_usage.live_ph_columns never opens a feed); a club the
    # memo cannot place reads None. Any failure is a stated absence, never a
    # zero and never a reason to fail the board.
    try:
        import betting_usage
        ph_live = betting_usage.live_ph_columns()
    except Exception:                                            # noqa: BLE001
        ph_live = {}
    lens_down = bool(lv.hand_lens_down(blobs["offense"])) if lv else True
    off, extras = {}, {}
    for t in (blobs["offense"] or {}).get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("offense_plus") is not None:
            off[o] = float(t["offense_plus"])
            # The dark capture on the LIVE path, reduced by the SAME helper the
            # vintage write side uses so the two cannot drift. The columns with
            # no live builder (the xwOBA pair, lineup_strength, star_out, every
            # schema-4 column, team_fld_runs) stay None here: the live read
            # states absence exactly the way a stored null does, and never
            # invents a number.
            vl, vr = (lv.off_splits_from_hitter_team(t) if lv else (None, None))
            extras[o] = {c: None for c in DARK_TEAM_COLUMNS}
            extras[o]["off_vs_lhp"], extras[o]["off_vs_rhp"] = vl, vr
            if lv and not lens_down:
                extras[o]["lhb_share_vr"] = lv.lhb_share_from_orders(t, "R")
                extras[o]["lhb_share_vl"] = lv.lhb_share_from_orders(t, "L")
                extras[o].update(lv.ph_splits_from_hitter_team(t))
            extras[o].update(ph_live.get(o) or {})
    pens, relief_ip = {}, {}
    for t in (blobs["bullpen"] or {}).get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("bullpen_plus") is not None:
            pens[o] = float(t["bullpen_plus"])
            relief_ip[o] = float(t.get("relief_ip") or 0.0)
    rots, starter_ip = {}, {}
    for t in (blobs["rotation"] or {}).get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("rotation_plus") is not None:
            rots[o] = float(t["rotation_plus"])
            starter_ip[o] = float(t.get("starter_ip") or 0.0)

    parsed = {"offense": off, "rotation": rots, "bullpen": pens}
    sources = {
        k: {"file": files[k],
            "present": blobs[k] is not None,
            "n_orgs": len(parsed[k]),
            "as_of": (blobs[k] or {}).get("as_of")}
        for k in files
    }
    teams = _assemble_team_inputs(off, rots, pens, starter_ip, relief_ip, extras)
    sources["n_orgs_joined"] = len([o for o in teams if not o.startswith("_")])
    return {"teams": teams, "sources": sources}


def team_inputs() -> dict:
    """{org: {...}} team strength, standardized, from the LIVE leaderboards.

    Empty when the leaderboards are absent (fresh checkout), which the caller
    degrades on. These are season-to-date: for a backtest that must not see
    the future, go through `inputs_as_of`. A caller that has to EXPLAIN an
    empty return wants `team_inputs_detail` instead."""
    return team_inputs_detail()["teams"]


def starter_inputs() -> dict:
    """{mlbam: {sem_plus, ip_per_gs, name, org}} from starter_leaderboards, so a
    game can be priced on the announced probable rather than the rotation
    average. Relievers are folded in too (openers, bulk relief)."""
    out = {}
    rot = _data("starter_leaderboards.json") or {}
    # `throws` is None on the LIVE path by design: the hand is captured by the
    # nightly vintage snapshot's one bulk StatsAPI join, and the live read does
    # not repeat that network call per build. A None here is a stated absence,
    # and nothing served reads the key (DARK_PITCHER_COLUMNS).
    for r in rot.get("starters") or []:
        mid = r.get("mlbam")
        if not mid or r.get("sem_plus") is None:
            continue
        out[int(mid)] = {"mlbam": int(mid), "name": r.get("name"),
                         "org": _org(r.get("team")),
                         "sem_plus": float(r["sem_plus"]),
                         "ip_per_gs": float(r.get("ip_per_gs") or 0.0) or None,
                         "role": r.get("role") or "SP", "throws": None}
    pen = _data("bullpen_leaderboards.json") or {}
    for r in pen.get("relievers") or []:
        mid = r.get("mlbam")
        if not mid or r.get("rem_plus") is None or int(mid) in out:
            continue
        out[int(mid)] = {"mlbam": int(mid), "name": r.get("name"),
                         "org": _org(r.get("team")),
                         "sem_plus": float(r["rem_plus"]),   # same 100/10z scale
                         "ip_per_gs": None, "role": "RP", "throws": None}
    return out


def park_index() -> dict:
    """{org: runs index / 100}. data/fa_meta.json carries the Savant park
    factors the FA engine already reads; no second copy is fetched. Missing
    parks resolve neutral at lookup, never invented.

    SERVE_ATH_PARK (section 5i-A) is the one exception to "missing resolves
    neutral", and it is ON since 2026-09-11 (owner decision 2). A
    SHORT_WINDOW_PARK_ORGS club whose venue holds less than a full 3-season
    Savant sample takes that venue's factor shrunk by its own PA sample, off
    fa_meta's `park_factors_short_window` sibling: the Athletics (Sutter Health
    Park, dropped by the 3-season view) and the Rays (Tropicana Field, whose
    2024-2026 row holds only 2024 and 2026, because they played 2025 at George
    M. Steinbrenner Field). A short row can only ever shrink a 3-season factor
    toward neutral by that factor's own sample, never replace it with a
    different number. See `park_index_from_meta`.

    THE BLOCK HAS TO BE ON DISK FOR THE FLAG TO DO ANYTHING. fa_meta.json is a
    tracked artifact the nightly checkout reverts, and the board, the refit and
    DFS all read it before the FA re-export rewrites it, so a committed copy
    without `park_factors_short_window` prices the Athletics neutral and the
    Rays unshrunk while the rows say v2. That state is logged here, loudly and
    once per process, naming the clubs (`short_window_parks_missing`), and
    test_betting_ballpark fails on it rather than skipping."""
    meta = _data("fa_meta.json")
    missing = short_window_parks_missing(meta)
    if missing and tuple(missing) not in _SHORT_PARK_WARNED:
        _SHORT_PARK_WARNED.add(tuple(missing))
        log.warning("betting_model: SERVE_ATH_PARK is on but data/fa_meta.json's "
                    "park_factors_short_window cannot price %s; those parks fall back "
                    "to the pre-2026-09-11 reading. Refresh it with "
                    "`python fa_export.py --park-blocks` and commit fa_meta.json",
                    ", ".join(missing))
    return park_index_from_meta(meta)


_SHORT_PARK_WARNED: set = set()


def _three_season_index(meta: dict) -> dict:
    out = {}
    for org, v in (meta.get("park_factors") or {}).items():
        try:
            out[str(org)] = float((v or {}).get("runs") or 100) / 100.0
        except (TypeError, ValueError):
            continue
    return out


def park_index_from_meta(meta: dict | None) -> dict:
    """`park_index` on an fa_meta document already in hand, so dfs_export and a
    lab price the SAME venue-correct table without a second reader. Pure."""
    meta = meta if isinstance(meta, dict) else {}
    out = _three_season_index(meta)
    if SERVE_ATH_PARK:
        out.update(short_window_parks(meta.get("park_factors_short_window"),
                                      measured=out))
    return out


def short_window_parks_missing(meta: dict | None) -> list[str]:
    """The SHORT_WINDOW_PARK_ORGS clubs this fa_meta document does NOT price off
    its short-window block while SERVE_ATH_PARK is on: the block is absent, or
    it carries no usable row for the club (or a refused one). [] with the flag
    off, when there is nothing the flag promised. Pure."""
    if not SERVE_ATH_PARK:
        return []
    meta = meta if isinstance(meta, dict) else {}
    got = short_window_parks(meta.get("park_factors_short_window"),
                             measured=_three_season_index(meta))
    return sorted(SHORT_WINDOW_PARK_ORGS - set(got))


# --- the short-sample parks (audit C5-F1, docs/diamond-betting.md 5i-A) ---
# THE DEFECT. `park_index()` reads data/fa_meta.json park_factors, which is
# Savant's DEFAULT view, a 3-season rolling index. That view drops any venue
# without a full window: the 2024-2026 view carries 29 venues and the 2023-2025
# view 28 (read 2026-09-11 off .cache/savant_pf_2026_all.html and _2025_all).
# The Athletics have played at Sutter Health Park since 2025, so every consumer
# of the index has priced every A's home game at a NEUTRAL park: the served
# board, the coefficient fit that sets b3, the vintage backtest and the dark
# props frame. The docstring's "missing parks resolve neutral at lookup, never
# invented" was true, and it was the wrong default for the park whose game
# carried the highest posted total (10.0) on the 2026-09-11 board.
#
# THE MEASURED FACTOR, not a typed one. Savant publishes the venue at shorter
# windows (fa_sources.fetch_savant_park_factors(..., rolling="2"), fetched
# 2026-09-11): 2025-2026 runs 121, woba 110, hr 121, on 34,287 PA; the single
# seasons read 117 (2025, 18,073 PA) and 125 (2026, 15,449 PA). The completed-
# game cache agrees on direction and says it louder: 72 A's home games average
# 11.667 total runs against 8.387 in their 75 road games, a raw ratio of 1.391,
# the highest of the 30 clubs (a raw ratio is not on Savant's player-controlled
# scale and is corroboration only).
#
# THE SHRINK, so a 2-season factor does not ride the coefficient as if it were
# a 3-season one. Variance decomposition over Savant's own single-season
# indices (2018, 2019, 2021-2026; 206 stable venue-season pairs): noise
# variance 32.372 index points^2 at a single-season 17,577 PA, signal variance
# 53.673. The n_pa-implied single-season reliability is 0.6238 against a direct
# season-to-season correlation of 0.6221, so the decomposition reproduces the
# number it can be checked against. Reliability is 0.8360 at the 3-season view's
# median 54,034 PA and 0.7638 at the A's 34,287. b3 was fitted on 3-season
# indices, so the A's deviation is scaled by 0.7638 / 0.8360 = 0.9137, the
# reliability of what b3 was fitted on: 121 -> 119.19, served as 1.1919.
# (Tropicana's 3-season row carried 34,861 PA and was served UNSHRUNK until
# 2026-09-11; the venue audit below brings it under the same shrink.)
#
# SERVED SINCE 2026-09-11, OWNER DECISION 2 ("flip on + refit"), generalised to
# every club the venue audit found on a short venue sample. It moves served
# prices and the value side of a total; it is a data-completeness repair to an
# EXISTING fitted input, not a new feature, so it carries no pre-registered gate
# of its own. It carries the measurement below and shipped in ONE commit with
# the MODEL_VERSION bump (betting_runs_v2). False restores the pre-2026-09-11
# index byte for byte.
#
# THE VENUE AUDIT (owner: "Rays are not playing at Tropicana this year, make
# sure you have the right ballpark for each year"). Every club and season
# 2021-2026: the 2026 venues from gameData.venue in all 2,197 cached regular-
# season feeds, 2021-2025 from Savant's single-season pages (rolling=1, fetched
# 2026-09-11 for section 5i), each against the default 3-season row every
# consumer reads. Findings:
#   * THE RAYS PLAYED 2026 AT TROPICANA FIELD: all 72 home games, venue 12, and
#     StatsAPI's 2026 club venue is Tropicana. 2025 is the year they did not:
#     George M. Steinbrenner Field (venue 2523, 17,419 PA). So the 2024-2026
#     Tropicana row the index serves is the right venue on the wrong sample:
#     34,828 PA, 2024 and 2026 only, 0.645 of the view's 53,975 median. It was
#     served UNSHRUNK at 0.94; it now prices 0.945 (reliability 0.7666 / 0.8360).
#   * THE ATHLETICS, Sutter Health Park (venue 2529) since 2025: 66 of 72 2026
#     home games there, dropped by the 3-season view, priced NEUTRAL until now;
#     now 1.1919 off the rolling=2 row (121 on 34,287 PA), the shrink above.
#   * EVERY OTHER CLUB-SEASON 2021-2026 plays at the venue its row names. The
#     only other short samples are historical and served by no live consumer:
#     Globe Life Field is absent from the 2019-2021 view (TEX 2021) and Rogers
#     Centre carries 0.64 of a window in 2019-2021 and 2020-2022 (TOR played
#     2020-21 in Buffalo and Dunedin).
#   * NEUTRAL SITES, excluded from the club mapping and priced here at the home
#     club's factor because this index is org-keyed: 10 of 2026's 2,197 games
#     (ATH 6 at Las Vegas Ballpark, ARI 2 in Mexico City, MIN 1 at Field of
#     Dreams, MIL 1 at Williamsport). The DFS park leg is venue-keyed and prices
#     them neutral.
#
# WHAT FLIPPING IT CHANGED, measured on the 2026-09-11 slate (15 games, 86
# priced rows, the 17:35 UTC snapshot, old and new pricer on the leaderboards as
# rebuilt at 22:41 UTC):
#   * with the served coefficients held, 12 rows move in TWO games. SEA at ATH:
#     fair total 9.86 -> 11.19 against a 10.0 line, Over 10.0 0.45629 -> 0.63743,
#     edge -0.05606 -> +0.12508, so the total's value side flips from the Under to
#     the Over and the Over clears the 0.06 floor; ATH moneyline 0.44860 ->
#     0.45168; ATH +1.5 0.64014 -> 0.63153. HOU at TBR: fair total 7.67 -> 7.70,
#     Over 7.5 0.49996 -> 0.50497; TBR moneyline 0.62432 -> 0.62406.
#     Floor-clearing sides 23 -> 24; the Pick of the Day is unchanged (PHI at
#     ATL, ATL moneyline 0.75424); the longshot slot stays empty.
#   * THE OVER TILT GETS WORSE, NOT BETTER: positive-edge Overs 12 -> 13 of 15,
#     fair-minus-line mean +0.8757 -> +0.9729. The board-wide lean is the Poisson
#     centre (section 7f), which this flag does not touch.
#   * THE REFIT (`build_context` fits b0..b4 through this seam, together with the
#     two-way starter admission of the same commit), on the 2,200-game cache: b3
#     3.472888 -> 3.934482, b0 4.477487 -> 4.449446, b1 0.250996 -> 0.247453, b2
#     -0.312974 -> -0.309139, b4 0.047531 -> 0.048185; home_field_runs_adj 0.2149
#     -> 0.2072, diff_shrink 0.80 -> 0.82, the fitted dispersion alpha 0.28122 ->
#     0.27929 (the served context: b3 3.473080). The omission was ATTENUATING b3:
#     72 A's home games that scored like a 1.39 park were coded neutral. With all
#     three v2 changes and the refit, every row on the board moves: SEA at ATH
#     11.30, Over 0.65094, edge +0.13859; HOU at TBR 7.62; the gap mean is
#     +0.9321; four value sides flip (LAA at WSN and KCR at BOS runlines to the
#     home side, PHI at ATL total to the Under, SEA at ATH total to the Over);
#     floor-clearing sides 23 -> 21; the headline is still ATL moneyline, 0.75543,
#     edge 0.12933.
#   * CACHED SLATES (27 odds snapshots re-priced on today's inputs, 425 games):
#     108 rows move in 18 games (8 A's and 10 Rays home games), 7 value sides
#     flip, floor-clearing sides 605 -> 608, no published slot changes.
#   * THE TEAM FIT AND DFS read the same shrink. The FA team fit's park score for
#     an A's hitter goes 0.500 -> 0.736 and for an A's pitcher 0.500 -> 0.264
#     (fit weight 0.05, so a member-club fit moves at most 0.0118; of the 12
#     members on the A's served list none gains the A's in his own top three,
#     and the list reorders, its three starters falling from 0.532 / 0.532 /
#     0.529 to 0.520 / 0.520 / 0.517, below the hitters; the rest of the class
#     moves on the next FA export within the same bound); a Rays score moves by
#     at most 0.013. DFS: the SEA at ATH and HOU at TBR
#     legs move to 1.192 and 0.945, 56 of 409 priced rows, -1.73 to +1.77 DK
#     points.
#   * THE VINTAGE PATH MOVES NOTHING YET: all 37 records (through 2026-09-10)
#     predate schema 5, carry no `parks_short_window` block, and keep pricing the
#     A's neutral and the Rays at 0.94. That is the park precedent, stated, not
#     repaired. The first record to carry the block is the first nightly after
#     data/fa_meta.json carries it (see `park_index`).
#   * Blast radius of the A's half, from the first (2026-09-11 BET2) measurement
#     that this block supersedes: 72 completed A's home games (55 in the vintage
#     fit half before the 2026-08-01 split, 17 after), 10 distinct A's home
#     events in the cached odds snapshots, 7 shadow-ledger rows. ZERO served
#     props numbers: props_fair_lines carries no park term. The dark props
#     frame (1,494 batter-games at Sutter) reads fa_meta park_factors and is
#     untouched by this flag.
SERVE_ATH_PARK = True
# The clubs the flag may reach. An explicit list, not "whatever the short view
# publishes": a flag whose effect grows by itself the day another club moves is
# a flag whose measured effect is no longer the one written above.
# test_betting_ballpark holds this list equal to the clubs fa_meta's short-window
# block carries, so a club that moves fails a test instead of joining silently.
SHORT_WINDOW_PARK_ORGS = frozenset({"ATH", "TBR"})
# The shrink constants, measured 2026-09-11 (see above; the script and its
# output are in the section 5i-A receipt). Index points are Savant's 100 scale.
PARK_INDEX_SIGNAL_VAR = 53.673
PARK_INDEX_NOISE_VAR_REF = 32.372
PARK_INDEX_NOISE_REF_PA = 17577.0
PARK_INDEX_3YR_REF_PA = 54034.0


def park_index_reliability(n_pa: float) -> float:
    """Reliability of a Savant park runs index measured on `n_pa` plate
    appearances: signal / (signal + noise), noise scaling as 1 / n_pa. 0 for a
    non-positive sample, which prices neutral."""
    try:
        n = float(n_pa)
    except (TypeError, ValueError):
        return 0.0
    if not n > 0:
        return 0.0
    noise = PARK_INDEX_NOISE_VAR_REF * PARK_INDEX_NOISE_REF_PA / n
    return PARK_INDEX_SIGNAL_VAR / (PARK_INDEX_SIGNAL_VAR + noise)


def short_window_park_value(row: dict | None) -> float | None:
    """One short-window Savant row -> the runs index / 100 the model would price.

    The deviation from neutral is scaled by the row's reliability relative to
    the 3-season view b3 was fitted on, capped at 1 so a long window is never
    stretched. None for a row with no usable runs index or sample."""
    if not isinstance(row, dict):
        return None
    try:
        runs = float(row.get("runs"))
    except (TypeError, ValueError):
        return None
    k = short_window_shrink(row.get("n_pa"))
    if k is None:
        return None
    return round(1.0 + k * (runs - 100.0) / 100.0, 4)


def short_window_shrink(n_pa) -> float | None:
    """The factor a park index deviation measured on `n_pa` plate appearances
    is scaled by before it prices: its reliability over the reliability of the
    3-season view b3 was fitted on, capped at 1 so a long window is never
    stretched. None for a non-positive or unreadable sample. One definition for
    the betting model and fa_fit's team-fit park component."""
    k = park_index_reliability(n_pa) / park_index_reliability(PARK_INDEX_3YR_REF_PA)
    if not k > 0:
        return None
    return min(1.0, k)


def short_window_parks(block: dict | None, *, measured: dict | None = None,
                       exclude=()) -> dict[str, float]:
    """{org: shrunk runs index / 100} for the SHORT_WINDOW_PARK_ORGS a short-
    window block carries. Reads the fa_meta shape ({"orgs": {org: row}}) and the
    vintage shape ({org: row}) alike. Pure: the flag is the CALLER's check.

    `measured` is the 3-season index the caller already serves ({org: runs /
    100}). A club absent from it (the Athletics) takes its shrunk short row. A
    club PRESENT in it (the Rays) takes the shrunk value only when the short
    row IS that same measurement, the 3-season row itself resting on a short
    venue sample: then the served number moves toward neutral by that row's own
    sample and can never move anywhere else. A row carrying a different index
    (another window's number) is refused, so a short window can never replace a
    measured 3-season factor. `exclude` is the pre-2026-09-11 keyword: orgs in it
    are skipped outright.

    A row whose `venue_match` is False (fa_fit's venue check: Savant's venue is
    not the one StatsAPI says the club plays in) is refused outright; a row
    written before the check existed carries no key and is read as before."""
    if not isinstance(block, dict):
        return {}
    rows = block.get("orgs") if isinstance(block.get("orgs"), dict) else block
    measured = measured if isinstance(measured, dict) else {}
    out: dict[str, float] = {}
    for org, row in rows.items():
        o = str(org)
        if o not in SHORT_WINDOW_PARK_ORGS or o in exclude:
            continue
        if isinstance(row, dict) and row.get("venue_match") is False:
            continue
        v = short_window_park_value(row)
        if v is None:
            continue
        if o in measured:
            try:
                same = abs(float(row.get("runs")) / 100.0 - float(measured[o])) < 1e-6
            except (TypeError, ValueError):
                same = False
            if not same:
                continue
        out[o] = v
    return out


# --- park by bat side (DARK, docs/diamond-betting.md sections 5i-B and 5i-C) --
# Source reliability of the per-venue L minus R split at Savant's 3-season
# window, measured 2026-09-11 from Savant's own single-season pages alone (2019,
# 2021-2026; 176 stable venue-season pairs; NO game outcome was read): runs
# split season-to-season r 0.0065 -> 3-season 0.0191; HR split r 0.1406 ->
# 3-season 0.3293. The pre-registered candidates scale the hand deviation by
# these, fixed BEFORE any candidate number exists; re-tuning them against
# outcomes would be fitting the feature to the eval window.
PARK_HAND_SPLIT_RELIABILITY = {"runs": 0.0191, "hr": 0.3293}


def lineup_park_factor(park_all: float | None, by_hand: dict | None,
                       lhb_share: float | None, *, stat: str = "runs") -> float | None:
    """DARK. The section 5i-B candidate park term for ONE scoring side.

        park_all + rel * (s * (L - park_all) + (1 - s) * (R - park_all))

    `park_all` is the served park index (runs / 100) of the home park, `by_hand`
    that park's {"L": x, "R": y} on the same scale, `lhb_share` the batting
    lineup's left-handed PA share against the opposing probable's hand, and
    `rel` PARK_HAND_SPLIT_RELIABILITY[stat]. None when any input is missing: the
    lab prices that side on `park_all` and counts it, it never guesses a hand.
    The permuted twin the gate requires is this function at 1 - lhb_share.

    NOTHING SERVED CALLS THIS. expected_runs, the fit and the export read the
    one park term they always read; this exists so the gate lab computes the
    candidate with one definition."""
    if park_all is None or lhb_share is None or not isinstance(by_hand, dict):
        return None
    try:
        s = float(lhb_share)
        lv_, rv_ = float(by_hand["L"]), float(by_hand["R"])
        pa = float(park_all)
    except (KeyError, TypeError, ValueError):
        return None
    if not 0.0 <= s <= 1.0:
        return None
    rel = PARK_HAND_SPLIT_RELIABILITY[stat]
    return pa + rel * (s * (lv_ - pa) + (1.0 - s) * (rv_ - pa))


def parks_by_hand_from_vintage(rec: dict | None) -> dict | None:
    """DARK. A schema-5 record's {org: {"L", "R", "hr_L", "hr_R"}} block, or None
    when the record predates it or stored it null. Never filled from fa_meta."""
    blk = (rec or {}).get("parks_by_hand")
    return blk if isinstance(blk, dict) and blk else None


# ---------------------------------------------------------------------------
# the vintage read path
# ---------------------------------------------------------------------------
# One warning per process, not one per game. A 1,705-game backtest with no
# vintages would otherwise emit 1,705 identical lines and bury everything else
# in the nightly log.
_VINTAGE_FALLBACK_WARNED = False
# {vintage_date: (teams, starters, parks|None)}. A vintage is reduced once and
# reused by every game it prices; without this a backtest rebuilds the same
# 30-team standardization fifteen times a day. `parks` is None (never {}) when
# the record predates the park column: see `parks_from_vintage`.
_VINTAGE_CACHE: dict[str, tuple[dict, dict, dict | None]] = {}

# The park index a game gets when its vintage carries no park column. Empty is
# NEUTRAL here and only here, because `expected_runs` already resolves a missing
# org to 1.00 (ATH has no Savant park entry), so an empty index makes the park
# term drop out of the regression entirely. It is a named constant rather than a
# bare {} at three call sites so the fallback is greppable, and every game that
# takes it is counted into the vintage block's `park_basis`.
NEUTRAL_PARK_INDEX: dict[str, float] = {}


def reset_vintage_cache() -> None:
    """Drop the memoized vintages, here and in the store. Tests that write
    vintages into a tmp dir call this; the pipeline never needs it."""
    global _VINTAGE_FALLBACK_WARNED
    _VINTAGE_CACHE.clear()
    _VINTAGE_FALLBACK_WARNED = False
    lv = _vintage_module()
    if lv:
        lv.reset_cache()


def _vintage_module():
    try:
        import leaderboard_vintages
        return leaderboard_vintages
    except Exception:                                            # pragma: no cover
        return None


def team_inputs_from_vintage(rec: dict) -> dict:
    """A stored vintage record -> the same {org: {...}} shape `team_inputs`
    returns, through the same standardization."""
    cols = list(rec.get("team_columns") or ())
    try:
        i_off = cols.index("offense_plus")
        i_rot = cols.index("rotation_plus")
        i_pen = cols.index("bullpen_plus")
        i_sip = cols.index("starter_ip")
        i_rip = cols.index("relief_ip")
    except ValueError:                                           # pragma: no cover
        return {}
    # The dark columns of every schema, by the RECORD'S OWN positions. A record
    # of a lower schema simply lacks the higher schema's names, so each of those
    # reads None: the explicit stated fallback, never a silent zero, and never a
    # fill from live files.
    dark_pos = {c: cols.index(c) for c in DARK_TEAM_COLUMNS if c in cols}
    off, rots, pens, sip, rip, extras = {}, {}, {}, {}, {}, {}
    for org, row in (rec.get("teams") or {}).items():
        if not isinstance(row, list) or len(row) <= max(i_off, i_rot, i_pen, i_sip, i_rip):
            continue
        if row[i_off] is None or row[i_rot] is None or row[i_pen] is None:
            continue
        off[org] = float(row[i_off])
        rots[org] = float(row[i_rot])
        pens[org] = float(row[i_pen])
        sip[org] = float(row[i_sip] or 0.0)
        rip[org] = float(row[i_rip] or 0.0)
        extras[org] = {c: (row[dark_pos[c]]
                           if c in dark_pos and dark_pos[c] < len(row) else None)
                       for c in DARK_TEAM_COLUMNS}
    return _assemble_team_inputs(off, rots, pens, sip, rip, extras)


def starter_inputs_from_vintage(rec: dict) -> dict:
    """A stored vintage record -> the same {mlbam: {...}} shape
    `starter_inputs` returns. Names are not stored (the model never reads
    one), so the display name comes back None."""
    cols = list(rec.get("pitcher_columns") or ())
    try:
        i_plus = cols.index("plus")
        i_ip = cols.index("ip_per_gs")
        i_org = cols.index("org")
        i_role = cols.index("role")
    except ValueError:                                           # pragma: no cover
        return {}
    # Schema-3 dark column; a record written before it reads None, stated.
    i_thr = cols.index("throws") if "throws" in cols else None
    out = {}
    for mid, row in (rec.get("pitchers") or {}).items():
        if not isinstance(row, list) or len(row) <= max(i_plus, i_ip, i_org, i_role):
            continue
        if row[i_plus] is None:
            continue
        try:
            key = int(mid)
        except (TypeError, ValueError):
            continue
        out[key] = {"mlbam": key, "name": None, "org": row[i_org],
                    "sem_plus": float(row[i_plus]),
                    "ip_per_gs": float(row[i_ip]) if row[i_ip] else None,
                    "role": row[i_role] or "SP",
                    "throws": (row[i_thr] if (i_thr is not None
                                              and i_thr < len(row)) else None)}
    return out


def parks_from_vintage(rec: dict) -> dict | None:
    """A stored vintage record -> {org: runs index / 100}, or None when the
    record has no park column.

    NONE IS THE SENTINEL AND IT MATTERS. `park_index()` reads the LIVE
    data/fa_meta.json, whose factors are `fa_fit.park_factors(CLASS_YEAR - 1)`,
    i.e. the IN-PROGRESS season. Handing that to a vintage-mode game lets the
    eval window contribute to the park index used to fit and to price it, which
    is the leak leaderboard_vintages exists to close and which the mode label
    was denying. Returning {} here would be just as bad in the other direction:
    the caller could not tell "no park column" from "a league of neutral parks",
    so it could not mark the games. None forces the caller to choose, out loud."""
    parks = (rec or {}).get("parks")
    if not isinstance(parks, dict) or not parks:
        return None
    out: dict[str, float] = {}
    for org, v in parks.items():
        try:
            out[str(org)] = float(v)
        except (TypeError, ValueError):
            continue
    # SERVE_ATH_PARK reaches the vintage path through the record's OWN dated
    # block (schema 5), with the same shrink the live path uses. A record that
    # predates the block keeps the Athletics neutral and the Rays at their raw
    # 3-season factor; nothing is filled from today's fa_meta, which would be
    # the leak this function exists to refuse.
    if out and SERVE_ATH_PARK:
        out.update(short_window_parks((rec or {}).get("parks_short_window"),
                                      measured=dict(out)))
    return out or None


def inputs_as_of(game_date: str | None, *, allow_fallback: bool = True) -> dict:
    """The team and pitcher inputs for a game on `game_date`, from the newest
    vintage whose knowledge cutoff is STRICTLY BEFORE it.

    Returns a bundle, always, with the provenance attached:

        {"teams": {...}, "starters": {...}, "parks": {...}|None,
         "parks_resolved": bool,
         "source": "vintage"|"live-leaderboards",
         "vintage_date": "2026-08-05"|None, "covers_through": ...|None,
         "contaminated": bool, "note": "..."}

    `parks` is None with `parks_resolved: False` when the vintage predates the
    park column. It is NOT quietly filled from `park_index()`: that index is the
    in-progress season's, so filling it would put the leak back on the one input
    that had it. The caller prices those games on NEUTRAL_PARK_INDEX and counts
    them.

    THE FALLBACK IS LOUD ON PURPOSE. With no vintage for the date this returns
    the LIVE season-to-date leaderboards, which contain the game being priced,
    and says so: `contaminated: True` plus a once-per-process log warning. The
    fallback is the current behaviour of the whole module, so nothing regresses
    while the store fills up; what changes is that a caller can no longer be
    unaware of which one it got. `allow_fallback=False` returns an empty bundle
    instead, which is what the vintage backtest uses so it cannot accidentally
    grade a game on contaminated features."""
    global _VINTAGE_FALLBACK_WARNED
    lv = _vintage_module()
    rec = None
    if lv and game_date:
        try:
            rec = lv.as_of(game_date)
        except Exception:                                        # pragma: no cover
            rec = None
    if rec:
        vd = rec.get("vintage_date")
        if vd not in _VINTAGE_CACHE:
            _VINTAGE_CACHE[vd] = (team_inputs_from_vintage(rec),
                                  starter_inputs_from_vintage(rec),
                                  parks_from_vintage(rec))
        teams, starters, parks = _VINTAGE_CACHE[vd]
        note = (f"priced on the leaderboard vintage of {vd} "
                f"(covers through {rec.get('covers_through')})")
        if parks is None:
            note += ("; that record carries no park column, so the park term must be "
                     "taken as neutral rather than from the live index")
        # Which basis every dark-capture column rides on for this record
        # (populated, stated null, or predates-the-column). Read off the
        # record itself; the live files are never consulted to fill a column
        # the vintage lacks, which would be the exact leak this store closes.
        try:
            fb = lv.feature_basis(rec) if lv else None
        except Exception:                                        # pragma: no cover
            fb = None
        return {"teams": teams, "starters": starters, "parks": parks,
                "parks_resolved": parks is not None, "source": "vintage",
                "vintage_date": vd, "covers_through": rec.get("covers_through"),
                "feature_basis": fb,
                "contaminated": False, "note": note}
    if not allow_fallback:
        return {"teams": {}, "starters": {}, "parks": None, "parks_resolved": False,
                "source": "none", "feature_basis": None,
                "vintage_date": None, "covers_through": None, "contaminated": False,
                "note": f"no leaderboard vintage exists strictly before {game_date}"}
    if not _VINTAGE_FALLBACK_WARNED:
        _VINTAGE_FALLBACK_WARNED = True
        log.warning("betting_model: no leaderboard vintage strictly before %s; "
                    "falling back to the LIVE season-to-date leaderboards. Any "
                    "number produced from this read is leakage-contaminated. Run "
                    "leaderboard_vintages.snapshot() nightly to fix it.", game_date)
    return {"teams": team_inputs(), "starters": starter_inputs(),
            "parks": park_index(), "parks_resolved": True,
            "source": "live-leaderboards", "vintage_date": None,
            "feature_basis": None,
            "covers_through": None, "contaminated": True,
            "note": ("no vintage exists strictly before this date, so the live "
                     "season-to-date leaderboards and the live park index were used; "
                     "they contain the game being priced and this number is "
                     "contaminated")}


def _vintage_resolver():
    """(resolve, stats).

    `resolve(game) -> (teams, starters, parks) or None`. None means the game has
    no vintage and must be skipped rather than graded on live leaderboards.

    THE THIRD ELEMENT IS THE FIX FOR THE PARK LEAK. It used to be a 2-tuple and
    the caller reached past it for `park_index()`, the live in-progress-season
    index, in both the coefficient fit and the pricing. A vintage with no park
    column now yields NEUTRAL_PARK_INDEX and the date is recorded in `stats`, so
    the eval artifact can say how many games were graded with the park term off
    instead of quietly graded with a leaking one.

    Memoized by GAME DATE inside the closure. The solvers evaluate the whole
    schedule dozens of times over a grid, and every game on a slate resolves
    to the same vintage, so this is the difference between a backtest that
    finishes and one that does not. `stats["park_source_by_date"]` is therefore
    keyed by date too; per-GAME counts are derived by the caller, which is the
    only place that knows the fit/eval split."""
    by_date: dict[str, tuple | None] = {}
    stats: dict = {"park_source_by_date": {}, "feature_basis_by_date": {}}

    def _resolve(g):
        d = g.get("date")
        if d not in by_date:
            b = inputs_as_of(d, allow_fallback=False)
            if b["source"] == "vintage" and b["teams"]:
                parks = b.get("parks")
                if parks is None:
                    parks = NEUTRAL_PARK_INDEX
                    stats["park_source_by_date"][d] = "neutral"
                else:
                    stats["park_source_by_date"][d] = "vintage"
                # The dark-capture marking, per date (a slate shares a vintage,
                # exactly like the park). Per-GAME counts are derived by the
                # caller, which knows the fit/eval split; see _feature_basis.
                stats["feature_basis_by_date"][d] = b.get("feature_basis") or {}
                by_date[d] = (b["teams"], b["starters"], parks)
            else:
                by_date[d] = None
        return by_date[d]
    return _resolve, stats


# ---------------------------------------------------------------------------
# fitted (or literature) coefficients
# ---------------------------------------------------------------------------
def coefficients() -> dict:
    """The live run-scoring coefficients. Fitted set if data/betting_model_context.json
    exists, literature priors otherwise. Callers print `source` on the page."""
    ctx = _load_json(CONTEXT_PATH) or {}
    c = ctx.get("coefficients")
    if isinstance(c, dict) and all(k in c for k in ("b0", "b1", "b2", "b3", "b4")):
        return c
    return dict(LITERATURE_COEFFS)


def league_context() -> dict:
    ctx = _load_json(CONTEXT_PATH) or {}
    return {
        "season": ctx.get("season"),
        "n_games": ctx.get("n_games") or 0,
        "lg_rpg": ctx.get("lg_rpg"),
        "home_win_rate": ctx.get("home_win_rate"),
        "extra_inning_home_rate": ctx.get("extra_inning_home_rate_shrunk") or LITERATURE_TIE_HOME,
        "home_logit_offset": float(ctx.get("home_logit_offset") or 0.0),
        "run_dispersion_alpha": run_dispersion_alpha(),
        "generated_at": ctx.get("generated_at"),
        "source": (coefficients() or {}).get("source"),
    }


def run_dispersion_alpha() -> float | None:
    """The SERVED NB2 dispersion, or None for Poisson.

    A missing key, a null, or a non-positive value all mean Poisson, so a
    checkout with an old context file prices exactly as it did before. The
    fitted value lives beside it under `run_dispersion_alpha_fitted` and is a
    MEASUREMENT, published whether or not it is served."""
    ctx = _load_json(CONTEXT_PATH) or {}
    a = ctx.get("run_dispersion_alpha")
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    return a if a > 0 else None


def _alpha_to_r(alpha: float | None) -> float | None:
    """alpha -> the NB2 size parameter r = 1/alpha. None (Poisson) for a
    missing or non-positive alpha, so every call site has one switch."""
    if alpha is None:
        return None
    try:
        a = float(alpha)
    except (TypeError, ValueError):
        return None
    return (1.0 / a) if a > 0 else None


# ---------------------------------------------------------------------------
# probability calibration (B5, docs/diamond-betting.md section 11b)
# ---------------------------------------------------------------------------
_PROB_EPS = 1e-6


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _logit(p: float) -> float:
    p = min(max(float(p), _PROB_EPS), 1.0 - _PROB_EPS)
    return math.log(p / (1.0 - p))


def fit_platt(ps: list[float], ys: list, *, max_iter: int = 60,
              tol: float = 1e-10) -> tuple[float, float] | None:
    """(a, b) for p' = sigmoid(a*logit(p) + b), by MLE. None when it cannot
    be fitted honestly.

    Newton-Raphson on the two-parameter logistic likelihood: deterministic (a
    fixed start at the identity (1, 0), a fixed iteration budget, no RNG), no
    library, and the exact gradient/Hessian, so two runs on the same rows
    return the same digits. `ys` may be fractional: the minimizer of expected
    log loss under fractional targets is the exact (a, b) that generated them,
    which is what makes the recovery test in test_betting_platt.py exact
    rather than statistical.

    Returns None on: fewer than 2 rows, a singular Hessian (all inputs equal),
    a non-finite step, or a solution walking past |a| or |b| of 50, which is
    the separable-data regime where the MLE does not exist and serving the
    diverging iterate would be serving an artifact of the iteration cap."""
    n = len(ps or [])
    if n < 2 or len(ys) != n:
        return None
    xs = [_logit(p) for p in ps]
    a, b = 1.0, 0.0
    for _ in range(max_iter):
        g_a = g_b = h_aa = h_ab = h_bb = 0.0
        for x, y in zip(xs, ys):
            q = _sigmoid(a * x + b)
            d = q - float(y)
            w = max(q * (1.0 - q), 1e-12)
            g_a += d * x
            g_b += d
            h_aa += w * x * x
            h_ab += w * x
            h_bb += w
        det = h_aa * h_bb - h_ab * h_ab
        if not math.isfinite(det) or abs(det) < 1e-12:
            return None
        da = (h_bb * g_a - h_ab * g_b) / det
        db = (h_aa * g_b - h_ab * g_a) / det
        a -= da
        b -= db
        if not (math.isfinite(a) and math.isfinite(b)) or abs(a) > 50 or abs(b) > 50:
            return None
        if abs(da) < tol and abs(db) < tol:
            break
    return a, b


def apply_platt(p: float, a: float, b: float) -> float:
    """One probability through the map, clipped inside (0, 1) so a downstream
    log loss can never meet an exact 0 or 1."""
    q = _sigmoid(a * _logit(p) + b)
    return min(max(q, _PROB_EPS), 1.0 - _PROB_EPS)


def served_platt() -> tuple[float, float] | None:
    """The SERVED calibration map, or None for identity.

    The flag is checked FIRST, before any file is read: while
    SERVE_PROB_CALIBRATION is False this returns None unconditionally, so a
    stray `prob_calibration` key in an old context file cannot calibrate a
    price, and the hot solver loops pay no extra file read."""
    if not SERVE_PROB_CALIBRATION:
        return None
    ctx = _load_json(CONTEXT_PATH) or {}
    pc = ctx.get("prob_calibration")
    if not isinstance(pc, dict):
        return None
    try:
        return float(pc["a"]), float(pc["b"])
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# the regulation-tie atom (L14-01), read in ONE place
# ---------------------------------------------------------------------------
def split_tie_atom(dist: dict, tie_home: float,
                   runline_split: tuple | None = None) -> dict:
    """THE ONE READING OF THE d == 0 ATOM, for every market priced off the margin.

    `dist` is P(home runs - away runs = d). d == 0 is a game level after nine,
    which MLB settles in extra innings. `tie_home` is the share of that atom the
    home side wins, the moneyline's split. `runline_split` is the pair
    (P(home by 2+ | home wins in extras), P(away by 2+ | away wins in extras));
    None or (0, 0) is the shipped whole-atom construction, in which every tie is
    a +1.5 cover for both sides. See SERVE_RUNLINE_TIE_SPLIT.

    Returns, UNROUNDED:
      p_tie             dist[0]
      p_home            P(d > 0)   + p_tie * tie_home                   moneyline
      p_home_minus_1_5  P(d >= 2)  + p_tie * tie_home * c_home          runline
      p_away_minus_1_5  P(d <= -2) + p_tie * (1 - tie_home) * c_away    runline
    The +1.5 sides are the complements of the opposite -1.5 sides, so the
    pair-sums-to-1 invariant is untouched.

    COHERENT BY CONSTRUCTION. The runline's share of the tie is the moneyline's
    share times a conditional in [0, 1], so p_home_minus_1_5 can never exceed
    p_home and p_away_minus_1_5 can never exceed 1 - p_home, for any inputs. An
    unconditional P(home by 2+ | extras) set beside a separately shrunk tie_home
    does not have that property on a thin fit window.

    BIT FOR BIT ON THE SHIPPED PATH. With a (0, 0) split the arithmetic is the
    pre-2026-09-11 expression verbatim: the tie term is skipped, not added as a
    zero, so no served number moves while SERVE_RUNLINE_TIE_SPLIT is False.

    Raises ValueError on a tie_home or a conditional outside [0, 1], NaN
    included: `not 0 <= nan <= 1` is True, so a NaN cannot slide through as a
    truthy probability."""
    th = float(tie_home)
    if not 0.0 <= th <= 1.0:
        raise ValueError(f"tie_home must be a probability, got {tie_home!r}")
    if runline_split is None:
        c_home, c_away = 0.0, 0.0
    else:
        c_home, c_away = float(runline_split[0]), float(runline_split[1])
    for c in (c_home, c_away):
        if not 0.0 <= c <= 1.0:
            raise ValueError(f"runline tie split must be in [0, 1], got {runline_split!r}")
    p_tie = dist.get(0, 0.0)
    p_home_reg = sum(p for d, p in dist.items() if d > 0)
    p_home = p_home_reg + p_tie * th
    p_home_minus15 = sum(p for d, p in dist.items() if d >= 2)
    p_away_minus15 = sum(p for d, p in dist.items() if d <= -2)
    if c_home:
        p_home_minus15 = p_home_minus15 + p_tie * th * c_home
    if c_away:
        p_away_minus15 = p_away_minus15 + p_tie * (1.0 - th) * c_away
    return {"p_tie": p_tie, "p_home": p_home,
            "p_home_minus_1_5": p_home_minus15,
            "p_away_minus_1_5": p_away_minus15}


def _runline_prices(atom: dict) -> dict:
    """The four published runline probabilities off one `split_tie_atom` result,
    rounded the way the board has always rounded them."""
    return {
        "p_home_minus_1_5": round(atom["p_home_minus_1_5"], 5),
        "p_away_minus_1_5": round(atom["p_away_minus_1_5"], 5),
        "p_home_plus_1_5": round(1.0 - atom["p_away_minus_1_5"], 5),
        "p_away_plus_1_5": round(1.0 - atom["p_home_minus_1_5"], 5),
    }


def _runline_split_pair(blk) -> tuple[float, float] | None:
    """(c_home, c_away) out of a context block, or None when it is absent,
    malformed or outside [0, 1]. One parser for the served key and the fitted
    one, so the two cannot disagree about what a valid split is."""
    if not isinstance(blk, dict):
        return None
    try:
        h = float(blk["home_by_2plus_given_home_win"])
        a = float(blk["away_by_2plus_given_away_win"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0.0 <= h <= 1.0 and 0.0 <= a <= 1.0):
        return None
    return h, a


def served_runline_tie_split() -> tuple[float, float] | None:
    """The SERVED runline split of the tie atom, or None for the whole-atom
    construction.

    The flag is checked FIRST, before any file is read, the served_platt
    pattern: while SERVE_RUNLINE_TIE_SPLIT is False this returns None
    unconditionally, so a stray `extra_inning_runline_split` key in an old or
    hand-edited context file cannot reprice the runline, and the solver loops
    pay no extra file read."""
    if not SERVE_RUNLINE_TIE_SPLIT:
        return None
    ctx = _load_json(CONTEXT_PATH) or {}
    pair = _runline_split_pair(ctx.get("extra_inning_runline_split"))
    if pair is None:
        # A context written before the flip carries a null served key beside
        # the measurement. With the flag on, the served split IS that
        # measurement (build_context writes one into the other), so the price
        # reads it rather than falling back to the whole atom on a context the
        # refit has not yet rewritten.
        pair = _runline_split_pair(ctx.get("extra_inning_runline_split_fitted"))
    return pair


def context_model_version() -> str | None:
    """The MODEL_VERSION stamped on the served context by the `build_context`
    that wrote it, or None when there is no context. A context whose version
    is not MODEL_VERSION holds coefficients fitted by a different pricer:
    betting_export stamps it beside every row so the ledger can tell them
    apart, and logs the mismatch."""
    ctx = _load_json(CONTEXT_PATH) or {}
    v = ctx.get("model_version")
    return str(v) if v else None


def fitted_runline_tie_split() -> dict | None:
    """The MEASUREMENT block (`extra_inning_runline_split_fitted`), published
    whether or not it is served, the run_dispersion_alpha_fitted convention.
    None when the context predates it or carries a malformed block. The export
    reads it to stamp each runline row's `tie_atom` disclosure (a zero shift
    while the split is served, what the split would do while it is not), and
    `served_runline_tie_split` prices off it when a context written before the
    2026-09-11 flip carries it beside a null served key."""
    ctx = _load_json(CONTEXT_PATH) or {}
    blk = ctx.get("extra_inning_runline_split_fitted")
    return blk if _runline_split_pair(blk) is not None else None


# ---------------------------------------------------------------------------
# the total level (BET1), read in ONE place
# ---------------------------------------------------------------------------
def _total_level_value(v) -> float | None:
    """A recentre constant out of a context value, or None when it is absent,
    not a finite number, or outside TOTAL_LEVEL_BOUNDS. One parser for the
    served key and the fitted block, so they cannot disagree about validity."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    lo, hi = TOTAL_LEVEL_BOUNDS
    if not math.isfinite(x) or not lo <= x <= hi:
        return None
    return x


def served_total_level() -> float | None:
    """The SERVED total recentre in runs, or None for none.

    The flag is checked FIRST, before any file is read, the served_platt
    pattern: while SERVE_TOTAL_LEVEL is False this returns None
    unconditionally, so a stray `total_level` key in an old or hand-edited
    context file cannot reprice a total."""
    if not SERVE_TOTAL_LEVEL:
        return None
    ctx = _load_json(CONTEXT_PATH) or {}
    return _total_level_value(ctx.get("total_level"))


def fitted_total_level() -> dict | None:
    """The MEASUREMENT block (`total_level_fitted`), published whether or not it
    is served. None when the context predates it or its constant is invalid."""
    ctx = _load_json(CONTEXT_PATH) or {}
    blk = ctx.get("total_level_fitted")
    if not isinstance(blk, dict) or _total_level_value(blk.get("centre")) is None:
        return None
    return blk


def _poisson_over(lam: float, line: float) -> float:
    """P(total > line) for a Poisson total, clipped off 0 and 1 so a log loss
    can never meet an exact 0. Integer lines are scored as strict Over (a push
    counts against it), which is all the fit grid needs: every grid line is a
    half point."""
    need = math.floor(line) + 1
    pm, cdf = math.exp(-lam), 0.0
    for k in range(need):
        if k:
            pm *= lam / k
        cdf += pm
    return min(max(1.0 - cdf, _PROB_EPS), 1.0 - _PROB_EPS)


def _total_level_losses(rows, delta: float, lines=None) -> list[float]:
    """Per-game total log loss summed over the grid, at recentre `delta`.
    `rows` is [(model total mean, actual total)]. The shifted mean is floored
    at 0.5 runs so a large negative search step cannot ask for a negative
    Poisson mean; no fitted constant on any window comes near it."""
    lines = tuple(lines if lines is not None else TOTAL_LEVEL_LINES)
    out = []
    for m, y in rows:
        lam = max(0.5, float(m) + delta)
        s = 0.0
        for L in lines:
            p = _poisson_over(lam, L)
            s -= math.log(p) if y > L else math.log(1.0 - p)
        out.append(s)
    return out


def fit_total_level(rows, *, lines=None, tol: float = 1e-5) -> dict | None:
    """Both recentre arms of TOTAL_LEVEL_GATE_CRITERIA on one fit window.

    `rows` is [(model total mean, actual total)] over the FIT window and nothing
    else. Returns None with fewer than two rows.

      centre  argmin of the mean summed over/under log loss at `lines`
              (TOTAL_LEVEL_LINES by default), golden-section on
              TOTAL_LEVEL_BOUNDS. Deterministic: a fixed contraction on a fixed
              interval, so two runs on the same rows return the same digits.
      mean    mean actual total minus mean model total. The 2026-09-05 plan's
              literal candidate, published beside the served one so the reader
              can see how little of the Over skew a mean recentre touches.

    `per_line` carries the observed Over rate and the mean model P(over) under
    the incumbent and both arms, which is the whole argument in one table: the
    mean is right and the Poisson centre is not."""
    rows = [(float(m), float(y)) for m, y in (rows or [])]
    n = len(rows)
    if n < 2:
        return None
    lines = tuple(lines if lines is not None else TOTAL_LEVEL_LINES)

    def f(d):
        return sum(_total_level_losses(rows, d, lines)) / n

    lo, hi = TOTAL_LEVEL_BOUNDS
    inv_phi = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = hi - inv_phi * (hi - lo), lo + inv_phi * (hi - lo)
    f1, f2 = f(x1), f(x2)
    while hi - lo > tol:
        if f1 > f2:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + inv_phi * (hi - lo)
            f2 = f(x2)
        else:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - inv_phi * (hi - lo)
            f1 = f(x1)
    centre = round((lo + hi) / 2.0, 4)
    mean_model = sum(m for m, _ in rows) / n
    mean_actual = sum(y for _, y in rows) / n
    mean_arm = round(mean_actual - mean_model, 4)
    per_line = []
    for L in lines:
        obs = sum(1 for _, y in rows if y > L) / n
        per_line.append({
            "line": L,
            "observed_over": round(obs, 4),
            "model_over_incumbent": round(sum(_poisson_over(m, L) for m, _ in rows) / n, 4),
            "model_over_centre": round(sum(_poisson_over(max(0.5, m + centre), L)
                                           for m, _ in rows) / n, 4),
            "model_over_mean": round(sum(_poisson_over(max(0.5, m + mean_arm), L)
                                         for m, _ in rows) / n, 4),
        })
    ys = sorted(y for _, y in rows)
    mid = n // 2
    median_actual = ys[mid] if n % 2 else (ys[mid - 1] + ys[mid]) / 2.0
    return {
        "centre": centre,
        "mean": mean_arm,
        "n": n,
        "lines": list(lines),
        "mean_model_total": round(mean_model, 4),
        "mean_actual_total": round(mean_actual, 4),
        "median_actual_total": median_actual,
        "log_loss_incumbent": round(f(0.0), 6),
        "log_loss_centre": round(f(centre), 6),
        "log_loss_mean": round(f(mean_arm), 6),
        "per_line": per_line,
    }


def _total_level_rows(games, teams, parks, starters, coeffs, adj, shrink,
                      resolve=None) -> list[tuple]:
    """[(model total mean, actual total, game_pk)] under the given pricer.
    lam_home + lam_away is 2 * mid, which the home adjustment and the
    differential shrink leave untouched by construction; they are passed only
    so the 1.5 / 9.5 lambda clamps bind exactly where the pricer's would."""
    rows = []
    for g in games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        er = expected_runs(g["home_org"], g["away_org"],
                           home_sp=gs.get(g.get("home_sp")),
                           away_sp=gs.get(g.get("away_sp")),
                           teams=gt, parks=gpk, coeffs=coeffs,
                           home_adj=adj, diff_shrink=shrink)
        if not er:
            continue
        rows.append((er["lam_home"] + er["lam_away"],
                     int(g["home_runs"]) + int(g["away_runs"]), g.get("game_pk")))
    return rows


def served_total_dispersion() -> float | None:
    """The SERVED total-scoped alpha_T, or None for the Poisson total. The flag
    is checked FIRST, so a stray context key cannot reprice a total."""
    if not SERVE_TOTAL_DISPERSION:
        return None
    ctx = _load_json(CONTEXT_PATH) or {}
    return _total_dispersion_value(ctx.get("total_dispersion_alpha"))


def _total_dispersion_value(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    lo, hi = TOTAL_DISPERSION_BOUNDS
    return x if (math.isfinite(x) and lo <= x <= hi) else None


def fitted_total_dispersion() -> dict | None:
    """The MEASUREMENT block (`total_dispersion_fitted`), published either way."""
    ctx = _load_json(CONTEXT_PATH) or {}
    blk = ctx.get("total_dispersion_fitted")
    if not isinstance(blk, dict) or _total_dispersion_value(blk.get("alpha")) is None:
        return None
    return blk


def _total_pmf(lam_h: float, lam_a: float, alpha: float | None) -> list[float]:
    """The total pmf off `_score_joint`'s convolution: Poisson sides for alpha
    None, NB2 sides sharing alpha otherwise."""
    return _score_joint(lam_h, lam_a, _alpha_to_r(alpha))[1]


def _pmf_over(tot: list[float], line: float) -> float:
    """P(total > line) off a total pmf, clipped off 0 and 1 (half-point lines)."""
    need = math.floor(line) + 1
    p = sum(tot[need:]) if need < len(tot) else 0.0
    return min(max(p, _PROB_EPS), 1.0 - _PROB_EPS)


def _total_dispersion_losses(rows, alpha: float | None, lines=None) -> list[float]:
    """Per-game total log loss summed over the grid under alpha_T. `rows` is
    [(lam_home, lam_away, actual total)]; alpha None is the served Poisson."""
    lines = tuple(lines if lines is not None else TOTAL_LEVEL_LINES)
    out = []
    for lh, la, y in rows:
        tot = _total_pmf(lh, la, alpha)
        s = 0.0
        for L in lines:
            p = _pmf_over(tot, L)
            s -= math.log(p) if y > L else math.log(1.0 - p)
        out.append(s)
    return out


def fit_total_dispersion(rows, *, lines=None, tol: float = 1e-4) -> dict | None:
    """alpha_T on ONE fit window: argmin of the mean summed over/under log loss at
    the grid, golden-section on TOTAL_DISPERSION_BOUNDS. Deterministic. `per_line`
    carries the observed Over rate and the mean model P(over) under the Poisson
    and under alpha_T."""
    rows = [(float(a), float(b), float(y)) for a, b, y in (rows or [])]
    n = len(rows)
    if n < 2:
        return None
    lines = tuple(lines if lines is not None else TOTAL_LEVEL_LINES)

    def f(a):
        return sum(_total_dispersion_losses(rows, a, lines)) / n

    lo, hi = TOTAL_DISPERSION_BOUNDS
    inv_phi = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = hi - inv_phi * (hi - lo), lo + inv_phi * (hi - lo)
    f1, f2 = f(x1), f(x2)
    while hi - lo > tol:
        if f1 > f2:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + inv_phi * (hi - lo)
            f2 = f(x2)
        else:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - inv_phi * (hi - lo)
            f1 = f(x1)
    alpha = round((lo + hi) / 2.0, 5)
    per_line = []
    pois = [_total_pmf(a, b, None) for a, b, _ in rows]
    nb = [_total_pmf(a, b, alpha) for a, b, _ in rows]
    for L in lines:
        per_line.append({
            "line": L,
            "observed_over": round(sum(1 for *_, y in rows if y > L) / n, 4),
            "model_over_poisson": round(sum(_pmf_over(t, L) for t in pois) / n, 4),
            "model_over_nb": round(sum(_pmf_over(t, L) for t in nb) / n, 4),
        })
    return {"alpha": alpha, "n": n, "lines": list(lines),
            "log_loss_poisson": round(f(None), 6), "log_loss_nb": round(f(alpha), 6),
            "per_line": per_line}


def _total_dispersion_rows(games, teams, parks, starters, coeffs, adj, shrink,
                           resolve=None) -> list[tuple]:
    """[(lam_home, lam_away, actual total, game_pk)] under the given pricer."""
    rows = []
    for g in games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        er = expected_runs(g["home_org"], g["away_org"],
                           home_sp=gs.get(g.get("home_sp")),
                           away_sp=gs.get(g.get("away_sp")),
                           teams=gt, parks=gpk, coeffs=coeffs,
                           home_adj=adj, diff_shrink=shrink)
        if not er:
            continue
        rows.append((er["lam_home"], er["lam_away"],
                     int(g["home_runs"]) + int(g["away_runs"]), g.get("game_pk")))
    return rows


def fit_total_dispersion_vintage(games, *, coeffs=None, adj=None, shrink=None) -> dict:
    """alpha_T for the SERVED pricer on the vintage FIT half; the eval half and the
    market are not read. The measurement build_context publishes either way."""
    if coeffs is None:
        coeffs = coefficients()
    if adj is None or shrink is None:
        ctx = _load_json(CONTEXT_PATH) or {}
        adj = float(ctx.get("home_field_runs_adj") or 0.0) if adj is None else adj
        shrink = float(ctx.get("diff_shrink") or 1.0) if shrink is None else shrink
    out = {"basis": ("vintage FIT half only (_vintage_cut_index), served coefficients "
                     "and corrections on dated features; the eval half and the market "
                     "are not read"),
           "criteria": "TOTAL_DISPERSION_GATE_CRITERIA", "served": SERVE_TOTAL_DISPERSION}
    resolve, _ = _vintage_resolver()
    gradable = [g for g in (games or []) if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out.update({"status": "insufficient vintage coverage", "alpha": None,
                    "n_gradable": len(gradable)})
        return out
    cut = dates[_vintage_cut_index(gradable, dates)]
    fit_g = [g for g in gradable if (g.get("date") or "") < cut]
    rows = _total_dispersion_rows(fit_g, None, None, None, coeffs, adj, shrink, resolve)
    fit = fit_total_dispersion([(a, b, y) for a, b, y, _ in rows])
    if not fit or len(rows) < VINTAGE_MIN_FIT_GAMES:
        out.update({"status": "insufficient fit rows", "alpha": None,
                    "n_fit_games": len(rows)})
        return out
    out.update(fit)
    out.update({"status": "fitted", "split_date": cut, "n_fit_games": len(rows)})
    return out


def _total_cal_pair(v) -> tuple[float, float] | None:
    """An (a, b) survival-map pair from a context value, or None. a must be
    positive (a non-positive slope is not a survival function) and both finite."""
    try:
        a, b = float(v[0]), float(v[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (math.isfinite(a) and math.isfinite(b)) or a <= 0 or abs(a) > 50 or abs(b) > 50:
        return None
    return a, b


def served_total_calibration() -> tuple[float, float] | None:
    """The SERVED 7h map, or None for the Poisson total. Flag checked first."""
    if not SERVE_TOTAL_CALIBRATION:
        return None
    ctx = _load_json(CONTEXT_PATH) or {}
    return _total_cal_pair(ctx.get("total_calibration"))


def fitted_total_calibration() -> dict | None:
    """The MEASUREMENT block (`total_calibration_fitted`), published either way."""
    ctx = _load_json(CONTEXT_PATH) or {}
    blk = ctx.get("total_calibration_fitted")
    if not isinstance(blk, dict) or _total_cal_pair((blk.get("a"), blk.get("b"))) is None:
        return None
    return blk


def survival_map_pmf(tot: list[float], a: float, b: float) -> list[float]:
    """The pmf implied by S'(k) = sigmoid(a*logit(S(k)) + b), S(k) = P(total > k).

    S(-1) = 1 maps to 1 and an exact 0 in the far tail maps to 0, so the result is
    a distribution on the same support; with a > 0 the map is monotone, so every
    cell is non-negative."""
    n = len(tot)
    surv = []
    rem = 1.0
    for k in range(n):
        rem -= tot[k]
        surv.append(max(0.0, rem))
    out = []
    prev = 1.0
    for k in range(n):
        s = surv[k]
        if s <= 0.0:
            s2 = 0.0
        elif s >= 1.0:
            s2 = 1.0
        else:
            # An UNCLIPPED logit: `_logit` floors at _PROB_EPS, which would flatten
            # every survival value in the tail to one number and pile the tail's
            # mass onto a single cell.
            sc = min(max(s, 1e-300), 1.0 - 1e-16)
            s2 = _sigmoid(a * math.log(sc / (1.0 - sc)) + b)
        out.append(max(0.0, prev - s2))
        prev = s2
    if prev > 0.0 and out:
        out[-1] += prev                        # the tail beyond the support
    return out


def _total_cal_samples(rows, lines=None) -> tuple[list[float], list[int]]:
    """Pooled (Poisson P(over L), outcome) pairs over the grid."""
    lines = tuple(lines if lines is not None else TOTAL_LEVEL_LINES)
    ps, ys = [], []
    for lh, la, y in rows:
        tot = _total_pmf(lh, la, None)
        for L in lines:
            ps.append(_pmf_over(tot, L))
            ys.append(1 if y > L else 0)
    return ps, ys


def _total_cal_losses(rows, ab, lines=None) -> list[float]:
    """Per-game grid log loss under the map (None is the served Poisson)."""
    lines = tuple(lines if lines is not None else TOTAL_LEVEL_LINES)
    out = []
    for lh, la, y in rows:
        tot = _total_pmf(lh, la, None)
        s = 0.0
        for L in lines:
            p = _pmf_over(tot, L)
            if ab is not None:
                p = apply_platt(p, ab[0], ab[1])
            s -= math.log(p) if y > L else math.log(1.0 - p)
        out.append(s)
    return out


def fit_total_calibration(rows, *, lines=None) -> dict | None:
    """(a, b) on ONE fit window, or None when fit_platt refuses or a <= 0."""
    rows = [(float(a), float(b), float(y)) for a, b, y in (rows or [])]
    n = len(rows)
    if n < 2:
        return None
    lines = tuple(lines if lines is not None else TOTAL_LEVEL_LINES)
    ps, ys = _total_cal_samples(rows, lines)
    ab = fit_platt(ps, ys)
    if ab is None or ab[0] <= 0:
        return None
    a, b = round(ab[0], 5), round(ab[1], 5)
    per_line = []
    for L in lines:
        pp = [_pmf_over(_total_pmf(x, z, None), L) for x, z, _ in rows]
        per_line.append({
            "line": L,
            "observed_over": round(sum(1 for *_, y in rows if y > L) / n, 4),
            "model_over_poisson": round(sum(pp) / n, 4),
            "model_over_mapped": round(sum(apply_platt(p, a, b) for p in pp) / n, 4),
        })
    return {"a": a, "b": b, "n": n, "lines": list(lines),
            "log_loss_poisson": round(sum(_total_cal_losses(rows, None, lines)) / n, 6),
            "log_loss_mapped": round(sum(_total_cal_losses(rows, (a, b), lines)) / n, 6),
            "per_line": per_line}


def fit_total_calibration_vintage(games, *, coeffs=None, adj=None, shrink=None) -> dict:
    """(a, b) for the SERVED pricer on the vintage FIT half; the eval half and the
    market are not read."""
    if coeffs is None:
        coeffs = coefficients()
    if adj is None or shrink is None:
        ctx = _load_json(CONTEXT_PATH) or {}
        adj = float(ctx.get("home_field_runs_adj") or 0.0) if adj is None else adj
        shrink = float(ctx.get("diff_shrink") or 1.0) if shrink is None else shrink
    out = {"basis": ("vintage FIT half only (_vintage_cut_index); the eval half and "
                     "the market are not read"),
           "criteria": "TOTAL_CALIBRATION_GATE_CRITERIA", "served": SERVE_TOTAL_CALIBRATION}
    resolve, _ = _vintage_resolver()
    gradable = [g for g in (games or []) if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out.update({"status": "insufficient vintage coverage", "a": None, "b": None})
        return out
    cut = dates[_vintage_cut_index(gradable, dates)]
    fit_g = [g for g in gradable if (g.get("date") or "") < cut]
    rows = _total_dispersion_rows(fit_g, None, None, None, coeffs, adj, shrink, resolve)
    fit = fit_total_calibration([(a, b, y) for a, b, y, _ in rows])
    if not fit or len(rows) < VINTAGE_MIN_FIT_GAMES:
        out.update({"status": "insufficient fit rows or refused", "a": None, "b": None})
        return out
    out.update(fit)
    out.update({"status": "fitted", "split_date": cut, "n_fit_games": len(rows)})
    return out


def fit_total_level_vintage(games, *, coeffs=None, adj=None, shrink=None) -> dict:
    """The recentre for the SERVED pricer, fitted on the vintage FIT half.

    The fit half is the one the honest backtest fits on and never grades
    (`_vintage_cut_index`, split_date 2026-08-01 on 2026-09-11), priced on the
    dated vintage features with the served coefficients and corrections, which is
    what the served pricer would have said about those games before they were
    played. The eval half is not read. The market is not read."""
    if coeffs is None:
        coeffs = coefficients()
    if adj is None or shrink is None:
        ctx = _load_json(CONTEXT_PATH) or {}
        adj = float(ctx.get("home_field_runs_adj") or 0.0) if adj is None else adj
        shrink = float(ctx.get("diff_shrink") or 1.0) if shrink is None else shrink
    out = {"basis": ("vintage FIT half only (_vintage_cut_index), served coefficients "
                     "and corrections on dated features; the eval half and the market "
                     "are not read"),
           "criteria": "TOTAL_LEVEL_GATE_CRITERIA", "served": SERVE_TOTAL_LEVEL}
    resolve, _ = _vintage_resolver()
    gradable = [g for g in (games or []) if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out.update({"status": "insufficient vintage coverage", "centre": None,
                    "n_gradable": len(gradable)})
        return out
    cut = dates[_vintage_cut_index(gradable, dates)]
    fit_g = [g for g in gradable if (g.get("date") or "") < cut]
    rows = _total_level_rows(fit_g, None, None, None, coeffs, adj, shrink, resolve)
    fit = fit_total_level([(m, y) for m, y, _ in rows])
    if not fit or len(rows) < VINTAGE_MIN_FIT_GAMES:
        out.update({"status": "insufficient fit rows", "centre": None,
                    "n_fit_games": len(rows)})
        return out
    out.update(fit)
    out.update({"status": "fitted", "split_date": cut, "n_fit_games": len(rows),
                "fit_first_date": min(g["date"] for g in fit_g),
                "fit_last_date": max(g["date"] for g in fit_g)})
    return out


# ---------------------------------------------------------------------------
# the game model
# ---------------------------------------------------------------------------
def _starter_share(team: dict, starter: dict | None) -> tuple[float, float, str]:
    """(starter share of the game, starter plus, source) for one pitching side.

    The listed probable covers ip_per_gs/9 of the game, clipped to [0.25, 0.85];
    with nobody announced the club's own starter innings share and rotation
    average stand in. ONE definition: game_prevention_z prices on it and the
    dark section-5f candidate (game_offense_ph_z) splits the game on it, so the
    two can never disagree about how much of a game the bullpen pitches."""
    if starter and starter.get("sem_plus") is not None:
        share = (starter.get("ip_per_gs") or (DEFAULT_SP_SHARE * 9.0)) / 9.0
        share = max(0.25, min(0.85, share))
        return share, float(starter["sem_plus"]), "probable"
    share = float(team.get("sp_ip_share") or DEFAULT_SP_SHARE)
    return share, float(team.get("rotation_plus", 100.0)), "rotation-average"


def game_prevention_z(team: dict, starter: dict | None, teams: dict) -> tuple[float, dict]:
    """(z, detail) for one side's run prevention IN THIS GAME.

    The listed probable's own SEM+ covers ip_per_gs/9 of the game; the team
    bullpen covers the rest. With nobody announced the team's rotation average
    stands in for the starter share, which is exactly what a book does with a
    TBD."""
    scale = teams.get("_scale") or {}
    mu = scale.get("prev_mu", 100.0)
    sd = scale.get("prev_sd", 1.0) or 1.0
    pen_plus = team.get("bullpen_plus", 100.0)
    share, sp_plus, src = _starter_share(team, starter)
    blended = share * sp_plus + (1.0 - share) * pen_plus
    return (blended - mu) / sd, {
        "starter_plus": round(sp_plus, 1), "bullpen_plus": round(pen_plus, 1),
        "starter_share": round(share, 3), "blend_plus": round(blended, 1),
        "source": src,
    }


# The four hitter-derived section-5f columns; a scoring side with all four null
# is excluded from the 5f eval set rather than priced on a zero bench term.
PH_HITTER_COLUMNS = ("lineup_dis_vs_lhp", "lineup_dis_vs_rhp",
                     "bench_adv_vs_lhp", "bench_adv_vs_rhp")


def game_offense_ph_z(team_s: dict, team_o: dict, opp_starter: dict | None,
                      teams: dict) -> tuple[float | None, dict]:
    """DARK. The section 5f candidate offense for scoring side S facing O:

        z_off_ph = z_off + (1 - w) * [ (pL - pL_bar) * (L - R)
                                      + phi * (pL * g_L + (1 - pL) * g_R) ] / off_sd

    `w` is O's starter share from `_starter_share`, the one helper
    game_prevention_z prices on; `pL` O's pen_lhp_share and `pL_bar` its mean over
    the clubs in `teams` (the same vintage); `L`, `R` S's off_vs_lhp and
    off_vs_rhp, read and never written; `phi` S's ph_share; g_h = max(0,
    bench_adv_vs_h - lineup_dis_vs_h), 0 when either is null. It never reads the
    probable's `throws`, which is 5e's lever. No new free parameter: the served
    b1 prices the result, refit on the fit half as the served model's is.

    Returns (None, detail) when the 5f eval rule EXCLUDES the side: S's ph_share
    or O's pen_lhp_share null, all four of S's hitter-derived columns null, or no
    split pair or no club mean to reference. The detail carries each arm in z
    units so a harness can report arm A and arm B alone.

    NOTHING SERVED CALLS THIS. expected_runs, the fit and the export price on
    z_off; this exists so the gate harness computes the candidate with one
    definition, and a test pins that no served path reaches it."""
    w, _, src = _starter_share(team_o, opp_starter)
    detail: dict = {"starter_share": w, "source": src}
    scale = teams.get("_scale") or {}
    off_sd = scale.get("off_sd", 1.0) or 1.0
    z_off = team_s.get("z_off")
    pL, phi = team_o.get("pen_lhp_share"), team_s.get("ph_share")
    L, R = team_s.get("off_vs_lhp"), team_s.get("off_vs_rhp")
    pens = [r.get("pen_lhp_share") for k, r in teams.items()
            if not str(k).startswith("_") and isinstance(r, dict)
            and r.get("pen_lhp_share") is not None]
    excluded = []
    if z_off is None:
        excluded.append("z_off")
    if phi is None:
        excluded.append("scoring side ph_share null")
    if pL is None:
        excluded.append("opposing pen_lhp_share null")
    if all(team_s.get(c) is None for c in PH_HITTER_COLUMNS):
        excluded.append("all four hitter-derived columns null")
    if L is None or R is None:
        excluded.append("off_vs_lhp or off_vs_rhp null")
    if not pens:
        excluded.append("no club carries pen_lhp_share")
    if excluded:
        detail["excluded"] = excluded
        return None, detail

    def _g(bench, lineup):
        if bench is None or lineup is None:
            return 0.0
        return max(0.0, float(bench) - float(lineup))

    pL, phi = float(pL), float(phi)
    pL_bar = sum(float(p) for p in pens) / len(pens)
    g_L = _g(team_s.get("bench_adv_vs_lhp"), team_s.get("lineup_dis_vs_lhp"))
    g_R = _g(team_s.get("bench_adv_vs_rhp"), team_s.get("lineup_dis_vs_rhp"))
    arm_a = (pL - pL_bar) * (float(L) - float(R))
    arm_b = phi * (pL * g_L + (1.0 - pL) * g_R)
    scale_late = (1.0 - w) / off_sd
    detail.update({"pL": pL, "pL_bar": pL_bar, "g_L": g_L, "g_R": g_R,
                   "arm_a_z": scale_late * arm_a, "arm_b_z": scale_late * arm_b,
                   "delta_z": scale_late * (arm_a + arm_b)})
    return float(z_off) + scale_late * (arm_a + arm_b), detail


def expected_runs(home_org: str, away_org: str, *, home_sp: dict | None = None,
                  away_sp: dict | None = None, teams: dict | None = None,
                  parks: dict | None = None, coeffs: dict | None = None,
                  home_adj: float | None = None,
                  diff_shrink: float | None = None) -> dict | None:
    """Expected runs for both sides, plus the components that produced them.
    None when either club is missing from the leaderboards.

    THE HOME-FIELD CORRECTION, because the raw fit gets it wrong for a
    structural reason worth naming. Fitting runs scored on a home dummy
    recovers only +0.013 runs of home field in 2026, while home teams actually
    won 52.3% of those same games. Both numbers are right: a home team leading
    after the top of the ninth DOES NOT BAT, so its runs-scored column is
    censored exactly in the games it wins. Regressing on runs therefore
    understates home field almost to zero.

    `home_adj` is the run-differential shift that reconciles them, solved in
    build_context so that the model's mean home win probability equals the
    observed home win rate. It is applied as +adj/2 to the home side and
    -adj/2 to the away side, so the runline moves coherently with the
    moneyline and the fair TOTAL is left untouched (the two halves cancel).
    Zero when no context has been built.

    THE MARGIN SHRINK, for a defect the first calibration table caught. The
    raw linear predictor put 2026 games as far apart as 90/10, and the bins
    above 0.80 came back 0.86 predicted against 0.67 actual: the model was
    more sure than the season was. `diff_shrink` scales the run DIFFERENTIAL
    toward zero while holding the pair mean, so it shrinks the moneyline and
    the runline together and leaves the fair total alone. It is fitted by
    minimizing log loss on completed games (`_solve_diff_shrink`), not chosen.
    1.0 when no context has been built."""
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    c = coeffs or coefficients()
    if home_adj is None or diff_shrink is None:
        ctx = _load_json(CONTEXT_PATH) or {}
        if home_adj is None:
            home_adj = float(ctx.get("home_field_runs_adj") or 0.0)
        if diff_shrink is None:
            diff_shrink = float(ctx.get("diff_shrink") or 1.0)
    h, a = teams.get(home_org), teams.get(away_org)
    if not h or not a:
        return None
    park = (parks.get(home_org) or 1.0) - 1.0
    zp_home, det_home = game_prevention_z(h, home_sp, teams)
    zp_away, det_away = game_prevention_z(a, away_sp, teams)

    def _runs(z_off, z_prev_opp, is_home):
        return (c["b0"] + c["b1"] * z_off + c["b2"] * z_prev_opp
                + c["b3"] * park + (c["b4"] if is_home else 0.0)
                + (home_adj / 2.0 if is_home else -home_adj / 2.0))

    raw_home = _runs(h["z_off"], zp_away, True)
    raw_away = _runs(a["z_off"], zp_home, False)
    mid, half = (raw_home + raw_away) / 2.0, (raw_home - raw_away) / 2.0
    lam_home = max(1.5, min(9.5, mid + diff_shrink * half))
    lam_away = max(1.5, min(9.5, mid - diff_shrink * half))
    return {
        "lam_home": lam_home, "lam_away": lam_away,
        "home_field_runs_adj": round(float(home_adj), 4),
        "diff_shrink": round(float(diff_shrink), 4),
        "park_index": round(park + 1.0, 3),
        "home": {"org": home_org, "z_off": round(h["z_off"], 3),
                 "offense_plus": h["offense_plus"], "prevention": det_home},
        "away": {"org": away_org, "z_off": round(a["z_off"], 3),
                 "offense_plus": a["offense_plus"], "prevention": det_away},
    }


def _poisson_pmf(lam: float, k_max: int) -> list[float]:
    """pmf[0..k_max] for Poisson(lam), recurrence form (no factorials, no
    overflow at the tail)."""
    out = [math.exp(-lam)]
    for k in range(1, k_max + 1):
        out.append(out[-1] * lam / k)
    return out


def _nb2_pmf(lam: float, r: float, k_max: int) -> list[float]:
    """pmf[0..k_max] for NB2 with MEAN lam and dispersion r = 1/alpha, so
    var = lam + lam^2/r. Same recurrence idiom as `_poisson_pmf` and for the
    same reason: no factorials, no overflow, and no gamma function, therefore
    no scipy in the serving path.

        p(0)   = (r / (r + lam))^r
        p(k)   = p(k-1) * (k-1+r)/k * lam/(r+lam)

    The ratio form is exact, not an approximation of the gamma expression: the
    Gamma(k+r)/Gamma(r) product telescopes into the (k-1+r)/k factors. As
    r -> infinity the recurrence converges to the Poisson one term by term,
    which is why `r=None` (not a large r) is the Poisson switch below: a limit
    reached numerically would not be bit-identical and the A/B would not be
    clean."""
    q = lam / (r + lam)
    out = [math.exp(r * math.log(r / (r + lam)))]
    for k in range(1, k_max + 1):
        out.append(out[-1] * (k - 1 + r) / k * q)
    return out


def _nb2_side_pmf(lam: float, r: float, k_max: int) -> list[float]:
    """NB2 side pmf over [0, k_max], RENORMALIZED to sum to 1.

    THE TRUNCATION IS NOT THE POISSON TRUNCATION AND WAS MEASURED, not assumed.
    Poisson at the shipped per-side k_max of 24 loses at most 2.09e-05 of mass
    at the lam ceiling of 9.5. NB2 at alpha 0.284 loses 2.12e-02 there - three
    orders of magnitude worse - because the NB tail is geometric in
    lam/(r+lam) = 0.729 rather than factorial. Reaching a 1e-12 tail would need
    k = 110 per side and a 110x110 joint grid, which is 30x the work for
    accuracy nothing published can see.

    So the support runs to `k_max` and the remainder is REDISTRIBUTED
    proportionally instead of leaked. Leaking is the worse of the two: the
    caller computes p_away as 1 - p_home, so every unassigned unit of mass
    silently becomes an away win. At the k_max = 40 this module uses the
    discarded mass is 4.00e-04 at lam 9.5, 1.81e-05 at the league mean 4.5, and
    renormalizing turns that into a proportional reshaping of the retained
    support rather than a one-sided error. The residual bias is a slight
    UNDERSTATEMENT of extreme margins, the direction that keeps this correction
    conservative about the thing it is claiming to fix."""
    p = _nb2_pmf(lam, r, k_max)
    s = sum(p)
    return p if s <= 0 else [v / s for v in p]


def _side_pmf(lam: float, r: float | None, k_max: int) -> list[float]:
    """One scoring side's run pmf. `r is None` means Poisson, EXACTLY."""
    return _poisson_pmf(lam, k_max) if r is None else _nb2_side_pmf(lam, r, k_max)


def _score_joint(lam_home: float, lam_away: float, r: float | None = None,
                 k_max: int = 24, total_k_max: int = 40) -> tuple[dict, list[float]]:
    """(margin distribution, total pmf) from ONE pass over the joint grid.

    WHY THEY ARE COMPUTED TOGETHER NOW. Under Poisson the total had a closed
    form - the sum of two independent Poissons is Poisson - so the two markets
    could be priced from two independent one-liners. Two NB2s with DIFFERENT
    means do not sum to an NB2 (they only do when the two success probabilities
    lam/(r+lam) agree, which happens only when lam_home == lam_away), so the
    total loses its closed form the moment dispersion is switched on. The
    honest fix is the joint grid, which prices margin and total off the same
    convolution and cannot let them disagree about the same game.

    `k_max` is the PER-SIDE truncation for the MARGIN and, on the Poisson
    branch, `total_k_max` is the length of the returned total pmf. On the NB
    branch the per-side support is raised to `total_k_max`, because a side index
    above it cannot reach a total of 40 at all while a side index below 40 very
    much can: see `_nb2_side_pmf` for the measured tail.

    THE TWO BRANCHES RETURN TOTALS OF DIFFERENT LENGTHS, AND THAT IS THE FIX.
    Poisson returns exactly `total_k_max + 1` cells and NB returns the FULL
    convolution support, `2 * side_k + 1`. Every cell on both branches means the
    same thing, P(total == k). Nothing is top-coded, nothing is renormalized,
    nothing is dropped. Both callers of the total (`total_side_probabilities`
    and the `over` closure in `game_probabilities`) read `len(pmf)`, so a longer
    array is simply a longer sum.

    THE DEFECT THAT FORCED IT. The loop used to drop every joint cell with
    i + j > total_k_max on the floor. That leaves an array that does not sum to
    1, and `total_side_probabilities` prices a half-point Under as `1 - p_over`,
    so the whole deficit landed on the UNDER. Measured at alpha 0.28425, side
    support 40:

        lam 4.50/4.50   residual 4.98e-06   Under 8.5 overstated by 2.45e-06
        lam 7.50/1.50   residual 3.02e-05   Under 8.5 overstated by 1.43e-05
        lam 9.50/1.50   residual 2.44e-04   Under 8.5 overstated by 1.48e-04
        lam 9.50/9.50   residual 1.55e-02   Under 8.5 overstated by 1.42e-02

    1.42e-02 at the lambda ceiling is a QUARTER of the 0.06 provisional edge
    floor, handed to one side of the market for free. Carrying the full support
    takes the NB residual at those same four shapes to 1.11e-16, 1.33e-12,
    1.33e-12 and 0.0, the floor set by the loop's own 1e-12 prune rather than
    by the support, and it costs NOTHING in the loop:
    the pairs visited are identical, only the array they are binned into is
    longer.

    TOP-CODING WAS TRIED AND WITHDRAWN, and the reason is not taste. Writing
    P(total >= total_k_max) into the last cell also sums to 1, but it changes
    what that cell MEANS, and the NB total is checked against the exact
    equal-mean closed form cell by cell. A cell that carries a tail is off that
    closed form by the whole tail, 4.98e-06 at lam 4.5/4.5. Carrying the tail
    explicitly keeps every cell exact and keeps the check meaningful.

    THE POISSON BRANCH IS UNTOUCHED, INCLUDING ITS OWN LEAK. Its truncated
    closed form is short 8.09e-06 at the lam ceiling of 19.0 total and 6.11e-15
    at the league-typical 9.0, and that mass still lands on a half-point Under.
    It stays, on purpose. 8.09e-06 is under the 5th decimal every published
    probability is rounded to, it only appears at a total no board posts, and
    the alternative costs the one invariant that makes the section 11 gate a
    true A/B on one flag: r is None reproduces the shipped Skellam BIT FOR BIT,
    margin and total, every cell. A repair worth less than one ulp of a
    published digit is not worth buying with the incumbent's identity."""
    if r is None:
        ph = _poisson_pmf(lam_home, k_max)
        pa = _poisson_pmf(lam_away, k_max)
        dist: dict = {}
        # Closed form, and it is exact - do not spend the grid on it. NOT
        # adjusted: see the docstring, this array is the shipped Skellam.
        total = _poisson_pmf(lam_home + lam_away, total_k_max)
        for i, p_i in enumerate(ph):
            if p_i < 1e-12:
                continue
            for j, p_j in enumerate(pa):
                if p_j < 1e-12:
                    continue
                d = i - j
                dist[d] = dist.get(d, 0.0) + p_i * p_j
        return dist, total
    side_k = max(k_max, total_k_max)
    ph = _nb2_side_pmf(lam_home, r, side_k)
    pa = _nb2_side_pmf(lam_away, r, side_k)
    dist = {}
    # The FULL convolution support. Every (i, j) the loop visits has a cell to
    # land in, so nothing is dropped and nothing has to be top-coded. See the
    # docstring: dropping put up to 1.55e-02 of mass on the Under.
    total = [0.0] * (2 * side_k + 1)
    for i, p_i in enumerate(ph):
        if p_i < 1e-12:
            continue
        for j, p_j in enumerate(pa):
            if p_j < 1e-12:
                continue
            w = p_i * p_j
            d = i - j
            dist[d] = dist.get(d, 0.0) + w
            total[i + j] += w
    return dist, total


def margin_distribution(lam_home: float, lam_away: float, k_max: int = 24,
                        r: float | None = None) -> dict:
    """P(home runs - away runs = d) for d in [-k_max, k_max], by direct
    convolution of the two scoring sides (no Bessel functions, so the serving
    path has no scipy dependency).

    `r=None` is the Skellam this module shipped with. `r` is the NB2
    dispersion, r = 1/alpha; see `_score_joint`. Thin wrapper, kept so every
    existing caller (dfs_export's implied-team-total bisection among them)
    keeps its exact signature and its exact numbers."""
    return _score_joint(lam_home, lam_away, r, k_max)[0]


def total_distribution(lam_home: float, lam_away: float, k_max: int = 40,
                       r: float | None = None) -> list[float]:
    """P(total runs = k) for k in [0, k_max].

    Poisson (`r=None`) keeps the closed form: the sum of two independent
    Poissons is Poisson. NB2 has no such form and goes through the joint grid.
    Thin wrapper over `_score_joint` so the two markets cannot drift apart.

    `k_max` IS THE POISSON LENGTH, NOT A UNIVERSAL ONE. On the NB branch the
    returned array runs to the full convolution support (2 * k_max) instead,
    because the NB tail above 40 is real mass - up to 1.55e-02 at the lambda
    ceiling - and truncating it hands that mass to the Under. Every cell on
    both branches is P(total == k); read the length off the array, never assume
    it. See `_score_joint`."""
    return _score_joint(lam_home, lam_away, r, 24, k_max)[1]


def total_side_probabilities(total_pmf: list[float], line: float) -> dict:
    """Over, Under and PUSH for one posted total.

    THE DEFECT (2026-08-09, found replaying .cache/odds/2026-08-09-0133.json).
    betting_export priced the Under as `1.0 - p_over`, and p_over is
    P(total >= floor(L) + 1). On an INTEGER line that reads
    Under L = 1 - P(>= L+1) = P(<= L), which hands the Under the whole push mass
    P(total == L). Measured on COL at STL with lam_total 9.380: Under 9.0 came
    out 0.53745 against a true P(<= 8) of 0.40671. The 0.13073 error IS
    P(total = 9) and is more than double the 0.06 provisional floor. Four of the
    23 events on that board carried a whole-number total (7.0, 8.0, 8.0, 10.0),
    and betting_shadow already grades a landed integer total as a push, so the
    ledger knew about mass the price did not.

    THE RETURNED PAIR IS CONDITIONAL ON NO PUSH. The de-vigged two-way market an
    edge is measured against is itself a no-push market: on a whole number the
    book returns the stake when the total lands, so its two prices describe the
    game GIVEN it does not push. Scoring an unconditional model probability
    against a conditional market one is the same class of mismatch as pricing
    two different lines against each other.

    A half-point line cannot push. Its p_over is computed by the identical
    expression the `over` callable uses and its p_under is the identical
    `1.0 - p_over`, so nothing already on the board moves by a single bit.

    `p_push` is the raw pmf mass at the line, unconditioned, because that is the
    number a reader wants: how often this bet is a refund.

    THIS FUNCTION IS ONLY AS HONEST AS THE pmf IT IS HANDED. `1.0 - p_over` on a
    half point is correct exactly when the pmf sums to 1, so `_score_joint`
    returns the NB total over its FULL convolution support rather than dropping
    the tail above 40; before that fix the NB branch put up to 1.55e-02 of
    unassigned mass on the Under at the lambda ceiling. The Poisson branch is
    still its own truncated closed form and is short by at most 8.09e-06, kept
    deliberately so `r=None` stays bit-identical to what shipped."""
    n = len(total_pmf or [])
    if not n:
        return {"p_over": None, "p_under": None, "p_push": None}
    if float(line) != int(line):
        need = math.floor(line) + 1
        p_over = sum(total_pmf[k] for k in range(need, n))
        return {"p_over": p_over, "p_under": 1.0 - p_over, "p_push": 0.0}
    k = int(line)
    p_push = total_pmf[k] if 0 <= k < n else 0.0
    p_over = sum(total_pmf[j] for j in range(k + 1, n))
    p_under = sum(total_pmf[j] for j in range(0, max(0, min(k, n))))
    s = p_over + p_under
    if s <= 0:
        return {"p_over": None, "p_under": None, "p_push": p_push}
    return {"p_over": p_over / s, "p_under": p_under / s, "p_push": p_push}


def game_probabilities(home_org: str, away_org: str, *, home_sp=None, away_sp=None,
                       teams=None, parks=None, coeffs=None, tie_home=None,
                       home_adj=None, diff_shrink=None,
                       run_alpha: float | None = None,
                       platt_ab: tuple | None = None,
                       runline_tie_split: tuple | None = None,
                       total_level: float | None = None,
                       total_alpha: float | None = None,
                       total_cal: tuple | None = None) -> dict | None:
    """The full model view of one game: moneyline, runline, fair total.

    `total_alpha` is the section 7g total-scoped NB2 dispersion. None resolves
    the SERVED value (None until SERVE_TOTAL_DISPERSION flips), and only on the
    serving path, the `total_level` rule. A value prices the Over, Under and push
    off a separate total pass with NB2 sides; the margin pass, and so the
    moneyline and the runline, cannot move.

    `total_cal` is the section 7h survival map (a, b). None resolves the SERVED
    pair (None until SERVE_TOTAL_CALIBRATION flips), serving path only. It maps
    the total pmf after any level or dispersion pass; nothing else reads it.

    Ties do not exist in MLB, so for the MONEYLINE the P(margin = 0) mass is
    split by the MEASURED extra-innings home win rate (league_context, shrunk
    toward a coin flip on a 100-game prior), not by an invented constant.

    The RUNLINE reads the same atom through the same function,
    `split_tie_atom`, with `runline_tie_split`. None resolves the SERVED split,
    which is the whole-atom construction (every tie a +1.5 cover for both
    sides) until SERVE_RUNLINE_TIE_SPLIT flips, and it resolves it ONLY on the
    serving path: a caller that brings its own fit-window `tie_home` (every
    lab) must bring its own split too, and otherwise gets the whole-atom
    construction, never a season-wide number its eval window helped produce.
    That is the rule `_fit_tie_home` states for the tie rate itself.
    `runline_at_split` (a callable, like `over`) re-prices the four runline
    probabilities under any explicit split off the same distribution and the
    same tie_home; the export uses it for the row's `tie_atom` disclosure (a
    zero shift while the split is served), and nothing prices off it.

    `run_alpha` is the NB2 run dispersion. None reads the served value out of
    the context file (`run_dispersion_alpha`, absent until the section 11 gate
    opened it); 0.0 forces Poisson. Both markets are priced off ONE joint pass
    so the margin and the total cannot disagree about the same game.

    `platt_ab` is the B5 response-scale calibration seam (section 11b). None
    resolves the SERVED map, which is None-for-identity until
    SERVE_PROB_CALIBRATION flips; an explicit (a, b) applies that map, which
    is what the gate lab uses. It touches the MONEYLINE ONLY: p_home and
    p_away move together, and the runline, the total and the fair total are
    computed from the uncalibrated margin distribution, because a scale repair
    on p_home says nothing about a mis-shaped margin (the dispersion gate owns
    those two markets).

    `total_level` is the BET1 total recentre in runs (SERVE_TOTAL_LEVEL). None
    resolves the SERVED value, which is None until the flag flips, and resolves
    it ONLY on the serving path: a caller that brings its own fit-window
    `tie_home` (every lab) gets no recentre unless it passes one, the
    `runline_tie_split` rule. A non-zero value prices the Over, the Under and the
    push off a SECOND pass at lambdas shifted by half the constant each; the
    margin distribution, and so the moneyline and the runline, still come from
    the first pass and cannot move. `fair_total` stays lam_home + lam_away, the
    expected runs; `total_price_mean` is the mean of the distribution the total
    is priced on."""
    er = expected_runs(home_org, away_org, home_sp=home_sp, away_sp=away_sp,
                       teams=teams, parks=parks, coeffs=coeffs, home_adj=home_adj,
                       diff_shrink=diff_shrink)
    if not er:
        return None
    if run_alpha is None:
        run_alpha = run_dispersion_alpha()
    r = _alpha_to_r(run_alpha)
    lam_h, lam_a = er["lam_home"], er["lam_away"]
    dist, tot = _score_joint(lam_h, lam_a, r)
    th = tie_home if tie_home is not None else (league_context().get("extra_inning_home_rate")
                                               or LITERATURE_TIE_HOME)
    if runline_tie_split is None and tie_home is None:
        runline_tie_split = served_runline_tie_split()
    # ONE reading of the tie atom for both markets (L14-01): the moneyline's
    # split and the runline's split come out of the same call, so they cannot
    # drift into two different claims about the same games again unseen.
    atom = split_tie_atom(dist, th, runline_tie_split)
    p_tie = atom["p_tie"]
    p_home = atom["p_home"]
    # The B5 calibration seam, moneyline only. Identity while the serve flag
    # is off; see served_platt for why an old context key cannot leak through.
    if platt_ab is None:
        platt_ab = served_platt()
    if platt_ab:
        p_home = apply_platt(p_home, platt_ab[0], platt_ab[1])
    # Runline. A -1.5 favourite must win by 2+. The +1.5 dog needs the game
    # inside one run OR an outright win, which is 1 - P(margin >= 2). What a
    # game level after nine counts as is `split_tie_atom`'s call, not this one.
    rl_prices = _runline_prices(atom)
    fair_total = lam_h + lam_a
    # BET1: the total, and ONLY the total, may be recentred. `dist` above is
    # already spent on the moneyline and the runline, so nothing below can move
    # them; with no recentre `tot` is the first pass's array, bit for bit.
    if total_level is None and tie_home is None:
        total_level = served_total_level()
    tl = float(total_level) if total_level else 0.0
    price_mean = None
    if total_alpha is None and tie_home is None:
        total_alpha = served_total_dispersion()
    ta = _total_dispersion_value(total_alpha) if total_alpha else None
    if tl or ta:
        lh2 = max(0.25, lam_h + tl / 2.0)
        la2 = max(0.25, lam_a + tl / 2.0)
        tot = _score_joint(lh2, la2, _alpha_to_r(ta) if ta else r)[1]
        if tl:
            price_mean = lh2 + la2
    if total_cal is None and tie_home is None:
        total_cal = served_total_calibration()
    tc = _total_cal_pair(total_cal) if total_cal else None
    if tc:
        tot = survival_map_pmf(tot, tc[0], tc[1])

    def runline_at_split(split) -> dict:
        return _runline_prices(split_tie_atom(dist, th, split))

    def over(line: float) -> float:
        need = math.floor(line) + 1 if line != int(line) else int(line) + 1
        return sum(tot[k] for k in range(need, len(tot)))

    def total_sides(line: float) -> dict:
        return total_side_probabilities(tot, line)

    return {
        "home_org": home_org, "away_org": away_org,
        "lam_home": round(lam_h, 3), "lam_away": round(lam_a, 3),
        "p_home": round(p_home, 5), "p_away": round(1.0 - p_home, 5),
        **rl_prices,
        # The atom itself and the runline's reading of it, so a row can say
        # what a game level after nine was worth to it (L14-01).
        "p_tie": round(p_tie, 5),
        "runline_tie_split": ([round(float(runline_tie_split[0]), 4),
                               round(float(runline_tie_split[1]), 4)]
                              if runline_tie_split else None),
        "runline_at_split": runline_at_split,   # callable; see the docstring
        "fair_total": round(fair_total, 2),
        # BET1. None while no recentre prices this game; otherwise the constant
        # and the mean of the total distribution the Over and Under are read off.
        "total_level_runs": round(tl, 4) if tl else None,
        "total_price_mean": round(price_mean, 2) if price_mean is not None else None,
        # 7g: present only while a total-scoped dispersion prices this game.
        **({"total_dispersion_alpha": round(ta, 5)} if ta else {}),
        # 7h: present only while the survival map prices this game.
        **({"total_calibration_ab": [round(tc[0], 5), round(tc[1], 5)]} if tc else {}),
        "run_dispersion_alpha": (round(float(run_alpha), 5)
                                 if r is not None else None),
        "prob_calibration_ab": ([round(float(platt_ab[0]), 5),
                                 round(float(platt_ab[1]), 5)]
                                if platt_ab else None),
        "over": over,                      # callable; the export resolves a line
        # callable; over/under/push on ONE line, push-conditioned. `over` alone
        # cannot price the Under of a whole number: see total_side_probabilities.
        "total_sides": total_sides,
        "components": er,
        "model_version": MODEL_VERSION,
    }


# ---------------------------------------------------------------------------
# market math
# ---------------------------------------------------------------------------
def devig(decimals: dict, method: str = "proportional") -> dict:
    """Raw prices -> fair (no-vig) probabilities.

    PROPORTIONAL method: q_i = 1/decimal_i, then p_i = q_i / sum(q). The sum of
    the raw implieds is the overround (a two-way MLB moneyline at -110/-110
    sums to 1.0476, a 4.76% hold); dividing it out spreads the vig in
    proportion to each side's raw probability.

    This is a CHOICE. Shin's method and the power method both take relatively
    more vig off the longshot, which moves a fair probability by up to a point
    on a lopsided moneyline and therefore moves every edge on the page. The
    method name ships in the payload so the number can be audited."""
    if method != "proportional":
        raise ValueError(f"unsupported de-vig method {method!r}")
    raw = {}
    for k, d in (decimals or {}).items():
        try:
            dv = float(d)
        except (TypeError, ValueError):
            continue
        if dv > 1.0:
            raw[k] = 1.0 / dv
    s = sum(raw.values())
    if not raw or s <= 0:
        return {}
    return {k: v / s for k, v in raw.items()}


def hold_pct(decimals: dict) -> float | None:
    """The book's hold on a market: sum of raw implieds minus 1, in percent."""
    raw = [1.0 / float(d) for d in (decimals or {}).values() if _pos(d)]
    return None if not raw else (sum(raw) - 1.0) * 100.0


def _pos(d) -> bool:
    try:
        return float(d) > 1.0
    except (TypeError, ValueError):
        return False


def ev_per_unit(p: float, decimal: float) -> float:
    """Expected profit on a 1-unit stake at `decimal` odds given probability p."""
    return p * (decimal - 1.0) - (1.0 - p)


def kelly_fraction(p: float, decimal: float) -> float:
    """Full-Kelly stake fraction. INFORMATIONAL ONLY on this site: the public
    record is flat 1 unit, always, because a variable stake makes a published
    ROI unauditable and invites the exact behaviour the disclaimer warns
    against. Negative means no bet."""
    b = decimal - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (p * b - (1.0 - p)) / b)


def edge(p_model: float, p_fair: float) -> float:
    """Our probability minus the de-vigged market probability. Positive means
    the model thinks the market is short."""
    return p_model - p_fair


# ---------------------------------------------------------------------------
# offline game results (for fitting + backtest)
# ---------------------------------------------------------------------------
_SPORT_RE = re.compile(rb"/api/v1/sports/(\d+)")


def _mlb_feed_paths() -> list[Path]:
    """MLB (sportId 1) game feeds inside the existing StatsAPI feed cache.
    The cache is mostly minor-league, so the sport is sniffed off the first
    few KB rather than parsing 18k files."""
    if not FEED_CACHE.exists():
        return []
    out = []
    for p in sorted(FEED_CACHE.glob("*.json")):
        try:
            head = p.open("rb").read(9000)
        except OSError:
            continue
        m = _SPORT_RE.search(head)
        if m and m.group(1) == b"1":
            out.append(p)
    return out


def _write_rows(path, rows) -> None:
    """Sibling temp then an atomic, RETRYING replace.

    The results cache is read by the backtest while the nightly may be
    rewriting it, and a half-written JSON array that still parses is the
    failure mode this codebase spent 2026-08-06 removing from its other
    artifacts.

    The retry is not optional on Windows: os.replace raises PermissionError
    (WinError 5) whenever a reader holds the target open, so a bare call would
    turn a routine concurrent read into an exception that propagates out of
    build_game_cache and discards a completed 1.5GB feed walk. storage owns the
    hardened version, with a 30 second deadline and backoff; reuse it rather
    than growing a second, weaker copy here.

    A failed swap leaves the PREVIOUS cache intact, which is the right outcome:
    results are regenerable, and being a run behind beats serving a truncated
    results set to a published record."""
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(rows), encoding="utf-8")
        try:
            from storage import _atomic_replace
        except Exception:                                     # noqa: BLE001
            _atomic_replace = None
        if _atomic_replace is not None:
            _atomic_replace(tmp, path)
        else:
            os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"


def _row_from_schedule(g: dict, fallback_date: str | None) -> dict | None:
    """One schedule game -> the SAME compact row shape the feed walk produces.

    Kept byte-compatible with the feed path on purpose: the two sources have to
    be mergeable by game_pk, and a row whose shape depends on which door it came
    through would make the fit and the backtest quietly source-dependent."""
    if (g.get("status") or {}).get("abstractGameState") != "Final":
        return None
    # gameType=R is a query parameter, not a promise about the payload. The
    # backtest must never see spring training, exhibition or postseason games:
    # they carry different team quality and different roster rules, and the fit
    # would silently absorb both.
    if (g.get("gameType") or "R") != "R":
        return None
    teams = g.get("teams") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    line = g.get("linescore") or {}
    lt = line.get("teams") or {}
    hr = (lt.get("home") or {}).get("runs", home.get("score"))
    ar = (lt.get("away") or {}).get("runs", away.get("score"))
    if hr is None or ar is None:
        return None
    ho = _org((home.get("team") or {}).get("abbreviation")
              or (home.get("team") or {}).get("name"))
    ao = _org((away.get("team") or {}).get("abbreviation")
              or (away.get("team") or {}).get("name"))
    if not ho or not ao:
        return None
    return {
        "game_pk": g.get("gamePk"),
        "season": str(g.get("season") or ""),
        "date": g.get("officialDate") or fallback_date,
        "home_org": ho, "away_org": ao,
        "home_runs": int(hr), "away_runs": int(ar),
        "innings": line.get("currentInning"),
        "home_sp": (home.get("probablePitcher") or {}).get("id"),
        "away_sp": (away.get("probablePitcher") or {}).get("id"),
    }


def fetch_finals(start_date: str, end_date: str, *, log_fn=None) -> list[dict]:
    """Final regular-season MLB games in a date range, straight from StatsAPI.

    ONE request for the whole range. This exists so the results set does not
    depend on the Statcast feed cache filling up as a side effect of an
    unrelated job: measured on 2026-08-06, .cache/game_feeds held 0 of 15 games
    for 2026-08-05 and 0 of 11 for 2026-08-06, so the feed walk could not have
    seen a single game the leaderboard vintages were able to price."""
    import feed_cache
    resp = feed_cache.SESSION.get(
        SCHEDULE_API,
        params={"sportId": 1, "startDate": start_date, "endDate": end_date,
                "gameType": "R", "hydrate": "probablePitcher,linescore"},
        timeout=30)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for d in data.get("dates") or []:
        for g in d.get("games") or []:
            row = _row_from_schedule(g, d.get("date"))
            if row and row.get("game_pk"):
                out.append(row)
    if log_fn:
        log_fn(f"betting_model: StatsAPI returned {len(out)} final games "
               f"for {start_date}..{end_date}")
    return out


def _topup_game_cache(cached: list[dict], *, log_fn=None) -> tuple[list[dict], bool]:
    """Extend the cached results with anything final since the last cached date.

    THE BUG THIS FIXES (2026-08-06). build_game_cache returned the cached file
    whenever it existed and the ONLY caller passed no force, so the results set
    could never advance past the day it was first written. It sat at
    2026-08-04 while the first vintage-gradable game date was 2026-08-06, which
    means every game the vintages could honestly price was outside the results
    set and `n_graded` was structurally pinned at 0 no matter how many nightly
    vintages accrued. The validation clock read as running and was not.

    Re-fetches the LAST cached date as well as everything after it, because a
    late-finishing game is written while that date is still the newest one and
    would otherwise be skipped forever.

    A fetch failure returns the cache untouched and says so. Results are the
    input to a published record; degrading them silently is worse than being a
    day behind."""
    today = _dt.date.today().isoformat()
    season = today[:4]

    # ANCHOR TO ONE SEASON. The schedule endpoint honours a date RANGE, not a
    # season, so a range that spans an offseason returns both: measured live,
    # 2025-09-20..2026-04-10 came back {'2026': 206, '2025': 121}. Merging that
    # would pool two seasons into one file, and every production caller reads
    # completed_games(None), so the fit would regress last season's outcomes
    # against THIS season's live team ratings and the published n_games would
    # roughly double at the rollover.
    #
    # docs/diamond-betting.md is explicit that this sample must not exist: a
    # partial 2026 tail plus an early 2027 run "should not" be accepted as one
    # sample, "the leaderboards reset between seasons". Resuming inside the
    # current season is what keeps the honest sample honest.
    #
    # Ignoring dates at or beyond today also stops a single bad or future-dated
    # row from making `last >= today` true forever, which would silently freeze
    # the top-up: the exact failure this function exists to fix.
    in_season = [r.get("date") for r in cached
                 if r.get("date") and r["date"] < today
                 and str(r.get("season") or r["date"][:4]) == season]
    # First run of a new season: start at the season boundary rather than
    # reaching back across the offseason.
    last = max(in_season) if in_season else f"{season}-01-01"
    try:
        fresh = fetch_finals(last, today, log_fn=log_fn)
    except Exception as exc:                                  # noqa: BLE001
        log.warning("betting_model: could not refresh completed games from "
                    "StatsAPI (%s); serving the cache, last game %s", exc, last)
        return cached, False

    if not fresh:
        # A 200 with zero usable rows is not the same as "no new games", and
        # treating it as such is exactly the empty-but-valid failure this
        # module keeps meeting. It happens for real when a hydrate key is
        # renamed and _row_from_schedule starts returning None for everything.
        # Logged through the module logger, not log_fn, because the production
        # caller passes no log_fn and this must not be silent there.
        log.warning("betting_model: StatsAPI returned no usable final games for "
                    "%s..%s. If games were played in that window the response "
                    "shape has changed and the results set is now frozen.",
                    last, today)
        return cached, False

    by_pk = {r["game_pk"]: r for r in cached if r.get("game_pk")}
    before = len(by_pk)
    # CONTENT change, not just cardinality. The range deliberately re-reads the
    # last cached date to catch a game that finished late, and a corrected score
    # replaces a row without changing the count. Deciding to write on `added`
    # alone would return the corrected rows to this caller and leave the wrong
    # ones on disk, so the next process would read the stale score back.
    changed = False
    for r in fresh:
        if str(r.get("season") or (r.get("date") or "")[:4]) != season:
            continue        # belt and braces: never let a neighbouring season in
        pk = r["game_pk"]
        if by_pk.get(pk) != r:
            changed = True
        by_pk[pk] = r
    rows = sorted(by_pk.values(),
                  key=lambda r: (r.get("date") or "", r.get("game_pk") or 0))
    added = len(rows) - before
    if changed:
        log.info("betting_model: results now through %s (+%d new, %d fetched)",
                 max(r.get("date") or "" for r in rows), added, len(fresh))
        if log_fn:
            log_fn(f"betting_model: +{added} completed game(s), now through "
                   f"{max(r.get('date') or '' for r in rows)}")
    return rows, changed


def build_game_cache(*, force: bool = False, refresh: bool = True,
                     log_fn=None) -> list[dict]:
    """Completed MLB games as compact rows.

    Two doors. The FULL build walks .cache/game_feeds, which is a 1.5GB scan of
    ~18k mostly-minor-league files, so it runs once and is cached. Every
    subsequent call tops the cache up from the StatsAPI schedule instead, which
    is one request.

    That split is the fix for the frozen-cache bug described on _topup_game_cache.
    Pass refresh=False for an offline read that is guaranteed not to touch the
    network."""
    GAME_CACHE.mkdir(parents=True, exist_ok=True)
    out_path = GAME_CACHE / "completed_games.json"
    if out_path.exists() and not force:
        cached = _load_json(out_path)
        if isinstance(cached, list) and cached:
            if not refresh:
                return cached
            rows, changed = _topup_game_cache(cached, log_fn=log_fn)
            if changed:
                _write_rows(out_path, rows)
            return rows
    rows: list[dict] = []
    paths = _mlb_feed_paths()
    if log_fn:
        log_fn(f"betting_model: scanning {len(paths)} MLB feeds")
    for p in paths:
        d = _load_json(p)
        if not isinstance(d, dict):
            continue
        gd = d.get("gameData") or {}
        if (gd.get("status") or {}).get("abstractGameState") != "Final":
            continue
        game = gd.get("game") or {}
        if game.get("type") != "R":
            continue
        teams = gd.get("teams") or {}
        line = ((d.get("liveData") or {}).get("linescore") or {})
        lt = line.get("teams") or {}
        hr, ar = (lt.get("home") or {}).get("runs"), (lt.get("away") or {}).get("runs")
        if hr is None or ar is None:
            continue
        pp = gd.get("probablePitchers") or {}
        rows.append({
            "game_pk": game.get("pk"),
            "season": str(game.get("season") or ""),
            "date": (gd.get("datetime") or {}).get("officialDate"),
            "home_org": _org((teams.get("home") or {}).get("abbreviation")
                             or (teams.get("home") or {}).get("name")),
            "away_org": _org((teams.get("away") or {}).get("abbreviation")
                             or (teams.get("away") or {}).get("name")),
            "home_runs": int(hr), "away_runs": int(ar),
            "innings": line.get("currentInning"),
            "home_sp": (pp.get("home") or {}).get("id"),
            "away_sp": (pp.get("away") or {}).get("id"),
        })
    rows = [r for r in rows if r["home_org"] and r["away_org"]]

    # COLD BOOTSTRAP. The feed walk finds nothing on a box whose .cache/game_feeds
    # is empty or has been pruned, and on 2026-08-06 that was the live state:
    # 0 of 15 feeds for 2026-08-05 and 0 of 11 for 2026-08-06. Writing that empty
    # result and returning it would persist an empty-but-valid [] that every
    # consumer reads as "no games have been played", and because the top-up
    # branch above requires a NON-EMPTY cache, the StatsAPI door could never be
    # reached to repair it. The walk would simply run again, find nothing again,
    # and the results set would be permanently zero.
    #
    # So when the walk comes back empty, fall through to StatsAPI for the season
    # rather than committing the empty answer.
    if not rows and refresh:
        log.warning("betting_model: the game-feed walk found no completed MLB "
                    "games (%d MLB feeds on disk). Falling back to StatsAPI for "
                    "the season rather than caching an empty results set.",
                    len(paths))
        try:
            season = str(_dt.date.today().year)
            rows = fetch_finals(f"{season}-01-01", _dt.date.today().isoformat(),
                                log_fn=log_fn)
            rows.sort(key=lambda r: (r.get("date") or "", r.get("game_pk") or 0))
        except Exception as exc:                              # noqa: BLE001
            log.error("betting_model: StatsAPI bootstrap failed too (%s); the "
                      "results set stays EMPTY and every betting number "
                      "downstream is unfitted", exc)

    if not rows:
        # Never persist an empty results set. A missing file re-tries next run;
        # a committed [] looks like a legitimately empty season forever.
        log.error("betting_model: refusing to cache an EMPTY completed-games "
                  "set; leaving %s as it was so the next run retries",
                  out_path.name)
        return rows

    _write_rows(out_path, rows)
    if log_fn:
        log_fn(f"betting_model: cached {len(rows)} completed games -> {out_path}")
    return rows


def completed_games(season: str | None = None, *, refresh: bool = True) -> list[dict]:
    rows = build_game_cache(refresh=refresh)
    return [r for r in rows if not season or r.get("season") == str(season)]


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------
def _design_rows(games: list[dict], teams: dict, parks: dict, starters: dict,
                 resolve=None):
    """Two rows per game (each side as the scoring side) -> (X, y, meta).

    `resolve(game) -> (teams, starters, parks) | None` swaps in per-game
    features, so the SAME design code serves the live path and the vintage path.
    A game the resolver declines is dropped, never quietly graded on the
    fallback. The PARK comes out of the resolver too: it is a fitted feature
    (b3), so a resolver-supplied game whose park still came from the caller's
    live index would leak into the coefficient itself."""
    X, y, meta = [], [], []
    for g in games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        h, a = gt.get(g["home_org"]), gt.get(g["away_org"])
        if not h or not a:
            continue
        park = (gpk.get(g["home_org"]) or 1.0) - 1.0
        zp_home, _ = game_prevention_z(h, gs.get(g.get("home_sp")), gt)
        zp_away, _ = game_prevention_z(a, gs.get(g.get("away_sp")), gt)
        X.append([1.0, h["z_off"], zp_away, park, 1.0])
        y.append(float(g["home_runs"]))
        meta.append((g, "home"))
        X.append([1.0, a["z_off"], zp_home, park, 0.0])
        y.append(float(g["away_runs"]))
        meta.append((g, "away"))
    return X, y, meta


_COEFF_KEYS = ("b0", "b1", "b2", "b3", "b4")


def _ridge_beta(X, y, lam: float, prior, penalize, signs):
    """Sign-constrained ridge toward a prior, solved exactly.

        argmin (1/n)*||y - X b||^2 + lam * sum_j d_j * (b_j - m_j)^2
        subject to  sign_j * b_j >= 0  on the constrained coefficients

    EXACT, NOT ITERATIVE, and that matters: an iterative projection would make
    the fit depend on a step size nobody registered. The feasible set is an
    orthant in three of the five coordinates and the objective is a convex
    quadratic, so the minimiser sits on one of the 2^3 faces obtained by pinning
    a subset of the constrained coefficients to their boundary at zero. Each
    face is one small linear solve; the answer is the feasible face with the
    lowest objective, which is the constrained optimum by KKT.

    Returns (beta, pinned index tuple), or (None, ()) when every face is
    singular."""
    import numpy as np

    A = np.asarray(X, dtype=float)
    b = np.asarray(y, dtype=float)
    n, k = A.shape
    m = np.asarray(prior, dtype=float)
    d = np.asarray([1.0 if q else 0.0 for q in penalize], dtype=float)
    G = (A.T @ A) / n + lam * np.diag(d)
    c = (A.T @ b) / n + lam * (d * m)
    cons = [j for j in range(k) if signs[j]]
    best = None
    for mask in range(1 << len(cons)):
        pinned = tuple(cons[i] for i in range(len(cons)) if (mask >> i) & 1)
        free = [j for j in range(k) if j not in pinned]
        try:
            sol = np.linalg.solve(G[np.ix_(free, free)], c[free])
        except np.linalg.LinAlgError:                          # pragma: no cover
            continue
        beta = np.zeros(k)
        beta[free] = sol
        if any(signs[j] * beta[j] < -1e-12 for j in cons):
            continue
        resid = b - A @ beta
        obj = float((resid ** 2).mean()) + lam * float((d * (beta - m) ** 2).sum())
        if best is None or obj < best[0]:
            best = (obj, beta, pinned)
    if best is None:                                           # pragma: no cover
        return None, ()
    return best[1], best[2]


def _ridge_fit_from_design(X, y, lam: float) -> dict | None:
    """`_ridge_beta` wrapped in the same dict shape the OLS path returns, so a
    caller reading `coefficients()` cannot tell which solver produced it except
    by reading `source`, which is the point."""
    import numpy as np

    prior = [float(LITERATURE_COEFFS[k]) for k in _COEFF_KEYS]
    penalize = [k in RIDGE_PENALIZED_TERMS for k in _COEFF_KEYS]
    signs = [RIDGE_SIGN_CONSTRAINTS.get(k, 0) for k in _COEFF_KEYS]
    beta, pinned = _ridge_beta(X, y, lam, prior, penalize, signs)
    if beta is None:                                           # pragma: no cover
        return None
    A, b = np.asarray(X, dtype=float), np.asarray(y, dtype=float)
    resid = b - A @ beta
    ss_tot = float(((b - b.mean()) ** 2).sum())
    out = {k: float(beta[i]) for i, k in enumerate(_COEFF_KEYS)}
    out.update({
        # The source string is this path's whole honesty contract: the page
        # prints it and `coefficients()["source"]` is what a reader audits.
        "source": "ridge-to-literature",
        "n_rows": len(X),
        "rmse": float(math.sqrt(float((resid ** 2).mean()))),
        "r2": float(1.0 - float((resid ** 2).sum()) / ss_tot) if ss_tot else None,
        "penalty": float(lam),
        "prior": "LITERATURE_COEFFS",
        "sign_constraints": {k: ("positive" if v > 0 else "negative")
                             for k, v in sorted(RIDGE_SIGN_CONSTRAINTS.items())},
        "sign_constraints_binding": [_COEFF_KEYS[i] for i in pinned],
    })
    return out


def choose_ridge_penalty(games, teams, parks, starters, resolve=None, *,
                         grid=None) -> dict:
    """The penalty, chosen ON THE FIT HALF and nowhere else.

    Split the fit half by DATE at RIDGE_INNER_SPLIT_Q, fit the ridge at every
    penalty on the inner-fit part, re-solve `diff_shrink` there for each one,
    and score moneyline log loss on the inner-eval part. Lowest log loss wins.

    TWO DELIBERATE CHEAPNESSES, stated because both are choices. The home
    adjustment is left at 0 for the sweep and the tie rate is the inner-fit
    rate: this is a RANKING over penalties, not a published level, and the home
    adjustment is a mean recentring that moves every arm the same way. Second, a
    window too small to split returns the grid smallest non-zero penalty with a
    `basis` that says so, rather than silently returning 0: 0 is the weakest
    member of the family, and defaulting to it on a technicality would hide that
    nothing was measured. 0 is not the OLS wherever a sign constraint binds,
    which is the case on this repo's vintage window.

    Returns {"penalty", "basis", "grid": [...], "n_inner_fit", "n_inner_eval"}."""
    grid = list(grid if grid is not None else RIDGE_PENALTY_GRID)
    dates = sorted({g.get("date") for g in games if g.get("date")})
    fallback = {"penalty": float(min([q for q in grid if q > 0] or [0.0])),
                "basis": "no inner split: the fit half is too small to hold one",
                "grid": [], "n_inner_fit": 0, "n_inner_eval": 0}
    if len(dates) < 4:
        return fallback
    idx = max(1, min(int(len(dates) * RIDGE_INNER_SPLIT_Q), len(dates) - 1))
    cut = dates[idx]
    inner_fit = [g for g in games if (g.get("date") or "") < cut]
    inner_ev = [g for g in games if (g.get("date") or "") >= cut]
    if (len(inner_fit) < RIDGE_MIN_INNER_FIT_GAMES
            or len(inner_ev) < RIDGE_MIN_INNER_EVAL_GAMES):
        return fallback
    Xi, yi, _ = _design_rows(inner_fit, teams, parks, starters, resolve)
    if len(Xi) < 200:
        return fallback
    tie = _fit_tie_home(inner_fit)
    rows, best = [], None
    for lam in grid:
        co = _ridge_fit_from_design(Xi, yi, lam)
        if not co:                                             # pragma: no cover
            continue
        shrink, _ = _solve_diff_shrink(inner_fit, teams, parks, starters, co, tie,
                                       0.0, resolve, None)
        ps, ys = _p_home_series(inner_ev, teams, parks, starters, co, tie, 0.0,
                                shrink, resolve, None)
        ll = _logloss(ps, ys) if ps else None
        rows.append({"penalty": lam,
                     "log_loss": round(ll, 6) if ll is not None else None,
                     "diff_shrink": shrink,
                     "b1": round(co["b1"], 6), "b2": round(co["b2"], 6),
                     "b3": round(co["b3"], 6),
                     "binding": co["sign_constraints_binding"]})
        if ll is not None and (best is None or ll < best[1]):
            best = (lam, ll)
    if best is None:                                           # pragma: no cover
        return fallback
    return {
        "penalty": float(best[0]),
        "basis": (f"lowest moneyline log loss ({best[1]:.6f}) on an inner date split "
                  f"of the fit half at q={RIDGE_INNER_SPLIT_Q}"),
        "grid": rows,
        "inner_split_date": cut,
        "n_inner_fit": len(inner_fit),
        "n_inner_eval": len(inner_ev),
    }


def fit_coefficients(games: list[dict] | None = None, *, teams=None, parks=None,
                     starters=None, resolve=None, ridge: bool | None = None,
                     penalty: float | None = None) -> dict | None:
    """The five run-scoring coefficients. None when there is nothing to fit on
    (no feed cache), which is what sends `coefficients()` to the literature
    priors.

    TWO SOLVERS, ONE SEAM. `ridge=None` reads SERVE_RIDGE_FIT, so the switch is
    that one constant and the persisted `source` moves with it:

      OLS                    `source: "fitted"`, plain lstsq, the incumbent.
      ridge-to-literature    `source: "ridge-to-literature"`, shrunk toward
                             LITERATURE_COEFFS under RIDGE_SIGN_CONSTRAINTS,
                             penalty chosen on this window own inner split.

    `ridge=` and `penalty=` are the gate lab handles and no serving caller
    passes them: `ridge_fit_gate` needs both arms on the same window, which is
    exactly what a served flag cannot give it."""
    import numpy as np

    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    games = games if games is not None else completed_games()
    if not games or (not teams and resolve is None):
        return None
    X, y, _ = _design_rows(games, teams, parks, starters, resolve)
    if len(X) < 200:
        return None
    use_ridge = SERVE_RIDGE_FIT if ridge is None else bool(ridge)
    if use_ridge:
        if penalty is None:
            pick = choose_ridge_penalty(games, teams, parks, starters, resolve)
            lam, basis = pick["penalty"], pick["basis"]
        else:
            lam, basis = float(penalty), "supplied by the caller (gate lab)"
        out = _ridge_fit_from_design(X, y, lam)
        if out:
            out["penalty_basis"] = basis
            return out
        log.warning("betting_model: ridge fit failed, falling back to OLS")
    A, b = np.asarray(X, dtype=float), np.asarray(y, dtype=float)
    beta, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = b - A @ beta
    ss_tot = float(((b - b.mean()) ** 2).sum())
    return {
        "b0": float(beta[0]), "b1": float(beta[1]), "b2": float(beta[2]),
        "b3": float(beta[3]), "b4": float(beta[4]),
        "source": "fitted",
        "n_rows": len(X),
        "rmse": float(math.sqrt(float((resid ** 2).mean()))),
        "r2": float(1.0 - float((resid ** 2).sum()) / ss_tot) if ss_tot else None,
    }


def _lambda_rows(games, teams, parks, starters, coeffs, adj, shrink, resolve=None):
    """[(lam, observed runs)] over both scoring sides of every game, at the
    given corrections. This is the design the dispersion is fitted CONDITIONAL
    on: alpha answers "given the mean this model already predicts, how much
    more variance is there", so it must see the same lambdas the pricer will,
    home adjustment and differential shrink included."""
    rows = []
    for g in games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        er = expected_runs(g["home_org"], g["away_org"],
                           home_sp=gs.get(g.get("home_sp")),
                           away_sp=gs.get(g.get("away_sp")),
                           teams=gt, parks=gpk, coeffs=coeffs,
                           home_adj=adj, diff_shrink=shrink)
        if not er:
            continue
        rows.append((er["lam_home"], int(g["home_runs"])))
        rows.append((er["lam_away"], int(g["away_runs"])))
    return rows


def _nb2_loglik(rows, alpha: float | None) -> float:
    """Sum of log p(k | lam) over side rows. `alpha=None` is Poisson.

    Both branches walk the SAME recurrence they price with, in log space, so
    the likelihood being maximized and the distribution being served cannot be
    two different objects."""
    r = _alpha_to_r(alpha)
    s = 0.0
    if r is None:
        for lam, k in rows:
            lp = -lam
            for j in range(1, k + 1):
                lp += math.log(lam / j)
            s += lp
        return s
    for lam, k in rows:
        lp = r * math.log(r / (r + lam))
        lr = math.log(lam / (r + lam))
        for j in range(1, k + 1):
            lp += math.log((j - 1 + r) / j) + lr
        s += lp
    return s


def fit_run_alpha(rows, *, tol: float = 1e-5) -> tuple[float | None, float, float]:
    """(alpha, NB2 log-likelihood, Poisson log-likelihood) by conditional MLE.

    ONE parameter, golden-section over a bounded interval, no derivatives and
    no library: the objective is unimodal in alpha for fixed means, and the
    bracket is the physical range (alpha 0 is Poisson, alpha 2 is a variance
    ten times the mean at league scale). Deterministic: the section is a fixed
    contraction on a fixed interval, so two runs on the same rows return the
    same digits.

    Returns alpha None when the search lands on the floor, which is the honest
    way to say "no dispersion detected" rather than serving a fake 1e-4."""
    if not rows:
        return None, 0.0, 0.0
    lo, hi = RUN_DISPERSION_MIN_ALPHA, RUN_DISPERSION_MAX_ALPHA
    inv_phi = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = hi - inv_phi * (hi - lo), lo + inv_phi * (hi - lo)
    f1, f2 = _nb2_loglik(rows, x1), _nb2_loglik(rows, x2)
    while hi - lo > tol:
        if f1 < f2:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + inv_phi * (hi - lo)
            f2 = _nb2_loglik(rows, x2)
        else:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - inv_phi * (hi - lo)
            f1 = _nb2_loglik(rows, x1)
    alpha = round((lo + hi) / 2.0, 5)
    ll_pois = _nb2_loglik(rows, None)
    if alpha <= RUN_DISPERSION_MIN_ALPHA:
        return None, ll_pois, ll_pois
    return alpha, _nb2_loglik(rows, alpha), ll_pois


def _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj, shrink,
                   resolve=None, run_alpha=None):
    """(predicted p_home, observed home win) for every game. The inner loop of
    both solvers and of the grader, written once so they cannot drift apart.
    `resolve` has the same contract as in `_design_rows`."""
    ps, ys = [], []
    for g in games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        gp = game_probabilities(g["home_org"], g["away_org"],
                                home_sp=gs.get(g.get("home_sp")),
                                away_sp=gs.get(g.get("away_sp")),
                                teams=gt, parks=gpk, coeffs=coeffs,
                                tie_home=tie_home, home_adj=adj, diff_shrink=shrink,
                                run_alpha=run_alpha)
        if gp:
            ps.append(gp["p_home"])
            ys.append(1 if g["home_runs"] > g["away_runs"] else 0)
    return ps, ys


def _solve_home_adj(games, teams, parks, starters, coeffs, tie_home, target: float,
                    shrink: float = 1.0, resolve=None, run_alpha=None) -> float:
    """The run-differential shift that makes the model's MEAN home win
    probability equal the observed home win rate. Bisection over a bounded
    interval; one parameter, one target, no free lunch. See the docstring on
    expected_runs for why the raw fit needs it.

    `run_alpha` is threaded because widening the run distribution flattens
    P(home) at a fixed differential, so the adjustment that hits the observed
    home rate under Poisson is not the one that hits it under NB2."""
    def mean_p(adj: float) -> float:
        ps, _ = _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj,
                               shrink, resolve, run_alpha)
        return sum(ps) / len(ps) if ps else 0.5

    lo, hi = -0.60, 1.20
    if mean_p(lo) > target or mean_p(hi) < target:
        return 0.0
    for _ in range(20):
        mid = (lo + hi) / 2.0
        if mean_p(mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 4)


def _solve_diff_shrink(games, teams, parks, starters, coeffs, tie_home,
                       adj: float = 0.0, resolve=None,
                       run_alpha=None) -> tuple[float, float]:
    """(shrink, log loss) minimizing log loss over a coarse-to-fine grid.

    ONE parameter. A value below 1 means the linear predictor spread the
    league further apart than the results did, which is the normal failure
    mode for a model built out of season-long rate stats: the inputs are
    themselves shrunk estimates, and stacking them recovers less signal than
    their spread implies.

    `run_alpha` is threaded because this shrink was fitted to fix moneyline
    OVERCONFIDENCE UNDER POISSON, and a wider run distribution is itself a
    de-confidencing device. Leaving it pinned at its Poisson value and then
    switching dispersion on would double-shrink the moneyline and would rig a
    Poisson-versus-NB comparison in the wrong direction: a tuned incumbent
    against an untuned challenger."""
    def ll(s: float) -> float:
        ps, ys = _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj, s,
                                resolve, run_alpha)
        return _logloss(ps, ys) if ps else 9.9

    best_s, best_l = 1.0, ll(1.0)
    for step, span in ((0.1, 8), (0.02, 5)):
        centre = best_s
        for i in range(-span, span + 1):
            s = round(centre + i * step, 4)
            if s < 0.2 or s > 1.6:
                continue
            loss = ll(s)
            if loss < best_l:
                best_s, best_l = s, loss
    return best_s, round(best_l, 6)


def build_context(*, season: str | None = None, write: bool = True, log_fn=None) -> dict:
    """Fit the coefficients and measure the league constants, then write
    data/betting_model_context.json. Offline; safe to re-run."""
    games = completed_games(season)
    teams, parks, starters = team_inputs(), park_index(), starter_inputs()
    coeffs = fit_coefficients(games, teams=teams, parks=parks, starters=starters)
    n = len(games)
    lg_rpg = (sum(g["home_runs"] + g["away_runs"] for g in games) / (2.0 * n)) if n else None
    home_wins = sum(1 for g in games if g["home_runs"] > g["away_runs"])
    home_rate = (home_wins / n) if n else None
    extras = [g for g in games if (g.get("innings") or 9) > 9]
    x_wins = sum(1 for g in extras if g["home_runs"] > g["away_runs"])
    tie_raw = (x_wins / len(extras)) if extras else None
    tie_shrunk = ((x_wins + 0.5 * TIE_SHRINK_K) / (len(extras) + TIE_SHRINK_K)
                  if extras else LITERATURE_TIE_HOME)
    # The runline's reading of the same extras slice (L14-01). Measured and
    # published every run; served only when SERVE_RUNLINE_TIE_SPLIT flips.
    rl_tie_split = _fit_runline_tie_split(games)
    # THREE one-parameter corrections, solved in sequence and then refined
    # once, because all three interact. Order is alpha, shrink, adj, and it is
    # not arbitrary:
    #   alpha  is a statement about RUNS given a mean, so it moves first and is
    #          the only one that can be read off the scoring rows directly.
    #   shrink minimizes moneyline log loss, and a wider run distribution is
    #          itself a de-confidencing device, so the shrink that was right
    #          under Poisson over-shrinks under NB2.
    #   adj    targets the observed home win rate, and both of the above move
    #          the mean P(home) it is chasing.
    # Leaving shrink and adj at their Poisson values while switching dispersion
    # on would compare a TUNED incumbent against an UNTUNED challenger, which
    # is rigged against the challenger and would make a pass meaningless.
    # One refinement pass, same argument as before: the second changes shrink
    # in the third decimal.
    adj, shrink, shrink_ll = 0.0, 1.0, None
    alpha, ll_nb, ll_pois, n_disp_rows = None, None, None, 0
    platt_fit = None
    if n and coeffs:
        for i in range(2):
            rows = _lambda_rows(games, teams, parks, starters, coeffs, adj, shrink)
            alpha, ll_nb, ll_pois = fit_run_alpha(rows)
            n_disp_rows = len(rows)
            serve_alpha = alpha if SERVE_RUN_DISPERSION else None
            shrink, shrink_ll = _solve_diff_shrink(games, teams, parks, starters, coeffs,
                                                   tie_shrunk, adj, None, serve_alpha)
            adj = _solve_home_adj(games, teams, parks, starters, coeffs, tie_shrunk,
                                  home_rate, shrink, None, serve_alpha)
        # The B5 Platt MEASUREMENT (section 11b), fitted on the full in-sample
        # p_home series under the solved corrections. Published whether or not
        # it is served, the run_dispersion_alpha_fitted convention. Expect a
        # near-identity: diff_shrink was just fitted on the same rows by log
        # loss, so the response scale is already absorbed, and that showing up
        # here as (a, b) near (1, 0) is the instrument agreeing with itself.
        _ps, _ys = _p_home_series(games, teams, parks, starters, coeffs,
                                  tie_shrunk, adj, shrink, None,
                                  alpha if SERVE_RUN_DISPERSION else None)
        _ab = fit_platt(_ps, _ys)
        if _ab:
            platt_fit = {"a": round(_ab[0], 5), "b": round(_ab[1], 5),
                         "n": len(_ps)}
    # BET1: the total recentre, fitted for THESE coefficients and corrections on
    # the vintage fit half alone. A failure here must not cost the context file
    # the moneyline depends on, so it degrades to a stated null.
    total_level_fit = None
    if n and coeffs:
        try:
            total_level_fit = fit_total_level_vintage(games, coeffs=coeffs,
                                                      adj=adj, shrink=shrink)
        except Exception:                                      # noqa: BLE001
            log.warning("betting_model: total level fit failed", exc_info=True)
            total_level_fit = {"status": "failed", "centre": None}
    # 7g: the total-scoped dispersion, the same posture: a measurement always,
    # served only through SERVE_TOTAL_DISPERSION, never at the moneyline's cost.
    total_disp_fit = None
    if n and coeffs:
        try:
            total_disp_fit = fit_total_dispersion_vintage(games, coeffs=coeffs,
                                                          adj=adj, shrink=shrink)
        except Exception:                                      # noqa: BLE001
            log.warning("betting_model: total dispersion fit failed", exc_info=True)
            total_disp_fit = {"status": "failed", "alpha": None}
    total_cal_fit = None
    if n and coeffs:
        try:
            total_cal_fit = fit_total_calibration_vintage(games, coeffs=coeffs,
                                                          adj=adj, shrink=shrink)
        except Exception:                                      # noqa: BLE001
            log.warning("betting_model: total calibration fit failed", exc_info=True)
            total_cal_fit = {"status": "failed", "a": None, "b": None}
    ctx = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_version": MODEL_VERSION,
        "season": season or (games[-1]["season"] if games else None),
        "n_games": n,
        "lg_rpg": round(lg_rpg, 4) if lg_rpg else None,
        "home_win_rate": round(home_rate, 4) if home_rate else None,
        "extra_inning_games": len(extras),
        "extra_inning_home_rate_raw": round(tie_raw, 4) if tie_raw is not None else None,
        "extra_inning_home_rate_shrunk": round(tie_shrunk, 4),
        # The SERVED runline split of the tie atom (SERVE_RUNLINE_TIE_SPLIT, on
        # since 2026-09-11). Null means the whole-atom construction, every tie a
        # +1.5 cover for both sides, which is what the runline priced before.
        "extra_inning_runline_split": (rl_tie_split if SERVE_RUNLINE_TIE_SPLIT else None),
        # The MEASUREMENT, published whether or not it is served.
        "extra_inning_runline_split_fitted": rl_tie_split,
        "extra_inning_runline_split_note": (
            "how often each side that won in extra innings won by two or more, "
            "read off the same extra-inning games as extra_inning_home_rate; the "
            "runline's share of the tie is tie_home times the home conditional and "
            "(1 - tie_home) times the away one; no prior is applied because the "
            "asymmetry is the walk-off and a pooled prior would erase it; served "
            "through SERVE_RUNLINE_TIE_SPLIT (owner decision 2026-09-11, ahead of "
            "the runline margin gate, which still decides its successor)"),
        "home_field_runs_adj": adj,
        "diff_shrink": shrink,
        "diff_shrink_log_loss": shrink_ll,
        "diff_shrink_note": ("run-differential shrink fitted by log loss on completed games; "
                             "below 1.0 means the raw predictor separated clubs further than "
                             "the results did, and the fair total is untouched by it"),
        # The SERVED dispersion. Null means Poisson and the module prices
        # exactly as it did before this key existed.
        "run_dispersion_alpha": (alpha if SERVE_RUN_DISPERSION else None),
        # The MEASUREMENT, published whether or not it is served, so a reader
        # can always see how far the served distribution is from the fitted one.
        "run_dispersion_alpha_fitted": alpha,
        # The B5 calibration seam (section 11b). `prob_calibration` is the
        # SERVED map and stays null until the pre-registered two-arm gate
        # passes and SERVE_PROB_CALIBRATION flips; `prob_calibration_fitted`
        # is the full-sample measurement, published either way.
        "prob_calibration": (platt_fit if SERVE_PROB_CALIBRATION else None),
        "prob_calibration_fitted": platt_fit,
        "prob_calibration_note": ("Platt p' = sigmoid(a*logit(p) + b) on the "
                                  "moneyline only, docs/diamond-betting.md "
                                  "section 11b; served null until both gate "
                                  "arms pass, and the fitted pair is expected "
                                  "near identity because diff_shrink already "
                                  "absorbs the response scale in-sample"),
        # BET1. `total_level` is the SERVED total recentre in runs and stays null
        # until SERVE_TOTAL_LEVEL flips; `total_level_fitted` is the fit-half
        # measurement, published either way (both arms and the per-line table).
        "total_level": ((total_level_fit or {}).get("centre")
                        if SERVE_TOTAL_LEVEL else None),
        "total_level_fitted": total_level_fit,
        # 7g. The SERVED total-scoped alpha_T (null until the flag flips) and its
        # fit-half measurement, published either way.
        "total_dispersion_alpha": ((total_disp_fit or {}).get("alpha")
                                   if SERVE_TOTAL_DISPERSION else None),
        "total_dispersion_fitted": total_disp_fit,
        # 7h. The SERVED survival map [a, b] (null until the flag flips) and its
        # fit-half measurement.
        "total_calibration": ([(total_cal_fit or {}).get("a"), (total_cal_fit or {}).get("b")]
                              if SERVE_TOTAL_CALIBRATION and (total_cal_fit or {}).get("a")
                              else None),
        "total_calibration_fitted": total_cal_fit,
        "total_level_note": ("one additive constant on the Poisson TOTAL mean, fitted "
                             "on the vintage fit half by over/under log loss at "
                             "the fixed lines 7.5 to 10.5; the moneyline and the "
                             "runline never read it. The model's mean total is "
                             "right on that half; the constant corrects where a "
                             "Poisson puts its middle, which is the mean, while "
                             "real run totals split lower. docs/diamond-betting.md "
                             "section 7f"),
        "run_dispersion_rows": n_disp_rows,
        "run_dispersion_loglik_nb2": round(ll_nb, 3) if ll_nb is not None else None,
        "run_dispersion_loglik_poisson": round(ll_pois, 3) if ll_pois is not None else None,
        "run_dispersion_note": ("NB2 run dispersion, var = lam + alpha*lam^2, by conditional "
                                "MLE on both scoring sides given the model's own lambda; "
                                "Poisson (alpha 0) underdisperses real run scoring by a "
                                "measured var/mean of 2.34 per side and 2.37 on the margin. "
                                "Served only because the pre-registered four-criterion gate "
                                "in docs/diamond-betting.md section 11 passed on a held-out "
                                "half; `run_dispersion` in betting_model_eval.json carries it"),
        "home_field_note": ("the runs regression recovers almost no home field because a "
                            "home team leading after the top of the ninth never bats; the "
                            "adjustment restores the observed home win rate as a run "
                            "differential, leaving the fair total unchanged"),
        "coefficients": coeffs or dict(LITERATURE_COEFFS),
        "source_note": ("fit on completed games read out of .cache/game_feeds, offline; "
                        "team inputs are season-to-date leaderboards, so this fit is "
                        "IN-SAMPLE and cannot validate the model"),
    }
    if write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONTEXT_PATH.write_text(json.dumps(ctx, indent=1), encoding="utf-8")
        if log_fn:
            log_fn(f"betting_model: wrote {CONTEXT_PATH.name} (n={n})")
    return ctx


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------
def _brier(ps: list[float], ys: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / max(1, len(ps))


def _logloss(ps: list[float], ys: list[int]) -> float:
    eps = 1e-9
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                for p, y in zip(ps, ys)) / max(1, len(ps))


def _paired_brier_skill(ps: list[float], ys: list[int], base: float) -> dict:
    """Is the model's Brier better than a constant baseline's, and by enough?

    The pairing matters. Comparing two Brier scores game by game removes the
    game-to-game variance that dominates a raw difference of means, which is
    the only reason a 0.006 margin is measurable at all. d_i is positive when
    the model beat the baseline on that game.

        delta   mean of d_i (positive = the model is better)
        t       delta / standard error
        beats_baseline_95  t >= 1.645, i.e. the one-sided 95% lower bound on
                           delta clears zero

    `n_for_95` is how many games a margin THIS SIZE would need to reach that
    bar, which is where VINTAGE_MIN_GRADED_GAMES came from."""
    n = len(ps)
    if n < 2:
        return {"delta": None, "sd": None, "t": None,
                "beats_baseline_95": False, "n_for_95": None}
    d = [((base - y) ** 2) - ((p - y) ** 2) for p, y in zip(ps, ys)]
    mu = sum(d) / n
    var = sum((x - mu) ** 2 for x in d) / n
    sd = math.sqrt(var)
    se = sd / math.sqrt(n) if sd else 0.0
    t = (mu / se) if se else None
    return {
        "delta": round(mu, 6),
        "sd": round(sd, 5),
        "t": round(t, 3) if t is not None else None,
        "beats_baseline_95": bool(t is not None and t >= Z_95_ONE_SIDED),
        "n_for_95": (round((Z_95_ONE_SIDED * sd / mu) ** 2) if (sd and mu > 0) else None),
        "baseline": round(base, 4),
        "note": ("paired per-game Brier difference against the constant home-field "
                 "baseline; positive means the model is better, and t >= 1.645 is the "
                 "one-sided 95% bar"),
    }


def _paired_delta(incumbent: list[float], challenger: list[float]) -> dict:
    """Paired per-row loss difference, incumbent minus challenger.

    Positive means the CHALLENGER is better, on every loss this module uses
    (Brier and log loss are both smaller-is-better). `lb95` is the one-sided
    95% lower bound on the mean, which is what a non-inferiority criterion
    reads and what a superiority criterion compares to zero through `t`."""
    n = len(incumbent)
    if n < 2:
        return {"n": n, "delta": None, "sd": None, "t": None, "lb95": None}
    d = [a - b for a, b in zip(incumbent, challenger)]
    mu = sum(d) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in d) / n)
    se = sd / math.sqrt(n) if sd else 0.0
    return {
        "n": n,
        "delta": round(mu, 6),
        "sd": round(sd, 6),
        "t": round(mu / se, 3) if se else None,
        "lb95": round(mu - Z_95_ONE_SIDED * se, 6) if se else None,
    }


def _dispersion_arm(fit_games, eval_games, teams, parks, starters, coeffs, tie,
                    fit_home_rate, *, alpha_fit: bool):
    """One arm of the section 11 gate: solve every free parameter on the FIT
    half, then price the EVAL half and return the per-row losses.

    `alpha_fit` is the only difference between the two arms. Both arms re-solve
    diff_shrink and home_adj from scratch under their own distribution, in the
    same alpha -> shrink -> adj order with the same single refinement pass
    build_context uses. That is the whole reason this function exists rather
    than two ad hoc call sequences: a gate that compared a TUNED Poisson to an
    UNTUNED NB would be rigged toward the incumbent and a pass would mean
    nothing."""
    alpha, adj, shrink = None, 0.0, 1.0
    for _ in range(2):
        if alpha_fit:
            alpha, _, _ = fit_run_alpha(_lambda_rows(fit_games, teams, parks, starters,
                                                     coeffs, adj, shrink))
        shrink, _ = _solve_diff_shrink(fit_games, teams, parks, starters, coeffs, tie,
                                       adj, None, alpha)
        adj = _solve_home_adj(fit_games, teams, parks, starters, coeffs, tie,
                              fit_home_rate, shrink, None, alpha)
    ml, tl = [], []               # per-row losses on the three published markets
    rl_home, rl_away = [], []     # the runline, one series per SIDE
    ys_ml, ys_rl, ys_rl_away, ys_tl = [], [], [], []
    n_over = 0
    # The runline prices the tie atom the way the board serves it, on the FIT
    # window's own split (SERVE_RUNLINE_TIE_SPLIT; `_lab_runline_split`).
    rl_split = _lab_runline_split(fit_games)
    for g in eval_games:
        gp = game_probabilities(g["home_org"], g["away_org"],
                                home_sp=starters.get(g.get("home_sp")),
                                away_sp=starters.get(g.get("away_sp")),
                                teams=teams, parks=parks, coeffs=coeffs, tie_home=tie,
                                home_adj=adj, diff_shrink=shrink, run_alpha=alpha,
                                runline_tie_split=rl_split)
        if not gp:
            continue
        hr, ar = g["home_runs"], g["away_runs"]
        y_ml = 1 if hr > ar else 0
        p_ml = gp["p_home"]
        ml.append((p_ml - y_ml) ** 2)
        ys_ml.append(y_ml)
        # THE RUNLINE, BOTH SIDES. The board publishes four runline prices per
        # game and they are two binary events, not four: p_home_plus_1_5 is
        # 1 - p_away_minus_1_5 and p_away_plus_1_5 is 1 - p_home_minus_1_5. Log
        # loss is invariant under complementation, so scoring "home -1.5" and
        # scoring "away +1.5" produce the IDENTICAL per-row number. The two
        # distinct series are the two tails of the margin distribution:
        #   home -1.5 / away +1.5   home margin >= +2   (the right tail)
        #   away -1.5 / home +1.5   home margin <= -2   (the left tail)
        # Both are priced, both ship, and `runline_side` decides which the gate
        # reads. See DISPERSION_GATE_CRITERIA.
        y_rl = 1 if (hr - ar) >= 2 else 0
        p_rl = min(max(gp["p_home_minus_1_5"], 1e-9), 1.0 - 1e-9)
        rl_home.append(-(math.log(p_rl) if y_rl else math.log(1.0 - p_rl)))
        ys_rl.append(y_rl)
        y_rl_a = 1 if (ar - hr) >= 2 else 0
        p_rl_a = min(max(gp["p_away_minus_1_5"], 1e-9), 1.0 - 1e-9)
        rl_away.append(-(math.log(p_rl_a) if y_rl_a else math.log(1.0 - p_rl_a)))
        ys_rl_away.append(y_rl_a)
        # Over 9.0. The model's `over` callable reads P(total >= 10) on a whole
        # number, so the graded event is total >= 10 and a game landing exactly
        # on 9 scores as a non-over. That is the UNCONDITIONAL probability, the
        # right object for a scoring rule; the push-conditioned pair the board
        # prices is a separate transformation of the same pmf.
        y_tl = 1 if (hr + ar) >= 10 else 0
        p_tl = min(max(gp["over"](9.0), 1e-9), 1.0 - 1e-9)
        tl.append(-(math.log(p_tl) if y_tl else math.log(1.0 - p_tl)))
        ys_tl.append(y_tl)
        n_over += y_tl
    rows = _lambda_rows(eval_games, teams, parks, starters, coeffs, adj, shrink)
    return {
        "alpha": alpha,
        "diff_shrink": shrink,
        "home_field_runs_adj": adj,
        "brier_ml": ml, "logloss_total": tl,
        "logloss_rl_home": rl_home,
        "logloss_rl_away": rl_away,
        # Both sides of the same game, one row per game, so the pairing stays
        # one pair per game and the sd is a per-game sd.
        "logloss_rl_both": [a + b for a, b in zip(rl_home, rl_away)],
        "runs_ll_per_row": (_nb2_loglik(rows, alpha) / len(rows)) if rows else None,
        "n_runs_rows": len(rows),
        "n_eval": len(ml),
        "base_rates": {"home_win": round(sum(ys_ml) / max(1, len(ys_ml)), 4),
                       "home_minus_1_5": round(sum(ys_rl) / max(1, len(ys_rl)), 4),
                       "away_minus_1_5": round(sum(ys_rl_away) / max(1, len(ys_rl_away)), 4),
                       "over_9": round(sum(ys_tl) / max(1, len(ys_tl)), 4)},
    }


def run_dispersion_gate(games=None, *, teams=None, parks=None, starters=None,
                        split_date: str | None = None, split_q: float = 0.7,
                        runline_side: str = RUNLINE_SIDE_AMENDMENT) -> dict:
    """The pre-registered four-criterion dispersion gate, written into
    docs/diamond-betting.md section 11 BEFORE it was run.

    Split the completed-game cache by DATE at the same 70% point `backtest`
    already uses. Fit {coefficients, alpha, diff_shrink, home_field_runs_adj}
    on the fit half. On the HELD-OUT half all four must hold:

      home win        paired Brier    non-inferiority, lb95(delta) >= -0.001
      runline         paired log loss delta > 0 at t >= 1.645
      total over 9.0  paired log loss delta > 0 at t >= 1.645
      runs both sides out-of-sample log-likelihood per row, NB > Poisson

    `runline_side` is criterion 2's estimand and it is NOT cosmetic: on the
    pre-registered split the home tail fails and the away tail and the sum pass.
    The default is the amended specification (both sides, per-game sum). All
    three readings are returned in `runline_by_side` on every run, so the number
    the gate did not headline is never hidden. See RUNLINE_SIDE_AMENDMENT for
    why both-sides is the estimand and for the plain statement that the choice
    moves the verdict.

    Moneyline is NON-INFERIORITY on purpose. `diff_shrink` was fitted to fix
    moneyline overconfidence under Poisson and already absorbs that market's
    calibration, so crediting NB for beating it there would be crediting it for
    work the incumbent had already done. The two markets the distribution's
    SHAPE actually decides - the runline and the total - carry the superiority
    tests.

    This mode is the CONTAMINATED forward split: its features are
    season-to-date leaderboards. That is deliberate and it is not a leak that
    can flatter one arm, because both arms see the identical features and the
    identical fit window. The question here is only which distribution shape
    fits run scoring better, and the vintage sample (221 graded games) is far
    too small to answer it."""
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    if runline_side not in RUNLINE_SIDES:
        raise ValueError(f"runline_side must be one of {RUNLINE_SIDES}, got {runline_side!r}")
    dates = sorted({g["date"] for g in games if g.get("date")})
    sd = split_date or (dates[int(len(dates) * split_q)] if len(dates) > 20 else None)
    out = {
        "status": "not run",
        "split_date": sd,
        "split_q": round(float(split_q), 3),
        "runline_side": runline_side,
        "criteria": DISPERSION_GATE_CRITERIA,
        "criteria_v1": DISPERSION_GATE_CRITERIA_V1,
    }
    if not sd:
        out["status"] = "no split"
        return out
    fit_g = [g for g in games if (g.get("date") or "") < sd]
    ev_g = [g for g in games if (g.get("date") or "") >= sd]
    out["n_fit"], out["n_eval_games"] = len(fit_g), len(ev_g)
    if len(fit_g) <= 200 or len(ev_g) <= 50:
        out["status"] = "insufficient sample"
        return out
    coeffs = fit_coefficients(fit_g, teams=teams, parks=parks, starters=starters)
    if not coeffs:
        out["status"] = "no coefficients"
        return out
    tie = _fit_tie_home(fit_g)
    fit_home_rate = (sum(1 for g in fit_g if g["home_runs"] > g["away_runs"])
                     / max(1, len(fit_g)))
    pois = _dispersion_arm(fit_g, ev_g, teams, parks, starters, coeffs, tie,
                           fit_home_rate, alpha_fit=False)
    nb = _dispersion_arm(fit_g, ev_g, teams, parks, starters, coeffs, tie,
                         fit_home_rate, alpha_fit=True)
    ml = _paired_delta(pois["brier_ml"], nb["brier_ml"])
    # ALL THREE READINGS, ALWAYS. The gate headlines one of them; the other two
    # go into the artifact beside it so a reader can see what the choice of
    # estimand did and does not have to take the headline on trust.
    by_side = {s: _paired_delta(pois[f"logloss_rl_{s}"], nb[f"logloss_rl_{s}"])
               for s in RUNLINE_SIDES}
    for s, d in by_side.items():
        d["passes_criterion_2"] = bool(d.get("delta") is not None and d["delta"] > 0
                                       and d.get("t") is not None
                                       and d["t"] >= Z_95_ONE_SIDED)
    rl = by_side[runline_side]
    tl = _paired_delta(pois["logloss_total"], nb["logloss_total"])
    runs_delta = ((nb["runs_ll_per_row"] - pois["runs_ll_per_row"])
                  if (nb["runs_ll_per_row"] is not None
                      and pois["runs_ll_per_row"] is not None) else None)
    checks = [
        {"criterion": "moneyline (home win), paired Brier, non-inferiority",
         "test": "lb95(poisson - nb) >= -0.001",
         "value": ml.get("lb95"), "threshold": -0.001,
         "pass": bool(ml.get("lb95") is not None and ml["lb95"] >= -0.001)},
        {"criterion": f"runline ({_RUNLINE_SIDE_LABEL[runline_side]}), paired log loss, "
                      "superiority",
         "test": "delta > 0 and t >= 1.645",
         "side": runline_side,
         "value": rl.get("delta"), "t": rl.get("t"), "threshold": 0.0,
         "pass": bool(rl.get("passes_criterion_2"))},
        {"criterion": "total (over 9.0), paired log loss, superiority",
         "test": "delta > 0 and t >= 1.645",
         "value": tl.get("delta"), "t": tl.get("t"), "threshold": 0.0,
         "pass": bool(tl.get("delta") is not None and tl["delta"] > 0
                      and tl.get("t") is not None and tl["t"] >= Z_95_ONE_SIDED)},
        {"criterion": "runs, both scoring sides, out-of-sample log-likelihood per row",
         "test": "nb > poisson",
         "value": round(runs_delta, 6) if runs_delta is not None else None,
         "threshold": 0.0,
         "pass": bool(runs_delta is not None and runs_delta > 0)},
    ]
    out.update({
        "status": "ran",
        "passed": all(c["pass"] for c in checks),
        "checks": checks,
        "alpha": nb["alpha"],
        "poisson_arm": {k: pois[k] for k in
                        ("diff_shrink", "home_field_runs_adj", "runs_ll_per_row",
                         "n_runs_rows", "n_eval", "base_rates")},
        "nb2_arm": {k: nb[k] for k in
                    ("alpha", "diff_shrink", "home_field_runs_adj", "runs_ll_per_row",
                     "n_runs_rows", "n_eval", "base_rates")},
        "moneyline_brier": ml,
        "runline_logloss": rl,
        "runline_by_side": by_side,
        "runline_side_note": ("criterion 2's estimand. `home` is the log loss on home "
                              "margin >= 2 (home -1.5, equivalently away +1.5), `away` "
                              "the log loss on home margin <= -2 (away -1.5, "
                              "equivalently home +1.5), `both` their per-game sum. The "
                              "board publishes all four prices and they are these two "
                              "events; V1 of the pre-registration named no side and the "
                              "first run scored `home` alone. See "
                              "betting_model.RUNLINE_SIDE_AMENDMENT"),
        "total_logloss": tl,
        "runs_loglik_per_row_delta": round(runs_delta, 6) if runs_delta is not None else None,
        "mode": "contaminated",
        "mode_note": ("forward split on season-to-date features. Both arms see the "
                      "identical features and the identical fit window, so the "
                      "contamination cannot favour one distribution over the other; "
                      "this gate asks about SHAPE, not about skill"),
    })
    return out


def dispersion_gate_sensitivity(games=None, *, teams=None, parks=None, starters=None,
                                quantiles=DISPERSION_SPLIT_QUANTILES) -> dict:
    """The gate verdict as a function of the two things that were never pinned:
    WHICH runline side criterion 2 scores, and WHERE the date split falls.

    One gate run per split quantile. Both arms are fitted once per split and all
    three side readings come off the same per-row losses, so the grid costs
    len(quantiles) gate runs and not 3x that, and the three sides at one split
    are exactly comparable because they are the same two fitted models.

    THE SHIP RULE, and it is decided before the numbers: dispersion ships only
    if the amended criterion 2 (RUNLINE_SIDE_AMENDMENT) passes at EVERY
    quantile, together with the other three. If the amended reading passes at
    some quantiles and fails at others the gate is INDETERMINATE, and
    indeterminate does not ship. A verdict that depends on where the split lands
    is not a verdict about the distribution, it is a verdict about the split.

    Returns the full grid, including the readings the ship rule does not use.
    Nothing here is filtered by which way it resolves."""
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    runs, grid = [], []
    for q in quantiles:
        g = run_dispersion_gate(games, teams=teams, parks=parks, starters=starters,
                                split_q=q, runline_side=RUNLINE_SIDE_AMENDMENT)
        if g.get("status") != "ran":
            grid.append({"split_q": round(float(q), 3), "status": g.get("status")})
            continue
        others = [c for c in g["checks"] if not c["criterion"].startswith("runline")]
        row = {
            "split_q": round(float(q), 3),
            "split_date": g["split_date"],
            "n_fit": g["n_fit"], "n_eval_games": g["n_eval_games"],
            "alpha": g["alpha"],
            "other_three_pass": all(c["pass"] for c in others),
            "by_side": {s: {"delta": g["runline_by_side"][s]["delta"],
                            "t": g["runline_by_side"][s]["t"],
                            "pass": g["runline_by_side"][s]["passes_criterion_2"]}
                        for s in RUNLINE_SIDES},
        }
        row["gate_by_side"] = {s: bool(row["other_three_pass"] and row["by_side"][s]["pass"])
                               for s in RUNLINE_SIDES}
        grid.append(row)
        runs.append(row)
    ran = [r for r in runs if "gate_by_side" in r]
    amend = RUNLINE_SIDE_AMENDMENT
    verdicts = [r["gate_by_side"][amend] for r in ran]
    if not ran:
        verdict, ship = "not run", False
    elif all(verdicts):
        verdict, ship = "pass", True
    elif not any(verdicts):
        verdict, ship = "fail", False
    else:
        verdict, ship = "indeterminate", False
    robust = {s: ("pass" if all(r["gate_by_side"][s] for r in ran)
                  else "fail" if not any(r["gate_by_side"][s] for r in ran)
                  else "indeterminate") for s in RUNLINE_SIDES} if ran else {}
    return {
        "status": "ran" if ran else "not run",
        "quantiles": [round(float(q), 3) for q in quantiles],
        "runline_side_shipped": amend,
        "grid": grid,
        "verdict_by_side": robust,
        "verdict": verdict,
        "ship": ship,
        "rule": ("the amended criterion 2 must pass at EVERY split quantile, with the "
                 "other three criteria, or the gate is INDETERMINATE and dispersion "
                 "stays off; a verdict that moves with the split point is a verdict "
                 "about the split point"),
        "note": ("side-by-split sensitivity for the section 11a gate. `home` was the "
                 "only reading the first run reported and V1 of the pre-registration "
                 "did not name a side"),
    }


def _platt_split_verdict(brier_delta: dict, logloss_delta: dict) -> dict:
    """The 11b criteria applied to one split's paired stats. Factored out so
    the arithmetic is testable on fixtures without a model run.

    Both deltas are identity-minus-Platt, so positive means Platt is better.
    Criterion 1 is superiority on Brier (delta > 0 at one-sided t >= 1.645);
    criterion 2 is non-inferiority on log loss at the point estimate."""
    b_ok = bool(brier_delta.get("delta") is not None and brier_delta["delta"] > 0
                and brier_delta.get("t") is not None
                and brier_delta["t"] >= Z_95_ONE_SIDED)
    l_ok = bool(logloss_delta.get("delta") is not None
                and logloss_delta["delta"] >= 0)
    return {"brier_pass": b_ok, "logloss_pass": l_ok, "pass": b_ok and l_ok}


def _arm_verdict(rows: list[dict]) -> str:
    """pass / fail / indeterminate over one arm's split grid, under the ALL
    THREE OR NOTHING rule: the arm passes only when every split passes. The
    fail/indeterminate distinction is reporting, not policy; neither ships."""
    verdicts = [bool(r.get("pass")) for r in rows]
    if not verdicts:
        return "not run"
    if all(verdicts):
        return "pass"
    if not any(verdicts):
        return "fail"
    return "indeterminate"


def _per_game_losses(ps: list[float], ys: list[int]) -> tuple[list[float], list[float]]:
    """(brier per game, log loss per game), the paired series both criteria read."""
    eps = 1e-9
    briers = [(p - y) ** 2 for p, y in zip(ps, ys)]
    lls = [-(math.log(max(p, eps)) if y else math.log(max(1.0 - p, eps)))
           for p, y in zip(ps, ys)]
    return briers, lls


def _platt_score_split(ps_fit, ys_fit, ps_ev, ys_ev) -> dict:
    """Fit (a, b) on the fit half's pairs, score identity against Platt on the
    eval half. Pure function of the four series, shared by both arms so the
    ledger arm cannot quietly run different arithmetic than the vintage arm."""
    ab = fit_platt(ps_fit, ys_fit)
    if not ab:
        return {"status": "fit failed", "pass": False}
    id_b, id_l = _per_game_losses(ps_ev, ys_ev)
    cal = [apply_platt(p, ab[0], ab[1]) for p in ps_ev]
    pl_b, pl_l = _per_game_losses(cal, ys_ev)
    brier_d = _paired_delta(id_b, pl_b)
    ll_d = _paired_delta(id_l, pl_l)
    out = {
        "status": "ran",
        "a": round(ab[0], 5), "b": round(ab[1], 5),
        "brier_delta": brier_d,
        "logloss_delta": ll_d,
    }
    out.update(_platt_split_verdict(brier_d, ll_d))
    return out


def _ledger_moneyline_rows() -> list[dict]:
    """The calibration ledger's settled canonical-side moneyline games, in
    ledger (settled) order: one row per game, each carrying the SERVED model
    probability and the outcome. [] when the ledger is absent, which is the
    normal state on a fresh checkout."""
    try:
        from tools import betting_calibration as bc
        return list(bc.canonical_settled_games(bc.rows()).get("moneyline") or [])
    except Exception:                                         # noqa: BLE001
        log.debug("betting_model: calibration ledger unavailable", exc_info=True)
        return []


def prob_calibration_gate(games=None, *, teams=None, parks=None, starters=None,
                          quantiles=PROB_CALIBRATION_SPLIT_QUANTILES,
                          ledger_rows: list[dict] | None = None) -> dict:
    """The B5 gate, pre-registered in docs/diamond-betting.md section 11b
    before this function existed. Two arms, both required.

    ARM 1, VINTAGE: on the vintage-gradable games, split the gradable dates at
    each quantile, refit {coefficients, tie, diff_shrink, home_adj} on the fit
    half on vintage features (the same discipline the honest mode's _grade
    uses), fit (a, b) on the fit half's own (p_home, home win) pairs, and
    score identity against Platt on the held-out half. ALL THREE quantiles or
    nothing, floors VINTAGE_MIN_FIT_GAMES / VINTAGE_MIN_EVAL_GAMES.

    ARM 2, LEDGER: the settled canonical-side moneyline games, ACTIVE only at
    PROB_CALIBRATION_LEDGER_MIN_GAMES. Below that it is "cannot count yet" and
    the arm cannot pass, which blocks the ship whatever arm 1 says.
    `ledger_rows` exists for tests; production reads the real ledger.

    This function measures and records. It never flips SERVE_PROB_CALIBRATION;
    the flag, this block persisted in the eval artifact and the tripwire in
    test_betting_platt.py move in one commit or not at all."""
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    out = {
        "criteria": PROB_CALIBRATION_GATE_CRITERIA,
        "expectation": ("pre-registered: Platt repairs response scale, cannot "
                        "manufacture discrimination, and is not expected to open "
                        "the skill gate; converging toward the constant baseline "
                        "is a finding. diff_shrink already absorbs most of the "
                        "response scale, so a near-identity (a, b) is the honest "
                        "likely outcome"),
        "quantiles": [round(float(q), 3) for q in quantiles],
        "serving_scope": ("moneyline only for the Platt map; the runline and the total "
                          "keep the UNSERVED dispersion correction (section 11a) whatever "
                          "this block says, and since 2026-09-05 they publish under the "
                          "any-market slot policy with the caveat on the row (section 7d)"),
    }

    # --- arm 1: vintage -----------------------------------------------------
    reset_vintage_cache()
    resolve, _ = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    grid = []
    for q in quantiles:
        row = {"split_q": round(float(q), 3)}
        if len(dates) < 4:
            row.update(status="insufficient dates", **{"pass": False})
            grid.append(row)
            continue
        cut = dates[min(len(dates) - 1, max(1, int(len(dates) * q)))]
        fit_g = [g for g in gradable if (g.get("date") or "") < cut]
        ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
        row.update(split_date=cut, n_fit=len(fit_g), n_eval=len(ev_g))
        if len(fit_g) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES:
            row.update(status="below floors", **{"pass": False})
            grid.append(row)
            continue
        coeffs = fit_coefficients(fit_g, teams=teams, parks=parks,
                                  starters=starters, resolve=resolve)
        if not coeffs:
            row.update(status="no coefficients", **{"pass": False})
            grid.append(row)
            continue
        tie = _fit_tie_home(fit_g)
        fit_home_rate = (sum(1 for g in fit_g if g["home_runs"] > g["away_runs"])
                         / max(1, len(fit_g)))
        alpha = None            # dispersion is not served; see section 11a
        shrink, _sll = _solve_diff_shrink(fit_g, teams, parks, starters, coeffs,
                                          tie, 0.0, resolve, alpha)
        adj = _solve_home_adj(fit_g, teams, parks, starters, coeffs, tie,
                              fit_home_rate, shrink, resolve, alpha)
        ps_fit, ys_fit = _p_home_series(fit_g, teams, parks, starters, coeffs,
                                        tie, adj, shrink, resolve, alpha)
        ps_ev, ys_ev = _p_home_series(ev_g, teams, parks, starters, coeffs,
                                      tie, adj, shrink, resolve, alpha)
        if len(ps_ev) < VINTAGE_MIN_EVAL_GAMES:
            row.update(status="below floors after pricing", **{"pass": False})
            grid.append(row)
            continue
        row.update(diff_shrink=shrink, home_field_runs_adj=adj)
        row.update(_platt_score_split(ps_fit, ys_fit, ps_ev, ys_ev))
        grid.append(row)
    vintage_arm = {
        "n_gradable": len(gradable),
        "grid": grid,
        "verdict": _arm_verdict(grid),
        "pass": _arm_verdict(grid) == "pass",
        "mode": "vintage",
        "note": ("features dated strictly before each game; the model is refit "
                 "on each fit half, so nothing later than a split reaches "
                 "either half"),
    }

    # --- arm 2: ledger ------------------------------------------------------
    rows = list(ledger_rows) if ledger_rows is not None else _ledger_moneyline_rows()
    usable = [r for r in rows
              if isinstance(r.get("model_prob"), (int, float))
              and r.get("result") in ("won", "lost")]
    n_led = len(usable)
    ledger_arm: dict = {
        "n_games": n_led,
        "need": PROB_CALIBRATION_LEDGER_MIN_GAMES,
        "active": n_led >= PROB_CALIBRATION_LEDGER_MIN_GAMES,
        "basis": ("settled canonical-side moneyline games, one per game, from "
                  "tools/betting_calibration; the model probabilities are the "
                  "SERVED ones, priced from season-to-date inputs, which is "
                  "exactly the scale the serve seam would apply to"),
    }
    if not ledger_arm["active"]:
        ledger_arm.update({
            "status": "cannot count yet",
            "pass": False,
            "verdict": "cannot count yet",
            "note": (f"{n_led} of {PROB_CALIBRATION_LEDGER_MIN_GAMES} settled "
                     "canonical moneyline games; below the pre-registered floor "
                     "this arm counts in NEITHER direction, and the ship is "
                     "blocked whatever the vintage arm says"),
        })
    else:
        led_grid = []
        for q in quantiles:
            k = min(len(usable) - 1, max(1, int(len(usable) * q)))
            fit_rows, ev_rows = usable[:k], usable[k:]
            row = {"split_q": round(float(q), 3),
                   "n_fit": len(fit_rows), "n_eval": len(ev_rows)}
            if len(ev_rows) < 2 or len(fit_rows) < 2:
                row.update(status="degenerate split", **{"pass": False})
                led_grid.append(row)
                continue
            row.update(_platt_score_split(
                [float(r["model_prob"]) for r in fit_rows],
                [1 if r["result"] == "won" else 0 for r in fit_rows],
                [float(r["model_prob"]) for r in ev_rows],
                [1 if r["result"] == "won" else 0 for r in ev_rows]))
            led_grid.append(row)
        ledger_arm.update({
            "status": "ran",
            "grid": led_grid,
            "verdict": _arm_verdict(led_grid),
            "pass": _arm_verdict(led_grid) == "pass",
        })

    ship = bool(vintage_arm["pass"] and ledger_arm["pass"])
    if vintage_arm["verdict"] in ("fail", "indeterminate") or \
            ledger_arm.get("verdict") == "fail":
        verdict = "fail" if (vintage_arm["verdict"] == "fail"
                             or ledger_arm.get("verdict") == "fail") else "indeterminate"
    elif ship:
        verdict = "pass"
    else:
        verdict = "indeterminate"
    out.update({
        "status": "ran" if any(r.get("status") == "ran" for r in grid) else "not run",
        "vintage_arm": vintage_arm,
        "ledger_arm": ledger_arm,
        "ship": ship,
        "verdict": verdict,
        "rule": ("both arms must pass, each at ALL THREE split quantiles, or the "
                 "flag stays off; a green vintage arm alone is recorded, never "
                 "served"),
        "served": SERVE_PROB_CALIBRATION,
        "served_ab": (list(served_platt()) if served_platt() else None),
    })
    return out


# ---------------------------------------------------------------------------
# B-ML-FIT: the ridge gate (docs/diamond-betting.md section 7e)
# ---------------------------------------------------------------------------
def _ridge_arm(fit_games, eval_games, teams, parks, starters, resolve, *,
               ridge: bool) -> dict | None:
    """One arm of the section 7e gate: solve EVERY free parameter on the fit
    half, then price the eval half and return the per-game losses.

    The tie rate, `diff_shrink` and the home adjustment are re-solved for this
    arm on this arm's own fit window, for the reason the dispersion gate states
    in its own arm builder: a tuned incumbent graded against an untuned
    challenger is not a measurement, it is a rigged one. The ridge penalty is
    chosen inside the fit half too (`choose_ridge_penalty`), so the eval half
    is untouched by anything either arm fitted."""
    coeffs = fit_coefficients(fit_games, teams=teams, parks=parks, starters=starters,
                              resolve=resolve, ridge=ridge)
    if not coeffs:
        return None
    tie = _fit_tie_home(fit_games)
    fit_home_rate = (sum(1 for g in fit_games if g["home_runs"] > g["away_runs"])
                     / max(1, len(fit_games)))
    shrink, _ = _solve_diff_shrink(fit_games, teams, parks, starters, coeffs, tie,
                                   0.0, resolve, None)
    adj = _solve_home_adj(fit_games, teams, parks, starters, coeffs, tie,
                          fit_home_rate, shrink, resolve, None)
    ps, ys, pks = [], [], []
    for g in eval_games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        gp = game_probabilities(g["home_org"], g["away_org"],
                                home_sp=gs.get(g.get("home_sp")),
                                away_sp=gs.get(g.get("away_sp")),
                                teams=gt, parks=gpk, coeffs=coeffs, tie_home=tie,
                                home_adj=adj, diff_shrink=shrink, run_alpha=None)
        if not gp:
            continue
        ps.append(gp["p_home"])
        ys.append(1 if g["home_runs"] > g["away_runs"] else 0)
        pks.append(g.get("game_pk"))
    if len(ps) < 2:
        return None
    briers, lls = _per_game_losses(ps, ys)
    return {
        "coefficients": coeffs,
        "extra_inning_home_rate": round(tie, 4),
        "diff_shrink": shrink,
        "home_field_runs_adj": adj,
        "n_eval": len(ps),
        "brier": round(_brier(ps, ys), 5),
        "log_loss": round(_logloss(ps, ys), 5),
        "_ps": ps, "_ys": ys, "_pks": pks,
        "_brier_rows": briers, "_ll_rows": lls,
    }


def _ridge_arm_public(arm: dict) -> dict:
    """The arm minus its working series. The series are per-game vectors; they
    exist to be paired, not to be published, and an artifact that carried them
    would be five times its size for nothing."""
    return {k: v for k, v in (arm or {}).items() if not k.startswith("_")}


def fit_window_probe(games=None, *, teams=None, parks=None, starters=None,
                     quantiles=None, ridge: bool = False) -> dict:
    """Does the vintage fit window earn its extra games? A PAIRED answer.

    The question VINTAGE_FIT_WINDOW_GROWS asks cannot be answered by comparing
    the two shipped configurations, because they have DIFFERENT eval windows:
    the fit half and the eval half are complements, so growing one shrinks the
    other and the two Brier numbers are not paired. This probe fixes that by
    holding the eval window and varying only the fit:

      ANCHORED  the earliest VINTAGE_FIT_TARGET_GAMES games before the cut,
                which is what the shipped rule uses however long the archive is
      GROWN     every gradable game before the same cut

    Both arms price the SAME eval games with all their corrections re-solved on
    their own fit window, so the difference is the fit window and nothing else.

    IT DOES NOT PRICE THE COST. Growing the fit window takes games off the
    VINTAGE_MIN_GRADED_GAMES clock one for one (79 of them on the 2026-09-06
    archive), and no paired statistic can see that, because those games are the
    ones the paired statistic would need to exist."""
    qs = tuple(quantiles if quantiles is not None else DISPERSION_SPLIT_QUANTILES)
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    out = {
        "question": ("is the OLS fit on every gradable game before the cut better than "
                     "the fit on the earliest VINTAGE_FIT_TARGET_GAMES of them, on the "
                     "SAME eval window"),
        "arm": "ridge" if ridge else "ols",
        "quantiles": list(qs),
        "cost_not_priced": ("growth takes eval games one for one; on the 2026-09-06 "
                            "archive the shipped rule leaves 487 eval games and a date "
                            "share split leaves 408, which is 79 fewer on the "
                            "VINTAGE_MIN_GRADED_GAMES clock"),
    }
    if not games or not teams:
        out["status"] = "no data"
        return out
    reset_vintage_cache()
    resolve, _ = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out["status"] = "insufficient vintage coverage"
        return out
    rows = []
    for q in qs:
        cut = dates[max(1, min(int(len(dates) * q), len(dates) - 1))]
        before = sorted([g for g in gradable if (g.get("date") or "") < cut],
                        key=lambda r: (r.get("date") or "", r.get("game_pk") or 0))
        ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
        # ANCHORED keeps whole slates, the same way the shipped cut does.
        anchored, cum = [], 0
        for d in sorted({g.get("date") for g in before if g.get("date")}):
            same = [g for g in before if g.get("date") == d]
            # The slate that CROSSES the target is included, which is what
            # `_vintage_cut_index` does (target_idx = i + 1). Stopping short of
            # it would probe a fit window the shipped rule never builds.
            anchored.extend(same)
            cum += len(same)
            if cum >= VINTAGE_FIT_TARGET_GAMES:
                break
        row = {"split_q": q, "split_date": cut, "n_eval": len(ev_g),
               "n_fit_anchored": len(anchored), "n_fit_grown": len(before)}
        if (len(anchored) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES
                or len(before) <= len(anchored)):
            row["status"] = "no contrast at this split"
            rows.append(row)
            continue
        a = _ridge_arm(anchored, ev_g, teams, parks, starters, resolve, ridge=ridge)
        b = _ridge_arm(before, ev_g, teams, parks, starters, resolve, ridge=ridge)
        if not a or not b or a["_pks"] != b["_pks"]:
            row["status"] = "arms did not price the same games"
            rows.append(row)
            continue
        row.update({
            "status": "ran",
            "anchored": _ridge_arm_public(a),
            "grown": _ridge_arm_public(b),
            "brier_delta": _paired_delta(a["_brier_rows"], b["_brier_rows"]),
            "log_loss_delta": _paired_delta(a["_ll_rows"], b["_ll_rows"]),
        })
        rows.append(row)
    ran = [r for r in rows if r.get("status") == "ran"]
    out["grid"] = rows
    out["status"] = "ran" if ran else "no contrast"
    out["rule"] = ("grow only if the grown arm is non-inferior at every split on the "
                   "same bar the ridge gate uses, paired Brier lb95 >= -0.001. The bar "
                   "is REUSED rather than invented, and the clause was fixed before "
                   "the grid below was read")
    out["non_inferior_everywhere"] = bool(ran and all(
        (r["brier_delta"].get("lb95") is not None
         and r["brier_delta"]["lb95"] >= -0.001) for r in ran))
    out["served"] = VINTAGE_FIT_WINDOW_GROWS
    return out


def ridge_fit_gate(games=None, *, teams=None, parks=None, starters=None,
                   quantiles=None, log_fn=None) -> dict:
    """The pre-registered gate on the ridge fit (RIDGE_FIT_GATE_CRITERIA).

    Runs on the VINTAGE-gradable sample only, because the contaminated modes
    cannot adjudicate a fit: their features contain the games being graded, and
    a shrinkage repair aimed at 610 noisy rows would be scored against a design
    where the noise is not noise. Both arms see the identical window, the
    identical features and the identical corrections machinery, so the only
    thing that differs between them is the solver.

    THE VERDICT IS NOT `passed` ON ONE SPLIT. It is taken across
    DISPERSION_SPLIT_QUANTILES, the same discipline section 11a arrived at the
    hard way: a verdict that moves with the split point is a verdict about the
    split point."""
    qs = tuple(quantiles if quantiles is not None else DISPERSION_SPLIT_QUANTILES)
    out = {
        "criteria": RIDGE_FIT_GATE_CRITERIA,
        "quantiles": list(qs),
        "surface": ("gate lab only: no served price reads either arm until "
                    "SERVE_RIDGE_FIT flips"),
    }
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    if not games or not teams:
        out.update({"status": "no data", "verdict": "indeterminate", "ship": False,
                    "served": SERVE_RIDGE_FIT})
        return out
    reset_vintage_cache()
    resolve, _rstats = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    out["n_gradable"] = len(gradable)
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out.update({"status": "insufficient vintage coverage",
                    "verdict": "indeterminate", "ship": False,
                    "served": SERVE_RIDGE_FIT,
                    "note": (f"{len(gradable)} vintage-gradable games; the gate needs "
                             f"{VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES} to "
                             "split at all")})
        return out
    elo_map = {}
    try:
        from tools import betting_elo
        elo_map = betting_elo.elo_probabilities(games)
    except Exception:                                          # noqa: BLE001
        log.warning("betting_model: ridge gate could not build the Elo tier",
                    exc_info=True)

    grid = []
    for q in qs:
        cut = dates[max(1, min(int(len(dates) * q), len(dates) - 1))]
        fit_g = [g for g in gradable if (g.get("date") or "") < cut]
        ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
        row = {"split_q": q, "split_date": cut,
               "n_fit": len(fit_g), "n_eval": len(ev_g)}
        if len(fit_g) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES:
            row.update({"status": "below the fit/eval floors", "pass": False})
            grid.append(row)
            continue
        old = _ridge_arm(fit_g, ev_g, teams, parks, starters, resolve, ridge=False)
        new = _ridge_arm(fit_g, ev_g, teams, parks, starters, resolve, ridge=True)
        if not old or not new or old["_pks"] != new["_pks"]:
            row.update({"status": "arms did not price the same games", "pass": False})
            grid.append(row)
            continue
        bd = _paired_delta(old["_brier_rows"], new["_brier_rows"])
        ld = _paired_delta(old["_ll_rows"], new["_ll_rows"])
        # The Elo leg, on the games Elo can price. It is the section 6 ladder's
        # results-only floor and it is never fitted here or anywhere else.
        e_idx = [i for i, pk in enumerate(new["_pks"]) if pk in elo_map]
        elo_row = {"n": len(e_idx)}
        if len(e_idx) >= 2:
            e_ps = [elo_map[new["_pks"][i]] for i in e_idx]
            e_ys = [new["_ys"][i] for i in e_idx]
            e_br, _ = _per_game_losses(e_ps, e_ys)
            elo_row["brier"] = round(_brier(e_ps, e_ys), 5)
            elo_row["ridge_vs_elo"] = _paired_delta(
                e_br, [new["_brier_rows"][i] for i in e_idx])
            elo_row["ols_vs_elo"] = _paired_delta(
                e_br, [old["_brier_rows"][i] for i in e_idx])
        checks = [
            {"id": "non_inferiority_vs_ols",
             "value": bd.get("lb95"), "threshold": -0.001,
             "pass": bool(bd.get("lb95") is not None and bd["lb95"] >= -0.001)},
            {"id": "superiority_vs_elo",
             "value": ((elo_row.get("ridge_vs_elo") or {}).get("t")),
             "threshold": Z_95_ONE_SIDED,
             "pass": bool((elo_row.get("ridge_vs_elo") or {}).get("t") is not None
                          and elo_row["ridge_vs_elo"]["t"] >= Z_95_ONE_SIDED)},
            {"id": "log_loss_not_worse",
             "value": ld.get("delta"), "threshold": 0.0,
             "pass": bool(ld.get("delta") is not None and ld["delta"] >= 0.0)},
        ]
        row.update({
            "status": "ran",
            "ols": _ridge_arm_public(old),
            "ridge": _ridge_arm_public(new),
            "brier_delta": bd,
            "log_loss_delta": ld,
            "elo": elo_row,
            "checks": checks,
            "pass": all(c["pass"] for c in checks),
        })
        grid.append(row)
        if log_fn:
            log_fn(f"betting_model: ridge gate q={q} cut={cut} "
                   f"brier delta {bd.get('delta')} lb95 {bd.get('lb95')} "
                   f"pass={row['pass']}")
    # REPORTED, NOT A CRITERION. The grid above splits at date quantiles, so
    # every one of its fit windows is GROWN. The window the site would actually
    # serve on is the anchored one `_vintage_cut_index` builds, and "what would
    # flipping the flag do to the published number" is a different question from
    # "does the ridge clear the gate". Both get answered, and only the grid
    # decides anything.
    served = {"basis": ("the shipped vintage cut (_vintage_cut_index), which is the "
                        "window a flip of SERVE_RIDGE_FIT would actually change"),
              "is_a_criterion": False}
    cut = dates[_vintage_cut_index(gradable, dates)]
    fit_g = [g for g in gradable if (g.get("date") or "") < cut]
    ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
    if len(fit_g) >= VINTAGE_MIN_FIT_GAMES and len(ev_g) >= VINTAGE_MIN_EVAL_GAMES:
        so = _ridge_arm(fit_g, ev_g, teams, parks, starters, resolve, ridge=False)
        sn = _ridge_arm(fit_g, ev_g, teams, parks, starters, resolve, ridge=True)
        if so and sn and so["_pks"] == sn["_pks"]:
            served.update({
                "split_date": cut, "n_fit": len(fit_g), "n_eval": len(ev_g),
                "ols": _ridge_arm_public(so), "ridge": _ridge_arm_public(sn),
                "brier_delta": _paired_delta(so["_brier_rows"], sn["_brier_rows"]),
                "log_loss_delta": _paired_delta(so["_ll_rows"], sn["_ll_rows"]),
            })
    out["served_window"] = served

    ran = [r for r in grid if r.get("status") == "ran"]
    if not ran:
        verdict = "indeterminate"
    elif all(r["pass"] for r in ran) and len(ran) == len(qs):
        verdict = "pass"
    elif any(r["pass"] for r in ran):
        verdict = "indeterminate"
    else:
        verdict = "fail"
    out.update({
        "status": "ran" if ran else "insufficient vintage coverage",
        "grid": grid,
        "stability": {
            "note": ("the coefficient and diff_shrink columns exist so a verdict that "
                     "rides on one window is visible as one; a term that changes sign "
                     "across three splits is not estimated, whatever its gate says"),
            "ols": [{"split_q": r["split_q"],
                     "b1": round(r["ols"]["coefficients"]["b1"], 6),
                     "b2": round(r["ols"]["coefficients"]["b2"], 6),
                     "b3": round(r["ols"]["coefficients"]["b3"], 6),
                     "b4": round(r["ols"]["coefficients"]["b4"], 6),
                     "diff_shrink": r["ols"]["diff_shrink"]} for r in ran],
            "ridge": [{"split_q": r["split_q"],
                       "penalty": r["ridge"]["coefficients"].get("penalty"),
                       "b1": round(r["ridge"]["coefficients"]["b1"], 6),
                       "b2": round(r["ridge"]["coefficients"]["b2"], 6),
                       "b3": round(r["ridge"]["coefficients"]["b3"], 6),
                       "b4": round(r["ridge"]["coefficients"]["b4"], 6),
                       "diff_shrink": r["ridge"]["diff_shrink"],
                       "binding": r["ridge"]["coefficients"].get(
                           "sign_constraints_binding")} for r in ran],
        },
        "verdict": verdict,
        "rule": ("every quantile must pass all three checks or the gate does not ship; "
                 "a mixed grid is INDETERMINATE and the incumbent keeps serving"),
        "elo_bar_note": ("check 2 is a bar on the MODEL CLASS, not on the challenger, "
                         "and each split persists `elo.ols_vs_elo` beside "
                         "`elo.ridge_vs_elo` so that cannot be misread. A split where "
                         "the incumbent also misses the Elo bar is not evidence that "
                         "the ridge broke something"),
        "ship": verdict == "pass",
        "served": SERVE_RIDGE_FIT,
        "mode": "vintage",
    })
    return out


def _total_level_split(fit_g, ev_g, teams, parks, starters, resolve) -> dict | None:
    """One split of TOTAL_LEVEL_GATE_CRITERIA: solve everything on the fit half
    exactly as the vintage lab does, fit both recentre arms on the same fit
    half, score the eval half. Working series carry a leading underscore and
    are popped before anything is published."""
    coeffs = fit_coefficients(fit_g, teams=teams, parks=parks, starters=starters,
                              resolve=resolve)
    if not coeffs:
        return None
    tie = _fit_tie_home(fit_g)
    fit_home_rate = (sum(1 for g in fit_g if g["home_runs"] > g["away_runs"])
                     / max(1, len(fit_g)))
    shrink, _ = _solve_diff_shrink(fit_g, teams, parks, starters, coeffs, tie,
                                   0.0, resolve, None)
    adj = _solve_home_adj(fit_g, teams, parks, starters, coeffs, tie,
                          fit_home_rate, shrink, resolve, None)
    fit_rows = _total_level_rows(fit_g, teams, parks, starters, coeffs, adj, shrink,
                                 resolve)
    fit = fit_total_level([(m, y) for m, y, _ in fit_rows])
    if not fit:
        return None
    ev_rows = _total_level_rows(ev_g, teams, parks, starters, coeffs, adj, shrink,
                                resolve)
    if len(ev_rows) < 2:
        return None
    ev_my = [(m, y) for m, y, _ in ev_rows]
    out = {"n_fit": len(fit_rows), "n_eval": len(ev_rows),
           "coefficients": {k: round(coeffs[k], 6) for k in _COEFF_KEYS},
           "diff_shrink": shrink, "home_field_runs_adj": adj,
           "fit": fit, "_ev_rows": ev_rows}
    inc = _total_level_losses(ev_my, 0.0)
    for arm in ("centre", "mean"):
        d = fit[arm]
        ch = _total_level_losses(ev_my, d)
        tot = _paired_delta(inc, ch)
        per_line = []
        for L in TOTAL_LEVEL_LINES:
            pl = _paired_delta(_total_level_losses(ev_my, 0.0, (L,)),
                               _total_level_losses(ev_my, d, (L,)))
            obs = sum(1 for _, y in ev_my if y > L) / len(ev_my)
            per_line.append({
                "line": L, "log_loss_delta": pl,
                "observed_over": round(obs, 4),
                "model_over_incumbent": round(sum(_poisson_over(m, L)
                                                  for m, _ in ev_my) / len(ev_my), 4),
                "model_over_arm": round(sum(_poisson_over(max(0.5, m + d), L)
                                            for m, _ in ev_my) / len(ev_my), 4)})
        n_ok = sum(1 for r in per_line
                   if r["log_loss_delta"].get("delta") is not None
                   and r["log_loss_delta"]["delta"] >= 0.0)
        checks = [
            {"id": "grid_log_loss_superiority", "value": tot.get("t"),
             "threshold": Z_95_ONE_SIDED,
             "pass": bool(tot.get("t") is not None and tot["t"] >= Z_95_ONE_SIDED)},
            {"id": "per_line_not_worse_3_of_4", "value": n_ok, "threshold": 3,
             "pass": n_ok >= 3},
        ]
        out[arm] = {"delta_runs": d, "grid_log_loss_delta": tot,
                    "per_line": per_line, "checks": checks,
                    "pass": all(c["pass"] for c in checks)}
    return out


def _total_level_posted_diagnostic(split: dict, games_by_pk: dict) -> dict:
    """DIAGNOSTIC, NEVER A CRITERION. On eval games whose slate has a cached open
    capture, the model P(over) at the posted modal line minus the realised Over
    rate, under the incumbent and both arms. The line is read from the market as
    a LOCATION to score at; no market probability reaches any arm."""
    rows = split.get("_ev_rows") or []
    need = {games_by_pk[pk]["date"] for _, _, pk in rows if pk in games_by_pk}
    caps = _market_open_by_market(need)
    arms = {"incumbent": 0.0, "centre": split["centre"]["delta_runs"],
            "mean": split["mean"]["delta_runs"]}
    acc = {k: [] for k in arms}
    ys, mkt = [], []
    for m, y, pk in rows:
        g = games_by_pk.get(pk)
        if g is None:
            continue
        ev = (caps.get(g["date"]) or {}).get((g["home_org"], g["away_org"])) or {}
        spec = ev.get("total")
        if not spec or spec.get("line") is None:
            continue
        line = float(spec["line"])
        if float(y) == line:
            continue                                 # a push resolves nothing
        ys.append(1 if y > line else 0)
        mkt.append(float(spec["p_over"]))
        for k, d in arms.items():
            pmf = _poisson_pmf(max(0.5, m + d), 40)
            acc[k].append(total_side_probabilities(pmf, line)["p_over"])
    n = len(ys)
    if not n:
        return {"n": 0, "note": "no eval game in this split has a cached open capture"}
    hit = sum(ys) / n
    return {
        "n": n, "is_a_criterion": False,
        "realised_over_rate": round(hit, 4),
        "market_fair_over_mean": round(sum(mkt) / n, 4),
        "model_over_mean": {k: round(sum(v) / n, 4) for k, v in acc.items()},
        "model_over_minus_realised": {k: round(sum(v) / n - hit, 4)
                                      for k, v in acc.items()},
        "n_positive_edge_over": {k: sum(1 for p, q in zip(v, mkt) if p > q)
                                 for k, v in acc.items()},
        "note": ("the market is a diagnostic target only; its line is where the "
                 "total is scored and its de-vigged Over is printed beside the "
                 "model, and neither enters any arm"),
    }


def total_level_gate(games=None, *, teams=None, parks=None, starters=None,
                     quantiles=None, log_fn=None) -> dict:
    """The pre-registered gate on SERVE_TOTAL_LEVEL (TOTAL_LEVEL_GATE_CRITERIA).

    Vintage-gradable sample only. Four splits: the anchored served cut and the
    three date quantiles. ALL FOUR must pass for `ship`. The CENTRE arm is the
    candidate; the MEAN arm is graded beside it on identical games so the plan's
    literal candidate has a number rather than an argument. The anchored split
    never grades the 305-game fit half; no quantile cut falls before it."""
    qs = tuple(quantiles if quantiles is not None else DISPERSION_SPLIT_QUANTILES)
    out = {"criteria": TOTAL_LEVEL_GATE_CRITERIA, "quantiles": list(qs),
           "lines": list(TOTAL_LEVEL_LINES),
           "surface": ("gate lab only: no served price reads either arm until "
                       "SERVE_TOTAL_LEVEL flips")}
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    if not games or not teams:
        out.update({"status": "no data", "verdict": "indeterminate", "ship": False,
                    "served": SERVE_TOTAL_LEVEL})
        return out
    reset_vintage_cache()
    resolve, _ = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    out["n_gradable"] = len(gradable)
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out.update({"status": "insufficient vintage coverage", "verdict": "indeterminate",
                    "ship": False, "served": SERVE_TOTAL_LEVEL})
        return out
    by_pk = {g.get("game_pk"): g for g in gradable}
    cuts = [("anchored", dates[_vintage_cut_index(gradable, dates)])]
    cuts += [(q, dates[max(1, min(int(len(dates) * q), len(dates) - 1))]) for q in qs]
    grid = []
    for q, cut in cuts:
        fit_g = [g for g in gradable if (g.get("date") or "") < cut]
        ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
        row = {"split_q": q, "split_date": cut, "n_fit": len(fit_g), "n_eval": len(ev_g)}
        if len(fit_g) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES:
            row.update({"status": "below the fit/eval floors", "pass": False})
            grid.append(row)
            continue
        sp = _total_level_split(fit_g, ev_g, teams, parks, starters, resolve)
        if not sp:
            row.update({"status": "did not price", "pass": False})
            grid.append(row)
            continue
        try:
            diag = _total_level_posted_diagnostic(sp, by_pk)
        except Exception:                                      # noqa: BLE001
            diag = {"n": 0, "note": "the posted-line diagnostic failed"}
        sp.pop("_ev_rows", None)
        row.update({"status": "ran", **sp, "posted_line_diagnostic": diag,
                    "pass": bool(sp["centre"]["pass"])})
        grid.append(row)
        if log_fn:
            log_fn(f"betting_model: total level gate q={q} cut={cut} centre "
                   f"{sp['centre']['delta_runs']} t={sp['centre']['grid_log_loss_delta'].get('t')} "
                   f"pass={row['pass']}")
    ran = [r for r in grid if r.get("status") == "ran"]
    if not ran:
        verdict = "indeterminate"
    elif len(ran) == len(cuts) and all(r["pass"] for r in ran):
        verdict = "pass"
    elif any(r["pass"] for r in ran):
        verdict = "indeterminate"
    else:
        verdict = "fail"
    out.update({"status": "ran" if ran else "insufficient vintage coverage",
                "grid": grid, "verdict": verdict, "ship": verdict == "pass",
                "rule": ("the centre arm must pass both checks at all four splits; a "
                         "mixed grid is INDETERMINATE and the incumbent keeps serving"),
                "served": SERVE_TOTAL_LEVEL, "mode": "vintage"})
    return out


def _total_dispersion_split(fit_g, ev_g, teams, parks, starters, resolve) -> dict | None:
    """One split of TOTAL_DISPERSION_GATE_CRITERIA: the pricer solved on the fit
    half exactly as the vintage lab does, alpha_T fitted on the same fit half, the
    eval half scored against the Poisson total."""
    coeffs = fit_coefficients(fit_g, teams=teams, parks=parks, starters=starters,
                              resolve=resolve)
    if not coeffs:
        return None
    tie = _fit_tie_home(fit_g)
    fit_home_rate = (sum(1 for g in fit_g if g["home_runs"] > g["away_runs"])
                     / max(1, len(fit_g)))
    shrink, _ = _solve_diff_shrink(fit_g, teams, parks, starters, coeffs, tie,
                                   0.0, resolve, None)
    adj = _solve_home_adj(fit_g, teams, parks, starters, coeffs, tie,
                          fit_home_rate, shrink, resolve, None)
    fit_rows = _total_dispersion_rows(fit_g, teams, parks, starters, coeffs, adj,
                                      shrink, resolve)
    fit = fit_total_dispersion([(a, b, y) for a, b, y, _ in fit_rows])
    if not fit:
        return None
    ev_rows = _total_dispersion_rows(ev_g, teams, parks, starters, coeffs, adj,
                                     shrink, resolve)
    if len(ev_rows) < 2:
        return None
    ev = [(a, b, y) for a, b, y, _ in ev_rows]
    alpha = fit["alpha"]
    inc = _total_dispersion_losses(ev, None)
    ch = _total_dispersion_losses(ev, alpha)
    tot = _paired_delta(inc, ch)
    per_line = []
    for L in TOTAL_LEVEL_LINES:
        pl = _paired_delta(_total_dispersion_losses(ev, None, (L,)),
                           _total_dispersion_losses(ev, alpha, (L,)))
        per_line.append({
            "line": L, "log_loss_delta": pl,
            "observed_over": round(sum(1 for *_, y in ev if y > L) / len(ev), 4),
            "model_over_poisson": round(sum(_pmf_over(_total_pmf(a, b, None), L)
                                            for a, b, _ in ev) / len(ev), 4),
            "model_over_nb": round(sum(_pmf_over(_total_pmf(a, b, alpha), L)
                                       for a, b, _ in ev) / len(ev), 4)})
    n_ok = sum(1 for r in per_line if r["log_loss_delta"].get("delta") is not None
               and r["log_loss_delta"]["delta"] >= 0.0)
    checks = [
        {"id": "grid_log_loss_superiority", "value": tot.get("t"),
         "threshold": Z_95_ONE_SIDED,
         "pass": bool(tot.get("t") is not None and tot["t"] >= Z_95_ONE_SIDED)},
        {"id": "per_line_not_worse_3_of_4", "value": n_ok, "threshold": 3,
         "pass": n_ok >= 3},
    ]
    return {"n_fit": len(fit_rows), "n_eval": len(ev_rows), "fit": fit,
            "alpha_T": alpha, "grid_log_loss_delta": tot, "per_line": per_line,
            "checks": checks, "pass": all(c["pass"] for c in checks)}


def total_dispersion_gate(games=None, *, teams=None, parks=None, starters=None,
                          quantiles=None, log_fn=None) -> dict:
    """The pre-registered gate on SERVE_TOTAL_DISPERSION (section 7g). Same four
    splits and the same verdict rule as `total_level_gate`: ALL FOUR must pass for
    `ship`, a mixed grid is INDETERMINATE, and a PASS still leaves the flip to the
    owner."""
    qs = tuple(quantiles if quantiles is not None else DISPERSION_SPLIT_QUANTILES)
    out = {"criteria": TOTAL_DISPERSION_GATE_CRITERIA, "quantiles": list(qs),
           "lines": list(TOTAL_LEVEL_LINES),
           "surface": ("gate lab only: no served price reads alpha_T until "
                       "SERVE_TOTAL_DISPERSION flips")}
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    if not games or not teams:
        out.update({"status": "no data", "verdict": "indeterminate", "ship": False,
                    "served": SERVE_TOTAL_DISPERSION})
        return out
    reset_vintage_cache()
    resolve, _ = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    out["n_gradable"] = len(gradable)
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out.update({"status": "insufficient vintage coverage", "verdict": "indeterminate",
                    "ship": False, "served": SERVE_TOTAL_DISPERSION})
        return out
    cuts = [("anchored", dates[_vintage_cut_index(gradable, dates)])]
    cuts += [(q, dates[max(1, min(int(len(dates) * q), len(dates) - 1))]) for q in qs]
    grid = []
    for q, cut in cuts:
        fit_g = [g for g in gradable if (g.get("date") or "") < cut]
        ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
        row = {"split_q": q, "split_date": cut, "n_fit": len(fit_g), "n_eval": len(ev_g)}
        if len(fit_g) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES:
            row.update({"status": "below the fit/eval floors", "pass": False})
            grid.append(row)
            continue
        sp = _total_dispersion_split(fit_g, ev_g, teams, parks, starters, resolve)
        if not sp:
            row.update({"status": "did not price", "pass": False})
            grid.append(row)
            continue
        row.update({"status": "ran", **sp})
        grid.append(row)
        if log_fn:
            log_fn(f"betting_model: total dispersion gate q={q} cut={cut} alpha_T "
                   f"{sp['alpha_T']} t={sp['grid_log_loss_delta'].get('t')} "
                   f"pass={sp['pass']}")
    ran = [r for r in grid if r.get("status") == "ran"]
    if not ran:
        verdict = "indeterminate"
    elif len(ran) == len(cuts) and all(r["pass"] for r in ran):
        verdict = "pass"
    elif any(r["pass"] for r in ran):
        verdict = "indeterminate"
    else:
        verdict = "fail"
    out.update({"status": "ran" if ran else "insufficient vintage coverage",
                "grid": grid, "verdict": verdict, "ship": verdict == "pass",
                "rule": ("both checks at all four splits; a mixed grid is "
                         "INDETERMINATE and the Poisson total keeps serving; a PASS "
                         "leaves the flip to the owner"),
                "served": SERVE_TOTAL_DISPERSION, "mode": "vintage"})
    return out


def _total_calibration_split(fit_g, ev_g, teams, parks, starters, resolve) -> dict | None:
    """One split of TOTAL_CALIBRATION_GATE_CRITERIA."""
    coeffs = fit_coefficients(fit_g, teams=teams, parks=parks, starters=starters,
                              resolve=resolve)
    if not coeffs:
        return None
    tie = _fit_tie_home(fit_g)
    fit_home_rate = (sum(1 for g in fit_g if g["home_runs"] > g["away_runs"])
                     / max(1, len(fit_g)))
    shrink, _ = _solve_diff_shrink(fit_g, teams, parks, starters, coeffs, tie,
                                   0.0, resolve, None)
    adj = _solve_home_adj(fit_g, teams, parks, starters, coeffs, tie,
                          fit_home_rate, shrink, resolve, None)
    fit_rows = _total_dispersion_rows(fit_g, teams, parks, starters, coeffs, adj,
                                      shrink, resolve)
    fit = fit_total_calibration([(a, b, y) for a, b, y, _ in fit_rows])
    if not fit:
        return {"n_fit": len(fit_rows), "refused": "fit_platt refused or a <= 0",
                "pass": False}
    ev_rows = _total_dispersion_rows(ev_g, teams, parks, starters, coeffs, adj,
                                     shrink, resolve)
    if len(ev_rows) < 2:
        return None
    ev = [(a, b, y) for a, b, y, _ in ev_rows]
    ab = (fit["a"], fit["b"])
    tot = _paired_delta(_total_cal_losses(ev, None), _total_cal_losses(ev, ab))
    per_line = []
    for L in TOTAL_LEVEL_LINES:
        pl = _paired_delta(_total_cal_losses(ev, None, (L,)),
                           _total_cal_losses(ev, ab, (L,)))
        pp = [_pmf_over(_total_pmf(a, b, None), L) for a, b, _ in ev]
        per_line.append({
            "line": L, "log_loss_delta": pl,
            "observed_over": round(sum(1 for *_, y in ev if y > L) / len(ev), 4),
            "model_over_poisson": round(sum(pp) / len(ev), 4),
            "model_over_mapped": round(sum(apply_platt(p, ab[0], ab[1]) for p in pp)
                                       / len(ev), 4)})
    n_ok = sum(1 for r in per_line if r["log_loss_delta"].get("delta") is not None
               and r["log_loss_delta"]["delta"] >= 0.0)
    checks = [
        {"id": "grid_log_loss_superiority", "value": tot.get("t"),
         "threshold": Z_95_ONE_SIDED,
         "pass": bool(tot.get("t") is not None and tot["t"] >= Z_95_ONE_SIDED)},
        {"id": "per_line_not_worse_3_of_4", "value": n_ok, "threshold": 3,
         "pass": n_ok >= 3},
    ]
    return {"n_fit": len(fit_rows), "n_eval": len(ev_rows), "fit": fit,
            "a": ab[0], "b": ab[1], "grid_log_loss_delta": tot, "per_line": per_line,
            "checks": checks, "pass": all(c["pass"] for c in checks)}


def total_calibration_gate(games=None, *, teams=None, parks=None, starters=None,
                           quantiles=None, log_fn=None) -> dict:
    """The pre-registered gate on SERVE_TOTAL_CALIBRATION (section 7h); the 7f/7g
    verdict rule."""
    qs = tuple(quantiles if quantiles is not None else DISPERSION_SPLIT_QUANTILES)
    out = {"criteria": TOTAL_CALIBRATION_GATE_CRITERIA, "quantiles": list(qs),
           "lines": list(TOTAL_LEVEL_LINES),
           "surface": "gate lab only: no served price reads (a, b) until the flag flips"}
    games = games if games is not None else completed_games()
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    if not games or not teams:
        out.update({"status": "no data", "verdict": "indeterminate", "ship": False,
                    "served": SERVE_TOTAL_CALIBRATION})
        return out
    reset_vintage_cache()
    resolve, _ = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    out["n_gradable"] = len(gradable)
    if len(gradable) < (VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES) or len(dates) < 4:
        out.update({"status": "insufficient vintage coverage", "verdict": "indeterminate",
                    "ship": False, "served": SERVE_TOTAL_CALIBRATION})
        return out
    cuts = [("anchored", dates[_vintage_cut_index(gradable, dates)])]
    cuts += [(q, dates[max(1, min(int(len(dates) * q), len(dates) - 1))]) for q in qs]
    grid = []
    for q, cut in cuts:
        fit_g = [g for g in gradable if (g.get("date") or "") < cut]
        ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
        row = {"split_q": q, "split_date": cut, "n_fit": len(fit_g), "n_eval": len(ev_g)}
        if len(fit_g) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES:
            row.update({"status": "below the fit/eval floors", "pass": False})
            grid.append(row)
            continue
        sp = _total_calibration_split(fit_g, ev_g, teams, parks, starters, resolve)
        if not sp:
            row.update({"status": "did not price", "pass": False})
            grid.append(row)
            continue
        row.update({"status": "ran" if "refused" not in sp else "refused", **sp})
        grid.append(row)
        if log_fn and "refused" not in sp:
            log_fn(f"betting_model: total calibration gate q={q} cut={cut} a={sp['a']} "
                   f"b={sp['b']} t={sp['grid_log_loss_delta'].get('t')} pass={sp['pass']}")
    ran = [r for r in grid if r.get("status") == "ran"]
    if not ran:
        verdict = "indeterminate"
    elif len(ran) == len(cuts) and all(r["pass"] for r in ran):
        verdict = "pass"
    elif any(r["pass"] for r in ran):
        verdict = "indeterminate"
    else:
        verdict = "fail"
    out.update({"status": "ran" if ran else "insufficient vintage coverage",
                "grid": grid, "verdict": verdict, "ship": verdict == "pass",
                "rule": ("both checks at all four splits; a mixed grid is INDETERMINATE; "
                         "a PASS leaves the flip to the owner"),
                "served": SERVE_TOTAL_CALIBRATION, "mode": "vintage"})
    return out


def _calibration(ps: list[float], ys: list[int], bins: int = 10) -> list[dict]:
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        sel = [(p, y) for p, y in zip(ps, ys) if (lo <= p < hi or (i == bins - 1 and p == 1.0))]
        if not sel:
            continue
        out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(sel),
                    "pred": round(sum(p for p, _ in sel) / len(sel), 4),
                    "actual": round(sum(y for _, y in sel) / len(sel), 4)})
    return out


def sweep_min_edge(rows: list[dict], *, grid=None, z: float = Z_95_ONE_SIDED,
                   min_bets: int = 100) -> dict:
    """The smallest edge threshold whose graded ROI lower bound clears zero.

    `rows` are SETTLED bets: {"edge": model minus de-vigged fair, "decimal":
    the price taken, "won": bool}. For each candidate threshold the qualifying
    bets are re-graded at flat 1 unit, and the threshold is accepted only when

        mean(profit) - z * stderr(profit) > 0

    which is a one-sided 95% lower bound on ROI per unit risked. The SMALLEST
    qualifying threshold wins, because a higher one is a smaller sample
    pretending to be a stronger result.

    Returns {"min_edge": float|None, "reason": str, "candidates": [...]}.
    None is the normal answer and stays the answer until a graded price
    history exists: this module has never held one, since the odds ingest only
    started caching snapshots and nothing has settled against them yet."""
    grid = list(grid) if grid is not None else [round(0.005 * i, 3) for i in range(1, 21)]
    if not rows:
        return {"min_edge": None, "n_rows": 0, "candidates": [],
                "reason": ("no settled bets with both a model edge and a taken price; "
                           "the threshold cannot be swept on data that does not exist")}
    cands = []
    for thr in sorted(grid):
        sel = [r for r in rows
               if r.get("edge") is not None and float(r["edge"]) >= thr
               and _pos(r.get("decimal"))]
        n = len(sel)
        if n < min_bets:
            cands.append({"edge": thr, "n": n, "qualified": False,
                          "reason": f"n < {min_bets}"})
            continue
        profits = [(float(r["decimal"]) - 1.0) if r.get("won") else -1.0 for r in sel]
        mu = sum(profits) / n
        var = sum((p - mu) ** 2 for p in profits) / n
        se = math.sqrt(var / n) if var else 0.0
        lower = mu - z * se
        cands.append({"edge": thr, "n": n, "roi": round(mu, 5),
                      "roi_lower_95": round(lower, 5), "qualified": bool(lower > 0)})
    ok = [c for c in cands if c.get("qualified")]
    if not ok:
        return {"min_edge": None, "n_rows": len(rows), "candidates": cands,
                "reason": ("no edge threshold produced an ROI whose one-sided 95% lower "
                           "bound clears zero on the graded sample")}
    best = ok[0]
    return {"min_edge": best["edge"], "n_rows": len(rows), "candidates": cands,
            "reason": (f"smallest threshold whose graded ROI lower bound clears zero "
                       f"(n={best['n']}, ROI {best['roi']:+.3f}, "
                       f"lower bound {best['roi_lower_95']:+.3f})")}


def _odds_history_dates() -> list[str]:
    """Dates with at least one cached odds snapshot. Filenames only, so this
    costs nothing and never parses a snapshot."""
    d = ROOT / ".cache" / "odds"
    if not d.exists():
        return []
    return sorted({p.name[:10] for p in d.glob("*.json") if len(p.name) >= 10})


def _shadow_graded_bets() -> list[dict]:
    """Settled paper bets from the shadow ledger, POOLED across every tag.

    THE CIRCLE THIS BREAKS. sweep_min_edge needs settled bets carrying a taken
    price, and min_edge_gate was only ever called with graded_bets=None, so the
    third gate could never open: publishing a pick needed min_edge, and min_edge
    needed settled picks. betting_shadow records what the model WOULD have bet at
    the price actually on the board and settles it against the result, which
    supplies that history without the site claiming anything.

    THIS POOLED LIST IS A COUNT AND NOTHING ELSE. `min_edge_gate` reports its
    length as gate 3's `have` and never sweeps it: see
    `_shadow_graded_bets_by_tag`.

    Deliberately best effort and silent on absence: a missing ledger is the
    normal state before the first slate is logged, and the gate already reports
    `have: 0` in that case, which is the honest answer."""
    try:
        import betting_shadow
        return betting_shadow.graded_bets()
    except Exception:                                         # noqa: BLE001
        log.debug("betting_model: shadow ledger unavailable", exc_info=True)
        return []


def _shadow_graded_bets_by_tag() -> dict:
    """{tag: settled paper bets} - the shape gate 3 is allowed to sweep.

    The per-tag API existed in betting_shadow from the day the fourth tag
    shipped and had no caller, so the gate went on sweeping the pooled set the
    docs forbid (docs/diamond-betting.md section 7a: "a pooled ROI measures a
    mixture nobody bet"). This is that caller."""
    try:
        import betting_shadow
        return betting_shadow.graded_bets_by_tag()
    except Exception:                                         # noqa: BLE001
        log.debug("betting_model: shadow ledger unavailable", exc_info=True)
        return {}


#: The tag a caller's EXPLICIT `graded_bets=` list is swept under.
#:
#: A caller that hands in rows has already decided what population they are -
#: that is what handing them in means - so they are one tag, not a mixture, and
#: they sweep as one. Naming it keeps the per-tag table honest about where the
#: rows came from instead of laundering them through a real tag's name.
EXPLICIT_TAG = "explicit"

#: Tags that may accumulate evidence but may NOT set a threshold.
#:
#: `untagged` is the pre-2026-08-07 era: one slot a slate, chosen on EV alone.
#: The rows are real and their ROI is real, but the selection rule that produced
#: them is not a rule this site still runs (it publishes two slots now), so a
#: threshold fitted to them would be applied to a rule that no longer exists.
#: That is the pooling defect with a smaller n, not an exception to it.
TAGS_THAT_MAY_NOT_SET_A_THRESHOLD = frozenset({"untagged"})


def sweep_min_edge_by_tag(rows_by_tag: dict, **kw) -> dict:
    """`sweep_min_edge` run ONCE PER TAG, never over their union.

    Returns {tag: sweep result}. A tag with four settled rows stays shut while
    another with a hundred and twenty opens, which is the correct behaviour and
    the reason the pooled version looked further along than it was."""
    return {t: sweep_min_edge(list(rws or []), **kw)
            for t, rws in sorted((rows_by_tag or {}).items())}


def min_edge_gate(vintage_block: dict | None, *, graded_bets: list[dict] | None = None) -> dict:
    """Whether `min_edge` may be set at all, and what it is if so.

    THREE GATES, all of which must be open. Every one of them is currently
    closed, and the honest thing is to say which:

      1. VINTAGE SAMPLE. The vintage-mode backtest must have graded at least
         VINTAGE_MIN_GRADED_GAMES games. See that constant for the derivation:
         it is the n at which the observed (contaminated, therefore optimistic)
         margin over the home-field baseline would be detectable at one-sided
         95%.
      2. OUT-OF-SAMPLE SKILL. On that sample, the paired Brier difference
         against the home-field baseline must clear zero at one-sided 95%.
         Sample size alone is not evidence; this is the actual claim.
      3. A GRADED PRICE HISTORY, SWEPT PER SELECTION RULE. A threshold is a
         statement about EV against real prices, so it can only be swept on
         settled bets with a taken price. The shadow ledger tags every row with
         the rule that chose it, and those tags select on four different
         quantities, so the sweep runs ONCE PER TAG and a tag opens only if it
         individually clears. Pooling them would fit a threshold to a mixture
         nobody bet (docs/diamond-betting.md section 7a).

    Gate 3 is why `min_edge` would still be None on the day gates 1 and 2 open:
    a calibrated probability is not an edge until there is a market to have an
    edge against.

    THE SCALAR `min_edge` IS THE STRICTEST CLEARED TAG'S THRESHOLD. One number
    has to serve the whole board, and the tags disagree about what an edge is
    worth, so the only safe reduction is the largest: a floor above a tag's own
    measured threshold is stricter than that tag's evidence requires and can
    never be looser. `min_edge_by_tag` ships beside it so a per-slot consumer
    can condition on its own rule instead of on the reduction."""
    vb = vintage_block or {}
    n_graded = int(vb.get("n_graded") or 0)
    skill = vb.get("skill_vs_home_base") or {}
    odds_dates = _odds_history_dates()
    # None means "look for them"; an explicit [] still means "none".
    explicit = graded_bets is not None
    rows = list(graded_bets if explicit else _shadow_graded_bets())
    by_tag = {EXPLICIT_TAG: rows} if explicit else _shadow_graded_bets_by_tag()
    # ONE SWEEP PER TAG. `rows` above is only ever counted, never swept: it is
    # the union of four selection rules and a threshold fitted to it is wrong
    # for every one of them separately.
    sweeps = sweep_min_edge_by_tag(by_tag)
    cleared = {t: s["min_edge"] for t, s in sweeps.items()
               if s.get("min_edge") is not None
               and t not in TAGS_THAT_MAY_NOT_SET_A_THRESHOLD}
    price_open = bool(cleared)
    sweep_min = max(cleared.values()) if cleared else None
    tag_table = {
        t: {"n": s.get("n_rows"), "min_edge": s.get("min_edge"),
            "open": bool(s.get("min_edge") is not None
                         and t not in TAGS_THAT_MAY_NOT_SET_A_THRESHOLD),
            "may_set_a_threshold": t not in TAGS_THAT_MAY_NOT_SET_A_THRESHOLD,
            "reason": s.get("reason")}
        for t, s in sweeps.items()
    }
    if cleared:
        sweep_reason = (f"{len(cleared)} of {len(sweeps)} tag(s) cleared on their own "
                        f"evidence ({', '.join(f'{t} at {v:.3f}' for t, v in sorted(cleared.items()))}); "
                        f"the published floor is the strictest of them")
    elif sweeps:
        sweep_reason = (f"no tag cleared: {len(sweeps)} tag(s) present and none of them "
                        "produced an ROI lower bound above zero on 100+ of its own "
                        "settled rows")
    else:
        sweep_reason = ("no settled bets with both a model edge and a taken price; "
                        "the threshold cannot be swept on data that does not exist")

    gates = [
        {"id": "vintage_sample",
         "need": f"{VINTAGE_MIN_GRADED_GAMES} vintage-graded games",
         "have": n_graded,
         "open": n_graded >= VINTAGE_MIN_GRADED_GAMES,
         "why": ("the contaminated forward margin over the home-field baseline is "
                 "+0.005794 Brier with a paired sd of 0.08647, so a margin that size "
                 "needs 603 games to clear one-sided 95%; 600 is that number, and a "
                 "clean margin will be smaller, so this is a floor and not a pass")},
        {"id": "out_of_sample_skill",
         "need": "paired Brier vs the home-field baseline, t >= 1.645",
         "have": skill.get("t"),
         "open": bool(skill.get("beats_baseline_95")),
         "why": ("sample size is not evidence; the model has to actually beat "
                 "'always take the home team' on games it could not see")},
        {"id": "graded_price_history",
         "need": ("settled bets with a taken price, enough that some edge threshold "
                  "clears an ROI lower bound of zero on at least 100 of them, "
                  "WITHIN ONE TAG"),
         # `have` stays the POOLED count and is a count only. It is what a
         # reader wants when asking how much evidence exists at all, and it is
         # explicitly not what the sweep ran on.
         "have": len(rows),
         "have_by_tag": {t: b["n"] for t, b in tag_table.items()},
         "open": price_open,
         "by_tag": tag_table,
         "why": ("an edge threshold is a claim about EV against real prices; "
                 f"{len(odds_dates)} dates of odds snapshots are cached. The sweep "
                 "runs per tag and a tag opens only if it individually clears - a "
                 "pooled ROI measures a mixture nobody bet"),
         "pooled_is_not_sweepable": ("`have` is the union of every tag and is never "
                                     "swept; see by_tag for the four clocks that are")},
    ]
    all_open = all(g["open"] for g in gates)
    return {
        "min_edge": sweep_min if all_open else None,
        "min_edge_by_tag": ({t: b["min_edge"] for t, b in tag_table.items()}
                            if all_open else {}),
        "min_edge_reduction": ("max over the tags that cleared; a floor above a tag's "
                               "own measured threshold is stricter than that tag's "
                               "evidence requires and can never be looser"),
        "all_gates_open": all_open,
        "gates": gates,
        "odds_snapshot_dates": len(odds_dates),
        # POOLED n, PER-TAG verdict. The count is the union; the reason is never
        # a statement about the union's ROI, because nothing swept it.
        "sweep": {"n_rows": len(rows), "reason": sweep_reason,
                  "n_tags": len(sweeps), "n_tags_cleared": len(cleared)},
        "sweep_by_tag": sweeps,
        "policy": ("min_edge stays null until all three gates are open. A threshold "
                   "invented to make a pick appear is the single most dishonest number "
                   "this module could publish."),
    }


def _fit_tie_home(fit_games: list[dict]) -> float:
    """The extra-innings home win rate measured on a FIT window only, shrunk
    toward a coin flip on the same 100-game prior build_context uses. Falls
    back to the literature constant when the window has no extra-inning games,
    never to a season-wide number the eval window helped produce."""
    extras = [g for g in fit_games if (g.get("innings") or 9) > 9]
    if not extras:
        return LITERATURE_TIE_HOME
    wins = sum(1 for g in extras if g["home_runs"] > g["away_runs"])
    return (wins + 0.5 * TIE_SHRINK_K) / (len(extras) + TIE_SHRINK_K)


def _fit_runline_tie_split(fit_games: list[dict]) -> dict | None:
    """How often a side that won in extra innings won by two or more, on the
    games passed in and nothing else (L14-01; `_fit_tie_home`'s window rule).

    The two conditionals are P(home by 2+ | home won in extras) and
    P(away by 2+ | away won in extras). `split_tie_atom` multiplies them by the
    moneyline's own tie_home and 1 - tie_home, which keeps the runline coherent
    with the moneyline whatever window the tie rate was shrunk on.

    NO PRIOR IS APPLIED, on purpose. The two rates differ by mechanism, not by
    noise: the home team stops batting the moment it leads in the bottom of an
    inning, and a game-ending hit counts only the runs needed to win unless it
    leaves the park, so the home side wins an extra-inning game by two or more
    only on a walk-off home run with a runner aboard. The away team can keep
    scoring in the top half. A prior pooled
    across the two sides would erase exactly the asymmetry being measured, and
    choosing a structural prior is the B-RUNLINE lane's job (fit on pre-2026
    finals). The counts ride the block so the sample is never hidden.

    None when either side has no extra-inning win in the window: a conditional
    with a zero denominator is not a measurement, and the whole-atom
    construction stays in force."""
    extras = [g for g in fit_games if (g.get("innings") or 9) > 9]
    home_w = [g for g in extras if g["home_runs"] > g["away_runs"]]
    away_w = [g for g in extras if g["away_runs"] > g["home_runs"]]
    if not home_w or not away_w:
        return None
    h2 = sum(1 for g in home_w if g["home_runs"] - g["away_runs"] >= 2)
    a2 = sum(1 for g in away_w if g["away_runs"] - g["home_runs"] >= 2)
    return {
        "n_games": len(fit_games),
        "n_extra_inning_games": len(extras),
        "n_home_wins": len(home_w),
        "n_home_wins_by_2plus": h2,
        "n_away_wins": len(away_w),
        "n_away_wins_by_2plus": a2,
        "home_by_2plus_given_home_win": round(h2 / len(home_w), 4),
        "away_by_2plus_given_away_win": round(a2 / len(away_w), 4),
    }


def _lab_runline_split(fit_games: list[dict]) -> tuple[float, float] | None:
    """The runline split a LAB prices its eval window on: the split measured on
    its FIT window alone, while SERVE_RUNLINE_TIE_SPLIT is on, so a lab grades
    the construction the board serves without the eval window helping to set
    it (the `_fit_tie_home` rule). None, the whole-atom construction, while the
    flag is off, or when the fit window holds no extra-inning win on one side.

    Only the labs that READ a runline probability call this (the section 11a
    dispersion arms and the backtest's per-market grade). The moneyline, the
    total and every solver are untouched by the split, so the labs that read
    only those need nothing."""
    if not SERVE_RUNLINE_TIE_SPLIT:
        return None
    return _runline_split_pair(_fit_runline_tie_split(fit_games))


def backtest(*, season: str | None = None, split_date: str | None = None,
             write: bool = True, log_fn=None) -> dict:
    """Grade the model on completed games, in BOTH modes, offline.

    MODE 1, CONTAMINATED (`in_sample`, `forward`). The team inputs
    (offense_plus / rotation_plus / bullpen_plus / SEM+) are SEASON-TO-DATE
    aggregates as of the last leaderboard build, so every game graded here
    contributed to the features used to predict it. `forward` refits the
    coefficients on games before `split_date` and grades only games after it,
    which removes coefficient leakage but NOT feature leakage. Both are
    reported, both carry `mode: "contaminated"`, and neither can validate
    anything.

    MODE 2, VINTAGE (`vintage`). Each game is priced on the newest
    leaderboard vintage whose knowledge cutoff is strictly before it
    (leaderboard_vintages.as_of). Games with no such vintage are SKIPPED, not
    graded on the fallback, and the count of skipped games is reported. Until
    the nightly snapshot has been running, that is every game and the honest n
    is zero. When the sample is large enough the coefficients and both
    one-parameter corrections are refit inside the vintage window too, on
    vintage features.

    THE PARK INDEX IS PART OF "FEATURES" AND USED NOT TO BE. Until 2026-08-05
    this function built `parks = park_index()` once and handed the LIVE index
    (data/fa_meta.json = `fa_fit.park_factors(CLASS_YEAR - 1)`, the in-progress
    season) to the vintage fit AND the vintage pricing, so eval-window games
    contributed to the park factor used to grade them while the mode label said
    "no leakage". Parks now travel in the vintage record; a record written before
    that column existed prices its games on a NEUTRAL park and the count lands in
    `vintage.park_basis`. The contaminated modes below are UNCHANGED: they are
    labelled contaminated and their numbers stay comparable to the old artifact.

    `validated` is False, `gates_picks` is False and `min_edge` is None until
    the vintage mode carries the sample AND the skill AND a graded price
    history; `min_edge_gate` reports which of the three is missing.

    Baselines are what make the number readable: 0.500 flat, and the measured
    home-field rate. A model that cannot beat "always take the home team" has
    not earned a page."""
    games = completed_games(season)
    teams, parks, starters = team_inputs(), park_index(), starter_inputs()
    lv = _vintage_module()
    cov = {}
    if lv:
        try:
            # GAME weighted, not calendar weighted. Without `game_dates` the age
            # distribution weights an off day the same as a 15-game Saturday,
            # and the number sitting beside `n_graded` is then not the one a
            # reader of `n_graded` is asking about. Measured on this archive the
            # two differ: calendar gives median 2 / p90 10 / max 13 over 36
            # covered days, game weighting gives median 3 / p90 11 / max 13 over
            # 414 graded game dates. The published vintage is STALER than the
            # calendar view says, because the archive's holes fall on days that
            # carry games.
            cov = lv.coverage(game_dates=[g.get("date") for g in games if g.get("date")])
        except Exception:                                        # pragma: no cover
            cov = {}
    result = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_version": MODEL_VERSION,
        "season": season,
        "validated": False,
        "contaminated": True,
        "contamination": ("team inputs are season-to-date leaderboards, so every graded "
                          "game is inside its own features; this measures calibration, "
                          "not out-of-sample skill"),
        "gates_picks": False,
        "min_edge": None,
        "n_games": len(games),
        "modes": ["contaminated", "vintage"],
        "headline_mode": "contaminated",
        "vintage_coverage": cov,
    }
    if not games or not teams:
        result["status"] = "no data"
        result["note"] = ("no completed-game cache and/or no leaderboards; run "
                          "betting_model.build_game_cache() on a box that has "
                          ".cache/game_feeds")
        result["vintage"] = _empty_vintage_block(cov, len(games))
        result["benchmarks"] = {"status": "no data",
                                "claim_rule": BENCHMARK_CLAIM_RULE}
        result["min_edge_gate"] = min_edge_gate(result["vintage"])
        if write:
            EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result

    def _grade(fit_games, eval_games, label, mode, resolve=None):
        coeffs = fit_coefficients(fit_games, teams=teams, parks=parks, starters=starters,
                                  resolve=resolve) or dict(LITERATURE_COEFFS)
        # The extra-innings home rate is measured on the FIT window too. It used
        # to come from league_context(), which is fitted over the WHOLE season:
        # a small leak (one shrunk scalar off ~140 games) but a real one, and a
        # mode that calls itself honest cannot carry it.
        tie = _fit_tie_home(fit_games)
        # The home-field reconciliation is refit on the FIT window too, so the
        # forward split does not smuggle the evaluation window's home rate in
        # through the back door.
        fit_home_rate = (sum(1 for g in fit_games if g["home_runs"] > g["away_runs"])
                         / max(1, len(fit_games)))
        # Dispersion is refit on the FIT window for the same reason the tie rate
        # and the home adjustment are: a shape parameter read off the whole
        # season is a leak into every eval game, small but real. Then shrink and
        # adj are solved UNDER it, so this mode never grades a tuned Poisson
        # against an untuned NB.
        alpha = None
        if SERVE_RUN_DISPERSION:
            alpha, _, _ = fit_run_alpha(_lambda_rows(fit_games, teams, parks, starters,
                                                     coeffs, 0.0, 1.0, resolve))
        shrink, _ = _solve_diff_shrink(fit_games, teams, parks, starters, coeffs, tie, 0.0,
                                       resolve, alpha)
        adj = _solve_home_adj(fit_games, teams, parks, starters, coeffs, tie,
                              fit_home_rate, shrink, resolve, alpha)
        # The runline reads the tie atom the way the board serves it, on the FIT
        # window's own split, never the season-wide one (`_lab_runline_split`).
        rl_split = _lab_runline_split(fit_games)
        ps, ys, tot_err, n_tot = [], [], 0.0, 0
        per_game_p: dict = {}
        # The per-market view of the same pass, for section 7e. Lambdas travel
        # UNROUNDED off `components`, because the total is re-priced at whatever
        # line the book posted and a 0.0005-run rounding in a lambda is a real
        # (if tiny) change to a tail probability.
        per_game_mkt: dict = {}
        for g in eval_games:
            gt, gs, gpk = teams, starters, parks
            if resolve is not None:
                got = resolve(g)
                if not got:
                    continue
                # `gpk`, not the enclosing `parks`. The enclosing one is the LIVE
                # park index (fa_meta.json = the in-progress season), and pricing
                # a vintage-mode eval game on it is the leak this lane closed.
                gt, gs, gpk = got
            gp = game_probabilities(g["home_org"], g["away_org"],
                                    home_sp=gs.get(g.get("home_sp")),
                                    away_sp=gs.get(g.get("away_sp")),
                                    teams=gt, parks=gpk, coeffs=coeffs, tie_home=tie,
                                    home_adj=adj, diff_shrink=shrink, run_alpha=alpha,
                                    runline_tie_split=rl_split)
            if not gp:
                continue
            ps.append(gp["p_home"])
            ys.append(1 if g["home_runs"] > g["away_runs"] else 0)
            if g.get("game_pk") is not None:
                per_game_p[g["game_pk"]] = gp["p_home"]
                per_game_mkt[g["game_pk"]] = {
                    "p_home": gp["p_home"],
                    "p_home_minus_1_5": gp["p_home_minus_1_5"],
                    "p_home_plus_1_5": gp["p_home_plus_1_5"],
                    "lam_home": gp["components"]["lam_home"],
                    "lam_away": gp["components"]["lam_away"],
                }
            tot_err += abs(gp["fair_total"] - (g["home_runs"] + g["away_runs"]))
            n_tot += 1
        if not ps:
            return None
        base_home = sum(ys) / len(ys)
        return {
            # Working state for the benchmark ladder, popped by backtest()
            # before the artifact is written: the ladder must score every tier
            # on the model's own graded window, and re-pricing the window to
            # get these back would be a second clock.
            "_per_game_p": per_game_p,
            "_per_game_markets": per_game_mkt,
            "label": label,
            "mode": mode,
            "honest": mode == "vintage",
            "n": len(ps),
            "coefficients": coeffs,
            "home_field_runs_adj": adj,
            "diff_shrink": shrink,
            "run_dispersion_alpha": alpha,
            "extra_inning_home_rate": round(tie, 4),
            "brier": round(_brier(ps, ys), 5),
            "brier_flat_500": round(_brier([0.5] * len(ps), ys), 5),
            "brier_home_base": round(_brier([base_home] * len(ps), ys), 5),
            "log_loss": round(_logloss(ps, ys), 5),
            "log_loss_flat_500": round(_logloss([0.5] * len(ps), ys), 5),
            "accuracy": round(sum(1 for p, y in zip(ps, ys)
                                  if (p >= 0.5) == bool(y)) / len(ps), 4),
            "home_win_rate": round(base_home, 4),
            "mean_p_home": round(sum(ps) / len(ps), 4),
            "total_mae": round(tot_err / n_tot, 3) if n_tot else None,
            "skill_vs_home_base": _paired_brier_skill(ps, ys, base_home),
            "calibration": _calibration(ps, ys),
        }

    # --- mode 1: contaminated -------------------------------------------
    result["in_sample"] = _grade(games, games,
                                 "in-sample (coefficients and features both leak)",
                                 "contaminated")
    dates = sorted({g["date"] for g in games if g.get("date")})
    sd = split_date or (dates[int(len(dates) * 0.7)] if len(dates) > 20 else None)
    if sd:
        fit_g = [g for g in games if (g.get("date") or "") < sd]
        ev_g = [g for g in games if (g.get("date") or "") >= sd]
        if len(fit_g) > 200 and len(ev_g) > 50:
            result["split_date"] = sd
            result["forward"] = _grade(fit_g, ev_g,
                                       f"forward from {sd} (coefficient leakage removed, "
                                       "feature leakage remains)",
                                       "contaminated")

    # --- the dispersion gate ---------------------------------------------
    # Lives inside this artifact rather than in an eval file of its own,
    # because it is a property of the SAME split this function already grades
    # and a second file would be a second clock to keep in sync.
    result["run_dispersion"] = run_dispersion_gate(games, teams=teams, parks=parks,
                                                   starters=starters, split_date=sd)
    # The verdict does NOT come from the line above. It comes from the sweep,
    # because criterion 2's estimand and the split point were both unpinned and
    # both move the answer. The single-split run stays as the pre-registered
    # headline; `sensitivity` is what SERVE_RUN_DISPERSION is set from.
    result["run_dispersion"]["sensitivity"] = dispersion_gate_sensitivity(
        games, teams=teams, parks=parks, starters=starters)
    # `passed` above is ONE split and is not the verdict. `verdict` is, and it
    # is lifted to the top of the block so the two can never be confused by a
    # reader who stops at the first boolean. They genuinely disagree right now:
    # the pre-registered 0.7 split passes all four criteria and the sweep is
    # INDETERMINATE because 0.8 does not.
    sens = result["run_dispersion"]["sensitivity"]
    result["run_dispersion"]["verdict"] = sens.get("verdict")
    result["run_dispersion"]["verdict_note"] = (
        "`passed` is the pre-registered single split under the amended criterion 2. "
        "`verdict` is the ship decision and comes from `sensitivity`, which requires "
        "that criterion to hold at every split quantile. Where they disagree, "
        "`verdict` governs and `served` follows it")
    result["run_dispersion"]["served"] = SERVE_RUN_DISPERSION
    result["run_dispersion"]["served_alpha"] = run_dispersion_alpha()

    # --- mode 2: vintage --------------------------------------------------
    result["vintage"] = _grade_vintage(games, cov, _grade, log_fn=log_fn)

    # --- the B5 calibration gate (section 11b) ----------------------------
    # Lives inside this artifact for the same reason the dispersion gate does:
    # it is a property of the same vintage sample this function already
    # grades, and a second eval file would be a second clock to keep in sync.
    result["prob_calibration"] = prob_calibration_gate(
        games, teams=teams, parks=parks, starters=starters)

    # --- the benchmark ladder (B6, section 6, dark) -----------------------
    # `_per_game_p` is working state, never artifact content: the ladder needs
    # the model's own graded probabilities to recompute tiers on identical
    # games, and it is popped from every graded block before the write.
    per_game, per_game_markets = {}, {}
    if isinstance(result.get("vintage"), dict):
        per_game = result["vintage"].pop("_per_game_p", None) or {}
        per_game_markets = result["vintage"].pop("_per_game_markets", None) or {}
    for k in ("in_sample", "forward"):
        if isinstance(result.get(k), dict):
            result[k].pop("_per_game_p", None)
            result[k].pop("_per_game_markets", None)
    result["benchmarks"] = _benchmarks_block(games, result["vintage"], per_game)

    # --- the per-market objective (B-OBJ, section 7e, dark) ---------------
    result["per_market"] = per_market_objective(games, result["vintage"],
                                                per_game_markets)

    # --- the ridge fit gate (B-ML-FIT, section 7e) ------------------------
    # Same argument as the dispersion and calibration gates: it is a property of
    # the sample this function already grades, and a second eval file would be a
    # second clock to keep in sync.
    result["ridge_fit"] = ridge_fit_gate(games, teams=teams, parks=parks,
                                         starters=starters, log_fn=log_fn)
    result["ridge_fit"]["fit_window_probe"] = fit_window_probe(
        games, teams=teams, parks=parks, starters=starters)

    # --- the total level gate (BET1, section 7f) --------------------------
    # Same argument again: a property of this sample. A failure here degrades to
    # a stated status, because the moneyline gates above must not be lost to it.
    try:
        result["total_level"] = total_level_gate(games, teams=teams, parks=parks,
                                                 starters=starters, log_fn=log_fn)
    except Exception:                                          # noqa: BLE001
        log.warning("betting_model: total level gate failed", exc_info=True)
        result["total_level"] = {"status": "failed", "verdict": "indeterminate",
                                 "ship": False, "served": SERVE_TOTAL_LEVEL}

    result["min_edge_gate"] = min_edge_gate(result["vintage"])
    result["min_edge"] = result["min_edge_gate"]["min_edge"]
    result["gates_picks"] = bool(result["min_edge"] is not None)
    result["validated"] = bool(result["min_edge_gate"]["all_gates_open"])
    result["contaminated"] = not result["validated"]
    result["headline_mode"] = "vintage" if result["validated"] else "contaminated"

    result["status"] = "ran"
    result["note"] = ("Two modes, both labelled. The in-sample and forward numbers are "
                      "CONTAMINATED: their features are season-to-date leaderboards that "
                      "contain the games being graded. The vintage number is the honest "
                      f"one and it graded {result['vintage'].get('n_graded', 0)} games. "
                      "A pick threshold is set from the vintage mode or from nothing.")
    if write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
        if log_fn:
            log_fn(f"betting_model: wrote {EVAL_PATH.name} "
                   f"(vintage-graded {result['vintage'].get('n_graded', 0)} of "
                   f"{len(games)} games)")
    return result


def _empty_vintage_block(cov: dict, n_games: int) -> dict:
    return {
        "label": "vintage (each game priced on leaderboards dated strictly before it)",
        "mode": "vintage",
        "honest": True,
        "status": "no vintages",
        "n_vintages": int((cov or {}).get("n_vintages") or 0),
        "n_gradable": 0,
        "n_graded": 0,
        "n_skipped_no_vintage": n_games,
        "min_fit_games": VINTAGE_MIN_FIT_GAMES,
        "min_eval_games": VINTAGE_MIN_EVAL_GAMES,
        "min_graded_games_for_min_edge": VINTAGE_MIN_GRADED_GAMES,
        # None, not a zeroed block: "nothing was graded" and "everything graded
        # on a neutral park" are different facts and the reader gets to tell them
        # apart. `_grade_vintage` replaces this the moment anything resolves.
        "park_basis": None,
        # Same contract for the schema-3 dark capture (section 5c).
        "feature_basis": None,
        "note": ("no completed game has a leaderboard vintage dated strictly before it, "
                 "so the honest sample is empty; run leaderboard_vintages.snapshot() "
                 "nightly and this number starts climbing"),
    }


def _vintage_cut_index(gradable: list[dict], dates: list[str]) -> int:
    """The index in `dates` where the fit window ends and the eval window
    begins. Whole slates never straddle the boundary, because the split is by
    date. See VINTAGE_FIT_TARGET_GAMES for why this is a target size rather
    than a share."""
    if VINTAGE_FIT_WINDOW_GROWS:
        # The fit half is the date share and both windows grow with the archive.
        # See VINTAGE_FIT_WINDOW_GROWS for what that costs the eval clock.
        return max(1, min(int(len(dates) * VINTAGE_FIT_MAX_DATE_SHARE),
                          len(dates) - 1))
    per_date: dict[str, int] = {}
    for g in gradable:
        per_date[g.get("date")] = per_date.get(g.get("date"), 0) + 1
    cum, target_idx = 0, len(dates) - 1
    for i, d in enumerate(dates):
        cum += per_date.get(d, 0)
        if cum >= VINTAGE_FIT_TARGET_GAMES:
            target_idx = i + 1
            break
    half_idx = max(1, int(len(dates) * VINTAGE_FIT_MAX_DATE_SHARE))
    return max(1, min(target_idx, half_idx, len(dates) - 1))


def _grade_vintage(games: list[dict], cov: dict, grade_fn, *, log_fn=None) -> dict:
    """The honest mode. Grades only games that have a vintage strictly before
    them, and refits everything inside that window on vintage features.

    The split is by DATE, not by row, so no two games from the same slate land
    on opposite sides of the fit/eval boundary.

    THE PARK BASIS IS REPORTED, not assumed. Every input this mode uses is dated
    strictly before its game, but the park column only exists on schema 2
    vintages; games whose record predates it are priced with the park term at a
    flat neutral and counted here. That is a stated loss of a feature, which is
    an honest number. Silently borrowing the live index for them, which is what
    this did before, was not."""
    reset_vintage_cache()
    block = _empty_vintage_block(cov, len(games))
    resolve, rstats = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    block["n_gradable"] = len(gradable)
    block["n_skipped_no_vintage"] = len(games) - len(gradable)
    if not gradable:
        return block
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    # THE GRADABLE SPAN, WHICH IS NOT THE GRADED SPAN. Stamped here so a return
    # before the split still carries a span, and OVERWRITTEN below the split by
    # the eval window's own dates. `first_graded_date` used to be set here and
    # never corrected, so it held 2026-07-06, a date inside the FIT half on
    # which nothing was ever graded, while `n_graded` counted only the eval
    # half. betting_learning divides `n_graded` by that span to publish the
    # accrual rate behind the 600-game clock, so the served ETA was computed
    # over 63 days instead of the eval window's 37 and ran about 70% slow.
    block["first_gradable_date"] = dates[0] if dates else None
    block["last_gradable_date"] = dates[-1] if dates else None
    block["first_graded_date"] = dates[0] if dates else None
    block["last_graded_date"] = dates[-1] if dates else None
    need = VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES
    if len(gradable) < need or len(dates) < 4:
        block["status"] = "insufficient vintage coverage"
        block["note"] = (f"{len(gradable)} games have a vintage; the honest mode needs at "
                         f"least {need} to split into a fit and an eval window, and "
                         f"{VINTAGE_MIN_GRADED_GAMES} graded before min_edge may be fitted")
        block["park_basis"] = _park_basis(rstats, gradable, [])
        block["feature_basis"] = _feature_basis(rstats, gradable, [])
        return block
    cut = dates[_vintage_cut_index(gradable, dates)]
    fit_g = [g for g in gradable if (g.get("date") or "") < cut]
    ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
    if len(fit_g) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES:
        block["status"] = "insufficient vintage coverage"
        block["note"] = (f"vintage split at {cut} leaves {len(fit_g)} fit and {len(ev_g)} "
                         f"eval games, below the {VINTAGE_MIN_FIT_GAMES}/"
                         f"{VINTAGE_MIN_EVAL_GAMES} floors")
        block["park_basis"] = _park_basis(rstats, gradable, ev_g)
        block["feature_basis"] = _feature_basis(rstats, gradable, ev_g)
        return block
    park_basis = _park_basis(rstats, gradable, ev_g)
    featb = _feature_basis(rstats, gradable, ev_g)
    # THE MODE LABEL SAYS WHAT IS ACTUALLY DATED. It used to read "features dated
    # strictly before each game; no leakage", which was false for the park index
    # in every build, and would go on being false for any game whose vintage
    # predates the park column even now.
    if park_basis["n_games_neutral_park"]:
        label = (f"vintage forward from {cut} (team, pitcher and park inputs dated "
                 f"strictly before each game, except {park_basis['n_games_neutral_park']} "
                 f"games whose vintage predates the park column and are priced on a "
                 f"NEUTRAL park)")
    else:
        label = (f"vintage forward from {cut} (team, pitcher and park inputs all dated "
                 f"strictly before each game; coefficients and both one-parameter "
                 f"corrections refit inside the window)")
    graded = grade_fn(fit_g, ev_g, label, "vintage", resolve)
    if not graded:                                               # pragma: no cover
        block["status"] = "insufficient vintage coverage"
        block["note"] = "the vintage split produced no gradable rows"
        block["park_basis"] = park_basis
        block["feature_basis"] = featb
        return block
    block.update(graded)
    block["status"] = "graded"
    block["split_date"] = cut
    # The graded span is the EVAL window's, because the eval window is what was
    # graded. Everything before `cut` is what the coefficients were fitted on.
    ev_dates = sorted({g.get("date") for g in ev_g if g.get("date")})
    block["first_graded_date"] = ev_dates[0] if ev_dates else None
    block["last_graded_date"] = ev_dates[-1] if ev_dates else None
    block["n_fit_games"] = len(fit_g)
    block["fit_window"] = {
        "n_games": len(fit_g),
        "first_date": (sorted({g.get("date") for g in fit_g if g.get("date")}) or [None])[0],
        "last_date": (sorted({g.get("date") for g in fit_g if g.get("date")}) or [None])[-1],
        "why_not_graded": ("these are the games the coefficients and both one-parameter "
                           "corrections are FITTED on, so scoring them would be scoring "
                           "the model against its own training data; they are excluded "
                           "from n_graded by construction and not by oversight"),
    }
    block["n_graded"] = graded["n"]
    block["park_basis"] = park_basis
    block["feature_basis"] = featb
    block["note"] = (f"{graded['n']} games graded on vintage features; "
                     f"{VINTAGE_MIN_GRADED_GAMES} are needed before min_edge may be "
                     "fitted, and the paired-Brier gate must also clear")
    if park_basis["n_games_neutral_park"]:
        block["note"] += (f". {park_basis['n_eval_games_neutral_park']} of the eval "
                          f"games carry no park term at all (their vintage predates the "
                          f"park column); the park index is NOT borrowed from the live "
                          f"file, which would leak the in-progress season")
    if log_fn:
        log_fn(f"betting_model: vintage mode graded {graded['n']} games "
               f"(brier {graded['brier']} vs home base {graded['brier_home_base']}; "
               f"park basis {park_basis['source']}, "
               f"{park_basis['n_games_neutral_park']} neutral-park games)")
    if park_basis["n_games_neutral_park"]:
        log.warning("betting_model: %d of %d vintage-gradable games have no dated park "
                    "index and were priced on a NEUTRAL park (dates %s..%s). Nightly "
                    "snapshots written from leaderboard_vintages schema 2 onward carry "
                    "one; this number falls to zero on its own as the archive rolls "
                    "forward, and it is never patched with the live index.",
                    park_basis["n_games_neutral_park"], len(gradable),
                    park_basis["neutral_park_first_date"],
                    park_basis["neutral_park_last_date"])
    return block


def _park_basis(rstats: dict, gradable: list[dict], eval_games: list[dict]) -> dict:
    """Which park index priced the vintage sample, in counts.

    The resolver memoizes by DATE (a slate shares a vintage), so the per-game
    counts have to be derived here, where the fit/eval split is known. The eval
    count is the one that matters for the published claim: it is the window the
    Brier gate reads."""
    by_date = (rstats or {}).get("park_source_by_date") or {}
    neutral_dates = sorted(d for d, v in by_date.items() if v == "neutral")
    n_neutral = sum(1 for g in gradable if by_date.get(g.get("date")) == "neutral")
    n_neutral_eval = sum(1 for g in eval_games if by_date.get(g.get("date")) == "neutral")
    n_dated = len(gradable) - n_neutral
    return {
        "source": ("vintage" if not n_neutral else
                   ("neutral" if not n_dated else "mixed")),
        "n_games_vintage_park": n_dated,
        "n_games_neutral_park": n_neutral,
        "n_eval_games_neutral_park": n_neutral_eval,
        "n_dates_neutral_park": len(neutral_dates),
        "neutral_park_first_date": neutral_dates[0] if neutral_dates else None,
        "neutral_park_last_date": neutral_dates[-1] if neutral_dates else None,
        "note": ("the park index is read from each game's own vintage record; a record "
                 "written before the park column existed prices its games on a NEUTRAL "
                 "park (the park term drops out) rather than on the live index, which "
                 "is the in-progress season and would leak the eval window into its own "
                 "features"),
    }


def _feature_basis(rstats: dict, gradable: list[dict], eval_games: list[dict]) -> dict:
    """Which basis each schema-3 dark-capture column rode on, in game counts.
    The park_basis pattern, generalized; park_basis itself is unchanged beside
    this for back-compat.

    Three statuses per (feature, game), and they are different facts a reader
    must be able to tell apart:
      populated        the game's vintage record carries at least one value
      null_stated      the record is schema 3 and says WHY the column is null
      predates_column  the record was written before the column existed
    Counts are over the gradable set and the eval window separately, since the
    eval window is the one any published claim would read. Basis strings are
    collected verbatim off the records, never summarized into a guess."""
    by_date = (rstats or {}).get("feature_basis_by_date") or {}
    # Schema 3 ONLY, by name: the eval artifact's block is unchanged by the
    # per-schema generalization of DARK_TEAM_COLUMNS (2026-09-11). A later
    # schema's harness reads its own columns off the same records.
    features = DARK3_TEAM_COLUMNS + DARK_PITCHER_COLUMNS
    out: dict = {}
    for f in features:
        counts = {"populated": 0, "null_stated": 0, "predates_column": 0}
        eval_counts = {"populated": 0, "null_stated": 0, "predates_column": 0}
        bases: set[str] = set()

        def _status(d):
            ent = (by_date.get(d) or {}).get(f)
            if not isinstance(ent, dict):
                return "predates_column"
            basis = str(ent.get("basis") or "")
            if basis:
                bases.add(basis)
            if (ent.get("n") or 0) > 0:
                return "populated"
            if "predates the column" in basis:
                return "predates_column"
            return "null_stated"

        for g in gradable:
            counts[_status(g.get("date"))] += 1
        for g in eval_games:
            eval_counts[_status(g.get("date"))] += 1
        out[f] = {"n_games": counts, "n_eval_games": eval_counts,
                  "bases": sorted(bases)}
    out["note"] = ("schema-3 dark capture only: counts of gradable and eval games "
                   "whose vintage record carried each column, said why it was null, "
                   "or predates it (docs/diamond-betting.md section 5c). Nothing "
                   "served reads these columns; a null is never filled from live "
                   "files")
    return out


# ---------------------------------------------------------------------------
# the benchmark ladder (B6, docs/diamond-betting.md section 6, dark)
# ---------------------------------------------------------------------------
BENCHMARK_CLAIM_RULE = (
    "never claim an unmeasured tier: a tier with n = 0 has no number and no claim, "
    "and a tier whose n is below the window's n is a SUBSAMPLE comparable only "
    "against the other tiers recomputed on those same games (its same_games block). "
    "The subsample is never the headline")


def _market_fair_probs(dates_needed: set, kind: str) -> dict:
    """{slate_date: {(home_org, away_org): mean de-vigged home probability}}
    from the cached odds snapshots of one kind.

    The EARLIEST capture per slate wins, because for the "open" tier the first
    snapshot is the open; a later re-capture of the same slate is closer to
    first pitch and scoring it as the open would flatter the market tier with
    information the open did not have. Per event, per book: a two-sided h2h
    market is de-vigged proportionally (`devig`) and the home fair
    probabilities are averaged across the books posting one."""
    try:
        import betting_ingest as bi
    except Exception:                                         # noqa: BLE001
        return {}
    out: dict = {}
    for meta in bi.list_snapshots():                          # oldest first
        wrap = bi.load_snapshot(meta["path"])
        if not wrap or wrap.get("kind") != kind:
            continue
        slate = wrap.get("slate_date") or meta["date"]
        if slate not in dates_needed or slate in out:
            continue
        ev_map: dict = {}
        for ev in wrap.get("events") or []:
            ho = _org(ev.get("home_team"))
            ao = _org(ev.get("away_team"))
            if not ho or not ao:
                continue
            fairs = []
            for bk in ev.get("bookmakers") or []:
                for mk in bk.get("markets") or []:
                    if mk.get("key") != "h2h":
                        continue
                    decs = {}
                    for o in mk.get("outcomes") or []:
                        d = bi.american_to_decimal(o.get("price"))
                        if d:
                            decs[o.get("name")] = d
                    if len(decs) != 2:
                        continue
                    fair = devig(decs)
                    p = fair.get(ev.get("home_team"))
                    if p is not None:
                        fairs.append(p)
            if fairs:
                ev_map[(ho, ao)] = sum(fairs) / len(fairs)
        out[slate] = ev_map
    return out


def _benchmarks_block(games: list[dict], vintage_block: dict,
                      model_per_game: dict) -> dict:
    """The pre-registered four-tier ladder on the vintage EVAL window
    (docs/diamond-betting.md section 6, written before this function existed).
    VALIDATION SURFACE ONLY: dark, no served probability reads any tier.

    Every tier is scored on the model's own graded window (`model_per_game`,
    the per-game p_home the vintage grade produced), so `home_constant` here
    reproduces the vintage block's brier_home_base by construction. Tiers that
    can only cover a subsample (the market captures) carry a `same_games`
    block with the OTHER tiers recomputed on exactly those games, which is the
    only comparison the claim rule allows a subsample to appear in."""
    out = {
        "claim_rule": BENCHMARK_CLAIM_RULE,
        "surface": ("validation ladder only, dark: no slot, no record row and "
                    "no exported edge reads a tier"),
    }
    if (vintage_block or {}).get("status") != "graded" or not model_per_game:
        out["status"] = "no vintage eval window"
        out["note"] = ("the ladder scores the vintage eval window and there is "
                       "none to score; it appears when the honest mode grades")
        return out
    ys = {g["game_pk"]: (1 if g["home_runs"] > g["away_runs"] else 0)
          for g in games if g.get("game_pk") in model_per_game}
    window = [g for g in games if g.get("game_pk") in ys]
    pks = [g["game_pk"] for g in window]
    n = len(pks)
    if n < 2:
        out["status"] = "window too small"
        return out

    def _brier_on(pmap: dict, sub) -> float:
        return round(sum((pmap[pk] - ys[pk]) ** 2 for pk in sub) / len(sub), 5)

    home_rate = sum(ys[pk] for pk in pks) / n
    home_map = {pk: home_rate for pk in pks}
    tiers: dict = {
        "model_vintage": {
            "n": n, "brier": _brier_on(model_per_game, pks),
            "source": "the vintage block's own graded eval window",
        },
        "home_constant": {
            "n": n, "brier": _brier_on(home_map, pks),
            "p_constant": round(home_rate, 4),
            "source": ("the eval window's home win rate as a constant, the "
                       "identical base brier_home_base uses"),
        },
    }
    # Tier 4: Elo from results only, literature constants, never fitted here.
    elo_map: dict = {}
    try:
        from tools import betting_elo
        elo_map = betting_elo.elo_probabilities(games)
        e_pks = [pk for pk in pks if pk in elo_map]
        tiers["elo_literature"] = {
            "n": len(e_pks),
            "brier": _brier_on(elo_map, e_pks) if e_pks else None,
            "config": {"k": betting_elo.LITERATURE_K,
                       "home_adv_elo": betting_elo.LITERATURE_HOME_ADV_ELO,
                       "base": betting_elo.BASE_RATING,
                       "standing": ("literature priors, never fitted on the eval "
                                    "window or anywhere else; season starts flat, "
                                    "no carryover")},
            "source": "tools/betting_elo.py walking this season's results only",
        }
    except Exception:                                         # noqa: BLE001
        log.warning("betting_model: Elo ladder tier unavailable", exc_info=True)
        tiers["elo_literature"] = {"n": 0, "brier": None,
                                   "status": "unavailable: tools/betting_elo "
                                             "failed to run, so this tier is "
                                             "unmeasured and claims nothing"}
    # Tiers 2 and 3: the de-vigged market, open and close captures.
    dates_needed = {g.get("date") for g in window if g.get("date")}
    for kind, name in (("open", "market_open_devig"), ("close", "market_close_devig")):
        fair_by_slate = _market_fair_probs(dates_needed, kind)
        matched: dict = {}
        for g in window:
            p = (fair_by_slate.get(g.get("date")) or {}).get(
                (g["home_org"], g["away_org"]))
            if p is not None:
                matched[g["game_pk"]] = p
        m_pks = sorted(matched)
        if not m_pks:
            tiers[name] = {
                "n": 0, "brier": None,
                "status": (f"no {kind} capture matched a graded eval game; this "
                           "tier is unmeasured and claims nothing" +
                           ("" if kind == "open" else
                            ". It auto-appears as close captures accrue; the "
                            "close job runbook is section 3")),
            }
            continue
        sub_rate = sum(ys[pk] for pk in m_pks) / len(m_pks)
        tiers[name] = {
            "n": len(m_pks),
            "brier": _brier_on(matched, m_pks),
            "n_slates_with_capture": len([s for s, m in fair_by_slate.items() if m]),
            "same_games": {
                "model": _brier_on(model_per_game, m_pks),
                "home_constant": _brier_on({pk: sub_rate for pk in m_pks}, m_pks),
                "elo_literature": (_brier_on(elo_map, [pk for pk in m_pks if pk in elo_map])
                                   if elo_map and any(pk in elo_map for pk in m_pks)
                                   else None),
                "note": ("the only comparison a subsample may appear in: every "
                         "tier recomputed on exactly these games"),
            },
            "subsample_note": (f"{len(m_pks)} of the window's {n} games have a "
                               f"cached {kind} capture; a doubleheader's two games "
                               "read the same capture"),
            "source": (f"proportional de-vig of the earliest {kind} snapshot per "
                       "slate, home fair probability averaged across books "
                       "posting a two-sided h2h market"),
        }
    out.update({
        "status": "ran",
        "window": {"split_date": vintage_block.get("split_date"), "n": n,
                   "first_date": min(dates_needed) if dates_needed else None,
                   "last_date": max(dates_needed) if dates_needed else None},
        "tiers": tiers,
    })
    return out


# ---------------------------------------------------------------------------
# B-OBJ: the per-market objective (docs/diamond-betting.md section 7e)
# ---------------------------------------------------------------------------
#: The markets this block scores. Props are absent on purpose: the props pull
#: is inert (section 7c), so a props market here would be a row of nulls
#: pretending to be a measurement.
PER_MARKET_MARKETS = ("moneyline", "runline", "total")
#: Games in the same-games accuracy window before the accuracy leg may be read.
#: 100 mirrors betting_shadow.MIN_BETS_FOR_SWEEP and the section 7b n floor, so
#: this module has one small-sample floor and not three.
PER_MARKET_MIN_CALIBRATION_GAMES = 100
#: Settled rows in ONE (market, rule) cell before its ROI may be read.
PER_MARKET_MIN_ROI_ROWS = 100
#: Non-inferiority bar on the accuracy leg: the paired per-game Brier of the
#: model minus the market open, one-sided 95% lower bound, on the same games.
PER_MARKET_ACCURACY_LB95_FLOOR = -0.002
#: The stake fraction the growth leg reports at. Quarter Kelly, and it is a
#: REPORTED quantity only: the public record stakes flat 1 unit, always
#: (section 7a), because a variable stake makes a published ROI unauditable.
PER_MARKET_KELLY_FRACTION = 0.25
#: CLV is ONE KEY CARRYING A REASON, not a column of nulls. Measured 2026-09-06:
#: 22 cached odds snapshots, all of kind "open", zero of kind "close", and 0 of
#: the 255 ledger rows carry a close price of any name.
CLV_UNAVAILABLE_REASON = (
    "close job never installed; 0 settled ledger rows carry a close price")
PER_MARKET_OBJECTIVE = (
    "LEXICOGRAPHIC, ACCURACY FIRST (owner decision 2026-09-05, decision 6). Per "
    "market: (1) the ACCURACY leg is paired per-game Brier and log loss on the "
    "vintage eval window against the ladder tiers, always including the market "
    "OPEN tier recomputed on the same games, and it is read FIRST; (2) the ROI "
    "leg is flat-stake ROI with the one-sided 95% lower bound `sweep_min_edge` "
    "already uses, plus expected log growth at quarter Kelly on the recorded "
    "price, per (market, rule) cell. A market may set a threshold only when its "
    "accuracy leg is NON-INFERIOR to the market open on the same games (paired "
    "Brier lb95 >= -0.002) AND its ROI leg clears an lb95 above zero at n >= 100 "
    "inside ONE (market, rule) cell. A market that fails the accuracy leg has "
    "its ROI leg REPORTED and NOT CONSULTED: a positive ROI on a market whose "
    "probabilities lose to the open is a sample, not a finding. Floors: "
    "100 canonical games per market for the accuracy leg, 100 settled rows per "
    "(market, rule) cell for ROI. CLV is one key carrying the reason it does not "
    "exist, never a null column."
)
PER_MARKET_SURFACE = (
    "validation surface only, dark: no slot, no record row, no exported edge and "
    "no min_edge reads this block. It states what each market WOULD have to show; "
    "nothing consults it, the same standing the section 6 ladder ships under")


def _modal_point(by_point: dict) -> float:
    """The line most books posted, ties broken by the lower number so the choice
    is deterministic. For the runline that means the home favourite reading
    (-1.5) wins a tie; for the total it means the lower line does."""
    return sorted(by_point, key=lambda k: (-len(by_point[k]), k))[0]


def _market_open_by_market(dates_needed: set) -> dict:
    """{slate: {(home_org, away_org): {market: spec}}} from the EARLIEST cached
    open snapshot per slate.

    A SECOND WALKER, DELIBERATELY. `_market_fair_probs` serves the section 6
    ladder and its numbers are published; widening it to three markets would
    change what that ladder reports as a side effect of adding this block. The
    earliest-capture rule, the proportional de-vig and the across-books average
    are the same three rules, applied to three markets instead of one.

    The three specs:
      moneyline  {"p_home"}              de-vigged P(home wins)
      runline    {"home_point", "p_home_cover"}
                 the HOME side of the posted 1.5 spread, whichever way it is
                 posted. Fixing the event as "home wins by 2+" instead would be
                 unpriced on every game where the home team is the underdog,
                 because the book posts home +1.5 there and never prices home
                 -1.5 at all.
      total      {"line", "p_over"}      de-vigged P(over) at the modal line.
                 On a whole-number line a de-vigged two-way over/under is
                 already conditional on no push, which is exactly what
                 `total_side_probabilities` returns, so the two sides of the
                 comparison condition on the same event.

    A DOUBLEHEADER'S TWO GAMES READ THE SAME CAPTURE, because the key is
    (home_org, away_org) and the snapshot has one entry for the pair. That is
    the existing ladder's behaviour, stated there as `subsample_note`, kept here
    so the two surfaces do not disagree about the same slate."""
    try:
        import betting_ingest as bi
    except Exception:                                         # noqa: BLE001
        return {}
    out: dict = {}
    for meta in bi.list_snapshots():                          # oldest first
        wrap = bi.load_snapshot(meta["path"])
        if not wrap or wrap.get("kind") != "open":
            continue
        slate = wrap.get("slate_date") or meta["date"]
        if slate not in dates_needed or slate in out:
            continue
        ev_map: dict = {}
        for ev in wrap.get("events") or []:
            ho, ao = _org(ev.get("home_team")), _org(ev.get("away_team"))
            if not ho or not ao:
                continue
            hn = ev.get("home_team")
            ml: list = []
            rl: dict = {}
            tl: dict = {}
            for bk in ev.get("bookmakers") or []:
                for mk in bk.get("markets") or []:
                    key = mk.get("key")
                    outs = mk.get("outcomes") or []
                    decs, pts = {}, {}
                    for o in outs:
                        d = bi.american_to_decimal(o.get("price"))
                        if d:
                            decs[o.get("name")] = d
                            if o.get("point") is not None:
                                pts[o.get("name")] = float(o["point"])
                    if len(decs) != 2:
                        continue
                    if key == "h2h":
                        f = devig(decs).get(hn)
                        if f is not None:
                            ml.append(f)
                    elif key == "spreads":
                        if hn in pts and abs(pts[hn]) == 1.5 and len(pts) == 2:
                            f = devig(decs).get(hn)
                            if f is not None:
                                rl.setdefault(pts[hn], []).append(f)
                    elif key == "totals":
                        if (pts.get("Over") is not None
                                and pts.get("Over") == pts.get("Under")):
                            f = devig(decs).get("Over")
                            if f is not None:
                                tl.setdefault(pts["Over"], []).append(f)
            rec: dict = {}
            if ml:
                rec["moneyline"] = {"p_home": sum(ml) / len(ml), "n_books": len(ml)}
            if rl:
                pt = _modal_point(rl)
                rec["runline"] = {"home_point": pt,
                                  "p_home_cover": sum(rl[pt]) / len(rl[pt]),
                                  "n_books": len(rl[pt])}
            if tl:
                pt = _modal_point(tl)
                rec["total"] = {"line": pt, "p_over": sum(tl[pt]) / len(tl[pt]),
                                "n_books": len(tl[pt])}
            if rec:
                ev_map[(ho, ao)] = rec
        out[slate] = ev_map
    return out


def _market_outcome(game: dict, market: str, spec: dict):
    """The observed 0/1 for one market on one game, or None when the game does
    not resolve it (a total that lands exactly on the line is a PUSH and is
    dropped from both sides of the comparison, never scored as a loss)."""
    hr, ar = game.get("home_runs"), game.get("away_runs")
    if hr is None or ar is None:
        return None
    if market == "moneyline":
        return 1 if hr > ar else 0
    if market == "runline":
        pt = spec.get("home_point")
        if pt is None:
            return None
        return 1 if (hr - ar) + float(pt) > 0 else 0
    if market == "total":
        line = spec.get("line")
        if line is None:
            return None
        tot = hr + ar
        if float(tot) == float(line):
            return None
        return 1 if tot > float(line) else 0
    return None                                               # pragma: no cover


def _model_market_prob(rec: dict, market: str, spec: dict, run_alpha):
    """The model's probability of the SAME event the market spec names.

    The total is recomputed from the game's own lambdas at the book's line
    rather than read off a stored number, because the model prices a total only
    once a line exists and the line is a property of the capture, not of the
    model."""
    if not rec:
        return None
    if market == "moneyline":
        return rec.get("p_home")
    if market == "runline":
        pt = spec.get("home_point")
        if pt == -1.5:
            return rec.get("p_home_minus_1_5")
        if pt == 1.5:
            return rec.get("p_home_plus_1_5")
        return None
    if market == "total":
        line = spec.get("line")
        lh, la = rec.get("lam_home"), rec.get("lam_away")
        if line is None or lh is None or la is None:
            return None
        _, tot = _score_joint(float(lh), float(la), _alpha_to_r(run_alpha))
        return total_side_probabilities(tot, float(line)).get("p_over")
    return None                                               # pragma: no cover


def _per_market_accuracy(games: list[dict], model_markets: dict, run_alpha,
                         elo_map: dict) -> dict:
    """The accuracy leg, one entry per market in PER_MARKET_MARKETS.

    Every tier is scored on EXACTLY the games that carry both a model price and
    an open capture for that market, which is the only comparison the section 6
    claim rule allows a subsample to appear in. The constant tier is the
    subsample's own base rate, fitted on the games it scores, the same way the
    ladder's `home_constant` is and with the same caveat."""
    by_pk = {g.get("game_pk"): g for g in games if g.get("game_pk") is not None}
    dates_needed = {g.get("date") for g in games
                    if g.get("game_pk") in model_markets and g.get("date")}
    opens = _market_open_by_market(dates_needed)
    out: dict = {}
    for market in PER_MARKET_MARKETS:
        m_ps, k_ps, ys, e_ps, e_ys, pushes = [], [], [], [], [], 0
        n_no_capture = 0
        for pk, rec in model_markets.items():
            g = by_pk.get(pk)
            if not g:
                continue                                      # pragma: no cover
            spec = ((opens.get(g.get("date")) or {}).get(
                (g.get("home_org"), g.get("away_org"))) or {}).get(market)
            if not spec:
                n_no_capture += 1
                continue
            mp = _model_market_prob(rec, market, spec, run_alpha)
            kp = (spec.get("p_home") if market == "moneyline"
                  else spec.get("p_home_cover") if market == "runline"
                  else spec.get("p_over"))
            y = _market_outcome(g, market, spec)
            if mp is None or kp is None:
                continue
            if y is None:
                pushes += 1
                continue
            m_ps.append(float(mp))
            k_ps.append(float(kp))
            ys.append(int(y))
            if market == "moneyline" and pk in elo_map:
                e_ps.append(float(elo_map[pk]))
                e_ys.append(int(y))
        n = len(ys)
        entry = {
            "n_games": n,
            "floor": PER_MARKET_MIN_CALIBRATION_GAMES,
            "floor_met": n >= PER_MARKET_MIN_CALIBRATION_GAMES,
            "n_eval_games_without_an_open_capture": n_no_capture,
            "n_pushes_dropped": pushes,
        }
        if n < 2:
            entry.update({"status": "no same-games window",
                          "non_inferior": False,
                          "note": ("no eval game carries both a model price and an "
                                   f"open capture of the {market}; this market is "
                                   "unmeasured and claims nothing")})
            out[market] = entry
            continue
        base = sum(ys) / n
        m_br, m_ll = _per_game_losses(m_ps, ys)
        k_br, k_ll = _per_game_losses(k_ps, ys)
        c_br, c_ll = _per_game_losses([base] * n, ys)
        tiers = {
            "model_vintage": {"n": n, "brier": round(_brier(m_ps, ys), 5),
                              "log_loss": round(_logloss(m_ps, ys), 5)},
            "market_open_devig": {"n": n, "brier": round(_brier(k_ps, ys), 5),
                                  "log_loss": round(_logloss(k_ps, ys), 5)},
            "base_rate_constant": {"n": n, "p_constant": round(base, 4),
                                   "brier": round(_brier([base] * n, ys), 5),
                                   "log_loss": round(_logloss([base] * n, ys), 5),
                                   "source": ("the same-games base rate, fitted on "
                                              "the games it scores")},
        }
        if len(e_ys) >= 2:
            tiers["elo_literature"] = {
                "n": len(e_ys), "brier": round(_brier(e_ps, e_ys), 5),
                "log_loss": round(_logloss(e_ps, e_ys), 5),
                "source": "tools/betting_elo.py, moneyline only by construction"}
        elif market == "moneyline":
            tiers["elo_literature"] = {"n": 0, "brier": None,
                                       "status": "unavailable, so it claims nothing"}
        vs_open_brier = _paired_delta(k_br, m_br)
        entry.update({
            "status": "measured",
            "tiers": tiers,
            "model_vs_market_open": {
                "brier": vs_open_brier,
                "log_loss": _paired_delta(k_ll, m_ll),
                "note": ("incumbent is the market open, challenger is the model; "
                         "positive means the MODEL is better"),
            },
            "model_vs_base_rate": {"brier": _paired_delta(c_br, m_br),
                                   "log_loss": _paired_delta(c_ll, m_ll)},
            "non_inferiority_bar": PER_MARKET_ACCURACY_LB95_FLOOR,
            "non_inferior": bool(
                n >= PER_MARKET_MIN_CALIBRATION_GAMES
                and vs_open_brier.get("lb95") is not None
                and vs_open_brier["lb95"] >= PER_MARKET_ACCURACY_LB95_FLOOR),
        })
        out[market] = entry
    return out


def _per_market_roi_cells() -> dict:
    """The ROI leg, one entry per (market, rule) cell of the shadow ledger.

    THE SAMPLE COMES FROM betting_shadow AND ITS SHAPING RULES, not from a
    second reading of the same file. `graded_bets_by_market_tag` is the public
    per-cell reader; the raw rows are walked in parallel ONLY to recover
    `model_prob`, which the sweep row does not carry and the Kelly leg cannot be
    computed without. The two counts are compared per cell and a disagreement is
    REPORTED rather than reconciled: if they ever diverge, one of the two samples
    is wrong and neither number should be read until somebody knows which.

    Flat stake is the published quantity. The quarter-Kelly growth beside it is
    a REPORTED diagnostic and is not what the record stakes; see
    PER_MARKET_KELLY_FRACTION."""
    try:
        import betting_shadow as bs
    except Exception:                                         # noqa: BLE001
        return {"status": "no ledger", "cells": {},
                "reason": "betting_shadow is not importable in this checkout"}
    try:
        era = bs.PER_MARKET_CAP_ERA
        cells = bs.graded_bets_by_market_tag(era=era)
    except Exception:                                         # noqa: BLE001
        log.warning("betting_model: per-cell ledger reader unavailable", exc_info=True)
        return {"status": "no per-cell reader", "cells": {},
                "reason": ("betting_shadow.graded_bets_by_market_tag is not available; "
                           "the per-market ROI leg refuses to rebuild the cells itself")}
    raw: dict = {}
    try:
        for r in bs.load():
            if r.get("result") not in ("won", "lost"):
                continue
            if r.get("edge") is None or not r.get("decimal"):
                continue
            m = bs.market_of(r)
            for t in bs.row_tags(r):
                if bs.era_split_applies(m, t) and bs.budget_era(r) != era:
                    continue
                raw.setdefault((m, t), []).append(r)
    except Exception:                                         # noqa: BLE001
        log.warning("betting_model: raw ledger walk failed", exc_info=True)
        raw = {}
    out: dict = {}
    for key, rows in sorted(cells.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        market, tag = key
        n = len(rows)
        profits = [(float(r["decimal"]) - 1.0) if r.get("won") else -1.0
                   for r in rows if _pos(r.get("decimal"))]
        entry = {"market": market, "rule": tag, "n": n,
                 "floor": PER_MARKET_MIN_ROI_ROWS,
                 "floor_met": n >= PER_MARKET_MIN_ROI_ROWS}
        if profits:
            mu = sum(profits) / len(profits)
            var = sum((x - mu) ** 2 for x in profits) / len(profits)
            se = math.sqrt(var / len(profits)) if var else 0.0
            entry.update({
                "n_priced": len(profits),
                "roi": round(mu, 5),
                "roi_lower_95": round(mu - Z_95_ONE_SIDED * se, 5),
                "clears_lb95": bool(mu - Z_95_ONE_SIDED * se > 0),
            })
        mrows = raw.get(key) or []
        if len(mrows) != n:
            entry["kelly"] = {
                "status": "unavailable",
                "reason": (f"the per-cell reader returned {n} rows and the parallel "
                           f"raw walk found {len(mrows)}; the two samples disagree and "
                           "neither growth number is trustworthy until they do not"),
            }
        else:
            gs, skipped = [], 0
            for r in mrows:
                pm, dec = r.get("model_prob"), r.get("decimal")
                if pm is None or not _pos(dec):
                    skipped += 1
                    continue
                f = PER_MARKET_KELLY_FRACTION * kelly_fraction(float(pm), float(dec))
                f = max(0.0, min(f, 0.99))
                if r.get("result") == "won":
                    gs.append(math.log(1.0 + f * (float(dec) - 1.0)))
                else:
                    gs.append(math.log(max(1e-9, 1.0 - f)))
            entry["kelly"] = {
                "fraction": PER_MARKET_KELLY_FRACTION,
                "n": len(gs), "n_skipped_no_model_prob": skipped,
                "log_growth_per_bet": (round(sum(gs) / len(gs), 6) if gs else None),
                "basis": ("realized mean log growth per settled bet at quarter Kelly on "
                          "the RECORDED price; reported, never staked"),
            }
        out[f"{market}::{tag}"] = entry
    return {"status": "ran", "era": era, "cells": out,
            "clv_unavailable": CLV_UNAVAILABLE_REASON,
            "note": ("one cell per (market, rule); there is no pooled row here and "
                     "betting_shadow.MarketTagCells refuses to build one")}


def per_market_objective(games: list[dict], vintage_block: dict,
                         model_markets: dict) -> dict:
    """The section 7e per-market objective, assembled and adjudicated.

    LEXICOGRAPHIC, ACCURACY FIRST. See PER_MARKET_OBJECTIVE for the clauses.
    The ROI leg is computed and reported for every market whether or not the
    accuracy leg cleared, and `roi_consulted` says which markets were allowed to
    use it. A market that fails accuracy and shows a positive ROI is a market
    with a sample, not a market with a finding.

    DARK. See PER_MARKET_SURFACE: nothing served reads this."""
    out = {
        "objective": PER_MARKET_OBJECTIVE,
        "surface": PER_MARKET_SURFACE,
        "markets": list(PER_MARKET_MARKETS),
    }
    roi = _per_market_roi_cells()
    out["roi"] = roi
    if (vintage_block or {}).get("status") != "graded" or not model_markets:
        out["status"] = "no vintage eval window"
        out["note"] = ("the accuracy leg scores the vintage eval window and there is "
                       "none to score; the ROI leg above is reported anyway because "
                       "it does not depend on one")
        return out
    elo_map = {}
    try:
        from tools import betting_elo
        elo_map = betting_elo.elo_probabilities(games)
    except Exception:                                         # noqa: BLE001
        log.warning("betting_model: per-market Elo tier unavailable", exc_info=True)
    alpha = (vintage_block or {}).get("run_dispersion_alpha")
    acc = _per_market_accuracy(games, model_markets, alpha, elo_map)
    verdicts: dict = {}
    for market in PER_MARKET_MARKETS:
        a = acc.get(market) or {}
        cells = {k: v for k, v in (roi.get("cells") or {}).items()
                 if v.get("market") == market}
        clearing = sorted(k for k, v in cells.items()
                          if v.get("floor_met") and v.get("clears_lb95"))
        ok_acc = bool(a.get("non_inferior"))
        if not a.get("floor_met"):
            reason = (f"accuracy leg unmeasured: {a.get('n_games', 0)} same-games "
                      f"comparisons against the market open, floor is "
                      f"{PER_MARKET_MIN_CALIBRATION_GAMES}")
        elif not ok_acc:
            lb = ((a.get("model_vs_market_open") or {}).get("brier") or {}).get("lb95")
            reason = (f"accuracy leg failed: paired Brier lb95 {lb} against the market "
                      f"open, bar is {PER_MARKET_ACCURACY_LB95_FLOOR}")
        elif not clearing:
            reason = ("accuracy leg cleared and no (market, rule) cell has an ROI "
                      f"lower bound above zero at n >= {PER_MARKET_MIN_ROI_ROWS}")
        else:
            reason = (f"accuracy leg cleared and {len(clearing)} cell(s) cleared ROI: "
                      + ", ".join(clearing))
        verdicts[market] = {
            "accuracy_ok": ok_acc,
            "roi_consulted": ok_acc,
            "roi_cells_clearing": clearing if ok_acc else [],
            "may_set_a_threshold": bool(ok_acc and clearing),
            "reason": reason,
        }
    out.update({
        "status": "ran",
        "window": {"split_date": (vintage_block or {}).get("split_date"),
                   "n_eval_games": (vintage_block or {}).get("n")},
        "accuracy": acc,
        "verdicts": verdicts,
        "lexicographic_note": ("`roi_cells_clearing` is empty for any market whose "
                               "accuracy leg did not clear, even when a cell would "
                               "have qualified on its own numbers. That is the order "
                               "of the rule, not a missing measurement: the cell is "
                               "in `roi.cells` and can be read there"),
    })
    return out


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB game probability model (eephus.io).")
    ap.add_argument("--context", action="store_true", help="fit + write betting_model_context.json")
    ap.add_argument("--backtest", action="store_true", help="grade on completed games (offline)")
    ap.add_argument("--gate", action="store_true",
                    help="the min_edge gate state off the last backtest artifact")
    ap.add_argument("--dispersion", action="store_true",
                    help="re-run the section 11a run-dispersion gate on its own")
    ap.add_argument("--ridge", action="store_true",
                    help="re-run the section 7e ridge fit gate and the fit window probe")
    ap.add_argument("--total-level", action="store_true",
                    help="re-run the section 7f total level gate (BET1); writes nothing")
    ap.add_argument("--total-calibration", action="store_true",
                    help="run the section 7h total survival-map gate; writes nothing")
    ap.add_argument("--total-dispersion", action="store_true",
                    help="run the section 7g total-scoped dispersion gate; writes nothing")
    ap.add_argument("--game", nargs=2, metavar=("AWAY", "HOME"), help="price one matchup")
    ap.add_argument("--season", default=None)
    args = ap.parse_args()

    if args.total_calibration:
        tcg = total_calibration_gate(log_fn=print)
        print(f"  total calibration (7h): verdict={tcg.get('verdict')} "
              f"ship={tcg.get('ship')} served={tcg.get('served')}")
        for row in tcg.get("grid") or []:
            if row.get("status") != "ran":
                print(f"    q={row.get('split_q')} {row.get('status')}")
                continue
            gd = row["grid_log_loss_delta"]
            print(f"    q={row['split_q']} cut={row['split_date']} n_fit={row['n_fit']} "
                  f"n_eval={row['n_eval']} a={row['a']} b={row['b']} "
                  f"ll_delta={gd.get('delta')} t={gd.get('t')} pass={row['pass']}")
            for pl in row["per_line"]:
                print(f"      line {pl['line']}: obs {pl['observed_over']} poisson "
                      f"{pl['model_over_poisson']} mapped {pl['model_over_mapped']} "
                      f"d={pl['log_loss_delta'].get('delta')} t={pl['log_loss_delta'].get('t')}")

    if args.total_dispersion:
        tdg = total_dispersion_gate(log_fn=print)
        print(f"  total dispersion (7g): verdict={tdg.get('verdict')} "
              f"ship={tdg.get('ship')} served={tdg.get('served')}")
        for row in tdg.get("grid") or []:
            if row.get("status") != "ran":
                print(f"    q={row.get('split_q')} {row.get('status')}")
                continue
            gd = row["grid_log_loss_delta"]
            print(f"    q={row['split_q']} cut={row['split_date']} n_fit={row['n_fit']} "
                  f"n_eval={row['n_eval']} alpha_T={row['alpha_T']} "
                  f"ll_delta={gd.get('delta')} t={gd.get('t')} pass={row['pass']}")
            for pl in row["per_line"]:
                print(f"      line {pl['line']}: obs {pl['observed_over']} poisson "
                      f"{pl['model_over_poisson']} nb {pl['model_over_nb']} "
                      f"d={pl['log_loss_delta'].get('delta')} t={pl['log_loss_delta'].get('t')}")

    if args.total_level:
        tg = total_level_gate(log_fn=print)
        print(f"  total level (7f): verdict={tg.get('verdict')} ship={tg.get('ship')} "
              f"served={tg.get('served')}")
        for row in tg.get("grid") or []:
            if row.get("status") != "ran":
                print(f"    q={row.get('split_q')} {row.get('status')}")
                continue
            for arm in ("centre", "mean"):
                a = row[arm]
                gd = a["grid_log_loss_delta"]
                print(f"    q={row['split_q']} cut={row['split_date']} "
                      f"n_fit={row['n_fit']} n_eval={row['n_eval']} {arm} "
                      f"delta={a['delta_runs']} ll_delta={gd.get('delta')} "
                      f"t={gd.get('t')} pass={a['pass']}")

    if args.context:
        print(json.dumps(build_context(season=args.season, log_fn=print), indent=1))
    if args.backtest:
        r = backtest(season=args.season, log_fn=print)
        for k in ("in_sample", "forward", "vintage"):
            b = r.get(k)
            if not b or b.get("n") is None:
                continue
            print(f"  [{b.get('mode')}] {b['label']}: n={b['n']} brier={b['brier']} "
                  f"(flat .500 {b['brier_flat_500']}, home-base {b['brier_home_base']}) "
                  f"acc={b['accuracy']} total MAE={b['total_mae']} "
                  f"skill t={(b.get('skill_vs_home_base') or {}).get('t')}")
        v = r.get("vintage") or {}
        print(f"  vintage coverage: {v.get('n_vintages', 0)} snapshots, "
              f"{v.get('n_graded', 0)} of {r.get('n_games', 0)} games gradable "
              f"({v.get('status')})")
        pc = r.get("prob_calibration") or {}
        print(f"  prob_calibration (11b): verdict={pc.get('verdict')} "
              f"ship={pc.get('ship')} served={pc.get('served')}")
        for row in ((pc.get("vintage_arm") or {}).get("grid") or []):
            bd = row.get("brier_delta") or {}
            print(f"    platt q={row.get('split_q')} n_eval={row.get('n_eval')} "
                  f"a={row.get('a')} b={row.get('b')} "
                  f"brier_delta={bd.get('delta')} t={bd.get('t')} "
                  f"pass={row.get('pass')}")
        la = pc.get("ledger_arm") or {}
        print(f"    ledger arm: {la.get('verdict')} "
              f"(n={la.get('n_games')} of {la.get('need')})")
        bmk = r.get("benchmarks") or {}
        if bmk.get("status") == "ran":
            for tname, row in (bmk.get("tiers") or {}).items():
                print(f"    ladder {tname}: n={row.get('n')} brier={row.get('brier')}")
        rf = r.get("ridge_fit") or {}
        print(f"  ridge_fit (7e): verdict={rf.get('verdict')} ship={rf.get('ship')} "
              f"served={rf.get('served')}")
        pm = r.get("per_market") or {}
        for mname, vd in (pm.get("verdicts") or {}).items():
            acc = (pm.get("accuracy") or {}).get(mname) or {}
            print(f"    per_market {mname}: n={acc.get('n_games')} "
                  f"accuracy_ok={vd.get('accuracy_ok')} "
                  f"may_set_a_threshold={vd.get('may_set_a_threshold')}")
        print(f"  min_edge: {r.get('min_edge')}")
        for g in (r.get("min_edge_gate") or {}).get("gates") or []:
            print(f"    gate {g['id']}: {'OPEN' if g['open'] else 'closed'} "
                  f"(have {g['have']}, need {g['need']})")
    if args.gate:
        ev = _load_json(EVAL_PATH) or {}
        print(json.dumps(min_edge_gate(ev.get("vintage")), indent=1))
    if args.dispersion:
        # Standalone so the gate can be re-run against a grown cache without
        # rewriting the whole eval artifact. It writes nothing.
        d = run_dispersion_gate()
        print(json.dumps(d, indent=1))
        print(f"  served: {SERVE_RUN_DISPERSION} (alpha {run_dispersion_alpha()})")
        for c in d.get("checks") or []:
            print(f"    {'PASS' if c['pass'] else 'FAIL'}  {c['criterion']}: "
                  f"{c['value']} against {c['threshold']}"
                  + (f" at t={c['t']}" if c.get("t") is not None else ""))
    if args.ridge:
        # Standalone so the gate can be re-run against a grown archive without
        # rewriting the whole eval artifact. It writes nothing.
        rg = ridge_fit_gate(log_fn=print)
        print(f"  ridge_fit (7e): verdict={rg.get('verdict')} ship={rg.get('ship')} "
              f"served={rg.get('served')}")
        for row in rg.get("grid") or []:
            if row.get("status") != "ran":
                print(f"    q={row.get('split_q')} {row.get('status')}")
                continue
            bd = row.get("brier_delta") or {}
            print(f"    q={row['split_q']} cut={row['split_date']} "
                  f"fit={row['n_fit']} eval={row['n_eval']} "
                  f"ols {row['ols']['brier']} ridge {row['ridge']['brier']} "
                  f"delta={bd.get('delta')} lb95={bd.get('lb95')} pass={row['pass']}")
        sw = rg.get("served_window") or {}
        if sw.get("ols"):
            print(f"    served window {sw.get('split_date')} "
                  f"(fit {sw.get('n_fit')} / eval {sw.get('n_eval')}): "
                  f"ols {sw['ols']['brier']} ridge {sw['ridge']['brier']} "
                  f"delta={(sw.get('brier_delta') or {}).get('delta')}")
        pr = fit_window_probe()
        print(f"  fit_window_probe: non_inferior_everywhere="
              f"{pr.get('non_inferior_everywhere')} served={pr.get('served')}")
        for row in pr.get("grid") or []:
            if row.get("status") != "ran":
                print(f"    q={row.get('split_q')} {row.get('status')}")
                continue
            bd = row.get("brier_delta") or {}
            print(f"    q={row['split_q']} anchored {row['n_fit_anchored']} vs grown "
                  f"{row['n_fit_grown']} on {row['n_eval']}: "
                  f"delta={bd.get('delta')} t={bd.get('t')} lb95={bd.get('lb95')}")
    if args.game:
        away, home = _org(args.game[0]), _org(args.game[1])
        gp = game_probabilities(home, away)
        if not gp:
            print(f"no leaderboard rows for {away} / {home}")
        else:
            gp.pop("over", None)
            gp.pop("total_sides", None)      # callable; not JSON-serializable
            gp.pop("runline_at_split", None)   # callable too
            print(json.dumps(gp, indent=1))
