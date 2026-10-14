# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Retire the Franchise Index in the glossary and the registry at the F-SCORE flip.

Owner answer FS-Q4 (b), 2026-10-01: F-SCORE replaces the Franchise Index as the
root score on /franchise/ and the Index leaves the page. FS_2C_INDEX_REPLACEMENT
built the replacement dark, keyed on fscore_export.FSCORE_LIVE and
FSCORE_REPLACES_INDEX (franchise_export.replace_index). data/glossary.json and
data/model_registry.json cannot be flagged, so this idempotent script is the
flip's glossary and registry step: FS_2F_FLIP runs it in the flip commit AFTER
it adds the franchise_score glossary entry and registry row, and it refuses to
run before those exist or while the flag is off (unless --force).

What it changes, keeping every original sentence (the receipts):
  glossary franchise_index: the definition opens "Retired 2026 by owner answer
    FS-Q4", the methodology closes with the retirement and where the three
    branches went, the origin names the replacement, seeAlso leads with
    franchise_score;
  glossary franchise_branch_score and season_record: seeAlso gains
    franchise_score ahead of franchise_index;
  registry franchise_index: verdict deprecated (retired by an owner answer, not
    by a failed test, which its summary says), a new summary and surface, the
    retirement appended to its notes; predicts, champion, baseline, metric and
    the null eval artifact stay;
  registry franchise_branch_score: its notes name the pillar each branch
    counts in;
  registry franchise_score: its surface names the root card and its notes the
    row it replaces.

Each file keeps its own line endings and indentation. The glossary is written
back only when its unchanged parse re-serialises to the file byte for byte
(refused otherwise, never reformatted); the registry, whose rows are indented
unevenly, is edited field by field inside each row's own text span.

usage: python tools/fscore_index_retirement.py [--check] [--force]
  --check  print what would change, write nothing, exit 1 when anything would
  --force  run while the flag is off (a dry run on copies, or a test)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"

RETIRED = "Retired 2026 by owner answer FS-Q4"
GL_DEFINITION_HEAD = (f"{RETIRED}: F-SCORE (franchise_score) replaced the Franchise Index as the root "
                      "score on /franchise/, and the Index is no longer served. What it was: ")
GL_METHOD_TAIL = (f"{RETIRED} (2026-10-01): its three branches count inside F-SCORE, ROSTER and OUTLOOK "
                  "in STRENGTH and FARM in PIPELINE; the method above is kept as the record.")
GL_ORIGIN_TAIL = ("; retired 2026 by owner answer FS-Q4 (the registry row is now deprecated), replaced by "
                  "F-SCORE (franchise_score)")
GL_SEE_ALSO_FRONT = {"franchise_index": "franchise_score", "franchise_branch_score": "franchise_score",
                     "season_record": "franchise_score"}

REG_INDEX = {
    "verdict": "deprecated",
    "summary": (f"{RETIRED}, not by a failed test: F-SCORE (franchise_score) replaced it as the root "
                "score on /franchise/. The row stays as the record."),
    "surface": "none since the F-SCORE flip; it was the /franchise/ root card, canopy and 30-club board",
}
REG_INDEX_NOTE = (f"{RETIRED} (2026-10-01, FS_2C_INDEX_REPLACEMENT): F-SCORE (franchise_score) replaced it "
                  "as the root score on /franchise/ and it is no longer served; its three branches count "
                  "inside F-SCORE (ROSTER and OUTLOOK in STRENGTH, FARM in PIPELINE), so none was dropped. "
                  "Deprecated here because it was retired by an owner answer, not because a test failed.")
REG_BRANCH_NOTE = ("Since the F-SCORE flip (owner answer FS-Q4, 2026-10-01) the branches sit under F-SCORE, "
                   "and each graded branch names the F-SCORE pillar it counts in (ROSTER and OUTLOOK in "
                   "STRENGTH, FARM in PIPELINE) where it printed a Franchise Index weight.")
REG_FSCORE = {
    "surface": ("/franchise/ root card and letter, the F-SCORE section and the board's default sort and "
                "letter column; one F-SCORE column on the /mlbstats/ Teams tab, copied verbatim"),
}
REG_FSCORE_NOTE = ("Replaces franchise_index as the root score on /franchise/ (owner answer FS-Q4 (b), "
                   "2026-10-01; FS_2C_INDEX_REPLACEMENT).")


class RetirementRefusal(RuntimeError):
    """The files are not in a state this script may edit."""


# --------------------------------------------------------------------------
# glossary: a byte-exact JSON round trip
# --------------------------------------------------------------------------

def _dump_like(obj, raw: str) -> str:
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = json.dumps(obj, indent=1, ensure_ascii=False).replace("\n", nl)
    return text + (nl if raw.endswith(nl) else "")


def retire_glossary(raw: str) -> str:
    g = json.loads(raw)
    if _dump_like(g, raw) != raw:
        raise RetirementRefusal("glossary.json does not re-serialise byte for byte; edit it by hand")
    by = {e["id"]: e for e in g["entries"]}
    if "franchise_score" not in by:
        raise RetirementRefusal("the franchise_score glossary entry is not there yet; add it first")
    if "franchise_index" not in by:
        raise RetirementRefusal("the franchise_index glossary entry is missing")
    e = by["franchise_index"]
    if not e["definition"].startswith(RETIRED):
        e["definition"] = GL_DEFINITION_HEAD + e["definition"]
    meth = e.get("methodology") or ""
    if GL_METHOD_TAIL not in meth:
        e["methodology"] = (meth + " " + GL_METHOD_TAIL).strip()
    origin = e.get("origin") or ""
    if GL_ORIGIN_TAIL not in origin:
        e["origin"] = origin + GL_ORIGIN_TAIL
    for eid, front in GL_SEE_ALSO_FRONT.items():
        ent = by.get(eid)
        if ent is None:
            continue
        see = list(ent.get("seeAlso") or [])
        if front not in see:
            ent["seeAlso"] = [front] + see
    return _dump_like(g, raw)


# --------------------------------------------------------------------------
# registry: field by field inside each row's own span
# --------------------------------------------------------------------------

def _row_span(text: str, mid: str) -> tuple[int, int] | None:
    i = text.find(f'"model_id": "{mid}"')
    if i < 0:
        return None
    start = text.rfind("{", 0, i)
    depth, in_str, esc = 0, False, False
    for j in range(start, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, j + 1
    raise RetirementRefusal(f"registry row {mid} does not close")


_VALUE = r'(?:"(?:[^"\\]|\\.)*"|null|true|false|-?\d[\d.eE+-]*)'


def _set_field(row: str, key: str, value) -> str:
    pat = re.compile(r'("' + re.escape(key) + r'":\s*)' + _VALUE)
    if not pat.search(row):
        raise RetirementRefusal(f"registry field {key} not found in its row")
    new = json.dumps(value, ensure_ascii=False)
    return pat.sub(lambda m: m.group(1) + new, row, count=1)


def _edit_row(text: str, mid: str, fields: dict, note: str) -> str:
    span = _row_span(text, mid)
    if span is None:
        raise RetirementRefusal(f"registry row {mid} is missing" +
                                ("; add it first" if mid == "franchise_score" else ""))
    a, b = span
    row = text[a:b]
    parsed = json.loads(row)
    for k, v in fields.items():
        if parsed.get(k) != v:
            row = _set_field(row, k, v)
    notes = parsed.get("notes") or ""
    if note not in notes:
        row = _set_field(row, "notes", (notes + " " + note).strip())
    # the edit landed on the row's own top-level fields and on nothing else
    after = json.loads(row)
    want = dict(parsed, **fields)
    want["notes"] = notes if note in notes else (notes + " " + note).strip()
    if after != want:
        raise RetirementRefusal(f"registry row {mid}: a field edit landed outside its top-level key")
    return text[:a] + row + text[b:]


def retire_registry(raw: str) -> str:
    text = _edit_row(raw, "franchise_score", REG_FSCORE, REG_FSCORE_NOTE)
    text = _edit_row(text, "franchise_index", REG_INDEX, REG_INDEX_NOTE)
    text = _edit_row(text, "franchise_branch_score", {}, REG_BRANCH_NOTE)
    json.loads(text)
    return text


# --------------------------------------------------------------------------

def _read(p: Path) -> str:
    return p.read_bytes().decode("utf-8")


def _write(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))


def apply(glossary: Path = GLOSSARY, registry: Path = REGISTRY, write: bool = True) -> list[str]:
    """Retire the Index in both files; returns the names of the files that
    changed (or would change, with write False). Idempotent."""
    changed = []
    for p, fn in ((glossary, retire_glossary), (registry, retire_registry)):
        raw = _read(p)
        new = fn(raw)
        if new != raw:
            changed.append(p.name)
            if write:
                _write(p, new)
    return changed


def _flag_on() -> bool:
    import fscore_export
    return bool(fscore_export.FSCORE_LIVE and getattr(fscore_export, "FSCORE_REPLACES_INDEX", False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when anything would change")
    ap.add_argument("--force", action="store_true", help="run while the flag is off")
    ap.add_argument("--glossary", type=Path, default=GLOSSARY)
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    a = ap.parse_args(argv)
    if not (a.force or a.check or _flag_on()):
        print("REFUSED: F-SCORE does not replace the Index yet (fscore_export.FSCORE_LIVE and "
              "FSCORE_REPLACES_INDEX); run in the flip commit")
        return 2
    try:
        changed = apply(a.glossary, a.registry, write=not a.check)
    except RetirementRefusal as exc:
        print(f"REFUSED: {exc}")
        return 2
    verb = "would change" if a.check else "changed"
    print(f"{verb}: {', '.join(changed) if changed else 'nothing'}")
    return 1 if (a.check and changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
