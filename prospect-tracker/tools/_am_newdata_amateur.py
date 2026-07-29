"""LANE newdata (c): amateur_leagues.py vs college_translation.

PRE-REGISTERED HYPOTHESES
  H-C1  The StatsAPI amateur line (sportId 22: CBB / CCBL / MLBDL / APP), keyed
        natively on mlbam, supports a college -> Single-A K%/BB% translation on a
        MUCH larger matched sample than the shipped CollegeSavant name-join
        (registered n = 207 hitters / 260 pitchers). Criterion: same
        regression-to-the-mean form, forward-chained by the amateur season, LOO
        MAE below the PREDICT-THE-MEAN control on the SAME pool, and the
        registered LOO MAEs (hit_k 5.295 / hit_bb 3.376 / pit_k 4.409 /
        pit_bb 3.117) reported alongside as context (different pools -- NOT a
        like-for-like win claim).
  H-C2  WOOD-BAT summer leagues (CCBL / MLBDL / APP) translate BETTER than NCAA
        metal-bat play: higher fitted slope and lower LOO MAE for the same
        target, because bat and competition are closer to pro.
  H-C3  (skeptical, pre-registered against the registered loss "college stuff
        r = -0.005") the amateur line does not rescue collegesavant_stuff.

CONTROLS on every reported effect: forward-chained by amateur season, a
zero-information control (the SAME predictor column row-permuted), a permutation
null band, and a paired bootstrap that refits the shrunk slope on each draw.

COVERAGE LIMIT stated up front: amateur_leagues is populated 2018-2026 and the
landed file here covers 2021-2026, so the matched pairs are recent-only.
"""
import sys, os, json, io, math, random, statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AM = json.load(io.open(os.path.join(ROOT, "data", "amateur_leagues.json"),
                       encoding="utf-8"))

WOOD = {"CCBL", "MLBDL", "APP"}
NCAA = {"CBB"}
SLOPE_SHRINK_K = 20          # matches rate_stabilization / college_translation
MIN_AM_PA, MIN_PRO_PA = 60, 100
MIN_AM_BF, MIN_PRO_BF = 60, 100


def load_pro():
    """Single-A (sportId 14) + High-A (13) season lines keyed by mlbam."""
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
    return hit, pit


def rate(n, d):
    return 100.0 * float(n) / float(d) if d else None


def fit_rtm(xs, ys, k=SLOPE_SHRINK_K):
    """regression-to-the-mean: pred = ybar + shrunk_slope * (x - xbar)."""
    n = len(xs)
    if n < 8:
        return None
    xb, yb = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - xb) ** 2 for x in xs)
    if sxx <= 0:
        return None
    ols = sum((x - xb) * (y - yb) for x, y in zip(xs, ys)) / sxx
    slope = ols * n / (n + k)
    syy = sum((y - yb) ** 2 for y in ys)
    r2 = ((sum((x - xb) * (y - yb) for x, y in zip(xs, ys)) ** 2)
          / (sxx * syy)) if syy > 0 else 0.0
    return {"xbar": xb, "ybar": yb, "ols": ols, "slope": slope, "r2": r2, "n": n}


def loo(xs, ys, k=SLOPE_SHRINK_K):
    """Leave-one-out MAE for the shrunk fit, plus the predict-the-mean control
    computed the same leave-one-out way (the zero-information floor)."""
    n = len(xs)
    e_fit, e_mean = [], []
    for i in range(n):
        tx = xs[:i] + xs[i + 1:]
        ty = ys[:i] + ys[i + 1:]
        f = fit_rtm(tx, ty, k)
        if not f:
            continue
        e_fit.append(abs((f["ybar"] + f["slope"] * (xs[i] - f["xbar"])) - ys[i]))
        e_mean.append(abs(statistics.mean(ty) - ys[i]))
    return (statistics.mean(e_fit) if e_fit else None,
            statistics.mean(e_mean) if e_mean else None, len(e_fit))


def chain(pairs, k=SLOPE_SHRINK_K, permute=None):
    """Forward-chained by amateur season: fit on strictly earlier amateur
    seasons, score the current one. Returns (fit MAE, mean-control MAE, n)."""
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
        tr = [p for p in pairs if p["s"] < T]
        te = [p for p in pairs if p["s"] == T]
        if len(tr) < 20 or not te:
            continue
        f = fit_rtm([p["x"] for p in tr], [p["y"] for p in tr], k)
        if not f:
            continue
        a = [abs((f["ybar"] + f["slope"] * (p["x"] - f["xbar"])) - p["y"]) for p in te]
        b = [abs(f["ybar"] - p["y"]) for p in te]
        ef += a
        em += b
        per.append((T, len(te), statistics.mean(a), statistics.mean(b)))
    if not ef:
        return None, None, 0, []
    return statistics.mean(ef), statistics.mean(em), len(ef), per


def build_pairs(leagues, side, xstat, ystat):
    hit, pit = PRO
    out = []
    for mid, lines in AM.items():
        m = int(mid)
        am = [l for l in lines
              if l["league"] in leagues
              and l["group"] == ("hitting" if side == "hit" else "pitching")]
        if not am:
            continue
        pro = (hit if side == "hit" else pit).get(m) or []
        for a in am:
            if side == "hit":
                pa = a.get("pa") or 0
                if pa < MIN_AM_PA:
                    continue
                x = rate(a.get(xstat) or 0, pa)
            else:
                bf = a.get("bf") or 0
                if bf < MIN_AM_BF:
                    continue
                x = rate(a.get(xstat) or 0, bf)
            if x is None:
                continue
            cand = sorted([p for p in pro if p["season"] > a["season"]],
                          key=lambda p: p["season"])
            tgt = None
            for p in cand:
                if side == "hit":
                    if (p.get("pa") or 0) >= MIN_PRO_PA:
                        tgt = p
                        break
                else:
                    if (p.get("bf") or (p.get("ip") and float(p["ip"]) * 4.3) or 0) >= MIN_PRO_BF:
                        tgt = p
                        break
            if not tgt:
                continue
            den = (tgt.get("pa") if side == "hit"
                   else (tgt.get("bf") or float(tgt.get("ip") or 0) * 4.3))
            y = rate(tgt.get(ystat) or 0, den)
            if y is None:
                continue
            out.append({"m": m, "s": a["season"], "x": x, "y": y,
                        "lg": a["league"], "tgt_season": tgt["season"]})
            if ONE_PER_PLAYER:
                break    # earliest qualifying amateur season only
    return out


ONE_PER_PLAYER = True


def report(name, pairs, registered_ref=None):
    from collections import Counter as _C
    print(f"\n===== {name}  n={len(pairs)} "
          f"(distinct players {len({p['m'] for p in pairs})}, "
          f"by amateur season {dict(sorted(_C(p['s'] for p in pairs).items()))}, "
          f"by league {dict(_C(p['lg'] for p in pairs))}) =====")
    if len(pairs) < 25:
        print("  UNAVAILABLE - fewer than 25 matched pairs")
        return
    f = fit_rtm([p["x"] for p in pairs], [p["y"] for p in pairs])
    print(f"  full-pool fit: xbar {f['xbar']:.2f}  ybar {f['ybar']:.2f}  "
          f"ols_slope {f['ols']:.4f}  shrunk_slope {f['slope']:.4f}  r2 {f['r2']:.4f}")
    lf, lm, ln = loo([p["x"] for p in pairs], [p["y"] for p in pairs])
    print(f"  LOO MAE  fit {lf:.4f}   predict-the-mean control {lm:.4f}   "
          f"delta {lf-lm:+.4f}   (n={ln})")
    if registered_ref:
        print(f"  registered college_translation LOO MAE for this stat: "
              f"{registered_ref}  (DIFFERENT POOL - context only)")
    ef, em, n, per = chain(pairs)
    if ef is None:
        print("  forward-chained: UNAVAILABLE (too few seasons)")
        return
    print(f"  FORWARD-CHAINED by amateur season: fit MAE {ef:.4f}  "
          f"mean-control {em:.4f}  delta {ef-em:+.4f}  n={n}")
    print(f"  {'season':>7}{'n':>5}{'fit':>9}{'mean':>9}{'delta':>9}")
    imp = 0
    for T, k, a, b in per:
        imp += (a < b)
        print(f"  {T:>7}{k:>5}{a:>9.4f}{b:>9.4f}{a-b:>+9.4f}")
    print(f"  folds improved {imp}/{len(per)}")
    nul = []
    for s in range(1, 61):
        e2, m2, _, _ = chain(pairs, permute=s)
        if e2 is not None:
            nul.append(e2 - m2)
    nul.sort()
    print(f"  ZERO-INFO CONTROL (predictor column permuted within season, "
          f"{len(nul)} draws): null mean {statistics.mean(nul):+.4f} "
          f"sd {statistics.pstdev(nul):.4f} null95 [{nul[1]:+.4f},{nul[-2]:+.4f}] "
          f"max|d| {max(abs(x) for x in nul):.4f}")
    print(f"    observed {ef-em:+.4f} -> outside null band: "
          f"{abs(ef-em) > max(abs(x) for x in nul) and ef < em}")
    # CLUSTER bootstrap on player id (a player can contribute >1 pair)
    rng = random.Random(5)
    byp = defaultdict(list)
    for p in pairs:
        byp[p["m"]].append(p)
    keys = list(byp)
    bs = []
    for _ in range(300):
        draw = []
        for _ in range(len(keys)):
            draw += byp[keys[rng.randrange(len(keys))]]
        e2, m2, _, _ = chain(draw)
        if e2 is not None:
            bs.append(e2 - m2)
    bs.sort()
    if bs:
        print(f"  PAIRED BOOTSTRAP (refit per draw, {len(bs)}): delta "
              f"{statistics.mean(bs):+.4f} sd {statistics.pstdev(bs):.4f} "
              f"CI95 [{bs[int(.025*len(bs))]:+.4f},{bs[int(.975*len(bs))]:+.4f}] "
              f"P(beats mean) {sum(1 for x in bs if x<0)/len(bs):.3f}")


PRO = None


def main():
    global PRO
    PRO = load_pro()
    hit, pit = PRO
    print(f"Single-A/High-A substrate: hitters {len(hit)} mlbam, "
          f"pitchers {len(pit)} mlbam (sportId 14+13, seasons 2021-2026)")
    from collections import Counter
    print("amateur lines by league:",
          Counter(l["league"] for v in AM.values() for l in v
                  if l["league"] in NCAA | WOOD))

    specs = [
        ("H-C1 NCAA (CBB) hitter K%   -> Single-A K%", NCAA, "hit", "so", "so", "5.295"),
        ("H-C1 NCAA (CBB) hitter BB%  -> Single-A BB%", NCAA, "hit", "bb", "bb", "3.376"),
        ("H-C1 NCAA (CBB) pitcher K%  -> Single-A K%", NCAA, "pit", "so", "so", "4.409"),
        ("H-C1 NCAA (CBB) pitcher BB% -> Single-A BB%", NCAA, "pit", "bb", "bb", "3.117"),
        ("H-C2 WOOD-BAT hitter K%     -> Single-A K%", WOOD, "hit", "so", "so", None),
        ("H-C2 WOOD-BAT hitter BB%    -> Single-A BB%", WOOD, "hit", "bb", "bb", None),
        ("H-C2 WOOD-BAT pitcher K%    -> Single-A K%", WOOD, "pit", "so", "so", None),
        ("H-C2 WOOD-BAT pitcher BB%   -> Single-A BB%", WOOD, "pit", "bb", "bb", None),
    ]
    global ONE_PER_PLAYER
    for mode in (True, False):
        ONE_PER_PLAYER = mode
        print("\n" + "#" * 74)
        print("# PAIRING MODE: " + ("one pair per player (earliest amateur season)"
                                    if mode else
                                    "all qualifying amateur seasons "
                                    "(cluster bootstrap on player)"))
        print("#" * 74)
        for nm, lg, side, xs, ys, ref in specs:
            report(nm, build_pairs(lg, side, xs, ys), ref)
    ONE_PER_PLAYER = True

    # H-C2 head-to-head on the SAME players (paired, removes pool differences)
    print("\n===== H-C2 HEAD-TO-HEAD on players with BOTH an NCAA and a wood-bat "
          "line (paired) =====")
    for side, stat in (("hit", "so"), ("hit", "bb"), ("pit", "so"), ("pit", "bb")):
        a = {p["m"]: p for p in build_pairs(NCAA, side, stat, stat)}
        b = {p["m"]: p for p in build_pairs(WOOD, side, stat, stat)}
        both = sorted(set(a) & set(b))
        if len(both) < 20:
            print(f"  {side}/{stat}: overlap n={len(both)} -> UNAVAILABLE")
            continue
        ya = [a[m]["y"] for m in both]
        fa = fit_rtm([a[m]["x"] for m in both], ya)
        fb = fit_rtm([b[m]["x"] for m in both], [b[m]["y"] for m in both])
        la = loo([a[m]["x"] for m in both], ya)
        lb = loo([b[m]["x"] for m in both], [b[m]["y"] for m in both])
        print(f"  {side}/{stat} overlap n={len(both)}: "
              f"NCAA ols {fa['ols']:+.4f} r2 {fa['r2']:.4f} LOO {la[0]:.4f} | "
              f"WOOD ols {fb['ols']:+.4f} r2 {fb['r2']:.4f} LOO {lb[0]:.4f}")


if __name__ == "__main__":
    main()
