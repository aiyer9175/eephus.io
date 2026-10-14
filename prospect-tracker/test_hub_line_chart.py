# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EEPHUS_HUB.lineChart and spark, the shared over-time chart helpers (final
pass Part 8, 8.E: P8.2 owns them; the Scores and F-SCORE plans reuse them).

They were promoted from assets/fa_dpw.js, whose value axis divided the data
range into four equal parts and printed $6.9M / $10.0M / $13.2M / $16.3M /
$19.4M on the served /fa/#view=dpw chart. The hub draws round 1-2-5 ticks with
the domain snapped to them. Pinned here: the ticks, the rule that a periodic x
tick never crowds the last one (the League Averages prototype once printed
"20252026"), hollow markers for a partial season, only the last point marked
past 30 points, the caller's width honoured, role="img" with an aria-label and
a real numbers table, and no text drawn in a series colour.

The hub is evaluated in a blank headless Chromium page. Playwright and chromium
are OPTIONAL; the browser tests skip when they are missing.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
HUB = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
DPW = (ROOT / "assets" / "fa_dpw.js").read_text(encoding="utf-8")

SEASONS = [str(y) for y in range(2000, 2027)]


@pytest.fixture(scope="module")
def page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 - no chromium on this machine
            pytest.skip("chromium unavailable: %s" % e)
        try:
            pg = b.new_page()
            pg.set_content("<!doctype html><html><body><div id='c'></div></body></html>")
            pg.add_script_tag(content=HUB)
            assert pg.evaluate("typeof window.EEPHUS_HUB.lineChart") == "function"
            assert pg.evaluate("typeof window.EEPHUS_HUB.spark") == "function"
            yield pg
        finally:
            b.close()


def _season_series(n_from=2000, n_to=2026, base=0.300, partial=("2020", "2026")):
    return [{"y": str(y), "v": round(base + 0.002 * math.sin(y), 4), "partial": str(y) in partial}
            for y in range(n_from, n_to + 1)]


def _render(page, series, opts):
    """Draw into the page and read back the SVG's parts."""
    return page.evaluate(
        """([series, opts]) => {
          const o = Object.assign({}, opts);
          o.fmt = v => Number(v).toFixed(3);
          const html = window.EEPHUS_HUB.lineChart(series, o);
          const c = document.getElementById('c');
          c.innerHTML = html;
          const svg = c.querySelector('svg');
          if (!svg) return {html: html};
          const texts = Array.from(svg.querySelectorAll('text')).map(t => ({
            s: t.textContent, x: +t.getAttribute('x'), y: +t.getAttribute('y'),
            anchor: t.getAttribute('text-anchor') || 'start', fill: t.getAttribute('fill')}));
          const marks = Array.from(svg.querySelectorAll('circle'))
            .filter(e => e.getAttribute('fill') !== 'transparent')
            .map(e => ({fill: e.getAttribute('fill'), stroke: e.getAttribute('stroke'),
                        cx: +e.getAttribute('cx')}));
          const hits = Array.from(svg.querySelectorAll('circle'))
            .filter(e => e.getAttribute('fill') === 'transparent')
            .map(e => e.querySelector('title') ? e.querySelector('title').textContent : null);
          const t = c.querySelector('details table');
          return {html: html, viewBox: svg.getAttribute('viewBox'), role: svg.getAttribute('role'),
                  aria: svg.getAttribute('aria-label'), texts: texts, marks: marks, hits: hits,
                  tableRows: t ? t.querySelectorAll('tbody tr').length : null,
                  tableHead: t ? Array.from(t.querySelectorAll('thead th')).map(h => h.textContent) : null};
        }""", [series, opts])


# ---------------------------------------------------------------------------
# ticks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lo,hi", [
    (8_102_049, 18_223_389),     # the served /fa/ $/WAR range (realized 2021, 2017)
    (0.2398, 0.2551), (3.71, 4.62), (0.0, 1.0), (15.9, 16.7), (-2.4, 7.9), (101, 104), (4, 4),
])
def test_ticks_are_1_2_5_steps_and_the_domain_snaps_to_them(page, lo, hi):
    nt = page.evaluate("([a, b]) => window.EEPHUS_HUB.niceTicks(a, b)", [lo, hi])
    step = nt["step"]
    mant = step / 10 ** math.floor(math.log10(step) + 1e-9)
    assert round(mant, 6) in (1.0, 2.0, 5.0), nt
    assert nt["lo"] == nt["ticks"][0] and nt["hi"] == nt["ticks"][-1], nt
    assert nt["lo"] <= lo and nt["hi"] >= hi, nt
    for t in nt["ticks"]:
        assert abs(t / step - round(t / step)) < 1e-6, (t, step)
    assert 3 <= len(nt["ticks"]) <= 7, nt


def test_the_served_dpw_range_draws_round_dollar_ticks(page):
    nt = page.evaluate("window.EEPHUS_HUB.niceTicks(8102049, 18223389, {floor: 0})")
    assert nt["ticks"] == [5_000_000, 10_000_000, 15_000_000, 20_000_000], nt


def test_floor_keeps_a_non_negative_quantity_off_negative_ticks(page):
    nt = page.evaluate("window.EEPHUS_HUB.niceTicks(0.001, 0.09, {floor: 0})")
    assert nt["lo"] == 0, nt


def test_the_y_labels_print_the_round_ticks(page):
    r = _render(page, [{"label": "AVG", "color": "var(--viz-1)", "pts": _season_series()}],
                {"xs": SEASONS, "width": 640, "table": False})
    ylabels = [t["s"] for t in r["texts"] if t["anchor"] == "end" and t["x"] < 60]
    vals = [float(s) for s in ylabels]
    steps = {round(b - a, 6) for a, b in zip(vals, vals[1:])}
    assert len(steps) == 1, ylabels


# ---------------------------------------------------------------------------
# x ticks: first and last, and a periodic tick never crowds either
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("width", [320, 360, 640])
def test_a_periodic_tick_never_crowds_the_last_one(page, width):
    r = _render(page, [{"label": "AVG", "color": "var(--viz-1)", "pts": _season_series()}],
                {"xs": SEASONS, "width": width, "every": 5, "table": False})
    H = int(r["viewBox"].split()[3])
    xt = [t for t in r["texts"] if t["y"] == H - 5]
    labels = [t["s"] for t in xt]
    assert labels[0] == "2000" and labels[-1] == "2026", labels
    assert "2025" not in labels, labels
    # no two x labels overlap: 9-unit text, 0.6em a character
    def span(t):
        w = len(t["s"]) * 5.4
        return {"start": (t["x"], t["x"] + w), "end": (t["x"] - w, t["x"]),
                "middle": (t["x"] - w / 2, t["x"] + w / 2)}[t["anchor"]]
    spans = sorted(span(t) for t in xt)
    for a, b in zip(spans, spans[1:]):
        assert a[1] <= b[0], (labels, spans)
    if width >= 640:
        assert {"2005", "2010", "2015", "2020"} <= set(labels), labels


def test_without_every_only_the_first_and_last_ticks_print(page):
    r = _render(page, [{"label": "AVG", "color": "var(--viz-1)", "pts": _season_series()}],
                {"xs": SEASONS, "table": False})
    H = int(r["viewBox"].split()[3])
    assert [t["s"] for t in r["texts"] if t["y"] == H - 5] == ["2000", "2026"]


# ---------------------------------------------------------------------------
# markers
# ---------------------------------------------------------------------------

def test_a_partial_season_is_hollow_and_a_full_one_is_filled(page):
    r = _render(page, [{"label": "AVG", "color": "var(--viz-1)", "pts": _season_series()}],
                {"xs": SEASONS, "table": False})
    assert len(r["marks"]) == 27
    hollow = [m for m in r["marks"] if m["fill"] == "var(--bg-secondary)"]
    filled = [m for m in r["marks"] if m["fill"] == "var(--viz-1)"]
    assert len(hollow) == 2 and len(filled) == 25, r["marks"]
    assert all(m["stroke"] == "var(--viz-1)" for m in hollow)
    # the two hollow points are 2020 and 2026 (the last x position)
    xs = sorted(m["cx"] for m in r["marks"])
    assert sorted(m["cx"] for m in hollow) == [xs[20], xs[26]]


def test_past_30_points_only_the_last_point_is_marked(page):
    pts = [{"y": str(g), "v": 0.2 + 0.001 * (g % 7), "partial": g == 162} for g in range(1, 163)]
    r = _render(page, [{"label": "K%", "color": "var(--viz-1)", "pts": pts}],
                {"xs": [p["y"] for p in pts], "table": False})
    assert len(r["marks"]) == 1, r["marks"]
    assert r["marks"][0]["fill"] == "var(--bg-secondary)"   # the live game is partial
    assert len(r["hits"]) == 162 and all(r["hits"])          # every point still hovers


def test_every_point_carries_a_hit_circle_with_a_title(page):
    r = _render(page, [{"label": "AVG", "color": "var(--viz-1)", "pts": _season_series()}],
                {"xs": SEASONS, "table": False})
    assert len(r["hits"]) == 27
    assert r["hits"][0] == "AVG 2000: %s" % ("%.3f" % _season_series()[0]["v"])


# ---------------------------------------------------------------------------
# width, accessibility, the numbers twin, colour
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("width", [306, 420, 900])
def test_the_callers_width_is_the_viewbox_width(page, width):
    r = _render(page, [{"label": "AVG", "color": "var(--viz-1)", "pts": _season_series()}],
                {"xs": SEASONS, "width": width, "height": 200, "table": False})
    assert r["viewBox"] == "0 0 %d 200" % width
    # the end label sits inside the box
    end = [t for t in r["texts"] if t["x"] > width - 60 and t["anchor"] == "start"]
    assert end and all(t["x"] < width for t in end)


def test_role_aria_and_a_real_numbers_table(page):
    two = [{"label": "All", "color": "var(--viz-1)", "pts": _season_series()},
           {"label": "Catchers", "color": "var(--viz-2)", "pts": _season_series(base=0.290)}]
    r = _render(page, two, {"xs": SEASONS, "aria": "AVG by season, 2000 to 2026"})
    assert r["role"] == "img"
    assert r["aria"] == "AVG by season, 2000 to 2026"
    assert r["tableRows"] == 27
    assert r["tableHead"] == ["Season", "All", "Catchers"]
    assert "(partial)" in r["html"]
    # a default aria-label names the series and the span
    r2 = _render(page, two, {"xs": SEASONS, "table": False})
    assert r2["aria"] == "All and Catchers, 2000 to 2026"
    assert "<details" not in r2["html"]


def test_no_text_is_drawn_in_a_series_colour(page):
    two = [{"label": "All", "color": "var(--viz-1)", "pts": _season_series()},
           {"label": "Catchers", "color": "var(--viz-2)", "pts": _season_series(base=0.3001)}]
    r = _render(page, two, {"xs": SEASONS, "every": 5})
    assert all("viz" not in (t["fill"] or "") for t in r["texts"]), r["texts"]


def test_two_end_labels_that_would_touch_are_pushed_apart(page):
    two = [{"label": "All", "color": "var(--viz-1)", "pts": _season_series()},
           {"label": "Catchers", "color": "var(--viz-2)", "pts": _season_series(base=0.3001)}]
    r = _render(page, two, {"xs": SEASONS, "table": False})
    ends = [t for t in r["texts"] if t["anchor"] == "start" and t["x"] > 500]
    assert len(ends) == 2 and abs(ends[0]["y"] - ends[1]["y"]) >= 11, ends


def test_fewer_than_two_points_draws_nothing(page):
    assert page.evaluate(
        "window.EEPHUS_HUB.lineChart([{label: 'x', color: 'var(--viz-1)', pts: [{y: '2026', v: 1}]}], {})") == ""
    assert page.evaluate("window.EEPHUS_HUB.spark([{y: '2026', v: 1}], {})") == ""


# ---------------------------------------------------------------------------
# spark
# ---------------------------------------------------------------------------

def test_spark_keeps_a_shared_scale_and_a_gap(page):
    r = page.evaluate("""() => {
      const pts = [{y: '2015', v: 10}, {y: '2016', v: 20}, {y: '2018', v: 15, partial: true}];
      const xs = ['2015', '2016', '2017', '2018'];
      const html = window.EEPHUS_HUB.spark(pts, {xs: xs, lo: 0, hi: 40, width: 190, height: 54,
                                                  last: true, tip: p => p.y + ': ' + p.v, aria: 'SP by winter'});
      const c = document.getElementById('c'); c.innerHTML = html;
      const svg = c.querySelector('svg');
      return {viewBox: svg.getAttribute('viewBox'), role: svg.getAttribute('role'),
              aria: svg.getAttribute('aria-label'),
              points: svg.querySelector('polyline').getAttribute('points'),
              stroke: svg.querySelector('polyline').getAttribute('stroke'),
              last: Array.from(svg.querySelectorAll('circle')).filter(e => e.getAttribute('fill') !== 'transparent')
                    .map(e => e.getAttribute('fill')),
              titles: Array.from(svg.querySelectorAll('title')).map(t => t.textContent)};
    }""")
    assert r["viewBox"] == "0 0 190 54" and r["role"] == "img" and r["aria"] == "SP by winter"
    assert r["stroke"] == "var(--viz-1)"
    xy = [tuple(map(float, p.split(","))) for p in r["points"].split()]
    # 2018 sits at the fourth of four slots, not the third: the gap stays a gap
    assert xy[2][0] == pytest.approx(185.0)
    # the shared 0-40 scale, not the series' own 10-20
    assert xy[0][1] == pytest.approx(6 + 30 * 42 / 40, abs=0.05)
    assert r["last"] == ["var(--bg-secondary)"]
    assert r["titles"] == ["2015: 10", "2016: 20", "2018: 15"]


# ---------------------------------------------------------------------------
# fa_dpw.js draws through the hub
# ---------------------------------------------------------------------------

def test_fa_dpw_draws_through_the_hub_and_the_viz_tokens():
    assert "H.lineChart(seriesList" in DPW
    assert "H.spark(pts" in DPW
    assert "<polyline" not in DPW, "fa_dpw.js still draws its own line"
    assert "--dpw-implied:var(--viz-1);--dpw-realized:var(--viz-2)" in DPW
    for literal in ("#1D4ED8", "#C9A227", "#3B7FCC", "#B08526"):
        assert literal not in DPW, "fa_dpw.js still carries its own %s" % literal


def test_the_hub_exports_the_chart_helpers():
    m = re.search(r"window\.EEPHUS_HUB = \{([^}]*)\}", HUB)
    names = {n.strip() for n in m.group(1).split(",")}
    assert {"histogram", "scatter", "lineChart", "spark", "niceTicks"} <= names


# ---------------------------------------------------------------------------
# The generic options STANDINGS_5 added (all opt-in; the defaults above are
# unchanged): vertical hairlines, a shared domain, explicit ticks, labels kept
# a gap apart with leaders, step lines, square markers, gaps that stay gaps,
# chosen end labels, the geo out-param; and on scatter, round ticks, an
# inverted y axis, labelled reference polylines clipped to the plot, squares,
# direct labels and labelled y ticks.
# ---------------------------------------------------------------------------

_DRAW = """([kind, data, opts]) => {
  const o = Object.assign({}, opts, {geo: {}});
  const html = window.EEPHUS_HUB[kind](data, o);
  const c = document.getElementById('c');
  c.innerHTML = html;
  const svg = c.querySelector('svg');
  const g = o.geo;
  const at = (q, a) => Array.from(svg.querySelectorAll(q)).map(e => a.map(k => e.getAttribute(k)));
  return {texts: at('text', ['data-end', 'data-tag', 'data-tick', 'data-id', 'fill', 'x', 'y']).map((t, i) =>
            t.concat([svg.querySelectorAll('text')[i].textContent])),
          lines: at('polyline', ['data-id', 'points', 'stroke', 'stroke-width']),
          rects: at('rect', ['data-id', 'data-x', 'x', 'y', 'width', 'fill', 'stroke']),
          segs: at('line', ['data-id', 'data-vref', 'x1', 'y1', 'x2', 'y2', 'stroke', 'stroke-dasharray']),
          hits: svg.querySelectorAll('circle[fill="transparent"]').length,
          geo: kind === 'lineChart' ? {lo: g.lo, hi: g.hi, xs: g.xs, PL: g.PL, PR: g.PR, PT: g.PT, PB: g.PB, W: g.W, H: g.H,
                                       x0: g.x(g.xs[0]), y0: g.y(0), y10: g.y(10)}
                                    : {x0: g.x(0), x1: g.x(1), y0: g.y(0), y1: g.y(1), W: g.W, H: g.H}};
}"""

DAYS = ["2026-09-%02d" % d for d in range(1, 11)]


def _series(vals, **kw):
    s = {"label": kw.pop("label", "A"), "color": kw.pop("color", "var(--viz-1)"),
         "pts": [{"y": d, "v": v} for d, v in zip(DAYS, vals)]}
    s.update(kw)
    return s


def test_vrefs_dom_yticks_and_geo(page):
    r = page.evaluate(_DRAW, ["lineChart", [_series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])],
                              {"xs": DAYS, "width": 400, "table": False, "dom": [-30, 30],
                               "vrefs": [{"x": DAYS[6], "label": "Postseason"}, {"x": "2026-12-01", "label": "never"}]}])
    assert r["geo"]["lo"] <= -30 and r["geo"]["hi"] >= 30 and r["geo"]["lo"] == -r["geo"]["hi"]
    vref = [s for s in r["segs"] if s[1]]
    assert [s[1] for s in vref] == [DAYS[6]], "a key outside xs draws nothing"
    assert vref[0][6] == "var(--border)" and float(vref[0][2]) == float(vref[0][4])
    assert "Postseason" in [t[-1] for t in r["texts"]] and "never" not in [t[-1] for t in r["texts"]]
    r = page.evaluate(_DRAW, ["lineChart", [_series([10, 20, 30, 40, 50, 60, 70, 80, 90, 95])],
                              {"xs": DAYS, "width": 400, "table": False, "yticks": [0, 25, 50, 75, 100]}])
    assert (r["geo"]["lo"], r["geo"]["hi"]) == (0, 100)
    ylab = [t[-1] for t in r["texts"] if t[5] is not None and float(t[5]) < r["geo"]["PL"]]
    assert ylab == ["0", "25", "50", "75", "100"]


def test_gap_keeps_every_end_label_apart_with_a_leader(page):
    ser = [_series([5] * 10, label=c, id=c, color="var(--text-tertiary)", end=c + " +5", strong=False) for c in "ABCDE"]
    ser[0]["color"], ser[0]["strong"] = "var(--viz-1)", True
    r = page.evaluate(_DRAW, ["lineChart", ser, {"xs": DAYS, "width": 360, "height": 220, "table": False, "gap": 11}])
    ends = sorted((float(t[6]), t[0], t[4], t[-1]) for t in r["texts"] if t[0])
    assert [e[1] for e in sorted(ends, key=lambda e: e[1])] == list("ABCDE")
    ys = [e[0] for e in ends]
    assert all(b - a >= 11 - 1e-6 for a, b in zip(ys, ys[1:])), ys
    fills = {e[1]: e[2] for e in ends}
    assert fills["A"] == "var(--text-primary)" and set(fills[c] for c in "BCDE") == {"var(--text-secondary)"}
    assert not [t for t in r["texts"] if t[4] in ("var(--viz-1)", "var(--viz-2)")], "no text in a series colour"
    leaders = [s for s in r["segs"] if s[6] == "var(--text-tertiary)" and not s[7]]
    assert len(leaders) >= 4, "the moved labels carry a 1 px leader"


def test_step_square_markers_and_breaks(page):
    vals = [10, None, None, 30, None, 20, 20, None, None, 40]
    r = page.evaluate(_DRAW, ["lineChart", [_series(vals, id="A", step=True, sq=True, sw=2.5)],
                              {"xs": DAYS, "width": 400, "table": False, "hits": False}])
    assert r["hits"] == 0
    assert [x[1] for x in r["rects"]] == [d for d, v in zip(DAYS, vals) if v is not None]
    pts = [tuple(map(float, q.split(","))) for q in r["lines"][0][1].split()]
    assert r["lines"][0][3] == "2.5"
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        assert x1 == x2 or y1 == y2, "a step line only runs flat or straight up and down"
    assert pts[-1][0] == max(p[0] for p in pts), "nothing past the last point"
    r = page.evaluate(_DRAW, ["lineChart", [_series(vals, id="A", breaks=True, nomark=True)],
                              {"xs": DAYS, "width": 400, "table": False}])
    assert len(r["lines"]) == 4, "a gap between values starts a new polyline"
    assert not r["rects"]


def test_xticks_never_crowd(page):
    xs = ["2026-%02d-%02d" % (m, d) for m in (3, 4, 5) for d in range(1, 29)]
    r = page.evaluate(_DRAW, ["lineChart", [{"label": "A", "color": "var(--viz-1)", "pts": [{"y": d, "v": i} for i, d in enumerate(xs)]}],
                              {"xs": xs, "width": 300, "table": False, "xticks": ["2026-03-02", "2026-04-01", "2026-05-01"]}])
    H = r["geo"]["H"]
    labs = [t[-1] for t in r["texts"] if t[6] is not None and float(t[6]) == H - 5]
    assert labs[0] == xs[0] and labs[-1] == xs[-1] and "2026-03-02" not in labs


def test_scatter_inverted_nice_lines_squares_tags_and_ticks(page):
    pts = [{"x": 4.0 + i * 0.1, "y": 3.9 + i * 0.12, "id": "C%d" % i, "shape": "sq", "hollow": i % 2 == 1,
            "color": "var(--viz-1)" if i == 0 else "var(--text-tertiary)", "tag": "C%d" % i if i < 2 else None, "strong": i == 0}
           for i in range(12)]
    lines = [{"pts": [[0, 0], [10, 10]], "label": ".500", "dash": "4 3", "id": "iso"},
             {"pts": [[0, 0], [10, 8.85]], "label": "90-win pace", "dash": "4 3", "id": "k"}]
    r = page.evaluate(_DRAW, ["scatter", pts, {"width": 360, "height": 300, "xMin": 3.5, "xMax": 5.5, "yMin": 3.5, "yMax": 5.5,
                                               "nice": True, "yInvert": True, "lines": lines}])
    g = r["geo"]
    assert g["y1"] > g["y0"], "the inverted axis puts the smallest value at the top"
    rect = {x[0]: x for x in r["rects"] if x[0]}
    assert rect["C1"][5] == "var(--bg-secondary)" and rect["C0"][5] == "var(--viz-1)" and rect["C1"][6] == "var(--text-tertiary)"
    for x in r["rects"]:
        if x[0]:
            assert 34 <= float(x[2]) + 4 <= 350 and 16 <= float(x[3]) + 4 <= 266
    segs = [s for s in r["segs"] if s[0] in ("iso", "k")]
    assert {s[0] for s in segs} == {"iso", "k"}
    for s in segs:
        x1, y1, x2, y2 = map(float, s[2:6])
        assert 34 - 0.1 <= min(x1, x2) and max(x1, x2) <= 350 + 0.1 and 16 - 0.1 <= min(y1, y2) and max(y1, y2) <= 266 + 0.1
        assert s[7] == "4 3"
    labels = {t[-1]: t for t in r["texts"]}
    assert ".500" in labels and "90-win pace" in labels
    tags = [t for t in r["texts"] if t[1]]
    assert [t[-1] for t in tags] == ["C0", "C1"] and tags[0][4] == "var(--text-primary)" and tags[1][4] == "var(--text-secondary)"
    assert not [t for t in r["texts"] if t[4] in ("var(--viz-1)", "var(--viz-2)")]
    xt = [float(t[-1]) for t in r["texts"] if t[6] is not None and float(t[6]) == 300 - 34 + 12]
    steps = {round(b - a, 6) for a, b in zip(xt, xt[1:])}
    assert len(steps) == 1 and round(steps.pop(), 6) in (0.5, 1.0, 0.2, 0.25)
    r = page.evaluate(_DRAW, ["scatter", [{"x": 80 + i, "y": i, "shape": "sq"} for i in range(4)],
                              {"width": 300, "height": 120, "yMin": -0.6, "yMax": 3.6, "nice": "x", "yInvert": True, "padR": 36,
                               "yTicks": [{"v": i, "label": "R%d" % i} for i in range(4)] + [{"v": 0, "label": "+6", "right": 1, "id": "R0"}]}])
    right = [t for t in r["texts"] if t[2]]
    assert [(t[2], t[-1]) for t in right] == [("R0", "+6")] and float(right[0][5]) == 300 - 36 + 4
    assert [t[-1] for t in r["texts"] if t[-1].startswith("R")] == ["R0", "R1", "R2", "R3"]


def test_scatter_defaults_are_unchanged(page):
    r = page.evaluate(_DRAW, ["scatter", [{"x": i, "y": i * 2, "label": "p"} for i in range(5)], {"width": 320, "height": 200}])
    assert r["rects"] == [] and r["geo"]["y1"] < r["geo"]["y0"]
    vals = sorted({t[-1] for t in r["texts"]})
    assert "0" in vals and "4" in vals and "8" in vals
