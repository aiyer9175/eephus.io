# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA module's PROSPX contract: READ-ONLY, ADDITIVE-ONLY.

Static source guards (cheap, run on every suite pass):
  1. No fa_* module may write to any non-fa table — every storage upsert
     it touches must be an upsert_fa_* accessor, and any raw SQL INSERT/
     UPDATE/DELETE must target fa_* tables only.
  2. The boot export stays additive: the FA module ships exclusively as
     lazy sidecars advertised in `_slices` — no new top-level boot keys.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
FA_MODULES = ["fa_sources.py", "fa_cba.py", "fa_class.py", "fa_projection.py",
              "fa_market.py", "fa_fit.py", "fa_export.py", "fa_backtest.py",
              "fa_pipeline.py", "fa_ident.py"]


def test_fa_modules_never_write_prospect_tables():
    for mod in FA_MODULES:
        src = (ROOT / mod).read_text(encoding="utf-8")
        # storage accessor calls: only fa-prefixed upserts allowed
        for call in re.findall(r"\bupsert_(\w+)", src):
            assert call.startswith("fa_") or mod == "fa_backtest.py" and call.startswith("fa_"), \
                f"{mod} calls upsert_{call} — non-FA write"
        # raw SQL: any INSERT/UPDATE/DELETE must hit fa_* tables
        for stmt in re.findall(r"(?i)\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+)", src):
            table = stmt[1].lower()
            assert table.startswith("fa_"), f"{mod} raw SQL touches {table}"


def test_fa_storage_accessors_only_touch_fa_tables():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    fa_section = src.split("MLB Free Agency module — storage accessors")[-1]
    for stmt in re.findall(r"(?i)\b(?:INSERT\s+INTO|FROM)\s+\{?([a-z_{}]+)", fa_section):
        t = stmt.strip("{}").lower()
        if t in ("table",):                      # the parameterized helper
            continue
        assert t.startswith("fa_"), f"FA storage section references {t}"


def test_boot_export_additive_only():
    """The FA module adds zero top-level boot keys — sidecars only."""
    boot = ROOT / "data" / "timeseries.json"
    if not boot.exists():
        pytest.skip("no boot export on this machine")
    d = json.loads(boot.read_text(encoding="utf-8"))
    for k in ("fa_class", "fa_archive", "fa_meta"):
        assert k not in d, f"{k} leaked into the boot payload"
        assert d.get("_slices", {}).get(k) == f"{k}.json", f"{k} not advertised in _slices"


def test_sidecars_exist_and_parse():
    for name in ("fa_class.json", "fa_archive.json", "fa_meta.json"):
        path = ROOT / "data" / name
        if not path.exists():
            pytest.skip(f"{name} not exported on this machine")
        d = json.loads(path.read_text(encoding="utf-8"))
        assert d.get("generated_at")
    cls = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    assert cls["n_members"] > 150 and cls["n_projected"] > 100
    top = cls["members"][0]
    # the board's two numbers ride every projected member, never conflated
    assert "mGuar" in top and "rational" in top and "surplus" in top
    assert top["surplus"] == top["rational"] - top["mGuar"]
