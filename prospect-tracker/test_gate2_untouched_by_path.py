# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Gate 2 is untouched by the projected $/WAR path (VAL_5, DESIGN_v2 sections
4.2, 5 row 32 and the "Not touched" list; docs/dpw-2026-09-25/DPW_PATH_GATE.md
0a and 16).

Pinned on a SYNTHETIC enrichment, the unified path forced on in-process over a
tmp copy of a synthetic series file (never the live file, never the
environment):

  * every Gate 2 and MarketModel input (winter_dpw, _destale_rate, disc_war,
    dollars_per_war_by_winter, _discount_rate, _dpw_inflation, the deferral NPV
    at its default rate) is byte-identical ON and OFF;
  * the readers of dollars_per_war_inflation and _destale_rate are a closed list;
  * no Gate 2 or MarketModel input reads the series file's pricing block;
  * with fa_market.WRITE_DPW_PATH_BLOCK off (the committed value) no caller of
    the one writer writes a dpw_path key: a hand call, the rebuild step and the
    Gate 2 persist route, whose default is now persist_dpw=False;
  * no Trade Machine pricing literal sits inside a unified branch.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from pathlib import Path

import pytest

import dpw_testkit as kit
import fa_market as fm

ROOT = Path(__file__).resolve().parent


def _synthetic_enriched(first: int = 2015, last: int = 2026, per_winter: int = 30) -> list[dict]:
    """Deterministic enriched signings shaped like fa_market.enriched_signings
    rows: every winter clears the thin-winter filter (n >= 25, discounted WAR
    > 20). Prices grow about 4 percent a winter with a fixed wiggle; no
    randomness and no real data."""
    rows = []
    for w in range(first, last + 1):
        lvl = 9.0e6 * 1.04 ** (w - first) * (1.0 + 0.03 * ((-1) ** w))
        for i in range(per_winter):
            years = (1, 1, 1, 2, 3, 4, 5, 7)[i % 8]
            war0 = 0.6 + 0.15 * (i % 11)
            path = [max(0.0, war0 - 0.25 * t) for t in range(15)]
            disc = sum(x / 1.07 ** t for t, x in enumerate(path[:years]))
            guar = int(round(lvl * disc * (1.0 + 0.02 * ((i % 5) - 2))))
            rows.append({"player_key": f"syn-{w}-{i:02d}", "player_name": f"Synthetic {w} {i}",
                         "class_year": w, "years": years, "guarantee_usd": guar,
                         "position": ("SP", "RP", "C", "SS", "OF", "1B")[i % 6],
                         "age": 27 + (i % 9), "qo": False,
                         "_war_path": {"war_by_year": path}})
    return rows


@pytest.fixture
def gate2_inputs():
    enriched = _synthetic_enriched()

    def snap():
        series = fm.dollars_per_war_by_winter(enriched)
        prior = {y: v for y, v in series.items() if y < 2027}
        sched = [{"year_offset": t, "amount_usd": 10_000_000} for t in (0, 1, 2, 12, 13)]
        return json.dumps({
            "series": {str(k): v for k, v in series.items()},
            "winter_dpw": fm.winter_dpw(prior, 2027),
            "destale": fm._destale_rate(prior, 2027),
            "disc_war": [fm.disc_war(r["_war_path"], r["years"]) for r in enriched[:40]],
            "discount_rate": fm._discount_rate(),
            "dpw_inflation": fm._dpw_inflation(),
            "deferral_npv": fm.deferral_npv_usd(sched, 50_000_000),
            "breakdowns": fm.dpw_breakdowns(enriched),
        }, sort_keys=True)
    return snap


def test_gate2_inputs_are_byte_identical_on_and_off(gate2_inputs, tmp_path):
    off = gate2_inputs()
    with kit.unified(tmp_path):
        import value_framework as vf
        assert vf.dpw_path_active()
        on = gate2_inputs()
    for stage in ("U1a", "U1b", "U1c", "U2"):
        with kit.unified(tmp_path, stages=(stage,)):
            assert gate2_inputs() == off, stage
    assert on == off


# The modules that may read dollars_per_war_inflation or call _destale_rate.
# A unified branch that started reading either would move Gate 2 with no model
# change (registration section 16); this list fails first.
# fa_backtest.py joined on 2026-10-08 (owner answer M14-2): its verdict edge
# recipe prices the corpus Deal+ numerator with the same ex-ante destale rate
# fa_export prices the served Deal+ with; it moves the derived edges, never a
# Gate 2 table number.
ALLOWED_READERS = {
    # xm_export.py joined at the XM-FLIP (2026-10-22): xM$ prices the FA rows
    # with the same ex-ante destale rate fa_export uses, a served column, never
    # a Gate 2 table number.
    "_destale_rate(": {"fa_market.py", "fa_export.py", "fa_backtest.py", "xm_export.py"},
    "dollars_per_war_inflation": {"backtest.py", "fa_class.py", "fa_export.py", "fa_market.py",
                                  "proj_export.py", "valuation_sets.py", "value_framework.py"},
}


@pytest.mark.parametrize("needle", sorted(ALLOWED_READERS))
def test_the_readers_of_the_legacy_escalator_are_a_closed_list(needle):
    found = set()
    for p in ROOT.glob("*.py"):
        if p.name.startswith("test_") or p.name in ("conftest.py",):
            continue
        if needle in p.read_text(encoding="utf-8", errors="replace"):
            found.add(p.name)
    assert found == ALLOWED_READERS[needle], sorted(found)


def test_no_gate2_or_market_model_input_reads_the_pricing_block():
    import fa_backtest
    src = inspect.getsource(fa_backtest)
    for banned in ("written_pricing_level_usd", "_written_doc", "level_usd", "dpw_path",
                   "price_level", "season_value_usd"):
        assert banned not in src, banned
    mm = inspect.getsource(fm.MarketModel)
    for banned in ("written_pricing_level_usd", "_written_doc", "level_usd", "dpw_path_active",
                   "price_level", "season_value_usd", "fa_dpw_series"):
        assert banned not in mm, banned
    for fn in (fm.winter_dpw, fm._destale_rate, fm.disc_war, fm.dollars_per_war_by_winter,
               fm._dpw_inflation, fm._discount_rate):
        body = inspect.getsource(fn)
        assert "price_level" not in body and "season_value_usd" not in body and "pricing" not in body


def test_the_block_switch_is_off_and_has_no_environment_override():
    assert fm.WRITE_DPW_PATH_BLOCK is False
    src = (ROOT / "fa_market.py").read_text(encoding="utf-8")
    assert len(re.findall(r"^WRITE_DPW_PATH_BLOCK = ", src, flags=re.M)) == 1
    assert "EEPHUS_WRITE_DPW_PATH" not in src
    import fa_backtest
    assert inspect.signature(fa_backtest.run_market_gate).parameters["persist_dpw"].default is False


@pytest.fixture
def writer_tmp(monkeypatch, tmp_path):
    enriched = _synthetic_enriched()
    monkeypatch.setattr(fm, "enriched_signings", lambda *a, **k: enriched)
    out = tmp_path / "fa_dpw_series.json"
    monkeypatch.setattr(fm, "DPW_SERIES_PATH", out)

    def boom(*a, **k):
        raise AssertionError("the dpw_path block builder ran with the block switch off")
    monkeypatch.setattr(fm, "build_dpw_path_block", boom)
    return out


def test_a_hand_call_writes_val1_keys_only(writer_tmp):
    fm.write_dpw_series(2027)
    doc = json.loads(writer_tmp.read_text(encoding="utf-8"))
    assert set(doc) == {"method", "model_version", "usd_per_war_by_winter", "breakdown", "pricing"}
    assert "dpw_path" not in json.dumps(doc)
    fm.write_dpw_series(2027, force=True)                    # force does nothing while off
    assert "dpw_path" not in json.loads(writer_tmp.read_text(encoding="utf-8"))


def test_the_rebuild_step_writes_val1_keys_only(writer_tmp):
    import run_monthly
    run_monthly._write_dpw_series_step(logging.getLogger("test"))
    doc = json.loads(writer_tmp.read_text(encoding="utf-8"))
    assert "dpw_path" not in doc and "pricing" in doc


def test_the_gate2_persist_route_is_the_one_writer_and_off_by_default():
    import fa_backtest
    body = inspect.getsource(fa_backtest.run_market_gate)
    assert body.count("fm.write_dpw_series(") == 1
    assert "fm.write_dpw_series(_CLASS_YEAR)" in body            # no force, no block of its own
    assert "if persist and persist_dpw:" in body
    assert "DPW_SERIES_PATH" not in body and ".write_text" not in body.split("if persist and persist_dpw:")[1]


def test_val1_still_finds_one_writer():
    import test_one_dpw_level
    test_one_dpw_level.test_the_series_has_one_writer()


def test_no_trade_machine_pricing_literal_inside_a_unified_branch():
    import bayes_trade_value as bt
    for fn in (bt._gross_war_pv, bt._contract_surplus_mm, bt.defensive_floor_mm):
        src = inspect.getsource(fn)
        i = src.find("if vf.dpw_path_active()")
        if i < 0:
            i = src.find("_dpw_align")
        assert i >= 0, fn.__name__
        if fn is bt._gross_war_pv or fn is bt.defensive_floor_mm:
            branch = src[i:].split("return round(pv, 2)" if fn is bt.defensive_floor_mm
                                   else "return round(tot, 1)", 1)[0]
            assert "0.09" not in branch and "0.05" not in branch, fn.__name__
