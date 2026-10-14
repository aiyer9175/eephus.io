"""Name the DEV selections in the aging_v3 registry row (idempotent).

Reads data/aging_v3_mde.json (AG_6_AGING_V3_DEV_AND_POWER, docs/AGING_V3_GATE.md
section 8) and appends one note to the aging_v3 row's notes naming the
selected grid values, the per-arm power verdicts and the two serve-rule
repairs the DEV run found in the AG_5 build. The edit is a replacement of
that one JSON string inside the file's own bytes: every other byte, the line
endings (CRLF) and the indent of every other row stay as they are, so the
diff is the one notes line. Running it twice changes nothing; running it
after a re-selection replaces the earlier note.

    python tools/register_aging_v3_dev.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
MDE = ROOT / "data" / "aging_v3_mde.json"
MARK = " DEV SELECTION ("


def note(doc: dict) -> str:
    sel = doc["selected"]
    power = doc.get("power") or {}
    parts = []
    for a in ("T", "S", "P", "R"):
        p = power.get(a) or {}
        mde = p.get("mde95")
        parts.append(f"{a} MDE95 {mde:.4f} {'UNDERPOWERED' if p.get('underpowered') else 'powered'}"
                     if mde is not None else f"{a} MDE95 n/a UNDERPOWERED")
    fr = doc.get("frame") or {}
    return (
        f"{MARK}{doc['generated_at'][:10]}, AG_6_AGING_V3_DEV_AND_POWER, data/aging_v3_mde.json, DEV rows only, "
        f"label seasons {fr.get('label_seasons')}, {fr.get('n_rows')} rows, {fr.get('n_players')} players): "
        f"lambda {sel['lambda']}, smoother {sel['smoother']} (penalty {sel['penalty']}), k_P {sel['k_P']}, "
        f"k_R {sel['k_R']}, selected once by the DEV ACAL minimum with ties within 0.002 to the value nearer the "
        f"incumbent, never re-selected; power at a 0.05 WAR plant in the 24-and-under and 31-and-over cells: "
        + "; ".join(parts)
        + ". The DEV run found and repaired two serve-rule defects in the AG_5 build (aging_v3.fit): the bucket of "
        "the base season and the archetype of the base's pair start were never assigned, so under ARM P every served "
        "hitter walked the pooled parent and under ARM R every path read NEUTRAL; both now assigned from every row at "
        "or before the base season, window still out of sample (test_aging_v3_gate.py). The look is tools/aging_v3_lab.py "
        "look (dry-run on fixtures with nulls at this commit), run once by AG_7 on the first free day."
    )


def main() -> int:
    raw = REG.read_bytes()
    text = raw.decode("utf-8")
    doc = json.loads(text)
    mde = json.loads(MDE.read_text(encoding="utf-8"))
    row = next(r for r in doc["models"] if r["model_id"] == "aging_v3")
    old_notes = row["notes"]
    new = note(mde)
    base = old_notes.rstrip()
    if MARK in base:
        base = base[:base.index(MARK)].rstrip()
    new_notes = base + new
    if old_notes == new_notes:
        print("registry already carries this DEV selection note; nothing written")
        return 0
    # the one string, as the file encodes it (json.dumps without ASCII
    # escaping is how the registry is written), replaced in place
    old_lit = json.dumps(old_notes, ensure_ascii=False)
    if text.count(old_lit) != 1:
        raise SystemExit(f"the aging_v3 notes string occurs {text.count(old_lit)} times in the file; "
                         "nothing written")
    out = text.replace(old_lit, json.dumps(new_notes, ensure_ascii=False), 1)
    check = json.loads(out)
    assert next(r for r in check["models"] if r["model_id"] == "aging_v3")["notes"] == new_notes
    REG.write_bytes(out.encode("utf-8"))
    print("registry written: aging_v3 notes name the DEV selection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
