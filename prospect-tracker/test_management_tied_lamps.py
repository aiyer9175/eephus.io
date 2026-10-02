# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PX-14 (final-pass plan 5.7, V1): the tied-game line score on /management/.

The "Coming to bat in a tied game" block draws its 18 measured cells as
ballpark lamps above the table, which stays. Pins, on the SERVED payload rows:

  - each half lights round(100 x (p - 0.5)) lamp rows (JS Math.round), up
    from the 50% rule when p > 0.5 and down when p < 0.5, 4 px per row;
  - the table under it is byte-identical to the page without the lamps;
  - the renderer stays inside its 3 KB budget and draws no red or green;
  - the chart is role="img" with a label that points at the table.

Skips when py_mini_racer is unavailable (as test_management_render.py does).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

pytest.importorskip("py_mini_racer")

import test_management_render as R  # noqa: E402

ROOT = Path(__file__).parent
JS_PATH = ROOT / "assets" / "management.js"
BOARD = ROOT / "data" / "management_board.json"


def _served_rows() -> list[dict]:
    d = json.loads(BOARD.read_text(encoding="utf-8"))
    return d["reference"]["half_inning_start"]["tied_game"]


def _payload() -> dict:
    d = json.loads(json.dumps(R.SAMPLE))
    d["reference"]["half_inning_start"] = {"note": "measured.", "tied_game": _served_rows()}
    return d


def _js_round(x: float) -> int:
    return math.floor(x + 0.5)


def _lamp_block(html: str) -> str:
    m = re.search(r'<div class="px-lamp-wrap.*?</p>', html, re.S)
    assert m, "no lamp block drawn"
    return m.group(0)


def test_each_half_lights_round_100_p_minus_half_lamp_rows():
    rows = _served_rows()
    assert len(rows) == 18
    html = R._render("reference", _payload())
    block = _lamp_block(html)
    got = {h: int(n) for h, n in re.findall(r'data-half="(\d+(?:top|bottom))" data-lamps="(-?\d+)"', block)}
    want = {f"{r['inning']}{r['half']}": _js_round(r["batting_team_win_prob"] * 100 - 50) for r in rows}
    assert got == want
    # Served shape as of 2026-10-02: every top half sits at or under 50%, every
    # bottom half above it, the bottom of the 9th the tallest bar.
    assert want["9bottom"] == max(want.values()) == 13
    assert want["1top"] == min(want.values()) == -3


def test_bar_heights_are_four_px_per_lamp_row_and_sit_on_the_rule():
    block = _lamp_block(R._render("reference", _payload()))
    up = max(1, max(_js_round(r["batting_team_win_prob"] * 100 - 50) for r in _served_rows()))
    for half, n, inner in re.findall(r'<g data-half="(\w+)" data-lamps="(-?\d+)">(.*?)</g>', block):
        n = int(n)
        if n == 0:
            assert inner == "", half
            continue
        y, h = map(int, re.search(r'y="(\d+)" width="16" height="(\d+)"', inner).groups())
        assert h == abs(n) * 4, half
        assert (y + h == up * 4) if n > 0 else (y == (up + 1) * 4), half


def test_the_table_under_it_is_unchanged():
    with_lamps = R._render("reference", _payload())
    js = R.JS
    stub = js.replace("  function tiedLamps(rows) {\r\n", '  function tiedLamps(rows) { return "";\r\n', 1)
    if stub == js:
        stub = js.replace("  function tiedLamps(rows) {\n", '  function tiedLamps(rows) { return "";\n', 1)
    assert stub != js, "tiedLamps moved"
    orig = R.JS
    try:
        R.JS = stub
        without = R._render("reference", _payload())
    finally:
        R.JS = orig
    assert with_lamps.replace(_lamp_block(with_lamps), "") == without
    assert "<th>Inning</th><th>Half</th><th>Win probability</th><th>Games</th>" in without
    assert without.count("<tr><td>") >= 18


def test_renderer_budget_and_palette():
    src = JS_PATH.read_text(encoding="utf-8")
    body = src[src.index("function tiedLamps"):src.index("// ---- PX-14 end")]
    assert len(body.encode("utf-8")) <= 3072, len(body.encode("utf-8"))
    block = _lamp_block(R._render("reference", _payload()))
    assert "accent-red" not in block and "accent-green" not in block
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block.replace("url(#mgmt-lp-", ""))
    assert 'role="img"' in block and "every value is in the table below" in block


def test_no_rows_draws_nothing():
    d = _payload()
    d["reference"]["half_inning_start"]["tied_game"] = []
    assert "px-lamp" not in R._render("reference", d)
