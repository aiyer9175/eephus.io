# AUDIT LANE `fa`. (c)->(b) Does the measured redundancy cost accuracy?
"""Arms on the PINNED Gate-2 chain.

Motivated by tools/_am_fa_redun.py: the guarantee stage runs an UNREGULARIZED
OLS (RIDGE_GUAR = 0.0) on a design matrix with VIF 26.8 (w1), 23.4
(log_rational), 17.7 (w1*years), 13.7 (years), where log_rational is 95.3%
explained by the raw war-path columns sitting beside it. The module already
knows this hurts -- _ols's docstring says unregularized OLS "extrapolated
wildly at megadeal-extreme inputs" -- but the fix that shipped was a
comps-envelope CLAMP at predict time, which treats the symptom.

Arms (each a one-line change, all forward-chained on the identical folds):
  drop_rational   remove the 4.7%-unique column
  ridge_*         regularize instead of clamping
  no_rate_line    remove the feature the incumbent's own re-gate could not
                  distinguish from a noise column
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa            # noqa: E402
import _am_fa_gate2 as g2  # noqa: E402
import fa_market as fm   # noqa: E402

_ORIG_FEATURES_GUAR = fm._features_guar
DROP_RATIONAL = False
_RATIONAL_IDX = 9


def _patched(s, years, dpw_usd, supply, log_comps_guar, log_rational, prime_war):
    v = _ORIG_FEATURES_GUAR(s, years, dpw_usd, supply, log_comps_guar,
                            log_rational, prime_war)
    if DROP_RATIONAL:
        v = v[:_RATIONAL_IDX] + v[_RATIONAL_IDX + 1:]
    return v


fm._features_guar = _patched


def corpusB():
    with open(_am_fa.SCRATCH / "fa_enriched_signings_B.pkl", "rb") as fh:
        return pickle.load(fh)


def set_arm(name):
    global DROP_RATIONAL
    fm.LAB_RESET()
    DROP_RATIONAL = False
    if name == "champion":
        pass
    elif name == "drop_rational":
        DROP_RATIONAL = True
    elif name.startswith("ridge_"):
        fm.RIDGE_GUAR = float(name.split("_")[1])
    elif name == "no_rate_line":
        fm.X_FEATURES["rate_line"] = False
    elif name == "drop_rational+ridge_3":
        DROP_RATIONAL = True
        fm.RIDGE_GUAR = 3.0
    else:
        raise ValueError(name)


ARMS = ["champion", "drop_rational", "ridge_0.5", "ridge_1", "ridge_3",
        "ridge_10", "no_rate_line", "drop_rational+ridge_3"]


def run(corpus, arm):
    set_arm(arm)
    try:
        rows = g2.chain(corpus)["rows"]
        return g2.pooled(rows)
    finally:
        fm.LAB_RESET()


if __name__ == "__main__":
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    c = corpusB()
    print("pinned corpus n=%d hash=%s" % (len(c), g2.corpus_hash(c)))
    print("\n%-24s %9s %9s %9s %10s" % ("arm", "guar", "aav", "years", "mega"))
    base = None
    pts = {}
    for a in ARMS:
        p = run(c, a)
        pts[a] = p
        if a == "champion":
            base = p
        print("%-24s %9.4f %9.4f %9.4f %10.3f%s"
              % (a, p["guarantee"]["mae_model"], p["aav"]["mae_model"],
                 p["years"]["mae_model"], p["mega_guarantee"]["mae_model"],
                 "" if a == "champion" else "   (dguar %+.4f)"
                 % (p["guarantee"]["mae_model"] - base["guarantee"]["mae_model"])))

    if B:
        cand = [a for a in ARMS if a != "champion"]
        print("\npaired bootstrap, FULL forward chain refit per draw, B=%d" % B)
        rng = random.Random(20260725)
        acc = {a: [] for a in cand}
        for i in range(B):
            draw = [c[rng.randrange(len(c))] for _ in range(len(c))]
            try:
                bp = run(draw, "champion")["guarantee"]["mae_model"]
                for a in cand:
                    acc[a].append(run(draw, a)["guarantee"]["mae_model"] - bp)
            except Exception as e:                       # noqa: BLE001
                print("   draw %d failed: %s" % (i, e))
        for a in cand:
            v = sorted(x for x in acc[a] if x == x)
            if not v:
                continue
            print("   %-24s dGuarMAE %+0.4f  CI95 [%+0.4f, %+0.4f]  P(improves)=%.3f  MDE95 %.4f"
                  % (a, sum(v) / len(v), v[int(.025 * len(v))], v[int(.975 * len(v))],
                     sum(1 for x in v if x < 0) / len(v),
                     (v[int(.975 * len(v))] - v[int(.025 * len(v))]) / 2))
