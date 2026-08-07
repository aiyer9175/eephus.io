# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/fa/ pricing pins F-DEF off, and must say so.

THE DECISION (owner, 2026-08-06). F-DEF wins Gate 1, the WAR projection gate,
and loses Gate 2, the money gate. Attribution on four config-only arms
(docs/fa-gate2-attribution-2026-08-06.md):

    arm            guarantee MAE     AAV MAE     mega MAE
    both on           10.207          3.135        86.065
    DEF off            9.690          2.909        79.814

Dropping it improves AAV by 0.226 $M, about 2.5x the 0.091 $M MDE95, and widens
the model's edge over its own baseline from +0.224 to +0.340. So it is pinned
OFF for pricing and left ON everywhere else.

THE MISTAKE THIS FILE EXISTS TO PREVENT, made twice before it worked:

  1. Pinning at the SCORE only. war_from_projection was told to skip the term
     while the war map was still FITTED with it, so the remaining coefficients
     had already absorbed its contribution. That is not the DEF-off arm, it is a
     third thing, and it measured WORSE than either (guarantee 10.385).
  2. Pinning the WRONG GATE. The second attempt threaded use_def into
     fa_backtest:247, which is GATE 1. run_market_gate never calls fitted_models
     in its own loop; it scores a MarketModel built from fa_market.enriched_signings,
     and THAT is where the fit happens for Gate 2. The money numbers did not move
     by a single digit.

Both attempts were caught by measuring rather than by reading, which is the only
reason they did not ship.

WHAT THESE TESTS HOLD
  1. The pin exists and is off.
  2. It is SCOPED: the global default stays on, so /projections/ is untouched.
     A global flip would contaminate whichever module ran second, because
     run_monthly builds both in one process.
  3. The fit and the score agree, i.e. use_def is threaded into fitted_models
     and fit_war_map, not applied at scoring alone.
  4. The pin sits on the Gate-2 seam.
  5. The divergence is DISCLOSED to readers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
fm = pytest.importorskip("fa_market")
fp = pytest.importorskip("fa_projection")


def test_the_pin_exists_and_is_off():
    assert hasattr(fm, "FA_PRICING_USE_DEF")
    assert fm.FA_PRICING_USE_DEF is False, (
        "the owner decision was to pin F-DEF OFF for pricing; flipping this back "
        "on gives up a measured 0.226 $M of AAV accuracy")


def test_the_pin_is_scoped_and_does_not_touch_projections():
    """A global flip would move /projections/ too. run_monthly builds both in
    ONE process, so module-level state is shared."""
    assert fp.DEF_FEATURE_DEFAULT is True, (
        "the GLOBAL default must stay on: only /fa/ pricing diverges, and "
        "turning it off globally would silently re-grade the projections module")


def test_the_fit_and_the_score_can_be_pinned_together():
    """Attempt one pinned the score alone against a map fitted WITH the term.
    The coefficients had absorbed its contribution, so the result was worse than
    either arm. The override has to reach the FIT."""
    import inspect
    assert "use_def" in inspect.signature(fp.fitted_models).parameters, (
        "fitted_models must accept use_def, or the fit and the score can "
        "disagree")
    assert "use_def" in inspect.signature(fp.fit_war_map).parameters, (
        "fit_war_map must accept use_def; this is the function that decides the "
        "column set")


def test_the_pin_sits_on_the_gate2_seam():
    """Attempt two pinned fa_backtest:247, which is GATE 1. The money numbers
    did not move at all. Gate 2's fit happens inside enriched_signings."""
    src = (ROOT / "fa_market.py").read_text(encoding="utf-8")
    i = src.index("def enriched_signings")
    body = src[i:i + 3000]
    assert "FA_PRICING_USE_DEF" in body, (
        "the pin must be applied inside enriched_signings, which is where Gate 2 "
        "fits its WAR. Pinning Gate 1 instead leaves the money model unchanged.")


def test_the_cache_key_separates_the_two_arms():
    """Both fits coexist on disk. Without the suffix an A/B would silently read
    the other arm's map, which is a whole class of wrong answer."""
    src = (ROOT / "fa_projection.py").read_text(encoding="utf-8")
    i = src.index("def fitted_models")
    body = src[i:i + 2500]
    assert "_use_def" in body and "_suffix" in body, (
        "the cache key must carry the arm, or the pin reads the wrong pickle")


@pytest.mark.skipif(not (ROOT / "data" / "fa_meta.json").exists(),
                    reason="fa_meta not built")
def test_the_divergence_is_disclosed_to_readers():
    """THE CONDITION THE OWNER ATTACHED. Two different WAR figures for one
    player with no explanation is a bug even when both are right."""
    meta = json.loads((ROOT / "data" / "fa_meta.json").read_text(encoding="utf-8"))
    d = meta.get("war_input_divergence")
    assert d, (
        "fa_meta must carry war_input_divergence; the pin was approved ON THE "
        "CONDITION that the page discloses it")
    assert d.get("diverges") is True
    for field in ("pinned_off", "why", "consequence", "measured"):
        assert d.get(field), f"the disclosure must state {field}"
    assert "Projections" in d["consequence"], (
        "the consequence must name the other surface a reader would compare "
        "against, or the disclosure does not help them")
