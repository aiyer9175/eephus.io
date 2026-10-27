# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Register the positional ladder v2 read (docs/ewar/LADDER_V2_GATE.md) and its
verification in data/model_registry.json and data/glossary.json (idempotent).

History. EWAR_LADDER_REDERIVE (2026-10-15) wrote the positional_ladder_v2 row
as validated and re-pointed Position Fit to it. The same day LADDER_V2_REVERT
(owner decision EW3-29) checked the read: on its own scoring an all-zero
fielding ladder scores as well as v2 (tools/ladder_v2_verify.py,
data/positional_ladder_v2_verify.json). This script now writes the reverted
state, from either earlier state:

  - positional_ladder_v2: provisional, measured_not_adopted, with a
    remeasure_pending line that says refuted pending re-read; the read's notes
    are kept and the verification is appended. Nothing serves it.
  - positional_ladder (v1): its surface names the /pal/ Position Fit board
    again; the 2026-10-15 superseded note stays as history and a restored note
    follows it.
  - glossary: positional_ladder describes the served v1 ladder and v2's state;
    positional_adjustment's Pos (ours) wording is put back; position_fit (the
    one-run-scale composition, which stays) is unchanged.

The verification figures are read from data/positional_ladder_v2_verify.json
when this runs, never typed. Each file keeps its own line endings, indent and
ASCII setting; the script refuses when a plain round trip would rewrite either
file. Running it twice changes nothing. Then:

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
VERIFY = ROOT / "data" / "positional_ladder_v2_verify.json"
V3_EVAL = ROOT / "data" / "positional_ladder_v3_eval.json"


def _f(x, nd=3, sign=False):
    s = f"{float(x):+.{nd}f}" if sign else f"{float(x):.{nd}f}"
    return s


def _verify() -> dict:
    """The figures every text below quotes, from the verification record."""
    v = json.loads(VERIFY.read_text(encoding="utf-8"))
    z = v["zero_ladder"]
    zb = z["tests"]["zero_minus_b"]
    v1z = z["tests"]["v1_minus_zero"]
    sc = v["savant_centring"]
    rate = sc["savant_league_rate_per_1277_7_inn"]
    cen = sc["scoring_with_savant_centred_tests"]["zero_minus_b_centred"]
    legs = v["bridges"]["legs"]
    span = v["bridges"]["span"]["BREF"]["infield_share"]
    big = span["bins"][-1]
    cov = v["rung_coverage"]["by_source"]["BREF"]["C"]
    return {
        "zb": _f(zb["dmae"]), "zb_lo": _f(zb["ci95"][0], sign=True), "zb_hi": _f(zb["ci95"][1]),
        "zb_lo_s": _f(zb["ci95"][0]),
        "v1z": _f(v1z["dmae"]), "v1z_lo": _f(v1z["ci95"][0]), "v1z_hi": _f(v1z["ci95"][1]),
        "mae_b": _f(z["mae_pooled"]["b"]), "mae_zero": _f(z["mae_pooled"]["zero"]),
        "mae_v1": _f(z["mae_pooled"]["v1"]),
        "b_best": z["b_scale_at_lowest_mae"],
        "cf": _f(rate["CF"]["pooled_2016_2026"], 2, True), "lf": _f(rate["LF"]["pooled_2016_2026"], 2, True),
        "rf": _f(rate["RF"]["pooled_2016_2026"], 2, True),
        "cen": _f(cen["dmae"]), "cen_lo": _f(cen["ci95"][0]), "cen_hi": _f(cen["ci95"][1]),
        "cfss_bref": _f(legs["BREF"]["CF_minus_SS"], 2, True), "cfss_fg": _f(legs["FG"]["CF_minus_SS"], 2, True),
        "cfss_sav": _f(legs["SAVANT"]["CF_minus_SS"], 2, True),
        "cfss_savc": _f(legs["SAVANT_centred"]["CF_minus_SS"], 2, True),
        "big_rows": big["rows"], "big_share": f"{100 * big['information_share']:.0f}",
        "span_rows": span["rows"], "c_rows": cov["rows_c_change_025"],
        "n_rows": zb["n_rows"], "n_players": zb["n_players"],
    }


def v2_texts(x: dict) -> dict:
    summary = (f"Refuted pending re-read: beat the Baseball-Reference inversion, but an all-zero fielding "
               f"ladder scores within {x['zb']} runs per 650 PA (CI95 {x['zb_lo_s']} to {x['zb_hi']}). "
               f"Not served.")
    pending = (f"Refuted pending re-read (2026-10-15): on the read's own test an all-zero fielding ladder "
               f"scores within {x['zb']} runs per 650 PA of v2 (95% CI {x['zb_lo_s']} to {x['zb_hi']}); "
               f"Position Fit values with positional_ladder (v1).")
    note = (
        f" REFUTED PENDING RE-READ 2026-10-15 (LADDER_V2_REVERT, owner decision EW3-29; "
        f"tools/ladder_v2_verify.py, data/positional_ladder_v2_verify.json, gate part 9). The pass rule "
        f"compared v2 only with the v1 refit and had no null comparator. On the read's own folds, rows and "
        f"scoring ({x['n_rows']:,} rows, {x['n_players']} players, seed 20261015, 2,000 draws): MAE v2 "
        f"{x['mae_b']}, all-zero fielding ladder {x['mae_zero']}, v1 refit {x['mae_v1']}; zero minus v2 "
        f"{x['zb']} (CI95 {x['zb_lo']} to {x['zb_hi']}), so the read's +0.886 is v1's spread costing error, "
        f"not v2's ladder earning it (v1 minus zero {x['v1z']}, CI95 {x['v1z_lo']} to {x['v1z_hi']}). "
        f"Scaling v1 or the FanGraphs table toward zero lowers the error at every step; v2's error is flat "
        f"in its scale (lowest at {x['b_best']} times v2). The DH rung enters no scored row and C enters "
        f"{x['c_rows']} rows with a C share change of 0.25 or more. Statcast FRP is not centred within position "
        f"(league rate per 1,277.7 innings CF {x['cf']}, LF {x['lf']}, RF {x['rf']}); with it centred the refit "
        f"beats zero by {x['cen']} (CI95 {x['cen_lo']} to {x['cen_hi']}), a different ladder. CF minus SS by "
        f"source leg: Baseball-Reference {x['cfss_bref']}, FanGraphs {x['cfss_fg']}, Statcast {x['cfss_sav']} "
        f"({x['cfss_savc']} centred). The infield to outfield gap rests on the {x['span_rows']} switcher rows "
        f"that played both, and {x['big_rows']} rows that moved half or more of their innings carry "
        f"{x['big_share']}% of its information. Position Fit values with positional_ladder (v1) again, on one "
        f"run scale; data/positional_ladder_v2.json is a lab artifact kept off the webroot."
    )
    return {"summary": summary, "pending": pending, "note": note}


V2_BASE = {
    "model_id": "positional_ladder_v2",
    "surface": ("Nothing served: a lab artifact (data/positional_ladder_v2.json, kept off the webroot) and the "
                "Library's Positional Ladder view, which prints the read and its verification; the /pal/ "
                "Position Fit board reads positional_ladder (v1)"),
    "predicts": ("The positional adjustment in runs per 650 PA: the fielding runs the same players gain or "
                 "lose when they change position, relative to the exposure-weighted average defensive position"),
    "champion": ("position-switcher network ladder (ladder_v2.py): per fielding source (Baseball-Reference "
                 "runs_field, FanGraphs fld, Statcast FRP) a WLS of next-season fielding runs on last season's "
                 "rate, age and the change in innings shares, plus Statcast same-season pairs; sources pooled by "
                 "inverse variance; DH = 1B + the 1B rate of DH-type seasons; C carried from v1 (13 C-switcher "
                 "rows, under the gate's 30); seasons 2016 to 2026"),
    "baseline": ("v1, the Baseball-Reference runs_position inversion (positional_ladder), refit on the same "
                 "training seasons in each fold; the served v1 vector, the FanGraphs inversion, the published "
                 "FanGraphs table and an offense-equalizing ladder as references; since the verification an "
                 "all-zero fielding ladder"),
    "metric": ("Leave-one-season-out 2016 to 2026: weighted MAE of switchers' fielding plus positional runs per "
               "650 PA (adjacent-season rows on three sources and Statcast same-season pairs); pass iff the "
               "dMAE CI95 lower bound is above zero, player-cluster bootstrap B 2000, seed 20261015"),
    "eval_artifact": "data/positional_ladder_v2_eval.json",
    "verdict": "provisional",
    "provisional_kind": "measured_not_adopted",
    "last_checked": "2026-10-15",
    "stale": False,
    "artifact_age_days": 0,
}

READ_NOTES = (
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
)

V1_SURFACE_ORIG = "Prospect defensive value and the /pal/ Position Fit board; eFV and the projection model do not read it"
V1_SURFACE_V2 = ("Prospect defensive value, the Defense board's Pos (ours) and the published ladder export; the /pal/ "
                 "Position Fit board reads positional_ladder_v2 since 2026-10-15; eFV and the projection model do not read it")
V1_SURFACE = ("Prospect defensive value, the /pal/ Position Fit board, the Defense board's Pos (ours) and the published "
              "ladder export; eFV and the projection model do not read it")
V1_NOTE_ADD = (" SUPERSEDED ON POSITION FIT 2026-10-15 (docs/ewar/LADDER_V2_GATE.md): the position-switcher ladder "
               "(positional_ladder_v2) predicted switchers' held-out fielding plus positional runs better than this "
               "inversion refit on the same seasons, so Position Fit values with v2; this row's ladder is still "
               "data/positional_fit.json fit.ladder, carried unrefit, for DEM+ and the export.")
V1_NOTE_RESTORED = (" RESTORED ON POSITION FIT 2026-10-15 (LADDER_V2_REVERT, owner decision EW3-29): the same day's "
                    "verification found that an all-zero fielding ladder scores as well as v2 on the read's own test "
                    "(data/positional_ladder_v2_verify.json), so Position Fit values with this row's ladder again, "
                    "composed on one run scale (docs/ewar/LADDER_V2_GATE.md part 8); fit.ladder is still carried unrefit.")


def _reread() -> str:
    """The glossary's sentence on the v3 re-read (LADDER_V3_REREAD), from its
    record; empty until the record exists."""
    if not V3_EVAL.exists():
        return ""
    ev = json.loads(V3_EVAL.read_text(encoding="utf-8"))
    z = ev["tests"]["zero_minus_v3_pooled"]
    lo, hi = _f(z["ci95"][0]), _f(z["ci95"][1])
    head = (f"A corrected re-read (v3, {str(ev['read_at'])[:10]}) measured only the gaps inside the infield "
            "and inside the outfield on the same players, with Statcast centred, and took the other levels "
            "from the offense gap among regulars. ")
    if ev["verdict"]["passed"]:
        return head + (f"It passed its checks (its error {_f(z['dmae'])} runs per 650 PA below the zero ladder's, "
                       f"95% CI {lo} to {hi}) and is not used until the owner decides. ")
    return head + (f"It did not pass: against the zero ladder its error was {_f(z['dmae'])} runs per 650 PA "
                   f"lower (95% CI {lo} to {hi}), not a separation, so Position Fit keeps this ladder. ")


def gl_ladder(x: dict) -> dict:
    rr = _reread()
    return {
        "id": "positional_ladder",
        "term": "Positional ladder",
        "category": "custom-index",
        "section": "Players & Stats",
        "module": ["pal"],
        "aliases": ["fitted positional ladder", "switcher ladder", "position-switcher ladder", "ladder v2"]
        + (["ladder v3"] if rr else []),
        "priority": 40,
        "definition": ("The runs a position is worth against the average defensive position, per 650 plate "
                       "appearances. The site's ladder is fitted on Baseball-Reference's positional runs; "
                       "Position Fit in the Alchemy Lab values positions with it."),
        "methodology": (
            "A least squares fit of Baseball-Reference's positional runs per 650 PA on each player-season's "
            "innings shares at the nine positions, no intercept, over a rolling six-season window, recentred so "
            "the exposure-weighted sum is zero. It recovers the constants Baseball-Reference uses, so a rung is "
            "what Baseball-Reference prices the position at, not an independent measure of how hard the position "
            "is to play.\n\n"
            "A second ladder, measured on players who changed position (the position-switcher ladder, v2), was "
            "read once on 2026-10-15 and valued Position Fit for that day. It is withdrawn"
            + ("" if rr else " and under re-read") + ". Its "
            "test compared it only with this ladder. Run on the same players and seasons, a ladder with every "
            f"fielding position at zero scores about as well: its error was {x['zb']} runs per 650 PA higher "
            f"than v2's (95% CI {x['zb_lo_s']} to {x['zb_hi']}), so the test measured this ladder's spread, not "
            "v2's. Two more things the check found: Statcast's fielding runs do not net to zero within a "
            "position, and the gap between the infield and the outfield is set by a few dozen players who "
            "moved between them. " + rr + "The Library's Positional Ladder view has the read"
            + (", the check and the re-read." if rr else " and the check.")
        ),
        "formula": ("positional runs per 650 PA = sum over positions of innings share_p x ladder_p, fitted by "
                    "least squares with no intercept on Baseball-Reference's positional runs; zero = the "
                    "exposure-weighted average defensive position"),
        "example": ("A shortstop moved to first base gives up the gap between the two rungs in positional value; "
                    "the Position Fit tab in the Alchemy Lab prints the current rungs."),
        "seeAlso": ["positional_adjustment", "position_fit", "pal_conversion"],
        "shelf": "ark",
        # the origin names the platform (test_glossary_provenance.py, 5bc67b32)
        "origin": ("Arkmetric, original to eephus.io: fit here from Baseball-Reference's positional runs. The position-switcher "
                   "ladder (v2) is measured from Baseball-Reference, FanGraphs and Statcast fielding runs."),
    }


PA_V1 = ("Pos (ours) is Position Fit's fitted ladder, in runs per 650 plate appearances and inverted from "
         "Baseball-Reference's positional runs,")
PA_V2 = ("Pos (ours) is the site's v1 ladder, in runs per 650 plate appearances and inverted from "
         "Baseball-Reference's positional runs (Position Fit itself values positions with the position-switcher "
         "ladder since 2026-10-15; see Positional ladder),")
PA_ORIGIN_V1 = "Pos (ours) is the site's Position Fit ladder, computed here;"
PA_ORIGIN_V2 = "Pos (ours) is the site's v1 ladder, computed here;"


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


def registry(x: dict) -> str:
    doc, raw, ea = _load(REG)
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    v1 = by_id["positional_ladder"]
    if v1["surface"] in (V1_SURFACE_ORIG, V1_SURFACE_V2):
        v1["surface"] = V1_SURFACE
    if V1_NOTE_ADD.strip() not in v1["notes"]:
        v1["notes"] = v1["notes"] + V1_NOTE_ADD
    if V1_NOTE_RESTORED.strip() not in v1["notes"]:
        v1["notes"] = v1["notes"] + V1_NOTE_RESTORED
    t = v2_texts(x)
    row = {"model_id": V2_BASE["model_id"], "summary": t["summary"]}
    row.update({k: v for k, v in V2_BASE.items() if k != "model_id"})
    row["remeasure_pending"] = t["pending"]
    row["notes"] = READ_NOTES + t["note"]
    cur = by_id.get(row["model_id"])
    if cur is not None:
        rows[rows.index(cur)] = row
    else:
        rows.insert(rows.index(v1) + 1, row)
    out = _render(doc, raw, ea)
    if out == raw:
        return "registry unchanged"
    REG.write_bytes(out)
    return "registry written"


def glossary(x: dict) -> str:
    doc, raw, ea = _load(GLO)
    ents = doc["entries"]
    by_id = {e["id"]: e for e in ents}
    pa = by_id["positional_adjustment"]
    if PA_V2 in pa["methodology"]:
        pa["methodology"] = pa["methodology"].replace(PA_V2, PA_V1)
    if PA_ORIGIN_V2 in pa["origin"]:
        pa["origin"] = pa["origin"].replace(PA_ORIGIN_V2, PA_ORIGIN_V1)
    entry = gl_ladder(x)
    cur = by_id.get(entry["id"])
    if cur is not None:
        ents[ents.index(cur)] = entry
    else:
        ents.insert(ents.index(pa) + 1, entry)
    out = _render(doc, raw, ea)
    if out == raw:
        return "glossary unchanged"
    GLO.write_bytes(out)
    return "glossary written"


def main() -> int:
    x = _verify()
    texts = v2_texts(x)
    for t in (texts, gl_ladder(x), V2_BASE):
        blob = json.dumps(t, ensure_ascii=False)
        if chr(0x2014) in blob or chr(0x2013) in blob:
            raise SystemExit("refusing: a dash in the registration text")
    print(registry(x))
    print(glossary(x))
    return 0


if __name__ == "__main__":
    sys.exit(main())
