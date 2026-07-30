# FA Gate-2 feature-experiment lab (pre-registered 2026-07-15, owner program
# "improve the FA module; don't ship any losses").
#
# Each arm toggles ONE fa_market.X_FEATURES flag and re-runs the UNCHANGED
# forward-chained Gate-2 harness (fa_backtest.run_market_gate, persist=False)
# on identical folds. The champion arm (all flags False) is re-scored in the
# same process first so every comparison is same-code same-data.
#
# PRE-REGISTERED SHIP CRITERIA (set before any arm ran; all values $M MAE
# from summary["pooled"], the 2022 fold from summary["per_winter"]):
#   rate_line: guarantee < champ AND aav < champ AND years <= champ
#              AND mega_guarantee <= champ
#   regime:    guarantee < champ AND 2022 fold guarantee_mae_model <
#              guarantee_mae_base AND mega_guarantee <= champ AND years <= champ
#   age_pos:   years < champ AND guarantee <= champ AND aav <= champ
#              AND mega_guarantee <= champ
#   qo_tier:   guarantee < champ AND years <= champ AND mega_guarantee <= champ
# A COMBINED arm of every individually-passing flag runs last and must ALSO
# pass rate_line's full criteria set; only the combined winner ships.
#
# Ledger position: the LightGBM challenger, ML WAR inputs, dpw trend
# forecasts and fitted fit-weights are all prior Gate-2/Gate-3 losses --
# none of these arms re-run those. Deterministic (OLS on fixed folds).
#
# ============================================================================
# WAVE 2 (pre-registered 2026-07-16, BEFORE any run; run with --wave2;
# artifact data/fa_market_feature_lab_wave2_eval.json). Audit items:
# class-supply train/serve population mismatch (deferred-queue item 5) and
# class projection age anchoring (export-layer item 4). Both flags are
# SERVE-SIDE: consumed only by fa_export's serve path -- nothing in
# fa_market's fit/predict or fa_backtest reads them, and the Gate-2 folds
# already run the aligned regime (fold supply = enriched population at
# fa_backtest.py:301; fold ages anchored in fm.enriched_signings since
# ba3917d). EXPECTED: every Gate-2 metric byte-identical to the wave-2
# champion (production defaults, rate_line=True). The gate re-run is a
# NOT-WORSE guard against accidental train-path coupling; the affirmative
# evidence is the serve diagnostic (fa_export.serve_alignment_diagnostics),
# recorded in the artifact.
#
# PRE-REGISTERED WAVE-2 SHIP CRITERIA (set before any arm ran):
#   supply_pop: GATE  guarantee <= champ AND aav <= champ AND years <= champ
#                     AND mega_guarantee <= champ AND gates_all_pass;
#               SERVE per pos group, aligned count <= raw whole-class count,
#                     AND mean |supply z| across the four pos groups (vs the
#                     champion training moments) STRICTLY DECREASES aligned
#                     vs raw.
#   age_anchor: GATE  same four not-worse clauses AND gates_all_pass;
#               SERVE every changed member age delta (anchored - stale) in
#                     [+1, +2] (the 3-season history window bounds it);
#                     n_changed == 0 ALSO ships (dormant convention guard:
#                     the fix then only protects future corpus vintages
#                     whose platform rows lack ages).
# Wave-2 arms ship INDEPENDENTLY on their own criteria (both are serve-side;
# wave-1's combined-winner-only rule would let an unrelated arm veto a
# repair, and age_anchor is structurally invisible to Gate 2). When both
# pass, a combined gate run is recorded and must satisfy the same not-worse
# clauses, but it gates nothing by itself. Any strict Gate-2 movement in
# EITHER direction is a red flag (the flag leaked into a training path) and
# FAILS the arm pending investigation.
#
# ============================================================================
# WAVE 3 - Phase E5 market-stage arms (owner program 2026-07-29). Run with
# --wave3; artifact data/fa_market_feature_lab_wave3_eval.json. Criteria are
# PRE-REGISTERED in docs/efv-2026-07-30/FA_LANE_GATES.md section E5, written
# before any wave-3 arm ran; that file is authoritative and this header only
# restates it:
#   E5a RECAL_MODE shift|fit         calibration ship on BIAS (rule 4): pooled
#                                    guarantee MAE must not worsen by more than
#                                    the 0.16 $M corpus floor, aav/years/mega
#                                    not worse beyond their fold MDE95, hard
#                                    gates stay True, AND mean |bias| over the
#                                    four actual-guarantee tiers must STRICTLY
#                                    DECREASE.
#   E5b AAV_CONSISTENT True|reprice  arithmetic-coherence fix: aav MAE improves,
#                                    or is a null with everything else
#                                    not-worse; the served guarantee and term
#                                    must describe the same deal.
#   E5c rate_line OFF                may only flip if guarantee MAE improves by
#                                    >= 0.16 $M. Expected NULL, re-ledgered.
#   E5d RECAL_MODE fit_group         E5a's criteria AND the hit-vs-pit guarantee
#                                    bias gap must strictly decrease.
#   E5e POS_GROUP_MODE v2            LAB ARM ONLY, not for ship this cycle.
# Every arm is paired on the 9 forward-chained winters; the reported interval is
# the paired t-95% over folds and MDE95 = 1.96*sd(delta)/sqrt(9). The 0.16 $M
# corpus floor (fa_market.py:1008-1021) OVERRIDES a smaller fold interval.
# ============================================================================
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

import fa_market as fm  # noqa: E402
import fa_backtest as fb  # noqa: E402

ARMS = ("rate_line", "regime", "age_pos", "qo_tier")

# Wave 2: serve-side alignment arms vs the PRODUCTION-default champion.
# PROD_FLAGS snapshots fa_market's shipped defaults at import time (before
# any lab mutation) -- rate_line=True is the shipped champion; wave-1's
# all-flags-off champion is a historical protocol, not today's baseline.
ARMS2 = ("supply_pop", "age_anchor")
PROD_FLAGS = dict(fm.X_FEATURES)


def _score(tag: str) -> dict:
    t0 = time.time()
    s = fb.run_market_gate(persist=False, challenger=False)
    pooled = {k: {"model": v["mae_model"], "base": v["mae_base"], "n": v["n"]}
              for k, v in s["pooled"].items()}
    w2022 = next((w for w in s["per_winter"] if w["winter"] == 2022), {})
    print(f"  [{tag}] guar {pooled['guarantee']['model']:.3f} | "
          f"aav {pooled['aav']['model']:.3f} | years {pooled['years']['model']:.4f} | "
          f"mega {pooled['mega_guarantee']['model']:.2f} | "
          f"2022 {w2022.get('guarantee_mae_model')} vs base {w2022.get('guarantee_mae_base')} "
          f"({time.time() - t0:.0f}s)", flush=True)
    return {"pooled": pooled, "winter_2022": w2022, "gates_all_pass": s["pass"]}


def _passes(arm: str, r: dict, champ: dict) -> bool:
    p, c = r["pooled"], champ["pooled"]
    base_ok = (p["mega_guarantee"]["model"] <= c["mega_guarantee"]["model"]
               and p["years"]["model"] <= c["years"]["model"])
    if arm == "rate_line":
        return (p["guarantee"]["model"] < c["guarantee"]["model"]
                and p["aav"]["model"] < c["aav"]["model"] and base_ok)
    if arm == "regime":
        w = r["winter_2022"]
        return (p["guarantee"]["model"] < c["guarantee"]["model"] and base_ok
                and w.get("guarantee_mae_model", 9e9) < w.get("guarantee_mae_base", 0))
    if arm == "age_pos":
        return (p["years"]["model"] < c["years"]["model"]
                and p["guarantee"]["model"] <= c["guarantee"]["model"]
                and p["aav"]["model"] <= c["aav"]["model"]
                and p["mega_guarantee"]["model"] <= c["mega_guarantee"]["model"])
    if arm == "qo_tier":
        return p["guarantee"]["model"] < c["guarantee"]["model"] and base_ok
    return False


def _gate_not_worse(r: dict, champ: dict) -> bool:
    """The wave-2 GATE clause: all four pooled Gate-2 metrics not worse
    than the same-run champion AND the hard gates still pass. Both wave-2
    arms are serve-side, so equality is the EXPECTED outcome; any strict
    movement in either direction indicates train-path coupling."""
    p, c = r["pooled"], champ["pooled"]
    return (all(p[k]["model"] <= c[k]["model"]
                for k in ("guarantee", "aav", "years", "mega_guarantee"))
            and r["gates_all_pass"])


def _passes_wave2(arm: str, r: dict, champ: dict, diag: dict) -> bool:
    """Pre-registered wave-2 criteria (header above, written before any
    run): the gate not-worse clause AND the arm's serve diagnostic."""
    if not _gate_not_worse(r, champ):
        return False
    if arm == "supply_pop":
        sup = diag["supply"]
        per_group_ok = all(sup["aligned"][g] <= sup["raw"][g] for g in sup["raw"])
        return per_group_ok and sup["mean_abs_z_aligned"] < sup["mean_abs_z_raw"]
    if arm == "age_anchor":
        a = diag["age"]
        if a["n_changed"] == 0:
            return True         # dormant convention guard -- ships
        return a["min_delta"] >= 1 and a["max_delta"] <= 2
    return False


# ============================================================================
# WAVE 3 - E5 market-stage arms
# ============================================================================
TIERS = ("tier:lt10", "tier:10to20", "tier:20to50", "tier:ge50")
# PTIERS bin on the PREDICTED guarantee. This is the conditioning
# fa_market._fit_recal is estimated against and its docstring's stated reason:
# conditioning on the ACTUAL is regression to the mean by construction, so
# `mean_abs_tier_bias` alone can be improved by simply de-shrinking the
# predictions. The wave-3 ship decision reads PTIERS; TIERS is descriptive.
PTIERS = ("ptier:lt10", "ptier:10to20", "ptier:20to50", "ptier:ge50")

# (arm label, {knob: value}) - one knob per arm except the combined runs.
WAVE3_ARMS = (
    ("recal_shift", {"RECAL_MODE": "shift"}),
    ("recal_fit", {"RECAL_MODE": "fit"}),
    ("recal_fit_group", {"RECAL_MODE": "fit_group"}),
    ("aav_consistent_true", {"AAV_CONSISTENT": True}),
    ("aav_consistent_reprice", {"AAV_CONSISTENT": "reprice"}),
    ("rate_line_off", {"_XF": {"rate_line": False}}),
    ("pos_group_v2", {"POS_GROUP_MODE": "v2"}),          # lab only, never ships
)
WAVE3_LAB_ONLY = ("pos_group_v2",)


def _apply(knobs: dict) -> None:
    fm.LAB_RESET()
    for k, v in knobs.items():
        if k == "_XF":
            fm.X_FEATURES.update(v)
        else:
            setattr(fm, k, v)


def _score3(tag: str) -> dict:
    t0 = time.time()
    s = fb.run_market_gate(persist=False, challenger=False)
    pooled = {k: {"model": v["mae_model"], "base": v["mae_base"], "n": v["n"]}
              for k, v in s["pooled"].items()}
    grp = s.get("pooled_by_pos_group") or {}
    tier_bias = {t: grp.get(f"guarantee:{t}", {}).get("bias_model") for t in TIERS}
    have = [abs(v) for v in tier_bias.values() if v is not None]
    ptier_bias = {t: grp.get(f"guarantee:{t}", {}).get("bias_model") for t in PTIERS}
    phave = [abs(v) for v in ptier_bias.values() if v is not None]
    out = {
        "pooled": pooled,
        "ptier_bias_guarantee": ptier_bias,
        "mean_abs_ptier_bias": (sum(phave) / len(phave)) if phave else None,
        "gates_all_pass": s["pass"],
        "per_winter": {w["winter"]: {k: w.get(f"{k}_mae_model")
                                     for k in ("guarantee", "aav", "years")}
                       for w in s["per_winter"]},
        "tier_bias_guarantee": tier_bias,
        "mean_abs_tier_bias": (sum(have) / len(have)) if have else None,
        "bias_hit": grp.get("guarantee:hit", {}).get("bias_model"),
        "bias_pit": grp.get("guarantee:pit", {}).get("bias_model"),
        "group_bias": {g: grp.get(f"guarantee:{g}", {}).get("bias_model")
                       for g in ("SP", "RP", "C", "POS", "POSP", "POSC")
                       if f"guarantee:{g}" in grp},
        "runtime_s": round(time.time() - t0, 1),
    }
    out["bias_side_gap"] = (abs(out["bias_hit"] - out["bias_pit"])
                            if out["bias_hit"] is not None and out["bias_pit"] is not None
                            else None)
    print(f"  [{tag}] guar {pooled['guarantee']['model']:.4f} | "
          f"aav {pooled['aav']['model']:.4f} | years {pooled['years']['model']:.4f} | "
          f"mega {pooled['mega_guarantee']['model']:.2f} | "
          f"mean|tierBias(act)| {out['mean_abs_tier_bias']:.3f} | "
          f"mean|tierBias(PRED)| {out['mean_abs_ptier_bias']:.3f} | "
          f"sideGap {out['bias_side_gap']:.3f} | pass {s['pass']} "
          f"({out['runtime_s']:.0f}s)", flush=True)
    print(f"        ptier bias: "
          + "  ".join(f"{k.split(':')[1]} {v:+.2f}" for k, v in ptier_bias.items()
                      if v is not None), flush=True)
    return out


def _fold_delta(arm: dict, champ: dict, metric: str) -> dict:
    """Paired t-95% over the forward-chained winters + this arm's own MDE95."""
    import math
    import statistics
    ws = sorted(set(arm["per_winter"]) & set(champ["per_winter"]))
    d = [arm["per_winter"][w][metric] - champ["per_winter"][w][metric] for w in ws]
    k = len(d)
    if k < 2:
        return {}
    mean = statistics.mean(d)
    sd = statistics.stdev(d)
    se = sd / math.sqrt(k)
    # t(.975, k-1) for k=9 is 2.306; table lookup keeps this dependency-free.
    tcrit = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447,
             8: 2.365, 9: 2.306, 10: 2.262}.get(k - 1, 1.96)
    return {"metric": metric, "k_folds": k, "delta_mean": mean, "sd": sd,
            "ci95": [mean - tcrit * se, mean + tcrit * se],
            "mde95": 1.96 * se, "folds_improved": sum(1 for x in d if x < 0),
            "null": abs(mean) < 1.96 * se, "per_fold": dict(zip(ws, d))}


GUAR_FLOOR_MM = 0.16        # corpus MDE95, fa_market.py:1008-1021


def _wave3_verdict(arm_name: str, r: dict, champ: dict) -> dict:
    """The PRE-REGISTERED criteria from FA_LANE_GATES.md section E5."""
    p, c = r["pooled"], champ["pooled"]
    dg = _fold_delta(r, champ, "guarantee")
    da = _fold_delta(r, champ, "aav")
    dy = _fold_delta(r, champ, "years")
    guar_move = p["guarantee"]["model"] - c["guarantee"]["model"]
    checks: dict = {
        "hard_gates_pass": bool(r["gates_all_pass"]),
        "guar_not_worse_beyond_floor": guar_move <= GUAR_FLOOR_MM,
        "aav_not_worse_beyond_mde": (p["aav"]["model"] - c["aav"]["model"]
                                     <= max(da.get("mde95", 0.0), 0.0)),
        "years_not_worse_beyond_mde": (p["years"]["model"] - c["years"]["model"]
                                       <= max(dy.get("mde95", 0.0), 0.0)),
        "mega_not_worse": (p["mega_guarantee"]["model"]
                           <= c["mega_guarantee"]["model"]),
    }
    if arm_name.startswith("recal"):
        # DECISION criterion: bias conditioned on the PREDICTION. The
        # actual-conditioned version is reported beside it as descriptive only
        # (regression to the mean makes it improvable by de-shrinking).
        checks["mean_abs_ptier_bias_decreases"] = (
            r["mean_abs_ptier_bias"] < champ["mean_abs_ptier_bias"])
    if arm_name == "recal_fit_group":
        checks["side_bias_gap_decreases"] = (
            r["bias_side_gap"] < champ["bias_side_gap"])
    if arm_name.startswith("aav_consistent"):
        checks["aav_improves_or_null"] = (
            p["aav"]["model"] < c["aav"]["model"] or da.get("null", False))
        # PRE-REGISTERED same-deal clause (FA_LANE_GATES.md E5b): the served
        # guarantee, term and AAV must describe ONE deal. Dividing by the
        # continuous years_f leaves projGuar/projYears describing a different
        # deal than projAav, so only the "reprice" mode can satisfy it. This is
        # an a-priori coherence clause, not a metric, and it is what makes
        # AAV_CONSISTENT=True unshippable even when its MAE delta is a null.
        checks["same_deal_coherence"] = (arm_name == "aav_consistent_reprice")
    if arm_name == "rate_line_off":
        checks = {"guar_improves_by_floor": guar_move <= -GUAR_FLOOR_MM}
    verdict = {"checks": checks,
               "pass": all(checks.values()) and arm_name not in WAVE3_LAB_ONLY,
               "lab_only": arm_name in WAVE3_LAB_ONLY,
               "delta_guarantee": dg, "delta_aav": da, "delta_years": dy,
               "guar_move_mm": guar_move,
               "mean_abs_tier_bias_actual_conditioned_DESCRIPTIVE":
                   r["mean_abs_tier_bias"],
               "mean_abs_ptier_bias_prediction_conditioned_DECISION":
                   r["mean_abs_ptier_bias"],
               "bias_side_gap": r["bias_side_gap"]}
    return verdict


def main_wave3():
    t0 = time.time()
    results: dict[str, dict] = {}
    print("wave-3 champion (production defaults):", flush=True)
    _apply({})
    results["champion"] = _score3("champion")
    for name, knobs in WAVE3_ARMS:
        _apply(knobs)
        print(f"arm {name} {knobs}:", flush=True)
        results[name] = _score3(name)
    _apply({})

    verdicts = {n: _wave3_verdict(n, results[n], results["champion"])
                for n, _ in WAVE3_ARMS}
    passing = [n for n, v in verdicts.items() if v["pass"]]
    print("\nwave-3 individually passing:", passing, flush=True)
    for n, v in verdicts.items():
        print(f"  {n:24s} pass={v['pass']}  {v['checks']}", flush=True)

    # COMBINED: at most one recal mode and one aav mode (they are exclusive
    # choices of the same knob), preferring the better-scoring passer.
    combined = None
    knobs: dict = {}
    recal = [n for n in passing if n.startswith("recal")]
    aavs = [n for n in passing if n.startswith("aav_consistent")]
    if recal:
        best = min(recal, key=lambda n: results[n]["mean_abs_ptier_bias"])
        knobs["RECAL_MODE"] = dict(WAVE3_ARMS)[best]["RECAL_MODE"]
        knobs["_recal_arm"] = best
    if aavs:
        best = min(aavs, key=lambda n: results[n]["pooled"]["aav"]["model"])
        knobs["AAV_CONSISTENT"] = dict(WAVE3_ARMS)[best]["AAV_CONSISTENT"]
        knobs["_aav_arm"] = best
    if "rate_line_off" in passing:
        knobs["_XF"] = {"rate_line": False}
    if knobs:
        meta = {k: knobs.pop(k) for k in list(knobs) if k.startswith("_recal_arm")
                or k.startswith("_aav_arm")}
        _apply(knobs)
        print(f"combined {knobs}:", flush=True)
        combined = _score3("combined")
        combined["knobs"] = {k: str(v) for k, v in knobs.items()}
        combined["from_arms"] = meta
        combined["verdict"] = _wave3_verdict("recal_combined", combined,
                                             results["champion"])
        print(f"  combined pass={combined['verdict']['pass']} "
              f"{combined['verdict']['checks']}", flush=True)
    _apply({})

    payload = {
        "experiment": "FA Gate-2 wave-3 E5 market-stage arms (owner program 2026-07-29)",
        "generated_at": date.today().isoformat(),
        "protocol": ("identical forward-chained Gate-2 folds vs the same-process "
                     "production-default champion; criteria PRE-REGISTERED in "
                     "docs/efv-2026-07-30/FA_LANE_GATES.md section E5 before any "
                     "arm ran; paired t-95% over the 9 winters with MDE95 = "
                     "1.96*sd/sqrt(9), overridden by the 0.16 $M corpus floor on "
                     "pooled guarantee MAE"),
        "guarantee_mde95_floor_mm": GUAR_FLOOR_MM,
        "champion": results["champion"],
        "arms": {n: {**results[n], "verdict": verdicts[n]} for n, _ in WAVE3_ARMS},
        "combined": combined,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / "fa_market_feature_lab_wave3_eval.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out} in {payload['runtime_seconds']}s", flush=True)


def main_wave2():
    t0 = time.time()
    import fa_export as fx
    results: dict[str, dict] = {}

    def _reset():
        for f, v in PROD_FLAGS.items():
            fm.X_FEATURES[f] = v

    _reset()
    print("wave-2 champion (production defaults):", flush=True)
    results["champion"] = _score("champion")

    for arm in ARMS2:
        _reset()
        fm.X_FEATURES[arm] = True
        print(f"arm {arm}:", flush=True)
        results[arm] = _score(arm)
    _reset()

    # Serve diagnostics: flag-independent by construction (computes both the
    # raw and aligned regimes itself); read-only, writes nothing.
    print("serve diagnostics (read-only):", flush=True)
    diag = fx.serve_alignment_diagnostics()
    print(f"  supply z raw {diag['supply']['z_raw']} -> aligned {diag['supply']['z_aligned']} "
          f"(mean|z| {diag['supply']['mean_abs_z_raw']} -> {diag['supply']['mean_abs_z_aligned']})",
          flush=True)
    print(f"  age n_changed {diag['age']['n_changed']} of "
          f"{diag['age']['n_members_with_hist']} (deltas "
          f"{diag['age']['min_delta']}..{diag['age']['max_delta']})", flush=True)

    passing = [a for a in ARMS2
               if _passes_wave2(a, results[a], results["champion"], diag)]
    print("wave-2 passing:", passing, flush=True)

    combined = None
    if len(passing) == len(ARMS2):
        for a in ARMS2:
            fm.X_FEATURES[a] = True
        print("combined (record-only, gates nothing):", flush=True)
        combined = _score("combined")
        combined["arms"] = list(ARMS2)
        combined["not_worse"] = _gate_not_worse(combined, results["champion"])
    _reset()

    payload = {
        "experiment": "FA Gate-2 wave-2 serve-side alignment arms (2026-07-16)",
        "generated_at": date.today().isoformat(),
        "protocol": ("identical forward-chained Gate-2 folds vs the production-default "
                     "champion (rate_line=True); pre-registered per-arm criteria in this "
                     "file's WAVE 2 header (gate not-worse clauses + serve diagnostics); "
                     "arms ship independently"),
        "champion": results["champion"],
        "arms": {a: {**results[a], "pass": a in passing} for a in ARMS2},
        "serve_diagnostics": diag,
        "combined": combined,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / "fa_market_feature_lab_wave2_eval.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out} in {payload['runtime_seconds']}s", flush=True)


def main():
    t0 = time.time()
    results: dict[str, dict] = {}

    for f in ARMS:
        fm.X_FEATURES[f] = False
    print("champion (all flags off):", flush=True)
    results["champion"] = _score("champion")

    for arm in ARMS:
        for f in ARMS:
            fm.X_FEATURES[f] = (f == arm)
        print(f"arm {arm}:", flush=True)
        results[arm] = _score(arm)
    passing = [a for a in ARMS if _passes(a, results[a], results["champion"])]
    print("individually passing:", passing, flush=True)

    combined = None
    if len(passing) >= 1:
        for f in ARMS:
            fm.X_FEATURES[f] = f in passing
        print(f"combined {passing}:", flush=True)
        combined = _score("combined")
        combined["arms"] = passing
        combined["ship"] = _passes("rate_line", combined, results["champion"]) \
            if combined else False
    for f in ARMS:
        fm.X_FEATURES[f] = False

    payload = {
        "experiment": "FA Gate-2 feature arms (owner program 2026-07-15)",
        "generated_at": date.today().isoformat(),
        "protocol": "identical forward-chained Gate-2 folds; pre-registered per-arm criteria in this file's header",
        "champion": results["champion"],
        "arms": {a: {**results[a], "pass": a in passing} for a in ARMS},
        "combined": combined,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / "fa_market_feature_lab_eval.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out} in {payload['runtime_seconds']}s", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave2", action="store_true",
                    help="run the 2026-07-16 serve-side alignment arms "
                         "(supply_pop / age_anchor) against the "
                         "production-default champion")
    ap.add_argument("--wave3", action="store_true",
                    help="run the 2026-07-30 E5 market-stage arms (recal, "
                         "aav_consistent, rate_line, pos_group v2)")
    args = ap.parse_args()
    if args.wave3:
        main_wave3()
    elif args.wave2:
        main_wave2()
    else:
        main()
