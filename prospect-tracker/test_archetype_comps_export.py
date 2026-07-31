# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Guards on the archetype comps sidecar.

These lock the two honesty constraints the surface ships under: the source
artifact's false health_warning must never be propagated, and the per-stratum
reliability flag must track the real t-statistic. If someone later relaxes
either one, these fail.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import archetype_comps_export as A

ROOT = Path(__file__).parent


@pytest.fixture(scope="module")
def built():
    src = json.loads(A.SRC_PATH.read_text(encoding="utf-8"))
    prereg = json.loads(A.PREREG_PATH.read_text(encoding="utf-8"))
    return A.build(src, prereg)


def test_source_health_warning_is_false_and_not_propagated(built):
    """The source claims every stratum's residual is statistically zero. It is
    not. Recompute it here rather than trusting either file."""
    src = json.loads(A.SRC_PATH.read_text(encoding="utf-8"))
    ts = [abs(float(r["oof_resid_t"])) for r in src["archetypes"]]
    n_ge2 = sum(1 for t in ts if t >= 2.0)
    assert n_ge2 == 477 and len(ts) == 3957
    assert round(100.0 * n_ge2 / len(ts), 2) == 12.05
    assert max(ts) == 4.91
    # and the excess survives multiplicity control, so it is not chance
    assert built["audit"]["bh_rejected"] == 77

    # The false claim must not be carried forward. It may only appear inside
    # the audit verdict that rebuts it, so compare against the exact source
    # string rather than a phrase. Reduce to a bool before asserting: pytest's
    # explanation for a failed `in` over a 300 KB blob is pathologically slow.
    blob = json.dumps(built)
    propagated = src["health_warning"] in blob
    assert not propagated
    assert "health_warning" not in built
    quoted_only_in_rebuttal = (
        "statistically zero" not in json.dumps(
            {k: v for k, v in built.items() if k != "audit"}))
    assert quoted_only_in_rebuttal
    assert built["audit"]["health_warning_verdict"].startswith("FALSE")


def test_reliability_flag_tracks_the_real_t(built):
    """Every row's tier must be derivable from its own published t. No row may
    be marked reliable while carrying a large residual."""
    rel_i = built["cols"].index("rel")
    t_i = built["cols"].index("resid_t")
    for row in built["rows"]:
        t, rel = abs(row[t_i]), row[rel_i]
        if rel == 0:
            assert t < A.T_NOMINAL
        else:
            assert t >= A.T_NOMINAL
    counts = built["reliability"]["counts"]
    assert counts["off_model"] == 77
    assert sum(counts.values()) == len(built["rows"]) == 3957
    # the tier the UI must mark is the one the source called "already priced"
    assert built["audit"]["already_priced_false"] == 474


def test_no_predictive_or_model_claim(built):
    assert "DISPLAY ONLY" in built["contract"].upper()
    assert "NO SHIP" in built["source"]["model_verdict"]
    assert built["source"]["producer_script"] == "tools/_comb_sweep_desc.py"
    assert not (ROOT / "tools" / "_comb_sweep_desc.py").exists(), \
        "the producer reappeared: re-derive the descriptive table and drop " \
        "the unreproducible-statistics language"
    assert "ABSENT" in built["source"]["producer_status"]


def test_membership_matches_the_preregistration(built):
    """The one property of this artifact that IS auditable."""
    assert built["audit"]["prereg_ids_unknown"] == 0
    assert built["audit"]["prereg_n_mismatch"] == 0
    assert built["audit"]["prereg_sha256_16"] == "fa70f4244573730b"


def test_payload_shape_is_frontend_ready(built):
    tokens, facets = built["tokens"], built["facets"]
    assert len(built["cols"]) == len(built["rows"][0])
    for tok in tokens:
        axis, _, level = tok.partition("=")
        assert axis in facets, axis
        assert level in facets[axis]["levels"], tok
    for row in built["rows"]:
        assert 1 <= len(row[0]) <= 3
        assert all(0 <= i < len(tokens) for i in row[0])
        assert all(v is not None for v in row[1:])
    # degenerate intervals must be flagged, never rendered as tight bands
    lo, hi = built["cols"].index("war_lo95"), built["cols"].index("war_hi95")
    zv = built["cols"].index("zero_var")
    for row in built["rows"]:
        assert row[zv] == (1 if row[lo] == row[hi] else 0)
    assert built["reliability"]["zero_var_rows"] == 130


def test_written_artifact_is_small_and_matches_build(built):
    out = json.loads(A.OUT_PATH.read_text(encoding="utf-8"))
    # bool first: a failed 3,957-row list comparison would spend minutes in
    # pytest's diff renderer
    same = out["rows"] == built["rows"] and out["tokens"] == built["tokens"]
    assert same, "data/archetype_comps.json is stale; re-run the export"
    assert A.OUT_PATH.stat().st_size < 400_000, "payload is lazy-loaded"
