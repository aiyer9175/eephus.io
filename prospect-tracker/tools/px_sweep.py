# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""px_sweep.py - the pixel system's served-page sweep (final-pass plan 5.7, T7).

Drives headless Chromium over the served site at 1280 and 390 px, light and
dark, and checks what the pixel work promised on every page it touched:

  hscroll     no horizontal page scroll (scrollWidth <= innerWidth)
  ico_size    every visible svg.ico box is whole pixels and 12, 16, 24 or 32
  ico_paint   every on-page icon paints at least 2 colours in its box, and on
              dark none of its pixels is pure black (an unfilled symbol); an
              icon riding the WIRE marquee is sized from layout and not
              paint-cropped (it moves between the measure and the capture)
  footer      the footer mark is the 16 px ball strike (PX-23): one image,
              /assets/favicon-16.png (or its pixel-equal copy in assets/brand/
              under PIXEL_BRAND, BR-04), drawn at 16 x 16 from a 16 x 16 file
  fence       nothing pixel-drawn sits inside a priced betting card
              (.bt-game-probs, the Dugout fence), and that block's markup is
              the same in every theme and width
  motion      Reduce Motion runs the same animations as no preference (owner
              rule 2026-10-01, which supersedes the plan's "reduced motion:
              frames identical, 0 running" check): the running animations on
              the settled page are the same with and without the preference
  pagemiss    the PROSPX player miss draws its card back (PX-20) beside the
              unchanged message
  pxmark      the PROSPX pages carry one masthead mark, a whole-pixel 44 x 44
              box; when it is the pixel mark (PB-05, under PIXEL_BRAND) it has
              no text and every drawn pixel equals the generator's 22 x 22
              drawing at 2x in the fills the page resolves (0 pixels off)

PB-10 (owner ask 2, Part 8 pixel_branding 5.4) adds the lockup checks:

  lockup      every visible pixel wordmark (nav, homepage rail, homepage hero)
              equals its committed PNG strike (assets/brand/wordmark-s2 and
              s4, branding/pixel/wordmark-s6, in the page's theme) at DPR 1
              and 2: every opaque strike pixel, scaled by the DPR, is the same
              colour on the page (0 pixels off) under B Stepped or C Lamps; A
              Hinted is exempt from equality and is checked for the crisp edge
              instead (no fringe pixel in the ring around the strike)
  navheight   the nav bar is 72 px tall at 1280 and 63 px at 390
  brandanim   3.2 s after load no animation on a brand mark (the wordmarks,
              the PROSPX mark, the masthead rules, the footer ball) is still
              running; other running animations are listed in the report
  frames      on / the hero pitch, seeked to the same instants over 1.3 s,
              draws the same frames with Reduce Motion as without it (the
              owner's 2026-10-01 rule superseded PB-10's "reduced-motion
              frames identical": a reduced-motion frame must match the frame
              without the preference)
  shift       on / no layout-shift entry during the first 3.2 s names a
              wordmark node, and the hero lockup's box does not move while the
              pitch plays

Pages: /, /prospx/, the PROSPX player miss, /ledger/, the Ledger Method tab
(finding M09-23 asked for it at 390), /management/, /betting/ and /404.html.
The DPR 2 lockup pass loads each page once per width and theme without the
player miss and the Method tab (same nav as their parents).

Read-only: it writes screenshots and report.json under --out and nothing
else. External <use> refs do not render over file://, so it always serves the
site over HTTP: its own loopback server (--port, 0 picks a free one), or a
running one named with --base.

    python tools/px_sweep.py --port 9108 --out <dir>
    python tools/px_sweep.py --base http://127.0.0.1:8000/ --out <dir>

Exit status 1 when any check fails. test_px_sweep.py runs it under pytest
(marked browser, skipped unless PX_SWEEP=1).
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import io
import json
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The footer mark's two homes: PX-23's served strike, and the same strike in
# the pixel set build_site.py reads under PIXEL_BRAND (BR-04).
FOOTER_MARKS = ("/assets/favicon-16.png", "/assets/brand/favicon-16.png")

PAGES = (
    ("home", "/"),
    ("prospx", "/prospx/"),
    ("prospx_miss", "/prospx/#player=px-sweep-no-such-player"),
    ("ledger", "/ledger/"),
    ("ledger_method", "/ledger/#section=method"),
    ("management", "/management/"),
    ("betting", "/betting/"),
    ("404", "/404.html"),
)
WIDTHS = (1280, 390)
THEMES = ("light", "dark")
ICON_SIZES = {12, 16, 24, 32}
# 3.2 s: the hero pitch ends near 0.9 s and its one glint near 2.7 s, so every
# brand animation has finished by then (Part 8 pixel_branding 3.5).
SETTLE_MS = 3200
# PB-10: the lockup checks.
DPRS = (1, 2)
DPR2_PAGES = ("home", "prospx", "ledger", "management", "betting", "404")
NAV_HEIGHT = {1280: 72, 390: 63}
LOCKUP_W_U = 55          # lockup canvas width in font pixels (pixel_branding 3.1)
LOCKUP_PAD = 3           # CSS px searched around a lockup box for its strike
FRAME_TIMES = (0, 260, 520, 780, 1040, 1300)   # ms into the hero pitch
# Brand marks: no animation on these may still run 3.2 s after load.
BRAND_SEL = (".eephus-wordmark-px, .eephus-wordmark-px *, svg.h1-logo, svg.h1-logo *, "
             ".mh-px, .mh-px *, .eephus-footer img")
# Things that must never be drawn inside a priced card.
PIXEL_SEL = "svg.ico, .px-art, .px-lamp, .px-spark, .cf-badge, .cf-cardback, .px-state, canvas"

_MEASURE = r"""
(pixelSel) => {
  const de = document.documentElement;
  const vis = (el) => (typeof el.checkVisibility === 'function')
    ? el.checkVisibility({opacityProperty: true, visibilityProperty: true}) : true;
  const icos = [];
  document.querySelectorAll('svg.ico').forEach((s) => {
    const b = s.getBoundingClientRect();
    if (!b.width && !b.height) return;
    const u = s.querySelector('use');
    // Inside the WIRE marquee (an owner-exempt loop) the box is translated a
    // fraction of a pixel per frame and moves between measure and capture: its
    // size is read from layout and its paint is not cropped from a still.
    const moving = !!s.closest('.ticker-track');
    const cs = getComputedStyle(s);
    icos.push({x: b.left + window.scrollX, y: b.top + window.scrollY,
               w: moving ? parseFloat(cs.width) : b.width, h: moving ? parseFloat(cs.height) : b.height,
               visible: !moving && vis(s), moving, href: u ? (u.getAttribute('href') || '') : ''});
  });
  const foot = Array.from(document.querySelectorAll('.eephus-footer img')).map((i) => {
    const b = i.getBoundingClientRect();
    return {src: i.getAttribute('src') || '', w: b.width, h: b.height,
            nw: i.naturalWidth, nh: i.naturalHeight, complete: i.complete};
  });
  const probs = Array.from(document.querySelectorAll('.bt-game-probs'));
  const fenced = probs.reduce((n, el) => n + el.querySelectorAll(pixelSel).length, 0);
  const miss = document.querySelector('.cf-miss');
  const marks = Array.from(document.querySelectorAll('header.header h1 svg.h1-logo')).map((s) => {
    const b = s.getBoundingClientRect();
    const fills = {};
    s.querySelectorAll('path').forEach((p) => { fills[p.getAttribute('class') || ''] = getComputedStyle(p).fill; });
    return {x: b.left + window.scrollX, y: b.top + window.scrollY, w: b.width, h: b.height,
            pixel: s.classList.contains('px-mark'), texts: s.querySelectorAll('text').length, fills};
  });
  return {
    marks,
    sw: de.scrollWidth, iw: window.innerWidth, theme: de.getAttribute('data-theme'),
    icos, foot, probs: probs.length, fenced,
    probsHtml: probs.map((e) => e.outerHTML).join('\n'),
    miss: miss ? {cardback: !!miss.querySelector('.cf-cardback[aria-hidden="true"]'),
                  text: (miss.querySelector('.state-message') || {}).textContent || ''} : null,
  };
}
"""

_ANIMS = r"""
() => document.getAnimations()
  .filter((a) => a.playState === 'running')
  .map((a) => {
    const t = a.effect && a.effect.target;
    const tag = t ? (t.tagName || '').toLowerCase() + (t.classList && t.classList.length ? '.' + t.classList[0] : '') : '';
    return (a.animationName || a.transitionProperty || a.constructor.name) + '@' + tag;
  })
  .sort()
"""

# PB-10: the visible pixel wordmarks, the nav bar, and the brand animations
# still running (with the rest listed for the report).
_LOCKUPS = r"""
(brandSel) => {
  const vis = (el) => (typeof el.checkVisibility === 'function')
    ? el.checkVisibility({opacityProperty: true, visibilityProperty: true}) : true;
  const lockups = Array.from(document.querySelectorAll('.eephus-wordmark-px svg.wm-px')).map((s) => {
    const b = s.getBoundingClientRect();
    const vb = (s.getAttribute('viewBox') || '').split(/\s+/).map(Number);
    return {x: b.left, y: b.top, w: b.width, h: b.height, vbw: vb[2] || 0, vbh: vb[3] || 0,
            visible: b.width > 0 && b.height > 0 && vis(s),
            where: s.closest('h1') ? 'hero' : (s.closest('.eephus-nav') ? 'nav' : 'rail'),
            stepped: s.classList.contains('wm-px--stepped'), hinted: s.classList.contains('wm-px--hinted'),
            lamps: s.classList.contains('wm-px--lamps')};
  });
  const nav = document.querySelector('header.eephus-nav');
  const running = document.getAnimations().filter((a) => a.playState === 'running');
  const name = (a) => {
    const t = a.effect && a.effect.target;
    return (a.animationName || a.transitionProperty || a.constructor.name) + '@' +
      (t ? (t.tagName || '').toLowerCase() + (t.classList && t.classList.length ? '.' + t.classList[0] : '') : '');
  };
  const isBrand = (a) => { const t = a.effect && a.effect.target; return !!(t && t.matches && t.matches(brandSel)); };
  return {lockups, sx: window.scrollX, sy: window.scrollY, nav: nav ? nav.getBoundingClientRect().height : null,
          brandRunning: running.filter(isBrand).map(name).sort(),
          otherRunning: running.filter((a) => !isBrand(a)).map(name).sort()};
}
"""

# PB-10: layout shifts and the hero lockup's box, recorded from the first paint.
_SHIFT_INIT = r"""
window.__pb10 = {shifts: [], boxes: []};
try {
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) {
      window.__pb10.shifts.push({t: e.startTime, v: e.value, input: e.hadRecentInput,
        wordmark: (e.sources || []).some((s) => s.node && s.node.nodeType === 1 &&
          (s.node.closest('.eephus-wordmark-px') || s.node.querySelector('.eephus-wordmark-px'))),
        nodes: (e.sources || []).map((s) => s.node ? s.node.nodeName : '?')});
    }
  }).observe({type: 'layout-shift', buffered: true});
} catch (e) {}
(function sample() {
  const t0 = performance.now();
  const id = setInterval(() => {
    // Sampled from the moment the visible hero lockup carries its pitch (the
    // stylesheet has applied), so an unstyled first paint is not counted.
    const s = Array.from(document.querySelectorAll('h1 .eephus-wordmark-px svg.wm-px, h1.eephus-wordmark-px svg.wm-px'))
      .find((el) => el.getBoundingClientRect().width > 0);
    if (s && (window.__pb10.boxes.length || s.getAnimations({subtree: true}).length)) {
      const b = s.getBoundingClientRect();
      window.__pb10.boxes.push([Math.round(performance.now()), b.left + window.scrollX, b.top + window.scrollY, b.width, b.height]);
    }
    if (performance.now() - t0 > 3200) clearInterval(id);
  }, 10);
})();
"""

# PB-10: restart the hero pitch from its first frame and hold it paused, so a
# frame can be seeked to the same instant under either motion preference.
_PITCH_RESTART = r"""
() => {
  const svg = Array.from(document.querySelectorAll('svg.wm-px--play')).find((el) => el.getBoundingClientRect().width > 0);
  if (!svg) return 0;
  svg.classList.remove('wm-px--play');
  void svg.getBoundingClientRect();
  svg.classList.add('wm-px--play');
  const anims = svg.getAnimations({subtree: true});
  anims.forEach((a) => a.pause());
  window.__pb10pitch = anims;
  return anims.length;
}
"""
_PITCH_SEEK = r"""
(t) => { (window.__pb10pitch || []).forEach((a) => { a.currentTime = t; }); return (window.__pb10pitch || []).length; }
"""


def _strike(vbw: int, theme: str):
    """The committed PNG strike for a lockup whose viewBox is vbw wide."""
    from PIL import Image

    s = vbw // LOCKUP_W_U
    home = ROOT / "assets" / "brand" if s in (2, 4) else ROOT / "branding" / "pixel"
    return Image.open(home / f"wordmark-s{s}-{theme}.png").convert("RGBA"), s


def _lockup_off(img, box: dict, theme: str, dpr: int, scroll=(0.0, 0.0), crisp_only=False):
    """(pixels off, pixels compared, offset) for one lockup on a screenshot.

    The strike is scaled by the DPR (nearest) and searched within LOCKUP_PAD
    CSS px of the box (a fractional box snaps to whole device pixels); every
    opaque strike pixel must be the same colour on the page. With crisp_only
    (A Hinted) the check is the edge instead: no pixel in the one-pixel ring
    around the strike differs from the field colour at the crop's corner."""
    from PIL import Image

    ref, _s = _strike(int(box["vbw"]), theme)
    if dpr != 1:
        ref = ref.resize((ref.width * dpr, ref.height * dpr), Image.Resampling.NEAREST)
    pad = LOCKUP_PAD * dpr
    x0 = int(round((box["x"] + scroll[0]) * dpr)) - pad
    y0 = int(round((box["y"] + scroll[1]) * dpr)) - pad
    crop = img.convert("RGB").crop((x0, y0, x0 + ref.width + 2 * pad, y0 + ref.height + 2 * pad))
    rpx = ref.load()
    opaque = [(x, y, rpx[x, y][:3]) for y in range(ref.height) for x in range(ref.width) if rpx[x, y][3] == 255]
    cpx = crop.load()
    best = None
    for dy in range(2 * pad + 1):
        for dx in range(2 * pad + 1):
            if crisp_only:
                field = cpx[0, 0]
                mask = {(x, y) for x, y, _ in opaque}
                ring = {(x + i, y + j) for x, y in mask for i in (-1, 0, 1) for j in (-1, 0, 1)} - mask
                off = sum(1 for x, y in ring
                          if 0 <= x + dx < crop.width and 0 <= y + dy < crop.height and cpx[x + dx, y + dy] != field)
                n = len(ring)
            else:
                off = 0
                for x, y, c in opaque:
                    if cpx[x + dx, y + dy] != c:
                        off += 1
                        if best is not None and off >= best[0]:
                            break
                n = len(opaque)
            if best is None or off < best[0]:
                best = (off, n, (dx - pad, dy - pad))
            if best[0] == 0:
                return best
    return best


def _check_lockups(img, m: dict, theme: str, dpr: int, tag: str, fail: list, scroll=(0.0, 0.0)) -> list:
    """Compare every visible lockup on one capture; return the per-lockup records."""
    out = []
    for lk in m["lockups"]:
        if not lk["visible"]:
            continue
        crisp = lk["hinted"]
        off, n, at = _lockup_off(img, lk, theme, dpr, scroll, crisp_only=crisp)
        rec = {"where": lk["where"], "s": int(lk["vbw"]) // LOCKUP_W_U, "box": [lk["x"], lk["y"], lk["w"], lk["h"]],
               "check": "crisp edge" if crisp else "bitmap", "off": off, "of": n, "offset": at}
        out.append(rec)
        if (lk["w"], lk["h"]) != (lk["vbw"], lk["vbh"]):
            fail.append(f"{tag}: the {lk['where']} lockup draws at {lk['w']}x{lk['h']}, not its "
                        f"{lk['vbw']}x{lk['vbh']} canvas")
        if off:
            fail.append(f"{tag}: the {lk['where']} lockup (s {rec['s']}) is {off} of {n} pixels off its "
                        f"{'crisp edge' if crisp else 'committed strike'}")
    if not out:
        fail.append(f"{tag}: no visible pixel wordmark")
    return out


class _Quiet(http.server.SimpleHTTPRequestHandler):
    # HTTP/1.1: a socket close cannot cut a large asset short (conftest.py).
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002
        pass


def serve(port: int = 0):
    """(httpd, base_url) for the site root on a background thread."""
    handler = functools.partial(_Quiet, directory=str(ROOT))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler, bind_and_activate=False)
    httpd.daemon_threads = True
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def _context(browser, width: int, theme: str, motion: str = "no-preference", dpr: int = 1):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=dpr,
                              color_scheme=theme, reduced_motion=motion)
    ctx.add_init_script("try{localStorage.setItem('prospect-tracker.theme', %r)}catch(e){}" % theme)
    return ctx


def _open(ctx, base: str, path: str, key: str):
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.goto(base.rstrip("/") + path, wait_until="load", timeout=180_000)
    if key == "prospx_miss":
        page.wait_for_selector(".cf-miss", timeout=120_000)
    page.wait_for_timeout(SETTLE_MS)
    return page, errors


def _paint(img, ico: dict, dark: bool) -> str | None:
    """None when the icon paints, else why not."""
    x0, y0 = int(round(ico["x"])), int(round(ico["y"]))
    box = (x0, y0, x0 + int(round(ico["w"])), y0 + int(round(ico["h"])))
    if box[0] < 0 or box[1] < 0 or box[2] > img.width or box[3] > img.height:
        return None  # off the captured page (an off-canvas drawer): size checked, paint not
    crop = img.crop(box).convert("RGB")
    cols = crop.getcolors(1 << 16) or []
    if len(cols) < 2:
        return f"one colour only {cols[0][1] if cols else None}"
    if dark and any(c == (0, 0, 0) for _, c in cols):
        return "pure black on dark"
    return None


def _rgb(css: str):
    nums = [int(float(v)) for v in css[css.index("(") + 1:css.index(")")].split(",")[:3]]
    return tuple(nums)


def _pxmark_off(img, mark: dict) -> str | None:
    """None when the pixel PROSPX mark on the page equals the generator's
    drawing at 2x in the page's own fills, else how many pixels are off."""
    sys.path.insert(0, str(ROOT / "tools"))
    import pixel_brand as PB

    rows = PB.pxmark()
    scale = int(round(mark["w"])) // len(rows)
    x0, y0 = int(round(mark["x"])), int(round(mark["y"]))
    crop = img.convert("RGB").crop((x0, y0, x0 + len(rows) * scale, y0 + len(rows) * scale))
    off = total = 0
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            want = _rgb(mark["fills"][PB.PXMARK_CLASS[ch]])
            for dy in range(scale):
                for dx in range(scale):
                    total += 1
                    off += crop.getpixel((x * scale + dx, y * scale + dy)) != want
    return f"{off} of {total} pixels off the drawing" if off else None


def run(base: str, out: Path, pages=PAGES, widths=WIDTHS, themes=THEMES) -> dict:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"base": base, "captures": {}, "motion": {}, "fence": {}, "failures": []}
    fail = report["failures"]
    probs_html: dict[str, set] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for key, path in pages:
                for width in widths:
                    for theme in themes:
                        tag = f"{key}_{width}_{theme}"
                        ctx = _context(browser, width, theme)
                        try:
                            page, errors = _open(ctx, base, path, key)
                            m = page.evaluate(_MEASURE, PIXEL_SEL)
                            lk = page.evaluate(_LOCKUPS, BRAND_SEL)
                            png = page.screenshot(full_page=True)
                        finally:
                            ctx.close()
                        (out / f"{tag}.png").write_bytes(png)
                        img = Image.open(io.BytesIO(png))
                        rec = {"scrollWidth": m["sw"], "innerWidth": m["iw"], "theme": m["theme"],
                               "icons": len(m["icos"]), "footer": m["foot"], "probs": m["probs"],
                               "fenced": m["fenced"], "miss": m["miss"], "pageerrors": errors}
                        if m["theme"] != theme:
                            fail.append(f"{tag}: page theme {m['theme']!r}, wanted {theme!r}")
                        if m["sw"] > m["iw"]:
                            fail.append(f"{tag}: horizontal scroll {m['sw']} > {m['iw']}")
                        sizes = sorted({f"{i['w']}x{i['h']}" for i in m["icos"]})
                        rec["icon_sizes"] = sizes
                        for i in m["icos"]:
                            if (i["w"] != int(i["w"]) or i["h"] != int(i["h"])
                                    or int(i["w"]) not in ICON_SIZES or i["w"] != i["h"]):
                                fail.append(f"{tag}: svg.ico box {i['w']}x{i['h']} ({i['href']})")
                                break
                        bad_paint = []
                        painted = 0
                        for i in m["icos"]:
                            if not i["visible"]:
                                continue
                            why = _paint(img, i, theme == "dark")
                            painted += 1
                            if why:
                                bad_paint.append(f"{i['href'].split('#')[-1]} {why}")
                        rec["icons_paint_checked"] = painted
                        if bad_paint:
                            fail.append(f"{tag}: {len(bad_paint)} icon(s) do not paint: " + "; ".join(bad_paint[:6]))
                        if m["foot"]:
                            f = m["foot"]
                            if (len(f) != 1 or not f[0]["src"].endswith(FOOTER_MARKS)
                                    or (f[0]["w"], f[0]["h"]) != (16, 16)
                                    or (f[0]["nw"], f[0]["nh"]) != (16, 16) or not f[0]["complete"]):
                                fail.append(f"{tag}: footer mark is not the 16 px strike: {f}")
                        elif key != "prospx_miss":
                            fail.append(f"{tag}: no footer mark")
                        if m["fenced"]:
                            fail.append(f"{tag}: {m['fenced']} pixel element(s) inside .bt-game-probs")
                        if m["probs"]:
                            probs_html.setdefault(key, set()).add(
                                hashlib.sha256(m["probsHtml"].encode("utf-8")).hexdigest())
                        if key == "prospx_miss":
                            ms = m["miss"]
                            if not ms or not ms["cardback"] or "Unknown prospect" not in ms["text"]:
                                fail.append(f"{tag}: the player miss shows no card back beside its message: {ms}")
                        if key.startswith("prospx"):
                            mk = m["marks"]
                            rec["pxmark"] = [{"w": k["w"], "h": k["h"], "pixel": k["pixel"]} for k in mk]
                            if len(mk) != 1 or (mk[0]["w"], mk[0]["h"]) != (44, 44):
                                fail.append(f"{tag}: the PROSPX masthead mark is not one 44 x 44 box: {rec['pxmark']}")
                            elif mk[0]["pixel"]:
                                why = "text inside" if mk[0]["texts"] else _pxmark_off(img, mk[0])
                                if why:
                                    fail.append(f"{tag}: the pixel PROSPX mark: {why}")
                        # PB-10: lockups at DPR 1, the nav height, brand motion settled.
                        rec["lockups"] = _check_lockups(img, lk, theme, 1, tag, fail, (lk["sx"], lk["sy"]))
                        rec["nav"] = lk["nav"]
                        if width in NAV_HEIGHT and lk["nav"] is not None and lk["nav"] != NAV_HEIGHT[width]:
                            fail.append(f"{tag}: the nav bar is {lk['nav']} px tall, not {NAV_HEIGHT[width]}")
                        elif lk["nav"] is None and key != "prospx_miss":
                            fail.append(f"{tag}: no nav bar")
                        rec["brand_running"], rec["other_running"] = lk["brandRunning"], lk["otherRunning"]
                        if lk["brandRunning"]:
                            fail.append(f"{tag}: brand animation(s) still running {SETTLE_MS} ms after load: "
                                        f"{lk['brandRunning']}")
                        report["captures"][tag] = rec
            # PB-10: the lockups at DPR 2 (viewport captures; every lockup sits at the top).
            report["lockups_dpr2"] = {}
            for key, path in pages:
                if key not in DPR2_PAGES:
                    continue
                for width in widths:
                    for theme in themes:
                        tag = f"{key}_{width}_{theme}_dpr2"
                        ctx = _context(browser, width, theme, dpr=2)
                        try:
                            page, _errs = _open(ctx, base, path, key)
                            lk = page.evaluate(_LOCKUPS, BRAND_SEL)
                            png = page.screenshot()
                        finally:
                            ctx.close()
                        img = Image.open(io.BytesIO(png))
                        report["lockups_dpr2"][tag] = _check_lockups(img, lk, theme, 2, tag, fail)
            # PB-10: on / the hero lockup holds still and shifts nothing while
            # the pitch plays, and Reduce Motion draws the pitch's own frames.
            if any(k == "home" for k, _ in pages):
                home = dict(pages)["home"]
                ctx = _context(browser, widths[0], themes[0])
                ctx.add_init_script(_SHIFT_INIT)
                try:
                    page, _errs = _open(ctx, base, home, "home")
                    rec = page.evaluate("() => window.__pb10")
                finally:
                    ctx.close()
                boxes = rec["boxes"]
                moved = sorted({tuple(b[1:]) for b in boxes})
                ours = [s for s in rec["shifts"] if s["wordmark"]]
                report["shift"] = {"samples": len(boxes), "boxes": [list(b) for b in moved],
                                   "shifts": rec["shifts"], "wordmark_shifts": len(ours)}
                if not boxes:
                    fail.append("home: the hero lockup was never sampled")
                elif len(moved) != 1:
                    fail.append(f"home: the hero lockup moved while the pitch played: {moved}")
                if ours:
                    fail.append(f"home: {len(ours)} layout shift(s) name a wordmark node: {ours}")
                frames: dict[str, list] = {}
                for motion in ("reduce", "no-preference"):
                    ctx = _context(browser, widths[0], themes[0], motion)
                    try:
                        page, _errs = _open(ctx, base, home, "home")
                        page.add_style_tag(content="#eephus-bg{visibility:hidden!important}")
                        n = page.evaluate(_PITCH_RESTART)
                        box = page.evaluate("""() => { const s = Array.from(document.querySelectorAll('svg.wm-px--play'))
                            .find((el) => el.getBoundingClientRect().width > 0); const b = s.getBoundingClientRect();
                            return {x: b.left - 8, y: b.top - 8, width: b.width + 16, height: b.height + 16}; }""")
                        shots = []
                        for t in FRAME_TIMES:
                            page.evaluate(_PITCH_SEEK, t)
                            page.wait_for_timeout(50)
                            shot = page.screenshot(clip=box)
                            shots.append(Image.open(io.BytesIO(shot)).convert("RGB").tobytes())
                            (out / f"pitch_{motion}_{t:04d}ms.png").write_bytes(shot)
                        frames[motion] = shots
                    finally:
                        ctx.close()
                    report.setdefault("frames", {})[motion] = {"animations": n, "frames": len(shots)}
                same = [a == b for a, b in zip(frames["reduce"], frames["no-preference"])]
                distinct = len(set(frames["no-preference"]))
                report["frames"]["identical"] = same
                report["frames"]["distinct_frames_without_preference"] = distinct
                if not all(same):
                    fail.append("home: with Reduce Motion the hero pitch draws different frames at "
                                f"{[t for t, s in zip(FRAME_TIMES, same) if not s]} ms")
                if report["frames"]["no-preference"]["animations"] == 0:
                    fail.append("home: the hero lockup carries no pitch to seek")
            for key, hashes in probs_html.items():
                report["fence"][key] = {"variants": len(hashes)}
                if len(hashes) != 1:
                    fail.append(f"{key}: .bt-game-probs markup differs across themes and widths")
            # Reduce Motion runs what no preference runs (owner, 2026-10-01).
            for key, path in pages:
                runs = {}
                for motion in ("reduce", "no-preference"):
                    ctx = _context(browser, widths[0], themes[0], motion)
                    try:
                        page, _ = _open(ctx, base, path, key)
                        runs[motion] = page.evaluate(_ANIMS)
                    finally:
                        ctx.close()
                report["motion"][key] = runs
                if runs["reduce"] != runs["no-preference"]:
                    fail.append(f"{key}: Reduce Motion runs {runs['reduce']} but no preference runs "
                                f"{runs['no-preference']}")
        finally:
            browser.close()
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The pixel system's served-page sweep (T7).")
    ap.add_argument("--base", help="a running server's base URL; default: serve the site here")
    ap.add_argument("--port", type=int, default=0, help="port for the built-in server (0 = any free)")
    ap.add_argument("--out", default=None, help="folder for screenshots and report.json")
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="px_sweep_"))
    httpd = None
    base = a.base
    if not base:
        httpd, base = serve(a.port)
    try:
        rep = run(base, out)
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()
    for line in rep["failures"]:
        print("FAIL", line)
    n = len(rep["captures"])
    print(f"{n} captures, {len(rep['failures'])} failure(s); report and screenshots in {out}")
    return 1 if rep["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
