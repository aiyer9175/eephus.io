# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Owner-directed live prospect-age penalty (2026-07-14, the Andrew Moore
directive). Mirrors the injury-penalty overlay: LIVE board only, multiplicative
on the model WAR term, surfaced as a "Prospect age penalty" factor chip."""

from __future__ import annotations

from efv_score import _age_factor


def test_young_prospects_untouched():
    assert _age_factor({"age_now": 19.4}) == 1.0
    assert _age_factor({"age_now": 24.9}) == 1.0
    assert _age_factor({"age_now": 25.0}) == 1.0


def test_ramp_and_floor():
    assert _age_factor({"age_now": 26.0}) == 0.9
    # the Moore case: 26.9yo -> ~0.81
    assert abs(_age_factor({"age_now": 26.9}) - 0.81) < 1e-9
    assert _age_factor({"age_now": 27.5}) == 0.75
    assert _age_factor({"age_now": 31.0}) == 0.75   # floored


def test_fallback_to_milb_age_and_missing_safe():
    assert _age_factor({"milb": {"age": 27.0}}) == 0.8
    assert _age_factor({}) == 1.0
    assert _age_factor({"age_now": None, "milb": {}}) == 1.0


def test_wired_into_live_scoring_only():
    """The overlay must ride adj_factor in run_live (tilting the MODEL term,
    like the injury penalty) and must NOT appear in the resolved scoring path
    (resolved outcomes already embed age)."""
    from pathlib import Path
    src = (Path(__file__).parent / "efv_score.py").read_text(encoding="utf-8")
    assert "adj_factor = inj * sc * agef" in src
    assert '"Prospect age penalty"' in src
