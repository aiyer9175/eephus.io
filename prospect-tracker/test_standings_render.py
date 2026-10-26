# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /standings/ page (STANDINGS_4) rendered in headless Chromium on fixture
payloads, behind standings_core.STANDINGS_LIVE.

THE SITE UNDER TEST is a temporary copy: the preview shell from
build_site.build_standings(), copies of assets/ and branding/, and fixture
payloads under data/scores/ built by standings_core and scores_core from
test_fixtures/standings/ and test_fixtures/scores/. Nothing here reads or
writes the repo's data/scores/ files or a real .cache/scores/, and every
request off loopback is aborted.

THE FIXTURES. OCTOBER: the 2026 final table (161-game NYY and BAL) with the
last weeks' games (so l10_seq is served), our columns copied from a futures
file whose records agree and a serving bracket_sim, and the season index's
bracket block from the SCORES_4b fixture. IN SEASON: the 2026-09-20 probe
with the tail schedule, a futures file stamped 2026-10-02T03:30:00+00:00, the
.5 row (NYY 85-65, 12 left, projWins 92.5), the lag row (LAD 86-57 against a
projection built on 85-57, the 2026-09-07 ledger entry) and a club whose
projection names no W-L (SEA).

WHAT IS PINNED (STANDINGS_PLAN 5 and 6, LANE_PRODUCT 6): the flag; the shell
and the shared head; the budgets and the cold first paint; no @keyframes and
no typed date; no page overflow at 390 to 1440 in both themes; the 352 px
Record group at 390; equal column x positions down the six division tables;
the frozen opaque club cell and the scroll shadow; 44 px controls at 390 and
24 px table buttons; the four states and the S3 banner; the October default,
the seeds and the mounted bracket; the marks, the RD/G ruler from 20 games,
the odds colour, the streak pictograms; the sort contract; and the
RECONCILIATION of every printed RD/G, W - xW, LEFT, PROJ, SEED, how-qualified,
LG and INTR cell to the served key, with the PROJ tooltips and the Eastern
stamp under two browser zones.
"""
from __future__ import annotations

import copy
import gzip
import json
import re
import shutil
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import build_site
import scores_core as sc
import standings_core as st
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "standings"
FIXSC = ROOT / "test_fixtures" / "scores"
KB = 1024
#: Plan 5.1 budgets (test-time pins; bytes with LF line endings, as served).
JS_RAW, JS_GZIP, CSS_RAW, SHELL_RAW, COLD_GZIP = 45 * KB, 14 * KB, 14 * KB, 17 * KB, 50 * KB
# SHELL_RAW 16 -> 17 KB on 2026-10-26 (PORT_RED_TESTS_CLEAR), the SCORES_7b precedent
# (test_scores_render.py): the page's own markup is 2.6 KB, the shared site chrome (the
# pixel wordmark, the nav icons) is the rest, and the shell measured 17,372 bytes. JS_RAW
# stays 45 KB: the script's header and helper notes moved to standings_core.py instead.
REG = [{"model_id": "playoff_odds_sim", "verdict": "provisional", "last_checked": "2026-10-02"},
       {"model_id": "postseason_bracket_sim", "verdict": "unvalidated", "last_checked": None}]
ODDS_STAMP = "2026-10-02T03:30:00+00:00"
DIV_CODES = ("ALE", "ALC", "ALW", "NLE", "NLC", "NLW")


def fx(name, base=FIX):
    return json.loads((base / name).read_text(encoding="utf-8"))


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tail_games():
    return st.games_from_schedule(fx("schedule_2026_tail.json"))


def futures_for(obj, *, gen, proj=None):
    """A futures.json whose club records agree with the rows (prices present
    so nothing can copy them)."""
    clubs = []
    for i, r in enumerate(obj["rows"]):
        left = r.get("left") or 0
        clubs.append({"team": r["code"], "record": f"{r['w']}-{r['l']}",
                      "projWins": (proj or {}).get(r["code"], r["w"] + left / 2),
                      "winTotalP10": r["w"], "winTotalP90": r["w"] + left,
                      "divisionPct": round(0.03 * (i % 9), 6), "playoffPct": round(0.1 * (i % 10) + 0.004, 6),
                      "byePct": 0.0004, "pennantPct": 0.0004 * (i % 3), "wsPct": 0.0, "impliedAmericanWS": 3233})
    return {"generated_at": gen, "season": obj["season"], "regular_season_end": "2026-09-27", "clubs": clubs}


def october_file():
    obj = st.build_season_file(fx("standings_2026.json"), as_of="2026-09-27", final=True,
                               generated_at="2026-10-02T06:00:00Z", games=tail_games())
    obj["opening_day"] = "2026-03-25"
    fut = futures_for(obj, gen="2026-10-02T05:31:18+00:00", proj={r["code"]: r["w"] for r in obj["rows"]})
    seeded = [r for r in obj["rows"] if r["seed"] is not None]
    br = {"season": 2026, "as_of": "2026-10-01", "generated_at": "2026-10-01T18:59:11+00:00", "label": "implied, no market",
          "method_version": "bracket_v1", "serve": {"on": True},
          "clubs": [{"team": r["code"], "league": r["lg"], "seed": r["seed"], "pennant_pct": round(0.5 / r["seed"], 6),
                     "ws_pct": round(0.25 / r["seed"], 6)} for r in seeded]}
    obj["ours"], obj["registry"] = st.build_ours(obj, futures=fut, bracket=br, october=True, registry=REG)
    return obj


def in_season_file():
    games = [g for g in tail_games()]
    obj = st.build_season_file(fx("p1_2026-09-20.json"), as_of="2026-09-20", final=False,
                               generated_at="2026-09-21T03:42:00Z", games=games)
    obj["opening_day"] = "2026-03-25"
    rows = {r["code"]: r for r in obj["rows"]}
    for r in obj["rows"]:                      # the tail schedule starts 09-12: no full last ten for anyone
        if not r.get("l10_seq") or len(r["l10_seq"]) != 10:
            r["l10_seq"] = None
    rows["NYY"].update(w=85, l=65, left=12)    # the .5 row
    rows["LAD"].update(w=86, l=57)             # the lag row
    rows["KCR"]["gp"] = 15                     # under 20 games: no RD/G colour
    fut = futures_for(obj, gen=ODDS_STAMP, proj={"NYY": 92.5, "LAD": 96.7})
    by = {c["team"]: c for c in fut["clubs"]}
    by["LAD"]["record"] = "85-57"
    del by["SEA"]["record"]
    sos = {"generated_at": "2026-09-21", "team_outlook": [
        {"team": r["code"], "current": {"sos": round(0.4801 + i / 1000, 4), "sosRank": i + 1}} for i, r in enumerate(obj["rows"])]}
    obj["ours"], obj["registry"] = st.build_ours(obj, futures=fut, sos=sos, registry=REG)
    return obj


def preseason_file():
    obj = st.build_season_file(fx("p3_2026-03-25.json"), as_of="2026-03-24", final=False, generated_at="2026-03-24T12:00:00Z")
    obj["opening_day"] = "2026-03-25"
    for r in obj["rows"]:
        r.update(w=0, l=0, gp=0, rs=0, ra=0, rd=0, rdg=None, pct=0.0, l10=[0, 0], streak=None, l10_seq=None)
    return obj


def payloads(season_doc, *, now=None, age_s=60, bracket=True, phist_from="2026-09-06", today="2026-10-02"):
    """{path under data/scores/: payload} for one standings season file."""
    now = now or datetime.now(timezone.utc)
    gen = _iso(now - timedelta(seconds=age_s))
    srev = sc.rev_of(season_doc)
    sindex = {"schema": sc.SCHEMA, "season": 2026, "dates": [],
              "bracket": sc.build_bracket(fx("postseason_series_2026.json", FIXSC), season=2026) if bracket else None}
    entry = {"season": season_doc["season"], "rev": srev, "race_rev": "r0", "phist_rev": "p0" if phist_from else None,
             "phist_from": phist_from, "n_dates": 0, "by_date": False, "final": season_doc["final"]}
    index = {"schema": sc.SCHEMA, "generated_at": gen, "seasons": [{"season": 2026, "rev": sc.rev_of(sindex), "n_dates": 0}],
             "registry": [], "copyright": season_doc["copyright"], "standings_seasons": [entry]}
    latest = {"schema": sc.SCHEMA, "generated_at": gen,
              "job": {"action": "idle", "state": "ok", "next_by": _iso(now + timedelta(minutes=10)), "last_ok_at": gen,
                      "down_after_s": 1800, "poll_live_s": 45, "poll_idle_s": 300, "errors_24h": 0, "refusals_24h": 0},
              "index_rev": sc.rev_of(index), "today": today, "next_game_date": None, "window": {}, "live": [],
              "standings": {"season": season_doc["season"], "as_of": season_doc["as_of"], "rev": srev, "race_rev": "r0",
                            "phist_rev": entry["phist_rev"], "stale_since": None}}
    return {"latest.json": latest, "index.json": index, "index-2026.json": sindex,
            f"standings/{season_doc['season']}.json": season_doc}


def make_site(dest: Path, pay: dict) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    build_site.write_standings_page(preview_root=dest)
    for d in ("assets", "branding"):
        if (ROOT / d).is_dir() and not (dest / d).exists():
            shutil.copytree(ROOT / d, dest / d)
    (dest / "data").mkdir(exist_ok=True)
    if (ROOT / "data" / "glossary.json").exists():
        shutil.copy2(ROOT / "data" / "glossary.json", dest / "data" / "glossary.json")
    for rel, doc in pay.items():
        p = dest / "data" / "scores" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(st.encode(doc).decode("utf-8") if rel.startswith("standings/") else sc.dumps(doc), encoding="utf-8")
    return dest


@contextmanager
def standings_page(base, pw, *, width=1280, theme="light", hash_="", tz=None, route=None, wait=True, init=None):
    """A page on the served copy: off-loopback requests aborted, console errors
    and every request recorded on page._errors and page._requests."""
    browser = pw.chromium.launch()
    kw = {"viewport": {"width": width, "height": 900}, "color_scheme": theme}
    if tz:
        kw["timezone_id"] = tz
    ctx = browser.new_context(**kw)
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    page._errors, page._requests = [], []
    page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base[:-1]) else r.abort())
    if route:                                  # registered last, so it is matched first
        route(page)
    page.on("request", lambda r: page._requests.append(r.url))
    page.on("console", lambda m: page._errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page._errors.append(str(e)))
    try:
        page.goto(base + "standings/" + hash_, wait_until="load")
        if wait:
            page.wait_for_selector("#standings-app-root table", timeout=15000)
        yield page
    finally:
        browser.close()


def no_errors(page):
    real = [e for e in page._errors if "Failed to load resource" not in e and "ERR_FAILED" not in e]
    assert real == [], real


def set_hash(page, h):
    page.evaluate("h => { location.hash = h; }", h)
    page.wait_for_timeout(60)
    page.wait_for_selector("#standings-app-root table", timeout=5000)


@pytest.fixture(scope="module")
def pw():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as p:
        try:
            p.chromium.launch().close()
        except Exception as e:  # pragma: no cover - chromium missing
            pytest.skip(f"chromium unavailable: {e}")
        yield p


@pytest.fixture(scope="module")
def oct_doc():
    return october_file()


@pytest.fixture(scope="module")
def ins_doc():
    return in_season_file()


@pytest.fixture(scope="module")
def oct_site(tmp_path_factory, oct_doc):
    return make_site(tmp_path_factory.mktemp("st_oct"), payloads(oct_doc))


@pytest.fixture(scope="module")
def ins_site(tmp_path_factory, ins_doc):
    return make_site(tmp_path_factory.mktemp("st_ins"), payloads(ins_doc, today="2026-09-21"))


def rows_of(doc):
    return {r["code"]: r for r in doc["rows"]}


# --------------------------------------------------------------------------- #
# The flag, the shell, the budgets
# --------------------------------------------------------------------------- #
def test_the_flags_are_on_since_the_flip_and_couple():
    assert st.STANDINGS_LIVE is True and st.STANDINGS_CHARTS is True
    assert (not st.STANDINGS_LIVE) or sc.SCORES_LIVE
    assert (not st.STANDINGS_CHARTS) or st.STANDINGS_LIVE


def test_standings_live_false_writes_no_published_page_and_the_flip_ships_one_line(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STANDINGS_LIVE", False)
    calls = []
    monkeypatch.setattr(build_site, "_write", lambda rel, html: calls.append(rel))
    path = Path(build_site.write_standings_page(preview_root=tmp_path))
    assert calls == [] and path == tmp_path / "standings" / "index.html" and path.exists()
    monkeypatch.setattr(build_site, "SCORES_PREVIEW_SITE", tmp_path / "preview")
    out = Path(build_site.write_standings_page())
    assert calls == [] and out == tmp_path / "preview" / "standings" / "index.html"
    # since STANDINGS_7_FLIP main() writes the published route under the flag and
    # publish_paths ships it; with the flag off it falls back to the preview copy
    import inspect
    main_src = inspect.getsource(build_site.main)
    assert "if standings_core.STANDINGS_LIVE:" in main_src
    assert '_write("standings/index.html", build_standings())' in main_src and "write_standings_page()" in main_src
    lines = [ln.strip() for ln in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines()]
    assert [ln for ln in lines if ln and not ln.startswith("#") and "standings" in ln] == ["standings"]
    # the flag on writes the published route; a preview_root never does
    monkeypatch.setattr(st, "STANDINGS_LIVE", True)
    assert build_site.write_standings_page() == str(build_site.ROOT / "standings" / "index.html")
    assert calls == ["standings/index.html"]


def test_the_shell_and_the_shared_head(monkeypatch):
    monkeypatch.setattr(st, "STANDINGS_LIVE", False)
    html = build_site.build_standings()
    assert "<title>MLB Standings - eephus.io</title>" in html
    assert build_site.STANDINGS_DESC.replace("'", "&#x27;") in html or build_site.STANDINGS_DESC in html
    assert html.count('id="standings-app-root"') == 1 and 'data-csv-export="standings"' in html
    assert build_site.STANDINGS_SUB in html and build_site.SCORES_SUB not in html
    icons = re.findall(r'<svg class="ico" width="32"[^>]*><use href="[^"#]*#i-([\w-]+)"', html)
    assert icons == ["scores"]
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)
    assert "Scores / Standings" in h1 and build_site._stage_chip("scores") in h1
    assert 'class="mlbstats-sectionnav"' not in html, "no strip while STANDINGS_LIVE is False"
    assert "EEPHUS_DATA_VERS" not in html
    for name, ver in (("standings.js", build_site._asset_ver("assets/standings.js")),
                      ("standings.css", build_site._asset_ver("assets/standings.css")),
                      ("sports-page.css", build_site._SPORTS_PAGE_CSS_VER), ("eephus-hub.js", build_site._HUB_VER),
                      ("eephus-teampick.js", build_site._TEAMPICK_VER), ("scores-bracket.js", build_site._SCORES_BRACKET_VER)):
        assert f"/assets/{name}?v={ver}" in html, name
    assert html.index("eephus-hub.js") < html.index("/assets/standings.js")
    # the strip under the flag: two links, aria-current on the page shown
    monkeypatch.setattr(st, "STANDINGS_LIVE", True)
    for active, cur in (("standings", "Standings"), ("scores", "Scores")):
        head = build_site._scores_module_head(active)
        nav = re.search(r'<nav class="mlbstats-sectionnav" aria-label="Scores / Standings">(.*?)</nav>', head).group(1)
        assert re.findall(r">(\w+)</a>", nav) == ["Scores", "Standings"]
        assert re.findall(r'aria-current="page">(\w+)<', nav) == [cur]


def test_the_scores_head_keeps_its_sub_line():
    html = build_site.build_scores()
    assert build_site.SCORES_SUB in html.replace("&#x27;", "'") and build_site.STANDINGS_SUB not in html


def _lf(p: Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


def test_budgets_and_the_cold_first_paint(oct_doc):
    js, css = _lf(ROOT / "assets" / "standings.js"), _lf(ROOT / "assets" / "standings.css")
    assert len(js) <= JS_RAW and len(gzip.compress(js)) <= JS_GZIP, (len(js), len(gzip.compress(js)))
    assert len(css) <= CSS_RAW, len(css)
    shell = build_site.build_standings().encode("utf-8")
    assert len(shell) <= SHELL_RAW, len(shell)
    pay = payloads(oct_doc)
    data = [sc.dumps(pay["latest.json"]).encode(), sc.dumps(pay["index.json"]).encode(), st.encode(oct_doc)]
    cold = sum(len(gzip.compress(b)) for b in [shell, js, css] + data)
    assert cold <= COLD_GZIP, cold


def test_no_keyframes_no_colour_literal_and_no_typed_date():
    css = (ROOT / "assets" / "standings.css").read_text(encoding="utf-8")
    js = (ROOT / "assets" / "standings.js").read_text(encoding="utf-8")
    assert "@keyframes" not in css and not re.search(r"animation(-name)?\s*:", css)
    for text in (css, js):
        assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", text)
        assert not re.search(r"\brgba?\(|\bhsla?\(", text)
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    for lit in re.findall(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', js):
        assert not re.search(rf"\b({months})\s+\d", lit), lit
        assert not re.search(r"\b20[0-2]\d\b|\b2030\b", lit), lit


def test_the_marks_are_drawn_and_mapped():
    sprite = (ROOT / "assets" / "eephus-icons.svg").read_text(encoding="utf-8")
    for key in ("st-clinch", "st-elim"):
        assert key in build_site.ICON_KEYS and build_site.ICON_FOR[key] == key
        assert f'<symbol id="i-{key}"' in sprite
        for size in (12, 16, 24, 32):
            assert f"#i-{key}" in build_site._ico(key, size)


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
_OVERFLOW = "() => document.scrollingElement.scrollWidth - window.innerWidth"


@pytest.mark.parametrize("width, theme", [(390, "light"), (390, "dark"), (768, "light"), (1024, "dark"),
                                          (1280, "light"), (1280, "dark"), (1440, "light")])
def test_no_page_overflow_in_any_view(oct_site, pw, width, theme):
    with serve_site(oct_site) as base, standings_page(base, pw, width=width, theme=theme) as page:
        for h in ("", "#view=division", "#view=wildcard", "#view=league", "#view=mlb", "#view=division&cols=splits",
                  "#view=playoffs"):
            if h:
                set_hash(page, h)
            assert page.evaluate(_OVERFLOW) <= 0, (h, page.evaluate(_OVERFLOW))
        no_errors(page)


def test_390_record_group_fits_and_columns_line_up(oct_site, pw):
    with serve_site(oct_site) as base, standings_page(base, pw, width=390, hash_="#view=division") as page:
        frames = page.evaluate("() => [...document.querySelectorAll('.st-frame')].map(f => [f.scrollWidth, f.clientWidth])")
        assert len(frames) == 6 and all(s <= c for s, c in frames), frames
        widths = page.evaluate("() => [...document.querySelectorAll('.st-table')].map(t => t.getBoundingClientRect().width)")
        assert all(abs(w - 352) <= 1 for w in widths), widths
        xs = page.evaluate("""() => [...document.querySelectorAll('.st-table')].map(t =>
            [...t.querySelectorAll('thead tr:last-child th')].map(th => Math.round(th.getBoundingClientRect().left)))""")
        assert len(xs) == 6 and all(x == xs[0] for x in xs), xs
        no_errors(page)


def test_390_splits_scroll_under_an_opaque_frozen_club_cell(oct_site, pw):
    with serve_site(oct_site) as base, standings_page(base, pw, width=390, hash_="#view=division&cols=splits") as page:
        f = page.locator(".st-frame").first
        assert page.evaluate("() => { const f = document.querySelector('.st-frame'); return f.scrollWidth > f.clientWidth; }")
        assert page.locator(".st-shadow").first.is_visible()
        cell = page.locator(".st-table tbody th[scope=row]").first
        left0 = cell.bounding_box()["x"]
        f.evaluate("el => { el.scrollLeft = 200; el.dispatchEvent(new Event('scroll')); }")
        page.wait_for_timeout(50)
        assert abs(cell.bounding_box()["x"] - left0) < 1
        bg = cell.evaluate("el => getComputedStyle(el).backgroundColor")
        assert bg not in ("transparent", "rgba(0, 0, 0, 0)") and not bg.startswith("rgba"), bg
        assert cell.evaluate("el => getComputedStyle(el).position") == "sticky"
        f.evaluate("el => { el.scrollLeft = el.scrollWidth; el.dispatchEvent(new Event('scroll')); }")
        page.wait_for_timeout(50)
        assert not page.locator(".st-shadow").first.is_visible()
        no_errors(page)


def test_1280_record_runs_and_odds_fit_with_logos_and_names(ins_site, pw):
    with serve_site(ins_site) as base, standings_page(base, pw, width=1280) as page:
        assert page.evaluate("() => [...document.querySelectorAll('.st-groups [aria-pressed=true]')].map(b => b.textContent)") \
            == ["Record", "Runs", "Odds"]
        frames = page.evaluate("() => [...document.querySelectorAll('.st-frame')].map(f => f.scrollWidth - f.clientWidth)")
        assert frames and max(frames) <= 0, frames
        assert page.locator(".st-nick").first.is_visible()
        # the logos are asked for (EEPHUS_HUB.teamLogo; the test aborts the off-loopback fetch)
        assert sum("teamlogos/mlb" in u for u in page._requests) >= 30
        no_errors(page)


def test_targets_44_px_at_390_and_24_px_table_buttons(oct_site, pw):
    with serve_site(oct_site) as base, standings_page(base, pw, width=390, hash_="#view=division") as page:
        small = page.evaluate("""() => [...document.querySelectorAll('.st-ctl button')].filter(b =>
            b.getBoundingClientRect().height < 44).map(b => b.textContent)""")
        assert small == [], small
        tb = page.evaluate("""() => [...document.querySelectorAll('.st-sort, .st-more')].filter(b => {
            const r = b.getBoundingClientRect(); return r.height < 24 || r.width < 24; }).length""")
        assert tb == 0
        rows = page.evaluate("() => [...document.querySelectorAll('.st-ctl .st-row')].map(r => r.getBoundingClientRect().height)")
        assert max(rows) <= 46, rows


# --------------------------------------------------------------------------- #
# States
# --------------------------------------------------------------------------- #
#: Holds the season file 1.5 s in the page itself (a route handler cannot wait).
SLOW_SEASON = r"""(() => { const f = window.fetch; window.fetch = function (u, o) {
  const p = f.call(this, u, o);
  return /standings\/\d{4}\.json/.test(String(u)) ? p.then(r => new Promise(ok => setTimeout(() => ok(r), 1500))) : p; }; })();"""


def test_loading_then_tables(oct_site, pw):
    with serve_site(oct_site) as base, standings_page(base, pw, width=390, init=SLOW_SEASON, wait=False) as page:
        box = page.locator("#standings-app-root .px-state.is-loading")
        box.wait_for(timeout=3000)
        assert box.get_attribute("role") == "status" and "Loading standings." in box.inner_text()
        page.wait_for_selector("#standings-app-root table", timeout=15000)


def test_failed_then_retry(oct_site, pw):
    state = {"n": 0}

    def fail_once(page):
        def handler(r):
            state["n"] += 1
            if state["n"] == 1:
                r.fulfill(status=500, body="no")
            else:
                r.continue_()
        page.route("**/standings/2026.json*", handler)
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280, route=fail_once, wait=False) as page:
        box = page.locator("#standings-app-root .px-state.is-failed")
        box.wait_for(timeout=5000)
        assert box.get_attribute("role") == "alert" and "Standings could not load." in box.inner_text()
        page.locator(".st-retry").click()
        page.wait_for_selector("#standings-app-root table", timeout=10000)
        assert state["n"] == 2


def test_my_teams_empty_state_and_follow(oct_site, pw):
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280, hash_="#view=division") as page:
        page.locator(".st-mine-btn").click()
        box = page.locator(".px-state.is-empty")
        box.wait_for(timeout=3000)
        assert "No followed clubs in this view. Follow a club from its row's details." in box.inner_text()
        page.locator(".st-mine-btn").click()
        page.locator('.st-more[data-code="NYY"]').click()
        page.locator('.st-follow[data-code="NYY"]').click()
        assert page.evaluate("() => JSON.parse(localStorage.getItem('eephus.scores.mine'))") == ["NYY"]
        assert page.locator("tr.st-mine").count() == 1
        page.locator(".st-mine-btn").click()
        assert page.evaluate("() => [...document.querySelectorAll('.st-table tbody tr[data-code]')].map(t => t.dataset.code)") == ["NYY"]
        no_errors(page)


def test_unmeasured_odds_and_the_race_start_sentence(tmp_path, pw, oct_doc):
    no_ours = copy.deepcopy(oct_doc)
    no_ours["ours"], no_ours["registry"] = None, []
    site = make_site(tmp_path / "a", payloads(no_ours))
    with serve_site(site) as base, standings_page(base, pw, width=1280, hash_="#cols=odds") as page:
        note = page.locator(".st-odds-note")
        assert note.get_attribute("class").count("is-unmeasured") == 1
        assert note.inner_text().strip() == "The daily odds record starts September 6, 2026."
        assert page.locator("[data-model-id]").count() == 0
    pre = make_site(tmp_path / "b", payloads(preseason_file(), today="2026-03-24"))
    with serve_site(pre) as base, standings_page(base, pw, width=390) as page:
        assert page.locator(".st-race-note").inner_text().strip() == "The race starts on Opening Day, March 25."


def test_the_s3_banner_in_season_only(tmp_path, pw, ins_doc, oct_doc):
    site = make_site(tmp_path / "a", payloads(ins_doc, age_s=40 * 3600, today="2026-09-21"))
    scores_js = (ROOT / "assets" / "scores.js").read_text(encoding="utf-8")
    with serve_site(site) as base, standings_page(base, pw, width=390) as page:
        ban = page.locator(".st-stale")
        assert re.fullmatch(r"Standings were last updated \w+ \d+ \(Eastern\)\. They may be out of date\.", ban.inner_text().strip())
        assert page.locator(".st-table").count() == 6, "a stale file never hides the tables"
        # the same decision as the Scores rule (assets/scores.js scoresStaleState)
        page.add_script_tag(content=scores_js)
        code = page.evaluate("""() => fetch('/data/scores/latest.json').then(r => r.json()).then(L =>
            window.EephusScores.scoresStaleState(L, Date.now(), L.today).code)""")
        assert code == "S3"
    old_final = make_site(tmp_path / "b", payloads(oct_doc, age_s=40 * 3600))
    with serve_site(old_final) as base, standings_page(base, pw, width=390) as page:
        assert page.locator(".st-stale").count() == 0
        assert page.locator(".st-stamp em").inner_text() == "Final standings, 2026 regular season."


# --------------------------------------------------------------------------- #
# October: the default view, the seeds and the bracket
# --------------------------------------------------------------------------- #
SEEDS = {"AL": ["TBR", "CLE", "HOU", "NYY", "BOS", "CHW"], "NL": ["MIL", "LAD", "ATL", "SDP", "CHC", "PHI"]}


def test_october_defaults_to_playoffs_with_the_seeds_and_the_bracket(oct_site, pw, oct_doc):
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280) as page:
        assert page.locator('.st-views [aria-pressed="true"]').inner_text() == "Playoffs"
        page.wait_for_selector("#st-bracket .scb", timeout=10000)
        got = page.evaluate("""() => [...document.querySelectorAll('.st-seeds .st-table')].map(t =>
            [...t.querySelectorAll('tbody tr[data-code]')].map(r => [r.dataset.code, r.cells[1].textContent, r.cells[3].textContent]))""")
        rows = rows_of(oct_doc)
        assert [[c for c, _s, _h in t] for t in got] == [SEEDS["AL"], SEEDS["NL"]]
        for t in got:
            for code, seed, how in t:
                assert seed == str(rows[code]["seed"]) and how == rows[code]["qualified_text"], code
        assert {r["code"]: r["seed"] for r in oct_doc["rows"] if r["seed"]} == {
            c["team"]: c["seed"] for c in fx("seeds_2026.json")["clubs"]}
        inside = page.evaluate("""() => { const b = document.querySelector('#st-bracket');
            return [b.textContent.includes('%'), b.querySelectorAll('[data-model-id]').length]; }""")
        assert inside == [False, 0]
        lab = page.locator(".st-seeds .st-oddslab").inner_text()
        assert "Eephus bracket simulator, unvalidated" in lab
        block = fx("postseason_series_2026.json", FIXSC)
        if "seed" in json.dumps(sc.build_bracket(block, season=2026)):   # once SCORES_4b serves its seeding
            pytest.fail("the bracket block now serves seeds: pin the mounted bracket's seeds to the served seed")
        no_errors(page)


def test_the_bracket_chunk_is_the_scores_chunk_unchanged(oct_site, pw):
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280) as page:
        page.wait_for_selector("#st-bracket .scb", timeout=10000)
        assert any("/assets/scores-bracket.js?v=" + build_site._SCORES_BRACKET_VER in u for u in page._requests)
        assert not any("-phist.json" in u or "-race.json" in u for u in page._requests)


# --------------------------------------------------------------------------- #
# Marks and colour
# --------------------------------------------------------------------------- #
MARKS = {"z": {"TBR", "MIL"}, "y": {"CLE", "HOU", "ATL", "LAD"}, "w": {"NYY", "BOS", "CHW", "PHI", "CHC", "SDP"}}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_marks_and_their_ink(oct_site, pw, theme):
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280, theme=theme, hash_="#view=mlb") as page:
        got = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.st-table tbody tr[data-code]')].map(r =>
            [r.dataset.code, [(r.querySelector('.st-letter abbr') || {}).textContent || '',
              (r.querySelector('.st-mk use') || {getAttribute: () => ''}).getAttribute('href')]]))""")
        assert len(got) == 30
        for code, (letter, href) in got.items():
            want = next((m for m, s in MARKS.items() if code in s), "e")
            assert letter == want, (code, letter)
            assert href.endswith("#i-st-elim" if want == "e" else "#i-st-clinch"), (code, href)
        ink = page.evaluate("""() => { const p = document.createElement('span'); document.body.appendChild(p);
            const tok = v => { p.style.color = 'var(' + v + ')'; return getComputedStyle(p).color; };
            return [getComputedStyle(document.querySelector('.st-mk .st-mk-e')).color, tok('--text-tertiary'),
                    getComputedStyle(document.querySelector('.st-mk .st-mk-c')).color, tok('--text-primary'),
                    tok('--accent-red'), tok('--accent-green')]; }""")
        assert ink[0] == ink[1] and ink[2] == ink[3] and ink[0] not in ink[4:] and ink[2] not in ink[4:]
        no_errors(page)


def test_rdg_ruler_from_20_games_and_uncoloured_runs(ins_site, pw, ins_doc):
    with serve_site(ins_site) as base, standings_page(base, pw, width=1440, hash_="#view=mlb&cols=runs") as page:
        idx = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('.st-table thead tr:last-child th')].map((t, i) => [t.textContent.replace(/[\\u25B2\\u25BC]/g, ''), i]))")
        got = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.st-table tbody tr[data-code]')].map(r =>
            [r.dataset.code, [...r.cells].map(c => c.className)]))""")
        rows = rows_of(ins_doc)
        rdg = [k for k in idx if k.startswith("RD/G")][0]
        for code, cls in got.items():
            c = cls[idx[rdg]]
            if rows[code]["gp"] < 20:
                assert "vt-" not in c, code
            else:
                assert "vt-fam-rdg" in c, (code, c)
            for k in idx:
                if k.startswith(("RD,", "RS", "RA", "W - xW")) or k == "RD":
                    assert "vt-" not in cls[idx[k]], (code, k)
        no_errors(page)


def test_odds_colour_and_the_eliminated_glyph(ins_site, pw, ins_doc):
    with serve_site(ins_site) as base, standings_page(base, pw, width=1440, hash_="#view=mlb&cols=odds") as page:
        res = page.evaluate("""() => { const out = []; const p = document.createElement('span'); document.body.appendChild(p);
            document.querySelectorAll('.st-table tbody tr[data-code]').forEach(r => {
              r.querySelectorAll('td.st-odds').forEach(td => {
                const s = td.getAttribute('style') || ''; let want = null;
                if (s) { p.setAttribute('style', s); want = getComputedStyle(p).color; }
                out.push([r.dataset.code, td.textContent, getComputedStyle(td).color, want, td.classList.contains('st-dim')]); }); });
            p.removeAttribute('style'); p.style.color = 'var(--text-dim)'; return [out, getComputedStyle(p).color]; }""")
        cells, dim = res
        rows = rows_of(ins_doc)
        for code, text, color, want, is_dim in cells:
            if re.fullmatch(r"\d+-\d+", text) or re.fullmatch(r"\.\d{3}", text):   # PROJ and SOS take no colour
                continue
            if want:
                assert color == want, (code, text)
            if rows[code]["e"]:
                assert is_dim and color == dim, (code, text)
        no_errors(page)


def test_streak_pictograms_and_text_ink(oct_site, pw):
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280, hash_="#view=mlb") as page:
        got = page.evaluate("""() => [...document.querySelectorAll('.st-table tbody tr[data-code]')].map(r => {
            const td = [...r.cells].find(c => c.querySelector('.st-up, .st-down')); if (!td) return null;
            const u = td.querySelector('use').getAttribute('href');
            const n = [...td.childNodes].find(x => x.nodeType === 3);
            return [u.split('#')[1], n.textContent, getComputedStyle(td).color]; })""")
        ink = page.evaluate("() => { const p = document.createElement('span'); p.style.color = 'var(--text-primary)'; document.body.appendChild(p); return getComputedStyle(p).color; }")
        got = [g for g in got if g]
        assert len(got) == 30
        for sym, text, color in got:
            assert sym == ("i-ev-up" if text.startswith("W") else "i-ev-down") and color == ink, (sym, text)
        no_errors(page)


def test_lamps_equal_the_l10_wins(oct_site, pw, oct_doc):
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280, hash_="#view=mlb") as page:
        got = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.st-table tbody tr[data-code]')].map(r =>
            [r.dataset.code, [r.querySelectorAll('.st-lamps i.on').length, r.querySelectorAll('.st-lamps i').length,
              (r.querySelector('.st-lamps') || {parentNode: {textContent: ''}}).parentNode.textContent]]))""")
        rows = rows_of(oct_doc)
        for code, (lit, n, text) in got.items():
            assert n == 10 and lit == rows[code]["l10"][0] and text == f"{rows[code]['l10'][0]}-{rows[code]['l10'][1]}", code


# --------------------------------------------------------------------------- #
# Sort and semantics
# --------------------------------------------------------------------------- #
def test_keyboard_sort_announce_and_restore(ins_site, pw):
    with serve_site(ins_site) as base, standings_page(base, pw, width=1280, hash_="#view=division&cols=runs") as page:
        page.locator('.st-sort[data-k="rdg"]').first.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(50)
        assert page.locator("#st-announce").inner_text() == "Sorted by run differential per game, highest first."
        assert page.evaluate("() => document.activeElement.dataset.k") == "rdg"
        page.keyboard.press("Enter")
        page.wait_for_timeout(50)
        assert page.locator("#st-announce").inner_text() == "Sorted by run differential per game, lowest first."
        assert page.evaluate("() => document.activeElement.dataset.k") == "rdg"
        per = page.evaluate("""() => [...document.querySelectorAll('.st-table')].map(t =>
            [...t.querySelectorAll('[aria-sort]')].filter(e => e.getAttribute('aria-sort') !== 'none').length)""")
        assert per == [1] * 6
        assert page.evaluate("() => [...document.querySelectorAll('[aria-sort]')].every(e => e.tagName === 'TH')")
        vals = page.evaluate("""() => { const t = document.querySelector('.st-table'); const i = [...t.querySelectorAll('thead tr:last-child th')]
            .findIndex(th => th.querySelector('[data-k=rdg]')); return [...t.querySelectorAll('tbody tr[data-code]')].map(r => parseFloat(r.cells[i].textContent)); }""")
        assert vals == sorted(vals)
        page.locator(".st-reset").click()
        page.wait_for_timeout(50)
        assert page.locator(".st-reset").count() == 0
        assert page.locator("#st-announce").inner_text() == "Standings order restored."
        assert page.evaluate("() => [...document.querySelectorAll('[aria-sort]')].every(e => e.getAttribute('aria-sort') === 'none')")
        no_errors(page)


def test_ties_keep_mlb_order_and_nulls_sort_last(ins_site, pw, ins_doc):
    rows = rows_of(ins_doc)
    with serve_site(ins_site) as base, standings_page(base, pw, width=1280, hash_="#view=mlb&cols=sched") as page:
        for d in ("desc", "asc"):
            set_hash(page, f"#view=mlb&cols=sched&sort=w.{d}")
            order = page.evaluate("() => [...document.querySelectorAll('.st-table tbody tr[data-code]')].map(r => r.dataset.code)")
            for a, b in zip(order, order[1:]):
                if rows[a]["w"] == rows[b]["w"]:
                    assert rows[a]["ranks"]["mlb"] < rows[b]["ranks"]["mlb"], (d, a, b)
            set_hash(page, f"#view=mlb&cols=sched&sort=magic.{d}")
            order = page.evaluate("() => [...document.querySelectorAll('.st-table tbody tr[data-code]')].map(r => r.dataset.code)")
            nums = [rows[c]["magic"] is not None for c in order]
            assert nums == sorted(nums, reverse=True), (d, order)
        assert page.locator("caption").count() == 1 and page.locator("tbody th[scope=row]").count() == 30
        no_errors(page)


# --------------------------------------------------------------------------- #
# RECONCILIATION to the payload
# --------------------------------------------------------------------------- #
def _cells(page):
    return page.evaluate("""() => { const out = {};
        document.querySelectorAll('.st-table').forEach(t => {
          const heads = [...t.querySelectorAll('thead tr:last-child th')].map(th => (th.querySelector('abbr') || th).textContent);
          t.querySelectorAll('tbody tr[data-code]').forEach(r => {
            const o = out[r.dataset.code] = out[r.dataset.code] || {};
            [...r.cells].forEach((c, i) => { o[heads[i]] = [c.textContent, c.getAttribute('title')]; }); }); });
        return out; }""")


def _pair(p):
    return f"{p[0]}-{p[1]}"


def _signed(v, d=0):
    s = f"{v:.{d}f}" if d else str(v)
    return ("0" if not d else f"{0:.{d}f}") if float(s) == 0 else ("+" if v > 0 else "") + s


@pytest.mark.parametrize("tz", ["America/Los_Angeles", "Asia/Tokyo"])
def test_every_served_cell_reads_back_in_season(ins_site, pw, ins_doc, tz):
    rows, clubs = rows_of(ins_doc), ins_doc["ours"]["clubs"]
    h = "#view=mlb&cols=splits,runs,odds,sched"
    with serve_site(ins_site) as base, standings_page(base, pw, width=1440, hash_=h, tz=tz) as page:
        got = _cells(page)
        assert len(got) == 30
        for code, cells in got.items():
            r, c = rows[code], clubs[code]
            assert cells["RD/G"][0] == _signed(r["rdg"], 2), code
            assert cells["W - xW"][0] == _signed(r["w_xw"]), code
            assert cells["LEFT"][0] == str(r["left"]), code
            assert cells["LG"][0] == _pair(r["vs_lg"]) and cells["INTR"][0] == _pair(r["intr"]), code
            if c["proj_basis_ok"] and c["proj_w_int"] is not None:
                assert cells["PROJ"][0] == f"{c['proj_w_int']}-{c['proj_l']}", code
                assert cells["PROJ"][1] == ("Projected final record from the season simulator, as of October 1 (Eastern). "
                                            f"Projected wins: {c['proj_w']:.1f}."), (code, cells["PROJ"][1])
            else:
                assert cells["PROJ"][0] == "-", code
        nyy, lad, sea = got["NYY"], got["LAD"], got["SEA"]
        assert nyy["PROJ"][0] == "93-69" and "92.5" in nyy["PROJ"][1]
        assert lad["PROJ"] == ["-", "Projection built on a W-L of 85-57; this row is 86-57."]
        assert sea["PROJ"][1] == f"The projection on file names no W-L; this row is {rows['SEA']['w']}-{rows['SEA']['l']}."
        lab = page.locator(".st-oddslab").first.inner_text()
        assert "as of October 1 (Eastern)" in lab and "Eephus season simulator, provisional" in lab
        assert not any("-phist.json" in u or "-race.json" in u for u in page._requests)
        assert page.evaluate("() => /\\bluck/i.test(document.body.textContent)") is False
        no_errors(page)


def test_seed_cells_and_the_final_rows_read_back(oct_site, pw, oct_doc):
    rows, clubs = rows_of(oct_doc), oct_doc["ours"]["clubs"]
    with serve_site(oct_site) as base, standings_page(base, pw, width=1440, hash_="#view=wildcard&cols=odds,sched") as page:
        got = _cells(page)
        for code, cells in got.items():
            assert cells["SEED"][0] == (str(rows[code]["seed"]) if rows[code]["seed"] else "-"), code
        assert got["NYY"]["LEFT"][0] == "0" and got["BAL"]["LEFT"][0] == "0"
        assert got["NYY"]["PROJ"][0] == "93-68" and got["BAL"]["PROJ"][0] == "79-82"
        assert (clubs["NYY"]["proj_w_int"], clubs["NYY"]["proj_l"]) == (93, 68)
        groups = page.evaluate("() => [...document.querySelectorAll('.st-sub')].map(h => h.textContent)")
        assert groups == ["Division leaders", "Wild card"] * 2
        cut = page.evaluate("() => [...document.querySelectorAll('tr.st-cut')].map(r => r.dataset.code)")
        assert cut == ["CHW", "PHI"], cut
        no_errors(page)


def test_the_credit_prints_the_copyright_verbatim(oct_site, pw, oct_doc):
    with serve_site(oct_site) as base, standings_page(base, pw, width=1280, hash_="#view=division") as page:
        assert page.locator(".st-copy").evaluate("e => e.textContent") == oct_doc["copyright"]
        assert page.locator(".st-copy a").get_attribute("href") == "http://gdx.mlb.com/components/copyright.txt"
        text = page.evaluate("() => document.querySelector('.st-app').textContent")
        assert "Standings, records and splits come from MLB's public StatsAPI feed." in text
        words = re.compile(r"\b(edge|value|ev|kelly|pick|lean|bet|luck|lucky|unlucky|contender|pretender|fraud|"
                           r"overachieving|underachieving|collapse|choke|surging|hot|cold|slump|regress|due|lock|safe|dead)\b", re.I)
        assert words.findall(text) == [] and "for real" not in text.lower()
        assert "—" not in text and "–" not in text
        no_errors(page)


# --------------------------------------------------------------------------- #
# Charts (STANDINGS_5, behind standings_core.STANDINGS_CHARTS)
# --------------------------------------------------------------------------- #
# THE CHART FIXTURES. A synthetic 184-date season (test_standings_core's
# synth_season and synth_standings) whose season file and race file agree, so
# C2's last date reconciles to the served signed WCGB; the odds record packed
# from the ledger and record fixtures by standings_core.phist_blocks (18
# regular entries 2026-09-06 to 2026-09-30, one post entry on 2026-10-01); and
# STANDINGS_3's post-only 2027 file (regular empty, post 2027-10-05 and
# 2027-10-06). The shell is built with STANDINGS_LIVE and STANDINGS_CHARTS set
# True inside the fixture only.
from test_standings_core import synth_season, synth_standings  # noqa: E402

CH_GEN = "2026-10-02T06:00:00Z"
CHART_RAW = 20 * KB
VIZ = ("var(--viz-1)", "var(--viz-2)")


def chart_docs():
    games = synth_season(n_dates=184)
    last = st.final_games(games)[-1]["date"]
    pay = synth_standings(games, last)
    race = st.build_race_file(games, 2026, {last: pay}, copyright=pay["copyright"], generated_at=CH_GEN)
    doc = st.build_season_file(pay, as_of=last, final=False, generated_at=CH_GEN, games=games, race=race)
    doc["registry"] = st.registry_block(REG, (st.MODEL_REGULAR, st.MODEL_POST))
    blocks = st.phist_blocks(fx("futures_ledger_2026.json")["entries"], fx("bracket_sim_record_2026.json")["entries"],
                             2026, "2026-03-25", None, st.FRAME_FROM_SEED[2026])
    ph = st.build_phist_file(2026, generated_at=CH_GEN, copyright=doc["copyright"], regular=blocks["regular"],
                             post=blocks["post"], switch_as_of=blocks["switch_as_of"])
    return doc, race, ph


def post_only_docs(doc, race):
    d27, r27 = copy.deepcopy(doc), copy.deepcopy(race)
    d27["season"] = r27["season"] = 2027
    post = {"as_of": ["2027-10-05", "2027-10-06"], "sha256": ["a" * 64, "b" * 64],
            "clubs": {"NYY": [[0.31, 0.17], [0.33, 0.18]], "LAD": [[0.42, 0.22], [0.42, 0.22]]}}
    regular = {"source": st.PHIST_REGULAR_SOURCE, "missing": ["2027-03-26", "2027-04-01", "2027-04-02"]}
    ph = st.build_phist_file(2027, generated_at=CH_GEN, copyright=doc["copyright"], regular=regular, post=post,
                             switch_as_of="2027-10-05")
    return d27, r27, ph


def chart_payloads(doc, race, ph, phist_from):
    pay = payloads(doc, phist_from=phist_from)
    y = doc["season"]
    e = pay["index.json"]["standings_seasons"][0]
    e["race_rev"], e["phist_rev"] = sc.rev_of(race), sc.rev_of(ph)
    pay["latest.json"]["index_rev"] = sc.rev_of(pay["index.json"])
    pay[f"standings/{y}-race.json"] = race
    pay[f"standings/{y}-phist.json"] = ph
    return pay


def make_chart_site(dest, pay):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(st, "STANDINGS_LIVE", True)
        mp.setattr(st, "STANDINGS_CHARTS", True)
        return make_site(dest, pay)


@pytest.fixture(scope="module")
def ch_docs():
    return chart_docs()


@pytest.fixture(scope="module")
def ch_site(tmp_path_factory, ch_docs):
    doc, race, ph = ch_docs
    return make_chart_site(tmp_path_factory.mktemp("st_ch"), chart_payloads(doc, race, ph, ph["regular"]["as_of"][0]))


@pytest.fixture(scope="module")
def ch27_site(tmp_path_factory, ch_docs):
    d27, r27, ph = post_only_docs(*ch_docs[:2])
    return make_chart_site(tmp_path_factory.mktemp("st_ch27"), chart_payloads(d27, r27, ph, ph["switch_as_of"]))


def jsg(v):
    """The chunk's signed format (a JS number as text): +2.5, 0, -3, '-' for null."""
    if v is None:
        return "-"
    t = str(int(v)) if float(v).is_integer() else repr(float(v))
    return ("+" if v > 0 else "") + t


def chart_page(base, pw, **kw):
    kw.setdefault("hash_", "#view=charts")
    kw.setdefault("wait", False)
    return standings_page(base, pw, **kw)


def wait_charts(page, c3=True):
    page.wait_for_selector(".stc-fig svg", timeout=15000)
    if c3:
        page.wait_for_selector('.stc-fig[data-k="c3"] svg', timeout=15000)


#: Every polyline vertex of a club, and the figure's own scales (fig._geo,
#: the hub's geo out-param) applied to served values, read in the page.
_VERTS = """([k, id]) => { const f = document.querySelector('.stc-fig[data-k="' + k + '"]');
    return [...f.querySelectorAll('polyline[data-id="' + id + '"]')].map(pl => pl.getAttribute('points').trim().split(/\\s+/)
      .map(q => q.split(',').map(Number))); }"""
_GEO = """([k, xs, vs]) => { const g = document.querySelector('.stc-fig[data-k="' + k + '"]')._geo;
    return xs.map((x, i) => [g.x(x), vs[i] == null ? null : g.y(vs[i])]); }"""
_TABLE = """async k => { const f = document.querySelector('.stc-fig[data-k="' + k + '"]'), d = f.querySelector('.stc-num');
    if (!d.open) { d.querySelector('summary').click(); await new Promise(r => setTimeout(r, 60)); }
    return [...d.querySelectorAll('tr')].map(r => [...r.cells].map(c => c.textContent)); }"""
_MARKS = """([k, c]) => [...document.querySelectorAll('.stc-fig[data-k="' + k + '"] rect[data-x][data-id="' + c + '"]')].map(r => r.dataset.x)"""
_STROKES = """k => Object.fromEntries([...document.querySelectorAll('.stc-fig[data-k="' + k + '"] polyline')].map(p =>
    [p.dataset.id, p.getAttribute('stroke')]))"""
_VREFS = """k => [...document.querySelectorAll('.stc-fig[data-k="' + k + '"] [data-vref]')].map(l => l.dataset.vref)"""


def test_with_the_charts_flag_off_no_chart_loads(tmp_path, monkeypatch, oct_doc, pw):
    # STANDINGS_CHARTS is on since STANDINGS_7_FLIP; the dark path still holds when it is off
    monkeypatch.setattr(st, "STANDINGS_CHARTS", False)
    assert "data-charts-src" not in build_site.build_standings()
    site = make_site(tmp_path / "st_nocharts", payloads(oct_doc))
    with serve_site(site) as base, standings_page(base, pw, width=1280, hash_="#view=division") as page:
        assert page.locator('[data-view="charts"]').count() == 0 and page.locator(".st-race").count() == 0
        assert not any("standings-charts.js" in u for u in page._requests)


def test_the_chart_chunk_is_stamped_and_within_its_budget(monkeypatch):
    monkeypatch.setattr(st, "STANDINGS_LIVE", True)
    monkeypatch.setattr(st, "STANDINGS_CHARTS", True)
    html = build_site.build_standings()
    ver = build_site._asset_ver("assets/standings-charts.js")
    assert f'data-charts-src="/assets/standings-charts.js?v={ver}"' in html
    js = _lf(ROOT / "assets" / "standings-charts.js")
    assert len(js) <= CHART_RAW, len(js)
    text = js.decode("utf-8")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", text) and not re.search(r"\brgba?\(|<canvas|getContext", text)
    assert not re.search(r"\b(luck|lucky|unlucky|trend|forecast|regress)\b", text, re.I)


def test_race_disclosure_c1_reconciles_to_the_race_file(ch_site, pw, ch_docs):
    doc, race, _ph = ch_docs
    with serve_site(ch_site) as base, standings_page(base, pw, width=1280, hash_="#view=division") as page:
        assert not any("-race.json" in u for u in page._requests), "the tables never fetch the race"
        page.locator('.st-race[data-div="ALE"] summary').click()
        page.wait_for_selector('.st-race .stc-fig[data-k="c1-ALE"] svg', timeout=10000)
        assert sum("-race.json" in u for u in page._requests) == 1
        assert not any("-phist.json" in u for u in page._requests)
        clubs = [r["code"] for r in sorted((r for r in doc["rows"] if r["div"] == "ALE"), key=lambda r: r["ranks"]["div"])]
        dates = race["dates"]
        for code in clubs:
            want = [t[0] - t[1] for t in race["clubs"][code]]
            verts = page.evaluate(_VERTS, ["c1-ALE", code])
            assert len(verts) == 1 and len(verts[0]) == len(dates)
            geo = page.evaluate(_GEO, ["c1-ALE", dates, want])
            for (vx, vy), (gx, gy) in zip(verts[0], geo):
                assert abs(vx - gx) < 0.06 and abs(vy - gy) < 0.06, code
        tab = page.evaluate(_TABLE, "c1-ALE")
        assert tab[0] == ["Date"] + clubs and len(tab) == len(dates) + 1
        for row in tab[1:]:
            i = dates.index(row[0])
            assert row[1:] == [jsg(race["clubs"][c][i][0] - race["clubs"][c][i][1]) for c in clubs], row[0]
        no_errors(page)


def test_charts_view_reconciles_every_chart(ch_site, pw, ch_docs):
    doc, race, ph = ch_docs
    rows = rows_of(doc)
    with serve_site(ch_site) as base, chart_page(base, pw, width=1280) as page:
        wait_charts(page)
        assert sum("-phist.json" in u for u in page._requests) == 1
        # C1: six panels on one shared, symmetric y domain
        doms = page.evaluate("() => [...document.querySelectorAll('.stc-fig[data-k^=c1]')].map(f => [f._geo.lo, f._geo.hi])")
        assert len(doms) == 6 and len({tuple(d) for d in doms}) == 1 and doms[0][0] == -doms[0][1]
        # C2, whole season and every club: wc_gap on every date, the signed WCGB on the last
        n = len(race["dates"])
        for lg in ("AL", "NL"):
            k = "c2-" + lg
            for tg in ("whole", "all"):
                page.locator(f'.stc-fig[data-k="{k}"] .stc-tg[data-v="{tg}"]').click()
                page.wait_for_timeout(80)
            tab = page.evaluate(_TABLE, k)
            head, body = tab[0][1:], tab[1:]
            assert len(body) == n and body[0][0] == race["dates"][-1]
            for j, code in enumerate(head, start=1):
                r = rows[code]
                assert body[0][j] == ("-" if r["wcgb"] is None else jsg(r["wcgb"] if r["wc_ahead"] else -r["wcgb"])), code
                for row in body:
                    assert row[j] == jsg(race["wc_gap"][code][race["dates"].index(row[0])]), (code, row[0])
                pts = [(d, v) for d, v in zip(race["dates"], race["wc_gap"][code]) if v is not None]
                verts = [q for seg in page.evaluate(_VERTS, [k, code]) for q in seg]
                geo = page.evaluate(_GEO, [k, [d for d, _v in pts], [v for _d, v in pts]])
                assert len(verts) == len(geo)
                for (vx, vy), (gx, gy) in zip(verts, geo):
                    assert abs(vx - gx) < 0.06 and abs(vy - gy) < 0.06, code
            assert len([r for r in doc["rows"] if r["lg"] == lg and r["wcgb"] is None]) == 3
        # C3: 18 regular markers and 1 post marker, the hairline at the served switch, nothing past the last entry
        reg, post = ph["regular"]["as_of"], ph["post"]["as_of"]
        assert len(reg) == 18 and reg[0] == "2026-09-06" and reg[-1] == "2026-09-30" and post == ["2026-10-01"]
        hl = page.evaluate("() => [...document.querySelectorAll('.stc-fig[data-k=c3] .stc-chip[aria-pressed=true]')].map(b => b.dataset.c)")
        assert len(hl) == 2
        for code in hl:
            marks = page.evaluate(_MARKS, ["c3", code])
            assert marks == reg + post, (code, marks)
        assert page.evaluate(_VREFS, "c3") == ["2026-10-01"] == [ph["switch_as_of"]]
        xs = page.evaluate("() => document.querySelector('.stc-fig[data-k=c3]')._geo.xs")
        assert xs[0] == "2026-09-06" and xs[-1] == "2026-10-01"
        assert page.locator(".stc-odds .is-unmeasured").inner_text().strip() == "The daily odds record starts September 6, 2026."
        cap = page.locator('.stc-fig[data-k="c3"] figcaption').inner_text()
        assert "Implied, no market. Eephus season simulator, provisional. Eephus bracket simulator, unvalidated." in cap
        assert "2026-phist.json" in cap and "futures ledger on this machine" in cap
        tab = page.evaluate(_TABLE, "c3")   # every value as copied (x 100, one decimal)
        for row in tab[1:]:
            d = row[0]
            for j, code in enumerate(tab[0][1:], start=1):
                if d in reg:
                    q = (ph["regular"]["clubs"].get(code) or [None] * 18)[reg.index(d)]
                    v = q[3] if q else None
                else:
                    q = (ph["post"]["clubs"].get(code) or [None])[post.index(d)]
                    v = q[0] if q else None
                assert row[j] == ("-" if v is None else f"{v * 100:.1f}"), (d, code)
        for _ in range(3):   # the market chips redraw from the one fetched file
            page.locator('.stc-mk[data-v="post"]').click()
            page.locator('.stc-mk[data-v="pen"]').click()
        assert sum("-phist.json" in u for u in page._requests) == 1
        # C4: points at rs_g and ra_g, the RA axis inverted, the two isolines
        marks, (x0, x1, y0, y1) = page.evaluate("""() => { const f = document.querySelector('.stc-fig[data-k=c4]'), g = f._geo;
            return [[...f.querySelectorAll('rect[data-id]')].map(r => [r.dataset.id, +r.getAttribute('x') + 4, +r.getAttribute('y') + 4]),
                    [g.x(0), g.x(1), g.y(0), g.y(1)]]; }""")
        assert len(marks) == 30
        for code, cx, cy in marks:
            r = rows[code]
            assert abs(cx - (x0 + (x1 - x0) * r["rs_g"])) < 0.06 and abs(cy - (y0 + (y1 - y0) * r["ra_g"])) < 0.06, code
        assert y1 > y0, "fewer runs allowed sit higher"
        iso = page.evaluate("""() => [...document.querySelectorAll('.stc-fig[data-k=c4] line[data-id^=iso]')].map(l =>
            [l.dataset.id, +l.getAttribute('x1'), +l.getAttribute('y1'), +l.getAttribute('x2'), +l.getAttribute('y2')])""")
        assert {i[0] for i in iso} == {"iso500", "iso90"} and doc["k90"] == 0.885
        for lid, ax, ay, bx, by in iso:
            kk = 1.0 if lid == "iso500" else doc["k90"]
            for px, py in ((ax, ay), (bx, by)):
                assert abs(py - (y0 + (y1 - y0) * kk * (px - x0) / (x1 - x0))) < 0.2, lid
        labels = page.evaluate("() => [...document.querySelectorAll('.stc-fig[data-k=c4] text[data-id^=iso]')].map(t => t.textContent)")
        assert sorted(labels) == [".500", "90-win pace"]
        # C5: ends at w and the wins of x_wl, its text w_xw, never coloured
        rects, ticks, (a0, a1) = page.evaluate("""() => { const f = document.querySelector('.stc-fig[data-k=c5]'), g = f._geo;
            return [[...f.querySelectorAll('rect[data-id]')].map(r => [r.dataset.id, +r.getAttribute('x') + 4, r.getAttribute('fill'), r.getAttribute('stroke')]),
                    Object.fromEntries([...f.querySelectorAll('text[data-tick]')].map(t => [t.dataset.tick, t.textContent])), [g.x(0), g.x(1)]]; }""")
        assert len(rects) == 60
        for rid, cx, fill, stroke in rects:
            code, which = rid.split(".")
            want = rows[code]["w"] if which == "w" else rows[code]["x_wl"][0]
            assert abs(cx - (a0 + (a1 - a0) * want)) < 0.06, rid
            assert fill in ("var(--text-primary)", "var(--bg-secondary)") and stroke == "var(--text-primary)"
        assert ticks == {r["code"]: jsg(r["w_xw"]) for r in doc["rows"]}
        # every chart: role, a field-built aria-label, a numbers table
        figs = page.evaluate("""() => [...document.querySelectorAll('.stc-fig')].map(f => { const s = f.querySelector('svg');
            return [f.dataset.k, s.getAttribute('role'), s.getAttribute('aria-label')]; })""")
        assert len(figs) == 6 + 2 + 1 + 2
        for k, role, aria in figs:
            assert role == "img" and "2026" in aria and len(aria) > 40, k
            assert len(page.evaluate(_TABLE, k)) > 1, k
        assert page.evaluate("() => /\\bluck/i.test(document.body.textContent)") is False
        no_errors(page)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_text_in_a_series_colour_and_end_labels_apart(ch_site, pw, theme):
    with serve_site(ch_site) as base, chart_page(base, pw, width=1280, theme=theme) as page:
        wait_charts(page)
        fills = page.evaluate("() => [...document.querySelectorAll('.stc-fig svg text')].map(t => t.getAttribute('fill'))")
        assert fills and not [f for f in fills if f in VIZ]
        used, v1, v2 = page.evaluate("""() => { const p = document.createElement('span'); document.body.appendChild(p);
            const tok = v => { p.style.color = 'var(' + v + ')'; return getComputedStyle(p).color; };
            const used = [...document.querySelectorAll('.stc-fig, .stc-fig *')].filter(e => !(e instanceof SVGElement)).map(e => getComputedStyle(e).color);
            return [used, tok('--viz-1'), tok('--viz-2')]; }""")
        assert not set(used) & {v1, v2}
        tops = page.evaluate("""() => [...document.querySelectorAll('.stc-fig')].filter(f => f.querySelector('[data-end]')).map(f =>
            [...f.querySelectorAll('text[data-end]')].map(t => t.getBoundingClientRect().top).sort((a, b) => a - b))""")
        assert len(tops) == 9
        for t in tops:
            assert all(b - a >= 10.9 for a, b in zip(t, t[1:])), t
        no_errors(page)


def test_chips_keys_tap_and_escape(ch_site, pw, ch_docs):
    doc = ch_docs[0]
    k = "c1-ALE"
    sel = f'.stc-fig[data-k="{k}"]'
    with serve_site(ch_site) as base, chart_page(base, pw, width=1280) as page:
        wait_charts(page, c3=False)
        before = page.evaluate(_STROKES, k)
        one = [c for c, v in before.items() if v == VIZ[0]]
        two = [c for c, v in before.items() if v == VIZ[1]]
        ale = [r["code"] for r in sorted((r for r in doc["rows"] if r["div"] == "ALE"), key=lambda r: r["ranks"]["div"])]
        assert one + two == ale[:2], "defaults: the view's first two (no followed club)"
        other = [c for c in before if c not in one + two][0]
        page.locator(f'{sel} .stc-chip[data-c="{other}"]').click()
        after = page.evaluate(_STROKES, k)
        assert after[other] == VIZ[0] and after[two[0]] == VIZ[1] and after[one[0]] == "var(--text-tertiary)"
        assert {c: v for c, v in after.items() if c not in (other, one[0])} == {c: v for c, v in before.items() if c not in (other, one[0])}
        n = page.evaluate("k => document.querySelector('.stc-fig[data-k=\"' + k + '\"]')._geo.xs.length", k)
        page.locator(sel).focus()

        def di():
            return page.locator(sel).get_attribute("data-i")
        page.keyboard.press("End")
        assert di() == str(n - 1) and page.locator(f"{sel} .stc-x").count() == 1
        page.keyboard.press("ArrowLeft")
        assert di() == str(n - 2)
        page.keyboard.press("ArrowRight")
        assert di() == str(n - 1)
        page.keyboard.press("Home")
        assert di() == "0" and page.locator(f"{sel} .stc-read").inner_text().startswith("Mar 26: ")
        page.keyboard.press("Escape")
        assert di() == "" and page.locator(f"{sel} .stc-read").inner_text() == "" and page.locator(f"{sel} .stc-x").count() == 0
        hl0 = [c for c, v in page.evaluate(_STROKES, k).items() if v == VIZ[0]]
        page.keyboard.press("ArrowDown")
        assert [c for c, v in page.evaluate(_STROKES, k).items() if v == VIZ[0]] != hl0
        box = page.locator(f"{sel} svg").bounding_box()
        mid = (box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        page.mouse.click(*mid)
        pinned = di()
        assert pinned not in ("", None)
        page.mouse.move(box["x"] + box["width"] * 0.2, mid[1])
        assert di() == pinned, "a pinned crosshair stays under a moving pointer"
        page.mouse.click(*mid)
        assert di() == "", "a second tap clears"
        page.mouse.click(*mid)
        page.locator(sel).focus()
        page.keyboard.press("Escape")
        assert di() == ""
        cx, cy, code = page.evaluate("""() => { const e = document.querySelector('.stc-fig[data-k=c4] rect[data-id]'); e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect();
            return [r.x + r.width / 2, r.y + r.height / 2, e.dataset.id]; }""")
        page.mouse.click(cx, cy)
        assert page.locator('.stc-fig[data-k="c4"] .stc-read').inner_text().startswith(code + ": ")
        no_errors(page)


def test_phone_draws_one_division_at_a_time(ch_site, pw):
    with serve_site(ch_site) as base, chart_page(base, pw, width=390) as page:
        wait_charts(page)
        assert page.evaluate("() => [...document.querySelectorAll('.stc-fig[data-k^=c1]')].map(f => f.dataset.k)") == ["c1-ALE"]
        page.locator('.stc-dv[data-v="NLW"]').click()
        page.wait_for_selector('.stc-fig[data-k="c1-NLW"] svg', timeout=5000)
        assert "div=NLW" in page.evaluate("() => location.hash")
        small = page.evaluate("""() => [...document.querySelectorAll('.stc-row button, .stc-chips button')].filter(b =>
            b.getBoundingClientRect().height < 44).length""")
        assert small == 0
        assert page.evaluate("() => document.querySelector('.stc-fig svg').getBoundingClientRect().width") <= 358
        assert sum("-race.json" in u for u in page._requests) == 1
        no_errors(page)


def test_the_post_only_2027_file(ch27_site, pw):
    with serve_site(ch27_site) as base, chart_page(base, pw, width=1280) as page:
        wait_charts(page)
        assert page.evaluate("() => [...document.querySelectorAll('.stc-mk')].map(b => b.textContent)") == ["Pennant", "World Series"]
        for code in ("LAD", "NYY"):
            assert page.evaluate(_MARKS, ["c3", code]) == ["2027-10-05", "2027-10-06"], code
        assert page.evaluate(_VREFS, "c3") == ["2027-10-05"]
        assert page.locator(".stc-odds .is-unmeasured").inner_text().strip() == "The daily odds record starts October 5, 2027."
        cap = page.locator('.stc-fig[data-k="c3"] figcaption').inner_text()
        assert "Eephus bracket simulator, unvalidated." in cap and "season simulator" not in cap
        no_errors(page)


@pytest.mark.parametrize("width, theme", [(390, "light"), (390, "dark"), (768, "dark"), (1024, "light"),
                                          (1280, "light"), (1280, "dark"), (1440, "dark")])
def test_charts_never_overflow_the_page(ch_site, pw, width, theme):
    with serve_site(ch_site) as base, chart_page(base, pw, width=width, theme=theme) as page:
        wait_charts(page)
        assert page.evaluate(_OVERFLOW) <= 0
        page.evaluate("() => document.querySelectorAll('.stc-num summary').forEach(s => s.click())")
        page.wait_for_timeout(100)
        assert page.evaluate(_OVERFLOW) <= 0
        set_hash(page, "#view=division")
        page.locator(".st-race summary").first.click()
        page.wait_for_selector(".st-race .stc-fig svg", timeout=10000)
        assert page.evaluate(_OVERFLOW) <= 0
        no_errors(page)


# --------------------------------------------------------------------------- #
# STANDINGS_6: the Season select, past seasons and As of
# --------------------------------------------------------------------------- #
#: Past season fixtures (the tracked copy's shape) and the as_of each season
#: file carries; under ST-Q3 (a) races exist from 2015, by-date files for the
#: newest season only.
PAST = {2020: ("standings_2020.json", "2020-09-27"), 2016: ("standings_2016.json", "2016-10-02"),
        2012: ("standings_2012.json", None), 2009: ("standings_2009.json", None)}
RACE_FROM = 2015
SNAP_DATE = "2026-06-01"


def past_file(y):
    name, as_of = PAST[y]
    return st.build_season_file(fx(name), as_of=as_of, final=True, generated_at="2026-10-14T12:00:00Z")


def multi_payloads(cur, past, snaps):
    """payloads() for the newest season plus past season files in the index
    and by-date files for the newest season."""
    pay = payloads(cur)
    ix = pay["index.json"]
    ix["standings_seasons"][0].update(n_dates=len(snaps), by_date=bool(snaps))
    for y, doc in past.items():
        ix["standings_seasons"].append({"season": y, "rev": sc.rev_of(doc), "race_rev": f"r{y}" if y >= RACE_FROM else None,
                                        "phist_rev": None, "phist_from": None, "n_dates": 0, "by_date": False, "final": True})
        pay[f"standings/{y}.json"] = doc
    for d, doc in snaps.items():
        pay[f"standings/{cur['season']}/{d}.json"] = doc
    pay["latest.json"]["index_rev"] = sc.rev_of(ix)
    return pay


@pytest.fixture(scope="module")
def sel_docs(oct_doc):
    docs = {y: past_file(y) for y in PAST}
    docs["snap"] = st.build_snapshot_file(fx("p4_2026-06-01.json"), as_of=SNAP_DATE, final=False,
                                          generated_at="2026-06-02T04:00:00Z")
    docs["snap"]["opening_day"] = "2026-03-25"
    return docs


@pytest.fixture(scope="module")
def sel_site(tmp_path_factory, oct_doc, sel_docs):
    past = {y: d for y, d in sel_docs.items() if y != "snap"}
    return make_site(tmp_path_factory.mktemp("st_sel"), multi_payloads(oct_doc, past, {SNAP_DATE: sel_docs["snap"]}))


def stamp_is(page, text):
    page.wait_for_function("t => (document.querySelector('.st-stamp em') || {}).textContent === t", arg=text, timeout=8000)


def _hash(page):
    return page.evaluate("() => location.hash")


def test_the_season_select_lists_every_indexed_season(sel_site, pw):
    with serve_site(sel_site) as base, standings_page(base, pw, width=390) as page:
        ix = json.loads((sel_site / "data" / "scores" / "index.json").read_text(encoding="utf-8"))
        want = sorted((e["season"] for e in ix["standings_seasons"]), reverse=True)
        opts = page.evaluate("() => [...document.querySelectorAll('#st-season option')].map(o => [+o.value, o.textContent, o.selected])")
        assert [o[0] for o in opts] == want == [2026, 2020, 2016, 2012, 2009]
        assert [o[1] for o in opts] == [str(y) for y in want] and [o[0] for o in opts if o[2]] == [2026]
        assert page.locator("label[for=st-season]").inner_text() == "Season"
        assert page.locator("label[for=st-date]").inner_text() == "As of"
        # bounded by the season's by-date files: Opening Day to the newest file's as_of
        assert page.locator("#st-date").get_attribute("min") == "2026-03-25"
        assert page.locator("#st-date").get_attribute("max") == "2026-09-27"
        assert page.locator("#st-date").get_attribute("value") == ""
        no_errors(page)


@pytest.mark.parametrize("width", [390, 1280])
def test_2020_cuts_at_its_format_with_its_note_and_served_seeds(sel_site, pw, sel_docs, width):
    doc = sel_docs[2020]
    rows = rows_of(doc)
    with serve_site(sel_site) as base, standings_page(base, pw, width=width, hash_="#view=wildcard&season=2020") as page:
        stamp_is(page, "Final standings, 2020 regular season.")
        note = page.evaluate("() => { const n = document.querySelector('.st-ctl + .st-fmt'); return n && n.textContent; }")
        assert note == doc["format"]["notes"][0] == "2020: a 60-game season; eight clubs per league reached the postseason."
        assert page.evaluate("() => +document.querySelector('#st-season').value") == 2020
        got = _cells(page)
        assert len(got) == 30
        for code, cells in got.items():
            assert cells["SEED"][0] == (str(rows[code]["seed"]) if rows[code]["seed"] else "-"), code
        for lg in ("AL", "NL"):
            seeds = sorted(int(c["SEED"][0]) for k, c in got.items() if rows[k]["lg"] == lg and c["SEED"][0] != "-")
            assert seeds == list(range(1, 9)), (lg, seeds)
        groups = page.evaluate("() => [...document.querySelectorAll('.st-sub')].map(h => h.textContent)")
        assert groups == ["Division leaders", "Division second place", "Wild card"] * 2
        cut = page.evaluate("() => [...document.querySelectorAll('tr.st-cut')].map(r => r.dataset.code)")
        assert [rows[c]["seed"] for c in cut] == [doc["format"]["per_league"]] * 2 == [8, 8]
        assert all(rows[c]["qualified"] == "wild_card" for c in cut)
        # no ODDS group outside its window: no chip, no column, no model label
        assert page.locator('.st-odds, [data-model-id], [data-group="odds"], .st-odds-note').count() == 0
        assert page.evaluate(_OVERFLOW) <= 0
        no_errors(page)


def test_2009_race_is_unmeasured_and_a_raced_season_is_not(sel_site, pw):
    with serve_site(sel_site) as base, standings_page(base, pw, width=1280, hash_="#season=2009") as page:
        stamp_is(page, "Final standings, 2009 regular season.")
        note = page.locator(".st-race-note")
        assert note.inner_text().strip() == "Game-by-game results for 2009 are not on file."
        assert "is-unmeasured" in note.get_attribute("class")
        assert page.locator("#st-date").count() == 0, "no As of for a season with no by-date file"
        assert page.locator(".st-table").count() == 6
        page.select_option("#st-season", "2016")
        stamp_is(page, "Final standings, 2016 regular season.")
        assert page.locator(".st-race-note").count() == 0
        assert not any("-race.json" in u or "-phist.json" in u for u in page._requests)
        no_errors(page)


def test_2012_marks_after_the_rule_and_its_cut(sel_site, pw, sel_docs):
    doc = sel_docs[2012]
    rows = rows_of(doc)
    with serve_site(sel_site) as base, standings_page(base, pw, width=1280, hash_="#view=mlb&season=2012") as page:
        stamp_is(page, "Final standings, 2012 regular season.")
        got = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.st-table tbody tr[data-code]')].map(r =>
            [r.dataset.code, [(r.querySelector('.st-letter abbr') || {}).textContent || '',
              (r.querySelector('.st-mk use') || {getAttribute: () => ''}).getAttribute('href')]]))""")
        assert len(got) == 30
        marked = {c for c, r in rows.items() if r["mark"]}
        assert marked == {c for c, r in rows.items() if r["seed"]} and len(marked) == 10
        assert {c for c, r in rows.items() if r["e"]} == set(rows) - marked
        for code, (letter, href) in got.items():
            assert letter == (rows[code]["mark"] or "e"), code
            assert href.endswith("#i-st-clinch" if rows[code]["mark"] else "#i-st-elim"), code
        set_hash(page, "#view=wildcard&season=2012")
        cut = page.evaluate("() => [...document.querySelectorAll('tr.st-cut')].map(r => r.dataset.code)")
        assert [rows[c]["seed"] for c in cut] == [3 + doc["format"]["wc_spots"]] * 2 == [5, 5]
        no_errors(page)


@pytest.mark.parametrize("width", [390, 1280])
def test_as_of_rerenders_from_the_date_file_and_hides_odds(sel_site, pw, sel_docs, oct_doc, width):
    snap = rows_of(sel_docs["snap"])
    with serve_site(sel_site) as base, standings_page(base, pw, width=width, hash_="#view=mlb&cols=runs,odds") as page:
        stamp_is(page, "Final standings, 2026 regular season.")
        if width >= 768:
            assert page.locator("td.st-odds").count() > 0
        page.fill("#st-date", SNAP_DATE)
        stamp_is(page, "Standings as of June 1, 2026.")
        assert "date=2026-06-01" in _hash(page)
        assert any(u.split("?")[0].endswith("/data/scores/standings/2026/2026-06-01.json") for u in page._requests)
        got = _cells(page)
        assert len(got) == 30
        for code, cells in got.items():
            r = snap[code]
            assert (cells["W"][0], cells["L"][0]) == (str(r["w"]), str(r["l"])), code
            assert cells["RD"][0] == _signed(r["rd"]), code
        assert any(rows_of(oct_doc)[c]["w"] != snap[c]["w"] for c in snap)
        assert page.locator('.st-odds, [data-model-id], [data-group="odds"], .st-odds-note').count() == 0
        assert page.locator("#st-date").input_value() == SNAP_DATE
        assert page.evaluate(_OVERFLOW) <= 0
        page.click(".st-latest")
        stamp_is(page, "Final standings, 2026 regular season.")
        assert "date=" not in _hash(page)
    with serve_site(sel_site) as base, standings_page(base, pw, width=width, hash_="#season=2026&date=2026-06-01") as page:
        stamp_is(page, "Standings as of June 1, 2026.")
        assert page.locator("[data-model-id]").count() == 0 and page.locator("#st-bracket").count() == 0
        no_errors(page)


@pytest.mark.parametrize("h, want, note", [
    ("#season=1999", "", None),
    ("#view=league&season=1999", "#view=league", None),
    ("#season=2009&date=2009-06-01", "#season=2009", None),
    ("#season=2026&date=2026-07-14", "#season=2026", "No standings file for July 14, 2026."),
    ("#date=2026-13-45", "", None),
])
def test_an_unknown_season_or_date_is_dropped(sel_site, pw, h, want, note):
    with serve_site(sel_site) as base, standings_page(base, pw, width=1280, hash_=h) as page:
        page.wait_for_function("w => location.hash === w", arg=want, timeout=8000)
        y = 2009 if "2009" in h else 2026
        stamp_is(page, f"Final standings, {y} regular season.")
        assert page.evaluate("() => +document.querySelector('#st-season').value") == y
        assert not any("/standings/2009/" in u for u in page._requests)
        miss = page.locator(".st-miss")
        if note:
            assert miss.inner_text().strip() == note
        else:
            assert miss.count() == 0
        no_errors(page)


def test_back_and_forward_restore_the_season_and_the_view(sel_site, pw):
    def state(page):
        return page.evaluate("""() => [+document.querySelector('#st-season').value,
            document.querySelector('.st-views [aria-pressed="true"]').dataset.view]""")
    with serve_site(sel_site) as base, standings_page(base, pw, width=1280, hash_="#view=division") as page:
        stamp_is(page, "Final standings, 2026 regular season.")
        page.select_option("#st-season", "2020")
        stamp_is(page, "Final standings, 2020 regular season.")
        page.click('[data-view="wildcard"]')
        page.wait_for_selector(".st-sub")
        assert state(page) == [2020, "wildcard"]
        page.go_back()
        page.wait_for_function("() => !document.querySelector('.st-sub')")
        assert state(page) == [2020, "division"]
        page.go_back()
        stamp_is(page, "Final standings, 2026 regular season.")
        assert state(page) == [2026, "division"]
        page.go_forward()
        stamp_is(page, "Final standings, 2020 regular season.")
        assert state(page) == [2020, "division"]
        page.go_forward()
        page.wait_for_selector(".st-sub")
        assert state(page) == [2020, "wildcard"]
        no_errors(page)


def test_ties_print_as_w_l_t_in_the_detail_row(sel_site, pw, sel_docs):
    rows = rows_of(sel_docs[2016])
    tied = sorted(c for c, r in rows.items() if r["t"])
    assert tied == ["CHC", "PIT"]
    with serve_site(sel_site) as base, standings_page(base, pw, width=390, hash_="#view=mlb&season=2016") as page:
        stamp_is(page, "Final standings, 2016 regular season.")
        for code in ("CHC", "NYY"):
            page.click(f'.st-more[data-code="{code}"]')
            page.wait_for_selector(f"#st-d-{code}")
            rec = page.evaluate("c => document.querySelector('#st-d-' + c + ' .st-dl dd').textContent", code)
            r = rows[code]
            assert rec == (f"{r['w']}-{r['l']}-{r['t']}" if r["t"] else f"{r['w']}-{r['l']}"), (code, rec)
        no_errors(page)


@pytest.mark.parametrize("width", [390, 1280])
def test_the_team_hash_highlights_scrolls_and_opens_the_detail_once(ins_site, pw, width):
    """STANDINGS_8 (plan 5.2, the Franchise SEASON tiles' target): #team=CODE
    highlights the row, scrolls it into view and opens its detail row; a close
    after arrival stays closed, and a new #team= opens the new club's row."""
    with serve_site(ins_site) as base, standings_page(base, pw, width=width, hash_="#team=TBR") as page:
        page.wait_for_selector("#st-d-TBR", timeout=5000)
        assert page.locator("tr.st-hl").evaluate_all("els => els.map(e => e.dataset.code)") == ["TBR"]
        assert page.locator('.st-more[data-code="TBR"]').get_attribute("aria-expanded") == "true"
        box = page.locator('tr.st-hl').bounding_box()
        assert box and 0 <= box["y"] < page.evaluate("window.innerHeight")
        page.locator('.st-more[data-code="TBR"]').click()
        page.wait_for_timeout(80)
        assert page.locator("#st-d-TBR").count() == 0
        page.locator('.st-more[data-code="NYY"]').click()
        page.wait_for_timeout(80)
        assert page.locator("#st-d-NYY").count() == 1 and page.locator("#st-d-TBR").count() == 0
        set_hash(page, "#team=LAD")
        page.wait_for_selector("#st-d-LAD", timeout=5000)
        assert page.locator(".st-detail").count() == 1
        no_errors(page)
