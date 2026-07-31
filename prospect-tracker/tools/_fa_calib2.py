"""Level calibration CONDITIONED ON THE PREDICTION (the decision-relevant form).

Conditioning on the ACTUAL is regression-to-the-mean by construction; the
question a reader actually asks is "when the board says $50M, what gets paid?"
"""
import sys, os, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fa_lab as lab

def deciles(rows, key, n=10):
    v = sorted(r[key] for r in rows)
    return [v[int(i * len(v) / n)] for i in range(1, n)]

def main(arm="champ"):
    pool = lab.load()
    r = lab.chain(pool, lab.ARMS[arm], want_rows=True)
    rows = r["rows"]
    print(f"arm={arm} n={len(rows)} pooled guar MAE ${r['guar_mae']:.3f}M bias ${r['guar_bias']:+.3f}M")
    cuts = deciles(rows, "pg")
    print("\n PREDICTED-guarantee decile -> what actually got paid")
    print(f"{'decile':>7}{'n':>5}{'predMed':>10}{'actMed':>10}{'act/pred':>10}"
          f"{'meanLogRatio':>14}{'bias$M':>9}{'MAE$M':>9}")
    for i in range(10):
        lo = cuts[i-1] if i > 0 else -1e18
        hi = cuts[i] if i < 9 else 1e18
        b = [x for x in rows if lo <= x["pg"] < hi]
        if not b: continue
        lr = [math.log(max(x["ag"],0.05)) - math.log(max(x["pg"],0.05)) for x in b]
        print(f"{i+1:>7}{len(b):>5}{statistics.median(x['pg'] for x in b):>10.2f}"
              f"{statistics.median(x['ag'] for x in b):>10.2f}"
              f"{statistics.median(x['ag'] for x in b)/max(statistics.median(x['pg'] for x in b),.01):>10.2f}"
              f"{statistics.mean(lr):>+14.3f}"
              f"{statistics.mean(x['ag']-x['pg'] for x in b):>+9.2f}"
              f"{statistics.mean(abs(x['ag']-x['pg']) for x in b):>9.2f}")
    # log-log calibration line, pooled OOS
    X = [math.log(max(x["pg"],0.05)) for x in rows]
    Y = [math.log(max(x["ag"],0.05)) for x in rows]
    mx, my = statistics.mean(X), statistics.mean(Y)
    b1 = sum((a-mx)*(c-my) for a,c in zip(X,Y)) / sum((a-mx)**2 for a in X)
    b0 = my - b1*mx
    print(f"\n log-log calibration  log(actual) = {b0:+.4f} + {b1:.4f} * log(pred)"
          f"   (perfect = 0 + 1.000)")
    resid = [c - (b0+b1*a) for a,c in zip(X,Y)]
    print(f" residual sd in log space {statistics.pstdev(resid):.3f}")
    # PREDICTED-years calibration
    print("\n PREDICTED years -> actual years")
    for y in sorted({int(x['py']) for x in rows}):
        b = [x for x in rows if int(x['py'])==y]
        print(f"   pred {y:>2}yr  n={len(b):>4}  actual mean {statistics.mean(x['ay'] for x in b):>5.2f}"
              f"  median {statistics.median(x['ay'] for x in b):>4.1f}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "champ")
