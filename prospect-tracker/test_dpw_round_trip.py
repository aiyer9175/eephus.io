# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""I4, the round-trip level (OD-1 round_trip), on SYNTHETIC winters.

fa_market.pricing_dpw_by_winter(signings, R, r_net) is sum PV_R(cash) / sum WAR
discounted at r_net: the winter's own deals, priced by the served formula at
that level with within-contract growth g_ref, return their PV cost at R.
Worked example A2 (DESIGN_v2 appendix): a 5-year $30M AAV deal for a flat
2-WAR player prices at $17.095M sticker and $13.942M round-trip at the default
R. At g = 0 and R = 0 the level is X02-06's AAV / WAR. Scheduled deals pay their
scheduled cash at R.
"""

from __future__ import annotations

import pytest

import dpw_path as dp
import fa_market as fm

R = 0.113763
G = 0.0409
R_NET = (1.0 + R) / (1.0 + G) - 1.0


def _deal(i, years=5, aav=30e6, war=2.0, winter=2026):
    return {"player_key": f"rt-{winter}-{i}", "class_year": winter, "years": years,
            "guarantee_usd": aav * years, "_war_path": {"war_by_year": [war] * 15}}


def _winter(n=25, **kw):
    return [_deal(i, **kw) for i in range(n)]


@pytest.fixture(autouse=True)
def _no_deferrals(monkeypatch):
    monkeypatch.setattr(fm, "_deferral_ledger", lambda: {})


def test_worked_example_a2():
    rt = fm.pricing_dpw_by_winter(_winter(), R, R_NET)[2026]
    assert rt == pytest.approx(13.942e6, rel=2e-4)
    sticker = fm.dollars_per_war_by_winter(_winter())[2026]
    assert sticker == pytest.approx(17.095e6, rel=2e-4)


def test_the_round_trip_returns_the_pv_cost_at_r():
    deals = _winter(10, years=3, aav=12e6, war=1.5) + _winter(10, years=1, aav=8e6, war=1.0) \
        + _winter(10, years=6, aav=25e6, war=3.0)
    for i, d in enumerate(deals):
        d["player_key"] = f"mix-{i}"
        d["_war_path"] = {"war_by_year": [max(0.0, d["_war_path"]["war_by_year"][0] - 0.2 * t)
                                          for t in range(15)]}
    a = fm.pricing_dpw_by_winter(deals, R, R_NET)[2026]
    cost = sum(sum((d["guarantee_usd"] / d["years"]) / (1 + R) ** t for t in range(d["years"]))
               for d in deals)
    value = sum(a * sum(w * (1 + G) ** t / (1 + R) ** t
                        for t, w in enumerate(d["_war_path"]["war_by_year"][:d["years"]]))
                for d in deals)
    assert value == pytest.approx(cost, rel=1e-12)


def test_at_zero_growth_and_zero_rate_the_level_is_aav_over_war():
    a = fm.pricing_dpw_by_winter(_winter(years=4, aav=20e6, war=2.5), 0.0, 0.0)[2026]
    assert a == pytest.approx(20e6 / 2.5, rel=1e-12)


def test_the_denominator_discounts_at_r_net():
    a1 = fm.pricing_dpw_by_winter(_winter(), R, 0.07)[2026]
    a2 = fm.pricing_dpw_by_winter(_winter(), R, 0.03)[2026]
    den1 = sum(2.0 / 1.07 ** t for t in range(5))
    den2 = sum(2.0 / 1.03 ** t for t in range(5))
    assert a1 / a2 == pytest.approx(den2 / den1, rel=1e-12)


def test_a_scheduled_deal_pays_its_scheduled_cash_at_r(monkeypatch):
    deals = _winter()
    s = deals[0]
    sched = [{"year_offset": t, "amount_usd": 15e6} for t in range(5)] + \
        [{"year_offset": 10 + t, "amount_usd": 15e6} for t in range(5)]
    monkeypatch.setattr(fm, "_deferral_ledger",
                        lambda: {f"{s['player_key']}:{s['class_year']}": {"schedule": sched}})
    a = fm.pricing_dpw_by_winter(deals, R, R_NET)[2026]
    level_cash = sum(30e6 / (1 + R) ** t for t in range(5))
    sched_cash = dp.pv([(x["year_offset"], x["amount_usd"]) for x in sched], R)
    den = sum(2.0 / (1 + R_NET) ** t for t in range(5))
    assert a == pytest.approx((24 * level_cash + sched_cash) / (25 * den), rel=1e-12)
    assert sched_cash < level_cash


def test_every_deferred_entry_carries_flows_and_the_doc_names_the_rate():
    """Row 29: all deferred entries carry their flows (so the round-trip level
    has no re-base branch), and the ledger's _doc names the rate
    deferral_npv_usd actually discounts at, not the old 9 percent."""
    import json
    from pathlib import Path
    d = json.loads((Path(fm.__file__).parent / "data" / "deferrals.json").read_text(encoding="utf-8"))
    deferred = {k: e for k, e in d["players"].items() if e.get("deferred")}
    assert deferred and all(e.get("flows") for e in deferred.values()), sorted(deferred)
    doc = " ".join(d["_doc"])
    assert "(9%)" not in doc
    assert "deferral_npv_usd" in doc and "_discount_rate()" in doc
