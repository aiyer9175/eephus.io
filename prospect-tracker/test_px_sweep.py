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
its card back). The checks themselves are documented in the tool.

Marked browser and SKIPPED BY DEFAULT: it loads every page 4 times plus the
motion pair (about 48 loads, several minutes, the homepage pulls the large
board payload). Run it with PX_SWEEP=1. Playwright and Chromium are optional;
it skips cleanly without them.
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
