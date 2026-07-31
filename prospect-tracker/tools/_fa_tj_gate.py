"""Gate for the TJ playing-time arm, to docs/EFV_GATE_STANDARD.md.

Baseline  : fa_projection's shipped pt_proj (BF).
Candidate : pt_proj x m(bucket), m fit EX-ANTE on strictly prior seasons.
Metric    : playing-time MAE in BF, pooled and on the TJ slice.
Controls  : (1) paired bootstrap resampling the whole pool with a refit of
            the multipliers on every draw; (2) a zero-information control
            (TJ bucket labels row-permuted, identical marginal);
            (3) a permutation null band; (4) 12 forward-chained seasons.
"""
import sys, os, math, random, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fa_tj_pt as src

FOLDS = list(range(2014, 2026))
SHRINK = 30.0          # pseudo-rows toward the no-TJ level


def bucket(r):
    if not r["tj_pre"]:
        return "none"
    mo = r["tj_mo"]
    if mo is None:
        return "tj_unk"
    if mo < 24:
        return "tj_lt24"
    if mo < 48:
        return "tj_24_48"
    if mo < 96:
        return "tj_48_96"
    return "tj_96p"


def fit_mult(train):
    """Bucket multiplier relative to the no-TJ bucket, exposure-weighted and
    shrunk toward 1.0. Pure ratio of realized to projected BF."""
    agg = {}
    for r in train:
        b = r["_b"]
        a = agg.setdefault(b, [0.0, 0.0])
        a[0] += r["bf"]
        a[1] += r["pt_proj"]
    base = agg.get("none")
    if not base or base[1] <= 0:
        return {}
    b0 = base[0] / base[1]
    out = {}
    for b, (num, den) in agg.items():
        if den <= 0:
            continue
        n = sum(1 for r in train if r["_b"] == b)
        raw = (num / den) / b0
        out[b] = (n * raw + SHRINK * 1.0) / (n + SHRINK)
    out["none"] = 1.0
    return out


def chain(rows, permute_seed=None):
    """Returns (pooled MAE base, pooled MAE cand, per-fold deltas, tj-slice)."""
    rows = list(rows)
    if permute_seed is not None:
        rng = random.Random(permute_seed)
        # permute the bucket label WITHIN season (identical marginal per fold)
        by = {}
        for r in rows:
            by.setdefault(r["season"], []).append(r)
        for s, rs in by.items():
            labs = [r["_b0"] for r in rs]
            rng.shuffle(labs)
            for r, l in zip(rs, labs):
                r["_b"] = l
    else:
        for r in rows:
            r["_b"] = r["_b0"]
    eb, ec, per = [], [], []
    tjb, tjc = [], []
    for T in FOLDS:
        tr = [r for r in rows if r["season"] < T]
        te = [r for r in rows if r["season"] == T]
        if len(tr) < 300 or not te:
            continue
        m = fit_mult(tr)
        fb = [abs(r["pt_proj"] - r["bf"]) for r in te]
        fc = [abs(r["pt_proj"] * m.get(r["_b"], 1.0) - r["bf"]) for r in te]
        eb += fb
        ec += fc
        tj = [i for i, r in enumerate(te) if r["_b"] != "none"]
        tjb += [fb[i] for i in tj]
        tjc += [fc[i] for i in tj]
        per.append((T, len(te), statistics.mean(fb), statistics.mean(fc)))
    return (statistics.mean(eb), statistics.mean(ec), per,
            statistics.mean(tjb), statistics.mean(tjc), len(eb), len(tjb))


def main():
    rows = src.load()
    for r in rows:
        r["_b0"] = bucket(r)
    from collections import Counter
    print("bucket counts", dict(Counter(r["_b0"] for r in rows)))

    b, c, per, tb, tc, n, ntj = chain(rows)
    print(f"\nPOINT ESTIMATE  n={n} (tj slice {ntj})")
    print(f"  pooled PT MAE (BF)  base {b:.3f}  cand {c:.3f}  delta {c-b:+.3f}")
    print(f"  TJ-slice PT MAE     base {tb:.3f}  cand {tc:.3f}  delta {tc-tb:+.3f}")
    print(f"\n{'fold':>6}{'n':>6}{'base':>10}{'cand':>10}{'delta':>9}")
    nneg = 0
    for T, k, x, y in per:
        nneg += (y < x)
        print(f"{T:>6}{k:>6}{x:>10.2f}{y:>10.2f}{y-x:>+9.2f}")
    print(f"  folds improved: {nneg}/{len(per)}")

    # multipliers fit on the full pool (what would ship)
    for r in rows:
        r["_b"] = r["_b0"]
    print("\n  full-pool multipliers:", {k: round(v, 4) for k, v in
                                         sorted(fit_mult(rows).items())})

    # ---- zero-information control + permutation null band
    print("\nZERO-INFORMATION CONTROL (bucket labels row-permuted within season)")
    ctl = [chain(rows, permute_seed=s) for s in range(1, 41)]
    d_pool = sorted(x[1] - x[0] for x in ctl)
    d_tj = sorted(x[4] - x[3] for x in ctl)
    print(f"  pooled delta: mean {statistics.mean(d_pool):+.4f} "
          f"sd {statistics.pstdev(d_pool):.4f}  "
          f"null95 band [{d_pool[1]:+.4f}, {d_pool[-2]:+.4f}]  "
          f"max|d| {max(abs(x) for x in d_pool):.4f}")
    print(f"  TJ-slice delta: mean {statistics.mean(d_tj):+.4f} "
          f"sd {statistics.pstdev(d_tj):.4f}  "
          f"null95 band [{d_tj[1]:+.4f}, {d_tj[-2]:+.4f}]  "
          f"max|d| {max(abs(x) for x in d_tj):.4f}")

    # ---- paired bootstrap (resample the whole pool, refit every draw)
    print("\nPAIRED BOOTSTRAP (resample pool stratified by season, refit each draw)")
    rng = random.Random(7)
    by = {}
    for r in rows:
        by.setdefault(r["season"], []).append(r)
    dp, dt = [], []
    for _ in range(400):
        draw = []
        for s, rs in by.items():
            k = len(rs)
            draw += [rs[rng.randrange(k)] for _ in range(k)]
        draw = [dict(r) for r in draw]
        x = chain(draw)
        dp.append(x[1] - x[0])
        dt.append(x[4] - x[3])
    for nm, d in (("pooled", dp), ("TJ slice", dt)):
        d = sorted(d)
        print(f"  {nm:<10} delta mean {statistics.mean(d):+.4f} sd {statistics.pstdev(d):.4f}"
              f"  CI95 [{d[int(.025*len(d))]:+.4f}, {d[int(.975*len(d))]:+.4f}]"
              f"  P(improves) {sum(1 for x in d if x<0)/len(d):.3f}")


if __name__ == "__main__":
    main()
