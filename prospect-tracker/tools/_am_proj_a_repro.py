"""AM-PROJ (a): re-derive the registered champion horizon backtest.

Runs proj_eval.run() with persist=False (data/proj_horizon_eval.json is staged
by another workflow and must NOT be overwritten) and diffs every cell against
the registered artifact.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import proj_eval  # noqa: E402

BASES = [2017, 2018, 2019, 2021]

t0 = time.time()
got = proj_eval.run(BASES, persist=False)
print("elapsed %.1fs" % (time.time() - t0))

reg = json.loads((ROOT / "data" / "proj_horizon_eval.json").read_text())
print("registered n_players", reg["n_players"], "| rerun n_players", got["n_players"])
keys = ["n", "mae", "bias", "mae_star", "bias_star", "tail_pred_ge3",
        "tail_act_ge3", "tail_ratio", "coverage", "coverage_survived",
        "n_survived", "pinball_q10", "pinball_q90"]
print(f"{'h':>2} {'metric':<18} {'registered':>11} {'rerun':>11} {'delta':>11}")
worst = 0.0
for h in ("1", "2", "3", "4", "5"):
    r = reg["horizons"][h]
    g = got["horizons"][int(h)] if int(h) in got["horizons"] else got["horizons"][h]
    for k in keys:
        a, b = r.get(k), g.get(k)
        if a is None or b is None:
            continue
        d = b - a
        flag = "" if abs(d) < 1e-9 else ("  <<< DIFF" if abs(d) > 1e-6 else "")
        if abs(d) > worst:
            worst = abs(d)
        print(f"{h:>2} {k:<18} {a:>11.4f} {b:>11.4f} {d:>11.4f}{flag}")
print("MAX ABS DELTA:", worst)
json.dump(got, open(ROOT / "tools" / "_am_proj_out_repro.json", "w"), indent=1)
