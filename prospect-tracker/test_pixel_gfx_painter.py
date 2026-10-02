# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The canvas pixel icon painter (final-pass plan 5.7, PX-18).

The exports cannot draw an external <use>, so assets/eephus-export.js paints
the icon set's own bitmaps (assets/eephus-icons.json, written by
tools/pixel_icons.py beside the sprite) with fillRect. What is pinned:

  1. the painter's scale is a whole number and its origin whole units, so every
     rect it emits lands on whole pixels, whatever the caller passes;
  2. one rect per horizontal run, covering exactly the bitmap's ink and accent
     cells, and an alias (ev-trade, ev-debut) paints its target's bitmap;
  3. the table is fetched lazily, at export time only: loading the script
     fetches nothing, the first loadIcons() fetches once and later calls reuse
     it, and a failed fetch leaves the painter a no-op (text-only frames);
  4. the three frames that use it: the image-export title (_brandCompose), the
     Generate GFX board title and the /news/ per-date rows, which carry the
     event's wire pictogram key and keep the text glyph as the fallback.

The painter runs under a real JS runtime (node, or the VS Code Electron
binary run as node, as test_source_comparison_hero_floor.py does); the
wiring checks read the source.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
EXPORT_JS = ROOT / "assets" / "eephus-export.js"
GFX_JS = ROOT / "assets" / "eephus-gfx.js"
ICONS = ROOT / "assets" / "eephus-icons.json"


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


# A DOM-free host: the module only touches document/location inside functions
# that run on boot (DOMContentLoaded never fires here) or inside the painter.
_STUB = r"""
var fs = require("fs");
var args = process.argv.slice(-3);
var table = JSON.parse(fs.readFileSync(args[1], "utf8"));
var mode = args[2];
var fetches = [];
global.window = global;
global.location = { pathname: "/fa/" };
global.document = {
  body: null, addEventListener: function () {},
  querySelector: function () { return { getAttribute: function () { return "/assets/eephus-icons.svg?v=abc123#i-fa"; } }; },
};
global.fetch = function (url) {
  fetches.push(url);
  if (mode === "fail") return Promise.reject(new Error("offline"));
  return Promise.resolve({ ok: true, json: function () { return table; } });
};
eval(fs.readFileSync(args[0], "utf8"));
var X = window.EephusExport;
function rec() {
  var calls = [];
  return { calls: calls, fillStyle: "#000",
           fillRect: function (x, y, w, h) { calls.push([x, y, w, h, this.fillStyle]); } };
}
var out = { fetchesAtLoad: fetches.length };
var before = rec();
out.paintBeforeLoad = X.pxIcon(before, "ledger", 0, 0, 1, "#111");
X.loadIcons().then(function () {
  return X.loadIcons();
}).then(function () {
  out.fetches = fetches.slice();
  out.hasLedger = X.hasIcon("ledger");
  out.route = X.routeIcon();
  var cases = [["ledger", 10.4, 7.6, 1.5], ["ev-trade", 3, 3, 2], ["ev-up", 0.5, 0.5, 0.4],
               ["ledger", 0, 0, 3], ["no-such-icon", 0, 0, 2]];
  out.cases = cases.map(function (c) {
    var g = rec();
    var w = X.pxIcon(g, c[0], c[1], c[2], c[3], "#123456", c[0] === "ledger" && c[3] === 3 ? "#ABCDEF" : null);
    return { key: c[0], width: w, calls: g.calls, after: g.fillStyle };
  });
  process.stdout.write(JSON.stringify(out));
});
"""


def _run(mode: str, tmp_path: Path) -> dict:
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    js = EXPORT_JS.read_text(encoding="utf-8").replace("\r\n", "\n")
    src = tmp_path / "export.js"
    src.write_text(js, encoding="utf-8")
    res = subprocess.run(cmd + ["-e", _STUB, str(src), str(ICONS), mode], capture_output=True,
                         text=True, env=dict(os.environ, **extra), timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _rows(key: str) -> list[str]:
    t = json.loads(ICONS.read_text(encoding="utf-8"))
    e = t[key]
    return t[e["alias"]]["rows"] if "alias" in e else e["rows"]


def _cells(calls, scale: int, x0: int, y0: int) -> dict:
    """{(col, row): colour} covered by the rects, in bitmap cells."""
    got = {}
    for x, y, w, h, col in calls:
        assert h == scale and w % scale == 0
        assert (x - x0) % scale == 0 and (y - y0) % scale == 0
        for c in range((x - x0) // scale, (x - x0 + w) // scale):
            cell = (c, (y - y0) // scale)
            assert cell not in got, f"cell {cell} painted twice"
            got[cell] = col
    return got


def test_painter_scale_and_origin_are_whole_numbers(tmp_path):
    out = _run("ok", tmp_path)
    for case in out["cases"]:
        for x, y, w, h, _col in case["calls"]:
            for v in (x, y, w, h):
                assert v == int(v), f"{case['key']}: fillRect got a fractional value {v}"
    by = {(c["key"], i): c for i, c in enumerate(out["cases"])}
    # 1.5 rounds to 2, 0.4 floors at 1, origin 10.4/7.6 snaps to 10/8
    ledger = by[("ledger", 0)]
    assert ledger["width"] == 24
    assert min(x for x, *_ in ledger["calls"]) >= 10 and all(
        (x - 10) % 2 == 0 and (y - 8) % 2 == 0 for x, y, *_ in ledger["calls"])
    assert by[("ev-up", 2)]["width"] == 12


def test_painter_covers_exactly_the_bitmap(tmp_path):
    out = _run("ok", tmp_path)
    for case, (scale, x0, y0) in ((out["cases"][0], (2, 10, 8)), (out["cases"][3], (3, 0, 0))):
        rows = _rows("ledger")
        want = {(c, r) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch in "#+"}
        got = _cells(case["calls"], scale, x0, y0)
        assert set(got) == want
        # one rect per run: no two rects in a row touch with the same colour
        assert len(case["calls"]) == sum(
            len(re.findall(r"#+|\++", row)) for row in rows)
    # accent cells take the accent colour only when one is passed
    accent = {(c, r) for r, row in enumerate(_rows("ledger")) for c, ch in enumerate(row) if ch == "+"}
    got3 = _cells(out["cases"][3]["calls"], 3, 0, 0)
    assert accent and all(got3[k] == "#ABCDEF" for k in accent)
    assert all(v == "#123456" for k, v in got3.items() if k not in accent)
    got0 = _cells(out["cases"][0]["calls"], 2, 10, 8)
    assert set(got0.values()) == {"#123456"}, "an icon at rest paints its accent in its ink"
    # the painter restores the context's fill
    assert all(c["after"] == "#000" for c in out["cases"])


def test_alias_paints_its_target_and_unknown_keys_paint_nothing(tmp_path):
    out = _run("ok", tmp_path)
    trade = out["cases"][1]
    want = {(c, r) for r, row in enumerate(_rows("trademachine")) for c, ch in enumerate(row) if ch in "#+"}
    assert set(_cells(trade["calls"], 2, 3, 3)) == want
    unknown = out["cases"][4]
    assert unknown["width"] == 0 and unknown["calls"] == []


def test_table_is_fetched_once_at_export_time_only(tmp_path):
    out = _run("ok", tmp_path)
    assert out["fetchesAtLoad"] == 0, "loading eephus-export.js fetched the icon table"
    assert out["paintBeforeLoad"] == 0, "the painter drew before the table loaded"
    assert out["fetches"] == ["/assets/eephus-icons.json?v=abc123"], (
        f"expected one fetch stamped with the sprite's own ?v=, got {out['fetches']}")
    assert out["hasLedger"] is True
    assert out["route"] == "fa", "the module icon is not read off the page route"


def test_a_failed_fetch_leaves_text_only_frames(tmp_path):
    out = _run("fail", tmp_path)
    assert out["hasLedger"] is False and out["route"] == ""
    assert all(c["width"] == 0 and c["calls"] == [] for c in out["cases"])


def _fn(src: str, name: str) -> str:
    m = re.search(r"(?:async\s+)?function %s\s*\(" % re.escape(name), src)
    assert m, f"{name} not found"
    i = src.index("{", m.end())
    depth = 0
    for j in range(i, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            return src[m.start():j + 1]
    raise AssertionError(name)


def test_frames_use_the_painter_at_integer_scales():
    exp = EXPORT_JS.read_text(encoding="utf-8")
    gfx = GFX_JS.read_text(encoding="utf-8")
    compose = _fn(exp, "_brandCompose")
    assert re.search(r"pxIcon\(g, ik, [^;]*, S, tc\)", compose), (
        "the image-export title no longer paints the module icon at the frame's own "
        "integer supersample S")
    assert "loadIcons()" in _fn(exp, "exportImage"), "exportImage no longer loads the table"
    board = _fn(gfx, "renderBoard")
    assert re.search(r"X\.pxIcon\(g, ik, PAD, 108 - 24, 2, fg\)", board), (
        "the Generate GFX board title no longer paints its 24 px module icon (scale 2)")
    day = _fn(gfx, "renderNewsDay")
    assert re.search(r"Xp\.pxIcon\(g, it\.ico, [^;]*, 1, vcol\)", day), (
        "the /news/ per-date rows no longer paint the wire pictogram at scale 1")
    assert "it.glyph" in day, "the per-date rows lost the text-glyph fallback"
    assert re.search(r"await X\.loadIcons\(\)", _fn(gfx, "renderCanvas")), (
        "the GFX engine no longer loads the table at render time")
    for src in (exp, gfx):
        for m in re.finditer(r"pxIcon\(([^)]*)\)", src):
            args = [a.strip() for a in m.group(1).split(",")]
            if len(args) < 5 or args[0] == "ctx":
                continue  # the definition
            assert re.fullmatch(r"\d+|S", args[4]), f"pxIcon scale {args[4]!r} is not an integer literal or S"


def test_news_day_spec_carries_the_pictogram_key():
    import build_site
    js = build_site._NEWS_GFX_JS
    assert "ico:TYPE[e.typ]?'ev-'+e.typ:''" in js
    assert "glyph:e.glyph||''" in js
    assert "val:e.val||''" in js
