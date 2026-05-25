"""Asserts the legacy breakout indicator has been removed.

The old `breakout_score` composite was replaced by the WAG-anchored
BOOM/BUST graduate labels. This test guards against accidental
reintroduction (e.g., a stash-applied PR resurrecting the breakout
field on the export payload)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent


def test_no_active_breakout_score_call_in_storage():
    """`_compute_breakout_score` must not be CALLED anywhere in storage.py.
    The DELETED_ stub or a REMOVED comment is fine; an active call is not."""
    src = (REPO / "storage.py").read_text(encoding="utf-8")
    # Allow the REMOVED-comment mention; flag any non-comment call.
    lines = src.splitlines()
    offenders = []
    for i, ln in enumerate(lines, start=1):
        if "_compute_breakout_score(" in ln and not ln.lstrip().startswith("#"):
            offenders.append(f"line {i}: {ln.strip()[:80]}")
    assert not offenders, "_compute_breakout_score is still called: " + "; ".join(offenders)


def test_no_breakout_score_field_in_export():
    """The export payload must not stamp a `breakout_score` field."""
    src = (REPO / "storage.py").read_text(encoding="utf-8")
    bad = re.findall(r'"breakout_score"\s*:\s*[a-zA-Z_]', src)
    assert not bad, f"breakout_score export field still present: {bad}"


def test_no_breakout_pill_function_active():
    """The JS `breakoutPillHTML` function must not be active in index.html.
    Tolerates a REMOVED- or DELETED- prefixed stub comment."""
    src = (REPO / "index.html").read_text(encoding="utf-8")
    # Active function definition: `function breakoutPillHTML(` (not inside a comment).
    matches = re.findall(r"^\s*function\s+breakoutPillHTML\s*\(", src, re.MULTILINE)
    assert not matches, "breakoutPillHTML still defined (active) in index.html"


def test_no_boom_bust_pill_function_active():
    """boomBustPillHTML was the replacement for breakoutPillHTML but was
    itself retired in v19 (graduates page now surfaces over/underperformers
    via WAG-high / WAG-low sort dimensions instead of a chip). Guard
    against accidental reintroduction."""
    src = (REPO / "index.html").read_text(encoding="utf-8")
    matches = re.findall(r"^\s*function\s+boomBustPillHTML\s*\(", src, re.MULTILINE)
    assert not matches, "boomBustPillHTML still defined (active) in index.html"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
