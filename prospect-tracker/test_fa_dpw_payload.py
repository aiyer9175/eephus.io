# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The two things that kept /fa/#view=dpw from ever rendering in production.

The $/WAR detail view shipped broken and stayed broken because both of its
failure modes are silent:

  1. THE FETCH PATH. assets/fa_dpw.js fetched RELATIVE urls
     ("data/fa_meta.json", "data/fa_dpw_series.json") from a document served
     at /fa/, so the browser resolved them to /fa/data/... . Both 404'd, the
     candidate loop fell through, ensureData() returned null and the view
     rendered "The $/WAR series failed to load." Nothing logged, nothing
     failed a build. The house pattern is assets/fa.js::load(), which fetches
     root-absolute `/data/${name}.json`.

  2. THE STALE INLINE. fa_export.py inlines the WHOLE of
     data/fa_dpw_series.json into data/fa_meta.json, and fa_dpw.js prefers the
     fa_meta copy. So a series rewrite that is not followed by a re-export
     leaves the page serving the OLD headline number off the fresh-looking
     file. Measured on 2026-08-04, before the repair: every one of the twelve
     winters disagreed, the 2026 winter by $2.37M/WAR (14,919,577 inlined vs
     17,293,779 post-R7 on disk), and the inlined copy had no `breakdown` key
     at all, which silently empties the realized series and all three
     small-multiple panels.

Regex-over-source is the house pattern for the JS half (see
test_gfx_chip_layout.py, test_no_hardcoded_colors.py); the page's JS cannot be
imported. Comments are stripped before the path scan, because the fix's own
comment quotes the broken url it replaced.

Writers to keep honest: fa_backtest.py writes the series, fa_export.py
inlines it (build_fa_meta_payload), run_monthly step 6 / d10 / d10b call
export_all().
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
JS = ROOT / "assets" / "fa_dpw.js"
META = ROOT / "data" / "fa_meta.json"
SERIES = ROOT / "data" / "fa_dpw_series.json"


# ---------------------------------------------------------------------------
# 1. the payloads agree
# ---------------------------------------------------------------------------

def _payloads():
    for p in (META, SERIES):
        if not p.exists():
            pytest.skip(f"{p.name} not exported on this machine")
    meta = json.loads(META.read_text(encoding="utf-8"))
    series = json.loads(SERIES.read_text(encoding="utf-8"))
    return meta, series


def test_fa_meta_inlines_the_current_dpw_series():
    """fa_meta.json's dpw_series IS data/fa_dpw_series.json, byte for byte.

    fa_dpw.js reads fa_meta FIRST, so if these two ever drift the page serves
    the stale one and looks perfectly healthy doing it. A series rewrite
    without a fa_export re-run fails here.
    """
    meta, series = _payloads()
    inlined = meta.get("dpw_series")
    assert inlined is not None, (
        "fa_meta.json has no dpw_series; fa_export.build_fa_meta_payload "
        "could not read data/fa_dpw_series.json when it last ran")
    assert inlined == series, (
        "fa_meta.json's inlined dpw_series has drifted from "
        "data/fa_dpw_series.json - re-run fa_export.export_all()")


def test_inlined_series_carries_the_fields_the_view_renders():
    """The equality above passes trivially if the series itself goes empty."""
    meta, _ = _payloads()
    s = meta["dpw_series"]
    head = s.get("usd_per_war_by_winter") or {}
    assert len(head) >= 8, f"only {len(head)} winters in the implied series"
    assert all(isinstance(v, (int, float)) and v > 0 for v in head.values())
    # fa_dpw.js:196 reads DATA.breakdown for the realized line and the
    # position/length/tier small multiples. The pre-repair inline had no such
    # key, which drew an implied-only chart and three empty panels.
    bd = s.get("breakdown") or {}
    for block in ("by_winter", "realized", "groups", "thresholds"):
        assert block in bd, f"breakdown.{block} missing from the inlined series"
    assert s.get("method") and s.get("model_version")


# ---------------------------------------------------------------------------
# 2. the fetch paths are root-absolute
# ---------------------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.M)


def _code_only(src: str) -> str:
    """Source with comments removed.

    The repair's own comment names the relative url it replaced, and a naive
    scan would match that. Full-line // comments and /* */ blocks cover every
    comment in this file; string literals here contain no comment markers.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", src))


def test_fa_dpw_js_fetches_root_absolute_data_urls():
    """No relative data/ url survives in fa_dpw.js code.

    /fa/index.html is served from a directory, so every relative url on the
    page resolves under /fa/ . Root-absolute is the only correct form here and
    it is what assets/fa.js already does.
    """
    src = JS.read_text(encoding="utf-8")
    code = _code_only(src)
    bad = re.findall(r"""['"`](?:\.{1,2}/)*data/[^'"`]+['"`]""", code)
    assert not bad, (
        f"relative data/ url(s) in assets/fa_dpw.js: {bad}. "
        "They resolve to /fa/data/... and 404. Use /data/... .")
    # and the positive form: both candidates are present and absolute
    assert '"/data/fa_meta.json"' in code
    assert '"/data/fa_dpw_series.json"' in code


def test_fa_dpw_js_has_no_other_relative_asset_url():
    """Same trap, any other subdirectory the view might reach for later."""
    code = _code_only(JS.read_text(encoding="utf-8"))
    bad = re.findall(
        r"""['"`](?:\.{1,2}/)*(?:assets|img|images|fonts)/[^'"`]+['"`]""", code)
    assert not bad, f"relative asset url(s) in assets/fa_dpw.js: {bad}"


def test_every_fetch_argument_is_root_absolute():
    """Catches a future fetch() added with a bare or ./ path.

    fa_dpw.js fetches through a url variable, so the assertion is on the
    literals that feed it: every quoted path-looking literal in the file is
    either root-absolute or a hash fragment (the view's own back-links).
    """
    code = _code_only(JS.read_text(encoding="utf-8"))
    for lit in re.findall(r"""['"`]([^'"`\s]*\.json)['"`]""", code):
        assert lit.startswith("/"), f"non-absolute json url literal: {lit!r}"


# ---------------------------------------------------------------------------
# 3. M04-08: the board's pricing series is served and reconciles
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["fa_class.json", "fa_class_2028.json",
                                  "fa_class_2029.json"])
def test_board_level_is_the_carry_forward_of_its_served_pricing_series(name):
    """fa_class.dpw_usd (the board eyebrow, every card's $/WAR column) is
    winter_dpw of the series the run re-derived, and that series is now in the
    file. Before 2026-09-25 it was written nowhere, so the board's $17.1M could
    not be traced to any winter a reader could see: the rail and the $/WAR view
    print the committed series, whose 2025-26 winter reads $17.3M."""
    import fa_market as fm
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"{name} not exported on this machine")
    cls = json.loads(p.read_text(encoding="utf-8"))
    if cls.get("dpw_usd") is None:
        pytest.skip(f"{name} did not price")
    ser = cls.get("dpw_series_pricing")
    assert ser, f"{name} carries no dpw_series_pricing"
    want = fm.winter_dpw({int(k): v for k, v in ser.items()}, cls["class_year"])
    assert abs(cls["dpw_usd"] - want) <= 1, (cls["dpw_usd"], want)


def test_fa_meta_names_the_board_pricing_basis():
    meta, _ = _payloads()
    cls = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    pr = meta.get("dpw_pricing")
    assert pr, "fa_meta.json has no dpw_pricing block"
    assert pr["winter_dpw_usd"] == cls["dpw_usd"]
    assert pr["usd_per_war_by_winter"] == cls["dpw_series_pricing"]
    assert pr["class_year"] == cls["class_year"]


def test_dpw_view_no_longer_says_every_future_season_prices_from_it():
    src = JS.read_text(encoding="utf-8")
    assert "Future seasons on this site are priced from it" not in src
    assert "pricingNote(PRICING, head)" in src
    assert "PRICING = j.dpw_pricing" in src
