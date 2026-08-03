# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression guard against undefined-name (NameError) drift in production code.

WHY THIS EXISTS (2026-08-03). `efv_score.run_backgrade` shipped a one-line
NameError for two days: `_relabel_pace_factor(factors, r.get("milb"))` where the
loop variables are `rec`/`row` and `r` was bound only inside a comprehension
(whose scope does not leak in Python 3). It raised on every row carrying a milb
block, killing the eFV regen tail - backgrade, history, tools and the valuation
curve all froze - and `run_monthly.rebuild_only` swallowed the crash in a
best-effort try/except, so `data/xfv.json` silently served stale while the
nightly logged success. Nothing in the suite exercised that seam.

A single synthetic-row test for that one function would not have caught it
(the seam needs a fitted ridge, a matrix and DB state). A static undefined-name
sweep does, in under a second, for the WHOLE production surface - and it caught
two further real defects the same day:

  * `build_site.py` called `log.exception(...)` inside the only handler
    protecting the Rng+ block, but `log` was never defined in that module: the
    error handler itself raised NameError and destroyed the graceful
    degradation it existed to provide.
  * `storage.py` annotated `upsert_pitch_arsenals` / `upsert_sabermetrics` with
    string forward-refs to `PitchArsenal` / `Sabermetrics` that were never
    imported (harmless at runtime - string annotations are not evaluated - but
    a lie to every reader and type checker).

Scope: production modules only. `tools/` is the experimental lab record and
`test_*.py` may deliberately reference removed functions inside skipped tests
(see `test_metrics_audit.py`'s `_compute_breakout_score` block, which documents
a 2026-05 removal on purpose).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent

# Paths that are NOT production code. Passed as ONE comma-joined --exclude:
# ruff honors only the last --exclude flag, so splitting these across two flags
# silently drops the first set (which is how the first draft of this guard let
# the deliberately-skipped test_metrics_audit references through).
EXCLUDES = ("tools", "vendor", ".cache", "scripts", "model", "test_*.py")


def _ruff_available() -> bool:
    try:
        subprocess.run([sys.executable, "-m", "ruff", "--version"],
                       capture_output=True, check=True, timeout=60)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _ruff_available(),
                    reason="ruff not installed in this environment")
def test_no_undefined_names_in_production_modules():
    """F821 (undefined name) must be zero across production modules.

    Test files are excluded: they may reference deliberately-removed functions
    inside `@pytest.mark.skip` blocks as documentation.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "F821",
         "--exclude", ",".join(EXCLUDES),
         "--output-format", "concise", "."],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    findings = [ln for ln in proc.stdout.splitlines() if ": F821" in ln]
    assert not findings, (
        "Undefined name(s) in production code - these raise NameError at "
        "runtime and pipeline steps wrapped in best-effort try/except will "
        "swallow them silently:\n  " + "\n  ".join(findings))


@pytest.mark.skipif(not _ruff_available(),
                    reason="ruff not installed in this environment")
def test_efv_score_backgrade_seam_is_name_clean():
    """Pin the specific regression: efv_score.py must have no undefined names.

    `run_backgrade` is not covered by any functional test (it needs a fitted
    ridge + matrix + DB), and it is wrapped in a best-effort handler upstream,
    so a NameError there is invisible until an artifact goes stale.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "F821",
         "--output-format", "concise", "efv_score.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    findings = [ln for ln in proc.stdout.splitlines() if ": F821" in ln]
    assert not findings, "efv_score.py has undefined names:\n  " + "\n  ".join(findings)


def test_relabel_pace_factor_call_sites_use_a_bound_row():
    """Belt-and-braces for the exact 2026-07-31 defect, independent of ruff.

    Both `_relabel_pace_factor` call sites must pass a row variable that the
    enclosing loop actually binds. `run_live` loops `for r in live:` (so `r` is
    correct there); `run_backgrade` loops `for rec in ...` and builds `row`, so
    it must pass `row`. Asserting on source text keeps the guard alive even
    where ruff is unavailable.
    """
    src = (ROOT / "efv_score.py").read_text(encoding="utf-8").splitlines()
    sites = [(i + 1, ln) for i, ln in enumerate(src) if "_relabel_pace_factor(" in ln
             and not ln.lstrip().startswith("def ")]
    assert sites, "expected _relabel_pace_factor call sites in efv_score.py"
    for lineno, line in sites:
        # Walk back to the nearest enclosing `for <var> in` at a shallower indent.
        indent = len(line) - len(line.lstrip())
        loop_var = None
        for j in range(lineno - 2, -1, -1):
            prev = src[j]
            if not prev.strip():
                continue
            p_indent = len(prev) - len(prev.lstrip())
            if p_indent < indent and prev.lstrip().startswith("for "):
                loop_var = prev.lstrip().split()[1].rstrip(",")
                break
            if p_indent == 0 and prev.lstrip().startswith("def "):
                break
        arg = line.split("_relabel_pace_factor(")[1]
        passed = arg.split(",")[1].strip().split(".")[0] if "," in arg else ""
        assert passed, f"line {lineno}: could not parse the row argument"
        # The argument must be either the loop variable itself or a dict the
        # function body builds (`row`); never an unbound single-letter alias.
        assert passed in {loop_var, "row"}, (
            f"efv_score.py:{lineno} passes `{passed}` to _relabel_pace_factor but "
            f"the enclosing loop binds `{loop_var}` - this is the 2026-07-31 "
            f"NameError shape (comprehension scopes do not leak in Python 3).")
