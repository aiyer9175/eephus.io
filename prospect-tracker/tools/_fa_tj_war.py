"""Does the TJ PT multiplier improve the projected pitcher WAR (Gate-1)?

The multiplier is applied to the EXPOSURE (BF and the IP it implies), so it
reaches WAR through fa_projection.war_from_projection's ip100 term. Same
controls as the PT gate.
"""
import sys, os, math, random, statistics, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fa_projection as fp
import tj_surgery as tj
import _fa_tj_gate as gate

SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
MIN_BF, FIRST, LAST = 100, 2006, 2025
P = os.path.join(SCRATCH, "tj_war_rows.pkl")


def build():
    corpus = fp.build_corpus()
    league = corpus["league"]
    by = {}
    for r in corpus["pit"]:
        if r.get("mlbam"):
            by.setdefault(r["mlbam"], {})[r["season"]] = r
    store = tj._load_store()
    curves, war_map = fp.fitted_models(corpus, LAST)
    rows = []
    for m, seasons in by.items():
        for t in range(FIRST, LAST + 1):
            prev = seasons.get(t - 1)
            if not prev or (prev.get("bf") or 0) < MIN_BF:
                continue
            hist = [seasons[s] for s in (t - 1, t - 2, t - 3) if s in seasons]
            age = (prev.get("age") or 0) + 1
            pr = fp.project_player(hist, "pit", t, curves, league, age)
            if not pr or not pr.get("pt_proj") or not pr.get("ip_proj"):
                continue
            act = seasons.get(t)
            lgf = fp._league_recent(league, t, "lg_fip") or 4.1
            w_base = fp.war_from_projection(pr, "pit", war_map, league, t)
            f = tj.tj_features(m, str(t), store)
            rows.append({
                "mlbam": m, "season": t, "age": age, "role": pr["role"],
                "pt_proj": float(pr["pt_proj"]), "ip_proj": float(pr["ip_proj"]),
                "fip": float(pr["fip_proj"]), "lgfip": float(lgf),
                "war_base": float(w_base), "bf": float(act["bf"]) if act else 0.0,
                "war": float(act.get("war") or 0.0) if act else 0.0,
                "tj_pre": f["tj_pre"], "tj_cnt": f["tj_count_pre"],
                "tj_mo": f["months_since_last_tj_pre"],
            })
    # re-derive WAR under a scaled exposure using the fitted map directly
    coef = war_map["pit"]["coef"]
    for r in rows:
        r["_coef"] = coef
    pickle.dump({"rows": rows, "coef": coef}, open(P, "wb"))
    return rows, coef


def war_at(r, coef, scale):
    """pit WAR = b0 + b1*(IP/100) + b2*(lgFIP-FIP)*(IP/100) + b3*SP*(IP/100)"""
    ip = r["ip_proj"] * scale
    sp = 1.0 if r["role"] == "SP" else 0.0
    lgf = r["lgfip"]
    if lgf is None:
        return None
    return (coef[0] + coef[1] * (ip / 100.0)
            + coef[2] * (lgf - r["fip"]) * (ip / 100.0)
            + coef[3] * sp * (ip / 100.0))


def chain(rows, coef, permute_seed=None):
    rows = list(rows)
    if permute_seed is not None:
        rng = random.Random(permute_seed)
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
    eb, ec, per, tjb, tjc = [], [], [], [], []
    for T in gate.FOLDS:
        tr = [r for r in rows if r["season"] < T]
        te = [r for r in rows if r["season"] == T]
        if len(tr) < 300 or not te:
            continue
        m = gate.fit_mult(tr)
        fb, fc = [], []
        for r in te:
            wb = war_at(r, coef, 1.0)
            wc = war_at(r, coef, m.get(r["_b"], 1.0))
            if wb is None:
                continue
            fb.append(abs(wb - r["war"]))
            fc.append(abs(wc - r["war"]))
            if r["_b"] != "none":
                tjb.append(fb[-1])
                tjc.append(fc[-1])
        eb += fb
        ec += fc
        per.append((T, len(fb), statistics.mean(fb), statistics.mean(fc)))
    return (statistics.mean(eb), statistics.mean(ec), per,
            statistics.mean(tjb), statistics.mean(tjc), len(eb), len(tjb))


if __name__ == "__main__":
    if "--rebuild" in sys.argv or not os.path.exists(P):
        rows, coef = build()
    else:
        d = pickle.load(open(P, "rb")); rows, coef = d["rows"], d["coef"]
    for r in rows:
        r["_b0"] = gate.bucket(r)
    print("pit WAR map coef", [round(c, 4) for c in coef])
    b, c, per, tb, tc, n, ntj = chain(rows, coef)
    print(f"\nPOINT ESTIMATE n={n} (tj slice {ntj})")
    print(f"  pooled WAR MAE  base {b:.4f}  cand {c:.4f}  delta {c-b:+.4f}")
    print(f"  TJ-slice        base {tb:.4f}  cand {tc:.4f}  delta {tc-tb:+.4f}")
    nneg = sum(1 for _, _, x, y in per if y < x)
    print(f"  folds improved {nneg}/{len(per)}")
    for T, k, x, y in per:
        print(f"   {T} n={k:>4} {x:.4f} -> {y:.4f}  {y-x:+.4f}")
    ctl = [chain(rows, coef, permute_seed=s) for s in range(1, 41)]
    dp = sorted(x[1] - x[0] for x in ctl); dt = sorted(x[4] - x[3] for x in ctl)
    print(f"\nZERO-INFO CONTROL pooled: mean {statistics.mean(dp):+.4f} sd {statistics.pstdev(dp):.4f}"
          f" null95 [{dp[1]:+.4f},{dp[-2]:+.4f}] max|d| {max(abs(x) for x in dp):.4f}")
    print(f"ZERO-INFO CONTROL tjslice: mean {statistics.mean(dt):+.4f} sd {statistics.pstdev(dt):.4f}"
          f" null95 [{dt[1]:+.4f},{dt[-2]:+.4f}] max|d| {max(abs(x) for x in dt):.4f}")
    rng = random.Random(11)
    by = {}
    for r in rows:
        by.setdefault(r["season"], []).append(r)
    dp, dt = [], []
    for _ in range(400):
        draw = []
        for s, rs in by.items():
            k = len(rs)
            draw += [dict(rs[rng.randrange(k)]) for _ in range(k)]
        x = chain(draw, coef)
        dp.append(x[1] - x[0]); dt.append(x[4] - x[3])
    for nm, d in (("pooled", dp), ("TJ slice", dt)):
        d = sorted(d)
        print(f"BOOTSTRAP {nm:<9} delta {statistics.mean(d):+.4f} sd {statistics.pstdev(d):.4f}"
              f" CI95 [{d[int(.025*len(d))]:+.4f},{d[int(.975*len(d))]:+.4f}]"
              f" P(imp) {sum(1 for x in d if x<0)/len(d):.3f}")
