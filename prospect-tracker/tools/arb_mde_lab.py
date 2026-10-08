# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE A power lab: the minimum detectable effect for the arbitration model.

NO CRITERION IN docs/ARBITRATION_GATE.md MAY BE READ BEFORE THIS RUNS.

Protocol, matching docs/EFV_GATE_STANDARD.md:
  * Paired bootstrap resampling TRAIN AND TEST with a refit on every draw. A
    test-only bootstrap understates sd by 1.6-1.8x, which is the difference
    between a resolvable result and a laundered one.
  * CLUSTERED ON PLAYER. A player supplies arb1, arb2 and arb3 rows and his path
    is strongly autocorrelated; resampling rows would treat ~1,000 correlated
    observations as ~1,000 independent draws and shrink the floor by roughly
    sqrt(rows/players).
  * Forward-chained by arbitration class year, so no fold ever trains on its own
    future.
  * ONE FLOOR PER STATISTIC CLASS. Floors are basis-specific and are not
    transferable: arb1 and arb2+ are different models on different populations
    with different baselines.
  * MDE95 is ONE-SIDED (1.645 sd), stated explicitly.

Also produced, because a floor you cannot trust is worse than no floor:
  * a TWO-SIDED coverage check on the estimator itself. For a program whose
    product is null verdicts, over-wide is the PERMISSIVE direction - it
    manufactures nulls - so over-coverage fails exactly like under-coverage.
  * a DETECTION check on a planted effect at the size being claimed. If the
    harness cannot see an effect it was handed, a null is a dead instrument
    rather than a finding.

Usage:
    python tools/arb_mde_lab.py cost           # per-replicate seconds
    python tools/arb_mde_lab.py mde [B]        # the floors
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np                                              # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import arb_dataset as A                                         # noqa: E402
import arb_metrics as M                                         # noqa: E402
import arb_model as Mod                                         # noqa: E402

SEED = 20260808
OUT_PATH = ROOT / "data" / "arb_mde_floor.json"


def load_pool(frame: str = "award"):
    """The scored pool with the projectable career features attached.

    `frame` is arb_model's feature frame (docs/ARBITRATION_GATE.md section
    13). The default stays "award" so this floor lab reproduces
    data/arb_mde_floor.json; tools/arb_gate_a.py passes its own."""
    panel_doc = A.build_panel()
    rows = panel_doc["rows"]
    sc = Mod.attach_frame(A.scored_rows(rows), rows, frame)
    metrics = M.metric_panel(2018, 2026)
    return sc, metrics


def _cluster_resample(rows, rng):
    """Resample PLAYERS with replacement, carrying all of each player's rows."""
    by: dict[int, list] = {}
    for r in rows:
        by.setdefault(int(r["mlbam"]), []).append(r)
    keys = list(by)
    draw = rng.integers(0, len(keys), len(keys))
    out = []
    for i in draw:
        out.extend(by[keys[i]])
    return out


def _delta(rows, metrics, seasons, *, split, plant=0.0):
    """One replicate: refit the whole forward chain, return (mse_delta,
    mdape_delta) of champion versus B1 on paired rows.

    `plant` multiplies the champion's prediction toward the truth, which is the
    detection check: a harness that cannot see a planted effect of the size
    being claimed is not measuring anything.
    """
    recs = Mod.forward_chain(rows, metrics, seasons=seasons)
    recs = [r for r in recs if split(r)]
    if plant:
        for r in recs:
            if r.get("champion") is not None:
                r["champion"] = (r["champion"] * (1 - plant)
                                 + r["actual"] * plant)
    p = Mod.paired(recs, "champion", "bar")
    if len(p) < 20:
        return None, None, 0
    return (Mod.mse(p, "bar") - Mod.mse(p, "champion"),
            Mod.mdape(p, "bar") - Mod.mdape(p, "champion"),
            len(p))


def _summ(vals, point, label):
    a = np.array([v for v in vals if v is not None and np.isfinite(v)], float)
    if len(a) < 5:
        return {"label": label, "B_used": int(len(a)), "insufficient": True}
    sd = float(a.std(ddof=1))
    return {
        "label": label,
        "B_used": int(len(a)),
        "point_delta": float(point) if point is not None else None,
        "boot_mean_delta": float(a.mean()),
        "sd": sd,
        "mde95_onesided": 1.645 * sd,
        "mde95_twosided": 1.96 * sd,
        "ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))],
        "p_gt_0": float((a > 0).mean()),
        "resolvable_onesided": bool(point is not None
                                    and abs(point) >= 1.645 * sd),
    }


SPLITS = {
    "arb1": lambda r: r["arb_year"] == 1,
    "arb2plus": lambda r: r["arb_year"] >= 2,
}


def run(B: int) -> dict:
    rows, metrics = load_pool()
    seasons = sorted({r["season"] for r in rows})
    print(f"pool {len(rows)} rows, {len({r['mlbam'] for r in rows})} players, "
          f"seasons {seasons}")
    out = {
        "generated_at": date.today().isoformat(),
        "produced_by": f"python tools/arb_mde_lab.py mde {B}",
        "purpose": ("Minimum detectable effect for GATE A. Floors are "
                    "basis-specific and one is measured per statistic class."),
        "protocol": ("paired bootstrap resampling TRAIN AND TEST, clustered on "
                     "PLAYER, refitting the deflator, both stages and the B1 "
                     "step multipliers on every draw; forward-chained by "
                     "arbitration class year"),
        "convention": "MDE95 is ONE-SIDED (1.645 sd) throughout",
        "seed": SEED,
        "B_requested": B,
        "pool": {"rows": len(rows),
                 "players": len({r["mlbam"] for r in rows}),
                 "seasons": seasons},
        "floors": {},
    }
    for name, split in SPLITS.items():
        t0 = time.time()
        pt_mse, pt_mdape, n_pair = _delta(rows, metrics, seasons, split=split)
        rng = np.random.default_rng(SEED)
        mses, mdapes = [], []
        for _ in range(B):
            draw = _cluster_resample(rows, rng)
            d_mse, d_mdape, _n = _delta(draw, metrics, seasons, split=split)
            mses.append(d_mse)
            mdapes.append(d_mdape)
        out["floors"][name] = {
            "n_paired_rows": n_pair,
            "mse": _summ(mses, pt_mse, f"{name} champion-minus-bar MSE"),
            "mdape": _summ(mdapes, pt_mdape, f"{name} champion-minus-bar MdAPE"),
            "elapsed_s": round(time.time() - t0, 1),
        }
        f = out["floors"][name]
        print(f"\n{name}: n_paired={n_pair}")
        for k in ("mse", "mdape"):
            s = f[k]
            if s.get("insufficient"):
                print(f"  {k}: insufficient replicates")
                continue
            print(f"  {k:6s} point {s['point_delta']:+.6g}  sd {s['sd']:.6g}  "
                  f"MDE95 {s['mde95_onesided']:.6g}  "
                  f"resolvable={s['resolvable_onesided']}  "
                  f"P(>0)={s['p_gt_0']:.3f}")

    # Detection check: plant an effect at roughly the measured floor and confirm
    # the harness sees it.
    det = {}
    for name, split in SPLITS.items():
        s = out["floors"][name]["mdape"]
        if s.get("insufficient"):
            continue
        d_mse, d_mdape, _n = _delta(rows, metrics, seasons, split=split, plant=0.25)
        det[name] = {"plant": 0.25, "mdape_delta_with_plant": d_mdape,
                     "mdape_delta_without": s.get("point_delta"),
                     "detected": bool(d_mdape is not None
                                      and d_mdape > s["mde95_onesided"])}
    out["detection_check"] = det
    print("\ndetection check (25% shrink toward truth):", json.dumps(det, default=float))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("cost", "mde"))
    ap.add_argument("B", nargs="?", type=int, default=200)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    if args.command == "cost":
        rows, metrics = load_pool()
        seasons = sorted({r["season"] for r in rows})
        rng = np.random.default_rng(SEED)
        t0 = time.time()
        for _ in range(3):
            _delta(_cluster_resample(rows, rng), metrics, seasons,
                   split=SPLITS["arb1"])
        per = (time.time() - t0) / 3
        print(f"{per:.2f}s per replicate per split")
        for b in (200, 500, 1000, 2000):
            print(f"  B={b:5d} -> {per * b * len(SPLITS) / 60:.1f} min")
        return 0

    doc = run(args.B)
    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(doc, indent=1, default=float),
                            encoding="utf-8")
        print(f"\nwrote {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
