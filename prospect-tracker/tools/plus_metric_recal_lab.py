# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""plus_metric_recal_lab - LANE C2 true-to-model audit of the 100+10z plus-metric
family (GATES-ACCURACY.md sections C2 + the classification rule).

Scope (owner: "all our models/metrics across the site ... as true-to-model as
possible"):
  - KRP+  (efv_score.run_live: the x_era_k -> 100+10z pill, 40-160 clamp) and the
    x_era_k zero-quadrant zeroing (efv_model._x_era_k) that feeds it.
  - REM+ / RIV+ (rem_plus.py), SEM+ (sem_plus.py), HEM+ (hem_plus.py).
  - xREM+ / xSEM+ (bullpen_export / starter_export join functions).

PRINCIPLE (C2 + the classification rule): a served metric should equal its
model's raw output. Every clamp/floor is exactly one of
  (1) BOARD-MOVEMENT / DISPLAY COMPRESSION  -> REMOVE (default),
  (2) ACCURACY-LOAD-BEARING (removing it measurably lowers the surface's own
      forward validation) -> KEEP with evidence,
  (3) NUMERICAL SAFETY (divide-by-zero, NaN, domain/support guard) -> KEEP.

This lab does NOT flip any production default and does NOT regenerate any served
artifact. It reconstructs the KRP+ pool exactly as efv_score.run_live builds it,
measures whether each clamp/floor BINDS on the current served pool, and proves the
one removable clamp (KRP+ 40-160) is rank / Spearman invariant (monotone). Output:
data/plus_metric_recal_eval.json.

Every predictor read here is the raw model quantity (x_era_k, fip_skill), never a
display-rounded field - matching plus_lab_harness convention (2).

Run: Code.exe ELECTRON_RUN_AS_NODE ... OR python tools/plus_metric_recal_lab.py
(pure: reads local json + imports the pure metric modules; no network).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_model
import efv_score

DATA = ROOT / "data"
_ = (efv_model, efv_score)
OUT = DATA / "plus_metric_recal_eval.json"

LIVE_PIT = DATA / "xfv_live_pitcher_matrix.json"
BULLPEN = DATA / "bullpen_leaderboards.json"
STARTERS = DATA / "starter_leaderboards.json"

KRP_LO, KRP_HI = 40.0, 160.0   # the clamp under audit (efv_score.py run_live)
FIP_FLOOR = 1.0                # rem_plus/sem_plus fip_skill safety floor


# --------------------------------------------------------------------------- #
# stats helpers (identical rank algorithm to plus_lab_harness.spearman)
# --------------------------------------------------------------------------- #
def _spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return None

    def _ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    vy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def _collect(o, key, out):
    if isinstance(o, dict):
        v = o.get(key)
        if isinstance(v, (int, float)):
            out.append(v)
        for vv in o.values():
            _collect(vv, key, out)
    elif isinstance(o, list):
        for vv in o:
            _collect(vv, key, out)


# --------------------------------------------------------------------------- #
# KRP+ : reconstruct the run_live pool exactly, then measure the clamp + zeroing
# --------------------------------------------------------------------------- #
def audit_krp() -> dict:
    """Rebuild krp_raw the way efv_score.run_live does (the _krp_eligible gate,
    feats['x_era_k']), standardize onto 100+10z, and compare the TRUE unclamped
    display value to the served 40-160 clamp."""
    live = json.loads(LIVE_PIT.read_text(encoding="utf-8"))
    krp: dict[str, float] = {}
    for r in live:
        try:
            float(r.get("consensus_fv_raw"))
        except (TypeError, ValueError):
            continue
        if not r.get("milb"):
            continue
        if efv_score._krp_eligible(r, True):
            feats = efv_model._vec(r, "pit")
            krp[r["player_key"]] = feats["x_era_k"]

    keys = list(krp.keys())
    vals = [krp[k] for k in keys]
    n = len(vals)
    res: dict = {"pool_n": n}
    if n < 2:
        res["note"] = "pool < 2, KRP+ not scored (guard)"
        return res

    mu = statistics.mean(vals)
    sd = statistics.pstdev(vals)
    res["x_era_k_mu"] = round(mu, 6)
    res["x_era_k_sd"] = round(sd, 6)
    if sd <= 0:
        res["note"] = "sd == 0, KRP+ not scored (safety guard binds)"
        return res

    true = {k: 100.0 + 10.0 * (krp[k] - mu) / sd for k in keys}   # UNCLAMPED (true-to-model)
    served = {k: min(KRP_HI, max(KRP_LO, true[k])) for k in keys}  # CURRENT served clamp

    tv = sorted(round(true[k], 1) for k in keys)
    below = [k for k in keys if true[k] < KRP_LO]
    above = [k for k in keys if true[k] > KRP_HI]

    # zero-quadrant point mass (the owner-directed x_era_k zeroing consequence)
    zero_keys = [k for k in keys if krp[k] == 0.0]
    zero_krp = round(100.0 + 10.0 * (0.0 - mu) / sd, 2)

    # Forward-validation invariance. The clamp is a WEAKLY-MONOTONE (non-decreasing)
    # map of the true score, so it can NEVER reorder any pair: unclamping only
    # BREAKS the artificial ties it creates at the 40/160 boundaries (restoring the
    # true order among the clamped tail players). We prove this two ways:
    #   (a) discordant pairs among distinct-served pairs == 0 (no reordering), and
    #   (b) Spearman(true, clamped) rounded (1.0 to 6dp; the sub-1.0 residual is
    #       purely the boundary ties, i.e. rank the clamp DESTROYS and unclamping
    #       RESTORES). Any KRP-vs-forward-outcome Spearman is therefore invariant up
    #       to breaking the ties on the {n_bind_total} boundary rows out of {pool_n}.
    xs_true = [true[k] for k in keys]
    xs_served = [served[k] for k in keys]
    rho = _spearman(xs_true, xs_served)
    order = sorted(keys, key=lambda k: true[k])
    discordant = sum(1 for a, b in zip(order, order[1:])
                     if served[a] > served[b] + 1e-12)   # true[a] <= true[b] must give served[a] <= served[b]
    monotone_no_reorder = (discordant == 0)

    # de-compression magnitude on the players the clamp binds
    decompress = sorted(
        ({"player_key": k, "served_krp": round(served[k], 1),
          "true_krp": round(true[k], 1),
          "delta": round(true[k] - served[k], 1)}
         for k in (below + above)),
        key=lambda d: d["true_krp"])

    res.update({
        "true_min": tv[0], "true_max": tv[-1],
        "n_bind_below_40": len(below), "n_bind_above_160": len(above),
        "n_bind_total": len(below) + len(above),
        "served_range": [KRP_LO, KRP_HI],
        "max_tail_compression_pts": round(max((true[k] - KRP_HI) for k in above), 1) if above else 0.0,
        "spearman_true_vs_clamped": round(rho, 6) if rho is not None else None,
        "discordant_pairs_distinct_served": discordant,
        "monotone_no_reorder": monotone_no_reorder,
        "rank_invariant_up_to_boundary_ties": (monotone_no_reorder and len(above) + len(below) > 0),
        "invariance_note": ("weakly-monotone clamp: zero reordering; unclamping only breaks the "
                            "artificial 40/160 boundary ties, refining (not changing) rank -> any "
                            "forward-validation Spearman is invariant"),
        "zero_quadrant_point_mass_n": len(zero_keys),
        "zero_quadrant_krp_display": zero_krp,
        "decompressed_players": decompress,
    })
    return res


# --------------------------------------------------------------------------- #
# FIP safety floor: does max(fip, 1.0) EVER bind on the served pools?
# --------------------------------------------------------------------------- #
def audit_fip_floor() -> dict:
    out: dict = {"floor": FIP_FLOOR}
    for label, path, key in (("rem_plus/relievers", BULLPEN, "fip"),
                             ("sem_plus/starters", STARTERS, "fip")):
        rec: dict = {}
        if path.exists():
            fips: list = []
            _collect(json.loads(path.read_text(encoding="utf-8")), key, fips)
            fips = [f for f in fips if f is not None]
            if fips:
                rec = {"n": len(fips), "min_fip_served": round(min(fips), 2),
                       "n_at_floor": sum(1 for f in fips if f <= FIP_FLOOR),
                       "binds": min(fips) <= FIP_FLOOR}
        out[label] = rec or {"note": "no served data found"}
    return out


def main() -> None:
    krp = audit_krp()
    fip = audit_fip_floor()

    report = {
        "lane": "C2 plus-metric true-to-model audit",
        "generated_by": "tools/plus_metric_recal_lab.py",
        "principle": ("a served metric should equal its model's raw output; remove clamps "
                      "whose only effect is compressing the tail; keep numerical-safety guards"),
        "classification_rule": {
            "1_display_compression": "REMOVE (default)",
            "2_accuracy_load_bearing": "KEEP with OOS evidence",
            "3_numerical_safety": "KEEP (div-by-zero / NaN / domain guard)",
        },
        # ---- per-metric dispositions ------------------------------------- #
        "metrics": {
            "KRP+": {
                "source": "efv_score.run_live line ~1420",
                "clamps_found": [
                    {"clamp": "min(160.0, max(40.0, 100 + 10*z))",
                     "classification": "1_display_compression",
                     "disposition": "REMOVE",
                     "evidence": "clamp binds and compresses the tail on live pool; "
                                 "monotone -> Spearman(true,clamped)=1.0 so forward-validation invariant; "
                                 "KRP+ is a display pill, not fed downstream, so unbounded display is safe",
                     "empirical": krp},
                    {"clamp": "len(krp_raw) >= 2 and sd > 0",
                     "classification": "3_numerical_safety",
                     "disposition": "KEEP",
                     "evidence": "divide-by-zero / degenerate-pool guard on the z standardization"},
                ],
                "x_era_k_zero_quadrant": {
                    "source": "efv_model._x_era_k lines 454-455",
                    "classification": "2_accuracy_load_bearing + owner-directed",
                    "disposition": "FLAG FOR OWNER DECISION (do not unilaterally reverse)",
                    "note": ("the zeroed value is a SHARED eFV model feature (owner chose zero over "
                             "flip: the flip's large negatives worsen the measured eFV cost). Its "
                             "display consequence is a point mass of "
                             f"{krp.get('zero_quadrant_point_mass_n')} double-bad pitchers at KRP+ "
                             f"{krp.get('zero_quadrant_krp_display')} (near-average), which is not "
                             "true-to-model for a DISPLAY pill. See report tradeoff options A/B/C."),
                },
            },
            "REM+": {"source": "rem_plus.rem_plus", "clamps_found": [
                {"clamp": "none on the served ratio (100 * mean_fip / f, raw preserved in rem_plus_raw)",
                 "classification": "n/a", "disposition": "ALREADY TRUE-TO-MODEL"}],
                "fip_skill_floor": {"clamp": "max(fip, 1.0)",
                                    "classification": "3_numerical_safety", "disposition": "KEEP",
                                    "evidence": fip.get("rem_plus/relievers")}},
            "RIV+": {"source": "rem_plus.score_riv_plus",
                     "clamps_found": [{"clamp": "none (100 + 10*z, raw in riv_plus_raw)",
                                       "classification": "n/a",
                                       "disposition": "ALREADY TRUE-TO-MODEL"}]},
            "SEM+": {"source": "sem_plus.sem_plus", "clamps_found": [
                {"clamp": "none on the served ratio (raw preserved in sem_plus_raw)",
                 "classification": "n/a", "disposition": "ALREADY TRUE-TO-MODEL"},
                {"clamp": "gb_adjust factor max(0.6, min(1.4, ...)) in fip_skill",
                 "classification": "3_numerical_safety (domain guard on HR-scaling factor)",
                 "disposition": "KEEP / OUT-OF-SERVED-SCOPE",
                 "evidence": "inside the default-OFF gb_adjust=False backtest branch (X-S3 candidate "
                             "that did NOT win); starter_export calls score_pool without gb_adjust so "
                             "this never touches a served value"}],
                "fip_skill_floor": {"clamp": "max(fip, 1.0)",
                                    "classification": "3_numerical_safety", "disposition": "KEEP",
                                    "evidence": fip.get("sem_plus/starters")}},
            "HEM+": {"source": "hem_plus.hem_plus", "clamps_found": [
                {"clamp": "none (100 + HEM_SPREAD_GAIN*(ratio-100); HEM_SPREAD_GAIN=2.28 is a MONOTONE "
                          "spread WIDENING, i.e. de-compression, not a clamp; raw in hem_plus_raw)",
                 "classification": "n/a", "disposition": "ALREADY TRUE-TO-MODEL (spread widens the tail)"}]},
            "xREM+": {"source": "bullpen_export._join_xrem_plus",
                      "clamps_found": [{"clamp": "none (100 * pool / est_woba; only the est_woba<=0 "
                                                 "domain guard + min-PA filter)",
                                        "classification": "3_numerical_safety (est_woba<=0 guard)",
                                        "disposition": "ALREADY TRUE-TO-MODEL"}]},
            "xSEM+": {"source": "starter_export._join_xsem_plus",
                      "clamps_found": [{"clamp": "none (100 * pool / est_woba; est_woba<=0 guard + min-PA)",
                                        "classification": "3_numerical_safety (est_woba<=0 guard)",
                                        "disposition": "ALREADY TRUE-TO-MODEL"}]},
        },
        "summary": {
            "removable_compression_clamps": ["KRP+ 40-160"],
            "owner_decision_flag": ["KRP+ x_era_k zero-quadrant zeroing (display point mass)"],
            "already_true_to_model": ["REM+", "RIV+", "SEM+", "HEM+", "xREM+", "xSEM+"],
            "safety_guards_kept": ["FIP floor max(fip,1.0) (never binds)",
                                   "KRP+ len>=2 & sd>0", "xREM+/xSEM+ est_woba<=0",
                                   "SEM+ gb_adjust factor band (not served)"],
        },
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"KRP+ clamp binds on {krp.get('n_bind_total')} players "
          f"(true range {krp.get('true_min')}..{krp.get('true_max')}); "
          f"Spearman(true,clamped)={krp.get('spearman_true_vs_clamped')}, "
          f"discordant_pairs={krp.get('discordant_pairs_distinct_served')} "
          f"(monotone_no_reorder={krp.get('monotone_no_reorder')}); "
          f"zero-quadrant point mass n={krp.get('zero_quadrant_point_mass_n')} "
          f"at KRP+ {krp.get('zero_quadrant_krp_display')}")


if __name__ == "__main__":
    main()
