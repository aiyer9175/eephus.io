"""RATCHET: every remapper construction must carry the as-of cutoff.

The C-4 flip's whole documented hazard is a PARTIAL flip. consensus.py's checklist
names five other places that build the remapper directly and warns that leaving any
of them uncapped puts the served board and its own validation on two different
normalizations, which is worse than either basis alone.

That checklist was a COMMENT, and a comment does not fail a build. It was also
wrong twice in one day: it missed a second pooling re-implementation in
consensus_gate_lab, and it went stale within hours when the pre-2017 exemption was
removed. This file is the executable version.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import consensus
import grade_normalization as gn

ROOT = Path(__file__).parent

#: Files allowed to build an UNCAPPED remapper, each with the reason. Tests are
#: exempt because several exist precisely to compare capped against uncapped.
_EXEMPT = {
    "test_grade_norm_asof.py":          "the as-of contract suite compares both bases",
    "test_grade_norm_era_floor.py":     "same, for the era floor",
    "test_grade_normalization.py":      "asserts flip-independent properties",
    "test_ba_era_basis.py":             "BA era separation, asserted on the raw scale",
    "test_grade_norm_flip_coverage.py": "this file",
}


def _call_sites():
    """(path, lineno, kwarg names) for every real build_remapper CALL in the tree.

    Parsed with ast rather than grepped, and that is not fastidiousness. The regex
    version of this test flagged four sites on its first run and ALL FOUR were false
    positives: docstrings containing "build_remapper (" with a space, and the
    definition of gate_lab's separate build_remapper_asof. A ratchet that cries wolf
    gets disabled, so it reads the syntax tree, where a docstring is a string and a
    call is a call.
    """
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        if ".cache" in p.parts or ".claude" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (fn.attr if isinstance(fn, ast.Attribute)
                    else fn.id if isinstance(fn, ast.Name) else None)
            if name != "build_remapper":        # NOT build_remapper_asof
                continue
            out.append((p, node.lineno, {k.arg for k in node.keywords}))
    return out


def test_every_remapper_construction_carries_the_cutoff():
    """The ratchet. A new uncapped construction fails here rather than silently
    serving a second normalization basis."""
    bad = []
    for path, lineno, kwargs in _call_sites():
        if path.name in _EXEMPT:
            continue
        if "as_of_year" not in kwargs:
            bad.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert not bad, (
        "these build the grade-normalization remapper WITHOUT an as_of cutoff, so "
        "they would serve a different normalization basis than the board:\n  "
        + "\n  ".join(bad)
        + "\nPass as_of_year=consensus.grade_norm_cutoff(), or add the file to "
          "_EXEMPT with a written reason.")


def test_the_ratchet_is_not_vacuous():
    """It must actually SEE the production call sites. A coverage test that scans
    zero files passes forever."""
    seen = {p.name for p, _l, _k in _call_sites()}
    assert "consensus.py" in seen, "the served construction is not being scanned"
    assert "surplus_backtest_real.py" in seen, "the binding site is not being scanned"
    assert len(seen) >= 5, f"only {len(seen)} files scanned; the walk is too narrow"


def test_the_cutoff_helper_is_the_single_point_of_truth():
    """The derivation must live in ONE place. Five copies of `max(snapshot year)`
    behind five copies of an `if` is exactly how a partial flip happens."""
    hits = []
    for p in sorted(ROOT.rglob("*.py")):
        if ".cache" in p.parts or ".claude" in p.parts or p.name.startswith("test_"):
            continue
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue
        # an ast walk sees CODE, so the many COMMENTS naming the flag do not count
        reads = any(
            (isinstance(n, ast.Attribute) and n.attr == "GRADE_NORM_AS_OF")
            or (isinstance(n, ast.Name) and n.id == "GRADE_NORM_AS_OF")
            for n in ast.walk(tree))
        if reads and "grade_norm_cutoff" not in src:
            hits.append(p.name)
    # storage.py is allowed: its fingerprint term reports the flag STATE, which is
    # the one legitimate reason to read the flag rather than the cutoff.
    extra = sorted(set(hits) - {"consensus.py", "storage.py"})
    assert not extra, (
        f"{extra} read the GRADE_NORM_AS_OF flag directly instead of calling "
        "consensus.grade_norm_cutoff(); the derivation must not be duplicated")


def test_the_cutoff_comes_from_data_not_the_clock():
    """A cutoff taken from date.today() would silently re-base every grade at
    midnight on New Year's Eve, and a rebuild of a fixed corpus would not be
    reproducible."""
    import inspect
    src = inspect.getsource(consensus.grade_norm_cutoff)
    for banned in ("date.today", "datetime.now", "utcnow"):
        assert banned not in src, f"grade_norm_cutoff reads the clock via {banned}"
    assert "snapshot_date" in src


def test_the_flip_is_on_and_reaches_the_era_floor():
    """Both halves. The flag alone is not the ship: before the reachability fix it
    was possible for the flag to be True while the era floor never fired, which is
    the false green C4_REACHABILITY_DEFECT.md records."""
    assert consensus.GRADE_NORM_AS_OF is True
    assert consensus.grade_norm_cutoff([]) is None          # empty pool degrades
    yr = gn._REFERENCE_FIRST_YEAR - 4
    capped, _r, _p = gn._paired_dists("mlb_pipeline", "hitter", yr,
                                      gn._REFERENCE_FIRST_YEAR)
    uncapped, _r2, _p2 = gn._paired_dists("mlb_pipeline", "hitter", yr, None)
    if not (len(capped) and len(uncapped)):
        pytest.skip("corpus has no pre-reference mlb_pipeline pairs")
    assert len(capped) < len(uncapped), (
        "the pre-reference cell pools the same set capped as uncapped, so the era "
        "floor is not firing and the flip is a silent no-op")
