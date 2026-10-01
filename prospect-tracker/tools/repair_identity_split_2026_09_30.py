# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_identity_split_2026_09_30.py - split the three merged debuted PROSPX
identities the final-pass census found (M02-11, owner answer 2026-09-25 batch 4):

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
    python tools/repair_identity_split_2026_09_30.py            # dry run
    python tools/repair_identity_split_2026_09_30.py --apply    # write
    python tools/repair_identity_split_2026_09_30.py --db PATH  # other DB

--apply refuses to run unless a dated backup prospects.db.bak-identsplit-*
sits beside the DB (pass --make-backup to take one first).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DEFAULT_DB = HERE / "prospects.db"
ID_CACHE = HERE / ".cache" / "mlbam_ids.json"
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


def repair(db_path: Path, apply: bool, cache_path: Path = ID_CACHE) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_identity_split_2026_09_30 [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = 0
    refused: list[str] = []

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
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
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
    cache = None
    cache_changes = 0
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
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
        _p("skip", f"{cache_path} not present")

    if refused:
        print("\n-- REFUSED (listed, NOT touched) --")
        for msg in refused:
            _p("refused", msg)

    if apply:
        con.commit()
        if cache is not None and cache_changes:
            # The exact format stats._save_id_cache writes.
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))
        print(f"\n=== APPLIED: {changes} DB write(s), {cache_changes} cache "
              "edit(s) ===")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {changes} DB write(s), {cache_changes} cache "
              "edit(s) planned; re-run with --apply ===")
    con.close()
    return 1 if refused else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Split the jose_rodriguez, michael_massey and "
                    "carlos_rodriguez merged identities (census M02-11).")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--make-backup", action="store_true",
                    help="take a dated prospects.db.bak-identsplit-<date> copy first")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    args = ap.parse_args()
    if args.apply:
        if args.make_backup:
            print(f"backup: {_make_backup(args.db)}")
        bak = _backup_present(args.db)
        if bak is None:
            print(f"FATAL: no {args.db.name}.{BACKUP_TAG}-* backup beside the DB; "
                  "re-run with --make-backup")
            return 2
        print(f"backup present: {bak.name}")
    return repair(args.db, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
