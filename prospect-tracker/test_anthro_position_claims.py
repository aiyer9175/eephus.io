# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Lane E4: the anthro claims harness must stay honest.

The deliverable here is a MEASUREMENT of three stated beliefs, so what needs
protecting is not an output number but the conditions under which a number is
allowed to be called SUPPORTED.

THE ERROR THESE TESTS EXIST FOR. The first run reported H1 CONTRADICTED at
p = 0.0005, a real-looking effect in the direction opposite the claim. Pitchers
were still in the sample: 55.4% of the height rows, 2.0 inches taller on average,
with no first-base innings. Removing them flipped the sign and H1 became the
strongest of the three.

The zero-information control PASSED on that run. It always would have. A noise
exposure tests the estimator, not the population, and only the population was
wrong. So the pitcher filter gets a test of its own rather than living as a line
of code someone could tidy away.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
lab = pytest.importorskip("anthro_position_lab")

ARTIFACT = ROOT / "data" / "anthro_position_eval.json"


# --- the estimator ---------------------------------------------------------

def test_spearman_is_right_on_known_cases():
    assert lab.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert lab.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert lab.spearman([1, 1, 1], [1, 2, 3]) is None, "no spread means no estimate"


def test_spearman_is_rank_based_not_value_based():
    """A monotone transform of the exposure must not move rho. That is the
    reason for choosing it over Pearson on a bounded share."""
    xs = [1, 2, 3, 4, 5]
    ys = [2, 1, 4, 3, 5]
    a = lab.spearman(xs, ys)
    b = lab.spearman([x ** 3 for x in xs], ys)
    assert a == pytest.approx(b)


def test_height_parsing_rejects_what_it_cannot_read():
    assert lab.height_inches("6' 2") == 74.0
    assert lab.height_inches("5' 11") == 71.0
    assert lab.height_inches(None) is None
    assert lab.height_inches("tall") is None, "a mis-parsed height is a fake exposure"
    assert lab.height_inches("2' 0") is None, "out of range is a parse artifact"
    assert lab.height_inches("9' 0") is None


# --- the verdict rule ------------------------------------------------------

def test_supported_needs_all_three_conditions():
    good = {"rho": 0.2, "ci95": [0.1, 0.3], "perm_p": 0.001}
    assert lab.verdict(good, "+")[0] == "SUPPORTED"


def test_two_of_three_is_not_a_pass():
    """Significance plus an interval clear of zero, but the WRONG sign, is not a
    confirmation of the claim. It is a contradiction of it."""
    wrong_sign = {"rho": -0.2, "ci95": [-0.3, -0.1], "perm_p": 0.001}
    assert lab.verdict(wrong_sign, "+")[0] == "CONTRADICTED"

    spans_zero = {"rho": 0.2, "ci95": [-0.01, 0.4], "perm_p": 0.001}
    assert lab.verdict(spans_zero, "+")[0] == "NOT SUPPORTED"

    not_sig = {"rho": 0.2, "ci95": [0.01, 0.4], "perm_p": 0.20}
    assert lab.verdict(not_sig, "+")[0] == "NOT SUPPORTED"


def test_a_negative_claim_is_judged_on_its_own_sign():
    """H3 predicts a NEGATIVE rho. Judging it against a positive expectation
    would report a confirmed claim as contradicted."""
    res = {"rho": -0.11, "ci95": [-0.18, -0.04], "perm_p": 0.003}
    assert lab.verdict(res, "-")[0] == "SUPPORTED"
    assert lab.verdict(res, "+")[0] == "CONTRADICTED"


def test_an_absent_estimate_is_inconclusive_not_a_refutation():
    assert lab.verdict({"rho": None, "reason": "x"}, "+")[0] == "INCONCLUSIVE"


# --- the population --------------------------------------------------------

def test_the_pitcher_filter_exists_and_is_applied():
    """THE REGRESSION. Without it 55.4% of the height sample were pitchers and
    H1 came back significant in the wrong direction."""
    src = (ROOT / "tools" / "anthro_position_lab.py").read_text(encoding="utf-8")
    assert "def position_players(" in src
    assert "pk in hitters" in src, (
        "the filter must actually be applied to the sample, not merely defined")


def test_a_synthetic_pitcher_confound_is_detectable_by_the_estimator():
    """Prove the mechanism rather than asserting it: tall bodies with a zero
    outcome, mixed into a real positive relationship, drag rho negative."""
    rng = random.Random(11)
    xs, ys = [], []
    for _ in range(300):                     # hitters: taller -> more 1B
        h = rng.uniform(68, 78)
        xs.append(h)
        ys.append(max(0.0, min(1.0, (h - 68) / 10 + rng.gauss(0, 0.1))))
    clean = lab.spearman(xs, ys)
    for _ in range(300):                     # pitchers: tall, zero 1B
        xs.append(rng.uniform(73, 79))
        ys.append(0.0)
    polluted = lab.spearman(xs, ys)
    assert clean > 0.5, "the synthetic hitter relationship must be strong"
    assert polluted < clean, (
        "adding tall zero-outcome rows must drag the estimate down; this is the "
        "exact shape of the first-run error")


# --- the artifact ----------------------------------------------------------

@pytest.mark.skipif(not ARTIFACT.exists(), reason="lab has not been run")
def test_the_artifact_records_the_control_and_it_is_clean():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert d["control_ok"] is True, (
        "a zero-information exposure came back SUPPORTED; every verdict in this "
        "artifact is untrustworthy until that is explained")
    assert d["zero_information_control"]["verdict"] != "SUPPORTED"


@pytest.mark.skipif(not ARTIFACT.exists(), reason="lab has not been run")
def test_the_artifact_states_what_it_does_not_license():
    """The causal caveat is the most important sentence in the deliverable and
    must travel with the numbers."""
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    blob = " ".join(d.get("caveats") or []).lower()
    assert "outcome of club decisions" in blob or "clubs behave" in blob, (
        "career innings share measures club behaviour, not player ability, and "
        "the artifact must say so")
    assert d.get("population") == "position players only; pitchers are excluded"


@pytest.mark.skipif(not ARTIFACT.exists(), reason="lab has not been run")
def test_every_claim_carries_a_verdict_and_an_interval():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert len(d["claims"]) == 3
    for c in d["claims"]:
        assert c["verdict"] in ("SUPPORTED", "NOT SUPPORTED", "CONTRADICTED",
                                "INCONCLUSIVE")
        assert "ci95" in c and "perm_p" in c and c["n"] > 0
