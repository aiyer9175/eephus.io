# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""HOME_7 pixel signals (site-pass plan 4.4, LANE_HOME 4): every piece
carries a reading, draws whole pixels in theme tokens, and moves only as a
CSS steps animation; script only toggles a class.

  PA1  five 6 x 6 family lamps in the rail head, lit (and blinking with
       ticker-blip, 1.4 s step-end) for a family with a row dated yesterday or
       today, the unlit var(--border-light) lamp and still otherwise; the
       counts are the title and the hidden text;
  PA2  the unread bar on rows dated after the newest row seen last visit
       (localStorage eephus.news.seen, every access in try/catch): 2 px in the
       family colour, two blinks (0.8 s, steps(1), 2 iterations), then lit;
  PA3  32 px band marks, static: ev-mlb; i-prospx with i-collegesavant;
  PA4  the callout lamp countdown, one 4 x 4 lamp per day left up to 45,
       today's lamp blinking;
  PA5  the phone jump bar lamp under the band in view, moved by a class;
  PA6  the On This Day calendar, static: 16 px with the day number beside it
       on the module card, 32 px with the number inside on /history/;
  PA7  the family empty and unmeasured states through _px_state and
       EephusState.

The browser half reads the SERVED pages in headless Chromium (conftest
serve_site) with Reduce Motion emulated and not: each animated piece reports
its animation name, duration, steps timing and iteration count, and two
frames 400 ms apart differ (the animation seeked, so the check never races a
blink); PA3 and PA6 run no animation. Playwright is optional; the browser
tests skip cleanly without it.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
MODES = ("reduce", "no-preference")


def _served(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- build side

def test_pa1_lamps_light_only_families_with_a_recent_row():
    today = date(2026, 10, 9)
    ev = [("2026-10-09", "trade", "", "", "k", "NYY", "A", "trade"),
          ("2026-10-08", "il_place", "", "", "k", "NYY", "B", "IL"),
          ("2026-10-08", "il_place", "", "", "k", "NYY", "C", "IL"),
          ("2026-10-07", "fa_sign", "", "", "k", "NYY", "D", "MLB deal")]
    out = B._fam_lamps_html(ev, today)
    lamps = re.findall(r'<i class="fam-lamp( is-lit)?" data-fam="(\w+)"></i>', out)
    assert [f for _l, f in lamps] == list(B._WIRE_FAMILIES)
    assert {f for lit, f in lamps if lit} == {"trd", "inj"}
    txt = "Rows dated Oct 8 or later: Prospects 0, MLB 0, Free agency 0, Trades 1, Injuries 2"
    assert f'title="{txt}"' in out and f'<span class="visually-hidden">{txt}. </span>' in out


def test_pa1_the_rail_head_carries_the_lamps_not_the_green_blip():
    home = _served("index.html")
    head = home.split('<div class="feed-head">', 1)[1].split("</div>", 1)[0]
    assert len(re.findall(r'<i class="fam-lamp(?: is-lit)?" data-fam="\w+"></i>', head)) == 5
    assert '<span class="blip">' not in head
    assert ".sb-feed .feed-head .blip" not in CSS
    assert re.search(r"\.sb-feed \.fam-lamp \{[^}]*background: var\(--border-light\)", CSS)
    assert re.search(r"\.sb-feed \.fam-lamp\.is-lit \{[^}]*animation: ticker-blip 1\.4s step-end infinite", CSS)


def test_pa2_the_unread_script_is_on_the_rail_and_news_and_guards_storage():
    js = B._WIRE_UNREAD_JS
    for rel in ("index.html", "news/index.html"):
        assert js in _served(rel), rel
    assert "eephus.news.seen" in js and "requestAnimationFrame" not in js
    # every storage access sits in a try
    assert js.count("localStorage") == 2 and js.count("try {") == 2
    assert re.search(r'<div class="feed-day" data-day="\d{4}-\d{2}-\d{2}">', _served("index.html"))
    assert re.search(r"\.feed-item\.is-unread \{[^}]*animation: wire-unread \.8s steps\(1\) 2", CSS)


def test_pa3_band_marks_are_the_plan_s_and_static():
    home = _served("index.html")
    for band, syms in (("mlb", ["ev-mlb"]), ("pro", ["prospx", "collegesavant"])):
        head = home.split(f'<section class="home-band home-band--{band}"', 1)[1].split("</span>", 1)[0]
        assert re.findall(r'width="32" height="32"[^>]*><use href="[^"#]*#i-([\w-]+)"', head) == syms, band
    assert not re.search(r"\.band-mark[^{]*\{[^}]*animation", CSS)


def test_pa4_the_countdown_has_one_lamp_per_day_left_up_to_45():
    for n in (1, 15, 23, 45, 80):
        svg = B._cal_lamps_svg(n)
        lamps = re.findall(r"M\d+ \d+h4v4h-4z", svg)
        assert len(lamps) == min(n, 45), n
        assert len(re.findall(r'<path class="cl-today" d="M0 0h4v4h-4z"/>', svg)) == 1
        assert len(svg.encode()) < 8192
    out = B._date_callout("pro", date(2026, 10, 9))
    assert "in 23 days" in out and len(re.findall(r"M\d+ \d+h4v4h-4z", out)) == 23
    live = B._date_callout("pro", date(2026, 11, 3))
    assert "Underway" in live and len(re.findall(r"M\d+ \d+h4v4h-4z", live)) == 30
    assert '<path class="cl-today" d="M12 0h4v4h-4z"/>' in live, "today is the third day of the run"
    assert re.search(r"\.home-callout \.cal-lamps \.cl-today \{[^}]*animation: ticker-blip 1\.4s step-end infinite", CSS)


def test_pa5_the_jump_bar_marks_the_first_band_and_only_toggles_a_class():
    home = _served("index.html")
    nav = re.search(r'<nav class="home-jump"[^>]*>(.*?)</nav>', home, re.S).group(1)
    assert re.findall(r'<a href="#band-(\w+)"( class="is-here")?>', nav) == [("mlb", ' class="is-here"'), ("pro", "")]
    js = B._HOME_JUMP_JS
    assert js in home and "IntersectionObserver" in js and "classList.toggle(\"is-here\"" in js
    assert "requestAnimationFrame" not in js and ".style." not in js


def test_pa6_the_calendar_marks_today():
    today = date.today()
    hist = _served("history/index.html")
    assert f'<div class="section-head hist-cal" style="--cal-day:&quot;{today.day}&quot;">' in hist
    out = B._this_day_html([{"player_name": "X", "player_key": "x", "debut_date": f"{today.year - 3}-{today:%m-%d}",
                             "fv_close": 50}], [])
    assert f'<span class="otd-cal-day">{today.day}</span>' in out
    assert re.search(r'<span class="otd-cal" aria-hidden="true"><svg class="ico" width="16"[^>]*><use href="[^"]*#i-history"', out)
    assert not re.search(r"\.(otd-cal|hist-cal)[^{]*\{[^}]*animation", CSS)


def test_pa7_states_go_through_the_pixel_component():
    home = _served("index.html")
    assert re.search(r'<div class="wire-state" id="wire-empty" hidden><div class="px-state is-empty">', home)
    assert '<p class="news-empty" id="wire-empty"' not in home
    assert "EephusState" in B._NEWS_FILTER_JS and "news-stale" in B._NEWS_FILTER_JS
    assert 'id="news-stale"' in B._wire_stale_html("stale", "news-stale")


# ---------------------------------------------------------------- browser side

_ANIM = r"""
([sel, pseudo]) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const cs = getComputedStyle(el, pseudo || null);
  return {name: cs.animationName, duration: cs.animationDuration,
          timing: cs.animationTimingFunction, count: cs.animationIterationCount};
}
"""

# Seek the element's own animation to t1 and t2 (ms) and read the property
# the frame changes; the two readings must differ.
_FRAMES = r"""
([sel, pseudo, prop, t1, t2]) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const anims = document.getAnimations().filter((a) => a.effect && a.effect.target === el
    && ((a.effect.pseudoElement || null) === (pseudo || null)));
  if (!anims.length) return null;
  const read = (t) => { anims.forEach((a) => { a.pause(); a.currentTime = t; });
    return getComputedStyle(el, pseudo || null)[prop]; };
  return [read(t1), read(t2)];
}
"""

_STATIC = r"""
(sel) => Array.from(document.querySelectorAll(sel)).reduce((n, el) =>
  n + el.getAnimations({subtree: true}).length
  + (getComputedStyle(el, '::before').animationName !== 'none' ? 1 : 0), 0)
"""

PIECES = {  # piece -> (page, width, selector, pseudo, property, t1, t2, expected animation)
    "PA1": ("", 1280, ".sb-feed .fam-lamp.is-lit", None, "opacity", 500, 900,
            {"name": "ticker-blip", "duration": "1.4s", "timing": "steps(1)", "count": "infinite"}),
    "PA2": ("", 1280, "#wire-rows .feed-item.is-unread", None, "boxShadow", 200, 600,
            {"name": "wire-unread", "duration": "0.8s", "timing": "steps(1)", "count": "2"}),
    "PA4": ("", 1280, ".home-callout .cal-lamps .cl-today", None, "opacity", 500, 900,
            {"name": "ticker-blip", "duration": "1.4s", "timing": "steps(1)", "count": "infinite"}),
    "PA5": ("", 390, ".home-jump a.is-here", "::after", "opacity", 500, 900,
            {"name": "ticker-blip", "duration": "1.4s", "timing": "steps(1)", "count": "infinite"}),
}


@pytest.fixture(scope="module")
def measured():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site

    out: dict = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        for mode in MODES:
            res: dict = {}
            for width in (1280, 390):
                ctx = browser.new_context(reduced_motion=mode, viewport={"width": width, "height": 900})
                # A reader whose last visit saw rows through 2000-01-01: every row is unread.
                ctx.add_init_script("try{localStorage.setItem('eephus.news.seen','2000-01-01')}catch(e){}")
                page = ctx.new_page()
                errors: list = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(base, wait_until="load", timeout=60_000)
                page.wait_for_timeout(300)
                # PA1 reads the build day's rows: when no family has a row dated
                # yesterday or today, light the first lamp to read the CSS.
                res[f"lit_{width}"] = page.evaluate("document.querySelectorAll('.sb-feed .fam-lamp.is-lit').length")
                page.evaluate("(() => { if (!document.querySelector('.sb-feed .fam-lamp.is-lit')) "
                              "document.querySelector('.sb-feed .fam-lamp').classList.add('is-lit'); })()")
                page.wait_for_timeout(100)
                for piece, (_pg, w, sel, pseudo, prop, t1, t2, _want) in PIECES.items():
                    if w != width:
                        continue
                    res[piece] = {"anim": page.evaluate(_ANIM, [sel, pseudo]),
                                  "frames": page.evaluate(_FRAMES, [sel, pseudo, prop, t1, t2])}
                res[f"static_{width}"] = page.evaluate(_STATIC, ".band-mark, .otd-cal")
                res[f"errors_{width}"] = errors
                ctx.close()
            ctx = browser.new_context(reduced_motion=mode, viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            page.goto(base + "history/", wait_until="load", timeout=60_000)
            res["hist_static"] = page.evaluate(_STATIC, ".hist-cal")
            res["hist_day"] = page.evaluate("getComputedStyle(document.querySelector('.hist-cal h1'), '::before').content")
            ctx.close()
            # A first visit draws no bar and writes the key; storage that throws draws none and no error.
            ctx = browser.new_context(reduced_motion=mode, viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            page.goto(base, wait_until="load", timeout=60_000)
            res["first_visit"] = page.evaluate("[document.querySelectorAll('.feed-item.is-unread').length,"
                                               " localStorage.getItem('eephus.news.seen')]")
            ctx.close()
            ctx = browser.new_context(reduced_motion=mode, viewport={"width": 1280, "height": 900})
            ctx.add_init_script("Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "news/", wait_until="load", timeout=60_000)
            res["blocked"] = [page.evaluate("document.querySelectorAll('.feed-item.is-unread').length"), errors]
            ctx.close()
            out[mode] = res
        browser.close()
    return out


@pytest.mark.parametrize("piece", sorted(PIECES))
def test_each_animated_piece_steps_and_its_frames_differ(measured, piece):
    want = PIECES[piece][-1]
    for mode in MODES:
        got = measured[mode][piece]
        assert got["anim"] == want, (mode, piece, got)
        a, b = got["frames"]
        assert a != b, (mode, piece, got["frames"])


def test_reduce_motion_changes_nothing(measured):
    strip = lambda r: {k: v for k, v in r.items() if k != "blocked"}  # noqa: E731
    assert strip(measured["reduce"]) == strip(measured["no-preference"])


def test_pa3_and_pa6_run_no_animation_and_the_masthead_prints_the_day(measured):
    for mode in MODES:
        r = measured[mode]
        assert r["static_1280"] == 0 and r["static_390"] == 0 and r["hist_static"] == 0, (mode, r)
        assert r["hist_day"].startswith(f'"{date.today().day}"'), r["hist_day"]


def test_pa2_first_visit_and_blocked_storage_draw_no_bar(measured):
    for mode in MODES:
        n, seen = measured[mode]["first_visit"]
        assert n == 0 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", seen or ""), measured[mode]["first_visit"]
        assert measured[mode]["blocked"] == [0, []]


def test_no_page_error(measured):
    for mode in MODES:
        assert measured[mode]["errors_1280"] == [] and measured[mode]["errors_390"] == []
