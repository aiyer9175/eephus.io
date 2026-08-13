"""Pins for the 2026-08-14 grade-basis epoch (Defect A dispersion correction).

Gate: docs/efv-2026-08-13/GRADE_BASIS_EPOCH_GATE.md.

Every pin here exists because the ship broke a claim that had been ARGUED rather
than asserted. The narrow path that preceded this epoch rested on board order and
dollars being provably immovable, and both were false, so the properties this lane
does rely on are pinned instead of reasoned about.
"""
from __future__ import annotations

import pytest

import efv_score as E
import storage as S
import value_framework as vf

SIDES = ("hit", "pit")
TARGET_SEASONS = 6


def test_correction_is_strictly_increasing_and_respects_the_floor():
    """The whole ordering argument needs b_c > 0. A non-increasing correction would
    reorder the board, which is out of scope for a level fix by definition."""
    for is_pit in (False, True):
        prev = None
        for i in range(-400, 1500):
            w = i / 100.0
            got = E.apply_dispersion_correction(w, is_pit)
            assert got >= -2.0 - 1e-12, f"correction emitted {got}, below the -2.0 floor"
            if prev is not None:
                assert got >= prev - 1e-12, "correction is not monotone"
            prev = got


def test_b_c_is_positive_on_both_sides():
    """ABORT condition from the gate. A clamp here would silently turn an abort into
    a ship."""
    for s in SIDES:
        _a, b = E._DISPERSION_CORRECTION[s]
        assert b > 0, f"{s}: b_c = {b} <= 0 is an ABORT, not something to clamp"


def test_the_two_seam_orders_agree_which_is_why_correct_then_clamp_is_free():
    """`max(-2, a+b*w)` and `a+b*max(-2, w)` agree for every row iff a_c <= 2*b_c.

    The gate picks correct-then-clamp because outside that regime the other order
    collapses every sub-floor row onto ONE identical grade and can emit a served WAR
    below -2.0. Inside it the choice costs nothing. This pin fails the day a refit
    moves the coefficients out of the safe regime, which is exactly when the seam
    order stops being free."""
    for s in SIDES:
        a, b = E._DISPERSION_CORRECTION[s]
        assert a <= 2 * b, (
            f"{s}: a_c={a} > 2*b_c={2 * b}. The seam orders no longer agree; "
            "re-read the gate before shipping this refit")
        is_pit = s == "pit"
        for i in range(-400, 800):
            w = i / 100.0
            correct_then_clamp = E.apply_dispersion_correction(w, is_pit)
            clamp_then_correct = a + b * max(-2.0, w)
            g1 = vf.outcome_implied_fv(correct_then_clamp, exposure_seasons=TARGET_SEASONS)
            g2 = vf.outcome_implied_fv(max(-2.0, clamp_then_correct),
                                       exposure_seasons=TARGET_SEASONS)
            assert abs(g1 - g2) < 1e-9, f"{s}: seam orders disagree at w={w}"


def test_routing_is_decided_on_the_uncorrected_grade():
    """THE load-bearing pin of this epoch.

    route_floor_grade uses "the flagship grade sits on the floor knot" as its proxy
    for "the model has no real prediction here". The correction adds a positive
    intercept, so deciding routing on the CORRECTED grade strips the provisional grade
    from every row the intercept lifts across zero: 950 rows measured, worst case
    40.1 -> 25.0 on a WAR move of -0.68 to +0.01.

    A player sitting at the floor with a provisional grade must keep it."""
    knot = E._outcome_floor_knot()
    key = "_synthetic_routed_row"
    E._prov_grades_cache = {key: 40.1}
    try:
        war_uncorrected = -0.68
        grade_uncorrected = vf.outcome_implied_fv(war_uncorrected,
                                                  exposure_seasons=TARGET_SEASONS)
        assert abs(grade_uncorrected - knot) <= 1e-9, (
            "fixture no longer sits on the floor knot; pick a more negative WAR")

        # What the shipped seam does: route on the UNCORRECTED grade.
        assert E.route_floor_grade(key, grade_uncorrected, True) == 40.1

        # What the naive seam would have done: route on the CORRECTED grade.
        war_corrected = E.apply_dispersion_correction(war_uncorrected, False)
        assert war_corrected > 0, "fixture no longer crosses the knot; correction moved"
        grade_corrected = vf.outcome_implied_fv(war_corrected,
                                                exposure_seasons=TARGET_SEASONS)
        assert E.route_floor_grade(key, grade_corrected, True) is None, (
            "the naive seam is supposed to LOSE the routed grade; if this passes, "
            "the two seams no longer differ and this pin proves nothing")
    finally:
        E._prov_grades_cache = None


def test_the_live_seam_passes_the_uncorrected_grade_to_the_router():
    """The test above pins route_floor_grade's behaviour. This pins that the SEAM
    actually hands it the uncorrected grade, which is the thing that can regress: the
    function is unchanged by this epoch, the call site is not."""
    import inspect
    live = inspect.getsource(E.run_live)
    assert "route_floor_grade(r[\"player_key\"], _grade_uncorrected," in live, (
        "run_live no longer routes on the uncorrected grade; 950 rows would lose "
        "their provisional grade to the flagship curve's dead zone")
    # and the uncorrected grade must be taken BEFORE the correction is applied
    assert live.index("_grade_uncorrected = vf.outcome_implied_fv") < \
        live.index("xfv_war = apply_dispersion_correction"), (
        "the uncorrected grade is computed from an already-corrected WAR")


def test_the_blend_leg_is_not_corrected():
    """Routing the correction through rank_war re-weights the model leg to lam*b_c
    against 1-lam. That is a BLEND-LAMBDA change, a banned lane, and it lands the
    pitcher effective lambda at 0.4203, outside the .65/.60/.51 the TOST covered.

    Pinned as source text because the defect would be an ASSIGNMENT, and there is no
    cheap runtime probe that distinguishes which variable the blend read."""
    import inspect
    src = inspect.getsource(E.run)
    assert "lam * _war_model" in src, (
        "run() blend no longer reads the uncorrected model leg; correcting rank_war "
        "is a blend-lambda change and needs its own gate")
    live = inspect.getsource(E.run_live)
    assert "apply_dispersion_correction" in live, "run_live lost the correction"
    # The correction must land AFTER the last rank_war rebuild in run_live, otherwise
    # the blend picks it up through the tilt path.
    assert live.index("apply_dispersion_correction") > live.rindex("rank_war = (1 - lam)"), (
        "the correction moved above a rank_war rebuild; the blend would pick it up")


def test_fingerprint_names_the_correction():
    """A fingerprint only guards what it names, which this programme has now learned
    four times. Without this term the epoch moves 4,585 served grades while the
    coordination device stays byte-identical to its pin."""
    fp = S.board_basis_fingerprint()
    assert "|disp=" in fp, "fingerprint does not name the dispersion correction"
    tail = fp.split("|disp=", 1)[1]
    assert "unavailable" not in tail, "dispersion term degraded to unavailable"
    for s in SIDES:
        a, b = E._DISPERSION_CORRECTION[s]
        assert f"{s}:{a:.6f}/{b:.6f}" in tail, f"{s} coefficients not in the fingerprint"


def test_epoch_was_bumped_past_the_last_old_basis_snapshot():
    """Rows dated at or before the epoch were ranked on the retired basis and are
    dropped by load_rank_history's strictly-after gate. The epoch must not still be
    2026-08-12: the 2026-08-13 board rows were built on the uncorrected basis, and
    feeding them to the movement engine publishes a basis change as player movement."""
    assert S.BOARD_RANK_BASIS_EPOCH >= "2026-08-13", (
        "epoch not bumped for the dispersion basis change")


def test_no_surface_asserts_an_unearned_accuracy_claim():
    """RATCHET. Four surfaces asserted "eFV out-ranks consensus" as fixed prose while
    the artifact they describe carries xfv_beats:false and "not resolvable at this
    power" on both sides. The hero was moved onto derived copy on 2026-08-13 and these
    were missed.

    An out-ranks claim is allowed ONLY inside a branch that the measurement selects.
    Grep-level, deliberately: the defect is prose, so prose is what is pinned."""
    import pathlib
    root = pathlib.Path(__file__).parent
    banned = ("out-ranks consensus", "OUT-RANKS", "out-ranks the scouting industry")
    # glossary.js is exempt: its two occurrences are inside _methEfvVerdict branches
    # that only render when beat.length says the measurement earned them.
    targets = ["data/glossary.json", "content/team.json", "prospx/index.html"]
    bad = []
    for t in targets:
        p = root / t
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.lstrip().startswith(("//", "#", "/*", "*")):
                continue          # the comments recording the defect are not the defect
            for b in banned:
                if b in line:
                    bad.append(f"{t}:{i}: {b}")
    assert not bad, (
        "unearned accuracy claim reintroduced; derive it from the backtest artifact "
        "or drop it:\n  " + "\n  ".join(bad))
