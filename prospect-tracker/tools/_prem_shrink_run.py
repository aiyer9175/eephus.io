# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Point-estimate driver for the conditional-lambda shrinkage lane. Read-only."""
from __future__ import annotations
import sys, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools"))

import _prem_shrink_lab as L

SIDE = sys.argv[1] if len(sys.argv) > 1 else "hit"

ARMS = [("BASE", "global", L.blend_lambda(SIDE))]
ARMS += [(f"GLOB:{x:.2f}", "global", x) for x in (0.40, 0.50, 0.55, 0.60, 0.65, 0.75, 0.80)]
ARMS += [(f"HIER:k={k}", "hier", k) for k in (25, 50, 100, 200)]
ARMS += [(f"GATE:dip={d}", "gate", d) for d in (0.25, 0.50, 1.00)]
ARMS += [(f"TGT:dip={d}", "target", d) for d in (0.50, 1.00)]
ARMS += [(f"RAND:s={s}", "rand", 0.50) for s in (11, 12, 13, 14, 15)]

out = {}
t0 = time.time()
for i, (name, mode, param) in enumerate(ARMS):
    seed = int(name.split("=")[1]) if mode == "rand" else None
    pooled, auc_rows, lams = L.run_arm(SIDE, mode, param, rand_seed=seed,
                                       collect_lams=(mode in ("hier", "gate", "target")))
    s = L.summarize(pooled, auc_rows)
    s["mean_lam"] = round(sum(x["lam"] for x in pooled) / max(1, len(pooled)), 4)
    s["mean_lam_target"] = (round(sum(x["lam"] for x in pooled if x["is_target"]) /
                                  max(1, sum(1 for x in pooled if x["is_target"])), 4)
                            if any(x["is_target"] for x in pooled) else None)
    if lams:
        s["lam_by_fold"] = lams
    out[name] = s
    print(f"[{i+1}/{len(ARMS)}] {name:16s} rho={s['rho_pooled']:.4f} "
          f"srv={s['rho_served']:.4f} t45={(s['t45'] or float('nan')):.4f} "
          f"tgt={(s['rho_target'] if s['rho_target'] is not None else float('nan')):+.4f} "
          f"auc={s['auc_pooled']:.4f} aucS={s['auc_served']:.4f} "
          f"lam~{s['mean_lam']:.3f} lamT={s['mean_lam_target']}  ({time.time()-t0:.0f}s)",
          flush=True)

base = out["BASE"]
print("\n---- DELTAS vs BASE ----")
for name, s in out.items():
    if name == "BASE":
        continue
    print(f"{name:16s} d_rho={s['rho_pooled']-base['rho_pooled']:+.4f} "
          f"d_srv={s['rho_served']-base['rho_served']:+.4f} "
          f"d_t45={(s['t45']-base['t45']) if (s['t45'] is not None and base['t45'] is not None) else float('nan'):+.4f} "
          f"d_tgt={(s['rho_target']-base['rho_target']) if (s['rho_target'] is not None and base['rho_target'] is not None) else float('nan'):+.4f} "
          f"d_auc={s['auc_pooled']-base['auc_pooled']:+.4f} "
          f"d_aucS={s['auc_served']-base['auc_served']:+.4f}")

dest = ROOT / "tools" / f"_prem_shrink_points_{SIDE}.json"
dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
print(f"\nwrote {dest}")
