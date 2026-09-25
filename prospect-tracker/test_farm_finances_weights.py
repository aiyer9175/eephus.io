# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Farm Finances leaf bars print the weights storage computes with.

WHY THIS EXISTS (census M02-09, 2026-09-25). The Finances tab hardcoded the v38 leaf
weights 42/18/18/7/8/7 while storage.FARM_LEAF_WEIGHTS["financial"] computes the v40
0.68/0.10/0.10/0.04/0.04/0.04; the copy said "the 5 leaves below" over six bars; and
the farm masthead and report card said v31.

Contract pinned here:
  * LEAF_WEIGHTS_FIN equals storage's financial weights in percent and sums to 100;
  * the leaf count in the copy is derived, not typed;
  * no farm masthead or report card prints a v31 version.
"""
from __future__ import annotations

import re
from pathlib import Path

import storage

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def test_leaf_weights_match_storage():
    src = PROSPX.read_text(encoding="utf-8")
    m = re.search(r"const LEAF_WEIGHTS_FIN = \{(.*?)\};", src, re.S)
    assert m
    page = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}
    served = {k: round(100 * w) for k, w in storage.FARM_LEAF_WEIGHTS["financial"].items()}
    assert page == served
    assert sum(page.values()) == 100


def test_no_stale_version_or_leaf_count():
    src = PROSPX.read_text(encoding="utf-8")
    assert "weighted blend of the 5 leaves" not in src
    assert "Object.keys(LEAF_WEIGHTS_FIN).length} leaves below" in src
    assert "v31 composite grade" not in src and "v31 weighting" not in src
