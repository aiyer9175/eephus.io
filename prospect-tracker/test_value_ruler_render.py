# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The value ruler as the browser actually paints it (2026-09-16).

test_value_ruler.py pins the ladders and the palette from the files. It cannot
see the CASCADE, and the cascade is where the headline feature of this change
died in review: `.proj-app .proj-board-table .proj-tot` sets colour at
specificity 0,3,0, so a one-class `.vt-*` rule loses to it and the 5y WAR total
stays --text-primary with the tier class sitting right there in its class list.
A driver that counted `.proj-tot.vt-*` BY SELECTOR would have reported success.

So every acceptance item here reads COMPUTED STYLE, never class presence:

  * the default board is not one colour, and no tier owns more than 45% of it;
  * the prospect view is not one colour either;
  * the 5y total is genuinely recoloured, in both themes (the 4.2 regression);
  * every /mlbstats/ headline index column splits;
  * the card and the board paint the same tier on the same number;
  * all seven --vt-* tokens AND --card-gold resolve non-empty in both themes
    (--card-gold was referenced from JS and defined nowhere, which is the class
    of defect a stylesheet scan structurally cannot catch);
  * display type keeps the weight it owns;
  * nothing scrolls sideways at 390 / 768 / 1280 / 1440.

Follows the test_projections_table_fit.py precedent: conftest.serve_site over
loopback, headless Chromium, read-only.
"""
from __future__ import annotations

import contextlib

import pytest

from conftest import serve_site

TIERS = ["elite", "great", "good", "above", "avg", "below", "poor"]
WIDTHS = [390, 768, 1280, 1440]


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@contextlib.contextmanager
def _page(server, path, w=1280, h=900, theme="light", ready=None):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            pg = browser.new_page(viewport={"width": w, "height": h})
            pg.goto(server + path, wait_until="networkidle", timeout=60_000)
            if theme == "dark":
                pg.evaluate("document.documentElement.setAttribute('data-theme','dark')")
            if ready:
                # attached, not visible: /mlbstats/ renders every section into the
                # DOM and shows one, so the first match of a shared selector is
                # routinely inside a section this hash did not open.
                pg.wait_for_selector(ready, timeout=30_000, state="attached")
            pg.wait_for_timeout(400)
            yield pg
        finally:
            browser.close()


_SHARES = """(sel) => {
  const out = {};
  for (const el of document.querySelectorAll(sel)) {
    const c = getComputedStyle(el).color;
    if (!el.textContent.trim()) continue;
    out[c] = (out[c] || 0) + 1;
  }
  return out;
}"""


# One board column by its HEADER, because the cells of a column are not all
# reachable by one attribute: some carry a data-gl hook and some do not.
_COLUMN = r"""(args) => {
  const [rootId, label] = args;
  const root = document.getElementById(rootId);
  const table = root && root.querySelector('.mlbstats-table');
  if (!table) return {};
  const norm = el => el.textContent.trim().replace(/\s+/g, ' ');
  const ths = [...table.querySelectorAll('thead th')];
  const i = ths.findIndex(th => norm(th) === label);
  if (i < 0) return {};
  const out = {};
  for (const tr of table.querySelectorAll('tbody tr')) {
    const td = tr.children[i];
    if (!td) continue;
    const el = td.querySelector('.rem-plus') || td;
    const t = norm(el);
    if (!t || t === '\u2014' || t === '-') continue;
    const c = getComputedStyle(el).color;
    out[c] = (out[c] || 0) + 1;
  }
  return out;
}"""


def _spread(shares):
    n = sum(shares.values())
    return n, len(shares), (max(shares.values()) / n if n else 1.0)


# --------------------------------------------------------------------------- #
# 1. Tokens resolve
# --------------------------------------------------------------------------- #

def test_every_ruler_token_resolves(server):
    """--card-gold returned the EMPTY STRING in both themes on the served page
    before this change, and trademachine.js referenced it three times. A var()
    chain that resolves to nothing makes the whole declaration invalid at
    computed-value time. test_theme_tokens.py cannot see this: it scans
    stylesheets, and the references were in JS inline styles."""
    for theme in ("light", "dark"):
        with _page(server, "trademachine/", theme=theme) as pg:
            got = pg.evaluate(
                """(names) => {
                  const cs = getComputedStyle(document.documentElement);
                  const o = {};
                  for (const n of names) o[n] = cs.getPropertyValue(n).trim();
                  return o;
                }""",
                [f"--vt-{t}" for t in TIERS] + ["--card-gold"])
            empty = [k for k, v in got.items() if not v]
            assert not empty, f"{theme}: unresolved token(s) {empty}"


# --------------------------------------------------------------------------- #
# 2. The boards split
# --------------------------------------------------------------------------- #

def test_the_default_board_is_not_one_colour(server):
    """Measured on the 2026-09-16 artifact: six of seven tiers present, widest
    38.6%. Before the ruler it was four bands with the widest at 60.2%."""
    with _page(server, "projections/", ready="table.proj-board-table tbody tr[data-key]") as pg:
        shares = pg.evaluate(_SHARES, "td.pc-y .proj-war")
    n, k, widest = _spread(shares)
    assert n >= 300, n
    assert k >= 5, (k, shares)
    assert widest <= 0.45, (widest, shares)


def test_the_prospect_view_is_not_one_colour(server):
    """#src=prospect used to be 92.0% one colour on the old ladder. The bottom
    cut at 1.5 rather than 1 is what buys the split; measured four tiers."""
    with _page(server, "projections/#src=prospect",
               ready="table.proj-board-table tbody tr[data-key]") as pg:
        shares = pg.evaluate(_SHARES, "td.pc-y .proj-war")
    n, k, _ = _spread(shares)
    assert n >= 300, n
    assert k >= 3, shares


def test_the_total_is_actually_recoloured(server):
    """THE REGRESSION PIN for the .proj-tot specificity defect. Computed colour,
    in both themes: at least one row's total differs from --text-primary, and
    the total keeps its 700 weight."""
    for theme in ("light", "dark"):
        with _page(server, "projections/", theme=theme,
                   ready="table.proj-board-table tbody tr[data-key]") as pg:
            got = pg.evaluate("""() => {
              const cs = getComputedStyle(document.documentElement);
              const prim = cs.getPropertyValue('--text-primary').trim();
              const probe = document.createElement('span');
              probe.style.color = prim;
              document.body.appendChild(probe);
              const primRgb = getComputedStyle(probe).color;
              probe.remove();
              const tot = [...document.querySelectorAll('.proj-tot')];
              return {
                primRgb,
                colors: [...new Set(tot.map(e => getComputedStyle(e).color))],
                weights: [...new Set(tot.map(e => getComputedStyle(e).fontWeight))],
              };
            }""")
        off = [c for c in got["colors"] if c != got["primRgb"]]
        assert off, (
            f"{theme}: every .proj-tot still computes --text-primary "
            f"({got['primRgb']}). The one-class rule lost to "
            ".proj-app .proj-board-table .proj-tot at 0,3,0.")
        assert got["weights"] == ["700"], got["weights"]


def test_the_leaderboards_are_not_one_colour(server):
    """Each /mlbstats/ player board's headline index column. Measured worst
    34.5% (WAR/PA+). Team rollups are exempt and 6.3 of the spec is the record:
    the league spans 16 points of a 100 + 10z index."""
    boards = [("mlbstats/#section=bullpen", "mlbstats-app-root", "REM+"),
              ("mlbstats/#section=starters", "mlbstats-starters-root", "SEM+"),
              ("mlbstats/#section=hitters", "mlbstats-hitters-root", "HEM+"),
              ("mlbstats/#section=defense", "mlbstats-defense-root", "DEM+")]
    thin = []
    for path, root, label in boards:
        with _page(server, path, ready=f"#{root} .mlbstats-table tbody tr") as pg:
            shares = pg.evaluate(_COLUMN, [root, label])
        n, k, widest = _spread(shares)
        if n < 40:
            thin.append(f"{path}: only {n} cells served")
            continue
        assert k >= 3, (path, shares)
        assert widest <= 0.45, (path, widest, shares)
    if len(thin) == len(boards):
        pytest.skip("; ".join(thin))


# Every element the ruler drew, as (family, printed number) -> tier, read off
# the RENDERED markup. Calling EephusTiers from the page would only prove the
# module agrees with itself; the question is whether both call sites hand it the
# same family for the same column.
_PAINTED = r"""() => {
  const out = [];
  for (const el of document.querySelectorAll('[class*="vt-fam-"]')) {
    const cs = [...el.classList];
    const fam = cs.find(c => c.startsWith("vt-fam-"));
    const tier = cs.find(c => /^vt-(elite|great|good|above|avg|below|poor)$/.test(c));
    if (!fam || !tier) continue;
    // the printed number, without the trailing sub-spans a cell may carry
    let t = "";
    for (const n of el.childNodes) if (n.nodeType === 3) t += n.textContent;
    t = t.trim().replace(/\s+/g, " ");
    if (!t || !/^-?[\d.]+$/.test(t)) continue;
    out.push([fam.slice(7), t, tier.slice(3)]);
  }
  return out;
}"""


def _painted_map(pg):
    got = {}
    for fam, txt, tier in pg.evaluate(_PAINTED):
        got.setdefault((fam, txt), set()).add(tier)
    return got


def test_the_card_and_the_board_paint_the_same_tier(server):
    """Audit F4, closed by construction: one module, and the family class in the
    markup so a test can prove WHICH ruler drew a number.

    This reads MARKUP on both surfaces. The /mlbstats/ boards give (family,
    printed value) -> tier; the /projections/ player card gives the same pairs
    from its tiles, lens and dot ruler; every pair present on both has to agree.
    A card call site passing the wrong family argument - which is exactly the F4
    defect, a 113 HEM+ reading one tier on the card and another on the board -
    fails here and cannot fail in a test that asks the module twice."""
    board = {}
    for path, root in (("mlbstats/#section=hitters", "mlbstats-hitters-root"),
                       ("mlbstats/#section=defense", "mlbstats-defense-root"),
                       ("mlbstats/#section=bullpen", "mlbstats-app-root")):
        with _page(server, path, ready=f"#{root} .mlbstats-table tbody tr") as pg:
            for k, v in _painted_map(pg).items():
                board.setdefault(k, set()).update(v)
    assert board, "no tiered cell on any /mlbstats/ board"

    with _page(server, "projections/",
               ready="table.proj-board-table tbody tr[data-key]") as pg:
        keys = pg.evaluate(
            "() => [...document.querySelectorAll('table.proj-board-table tbody "
            "tr[data-key]')].slice(0, 8).map(tr => tr.dataset.key)")
    assert keys, "no player rows on the board"

    card = {}
    for key in keys:
        with _page(server, "projections/#player=" + key,
                   ready=".mlbp-tile-val, .mlbp-ruler-val") as pg:
            for k, v in _painted_map(pg).items():
                card.setdefault(k, set()).update(v)
    fams = {f for f, _ in card}
    assert fams & {"z", "ratio", "run"}, (
        f"the card painted no index family at all (saw {sorted(fams)})")

    shared = sorted(set(card) & set(board))
    disagree = [f"{f} {v}: card {sorted(card[(f, v)])} board {sorted(board[(f, v)])}"
                for f, v in shared if card[(f, v)] != board[(f, v)]]
    assert not disagree, "the card and the board disagree:\n  " + "\n  ".join(disagree)
    assert len(shared) >= 3, (
        f"only {len(shared)} (family, value) pairs appear on both surfaces; "
        "the comparison is too thin to mean anything")


# --------------------------------------------------------------------------- #
# 3. Geometry and weight
# --------------------------------------------------------------------------- #

def test_display_type_keeps_its_weight(server):
    """The ruler declines the weight channel wherever a rule already owns it:
    .mlbp-tile-val 800, .mlbp-cell-val 700, .mlbp-ruler-val 700, the lens number
    800, .proj-tot 700. Those call sites take an INK helper, so no `vt` base
    class lands on them and no weight rule can reach them.

    Read on REAL player cards, and only on the elements that actually carry a
    tier class. An empty #player= renders none of them, and a page-wide sweep of
    .mlbp-tile-val also picks up the sign-pair tiles (the $412M, the age line)
    that the ruler never touched and that legitimately compute 600 - either way
    the assertion would pass while measuring nothing.

    .mlbp-lens-num is the documented exception: the tier rides the INNER span
    (site.css declares .mlbp-lens-num after the ruler block), so the lens is
    checked for its own 800 plus the presence of a tiered inner span.
    """
    want = {".mlbp-tile-val": "800", ".mlbp-cell-val": "700",
            ".mlbp-ruler-val": "700"}
    with _page(server, "projections/",
               ready="table.proj-board-table tbody tr[data-key]") as pg:
        keys = pg.evaluate(
            "() => [...document.querySelectorAll('table.proj-board-table tbody "
            "tr[data-key]')].slice(0, 8).map(tr => tr.dataset.key)")
    assert keys, "no player rows on the board"
    seen = {sel: set() for sel in want}
    lens = {"n": 0, "tiered": 0, "weights": set()}
    for key in keys:
        with _page(server, "projections/#player=" + key,
                   ready=".mlbp-tile-val, .mlbp-ruler-val") as pg:
            got = pg.evaluate(r"""(sels) => {
              const tiered = e => /(^|\s)vt-fam-/.test(e.className);
              const o = {};
              for (const s of sels) {
                o[s] = [...new Set([...document.querySelectorAll(s)]
                  .filter(tiered).map(e => getComputedStyle(e).fontWeight))];
              }
              const ln = [...document.querySelectorAll('.mlbp-lens-num')];
              o._lens = {
                n: ln.length,
                tiered: ln.filter(e => e.querySelector('[class*="vt-fam-"]')).length,
                weights: [...new Set(ln.map(e => getComputedStyle(e).fontWeight))],
              };
              return o;
            }""", list(want))
        for sel in want:
            seen[sel].update(got[sel])
        lens["n"] += got["_lens"]["n"]
        lens["tiered"] += got["_lens"]["tiered"]
        lens["weights"].update(got["_lens"]["weights"])
    missing = [sel for sel in want if not seen[sel]]
    assert not missing, (
        f"no tiered element found for {missing} over {len(keys)} player cards; "
        "every assertion below it would have been vacuous")
    for sel, w in want.items():
        assert seen[sel] == {w}, (sel, sorted(seen[sel]))
    assert lens["n"] and lens["tiered"], (
        "the defense lens painted no tier on an inner span", lens)
    assert lens["weights"] == {"800"}, sorted(lens["weights"])

    # and the 5y total, which is the one that was carrying the `vt` base class
    # and keeping its 700 on a single specificity step
    with _page(server, "projections/",
               ready="table.proj-board-table tbody tr[data-key]") as pg:
        tot = pg.evaluate(r"""() => {
          const el = [...document.querySelectorAll('.proj-tot')]
            .filter(e => /(^|\s)vt-fam-/.test(e.className));
          return {n: el.length,
                  base: el.filter(e => e.classList.contains('vt')).length,
                  weights: [...new Set(el.map(e => getComputedStyle(e).fontWeight))]};
        }""")
    assert tot["n"] >= 10, tot
    assert tot["base"] == 0, "the 5y total emits the `vt` weight opt-in again"
    assert tot["weights"] == ["700"], tot


@pytest.mark.parametrize("path", ["projections/", "mlbstats/", "trademachine/"])
def test_no_sideways_scroll_with_the_ruler(server, path):
    for theme in ("light", "dark"):
        for w in WIDTHS:
            with _page(server, path, w=w, theme=theme) as pg:
                over = pg.evaluate(
                    "() => document.documentElement.scrollWidth "
                    "- document.documentElement.clientWidth")
            assert over <= 0, f"{path} {theme} {w}px: {over}px of page scroll"
