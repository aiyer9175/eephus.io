#!/usr/bin/env python
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Carry data/franchise_spine.json back to 1871: the `history` block.

OWNER ANSWER 2026-09-25 (final-pass batch 6, M10-12). The Hall of Fame
franchise credit needs every war_daily stint, 1871 on, to land on one of the
30 current franchises or on a named defunct club. The 1969-2026 spine above
this block serves the /franchise/ club bWAR line and is not touched here; this
tool writes only `history`, for the seasons 1871 to 1968, and rewrites the
spine's `scope` and `not_in_scope` lines so they no longer say the spine cannot
serve /hof/.

THE KEY BEFORE 1969 IS (team_ID, lg_ID, season), NOT (team_ID, season). Before
1969 Baseball-Reference reuses a team code across unrelated clubs: BAL is the
1872 Canaries (National Association), the 1882-1891 American Association
Orioles, the 1914-1915 Federal League Terrapins and the 1954 on Orioles; COL is
the 1883 Columbus club and the 1993 Rockies; PHA is the AA and the AL
Athletics. The league column separates them. war_daily carries a null lg_ID
for the National Association (1871-1875); this block writes it as "NA".

LINEAGE (the 30 current franchises before 1969) follows the franchise
grouping Baseball-Reference and the Lahman database both use: a franchise
begins when its club entered the National League (1876), the American
Association (1882) or the American League (1901), so a National Association
club is a club of its own and never the start of a current franchise (the
1871-1875 Boston Red Stockings are not the Braves; the 1871-1875 Chicago White
Stockings are not the Cubs). The 1901 Milwaukee Brewers start the Orioles and
the 1901-1902 Baltimore Orioles start the Yankees, as both sources have it.

DEFUNCT CLUBS are every other (team_ID, lg_ID, season) before 1969, written out
one club at a time, never left to a default. A defunct club is one team code,
split into a new club when the league family changes (nineteenth-century
majors NA/NL/AA/UA/PL, the Federal League, the seven Negro Leagues MLB
recognised in 2020) and, inside the nineteenth-century family only, when a
season is missing (the 1884 Union Association Nationals, the 1886-1889 NL
Nationals and the 1892-1899 NL Senators all read WHS). Negro Leagues codes are
never split on a gap, because the recognised seasons themselves have gaps.
MERGES then join the codes one club played under, each named below.

Deterministic. Reads war_source's last-good parquets by path; never a socket.
Run:  python tools/franchise_spine_history.py          (writes the block)
      python tools/franchise_spine_history.py --check  (exit 1 if it would move)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SPINE = ROOT / "data" / "franchise_spine.json"

FIRST = 1871
LAST = 1968

NINETEENTH = {"NA", "NL", "AA", "UA", "PL"}
FEDERAL = {"FL"}
NEGRO = {"NNL", "ECL", "ANL", "EWL", "NSL", "NN2", "NAL"}
GROUP_LABEL = {"nineteenth_century": "nineteenth-century major",
               "federal_league": "Federal League",
               "negro_leagues": "Negro Leagues"}

#: The 30 current franchises before 1969: (team_ID, lg_ID, first, last).
#: Franchises that start in 1969 or later have no entry.
LINEAGE = {
    "ATH": [("PHA", "AL", 1901, 1954), ("KCA", "AL", 1955, 1967), ("OAK", "AL", 1968, 1968)],
    "ATL": [("BSN", "NL", 1876, 1952), ("MLN", "NL", 1953, 1965), ("ATL", "NL", 1966, 1968)],
    "BAL": [("MLA", "AL", 1901, 1901), ("SLB", "AL", 1902, 1953), ("BAL", "AL", 1954, 1968)],
    "BOS": [("BOS", "AL", 1901, 1968)],
    "CHC": [("CHC", "NL", 1876, 1968)],
    "CHW": [("CHW", "AL", 1901, 1968)],
    "CIN": [("CIN", "AA", 1882, 1889), ("CIN", "NL", 1890, 1968)],
    "CLE": [("CLE", "AL", 1901, 1968)],
    "DET": [("DET", "AL", 1901, 1968)],
    "HOU": [("HOU", "NL", 1962, 1968)],
    "LAA": [("LAA", "AL", 1961, 1964), ("CAL", "AL", 1965, 1968)],
    "LAD": [("BRO", "AA", 1884, 1889), ("BRO", "NL", 1890, 1957), ("LAD", "NL", 1958, 1968)],
    "MIN": [("WSH", "AL", 1901, 1960), ("MIN", "AL", 1961, 1968)],
    "NYM": [("NYM", "NL", 1962, 1968)],
    "NYY": [("BLA", "AL", 1901, 1902), ("NYY", "AL", 1903, 1968)],
    "PHI": [("PHI", "NL", 1883, 1968)],
    "PIT": [("PIT", "AA", 1882, 1886), ("PIT", "NL", 1887, 1968)],
    "SFG": [("NYG", "NL", 1883, 1957), ("SFG", "NL", 1958, 1968)],
    "STL": [("STL", "AA", 1882, 1891), ("STL", "NL", 1892, 1968)],
    "TEX": [("WSA", "AL", 1961, 1968)],
}

#: Codes one defunct club played under. Each entry is (name, members), a member
#: being (team_ID, lg_ID, first, last) exactly as the split rule cuts it.
MERGES = [
    ("Chicago White Stockings, 1871 and 1874-1875 (no club 1872-1873 after the Chicago fire)",
     [("CHI", "NA", 1871, 1871), ("CHI", "NA", 1874, 1875)]),
    ("Baltimore Orioles, American Association 1882-1891 then National League 1892-1899",
     [("BAL", "AA", 1882, 1891), ("BLN", "NL", 1892, 1899)]),
    ("Washington Senators, American Association 1891 then National League 1892-1899",
     [("WAS", "AA", 1891, 1891), ("WHS", "NL", 1892, 1899)]),
    ("Cleveland Blues (AA 1887-1888) then Spiders (NL 1889-1899)",
     [("CLE", "AA", 1887, 1888), ("CLV", "NL", 1889, 1899)]),
    ("Indianapolis Hoosiers 1914 then Newark Peppers 1915, Federal League",
     [("IND", "FL", 1914, 1914), ("NEW", "FL", 1915, 1915)]),
    ("Elite Giants: Nashville, Columbus 1935, Washington 1936-1937, Baltimore 1938-1948",
     [("NEG", "*", 1930, 1934), ("CEG", "NN2", 1935, 1935), ("WEG", "NN2", 1936, 1937),
      ("BEG", "NN2", 1938, 1948)]),
    ("Eagles: Brooklyn 1935, Newark 1936-1948",
     [("BE", "NN2", 1935, 1935), ("NE", "NN2", 1936, 1948)]),
    ("Crawfords: Pittsburgh 1933-1938, then Toledo and Indianapolis (NAL) 1939-1940",
     [("PC", "NN2", 1933, 1938), ("TC", "NAL", 1939, 1940)]),
]


def _group(lg: str) -> str:
    if lg in NINETEENTH:
        return "nineteenth_century"
    if lg in FEDERAL:
        return "federal_league"
    if lg in NEGRO:
        return "negro_leagues"
    raise SystemExit(f"franchise_spine_history: league {lg!r} has no family; refusing")


def _rows():
    """{(team_ID, lg, season)} for every war_daily stint row before 1969."""
    import pandas as pd
    import war_source
    seen = set()
    for side in ("bat", "pit"):
        df = pd.read_parquet(war_source._cache_path(side), columns=["team_ID", "lg_ID", "year_ID"])
        df = df[df["year_ID"] <= LAST]
        for t, lg, y in zip(df["team_ID"], df["lg_ID"], df["year_ID"]):
            seen.add((str(t), "NA" if lg is None or lg != lg else str(lg), int(y)))
    return seen


def _in(iv, t, lg, y) -> bool:
    return iv[0] == t and (iv[1] == "*" or iv[1] == lg) and iv[2] <= y <= iv[3]


def build_history(seen) -> dict:
    lineage_hit = set()
    for org, ivs in LINEAGE.items():
        for t, lg, a, b in ivs:
            for key in seen:
                if _in((t, lg, a, b), *key):
                    lineage_hit.add(key)
    rest = sorted(seen - lineage_hit)
    for t, lg, y in rest:
        if lg in ("AL", "NL") and y >= 1901:
            raise SystemExit(f"franchise_spine_history: {t} {lg} {y} is a modern AL/NL season "
                             "outside every lineage interval; refusing")

    # Split each code into clubs: league family change, or a missing season
    # inside the nineteenth-century family.
    by_code = defaultdict(list)
    for t, lg, y in rest:
        by_code[t].append((y, lg))
    clubs = []
    for t, ys in sorted(by_code.items()):
        ys.sort()
        cur = None
        for y, lg in ys:
            g = _group(lg)
            if (cur is None or g != cur["group"]
                    or (g == "nineteenth_century" and y > cur["_last"] + 1)):
                cur = {"group": g, "members": [], "_last": y}
                clubs.append(cur)
            m = cur["members"]
            if m and m[-1]["team_id"] == t and m[-1]["lg"] == lg and m[-1]["last"] == y - 1:
                m[-1]["last"] = y
            elif m and m[-1]["team_id"] == t and m[-1]["lg"] == lg and m[-1]["last"] >= y:
                pass
            else:
                m.append({"team_id": t, "lg": lg, "first": y, "last": y})
            cur["_last"] = y

    # Collapse a member list into (team_id, lg, first, last) spans per code and
    # league, which is what the MERGES table names.
    def spans(c):
        out = []
        for m in c["members"]:
            if out and out[-1]["team_id"] == m["team_id"] and out[-1]["lg"] == m["lg"]:
                out[-1]["last"] = m["last"]
                out[-1]["seasons"] += m["last"] - m["first"] + 1
            else:
                out.append({**m, "seasons": m["last"] - m["first"] + 1})
        return out

    for c in clubs:
        c["members"] = spans(c)

    def covers(c, mem):
        t, lg, a, b = mem
        return any(m["team_id"] == t and (lg == "*" or m["lg"] == lg)
                   and m["first"] >= a and m["last"] <= b for m in c["members"])

    merged = []
    used = set()
    for name, members in MERGES:
        parts = []
        for mem in members:
            hit = [i for i, c in enumerate(clubs) if i not in used and covers(c, mem)]
            if not hit:
                raise SystemExit(f"franchise_spine_history: merge member {mem} matches no club; refusing")
            parts.extend(hit)
            used.update(hit)
        groups = {clubs[i]["group"] for i in parts}
        if len(groups) != 1:
            raise SystemExit(f"franchise_spine_history: merge {name!r} crosses league families")
        mm = sorted((m for i in parts for m in clubs[i]["members"]), key=lambda m: (m["first"], m["team_id"]))
        merged.append({"group": groups.pop(), "members": mm, "merge": name})
    final = [c for i, c in enumerate(clubs) if i not in used] + merged

    out = []
    for c in final:
        mm = sorted(c["members"], key=lambda m: (m["first"], m["team_id"], m["lg"]))
        first, last = min(m["first"] for m in mm), max(m["last"] for m in mm)
        codes = []
        for m in mm:
            if m["team_id"] not in codes:
                codes.append(m["team_id"])
        key = f"DEF-{mm[0]['team_id']}-{first}"
        out.append({
            "key": key,
            "label": f"{'/'.join(codes)} {first}-{last}" if first != last else f"{'/'.join(codes)} {first}",
            "group": c["group"],
            "first": first, "last": last,
            "intervals": [{"team_id": m["team_id"], "lg": m["lg"], "first": m["first"], "last": m["last"]}
                          for m in mm],
            "merge": c.get("merge"),
        })
    out.sort(key=lambda c: (c["first"], c["key"]))
    keys = [c["key"] for c in out]
    if len(keys) != len(set(keys)):
        raise SystemExit("franchise_spine_history: two defunct clubs share a key; refusing")

    return {
        "first_season": FIRST,
        "last_season": LAST,
        "key": "(team_id, lg, season); lg NA is the National Association, which war_daily carries as a null lg_ID",
        "basis": ("lineage follows the Baseball-Reference and Lahman franchise grouping (a current franchise "
                  "starts at its club's NL 1876, AA 1882 or AL 1901 entry; National Association clubs are clubs of "
                  "their own). Every other season before 1969 is a named defunct club: one team code, split at a "
                  "league-family change and, for nineteenth-century majors, at a missing season, then joined by "
                  "the named merges. Written by tools/franchise_spine_history.py from the war_daily parquets."),
        "lineage": {org: [{"team_id": t, "lg": lg, "first": a, "last": b} for t, lg, a, b in ivs]
                    for org, ivs in sorted(LINEAGE.items())},
        "defunct_bucket": "DEFUNCT",
        "defunct_groups": GROUP_LABEL,
        "defunct": out,
        "census": {"team_lg_seasons": len(seen), "to_lineage": len(lineage_hit),
                   "to_defunct": len(rest), "defunct_clubs": len(out),
                   "merges": len(MERGES)},
    }


SCOPE = ("Baseball-Reference war_daily team_ID to canonical org. `orgs` covers seasons 1969 to 2026 and keys on "
         "(team_id, season); it is the /franchise/ club bWAR line. `history` carries the map back to 1871, keyed on "
         "(team_id, lg, season), with every season before 1969 landing on one of the 30 franchises or on a named "
         "defunct club; it serves the Hall of Fame franchise credit (docs/HOF_FRANCHISE_ATTRIBUTION.md, owner "
         "answer 2026-09-25). The 2000-2026 standings join by StatsAPI team id (stable across relocations) and "
         "need no spine.")
NOT_IN_SCOPE = ["standings (joined by StatsAPI team id)",
                "the cap a Hall of Fame plaque shows (the credit is by playing WAR, not by plaque)",
                "pennants and titles"]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    raw = SPINE.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    new = dict(doc)
    new["scope"] = SCOPE
    new["not_in_scope"] = NOT_IN_SCOPE
    new["history"] = build_history(_rows())
    txt = json.dumps(new, indent=1, ensure_ascii=False) + "\n"
    if crlf:
        txt = txt.replace("\n", "\r\n")
    data = txt.encode("utf-8")
    if "--check" in argv:
        same = data == raw
        print("franchise_spine history: " + ("current" if same else "WOULD MOVE"))
        return 0 if same else 1
    SPINE.write_bytes(data)
    c = new["history"]["census"]
    print(f"wrote {SPINE.relative_to(ROOT)}: {c['team_lg_seasons']} team-league-seasons before 1969, "
          f"{c['to_lineage']} to the 30 franchises, {c['to_defunct']} to {c['defunct_clubs']} defunct clubs "
          f"({c['merges']} merges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
