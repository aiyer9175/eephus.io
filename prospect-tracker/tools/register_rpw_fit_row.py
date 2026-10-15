"""Register the runs-per-win fit row in data/model_registry.json (idempotent).

Writes, once, the row docs/ewar/RPW_GATE.md part 7 names: rpw_fit, verdict
provisional, provisional_kind measurement_only, eval_artifact data/rpw_fit.json (built
by tools/build_rpw_fit.py). Keeps the file's line endings and its one-space indent;
refuses when a plain round trip would rewrite the file. Running it twice changes
nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_rpw_fit_row.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
AFTER = "count_value"

ROW = {
    "model_id": "rpw_fit",
    "summary": "Measured, not served: runs per win fitted from club wins; the wins-on-run-differential slope beat the FanGraphs closed form out of sample (lo95 +0.0135 wins), pending eWAR v3's team guard.",
    "surface": "None served: no page reads it. data/rpw_fit.json is the conversion EWAR_V3_ASSEMBLE reads for eWAR v3 only if the EBR_GATE 11.2.4 team guard reads NON-INFERIOR",
    "predicts": "Club wins from run differential (W = G / 2 + RD / RPW, or Pythagenpat), leave one season out, as the test of a runs-per-win conversion; player-free",
    "champion": "none admitted. Carried forward: (c) the slope of wins on run differential through the origin, RPW 10.6261 on all ten primary seasons (PRIMARY PASS, GUARD PENDING)",
    "baseline": "(a) the FanGraphs closed form 9 x (R/IP) x 1.5 + 3, league_constants.league_totals rpw (9.52 to 10.30), eWAR v3's incumbent conversion",
    "metric": "Held-out MAE in wins over 300 team-seasons (RMSE reported); paired team-season bootstrap B 2000, seed 20261025; pass when lo95 of MAE(a) - MAE(candidate) is above 0",
    "eval_artifact": "data/rpw_fit.json",
    "verdict": "provisional",
    "provisional_kind": "measurement_only",
    "notes": (
        "Registered 2026-10-15 in docs/ewar/RPW_GATE.md (task EWAR_RPW_FIT, owner decision EW3-24), committed alone before any number (5d6f592b). "
        "Build 1, 2026-10-15, tools/build_rpw_fit.py over the cached StatsAPI standings, FanGraphs park factors and Baseball-Reference war_daily: "
        "held-out MAE in wins (a) closed form 3.2976, (b) Pythagenpat z fitted 3.2113 (z 0.251), (c) slope of wins on RD 3.1968, (d) run environment 3.2767, "
        "(e) Baseball-Reference recovered 3.3354; references G/2 10.3867 and Pythagenpat 0.287 3.2980. dMAE vs (a): b +0.0863 (lo95 -0.0014), c +0.1008 (lo95 +0.0135, PRIMARY PASS), "
        "d +0.0209 (lo95 -0.0782), e -0.0379 (hi95 -0.0007, worse). A Holm read over the four challengers rejects nothing (reported, deciding nothing). "
        "(c) replaces the closed form in eWAR v3 part 9.2 only after the EBR_GATE 11.2.4 team guard reads NON-INFERIOR; until then the incumbent stands. "
        "Pitcher leg: FanGraphs' per-pitcher dynamic form on runs allowed does not separate from the league constant (MAE 3.3564 vs 3.2976, dMAE lo95 -0.1486, hi95 +0.0318). "
        "No player value, FV-cell statistic, betting column or projections input; nothing served moves."
    ),
}


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))

    def render(d) -> bytes:
        text = json.dumps(d, indent=1, ensure_ascii=False)
        if crlf:
            text = text.replace("\n", "\r\n")
        if raw.endswith(b"\n"):
            text += "\r\n" if crlf else "\n"
        return text.encode("utf-8")

    if render(doc) != raw:
        print("refusing: a plain round trip would rewrite data/model_registry.json")
        return 2
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    cur = by_id.get(ROW["model_id"])
    if cur == ROW:
        print("registry already carries rpw_fit; nothing written")
        return 0
    if cur is not None:
        rows[rows.index(cur)] = dict(ROW)
        what = "registry row replaced"
    else:
        idx = next((i for i, r in enumerate(rows) if r["model_id"] == AFTER), len(rows) - 1)
        rows.insert(idx + 1, dict(ROW))
        what = "registry written"
    REG.write_bytes(render(doc))
    print(f"{what}: rpw_fit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
