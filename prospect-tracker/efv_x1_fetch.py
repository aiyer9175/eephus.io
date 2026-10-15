# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The season lines EFV_X1_MLE_TRANSLATION reads (efv_x1_translate.py), fetched once from
the public MLB StatsAPI into .cache/EFV_X1_MLE_TRANSLATION/ and never anywhere else.

Why a second cache: milb_history's lean rows drop the team, the pitcher's home runs,
hit batsmen and outs, and the ground and air outs, which the translation needs (HR/9,
GB%, the team's environment). Each file holds one (kind, group, sport, season):

    players_{group}_{sport}_{season}.json   one row per player and sport-season (the
                                            feed aggregates a multi-team player into one
                                            row with num_teams above 1 and no team)
    teams_{group}_{sport}_{season}.json     one row per team (its batters' line for
                                            hitting, its pitchers' allowed line for
                                            pitching)

Polite: one request at a time, PAUSE_S seconds apart, no login, no paid source. A past
season, once cached, is never fetched again. Nothing served reads this module.

Run:  python efv_x1_fetch.py            (fetch whatever is missing; prints counts)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import milb_history as mh

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "EFV_X1_MLE_TRANSLATION"
BASE = "https://statsapi.mlb.com/api/v1"
UA = {"User-Agent": "Mozilla/5.0 (PROSPX research; polite, cached)"}
PAUSE_S = 0.6
SPORTS: tuple[int, ...] = (1,) + tuple(mh.MINOR_SPORTS)
#: 2020 had no minor league season; MLB 2020 links nothing and is skipped too.
SEASONS: tuple[int, ...] = tuple(s for s in range(2005, 2027) if s != 2020)
GROUPS = ("hitting", "pitching")

HIT_FIELDS = {"pa": "plateAppearances", "ab": "atBats", "h": "hits", "doubles": "doubles",
              "triples": "triples", "hr": "homeRuns", "bb": "baseOnBalls",
              "ibb": "intentionalWalks", "hbp": "hitByPitch", "sf": "sacFlies",
              "so": "strikeOuts", "go": "groundOuts", "ao": "airOuts", "g": "gamesPlayed"}
PIT_FIELDS = {"bf": "battersFaced", "outs": "outs", "ip": "inningsPitched", "so": "strikeOuts",
              "bb": "baseOnBalls", "ibb": "intentionalWalks", "hbp": "hitBatsmen",
              "hr": "homeRuns", "h": "hits", "go": "groundOuts", "ao": "airOuts",
              "g": "gamesPlayed", "gs": "gamesStarted", "sf": "sacFlies", "ab": "atBats",
              "doubles": "doubles", "triples": "triples"}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _level(sport: int, league: str) -> str:
    return mh._level16(league) if sport == 16 else mh.SPORT_LEVEL.get(sport, "?")


def _lean(split: dict, sport: int, season: int, group: str, kind: str) -> dict:
    st = split.get("stat") or {}
    league = (split.get("league") or {}).get("name") or ""
    team = split.get("team") or {}
    row = {"season": int(season), "sport": int(sport), "level": _level(sport, league),
           "league": league, "team_id": team.get("id"),
           "team": team.get("name")}
    if kind == "players":
        row.update({"mlbam": (split.get("player") or {}).get("id"),
                    "num_teams": split.get("numTeams"), "age": st.get("age")})
    for k, src in (HIT_FIELDS if group == "hitting" else PIT_FIELDS).items():
        row[k] = st.get(src)
    return row


def path_for(kind: str, group: str, sport: int, season: int) -> Path:
    return CACHE_DIR / f"{kind}_{group}_{int(sport)}_{int(season)}.json"


def fetch_players(sport: int, season: int, group: str) -> list[dict]:
    out, offset = [], 0
    while True:
        url = (f"{BASE}/stats?stats=season&group={group}&season={season}"
               f"&sportIds={sport}&playerPool=ALL&limit=2000&offset={offset}")
        d = _get(url)
        time.sleep(PAUSE_S)
        blk = (d.get("stats") or [{}])[0]
        page = blk.get("splits") or []
        out.extend(_lean(s, sport, season, group, "players") for s in page)
        total = blk.get("totalSplits") or len(out)
        offset += len(page)
        if not page or offset >= total:
            break
    return out


def fetch_teams(sport: int, season: int, group: str) -> list[dict]:
    d = _get(f"{BASE}/teams/stats?stats=season&group={group}&season={season}"
             f"&sportIds={sport}")
    time.sleep(PAUSE_S)
    out = []
    for blk in d.get("stats") or []:
        for s in blk.get("splits") or []:
            row = _lean(s, sport, season, group, "teams")
            out.append(row)
    return out


def load(kind: str, group: str, sport: int, season: int) -> list[dict]:
    """Cached rows, or [] when the file is absent (offline-safe; never fetches)."""
    p = path_for(kind, group, sport, season)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def fetch_all(*, seasons=SEASONS, sports=SPORTS, log=print) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict = {}
    for season in seasons:
        for sport in sports:
            for group in GROUPS:
                for kind, fn in (("players", fetch_players), ("teams", fetch_teams)):
                    p = path_for(kind, group, sport, season)
                    if p.exists():
                        counts[p.name] = len(json.loads(p.read_text(encoding="utf-8")))
                        continue
                    for attempt in range(3):
                        try:
                            rows = fn(sport, season, group)
                            break
                        except Exception as e:  # noqa: BLE001
                            log(f"  retry {attempt + 1} {p.name}: {e}")
                            time.sleep(5.0 * (attempt + 1))
                    else:
                        log(f"  FAILED {p.name}")
                        continue
                    tmp = p.with_name(p.name + ".tmp")
                    tmp.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
                    tmp.replace(p)
                    counts[p.name] = len(rows)
                    log(f"  {p.name}: {len(rows)} rows")
    return counts


if __name__ == "__main__":
    c = fetch_all(log=lambda m: print(m, flush=True))
    print(f"{len(c)} files, {sum(c.values())} rows", flush=True)
    sys.exit(0)
