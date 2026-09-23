# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The value ruler: one seven-tier scale, one file, ten ladders (2026-09-16).

The site used to colour numbers by value in four separate families, each a
four-step text ladder on the same four colours, with the cuts living in seven
different functions across four files (two of which were copies of each other
that had already drifted). The default /projections/ board painted 60.2% of its
500 season cells one colour and the #src=prospect view painted 92.0% one colour,
which is the ask this ruler answers.

What is pinned here, none of it by eye:

  * the ladders live in ONE file and no other asset carries a cut for them;
  * every cut a house rule locks is still a boundary AND still carries the tier
    name it carried before, so no value crosses a boundary it was on the other
    side of yesterday - each old band simply splits in two;
  * red means below zero and nothing else, so no above-average index can take it;
  * a cell is tiered on the number it PRINTS, so a cell reading "4.0" is never
    painted below the 4 cut;
  * the seven tokens exist in both themes, clear the contrast floor on all three
    surfaces a table can sit on, and are separable from their neighbours;
  * the weight channel is opt-in, so display type keeps the weight it owns.

The browser half of the acceptance list (computed colour, real board spread, the
.proj-tot specificity regression) is test_value_ruler_render.py.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
TIERS_JS = ASSETS / "eephus-tiers.js"
SITE_CSS = ASSETS / "site.css"

TIERS = ["elite", "great", "good", "above", "avg", "below", "poor"]


@pytest.fixture(scope="module")
def ruler():
    """The real module, evaluated. No DOM, no page: eephus-tiers.js declares no
    dependency on either, which is itself part of the contract (every JS harness
    on the site has to be able to eval it before the file under test)."""
    ctx = MiniRacer()
    ctx.eval("var window = {};" + TIERS_JS.read_text(encoding="utf-8"))
    return ctx


def _ladders(ruler):
    import json
    return json.loads(ruler.eval("JSON.stringify(EephusTiers.LADDERS)"))


def _tier(ruler, v, fam):
    return ruler.eval(f'EephusTiers.tier({v!r}, {fam!r})')


# --------------------------------------------------------------------------- #
# 1. One file owns every cut
# --------------------------------------------------------------------------- #

# Exempt BY NAME, each for a stated reason:
#   highlightAbove   a chart highlight line, not a cell tier (mlbstats.js)
#   _tmTierOf        shared with the board's tier FILTER and mirrored by
#                    bayes_trade_value._platform_tier; colour never rides it
#   _tbGrade         the letter ladder, mirrored by _trade_value_grade
#   fitClass         /pal/ tier chips read their cuts from data/pal.json
#   pctClass         Savant percentile sliders, deferred to phase 2 unmeasured
#   pwoba_pctile     a percentile is already a rank, so it has no value family
_LADDER_EXEMPT = ("highlightAbove", "_tmTierOf", "_tbGrade", "fitClass",
                  "pctClass", "pwoba_pctile")

_BANNED = ("rem-elite", "rem-good", "rem-avg", "rem-low", "proj-war-",
           "remClass", "hemClass", "wrcClass", "_TB_TIER_COLORS",
           "_tbGradeColor")
# `<identifier> >= <number>) return "<string>"`, which is the shape every
# banding helper on this site had. An `indexOf(x) >= 0) return "..."` guard is
# not one: the operand has to be a bare identifier, not a call result.
_CUT_LITERAL = re.compile(r'[A-Za-z_$][\w$.]*\s*>=\s*-?\d+(?:\.\d+)?\s*\)\s*return\s*"')


def test_the_ladders_live_in_one_file():
    """No asset other than eephus-tiers.js may carry one of the dead class sets,
    one of the dead banding helpers, or the shape of a cut ladder."""
    offenders = []
    for js in sorted(ASSETS.glob("*.js")):
        if js.name == "eephus-tiers.js":
            continue
        text = js.read_text(encoding="utf-8")
        for token in _BANNED:
            if token in text:
                offenders.append(f"{js.name}: {token}")
        for m in _CUT_LITERAL.finditer(text):
            line = text[: m.start()].count("\n") + 1
            ctx = text[max(0, m.start() - 400): m.end()]
            if any(x in ctx for x in _LADDER_EXEMPT):
                continue
            offenders.append(f"{js.name}:{line}: cut ladder literal")
    assert not offenders, (
        "the value ruler is one file. These carry a cut or a dead class set:\n  "
        + "\n  ".join(offenders))


def test_only_the_ruler_block_names_the_tier_colours():
    """assets/*.css may reference --vt-* only from the ruler block and the legend
    chip. A module stylesheet reaching for one is the same defect one layer up."""
    for css in sorted(ASSETS.glob("*.css")):
        if css.name == "site.css":
            assert "--vt-elite" in css.read_text(encoding="utf-8")
            continue
        assert "--vt-" not in css.read_text(encoding="utf-8"), css.name


# --------------------------------------------------------------------------- #
# 2. The locked cuts
# --------------------------------------------------------------------------- #

# family -> {cut: the tier name that cut has carried since before the ruler}.
# `run` at 120 is the ONE recorded exception and it is asserted explicitly: the
# run family gains 140 above today's top cut so the reliever board (REM+ to 200
# on the served artifact) can separate its top from its merely very good, which
# means a 120 reads `great` rather than `elite`. Both are bold teal and 120 is
# still a boundary. Everything else keeps its word.
LOCKED = {
    "z":     {120: "elite", 107: "good", 93: "avg"},
    "run":   {120: "great", 107: "good", 93: "avg"},
    "ratio": {130: "elite", 112: "good", 88: "avg"},
    "wrc":   {145: "elite", 120: "good", 85: "avg"},
}


def test_the_locked_cuts_keep_their_tier(ruler):
    lads = _ladders(ruler)
    for fam, want in LOCKED.items():
        cuts = lads[fam]["cuts"]
        for cut, name in want.items():
            assert cut in cuts, f"{fam}: {cut} is no longer a boundary"
            assert _tier(ruler, cut, fam) == name, (
                f"{fam}: {cut} now paints {_tier(ruler, cut, fam)!r}, not {name!r}")
            # and it is a real boundary: one step below is a dimmer tier
            below = cut - (0.5 if cut < 10 else 1)
            assert TIERS.index(_tier(ruler, below, fam)) > TIERS.index(name), (
                f"{fam}: {cut} is not a boundary, {below} paints the same tier")


def test_the_index_ladders_are_strict_refinements(ruler):
    """Every OLD band splits in two; nothing crosses. Asserted as the old
    four-band read against the new seven-tier read on a dense sweep."""
    old = {  # the pre-ruler ladders, verbatim, as the four surfaces banded them
        "z":     [(120, "elite"), (107, "good"), (93, "avg")],
        "ratio": [(130, "elite"), (112, "good"), (88, "avg")],
        "wrc":   [(145, "elite"), (120, "good"), (85, "avg")],
    }
    groups = {"elite": {"elite"}, "good": {"great", "good"},
              "avg": {"above", "avg"}, "low": {"below"}}
    # Swept on the PRINTED value, which is what these columns show (fInt). The
    # ruler rounds before it compares, so a 92.5 reading "93" is `avg` where the
    # old code painted the raw 92.5 low - that is section 3.1 working, not a
    # refinement violation, and it is pinned separately.
    for fam, table in old.items():
        for v in range(40, 201):
            was = next((lab for cut, lab in table if v >= cut), "low")
            now = _tier(ruler, v, fam)
            assert now in groups[was], (fam, v, was, now)


# --------------------------------------------------------------------------- #
# 3. Shape
# --------------------------------------------------------------------------- #

def test_every_ladder_is_five_strictly_decreasing_cuts(ruler):
    """Five cuts, six positive tiers. "Decreasing" is in QUALITY order: a `lo`
    family (FIP) reads better as the number falls, so its cuts ascend.

    The inventory is pinned so a ladder cannot appear without someone saying
    why. `warProspect` was added 2026-09-18 with a reason on the record: when
    the board moved from the if-healthy path to the expected value, the whole
    prospect pool fell under the war ladder's bottom cut of 1.5 and the view
    went to one colour. It is a second ruler of the same SHAPE on a different
    population, not a softer ruler on the same one -- see
    test_the_prospect_ladder_is_the_war_ladder_on_its_own_pool, which measures
    that claim against the served board instead of asserting it in prose. Its
    first cuts were fitted to the war shares as they read on 2026-09-16, which
    was the IF-HEALTHY display; they were refitted on 2026-09-18b."""
    lads = _ladders(ruler)
    assert set(lads) == {"war", "warProspect", "rosterWar", "z", "run", "ratio",
                         "wrc", "woba", "fip", "surplus", "trade"}, sorted(lads)
    for fam, L in lads.items():
        cuts = L["cuts"]
        assert len(cuts) == 5, (fam, cuts)
        assert L["dir"] in ("hi", "lo"), (fam, L["dir"])
        order = cuts if L["dir"] == "hi" else [-c for c in cuts]
        assert all(a > b for a, b in zip(order, order[1:])), (fam, cuts)


def test_red_is_only_below_zero(ruler):
    """A family declares neg only when its value can genuinely be negative, and
    its last positive cut then sits at or above zero, so red is EXACTLY the set
    of negative numbers. An above-average index can never take it."""
    lads = _ladders(ruler)
    assert {f for f, L in lads.items() if L["neg"]} == {"war", "warProspect",
                                                       "surplus", "trade"}
    for fam, L in lads.items():
        if L["neg"]:
            assert L["cuts"][-1] >= 0, (fam, L["cuts"])
            assert _tier(ruler, -0.1, fam) == "poor", fam
            assert _tier(ruler, 0, fam) != "poor", fam
        else:
            lo, hi = min(L["cuts"]), max(L["cuts"])
            span = hi - lo
            for i in range(0, 401):
                v = lo - span + (span * 3) * i / 400.0
                assert _tier(ruler, v, fam) != "poor", (fam, v)


def test_tier_is_monotone(ruler):
    """Sweep each ladder's range: the tier never IMPROVES as the value falls
    (inverted for dir "lo"). A ladder that is not monotone is a ladder that
    paints a worse number a better colour somewhere."""
    lads = _ladders(ruler)
    for fam, L in lads.items():
        lo, hi = min(L["cuts"]), max(L["cuts"])
        span = max(hi - lo, 1e-9)
        xs = [lo - span + (3 * span) * i / 600.0 for i in range(601)]
        if L["dir"] == "lo":
            xs.reverse()
        prev = 0
        for v in xs[::-1]:            # walk from best to worst
            idx = TIERS.index(_tier(ruler, v, fam))
            assert idx >= prev, (fam, v, TIERS[prev], TIERS[idx])
            prev = idx


def test_a_cell_is_tiered_on_the_number_it_prints(ruler):
    """The board prints fmtWar(3.97) as "4.0" and used to paint it in the sub-4
    colour. Measured disagreement on the final war ladder: 37 of the 500
    default-view season cells, 219 of the 7,709 pooled."""
    assert _tier(ruler, 3.97, "war") == _tier(ruler, 4.0, "war") == "great"
    assert _tier(ruler, 3.94, "war") == "good"
    assert _tier(ruler, 119.5, "z") == _tier(ruler, 120, "z") == "elite"
    assert _tier(ruler, 119.4, "z") == "great"
    assert _tier(ruler, 2.995, "fip") == _tier(ruler, 3.00, "fip") == "elite"
    assert _tier(ruler, 0.3995, "woba") == _tier(ruler, 0.400, "woba") == "elite"


def test_the_family_class_says_which_ruler_drew_the_number(ruler):
    """Nothing in the markup could say whether a 113 was drawn by the z ruler or
    the HEM+ ruler. Now it can, and a test can read it."""
    assert ruler.eval('EephusTiers.cls(113, "z")') == "vt vt-fam-z vt-great"
    assert ruler.eval('EephusTiers.cls(113, "ratio")') == "vt vt-fam-ratio vt-good"
    assert ruler.eval('EephusTiers.clsInk(113, "z")') == "vt-fam-z vt-great"
    assert ruler.eval('EephusTiers.varOf(113, "z")') == "var(--vt-great)"
    for bad in ('EephusTiers.cls(null, "z")', 'EephusTiers.cls("", "z")',
                'EephusTiers.cls(1, "nope")', 'EephusTiers.clsInk(NaN, "z")'):
        assert ruler.eval(bad) == "", bad


def test_the_total_bands_on_the_seasons_it_actually_paints(ruler):
    """clsAvg, not total / horizon. 3.6 WAR over the 2 in-window seasons a
    2029-ETA prospect plays is 1.81/yr (`avg`), not 0.72/yr (`below`).

    clsAvgInk is the same average with the weight opt-in withheld; it is what
    the 5y total call site uses, because `.proj-tot` owns its own 700."""
    assert ruler.eval('EephusTiers.clsAvg(3.6, 2, "war")') == "vt vt-fam-war vt-avg"
    assert ruler.eval('EephusTiers.clsAvg(3.6, 5, "war")') == "vt vt-fam-war vt-below"
    assert ruler.eval('EephusTiers.clsAvg(3.6, 0, "war")') == ""
    assert ruler.eval('EephusTiers.clsAvg(null, 5, "war")') == ""
    assert ruler.eval('EephusTiers.clsAvgInk(3.6, 2, "war")') == "vt-fam-war vt-avg"
    assert ruler.eval('EephusTiers.clsAvgInk(3.6, 5, "war")') == "vt-fam-war vt-below"
    assert ruler.eval('EephusTiers.clsAvgInk(3.6, 0, "war")') == ""
    assert ruler.eval('EephusTiers.clsAvgInk(null, 5, "war")') == ""


# A hand-written tier class is allowed in exactly two shapes, and both are
# recorded here rather than left to a reader to notice:
#   vt-fam-pctile   the /mlbstats/ pWOBA cell, banded on a PERCENTILE, which is
#                   already a rank and so has no ladder family. It still names a
#                   family so the markup says which ruler drew it.
#   data-kind="fallback"  the hitters lineup-card cell with no split line for
#                   this hand: a STATE that reads neutral whatever the number
#                   is, exactly as it did on `rem-avg` before the ruler.
_FAM_EXEMPT = ('vt-fam-', 'data-kind="fallback"')
_VT_CLASS = re.compile(r"vt-(?:elite|great|good|above|avg|below|poor)\b")


def test_every_hand_written_tier_class_names_its_family():
    """The family class is what lets a test read WHICH ruler drew a number
    (audit F4). Every call site that types a tier class by hand, rather than
    taking one from the module, has to say so on the same line."""
    offenders = []
    for js in sorted(ASSETS.glob("*.js")):
        if js.name == "eephus-tiers.js":
            continue
        for i, line in enumerate(js.read_text(encoding="utf-8").splitlines(), 1):
            if _VT_CLASS.search(line) and not any(x in line for x in _FAM_EXEMPT):
                offenders.append(f"{js.name}:{i}: {line.strip()[:90]}")
    assert not offenders, (
        "hand-written tier class with no family and no recorded exemption:\n  "
        + "\n  ".join(offenders))


# --------------------------------------------------------------------------- #
# 3b. What the ruler deliberately does NOT colour
# --------------------------------------------------------------------------- #
# Two surfaces landed beside the ruler and neither takes a tier. Both are
# recorded here rather than left for the next reader to "fix", because in both
# cases the change that looks right would ship a wrong number.

_TIER_HELPERS = ("remCell", "runCell", "hemCell", "wrcCell", "vtCell",
                 "EephusTiers")


def _col_bodies(text, needle):
    """Every column object whose header matches `needle`, cut at the next column
    so a neighbour's formatter can never be read as this one's."""
    out, i = [], text.find(needle)
    while i >= 0:
        nxt = text.find('{ key: "', i + 1)
        out.append(text[i:nxt if nxt > i else i + 1200])
        i = text.find(needle, i + 1)
    return out


def test_raw_ewar_columns_carry_no_ladder():
    """The /mlbstats/ eWAR columns - the eWAR section's player and team boards,
    each board's own eWAR column and the team_war rollup - print a COUNTING
    total and stay uncoloured.

    The ruler owns two WAR ladders and neither was measured on a played season:
    `war` was cut on /projections/ PROJECTED seasons, which are regressed and
    narrower than played ones, and `rosterWar` on the 30 projected club totals.
    Painting season-to-date eWAR on either borrows a ladder from a pool it was
    never measured on, which is the one thing the cut table forbids. Give them a
    family when someone measures their pool; until then this holds the line."""
    js = (ASSETS / "mlbstats.js").read_text(encoding="utf-8")
    bodies = (_col_bodies(js, '{ key: "war", label: "eWAR"')
              + _col_bodies(js, '{ key: "team_war", label: "eWAR"'))
    assert len(bodies) >= 9, f"the eWAR columns moved: found {len(bodies)}"
    offenders = [b.splitlines()[0].strip() for b in bodies
                 if any(h in b for h in _TIER_HELPERS)]
    assert not offenders, (
        "a raw eWAR column took a ladder measured on projected seasons:\n  "
        + "\n  ".join(offenders))


def test_the_salary_path_prices_are_not_tiered():
    """The /projections/ salary path strip prints a COST per season, plus the
    non-tender cell. A salary is not a ranked value - a big one is neither good
    nor bad on its own - so no cut set applies to `sp-s`, and the cell states
    (is-ros / is-guar / is-est / is-cut / is-fa / is-unk) are STATES the payload
    already carries, drawn with a border and a strike, never with a tier colour.

    The per-season `sp-d` figure keeps its sign pair for two reasons: the house
    rule that a sign is not a tier, and the measurement behind the `surplus`
    ladder, whose 100 / 50 / 20 / 5 / 1 cuts were taken on TOTAL surplus. One
    season of it sits under the bottom cut nearly everywhere and would paint the
    strip one colour, which is the defect the ruler exists to remove."""
    js = (ASSETS / "projections.js").read_text(encoding="utf-8")
    i = js.index("function salaryStripHtml(")
    end = js.index("function war1(", i)
    strip = js[i:end]
    assert "proj-sp-c" in strip and "is-cut" in strip, "the salary strip moved"
    assert "EephusTiers" not in strip, (
        "the salary path took a tier; salaries are costs, not ranked values")


# --------------------------------------------------------------------------- #
# 4. The served constants
# --------------------------------------------------------------------------- #

def test_the_served_constants_are_a_subset(ruler):
    """The ruler refines the published cuts; it never replaces them. If one of
    these moves on the server, this fails rather than the board quietly painting
    a different story from the payload."""
    import hitter_export as HE
    import dem_plus as D
    from bayes_trade_value import _TRADE_GRADE_CUTS

    lads = _ladders(ruler)
    assert set(HE.WRC_PLUS_BANDS.values()) <= set(lads["wrc"]["cuts"]), \
        (HE.WRC_PLUS_BANDS, lads["wrc"]["cuts"])
    assert {D.DEM_ELITE, D.DEM_ABOVE, D.DEM_AVG} <= set(lads["z"]["cuts"]), \
        (D.DEM_ELITE, D.DEM_ABOVE, D.DEM_AVG, lads["z"]["cuts"])
    grade_cuts = {float(thr) for thr, _ in _TRADE_GRADE_CUTS}
    assert set(lads["trade"]["cuts"]) <= grade_cuts, \
        (lads["trade"]["cuts"], sorted(grade_cuts))


def test_the_trade_ladder_is_the_grade_ladder_merged(ruler):
    """Every letter falls in exactly one tier, so the Surplus figure and the
    letter beside it can never tell different stories. Monotone by
    construction, asserted on the real cut table."""
    from bayes_trade_value import _trade_value_grade
    want = {"A+": "elite", "A": "great", "A-": "great", "B+": "good", "B": "good",
            "B-": "above", "C": "avg", "D": "below", "F": "poor"}
    seen = {}
    for x10 in range(-2000, 15001):
        mm = x10 / 10.0
        g = _trade_value_grade(mm)
        t = _tier(ruler, mm, "trade")
        seen.setdefault(g, set()).add(t)
    for g, tiers in seen.items():
        assert tiers == {want[g]}, (g, tiers)


# --------------------------------------------------------------------------- #
# 5. The palette
# --------------------------------------------------------------------------- #

_HEX = re.compile(r"^#([0-9A-Fa-f]{6})$")


def _tokens(block: str) -> dict:
    out = {}
    for name, val in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", block):
        out[name] = val.strip()
    return out


def _blocks():
    css = SITE_CSS.read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    light = css.split(":root {", 1)[1].split("\n}", 1)[0]
    dark = css.split('[data-theme="dark"] {', 1)[1].split("\n}", 1)[0]
    return _tokens(light), _tokens(dark)


def _resolve(name, theme, light):
    """One token to a literal hex, following var() aliases. A dark block that
    does not override a token inherits the light one, exactly as the cascade
    does, so the test reads the palette the browser reads."""
    seen = set()
    while True:
        assert name not in seen, f"cyclic token {name}"
        seen.add(name)
        val = theme.get(name, light.get(name))
        assert val, f"token {name} is not defined"
        m = _HEX.match(val)
        if m:
            return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
        m = re.match(r"var\(\s*(--[a-z0-9-]+)\s*\)$", val)
        assert m, f"{name} resolves to {val!r}, neither a hex nor a plain var()"
        name = m.group(1)


def _lum(rgb):
    def ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _lab(rgb):
    def ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _de2000(c1, c2):
    """CIEDE2000. Written out rather than imported so the guard has no
    dependency a machine can be missing."""
    L1, a1, b1 = _lab(c1)
    L2, a2, b2 = _lab(c2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7))) if Cb else 0.5
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30))
         + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6))
         - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dTh = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7)) if Cbp else 0.0
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dTh)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


def test_every_tier_has_a_token_in_both_themes():
    light, dark = _blocks()
    for t in TIERS:
        assert f"--vt-{t}" in light, t
        assert f"--vt-{t}" in dark, t
    assert "--card-gold" in light, (
        "--card-gold is referenced from assets/trademachine.js and was defined in "
        "no stylesheet, so it computed to the empty string in BOTH themes")
    css = SITE_CSS.read_text(encoding="utf-8")
    for t in TIERS:
        assert re.search(r"^\.vt-%s\s*\{[^}]*color:\s*var\(--vt-%s\)" % (t, t),
                         css, re.M), t


def test_contrast_floor():
    """WCAG, computed from the parsed tokens against the three surfaces a table
    can sit on. Measured 2026-09-16, light / dark, on bg-primary / -secondary /
    -tertiary:

        elite  9.39 / 9.81 / 8.58    11.51 / 10.22 / 9.21
        great  5.25 / 5.48 / 4.79     6.84 /  6.07 / 5.48
        good   7.40 / 7.73 / 6.76    15.01 / 13.33 / 12.01
        above  4.73 / 4.94 / 4.32     7.54 /  6.69 / 6.03
        avg    6.69 / 6.98 / 6.11     9.94 /  8.82 / 7.95
        below  5.17 / 5.40 / 4.72     6.18 /  5.49 / 4.95
        poor   5.69 / 5.94 / 5.19     7.11 /  6.31 / 5.69

    AA 4.5 on the first two surfaces. The floor on --bg-tertiary is 4.3: `above`
    is the unchanged --accent-green at 4.32 and an existing condition, and the
    ruler REMOVES the two worse readings it replaces (--accent-cyan 3.97 and
    --text-tertiary 4.27 light, --text-tertiary 3.96 dark)."""
    light, dark = _blocks()
    bad = []
    for label, theme in (("light", {}), ("dark", dark)):
        for t in TIERS:
            fg = _resolve(f"--vt-{t}", theme, light)
            for surf, floor in (("--bg-primary", 4.5), ("--bg-secondary", 4.5),
                                ("--bg-tertiary", 4.3)):
                r = _contrast(fg, _resolve(surf, theme, light))
                if r < floor:
                    bad.append(f"{label} {t} on {surf}: {r:.2f} < {floor}")
    assert not bad, "\n".join(bad)


def test_adjacent_tiers_are_separable():
    """CIEDE2000 at least 10 between neighbours in both themes. Measured
    adjacent minimum 11.1 light (good vs above, the two greens) and 11.9 dark
    (below vs poor). Under simulated deuteranopia the adjacent minimum is 6.0,
    and in every such pair the two tiers are also split by the 700 / 400 weight
    step on the surfaces where they sit side by side."""
    light, dark = _blocks()
    bad = []
    for label, theme in (("light", {}), ("dark", dark)):
        cols = [_resolve(f"--vt-{t}", theme, light) for t in TIERS]
        for i in range(len(TIERS) - 1):
            d = _de2000(cols[i], cols[i + 1])
            if d < 10:
                bad.append(f"{label} {TIERS[i]} vs {TIERS[i+1]}: dE {d:.1f}")
    assert not bad, "\n".join(bad)


def test_the_weight_channel_is_opt_in():
    """Every weight rule in the ruler block keys on the `vt` BASE class, which
    only EephusTiers.cls() emits. The call sites whose element already owns a
    weight (the card tiles at 800, the Upside strip at 700, the dot-ruler value
    at 700, the 5y total at 700) take an INK helper - clsInk, or clsAvgInk for
    the total, which averages like clsAvg and emits like clsInk - so a trailing
    400 can never flatten display type.

    The total is the one that mattered: on clsAvg it emitted `vt`, matched
    `.vt.vt-above { font-weight: 400 }` at 0,2,0, and kept its 700 only because
    `.proj-app .proj-board-table .proj-tot` is 0,3,0. One specificity step is
    not an opt-in rule, it is luck. Now it does not match the weight rule at
    all."""
    css = SITE_CSS.read_text(encoding="utf-8")
    weight_rules = re.findall(r"^([^\n{]*\.vt-[a-z]+[^\n{]*)\{[^}]*font-weight",
                              css, re.M)
    assert weight_rules, "no .vt-* weight rule found at all"
    for sel in weight_rules:
        for part in sel.split(","):
            part = part.strip()
            if not part:
                continue
            assert ".vt." in part, f"weight rule without the vt opt-in: {part}"

    proj = (ASSETS / "projections.js").read_text(encoding="utf-8")
    for needle in ('mlbp-cell-val ${EephusTiers.clsInk(v, "war")}',
                   'proj-tot ${EephusTiers.clsAvgInk(',
                   'EephusTiers.clsInk(v, fam)'):
        assert needle in proj, needle
    assert 'proj-tot ${EephusTiers.clsAvg(' not in proj, (
        "the 5y total is back on clsAvg, which emits the `vt` weight opt-in")
    # and the .proj-tot colour rules match the 0,3,0 rule they have to beat
    for t in TIERS:
        assert (f".proj-app .proj-board-table .proj-tot.vt-{t}") in css, t

def test_the_prospect_ladder_is_the_war_ladder_on_its_own_pool(ruler):
    """THE CLAIM warProspect MAKES, measured on the served artifact rather
    than asserted: a prospect cell and a veteran cell painted one colour
    occupy the same RANK in their own population.

    Two failures this pins. (1) ONE COLOUR. On 2026-09-18 the board moved to
    the expected value; a prospect expected path is P(bucket|FV)-weighted, so
    99.6 percent of the pool landed under the war ladder's bottom cut and the
    view painted one colour. (2) A STALE FIT. The first cuts were set against
    the war ladder's shares as they read one commit earlier, on the if-healthy
    display, and that pool no longer exists.

    Tolerance is 10 points per tier, which is loose on purpose: the prospect
    pool is 813 cells over 17 distinct printed values, so the cut grid cannot
    land the shares exactly. It is tight enough to catch either failure -- the
    old cuts miss `avg` by 37 points and `below` by 13."""
    import json
    from pathlib import Path
    doc = Path(__file__).parent / "data" / "mlb_projections.json"
    if not doc.exists():
        pytest.skip("data/mlb_projections.json not built")
    d = json.loads(doc.read_text(encoding="utf-8"))
    first, H = d["first_season"], d["horizon"]

    def war_at(m, t):
        arr = m.get("war") or []
        if m.get("src") == "prospect":
            off = t - (m["eta"] - first)
            return arr[off] if 0 <= off < len(arr) else None
        return arr[t] if t < len(arr) else None

    def shown(m):
        if m.get("src") != "prospect":
            return m.get("warTotal")
        vals = [war_at(m, t) for t in range(H)]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None

    def shares(cells, fam):
        """Tier every cell in ONE eval: the real tier(), on the real cuts."""
        assert cells, fam
        js = ("JSON.stringify(%s.map(function(v){return EephusTiers.tier(v, %r);}))"
              % (json.dumps(cells), fam))
        got = json.loads(ruler.eval(js))
        return {t: 100.0 * got.count(t) / len(got) for t in TIERS}

    rows = (d.get("vets") or []) + (d.get("prospects") or [])
    top = sorted(rows, key=lambda m: -(shown(m) or 0))[:100]
    default_cells = [war_at(m, t) for m in top for t in range(H)
                     if war_at(m, t) is not None]
    pros_cells = [war_at(m, t) for m in (d.get("prospects") or []) for t in range(H)
                  if war_at(m, t) is not None]
    want = shares(default_cells, "war")
    got = shares(pros_cells, "warProspect")

    # (1) never one colour: no tier may own the pool.
    assert max(got.values()) < 60.0, got
    assert sum(1 for v in got.values() if v >= 1.0) >= 4, got
    # (2) the same shape as the war ladder on its own pool.
    for t in TIERS:
        assert abs(got[t] - want[t]) <= 10.0, (t, got, want)
    # The cuts are on the grid the war formatter PRINTS, so the table means
    # what it says: under a one-decimal round, a cut of 0.65 really cuts at
    # 0.7 and the printed boundary is a fiction.
    for c in _ladders(ruler)["warProspect"]["cuts"]:
        assert abs(round(c, 1) - c) < 1e-9, c
