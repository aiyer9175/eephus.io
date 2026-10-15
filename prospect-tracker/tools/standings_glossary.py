# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/standings_glossary.py - the Standings glossary entries and the two registry
surface amendments (STANDINGS_PLAN 5.12 'Glossary' and 7, STANDINGS_7_FLIP).

The flip commit writes, together with standings_core.STANDINGS_LIVE and STANDINGS_CHARTS:

  data/glossary.json      30 new entries, module scores: the 26 table entries of
                          STANDINGS_PLAN 5.12 (the sixteen of LANE_PRODUCT 4.3 with the
                          plan's texts for clinch_marks, magic_number, remaining_sos and
                          projected_record, plus the ten for the columns that had none)
                          and the 4 chart entries (the charts flip in the same commit).
                          xwl and w_minus_xw already exist (League Trends LT-08, Q8_15),
                          so the page links them and this script leaves them alone.
  data/model_registry.json  two SURFACE amendments, no new row: playoff_odds_sim and
                          postseason_bracket_sim each gain the /standings/ clause the plan
                          gives.

Idempotent: an entry already present with the same fields changes nothing; one whose fields
differ is replaced in place; a missing one is appended. A surface that already ends with its
clause is left alone. Each file keeps its own line endings, its one-space indent, its raw
UTF-8 and its own trailing newline (the registry has none). The glossary version stamp moves
through build_glossary_data.glossary_version() only when the glossary changes.

Run:
  python tools/standings_glossary.py            dry run: names what would change, writes nothing
  python tools/standings_glossary.py --check    exit 1 when either file would change
  python tools/standings_glossary.py --write    write (refuses while STANDINGS_LIVE is False)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"

MODULE = "scores"
SECTION = "Players & Stats"      # tools/glossary_sections.SECTION_BY_MODULE["scores"]
PRIORITY = 70
ORIGIN_MLB = "MLB, the StatsAPI standings feed; defined here for reference."
ORIGIN_SIM = "Arkmetric, original to eephus.io: the site's season simulator, and in October its bracket simulator."

#: The registry clauses, verbatim from the STANDINGS_7_FLIP specification.
SURFACE_CLAUSES = {
    "playoff_odds_sim": (
        "; /standings/ ODDS group (division, postseason, pennant and World Series chances, projected "
        "final record and remaining schedule) for the current season, copied from data/futures.json "
        "(the remaining schedule from data/mlb_projections.json; the printed projected wins rounded half "
        "up and the projected losses derived from them and the games left)"),
    "postseason_bracket_sim": (
        "; the Pennant and World Series columns of the /standings/ ODDS group during the postseason "
        "only, outside the bracket, labelled implied, no market"),
}

#: The column headers (STANDINGS_PLAN 5.3 and 5.4) and charts (5.5, C1 to C5) link the
#: ids in standings_core.HEADER_GLOSSARY and CHART_GLOSSARY; test_glossary_slugs_resolve.py
#: pins every one of them to an entry.


def entries() -> list[dict]:
    """The 30 entries, in the order the plan lists them."""
    def e(id_, term, category, aliases, definition, see, *, shelf="foundation", origin=ORIGIN_MLB,
          methodology=None):
        out = {"id": id_, "term": term, "category": category, "section": SECTION, "module": [MODULE],
               "aliases": aliases, "priority": PRIORITY, "definition": definition}
        if methodology:
            out["methodology"] = methodology
        out["seeAlso"] = see
        out["shelf"] = shelf
        out["origin"] = origin
        return out

    sim = {"shelf": "ark", "origin": ORIGIN_SIM}
    return [
        # the sixteen of LANE_PRODUCT 4.3, with the plan's four texts
        e("standings_page", "Standings", "site-feature", ["MLB standings", "Standings page"],
          "MLB's standings by division, wild card, league and the majors, with each club's record, "
          "splits and run totals from MLB's feed, and the site's simulator chances in a labelled group.",
          ["games_back", "clinch_marks", "season_sim_odds"]),
        e("games_back", "Games back (GB)", "standard-stat", ["GB", "games behind"],
          "How far a club trails the leader: the leader's wins minus the club's wins, plus the club's "
          "losses minus the leader's losses, divided by two.",
          ["wild_card_games_back", "standings_page"]),
        e("wild_card_games_back", "Wild card games back (WCGB)", "standard-stat", ["WCGB", "wild card games behind"],
          "Games back of the club holding the last wild card spot; a plus sign means the club holds a "
          "spot by that many games.",
          ["games_back", "postseason_seed"]),
        e("magic_number", "Magic number", "mlb-rules", ["MAGIC"],
          "The combination of a leader's wins and a chaser's losses that clinches. MLB's figure from its "
          "standings feed; where the feed prints none for a leader that has not clinched, the site serves "
          "the runner-up's elimination number, which is the same count.",
          ["elimination_number", "clinch_marks"]),
        e("elimination_number", "Elimination number", "mlb-rules", ["ELIM"],
          "The combination of a club's losses and the leader's wins that ends its chances; E means it "
          "already has.",
          ["magic_number", "clinch_marks"]),
        e("clinch_marks", "Clinch and elimination marks", "mlb-rules", ["clinch marks", "clinch letters"],
          "MLB's letters: x a playoff spot, y the division, z the league's best record, w a wild card "
          "spot. e is set on this site when a club carries no letter and either MLB's wild card "
          "elimination number reads E or the season is over; a division E alone is not e.",
          ["magic_number", "elimination_number", "postseason_seed"]),
        e("streak", "Streak (STRK)", "standard-stat", ["STRK", "win streak", "losing streak"],
          "Consecutive wins or losses to date, from MLB's feed: W4 is four wins in a row.",
          ["last_ten"]),
        e("last_ten", "Last 10 (L10)", "standard-stat", ["L10", "last ten", "last 10 games"],
          "The club's record over its last ten games.",
          ["streak"]),
        e("run_differential", "Run differential (RD)", "standard-stat", ["RD", "run diff"],
          "Runs scored minus runs allowed.",
          ["rd_per_game", "runs_scored", "runs_allowed"]),
        e("rd_per_game", "Run differential per game (RD/G)", "standard-stat", ["RD/G"],
          "Run differential divided by games played, so clubs with different game counts compare on one "
          "scale. Coloured by the site's ruler from 20 games.",
          ["run_differential", "xwl"]),
        e("one_run_record", "One-run record (1-RUN)", "standard-stat", ["1-RUN", "one-run games"],
          "Record in games decided by one run.",
          ["extra_inning_record"]),
        e("extra_inning_record", "Extra-inning record (XTRA)", "standard-stat", ["XTRA", "extra innings record"],
          "Record in games that went past nine innings.",
          ["one_run_record"]),
        e("record_vs_winning", "Record against clubs over .500", "standard-stat", [">.500", "record against winning clubs"],
          "Record in games against clubs with a winning record, as MLB's feed counts them.",
          ["win_pct"]),
        e("remaining_sos", "Strength of remaining schedule (SOS)", "methodology", ["SOS", "strength of schedule", "SOS rank"],
          "The average talent rating of the opponents a club has left to play, each rated as a win rate "
          "from the season simulator's roster ratings (the site's projected win total over 162 games), not "
          "by their record. Rank 1 is the hardest schedule left. Shown only while the club has games left "
          "in the regular season.",
          ["season_sim_odds", "games_left"], **sim),
        e("season_sim_odds", "Simulator chances", "methodology", ["DIV%", "POST%", "PEN%", "WS%", "standings odds"],
          "Each club's chance to win its division, reach the postseason, win the pennant and win the World "
          "Series, from the site's season simulator (and in October its bracket simulator). Implied, with "
          "no market; its status is printed beside it.",
          ["projected_record", "postseason_bracket_sim", "odds_over_time_chart"], **sim),
        e("projected_record", "Projected final record (PROJ)", "methodology", ["PROJ", "projected final record"],
          "The season simulator's projected final record: its projected wins rounded half up, and the games "
          "left over as losses, with games played banked. Blank when the projection on file was built on a "
          "different W-L than this row; the tooltip names both.",
          ["season_sim_odds", "games_left"], **sim),
        # ten for the columns that had none
        e("win_pct", "Winning percentage (PCT)", "standard-stat", ["PCT", "winning percentage", "win percentage"],
          "Wins divided by wins plus losses, to three decimals; ties are not counted.",
          ["season_record", "pythag_pct"]),
        e("runs_scored", "Runs scored (RS)", "standard-stat", ["RS"],
          "Runs the club has scored this season, from MLB's feed. The runs chart plots them per game.",
          ["runs_allowed", "run_differential"]),
        e("runs_allowed", "Runs allowed (RA)", "standard-stat", ["RA"],
          "Runs the club has allowed this season, from MLB's feed. The runs chart plots them per game.",
          ["runs_scored", "run_differential"]),
        e("home_away_record", "Home and road record (HOME, AWAY)", "standard-stat", ["HOME", "AWAY", "home record", "road record"],
          "Record in games at the club's home park and in games on the road.",
          ["season_record"]),
        e("division_record", "Division record (DIV)", "standard-stat", ["DIV", "record against the division"],
          "Record against the other clubs of the club's own division.",
          ["league_record"]),
        e("league_record", "League record (LG)", "standard-stat", ["LG", "record against the league"],
          "Record against every club in the club's own league, its division included.",
          ["division_record", "interleague_record"]),
        e("interleague_record", "Interleague record (INTR)", "standard-stat", ["INTR"],
          "Record against clubs of the other league.",
          ["league_record"]),
        e("vs_hand_record", "Record against left- and right-handed starters (vs L, vs R)", "standard-stat",
          ["vs L", "vs R", "record against left-handed starters", "record against right-handed starters"],
          "Record in games started by a left-handed or a right-handed opposing pitcher, as MLB's feed "
          "counts them.",
          ["season_record"]),
        e("games_left", "Games left (LEFT)", "standard-stat", ["LEFT", "games remaining"],
          "Regular-season games still on MLB's schedule for the club. A postponed game counts once it is "
          "rescheduled; it reads 0 once the regular season is over.",
          ["magic_number", "projected_record"]),
        e("postseason_seed", "Postseason seed (SEED)", "mlb-rules", ["SEED", "playoff seed"],
          "The club's postseason seed in its league, in MLB's order: division winners first, then the wild "
          "cards (in 2020, division winners, then division runners-up, then the wild cards). During the "
          "season it is the seed the club would hold if the season ended on the stamped date; blank for a "
          "club outside the field.",
          ["clinch_marks", "wild_card_games_back"]),
        # the four chart entries (the charts flip in the same commit)
        e("division_race_chart", "Division race chart", "site-feature", ["division race"],
          "Each club's wins minus losses after every date of the season, one panel per division.",
          ["games_back", "season_record"]),
        e("wild_card_race_chart", "Wild card race chart", "site-feature", ["wild card race"],
          "Each club's games ahead of or behind the club holding the last wild card spot on every date; "
          "division leaders of that date are left out.",
          ["wild_card_games_back"]),
        e("odds_over_time_chart", "Odds over time chart", "site-feature", ["odds over time"],
          "The site's simulator chances on every day they were recorded, held flat between records. "
          "Implied, with no market.",
          ["season_sim_odds"], **sim),
        e("expected_record_chart", "Record against expected record chart", "site-feature", ["record against expected record"],
          "Each club's wins beside the wins its runs scored and allowed imply.",
          ["xwl", "w_minus_xw"]),
    ]


def apply_glossary(doc: dict, new: list[dict] | None = None) -> tuple[dict, list[str]]:
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


def apply_registry(doc: dict) -> tuple[dict, list[str]]:
    out = dict(doc)
    rows = [dict(m) for m in doc["models"]]
    changed = []
    for m in rows:
        clause = SURFACE_CLAUSES.get(m["model_id"])
        if clause and not str(m.get("surface") or "").endswith(clause):
            m["surface"] = str(m.get("surface") or "") + clause
            changed.append(f"surface {m['model_id']}")
    missing = set(SURFACE_CLAUSES) - {m["model_id"] for m in rows}
    if missing:
        raise SystemExit(f"registry rows missing: {sorted(missing)}")
    out["models"] = rows
    return out, changed


def _read(path: Path):
    raw = path.read_bytes()
    return raw, b"\r\n" in raw, raw.endswith(b"\n"), json.loads(raw.decode("utf-8"))


def _dump(doc: dict, crlf: bool, nl: bool) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=False) + ("\n" if nl else "")
    return (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")


def main(argv: list[str]) -> int:
    _, g_crlf, g_nl, gdoc = _read(GLOSSARY)
    _, r_crlf, r_nl, rdoc = _read(REGISTRY)
    gnew, gch = apply_glossary(gdoc)
    rnew, rch = apply_registry(rdoc)
    changed = gch + rch
    if not changed:
        print("standings glossary and registry: no change")
        return 0
    if "--write" not in argv:
        print("standings glossary and registry: would " + "; ".join(changed))
        return 1 if "--check" in argv else 0
    import standings_core
    if not standings_core.STANDINGS_LIVE:
        print("standings glossary: refused; standings_core.STANDINGS_LIVE is False (STANDINGS_7_FLIP writes these)")
        return 2
    if gch:
        from build_glossary_data import glossary_version
        gnew["version"] = glossary_version()
        GLOSSARY.write_bytes(_dump(gnew, g_crlf, g_nl))
    if rch:
        REGISTRY.write_bytes(_dump(rnew, r_crlf, r_nl))
    print(f"standings glossary and registry: {len(changed)} changes written ({', '.join(changed)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
