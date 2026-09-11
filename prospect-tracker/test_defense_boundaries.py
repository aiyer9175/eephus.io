# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The four hard stops DEM+ shipped under, enforced (DEM_PLUS_GATE.md section 5).

  C1  no eFV / xFV reader (do-not-reopen 17)
  C2  one fielding source in the core: no OAA, DRS or eWAR import (the banned
      OAA/rfield blend class lives outside SDR gates G-A/G-B)
  C3  eWAR fielding untouched (fielding_blend_w stays 0.0)
  C4  nothing served in betting reads the board before its own pre-registration
  C6  the projections war map never reads the index
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent
NAMES = re.compile(r"dem_plus|defense_leaderboards|defense_export")


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def test_no_efv_module_reads_dem_plus():
    hits = [p.name for p in list(ROOT.glob("efv_*.py")) + list(ROOT.glob("xfv*.py"))
            if NAMES.search(_src(p))]
    assert not hits, f"eFV modules must not read DEM+ (do-not-reopen 17): {hits}"


def test_core_has_one_fielding_source():
    src = _src(ROOT / "dem_plus.py")
    for banned in ("savant_oaa", "war_source", "import ewar", "runs_field",
                   "runs_defense", "oaa"):
        assert banned not in src.lower().replace("outs above average", ""), banned


def test_ewar_does_not_import_the_defense_modules():
    src = _src(ROOT / "ewar.py")
    assert not NAMES.search(src)
    # the blend weight defaults to None and None reads as 0.0
    assert re.search(r"fielding_blend_w:\s*float\s*\|\s*None\s*=\s*None", src)
    assert "0.0 if fielding_blend_w is None" in src


def test_betting_and_vintages_do_not_read_defense():
    for name in ("betting_model.py", "betting_export.py", "leaderboard_vintages.py",
                 "betting_usage.py", "dfs_export.py"):
        p = ROOT / name
        if p.exists():
            assert not NAMES.search(_src(p)), f"{name} reads the DEM+ board"


def test_war_map_does_not_read_the_index():
    assert not NAMES.search(_src(ROOT / "fa_projection.py"))
