"""Smoke audit 2026-10-01, Franchise ODDS tiles (SCL01, SCL05).

SCL01: the Pennant tile's postseason_bracket_sim verdict chip took
white-space: nowrap from .eephus-beta, so at 390 px it ran 57 px past its
162 px tile and covered 49 x 19 px of the Pythag vs actual tile. SCL05: once
the regular season is over the outlook overlay carries no strength of
schedule and no rank, and the tile printed an empty value over a bare
'rank  · IL out 60+' line. One assertion per finding.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
CSS = (ROOT / "assets" / "franchise.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, selector
    return m.group(1)


def test_scl01_verdict_chip_wraps_inside_its_tile():
    r = _rule(".fr-app .fr-verdict")
    assert "white-space: normal" in r and "overflow-wrap: anywhere" in r and "max-width: 100%" in r, r


def test_scl05_sos_tile_prints_the_null_glyph_and_no_bare_rank():
    pytest.importorskip("py_mini_racer")
    from test_franchise_render import _render, _served
    p = copy.deepcopy(_served())
    club = next(c for c in p["clubs"] if c["code"] == "MIL")
    club["sections"]["odds"].update({"sos": None, "sos_rank": None, "il_out_60": 4})
    html, _ = _render(team="MIL", payload=p)
    sec = html.split('data-frsec="odds"')[1]
    t = sec[sec.index("Strength of schedule"):]   # the tile's own big and sub come first
    big = re.search(r'fr-tile-big[^"]*">(.*?)</div>', t).group(1)
    sub = re.search(r'fr-tile-sub">(.*?)</div>', t).group(1)
    assert big == '<span title="not measured">-</span>' and "rank" not in sub and sub == "IL out 60+: 4", (big, sub)
