"""LANE newdata (d): does draft_bonus.py's signing bonus / slot money add
anything OVER pick_overall, which the draft models already carry?

PRE-REGISTERED HYPOTHESES
  H-D1  Signing bonus RESIDUALIZED on pick number (log bonus minus its
        pick-conditional expectation, fit on strictly prior draft classes)
        predicts reaching the majors beyond pick number alone. Rationale: a
        pick that signs well over its pick-implied money was ranked higher by
        the club than the slot it fell to (leverage / underslot-elsewhere
        deals), so bonus is a market-revealed scouting signal.
  H-D2  pool_pct (bonus / assigned slot) does the same on the slotted subset
        (rounds 1-10 + comp picks), which is where slot money exists.
  H-D3  Among players who DID debut, the same residual predicts a SHORTER
        time to debut -- the ETA-relevant form.

CONFOUND HANDLED EXPLICITLY (the lane brief names it): bonus is mechanically
a near-deterministic function of pick number. Every test below measures the
INCREMENT over a pick-only baseline that is refit on the same folds, never the
marginal correlation of bonus with the outcome.

SELECTION HANDLED EXPLICITLY: unsigned picks have no bonus AND can never
debut for that club, so a naive "bonus present" pool would smuggle the
signing decision in as the signal. Primary pool = SIGNED picks only
(bonus_usd present). The unsigned rate is reported, not modelled.

PASS CRITERIA (set before running, all required)
  (1) mean AUC gain > 0 on >= 4 of the forward-chained class folds,
  (2) gain outside the zero-information null band -- the SAME bonus-residual
      column row-permuted WITHIN draft class, 60 draws, refit every draw,
  (3) paired bootstrap (resample within class, refit both models per draw)
      CI95 excluding 0.
"""
import sys, os, json, io, math, random, statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")

DB = json.load(io.open(os.path.join(ROOT, "data", "draft_bonus_slot.json"),
                       encoding="utf-8"))
PEOPLE = json.load(io.open(os.path.join(SCRATCH, "nd_people.json"),
                           encoding="utf-8"))

K_YEARS = 4                       # debut within K seasons of the draft
CLASSES = (2017, 2018, 2019, 2020, 2021, 2022)
FOLDS = (2019, 2020, 2021, 2022)  # train strictly on prior classes


def build():
    rows = []
    for mid, v in DB.items():
        y = v["year"]
        if y not in CLASSES:
            continue
        b = v.get("bonus_usd")
        if not b or b <= 0:          # unsigned / unknown -> excluded (see docstring)
            continue
        p = v.get("pick_overall")
        if not p or p <= 0:
            continue
        info = PEOPLE.get(mid) or {}
        dd = info.get("debut")
        dyr = int(dd[:4]) if dd else None
        rows.append({
            "mlbam": mid, "year": y, "pick": float(p),
            "logpick": math.log(float(p)),
            "logbonus": math.log(float(b)),
            "slot": v.get("slot_usd"),
            "pool_pct": v.get("pool_pct"),
            "round": v.get("round"),
            "debut_year": dyr,
            "y": 1 if (dyr is not None and dyr - y <= K_YEARS) else 0,
            "yrs": (dyr - y) if dyr is not None else None,
            "pos": (info.get("pos") or "?"),
        })
    return rows


def unsigned_stats():
    tot = sig = 0
    for mid, v in DB.items():
        if v["year"] not in CLASSES:
            continue
        tot += 1
        if v.get("bonus_usd"):
            sig += 1
    return tot, sig


# ---------------------------------------------------------------- logistic
import numpy as np


def logit_fit(X, y, l2=1.0, iters=60):
    """Newton / IRLS with ridge on standardized columns."""
    A = np.asarray(X, dtype=float)
    yv = np.asarray(y, dtype=float)
    mu = A.mean(axis=0)
    sd = A.std(axis=0)
    sd[sd < 1e-12] = 1.0
    Z = np.hstack([np.ones((len(A), 1)), (A - mu) / sd])
    p = Z.shape[1]
    w = np.zeros(p)
    w[0] = math.log(max(1e-6, yv.sum()) / max(1e-6, len(yv) - yv.sum()))
    R = np.eye(p) * l2
    R[0, 0] = 0.0
    for _ in range(iters):
        z = np.clip(Z @ w, -30, 30)
        pr = 1.0 / (1.0 + np.exp(-z))
        g = Z.T @ (pr - yv) + R @ w
        W = pr * (1 - pr) + 1e-9
        H = Z.T @ (Z * W[:, None]) + R
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        w = w - step
        if np.max(np.abs(step)) < 1e-8:
            break
    return {"w": w, "mu": mu, "sd": sd}


def logit_pred_many(m, X):
    A = np.asarray(X, dtype=float)
    Z = np.hstack([np.ones((len(A), 1)), (A - m["mu"]) / m["sd"]])
    return 1.0 / (1.0 + np.exp(-np.clip(Z @ m["w"], -30, 30)))


def auc(scores, labels):
    pairs = sorted(zip(scores, labels))
    n1 = sum(labels)
    n0 = len(labels) - n1
    if not n1 or not n0:
        return float("nan")
    # rank-based (ties averaged)
    ranks, i = [0.0] * len(pairs), 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = r
        i = j + 1
    s1 = sum(r for r, (_, l) in zip(ranks, pairs) if l == 1)
    return (s1 - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def brier(scores, labels):
    return statistics.mean((s - l) ** 2 for s, l in zip(scores, labels))


# ------------------------------------------------- bonus residual on pick
def add_resid(rows, train, key="logbonus", out="bres"):
    """E[log bonus | pick] as a quadratic in log(pick), fit on TRAIN only."""
    X = [[r["logpick"], r["logpick"] ** 2] for r in train]
    y = [r[key] for r in train]
    mu = [statistics.mean(c) for c in zip(*X)]
    sd = [statistics.pstdev(c) or 1.0 for c in zip(*X)]
    Z = [[(v - m) / s for v, m, s in zip(r, mu, sd)] for r in X]
    ybar = statistics.mean(y)
    A = [[sum(Z[i][a] * Z[i][b] for i in range(len(Z))) + (0.5 if a == b else 0)
          for b in range(2)] for a in range(2)]
    B = [sum(Z[i][a] * (y[i] - ybar) for i in range(len(Z))) for a in range(2)]
    det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
    if abs(det) < 1e-9:
        c = [0.0, 0.0]
    else:
        c = [(B[0] * A[1][1] - B[1] * A[0][1]) / det,
             (A[0][0] * B[1] - A[1][0] * B[0]) / det]
    for r in rows:
        xx = [r["logpick"], r["logpick"] ** 2]
        pred = ybar + sum(ci * ((v - m) / s) for ci, v, m, s in zip(c, xx, mu, sd))
        r[out] = r[key] - pred
    return c


def chain(rows, cand_keys, permute=None, folds=FOLDS):
    """Forward-chained by draft class. Returns per-fold (AUC base, AUC cand)."""
    rows = [dict(r) for r in rows]
    out = []
    for T in folds:
        tr = [r for r in rows if r["year"] < T]
        te = [r for r in rows if r["year"] == T]
        if len(tr) < 200 or len(te) < 50:
            continue
        add_resid(tr + te, tr)
        if permute is not None:
            # permute EVERY candidate column (the zero-information twin of the
            # exact columns under test), within draft class.
            rng = random.Random(permute * 1000 + T)
            for key in cand_keys:
                for grp in (tr, te):
                    vals = [r[key] for r in grp]
                    rng.shuffle(vals)
                    for r, v in zip(grp, vals):
                        r[key] = v
        yb = [r["y"] for r in tr]
        if sum(yb) < 10:
            continue
        mb = logit_fit([[r["logpick"]] for r in tr], yb)
        mc = logit_fit([[r["logpick"]] + [r[k] for k in cand_keys] for r in tr], yb)
        sb = list(logit_pred_many(mb, [[r["logpick"]] for r in te]))
        sc = list(logit_pred_many(
            mc, [[r["logpick"]] + [r[k] for k in cand_keys] for r in te]))
        yt = [r["y"] for r in te]
        out.append((T, len(te), sum(yt), auc(sb, yt), auc(sc, yt),
                    brier(sb, yt), brier(sc, yt)))
    return out


def report(name, rows, cand_keys, folds=FOLDS, nperm=60, nboot=200):
    print(f"\n===== {name}  (n={len(rows)}, base rate "
          f"{statistics.mean([r['y'] for r in rows]):.3f}) =====")
    res = chain(rows, cand_keys, folds=folds)
    if not res:
        print("  UNAVAILABLE - no fold had enough data")
        return
    print(f"  {'class':>6}{'n':>6}{'debuts':>8}{'AUCbase':>9}{'AUCcand':>9}"
          f"{'dAUC':>9}{'dBrier':>10}")
    for T, n, k, ab, ac, bb, bc in res:
        print(f"  {T:>6}{n:>6}{k:>8}{ab:>9.4f}{ac:>9.4f}{ac-ab:>+9.4f}{bc-bb:>+10.5f}")
    d = statistics.mean(ac - ab for _, _, _, ab, ac, _, _ in res)
    db = statistics.mean(bc - bb for _, _, _, _, _, bb, bc in res)
    imp = sum(1 for _, _, _, ab, ac, _, _ in res if ac > ab)
    print(f"  MEAN dAUC {d:+.4f}   mean dBrier {db:+.5f}   folds improved {imp}/{len(res)}")

    nul = []
    for s in range(1, nperm + 1):
        r2 = chain(rows, cand_keys, permute=s, folds=folds)
        if r2:
            nul.append(statistics.mean(ac - ab for _, _, _, ab, ac, _, _ in r2))
    nul.sort()
    print(f"  ZERO-INFO CONTROL (bonus residual permuted within class, "
          f"{len(nul)} draws)")
    print(f"    null mean {statistics.mean(nul):+.4f} sd {statistics.pstdev(nul):.4f}"
          f"  null95 [{nul[1]:+.4f},{nul[-2]:+.4f}]  max|d| {max(abs(x) for x in nul):.4f}")
    print(f"    observed {d:+.4f} -> outside null band: "
          f"{d > max(abs(x) for x in nul)}")

    rng = random.Random(97)
    by = defaultdict(list)
    for r in rows:
        by[r["year"]].append(r)
    bs = []
    for _ in range(nboot):
        draw = []
        for yv, rs in by.items():
            k = len(rs)
            draw += [rs[rng.randrange(k)] for _ in range(k)]
        r2 = chain(draw, cand_keys, folds=folds)
        if r2:
            bs.append(statistics.mean(ac - ab for _, _, _, ab, ac, _, _ in r2))
    bs.sort()
    if bs:
        print(f"  PAIRED BOOTSTRAP (refit per draw, {len(bs)}): dAUC "
              f"{statistics.mean(bs):+.4f} sd {statistics.pstdev(bs):.4f} "
              f"CI95 [{bs[int(.025*len(bs))]:+.4f},{bs[int(.975*len(bs))]:+.4f}] "
              f"P(gain>0) {sum(1 for x in bs if x>0)/len(bs):.3f}")


def spearman(a, b):
    def rk(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            m = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[s[k]] = m
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    dbb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return num / (da * dbb) if da and dbb else float("nan")


def main():
    tot, sig = unsigned_stats()
    print(f"draft picks {CLASSES[0]}-{CLASSES[-1]}: {tot}  with a signing bonus "
          f"{sig} ({sig/tot:.3f})  -> unsigned/unknown {tot-sig} EXCLUDED")
    rows = build()
    by = defaultdict(int)
    for r in rows:
        by[r["year"]] += 1
    print("signed pool by class", dict(sorted(by.items())))
    print(f"debuted within {K_YEARS}y: "
          f"{sum(r['y'] for r in rows)} / {len(rows)}")

    # collinearity read: how much of log bonus does pick already explain?
    add_resid(rows, rows)
    lb = [r["logbonus"] for r in rows]
    lp = [r["logpick"] for r in rows]
    print(f"\nCOLLINEARITY  Spearman(log bonus, log pick) = {spearman(lb, lp):+.4f}")
    var_b = statistics.pvariance(lb)
    var_r = statistics.pvariance([r["bres"] for r in rows])
    print(f"  var(log bonus) {var_b:.4f}  var(residual on pick) {var_r:.4f}"
          f"  -> pick explains {1 - var_r/var_b:.3f} of log-bonus variance")

    report("H-D1 bonus residual on pick, FULL signed pool", rows, ["bres"])

    slot = [r for r in rows if r.get("pool_pct")]
    print(f"\n(slotted subset for H-D2: n={len(slot)})")
    for r in slot:
        r["ppct"] = float(r["pool_pct"])
    report("H-D2 pool_pct (bonus/slot) on the slotted subset", slot, ["ppct"])

    # H-D3 ETA form: years to debut among the debuted
    print("\n===== H-D3 years-to-debut among DEBUTED (selection-conditioned) =====")
    deb = [r for r in rows if r["yrs"] is not None]
    print(f"  n debuted {len(deb)}")
    add_resid(deb, deb)
    print(f"  Spearman(years-to-debut, log pick)        {spearman([r['yrs'] for r in deb], [r['logpick'] for r in deb]):+.4f}")
    print(f"  Spearman(years-to-debut, bonus residual)  {spearman([r['yrs'] for r in deb], [r['bres'] for r in deb]):+.4f}")
    # partial: residualize years on pick first, forward-chained per class
    print(f"  {'class':>6}{'n':>5}{'rho(yrs_resid, bonus_resid)':>30}")
    rr = []
    for T in CLASSES:
        tr = [r for r in deb if r["year"] < T]
        te = [r for r in deb if r["year"] == T]
        if len(tr) < 60 or len(te) < 25:
            continue
        add_resid(tr + te, tr)
        # years residual on pick, fit on train
        X = [[r["logpick"]] for r in tr]
        ybar = statistics.mean([r["yrs"] for r in tr])
        xm = statistics.mean([x[0] for x in X])
        sxy = sum((x[0] - xm) * (r["yrs"] - ybar) for x, r in zip(X, tr))
        sxx = sum((x[0] - xm) ** 2 for x in X) or 1.0
        sl = sxy / sxx
        res = [r["yrs"] - (ybar + sl * (r["logpick"] - xm)) for r in te]
        rho = spearman(res, [r["bres"] for r in te])
        rr.append(rho)
        print(f"  {T:>6}{len(te):>5}{rho:>30.4f}")
    if rr:
        print(f"  mean rho {statistics.mean(rr):+.4f}  (negative = more money -> faster)")
        # permutation null on the same statistic
        nul = []
        for s in range(1, 201):
            rng = random.Random(s)
            vals = []
            for T in CLASSES:
                tr = [r for r in deb if r["year"] < T]
                te = [r for r in deb if r["year"] == T]
                if len(tr) < 60 or len(te) < 25:
                    continue
                add_resid(tr + te, tr)
                X = [[r["logpick"]] for r in tr]
                ybar = statistics.mean([r["yrs"] for r in tr])
                xm = statistics.mean([x[0] for x in X])
                sxy = sum((x[0] - xm) * (r["yrs"] - ybar) for x, r in zip(X, tr))
                sxx = sum((x[0] - xm) ** 2 for x in X) or 1.0
                sl = sxy / sxx
                res = [r["yrs"] - (ybar + sl * (r["logpick"] - xm)) for r in te]
                bb = [r["bres"] for r in te]
                rng.shuffle(bb)
                vals.append(spearman(res, bb))
            nul.append(statistics.mean(vals))
        nul.sort()
        print(f"  ZERO-INFO null: mean {statistics.mean(nul):+.4f} "
              f"sd {statistics.pstdev(nul):.4f} null95 "
              f"[{nul[4]:+.4f},{nul[-5]:+.4f}] max|d| {max(abs(x) for x in nul):.4f}")


if __name__ == "__main__":
    main()
