# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Baseball America's stored FV means two different things in two eras, and the
normalizer is the only thing standing between that and the consensus.

WHAT WAS FOUND (2026-08-12). BA's own RAW grades are stable across every vintage
we hold: mean 48.09 / 48.00 / 48.21 / 49.23 for 2023, 2024, 2025, 2026. But the
fv we STORE drops from 48.09 to 36.48 in 2026, because the parser changed which
number it takes:

    2023-2025 vintages store the RAW grade      (recovered risk ordinal 0 on
                                                 every row, all five labels)
    2026+     vintages store the ADJUSTED grade (raw minus 5 x risk ordinal;
                                                 recovered exactly, Low 0 /
                                                 Mild 1 / Average 2 / High 3 /
                                                 Extreme 4)

BA also changed its risk VOCABULARY in the same cycle: 2023-2025 publish
Low / Medium / High / Very High / Extreme, 2026 publishes
Low / Mild / Average / High / Extreme. Two different five-rung ladders.

THIS EXPLAINS THE "BA SCALE BROKE ~11.5 FV IN THE 2026 CYCLE" FINDING. BA did
not re-grade anybody. We changed what we store, by 11.7 FV, and the break is an
artifact of our own ingestion.

WHY IT IS NOT A SERVED DEFECT. grade_normalization keys its cells by
(source, role, CYCLE), so the two eras land in different cells and each is
mapped onto the FanGraphs scale on its own terms: a nominal 45 maps to 37.67 in
2025 and 49.56 in 2026, an 11.89 FV difference that matches the storage shift
almost exactly. The consensus is protected.

WHAT THESE TESTS HOLD is the thing that would un-protect it: build_remapper
falls back to the RAW fv for a cell with no usable overlap, by design and
correctly, because dropping a source is worse. But a BA cell falling back would
serve a 2026 adjusted grade against 2023-2025 raw ones, a ~12 FV error inside a
single source, and nothing else in the tree would notice.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
DB = ROOT / "prospects.db"

#: Recovered from the data, not assumed. See the module docstring.
RISK_ORDINALS_2026 = {"Low": 0, "Mild": 1, "Average": 2, "High": 3, "Extreme": 4}


@pytest.fixture(scope="module")
def ba_rows():
    if not DB.exists():
        pytest.skip("prospects.db not present")
    con = sqlite3.connect(DB)
    try:
        rows = con.execute(
            "SELECT snapshot_date, fv, tools_json FROM snapshots "
            "WHERE source='baseballamerica' AND fv IS NOT NULL "
            "AND tools_json IS NOT NULL AND tools_json != ''").fetchall()
    finally:
        con.close()
    out = []
    for d, fv, tj in rows:
        try:
            ex = (json.loads(tj).get("_extras") or {})
        except ValueError:
            continue
        if ex.get("ba_raw_grade") is None or not ex.get("ba_risk"):
            continue
        out.append({"date": d, "fv": float(fv),
                    "raw": float(ex["ba_raw_grade"]), "risk": ex["ba_risk"]})
    if not out:
        pytest.skip("no Baseball America rows with grade and risk")
    return out


def test_the_two_eras_store_different_quantities_and_we_know_which(ba_rows):
    """If this ever changes, every number in the docstring above is stale."""
    old = [r for r in ba_rows if r["date"] < "2026"]
    new = [r for r in ba_rows if r["date"] >= "2026"]
    if not old or not new:
        pytest.skip("only one era present")
    assert all(abs(r["raw"] - r["fv"]) < 1e-9 for r in old), (
        "a pre-2026 Baseball America row no longer stores the RAW grade. The "
        "eras have converged or the parser changed again; re-derive the "
        "ordinals before trusting anything keyed on this split.")
    off = [r for r in new
           if abs((r["raw"] - 5.0 * RISK_ORDINALS_2026.get(r["risk"], -99)) - r["fv"]) > 1e-9]
    assert not off, (
        f"{len(off)} 2026+ row(s) break adjusted = raw - 5*ordinal, e.g. "
        f"{off[0]}. Either the ordinals moved or the vocabulary changed again.")


def test_the_risk_vocabulary_is_known_in_both_eras(ba_rows):
    """An unseen label silently maps to nothing downstream."""
    known = set(RISK_ORDINALS_2026) | {"Medium", "Very High"}
    seen = {r["risk"] for r in ba_rows}
    assert seen <= known, (
        f"unrecognised Baseball America risk label(s): {sorted(seen - known)}. "
        "BA has already changed this vocabulary once (Medium and Very High "
        "became Mild and Average in the 2026 cycle); a third ladder needs its "
        "ordinals recovered from the data before it is mapped.")


def test_no_baseball_america_cell_falls_back_to_the_raw_scale():
    """THE GUARD. A fallback cell serves an adjusted grade beside raw ones.

    build_remapper returns the RAW fv for a (source, role, year) cell with no
    usable overlap. That is right in general, because dropping a source is
    worse than serving it unnormalized. For Baseball America specifically it
    would put a 2026 adjusted grade on the same scale as 2023-2025 raw grades,
    an error of about 12 FV inside one source, and no other guard would see it.
    """
    gn = pytest.importorskip("grade_normalization")
    remap = gn.build_remapper()
    probe, fallback = 45.0, []
    for year in (2023, 2024, 2025, 2026):
        for pos in ("C", "SS", "2B", "3B", "1B", "LF", "CF", "RF", "RHP", "LHP"):
            if abs(remap(probe, "baseballamerica", pos, year) - probe) < 1e-9:
                fallback.append((year, pos))
    assert not fallback, (
        f"Baseball America cell(s) fall back to the raw scale: {fallback}. A "
        "2026 row there is served about 12 FV below its era-mates because the "
        "two eras store different quantities (see this module's docstring).")


def test_the_normalizer_actually_separates_the_two_eras():
    """The fallback guard above is only meaningful if the cells disagree.

    If both eras mapped to the same output the normalization would be doing
    nothing and the 11.7 FV storage difference would be reaching consensus
    whole.
    """
    gn = pytest.importorskip("grade_normalization")
    remap = gn.build_remapper()
    gaps = [remap(45.0, "baseballamerica", pos, 2026)
            - remap(45.0, "baseballamerica", pos, 2025)
            for pos in ("SS", "RHP", "CF")]
    assert all(g > 5.0 for g in gaps), (
        f"the normalizer maps the two Baseball America eras to nearly the same "
        f"place (gaps {[round(g, 2) for g in gaps]}). It is supposed to absorb "
        "an 11.7 FV difference in what the two eras store; if it no longer "
        "does, that difference is reaching the consensus.")
