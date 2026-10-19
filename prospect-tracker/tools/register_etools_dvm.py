# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ETOOLS_DVM: say in the glossary and the registry that per-tool DvM+ and ToolDvM+ keep
consensus grade changes, and why (docs/farm-attribution-2026-09-25/ETOOLS_DVM_GATE.md
Part 8). Every figure is read from data/_labs/etools/etools_dvm_read.json.

Idempotent and format-preserving: each edit is a string replacement of one JSON string
value, so the file's line endings, indent and key order never move; a second run changes
nothing.

    python tools/register_etools_dvm.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
READ = ROOT / "data" / "_labs" / "etools" / "etools_dvm_read.json"
MARK = "ETOOLS_DVM (2026-10-17"


def _sentence(doc: dict) -> str:
    n = len(doc["groups"])
    nr = sum(1 for v in doc["groups"].values() if v["verdict"] == "NOT RESOLVABLE")
    sw = doc.get("switch") or []
    head = (f"{MARK}, owner decision EW3-34): built on eTool grade changes instead, these "
            f"indexes were read once against the consensus version (docs/farm-attribution-2026-09-25/"
            f"ETOOLS_DVM_GATE.md). ")
    if sw:
        return head + "Switched: " + ", ".join(sw) + "."
    return head + (f"None switched: {nr} of {n} tool groups with an eTool (Hit, Power, PitchSel, BatCtrl, "
                   "FB, Cmd) were not resolvable, because neither year-to-year club persistence nor "
                   "the link from a grade gain to later MLB outcomes could recover a planted effect "
                   "on the data that exists, so every per-tool DvM+ keeps consensus grade changes.")


def _replace_value(text: str, old_value: str, new_value: str) -> str:
    o, n = json.dumps(old_value, ensure_ascii=False), json.dumps(new_value, ensure_ascii=False)
    if text.count(o) != 1:
        raise SystemExit(f"expected exactly one occurrence of {o[:80]}...")
    return text.replace(o, n)


def _entry(doc: dict, key: str, val: str) -> dict:
    for e in doc["entries"] if "entries" in doc else doc:
        if e.get(key) == val:
            return e
    raise SystemExit(f"no entry {key}={val}")


def main() -> int:
    read = json.loads(READ.read_text(encoding="utf-8"))
    s = _sentence(read)
    # glossary
    raw = GLOSSARY.read_bytes().decode("utf-8")
    g = json.loads(raw)
    tsd = _entry(g, "id", "tool_specific_dvm_plus")
    old = tsd["methodology"]
    if MARK not in old:
        new = ("Same shape as DvM+ and ToolDvM+, one tool at a time. For each tool group (Hit, Power, "
               "Speed, Field, Arm, PitchSel, BatCtrl, FB, SL, CB, CH, Cmd, Ct), every active prospect's "
               "growth in that tool inside a 7-year lookback, read on same-source pairs (one outlet's list "
               "to its next list) and credited to each club that held him for the part that happened there; "
               "Power is each outlet's game and raw power averaged to the half grade. The growth is priced on "
               "the FV-to-expected-WAR table and level weighted; the club mean is shrunk by n/(n+2) and "
               "anchored 100 + 10z across the league, then stretched 1.35. Cells with fewer than 3 "
               "contributing prospects render ' - '.\n\n" + s)
        raw = _replace_value(raw, old, new)
    td = _entry(g, "id", "tools_dvm_plus")
    old = td["methodology"]
    if MARK not in old:
        raw = _replace_value(raw, old, old + "\n\n" + s)
    if raw != GLOSSARY.read_bytes().decode("utf-8"):
        GLOSSARY.write_bytes(raw.encode("utf-8"))
        print("glossary: updated")
    # registry
    raw = REGISTRY.read_bytes().decode("utf-8")
    r = json.loads(raw)
    rows = r if isinstance(r, list) else (r.get("models") or r.get("rows") or [])
    row = next((x for x in rows if x.get("model_id") == "dvm_plus_tools"), None)
    if row is None:
        raise SystemExit("no dvm_plus_tools row")
    old = row["notes"]
    if MARK not in old:
        add = (f" {s} Read artifact: data/_labs/etools/etools_dvm_read.json (role development). "
               "2026-10-16 repair: PowerDvM+ was null on every club after VAL_4 because the outlet "
               "observations carried game and raw power but not the consolidated Power grade; restored.")
        raw = _replace_value(raw, old, old + add)
        REGISTRY.write_bytes(raw.encode("utf-8"))
        print("registry: updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
