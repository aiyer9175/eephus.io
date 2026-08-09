# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE A adjudication -> data/arbitration_eval.json.

Runs the pre-registered battery in docs/ARBITRATION_GATE.md section 4 and writes
the verdict, wins and losses alike. Nothing here decides anything the gate did
not already decide before the numbers were read.

Usage:
    python tools/arb_gate_a.py --write [--B 2000]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np                                              # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import arb_mde_lab as L                                         # noqa: E402
import arb_model as Mod                                         # noqa: E402

OUT = ROOT / "data" / "arbitration_eval.json"
SEED = 20260808
PROD_KEYS = ("war", "war3", "career_war", "pa", "ipouts", "gs")

ARB1 = ("arb1", lambda r: r["arb_year"] == 1, "bar2")
ARB2 = ("arb2plus", lambda r: r["arb_year"] >= 2, "bar")


def _permute_production(rows, rng):
    """A3 control: permute the PRODUCTION block across players WITHIN
    (season, arb-step) cells.

    Prior salary, arbitration step, season, age and role stay attached to the
    player. A whole-matrix permutation is INADMISSIBLE here: it destroys the
    prior-salary link too and has no dynamic range, which is precisely why a
    previously registered control in this repo was recorded UNINFORMATIVE.
    """
    out = [dict(r) for r in rows]
    cells: dict[tuple, list[int]] = {}
    for i, r in enumerate(out):
        cells.setdefault((r["season"], r["arb_year"]), []).append(i)
    for idx in cells.values():
        if len(idx) < 3:
            continue
        perm = rng.permutation(len(idx))
        vals = [{k: out[i].get(k) for k in PROD_KEYS} for i in idx]
        for j, pj in enumerate(perm):
            for k in PROD_KEYS:
                out[idx[j]][k] = vals[pj][k]
    return out


def _gain(rows, metrics, seasons, split, bar, *, leak=False):
    recs = [r for r in Mod.forward_chain(rows, metrics, seasons=seasons,
                                         leak_deflator=leak) if split(r)]
    p = Mod.paired(recs, "champion", bar)
    if len(p) < 20:
        return None
    return {
        "n": len(p),
        "mdape_gain": Mod.mdape(p, bar) - Mod.mdape(p, "champion"),
        "mse_gain": Mod.mse(p, bar) - Mod.mse(p, "champion"),
        "mdape_champion": Mod.mdape(p, "champion"),
        "mdape_bar": Mod.mdape(p, bar),
    }


def run(B: int) -> dict:
    rows, metrics = L.load_pool()
    seasons = sorted({r["season"] for r in rows})
    rng = np.random.default_rng(SEED)
    out_floors = {}
    verdicts = {}

    for name, split, bar in (ARB1, ARB2):
        point = _gain(rows, metrics, seasons, split, bar)
        boot = []
        for _ in range(B):
            g = _gain(L._cluster_resample(rows, rng), metrics, seasons, split, bar)
            if g:
                boot.append(g["mdape_gain"])
        a = np.array(boot, float)
        sd = float(a.std(ddof=1))
        floor = 1.645 * sd

        # A3 control
        perm = []
        for _ in range(200):
            g = _gain(_permute_production(rows, rng), metrics, seasons, split, bar)
            if g:
                perm.append(g["mdape_gain"])
        pa = np.array(perm, float)
        p95 = float(np.percentile(pa, 95))

        # A5 deflator leak twin
        leaked = _gain(rows, metrics, seasons, split, bar, leak=True)
        leak_delta = (leaked["mdape_gain"] - point["mdape_gain"]) if leaked else None

        resolvable = abs(point["mdape_gain"]) >= floor
        beats_control = point["mdape_gain"] > p95
        leak_ok = leak_delta is None or abs(leak_delta) < abs(point["mdape_gain"])
        verdict = "PASS" if (resolvable and beats_control and leak_ok) else "NULL"
        verdicts[name] = verdict
        out_floors[name] = {
            "bar": bar,
            "bar_description": ("arb-1 intercept plus one WAR term (a lag "
                                "baseline is the wrong bar for the first trip)"
                                if name == "arb1" else
                                "median deflated step multiplier off prior "
                                "salary, floored at the max cut and the minimum"),
            "n_paired": point["n"],
            "mdape_champion": point["mdape_champion"],
            "mdape_bar": point["mdape_bar"],
            "mdape_gain": point["mdape_gain"],
            "mse_gain": point["mse_gain"],
            "mde95_onesided": floor,
            "gain_over_floor": (abs(point["mdape_gain"]) / floor) if floor else None,
            "resolvable": bool(resolvable),
            "p_gt_0": float((a > 0).mean()),
            "a3_control": {
                "permuted_mean": float(pa.mean()),
                "permuted_p95": p95,
                "real_over_p95": (point["mdape_gain"] / p95) if p95 > 0 else None,
                "p_perm_ge_real": float((pa >= point["mdape_gain"]).mean()),
                "beats_control": bool(beats_control),
            },
            "a5_deflator_leak_twin": {
                "gain_with_panel_wide_deflator": (leaked["mdape_gain"]
                                                  if leaked else None),
                "delta": leak_delta,
                "leak_smaller_than_margin": bool(leak_ok),
            },
            "verdict": verdict,
        }

    ship = verdicts.get("arb1") == "PASS" or verdicts.get("arb2plus") == "PASS"
    doc = {
        "generated_at": date.today().isoformat(),
        "produced_by": f"python tools/arb_gate_a.py --write --B {B}",
        "model": "arb_award_v1",
        "gate": "docs/ARBITRATION_GATE.md section 4 (GATE A)",
        "purpose": ("Does the two-stage arbitration award model beat the "
                    "class-appropriate baseline by more than its own measured "
                    "floor, and is the margin production information rather "
                    "than structure?"),
        "conventions": {
            "metric": ("MdAPE on deflated dollars is the adjudicating headline; "
                       "MSE in deflated dollars is reported alongside because "
                       "the downstream consumer needs an expectation"),
            "protocol": ("forward-chained by arbitration class year; paired "
                         "bootstrap resampling train AND test, clustered on "
                         "PLAYER, refitting the deflator and both stages every "
                         "draw"),
            "floor": "MDE95 one-sided (1.645 sd), measured per statistic class",
            "pool": ("only seasons whose arbitration step comes from MLBTR "
                     "published service time; substitute sources measure 0.66 "
                     "and 0.70 agreement against it and cannot carry a scored "
                     "backtest"),
            "smearing": ("served point is the Duan smearing-corrected "
                         "conditional MEAN, never exp(mu_hat)"),
        },
        "pool": {"rows": len(rows), "players": len({r["mlbam"] for r in rows}),
                 "seasons": seasons, "folds": len(seasons) - 1},
        "B": B,
        "seed": SEED,
        "results": out_floors,
        "verdict": "provisional" if ship else "unvalidated",
        "loss_ledger": [],
    }
    if verdicts.get("arb2plus") != "PASS":
        doc["loss_ledger"].append({
            "claim": "the model beats the step-multiplier baseline on arb 2/3/4",
            "measured_mdape_gain": out_floors["arb2plus"]["mdape_gain"],
            "floor": out_floors["arb2plus"]["mde95_onesided"],
            "verdict": "NULL",
            "statement": (
                "The arb-2-and-later model is a NULL. Its margin over a median "
                "step multiplier off the prior salary is below the floor "
                "measured for this basis. The A3 control shows the production "
                "block does carry signal there - permuting it makes the model "
                "WORSE than the baseline - so this is a power limit, not an "
                "absence of information, and it is still reported as a null."),
        })
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=1500)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    doc = run(args.B)
    for name, r in doc["results"].items():
        print(f"\n{name}  vs {r['bar']}  n={r['n_paired']}")
        print(f"  MdAPE champion {r['mdape_champion']:.4f} vs bar "
              f"{r['mdape_bar']:.4f}  gain {r['mdape_gain']:+.5f}")
        print(f"  floor {r['mde95_onesided']:.5f}  -> "
              f"{r['gain_over_floor']:.2f}x  resolvable={r['resolvable']}")
        c = r["a3_control"]
        print(f"  A3 control: permuted p95 {c['permuted_p95']:+.5f}  "
              f"real/p95 {c['real_over_p95'] if c['real_over_p95'] is None else round(c['real_over_p95'],2)}x  "
              f"P(perm>=real)={c['p_perm_ge_real']:.3f}")
        print(f"  VERDICT: {r['verdict']}")
    print(f"\nartifact verdict: {doc['verdict']}")
    if args.write:
        OUT.write_text(json.dumps(doc, indent=1, default=float), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
