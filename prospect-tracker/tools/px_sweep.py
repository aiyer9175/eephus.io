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
              dark none of its pixels is pure black (an unfilled symbol)
  footer      the footer mark is the 16 px ball strike (PX-23): one image,
              /assets/favicon-16.png, drawn at 16 x 16 from a 16 x 16 file
  fence       nothing pixel-drawn sits inside a priced betting card
              (.bt-game-probs, the Dugout fence), and that block's markup is
              the same in every theme and width
  motion      Reduce Motion runs the same animations as no preference (owner
              rule 2026-10-01, which supersedes the plan's "reduced motion:
              frames identical, 0 running" check): the running animations on
              the settled page are the same with and without the preference
  pagemiss    the PROSPX player miss draws its card back (PX-20) beside the
              unchanged message

Pages: /, /prospx/, the PROSPX player miss, /ledger/, the Ledger Method tab
(finding M09-23 asked for it at 390), /management/, /betting/ and /404.html.

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
SETTLE_MS = 1800
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
    icos.push({x: b.left + window.scrollX, y: b.top + window.scrollY, w: b.width, h: b.height,
               visible: vis(s), href: u ? (u.getAttribute('href') || '') : ''});
  });
  const foot = Array.from(document.querySelectorAll('.eephus-footer img')).map((i) => {
    const b = i.getBoundingClientRect();
    return {src: i.getAttribute('src') || '', w: b.width, h: b.height,
            nw: i.naturalWidth, nh: i.naturalHeight, complete: i.complete};
  });
  const probs = Array.from(document.querySelectorAll('.bt-game-probs'));
  const fenced = probs.reduce((n, el) => n + el.querySelectorAll(pixelSel).length, 0);
  const miss = document.querySelector('.cf-miss');
  return {
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


def _context(browser, width: int, theme: str, motion: str = "no-preference"):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=1,
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
                            if (len(f) != 1 or not f[0]["src"].endswith("/assets/favicon-16.png")
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
                        report["captures"][tag] = rec
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
