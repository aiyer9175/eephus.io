# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PX-19 and PX-24 (final-pass plan 5.7, V4; owner answer PX-Q1).

The ruler key: EephusTiers.key(el) draws one 6-cell meter per value-ruler
step beside its word, lit cells counting the step (elite 6 down to poor 0);
an index family's key stops at `below`. /mlbstats/ puts it once in each
board's "how to read this board" fold.

The card-foil rarity sprite: i-fv-45 ... i-fv-70 in the shared sprite, the
card outline with one foil corner per FV threshold the rank border uses and
a centre stone at 70; the PROSPX player card header draws it keyed to the
same value as the border (rarityFvOf), and the board header's FV key prints
the threshold numbers only, never a tier word.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")
PROSPX = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
BITS = json.loads((ROOT / "assets" / "eephus-icons.json").read_text(encoding="utf-8"))
TIER_WORDS = ("shine", "foil", "chrome", "holo", "legendary")


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    j = src.index("\n}", i)
    return src[i:j + 2]


# ------------------------------------------------------------ the ruler key

@pytest.fixture(scope="module")
def tiers():
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    ctx = MiniRacer()
    ctx.eval("var window = {};" + TIERS_JS)
    return ctx


def test_the_ruler_key_lights_one_cell_per_step(tiers):
    html = tiers.eval("window.EephusTiers.keyHTML()")
    items = re.findall(r'<li class="vt-(\w+)"><svg class="vt-meter"[^>]*>(.*?)</svg><span>(\w+)</span></li>', html)
    assert [t for t, _m, _w in items] == ["elite", "great", "good", "above", "avg", "below", "poor"]
    for t, cells, word in items:
        assert word == t
        assert cells.count('class="on"') + cells.count('class="off"') == 6
        assert cells.count('class="on"') == {"elite": 6, "great": 5, "good": 4, "above": 3,
                                             "avg": 2, "below": 1, "poor": 0}[t]
    assert 'width="34" height="8" viewBox="0 0 17 4"' in html  # 2x, whole pixels
    assert not re.search(r"\d\.\d", html.split('aria-label="Value ruler key">')[1])


def test_an_index_family_key_stops_at_below(tiers):
    html = tiers.eval("window.EephusTiers.keyHTML({ neg: false })")
    assert html.count("<li ") == 6 and "vt-poor" not in html


def test_key_writes_into_its_element(tiers):
    got = tiers.eval("var el = {innerHTML: ''}; window.EephusTiers.key(el); el.innerHTML")
    assert got == tiers.eval("window.EephusTiers.keyHTML()")


def test_mlbstats_draws_the_key_once_per_board_fold():
    src = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    assert "body + VALUE_RULER_NOTE + rulerKey()" in src
    assert "EephusTiers.keyHTML({ neg: false })" in src


# --------------------------------------------------- the card-foil sprite

def _accent(key: str) -> int:
    return "".join(BITS[key]["rows"]).count("+")


def test_the_rarity_sprite_counts_its_corners():
    keys = ["fv-45", "fv-50", "fv-55", "fv-61", "fv-70"]
    assert all(k in BITS and BITS[k]["group"] == "fv" for k in keys)
    corner = _accent("fv-45")
    assert corner == 7
    assert [_accent(k) for k in keys[:4]] == [corner, 2 * corner, 3 * corner, 4 * corner]
    assert _accent("fv-70") == 4 * corner + 12  # the centre stone
    ink = {k: "".join(r.replace("+", "#") for r in BITS[k]["rows"]) for k in keys}
    assert len(set(ink.values())) == 2  # one card outline; only 70 adds the stone
    for k in keys:  # the label names the threshold, never a tier word
        assert not any(w in BITS[k]["label"].lower() for w in TIER_WORDS)


def test_the_sprite_steps_match_the_rank_border_thresholds():
    border = _fn(PROSPX, "rankNumRarityClass")
    cuts = [int(c) for c in re.findall(r"fv >= (\d+)\) return \"card-rarity-", border)]
    assert cuts == [70, 61, 55, 50, 45]
    steps = re.search(r"const FV_RARITY_STEPS = \[(.*?)\];", PROSPX, re.S).group(1)
    assert [int(c) for c in re.findall(r"\[(\d+), \"card-rarity-", steps)] == cuts


def test_the_player_card_header_draws_the_sprite_off_the_border_value():
    fn = _fn(PROSPX, "fvRaritySpriteHTML")
    assert "rarityFvOf(player)" in fn and 'pxIcoHTML("fv-" + step[0], size)' in fn
    assert 'role="img"' in fn and "FV ${step[0]} and up" in fn
    assert "efvDetailHeaderHTML(p, fvBadge, fvRaritySpriteHTML(p, 24))" in PROSPX
    hdr = _fn(PROSPX, "efvDetailHeaderHTML")
    assert hdr.count("${lead}") == 2  # both label rows (eFV and consensus-only)


def test_the_fv_key_prints_numbers_only():
    fn = _fn(PROSPX, "fvKeyHTML")
    text = re.sub(r"<[^>]+>|\$\{[^}]*\}", " ", fn)
    assert not any(w in text.lower() for w in TIER_WORDS)
    assert "${s[0]}+" in fn and 'pxIcoHTML("fv-" + s[0], 16)' in fn
    assert "rank-num ${s[1]}" in fn  # the real border the board draws
    assert "fvKeyHTML() + header + rows" in PROSPX  # once, in the board header


def test_px_icon_helper_only_draws_pixel_sizes():
    fn = _fn(PROSPX, "pxIcoHTML")
    assert "[12, 16, 24, 32].indexOf(size) < 0" in fn
    assert '"2 2 12 12"' in fn and '"0 0 16 16"' in fn
    assert 'use[href*="/assets/eephus-icons.svg"]' in fn  # the stamped sprite URL
