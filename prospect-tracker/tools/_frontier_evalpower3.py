# SCRATCH part 3: EMPIRICAL power curve / minimum detectable effect, current gate vs recommended.
# For each candidate effect size eps (fraction of the way from the model's ranking to truth),
# run a paired refit bootstrap: resample the pool (cluster = decision-year cohort), refit the
# whole forward chain, score, then move the CANDIDATE arm's ranks eps toward truth inside each
# block. P(delta>0) across replicates = the gate's power at that effect size.
# Read-only; writes data/_scratch_evalpower3.json.

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _frontier_evalpower as fp   # noqa: E402

EPS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.08)
# (name, sides, origins, train_frame, test_frame, metric)
GATES = {
    "EV0_current_gate":  (("hit",), fp.ORIGINS_GATE, "debuted", "debuted", "pooled_rho"),
    "REC_blockrho":      (("hit", "pit"), fp.ORIGINS_ALL, "fullpool", "debuted", "block_rho"),
    "REC_cauc":          (("hit", "pit"), fp.ORIGINS_ALL, "fullpool", "debuted", "cauc"),
    "EV5_deb_blockrho":  (("hit", "pit"), fp.ORIGINS_ALL, "debuted", "debuted", "block_rho"),
}


def inject_block(recs, eps):
    """Move each block's predicted ranks eps toward the truth ranks, preserving the block's
    prediction marginal exactly (rank-remap). eps=0 is the identity."""
    if eps <= 0:
        return recs
    out = []
    for (s, y), g in fp._blocks(recs).items():
        p = np.array([x[0] for x in g], float)
        t = np.array([x[1] for x in g], float)
        fv = [x[2] for x in g]
        if len(g) < 3:
            out.extend((s, y, x[0], x[1], x[2]) for x in g)
            continue
        mix = (1 - eps) * fp._pct(p) + eps * fp._pct(t)
        srt = np.sort(p)
        pos = np.clip(mix * (len(p) - 1), 0, len(p) - 1)
        lo = np.floor(pos).astype(int)
        hi = np.minimum(len(p) - 1, lo + 1)
        newp = srt[lo] * (1 - (pos - lo)) + srt[hi] * (pos - lo)
        out.extend((s, y, float(newp[i]), float(t[i]), fv[i]) for i in range(len(g)))
    return out


def run_gate(pool, gname):
    sides, origins, tf, sfr, mk = GATES[gname]
    recs = []
    for side in sides:
        recs.extend(fp.score_records(pool[side], side, fp.BASE_KEYS[side],
                                     origins, tf, sfr))
    return recs, mk


def main(B=250):
    t0 = time.time()
    pool = fp.load_pool()
    out = {"B": B, "eps": list(EPS), "power": {}, "sd": {}}
    for gname in GATES:
        rng = random.Random(777)
        deltas = {e: [] for e in EPS}
        for b in range(B):
            rp = fp.resample(pool, rng, "strat")
            recs, mk = run_gate(rp, gname)
            m0 = fp.metric(recs, mk)
            if m0 is None:
                continue
            for e in EPS:
                m1 = fp.metric(inject_block(recs, e), mk)
                if m1 is not None:
                    deltas[e].append(m1 - m0)
            if (b + 1) % 50 == 0:
                print(f"[{time.time()-t0:.0f}s] {gname} {b+1}/{B}", flush=True)
        print(f"\n== {gname} ==")
        print(f"{'eps':>7s} {'mean_d':>9s} {'sd_d':>9s} {'t=d/sd':>8s} {'power95':>8s} {'P(d>0)':>8s}")
        for e in EPS:
            d = np.array(deltas[e])
            p = float((d > 0).mean())
            sd = float(d.std(ddof=1))
            t = float(d.mean()) / sd if sd else 0.0
            # power of a one-sided 95% bootstrap gate at this true effect size
            pw = 0.5 * (1 + math.erf((t - 1.645) / math.sqrt(2)))
            print(f"{e:>7.3f} {d.mean():>9.5f} {sd:>9.5f} {t:>8.2f} {pw:>8.3f} {p:>8.3f}")
            out["power"].setdefault(gname, {})[str(e)] = {
                "mean_delta": round(float(d.mean()), 5), "sd": round(sd, 5),
                "t": round(t, 3), "power_95": round(float(pw), 3),
                "boot_p_gt0": round(p, 3)}
    (ROOT / "tools" / "_frontier_out" / "_scratch_evalpower3.json").write_text(json.dumps(out, indent=1),
                                                           encoding="utf-8")
    print(f"\ndone [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(B=int(sys.argv[1]) if len(sys.argv) > 1 else 250)
