# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The /diamond/ display pass (2026-10-07).

QREA19  the receipts table does not sort, so its headers do not take the
        pointer cursor the shared .mlbstats-table th rule gives them.
COPY    "not for sale" is said by the banner and the price card heading; the
        masthead and the price card no longer repeat it, and the report-card
        sentence sits on the receipts it introduces.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import build_site

ROOT = Path(__file__).parent
DIAMOND_JS = (ROOT / "assets" / "diamond.js").read_text(encoding="utf-8")


def test_the_diamond_table_does_not_offer_a_sort_cursor():
    assert '".dm-table th{cursor:default}"' in DIAMOND_JS


def test_the_diamond_page_says_not_for_sale_once_above_the_price():
    out = build_site.build_diamond()
    if 'class="card diamond-banner"' not in out:
        pytest.skip("gated build: the banner is a different card")
    assert "Not selling anything yet" not in out
    assert "Nothing is for sale today" not in out
    assert "not switched on" in out.lower()
    i_banner = out.index("diamond-banner")
    i_card = out.index("record against consensus is public")
    assert out.index("The receipts") < i_card, "the report-card line belongs on the receipts"
    assert i_banner < i_card
