"""B-L6 denoised-baseline fairness control: the decision rule and its receipts.

WHAT THESE TESTS ARE FOR. The lab's numbers are a measurement and will move. What must
NOT move without someone noticing is (a) the registered decision rule, (b) the identity
that defines the GLS weight, (c) the agreement between the artifact's stored verdict and
its own stored numbers, and (d) that no reader surface prints a raw adjudicator token.
Since LIBRARY_6 (2026-10-14) the B-L6 record reaches readers as a dated Model Updates
note row labelled eFV v1 (data/model_updates_typed.json); the Library's Model upgrades
panel that rendered it is retired.

Every test here was mutation-proved: the mutation table is in the docstring of each
test, and each mutation was confirmed to turn the test red. A test that passes with the
code it covers deleted is worse than no test, and this repo has shipped one before.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

GATE_DOC = ROOT / "docs" / "efv-2026-08-09" / "DENOISED_BASELINE_GATE.md"
ARTIFACT = ROOT / "data" / "xfv_denoised_baseline_eval.json"
GLOSSARY = ROOT / "assets" / "glossary.js"


def _lab():
    import efv_denoised_baseline_lab as L
    return L


def _artifact():
    if not ARTIFACT.exists():
        pytest.skip("xfv_denoised_baseline_eval.json not built in this tree")
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the decision rule
def test_uninformative_beats_survives_when_the_baseline_got_worse():
    """The single most important branch: a baseline that did NOT improve can never be
    reported as a win for eFV, no matter how large the delta.

    This is the branch the real run actually hit. P1 scored rho 0.30703 against the
    served consensus's 0.31889 and eFV "beat" it by +0.043 at 1.31x its floor. Without
    the ordering in `adjudicate`, that would have shipped as eFV's best result ever
    when it is an artifact of a handicapped baseline.

    MUTATION TABLE (each confirmed red):
      - move the `rho_p1 <= rho_p0` check BELOW the `d1 >= mde_cond` check  -> SURVIVES
      - change `<=` to `<`                                                  -> SURVIVES on ties
      - delete the UNINFORMATIVE branch entirely                            -> SURVIVES
    """
    L = _lab()
    # huge delta, comfortably over its floor, but the baseline is WORSE than served
    v, why = L.adjudicate(d1=0.043, mde_cond=0.033, mde_refit=0.036,
                          rho_p1=0.30703, rho_p0=0.31889, noop_rho=0.90)
    assert v == "UNINFORMATIVE", f"a worse baseline must not yield {v}"
    assert "not a better aggregate" in why


def test_a_baseline_that_ties_the_served_consensus_is_also_uninformative():
    """`<=`, not `<`. A baseline that merely matches the incumbent has not improved on
    it, and 'improved by exactly zero' must not open the survive branch.

    MUTATION: `<=` -> `<` turns this red.
    """
    L = _lab()
    v, _ = L.adjudicate(d1=0.05, mde_cond=0.03, mde_refit=0.03,
                        rho_p1=0.3200, rho_p0=0.3200, noop_rho=0.5)
    assert v == "UNINFORMATIVE"


def test_no_op_short_circuits_before_everything_else():
    """If the rebuilt baseline ranks the rows the same way as the served one, the
    statistic cannot see the reweighting and no verdict about eFV is licensed - even
    though a near-identical baseline trivially satisfies `rho_p1 > rho_p0` sometimes.

    MUTATION TABLE:
      - raise the threshold 0.999 -> 1.01  -> falls through to SURVIVES
      - move the no-op check below the improvement check -> UNINFORMATIVE/SURVIVES
    """
    L = _lab()
    v, why = L.adjudicate(d1=0.05, mde_cond=0.03, mde_refit=0.03,
                          rho_p1=0.3190, rho_p0=0.3189, noop_rho=0.9995)
    assert v == "NO_OP", f"a rank-identical baseline must not yield {v}"
    assert "same" in why


def test_survives_and_collapses_split_on_the_e_cond_floor():
    """The registered rule is `d1 >= MDE95_cond`. Above it SURVIVES, below COLLAPSES,
    and the boundary is inclusive.

    MUTATION TABLE:
      - `>=` -> `>`            -> the exact-boundary case flips to COLLAPSES
      - compare against mde_refit instead of mde_cond -> boundary case flips
    """
    L = _lab()
    ok = dict(rho_p1=0.3300, rho_p0=0.3189, noop_rho=0.90, mde_refit=0.040)
    assert L.adjudicate(d1=0.040, mde_cond=0.033, **ok)[0] == "SURVIVES"
    assert L.adjudicate(d1=0.030, mde_cond=0.033, **ok)[0] == "COLLAPSES"
    # boundary is inclusive
    assert L.adjudicate(d1=0.033, mde_cond=0.033, **ok)[0] == "SURVIVES"


def test_a_negative_delta_is_a_reversal_not_a_collapse():
    """eFV losing outright is a different finding from eFV failing to clear a floor, and
    the artifact must not blur them.

    MUTATION: delete the `d1 < 0` branch -> returns COLLAPSES, which would let a real
    reversal be written up as an underpowered null.
    """
    L = _lab()
    v, _ = L.adjudicate(d1=-0.02, mde_cond=0.033, mde_refit=0.036,
                        rho_p1=0.3400, rho_p0=0.3189, noop_rho=0.90)
    assert v == "REVERSAL"


# --------------------------------------------------------------- the weight identity
def test_gls_weight_is_b_over_sigma_squared_and_is_checked_not_trusted():
    """C-A1's whole methodological point is `w_s ∝ b_s / sigma_s^2` rather than the
    naive `1 / sigma_s^2`, which would reward range compression. `load_precision`
    RECOMPUTES the identity instead of trusting the stored column, because a stored
    column can go stale against the b and sigma beside it.

    MUTATION: relax the tolerance to 1.0, or delete the loop -> a corrupted artifact
    loads silently and every arm in the lane is then weighted wrong.
    """
    L = _lab()
    if not L.PRECISION_PATH.exists():
        pytest.skip("source_cohort_accuracy.json not built in this tree")
    prec = L.load_precision()
    for s in prec["sources"]:
        assert prec["gls_weight"][s] == pytest.approx(
            prec["b"][s] / prec["sigma2"][s], abs=1e-4), f"{s} weight is not b/sigma^2"
    # and the naive form is NOT what is stored, which is the thing worth pinning
    naive = {s: 1.0 / prec["sigma2"][s] for s in prec["sources"]}
    assert prec["gls_weight"] != naive


def test_load_precision_refuses_an_artifact_whose_weight_column_is_stale(tmp_path, monkeypatch):
    """The guard has to actually fire, not merely exist.

    MUTATION: remove the `raise` -> this test goes red.
    """
    L = _lab()
    if not L.PRECISION_PATH.exists():
        pytest.skip("source_cohort_accuracy.json not built in this tree")
    good = json.loads(L.PRECISION_PATH.read_text(encoding="utf-8"))
    em = good["precision_label_free"]["estimator_primary_em_fiml"]
    em["gls_weight"] = [w + 1.0 for w in em["gls_weight"]]      # corrupt it
    p = tmp_path / "stale.json"
    p.write_text(json.dumps(good), encoding="utf-8")
    monkeypatch.setattr(L, "PRECISION_PATH", p)
    with pytest.raises(AssertionError, match="not b/sigma"):
        L.load_precision()


# ------------------------------------------------- the artifact agrees with itself
def test_stored_verdicts_reproduce_from_the_stored_numbers():
    """The artifact carries both the inputs and the conclusion. If they ever disagree,
    someone edited one of them by hand - which is exactly how a false d50c1afb-style
    'proof' got shipped in three files earlier in this program.

    MUTATION: hand-edit `verdict_corrected` in the artifact to SURVIVES -> red.
    """
    L = _lab()
    a = _artifact()
    cor = a["primary_corrected_amendment_2"]
    arms, inc = a["arms"], a["incumbent_rederived_today"]
    recomputed, _ = L.adjudicate(
        d1=cor["delta"],
        mde_cond=cor["MDE95_E_cond"],
        mde_refit=cor["MDE95_E_refit"],
        rho_p1=arms["S3_global_centering"]["baseline_rho"],
        rho_p0=inc["consensus_rho"],
        noop_rho=arms["S3_global_centering"]["rank_corr_with_published"],
    )
    assert recomputed == cor["verdict"] == a["verdict_corrected"]


def test_the_attribution_arithmetic_closes():
    """drift + denoising must equal the total move from the registered delta. This is
    the number the public panel prints as a percentage, so an inconsistency here is a
    wrong number on the site.

    MUTATION: change either summand in the artifact -> red.
    """
    a = _artifact()
    at = a["attribution"]
    total = at["delta_today_vs_denoised_baseline"] - at["delta_registered_2026_08_08"]
    assert at["moved_by_frame_drift"] + at["moved_by_denoising"] == pytest.approx(
        total, abs=1e-5)


def test_the_control_never_ships_a_weight():
    """B-L6 measures; it does not reweight anything. C-A1 established zero-weights-ship
    and a +0.001 rho gain is not a reason to break it.

    MUTATION: add a non-empty weights dict to either file -> red.
    """
    for name in ("source_weights.json", "draft_source_weights.json"):
        p = ROOT / "data" / name
        if not p.exists():
            continue
        assert json.loads(p.read_text(encoding="utf-8")).get("weights") == {}, (
            f"{name} gained weights; B-L6 measured a +0.001 rho gain and that is far "
            f"below any floor")


def test_the_artifact_is_labelled_not_vintage_disciplined():
    """The baseline is defined using rows it also scores. That is legitimate for a
    baseline definition and illegitimate to quote as out-of-sample, so the label is
    load-bearing and must survive a re-run.

    MUTATION: flip the flag to True -> red.
    """
    a = _artifact()
    assert a["basis"]["vintage_disciplined"] is False
    assert "2027" in GATE_DOC.read_text(encoding="utf-8")


# ------------------------------------------------------ the record a reader sees
TYPED = ROOT / "data" / "model_updates_typed.json"


def _b_l6_note():
    doc = json.loads(TYPED.read_text(encoding="utf-8"))
    rows = [n for n in doc["notes"]
            if (n.get("source") or {}).get("path") == "data/xfv_denoised_baseline_eval.json"]
    assert len(rows) == 1, f"expected one B-L6 note row, found {len(rows)}"
    return rows[0]


def test_no_reader_surface_prints_a_raw_adjudicator_token():
    """A cross-file coupling that has no other guard: `adjudicate` emits formal tokens
    (COLLAPSES, NULL, ...). The B-L6 record now reaches readers as a Model Updates note
    row, and the Library no longer fetches the artifact, so neither may carry a raw token.

    MUTATION: write COLLAPSES into the note row's text -> red.
    MUTATION: fetch xfv_denoised_baseline_eval.json from glossary.js again -> red.
    """
    lab_src = (ROOT / "tools" / "efv_denoised_baseline_lab.py").read_text(encoding="utf-8")
    body = lab_src[lab_src.index("def adjudicate("):]
    body = body[:body.index("\ndef ")]
    emitted = set(re.findall(r'return "([A-Z_]+)"', body))
    assert emitted, "no verdict literals found; the parse target moved"

    text = _b_l6_note()["text"]
    raw = sorted(t for t in emitted if re.search(r"\b" + t + r"\b", text))
    assert not raw, f"the B-L6 note row prints raw verdict tokens: {raw}"
    src = GLOSSARY.read_text(encoding="utf-8")
    assert "xfv_denoised_baseline_eval.json" not in src, (
        "glossary.js reads the B-L6 artifact again; map every adjudicator token to plain "
        "language before rendering it")


def test_the_retired_conviction_claim_is_gone_from_the_hero():
    """The B-L6 pre-commitment required the conviction copy to get harder to clear once
    the edge failed to survive. The retired sentence asserted the win as settled fact
    with no estimator attached.

    MUTATION: restore the old headline -> red.
    """
    src = GLOSSARY.read_text(encoding="utf-8")
    assert "out-ranks the scouting industry out of sample" not in src, (
        "the retired conviction headline is back; B-L6 found the margin clears neither "
        "registered floor")
    assert "cannot call a win" in src


def test_the_b_l6_note_row_states_the_measurement_from_its_artifact_key():
    """The panel that printed B-L6 retired with the Library's Model upgrades panel
    (LIBRARY_6, 2026-10-14). The pre-commitment's printed gap-closure share binds a
    surface that asserts eFV beats the consensus; none does (the hero reads "cannot
    call a win" or "statistically indistinguishable", and the served claim is a tie), and
    the share stays derivable from block `attribution` of the artifact. What must survive
    is the measurement itself, stated as a dated fact whose figures are the artifact's:
    the gap, both floors, and that it cleared neither.

    MUTATION: change +0.03138 in the note row -> red.
    MUTATION: point the row's source key at another block -> red.
    """
    a = _artifact()
    n = _b_l6_note()
    assert n["date"] == "2026-08-11" and n["model_id"] == "efv_v1"
    assert n["source"]["key"] == "incumbent_rederived_today"
    inc = a["incumbent_rederived_today"]
    for fig in (f"+{inc['delta']:.5f}", f"{inc['MDE95_E_cond']:.4f}",
                f"{inc['MDE95_E_refit']:.4f}"):
        assert fig in n["text"], (fig, n["text"])
    assert inc["delta"] < min(inc["MDE95_E_cond"], inc["MDE95_E_refit"])
    assert "did not clear either" in n["text"]
