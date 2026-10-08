# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The writers' award results from MLB's StatsAPI (AWARDS_4_WINNERS_INGEST; AWARDS_PLAN
4.1 'Files', 4.11 'Past seasons and the writers', 5.6 'Rule and vote'; LANE_DATA 5.2
'The winners' source'; owner answer AW-Q4).

THE SOURCE. https://statsapi.mlb.com/api/v1/awards/<id>/recipients, the source
awards_statsapi audited in data/sources/registry.yaml (public JSON, legal risk low,
MLBAM join), for the eight award ids ALMVP, NLMVP, ALCY, NLCY, ALROY, NLROY, ALMOY and
NLMOY (ids confirmed in data/sources/samples/awards_list_04.json; field names in
data/sources/samples/awards_roy_recipients_05.json). Each call returns every season of
one award, so a backfill is eight calls: one at a time, a pause between them, a
descriptive User-Agent. Baseball-Reference and FanGraphs award pages are never read.

WHAT IT WRITES. The tracked, unpublished data/_labs/awards/award_winners.json
(data/_labs/ ships in neither deploy consumer):

  {"schema", "produced_by", "fetched_at", "source", "copyright" (the response's own
   string, verbatim), "award_ids", "fetch_log": [{"fetched_at", "seasons", "calls"}],
   "seasons": {"<S>": {"<award id>": {"person_id", "name", "team_id", "team_code",
                                      "date", "votes" (only where the feed has it)}}}}

team_code goes through trades.canonical_org_from_id. Manager of the Year recipients are
people: their person ids are kept as given, and awards_export compares the Manager award
on the club (team_id).

WRITE-ONCE. A season already in the file is closed: asking for it again is refused
before any call is made, and nothing is rewritten. A requested season that lacks any of
the eight awards in the responses is refused too (nothing partial is written), which is
how a run before the November announcements stops. The backfill is 2011 to 2025
(AWARDS_4); AWARDS_12 adds 2026 with --first 2026 --last 2026 after all eight
announcements.

Run: python tools/award_winners_ingest.py [--first 2011] [--last 2025]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = 1
PRODUCED_BY = "tools/award_winners_ingest.py"
OUT = ROOT / "data" / "_labs" / "awards" / "award_winners.json"
ENDPOINT = "https://statsapi.mlb.com/api/v1/awards/{award_id}/recipients"
USER_AGENT = "eephus.io award winners ingest (one call per award, tools/award_winners_ingest.py)"
#: StatsAPI award id -> (the awards module's award key, league). The exporter reads
#: the same table (awards_export.STATSAPI_AWARD_IDS).
AWARD_IDS = {
    "ALMVP": ("MVP", "AL"), "NLMVP": ("MVP", "NL"),
    "ALCY": ("CY", "AL"), "NLCY": ("CY", "NL"),
    "ALROY": ("ROY", "AL"), "NLROY": ("ROY", "NL"),
    "ALMOY": ("MOY", "AL"), "NLMOY": ("MOY", "NL"),
}
FIRST_SEASON = 2011
LAST_SEASON = 2025
PAUSE_S = 2.0
TIMEOUT_S = 30
SOURCE = {
    "id": "awards_statsapi",
    "name": "MLB StatsAPI award recipients",
    "endpoint": ENDPOINT,
    "registry": "data/sources/registry.yaml awards_statsapi",
}


class IngestRefusal(RuntimeError):
    """The ingest declines; the file on disk stands unchanged."""


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def team_code(team_id) -> str | None:
    import trades
    return trades.canonical_org_from_id(team_id)


def parse_recipients(award_id: str, doc: dict, first: int, last: int) -> dict:
    """{season: record} for one award's recipients response, seasons first..last.

    A record is {person_id, name, team_id, team_code, date} plus votes where the feed
    carries it. Two recipients in one season (a shared award) are refused: the
    awards page compares one writers' 1st per award and league."""
    out: dict = {}
    for rec in doc.get("awards") or []:
        if str(rec.get("id")) != award_id:
            raise IngestRefusal(f"{award_id}: a recipient row carries award id {rec.get('id')!r}")
        season = _int(rec.get("season"))
        if season is None or not (first <= season <= last):
            continue
        player = rec.get("player") or {}
        team = rec.get("team") or {}
        pid = _int(player.get("id"))
        name = player.get("nameFirstLast") or player.get("fullName")
        if pid is None or not name:
            raise IngestRefusal(f"{award_id} {season}: a recipient has no person id or name")
        if season in out:
            raise IngestRefusal(f"{award_id} {season}: more than one recipient")
        tid = _int(team.get("id"))
        row = {"person_id": pid, "name": str(name), "team_id": tid,
               "team_code": team_code(tid) if tid is not None else None,
               "date": rec.get("date")}
        if rec.get("votes") is not None:
            row["votes"] = rec.get("votes")
        out[season] = row
    return out


def build_seasons(responses: dict, first: int, last: int) -> dict:
    """{"<S>": {award id: record}} for first..last from {award id: response}; every
    season must carry all eight awards, or nothing is returned (refusal)."""
    by_award = {aid: parse_recipients(aid, responses[aid], first, last) for aid in AWARD_IDS}
    seasons = {}
    missing = []
    for S in range(first, last + 1):
        have = {aid: by_award[aid][S] for aid in AWARD_IDS if S in by_award[aid]}
        if len(have) != len(AWARD_IDS):
            missing.append(f"{S} lacks {', '.join(a for a in AWARD_IDS if a not in have)}")
            continue
        seasons[str(S)] = have
    if missing:
        raise IngestRefusal("incomplete seasons, nothing written: " + "; ".join(missing))
    return seasons


def copyright_of(responses: dict) -> str | None:
    vals = {str(r.get("copyright")) for r in responses.values() if r.get("copyright")}
    if len(vals) > 1:
        raise IngestRefusal("the eight responses carry different copyright strings")
    return next(iter(vals), None)


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def _fetch_one(award_id: str) -> dict:
    import requests
    r = requests.get(ENDPOINT.format(award_id=award_id), headers={"User-Agent": USER_AGENT},
                     timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def ingest(first: int = FIRST_SEASON, last: int = LAST_SEASON, *, out: Path = OUT,
           fetch=_fetch_one, pause: float = PAUSE_S, now=None, log=print) -> dict:
    """Fetch the eight awards once each and add seasons first..last to the file.
    Refuses, before any call, when a requested season is already in the file."""
    if first > last:
        raise IngestRefusal(f"first season {first} is after last season {last}")
    out = Path(out)
    existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    closed = sorted(int(s) for s in ((existing or {}).get("seasons") or {}))
    asked = [S for S in range(first, last + 1) if S in closed]
    if asked:
        raise IngestRefusal(f"seasons {asked[0]} to {asked[-1]} are closed in {out.name}; "
                            "a closed season is never refetched or rewritten")
    responses = {}
    for i, aid in enumerate(AWARD_IDS):
        if i and pause:
            time.sleep(pause)
        responses[aid] = fetch(aid)
        log(f"  {aid}: {len(responses[aid].get('awards') or [])} recipient rows")
    seasons = build_seasons(responses, first, last)
    cr = copyright_of(responses)
    stamp = now or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    doc = existing or {"schema": SCHEMA, "produced_by": PRODUCED_BY, "fetched_at": None,
                       "source": SOURCE, "copyright": None, "award_ids": list(AWARD_IDS),
                       "fetch_log": [], "seasons": {}}
    doc["fetched_at"] = stamp
    if cr:
        doc["copyright"] = cr
    doc.setdefault("fetch_log", []).append(
        {"fetched_at": stamp, "seasons": [first, last], "calls": len(responses)})
    merged = dict(doc.get("seasons") or {})
    merged.update(seasons)
    doc["seasons"] = {k: merged[k] for k in sorted(merged, key=int)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(doc), encoding="utf-8", newline="\n")
    log(f"  wrote {len(seasons)} seasons ({first} to {last}) x {len(AWARD_IDS)} awards to {out}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch the writers' award results from StatsAPI.")
    ap.add_argument("--first", type=int, default=FIRST_SEASON)
    ap.add_argument("--last", type=int, default=LAST_SEASON)
    a = ap.parse_args(argv)
    try:
        ingest(a.first, a.last)
    except IngestRefusal as e:
        print(f"REFUSED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
