# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The positional ladder's zero, and the two sums that are NOT it.

Asked again on 2026-08-03: the Fitted (runs/650) column does not add to zero,
and by definition it should. Half right. The adjustment is centred on an
EXPOSURE-WEIGHTED sum, which positional_fit._recentre imposes exactly; adding
the nine displayed rungs with equal weight is a different quantity and is not
zero, because DH is about 7% of league exposure rather than a ninth, so the
large negative DH rung gets counted nine times too heavily.

The model has documented that since 2026-07-31 and publishes all three sums in
`ladder.identification`. The page could not say any of it, for two reasons
this file now guards:

  1. `build_positional_fit_payload` did not forward the block, and
  2. the SERVED artifact was generated 2026-07-24, a week BEFORE the block
     existed, so even the source data could not answer the question.

So the number was right and unexplainable at the same time, which is
indistinguishable from wrong to anyone checking it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
FIELDERS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]


def _ladder(name: str, key_path: tuple[str, ...]):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"data/{name} not built")
    doc = json.loads(p.read_text(encoding="utf-8"))
    for k in key_path:
        doc = (doc or {}).get(k) or {}
    if not doc.get("values"):
        pytest.skip(f"data/{name}: no fitted ladder")
    return doc


def test_recentring_zeroes_the_weighted_sum_exactly():
    """The invariant itself, independent of any artifact, so it is checkable
    today rather than after the next regen.

    _recentre subtracts a SCALAR from every rung, which only zeroes the
    weighted sum if the weights themselves sum to 1. They do: _ladder_design
    divides each row of innings by that row's total, so every row of X sums to
    1 and so does their column mean. If a future edit ever stops normalizing
    the design, the centring silently stops centring and this catches it.
    """
    np = pytest.importorskip("numpy")
    import positional_fit as pf

    rng = np.random.default_rng(11)
    X = rng.random((500, len(pf.LADDER_POSITIONS)))
    X = X / X.sum(axis=1, keepdims=True)          # the design's own convention
    exposure = X.mean(axis=0)
    assert abs(exposure.sum() - 1.0) < 1e-12, "weights must sum to 1"

    raw = rng.normal(size=len(pf.LADDER_POSITIONS)) * 10
    beta = pf._recentre(raw, exposure)
    assert abs(float(exposure @ beta)) < 1e-9, (
        "the exposure-weighted sum of the recentred ladder must be zero")
    # And the SHAPE is untouched: recentring is a level shift, not a rescale.
    assert np.allclose(np.diff(raw), np.diff(beta))


def test_exposure_weighted_sum_is_the_zero():
    """The identity that IS claimed. Skips on a pre-2026-07-31 artifact, which
    predates the block rather than failing it."""
    L = _ladder("positional_fit.json", ("fit", "ladder"))
    ident = L.get("identification")
    if not ident:
        pytest.skip("artifact predates the identification block (regen owed)")
    assert abs(float(ident["sum_exposure_weighted"])) < 1e-6, (
        "the exposure-weighted sum is the imposed identification and must be "
        f"zero, got {ident['sum_exposure_weighted']}")


def test_the_equal_weight_sums_are_reported_and_are_not_zero():
    """The two quantities people actually add up. Publishing them is the whole
    point: an unexplained non-zero reads as a bug."""
    L = _ladder("positional_fit.json", ("fit", "ladder"))
    ident = L.get("identification")
    if not ident:
        pytest.skip("artifact predates the identification block (regen owed)")

    vals = L["values"]
    assert abs(sum(vals.values()) - float(ident["sum_equal_weight_9"])) < 0.02
    assert abs(sum(vals[p] for p in FIELDERS if p in vals)
               - float(ident["sum_equal_weight_fielders"])) < 0.02
    # If either of these were ever zero the explanation would be wrong.
    assert abs(float(ident["sum_equal_weight_9"])) > 0.1
    assert ident.get("why_equal_weight_sums_are_not_zero")


def test_the_ui_payload_forwards_the_identification_block():
    """The page cannot explain the sum if the slim payload drops it. Guards the
    forwarding itself, so this does not silently regress when the payload is
    next trimmed."""
    import build_site
    import inspect
    src = inspect.getsource(build_site.build_positional_fit_payload)
    assert '"identification"' in src, (
        "build_positional_fit_payload no longer forwards ladder.identification, "
        "so /pal/ cannot say which sum is zero")


def test_pal_renders_the_sum_explanation_when_present():
    js = (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")
    assert "sum_exposure_weighted" in js, (
        "assets/pal.js does not surface the exposure-weighted sum")
    assert "identification" in js
    # Must degrade: the deployed artifact predates the block.
    assert "L.identification || null" in js, (
        "the explanation must render only when the artifact carries the block")


# --------------------------------------------------------------------------- #
# THE DISPLAY LAYER (owner decision 2026-08-04).
#
# Everything above pins the MODEL, and none of it moves: the exposure-weighted
# sum is still the imposed identification, the two equal-weight sums are still
# non-zero and still published. What changed is which column the /pal/ table
# PRINTS. The owner kept reading -3.96 off the page and reading it as a broken
# table, because the identity a reader checks by hand is the folklore one: the
# EIGHT FIELDING rungs sum to zero. The artifact already published exactly that
# column (`identification.values_fielder_centred`), so the page now prints it,
# with DH shown against the same line. The two columns differ by one constant
# (the fielder mean, 1.22 runs here), so every gap between two positions is
# identical and nothing downstream changes basis.
# --------------------------------------------------------------------------- #
def test_displayed_fielder_column_sums_to_zero():
    """The whole point of the display change. Tolerance is rounding, not slack:
    each rung is published to 2 dp, so eight of them can drift at most
    8 x 0.005 = 0.04 from the exact zero the centring imposes."""
    L = _ladder("positional_fit.json", ("fit", "ladder"))
    ident = L.get("identification")
    if not ident:
        pytest.skip("artifact predates the identification block (regen owed)")
    fc = ident.get("values_fielder_centred")
    assert fc, "the artifact must publish the fielder-centred column the page prints"
    s8 = sum(float(fc[p]) for p in FIELDERS if p in fc)
    assert abs(s8) < 0.05, (
        f"the displayed runs/650 column must sum to 0.000 over the eight "
        f"fielding positions, got {s8:.3f}")
    # DH is NOT in that sum, and it is shown against the same line, so it must
    # have absorbed the whole shift: fielder-centred DH sits below model DH.
    assert float(fc["DH"]) < float(L["values"]["DH"])


def test_display_change_is_a_level_shift_only():
    """The guarantee that makes the display change safe: one constant separates
    the two columns, so every DIFFERENCE between positions - which is the entire
    content of a positional adjustment - is untouched."""
    L = _ladder("positional_fit.json", ("fit", "ladder"))
    ident = L.get("identification")
    if not ident or not ident.get("values_fielder_centred"):
        pytest.skip("artifact predates the fielder-centred column (regen owed)")
    fc, vals = ident["values_fielder_centred"], L["values"]
    deltas = [float(fc[p]) - float(vals[p]) for p in vals if p in fc]
    assert max(deltas) - min(deltas) < 0.02, (
        "fielder-centring must be a pure level shift, not a rescale")


def test_ui_payload_selects_the_fielder_centred_column_for_display():
    """Guards the selection itself. `values` must STILL be forwarded: the CIs,
    the folklore diffs and every downstream valuation are on that basis."""
    import inspect

    import build_site
    src = inspect.getsource(build_site.build_positional_fit_payload)
    assert "values_fielder_centred" in src, (
        "build_positional_fit_payload no longer selects the fielder-centred "
        "column, so /pal/ prints a runs/650 table that does not add to zero")
    assert '"valuesDisplay"' in src
    assert '"values": ladder.get("values")' in src, (
        "the exposure-centred column must still be forwarded for the CIs and "
        "for downstream consumers")

    js = (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")
    assert "L.valuesDisplay" in js, "the pal.js ladder does not read the display column"
    assert "valuesDisplayBasis" in js, (
        "pal.js must know which basis it is printing so the explainer text "
        "matches the numbers on older artifacts")


def test_served_payload_prints_a_zero_summing_fielder_column():
    """The end of the chain: the file the browser actually fetches. Skips until
    the next site build regenerates it, rather than failing on a payload that
    predates the decision."""
    p = ROOT / "data" / "positional_fit_ui.json"
    if not p.exists():
        pytest.skip("data/positional_fit_ui.json not built")
    lad = (json.loads(p.read_text(encoding="utf-8")).get("ladder") or {})
    if lad.get("valuesDisplayBasis") != "fielder_centred":
        pytest.skip("served payload predates the display decision (rebuild owed)")
    disp = lad.get("valuesDisplay") or {}
    s8 = sum(float(disp[p_]) for p_ in FIELDERS if p_ in disp)
    assert abs(s8) < 0.05, (
        f"the served runs/650 column must sum to 0.000 over the eight fielding "
        f"positions, got {s8:.3f}")
