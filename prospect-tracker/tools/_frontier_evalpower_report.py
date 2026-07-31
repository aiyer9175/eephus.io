# SCRATCH part 3: decision table from _scratch_evalpower.json + _scratch_evalpower2.json.
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A = json.loads((ROOT / "tools" / "_frontier_out" / "_scratch_evalpower.json").read_text(encoding="utf-8"))
try:
    B = json.loads((ROOT / "tools" / "_frontier_out" / "_scratch_evalpower2.json").read_text(encoding="utf-8"))
except OSError:
    B = {}

ns = A["n"]
slopes = {k: v.get("0.1") or v.get(0.1) for k, v in A["slopes"].items()}
null = A["null_band"]

print("Z = 2.49 (one-sided 95%, 80% power).  MDE_eps = MDE / (d metric / d eps), the common")
print("rank-improvement axis (eps = fraction of the way from the model's ranking to truth).\n")

for cand in ("prod_trend", "drop_peakk", "noise"):
    print(f"### candidate = {cand}")
    print(f"{'evaluator':30s} {'n':>5s} {'delta':>9s} {'sd_boot':>8s} {'sd_null':>8s} "
          f"{'sd_arm':>8s} {'pair_x':>6s} {'under_x':>7s} {'MDE':>8s} {'MDE_eps':>8s} "
          f"{'vsEV0':>6s}")
    ev0 = None
    for k in ns:
        s = (A["summary"].get(cand) or {}).get(k)
        if not s:
            continue
        st = s["strat"]
        mde_eps = s["mde_eps"]
        if k == "EV0_current_gate":
            ev0 = mde_eps
        rel = (ev0 / mde_eps) if (ev0 and mde_eps) else None
        print(f"{k:30s} {ns[k]:>5d} {st['delta']:>9.5f} {st['sd']:>8.5f} "
              f"{null[k]['sd']:>8.5f} {st['sd_arm_base']:>8.5f} "
              f"{str(st['pairing_gain_x']):>6s} {str(s['sd_understatement_x']):>7s} "
              f"{s['mde_95_80']:>8.4f} {mde_eps:>8.4f} "
              f"{(f'{rel:.2f}x' if rel else '-'):>6s}")
    print()

print("\n=== SNR (|delta| / sd_boot) by candidate, i.e. how loudly each evaluator hears a REAL change")
print(f"{'evaluator':30s} {'prod_trend':>11s} {'drop_peakk':>11s} {'noise':>9s}")
for k in ns:
    row = []
    for c in ("prod_trend", "drop_peakk", "noise"):
        s = (A["summary"].get(c) or {}).get(k)
        row.append(abs(s["strat"]["delta"]) / s["strat"]["sd"] if s and s["strat"]["sd"] else 0)
    print(f"{k:30s} {row[0]:>11.2f} {row[1]:>11.2f} {row[2]:>9.2f}")
