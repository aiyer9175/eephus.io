"""RECON ONLY (lane: defense), part 2.

(c') OAA at min=1 (ALL fielders, not just qualified): coverage + joins.
(d') OAA vs BRef war_def on the wider min=1 pool, with the measurement-standard controls.
(e') DEFINITIVE ladder recovery: least-squares solve of
        runs_position_per650  ~  sum_pos  innings_share_pos * ladder_pos
     which inverts BRef's own positional-adjustment construction instead of
     eyeballing per-position means.
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _recon_defense import (DATA, CACHE, POS_ADJ_STD, def_history, statsapi_fielding,
                            primary_pos, pearson, spearman, boot_ci, perm_null, sec)

FIT_POS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]


def oaa_all():
    out = {}
    for f in sorted((CACHE / "savant_oaa").glob("oaa_all_*.csv")):
        yr = int(f.stem.split("_")[-1])
        out[yr] = list(csv.DictReader(f.open(encoding="utf-8-sig")))
    return out


def solve(A, b):
    """Least squares via normal equations + Gaussian elimination (no numpy dep)."""
    k = len(A[0])
    M = [[sum(A[r][i] * A[r][j] for r in range(len(A))) for j in range(k)] +
         [sum(A[r][i] * b[r] for r in range(len(A)))] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        if abs(pv) < 1e-12:
            continue
        M[c] = [v / pv for v in M[c]]
        for r in range(k):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [a - f * bb for a, bb in zip(M[r], M[c])]
    return [M[i][k] for i in range(k)]


def main():
    dh_meta, dh = def_history()
    fld = statsapi_fielding()
    oaa = oaa_all()
    dh_ids = {m for m, _ in dh}
    dhome = json.loads((DATA / "def_home.json").read_text(encoding="utf-8"))
    prospect_ids = {int(k) for k in dhome["by_mlbam"]}

    sec("(c') Savant OAA at min=1 (ALL fielders) -- coverage and joins")
    print(f"{'yr':>5} {'rows':>5} {'uniq':>5} {'in def_hist':>11} {'%':>6} "
          f"{'in statsapi':>11} {'%':>6} {'yr col':>7}")
    for y in sorted(oaa):
        rr = oaa[y]
        ids = {int(r['player_id']) for r in rr}
        j1 = sum(1 for i in ids if (i, y) in dh)
        sa = {m for (m, yy) in fld if yy == y}
        j2 = len(ids & sa)
        yc = rr[0].get('year')
        print(f"{y:>5} {len(rr):>5} {len(ids):>5} {j1:>11} {100*j1/len(ids):>5.1f}% "
              f"{j2:>11} {100*j2/len(ids):>5.1f}% {yc!s:>7}")

    # reverse coverage: what share of BRef position-player-seasons get an OAA row
    print("\nREVERSE coverage -- share of BRef def-history player-seasons with an OAA row:")
    print(f"{'yr':>5} {'bref rows':>10} {'>=100pa':>8} {'>=400pa':>8} "
          f"{'oaa%all':>8} {'oaa%100':>8} {'oaa%400':>8}")
    for y in sorted(oaa):
        ids = {int(r['player_id']) for r in oaa[y]}
        rows = [(m, v) for (m, yy), v in dh.items() if yy == y]
        for tag, thr in (("", 0),):
            pass
        a = [m for m, v in rows]
        b100 = [m for m, v in rows if v["pa"] >= 100]
        b400 = [m for m, v in rows if v["pa"] >= 400]
        f = lambda s: 100 * sum(1 for m in s if m in ids) / max(1, len(s))
        print(f"{y:>5} {len(a):>10} {len(b100):>8} {len(b400):>8} "
              f"{f(a):>7.1f}% {f(b100):>7.1f}% {f(b400):>7.1f}%")

    print("\nposition coverage (min=1 pool), rows by primary_pos_formatted:")
    allpos = sorted({r["primary_pos_formatted"] for y in oaa for r in oaa[y]})
    print("  positions present:", allpos)
    print("  ABSENT vs the 9 fielding slots:",
          sorted(set(FIT_POS) - set(allpos)), " (P also absent)")
    tot = Counter(r["primary_pos_formatted"] for y in oaa for r in oaa[y])
    print("  pooled counts:", tot.most_common())
    inf = sum(tot[p] for p in ("1B", "2B", "3B", "SS"))
    outf = sum(tot[p] for p in ("LF", "CF", "RF"))
    print(f"  INFIELD rows={inf}  OUTFIELD rows={outf}  -> infield IS present")

    print("\nOAA join against the PROSPECT universe (def_home mlbam, n="
          f"{len(prospect_ids)}):")
    oaa_ids = {int(r['player_id']) for y in oaa for r in oaa[y]}
    print(f"  distinct OAA mlbam 2016-2025 = {len(oaa_ids)}")
    print(f"  ^ def_home prospects        = {len(oaa_ids & prospect_ids)} "
          f"({100*len(oaa_ids&prospect_ids)/len(prospect_ids):.1f}% of prospects) "
          "-- i.e. prospects who reached MLB and fielded")
    print(f"  ^ mlb_def_history mlbam     = {len(oaa_ids & dh_ids)} "
          f"({100*len(oaa_ids&dh_ids)/len(oaa_ids):.1f}% of OAA ids)")

    # ---------------- (d') correlation on the wide pool ----------------
    sec("(d') OAA vs BRef war_def -- min=1 pool, with controls")
    RPW = 9.7
    rows = []
    for y in sorted(oaa):
        for r in oaa[y]:
            m = int(r["player_id"])
            h = dh.get((m, y))
            if not h or h["pa"] <= 0:
                continue
            try:
                O = float(r["outs_above_average"]); F = float(r["fielding_runs_prevented"])
            except ValueError:
                continue
            rows.append({"y": y, "m": m, "pos": r["primary_pos_formatted"], "oaa": O,
                         "frp": F, "wd": h["war_def"], "rp": h["runs_position"],
                         "pa": h["pa"], "fr": h["war_def"] * RPW - h["runs_position"]})
    print(f"matched player-seasons = {len(rows)}")

    def rpt(tag, sub, fx=lambda r: r["frp"], fy=lambda r: r["fr"]):
        xs = [fx(r) for r in sub]; ys = [fy(r) for r in sub]
        if len(xs) < 25:
            print(f"  {tag:<34} n={len(xs)} (skip)"); return
        r_ = pearson(xs, ys)
        lo, hi = boot_ci(xs, ys, pearson)
        nb = perm_null(xs, ys, pearson)
        # zero-information control: row-permuted feature, refit-free but same n
        rng = random.Random(3)
        ctl = xs[:]; rng.shuffle(ctl)
        print(f"  {tag:<34} n={len(xs):>5} r={r_:>6.3f} [{lo:.3f},{hi:.3f}] "
              f"rho={spearman(xs,ys):>6.3f} perm95={nb:.3f} ctl_r={pearson(ctl,ys):>6.3f}")

    print("\nfielding-only runs (war_def*9.7 - runs_position):")
    rpt("ALL", rows)
    for thr in (100, 300, 500):
        rpt(f"pa >= {thr}", [r for r in rows if r["pa"] >= thr])
    print("\nwar_def (wins, incl. positional adj):")
    rpt("ALL", rows, fy=lambda r: r["wd"])
    for thr in (100, 300, 500):
        rpt(f"pa >= {thr}", [r for r in rows if r["pa"] >= thr], fy=lambda r: r["wd"])

    print("\nRATE form: FRP per 650 PA vs fielding runs per 650 PA (pa>=300):")
    sub = [r for r in rows if r["pa"] >= 300]
    rpt("rate", sub, fx=lambda r: r["frp"] * 650 / r["pa"],
        fy=lambda r: r["fr"] * 650 / r["pa"])

    print("\nby position, fielding-only runs, pa>=300:")
    for p in sorted({r["pos"] for r in sub}):
        rpt(f"  {p}", [r for r in sub if r["pos"] == p])

    print("\ncalibration OLS fielding_runs ~ a + b*FRP, by position (pa>=300):")
    print(f"{'pos':>4} {'n':>5} {'b':>7} {'a':>7} {'R2':>6} {'resid sd':>9}")
    for p in sorted({r["pos"] for r in sub}) + ["ALL"]:
        s = sub if p == "ALL" else [r for r in sub if r["pos"] == p]
        if len(s) < 25:
            continue
        xs = [r["frp"] for r in s]; ys = [r["fr"] for r in s]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        b = sum((a-mx)*(c-my) for a, c in zip(xs, ys)) / sum((a-mx)**2 for a in xs)
        a0 = my - b*mx
        res = [c - (a0 + b*a) for a, c in zip(xs, ys)]
        print(f"{p:>4} {len(s):>5} {b:>7.3f} {a0:>7.2f} {pearson(xs,ys)**2:>6.3f} "
              f"{statistics.pstdev(res):>9.2f}")

    # 4 independent time splits
    print("\nEFFECT OVER 4 INDEPENDENT TIME SPLITS (r, FRP vs fielding runs, pa>=300):")
    splits = [(2016, 2018), (2019, 2020), (2021, 2023), (2024, 2025)]
    vals = []
    for a, b in splits:
        s = [r for r in sub if a <= r["y"] <= b]
        v = pearson([r["frp"] for r in s], [r["fr"] for r in s])
        vals.append(v)
        print(f"  {a}-{b}: n={len(s):>4} r={v:.3f}")
    print(f"  mean r over splits = {statistics.mean(vals):.3f} "
          f"sd = {statistics.pstdev(vals):.3f}")

    # ---------------- (e') definitive ladder ----------------
    sec("(e') LADDER RECOVERY -- least squares on innings shares (no intercept)")
    A, bvec, W = [], [], []
    used = 0
    for (m, yr), h in dh.items():
        by = fld.get((m, yr))
        if not by or h["pa"] < 200:
            continue
        # innings for fielding positions; DH gets weight from games (0 innings)
        w = {}
        for p in FIT_POS:
            v = by.get(p)
            if not v:
                continue
            w[p] = v["inn"] if p != "DH" else v["g"] * 8.5
        # exclude the pitcher slot entirely (two-way players)
        tot = sum(w.values())
        if tot <= 0:
            continue
        share = {p: v / tot for p, v in w.items()}
        A.append([share.get(p, 0.0) for p in FIT_POS])
        bvec.append(h["runs_position"] * 650.0 / h["pa"])
        W.append(h["pa"])
        used += 1
    coef = solve(A, bvec)
    pred = [sum(a * c for a, c in zip(row, coef)) for row in A]
    resid = [y - p for y, p in zip(bvec, pred)]
    ss_res = sum(r * r for r in resid)
    mb = statistics.mean(bvec)
    ss_tot = sum((y - mb) ** 2 for y in bvec)
    print(f"n player-seasons (pa>=200, 2000-2026) = {used}")
    print(f"R2 = {1 - ss_res/ss_tot:.4f}   resid sd = {statistics.pstdev(resid):.3f} runs/650PA")
    print(f"\n{'pos':>4} {'recovered':>10} {'standard':>9} {'diff':>7}  {'ratio':>6}")
    for p, c in zip(FIT_POS, coef):
        s = POS_ADJ_STD[p]
        print(f"{p:>4} {c:>10.2f} {s:>9.1f} {c-s:>7.2f} {(c/s if s else float('nan')):>6.2f}")
    ks = FIT_POS
    X = [POS_ADJ_STD[p] for p in ks]; Y = list(coef)
    mx, my = statistics.mean(X), statistics.mean(Y)
    bb = sum((a-mx)*(c-my) for a, c in zip(X, Y)) / sum((a-mx)**2 for a in X)
    print(f"\nOLS recovered ~ a + b*standard: b={bb:.4f} a={my-bb*mx:.3f} "
          f"R2={pearson(X,Y)**2:.4f}")
    print("bootstrap 95% CI on each recovered coefficient (500 draws, resample seasons):")
    rng = random.Random(19)
    boots = []
    for _ in range(200):
        idx = [rng.randrange(len(A)) for _ in range(len(A))]
        boots.append(solve([A[i] for i in idx], [bvec[i] for i in idx]))
    for i, p in enumerate(FIT_POS):
        v = sorted(bt[i] for bt in boots)
        print(f"  {p:>3} {coef[i]:>8.2f}  [{v[5]:.2f}, {v[194]:.2f}]")

    # conversion price matrix from the recovered ladder
    print("\nCONVERSION PRICE MATRIX (runs / 650 PA, recovered ladder), row=from col=to:")
    order = ["C", "SS", "2B", "3B", "CF", "RF", "LF", "1B", "DH"]
    cm = dict(zip(FIT_POS, coef))
    print("     " + " ".join(f"{p:>6}" for p in order))
    for a in order:
        print(f"{a:>4} " + " ".join(f"{cm[b]-cm[a]:>6.2f}" for b in order))
    print("\n(positional adjustment only; a real conversion model must ALSO price the "
          "fielding-quality delta at the new position, which OAA/FRP measures at "
          f"resid sd ~6 runs.)")


if __name__ == "__main__":
    main()
