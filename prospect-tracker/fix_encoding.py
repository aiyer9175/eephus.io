#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
Repair player names in manual_rankings.csv.

Two corruption patterns handled:
  1. Classic mojibake  — UTF-8 bytes decoded as Latin-1, then re-stored:
       'RodrÃ­guez'  (Ã = U+00C3, ­ = U+00AD) -> 'Rodríguez'
  2. Partial-fix corruption — the Ã byte was already replaced with U+FFFD
     before a prior fix attempt ran, leaving e.g.:
       'Rodr�\xadguez'  -> 'Rodríguez'

Both are fixed character-by-character so that correctly-encoded names
(é = U+00E9, ñ = U+00F1, etc.) are left untouched.
"""

import csv
import unicodedata
from pathlib import Path


def fix_name(text: str) -> str:
    """
    Fix mojibake in a player name character by character.

    Handles two patterns:
      - Ã + <cont>   where Ã  = U+00C3 and <cont> is any Latin-1 char
      - FFFD + <cont> where FFFD = U+FFFD (replacement char) and <cont>
                      is the byte that was the UTF-8 continuation byte

    For each suspicious pair, we try encode('latin-1') + decode('utf-8').
    If that produces a clean character we keep it; otherwise we leave the
    original characters in place.
    """
    if not text:
        return text

    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else None

        if nxt is not None and ch in ('\xc3', '�'):
            # Try to interpret (ch, nxt) as a mojibake pair:
            #   encode('latin-1') treats Ã as 0xC3 and the next char as its
            #   byte value, giving the original UTF-8 two-byte sequence.
            # For U+FFFD we substitute Ã (0xC3) since FFFD is an artefact
            # of a previous failed decode of the same byte.
            probe_first = '\xc3'          # always use C3 as the lead byte
            try:
                pair_bytes = (probe_first + nxt).encode('latin-1')
                fixed_char = pair_bytes.decode('utf-8')
                # Accept only if result is a single printable non-ASCII char
                if len(fixed_char) == 1 and ord(fixed_char) > 127 and '�' not in fixed_char:
                    result.append(fixed_char)
                    i += 2
                    continue
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # Remove soft hyphens that crept in from encoding corruption
        if ch == '\xad':        # U+00AD soft hyphen — never valid in a name
            i += 1
            continue

        result.append(ch)
        i += 1

    fixed = ''.join(result)
    # Normalise to NFC (composed form) as a final pass
    return unicodedata.normalize('NFC', fixed)


def _detect_encoding(path: Path) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            path.open(encoding=enc).read()
            return enc
        except UnicodeDecodeError:
            continue
    return 'latin-1'


def main():
    csv_path = Path(__file__).parent / "manual_rankings.csv"
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        return

    enc = _detect_encoding(csv_path)
    rows = []
    fixed_count = 0

    with csv_path.open(encoding=enc) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            name = row.get("player_name", "")
            if name:
                fixed = fix_name(name)
                if fixed != name:
                    fixed_count += 1
                    print(f"  Fixed: {name!r} -> {fixed!r}")
                row["player_name"] = fixed
            rows.append(row)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Processed {len(rows)} rows, {fixed_count} name fixes -> {csv_path}")


if __name__ == "__main__":
    main()
