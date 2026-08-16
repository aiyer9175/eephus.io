# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""dynasty_blend.py - THE dynasty talent composite. One copy, two consumers.

WHY THIS MODULE EXISTS (2026-08-16). fantasy_export._dynasty_prospects and
card_market_export.talent_score each carried a private copy of this arithmetic.
The card copy was introduced as a "structural clone, same weights, same inputs"
of the fantasy blend, and then the two silently diverged: fantasy decayed ETA
proximity at 0.18 per year while cards decayed it at 0.25, so the same prospect
carried two different talent composites on two surfaces. Nothing caught it,
because the card module's parity test hand-computed its expectation FROM THE
CLONE'S OWN CONSTANTS, which pinned the clone against itself rather than
against the fantasy blend it claimed to mirror. A comment promising two files
agree is not a mechanism; a shared import is. Both modules now route every leg
of the blend through here, and the cross-module test asserts they hold the
IDENTICAL function objects.

Stdlib only, by design: importing this can never fail and never drags
fa_projection, the scrapers, or any other fat module onto a cheap path, so
neither consumer needs a fallback shim (a shim is where the last clone hid).

SCOPE. This is a DISPLAY-LAYER composite, a ranking aid like the client's
scoring re-rank. It moves no served eFV number, feeds no model, and triggers
no model gate. The grade passed to blend_score is the caller's business; both
consumers pass THE board grade (fantasy_export._board_grade) as of 2026-08-16.
"""
from __future__ import annotations

# Blend weights. The grade term carries weight 1 implicitly: the composite is
# the grade nudged by the other legs, not a rescaling of it.
W_STAR = 10.0        # ceiling premium per unit P(star)
W_BUST = -6.0        # floor risk per unit P(bust); negative, so it subtracts
W_ETA = 4.0          # per unit ETA proximity (sooner arrival = value sooner)
W_SURPLUS = 2.0      # small tiebreak per unit normalized surplus

# ETA proximity: 1.0 for an ETA this season, ETA_DECAY less per year out,
# floored at 0. An unknown ETA gets the flat ETA_UNKNOWN credit.
ETA_DECAY = 0.18
ETA_UNKNOWN = 0.4


def eta_proximity(eta_year, season) -> float:
    """Proximity credit in [0, 1] for an ETA year against the current season.
    A falsy eta_year (None, 0) means no published ETA and earns ETA_UNKNOWN."""
    if not eta_year:
        return ETA_UNKNOWN
    return max(0.0, 1.0 - ETA_DECAY * max(0, int(eta_year) - int(season)))


def surplus_norm(surplus_mm) -> float:
    """Surplus $M onto the blend's tiebreak axis: clamp(surplus / 100) into
    [-0.5, 1.5]. None reads as 0.0 (no surplus opinion, no nudge)."""
    return max(-0.5, min(1.5, float(surplus_mm or 0.0) / 100.0))


def blend_score(grade, star, bust, eta_prox, surplus_norm_v) -> float:
    """The composite: grade primary, star odds add a ceiling premium, bust risk
    subtracts, a nearer ETA adds, surplus breaks ties. `eta_prox` and
    `surplus_norm_v` are the already-transformed legs from eta_proximity and
    surplus_norm, so a caller cannot half-route through this module."""
    return (float(grade)
            + W_STAR * float(star or 0.0)
            + W_BUST * float(bust or 0.0)
            + W_ETA * float(eta_prox)
            + W_SURPLUS * float(surplus_norm_v))
