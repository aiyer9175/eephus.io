# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Pre-launch visual sweep: boot every shipped surface across viewports and themes,
capture page errors + console errors + horizontal-bleed, and screenshot each for an
eyeball pass over squish / cutoff / bleed / overlap.

This is a TOOL, not a pytest test (no test_ prefix): it is run by hand during the
polish pass. It serves the repo dir on an ephemeral port (same pattern as
test_prospx_sort_a11y.py) and drives chromium via Playwright. Skips cleanly if
Playwright / chromium are unavailable.

Usage:
    python tools/visual_sweep.py                 # full matrix, screenshots to a temp dir
    python tools/visual_sweep.py --out DIR        # screenshots to DIR
    python tools/visual_sweep.py --routes prospx  # only routes whose id contains "prospx"
    python tools/visual_sweep.py --viewports 375,1280  --themes dark

Report: prints a per-cell table and a defect summary (pageerror / console.error /
horizontal bleed), and writes report.json next to the screenshots. Exit code is
non-zero if any pageerror or horizontal bleed is found (P0/P1 signal).
"""
import argparse
import functools
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (id, path-with-hash). Paths are relative to the served repo root.
ROUTES = [
    ("home", "/index.html"),
    ("prospx", "/prospx/index.html"),
    ("prospx-player", "/prospx/index.html#player=jesus_made"),
    ("prospx-farm", "/prospx/index.html#tab=farm"),
    ("prospx-leaderboards", "/prospx/index.html#tab=leaderboards"),
    ("prospx-draft", "/prospx/index.html#tab=draft"),
    ("prospx-ifa", "/prospx/index.html#tab=ifa"),
    ("prospx-overseas", "/prospx/index.html#tab=overseas"),
    ("prospx-watchlist", "/prospx/index.html#tab=watchlist"),
    ("projections", "/projections/index.html"),
    ("projections-player", "/projections/index.html#player=paul_skenes"),
    ("fa", "/fa/index.html"),
    ("mlbstats", "/mlbstats/index.html"),
    ("pal", "/pal/index.html"),
    ("trademachine", "/trademachine/index.html"),
    ("glossary", "/glossary/index.html"),
    ("collegesavant", "/collegesavant/index.html"),
    ("collegesavant-pit", "/collegesavant/pitcher_index.html"),
    ("news", "/news/index.html"),
    ("forums", "/forums/index.html"),
    ("sources", "/sources/index.html"),
    ("team", "/team/index.html"),
    ("player-router", "/player/index.html"),
    ("notfound", "/404.html"),
]

DEFAULT_VIEWPORTS = [375, 768, 1280, 1440]
DEFAULT_THEMES = ["light", "dark"]

# Probe run in-page after load: horizontal bleed + any element wider than the
# viewport + a couple of known-fragile selectors overflowing their own box.
PROBE = r"""
() => {
  const de = document.documentElement;
  const vw = window.innerWidth;
  const bleed = de.scrollWidth > vw + 1;
  // widest offending element (helps localize a bleed)
  let worst = null, worstW = vw + 1;
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width > worstW && r.right > vw + 1 && r.left >= -1) {
      worstW = r.width;
      worst = (el.tagName.toLowerCase() + '.' + (el.className || '').toString().trim().replace(/\s+/g, '.')).slice(0, 60);
    }
  }
  // flagged fragile containers overflowing their own scroll box
  const clipped = [];
  for (const sel of ['.tool-grade-strip', '.mlbp-slider', '.tm-board', '.player-meta', '.card-tile-grid']) {
    for (const el of document.querySelectorAll(sel)) {
      if (el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflowX === 'hidden') {
        clipped.push(sel); break;
      }
    }
  }
  return { bleed, scrollW: de.scrollWidth, vw, worst, clipped };
}
"""


def _serve():
    class _H(http.server.SimpleHTTPRequestHandler):
        # HTTP/1.1, not the stdlib HTTP/1.0 default. Under 1.0 the server marks
        # end-of-body by CLOSING the socket, and on Windows that close races the
        # send buffer: a large asset (assets/site.css is 211KB) can lose its tail,
        # so the browser waits on bytes that never arrive. In a TEST that showed
        # up as a goto timeout; HERE it would be worse, because a sweep whose CSS
        # truncated still SCREENSHOTS, and an unstyled page is a plausible-looking
        # image rather than an error. Content-Length framing removes the race.
        # Measured 2026-08-04, same file: HTTP/1.0 hangs to 12s, HTTP/1.1 0.02s.
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # noqa: A002 (matches stdlib sig)
            pass

    handler = functools.partial(_H, directory=ROOT)

    class Quiet(socketserver.ThreadingTCPServer):
        # Threading is REQUIRED once keep-alive is on: a browser opens several
        # parallel connections per page and a single-threaded server deadlocks.
        allow_reuse_address = True
        daemon_threads = True

    httpd = Quiet(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def run(out_dir, route_filter=None, viewports=None, themes=None):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        print(f"playwright unavailable: {e}", file=sys.stderr)
        return 2
    viewports = viewports or DEFAULT_VIEWPORTS
    themes = themes or DEFAULT_THEMES
    routes = [r for r in ROUTES if (not route_filter or route_filter in r[0])]
    os.makedirs(out_dir, exist_ok=True)
    httpd, port = _serve()
    base = f"http://127.0.0.1:{port}"
    findings = []
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as e:  # noqa: BLE001
                print(f"chromium unavailable: {e}", file=sys.stderr)
                return 2
            for theme in themes:
                for vw in viewports:
                    ctx = browser.new_context(
                        viewport={"width": vw, "height": 900},
                        color_scheme=("dark" if theme == "dark" else "light"),
                    )
                    # stamp the app's own theme attribute before any script runs
                    ctx.add_init_script(
                        f"try{{localStorage.setItem('eephus-theme','{theme}');}}catch(e){{}}"
                    )
                    for rid, path in routes:
                        page = ctx.new_page()
                        errs, cons = [], []
                        page.on("pageerror", lambda e: errs.append(str(e)))
                        page.on("console", lambda m: cons.append(m.text) if m.type == "error" else None)
                        try:
                            page.goto(base + path, wait_until="networkidle", timeout=45000)
                        except Exception as e:  # noqa: BLE001
                            errs.append(f"GOTO: {e}")
                        page.wait_for_timeout(1800)  # async re-render + starfield settle
                        try:
                            page.evaluate(f"document.documentElement.setAttribute('data-theme','{theme}')")
                            page.wait_for_timeout(300)
                        except Exception:  # noqa: BLE001
                            pass
                        try:
                            probe = page.evaluate(PROBE)
                        except Exception as e:  # noqa: BLE001
                            probe = {"bleed": None, "error": str(e)}
                        shot = f"{rid}__{theme}__{vw}.png"
                        try:
                            page.screenshot(path=os.path.join(out_dir, shot), full_page=False)
                        except Exception:  # noqa: BLE001
                            shot = None
                        rec = {
                            "route": rid, "theme": theme, "vw": vw,
                            "pageerrors": errs[:5], "console_errors": cons[:5],
                            "bleed": probe.get("bleed"), "worst": probe.get("worst"),
                            "clipped": probe.get("clipped"), "shot": shot,
                        }
                        findings.append(rec)
                        flag = ""
                        if errs:
                            flag += f" PAGEERR({len(errs)})"
                        if probe.get("bleed"):
                            flag += f" BLEED->{probe.get('worst')}"
                        if probe.get("clipped"):
                            flag += f" CLIP{probe.get('clipped')}"
                        if cons:
                            flag += f" CONSOLE({len(cons)})"
                        print(f"  {rid:22} {theme:5} {vw:>5}px{flag or '  ok'}")
                        page.close()
                    ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=1)
    p0 = [f for f in findings if f["pageerrors"]]
    p1 = [f for f in findings if f["bleed"] or f["clipped"]]
    print(f"\n=== SWEEP DONE: {len(findings)} cells ===")
    print(f"P0 pageerrors: {len(p0)} cells -> {sorted({f['route'] for f in p0})}")
    print(f"P1 bleed/clip: {len(p1)} cells -> {sorted({f['route'] for f in p1})}")
    print(f"screenshots + report.json in {out_dir}")
    return 1 if (p0 or p1) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "eephus_sweep"))
    ap.add_argument("--routes", default=None, help="substring filter on route id")
    ap.add_argument("--viewports", default=None, help="comma list, e.g. 375,1280")
    ap.add_argument("--themes", default=None, help="comma list: light,dark")
    a = ap.parse_args()
    vps = [int(x) for x in a.viewports.split(",")] if a.viewports else None
    ths = a.themes.split(",") if a.themes else None
    sys.exit(run(a.out, a.routes, vps, ths))


if __name__ == "__main__":
    main()
