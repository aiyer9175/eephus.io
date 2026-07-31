"""LANE newdata (a) REDUNDANCY + INCREMENT check for the TJ playing-time arm.

PRE-REGISTERED QUESTIONS
  Q1 How collinear is the TJ bucket with the IL-history features the (inert,
     default-OFF) W1 PT-RISK arm uses? If TJ is just "recently on the IL",
     it is a duplicate signal under a second name.
  Q2 Does the TJ multiplier still improve playing-time MAE when the baseline
     ALREADY carries an IL-days-based multiplier fit the same way? i.e. is the
     TJ increment over IL real, or does IL subsume it?
  Q3 Direction sanity: is the fitted tj_lt24 multiplier < 1 (a penalty)? A
     survivorship-contaminated join would make surgery look protective (>1).

CRITERIA SET BEFORE RUNNING
  - Q1 fails as "redundant" if |Cramer's V| between tj bucket and an IL-days
    tercile exceeds 0.5, or if the tj bucket becomes insignificant once
    IL-days enters.
  - Q2 ships only if the TJ-on-top-of-IL pooled delta stays outside the
    zero-information permutation band (same construction as _fa_tj_gate).
"""
import sys, os, math, random, statistics
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import _fa_tj_pt as src
import _fa_tj_gate as gate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IL = json.load(open(os.path.join(ROOT, ".cache", "mlb_transactions",
                                 "il_table.json")))["il"]
FOLDS = gate.FOLDS
SHRINK = gate.SHRINK


def il_prior(mlbam, season):
    """(il_days in season-1, career il_days strictly before season)."""
    y = IL.get(str(mlbam)) or {}
    d1 = float((y.get(str(season - 1)) or [0.0, 0])[0])
    car = sum(float(v[0]) for s, v in y.items() if int(s) < season)
    return d1, car


def il_bucket(r):
    d1 = r["il_d1"]
    if d1 <= 0:
        return "il_none"
    if d1 < 30:
        return "il_lt30"
    if d1 < 90:
        return "il_30_90"
    return "il_90p"


def cramers_v(pairs):
    rows = sorted({a for a, _ in pairs})
    cols = sorted({b for _, b in pairs})
    n = len(pairs)
    obs = Counter(pairs)
    ra = Counter(a for a, _ in pairs)
    rb = Counter(b for _, b in pairs)
    chi = 0.0
    for a in rows:
        for b in cols:
            e = ra[a] * rb[b] / n
            if e > 0:
                chi += (obs[(a, b)] - e) ** 2 / e
    k = min(len(rows), len(cols))
    return math.sqrt(chi / (n * (k - 1))) if k > 1 and n else 0.0


def fit_mult_key(train, key):
    agg = {}
    for r in train:
        a = agg.setdefault(r[key], [0.0, 0.0])
        a[0] += r["bf"]
        a[1] += r["pt_proj"]
    base = agg.get("none") or agg.get("il_none")
    if not base or base[1] <= 0:
        return {}
    b0 = base[0] / base[1]
    out = {}
    for b, (num, den) in agg.items():
        if den <= 0:
            continue
        n = sum(1 for r in train if r[key] == b)
        out[b] = (n * ((num / den) / b0) + SHRINK) / (n + SHRINK)
    return out


def chain2(rows, use_il, use_tj, permute_tj=None):
    """Forward-chained MAE with an IL multiplier and/or a TJ multiplier.
    The TJ multiplier is fit on the IL-ADJUSTED residual exposure so it can
    only earn credit IL has not already taken."""
    rows = [dict(r) for r in rows]
    if permute_tj is not None:
        rng = random.Random(permute_tj)
        by = defaultdict(list)
        for r in rows:
            by[r["season"]].append(r)
        for s, rs in by.items():
            labs = [r["_tj"] for r in rs]
            rng.shuffle(labs)
            for r, l in zip(rs, labs):
                r["_tj"] = l
    err, per, tjerr = [], [], []
    for T in FOLDS:
        tr = [r for r in rows if r["season"] < T]
        te = [r for r in rows if r["season"] == T]
        if len(tr) < 300 or not te:
            continue
        mi = fit_mult_key(tr, "_il") if use_il else {}
        # residualize train exposure by the IL multiplier before fitting TJ
        for r in tr:
            r["pt_res"] = r["pt_proj"] * (mi.get(r["_il"], 1.0) if use_il else 1.0)
        if use_tj:
            agg = {}
            for r in tr:
                a = agg.setdefault(r["_tj"], [0.0, 0.0])
                a[0] += r["bf"]
                a[1] += r["pt_res"]
            b0 = agg["none"][0] / agg["none"][1]
            mt = {}
            for b, (num, den) in agg.items():
                if den <= 0:
                    continue
                n = sum(1 for r in tr if r["_tj"] == b)
                mt[b] = (n * ((num / den) / b0) + SHRINK) / (n + SHRINK)
            mt["none"] = 1.0
        else:
            mt = {}
        fe = []
        for r in te:
            p = r["pt_proj"]
            if use_il:
                p *= mi.get(r["_il"], 1.0)
            if use_tj:
                p *= mt.get(r["_tj"], 1.0)
            fe.append(abs(p - r["bf"]))
        for i, r in enumerate(te):
            if r["_tj"] != "none":
                tjerr.append(fe[i])
        err += fe
        per.append((T, len(te), statistics.mean(fe)))
    return statistics.mean(err), per, statistics.mean(tjerr), len(err)


def main():
    rows = src.load()
    for r in rows:
        r["_tj"] = gate.bucket(r)
        d1, car = il_prior(r["mlbam"], r["season"])
        r["il_d1"], r["il_car"] = d1, car
        r["_il"] = il_bucket(r)

    print("=== Q1 REDUNDANCY: TJ bucket vs IL bucket ===")
    print("  tj counts", dict(Counter(r["_tj"] for r in rows)))
    print("  il counts", dict(Counter(r["_il"] for r in rows)))
    v = cramers_v([(r["_tj"], r["_il"]) for r in rows])
    print(f"  Cramer's V (tj bucket x il bucket) = {v:.4f}")
    # point-biserial: tj_pre flag vs prior-season IL days / career IL days
    def pb(flagkey, numkey):
        a = [r[numkey] for r in rows if r[flagkey]]
        b = [r[numkey] for r in rows if not r[flagkey]]
        mu = statistics.mean([r[numkey] for r in rows])
        sd = statistics.pstdev([r[numkey] for r in rows]) or 1.0
        n1, n0, n = len(a), len(b), len(rows)
        return ((statistics.mean(a) - statistics.mean(b)) / sd
                * math.sqrt(n1 * n0 / (n * n)))
    print(f"  r_pb(tj_pre, il_days_prior1)  = {pb('tj_pre','il_d1'):+.4f}")
    print(f"  r_pb(tj_pre, career_il_days)  = {pb('tj_pre','il_car'):+.4f}")
    print(f"  mean il_d1  tj_pre=1 {statistics.mean([r['il_d1'] for r in rows if r['tj_pre']]):.1f}"
          f"  tj_pre=0 {statistics.mean([r['il_d1'] for r in rows if not r['tj_pre']]):.1f}")
    # within the recent-TJ bucket specifically
    for b in ("tj_lt24", "tj_24_48", "tj_48_96", "tj_96p"):
        s = [r for r in rows if r["_tj"] == b]
        if s:
            print(f"    {b:<9} n={len(s):>5} mean il_d1 {statistics.mean([r['il_d1'] for r in s]):6.1f}"
                  f"  share il_none {sum(1 for r in s if r['_il']=='il_none')/len(s):.3f}")

    print("\n=== Q2 INCREMENT: does TJ add on top of an IL multiplier? ===")
    combos = [("base (shipped pt_proj)", False, False),
              ("IL only", True, False),
              ("TJ only", False, True),
              ("IL + TJ (TJ fit on IL residual)", True, True)]
    res = {}
    for nm, ui, ut in combos:
        m, per, tj, n = chain2(rows, ui, ut)
        res[nm] = (m, tj, n)
        print(f"  {nm:<34} pooled MAE {m:8.3f}   TJ-slice {tj:8.3f}   n={n}")
    d_inc = res["IL + TJ (TJ fit on IL residual)"][0] - res["IL only"][0]
    d_inc_tj = res["IL + TJ (TJ fit on IL residual)"][1] - res["IL only"][1]
    print(f"  INCREMENT of TJ over IL: pooled {d_inc:+.4f}  TJ-slice {d_inc_tj:+.4f}")

    print("\n  zero-information control (TJ labels row-permuted within season,"
          " IL arm left intact, 40 draws)")
    ctl = [chain2(rows, True, True, permute_tj=s) for s in range(1, 41)]
    base_il = res["IL only"][0]
    base_il_tj = res["IL only"][1]
    dp = sorted(x[0] - base_il for x in ctl)
    dt = sorted(x[2] - base_il_tj for x in ctl)
    print(f"    pooled   null mean {statistics.mean(dp):+.4f} sd {statistics.pstdev(dp):.4f}"
          f" null95 [{dp[1]:+.4f},{dp[-2]:+.4f}] max|d| {max(abs(x) for x in dp):.4f}")
    print(f"    TJ-slice null mean {statistics.mean(dt):+.4f} sd {statistics.pstdev(dt):.4f}"
          f" null95 [{dt[1]:+.4f},{dt[-2]:+.4f}] max|d| {max(abs(x) for x in dt):.4f}")

    print("\n  paired bootstrap on the INCREMENT (refit both arms every draw, 300)")
    rng = random.Random(23)
    by = defaultdict(list)
    for r in rows:
        by[r["season"]].append(r)
    dd, ddt = [], []
    for _ in range(300):
        draw = []
        for s, rs in by.items():
            k = len(rs)
            draw += [rs[rng.randrange(k)] for _ in range(k)]
        a = chain2(draw, True, False)
        b = chain2(draw, True, True)
        dd.append(b[0] - a[0])
        ddt.append(b[2] - a[2])
    for nm, d in (("pooled", dd), ("TJ slice", ddt)):
        d = sorted(d)
        print(f"    {nm:<9} increment {statistics.mean(d):+.4f} sd {statistics.pstdev(d):.4f}"
              f" CI95 [{d[int(.025*len(d))]:+.4f},{d[int(.975*len(d))]:+.4f}]"
              f" P(improves) {sum(1 for x in d if x<0)/len(d):.3f}")

    print("\n=== Q3 DIRECTION SANITY (full-pool multipliers) ===")
    for r in rows:
        r["_b"] = r["_tj"]
    print("  TJ marginal:", {k: round(v, 4) for k, v in sorted(gate.fit_mult(rows).items())})
    print("  IL marginal:", {k: round(v, 4) for k, v in sorted(fit_mult_key(rows, "_il").items())})
    # realized survival rate by bucket -- the survivorship read
    for b in sorted(set(r["_tj"] for r in rows)):
        s = [r for r in rows if r["_tj"] == b]
        print(f"    {b:<9} n={len(s):>5} P(appears in t) {sum(r['survived'] for r in s)/len(s):.3f}"
              f"  mean actual BF {statistics.mean([r['bf'] for r in s]):7.1f}"
              f"  mean proj BF {statistics.mean([r['pt_proj'] for r in s]):7.1f}")


if __name__ == "__main__":
    main()
