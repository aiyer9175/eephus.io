# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The xHEM+ P/PA walk-shrink registration pins (task XHEM_PPA_SHRINK_TEST, owner
decision EW3-32 item 2, "Run it (owner override)").

docs/ewar/XHEM_PPA_SHRINK_GATE.md is committed ALONE, with this file, before any
number of its estimands exists. Every clause is pinned by the sentence that makes it
bind. Prose assertions run on a whitespace-flattened copy so that re-wrapping a
paragraph is not a failure. Results go in part 9 of the document, never above it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar" / "XHEM_PPA_SHRINK_GATE.md"
ARTIFACT = ROOT / "data" / "_labs" / "xhem_ppa_shrink_eval.json"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_registered_before_any_number():
    flat = _flat(_doc())
    assert flat.startswith("# xHEM+ with a P/PA walk-shrink target: the forward test (xhem_ppa_shrink_v1)")
    assert "STATUS: REGISTERED, RESULTS EMPTY." in flat
    assert "`test_xhem_ppa_shrink_registration.py`" in flat


def test_override_is_disclosed():
    flat = _flat(_doc())
    assert "\"Run it (owner override)\"" in flat
    assert "+0.0563 with interval -0.0002 to +0.1161: a miss by 0.0002" in flat
    assert "The override waives the trigger only. Every rule below binds as written." in flat
    assert "Scope: item (a) of the ewar-map plan's T6 only." in flat


def test_pair_set_and_data():
    flat = _flat(_doc())
    assert "(Y, Y+1) for Y in 2016, 2017, 2018, 2021, 2022, 2023, 2024 (2020 out on both sides; no 2025 to 2026 pair)" in flat
    assert "Savant `pa` 200 or more in both seasons" in flat
    assert "**2026 never enters.**" in flat
    assert "no season-complete override is set" in flat


def test_construction_constants_are_frozen():
    flat = _flat(_doc())
    assert "sPPA = (pitches + K_PPA * L_Y) / (PA + K_PPA), K_PPA = 100" in flat
    assert "T = lgBB_Y + b * (sPPA - L_Y), floored at 0" in flat
    assert "r_shr = (uBB + K_UBB * T) / (D + K_UBB), K_UBB = 120" in flat
    assert "xw' = est_woba + w_ubb,Y * (r_shr - r_raw)" in flat
    assert "on the 2013, 2014 and 2015 StatsAPI seasons only" in flat
    assert "the run refuses if b is not finite or n is under 300" in flat


def test_arms_statistics_and_pass_rule():
    flat = _flat(_doc())
    assert "**N, the NULL comparator: the unmodified xHEM+.**" in flat
    assert "**P, the permuted-P/PA twin:**" in flat
    assert "`random.Random(20261018)`" in flat
    assert "B = 2,000, seed 20261015" in flat
    assert "1.645 times the bootstrap sd of the gap" in flat
    assert "(k = 1), so Holm leaves the 95 percent interval as it is" in flat
    assert ("(1) V minus N has lo95 above 0 under v1; (2) V minus N has lo95 above 0 under v2; "
            "(3) the twin fails: P minus N has lo95 at or below 0 under v1 and under v2.") in flat
    assert "a permuted P/PA passing means the gain is not P/PA's" in flat
    assert "P/PA stays a context column, nothing is built" in flat


def test_never_list():
    flat = _flat(_doc())
    assert "(`docs/PROSPECT_ANCHOR_GATE.md`)" in flat
    assert "no betting artifact, dark column, price, market capture or game result, and no 2026 row" in flat
    assert "It runs once." in flat


RESULT_PATTERNS = (
    r"\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]",
    r"\bp\s*=\s*-?0?\.\d",
    r"\brho(_[A-Z])?\s*=\s*-?\d",
    r"\bgap\s*=\s*[-+]?\d",
    r"\bverdict\s*:\s*\w",
    r"\bb\s*=\s*-?\d*\.\d",
)


def test_no_result_above_part_9():
    text = _doc()
    head, results = text.split("## 9. Results", 1)
    for pattern in RESULT_PATTERNS:
        m = re.search(pattern, head, re.I)
        assert m is None, f"a result above part 9: {m.group(0) if m else ''!r}"
    if not ARTIFACT.exists():
        assert _flat(results).strip() == "EMPTY AT REGISTRATION."
