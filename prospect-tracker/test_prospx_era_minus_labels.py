# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One label, one quantity: the level ERA index never prints as a bare "ERA-".

WHY THIS EXISTS (audit F05-06, 2026-09-09, verified CONFIRMED). Two different
numbers were rendered as "ERA-" on the same MLB pitcher card, and on the Stats tab
side by side: the site's level index (statline.era_minus_level: ERA shrunk toward
the level average by innings, over that average) and the MLB sabermetrics tile
(sabermetrics.era_minus, MLB's park- and league-adjusted figure). On
data/debuts_lite.json 429 MLB statlines carried both, 250 disagreeing by 15 or more
points and 134 by 30 or more. A code comment claimed storage skipped the level
fields on MLB lines; it never did.

The repair is DISPLAY ONLY and that is load-bearing. The era_minus_level FIELD stays
on MLB lines because bayes_trade_value's pitcher disqualifier and the in-browser
RPS+ (computeRelProd) read it; stripping it server-side would move trade values and
RPS+. So this file pins three things:
  1. every display site that prints the level index is guarded to sub-MLB lines;
  2. it is labelled "ERA- lvl" (the leaderboard columns were already qualified);
  3. the model reads of the field are untouched.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _live_lines(src: str) -> list[tuple[int, str]]:
    """(line number, code) with // line comments stripped (URLs survive)."""
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        code = re.sub(r"(^|\s)//.*$", r"\1", line)
        if code.strip():
            out.append((i, code))
    return out


def test_every_display_null_check_of_the_level_index_is_guarded_to_sub_mlb():
    """The three display sites (board list pill, Key-signals rail chip, card pill)
    all gate on `sl.era_minus_level != null`. Each must also require a sub-MLB line,
    the way the RPS+ pill beside them already does."""
    sites = [(n, c) for n, c in _live_lines(_src()) if "sl.era_minus_level != null" in c]
    assert len(sites) >= 3, (
        f"expected the three display sites, found {len(sites)}: {sites}. If a site was "
        "removed, fine; if it was renamed, this test must follow it.")
    unguarded = [(n, c.strip()) for n, c in sites
                 if 'sl.era_minus_level != null && sl.level !== "MLB"' not in c]
    assert not unguarded, (
        "a display of the level ERA index is not guarded to sub-MLB lines, so an MLB "
        f"card prints it beside the MLB sabermetrics ERA- tile again: {unguarded}")


def test_the_level_index_never_prints_under_the_bare_label():
    src = _src()
    live = "\n".join(c for _, c in _live_lines(src))
    # A bare ERA- label interpolating the level field, in either template shape.
    assert not re.search(r">ERA- \$\{(?:v|Math\.round\(sl\.era_minus_level\))\}", live), (
        "a pill prints the level index as bare 'ERA-'")
    assert not re.search(r'key:\s*"ERA-"\s*,\s*value:\s*sl\.era_minus_level', live), (
        "the Key-signals chip prints the level index as bare 'ERA-'")
    assert 'driver: `ERA- ${sl.era_minus_level}' not in live, (
        "the RPS+ driver string labels the level index as bare 'ERA-'")
    # Each surviving display carries the qualified label.
    assert live.count("ERA- lvl ${") >= 3, "the list, card and driver labels must say ERA- lvl"
    assert 'key: "ERA- lvl", value: sl.era_minus_level' in live


def test_the_label_has_a_tooltip_that_says_what_it_is_and_is_not():
    src = _src()
    m = re.search(r"^function eraMinusLevelTip\(\) \{.*?\n\}\n", src, re.S | re.M)
    assert m, "eraMinusLevelTip() is the one tooltip for the level index"
    body = m.group(0)
    assert "level average" in body and "not the ERA-" in body
    assert "no park or league adjustment" in body
    # The only number a definition may type is its own anchor.
    assert set(re.findall(r"\d+", body)) <= {"100"}, re.findall(r"\d+", body)
    assert src.count("eraMinusLevelTip()") >= 4, "list pill, rail chip and card pill all use it"


def test_the_false_mlb_skip_comment_is_gone():
    assert "storage.py:_serialize skips them" not in _src()


def test_the_model_reads_of_the_field_are_untouched():
    """The trap the verifier named: fix the DISPLAY, not the field."""
    src = _src()
    m = re.search(r"^function computeRelProd\(p\) \{.*?\n\}\n", src, re.S | re.M)
    assert m, "computeRelProd moved"
    fn = m.group(0)
    assert "if (sl.era_minus_level == null) return null;" in fn
    assert "100 - sl.era_minus_level" in fn
    assert 'sl.level !== "MLB"' not in fn, "RPS+ must keep reading the field on MLB lines"
    btv = (ROOT / "bayes_trade_value.py").read_text(encoding="utf-8")
    assert 'row.get("era_minus_level")' in btv, (
        "the pitcher disqualifier stopped reading era_minus_level; if that was "
        "deliberate, this pin goes with it")
