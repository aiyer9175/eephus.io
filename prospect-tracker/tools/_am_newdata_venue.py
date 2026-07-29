"""LANE newdata (b): does venue_meta.py structural metadata improve the
registered MiLB park-factor layer (milb_park_factors / park_shrink)?

PRE-REGISTERED HYPOTHESES
  H-B1  Venue STRUCTURE (outfield dimensions, roof, turf, latitude, longitude)
        explains a nonzero share of the measured team-season run_pf / hr_pf.
        Test: forward-chained ridge, out-of-sample Pearson r and MAE against
        the observed PF, vs a "predict 1.0" baseline.
  H-B2  A venue-meta prediction is a better EB SHRINKAGE TARGET than 1.0 for a
        venue's NEXT season PF. This is the operational use: the incumbent
        shrinks a thin venue's factor toward the league mean; if structure
        carries information, thin venues should shrink toward their structural
        expectation instead.

PRE-REGISTERED PASS CRITERIA (all three required)
  (1) improvement in >= 4 of the forward folds,
  (2) pooled delta outside the zero-information null band -- the SAME venue
      metadata columns permuted ACROSS venue ids, 60 draws, refit each time,
  (3) cluster (by venue) paired bootstrap CI95 excluding 0, refit per draw.

KNOWN COVERAGE LIMIT measured before running: elevation_ft lands on only 5 of
the 188 venues that overlap the park-factor panel, so ELEVATION IS EXCLUDED --
the single most physically obvious park variable is not testable here. lat/lon
(167/228 filled) is carried as its geographic proxy.
"""
import sys, os, json, math, random, statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PF = json.load(open(os.path.join(ROOT, "data", "milb_park_factors.json")))
VM = json.load(open(os.path.join(ROOT, "data", "venue_meta.json")))

TARGETS = ("run_pf", "hr_pf")
FOLDS = (2022, 2023, 2024, 2025, 2026)


def feats(vid):
    v = VM.get(str(vid))
    if not v:
        return None
    d = v.get("dims") or {}
    ll, cf, rl = d.get("leftLine"), d.get("center"), d.get("rightLine")
    if not (ll and cf and rl):
        return None
    lat, lon = v.get("lat"), v.get("lon")
    if lat is None or lon is None:
        return None
    lc = d.get("leftCenter") or (ll + cf) / 2.0
    rc = d.get("rightCenter") or (rl + cf) / 2.0
    mean_d = (ll + lc + cf + rc + rl) / 5.0
    return [
        float(ll), float(cf), float(rl), float(mean_d),
        float(abs(ll - rl)),                       # LF/RF asymmetry
        1.0 if v.get("roof") != "Open" else 0.0,
        1.0 if v.get("turf") != "Grass" else 0.0,
        float(lat), float(lon),
        float(v.get("capacity") or 0) / 1000.0,
    ]


FNAMES = ("leftLine", "center", "rightLine", "mean_dist", "lr_asym",
          "roofed", "turf", "lat", "lon", "cap_k")


def ridge(X, y, lam=1.0):
    """Standardized ridge with intercept, solved by Gauss-Jordan."""
    p = len(X[0])
    mu = [statistics.mean(c) for c in zip(*X)]
    sd = [statistics.pstdev(c) or 1.0 for c in zip(*X)]
    Z = [[(r[j] - mu[j]) / sd[j] for j in range(p)] for r in X]
    ybar = statistics.mean(y)
    yc = [v - ybar for v in y]
    A = [[sum(Z[i][a] * Z[i][b] for i in range(len(Z))) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    B = [sum(Z[i][a] * yc[i] for i in range(len(Z))) for a in range(p)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-12:
            return ybar, mu, sd, [0.0] * p
        A[c], A[piv] = A[piv], A[c]
        B[c], B[piv] = B[piv], B[c]
        d = A[c][c]
        A[c] = [x / d for x in A[c]]
        B[c] /= d
        for r in range(p):
            if r != c and A[r][c]:
                f = A[r][c]
                A[r] = [x - f * yy for x, yy in zip(A[r], A[c])]
                B[r] -= f * B[c]
    return ybar, mu, sd, B


def predict(model, x):
    ybar, mu, sd, coef = model
    return ybar + sum(c * ((v - m) / s) for c, v, m, s in zip(coef, x, mu, sd))


def pearson(a, b):
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def build(target):
    rows = []
    for t in PF["team_seasons"]:
        y = t.get(target)
        if y is None:
            continue
        f = feats(t["venue_id"])
        if f is None:
            continue
        rows.append({"season": int(t["season"]), "venue": int(t["venue_id"]),
                     "level": t["level"], "y": float(y), "x": f})
    return rows


def prior_mean(rows, venue, before, K):
    """EB estimate of a venue's PF from strictly prior seasons, shrunk to 1.0."""
    hs = [r["y"] for r in rows if r["venue"] == venue and r["season"] < before]
    n = len(hs)
    if not n:
        return 1.0, 0
    return (n * statistics.mean(hs) + K * 1.0) / (n + K), n


def prior_mean_to(rows, venue, before, K, target):
    hs = [r["y"] for r in rows if r["venue"] == venue and r["season"] < before]
    n = len(hs)
    if not n:
        return target, 0
    return (n * statistics.mean(hs) + K * target) / (n + K), n


def run(target, K=1.0, permute_seed=None, sample=None, verbose=True):
    rows = build(target)
    if sample is not None:
        rows = sample
    if permute_seed is not None:
        rng = random.Random(permute_seed)
        vids = sorted({r["venue"] for r in rows})
        shuf = vids[:]
        rng.shuffle(shuf)
        remap = dict(zip(vids, shuf))
        xs = {r["venue"]: r["x"] for r in rows}
        rows = [dict(r, x=xs[remap[r["venue"]]]) for r in rows]

    out = {"base": [], "meta": [], "cand": [], "y": [], "thin": [],
           "per": [], "r_meta": []}
    for T in FOLDS:
        tr = [r for r in rows if r["season"] < T]
        te = [r for r in rows if r["season"] == T]
        if len(tr) < 100 or not te:
            continue
        # H-B1 model: venue structure -> PF, fit on strictly prior seasons
        m = ridge([r["x"] for r in tr], [r["y"] for r in tr], lam=5.0)
        b_e, c_e, m_e, ys, mp = [], [], [], [], []
        for r in te:
            pm = predict(m, r["x"])
            pm = max(0.80, min(1.20, pm))
            base, n = prior_mean(rows, r["venue"], T, K)
            cand, _ = prior_mean_to(rows, r["venue"], T, K, pm)
            b_e.append(abs(base - r["y"]))
            c_e.append(abs(cand - r["y"]))
            m_e.append(abs(pm - r["y"]))
            ys.append(r["y"])
            mp.append(pm)
            out["thin"].append(n)
        out["base"] += b_e
        out["cand"] += c_e
        out["meta"] += m_e
        out["y"] += ys
        out["r_meta"].append(pearson(mp, ys))
        out["per"].append((T, len(te), statistics.mean(b_e),
                           statistics.mean(c_e), statistics.mean(m_e),
                           pearson(mp, ys)))
    return out


def summarize(target, K):
    o = run(target, K)
    n = len(o["base"])
    b, c, m = (statistics.mean(o["base"]), statistics.mean(o["cand"]),
               statistics.mean(o["meta"]))
    print(f"\n=== {target}  (EB pseudo-seasons K={K})  n={n} scored team-seasons ===")
    print(f"  H-B1 venue-meta-only MAE      {m:.4f}   "
          f"(predict-1.0 MAE {statistics.mean([abs(1.0-y) for y in o['y']]):.4f})")
    print(f"  H-B1 out-of-sample Pearson r  per fold "
          f"{[round(x,3) for x in o['r_meta']]}")
    print(f"  H-B2 baseline (shrink->1.0)   MAE {b:.4f}")
    print(f"  H-B2 candidate (shrink->meta) MAE {c:.4f}   delta {c-b:+.5f}")
    print(f"  {'fold':>6}{'n':>5}{'base':>9}{'cand':>9}{'delta':>9}{'metaMAE':>9}{'r':>8}")
    imp = 0
    for T, k, x, y, mm, rr in o["per"]:
        imp += (y < x)
        print(f"  {T:>6}{k:>5}{x:>9.4f}{y:>9.4f}{y-x:>+9.5f}{mm:>9.4f}{rr:>8.3f}")
    print(f"  folds improved {imp}/{len(o['per'])}")

    # thin-venue slice: the case the prior is supposed to help
    idx = [i for i, t in enumerate(o["thin"]) if t <= 1]
    if idx:
        tb = statistics.mean([o["base"][i] for i in idx])
        tc = statistics.mean([o["cand"][i] for i in idx])
        print(f"  THIN slice (<=1 prior season, n={len(idx)}): "
              f"base {tb:.4f} cand {tc:.4f} delta {tc-tb:+.5f}")

    print("  zero-information control: venue metadata rows permuted ACROSS "
          "venue ids (60 draws, refit each)")
    d = sorted(statistics.mean(run(target, K, permute_seed=s)["cand"]) - b
               for s in range(1, 61))
    print(f"    null mean {statistics.mean(d):+.5f} sd {statistics.pstdev(d):.5f}"
          f"  null95 [{d[1]:+.5f},{d[-2]:+.5f}]  max|d| {max(abs(x) for x in d):.5f}")
    verdict = abs(c - b) > max(abs(x) for x in d) and c < b
    print(f"    observed delta {c-b:+.5f}  -> outside null band: {verdict}")
    return c - b, max(abs(x) for x in d), o


def main():
    print("venue_meta coverage on the park panel:")
    ts = PF["team_seasons"]
    have = sum(1 for t in ts if feats(t["venue_id"]) is not None)
    print(f"  team-seasons with usable venue features {have}/{len(ts)}")
    vids = {t["venue_id"] for t in ts}
    print(f"  venues in panel {len(vids)}, with features "
          f"{sum(1 for v in vids if feats(v) is not None)}")
    print(f"  elevation_ft on panel venues: "
          f"{sum(1 for v in vids if (VM.get(str(v)) or {}).get('elevation_ft') is not None)}"
          f" -> EXCLUDED as a feature")

    for target in TARGETS:
        for K in (1.0, 3.0):
            summarize(target, K)

    # H-B1 direction read: what does the full-pool fit say each dim does?
    print("\n=== H-B1 full-pool standardized coefficients (direction sanity) ===")
    for target in TARGETS:
        rows = build(target)
        m = ridge([r["x"] for r in rows], [r["y"] for r in rows], lam=5.0)
        print(f"  {target}: " + "  ".join(
            f"{n}={c:+.4f}" for n, c in zip(FNAMES, m[3])))
        # in-sample R2 for scale
        pred = [predict(m, r["x"]) for r in rows]
        ys = [r["y"] for r in rows]
        ssr = sum((a - b) ** 2 for a, b in zip(pred, ys))
        sst = sum((y - statistics.mean(ys)) ** 2 for y in ys)
        print(f"    in-sample R2 {1 - ssr/sst:.4f}  (n={len(rows)})")

    # YoY stability of the measured factor -- the registered R-PARK gate
    print("\n=== measured-PF year-over-year stability (registered gate rho>=0.50) ===")
    for target in TARGETS:
        rows = build(target)
        by = defaultdict(dict)
        for r in rows:
            by[r["venue"]][r["season"]] = r["y"]
        a, b2 = [], []
        for v, ss in by.items():
            for s in ss:
                if s + 1 in ss:
                    a.append(ss[s])
                    b2.append(ss[s + 1])
        print(f"  {target}: n_pairs {len(a)}  Pearson r {pearson(a, b2):+.4f}")


if __name__ == "__main__":
    main()
