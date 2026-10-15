# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The glossary entries and registry text of the Source Accuracy Tools tab flip (TL_15).

TL_14 built the tab dark and wrote no glossary term; the flip carries the two terms the
tab prints (tool-implied production, tool above grade) and points the two registry rows
of look W at the served surface, with their freshness stamps.

    python tools/tool_display_flip.py --check     lint the copy; writes nothing
    python tools/tool_display_flip.py --apply     write data/glossary.json and
                                                  data/model_registry.json

--apply is idempotent (a second run changes nothing), keeps each file's own line endings
and indent, and refuses a file whose serialization it could not reproduce byte for byte.
No measured number is typed here: the receipts in assets/glossary.js read them from the
registry rows' eval artifact, data/tool_accuracy_eval.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
DATE = "2026-10-14"
MARK = "FLIP 2026-10-14 (TL_15_TOOL_DISPLAY_FLIP)"

#: tools/copy_lint.py's banned words, mirrored so --check needs no import of the linter.
BANNED_WORDS = ("leverage", "seamless", "robust", "delve", "comprehensive", "crucial",
                "essential", "powerful", "showcase", "utilize", "unlock", "elevate",
                "game-changing", "cutting-edge", "tapestry", "meticulous", "underscore",
                "harness")
FORECAST_WORDS = ("luck", "due", "regress", "trending", "will", "clutch", "sleeper")
DASHES = (chr(0x2014), chr(0x2013))
ORIGIN = "Arkmetric, original to eephus.io (tool-implied production gate, tool_implied.py)."

NEW_ENTRIES: dict[str, dict] = {
    "tool_implied_production": {
        "id": "tool_implied_production",
        "term": "Tool-implied production",
        "category": "custom-index",
        "section": "Prospects",
        "shelf": "ark",
        "origin": ORIGIN,
        "module": ["prospx"],
        "aliases": ["TIP", "Tool-implied production", "tool implied production"],
        "priority": 11,
        "definition": (
            "The MLB stat a tool grade points to under the FanGraphs framework: hit to K% "
            "(and AVG), game power to ISO, raw power to exit velocity, speed to sprint speed "
            "and SB, field to OAA, arm to arm strength, fastball to K%, command to BB%. It is "
            "read off a table of the typical realized stat at each tool grade."),
        "methodology": (
            "Each table is fit per tool and stat on debuted players: the median realized stat "
            "in tool-grade bins of 5 points (a bin under 15 players is thin and dropped), "
            "smoothed so the stat moves the way the grade says it should, interpolated between "
            "bins and held flat past the last bin, with no extrapolation. The version the "
            "Source Accuracy Tools tab reads is fit on each player's first three MLB seasons "
            "after his board year, and a table never scores a player or a board year it was "
            "fit on (leave one board year out). It is a measurement, not a projection: no "
            "grade, chip, price or eFV input is built from it, and the tool grades shown on "
            "PROSPX are unchanged. Tool grades display rounded up (the tool-implied "
            "production gate, Part 1.2)."),
        "formula": (
            "TIP(tool, stat, grade) = smoothed median of the realized stat in the bin "
            "round(grade / 5) x 5, read at the grade"),
        "seeAlso": ["tool_above_grade", "tool", "wag"],
    },
    "tool_above_grade": {
        "id": "tool_above_grade",
        "term": "Tool above grade (TAG)",
        "category": "custom-index",
        "section": "Prospects",
        "shelf": "ark",
        "origin": ORIGIN,
        "module": ["prospx"],
        "aliases": ["TAG", "Tool above grade", "TAG percentile", "regressed TAG"],
        "priority": 12,
        "definition": (
            "How far a debuted player's production sat from what his tool grade implied: the "
            "realized stat minus tool-implied production, in the stat's own units, signed so "
            "that a positive TAG means he produced above the grade. WAG's idea, per tool."),
        "methodology": (
            "Three readings per player, source and tool: the gap; the TAG percentile, his rank "
            "among the players in the same tool-grade bin (0.5 is on grade); and the regressed "
            "TAG, the gap times E / (E + k), with E his exposure in the stat's own unit and k "
            "the stat's split-half stabilization constant, so a thin sample shrinks toward "
            "zero. Sprint speed, OAA and arm strength have no k, so their bias reads off the "
            "percentile only. Per source and tool the Source Accuracy Tools tab prints "
            "ordering (the within-board-year Spearman of the source's grades against the "
            "realized stat), bias (the mean regressed TAG and the mean TAG percentile minus "
            "0.5; a negative mean is a source whose grades ran hot) and error (the mean "
            "absolute regressed TAG). Only ordering can earn a source a weight; bias is shown "
            "and never applied. Every figure is among players who reached the majors. TAG "
            "percentiles and rates round to nearest (the tool-implied production gate, "
            "Part 2)."),
        "formula": (
            "TAG gap = realized stat - TIP(tool, stat, source grade)\n"
            "regressed TAG = gap x E / (E + k)\n"
            "TAG percentile = mid-rank of the realized stat among the table's rows in the "
            "same tool-grade bin"),
        "seeAlso": ["tool_implied_production", "wag", "tool"],
    },
}
ANCHOR = "wag"

SURFACE = {
    "tool_source_accuracy": (
        "Served since 2026-10-14: the Source Accuracy Tools tab on /glossary/ prints look W's "
        "display copy (/data/tool_source_accuracy.json), copied from the spent record without a "
        "re-run. No weighted tool grade was built, so no grade, chip or eFV input reads the look"),
    "tool_implied_production": (
        "Served since 2026-10-14: the Source Accuracy Tools tab on /glossary/ prints the "
        "per-source TAG metrics (ordering, bias, error). The tables feed the tool accuracy lab "
        "and the stat-line model's registration; no grade, chip, price or eFV input reads them"),
}
STATUS = {
    "tool_source_accuracy": ("read once 2026-10-14 (look W): VOID under W.7, equal weight retains; "
                             "printed on the Source Accuracy Tools tab since 2026-10-14"),
    "tool_implied_production": ("TAG tables computed once at look W (2026-10-14); printed on the "
                                "Source Accuracy Tools tab since 2026-10-14, read by nothing else "
                                "served"),
}
#: Copy repairs on the two rows' existing fields (docs/COPY_STYLE.md L1 and L8): (field, old
#: text, new text); applied only while the old text is present.
REWRITES = {
    "tool_source_accuracy": [
        ("metric", "outcomes through 2026), PASS when G1 to G5 hold on arm A and Holm survives; "
                   "secondaries (game_pwr to ISO, fb to K%, cmd to BB%, hit to AVG, speed to SB) "
                   "descriptive only, BA2's verdicts stand",
         "outcomes through 2026). PASS when G1 to G5 hold on arm A and Holm survives. Secondaries "
         "(game_pwr to ISO, fb to K%, cmd to BB%, hit to AVG, speed to SB) are descriptive only, "
         "and BA2's verdicts stand"),
        ("baseline", "tool consensus of consensus.py on the common set",
         "tool consensus the site serves, on the common set"),
    ],
    "tool_implied_production": [
        ("baseline", "(docs/reference/FANGRAPHS_FV_FRAMEWORK.md Part 2)",
         "(the FanGraphs FV framework reference, Part 2)"),
    ],
}
SUMMARY_TIP = ("Measured once at look W (2026-10-14): TIP tables for the tool framework and TAG "
               "tables per source, tool and board year; the Source Accuracy Tools tab prints "
               "per-source TAG metrics.")
NOTE = (f"{MARK}: build_site.SOURCE_ACCURACY_TOOLS_TAB True; data/tool_source_accuracy.json "
        "(look W's display copy, served True) written from data/tool_accuracy_eval.json by "
        "tools/tool_accuracy_lab.py --export-display without a re-run; glossary entries "
        "tool_implied_production and tool_above_grade carry receipts read from this row's eval "
        "artifact. Flip 2 (TOOL_SOURCE_WEIGHTS) not built: TL_13 built nothing because no tool "
        "passed, so owner answer TL-Q5 has nothing to turn on and tools_consensus is untouched.")


def _dump(doc: dict, like: bytes, ensure_ascii: bool) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=ensure_ascii)
    if like.endswith(b"\n"):
        text += "\n"
    if b"\r\n" in like:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def _texts() -> list[tuple[str, str]]:
    out = []
    for gid, fields in NEW_ENTRIES.items():
        for k, v in fields.items():
            if isinstance(v, str):
                out.append((f"{gid}.{k}", v))
            elif isinstance(v, list):
                out.extend((f"{gid}.{k}[{i}]", s) for i, s in enumerate(v) if isinstance(s, str))
    for mid in SURFACE:
        out += [(f"{mid}.surface", SURFACE[mid]), (f"{mid}.status", STATUS[mid])]
    out += [("tool_implied_production.summary", SUMMARY_TIP), ("note", NOTE)]
    out += [(f"{mid}.{f}", new) for mid, rows in REWRITES.items() for f, _old, new in rows]
    return out


def check() -> list[str]:
    problems: list[str] = []
    for where, text in _texts():
        for d in DASHES:
            if d in text:
                problems.append(f"{where}: dash")
        low = text.lower()
        for w in BANNED_WORDS + FORECAST_WORDS:
            if re.search(r"\b" + re.escape(w) + r"\b", low):
                problems.append(f"{where}: {w!r}")
    graw = GLOSSARY.read_bytes()
    gdoc = json.loads(graw.decode("utf-8"))
    ids = {e["id"] for e in gdoc["entries"]}
    for gid, entry in NEW_ENTRIES.items():
        for ref in entry.get("seeAlso", []):
            if ref not in ids and ref not in NEW_ENTRIES:
                problems.append(f"{gid}.seeAlso {ref} does not resolve")
    if _dump(gdoc, graw, False) != graw:
        problems.append("the glossary does not round-trip; refusing to reformat it")
    rraw = REGISTRY.read_bytes()
    if _dump(json.loads(rraw.decode("utf-8")), rraw, False) != rraw:
        problems.append("the registry does not round-trip; refusing to reformat it")
    return problems


def apply_glossary() -> int:
    raw = GLOSSARY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    by_id = {e["id"]: e for e in doc["entries"]}
    changed = 0
    anchor = ANCHOR
    for gid, entry in NEW_ENTRIES.items():
        if gid in by_id:
            if by_id[gid] != entry:
                by_id[gid].clear()
                by_id[gid].update(entry)
                changed += 1
        else:
            at = next((i for i, e in enumerate(doc["entries"]) if e["id"] == anchor),
                      len(doc["entries"]) - 1)
            doc["entries"].insert(at + 1, entry)
            changed += 1
        anchor = gid
    if changed:
        doc["version"] = DATE
        GLOSSARY.write_bytes(_dump(doc, raw, False))
    return changed


def apply_registry() -> int:
    sys.path.insert(0, str(ROOT))
    import model_registry
    raw = REGISTRY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    by_id = {r["model_id"]: r for r in doc["models"]}
    fresh = model_registry.freshness(doc)
    changed = 0
    for mid in SURFACE:
        r = by_id[mid]
        before = json.dumps(r, sort_keys=True)
        r["surface"] = SURFACE[mid]
        r["registration_status"] = STATUS[mid]
        if mid == "tool_implied_production":
            r["summary"] = SUMMARY_TIP
        for field, old, new in REWRITES.get(mid, []):
            if old in (r.get(field) or ""):
                r[field] = r[field].replace(old, new)
        if MARK not in (r.get("notes") or ""):
            r["notes"] = (r.get("notes") or "").rstrip() + " " + NOTE
        f = fresh.get(mid)
        if f and r.get("last_checked") is None:
            r["last_checked"] = date.today().isoformat()
            r["stale"] = f["stale"]
            r["artifact_age_days"] = f["artifact_age_days"]
        if json.dumps(r, sort_keys=True) != before:
            changed += 1
    if changed:
        REGISTRY.write_bytes(_dump(doc, raw, False))
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    problems = check()
    for p in problems:
        print("PROBLEM", p)
    if problems:
        return 1
    if a.apply:
        print("glossary entries changed:", apply_glossary())
        print("registry rows changed:", apply_registry())
    else:
        print("tool_display_flip: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
