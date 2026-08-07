"""BOARD BASIS: one basis everywhere, and no silent re-rank.

Three defects motivate this file, all measured 2026-07-29/30 and all invisible to the
suite at the time:

1.  The board rank basis moved TWICE in five days with no model change
    (2026-07-25 `storage.BOARD_GRADE_FIELD` -> raw `xfv_grade`; 2026-07-29
    `efv_board_scale.ENABLED_DEFAULT` -> False). The served top 100 went from 16
    pitchers to 8 and four named arms moved 39->148, 8->15, 12->50, 48->143 with
    ZERO grade changes. `test_efv_board_scale.test_top_n_side_mix_gate` says so in
    its own docstring: it is a COLLAPSE tripwire only and "would NOT have caught
    that regression".
2.  The movement engine published that re-rank as real player movement (Seth
    Hernandez's card reads down 33, confidence high, for a change no player caused).
3.  `data/xfv_history.json` is on a THIRD basis: the retired per-side quantile
    field. Measured: Jesus Made 59.00 in history vs 64.24 served, Bradfield 46.60 vs
    50.97, Ryan Sloan 54.80 vs 56.52. This is the defect behind a top-3% hitter
    appearing to "grade 49.1" on a stale surface.
    FIXED IN CODE 2026-07-30 (Phase 3.2): score_history grades through the board's own
    map and stamps the artifact with the basis it was built on. The committed artifact
    stays stale until a production regen, and a residual TILT gap survives even that;
    both are stated on the tests below rather than papered over.

A fourth defect was found while fixing the third, and is worth recording because it is
the general lesson: a fingerprint only guards what it NAMES. The 2026-07-30 grade-scale
change re-ranked 1,060 board rows while leaving BOARD_GRADE_FIELD and the side-scale flag
- the fingerprint's only two terms - completely unchanged. The fingerprint now names the
outcome curve's content hash as well. When you add a new input to the board ordering, add
it to storage.board_basis_fingerprint in the same commit or this file is lying again.

The side-mix PIN below is deliberately a pin and not a quota. Do not read it as a
target pitcher share. The reason a low pitcher share is defensible at all is measured
in docs/efv-2026-07-30/CROSS_SIDE_WAR_FINDING.md: at consensus FV 55+ a hitter has
historically returned about 2.2x the first-6-year bWAR of a pitcher at the SAME grade
(11.653 vs 5.270, n=75/53), so consensus FV is not cross-side comparable and the
consensus top-100 share of 0.28 is the mis-scaled number, not the truth. The share
that is WRONG is therefore unknown within a wide band, which is exactly why this is a
change-detector rather than a bound.
"""
import json
import statistics
from pathlib import Path

import pytest

import efv_board_scale as bs
import storage

DATA = Path(__file__).parent / "data"


def _active():
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    return {k: v for k, v in (doc.get("by_player") or {}).items()
            if (v or {}).get("kind") == "active"}


# ── the change detector ─────────────────────────────────────────────────────
# Measured on the 2026-07-30 served artifact (data/xfv.json generated 2026-07-28,
# board scale OFF). Recorded so that ANY basis change has to come here and make a
# deliberate edit, with a decision record, instead of shipping silently.
PINNED_MIX = {"top10": 0, "top25": 1, "top50": 2, "top100": 6}
PINNED_BASIS = "xfv_grade"
# Tolerance per cut. The pin exists to catch a BASIS change, and the basis is pinned
# exactly by the fingerprint test below - so the mix only has to be tight enough to
# catch a re-rank of the 2026-07-25 magnitude (top-100 pitchers went 16 -> 8) while
# surviving an ordinary nightly data regen. Recorded 2026-07-30 at top-100 P=8; the
# same-day box regen moved it to 6 with the fingerprint and BOARD_GRADE_FIELD both
# unchanged, which is exactly the false positive this tolerance exists to absorb.
MIX_TOLERANCE = {"top10": 2, "top25": 3, "top50": 4, "top100": 5}
# 2026-07-30, the pooled outcome refit (LANE-P2): DELIBERATELY NOT RE-RECORDED, because
# the flip does not breach the band and re-pinning on a change that did not move the
# statistic would only lose the reading it was recorded at. Measured two ways rather than
# assumed. (a) Counterfactual on this very artifact, inverting each row's xfv_war_6yr
# through the new pooled curve: 10H/0P, 24H/1P, 47H/3P, 92H/8P against the served
# 10H/0P, 24H/1P, 48H/2P, 94H/6P -- a move of 0/0/+1/+2 pitchers, and an exact
# reproduction of the pooled column Phase 1 recorded, which is how we know the shipped
# curve is the one the owner approved. (b) A full before/after re-score of both sides on
# identical inputs: top-100 12P before, 12P after, i.e. the grade map moved the mix by
# ZERO there. The visible drift in this file remains an artifact-refresh effect, not a
# basis effect. The BASIS change itself is caught by the fingerprint test below, which
# now names the outcome-curve hash for exactly this reason.


def test_basis_fingerprint_is_pinned_so_a_flip_cannot_ship_silently():
    """storage.BOARD_RANK_BASIS_EPOCH is hand-maintained and was NOT bumped when the
    basis moved on 2026-07-29, which is how a one-time re-rank reached the movement
    engine as player movement. The fingerprint gives that coordination teeth.

    If this fails: the board ordering changed. Bump BOARD_RANK_BASIS_EPOCH to the flip
    date, record the decision, and restamp BOARD_BASIS_FINGERPRINT in the same commit.
    """
    assert storage.board_basis_fingerprint() == storage.BOARD_BASIS_FINGERPRINT, (
        f"board basis fingerprint moved: {storage.board_basis_fingerprint()!r} != "
        f"{storage.BOARD_BASIS_FINGERPRINT!r}. Bump BOARD_RANK_BASIS_EPOCH (currently "
        f"{storage.BOARD_RANK_BASIS_EPOCH}) and restamp the fingerprint together.")


@pytest.mark.skipif(not (DATA / "xfv.json").exists(), reason="needs a built xfv.json")
def test_top_n_side_mix_is_pinned_to_the_recorded_basis():
    """A basis change must not reach the board without a human deciding it did.

    If this fails, the board basis or the model moved. That is not automatically a
    bug. What IS a bug is letting it happen without (a) re-reading
    CROSS_SIDE_WAR_FINDING.md, (b) recording the decision, and (c) bumping
    storage.BOARD_RANK_BASIS_EPOCH so the movement engine does not publish the
    one-time re-rank as player movement. Then update PINNED_MIX in the same commit.
    """
    assert storage.BOARD_GRADE_FIELD == PINNED_BASIS, (
        f"board basis moved: {storage.BOARD_GRADE_FIELD!r} != {PINNED_BASIS!r}. "
        f"Bump BOARD_RANK_BASIS_EPOCH, record the decision, then update this pin.")
    mix = bs.top_n_side_mix(_active())
    got = {k: mix[k]["P"] for k in PINNED_MIX}
    drift = {k: got[k] - PINNED_MIX[k] for k in PINNED_MIX}
    bad = {k: d for k, d in drift.items() if abs(d) > MIX_TOLERANCE[k]}
    assert not bad, (
        f"top-N pitcher counts moved beyond tolerance: {bad} (got {got}, recorded "
        f"{PINNED_MIX}, tolerance {MIX_TOLERANCE}). A basis flip, a re-enabled side "
        f"scale, or a real model change landed. See the docstring, then re-record.")


@pytest.mark.skipif(not (DATA / "xfv.json").exists(), reason="needs a built xfv.json")
def test_neither_side_is_swept_from_the_top_of_the_board():
    """Two-sided collapse tripwire, independent of the pin above.

    The existing gate in test_efv_board_scale only guards the pitcher floor. A board
    that handed the top 100 entirely to PITCHERS would be just as wrong and nothing
    would catch it.
    """
    mix = bs.top_n_side_mix(_active())
    for n in ("top50", "top100"):
        assert mix[n]["P"] >= 1, f"no pitcher in the {n} of the joint board: {mix}"
        assert mix[n]["H"] >= 1, f"no hitter in the {n} of the joint board: {mix}"
    share = mix["top100"]["pit_share"]
    assert 0.01 <= share <= 0.60, (
        f"top-100 pitcher share {share} is outside any defensible band. The "
        f"consensus share is ~0.28 and the WAR-honest share is lower (see "
        f"CROSS_SIDE_WAR_FINDING.md); a value outside [0.01, 0.60] means the basis "
        f"is not a joint ranking at all.")


# ── the basis-coherence defect (A2) ─────────────────────────────────────────
# CODE FIXED 2026-07-30 (LANE-P2, Phase 3.2). efv_score.score_history now grades every
# snapshot through vf.outcome_implied_fv -- the board's own map -- instead of mapping the
# guarded blend through the retired per-side quantile scale. What remains is two separate
# things, and the marker below is kept because of the SECOND one, not the first.
def _history_doc():
    return json.loads((DATA / "xfv_history.json").read_text(encoding="utf-8"))


def _history_tail_vs_board():
    """[(player_key, history tail, board grade)] for every player on both surfaces."""
    served = _active()
    out = []
    for key, series in (_history_doc().get("by_player") or {}).items():
        row = served.get(key)
        if not row or not series:
            continue
        board = bs.board_value(row)
        last = (series[-1] or {}).get("x")
        if board is None or last is None:
            continue
        out.append((key, float(last), float(board)))
    return out


@pytest.mark.skipif(not (DATA / "xfv_history.json").exists(),
                    reason="needs a built xfv_history.json")
def test_history_artifact_declares_the_basis_it_was_built_on():
    """A grade series with no basis stamp is unauditable, which is how it sat on a third
    basis for as long as it did. score_history stamps the artifact; storage reads the
    stamp to decide whether the eFV-delta movement signal may publish this run
    (storage.xfv_history_is_on_board_basis). Both halves are pinned here.

    Pre-regen this is EXPECTED to report an unstamped artifact and therefore a suppressed
    movement signal - that is the suppression working, not a failure - so the assertion is
    the IMPLICATION, not the stamp's presence."""
    stamped = storage.xfv_history_basis()
    assert stamped == (_history_doc().get("basis") or None) or stamped is None
    # The gate must agree with the stamp in both directions, or the suppression window is
    # decorative.
    assert storage.xfv_history_is_on_board_basis() == (
        bool(stamped) and stamped == storage.board_basis_fingerprint()), (
        f"basis gate disagrees with the stamp: stamp={stamped!r} "
        f"board={storage.board_basis_fingerprint()!r}")


@pytest.mark.xfail(strict=True, reason=(
    "STILL FAILS, for a SMALLER and DIFFERENT reason than when it was registered, and "
    "the marker is kept deliberately rather than removed. (1) The BASIS defect is fixed "
    "in code as of 2026-07-30: score_history grades through vf.outcome_implied_fv, the "
    "board's own map. Measured on a scratch rebuild against the new board: tails "
    "disagreeing by more than 0.51 FV went 91.9% -> 26.7% and the MEDIAN |disagreement| "
    "went 3.80 FV -> 0.00 FV; franklin_arias 58.1 -> 60.1 against a board 60.4, "
    "jesus_made 59.1 -> 60.6 against 60.8. (2) data/xfv_history.json is STILL the old "
    "artifact: it only rebuilds when score_history runs, which is a production regen on "
    "the box, and this lane must not run one. So the committed file is on the retired "
    "quantile basis and this test fails today no matter what the code does. (3) Even "
    "after that regen it will STILL fail, because run_live applies the injury / age / "
    "Statcast / reliever-ceiling tilts and the S-XLINE lean to xfv_war before grading "
    "and score_history has never had as-of values for any of them: 417 of 1,563 tails "
    "keep a tilt gap (138 carry an injury factor, 95 sit at the FV20 floor where the "
    "curve's low end is near-vertical). Closing THAT needs as-of tilt inputs, which do "
    "not exist. Removing this marker would therefore just add a red without adding "
    "information. Revisit it when the tilt inputs become as-of, or narrow the test to "
    "untilted rows; the basis half of the claim is now covered by "
    "test_history_median_tail_is_on_the_board_basis below."))
@pytest.mark.skipif(not (DATA / "xfv_history.json").exists(),
                    reason="needs a built xfv_history.json")
def test_history_series_is_on_the_board_basis():
    """The last point of a player's eFV history must equal the grade the board serves.

    Measured mismatch at registration time: jesus_made history 59.00 vs served 64.24;
    enrique_bradfield_jr 46.60 vs 50.97; ryan_sloan 54.80 vs 56.52 -- i.e. the history
    equals xfv_grade_quantile exactly, not the board number.
    """
    bad = [t for t in _history_tail_vs_board() if abs(t[1] - t[2]) > 0.51]
    assert not bad, (
        f"{len(bad)} players whose eFV history tail disagrees with the board grade; "
        f"first 5: {bad[:5]}")


@pytest.mark.skipif(not (DATA / "xfv_history.json").exists(),
                    reason="needs a built xfv_history.json")
def test_history_median_tail_is_on_the_board_basis():
    """The BASIS half of the claim above, stated as something a tilt gap cannot break.

    A per-row equality test cannot separate "the series is on the wrong scale" from "this
    player carries a live injury tilt the history path never saw". The MEDIAN can: a basis
    error shifts every row (measured 3.80 FV median on the quantile basis), a tilt gap
    shifts a minority (measured 0.00 FV median once repointed). So this is the test that
    actually goes green when the repoint reaches the artifact and red if the basis ever
    drifts again.

    SKIPPED while the artifact is on a foreign basis, which is exactly the state the
    suppression window exists for; it activates on the first production regen."""
    if not storage.xfv_history_is_on_board_basis():
        pytest.skip("xfv_history.json is not on the current board basis yet (pre-regen); "
                    "the eFV-delta movement signal is suppressed until it is")
    pairs = _history_tail_vs_board()
    assert len(pairs) > 100, f"too few comparable rows to judge a basis: {len(pairs)}"
    med = statistics.median(abs(t[1] - t[2]) for t in pairs)
    assert med <= 0.5, (
        f"median |history tail - board grade| is {med:.2f} FV over {len(pairs)} players. "
        f"A tilt gap moves a minority of rows; a number this size means the SCALE moved. "
        f"Re-read efv_score.score_history's grading line before re-recording anything.")


# ── the floor-routing basis (Lane B2, 2026-08-07) ───────────────────────────
# The board number for the constant-anchor cohort may come from EITHER the pooled
# outcome curve or efv_ungraded's capped provisional map, and those two maps
# disagree by -7.0 FV at WAR 0.0 and +11 to +12 through the 0.5-1.5 band. Which map
# produced a row is therefore part of the board's identity, and the fingerprint gap
# the plan registered is closed by the floorroute= term. These tests pin the switch,
# the term, and the scoping predicate that decides who is eligible.


def test_floor_routing_switch_is_pinned_off():
    """Implemented and gated. Serving it needs the prospx board dedupe and the
    two-scale disclosure to land first; without the dedupe the same player prints
    the SAME grade twice instead of two contradictory ones, which reads worse than
    the defect. If this fails, confirm both frontend pieces shipped, then update
    docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_GATE.md section 4 in the same commit."""
    import efv_score
    assert efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT is False


def test_fingerprint_names_the_routing_and_the_provisional_map():
    """A fingerprint only guards what it names, and naming the SWITCH alone would
    not have been enough: the routed grade is efv_ungraded._GRADE_MAP's output, so a
    BASE / SLOPE / KNEE / CEIL / SOFT edit re-grades every routed row while the
    switch reads True the whole time. The term carries the map's hash for the same
    reason grademap= carries the outcome curve's."""
    fp = storage.board_basis_fingerprint()
    assert "|floorroute=" in fp, fp
    term = fp.split("|floorroute=")[1]
    state, _, map_hash = term.partition("@")
    assert state in ("on", "off"), fp
    assert len(map_hash) == 8, f"provisional map hash missing from {fp!r}"
    assert fp == storage.BOARD_BASIS_FINGERPRINT


def test_the_provisional_map_hash_actually_moves_with_the_map():
    """The failure mode this term exists to prevent, exercised directly: a hash that
    does not respond to the map is decoration."""
    import efv_ungraded
    before = storage.board_basis_fingerprint()
    original = efv_ungraded._GRADE_MAP["hit"]["SLOPE"]
    try:
        efv_ungraded._GRADE_MAP["hit"]["SLOPE"] = original + 0.1
        after = storage.board_basis_fingerprint()
    finally:
        efv_ungraded._GRADE_MAP["hit"]["SLOPE"] = original
    assert after != before, (
        "the provisional grade map changed and the board fingerprint did not move")
    assert storage.board_basis_fingerprint() == before, "restore failed"


def test_routing_predicate_is_scoped_to_the_abstaining_floor():
    """Both halves of the scope are load-bearing and both are pinned.

    constant_only  a published grade is an opinion and is never overridden.
    at the floor   vf.outcome_implied_fv maps every non-positive prediction to the
                   curve's first knot, so at the floor the flagship map is ABSTAINING
                   rather than disagreeing. Above it the curve resolved a real
                   prediction. This is not a technicality: 184 rows in this cohort
                   grade above FV30 on the flagship map and a median 7.7 FV LOWER on
                   the provisional one, so an unscoped routing would demote 184
                   visible board rows.
    """
    import efv_score
    floor = efv_score._outcome_floor_knot()
    saved = efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT
    saved_cache = efv_score._prov_grades_cache
    try:
        efv_score._prov_grades_cache = {"pk": 31.4}
        efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT = False
        assert efv_score.route_floor_grade("pk", floor, True) is None, "gated off"
        efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT = True
        assert efv_score.route_floor_grade("pk", floor, True) == 31.4
        assert efv_score.route_floor_grade("pk", floor + 0.1, True) is None
        assert efv_score.route_floor_grade("pk", 38.0, True) is None
        assert efv_score.route_floor_grade("pk", floor, False) is None
        assert efv_score.route_floor_grade("pk", None, True) is None
        assert efv_score.route_floor_grade("absent", floor, True) is None
    finally:
        efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT = saved
        efv_score._prov_grades_cache = saved_cache


def test_floor_knot_is_read_from_the_curve_not_written_as_20():
    """A literal 20.0 here would keep matching rows the map no longer produces if the
    curve is ever refit with a different first knot."""
    import efv_score
    import value_framework as vf
    assert efv_score._outcome_floor_knot() == float(vf._outcome_curve()["knots"][0])
    assert vf.outcome_implied_fv(-1.0, exposure_seasons=6) == efv_score._outcome_floor_knot()
    assert vf.outcome_implied_fv(0.0, exposure_seasons=6) == efv_score._outcome_floor_knot()
