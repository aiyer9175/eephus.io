# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Copy gates, enforced by the suite (audit F-04).

The two owner-mandated copy tools existed but nothing ran them, so a copy
regression (an em-dash, an LLM-cadence word in pure copy) could land silently:

  - tools/strip_emdashes.py --check: no em- or en-dashes anywhere in the
    canonical copy-surface list (its TARGETS: generators, app HTML, JS, CSS,
    articles, and the hand-committed data files the frontend renders).
  - tools/copy_lint.py --check: same em-dash rule plus the LLM ban-list,
    hard-failing only in pure-copy files (glossary.json, README, content/*)
    so code identifiers don't false-positive.

Both are shelled out through their real CLI contract (exit 0 = clean), the
same invocation a pipeline or pre-commit hook would use, so the gate tests
the tool as shipped rather than importing internals. Read-only: --check
never rewrites files, so this test dirties nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def _run_gate(script: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # findings may be non-cp1252
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), "--check"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=120,
    )


def test_strip_emdashes_check_is_clean():
    r = _run_gate("strip_emdashes.py")
    assert r.returncode == 0, (
        "strip_emdashes --check found em/en-dashes in copy surfaces:\n"
        f"{r.stdout}\n{r.stderr}"
    )


def test_copy_lint_check_is_clean():
    r = _run_gate("copy_lint.py")
    assert r.returncode == 0, (
        "copy_lint --check failed (em-dashes or LLM terms in pure copy):\n"
        f"{r.stdout}\n{r.stderr}"
    )


def test_the_emdash_gate_covers_every_user_facing_page():
    """PLAN ITEM F2.6, closed 2026-08-06. Ten pages users load had never been
    scanned by the gate, every Diamond-era surface among them: betting, cards,
    dfs, diamond, dynasty, redraft, plus fantasy, history, parks and player.

    All ten measured clean when they were added, so nothing shipped wrong. The
    defect was the coverage, not the copy: a page nobody scans is one bad paste
    away from breaking a rule the owner treats as absolute, and it would break
    it silently because no gate was looking.

    This test fails when a NEW page appears without being added, which is the
    only way the gap recurs."""
    import fnmatch
    import re
    from pathlib import Path

    root = Path(__file__).parent
    src = (root / "tools" / "strip_emdashes.py").read_text(encoding="utf-8")
    block = src[src.index("TARGETS"):src.index("def ")]
    targets = set(re.findall(r'"([^"]+)"', block))

    pages = sorted(p.relative_to(root).as_posix()
                   for p in root.glob("*/index.html"))
    assert pages, "no section pages found; has the layout changed?"

    uncovered = [p for p in pages
                 if not any(fnmatch.fnmatch(p, t) for t in targets)]
    assert not uncovered, (
        "user-facing pages the em-dash gate does not scan: "
        f"{uncovered}\nAdd them to TARGETS in tools/strip_emdashes.py. If one "
        "genuinely must be excluded, say why there, the way the exporter "
        "exclusions are documented.")
