"""ADVERSARIAL VERIFICATION of the `newdata` lane. Independent re-derivation.

Nothing here imports the lane's labs except the raw substrate loaders
(_fa_tj_pt.load -> the pickled rows, which are just (player, season) facts).
All fitting / chaining / control / bootstrap code below is written fresh.

TEST A  TJ-over-IL playing-time increment (lane claim: -1.7290 pooled BF,
        null max|d| 1.2696, SNR 1.36x, bootstrap CI95 [-2.9360,-0.2989]).
        A1 reproduce.  A2 richer IL baseline.  A3 PLAYER-clustered bootstrap
        (the lane resampled ROWS within season, which ignores the fact that one
        pitcher contributes up to 20 correlated rows).  A4 a CONDITIONAL
        zero-information control (TJ permuted within season x IL stratum),
        which is the correct twin for a claim of the form "TJ adds beyond IL".

TEST B  wood-bat amateur -> Single-A translation (lane claim: hitter K%
        forward-chained -0.8451 vs null max|d| 0.6572).
        B1 reproduce.  B2 LABEL-TIME forward chaining (the lane chains on the
        AMATEUR season only; a 2021 amateur row whose Single-A target lands in
        2025 is in the training set for the 2023 fold, i.e. the model is
        trained on outcomes that had not happened yet).  B3 fold-level detail.

TEST C  milb_park_factors YoY stability: the registered gate says "rho";
        the lane reported PEARSON. Compute BOTH.
"""
import sys, os, io, json, math, random, statistics
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")

FOLDS = list(range(2014, 2026))
SHRINK = 30.0


# ------------------------------------------------------------------ helpers
def spearman(xs, ys):
    def rk(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    return pearson(rk(xs), rk(ys))


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else float("nan")


# =========================================================== TEST A: TJ / IL
def tj_bucket(r):
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


def load_tj_rows():
    import _fa_tj_pt as src
    rows = src.load()
    IL = json.load(io.open(os.path.join(ROOT, ".cache", "mlb_transactions",
                                        "il_table.json"), encoding="utf-8"))["il"]
    for r in rows:
        y = IL.get(str(r["mlbam"])) or {}
        d1 = float((y.get(str(r["season"] - 1)) or [0.0, 0])[0])
        d2 = float((y.get(str(r["season"] - 2)) or [0.0, 0])[0])
        car = sum(float(v[0]) for s, v in y.items() if int(s) < r["season"])
        r["il_d1"], r["il_d2"], r["il_car"] = d1, d2, car
        r["tjb"] = tj_bucket(r)
        # lane's IL bucket (prior season only, 4 levels)
        r["il4"] = ("il_none" if d1 <= 0 else "il_lt30" if d1 < 30
                    else "il_30_90" if d1 < 90 else "il_90p")
        # richer IL bucket: prior-season x career-history -> 8 levels
        c = "c0" if car <= 0 else "c1" if car < 120 else "c2"
        r["il8"] = r["il4"] + "|" + c
    return rows


def _mult(train, key, basekey, denom):
    """Exposure-ratio multiplier per level of `key`, shrunk toward 1.0,
    anchored on the `basekey` level. denom = row field carrying the
    (possibly already-adjusted) projected exposure."""
    agg, cnt = {}, Counter()
    for r in train:
        a = agg.setdefault(r[key], [0.0, 0.0])
        a[0] += r["bf"]
        a[1] += r[denom]
        cnt[r[key]] += 1
    if basekey not in agg or agg[basekey][1] <= 0:
        return {}
    b0 = agg[basekey][0] / agg[basekey][1]
    out = {}
    for b, (num, den) in agg.items():
        if den <= 0:
            continue
        out[b] = (cnt[b] * ((num / den) / b0) + SHRINK) / (cnt[b] + SHRINK)
    out[basekey] = 1.0
    return out


def chain_il_tj(rows, ilkey=None, use_tj=False, tjfield="tjb"):
    """Forward-chained pooled PT MAE. IL arm (if any) fit first; TJ arm fit on
    the IL-adjusted exposure so it can only claim residual credit."""
    err = []
    per = []
    for T in FOLDS:
        tr = [r for r in rows if r["season"] < T]
        te = [r for r in rows if r["season"] == T]
        if len(tr) < 300 or not te:
            continue
        mi = {}
        if ilkey:
            mi = _mult(tr, ilkey, "il_none" if ilkey == "il4" else "il_none|c0",
                       "pt_proj")
            for r in tr:
                r["_res"] = r["pt_proj"] * mi.get(r[ilkey], 1.0)
        else:
            for r in tr:
                r["_res"] = r["pt_proj"]
        mt = _mult(tr, tjfield, "none", "_res") if use_tj else {}
        fe = []
        for r in te:
            p = r["pt_proj"]
            if ilkey:
                p *= mi.get(r[ilkey], 1.0)
            if use_tj:
                p *= mt.get(r[tjfield], 1.0)
            fe.append(abs(p - r["bf"]))
        err += fe
        per.append((T, len(te), statistics.mean(fe)))
    return statistics.mean(err), per, len(err)


def permuted(rows, seed, strata):
    """Zero-information twin of the TJ COLUMN: row-permute tjb within `strata`."""
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    by = defaultdict(list)
    for r in out:
        by[tuple(r[k] for k in strata)].append(r)
    for _, rs in by.items():
        labs = [r["tjb"] for r in rs]
        rng.shuffle(labs)
        for r, l in zip(rs, labs):
            r["tjb"] = l
    return out


def test_a(rows):
    print("=" * 78)
    print("TEST A  TJ playing-time increment over an IL baseline (independent)")
    print("=" * 78)
    print("  n rows", len(rows), " distinct pitchers",
          len({r["mlbam"] for r in rows}),
          " seasons", min(r["season"] for r in rows), "-",
          max(r["season"] for r in rows))
    print("  tj buckets", dict(Counter(r["tjb"] for r in rows)))

    base, _, n = chain_il_tj(rows, None, False)
    il4, _, _ = chain_il_tj(rows, "il4", False)
    il4tj, per, nn = chain_il_tj(rows, "il4", True)
    il8, _, _ = chain_il_tj(rows, "il8", False)
    il8tj, _, _ = chain_il_tj(rows, "il8", True)
    tjonly, _, _ = chain_il_tj(rows, None, True)
    print(f"\n  A1 scored rows n={n}")
    print(f"    no arm                  {base:9.4f}")
    print(f"    TJ only                 {tjonly:9.4f}   d {tjonly-base:+.4f}")
    print(f"    IL4 only                {il4:9.4f}")
    print(f"    IL4 + TJ                {il4tj:9.4f}   INCREMENT {il4tj-il4:+.4f}")
    print(f"    IL8 only (richer IL)    {il8:9.4f}")
    print(f"    IL8 + TJ                {il8tj:9.4f}   INCREMENT {il8tj-il8:+.4f}")

    for label, ilkey, obs_base, obs in (("IL4", "il4", il4, il4tj),
                                        ("IL8", "il8", il8, il8tj)):
        for sname, strata in (("season only (lane's control)", ("season",)),
                              ("season x IL stratum (conditional)",
                               ("season", ilkey))):
            nul = []
            for s in range(1, 61):
                m, _, _ = chain_il_tj(permuted(rows, s, strata), ilkey, True)
                nul.append(m - obs_base)
            nul.sort()
            mx = max(abs(x) for x in nul)
            d = obs - obs_base
            print(f"\n    NULL [{label}, {sname}] 60 draws: mean {statistics.mean(nul):+.4f}"
                  f" sd {statistics.pstdev(nul):.4f} null95 [{nul[1]:+.4f},{nul[-2]:+.4f}]"
                  f" max|d| {mx:.4f}")
            print(f"      observed increment {d:+.4f}   SNR vs max|d| "
                  f"{abs(d)/mx if mx else float('nan'):.2f}x   outside band: {abs(d) > mx and d < 0}")

    # A3 PLAYER-clustered bootstrap vs the lane's row-within-season bootstrap
    byp = defaultdict(list)
    for r in rows:
        byp[r["mlbam"]].append(r)
    keys = list(byp)
    bys = defaultdict(list)
    for r in rows:
        bys[r["season"]].append(r)
    for nm, draw_fn in (
        ("rows within season (lane's)",
         lambda rng: [rs[rng.randrange(len(rs))] for s, rs in bys.items()
                      for _ in range(len(rs))]),
        ("PLAYER clusters (correct)",
         lambda rng: [r for _ in range(len(keys))
                      for r in byp[keys[rng.randrange(len(keys))]]]),
    ):
        rng = random.Random(23)
        dd = []
        for _ in range(300):
            dr = draw_fn(rng)
            a, _, _ = chain_il_tj(dr, "il4", False)
            b, _, _ = chain_il_tj(dr, "il4", True)
            dd.append(b - a)
        dd.sort()
        print(f"\n    BOOTSTRAP [{nm}] 300 draws, both arms refit: mean "
              f"{statistics.mean(dd):+.4f} sd {statistics.pstdev(dd):.4f} "
              f"CI95 [{dd[int(.025*len(dd))]:+.4f},{dd[int(.975*len(dd))]:+.4f}] "
              f"P(improves) {sum(1 for x in dd if x < 0)/len(dd):.3f}")


# ======================================================= TEST B: wood-bat
WOOD = {"CCBL", "MLBDL", "APP"}


def load_amateur_pairs(side, stat, min_am=60, min_pro=100):
    AM = json.load(io.open(os.path.join(ROOT, "data", "amateur_leagues.json"),
                           encoding="utf-8"))
    hit, pit = defaultdict(list), defaultdict(list)
    for sport in (14, 13):
        for season in range(2021, 2027):
            for grp, sink in (("hitting", hit), ("pitching", pit)):
                p = os.path.join(ROOT, ".cache", "milb_stats",
                                 f"{grp}_{sport}_{season}.json")
                if not os.path.exists(p):
                    continue
                for r in json.load(io.open(p, encoding="utf-8")):
                    if r.get("mlbam"):
                        sink[int(r["mlbam"])].append(r)
    pro = hit if side == "hit" else pit
    out = []
    for mid, lines in AM.items():
        m = int(mid)
        am = [l for l in lines if l["league"] in WOOD
              and l["group"] == ("hitting" if side == "hit" else "pitching")]
        if not am:
            continue
        cand_pro = pro.get(m) or []
        for a in sorted(am, key=lambda l: l["season"]):
            den = (a.get("pa") or 0) if side == "hit" else (a.get("bf") or 0)
            if den < min_am:
                continue
            x = 100.0 * float(a.get(stat) or 0) / den
            tgt = None
            for p in sorted([p for p in cand_pro if p["season"] > a["season"]],
                            key=lambda p: p["season"]):
                d = ((p.get("pa") or 0) if side == "hit"
                     else (p.get("bf") or (float(p.get("ip") or 0) * 4.3)))
                if d >= min_pro:
                    tgt = (p, d)
                    break
            if not tgt:
                continue
            p, d = tgt
            out.append({"m": m, "s": a["season"], "ts": p["season"],
                        "x": x, "y": 100.0 * float(p.get(stat) or 0) / d})
            break          # one pair per player, earliest amateur season
    return out


def fit_rtm(xs, ys, k=20):
    n = len(xs)
    if n < 8:
        return None
    xb, yb = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - xb) ** 2 for x in xs)
    if sxx <= 0:
        return None
    ols = sum((x - xb) * (y - yb) for x, y in zip(xs, ys)) / sxx
    return {"xbar": xb, "ybar": yb, "slope": ols * n / (n + k)}


def chain_am(pairs, mode="feature", permute=None):
    """mode='feature': train on amateur season < T (the lane's chaining).
       mode='label'  : ALSO require the training pair's TARGET season to be
                       strictly before the earliest target season in fold T,
                       i.e. only outcomes that had actually happened."""
    if permute is not None:
        rng = random.Random(permute)
        by = defaultdict(list)
        for p in pairs:
            by[p["s"]].append(p)
        pairs = []
        for s, ps in by.items():
            xs = [p["x"] for p in ps]
            rng.shuffle(xs)
            pairs += [dict(p, x=x) for p, x in zip(ps, xs)]
    seasons = sorted({p["s"] for p in pairs})
    ef, em, per = [], [], []
    for T in seasons[1:]:
        te = [p for p in pairs if p["s"] == T]
        if not te:
            continue
        if mode == "feature":
            tr = [p for p in pairs if p["s"] < T]
        else:
            asof = min(p["ts"] for p in te)     # decision date for this fold
            tr = [p for p in pairs if p["s"] < T and p["ts"] <= asof]
        if len(tr) < 20:
            continue
        f = fit_rtm([p["x"] for p in tr], [p["y"] for p in tr])
        if not f:
            continue
        a = [abs(f["ybar"] + f["slope"] * (p["x"] - f["xbar"]) - p["y"]) for p in te]
        b = [abs(f["ybar"] - p["y"]) for p in te]
        ef += a
        em += b
        per.append((T, len(te), len(tr), statistics.mean(a), statistics.mean(b)))
    if not ef:
        return None, None, 0, []
    return statistics.mean(ef), statistics.mean(em), len(ef), per


def test_b():
    print("\n" + "=" * 78)
    print("TEST B  wood-bat amateur -> Single-A translation (independent)")
    print("=" * 78)
    for side, stat, nm in (("hit", "so", "hitter K%"), ("hit", "bb", "hitter BB%"),
                           ("pit", "bb", "pitcher BB%"), ("pit", "so", "pitcher K%")):
        pairs = load_amateur_pairs(side, stat)
        print(f"\n  --- {nm}: n={len(pairs)} players={len({p['m'] for p in pairs})}"
              f" amateur seasons {dict(sorted(Counter(p['s'] for p in pairs).items()))}"
              f" target seasons {dict(sorted(Counter(p['ts'] for p in pairs).items()))}")
        for mode in ("feature", "label"):
            ef, em, n, per = chain_am(pairs, mode)
            if ef is None:
                print(f"    [{mode}-time chaining] UNAVAILABLE")
                continue
            d = ef - em
            nul = []
            for s in range(1, 61):
                e2, m2, _, _ = chain_am(pairs, mode, permute=s)
                if e2 is not None:
                    nul.append(e2 - m2)
            nul.sort()
            mx = max(abs(x) for x in nul) if nul else float("nan")
            print(f"    [{mode:>7}-time chaining] fit {ef:.4f} mean-ctl {em:.4f}"
                  f" delta {d:+.4f} n={n} folds={len(per)}")
            for T, k, ntr, a, b in per:
                print(f"        fold {T} n_te={k:>4} n_tr={ntr:>4}"
                      f" fit {a:.4f} mean {b:.4f} d {a-b:+.4f}")
            print(f"        NULL 60 draws: mean {statistics.mean(nul):+.4f}"
                  f" null95 [{nul[1]:+.4f},{nul[-2]:+.4f}] max|d| {mx:.4f}"
                  f"  SNR {abs(d)/mx if mx else float('nan'):.2f}x"
                  f"  outside: {abs(d) > mx and d < 0}")
            byp = defaultdict(list)
            for p in pairs:
                byp[p["m"]].append(p)
            keys = list(byp)
            rng = random.Random(5)
            bs = []
            for _ in range(300):
                dr = [q for _ in range(len(keys))
                      for q in byp[keys[rng.randrange(len(keys))]]]
                e2, m2, _, _ = chain_am(dr, mode)
                if e2 is not None:
                    bs.append(e2 - m2)
            bs.sort()
            if bs:
                print(f"        BOOTSTRAP (player clusters, refit) mean "
                      f"{statistics.mean(bs):+.4f} CI95 "
                      f"[{bs[int(.025*len(bs))]:+.4f},{bs[int(.975*len(bs))]:+.4f}]"
                      f" P(beats mean) {sum(1 for x in bs if x < 0)/len(bs):.3f}")


# ======================================================= TEST C: park factors
def test_c():
    print("\n" + "=" * 78)
    print("TEST C  milb_park_factors YoY stability: registered gate says RHO")
    print("=" * 78)
    PF = json.load(io.open(os.path.join(ROOT, "data", "milb_park_factors.json"),
                           encoding="utf-8"))
    ven = PF["venues"]
    print("  venues node type", type(ven).__name__, "n", len(ven))
    sample = ven[0] if isinstance(ven, list) else ven[list(ven)[0]]
    print("  sample keys", list(sample)[:14] if isinstance(sample, dict) else sample)
    for fld in ("run_pf", "hr_pf"):
        by = {}
        for r in ven:
            vid = str(r.get("venue_id"))
            for s, d in (r.get("seasons") or {}).items():
                if d.get(fld) is not None:
                    by[(vid, int(s))] = float(d[fld])
        xs, ys = [], []
        for (vid, s), v in by.items():
            nxt = by.get((vid, s + 1))
            if nxt is not None:
                xs.append(v)
                ys.append(nxt)
        if len(xs) < 10:
            print(f"  {fld}: n={len(xs)} UNAVAILABLE")
            continue
        print(f"  {fld} [SHRUNK venue-season, all seasons]: n={len(xs)}   "
              f"PEARSON {pearson(xs, ys):+.4f}   SPEARMAN(rho) {spearman(xs, ys):+.4f}"
              f"   gate bar 0.50")
        # 2026 is explicitly partial-season per the artifact's own method note
        xs2, ys2 = [], []
        for (vid, s), v in by.items():
            if s + 1 > 2025:
                continue
            nxt = by.get((vid, s + 1))
            if nxt is not None:
                xs2.append(v)
                ys2.append(nxt)
        print(f"  {fld} [SHRUNK, excl. partial 2026]: n={len(xs2)}   "
              f"PEARSON {pearson(xs2, ys2):+.4f}   SPEARMAN(rho) {spearman(xs2, ys2):+.4f}")
        # UNSHRUNK team-season ratio, the actual measured environment
        raw = {}
        for t in PF["team_seasons"]:
            if fld == "run_pf":
                h, r_ = t.get("rpg_home"), t.get("rpg_road")
                if not h or not r_:
                    continue
                val = float(h) / float(r_)
            else:
                continue
            raw.setdefault((str(t.get("venue_id")), int(t["season"])), []).append(val)
        if raw:
            rm = {k: sum(v) / len(v) for k, v in raw.items()}
            xr, yr = [], []
            for (vid, s), v in rm.items():
                nxt = rm.get((vid, s + 1))
                if nxt is not None and s + 1 <= 2025:
                    xr.append(v)
                    yr.append(nxt)
            print(f"  {fld} [UNSHRUNK raw home/road ratio, excl 2026]: n={len(xr)}   "
                  f"PEARSON {pearson(xr, yr):+.4f}   SPEARMAN(rho) {spearman(xr, yr):+.4f}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "a"):
        test_a(load_tj_rows())
    if which in ("all", "b"):
        test_b()
    if which in ("all", "c"):
        test_c()
