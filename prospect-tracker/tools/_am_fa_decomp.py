# AUDIT LANE `fa`. (b) WHERE THE GATE-2 ERROR ACTUALLY LIVES.
"""Decompose the pooled Gate-2 guarantee MAE into blocks that can be attacked.

The mandate says attack the LARGEST identified block, not the most
interesting one. So: measure total dollars of absolute error contributed by
each slice (share of pooled MAE), not just the per-row MAE of the slice --
a slice with a huge per-row MAE and 3 rows is not where the error lives.
"""
from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa            # noqa: E402
import _am_fa_gate2 as g2  # noqa: E402


def corpus(which="B"):
    if which == "B":
        with open(_am_fa.SCRATCH / "fa_enriched_signings_B.pkl", "rb") as fh:
            return pickle.load(fh)
    return _am_fa.signings()


def block(rows, keyfn, label, total_abs):
    agg = defaultdict(lambda: {"n": 0, "abs": 0.0, "signed": 0.0,
                               "absb": 0.0, "act": 0.0})
    for r in rows:
        k = keyfn(r)
        a = agg[k]
        a["n"] += 1
        a["abs"] += abs(r["pred_guar"] - r["act_guar"])
        a["signed"] += r["pred_guar"] - r["act_guar"]
        a["absb"] += abs(r["base_guar"] - r["act_guar"])
        a["act"] += r["act_guar"]
    print("\n== %s ==" % label)
    print("  %-16s %5s %9s %9s %9s %9s %9s" %
          ("slice", "n", "MAE", "baseMAE", "bias", "shareErr", "meanActual"))
    for k in sorted(agg, key=lambda x: -agg[x]["abs"]):
        a = agg[k]
        print("  %-16s %5d %9.2f %9.2f %+9.2f %8.1f%% %9.1f" %
              (str(k), a["n"], a["abs"] / a["n"], a["absb"] / a["n"],
               a["signed"] / a["n"], 100 * a["abs"] / total_abs,
               a["act"] / a["n"]))
    return agg


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "B"
    c = corpus(which)
    print("corpus %s n=%d hash=%s" % (which, len(c), g2.corpus_hash(c)))
    rows = g2.chain(c)["rows"]
    p = g2.pooled(rows)
    for k, v in p.items():
        print("  %-16s model %.4f  base %.4f  n=%d"
              % (k, v["mae_model"], v["mae_base"], v["n"]))
    total_abs = sum(abs(r["pred_guar"] - r["act_guar"]) for r in rows)
    print("\nTOTAL absolute guarantee error across the chain: $%.0fM over %d signings"
          % (total_abs, len(rows)))

    def sizebin(r):
        g = r["act_guar"]
        for lo, hi, nm in [(0, 5, "A <$5M"), (5, 20, "B $5-20M"),
                           (20, 50, "C $20-50M"), (50, 100, "D $50-100M"),
                           (100, 200, "E $100-200M"), (200, 1e9, "F >=$200M")]:
            if lo <= g < hi:
                return nm
        return "?"

    def agebin(r):
        a = r["age"] or 0
        if a < 27:
            return "a <27"
        if a < 30:
            return "b 27-29"
        if a < 33:
            return "c 30-32"
        if a < 36:
            return "d 33-35"
        return "e >=36"

    block(rows, sizebin, "BY DEAL SIZE (actual NPV guarantee)", total_abs)
    block(rows, lambda r: r["pos_group"], "BY POSITION GROUP", total_abs)
    block(rows, agebin, "BY SIGNING AGE", total_abs)
    block(rows, lambda r: r["winter"], "BY WINTER", total_abs)
    block(rows, lambda r: "QO" if r["qo"] else "no-QO", "BY QO STATUS", total_abs)

    # ---- YEARS vs AAV: exact additive decomposition of the guarantee error --
    # pred_guar and act_guar are both years x AAV, so the guarantee error
    # splits exactly into a term-length error, a rate error and an interaction.
    print("\n== YEARS vs AAV decomposition of the guarantee error ==")
    print("  identity check: max |pred_guar - pred_years*pred_aav| = %.4f $M"
          % max(abs(r["pred_guar"] - r["pred_years"] * r["pred_aav"]) for r in rows))
    ty = ta = ti = 0.0
    for r in rows:
        dy = r["pred_years"] - r["act_years"]
        da = r["pred_aav"] - r["act_aav"]
        ty += abs(r["act_aav"] * dy)
        ta += abs(r["act_years"] * da)
        ti += abs(dy * da)
    n = len(rows)
    print("  mean |AAV x dYears|      $%7.3fM   (term-length error priced at the true rate)" % (ty / n))
    print("  mean |Years x dAAV|      $%7.3fM   (rate error priced over the true term)" % (ta / n))
    print("  mean |dYears x dAAV|     $%7.3fM   (interaction)" % (ti / n))

    # where does the YEARS error live?
    print("\n== YEARS error by actual term ==")
    yagg = defaultdict(lambda: {"n": 0, "abs": 0.0, "signed": 0.0, "absb": 0.0})
    for r in rows:
        a = yagg[int(r["act_years"])]
        a["n"] += 1
        a["abs"] += abs(r["pred_years"] - r["act_years"])
        a["signed"] += r["pred_years"] - r["act_years"]
        a["absb"] += abs(r["base_years"] - r["act_years"])
    print("  %-8s %5s %8s %8s %8s" % ("actYrs", "n", "MAE", "bias", "baseMAE"))
    for k in sorted(yagg):
        a = yagg[k]
        print("  %-8d %5d %8.3f %+8.3f %8.3f"
              % (k, a["n"], a["abs"] / a["n"], a["signed"] / a["n"], a["absb"] / a["n"]))

    # AAV error by actual AAV
    print("\n== AAV error by actual AAV ==")
    aagg = defaultdict(lambda: {"n": 0, "abs": 0.0, "signed": 0.0, "absb": 0.0})

    def abin(r):
        v = r["act_aav"]
        for lo, hi, nm in [(0, 2, "A <$2M"), (2, 5, "B $2-5M"), (5, 10, "C $5-10M"),
                           (10, 20, "D $10-20M"), (20, 30, "E $20-30M"),
                           (30, 1e9, "F >=$30M")]:
            if lo <= v < hi:
                return nm
        return "?"
    for r in rows:
        a = aagg[abin(r)]
        a["n"] += 1
        a["abs"] += abs(r["pred_aav"] - r["act_aav"])
        a["signed"] += r["pred_aav"] - r["act_aav"]
        a["absb"] += abs(r["base_aav"] - r["act_aav"])
    print("  %-10s %5s %8s %8s %8s" % ("actAAV", "n", "MAE", "bias", "baseMAE"))
    for k in sorted(aagg):
        a = aagg[k]
        print("  %-10s %5d %8.3f %+8.3f %8.3f"
              % (k, a["n"], a["abs"] / a["n"], a["signed"] / a["n"], a["absb"] / a["n"]))
