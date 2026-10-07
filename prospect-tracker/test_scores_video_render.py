# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /scores/ video chunk (SCORES_4a_VIDEO; plan 6.3 to 6.5, 8.1, 12) in
headless Chromium on fixture payloads, behind scores_core.SCORES_LIVE.

THE SITE UNDER TEST is test_scores_render's temporary copy, with the final
849845 built from the trimmed content fixture (plus a pickoff attempt clip)
and the live 849846 from its live content read. Every request to *.mlb.com,
img.mlbstatic.com or streamable.com is answered with fixture bytes and
logged; anything else off loopback is aborted. Nothing here reads or writes
the repo's data/ or a real .cache/scores/.

WHAT IS PINNED, branch (a) (MLB's embed player): before a click no iframe
exists and no frame or media request is made, posters are lazy and at most
six per game, "Video: MLB" sits under every poster; a click, Enter or Space
gives one iframe with the allowlisted src, the title "MLB video: ...", the
allow list, referrerpolicy and MLB's story-player sandbox list, inside a
figure with "Video: MLB" and "Close video"; a second clip removes the first
frame; Escape and Close remove it and return focus to the button; the switch
off renders links only; an open frame survives a poll that reorders Biggest
plays and the notice offers the new list; the Plays tab labels an earlier
event's clip by its own event; star rows carry a compact button and no link;
the Video panel holds the recap and the condensed game; rows with no clip say
so with the Gameday link; the chunk loads only once a game view opens; no
horizontal page scroll with a frame open and no console errors.
"""
from __future__ import annotations

import base64
import copy
import json
import re
from contextlib import contextmanager
from pathlib import Path

import pytest

import build_site
import scores_core as sc
from conftest import serve_site
from test_scores_clips import content_with, pickoff_item
from test_scores_render import TODAY, build_payloads, make_site, pw, write_payloads  # noqa: F401

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "scores"
VIDEO_JS_RAW = 20 * 1024        # plan 8.1: assets/scores-video.js, the lazy chunk
SANDBOX = ("allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms "
           "allow-modals allow-pointer-lock allow-top-navigation-by-user-activation")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HJxCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
MEDIA_HOSTS = re.compile(r"^https://([a-z0-9-]+\.)*(mlb\.com|mlbstatic\.com|streamable\.com)/", re.I)


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def build_video_payloads(*, embed=True, pending=False) -> dict:
    """test_scores_render's payloads with clips: 849845 from its content
    fixture plus a pickoff attempt clip, 849846 from its live read."""
    real = sc.build_game_file
    contents = {849845: content_with("content_849845.json", extra=[pickoff_item()]),
                849846: _load("content_849846_live.json")}

    def with_content(game, wp, box, lg, **kw):
        pk = int(game.get("gamePk"))
        if pk in contents:
            kw.setdefault("content", contents[pk])
            kw.setdefault("seen_at", kw.get("generated_at"))
            if pk == 849845:
                kw.setdefault("clips_pending", pending)
        return real(game, wp, box, lg, **kw)

    sc.build_game_file = with_content
    try:
        p = build_payloads()
    finally:
        sc.build_game_file = real
    p["index.json"]["rules"]["video"].update(embed=embed, branch=sc.VIDEO_BRANCH)
    p["latest.json"]["index_rev"] = sc.rev_of(p["index.json"])
    return p


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return make_site(tmp_path_factory.mktemp("scores_video_site"), build_video_payloads())


@contextmanager
def video_page(base: str, pw, *, width=390, theme="light", hash_="", clock=False):
    """A page whose MLB, poster and frame requests get fixture bytes and are
    logged on page._media; everything else off loopback is aborted."""
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme)
    page = ctx.new_page()
    page._errors, page._requests, page._media = [], [], []

    def route(r):
        url = r.request.url
        if url.startswith(base[:-1]):
            return r.continue_()
        if MEDIA_HOSTS.match(url):
            page._media.append(url)
            if "img.mlbstatic.com" in url:
                return r.fulfill(status=200, content_type="image/png", body=PNG)
            return r.fulfill(status=200, content_type="text/html",
                             body="<!doctype html><title>fixture player</title><p>MLB player fixture</p>")
        return r.abort()

    page.route("**/*", route)
    page.on("request", lambda r: page._requests.append(r.url))
    page.on("console", lambda m: page._errors.append(m.text) if m.type == "error" and
            "net::ERR_FAILED" not in m.text and "ERR_BLOCKED" not in m.text else None)
    page.on("pageerror", lambda e: page._errors.append(str(e)))
    if clock:
        page.clock.install()
    try:
        page.goto(base + "scores/" + hash_, wait_until="load")
        yield page
    finally:
        browser.close()


def _no_errors(page):
    real = [e for e in page._errors if "Failed to load resource" not in e]
    assert real == [], real


def _frames(page):
    return [u for u in page._media if "streamable.com" in u]


def _open_game(page):
    page.wait_for_selector(".sc-bigs .sc-clip")


# --------------------------------------------------------------------------- #
# Static pins
# --------------------------------------------------------------------------- #
def test_chunk_budget_and_the_shell_stamp():
    js = (ROOT / "assets" / "scores-video.js").read_bytes().replace(b"\r\n", b"\n")
    assert len(js) <= VIDEO_JS_RAW, len(js)
    text = js.decode()
    for bad in ("<video", "preconnect", "crossorigin", "autoplay=", '"autoplay"', ".autoplay", "muted", "loop"):
        assert bad not in text.lower(), bad
    html = build_site.build_scores()
    assert f'data-vv="{build_site._asset_ver("assets/scores-video.js")}"' in html
    assert "scores-video.js" not in html, "the chunk is lazy, never a tag in the shell"
    assert "/assets/scores-video.js?v=" in (ROOT / "assets" / "scores.js").read_text(encoding="utf-8")


def test_fixture_payloads_pass_the_validator():
    for rel, doc in build_video_payloads().items():
        res = sc.validate_payload(sc.kind_of_name(rel), doc, name=rel)
        assert res["ok"], (rel, res["refused"])


# --------------------------------------------------------------------------- #
# Before a click
# --------------------------------------------------------------------------- #
def test_no_frame_and_no_frame_request_before_a_click(site, pw):
    with serve_site(site) as base, video_page(base, pw, hash_=f"#date={TODAY}") as page:
        page.wait_for_selector("#scores-app-root .sc-card")
        assert not any("scores-video.js" in u for u in page._requests), "the chunk loaded on the day view"
        page.evaluate("location.hash = '#date=2026-09-29&game=849845'")
        _open_game(page)
        assert any("scores-video.js?v=" in u for u in page._requests)
        assert page.locator("iframe").count() == 0 and page.locator("video").count() == 0
        assert _frames(page) == [], "a frame request before any click"
        assert all("img.mlbstatic.com" in u for u in page._media), page._media
        imgs = page.locator(".sc-clip img")
        assert 1 <= imgs.count() <= 6
        for i in range(imgs.count()):
            im = imgs.nth(i)
            assert im.get_attribute("loading") == "lazy" and im.get_attribute("decoding") == "async"
            assert im.get_attribute("width") == "480" and im.get_attribute("height") == "270"
            assert im.get_attribute("alt") == "" and " 960w" in im.get_attribute("srcset")
        first = page.locator(".sc-bigs .sc-clip").first
        assert first.get_attribute("aria-label") == "Play video, 29 seconds: Riley home run, 3 RBI, bottom 8th"
        assert page.locator(".sc-bigs .sc-vcredit").first.inner_text() == "Video: MLB"
        # rows four and five have no clip: the F3 sentence and Gameday on MLB.com
        none = page.locator(".sc-bigs .sc-vnone")
        assert none.count() == 2 and none.first.inner_text().startswith("No MLB clip for this play.")
        assert none.first.locator("a").get_attribute("href") == "https://www.mlb.com/gameday/849845"
        assert "noopener" in none.first.locator("a").get_attribute("rel")
        # the stars carry compact buttons and no link; the Video panel the two game videos
        assert page.locator(".sc-stars .sc-clip-sm").count() == 3
        assert page.locator(".sc-stars a.sc-vlink").count() == 0
        assert page.locator("h3", has_text=re.compile(r"^Video$")).count() == 1
        assert page.locator(".sc-clip[aria-label^='Play video, 3 minutes: game recap'] img").count() == 1
        assert page.locator(".sc-clip-sm", has_text="Condensed game 18:33").count() == 1
        _no_errors(page)


# --------------------------------------------------------------------------- #
# The player
# --------------------------------------------------------------------------- #
def test_a_click_opens_one_frame_a_second_replaces_it_escape_and_close_restore(site, pw):
    with serve_site(site) as base, video_page(base, pw, width=1280, hash_="#date=2026-09-29&game=849845") as page:
        _open_game(page)
        btns = page.locator(".sc-bigs .sc-clip")
        first_id = btns.nth(0).get_attribute("data-clip")
        btns.nth(0).click()
        fr = page.locator("iframe")
        assert fr.count() == 1
        src = fr.get_attribute("src")
        assert re.fullmatch(r"https://streamable\.com/m/[a-z0-9-]+", src) and "autoplay" not in src
        assert src.endswith("jhoan-duran-in-play-run-s-to-austin-riley-kkhhvg-x2885")
        assert fr.get_attribute("title").startswith("MLB video: Riley home run")
        assert fr.get_attribute("allow") == "fullscreen; picture-in-picture"
        assert fr.get_attribute("allowfullscreen") is not None
        assert fr.get_attribute("referrerpolicy") == "strict-origin-when-cross-origin"
        assert fr.get_attribute("sandbox") == SANDBOX
        fig = page.locator("figure.sc-vfig")
        assert page.locator(".sc-big").first.locator(".sc-vcredit:visible").count() == 1, "the credit printed twice"
        assert fig.count() == 1 and "Video: MLB" in fig.inner_text() and fig.locator(".sc-vclose").inner_text() == "Close video"
        page.wait_for_function("document.querySelector('iframe') && document.querySelector('iframe').contentDocument !== undefined")
        assert any(u.startswith("https://streamable.com/m/") for u in page._media)
        # a second clip removes the first frame and restores its button
        page.locator(".sc-bigs .sc-clip").nth(0).click()       # the second row's button is now the first left
        assert page.locator("iframe").count() == 1 and page.locator("iframe").get_attribute("src") != src
        assert page.locator(f'.sc-bigs .sc-clip[data-clip="{first_id}"]').count() == 1
        # Escape removes the frame and returns focus to its button
        page.keyboard.press("Escape")
        assert page.locator("iframe").count() == 0
        focused = page.evaluate("document.activeElement && document.activeElement.getAttribute('data-clip')")
        assert focused and focused != first_id
        # Enter opens, Close video closes and refocuses
        page.keyboard.press("Enter")
        assert page.locator("iframe").count() == 1
        page.locator(".sc-vclose").click()
        assert page.locator("iframe").count() == 0
        assert page.evaluate("document.activeElement.getAttribute('data-clip')") == focused
        # Space too
        page.keyboard.press(" ")
        assert page.locator("iframe").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        _no_errors(page)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 1280])
def test_no_page_scroll_with_a_frame_open(site, pw, width, theme):
    with serve_site(site) as base, video_page(base, pw, width=width, theme=theme,
                                              hash_="#date=2026-09-29&game=849845") as page:
        _open_game(page)
        page.locator(".sc-bigs .sc-clip").first.click()
        box = page.locator(".sc-vframe").bounding_box()
        assert abs(box["height"] - box["width"] * 9 / 16) <= 2, box        # a 16:9 box
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "page scroll"
        for tab in ("plays", "summary"):
            page.evaluate(f"location.hash = '#date=2026-09-29&game=849845&tab={tab}'")
            page.wait_for_selector(f'#sc-tab-{tab}[aria-selected="true"]')
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (tab, "page scroll")
        _no_errors(page)


def test_the_plays_tab_labels_an_earlier_events_clip_by_its_event(site, pw):
    with serve_site(site) as base, video_page(base, pw, hash_="#date=2026-09-29&game=849845&tab=plays") as page:
        page.wait_for_selector(".sc-pa .sc-clip-sm")
        row = page.locator("#sc-pa-31")
        assert row.locator(".sc-clip-sm").count() == 1
        b = row.locator(".sc-clip-sm")
        assert b.inner_text().strip() == "Pickoff attempt video 0:14"
        assert b.get_attribute("aria-label") == "Play video, 14 seconds: Pickoff attempt, bottom 4"
        assert page.locator(".sc-pa .sc-clip-sm", has_text="Play video").count() == 16
        assert page.locator(".sc-pa .sc-vnone").count() == 0, "the Plays tab adds no fallback line per row"
        b.click()
        assert page.locator("iframe").get_attribute("src").endswith("max-fried-pickoff-attempt-to-second-x4410")
        _no_errors(page)


def test_embed_off_renders_links_only(tmp_path, pw):
    site = make_site(tmp_path / "site", build_video_payloads(embed=False, pending=True))
    with serve_site(site) as base, video_page(base, pw, hash_="#date=2026-09-29&game=849845") as page:
        page.wait_for_selector(".sc-bigs a.sc-vlink")
        assert page.locator(".sc-clip").count() == 0 and page.locator("iframe").count() == 0
        links = page.locator(".sc-bigs a.sc-vlink")
        assert links.first.inner_text().startswith("Watch on MLB.com")
        assert re.fullmatch(r"https://www\.mlb\.com/video/[a-z0-9-]+", links.first.get_attribute("href"))
        assert links.first.get_attribute("target") == "_blank"
        assert page.locator(".sc-stars .sc-v a, .sc-stars .sc-v button").count() == 0
        # a clip may still post: "yet"
        assert page.locator(".sc-bigs .sc-vnone").first.inner_text().startswith("No MLB clip for this play yet.")
        assert _frames(page) == []
        _no_errors(page)


def test_an_open_frame_survives_a_reordering_poll(tmp_path, pw):
    payloads = build_video_payloads()
    site = make_site(tmp_path / "site", payloads)
    with serve_site(site) as base, video_page(base, pw, width=1280, hash_="#date=2026-09-29&game=849845",
                                              clock=True) as page:
        _open_game(page)
        page.locator(".sc-bigs .sc-clip").first.click()
        page.evaluate("document.querySelector('iframe').dataset.keep = '1'")
        gf = copy.deepcopy(payloads["games/849845.json"])
        big = list(reversed(gf["plays_big"]))
        for i, b in enumerate(big, start=1):
            b["rank"] = i
        gf["plays_big"] = big
        gf["rev"] = gf["card"]["rev"] = sc.rev_of({k: v for k, v in gf.items() if k != "rev"})
        doc = payloads["2026-09-29.json"]
        for c in doc["games"]:
            if c["pk"] == 849845:
                c["rev"] = gf["rev"]
        payloads["latest.json"]["window"]["2026-09-29"]["rev"] = sc.rev_of(doc)
        write_payloads(site, {"games/849845.json": gf, "2026-09-29.json": doc, "latest.json": payloads["latest.json"]})
        page.clock.fast_forward(301_000)
        page.wait_for_selector(".sc-vnew")
        assert page.locator(".sc-vnew").inner_text() == "Biggest plays changed. Show the new list"
        assert page.evaluate("document.querySelectorAll('iframe').length === 1 && "
                             "document.querySelector('iframe').dataset.keep === '1'"), "the poll detached the frame"
        page.locator(".sc-vnew").click()
        assert page.locator("iframe").count() == 0
        order = page.evaluate("Array.from(document.querySelectorAll('.sc-bigs .sc-big')).map(li => +li.dataset.ab)")
        assert order == [b["ab"] for b in big]
        _no_errors(page)


def test_the_card_chip_opens_the_game_at_that_play(site, pw):
    with serve_site(site) as base, video_page(base, pw, hash_="#date=2026-09-29") as page:
        page.wait_for_selector('article[data-pk="849845"]')
        chip = page.locator('article[data-pk="849845"] a.sc-chip', has_text="Video 0:29")
        assert chip.count() == 1
        assert page.locator('article[data-pk="849845"] img').count() == 0, "a poster on the day view (SC-CARDVID (a))"
        chip.click()
        page.wait_for_selector(".sc-bigs .sc-clip")
        page.wait_for_function("document.activeElement && document.activeElement.classList.contains('sc-clip')")
        assert page.evaluate("document.activeElement.closest('.sc-big').dataset.ab") == \
            str(build_video_payloads()["games/849845.json"]["card"]["top_play"]["ab"])
        assert page.locator("iframe").count() == 0, "the chip focuses the clip, never plays it"
        _no_errors(page)
