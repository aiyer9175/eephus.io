# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
identity_repairs.py - the list of identity repairs a prospects.db must carry.

One entry per repair. tools/repair_identity_split_2026_09_30.py reads this list
and applies every entry (dry run by default, value-guarded writes, a dated
backup before any write, one receipt row per applied repair). The deploy box
keeps its own prospects.db, so the owner's answer B4ID-2 (2026-10-01) folds the
tool into the fWAR label epoch's step A as an idempotent, receipt-guarded
pipeline step: step A only wires `run_step()` of that tool; adding a repair
means adding an entry here.

Each entry names:
  repair_id   stable id, also the receipt key
  kind        "row_split": another human's board rows sat on board_key and
                moved to moved_to; board_key keeps its own id (right_id).
                The row moves are the tool's M02-11 tables (MOVES and the rest).
              "rebind": board_key served the wrong human's MLBAM id (wrong_id)
                and every row fetched through it; the key is re-bound to its
                own human (right_id) and the foreign rows are removed.
  board_key   the board key the repair is about
  wrong_id    the MLBAM id of the human who does NOT belong on board_key
  right_id    the MLBAM id of the human board_key belongs to
  proof       {"right": {...}, "wrong": {...}, "evidence": str}, each side
              with name, birth_date, position, org and the cached source that
              publishes them
  date        the day the repair was written (ISO)

"rebind" entries also carry what the tool needs to act:
  fragment_keys  other keys of the same human whose id-cache entry pointed at
                 wrong_id (FanGraphs __noid / __sa fragments, the bare slug)
  birth_date     (wrong human's date the keys carry, right human's date)
  foreign_rows   {table: (column, substring)}: rows on board_key or a
                 fragment key that were fetched through wrong_id; a row is
                 removed only when its column carries the substring
  split_key      where scrapers._SPLIT_KEYS routes wrong_id for these keys

Nothing here writes; this module is data plus a schema check.
"""

from __future__ import annotations

import re

KINDS = ("row_split", "rebind")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PROOF_FIELDS = ("name", "birth_date", "position", "org", "source")


def _human(name, birth_date, position, org, source):
    return {"name": name, "birth_date": birth_date, "position": position,
            "org": org, "source": source}


_M02_11_EVIDENCE = (
    "Census M02-11, owner answer 2026-09-25 batch 4, applied 2026-09-30 by "
    "tools/repair_identity_split_2026_09_30.py (commit 1987b1b2). MLB "
    "Pipeline's Person id on each cached ranked row names the human; the "
    "tool re-reads it from the cached page before every Pipeline row moves.")

_JOSE_RODRIGUEZ_692064 = _human(
    "Jose Rodriguez", "2001-07-18", "RHP", "TOR",
    "MLB Pipeline 2025 Dodgers Top 30, Person 692064; MLB debut 2026-09-18")

REPAIRS: tuple[dict, ...] = (
    {
        "repair_id": "m02_11_jose_rodriguez_679563",
        "kind": "row_split",
        "board_key": "jose_rodriguez",
        "wrong_id": 679563,
        "right_id": 692064,
        "moved_to": "jose_rodriguez_679563",
        "proof": {
            "right": _JOSE_RODRIGUEZ_692064,
            "wrong": _human(
                "Jose Rodriguez", "2001-05-13", "SS", "PHI",
                ".cache/mlb_pipeline_2021..2024_org_whitesox.html, Person "
                "679563; data/rosters_by_org.json"),
            "evidence": _M02_11_EVIDENCE,
        },
        "date": "2026-09-30",
    },
    {
        "repair_id": "m02_11_jose_rodriguez_800412",
        "kind": "row_split",
        "board_key": "jose_rodriguez",
        "wrong_id": 800412,
        "right_id": 692064,
        "moved_to": "jose_rodriguez_800412",
        "proof": {
            "right": _JOSE_RODRIGUEZ_692064,
            "wrong": _human(
                "Jose Rodriguez", "2005-06-10", "OF", "MIN",
                ".cache/mlb_pipeline_2023_org_twins.html and 2024, Person "
                "800412; data/rosters_by_org.json"),
            "evidence": _M02_11_EVIDENCE,
        },
        "date": "2026-09-30",
    },
    {
        "repair_id": "m02_11_jose_rodriguez_836624",
        "kind": "row_split",
        "board_key": "jose_rodriguez",
        "wrong_id": 836624,
        "right_id": 692064,
        "moved_to": "jose_rodriguez_836624",
        "proof": {
            "right": _JOSE_RODRIGUEZ_692064,
            "wrong": _human(
                "Jose Rodriguez", "2009-01-19", "SS", "MIL",
                ".cache/mlb_pipeline_2026_international.html and "
                "mlb_pipeline_2026_org_brewers.html, Person 836624"),
            "evidence": _M02_11_EVIDENCE,
        },
        "date": "2026-09-30",
    },
    {
        "repair_id": "m02_11_michael_massey_695602",
        "kind": "row_split",
        "board_key": "michael_massey",
        "wrong_id": 695602,
        "right_id": 686681,
        "moved_to": "michael_massey__sa3037259",
        "proof": {
            "right": _human(
                "Michael Massey", "1998-03-22", "2B", "KCR",
                "players row and MLB statline of 686681; MLB debut "
                "2022-07-15"),
            "wrong": _human(
                "Michael Massey", "2003-04-05", "RHP", "DET",
                ".cache/mlb_pipeline_2025_org_tigers.html, Person 695602 "
                "(its report reads 'no relation to the Royals second "
                "baseman of the same name')"),
            "evidence": _M02_11_EVIDENCE,
        },
        "date": "2026-09-30",
    },
    {
        "repair_id": "m02_11_carlos_rodriguez_677578",
        "kind": "row_split",
        "board_key": "carlos_rodriguez",
        "wrong_id": 677578,
        "right_id": 692230,
        "moved_to": "carlos_d_rodriguez",
        "proof": {
            "right": _human(
                "Carlos Rodriguez", "2001-11-27", "RHP", "MIL",
                "players row and MLB pitching line of 692230; MLB debut "
                "2024-06-11"),
            "wrong": _human(
                "Carlos D. Rodriguez", "2000-12-07", "OF", "SDP",
                ".cache/mlb_pipeline_2018..2021_org_brewers.html and "
                "mlb_pipeline_2025_org_braves.html, Person 677578"),
            "evidence": _M02_11_EVIDENCE,
        },
        "date": "2026-09-30",
    },
    {
        # Owner answer PVA-2 (2026-10-01): a dedicated repair task. Found by
        # PV_A_retention_defects_scorer (D7) and by B4_IDENTITY_SPLIT's C4b
        # probe (an SIRP row serving a hitter line).
        "repair_id": "flores_joshua_834237",
        "kind": "rebind",
        "board_key": "joshua_flores__sa3069242",
        "wrong_id": 832714,
        "right_id": 834237,
        "fragment_keys": ("joshua_flores", "joshua_flores__noid"),
        "birth_date": ("2007-11-03", "2007-06-14"),
        "foreign_rows": {
            "statlines": ("payload_json", '"mlbam_id": 832714'),
            "career_stats": ("payload_json", '"is_pitcher": false'),
            "acquisitions": ("team_name", "Baltimore Orioles"),
            "player_transactions": ("payload_json", "C Jose Flores"),
        },
        "split_key": "jose_flores_832714",
        "proof": {
            "right": _human(
                "Joshua Flores", "2007-06-14", "RHP", "MIL",
                ".cache/mlb_pipeline_draft_2025.html Person 834237 (P, "
                "2025 round 4 pick 125 by team 158, active roster ACL "
                "Brewers, Lake Central HS) and .cache/mlb_draft_api_2025.json "
                "(StatsAPI draft: bonus 722,500, born Crown Point IN)"),
            "wrong": _human(
                "Jose Flores", "2007-11-03", "C", "BAL",
                ".cache/player_index.json Person 832714 (StatsAPI sport 16 "
                "2026, C, team 3130); data/rosters_by_org.json (C, DSL "
                "Orioles Orange); his transaction log 'Baltimore Orioles "
                "signed C Jose Flores' 2025-01-15"),
            "evidence": (
                "The board row's own FanGraphs rows (fg id sa3069242, "
                "2025-07-31 to 2026-08-02) read SIRP MIL, 2025 draft, Lake "
                "Central HS (IN), bonus 722,500: the StatsAPI draft record "
                "of 834237 to the dollar. 832714 is a catcher signed out of "
                "the international market by Baltimore, so no MIL draft row "
                "can be his. Different first name, birth date, side of the "
                "ball, club and acquisition."),
        },
        "date": "2026-10-01",
    },
)


def by_id() -> dict[str, dict]:
    return {e["repair_id"]: e for e in REPAIRS}


def schema_errors(entries=REPAIRS) -> list[str]:
    """Every way an entry breaks the schema above; [] when the list is sound."""
    errs: list[str] = []
    seen: set[str] = set()
    for i, e in enumerate(entries):
        tag = e.get("repair_id") or f"entry {i}"
        for f in ("repair_id", "kind", "board_key", "wrong_id", "right_id",
                  "proof", "date"):
            if f not in e:
                errs.append(f"{tag}: missing {f}")
        if tag in seen:
            errs.append(f"{tag}: duplicate repair_id")
        seen.add(tag)
        if e.get("kind") not in KINDS:
            errs.append(f"{tag}: kind {e.get('kind')!r} not in {KINDS}")
        for f in ("wrong_id", "right_id"):
            if not isinstance(e.get(f), int) or isinstance(e.get(f), bool) \
                    or e.get(f, 0) <= 0:
                errs.append(f"{tag}: {f} must be a positive int")
        if e.get("wrong_id") == e.get("right_id"):
            errs.append(f"{tag}: wrong_id equals right_id")
        if not isinstance(e.get("board_key"), str) or not e.get("board_key"):
            errs.append(f"{tag}: board_key must be a non-empty string")
        if not _DATE.match(str(e.get("date", ""))):
            errs.append(f"{tag}: date must be YYYY-MM-DD")
        proof = e.get("proof") or {}
        for side in ("right", "wrong"):
            h = proof.get(side) or {}
            for f in _PROOF_FIELDS:
                if not h.get(f):
                    errs.append(f"{tag}: proof.{side}.{f} missing")
            if h.get("birth_date") and not _DATE.match(h["birth_date"]):
                errs.append(f"{tag}: proof.{side}.birth_date not ISO")
        if not proof.get("evidence"):
            errs.append(f"{tag}: proof.evidence missing")
        if e.get("kind") == "row_split" and not e.get("moved_to"):
            errs.append(f"{tag}: row_split needs moved_to")
        if e.get("kind") == "rebind":
            bd = e.get("birth_date")
            if not (isinstance(bd, tuple) and len(bd) == 2
                    and all(_DATE.match(str(x)) for x in bd)):
                errs.append(f"{tag}: rebind birth_date must be (wrong, right) ISO")
            elif bd[1] != proof.get("right", {}).get("birth_date"):
                errs.append(f"{tag}: birth_date[1] disagrees with proof.right")
            if not isinstance(e.get("fragment_keys"), tuple):
                errs.append(f"{tag}: fragment_keys must be a tuple")
            fr = e.get("foreign_rows")
            if not isinstance(fr, dict) or not all(
                    isinstance(v, tuple) and len(v) == 2 and all(v)
                    for v in fr.values()):
                errs.append(f"{tag}: foreign_rows must map table -> (column, substring)")
            if not e.get("split_key"):
                errs.append(f"{tag}: rebind needs split_key")
    return errs
