# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Register the positional ladder v3 re-read (docs/ewar/LADDER_V3_GATE.md) in
data/model_registry.json (idempotent).

Writes one row, positional_ladder_v3, right after positional_ladder_v2. Every
figure is read from data/positional_ladder_v3_eval.json when this runs, never
typed. The verdict follows the record: a passing read is provisional
(measured_not_adopted: built dark, Position Fit waits for the owner); a failing
one is provisional (measured_not_adopted) with a summary that says it failed.
The glossary's Positional ladder entry is written by
tools/register_positional_ladder_v2.py, which reads this record too.

The registry keeps its own line endings, indent and ASCII setting; the script
refuses when a plain round trip would rewrite it. Running it twice changes
nothing. Then:

    python tools/register_positional_ladder_v3.py
    python tools/register_positional_ladder_v2.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import register_positional_ladder_v2 as R2  # noqa: E402

EVAL = ROOT / "data" / "positional_ladder_v3_eval.json"


def _s(x, nd=3):
    return f"{float(x):+.{nd}f}"


def _u(x, nd=3):
    return f"{float(x):.{nd}f}"


def figures() -> dict:
    ev = json.loads(EVAL.read_text(encoding="utf-8"))
    t, v, sc = ev["tests"], ev["verdict"], ev["scores"]["pooled"]
    ratios = ev["simulation"]["base"]["mean_ratio"]
    g = ev["v3"]["gaps"]
    z, v1, za, w = (t["zero_minus_v3_pooled"], t["v1_minus_v3_pooled"], t["zero_minus_v3_across"],
                    t["zero_minus_v3_within"])
    fails = [k.split("_", 1)[0] for k in ("1_beats_zero", "2_beats_v1", "3_below_scaled_v1_and_fg_table",
                                          "4_not_worse_than_zero_next_season", "5_recovers_planted_ladder")
             if not v[k]]
    return {
        "date": str(ev["read_at"])[:10], "passed": v["passed"], "fails": fails,
        "z": _u(z["dmae"]), "z_lo": _s(z["ci95"][0]), "z_hi": _s(z["ci95"][1]),
        "v1": _s(v1["dmae"]), "v1_lo": _s(v1["ci95"][0]), "v1_hi": _s(v1["ci95"][1]),
        "za": _s(za["dmae"]), "za_lo": _s(za["ci95"][0]), "za_hi": _s(za["ci95"][1]),
        "w": _s(w["dmae"]), "w_lo": _s(w["ci95"][0]), "w_hi": _s(w["ci95"][1]),
        "n_rows": z["n_rows"], "n_players": z["n_players"],
        "mae": {k: _u(sc[k]["mae"]) for k in ("v3", "zero", "v1", "fg_table", "v1_x0.25", "v1_x0.5",
                                               "v1_x0.75", "v1_x1.25")},
        "ratios": ", ".join(f"{p} {r:.2f}" for p, r in ratios.items()),
        "gaps": (f"2B {g['IF_vs_SS']['2B']:+.2f} and 3B {g['IF_vs_SS']['3B']:+.2f} from SS, LF "
                 f"{g['OF_vs_CF']['LF']:+.2f} and RF {g['OF_vs_CF']['RF']:+.2f} from CF"),
    }


def row(x: dict) -> dict:
    if x["passed"]:
        summary = (f"Passed its five checks {x['date']}: beats zero by {x['z']} runs per 650 PA "
                   f"(CI95 {x['z_lo']} to {x['z_hi']}). Built dark; not served.")
    else:
        summary = (f"Failed the re-read: an all-zero fielding ladder scores within {x['z']} runs per 650 PA "
                   f"(CI95 {x['z_lo']} to {x['z_hi']}). Not served.")
    notes = (
        f"Registered 2026-10-15 in docs/ewar/LADDER_V3_GATE.md (task LADDER_V3_REREAD, owner decision EW3-29), "
        f"committed alone before any number; amended once before the read (A1: the within-group fit takes "
        f"player fixed effects, because the registered persistence form recovered a planted ladder at 0.5 to "
        f"0.9 of its size on fixtures). Read once {x['date']} (tools/ladder_v3_lab.py --read, "
        f"{x['n_rows']:,} held-out rows, {x['n_players']} players, seed 20261015, 2,000 draws). The five checks: "
        f"zero minus v3 {x['z']} (CI95 {x['z_lo']} to {x['z_hi']}); v1 refit minus v3 {x['v1']} "
        f"(CI95 {x['v1_lo']} to {x['v1_hi']}); pooled MAE v3 {x['mae']['v3']} against v1 x 0.25 "
        f"{x['mae']['v1_x0.25']}, x 0.5 {x['mae']['v1_x0.5']}, x 0.75 {x['mae']['v1_x0.75']}, x 1 "
        f"{x['mae']['v1']}, x 1.25 {x['mae']['v1_x1.25']} and the FanGraphs table {x['mae']['fg_table']}; "
        f"zero minus v3 on the next-season rows {x['za']} (CI95 {x['za_lo']} to {x['za_hi']}); recovery of a "
        f"planted ladder on the real design, mean of five seeds, {x['ratios']} (bar 0.80 to 1.25). "
        + ("All five pass. " if x["passed"] else f"Failed checks: {', '.join(x['fails'])}. ")
        + f"On the Statcast same-season pairs v3 beats zero by {x['w']} (CI95 {x['w_lo']} to {x['w_hi']}). "
        f"The candidate, fit on 2016 to 2026: inside the groups {x['gaps']}; group levels, 1B and DH from the "
        f"offense gap among regulars; C carried from v1. Position Fit values with positional_ladder (v1); "
        + ("v3 is built dark and waits for the owner's answer."
           if x["passed"] else "no v3 ladder artifact is written or published (EW3-29).")
    )
    return {
        "model_id": "positional_ladder_v3",
        "summary": summary,
        "surface": ("Nothing served: the Library's Positional Ladder view prints the re-read; the /pal/ "
                    "Position Fit board reads positional_ladder (v1)"),
        "predicts": ("The positional adjustment in runs per 650 PA: gaps inside the infield and inside the "
                     "outfield from the same players' fielding runs, levels from the offense gap"),
        "champion": ("ladder_v3.py: per fielding source (Baseball-Reference runs_field, FanGraphs fld, Statcast "
                     "FRP centred within position and season) a player fixed-effects WLS of fielding runs per "
                     "650 PA on innings shares inside the infield (2B, 3B, SS) and the outfield (LF, CF, RF), "
                     "plus Statcast same-season pairs; sources pooled by inverse variance; group levels, 1B and "
                     "DH from the offense-equalizing gap among regulars; C carried from v1; seasons 2016 to 2026"),
        "baseline": ("An all-zero fielding ladder, the Baseball-Reference inversion refit in each fold (v1) and "
                     "scaled by 0.25 to 1.25, and the FanGraphs table; the offense ladder, the shapes on a zero "
                     "level and the v2 vector as references"),
        "metric": ("Leave-one-season-out 2016 to 2026: weighted MAE of switchers' fielding plus positional runs "
                   "per 650 PA (across-season rows with a multi-season predictor, and Statcast same-season "
                   "pairs); passes iff it beats zero and v1 (CI95 lower bounds above 0), is below every scaled "
                   "v1 and the FanGraphs table, is not significantly worse than zero next season, and recovers "
                   "a planted ladder at 0.80 to 1.25 per gap"),
        "eval_artifact": "data/positional_ladder_v3_eval.json",
        "verdict": "provisional",
        "provisional_kind": "measured_not_adopted",
        "last_checked": x["date"],
        "stale": False,
        "artifact_age_days": 0,
        "notes": notes,
    }


def registry(x: dict) -> str:
    doc, raw, ea = R2._load(R2.REG)
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    new = row(x)
    cur = by_id.get(new["model_id"])
    if cur is not None:
        # freshness fields belong to the registry's own stamping pass
        for k in ("last_checked", "stale", "artifact_age_days"):
            if k in cur:
                new[k] = cur[k]
        rows[rows.index(cur)] = new
    else:
        rows.insert(rows.index(by_id["positional_ladder_v2"]) + 1, new)
    out = R2._render(doc, raw, ea)
    if out == raw:
        return "registry unchanged"
    R2.REG.write_bytes(out)
    return "registry written"


def main() -> int:
    x = figures()
    blob = json.dumps(row(x), ensure_ascii=False)
    if chr(0x2014) in blob or chr(0x2013) in blob:
        raise SystemExit("refusing: a dash in the registration text")
    print(registry(x))
    return 0


if __name__ == "__main__":
    sys.exit(main())
