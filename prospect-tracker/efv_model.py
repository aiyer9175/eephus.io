# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV Pass 2 -- the HITTER model + leakage-free out-of-time backtest vs consensus FV.

Trains the eFV hitter model on the Pass-1 matrix (data/xfv_hitter_matrix.json) and scores
it forward-chained against the consensus-FV-only baseline (the bar established in Pass 1).
Honest by mandate: the loser is committed either way (program rule), and we expect a TIE
on rank per the Phase-1 verdict -- the flagship case rests on the distribution/surplus
(Pass 3), not a rank win.

  TARGET     first-6-season summed bWAR, KM-censored (target_censored), sample-weighted by
             observed fraction; resolved-only run as the sensitivity check.
  COHORT     hitters; decision-year = debut_year (debuted) or last-prospect-point year + 1
             (bust). Forward-chained: predict cohort year Y with models fit on rows whose
             decision_year < Y. Two evals: DEBUTED-ONLY (clean WAR regression, the
             prospect_path protocol) and FULL-POOL (debuted + busts; the rank-the-board task,
             with the decision-year-proxy caveat stated).
  MODELS     baseline = within-fold OLS WAR~consensus_fv_raw (Spearman == FV's rank corr);
             eFV-core = prior-anchored ridge (FV dominant, standardized, alpha tuned in-fold);
             challenger = monotone LightGBM; comps = distance-weighted k-NN (also the UI
             feature); ensemble = mean(ridge, lgbm).
  GATE       a model beats consensus only if it wins BOTH pooled-OOS MAE and Spearman.

Artifact: data/xfv_eval.json. Run: python efv_model.py
"""

from __future__ import annotations

import json
import logging
import math
import random
import statistics
from datetime import date
from pathlib import Path

from prospect_path import (_spearman, _calibration, _score, _fit_ridge, _predict,
                           _fit_linear_calibration)

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
MATRIX_PATH = DATA_DIR / "xfv_hitter_matrix.json"
OUT_PATH = DATA_DIR / "xfv_eval.json"

# Forward-chained test cohorts (>= ~30 test rows each; earlier years seed the first fold).
#
# PROMOTED 2026-08-06 BY OWNER DECISION, from (2020, 2021, 2022, 2023) to the full
# 11-fold chain. Lane C3. This is a deliberate protocol change, not a fix, and the
# owner took it with the costs below in front of them.
#
# WHAT IT BUYS. Fold count 4 -> 11 and pooled n 353 hit / 438 pit -> 755 / 890.
# The 2024 fold is trainable and has been since 2026-07-15 (the
# S5_fold_guards_and_2024_tripwire block below still reports tripped=true, hit and
# pit both passing the >=60 train / >=15 test guards).
#
# WHAT IT COSTS, measured before the change:
#   model minus consensus, pooled rho (debuted_km)
#     4-fold  2020-23    hit +0.0361   pit +0.0533   <- the shipped claim
#     11-fold 2014-24    hit +0.0113   pit +0.0108
#   Against a model-vs-consensus MDE95 of ~0.045, pit CLEARED at 4 folds and both
#   become NULLS at 11. The published "eFV beats consensus" therefore stops being
#   RESOLVABLE. It does not become false; it becomes unmeasurable at this power,
#   and the Methodology surface has to say so rather than keep asserting it.
#   The pitcher two-metric win (blend MAE 2.372 < baseline 2.381) also flips.
#
# TWO CONSEQUENCES A READER OF THIS CONSTANT MUST KNOW.
#   1. LABEL MATURITY. Every 2024 debuted row carries observed_seasons=2,
#      censored=true, weight=0.333, and target_censored is exactly 3x the observed
#      two-season bWAR. prospect_path._score computes the headline Spearman and MAE
#      UNWEIGHTED, so those rows enter the published number at FULL weight with two
#      thirds of each label extrapolated. That is a real caveat on every number
#      this constant now produces.
#   2. HISTORICAL LAB NUMBERS STOP REPRODUCING. About thirty lab tools import this
#      constant, so re-running any of them no longer reproduces the figure recorded
#      in the ledger against it. Ledger entries dated before 2026-08-06 are on the
#      4-fold basis and must be read that way.
SCORED_YEARS = (2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024)

#: The pre-promotion basis, kept so a reader can reproduce a ledger number that was
#: recorded against it, and so the two can be compared without archaeology.
SCORED_YEARS_LEGACY_4FOLD = (2020, 2021, 2022, 2023)

# Feature keys + monotone direction (LightGBM; ridge ignores the sign, regularizes only).
# LEAN, theory-motivated sets (Phase-1 verdict + an OOS feature search). The earlier
# kitchen-sink set was DRAGGED DOWN by noisy features (milb_missing/n_sources/pick/etc.):
# adding them made the model rank BELOW consensus. Stripping to the earned signals flips
# it -- this lean model beats consensus FV on out-of-sample rank for BOTH cuts and BOTH
# sides, and the edge holds (grows) on recent 2019-2023 cohorts (see data/xfv_eval.json
# era_split). Power is DELIBERATELY absent for hitters (Phase-1: over-priced by scouts,
# anti-signal for incremental WAR) -- that omission IS eFV's power-overpricing correction.
_FEATURES_HIT = [
    ("fv",             +1),   # consensus_fv_raw -- the dominant, regularized prior
    ("obp_rel",        +1),   # Phase-1: strongest hitter edge BEYOND FV (on-base skill)
    # k_rel declared 0 = NO DIRECTIONAL CLAIM (sign audit 2026-07-25, owner bug
    # "why is Arias punished for contact when he has great contact?"). The theory
    # (-1, more whiffs worse) is true MARGINALLY: weighted corr with realized WAR
    # -0.0884. It is FALSE conditionally: the served ridge fits +0.1874, unregularized
    # OLS +0.2446, and the sign survives every conditioning tried, +0.0996 with
    # peak_k_rel removed, +0.2508 refit on production-bearing rows only, positive in
    # 8 of the 9 informative forward-chained folds. It is a genuine SUPPRESSOR
    # (conditional on FV + tools + the on-base/OPS block, residual contact reads as
    # a slap-hitter tell), not a collinear split: MERGING k_rel with peak_k_rel into
    # one z-mean column still fits POSITIVE (+0.0595, 9/11 folds).
    # Dropping it is a measured NULL: pooled forward-chained rho +0.00715 (0.42x the
    # 0.017 MDE95), paired-bootstrap CI95 [-0.0051, +0.0179], and the row-permuted
    # zero-information control scores +0.00718, identical to the candidate, i.e. no
    # result. So it STAYS; only the declaration was wrong.
    # Ledger: data/xfv_sign_audit.json, data/xfv_sign_merge_gate.json.
    ("k_rel",           0),
    ("peak_k_rel",     -1),   # best-season contact (multi-season peak); helps OOS
    ("age_rel_level",  -1),   # younger-for-level better
    # n_milb_seasons declared 0 (sign audit 2026-07-25). "Track record/persistence"
    # (+1) is true MARGINALLY (+0.0946) and FALSE conditionally: served ridge
    # -0.2324, unregularized OLS -0.5051, -0.2368 with milb_missing removed, -0.3231
    # on production-bearing rows only, negative in 7 of the 9 informative folds. The
    # conditional meaning is inverted by construction, since holding level_rank and
    # age fixed, more MiLB seasons means MORE seasons used to reach the same level.
    # SUPPRESSOR, keep: dropping is a NULL (+0.00426 = 0.25x the 0.017 floor, CI95
    # [-0.0097, +0.0182], zero-information control +0.00386 = the same number).
    # NOTE the display consequence, fixed in patch 4: this weight put a
    # "Track-record depth DOWN" chip on 1,882 of the 1,886 live hitter cards that
    # show it (99.8%), mean magnitude 0.362.
    ("n_milb_seasons",  0),
    ("tool_hit",       +1),   # best single tool for WAR
    ("tool_speed",     +1),   # athletic up-side / defensive value
    # milb_missing: indicator that the production block is IMPUTED (no pre-decision MiLB
    # track record). Re-validated 2026-06-24: ALONE on the lean set it is a clean OOS gain
    # (blend 0.339->0.362, FV-45 tier 0.012->0.093) -- the model needs to tell imputed-zero
    # production from average production, which is exactly the thin-record fringe cohort the
    # old kitchen-sink rejection (milb_missing BUNDLED with n_sources/pick) hid.
    ("milb_missing",    0),   # declared 0 (sign audit 2026-07-25): served fit is
                              # +0.0397 against a declared -1. Marginal -0.0302 agrees
                              # with the old declaration, so this is a suppressor by the
                              # letter, but the weight is at the noise scale and the
                              # feature is INERT in the served fit; dropping it moves
                              # pooled forward-chained rho by -0.00022 (0.013x the 0.017
                              # floor), the smallest effect measured anywhere in the set.
                              # Kept (gate standard section 6: do not remove on sub-floor
                              # evidence); the claim is what goes.
    # Acquisition-cohort indicators -- the ridge re-centers each cohort's intercept, lifting
    # cross-tier ordering in EVERY tier (sweep: stacks with milb_missing to blend 0.367).
    ("is_ifa",          0),
    ("is_college",      0),
    # ops_rel: FV-45 FRINGE-tier on-base+slugging signal the obp_rel/k_rel pair misses.
    # E-LEAN1 flagged a genuine t45 signal (~+0.02) that the pooled-first gate could not
    # ship; WS-M / M5 re-tested it under a pre-registered FRINGE gate (docs/prelaunch-2026-07)
    # and it cleared: t45 +0.0237 (0.120 -> 0.144), with pooled (-0.002) and within-tier
    # (-0.0026) movement at the identity noise floor (~0.0023 = statistically no change).
    # Ledger: data/xfv_ops_rel_fringe_eval.json (resolved-target within-tier dips -0.0052 =
    # the accepted sensitivity cost of a fringe-targeted add). Kept LAST to match the tested
    # key order (ridge predictions are feature-order invariant).
    ("ops_rel",        +1),
    # age: absolute age at the production read (OWNER-DIRECTED ship 2026-07-14,
    # data/xfv_age_feature_eval.json). Missed the pooled auto-ship bar by 0.0003
    # (+0.0043) but improves within-tier (+0.0053) AND t45 (+0.0057) with no
    # metric down -- and the OOS eval pool is debuted-only, structurally blind
    # to the never-debut risk this feature targets (the 27yo-org-arm class the
    # owner flagged). No missing indicator: mean-imputed (22.5) rows stay
    # neutral under standardization; the indicator variant destabilizes
    # pitchers (sparse-column class).
    # age declared 0 for HITTERS (sign audit 2026-08-04). Same latent class as the
    # pitcher `age` (2026-07-25) and pitcher `age_rel_level` (2026-07-30) corrections,
    # one matrix rebuild later, and adjudicated by the SAME four steps. Two of the four
    # land DIFFERENTLY here and are recorded as such rather than assimilated.
    #   what moved   the 07-25 audit measured served -0.0619, negative in 9 of 9
    #                informative folds, marginal -0.0506: the -1 was true and stable.
    #                On the 2026-08-04 hitter matrix (n 1883, the same pool size as the
    #                07-25 n 1882) the served ridge fits +0.0420 and the contradiction
    #                surfaces.
    #   why it moved NOT the C1 decimal-age ship, which is what moved the pitcher side.
    #                Tested directly on the same rows: rounding the age column back to
    #                integers does not restore the declared sign, it goes MORE positive
    #                (+0.0520, +0.0668 with age_rel_level also rounded), and the marginal
    #                stays positive (+0.0205). The FEATURE COLUMN is not what moved. The
    #                marginal correlation of age with realized WAR went -0.0506 -> +0.0165
    #                on the same pool, so this is a LABEL-side change out of the
    #                2026-08-04 rebuild. Isolating which one was outside that lane.
    #   fitted sign  NOT a suppressor, and the suppressor defence the pitcher case had is
    #                not available: marginal weighted Pearson +0.0165 is on the SAME side
    #                as the fit, so efv_sign_audit classifies WRONG_SIGN. But the marginal
    #                is not reliably signed EITHER way - the rank marginal (Spearman) is
    #                -0.0547, on the DECLARED side - and the unregularized OLS partial is
    #                +0.0119, BELOW the audit's own NOISE_W 0.02 floor. The served +0.0420
    #                is 2.1x that floor and the second-smallest weight in the set. Nothing
    #                measured here supports -1 and nothing supports +1.
    #   IS a split   the OTHER divergence from the precedent. r(age, age_rel_level) =
    #                +0.518, and removing the sibling SNAPS THE SIGN BACK to -0.0502 while
    #                the sibling barely notices the removal of age (-0.2159 -> -0.1952).
    #                That is _sweep_signs' COLLINEAR_SPLIT verdict: one age signal split
    #                arbitrarily across two columns. On pitchers the same test came out the
    #                opposite way (dropping age pushed age_rel_level MORE positive, +0.0418
    #                -> +0.0916), which is what earned that case its "independent
    #                conditional effect" reading. The hitter contradiction is therefore
    #                WEAKER evidence for a real positive effect than the pitcher one was.
    #                The block's declared negative direction is intact and simply lives in
    #                age_rel_level (served -0.2159, marginal -0.2146).
    #   stability    6 of 9 informative folds positive but the fold-weight MEAN is NEGATIVE
    #                (-0.0056), range -0.2754 to +0.1231. There is the same drift with
    #                sample size the pitcher case had (the 5 largest folds, train n
    #                845..1641, all positive) but the magnitudes never leave the noise
    #                band. Unstable sign, not a stable positive one.
    #   drop gate    FRESH on this matrix, the pit-age protocol: pooled forward-chained rho
    #                over 11 splits, dropping = +0.00669, i.e. dropping HELPS but at 0.393x
    #                the 0.017 hit MDE95. Paired bootstrap B=2000 (resampling TRAIN and
    #                TEST, refit per draw) CI95 [-0.0042, +0.0108], P(drop helps) 0.82,
    #                helps in 6 of 11 folds and the fold deltas are dominated by 2018
    #                (+0.0601) with the other ten inside +/-0.012. The zero-information
    #                control - the same column ROW-PERMUTED and KEPT in the set - scores
    #                +0.0062, which is 93% of the candidate: destroying the column's
    #                information buys almost exactly what removing it buys, so the "gain"
    #                is not a gain from removing information. Permutation null p 0.150.
    #                Sub-floor NULL, and gate standard section 6 forbids removing on
    #                sub-floor evidence -> KEEP.
    #   merge gate   already adjudicated 2026-07-25 (data/xfv_sign_merge_gate.json,
    #                "hit:age+age_rel_level"): merging the pair into one z-mean column is
    #                itself a null (+0.00033 = 0.02x floor, the smallest effect in that
    #                whole set, CI95 [-0.0256, +0.0121]) -> rejected as a remedy. It would
    #                also move served numbers, which a correctness fix must not.
    #   why 0        not +1: every stability probe refuses "older hitters are better", and
    #                a direction that inverts when the LABEL is redefined is not theory.
    #                0 = NO DIRECTIONAL CLAIM, the same declaration used five times before
    #                for this exact situation.
    # CORRECTNESS only, no accuracy claim and none required: the declaration binds only
    # _fit_lgbm_mono's monotone_constraints (the eval-only LightGBM challenger), never the
    # shipped ridge, so no grade, WAR, surplus or ordering moves.
    # DISPLAY CONSEQUENCE, reported not patched (efv_score.py was outside this lane): with
    # w +0.0420 and train mean 22.10, a hitter YOUNGER than the mean gets a NEGATIVE
    # contribution, so the Age chip reaches ~150 of 2,128 live hitter cards and 134 of them
    # read DOWN on young hitters. Same defect class as the 2026-07-25 Ryan Sloan pitcher
    # bug (1,058 of 2,393 cards, 44.2%), at 7.1% incidence. Whether hitters join pit in
    # efv_score._EXPLAINER_SKIP_SIDE is an owner call; the comment at efv_score.py:536
    # still quotes the retired -0.0619 and needs correcting either way.
    # Ledger: data/xfv_hit_age_sign_gate.json, data/xfv_sign_merge_gate.json.
    ("age",             0),
    # level_rank: highest MiLB level reached at the decision read (DSL 0 .. AAA 5).
    # The 2026-07-15 feature-arms sweep flagged the ops_rel FRINGE signature (t45
    # +0.0200, pooled flat) but refused post-hoc fringe-gating; the keep-alive
    # cleared its PRE-REGISTERED fringe re-gate at the 2024-fold vintage
    # (docs/efv-2026-07-15/GATES.md section LR-FRINGE): t45 +0.0192 (bar +0.015),
    # pooled +0.0003 / within-tier -0.0003 (identity noise floor 0.0011), no era
    # cell down > 0.01; resolved-target sensitivity agrees (t45 +0.0132). Proximity
    # to the majors is exactly the fringe-tier discriminator the rate-relative
    # block misses. Ledger: data/xfv_level_rank_fringe_eval.json. Kept LAST to
    # match the tested key order (ridge predictions are feature-order invariant).
    ("level_rank",     +1),
    # NOTE: game power deliberately excluded -- Phase-1 shows scouts over-price it and it
    # is ~neutral-to-negative for incremental WAR (it predicts ISO, not WAR).
]
_FEATURES_PIT = [
    ("fv",             +1),   # consensus_fv_raw -- the dominant, regularized prior
    ("peak_k_rel",     +1),   # multi-season PEAK K-rate -- the lever that flipped pitchers
    ("k_rel",          +1),   # final-season K-rate (Phase-1 top adder)
    ("bb_rel",         -1),   # walk rate -- completes the K-BB% edge (helps OOS; cmd does NOT)
    # age_rel_level declared 0 for PITCHERS (sign audit 2026-07-30). Same latent class
    # and the same block as the pitcher `age` correction below, one matrix rebuild later.
    #   what moved   the 2026-07-25 audit measured served -0.0076, BELOW the audit's own
    #                NOISE_W 0.02 floor, so the -1 declaration was surviving on a weight
    #                that asserted nothing. On the 2026-07-30 pitcher matrix (n 1988) the
    #                served ridge fits +0.0418 and the contradiction surfaces.
    #   why it moved PRE-REGISTERED, not a surprise. C1 decimal ages (2026-07-29) un-flattened
    #                the 752 of 4,260 rows that integer-meets-integer had pinned at
    #                age_rel_level exactly 0.0; that ship's own warning reads "several of the
    #                largest upward moves are PITCHERS WHO GOT OLDER, because decimalization
    #                gives the inverted pitcher `age` coefficient finer resolution ... do not
    #                rebuild the pitcher matrix expecting neutrality." This is that rebuild.
    #   fitted sign  marginal (weighted Pearson) -0.069, so "younger for level is better" is
    #                true UNCONDITIONALLY and false conditional on FV + K/BB + tool_fb -> a
    #                SUPPRESSOR by efv_sign_audit's classification, i.e. the DECLARATION is
    #                what is wrong. Unregularized OLS partial is also positive, +0.0657.
    #   not a split  removing the collinear partner `age` does NOT snap the sign back: it goes
    #                MORE positive, +0.0916 (+0.0272 on the 07-25 matrix). So this is an
    #                independent conditional effect, not a collinear split of one age signal.
    #   what it is   the cleanest read on WHAT conditions it: the SAME column on the SAME side
    #                of the SAME matrix fits -0.5943 in the efv_ungraded provisional pit set,
    #                which carries no `fv` anchor, and +0.0418 here, which does. Age-for-level
    #                is a real negative until the consensus grade is in the model; after that
    #                the residual is a scout-already-knew term, not a youth bonus.
    #   stability    7 of 9 informative folds now positive and only 2 of 9 agree with -1 (was
    #                3 of 9 positive, 6 of 9 agreeing). fold w mean +0.042, min -0.445,
    #                max +0.359. Never a stable negative; now not even a fold majority.
    #   drop gate    2026-07-30, the pit-`age` protocol: pooled forward-chained rho over 11
    #                splits, dropping = -0.00249, i.e. dropping HURTS and is 0.156x the 0.016
    #                pit MDE95. Paired bootstrap B=2000 (resampling TRAIN and TEST, refit per
    #                draw) CI95 [-0.0121, +0.0136], P(drop helps) 0.47, helps in 4 of 11 folds.
    #                Zero-information control -0.00302, permutation null p 0.439. NULL, and
    #                gate standard section 6 forbids removing on sub-floor evidence -> KEEP.
    #   merge gate   already adjudicated 2026-07-25 (data/xfv_sign_merge_gate.json,
    #                "pit:age+age_rel_level"): merging the pair into one z-mean column fits
    #                +0.0471, so it does NOT restore the declared direction, and the merge is
    #                itself a null (-0.00588 = 0.368x floor, CI95 [-0.0231, +0.0167])
    #                -> rejected as a remedy.
    #   consistency  `age`, the other member of this same pitcher age block, was corrected to 0
    #                on 2026-07-25/29 for exactly this reason. Declaring "younger for level is
    #                better" while declining to declare "younger is better", on the same side
    #                out of the same block, is not a position this module can hold.
    # CORRECTNESS only, no accuracy claim and none required: the declaration binds only
    # _fit_lgbm_mono's monotone_constraints (the eval-only challenger), never the shipped
    # ridge, so no served number moves. The HITTER-side ("age_rel_level", -1) above is
    # untouched and correct (served -0.1361, marginal -0.2154).
    # Ledger: data/xfv_sign_audit.json (predates the decimal-age rebuild; the fresh figures
    # above are quoted inline), data/xfv_sign_merge_gate.json.
    ("age_rel_level",   0),
    ("x_era_k",        +1),   # (-era_rel)*k_rel: run-prevention x missing-bats interaction.
                              # Feature re-test 2026-06-22: genuine OOS lift (debuted-km
                              # 0.274->0.282, blend +0.0074, sane cal); era_rel alone fails.
    ("tool_fb",        +1),   # fastball -- best pitcher tool adder
    # age: OWNER-DIRECTED ship 2026-07-14 (see the hitter-side note +
    # data/xfv_age_feature_eval.json): pit age-only pooled +0.0019 (sub-bar)
    # but wm +0.0114 / t45 +0.0117, no metric down; the debuted-only eval
    # cannot see the never-debut org-arm risk this targets.
    # age declared 0 for PITCHERS (sign audit 2026-07-25, owner bug "Ryan Sloan, 20 in
    # Double-A, is PENALIZED for age"). Adjudicated under the full EFV_GATE_STANDARD:
    #   fitted sign   served ridge +0.0589 against a declared -1. Marginal -0.0543, so
    #                 the theory is true unconditionally and false conditional on FV +
    #                 K/BB + tool_fb (the consensus anchor already prices young arms).
    #   stability     NOT a stable wrong sign and NOT chatter, a monotone DRIFT with
    #                 sample size: fold weights -0.060 / -0.059 / -0.759 / -0.452 /
    #                 -0.182 / -0.082 / -0.061 / +0.047 / +0.050 across train<2016..2024
    #                 (the 2014/2015 folds are degenerate, pre-StatsAPI rows make every
    #                 production column constant, and are excluded rather than counted
    #                 as disagreement). The two LARGEST folds (n=1473, n=1730) and the
    #                 full pool all fit it non-negative. "Negative in 9 of 11 folds" is
    #                 a small-and-old-data artifact.
    #   drop gate     pooled forward-chained rho over 11 splits: +0.00377 for dropping =
    #                 0.236x the 0.016 pit MDE95. Paired bootstrap (B=2000, resampling
    #                 TRAIN and TEST with a refit per draw) CI95 [-0.0089, +0.0175],
    #                 P(drop helps) 0.68. Zero-information control (the same column
    #                 row-permuted, kept in the set) +0.00252, so two thirds of the
    #                 "gain" is reproduced by destroying the column's information
    #                 without removing it. Permutation null p 0.382. Dropping is a NULL,
    #                 helps in only 4 of 11 folds, and gate standard section 6 forbids
    #                 removing on sub-floor evidence -> KEEP.
    #   merge gate    merging age with age_rel_level into one z-mean column does NOT
    #                 restore the declared direction (merged weight +0.0471, positive in
    #                 3 of 11 folds) and is itself a null (-0.00588 = 0.37x floor,
    #                 CI95 [-0.0231, +0.0167]) -> rejected as a remedy.
    # This is a CORRECTNESS fix, not an accuracy claim: no rank gain is claimed and none
    # is required.
    # SUPERSEDED 2026-08-04: the sentence that used to sit here said the hitter-side
    # ("age", -1) was "untouched and correct (served -0.0619, negative in all 9
    # informative folds)". Both halves expired on the 2026-08-04 matrix rebuild - the
    # hitter column now serves +0.0420 and its fold mean is negative only on average
    # (6 of 9 folds positive), so the hitter declaration moved to 0 as well. See
    # docs/efv-2026-08-04/HIT_AGE_SIGN_GATE.md.
    # Ledger: data/xfv_sign_audit.json, data/xfv_sign_merge_gate.json.
    ("age",             0),
    # NOTE: pitcher cohort interactions (ifa_x_era / col_x_k / fb_x_k) were tested + REVERTED
    # 2026-06-24. They lifted OOS rank only marginally (blend 0.269->0.285, "marginally above
    # noise" per the sweep) AND col_x_k = is_college*k_rel is a SPARSE column (nonzero only for
    # college arms), so standardizing it against a mostly-zero distribution handed thin-sample
    # college draftees extreme boosts at LIVE time (Caden Hunter +6; Moore/Root/Quick jumping to
    # 50 on col_x_k alone). Bare indicators don't help pitchers (0.267 < 0.269). A ranking gain
    # that wrecks absolute-grade robustness is not a clean gain -> reverted. (Hitter cohort
    # indicators stay -- bounded 0/1, robust +0.030 gain.)
    #
    # seasons_at_level: consecutive seasons on the CURRENT level (1 = arrived this year).
    # SHIPPED PITCHERS ONLY, 2026-07-30, owner decision on the E1 gate
    # (docs/efv-2026-07-30/E1_REPEAT_LEVEL_GATE.md, ledger data/xfv_repeat_level_eval.json).
    #   what it adds  nothing else in the set sees a STALL. Only the final pre-decision
    #                 season's rates enter, so an arm repeating a level after a bad year read
    #                 identically to one who just arrived and is pitching well. It is NOT
    #                 n_milb_seasons, which counts total seasons anywhere and is a declared
    #                 suppressor for the opposite reason (more seasons = more seasons spent
    #                 REACHING the level). Cleanest demonstration: taylor and arias share
    #                 n_milb_seasons 4.0 and differ 3.0 vs 1.0 here.
    #   evidence      pooled OOS blend Spearman 0.3060 -> 0.3187 (+0.0127), 3 of 4
    #                 forward-chained folds, BOTH full-pool AUC labels up (contributor
    #                 +0.0041, star +0.0059).
    #   why it ships  inside the generic MDE95 (0.79x) but PASSES the feature-specific
    #                 permutation null: 0 of 30 draws from the true marginal with the row
    #                 link broken matched or beat it, null sd 0.0030, p=0.032, ~4.2 sd out.
    #                 That is the bar this codebase set for itself after the pitcher-label
    #                 lane (null band + permutation p, docs/PITCHER_LABEL_LEDGER.md). The two
    #                 tests answer different questions and do not conflict: permutation says
    #                 the signal is real, MDE95 says the magnitude is imprecise.
    #   sign          -1 CONFIRMED for pitchers, fitted -0.1072 and the 4th largest weight in
    #                 the model. HITTERS ARE EXCLUDED ON PURPOSE: the same column fits +0.0945
    #                 there (a hitter who has sat at a level is one the system KEPT on the
    #                 board) and its permutation p is 0.375, so that arm is closed on an
    #                 inverted sign AND on noise. Do not "restore symmetry" by adding it to
    #                 _FEATURES_HIT.
    ("seasons_at_level", -1),
]


# PACE FROM ENTRY (2026-07-31, owner ask: franklin_arias / josue_de_paula).
# PRE-REGISTERED, DEFAULT OFF, NOT YET GATED. The columns are emitted
# unconditionally by efv_dataset._pace_from_entry (entry_level_rank,
# pace_from_entry, entry_observed) because _fit_lgbm_mono indexes feats[k] with
# no default; flipping this flag is what puts them in the ridge.
#
# THE DEFECT IT TARGETS, measured: n_milb_seasons counts seasons with no idea
# where the player ENTERED, and _LEVEL_RANK puts DSL at 0, so a DSL starter
# mechanically carries more counted seasons than a college draftee at the same
# rung. The only entry-pathway machinery in the model today is the is_ifa dummy,
# which fits -0.0010 (inert). Arias reads 1.33 rungs/season from a DSL entry and
# de_paula 1.00, against a stalled AA repeater's 0.00.
#
# EXPECTED FAILURE MODE, PRE-REGISTERED so it is not read as a finding: this
# feature family has inverted on the hitter side THREE times (n_milb_seasons
# marginal +0.095 vs conditional -0.23; seasons_at_level +0.0945 at permutation
# p=0.375; pit age_rel_level +0.0418 against a declared -1). The training pool is
# survivorship-censored to debuted players, so "moved slowly but is still on the
# board" selects for players the system KEPT. If the hitter arm fits a NEGATIVE
# weight on pace (fast movers score worse), that is the censoring artifact and
# the arm closes - it must NOT ship as "DSL starters are worse".
#
# Gate when run: forward-chained pooled Spearman vs MDE95 floors 0.017 hit /
# 0.016 pit, a row-permuted zero-information control kept IN the feature set, the
# feature-specific permutation null (30 draws, the bar seasons_at_level cleared at
# p=0.032), and a paired bootstrap B=2000. Also worth its own arm: the same
# column fits -0.5943 in the fv-anchor-free efv_ungraded set against ~0 in the
# anchored flagship, so if the flagship arm nulls, efv_ungraded is where the
# signal is not already priced by scouts.
#
# RESULT 2026-08-04 (data/xfv_pace_entry_eval.json): GATE RUN, NO-SHIP, ARM
# CLOSED. The pre-registered failure above FIRED and was not relaxed: the hitter
# arm fits a NEGATIVE pace weight (-0.0419, negative in 3 of 4 folds), i.e. the
# censoring artifact. Permutation p 0.71 hit / 0.94 pit; the fuller triple
# variant is a RESOLVED HARM (CI95 excludes zero), so it must not return as the
# richer spec. Coverage was not the limiter (~80% of eval rows non-censored).
# CORRECTION to the second-arm motivation two paragraphs up: the -0.5943 figure
# DOES NOT REPRODUCE. pace_from_entry fits POSITIVE in all four plausible
# efv_ungraded specs on both sides (+0.0993..+0.3440 hit, +0.0751..+0.2708 pit;
# one -0.0559 outlier); the nearest thing to -0.5943 is entry_observed, a
# different column, and -0.5943 is also age_rel_level's efv_ungraded PITCHER
# weight quoted ~130 lines above, so this reads as a column mix-up. The arm was
# run anyway on its own OOS numbers and lost. Do NOT re-open on that premise.
# Keep this flag False; the columns stay emitted and inert.
# Doc: docs/efv-2026-07-31/PACE_FROM_ENTRY_GATE.md
PACE_FROM_ENTRY = False


# Guarded-blend weight for the shipped HEADLINE rank: rank = (1-lambda)*consensus_OLS
# + lambda*model. lambda is now WAG-CALIBRATED (see _wag_calibrated_lambda): it is the
# trust factor that realized WAR-Above-Grade actually supports for eFV's adjustment,
# forward-chained. Hitters land ~0.8 (the adjustment is well-supported); pitchers shrink
# harder (consensus is the stronger pitcher signal, and WAG confirms a smaller edge). The
# fallback below is used only if the WAG join is unavailable. Clamped so the validated rank
# win is never surrendered and the magnitude is never overstated.
_BLEND_LAMBDA_FALLBACK = {"hit": 0.85, "pit": 0.80}
_BLEND_LAMBDA_CLAMP = (0.35, 0.90)
_WAG_LAMBDA_CACHE: dict[str, float] = {}

# A1 lambda re-select ship (see blend_lambda): hit accuracy-max blend weight 0.85 (was the
# 0.70 rank_calibration band ceiling). BOTH sides are now pinned; None would mean "no
# override, take whatever rank_calibration selects on this matrix rebuild".
#
# CHURN TRADE (2026-07-24, docs/EFV_FRONTIER_AUDIT.md): hit 0.85 -> 0.70. This is NOT an
# accuracy claim in either direction. The A1 ship that raised it to 0.85 was measured at
# +0.0048 pooled rho against a re-measured minimum detectable effect of 0.0076 for a
# lambda shift (0.63x of its own floor), i.e. it was never resolvable; the re-measured cost
# of going back to 0.70 is -0.00049 (CI95 [-0.0045,+0.0070]), equally unresolvable. What IS
# measurable is stability: the lower weight cuts run-to-run movement of the displayed eFV
# grade by 6.0%, because the consensus leg is far more stable across refits than the model
# leg. Non-inferiority + product trade, taken deliberately. Revert = set this back to 0.85.
#
# PITCHER CHURN PIN (2026-08-04, docs/EXECUTION_2026-08-04-eight-asks.md): pit None -> 0.57,
# the value the served board was already built on. Same shape of trade as the hit pin above
# and, like it, explicitly NOT an accuracy claim in either direction - nothing here says 0.57
# ranks better than any other value in the band.
#
# What was measured (2026-08-03): pooled blend Spearman across the ENTIRE rank-gate band
# [0.50, 0.70] spans only 0.0025 on pitchers, which is 0.16x the 0.016 pitcher MDE95 (hitters
# 0.0035, 0.21x their MDE95). The band is flat inside its own noise floor, so no lambda in it
# is distinguishable from any other on the criterion that matters. Worse, almost all of the
# movement the argmax actually resolves lives in the t45 term - a Spearman on 60 FV-45 pitcher
# rows - so the selector is maximizing a 60-row rank correlation, i.e. an argmax over noise.
#
# What IS measurable is churn: re-selecting on every matrix rebuild produced three different
# served pitcher lambdas in three weeks (0.54, 0.57, 0.59), each true only at its own matrix
# vintage, and each one re-blends and re-prints every pitcher grade on the board for no
# resolvable accuracy reason. It also cost review time three times over, since the quoted
# number kept disagreeing with the artifact. Pinning removes that movement entirely.
#
# Stability/correctness change, not an accuracy change. Revert = set this back to None (the
# dynamic rank_calibration reselect). If a future rebuild claims a better lambda, it has to
# clear MDE95 on pooled rho first, not win the composite argmax.
_BLEND_LAMBDA_RESELECT: dict[str, float | None] = {"hit": 0.70, "pit": 0.57}

# WAG sizes the blend ONLY when its predicted-edge -> realized-WAG regression is meaningful.
# When that regression is non-significant (|spearman| below this / too few rows), its slope is
# noise and would shrink the blend to a rank-SUBOPTIMAL weight. Pitchers already land here (WAG
# spearman ~0.02, slope 0.39) -- the shipped pit eval shows the 0.391 blend (rho 0.2625)
# trailing the pure ridge (rho 0.281); the blend was pulling the better prediction back toward
# the weaker consensus. There we size lambda by the rank gate directly (rank_calibration).
# Threshold raised 0.05 -> 0.10 (2026-07-06): the 2026 norm-fix collapsed the HITTER WAG signal
# (spearman 0.20 -> 0.066, bootstrap CI straddles 0), so at 0.05 it was still (barely) clearing
# the gate and pinning a rank-suboptimal lambda ~0.53; a non-significant WAG at n~400 needs
# ~0.10 to be real, so hitters now defer to the rank gate too (lambda ~0.70), which lifts the
# pooled OOS rank rho 0.343 -> 0.353 (within-tier + FV45 also up).
_WAG_MIN_SPEARMAN = 0.10
_WAG_MIN_N = 100

# Realized-outcome bars for the M1 AUC instrumentation (source_backtest.CONTRIBUTOR_WAR /
# STAR_WAR): a first-6yr summed-bWAR contributor clears 3, a star clears 10.
_CONTRIB_WAR = 3.0
_STAR_WAR = 10.0


def _feature_spec(side: str):
    feats = _FEATURES_PIT if side == "pit" else _FEATURES_HIT
    return [k for k, _ in feats], [m for _, m in feats]


def _load_wag() -> dict:
    """player_key -> stored WAG block (regressed_wag = exposure/injury-corrected,
    reliability-shrunk talent over/underperformance vs consensus FV; w_obs = its weight).
    The realized 'beat your grade' truth eFV's adjustment is calibrated against."""
    try:
        deb = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for r in deb:
        w = (r.get("debuted_value") or {}).get("wag")
        if w and r.get("player_key") and w.get("regressed_wag") is not None:
            out[r["player_key"]] = w
    return out


def wag_calibration(side: str) -> dict:
    """Forward-chained calibration of eFV's adjustment against realized WAG. Regresses
    each debuted player's realized regressed_wag (per-season talent over/underperformance)
    on eFV's PREDICTED per-season rate adjustment (model - consensus, /6), weighted by WAG
    reliability (w_obs), through the origin. The slope is how much realized over/under-
    performance you actually get per unit of predicted edge -> the trust factor for the
    blend. Returns {lambda, slope_wobs, slope_unweighted, spearman, n}. Leakage-free."""
    from efv_dataset import matrix_path
    keys, _m = _feature_spec(side)
    wag = _load_wag()
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    x, y, w = [], [], []
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        # AUDIT FIX 2026-07-14 (guard order): check ols/ridge BEFORE calling
        # _predict on them - _fit_ridge returns None under 40 rows, which
        # would TypeError here (latent: today's fold gate makes it unreachable).
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            wg = wag.get(r["player_key"])
            if not wg:
                continue
            cons_war = max(0.0, _pred_ols(ols, r["fv"]))
            model_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            x.append((model_war - cons_war) / 6.0)       # predicted per-season rate edge
            y.append(float(wg["regressed_wag"]))         # realized per-season WAG
            w.append(float(wg.get("w_obs") or 0.0))
    def _slope(wt):
        num = sum(wt[i] * x[i] * y[i] for i in range(len(x)))
        den = sum(wt[i] * x[i] * x[i] for i in range(len(x)))
        return (num / den) if den else None
    sw = _slope(w)
    su = _slope([1.0] * len(x))
    lo, hi = _BLEND_LAMBDA_CLAMP
    lam = min(hi, max(lo, sw)) if sw is not None else _BLEND_LAMBDA_FALLBACK[side]
    return {"lambda": round(lam, 3), "slope_wobs": round(sw, 3) if sw is not None else None,
            "slope_unweighted": round(su, 3) if su is not None else None,
            "spearman": _spearman(x, y) if len(x) >= 8 else None, "n": len(x)}


def _lam_key(lam: float) -> str:
    """Stable dict key for a lambda in the composite_at map (3dp, matches the candidate grid)."""
    return f"{float(lam):.3f}"


def rank_calibration(side: str, also_at: tuple[float, ...] = ()) -> dict:
    """RANK-gate blend lambda -- the fallback used when WAG cannot calibrate (its predicted-
    edge -> realized-WAG regression is non-significant). Sizes lambda directly on the forward-
    chained OOS ranking, over the same debuted-cohort folds the eval uses (identical setup to
    the 'blend' row in data/xfv_eval*.json).

    Pitchers land here: WAG spearman ~0.02 pins lambda at 0.391, and the shipped pit eval shows
    that 0.391 blend (rho 0.2625) trailing the pure ridge (0.281) -- the blend was dragging the
    better prediction back toward the weaker consensus. A leakage-free forward-chained selector
    (tools/xfv_ml_lab.lambda_fwdchain) confirms higher-than-0.391 ranks better in every cohort
    with prior data (+0.017 pooled). BUT an adversarial bootstrap showed pooled rho is FLAT
    across 0.80-1.0 and the move's CI only stays strictly positive near ~0.65, while the value-
    bearing within-tier + FV-45-fringe signals PEAK at ~0.65 and DEGRADE toward 0.90. So lambda
    maximizes pooled + within-tier + fringe TOGETHER within a conservative [0.50, 0.70] band --
    the robust middle, not the noisy high-lambda plateau. (Leakage note: lambda is one smooth
    parameter; selecting it on the pooled OOS folds is in-sample for that single scalar, but the
    per-cohort forward-chain independently validates the direction.)

    AUDIT NOTE 2026-07-14: this selector's per-fold consensus-OLS anchor is fit on
    DEBUTED-only rows, while production (_fit_production) fits its anchor on the full
    pool minus recent busts - the flatter full-pool slope makes the EFFECTIVE live
    weight ~0.03 higher than the number quoted here (rank order within a scoring run
    is unaffected; documented rather than re-plumbed).

    ADJUDICATED 2026-07-15 (data/xfv_lambda_adjudication_eval.json): the parity
    re-plumb was tested as a selection PROTOCOL in a nested forward-chained
    tournament and LOST out-of-sample (hit composite -0.1025 with CI95 entirely
    negative + contributor-AUC below floor; pit -0.0024, tie). The earlier
    C-vs-D band-end disagreement was a lab leakage artifact (a vacuous
    decision_year filter fit the parity stack on each fold's own test rows;
    leak-fixed D == C exactly), not implementation sensitivity. This
    debuted-only selector is the ADJUDICATED WINNER; no owner decision pending.
    The returned dict carries the full candidate curve + near_boundary flag so
    any future restamp proposal checks flatness first.

    also_at (2026-08-04): extra lambdas at which to ALSO report the decisive
    components, returned under 'composite_at' keyed by _lam_key. This exists
    because what this selector picks is NOT always what ships -- both sides now
    carry a _BLEND_LAMBDA_RESELECT pin -- and the eval artifact must be able to
    quote the composite at the lambda that actually served. Reporting only; it
    does not touch selection, and any lambda is accepted, inside the band or not.

    LIVE NOTE 2026-08-04: no production caller reaches this selector for its
    lambda any more (both sides are pinned). It still runs in run() so the
    rank-gate evidence stays in the artifact and the pins stay auditable."""
    from efv_dataset import matrix_path
    keys, _m = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    folds = []   # (cons_war, model_pred, target, fv)
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            folds.append((cons, _predict(ridge, r["feats"]), r["target"], r["fv"]))
    if len(folds) < 30:
        return {"lambda": _BLEND_LAMBDA_FALLBACK[side], "criterion": None, "n": len(folds)}

    def _metrics(lam):
        scored = [((1 - lam) * c + lam * m, t, fv) for c, m, t, fv in folds]
        rho = _spearman([s for s, _, _ in scored], [t for _, t, _ in scored]) or 0.0
        byt: dict = {}
        for s, t, fv in scored:
            byt.setdefault(round(fv / 5) * 5, []).append((s, t))
        wsum = wn = 0.0
        t45 = 0.0
        for tk, grp in byt.items():
            if len(grp) < 15:
                continue
            r = _spearman([a for a, _ in grp], [b for _, b in grp])
            if r is None:
                continue
            wsum += r * len(grp)
            wn += len(grp)
            if tk == 45:
                t45 = r
        return rho, (wsum / wn if wn else 0.0), t45

    # E-LAMBDA history (2026-07-14, tools/efv_lambda_band_lab.py ->
    # data/xfv_lambda_band_eval.json): a same-day cap-raise of the HIT ceiling
    # to 0.90 was shipped on a monotone-to-pure-model curve (composite +0.0253,
    # bootstrap P=0.866)... and RETRACTED hours later when the label-integrity
    # repair (41 veteran re-appearances mislabeled as debuts + the career_war
    # sliding-window decay) rebuilt the matrices: on corrected labels the swept
    # optimum is INTERIOR (~0.89) with gain +0.0082 and bootstrap P=0.677 -
    # below every gate. The corrupted labels had been making consensus look
    # worse than it is. The conservative [0.50, 0.70] band STANDS for both
    # sides; the retraction is recorded in the ledger + registry.
    lo, hi = 0.50, 0.70
    cand = [round(lo + (hi - lo) * i / 20, 3) for i in range(21)]
    metr = {lam: _metrics(lam) for lam in cand}
    best = max(cand, key=lambda L: sum(metr[L]))   # pooled + within-tier + FV-45 fringe
    rho, wm, t45 = metr[best]
    # Flatness surface for the restamp protocol: a near-boundary argmax or a
    # composite curve flat within noise across the band means the selection is
    # weak evidence and a restamp needs the owner's sign-off, not just a rerun.
    curve = {str(L): round(sum(metr[L]), 4) for L in cand}
    spread = max(curve.values()) - min(curve.values())
    out = {"lambda": best, "rho": round(rho, 4), "within_tier_wm": round(wm, 4),
           "t45": round(t45, 4), "n": len(folds), "band": [lo, hi],
           "curve": curve, "curve_spread": round(spread, 4),
           "near_boundary": bool(best <= lo + 0.02 or best >= hi - 0.02)}
    if also_at:
        # Components at caller-supplied lambdas (the SHIPPED one, typically). Cheap:
        # _metrics only re-scores the already-fitted folds, no refits.
        at = {}
        for L in also_at:
            r_, w_, t_ = _metrics(float(L))
            at[_lam_key(L)] = {"lambda": round(float(L), 4), "pooled_rho": round(r_, 4),
                               "within_tier_wm": round(w_, 4), "t45": round(t_, 4),
                               "composite_sum": round(r_ + w_ + t_, 4)}
        out["composite_at"] = at
    return out


def blend_lambda(side: str) -> float:
    """Blend weight on the eFV model vs the consensus anchor (cached). Calibrated by WAG only
    when its predicted-edge -> realized-WAG regression is SIGNIFICANT (|spearman| >=
    _WAG_MIN_SPEARMAN); otherwise the slope is noise and pins a rank-suboptimal weight, so we
    size lambda by the rank gate directly (rank_calibration). As of the 2026 norm-fix BOTH sides
    are non-significant on WAG (pitchers spearman ~0.001, hitters ~0.066, both CIs straddle 0),
    so both would defer to the rank gate. Falls back to the hand-set value on any error.

    LIVE PATH (2026-08-04): neither branch below actually runs any more. Both sides carry a
    _BLEND_LAMBDA_RESELECT pin (hit 0.70, pit 0.57), so this returns the pin. The WAG and
    rank-gate branches are kept live for the un-pinned case and because both calibrations are
    still emitted into the eval artifact as evidence."""
    if side not in _WAG_LAMBDA_CACHE:
        # A1 LAMBDA RE-SELECT (2026-07-24b; data/xfv_lambda_reselect_eval.json). Re-opened on
        # the wave-B REPAIRED matrices (the 2026-07-14 band raise was retracted on CORRUPTED
        # labels). Forward-chained sweep [0.50,1.00]: hit pooled OOS Spearman + contributor AUC
        # + star AUC + within-tier ALL rise monotonically past the old [0.50,0.70]
        # rank_calibration band -> that band was a BOARD-MOVEMENT cap, not accuracy-load-bearing.
        # The significance-bar-clearing accuracy-max (player-clustered bootstrap seed 20260724 /
        # 2000 reps: one-sided-95 lower bound > 0 on BOTH pooled rho AND contributor AUC) is 0.85
        # (d_rho +0.0048 lo +0.0001 P0.952; d_cAUC +0.0031 lo +0.0003; leakage-free nested
        # forward-chain agrees). Pit was left dynamic (~0.61) at the time: its pooled curve is a
        # flat noise plateau AND every higher lambda LOWERS contributor/star AUC, so there was no
        # accuracy-justified move (the owner rule is ship only if OOS does not drop). SUPERSEDED
        # 2026-08-04: pit is now PINNED at 0.57 for run-to-run stability, not for accuracy - see
        # the pitcher churn-pin block on _BLEND_LAMBDA_RESELECT.
        ov = _BLEND_LAMBDA_RESELECT.get(side)
        if ov is not None:
            _WAG_LAMBDA_CACHE[side] = ov
            return _WAG_LAMBDA_CACHE[side]
        try:
            wc = wag_calibration(side)
            rho = wc.get("spearman")
            if rho is not None and abs(rho) >= _WAG_MIN_SPEARMAN and (wc.get("n") or 0) >= _WAG_MIN_N:
                _WAG_LAMBDA_CACHE[side] = wc["lambda"]
            else:
                _WAG_LAMBDA_CACHE[side] = rank_calibration(side)["lambda"]
        except Exception:
            _WAG_LAMBDA_CACHE[side] = _BLEND_LAMBDA_FALLBACK[side]
    return _WAG_LAMBDA_CACHE[side]


def oos_grades(side: str) -> dict:
    """{player_key: OUT-OF-SAMPLE eFV ranking score} over the full labeled pool
    (debuted + busts), forward-chained: each cohort year is scored by a model fit ONLY
    on earlier cohorts. The score is the guarded-blend rank_war (monotone in the grade),
    suitable for an apples-to-apples head-to-head against the sources on realized outcomes
    WITHOUT the in-sample advantage a fitted model would otherwise enjoy. Leakage-free."""
    from efv_dataset import matrix_path
    keys, _m = _feature_spec(side)
    lam = blend_lambda(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(full, "target_censored", side)
    out = {}
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        # AUDIT FIX 2026-07-14 (guard order): check ols/ridge BEFORE calling
        # _predict on them - _fit_ridge returns None under 40 rows, which
        # would TypeError here (latent: today's fold gate makes it unreachable).
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            cons_war = max(0.0, _pred_ols(ols, r["fv"]))
            model_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            out[r["player_key"]] = (1 - lam) * cons_war + lam * model_war
    return out


_KEYS, _MONO = _feature_spec("hit")   # hitter defaults (back-compat for imports)


# ---------------------------------------------------------------------------
# feature vectorization (impute + missingness indicators)
# ---------------------------------------------------------------------------

def _decision_year(r) -> int:
    if r["kind"] == "debuted":
        return int(r["debut_year"])
    c = r.get("cutoff") or ""
    return (int(c[:4]) + 1) if c[:4].isdigit() else 2026


_MID_POS = ("C", "SS", "2B", "CF")

# ── pos_prem on the OBSERVED position: BUILT, MEASURED, DEFAULT OFF (2026-07-30) ──
# The owner asked for this feature to read what the player HAS PLAYED rather than what
# FanGraphs projects, and the argument is good on its face: the feature is asking "was
# he good enough to stay up the middle", which is an observation, not a forecast.
#
# It does not ship on, and the reason is a coverage split, not a preference:
#
#   data/positions_played.json is built by fielding_positions.build_positions_played,
#   whose __main__ filters to players with NO debut_date. It is a PRE-DEBUT census.
#   Measured against the eFV hitter training matrix (1,927 rows):
#
#       covered by the observation ....  613 / 1,927   31.8%
#         of the BUST rows ...........  570 / 1,082   52.7%
#         of the DEBUTED rows ........   43 /   845    5.1%
#       covered on the LIVE scoring pool  1,956 / 2,104  93.0%
#
#   So a fallback-to-projection flip would define the feature ONE way on 93% of the
#   rows the model SCORES and the OTHER way on 68% of the rows it TRAINS on - and the
#   train-side split is almost perfectly aligned with the LABEL (95% of debuted rows
#   fall back, 47% of busts do). A feature whose DEFINITION correlates with the target
#   is the shape of a leak, and the ridge would happily learn it. That is a worse
#   defect than the one the flip fixes.
#
# What it would do if turned on today, measured on the current tree:
#   * training pool: 116 of the 613 covered rows change value (69 gain the premium,
#     47 lose it)
#   * live pool: 327 of 1,956 covered rows change (232 gain, 95 lose - the same
#     down-spectrum skew the projection carries, 2.4:1 here)
#   * 10 rows inside the served TOP 100 change the feature (caleb_bonemer rank 22,
#     kevin_alvarez 26, jojo_parker 30, edward_florentino 34, charles_davalan 35,
#     josue_briceno 65, josh_adamczewski 67, francisco_renteria 70, elian_pena 81,
#     emmanuel_rodriguez 87) and 29 inside the top 300
#
# Ten top-100 rows is more than a handful, so per the owner's own rule this lands
# behind a flag with a registry row rather than silently. UNBLOCKING IT is a data job,
# not a modelling one: rebuild positions_played.json WITHOUT the pre-debut filter so
# the training pool is covered, then re-run the eFV accuracy gate
# (docs/EFV_GATE_STANDARD.md) on the refit. Until then this is unmeasurable, not
# merely unmeasured.
POS_PREMIUM_USES_OBSERVED = False

_OBSERVED_POS_CACHE: dict | None = None


def _observed_pos_map() -> dict:
    """{player_key: observed position}, loaded once. Empty on any failure - a missing
    sidecar must degrade to the projection, never raise inside feature extraction."""
    global _OBSERVED_POS_CACHE
    if _OBSERVED_POS_CACHE is None:
        try:
            from pathlib import Path as _P
            import fielding_positions as _fp
            _OBSERVED_POS_CACHE = _fp.load_observed_positions(
                _P(__file__).parent / "data" / "positions_played.json")
        except Exception:
            _OBSERVED_POS_CACHE = {}
    return _OBSERVED_POS_CACHE


def _pos_premium(pos, side: str) -> float:
    """Up-the-middle defensive premium (hitters: C/SS/2B/CF); starters over relievers
    (pitchers). A coarse positional-value tilt -- the search decides if it earns weight."""
    if not pos:
        return 0.0
    p = str(pos).upper()
    if side == "pit":
        return 0.0 if "RP" in p or p == "RP" else 1.0
    return 1.0 if any(x in p for x in _MID_POS) else 0.0


def _pos_premium_for_row(r, side: str) -> float:
    """_pos_premium with the row in hand, so the observed position can be used when
    POS_PREMIUM_USES_OBSERVED is on. Falls back to the row's listed position wherever
    there is no observation. Identical to _pos_premium(r['position'], side) with the
    flag off - see the block above for why it is off."""
    pos = r.get("position")
    if POS_PREMIUM_USES_OBSERVED and side != "pit":
        pos = _observed_pos_map().get(r.get("player_key")) or pos
    return _pos_premium(pos, side)


def _x_era_k(era_rel: float, k_rel: float) -> float:
    """Run-prevention x missing-bats interaction: (-era_rel)*k_rel.

    QUADRANT FIX (audited, then OWNER-DIRECTED ship 2026-07-14): the raw
    product is POSITIVE in the double-bad quadrant (era worse than level AND
    K-rate below level, neg*neg) - 730 live pitchers carried a spurious
    'K-backed run prevention' boost up to +0.48. The quadrant is ZEROED (not
    flipped: the flip's large negatives reshape the fit for a worse measured
    cost). Honesty note: on the DEBUTED-ONLY OOS protocol this measures as a
    small fringe-tier loss (t45 ~-0.02) because that pool credits the
    spurious boost via survivorship - its never-debut victims are outside
    the sample frame. The owner chose correctness over the survivorship-
    biased metric; the double-bad signal still reaches the model through
    era_rel / k_rel / bb_rel directly."""
    x = (-era_rel) * k_rel
    if era_rel > 0 and k_rel < 0:
        return 0.0
    return x


# Tool-grade imputation constants (AUDIT FIX 2026-07-14): the old flat 45.0
# imputed far below the OBSERVED train means (tool_fb mean is 58.0!), and tools
# are missing for 56-65% of LIVE rows vs only 11-14% of training rows - so the
# majority of the live pitcher pool ate a ~-1.3 SD spurious fastball penalty
# relative to training. Impute at the measured train means (pinned by
# test_efv_model) so missing stays NEUTRAL under standardization. Non-lean
# tools (cmd/sl/ch/cb, game_pwr/raw_pwr/field/throw) keep 45.0 - they carry no
# shipped coefficient.
_TOOL_IMPUTE = {"tool_hit": 50.0, "tool_speed": 48.0, "tool_fb": 58.0}

# n_milb_seasons live support cap (AUDIT FIX 2026-07-14): training counts are
# era-censored by the 2014 StatsAPI floor (observed max = 8 on both sides);
# live rows count uncapped (and include the in-progress season), so the ridge
# extrapolated beyond its training support. Cap at the training max.
_N_MILB_SEASONS_CAP = 8.0

# RELIEF-SHAPE neutral imputes (docs/efv-2026-07-15/GATES.md): observed
# debuted-pool means, measured the same way as _TOOL_IMPUTE, so zero-graded
# rows stay neutral under standardization instead of reading as RP-shaped.
_SHAPE_IMPUTE = 38.9
_DEPTH_IMPUTE = 1.6


def _vec(r, side: str = "hit") -> dict:
    m = r.get("milb") or {}
    # milb_missing semantics (AUDIT FIX 2026-07-14): the flag's documented job
    # is "no pre-decision MiLB track record", but 100% of 2011-2014 and ~97% of
    # 2015 debut rows fired it for DATA-AVAILABILITY reasons (no mlbam id /
    # StatsAPI cache floor 2014) - real-WAR debuts flagged as imputed-zero
    # production, diluting the coefficient. Rows the dataset marks
    # milb_unavailable stay NEUTRAL (0.0) instead.
    if r.get("milb"):
        milb_missing = 0.0
    elif r.get("milb_unavailable"):
        milb_missing = 0.0
    else:
        milb_missing = 1.0
    pick = r.get("pick_overall")
    bonus = r.get("bonus_usd")
    def g(v, d=0.0):
        return float(v) if v is not None else d
    out = {
        # fv_effective = the E-STALE anchor-staleness-decayed anchor (live rows
        # only; efv_dataset.build_live_matrix). Training rows have no
        # fv_effective (staleness 0 at a listing event by construction) and
        # fall through to the raw consensus.
        "fv": g(r.get("fv_effective"), g(r.get("consensus_fv_raw"))),
        "fv_trend": g(r.get("fv_trend")),
        "n_sources": g(r.get("n_sources")),
        "age_rel_level": g(m.get("age_rel_level")),
        # Absolute age at the production read (E-AGE, docs/efv-2026-07-14):
        # age_rel_level alone under-prices the outcome clock at old-skewing
        # levels (a 26.6yo AAA bat reads as just "+2 vs level"). Mean-imputed
        # (22.5) behind the indicator so milb-missing rows stay neutral under
        # standardization. Emitted unconditionally; only in _FEATURES_* if the
        # pre-registered gate cleared.
        "age": g(m.get("age"), 22.5),
        "age_missing": 0.0 if m.get("age") is not None else 1.0,
        "level_rank": g(m.get("level_rank")),
        "k_rel": g(m.get("k_rel")),
        "bb_rel": g(m.get("bb_rel")),
        "milb_missing": milb_missing,
        "n_milb_seasons": min(g(m.get("n_milb_seasons")), _N_MILB_SEASONS_CAP),
        # E1 candidate: consecutive seasons on the CURRENT level (1 = arrived this
        # year). Emitted unconditionally so every consumer of `feats` has the key
        # whether or not the feature is switched into the model -- _fit_lgbm_mono
        # indexes feats directly with no default, so a key that exists only on
        # some rows is a crash, not a missing value. Imputed to 1.0 for rows with
        # no MiLB block, the modal value, matching how the rest of the milb block
        # is mean-imputed behind the milb_missing indicator.
        "seasons_at_level": g(m.get("seasons_at_level"), 1.0),
        # Pace from ENTRY level (see efv_model.PACE_FROM_ENTRY). Emitted
        # unconditionally for the same reason seasons_at_level is: _fit_lgbm_mono
        # indexes feats[k] with no default. Imputed neutral behind milb_missing -
        # 1.0 rung/season is the modal climb rate, and entry_observed 0.0 for a
        # row with no ladder is the honest "we cannot see where he started".
        "pace_from_entry": g(m.get("pace_from_entry"), 1.0),
        "entry_level_rank": g(m.get("entry_level_rank"), 2.0),
        "entry_observed": g(m.get("entry_observed"), 0.0),
        "prod_trend": g(m.get("prod_trend")),
        "pos_prem": _pos_premium_for_row(r, side),
        "pick_overall": float(pick) if pick is not None else 250.0,
        "pick_missing": 0.0 if pick is not None else 1.0,
        "bonus_log": math.log1p(float(bonus)) if bonus else 0.0,
        "il_stints_pre": g(r.get("il_stints_pre")),
        "fv_stddev": g(r.get("fv_stddev")),
        # Acquisition-cohort indicators (efv_dataset._cohort_flags). The ridge re-centers
        # each cohort's intercept -> sharper cross-tier ordering (OOS gain, both sides).
        "is_ifa": g(r.get("is_ifa")),
        "is_college": g(r.get("is_college")),
    }
    if side == "pit":
        out.update({
            "tool_fb": g(r.get("tool_fb"), _TOOL_IMPUTE["tool_fb"]),
            "tool_cmd": g(r.get("tool_cmd"), 45.0),
            "tool_sl": g(r.get("tool_sl"), 45.0), "tool_ch": g(r.get("tool_ch"), 45.0),
            "tool_cb": g(r.get("tool_cb"), 45.0), "era_rel": g(m.get("era_rel")),
            "peak_k_rel": g(m.get("peak_k_rel")), "peak_bb_rel": g(m.get("peak_bb_rel")),
            # run-prevention x missing-bats interaction (final-season); see the
            # _x_era_k docstring for the audited-and-deferred quadrant issue.
            "x_era_k": _x_era_k(g(m.get("era_rel")), g(m.get("k_rel"))),
        })
        # RELIEF-SHAPE (docs/efv-2026-07-15/GATES.md): the PAL prospect-watch
        # shape composite (pal_conversion.prospect_role_fit, minus tool_ct
        # which the pre-debut anchor never captures). Computed None-aware from
        # the RAW grades: the imputed tool_* values above would fake depth 1
        # (tool_fb=58) plus a 45 command on tool-missing rows - the 2026-07-14
        # imputation-audit bug class. Zero observed pitch grades -> the
        # observed-train-mean neutrals. GATE VERDICT 2026-07-15: all three
        # arms FAILED the pre-registered RELIEF-SHAPE bar (best pooled
        # -0.0021; the shape signal is real univariately but tool_fb +
        # peak_k_rel/bb_rel already price it - adding it only redistributes
        # rank skill between the 45/50 tiers). Ledger data/
        # xfv_relief_shape_eval.json; arms SPENT, do not re-attempt blind.
        # Keys stay emitted-but-INERT (never in _FEATURES_PIT; the
        # age_missing precedent) so tools/efv_relief_shape_lab.py remains
        # reproducible.
        _obs = [float(v) for v in (r.get("tool_fb"), r.get("tool_sl"),
                                   r.get("tool_cb"), r.get("tool_ch"))
                if v is not None]
        if _obs:
            depth = sum(1 for v in _obs if v >= 55.0)
            depth_s = {0: 5.0, 1: 15.0, 2: 45.0, 3: 80.0}.get(depth, 100.0)
            raw_cmd = r.get("tool_cmd")
            cmd_s = (50.0 if raw_cmd is None
                     else max(0.0, min(100.0, (float(raw_cmd) - 40.0) / 20.0 * 100.0)))
            shape = round(0.60 * depth_s + 0.40 * cmd_s, 1)
            out.update({"starter_shape": shape, "arsenal_depth": float(depth),
                        "relief_flag": 1.0 if shape < 40.0 else 0.0})
        else:
            out.update({"starter_shape": _SHAPE_IMPUTE, "arsenal_depth": _DEPTH_IMPUTE,
                        "relief_flag": 0.0})
    else:
        out.update({
            "tool_hit": g(r.get("tool_hit"), _TOOL_IMPUTE["tool_hit"]),
            "tool_game_pwr": g(r.get("tool_game_pwr"), 45.0),
            "tool_speed": g(r.get("tool_speed"), _TOOL_IMPUTE["tool_speed"]),
            "tool_field": g(r.get("tool_field"), 45.0),
            "obp_rel": g(m.get("obp_rel")), "ops_rel": g(m.get("ops_rel")),
            "peak_obp_rel": g(m.get("peak_obp_rel")), "peak_k_rel": g(m.get("peak_k_rel")),
            "peak_iso_rel": g(m.get("peak_iso_rel")), "peak_ops_rel": g(m.get("peak_ops_rel")),
            "iso_rel": g(m.get("iso_rel")),
            # NOTE: game power stays out of the hitter model. Beyond raw iso_rel + peak_iso_rel
            # (both rejected earlier), the 2026-06-22 CONDITIONAL-power experiment tested power
            # REALIZED in games + level-weighted / contact-paired (iso_x_level, iso_upper,
            # iso_x_hit, iso_x_contact, peak_iso_x_level): all FAILED the OOS bar (best debuted-km
            # -0.0016; replacing tool_speed with power cost -0.014). Third independent confirmation
            # that power does not earn a place here -- the Witt-class power-star miss is the
            # accepted cost of the population-level power-overpricing correction.
        })
    return out


def _prep(rows, target_key, side: str = "hit"):
    out = []
    for r in rows:
        t = r.get(target_key)
        if t is None or r.get("consensus_fv_raw") is None:
            continue
        out.append({"player_key": r["player_key"], "kind": r["kind"],
                    "decision_year": _decision_year(r),
                    "feats": _vec(r, side), "target": float(t),
                    "weight": float(r.get("weight", 1.0)),
                    "fv": float(r["consensus_fv_raw"])})
    return out


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

def _fit_ols_fv(train):
    """Baseline: WAR ~ a + b*FV (the bar). Spearman of its prediction == FV rank corr."""
    n = len(train)
    if n < 8:
        return None
    mx = sum(r["fv"] for r in train) / n
    my = sum(r["target"] for r in train) / n
    cov = sum((r["fv"] - mx) * (r["target"] - my) for r in train)
    var = sum((r["fv"] - mx) ** 2 for r in train)
    if var <= 0:
        return None
    b = cov / var
    return {"a": my - b * mx, "b": b}


def _pred_ols(model, fv):
    return model["a"] + model["b"] * fv


def fit_production_stack(rows, side: str, keys=None):
    """The ONE production fit, shared by efv_score._fit_production (the shipped
    scorer) and rank_calibration (the lambda selector): full labeled pool minus
    never-MLB recent busts -> ridge + linear output calibration + consensus OLS
    anchor. E-LAMBDA parity repair 2026-07-15: the selector used to fit a
    DEBUTED-only anchor and score a RAW uncalibrated model leg, so it sized
    lambda for a blend production never ships (stamped pit 0.63 / hit 0.70 were
    measured on the wrong blend). Both callers now fit through here; the
    selector's legs apply the same calibration clamp and cons floor as run_live.
    Returns {ridge, a, b, ols, keys, n} or None when the pool cannot support a fit."""
    if keys is None:
        keys, _m = _feature_spec(side)
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    if len(data) < 60:
        return None
    ridge = _fit_ridge(data, keys)
    if not ridge:
        return None
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    ols = _fit_ols_fv(data)
    if not ols:
        return None
    return {"ridge": ridge, "a": a, "b": b, "ols": ols, "keys": keys, "n": len(data)}


def _fit_lgbm_mono(train, keys, mono):
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        return None
    if len(train) < 60:
        return None
    X = np.array([[r["feats"][k] for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    w = np.array([r["weight"] for r in train])
    model = lgb.LGBMRegressor(
        n_estimators=250, learning_rate=0.04, num_leaves=7,
        min_child_samples=25, subsample=0.9, subsample_freq=1,
        colsample_bytree=0.8, reg_lambda=5.0, monotone_constraints=mono,
        random_state=7, deterministic=True, verbose=-1)
    model.fit(X, y, sample_weight=w)
    return {"model": model, "keys": keys}


def _pred_lgbm(gbm, feats):
    import numpy as np
    import warnings as _w
    X = np.array([[feats[k] for k in gbm["keys"]]])
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        return float(gbm["model"].predict(X)[0])


def _fit_comps(train, keys):
    import numpy as np
    if len(train) < 40:
        return None
    X = np.array([[r["feats"][k] for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    return {"Xs": (X - mu) / sd, "y": y, "mu": mu, "sd": sd, "keys": keys,
            "pk": [r["player_key"] for r in train]}


def _pred_comps(cm, feats, k=20):
    import numpy as np
    x = (np.array([feats[c] for c in cm["keys"]]) - cm["mu"]) / cm["sd"]
    d = np.sqrt(((cm["Xs"] - x) ** 2).sum(axis=1))
    idx = np.argsort(d)[:k]
    w = 1.0 / (d[idx] + 1e-6)
    pred = float((w * cm["y"][idx]).sum() / w.sum())
    comps = [(cm["pk"][i], round(float(cm["y"][i]), 2), round(float(d[i]), 2))
             for i in idx[:5]]
    return pred, comps


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

def _lofo_calibrate(fold_map):
    """Leave-one-fold-out linear recentering (realized ~ a + b*pred).

    DOCSTRING CORRECTED 2026-07-14 (audit): the old claims were wrong on both
    counts. (1) POOLED Spearman is NOT strictly unchanged vs raw - each fold
    gets its own affine map, so cross-fold ordering can shift (within-fold
    order is preserved). (2) "fit on the OTHER folds only" includes LATER
    folds - leave-one-out over a time series is not forward-chained, so this
    is a diagnostic recentering, not a leakage-clean protocol; the governance
    metrics never consume it for ranking claims."""
    out, yrs = [], list(fold_map)
    for yr in yrs:
        others = [p for y in yrs if y != yr for p in fold_map[y]]
        cal = _fit_linear_calibration(others)
        if not cal:
            out.extend(fold_map[yr])
            continue
        out.extend((max(0.0, cal["a"] + cal["b"] * pred), t) for pred, t in fold_map[yr])
    return out


def _run_eval(data, label, keys=None, mono=None, lam=None):
    keys = keys or _KEYS
    mono = mono or _MONO
    pairs = {m: [] for m in ("baseline", "ridge", "blend", "lgbm", "comps", "ensemble")}
    # Row weights parallel to `pairs`. A censored 2024 row carries 0.333, and
    # pooling it unweighted put two thirds of an extrapolated label into the
    # published figure at full strength. Owner decision 2026-08-06.
    wts = {m: [] for m in pairs}
    fold_map = {m: {} for m in ("ridge", "ensemble")}   # for LOFO calibration
    per_year = {}
    for yr in SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = _fit_ols_fv(train)
        ridge = _fit_ridge(train, keys)
        gbm = _fit_lgbm_mono(train, keys, mono)
        cm = _fit_comps(train, keys)
        yp = {m: [] for m in pairs}
        # WEIGHTS, parallel to yp. Kept as a separate list rather than folded
        # into the tuples so _lofo_calibrate and every other pair consumer keep
        # their existing shape; only _score learns about weights.
        yw = {m: [] for m in pairs}
        for r in test:
            t = r["target"]
            # A censored 2024 row carries 0.333. Pooling it at full strength put
            # two thirds of an extrapolated label into the published number.
            _w = float(r.get("weight") or 1.0)
            if ols:
                yp["baseline"].append((max(0.0, _pred_ols(ols, r["fv"])), t))
                yw["baseline"].append(_w)
            if ridge:
                yp["ridge"].append((_predict(ridge, r["feats"]), t))
                yw["ridge"].append(_w)
            # blend == the SHIPPED headline rank: (1-lam)*consensus_OLS + lam*model
            # (consensus anchor floored at 0 WAR, matching the baseline).
            if ridge and ols and lam is not None:
                yp["blend"].append(((1 - lam) * max(0.0, _pred_ols(ols, r["fv"]))
                                    + lam * _predict(ridge, r["feats"]), t))
                yw["blend"].append(_w)
            if gbm:
                yp["lgbm"].append((_pred_lgbm(gbm, r["feats"]), t))
                yw["lgbm"].append(_w)
            if cm:
                p, _ = _pred_comps(cm, r["feats"])
                yp["comps"].append((p, t))
                yw["comps"].append(_w)
            if ridge and gbm:
                yp["ensemble"].append(
                    ((_predict(ridge, r["feats"]) + _pred_lgbm(gbm, r["feats"])) / 2, t))
                yw["ensemble"].append(_w)
        for m in pairs:
            pairs[m].extend(yp[m])
            wts[m].extend(yw[m])
        for m in fold_map:
            fold_map[m][yr] = yp[m]
        per_year[str(yr)] = {m: _score(yp[m], yw[m])
                             for m in pairs if len(yp[m]) >= 8}
    pooled = {m: (_score(pairs[m], wts[m]) if pairs[m] else {"n": 0})
              for m in pairs}
    # calibrated (rank-preserving) variants — the Pass-3 step that should
    # close the MAE gap without surrendering the rank edge.
    pooled["ridge_cal"] = _score(_lofo_calibrate(fold_map["ridge"])) if fold_map["ridge"] else {"n": 0}
    pooled["ensemble_cal"] = _score(_lofo_calibrate(fold_map["ensemble"])) if fold_map["ensemble"] else {"n": 0}
    base = pooled["baseline"]
    verdict = {}
    for m in ("ridge", "blend", "lgbm", "comps", "ensemble", "ridge_cal", "ensemble_cal"):
        s = pooled[m]
        if s.get("n", 0) > 80 and s.get("mae") is not None and base.get("mae") is not None:
            beats_mae = s["mae"] < base["mae"]
            beats_rho = (s.get("spearman") or -9) > (base.get("spearman") or -9)
            verdict[m] = {"beats_mae": beats_mae, "beats_spearman": beats_rho,
                          "rank_win": bool(beats_mae and beats_rho)}
    return {"label": label, "pooled_oos": pooled, "per_year": per_year,
            "verdict_vs_consensus": verdict}


def _importances(data, keys=None, mono=None):
    """Full-window diagnostics (NOT shipped predictions): standardized ridge weights +
    lgbm gain, to show WHERE the signal is. Interpretation only."""
    keys = keys or _KEYS
    mono = mono or _MONO
    out = {}
    ridge = _fit_ridge(data, keys)
    if ridge:
        out["ridge_std_weights"] = {k: round(w, 3) for k, w in zip(ridge["keys"], ridge["w"])}
    gbm = _fit_lgbm_mono(data, keys, mono)
    if gbm:
        imp = gbm["model"].feature_importances_
        tot = float(sum(imp)) or 1.0
        out["lgbm_gain_share"] = {k: round(float(v) / tot, 3)
                                  for k, v in sorted(zip(keys, imp), key=lambda x: -x[1])}
    return out


def _era_of(yr) -> str:
    """Debut-era bucket, matching _era_split and the eFV labs."""
    y = int(yr)
    return "<=2018" if y <= 2018 else ("2019-2021" if y <= 2021 else "2022-2023")


# ---------------------------------------------------------------------------
# gate floors (measured, not assumed)
# ---------------------------------------------------------------------------
#: Model-vs-consensus MDE95 under the protocol that SHIPS today: 11 forward-chained
#: folds, pair-weighted pooled Spearman, debuted-KM pool. Measured 2026-08-07 by
#: `python tools/efv_mde_lab.py mde 2000` (paired bootstrap resampling train AND test
#: together, refit every draw, seed 20260807); ledger data/xfv_mde_floor.json.
#:
#: One-sided 95% (1.645 * sd), which is the convention the retired 0.045 was on: the
#: same lab reproduces 0.0376 hit / 0.0487 pit on the legacy 4-fold pool, bracketing
#: it. The convention was never written down before, and reading 0.045 as two-sided
#: would have moved the bar by 18%.
#:
#: The 11-fold promotion did NOT lower this floor. Pool n went 353/438 -> 755/890, but
#: the added folds are the thin 2014-2019 cohorts and the censored 2024 cohort, and
#: pair-weighting the 2024 rows at 0.333 gives back the effective n that the extra
#: rows bought. The planning estimate of ~0.012 is off by roughly 3.7x.
MDE95_POOLED_RHO = {"hit": 0.044, "pit": 0.044}

#: Same measurement for the two-metric gate's block-rho leg (below). Higher SNR than
#: either side's pooled rho because the (side x cohort-year) normalization removes the
#: between-fold level differences that pooling otherwise counts as signal.
MDE95_BLOCK_RHO = 0.0325

_BLOCK_RHO_CACHE: dict = {}


def _block_norm(pairs):
    """Percentile position inside one block, on [0, 1]. Uses the same average-rank
    treatment of ties as _spearman, so a block of identical predictions contributes
    a constant rather than an arbitrary order."""
    from prospect_path import _rankdata
    n = len(pairs)
    r = _rankdata(pairs)
    return [(x - 0.5) / n for x in r]


def block_rho_eval() -> dict:
    """The second leg of the two-metric gate (docs/EFV_GATE_STANDARD.md section 3).

    Pooled Spearman alone is a low-power instrument at these n, and it is inflated by
    between-fold level differences: a fold where everyone busted and a fold where
    everyone stuck are pooled as if their WAR numbers were on one scale. block-rho
    percentile-normalizes prediction and outcome INSIDE each (side x cohort-year)
    block, then pools, so only within-cohort ordering counts. Both sides enter one
    number, which is also why it is computed jointly and memoized rather than per side.

    Read it WITH the pooled rho, never instead of it. Note the carve-out at
    EFV_GATE_STANDARD.md section 3: full-pool debut AUC, the other high-SNR
    instrument, is INADMISSIBLE for any candidate that can sense a missing MiLB
    block, because missingness is a near-deterministic proxy for that AUC's label.
    block-rho carries no such exclusion, which is what makes it the usable one.
    """
    if "v" in _BLOCK_RHO_CACHE:
        return _BLOCK_RHO_CACHE["v"]
    from efv_dataset import matrix_path
    cons_all, blend_all, tgt_all, wts_all = [], [], [], []
    per_side = {}
    for side in ("hit", "pit"):
        keys, _m = _feature_spec(side)
        lam = blend_lambda(side)
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
        n_side = 0
        for yr in SCORED_YEARS:
            tr = [r for r in data if r["decision_year"] < yr]
            te = [r for r in data if r["decision_year"] == yr]
            if len(te) < 15 or len(tr) < 60:
                continue
            ols = _fit_ols_fv(tr)
            ridge = _fit_ridge(tr, keys)
            if not (ols and ridge):
                continue
            cons = [max(0.0, _pred_ols(ols, r["fv"])) for r in te]
            blend = [(1 - lam) * c + lam * _predict(ridge, r["feats"])
                     for c, r in zip(cons, te)]
            cons_all.extend(_block_norm(cons))
            blend_all.extend(_block_norm(blend))
            tgt_all.extend(_block_norm([r["target"] for r in te]))
            wts_all.extend(float(r.get("weight") or 1.0) for r in te)
            n_side += len(te)
        per_side[side] = n_side
    if len(tgt_all) < 8:
        raise ValueError("block-rho pool too small")
    from prospect_path import _weighted_spearman
    c = _weighted_spearman(cons_all, tgt_all, wts_all)
    b = _weighted_spearman(blend_all, tgt_all, wts_all)
    delta = round((b or 0.0) - (c or 0.0), 4)
    resolvable = abs(delta) >= MDE95_BLOCK_RHO
    out = {
        "instrument": "block-rho: (side x cohort-year) percentile-normalized, both sides pooled",
        "registration": "docs/EFV_GATE_STANDARD.md section 3 (two-metric gate)",
        "n": len(tgt_all), "n_by_side": per_side,
        "weighting": "pair-weighted, same basis as the headline pooled rho",
        "consensus_block_rho": c, "blend_block_rho": b, "delta": delta,
        "mde95": MDE95_BLOCK_RHO,
        "mde95_source": "tools/efv_mde_lab.py mde (data/xfv_mde_floor.json)",
        "resolvable": resolvable,
        "verdict": ("beats consensus" if (delta > 0 and resolvable)
                    else "loses to consensus" if (delta < 0 and resolvable)
                    else "not resolvable at this power"),
        "note": ("identical block on both side artifacts; the instrument is joint by "
                 "construction. Reported BESIDE the pooled rho, not instead of it."),
    }
    _BLOCK_RHO_CACHE["v"] = out
    return out


def _honest_note(evals, era, block, side) -> str:
    """The artifact's own summary, DERIVED from the numbers beside it.

    This used to be a hardcoded paragraph asserting that eFV beats consensus on rank
    for both cuts. The 2026-08-06 promotion to 11 folds made that false in the same
    file that printed it: hitter full_pool_km went rank-negative and every cut's
    delta fell far under its MDE. A note that cannot be contradicted by its own
    artifact is the only kind worth shipping, so it is now assembled from
    verdict_vs_consensus, the era split, and the block-rho leg.
    """
    parts = []
    cuts = []
    for cut in ("debuted_km", "full_pool_km"):
        ev = evals.get(cut) or {}
        pooled = ev.get("pooled_oos") or {}
        base = (pooled.get("baseline") or {}).get("spearman")
        blend = (pooled.get("blend") or {}).get("spearman")
        if base is None or blend is None:
            continue
        cuts.append((cut, round(blend - base, 4)))
    if cuts:
        side_mde = MDE95_POOLED_RHO.get(side)
        wins = [c for c in cuts if c[1] > 0]
        resolved = [c for c in cuts if abs(c[1]) >= (side_mde or 9)]
        detail = ", ".join(f"{name} {d:+.4f}" for name, d in cuts)
        if resolved:
            parts.append(f"eFV's rank edge over consensus FV is measurable on {detail} "
                         f"against an MDE95 of {side_mde}.")
        elif len(wins) == len(cuts):
            parts.append(f"eFV ranks ahead of consensus FV on every out-of-sample cut "
                         f"({detail}), but no gap reaches the {side_mde} this eval can "
                         f"resolve, so treat it as a tie, not a win.")
        else:
            parts.append(f"eFV does not beat consensus FV on out-of-sample rank on every "
                         f"cut ({detail}), and no gap reaches the {side_mde} this eval can "
                         f"resolve either way.")
    if block:
        parts.append(f"The higher-SNR block-rho leg reads {block.get('delta'):+.4f} against "
                     f"{block.get('mde95')}: {block.get('verdict')}.")
    recent = (era or {}).get("2022-2023") or {}
    old = (era or {}).get("<=2018") or {}
    if recent.get("consensus_spearman") is not None and old.get("consensus_spearman") is not None:
        d_new = recent["xfv_blend_spearman"] - recent["consensus_spearman"]
        d_old = old["xfv_blend_spearman"] - old["consensus_spearman"]
        parts.append(f"By era the edge concentrates in recent cohorts ({d_new:+.4f} on "
                     f"2022-2023 vs {d_old:+.4f} on <=2018), so what edge exists is not "
                     f"an artifact of older, less accurate scouting.")
    mae = ((evals.get("debuted_km") or {}).get("verdict_vs_consensus") or {}).get("blend") or {}
    if mae.get("beats_mae") is False:
        parts.append("eFV still trails on MAE (it predicts more spread; consensus regresses "
                     "to the mean). That loss is committed.")
    parts.append("The flagship case is the package: rank + calibrated distribution + "
                 "uncertainty + surplus + power-correction, not a resolved rank win.")
    return " ".join(parts)


def _cohort_map(rows) -> dict:
    """player_key -> acquisition cohort (ifa / college / hs / draft / other), matching
    efv_dataset._cohort_flags + the eFV lab's leakage-free draft-age split (drafted at
    age >= 21 = college, else hs). Storage-derived; used ONLY for the M1 eval AUC
    breakdown, NEVER for scoring, so a missing storage layer degrades to 'other'."""
    keys = [r["player_key"] for r in rows if r.get("player_key")]
    if not keys:
        return {}
    bd = {r["player_key"]: r.get("birth_date") for r in rows}
    acq = {}
    try:
        import storage
        with storage.connect() as con:
            ph = ",".join("?" for _ in keys)
            for r in con.execute(
                    f"SELECT player_key, method, year FROM acquisitions "
                    f"WHERE player_key IN ({ph})", tuple(keys)):
                acq[r["player_key"]] = {"method": r["method"], "year": r["year"]}
    except Exception:
        return {}
    out = {}
    for pk in keys:
        a = acq.get(pk) or {}
        m = a.get("method")
        if m == "international_fa":
            out[pk] = "ifa"
        elif m == "draft":
            yr, b = a.get("year"), bd.get(pk)
            coh = "draft"
            if yr and b:
                try:
                    coh = "college" if (int(yr) - int(str(b)[:4])) >= 21 else "hs"
                except (ValueError, TypeError):
                    coh = "draft"
            out[pk] = coh
        else:
            out[pk] = "other"
    return out


def _auc_breakdown(data, keys, lam, cohort_map) -> dict:
    """M1 instrumentation (measurement, not a model change). Forward-chained
    contributor-AUC (realized first-6yr WAR >= _CONTRIB_WAR) and star-AUC
    (>= _STAR_WAR) for the shipped BLEND and the CONSENSUS baseline, sliced by
    acquisition cohort, debut era, and FV tier -- so eFV's discrimination margin
    over consensus FV is visible per cell. Same forward-chained folds as the
    'blend' eval row (each cohort year scored by models fit on strictly-earlier
    cohorts). Reuses source_backtest._auc (Mann-Whitney U). Both scores share the
    SAME binary labels, so the model-minus-consensus margin is label-invariant."""
    try:
        from source_backtest import _auc
    except Exception:
        return {"n": 0, "note": "source_backtest._auc unavailable"}
    # Forward-chain over the full scoreable span (seed years 2016+ populate the <=2018
    # era cell, as in _era_split); tag each row with its fold year. Pooled/cohort/tier
    # use SCORED_YEARS only so pooled n matches the 'blend' eval row; by_era uses the
    # full span so all three era cells can appear.
    recs = []   # (blend, cons, war, fv, cohort, era, year)
    for yr in range(2016, max(SCORED_YEARS) + 1):
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            blend = (1 - lam) * cons + lam * _predict(ridge, r["feats"])
            recs.append((blend, cons, r["target"], r["fv"],
                         cohort_map.get(r["player_key"], "other"),
                         _era_of(r["decision_year"]), int(r["decision_year"])))
    scored = [r for r in recs if r[6] in SCORED_YEARS]
    if len(scored) < 30:
        return {"n": len(scored), "note": "insufficient rows for AUC breakdown"}

    def _pair(subset, thresh):
        if len(subset) < 15:
            return None
        labels = [w >= thresh for _, _, w, _, _, _, _ in subset]
        n_pos = sum(labels)
        if n_pos == 0 or n_pos == len(labels):
            return None
        am = _auc([b for b, _, _, _, _, _, _ in subset], labels)
        ac = _auc([c for _, c, _, _, _, _, _ in subset], labels)
        return {"n": len(subset), "n_pos": int(n_pos),
                "model_auc": round(am, 4) if am is not None else None,
                "consensus_auc": round(ac, 4) if ac is not None else None,
                "margin": (round(am - ac, 4) if (am is not None and ac is not None) else None)}

    def _cell(subset):
        c = {"contributor": _pair(subset, _CONTRIB_WAR), "star": _pair(subset, _STAR_WAR)}
        return c if (c["contributor"] or c["star"]) else None

    out = {"n": len(scored), "n_with_seed_folds": len(recs),
           "labels": {"contributor_war": _CONTRIB_WAR, "star_war": _STAR_WAR,
                      "war_metric": "first-6yr summed bWAR (target_censored); "
                                    "model=blend, consensus=OLS(FV) anchor, shared labels"},
           "pooled": _cell(scored), "by_cohort": {}, "by_era": {}, "by_fv_tier": {}}
    for c in ("hs", "college", "ifa", "draft", "other"):
        cell = _cell([r for r in scored if r[4] == c])
        if cell:
            out["by_cohort"][c] = cell
    for e in ("<=2018", "2019-2021", "2022-2023"):
        cell = _cell([r for r in recs if r[5] == e])
        if cell:
            out["by_era"][e] = cell
    for tk in sorted({round(r[3] / 5) * 5 for r in scored}):
        cell = _cell([r for r in scored if round(r[3] / 5) * 5 == tk])
        if cell:
            out["by_fv_tier"][str(int(tk))] = cell
    return out


# ---------------------------------------------------------------------------
# eFV 3.4 F-SIDE -- standing JOINT side-fairness eval line (measurement-only)
# ---------------------------------------------------------------------------
# Question kept honest by this line: do PITCHERS at a given joint-board slot /
# display grade systematically deliver worse realized outcomes than HITTERS at
# the same slot -- and does any future model change WIDEN that gap? The line is
# output-neutral by construction: it READS the Pass-1 matrices and the stamped
# live lambdas, and WRITES only eval artifacts (data/xfv_side_fairness_eval.json
# + a compact 'side_fairness' block in xfv_eval*.json). No scorer, producer or
# payload writer is touched, so every published player number is byte-identical.
#
# Provenance: the 2026-07 side_fairness scratchpad investigation; this code is
# that prototype verbatim (same folds, same guards, same RNG stream), so the
# headline number reproduces bit-for-bit: full-pool joint display-grade TOP-25
# hit-minus-pit mean first-6yr WAR +3.95, CI90 [1.55, 6.35], p(hit>pit)=0.996.

_SF_SEED = 7            # bootstrap seed (prototype + program standard)
_SF_BOOT = 2000         # bootstrap replicates (program standard)
_SF_IPCW_CAP = 5.0      # IPCW weight cap
_SF_BUST_WAR = 0.5      # realized bust threshold (first-6yr WAR < 0.5)
_SF_BANDS = ((1, 25, "001-025"), (26, 50, "026-050"), (51, 100, "051-100"),
             (101, 200, "101-200"), (201, 10 ** 9, "201+"))
_SF_OUT = "xfv_side_fairness_eval.json"
_SF_CACHE: dict = {}    # per-process memo: hit + pit run() calls share one computation


def _sf_live_lambdas():
    """Blend weights actually SERVED: the live lambdas stamped into data/xfv.json meta
    by the scorer -- so a lambda restamp flows into this line automatically. Fallback =
    the 2026-07-14 stamp so the line still runs on a cold tree (source recorded)."""
    try:
        meta = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8")).get("meta", {})
        ll = meta.get("live_lambda") or {}
        return ({"hit": float(ll["hit"]), "pit": float(ll["pit"])},
                "data/xfv.json meta.live_lambda")
    except Exception:
        return {"hit": 0.70, "pit": 0.63}, "fallback constants (xfv.json meta unavailable)"


def _sf_pool(side, frame):
    """(prepped rows, player_key -> censored flag) for one side/frame.
    full_pool (PRIMARY) = debuted + busts minus recent busts, KM target -- the
    rank-the-board population; debuted_only = the survivorship-censored sensitivity
    frame (it cannot see never-debut risk; that is WHY it is not primary)."""
    from efv_dataset import matrix_path
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    if frame == "debuted_only":
        raw = [r for r in rows if r["kind"] == "debuted"]
    else:
        raw = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    cens = {r["player_key"]: bool(r.get("censored")) for r in rows}
    return _prep(raw, "target_censored", side), cens


def _sf_fwd_chain(data, side, lam, years):
    """Forward-chained OOS production-analogue scores (prototype verbatim): per fold
    fit OLS(FV) anchor + lean ridge + linear calibration on decision_year < Y, score
    == Y; rank_war = (1-lam)*max(0, cons) + lam*max(-2, a+b*ridge). Fold guards match
    _run_eval (>=15 test / >=60 train)."""
    keys, _m = _feature_spec(side)
    out = []
    for yr in years:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            model = max(-2.0, a + b * _predict(ridge, r["feats"]))
            out.append({"pk": r["player_key"], "side": side, "year": yr, "fv": r["fv"],
                        "war": r["target"], "rank_war": (1 - lam) * cons + lam * model})
    return out


def _sf_quantile_display(rows_side):
    """Per-side rank-preserving quantile map of rank_war onto that side's OWN
    consensus-FV distribution (efv_score.run/run_live: xfv_grade_display),
    replicated within one fold-year test pool. This map is exactly what lets each
    side fill the joint board's top slots at its own FV-distribution rate -- the
    map-vs-raw share-inflation this line measures.

    NAMING CORRECTED 2026-08-04: this used to be documented as "Production display
    grade". It is NOT the served display any more. The quantile map was retired
    from display on 2026-07-25 (storage.BOARD_GRADE_FIELD = raw xfv_grade); what
    it still IS, in production, is the basis SURPLUS DOLLARS are priced through
    (efv_score re-prices on xfv_grade_display). So the F-SIDE 'display' leg is a
    fairness read on the DOLLAR basis, not on the served board order.
    OPEN: the served-board leg of that eval is the raw rank_war leg, and nothing
    here measures fairness on the actual served grade. Flagged, not silently
    re-plumbed - changing what F-SIDE measures is a gate decision, not a comment
    fix."""
    if not rows_side:
        return
    target = sorted(r["fv"] for r in rows_side)
    order = sorted(range(len(rows_side)), key=lambda i: rows_side[i]["rank_war"])
    m = len(rows_side)
    for pos_rank, i in enumerate(order):
        pos = ((pos_rank / (m - 1)) if m > 1 else 0.0) * (m - 1)
        lo = int(pos)
        hi = min(m - 1, lo + 1)
        rows_side[i]["disp"] = target[lo] * (1 - (pos - lo)) + target[hi] * (pos - lo)


def _sf_summ(rows, wkey=None):
    """Realized-outcome cell: mean AND median first-6yr WAR (co-primary) +
    contributor/star/bust rates. wkey='ipcw_w' produces the IPCW-weighted variant
    (weighted median = lowest value whose cumulative weight reaches half; effective_n
    = (sum w)^2 / sum w^2 reported)."""
    if not rows:
        return None
    wars = [r["war"] for r in rows]
    if wkey is None:
        n = len(wars)
        return {"n": n,
                "mean_war": round(statistics.mean(wars), 2),
                "median_war": round(statistics.median(wars), 2),
                "contrib_rate": round(sum(1 for x in wars if x >= _CONTRIB_WAR) / n, 3),
                "star_rate": round(sum(1 for x in wars if x >= _STAR_WAR) / n, 3),
                "bust_rate": round(sum(1 for x in wars if x < _SF_BUST_WAR) / n, 3)}
    w = [r[wkey] for r in rows]
    W = sum(w)
    med = sorted(wars)[-1]
    acc = 0.0
    for x, wi in sorted(zip(wars, w)):
        acc += wi
        if acc >= W / 2:
            med = x
            break
    return {"n": len(rows),
            "effective_n": round(W * W / sum(x * x for x in w), 1),
            "mean_war": round(sum(v * wi for v, wi in zip(wars, w)) / W, 2),
            "median_war": round(med, 2),
            "contrib_rate": round(sum(wi for v, wi in zip(wars, w) if v >= _CONTRIB_WAR) / W, 3),
            "star_rate": round(sum(wi for v, wi in zip(wars, w) if v >= _STAR_WAR) / W, 3),
            "bust_rate": round(sum(wi for v, wi in zip(wars, w) if v < _SF_BUST_WAR) / W, 3)}


def _sf_boot(hit_rows, pit_rows, wkey=None, iters=_SF_BOOT, seed=_SF_SEED):
    """Bootstrap hit-minus-pit realized-WAR difference: mean AND median co-primary,
    each with CI90 + bootstrap SE. The unweighted mean draws consume the RNG stream
    exactly as the prototype's boot_diff did, so historical CIs reproduce verbatim.
    Weighted variant (wkey) resamples rows and recomputes the weighted statistic."""
    if len(hit_rows) < 8 or len(pit_rows) < 8:
        return None
    rng = random.Random(seed)
    hw = [r["war"] for r in hit_rows]
    pw = [r["war"] for r in pit_rows]
    hwt = None if wkey is None else [r[wkey] for r in hit_rows]
    pwt = None if wkey is None else [r[wkey] for r in pit_rows]

    def _mean(vals, wts):
        if wts is None:
            return statistics.mean(vals)
        return sum(v * w for v, w in zip(vals, wts)) / sum(wts)

    def _median(vals, wts):
        if wts is None:
            return statistics.median(vals)
        W = sum(wts)
        acc = 0.0
        for v, w in sorted(zip(vals, wts)):
            acc += w
            if acc >= W / 2:
                return v
        return sorted(vals)[-1]

    md, dd = [], []
    for _ in range(iters):
        hidx = [rng.randrange(len(hw)) for _ in hw]
        pidx = [rng.randrange(len(pw)) for _ in pw]
        hs, ps = [hw[i] for i in hidx], [pw[i] for i in pidx]
        hws = None if hwt is None else [hwt[i] for i in hidx]
        pws = None if pwt is None else [pwt[i] for i in pidx]
        md.append(_mean(hs, hws) - _mean(ps, pws))
        dd.append(_median(hs, hws) - _median(ps, pws))
    md.sort()
    dd.sort()
    return {"mean_diff": round(_mean(hw, hwt) - _mean(pw, pwt), 2),
            "mean_ci90": [round(md[int(0.05 * iters)], 2), round(md[int(0.95 * iters)], 2)],
            "mean_se": round(statistics.pstdev(md), 3),
            "median_diff": round(_median(hw, hwt) - _median(pw, pwt), 2),
            "median_ci90": [round(dd[int(0.05 * iters)], 2), round(dd[int(0.95 * iters)], 2)],
            "median_se": round(statistics.pstdev(dd), 3),
            "p_hit_gt_pit": round(sum(1 for d in md if d > 0) / iters, 3)}


def _sf_band_tables(scored, wkey=None):
    """Joint-board band tables for BOTH rankings -- production display grade ('disp')
    and raw rank_war WAR units (the calibration-honest cross-side comparison) --
    banded within each fold year, pooled across folds. The display table carries the
    pitcher slot share, the raw-frame share, and the display-vs-raw share-inflation
    ratio (how much the per-side quantile map inflates pitcher representation)."""
    tabs = {}
    for key in ("disp", "rank_war"):
        bands = {}
        for yr in sorted({r["year"] for r in scored}):
            pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r[key])
            for i, r in enumerate(pool, 1):
                for lo, hi, name in _SF_BANDS:
                    if lo <= i <= hi:
                        bands.setdefault(name, []).append(r)
                        break
        out = {}
        for name in sorted(bands):
            grp = bands[name]
            hit = [r for r in grp if r["side"] == "hit"]
            pit = [r for r in grp if r["side"] == "pit"]
            out[name] = {"pit_share": round(len(pit) / len(grp), 3),
                         "hit": _sf_summ(hit, wkey), "pit": _sf_summ(pit, wkey),
                         "boot": _sf_boot(hit, pit, wkey)}
        tabs[key] = out
    for name, cell in tabs["disp"].items():
        rw = tabs["rank_war"].get(name, {}).get("pit_share")
        cell["pit_share_rank_war_frame"] = rw
        cell["share_inflation_display_vs_raw"] = (round(cell["pit_share"] / rw, 2)
                                                  if rw else None)
    return tabs["disp"], tabs["rank_war"]


def _sf_grade_cells(scored, gkey, wkey=None):
    """Equal-grade cells on nearest-5 bands (55-band = [52.5, 57.5), 60 = 57.5+;
    prototype banding) PLUS the BINDING '55_plus' threshold cell = all rows with
    grade >= 52.5 (displays as 55 or better under the round-to-nearest eFV scale).
    The 50 band is a TRACKED DIAGNOSTIC, never a gate (pre-registered)."""
    out = {}
    for g in (40, 45, 50, 55, 60):
        if g == 60:
            grp = [r for r in scored if r.get(gkey) is not None and r[gkey] >= 57.5]
        else:
            grp = [r for r in scored if r.get(gkey) is not None
                   and abs(r[gkey] - g) <= 2.5 and r[gkey] < g + 2.5]
        hit = [r for r in grp if r["side"] == "hit"]
        pit = [r for r in grp if r["side"] == "pit"]
        out[str(g)] = {"hit": _sf_summ(hit, wkey), "pit": _sf_summ(pit, wkey),
                       "boot": _sf_boot(hit, pit, wkey)}
    grp = [r for r in scored if r.get(gkey) is not None and r[gkey] >= 52.5]
    hit = [r for r in grp if r["side"] == "hit"]
    pit = [r for r in grp if r["side"] == "pit"]
    out["55_plus_binding"] = {"hit": _sf_summ(hit, wkey), "pit": _sf_summ(pit, wkey),
                              "boot": _sf_boot(hit, pit, wkey)}
    return out


def _sf_per_fold_top25(scored):
    """Per-fold joint display-grade TOP-25 hit-minus-pit diffs -- the B1 sign-agreement
    input (mean AND median, co-primary)."""
    out = {}
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r["disp"])[:25]
        hit = [r for r in pool if r["side"] == "hit"]
        pit = [r for r in pool if r["side"] == "pit"]
        if not (hit and pit):
            out[str(yr)] = {"n_hit": len(hit), "n_pit": len(pit), "note": "one-sided top-25"}
            continue
        dm = (statistics.mean(r["war"] for r in hit)
              - statistics.mean(r["war"] for r in pit))
        dmed = (statistics.median(r["war"] for r in hit)
                - statistics.median(r["war"] for r in pit))
        out[str(yr)] = {"n_hit": len(hit), "n_pit": len(pit),
                        "mean_diff": round(dm, 2), "median_diff": round(dmed, 2),
                        "sign": "hit_gt_pit" if dm > 0 else "pit_ge_hit"}
    return out


def _sf_ipcw_weights(scored, cens_map):
    """IPCW: on the RESOLVED subset, weight each row by 1 / P(resolved), estimated
    empirically within (side, fold-year, nearest-5 FV) cells (fallback to
    (side, fold-year) when the cell has < 5 rows), capped at _SF_IPCW_CAP. Returns
    resolved rows with r['ipcw_w'] set. This re-inflates the resolved subset back
    toward the full-board population -- the uncertainty band around the KM frame."""
    from collections import defaultdict
    cell = defaultdict(lambda: [0, 0])
    coarse = defaultdict(lambda: [0, 0])
    for r in scored:
        res = not cens_map.get((r["side"], r["pk"]), False)
        k = (r["side"], r["year"], round(r["fv"] / 5) * 5)
        cell[k][0] += 1
        cell[k][1] += res
        coarse[(r["side"], r["year"])][0] += 1
        coarse[(r["side"], r["year"])][1] += res
    out = []
    for r in scored:
        if cens_map.get((r["side"], r["pk"]), False):
            continue
        k = (r["side"], r["year"], round(r["fv"] / 5) * 5)
        n, nr = cell[k] if cell[k][0] >= 5 else coarse[(r["side"], r["year"])]
        p = (nr / n) if n else 1.0
        rr = dict(r)
        rr["ipcw_w"] = min(_SF_IPCW_CAP, 1.0 / p) if p > 0 else _SF_IPCW_CAP
        out.append(rr)
    return out


def _sf_frame(frame, lam):
    """One frame (full_pool | debuted_only): forward-chain both sides, replicate the
    display map, build the joint tables. Returns (result block, scored rows,
    (side, pk) -> censored map)."""
    scored, cens_map, fold_counts = [], {}, {}
    for side in ("hit", "pit"):
        data, cens = _sf_pool(side, frame)
        fc = {}
        for yr in (*SCORED_YEARS, max(SCORED_YEARS) + 1):
            ntr = sum(1 for r in data if r["decision_year"] < yr)
            nte = sum(1 for r in data if r["decision_year"] == yr)
            fc[str(yr)] = {"n_train": ntr, "n_test": nte,
                           "passes_guards": bool(nte >= 15 and ntr >= 60)}
        fold_counts[side] = fc
        rows = _sf_fwd_chain(data, side, lam[side], SCORED_YEARS)
        for yr in sorted({r["year"] for r in rows}):
            _sf_quantile_display([r for r in rows if r["year"] == yr])
        for pk, c in cens.items():
            cens_map[(side, pk)] = c
        scored.extend(rows)
    disp_tab, rw_tab = _sf_band_tables(scored)
    res = {
        "n_hit": sum(1 for r in scored if r["side"] == "hit"),
        "n_pit": sum(1 for r in scored if r["side"] == "pit"),
        "per_side_spearman_rankwar_vs_war": {
            s: _spearman([r["rank_war"] for r in scored if r["side"] == s],
                         [r["war"] for r in scored if r["side"] == s])
            for s in ("hit", "pit")},
        "fold_counts_vs_guards": fold_counts,
        "per_fold_top25_display": _sf_per_fold_top25(scored),
        "joint_bands_display_grade": disp_tab,
        "joint_bands_rank_war": rw_tab,
        "equal_display_grade": _sf_grade_cells(scored, "disp"),
        "equal_consensus_fv": _sf_grade_cells(scored, "fv"),
        "pred_vs_realized_by_side": {
            s: {"n": len([r for r in scored if r["side"] == s]),
                "mean_pred": round(statistics.mean(r["rank_war"] for r in scored
                                                   if r["side"] == s), 2),
                "mean_real": round(statistics.mean(r["war"] for r in scored
                                                   if r["side"] == s), 2)}
            for s in ("hit", "pit")},
    }
    return res, scored, cens_map


def _sf_ipcw_frame(scored, cens_map):
    """IPCW uncertainty band: band membership comes from the FULL joint board (all
    rows ranked by display grade); band statistics are then estimated from the
    RESOLVED members only, re-weighted by 1/P(resolved). Reported next to the KM
    primary frame -- agreement bounds what window-censoring could be hiding."""
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r["disp"])
        for i, r in enumerate(pool, 1):
            for lo, hi, name in _SF_BANDS:
                if lo <= i <= hi:
                    r["band_disp"] = name
                    break
    resolved = _sf_ipcw_weights(scored, cens_map)
    ws = [r["ipcw_w"] for r in resolved]
    out = {"resolved_n": len(resolved),
           "resolved_share": round(len(resolved) / len(scored), 3) if scored else None,
           "weight_cap": _SF_IPCW_CAP,
           "weights": ({"max": round(max(ws), 2), "mean": round(statistics.mean(ws), 2),
                        "n_at_cap": sum(1 for w in ws if w >= _SF_IPCW_CAP)} if ws else None),
           "bands_display_grade": {}}
    for lo, hi, name in _SF_BANDS:
        grp = [r for r in resolved if r.get("band_disp") == name]
        hit = [r for r in grp if r["side"] == "hit"]
        pit = [r for r in grp if r["side"] == "pit"]
        out["bands_display_grade"][name] = {
            "hit": _sf_summ(hit, "ipcw_w"), "pit": _sf_summ(pit, "ipcw_w"),
            "boot": _sf_boot(hit, pit, "ipcw_w")}
    return out


def _sf_resolved_le2018_check(lam):
    """B3 input: on decision folds <= 2018 (first-6yr windows fully elapsed, censoring
    ~absent) the IPCW estimator must preserve the top-25 diff sign AND sit within 1
    bootstrap SE of the unweighted estimate -- i.e. the reweighting machinery must be
    ~identity exactly where there is nothing to reweight."""
    scored, cens_map = [], {}
    for side in ("hit", "pit"):
        data, cens = _sf_pool(side, "full_pool")
        rows = _sf_fwd_chain(data, side, lam[side], (2016, 2017, 2018))
        for yr in sorted({r["year"] for r in rows}):
            _sf_quantile_display([r for r in rows if r["year"] == yr])
        for pk, c in cens.items():
            cens_map[(side, pk)] = c
        scored.extend(rows)
    if not scored:
        return {"evaluable": False,
                "note": "no <=2018 folds pass the >=15/>=60 guards"}
    top = []
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r["disp"])
        top.extend(pool[:25])
    hit = [r for r in top if r["side"] == "hit"]
    pit = [r for r in top if r["side"] == "pit"]
    unw = _sf_boot(hit, pit)
    resolved = _sf_ipcw_weights(scored, cens_map)
    wmap = {(r["side"], r["pk"], r["year"]): r["ipcw_w"] for r in resolved}
    rtop = [dict(r, ipcw_w=wmap[(r["side"], r["pk"], r["year"])]) for r in top
            if (r["side"], r["pk"], r["year"]) in wmap]
    ipw = _sf_boot([r for r in rtop if r["side"] == "hit"],
                   [r for r in rtop if r["side"] == "pit"], "ipcw_w")
    if not (unw and ipw):
        return {"evaluable": False, "fold_years_used": sorted({r["year"] for r in scored}),
                "note": "top-25 too one-sided for a bootstrap on <=2018 folds",
                "unweighted": unw, "ipcw": ipw}
    sign_ok = (unw["mean_diff"] > 0) == (ipw["mean_diff"] > 0)
    within = abs(ipw["mean_diff"] - unw["mean_diff"]) <= unw["mean_se"]
    return {"evaluable": True,
            "fold_years_used": sorted({r["year"] for r in scored}),
            "resolved_share_of_top25": round(len(rtop) / len(top), 3),
            "unweighted": unw, "ipcw": ipw,
            "sign_preserved": bool(sign_ok),
            "within_1se_of_unweighted": bool(within),
            "pass": bool(sign_ok and within)}


def _sf_s3_reference():
    """S3 reference values: the SHIPPED pit BENCH/GOOD bucket log-loss (the
    'logloss_before' line of the E-ISO4 artifact -- the live grade->bucket tables)."""
    try:
        d = json.loads((DATA_DIR / "xfv_grade_recal4_eval.json").read_text(encoding="utf-8"))
        pb = d["results"]["per_side"]["pit"]["per_bucket"]
        return {"bench_logloss": pb["bench"]["logloss_before"],
                "good_logloss": pb["good"]["logloss_before"],
                "source": "data/xfv_grade_recal4_eval.json results.per_side.pit.per_bucket "
                          "logloss_before (the shipped tables)"}
    except Exception:
        return {"bench_logloss": 0.25642, "good_logloss": 0.04971,
                "source": "fallback constants (2026-07 E-ISO4 artifact values)"}


def _side_fairness_eval(persist: bool = True, out_path=None) -> dict:
    """eFV 3.4 F-SIDE: the standing JOINT side-fairness eval line. Builds the
    full-pool-KM primary frame, the debuted-only sensitivity frame and the IPCW
    uncertainty band; stamps binding rules B1-B4 and standing forward gates S1-S5.
    Memoized per process (hit + pit run() calls share one computation). Writes
    data/xfv_side_fairness_eval.json when persist=True (out_path overrides)."""
    art = _SF_CACHE.get("artifact")
    if art is None:
        lam, lam_src = _sf_live_lambdas()
        full, scored_full, cens_full = _sf_frame("full_pool", lam)
        deb, _s, _c = _sf_frame("debuted_only", lam)
        ipcw = _sf_ipcw_frame(scored_full, cens_full)
        b3 = _sf_resolved_le2018_check(lam)
        top = full["joint_bands_display_grade"]["001-025"]
        deb_top = deb["joint_bands_display_grade"]["001-025"]
        pooled_sign = "hit_gt_pit" if top["boot"]["mean_diff"] > 0 else "pit_ge_hit"
        folds = [v for v in full["per_fold_top25_display"].values() if "sign" in v]
        n_agree = sum(1 for v in folds if v["sign"] == pooled_sign)
        binding_rules = {
            "B1_fold_sign_agreement": {
                "rule": ">=3/4 forward-chained folds agree with the pooled sign of the "
                        "joint top-25 hit-minus-pit mean-WAR diff (primary frame)",
                "pooled_sign": pooled_sign, "n_folds": len(folds), "n_agree": n_agree,
                "pass": bool(len(folds) >= 4 and n_agree >= 3)},
            "B2_dual_frame_sign": {
                "rule": "full-pool-KM and debuted-only top-25 mean diffs share a sign",
                "full_pool_mean_diff": top["boot"]["mean_diff"],
                "debuted_only_mean_diff": deb_top["boot"]["mean_diff"],
                "pass": bool((top["boot"]["mean_diff"] > 0)
                             == (deb_top["boot"]["mean_diff"] > 0))},
            "B3_ipcw_identity_where_uncensored": dict(
                {"rule": "IPCW estimate sign-preserving AND within 1 bootstrap SE of "
                         "unweighted on the resolved <=2018 decision folds"}, **b3),
            # CLAUSE SCOPE CORRECTED 2026-08-04. S1 below declares the top-25
            # mean AND median co-primary, and this check tested the MEAN ONLY
            # while stamping median_ci90 into the artifact and never reading it.
            # Its own rule string said "mean-diff CI90", contradicting the
            # declaration two blocks down, so the gate reported pass while one
            # of its two co-primary legs was failing and nothing surfaced it.
            #
            # Measured on the shipped lambdas: mean CI90 [0.81, 6.01] excludes
            # zero, median CI90 [-0.64, 6.53] does NOT. A control run at the OLD
            # lambdas {0.85, 0.54} on the SAME rows also fails the median leg
            # ([-0.07, 6.58]), so this is matrix and label drift over 11 days,
            # NOT the 2026-08-04 pitcher pin. The legs are reported separately so
            # a future failure is attributable instead of hidden behind one flag.
            "B4_ci90_excludes_zero": {
                "rule": "S1 co-primary: top-25 mean-diff AND median-diff CI90 exclude 0",
                "mean_ci90": top["boot"]["mean_ci90"],
                "median_ci90": top["boot"]["median_ci90"],
                "mean_pass": bool(top["boot"]["mean_ci90"][0] * top["boot"]["mean_ci90"][1] > 0),
                "median_pass": bool(top["boot"]["median_ci90"][0] * top["boot"]["median_ci90"][1] > 0),
                "pass": bool(top["boot"]["mean_ci90"][0] * top["boot"]["mean_ci90"][1] > 0
                             and top["boot"]["median_ci90"][0] * top["boot"]["median_ci90"][1] > 0)},
        }
        s3ref = _sf_s3_reference()
        rw = full["joint_bands_rank_war"]
        fv40 = full["equal_consensus_fv"]["40"]
        gates = {
            "S1_top25_no_widening": {
                "rule": "S1: joint TOP-25 hit-minus-pit realized-WAR diff must not "
                        "increase by >1 bootstrap SE (mean AND median co-primary)",
                "frame": "full_pool_km / joint_bands_display_grade / 001-025",
                "baseline_mean_diff": top["boot"]["mean_diff"],
                "baseline_mean_se": top["boot"]["mean_se"],
                "max_allowed_mean_diff": round(top["boot"]["mean_diff"]
                                               + top["boot"]["mean_se"], 2),
                "baseline_median_diff": top["boot"]["median_diff"],
                "baseline_median_se": top["boot"]["median_se"],
                "max_allowed_median_diff": round(top["boot"]["median_diff"]
                                                 + top["boot"]["median_se"], 2)},
            "S2_hit_no_harm": {
                "rule": "S2: hit pooled blend Spearman must stay within 0.0023 of the "
                        "corrected-label baseline",
                "baseline_hit_blend_rho": 0.3808, "floor": 0.3785,
                "source": "docs/efv-2026-07-14/GATES.md corrected-label baselines"},
            "S3_pit_bucket_logloss": {
                "rule": "S3: pit BENCH+GOOD bucket log-loss <= +1.0% relative",
                "reference": s3ref,
                "ceilings": {"bench": round(s3ref["bench_logloss"] * 1.01, 5),
                             "good": round(s3ref["good_logloss"] * 1.01, 5)}},
            "S4_midband_pit_outperformance": {
                "rule": "S4: rank_war-frame mid-band pit-outperformance cells (51-100, "
                        "101-200, equal-FV40) must not flip sign",
                "cells": {
                    "rank_war_051-100_mean_diff": (rw.get("051-100", {}).get("boot") or {}).get("mean_diff"),
                    "rank_war_101-200_mean_diff": (rw.get("101-200", {}).get("boot") or {}).get("mean_diff"),
                    "equal_fv40_mean_diff": (fv40.get("boot") or {}).get("mean_diff")},
                "expected_sign": "negative (pitchers outperform hitters at equal raw "
                                 "mid-board slot / equal FV40)",
                "sign_now_all_negative": bool(all(
                    (v is not None and v < 0) for v in (
                        (rw.get("051-100", {}).get("boot") or {}).get("mean_diff"),
                        (rw.get("101-200", {}).get("boot") or {}).get("mean_diff"),
                        (fv40.get("boot") or {}).get("mean_diff"))))},
            "S5_fold_guards_and_2024_tripwire": {
                "rule": "S5: stamp per-side fold-year counts vs the >=15 test / >=60 "
                        "train guards; the FIRST run where the 2024 decision fold "
                        "becomes trainable must re-run E-ISO4-path, M3 and E-STUFF "
                        "before re-baselining this line",
                "guards": {"min_test": 15, "min_train": 60},
                "fold_counts_full_pool": full["fold_counts_vs_guards"],
                "fold_counts_debuted_only": deb["fold_counts_vs_guards"],
                "first_trainable_2024_fold": {
                    # keyed on the DEBUTED frame: the full-pool 2024 test cell is
                    # currently bust-only (zero debuted rows), so its guard pass is
                    # degenerate -- a tripwire fired on it would cry wolf on day one.
                    "hit_passes_guards": deb["fold_counts_vs_guards"]["hit"]["2024"]["passes_guards"],
                    "pit_passes_guards": deb["fold_counts_vs_guards"]["pit"]["2024"]["passes_guards"],
                    "full_pool_2024_note": "full-pool 2024 cell passes the raw guards "
                                           "on bust rows alone (no debuted rows); the "
                                           "trip condition is the DEBUTED 2024 fold",
                    "tripped": bool(
                        deb["fold_counts_vs_guards"]["hit"]["2024"]["passes_guards"]
                        or deb["fold_counts_vs_guards"]["pit"]["2024"]["passes_guards"]),
                    "re_run_on_trip": ["E-ISO4-path", "M3", "E-STUFF"]}},
        }
        art = {
            "generated_at": date.today().isoformat(),
            "eval_line": "eFV 3.4 F-SIDE -- standing joint side-fairness eval "
                         "(measurement-only; output-neutral)",
            "question": "do pitchers at a given joint-board slot / display grade "
                        "deliver worse realized outcomes than hitters at the same "
                        "slot, and does any future change widen that gap?",
            "protocol": {
                "folds": list(SCORED_YEARS),
                "fold_guards": {"min_test": 15, "min_train": 60},
                "lambdas": lam, "lambda_source": lam_src,
                "display_map": "per-side rank-preserving quantile map of rank_war onto "
                               "the side's consensus-FV distribution, replicated within "
                               "each fold-year test pool. LABEL CORRECTED 2026-08-04: this "
                               "is the analogue of xfv_grade_display, which was RETIRED as "
                               "the served display on 2026-07-25 and now serves only as the "
                               "SURPLUS-PRICING basis. It is not the served board grade.",
                "joint_board": "both sides unioned; ranked by the quantile map above (the "
                               "surplus-pricing basis, formerly the display) and by raw "
                               "rank_war WAR units (calibration-honest). NOTE: the served "
                               "board grade is raw xfv_grade "
                               "(storage.BOARD_GRADE_FIELD), so neither leg is a direct "
                               "read on served board order; re-basing this eval is a gate "
                               "decision, recorded here rather than done silently.",
                "war_metric": "first-6yr summed bWAR, KM-censored (target_censored)",
                "bootstrap": {"reps": _SF_BOOT, "seed": _SF_SEED, "ci": "CI90"},
                "outcome_thresholds": {"contributor": _CONTRIB_WAR, "star": _STAR_WAR,
                                       "bust": _SF_BUST_WAR},
                "provenance": "2026-07 side_fairness prototype verbatim; headline "
                              "top-25 +3.95 CI90 [1.55, 6.35] reproduced"},
            "primary_frame": "full_pool_km",
            "frames": {"full_pool_km": full,
                       "debuted_only_sensitivity": deb,
                       "ipcw_resolved_reweighted": ipcw},
            "binding_rules": binding_rules,
            "binding_grade_cell": {
                "binding": "equal display grade >= 55 (grade >= 52.5 on the "
                           "round-to-nearest eFV scale; cell '55_plus_binding')",
                "value": full["equal_display_grade"]["55_plus_binding"],
                "diagnostic_50_band": dict(
                    full["equal_display_grade"]["50"], never_a_gate=True,
                    note="the 50-band model-vs-realized discrepancy is a TRACKED "
                         "DIAGNOSTIC, never a gate (pre-registered)")},
            "standing_gates": gates,
            "output_neutrality": {
                "claim": "measurement-only: no scorer/producer/payload writer touched; "
                         "every published player number (data/xfv.json payloads) is "
                         "byte-identical",
                "writes": ["data/" + _SF_OUT,
                           "side_fairness summary block in data/xfv_eval.json + "
                           "data/xfv_eval_pitcher.json"]},
        }
        _SF_CACHE["artifact"] = art
    if persist:
        p = Path(out_path) if out_path else (DATA_DIR / _SF_OUT)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(art, indent=1), encoding="utf-8")
        log.info("wrote %s", p)
    return art


def _side_fairness_summary() -> dict:
    """Compact side_fairness block embedded in BOTH xfv_eval.json and
    xfv_eval_pitcher.json (identical -- the eval is joint by construction)."""
    art = _side_fairness_eval(persist=False)
    full = art["frames"]["full_pool_km"]
    top = full["joint_bands_display_grade"]["001-025"]
    return {
        "eval_line": "eFV 3.4 F-SIDE joint side-fairness (measurement-only; standing)",
        "artifact": "data/" + _SF_OUT,
        "primary_frame": "full_pool_km, joint display-grade board, folds "
                         + "-".join(str(y) for y in (SCORED_YEARS[0], SCORED_YEARS[-1])),
        "top25_hit_minus_pit": top["boot"],
        "top25_pit_share": {"display_frame": top["pit_share"],
                            "rank_war_frame": top["pit_share_rank_war_frame"],
                            "share_inflation": top["share_inflation_display_vs_raw"]},
        "binding_rules_pass": {k: v.get("pass")
                               for k, v in art["binding_rules"].items()},
        "standing_gates": sorted(art["standing_gates"].keys()),
        "note": "identical block on both sides; full tables + gate baselines live "
                "in the artifact",
    }


def _era_split(deb_data, keys, lam):
    """Honest record of the 'scouting got more accurate over time' question: forward-chained
    consensus vs shipped-blend rank by debut era. If eFV's edge lived only in old cohorts it
    would not transfer to today; this shows whether it holds on RECENT cohorts."""
    eras = {"<=2018": [], "2019-2021": [], "2022-2023": []}
    cons = {k: [] for k in eras}
    blend = {k: [] for k in eras}
    for yr in range(2016, 2024):
        train = [r for r in deb_data if r["decision_year"] < yr]
        test = [r for r in deb_data if r["decision_year"] == yr]
        if len(train) < 60 or len(test) < 10:
            continue
        ols = _fit_ols_fv(train)
        ridge = _fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        bucket = "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")
        for r in test:
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            cons[bucket].append((cw, r["target"]))
            blend[bucket].append(((1 - lam) * cw + lam * _predict(ridge, r["feats"]), r["target"]))
    out = {}
    for k in eras:
        if len(cons[k]) >= 15:
            out[k] = {"n": len(cons[k]),
                      "consensus_spearman": _spearman([a for a, _ in cons[k]], [b for _, b in cons[k]]),
                      "xfv_blend_spearman": _spearman([a for a, _ in blend[k]], [b for _, b in blend[k]])}
    return out


def run(persist: bool = True, side: str = "hit") -> dict:
    from efv_dataset import matrix_path
    keys, mono = _feature_spec(side)
    wag_cal = wag_calibration(side)
    lam = blend_lambda(side)   # WAG when it has signal; rank-gate fallback when WAG is noise
    # also_at=(lam,) so the artifact can quote the composite at the lambda that ACTUALLY
    # SHIPS. The selector's own argmax is reported separately: with both sides pinned via
    # _BLEND_LAMBDA_RESELECT the two are routinely different (2026-08-03 hit: shipped 0.70,
    # selector 0.50).
    rank_cal = rank_calibration(side, also_at=(lam,))
    lam_selector = ("wag" if abs(wag_cal.get("spearman") or 0) >= _WAG_MIN_SPEARMAN
                    and (wag_cal.get("n") or 0) >= _WAG_MIN_N else "rank_gate")
    lam_pin = _BLEND_LAMBDA_RESELECT.get(side)
    # "source" answers WHERE THE SERVED NUMBER CAME FROM, which is the pin whenever one is
    # set; lam_selector is only which calibrator would have been consulted without it.
    lam_source = "pinned_reselect" if lam_pin is not None else lam_selector
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in rows if r["kind"] == "debuted"]
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]

    deb_km = _prep(deb, "target_censored", side)
    cohort_map = _cohort_map(full)   # covers debuted + busts so both AUC pools get real cohorts
    evals = {
        "debuted_km": _run_eval(deb_km, "debuted, KM-censored target", keys, mono, lam),
        "debuted_resolved": _run_eval(_prep([r for r in deb if not r["censored"]],
                                            "target_resolved", side), "debuted, resolved-only (sensitivity)", keys, mono, lam),
        "full_pool_km": _run_eval(_prep(full, "target_censored", side),
                                  "full pool (debuted+busts), KM target [decision-year proxy]", keys, mono, lam),
    }
    # M1 AUC instrumentation: per-cohort / per-era / per-FV-tier contributor + star AUC,
    # model (blend) vs consensus, on the same forward-chained debuted-KM folds.
    evals["debuted_km"]["auc_breakdown"] = _auc_breakdown(deb_km, keys, lam, cohort_map)
    evals["full_pool_km"]["auc_breakdown"] = _auc_breakdown(
        _prep(full, "target_censored", side), keys, lam, cohort_map)
    out = {
        "generated_at": date.today().isoformat(),
        "model": f"eFV {'pitcher' if side == 'pit' else 'hitter'} v1 (lean + guarded blend)",
        "scope": "PITCHERS" if side == "pit" else "HITTERS",
        "conventions": {
            "target": "first-6-season summed bWAR; KM-censored (rate-projected tail) + resolved sensitivity",
            "vintage": "features strictly pre-outcome (Pass-1 matrix; leakage verified 0)",
            "protocol": "forward-chained by decision-year cohort; pooled OOS",
            "baseline": "within-fold OLS WAR ~ consensus_fv_raw (THE bar)",
            "shipped_model": f"'blend' = (1-{lam})*consensus_OLS + {lam}*lean-ridge; this is the "
                             "headline RANK driver. 'ridge' = the pure lean model.",
            "rank_gate": "beat consensus FV on pooled-OOS Spearman (the flagship criterion)",
            "features": keys,
        },
        "lambda_calibration": {
            "shipped_lambda": lam,
            "source": lam_source,
            "shipped_lambda_provenance": {
                # shipped_lambda IS the live blend_lambda(side) recomputed at eval time
                # (no stale copy) -- this block records the decisive values so the
                # bookkeeping is self-contained and cannot silently desync from the
                # export's lambda again.
                "live_blend_lambda": blend_lambda(side),
                "matches_shipped_lambda": abs(lam - blend_lambda(side)) < 1e-9,
                "source": lam_source,
                "pinned_lambda": lam_pin,
                "selector": lam_selector,
                "rank_gate_band": rank_cal.get("band"),
                # BOOKKEEPING FIX 2026-08-04. This key used to be filled from
                # rank_cal["rho"/"within_tier_wm"/"t45"], which are the components at the
                # lambda the SELECTOR chose -- not at the lambda that shipped. It was
                # harmless only while the two coincided. On the 2026-08-03 hitter run the
                # selector chose 0.50 while _BLEND_LAMBDA_RESELECT pins the served value at
                # 0.70, so a key asserting "at shipped" carried 0.50's numbers (rho 0.3851 /
                # wm 0.2456 / t45 0.3334) instead of 0.70's (0.3882 / 0.2349 / 0.2777).
                # Now: composite_at_shipped is evaluated AT shipped_lambda, and the
                # selector's own argmax keeps its own key. Selection logic unchanged.
                "composite_at_shipped": dict(
                    (rank_cal.get("composite_at") or {}).get(_lam_key(lam))
                    or {"lambda": lam, "pooled_rho": None, "within_tier_wm": None,
                        "t45": None, "composite_sum": None}),
                "composite_at_selected": {
                    "selected_lambda": rank_cal.get("lambda"),
                    "pooled_rho": rank_cal.get("rho"),
                    "within_tier_wm": rank_cal.get("within_tier_wm"),
                    "t45": rank_cal.get("t45"),
                    "composite_sum": (round((rank_cal.get("rho") or 0)
                                            + (rank_cal.get("within_tier_wm") or 0)
                                            + (rank_cal.get("t45") or 0), 4)
                                      if rank_cal.get("rho") is not None else None),
                },
                "shipped_equals_selected": (rank_cal.get("lambda") is not None
                                            and abs(lam - rank_cal["lambda"]) < 1e-9),
                "note": "rank_calibration selects lambda in rank_gate_band by argmax of "
                        "pooled + within-tier + FV45-fringe Spearman. composite_at_shipped "
                        "= those decisive components recomputed AT shipped_lambda (the value "
                        "actually served); composite_at_selected = the same components at the "
                        "selector's own argmax. They differ whenever a _BLEND_LAMBDA_RESELECT "
                        "pin overrides the selector, which is the live case on both sides.",
            },
            "wag": wag_cal,
            "rank_gate": rank_cal,
            "reading": "eFV still predicts WAR; the blend lambda is HOW MUCH to trust eFV's "
                       "adjustment over the consensus anchor. WAG (realized over/underperformance "
                       "vs consensus FV = where consensus MISSED) sets lambda ONLY when its "
                       "predicted-edge -> realized-WAG regression is SIGNIFICANT. As of the 2026 "
                       "norm-fix that regression is non-significant on BOTH sides (pitchers spearman "
                       "~0.001, hitters ~0.066, both bootstrap CIs straddle 0), so a WAG-sized lambda "
                       "would be noise pinning a rank-suboptimal weight. Both sides therefore "
                       "defer to the RANK GATE (rank_calibration): pooled + within-tier + "
                       "FV45-fringe rank rho maximized in a conservative band, which lifts the "
                       "pooled OOS rank rho vs the old WAG-pinned lambda (the robust, "
                       "CI-positive part of the available gain). AS SERVED both sides are then "
                       "PINNED inside that band (hit 0.70, pit 0.57 as of 2026-08-04) rather "
                       "than re-selected on every matrix rebuild: the composite curve is flat "
                       "within the band's own noise floor (pooled-rho spread 0.16x the pitcher "
                       "MDE95, 0.21x the hitter MDE95) so the argmax is not resolvable, while "
                       "the run-to-run grade churn it caused is. The pins are STABILITY "
                       "decisions, not accuracy claims - see composite_at_shipped vs "
                       "composite_at_selected for what each costs on this vintage.",
        },
        "era_split_debuted": _era_split(_prep(deb, "target_censored", side), keys, lam),
        "evals": evals,
        "feature_diagnostics_full_window": _importances(_prep(deb, "target_censored", side), keys, mono),
    }
    # Two-metric gate, second leg. Joint by construction, so it must never block the
    # per-side artifact: fail soft and record why, same contract as side_fairness.
    try:
        out["block_rho"] = block_rho_eval()
    except Exception as exc:
        log.warning("block-rho leg unavailable: %s", exc)
        out["block_rho"] = {"error": f"block-rho unavailable: {exc}"}
    out["honest_note"] = _honest_note(
        out["evals"], out["era_split_debuted"],
        out["block_rho"] if "error" not in out["block_rho"] else None, side)
    # eFV 3.4 F-SIDE: joint side-fairness line (measurement-only; identical compact
    # block on both sides -- the full tables live in data/xfv_side_fairness_eval.json).
    # The line must never block the per-side eval artifact: fail soft, record why.
    try:
        out["side_fairness"] = _side_fairness_summary()
        if persist:
            _side_fairness_eval(persist=True)   # memoized; writes the joint artifact
    except Exception as exc:
        log.warning("F-SIDE side-fairness eval unavailable: %s", exc)
        out["side_fairness"] = {"error": f"side-fairness eval unavailable: {exc}"}
    if persist:
        out_path = OUT_PATH if side == "hit" else (DATA_DIR / "xfv_eval_pitcher.json")
        out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", out_path)
    return out


def _fmt(s):
    return f"n={s.get('n',0):4d} mae={s.get('mae')} rho={s.get('spearman')}"


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run(side="pit" if "--pit" in sys.argv else "hit")
    for ek, ev in rep["evals"].items():
        print(f"\n=== {ek}: {ev['label']} ===")
        for m, s in ev["pooled_oos"].items():
            if s.get("n"):
                print(f"  {m:10s} {_fmt(s)}")
        print("  verdict vs consensus:", json.dumps(ev["verdict_vs_consensus"]))
    print("\nfeature diagnostics (full-window, interpretation only):")
    print("  ridge std weights:", json.dumps(rep["feature_diagnostics_full_window"].get("ridge_std_weights", {})))
    print("  lgbm gain share:  ", json.dumps(rep["feature_diagnostics_full_window"].get("lgbm_gain_share", {})))
    sf = rep.get("side_fairness") or {}
    if sf.get("top25_hit_minus_pit"):
        print("\nF-SIDE joint top-25 hit-minus-pit (full-pool KM):",
              json.dumps(sf["top25_hit_minus_pit"]))
        print("  binding rules pass:", json.dumps(sf["binding_rules_pass"]))
