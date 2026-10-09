# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The per-year vintage-matched block (owner answer M7-1, 2026-09-25).

Registered in docs/efv-2026-09-25/PER_YEAR_BLOCK.md before any per-cohort number
existed. The writer splits the headline vm2 rows by debut year, adds and drops
nothing, scores the four registered graders on identical rows, derives the E_cond
floor only for a cohort of at least PER_YEAR_VM_MIN_N rows, and marks every other
cohort under its floor. The chart side is pinned in test_source_comparison_basis.py.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

import source_backtest as SB

ROOT = Path(__file__).parent
DOC = ROOT / "docs" / "efv-2026-09-25" / "PER_YEAR_BLOCK.md"
DATA = ROOT / "data" / "source_backtest.json"


def test_registration_constants_match_the_gate_doc():
    text = DOC.read_text(encoding="utf-8")
    assert SB.PER_YEAR_VM_REGISTRATION == "docs/efv-2026-09-25/PER_YEAR_BLOCK.md"
    assert SB.PER_YEAR_VM_MIN_N == 40 and "Minimum n: 40 rows" in text
    assert SB.PER_YEAR_VM_GRADERS == ("xfv", "prospx_consensus", "mlb_pipeline",
                                      "fangraphs")
    assert SB.PER_YEAR_VM_KEY == "per_year_vintage_matched"
    assert "accuracy.per_year_vintage_matched" in text


def _rows(year: int, n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        war = rng.gauss(2.0, 3.0)
        out.append({
            "key": f"p{year}_{i}", "year": year,
            "grades": {g: 45 + war + rng.gauss(0, 3 + k)
                       for k, g in enumerate(SB.PER_YEAR_VM_GRADERS)},
            "outcome": {"war": war, "contributor": war >= 5},
        })
    return out


def test_partition_floor_and_hollow_flags():
    pytest.importorskip("numpy")
    rows = _rows(2019, 45, 1) + _rows(2020, 39, 2) + _rows(2021, 12, 3)
    blk = SB._per_year_vintage_matched(rows)
    assert blk["frame_version"] == "vm2" and blk["basis"] == SB.VM2_BASIS
    assert blk["min_n"] == 40 and blk["graders"] == list(SB.PER_YEAR_VM_GRADERS)
    assert blk["n_total"] == len(rows)
    c = blk["cohorts"]
    assert sorted(c) == ["2019", "2020", "2021"]
    assert [c[y]["n"] for y in ("2019", "2020", "2021")] == [45, 39, 12]
    for y in c:
        assert set(c[y]["spearman"]) == set(SB.PER_YEAR_VM_GRADERS)
        assert all(v is not None for v in c[y]["spearman"].values())
    assert c["2019"]["under_floor"] is False
    fl = c["2019"]["floor_vs_efv"]
    assert set(fl) == {"prospx_consensus", "mlb_pipeline", "fangraphs"}
    for f in fl.values():
        assert f["mde95"] and f["estimator"] == "E_cond" and f["B"] == SB._CLAIM_BOOT_B
        assert f["seed"] == SB._CLAIM_SEED and f["n"] == 45
    for y in ("2020", "2021"):
        assert c[y]["under_floor"] is True and c[y]["floor_vs_efv"] is None


def test_block_carries_no_verdict_word():
    pytest.importorskip("numpy")
    blob = json.dumps(SB._per_year_vintage_matched(_rows(2019, 50, 4)))
    for word in ("verdict", "beats", "wins", "best", "resolvable"):
        assert word not in blob, word


def test_served_block_partitions_the_headline_frame():
    if not DATA.exists():
        pytest.skip("data/source_backtest.json absent (gitignored build artifact)")
    acc = json.loads(DATA.read_text(encoding="utf-8")).get("accuracy") or {}
    blk = acc.get("per_year_vintage_matched")
    if not blk:
        pytest.skip("source_backtest.json predates the per-year vintage-matched block")
    hv = acc["head_to_head_verdict"]
    assert blk["basis"] == hv["basis"] == SB.VM2_BASIS
    assert blk["n_total"] == hv["n"] == sum(c["n"] for c in blk["cohorts"].values())
    for y, c in blk["cohorts"].items():
        assert int(y) < 2025, "an R-VM debut cohort reached the per-year block"
        assert set(c["spearman"]) == set(blk["graders"])
        if c["n"] < blk["min_n"]:
            assert c["under_floor"] is True and c["floor_vs_efv"] is None
        if c["under_floor"] is False:
            assert all(f.get("mde95") for f in c["floor_vs_efv"].values())
