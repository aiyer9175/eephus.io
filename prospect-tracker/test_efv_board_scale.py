"""W-SIDESCALE: the board scale is one definition, order-preserving, and the
TOP-N SIDE MIX is now a permanent gate.

The 2026-07-25 raw-grade unification shipped a top 25 with zero pitchers on it and
nothing in the suite noticed. test_top_n_side_mix_gate is that missing check.
"""
import json
import os
from pathlib import Path

import pytest

import efv_board_scale as bs

DATA = Path(__file__).parent / "data"


def _board(pool_kind=None):
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    bp = doc.get("by_player") or {}
    if pool_kind:
        bp = {k: v for k, v in bp.items() if (v or {}).get("kind") == pool_kind}
    return bp


# ── the scale itself ────────────────────────────────────────────────────────
def test_coefficients_reproduce_from_the_labeled_artifacts():
    """The shipped constants must be re-derivable from the recorded recipe, so the
    provenance in the docstring is checkable rather than a claim.

    Only meaningful while the scale is ENABLED. `fit_from_artifacts()` re-derives from
    data/xfv_scored*.json, which is a moving pool: the 2026-07-28 regen shifted it
    (grade-normalization rebuild, blend lambda, training-pool repairs), so the
    re-derivation now returns hit intercept -2.863787 against the shipped -2.603487.

    With the scale disabled (2026-07-29) those constants are inert -- calibrate() is
    the identity and test_disabled_is_exactly_the_identity pins that. Patching COEFFS
    to match a pool that moved for unrelated reasons would fake provenance rather than
    establish it, so the constants stay frozen exactly as shipped and recorded in
    data/xfv_board_scale_eval.json shipped_coeffs. If the scale is ever re-enabled it
    must be RE-FIT and re-gated, not patched, and this test becomes live again.
    """
    if not bs.enabled():
        pytest.skip("board scale disabled; frozen constants are inert, re-fit on any "
                    "re-enable rather than reconciling against a moved pool")
    f = bs.fit_from_artifacts()
    for side, (a, b) in bs.COEFFS.items():
        assert abs(f[side][0] - a) < 5e-5, f"{side} intercept drifted from the fit"
        assert abs(f[side][1] - b) < 5e-5, f"{side} slope drifted from the fit"


def test_calibration_is_strictly_order_preserving_within_a_side():
    """Affine with a positive slope. This is the property that keeps the visible
    grade column monotonic in board order -- the whole point of the unification."""
    for side, (_a, b) in bs.COEFFS.items():
        assert b > 0, f"{side} slope must be positive or the board column inverts"
    os.environ[bs.ENV_FLAG] = "1"
    try:
        for side in ("H", "P"):
            vals = [bs.calibrate(g / 10.0, side) for g in range(200, 801)]
            assert all(y >= x for x, y in zip(vals, vals[1:])), f"{side} map not monotonic"
    finally:
        os.environ.pop(bs.ENV_FLAG, None)


def test_stamping_is_idempotent_and_cannot_double_correct():
    doc = {"by_player": {"a": {"side": "P", "xfv_grade": 55.0},
                         "b": {"side": "H", "xfv_grade": 55.0}}}
    os.environ[bs.ENV_FLAG] = "1"
    try:
        bs.stamp_doc(doc)
        once = {k: v["xfv_grade"] for k, v in doc["by_player"].items()}
        bs.stamp_doc(doc)
        bs.stamp_doc(doc)
        twice = {k: v["xfv_grade"] for k, v in doc["by_player"].items()}
        assert once == twice, "re-stamping moved the grade: double correction"
        for rec in doc["by_player"].values():
            assert rec["xfv_grade_model_raw"] == 55.0
    finally:
        os.environ.pop(bs.ENV_FLAG, None)


def test_disabled_is_exactly_the_identity():
    """Default OFF must be byte-identical to the raw model grade, so wiring the seam
    cannot itself move a served number."""
    assert bs.enabled() is False
    for g in (20.0, 37.4, 59.2, 64.5, 75.2):
        for side in ("H", "P"):
            assert bs.calibrate(g, side) == g


# ── the permanent gate ──────────────────────────────────────────────────────
@pytest.mark.skipif(not (DATA / "xfv.json").exists(), reason="needs a built xfv.json")
def test_top_n_side_mix_gate():
    """PERMANENT GATE (acceptance check 1). A joint board that hands the entire top
    of the board to one side is a scale bug, not a scouting opinion. The bound is
    deliberately loose -- it is a tripwire for the 25H/0P class of regression, not a
    quota. F-SIDE's calibration-honest frame puts the top-25 pitcher share near 0.09
    (data/xfv_side_fairness_eval.json), so a board with ZERO pitchers in its top 50
    is out of family with our own side-fairness measurement.
    """
    mix = bs.top_n_side_mix(_board("active"))
    assert mix["top50"]["P"] >= 1, (
        f"no pitcher in the top 50 of the joint board: {mix}. Either the board scale "
        f"is not cross-side comparable (see efv_board_scale) or a basis flip landed "
        f"without re-running the side-mix gate.")
    assert mix["top100"]["P"] >= 5, f"top-100 pitcher count collapsed: {mix}"
    assert mix["top100"]["H"] >= 5, f"top-100 hitter count collapsed: {mix}"
    # Honest scope note: this bound is a COLLAPSE tripwire. On the 2026-07-25 raw
    # basis the live board reads 24H/1P at top 25 and 91H/9P at top 100, which passes
    # here -- so this test alone would NOT have caught that regression, only a total
    # one-side sweep. The side mix must still be REPORTED (efv_board_scale --mix) on
    # any change to the board basis; that report is the real gate.


@pytest.mark.skipif(not (DATA / "xfv.json").exists(), reason="needs a built xfv.json")
def test_board_number_is_monotonic_in_board_order():
    """Acceptance check 2. Sorting by the board number and reading the DISPLAYED
    (rounded) grade down the page must never go back up."""
    rows = []
    for k, rec in _board("active").items():
        v = bs.board_value(rec)
        if v is not None:
            rows.append((v, k))
    rows.sort(key=lambda r: (-r[0], r[1]))
    # eFV is the round-to-NEAREST exception to the repo's grades-round-UP rule.
    shown = [int(v + 0.5) for v, _k in rows]
    inversions = sum(1 for a, b in zip(shown, shown[1:]) if b > a)
    assert inversions == 0, f"{inversions} display inversions in board order"


@pytest.mark.skipif(not (DATA / "xfv_board_scale_eval.json").exists(),
                    reason="run tools/efv_board_scale_lab.py")
def test_recorded_gate_matches_the_eval_artifact():
    """The GATE record in the module docstring is the thing people will read instead
    of re-running the lab. It must not be allowed to drift away from the artifact it
    claims to summarise."""
    a = json.loads((DATA / "xfv_board_scale_eval.json").read_text(encoding="utf-8"))
    prim = a["outcome_functionals"]["identity_war"]
    g = bs.GATE["primary"]
    assert prim["point_gap55"] == g["point"]
    assert prim["paired_bootstrap"]["ci90"] == g["boot_ci90"]
    assert prim["permutation_null"]["p_two_sided"] == g["permutation_p_two_sided"]
    assert prim["verdict"] == "NULL", "the primary specification stopped being a null"
    assert a["shipped_coeffs"] == {s: list(c) for s, c in bs.COEFFS.items()}


@pytest.mark.skipif(not (DATA / "xfv.json").exists(), reason="needs a built xfv.json")
def test_board_readers_agree_with_the_module():
    """storage / build_site / prospx must all be on ONE number. The two python
    readers are checked directly; prospx reads the same stamped field."""
    import build_site
    bp = _board()
    grades = build_site._load_xfv_grades()
    checked = 0
    for k, rec in list(bp.items())[:2000]:
        want = bs.board_value(rec)
        if want is None or k not in grades:
            continue
        assert abs(grades[k] - want) < 1e-9, f"build_site disagrees on {k}"
        checked += 1
    assert checked > 100
