# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The consensus weight A/B stamps the label it was scored on (POSTEPOCH_6).

data/consensus_weight_eval.json was written before the fWAR label epoch and
carried no label, so a reader could not tell which WAR series the reading came
from. run_consensus_weight_ab now writes a 'label' block. These tests run the A/B
on an empty temporary data directory (hermetic and fast; nothing under data/ is
read or written) and pin that the ship rule and its two constants did not move.
"""

from __future__ import annotations

import inspect
import json

import efv_dataset
import source_backtest
import war_source


def test_label_block_present_and_names_the_label(tmp_path):
    (tmp_path / "fwar_vintage.json").write_text(
        json.dumps({"schema": "fwar_vintage/1", "vintage_id": "test-vintage-1"}),
        encoding="utf-8")
    r = source_backtest.run_consensus_weight_ab(data_dir=tmp_path, write=False)
    assert "label" in r
    lab = r["label"]
    assert set(lab) == {"provider", "resolved_through", "vintage"}
    assert lab["provider"] == war_source.DEFAULT_PROVIDER
    assert lab["resolved_through"] == efv_dataset.RESOLVED_THROUGH
    if lab["provider"] == "fwar":
        assert lab["vintage"] == "test-vintage-1"
    else:
        assert lab["vintage"] is None
    # write=False writes nothing
    assert not (tmp_path / "consensus_weight_eval.json").exists()
    assert not (tmp_path / "source_weights.json").exists()


def test_label_vintage_is_none_when_the_vintage_file_is_missing(tmp_path):
    lab = source_backtest._consensus_ab_label(tmp_path)
    assert lab["provider"] == war_source.DEFAULT_PROVIDER
    assert lab["vintage"] is None


def test_label_is_written_into_the_artifact(tmp_path):
    (tmp_path / "fwar_vintage.json").write_text(
        json.dumps({"vintage_id": "test-vintage-2"}), encoding="utf-8")
    source_backtest.run_consensus_weight_ab(data_dir=tmp_path, write=True)
    d = json.loads((tmp_path / "consensus_weight_eval.json").read_text(encoding="utf-8"))
    assert d["label"]["provider"] == war_source.DEFAULT_PROVIDER
    assert d["label"]["resolved_through"] == efv_dataset.RESOLVED_THROUGH
    # an empty universe can never ship a weight
    assert d["ship"] is False
    assert not (tmp_path / "source_weights.json").exists()


def test_ship_rule_and_constants_unchanged():
    src = inspect.getsource(source_backtest.run_consensus_weight_ab)
    assert "_SHIP_MIN_RHO_GAIN = 0.0068" in src
    assert "_SHIP_MIN_AUC_GAIN = 0.0052" in src
    flat = " ".join(src.split())
    assert ("ship = (summary[\"weighted\"][\"spearman\"] is not None "
            "and summary[\"weighted\"][\"auc\"] is not None "
            "and _d_rho >= _SHIP_MIN_RHO_GAIN "
            "and _d_auc >= _SHIP_MIN_AUC_GAIN)") in flat
