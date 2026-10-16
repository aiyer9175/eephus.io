# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pitcher drift rebase read (EFV_PIT_DRIFT_REBASE, docs/efv-v2/EFV_PIT_DRIFT_REBASE.md).

1. The fold rule is the served rule: fold_factors calls efv5_combined.rebase_factor with the
   fold's training rows as the support; a planted 1.4x spread is brought back to the
   training SD; under 20 nonzero values nothing moves; apply_rows keeps 0.0 and None.
2. The ship rule is the re-fit's, with S in V5's place, and the flip asks more.
3. The artifact, when present: development only, every fold reproduced, the flip decision
   the registration's, the flag where the decision put it.
4. Gate compliance: no FV-cell grouping, no reserved list vintage, no dash characters.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

import efv5_combined as V5C
import efv5_pit_rebase as X

ROOT = Path(__file__).parent
SRC = ROOT / "efv5_pit_rebase.py"
DOC = ROOT / X.DOC
KEY = "scr_g5_pit_A_all_SP_k_pct"


def _rows(vals, key=KEY):
    return [{"player_key": f"p{i}", "v2": {key: v}} for i, v in enumerate(vals)]


def test_fold_factors_are_the_served_rule():
    rng = np.random.default_rng(3)
    base = rng.normal(0, 1.0, 400)
    train = _rows([0.0] * 300 + list(base[:100]))
    wide = list(rng.normal(0, 1.4, 60))
    test = _rows([0.0] * 140 + wide + [None] * 5)
    f = X.fold_factors(train, test, [KEY])[KEY]
    assert f["train_nonzero"] == 100 and f["test_nonzero"] == 60
    assert f["factor"] == pytest.approx(f["train_sd"] / f["test_sd"])
    out = X.apply_rows(test, factors={KEY: f["factor"]})
    vals = [r["v2"][KEY] for r in out]
    assert vals[:140] == [0.0] * 140 and vals[-5:] == [None] * 5
    assert X.nonzero_sd(vals) == pytest.approx(f["train_sd"])
    # the input rows are never changed in place
    assert [r["v2"][KEY] for r in test][140:200] == wide
    # under SPREAD_MIN_NONZERO nonzero test values: no factor
    few = _rows([0.0] * 50 + list(rng.normal(0, 2, V5C.SPREAD_MIN_NONZERO - 1)))
    assert X.fold_factors(train, few, [KEY])[KEY]["factor"] is None
    assert X.apply_rows(few, factors={KEY: None}) == few


def test_apply_rows_sets_the_sixty_count_and_withholds():
    rows = [{"player_key": "a", "v2": {X.SIXTY: 3.0, KEY: 1.0}},
            {"player_key": "b", "v2": {X.SIXTY: 0.0, KEY: 0.0}}]
    out = X.apply_rows(rows, sixty={"a": 1.0})
    assert out[0]["v2"][X.SIXTY] == 1.0 and out[1]["v2"][X.SIXTY] == 0.0
    w = X.apply_rows(rows, withhold=[KEY, X.SIXTY])
    assert all(r["v2"][KEY] is None and r["v2"][X.SIXTY] is None for r in w)


def test_the_ship_rule_is_the_refits_and_the_flip_asks_more():
    def read(lv, vm):
        return {"lv_dev": {"n": 1397, **{f"{c}_vs_S": {"delta": lv} for c in ("C", "C2", "C1")}},
                "vm_dev": {"n": 424, **{f"{c}_vs_S": {"delta": vm} for c in ("C", "C2", "C1")}}}
    s = X.ship(read(0.001, -0.001))["C"]
    assert s["passes"] is True and s["no_frame_below_zero"] is False
    assert X.ship(read(0.0, 0.0))["C"]["passes"] is False          # a no-op does not pass
    assert X.ship(read(0.01, -0.006))["C"]["rule_no_frame_trails"] is False
    assert X.MAX_TRAIL == 0.005


def test_the_read_artifact():
    """The registered read, when it has run: development only, the flip decision follows
    the registration, and the served flag sits where the decision put it."""
    if not X.OUT_PATH.exists():
        pytest.skip("the read has not run in this tree")
    d = json.loads(X.OUT_PATH.read_text(encoding="utf-8"))
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["frames"] == ["lv_dev", "vm_dev"] and d["side"] == "pit"
    assert set(d["rebase_keys"]) == V5C.REBASE_KEYS
    assert d["served_weights"] == {"w_skill": 1.0, "w_time": 0.0}
    assert {k.split("|")[0] for k in d["folds"]} == {"lv_dev", "vm_dev"}
    assert all(int(k.split("|")[2]) < 2025 for k in d["folds"])
    assert {int(k.split("|")[2]) for k in d["folds"] if k.startswith("lv_dev")} == {2017, 2018, 2019}
    c = d["ship"]["C"]
    want = bool(c["passes"] and d["planted"]["recovered"] and c["no_frame_below_zero"])
    assert d["flip"]["flip"] is want
    assert V5C.DRIFT_REBASE_ON is want
    b = d["board"]
    assert b["hitters_unchanged"] is True
    assert set(b["rebased_receipt"]) >= V5C.REBASE_KEYS
    assert d["sixty_receipts"]["training_share_kept"] >= 0.99


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert not any(bad in n.lower() for n in names), bad
    assert "run_backtest" not in names          # named in the docstring, never called
    assert max(X.LV_DEV) < min(X.F.RESERVED_LV)
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in src
        assert ch not in DOC.read_text(encoding="utf-8")
