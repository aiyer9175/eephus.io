# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""T7, the pixel system's served-page sweep (final-pass plan 5.7.4).

Runs tools/px_sweep.py against the site served over loopback HTTP (external
<use> refs do not render over file://): /, /prospx/, the PROSPX player miss,
/ledger/ and its Method tab, /management/, /betting/ and /404.html at 1280 and
390 px in light and dark, and fails on any failure the sweep reports (no
horizontal scroll; icon boxes whole and 12, 16, 24 or 32 px; every icon paints;
the footer mark is the 16 px ball strike; nothing pixel-drawn in a priced
betting card; Reduce Motion runs what no preference runs; the player miss shows
its card back). PB-10 (owner ask 2) adds the lockup checks: every visible pixel
wordmark equals its committed PNG strike at DPR 1 and 2 in both themes (0
pixels off; A Hinted is checked for its crisp edge instead); the nav bar stays
72 px at 1280 and 63 px at 390; no brand-mark animation runs 3.2 s after load;
on / the hero pitch draws the same frames with Reduce Motion as without it over
1.3 s, no layout shift names a wordmark node and the hero box never moves while
it plays. The checks themselves are documented in the tool.

Marked browser and SKIPPED BY DEFAULT: it loads every page 4 times at DPR 1 and
most of them 4 more times at DPR 2, plus the motion pair and the pitch probes
(about 80 loads, about five minutes, the homepage pulls the large board
payload). Run it with PX_SWEEP=1. Playwright and Chromium are optional; it skips
cleanly without them.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

ROOT = Path(__file__).parent


def _sweep():
    spec = importlib.util.spec_from_file_location("px_sweep", ROOT / "tools" / "px_sweep.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(os.environ.get("PX_SWEEP") != "1",
                    reason="the T7 browser sweep runs only with PX_SWEEP=1 (several minutes)")
def test_px_sweep_served_pages(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from conftest import serve_site

    sweep = _sweep()
    with serve_site() as base:
        try:
            rep = sweep.run(base, tmp_path)
        except Exception as e:  # noqa: BLE001 - a missing browser binary is a skip
            if "Executable doesn't exist" in str(e):
                pytest.skip("playwright chromium not installed")
            raise
    assert rep["captures"], "the sweep captured nothing"
    assert not rep["failures"], "T7 failures:\n  " + "\n  ".join(rep["failures"])


def test_sweep_covers_the_plan_pages_and_the_method_tab():
    """The page list is the plan's T7 list plus the two this program added: the
    Ledger Method tab (finding M09-23, 4 px overflow at 390) and the PROSPX
    player miss (PX-20)."""
    sweep = _sweep()
    paths = [p for _, p in sweep.PAGES]
    for want in ("/", "/prospx/", "/ledger/", "/management/", "/betting/", "/404.html",
                 "/ledger/#section=method"):
        assert want in paths, f"T7 no longer sweeps {want}"
    assert any(p.startswith("/prospx/#player=") for p in paths)
    assert sweep.WIDTHS == (1280, 390) and sweep.THEMES == ("light", "dark")
    assert sweep.ICON_SIZES == {12, 16, 24, 32}


def test_pb10_lockup_checks_cover_the_plan():
    """PB-10: DPR 1 and 2, the plan's six surfaces at DPR 2, the measured nav
    heights, every brand animation settled by 3.2 s, and the 1.3 s pitch."""
    sweep = _sweep()
    assert sweep.DPRS == (1, 2)
    keys = {k for k, _ in sweep.PAGES}
    assert set(sweep.DPR2_PAGES) == {"home", "prospx", "ledger", "management", "betting", "404"} <= keys
    assert sweep.NAV_HEIGHT == {1280: 72, 390: 63}
    assert sweep.SETTLE_MS >= 3200
    assert sweep.FRAME_TIMES[0] == 0 and sweep.FRAME_TIMES[-1] == 1300
    assert ".eephus-wordmark-px" in sweep.BRAND_SEL and "svg.h1-logo" in sweep.BRAND_SEL


def test_pb10_strikes_are_the_committed_pngs_at_their_canvas_size():
    """Each lockup scale the pages draw has a committed strike in both themes,
    LOCKUP_W_U font pixels wide per scale step (the 55 u lockup canvas)."""
    sweep = _sweep()
    for s in (2, 4, 6):
        for theme in ("light", "dark"):
            im, got = sweep._strike(s * sweep.LOCKUP_W_U, theme)
            assert got == s and im.size == (s * sweep.LOCKUP_W_U, s * 21), (s, theme, im.size)
            assert im.getextrema()[3] == (0, 255), "a strike is 1-bit: transparent or opaque"


def test_pb10_lockup_compare_finds_its_own_strike_and_rejects_the_other_theme():
    """The comparator on a synthetic page: the light strike pasted on a field at
    a whole-pixel offset is 0 pixels off; the dark strike is not."""
    from PIL import Image

    sweep = _sweep()
    ref, _ = sweep._strike(110, "light")
    page = Image.new("RGBA", (200, 100), (244, 240, 230, 255))
    page.alpha_composite(ref, (31, 17))
    box = {"x": 31, "y": 17, "w": 110, "h": 42, "vbw": 110, "vbh": 42}
    off, n, at = sweep._lockup_off(page, box, "light", 1)
    assert (off, at) == (0, (0, 0)) and n > 500
    assert sweep._lockup_off(page, box, "dark", 1)[0] > n // 2
    big = page.resize((400, 200), Image.Resampling.NEAREST)
    assert sweep._lockup_off(big, box, "light", 2)[0] == 0
