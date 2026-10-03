# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PX_LOGO_ANIMATION (owner ask 2026-10-02: "The eephus.io logo animation on
the homepage is still showing the old animation instead of the new one"): the
homepage plays the pixel pitch, and the old vector draw-on is gone.

The motion is the bundle's (Part 8 pixel_branding 3.5, owner answer PB-Q4,
built by tools/pixel_brand.py into assets/brand/wordmark.css): the arc lights
run by run, left to right, in whole-pixel steps (step-end, so no pixel ever
sits between two positions), then the ball (the mark's accent) drops onto the
apex in four whole-pixel frames, all inside 0.9 s; one glint follows once per
page view. It plays once on load on the hero only, replays on hover (and on
keyboard focus of the brand link) on every wordmark, never loops, and runs
under Reduce Motion like every animation on the site (owner, 2026-10-01).

Static: no served page, stylesheet or script names the retired draw-on
keyframes, the vector arc or ball, or the standalone arc mark (no allowlist).

In headless Chromium over the served site: the hero's animation-name resolves
to the new keyframes with the timing above at 1280 and 390, it runs once and
settles, hover and focus replay it, leaving starts nothing; and the final frame
of the pitch is pixel-identical to the static lockup (the same page with every
animation off) and to the committed PNG strike of the same fragment.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_pixel_brand_motion.py)."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

import build_site as B
from conftest import serve_site

ROOT = Path(__file__).parent
BRAND = ROOT / "assets" / "brand"
PIXEL = ROOT / "branding" / "pixel"

# Everything the old vector mark and its draw-on were made of: the four
# keyframes (ew-arc-draw, ew-ball-settle, ew-arc-redraw, ew-ball-resettle), the
# arc and ball SVG classes, the lockup and animate classes, the ball fills, the
# per-instance gradient ids (eephus-arc-nav, -sb, -mast, -pxnav, -csnav) and the
# standalone animated mark branding/animated/eephus-arc.svg.
RETIRED = re.compile(
    r"\bew-(?:arc|ball)|eephus-wordmark-merged|eephus-logo--animate|"
    r"eephus-logo-(?:ball|seam)|eephus-arc\b")

# The pitch must be over inside this (the spec's 0.9 s).
PITCH_MS = 900


def _served_files():
    """Every file the deploy ships that can carry markup, style or script: the
    root pages plus every .html/.css/.js under the directories
    deploy/publish_paths.txt lists (data/ ships separately and holds none)."""
    out = []
    for line in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = ROOT / line
        if p.is_file() and p.suffix in (".html", ".css", ".js"):
            out.append(p)
        elif p.is_dir():
            out += [f for f in p.rglob("*") if f.is_file() and f.suffix in (".html", ".css", ".js")]
    return out


def test_no_served_file_references_the_retired_draw_on_or_arc_mark():
    files = _served_files()
    names = {f.relative_to(ROOT).as_posix() for f in files}
    # The scan reaches the surfaces the old mark lived on.
    for rel in ("index.html", "404.html", "ledger/index.html", "prospx/index.html",
                "collegesavant/index.html", "collegesavant/pitcher_index.html", "assets/site.css"):
        assert rel in names, rel
    hits = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in RETIRED.finditer(text):
            hits.append(f"{f.relative_to(ROOT).as_posix()}: {m.group(0)}")
    assert not hits, hits[:20]
    # branding/animated/eephus-arc.svg is now the pixel pitch (PB-09), export art
    # off the publish manifest; the retired vector draw-on must not come back there.
    arc = (ROOT / "branding" / "animated" / "eephus-arc.svg").read_text(encoding="utf-8")
    assert not re.search(r"ew-(?:arc|ball)|eephus-logo-(?:ball|seam)", arc)


def test_every_wordmark_builds_as_the_pixel_lockup_under_either_flag(monkeypatch):
    for flag in (False, True):
        monkeypatch.setattr(B, "PIXEL_BRAND", flag)
        for uid, tag in (("nav", "span"), ("sb", "span"), ("mast", "h1")):
            mark = B.eephus_merged_wordmark(uid, tag=tag)
            assert mark.startswith(f'<{tag} class="nameplate eephus-wordmark-px"><svg class="wm-px')
            assert not RETIRED.search(mark), mark[:120]
        lockup = B.eephus_logo_lockup()
        assert lockup.startswith('<div class="eephus-logo"><h1 class="nameplate eephus-wordmark-px">')
        assert "wm-px--play" in lockup


def _vars(svg: str) -> dict:
    style = re.search(r'style="([^"]+)"', svg).group(1)
    return dict(kv.split(":") for kv in style.split(";"))


@pytest.mark.parametrize("scale", [6, 4, 2])
def test_the_fragment_timeline_fits_the_spec(scale):
    """Per fragment: the runs light at i * step, the ball drops after the last
    run, and the drop (240 ms) ends inside 0.9 s."""
    svg = (BRAND / f"wordmark-s{scale}.svg").read_text(encoding="utf-8")
    v = _vars(svg)
    step, drop = int(v["--step"].rstrip("ms")), int(v["--drop-at"].rstrip("ms"))
    runs = [int(i) for i in re.findall(r'class="wm-s" style="--i:(\d+)"', svg)]
    assert runs == list(range(len(runs))) and len(runs) >= 8, runs
    last_run_at = runs[-1] * step + 1
    assert last_run_at < drop, (last_run_at, drop)
    assert drop + 240 <= PITCH_MS, drop
    # Only the hero fragments play on load; the nav and sidebar mark replay only.
    assert ("wm-px--play" in svg) == (scale in (6, 4))


# ------------------------------------------------------------------ browser
_RUNNING_JS = r"""() => document.getAnimations()
  .filter(a => a.animationName && /^(ew|wm)-/.test(a.animationName) && a.playState === 'running')
  .map(a => a.animationName)"""

# The hero's computed animation on every lit piece, from the shown fragment.
_HERO_JS = r"""() => {
  const svg = [...document.querySelectorAll('.masthead svg.wm-px')]
    .find(s => s.getBoundingClientRect().width > 0);
  const cs = el => getComputedStyle(el);
  const runs = [...svg.querySelectorAll('.wm-s')].map(el => {
    const c = cs(el);
    return {name: c.animationName, fn: c.animationTimingFunction, dur: c.animationDuration,
            delay: c.animationDelay, n: c.animationIterationCount, fill: c.animationFillMode};
  });
  const b = cs(svg.querySelector('.wm-ball'));
  const anims = document.getAnimations().filter(a => /^wm-/.test(a.animationName));
  const ends = anims.filter(a => a.animationName !== 'wm-flash').map(a => {
    const t = a.effect.getComputedTiming(); return t.delay + t.activeDuration; });
  const kf = anims.map(a => a.effect.getKeyframes().map(k => k.easing));
  return {width: svg.getAttribute('width'), runs,
          ball: {name: b.animationName, fn: b.animationTimingFunction, dur: b.animationDuration,
                 delay: b.animationDelay, n: b.animationIterationCount},
          step: parseFloat(getComputedStyle(svg).getPropertyValue('--step')),
          end: Math.max(...ends), iterations: [...new Set(anims.map(a => a.effect.getTiming().iterations))],
          easings: [...new Set(kf.flat())]};
}"""

_STEP_END = {"step-end", "steps(1, end)", "steps(1)"}

# A page with only the fragment on it, as tools/pixel_brand.py's strikes were
# drawn (no masthead glow, transparent background).
_ISOLATED = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/assets/site.css">
<style>body{margin:0;background:transparent!important} #eephus-bg{display:none!important}
.box{position:absolute;left:10px;top:10px}{extra}</style></head>
<body><div class="box"><span class="nameplate eephus-wordmark-px" id="wm">{frag}<span class="wm-txt">eephus.io</span></span></div></body></html>"""
_STILL = "\n.wm-px, .wm-px * { animation: none !important; }"


def _png(raw: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(raw)).convert("RGBA")


def _pixels_off(a, b) -> int:
    if a.size != b.size:
        return -1
    return sum(1 for p, q in zip(a.getdata(), b.getdata()) if p != q)


@pytest.fixture(scope="module")
def runs():
    pytest.importorskip("playwright.sync_api")
    pytest.importorskip("PIL")
    from playwright.sync_api import sync_playwright

    out: dict = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")

        for width in (1280, 390):
            for rm in ("no-preference", "reduce"):
                ctx = browser.new_context(viewport={"width": width, "height": 900}, reduced_motion=rm)
                page = ctx.new_page()
                page.goto(base + "index.html", wait_until="load", timeout=30_000)
                out[f"hero_{width}_{rm}"] = page.evaluate(_HERO_JS)
                out[f"at_load_{width}_{rm}"] = page.evaluate(_RUNNING_JS)
                page.wait_for_timeout(3300)
                out[f"settled_{width}_{rm}"] = page.evaluate(_RUNNING_JS)
                if width == 1280 and rm == "no-preference":
                    # Final frame on the served page against the same page with
                    # every wordmark animation switched off.
                    page.evaluate("document.fonts.ready")
                    # The starfield canvas twinkles behind the hero in every
                    # theme; hide it so only the mark is compared.
                    page.add_style_tag(content="#eephus-bg { display: none !important; }")
                    for theme in ("light", "dark"):
                        page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
                        page.wait_for_timeout(100)
                        loc = page.locator(".masthead .eephus-wordmark-px")
                        final = loc.screenshot()
                        page.add_style_tag(content=_STILL)
                        page.wait_for_timeout(100)
                        still = loc.screenshot()
                        out[f"final_vs_still_{theme}"] = _pixels_off(_png(final), _png(still))
                        page.evaluate("document.querySelectorAll('style').forEach(s => "
                                      "{ if (s.textContent.includes('animation: none !important')) s.remove(); })")
                        # Lifting the override restarts the one-shot; let it end.
                        page.wait_for_timeout(3300)
                    page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
                    box = page.locator(".masthead .nameplate").first.bounding_box()
                    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.wait_for_timeout(80)
                    out["hero_hover"] = page.evaluate(_RUNNING_JS)
                    page.wait_for_timeout(1400)
                    page.mouse.move(2, 2)
                    page.wait_for_timeout(80)
                    out["hero_leave"] = page.evaluate(_RUNNING_JS)
                ctx.close()

        # The nav lockup: static on load, replays on hover and on keyboard focus.
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(base + "ledger/index.html", wait_until="load", timeout=30_000)
        out["nav_load"] = page.evaluate(_RUNNING_JS)
        for _ in range(12):
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement && document.activeElement.matches('a.eephus-wordmark')"):
                break
        page.wait_for_timeout(60)
        out["nav_focus"] = page.evaluate(_RUNNING_JS)
        page.wait_for_timeout(1400)
        page.keyboard.press("Tab")
        page.wait_for_timeout(80)
        out["nav_blur"] = page.evaluate(_RUNNING_JS)
        ctx.close()

        # Each fragment alone: its final frame equals the committed PNG strike
        # and the same fragment with every animation off.
        for scale in (6, 4, 2):
            frag = (BRAND / f"wordmark-s{scale}.svg").read_text(encoding="utf-8").strip()
            for theme in ("light", "dark"):
                shots = {}
                for kind, extra in (("final", ""), ("still", _STILL)):
                    ctx = browser.new_context(viewport={"width": 520, "height": 220})
                    page = ctx.new_page()
                    body = _ISOLATED.replace("{extra}", extra).replace("{frag}", frag)
                    page.route(base + "__px_logo.html", lambda route, _req, b=body: route.fulfill(
                        status=200, content_type="text/html; charset=utf-8", body=b))
                    page.goto(base + "__px_logo.html", wait_until="load", timeout=30_000)
                    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
                    # The still page has nothing to wait for; the played one ends by 2.7 s.
                    page.wait_for_timeout(3300 if kind == "final" else 100)
                    box = page.locator("#wm svg").bounding_box()
                    shots[kind] = _png(page.screenshot(clip=box, omit_background=True))
                    ctx.close()
                strike = _png(((PIXEL if scale == 6 else BRAND) / f"wordmark-s{scale}-{theme}.png").read_bytes())
                out[f"iso_s{scale}_{theme}"] = (_pixels_off(shots["final"], shots["still"]),
                                                _pixels_off(shots["final"], strike))
        browser.close()
    return out


@pytest.mark.parametrize("rm", ["no-preference", "reduce"])
@pytest.mark.parametrize("width,shown", [(1280, "330"), (390, "220")])
def test_hero_animation_name_resolves_to_the_pixel_keyframes(runs, width, shown, rm):
    h = runs[f"hero_{width}_{rm}"]
    assert h["width"] == shown
    names = {r["name"] for r in h["runs"]}
    assert names == {"wm-on"}, names
    assert h["ball"]["name"] == "wm-drop"


@pytest.mark.parametrize("rm", ["no-preference", "reduce"])
@pytest.mark.parametrize("width", [1280, 390])
def test_hero_timing_is_whole_pixel_steps_inside_the_spec(runs, width, rm):
    h = runs[f"hero_{width}_{rm}"]
    for i, r in enumerate(h["runs"]):
        assert r["fn"] in _STEP_END, r
        assert r["n"] == "1" and r["dur"] == "0.001s" and r["fill"] == "backwards", r
        # Run i lights at i * step: left to right, one run per step.
        assert float(r["delay"].rstrip("s")) * 1000 == pytest.approx(i * h["step"], abs=0.5), (i, r)
    assert h["ball"]["fn"] in _STEP_END and h["ball"]["n"] == "1" and h["ball"]["dur"] == "0.24s"
    # The accent (the ball) lights last, and the pitch is over inside 0.9 s.
    last_run = (len(h["runs"]) - 1) * h["step"]
    assert float(h["ball"]["delay"].rstrip("s")) * 1000 > last_run
    assert h["end"] <= PITCH_MS, h["end"]
    # Every keyframe step is step-end and nothing loops.
    assert set(h["easings"]) <= _STEP_END, h["easings"]
    assert h["iterations"] == [1], h["iterations"]


@pytest.mark.parametrize("rm", ["no-preference", "reduce"])
@pytest.mark.parametrize("width", [1280, 390])
def test_the_pitch_runs_once_on_load_under_either_motion_setting(runs, width, rm):
    assert "wm-on" in runs[f"at_load_{width}_{rm}"]
    assert runs[f"settled_{width}_{rm}"] == []


def test_hover_replays_and_leaving_starts_nothing(runs):
    assert "wm-on-h" in runs["hero_hover"] and "wm-drop-h" in runs["hero_hover"]
    assert runs["hero_leave"] == []


def test_the_nav_mark_is_still_on_load_and_replays_on_keyboard_focus(runs):
    assert runs["nav_load"] == []
    assert "wm-on-h" in runs["nav_focus"]
    assert runs["nav_blur"] == []


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_final_frame_is_the_static_lockup_on_the_homepage(runs, theme):
    assert runs[f"final_vs_still_{theme}"] == 0


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("scale", [6, 4, 2])
def test_the_final_frame_equals_the_committed_strike(runs, scale, theme):
    vs_still, vs_strike = runs[f"iso_s{scale}_{theme}"]
    assert vs_still == 0
    assert vs_strike == 0
