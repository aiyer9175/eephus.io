# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX farm headers name both pools and say which one the total FV sums.

WHY THIS EXISTS (census M02-12, 2026-09-25). The farm-detail hero printed the length of
the one-row farm pool (graded rows plus provisional rows) as "N prospects tracked" right
beside org.total_fv, which sums the GRADED rows only (org.count of them): LAD read "273
prospects tracked · 4809 total FV" where the 4809 is built on 156 players. The farm GFX
card printed org.count (156) under the same words, so one farm carried two different
"prospects tracked" numbers.

Contract pinned here:
  * the two hero lines and the GFX card all print through farmPoolCountsText;
  * no header prints a bare pool length as "prospects tracked" beside the total;
  * the text names the graded count and, when the pool is larger, the tracked and
    provisional counts, and those add up.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def test_no_header_prints_the_pool_length_as_prospects_tracked():
    src = _src()
    assert "rosterPlayersAll.length} prospects tracked" not in src
    assert "} prospects tracked</div>" not in src  # the GFX card's old org.count line
    assert src.count("farmPoolCountsText(org, rosterPlayersAll.length)") == 2
    assert "farmPoolCountsText(org.count != null ? org" in src  # GFX card
    assert "total FV (graded)" in src and "Total FV of graded" in src


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval(_function_source(_src(), "farmPoolCountsText"))
    return ctx


def _txt(js, org, n):
    return js.eval("farmPoolCountsText(%s, %s)" % (json.dumps(org), json.dumps(n)))


def test_counts_text_names_both_pools(js):
    assert _txt(js, {"count": 156}, 273) == "156 graded · 273 tracked (117 provisional)"
    assert _txt(js, {"count": 156}, 156) == "156 graded prospects"
    assert _txt(js, {"count": 156}, None) == "156 graded prospects"
    assert _txt(js, {}, 40) == "40 prospects tracked"


def test_counts_add_up_for_every_served_org(js):
    from conftest import load_data_doc
    doc = load_data_doc("timeseries.json")
    orgs = (doc or {}).get("org_summary") or []
    if not orgs:
        pytest.skip("data/timeseries.json org_summary not built")
    for o in orgs:
        t = _txt(js, {"count": o["count"]}, o["count"] + 7)
        m = re.fullmatch(r"(\d+) graded · (\d+) tracked \((\d+) provisional\)", t)
        assert m, (o["org"], t)
        g, n, p = map(int, m.groups())
        assert g == o["count"] and g + p == n, (o["org"], t)
