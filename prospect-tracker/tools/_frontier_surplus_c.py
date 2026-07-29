# SCRATCH (not shipped): STAGE C -- surplus error DECOMPOSITION on the real
# resolved backtest pool. Answers: is surplus error dominated by the WAR estimate,
# the $/WAR series, or the control-year assumptions?
#
# Ladder (all vs the SAME ground truth realized_sv_pv):
#   L2  production: predicted FV -> engine -> calibration            (WAR err + pricing err)
#   L1  ORACLE WAR through the FV bottleneck: realized 6yr WAR -> realized_implied_fv
#       -> engine -> calibration                                     (pricing err + FV-bottleneck err)
#   L0  ORACLE WAR direct: the realized per-season WAR path priced by the engine's
#       own service path (_service_path_surplus_usd)                 (pure pricing-assumption err)
# then component ablations off L0: flat vs convex $/WAR, control years, discount rate.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only     # noqa: E402
from backtest import realized_sv_pv                                 # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)
SEED = 20260724
B = 2000


def main():
    t0 = time.time()
    records, acct = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    disc = float(cfg["discount_rate"])
    flat_mm = vf.dollars_per_war_flat()
    dpw_flat = {y: {"overall": flat_mm} for y in range(2014, 2035)}
    print("resolved n=%d  flat $/WAR=%.3fM  disc=%.3f  (%.1fs)" % (
        len(resolved), flat_mm, disc, time.time() - t0))

    rows = []
    for rec in resolved:
        lv, rz = rec.listing, rec.realized
        truth = realized_sv_pv(rz, lv.listing_year, discount_rate=disc, dpw_by_year=dpw_flat)
        raw2 = vf.expected_surplus_usd(lv.fv, lv.is_pitcher, lv.position,
                                       age=lv.age_at_listing, eta_years=lv.eta_years)
        L2 = vf.apply_calibration((raw2 or 0.0) / 1e6, lv.fv, lv.is_pitcher)

        wars = [float(s.fwar) for s in sorted(rz.seasons, key=lambda s: s.year)]
        realized_6 = float(sum(wars))
        eta_actual = (float(rz.debut_year - lv.listing_year) if rz.debut_year is not None
                      else float(lv.eta_years or 3.5))
        # L1: perfect 6yr-WAR foresight, but forced through the FV bottleneck
        fv_or = vf.realized_implied_fv(realized_6, lv.is_pitcher, position=lv.position,
                                       exposure_seasons=6)
        if fv_or is None:
            L1 = 0.0
        else:
            r1 = vf.expected_surplus_usd(fv_or, lv.is_pitcher, lv.position,
                                         age=lv.age_at_listing, eta_years=max(0.0, eta_actual))
            L1 = vf.apply_calibration((r1 or 0.0) / 1e6, fv_or, lv.is_pitcher)
        # L0: perfect per-season WAR path priced by the engine's own service path
        L0 = (vf._service_path_surplus_usd(wars, False, max(0.0, eta_actual)) / 1e6) if wars else 0.0
        rows.append({"pid": lv.player_id, "year": int(lv.listing_year), "fv": float(lv.fv),
                     "is_pit": bool(lv.is_pitcher), "truth": float(truth),
                     "L2": float(L2), "L1": float(L1), "L0": float(L0),
                     "wars": wars, "eta": max(0.0, eta_actual),
                     "debuted": rz.debut_year is not None, "realized6": realized_6})

    T = np.array([r["truth"] for r in rows])
    res = {"n": len(rows), "acct": acct, "flat_dpw_mm": flat_mm, "discount_rate": disc,
           "truth_mean": float(T.mean()), "truth_sd": float(T.std()),
           "truth_mean_abs": float(np.abs(T).mean())}

    def stat(name, P):
        P = np.asarray(P, float)
        e = P - T
        return {"level": name, "n": len(P), "mae": float(np.abs(e).mean()),
                "rmse": float(np.sqrt((e ** 2).mean())), "bias": float(e.mean()),
                "pred_mean": float(P.mean())}

    ladder = {k: stat(k, [r[k] for r in rows]) for k in ("L2", "L1", "L0")}
    res["ladder"] = ladder

    # ---- component ablations off L0 (pure pricing) -------------------------
    def path(wars, eta, tiered=True, flat=None, nyears=None, disc_r=None):
        w = list(wars) if nyears is None else list(wars)[:nyears]
        if not w:
            return 0.0
        if tiered:
            markets = [vf.tiered_war_value_usd(x) for x in w]
        else:
            markets = [x * flat * 1e6 for x in w]
        sal = vf._service_path_salaries(w, markets, False)
        r = disc if disc_r is None else disc_r
        infl = float(cfg.get("dollars_per_war_inflation", 0.0))
        net = (1.0 + infl) / (1.0 + r)
        return sum((markets[t] - sal[t]) * (net ** (eta + t)) for t in range(len(w))) / 1e6

    ab = {}
    ab["L0_reproduce"] = stat("L0_reproduce", [path(r["wars"], r["eta"]) for r in rows])
    ab["flat_dpw"] = stat("flat_dpw", [path(r["wars"], r["eta"], tiered=False, flat=flat_mm)
                                       for r in rows])
    for ny in (5, 6, 7):
        ab[f"control_{ny}y"] = stat(f"control_{ny}y",
                                    [path(r["wars"], r["eta"], nyears=ny) for r in rows])
    for dr in (0.05, 0.07, 0.09, 0.11):
        ab[f"disc_{dr}"] = stat(f"disc_{dr}", [path(r["wars"], r["eta"], disc_r=dr) for r in rows])
    for mult in (0.85, 0.9, 1.1, 1.15):
        ab[f"dpw_x{mult}"] = stat(f"dpw_x{mult}",
                                  [path([w * 1 for w in r["wars"]], r["eta"], tiered=False,
                                        flat=flat_mm * mult) for r in rows])
    res["pricing_ablations"] = ab

    # ---- WAR-estimate error: shrink the predicted-vs-realized WAR gap -------
    # Convert the L2 prediction's implied WAR toward realized and re-price, to price
    # "what would a partially better WAR estimate be worth in $ MAE?"
    imp = []
    for r in rows:
        fvp = r["fv"]
        w_pred = (vf.fv_to_6yr_avg_war(fvp) or 0.0) * 6
        imp.append(w_pred)
    imp = np.array(imp)
    real6 = np.array([r["realized6"] for r in rows])
    res["war_level"] = {
        "consensus_fv_implied_6yr_war_mean": float(imp.mean()),
        "realized_6yr_war_mean": float(real6.mean()),
        "bias_war": float(imp.mean() - real6.mean()),
        "mae_war": float(np.abs(imp - real6).mean()),
    }
    shrink = {}
    for k in (0.0, 0.25, 0.5, 0.75, 1.0):
        w_mix = (1 - k) * imp + k * real6
        preds = []
        for r, wm in zip(rows, w_mix):
            fvh = vf.realized_implied_fv(float(wm), r["is_pit"], position=None, exposure_seasons=6)
            if fvh is None:
                preds.append(0.0); continue
            raw = vf.expected_surplus_usd(fvh, r["is_pit"], None,
                                          age=None, eta_years=r["eta"])
            preds.append(vf.apply_calibration((raw or 0.0) / 1e6, fvh, r["is_pit"]))
        shrink[f"k={k}"] = stat(f"war_toward_truth_{k}", preds)
    res["war_estimate_value_ladder"] = shrink

    # ---- bootstrap CIs on the key MAE gaps ---------------------------------
    rng = np.random.default_rng(SEED)
    pid = np.array([r["pid"] for r in rows])
    upid = np.unique(pid)
    idx_by = {p: np.flatnonzero(pid == p) for p in upid}
    A = {k: np.array([r[k] for r in rows]) for k in ("L2", "L1", "L0")}
    d21, d10, d20 = [], [], []
    for _ in range(B):
        s = rng.integers(0, len(upid), len(upid))
        idx = np.concatenate([idx_by[upid[j]] for j in s])
        t = T[idx]
        m = {k: float(np.abs(A[k][idx] - t).mean()) for k in A}
        d21.append(m["L1"] - m["L2"]); d10.append(m["L0"] - m["L1"]); d20.append(m["L0"] - m["L2"])
    q = lambda a, p: float(np.percentile(a, p))
    res["bootstrap_mae_gaps"] = {
        "reps": B, "seed": SEED, "cluster": "player",
        "L1_minus_L2": {"mean": float(np.mean(d21)), "ci95": [q(d21, 2.5), q(d21, 97.5)],
                        "P(L1 better)": float((np.array(d21) < 0).mean())},
        "L0_minus_L1": {"mean": float(np.mean(d10)), "ci95": [q(d10, 2.5), q(d10, 97.5)],
                        "P(L0 better)": float((np.array(d10) < 0).mean())},
        "L0_minus_L2": {"mean": float(np.mean(d20)), "ci95": [q(d20, 2.5), q(d20, 97.5)],
                        "P(L0 better)": float((np.array(d20) < 0).mean())},
    }

    (OUT / "_surplus_stageC.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "acct"}, indent=1))
    print("done %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
