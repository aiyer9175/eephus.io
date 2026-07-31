# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Offline tests for the Tommy John surgery ingest (tj_surgery.py).

No network. Parse assertions run against the saved verification sample
(data/sources/samples/tj_list_verify.csv); feature assertions run against
the landed store (data/tj_surgery.json). Both are skipped if the artifact
is absent so a fresh checkout does not hard-fail the suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tj_surgery as tj

REPO = Path(__file__).parent
SAMPLE = REPO / "data" / "sources" / "samples" / "tj_list_verify.csv"
LANDED = REPO / "data" / "tj_surgery.json"


def _sample_records():
    if not SAMPLE.exists():
        pytest.skip("verification sample not present (run tj_surgery.py first)")
    return tj.parse_records(SAMPLE.read_text(encoding="utf-8"))


def test_parse_skips_donations_banner():
    """Row 1 is the donations banner; row 2 is the real header. No parsed
    record may be the banner or the header itself."""
    recs = _sample_records()
    assert recs, "no records parsed"
    players = {r["player"] for r in recs}
    assert "Donations" not in players
    assert "Player" not in players          # the header row must not leak in
    # first real record should be an actual person with an id
    assert recs[0]["player"] and recs[0]["player"] != "Donations"


def test_mlbamid_fill_rate_above_95pct():
    recs = _sample_records()
    filled = sum(1 for r in recs if r["mlbamid"])
    rate = filled / len(recs)
    assert rate > 0.95, f"mlbamid fill rate {rate:.4f} <= 0.95"


def test_records_are_well_formed():
    """Every id-bearing record carries a 4-digit year and, when a date is
    present, an ISO YYYY-MM-DD string."""
    recs = _sample_records()
    for r in (x for x in recs if x["mlbamid"]):
        assert r["mlbamid"].isdigit()
        assert isinstance(r["year"], int) and 1900 < r["year"] < 2100
        if r["date"]:
            assert len(r["date"]) == 10 and r["date"][4] == "-"


def _landed_store():
    if not LANDED.exists():
        pytest.skip("landed json not present (run tj_surgery.py first)")
    doc = json.loads(LANDED.read_text(encoding="utf-8"))
    return doc.get("players", {})


def test_landed_json_keyed_by_numeric_mlbamid():
    store = _landed_store()
    assert store, "empty players map"
    # keys are all-digit mlbam ids; values are non-empty surgery lists
    for k, v in list(store.items())[:200]:
        assert k.isdigit(), f"non-numeric key {k!r}"
        assert isinstance(v, list) and v
        assert {"year", "date", "level", "recovery_months",
                "active", "post_tj_mlb_g"} <= set(v[0])


def _pick_multi_surgery(store: dict) -> str:
    """Prefer the hand-picked case (Bryce Montes de Oca, 656755: HS 2013,
    AAA 2023, AAA 2024 - three surgeries across three distinct years).
    Fall back to any player with >= 2 distinct surgery years."""
    prefer = "656755"
    if prefer in store and len({s["year"] for s in store[prefer]}) >= 2:
        return prefer
    for k, v in store.items():
        if len({s["year"] for s in v if s.get("year")}) >= 2:
            return k
    pytest.skip("no multi-surgery player in landed store")


def test_tj_features_asof_and_monotone():
    """as-of correctness + monotonicity on a hand-picked multi-surgery case.

    Counting only surgeries with Year STRICTLY BEFORE the cutoff year, the
    pre-cutoff count must be non-decreasing as the cutoff year advances, and
    months_since_last must RESET downward when a newer surgery crosses under
    the cutoff (proving it tracks the most-recent pre-cutoff event, not the
    first)."""
    store = _landed_store()
    mid = _pick_multi_surgery(store)
    years = sorted({s["year"] for s in store[mid] if s.get("year")})

    # counts across a sweep of cutoff years are monotone non-decreasing
    lo, hi = years[0], years[-1] + 2
    counts = [tj.tj_features(mid, f"{cy}-01-01", store=store)["tj_count_pre"]
              for cy in range(lo, hi + 1)]
    assert counts == sorted(counts), f"counts not monotone: {counts}"

    # strictly-before-year semantics: at cutoff == first surgery year, none
    # counted; one year later, exactly the first surgery counts
    assert tj.tj_features(mid, f"{years[0]}-06-01", store=store)["tj_pre"] == 0
    assert tj.tj_features(mid, f"{years[0]}-06-01",
                          store=store)["tj_count_pre"] == 0
    f_after_first = tj.tj_features(mid, f"{years[0] + 1}-01-01", store=store)
    assert f_after_first["tj_pre"] == 1
    assert f_after_first["tj_count_pre"] == 1

    # after the last surgery, all of them are counted
    f_all = tj.tj_features(mid, f"{years[-1] + 1}-01-01", store=store)
    assert f_all["tj_count_pre"] == len(years) if len(years) == len(store[mid]) \
        else f_all["tj_count_pre"] >= len(years)

    # months_since resets: measured just after the FIRST surgery it is large;
    # measured just after the LAST surgery it is smaller (a newer event took
    # over as the most-recent pre-cutoff surgery)
    if len(years) >= 2:
        m_early = tj.tj_features(mid, f"{years[1]}-01-01",
                                 store=store)["months_since_last_tj_pre"]
        m_late = tj.tj_features(mid, f"{years[-1] + 1}-01-01",
                                store=store)["months_since_last_tj_pre"]
        assert m_early is not None and m_late is not None
        assert m_late < m_early, f"months_since did not reset: {m_early} -> {m_late}"


def test_tj_features_unknown_player_is_empty():
    store = _landed_store()
    f = tj.tj_features("0", "2020-01-01", store=store)
    assert f == {"tj_pre": 0, "tj_count_pre": 0,
                 "months_since_last_tj_pre": None}


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
