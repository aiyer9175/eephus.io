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
    main()
