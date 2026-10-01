# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_identity_split_2026_09_30.py - apply every repair in identity_repairs.py
(the identity-repair list) to a prospects.db.

Since 2026-10-01 this tool reads the list: one entry per repair (the board key,
the wrong id, the right id, the proof, the date). Owner answer B4ID-2 folds it
into the fWAR label epoch's step A as an idempotent, receipt-guarded pipeline
step, so the deploy box repairs its own prospects.db on its first nightly after
the epoch's code sync; step A only wires run_step() below. A repair that has a
receipt for this DB is skipped; one with no receipt is dry-run, and written only
behind a dated backup; a receipt row is appended only for a repair that refused
nothing. Receipts: .cache/identity_repairs/receipts.jsonl (gitignored, so the
box's nightly `git checkout -- .` cannot drop them).

Two kinds of entry:
  row_split  the 2026-09-30 M02-11 split below (the tables MOVES and on)
  rebind     a board key bound to another human's MLBAM id (the Flores
             repair below); generic, driven by the entry's own fields

----------------------------------------------------------------------------
REBIND flores_joshua_834237 (owner answer PVA-2, 2026-10-01; found by the
PV_A scorer lane as its D7 and by B4_IDENTITY_SPLIT's C4b probe as an SIRP
row serving a hitter line).

The board row joshua_flores__sa3069242 is Joshua Flores, the Brewers RHP. It
served MLBAM id 832714, which is Jose Flores, an Orioles DSL catcher, and with
it Jose's DSL statline, his career line, his headshot binding, his transaction
log and a Baltimore international signing. Two humans, proved from cached MLB
pages (re-read 2026-10-01):

  834237  Joshua Christian Flores, b. 2007-06-14 (Crown Point, IN), P, bats
          R / throws R, drafted 2025 round 4 pick 125 by team 158 (Milwaukee),
          Lake Central HS, active roster ACL Brewers (parent org Milwaukee).
          Sources: .cache/mlb_pipeline_draft_2025.html, Apollo record
          "Person:834237"; .cache/mlb_draft_api_2025.json (StatsAPI draft
          2025: the same Person, signing bonus 722,500, pick value 599,600).
  832714  Jose Flores, b. 2007-11-03, C, team 3130 (DSL Orioles Orange).
          Sources: .cache/player_index.json (StatsAPI sport 16, season 2026:
          C, birthDate 2007-11-03, current_team_id 3130);
          data/rosters_by_org.json (C, DSL Orioles Orange, age 18.9); his own
          StatsAPI transaction log, which the wrong id wrote onto all three
          Flores keys: "Baltimore Orioles signed C Jose Flores" and "C Jose
          Flores assigned to DSL Orioles Orange", both 2025-01-15.
  The board row's own FanGraphs rows (fg id sa3069242; 2025-07-31,
  2026-02-12, 2026-07-23, 2026-08-02) read SIRP MIL, signed 2025 in the
  draft from Lake Central HS (IN) for 722,500: the StatsAPI draft record of
  834237 to the dollar. 832714 is a catcher Baltimore signed on the
  international market, so no MIL draft row can be his. First name, birth
  date, side of the ball, club and acquisition all differ.
  The players rows of all three Flores keys carry 2007-11-03, which is Jose's
  StatsAPI birth date (the PlayerIndex refresh writes the bound id's date);
  data/xfv_ungraded.json shows Jose at 2007-11-07 only because that file
  approximates a birth date from the roster age.

Writes (each guarded by the exact value it expects; see _repair_rebind):
  player_photos  832714 unbound from joshua_flores__sa3069242 (player_key set
                 NULL, its headshot context kept); 834237 bound to it ('milb',
                 the house default until headshots.resolve_ctx runs)
  players        birth_date 2007-11-03 -> 2007-06-14 on joshua_flores,
                 joshua_flores__noid and joshua_flores__sa3069242
  rows fetched through 832714, removed: the DSL hitter statline and career
                 line on the board key, the Baltimore IFA acquisitions on
                 the board key and joshua_flores__noid, and the "C Jose
                 Flores" transaction logs on all three keys. The bare key's
                 own MIL draft acquisition stays. The next ingest refetches
                 through 834237.
  id cache       joshua_flores and joshua_flores__noid 832714 -> 834237,
                 joshua_flores__sa3069242 null -> 834237
  Kept on purpose: roster_status rows (no debut, no 40-man, 0 options, no
  injuries: identity-free and equally true of Joshua) and the derived
  history (metric_snapshots, trade_value_history, grpo_score_history),
  disclosed at run time. Forward pin: scrapers._SPLIT_KEYS routes 832714 to
  jose_flores_832714 for all three keys, so a re-resolution cannot bind it
  back. The served row moves at the next regeneration (owner answer B4ID-1:
  no hand regeneration of data/xfv.json or the trade values).

----------------------------------------------------------------------------
ROW_SPLIT (2026-09-30): split the three merged debuted PROSPX identities the
final-pass census found (M02-11, owner answer 2026-09-25 batch 4):

  jose_rodriguez     served as SS with a TOR RHP's MLB pitching line
  michael_massey     served as RHP with a KCR 2B's MLB hitting line
  carlos_rodriguez   served as OF with a MIL RHP's pitching line

Follows tools/repair_merged_identities_2026_08_04.py and
tools/repair_identity_residue_2026_08_19.py: idempotent, dry run by default,
every write guarded by the exact value it expects to find, the INCUMBENT (the
human the key's player_photos binding already names) is never re-keyed, and
history computed while a key was merged is disclosed rather than moved.

THE DECISIVE EVIDENCE is MLB's own person id. Every MLB Pipeline row this
script moves was re-read from the cached Pipeline page it was scraped from
(.cache/mlb_pipeline_<year>_org_<club>.html and mlb_pipeline_2026_international
.html): each RankedPlayerEntity carries "player": {"__ref": "Person:<mlbam>"},
and the Person record carries the birthDate. scrape_mlb_pipeline read that id
and then keyed the row by name alone, which is the seam this repair closes
(scrapers.scrape_mlb_pipeline now routes the row through split_key_for_mlbam).
FanGraphs rows move on two signals: the FanGraphs player id or signing record
the row itself carries, and a side/era fact the incumbent cannot satisfy.

jose_rodriguez (bound to 692064, TOR RHP b.2001-07-18, MLB debut 2026-09-18).
Four humans' board rows sat on the key:
  679563  b.2001-05-13  CHW 2B/SS, now PHI AA SS (roster age 25.4)
          Pipeline White Sox Top 30 2021-2024 (Person 679563; Pipeline's own
          org field reads the placeholder "Office of the Commissioner"),
          FanGraphs CHW SS/2B 2020-02-13 .. 2023-08-01 (fg id 24388, signed
          2017 CHW from the Dominican Republic for $37,500), and the BA 2023
          White Sox Top 30 row (CHW, hitter tools). 692064 signed with LAD
          from Mexico in 2019 and has only ever pitched. -> jose_rodriguez_679563
  800412  b.2005-06-10  MIN OF, now MIN A OF (roster age 21.3)
          Pipeline Twins Top 30 2023 and 2024 (Person 800412). -> jose_rodriguez_800412
  836624  b.2009-01-19  MIL SS, MIL DSL (roster age 17.7)
          Pipeline 2026 International and Brewers Top 30 rows (Person 836624),
          re-minted on the bare key by the daily Pipeline upserts after the
          2026-08-04 repair moved his first rows. -> jose_rodriguez_836624
          (his existing key). His International row collides with the one
          already there on (source, interval_label, player_key), so it is
          applied the way insert_snapshots' upsert would have applied it
          (newer date and values onto his row) and the bare copy is removed.
  692064 keeps the Pipeline 2025 Dodgers row (Person 692064), the FanGraphs
  2026 trade-deadline SIRP/LAD row (sa3015437) and his own auto_detect debut
  row, whose SS/MIL position and org came from the contaminated players row
  and are restored to RHP/TOR. players[jose_rodriguez] goes SS/MIL/0 back to
  RHP/TOR/1. acquisitions[jose_rodriguez].bonus_usd 1,500,000 is 836624's
  2026 MIL signing (Spotrac 2026 MIL SS Venezuela $1.5M, FanGraphs sa3075073
  the same), matched by name; 692064's own FanGraphs record is a 2019 LAD J2
  signing for $15,000. Set to NULL, the value the pipeline produces once
  spotrac._IFA_ORG_SPLIT_KEYS routes the MIL row away.

michael_massey (bound to 686681, KCR 2B b.1998-03-22, MLB debut 2022-07-15).
  695602  b.2003-04-05  DET RHP (Wake Forest, 2024 draft, $522,500), now DET A
          Pipeline 2025 Tigers Top 30 (Person 695602; its own report reads
          "no relation to the Royals second baseman of the same name") and
          FanGraphs 2026-07-23 / 2026-08-02 SIRP DET (sa3037259). His earlier
          FanGraphs rows already sit on michael_massey__sa3037259, so that key
          is his. -> michael_massey__sa3037259
  players[michael_massey] RHP/DET/1 -> 2B/KCR/0 (the birth date is already
  the 2B's). His auto_detect debut row RHP/DET -> 2B/KCR. The two fragment
  keys of the RHP (michael_massey__sa3037259, michael_massey__noid) carry the
  2B's birth date 1998-03-22 and are set to 2003-04-05 (Pipeline birthDate,
  roster age 23.5). The id cache had both fragments resolving to the 2B's
  686681; re-pointed to 695602, and 695602 is bound to __sa3037259. Through
  that wrong id both fragments had been handed the 2B's draft row,
  transaction log and roster status (MLB debut 2022-07-15), which served the
  A-ball RHP as a debuted Royals draftee; those rows are removed (the 2B's
  own copies on michael_massey stay).

carlos_rodriguez (bound to 692230, MIL RHP b.2001-11-27, MLB debut 2024-06-11).
  677578  b.2000-12-07  the OF (MIL 2017 IFA, later ATL, now SDP AAA RF), whose
          own key is carlos_d_rodriguez (player_photos binds 677578 there).
          Pipeline Brewers Top 30 2018-2021 and Braves 2025 (Person 677578),
          FanGraphs CF MIL 2018-08-01 .. 2020-08-01 (hitter tools, from
          Venezuela). 692230 was drafted out of Florida SouthWestern in July
          2021 and has only pitched, so no 2018-2020 MIL row can be his.
          -> carlos_d_rodriguez

NOT DONE ON PURPOSE (disclosed at run time):
  * metric_snapshots, trade_value_history, grpo_score_history and the
    inferred trades rows on the three bare keys were computed while the keys
    were merged. Append-only history, left in place (house rule).
  * The FanGraphs fragment keys carlos_rodriguez__sa3005478 / __noid and
    jose_rodriguez__sa3015437 are one human under two keys (the C7 class),
    not merges. Folding them is an alias decision for the C7 queue.

Usage:
    python tools/repair_identity_split_2026_09_30.py            # dry run, every repair
    python tools/repair_identity_split_2026_09_30.py --apply    # write + receipts
    python tools/repair_identity_split_2026_09_30.py --only flores_joshua_834237
    python tools/repair_identity_split_2026_09_30.py --db PATH  # other DB
    python tools/repair_identity_split_2026_09_30.py --step     # the step A entry

--apply refuses to run unless a dated backup prospects.db.bak-identsplit-*
sits beside the DB (pass --make-backup to take one first).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import identity_repairs  # noqa: E402

DEFAULT_DB = HERE / "prospects.db"
ID_CACHE = HERE / ".cache" / "mlbam_ids.json"
RECEIPTS = HERE / ".cache" / "identity_repairs" / "receipts.jsonl"
BACKUP_TAG = "bak-identsplit"

# ---------------------------------------------------------------------------
# Snapshot moves. (id, source, snapshot_date, interval_label, from_key, to_key)
# Every field is checked before the row moves.
# ---------------------------------------------------------------------------
MOVES: list[tuple[int, str, str, str, str, str]] = [
    # jose_rodriguez -> 679563 (CHW 2B/SS, b.2001-05-13)
    (2869596, "fangraphs", "2020-02-13", "2020report", "jose_rodriguez", "jose_rodriguez_679563"),
    (2870775, "fangraphs", "2020-08-01", "2020updated", "jose_rodriguez", "jose_rodriguez_679563"),
    (2368176, "mlb_pipeline", "2021-01-22", "MLB Pipeline 2021 White Sox Top 30", "jose_rodriguez", "jose_rodriguez_679563"),
    (2175796, "fangraphs", "2021-02-26", "2021report", "jose_rodriguez", "jose_rodriguez_679563"),
    (2176965, "fangraphs", "2021-07-30", "2021updated", "jose_rodriguez", "jose_rodriguez_679563"),
    (2368190, "mlb_pipeline", "2022-01-22", "MLB Pipeline 2022 White Sox Top 30", "jose_rodriguez", "jose_rodriguez_679563"),
    (2178207, "fangraphs", "2022-02-24", "2022report", "jose_rodriguez", "jose_rodriguez_679563"),
    (2179470, "fangraphs", "2022-08-02", "2022updated", "jose_rodriguez", "jose_rodriguez_679563"),
    (2368223, "mlb_pipeline", "2023-01-22", "MLB Pipeline 2023 White Sox Top 30", "jose_rodriguez", "jose_rodriguez_679563"),
    (4645068, "baseballamerica", "2023-02-15", "Baseball America 2023 White Sox Top 30", "jose_rodriguez", "jose_rodriguez_679563"),
    (2180794, "fangraphs", "2023-02-23", "2023report", "jose_rodriguez", "jose_rodriguez_679563"),
    (2182047, "fangraphs", "2023-08-01", "2023updated", "jose_rodriguez", "jose_rodriguez_679563"),
    (2368261, "mlb_pipeline", "2024-01-22", "MLB Pipeline 2024 White Sox Top 30", "jose_rodriguez", "jose_rodriguez_679563"),
    # jose_rodriguez -> 800412 (MIN OF, b.2005-06-10)
    (2228965, "mlb_pipeline", "2023-01-22", "MLB Pipeline 2023 Twins Top 30", "jose_rodriguez", "jose_rodriguez_800412"),
    (2229752, "mlb_pipeline", "2024-01-22", "MLB Pipeline 2024 Twins Top 30", "jose_rodriguez", "jose_rodriguez_800412"),
    # jose_rodriguez -> 836624 (MIL DSL SS, b.2009-01-19), his existing key
    (4391482, "mlb_pipeline_international", "2026-09-30", "MLB Pipeline 2026 International", "jose_rodriguez", "jose_rodriguez_836624"),
    (4724622, "mlb_pipeline", "2026-09-30", "MLB Pipeline 2026 Brewers Top 30", "jose_rodriguez", "jose_rodriguez_836624"),
    # michael_massey -> 695602 (DET RHP, b.2003-04-05), his existing key
    (2111395, "mlb_pipeline", "2025-01-22", "MLB Pipeline 2025 Tigers Top 30", "michael_massey", "michael_massey__sa3037259"),
    (3991642, "fangraphs", "2026-07-23", "2026tradedeadline", "michael_massey", "michael_massey__sa3037259"),
    (4330220, "fangraphs", "2026-08-02", "2026updated", "michael_massey", "michael_massey__sa3037259"),
    # carlos_rodriguez -> 677578 (the OF, b.2000-12-07), his existing key
    (2874985, "mlb_pipeline", "2018-01-22", "MLB Pipeline 2018 Brewers Top 30", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2866430, "fangraphs", "2018-08-01", "2018updated", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2875876, "mlb_pipeline", "2019-01-22", "MLB Pipeline 2019 Brewers Top 30", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2867433, "fangraphs", "2019-02-13", "2019report", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2868247, "fangraphs", "2019-07-31", "2019updated", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2876768, "mlb_pipeline", "2020-01-22", "MLB Pipeline 2020 Brewers Top 30", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2869533, "fangraphs", "2020-02-13", "2020report", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2870814, "fangraphs", "2020-08-01", "2020updated", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2227793, "mlb_pipeline", "2021-01-22", "MLB Pipeline 2021 Brewers Top 30", "carlos_rodriguez", "carlos_d_rodriguez"),
    (2111644, "mlb_pipeline", "2025-01-22", "MLB Pipeline 2025 Braves Top 30", "carlos_rodriguez", "carlos_d_rodriguez"),
]

#: Pipeline rows: (cache file, Person id) re-verified against the cached page
#: before the move, keyed by snapshot id.
PIPELINE_PROOF: dict[int, tuple[str, int]] = {
    2368176: ("mlb_pipeline_2021_org_whitesox.html", 679563),
    2368190: ("mlb_pipeline_2022_org_whitesox.html", 679563),
    2368223: ("mlb_pipeline_2023_org_whitesox.html", 679563),
    2368261: ("mlb_pipeline_2024_org_whitesox.html", 679563),
    2228965: ("mlb_pipeline_2023_org_twins.html", 800412),
    2229752: ("mlb_pipeline_2024_org_twins.html", 800412),
    4391482: ("mlb_pipeline_2026_international.html", 836624),
    4724622: ("mlb_pipeline_2026_org_brewers.html", 836624),
    2111395: ("mlb_pipeline_2025_org_tigers.html", 695602),
    2874985: ("mlb_pipeline_2018_org_brewers.html", 677578),
    2875876: ("mlb_pipeline_2019_org_brewers.html", 677578),
    2876768: ("mlb_pipeline_2020_org_brewers.html", 677578),
    2227793: ("mlb_pipeline_2021_org_brewers.html", 677578),
    2111644: ("mlb_pipeline_2025_org_braves.html", 677578),
}

#: auto_detect debut rows whose position/org came from a contaminated players
#: row: id -> (key, wrong (position, org), right (position, org)).
AUTO_DETECT_FIX: dict[int, tuple[str, tuple[str, str], tuple[str, str]]] = {
    5211184: ("jose_rodriguez", ("SS", "MIL"), ("RHP", "TOR")),
    2455118: ("michael_massey", ("RHP", "DET"), ("2B", "KCR")),
}

#: players rows: key -> (expected (position, org, is_pitcher, birth_date),
#: repaired (position, org, is_pitcher, birth_date)).
PLAYERS_FIX: dict[str, tuple[tuple, tuple]] = {
    "jose_rodriguez": (("SS", "MIL", 0, "2001-07-18"),
                       ("RHP", "TOR", 1, "2001-07-18")),
    "michael_massey": (("RHP", "DET", 1, "1998-03-22"),
                       ("2B", "KCR", 0, "1998-03-22")),
    "michael_massey__sa3037259": (("SIRP", "DET", 1, "1998-03-22"),
                                  ("SIRP", "DET", 1, "2003-04-05")),
    "michael_massey__noid": (("SIRP", "DET", 1, "1998-03-22"),
                             ("SIRP", "DET", 1, "2003-04-05")),
}

#: players rows created for the new split keys, every field published by MLB
#: (name and birth date from the Pipeline Person record, position and club
#: from the current StatsAPI roster in data/rosters_by_org.json).
PLAYERS_CREATE: dict[str, tuple[str, str, str, int, str]] = {
    "jose_rodriguez_679563": ("José Rodríguez", "SS", "PHI", 0, "2001-05-13"),
    "jose_rodriguez_800412": ("Jose Rodriguez", "OF", "MIN", 0, "2005-06-10"),
}

#: player_photos bindings to add: mlbam -> key. Refused if the id is bound.
BIND: dict[int, str] = {
    679563: "jose_rodriguez_679563",
    800412: "jose_rodriguez_800412",
    695602: "michael_massey__sa3037259",
}

#: .cache/mlbam_ids.json: key -> (expected current value, repaired value).
#: _MISSING means the key must be absent.
_MISSING = object()
CACHE_FIX: dict[str, tuple[object, int]] = {
    "jose_rodriguez_679563": (_MISSING, 679563),
    "jose_rodriguez_800412": (_MISSING, 800412),
    "michael_massey__sa3037259": (686681, 695602),
    "michael_massey__noid": (686681, 695602),
}

#: acquisitions bonus that belongs to another human: key -> (method, year,
#: team_name, wrong bonus, repaired bonus).
ACQ_FIX = {
    "jose_rodriguez": ("international_fa", 2019, "Los Angeles Dodgers",
                       1500000, None),
}

#: Rows written onto the DET RHP's fragment keys through the WRONG cached id
#: (686681, the KCR 2B): his draft, his transaction log and his roster status
#: (MLB debut 2022-07-15) made the A-ball RHP read as a debuted Royals draftee.
#: The 2B's own copies live on michael_massey and stay. Removed, guarded on
#: text only the 2B's rows carry; the next ingest refetches the RHP's own
#: rows through 695602. table -> (SQL guard column, substring that must match)
FOREIGN_ROWS: dict[str, tuple[str, str]] = {
    "acquisitions": ("team_name", "Kansas City Royals"),
    "player_transactions": ("payload_json", "Kansas City Royals signed 2B Michael Massey"),
    "roster_status": ("payload_json", '"mlb_debut_date": "2022-07-15"'),
}
FOREIGN_KEYS = ("michael_massey__sa3037259", "michael_massey__noid")

DERIVED_TABLES = ("metric_snapshots", "trade_value_history",
                  "grpo_score_history", "trades")


def _p(action: str, *detail) -> None:
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def _pipeline_person_ids(cache_file: str) -> dict[int, str]:
    """{Person id: name} for every ranked row of one cached Pipeline page."""
    import html
    import re
    path = HERE / ".cache" / cache_file
    if not path.exists():
        return {}
    text = html.unescape(path.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for m in re.finditer(r'"player":\{"__ref":"Person:(\d+)"\}', text):
        out[int(m.group(1))] = ""
    return out


def _backup_present(db_path: Path) -> Path | None:
    hits = sorted(h for h in db_path.parent.glob(f"{db_path.name}.{BACKUP_TAG}-*")
                  if not h.name.endswith(("-wal", "-shm", "-journal")))
    return hits[-1] if hits else None


def _make_backup(db_path: Path) -> Path:
    dest = db_path.with_name(f"{db_path.name}.{BACKUP_TAG}-{date.today().isoformat()}")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _repair_m02_11(con, cache, refused: list[str]) -> tuple[int, int]:
    """The 2026-09-30 row split (every row_split entry of the list).
    Returns (DB writes, id-cache edits); edits `cache` in place."""
    changes = 0

    # ------------------------------------------------------------------
    # 1. snapshot moves
    # ------------------------------------------------------------------
    print("\n-- snapshots --")
    page_cache: dict[str, dict[int, str]] = {}
    for sid, source, sdate, label, from_key, to_key in MOVES:
        row = con.execute("SELECT * FROM snapshots WHERE id = ?", (sid,)).fetchone()
        if row is None:
            # Either already merged into an existing row on to_key, or gone.
            done = con.execute(
                "SELECT id FROM snapshots WHERE source = ? AND interval_label = ? "
                "AND player_key = ?", (source, label, to_key)).fetchone()
            if done is not None:
                _p("ok", f"already repaired: {source} {label} lives on {to_key}")
            else:
                refused.append(f"snapshot id={sid} missing and not on {to_key}")
            continue
        if row["player_key"] == to_key:
            _p("ok", f"already on {to_key}: {source} {sdate} {label}")
            continue
        if (row["player_key"], row["source"], row["interval_label"]) != (from_key, source, label):
            refused.append(f"snapshot id={sid} drifted: {row['player_key']} "
                           f"{row['source']} {row['interval_label']} - NOT moved")
            continue
        if sid in PIPELINE_PROOF:
            page, person = PIPELINE_PROOF[sid]
            ids = page_cache.setdefault(page, _pipeline_person_ids(page))
            if person not in ids:
                refused.append(f"snapshot id={sid}: Person {person} not found in "
                               f".cache/{page} - NOT moved")
                continue
        clash = con.execute(
            "SELECT * FROM snapshots WHERE source = ? AND interval_label = ? "
            "AND player_key = ?", (source, label, to_key)).fetchone()
        if clash is None:
            _p("move", f"{source} {row['snapshot_date']} {label} "
               f"{row['position']}/{row['org']} FV {row['fv']}: {from_key} -> {to_key}")
            con.execute("UPDATE snapshots SET player_key = ? WHERE id = ? "
                        "AND player_key = ?", (to_key, sid, from_key))
            changes += 1
            continue
        # The same publication already sits on the right key under an older
        # date: apply the newer copy exactly as insert_snapshots' upsert does.
        if row["snapshot_date"] < clash["snapshot_date"]:
            refused.append(f"snapshot id={sid} is OLDER than the copy on {to_key} "
                           f"(id={clash['id']}) - NOT merged")
            continue
        _p("merge", f"{source} {label}: the {row['snapshot_date']} copy on {from_key} "
           f"(id={sid}) supersedes the {clash['snapshot_date']} copy on {to_key} "
           f"(id={clash['id']}); applied as the upsert would, bare copy removed")
        con.execute(
            "UPDATE snapshots SET snapshot_date = ?, player_name = ?, "
            "position = COALESCE(?, position), org = COALESCE(?, org), "
            "rank = ?, fv = ?, status = ?, "
            "tools_json = COALESCE(?, tools_json), fv_plus = ? WHERE id = ?",
            (row["snapshot_date"], row["player_name"], row["position"],
             row["org"], row["rank"], row["fv"], row["status"],
             row["tools_json"], row["fv_plus"], clash["id"]))
        con.execute("DELETE FROM snapshots WHERE id = ? AND player_key = ?",
                    (sid, from_key))
        changes += 2

    print("\n-- auto_detect debut rows --")
    for sid, (key, wrong, right) in AUTO_DETECT_FIX.items():
        row = con.execute("SELECT player_key, source, position, org FROM snapshots "
                          "WHERE id = ?", (sid,)).fetchone()
        if row is None or row["player_key"] != key or row["source"] != "auto_detect":
            refused.append(f"auto_detect id={sid} not found on {key}")
            continue
        cur = (row["position"], row["org"])
        if cur == right:
            _p("ok", f"already repaired: {key} debut row {right}")
        elif cur == wrong:
            _p("restore", f"{key} debut row {wrong} -> {right}")
            con.execute("UPDATE snapshots SET position = ?, org = ? WHERE id = ?",
                        (right[0], right[1], sid))
            changes += 1
        else:
            refused.append(f"auto_detect id={sid} reads {cur}, expected {wrong}")

    # ------------------------------------------------------------------
    # 2. players rows
    # ------------------------------------------------------------------
    print("\n-- players --")
    for key, (wrong, right) in PLAYERS_FIX.items():
        r = con.execute("SELECT position, org, is_pitcher, birth_date FROM players "
                        "WHERE player_key = ?", (key,)).fetchone()
        if r is None:
            refused.append(f"players[{key}] missing")
            continue
        cur = (r["position"], r["org"], r["is_pitcher"], r["birth_date"])
        if cur == right:
            _p("ok", f"already repaired: players[{key}] {right}")
        elif cur == wrong:
            _p("restore", f"players[{key}] {wrong} -> {right}")
            con.execute("UPDATE players SET position = ?, org = ?, is_pitcher = ?, "
                        "birth_date = ?, updated_at = datetime('now') "
                        "WHERE player_key = ?", (*right, key))
            changes += 1
        else:
            refused.append(f"players[{key}] reads {cur}, expected {wrong}")
    for key, (name, pos, org, is_p, dob) in PLAYERS_CREATE.items():
        if con.execute("SELECT 1 FROM players WHERE player_key = ?", (key,)).fetchone():
            _p("ok", f"already repaired: players[{key}] exists")
            continue
        _p("create", f"players[{key}]: {name} / {pos} / {org} / is_pitcher={is_p} / b.{dob}")
        con.execute("INSERT INTO players (player_key, player_name, position, org, "
                    "is_pitcher, birth_date) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, name, pos, org, is_p, dob))
        changes += 1

    # ------------------------------------------------------------------
    # 3. player_photos bindings
    # ------------------------------------------------------------------
    print("\n-- player_photos --")
    for mid, key in BIND.items():
        r = con.execute("SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                        (mid,)).fetchone()
        if r is not None and r["player_key"] == key:
            _p("ok", f"already bound: {mid} -> {key}")
        elif r is not None:
            refused.append(f"player_photos: {mid} is bound to {r['player_key']} - "
                           f"NOT re-pointed to {key}")
        elif con.execute("SELECT mlbam_id FROM player_photos WHERE player_key = ?",
                         (key,)).fetchone():
            refused.append(f"player_photos: {key} already carries another id")
        else:
            _p("bind", f"player_photos: {mid} -> {key}")
            con.execute("INSERT INTO player_photos (mlbam_id, headshot_ctx, player_key) "
                        "VALUES (?, 'milb', ?)", (mid, key))
            changes += 1

    # ------------------------------------------------------------------
    # 4. acquisitions bonus carried by the wrong human
    # ------------------------------------------------------------------
    print("\n-- acquisitions --")
    for key, (method, year, team, wrong, right) in ACQ_FIX.items():
        r = con.execute("SELECT method, year, team_name, bonus_usd FROM acquisitions "
                        "WHERE player_key = ?", (key,)).fetchone()
        if r is None:
            refused.append(f"acquisitions[{key}] missing")
            continue
        if (r["method"], r["year"], r["team_name"]) != (method, year, team):
            refused.append(f"acquisitions[{key}] is {tuple(r)}, expected "
                           f"{(method, year, team)}")
        elif r["bonus_usd"] == right:
            _p("ok", f"already repaired: acquisitions[{key}].bonus_usd {right}")
        elif r["bonus_usd"] == wrong:
            _p("restore", f"acquisitions[{key}].bonus_usd {wrong} -> {right}")
            con.execute("UPDATE acquisitions SET bonus_usd = ? WHERE player_key = ?",
                        (right, key))
            changes += 1
        else:
            refused.append(f"acquisitions[{key}].bonus_usd reads {r['bonus_usd']}")

    print("\n-- the 2B's rows on the DET RHP's fragment keys --")
    for key in FOREIGN_KEYS:
        for table, (col, needle) in FOREIGN_ROWS.items():
            rows = con.execute(f"SELECT rowid, {col} FROM {table} WHERE player_key = ?",
                               (key,)).fetchall()
            if not rows:
                _p("ok", f"already repaired: no {table} row on {key}")
                continue
            for r in rows:
                if needle in str(r[1]):
                    _p("remove", f"{table}[{key}]: the KCR 2B's row (686681), "
                       f"matched on {needle!r}")
                    con.execute(f"DELETE FROM {table} WHERE rowid = ? AND player_key = ?",
                                (r[0], key))
                    changes += 1
                else:
                    refused.append(f"{table}[{key}] does not carry {needle!r} - NOT removed")

    # ------------------------------------------------------------------
    # 5. derived history: disclose, do not move
    # ------------------------------------------------------------------
    print("\n-- derived history, REPORTED and left in place --")
    tables = _tables(con)
    for key in ("jose_rodriguez", "michael_massey", "carlos_rodriguez"):
        for t in DERIVED_TABLES:
            if t not in tables:
                continue
            extra = " AND source = 'inferred'" if t == "trades" else ""
            n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE player_key = ?{extra}",
                            (key,)).fetchone()[0]
            if n:
                _p("disclose", f"{t}[{key}]: {n} row(s) computed while merged")

    # ------------------------------------------------------------------
    # 6. the id cache (gitignored, derived; every edit value-guarded)
    # ------------------------------------------------------------------
    print("\n-- .cache/mlbam_ids.json --")
    cache_changes = 0
    if cache is not None:
        for key, (expect, value) in CACHE_FIX.items():
            cur = cache.get(key, _MISSING)
            if cur == value:
                _p("ok", f"already repaired: cache[{key}] = {value}")
            elif cur is expect or cur == expect:
                _p("repoint", f"cache[{key}]: "
                   f"{'absent' if cur is _MISSING else cur} -> {value}")
                cache[key] = value
                cache_changes += 1
            else:
                refused.append(f"cache[{key}] reads {cur}, expected "
                               f"{'absent' if expect is _MISSING else expect}")
    else:
        _p("skip", "id cache not present")
    return changes, cache_changes


def _repair_rebind(con, cache, e: dict, refused: list[str]) -> tuple[int, int]:
    """One `rebind` entry of the list: board_key served wrong_id. Re-bind it
    to right_id and remove what wrong_id fetched. Every write is guarded by
    the value it expects; anything else is refused and left alone.
    Returns (DB writes, id-cache edits); edits `cache` in place."""
    board, wrong, right = e["board_key"], e["wrong_id"], e["right_id"]
    keys = (board, *e["fragment_keys"])
    tables = _tables(con)
    changes = 0
    print(f"\n-- rebind {e['repair_id']}: {board} {wrong} -> {right} --")

    # The forward pin must be in the code before the DB is touched: without
    # it the next resolution could bind wrong_id back.
    try:
        from scrapers import split_key_for_mlbam
        for k in keys:
            got = split_key_for_mlbam(k, wrong)
            if got != e["split_key"]:
                refused.append(f"{e['repair_id']}: scrapers._SPLIT_KEYS lacks "
                               f"({k}, {wrong}) -> {e['split_key']} (reads {got})")
    except Exception as exc:                                  # noqa: BLE001
        refused.append(f"{e['repair_id']}: scrapers pin check failed: {exc}")

    # player_photos: unbind the wrong id, bind the right one.
    r = con.execute("SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                    (wrong,)).fetchone()
    if r is not None and r["player_key"] in keys:
        _p("unbind", f"player_photos: {wrong} off {r['player_key']} "
           "(headshot context kept)")
        con.execute("UPDATE player_photos SET player_key = NULL, "
                    "checked_at = datetime('now') WHERE mlbam_id = ? "
                    "AND player_key = ?", (wrong, r["player_key"]))
        changes += 1
    else:
        _p("ok", f"already repaired: {wrong} not bound to {', '.join(keys)}")
    r = con.execute("SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                    (right,)).fetchone()
    other = con.execute("SELECT mlbam_id FROM player_photos WHERE player_key = ? "
                        "AND mlbam_id <> ?", (board, right)).fetchone()
    if r is not None and r["player_key"] == board:
        _p("ok", f"already bound: {right} -> {board}")
    elif r is not None and r["player_key"]:
        refused.append(f"player_photos: {right} is bound to {r['player_key']} - "
                       f"NOT re-pointed to {board}")
    elif other is not None:
        refused.append(f"player_photos: {board} still carries id {other[0]}")
    elif r is not None:
        _p("bind", f"player_photos: {right} (unowned row) -> {board}")
        con.execute("UPDATE player_photos SET player_key = ? WHERE mlbam_id = ? "
                    "AND player_key IS NULL", (board, right))
        changes += 1
    else:
        _p("bind", f"player_photos: {right} -> {board}")
        con.execute("INSERT INTO player_photos (mlbam_id, headshot_ctx, player_key) "
                    "VALUES (?, 'milb', ?)", (right, board))
        changes += 1

    # players.birth_date: the wrong human's date -> the right human's.
    bd_wrong, bd_right = e["birth_date"]
    for k in keys:
        r = con.execute("SELECT birth_date FROM players WHERE player_key = ?",
                        (k,)).fetchone()
        if r is None:
            _p("skip", f"players[{k}] absent")
        elif r["birth_date"] == bd_right:
            _p("ok", f"already repaired: players[{k}].birth_date {bd_right}")
        elif r["birth_date"] in (bd_wrong, None, ""):
            _p("restore", f"players[{k}].birth_date {r['birth_date']} -> {bd_right}")
            con.execute("UPDATE players SET birth_date = ?, updated_at = datetime('now') "
                        "WHERE player_key = ? AND (birth_date IS ? OR birth_date = ?)",
                        (bd_right, k, r["birth_date"], r["birth_date"] or ""))
            changes += 1
        else:
            refused.append(f"players[{k}].birth_date reads {r['birth_date']}, "
                           f"expected {bd_wrong}")

    # Rows fetched through the wrong id. A row without the marker is the
    # key's own and stays.
    for table, (col, needle) in e["foreign_rows"].items():
        if table not in tables:
            _p("skip", f"no {table} table")
            continue
        for k in keys:
            for row in con.execute(f"SELECT rowid, {col} FROM {table} "
                                   "WHERE player_key = ?", (k,)).fetchall():
                if needle in str(row[1]):
                    _p("remove", f"{table}[{k}]: fetched through {wrong}, "
                       f"matched on {needle!r}")
                    con.execute(f"DELETE FROM {table} WHERE rowid = ? "
                                "AND player_key = ?", (row[0], k))
                    changes += 1
                else:
                    _p("keep", f"{table}[{k}]: no {needle!r}, the key's own row")

    for t in DERIVED_TABLES:
        if t not in tables:
            continue
        n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE player_key = ?",
                        (board,)).fetchone()[0]
        if n:
            _p("disclose", f"{t}[{board}]: {n} row(s) computed while bound to {wrong}")

    cache_changes = 0
    if cache is not None:
        for k in keys:
            cur = cache.get(k, _MISSING)
            if cur == right:
                _p("ok", f"already repaired: cache[{k}] = {right}")
            elif cur is _MISSING and k != board:
                _p("skip", f"cache[{k}] absent")
            elif cur is _MISSING or cur is None or cur == wrong:
                _p("repoint", f"cache[{k}]: "
                   f"{'absent' if cur is _MISSING else cur} -> {right}")
                cache[k] = right
                cache_changes += 1
            else:
                refused.append(f"cache[{k}] reads {cur}, expected {wrong} or null")
    return changes, cache_changes


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------

def entry_fingerprint(e: dict) -> str:
    """Content hash of one list entry; a receipt names the entry it applied."""
    blob = json.dumps(e, sort_keys=True, default=list).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def load_receipts(receipt_path: Path = RECEIPTS) -> list[dict]:
    if not receipt_path.exists():
        return []
    out = []
    for line in receipt_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def receipted_ids(db_path: Path, receipt_path: Path = RECEIPTS) -> set[str]:
    db = str(Path(db_path).resolve())
    return {r["repair_id"] for r in load_receipts(receipt_path)
            if r.get("db") == db and r.get("repair_id")}


def _append_receipts(rows: list[dict], receipt_path: Path) -> None:
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.open("a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def repair(db_path: Path, apply: bool, cache_path: Path = ID_CACHE,
           only: set[str] | None = None, entries=None,
           receipt_path: Path = RECEIPTS) -> int:
    """Apply the selected entries of the identity-repair list. Dry run unless
    `apply`. On apply, one receipt row per selected entry that refused
    nothing. Returns 0 clean, 1 something refused, 2 fatal."""
    return repair_result(db_path, apply, cache_path, only, entries,
                         receipt_path)["rc"]


def repair_result(db_path: Path, apply: bool, cache_path: Path = ID_CACHE,
                  only: set[str] | None = None, entries=None,
                  receipt_path: Path = RECEIPTS) -> dict:
    """repair() with the counts: {rc, db_writes, cache_edits, refused,
    receipts}."""
    out = {"rc": 2, "db_writes": 0, "cache_edits": 0, "refused": [],
           "receipts": []}
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_identity_split_2026_09_30 [{mode}] db={db_path} ===")
    entries = identity_repairs.REPAIRS if entries is None else tuple(entries)
    errs = identity_repairs.schema_errors(entries)
    if errs:
        print("FATAL: the identity-repair list breaks its schema:")
        for m in errs:
            print(f"  {m}")
        return out
    if only:
        unknown = set(only) - {e["repair_id"] for e in entries}
        if unknown:
            print(f"FATAL: unknown repair id(s): {sorted(unknown)}")
            return out
        entries = tuple(e for e in entries if e["repair_id"] in only)
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return out

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cache = None
    if cache_path is not None and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    # (entries covered, writes, cache edits, refused) per unit of work
    units: list[tuple[tuple[dict, ...], int, int, list[str]]] = []
    splits = tuple(e for e in entries if e["kind"] == "row_split")
    if splits:
        ref: list[str] = []
        ch, cc = _repair_m02_11(con, cache, ref)
        units.append((splits, ch, cc, ref))
    for e in entries:
        if e["kind"] == "rebind":
            ref = []
            ch, cc = _repair_rebind(con, cache, e, ref)
            units.append(((e,), ch, cc, ref))

    changes = sum(u[1] for u in units)
    cache_changes = sum(u[2] for u in units)
    refused = [m for u in units for m in u[3]]
    if refused:
        print("\n-- REFUSED (listed, NOT touched) --")
        for msg in refused:
            _p("refused", msg)

    if apply:
        con.commit()
        if cache is not None and cache_changes:
            # The exact format stats._save_id_cache writes.
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))
        bak = _backup_present(db_path)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for covered, ch, cc, ref in units:
            if ref:
                continue
            for e in covered:
                rows.append({
                    "repair_id": e["repair_id"], "kind": e["kind"],
                    "board_key": e["board_key"], "wrong_id": e["wrong_id"],
                    "right_id": e["right_id"], "entry": entry_fingerprint(e),
                    "db": str(Path(db_path).resolve()),
                    "backup": bak.name if bak else None,
                    "applied_at": now,
                    "outcome": "applied" if (ch or cc) else "already_repaired",
                    "db_writes": ch, "cache_edits": cc,
                })
        if rows and receipt_path is not None:
            _append_receipts(rows, receipt_path)
            out["receipts"] = rows
        print(f"\n=== APPLIED: {changes} DB write(s), {cache_changes} cache "
              f"edit(s); {len(rows)} receipt row(s) ===")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {changes} DB write(s), {cache_changes} cache "
              "edit(s) planned; re-run with --apply ===")
    con.close()
    out.update(rc=1 if refused else 0, db_writes=changes,
               cache_edits=cache_changes, refused=refused)
    return out


def run_step(db_path: Path = DEFAULT_DB, cache_path: Path = ID_CACHE,
             receipt_path: Path = RECEIPTS, make_backup: bool = True) -> dict:
    """The receipt-guarded pipeline step (fWAR epoch step A wires this).

    Repairs with a receipt for this DB are skipped. The rest are dry-run
    first; when the dry run plans no write they are receipted as already
    repaired, otherwise a dated backup is taken (once) and they are applied.
    A repair that refuses anything gets no receipt and is retried next run.
    Never raises on a refusal; returns a summary for the step's heartbeat."""
    done = receipted_ids(db_path, receipt_path)
    pending = {e["repair_id"] for e in identity_repairs.REPAIRS} - done
    summary = {"receipted": sorted(done), "pending": sorted(pending),
               "rc": 0, "backup": None}
    if not pending:
        return summary
    dry = repair_result(db_path, apply=False, cache_path=cache_path,
                        only=pending, receipt_path=None)
    if dry["rc"] == 2:
        summary["rc"] = 2
        return summary
    planned = bool(dry["db_writes"] or dry["cache_edits"])
    if planned:
        if make_backup:
            summary["backup"] = _make_backup(db_path).name
        elif _backup_present(db_path) is None:
            summary["rc"] = 2
            summary["refused"] = ["no backup beside the DB and make_backup=False"]
            return summary
    res = repair_result(db_path, apply=True, cache_path=cache_path,
                        only=pending, receipt_path=receipt_path)
    summary.update(rc=res["rc"], db_writes=res["db_writes"],
                   cache_edits=res["cache_edits"], refused=res["refused"])
    summary["receipted"] = sorted(receipted_ids(db_path, receipt_path))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Apply the identity-repair list (identity_repairs.py) to "
                    "prospects.db: the M02-11 split and every rebind.")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--make-backup", action="store_true",
                    help="take a dated prospects.db.bak-identsplit-<date> copy first")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    ap.add_argument("--only", action="append", default=None, metavar="REPAIR_ID",
                    help="limit to these repair ids (repeatable)")
    ap.add_argument("--step", action="store_true",
                    help="run the receipt-guarded step (skips receipted repairs)")
    args = ap.parse_args()
    if args.step:
        out = run_step(args.db)
        print(json.dumps(out, indent=1))
        return int(out["rc"])
    if args.apply:
        if args.make_backup:
            print(f"backup: {_make_backup(args.db)}")
        bak = _backup_present(args.db)
        if bak is None:
            print(f"FATAL: no {args.db.name}.{BACKUP_TAG}-* backup beside the DB; "
                  "re-run with --make-backup")
            return 2
        print(f"backup present: {bak.name}")
    return repair(args.db, apply=args.apply,
                  only=set(args.only) if args.only else None)


if __name__ == "__main__":
    sys.exit(main())
