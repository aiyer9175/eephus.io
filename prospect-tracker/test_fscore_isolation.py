# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""F-SCORE is descriptive, so nothing that serves a forecast, a price or a
grade may read it (plan Part 8 8.A; fscore.md 4.7).

The only READERS of fscore.json are fscore_export.py (its writer),
franchise_export.py (the Franchise embed), assets/franchise.js (the page),
team_stats_export.py (the one Teams column), assets/mlbstats-league.js (the
Teams tab) and build_site.py. Two modules may NAME the file without reading
it: run_monthly.py (its step label) and data_catalog.py (the catalog row the
flip adds). Every other Python module under the module root and tools/, and
every script under assets/, must not mention it; test files are exempt.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN = "fscore.json"

READERS = {"fscore_export.py", "franchise_export.py", "assets/franchise.js",
           "team_stats_export.py", "assets/mlbstats-league.js", "build_site.py"}
NAMERS = {"run_monthly.py", "data_catalog.py"}


def _candidates():
    for p in ROOT.glob("*.py"):
        yield p
    for p in (ROOT / "tools").rglob("*.py"):
        yield p
    for p in (ROOT / "assets").rglob("*.js"):
        yield p


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def test_only_the_named_modules_mention_fscore_json():
    found = set()
    for p in _candidates():
        if p.name.startswith("test_") or p.name == "conftest.py":
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if TOKEN in txt:
            found.add(_rel(p))
    stray = sorted(found - READERS - NAMERS)
    assert not stray, f"modules outside the allowed readers mention {TOKEN}: {stray}"
    assert "fscore_export.py" in found


def test_no_betting_efv_eta_fa_projection_or_arbitration_module_reads_it():
    fenced = ("betting", "efv", "eta", "fa_", "proj", "arb", "value_framework", "surplus")
    for p in _candidates():
        if p.name.startswith("test_"):
            continue
        if any(p.name.startswith(f) for f in fenced):
            txt = p.read_text(encoding="utf-8", errors="replace")
            assert TOKEN not in txt and "fscore_export" not in txt, _rel(p)


def test_the_franchise_and_teams_readers_import_the_flag_not_a_copy_of_it():
    fe = (ROOT / "franchise_export.py").read_text(encoding="utf-8")
    ts = (ROOT / "team_stats_export.py").read_text(encoding="utf-8")
    assert "fscore_export.FSCORE_LIVE" in fe and "FSCORE_LIVE = " not in fe
    assert "fscore_export.FSCORE_LIVE" in ts and "FSCORE_LIVE = " not in ts
