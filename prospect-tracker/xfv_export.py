# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""xFV Pass 6 -- consolidate the per-side scores + tool xFVs into one artifact the
site can consume (data/xfv.json): per player the headline grade (re-anchored to the
20-80 scale), the realized 6yr-WAR projection, the 5-bucket distribution, surplus $,
the uncertainty band, the consensus FV for side-by-side comparison, and tool xFVs.

Run: python xfv_export.py   (after xfv_score for both sides + xfv_tools)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from xfv_score import scored_path

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv.json"


def run(persist: bool = True) -> dict:
    by_player = {}
    for side in ("hit", "pit"):
        for s in json.loads(scored_path(side).read_text(encoding="utf-8")):
            by_player[s["player_key"]] = {
                "side": "P" if side == "pit" else "H",
                "xfv_grade": s.get("xfv_grade_display"),         # headline, 20-80 scale
                "xfv_grade_realized": s.get("xfv_grade"),        # deflated, drives surplus
                "consensus_fv": s.get("consensus_fv"),
                "xfv_minus_consensus": s.get("xfv_minus_consensus_display"),
                "xfv_war_6yr": s.get("xfv_war_6yr"),
                "p_bucket": s.get("p_bucket"),
                "surplus_mm": s.get("surplus_mm"),
                "band_p10_mm": s.get("band_p10_mm"),
                "band_p90_mm": s.get("band_p90_mm"),
                "p_bust": s.get("p_bust"),
            }
    tools = json.loads((DATA_DIR / "xfv_tools.json").read_text(encoding="utf-8")).get("by_player", {})
    for pk, tv in tools.items():
        if pk in by_player:
            by_player[pk]["tool_xfv"] = tv

    out = {
        "meta": {
            "generated_at": date.today().isoformat(),
            "n_players": len(by_player),
            "grade_scale": "headline xfv_grade is rank-preserving onto the 20-80 consensus "
                           "distribution; xfv_grade_realized is the deflated outcome-implied "
                           "grade that drives surplus + distribution",
            "eval": {"hitter": "data/xfv_eval.json", "pitcher": "data/xfv_eval_pitcher.json",
                     "tools": "data/xfv_tools.json"},
            "status": "provisional",
        },
        "by_player": by_player,
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=0), encoding="utf-8")
        log.info("wrote %s (%d players)", OUT_PATH, len(by_player))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print("xFV consolidated export:", rep["meta"]["n_players"], "players ->", OUT_PATH)
