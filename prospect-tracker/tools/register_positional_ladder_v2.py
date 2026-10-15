# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Register the positional ladder v2 read (docs/ewar/LADDER_V2_GATE.md) in
data/model_registry.json and data/glossary.json (idempotent).

Registry: adds the positional_ladder_v2 row and re-points the positional_ladder
(v1) row's surface, since Position Fit now values with v2 while DEM+ and the
ladder export keep v1. Glossary: adds the positional_ladder and position_fit
entries the /pal/ page has linked to (data-gl) without an entry, and updates
the positional_adjustment entry, whose "Pos (ours)" is still v1.

Every figure below is the one read's (data/positional_ladder_v2_eval.json,
2026-10-15) and does not move: the read ran once. Each file keeps its own line
endings, indent and ASCII setting; the script refuses when a plain round trip
would rewrite either file. Running it twice changes nothing. Then:

    python tools/register_positional_ladder_v2.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
GLO = ROOT / "data" / "glossary.json"

V2_ROW = {
    "model_id": "positional_ladder_v2",
    "summary": ("Validated: switchers' held-out fielding plus positional runs, 0.886 runs per 650 PA "
                "lower error than the Baseball-Reference inversion (CI95 0.717 to 1.059), all three sources."),
    "surface": ("The /pal/ Position Fit board (the ladder it values positions with) and the Library's "
                "Positional Ladder view; eWAR, DEM+, eFV and the projection model do not read it"),
    "predicts": ("The positional adjustment in runs per 650 PA: the fielding runs the same players gain or "
                 "lose when they change position, relative to the exposure-weighted average defensive position"),
    "champion": ("position-switcher network ladder (ladder_v2.py): per fielding source (Baseball-Reference "
                 "runs_field, FanGraphs fld, Statcast FRP) a WLS of next-season fielding runs on last season's "
                 "rate, age and the change in innings shares, plus Statcast same-season pairs; sources pooled by "
                 "inverse variance; DH = 1B + the 1B rate of DH-type seasons; C carried from v1 (13 C-switcher "
                 "rows, under the gate's 30); seasons 2016 to 2026"),
    "baseline": ("v1, the Baseball-Reference runs_position inversion (positional_ladder), refit on the same "
                 "training seasons in each fold; the served v1 vector, the FanGraphs inversion, the published "
                 "FanGraphs table and an offense-equalizing ladder as references"),
    "metric": ("Leave-one-season-out 2016 to 2026: weighted MAE of switchers' fielding plus positional runs per "
               "650 PA (adjacent-season rows on three sources and Statcast same-season pairs); pass iff the "
               "dMAE CI95 lower bound is above zero, player-cluster bootstrap B 2000, seed 20261015"),
    "eval_artifact": "data/positional_ladder_v2_eval.json",
    "verdict": "validated",
    "notes": (
        "Registered 2026-10-15 in docs/ewar/LADDER_V2_GATE.md (task EWAR_LADDER_REDERIVE, owner decision EW3-25), "
        "committed alone before any number; amended once before the read (A1 to A4: the registered across-season "
        "equation flattened any ladder on fixtures built with runs centred within position, as every real source is, "
        "so it was replaced by the persistence form that recovers a planted ladder, and the scoring predictor with it). "
        "Read once 2026-10-15: pooled dMAE +0.886 runs per 650 PA against the v1 refit (CI95 +0.717 to +1.059, "
        "4,141 rows, 611 players); the EW3-23 next-season form +0.754 (+0.587 to +0.928); lower on Baseball-Reference "
        "(+0.433), FanGraphs (+0.709) and Statcast (+1.343) rows and in 11 of 11 held-out seasons. The per-season "
        "shrunk version did not beat the pooled one (-0.026, -0.055 to +0.003), so the pooled 2016 to 2026 fit serves: "
        "C +10.19, CF +1.42, LF +0.62, SS +0.33, RF +0.32, 3B -2.11, 2B -2.12, 1B -3.37, DH -6.48 (exposure-weighted "
        "zero). Among fielders it is much flatter than the Baseball-Reference inversion (SS +9.38, 1B -8.40). "
        "Position Fit composes it on one run scale (gate part 8): an average glove is worth the same at every fielding "
        "position. Not in eWAR (EWAR_V3_ASSEMBLE decides that under its own gate); DEM+ keeps v1."
    ),
    "last_checked": "2026-10-15",
    "stale": False,
    "artifact_age_days": 0,
}

V1_SURFACE_OLD = "Prospect defensive value and the /pal/ Position Fit board; eFV and the projection model do not read it"
V1_SURFACE_NEW = ("Prospect defensive value, the Defense board's Pos (ours) and the published ladder export; the /pal/ "
                  "Position Fit board reads positional_ladder_v2 since 2026-10-15; eFV and the projection model do not read it")
V1_NOTE_ADD = (" SUPERSEDED ON POSITION FIT 2026-10-15 (docs/ewar/LADDER_V2_GATE.md): the position-switcher ladder "
               "(positional_ladder_v2) predicted switchers' held-out fielding plus positional runs better than this "
               "inversion refit on the same seasons, so Position Fit values with v2; this row's ladder is still "
               "data/positional_fit.json fit.ladder, carried unrefit, for DEM+ and the export.")

GL_LADDER = {
    "id": "positional_ladder",
    "term": "Positional ladder",
    "category": "custom-index",
    "section": "Players & Stats",
    "module": ["pal"],
    "aliases": ["switcher ladder", "position-switcher ladder", "ladder v2"],
    "priority": 40,
    "definition": ("The runs a position is worth against the average defensive position, per 650 plate "
                   "appearances, measured on players who changed position: the fielding runs the same player "
                   "gains or loses when he moves. Position Fit in the Alchemy Lab values positions with it."),
    "methodology": (
        "Three fielding sources, each fit on its own: Baseball-Reference fielding runs, FanGraphs fielding runs "
        "(framing excluded) and Statcast fielding runs prevented, with innings by position from MLB StatsAPI, "
        "seasons 2016 to 2026. For a player with 300 or more fielded innings in two straight seasons, his "
        "fielding runs per 650 PA of innings are fit on last season's rate, his age and the change in where he "
        "played; players who stayed put set the persistence and aging terms, players who moved set the gaps "
        "between positions. Statcast also adds same-season pairs (150 or more innings at two positions). The "
        "three ladders are averaged position by position, each weighted by its precision. Catcher keeps the "
        "Baseball-Reference rung, because too few catchers change position to measure one; DH is first base "
        "plus the first-base fielding of the players who DH.\n\n"
        "It replaced the ladder recovered by inverting Baseball-Reference's positional runs after one "
        "registered read on 2026-10-15, its rules fixed before any number: "
        "predicting the fielding plus positional runs of players who changed position in held-out seasons, "
        "its error was 0.886 runs per 650 PA lower (95% CI 0.717 to 1.059), on each of the three sources. "
        "Among fielders it is much flatter than Baseball-Reference's: shortstop sits 3.7 runs above first "
        "base, not 17.8. It is not in eWAR, and the Defense board's Pos (ours) still uses the "
        "Baseball-Reference inversion. The Library's Positional Ladder view has the full table."
    ),
    "formula": ("per source: r_t = a + b x (age - 27) + k x r_(t-1) + sum over positions of "
                "(share_t - share_(t-1)) x D_p, plus Statcast r_b - r_a = D_b - D_a; ladder_p = -D_p; "
                "sources pooled by inverse variance; DH = ladder(1B) + mean 1B rate of DH-type seasons; "
                "zero = the exposure-weighted average defensive position"),
    "example": ("A shortstop moved to first base gives up 3.7 runs per 650 PA of positional value on this "
                "ladder, about the fielding runs the same players gained on that move."),
    "seeAlso": ["positional_adjustment", "position_fit", "pal_conversion"],
    "shelf": "ark",
    "origin": "Arkmetric, original to eephus.io, measured on position switchers from Baseball-Reference, FanGraphs and Statcast fielding runs.",
}

GL_POSFIT = {
    "id": "position_fit",
    "term": "Position fit",
    "category": "custom-index",
    "section": "Players & Stats",
    "module": ["pal"],
    "aliases": ["positional conversion", "misplaced hitters"],
    "priority": 36,
    "definition": ("Which hitters are worth more runs at a different position, per 650 plate appearances: "
                   "the bat plus the fielding at that position plus the positional ladder. The bat is the "
                   "same everywhere, so fielding and the ladder decide. A valuation of where a hitter fits, "
                   "not a forecast of where his club puts him."),
    "methodology": (
        "The glove is read from Statcast fielding runs prevented over up to three seasons, shrunk per position "
        "by how reliable a season is there, and carried to a new position through the difficulty Statcast "
        "measures on players who play two positions in a season; that part predicts the size of a move. In "
        "the value, the ladder and the difficulty share one run scale (since 2026-10-15): an average glove is "
        "worth the same at every fielding position, so a move between two fielding positions is priced by the "
        "player's glove alone, and only a move to DH carries a league-wide part. Before, the two came from "
        "different run scales and an average glove gained or lost up to 13.6 runs on a move (left field "
        "-7.51 against third base +6.06). A hitter is flagged when the gain clears 3 runs per 650 PA and one "
        "standard error. The demotion backtest, how well the read ranks the hitters clubs moved down the next "
        "season, is a check inside the model's artifact, not a registered gate; the page prints its result."
    ),
    "formula": ("value at a fielding position p = bat + mean of the seven Statcast-position rungs + s(p) x "
                "glove z x innings per 650 PA / 1,000; value at DH = bat + ladder(DH); gain = value(best) - "
                "value(now); flag: gain >= 3 runs per 650 PA and >= 1 standard error"),
    "seeAlso": ["positional_ladder", "rng_plus", "pal_conversion"],
    "shelf": "ark",
    "origin": "Arkmetric, original to eephus.io.",
}

PA_OLD = ("Pos (ours) is Position Fit's fitted ladder, in runs per 650 plate appearances and inverted from "
          "Baseball-Reference's positional runs,")
PA_NEW = ("Pos (ours) is the site's v1 ladder, in runs per 650 plate appearances and inverted from "
          "Baseball-Reference's positional runs (Position Fit itself values positions with the position-switcher "
          "ladder since 2026-10-15; see Positional ladder),")
PA_ORIGIN_OLD = "Pos (ours) is the site's Position Fit ladder, computed here;"
PA_ORIGIN_NEW = "Pos (ours) is the site's v1 ladder, computed here;"


def _render(doc, raw: bytes, ensure_ascii: bool) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=ensure_ascii)
    crlf = b"\r\n" in raw
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def _load(path: Path):
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    for ea in (False, True):
        if _render(doc, raw, ea) == raw:
            return doc, raw, ea
    raise SystemExit(f"refusing: a plain round trip would rewrite {path.name}")


def registry() -> str:
    doc, raw, ea = _load(REG)
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    v1 = by_id["positional_ladder"]
    if v1["surface"] == V1_SURFACE_OLD:
        v1["surface"] = V1_SURFACE_NEW
    if V1_NOTE_ADD.strip() not in v1["notes"]:
        v1["notes"] = v1["notes"] + V1_NOTE_ADD
    cur = by_id.get(V2_ROW["model_id"])
    if cur is not None:
        rows[rows.index(cur)] = dict(V2_ROW)
    else:
        rows.insert(rows.index(v1) + 1, dict(V2_ROW))
    out = _render(doc, raw, ea)
    if out == raw:
        return "registry unchanged"
    REG.write_bytes(out)
    return "registry written"


def glossary() -> str:
    doc, raw, ea = _load(GLO)
    ents = doc["entries"]
    by_id = {e["id"]: e for e in ents}
    pa = by_id["positional_adjustment"]
    if PA_OLD in pa["methodology"]:
        pa["methodology"] = pa["methodology"].replace(PA_OLD, PA_NEW)
    if PA_ORIGIN_OLD in pa["origin"]:
        pa["origin"] = pa["origin"].replace(PA_ORIGIN_OLD, PA_ORIGIN_NEW)
    at = ents.index(pa)
    for entry in (GL_POSFIT, GL_LADDER):
        cur = by_id.get(entry["id"])
        if cur is not None:
            ents[ents.index(cur)] = dict(entry)
        else:
            ents.insert(at + 1, dict(entry))
    out = _render(doc, raw, ea)
    if out == raw:
        return "glossary unchanged"
    GLO.write_bytes(out)
    return "glossary written"


def main() -> int:
    for t in (V2_ROW, GL_LADDER, GL_POSFIT):
        blob = json.dumps(t, ensure_ascii=False)
        if chr(0x2014) in blob or chr(0x2013) in blob:
            raise SystemExit("refusing: a dash in the registration text")
    print(registry())
    print(glossary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
