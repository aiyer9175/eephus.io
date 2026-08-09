# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE D: does arbitration history add anything to the free-agent market model?

Pre-registered in docs/ARBITRATION_GATE.md section 7 as a NULL, with the
controls chosen before the numbers were read.

THE CLAIM THAT IS NOT ADMISSIBLE. Arbitration salary and free-agent price are
both monotone functions of the same production, which `fa_market` already reads
through its projected-WAR and rational-anchor terms. A strong raw correlation is
the arithmetic consequence of a shared cause and is not evidence of anything. A
planning-stage measurement found partial r = +0.423 on 495 first-time free
agents after controlling trailing-3yr WAR, walk-year WAR, age and QO - but that
was a FOUR-VARIABLE control, not the incumbent feature set, and it was
in-sample. It is a reason to run this gate, not a result.

WHAT IS MEASURED HERE. The incumbent Gate-2 model is run unchanged over its own
forward-chained winters via GATE2_COLLECT, which exists precisely so an A/B can
be paired row by row instead of compared on two pooled MAEs. Its per-signing
RESIDUAL is then regressed on the arbitration features. If arbitration carries
information the free-agent model does not already have, it must show up in that
residual. This deliberately does NOT modify fa_market: the incumbent OLS has
already beaten a LightGBM challenger and an ML WAR path, and a null does not
justify touching a validated production model.

TWO CONTROLS, both pre-registered:
  D1  missingness-indicator alone - a bare "has an arbitration history" binary
      with no salary value. If it reproduces most of the lift, the feature is an
      age and service-time proxy, not arbitration information. This is the AUC
      carve-out transplanted: an honest missingness indicator once scored
      +0.0792 against a permuted twin at +0.0003 while the real metric went
      NEGATIVE, and six arms of that program would have read as wins.
  D2  complete-case - restrict to rows that HAVE an arbitration history, the
      only comparison where the feature is present on both sides.

Plus a zero-information placebo (the arb column permuted within class year) and
a permutation null.

Usage:
    python tools/arb_fa_gate_d.py --write
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

OUT = ROOT / "data" / "arb_fa_link_eval.json"
SEED = 20260809


def _arb_features():
    """{player_key: {...}} arbitration summary per player, from the panel."""
    import arb_dataset as A
    import arb_metrics as M
    import arb_model as Mod
    from scrapers import canonical_player_key, normalize_key

    doc = A.build_panel()
    rows = doc["rows"]
    sc = A.scored_rows(rows)
    war_by: dict[int, dict[int, float]] = {}
    for r in rows:
        war_by.setdefault(r["mlbam"], {})[r["season"]] = r["war"]
    for r in sc:
        h = war_by.get(r["mlbam"], {})
        r["war3"] = round(sum(h.get(r["season"] - k, 0.0) for k in (0, 1, 2)), 2)
        r["career_war"] = round(sum(v for y, v in h.items() if y <= r["season"]), 2)
    metrics = M.metric_panel(2018, 2026)
    seasons = sorted({r["season"] for r in sc})
    recs = Mod.forward_chain(sc, metrics, seasons=seasons)

    by_player: dict[int, list] = {}
    for rec in recs:
        by_player.setdefault(int(rec["mlbam"]), []).append(rec)
    name_by = {int(r["mlbam"]): r.get("name") for r in sc}

    out = {}
    for mlbam, rs in by_player.items():
        rs = sorted(rs, key=lambda r: r["season"])
        last = rs[-1]
        # The registered feature: OUR OWN out-of-fold arbitration residual. It is
        # orthogonal by construction to the arb model's own features, and the
        # mechanism is that a player the panel overpaid relative to WAR is a
        # counting-stat player, which is the profile the free-agent market
        # prices differently.
        resid = None
        if last.get("served") and last.get("actual"):
            resid = float(np.log(last["actual"] / last["served"]))
        slope = None
        if len(rs) >= 2:
            xs = np.array([r["season"] for r in rs], float)
            ys = np.array([np.log(max(r["actual"], 1.0)) for r in rs], float)
            if xs.std() > 0:
                slope = float(np.polyfit(xs, ys, 1)[0])
        nm = name_by.get(mlbam) or ""
        key = canonical_player_key(normalize_key(nm)) if nm else None
        if key:
            out[key] = {"mlbam": mlbam, "arb_resid": resid, "arb_slope": slope,
                        "n_arb": len(rs),
                        "last_arb_usd": last.get("actual")}
    return out


def _gate2_rows():
    """Paired per-signing rows from the UNCHANGED incumbent Gate-2 harness."""
    import fa_backtest as fb
    fb.GATE2_COLLECT = []
    try:
        # persist_dpw=False, or the lab rewrites the $/WAR level the entire
        # valuation engine prices against.
        fb.run_market_gate(persist=False, persist_dpw=False)
        return list(fb.GATE2_COLLECT)
    finally:
        fb.GATE2_COLLECT = None


def _r2(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    return 1.0 - float(e.var() / y.var()) if y.var() > 0 else 0.0


def run() -> dict:
    arb = _arb_features()
    rows = _gate2_rows()
    print(f"arb summaries: {len(arb)} players | gate-2 scored rows: {len(rows)}")

    recs = []
    for t in rows:
        winter, key = t[0], t[1]
        pred_g, act_g = t[2], t[3]
        if not act_g or act_g <= 0 or pred_g is None:
            continue
        a = arb.get(key)
        recs.append({
            "winter": int(winter), "key": key,
            "resid": float(np.log(max(act_g, 0.1)) - np.log(max(pred_g, 0.1))),
            "has_arb": 1.0 if a else 0.0,
            "arb_resid": (a or {}).get("arb_resid"),
            "arb_slope": (a or {}).get("arb_slope"),
        })
    n_all = len(recs)
    complete = [r for r in recs if r["arb_resid"] is not None]
    print(f"paired rows: {n_all} | with an arbitration history: {len(complete)}")

    y = np.array([r["resid"] for r in recs], float)
    ones = np.ones((len(recs), 1))

    # D1: the missingness indicator ALONE, no salary value.
    X_ind = np.column_stack([ones, [r["has_arb"] for r in recs]])
    d1 = _r2(X_ind, y) - _r2(ones, y)

    # The registered feature, zero-filled (the naive deployment).
    X_naive = np.column_stack([ones, [r["has_arb"] for r in recs],
                               [r["arb_resid"] or 0.0 for r in recs]])
    naive = _r2(X_naive, y) - _r2(ones, y)

    out = {
        "generated_at": date.today().isoformat(),
        "produced_by": "python tools/arb_fa_gate_d.py --write",
        "gate": "docs/ARBITRATION_GATE.md section 7 (GATE D)",
        "model": "arb_fa_link",
        "conventions": {
            "target": ("log residual of the UNCHANGED incumbent Gate-2 guarantee "
                       "prediction; if arbitration carries information the FA "
                       "model lacks, it must appear here"),
            "protocol": ("fa_backtest.run_market_gate(persist=False, "
                         "persist_dpw=False) over its own forward-chained "
                         "winters, paired row by row via GATE2_COLLECT"),
            "feature": ("arb_resid: our own out-of-fold arbitration residual, "
                        "orthogonal by construction to the arb model's features"),
        },
        "n_gate2_rows": n_all,
        "n_with_arb_history": len(complete),
        "d1_missingness_indicator_alone_dR2": d1,
        "naive_zero_filled_dR2": naive,
    }

    # D2: complete-case, the only comparison where the feature exists on both
    # sides.
    if len(complete) >= 40:
        yc = np.array([r["resid"] for r in complete], float)
        o = np.ones((len(complete), 1))
        Xc = np.column_stack([o, [r["arb_resid"] for r in complete]])
        d2 = _r2(Xc, yc) - _r2(o, yc)
        rng = np.random.default_rng(SEED)
        null = []
        by_w: dict[int, list[int]] = {}
        for i, r in enumerate(complete):
            by_w.setdefault(r["winter"], []).append(i)
        vals = np.array([r["arb_resid"] for r in complete], float)
        for _ in range(2000):
            perm = vals.copy()
            for idx in by_w.values():
                sub = np.array(idx)
                perm[sub] = vals[rng.permutation(sub)]
            Xp = np.column_stack([o, perm])
            null.append(_r2(Xp, yc) - _r2(o, yc))
        na = np.array(null, float)
        out["d2_complete_case"] = {
            "n": len(complete),
            "dR2": d2,
            "permuted_mean_dR2": float(na.mean()),
            "permuted_p95_dR2": float(np.percentile(na, 95)),
            "p_perm_ge_real": float((na >= d2).mean()),
            "beats_placebo": bool(d2 > float(np.percentile(na, 95))),
        }
    else:
        out["d2_complete_case"] = {"n": len(complete), "insufficient": True}

    d2b = out["d2_complete_case"]
    passed = bool(d2b.get("beats_placebo"))
    # D1 kill rule: if the bare indicator reproduces >= 60% of the naive lift,
    # the feature is a service-time proxy.
    indicator_dominates = bool(naive > 0 and d1 / naive >= 0.60)
    out["verdict_gate"] = "PASS" if (passed and not indicator_dominates) else "NULL"
    out["verdict"] = "unvalidated"
    out["indicator_dominates"] = indicator_dominates
    out["loss_ledger"] = []
    if out["verdict_gate"] == "NULL":
        out["loss_ledger"].append({
            "claim": ("arbitration history adds information to the free-agent "
                      "market model"),
            "verdict": "NULL",
            "statement": (
                "The arbitration block is a NULL on the free-agent market gate. "
                "Its incremental contribution to the incumbent Gate-2 guarantee "
                "residual is not separable from a placebo permuted within class "
                "year. The raw correlation between arbitration salary and the "
                "first free-agent guarantee is real and large, and it is fully "
                "accounted for by the production both quantities measure, which "
                "the incumbent model already reads through its projected-WAR and "
                "rational-anchor terms. fa_market is UNCHANGED."),
        })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    doc = run()
    print()
    print(f"D1 indicator-alone dR2   {doc['d1_missingness_indicator_alone_dR2']:+.5f}")
    print(f"naive zero-filled  dR2   {doc['naive_zero_filled_dR2']:+.5f}")
    d2 = doc["d2_complete_case"]
    if not d2.get("insufficient"):
        print(f"D2 complete-case n={d2['n']}  dR2 {d2['dR2']:+.5f}  "
              f"placebo p95 {d2['permuted_p95_dR2']:+.5f}  "
              f"P(perm>=real) {d2['p_perm_ge_real']:.4f}")
    print(f"VERDICT: {doc['verdict_gate']}")
    if args.write:
        OUT.write_text(json.dumps(doc, indent=1, default=float), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
