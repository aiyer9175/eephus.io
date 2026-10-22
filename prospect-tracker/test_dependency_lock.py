# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every third-party import is declared, and every declared name is pinned.

X04-04 (2026-09-24): requirements.txt held ten floors while numpy (about 150
files), pandas, scipy, joblib, statsmodels, pyarrow, urllib3 and playwright were
imported and never declared, so the box resolved them from whatever the floors
dragged in. No file recorded which versions wrote a served number.

These tests read files only. They never compare the lock to the running
interpreter, because the box and CI run Python 3.12 and would fail that by
design; `python tools/freeze_constraints.py --check` asks that question on the
machine that owns the lock.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import freeze_constraints as fc  # noqa: E402

# Import name -> distribution name, where they differ.
DIST_OF = {
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "PIL": "pillow",
    "py_mini_racer": "py-mini-racer",
}
# Names imported under a try or from files that no longer exist; not packages.
NOT_PACKAGES = {"fa_config", "draft_anchor_backfill"}


def _local_names() -> set[str]:
    names = {p.stem for p in ROOT.glob("*.py")}
    names |= {p.stem for p in (ROOT / "tools").glob("*.py")}
    names |= {p.name for p in ROOT.iterdir() if p.is_dir()}
    return names


def third_party_imports() -> dict[str, list[str]]:
    std = set(sys.stdlib_module_names)
    local = _local_names()
    found: dict[str, list[str]] = {}
    files = list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py"))
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                mods = [n.module.split(".")[0]]
            for m in mods:
                # __main__ is the running script (efv_side_role_calibration.py and
                # efv_x3_pooled.py import it), never a package; it is not in
                # sys.stdlib_module_names, so name it here.
                if m in std or m in local or m in NOT_PACKAGES or m in ("__future__", "__main__"):
                    continue
                found.setdefault(m, []).append(f.name)
    return found


def _pinned() -> dict[str, str]:
    text = (ROOT / "constraints-local.txt").read_text(encoding="utf-8")
    out = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            name, _, ver = ln.partition("==")
            out[fc.canon(name)] = ver
    return out


def test_every_third_party_import_is_declared():
    declared = {fc.canon(n) for n in fc.declared_names(ROOT)}
    undeclared = sorted(
        f"{m} ({len(set(fs))} files)" for m, fs in third_party_imports().items()
        if fc.canon(DIST_OF.get(m, m)) not in declared)
    assert not undeclared, "imported but not in requirements*.txt: " + ", ".join(undeclared)


def test_every_declared_name_is_pinned_exactly():
    pinned = _pinned()
    unpinned = sorted(n for n in fc.declared_names(ROOT) if fc.canon(n) not in pinned)
    assert not unpinned, "declared but not pinned in constraints-local.txt: " + ", ".join(unpinned)
    for c, ver in pinned.items():
        assert re.fullmatch(r"[0-9][0-9A-Za-z.+!-]*", ver), f"{c} has no exact version: {ver!r}"


def test_the_lock_names_the_interpreter_it_was_measured_on():
    head = (ROOT / "constraints-local.txt").read_text(encoding="utf-8")[:600]
    assert re.search(r"Python 3\.[0-9]+\.[0-9]+ on ", head), head
    assert "tools/freeze_constraints.py" in head
