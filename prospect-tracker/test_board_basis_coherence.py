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
PINNED_MIX = {"top10": 0, "top25": 1, "top50": 2, "top100": 8}
PINNED_BASIS = "xfv_grade"


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
    assert got == PINNED_MIX, (
        f"top-N pitcher counts moved: {got} != {PINNED_MIX}. A basis flip, a "
        f"re-enabled side scale, or a model change landed. See the docstring.")


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


# ── the basis-coherence defect (open; A2 in the 2026-07-29 master plan) ──────
@pytest.mark.xfail(strict=True, reason=(
    "OPEN DEFECT, registered 2026-07-30. efv_score.score_history builds the eFV "
    "history series from the retired per-side quantile grade while the board serves "
    "storage.BOARD_GRADE_FIELD (raw xfv_grade), so the FV-history chart and "
    "movement.xfv_movement run on a different scale than the board. Fixing it needs a "
    "one-time history restamp with grade movement suppressed for the transition, "
    "because the owner's primary movement signal is the eFV delta and rebasing would "
    "otherwise publish 4-5 FV of phantom moves board-wide. When that lands this test "
    "XPASSes and the marker must be removed in the same commit."))
@pytest.mark.skipif(not (DATA / "xfv_history.json").exists(),
                    reason="needs a built xfv_history.json")
def test_history_series_is_on_the_board_basis():
    """The last point of a player's eFV history must equal the grade the board serves.

    Measured mismatch at registration time: jesus_made history 59.00 vs served 64.24;
    enrique_bradfield_jr 46.60 vs 50.97; ryan_sloan 54.80 vs 56.52 -- i.e. the history
    equals xfv_grade_quantile exactly, not the board number.
    """
    served = _active()
    hist = (json.loads((DATA / "xfv_history.json").read_text(encoding="utf-8"))
            .get("by_player") or {})
    bad = []
    for key, series in hist.items():
        row = served.get(key)
        if not row or not series:
            continue
        board = bs.board_value(row)
        last = (series[-1] or {}).get("x")
        if board is None or last is None:
            continue
        if abs(float(last) - float(board)) > 0.51:
            bad.append((key, float(last), float(board)))
    assert not bad, (
        f"{len(bad)} players whose eFV history tail disagrees with the board grade; "
        f"first 5: {bad[:5]}")
