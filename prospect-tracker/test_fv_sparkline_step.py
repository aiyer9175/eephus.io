# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PX-16 (final-pass plan 5.7, V3): _fv_sparkline draws the consensus FV
history as a pixel STEP line, same signature, integer box.

Pins: one 2 px run per board snapshot (held flat until the next board), a
2 px riser only where the drawn row changes, dotted grade rules at every
multiple of 5 inside the band, whole-pixel coordinates, no polyline or
stroke, and the homepage mover row at 56 x 20 (8 columns x 7 px).
"""
from __future__ import annotations

import inspect
import math
import re

import build_site as B

_RECT = re.compile(r"M(\d+) (\d+)h(\d+)v(\d+)h-(\d+)z")


def _pts(vals):
    return [{"consensus_fv_raw": v} for v in vals]


def _paths(svg: str) -> tuple[str, str]:
    gl = re.search(r'<path class="gl" d="([^"]*)"', svg).group(1)
    ln = re.search(r'<path class="ln"(?: fill="[^"]+")? d="([^"]*)"', svg).group(1)
    return gl, ln


def _rects(d: str) -> list[tuple[int, int, int, int]]:
    """Every subpath is a whole-pixel rectangle; return them as (x, y, w, h)."""
    assert "".join(m.group(0) for m in _RECT.finditer(d)) == d, "non-rect path data"
    out = []
    for x, y, w, h, back in _RECT.findall(d):
        assert w == back
        out.append((int(x), int(y), int(w), int(h)))
    return out


def _y_of(vals, h, v):
    lo = math.floor(min(vals) / 5) * 5 - 2.5
    hi = math.ceil(max(vals) / 5) * 5 + 2.5
    return int(round((hi - v) * (h - 2) / (hi - lo)))


RISER = [45, 45, 47.5, 50, 50, 52.5, 52.5, 55]


def test_one_run_per_snapshot_held_flat():
    svg = B._fv_sparkline(_pts(RISER), "var(--accent-green)", w=56, h=20)
    assert 'width="56" height="20" viewBox="0 0 56 20"' in svg
    assert "polyline" not in svg and "stroke" not in svg
    _gl, ln = _paths(svg)
    flats = [r for r in _rects(ln) if r[3] == 2]
    assert len(flats) == len(RISER) == 8
    assert [(r[0], r[2]) for r in flats] == [(i * 7, 7) for i in range(8)]
    assert [r[1] for r in flats] == [_y_of(RISER, 20, v) for v in RISER]
    risers = [r for r in _rects(ln) if r[3] > 2]
    changes = sum(1 for a, b in zip(RISER, RISER[1:]) if _y_of(RISER, 20, a) != _y_of(RISER, 20, b))
    assert len(risers) == changes == 4
    assert all(r[2] == 2 for r in risers)


def test_grade_rules_sit_at_multiples_of_five():
    svg = B._fv_sparkline(_pts(RISER), "var(--accent-green)", w=56, h=20)
    gl, _ln = _paths(svg)
    ys = sorted({r[1] for r in _rects(gl)})
    want = sorted({_y_of(RISER, 20, g) for g in (45, 50, 55)})
    assert ys == want
    # dotted: one 1x1 cell on every other column
    assert all(r[2] == 1 and r[3] == 1 and r[0] % 2 == 0 for r in _rects(gl))


def test_whole_pixels_inside_the_box_for_any_snapshot_count():
    for n in (2, 3, 9, 55, 56, 57, 76):
        vals = [40 + (i % 7) * 1.7 for i in range(n)]
        for w, h in ((56, 20), (150, 34)):
            svg = B._fv_sparkline(_pts(vals), "red", w=w, h=h)
            gl, ln = _paths(svg)
            for x, y, rw, rh in _rects(gl) + _rects(ln):
                assert 0 <= x and x + rw <= w and 0 <= y and y + rh <= h, (n, w, (x, y, rw, rh))
            flats = sorted(r for r in _rects(ln) if r[3] == 2)
            # the flat runs tile the box edge to edge, with no gap and no overlap
            assert flats[0][0] == 0 and flats[-1][0] + flats[-1][2] == w
            assert all(a[0] + a[2] == b[0] for a, b in zip(flats, flats[1:]))
            if n <= w:
                assert len(flats) == n, (n, w)


def test_too_few_points_draw_nothing_and_signature_is_kept():
    assert B._fv_sparkline(_pts([50]), "red") == ""
    assert B._fv_sparkline([], "red") == ""
    sig = inspect.signature(B._fv_sparkline)
    assert list(sig.parameters) == ["points", "color", "w", "h"]
    assert sig.parameters["w"].default == 150 and sig.parameters["h"].default == 34


def test_mover_row_draws_at_56_by_20():
    src = inspect.getsource(B._row_mover)
    assert "w=56, h=20" in src
    css = (B.ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    assert ".row-spark svg { width: 56px; height: 20px;" in css
