"""Scratch probe #2 (IDEATION ONLY): how wrong is comonotonic quantile summation?

warTotalP10/P90 (both /fa/ and /projections/) are computed as sum(per-year P10)
and sum(per-year P90). That is the rank-1 / perfectly-comonotonic aggregation:
it is exact ONLY if the forecast error in every season is perfectly rank-correlated.

Measure the empirical analogue on the cached corpus: inside conditioning cells
(base-season WAR bin x side), compare
    sd(sum_t y_t)   vs   sum_t sd(y_t)
The ratio is the shrink factor the honest interval needs (1.0 = comonotonic).
"""
import math
import pickle
import statistics
from collections import defaultdict
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "fa_corpus.pkl"
with open(CACHE, "rb") as fh:
    corpus = pickle.load(fh)
LAST = corpus["last"]
H = 5

for side in ("hit", "pit"):
    by = defaultdict(dict)
    for r in corpus[side]:
        if r.get("mlbam"):
            by[r["mlbam"]][r["season"]] = r
    cells = defaultdict(list)      # bin -> list of [y1..y5]
    for m, seasons in by.items():
        for s, row in seasons.items():
            w0 = row.get("war")
            if w0 is None or s + H > LAST - 1:
                continue
            expo = row.get("pa" if side == "hit" else "bf") or 0
            if expo < 100:
                continue
            fwd = [(seasons.get(s + h) or {}).get("war") or 0.0 for h in range(1, H + 1)]
            b = ("star" if w0 >= 3 else "reg" if w0 >= 1.5 else
                 "avg" if w0 >= 0.5 else "fringe")
            cells[b].append(fwd)
    print(f"\n=== {side}: sd(total) vs sum of per-year sd, 5-season forward window ===")
    for b in ("star", "reg", "avg", "fringe"):
        rows = cells[b]
        if len(rows) < 100:
            continue
        per = [statistics.pstdev([r[t] for r in rows]) for t in range(H)]
        tot = statistics.pstdev([sum(r) for r in rows])
        # implied average pairwise correlation from var(sum) = sum var + 2 sum cov
        sv = sum(v * v for v in per)
        cross = (tot * tot - sv) / 2.0
        pairs = [(i, j) for i in range(H) for j in range(i + 1, H)]
        denom = sum(per[i] * per[j] for i, j in pairs)
        rho = cross / denom if denom else float("nan")
        print(f"{b:>7} n={len(rows):5d}  sum_sd={sum(per):6.2f}  sd_total={tot:6.2f}  "
              f"ratio={tot/sum(per):.3f}  implied mean pairwise rho={rho:.3f}")
    # what the ratio implies for a 6-year FA term
    print("  (a comonotonic interval is 1/ratio times too wide at this window)")
