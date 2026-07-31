# SCRATCH part 4: origin-window sweep UNDER THE PRODUCTION FIT CONFIG.
# frame = train on full pool minus recent busts (production), test on debuted rows.
# metric = block-normalized pooled Spearman (blocks = side x cohort-year) + contributor AUC.
# Paired cohort-clustered refit bootstrap. Read-only; writes data/_scratch_evalpower4.json.

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _frontier_evalpower as fp   # noqa: E402

WINDOWS = {"W4_2020_2023": tuple(range(2020, 2024)),
           "W5_2020_2024": tuple(range(2020, 2025)),
           "W6_2019_2024": tuple(range(2019, 2025)),
           "W7_2018_2024": tuple(range(2018, 2025)),
           "W9_2016_2024": tuple(range(2016, 2025))}
METRICS = ("block_rho", "cauc")
ARMS = ("base", "prod_trend", "drop_peakk", "noise")


def score_all(pool, arm):
    return {s: fp.score_records(pool[s], s, fp.ARMS[arm][s], fp.ORIGINS_ALL,
                                "fullpool", "debuted") for s in ("hit", "pit")}


def evaluate(rec):
    out = {}
    for wn, yrs in WINDOWS.items():
        sub = [r for s in ("hit", "pit") for r in rec[s] if r[1] in yrs]
        for mk in METRICS:
            out[f"{wn}|{mk}"] = fp.metric(sub, mk)
    return out


def main(B=250):
    t0 = time.time()
    pool = fp.load_pool()
    point = {a: evaluate(score_all(pool, a)) for a in ARMS}
    ns = {}
    rec = score_all(pool, "base")
    for wn, yrs in WINDOWS.items():
        ns[wn] = len([r for s in ("hit", "pit") for r in rec[s] if r[1] in yrs])
    print("n per window:", ns, flush=True)

    # injection slope at eps=0.10 (linear region) for the common effect axis
    inj = {}
    for wn, yrs in WINDOWS.items():
        sub = [r for s in ("hit", "pit") for r in rec[s] if r[1] in yrs]
        import _frontier_evalpower3 as fp3
        pert = fp3.inject_block(sub, 0.10)
        for mk in METRICS:
            inj[f"{wn}|{mk}"] = (fp.metric(pert, mk) - fp.metric(sub, mk)) / 0.10
    print("slopes:", {k: round(v, 3) for k, v in inj.items()}, flush=True)

    keys = list(point["base"])
    boot = {a: {k: [] for k in keys} for a in ARMS}
    rng = random.Random(31337)
    for b in range(B):
        rp = fp.resample(pool, rng, "strat")
        for a in ARMS:
            r = evaluate(score_all(rp, a))
            for k in keys:
                boot[a][k].append(r[k])
        if (b + 1) % 25 == 0:
            print(f"[{time.time()-t0:.0f}s] {b+1}/{B}", flush=True)

    out = {"n": ns, "point": point, "slopes": inj, "B": B, "summary": {}}
    for a in ("prod_trend", "drop_peakk", "noise"):
        print(f"\n### candidate = {a} (production fit config: train full pool, test debuted)")
        print(f"{'window|metric':24s} {'n':>5s} {'delta':>9s} {'sd':>8s} {'MDE':>8s} "
              f"{'slope':>7s} {'MDE_eps':>8s} {'|d|/sd':>7s}")
        for k in keys:
            d = np.array([c - bb for c, bb in zip(boot[a][k], boot["base"][k])
                          if c is not None and bb is not None])
            sd = float(d.std(ddof=1))
            dl = point[a][k] - point["base"][k]
            mde = 2.49 * sd
            me = mde / inj[k] if inj[k] else None
            print(f"{k:24s} {ns[k.split('|')[0]]:>5d} {dl:>9.5f} {sd:>8.5f} {mde:>8.4f} "
                  f"{inj[k]:>7.3f} {me:>8.4f} {abs(dl)/sd if sd else 0:>7.2f}")
            out["summary"].setdefault(a, {})[k] = {
                "delta": round(dl, 5), "sd": round(sd, 5), "mde": round(mde, 5),
                "mde_eps": round(me, 5), "ci95": [round(float(np.percentile(d, 2.5)), 5),
                                                  round(float(np.percentile(d, 97.5)), 5)],
                "p_gt0": round(float((d > 0).mean()), 3)}
    (ROOT / "tools" / "_frontier_out" / "_scratch_evalpower4.json").write_text(json.dumps(out, indent=1),
                                                           encoding="utf-8")
    print(f"\ndone [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(B=int(sys.argv[1]) if len(sys.argv) > 1 else 250)
