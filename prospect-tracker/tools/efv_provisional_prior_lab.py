# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""P1 provisional-prior gate lab. V1 registered 2026-07-19 (FAIL 2026-07-23,
committed loss); V2 re-registered 2026-07-23 in docs/efv-provisional-prior/GATES.md
BEFORE this harness was run at the V2 vintage.

Runs the pre-registered clauses against the matrix, comparing the served
provisional-cohort eFV grades OFF vs ON. The provisional cohort = rows with a real
draft pick_overall but NO MiLB track record yet (the branch P1 changes). Those rows
are NOT in the forward-chained flagship eval, so P1 cannot move the flagship metric;
clause 1 verifies that invariant holds (run with --clause1).

V2 lab changes (all registered in GATES.md V2 before running, none post-hoc):
  - clause 2 tests the REGISTERED pedigree partial order (within exact consensus FV,
    pick_i <= pick_j AND bonus_i >= bonus_j implies grade_on_i >= grade_on_j - 1e-6).
    The V1 lab sorted rounded-FV buckets on pick alone, comparing incomparable
    pedigrees; that was a mis-operationalization, fixed here, tolerance unchanged.
  - clause 4 checks the named LIVE movers (roch_cholowsky, aj_gracia) move UP, and
    no low-pedigree row (pick > 70, bonus <= $1M) rises more than +2.0 FV.
  - clause 5 tallies the FULL cohort (V1 only spot-checked top_moves).
  - sub-$1M IFA invariance is verified explicitly (no-pick rows never move unless
    the separately-gated >= $1M step is wired).

V3 section (GATES.md V3 registration 2026-07-23, the Grady Emerson case; frozen
before this harness ran; one attempt per arm; seed 20260723, 2000 player-clustered
bootstrap reps). Arms are env flags, default OFF, read at call time:
  ARM-A  EEPHUS_P1_SLOT_TRUST  slot_usd stands in for a missing bonus in the
         log-TRUST term (current-class unsigned picks only).
  ARM-B  EEPHUS_P1_DSPLUS      ped += 0.4 * max(0, (DSplus - 100) / 10).
  ARM-C  both flags.
V3 bars (frozen): A1/B1-pooled no-harm delta-Spearman lo95 >= -0.005 on the
804-draftee resolved backtest; B1-covered gain lo95 > 0 on the DSplus-covered
resolved subcohort (STOP-B: covered n < 60 -> COVERAGE-STARVED, arm stays OFF);
A2/B3 live battery ceiling 3.0 FV on the implied served-quantile move, every move
upward, ARM-A movers restricted to missing-bonus drafted rows; B2 prior
non-decreasing in DSplus within pick tier; A3/B4 flag-OFF bit-identity vs the
committed V2 math.

Run:  python tools/efv_provisional_prior_lab.py             # clauses 2-5 + movers
      python tools/efv_provisional_prior_lab.py --clause1   # flagship bit-identity
      python tools/efv_provisional_prior_lab.py --ifa-step  # IFA $1M-step LOCO gate
      python tools/efv_provisional_prior_lab.py --v3        # V3 gated arms A/B/C

Artifacts: data/xfv_provisional_prior_eval.json (committed win or lose; --v3
           appends a "v3" block, existing blocks untouched);
           data/ifa_step_prior_eval.json (the IFA step arm's own ledger).

VINTAGE CAVEAT: on a restored-from-git matrix this is a PRELIMINARY screen; a PASS
must be re-run at the canonical matrix vintage before flipping the flag. The lab
ABSTAINS (not FAIL) when it detects a degenerate target_censored column.
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
from efv_score import _map_grade, _build_grade_map

OUT_PATH = ROOT / "data" / "xfv_provisional_prior_eval.json"
IFA_OUT_PATH = ROOT / "data" / "ifa_step_prior_eval.json"

# clause thresholds (GATES.md; V2 registration 2026-07-23)
BOUNDED_PULL_MAX_FV = 5.0      # clause 3: any pick > 1 moves <= one grade band
LOWPED_RISER_MAX_FV = 2.0      # clause 4: low-pedigree riser bound (V2 registration)
LOWPED_PICK = 70               # low-pedigree = pick > 70 ...
LOWPED_BONUS = 1_000_000       # ... and bonus <= $1M
NAMED_MOVERS = ("roch_cholowsky", "aj_gracia")          # clause 4 directional cases
IFA_MOVERS = ("roki_sasaki", "fabricio_blanco", "jose_luis_acevedo")
IFA_SEED = 20260723
IFA_N_BOOT = 10_000


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _grade_for(row, side, ols, lam, gmap, *, p1_on, cfg_over=None):
    """The served grade for one provisional row, OFF or ON. Mirrors efv_score's
    non-milb branch exactly: cons_war from the consensus OLS, then either cons_war
    (OFF) or the pedigree prior (ON), blended by lambda into rank_war, mapped to a
    20-80 display grade. V2 passes cons_fv + is_pitcher (the Fix B baseline)."""
    cons_fv = _f(row.get("consensus_fv_raw"))
    if cons_fv is None:
        return None
    cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else 0.0
    if p1_on:
        xfv_war, _ = es._provisional_prior_war(cons_war, row.get("pick_overall"),
                                               row.get("bonus_usd"),
                                               cons_fv=cons_fv,
                                               is_pitcher=(side == "pit"))
    else:
        xfv_war = cons_war
    rank_war = (1 - lam) * cons_war + lam * xfv_war
    return _map_grade(gmap[side], rank_war)


def _with_flag(enabled: bool, **over):
    """Config copy with the P1 flag (and optional overrides) set."""
    cfg = dict(vf._config())
    cfg["efv_provisional_prior"] = {**cfg.get("efv_provisional_prior", {}),
                                    "enabled": enabled, **over}
    return cfg


def _fit_side(side):
    is_pit = side == "pit"
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    ridge = _fit_ridge(data, keys)
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    ols = _fit_ols_fv(data)
    return pool, ols, blend_lambda(side)


def _live_named_rows():
    """(player_key, side, cons_fv, pick, bonus, method) for the named live movers,
    from timeseries latest snapshot + the acquisitions sidecar (read-only DB)."""
    import sqlite3
    keys = set(NAMED_MOVERS) | set(IFA_MOVERS)
    acq = {}
    try:
        con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
        cur = con.cursor()
        qmarks = ",".join("?" * len(keys))
        cur.execute(f"SELECT player_key, method, pick_overall, bonus_usd "
                    f"FROM acquisitions WHERE player_key IN ({qmarks})", tuple(keys))
        for pk, method, pick, bonus in cur.fetchall():
            acq[pk] = (method, pick, bonus)
        con.close()
    except sqlite3.Error:
        return []
    ts_path = ROOT / "data" / "timeseries.json"
    if not ts_path.exists():
        return []
    out = []
    for p in (json.loads(ts_path.read_text(encoding="utf-8")).get("players") or []):
        pk = p.get("player_key")
        if pk not in keys or pk not in acq:
            continue
        pts = [pt for pt in (p.get("points") or [])
               if _f(pt.get("consensus_fv_raw")) is not None and pt.get("snapshot_date")]
        if not pts:
            continue
        last = max(pts, key=lambda pt: pt["snapshot_date"])
        side = "pit" if (p.get("position") or "").upper().startswith("P") else "hit"
        method, pick, bonus = acq[pk]
        out.append({"player_key": pk, "side": side,
                    "consensus_fv_raw": _f(last.get("consensus_fv_raw")),
                    "pick_overall": pick, "bonus_usd": bonus, "method": method})
    return out


def run() -> dict:
    gmap = {s: _build_grade_map(s) for s in ("hit", "pit")}
    result = {"generated_at": date.today().isoformat(),
              "note": "P1 provisional-prior gate V2 - see docs/efv-provisional-prior/"
                      "GATES.md (V2 re-registration 2026-07-23, frozen before this run)",
              "vintage_caveat": "PRELIMINARY unless run at the canonical matrix vintage",
              "registration": {
                  "formula": "prior = cons_war + w * clip(slot_war - max(cons_war, "
                             "6*expected_six_year_avg_war(cons_fv)), 0, pull_cap_war)",
                  "pull_cap_war": 1.9,
                  "derivation": "min over sides of d*(5.0 FV)/(lam*w_max): "
                                "hit 1.226/(0.70*0.75)=2.335, pit 0.7435/(0.52*0.75)"
                                "=1.906 -> frozen 1.9 (GATES.md V2)",
              },
              "sides": {}, "clauses": {}, "live_movers": [], "verdict": None}

    monotonic_ok = True
    monotone_violations = []
    bounded_ok = True
    lowped_ok = True
    lowped_max_delta = 0.0
    total_provisional = 0
    total_moved_up = 0
    n55_off = n55_on = 0
    crossers = []
    top2_in_cohort = 0
    ifa_moved = []          # sub-$1M invariance: no-pick rows that moved (must be none)
    degenerate = False

    _orig_config = vf._config
    for side in ("hit", "pit"):
        pool, ols, lam = _fit_side(side)
        # VINTAGE GUARD: a restored-from-git / degraded matrix can carry an all-zero
        # target_censored column, which collapses the consensus-WAR OLS baseline to
        # ~0 and makes any OFF-vs-ON comparison meaningless. Abstain, never FAIL.
        tgt = [r.get("target_censored") for r in pool if r.get("target_censored") is not None]
        if tgt and max(tgt) <= 1e-9:
            degenerate = True

        provisional = [r for r in pool
                       if not r.get("milb") and r.get("pick_overall") is not None]
        top2_in_cohort += sum(1 for r in provisional if (r["pick_overall"] or 999) <= 70)
        # sub-$1M IFA invariance cohort: provisional rows with NO pick (all matrix
        # IFA-with-bonus rows are < $1M as of registration; the step is not wired
        # here, so every one of them must be bit-identical OFF vs ON).
        no_pick = [r for r in pool if not r.get("milb") and r.get("pick_overall") is None
                   and _f(r.get("consensus_fv_raw")) is not None]
        moves = []
        for r in provisional:
            vf._config = lambda c=_with_flag(False): c
            g_off = _grade_for(r, side, ols, lam, gmap, p1_on=False)
            vf._config = lambda c=_with_flag(True): c
            g_on = _grade_for(r, side, ols, lam, gmap, p1_on=True)
            vf._config = _orig_config
            if g_off is None or g_on is None:
                continue
            moves.append({
                "player_key": r.get("player_key"), "pick": r.get("pick_overall"),
                "bonus_usd": r.get("bonus_usd"), "consensus_fv": _f(r.get("consensus_fv_raw")),
                "grade_off": round(g_off, 2), "grade_on": round(g_on, 2),
                "delta": round(g_on - g_off, 2),
            })
        for r in no_pick:
            vf._config = lambda c=_with_flag(False): c
            g_off = _grade_for(r, side, ols, lam, gmap, p1_on=False)
            vf._config = lambda c=_with_flag(True): c
            g_on = _grade_for(r, side, ols, lam, gmap, p1_on=True)
            vf._config = _orig_config
            if g_off is not None and g_on is not None and abs(g_on - g_off) > 1e-9:
                ifa_moved.append({"player_key": r.get("player_key"), "side": side,
                                  "delta": round(g_on - g_off, 3)})

        # --- clause 2 (V2): pedigree partial order within EXACT consensus FV ------
        # comparable iff pick_i <= pick_j AND bonus_i >= bonus_j (missing bonus = 0,
        # matching the model's own precision inputs); then grade_on_i must be >=.
        by_fv = {}
        for m in moves:
            by_fv.setdefault(round(m["consensus_fv"] or 0.0, 2), []).append(m)
        for fv, grp in by_fv.items():
            for i in range(len(grp)):
                for j in range(len(grp)):
                    if i == j:
                        continue
                    a_, b_ = grp[i], grp[j]
                    if (a_["pick"] or 9999) <= (b_["pick"] or 9999) and \
                       (a_["bonus_usd"] or 0) >= (b_["bonus_usd"] or 0):
                        if a_["grade_on"] < b_["grade_on"] - 1e-6:
                            monotonic_ok = False
                            monotone_violations.append(
                                {"fv": fv, "side": side,
                                 "dominant": a_["player_key"], "dominated": b_["player_key"],
                                 "grades": [a_["grade_on"], b_["grade_on"]]})

        # --- clause 3: bounded pull (any pick > 1 moves <= one grade band) --------
        for m in moves:
            if m["pick"] and m["pick"] > 1 and abs(m["delta"]) > BOUNDED_PULL_MAX_FV:
                bounded_ok = False

        # --- clause 4b: no low-pedigree riser above +2.0 FV ------------------------
        for m in moves:
            if (m["pick"] or 999) > LOWPED_PICK and not (m["bonus_usd"] or 0) > LOWPED_BONUS:
                lowped_max_delta = max(lowped_max_delta, m["delta"])
                if m["delta"] > LOWPED_RISER_MAX_FV:
                    lowped_ok = False

        # --- clause 5: FULL-cohort >= 55 tally -------------------------------------
        n55_off += sum(1 for m in moves if m["grade_off"] >= 55)
        n55_on += sum(1 for m in moves if m["grade_on"] >= 55)
        crossers.extend(m for m in moves if m["grade_on"] >= 55 and m["grade_off"] < 55)

        up = [m for m in moves if m["delta"] > 0.01]
        total_provisional += len(moves)
        total_moved_up += len(up)
        result["sides"][side] = {
            "n_provisional": len(moves),
            "n_moved_up": len(up),
            "n_no_pick_checked": len(no_pick),
            "top_moves": sorted(moves, key=lambda m: -m["delta"])[:10],
            "max_abs_delta": round(max((abs(m["delta"]) for m in moves), default=0.0), 2),
        }
    vf._config = _orig_config

    # --- clause 4a: named live movers (backgrade-path construction) ----------------
    named_up_ok = True
    fits = {}
    for row in _live_named_rows():
        side = row["side"]
        if side not in fits:
            _pool, ols, lam = _fit_side(side)
            fits[side] = (ols, lam)
        ols, lam = fits[side]
        is_draft = row["pick_overall"] is not None
        vf._config = lambda c=_with_flag(False): c
        g_off = _grade_for(row, side, ols, lam, gmap, p1_on=False)
        vf._config = lambda c=_with_flag(True): c
        g_on = _grade_for(row, side, ols, lam, gmap, p1_on=True)
        vf._config = _orig_config
        entry = {"player_key": row["player_key"], "side": side, "method": row["method"],
                 "consensus_fv": row["consensus_fv_raw"], "pick": row["pick_overall"],
                 "bonus_usd": row["bonus_usd"],
                 "grade_off": None if g_off is None else round(g_off, 2),
                 "grade_on": None if g_on is None else round(g_on, 2),
                 "delta": None if (g_off is None or g_on is None) else round(g_on - g_off, 2)}
        if row["player_key"] in IFA_MOVERS:
            # candidate read for the step arm: what WOULD it do if wired (uses the
            # validated first6 step mean from the IFA artifact when present).
            step_war = None
            if IFA_OUT_PATH.exists():
                try:
                    step_war = (json.loads(IFA_OUT_PATH.read_text(encoding="utf-8"))
                                .get("consumable") or {}).get("ifa_step_war")
                except (OSError, ValueError):
                    step_war = None
            if step_war is not None:
                vf._config = lambda c=_with_flag(True, ifa_step_enabled=True,
                                                 ifa_step_war=step_war): c
                g_cand = _grade_for(row, side, ols, lam, gmap, p1_on=True)
                vf._config = _orig_config
                entry["ifa_step_candidate_grade"] = (None if g_cand is None
                                                     else round(g_cand, 2))
                entry["ifa_step_war_used"] = step_war
            else:
                entry["ifa_step_candidate_grade"] = None
                entry["note"] = "ifa step artifact absent; candidate read skipped"
        elif row["player_key"] in NAMED_MOVERS:
            if entry["delta"] is None or entry["delta"] <= 0:
                named_up_ok = False
        result["live_movers"].append(entry)
    vf._config = _orig_config
    named_found = {e["player_key"] for e in result["live_movers"]}
    for pk in NAMED_MOVERS:
        if pk not in named_found:
            named_up_ok = False          # a named case missing = cannot verify = fail

    crossers_all_top2 = all((m["pick"] or 999) <= 70 for m in crossers)
    dist_ok = crossers_all_top2 and (n55_on - n55_off) <= top2_in_cohort

    result["clauses"] = {
        "1_flagship_untouched": {
            "status": "INVARIANT - verified separately (--clause1): efv_model.run "
                      "OFF vs ON, metric blocks bit-identical",
            "reason": "provisional rows are not in the forward-chained eval pool",
        },
        "2_monotonic_in_pedigree": {"pass": bool(monotonic_ok),
                                    "operationalization": "pedigree partial order "
                                    "within exact consensus FV (V2 registration)",
                                    "violations": monotone_violations[:10]},
        "3_bounded_pull": {"pass": bool(bounded_ok), "max_fv": BOUNDED_PULL_MAX_FV},
        "4_directional": {"pass": bool(lowped_ok and named_up_ok),
                          "named_movers_up": bool(named_up_ok),
                          "lowped_riser_bound": LOWPED_RISER_MAX_FV,
                          "lowped_max_delta": round(lowped_max_delta, 2),
                          "moved_up": total_moved_up, "of": total_provisional},
        "5_distribution_sanity": {"pass": bool(dist_ok),
                                  "n55_off": n55_off, "n55_on": n55_on,
                                  "crossers": [{k: m[k] for k in
                                                ("player_key", "pick", "grade_off",
                                                 "grade_on")} for m in crossers],
                                  "top2_round_picks_in_cohort": top2_in_cohort},
        "ifa_sub1m_invariance": {"pass": not ifa_moved, "moved": ifa_moved[:10],
                                 "note": "no-pick provisional rows must be "
                                         "bit-identical (step not wired in this run)"},
    }
    if degenerate:
        result["verdict"] = ("ABSTAIN - degraded matrix (target_censored all-zero); "
                             "cons_war baseline is degenerate. Re-run on the canonical "
                             "matrix vintage. NOT a loss; the gate could not evaluate.")
        result["degenerate_vintage"] = True
        return result
    measured = [monotonic_ok, bounded_ok, lowped_ok and named_up_ok, dist_ok,
                not ifa_moved]
    result["verdict"] = ("PASS (clauses 2-5; clause 1 verified separately via --clause1)"
                         if all(measured) else "FAIL - committed loss, flag stays off")
    return result


# ------------------------------------------------------------------ clause 1 ----
def run_clause1() -> dict:
    """Flagship bit-identity: efv_model.run(persist=False) OFF vs ON, both sides.
    Compares the deterministic metric blocks (evals, era split, lambda calibration,
    feature diagnostics) as canonical JSON strings. Updates the committed artifact's
    clause-1 block in place."""
    import efv_model
    _orig_config = vf._config
    out = {"checked_at": date.today().isoformat(), "sides": {}, "identical": True}
    for side in ("hit", "pit"):
        blocks = {}
        for label, enabled in (("off", False), ("on", True)):
            vf._config = lambda c=_with_flag(enabled): c
            try:
                rep = efv_model.run(persist=False, side=side)
            finally:
                vf._config = _orig_config
            blocks[label] = json.dumps(
                {k: rep.get(k) for k in ("evals", "era_split_debuted",
                                         "lambda_calibration",
                                         "feature_diagnostics_full_window")},
                sort_keys=True)
        same = blocks["off"] == blocks["on"]
        out["sides"][side] = {"identical": bool(same),
                              "bytes": len(blocks["off"])}
        if not same:
            out["identical"] = False
    if OUT_PATH.exists():
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        doc.setdefault("clauses", {})["1_flagship_untouched"] = {
            "pass": bool(out["identical"]),
            "measured": out,
            "reason": "provisional rows are not in the forward-chained eval pool",
        }
        OUT_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return out


# ------------------------------------------------------------- IFA step gate ----
def _load_ifa_lab():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ifa_pedigree_lab", ROOT / "tools" / "ifa_pedigree_lab.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_ifa_step(persist: bool = True) -> dict:
    """IFA >= $1M step arm validation (GATES.md IFA-step registration, 2026-07-23,
    frozen before this run). Reuses tools/ifa_pedigree_lab.py's cohort construction
    verbatim (READ-ONLY import; classes 2012-2017, same dedup/matching/QA), then runs
    the LOCO-by-class protocol restricted to the step boundary. Seed 20260723."""
    import numpy as np
    lab = _load_ifa_lab()
    rows, acct = lab.load_cohort()
    wp = lab.war_players()
    acct.update(lab.assign_outcomes(rows, wp))
    step_min = 1_000_000

    def _means(rs, key):
        hi = [r[key] for r in rs if r["bonus_usd"] >= step_min]
        lo = [r[key] for r in rs if r["bonus_usd"] < step_min]
        return ((sum(hi) / len(hi)) if hi else None,
                (sum(lo) / len(lo)) if lo else None, len(hi), len(lo))

    # LOCO: per-fold training two-level means; direction stability; held-out pool
    folds, direction_stable = {}, True
    held_pred, held_out = [], []
    for y in lab.CLASSES:
        train = [r for r in rows if r["year"] != y]
        test = [r for r in rows if r["year"] == y]
        hi_m, lo_m, n_hi, n_lo = _means(train, "war_window")
        stable = (hi_m is not None and lo_m is not None and hi_m > lo_m)
        if not stable:
            direction_stable = False
        t_hi, t_lo, tn_hi, tn_lo = _means(test, "war_window")
        folds[str(y)] = {"train_hi_mean": round(hi_m, 3), "train_lo_mean": round(lo_m, 3),
                         "train_direction_ok": bool(stable),
                         "heldout_hi_mean": None if t_hi is None else round(t_hi, 3),
                         "heldout_lo_mean": None if t_lo is None else round(t_lo, 3),
                         "heldout_diff": (None if (t_hi is None or t_lo is None)
                                          else round(t_hi - t_lo, 3)),
                         "n_hi": tn_hi, "n_lo": tn_lo}
        for r in test:
            held_pred.append(hi_m if r["bonus_usd"] >= step_min else lo_m)
            held_out.append(r["war_window"])
    rho_step = lab.spearman(held_pred, held_out)
    rho_lo95, rho_hi95 = lab.boot_ci(held_pred, held_out)

    # pooled step-boundary read (THE gate): hi-lo mean diff, bootstrap, both bases
    def _boundary(key):
        hi = np.array([r[key] for r in rows if r["bonus_usd"] >= step_min])
        lo = np.array([r[key] for r in rows if r["bonus_usd"] < step_min])
        rng = np.random.RandomState(IFA_SEED)
        diffs = np.empty(IFA_N_BOOT)
        for b in range(IFA_N_BOOT):
            diffs[b] = (hi[rng.randint(0, len(hi), len(hi))].mean()
                        - lo[rng.randint(0, len(lo), len(lo))].mean())
        return {"hi_mean": round(float(hi.mean()), 3), "n_hi": int(len(hi)),
                "lo_mean": round(float(lo.mean()), 3), "n_lo": int(len(lo)),
                "diff": round(float(hi.mean() - lo.mean()), 3),
                "diff_ci95": [round(float(np.percentile(diffs, 2.5)), 3),
                              round(float(np.percentile(diffs, 97.5)), 3)]}

    window = _boundary("war_window")
    first6 = _boundary("war_first6")

    # sensitivities (reported, never gating; protocol-inherited)
    _POSTED_PRO = {"Japan", "South Korea", "Korea", "Taiwan"}
    amateur = [r for r in rows if (r.get("country") or "?") not in _POSTED_PRO]
    cuba = [r for r in rows if (r.get("country") or "?") == "Cuba"]
    noncuba = [r for r in rows if (r.get("country") or "?") != "Cuba"]
    early = [r for r in rows if r["year"] <= 2014]

    def _diff_only(rs, key):
        hi_m, lo_m, n_hi, n_lo = _means(rs, key)
        return {"hi_mean": None if hi_m is None else round(hi_m, 3),
                "lo_mean": None if lo_m is None else round(lo_m, 3),
                "diff": (None if (hi_m is None or lo_m is None)
                         else round(hi_m - lo_m, 3)),
                "n_hi": n_hi, "n_lo": n_lo}

    gate_window = window["diff_ci95"][0] > 0
    gate_first6 = first6["diff_ci95"][0] > 0
    validation_pass = gate_window and gate_first6 and direction_stable

    # P1 V2 status (the wiring precondition); read from the committed artifact.
    p1_pass = False
    p1_verdict = "artifact absent"
    if OUT_PATH.exists():
        try:
            p1_verdict = (json.loads(OUT_PATH.read_text(encoding="utf-8"))
                          .get("verdict") or "")
            p1_pass = p1_verdict.startswith("PASS")
        except (OSError, ValueError):
            pass

    ev = {
        "generated_at": date.today().isoformat(),
        "experiment": "IFA >= $1M step prior (P1 V2 companion; the ifa_pedigree "
                      "ledger's one robust structure, pre-registered as its own arm)",
        "registration": "docs/efv-provisional-prior/GATES.md, IFA $1M-step section "
                        "(2026-07-23, frozen before this run); seed 20260723",
        "protocol": {
            "cohort": "identical to tools/ifa_pedigree_lab.py (Spotrac classes "
                      "2012-2017, same dedup/matching/QA amendments)",
            "boundary_usd": step_min,
            "gate": "pooled step-boundary read lo95 > 0 (window basis) AND first6 "
                    "lo95 > 0 (wiring units clause) AND train direction hi > lo in "
                    "all 6 LOCO folds",
            "consumable": "first6-basis >= $1M mean (the P1 blend axis)",
        },
        "accounting": {k: v for k, v in acct.items() if k != "qa_disagreements"},
        "loco_folds": folds,
        "direction_stable_all_folds": bool(direction_stable),
        "heldout_step_predictor": {
            "pooled_spearman": round(rho_step, 4),
            "bootstrap_ci95": [round(rho_lo95, 4), round(rho_hi95, 4)],
            "note": "two-level train-mean predictor vs held-out outcomes (reported)",
        },
        "step_boundary_window": window,
        "step_boundary_first6": first6,
        "sensitivity": {
            "posted_pro_excluded_window": _diff_only(amateur, "war_window"),
            "posted_pro_excluded_first6": _diff_only(amateur, "war_first6"),
            "cuba_window": _diff_only(cuba, "war_window"),
            "noncuba_window": _diff_only(noncuba, "war_window"),
            "first6_2012_2014_only": _diff_only(early, "war_first6"),
        },
        "caveats": [
            "first6 basis is right-censored for late debuts of the 2016-17 classes; "
            "the 2012-2014-only refit is the censoring check (conservative-at-top).",
            "the >= $1M group includes posted NPB/KBO professionals (Ohtani-class); "
            "in the served branch high-FV posted pros get pull 0 by construction "
            "(ref_war >> step mean), so the constant only lifts LOW-FV signees; the "
            "posted-pro-excluded sensitivity is the honest mean for that population.",
            "tracker-listed cohort skews to larger bonuses; sub-$1M mass is "
            "near-uniformly 0 WAR, which if anything UNDERSTATES the step.",
        ],
        "gates": {
            "window_lo95_gt_0": bool(gate_window),
            "first6_lo95_gt_0": bool(gate_first6),
            "direction_stable_all_folds": bool(direction_stable),
            "validation_pass": bool(validation_pass),
        },
        "p1_v2_precondition": {"verdict": p1_verdict, "pass": bool(p1_pass)},
        "consumable": {
            "ifa_step_war": first6["hi_mean"],
            "basis": "first6 (P1 blend axis)",
            "posted_pro_excluded_alternative": (_diff_only(amateur, "war_first6")
                                                or {}).get("hi_mean"),
        },
        "wiring_decision": None,
    }
    ev["wiring_decision"] = (
        "WIRE (ifa_step_enabled: true + ifa_step_war into config)"
        if (validation_pass and p1_pass) else
        ("LEDGER ONLY - validation passed but P1 V2 did not flip (no consumer)"
         if validation_pass else
         "LEDGER ONLY - validation failed, ifa_step_enabled stays false"))
    if persist:
        IFA_OUT_PATH.write_text(json.dumps(ev, indent=1), encoding="utf-8")
    return ev


# ------------------------------------------------------------------ V3 arms ----
# GATES.md V3 registration (2026-07-23), frozen before this section ran.
V3_SEED = 20260723
V3_NBOOT = 2000
V3_NOHARM_LO95 = -0.005     # A1 + B1-pooled no-harm bar on delta Spearman
V3_CEILING_FV = 3.0         # A2/B3 implied served-quantile move ceiling
V3_STOPB_MIN_N = 60         # STOP-B: DSplus-covered resolved subcohort minimum
V3_DSPLUS_SCALE = 0.4       # frozen a-priori: ped += 0.4 * max(0,(ds-100)/10)
V3_ARM_FLAGS = {
    "OFF": {},
    "A": {"EEPHUS_P1_SLOT_TRUST": True},
    "B": {"EEPHUS_P1_DSPLUS": True},
    "C": {"EEPHUS_P1_SLOT_TRUST": True, "EEPHUS_P1_DSPLUS": True},
}
_V3_NAMED = "grady_emerson"     # the registration's named live example


def _v3_env(flags):
    """Context manager: set the arm's env flags, restore on exit. The V3
    mechanism reads the environment at call time, so this is the whole switch."""
    import os
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        old = {}
        for k in ("EEPHUS_P1_SLOT_TRUST", "EEPHUS_P1_DSPLUS"):
            old[k] = os.environ.get(k)
            if flags.get(k):
                os.environ[k] = "1"
            else:
                os.environ.pop(k, None)
        try:
            yield
        finally:
            for k, prev in old.items():
                if prev is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = prev
    return _cm()


def _v3_inject(slot_by_pick=None, dsplus_by_key=None):
    """Backtest-substrate injection: hand the production lookup its per-row
    values (the row's OWN slot dollars / own-class DSplus) so the REAL scoring
    code path is exercised on resolved rows without the live identity join."""
    es._provisional_prior_war._p1v3_cache = {
        "slot_by_pick": dict(slot_by_pick or {}),
        "dsplus_by_key": dict(dsplus_by_key or {})}


def _v3_reset_cache():
    es._provisional_prior_war._p1v3_cache = None


def _v3_rankdata(a):
    import numpy as np
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


def _v3_spearman(x, y):
    import math
    rx, ry = _v3_rankdata(x), _v3_rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    den = math.sqrt(float((rx ** 2).sum()) * float((ry ** 2).sum()))
    return float((rx * ry).sum() / den) if den > 0 else float("nan")


def _v3_boot_delta(arm_scores, base_scores, y, idx=None):
    """Player-clustered bootstrap of delta Spearman (arm vs base). One row per
    player in the substrate (asserted by the caller), so a row resample IS the
    player-clustered resample. Seed and rep count are frozen constants."""
    import numpy as np
    arm_scores = np.asarray(arm_scores, dtype=float)
    base_scores = np.asarray(base_scores, dtype=float)
    y = np.asarray(y, dtype=float)
    if idx is None:
        idx = np.arange(len(y))
    idx = np.asarray(idx)
    point = (_v3_spearman(arm_scores[idx], y[idx])
             - _v3_spearman(base_scores[idx], y[idx]))
    rng = np.random.default_rng(V3_SEED)
    m = len(idx)
    deltas = np.empty(V3_NBOOT)
    for t in range(V3_NBOOT):
        take = idx[rng.integers(0, m, m)]
        deltas[t] = (_v3_spearman(arm_scores[take], y[take])
                     - _v3_spearman(base_scores[take], y[take]))
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return {"n": int(m), "delta_point": round(point, 6),
            "delta_boot_mean": round(float(deltas.mean()), 6),
            "ci95": [round(float(lo), 6), round(float(hi), 6)],
            "p_gt0": round(float((deltas > 0).mean()), 4)}


_V3_PIT_POS = {"P", "RHP", "LHP", "SP", "RP", "PITCHER"}


def _v3_side_of(pos):
    import re
    if not pos:
        return None
    toks = re.split(r"[/\s,]+", str(pos).upper().strip())
    return "pit" if any(t in _V3_PIT_POS for t in toks) else "hit"


def _v3_class_dsplus(cur, year):
    """Historical per-class rank-consensus DS+ from draft_snapshots: latest
    rank per source, equal-mean consensus (round 2), class-normalized through
    the production draft_export._stock_plus. Boards for 2018+ classes are the
    backfilled final PRE-DRAFT vintages (pre-signing information only)."""
    from draft_export import _stock_plus
    per_src = {}
    for pk, src, d, rk in cur.execute(
            "SELECT player_key, source, snapshot_date, rank FROM draft_snapshots "
            "WHERE draft_year=? AND rank IS NOT NULL", (year,)):
        k = (pk, src)
        prev = per_src.get(k)
        if prev is None or (d or "") >= (prev[0] or ""):
            per_src[k] = (d, float(rk))
    ranks = {}
    for (pk, _s), (_d, rk) in per_src.items():
        ranks.setdefault(pk, []).append(rk)
    cons = {pk: round(sum(v) / len(v), 2) for pk, v in ranks.items()}
    lst = sorted(cons.values())
    return {pk: _stock_plus(r, lst) for pk, r in cons.items()}


def _v3_build_cohort():
    """The 804-draftee resolved substrate, rebuilt exactly the way the V2-era
    backtest built it (scripts recorded in the 2026-07-23 planning session):
    signed-era draftees 2011-2019 from acquisitions (latest class per player),
    near-draft consensus FV = earliest fv-notnull prospect snapshot in
    [Jun 1 draft year, Dec 31 next year] (same-day sources equal-mean), outcome
    WAR = career_war seasons draft_year+1 .. draft_year+7 (no row = 0). V3
    additions: slot_usd from draft_results, own-class DSplus for 2018/2019."""
    import sqlite3
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    acq = {}
    for r in cur.execute(
            "SELECT player_key, year, pick_overall, bonus_usd FROM acquisitions "
            "WHERE method='draft' AND pick_overall IS NOT NULL "
            "AND year BETWEEN 2011 AND 2019"):
        pk = r["player_key"]
        prev = acq.get(pk)
        if prev is None or (r["year"], -(r["pick_overall"] or 9e9)) > (
                prev["year"], -(prev["pick_overall"] or 9e9)):
            acq[pk] = dict(r)

    dr_by_pk, dr_by_pick = {}, {}
    for r in cur.execute(
            "SELECT draft_year, pick_overall, player_key, bonus_usd, slot_usd "
            "FROM draft_results WHERE draft_year BETWEEN 2011 AND 2019"):
        if r["player_key"]:
            dr_by_pk[(r["player_key"], r["draft_year"])] = dict(r)
        dr_by_pick[(r["draft_year"], r["pick_overall"])] = dict(r)

    ds_by_class = {y: _v3_class_dsplus(cur, y) for y in (2018, 2019)}

    cohort = []
    for pk, a in acq.items():
        y = a["year"]
        rows = cur.execute(
            "SELECT snapshot_date, position, fv FROM snapshots "
            "WHERE player_key=? AND fv IS NOT NULL AND snapshot_date>=? "
            "AND snapshot_date<=? ORDER BY snapshot_date",
            (pk, f"{y}-06-01", f"{y + 1}-12-31")).fetchall()
        if not rows:
            continue
        d0 = rows[0]["snapshot_date"]
        same_day = [r for r in rows if r["snapshot_date"] == d0]
        fv = sum(r["fv"] for r in same_day) / len(same_day)
        side = _v3_side_of(next((r["position"] for r in same_day
                                 if r["position"]), None))
        if side is None:
            continue
        bonus = a["bonus_usd"]
        drr = dr_by_pk.get((pk, y)) or dr_by_pick.get((y, a["pick_overall"]))
        if bonus is None and drr:
            bonus = drr["bonus_usd"]
        dk = drr["player_key"] if drr else None
        dsplus = (ds_by_class.get(y) or {}).get(dk) if dk else None
        cohort.append({"player_key": pk, "draft_year": y,
                       "pick_overall": a["pick_overall"], "bonus_usd": bonus,
                       "slot_usd": drr["slot_usd"] if drr else None,
                       "fv": fv, "side": side, "dsplus": dsplus})

    cw = {}
    for r in cur.execute("SELECT player_key, payload_json FROM career_war"):
        try:
            cw[r["player_key"]] = json.loads(r["payload_json"])
        except ValueError:
            pass
    for c in cohort:
        pay = cw.get(c["player_key"])
        war = 0.0
        for yr, w in ((pay or {}).get("seasons") or {}).items():
            try:
                yi, wf = int(yr), float(w)
            except (TypeError, ValueError):
                continue
            if c["draft_year"] + 1 <= yi <= c["draft_year"] + 7:
                war += wf
        c["war_out"] = round(war, 3)
    con.close()
    assert len({c["player_key"] for c in cohort}) == len(cohort), \
        "substrate must be one row per player (player-clustered bootstrap)"
    return cohort


def _v2_reference_prior(cons_war, pick, bonus, cons_fv, is_pit):
    """FROZEN replica of the committed V2 draft-branch math (2026-07-23), used
    only for the A3/B4 flag-OFF bit-identity read. Draft rows only."""
    import math
    import storage
    cfg = (vf._config().get("efv_provisional_prior") or {})
    if not cfg.get("enabled"):
        return float(cons_war)
    slot_war = storage._pick_slot_expected_war(pick)
    if slot_war is None:
        return float(cons_war)
    try:
        p = int(pick)
    except (TypeError, ValueError):
        return float(cons_war)
    if p <= 10:
        ped = float(cfg.get("draft_top10_precision", 0.8))
    elif p <= int(cfg.get("round1_last_pick", 30)):
        ped = float(cfg.get("draft_round1_precision", 0.4))
    elif p <= int(cfg.get("round2_last_pick", 70)):
        ped = float(cfg.get("draft_round2_precision", 0.15))
    else:
        ped = float(cfg.get("draft_later_precision", 0.05))
    try:
        b = float(bonus) if bonus is not None else None
    except (TypeError, ValueError):
        b = None
    if b is not None and b > 0:
        floor = float(cfg.get("bonus_floor_usd", 10000))
        ped += max(0.0, math.log10(max(b, floor) / floor)) * float(cfg.get("bonus_log_scale", 0.5))
    ped = min(ped, float(cfg.get("max_pedigree_precision", 3.0)))
    base = float(cfg.get("base_precision", 1.0))
    w = ped / (ped + base) if (ped + base) > 0 else 0.0
    ref = float(cons_war)
    if cons_fv is not None and is_pit is not None:
        try:
            m6 = vf.expected_six_year_avg_war(float(cons_fv), bool(is_pit))
        except (TypeError, ValueError):
            m6 = None
        if m6 is not None:
            from efv_dataset import TARGET_SEASONS as _TS
            ref = max(ref, float(m6) * _TS)
    pull = min(max(float(slot_war) - ref, 0.0), float(cfg.get("pull_cap_war", 1.9)))
    prior = float(cons_war) + w * pull
    return max(float(cfg.get("war_floor", -2.0)),
               min(float(cfg.get("war_ceiling", 20.0)), prior))


def _v3_cohort_priors(cohort, fits):
    """Per-row priors on the resolved substrate for OFF/A/B/C, all through the
    PRODUCTION _provisional_prior_war with per-row injected lookup values (the
    row's own slot dollars, its own-class DSplus). Registration note: the
    current-class/unsigned guard is a live-targeting restriction; on resolved
    rows the imputation is applied wherever the bonus is missing AND the slot
    is known, because every resolved draftee WAS a current-class unsigned pick
    when this branch would have scored them. Also returns the flag-OFF
    bit-identity read vs the frozen V2 reference."""
    out = {arm: [] for arm in V3_ARM_FLAGS}
    identity_bad = []
    for c in cohort:
        ols, lam = fits[c["side"]][0], fits[c["side"]][1]
        cons_war = max(0.0, _pred_ols(ols, c["fv"])) if ols else 0.0
        is_pit = c["side"] == "pit"
        slot_map = ({int(c["pick_overall"]): float(c["slot_usd"])}
                    if (c["bonus_usd"] is None and c["slot_usd"]) else {})
        b_key = float(c["bonus_usd"]) if c["bonus_usd"] is not None else None
        ds_map = ({(int(c["pick_overall"]), b_key): int(c["dsplus"])}
                  if c["dsplus"] is not None else {})
        for arm, flags in V3_ARM_FLAGS.items():
            _v3_inject(slot_by_pick=slot_map, dsplus_by_key=ds_map)
            with _v3_env(flags):
                war, _f = es._provisional_prior_war(
                    cons_war, c["pick_overall"], c["bonus_usd"],
                    cons_fv=c["fv"], is_pitcher=is_pit)
            out[arm].append(war)
        ref = _v2_reference_prior(cons_war, c["pick_overall"], c["bonus_usd"],
                                  c["fv"], is_pit)
        if out["OFF"][-1] != ref:
            identity_bad.append({"player_key": c["player_key"],
                                 "off": out["OFF"][-1], "v2_ref": ref})
    _v3_reset_cache()
    return out, identity_bad


def _v3_live_rows():
    """The live provisional cohort: served rows flagged xfv_provisional with
    kind == active in data/xfv.json, rebuilt for in-process scoring from the
    timeseries latest snapshot + the acquisitions sidecar (read-only DB).
    No served artifact is regenerated."""
    import sqlite3
    served = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))
    act = {k: v for k, v in (served.get("by_player") or {}).items()
           if isinstance(v, dict) and v.get("xfv_provisional")
           and v.get("kind") == "active"}
    ts = json.loads((ROOT / "data" / "timeseries.json").read_text(encoding="utf-8"))
    latest = {}
    for p in (ts.get("players") or []):
        pk = p.get("player_key")
        if pk not in act:
            continue
        pts = [pt for pt in (p.get("points") or [])
               if _f(pt.get("consensus_fv_raw")) is not None
               and pt.get("snapshot_date")]
        if pts:
            latest[pk] = max(pts, key=lambda pt: pt["snapshot_date"])
    acq = {}
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    keys = tuple(latest)
    for i in range(0, len(keys), 500):
        chunk = keys[i:i + 500]
        qm = ",".join("?" * len(chunk))
        for r in con.execute(
                f"SELECT player_key, method, year, pick_overall, bonus_usd "
                f"FROM acquisitions WHERE player_key IN ({qm})", chunk):
            acq[r["player_key"]] = dict(r)
    con.close()
    rows = []
    for pk, pt in latest.items():
        a = acq.get(pk) or {}
        rows.append({
            "player_key": pk,
            "side": "pit" if (act[pk].get("side") == "P") else "hit",
            "consensus_fv_raw": _f(pt.get("consensus_fv_raw")),
            "pick_overall": a.get("pick_overall"), "bonus_usd": a.get("bonus_usd"),
            "acq_year": a.get("year"), "method": a.get("method"),
            "served_quantile": act[pk].get("xfv_grade_quantile"),
        })
    return rows, len(act)


def _v3_battery(arm, rows, fits, gmap):
    """A2/B3 live move battery for one arm: implied served-quantile move =
    grade through the CURRENT pool's monotone rank_war -> display map
    (_build_grade_map on data/xfv_scored_live*.json), flag OFF vs ON, no
    artifact regenerated. APPROXIMATION (documented): the true post-flip
    quantile re-ranks the whole pool jointly; the frozen-map read is the same
    display-step approximation the V2 clause-3 cap derivation used, and it
    upper-bounds the row's own step because upward moves cannot widen under a
    joint re-rank of upward-only movers. Uses the REAL DB-built lookups end to
    end (no injection)."""
    _v3_reset_cache()
    flags = V3_ARM_FLAGS[arm]
    moves, bad_dir, ifa_moved = [], [], []
    dsplus_map = None
    for row in rows:
        side = row["side"]
        ols, lam = fits[side][0], fits[side][1]
        with _v3_env(V3_ARM_FLAGS["OFF"]):
            g_off = _grade_for(row, side, ols, lam, gmap, p1_on=True)
        with _v3_env(flags):
            g_on = _grade_for(row, side, ols, lam, gmap, p1_on=True)
        if g_off is None or g_on is None:
            continue
        d = g_on - g_off
        if row["pick_overall"] is None and abs(d) > 1e-9:
            ifa_moved.append({"player_key": row["player_key"], "delta": round(d, 3)})
        if d < -1e-9:
            bad_dir.append({"player_key": row["player_key"], "delta": round(d, 3)})
        if abs(d) > 1e-9:
            moves.append({"player_key": row["player_key"], "acq_year": row["acq_year"],
                          "pick": row["pick_overall"], "bonus_usd": row["bonus_usd"],
                          "consensus_fv": row["consensus_fv_raw"],
                          "grade_off": round(g_off, 2), "grade_on": round(g_on, 2),
                          "delta": round(d, 2)})
    cache = getattr(es._provisional_prior_war, "_p1v3_cache", None) or {}
    dsplus_map = cache.get("dsplus_by_key") or {}
    for m in moves:
        b_key = float(m["bonus_usd"]) if m["bonus_usd"] is not None else None
        m["missing_bonus"] = m["bonus_usd"] is None
        m["dsplus"] = dsplus_map.get((m["pick"], b_key)) if m["pick"] is not None else None
    _v3_reset_cache()
    max_d = max((m["delta"] for m in moves), default=0.0)
    if arm == "A":
        restricted_ok = all(m["missing_bonus"] and m["pick"] is not None for m in moves)
    elif arm == "B":
        restricted_ok = all(m["pick"] is not None and m["dsplus"] is not None for m in moves)
    else:
        restricted_ok = all(m["pick"] is not None and
                            (m["missing_bonus"] or m["dsplus"] is not None) for m in moves)
    return {
        "n_scored": len(rows), "n_movers": len(moves),
        "max_delta_fv": round(max_d, 2),
        "ceiling_fv": V3_CEILING_FV,
        "all_upward": not bad_dir,
        "movers_restricted_ok": bool(restricted_ok),
        "no_pick_rows_moved": ifa_moved[:10],
        "pass": (not bad_dir) and (not ifa_moved) and restricted_ok
                and max_d <= V3_CEILING_FV + 1e-9,
        "movers": sorted(moves, key=lambda m: -m["delta"])[:15],
        "mover_acq_years": sorted({m["acq_year"] for m in moves if m["acq_year"]}),
    }


def _v3_grid_check(fits):
    """B2: prior non-decreasing in DSplus within pick tier, checked on a fixed
    synthetic grid through the PRODUCTION function (injected DSplus values).
    Grid frozen at registration intent: picks one per tier, DSplus 85..140,
    FV 40/45/55, bonus missing and $2M, both sides."""
    violations = []
    for side in ("hit", "pit"):
        ols = fits[side][0]
        for fv in (40.0, 45.0, 55.0):
            cons_war = max(0.0, _pred_ols(ols, fv)) if ols else 0.0
            for pick in (2, 20, 50, 120):
                for bonus in (None, 2_000_000):
                    b_key = float(bonus) if bonus is not None else None
                    prev = None
                    for ds in (85, 95, 100, 105, 115, 125, 135, 140):
                        _v3_inject(dsplus_by_key={(pick, b_key): ds})
                        with _v3_env(V3_ARM_FLAGS["B"]):
                            war, _fac = es._provisional_prior_war(
                                cons_war, pick, bonus, cons_fv=fv,
                                is_pitcher=(side == "pit"))
                        if prev is not None and war < prev - 1e-9:
                            violations.append({"side": side, "fv": fv, "pick": pick,
                                               "bonus": bonus, "dsplus": ds,
                                               "prior": war, "prev": prev})
                        prev = war
    _v3_reset_cache()
    return {"pass": not violations, "violations": violations[:10],
            "grid": "picks (2,20,50,120) x DSplus (85..140) x FV (40,45,55) "
                    "x bonus (None, $2M) x both sides"}


def run_v3() -> dict:
    """The V3 gated run: one attempt per arm, all bars frozen in GATES.md V3
    (2026-07-23). Appends a 'v3' block to the committed eval artifact."""
    import numpy as np
    fits = {}
    degenerate = False
    for side in ("hit", "pit"):
        pool, ols, lam = _fit_side(side)
        tgt = [r.get("target_censored") for r in pool
               if r.get("target_censored") is not None]
        if tgt and max(tgt) <= 1e-9:
            degenerate = True
        fits[side] = (ols, lam)
    gmap = {s: _build_grade_map(s) for s in ("hit", "pit")}

    v3 = {"generated_at": date.today().isoformat(),
          "registration": "docs/efv-provisional-prior/GATES.md, V3 registration "
                          "(2026-07-23, owner directive: the Grady Emerson case; "
                          "frozen before this run; one attempt per arm)",
          "seed": V3_SEED, "n_boot": V3_NBOOT,
          "bootstrap": "player-clustered (one substrate row per player; row "
                       "resample), numpy default_rng(20260723), 2000 reps",
          "flags": {"ARM-A": "EEPHUS_P1_SLOT_TRUST", "ARM-B": "EEPHUS_P1_DSPLUS",
                    "ARM-C": "both"},
          "approximations": [
              "identity: _provisional_prior_war only sees (pick_overall, "
              "bonus_usd); live lookups key on that pair; a missing-bonus key "
              "resolves to the CURRENT class's unsigned pick; cross-class keys "
              "with disagreeing values are dropped (rows unchanged).",
              "served-quantile step: implied move read through the frozen "
              "current-pool rank_war -> display map (_build_grade_map), the "
              "same approximation the V2 cap derivation used; no artifact "
              "regenerated.",
              "backtest slot-trust: the current-class/unsigned guard is a "
              "live-targeting restriction; resolved rows are imputed wherever "
              "bonus is missing AND slot_usd is known (every resolved draftee "
              "was a current-class unsigned pick when this branch would have "
              "scored them).",
              "DSplus basis: rank-consensus DS+ (draft_stock_plus_pre_college "
              "for the live class via the export payload; per-class recompute "
              "from backfilled pre-draft draft_snapshots for 2018+), i.e. "
              "BEFORE the college +-6 boost, one basis for live + historical.",
          ]}
    if degenerate:
        v3["verdict"] = ("ABSTAIN - degraded matrix (target_censored all-zero); "
                         "attempt NOT consumed, re-run at a scored vintage")
        return v3

    cohort = _v3_build_cohort()
    covered_idx = [i for i, c in enumerate(cohort) if c["dsplus"] is not None]
    n_missing_bonus = sum(1 for c in cohort if c["bonus_usd"] is None)
    n_imputable = sum(1 for c in cohort
                      if c["bonus_usd"] is None and c["slot_usd"])
    v3["substrate"] = {
        "n": len(cohort),
        "n_by_side": {s: sum(1 for c in cohort if c["side"] == s)
                      for s in ("hit", "pit")},
        "outcome_window": "draft_year+1 .. draft_year+7 bWAR sum (career_war; "
                          "no row = 0), the recorded V2-era backtest protocol",
        "n_missing_bonus": n_missing_bonus,
        "n_slot_imputable": n_imputable,
        "dsplus_covered_n": len(covered_idx),
        "dsplus_covered_by_class": {
            str(y): sum(1 for c in cohort
                        if c["dsplus"] is not None and c["draft_year"] == y)
            for y in (2018, 2019)},
    }

    priors, identity_bad = _v3_cohort_priors(cohort, fits)
    war_out = [c["war_out"] for c in cohort]
    rho_v2 = _v3_spearman(np.asarray(priors["OFF"]), np.asarray(war_out))
    v3["substrate"]["rho_v2_baseline"] = round(rho_v2, 4)

    live_rows, n_served_prov = _v3_live_rows()
    v3["live_cohort"] = {"n_served_active_provisional": n_served_prov,
                         "n_scoreable": len(live_rows)}

    # live-row OFF identity (part of A3/B4): new code, flags unset, must equal
    # the frozen V2 reference on every scoreable live row.
    live_identity_bad = []
    for row in live_rows:
        side = row["side"]
        ols = fits[side][0]
        cons_fv = row["consensus_fv_raw"]
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else 0.0
        with _v3_env(V3_ARM_FLAGS["OFF"]):
            war_new, _fx = es._provisional_prior_war(
                cons_war, row["pick_overall"], row["bonus_usd"],
                cons_fv=cons_fv, is_pitcher=(side == "pit"))
        ref = (_v2_reference_prior(cons_war, row["pick_overall"], row["bonus_usd"],
                                   cons_fv, side == "pit")
               if row["pick_overall"] is not None else None)
        if ref is not None and war_new != ref:
            live_identity_bad.append({"player_key": row["player_key"],
                                      "off": war_new, "v2_ref": ref})
    identity = {
        "pass": not identity_bad and not live_identity_bad,
        "backtest_rows_checked": len(cohort),
        "live_rows_checked": sum(1 for r in live_rows
                                 if r["pick_overall"] is not None),
        "mismatches": (identity_bad + live_identity_bad)[:10],
        "note": "flags unset: new code vs frozen committed-V2 replica, exact "
                "float equality",
    }

    arms_out = {}
    named_example = {}
    for arm in ("A", "B", "C"):
        entry = {"flag": {"A": "EEPHUS_P1_SLOT_TRUST", "B": "EEPHUS_P1_DSPLUS",
                          "C": "EEPHUS_P1_SLOT_TRUST + EEPHUS_P1_DSPLUS"}[arm]}
        pooled = _v3_boot_delta(priors[arm], priors["OFF"], war_out)
        entry["pooled_delta_vs_v2"] = pooled
        entry["pooled_bar"] = f"lo95 >= {V3_NOHARM_LO95} (no-harm)"
        pooled_ok = pooled["ci95"][0] >= V3_NOHARM_LO95
        if arm == "A":
            entry["n_rows_changed_backtest"] = n_imputable
            entry["a1"] = {"pass": bool(pooled_ok), **pooled,
                           "note": f"only {n_imputable} resolved rows are "
                                   "slot-imputable (draft_results carries no "
                                   "slot dollars before 2017); the bar is "
                                   "no-harm and the read is near-null by "
                                   "construction, honest per registration"}
            battery = _v3_battery("A", live_rows, fits, gmap)
            entry["a2_battery"] = battery
            entry["a3_off_identity"] = identity
            entry["verdict"] = ("PASS" if (entry["a1"]["pass"] and battery["pass"]
                                           and identity["pass"]) else "FAIL")
        else:
            if len(covered_idx) < V3_STOPB_MIN_N:
                entry["verdict"] = "COVERAGE-STARVED"
                entry["stop_b"] = {"covered_n": len(covered_idx),
                                   "bar": V3_STOPB_MIN_N}
                arms_out[f"ARM-{arm}"] = entry
                continue
            covered = _v3_boot_delta(priors[arm], priors["OFF"], war_out,
                                     idx=np.asarray(covered_idx))
            n_changed = sum(1 for i in covered_idx
                            if priors[arm][i] != priors["OFF"][i])
            entry["b1"] = {
                "covered_delta_vs_v2": covered,
                "covered_bar": "lo95 > 0 (gain, strict)",
                "covered_n": len(covered_idx),
                "n_covered_rows_changed": n_changed,
                "pooled_delta_vs_v2": pooled,
                "pooled_bar": f"lo95 >= {V3_NOHARM_LO95}",
                "pass": bool(covered["ci95"][0] > 0 and pooled_ok),
            }
            entry["b2_grid"] = _v3_grid_check(fits)
            battery = _v3_battery(arm, live_rows, fits, gmap)
            entry["b3_battery"] = battery
            entry["b4_off_identity"] = identity
            clauses = [entry["b1"]["pass"], entry["b2_grid"]["pass"],
                       battery["pass"], identity["pass"]]
            entry["verdict"] = "PASS" if all(clauses) else "FAIL"
        arms_out[f"ARM-{arm}"] = entry

        # named example: Grady Emerson under this arm (live-path scoring)
        ge = next((r for r in live_rows if r["player_key"] == _V3_NAMED), None)
        if ge:
            side = ge["side"]
            ols, lam = fits[side][0], fits[side][1]
            with _v3_env(V3_ARM_FLAGS["OFF"]):
                g_off = _grade_for(ge, side, ols, lam, gmap, p1_on=True)
            _v3_reset_cache()
            with _v3_env(V3_ARM_FLAGS[arm]):
                g_on = _grade_for(ge, side, ols, lam, gmap, p1_on=True)
            _v3_reset_cache()
            named_example[f"ARM-{arm}"] = {
                "served_quantile": ge["served_quantile"],
                "grade_off": None if g_off is None else round(g_off, 2),
                "grade_on": None if g_on is None else round(g_on, 2),
                "delta": (None if (g_off is None or g_on is None)
                          else round(g_on - g_off, 2))}
    v3["arms"] = arms_out
    v3["named_example_grady_emerson"] = {
        "context": "2026 pick 2 TBR, slot_usd 10507000, bonus NULL, signed 0, "
                   "consensus 48.3, served quantile 48.6, V2 credit 0.844",
        **named_example}
    v3["verdict"] = {k: v.get("verdict") for k, v in arms_out.items()}
    return v3


if __name__ == "__main__":
    if "--clause1" in sys.argv:
        rep = run_clause1()
        print("clause 1 flagship bit-identity:",
              "IDENTICAL" if rep["identical"] else "DIFFERS (FAIL)")
        for side, s in rep["sides"].items():
            print(f"  {side}: identical={s['identical']} ({s['bytes']} bytes compared)")
        sys.exit(0)
    if "--v3" in sys.argv:
        rep = run_v3()
        doc = (json.loads(OUT_PATH.read_text(encoding="utf-8"))
               if OUT_PATH.exists() else {})
        doc["v3"] = rep
        OUT_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print("P1 V3 gated run:", rep.get("verdict"))
        for name, e in (rep.get("arms") or {}).items():
            print(f"\n{name} [{e.get('flag')}]: {e.get('verdict')}")
            for k in ("a1", "b1"):
                if k in e:
                    blk = e[k]
                    print(f"  {k}: pass={blk.get('pass')} "
                          f"pooled={e['pooled_delta_vs_v2']['ci95']}")
                    if k == "b1":
                        print(f"      covered={blk['covered_delta_vs_v2']['ci95']} "
                              f"n={blk['covered_n']} changed={blk['n_covered_rows_changed']}")
            for k in ("a2_battery", "b3_battery"):
                if k in e:
                    b = e[k]
                    print(f"  {k}: pass={b['pass']} movers={b['n_movers']}/"
                          f"{b['n_scored']} max_delta={b['max_delta_fv']} "
                          f"upward={b['all_upward']} restricted={b['movers_restricted_ok']}")
            if "b2_grid" in e:
                print(f"  b2_grid: pass={e['b2_grid']['pass']}")
            for k in ("a3_off_identity", "b4_off_identity"):
                if k in e:
                    print(f"  {k}: pass={e[k]['pass']}")
        print("\nnamed example:", json.dumps(
            rep.get("named_example_grady_emerson"), indent=1))
        print("artifact ->", OUT_PATH)
        sys.exit(0)
    if "--ifa-step" in sys.argv:
        rep = run_ifa_step()
        print("IFA step gate:", rep["wiring_decision"])
        print("  window:", rep["step_boundary_window"])
        print("  first6:", rep["step_boundary_first6"])
        print("  direction stable:", rep["direction_stable_all_folds"])
        print("  heldout step predictor:", rep["heldout_step_predictor"])
        print("artifact ->", IFA_OUT_PATH)
        sys.exit(0)
    rep = run()
    # carry a previously MEASURED clause-1 block forward across re-runs (the
    # --clause1 pass is expensive; a movers-refresh re-run must not silently
    # demote a measured invariant back to "verify separately")
    if OUT_PATH.exists():
        try:
            _old = (json.loads(OUT_PATH.read_text(encoding="utf-8"))
                    .get("clauses") or {}).get("1_flagship_untouched") or {}
            if "measured" in _old:
                rep["clauses"]["1_flagship_untouched"] = _old
        except (OSError, ValueError):
            pass
    OUT_PATH.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print("P1 provisional-prior gate:", rep["verdict"])
    for side, s in rep["sides"].items():
        print(f"  {side}: {s['n_provisional']} provisional, {s['n_moved_up']} moved up, "
              f"max abs delta {s['max_abs_delta']} FV")
    for k, v in rep["clauses"].items():
        if "pass" in v:
            print(f"  clause {k}: {'PASS' if v['pass'] else 'FAIL'}")
    for m in rep["live_movers"]:
        print("  mover:", m)
    print("artifact ->", OUT_PATH)
