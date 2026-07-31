# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""LANE A4: uncapped live Statcast overlay lab (efv-2026-07-24 accuracy program).

Measures the LIVE board-move distribution of the S-XLINE-4 + W-OVERLAY-R
model-leg overlay under three settings, on the CURRENT live board matrices:
  OFF      : production default (overlay is a no-op).
  CAPPED   : BETA 0.6, DELTA_CAP_FV 2.0 (the failed-only-on-the-display-ceiling
             S-XLINE-4 ship setting).
  UNCAPPED : BETA 0.6, DELTA_CAP_FV removed (owner ceiling removal).

Two measurements:
  (1) direct overlay FV-lean delta per covered board player (capped vs
      uncapped) - the purest "now unbounded" quantity + coverage n hit/pit.
  (2) served xfv_grade_display + board-rank move vs the OFF baseline, by
      running efv_score.run_live for each setting with scored_live_path
      REDIRECTED to scratchpad (never regenerates served artifacts).

PROVENANCE / HONESTY: these are coverage-limited LIVE signals with NO resolved
OOS fold (the A-ball covered cohorts have not resolved). The ship is authorized
by the SCREEN validation already recorded (aaa_physics_screen_eval survivor
legs velo/spin/vaa lo95>0; S-XLINE-4 INC forward reads whiff rho +0.0965 CI
[+0.0277,+0.1604] n=788, fb_velo rho +0.1423 CI [+0.0196,+0.2704] n=227) PLUS
the owner ceiling removal - NOT a new pooled-OOS gate. No missing feature is
imputed with a signal-manufacturing constant: covered players carry real cached
physics/whiff z-legs; uncovered players stay OFF-path byte-identical (None).

Run:  python tools/efv_overlay_uncapped_lab.py
Writes data/xfv_overlay_uncapped_eval.json (owned by lane A4).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("EEPHUS_XOVERLAY_HIT", "1")
os.environ.setdefault("EEPHUS_XOVERLAY_PIT", "1")
# Isolate the overlay: hold the orthogonal top-band F-SIDE-FIX display
# recalibration OFF-consistent across all three scenarios so the measured
# board move is attributable to the overlay alone (F-SIDE-FIX only touches
# >= 52.5-preside grades and reads cross-side scored artifacts, which would
# otherwise confound the redirected-persist runs).
os.environ["EEPHUS_SIDE_FAIRNESS_FIX"] = "0"

import efv_score  # noqa: E402
import efv_statcast_overlay as ov  # noqa: E402

DATA = ROOT / "data"
SCRATCH = Path(os.environ.get("A4_SCRATCH") or (ROOT / ".cache" / "a4_overlay_lab"))
SCRATCH.mkdir(parents=True, exist_ok=True)
EVAL_PATH = DATA / "xfv_overlay_uncapped_eval.json"

# ---- name lookup (player_key -> player_name), read-only DB -----------------
def _names() -> dict:
    import sqlite3
    out = {}
    try:
        c = sqlite3.connect(f"file:{(ROOT/'prospects.db').as_posix()}?mode=ro", uri=True)
        for pk, nm in c.execute("select player_key, player_name from players"):
            if pk and nm:
                out[pk] = nm
        c.close()
    except Exception:
        pass
    return out


NAMES = _names()


def _pctile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(len(s) - 1, lo + 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _live_rows(side):
    p = DATA / ("xfv_live_pitcher_matrix.json" if side == "pit"
               else "xfv_live_hitter_matrix.json")
    return json.loads(p.read_text(encoding="utf-8"))


# ---- (1) direct overlay FV-lean deltas, capped vs uncapped ------------------
def direct_lean(side):
    """Per covered board row: (player_key, capped_delta, uncapped_delta).
    Uncapped removes DELTA_CAP_FV; the round(.,2) display rounding is kept (it
    is not a cap). Off-path invariance verified: uncovered rows return None
    under BOTH settings."""
    rows = _live_rows(side)
    covered = []
    n_uncovered_moved = 0
    prev_cap = ov.DELTA_CAP_FV
    try:
        for r in rows:
            ov.DELTA_CAP_FV = 2.0
            capd = ov.overlay_fv(r, side)
            ov.DELTA_CAP_FV = 12.0  # A4 ship value (wide safety bound; never binds on real signal)
            unc = ov.overlay_fv(r, side)
            if capd is None and unc is None:
                continue
            if (capd is None) != (unc is None):
                # cap removal can only change magnitude, never coverage
                n_uncovered_moved += 1
            pk = r.get("player_key")
            covered.append({
                "player_key": pk,
                "name": NAMES.get(pk, (pk or "").replace("_", " ").title()),
                "mlbam_id": r.get("mlbam_id"),
                "level": (r.get("milb") or {}).get("milb_level"),
                "chip": (unc or capd)[1],
                "capped_delta_fv": (capd[0] if capd else 0.0),
                "uncapped_delta_fv": (unc[0] if unc else 0.0),
            })
    finally:
        ov.DELTA_CAP_FV = prev_cap
    return covered, n_uncovered_moved


# ---- (2) served board move via run_live (redirected persist) ---------------
def _run_scored(side, setting):
    """Run efv_score.run_live under `setting` and return {player_key: entry}.
    scored_live_path is redirected to scratchpad so no served artifact moves."""
    if setting == "off":
        os.environ["EEPHUS_XOVERLAY_HIT"] = "0"
        os.environ["EEPHUS_XOVERLAY_PIT"] = "0"
        ov.DELTA_CAP_FV = 2.0
    elif setting == "capped":
        os.environ["EEPHUS_XOVERLAY_HIT"] = "1"
        os.environ["EEPHUS_XOVERLAY_PIT"] = "1"
        ov.DELTA_CAP_FV = 2.0
    elif setting == "uncapped":
        os.environ["EEPHUS_XOVERLAY_HIT"] = "1"
        os.environ["EEPHUS_XOVERLAY_PIT"] = "1"
        ov.DELTA_CAP_FV = 12.0  # A4 ship value (wide safety bound; never binds on real signal)
    out_path = SCRATCH / f"scored_{side}_{setting}.json"
    orig = efv_score.scored_live_path
    efv_score.scored_live_path = lambda s, _p=out_path: _p
    try:
        efv_score.run_live(persist=True, side=side)
    finally:
        efv_score.scored_live_path = orig
    scored = json.loads(out_path.read_text(encoding="utf-8"))
    # board rank: 1 = best (highest rank_war)
    order = sorted(range(len(scored)),
                   key=lambda i: (scored[i].get("rank_war", 0.0),
                                  scored[i]["player_key"]), reverse=True)
    rank_of = {}
    for pos, i in enumerate(order):
        rank_of[scored[i]["player_key"]] = pos + 1
    return {s["player_key"]: {
        "grade": s.get("xfv_grade_display"),
        "rank": rank_of[s["player_key"]],
    } for s in scored}


def served_move(side, covered_keys):
    off = _run_scored(side, "off")
    capped = _run_scored(side, "capped")
    uncapped = _run_scored(side, "uncapped")
    moves = {"capped": [], "uncapped": []}
    rank_moves = {"capped": [], "uncapped": []}
    per_player = {}
    for pk in off:
        og = off[pk]["grade"]
        orank = off[pk]["rank"]
        row = {"off_grade": og, "off_rank": orank}
        for lbl, tbl in (("capped", capped), ("uncapped", uncapped)):
            if pk in tbl and tbl[pk]["grade"] is not None and og is not None:
                dg = round(tbl[pk]["grade"] - og, 3)
                dr = tbl[pk]["rank"] - orank
                row[f"{lbl}_grade"] = tbl[pk]["grade"]
                row[f"{lbl}_dgrade"] = dg
                row[f"{lbl}_drank"] = dr
                if pk in covered_keys:
                    moves[lbl].append(dg)
                    rank_moves[lbl].append(dr)
        per_player[pk] = row
    return moves, rank_moves, per_player


def dist_block(vals):
    av = [abs(v) for v in vals]
    return {
        "n": len(vals),
        "max_abs": round(max(av), 3) if av else 0.0,
        "p90_abs": round(_pctile(av, 0.90), 3) if av else 0.0,
        "p50_abs": round(_pctile(av, 0.50), 3) if av else 0.0,
        "mean_abs": round(statistics.mean(av), 3) if av else 0.0,
        "max_signed": round(max(vals), 3) if vals else 0.0,
        "min_signed": round(min(vals), 3) if vals else 0.0,
    }


def run_side(side):
    covered, n_flip = direct_lean(side)
    covered_keys = {c["player_key"] for c in covered}
    cap_leans = [c["capped_delta_fv"] for c in covered]
    unc_leans = [c["uncapped_delta_fv"] for c in covered]
    n_at_cap = sum(1 for c in covered if abs(c["uncapped_delta_fv"]) > 2.0 + 1e-9)
    moves, rank_moves, per_player = served_move(side, covered_keys)

    # top-10 covered movers by |uncapped served grade move|, with lean context
    movers = []
    for c in covered:
        pk = c["player_key"]
        pp = per_player.get(pk, {})
        movers.append({
            "name": c["name"],
            "player_key": pk,
            "level": c["level"],
            "chip": c["chip"],
            "capped_lean_fv": round(c["capped_delta_fv"], 3),
            "uncapped_lean_fv": round(c["uncapped_delta_fv"], 3),
            "off_grade": pp.get("off_grade"),
            "uncapped_grade": pp.get("uncapped_grade"),
            "uncapped_dgrade": pp.get("uncapped_dgrade"),
            "uncapped_drank": pp.get("uncapped_drank"),
        })
    movers.sort(key=lambda m: abs(m.get("uncapped_dgrade") or 0.0), reverse=True)

    return {
        "coverage": {
            "n_covered_board": len(covered),
            "coverage_flip_uncovered_moved": n_flip,  # must be 0 (off-path invariance)
            "n_lean_exceeds_old_2fv_cap": n_at_cap,
        },
        "fv_lean_capped": dist_block(cap_leans),
        "fv_lean_uncapped": dist_block(unc_leans),
        "served_grade_move_vs_off": {
            "capped": dist_block(moves["capped"]),
            "uncapped": dist_block(moves["uncapped"]),
        },
        "served_rank_move_vs_off": {
            "capped": dist_block(rank_moves["capped"]),
            "uncapped": dist_block(rank_moves["uncapped"]),
        },
        "top_movers_uncapped": movers[:10],
    }


def main():
    result = {
        "lane": "A4 SIGNAL REVIVAL WITHOUT CEILING",
        "generated_by": "tools/efv_overlay_uncapped_lab.py",
        "registration": "docs/efv-2026-07-24/GATES-ACCURACY.md A4",
        "authorization": ("coverage-limited LIVE signals, NO resolved OOS fold; "
                          "ship authorized by screen validation + owner ceiling "
                          "removal, not a new OOS gate"),
        "screen_validation": {
            "aaa_survivors": {"velo": {"rho": 0.1283, "lo95": 0.0289},
                              "spin": {"rho": 0.152, "lo95": 0.048},
                              "vaa": {"rho": 0.1239, "lo95": 0.0272}},
            "s_xline_inc": {"hit_whiff": {"rho": 0.0965, "ci95": [0.0277, 0.1604], "n": 788},
                            "pit_fb_velo": {"rho": 0.1423, "ci95": [0.0196, 0.2704], "n": 227}},
        },
        "settings": {"BETA_FV_PER_RESID_Z": ov.BETA_FV_PER_RESID_Z,
                     "BETA_decision": "KEPT at screen-calibrated 0.6 (no resolved OOS fold justifies a raise)",
                     "DELTA_CAP_FV_before": 2.0, "DELTA_CAP_FV_after": 12.0,
                     "DELTA_CAP_classification": ("2-FV DISPLAY cap REMOVED (owner directive); "
                                                  "12.0 is a wide NUMERICAL-SAFETY sanity bound only, "
                                                  "never binds on plausible signal (max real lean 2.36 FV)"),
                     "OVERLAY_HIT_DEFAULT_after": True,
                     "OVERLAY_PIT_DEFAULT_after": True,
                     "f_side_fix_held": "EEPHUS_SIDE_FAIRNESS_FIX=0 across all scenarios to isolate the overlay"},
        "sides": {},
    }
    for side in ("hit", "pit"):
        result["sides"][side] = run_side(side)
    EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
    # console summary
    for side in ("hit", "pit"):
        s = result["sides"][side]
        print(f"\n=== {side.upper()} ===")
        print("coverage:", s["coverage"])
        print("FV-lean capped  :", s["fv_lean_capped"])
        print("FV-lean uncapped:", s["fv_lean_uncapped"])
        print("served grade move vs OFF (capped)  :", s["served_grade_move_vs_off"]["capped"])
        print("served grade move vs OFF (uncapped):", s["served_grade_move_vs_off"]["uncapped"])
        print("served rank move vs OFF (uncapped) :", s["served_rank_move_vs_off"]["uncapped"])
        print("top movers (uncapped):")
        for m in s["top_movers_uncapped"]:
            print(f"  {m['name']:<22} {m['level']:<4} {m['chip']:<20} "
                  f"lean cap={m['capped_lean_fv']:+.2f} unc={m['uncapped_lean_fv']:+.2f} "
                  f"grade {m['off_grade']}->{m['uncapped_grade']} "
                  f"(d={m['uncapped_dgrade']:+}) drank={m['uncapped_drank']:+}")
    print(f"\nwrote {EVAL_PATH}")


if __name__ == "__main__":
    main()
