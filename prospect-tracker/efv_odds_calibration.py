# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eFV OUTCOME-ODDS DISPERSION CALIBRATION (the ODDS lane, 2026-07-25).

WIRED AND LIVE at all three efv_score scoring seams: run() resolved
(efv_score.py:1292), run_live() (efv_score.py:1812) and run_backgrade()
(efv_score.py:2191). Importing this module alone still changes nothing - the
seams call recalibrate_bucket() explicitly - but the served numbers DO go
through this map, so a change here moves p_bust/p_bucket on the board.

(This header read "NOT YET WIRED IN. Inert until the efv_score.py hunks in
tools/_prem_odds.patch are applied" until 2026-08-03. The hunks were applied
on 2026-07-31 and the header was never updated, which is the kind of stale
disclaimer that makes a live calibration look safe to edit.)

THE DEFECT
----------
Served p_bust is vf.p_bucket_given_fv(xfv_grade, is_pitcher)[bust]. That curve was
fitted over the Clemens published-list population and is keyed on CONSENSUS FV, whose
standard deviation on the served-comparable pool is 6.57 FV. Production reads it at
xfv_grade = vf.realized_implied_fv(...), a WAR-inversion grade whose standard deviation
on the SAME rows is 15.54 FV, i.e. 2.37x wider. Reading a probability curve at 2.4x the
dispersion it was fitted for returns log-odds that are far too steep.

That is exactly the measured reliability signature on the out-of-fold, fully-resolved
frame (decision years 2014-2020, 7 forward-chained folds, served-comparable rows only):

    served p_bust bin      n     served    observed   CI95 of observed
    0.00-0.09             64     0.0356    0.2656     [0.1730, 0.3848]
    0.09-0.22             65     0.1445    0.5077     [0.3892, 0.6254]
    0.22-0.38             64     0.3065    0.6094     [0.4869, 0.7194]
    0.38-0.50             65     0.4411    0.7077     [0.5880, 0.8042]
    0.50-0.74             64     0.6261    0.7969     [0.6829, 0.8773]
    0.75-0.95             65     0.8677    0.8615     [0.7573, 0.9254]
    0.96-0.98             64     0.9818    0.8438     [0.7357, 0.9129]
    0.98-0.99             65     0.9867    0.8615     [0.7573, 0.9254]

Too low at the bottom, too high at the top: an over-sharp curve, not a shifted one.
The independently fitted correction slope recovers the same number the dispersion ratio
predicts: b = 0.37, i.e. 1/b = 2.7x too steep.

THE CORRECTION
--------------
A single monotone Platt map in log-odds, per side:

    logit(p') = A + B * logit(p)

Because it is STRICTLY MONOTONE it preserves RESOLUTION EXACTLY (0.03201 -> 0.03201 on
the frame under one global transform) and cannot reorder anything: no rank, no grade,
no dollar figure moves. Reliability falls 0.05469 -> 0.02627 under the global map, and
out of fold under the forward chain the full paired-bootstrap gate is:

    incumbent - recalibrated   Brier    +0.03953  CI95 [+0.01655, +0.05934]  P(>0)=1.000
    incumbent - recalibrated   logloss  +0.15546  CI95 [+0.07339, +0.22676]  P(>0)=0.994
    incumbent - recalibrated   reliab   +0.04297  CI95 [+0.02149, +0.06125]  P(>0)=1.000

WHAT WAS RULED OUT FIRST (all measured, none asserted)
------------------------------------------------------
* CONDITIONING on level / age / production is a NULL. A head adding those three columns
  on top of this recalibration is indistinguishable from its own ROW-PERMUTED twin
  (CTRL - R2 Brier +0.00522, CI95 [-0.02548, +0.03172], P(>0)=0.654) and its gain sits
  INSIDE the label-permutation null band (observed +0.00439 vs null p95 +0.01467).
  The conditional surface the complaint pointed at does not exist.
* A MEAN-PRESERVING slope-only variant, which would have avoided the population-level
  term, FAILS: it is worse than the incumbent on Brier (P(>0)=0.250) and does not
  improve reliability (P(>0)=0.386). Compressing toward a wrong centre makes it worse,
  so the level and slope terms are not separable and A is carried with B.
* TRACK-RECORD COMPOSITION is not the driver: the gap is +0.133 on rows with a MiLB
  track record and +0.158 on rows without, i.e. essentially the same.
* The "bust bucket is pinned at 0 surplus so negative outcomes get probability zero"
  defect is real but belongs to the SURPLUS FAN, not to p_bust: 162 of 162 (100%)
  served-comparable rows with negative first-6yr WAR already fall INSIDE the bust band.

SCOPE LIMIT
-----------
Applies ONLY where p_bust is read at the eFV realized-implied grade (efv_score's three
scoring seams). It must NOT be applied to:
  * efv_ungraded PROVISIONAL rows -- data/xfv_thin_pbust_eval.json owns those and
    already replaces p_bust there; stacking would undo that lane's fix.
  * p_bust read at a CONSENSUS FV grade (trade machine, /projections/, FA). On its
    native key the same curve shows a nearly FLAT +0.11 to +0.17 gap across every
    consensus band, i.e. a level error and no slope error, so this slope map is the
    wrong instrument there.

Lab + gates: tools/_prem_odds*.py, data/xfv_odds_dispersion_eval.json.
"""
from __future__ import annotations

import math

# Forward-chained Platt fits on the served-comparable, fully-resolved frame
# (n=516; hitters 244, pitchers 272).
#
# RE-MEASURED 2026-08-03 on the current tree, and the old note here was wrong.
# It read "per-fold slope stability: 0.470 / 0.392 / 0.289 / 0.276 as the
# training window grows -- monotonically DOWNWARD, so these full-frame values
# are the CONSERVATIVE end of the measured range". A monotone trend in a fixed
# constant would be a re-fit trigger, so it was worth checking. It is not one.
# Cumulative slope by training window on the served frame (tools/
# odds_grade_basis_lab: score_chain -> irls_logit on logit(p_inc)):
#
#     through   hit n    hit slope     pit n    pit slope
#     2017         44       0.6526        39       0.4163
#     2018         81       0.2627        85       0.3139
#     2019        163       0.2910       164       0.2598
#     2020        244       0.3750       272       0.3602
#
# Neither side is monotone: both dip in the small-n middle and come back. The
# intermediate points are noise-dominated (n=44 to n=163), and the full-frame
# fit REPRODUCES THE SHIPPED CONSTANTS (hit 0.3750 vs 0.3749 shipped; pit
# 0.3602 vs 0.3553, a 1.4% gap). So these are the converged values, not a
# conservative end of a drifting range, and no re-fit is warranted.
#
# A re-fit was also tested end to end and does NOT clear the pre-registered
# ship gate: tools/odds_recalibration_ship_lab has the per-fold refit beating
# the incumbent on Brier and log loss with the CI excluding zero, but failing
# to beat a flat base-rate constant, which the gate requires
# (data/xfv_odds_recalibration_ship_eval.json, SHIP false).
_PLATT = {
    "hit": (0.7268, 0.3749),
    "pit": (0.7269, 0.3553),
}
_EPS = 1e-4


def recalibrate_p_bust(p_bust, is_pitcher: bool):
    """Map a served p_bust through the dispersion correction. Monotone; identity
    on None / non-finite / out-of-range input."""
    if p_bust is None:
        return None
    try:
        p = float(p_bust)
    except (TypeError, ValueError):
        return p_bust
    if not math.isfinite(p):
        return p_bust
    p = min(max(p, _EPS), 1.0 - _EPS)
    a, b = _PLATT["pit" if is_pitcher else "hit"]
    z = a + b * math.log(p / (1.0 - p))
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


def recalibrate_bucket(probs, is_pitcher: bool, *, provisional: bool = False):
    """Recalibrate the BUST mass of a 5-vector [bust, bench, regular, good, star] and
    rescale the four non-bust buckets proportionally so the vector still sums to 1.

    Mirrors the convention efv_ungraded.thin_sample_p_bust already uses (replace the
    bust mass, renormalize the remainder), so the two lanes describe p_bucket the same
    way. `provisional=True` is a hard no-op: those rows belong to the thin-sample lane.
    """
    if provisional or not probs or len(probs) != 5:
        return probs
    old = float(probs[0])
    new = recalibrate_p_bust(old, is_pitcher)
    if new is None:
        return probs
    rest = 1.0 - old
    if rest <= 1e-9:
        return [new] + [(1.0 - new) / 4.0] * 4
    scale = (1.0 - new) / rest
    return [new] + [float(p) * scale for p in probs[1:]]
