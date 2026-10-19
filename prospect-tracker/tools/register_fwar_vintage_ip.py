# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Point the `fwar` registry row at the innings-amended vintage (EWAR_P0B_VINTAGE_IP).

    python tools/register_fwar_vintage_ip.py
    python tools/gen_audit_docs.py      # then regenerate MODEL_REGISTRY.md

Idempotent: a text-level edit of the one `fwar` row of data/model_registry.json
(champion and notes), so the file keeps its own indent and line endings and no
other row is re-serialised. A second run changes nothing. The vintage ids are
read off data/fwar_vintage.json's last amendment, never typed here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
VINTAGE = ROOT / "data" / "fwar_vintage.json"
TASK = "EWAR_P0B_VINTAGE_IP"


def main() -> int:
    am = json.loads(VINTAGE.read_text(encoding="utf-8"))["amendments"][-1]
    if am.get("task") != TASK:
        print(f"REFUSED: the vintage's last amendment is {am.get('task')!r}, not {TASK}")
        return 2
    old, new = am["previous_vintage_id"], am["vintage_id"]
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    champ_old = (f'"champion": "published fWAR, frozen vintage {old} (fetched 2026-10-02, '
                 'seasons 2000-2026, 48,900 player-seasons; plate appearances added 2026-10-15)",')
    champ_new = (f'"champion": "published fWAR, frozen vintage {new} (fetched 2026-10-02, '
                 'seasons 2000-2026, 48,900 player-seasons; plate appearances added 2026-10-15; '
                 'pitcher innings, outs, games and starts added 2026-10-19)",')
    note_tail = "the training label is value-identical.\","
    note_add = (f" Amended 2026-10-19 ({TASK}, the EW3-19 precedent, a new vintage id; gate part 9, "
                f"the 2026-10-19 entry): inningsPitched (outs / 3), outs, gamesPitched and "
                f"gamesStarted appended to every pitching row from StatsAPI's season pitching line "
                f"by tools/amend_fwar_vintage_ip.py, every published value unchanged, so the "
                f"vintage id moved {old} to {new} and the label= term reads fwar@{new}; the "
                f"training label is value-identical.")
    if champ_new in text:
        print("already registered: nothing to do")
        return 0
    if text.count(champ_old) != 1:
        print("REFUSED: the fwar row's champion is not the expected text")
        return 2
    i = text.index(champ_old)
    j = text.index(note_tail, i)
    text = (text[:i] + champ_new + text[i + len(champ_old):j]
            + note_tail[:-2] + note_add + '",' + text[j + len(note_tail):])
    json.loads(text)
    out = text.replace("\n", "\r\n") if crlf else text
    REG.write_bytes(out.encode("utf-8"))
    print(f"fwar row now names {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
