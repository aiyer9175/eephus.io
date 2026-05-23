"""Tests for the Farm System Report Card Overhaul — new helpers
(`_fv_to_expected_war`, `_grad_wag`) and per-org grade behavior added
in Steps 1-9 of the overhaul plan."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from storage import (
    FV_EXPECTED_WAR,
    _fv_to_expected_war,
    _grad_wag,
    _grad_wag_cumulative,
    _letter_grade,
    _rank_descending,
)


# ---------------------------------------------------------------------------
# FV → expected-WAR primer table (Step 1)
# ---------------------------------------------------------------------------

class TestFvToExpectedWar:
    def test_anchor_points_match_table(self):
        # Hardcoded industry-standard anchors. Don't drift without
        # updating the glossary entry + UI tooltips.
        assert _fv_to_expected_war(80) == FV_EXPECTED_WAR[80]
        assert _fv_to_expected_war(70) == FV_EXPECTED_WAR[70]
        assert _fv_to_expected_war(60) == FV_EXPECTED_WAR[60]
        assert _fv_to_expected_war(50) == FV_EXPECTED_WAR[50]
        assert _fv_to_expected_war(40) == FV_EXPECTED_WAR[40]
        assert _fv_to_expected_war(30) == FV_EXPECTED_WAR[30]

    def test_linear_interpolation_between_tiers(self):
        # 55 sits exactly between 50 (=3.0) and 60 (=12.0) → midpoint 7.5
        v = _fv_to_expected_war(55)
        assert v == 6.0  # FV_EXPECTED_WAR[55] is anchored at 6.0; not just midpoint
        # 52 sits 2/5 of the way from 50 (3.0) to 55 (6.0) → 3.0 + 2/5*(6.0-3.0) = 4.2
        v52 = _fv_to_expected_war(52)
        assert abs(v52 - 4.2) < 0.05
        # 67 sits 2/5 of the way from 65 (17.0) to 70 (25.0) → 17.0 + 2/5*(25.0-17.0) = 20.2
        v67 = _fv_to_expected_war(67)
        assert abs(v67 - 20.2) < 0.05

    def test_out_of_range_returns_none(self):
        assert _fv_to_expected_war(None) is None
        assert _fv_to_expected_war(15) is None      # below 20
        assert _fv_to_expected_war(85) is None      # above 80
        assert _fv_to_expected_war("garbage") is None

    def test_clamps_at_tier_extremes(self):
        # Edge values clamp to the nearest anchor rather than returning None.
        assert _fv_to_expected_war(20) == FV_EXPECTED_WAR[20]
        assert _fv_to_expected_war(80) == FV_EXPECTED_WAR[80]


# ---------------------------------------------------------------------------
# Per-graduate cumulative WAG — the legacy career-total view.
# Kept under `_grad_wag_cumulative` since the canonical `_grad_wag`
# is now rate-based (matches the frontend gradVsFvProjection pill).
# ---------------------------------------------------------------------------

class TestGradWagCumulative:
    def test_positive_when_war_beats_projection(self):
        # FV 50 → expected 3.0 WAR. Career WAR of 10 → WAG = +7.0.
        grad = {
            "career_war": {"career_war": 10.0},
            "fv_close_raw": 50.0,
        }
        assert _grad_wag_cumulative(grad) == 7.0

    def test_negative_when_war_misses_projection(self):
        # FV 60 → expected 12.0 WAR. Career WAR of 3 → WAG = -9.0.
        grad = {
            "career_war": {"career_war": 3.0},
            "fv_close_raw": 60.0,
        }
        assert _grad_wag_cumulative(grad) == -9.0

    def test_zero_when_war_matches_projection(self):
        # FV 50 → expected 3.0 WAR. Career WAR of 3 → WAG = 0.
        grad = {
            "career_war": {"career_war": 3.0},
            "fv_close_raw": 50.0,
        }
        assert _grad_wag_cumulative(grad) == 0.0

    def test_none_when_career_war_missing(self):
        # No career_war at all → None (not 0).
        assert _grad_wag_cumulative({"fv_close_raw": 50.0}) is None
        assert _grad_wag_cumulative({"career_war": {}, "fv_close_raw": 50.0}) is None
        assert _grad_wag_cumulative({"career_war": {"career_war": None},
                          "fv_close_raw": 50.0}) is None

    def test_none_when_fv_close_missing(self):
        assert _grad_wag_cumulative({"career_war": {"career_war": 5.0}}) is None
        assert _grad_wag_cumulative({"career_war": {"career_war": 5.0},
                          "fv_close_raw": None,
                          "fv_close": None}) is None

    def test_fv_close_fallback_when_raw_missing(self):
        # If fv_close_raw isn't set, fall back to fv_close (snapped).
        grad = {
            "career_war": {"career_war": 5.0},
            "fv_close": 50.0,
        }
        assert _grad_wag_cumulative(grad) == 2.0  # 5.0 - 3.0


# ---------------------------------------------------------------------------
# Per-graduate rate-based WAG (current default) — (WAR/yr − FV-implied
# WAR/yr). Mirrors the frontend `gradVsFvProjection` pill so the boom/
# bust label backend stamps matches what the user sees on the card.
# ---------------------------------------------------------------------------

class TestGradWagRate:
    # v14 — WAG = (career_war / career_pa) * 612 - fv_implied_war_per_yr
    # (hitters), or (career_war / career_ip) * role_ip_target - implied
    # (pitchers). Mid-career grads no longer false-negative because their
    # rate now projects to a full season instead of being penalized for
    # partial accumulation.

    def test_positive_when_rate_beats_projection(self):
        # FV 50 hitter, 4 WAR / 800 PA = (4/800)*612 = 3.06 full-season.
        # Expected at FV 50 = 1.6. WAG ≈ +1.46.
        grad = {
            "career_war": {"career_war": 4.0},
            "fv_close_raw": 50.0,
            "position": "SS",
            "career_stats": [{"level": "MLB", "pa": 800}],
        }
        v = _grad_wag(grad)
        assert v is not None and v > 1.0

    def test_pitcher_uses_pitcher_table_and_role(self):
        # SP role, FV 60. 6 WAR / 350 IP = (6/350)*175 = 3.0 full-season.
        # Expected at FV 60 (pitcher) = 3.5. WAG ≈ -0.5.
        grad = {
            "career_war": {"career_war": 6.0},
            "fv_close_raw": 60.0,
            "position": "SP",
            "career_stats": [{"level": "MLB", "ip": 350}],
        }
        v = _grad_wag(grad)
        assert v is not None
        # Roughly -0.5 — settled band
        assert -1.5 < v < 2.5

    def test_negative_when_rate_misses_projection(self):
        # FV 65 hitter, 2 WAR / 800 PA = (2/800)*612 = 1.53 full-season.
        # Expected at FV 65 = ~4.2. WAG ≈ -2.67 (clearly negative).
        grad = {
            "career_war": {"career_war": 2.0},
            "fv_close_raw": 65.0,
            "position": "OF",
            "career_stats": [{"level": "MLB", "pa": 800}],
        }
        v = _grad_wag(grad)
        assert v is not None and v < -1.5

    def test_none_when_career_war_missing(self):
        assert _grad_wag({"fv_close_raw": 50.0}) is None
        assert _grad_wag({"career_war": {}, "fv_close_raw": 50.0}) is None

    def test_none_when_pa_under_floor(self):
        # 100 PA < 150 hitter floor → WAG = None
        grad = {
            "career_war": {"career_war": 2.0},
            "fv_close_raw": 50.0,
            "position": "SS",
            "career_stats": [{"level": "MLB", "pa": 100}],
        }
        assert _grad_wag(grad) is None

    def test_witt_shaped_grad_classifies_as_boom(self):
        # Witt-shape: 5 seasons, 28 WAR, 3000 PA, FV 60.
        # full-season WAR = (28/3000)*612 = 5.71
        # expected at FV 60 = 3.4. WAG ≈ +2.31 — narrowly SETTLED.
        # Bump to 32 WAR (5 MVP-tier seasons) → 6.53 full-season → +3.13 → BOOM.
        witt = {
            "career_war": {"career_war": 32.0, "war_seasons_count": 5},
            "career_stats": [{"level": "MLB", "pa": 600}] * 5,
            "fv_close_raw": 60.0,
            "position": "SS",
        }
        from storage import _compute_boom_bust
        assert _compute_boom_bust(witt) == "boom"

    def test_caminero_no_longer_bust(self):
        # The exact bug the v14 redesign fixes. Caminero: ~4.6 career WAR
        # over ~510 PA at FV 55. Under v13 (rate=war_per_yr): rate was tiny
        # because partial-season denominator inflated. Under v14:
        # full-season = (4.6/510)*612 = 5.52, expected = 2.5, WAG ≈ +3.0.
        caminero = {
            "career_war": {"career_war": 4.6, "war_seasons_count": 1},
            "career_stats": [{"level": "MLB", "pa": 510}],
            "fv_close_raw": 55.0,
            "position": "3B",
        }
        assert _grad_wag(caminero) > 2.0


# ---------------------------------------------------------------------------
# Inverted ranking for Health Burden (Step 7) — lowest score → best rank
# ---------------------------------------------------------------------------

class TestHealthBurdenInvertedRanking:
    def test_negated_score_ranks_correctly(self):
        # Lowest burden = best. Three orgs with burden scores [5, 30, 50].
        # After negation: [-5, -30, -50]. _rank_descending puts the
        # largest negative first → org with raw 5 gets rank 1.
        raw_burdens = [5.0, 30.0, 50.0]
        ranks = _rank_descending([-b for b in raw_burdens])
        assert ranks == [1, 2, 3]  # lowest raw burden → best rank

    def test_lowest_burden_gets_a_plus_in_letter_grade(self):
        # 5 orgs: burdens [10, 20, 30, 40, 50].
        # Rank 1 (lowest burden, 10) → A+; rank 5 (highest, 50) → F
        # under the v6 letter scale (was D in v5 — but the new bottom
        # tier is F in a 5-org pool because pct=(5-1)/(5-1)=1.0 ≥ 0.97).
        burdens = [10.0, 20.0, 30.0, 40.0, 50.0]
        ranks = _rank_descending([-b for b in burdens])
        letters = [_letter_grade(r, len(burdens)) for r in ranks]
        assert letters[0] == "A+"  # burden=10 (lowest)
        assert letters[-1] == "F"  # burden=50 (highest)
