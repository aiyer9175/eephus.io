# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The farm glossary entries describe the ONE WAG definition (storage.WAG_UNIFIED, owner
decision 14b, 2026-09-11): Boom / Bust / Talent Translation read the engine label, keyed
on percentiles of the expectation at the eFV grade at debut and gated on measured MLB
exposure. The numbers quoted are the ones value_framework applies."""
from __future__ import annotations

import json
from pathlib import Path

import storage
import value_framework as vf

ROOT = Path(__file__).parent
RETIRED = ("+2.5", "-1.5", "\u22121.5", "800 PA", "legacy WAG", "2+ MLB WAR seasons")


def _g() -> dict:
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in g["entries"]}


def _text(e: dict) -> str:
    return " ".join(str(e.get(k) or "") for k in ("definition", "methodology", "formula", "example"))


def test_the_farm_boom_bust_copy_quotes_the_engine_rules():
    assert storage.WAG_UNIFIED is True
    cfg = vf._config()["wag"]
    bb, me = cfg["boom_bust"], cfg["meaningful_exposure"]
    gate = f"{int(me['hitter_pa'])} PA or {int(me['pitcher_ip'])} IP"
    boom_pct = f"{round(float(bb['boom_percentile']) * 100)}th percentile"
    bust_pct = f"{round(float(bb['bust_percentile']) * 100)}th percentile"
    g = _g()
    for eid in ("farm_grade_mlb_production", "mlb_production_boom_pct",
                "mlb_production_bust_pct", "farm_grade_talent_translation"):
        t = _text(g[eid])
        assert gate in t, eid
        for r in RETIRED:
            assert r not in t, (eid, r)
    assert boom_pct in _text(g["mlb_production_boom_pct"])
    assert bust_pct in _text(g["mlb_production_bust_pct"])
    assert boom_pct in _text(g["farm_grade_mlb_production"])
    assert "eFV grade at debut" in _text(g["farm_grade_talent_translation"])


def test_the_survivor_curve_is_no_longer_called_the_wag_baseline():
    g = _g()
    fv = _text(g["fv_to_war_table"])
    assert "legacy WAG" not in fv and "(WAG baseline)" not in fv
    assert "overseas signing WAG baseline" in fv
    assert "not the engine WAG" in g["overseas_posting_class"]["methodology"]
