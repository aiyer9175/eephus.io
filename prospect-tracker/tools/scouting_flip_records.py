# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The registry row and glossary entries of the /scouting/ flip (TL_23_SCOUTING_PAGE_FLIP).

Spec: docs/scouting-2026-10/SCOUTING_PAGE.md sections 6 and 7 (the row
scouting_reference, the glossary entries for the scouting scale, Future Value
tiers and tool-implied production) and its finding F3 (the fv_to_war_anchors row
still names the 2017-2020 cohorts while the fit file it points at carries
cohort_window [2014, 2020]).

    python tools/scouting_flip_records.py --check     lint the copy, write nothing
    python tools/scouting_flip_records.py --apply     write the three files

--apply is idempotent (a second run changes nothing), keeps each file's own line
endings and indent, and refuses a file whose serialization it could not
reproduce byte for byte. It writes:
  data/model_registry.json                  the new row scouting_reference; the
                                            fv_to_war_anchors cohort words (F3); the
                                            tool_tables_rederived surface (now read by
                                            /scouting/)
  data/glossary.json                        the new entry scouting_reference (Future
                                            Value tiers); additions to twenty_eighty
                                            and tool_implied_production
  data/reference/fv_framework_tables.json   a top-level generated_at (the day TL_22
                                            transcribed it), so the registry ages the
                                            row's eval artifact by its own stamp
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "model_registry.json"
GLOSSARY = ROOT / "data" / "glossary.json"
TABLES = ROOT / "data" / "reference" / "fv_framework_tables.json"

BANNED_WORDS = ("leverage", "seamless", "robust", "delve", "comprehensive", "crucial",
                "essential", "powerful", "showcase", "utilize", "unlock", "elevate",
                "game-changing", "cutting-edge", "tapestry", "meticulous", "underscore",
                "harness")
FORECAST_WORDS = ("luck", "due", "regress", "trending", "will", "clutch", "sleeper")
DASHES = (chr(0x2014), chr(0x2013))

TABLES_STAMP = "2026-10-14"      # TL_22 transcribed the file (commit cfd3dc62)
GLOSSARY_VERSION = "2026-10-15"

SCOUTING_ROW = {
    "model_id": "scouting_reference",
    "summary": ("Reference, not a forecaster: published 20-80 tables transcribed cell by cell "
                "with section and source ids, plus served value tables read at grades 20 to 80."),
    "surface": "/scouting/ (data/scouting_reference.json, written by tools/scouting_export.py)",
    "predicts": ("Nothing forward: published 20-80 tables transcribed with section and source "
                 "ids, plus served value-framework configs read at grades 20 to 80"),
    "champion": ("none: a cited transcription of docs/reference/FANGRAPHS_FV_FRAMEWORK.md "
                 "sections 1.3, 2.1, 2.2, 3.1 to 3.6, 7.2, 7.7, 11.1 and 11.2, and the served "
                 "value_framework.fv_to_prime_war display config"),
    "baseline": "none: the page prints the published tables themselves",
    "metric": ("transcription fidelity: test_scouting_page.py re-parses the framework document "
               "and pins every cell of the 20 tables"),
    "eval_artifact": "data/reference/fv_framework_tables.json",
    "verdict": "provisional",
    "provisional_kind": "measurement_only",
    "notes": (
        "Registered by TL_20 in docs/scouting-2026-10/SCOUTING_PAGE.md section 6, built dark by "
        "TL_22 (cfd3dc62), written by TL_23_SCOUTING_PAGE_FLIP on 2026-10-15 with the page flip "
        "(owner answers TL-Q7 and TL-Q8 of 2026-10-01). VERDICT: `provisional` is the registry's "
        "word for a measured-but-descriptive row; its enum has no word for a reference, and this "
        "row is one: nothing is fitted, scored or forecast. The eval artifact is the committed "
        "transcription (20 tables, 170 rows, every cell carrying its framework section id and "
        "source id), dated by its own generated_at; its freshness is the framework document's "
        "commit (07abfc82, 2026-07-30). The row also serves value_framework.fv_to_prime_war, a "
        "display config of industry shape that no other row serves (SCOUTING_PAGE.md finding F2, "
        "default D3). The other numbers on the page keep their own rows: fv_to_6yr_avg_war is "
        "fv_to_war_anchors (its calibration test prospect_anchor read UNDECIDED on 2026-10-14), "
        "p_bucket_given_fv is prospect_surplus (xfv_odds_calibration_slope named for the PROSPX "
        "difference), the tools with no ground truth are tool_grade_tables, and a measured tool "
        "cell prints only where tool_tables_rederived records PASS. Nothing on the page is "
        "computed by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md)."),
    "last_checked": "2026-10-15",
    "stale": False,
}

#: Fields replaced on existing registry rows.
ROW_REWRITES = {
    "fv_to_war_anchors": {
        "summary": ("Validated: empirical 6-year WAR anchors from the 2014-2020 cohorts, "
                    "Edwards-blended in thin cells; positional stratification parked as too thin."),
        "champion": "empirical_anchors (2014-2020 cohorts, Edwards-blended thin cells)",
    },
    "tool_tables_rederived": {
        "summary": ("Read once on the 2026 holdout: HR per 600, ISO, AVG, BB% (SP) and velocity "
                    "(SP) pass and print on /scouting/; K% and SB per 600 fail."),
        "surface": ("/scouting/ tool tiers (TL_23_SCOUTING_PAGE_FLIP, 2026-10-15): a cell that "
                    "records PASS prints as measured beside the FanGraphs estimate, with its n; "
                    "the artifact is data/tool_tables_rederived_eval.json, the look T artifact "
                    "of gate Part T, and no grade, weight or eFV input reads it"),
    },
}

NEW_GLOSSARY = {
    "scouting_reference": {
        "id": "scouting_reference",
        "term": "Future Value tiers",
        "category": "scouting",
        "section": "Prospects",
        "module": ["prospx"],
        "aliases": ["Future Value tiers", "FV tiers", "WAR by FV tier", "Scouting page"],
        "priority": 6,
        "definition": (
            "What each FV grade means in WAR, in two quantities that are never mixed: 'If he "
            "arrives', the WAR of a player who reaches his projected role, and 'Expected, "
            "bust-inclusive', the average over every prospect at the grade with busts at zero. "
            "The Scouting page prints both by tier."),
        "methodology": (
            "The 'If he arrives' column prints our prime-season table (FV 35 and up) beside the "
            "published FanGraphs tables (McDaniel 2014; the 2018 and 2022 primers). The "
            "'Expected, bust-inclusive' column prints our valuation table as served, WAR per "
            "season over a player's first six seasons, with its provenance, beside the Clemens "
            "2026 table, and the chance of each outcome band at the grade. Reading one quantity "
            "as the other overprices a 50 FV about two times and a 40 or 45 FV about three "
            "times. Nothing on the page is computed from player outcomes by FV tier. The expected "
            "table is under the Prospect Anchor calibration test, which read it once on "
            "2026-10-14 and could not decide it; that is not a confirmation."),
        "seeAlso": ["fv", "twenty_eighty", "tool_implied_production", "consensus_fv"],
        "shelf": "foundation",
        "origin": ("Published tables: FanGraphs (McDaniel 2014; Longenhagen and McDaniel 2018; "
                   "Longenhagen 2022; Clemens 2025 and 2026). The two-column layout and the "
                   "served tables are eephus.io's."),
    },
}

#: Text appended once to an existing glossary field, and seeAlso ids added once.
GLOSSARY_APPEND = {
    "twenty_eighty": {
        "methodology": (
            " The Scouting page prints the scale as FanGraphs, Baseball America and MLB "
            "Pipeline publish it, each grade's distance from average in standard deviations, "
            "WAR by FV tier and the stat line each tool grade implies, every number cited."),
        "seeAlso": ["scouting_reference"],
    },
    "tool_implied_production": {
        "methodology": (
            " A second set of tables, re-derived on debuted players' MLB seasons 2015 to 2025 "
            "(2020 excluded) and tested once against the published FanGraphs estimates on the "
            "2026 season, decides only what the Scouting page prints: a tool tier shows our "
            "measured value, with its n, only where that test passed, and the FanGraphs "
            "estimate everywhere."),
        "seeAlso": ["scouting_reference"],
    },
}


def _texts() -> list[tuple[str, str]]:
    out = []

    def walk(where, v):
        if isinstance(v, str):
            out.append((where, v))
        elif isinstance(v, list):
            for i, s in enumerate(v):
                walk(f"{where}[{i}]", s)
        elif isinstance(v, dict):
            for k, s in v.items():
                walk(f"{where}.{k}", s)
    walk("registry.scouting_reference", {k: v for k, v in SCOUTING_ROW.items()
                                         if k in ("summary", "surface", "predicts", "champion",
                                                  "baseline", "metric")})
    for mid, f in ROW_REWRITES.items():
        walk(f"registry.{mid}", f)
    walk("glossary", NEW_GLOSSARY)
    walk("glossary", GLOSSARY_APPEND)
    return out


def _dump(doc: dict, like: bytes) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if like.endswith(b"\n"):
        text += "\n"
    if b"\r\n" in like:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def _load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), raw


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
    for path in (REGISTRY, GLOSSARY, TABLES):
        doc, raw = _load(path)
        if _dump(doc, raw) != raw:
            problems.append(f"{path.name} does not round-trip through indent=1; refusing")
    reg, _ = _load(REGISTRY)
    ids = {m["model_id"] for m in reg["models"]}
    for mid in ROW_REWRITES:
        if mid not in ids:
            problems.append(f"registry rewrite of a missing row {mid}")
    gl, _ = _load(GLOSSARY)
    gids = {e["id"] for e in gl["entries"]}
    for gid in GLOSSARY_APPEND:
        if gid not in gids:
            problems.append(f"glossary addition to a missing entry {gid}")
    for gid, e in NEW_GLOSSARY.items():
        for ref in e["seeAlso"]:
            if ref not in gids and ref not in NEW_GLOSSARY:
                problems.append(f"{gid}.seeAlso {ref} does not resolve")
    return problems


def apply() -> dict:
    problems = check()
    if problems:
        raise SystemExit("refusing to apply: " + "; ".join(problems))
    changed = {}

    # 1. registry
    reg, raw = _load(REGISTRY)
    n = 0
    by_id = {m["model_id"]: m for m in reg["models"]}
    for mid, fields in ROW_REWRITES.items():
        row = by_id[mid]
        for k, v in fields.items():
            if row.get(k) != v:
                row[k] = v
                n += 1
    if "scouting_reference" not in by_id:
        at = next(i for i, m in enumerate(reg["models"]) if m["model_id"] == "tool_tables_rederived")
        reg["models"].insert(at + 1, dict(SCOUTING_ROW))
        n += 1
    if n:
        REGISTRY.write_bytes(_dump(reg, raw))
    changed["registry"] = n

    # 2. glossary
    gl, raw = _load(GLOSSARY)
    n = 0
    by_id = {e["id"]: e for e in gl["entries"]}
    for gid, add in GLOSSARY_APPEND.items():
        e = by_id[gid]
        tail = add["methodology"]
        if not (e.get("methodology") or "").endswith(tail):
            e["methodology"] = (e.get("methodology") or "") + tail
            n += 1
        for ref in add["seeAlso"]:
            if ref not in e.setdefault("seeAlso", []):
                e["seeAlso"].append(ref)
                n += 1
    for gid, entry in NEW_GLOSSARY.items():
        if gid not in by_id:
            at = next(i for i, e in enumerate(gl["entries"]) if e["id"] == "twenty_eighty")
            gl["entries"].insert(at + 1, entry)
            n += 1
    if n:
        gl["version"] = GLOSSARY_VERSION
        GLOSSARY.write_bytes(_dump(gl, raw))
    changed["glossary"] = n

    # 3. the transcription's own date stamp
    doc, raw = _load(TABLES)
    if "generated_at" not in doc:
        out = {}
        for k, v in doc.items():
            out[k] = v
            if k == "transcribed_by":
                out["generated_at"] = TABLES_STAMP
        if "generated_at" not in out:
            out["generated_at"] = TABLES_STAMP
        TABLES.write_bytes(_dump(out, raw))
        changed["tables"] = 1
    else:
        changed["tables"] = 0
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if a.apply:
        print(apply())
        return 0
    problems = check()
    for p in problems:
        print("PROBLEM", p)
    print("scouting_flip_records: " + ("clean" if not problems else f"{len(problems)} problems"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
