# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX Farm Finances tiles subtract the acquisition bonus once.

WHY THIS EXISTS (census M02-02, 2026-09-24, four verifiers CONFIRMED). storage.py adds
(eFV expected surplus - bonus paid) per active prospect into fin_active_surplus, so the
leaf's surplus_total_mm is already NET of the bonus and cost_basis_mm is the bonus. The
Finances tab read surplus_total_mm as gross and printed Net = surplus_total_mm -
cost_basis_mm, subtracting the bonus a second time on all 30 orgs: STL printed Net
$395.6M "+532% over cost" where the net is $470.0M (+632%), and the Club Ledger serves
that same $470.0M as STL's net farm surplus.

Contract pinned here:
  * the Net Surplus tile prints surplus_total_mm as served, Gross prints it plus the cost
    basis, and "% over cost" is net / cost, for every org in the served artifact;
  * no expression in the page subtracts cost_basis_mm from surplus_total_mm again;
  * the leaf key keeps its name and net meaning (the Ledger and its tests read it).
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest
from conftest import load_data_doc

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def _orgs():
    doc = load_data_doc("timeseries.json")
    orgs = [o for o in ((doc or {}).get("org_summary") or [])
            if ((o.get("tree") or {}).get("fin_active_surplus") or {}).get("surplus_total_mm") is not None]
    if not orgs:
        pytest.skip("data/timeseries.json org_summary not built")
    return orgs


def test_no_second_subtraction_of_the_cost_basis():
    src = _src()
    fn = _function_source(src, "makeFarmFinancialComposite")
    assert "const netActive    = activeSurplus.surplus_total_mm;" in fn
    assert not re.search(r"(totalSurplus|surplus_total_mm)\s*-\s*(costBasis|[\w.]*cost_basis_mm)", src), (
        "surplus_total_mm is already net of the bonus; subtracting the cost basis again double-counts it")


def test_leaf_total_is_the_net_accumulator():
    for o in _orgs():
        leaf = o["tree"]["fin_active_surplus"]
        assert leaf["surplus_total_mm"] == pytest.approx(o["_active_surplus_net_mm"], abs=0.051), o["org"]
        assert leaf["cost_basis_mm"] == pytest.approx(o["_active_surplus_cost_mm"], abs=0.051), o["org"]


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval("function escapeHtml(s) { return String(s); }"
             " function gradeColor(l) { return '#000'; }"
             " function formatMetric(v, t) { return '$' + Number(v).toFixed(2) + 'M'; }")
    ctx.eval(_function_source(_src(), "makeFarmFinancialComposite"))
    return ctx


def _tiles(html: str) -> dict:
    out = {}
    for label, value, sub in re.findall(
            r"text-transform:uppercase;color:var\(--text-tertiary\);font-weight:600;margin-bottom:3px;\">([^<]+)</div>\s*"
            r"<div[^>]*>([^<]*)</div>\s*(?:<div[^>]*>(.*?)</div>)?", html, re.S):
        out[label.strip()] = (value.strip(), sub or "")
    return out


def test_tiles_read_gross_cost_net_for_every_org(js):
    import json
    orgs = _orgs()
    assert len(orgs) >= 30
    for o in orgs:
        leaf = o["tree"]["fin_active_surplus"]
        net, cost = leaf["surplus_total_mm"], leaf["cost_basis_mm"]
        html = js.eval("makeFarmFinancialComposite(%s)" % json.dumps(
            {"tree": o["tree"], "grades": o.get("grades") or {}, "component_ranks": {}}))
        t = _tiles(html)
        assert t["Net Surplus"][0] == f"${net:.1f}M", (o["org"], t["Net Surplus"])
        assert t["Cost Basis"][0] == f"${cost:.1f}M", o["org"]
        assert t["Gross Surplus"][0] == f"${net + cost:.1f}M", o["org"]
        pct = f"{'+' if net >= 0 else ''}{100 * net / cost:.0f}% over cost"
        assert t["Net Surplus"][1].startswith(pct), (o["org"], t["Net Surplus"][1], pct)
