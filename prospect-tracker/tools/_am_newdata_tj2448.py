"""LANE newdata (a), ACCURACY FOLLOW-UP to the SHIPPED P-TJPT arm.

fa_projection.P-TJPT ships ONE multiplier: PT_TJ_MULT = 0.606 for a surgery
inside 24 months. Its header says the all-bucket form measured a LARGER pooled
gain (-1.833 BF vs the coded arm's -1.663) but was not coded because permuting
five bucket labels admits far more null excursion than permuting one.

That reasoning is right about the CONTROL and leaves an accuracy increment
untested: the 24-48-month bucket's ex-ante multiplier is 1.0976, a ~10% exposure
BOOST (the recovery bounce), which the shipped arm forces to 1.0.

PRE-REGISTERED HYPOTHESIS
  H-TJ2  Adding a SECOND multiplier for the 24-48-month bucket, on top of the
         shipped lt24 arm, reduces pooled playing-time MAE further.

CONTROL MATCHED TO THE ARM (the correction the shipped header itself insists on):
the zero-information twin permutes exactly the label set the candidate arm reads
-- three levels {tj_lt24, tj_24_48, other} -- within season, never the five-level
label. Baseline for every comparison is the SHIPPED arm, not the no-arm engine.

PASS CRITERIA (set before running)
  (1) pooled MAE lower than the SHIPPED arm on >= 7 of the 12 forward folds,
  (2) delta outside the matched zero-information band (60 draws),
  (3) paired bootstrap CI95 excluding 0, refit each draw.
"""
import sys, os, random, statistics
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fa_tj_pt as src
import _fa_tj_gate as gate

FOLDS = gate.FOLDS
SHRINK = gate.SHRINK
SHIPPED_MULT = 0.606          # fa_projection.PT_TJ_MULT


def lab3(r):
    """The three-level label the candidate arm reads."""
    if not r["tj_pre"]:
        return "other"
    mo = r["tj_mo"]
    if mo is None:
        return "other"
    if mo < 24:
        return "tj_lt24"
    if mo < 48:
        return "tj_24_48"
    return "other"


def fit(train, levels):
    """Exposure ratio per level relative to `other`, shrunk toward 1.0."""
    agg = defaultdict(lambda: [0.0, 0.0])
    for r in train:
        a = agg[r["_l"]]
        a[0] += r["bf"]
        a[1] += r["pt_proj"]
    if agg["other"][1] <= 0:
        return {}
    b0 = agg["other"][0] / agg["other"][1]
    out = {"other": 1.0}
    n_by = Counter(r["_l"] for r in train)
    for lv in levels:
        num, den = agg.get(lv, [0.0, 0.0])
        if den <= 0:
            continue
        out[lv] = (n_by[lv] * ((num / den) / b0) + SHRINK) / (n_by[lv] + SHRINK)
    return out


def chain(rows, arm, permute_seed=None):
    """arm: 'none' | 'shipped' | 'fit_lt24' | 'two_bucket'."""
    rows = [dict(r) for r in rows]
    if permute_seed is not None:
        rng = random.Random(permute_seed)
        by = defaultdict(list)
        for r in rows:
            by[r["season"]].append(r)
        for s, rs in by.items():
            labs = [r["_l0"] for r in rs]
            rng.shuffle(labs)
            for r, l in zip(rs, labs):
                r["_l"] = l
    else:
        for r in rows:
            r["_l"] = r["_l0"]
    err, per = [], []
    for T in FOLDS:
        tr = [r for r in rows if r["season"] < T]
        te = [r for r in rows if r["season"] == T]
        if len(tr) < 300 or not te:
            continue
        if arm == "none":
            m = {}
        elif arm == "shipped":
            m = {"tj_lt24": SHIPPED_MULT}
        elif arm == "fit_lt24":
            m = fit(tr, ["tj_lt24"])
        else:
            m = fit(tr, ["tj_lt24", "tj_24_48"])
        e = [abs(r["pt_proj"] * m.get(r["_l"], 1.0) - r["bf"]) for r in te]
        err += e
        per.append((T, len(te), statistics.mean(e)))
    return statistics.mean(err), per, len(err)


def main():
    rows = src.load()
    for r in rows:
        r["_l0"] = lab3(r)
    print("three-level label counts", dict(Counter(r["_l0"] for r in rows)))

    res = {}
    for arm in ("none", "shipped", "fit_lt24", "two_bucket"):
        mae, per, n = chain(rows, arm)
        res[arm] = (mae, dict((T, x) for T, _, x in per), n, per)
        print(f"  arm {arm:<11} pooled PT MAE {mae:8.4f}  n={n}")

    for r in rows:
        r["_l"] = r["_l0"]
    print("\nfull-pool ex-ante multipliers (what would ship):",
          {k: round(v, 4) for k, v in fit(rows, ["tj_lt24", "tj_24_48"]).items()})

    ship = res["shipped"][0]
    print(f"\n=== candidate TWO-BUCKET vs the SHIPPED arm (baseline MAE {ship:.4f}) ===")
    d = res["two_bucket"][0] - ship
    sp = res["shipped"][1]
    imp = sum(1 for T, _, x in res["two_bucket"][3] if x < sp[T])
    print(f"  delta {d:+.5f}   folds improved {imp}/{len(res['two_bucket'][3])}")
    print(f"  {'fold':>6}{'shipped':>11}{'two-bucket':>13}{'delta':>10}")
    for T, _, x in res["two_bucket"][3]:
        print(f"  {T:>6}{sp[T]:>11.3f}{x:>13.3f}{x-sp[T]:>+10.3f}")

    print("\n  MATCHED zero-information control (three-level label permuted "
          "within season, 60 draws, refit each)")
    nul = sorted(chain(rows, "two_bucket", permute_seed=s)[0] - ship
                 for s in range(1, 61))
    print(f"    null mean {statistics.mean(nul):+.4f} sd {statistics.pstdev(nul):.4f}"
          f"  null95 [{nul[1]:+.4f},{nul[-2]:+.4f}]  max|d| {max(abs(x) for x in nul):.4f}")
    print(f"    observed {d:+.4f} -> outside band: "
          f"{d < 0 and abs(d) > max(abs(x) for x in nul)}"
          f"   SNR {abs(d)/max(abs(x) for x in nul):.2f}x")

    print("\n  paired bootstrap (resample by season, refit the candidate each draw)")
    rng = random.Random(41)
    by = defaultdict(list)
    for r in rows:
        by[r["season"]].append(r)
    ds, dn = [], []
    for _ in range(400):
        draw = []
        for s, rs in by.items():
            k = len(rs)
            draw += [rs[rng.randrange(k)] for _ in range(k)]
        a = chain(draw, "shipped")[0]
        b = chain(draw, "two_bucket")[0]
        c = chain(draw, "none")[0]
        ds.append(b - a)
        dn.append(a - c)
    for nm, dd in (("two_bucket - shipped", ds), ("shipped - no arm", dn)):
        dd = sorted(dd)
        print(f"    {nm:<22} {statistics.mean(dd):+.4f} sd {statistics.pstdev(dd):.4f}"
              f" CI95 [{dd[int(.025*len(dd))]:+.4f},{dd[int(.975*len(dd))]:+.4f}]"
              f" P(improves) {sum(1 for x in dd if x<0)/len(dd):.3f}")

    print("\n  SANITY: is the shipped constant 0.606 the right level? "
          "(ex-ante refit of lt24 alone)")
    d2 = res["fit_lt24"][0] - ship
    print(f"    fit_lt24 pooled MAE {res['fit_lt24'][0]:.4f} vs shipped "
          f"{ship:.4f}  delta {d2:+.5f}")


if __name__ == "__main__":
    main()
