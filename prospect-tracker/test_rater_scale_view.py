"""A-CLAIM-13: the rater scale view, and the controls that make it readable.

WHAT THIS LANE MEASURES. Each rater's ordering inside side x base-year blocks, beside its
pooled ordering on the same rows. The gap is how much of a rater's published Spearman is
block scale rather than within-cohort skill.

THE THREE MISTAKES THESE TESTS EXIST FOR, and the third was made:

  1. COMPARING TWO POPULATIONS. The pooled leg must be computed on the rows the block leg
     KEPT, or the delta mixes the normalization with the blocks that fell under the
     minimum.
  2. PUBLISHING FOUR NUMBERS SIDE BY SIDE WITH NO FLOOR. Four block rhos next to each other
     is a comparison whether or not it is labelled one.
  3. TRUSTING A ONE-DRAW PLACEBO. The first build permuted the block labels ONCE, and that
     single draw said the transform accounted for all of eFV's loss and none of the
     raters'. At 200 permutations that reading reverses. A placebo with no distribution
     cannot tell a mean from a draw.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "source_backtest.json"
DOC = ROOT / "docs" / "efv-2026-09-06" / "RATER_SCALE_VIEW.md"
RATERS = ("fangraphs", "mlb_pipeline", "prospx_consensus", "xfv")
PUBLISHED = ("fangraphs", "mlb_pipeline", "prospx_consensus")

# --------------------------------------------------------------------------
# The step A record (2026-10-03, POSTEPOCH_3_RATER_SCALE_VIEW_REREAD)
# --------------------------------------------------------------------------
# On the fWAR label (epoch step Q) the three A-CLAIM-13 findings below no longer
# hold. The doc records that as a dated section rather than editing the
# 2026-09-06 text. Two things are pinned from then on:
#   * the PRE-EPOCH state, per rater, against the step A copy of the artifact
#     (eWAR v2 label), exactly as it was: the sign flip and the placebo findings
#     held, and the base-year finding held for mlb_pipeline and
#     prospx_consensus but NOT for fangraphs (-0.01808 against 0.0182);
#   * the SERVED state, which must equal the STATE lines of the doc's latest
#     dated section, so any further move fails and asks for a new section.
SNAPSHOT_DIRNAME = "_pre_epoch_fwar_2026-10"
SNAPSHOT_SHA256 = "0f76e33bd3eceeaecc93b543a16020d969f36b37a4b56f6951894117a2f5e614"
STEP_A_STATE = {
    "sign_agree": False,
    "fangraphs": {"inside_band": False, "year_effect_resolves": False},
    "mlb_pipeline": {"inside_band": False, "year_effect_resolves": True},
    "prospx_consensus": {"inside_band": False, "year_effect_resolves": True},
}


def _main_checkout(start: Path):
    """The main checkout's root. In a git worktree `.git` is a FILE whose
    'gitdir: <main>/.git/worktrees/<name>' line names it; in the main checkout
    `.git` is a directory and its parent is the root."""
    for d in (start, *start.parents):
        g = d / ".git"
        if g.is_dir():
            return d
        if g.is_file():
            try:
                line = g.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            m = re.match(r"gitdir:\s*(.+?)[\\/]\.git[\\/]worktrees[\\/][^\\/]+[\\/]?$", line)
            return Path(m.group(1)) if m else None
    return None


def _snapshot_file():
    """The step A copy of source_backtest.json, or None when none is found.
    PRE_EPOCH_FWAR_SNAPSHOT may name the snapshot directory or the file."""
    env = os.environ.get("PRE_EPOCH_FWAR_SNAPSHOT")
    if env:
        p = Path(env)
        f = p / "source_backtest.json" if p.is_dir() else p
        return f if f.is_file() else None
    main = _main_checkout(ROOT)
    if main is None:
        return None
    f = main / SNAPSHOT_DIRNAME / "source_backtest.json"
    return f if f.is_file() else None


def _scale_state(art: dict) -> dict:
    """The three A-CLAIM-13 findings read off one build, per rater where the
    finding is per rater."""
    a = art["accuracy"]
    v = a["per_year_scale_view"]
    pooled = a["head_to_head_by_frame"]["vintage_matched"]["delta"]
    block = (v["gaps_on_this_view"]["xfv_vs_prospx_consensus"]
             ["floor_E_cond_in_run"]["point_delta"])
    out = {"sign_agree": pooled * block > 0, "_pooled": pooled, "_block": block}
    year = v["attribution"]["year_only"]["per_rater"]
    for r in PUBLISHED:
        f = year[r]["floor_E_cond_in_run"] or {}
        out[r] = {
            "inside_band": bool(v["per_rater"][r]["observed_inside_placebo_band"]),
            "year_effect_resolves": abs(year[r]["delta_block_minus_pooled"]) > f["mde95"],
            "_year_delta": year[r]["delta_block_minus_pooled"],
            "_year_floor": f["mde95"],
        }
    return out


def _doc_state(step_a: bool = False) -> dict:
    """STATE lines of the doc's LATEST dated section ('## YYYY-MM-DD: ...').
    Lines labelled step_a carry the pre-epoch state; the rest the served one."""
    txt = DOC.read_text(encoding="utf-8")
    heads = list(re.finditer(r"(?m)^## \d{4}-\d{2}-\d{2}\b.*$", txt))
    assert heads, f"{DOC.name} has no dated section carrying STATE lines"
    body = txt[heads[-1].start():]
    state: dict = {}
    for line in body.splitlines():
        toks = line.strip().split()
        if not toks or toks[0] != "STATE":
            continue
        toks = toks[1:]
        is_a = bool(toks) and toks[0] == "step_a"
        if is_a:
            toks = toks[1:]
        if is_a != step_a:
            continue
        kv = dict(t.split("=", 1) for t in toks)
        rater = kv.pop("rater", None)
        vals = {k: {"true": True, "false": False}[v] for k, v in kv.items()}
        if rater:
            state.setdefault(rater, {}).update(vals)
        else:
            state.update(vals)
    assert state, (f"the latest dated section of {DOC.name} carries no "
                   f"{'step_a ' if step_a else ''}STATE lines")
    return state


NO_SNAPSHOT = ("no step A snapshot found: set PRE_EPOCH_FWAR_SNAPSHOT or keep "
               f"<main checkout>/{SNAPSHOT_DIRNAME}/source_backtest.json")


def _step_a_state():
    """The step A state per rater, or None when no snapshot is found. A file that
    is found but is not the step A copy FAILS; it is never skipped."""
    f = _snapshot_file()
    if f is None:
        return None
    raw = f.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == SNAPSHOT_SHA256, (
        f"{f} is not the step A copy (sha256 {sha}, pinned {SNAPSHOT_SHA256})")
    man = f.parent / "MANIFEST.json"
    if man.is_file():
        want = (json.loads(man.read_text(encoding="utf-8"))
                .get("files", {}).get("data/source_backtest.json", {}).get("sha256"))
        assert want == sha, (
            f"{f} does not match its MANIFEST.json entry ({want} against {sha})")
    return _scale_state(json.loads(raw.decode("utf-8")))


@pytest.fixture(scope="module")
def view():
    if not ART.exists():
        pytest.skip("data/source_backtest.json has not been built")
    v = (json.loads(ART.read_text(encoding="utf-8"))
         .get("accuracy", {}).get("per_year_scale_view"))
    if not v or v.get("status"):
        pytest.skip(f"scale view not computed: {(v or {}).get('status')}")
    return v


# --------------------------------------------------------------------------
# It is a view, and nothing reads it
# --------------------------------------------------------------------------

def test_it_is_marked_an_additional_view_that_changes_no_verdict(view):
    assert view["view"] == "additional"
    assert view["changes_no_verdict"] is True


def test_it_sits_beside_per_year_as_registered():
    if not ART.exists():
        pytest.skip("artifact not built")
    a = json.loads(ART.read_text(encoding="utf-8"))["accuracy"]
    assert "per_year" in a and "per_year_scale_view" in a


def test_no_served_surface_reads_the_scale_view():
    """The block rho is a narrower statistic than the pooled one and would be
    read as a head-to-head if it ever reached a page. Nothing may render it."""
    # The key, not the statistic name. `efv_model.block_rho_eval` is a different
    # and older lane (consensus against the blend, within base year) that has
    # every right to the phrase, and grepping for `block_rho` would flag it and
    # teach the next reader to ignore this test.
    hits = []
    allowed = {"source_backtest.py"}
    for f in list(ROOT.glob("assets/*.js")) + list(ROOT.glob("*.py")):
        if f.name in allowed or f.name.startswith("test_"):
            continue
        try:
            if "per_year_scale_view" in f.read_text(encoding="utf-8", errors="ignore"):
                hits.append(f.name)
        except OSError:
            pass
    assert not hits, f"the scale view is being read outside the backtest: {hits}"


# --------------------------------------------------------------------------
# The two legs sit on the same rows
# --------------------------------------------------------------------------

def test_the_pooled_leg_is_on_the_rows_the_block_leg_kept(view):
    """If a block fell under the minimum its rows leave BOTH legs. A pooled leg
    computed on all rows would mix the normalization with the population."""
    for r in RATERS:
        c = view["per_rater"][r]
        assert c["pooled_rho_same_rows"] is not None
        assert c["pooled_rho_all_rows"] is not None
    if not view["blocks_dropped_below_min"]:
        for r in RATERS:
            c = view["per_rater"][r]
            assert c["pooled_rho_same_rows"] == c["pooled_rho_all_rows"], (
                "no block was dropped, so the two pooled values must agree; "
                "they do not, which means the legs are not on the same rows")


def test_every_rater_carries_a_floor_and_a_call(view):
    for r in RATERS:
        c = view["per_rater"][r]
        assert (c["floor_E_cond_in_run"] or {}).get("mde95") is not None
        assert c["call_E_cond_in_run"]


def test_the_delta_is_block_minus_pooled_and_the_arithmetic_holds(view):
    for r in RATERS:
        c = view["per_rater"][r]
        want = round(c["block_rho"] - c["pooled_rho_same_rows"], 5)
        assert abs(c["delta_block_minus_pooled"] - want) <= 2e-4, (
            f"{r}: the published delta does not equal block minus pooled")


# --------------------------------------------------------------------------
# The gaps the view displays are floored
# --------------------------------------------------------------------------

def test_every_gap_the_view_displays_carries_a_floor(view):
    gaps = view["gaps_on_this_view"]
    for r in RATERS:
        if r == "xfv":
            continue
        g = gaps[f"xfv_vs_{r}"]
        assert (g["floor_E_cond_in_run"] or {}).get("mde95") is not None
        assert g["call_E_cond_in_run"]


def test_the_efv_versus_consensus_gap_does_not_resolve_on_this_view(view):
    """The registered expectation's surviving half. If this ever clears it is a
    real change to what the platform may say and must be confirmed first, not
    absorbed by editing this test."""
    f = view["gaps_on_this_view"]["xfv_vs_prospx_consensus"]["floor_E_cond_in_run"]
    assert abs(f["point_delta"]) <= f["mde95"], (
        f"eFV vs the consensus now CLEARS on the block view ({f['point_delta']} "
        f"against {f['mde95']}). That contradicts the registration and it would "
        "change a published claim from a description into a direction.")


def test_the_sign_flip_between_the_two_instruments_is_still_there(view):
    """The most useful thing this lane found on 2026-09-06: the eFV-vs-consensus
    gap changed SIGN depending on whether block scale is removed, and neither
    reading resolved. On the fWAR label (2026-10-03) the two instruments agree
    in sign (-0.0062 pooled, -0.00002 block); the doc records that as a dated
    section. The served state must equal that section's STATE line, and the
    step A state (the flip held: +0.005 and -0.00163) stays pinned."""
    served = _scale_state(json.loads(ART.read_text(encoding="utf-8")))
    want = _doc_state()["sign_agree"]
    assert served["sign_agree"] is want, (
        f"the pooled cell ({served['_pooled']}) and the block view "
        f"({served['_block']}) give sign_agree={served['sign_agree']}, but the "
        f"doc's latest dated section says sign_agree={want}. That is a change in "
        "the evidence: re-read the accuracy copy and record a new dated section "
        "before this test is updated.")
    step_a = _step_a_state()
    if step_a is None:
        pytest.skip(NO_SNAPSHOT)
    assert _doc_state(step_a=True)["sign_agree"] is STEP_A_STATE["sign_agree"]
    assert step_a["sign_agree"] is STEP_A_STATE["sign_agree"], (
        f"step A: pooled {step_a['_pooled']} and block {step_a['_block']} no "
        "longer show the sign flip the record says they showed")


# --------------------------------------------------------------------------
# The placebo
# --------------------------------------------------------------------------

def test_the_placebo_is_a_distribution_not_a_single_draw(view):
    """THE MISTAKE THIS CATCHES was made. One permutation said the transform
    accounted for all of eFV's loss and none of the raters'; 200 say it costs
    every column about the same."""
    pl = view["placebo_permuted_blocks"]
    assert pl["B"] >= 100, "a placebo below 100 draws cannot separate a mean from noise"
    for r in RATERS:
        c = pl["per_rater"][r]
        assert c["B_used"] >= 100
        assert c["sd"] > 0
        assert len(c["ci95"]) == 2


def test_the_placebo_preserves_the_block_sizes(view):
    assert view["placebo_permuted_blocks"]["block_sizes_preserved"] is True


def test_every_rater_is_reported_net_of_its_own_placebo(view):
    """A single pooled placebo constant would subtract the wrong amount from at
    least one column, because a coarse 20-to-80 grade and a continuous model
    number are not tied to the same degree."""
    for r in RATERS:
        c = view["per_rater"][r]
        assert c["placebo_mean_delta"] is not None
        want = round(c["delta_block_minus_pooled"] - c["placebo_mean_delta"], 5)
        assert abs(c["delta_net_of_placebo"] - want) <= 2e-4


def test_the_three_raters_clear_the_placebo_and_efv_does_not(view):
    """The 2026-09-06 finding: the three raters sat OUTSIDE their permutation
    bands. On the fWAR label (2026-10-03) all three sit inside; the doc records
    that as a dated section. Each rater's served state must equal that section's
    STATE line, and the step A state (all three outside) stays pinned per rater."""
    served = _scale_state(json.loads(ART.read_text(encoding="utf-8")))
    doc = _doc_state()
    for r in PUBLISHED:
        assert served[r]["inside_band"] is doc[r]["inside_band"], (
            f"{r}: inside its permutation band = {served[r]['inside_band']}, but "
            f"the doc's latest dated section says {doc[r]['inside_band']}. Re-read "
            "the accuracy copy and record a new dated section before this test "
            "is updated.")
    step_a = _step_a_state()
    if step_a is not None:
        doc_a = _doc_state(step_a=True)
        for r in PUBLISHED:
            assert doc_a[r]["inside_band"] is STEP_A_STATE[r]["inside_band"]
            assert step_a[r]["inside_band"] is STEP_A_STATE[r]["inside_band"], (
                f"step A: {r} inside its band = {step_a[r]['inside_band']}, "
                f"against the recorded {STEP_A_STATE[r]['inside_band']}")
    # DS-02 (2026-09-25): the served eFV V2 grade is the consensus value at the order
    # rank inside (side, year), so it carries the block scale by construction (bug B5's
    # repair). The registration below was made on eFV v1.
    import efv_v2_serve
    if (efv_v2_serve.enabled()
            and view["per_rater"]["xfv"]["observed_inside_placebo_band"] is False):
        pytest.xfail("eFV V2 sits outside its placebo band: its grade is drawn from the "
                     "consensus values of each (side, year) group, so it carries block "
                     "scale by construction; the registration was made on eFV v1")
    assert view["per_rater"]["xfv"]["observed_inside_placebo_band"] is True, (
        "eFV now sits OUTSIDE its permutation band, which would mean eFV carries "
        "block scale too. Confirm before anything is said about the difference.")
    if step_a is None:
        pytest.skip(NO_SNAPSHOT)


# --------------------------------------------------------------------------
# The attribution
# --------------------------------------------------------------------------

def test_both_attribution_passes_ran(view):
    for tag in ("side_only", "year_only"):
        blk = view["attribution"][tag]
        assert not blk.get("status"), f"{tag}: {blk.get('status')}"
        assert set(blk["per_rater"]) == set(RATERS)


def test_the_effect_is_the_base_year_and_not_the_side(view):
    """The half of this lane anybody would have guessed was doing the work is the
    side scale, and it buys nothing measurable. Recorded as a test so a future
    frame that reverses it has to be noticed.

    The base-year half is read per rater against the doc's latest dated section.
    On 2026-09-06 every rater's year-only delta cleared its floor. At step A it
    cleared for mlb_pipeline and prospx_consensus only (fangraphs -0.01808
    against 0.0182), and on the fWAR label (2026-10-03) it clears for none."""
    side = view["attribution"]["side_only"]["per_rater"]
    year = view["attribution"]["year_only"]["per_rater"]
    for r in RATERS:
        f = (side[r]["floor_E_cond_in_run"] or {})
        assert abs(side[r]["delta_block_minus_pooled"]) <= f["mde95"], (
            f"{r}: the SIDE scale now resolves on its own "
            f"({side[r]['delta_block_minus_pooled']} against {f['mde95']}). That "
            "is a new finding and the doc says the opposite; confirm it before "
            "the copy is changed.")
    assert set(year) == set(RATERS)
    served = _scale_state(json.loads(ART.read_text(encoding="utf-8")))
    doc = _doc_state()
    for r in PUBLISHED:
        got = served[r]["year_effect_resolves"]
        want = doc[r]["year_effect_resolves"]
        assert got is want, (
            f"{r}: the base-year scale resolves = {got} "
            f"({served[r]['_year_delta']} against {served[r]['_year_floor']}), but "
            f"the doc's latest dated section says {want}. This is the lane's "
            "central measurement: re-read the accuracy copy and record a new "
            "dated section before this test is updated.")
    step_a = _step_a_state()
    if step_a is None:
        pytest.skip(NO_SNAPSHOT)
    doc_a = _doc_state(step_a=True)
    for r in PUBLISHED:
        want = STEP_A_STATE[r]["year_effect_resolves"]
        assert doc_a[r]["year_effect_resolves"] is want
        assert step_a[r]["year_effect_resolves"] is want, (
            f"step A: {r} base-year resolves = {step_a[r]['year_effect_resolves']} "
            f"({step_a[r]['_year_delta']} against {step_a[r]['_year_floor']}), "
            f"against the recorded {want}")


def test_the_side_only_pass_has_exactly_two_blocks(view):
    assert view["attribution"]["side_only"]["blocks_kept"] == 2


# --------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------

def test_the_gate_document_records_the_refuted_prediction():
    assert DOC.exists(), f"{DOC} is missing"
    txt = DOC.read_text(encoding="utf-8")
    assert "REFUTED" in txt, (
        "the registration predicted -0.0113 at 0.93x floor and the measurement "
        "is about three times that and resolves; a refuted prediction is written "
        "down, not edited")
    assert "receipt, not a claim" in txt, (
        "the eFV vs FanGraphs cell clears its floor on this view and the doc must "
        "say it is descriptive under the alpha-spending clause")


def test_the_gate_document_records_the_one_draw_placebo_mistake():
    txt = DOC.read_text(encoding="utf-8").lower()
    assert "single-draw placebo is not a placebo" in txt


def test_the_mechanism_was_marked_untested_and_then_corrected():
    """It was written down as a hypothesis, which is why A-CLAIM-3 could go and
    kill it. The doc has to carry BOTH halves: a reader who finds only the
    hypothesis would take it for a live explanation."""
    txt = DOC.read_text(encoding="utf-8")
    assert "hypothesis and has not been tested" in txt, (
        "the exposure explanation is a story about the numbers, not a "
        "measurement, and must be labelled as one")
    assert "falsified the same day" in txt, (
        "A-CLAIM-3 tested the exposure explanation and it lost; the correction "
        "belongs in this doc, not only in the one that ran the test")
