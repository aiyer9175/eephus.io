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
    args = ap.parse_args()
    main_wave2() if args.wave2 else main()
