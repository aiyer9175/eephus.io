# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins the shared stabilization / baseline constants (audit F-05 / F-06).

Two guarantees:
  1. The values never drift silently: each constant is pinned to the exact
     literal it replaced in the 2026-07-01 centralization (a byte-identical
     refactor; changing any value is a model change and needs its own eval).
  2. Every consuming module references the SHARED object, not a re-typed
     local literal: `is` identity against rate_stabilization (float literals
     are per-code-object constants in CPython, so a re-typed 170.0 in a
     consumer would be a different object), plus a source scan proving the
     old literals are gone. SLOPE_SHRINK_K is a small int (always interned),
     so for it the source scan is the real guard.
"""
from pathlib import Path

import rate_stabilization as rs

ROOT = Path(__file__).parent


def _src(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_values_pinned_exactly():
    assert rs.K_AB == 170.0 and isinstance(rs.K_AB, float)
    assert rs.K_IP == 50.0 and isinstance(rs.K_IP, float)
    assert rs.NEED_ERA_SHRINK_IP == 45.0 and isinstance(rs.NEED_ERA_SHRINK_IP, float)
    assert rs.BF_PER_9 == 38.0 and isinstance(rs.BF_PER_9, float)
    assert rs.SLOPE_SHRINK_K == 20 and isinstance(rs.SLOPE_SHRINK_K, int)
    assert rs.REPLACEMENT_WINS == 47.7 and isinstance(rs.REPLACEMENT_WINS, float)


def test_module_sits_at_the_bottom_of_the_import_graph():
    # storage.py (imported nearly everywhere) imports rate_stabilization, so
    # the constants module must never import anything at all: any import here
    # is one refactor away from a cycle.
    for line in _src("rate_stabilization.py").splitlines():
        stripped = line.strip()
        assert not stripped.startswith(("import ", "from ")), line


def test_storage_references_shared():
    import storage
    assert storage.K_AB is rs.K_AB
    assert storage.K_IP is rs.K_IP
    src = _src("storage.py")
    assert "K_AB = 170" not in src
    assert "K_IP = 50" not in src


def test_pal_conversion_references_shared():
    import pal_conversion
    assert pal_conversion.NEED_ERA_SHRINK_IP is rs.NEED_ERA_SHRINK_IP
    assert "NEED_ERA_SHRINK_IP = 45" not in _src("pal_conversion.py")


def test_college_translation_references_shared():
    import college_translation
    assert college_translation.BF_PER_9 is rs.BF_PER_9
    assert college_translation.SLOPE_SHRINK_K is rs.SLOPE_SHRINK_K
    assert college_translation.SLOPE_SHRINK_K == 20   # int guard (see docstring)
    src = _src("college_translation.py")
    assert "BF_PER_9 = 38" not in src
    assert "SLOPE_SHRINK_K = 20" not in src


def test_replacement_wins_shared():
    import proj_backtest
    import proj_export
    assert proj_export.REPLACEMENT_WINS is rs.REPLACEMENT_WINS
    assert proj_backtest.REPLACEMENT_WINS is rs.REPLACEMENT_WINS
    for name in ("proj_export.py", "proj_backtest.py"):
        assert "REPLACEMENT_WINS = 47.7" not in _src(name)
