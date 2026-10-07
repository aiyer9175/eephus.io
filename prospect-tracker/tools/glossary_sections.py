# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Term shelves for data/glossary.json (LIBRARY_4, Library plan 3.3).

Every entry carries a `section`, one of the seven SECTIONS, set from its first
module through SECTION_BY_MODULE. A `foundations` entry has no module of its
own, so it is placed by its old display group (FOUNDATION_SECTION_BY_GROUP).
`category` and `groups` stay in the file for the old #cat= links.

The script also folds each duplicate slug in MERGES into its keeper (the
display term P(enter) was carried by both p_enter and enter_prob). The old slug
stays resolvable through SLUG_ALIASES in assets/eephus-gl.js.

Idempotent: a second run changes nothing and leaves the version stamp alone.
When it does change the payload, the stamp moves through
build_glossary_data.glossary_version() (the stamp is the build date). The file
keeps its own line endings, its one-space indent and its raw UTF-8.

Run: python tools/glossary_sections.py [--check]
  --check: exit 1 when the file would change (nothing is written).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "glossary.json"

SECTIONS = ("Prospects", "Players & Stats", "Value & Contracts", "Clubs",
            "Site & Methods", "Diamond", "Hall of Fame")

# First module -> section.
SECTION_BY_MODULE = {
    "prospx": "Prospects",
    "collegesavant": "Prospects",
    "mlbstats": "Players & Stats",
    "pal": "Players & Stats",
    "scores": "Players & Stats",
    "projections": "Players & Stats",
    "fa": "Value & Contracts",
    "arbitration": "Value & Contracts",
    "trademachine": "Value & Contracts",
    "ledger": "Clubs",
    "management": "Clubs",
    "franchise": "Clubs",
    "platform": "Site & Methods",
    "betting": "Diamond",
    "fantasy": "Diamond",
    "hof": "Hall of Fame",
}

# The override map: a foundations entry is placed by its old display group.
FOUNDATION_SECTION_BY_GROUP = {
    "Statistical Foundations": "Players & Stats",
    "Statcast & Tracking": "Players & Stats",
    "MLB Rules & Transactions": "Value & Contracts",
    "Levels & Leagues": "Prospects",
    "Prospect Grades & Scouting": "Prospects",
    "Badges & Indicators": "Prospects",
    "Platform & Methodology": "Site & Methods",
}

# Retired slug -> the entry it folds into.
MERGES = {"enter_prob": "p_enter"}


def section_for(entry: dict, groups: dict) -> str:
    mods = entry.get("module") or []
    first = mods[0] if mods else "foundations"
    if first == "foundations":
        group = groups.get(entry.get("category"), entry.get("category"))
        if group not in FOUNDATION_SECTION_BY_GROUP:
            raise ValueError(f"{entry['id']}: foundations entry in group {group!r} has no section")
        return FOUNDATION_SECTION_BY_GROUP[group]
    if first not in SECTION_BY_MODULE:
        raise ValueError(f"{entry['id']}: module {first!r} has no section; add it to SECTION_BY_MODULE")
    return SECTION_BY_MODULE[first]


def _union(a: list, b: list) -> list:
    out = list(a or [])
    for x in b or []:
        if x not in out:
            out.append(x)
    return out


def _insert_after(entry: dict, after: str, key: str, value) -> dict:
    """A copy of entry with key placed right after `after` (or at the end)."""
    out = {}
    for k, v in entry.items():
        if k == key:
            continue
        out[k] = v
        if k == after:
            out[key] = value
    if key not in out:
        out[key] = value
    return out


def _merge(keep: dict, old: dict) -> dict:
    """Fold `old` into `keep`, keeping the richer text field by field.

    The keeper's definition stays: it is the line the FA board's P(enter)
    column links, and it states the 100 percent case the option-only line
    leaves out. The retired entry's method, formula and example are the
    fuller ones; the keeper's one method sentence the retired text lacks is
    carried over."""
    out = {}
    for k, v in keep.items():
        out[k] = v
        if k == "methodology":
            meth = old.get("methodology") or ""
            extra = "The source is carried per row in enterProbSrc."
            if (keep.get("methodology") or "").endswith(extra) and extra not in meth:
                meth = (meth + " " + extra).strip()
            if len(meth) > len(v or ""):
                out[k] = meth
            for f in ("formula", "example"):
                if old.get(f) and not keep.get(f):
                    out[f] = old[f]
    out["aliases"] = _union(keep.get("aliases"), old.get("aliases"))
    out["seeAlso"] = [s for s in _union(keep.get("seeAlso"), old.get("seeAlso"))
                      if s != keep["id"]]
    if old.get("priority") is not None:
        out["priority"] = max(keep.get("priority") or 0, old["priority"])
    return out


def apply(doc: dict) -> dict:
    """The shelved payload (a new dict); `doc` is not modified."""
    entries = [dict(e) for e in doc["entries"]]
    by_id = {e["id"]: i for i, e in enumerate(entries)}
    for old_id, keep_id in MERGES.items():
        if old_id not in by_id:
            continue
        old = entries[by_id[old_id]]
        entries[by_id[keep_id]] = _merge(entries[by_id[keep_id]], old)
        entries = [e for e in entries if e["id"] != old_id]
        by_id = {e["id"]: i for i, e in enumerate(entries)}
        for e in entries:
            if old_id in (e.get("seeAlso") or []):
                e["seeAlso"] = [s for s in _union([keep_id if s == old_id else s for s in e["seeAlso"]], [])
                                if s != e["id"]]
    groups = doc.get("groups") or {}
    entries = [_insert_after(e, "category", "section", section_for(e, groups)) for e in entries]
    out = dict(doc)
    out["entries"] = entries
    return out


def _dump(doc: dict, crlf: bool) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def main(argv: list[str]) -> int:
    raw = GLOSSARY.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    new = apply(doc)
    if _dump(new, crlf) == raw:
        print("glossary sections: no change")
        return 0
    if "--check" in argv:
        print("glossary sections: data/glossary.json would change")
        return 1
    sys.path.insert(0, str(ROOT))
    from build_glossary_data import glossary_version
    new["version"] = glossary_version()
    GLOSSARY.write_bytes(_dump(new, crlf))
    counts = {s: sum(1 for e in new["entries"] if e["section"] == s) for s in SECTIONS}
    print(f"glossary sections: {len(new['entries'])} entries, " +
          ", ".join(f"{s} {n}" for s, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
