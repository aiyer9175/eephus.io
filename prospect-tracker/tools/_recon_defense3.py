"""RECON ONLY (lane: defense), part 3 -- the CONVERSION-MODEL ground truth.

Per-position Savant OAA (pos= param) x StatsAPI innings-by-position gives
WITHIN-player, WITHIN-season fielding-rate observations at two positions.
That is the identifying variation a positional-conversion model needs:
how much does the SAME glove lose/gain per inning moving A -> B?
"""
from __future__ import annotations

import csv
import itertools
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _recon_defense import CACHE, DATA, statsapi_fielding, sec, pearson

CODE = {"2": "C", "3": "1B", "4": "2B", "5": "3B", "6": "SS", "7": "LF", "8": "CF", "9": "RF"}
INN_UNIT = 1000.0   # OAA per 1000 defensive innings (~ a full season at one spot is ~1250)


def per_pos_oaa():
    out = defaultdict(dict)
    for y in range(2016, 2026):
        for c, p in CODE.items():
            f = CACHE / "savant_oaa" / f"oaa_{y}_pos{c}.csv"
            if not f.exists():
                continue
            for r in csv.DictReader(f.open(encoding="utf-8-sig")):
                try:
                    out[(int(r["player_id"]), y)][p] = (
                        float(r["outs_above_average"]),
                        float(r["fielding_runs_prevented"]))
                except ValueError:
                    continue
    return out


def main():
    oaa = per_pos_oaa()
    fld = statsapi_fielding()

    sec("(f) OAA x innings join -- can we build per-position RATES?")
    hit = miss = 0
    inn_missing = Counter()
    rates = defaultdict(dict)   # (mlbam,yr) -> pos -> (oaa_rate, frp_rate, innings)
    for key, byp in oaa.items():
        f = fld.get(key)
        if not f:
            miss += 1
            continue
        hit += 1
        for p, (o, fr) in byp.items():
            inn = (f.get(p) or {}).get("inn", 0.0)
            if inn <= 0:
                inn_missing[p] += 1
                continue
            rates[key][p] = (o * INN_UNIT / inn, fr * INN_UNIT / inn, inn)
    print(f"OAA player-seasons with a StatsAPI fielding row: {hit}/{hit+miss} "
          f"({100*hit/(hit+miss):.1f}%)")
    print("per-position rows with 0 StatsAPI innings (unusable for a rate):",
          dict(inn_missing))
    tot_rows = sum(len(v) for v in rates.values())
    print(f"usable per-position RATE observations: {tot_rows}")
    inns = [v[2] for d in rates.values() for v in d.values()]
    print(f"innings per observation: median={statistics.median(inns):.0f} "
          f"p25={sorted(inns)[len(inns)//4]:.0f} p75={sorted(inns)[3*len(inns)//4]:.0f} "
          f"max={max(inns):.0f}")

    sec("(f2) WITHIN-PLAYER-SEASON position pairs -- the conversion signal")
    MIN_INN = 100.0
    pair = defaultdict(list)
    for key, d in rates.items():
        ok = {p: v for p, v in d.items() if v[2] >= MIN_INN}
        for a, b in itertools.combinations(sorted(ok), 2):
            # difference in FRP per 1000 innings, b minus a
            pair[(a, b)].append((ok[b][1] - ok[a][1], min(ok[a][2], ok[b][2])))
    print(f"pairs with BOTH positions >= {MIN_INN:.0f} innings, same player-season:")
    print(f"{'pair':>8} {'n':>5} {'mean dFRP/1000inn':>18} {'95% CI':>20} "
          f"{'perm95|mean|':>13} {'median':>8}")
    rng = random.Random(41)
    for (a, b), v in sorted(pair.items(), key=lambda kv: -len(kv[1])):
        if len(v) < 30:
            continue
        xs = [d for d, _ in v]
        m = statistics.mean(xs)
        bs = []
        for _ in range(2000):
            s = [xs[rng.randrange(len(xs))] for _ in range(len(xs))]
            bs.append(statistics.mean(s))
        bs.sort()
        # permutation null: sign-flip (H0: no directional cost to the move)
        nulls = []
        for _ in range(1000):
            nulls.append(abs(statistics.mean([x if rng.random() < .5 else -x for x in xs])))
        nulls.sort()
        print(f"{a+'/'+b:>8} {len(xs):>5} {m:>18.2f} "
              f"{'['+format(bs[50],'.2f')+', '+format(bs[1949],'.2f')+']':>20} "
              f"{nulls[949]:>13.2f} {statistics.median(xs):>8.2f}")

    sec("(f3) OAA rate PERSISTENCE (year over year, same position) -- reliability")
    print("the shrinkage parameter a conversion model needs")
    for p in ("SS", "2B", "3B", "1B", "CF", "LF", "RF"):
        xs, ys = [], []
        for (m, y), d in rates.items():
            if p not in d or d[p][2] < 300:
                continue
            n = rates.get((m, y + 1))
            if not n or p not in n or n[p][2] < 300:
                continue
            xs.append(d[p][1]); ys.append(n[p][1])
        if len(xs) < 30:
            print(f"  {p:>3} n={len(xs)} (skip)")
            continue
        r = pearson(xs, ys)
        bs = []
        for _ in range(1000):
            idx = [rng.randrange(len(xs)) for _ in range(len(xs))]
            bs.append(pearson([xs[i] for i in idx], [ys[i] for i in idx]))
        bs.sort()
        nulls = []
        for _ in range(500):
            y2 = ys[:]; rng.shuffle(y2)
            nulls.append(abs(pearson(xs, y2)))
        nulls.sort()
        print(f"  {p:>3} n={len(xs):>4} r(y, y+1) = {r:.3f} "
              f"[{bs[25]:.3f}, {bs[974]:.3f}]  perm95={nulls[474]:.3f}")

    sec("(f4) SAMPLES written")
    out = DATA / "sources" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    for src, dst in (("oaa_all_2024.csv", "savant_oaa_2024_all.csv"),
                     ("oaa_2024_pos6.csv", "savant_oaa_2024_SS.csv"),
                     ("oaa_2024_pos4.csv", "savant_oaa_2024_2B.csv")):
        s = CACHE / "savant_oaa" / src
        if s.exists():
            lines = s.read_text(encoding="utf-8-sig").splitlines()
            (out / dst).write_text("\n".join(lines[:26]) + "\n", encoding="utf-8")
            print("wrote", out / dst, f"({len(lines)-1} rows in cache, 25 sampled)")
    # statsapi fielding sample
    f = CACHE / "statsapi_field" / "fld_2024.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["stats"][0]["splits"] = d["stats"][0]["splits"][:25]
    (out / "statsapi_fielding_2024_sample.json").write_text(
        json.dumps(d, indent=1)[:200000], encoding="utf-8")
    print("wrote", out / "statsapi_fielding_2024_sample.json")


if __name__ == "__main__":
    main()
