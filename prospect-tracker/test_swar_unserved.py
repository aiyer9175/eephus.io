# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 skill modules are UNSERVED (orchestrator ruling X15 of the former
skill plan, carried into docs/ebr-2026-09-30/EBR_GATE.md part 9.4): a source and
write test, never a sys.modules import test, which the replica's own import of
fg_leaderboards would fail by construction.

  1. No served exporter imports the skill modules: every module named in
     run_monthly.SCHEDULED_EXPORTS (and every *_export.py beside them),
     war_board_export.py, mlb_player_export.py, build_site.py and every
     assets/*.js is parsed for an import of, or a path into, swar, build_swar,
     swar_lab, .cache/swar/ or docs/ebr-2026-09-30/swar_eval.json, and none
     is found.
  2. The skill modules write no served file: build_swar runs on fixtures with
     open() and Path.write_* monkeypatched to record every write path, and
     each lies under .cache/swar/ or the test's tmp_path, never under data/ or
     a path deploy/publish_paths.txt lists.
  3. war_source.PROVIDERS lacks 'ewar_v3' (EBR_3_EWAR_V3 adds it, behind
     EWAR_V3_LIVE, with the pin updated in the same commit).
"""
from __future__ import annotations

import ast
import builtins
import io
import re
import sys
from pathlib import Path

import pytest

import run_monthly
import war_source

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_swar as B  # noqa: E402
from test_swar import SEASON, FixtureInputs  # noqa: E402

SKILL_MODULES = ("swar", "build_swar", "swar_lab")
#: `swar` bounded by non-letters, so Swartz and swartz_pool (the arbitration
#: module's namesake) never match while swar.json, build_swar, swar_lab and
#: .cache/swar/ do.
PATH_PATTERN = re.compile(r"(?<![A-Za-z])swar(?![A-Za-z])")
SERVED_EXTRA = ("war_board_export.py", "mlb_player_export.py", "build_site.py", "run_monthly.py")


def _served_python_files() -> list[Path]:
    names: set[str] = set()
    for entry in run_monthly.SCHEDULED_EXPORTS:
        entry = str(entry)
        names.add(f"{entry}.py")
        stem = entry.split("_")[0]
        names.add(f"{stem}_export.py")
        names.add(f"{entry}_export.py")
    files = {ROOT / n for n in names if (ROOT / n).exists()}
    files.update(ROOT.glob("*_export.py"))
    files.update(ROOT / n for n in SERVED_EXTRA)
    return sorted(p for p in files if p.exists())


def _python_imports(src: str, path: Path) -> set[str]:
    tree = ast.parse(src, filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_no_served_exporter_imports_or_names_a_path_into_the_skill_modules():
    files = _served_python_files()
    assert len(files) >= 20, [p.name for p in files]
    assert ROOT / "war_board_export.py" in files and ROOT / "build_site.py" in files
    offenders = []
    for path in files:
        src = path.read_text(encoding="utf-8")
        hits = _python_imports(src, path) & set(SKILL_MODULES)
        if hits:
            offenders.append((path.name, "import", sorted(hits)))
        for m in PATH_PATTERN.finditer(src):
            line = src[src.rfind("\n", 0, m.start()) + 1: src.find("\n", m.end())]
            offenders.append((path.name, "path", line.strip()))
        if "swar_eval.json" in src or ".cache/swar" in src:
            offenders.append((path.name, "artifact", "swar_eval.json or .cache/swar"))
    assert offenders == []


def test_no_served_asset_names_a_path_into_the_skill_modules():
    assets = sorted((ROOT / "assets").glob("*.js"))
    assert len(assets) >= 10
    offenders = []
    for path in assets:
        src = path.read_text(encoding="utf-8", errors="replace")
        for m in PATH_PATTERN.finditer(src):
            line = src[src.rfind("\n", 0, m.start()) + 1: src.find("\n", m.end())]
            offenders.append((path.name, line.strip()[:120]))
        if "swar_eval.json" in src or ".cache/swar" in src:
            offenders.append((path.name, "artifact"))
    assert offenders == []


def _publish_paths() -> list[str]:
    out = []
    for line in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.rstrip("/"))
    return out


def test_the_skill_build_writes_only_under_cache_swar_or_tmp_path(tmp_path, monkeypatch):
    writes: list[Path] = []
    real_open, real_io_open = builtins.open, io.open
    real_write_text, real_write_bytes, real_path_open = Path.write_text, Path.write_bytes, Path.open

    def _is_write(mode) -> bool:
        return any(ch in str(mode) for ch in "wax+")

    def rec_open(file, mode="r", *a, **kw):
        if _is_write(mode) and not isinstance(file, int):
            writes.append(Path(file))
        return real_open(file, mode, *a, **kw)

    def rec_io_open(file, mode="r", *a, **kw):
        if _is_write(mode) and not isinstance(file, int):
            writes.append(Path(file))
        return real_io_open(file, mode, *a, **kw)

    def rec_write_text(self, *a, **kw):
        writes.append(Path(self))
        return real_write_text(self, *a, **kw)

    def rec_write_bytes(self, *a, **kw):
        writes.append(Path(self))
        return real_write_bytes(self, *a, **kw)

    def rec_path_open(self, mode="r", *a, **kw):
        if _is_write(mode):
            writes.append(Path(self))
        return real_path_open(self, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", rec_open)
    monkeypatch.setattr(io, "open", rec_io_open)
    monkeypatch.setattr(Path, "write_text", rec_write_text)
    monkeypatch.setattr(Path, "write_bytes", rec_write_bytes)
    monkeypatch.setattr(Path, "open", rec_path_open)

    out = tmp_path / "preview" / "swar.json"
    B.build([SEASON], inp=FixtureInputs(), out_path=out, log=lambda *a: None)
    assert out.exists()
    assert writes, "the build wrote nothing, so the recorder saw nothing"

    cache_swar = (ROOT / ".cache" / "swar").resolve()
    tmp = tmp_path.resolve()
    data_dir, docs_dir = (ROOT / "data").resolve(), (ROOT / "docs").resolve()
    published = [(ROOT / p).resolve() for p in _publish_paths()]

    def _under(p: Path, parent: Path) -> bool:
        try:
            p.relative_to(parent)
            return True
        except ValueError:
            return False

    for w in writes:
        wr = w.resolve()
        assert _under(wr, cache_swar) or _under(wr, tmp), f"write outside .cache/swar/ or tmp_path: {w}"
        assert not _under(wr, data_dir) and not _under(wr, docs_dir), w
        assert not any(_under(wr, p) or wr == p for p in published), w


def test_the_builder_default_output_sits_under_cache_swar_preview():
    assert B.OUT_PATH == ROOT / ".cache" / "swar" / "preview" / "swar.json"
    assert B.OUT_PATH.resolve() != (ROOT / "data" / "swar.json").resolve()
    # the CLI refuses an --out outside .cache/swar/ before any work
    assert B.main(["--out", str(ROOT / "data" / "swar.json"), "--seasons", str(SEASON)]) == 2


def test_war_source_providers_lack_ewar_v3_before_the_flip():
    assert "ewar_v3" not in war_source.PROVIDERS
    assert "swar" not in war_source.PROVIDERS and "swar_v1" not in war_source.PROVIDERS
    assert war_source.DISPLAY_PROVIDER == "ewar_v2"
