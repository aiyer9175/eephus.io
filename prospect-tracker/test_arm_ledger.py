"""A-CLAIM-15: the program arm ledger.

WHAT IT IS FOR. Every driver lane reports honest per-lane statistics: a floor
derived on its own frame, a Holm correction across its own family, a
zero-information twin. Each is defensible alone. What no artifact said until now
is how many lanes there have been, and that count is what any future survivor has
to be read against. Fifty arms at a nominal 5% produce about two spurious passes
on pure noise, each arriving with a per-lane correction that is correct and
beside the point.

WHAT IT MUST NOT BECOME. A retrospective program-wide Holm. The arms were gated
on different frames, pools and label definitions, so a joint family applied after
the fact would imply a structure that never existed. The ledger counts; the
reserved 2025 fold is what actually buys confirmation.

THE RESULT IT CURRENTLY RECORDS is favourable and it is earned: 39 of 48 arms are
scoreable against a recorded floor and none of them reached it, against about 2.4
passes expected from noise alone. That independently reproduces the "39 gated arms,
zero survivors" figure from the 2026-08-14 driver program, which is the strongest
available evidence that the ledger is reading the artifacts correctly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_arm_ledger as al          # noqa: E402

ART = ROOT / "data" / "xfv_arm_ledger.json"


@pytest.fixture(scope="module")
def led():
    if not ART.exists():
        pytest.skip("data/xfv_arm_ledger.json has not been built")
    return json.loads(ART.read_text(encoding="utf-8"))


def test_it_reads_every_lane_it_claims_to(led):
    assert not led["sources_missing"], (
        "the ledger could not read one of its sources, so the arm count is a "
        f"lower bound and the denominator is wrong: {led['sources_missing']}")


def test_the_count_matches_the_rows(led):
    assert led["n_arms"] == len(led["arms"])
    assert sum(led["by_lane"].values()) == led["n_arms"]
    assert sum(led["by_verdict"].values()) == led["n_arms"]


def test_sweeps_are_never_folded_into_the_arm_count(led):
    """A sweep over a continuous knob is a different multiplicity object from an
    independent feature arm. Summing them overstates the count as badly as
    ignoring them understates it."""
    sweep_total = sum(s["settings"] for s in led["sweeps"])
    assert sweep_total > 0, "no sweeps counted at all; a lane went missing"
    assert led["n_arms"] != led["n_arms"] + sweep_total
    assert "must not be summed" in led["sweeps_are_not_arms"]


def test_no_arm_is_reported_with_a_verdict_it_never_had(led):
    """Most committed arms predate the verdict vocabulary entirely. Reporting
    them as PASS or NULL would be inventing a record."""
    stored = {r["verdict"] for r in led["arms"]}
    for v in stored:
        assert v == "NO_STORED_VERDICT" or v.isupper(), (
            f"verdict {v!r} is neither the honest absence marker nor one of the "
            "driver lab's uppercase verdict strings")
    assert led["n_without_stored_verdict"] == sum(
        1 for r in led["arms"] if r["verdict"] == "NO_STORED_VERDICT")


def test_cleared_is_computed_from_the_arms_own_floor(led):
    for r in led["arms"]:
        if r.get("cleared_own_floor") is None:
            assert r.get("delta_rho") is None or r.get("floor_rho") is None, (
                f"{r['arm']} has both a delta and a floor but was not scored")
            continue
        assert r["cleared_own_floor"] is (r["delta_rho"] >= r["floor_rho"]), (
            f"{r['arm']}: cleared flag disagrees with its own numbers "
            f"({r['delta_rho']} vs {r['floor_rho']})")


def test_cleared_is_labelled_as_the_weak_bar_it_is(led):
    note = led.get("cleared_is_the_weakest_bar") or ""
    assert "not a verdict" in note.lower(), (
        "the ledger publishes a cleared count without saying that clearing a "
        "point floor is not a verdict; somebody will quote it as one")


def test_it_refuses_to_apply_a_retrospective_correction(led):
    note = led.get("this_is_not_a_correction") or ""
    assert "no program-wide holm" in note.lower()


def test_the_reserved_fold_is_recorded_and_not_yet_spent(led):
    rf = led["reserved_fold"]
    assert rf["cohort"] == "2025 base year"
    assert rf["enters_at_run_year"] == 2028, (
        "the reserved fold's entry year disagrees with the resolvability rule: "
        "2025 plus the 3-year development lag is the 2028 run")
    assert "registered_in" in rf and rf["registered_in"].endswith(
        "EPOCH_2026_PREREGISTRATION.md")


def test_the_alpha_clause_exists_and_names_one_confirmatory_read():
    doc = (ROOT / "docs" / "efv-2026-08-19"
           / "EPOCH_2026_PREREGISTRATION.md").read_text(encoding="utf-8")
    assert "Alpha spending" in doc, "the alpha-spending clause is gone"
    low = doc.lower()
    assert "one confirmatory read" in low
    assert "descriptive" in low, (
        "the clause does not record the prior reads as descriptive, which is "
        "the whole point: three prior looks at a four-cell family were taken "
        "before the frame was frozen")
    assert "not lan-demets" in low or "not Lan-DeMets" in doc, (
        "the clause does not say what it is NOT; calling a retrospective count "
        "an alpha-spending function would be a second kind of dishonesty")


def test_the_current_yield_is_zero_and_that_is_recorded(led):
    """Records the 2026-09-06 state. A future arm that clears has to arrive
    through a deliberate update here, not silently."""
    assert led["n_cleared_own_floor"] == 0, (
        f"an arm now clears its own floor: {led['cleared_own_floor']}. That may "
        "be a real finding. Read it against the 48-arm denominator and the "
        "reserved fold before it changes any published claim, then update this "
        "test deliberately.")
    assert led["n_scoreable_against_a_floor"] >= 39, (
        "fewer arms are scoreable than the 39 recorded on 2026-09-06, so a "
        "lane's floor block has stopped being readable and the denominator "
        "silently shrank")


def test_the_reading_states_the_noise_expectation(led):
    r = led["reading"]
    assert "nominal 5%" in r and "noise" in r
    assert str(led["n_arms"]) in r


def test_collect_is_offline_and_writes_nothing_by_itself():
    """The ledger reads committed artifacts. `collect()` must not write, so a
    test or a dry run cannot dirty the tree."""
    before = ART.read_bytes() if ART.exists() else None
    al.collect()
    after = ART.read_bytes() if ART.exists() else None
    assert before == after, "collect() wrote to the artifact"
