"""TEST A2: redo the TJ-over-IL redundancy check on the ARM THAT ACTUALLY SHIPS.

fa_projection applies PT_TJ_MULT to the lt24 bucket ONLY. The newdata lane ran
its redundancy test on the FIVE-level bucket arm and permuted the five-level
label as its control -- the exact mismatch the P-TJPT header was corrected for
on 2026-07-25 ("Match the control to the arm you actually ship").

Here the arm is a single binary lt24 multiplier and the zero-information twin
is the SAME binary column row-permuted (within season, and within season x IL
stratum). Also reports the null band as a function of draw count, because
max|d| grows with draws and is not a stable floor.
"""
import sys, os, io, json, random, statistics
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import _fa_tj_pt as src

FOLDS = list(range(2014, 2026))
SHRINK = 30.0
FROZEN = 0.606


def load():
    rows = src.load()
    IL = json.load(io.open(os.path.join(ROOT, ".cache", "mlb_transactions",
                                        "il_table.json"), encoding="utf-8"))["il"]
    for r in rows:
        y = IL.get(str(r["mlbam"])) or {}
        d1 = float((y.get(str(r["season"] - 1)) or [0.0, 0])[0])
        r["il4"] = ("il_none" if d1 <= 0 else "il_lt30" if d1 < 30
                    else "il_30_90" if d1 < 90 else "il_90p")
        mo = r["tj_mo"]
        r["lt24"] = 1 if (r["tj_pre"] and mo is not None and mo < 24) else 0
    return rows


def _mult(train, key, base, denom):
    agg, cnt = {}, Counter()
    for r in train:
        a = agg.setdefault(r[key], [0.0, 0.0])
        a[0] += r["bf"]
        a[1] += r[denom]
        cnt[r[key]] += 1
    if base not in agg or agg[base][1] <= 0:
        return {}
    b0 = agg[base][0] / agg[base][1]
    out = {}
    for b, (num, den) in agg.items():
        if den <= 0:
            continue
        out[b] = (cnt[b] * ((num / den) / b0) + SHRINK) / (cnt[b] + SHRINK)
    out[base] = 1.0
    return out


def chain(rows, use_il, tj_mode):
    """tj_mode: None | 'refit' (ex-ante lt24 multiplier) | 'frozen' (0.606)."""
    err, per = [], []
    for T in FOLDS:
        tr = [r for r in rows if r["season"] < T]
        te = [r for r in rows if r["season"] == T]
        if len(tr) < 300 or not te:
            continue
        mi = {}
        if use_il:
            mi = _mult(tr, "il4", "il_none", "pt_proj")
        for r in tr:
            r["_res"] = r["pt_proj"] * (mi.get(r["il4"], 1.0) if use_il else 1.0)
        mt = _mult(tr, "lt24", 0, "_res") if tj_mode == "refit" else {}
        fe = []
        for r in te:
            p = r["pt_proj"]
            if use_il:
                p *= mi.get(r["il4"], 1.0)
            if tj_mode == "refit":
                p *= mt.get(r["lt24"], 1.0)
            elif tj_mode == "frozen" and r["lt24"]:
                p *= FROZEN
            fe.append(abs(p - r["bf"]))
        err += fe
        per.append((T, len(te), statistics.mean(fe)))
    return statistics.mean(err), per, len(err)


def permute(rows, seed, strata):
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    by = defaultdict(list)
    for r in out:
        by[tuple(r[k] for k in strata)].append(r)
    for _, rs in by.items():
        labs = [r["lt24"] for r in rs]
        rng.shuffle(labs)
        for r, l in zip(rs, labs):
            r["lt24"] = l
    return out


def main():
    rows = load()
    print("n rows", len(rows), " lt24 rows", sum(r["lt24"] for r in rows))
    base, _, n = chain(rows, False, None)
    il, _, _ = chain(rows, True, None)
    for mode in ("refit", "frozen"):
        noil, _, _ = chain(rows, False, mode)
        both, per, _ = chain(rows, True, mode)
        print(f"\n=== ARM = lt24-only, {mode} ===  scored n={n}")
        print(f"  no arm            {base:9.4f}")
        print(f"  TJ only           {noil:9.4f}   d vs no-arm {noil-base:+.4f}")
        print(f"  IL only           {il:9.4f}")
        print(f"  IL + TJ           {both:9.4f}   INCREMENT over IL {both-il:+.4f}")
        print("  folds improved vs IL-only:", end=" ")
        ilper = chain(rows, True, None)[1]
        print(f"{sum(1 for (a, b) in zip(per, ilper) if a[2] < b[2])}/{len(per)}")
        for sname, strata in (("season", ("season",)),
                              ("season x IL", ("season", "il4"))):
            nul = []
            for s in range(1, 121):
                m, _, _ = chain(permute(rows, s, strata), True, mode)
                nul.append(m - il)
            for k in (40, 60, 120):
                sub = sorted(nul[:k])
                mx = max(abs(x) for x in sub)
                d = both - il
                print(f"  NULL[{sname}] {k:>3} draws: mean {statistics.mean(sub):+.4f}"
                      f" sd {statistics.pstdev(sub):.4f}"
                      f" null95 [{sub[max(0,int(.025*k))]:+.4f},{sub[min(k-1,int(.975*k))]:+.4f}]"
                      f" max|d| {mx:.4f}  SNR {abs(d)/mx:.2f}x")
        # player-clustered bootstrap of the increment
        byp = defaultdict(list)
        for r in rows:
            byp[r["mlbam"]].append(r)
        keys = list(byp)
        rng = random.Random(23)
        dd = []
        for _ in range(300):
            dr = [q for _ in range(len(keys))
                  for q in byp[keys[rng.randrange(len(keys))]]]
            a, _, _ = chain(dr, True, None)
            b, _, _ = chain(dr, True, mode)
            dd.append(b - a)
        dd.sort()
        print(f"  BOOTSTRAP (player clusters, refit) mean {statistics.mean(dd):+.4f}"
              f" CI95 [{dd[int(.025*len(dd))]:+.4f},{dd[int(.975*len(dd))]:+.4f}]"
              f" P(improves) {sum(1 for x in dd if x < 0)/len(dd):.3f}")


if __name__ == "__main__":
    main()
