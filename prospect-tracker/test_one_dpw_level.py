# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ONE $/WAR level for prospect and veteran surplus (VAL_1, owner decision
FP2-1, 2026-09-25).

Before this change three bases served at once. Prospect surplus priced a win at
the clemens_2026 FanGraphs flat $11.74M, /projections/ priced a veteran win at a
committed series carried to $17.97M, and /fa/ priced at a series it re-derived
every run and wrote nowhere ($17.14M). The Trade Machine and the Club Ledger
added prospect and veteran dollars into one total, so a prospect win cost less
than a veteran win inside the same number. Nothing asserted that the surfaces shared a
level, so nothing could see it.

These tests hold the invariant on the served artifacts and on the engine: one
written series, one writer, one level, read by every surface.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import value_framework as vf

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def _load(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def _pricing():
    doc = _load("fa_dpw_series.json")
    block = doc.get("pricing")
    assert block, "data/fa_dpw_series.json carries no pricing block; run fa_market.write_dpw_series"
    return doc, block


def test_the_written_series_carries_its_own_level():
    """pricing.level_usd is winter_dpw over the winters BEFORE the class, on the
    written series itself, so a reader can rebuild the level from the file."""
    import fa_market as fm

    doc, block = _pricing()
    series = {int(k): float(v) for k, v in doc["usd_per_war_by_winter"].items()}
    prior = {y: v for y, v in series.items() if y < int(block["class_year"])}
    assert int(block["anchor_winter"]) == max(prior)
    want = fm.winter_dpw(prior, int(block["class_year"]))
    assert abs(float(block["level_usd"]) - want) <= 1.0, (block["level_usd"], want)
    assert float(block["discount_rate"]) == pytest.approx(float(vf._config()["discount_rate"]))


def test_prospect_surplus_prices_at_the_written_level_with_the_clemens_shape():
    import valuation_sets as vs

    _doc, block = _pricing()
    cfg = vf._config()
    assert cfg["_valuation_set"] == "clemens_2026"
    dpw = cfg["dollars_per_war"]
    meta = dpw.get("_fa_reanchor") or {}
    assert meta.get("applied") is True and meta.get("method") == "fa_winter_level", meta
    assert float(dpw["flat"]) == pytest.approx(float(block["level_usd"]), abs=0.5)
    wc = vs.load("clemens_2026")["params"]["win_cost"]
    scale = float(dpw["flat"]) / (float(wc["flat_musd"]) * 1e6)
    for k, v in wc["rates_musd"].items():
        assert float(dpw["tiered"]["rates"][k]) == pytest.approx(float(v) * 1e6 * scale, rel=1e-9)
    # The FV 40 anchor is a FanGraphs-level dollar figure and moves with the level.
    import yaml
    base = yaml.safe_load((ROOT / "value_framework_config.yaml").read_text(encoding="utf-8"))
    assert float(cfg["lowtier_anchor"]["anchor_usd_40fv_position"]) == pytest.approx(
        float(base["lowtier_anchor"]["anchor_usd_40fv_position"]) * scale, rel=1e-9)


def test_every_surface_prices_the_class_at_one_level():
    """The cross-artifact invariant: /fa/, /projections/, prospect surplus and
    the stamp on every surplus artifact name the same $/WAR level."""
    _doc, block = _pricing()
    level = int(block["level_usd"])
    fa = _load("fa_class.json")
    if int(fa["class_year"]) == int(block["class_year"]):
        assert abs(int(fa["dpw_usd"]) - level) <= 1, (fa["dpw_usd"], level)
        assert fa.get("dpw_series_source") == "data/fa_dpw_series.json"
    proj = _load("mlb_projections.json")
    if int(proj["first_season"]) == int(block["class_year"]):
        assert abs(int(proj["dpw_usd"]) - level) <= 1, (proj["dpw_usd"], level)
    assert abs(round(float(vf._config()["dollars_per_war"]["flat"])) - level) <= 1
    stamps = {}
    for name, path in (("xfv.json", ("meta", "calibration")), ("trade_values.json", ("calibration",)),
                       ("mlb_projections.json", ("calibration",)), ("timeseries.json", ("calibration",)),
                       ("ledger_board.json", ("calibration",))):
        p = DATA / name
        if not p.exists():
            continue
        cur = json.loads(p.read_text(encoding="utf-8"))
        for k in path:
            cur = (cur or {}).get(k)
        stamps[name] = (cur or {}).get("dpw_level_usd")
    assert stamps and all(v is not None and abs(int(v) - level) <= 1 for v in stamps.values()), stamps


def test_the_fa_board_prices_on_the_written_series():
    doc, _block = _pricing()
    series = doc["usd_per_war_by_winter"]
    for name in ("fa_class.json", "fa_class_2028.json", "fa_class_2029.json"):
        p = DATA / name
        if not p.exists():
            continue
        cls = json.loads(p.read_text(encoding="utf-8"))
        if cls.get("dpw_usd") is None:
            continue
        cy = int(cls["class_year"])
        want = {k: v for k, v in series.items() if int(k) <= cy - 1}
        assert cls["dpw_series_pricing"] == want, name


def test_the_series_has_one_writer():
    """Only fa_market.write_dpw_series writes the file. The Gate 2 persist used
    to write its own copy with no level, which is how /projections/ came to
    price on a series /fa/ did not."""
    writers = []
    for p in ROOT.glob("*.py"):
        if p.name.startswith("test_"):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"fa_dpw_series\.json[^\n]*\)\s*\.write_text|DPW_SERIES_PATH\.write_text", src):
            writers.append((p.name, m.group(0)))
    assert [w[0] for w in writers] == ["fa_market.py"], writers
    import fa_backtest
    import inspect
    body = inspect.getsource(fa_backtest.run_market_gate)
    assert "fm.write_dpw_series(" in body


def test_the_rebuild_writes_the_series_before_it_prices_anything():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    body = src.split("def rebuild_only(", 1)[1].split("\ndef ", 1)[0]
    i_write = body.index("_write_dpw_series_step(log)")
    i_ts = body.index("export_timeseries_json(")
    i_proj = body.index("from proj_export import export")
    assert i_write < i_ts < i_proj


def test_calibration_is_applied_in_the_unit_it_was_fit_in(monkeypatch):
    """s * f(x / s): at s = 1 the map is untouched; at any s the calibrated
    value of a raw figure s*x is exactly s times the calibrated value of x."""
    cal = vf._config()["calibration"]
    assert cal.get("fit_dpw_flat_usd"), "the calibration block does not name the level it was fit at"
    s_live = vf.calibration_level_scale()
    assert s_live == pytest.approx(float(vf._config()["dollars_per_war"]["flat"])
                                   / float(cal["fit_dpw_flat_usd"]))
    xs = [0.5, 1.3, 4.0, 12.0, 30.0, 150.0]
    monkeypatch.setattr(vf, "calibration_level_scale", lambda: 1.0)
    base = [vf.apply_calibration(x) for x in xs]
    for s in (1.25, 1.46, 0.8):
        monkeypatch.setattr(vf, "calibration_level_scale", lambda s=s: s)
        got = [vf.apply_calibration(x * s) for x in xs]
        assert got == pytest.approx([b * s for b in base], rel=1e-12)


def test_the_identity_set_keeps_its_own_level():
    """prospx_current is byte-identical to the base config by contract: its
    trailing-mean re-anchor still applies and the calibration is not rescaled."""
    with vf.valuation_set("prospx_current"):
        meta = vf._config()["dollars_per_war"].get("_fa_reanchor") or {}
        assert meta.get("method") != "fa_winter_level"
        assert vf.calibration_level_scale() == 1.0


def test_the_trade_engine_reads_the_live_level():
    import inspect

    import bayes_trade_value as btv
    src = inspect.getsource(btv)
    assert "dpw_mm           = 11.74" not in src
    assert "floor_dollars_per_war_mm" not in inspect.getsource(btv.defensive_floor_mm)
    rate = float(vf._config()["dollars_per_war"]["tiered"]["rates"]["1_to_2"]) / 1e6
    # An elite catcher at full grade over a 1-year window: base WAR x the live
    # 1-to-2 tier rate, discounted one season.
    got = btv.defensive_floor_mm("C", 70.0, remaining_years=1)
    cfg = btv._cfg()
    want = float(cfg["defensive_floor_war"]["C"]) * rate / (1.0 + float(cfg.get("floor_discount_rate", 0.09)))
    assert got == pytest.approx(round(want, 2), abs=0.011)


def test_no_copy_still_discloses_two_levels():
    g = _load("glossary.json")
    text = json.dumps(g, ensure_ascii=False)
    assert "prospect surplus prices at the clemens_2026 set's flat" not in text
    for eid in ("rational_value", "winter_dpw", "dpw_tier", "surplus_value", "value_framework"):
        e = next(x for x in g["entries"] if x.get("id") == eid)
        body = " ".join(v for v in e.values() if isinstance(v, str))
        assert "fa_implied re-anchor" not in body or "disabled" not in body, eid
        assert "Two copies of the series are served" not in body, eid
