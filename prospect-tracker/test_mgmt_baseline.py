# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The matched-state league baseline (mgmt_baseline.py) behind decision value above
state: the identity holds in every cell, thin cells are excluded and counted, the
baseline removes the level of the state and nothing else, and the selection caveat
is stated for the two families where it bites."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import mgmt_baseline as MB  # noqa: E402

BASELINE = ROOT / "data" / "management_baseline.json"
ART = ROOT / "data" / "management_decisions.json"
BOARD = ROOT / "data" / "management_board.json"
SHARDS = ROOT / "data" / "mgmt_decisions"


@pytest.fixture(scope="module")
def base():
    if not BASELINE.exists():
        pytest.skip("run python mgmt_decisions.py")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_dvs_sums_to_zero_over_all_league_windows_in_every_cell(base):
    """Checked, not asserted: the artifact publishes the largest absolute mean
    residual it found, and it is float noise."""
    for f, blk in base["families"].items():
        if blk.get("identity_max_abs") is None:
            continue
        assert blk["identity_max_abs"] < 1e-9, (f, blk["identity_max_abs"])
    # and on a synthetic frame, through the same function
    got = MB._cells_from(None, ["a", "a", "a", "b", "b"], [0.1, 0.2, 0.3, -0.5, 0.5])
    assert got["identity_max_abs"] < 1e-12
    assert got["cells"]["a"]["mean_mwpa"] == pytest.approx(0.2)
    assert got["cells"]["b"]["mean_mwpa"] == pytest.approx(0.0)


def test_thin_cells_are_excluded_and_counted(base):
    assert base["min_cell"] == MB.MIN_CELL == 25
    assert base["cell_columns"] == ["n", "mean_mwpa"], "cells are [n, mean_mwpa]; thin is n below min_cell"
    for f, blk in base["families"].items():
        if "cells" not in blk:
            assert blk["same_cells_as"] in base["families"]
            continue
        thin = sum(1 for c in blk["cells"].values() if c[0] < MB.MIN_CELL)
        assert thin == blk["thin_cells"], f
        assert blk["n_cells"] == len(blk["cells"]), f
    # under the registry's stamp-parse ceiling, or the artifact reads as undated
    import model_registry as mr
    assert BASELINE.stat().st_size <= mr._MAX_STAMP_PARSE_BYTES
    assert mr._artifact_date(BASELINE) is not None
    # a served decision that lands in a thin cell carries no DVS
    if not ART.exists() or not SHARDS.exists():
        pytest.skip("no served ledger")
    art = json.loads(ART.read_text(encoding="utf-8"))
    idx = [e for e in art["shards"]["index"] if e["season"] == 2025] or art["shards"]["index"]
    if not idx:
        pytest.skip("no shards")
    import mgmt_shards
    sh = json.loads((SHARDS / f"{idx[0]['season']}-{idx[0]['club']}.json").read_text(encoding="utf-8"))
    checked = 0
    # schema 2 shards carry coded families, not rows; read them through the one reader
    for r in mgmt_shards.expand(sh):
        if r["family"] != "pitching_change" or "mwpa" not in r:
            continue
        sd_home = r["score_diff"] if r["home"] else -r["score_diff"]
        key = MB.cell_key(sh["season"], r["inning"], r["half"], r["outs"], r["base"], sd_home)
        cell = base["families"]["pitching_change"]["cells"].get(key)
        if cell is None or cell[0] < MB.MIN_CELL:
            assert "dvs" not in r, (key, r.get("dvs"))
        else:
            assert "dvs" in r and abs(r["dvs"] - (r["mwpa"] - cell[1])) < 2e-4, key
        checked += 1
    assert checked > 50
    for f in ("pitching_change", "pinch_hit"):
        assert art["families"][f]["thin_cells"]["cells_thin"] == base["families"][f]["thin_cells"]


def test_baseline_removes_the_state_level_on_a_synthetic_frame():
    """Two cells with different levels: DVS is the decision's window minus ITS cell's
    mean, so the same realized figure reads differently from the two spots."""
    got = MB._cells_from(None, ["hot"] * 4 + ["cold"] * 4, [0.03, 0.07, 0.05, 0.05, -0.04, 0.00, -0.02, -0.02])
    hot, cold = got["cells"]["hot"]["mean_mwpa"], got["cells"]["cold"]["mean_mwpa"]
    assert hot == pytest.approx(0.05) and cold == pytest.approx(-0.02)
    mwpa = 0.06
    assert mwpa - hot == pytest.approx(0.01)
    assert mwpa - cold == pytest.approx(0.08)
    assert MB.cell_key(2025, 7, "bottom", 1, 5, 2) == "2025|7|bottom|1|5|+2"
    assert MB.cell_key(2025, 9, "top", 0, 0, -9) == "2025|9+|top|0|0|<=-4"
    assert MB.score_bucket(0) == "0" and MB.inning_bucket(12) == "9+" and MB.inning_bucket(3) == "1-3"


def test_selection_caveat_is_stated_for_ibb_and_pinch_hit(base):
    sc = base["selection_caveat"]
    assert "biased FOR the walk" in sc["intentional_walk"]
    assert "Stated, not solved" in sc["intentional_walk"] and "Stated, not solved" in sc["pinch_hit"]
    assert "single" in base["single_pa_caveat"] and "NOT an independent second number" in base["single_pa_caveat"]
    assert "never" in base["where_dvs_lives"]
    if BOARD.exists():
        b = json.loads(BOARD.read_text(encoding="utf-8"))
        served = b["decisions"]["baseline"]
        assert served["selection_caveat"] == sc
        assert "cells" not in served["families"]["pitching_change"], "the board never carries the cell table"
