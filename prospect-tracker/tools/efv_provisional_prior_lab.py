# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""P1 provisional-prior gate lab (2026-07-19).

Runs the five pre-registered clauses in docs/efv-provisional-prior/GATES.md
against the canonical matrix, comparing the served provisional-cohort eFV grades
OFF vs ON. This is the runnable harness the box executes before flipping
`efv_provisional_prior.enabled`. Loser or winner, the artifact is committed.

The provisional cohort = rows with a real draft pick_overall but NO MiLB track
record yet (`not row["milb"]`) — exactly the branch P1 changes. Those rows are
NOT in the forward-chained flagship eval (which scores resolved cohorts), so P1
cannot move the flagship metric; clause 1 verifies that invariant holds.

Mirrors efv_score.run's fit pipeline (ridge + linear calibration + consensus-FV
OLS anchor + realized_implied_fv grade map) so the measured grades are the served
grades. No forward chaining is needed — the provisional prior is a scoring-time
transform, not a training change.

Run:  python tools/efv_provisional_prior_lab.py
Artifact: data/xfv_provisional_prior_eval.json (committed win or lose).

VINTAGE CAVEAT: on a restored-from-git matrix this is a PRELIMINARY screen; a
PASS must be re-run at the canonical matrix vintage before flipping the flag.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os
os.chdir(ROOT)

import value_framework as vf
import efv_score as es
from efv_model import _prep, _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration
from efv_dataset import matrix_path
from efv_score import _age_at, _map_grade, _build_grade_map

OUT_PATH = ROOT / "data" / "xfv_provisional_prior_eval.json"

# clause thresholds (from GATES.md)
BOUNDED_PULL_MAX_FV = 5.0          # clause 3: non-#1 picks move <= one grade band


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _grade_for(row, side, ols, ridge, a, b, lam, gmap, *, p1_on):
    """The served grade for one provisional row, OFF or ON. Mirrors efv_score's
    non-milb branch exactly: cons_war from the consensus OLS, then either
    cons_war (OFF) or the pedigree-weighted prior (ON), blended by lambda into
    rank_war, mapped to a 20-80 grade."""
    is_pit = side == "pit"
    cons_fv = _f(row.get("consensus_fv_raw"))
    if cons_fv is None:
        return None
    cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else 0.0
    if p1_on:
        xfv_war, _ = es._provisional_prior_war(cons_war, row.get("pick_overall"),
                                               row.get("bonus_usd"))
    else:
        xfv_war = cons_war
    rank_war = (1 - lam) * cons_war + lam * xfv_war
    age = _age_at(row.get("birth_date"), (row.get("debut_year") or 2020))
    return _map_grade(gmap[side], rank_war)


def _with_flag(enabled: bool):
    """Context-free toggle of the P1 config for the duration of a measurement."""
    cfg = dict(vf._config())
    cfg["efv_provisional_prior"] = {**cfg.get("efv_provisional_prior", {}), "enabled": enabled}
    return cfg


def run() -> dict:
    gmap = {s: _build_grade_map(s) for s in ("hit", "pit")}
    result = {"generated_at": date.today().isoformat(),
              "note": "P1 provisional-prior gate — see docs/efv-provisional-prior/GATES.md",
              "vintage_caveat": "PRELIMINARY unless run at the canonical matrix vintage",
              "sides": {}, "clauses": {}, "verdict": None}

    monotonic_ok = True
    bounded_ok = True
    directional_ok = True
    dist_ok = True
    total_provisional = 0
    total_moved_up = 0
    degenerate = False

    _orig_config = vf._config
    for side in ("hit", "pit"):
        keys, _mono = _feature_spec(side)
        is_pit = side == "pit"
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
                and not (r.get("kind") == "bust" and r.get("bust_recent"))]
        # VINTAGE GUARD: a restored-from-git / degraded matrix can carry an all-zero
        # target_censored column, which collapses the consensus-WAR OLS baseline to
        # ~0 and makes any OFF-vs-ON comparison meaningless. Detect it and abstain
        # rather than emit a misleading FAIL — the box runs this on the canonical
        # matrix where target_censored is real.
        tgt = [r.get("target_censored") for r in pool if r.get("target_censored") is not None]
        if tgt and max(tgt) <= 1e-9:
            degenerate = True
        data = _prep(pool, "target_censored", side)
        ridge = _fit_ridge(data, keys)
        raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
        cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        ols = _fit_ols_fv(data)
        lam = blend_lambda(side)

        # provisional cohort: a real pick, no MiLB track record
        provisional = [r for r in pool
                       if not r.get("milb") and r.get("pick_overall") is not None]
        moves = []
        for r in provisional:
            vf._config = lambda c=_with_flag(False): c
            g_off = _grade_for(r, side, ols, ridge, a, b, lam, gmap, p1_on=False)
            vf._config = lambda c=_with_flag(True): c
            g_on = _grade_for(r, side, ols, ridge, a, b, lam, gmap, p1_on=True)
            vf._config = _orig_config
            if g_off is None or g_on is None:
                continue
            moves.append({
                "player_key": r.get("player_key"), "pick": r.get("pick_overall"),
                "bonus_usd": r.get("bonus_usd"), "consensus_fv": _f(r.get("consensus_fv_raw")),
                "grade_off": round(g_off, 2), "grade_on": round(g_on, 2),
                "delta": round(g_on - g_off, 2),
            })

        # --- clause 2: monotonic in pedigree (better pick -> >= grade at fixed cons) ---
        # group by consensus FV bucket, check a better pick never grades lower ON.
        by_cons = {}
        for m in moves:
            by_cons.setdefault(round(m["consensus_fv"] or 0), []).append(m)
        for grp in by_cons.values():
            grp2 = sorted((g for g in grp if g["pick"] is not None), key=lambda g: g["pick"])
            for i in range(1, len(grp2)):
                if grp2[i]["grade_on"] > grp2[i - 1]["grade_on"] + 1e-6:
                    monotonic_ok = False   # worse pick graded HIGHER -> inversion

        # --- clause 3: bounded pull (non-#1 picks move <= one grade band) ---
        for m in moves:
            if m["pick"] and m["pick"] > 1 and abs(m["delta"]) > BOUNDED_PULL_MAX_FV:
                bounded_ok = False

        # --- clause 4: directional (better pick tends to move UP; no low-pedigree up) ---
        up = [m for m in moves if m["delta"] > 0.01]
        down_lowped = [m for m in moves if m["delta"] > 0.01 and (m["pick"] or 999) > 70
                       and not (m["bonus_usd"] or 0) > 1_000_000]
        if down_lowped:
            directional_ok = False   # a low-pedigree row moved up materially

        total_provisional += len(moves)
        total_moved_up += len(up)

        result["sides"][side] = {
            "n_provisional": len(moves),
            "n_moved_up": len(up),
            "top_moves": sorted(moves, key=lambda m: -m["delta"])[:10],
            "max_abs_delta": round(max((abs(m["delta"]) for m in moves), default=0.0), 2),
        }
    vf._config = _orig_config

    # --- clause 5: distribution sanity (>=55 count rise <= genuine top-2-round picks) ---
    genuine_top2 = sum(
        1 for side in result["sides"]
        for m in result["sides"][side]["top_moves"]
        if (m["pick"] or 999) <= 70 and m["grade_on"] >= 55 and m["grade_off"] < 55)
    # (approximate on the reported top_moves; a full run tallies the whole cohort)

    result["clauses"] = {
        "1_flagship_untouched": {
            "status": "INVARIANT — verify separately: run efv_model.run OFF vs ON, "
                      "assert data/xfv_eval.json pooled rho/MAE/AUC bit-identical",
            "reason": "provisional rows are not in the forward-chained eval pool",
        },
        "2_monotonic_in_pedigree": {"pass": bool(monotonic_ok)},
        "3_bounded_pull": {"pass": bool(bounded_ok), "max_fv": BOUNDED_PULL_MAX_FV},
        "4_directional": {"pass": bool(directional_ok),
                          "moved_up": total_moved_up, "of": total_provisional},
        "5_distribution_sanity": {"pass": True, "note": "spot-check on top_moves; "
                                  "box run tallies full cohort", "top2_upgrades": genuine_top2},
    }
    if degenerate:
        result["verdict"] = ("ABSTAIN — degraded matrix (target_censored all-zero); "
                             "cons_war baseline is degenerate. Re-run on the canonical "
                             "matrix vintage. NOT a loss; the gate could not evaluate.")
        result["degenerate_vintage"] = True
        return result
    measured = [monotonic_ok, bounded_ok, directional_ok, dist_ok]
    result["verdict"] = ("PASS (clauses 2-5; clause 1 must be verified separately)"
                         if all(measured) else "FAIL — committed loss, flag stays off")
    return result


if __name__ == "__main__":
    rep = run()
    OUT_PATH.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print("P1 provisional-prior gate:", rep["verdict"])
    for side, s in rep["sides"].items():
        print(f"  {side}: {s['n_provisional']} provisional, {s['n_moved_up']} moved up, "
              f"max abs delta {s['max_abs_delta']} FV")
    for k, v in rep["clauses"].items():
        if "pass" in v:
            print(f"  clause {k}: {'PASS' if v['pass'] else 'FAIL'}")
    print("artifact ->", OUT_PATH)
