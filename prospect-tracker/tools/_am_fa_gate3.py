# AUDIT LANE `fa`. Gate-3 re-derivation + the floor the registered gate never had.
"""Gate 3 (team fit) scored under a CLUSTER bootstrap over signings.

The registered artifact compares weight mixes on point MRR alone
(shipped_balanced 0.167 vs fitted_logistic 0.165) and calls the difference
"within noise" without ever measuring the noise. This lab measures it, and
separately checks whether the vector the gate scores as `live_analog` is the
vector that actually ships.
"""
from __future__ import annotations

import json
import pickle
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa  # noqa: E402

FEATS = ("need", "window", "afford", "park", "behavior")


def rows():
    def build():
        import fa_fit_backtest as fbt
        return fbt.build_rows()
    return _am_fa.cached("fa_gate3_rows", build)


def groups_by_winter(rs):
    g = defaultdict(list)
    for r in rs:
        g[(r["winter"], r["signing"])].append(r)
    return g


def metrics(groups, score):
    """top1/3/5 + MRR over an iterable of candidate-club groups."""
    n = 0
    hits = {1: 0, 3: 0, 5: 0}
    rr = 0.0
    for group in groups:
        if not any(r["signed"] for r in group):
            continue
        n += 1
        ordered = sorted(group, key=lambda r: -score(r))
        rank = next(i for i, r in enumerate(ordered, 1) if r["signed"])
        rr += 1.0 / rank
        for k in hits:
            if rank <= k:
                hits[k] += 1
    if not n:
        return None
    return {"n": n, "top1": hits[1] / n, "top3": hits[3] / n,
            "top5": hits[5] / n, "mrr": rr / n}


def wvec(w):
    return lambda r: sum(w[f] * r[f] for f in FEATS)


def cluster_bootstrap(groups, scorers, B=2000, seed=20260725):
    """Resample SIGNINGS with replacement (the independent unit is the
    signing, not the club-row) and recompute every scorer on the same draw,
    so the gaps are paired."""
    rng = random.Random(seed)
    gl = list(groups)
    out = {k: [] for k in scorers}
    for _ in range(B):
        draw = [gl[rng.randrange(len(gl))] for _ in range(len(gl))]
        for k, fn in scorers.items():
            m = metrics(draw, fn)
            out[k].append(m["mrr"] if m else float("nan"))
    return out


def ci(vals, lo=2.5, hi=97.5):
    v = sorted(vals)
    n = len(v)
    return v[int(lo / 100 * n)], v[int(hi / 100 * n)]


if __name__ == "__main__":
    import fa_class
    import fa_fit_backtest as fbt

    rs = rows()
    g = groups_by_winter(rs)
    gl = list(g.values())
    cfgw = (fa_class.get_config().get("fit") or {})["weights"]
    print("shipped fa_config fit.weights :", cfgw)
    print("fa_fit_backtest.LIVE_WEIGHTS  :", fbt.LIVE_WEIGHTS)
    print("identical                     :", cfgw == fbt.LIVE_WEIGHTS)
    print()

    scorers = {
        "live_analog(LIVE_WEIGHTS=hand_v2)": wvec(fbt.LIVE_WEIGHTS),
        "shipped_config_weights": wvec(cfgw),
        "behavior_only": lambda r: r["behavior"],
        "payroll_only": lambda r: r["afford"],
    }
    print("%-36s %5s %7s %7s %7s %7s" % ("arm", "n", "top1", "top3", "top5", "mrr"))
    base = {}
    for k, fn in scorers.items():
        m = metrics(gl, fn)
        base[k] = m
        print("%-36s %5d %7.4f %7.4f %7.4f %7.4f"
              % (k, m["n"], m["top1"], m["top3"], m["top5"], m["mrr"]))
    print()

    B = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    bs = cluster_bootstrap(gl, scorers, B=B)
    print("cluster bootstrap over signings, B=%d" % B)
    ship = "shipped_config_weights"
    for k in scorers:
        if k == ship:
            continue
        d = [a - b for a, b in zip(bs[ship], bs[k])]
        lo, hi = ci(d)
        print("  MRR gap  %-34s %+0.4f  CI95 [%+0.4f, %+0.4f]  P(shipped better)=%.3f"
              % ("shipped - " + k, base[ship]["mrr"] - base[k]["mrr"], lo, hi,
                 sum(1 for x in d if x > 0) / len(d)))
    lo, hi = ci(bs[ship])
    print("  shipped MRR CI95 [%.4f, %.4f]  half-width %.4f  => MDE95 ~ %.4f"
          % (lo, hi, (hi - lo) / 2, (hi - lo) / 2))

    # zero-information control: permute the `signed` label WITHIN each signing
    rng = random.Random(7)
    perm = []
    for grp in gl:
        idx = list(range(len(grp)))
        rng.shuffle(idx)
        signed_at = next((i for i, r in enumerate(grp) if r["signed"]), None)
        if signed_at is None:
            perm.append(grp)
            continue
        newgrp = [{**r, "signed": 0} for r in grp]
        newgrp[idx[0]] = {**newgrp[idx[0]], "signed": 1}
        perm.append(newgrp)
    pm = metrics(perm, wvec(cfgw))
    print("  PERMUTATION NULL (signed label shuffled within signing): MRR %.4f (n=%d)"
          % (pm["mrr"], pm["n"]))

    # per-winter (independent time splits)
    print("\n  per-winter MRR (independent splits)")
    byw = defaultdict(list)
    for (w, _s), grp in g.items():
        byw[w].append(grp)
    for w in sorted(byw):
        a = metrics(byw[w], wvec(cfgw))
        b = metrics(byw[w], wvec(fbt.LIVE_WEIGHTS))
        c = metrics(byw[w], lambda r: r["behavior"])
        if a:
            print("    %d n=%3d shipped %.4f | hand_v2 %.4f | behavior %.4f"
                  % (w, a["n"], a["mrr"], b["mrr"], c["mrr"]))
