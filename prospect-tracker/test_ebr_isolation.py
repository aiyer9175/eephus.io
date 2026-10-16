# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eBR's isolation (EBR_GATE.md I9, part 5 and part 7.6).

No fitted consumer (efv_*, proj_*, fa_*, arb_*, betting_* or leaderboard_vintages)
imports ebr or reads .cache/ebr or data/ebr*; no betting module reads a
baserunning file or an ebr key; only tools/build_ebr.py and tools/ebr_gate.py
import the core, and only the look computes a year-to-year, split-half or forward
statistic; and a build leaves .cache/pbp_corpus, the management files, eWAR v2's
artifact, the sprint file and war_source.PROVIDERS byte-identical.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_ebr  # noqa: E402
import ebr  # noqa: E402

FITTED = ("efv_", "proj_", "fa_", "arb_", "betting_")
CORE_NAMES = {"ebr", "build_ebr", "ebr_gate"}
READS = re.compile(r"(\.cache/ebr|\.cache\W+ebr\b|data/ebr|ebr\.json|ebr_eval)")
BETTING_READS = re.compile(r"(baserunning|savant_running|pbp_runners|[\"']ebr[\"'])")
GUARDED = (ROOT / "data" / "management_running.json", ROOT / "data" / "management_board.json",
           ROOT / "data" / "ewar.json", ROOT / "data" / "savant_sprint.json")


def _modules():
    return sorted(list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")))


def _imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module.split(".")[0])
    return out


def _fitted(p: Path) -> bool:
    return p.name.startswith(FITTED) or p.name == "leaderboard_vintages.py"


def test_no_fitted_consumer_imports_ebr_or_reads_its_artifacts():
    fitted = [p for p in _modules() if _fitted(p)]
    assert len(fitted) > 100 and any(p.name == "leaderboard_vintages.py" for p in fitted)
    bad = []
    for p in fitted:
        if _imports(p) & CORE_NAMES or READS.search(p.read_text(encoding="utf-8", errors="replace")):
            bad.append(p.name)
    assert bad == []


def test_no_betting_module_reads_a_baserunning_file_or_an_ebr_key():
    bad = [p.name for p in _modules() if p.name.startswith("betting_")
           and BETTING_READS.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert bad == []


# The section build (EBR_2_BUILD_DARK): the board, the history file, the eval
# and the card block are display only. No betting module, no vintage snapshot
# and no fitted consumer reads them, and the betting vintage's team columns
# carry no eBR (nothing was added to leaderboard_vintages.TEAM_COLUMNS).
BOARD_READS = re.compile(r"(baserunning_leaderboards|baserunning_history|baserunning_export|"
                         r"skills\W+br\b|\[\s*(?:\x22br\x22|\x27br\x27)\s*\]|team_ebr|ebr_sb|ebr_xb|ebr_dp)")


def test_no_betting_or_vintage_or_fitted_code_reads_the_board_or_the_card_block():
    bad = []
    for p in _modules():
        if not (_fitted(p) or p.name.startswith("betting_")):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if BOARD_READS.search(src) or (p.name.startswith("betting_") and BETTING_READS.search(src)):
            bad.append(p.name)
    assert bad == []
    import leaderboard_vintages
    cols = " ".join(str(c) for c in leaderboard_vintages.TEAM_COLUMNS)
    assert "ebr" not in cols and "baserunning" not in cols, cols


def test_the_card_exporter_is_the_only_consumer_of_the_board_outside_the_section():
    """Who reads baserunning_leaderboards.json: the exporter that writes it,
    run_monthly's wiring, build_site's shell, the card exporter (behind
    CARD_BASERUNNING_LIVE) and the page scripts. Anything else is a new
    reader this pin makes visible."""
    readers = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in _modules()
                     if not p.name.startswith("test_")
                     and re.search(r"baserunning_leaderboards|_bre\.OUT_NAME|bre\.OUT_NAME",
                                   p.read_text(encoding="utf-8", errors="replace")))
    allowed = {"baserunning_export.py", "mlb_player_export.py", "run_monthly.py", "build_site.py",
               "data_catalog.py", "league_averages.py"}
    assert set(readers) <= allowed, sorted(set(readers) - allowed)


def test_the_builders_own_scan_agrees_and_catches_a_planted_offender(tmp_path):
    assert build_ebr.isolation_scan(ROOT)["pass"] is True
    (tmp_path / "tools").mkdir()
    (tmp_path / "efv_planted.py").write_text("import ebr\n", encoding="utf-8")
    (tmp_path / "tools" / "proj_planted.py").write_text("P = '.cache/ebr/preview/ebr.json'\n", encoding="utf-8")
    (tmp_path / "betting_planted.py").write_text("x = row['ebr']\n", encoding="utf-8")
    (tmp_path / "harmless.py").write_text("import ebr\n", encoding="utf-8")
    scan = build_ebr.isolation_scan(tmp_path)
    assert scan["pass"] is False
    assert sorted(scan["offenders"]) == ["betting_planted.py", "efv_planted.py", "proj_planted.py"]


def test_only_the_builder_and_the_look_import_the_core():
    users = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in _modules()
                   if _imports(p) & CORE_NAMES and not p.name.startswith("test_"))
    # tools/build_count_value.py reuses ebr's RE24 recipe for RE288
    # (docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md part 3): a measurement, not a
    # fitted consumer under I9, and scanned below for year-to-year statistics.
    # tools/pitch_basis_build.py reuses ebr.fit_mask for the runner-scoring table
    # of eWAR's pitching bases (EBR_GATE.md part 11.3.3), on the same terms.
    # tools/build_pitch_ledger.py reuses ebr.base_code and ebr.fit_mask for the pitch
    # ledger's walk and its telescope check (docs/ewar/PITCH_LEDGER_GATE.md parts 2 and
    # 7), a same-season measurement on the same terms.
    assert users == ["tools/build_count_value.py", "tools/build_ebr.py", "tools/build_pitch_ledger.py",
                     "tools/ebr_gate.py", "tools/pitch_basis_build.py"]


def test_only_the_look_computes_a_year_to_year_statistic():
    forbidden = ("PAIRS", "persistence", "% 2", "split_half", "Spearman-Brown", "y + 1", "s + 1",
                 "season + 1")
    for p in (ROOT / "ebr.py", ROOT / "tools" / "build_ebr.py", ROOT / "count_value.py",
              ROOT / "tools" / "build_count_value.py", ROOT / "pitch_basis.py",
              ROOT / "tools" / "pitch_basis_build.py"):
        src = p.read_text(encoding="utf-8")
        assert not [t for t in forbidden if t in src], p.name
    gate = (ROOT / "tools" / "ebr_gate.py").read_text(encoding="utf-8")
    assert "def persistence_d(" in gate and "def reliability(" in gate


def _digest() -> dict:
    out = {}
    corpus = ROOT / ".cache" / "pbp_corpus"
    if corpus.exists():
        for p in sorted(corpus.rglob("*")):
            if p.is_file():
                out[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    for p in GUARDED:
        out[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    import war_source
    out["war_source.PROVIDERS"] = list(war_source.PROVIDERS)
    return out


def _load_fixtures():
    import importlib.util
    if "ebr_fixtures" in sys.modules:
        return sys.modules["ebr_fixtures"]
    spec = importlib.util.spec_from_file_location(
        "ebr_fixtures", ROOT / "test_fixtures" / "ebr" / "ebr_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ebr_fixtures"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_a_build_leaves_the_guarded_files_byte_identical(tmp_path, monkeypatch):
    fx = _load_fixtures()
    monkeypatch.setattr(ebr, "FROZEN_K", None)
    monkeypatch.setattr(ebr, "FROZEN_POOL_SHA256", None)
    monkeypatch.setattr(ebr, "POOL_SEASONS", (2023, 2024))
    before = _digest()
    data = {s: fx.season_frames(s) for s in (2023, 2024)}
    raw = {s: ebr.season_raw(pa) for s, (pa, _) in data.items()}
    opps = {}
    for s, (pa, rn) in data.items():
        o = ebr.xb_opportunities(pa, rn)
        ebr.finalize_opportunities(o)
        opps[s] = o
    sub, ev = build_ebr.build(record_data=(data, {}), out_dir=tmp_path / "preview",
                              frozen_dir=tmp_path / "frozen", today=date(2026, 11, 2),
                              comparators=False, arm_blob={},
                              pool_doc=ebr.frozen_pool_document(raw, opps))
    build_ebr.write(sub, ev, tmp_path / "preview")
    assert sorted(p.name for p in (tmp_path / "preview").iterdir()) == ["ebr.json", "ebr_eval.json"]
    assert _digest() == before


@pytest.mark.skipif(not (ROOT / ".cache" / "ebr" / "preview" / "ebr_eval.json").exists(),
                    reason="no preview build on this machine")
def test_the_preview_eval_carries_no_per_player_comparator_value():
    ev = json.loads((ROOT / ".cache" / "ebr" / "preview" / "ebr_eval.json").read_text(encoding="utf-8"))
    assert ev["isolation_I9"]["pass"] is True
    text = json.dumps(ev)
    assert '"mlbam"' not in text and '"by_mlbam"' not in text and '"players": {' not in text
