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

from xfv_score import scored_path, scored_live_path

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv.json"


def _entry(s, side, kind):
    e = {
        "side": "P" if side == "pit" else "H",
        "kind": kind,                                    # "active" (live board) | "resolved"
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
    if s.get("dist") is not None:                        # live: full surplus fan + comparison
        e["dist"] = s["dist"]
    if s.get("consensus_surplus_mm") is not None:
        e["consensus_surplus_mm"] = s["consensus_surplus_mm"]
    if s.get("injury_factor") is not None:               # live injury penalty (<1.0 = hurt)
        e["injury_factor"] = s["injury_factor"]
    if s.get("statcast_factor") is not None:             # live Statcast+ tilt (!=1.0)
        e["statcast_factor"] = s["statcast_factor"]
    if s.get("factors"):                                 # per-prospect xFV explainer
        e["factors"] = s["factors"]
    if s.get("xfv_provisional"):                          # prior-anchored (no pro track record)
        e["xfv_provisional"] = True
    if s.get("realized_war") is not None:                # backgraded graduate's actual career WAR
        e["realized_war"] = s["realized_war"]
    return e


def run(persist: bool = True) -> dict:
    by_player = {}
    counts = {"resolved": 0, "active": 0}
    # resolved (backtest cohort -- known outcomes; powers the Debuted views) FIRST, then
    # the live board OVERWRITES any overlap so a current prospect shows its live grade.
    for side in ("hit", "pit"):
        for s in json.loads(scored_path(side).read_text(encoding="utf-8")):
            by_player[s["player_key"]] = _entry(s, side, "resolved")
            counts["resolved"] += 1
    # Backgrade: every other graded prospect (graduates + lingering/no-track-record actives),
    # scored on the live grade scale. Overwrites the resolved-scale entry so the WHOLE site
    # reads on one scale; the live board (next) wins for current prospects.
    from xfv_score import backgrade_path
    bp = backgrade_path()
    if bp.exists():
        for s in json.loads(bp.read_text(encoding="utf-8")).get("scored", []):
            by_player[s["player_key"]] = _entry(s, s.get("side") == "pit" and "pit" or "hit",
                                                s.get("kind", "backgrade"))
            counts["backgrade"] = counts.get("backgrade", 0) + 1
    for side in ("hit", "pit"):
        lp = scored_live_path(side)
        if not lp.exists():
            continue
        for s in json.loads(lp.read_text(encoding="utf-8")):
            by_player[s["player_key"]] = _entry(s, side, "active")
            counts["active"] += 1

    # tool xFVs: resolved first, then live overlays (live wins for board players).
    for fn in ("xfv_tools.json", "xfv_tools_live.json"):
        fp = DATA_DIR / fn
        if not fp.exists():
            continue
        for pk, tv in json.loads(fp.read_text(encoding="utf-8")).get("by_player", {}).items():
            if pk in by_player:
                by_player[pk]["tool_xfv"] = tv

    out = {
        "meta": {
            "generated_at": date.today().isoformat(),
            "n_players": len(by_player),
            "n_active": counts["active"],
            "grade_scale": "headline xfv_grade is rank-preserving onto the 20-80 consensus "
                           "distribution; xfv_grade_realized is the deflated outcome-implied "
                           "grade that drives surplus + distribution. Live board players carry "
                           "kind=active + a surplus dist; they require a pro track record (xFV "
                           "abstains on players with no MiLB production).",
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


def regen_all(persist: bool = True, include_eval: bool = False) -> dict:
    """Run the whole xFV pipeline in dependency order and consolidate data/xfv.json:
    training matrix -> live matrix -> resolved scores -> live scores -> tool xFVs ->
    export. The forward-chained backtest eval (xfv_model, the governance artifact) is
    heavy and stable, so it is OPT-IN (include_eval). Requires data/timeseries.json
    (run after the site export). One call for what was five manual module runs."""
    import xfv_dataset
    import xfv_score
    import xfv_tools
    for side in ("hit", "pit"):
        xfv_dataset.run(persist, side)          # labeled training matrix + baseline
        xfv_dataset.build_live(persist, side)   # current active-board feature matrix
    if include_eval:
        import xfv_model
        for side in ("hit", "pit"):
            xfv_model.run(persist, side)         # forward-chained eval (registry artifact)
    for side in ("hit", "pit"):
        xfv_score.run(persist, side)             # resolved cohort scores
        xfv_score.run_live(persist, side)        # live board scores (gated on track record)
    xfv_score.run_backgrade(persist)              # backgrade the rest of the site (graduates etc.)
    xfv_score.score_history(persist)              # xFV-over-time per snapshot (FV history chart)
    xfv_tools.run(persist)                        # resolved tool xFVs
    xfv_tools.run_live(persist)                   # live tool xFVs
    # UNGRADED prospects -- production-only leading indicator for the source-ungraded roster
    # players (DSL/CPX breakouts etc.). Separate model + artifact (data/xfv_ungraded.json);
    # NOT folded into the flagship xfv.json or the farm-rank composite. Needs rosters_by_org.json
    # (written by the site export) + the labeled matrix (built above). Best-effort.
    try:
        import xfv_ungraded
        xfv_ungraded.build(persist)
    except Exception:
        log.exception("xfv_ungraded.build failed -- continuing without ungraded grades")
    return run(persist)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--all" in sys.argv:
        rep = regen_all(include_eval="--eval" in sys.argv)
    else:
        rep = run()
    print("xFV consolidated export:", rep["meta"]["n_players"], "players",
          f"({rep['meta']['n_active']} live board) ->", OUT_PATH)
