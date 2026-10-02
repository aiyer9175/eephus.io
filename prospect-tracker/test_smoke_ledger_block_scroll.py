"""Smoke audit 2026-10-01, Club Ledger block scroll (SCL02, SCL03).

SCL02: the options calendar's club link on League scrolled to the block, then
the data-llink handler called window.scrollTo(0, 0) after render() and undid
it. SCL03: a deep link scrolled on the preview render and marked the block
done, so the render after the club's rows arrived (rows above the block)
never scrolled again. One assertion per finding, read off assets/ledger.js.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "ledger.js").read_text(encoding="utf-8")


def _body(start: str, end: str) -> str:
    i = JS.index(start)
    return JS[i:JS.index(end, i)]


def test_scl02_llink_handler_does_not_scroll_to_top_after_render():
    h = _body('querySelectorAll("a[data-llink]")', "function boot()")
    calls = [m.start() for m in re.finditer(r"\brender\(\)", h)]
    tops = [m.start() for m in re.finditer(r"scrollTo\(0, 0\)", h)]
    assert calls and all(t < calls[0] for t in tops), "scrollTo(0, 0) runs after render() in the data-llink handler"


def test_scl03_block_marked_scrolled_only_once_the_shard_settles():
    r = _body("function render() {", "function wire()")
    sets = re.findall(r"^.*\bSCROLLED = state\.team.*$", r, re.M)
    assert len(sets) == 1 and 'SHARD_STATE[state.team] === "ready"' in sets[0] and 'SHARD_STATE[state.team] === "failed"' in sets[0], sets
