"""Does Tommy John history predict PLAYING-TIME shortfall for pitchers?

Design that does NOT condition on survival: every pitcher with >= MIN_BF in
season t-1 is projected for season t; a pitcher who never appears in t gets
actual BF = 0. So attrition is IN the label, which is the whole point --
fa_projection currently models playing time as a 2-season exposure Marcel
plus an age delta and nothing else.

Ex-ante by construction: tj_features counts only surgeries strictly before
the target season.
"""
import sys, os, json, math, statistics, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fa_projection as fp
import tj_surgery as tj

SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
MIN_BF = 100
FIRST, LAST = 2006, 2025


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
            if not pr or not pr.get("pt_proj"):
                continue
            act = seasons.get(t)
            act_bf = float(act["bf"]) if act else 0.0
            act_war = float(act.get("war") or 0.0) if act else 0.0
            f = tj.tj_features(m, str(t), store)
            rows.append({
                "mlbam": m, "season": t, "age": age, "role": pr["role"],
                "pt_proj": float(pr["pt_proj"]), "bf": act_bf,
                "prev_bf": float(prev["bf"]), "war": act_war,
                "survived": 1 if act else 0,
                "tj_pre": f["tj_pre"], "tj_cnt": f["tj_count_pre"],
                "tj_mo": f["months_since_last_tj_pre"],
            })
    with open(os.path.join(SCRATCH, "tj_pt_rows.pkl"), "wb") as fh:
        pickle.dump(rows, fh)
    return rows


def load():
    p = os.path.join(SCRATCH, "tj_pt_rows.pkl")
    if os.path.exists(p):
        return pickle.load(open(p, "rb"))
    return build()


if __name__ == "__main__":
    rows = build() if "--rebuild" in sys.argv else load()
    print("n =", len(rows), " seasons", min(r['season'] for r in rows), "-", max(r['season'] for r in rows))
    print("tj_pre share", round(statistics.mean(r["tj_pre"] for r in rows), 4))
    print("survival rate", round(statistics.mean(r["survived"] for r in rows), 4))

    def slab(name, sel):
        r = [x for x in rows if sel(x)]
        if len(r) < 30:
            return
        ratio = [x["bf"] / x["pt_proj"] for x in r]
        print(f"  {name:<22} n={len(r):>5}  survive {statistics.mean(x['survived'] for x in r):.3f}"
              f"  BF/projBF mean {statistics.mean(ratio):.3f} med {statistics.median(ratio):.3f}"
              f"  actBF {statistics.mean(x['bf'] for x in r):>6.1f}"
              f"  projBF {statistics.mean(x['pt_proj'] for x in r):>6.1f}"
              f"  WAR {statistics.mean(x['war'] for x in r):>5.2f}")

    print("\n-- by TJ history (as-of, strictly pre-season)")
    slab("no TJ", lambda x: x["tj_pre"] == 0)
    slab("TJ ever", lambda x: x["tj_pre"] == 1)
    slab("TJ x1", lambda x: x["tj_cnt"] == 1)
    slab("TJ x2+", lambda x: x["tj_cnt"] >= 2)
    print("\n-- by recency of the most recent TJ")
    slab("TJ  <24 mo", lambda x: x["tj_pre"] and x["tj_mo"] is not None and x["tj_mo"] < 24)
    slab("TJ 24-48 mo", lambda x: x["tj_pre"] and x["tj_mo"] is not None and 24 <= x["tj_mo"] < 48)
    slab("TJ 48-96 mo", lambda x: x["tj_pre"] and x["tj_mo"] is not None and 48 <= x["tj_mo"] < 96)
    slab("TJ  96+ mo", lambda x: x["tj_pre"] and x["tj_mo"] is not None and x["tj_mo"] >= 96)
    print("\n-- role x TJ")
    for rl in ("SP", "RP"):
        slab(f"{rl} no TJ", lambda x, rl=rl: x["role"] == rl and not x["tj_pre"])
        slab(f"{rl} TJ", lambda x, rl=rl: x["role"] == rl and x["tj_pre"])
