# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eFV model (efv_model.py) unit tests.

Pins the pieces that silently break the flagship if they drift:
  1. the blend-lambda hierarchy -- WAG when its calibration has signal, else the
     rank-gate fallback (never the noisy WAG slope), the hard-coded fallback
     constants, and the clamp band;
  2. the LEAN, shipped feature sets (exact keys + monotone directions) so a stray
     feature edit fails loudly instead of quietly re-ranking the board;
  3. _vec produces finite values for a minimal synthetic record (impute path).
  4. NO CLAIM WITHOUT ITS ESTIMATOR: every published margin in this module carries
     the name of the bootstrap that produced its floor, and no leg publishes a
     bare inequality as a verdict. Asserted as a PROPERTY over the emitted
     structure, not against a list of expected strings, so it keeps holding when
     the vintage moves the numbers or a new leg is added.

The lambda-hierarchy tests monkeypatch wag_calibration / rank_calibration and use a
fresh cache so each branch is forced deterministically -- no dependence on the live
data files for the branch logic.
"""
import math
import re
from pathlib import Path

import pytest

import efv_model as em

ROOT = Path(__file__).resolve().parent


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
    # DECLARATION MOVED -1 -> 0 on 2026-08-04. The feature STAYS; only the
    # directional claim went. On the rebuilt matrix the column serves +0.0420
    # against a declared -1, and the four-step adjudication (the same one the
    # pitcher age_rel_level case got on 2026-07-30) found: it is a COLLINEAR
    # SPLIT with age_rel_level (r +0.518; removing the sibling snaps the sign
    # back to -0.0502), and the fresh drop gate is a sub-floor NULL (+0.00669 =
    # 0.39x the hitter MDE95, CI95 straddling zero, and a row-permuted control
    # scores 93 percent of the candidate). The gate standard forbids removing a
    # feature on sub-floor evidence, so the feature stays and the declaration
    # moves. Not +1 either: the fold mean is negative, the rank marginal is
    # negative, and it served -0.0619 one rebuild ago. A direction that inverts
    # when the label is redefined is not a theory. Ledger:
    # data/xfv_hit_age_sign_gate.json, docs/efv-2026-08-04/HIT_AGE_SIGN_GATE.md.
    ("age", 0),
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


# --------------------------------------------------------------------------
# 4. NO CLAIM WITHOUT ITS ESTIMATOR
#
# B-L1 landed two floors per statistic (E_refit resamples the pool and refits the
# chain per draw; E_cond holds the fit and resamples the scored unit). They return
# OPPOSITE CALLS on live cells, so an unlabelled floor is not a claim anyone can
# check. These assert the PROPERTY over whatever the module emits: any dict that
# carries a floor must carry the estimator that produced it, and any verdict STRING
# beside a floor must name it too, because the string is what a reader acts on.
# --------------------------------------------------------------------------
#: Keys that ARE a floor.
_FLOOR_KEYS = ("mde95", "mde95_cond", "floor", "min_detectable")
#: Keys that carry a published call. A dict holding one of these AND a floor is a
#: verdict-bearing dict and owes an estimator sibling.
_VERDICT_KEYS = ("verdict", "resolvable", "beats", "win", "detects")
_ESTIMATOR_SIBLINGS = ("mde95_estimator", "estimator", "mde95_estimators")
_ESTIMATOR_TOKENS = (em.E_REFIT, em.E_COND)
#: Suffixes that mark a key as PROSE ABOUT a floor or a call rather than one:
#: `*_floor_status` explains, `*_UNFLOORED` declares the absence of a floor, and
#: `retired_key_*` documents a key that no longer ships.
_DESCRIPTIVE = ("_status", "_source", "_note", "_estimator", "unfloored")


def _descriptive(key: str) -> bool:
    k = key.lower()
    return k.startswith("retired_key") or k.endswith(_DESCRIPTIVE)


def _is_floor(key: str) -> bool:
    k = key.lower()
    if _descriptive(k):
        return False
    return any(k == f or k.startswith(f + "_") or k.endswith("_" + f) for f in _FLOOR_KEYS)


def _is_call(key: str) -> bool:
    k = key.lower()
    if _descriptive(k):
        return False
    return any(w in k for w in _VERDICT_KEYS)


def _has_estimator(node: dict) -> bool:
    return any(node.get(sib) for sib in _ESTIMATOR_SIBLINGS)


def _unlabelled(node, path="$", out=None):
    """Every violation of the property, as ``path`` strings.

    A dict violates when it holds BOTH a floor with a real value AND a verdict-bearing
    key, but names no estimator. A `verdict` string violates when it sits beside a
    floor and does not contain an estimator token.
    """
    out = [] if out is None else out
    if isinstance(node, dict):
        floors = [k for k, v in node.items() if _is_floor(k) and v is not None]
        calls = [k for k in node if _is_call(k)]
        if floors and calls and not _has_estimator(node):
            out.append(f"{path}: floors {floors} beside calls {calls}, no estimator named")
        if floors and isinstance(node.get("verdict"), str) \
                and not any(t in node["verdict"] for t in _ESTIMATOR_TOKENS):
            out.append(f"{path}.verdict: '{node['verdict']}' names no estimator")
        for k, v in node.items():
            _unlabelled(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _unlabelled(v, f"{path}[{i}]", out)
    return out


def test_floored_verdict_refuses_a_margin_with_no_estimator():
    """The rule is enforced at the constructor, not by convention. A default would
    silently pick a side of a disagreement the two estimators really have."""
    for bad in (None, "", 0):
        with pytest.raises(ValueError):
            em.floored_verdict(0.05, 0.03, bad, source="x")
    for bad_floor in (None, 0, -0.01):
        with pytest.raises(ValueError):
            em.floored_verdict(0.05, bad_floor, em.E_REFIT, source="x")


def test_floored_verdict_stamps_the_estimator_into_the_string_not_only_a_field():
    for est in (em.E_REFIT, em.E_COND):
        v = em.floored_verdict(0.05, 0.03, est, source="x")
        assert v["mde95_estimator"] == est
        assert est in v["verdict"], "the sentence a reader acts on must carry it too"
        assert not _unlabelled(v)


def test_the_two_estimators_really_can_disagree():
    """The reason the rule exists, read from the shipped artifact rather than
    asserted. headtohead_common is the live cell where the same margin is a NULL
    under one published floor and a win under the other."""
    f = em.power_floors("headtohead_common")
    if not f.get("E_refit") or not f.get("E_cond"):
        pytest.skip("data/xfv_power_eval.json partb_floors not present")
    delta = 0.03318      # the cell's own point_delta
    a = em.floored_verdict(delta, f["E_refit"], em.E_REFIT, source=f["source"])
    b = em.floored_verdict(delta, f["E_cond"], em.E_COND, source=f["source"])
    assert a["resolvable"] is not b["resolvable"], \
        "if these ever agree the test is stale, not the rule"


def test_a_floor_is_never_borrowed_from_another_statistic():
    """power_floors returns {} for an unpublished class instead of a near neighbour.
    The refit share is 0.128 on headtohead_common and 0.795 on pooled_rho.hit.debuted_km
    inside the SAME artifact, a 6.2x spread, so 'close enough' does not exist here."""
    assert em.power_floors("pooled_rho.hit.debuted_resolved") == {}
    assert em.power_floors("no_such_cell") == {}


# ---- the demoted rank_win -------------------------------------------------
def _scores(mae, rho, n=400):
    return {"n": n, "mae": mae, "spearman": rho}


def test_rank_win_and_its_bare_legs_are_gone():
    """The retired keys must be ABSENT, not renamed-and-kept: a stale
    `.get("rank_win")` has to return None (no verdict), never a confident bool."""
    base = _scores(2.40, 0.3771)
    v = em._leg_diagnostic("blend", _scores(2.44, 0.3883), base,
                           em.power_floors("pooled_rho.hit.debuted_km"), "hit", "debuted_km")
    for dead in ("rank_win", "beats_mae", "beats_spearman"):
        assert dead not in v, f"{dead} is still published"
    assert v.get("rank_win") is None
    # and the reason is IN THE ARTIFACT, not only in a doc
    assert "DIAGNOSTIC" in v["status"]
    assert "REMOVED" in v["retired_key_rank_win"]


def test_the_mae_leg_is_published_unfloored_and_says_why():
    v = em._leg_diagnostic("blend", _scores(2.44, 0.3883), _scores(2.40, 0.3771),
                           em.power_floors("pooled_rho.hit.debuted_km"), "hit", "debuted_km")
    assert v["mae_floor"] is None
    assert "NO MDE95 EXISTS FOR ANY MAE STATISTIC" in v["mae_floor_status"]
    assert "EFV_GATE_STANDARD" in v["mae_floor_status"]
    # the surviving inequality is suffixed so it cannot be read as a call
    assert v["mae_lower_than_baseline_UNFLOORED"] is False
    assert v["mae_delta_vs_baseline"] == 0.04


def test_only_the_shipped_blend_leg_inherits_the_pooled_rho_floor():
    """B-L1 measured the pooled_rho cells on the blend-minus-baseline delta. ridge /
    lgbm / comps / ensemble are different statistics and must publish unfloored."""
    floors = em.power_floors("pooled_rho.hit.debuted_km")
    if not floors:
        pytest.skip("partb_floors not present")
    blend = em._leg_diagnostic("blend", _scores(2.44, 0.3883), _scores(2.40, 0.3771),
                               floors, "hit", "debuted_km")
    assert blend["spearman_call_E_refit"]["mde95_estimator"] == em.E_REFIT
    assert blend["spearman_call_E_cond"]["mde95_estimator"] == em.E_COND
    assert not _unlabelled(blend)
    for other in ("ridge", "lgbm", "comps", "ensemble", "ridge_cal", "ensemble_cal"):
        v = em._leg_diagnostic(other, _scores(2.44, 0.3883), _scores(2.40, 0.3771),
                               floors, "hit", "debuted_km")
        assert "spearman_call_E_refit" not in v
        assert v["spearman_floor"] is None
        assert "does not inherit" in v["spearman_floor_status"]
        assert not _unlabelled(v)


def test_a_cut_with_no_published_cell_publishes_unfloored():
    v = em._leg_diagnostic("blend", _scores(2.44, 0.3883), _scores(2.40, 0.3771),
                           em.power_floors("pooled_rho.hit.debuted_resolved"),
                           "hit", "debuted_resolved")
    assert "spearman_call_E_refit" not in v
    assert v["spearman_floor"] is None
    assert not _unlabelled(v)


# ---- block-rho and the honest note ---------------------------------------
def test_block_rho_report_names_the_estimator_on_every_call():
    r = em._block_rho_report(0.3081, 0.3166, 0.0085, 1644, {"hit": 755, "pit": 889})
    assert r["mde95_estimator"] == em.E_REFIT
    assert em.E_REFIT in r["verdict"]
    assert not _unlabelled(r), _unlabelled(r)
    if "call_E_cond" in r:
        assert em.E_COND in r["call_E_cond"]["verdict"]
        # labels changed, floors did not: the shipped constant is still the gate
        assert r["mde95"] == em.MDE95_BLOCK_RHO


def _quotable_floors(side) -> set[str]:
    """Every floor VALUE this side's note is able to print, read from the constants
    and the artifact rather than typed here. Keyed off the values, not off phrasing:
    a prose rewrite must not be able to slip a floor past the guard by dropping the
    word 'MDE95'."""
    vals = {em.MDE95_POOLED_RHO[side], em.MDE95_BLOCK_RHO}
    for cell in (f"pooled_rho.{side}.debuted_km", f"pooled_rho.{side}.full_pool_km",
                 "block_rho"):
        f = em.power_floors(cell)
        vals |= {v for v in (f.get("E_refit"), f.get("E_cond")) if v}
    return {str(v) for v in vals}


def _quotes_a_floor(sentence: str, floors: set[str]) -> bool:
    # standalone number, so 0.044 does not match inside 0.0440 or 10.0445
    return any(re.search(r"(?<![\d.])" + re.escape(f) + r"(?![\d])", sentence)
               for f in floors)


def test_the_honest_note_never_quotes_a_floor_without_its_estimator():
    evals = {
        "debuted_km": {
            "pooled_oos": {"baseline": {"spearman": 0.3771}, "blend": {"spearman": 0.3883}},
            "verdict_vs_consensus": {"blend": em._leg_diagnostic(
                "blend", _scores(2.44, 0.3883), _scores(2.40, 0.3771),
                em.power_floors("pooled_rho.hit.debuted_km"), "hit", "debuted_km")}},
        "full_pool_km": {
            "pooled_oos": {"baseline": {"spearman": 0.2954}, "blend": {"spearman": 0.2764}}},
    }
    block = em._block_rho_report(0.3081, 0.3166, 0.0085, 1644, {"hit": 755, "pit": 889})
    note = em._honest_note(evals, {}, block, "hit")
    floors = _quotable_floors("hit")
    quoting = [s for s in re.split(r"(?<=\.)\s+", note) if _quotes_a_floor(s, floors)]
    assert len(quoting) >= 3, (
        f"the note stopped quoting floors; this test is now vacuous. note={note}")
    for s in quoting:
        assert any(t in s for t in _ESTIMATOR_TOKENS), f"unlabelled floor sentence: {s}"


# ---- the served surface ---------------------------------------------------
def test_the_diamond_verdict_sentence_names_its_estimator():
    """assets/diamond.js prints head_to_head_verdict.mde95 on the pricing page. The
    PROPERTY: every render of that floor is accompanied by a render of its estimator
    label, in the same statement.

    SIBLING SITE OWNED ELSEWHERE: assets/glossary.js:671-672 renders the SAME floor
    (hh.mde95) in the Methodology tab and is not yet labelled. Add it to `surfaces`
    below once that lane's patch lands; it is deliberately absent rather than
    asserted-and-red."""
    surfaces = [ROOT / "assets" / "diamond.js"]
    for path in surfaces:
        src = path.read_text(encoding="utf-8")
        block = re.search(r"var verdictHTML = \"\";.*?\n    \}\n", src, re.S)
        assert block, f"{path.name}: verdict block not found, test is stale"
        body = block.group(0)
        floors = len(re.findall(r"dec\(vv\.mde95\)", body))
        assert floors >= 1, f"{path.name}: no floor rendered, test is now vacuous"
        labels = len(re.findall(r"esc\(est\)", body))
        assert labels >= floors, (
            f"{path.name}: {floors} floor renders but only {labels} estimator labels")
        assert "vv.mde95_estimator" in body, (
            f"{path.name}: the label must come from the artifact when it carries one")
