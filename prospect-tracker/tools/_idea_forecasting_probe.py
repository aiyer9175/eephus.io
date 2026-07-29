"""Scratch feasibility probe (IDEATION ONLY - writes nothing back to the repo).

Loads the cached FA corpus directly (no rebuild) and measures:
  1. the exposure MIXTURE: P(absent next season), and the shape of PA | present
  2. the persistence / correlation structure of WAR across horizons (for the
     comonotonic-sum question on warTotalP10/P90)
  3. reliability (split-half-ish year-to-year) of the component rates
"""
import pickle
import statistics
from collections import defaultdict
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "fa_corpus.pkl"
with open(CACHE, "rb") as fh:
    corpus = pickle.load(fh)

print("corpus span", corpus.get("first"), corpus.get("last"),
      "hit rows", len(corpus["hit"]), "pit rows", len(corpus["pit"]))

for side, expo_key in (("hit", "pa"), ("pit", "bf")):
    by = defaultdict(dict)
    for r in corpus[side]:
        if r.get("mlbam"):
            by[r["mlbam"]][r["season"]] = r
    # 1. exposure mixture, conditioned on a "regular" base season
    buckets = defaultdict(list)
    absent = defaultdict(int)
    tot = defaultdict(int)
    for m, seasons in by.items():
        for s, row in seasons.items():
            if s + 1 > corpus["last"] - 1:
                continue
            e0 = row.get(expo_key) or 0
            if e0 <= 0:
                continue
            b = ("reg" if e0 >= (450 if side == "hit" else 500) else
                 "part" if e0 >= (200 if side == "hit" else 200) else "fringe")
            nxt = seasons.get(s + 1)
            tot[b] += 1
            if nxt is None:
                absent[b] += 1
            else:
                buckets[b].append(nxt.get(expo_key) or 0)
    print(f"\n--- {side} next-season exposure mixture ---")
    for b in ("reg", "part", "fringe"):
        n = tot[b]
        if not n:
            continue
        vals = sorted(buckets[b])
        q = lambda p: vals[min(len(vals) - 1, int(p * len(vals)))] if vals else 0
        print(f"{b:>7} n={n:5d} P(absent)={absent[b]/n:.3f} "
              f"| given present: p10={q(.10):5.0f} p25={q(.25):5.0f} p50={q(.50):5.0f} "
              f"p75={q(.75):5.0f} p90={q(.90):5.0f}")
        # crude multimodality read: share of present-players below 40% of a full load
        full = 600 if side == "hit" else 600
        low = sum(1 for v in vals if v < 0.4 * full) / max(len(vals), 1)
        print(f"{'':>7}   share of PRESENT players under 40% of a full load: {low:.3f}")

    # 2. WAR persistence: corr(war_t, war_{t+h}) among players present in BOTH,
    #    and among the full pool with absent = 0 (the label convention).
    print(f"--- {side} WAR autocorrelation (label convention: absent = 0) ---")
    for h in (1, 2, 3, 4):
        pairs_sv, pairs_all = [], []
        for m, seasons in by.items():
            for s, row in seasons.items():
                if row.get("war") is None or s + h > corpus["last"] - 1:
                    continue
                nxt = seasons.get(s + h)
                pairs_all.append((row["war"], (nxt or {}).get("war") or 0.0))
                if nxt is not None and nxt.get("war") is not None:
                    pairs_sv.append((row["war"], nxt["war"]))

        def corr(p):
            if len(p) < 30:
                return float("nan")
            xs = [a for a, _ in p]
            ys = [b for _, b in p]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
            if sx == 0 or sy == 0:
                return float("nan")
            return sum((a - mx) * (b - my) for a, b in p) / (len(p) * sx * sy)
        print(f"  h={h} r_all={corr(pairs_all):.3f} (n={len(pairs_all)})  "
              f"r_survived={corr(pairs_sv):.3f} (n={len(pairs_sv)})")

# 3. serial correlation of YEAR-OVER-YEAR WAR DEVIATIONS from a naive 3-yr mean
#    -- the quantity that governs whether summing per-year quantiles is right.
print("\n--- residual serial correlation (deviation from trailing 3yr mean) ---")
for side in ("hit", "pit"):
    by = defaultdict(dict)
    for r in corpus[side]:
        if r.get("mlbam"):
            by[r["mlbam"]][r["season"]] = r
    d1, d2 = [], []
    for m, seasons in by.items():
        ss = sorted(seasons)
        for s in ss:
            hist = [seasons[t]["war"] for t in (s - 1, s - 2, s - 3)
                    if t in seasons and seasons[t].get("war") is not None]
            if len(hist) < 2:
                continue
            base = sum(hist) / len(hist)
            r0 = (seasons[s].get("war") or 0.0) - base
            n1 = seasons.get(s + 1)
            if n1 is not None and s + 1 <= corpus["last"] - 1:
                d1.append((r0, (n1.get("war") or 0.0) - base))
            n2 = seasons.get(s + 2)
            if n2 is not None and s + 2 <= corpus["last"] - 1:
                d2.append((r0, (n2.get("war") or 0.0) - base))

    def corr(p):
        if len(p) < 30:
            return float("nan")
        xs = [a for a, _ in p]
        ys = [b for _, b in p]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
        return sum((a - mx) * (b - my) for a, b in p) / (len(p) * sx * sy)
    print(f"  {side}: corr(dev_t, dev_t+1)={corr(d1):.3f} n={len(d1)}   "
          f"corr(dev_t, dev_t+2)={corr(d2):.3f} n={len(d2)}")
