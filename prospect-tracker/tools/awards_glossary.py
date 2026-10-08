# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/awards_glossary.py - the Awards glossary entries (AWARDS_PLAN 4.10 'Registry and
glossary'; LANE_PRODUCT 4.7's drafts with the plan's changes).

AWARDS_8 drafts the fourteen entries here and commits the script with a dry-run test;
AWARDS_11_FLIP_RENAME is the one task that writes them, in the flip commit, after it sets
awards_core.AWARDS_LIVE to True. While the flag is False data/glossary.json carries no
awards entry (AWARDS_PLAN 3 'The flag', row I13), so --write refuses.

The entries: module hof, so tools/glossary_sections.py files them on the Hall of Fame
shelf; every number in a definition is read from awards_core (floors, ballot lengths and
points, the rookie limits, the replacement-wins constant, the dark projection season) or
from efv_vintage_frame's reserved frames, never typed. Changes from LANE_PRODUCT 4.7:
rookie_proxy and sl_prospect_expectation read as AWARDS_PLAN 4.10 writes them, the race
strip says what the race is (AWARDS_PLAN 4.6 and 8 C8: the order among the three on
realized WPA through 2026, the place on the rule from 2027), rule_and_vote prints no
count of matches (C11), and the three superlative entries carry the data lane's
definitions.

Idempotent: an entry already present with the same fields changes nothing; one whose
fields differ is replaced in place; a missing one is appended. When the payload changes
the version stamp moves through build_glossary_data.glossary_version(). The file keeps
its own line endings, its one-space indent and its raw UTF-8.

Run:
  python tools/awards_glossary.py            dry run: names what would change, writes nothing
  python tools/awards_glossary.py --check    exit 1 when data/glossary.json would change
  python tools/awards_glossary.py --write    write (AWARDS_11 only: refuses while the flag is False)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
GLOSSARY = ROOT / "data" / "glossary.json"

MODULE = "hof"
SECTION = "Hall of Fame"
PRIORITY = 35


def _ids() -> tuple:
    return ("eephus_selection", "awards_rule_mvp", "awards_rule_cy", "awards_rule_roy",
            "awards_rule_moy", "rookie_proxy", "bbwaa_ballot", "award_race_strip",
            "finalist_comparison", "rule_and_vote", "my_ballot", "sl_prospect_expectation",
            "sl_preseason_projection", "sl_next_season_change")


def _points(rule: dict) -> str:
    return ", ".join(str(p) for p in rule["points"])


def entries() -> list[dict]:
    """The fourteen entries, every number from awards_core or the reserved frames."""
    import awards_core as A

    G = A.FULL_SEASON_GAMES
    mvp_pa, mvp_ip = math.ceil(A.MVP_PA_PER_GAME * G), math.ceil(A.MVP_IP_PER_GAME * G)
    cy_ip = math.ceil(A.CY_IP_PER_GAME * G)
    B = A.BALLOT_RULES
    frames = A.reserved_frames()
    import efv_vintage_frame as V
    lv = sorted(int(y) for y in V.RESERVED_LV)
    lv_text = " and ".join(str(y) for y in lv)
    dark = min(A.PROJ_DARK_SEASONS)
    import awards_rookies as R
    import calendar
    cap = f"{calendar.month_name[R.SEASON_CAP[0]]} {R.SEASON_CAP[1]}"
    rookie = (f"The site's test for rookie status: MLB's at-bat and innings limits from prior "
              f"seasons, and an estimate of MLB's {A.ROOKIE_PROXY_DAYS_MAX}-day active-roster limit "
              f"built from MLB's transaction log until the site measures service time.")

    def e(id_, term, category, aliases, definition, methodology, see, shelf="foundation", origin=None):
        out = {"id": id_, "term": term, "category": category, "section": SECTION, "module": [MODULE],
               "aliases": aliases, "priority": PRIORITY, "definition": definition}
        if methodology:
            out["methodology"] = methodology
        out["seeAlso"] = see
        out["shelf"] = shelf
        if origin:
            out["origin"] = origin
        return out

    rules = ["awards_rule_mvp", "awards_rule_cy", "awards_rule_roy", "awards_rule_moy"]
    return [
        e("eephus_selection", "The eephus selection", "site-feature",
          ["eephus selection", "the eephus selection", "Awards selection"],
          "The site's Top 3 for an MLB award, chosen by a rule published on the Awards page: one metric "
          "family, one frame, one playing-time floor and one tie rule per award. Frozen after the regular "
          "season, before the writers' results. Not a forecast of the vote.",
          "Before the freeze the cards read 'Current leaders on the rule'. The freeze runs once, on the "
          "exporter's first run after the regular season's last game, into a write-once record; later "
          "changes to the site's WAR show beside the frozen value as 'Now' and never move the order. The "
          "WAR it reads is the series the site displays, named on every card.",
          rules + ["rule_and_vote"]),
        e("awards_rule_mvp", "MVP rule", "method", ["MVP rule", "Most Valuable Player rule"],
          "The published rule behind the eephus selection for Most Valuable Player: in-league eWAR, "
          "batting plus pitching, summed before rounding.",
          f"Floor: in-league PA of at least {mvp_pa} or IP of at least {mvp_ip} in a {G}-game season "
          f"({A.MVP_PA_PER_GAME} PA and {A.MVP_IP_PER_GAME} IP per scheduled game). Ties: the unrounded "
          f"score, then in-league WPA, then MLBAM id. A player traded across leagues is a candidate in "
          f"each league with that league's share only, and both shares print on his row.",
          ["eephus_selection", "ewar", "bbwaa_ballot"]),
        e("awards_rule_cy", "Cy Young rule", "method", ["Cy Young rule"],
          "The published rule behind the eephus selection for the Cy Young Award: in-league pitching "
          "eWAR, which prices pitching on FIP.",
          f"Floor: in-league IP of at least {cy_ip} in a {G}-game season ({A.CY_IP_PER_GAME} IP per "
          f"scheduled game), so relievers stay eligible. Ties: the unrounded score, then in-league IP, "
          f"then SEM+ for a starter or REM+ for a reliever, then MLBAM id.",
          ["eephus_selection", "ewar", "sem_plus", "rem_plus"]),
        e("awards_rule_roy", "Rookie of the Year rule", "method", ["Rookie of the Year rule", "ROY rule"],
          "The published rule behind the eephus selection for Rookie of the Year: in-league eWAR, both "
          "sides, among players who pass the site's rookie test.",
          f"Floor: PA of at least {A.ROY_MIN_PA} or IP of at least {A.ROY_MIN_IP} in the season. "
          f"Rookie test: at most {A.ROOKIE_PRIOR_AB_MAX} career AB and {A.ROOKIE_PRIOR_IP_MAX:g} career "
          f"IP through the prior season, and at most {A.ROOKIE_PROXY_DAYS_MAX} estimated active days; "
          f"a player removed by the days estimate alone is listed under the card with his days.",
          ["eephus_selection", "rookie_proxy", "ewar"]),
        e("awards_rule_moy", "Manager of the Year rule", "method", ["Manager of the Year rule", "MOY rule"],
          "The published rule behind the eephus selection for Manager of the Year: the club-season's "
          "wins above the club's own earned eWAR. The agent is the club-season; manager names join when "
          "the manager ledger lands.",
          f"Score: W minus ({A.REPLACEMENT_WINS} plus the club's earned eWAR) times games played over "
          f"{G}, with no floor, so a losing club can lead. It splits into W minus Pythagorean wins and "
          f"Pythagorean wins minus the eWAR line, printed beside the score. The decision values on "
          f"In-Game Management are realized value, not skill, and are never summed across families.",
          ["eephus_selection", "ewar", "realized_mwpa"]),
        e("rookie_proxy", "Rookie proxy", "method", ["rookie test", "rookie proxy", "45-day estimate"],
          rookie,
          f"At-bats and innings come from MLB's season lines through the prior season. The days count "
          f"open on a selection, purchase, recall, reinstatement or activation to an MLB club and close on "
          f"an injured list placement, option, outright, designation, release, trade, waiver claim, "
          f"assignment, free agency, suspension or retirement, counted only from Opening Day to "
          f"{cap}.",
          ["awards_rule_roy"]),
        e("bbwaa_ballot", "BBWAA ballot", "mlb-rules", ["BBWAA ballot", "writers' ballot"],
          f"The writers' award ballot: 30 voters per league, two per city. MVP lists {B['MVP']['n']} "
          f"places ({_points(B['MVP'])} points), Cy Young {B['CY']['n']} ({_points(B['CY'])}), Rookie "
          f"and Manager {B['ROY']['n']} each ({_points(B['ROY'])}). Ballots are due before the "
          f"postseason, so the vote covers the regular season.",
          None, ["my_ballot", "eephus_selection"], shelf="industry",
          origin="The Baseball Writers' Association of America, which votes the four awards."),
        e("award_race_strip", "Race strip", "site-feature", ["race strip", "the race"],
          "Where each of the three finalists stood week by week, drawn as lamps: tall for 1st, middle for "
          "2nd, short for 3rd. Through the 2026 season it is their order among the three on realized win "
          "probability added, which is not the selection metric; from 2027 it is the place on the "
          "selection rule among every eligible player, from the site's nightly snapshots. Weeks with no "
          "record are marked, never filled in.",
          None, ["eephus_selection", "wpa"]),
        e("finalist_comparison", "Compare the three", "site-feature",
          ["Compare the three", "finalist comparison"],
          "The three finalists on each metric's own value ruler, with the numbers beside them.",
          None, ["value_ruler", "eephus_selection"]),
        e("rule_and_vote", "Rule and vote", "site-feature", ["Rule and vote"],
          "The eephus selection beside the writers' result, season by season. A record of both lists; "
          "it scores neither.",
          "Winners come from MLB's public StatsAPI awards feed. Seasons before the site published a "
          "selection are computed after the fact by the same rule from the same files and say so.",
          ["eephus_selection", "bbwaa_ballot"]),
        e("my_ballot", "My Ballot", "site-feature", ["My Ballot", "ballot"],
          "Your own ballot for each award, with the BBWAA places and points and the site's statistics "
          "beside every candidate. Kept in your browser only; share it as a link or an image.",
          None, ["bbwaa_ballot"]),
        e("sl_prospect_expectation", "Former prospects against the grade at debut", "method",
          ["prospects against expectation", "grade at debut"],
          f"Former prospects against their grade at debut: where a player's season eWAR places him in "
          f"the pool beside where his eFV at debut placed him. Open to debut seasons before "
          f"{frames['lv_first']}: the site holds out the {lv_text} prospect list vintages, whose players "
          f"debut in {frames['lv_first']} or later, and the debut cohorts from {frames['vm_first']} for "
          f"registered checks of eFV, and each opens once its check is recorded.",
          f"Both places are mid-rank percentiles inside the season's pool, ties shared; the pool is "
          f"players with PA of at least {A.SL_MIN_PA} or IP of at least {A.SL_MIN_IP} and an eFV at "
          f"debut. One player at a time: nothing is averaged or counted by grade band. Rows at eFV "
          f"{A.EFV_FLOOR:g} carry 'graded at the floor'.",
          ["xfv", "ewar"]),
        e("sl_preseason_projection", "Against the preseason projection", "method",
          ["preseason projection", "against the projection"],
          f"Season WAR minus the WAR projected for the season in the projection file frozen the day "
          f"before Opening Day, one player at a time, with that file's P10 to P90 band beside it. No "
          f"file was saved before the {dark} season, so the card is dark for {dark}; from {dark + 1} it "
          f"reads the frozen file once that season's registered checks are recorded.",
          None, ["ewar", "sl_next_season_change"]),
        e("sl_next_season_change", "Projected change for next season", "method",
          ["projected rise", "projected drop", "next season change"],
          "The projections engine's WAR for next season minus the season's realized WAR on the same WAR "
          "series, one player at a time, naming the projections build it read. The engine's path pulls "
          "unusual seasons back toward a player's longer record, so both lists are mostly that.",
          None, ["ewar", "sl_preseason_projection"]),
    ]


def apply(doc: dict, new: list[dict] | None = None) -> tuple[dict, list[str]]:
    """(the payload with the entries in place, [what changed]); `doc` is not modified."""
    new = entries() if new is None else new
    out = dict(doc)
    rows = [dict(x) for x in doc["entries"]]
    at = {x["id"]: i for i, x in enumerate(rows)}
    changed = []
    for ent in new:
        if ent["id"] in at:
            if rows[at[ent["id"]]] != ent:
                rows[at[ent["id"]]] = dict(ent)
                changed.append(f"update {ent['id']}")
        else:
            rows.append(dict(ent))
            at[ent["id"]] = len(rows) - 1
            changed.append(f"add {ent['id']}")
    out["entries"] = rows
    return out, changed


def dump(doc: dict, crlf: bool) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    return (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")


def main(argv: list[str]) -> int:
    raw = GLOSSARY.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    new, changed = apply(doc)
    if not changed:
        print("awards glossary: no change")
        return 0
    if "--write" not in argv:
        print("awards glossary: would " + "; ".join(changed))
        return 1 if "--check" in argv else 0
    import awards_core as A
    if not A.AWARDS_LIVE:
        print("awards glossary: refused; awards_core.AWARDS_LIVE is False (AWARDS_11 writes these)")
        return 2
    from build_glossary_data import glossary_version
    new["version"] = glossary_version()
    GLOSSARY.write_bytes(dump(new, crlf))
    print(f"awards glossary: {len(changed)} entries written ({', '.join(changed)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
