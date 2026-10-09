# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4 item 3: structured extraction of the as-of scouting report (EFV4_REPORT_LLM_
EXTRACTION, research s2.3; this module is the EFV4_REPORT_EXTRACT_PREP half).

WHAT THIS IS. The preparation and ingest half of the report-extraction family. It never
calls a model (owner EW2-10, 2026-10-08: the extraction runs as subagents in the owner's
session, no API key). It builds:

  1. THE CORPUS. One document per (F-LV row, report source): the in-window report of a
     real grader that efv_text_features attaches to the row, cleaned by
     efv_text_features.clean_report (the anachronism filter drops a report naming a
     later year; the grade string, n/n pairs, FV, ETA and every year are stripped), then
     REDACTED here (redact()). List vintages 2013 to 2019 on both sides; 2011 and 2012
     are dropped (backfilled pages, efv_text_features.DROPPED_VINTAGES) and the reserved
     vintages 2020 and 2021 are never built (efv_vintage_frame guard, CORPUS_VINTAGES is
     checked at import). A document's id is the sha256 of its redacted text, so carried
     identical text shares one id and one extraction.
  2. THE REDACTION (leakage protocol step 1). Before any text leaves this module: the
     player's own name forms ([PLAYER]); any other person whose full name is in the
     affiliated or major league stat caches or the draft caches ([PERSON]); the thirty
     clubs by nickname, by city-plus-nickname and by club city alone ([CLUB]); minor
     league affiliates named after a level word, plus every such place seen anywhere in
     the corpus ([AFFILIATE]); schools by lexicon and by pattern ([SCHOOL]); money
     ([MONEY]); pick and rank numbers ([N]); ages ([AGE]). League names are protected
     (they carry level, not identity). The model never sees who the player is.
  3. THE CONTROLS. (a) Name-redaction invariance: CONTROL_N documents with the identity
     redaction switched off (grades and years stay stripped), so a later read can
     withhold any field whose within-fold partial correlation with the outcome given u_c
     moves beyond its interval when names are left in. (b) The shuffled-document twin:
     CONTROL_N recipient rows, each handed the redacted document of a random other
     player of the same side and vintage. The read's full-frame twin permutes the main
     store and needs no new text; these re-extracted donor documents add the extractor's
     own test-retest noise to the twin. Both sets are mixed into control_NNNN chunks
     under opaque control ids; which id is which lives only in the manifest.
  4. THE FILES. chunk_NNNN.json and control_NNNN.json (CHUNK_SIZE documents each:
     doc_id, side, text, and control_id on a control), SCHEMA.json (one extraction, the
     twelve fields) and PROMPT.md (the fixed instruction: features of the text only,
     never guess identity, never output a grade the text does not state), written to an
     output folder the caller names; the manifest (document to row map, control maps,
     redaction receipt, coverage) to data/_labs/efv_w2/report_extract_manifest.json.
  5. THE LOADER. ingest() validates every out/*.json against its chunk, the prompt hash
     and the schema, and merges the extractions into data/_labs/efv_w2/
     report_extract.jsonl keyed by (doc_id, control_id, prompt_sha256, model_id): the
     log a later read replays without any model.

THE COLUMNS (later read; row_fields() and writer_minus_stated() are the fixed functions).
    txt_conviction, txt_hedge_count, txt_risk, txt_injury_mention, txt_makeup,
    txt_body_projection, txt_role_ceiling, txt_role_floor, txt_reliever_risk (pitchers),
    txt_approach_concern (hitters), txt_writer_minus_stated, txt_arrival.
A row with two source documents (2019: Pipeline and FanGraphs) takes the mean of each
numeric field over its documents and the maximum of the injury flag. The extraction is a
fixed function of the document, so only the ridge on these columns is fold-fitted (on
vintages strictly below V, the lab's rule). Heads: txt_arrival and txt_role_floor go to
the timing head, the rest to the skill head; a hitter skill column is offered only when
the DS-03 probe on report_absent reads BALANCED (efv_text_features.offered_columns;
IMBALANCED today, so hitters enter the timing head only).

DEFAULTS (named; the owner may choose otherwise): the writer-versus-grade term is the
within-(side, V) percentile of the extracted writer_level minus the consensus percentile
u_c, because the stated grade is redacted before the call and the prompt forbids
outputting a grade; ages, money and pick or rank numbers are redacted as identity cues;
club city names that are also states (Arizona, Colorado, Florida, Minnesota, Texas,
Washington) are redacted only beside a nickname; a lone first name is never redacted;
CONTROL_N 300 per control set, half per side; chunk order is a seeded shuffle so no
chunk is one vintage.

BANS. No model call, no network, no WAR, debut or label read; nothing is grouped,
counted or averaged by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md); consensus
enters only as the within-(side, V) percentile in writer_minus_stated.

Run:  python efv_w2_report_llm.py --build OUTDIR    (corpus, controls, SCHEMA, PROMPT,
                                                     manifest)
      python efv_w2_report_llm.py --ingest OUTDIR   (OUTDIR/out/*.json into the store)
      python efv_w2_report_llm.py                   (status; no statistic)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_text_features as T  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

MODULE = "efv_w2_report_llm"
ITEM = "EFV4_REPORT_LLM_EXTRACTION"
DB_PATH = ROOT / "prospects.db"
LAB_DIR = ROOT / "data" / "_labs" / "efv_w2"
STORE_PATH = LAB_DIR / "report_extract.jsonl"
MANIFEST_PATH = LAB_DIR / "report_extract_manifest.json"
CACHE = ROOT / ".cache"

#: List vintages the corpus holds: the first contemporaneous text vintage to the last
#: development vintage. Never a reserved vintage (checked below).
CORPUS_VINTAGES: tuple[int, ...] = tuple(range(T.FIRST_TEXT_VINTAGE, min(F.RESERVED_LV)))
if set(CORPUS_VINTAGES) & set(F.RESERVED_LV) or set(CORPUS_VINTAGES) & set(T.DROPPED_VINTAGES):
    raise F.ReservedFrameError(f"corpus vintages reach a reserved or dropped vintage: "
                               f"{CORPUS_VINTAGES}")
CHUNK_SIZE = 40
CONTROL_N = 300
SEED = 20261008
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# the schema: one extraction
# ---------------------------------------------------------------------------

INJURY_VALUES: tuple[str, ...] = ("none", "elbow", "shoulder", "other_arm", "back_core",
                                  "leg_hip", "hand_wrist", "head", "illness_other")

#: field -> (kind, lo, hi, nullable_on, definition). kind "int" or "enum". A field is
#: null exactly on the side named in nullable_on ("hit" or "pit"); role_floor may be
#: null on either side (the text names no floor).
FIELDS: dict[str, dict] = {
    "conviction": {"kind": "int", "lo": 1, "hi": 5, "null_side": None,
                   "def": ("How sure the writer sounds about the player's future as "
                           "described: 1 openly unsure or split, 3 ordinary, 5 emphatic "
                           "and unqualified. Silent: 3.")},
    "hedge_count": {"kind": "int", "lo": 0, "hi": 40, "null_side": None,
                    "def": ("Number of hedging constructions about the player's future "
                            "(could, might, may, if he, needs to, has to, has a chance "
                            "to, questions about, remains to be seen, whether). Silent: 0.")},
    "risk": {"kind": "int", "lo": 1, "hi": 5, "null_side": None,
             "def": ("How much the text stresses downside or uncertainty: 1 safe, polished, "
                     "high floor; 5 raw, volatile, long way to go. Silent: 3.")},
    "injury_mention": {"kind": "enum", "values": list(INJURY_VALUES), "null_side": None,
                       "def": ("The most serious injury or health problem the text names "
                               "for the player, by body area; none when it names none.")},
    "makeup": {"kind": "int", "lo": -1, "hi": 1, "null_side": None,
               "def": ("Work ethic, character, coachability, competitiveness, maturity: "
                       "+1 praised, -1 questioned, 0 not discussed or mixed.")},
    "body_projection": {"kind": "int", "lo": -1, "hi": 1, "null_side": None,
                        "def": ("+1 projectable frame or room to add strength; -1 maxed "
                                "out, heavy or soft body, conditioning concern; 0 not "
                                "discussed or neutral.")},
    "role_ceiling": {"kind": "int", "lo": 1, "hi": 5, "null_side": None,
                     "def": ("Best realistic big league role the text describes: 1 depth "
                             "or up-and-down, 2 bench player or middle reliever, 3 regular "
                             "at the low end, back-end starter or late-inning reliever, 4 "
                             "above-average regular or mid-rotation starter, 5 star or "
                             "front-of-the-rotation starter.")},
    "role_floor": {"kind": "int", "lo": 1, "hi": 5, "null_side": "both",
                   "def": ("The fallback role the text names if things go wrong, same "
                           "scale as role_ceiling and never above it; null when the text "
                           "names no fallback.")},
    "reliever_risk": {"kind": "int", "lo": 1, "hi": 5, "null_side": "hit",
                      "def": ("Pitchers only (null for hitters): 1 text affirms a "
                              "starter, 2 no bullpen mention, 3 bullpen named as a "
                              "possible fallback, 4 bullpen called likely, 5 already or "
                              "only a reliever.")},
    "approach_concern": {"kind": "int", "lo": 0, "hi": 3, "null_side": "pit",
                         "def": ("Hitters only (null for pitchers): how many of three "
                                 "concerns the text raises: swing-and-miss or "
                                 "strikeouts; chase or poor pitch recognition; passivity "
                                 "or too few walks.")},
    "writer_level": {"kind": "int", "lo": 1, "hi": 7, "null_side": None,
                     "def": ("Overall strength of prospect the prose describes, weighing "
                             "upside and the odds of reaching it: 1 fringe, 2 depth, 3 "
                             "possible role player, 4 likely big leaguer in a modest role, "
                             "5 everyday player or mid-rotation starter, 6 above-average "
                             "to all-star, 7 potential star. A reading of the words, not "
                             "a grade.")},
    "arrival": {"kind": "int", "lo": -2, "hi": 2, "null_side": None,
                "def": ("How soon the text says he reaches the majors or a regular role: "
                        "-2 a long way off, -1 time needed, 0 neutral or silent, +1 "
                        "moving fast or close, +2 ready now.")},
}
FIELD_ORDER: tuple[str, ...] = tuple(FIELDS)

#: field -> served column name (the lab's names). writer_level feeds the derived
#: writer-versus-grade term; injury_mention becomes a 0/1 flag.
COLUMN_OF: dict[str, str] = {f: f"txt_{f}" for f in FIELD_ORDER}
COLUMN_OF["writer_level"] = "txt_writer_minus_stated"
COLUMNS: tuple[str, ...] = tuple(COLUMN_OF[f] for f in FIELD_ORDER)
TIMING_COLUMNS: frozenset[str] = frozenset({"txt_arrival", "txt_role_floor"})
SIDE_ONLY: dict[str, str] = {"txt_reliever_risk": "pit", "txt_approach_concern": "hit"}


def column_head(column: str) -> str:
    return "time" if column in TIMING_COLUMNS else "skill"


def _arms() -> tuple[dict, ...]:
    out = []
    for side in F.SIDES:
        for col in COLUMNS:
            if SIDE_ONLY.get(col, side) != side:
                continue
            out.append({"name": f"rpt_{col[4:]}_{side}", "column": col, "side": side,
                        "head": column_head(col), "kind": "column_pending_extraction",
                        "retest": False,
                        "source": {"module": MODULE, "attr": "row_fields"}})
    return tuple(out)


#: The arms (one column per side and field). Kind column_pending_extraction: the lab
#: cannot read them until the store holds the extraction.
ARMS: tuple[dict, ...] = _arms()
ARM_NAMES: tuple[str, ...] = tuple(a["name"] for a in ARMS)


def json_schema() -> dict:
    """The JSON schema of one extraction (the fields object)."""
    props = {}
    for f, spec in FIELDS.items():
        if spec["kind"] == "enum":
            p = {"type": "string", "enum": list(spec["values"])}
        else:
            p = {"type": "integer", "minimum": spec["lo"], "maximum": spec["hi"]}
            if spec["null_side"]:
                p = {"type": ["integer", "null"], "minimum": spec["lo"],
                     "maximum": spec["hi"]}
        p["description"] = spec["def"]
        props[f] = p
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "eFV report extraction, one document",
            "x-schema-version": SCHEMA_VERSION,
            "type": "object", "additionalProperties": False,
            "required": list(FIELD_ORDER), "properties": props}


PROMPT_TEXT = """# eFV report extraction: the fixed instruction

You read scouting reports one at a time and record twelve features OF THE TEXT for each.
You are describing the writer's language, not judging the player.

## Rules

1. Use only the text in front of you. Do not use outside knowledge about players, clubs,
   drafts or careers. The text is redacted: [PLAYER] is the subject, [PERSON] another
   person, [CLUB] a major league organisation, [AFFILIATE] a minor league team, [SCHOOL] a
   school, [MONEY] an amount, [N] a pick or rank number, [AGE] an age.
2. Never try to work out who the player is, which club he is with or when the report was
   written. If you think you recognise him, ignore it and score the words on the page.
3. Never predict what happened to the player later. Score what the writer says.
4. Never output a grade the text does not state. The grade lines were removed; do not
   rebuild them. Every field is a description of the writer's language on a fixed scale.
5. Score each document on its own. Do not compare documents or adjust one score to
   another, and do not look at other chunks or at earlier output.
6. Fill every field. Use null only where the field says so. When the text is silent,
   use the field's stated silent value.

## The fields

The full definitions, types and ranges are in SCHEMA.json beside this file; in short:

- conviction (1 to 5): how sure the writer sounds about the future described. Silent 3.
- hedge_count (0 to 40): hedging constructions about the future (could, might, may, if
  he, needs to, has to, has a chance to, questions about, remains to be seen, whether).
- risk (1 to 5): 1 safe, polished, high floor; 5 raw, volatile, long way to go. Silent 3.
- injury_mention: the most serious injury or health problem named for the player, one of
  none, elbow (Tommy John, UCL), shoulder (labrum, rotator cuff), other_arm (forearm,
  biceps, other arm trouble), back_core (back, oblique, abdominal), leg_hip (knee, ankle,
  foot, hamstring, hip, leg), hand_wrist (hand, wrist, finger, thumb, hamate), head
  (concussion), illness_other (illness or anything else).
- makeup (-1, 0, +1): work ethic, character, competitiveness: praised +1, questioned -1,
  else 0.
- body_projection (-1, 0, +1): projectable or room to add strength +1; maxed out, heavy,
  soft or conditioning concern -1; else 0.
- role_ceiling (1 to 5): best realistic big league role the text describes: 1 depth or
  up-and-down, 2 bench player or middle reliever, 3 low-end regular, back-end starter or
  late-inning reliever, 4 above-average regular or mid-rotation starter, 5 star or
  front-of-the-rotation starter.
- role_floor (1 to 5 or null): the fallback the text names if things go wrong, same
  scale, never above role_ceiling; null when no fallback is named.
- reliever_risk (pitchers 1 to 5, hitters null): 1 affirmed starter, 2 no bullpen
  mention, 3 bullpen a possible fallback, 4 bullpen likely, 5 already or only a reliever.
- approach_concern (hitters 0 to 3, pitchers null): count of swing-and-miss, chase or poor
  pitch recognition, and passivity or too few walks raised as concerns.
- writer_level (1 to 7): overall strength of prospect the prose describes, weighing upside
  and the odds of reaching it: 1 fringe, 2 depth, 3 possible role player, 4 likely big
  leaguer in a modest role, 5 everyday player or mid-rotation starter, 6 above-average to
  all-star, 7 potential star. A reading of the words, not a grade.
- arrival (-2 to +2): how soon the text says he reaches the majors or a regular role: -2
  a long way off, -1 time needed, 0 neutral or silent, +1 moving fast or close, +2 ready
  now.

## Input

A chunk file: {"chunk": "...", "prompt_sha256": "...", "documents": [{"doc_id": "...",
"side": "hit" or "pit", "text": "..."}, ...]}. A document in a control chunk also carries
"control_id"; treat it exactly like any other document.

## Output

Write one file, out/<chunk>.json (the same name as the chunk file), holding exactly:

{"chunk": "<chunk>", "prompt_sha256": "<copied from the chunk>", "model_id": "<your
model id, e.g. claude-opus-5-5>", "extractions": [{"doc_id": "<copied>", "control_id":
"<copied, control chunks only>", "fields": {<the twelve fields>}}, ...]}

One extraction per document, in the chunk's order. Nothing else in the file: no notes,
no reasons, no extra keys.
"""


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def prompt_sha256(prompt: str = PROMPT_TEXT, schema: dict | None = None) -> str:
    """The prompt hash every extraction is keyed by: the instruction text and the
    canonical schema together, so a change to either is a new key."""
    schema = json_schema() if schema is None else schema
    blob = prompt.replace("\r\n", "\n") + "\n" + _canon(schema)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


PROMPT_SHA = prompt_sha256()

# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def validate_fields(fields, side: str) -> list[str]:
    """Problems with one extraction's fields object for a document of `side`; empty
    when it is valid."""
    errs: list[str] = []
    if not isinstance(fields, dict):
        return ["fields is not an object"]
    extra = sorted(set(fields) - set(FIELD_ORDER))
    if extra:
        errs.append(f"extra keys {extra}")
    for f, spec in FIELDS.items():
        if f not in fields:
            errs.append(f"missing {f}")
            continue
        v = fields[f]
        ns = spec["null_side"]
        if spec["kind"] == "enum":
            if v not in spec["values"]:
                errs.append(f"{f}={v!r} not in {spec['values']}")
            continue
        if ns == side and v is not None:
            errs.append(f"{f} must be null for side {side}")
            continue
        if v is None:
            if ns not in ("both", side):
                errs.append(f"{f} is null")
            continue
        if isinstance(v, bool) or not isinstance(v, int):
            errs.append(f"{f}={v!r} is not an integer")
            continue
        if not spec["lo"] <= v <= spec["hi"]:
            errs.append(f"{f}={v} outside {spec['lo']} to {spec['hi']}")
    rf, rc = fields.get("role_floor"), fields.get("role_ceiling")
    if (isinstance(rf, int) and isinstance(rc, int) and not isinstance(rf, bool)
            and not isinstance(rc, bool) and rf > rc):
        errs.append(f"role_floor {rf} above role_ceiling {rc}")
    return errs


# ---------------------------------------------------------------------------
# redaction
# ---------------------------------------------------------------------------

CLUB_NICKNAMES: tuple[str, ...] = (
    "Red Sox", "White Sox", "Blue Jays", "Devil Rays", "Diamondbacks", "D-backs",
    "Angels", "Astros", "Athletics", "A's", "Braves", "Brewers", "Cardinals", "Cubs",
    "Dodgers", "Giants", "Guardians", "Indians", "Mariners", "Marlins", "Mets",
    "Nationals", "Nats", "Orioles", "O's", "Padres", "Phillies", "Pirates", "Rangers",
    "Rays", "Reds", "Rockies", "Royals", "Tigers", "Twins", "Yankees", "Expos",
    "Bucs", "Jays", "Yanks", "Cards")
#: Club cities redacted alone (not followed by a capitalized word or a hometown word).
CLUB_CITIES: tuple[str, ...] = (
    "Kansas City", "Los Angeles", "New York", "San Diego", "San Francisco", "St. Louis",
    "Tampa Bay", "Atlanta", "Baltimore", "Boston", "Chicago", "Cincinnati", "Cleveland",
    "Detroit", "Houston", "Anaheim", "Miami", "Milwaukee", "Oakland", "Philadelphia",
    "Pittsburgh", "Seattle", "Toronto", "Montreal")
#: Club places that are also states: redacted only in front of a nickname.
CLUB_STATES: tuple[str, ...] = ("Arizona", "Colorado", "Florida", "Minnesota", "Texas",
                                "Washington", "Tampa")
US_STATES: frozenset[str] = frozenset((
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "Wisconsin", "Wyoming", "Carolina", "Dakota"))
#: Two-word states (a hometown, never a school by themselves).
US_STATES_2: frozenset[str] = frozenset((
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Rhode Island", "South Carolina", "South Dakota", "West Virginia"))
#: Countries and regions: an international signing is a feature of the text, never
#: redacted, so a school lexicon entry with one of these names is dropped.
COUNTRIES: frozenset[str] = frozenset((
    "Dominican", "Dominican Republic", "Venezuela", "Cuba", "Mexico", "Taiwan", "Japan",
    "Panama", "Curacao", "Brazil", "Colombia", "Bahamas", "Australia", "Korea",
    "South Korea", "Nicaragua", "Aruba", "Netherlands", "Germany", "Italy", "Canada",
    "China", "Puerto Rico", "Haiti", "Honduras", "Lithuania", "South Africa", "Spain",
    "France", "England", "Philippines", "Guatemala", "El Salvador", "Jamaica", "Peru",
    "Russia", "Uganda", "Zimbabwe", "Virgin Islands", "Czech Republic", "Great Britain",
    "Ireland", "Israel", "Hong Kong", "New Zealand", "Belize", "Cayman Islands"))
#: Minor league affiliate places of the 2013 to 2019 ladder that the corpus seldom
#: names after a level word (level_places finds the rest).
AFFILIATE_PLACES_EXTRA: tuple[str, ...] = (
    "Cedar Rapids", "South Bend", "West Michigan", "Great Lakes", "Quad Cities",
    "Bowling Green", "High Desert", "Visalia", "Bradenton", "Daytona", "Down East",
    "Buies Creek", "Fayetteville", "Hartford", "Northwest Arkansas", "Amarillo",
    "Lehigh Valley", "Scranton", "Wilkes-Barre", "Pawtucket", "Omaha", "New Orleans",
    "Oklahoma City", "Round Rock", "Colorado Springs", "Spokane", "Billings",
    "Great Falls", "Missoula", "Idaho Falls", "Johnson City", "Elizabethton", "Bristol",
    "Pulaski", "State College", "Jamestown", "Morgantown", "Staten Island", "Savannah",
    "Salem")
_NOT_SCHOOL: frozenset[str] = frozenset(("None", "Unknown", "N/A", "NA", "Other"))
#: Phrases kept verbatim (protected before any pass): leagues carry level, not identity.
_PROTECT_RE = re.compile(
    r"(?:\b[A-Z][\w\-]*\s){1,3}[Ll]eagues?\b|\bTommy John\b|\bFutures Game\b|"
    r"\bAll-Star(?: Game)?\b|\bGulf Coast\b|\bDominican Republic\b|\bPuerto Rico\b|"
    r"\bMajor Leagues?\b|\bMinor Leagues?\b|\bBig Leagues?\b|\bNew York-Penn\b")
_LEVEL_RE = re.compile(
    r"\b(Triple-A|Double-A|High-A|Hi-A|Low-A|Single-A|Advanced-A|Class A Advanced|"
    r"Class A Short Season|Class A Short-Season|Class A short-season|Class A|Class-A|"
    r"Advanced Class A|short-season A|short-season|"
    r"Short-Season A|Short-Season|Short Season A|Short Season|Rookie-level|Rookie)\s+"
    r"((?:St\.\s)?[A-Z][a-z][\w\-]*(?:\s[A-Z][a-z][\w\-]*){0,2})")
#: First words of a two-word place that are never redacted alone.
_PLACE_HEADS: frozenset[str] = frozenset((
    "Fort", "Lake", "Las", "San", "Santa", "Palm", "Myrtle", "Staten", "Corpus", "Grand",
    "Salt", "El", "New", "Hudson", "Inland", "Rancho", "West", "East", "North", "South",
    "High", "Low", "Port", "Mount", "Great"))
#: League words: a place never starts with one.
_LEAGUE_WORDS: frozenset[str] = frozenset((
    "Midwest", "Pioneer", "Appalachian", "Northwest", "Pacific", "Dominican", "Arizona",
    "Gulf", "Eastern", "Southern", "Texas", "Carolina", "California", "Florida",
    "International", "South", "Mexican", "Venezuelan", "Atlantic", "Cal", "Appy",
    "Sally", "Penn", "Short", "Season", "Rookie", "League", "Leagues"))
_NOT_PLACE: frozenset[str] = frozenset((
    "All-Star", "Futures", "Game", "Minor", "Major", "Draft", "The", "In", "He", "His",
    "But", "And", "With", "After", "Before", "When", "While", "As", "At", "For", "This",
    "That", "Though", "Although", "There", "It", "If", "Now", "Then", "Still", "Even",
    "Player", "Pitcher", "Hitter", "MVP", "Year", "Fall", "Instructional", "Complex",
    "Championship", "Playoffs", "Rookie", "Class", "Advanced", "Triple-A", "Double-A",
    "Top", "No", "Most", "Valuable", "Pitcher", "Of", "On", "To", "From"))
_MONEY_RE = re.compile(r"\$\s?\d[\d,.]*(?:\s?(?:million|mil|thousand|M|K|k)\b)?")
_RANK_RE = re.compile(r"(?:\bNo\.|#)\s?\d+\b")
_ORD = (r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|"
        r"twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|"
        r"nineteenth|twentieth")
_OVERALL_RE = re.compile(r"\b(?:\d+(?:st|nd|rd|th)|(?:" + _ORD + r"))(?=[\s-]+(?:overall|pick)\b)",
                         re.IGNORECASE)
_AGE_RES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b\d{2}(?=[\s-]+years?[\s-]+olds?\b)"), "[AGE]"),
    (re.compile(r"\b(ages?(?: of)?)\s+\d{2}\b"), r"\1 [AGE]"),
    (re.compile(r"\b(turn(?:s|ed|ing)?)\s+\d{2}\b"), r"\1 [AGE]"),
    (re.compile(r"\b(at|until|by)\s+(?:1[4-9]|2\d|3\d)\b(?!\s?(?:mph|percent|%|games|"
                r"innings|homers|home|steals|starts|appearances|pitches|-))"), r"\1 [AGE]"),
)
_SCHOOL_PAT = re.compile(
    r"\bUniversity of (?:[A-Z][\w.&'\-]*)(?:\s[A-Z][\w.&'\-]*){0,2}"
    r"|\b(?:(?!(?:The|A|An|At|In|From|His|For|With|And|To|As|By|After|Of)\s)"
    r"[A-Z][\w.&'\-]*\s){1,3}(?:State|University|College|CC|JC|Tech|A&M|Academy|"
    r"High School|HS|Community College|Junior College)\b(?:\s\([A-Z][\w.]*\))?"
    r"(?:\s(?:CC|JC|Community College|College))?")
_NAME_TOK = re.compile(r"[A-Z\u00c0-\u00de][\w'.\u2019]*")
_PH = "\u0000{}\u0000"
_PH_RE = re.compile("\u0000(\\d+)\u0000")
_WS = re.compile(r"[ \t]+")
_SUFFIX_TOK = frozenset(("Jr.", "Jr", "Sr.", "Sr", "II", "III", "IV"))
PERSON_WHITELIST: frozenset[str] = frozenset(("tommyjohn",))


_GEN_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv)\b\.?")


def _norm(s: str) -> str:
    """Accent-folded lower-case letters only, a generational suffix dropped (the
    efv_identity.norm_name rule), so a lexicon key and a text span normalise alike."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", _GEN_SUFFIX.sub("", s.lower()))


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def normalise_text(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "")
    for a, b in (("\ufffd", "'"), ("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'),
                 ("\u201d", '"'), ("\u2014", " - "), ("\u2013", "-"), ("\u00a0", " ")):
        t = t.replace(a, b)
    return t


def name_forms(names) -> list[str]:
    """The player's own name forms to redact, longest first: each full name (and its
    accent-folded spelling) and every tail of it after the first token (Adam Brett
    Walker: Brett Walker, Walker), a generational suffix dropped; a surname particle
    (de, del, la, los) is spelled both capitalized and lower-case. A lone first name
    and a lone particle are never forms."""
    forms: set[str] = set()
    for n in names or ():
        if not n:
            continue
        toks = [t for t in str(n).replace(",", " ").split() if t not in _SUFFIX_TOK]
        if not toks:
            continue
        for v in {" ".join(toks), _fold(" ".join(toks))}:
            vt = v.split()
            for tail in [vt] + [vt[k:] for k in range(1, len(vt))]:
                if len(tail) == 1 and (tail[0].lower() in _PARTICLES or len(tail[0]) < 2):
                    continue
                variants: list[list[str]] = [[]]
                for t in tail:
                    opts = ([t[:1].upper() + t[1:], t.lower()] if t.lower() in _PARTICLES
                            else [t])
                    variants = [v0 + [o] for v0 in variants for o in opts]
                forms.update(" ".join(x) for x in variants)
    return sorted(forms, key=lambda s: (-len(s), s))


_PARTICLES: frozenset[str] = frozenset(("de", "del", "la", "los", "las", "da", "dos",
                                        "van", "von", "der", "le", "di"))


def _sub_protect(t: str, store: list[str]) -> str:
    def rep(m):
        store.append(m.group(0))
        return _PH.format(len(store) - 1)
    return _PROTECT_RE.sub(rep, t)


def _restore(t: str, store: list[str]) -> str:
    return _PH_RE.sub(lambda m: store[int(m.group(1))], t)


class Lexicon:
    """Everything the redaction reads besides the document: person full names
    (normalised), schools, affiliate places. Built once per corpus, recorded by count
    in the manifest."""

    def __init__(self, persons=(), schools=(), places=()):
        self.persons: frozenset[str] = frozenset(p for p in persons if p)
        sch = sorted({s for s in schools if s}, key=lambda s: (-len(s), s))
        self.schools: tuple[str, ...] = tuple(sch)
        self.places: tuple[str, ...] = tuple(sorted({p for p in places if p},
                                                    key=lambda s: (-len(s), s)))
        self._school_re = _alt_re(self.schools)
        self._place_re = _alt_re(self.places, guard_next=True)

    def receipt(self) -> dict:
        return {"persons": len(self.persons), "schools": len(self.schools),
                "places": len(self.places),
                "sha256": hashlib.sha256(_canon([sorted(self.persons), list(self.schools),
                                                 list(self.places)]).encode()).hexdigest()}


def _alt_re(words, guard_next: bool = False):
    if not words:
        return None
    alt = "|".join(re.escape(w) for w in words)
    tail = r"(?!\w)" + (r"(?!\s(?:League|Leagues)\b)" if guard_next else "")
    return re.compile(r"(?<![\w'])(?:" + alt + ")" + tail)


_CLUB_RE = re.compile(
    r"(?<![\w'])(?:(?:" + "|".join(re.escape(c) for c in CLUB_CITIES + CLUB_STATES)
    + r")\s)?(?:" + "|".join(re.escape(n) for n in CLUB_NICKNAMES) + r")(?!\w)")
_CITY_RE = re.compile(
    r"(?<![\w'])(?:" + "|".join(re.escape(c) for c in CLUB_CITIES) + r")(?![\w-])"
    r"(?!\s[A-Z])(?!-born|-based|-area|\s(?:native|high|prep|product|area|suburb|"
    r"schooler|hs)\b)")


def _redact_persons(t: str, persons: frozenset[str], counts: dict) -> str:
    """Replace every run of 2 or 3 capitalized tokens whose normalised form is a known
    person's full name by [PERSON] (a trailing possessive is kept)."""
    if not persons:
        return t
    out = []
    pos = 0
    toks = list(_NAME_TOK.finditer(t))
    i = 0
    while i < len(toks):
        hit = None
        for n in (3, 2):
            if i + n > len(toks):
                continue
            span = toks[i:i + n]
            if any(t[span[k].end():span[k + 1].start()] not in (" ", "-")
                   for k in range(n - 1)):
                continue
            raw = t[span[0].start():span[-1].end()]
            poss = ""
            if raw.endswith(".") and len(raw.split()[-1]) > 2:
                raw = raw[:-1]
            for suf in ("'s", "'"):
                if raw.endswith(suf):
                    raw, poss = raw[:-len(suf)], suf
                    break
            key = _norm(raw)
            if key in persons and key not in PERSON_WHITELIST:
                hit = (span[0].start(), span[0].start() + len(raw), poss, n)
                break
        if hit:
            out.append(t[pos:hit[0]])
            out.append("[PERSON]")
            pos = hit[1]
            counts["person"] = counts.get("person", 0) + 1
            i += hit[3]
        else:
            i += 1
    out.append(t[pos:])
    return "".join(out)


def redact(text: str, *, player_names=(), lexicon: Lexicon | None = None,
           identity: bool = True) -> tuple[str, dict]:
    """(redacted text, counts by token) for one cleaned report. identity=False is the
    name-redaction invariance control: no identity pass at all (player, persons, clubs,
    affiliates, schools, money, pick and rank numbers, ages); the input is already
    stripped of grades and years by efv_text_features.clean_report either way."""
    lex = lexicon or Lexicon()
    counts: dict[str, int] = {}
    t = normalise_text(text)
    if not identity:
        return _WS.sub(" ", t).strip(), counts
    store: list[str] = []
    t = _sub_protect(t, store)

    def sub(pat, repl, s, key):
        new, n = pat.subn(repl, s)
        if n:
            counts[key] = counts.get(key, 0) + n
        return new

    t = sub(_MONEY_RE, "[MONEY]", t, "money")
    t = sub(_RANK_RE, "No. [N]", t, "rank")
    t = sub(_OVERALL_RE, "[N]", t, "pick")
    for pat, repl in _AGE_RES:
        t = sub(pat, repl, t, "age")
    for form in name_forms(player_names):
        pat = re.compile(r"(?<![\w'])" + re.escape(form) + r"(?![\w])")
        t = sub(pat, "[PLAYER]", t, "player")
    t = _redact_persons(t, lex.persons, counts)
    if lex._school_re is not None:
        t = sub(lex._school_re, "[SCHOOL]", t, "school")
    t = sub(_SCHOOL_PAT, "[SCHOOL]", t, "school")
    t = sub(_CLUB_RE, "[CLUB]", t, "club")
    t = sub(_CITY_RE, "[CLUB]", t, "club")

    def lvl(m):
        place = m.group(2)
        first = place.split()[0]
        if first in _NOT_PLACE or first in _LEAGUE_WORDS or first.startswith("["):
            return m.group(0)
        counts["affiliate"] = counts.get("affiliate", 0) + 1
        return f"{m.group(1)} [AFFILIATE]"
    t = _LEVEL_RE.sub(lvl, t)
    if lex._place_re is not None:
        t = sub(lex._place_re, "[AFFILIATE]", t, "affiliate")
    t = _restore(t, store)
    return _WS.sub(" ", t).strip(), counts


def level_places(texts) -> list[str]:
    """Affiliate places named right after a level word anywhere in `texts` (Double-A
    Altoona -> Altoona), minus anything also used as a lower-case word in the corpus
    (reading, mobile), a state, a club city or a protected word."""
    seen: dict[str, int] = {}
    lower: dict[str, int] = {}
    low_re = re.compile(r"\b[a-z][a-z']+\b")
    for t in texts:
        t = normalise_text(t)
        for w in low_re.findall(t):
            lower[w] = lower.get(w, 0) + 1
        prot: list[str] = []
        tp = _sub_protect(t, prot)
        for m in _LEVEL_RE.finditer(tp):
            place = m.group(2)
            if place.split()[0] in _NOT_PLACE or place.split()[0] in _LEAGUE_WORDS:
                continue
            seen[place] = seen.get(place, 0) + 1
    out = []
    bad = (set(US_STATES) | set(CLUB_CITIES) | set(CLUB_STATES) | set(_NOT_PLACE)
           | set(_LEAGUE_WORDS) | set(CLUB_NICKNAMES))
    for p in seen:
        words = p.split()
        if p in bad or any(w in bad for w in words):
            continue
        if len(words) == 1 and p in _PLACE_HEADS or p.endswith("-") or p.startswith("Short"):
            continue
        if any(lower.get(w.lower(), 0) >= 3 for w in words):
            continue
        out.append(p)
    return sorted(out)


def school_lexicon(db_path: Path | str = DB_PATH) -> list[str]:
    """School names from the draft tables and FanGraphs signed_from fields, with the
    state parenthetical dropped and an HS name also spelled High School. A single word
    that is a state is left out (a hometown, not a school)."""
    raw: set[str] = set()
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        for q in ("SELECT school FROM draft_results", "SELECT school FROM draft_players",
                  "SELECT college_commit FROM draft_players"):
            try:
                raw.update(r[0] for r in con.execute(q) if r[0])
            except sqlite3.Error:
                pass
        try:
            for (tj,) in con.execute("SELECT tools_json FROM snapshots WHERE source = "
                                     "'fangraphs' AND tools_json LIKE '%signed_from%'"):
                try:
                    s = ((json.loads(tj) or {}).get("_extras") or {}).get("signed_from")
                except (TypeError, ValueError):
                    s = None
                if isinstance(s, str):
                    raw.add(s)
        except sqlite3.Error:
            pass
    finally:
        con.close()
    out: set[str] = set()
    for s in raw:
        s = re.sub(r"\s*\([^)]*\)", "", normalise_text(s)).strip()
        if len(s) < 4 or not s[0].isupper():
            continue
        if re.fullmatch(r"[A-Z]{2,3}", s) or s in US_STATES or s in CLUB_CITIES:
            continue
        if s.split()[0] in US_STATES and len(s.split()) == 1:
            continue
        if s in US_STATES_2 or s in COUNTRIES or s in _NOT_SCHOOL:
            continue
        out.add(s)
        if s.endswith(" HS"):
            out.add(s[:-3] + " High School")
            out.add(s[:-3] + " High")
    return sorted(out)


def drop_common_words(words, texts, name_tokens=frozenset(), min_lower: int = 3) -> list[str]:
    """Single-word entries of `words` that are safe to redact everywhere: not used as a
    lower-case word at least min_lower times in `texts` (mobile, liberty), not a token
    of any person's name (Bradley, Chapman, Troy), not a word of a club city or a
    state. Multi-word entries pass unchanged."""
    lower: dict[str, int] = {}
    for t in texts:
        for w in re.findall(r"\b[a-z][a-z']+\b", t):
            lower[w] = lower.get(w, 0) + 1
    city_words = {w for c in CLUB_CITIES + CLUB_STATES for w in c.split()}
    out = []
    for w in words:
        if " " not in w and (lower.get(w.lower(), 0) >= min_lower or w in name_tokens
                             or w in city_words or w in US_STATES):
            continue
        out.append(w)
    return out


def person_lexicon(cache: Path = CACHE, tokens: set | None = None) -> set[str]:
    """Normalised full names of every person in the minor and major league season-line
    caches (2005 on), the major league caches 2000 to 2004 and the draft caches. Only a
    name of two or more tokens enters. When `tokens` is a set, every name token
    (accent-folded) is added to it."""
    names: set[str] = set()

    def add(n):
        if isinstance(n, str) and len(n.split()) >= 2:
            k = _norm(n)
            if len(k) >= 6:
                names.add(k)
                if tokens is not None:
                    tokens.update(_fold(t) for t in n.split())

    for p in sorted((cache / "milb_stats").glob("*.json")):
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows if isinstance(rows, list) else ():
            add(r.get("name"))
    for p in sorted(cache.glob("fa_statsapi_*_200[0-4].json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for blk in doc.get("stats") or ():
            for s in blk.get("splits") or ():
                add((s.get("player") or {}).get("fullName"))
    for p in sorted((cache / "draft_history").glob("*.json")):
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows if isinstance(rows, list) else ():
            add(r.get("name"))
    return names


def player_names(db_path: Path | str = DB_PATH) -> dict[str, list[str]]:
    """{player_key: every printed name the snapshots and players tables carry}."""
    out: dict[str, set[str]] = {}
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        for q in ("SELECT DISTINCT player_key, player_name FROM snapshots",
                  "SELECT player_key, player_name FROM players"):
            for pk, n in con.execute(q):
                if pk and n:
                    out.setdefault(pk, set()).add(str(n))
    finally:
        con.close()
    return {k: sorted(v) for k, v in out.items()}


# ---------------------------------------------------------------------------
# the corpus
# ---------------------------------------------------------------------------


def doc_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def row_documents(rows: list[dict], reports: dict[str, list[dict]]) -> list[dict]:
    """Per (row, source) the raw in-window report the row's attach_text kept (the same
    latest-in-window rule), cleaned. Each: side, vintage, player_key, source, date,
    clean (cleaned text). A dropped (later-year) report yields nothing."""
    out = []
    for r in rows:
        V = int(r["vintage"])
        F.guard_score_request(V, purpose="report extraction corpus")
        if V in T.DROPPED_VINTAGES:
            continue
        kept = {(s["source"], s["date"]): s["sha256"] for s in r.get("report_sources") or ()}
        if not kept:
            continue
        for rep in reports.get(r["player_key"], ()):
            key = (rep["source"], str(rep["date"])[:10])
            if key not in kept or T._sha(rep["text"]) != kept[key]:
                continue
            c = T.clean_report(normalise_text(rep["text"]), V)
            if c["dropped"] or not c["text"]:
                continue
            out.append({"side": r["side"], "vintage": V, "player_key": r["player_key"],
                        "source": rep["source"], "date": key[1], "clean": c["text"]})
            kept.pop(key)
    return out


def build_corpus(docs: list[dict], names: dict[str, list[str]], lexicon: Lexicon) -> dict:
    """Redact every (row, source) document. Returns {"documents": {doc_id: {side,
    text}}, "rows": [...], "counts": {...}, "residual": [...]} where rows map each
    (side, vintage, player_key, source) to its doc_id."""
    documents: dict[str, dict] = {}
    rows = []
    counts: dict[str, int] = {}
    residual = []
    for d in docs:
        pn = names.get(d["player_key"], [])
        red, c = redact(d["clean"], player_names=pn, lexicon=lexicon)
        for k, v in c.items():
            counts[k] = counts.get(k, 0) + v
        did = doc_id(red)
        prev = documents.get(did)
        if prev is None:
            documents[did] = {"side": d["side"], "text": red}
        elif prev["side"] != d["side"]:
            prev.setdefault("sides", sorted({prev["side"], d["side"]}))
        rows.append({"side": d["side"], "vintage": d["vintage"],
                     "player_key": d["player_key"], "source": d["source"],
                     "date": d["date"], "doc_id": did, "redactions": c})
        for n in pn:
            toks = [t for t in n.split() if t not in _SUFFIX_TOK]
            last = toks[-1] if len(toks) >= 2 else None
            if last and len(last) >= 4 and re.search(
                    r"(?<![\w'])" + re.escape(last) + r"(?![\w])", red):
                residual.append({"doc_id": did, "player_key": d["player_key"]})
                break
    return {"documents": documents, "rows": rows, "counts": counts, "residual": residual}


def build_controls(docs: list[dict], corpus: dict, names: dict[str, list[str]],
                   lexicon: Lexicon, *, n: int = CONTROL_N, seed: int = SEED) -> dict:
    """The two control sets. invariance: n documents (half per side, seeded) whose
    identity redaction removed the player's name at least once, re-emitted with the
    identity pass off. shuffle: n recipient rows (half per side, seeded), each handed
    the redacted document of a random other player of the same side and vintage.
    Every control document gets an opaque control id."""
    rng = random.Random(seed)
    by_row = {(r["side"], r["vintage"], r["player_key"], r["source"]): r
              for r in corpus["rows"]}
    inv, shf = [], []
    half = n // 2
    for side in F.SIDES:
        pool = [d for d in docs if d["side"] == side
                and by_row[(side, d["vintage"], d["player_key"], d["source"])]
                ["redactions"].get("player", 0) > 0]
        pool.sort(key=lambda d: (d["vintage"], d["player_key"], d["source"]))
        for d in rng.sample(pool, min(half, len(pool))):
            raw, _ = redact(d["clean"], player_names=names.get(d["player_key"], []),
                            lexicon=lexicon, identity=False)
            r = by_row[(side, d["vintage"], d["player_key"], d["source"])]
            inv.append({"kind": "invariance", "side": side, "vintage": d["vintage"],
                        "player_key": d["player_key"], "source": d["source"],
                        "paired_doc_id": r["doc_id"], "doc_id": doc_id(raw),
                        "text": raw})
        rows = sorted((r for r in corpus["rows"] if r["side"] == side),
                      key=lambda r: (r["vintage"], r["player_key"], r["source"]))
        for r in rng.sample(rows, min(half, len(rows))):
            donors = [x for x in rows if x["vintage"] == r["vintage"]
                      and x["player_key"] != r["player_key"]]
            if not donors:
                continue
            dn = rng.choice(donors)
            shf.append({"kind": "shuffle", "side": side, "vintage": r["vintage"],
                        "player_key": r["player_key"], "source": r["source"],
                        "donor_player_key": dn["player_key"],
                        "donor_doc_id": dn["doc_id"], "doc_id": dn["doc_id"],
                        "text": corpus["documents"][dn["doc_id"]]["text"]})
    out = inv + shf
    for i, c in enumerate(out):
        c["control_id"] = "c" + hashlib.sha256(
            f"{seed}|{c['kind']}|{i}|{c['doc_id']}".encode()).hexdigest()[:16]
    return {"invariance": inv, "shuffle": shf}


def chunk_payloads(corpus: dict, controls: dict, *, size: int = CHUNK_SIZE,
                   seed: int = SEED) -> dict[str, dict]:
    """{file name: chunk object}. Corpus documents in a seeded shuffle of doc_id order;
    control documents of both kinds mixed in their own seeded shuffle."""
    rng = random.Random(seed + 1)
    ids = sorted(corpus["documents"])
    rng.shuffle(ids)
    out: dict[str, dict] = {}
    for k in range(0, len(ids), size):
        name = f"chunk_{k // size + 1:04d}"
        out[name + ".json"] = {
            "chunk": name, "prompt_sha256": PROMPT_SHA, "schema_version": SCHEMA_VERSION,
            "documents": [{"doc_id": i, "side": corpus["documents"][i]["side"],
                           "text": corpus["documents"][i]["text"]}
                          for i in ids[k:k + size]]}
    ctl = sorted(controls["invariance"] + controls["shuffle"], key=lambda c: c["control_id"])
    rng.shuffle(ctl)
    for k in range(0, len(ctl), size):
        name = f"control_{k // size + 1:04d}"
        out[name + ".json"] = {
            "chunk": name, "prompt_sha256": PROMPT_SHA, "schema_version": SCHEMA_VERSION,
            "documents": [{"doc_id": c["doc_id"], "control_id": c["control_id"],
                           "side": c["side"], "text": c["text"]} for c in ctl[k:k + size]]}
    return out


def coverage(corpus: dict) -> dict:
    """Document counts by side and vintage (rows, unique documents, by source). Counts
    only; no grade enters."""
    out: dict = {}
    for r in corpus["rows"]:
        k = f"{r['side']}:{r['vintage']}"
        b = out.setdefault(k, {"row_documents": 0, "by_source": {}, "_ids": set()})
        b["row_documents"] += 1
        b["by_source"][r["source"]] = b["by_source"].get(r["source"], 0) + 1
        b["_ids"].add(r["doc_id"])
    for b in out.values():
        b["unique_documents"] = len(b.pop("_ids"))
    return dict(sorted(out.items()))


def _write_json(path: Path, obj, *, indent=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=False)
    path.write_bytes((txt + "\n").encode("utf-8"))


def write_extract_files(out_dir: Path, chunks: dict[str, dict]) -> dict:
    """chunks/, SCHEMA.json, PROMPT.md and INDEX.json under out_dir; stale chunk files
    from an earlier build are removed so the folder is exactly this build."""
    out_dir = Path(out_dir)
    cdir = out_dir / "chunks"
    cdir.mkdir(parents=True, exist_ok=True)
    for p in cdir.glob("*.json"):
        if p.name not in chunks:
            p.unlink()
    for name, obj in chunks.items():
        _write_json(cdir / name, obj)
    _write_json(out_dir / "SCHEMA.json", json_schema(), indent=2)
    (out_dir / "PROMPT.md").write_bytes(PROMPT_TEXT.encode("utf-8"))
    (out_dir / "out").mkdir(exist_ok=True)
    index = {"prompt_sha256": PROMPT_SHA, "schema_version": SCHEMA_VERSION,
             "chunk_size": CHUNK_SIZE,
             "chunks": {n[:-5]: len(o["documents"]) for n, o in sorted(chunks.items())}}
    _write_json(out_dir / "INDEX.json", index, indent=2)
    return index


def build(out_dir: Path, *, manifest_path: Path = MANIFEST_PATH, db_path=DB_PATH,
          cache: Path = CACHE, log=print) -> dict:
    """The whole preparation on the real tree: frames, documents, redaction, controls,
    chunk files, manifest."""
    vs = CORPUS_VINTAGES
    universe = F.load_universe()
    reports = T.load_reports(db_path=db_path, lo=f"{min(vs) - 1}-01-01",
                             hi=f"{max(vs)}-05-01")
    docs: list[dict] = []
    for side in F.SIDES:
        by_v = T.text_rows(side, vs, universe=universe, reports=reports, db_path=db_path)
        for V in vs:
            docs += row_documents(by_v[V], reports)
    log(f"documents (row, source): {len(docs)}")
    names = player_names(db_path)
    cleans = [d["clean"] for d in docs]
    places = sorted(set(level_places(cleans)) | set(AFFILIATE_PLACES_EXTRA))
    name_tokens: set[str] = set()
    persons = person_lexicon(cache, tokens=name_tokens)
    schools = drop_common_words(school_lexicon(db_path), cleans, frozenset(name_tokens))
    lexicon = Lexicon(persons=persons, schools=schools, places=places)
    log(f"lexicon {lexicon.receipt()}")
    corpus = build_corpus(docs, names, lexicon)
    controls = build_controls(docs, corpus, names, lexicon)
    chunks = chunk_payloads(corpus, controls)
    index = write_extract_files(out_dir, chunks)
    n_main = sum(1 for n in chunks if n.startswith("chunk_"))
    manifest = {
        "produced_by": f"{MODULE}.py", "item": ITEM, "schema_version": SCHEMA_VERSION,
        "prompt_sha256": PROMPT_SHA, "seed": SEED, "chunk_size": CHUNK_SIZE,
        "vintages": list(vs), "dropped_vintages": list(T.DROPPED_VINTAGES),
        "reserved_never_built": sorted(F.RESERVED_LV),
        "note": ("development preparation only: no model call, no statistic, no served "
                 "number; the documents themselves live outside the repository"),
        "lexicon": lexicon.receipt(), "affiliate_places": places,
        "redaction_counts": dict(sorted(corpus["counts"].items())),
        "residual_surname_documents": len({r["doc_id"] for r in corpus["residual"]}),
        "n_row_documents": len(corpus["rows"]), "n_documents": len(corpus["documents"]),
        "n_chunks": n_main, "n_control_chunks": len(chunks) - n_main,
        "chunks": index["chunks"], "coverage": coverage(corpus),
        "rows": [{k: r[k] for k in ("side", "vintage", "player_key", "source", "date",
                                    "doc_id")} for r in corpus["rows"]],
        "controls": {k: [{x: c[x] for x in c if x != "text"} for c in v]
                     for k, v in controls.items()},
    }
    write_manifest(Path(manifest_path), manifest)
    return manifest


def write_manifest(path: Path, manifest: dict) -> None:
    """The manifest with one line per top-level scalar block and one line per row or
    control record, so a rebuild diffs by row."""
    lines = ["{"]
    keys = list(manifest)
    for i, k in enumerate(keys):
        v = manifest[k]
        end = "," if i < len(keys) - 1 else ""
        if k == "rows":
            body = ",\n".join("  " + _canon(r) for r in v)
            lines.append(f' "{k}": [\n{body}\n ]{end}')
        elif k == "controls":
            parts = []
            for j, (ck, cv) in enumerate(v.items()):
                body = ",\n".join("   " + _canon(r) for r in cv)
                cend = "," if j < len(v) - 1 else ""
                parts.append(f'  "{ck}": [\n{body}\n  ]{cend}')
            lines.append(f' "{k}": {{\n' + "\n".join(parts) + f"\n }}{end}")
        else:
            lines.append(f' "{k}": {_canon(v)}{end}')
    lines.append("}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# the loader
# ---------------------------------------------------------------------------


def store_key(rec: dict) -> tuple[str, str, str, str]:
    return (rec["doc_id"], rec.get("control_id") or "", rec["prompt_sha256"], rec["model_id"])


def read_store(path: Path = STORE_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()]


_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9.\-_]{2,63}$")


def ingest(out_dir: Path, *, chunks_dir: Path | None = None, store_path: Path = STORE_PATH,
           prompt_sha: str = PROMPT_SHA) -> dict:
    """Validate out_dir/*.json (the extractor's files; out_dir is usually OUTDIR/out)
    against their chunks (chunks_dir, default the sibling chunks/ folder), the prompt
    hash and the schema, and merge the valid extractions into the store keyed by
    (doc_id, control_id, prompt_sha256, model_id). A file with a wrong prompt hash, an
    unknown chunk or a bad model id is rejected whole; an invalid extraction is rejected
    alone; a key already in the store is kept as it was (the first extraction stands)
    and a differing repeat is counted as a conflict. Returns the receipt."""
    out_dir = Path(out_dir)
    chunks_dir = Path(chunks_dir) if chunks_dir else out_dir.parent / "chunks"
    existing = {store_key(r): r for r in read_store(store_path)}
    new: dict[tuple, dict] = {}
    rec = {"files": 0, "files_rejected": {}, "accepted": 0, "already_stored": 0,
           "conflicts": 0, "invalid": {}, "missing_documents": {}, "unknown_documents": {}}
    for p in sorted(out_dir.glob("*.json")):
        rec["files"] += 1
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            rec["files_rejected"][p.name] = f"unreadable: {e}"
            continue
        if not isinstance(doc, dict):
            rec["files_rejected"][p.name] = "not an object"
            continue
        name = doc.get("chunk")
        cpath = chunks_dir / f"{name}.json"
        if not isinstance(name, str) or name != p.stem or not cpath.exists():
            rec["files_rejected"][p.name] = f"no chunk file for {name!r}"
            continue
        if doc.get("prompt_sha256") != prompt_sha:
            rec["files_rejected"][p.name] = "prompt_sha256 does not match the prompt"
            continue
        model = doc.get("model_id")
        if not isinstance(model, str) or not _MODEL_RE.match(model):
            rec["files_rejected"][p.name] = f"bad model_id {model!r}"
            continue
        chunk = json.loads(cpath.read_text(encoding="utf-8"))
        if chunk.get("prompt_sha256") != prompt_sha:
            rec["files_rejected"][p.name] = "chunk was built under another prompt"
            continue
        want = {(d["doc_id"], d.get("control_id") or ""): d for d in chunk["documents"]}
        seen: set = set()
        valid: set = set()
        for ex in doc.get("extractions") or ():
            if not isinstance(ex, dict):
                rec["invalid"].setdefault(p.name, []).append("extraction is not an object")
                continue
            k = (ex.get("doc_id"), ex.get("control_id") or "")
            if k not in want:
                rec["unknown_documents"].setdefault(p.name, []).append(k[0])
                continue
            if k in seen:
                rec["invalid"].setdefault(p.name, []).append(f"{k[0][:12]}: repeated")
                continue
            seen.add(k)
            side = want[k]["side"]
            errs = validate_fields(ex.get("fields"), side)
            if errs:
                rec["invalid"].setdefault(p.name, []).append(f"{k[0][:12]}: {'; '.join(errs)}")
                continue
            valid.add(k)
            row = {"doc_id": k[0], "control_id": k[1] or None, "side": side,
                   "chunk": name, "prompt_sha256": prompt_sha, "model_id": model,
                   "schema_version": SCHEMA_VERSION,
                   "fields": {f: ex["fields"][f] for f in FIELD_ORDER}}
            sk = store_key(row)
            if sk in existing or sk in new:
                prior = existing.get(sk) or new[sk]
                if prior["fields"] != row["fields"]:
                    rec["conflicts"] += 1
                rec["already_stored"] += 1
                continue
            new[sk] = row
            rec["accepted"] += 1
        missing = [k[0] for k in want if k not in valid]
        if missing:
            rec["missing_documents"][p.name] = len(missing)
    if new:
        allrows = sorted(list(existing.values()) + list(new.values()),
                         key=lambda r: store_key(r))
        sp = Path(store_path)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_bytes("".join(_canon(r) + "\n" for r in allrows).encode("utf-8"))
    rec["store_rows"] = len(existing) + len(new)
    return rec


# ---------------------------------------------------------------------------
# the columns (fixed functions of the stored extraction)
# ---------------------------------------------------------------------------


def field_value(field: str, v):
    """The numeric value of one stored field (the injury enum becomes a 0/1 flag)."""
    if field == "injury_mention":
        return None if v is None else float(v != "none")
    return None if v is None else float(v)


def row_fields(manifest_rows: list[dict], store: list[dict], *, model_id: str,
               prompt_sha: str = PROMPT_SHA) -> dict[tuple, dict[str, float | None]]:
    """{(side, vintage, player_key): {field: value}} from the main-corpus extractions of
    one model under one prompt. A row with several source documents takes the mean of
    each numeric field over them and the maximum of the injury flag; a field null on
    every document is None. writer_level stays raw here (writer_minus_stated derives
    the column)."""
    ext = {r["doc_id"]: r["fields"] for r in store
           if not r.get("control_id") and r["model_id"] == model_id
           and r["prompt_sha256"] == prompt_sha}
    by_row: dict[tuple, list[dict]] = {}
    for m in manifest_rows:
        f = ext.get(m["doc_id"])
        if f is not None:
            by_row.setdefault((m["side"], int(m["vintage"]), m["player_key"]), []).append(f)
    out = {}
    for key, fl in by_row.items():
        vals = {}
        for field in FIELD_ORDER:
            xs = [field_value(field, f[field]) for f in fl]
            xs = [x for x in xs if x is not None]
            if not xs:
                vals[field] = None
            elif field == "injury_mention":
                vals[field] = max(xs)
            else:
                vals[field] = float(np.mean(xs))
        out[key] = vals
    return out


def writer_minus_stated(writer_level, fv, groups) -> np.ndarray:
    """txt_writer_minus_stated: the within-group percentile of the extracted
    writer_level minus the within-group consensus percentile u_c, over rows that carry
    both (NaN elsewhere). Groups are (side, vintage)."""
    wl = np.asarray([np.nan if w is None else float(w) for w in writer_level])
    cv = np.asarray([np.nan if c is None else float(c) for c in fv])
    g = list(groups)
    out = np.full(wl.size, np.nan)
    ok = np.flatnonzero(~np.isnan(wl) & ~np.isnan(cv))
    if ok.size:
        gg = [g[i] for i in ok]
        out[ok] = T.within_pct(wl[ok], gg) - T.within_pct(cv[ok], gg)
    return out


# ---------------------------------------------------------------------------
# status and CLI
# ---------------------------------------------------------------------------


def status(manifest_path: Path = MANIFEST_PATH, store_path: Path = STORE_PATH) -> dict:
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8")) \
        if Path(manifest_path).exists() else None
    store = read_store(store_path)
    out = {"prompt_sha256": PROMPT_SHA, "manifest": bool(m), "store_rows": len(store)}
    if m:
        out.update({k: m.get(k) for k in ("n_documents", "n_row_documents", "n_chunks",
                                          "n_control_chunks", "prompt_sha256")})
        out["manifest_prompt_current"] = m.get("prompt_sha256") == PROMPT_SHA
        ids = {r["doc_id"] for r in m.get("rows", [])}
        models: dict[str, int] = {}
        for r in store:
            if not r.get("control_id") and r["doc_id"] in ids \
                    and r["prompt_sha256"] == PROMPT_SHA:
                models[r["model_id"]] = models.get(r["model_id"], 0) + 1
        out["extracted_documents_by_model"] = models
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--build", metavar="OUTDIR", default="",
                    help="write chunks, controls, SCHEMA.json, PROMPT.md and the manifest")
    ap.add_argument("--ingest", metavar="OUTDIR", default="",
                    help="validate OUTDIR/out/*.json and merge into the store")
    a = ap.parse_args(argv)
    if a.build:
        m = build(Path(a.build))
        print(json.dumps({k: m[k] for k in ("n_row_documents", "n_documents", "n_chunks",
                                             "n_control_chunks", "prompt_sha256",
                                             "redaction_counts", "lexicon",
                                             "residual_surname_documents")}, indent=1))
        return 0
    if a.ingest:
        r = ingest(Path(a.ingest) / "out")
        print(json.dumps(r, indent=1))
        return 0 if not r["files_rejected"] else 1
    print(json.dumps(status(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
