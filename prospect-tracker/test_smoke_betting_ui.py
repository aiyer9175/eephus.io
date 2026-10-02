"""SRE02, SRE03, SRE06, SRE07: the /betting/ header, the Futures loader, the
header chips and the postseason bracket panel at phone width.

SRE02. The header printed '1 games priced' on a one-game slate; it now picks
'game' or 'games' from the payload's n_games.
SRE03. While data/futures.json loaded, the Futures tab printed a bare
'Loading.' paragraph with no lamps; it now draws the shared lamp loader
(assets/eephus-state.js, role=status) and the failed kind (role=alert) when the
fetch rejects.
SRE06. At 390 px the 'vintage graded 777 of 600' chip broke inside its border
box across two lines and overlapped the chips above; a chip is now one unit.
SRE07. At 390 px the nowrap Series now sentence pushed every probability column
of the bracket panel past the scroller's edge; it now wraps at phone width.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = (ROOT / "assets" / "betting.js").read_text(encoding="utf-8")


def _body(name: str) -> str:
    i = SRC.index("function " + name + "(")
    return SRC[i:SRC.index("\n  }\n", i)]


def test_sre02_header_pluralizes_on_n_games():
    body = _body("renderBanner")
    assert '" games priced &middot; "' not in SRC, "the header still hard-codes 'games'"
    assert re.search(r'nGames === 1 \? " game" : " games"\) \+ " priced &middot; "', body), \
        "the header does not choose game or games from n_games"


def test_sre03_futures_loading_uses_the_shared_lamp_loader():
    body = _body("renderFutures")
    assert '<p class="bt-note">Loading.</p>' not in body
    assert 'pxState("loading", esc("Loading the futures board."))' in body
    assert 'if (FUT_ERR) return pxState("failed", esc(FUT_ERR));' in body


def test_sre06_chip_is_one_unit_with_a_row_gap():
    m = re.search(r'"\.bt-chip\{([^}]*)\}"', SRC)
    assert m, "the .bt-chip rule is gone"
    rule = m.group(1)
    assert "white-space:nowrap" in rule and "display:inline-block" in rule
    assert "margin:2px 0 2px 4px" in rule, "wrapped chips need a vertical gap"


def test_sre07_series_now_wraps_at_phone_width():
    assert "'<td class=\"bt-l bt-br-now\">' + esc(c.series_now_text" in _body("brPanel")
    i = SRC.index('"@media (max-width:640px){",')
    tier = SRC[i:SRC.index('"}"', i)]
    m = re.search(r'"\.bt-table td\.bt-br-now\{([^}]*)\}"', tier)
    assert m, "the Series now cell has no phone-width rule"
    assert "white-space:normal" in m.group(1) and "max-width:140px" in m.group(1)
