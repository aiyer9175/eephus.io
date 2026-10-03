# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eFV production seam (efv_score.py) unit tests.

Pins the flagship grade's three load-bearing invariants:
  1. the grade mapping efv_score uses is monotone in E[6yr WAR] (higher projected WAR
     never yields a lower grade -> the OOS rank edge holds);
  2. the eFV display grade rounds to NEAREST 0.1 -- the deliberate exception to the
     site's grades-round-UP (ceiling) rule;
  3. the live injury + Statcast+ tilt factors are bounded (Statcast at +/-18%), so an
     extreme live input can never blow up the WAR projection / grade / surplus.

Pure-data, no network, no writes.
"""
import json
import math
from pathlib import Path

import pytest

import efv_score

DATA = Path(efv_score.__file__).parent / "data"


# --------------------------------------------------------------------------
# 1. Monotonicity of the grade mapping efv_score scores through
# --------------------------------------------------------------------------
# efv_score does: xfv_grade = vf.outcome_implied_fv(xfv_war) -- the inverse of the
# pooled empirical outcome curve (2026-07-30; it was vf.realized_implied_fv before).
# We drive that EXACT seam (efv_score.vf) so the test tracks whatever function the
# production module actually calls, not a hand-picked stand-in.
WARS = [-3.0, -1.0, 0.0, 0.5, 1.0, 2.0, 4.0, 7.0, 12.0, 20.0, 35.0]


def test_board_grade_is_monotone_in_expected_war():
    oiv = efv_score.vf.outcome_implied_fv
    grades = [oiv(w) for w in WARS]
    assert all(g is not None for g in grades), "seam returned None for a real WAR input"
    # non-decreasing: a higher projected WAR is NEVER graded lower (ties allowed at floor/cap)
    for lo, hi in zip(grades, grades[1:]):
        assert hi >= lo - 1e-9, f"grade dropped as WAR rose: {lo} -> {hi}"
    # STRICTLY increasing off the clamps, which the retired map was NOT: its age and
    # position arguments made two rows with the same predicted WAR grade differently, and
    # the live board carried 86 hit / 52 pit within-side order violations because of it.
    # The board number is now a pure function of predicted WAR, so surplus's reliance on
    # the per-side rank quantile is safe by construction, not by measurement.
    interior = [(w, g) for w, g in zip(WARS, grades) if 20.0 < g < 80.0]
    for (w0, g0), (w1, g1) in zip(interior, interior[1:]):
        assert g1 > g0, f"grade did not strictly rise from WAR {w0} to {w1}"
    # and the mapping actually moves (not a constant) across the range
    assert grades[-1] > grades[0]
    # clamped to the 20-80 grade scale
    assert all(20.0 - 1e-9 <= g <= 80.0 + 1e-9 for g in grades)
    # a non-positive prediction reads exactly the FV20 floor, same as the retired map, so
    # the floor population does not move when the basis does
    assert oiv(0.0) == 20.0 and oiv(-5.0) == 20.0


@pytest.mark.parametrize("is_pit", [False, True])
@pytest.mark.parametrize("age,pos", [(None, None), (21.0, "SS"), (26.0, "RP")])
def test_odds_grade_is_monotone_in_expected_war(is_pit, age, pos):
    """The retired map still runs, on purpose: it keys p_bucket / p_bust, which were
    ground-truthed on it. Its monotonicity is still load-bearing for the odds, so it is
    still pinned -- it just is not the board number any more."""
    riv = efv_score.vf.realized_implied_fv
    grades = [riv(w, is_pit, age=age, position=pos) for w in WARS]
    assert all(g is not None for g in grades), "seam returned None for a real WAR input"
    for lo, hi in zip(grades, grades[1:]):
        assert hi >= lo - 1e-9, f"grade dropped as WAR rose: {lo} -> {hi}"
    assert grades[-1] > grades[0]
    assert all(20.0 - 1e-9 <= g <= 80.0 + 1e-9 for g in grades)


# --------------------------------------------------------------------------
# 2. eFV display grade rounds to NEAREST 0.1 (the exception to grades-round-UP)
# --------------------------------------------------------------------------
# efv_score stores the grade as round(xfv_grade, 1) (run / run_live / run_backgrade).
# That is round-to-nearest, NOT math.ceil -- the documented eFV exception to the
# site-wide "grades display the ceiling" rule.
def test_display_grade_rounds_to_nearest_not_up():
    oiv = efv_score.vf.outcome_implied_fv
    # RESTAMPED 2026-09-04 for the eWAR label epoch: the pooled FV outcome curve was refit
    # on the rebased label, so oiv(2.0) moved 44.535 -> 44.333. The test's POINT is intact
    # and re-verified rather than assumed: 44.333 is still a clean non-integer, 0.33 from
    # the nearest whole grade, and 44.3 is still a round DOWN, which a ceiling rule could
    # never produce. Only the pinned value moved.
    # RESTAMPED 2026-10-03 for the fWAR label epoch (runbook step I): the pooled curve was
    # refit on the fWAR training label at RESOLVED_THROUGH 2026 (hash baa9676f90a6), so
    # oiv(2.0) moved 44.333 -> 44.352, which rounds UP to 44.4 and can no longer show a
    # round DOWN. The probe moves to 1.98 WAR (oiv 44.320, 0.03 inside the 44.35 boundary),
    # so every assertion below keeps its meaning: a clean non-integer, rounded to the
    # nearest tenth, DOWN, never the ceiling. Only the probe point and the pin moved.
    raw = oiv(1.98)                             # lands at ~44.320 (a clean non-integer)
    assert raw is not None and abs(raw - round(raw)) > 0.05, "need a fractional raw grade"
    efv_display = round(raw, 1)                 # the convention efv_score applies
    # rounds to the nearest tenth -- here DOWN, which the ceiling rule could never do
    assert efv_display == pytest.approx(44.3, abs=1e-9)
    assert efv_display < raw                    # rounded down -> definitively not a ceiling
    assert efv_display != math.ceil(raw)        # grades-round-UP would give 45; eFV does not


def test_committed_grades_carry_the_round_to_nearest_signature():
    """The shipped artifact proves the rule in production: eFV grades sit on a 0.1
    grid AND many are non-integers -- impossible if they were integer-ceiled like FV."""
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    grades = [e["xfv_grade"] for e in doc["by_player"].values() if e.get("xfv_grade") is not None]
    assert grades, "no eFV grades in the committed artifact"
    assert all(abs(g - round(g, 1)) < 1e-9 for g in grades), "grades not quantized to 0.1"
    non_integer = [g for g in grades if abs(g - round(g)) > 1e-9]
    # a real share are non-integers -> not the integer round-UP convention FV grades use
    assert len(non_integer) > 0.1 * len(grades)


# --------------------------------------------------------------------------
# 3. Live tilt factors are bounded on extreme inputs
# --------------------------------------------------------------------------
def test_injury_factor_bounds():
    # every LIVE multiplier stacked at its worst -> bounded, never above 1.0
    worst = {"il_on": True, "il_type": "60-day IL", "il_days_12mo": 400.0,
             "il_stints_12mo": 9.0, "is_post_tj": True}
    f = efv_score._injury_factor(worst, is_pit=True)
    assert 0.5 <= f <= 1.0
    # 0.70 * 0.82 * 0.92 (post-TJ no longer multiplies - owner 2026-07-15)
    assert f == round(0.70 * 0.82 * 0.92, 3), \
        "stacked worst case must be the three LIVE components only"
    # a healthy record is a no-op
    assert efv_score._injury_factor({}, is_pit=True) == 1.0
    # Owner directive 2026-07-15: post-TJ STATUS alone (fully recovered, zero
    # IL time - the Kade Anderson case) is NOT an injury and carries NO penalty.
    assert efv_score._injury_factor({"is_post_tj": True}, is_pit=True) == 1.0
    # Owner directive 2026-07-17: a currently-HEALTHY player carries NO penalty
    # regardless of trailing-12mo IL time (the Josue Briceno case: activated off
    # a 60-day stint with ~108 trailing IL days must clear to exactly 1.0).
    assert efv_score._injury_factor({"il_on": 0, "il_days_12mo": 108.0}, is_pit=True) == 1.0
    assert efv_score._injury_factor({"il_days_12mo": 400.0, "il_stints_12mo": 9.0}, is_pit=True) == 1.0
    # missing / None fields (the only non-numeric the live board ever produces)
    # never throw or escape the band
    for r in ({"il_days_12mo": None}, {"il_on": True, "il_type": None},
              {"il_stints_12mo": None}, {"is_post_tj": True}):
        assert 0.5 <= efv_score._injury_factor(r, is_pit=True) <= 1.0


def test_injury_factor_short_il_is_days_aware():
    """B1 (2026-07-30) companion to test_injury_factor_bounds.

    The MiLB 7-day IL is the default landing spot for ANY minor-league injury, so
    the designation carries no severity information and used to price at the same
    0.90 as an unclassified serious one. Measured case: seth_hernandez, il_type
    '7-day', FOUR trailing IL days, one stint -> 0.90 -> -1.25 FV -> 18 board spots.
    """
    def f(**kw):
        return efv_score._injury_factor({"il_on": 1, **kw}, is_pit=True)

    # 1. A handful of IL days cannot cost anywhere near 10% of projected WAR.
    #    The measured seth_hernandez row: 4 days, 1 stint on the 7-day IL.
    assert f(il_type="7-day", il_days_12mo=4.0, il_stints_12mo=1.0) > 0.97
    # 2. ... but a genuinely long absence still does. The mild ramp saturates at
    #    the INCUMBENT flat value, so nothing at or past the saturation point moved.
    assert f(il_type="7-day", il_days_12mo=efv_score._IL_MILD_FULL_DAYS,
             il_stints_12mo=1.0) == pytest.approx(efv_score._IL_MILD_FLOOR, abs=1e-9)
    assert f(il_type="7-day", il_days_12mo=200.0, il_stints_12mo=1.0) == \
        pytest.approx(round(efv_score._IL_MILD_FLOOR * 0.82, 3), abs=1e-9)
    # 3. Monotone non-increasing in days missed, and never outside the band.
    prev = 1.0
    for d in range(0, 400, 5):
        v = f(il_type="7-day", il_days_12mo=float(d), il_stints_12mo=1.0)
        assert 0.5 <= v <= 1.0
        assert v <= prev + 1e-9, f"factor rose as days rose at {d}"
        prev = v
    # 4. The severity types are NOT days-scaled (the type is informative there),
    #    and the MiLB full-season IL has its own branch instead of falling through
    #    to the mild one -- otherwise a season-ending injury with few accumulated
    #    days would be RELIEVED.
    #    OWNER DECISION 2026-07-30 (B1b): full-season prices AT the 60-day severity,
    #    on the ground that out for the year cannot be milder than out for two months.
    #    It was pinned to the incumbent 0.90 pending authorization; that is now taken,
    #    so this pins the decided value rather than a one-sided bound.
    assert f(il_type="60-day", il_days_12mo=1.0) == pytest.approx(0.70, abs=1e-9)
    assert f(il_type="60-day", il_days_12mo=45.0) == pytest.approx(0.70, abs=1e-9)
    assert efv_score._IL_FULL_SEASON == pytest.approx(efv_score._IL_SEVERE, abs=1e-12)
    assert f(il_type="full-season", il_days_12mo=7.0) == pytest.approx(0.70, abs=1e-9)
    # ... and it must behave exactly like the 60-day type across the whole day range,
    # including the chronicity modifiers, rather than merely sharing its base value.
    # Measured: the base holds flat to 0.70 through 45 days, then the >=60 and >=120
    # day modifiers bite (0.63 at 60, 0.574 at 120+). A season-ending injury is never
    # RELIEVED by having few accrued days, which is the defect this branch exists for.
    for _d in (0.0, 7.0, 45.0, 60.0, 120.0, 200.0):
        assert f(il_type="full-season", il_days_12mo=_d) == \
            pytest.approx(f(il_type="60-day", il_days_12mo=_d), abs=1e-9), f"days {_d}"
    assert f(il_type="full-season", il_days_12mo=0.0) == pytest.approx(0.70, abs=1e-9)
    assert f(il_type="full-season", il_days_12mo=120.0) == pytest.approx(0.574, abs=1e-3)
    # 5. An ACTIVE stint with zero trailing days AND zero trailing stints is a
    #    placement older than the 12-month window (the LONGEST absences on the
    #    board, 29 live rows), not a fresh one -- it must not get the day-0 pass.
    assert f(il_type="7-day", il_days_12mo=0.0, il_stints_12mo=0.0) == \
        pytest.approx(efv_score._IL_MILD_FLOOR, abs=1e-9)
    # ... while a player placed TODAY carries a stint and IS at day 0.
    assert f(il_type="7-day", il_days_12mo=0.0, il_stints_12mo=1.0) == \
        pytest.approx(efv_score._IL_MILD_DAY0, abs=1e-9)
    # 6. The two standing owner directives are untouched by the days-awareness.
    assert efv_score._injury_factor({"il_on": 0, "il_type": "7-day",
                                     "il_days_12mo": 118.0}, is_pit=True) == 1.0   # healthy = no penalty
    assert efv_score._injury_factor({"is_post_tj": True}, is_pit=True) == 1.0       # post-TJ status alone


def test_injury_factor_matches_the_committed_live_board():
    """The (type, days, stints) shapes the shipped live matrices actually carry stay
    inside the band, and B1's SHORT-IL relief only ever moves a live row UP.

    B1b EXCEPTION, owner decision 2026-07-30: full-season rows move DOWN on purpose
    (0.90 -> 0.70, the 60-day severity), because a season-ending injury cannot be
    milder than a two-month one. That is the whole content of the decision, so it is
    carved out explicitly here rather than weakening the no-harsher invariant for every
    type - the invariant is what proves the short-IL fix is a pure relief, and it stays
    strict for the 7-day and unclassified rows it was written about."""
    def retired(r):
        t = str(r.get("il_type") or "").lower()
        f = 0.70 if "60" in t else (0.82 if ("15" in t or "10" in t) else 0.90)
        days = float(r.get("il_days_12mo") or 0.0)
        if days >= 120:
            f *= 0.82
        elif days >= 60:
            f *= 0.90
        if float(r.get("il_stints_12mo") or 0.0) >= 3:
            f *= 0.92
        return round(max(0.5, f), 3)

    seen = set()
    for fn in ("xfv_live_hitter_matrix.json", "xfv_live_pitcher_matrix.json"):
        p = DATA / fn
        if not p.exists():                       # matrices are build artifacts
            pytest.skip(f"{fn} not built")
        for r in json.loads(p.read_text(encoding="utf-8")):
            if not r.get("il_on"):
                assert efv_score._injury_factor(r, is_pit=True) == 1.0
                continue
            new, old = efv_score._injury_factor(r, is_pit=True), retired(r)
            assert 0.5 <= new <= 1.0
            t = str(r.get("il_type") or "").lower()
            if any(k in t for k in efv_score._IL_FULL_SEASON_TYPES):
                # B1b: deliberately harsher, and it must land exactly on the severity
                # value rather than drifting somewhere between the two policies.
                assert new <= old + 1e-9, "full-season should not be RELIEVED"
                assert new == pytest.approx(retired({**r, "il_type": "60-day"}),
                                            abs=1e-9), (
                    f"full-season must price as 60-day: {r.get('il_days_12mo')}d -> {new}")
            else:
                assert new >= old - 1e-9, (
                    f"B1 made a live row HARSHER: {r.get('il_type')} "
                    f"{r.get('il_days_12mo')}d {r.get('il_stints_12mo')}st {old} -> {new}")
            seen.add(str(r.get("il_type")))
    # the live board only ever produces these three designations
    assert seen <= {"7-day", "60-day", "full-season"}, seen


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_statcast_factor_bounded_pm18pct(side):
    # SC+ is a 100-centered index; extreme values on either side clamp to +/-18%
    hi = efv_score._statcast_factor({"statcast_plus": 10_000}, side)
    lo = efv_score._statcast_factor({"statcast_plus": -10_000}, side)
    assert hi == pytest.approx(1.18, abs=1e-9)
    assert lo == pytest.approx(0.82, abs=1e-9)
    # every input stays inside the band
    for sc in (40, 70, 100, 130, 160, 1e9, -1e9):
        assert 0.82 <= efv_score._statcast_factor({"statcast_plus": sc}, side) <= 1.18
    # no Statcast+ (lower levels) or non-numeric -> untouched
    assert efv_score._statcast_factor({}, side) == 1.0
    assert efv_score._statcast_factor({"statcast_plus": None}, side) == 1.0
    assert efv_score._statcast_factor({"statcast_plus": "n/a"}, side) == 1.0


# ── the explainer top-N cut, adjudicated 2026-08-07 (Lane F5) ───────────────
# The owner's question, from the Arias attribution replay: obp_rel is the third-largest
# term in his ledger and almost never clears the top-4 cut, so a reader cannot see a
# feature that moved a board grade. The cut is KEPT (the card ranks by contribution size
# on this player today; the replay ranks by movement between two model vintages, and
# obp_rel clears the 0.05 reporting floor on only 154 of 4,586 live actives, so widening
# would not surface it) and the admission that something WAS cut is what shipped. These
# pin the two properties that decision rests on.


def _ridge_stub(keys, weights):
    return {"keys": list(keys), "mu": [0.0] * len(keys), "sd": [1.0] * len(keys),
            "w": list(weights)}


def test_the_top_cut_is_exactly_a_slice_of_the_uncut_list():
    """run_live computes the groups UNCUT and slices, so the remainder it reports is a
    measured quantity rather than an inference. That is only sound if slicing the uncut
    list reproduces the cut list exactly, which holds because collapse() sorts by
    magnitude BEFORE it truncates. If a future collapse() ever filtered after the cut,
    factors_more would start counting rows that were never candidates."""
    keys = ["obp_rel", "bb_rel", "iso_rel", "level_rank", "n_sources", "fv_stddev"]
    ridge = _ridge_stub(keys, [0.90, 0.70, 0.50, 0.30, 0.20, 0.10])
    feats = {k: 1.0 for k in keys}
    uncut = efv_score._factors(ridge, feats, top=None, side="hit")
    cut = efv_score._factors(ridge, feats, side="hit")
    assert len(uncut) == 6, f"the stub should clear the 0.05 floor six times: {uncut}"
    assert cut == uncut[:efv_score._EXPLAINER_TOP]
    assert len(cut) == efv_score._EXPLAINER_TOP


def test_the_cut_list_is_ordered_biggest_first_so_the_remainder_is_the_small_end():
    """"and N smaller factors" is a claim about magnitude, not just about count. It is
    only true if the cut takes the LARGEST groups, so the hidden set can never contain a
    group bigger than one that was shown."""
    keys = ["obp_rel", "bb_rel", "iso_rel", "level_rank", "n_sources", "fv_stddev"]
    ridge = _ridge_stub(keys, [0.10, 0.90, 0.20, 0.70, 0.30, 0.50])
    feats = {k: 1.0 for k in keys}
    uncut = efv_score._factors(ridge, feats, top=None, side="hit")
    mags = [f["mag"] for f in uncut]
    assert mags == sorted(mags, reverse=True), mags
    shown, hidden = uncut[:efv_score._EXPLAINER_TOP], uncut[efv_score._EXPLAINER_TOP:]
    assert hidden, "the stub is meant to overflow the cut"
    assert min(f["mag"] for f in shown) >= max(f["mag"] for f in hidden)


def test_a_short_ledger_reports_no_remainder_at_all():
    """A reader must never be told "and 0 smaller factors". Fewer groups than the cut
    depth means nothing was dropped and the payload field is absent."""
    keys = ["obp_rel", "bb_rel"]
    ridge = _ridge_stub(keys, [0.40, 0.20])
    feats = {k: 1.0 for k in keys}
    uncut = efv_score._factors(ridge, feats, top=None, side="hit")
    assert len(uncut) == 2
    assert uncut[efv_score._EXPLAINER_TOP:] == []


def test_injury_penalty_is_pitcher_only_and_says_why():
    """Owner decision 2026-09-04: the live IL haircut applies to PITCHERS ONLY.

    This is not a preference, it is a measured sign. On the full pool including busts,
    with the scouting grade, age and rostered-exposure proxies partialled out, being on
    the injured list at the decision point predicts:

        pitchers  n=1,220  rho -0.1664  CI95 [-0.2228, -0.1087]  -> penalty SUPPORTED
        hitters   n=1,127  rho +0.0651  CI95 [+0.0021, +0.1282]  -> CONTRAINDICATED

    The hitter interval sits ABOVE zero, so the old both-sides haircut was subtracting
    grade, rank and dollars from 225 served hitters against the evidence, at a median
    x0.738. Exposure control is what makes the number readable at all: a player cannot be
    placed on an injured list unless he is rostered, so "no IL record" means never-exposed
    as often as it means healthy. Artifact: data/xfv_health_profile_eval.json,
    penalty_verdict. Ship record: docs/efv-2026-09-03/DRIVER_SWEEP_VOLUME_AND_LEVEL.md.

    If this test goes red because the constant changed, the question to answer first is
    whether the MEASUREMENT moved, not whether the constant should be widened back.
    """
    hurt = {"il_on": 1, "il_type": "60-day", "il_days_12mo": 130.0, "il_stints_12mo": 3.0}

    assert efv_score.INJURY_PENALTY_SIDES == frozenset({"pit"})

    # the pitcher path is untouched: the severity machinery still bites
    pit = efv_score._injury_factor(hurt, is_pit=True)
    assert 0.5 <= pit < 1.0, "the pitcher haircut must still apply"

    # the hitter path is a hard no-op, on every shape the live board produces
    assert efv_score._injury_factor(hurt, is_pit=False) == 1.0
    for extra in ({}, {"is_post_tj": True}, {"il_days_12mo": 400.0},
                  {"il_type": "full-season"}, {"il_stints_12mo": 9.0}):
        assert efv_score._injury_factor({**hurt, **extra}, is_pit=False) == 1.0

    # the side may be carried on the row instead of passed, and must give the same answer
    assert efv_score._injury_factor({**hurt, "is_pitcher": True}) == pit
    assert efv_score._injury_factor({**hurt, "is_pitcher": False}) == 1.0

    # a caller that forgets the argument entirely gets the SAFE side. An unproven penalty
    # is a live subtraction, so defaulting to "no haircut" fails toward not taxing someone
    # the evidence does not convict.
    assert efv_score._injury_factor(hurt) == 1.0


def test_injury_penalty_sides_is_in_the_board_fingerprint():
    """The haircut is a multiplicative overlay on the served grade, so the coordination
    device has to be able to see it. Every other term in that string was added AFTER
    something moved every served grade while the fingerprint stayed byte-identical; this
    one was added in the same commit as the change it guards."""
    import storage
    fp = storage.board_basis_fingerprint()
    assert "injsides=" in fp
    assert "injsides=pit" in fp
    assert fp == storage.BOARD_BASIS_FINGERPRINT
