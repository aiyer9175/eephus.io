# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eFV model (efv_model.py) unit tests.

Pins the pieces that silently break the flagship if they drift:
  1. the blend-lambda hierarchy -- WAG when its calibration has signal, else the
     rank-gate fallback (never the noisy WAG slope), the hard-coded fallback
     constants, and the clamp band;
  2. the LEAN, shipped feature sets (exact keys + monotone directions) so a stray
     feature edit fails loudly instead of quietly re-ranking the board;
  3. _vec produces finite values for a minimal synthetic record (impute path).

The lambda-hierarchy tests monkeypatch wag_calibration / rank_calibration and use a
fresh cache so each branch is forced deterministically -- no dependence on the live
data files for the branch logic.
"""
import math

import pytest

import efv_model as em


# --------------------------------------------------------------------------
# 1. Blend-lambda hierarchy
# --------------------------------------------------------------------------
def test_fallback_and_clamp_constants_are_pinned():
    # hard-set fallback (used only when WAG AND rank calibration both error out)
    assert em._BLEND_LAMBDA_FALLBACK == {"hit": 0.85, "pit": 0.80}
    # the clamp band every calibrated lambda must live inside
    assert em._BLEND_LAMBDA_CLAMP == (0.35, 0.90)
    # the WAG-significance gate that decides WAG-vs-rank-gate (raised 0.05 -> 0.10 on
    # 2026-07-06: the norm-fix collapsed the hitter WAG signal to non-significance, so
    # 0.05 was still pinning a rank-suboptimal lambda; 0.10 defers non-significant WAG
    # to the rank gate, lifting the pooled OOS rank rho)
    assert em._WAG_MIN_SPEARMAN == 0.10
    assert em._WAG_MIN_N == 100


@pytest.fixture
def fresh_lambda_cache(monkeypatch):
    """Swap in an empty cache so blend_lambda recomputes (auto-restored after).

    Also clears _BLEND_LAMBDA_RESELECT. That override short-circuits the whole
    WAG/rank-gate/fallback ladder (efv_model.blend_lambda returns it immediately), so
    with an override set this fixture could not actually make blend_lambda "recompute"
    and the three ladder tests below were silently testing nothing. They were FAILING
    from the moment the A1 re-select shipped a hit override; test_hard_fallback_on_error
    only passed because that override happened to equal the fallback constant. The
    override itself is pinned separately by test_reselect_override_wins below."""
    monkeypatch.setattr(em, "_WAG_LAMBDA_CACHE", {})
    monkeypatch.setattr(em, "_BLEND_LAMBDA_RESELECT", {"hit": None, "pit": None})


@pytest.mark.parametrize("wag", [
    {"spearman": 0.02, "n": 5000, "lambda": 0.39},   # sub-threshold rho (pitcher-like noise)
    {"spearman": 0.90, "n": 50, "lambda": 0.70},     # too few WAG rows
    {"spearman": None, "n": 5000, "lambda": 0.70},   # no rho at all
])
def test_degenerate_wag_falls_back_to_rank_calibration(monkeypatch, fresh_lambda_cache, wag):
    """When the WAG join is absent/degenerate its slope is noise; blend_lambda must
    take the rank-gate value, NOT WAG's lambda."""
    monkeypatch.setattr(em, "wag_calibration", lambda side: dict(wag))
    monkeypatch.setattr(em, "rank_calibration", lambda side: {"lambda": 0.62})
    got = em.blend_lambda("hit")
    assert got == 0.62, "degenerate WAG must defer to rank_calibration"
    assert got != wag["lambda"], "must NOT use the noisy WAG slope"


def test_significant_wag_is_used(monkeypatch, fresh_lambda_cache):
    """When WAG clears both gates (|rho| >= 0.05 and n >= 100) its lambda is used."""
    monkeypatch.setattr(em, "wag_calibration",
                        lambda side: {"spearman": 0.21, "n": 400, "lambda": 0.83})
    monkeypatch.setattr(em, "rank_calibration",
                        lambda side: {"lambda": 0.62})   # must be ignored
    assert em.blend_lambda("pit") == 0.83


def test_hard_fallback_on_error(monkeypatch, fresh_lambda_cache):
    """Any exception in calibration -> the hand-set fallback constant for the side."""
    def boom(side):
        raise RuntimeError("no data")
    monkeypatch.setattr(em, "wag_calibration", boom)
    assert em.blend_lambda("hit") == em._BLEND_LAMBDA_FALLBACK["hit"] == 0.85
    monkeypatch.setattr(em, "_WAG_LAMBDA_CACHE", {})
    assert em.blend_lambda("pit") == em._BLEND_LAMBDA_FALLBACK["pit"] == 0.80


def test_reselect_override_wins(monkeypatch):
    """The _BLEND_LAMBDA_RESELECT override short-circuits the WAG/rank/fallback ladder.

    Pins the mechanism the A1 re-select ship (and the 2026-07-24 churn trade) rides on:
    when a side has an override, blend_lambda returns it regardless of what WAG or the
    rank gate say, and regardless of a calibration error. A side set to None falls
    through to the normal ladder."""
    monkeypatch.setattr(em, "_WAG_LAMBDA_CACHE", {})
    monkeypatch.setattr(em, "_BLEND_LAMBDA_RESELECT", {"hit": 0.70, "pit": None})
    monkeypatch.setattr(em, "wag_calibration",
                        lambda side: {"spearman": 0.90, "n": 9999, "lambda": 0.42})
    monkeypatch.setattr(em, "rank_calibration", lambda side: {"lambda": 0.62})
    assert em.blend_lambda("hit") == 0.70, "override must win over WAG and the rank gate"
    assert em.blend_lambda("pit") == 0.42, "None must fall through to the normal ladder"


def test_shipped_lambda_is_inside_its_measured_floor():
    """The shipped hit lambda is a CHURN trade, not an accuracy claim.

    docs/EFV_GATE_STANDARD.md: the minimum detectable effect for a lambda shift is
    0.0076 pooled rho (hit). Both the A1 raise to 0.85 (+0.0048) and the 2026-07-24
    return to 0.70 (-0.00049) are inside that floor, so neither is an accuracy move and
    the constant must not be re-litigated on sub-floor rho evidence."""
    assert em._BLEND_LAMBDA_RESELECT["hit"] == 0.70
    lo, hi = em._BLEND_LAMBDA_CLAMP
    assert lo <= em._BLEND_LAMBDA_RESELECT["hit"] <= hi


def test_shipped_lambda_respects_clamp_both_sides():
    """The live, data-driven lambda for each side must stay inside the clamp band.
    (Shipped pit lambda is rank-calibrated ~0.66, well below the 0.80 fallback -- the
    two must not be conflated; this only asserts the band, not the exact value.)"""
    lo, hi = em._BLEND_LAMBDA_CLAMP
    for side in ("hit", "pit"):
        lam = em.blend_lambda(side)
        assert lo <= lam <= hi, f"{side} lambda {lam} escaped clamp {em._BLEND_LAMBDA_CLAMP}"


# --------------------------------------------------------------------------
# 2. Lean feature sets -- pin exact keys + directions (silent drift fails loudly)
# --------------------------------------------------------------------------
_EXPECTED_HIT = [
    # k_rel / n_milb_seasons / milb_missing declared 0 = "no directional claim"
    # (sign audit 2026-07-25): all three fitted AGAINST their old declaration in the
    # served production fit. See efv_sign_audit.py + test_efv_sign_declarations.py.
    ("fv", +1), ("obp_rel", +1), ("k_rel", 0), ("peak_k_rel", -1),
    ("age_rel_level", -1), ("n_milb_seasons", 0), ("tool_hit", +1),
    ("tool_speed", +1), ("milb_missing", 0), ("is_ifa", 0), ("is_college", 0),
    # ops_rel: FV-45 fringe signal shipped via WS-M / M5 (fringe gate, t45 +0.0237;
    # ledger data/xfv_ops_rel_fringe_eval.json). Kept last (ridge is order-invariant).
    ("ops_rel", +1),
    # age: absolute age, OWNER-DIRECTED ship 2026-07-14 (missed the pooled
    # auto-bar by 0.0003, every metric >= -noise; ledger
    # data/xfv_age_feature_eval.json + docs/efv-2026-07-14/GATES.md).
    ("age", -1),
    # level_rank: cleared its pre-registered LR-FRINGE re-gate at the 2024-fold
    # vintage (t45 +0.0192, bar +0.015; docs/efv-2026-07-15/GATES.md; ledger
    # data/xfv_level_rank_fringe_eval.json).
    ("level_rank", +1),
]
_EXPECTED_PIT = [
    ("fv", +1), ("peak_k_rel", +1), ("k_rel", +1), ("bb_rel", -1),
    # age_rel_level: declaration corrected to 0 on 2026-07-30, the other half of the
    # pitcher age block below. The 07-25 audit measured it at -0.0076, under the audit's
    # own 0.02 noise floor, so the -1 survived on a weight that asserted nothing; the
    # decimal-age matrix rebuild moved it to +0.0418 and surfaced the contradiction.
    # Marginal -0.069, and dropping the partner `age` pushes it MORE positive (+0.0916),
    # so it is a suppressor and not a collinear split. Dropping is a measured NULL
    # (-0.00249, 0.16x the pit MDE95). The feature stays; the claim goes.
    ("age_rel_level", 0), ("x_era_k", +1), ("tool_fb", +1),
    # age: shipped 2026-07-14 owner-directed, declaration corrected to 0 on
    # 2026-07-25 (served ridge fits +0.0589 against the old -1; dropping it is a
    # measured NULL at 0.24x the pit MDE95). The feature stays; the claim goes.
    ("age", 0),
    # seasons_at_level: SHIPPED PITCHERS ONLY 2026-07-30 (owner decision on the E1 gate,
    # docs/efv-2026-07-30/E1_REPEAT_LEVEL_GATE.md). Consecutive seasons on the current
    # level, the first feature in the set that can see a STALL rather than a snapshot.
    # Sign -1 CONFIRMED, fitted -0.1072 and the 4th largest weight. It ships INSIDE the
    # generic MDE95 (0.79x) on the strength of the feature-specific permutation null:
    # 0 of 30 draws from the true marginal beat the real +0.0127, null sd 0.0030,
    # p=0.032. Deliberately absent from _EXPECTED_HIT: on hitters the same column fits
    # +0.0945 and permutes to p=0.375, so that arm is closed on both an inverted sign
    # and noise. If this list and the hitter list ever "look asymmetric", that is the
    # measurement, not an oversight.
    ("seasons_at_level", -1),
]


def test_hit_feature_set_exact():
    assert em._FEATURES_HIT == _EXPECTED_HIT
    keys, mono = em._feature_spec("hit")
    assert keys == [k for k, _ in _EXPECTED_HIT]
    assert mono == [m for _, m in _EXPECTED_HIT]


def test_pit_feature_set_exact():
    assert em._FEATURES_PIT == _EXPECTED_PIT
    keys, mono = em._feature_spec("pit")
    assert keys == [k for k, _ in _EXPECTED_PIT]
    assert mono == [m for _, m in _EXPECTED_PIT]


def test_feature_keys_are_unique_and_fv_dominant_prior():
    for feats in (em._FEATURES_HIT, em._FEATURES_PIT):
        keys = [k for k, _ in feats]
        assert len(keys) == len(set(keys)), "duplicate feature key"
        assert keys[0] == "fv", "consensus FV must lead as the regularized prior"


# --------------------------------------------------------------------------
# 3. _vec produces finite values for a minimal synthetic record
# --------------------------------------------------------------------------
@pytest.mark.parametrize("side", ["hit", "pit"])
def test_vec_finite_on_minimal_record(side):
    # the smallest record _vec accepts: everything missing -> impute path + milb_missing=1
    vec = em._vec({}, side)
    assert vec, "empty vector"
    assert all(isinstance(v, float) and math.isfinite(v) for v in vec.values()), \
        {k: v for k, v in vec.items() if not math.isfinite(v)}
    # missingness indicator fires when the production block is absent
    assert vec["milb_missing"] == 1.0
    # every shipped feature key for this side is present in the vector
    keys, _ = em._feature_spec(side)
    assert set(keys) <= set(vec), f"model expects keys absent from _vec: {set(keys) - set(vec)}"


def test_vec_finite_on_populated_record():
    r = {
        "consensus_fv_raw": 55, "fv_trend": 3.0, "n_sources": 4, "position": "SS",
        "pick_overall": 12, "bonus_usd": 2_500_000, "il_stints_pre": 1,
        "fv_stddev": 2.5, "is_ifa": 0, "is_college": 1,
        "milb": {"age_rel_level": -1.2, "level_rank": 5, "k_rel": -0.02, "bb_rel": 0.03,
                 "n_milb_seasons": 3, "prod_trend": 0.1, "obp_rel": 0.04, "iso_rel": 0.02,
                 "peak_k_rel": -0.03, "peak_obp_rel": 0.05, "era_rel": -0.4},
    }
    for side in ("hit", "pit"):
        vec = em._vec(r, side)
        assert all(math.isfinite(v) for v in vec.values())
        assert vec["milb_missing"] == 0.0    # a real production block -> not imputed
        assert vec["fv"] == 55.0
