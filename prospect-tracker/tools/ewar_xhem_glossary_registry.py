# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The xHEM+ part's glossary entries and registry rows (docs/ebr-2026-09-30/EBR_GATE.md
11.11.2; owner decision EW3-51; task EWAR_XHEM_HALF built it, the flip applies it).

PREPARED DARK, APPLIED IN THE FLIP COMMIT (FLIP RULE AG4-Q: the flip carries the flag,
the registry, the glossary, the copy and the tests). Refuses while
ewar_v3.XHEM_HALF_LIVE is False, so nothing lands before the flag does.

    python tools/ewar_xhem_glossary_registry.py --check   # what would change; writes nothing
    python tools/ewar_xhem_glossary_registry.py           # apply (idempotent)
    python tools/gen_audit_docs.py                        # then regenerate the generated docs

What it writes:
  data/glossary.json      a new entry `ewar_xhem` after `ewar_realized`; the `ewar` entry's
                          definition, methodology and formula and the `ewar_realized` entry's
                          definition, methodology and formula name the part (anchored
                          replacements; a missing anchor refuses)
  data/model_registry.json  a new row `ewar_xhem_half` after `ewar_v3_realized` (provisional,
                          shipped_partial_measurement, remeasure_pending EWAR_XHEM_2027_READ,
                          notes recording the owner decision taken while the registered
                          admission rule was not met); one sentence on the `ewar_v3` row's notes
  test_methodology_freshness.py  MODEL_GLOSSARY gains ewar_xhem_half -> [ewar_xhem, ewar]

Site copy says "Provisional" and states the evidence only (owner EW3-51 copy), with its
numbers read from data/swar_eval.json through ewar_v3.xhem_copy(); it never says
"override". Keeps each file's line endings, one-space indent, non-ASCII and trailing
newline; refuses when a plain round trip would rewrite a file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ewar_v3 as V3  # noqa: E402

GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
FRESHNESS = ROOT / "test_methodology_freshness.py"
GATE = "docs/ebr-2026-09-30/EBR_GATE.md"


def entry(copy: str) -> dict:
    return {
        "id": "ewar_xhem",
        "term": "xHEM+ part of eWAR",
        "category": "custom-index",
        "section": "Players & Stats",
        "module": ["projections", "mlbstats"],
        "aliases": ["xHEM+ part", "xHEM+ (expected batting, half weight)", "xHEM+ (half weight)"],
        "priority": 7,
        "definition": ("Half the change in a hitter's batting runs when they are priced on his Statcast "
                       "expected wOBA (xwOBA) in place of his actual results, carried in eWAR from 2016. "
                       "eWAR realized does not carry it. " + copy),
        "methodology": ("For each hitter-season from 2016 with 200 or more plate appearances and a Savant "
                        "value: his expected wOBA, levelled so the season's tracked pool averages the league "
                        "wOBA, minus his actual wOBA, over the season's wOBA scale, times his plate "
                        "appearances. Below 200 PA, or without a Savant value, his shrunk event rates (the "
                        "HEM+ construction) stand in; pitchers batting carry none. The runs are re-centred so "
                        "the league's hitters sum to zero each season, so the league's hitting total stays "
                        "FanGraphs', converted to wins at FanGraphs' runs per win for the season, and halved. "
                        "The half is fixed and was never tuned. There is no part before 2016, the first "
                        "season of the Statcast expected stats the site holds. A read after the 2027 season "
                        "keeps it or removes it."),
        "formula": ("xHEM+ part = 0.5 x [PA x (xwOBA x lgwOBA / pool xwOBA - wOBA) / wOBA scale, re-centred "
                    "per season] / runs per win (HEM+'s shrunk rates below 200 PA)"),
        "seeAlso": ["ewar", "ewar_realized", "xhem_plus", "hem_plus"],
        "shelf": "ark",
        "origin": ("Arkmetric, original to eephus.io. Expected-stat inputs from Baseball Savant (Statcast); "
                   "built on FanGraphs' published WAR."),
    }


def glossary_edits(copy: str) -> dict[str, list[tuple[str, str, str]]]:
    """{entry id: [(field, anchor, replacement)]}: each anchor must occur once, unless
    the replacement is already present (idempotence)."""
    return {
        "ewar": [
            ("definition",
             "and every failed challenge is charged to the player who made it. Every other component "
             "(batting, baserunning, fielding and framing, the positional adjustment, pitching) is "
             "FanGraphs' own. A season with no challenge term equals the player's fWAR. Beside it on "
             "player pages and in Awards, eWAR realized is the same frame with pitchers priced on the "
             "runs they allowed.",
             "and every failed challenge is charged to the player who made it. From 2016 a second part "
             "rides on hitters: half the change when a hitter's batting runs are priced on his Statcast "
             "expected wOBA in place of his actual results (see the xHEM+ part of eWAR). " + copy + " "
             "Every other component (the rest of batting, baserunning, fielding and framing, the "
             "positional adjustment, pitching) is FanGraphs' own. A season before 2016 with no challenge "
             "term equals the player's fWAR. Beside it on player pages and in Awards, eWAR realized is "
             "the same frame with pitchers priced on the runs they allowed and hitters on FanGraphs' "
             "batting."),
            ("methodology",
             "none was admitted, so FanGraphs' own component stays in place for each.",
             "none was admitted, so FanGraphs' own component stays in place for each. The xHEM+ batting "
             "part is carried from 2016 at half weight anyway, provisionally, by the owner's decision of "
             "2026-10-22 (see the xHEM+ part of eWAR); a read after the 2027 season keeps it or removes it."),
            ("formula",
             "eWAR = fWAR + (ABS part runs) / RPW, the ABS part from 2026",
             "eWAR = fWAR + (ABS part runs) / RPW, the ABS part from 2026, + the xHEM+ part (hitters, from "
             "2016, half weight)"),
        ],
        "ewar_realized": [
            ("definition",
             "everything else, the ABS challenge part included, is eWAR's.",
             "hitters keep FanGraphs' batting, without the xHEM+ part eWAR carries from 2016; everything "
             "else, the ABS challenge part included, is eWAR's."),
            ("methodology",
             "Hitters' eWAR realized equals their eWAR.",
             "Hitters' eWAR realized equals their eWAR less the xHEM+ part (from 2016)."),
            ("formula",
             "eWAR realized = eWAR + (pitchers) runs-allowed WAR - FIP WAR on FanGraphs' chain, re-centred per season",
             "eWAR realized = eWAR + (pitchers) runs-allowed WAR - FIP WAR on FanGraphs' chain, re-centred per "
             "season - (hitters) the xHEM+ part"),
        ],
    }


def registry_row(record: dict) -> dict:
    look = record["look"]["cells"]["batting"]
    hold = record["holdout"]["block"]["cells"]["batting"]

    def _c(cell: dict) -> str:
        return (f"{cell['disposition']}, gap {cell['gap']:+.5f}, 95 percent interval {cell['lo95']:+.5f} to "
                f"{cell['hi95']:+.5f}, {cell['n_pairs']:,} pairs")

    return {
        "model_id": "ewar_xhem_half",
        "summary": ("Provisional, owner decision: half of xHEM+ expected batting in headline eWAR from 2016, "
                    "though the registered admission rule was not met; a 2027 read keeps or removes it."),
        "surface": ("The displayed eWAR site-wide on the hitting side from 2016 (season lines, career totals, the "
                    "MLB Stats boards and Earned board, Awards' eWAR, the trade lookup, club totals); the player "
                    "pages' eWAR parts table (xhem); data/ewar_v3.json parts.xhem"),
        "predicts": ("Nothing claimed beyond the record: candidate part 4's xHEM+ arm (S1x) ranked next-season "
                     "batting runs better than the season's own batting runs in the 2016-2024 look"),
        "champion": (f"x = {V3.XHEM_LAMBDA} * d_batx / RPW*_s (EBR_GATE.md 11.11.1), d_batx the re-centred S1x "
                     "delta from the swar preview, RPW*_s league_constants.league_totals(s)['rpw'], 2016 on, "
                     "hitting side of the headline series only; LAMBDA fixed in advance, never tuned"),
        "baseline": "FanGraphs' batting runs (the headline eWAR without the part); eWAR realized keeps them",
        "metric": ("The skill look's H-rate cell (11.2.1: Spearman gap on next-season batting runs per PA, "
                   "convention v2, B 2,000, seed 20261008) and the team guard of 11.2.4; the 2027 read "
                   "(11.11.5) decides keep or remove"),
        "eval_artifact": "data/swar_eval.json",
        "verdict": "provisional",
        "provisional_kind": "shipped_partial_measurement",
        "remeasure_pending": ("EWAR_XHEM_2027_READ, not before 2027-11-10 (EBR_GATE.md 11.11.5): KEEP if the "
                              "gap's one-sided 95 percent lower bound is above 0 and the team guard is "
                              "NON-INFERIOR, otherwise the flag goes False"),
        "notes": ("OWNER DECISION EW3-51 (2026-10-22, 'Half weight + 2027 check'), TAKEN WHILE THE REGISTERED "
                  "ADMISSION RULE WAS NOT MET (EBR_GATE.md 11.2.6 needs the team guard NON-INFERIOR): skill look "
                  f"2026-10-19 xHEM+ H-rate {_c(look['xHEM+ H-rate'])}, H-cum {_c(look['xHEM+ H-cum'])}; team "
                  "guard NOT NON-INFERIOR, underpowered (a half-width above 0.02). Holdout 2026-10-21 (2025 to "
                  f"2026): H-rate {_c(hold['xHEM+ H-rate'])}, H-cum {_c(hold['xHEM+ H-cum'])}; guard NOT "
                  "NON-INFERIOR, underpowered. Registered in " + GATE + " 11.11 (committed alone before any "
                  "number of the part). Built by tools/build_ewar_v3.py behind ewar_v3.XHEM_HALF_LIVE; eWAR "
                  "realized, the ABS part and the runs-per-win form unchanged; the eFV training label stays on "
                  "its frozen headline vintage (the label reads the headline without the part). Rows: S1x as "
                  "scored (the HEM+ arm below 200 PA or without a Savant xwOBA). Site copy states the evidence "
                  "only and never says override."),
    }


V3_NOTE = (" 2026-10-22 EWAR_XHEM_HALF: from 2016 the headline eWAR's hitting side also carries half of "
           "candidate part 4's xHEM+ arm (EBR_GATE.md 11.11, owner decision EW3-51 taken while the registered "
           "admission rule was not met; row ewar_xhem_half); eWAR realized does not.")

FRESH_ANCHOR = '    "ewar": ["ewar"],\n'
FRESH_LINE = '    "ewar_xhem_half": ["ewar_xhem", "ewar"],\n'


def _render(raw: bytes, doc) -> bytes:
    crlf = b"\r\n" in raw
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def _apply_glossary(doc: dict, copy: str) -> list[str]:
    done = []
    rows = doc["entries"]
    by = {e.get("id"): e for e in rows}
    for eid, edits in glossary_edits(copy).items():
        e = by.get(eid)
        if e is None:
            raise SystemExit(f"refusing: glossary entry {eid} is absent")
        for field, old, new in edits:
            cur = e.get(field) or ""
            if new in cur:
                continue
            if cur.count(old) != 1:
                raise SystemExit(f"refusing: the anchor for {eid}.{field} is not in the entry exactly once")
            e[field] = cur.replace(old, new)
            done.append(f"{eid}.{field}")
    new = entry(copy)
    cur = by.get(new["id"])
    if cur != new:
        if cur is not None:
            rows[rows.index(cur)] = new
        else:
            idx = next(i for i, r in enumerate(rows) if r.get("id") == "ewar_realized")
            rows.insert(idx + 1, new)
        done.append(new["id"])
    return done


def _apply_registry(doc: dict, record: dict) -> list[str]:
    done = []
    rows = doc["models"]
    by = {m.get("model_id"): m for m in rows}
    v3 = by.get("ewar_v3")
    if v3 is None:
        raise SystemExit("refusing: registry row ewar_v3 is absent")
    if V3_NOTE.strip() not in (v3.get("notes") or ""):
        v3["notes"] = (v3.get("notes") or "").rstrip() + V3_NOTE
        done.append("ewar_v3.notes")
    new = registry_row(record)
    cur = by.get(new["model_id"])
    if cur != new:
        if cur is not None:
            rows[rows.index(cur)] = new
        else:
            idx = next((i for i, r in enumerate(rows) if r.get("model_id") == "ewar_v3_realized"), len(rows) - 1)
            rows.insert(idx + 1, new)
        done.append(new["model_id"])
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="report what would change; write nothing")
    a = ap.parse_args(argv)
    if not V3.XHEM_HALF_LIVE:
        print("refusing: ewar_v3.XHEM_HALF_LIVE is False; this runs in the flip commit, after the flag")
        return 2
    record = json.loads(V3.SWAR_EVAL.read_text(encoding="utf-8"))
    copy = V3.xhem_copy(record)
    plans = []
    for path, fn in ((GLOSSARY, lambda d: _apply_glossary(d, copy)), (REGISTRY, lambda d: _apply_registry(d, record))):
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if _render(raw, doc) != raw:
            print(f"refusing: a plain round trip would rewrite {path.name}")
            return 2
        done = fn(doc)
        plans.append((path, raw, doc, done))
    fresh_raw = FRESHNESS.read_bytes()
    fresh_txt = fresh_raw.decode("utf-8")
    crlf = "\r\n" in fresh_txt
    nl = "\r\n" if crlf else "\n"
    anchor, line = FRESH_ANCHOR.replace("\n", nl), FRESH_LINE.replace("\n", nl)
    fresh_todo = line not in fresh_txt
    if fresh_todo and fresh_txt.count(anchor) != 1:
        print("refusing: the MODEL_GLOSSARY anchor for ewar is not in test_methodology_freshness.py once")
        return 2
    for path, _raw, _doc, done in plans:
        print(f"{path.name}: {', '.join(done) if done else 'nothing to change'}")
    print(f"{FRESHNESS.name}: {'ewar_xhem_half mapping' if fresh_todo else 'nothing to change'}")
    if a.check:
        return 0
    for path, raw, doc, done in plans:
        if done:
            path.write_bytes(_render(raw, doc))
    if fresh_todo:
        FRESHNESS.write_bytes(fresh_txt.replace(anchor, anchor + line).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
