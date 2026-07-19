# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Multi-horizon WAR-path eval CLI guards: the --bases range parser (interior
cohorts must not drop) and the persist merge (challenger_blocks owned by other
tools must survive a champion re-run)."""

from __future__ import annotations

import json
import sys

import proj_eval as pe


def test_parse_bases_expands_inclusive_range():
    """A documented 'lo-hi' range must include every interior cohort - the old
    endpoint-only parse silently dropped 2018-2020 from '2017-2021', biasing
    the holdout ship decision."""
    assert pe._parse_bases("2017-2021") == [2017, 2018, 2019, 2020, 2021]
    # the touched-once confirmation holdout from the docstring
    assert pe._parse_bases("2022-2024") == [2022, 2023, 2024]


def test_parse_bases_comma_form_preserves_covid_gap():
    """Plain comma tokens parse as literals, so the dashless default keeps its
    deliberate 2020 omission (COVID)."""
    assert pe._parse_bases("2017,2018,2019,2021") == [2017, 2018, 2019, 2021]
    assert pe._parse_bases("2020") == [2020]


def test_parse_bases_dedups_sorts_and_mixes():
    """Mixed comma + range tokens de-dup and sort; reversed ranges normalize."""
    assert pe._parse_bases("2019,2017-2018,2017") == [2017, 2018, 2019]
    assert pe._parse_bases("2021-2019") == [2019, 2020, 2021]
    assert pe._parse_bases(" 2022 , 2020-2021 ") == [2020, 2021, 2022]


def test_persist_preserves_challenger_blocks(tmp_path, monkeypatch):
    """A default (persisting) `python proj_eval.py` recomputes only the champion
    top-level keys; the top-level challenger_blocks written by other tools
    (train_proj_models / *_backtest) must survive the write, or the
    /projections/ accountability 'Veteran WAR paths' card empties out."""
    artifact = tmp_path / "proj_horizon_eval.json"
    artifact.write_text(json.dumps({
        "model": "old_champion", "bases": [2017], "n_players": 1,
        "horizons": {"1": {"mae": 0.9}},
        "challenger_blocks": {
            "holdout_2022_2024": {"horizons": {"1": {"mae": 0.5}}},
            "mean_head_rejected": {"note": "keep me"},
        },
    }), encoding="utf-8")

    # Stub the heavy run() (corpus build) - we are exercising main()'s persist
    # merge, not the eval math. horizons={} keeps main()'s print loop a no-op.
    fake = {"model": "new_champion", "bases": [2023], "n_players": 42,
            "horizons": {}}
    monkeypatch.setattr(pe, "run", lambda bases, persist=True, **kw: fake)
    monkeypatch.setattr(pe, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["proj_eval.py"])   # persist is the default

    pe.main()

    out = json.loads(artifact.read_text(encoding="utf-8"))
    # champion keys updated in place ...
    assert out["model"] == "new_champion"
    assert out["n_players"] == 42
    # ... and the tool-owned governance receipts preserved verbatim
    cb = out.get("challenger_blocks") or {}
    assert set(cb) == {"holdout_2022_2024", "mean_head_rejected"}
    assert cb["holdout_2022_2024"]["horizons"]["1"]["mae"] == 0.5
    assert cb["mean_head_rejected"]["note"] == "keep me"


def test_no_persist_leaves_artifact_untouched(tmp_path, monkeypatch):
    """--no-persist must not write the artifact at all."""
    artifact = tmp_path / "proj_horizon_eval.json"
    artifact.write_text(json.dumps({"challenger_blocks": {"x": 1}}),
                        encoding="utf-8")
    before = artifact.read_text(encoding="utf-8")
    monkeypatch.setattr(pe, "run", lambda bases, persist=True, **kw: {
        "model": "m", "bases": [2023], "n_players": 1, "horizons": {}})
    monkeypatch.setattr(pe, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["proj_eval.py", "--no-persist"])
    pe.main()
    assert artifact.read_text(encoding="utf-8") == before
