"""SRE08: the export chip never covers the last header of an exportable table.

assets/eephus-export.js injects a 22 px chip at the top right of every
.eephus-exportable host, over the right end of the header row. Before the fix
the last header cell kept its own 8 px, so a right-aligned label ran under the
chip when it faded in on hover: on /betting/#section=futures at 1280 the text
of 'World Series (implied, no market)' ran to x=1235 under a chip at
1217..1239, and 'Model price (implied)' on the board above did the same.

The injected CSS must reserve right padding on the last header cell of an
.eephus-exportable table at least as wide as the chip plus its right offset,
both read off the chip rule in the same file.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET = ROOT / "assets" / "eephus-export.js"


def test_last_header_reserves_room_for_the_chip():
    src = ASSET.read_text(encoding="utf-8")
    chip = re.search(r"\.eephus-export-chip\{position:absolute;[^}]*?right:(\d+)px;[^}]*?width:(\d+)px;", src)
    reserve = re.search(
        r'"\.eephus-exportable > table > thead > tr > th:last-child[^"]*"[^\n]*?\{padding-right:(\d+)px;\}', src)
    need = int(chip.group(1)) + int(chip.group(2)) if chip else None
    assert chip and reserve and int(reserve.group(1)) >= need, (
        "the last header cell of an .eephus-exportable table must keep at least the chip width plus its "
        "right offset clear (chip %s, reserve %s)" % (chip and chip.groups(), reserve and reserve.group(1)))
