# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The canvas pixel lockup painter (owner ask 2, PB-08 / BR-08).

Under build_site.PIXEL_BRAND the exports paint the pixel lockup from its
committed PNG strikes (assets/brand/wordmark-s{2,4}-{light,dark}.png, written by
tools/pixel_brand.py) instead of setting the words in a font: the image-export
frame (_brandCompose in assets/eephus-export.js) and the three Generate GFX
headers (renderBoard, renderNewsDay and renderSourceComp in
assets/eephus-gfx.js), which drew 'EEPHUS.IO' in capitals. Pinned here:

  1. integer scale: whatever the caller passes, the painter draws a strike at a
     whole number of device pixels per strike pixel, from a whole device pixel,
     with smoothing off (restored after), and picks the largest committed strike
     that divides the requested font-pixel size (s 4 at 1:1 before s 2 doubled);
     a size no strike divides paints nothing;
  2. the strikes load at export time only, once per strike, revalidated, and a
     failed load or a strike of the wrong size leaves the text wordmark;
  3. the painter's strike geometry and baseline equal the generator's, and the
     served strikes are the generator's pixels;
  4. the wiring: the flag is read off the page (the pixel lockup's hidden words,
     which build_site emits only with the flag on, the nav included), the
     flag-off frames keep today's text, and the flag-on text fallback is
     lowercase with the lilac .io (owner answer PB-Q3).

The painter runs under a real JS runtime (node, or the VS Code Electron binary
run as node, as test_pixel_gfx_painter.py does); the wiring checks read the
source.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent
EXPORT_JS = ROOT / "assets" / "eephus-export.js"
GFX_JS = ROOT / "assets" / "eephus-gfx.js"
BRAND = ROOT / "assets" / "brand"
sys.path.insert(0, str(ROOT / "tools"))
import pixel_brand as PB  # noqa: E402
import pixel_brand_src as SRC  # noqa: E402


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


# A DOM-free host. The page's flag is the pixel lockup's hidden words: mode
# "off" serves no ".nameplate > .wm-txt". Image decodes a strike to the size its file
# name implies (mode "badsize" one pixel wider).
_STUB = r"""
var fs = require("fs");
var args = process.argv.slice(-2);
var mode = args[1];
var fetches = [];
global.window = global;
global.location = { pathname: "/fa/" };
global.document = {
  body: null, addEventListener: function () {},
  querySelector: function (sel) {
    if (sel === ".nameplate > .wm-txt") return mode === "off" ? null : {};
    return null;
  },
};
global.fetch = function (url, opts) {
  fetches.push([url, (opts && opts.cache) || null]);
  if (mode === "fail") return Promise.reject(new Error("offline"));
  return Promise.resolve({ ok: true, blob: function () { return Promise.resolve({ url: url }); } });
};
global.URL = { createObjectURL: function (b) { return "blob:" + b.url; }, revokeObjectURL: function () {} };
global.Image = function () {
  var self = this;
  Object.defineProperty(this, "src", { set: function (v) {
    var s = +/wordmark-s(\d)-/.exec(v)[1];
    self.width = (s === 4 ? 220 : 110) + (mode === "badsize" ? 1 : 0);
    self.height = s === 4 ? 84 : 42;
    setTimeout(function () { self.onload(); }, 0);
  } });
};
eval(fs.readFileSync(args[0], "utf8"));
var X = window.EephusExport;
function rec() {
  var calls = [];
  return { calls: calls, imageSmoothingEnabled: true,
           drawImage: function (img, x, y, w, h) {
             calls.push({ w0: img.width, h0: img.height, x: x, y: y, w: w, h: h,
                          smooth: this.imageSmoothingEnabled });
           } };
}
var out = { fetchesAtLoad: fetches.length, flag: X.pixelBrand(), strikes: {} };
for (var u = 0; u <= 12; u++) out.strikes[u] = X.lockupStrike(u);
out.before = X.pxLockup(rec(), 0, 0, 4, 1, false);
Promise.all([X.loadLockup(4, false), X.loadLockup(4, false), X.loadLockup(4, true),
             X.loadLockup(2, true), X.loadLockup(6, false), X.loadLockup(3, false)]).then(function (imgs) {
  out.loaded = imgs.map(function (i) { return !!i; });
  out.fetches = fetches.slice();
  var cases = [[0.4, 7.6, 4, 1, false], [10.3, 12.7, 4, 2, false], [40, 12, 4, 2, true],
               [0, 0, 8, 2, false], [5, 5, 2, 2, true], [5.25, 5, 6, 2, false],
               [1, 1, 3, 1, false], [1, 1, 6, 1, true]];
  out.cases = cases.map(function (c) {
    var g = rec();
    var box = X.pxLockup(g, c[0], c[1], c[2], c[3], c[4]);
    return { args: c, box: box, calls: g.calls, after: g.imageSmoothingEnabled };
  });
  process.stdout.write(JSON.stringify(out));
});
"""


def _run(mode: str, tmp_path: Path) -> dict:
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    src = tmp_path / "export.js"
    src.write_text(EXPORT_JS.read_text(encoding="utf-8").replace("\r\n", "\n"), encoding="utf-8")
    res = subprocess.run(cmd + ["-e", _STUB, str(src), mode], capture_output=True,
                         text=True, env=dict(os.environ, **extra), timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _whole(v: float) -> bool:
    return abs(v - round(v)) < 1e-9


# ---------------------------------------------------------------- 1. integer scale
def test_strike_choice_is_the_largest_committed_scale_that_divides_u(tmp_path):
    out = _run("on", tmp_path)
    for u in range(0, 13):
        got = out["strikes"][str(u)]
        want = next(({"s": s, "k": u // s} for s in sorted(SRC.EXPORT_SCALES, reverse=True)
                     if u >= s and u % s == 0), None)
        assert got == want, (u, got)
    # the exports' own size: letters 4 device px per font pixel is the s 4 strike at 1:1
    assert out["strikes"]["4"] == {"s": 4, "k": 1}


def test_painter_draws_whole_device_pixels_with_smoothing_off(tmp_path):
    out = _run("on", tmp_path)
    painted = 0
    for case in out["cases"]:
        x, y, u, unit, _dark = case["args"]
        if u % 2:
            assert case["box"] is None and case["calls"] == [], case["args"]
            continue
        assert case["box"] is not None, case["args"]
        (call,) = case["calls"]
        k = out["strikes"][str(u)]["k"]
        for v in (call["x"], call["y"], call["w"], call["h"]):
            assert _whole(v * unit), (case["args"], v)
        assert round(call["w"] * unit) == call["w0"] * k
        assert round(call["h"] * unit) == call["h0"] * k
        # JS Math.round: half up
        assert abs(call["x"] * unit - math.floor(x * unit + .5)) < 1e-9
        assert abs(call["y"] * unit - math.floor(y * unit + .5)) < 1e-9
        assert call["smooth"] is False and case["after"] is True
        assert abs(case["box"]["base"] * unit - (SRC.BASE + 1) * u) < 1e-9
        painted += 1
    assert painted == 7


# ---------------------------------------------------------------- 2. lazy, once, fallbacks
def test_strikes_load_lazily_once_each_and_revalidate(tmp_path):
    out = _run("on", tmp_path)
    assert out["flag"] is True
    assert out["fetchesAtLoad"] == 0, "loading the script must fetch nothing"
    assert out["before"] is None, "nothing paints before the strike loads"
    assert out["loaded"] == [True, True, True, True, True, False]
    urls = [u for u, _ in out["fetches"]]
    assert sorted(urls) == sorted(f"/assets/brand/wordmark-s{s}-{t}.png"
                                  for s, t in ((4, "light"), (4, "dark"), (2, "dark"), (2, "light")))
    assert all(cache == "no-cache" for _, cache in out["fetches"])


@pytest.mark.parametrize("mode", ["fail", "badsize"])
def test_a_missing_or_wrong_strike_paints_nothing(tmp_path, mode):
    out = _run(mode, tmp_path)
    assert not any(out["loaded"])
    assert all(c["box"] is None and c["calls"] == [] for c in out["cases"])


def test_the_flag_is_the_served_pixel_lockup(tmp_path, monkeypatch):
    out = _run("off", tmp_path)
    assert out["flag"] is False
    assert out["fetchesAtLoad"] == 0
    # The probe the painter reads is what build_site serves: the pixel lockup
    # (every placement, the hand-kept navs synced from the same function) wraps
    # its words in .wm-txt directly under the .nameplate, and nothing else does.
    import build_site as B
    probe = re.search(r'var PIXEL_BRAND_PROBE = "([^"]+)";', EXPORT_JS.read_text(encoding="utf-8")).group(1)
    assert probe == ".nameplate > .wm-txt"
    monkeypatch.setattr(B, "PIXEL_BRAND", True)
    for uid, tag in (("nav", "span"), ("sb", "span"), ("mast", "h1")):
        mark = B.eephus_merged_wordmark(uid, tag=tag)
        assert re.match(rf'<{tag} class="nameplate [^"]*">.*<span class="wm-txt">eephus\.io</span></{tag}>$', mark), uid
    monkeypatch.setattr(B, "PIXEL_BRAND", False)
    for uid, tag in (("nav", "span"), ("sb", "span"), ("mast", "h1")):
        assert "wm-txt" not in B.eephus_merged_wordmark(uid, tag=tag), uid
    for rel in list(B.HAND_AUTHORED_PAGES) + ["index.html", "fa/index.html", "news/index.html", "glossary/index.html"]:
        assert "wm-txt" not in (ROOT / rel).read_text(encoding="utf-8"), rel


# ---------------------------------------------------------------- 3. geometry = generator
def _js_strikes() -> tuple[dict, int, list]:
    js = EXPORT_JS.read_text(encoding="utf-8")
    m = re.search(r"var LOCKUP_STRIKES = \{([^}]*)\};", js)
    dims = {int(s): (int(w), int(h)) for s, w, h in re.findall(r"(\d+): \[(\d+), (\d+)\]", m.group(1))}
    base = int(re.search(r"var LOCKUP_BASE_U = (\d+);", js).group(1))
    order = [int(v) for v in re.search(r"var scales = \[([\d, ]+)\];", js).group(1).split(",")]
    return dims, base, order


def test_painter_geometry_equals_the_generator():
    dims, base, order = _js_strikes()
    assert sorted(dims) == sorted(SRC.EXPORT_SCALES)
    assert order == sorted(SRC.EXPORT_SCALES, reverse=True)
    assert base == SRC.BASE + 1
    for s in SRC.EXPORT_SCALES:
        comp = PB.compose(s)
        assert dims[s] == (comp["W"], comp["H"]), s
        # the baseline: the letters' ink above it ends on the row just above
        # LOCKUP_BASE_U font pixels, and only the descender ('p') crosses it
        rows = {y for _, y in comp["letters"]}
        assert max(y for y in rows if y < base * s) == base * s - 1, s
        below = {x for x, y in comp["letters"] if y >= base * s}
        assert 0 < len(below) <= 2 * s, s


@pytest.mark.parametrize("s", SRC.EXPORT_SCALES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_served_strikes_are_the_generator_pixels(s, theme):
    im = Image.open(BRAND / f"wordmark-s{s}-{theme}.png")
    assert PB.same_pixels(im, PB.to_png(PB.compose(s), theme))
    # .io is lilac in both themes (owner answer PB-Q3): the strike paints its
    # dot cells in --logo-dot, the lilac of both decks, never the old gold
    lilac = PB.hx(SRC.TOKENS["logo-dot"][theme == "dark"])
    assert PB.hx(PB.key_hex("dot", theme)) == lilac != PB.hx("#C9A227")
    assert lilac + (255,) in {c for _, c in im.convert("RGBA").getcolors(1 << 16)}


# ---------------------------------------------------------------- 4. wiring
def _body(js: str, head: str) -> str:
    i = js.index(head)
    j = js.find("\n  function ", i + len(head))
    k = js.find("\n  async function ", i + len(head))
    ends = [e for e in (j, k) if e > 0]
    return js[i:min(ends)] if ends else js[i:]


def test_export_frame_paints_the_lockup_only_under_the_flag():
    js = EXPORT_JS.read_text(encoding="utf-8")
    body = _body(js, "function _brandCompose(")
    assert re.search(r"var pb = pixelBrand\(\);\s*var lk = pb \? pxLockup\(", body)
    # flag off keeps today's text and its gold .io on light; flag on is lilac
    assert 'g.fillText("eephus", pad, by);' in body
    assert '(pb ? "#6E56CF" : "#C9A227")' in body
    exp = _body(js, "function exportImage(")
    assert "if (pixelBrand()) jobs.push(loadLockup(" in exp


def test_gfx_headers_draw_the_lockup_not_capitals():
    js = GFX_JS.read_text(encoding="utf-8")
    for head in ("function renderBoard(", "async function renderNewsDay(", "function renderSourceComp("):
        body = _body(js, head)
        assert "brandHead(g, P, PAD, 50);" in body, head
        assert "EEPHUS.IO" not in body, head
    # the capitals survive only as the flag-off branch of brandHead
    assert js.count('"EEPHUS.IO"') == 1
    brand = _body(js, "function brandHead(")
    assert 'if (!L) { g.fillText("EEPHUS.IO", x, base); return; }' in brand
    assert 'tok("--logo-dot", P.dark ? "#9B8CFF" : "#6E56CF")' in brand
    assert "C9A227" not in brand
    rc = _body(js, "async function renderCanvas(")
    assert "await L.loadLockup(LOCKUP_U, palette().dark)" in rc


def test_painter_uses_no_animation_frame():
    for path in (EXPORT_JS, GFX_JS):
        assert "requestAnimationFrame" not in path.read_text(encoding="utf-8"), path.name
