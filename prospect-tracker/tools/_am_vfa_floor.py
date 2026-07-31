# ADVERSARIAL VERIFICATION of the `fa` lane. Does the 0.4459 MDE95 TRANSFER?
"""Arm-SPECIFIC paired-bootstrap floors on the pinned Gate-2 chain.

The audited lane derived ONE floor (MDE95 0.4459 $M) from the paired bootstrap
of the RECALIBRATION arm, then applied it to structural arms (drop_rational,
no_rate_line, ridge_*) and to every registered fa_market claim. A paired
bootstrap CI is arm-specific: an arm that rescales EVERY prediction and an arm
that deletes one column of a 13-column OLS do not have the same sampling
variance for dMAE. This re-derives the CI per arm on the identical corpus and
the identical full-refit protocol.

Per draw: one oof_chain (champion, also the recalibration substrate) plus one
full chain per structural arm. Everything forward-chained inside each draw.
"""
from __future__ import annotations

import pickle
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa              # noqa: E402
import _am_fa_gate2 as g2  # noqa: E402
import _am_fa_recal as rc  # noqa: E402
import _am_fa_arms as arms  # noqa: E402  (installs the _features_guar patch)
import fa_market as fm     # noqa: E402

STRUCT = ["drop_rational", "no_rate_line", "ridge_0.5"]


def corpusB():
    with open(_am_fa.SCRATCH / "fa_enriched_signings_B.pkl", "rb") as fh:
        return pickle.load(fh)


def one_draw(draw):
    """Returns {arm: dMAE vs champion} on this draw, all refit."""
    fm.LAB_RESET()
    arms.DROP_RATIONAL = False
    oof = rc.oof_chain(draw)
    champ = rc.summarize(rc.score(oof, "off"), "off")
    out = {"_champ_mae": champ["mae"], "_champ_bias": champ["bias"], "_n": champ["n"]}
    for k in ("shift", "loglin"):
        s = rc.summarize(rc.score(oof, k), k)
        out[k] = s["mae"] - champ["mae"]
        out[k + "|bias|"] = abs(s["bias"]) - abs(champ["bias"])
    for a in STRUCT:
        p = arms.run(draw, a)
        out[a] = p["guarantee"]["mae_model"] - champ["mae"]
    fm.LAB_RESET()
    arms.DROP_RATIONAL = False
    return out


def report(acc, tag=""):
    print("\n  %s paired bootstrap, FULL refit per draw, B=%d" % (tag, len(acc["shift"])))
    for k in ["shift", "loglin", "shift|bias|", "loglin|bias|"] + STRUCT:
        v = sorted(x for x in acc[k] if x == x)
        if len(v) < 10:
            continue
        lo, hi = v[int(.025 * len(v))], v[int(.975 * len(v))]
        print("    %-16s d %+0.4f  CI95 [%+0.4f, %+0.4f]  halfwidth(MDE95) %0.4f  P(improves)=%.3f"
              % (k, sum(v) / len(v), lo, hi, (hi - lo) / 2,
                 sum(1 for x in v if x < 0) / len(v)))
    sys.stdout.flush()


if __name__ == "__main__":
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    c = corpusB()
    print("corpus n=%d hash=%s" % (len(c), g2.corpus_hash(c)))
    pt = one_draw(c)
    print("POINT (unresampled): champ MAE %.4f bias %+.4f n=%d"
          % (pt["_champ_mae"], pt["_champ_bias"], pt["_n"]))
    for k in ["shift", "loglin"] + STRUCT:
        print("   %-16s dMAE %+0.4f" % (k, pt[k]))
    sys.stdout.flush()

    keys = ["shift", "loglin", "shift|bias|", "loglin|bias|"] + STRUCT
    acc = {k: [] for k in keys}
    rng = random.Random(20260725)
    t0 = time.time()
    for i in range(B):
        draw = [c[rng.randrange(len(c))] for _ in range(len(c))]
        try:
            r = one_draw(draw)
            for k in keys:
                acc[k].append(r[k])
        except Exception as e:                     # noqa: BLE001
            print("   draw %d failed: %s" % (i, e))
        if (i + 1) % 20 == 0:
            print("  [%d/%d  %.0fs]" % (i + 1, B, time.time() - t0))
            report(acc, "interim")
    report(acc, "FINAL")
