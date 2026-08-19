# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Row-matched champion-vs-challenger guards on data/proj_horizon_eval.json.

Three invariants, one incident class each:
  1. generated_at exists at the top level (the artifact sat undated; the
     freshness map ages undated artifacts by mtime, which the deploy box's
     nightly checkout rewrites).
  2. The row-matched block scores BOTH models on identical rows: one n per
     cell, shared by champion and challenger (the gate1_targets h1 0.5569
     vs the champion's 0.647 sat on DIFFERENT base sets, inviting a false
     win claim off mismatched bases).
  3. The tool-owned challenger_blocks (holdout receipts in particular)
     survive the writer (the 2026-06-11 key-collision incident: a writer
     that clobbers instead of read-modify-write destroys committed
     governance receipts).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import proj_eval as pe

ARTIFACT = Path(__file__).parent / "data" / "proj_horizon_eval.json"


def _artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_generated_at_present():
    """Top-level generated_at, ISO-shaped: the artifact must date itself so
    model_registry.freshness() never falls back to a checkout mtime."""
    d = _artifact()
    stamp = d.get("generated_at")
    assert isinstance(stamp, str) and len(stamp) >= 10, "generated_at missing"
    # ISO date prefix YYYY-MM-DD
    assert stamp[:4].isdigit() and stamp[4] == "-" and stamp[7] == "-"


def test_rowmatch_block_identical_n_per_cell():
    """Every row-matched cell carries ONE n, identical for both models: a
    (player, horizon) row enters only when champion AND challenger both
    produced a path for it. Unequal n means the cut regressed to the
    mismatched-base comparison it exists to replace."""
    d = _artifact()
    block = d.get("rowmatch_champion_vs_challenger")
    assert block, "row-matched block missing from the artifact"
    assert block.get("generated_at"), "row-matched block must date itself"
    assert block.get("champion_model") == "marcel_decay_v2"
    assert block.get("challenger_model") == "proj_lgbm_v1"
    horizons = block.get("horizons") or {}
    assert horizons, "row-matched block has no horizon cells"
    for h, cell in horizons.items():
        champ, chal = cell["champion"], cell["challenger"]
        assert champ["n"] == chal["n"] == cell["n"], (
            f"h{h}: champion n {champ['n']} != challenger n {chal['n']} "
            f"(cell n {cell['n']}) - the cut is no longer row-matched")
        assert cell["n"] > 0
        assert champ["n_star"] == chal["n_star"], (
            f"h{h}: star cells diverge ({champ['n_star']} vs {chal['n_star']})")
        # both models scored: the headline metrics exist on the shared rows
        for side_block in (champ, chal):
            assert side_block["mae"] is not None
            assert "tail_ratio" in side_block


def test_rowmatch_shares_tail_actual():
    """tail_act_ge3 is a property of the SHARED rows, so it lives once per
    cell; each model's tail_ratio divides its own tail_pred_ge3 by it."""
    block = _artifact().get("rowmatch_champion_vs_challenger") or {}
    for h, cell in (block.get("horizons") or {}).items():
        ta = cell["tail_act_ge3"]
        for m in ("champion", "challenger"):
            tr = cell[m]["tail_ratio"]
            if ta:
                assert tr == round(cell[m]["tail_pred_ge3"] / ta, 3), (
                    f"h{h} {m}: tail_ratio inconsistent with tail counts")
            else:
                assert tr is None


def test_holdout_blocks_survived_regeneration():
    """The touched-once holdout receipts and the other tool-owned challenger
    blocks must survive every proj_eval persist (read-modify-write, never
    clobber - the 2026-06-11 key-collision warning)."""
    cb = _artifact().get("challenger_blocks") or {}
    for key in ("holdout_2022_2024", "holdout_2022_2024_champion",
                "holdout_2022_2024_starblend", "gate1_targets", "dev"):
        assert key in cb, f"challenger_blocks.{key} was clobbered"
    # frozen governance receipts: spot-pin one committed value per holdout block
    assert cb["holdout_2022_2024"]["horizons"]["1"]["mae"] == 0.5394
    assert cb["holdout_2022_2024_champion"]["horizons"]["1"]["mae"] == 0.6179
    assert cb["holdout_2022_2024_starblend"]["horizons"]["2"]["tail_ratio"] == 0.254


def test_writer_merges_rowmatch_without_clobber(tmp_path, monkeypatch):
    """main() --rowmatch adds its block and generated_at through the same
    read-modify-write path; challenger_blocks and unrelated top-level keys
    survive verbatim. Heavy runs stubbed - this exercises the merge, not
    the eval math."""
    artifact = tmp_path / "proj_horizon_eval.json"
    artifact.write_text(json.dumps({
        "model": "old_champion", "horizons": {},
        "challenger_blocks": {"holdout_2022_2024": {"keep": True}},
        "unrelated_key": "keep me",
    }), encoding="utf-8")

    fake_champ = {"model": "marcel_decay_v2", "bases": [2017], "n_players": 3,
                  "horizons": {}}
    fake_rm = {"generated_at": "2026-08-19T00:00:00Z",
               "champion_model": "marcel_decay_v2",
               "challenger_model": "proj_lgbm_v1",
               "bases": [2017], "n_players_matched": 3, "horizons": {}}
    monkeypatch.setattr(pe, "run", lambda bases, persist=True, **kw: fake_champ)
    monkeypatch.setattr(pe, "run_rowmatch", lambda bases: fake_rm)
    monkeypatch.setattr(pe, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["proj_eval.py", "--rowmatch"])

    pe.main()

    out = json.loads(artifact.read_text(encoding="utf-8"))
    assert out["model"] == "marcel_decay_v2"
    assert out["rowmatch_champion_vs_challenger"] == fake_rm
    assert isinstance(out.get("generated_at"), str)
    assert out["challenger_blocks"] == {"holdout_2022_2024": {"keep": True}}
    assert out["unrelated_key"] == "keep me"
