# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""bracket_sim.py - the postseason bracket-state simulator (method bracket_v1).

REGISTERED BEFORE ANY NUMBER EXISTED. docs/betting-2026-10/BRACKET_SIM_GATE.md
(model id postseason_bracket_sim; owner answers INT-A2 (b) and Q901-1 (c), both
2026-10-01) fixes every input, format, output, the forward record, the serve
rule and the one look. This module builds exactly that file and nothing more;
section numbers below ("gate 3.1") point into it.

WHAT IT COMPUTES. Once a day, inside the nightly after the betting board export,
it reads the posted postseason bracket from StatsAPI (two calls, gate 3.3),
conditions on every played game, and computes for each of the twelve postseason
clubs P(win each remaining round), the pennant and the World Series. The
computation is an EXACT series recursion (gate 5): no random draw, so there is
no seed and no simulation error. Per game it uses the served betting_game_prob
p_home where the board prices that exact game (gate 3.1), verbatim, and
otherwise the literature Elo of tools/betting_elo.py over the 2026
regular-season finals, walked once at the first run and frozen into the
record's header (gate 3.2). A postseason result never moves a rating.

WHAT IT NEVER DOES (gate 12). No market price, no American, decimal or
fractional price, no edge, no expected value, no slot, no record row, no
ledger row, and no input to the betting pricer or any other model. Every
served number is labelled "implied, no market" with its as-of date.

THE FORWARD RECORD (gate 7). .cache/bracket_sim/record.json is the source of
truth: one entry per as-of date, first write wins, chain-hashed, never edited.
data/bracket_sim_record.json is a derived re-render of the same bytes,
published by rsync. The page serves the day's frozen entry, so it never shows
a number the record does not hold. Nothing here scores anything: the one look
(gate 10) is a separate scorer that runs once, after the World Series.

THE CORE IS PURE. parse_bracket, derive_seeds, build_structure, resolve_inputs,
compute and outputs_from take data and return data. run() alone touches the
network and the disk, and every path it writes is a module global read at call
time, so the test harness can point them elsewhere.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# identity, flag and label
# ---------------------------------------------------------------------------
MODEL_ID = "postseason_bracket_sim"
METHOD_VERSION = "bracket_v1"
GATE_DOC = "docs/betting-2026-10/BRACKET_SIM_GATE.md"

#: Gate 8. True serves the Pennant and World Series columns on /betting/ and the
#: Pennant tile on /franchise/ from this simulator; False restores both surfaces
#: byte for byte (the record keeps running dark either way). Landed True on
#: 2026-10-01, inside the window the owner set (by 2026-10-03).
SERVE_BRACKET_SIM = True

LABEL = "implied, no market"
LINE_TEMPLATE = ("Pennant and World Series: implied by the postseason bracket "
                 "simulator as of {as_of}, no market.")
DIVISION_COLUMNS_TEMPLATE = ("As of the end of the regular season ({build}): "
                             "postseason results are not in the Division, "
                             "Playoffs, Bye, Proj W and Win band columns.")
NOT_UPDATED_TEMPLATE = "The postseason odds did not update on {as_of}."

# ---------------------------------------------------------------------------
# paths (module globals, read at call time)
# ---------------------------------------------------------------------------
DATA = ROOT / "data"
CACHE = ROOT / ".cache"
FETCH_CACHE_DIR = CACHE / "bracket"
RECORD_PATH = CACHE / "bracket_sim" / "record.json"
RECORD_DERIVED_PATH = DATA / "bracket_sim_record.json"
OUT_PATH = DATA / "bracket_sim.json"
BOARD_PATH = DATA / "betting.json"
FUTURES_PATH = DATA / "futures.json"
STANDINGS_DIR = CACHE

SERIES_URL = "https://statsapi.mlb.com/api/v1/schedule/postseason/series"
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
#: The schedule window. A floor and a ceiling, not facts about any one season.
POSTSEASON_FIRST_MMDD = "09-15"
POSTSEASON_LAST_MMDD = "11-30"

# ---------------------------------------------------------------------------
# the formats (gate 4) and the constants of gate 3
# ---------------------------------------------------------------------------
ROUNDS = ("F", "D", "L", "W")
ROUND_ORDER = {r: i for i, r in enumerate(ROUNDS)}
ROUND_NEED = {"F": 2, "D": 3, "L": 4, "W": 4}
ROUND_LENGTH = {"F": 3, "D": 5, "L": 7, "W": 7}
ROUND_NAME = {"F": "Wild Card Series", "D": "Division Series",
              "L": "League Championship Series", "W": "World Series"}
ROUND_SERIES = {"F": 4, "D": 4, "L": 2, "W": 1}
#: 1 = the club holding home field hosts game k; 0 = the other club hosts it.
HOST_TABLE = {"F": (1, 1, 1), "D": (1, 1, 0, 0, 1), "L": (1, 1, 0, 0, 0, 1, 1),
              "W": (1, 1, 0, 0, 0, 1, 1)}
#: Series of each round per league, for the gate 6.3 round sums.
ROUND_SERIES_PER_LEAGUE = {"F": 2, "D": 2, "L": 1}
#: Gate 3.3: a game counts as played only when its codedGameState is F or O.
PLAYED_STATES = ("F", "O")
#: A postponed or cancelled game never counts as a posted game to price.
DEAD_STATES = ("D", "C")
#: Gate 7.1 `late`: a game has begun unless it is still scheduled, in pre-game,
#: postponed or cancelled.
NOT_BEGUN_STATES = ("S", "P", "D", "C")
#: Gate 3.1 condition 2 (the INT-A1 scope of docs/diamond-betting.md 8a).
BOARD_GAME_TYPES = ("F", "D", "L", "W")
LEAGUE_IDS = {"AL": 103, "NL": 104}
PLACEHOLDER_MARKS = ("/", "seed", "champion", "winner", "tbd", "tba")
CHECK_TOL = 1e-9
MONOTONE_TOL = 1e-12
GAME_INPUT_FIELDS = ["k", "host", "p_host", "source", "note", "game_pk"]


class BracketCrash(Exception):
    """Gate 9: any condition on which no probability may be written."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _ny_date(now: _dt.datetime) -> str:
    from zoneinfo import ZoneInfo
    return now.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _iso(now: _dt.datetime) -> str:
    return now.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(obj) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def _hash_of(doc: dict) -> str:
    return _sha({k: v for k, v in doc.items() if k != "sha256"})


def detect_machine() -> str:
    """`box` on the production nightly, `local` anywhere else (gate 7.2).

    EEPHUS_MACHINE overrides. Otherwise the box is recognised by the variable
    deploy/nightly-build.sh exports for every pipeline run."""
    forced = (os.environ.get("EEPHUS_MACHINE") or "").strip().lower()
    if forced in ("box", "local"):
        return forced
    return "box" if os.environ.get("EEPHUS_SKIP_INPROC_BUILD") == "1" else "local"


def _org_by_id(tid):
    from trades import canonical_org_from_id
    return canonical_org_from_id(tid, None)


def _all_orgs() -> set:
    from trades import _org_by_id as _m
    return set(_m().values())


def _is_placeholder(name: str | None) -> bool:
    low = str(name or "").lower()
    return any(m in low for m in PLACEHOLDER_MARKS)


def _elo():
    from tools import betting_elo
    return betting_elo


def elo_win_prob(r_host: float, r_visitor: float, home_adv: float) -> float:
    """Gate 3.2: P(host wins) = 1 / (1 + 10 ^ (-(R_host - R_visitor + home) / 400))."""
    return _elo().elo_win_prob(r_host, r_visitor, home_adv)


# ---------------------------------------------------------------------------
# reading the bracket (gate 3.3)
# ---------------------------------------------------------------------------
def _game_row(g: dict, org_of) -> dict:
    teams = g.get("teams") or {}
    out = {
        "game_pk": g.get("gamePk"),
        "k": g.get("seriesGameNumber"),
        "official_date": g.get("officialDate"),
        "game_date": g.get("gameDate"),
        "state": (g.get("status") or {}).get("codedGameState"),
        "if_necessary": g.get("ifNecessary"),
        "game_type": g.get("gameType"),
        "description": g.get("seriesDescription"),
        "venue_id": (g.get("venue") or {}).get("id"),
        "series_status": g.get("seriesStatus") or {},
    }
    for side in ("home", "away"):
        t = (teams.get(side) or {})
        team = t.get("team") or {}
        tid, name = team.get("id"), team.get("name")
        org = org_of(tid) if tid is not None else None
        if org is None and not _is_placeholder(name):
            raise BracketCrash(f"posted club id {tid} ({name}) in game "
                               f"{g.get('gamePk')} does not resolve to one of the 30 clubs")
        out[side] = org
        out[side + "_name"] = name
        out[side + "_venue_id"] = (team.get("venue") or {}).get("id")
        out[side + "_win"] = t.get("isWinner")
        out[side + "_score"] = t.get("score")
    return out


def _league_of(description: str | None, rnd: str) -> str | None:
    d = str(description or "")
    if rnd == "W":
        return None
    for lg in LEAGUE_IDS:
        if d.startswith(lg + " "):
            return lg
    raise BracketCrash(f"cannot tell the league of a {rnd} series from {description!r}")


def parse_bracket(series_payload: dict, schedule_payload: dict, *, org_of=None) -> list[dict]:
    """The eleven posted series, each with its games, wins and decided flag.

    The series endpoint fixes which game belongs to which series; the schedule
    call (hydrate=team,seriesStatus) supplies each game's status, clubs and
    result and wins wherever both carry a game."""
    org_of = org_of or _org_by_id
    sched = {}
    for d in (schedule_payload or {}).get("dates") or []:
        for g in d.get("games") or []:
            if g.get("gamePk") is not None:
                sched[g["gamePk"]] = g
    out = []
    for se in (series_payload or {}).get("series") or []:
        sid = (se.get("series") or {}).get("id")
        if not sid or sid[:1] not in ROUNDS:
            continue
        rnd = sid[0]
        games = [_game_row(sched.get(g0.get("gamePk")) or g0, org_of)
                 for g0 in se.get("games") or []]
        games.sort(key=lambda r: (r["k"] or 0, str(r["game_date"] or ""), r["game_pk"] or 0))
        desc = next((g["description"] for g in games if g["description"]), None)
        clubs = sorted({c for g in games for c in (g["home"], g["away"]) if c})
        if len(clubs) > 2:
            raise BracketCrash(f"series {sid} lists {len(clubs)} clubs: {clubs}")
        holders = sorted({g[s + "_name"] for g in games for s in ("home", "away")
                          if not g[s] and g[s + "_name"]})
        wins: dict[str, int] = {c: 0 for c in clubs}
        played = []
        over_winner = None
        for g in games:
            if g["state"] not in PLAYED_STATES:
                continue
            if not (g["home"] and g["away"]):
                raise BracketCrash(f"played game {g['game_pk']} in {sid} has a placeholder club")
            if g["home_win"] is True or g["away_win"] is True:
                w = g["home"] if g["home_win"] is True else g["away"]
            elif g["home_score"] is not None and g["away_score"] is not None \
                    and g["home_score"] != g["away_score"]:
                w = g["home"] if g["home_score"] > g["away_score"] else g["away"]
            else:
                raise BracketCrash(f"played game {g['game_pk']} in {sid} has no winner")
            wins[w] = wins.get(w, 0) + 1
            played.append(g["game_pk"])
            st = g["series_status"] or {}
            if st.get("isOver") and (st.get("winningTeam") or {}).get("id") is not None:
                over_winner = org_of((st.get("winningTeam") or {}).get("id"))
        need = ROUND_NEED[rnd]
        reached = [c for c, n in wins.items() if n >= need]
        if len(reached) > 1:
            raise BracketCrash(f"series {sid}: two clubs reached {need} wins")
        winner = reached[0] if reached else over_winner
        if winner is not None and winner not in clubs:
            raise BracketCrash(f"series {sid}: winner {winner} is not one of its clubs")
        loser = None
        if winner is not None:
            others = [c for c in clubs if c != winner]
            loser = others[0] if others else None
        out.append({
            "id": sid, "round": rnd, "league": _league_of(desc, rnd), "description": desc,
            "need": need, "length": ROUND_LENGTH[rnd],
            "posted_clubs": clubs, "placeholders": holders,
            "wins": {c: wins[c] for c in sorted(wins)},
            "decided": winner is not None, "winner": winner, "loser": loser,
            "played_game_pks": sorted(played),
            "games": games,
        })
    if not out:
        return []
    counts = {r: sum(1 for s in out if s["round"] == r) for r in ROUNDS}
    if counts != ROUND_SERIES:
        raise BracketCrash(f"the posted bracket has series counts {counts}, not {ROUND_SERIES}")
    out.sort(key=lambda s: (ROUND_ORDER[s["round"]], s["id"]))
    return out


# ---------------------------------------------------------------------------
# seeds (gate 3.4)
# ---------------------------------------------------------------------------
def standings_table(records: list) -> dict:
    """{org: {league, division, wins, losses}} from StatsAPI standings records."""
    from trades import canonical_org_from_id
    inv = {v: k for k, v in LEAGUE_IDS.items()}
    out = {}
    for rec in records or []:
        lg = inv.get((rec.get("league") or {}).get("id"))
        div = (rec.get("division") or {}).get("id")
        for tr in rec.get("teamRecords") or []:
            team = tr.get("team") or {}
            org = canonical_org_from_id(team.get("id"), team.get("name"))
            if org:
                out[org] = {"league": lg, "division": div,
                            "wins": int(tr.get("wins") or 0), "losses": int(tr.get("losses") or 0)}
    return out


def _cmp_pct(a: dict, b: dict) -> int:
    """Sign of pct(a) - pct(b), exact (cross-multiplied, no float)."""
    x = a["wins"] * (b["wins"] + b["losses"])
    y = b["wins"] * (a["wins"] + a["losses"])
    return (x > y) - (x < y)


def derive_seeds(series: list[dict], records: list) -> dict:
    """Seeds read off the posted bracket and checked against final standings.

    Byes (in a Division Series, in no Wild Card Series) are seeds 1 and 2; the
    Wild Card hosts are 3 and 4, the division champion among them being 3; their
    visitors are 6 and 5. Seed 1 is the bye whose Division Series takes the 4/5
    winner, seed 2 the one that takes the 3/6 winner, read from the posted
    opponent or placeholder. Any disagreement with the standings is a crash."""
    from franchise_export import division_champions
    from trades import canonical_org
    table = standings_table(records)
    champs_by_div = division_champions(records, live=True)
    seeds, links = {}, {}
    for lg in LEAGUE_IDS:
        fs = [s for s in series if s["round"] == "F" and s["league"] == lg]
        ds = [s for s in series if s["round"] == "D" and s["league"] == lg]
        if len(fs) != 2 or len(ds) != 2:
            raise BracketCrash(f"{lg}: {len(fs)} Wild Card and {len(ds)} Division Series posted")
        host_of = {}
        for f in fs:
            if len(f["posted_clubs"]) != 2:
                raise BracketCrash(f"{f['id']}: a Wild Card Series without two posted clubs")
            g1 = next((g for g in f["games"] if g["k"] == 1), f["games"][0] if f["games"] else None)
            if not g1 or g1["home"] not in f["posted_clubs"]:
                raise BracketCrash(f"{f['id']}: no posted host")
            host_of[f["id"]] = g1["home"]
        wc_clubs = {c for f in fs for c in f["posted_clubs"]}
        byes = sorted({c for d in ds for c in d["posted_clubs"]} - wc_clubs)
        if len(byes) != 2:
            raise BracketCrash(f"{lg}: {len(byes)} bye clubs on the posted bracket, not 2")
        lg_divs = {(rec.get("division") or {}).get("id") for rec in records or []
                   if (rec.get("league") or {}).get("id") == LEAGUE_IDS[lg]}
        champs = {champs_by_div.get(dv) for dv in lg_divs}
        if None in champs or len(champs) != 3:
            raise BracketCrash(f"{lg}: the standings name {sorted(c for c in champs if c)} "
                               "as division champions, not three clubs")
        hosts = [host_of[f["id"]] for f in fs]
        champ_hosts = [h for h in hosts if h in champs]
        if len(champ_hosts) != 1:
            raise BracketCrash(f"{lg}: {len(champ_hosts)} Wild Card hosts are division champions, not 1")
        s3 = champ_hosts[0]
        s4 = next(h for h in hosts if h != s3)
        f36 = next(f for f in fs if host_of[f["id"]] == s3)
        f45 = next(f for f in fs if host_of[f["id"]] == s4)
        s6 = next(c for c in f36["posted_clubs"] if c != s3)
        s5 = next(c for c in f45["posted_clubs"] if c != s4)
        link = {}
        for d in ds:
            mine = [b for b in byes if b in d["posted_clubs"]]
            if len(mine) != 1:
                raise BracketCrash(f"{d['id']}: {len(mine)} bye clubs in one Division Series")
            other = [c for c in d["posted_clubs"] if c != mine[0]]
            got = None
            if other:
                got = next((f["id"] for f in fs if other[0] in f["posted_clubs"]), None)
                if got is None:
                    raise BracketCrash(f"{d['id']}: posted opponent {other[0]} played no Wild Card Series")
            else:
                for name in d["placeholders"]:
                    parts = [p.strip() for p in str(name).split("/")]
                    if len(parts) == 2:
                        codes = {canonical_org(p) for p in parts}
                        got = next((f["id"] for f in fs if set(f["posted_clubs"]) == codes), got)
            link[d["id"]] = (mine[0], got)
        by_f = {f_id: bye for bye, f_id in link.values() if f_id}
        if len(by_f) != len([1 for _b, f_id in link.values() if f_id]):
            raise BracketCrash(f"{lg}: both Division Series read the same Wild Card Series")
        if f45["id"] in by_f:
            s1 = by_f[f45["id"]]
        elif f36["id"] in by_f:
            s1 = next(b for b in byes if b != by_f[f36["id"]])
        else:
            a, b = (table.get(x) for x in byes)
            if not a or not b or _cmp_pct(a, b) == 0:
                raise BracketCrash(f"{lg}: seeds 1 and 2 cannot be told apart")
            s1 = byes[0] if _cmp_pct(a, b) > 0 else byes[1]
        s2 = next(b for b in byes if b != s1)
        order = {"1": s1, "2": s2, "3": s3, "4": s4, "5": s5, "6": s6}
        # ---- the check against the final standings ----------------------
        for k, c in order.items():
            row = table.get(c)
            if not row or row["league"] != lg:
                raise BracketCrash(f"{lg} seed {k} {c} is not an {lg} club in the standings")
        if {s1, s2, s3} != champs:
            raise BracketCrash(f"{lg}: seeds 1-3 {sorted([s1, s2, s3])} are not the division "
                               f"champions {sorted(champs)}")
        for hi, lo in (("1", "2"), ("2", "3"), ("4", "5"), ("5", "6")):
            if _cmp_pct(table[order[hi]], table[order[lo]]) < 0:
                raise BracketCrash(f"{lg}: seed {hi} {order[hi]} has a worse record than "
                                   f"seed {lo} {order[lo]}")
        for c, row in table.items():
            if row["league"] == lg and c not in order.values() \
                    and _cmp_pct(row, table[s6]) > 0:
                raise BracketCrash(f"{lg}: {c} out-records seed 6 {s6} and is not in the bracket")
        seeds[lg] = order
        links[lg] = {"F36": f36["id"], "F45": f45["id"],
                     "D1": next(d_id for d_id, (b, _f) in link.items() if b == s1),
                     "D2": next(d_id for d_id, (b, _f) in link.items() if b == s2)}
    clubs = {c for o in seeds.values() for c in o.values()}
    info = {c: dict(table[c]) for c in sorted(clubs)}
    return {"seeds": seeds, "links": links, "clubs": info}


# ---------------------------------------------------------------------------
# structure: who can meet whom
# ---------------------------------------------------------------------------
def build_structure(series: list[dict], seeding: dict) -> list[dict]:
    """Each series with its two sides: a fixed club, or the winner of an
    earlier series. The posted clubs must sit inside each side's support."""
    by_id = {s["id"]: s for s in series}
    seeds, links = seeding["seeds"], seeding["links"]
    sides: dict[str, dict] = {}
    for lg, o in seeds.items():
        lk = links[lg]
        sides[lk["F36"]] = {"A": {"club": o["3"]}, "B": {"club": o["6"]}}
        sides[lk["F45"]] = {"A": {"club": o["4"]}, "B": {"club": o["5"]}}
        sides[lk["D1"]] = {"A": {"club": o["1"]}, "B": {"from": lk["F45"]}}
        sides[lk["D2"]] = {"A": {"club": o["2"]}, "B": {"from": lk["F36"]}}
        lcs = next(s for s in series if s["round"] == "L" and s["league"] == lg)
        sides[lcs["id"]] = {"A": {"from": lk["D1"]}, "B": {"from": lk["D2"]}}
    ws = next(s for s in series if s["round"] == "W")
    al = next(s["id"] for s in series if s["round"] == "L" and s["league"] == "AL")
    nl = next(s["id"] for s in series if s["round"] == "L" and s["league"] == "NL")
    sides[ws["id"]] = {"A": {"from": al}, "B": {"from": nl}}
    out = []
    support: dict[str, set] = {}
    for s in sorted(series, key=lambda s: (ROUND_ORDER[s["round"]], s["id"])):
        sd = sides.get(s["id"])
        if sd is None:
            raise BracketCrash(f"series {s['id']} has no place in the bracket")
        sup = set()
        for side in ("A", "B"):
            ref = sd[side]
            sup |= {ref["club"]} if "club" in ref else support[ref["from"]]
        if not set(s["posted_clubs"]) <= sup:
            raise BracketCrash(f"series {s['id']}: posted clubs {s['posted_clubs']} are not "
                               f"among the clubs that can reach it {sorted(sup)}")
        for ref in (sd["A"], sd["B"]):
            if "from" in ref and by_id[ref["from"]]["decided"]:
                w = by_id[ref["from"]]["winner"]
                if s["posted_clubs"] and len(s["posted_clubs"]) == 2 and w not in s["posted_clubs"]:
                    raise BracketCrash(f"series {s['id']}: {ref['from']} winner {w} is not posted")
        support[s["id"]] = {s["winner"]} if s["decided"] else sup
        row = {k: v for k, v in s.items() if k != "games"}
        row["sides"] = sd
        row["games"] = [[g["k"], g["game_pk"], g["official_date"], g["game_date"], g["state"],
                         g["home"] or g["home_name"], g["away"] or g["away_name"], g["if_necessary"]]
                        for g in s["games"]]
        out.append(row)
    return out


def _paths(structure: list[dict], seeding: dict) -> dict:
    """{club: [series id per round it can play, in order]}."""
    paths = {}
    for lg, o in seeding["seeds"].items():
        lk = seeding["links"][lg]
        lcs = next(s["id"] for s in structure if s["round"] == "L" and s["league"] == lg)
        ws = next(s["id"] for s in structure if s["round"] == "W")
        for k in ("3", "6"):
            paths[o[k]] = [lk["F36"], lk["D2"], lcs, ws]
        for k in ("4", "5"):
            paths[o[k]] = [lk["F45"], lk["D1"], lcs, ws]
        paths[o["1"]] = [lk["D1"], lcs, ws]
        paths[o["2"]] = [lk["D2"], lcs, ws]
    return paths


# ---------------------------------------------------------------------------
# inputs (gates 3.1, 3.2 and 4)
# ---------------------------------------------------------------------------
def _support(structure: list[dict]) -> dict:
    sup = {}
    for s in structure:
        if s["decided"]:
            sup[s["id"]] = [s["winner"]]
            continue
        got = set()
        for side in ("A", "B"):
            ref = s["sides"][side]
            got |= {ref["club"]} if "club" in ref else set(sup[ref["from"]])
        sup[s["id"]] = sorted(got)
    return sup


def _side_support(ref: dict, sup: dict) -> list:
    return [ref["club"]] if "club" in ref else list(sup[ref["from"]])


def _board_index(board: dict | None) -> dict:
    out = {}
    for c in (board or {}).get("team_bets") or []:
        if c.get("game_pk") is not None:
            out[c["game_pk"]] = c
    return out


def board_probability(card: dict | None, host: str, visitor: str):
    """Gate 3.1: (p_home, None) when every condition holds, else (None, reason)."""
    if card is None:
        return None, "condition 1: the served board carries no card for this game"
    if card.get("game_type") not in BOARD_GAME_TYPES:
        return None, f"condition 2: the card's game_type is {card.get('game_type')!r}"
    h = (card.get("home") or {}).get("org")
    a = (card.get("away") or {}).get("org")
    if (h, a) != (host, visitor):
        return None, f"condition 3: the card is {a} at {h}, the bracket has {visitor} at {host}"
    p = (card.get("model") or {}).get("p_home")
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) \
            or not (0.0 < float(p) < 1.0):
        return None, "condition 4: model.p_home is not a number strictly between 0 and 1"
    return float(p), None


def resolve_inputs(structure: list[dict], games_by_series: dict, seeding: dict,
                   board: dict | None, ratings: dict) -> tuple[list, list, list]:
    """Every game the recursion can reach, with its host and probability.

    Returns (inputs, host_disagreements, ws_home_ties)."""
    sup = _support(structure)
    seed_no = {c: int(k) for o in seeding["seeds"].values() for k, c in o.items()}
    info = seeding["clubs"]
    cards = _board_index(board)
    board_at = (board or {}).get("generated_at")
    inputs, disagree, ties = [], [], []
    for s in structure:
        if s["decided"]:
            continue
        rnd, sid = s["round"], s["id"]
        posted_games = [g for g in games_by_series.get(sid) or []]
        for x in _side_support(s["sides"]["A"], sup):
            for y in _side_support(s["sides"]["B"], sup):
                posted_pair = len(s["posted_clubs"]) == 2 and set(s["posted_clubs"]) == {x, y}
                start = [s["wins"].get(x, 0), s["wins"].get(y, 0)] if posted_pair else [0, 0]
                by_k = {}
                if posted_pair:
                    for g in posted_games:
                        if g["state"] in PLAYED_STATES or g["state"] in DEAD_STATES:
                            continue
                        if g["home"] in (x, y) and g["away"] in (x, y) and g["k"]:
                            by_k.setdefault(g["k"], g)
                if rnd in ("F", "D"):
                    variants = [(x, 1.0)]
                elif rnd == "L":
                    variants = [(x if seed_no[x] < seed_no[y] else y, 1.0)]
                else:
                    c = _cmp_pct(info[x], info[y])
                    if c == 0 and not (posted_pair and 1 in by_k):
                        variants = [(x, 0.5), (y, 0.5)]
                        ties.append({"series": sid, "pair": [x, y],
                                     "rule": "equal winning percentage: home field weighted one half each"})
                    elif c == 0:
                        variants = [(by_k[1]["home"], 1.0)]
                    else:
                        variants = [(x if c > 0 else y, 1.0)]
                rows = []
                for hf, weight in variants:
                    games = []
                    for k in range(start[0] + start[1] + 1, s["length"] + 1):
                        table_host = hf if HOST_TABLE[rnd][k - 1] else (y if hf == x else x)
                        g = by_k.get(k)
                        host = g["home"] if g else table_host
                        visitor = y if host == x else x
                        if g and host != table_host and weight == 1.0:
                            disagree.append({"series": sid, "game_pk": g["game_pk"], "k": k,
                                             "posted_host": host, "table_host": table_host})
                        neutral = bool(g and g.get("venue_id") and g.get("home_venue_id")
                                       and g["venue_id"] != g["home_venue_id"])
                        p, why = (board_probability(cards.get(g["game_pk"]), host, visitor)
                                  if g else (None, "no posted game with both clubs"))
                        if p is not None:
                            card = cards.get(g["game_pk"]) or {}
                            note = {"board_generated_at": board_at,
                                    "postseason_label": card.get("postseason_label")}
                            games.append([k, host, p, "board", note, g["game_pk"]])
                            continue
                        if host not in ratings or visitor not in ratings:
                            raise BracketCrash(f"the frozen Elo walk lacks {host if host not in ratings else visitor}")
                        home_adv = 0.0 if neutral else _elo_home_adv()
                        p = elo_win_prob(float(ratings[host]), float(ratings[visitor]), home_adv)
                        note = why + ("; neutral site, no home term" if neutral else "")
                        games.append([k, host, p, "prior", note, g["game_pk"] if g else None])
                    rows.append({"weight": weight, "home_field": hf, "games": games})
                inputs.append({"series": sid, "pair": [x, y], "start": start, "variants": rows})
    return inputs, disagree, ties


def _elo_home_adv() -> float:
    return float(_elo().LITERATURE_HOME_ADV_ELO)


# ---------------------------------------------------------------------------
# the computation (gate 5) and its checks (gate 6.3)
# ---------------------------------------------------------------------------
def series_win_prob(games: list, x: str, need: int, a: int, b: int) -> float:
    """P(x wins the series) from x's a wins and the other club's b, walking the
    remaining games in order; each game row is [k, host, p_host, ...]."""
    by_k = {int(g[0]): g for g in games}
    memo: dict = {}

    def f(i: int, j: int) -> float:
        if i >= need:
            return 1.0
        if j >= need:
            return 0.0
        if (i, j) in memo:
            return memo[(i, j)]
        g = by_k.get(i + j + 1)
        if g is None:
            raise BracketCrash(f"no input for game {i + j + 1}")
        p = float(g[2]) if g[1] == x else 1.0 - float(g[2])
        v = p * f(i + 1, j) + (1.0 - p) * f(i, j + 1)
        memo[(i, j)] = v
        return v

    return f(int(a), int(b))


def compute(structure: list[dict], inputs: list[dict]) -> dict:
    """{series id: {club: P(wins that series)}} over the whole bracket."""
    rows = {(r["series"], r["pair"][0], r["pair"][1]): r for r in inputs}
    dist: dict[str, dict] = {}
    for s in sorted(structure, key=lambda s: (ROUND_ORDER[s["round"]], s["id"])):
        if s["decided"]:
            dist[s["id"]] = {s["winner"]: 1.0}
            continue
        sides = []
        for side in ("A", "B"):
            ref = s["sides"][side]
            sides.append({ref["club"]: 1.0} if "club" in ref else dist[ref["from"]])
        out: dict[str, float] = {}
        for x in sorted(sides[0]):
            for y in sorted(sides[1]):
                w = sides[0][x] * sides[1][y]
                r = rows.get((s["id"], x, y))
                if r is None:
                    raise BracketCrash(f"no inputs for {x} v {y} in {s['id']}")
                q = 0.0
                for v in r["variants"]:
                    q += float(v["weight"]) * series_win_prob(v["games"], x, s["need"],
                                                              r["start"][0], r["start"][1])
                out[x] = out.get(x, 0.0) + w * q
                out[y] = out.get(y, 0.0) + w * (1.0 - q)
        dist[s["id"]] = {c: out[c] for c in sorted(out)}
    return dist


def run_checks(adv: dict, structure: list[dict], seeding: dict, paths: dict) -> dict:
    """Gate 6.3, on the unrounded values. Returns the results; never raises."""
    league = {c: lg for lg, o in seeding["seeds"].items() for c in o.values()}
    vals = [p for a in adv.values() for p in a.values()]
    finite = all(isinstance(p, float) and math.isfinite(p) and -CHECK_TOL <= p <= 1 + CHECK_TOL
                 for p in vals)
    title = math.fsum(a.get("W", 0.0) for a in adv.values())
    pennant = {lg: math.fsum(adv[c].get("L", 0.0) for c in adv if league[c] == lg)
               for lg in LEAGUE_IDS}
    sums = {}
    for r, n in ROUND_SERIES_PER_LEAGUE.items():
        for lg in LEAGUE_IDS:
            sums[f"{r}_{lg}"] = [math.fsum(adv[c].get(r, 0.0) for c in adv if league[c] == lg), n]
    sums["W"] = [title, 1]
    monotone = True
    for c, a in adv.items():
        seq = [a[r] for r in ROUNDS if r in a]
        if any(seq[i + 1] > seq[i] + MONOTONE_TOL for i in range(len(seq) - 1)):
            monotone = False
    exact = True
    for s in structure:
        if not s["decided"]:
            continue
        r = s["round"]
        if adv.get(s["winner"], {}).get(r) != 1.0:
            exact = False
        if s["loser"]:
            later = [rr for rr in ROUNDS if ROUND_ORDER[rr] >= ROUND_ORDER[r]]
            if any(adv.get(s["loser"], {}).get(rr, 0.0) != 0.0 for rr in later):
                exact = False
    results = {
        "title_sum_is_1": abs(title - 1.0) <= CHECK_TOL,
        "pennant_sum_is_1_per_league": all(abs(v - 1.0) <= CHECK_TOL for v in pennant.values()),
        "round_sums_equal_series_counts": all(abs(v - n) <= CHECK_TOL for v, n in sums.values()),
        "never_rises_round_to_round": monotone,
        "decided_clubs_exactly_0_or_1": exact,
        "every_value_finite": finite,
    }
    results["passed"] = all(results.values())
    results["sums"] = {k: [v, n] for k, (v, n) in sorted(sums.items())}
    results["pennant_sums"] = pennant
    return results


def outputs_from(structure: list[dict], inputs: list[dict], seeding: dict) -> dict:
    """The per-club outputs of gate 6.1 and the 6.3 checks, from stored inputs.

    Pure: the replay test recomputes every stored entry through this function
    and compares the canonical bytes."""
    dist = compute(structure, inputs)
    paths = _paths(structure, seeding)
    by_id = {s["id"]: s for s in structure}
    adv = {}
    for c in sorted(paths):
        adv[c] = {by_id[sid]["round"]: dist[sid].get(c, 0.0) for sid in paths[c]}
    checks = run_checks(adv, structure, seeding, paths)
    seed_of = {c: (lg, int(k)) for lg, o in seeding["seeds"].items() for k, c in o.items()}
    clubs = {}
    for c in sorted(paths):
        a6 = {r: round(v, 6) for r, v in adv[c].items()}
        status, round_now, sid_now = "alive", None, None
        for sid in paths[c]:
            s = by_id[sid]
            if s["decided"]:
                if s["winner"] == c:
                    if s["round"] == "W":
                        status = "champion"
                    continue
                status = "eliminated"
                round_now = s["round"]
                break
            round_now, sid_now = s["round"], sid
            break
        clubs[c] = {
            "league": seed_of[c][0], "seed": seed_of[c][1], "status": status,
            "round_now": round_now if status == "alive" else None,
            "eliminated_in": round_now if status == "eliminated" else None,
            "series_now": sid_now if status == "alive" else None,
            "series_now_text": _series_text(c, status, round_now, by_id.get(sid_now) if sid_now else None),
            "adv": a6,
            "p_round_now": a6.get(round_now) if status == "alive" else None,
            "reach_lcs_pct": a6.get("D"),
            "pennant_pct": a6.get("L"),
            "ws_pct": a6.get("W"),
        }
    return {
        "clubs": clubs,
        "series_dist": {sid: {c: round(p, 6) for c, p in d.items()} for sid, d in sorted(dist.items())},
        "checks": checks,
    }


def _series_text(club: str, status: str, rnd: str | None, s: dict | None) -> str:
    if status == "champion":
        return "won the World Series"
    if status == "eliminated":
        return f"eliminated in the {ROUND_NAME[rnd]}"
    if s is None:
        return ""
    name = s.get("description") or ROUND_NAME[s["round"]]
    opp = [c for c in s["posted_clubs"] if c != club]
    if club in s["posted_clubs"] and opp:
        a, b = s["wins"].get(club, 0), s["wins"].get(opp[0], 0)
        if a + b == 0:
            return f"{name} v {opp[0]}, not started"
        state = "tied" if a == b else ("leads" if a > b else "trails")
        return f"{name} v {opp[0]}, {state} {a}-{b}"
    return f"{name}, opponent not yet decided"


# ---------------------------------------------------------------------------
# the record (gate 7) and its write guard (gate 9)
# ---------------------------------------------------------------------------
def verify_record(rec: dict) -> None:
    """The hash chain end to end; raises BracketCrash on any break."""
    head = rec.get("header")
    if not head:
        if rec.get("entries"):
            raise BracketCrash("record entries without a header")
        return
    if _hash_of(head) != head.get("sha256"):
        raise BracketCrash("record header hash does not verify")
    prev = head["sha256"]
    last = ""
    for e in rec.get("entries") or []:
        if e.get("prev_sha256") != prev:
            raise BracketCrash(f"record chain breaks at {e.get('as_of')}")
        if _hash_of(e) != e.get("sha256"):
            raise BracketCrash(f"record entry {e.get('as_of')} was edited")
        if str(e.get("as_of")) <= last:
            raise BracketCrash(f"record entry {e.get('as_of')} is out of order")
        last = str(e.get("as_of"))
        prev = e["sha256"]


def guard_append(old: dict, new: dict) -> None:
    """Gate 9: refuse a write that is shorter, edits an entry or runs backwards."""
    verify_record(new)
    o_head, n_head = old.get("header"), new.get("header")
    if o_head and _canon(o_head) != _canon(n_head):
        raise BracketCrash("write guard: the record header would change")
    o_e, n_e = old.get("entries") or [], new.get("entries") or []
    if len(n_e) != len(o_e) + 1:
        raise BracketCrash(f"write guard: {len(o_e)} entries would become {len(n_e)}, not one more")
    for a, b in zip(o_e, n_e):
        if _canon(a) != _canon(b):
            raise BracketCrash(f"write guard: entry {a.get('as_of')} would be edited")
    if o_e and str(n_e[-1].get("as_of")) <= str(o_e[-1].get("as_of")):
        raise BracketCrash("write guard: a new entry must carry a later as-of date")


def load_record() -> dict:
    p = RECORD_PATH
    if not p.exists():
        return {}
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BracketCrash(f"the record does not parse: {exc}") from exc
    verify_record(rec)
    return rec


def _write_atomic(path: Path, raw: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(path)


def write_record(old: dict, new: dict) -> None:
    guard_append(old, new)
    raw = json.dumps(new, separators=(",", ":"), allow_nan=False)
    _write_atomic(RECORD_PATH, raw)
    _write_atomic(RECORD_DERIVED_PATH, raw)


def rerender_record(rec: dict) -> None:
    """Re-render the derived public copy from the source of truth, verbatim."""
    if rec.get("header"):
        _write_atomic(RECORD_DERIVED_PATH, json.dumps(rec, separators=(",", ":"), allow_nan=False))


def _seal(doc: dict, prev: str | None) -> dict:
    out = dict(doc)
    if prev is not None:
        out["prev_sha256"] = prev
    out.pop("sha256", None)
    out["sha256"] = _hash_of(out)
    return out


def append_entry(rec: dict, entry: dict) -> dict:
    entries = list(rec.get("entries") or [])
    prev = entries[-1]["sha256"] if entries else rec["header"]["sha256"]
    new = {"header": rec["header"], "entries": entries + [_seal(entry, prev)]}
    write_record(rec, new)
    return new


def build_header(season: int, now: _dt.datetime, machine: str, structure: list[dict],
                 games: list[dict] | None = None) -> dict:
    """Gate 3.2 and 7.1: the frozen Elo walk, the constants, decided_at_start."""
    betting_elo = _elo()
    if games is None:
        import betting_model as bm
        games = bm.completed_games(str(season), refresh=False)
    used = sorted(
        ([g.get("game_pk"), g.get("date"), g.get("home_org"), g.get("away_org"),
          int(g.get("home_runs")), int(g.get("away_runs"))]
         for g in games or []
         if g.get("home_org") and g.get("away_org")
         and g.get("home_runs") is not None and g.get("away_runs") is not None),
        key=lambda r: (r[1] or "", r[0] or 0))
    ratings = betting_elo.final_ratings(games or [])
    missing = sorted(_all_orgs() - set(ratings))
    if missing:
        raise BracketCrash(f"the Elo walk lacks {', '.join(missing)}")
    head = {
        "model_id": MODEL_ID, "method_version": METHOD_VERSION, "gate": GATE_DOC,
        "season": int(season), "created_at": _iso(now), "created_machine": machine,
        "elo": {
            "ratings": {k: float(ratings[k]) for k in sorted(ratings)},
            "n_games": len(used),
            "games_sha256": hashlib.sha256(
                json.dumps(used, separators=(",", ":")).encode("ascii")).hexdigest(),
            "games_hash_basis": ("sha256 of the compact JSON list of [game_pk, date, home_org, "
                                 "away_org, home_runs, away_runs] over the walked games, sorted "
                                 "by (date, game_pk)"),
            "first_game_date": used[0][1] if used else None,
            "last_game_date": used[-1][1] if used else None,
            "k": float(betting_elo.LITERATURE_K),
            "home_adv_elo": float(betting_elo.LITERATURE_HOME_ADV_ELO),
            "base": float(betting_elo.BASE_RATING),
            "source": ("betting_model.completed_games(season, refresh=False): the 2026 "
                       "regular-season finals (gameType R only), walked once through "
                       "tools/betting_elo.final_ratings and frozen here"),
        },
        "constants": {
            "round_need": ROUND_NEED, "round_length": ROUND_LENGTH,
            "host_table": {k: list(v) for k, v in HOST_TABLE.items()},
            "played_states": list(PLAYED_STATES), "board_game_types": list(BOARD_GAME_TYPES),
            "label": LABEL, "check_tolerance": CHECK_TOL,
            "home_field": {"F": "every game at the higher seed",
                           "D": "2-2-1, the higher seed hosts games 1, 2 and 5",
                           "L": "2-3-2, the higher seed hosts games 1, 2, 6 and 7",
                           "W": ("2-3-2, the better regular-season winning percentage hosts "
                                 "games 1, 2, 6 and 7; equal percentages weight each club one half"),
                           "posted": "a posted host with both clubs resolved overrides the table"},
        },
        "game_input_fields": GAME_INPUT_FIELDS,
        "decided_at_start": [{"series": s["id"], "winner": s["winner"], "loser": s["loser"]}
                             for s in structure if s["decided"]],
    }
    return _seal(head, None)


# ---------------------------------------------------------------------------
# fetching (gate 3.3)
# ---------------------------------------------------------------------------
def _http_get(url: str, params: dict) -> dict:
    try:
        import feed_cache
        sess = feed_cache.SESSION
    except Exception:                                         # noqa: BLE001
        import requests
        sess = requests
    resp = sess.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_state(season: int, as_of: str, now: _dt.datetime, fetch=None) -> tuple[dict, dict, dict]:
    """The two StatsAPI calls, cached under .cache/bracket/ with fetched_at.

    The cache is a receipt of what was read, never a source: every run fetches
    (gate 9.5, no stale bracket)."""
    fetch = fetch or _http_get
    calls = (
        ("series", SERIES_URL, {"sportId": 1, "season": int(season)}),
        ("schedule", SCHEDULE_URL, {"sportId": 1, "season": int(season),
                                    "gameType": ",".join(ROUNDS), "hydrate": "team,seriesStatus",
                                    "startDate": f"{season}-{POSTSEASON_FIRST_MMDD}",
                                    "endDate": f"{season}-{POSTSEASON_LAST_MMDD}"}),
    )
    got, stamps = {}, {}
    for name, url, params in calls:
        try:
            payload = fetch(url, params)
        except Exception as exc:                              # noqa: BLE001
            raise BracketCrash(f"StatsAPI {name} call failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise BracketCrash(f"StatsAPI {name} call did not parse")
        fetched_at = _iso(now)
        got[name] = payload
        stamps[name] = fetched_at
        try:
            _write_atomic(FETCH_CACHE_DIR / f"{as_of}_{name}.json",
                          json.dumps({"fetched_at": fetched_at, "url": url, "params": params,
                                      "payload": payload}, separators=(",", ":")))
        except OSError as exc:                                # pragma: no cover
            log.warning("bracket_sim: could not cache the %s call (%s)", name, exc)
    return got["series"], got["schedule"], stamps


def load_standings(season: int) -> list:
    p = STANDINGS_DIR / f"statsapi_standings_{season}.json"
    try:
        return (json.loads(p.read_text(encoding="utf-8")) or {}).get("records") or []
    except (OSError, ValueError) as exc:
        raise BracketCrash(f"standings cache {p.name} unreadable: {exc}") from exc


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# the day's entry
# ---------------------------------------------------------------------------
def build_entry(series: list[dict], seeding: dict, structure: list[dict], board: dict | None,
                ratings: dict, *, as_of: str, now: _dt.datetime, machine: str,
                stamps: dict | None = None) -> dict:
    games_by_series = {s["id"]: s["games"] for s in series}
    inputs, disagree, ties = resolve_inputs(structure, games_by_series, seeding, board, ratings)
    outputs = outputs_from(structure, inputs, seeding)
    if not outputs["checks"]["passed"]:
        bad = [k for k, v in outputs["checks"].items() if v is False]
        raise BracketCrash(f"consistency check failed: {', '.join(bad)}")
    all_games = [g for s in series for g in s["games"]]
    late = any(g["official_date"] == as_of and g["state"] not in NOT_BEGUN_STATES
               for g in all_games)
    upcoming = sorted(str(g["game_date"]) for g in all_games
                      if g["state"] not in PLAYED_STATES and g["state"] not in DEAD_STATES
                      and g["game_date"])
    return {
        "kind": "good", "as_of": as_of, "generated_at": _iso(now), "machine": machine,
        "method_version": METHOD_VERSION, "season": int(as_of[:4]),
        "fetched_at": stamps or {},
        "board": ({"generated_at": (board or {}).get("generated_at"),
                   "slate_date": (board or {}).get("slate_date")} if board else None),
        "seeding": seeding,
        "bracket": structure,
        "inputs": inputs,
        "host_disagreements": disagree,
        "ws_home_ties": ties,
        "outputs": outputs,
        "late": late,
        "next_game_start": upcoming[0] if upcoming else None,
    }


def replay(entry: dict) -> bool:
    """Gate 9.4: the stored outputs, recomputed from the entry's own inputs."""
    got = outputs_from(entry["bracket"], entry["inputs"], entry["seeding"])
    return _canon(got) == _canon(entry["outputs"])


def crash_entry(as_of: str, now: _dt.datetime, machine: str, reason: str) -> dict:
    return {"kind": "crash", "as_of": as_of, "generated_at": _iso(now), "machine": machine,
            "method_version": METHOD_VERSION, "reason": str(reason)[:500]}


# ---------------------------------------------------------------------------
# the served payload (gates 6.1 and 8)
# ---------------------------------------------------------------------------
def record_summary(rec: dict) -> dict:
    entries = rec.get("entries") or []
    good = [e for e in entries if e.get("kind") == "good"]
    last = good[-1] if good else None
    machines: dict[str, int] = {}
    for e in entries:
        machines[e.get("machine") or "?"] = machines.get(e.get("machine") or "?", 0) + 1
    return {
        "path": "data/bracket_sim_record.json",
        "source_of_truth": ".cache/bracket_sim/record.json",
        "n_days": len(entries),
        "n_crash_days": sum(1 for e in entries if e.get("kind") == "crash"),
        "n_series_decided": (sum(1 for s in last["bracket"] if s["decided"]) if last else 0),
        "n_scored": 0,
        "first_as_of": entries[0]["as_of"] if entries else None,
        "last_as_of": entries[-1]["as_of"] if entries else None,
        "entries_by_machine": machines,
        "what_it_is": ("Each day's frozen output, one entry per date, chain-hashed and never "
                       "edited. Nothing in it is scored: the one look is after the World "
                       "Series, by the rule registered before the first number."),
    }


def _division_columns_note(futures: dict | None) -> str | None:
    fu = futures or {}
    if not fu.get("as_of_note") or not fu.get("generated_at"):
        return None
    return DIVISION_COLUMNS_TEMPLATE.format(build=str(fu["generated_at"])[:10])


def build_payload(rec: dict, entry: dict | None, state: str, *, run_as_of: str,
                  now: _dt.datetime, futures: dict | None, reason: str | None = None) -> dict:
    flag = bool(SERVE_BRACKET_SIM)
    on = flag and state in ("live", "final", "last_good") and entry is not None
    doc = {
        "generated_at": _iso(now),
        "produced_by": "bracket_sim.run",
        "model_id": MODEL_ID,
        "method_version": METHOD_VERSION,
        "gate": GATE_DOC,
        "label": LABEL,
        "season": int(run_as_of[:4]),
        "serve": {
            "flag": flag,
            "state": state if flag else "off",
            "computed_state": state,
            "on": on,
            "as_of": entry["as_of"] if entry else None,
            "line": LINE_TEMPLATE.format(as_of=entry["as_of"]) if entry else None,
            "division_columns_note": _division_columns_note(futures),
            "not_updated_note": (NOT_UPDATED_TEMPLATE.format(as_of=run_as_of)
                                 if flag and state == "not_updated" else None),
            "registry_row": MODEL_ID,
            "reason": reason,
        },
        "record": record_summary(rec),
        "method": ("Exact series recursion over the posted bracket, conditioned on every "
                   "played game. Per game: the served betting_game_prob p_home where the "
                   "board prices that game, else the literature Elo (1500, K 4, 24 points "
                   "home) over the 2026 regular-season finals, frozen at the first run. No "
                   "random draw, so no simulation error and no interval."),
        "never": ("No market price, no American or decimal price, no edge, no expected "
                  "value, no slot, no record row, no ledger row and no input to any model "
                  "is taken from these numbers."),
        "columns": {"pennant": f"Pennant ({LABEL})", "ws": f"World Series ({LABEL})",
                    "p_round_now": "P(win this round)", "reach_lcs": "P(reach the LCS)"},
    }
    if entry is None or state in ("not_updated", "idle"):
        doc["clubs"] = []
        doc["series"] = []
        doc["decided_series"] = []
        return doc
    doc.update({
        "as_of": entry["as_of"],
        "entry_generated_at": entry["generated_at"],
        "entry_sha256": entry["sha256"],
        "machine": entry["machine"],
        "late": entry["late"],
        "clubs": sorted(
            [{"team": c, **{k: v for k, v in o.items()}}
             for c, o in entry["outputs"]["clubs"].items()],
            key=lambda r: (-(r["ws_pct"] or 0.0), r["league"], r["seed"])),
        "series": [{"id": s["id"], "round": s["round"], "league": s["league"],
                    "description": s["description"],
                    "clubs": s["posted_clubs"] or s["placeholders"], "wins": s["wins"],
                    "decided": s["decided"], "winner": s["winner"]}
                   for s in entry["bracket"]],
        "decided_series": [{"id": s["id"], "round": s["round"], "league": s["league"],
                            "description": s["description"], "winner": s["winner"],
                            "loser": s["loser"],
                            "result": f"{s['wins'].get(s['winner'], 0)}-{s['wins'].get(s['loser'], 0)}"}
                           for s in entry["bracket"] if s["decided"]],
    })
    return doc


def write_payload(doc: dict) -> None:
    _write_atomic(OUT_PATH, json.dumps(doc, separators=(",", ":"), allow_nan=False))


# ---------------------------------------------------------------------------
# the daily step
# ---------------------------------------------------------------------------
def _last_good(rec: dict) -> dict | None:
    good = [e for e in rec.get("entries") or [] if e.get("kind") == "good"]
    return good[-1] if good else None


def _final(entry: dict | None) -> bool:
    return bool(entry) and any(s["round"] == "W" and s["decided"] for s in entry["bracket"])


def _played_since(entry: dict, series: list[dict] | None, now: _dt.datetime) -> bool:
    if series is not None:
        then = {pk for s in entry["bracket"] for pk in s.get("played_game_pks") or []}
        now_pks = {pk for s in series for pk in s.get("played_game_pks") or []}
        return bool(now_pks - then)
    nxt = entry.get("next_game_start")
    return bool(nxt) and str(nxt) <= _iso(now).replace("+00:00", "Z")


def run(*, now: _dt.datetime | None = None, fetch=None, machine: str | None = None,
        log_fn=None) -> dict:
    """The nightly step: fetch, compute, freeze, publish. Never raises.

    Returns {ok, state, as_of, wrote_entry, n_clubs, message}."""
    say = log_fn or log.info
    now = now or _dt.datetime.now(_dt.timezone.utc)
    as_of = _ny_date(now)
    season = int(as_of[:4])
    machine = machine or detect_machine()
    futures = _read_json(FUTURES_PATH)
    try:
        rec = load_record()
    except BracketCrash as exc:
        doc = build_payload({}, None, "not_updated", run_as_of=as_of, now=now,
                            futures=futures, reason=str(exc))
        write_payload(doc)
        return {"ok": False, "state": "not_updated", "as_of": as_of, "wrote_entry": False,
                "n_clubs": 0, "message": f"record refused: {exc}"}

    def _serve(entry, state, reason=None):
        write_payload(build_payload(rec, entry, state, run_as_of=as_of, now=now,
                                    futures=futures, reason=reason))
        rerender_record(rec)

    head = rec.get("header")
    if head and int(head.get("season", season)) != season:
        _serve(None, "idle", f"the record holds season {head.get('season')}; "
                             f"a {season} record is a later registration")
        return {"ok": True, "state": "idle", "as_of": as_of, "wrote_entry": False,
                "n_clubs": 0, "message": "a new season's record is a later registration"}
    entries = rec.get("entries") or []
    today = next((e for e in entries if e.get("as_of") == as_of), None)
    last_good = _last_good(rec)
    if today is not None:
        if today.get("kind") == "good":
            state = "final" if _final(today) else "live"
            _serve(today, state)
            return {"ok": True, "state": state, "as_of": as_of, "wrote_entry": False,
                    "n_clubs": len(today["outputs"]["clubs"]),
                    "message": "the day's entry is already frozen; nothing written"}
        state = ("last_good" if last_good and not _played_since(last_good, None, now)
                 else "not_updated")
        _serve(last_good if state == "last_good" else None, state, today.get("reason"))
        return {"ok": False, "state": state, "as_of": as_of, "wrote_entry": False,
                "n_clubs": 0, "message": f"the day's crash entry stands: {today.get('reason')}"}
    if _final(last_good):
        _serve(last_good, "final")
        return {"ok": True, "state": "final", "as_of": as_of, "wrote_entry": False,
                "n_clubs": len(last_good["outputs"]["clubs"]),
                "message": "the World Series is decided; the final entry is served"}
    if entries and str(entries[-1].get("as_of")) > as_of:
        _serve(last_good, "last_good", "the record already holds a later date")
        return {"ok": False, "state": "last_good", "as_of": as_of, "wrote_entry": False,
                "n_clubs": 0, "message": "the record already holds a later date"}

    series = None
    try:
        series_raw, sched_raw, stamps = fetch_state(season, as_of, now, fetch)
        series = parse_bracket(series_raw, sched_raw)
        if not series:
            _serve(None, "idle", "no postseason bracket is posted")
            return {"ok": True, "state": "idle", "as_of": as_of, "wrote_entry": False,
                    "n_clubs": 0, "message": "no postseason bracket is posted"}
        seeding = derive_seeds(series, load_standings(season))
        structure = build_structure(series, seeding)
        if not head:
            # The record starts here: the Elo walk is frozen once, with the
            # series already decided when it began (gate 7.1).
            head = build_header(season, now, machine, structure)
            rec = {"header": head, "entries": []}
        board = _read_json(BOARD_PATH)
        entry = build_entry(series, seeding, structure, board, head["elo"]["ratings"],
                            as_of=as_of, now=now, machine=machine, stamps=stamps)
        rec = append_entry(rec, entry)
        sealed = rec["entries"][-1]
        state = "final" if _final(sealed) else "live"
        _serve(sealed, state)
        say(f"bracket_sim: froze {as_of} ({machine}), {len(sealed['outputs']['clubs'])} clubs, "
            f"{sum(1 for s in structure if s['decided'])} series decided")
        return {"ok": True, "state": state, "as_of": as_of, "wrote_entry": True,
                "n_clubs": len(sealed["outputs"]["clubs"]),
                "message": f"froze {as_of}: {sum(1 for s in structure if s['decided'])} of 11 series decided"}
    except BracketCrash as exc:
        reason = str(exc)
        if rec.get("header"):
            try:
                rec = append_entry(rec, crash_entry(as_of, now, machine, reason))
            except BracketCrash as exc2:
                reason = f"{reason}; the crash entry was refused too: {exc2}"
        state = ("last_good" if last_good and not _played_since(last_good, series, now)
                 else "not_updated")
        _serve(last_good if state == "last_good" else None, state, reason)
        return {"ok": False, "state": state, "as_of": as_of, "wrote_entry": bool(rec.get("header")),
                "n_clubs": 0, "message": f"crash: {reason}"}


if __name__ == "__main__":                                     # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(run(log_fn=print), indent=1))
