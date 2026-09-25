# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Re-date placeholder debut days from the MLB StatsAPI people record (DS-12).

THE DEFECT (docs/efv-v2/DRIVER_SYSTEM_V2.md, bug B7). When the PlayerIndex sweep has no
mlbDebutDate for a player, stats.derive_roster_status falls back to his first contract
selection. For a November Rule 5 protection add that is not a game date, so
storage._derived_graduation_date rolls it forward to a synthesized {first MLB season}-07-01
(_safe_in_year_placeholder), and the eFV training matrix reads that day as the debut: the
consensus input cutoff and the MiLB feature cutoff both sit at July 1 whatever the real
debut day was. 131 debuted matrix rows carried one on 2026-09-25.

WHAT THIS DOES. Finds every roster_status row storage would roll forward (offseason
selection date, first MLB season later), asks /people/{id} for mlbDebutDate, and keeps
the answer only when its YEAR equals the first MLB season on file (an id bound to the
wrong man fails that check and stays unresolved). Writes data/debut_redates.json, which
efv_dataset.build_matrix applies until the next full export writes the real day into
debuts.json, and with --db also writes the date into the local roster_status table.
run_monthly step 3f now makes the same /people call for these rows, so the next
pipeline run fixes the source.

Never computes a score. The label is unaffected: the debut YEAR agrees with the first
eWAR season on every debuted matrix row, only the day was synthetic.

Run:  python tools/redate_placeholder_debuts.py [--db] [--offline]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage  # noqa: E402

OUT_PATH = ROOT / "data" / "debut_redates.json"
PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people/{}"
BASIS = "rule5_rollforward_placeholder"
OFFSEASON_MONTHS = ("11", "12")


def placeholder_day(first_season: int, today: date | None = None) -> str:
    """The day storage._safe_in_year_placeholder writes for a prior season."""
    today = today or date.today()
    mid = f"{first_season}-07-01"
    return mid if first_season != today.year or mid <= today.isoformat() else today.isoformat()


def candidates(roster_status: dict, debuts: list[dict], durable_ids: dict) -> list[dict]:
    """Rows storage rolls forward: an offseason date with a later first MLB season."""
    ids = {r.get("player_key"): r.get("mlbam_id") for r in debuts if r.get("mlbam_id")}
    out = []
    for pk, rs in sorted(roster_status.items()):
        d = rs.get("mlb_debut_date") or ""
        seasons = [int(s) for s in (rs.get("mlb_seasons") or []) if s]
        if len(d) < 10 or d[5:7] not in OFFSEASON_MONTHS or not seasons:
            continue
        first = min(seasons)
        if first <= int(d[:4]):
            continue
        out.append({"player_key": pk, "mlbam_id": ids.get(pk) or durable_ids.get(pk),
                    "roster_status_date": d, "first_mlb_season": first,
                    "placeholder_date": placeholder_day(first)})
    return out


def _fetch(mid: int) -> tuple[int, dict | None]:
    import requests
    try:
        r = requests.get(PEOPLE_URL.format(int(mid)), timeout=20)
        r.raise_for_status()
        people = (r.json() or {}).get("people") or []
    except Exception:                                         # noqa: BLE001
        return mid, None
    return mid, (people[0] if people else None)


def resolve(cands: list[dict], people: dict[int, dict | None]) -> dict:
    rows = {}
    for c in cands:
        rec = dict(c, placeholder_basis=BASIS, debut_date=None)
        mid = c.get("mlbam_id")
        person = people.get(int(mid)) if mid else None
        if not mid:
            rec["status"] = "unresolved: no mlbam id"
        elif person is None:
            rec["status"] = "unresolved: people record unavailable"
        elif not person.get("mlbDebutDate"):
            rec["status"] = "unresolved: people record has no mlbDebutDate"
        elif int(person["mlbDebutDate"][:4]) != c["first_mlb_season"]:
            rec["status"] = (f"unresolved: mlbDebutDate {person['mlbDebutDate']} is not in "
                             f"the first MLB season on file ({c['first_mlb_season']})")
        else:
            rec["debut_date"] = person["mlbDebutDate"]
            rec["status"] = "redated"
        if person is not None:
            rec["people_full_name"] = person.get("fullName")
        rows[c["player_key"]] = rec
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true",
                    help="also write the re-dated day into the local roster_status table")
    ap.add_argument("--offline", action="store_true",
                    help="reuse the people answers already in data/debut_redates.json")
    args = ap.parse_args(argv)
    rs = storage.load_roster_status()
    debuts = json.loads((ROOT / "data" / "debuts.json").read_text(encoding="utf-8"))
    cands = candidates(rs, debuts, storage._durable_mlbam_by_key())
    people: dict[int, dict | None] = {}
    if args.offline and OUT_PATH.exists():
        prev = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("rows") or {}
        for r in prev.values():
            if r.get("mlbam_id"):
                people[int(r["mlbam_id"])] = ({"mlbDebutDate": r.get("debut_date"),
                                               "fullName": r.get("people_full_name")}
                                              if r.get("people_full_name") else None)
    else:
        mids = sorted({int(c["mlbam_id"]) for c in cands if c.get("mlbam_id")})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for mid, person in ex.map(_fetch, mids):
                people[mid] = person
    rows = resolve(cands, people)
    n_ok = sum(1 for r in rows.values() if r["status"] == "redated")
    doc = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "MLB StatsAPI /people/{id} mlbDebutDate",
        "rule": ("a roster_status debut date in November or December whose first MLB "
                 "season is later is a 40-man selection, not a game date; storage rolls it "
                 "forward to a placeholder. It is re-dated only when the people record's "
                 "mlbDebutDate falls in the first MLB season on file."),
        "consumers": ["efv_dataset.build_matrix (until debuts.json carries the real day)"],
        "regen_cmd": "python tools/redate_placeholder_debuts.py --db",
        "n_candidates": len(rows), "n_redated": n_ok, "n_unresolved": len(rows) - n_ok,
        "rows": rows,
    }
    tmp = OUT_PATH.with_name(OUT_PATH.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    storage._atomic_replace(tmp, OUT_PATH)
    if args.db:
        upd = {}
        for pk, r in rows.items():
            if r["status"] != "redated" or pk not in rs:
                continue
            rec = dict(rs[pk])
            rec["mlb_debut_date"] = r["debut_date"]
            rec["mlb_debut_date_source"] = "api_people"
            upd[pk] = rec
        n_db = storage.upsert_roster_status(upd)
        print(f"roster_status rows re-dated in the local DB: {n_db}")
    print(f"{len(rows)} placeholder candidates, {n_ok} re-dated, "
          f"{len(rows) - n_ok} unresolved -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
