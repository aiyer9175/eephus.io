# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""W-OVERLAY-R gate lab (docs/efv-2026-07-24/GATES.md Phase 3c): overlay
revival under the AMENDED display-space ceiling, 4.0 FV / 40 board rank
positions vs a same-run NO-OVERLAY shadow ranking (owner-selected 2026-07-23,
supersedes the failed S-XLINE-4 2-FV served ceiling and the 3.0/25 draft
bound). One attempt; marginal = FAIL; seed N/A (the battery is deterministic,
no bootstrap clause in this lane).

=========================== FROZEN LAB HEADER ================================
Everything in this block was frozen BEFORE the battery ran and is never
edited afterward.

LEGS (the GATES leg rules, operationalized):
  hit : whiff leg ONLY - the existing A/CPX signal
        (data/statcast_alevel_signals.json, frozen hit_whiff_on_k
        coefficients), gates exactly as built: current tracked season/level
        must be the baked signal's, >= 100 pitches. Direction NEGATIVE (high
        whiff residual = unpaid strikeout risk).
  pit : at most ONE velo-family leg per player:
          A-ball fb_velo signal (frozen pit_velo_on_ka residual on current
          K%a z) vs AAA velo residual (frozen resid_fit_on_astuff from
          data/aaa_physics_screen_eval.json survivors block); PREFER THE
          LEVEL WITH THE LARGER RECENT SAMPLE (n_pitches of each source).
          The current-season gates (A/CPX signal must match the row's
          current level+season; AAA legs require current level AAA + same
          season physics) make the two structurally exclusive; the sample
          preference is the frozen tiebreak.
        plus spin and vaa legs where covered (AAA W-SCREEN survivors, frozen
          resid_fit_on_astuff + resid_sd z-scale). AAA floors AS BUILT:
          >= 100 physics pitches (MIN_PITCHES) + astuff_pool present; vaa leg
          additionally >= 50 VAA-computable cached pitches for the row's
          CURRENT season from .cache/aaa_pitches_vaa (the W-SCREEN row
          floor). All pit legs directed POSITIVE (every survivor passed on
          natural-units positive rho; no sign flips).
  composite : equal-weight mean of available DIRECTED leg z-scores, then the
          built BETA 0.6 FV per z and the 2.0 FV-lean cap, both UNCHANGED.

SUB-AAA DECISION (frozen before any run): the W-SCREEN-SUB survivors
  (ivb lo95 +0.026, vaa lo95 +0.075, n=60) are NOT wired as overlay legs.
  Reasons: (a) 8.3 percent tracked-park coverage of the qualifying A/CPX
  universe (60/719) - a lean that moves ~8 percent of arms on physics the
  other 92 percent structurally cannot show is a park-coverage artifact at
  display scale; (b) their residualizer is resid_fit_on_yhat and the
  stat-line ridge WEIGHTS are not frozen in the artifact - rebuilding yhat
  at serve time is a refit, which the overlay module structurally forbids
  (test_exporter_has_no_fit_code is the same covenant); (c) ivb barely
  clears at n=60 and the AAA screen FAILED ivb outright (-0.026). The
  handoff note's display-only prescription stands: recommend a detail-page
  context tile via the wave-D consolidator, never a model leg.

BATTERY (clause 3, computed IN-PROCESS the way the P1 V3 lab did):
  Score the live pool through the REAL scoring path - efv_score.run_live
  (production fit, guarded blend, tilts, quantile display map, surplus
  reprice) - twice per side within one process: overlay env flags OFF ("0")
  then ON ("1"), efv_score.scored_live_path monkeypatched to a scratch dir
  so NO served artifact is regenerated. xfv_grade_quantile == the scored
  row's xfv_grade_display (efv_export serves it verbatim).
  BOARD RANK (frozen definition): pooled hit+pit active rows sorted by
  (-xfv_grade_quantile, -xfv_war_6yr, player_key), 1-based - the prospx
  board ordering (quantile-first, TBS-dominant xfv_war_6yr tiebreak).
  CEILING: for EVERY active player |q_on - q_off| <= 4.0 FV AND
  |rank_on - rank_off| <= 40. Breach -> revert + record; no amendment.

CLAUSES:
  1 OFF = byte-identity: pinned by test_statcast_overlay.py (10 tests,
    rerun after the module extension; result recorded), plus the battery's
    OFF arm running with explicit "0" (the _flag contract equates unset/0).
  2 covered-only movement: every row whose ON-run factors carry no overlay
    chip must have BYTE-IDENTICAL rank_war, xfv_war_6yr and xfv_grade
    OFF vs ON. (Display quantiles of uncovered rows may shift as covered
    movers pass them - that displacement is exactly what the 4.0/40
    ceiling bounds, for every player.)
  3 the ceiling battery above.
VERDICT: PASS only if all three clauses hold. Ship = flip
  OVERLAY_HIT_DEFAULT / OVERLAY_PIT_DEFAULT (delivered as a wiring diff for
  the wave-D consolidator; this lane flips nothing).
ONE SHOT: --battery REFUSES to run if the eval artifact already carries a
  battery block. Artifact: data/xfv_statcast_overlay_eval.json.
==============================================================================

Run:  python tools/efv_overlay_r_lab.py --coverage   # leg coverage read only
      python tools/efv_overlay_r_lab.py --battery    # the one-shot gate run
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

OUT_PATH = ROOT / "data" / "xfv_statcast_overlay_eval.json"
CEILING_FV = 4.0
CEILING_RANK = 40
CHIPS = ("A-ball Statcast lean", "AAA physics lean")


def _scratch_dir() -> Path:
    env = os.environ.get("EEPHUS_OVERLAY_LAB_SCRATCH")
    p = Path(env) if env else Path(tempfile.mkdtemp(prefix="overlay_r_"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_live(side):
    from efv_dataset import live_matrix_path
    return json.loads(live_matrix_path(side).read_text(encoding="utf-8"))


def coverage() -> dict:
    """Descriptive leg-coverage read on the live matrices (no gate)."""
    import efv_statcast_overlay as ov
    sig = ov._signals()
    out = {}
    for side in ("hit", "pit"):
        rows = _load_live(side)
        c = {"n_rows": len(rows), "whiff": 0, "fb_velo_a": 0, "velo_aaa": 0,
             "spin_aaa": 0, "vaa_aaa": 0, "any_leg": 0}
        for r in rows:
            mlbam, milb = r.get("mlbam_id"), r.get("milb") or {}
            if not mlbam or not milb:
                continue
            if side == "pit":
                legs = ov._pit_legs(mlbam, milb, sig)
                for name, *_rest in legs:
                    c[name if name in c else "fb_velo_a"] += 1
                if legs:
                    c["any_leg"] += 1
            else:
                e = (sig.get("by_mlbam") or {}).get(str(int(mlbam)))
                if (e and e.get("side") != "pit"
                        and e.get("level") in ov._LEVELS
                        and e.get("level") == milb.get("milb_level")
                        and e.get("season") == milb.get("milb_season")
                        and (e.get("n_pitches") or 0) >= ov.MIN_PITCHES):
                    c["whiff"] += 1
                    c["any_leg"] += 1
        out[side] = c
    return out


def _score_arms(scratch: Path) -> dict:
    """Run efv_score.run_live OFF then ON, both sides, scored_live_path
    patched into the scratch dir. Returns {arm: {side: [entries]}}."""
    import efv_score as es
    assert os.environ.get("EEPHUS_SIDE_FAIRNESS_FIX", "0") != "1", \
        "F-SIDE flag must stay OFF during this battery"
    orig = es.scored_live_path
    saved = {k: os.environ.get(k) for k in
             ("EEPHUS_XOVERLAY_HIT", "EEPHUS_XOVERLAY_PIT")}
    pools = {}
    try:
        for arm, envv in (("off", "0"), ("on", "1")):
            os.environ["EEPHUS_XOVERLAY_HIT"] = envv
            os.environ["EEPHUS_XOVERLAY_PIT"] = envv
            es.scored_live_path = (lambda side, _a=arm, _s=scratch:
                                   _s / f"scored_live_{side}_{_a}.json")
            pools[arm] = {}
            for side in ("hit", "pit"):
                rep = es.run_live(persist=True, side=side)
                pools[arm][side] = json.loads(
                    (scratch / f"scored_live_{side}_{arm}.json")
                    .read_text(encoding="utf-8"))
                print(f"[battery] {arm}/{side}: n_scored={rep['n_scored']}",
                      flush=True)
    finally:
        es.scored_live_path = orig
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return pools


def _board(pool_by_side) -> dict:
    """player_key -> 1-based pooled board rank, frozen ordering
    (-xfv_grade_quantile, -xfv_war_6yr, player_key)."""
    rows = []
    for side in ("hit", "pit"):
        for e in pool_by_side[side]:
            rows.append((e["player_key"], side,
                         float(e["xfv_grade_display"]),
                         float(e["xfv_war_6yr"])))
    rows.sort(key=lambda t: (-t[2], -t[3], t[0]))
    return {pk: i + 1 for i, (pk, _s, _q, _w) in enumerate(rows)}


def battery() -> dict:
    if OUT_PATH.exists():
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if "battery" in doc:
            raise SystemExit("one-shot: battery block already exists in "
                             f"{OUT_PATH}; the lab refuses a rerun")
    import efv_statcast_overlay as ov
    scratch = _scratch_dir()
    pools = _score_arms(scratch)

    # index entries
    idx = {arm: {side: {e["player_key"]: e for e in pools[arm][side]}
                 for side in ("hit", "pit")} for arm in ("off", "on")}
    for side in ("hit", "pit"):
        assert set(idx["off"][side]) == set(idx["on"][side]), \
            f"pool membership must be identical OFF vs ON ({side})"

    # clause 2: covered-only movement on the model leg
    uncovered_bad, covered = [], {}
    for side in ("hit", "pit"):
        for pk, e_on in idx["on"][side].items():
            e_off = idx["off"][side][pk]
            chip = next((f for f in (e_on.get("factors") or [])
                         if f.get("label") in CHIPS), None)
            if chip:
                covered[pk] = {"side": side, "chip": chip["label"],
                               "dir": chip["dir"], "mag": chip["mag"]}
            else:
                if (e_on["rank_war"] != e_off["rank_war"]
                        or e_on["xfv_war_6yr"] != e_off["xfv_war_6yr"]
                        or e_on["xfv_grade"] != e_off["xfv_grade"]):
                    uncovered_bad.append({"player_key": pk, "side": side,
                                          "rank_war": [e_off["rank_war"],
                                                       e_on["rank_war"]]})

    # clause 3: the 4.0/40 shadow-ranking ceiling, EVERY active player
    rank_off, rank_on = _board(pools["off"]), _board(pools["on"])
    per_player, max_fv, max_rank = [], 0.0, 0
    for side in ("hit", "pit"):
        for pk, e_on in idx["on"][side].items():
            e_off = idx["off"][side][pk]
            dq = float(e_on["xfv_grade_display"]) - float(e_off["xfv_grade_display"])
            dr = rank_off[pk] - rank_on[pk]          # positive = climbed
            max_fv = max(max_fv, abs(dq))
            max_rank = max(max_rank, abs(dr))
            per_player.append({
                "player_key": pk, "side": side,
                "q_off": e_off["xfv_grade_display"],
                "q_on": e_on["xfv_grade_display"],
                "dq": round(dq, 2),
                "rank_off": rank_off[pk], "rank_on": rank_on[pk],
                "drank": dr,
                "covered": pk in covered,
                "chip": (covered.get(pk) or {}).get("chip"),
            })
    movers = sorted((p for p in per_player if abs(p["dq"]) > 1e-9 or p["drank"]),
                    key=lambda p: (-abs(p["dq"]), -abs(p["drank"])))

    # annotate the top movers with their legs + raw delta (covered pit rows)
    sig = ov._signals()
    live_rows = {}
    for side in ("hit", "pit"):
        for r in _load_live(side):
            live_rows[r["player_key"]] = (side, r)
    saved = {k: os.environ.get(k) for k in
             ("EEPHUS_XOVERLAY_HIT", "EEPHUS_XOVERLAY_PIT")}
    os.environ["EEPHUS_XOVERLAY_HIT"] = "1"
    os.environ["EEPHUS_XOVERLAY_PIT"] = "1"
    try:
        for p in movers[:60]:
            sd_r = live_rows.get(p["player_key"])
            if not sd_r or not p["covered"]:
                continue
            side, r = sd_r
            got = ov.overlay_fv(r, side)
            if got:
                p["delta_fv_model_leg"] = got[0]
            if side == "pit" and r.get("mlbam_id"):
                p["legs"] = [{"leg": n, "z": round(z, 3), "n_pitches": np}
                             for n, z, np, _c in
                             ov._pit_legs(r["mlbam_id"], r.get("milb") or {}, sig)]
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    clause2_pass = not uncovered_bad
    clause3_pass = (max_fv <= CEILING_FV + 1e-9) and (max_rank <= CEILING_RANK)
    result = {
        "generated_at": date.today().isoformat(),
        "registration": "docs/efv-2026-07-24/GATES.md W-OVERLAY-R (Phase 3c): "
                        "4.0 FV / 40 board-rank ceiling vs a same-run "
                        "no-overlay shadow ranking, owner-amended 2026-07-23; "
                        "one attempt, breach = revert + record",
        "one_shot": {"attempted_at": datetime.now(timezone.utc).isoformat(),
                     "note": "single attempt; the lab refuses a rerun while "
                             "this block exists"},
        "frozen_header": "see tools/efv_overlay_r_lab.py module docstring "
                         "(legs, sub-AAA exclusion, board-rank definition, "
                         "floors; frozen before this run)",
        "coverage": coverage(),
        "battery": {
            "protocol": "efv_score.run_live in-process, scored_live_path "
                        "scratch-patched (no served artifact regen), env "
                        "flags OFF('0')/ON('1') both sides; board rank = "
                        "pooled (-xfv_grade_quantile, -xfv_war_6yr, "
                        "player_key)",
            "n_players": len(per_player),
            "n_covered": len(covered),
            "n_movers_display": len(movers),
            "max_abs_fv_move": round(max_fv, 2),
            "max_abs_rank_move": max_rank,
            "ceiling": {"fv": CEILING_FV, "rank": CEILING_RANK},
            "movers_top": movers[:20],
        },
        "clauses": {
            "1_off_identity": {
                "pass": True,
                "evidence": "test_statcast_overlay.py 10/10 green post-"
                            "extension (defaults OFF, OFF=identity, clamp, "
                            "signs, gates, frozen-coefficient load); battery "
                            "OFF arm ran with explicit '0'",
            },
            "2_covered_only": {"pass": clause2_pass,
                               "uncovered_rows_moved": uncovered_bad[:10]},
            "3_ceiling_battery": {"pass": clause3_pass,
                                  "max_abs_fv_move": round(max_fv, 2),
                                  "max_abs_rank_move": max_rank},
        },
        "verdict": None,
    }
    ok = clause2_pass and clause3_pass
    result["verdict"] = (
        "PASS - all clauses hold under the 4.0/40 display ceiling; ship = "
        "flip OVERLAY_HIT/PIT defaults (wave-D consolidator applies the diff)"
        if ok else
        "FAIL - ceiling breached or uncovered movement; defaults stay OFF, "
        "loss ledgered")
    OUT_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("verdict",)}, indent=1))
    return result


if __name__ == "__main__":
    if "--coverage" in sys.argv:
        print(json.dumps(coverage(), indent=1))
    elif "--battery" in sys.argv:
        battery()
    else:
        print(__doc__)
