"""OOS level-calibration of the FA market model (forward-chained rows only)."""
import sys, os, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fa_lab as lab

def report(rows, label):
    print(f"\n=== {label} (n={len(rows)}) ===")
    def sl(name, sel):
        r = [x for x in rows if sel(x)]
        if not r: return
        bias = statistics.mean(x["pg"] - x["ag"] for x in r)
        mae = statistics.mean(abs(x["pg"] - x["ag"]) for x in r)
        # multiplicative calibration in log space
        lr = [math.log(max(x["ag"],0.1)) - math.log(max(x["pg"],0.1)) for x in r]
        ybias = statistics.mean(x["py"] - x["ay"] for x in r)
        print(f"  {name:<18} n={len(r):>4}  bias ${bias:>+8.2f}M  MAE ${mae:>7.2f}M "
              f" logratio {statistics.mean(lr):>+6.3f}  ratio {math.exp(statistics.mean(lr)):>5.2f}x"
              f"  yrsBias {ybias:>+5.2f}")
    print(" -- by ACTUAL guarantee band")
    for nm, lo, hi in (("<$5M",0,5),("$5-25M",5,25),("$25-100M",25,100),(">=$100M",100,1e9)):
        sl(nm, lambda x,l=lo,h=hi: l <= x["ag"] < h)
    print(" -- by position group")
    for g in ("C","POS","SP","RP"):
        sl(g, lambda x,g=g: x["pos"]==g)
    print(" -- by age band")
    for nm, lo, hi in (("<=27",0,28),("28-30",28,31),("31-33",31,34),("34+",34,99)):
        sl(nm, lambda x,l=lo,h=hi: l <= x["age"] < h)
    print(" -- by QO")
    sl("QO", lambda x: x["qo"]); sl("noQO", lambda x: not x["qo"])
    print(" -- by ACTUAL years")
    for nm, lo, hi in (("1yr",1,2),("2-3yr",2,4),("4-6yr",4,7),("7yr+",7,99)):
        sl(nm, lambda x,l=lo,h=hi: l <= x["ay"] < h)
    print(" -- by winter")
    for w in sorted({x["winter"] for x in rows}):
        sl(str(w), lambda x,w=w: x["winter"]==w)

if __name__ == "__main__":
    pool = lab.load()
    for arm in (sys.argv[1:] or ["champ"]):
        r = lab.chain(pool, lab.ARMS[arm], want_rows=True)
        report(r["rows"], f"arm={arm}  pooled guar MAE ${r['guar_mae']:.3f}M")
