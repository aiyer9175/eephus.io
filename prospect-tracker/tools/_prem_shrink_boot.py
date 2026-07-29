# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Paired bootstrap + permutation null for the conditional-lambda shrinkage lane.

Per docs/EFV_GATE_STANDARD.md section 2: every draw resamples the WHOLE pool (train AND
test) at the player level and REFITS ridge + consensus OLS + the inner-forward-chain
stratum lambdas. Arms are evaluated on the SAME resample so the deltas are paired.

Reported per arm: d_rho pooled, d_rho on the SERVED (has-MiLB-track-record) population,
d_t45, d_auc (pooled and served), and the rho INSIDE Bradfield's own stratum.
"""
from __future__ import annotations
import sys, json, random, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools"))

import _prem_shrink_lab as L

SIDE = "hit"
B = int(sys.argv[1]) if len(sys.argv) > 1 else 300
SEED = 20260725
LAM_G = L.blend_lambda(SIDE)

ARMS = [
    ("HIER:k=25", "hier", 25),
    ("HIER:k=50", "hier", 50),
    ("GATE:dip=0.5", "gate", 0.50),
    ("GATE:dip=1.0", "gate", 1.00),
    ("GLOB:0.50", "global", 0.50),
    ("GLOB:0.80", "global", 0.80),
    ("RAND(control)", "rand", 0.50),
]

M = ["rho_pooled", "rho_served", "t45", "rho_target", "auc_pooled", "auc_served"]


def metrics(side, mode, param, rows, seed=None):
    pooled, auc_rows, _ = L.run_arm(side, mode, param, rand_seed=seed, rows=rows)
    return L.summarize(pooled, auc_rows)


def main():
    rnd = random.Random(SEED)
    base_pool = L.data_for(SIDE)
    n = len(base_pool)

    draws = {a[0]: {m: [] for m in M} for a in ARMS}
    t0 = time.time()
    ok = 0
    for b in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        rows = [base_pool[i] for i in idx]
        try:
            base = metrics(SIDE, "global", LAM_G, rows)
            if base["rho_pooled"] is None:
                continue
            for name, mode, param in ARMS:
                s = metrics(SIDE, mode, param, rows,
                            seed=(rnd.randrange(10 ** 6) if mode == "rand" else None))
                for m in M:
                    if s.get(m) is not None and base.get(m) is not None:
                        draws[name][m].append(s[m] - base[m])
            ok += 1
        except Exception as e:            # a degenerate resample; drop the draw
            if b < 3:
                print("draw error:", type(e).__name__, e, flush=True)
            continue
        if (b + 1) % 25 == 0:
            print(f"  draw {b+1}/{B} ok={ok} ({time.time()-t0:.0f}s)", flush=True)

    out = {"B": B, "draws_ok": ok, "side": SIDE, "lam_global": LAM_G,
           "protocol": ("player-level paired bootstrap of the FULL pool (debuted+bust); "
                        "ridge + consensus OLS + inner-forward-chain stratum lambdas "
                        "refit on every draw; arms share each resample"),
           "arms": {}}
    print(f"\n{'arm':16s} {'metric':12s} {'mean':>9s} {'CI95_lo':>9s} {'CI95_hi':>9s}  verdict")
    for name, _, _ in ARMS:
        out["arms"][name] = {}
        for m in M:
            d = sorted(draws[name][m])
            if len(d) < 30:
                continue
            mean = sum(d) / len(d)
            lo, hi = d[int(0.025 * len(d))], d[min(len(d) - 1, int(0.975 * len(d)))]
            v = "POSITIVE" if lo > 0 else ("NEGATIVE" if hi < 0 else "NULL")
            out["arms"][name][m] = {"mean": round(mean, 5), "ci95": [round(lo, 5), round(hi, 5)],
                                    "verdict": v, "n_draws": len(d)}
            print(f"{name:16s} {m:12s} {mean:+9.5f} {lo:+9.5f} {hi:+9.5f}  {v}")
        print()

    dest = ROOT / "tools" / "_prem_shrink_boot_out.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {dest}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    raise SystemExit(main())
