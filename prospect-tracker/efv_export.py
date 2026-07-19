# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV Pass 6 -- consolidate the per-side scores + tool eFVs into one artifact the
site can consume (data/xfv.json): per player the headline grade (re-anchored to the
20-80 scale), the realized 6yr-WAR projection, the 5-bucket distribution, surplus $,
the uncertainty band, the consensus FV for side-by-side comparison, and tool eFVs.

Run: python efv_export.py   (after efv_score for both sides + xfv_tools)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from efv_score import scored_path, scored_live_path

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv.json"


def _entry(s, side, kind):
    e = {
        "side": "P" if side == "pit" else "H",
        "kind": kind,                    # "active" | "resolved" | backgrade kinds ("debuted"/"bust")
        # COMMENT CORRECTED 2026-07-14 (audit; the flip shipped 2026-07-06):
        # xfv_grade_quantile IS the displayed headline site-wide (prospx,
        # build_site, proj_export, fa_fit all read it first) and surplus_mm is
        # priced on it -- see meta.grade_scale. xfv_grade / xfv_grade_realized
        # is the honest pure-model reference (realized_implied_fv(E[6yr WAR]),
        # deflated), which still drives p_bucket / p_bust (validated odds).
        # The artifact shape (xfv_grade == realized alias) is test-pinned.
        "xfv_grade": s.get("xfv_grade"),                 # realized (pure model) reference
        "xfv_grade_realized": s.get("xfv_grade"),        # alias (identical; kept for back-compat reads)
        "xfv_grade_quantile": s.get("xfv_grade_display"),# the DISPLAYED headline (20-80 quantile map)
        "consensus_fv": s.get("consensus_fv"),
        "xfv_minus_consensus": s.get("xfv_minus_consensus"),          # realized - consensus (matches headline)
        "xfv_minus_consensus_quantile": s.get("xfv_minus_consensus_display"),  # preserved (quantile - consensus)
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
    if s.get("krp_plus") is not None:                    # KRP+ (K-backed Run Prevention), pitchers
        e["krp_plus"] = s["krp_plus"]
    if s.get("factors"):                                 # per-prospect eFV explainer
        e["factors"] = s["factors"]
    if s.get("xfv_provisional"):                          # prior-anchored (no pro track record)
        e["xfv_provisional"] = True
    if s.get("realized_war") is not None:                # backgraded graduate's actual career WAR
        e["realized_war"] = s["realized_war"]
    return e


def run(persist: bool = True) -> dict:
    from efv_model import blend_lambda   # local: avoids a module-level cycle
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
    from efv_score import backgrade_path
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

    # tool eFVs: resolved first, then live overlays (live wins for board players).
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
            # AUDIT FIX 2026-07-14: the LIVE blend lambda, stamped on every
            # regen - the governance eval artifacts (xfv_eval*.json) record
            # their own lambda at eval time and had silently desynced from
            # the live value twice; this stamp is the always-current truth
            # to compare them against.
            "live_lambda": {"hit": round(blend_lambda("hit"), 4),
                            "pit": round(blend_lambda("pit"), 4)},
            "grade_scale": "xfv_grade_quantile is the DISPLAYED grade site-wide: the model's "
                           "outcome-grounded ranking mapped onto the familiar 20-80 consensus "
                           "scale, and the grade surplus_mm is priced on (owner: eFV + eFV "
                           "surplus consistent everywhere, matching /projections/). xfv_grade / "
                           "xfv_grade_realized is the honest pure-model grade -- "
                           "realized_implied_fv(E[6yr WAR]), deflated -- kept as a secondary "
                           "reference; the outcome distribution p_bucket / p_bust stays on it "
                           "(validated star/bust odds). Live board players carry kind=active + a "
                           "surplus dist; they require a pro track record (eFV abstains on "
                           "players with no MiLB production).",
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
    """Run the whole eFV pipeline in dependency order and consolidate data/xfv.json:
    training matrix -> live matrix -> resolved scores -> live scores -> tool eFVs ->
    export. The forward-chained backtest eval (efv_model, the governance artifact) is
    heavy and stable, so it is OPT-IN (include_eval). Requires data/timeseries.json
    (run after the site export). One call for what was five manual module runs."""
    import efv_dataset
    import efv_score
    import efv_tools
    for side in ("hit", "pit"):
        efv_dataset.run(persist, side)          # labeled training matrix + baseline
        efv_dataset.build_live(persist, side)   # current active-board feature matrix
    if include_eval:
        import efv_model
        for side in ("hit", "pit"):
            efv_model.run(persist, side)         # forward-chained eval (registry artifact)
    for side in ("hit", "pit"):
        efv_score.run(persist, side)             # resolved cohort scores
        efv_score.run_live(persist, side)        # live board scores (gated on track record)
    efv_score.run_backgrade(persist)              # backgrade the rest of the site (graduates etc.)
    efv_score.score_history(persist)              # eFV-over-time per snapshot (FV history chart)
    efv_tools.run(persist)                        # resolved tool eFVs
    efv_tools.run_live(persist)                   # live tool eFVs
    # UNGRADED prospects -- production-only leading indicator for the source-ungraded roster
    # players (DSL/CPX breakouts etc.). Separate model + artifact (data/xfv_ungraded.json);
    # NOT folded into the flagship xfv.json or the farm-rank composite. Needs rosters_by_org.json
    # (written by the site export) + the labeled matrix (built above). Best-effort.
    try:
        import efv_ungraded
        efv_ungraded.build(persist)
    except Exception:
        log.exception("efv_ungraded.build failed -- continuing without ungraded grades")
    # C1: refresh the shipped-distribution reliability curves + drift tripwire.
    # Diagnostic only (no served number depends on them); regen_all previously
    # omitted it, leaving data/xfv_reliability.json stale. Best-effort.
    try:
        import efv_reliability
        efv_reliability.build(persist)
    except Exception:
        log.exception("efv_reliability.build failed -- continuing without reliability regen")
    return run(persist)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--all" in sys.argv:
        rep = regen_all(include_eval="--eval" in sys.argv)
    else:
        rep = run()
    print("eFV consolidated export:", rep["meta"]["n_players"], "players",
          f"({rep['meta']['n_active']} live board) ->", OUT_PATH)
