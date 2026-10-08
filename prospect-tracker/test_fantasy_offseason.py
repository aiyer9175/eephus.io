# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /fantasy/ off-season mode (site pass REDESIGN_fantasy, 2026-10-08).

In October the module tabs read "Rest of season" and "Tonight's slate", Redraft
carried Daily Streamers and Two-Start SP tabs that each rendered one empty line,
and DFS showed four tabs over an empty slate. The page now reads the site's one
season state (EephusSeason, PROSPX_4) and, outside phase "regular":

  * the Redraft tab subtitle reads "<next season> draft prep" and the DFS one
    "Off until Opening Day";
  * Daily Streamers and Two-Start SP leave the Redraft nav, and an old link to
    either (#m=redraft&section=streamers, #section=two_start) still resolves,
    to an "unmeasured" state card;
  * DFS hides its four tabs and shows one "unmeasured" state card naming the
    next Opening Day, without fetching the slate;
  * Dynasty is unchanged.

Inside phase "regular", and with no state on the page, nothing changes.

The source guards always run; the rendered half needs playwright and serves
the worktree over loopback, with assets/eephus-config.js answered by the
fixture state for each of the four registered dates.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import season_state as ss
from conftest import serve_site

ROOT = Path(__file__).parent

# The StatsAPI calendar fixture test_season_state.py pins the phases on.
MLB = {
    2026: {"seasonId": "2026", "springStartDate": "2026-02-20", "regularSeasonStartDate": "2026-03-25",
           "allStarDate": "2026-07-14", "regularSeasonEndDate": "2026-09-27",
           "postSeasonStartDate": "2026-09-28", "postSeasonEndDate": "2026-10-31"},
    2027: {"seasonId": "2027", "springStartDate": "2027-02-19", "regularSeasonStartDate": "2027-03-25",
           "allStarDate": "2027-07-13", "regularSeasonEndDate": "2027-09-26",
           "postSeasonStartDate": "2027-09-27", "postSeasonEndDate": "2027-10-31"},
}
MILB = {2026: [{"seasonId": "2026", "regularSeasonEndDate": "2026-09-20"}]}
DATES = {"2026-07-15": "regular", "2026-10-02": "postseason",
         "2026-12-01": "offseason", "2027-03-01": "spring"}

ALL_REDRAFT = ["streamers", "two_start", "ros_sp", "ros_rp", "ros_hitter", "buysell", "closers"]
OFF_REDRAFT = ["ros_sp", "ros_rp", "ros_hitter", "buysell", "closers"]
ALL_DFS = ["slate", "value", "optimizer", "stacks"]
ALL_DYNASTY = ["dynasty", "callups", "keeper", "fantasy_rank"]


def _src(name: str) -> str:
    return (ROOT / "assets" / name).read_text(encoding="utf-8")


def _state(iso: str) -> dict:
    return ss.build_state(date.fromisoformat(iso), MLB, MILB)


# ---- source guards -------------------------------------------------------------
def test_fixture_phases_match_the_registered_dates():
    for iso, phase in DATES.items():
        s = _state(iso)
        assert s["phase"] == phase, iso
        assert s["next_opening_day"] == ("2026-03-25" if iso < "2026-03-25" else "2027-03-25"), iso


def test_hub_applies_the_season_before_routing_and_after_the_state_loads():
    hub = _src("fantasy-hub.js")
    init = hub.split("  function init() {")[1].split("\n  }\n")[0]
    assert init.index("applySeason();") < init.index("activate(r.mod, r.sub);")
    assert 'var OFF_HIDE = { redraft: ["streamers", "two_start"] };' in hub
    assert 'modSub("redraft", off.next ? off.next + " draft prep" : "Draft prep");' in hub
    assert 'modSub("dfs", "Off until Opening Day");' in hub
    # the season state (eephus-config.js) and its reader (eephus-ui.js) run after
    # this deferred file, so init waits for DOMContentLoaded
    assert 'if (document.readyState === "complete") init();' in hub
    assert 'document.addEventListener("DOMContentLoaded", init);' in hub
    assert 's.phase === "regular") return null;' in hub


def test_clients_read_the_same_state_and_keep_their_in_season_paths():
    rd, dfs = _src("redraft.js"), _src("dfs.js")
    for src in (rd, dfs):
        assert 'if (!s || s.phase === "regular") return null;' in src
    assert 'var OFF_SECTIONS = { streamers: "Daily Streamers", two_start: "Two-Start SP" };' in rd
    assert 'pxState("unmeasured"' in rd and 'cls: "rd-offseason"' in rd
    assert "if (offSeason()) { if (r) r.innerHTML = offSeasonCard(); return; }" in dfs
    assert 'pxState("unmeasured"' in dfs and 'cls: "dfs-offseason"' in dfs
    # the boot's in-season half is untouched: loader, then the slate fetch
    boot = dfs.split("  function boot() {")[1].split("\n  }\n")[0]
    assert boot.index("offSeason()") < boot.index('pxState("loading"') < boot.index("load(DATA_URL)")


def test_shell_keeps_its_in_season_markup():
    import build_site
    html = build_site.build_fantasy()
    assert '<span class="fh-modsub">Rest of season</span>' in html
    assert "<span class=\"fh-modsub\">Tonight's slate</span>" in html
    for key in ALL_REDRAFT:
        assert f'data-redraftsection="{key}"' in html, key


# ---- rendered --------------------------------------------------------------------
@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def _browser(p):
    try:
        return p.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"chromium not installed for playwright: {exc}")


def _open(browser, server, iso, route, requests=None):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    body = ss.render_block(_state(iso)) + "\n"
    page.route("**/assets/eephus-config.js*",
               lambda r: r.fulfill(status=200, content_type="application/javascript", body=body))
    if requests is not None:
        page.on("request", lambda r: requests.append(r.url))
    page.goto(server + route, wait_until="load", timeout=90_000)
    return page


_VISIBLE_TABS = """mod => [...document.querySelectorAll('[data-' + mod + 'section]')]
  .filter(b => b.getBoundingClientRect().width > 0).map(b => b.getAttribute('data-' + mod + 'section'))"""
_SUBS = """() => Object.fromEntries([...document.querySelectorAll('[data-fantasymodule]')]
  .map(b => [b.getAttribute('data-fantasymodule'), b.querySelector('.fh-modsub').textContent]))"""


@pytest.mark.parametrize("iso", sorted(DATES))
def test_visible_tabs_and_subtitles_per_phase(server, iso):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    phase = DATES[iso]
    with sync_playwright() as p:
        browser = _browser(p)
        try:
            page = _open(browser, server, iso, "fantasy/")
            page.wait_for_function("() => !!window.EEPHUS_FANTASY_HOST && !!window.EephusSeason")
            page.wait_for_function("() => !document.querySelector('#redraft-app-root .px-state.is-loading') && "
                                   "document.querySelector('#redraft-app-root').children.length > 0",
                                   timeout=60_000)
            assert page.evaluate("() => window.EephusSeason.phase()") == phase
            subs = page.evaluate(_SUBS)
            redraft = page.evaluate(_VISIBLE_TABS, "redraft")
            assert subs["dynasty"] == "Keepers and prospects"
            if phase == "regular":
                assert subs == {"redraft": "Rest of season", "dynasty": "Keepers and prospects",
                                "dfs": "Tonight's slate"}
                assert redraft == ALL_REDRAFT
            else:
                assert subs["redraft"] == "2027 draft prep", subs
                assert subs["dfs"] == "Off until Opening Day", subs
                assert redraft == OFF_REDRAFT
                # the landing never opens on a hidden tab
                assert page.evaluate("() => location.hash").split("section=")[1].split("&")[0] in OFF_REDRAFT
            page.click('[data-fantasymodule="dynasty"]')
            assert page.evaluate(_VISIBLE_TABS, "dynasty") == ALL_DYNASTY
            page.click('[data-fantasymodule="dfs"]')
            page.wait_for_function("() => !document.querySelector('#dfs-app-root .px-state.is-loading') && "
                                   "document.querySelector('#dfs-app-root').children.length > 0",
                                   timeout=60_000)
            dfs = page.evaluate(_VISIBLE_TABS, "dfs")
            card = page.locator("#dfs-app-root .px-state.is-unmeasured.dfs-offseason")
            if phase == "regular":
                assert dfs == ALL_DFS and card.count() == 0
            else:
                assert dfs == [] and card.count() == 1
                assert "March 25, 2027" in card.inner_text()
        finally:
            browser.close()


@pytest.mark.parametrize("route,cls", [
    ("fantasy/#m=redraft&section=streamers", "rd-offseason"),
    ("fantasy/#m=redraft&section=two_start", "rd-offseason"),
    ("fantasy/#section=streamers", "rd-offseason"),
    ("fantasy/#m=dfs", "dfs-offseason"),
    ("fantasy/#m=dfs&section=optimizer", "dfs-offseason"),
    ("fantasy/#section=stacks", "dfs-offseason"),
])
def test_old_deep_links_resolve_to_the_state_card_off_season(server, route, cls):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    mod = "redraft" if cls.startswith("rd") else "dfs"
    with sync_playwright() as p:
        browser = _browser(p)
        try:
            got: list[str] = []
            page = _open(browser, server, "2026-12-01", route, got)
            sel = f"#{mod}-app-root .px-state.is-unmeasured.{cls}"
            page.wait_for_selector(sel, timeout=60_000)
            assert page.evaluate("() => location.hash").startswith(f"#m={mod}")
            text = page.locator(sel).inner_text()
            assert "Opening Day" in text and "2027" in text
            if mod == "dfs":
                page.wait_for_load_state("networkidle", timeout=60_000)
                assert not [u for u in got if "/data/dfs.json" in u], got
            # the same link in season paints the board, not the card
            page.close()
            page = _open(browser, server, "2026-07-15", route)
            page.wait_for_function(
                f"() => !document.querySelector('#{mod}-app-root .px-state.is-loading') && "
                f"document.querySelector('#{mod}-app-root').children.length > 0", timeout=60_000)
            assert page.locator(sel).count() == 0
        finally:
            browser.close()
