# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""W08_2_PARTNER_SCREEN_FLIP: the glossary entry and the registry row text of
docs/trademachine-2026-10/FLIP_NOTES.md sections 3 and 4, applied as text
edits so each file keeps its own line endings, indent and every other byte.

Idempotent: a second run changes nothing. Usage:
    python tools/flip_trade_partner_screen_text.py [--check]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
FLIP_DATE = "2026-10-09"

ENTRY = {
    "id": "trade_partner_screen",
    "term": "Trade partner screen",
    "category": "site-feature",
    "section": "Value & Contracts",
    "module": ["trademachine"],
    "aliases": ["partner screen", "partner_v1"],
    "priority": 40,
    "definition": ("For one player on the Trade Machine builder, the 29 clubs other than his own "
                   "ordered by a published rule with every factor printed: need at his slot, "
                   "contention, the marginal tax his CBT charge carries, and farm surplus as the "
                   "ability to pay in prospects. A screen, not a rumor board: it makes no claim "
                   "about any trade."),
    "methodology": ("Rule partner_v1, registered before any screen output existed: each "
                    "factor ranks the 29 clubs, ties at their average rank, and scores (29 - rank) / 28; "
                    "an input not on file scores 0.5. Need is the starter's HEM+ at the position with "
                    "team DEM+ for a fielder, Offense+ for a designated hitter, Rotation+ for a starter "
                    "and Bullpen+ for a reliever, lower counting as more need. Contention is Team "
                    "Outlook's 2027 wins on the served frame before the first regular-season game and "
                    "playoff odds after. Tax is the marginal tax of the player's CBT charge at the "
                    "club's payor tier on the Club Ledger's schedule, printed as tax payroll before and "
                    "after, threshold, bracket and payor tier, never as room under a line. Ability to "
                    "pay is farm surplus. The Score adds the four with equal weight, 0 to 4. The org "
                    "trade profile is shown with weight 0. Read from a slim slice of the Franchise "
                    "board and the CBT sidecar; the daily output is frozen and "
                    "hashed for one registered read after the 2027 deadline."),
    "example": "",
    "formula": "Score = Need + Contention + Tax + Ability to pay, each (29 - rank) / 28",
    "seeAlso": ["trade_machine", "cbt_payroll", "payor_tier", "surplus_value", "farm_report_card"],
    "shelf": "ark",
    # FLIP_NOTES section 3 proposed the gate's docs path and the slice's file name in
    # the methodology; copy rule L8 bans both in served copy, so they are left out. It
    # also proposed "eephus wiring W08, owner answer W-OQ4 (a),
    # 2026-10-01"; test_glossary_provenance requires an ark entry's origin to
    # name eephus.io, so the line follows the house form for an Arkmetric rule.
    "origin": "Arkmetric rule, original to eephus.io, over numbers the site already serves.",
}

SURFACE_OLD = ('   "surface": "None served: Trade Machine partner screen v1, built dark behind '
               'TRADE_PARTNER_SCREEN_LIVE (task W08_1); a descriptive screen, never a price, a grade '
               'or a trade value",\n')
SURFACE_NEW = ('   "surface": "Trade Machine partner screen (/trademachine/, under the deal builder): for '
               'a player on the builder, the 29 other clubs ordered by partner_v1 with every factor '
               'printed; a descriptive screen, never a price, a grade or a trade value",\n')
NOTES_TAIL = ' Gate: docs/trademachine-2026-10/TRADE_PARTNER_SCREEN_GATE.md."'


def _flip_note() -> str:
    import trade_partner_screen as T
    return (f" FLIP {FLIP_DATE} (W08_2_PARTNER_SCREEN_FLIP): TRADE_PARTNER_SCREEN_LIVE True; served "
            "data/trade_partner_slice.json (tracked, beside data/franchise_board.json) and "
            "data/trade_partner_screen_chain.json (gitignored, re-rendered nightly from the record's "
            f"chain); the first frozen day is {FLIP_DATE} (machine local, written by the flip's local "
            "build; the box's entries begin with its first nightly after the deferred deploy), "
            f"rule_sha256 {T.rule_sha256()}, rule_py_sha256 {T.rule_py_sha256()}. Still registered, "
            "not read: nothing is scored before the one look.")


def apply_glossary(text: str) -> str:
    """Insert ENTRY after the trade_machine entry. `text` has LF line endings."""
    if '"id": "trade_partner_screen"' in text:
        return text
    anchor = '  },\n  {\n   "id": "milb_translation",'
    assert text.count(anchor) == 1, "glossary anchor (the entry after trade_machine) not found"
    assert text.index(anchor) > text.index('"id": "trade_machine"'), \
        "milb_translation no longer follows trade_machine"
    body = "\n".join("  " + ln for ln in json.dumps(ENTRY, indent=1, ensure_ascii=False).split("\n"))
    return text.replace(anchor, "  },\n" + body + ",\n" + anchor[len("  },\n"):], 1)


def apply_registry(text: str) -> str:
    """Update the trade_partner_screen row's surface, notes and last_checked. LF text."""
    i = text.index('   "model_id": "trade_partner_screen",')
    j = text.index("\n  }", i)
    row = text[i:j]
    if f"FLIP {FLIP_DATE}" in row:
        return text
    assert row.count(SURFACE_OLD) == 1, "the registered surface text moved"
    assert row.endswith(NOTES_TAIL), "the notes line is no longer the row's last line"
    assert '"last_checked"' not in row
    row = row.replace(SURFACE_OLD, SURFACE_NEW)
    row = row[:-len(NOTES_TAIL)] + NOTES_TAIL[:-1] + _flip_note() + '",\n' \
        + f'   "last_checked": "{FLIP_DATE}"'
    return text[:i] + row + text[j:]


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    changed = []
    for path, fn in ((GLOSSARY, apply_glossary), (REGISTRY, apply_registry)):
        raw = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        out = fn(raw.replace("\r\n", "\n"))
        if crlf:
            out = out.replace("\n", "\r\n")
        json.loads(out)
        if out != raw:
            changed.append(path.name)
            if not check:
                path.write_bytes(out.encode("utf-8"))
    print(("would change: " if check else "changed: ") + (", ".join(changed) or "nothing"))
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
