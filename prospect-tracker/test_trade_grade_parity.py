# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Trade Board's letter grade is computed TWICE, and only a comment said so.

`bayes_trade_value._trade_value_grade` stamps `trade_value_grade` onto every
exported row, and `assets/trademachine.js:_tbGrade` recomputes the same letter in
the browser off `trade_value_mm` - deliberately, so the Grade column stays in
lock-step with the Surplus column beside it even when a shipped artifact predates
the server-side field. Both copies carried a comment claiming the other one
matched; neither carried a test. A one-cut drift would be invisible: the letter
would simply be wrong for the band between the two thresholds, on a page whose
whole job is to say how much a player is worth.

The same defect class had already shipped in this module twice, which is why the
tier ladder is pinned here too:
  * the evaluator's dollar colors broke at 80/35/12 while the board's tier colors
    broke at 40/20/8, so an $18M asset read plain grey in the evaluator and cyan
    "mid" one tab over (fixed 2026-08-03, `_tmTierOf`);
  * `_platform_tier` put "low" at >= 0 while the bayes compute's own labeler put
    it at >= 2, so one dollar figure could get two tiers depending on which side
    of the re-point produced it (fixed 2026-08-03).

These are MIRRORS, not an import, for the same reason fa.js keeps its own
`formatMetric` (see test_number_format_parity.py): the browser will not pull a
Python module. A mirror that drifts is worse than no mirror, so the drift is what
gets pinned.
"""

from __future__ import annotations

import re
from pathlib import Path

from bayes_trade_value import _TRADE_GRADE_CUTS, _platform_tier, _trade_value_grade

ROOT = Path(__file__).parent
JS = ROOT / "assets" / "trademachine.js"

# `if (v >= 40)  return "A-";` / `if (v >= 40) return "elite";`
_CUT_RE = re.compile(r'if\s*\(\s*v\s*>=\s*(-?[0-9.]+)\s*\)\s*return\s*"([^"]+)"\s*;')
# the ladder's final unconditional fallthrough: `return "F";`
_FALLTHROUGH_RE = re.compile(r'return\s*"([^"]+)"\s*;\s*\}\s*$')


def _body(name: str) -> str:
    """The body of `function <name>(...) { ... }`, brace-matched."""
    js = JS.read_text(encoding="utf-8")
    start = js.index(f"function {name}(")
    depth, end = 0, -1
    for i in range(js.index("{", start), len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end > 0, f"unbalanced braces in {name}"
    return js[start:end]


def _ladder(name: str) -> tuple[list[tuple[float, str]], str]:
    """The (threshold, label) cuts of a JS `if (v >= x) return "y";` ladder, in
    SOURCE ORDER (first match wins in both languages, so order is part of the
    contract), plus the unconditional fallthrough label."""
    body = _body(name)
    cuts = [(float(t), lab) for t, lab in _CUT_RE.findall(body)]
    tail = _FALLTHROUGH_RE.search(body)
    assert cuts, f"{name}: no `if (v >= n) return \"x\";` cuts found"
    assert tail, f"{name}: no unconditional fallthrough return"
    return cuts, tail.group(1)


def _apply(cuts: list[tuple[float, str]], tail: str, mm: float) -> str:
    """Evaluate an extracted ladder exactly as the browser would."""
    for thr, lab in cuts:
        if mm >= thr:
            return lab
    return tail


# --------------------------------------------------------------------------- #
# Trade Value Grade
# --------------------------------------------------------------------------- #

def test_js_grade_cuts_equal_the_python_table():
    """_tbGrade's thresholds ARE _TRADE_GRADE_CUTS, cut for cut and in order."""
    cuts, tail = _ladder("_tbGrade")
    js_table = cuts + [(float("-inf"), tail)]
    py_table = [(float(thr), lab) for thr, lab in _TRADE_GRADE_CUTS]
    assert js_table == py_table, (
        "assets/trademachine.js:_tbGrade has drifted from "
        "bayes_trade_value._TRADE_GRADE_CUTS. The board recomputes the letter "
        "client-side off trade_value_mm, so a difference means the Grade column "
        "and the exported trade_value_grade disagree on the same player.\n\n"
        f"python: {py_table}\njs:     {js_table}")


def test_grade_agrees_on_every_boundary_and_between_them():
    """Behavioural parity, including the exact cut values.

    Table equality would still pass if one side used `>` where the other used
    `>=`, and every threshold in this ladder is a round number a real surplus
    lands on exactly ($40.0M is the Elite floor AND the A- floor)."""
    cuts, tail = _ladder("_tbGrade")
    probes: list[float] = [-250.0, -0.1, 0.0, 0.1, 250.0]
    for thr, _ in cuts:
        probes += [thr - 0.1, thr, thr + 0.1]
    for mm in sorted(set(probes)):
        assert _apply(cuts, tail, mm) == _trade_value_grade(mm), (
            f"grade disagreement at ${mm}M: js "
            f"{_apply(cuts, tail, mm)!r} vs python {_trade_value_grade(mm)!r}")


def test_the_negative_surplus_grade_is_f_in_both():
    """A contract liability is an F, not a D and not a blank. It is the one row
    of the table with no numeric threshold, so it is the one the regex could
    silently lose."""
    cuts, tail = _ladder("_tbGrade")
    assert tail == "F"
    assert _trade_value_grade(-1.0) == "F"
    assert _apply(cuts, tail, -1.0) == "F"


# --------------------------------------------------------------------------- #
# Tier ladder (the same mirror, one column over)
# --------------------------------------------------------------------------- #

def test_js_tier_cuts_match_platform_tier():
    """The evaluator colors dollars through _tmTierOf; the board colors them
    through the server's trade_value_tier, stamped by _platform_tier. They are
    the same ladder or the same asset is two colors on two tabs."""
    cuts, tail = _ladder("_tmTierOf")
    probes: list[float] = [-99.0, -0.1, 0.0, 0.1, 999.0]
    for thr, _ in cuts:
        probes += [thr - 0.1, thr, thr + 0.1]
    for mm in sorted(set(probes)):
        assert _apply(cuts, tail, mm) == _platform_tier(mm), (
            f"tier disagreement at ${mm}M: js {_apply(cuts, tail, mm)!r} vs "
            f"python {_platform_tier(mm)!r}")


def test_the_board_tier_ladder_and_the_grade_ladder_share_their_floors():
    """The published filter chips promise Elite $40M+ / High $20-40M / Mid
    $8-20M, and the grade comments claim A- sits on the Elite floor and B- on the
    Mid floor. Pin the coincidence so a later cut move cannot quietly break the
    story the two columns tell together."""
    assert _platform_tier(40.0) == "elite" and _trade_value_grade(40.0) == "A-"
    assert _platform_tier(8.0) == "mid" and _trade_value_grade(8.0) == "B-"


def test_the_board_colours_come_from_the_value():
    """The tier-name-to-colour map is gone (2026-09-16). It keyed five colours on
    a tier NAME, one of which (--card-gold) was not a defined token, so the top
    tier computed to the empty string in both themes; and the Grade chip beside
    it was coloured off the LETTER by a second, different map, so the two columns
    could tell different stories about the same player.

    Both are painted from the VALUE now, through one call, on a ladder whose cuts
    are grade cuts. _tmTierOf is deliberately untouched: it is shared with the
    board's tier FILTER and mirrors _platform_tier, and colour must never ride
    the function the filter and the server share."""
    js = JS.read_text(encoding="utf-8")
    assert "_TB_TIER" + "_COLORS" not in js
    assert "_tbGrade" + "Color" not in js
    assert 'function _tbValTier(mm) { return EephusTiers.varOf(mm, "trade"); }' in js
    # ONE colour per row, computed once from the VALUE and used by both cells,
    # so the Surplus figure and the letter chip beside it cannot disagree. It
    # goes through _tmValColor, which is _tbValTier plus the grey fallback the
    # board painted before the ruler: a bare _tbValTier returns "" for an
    # unpriced row and emits style="color:;".
    body = js.split("pagedRows.forEach(", 1)[1][:2000]
    assert "const tvCol = _tmValColor(tv);" in body
    assert "const gradeCol" not in js, "two colour bindings for one row again"
    row = js.split("pagedRows.forEach(", 1)[1]
    chip = row.split("tm-grade-chip", 1)[1][:200]
    assert "color:${tvCol};border-color:${tvCol};" in chip, chip[:120]
    surplus = row.split('class="tm-num tm-surplus"', 1)[1][:120]
    assert "color:${tvCol};" in surplus, surplus[:120]
    assert 'function _tmValColor(mm) { return _tbValTier(mm) || "var(--text-secondary)"; }' in js
    # and every trade cut is a grade cut, so the map is monotone by construction
    ruler = (JS.parent / "eephus-tiers.js").read_text(encoding="utf-8")
    cuts = re.search(r"trade:\s*\{ cuts: \[([^\]]+)\]", ruler).group(1)
    trade = {float(x) for x in cuts.split(",")}
    assert trade <= {float(thr) for thr, _ in _TRADE_GRADE_CUTS}, trade
    # _tmTierOf still exists and still matches the server
    grade_cuts, tail = _ladder("_tmTierOf")
    assert tail == "minimal" and grade_cuts[0][1] == "elite"
