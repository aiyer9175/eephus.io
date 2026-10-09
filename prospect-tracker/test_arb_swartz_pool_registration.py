# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Registration pins for the A6 / C3' amendment
(docs/ARBITRATION_GATE.md section 16, registered 2026-10-08).

Committed alone, before the repaired MLBTR loader was scored. These pins hold
the two pools, the headline choice, the C3' bound and the collision rule in
place, so none can be edited after a result is visible.
"""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent / "docs" / "ARBITRATION_GATE.md"
HEAD = ("## 16. A6 / C3' amendment (registered 2026-10-08, before any re-score): "
        "the repaired MLBTR pool")


def _sec14() -> str:
    doc = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert HEAD in doc, "section 16 is missing"
    return doc.split(HEAD, 1)[1].split("\n## ", 1)[0]


def test_the_amendment_names_both_pools_and_the_headline():
    s = _sec14()
    assert "`arb_dataset.load_swartz_projections()`" in s
    assert "`load_ledger` is NOT\n  changed" in s
    assert "**The frozen pool**" in s and "**The repaired pool**" in s
    assert "**The repaired pool is the headline from this date.**" in s
    assert "`a6_swartz_frozen_pool`" in s


def test_c3_keeps_its_bound_and_collisions_are_published():
    s = _sec14()
    assert "its registered bound (0.216) unchanged" in s.replace("\n  ", " ")
    assert "COLLISION" in s
    assert "at least\n  0.95" in s
