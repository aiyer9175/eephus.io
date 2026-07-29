"""LANE newdata (a-velo): does Tommy John history predict FASTBALL VELOCITY
change, beyond age?

SUBSTRATE (fetched here, cached to the scratchpad, nothing written into the
repo): Baseball Savant pitch-arsenals leaderboard, type=avg_speed, min=100,
2015-2026, keyed on the MLBAM `pitcher` id -- the same spine tj_surgery.py uses.
Velocity is the fastball read: ff_avg_speed, falling back to si_avg_speed then
fc_avg_speed when a pitcher throws no four-seamer.

PRE-REGISTERED HYPOTHESES
  H-V1  A surgery in the window between season t-1 and season t predicts a
        season-over-season fastball velocity DROP relative to the age-expected
        change. (Direction: negative. This is the ex-post read, and it is mostly
        a survivorship statement -- a pitcher who threw 100 pitches in BOTH t-1
        and t after a surgery is by construction a recoverer.)
  H-V2  The decision-relevant version: does a PRIOR surgery (strictly before
        season t) predict the t-1 -> t velocity change for pitchers who threw in
        both seasons, beyond age? Direction not pre-signed: the injury
        literature says post-TJ arms come back at or above prior velocity, so a
        POSITIVE coefficient is a real possibility and would be a null for
        "TJ = decline".
  H-V3  Does months-since-last-TJ have a monotone relationship to the velocity
        change (the recovery ramp)?

CONTROLS: forward-chained by season, a zero-information control (the TJ column
row-permuted within season), a permutation null band, and a paired bootstrap
with a refit per draw, clustered on pitcher.

SURVIVORSHIP, stated: this panel conditions on throwing >= 100 pitches in BOTH
seasons, so it cannot see the arms that never came back. It answers "given he
pitched again, what happened to the velocity", NOT "what does TJ do to a career".
The career-level version is the playing-time gate (tools/_fa_tj_gate.py), where
non-appearance is a zero row rather than a dropped row.
"""
import sys, os, csv, io, json, math, random, statistics, urllib.request
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
VELO_DIR = os.path.join(SCRATCH, "velo")
os.makedirs(VELO_DIR, exist_ok=True)

SEASONS = list(range(2015, 2027))
TJ = json.load(io.open(os.path.join(ROOT, "data", "tj_surgery.json"),
                       encoding="utf-8"))["players"]


def fetch(year):
    p = os.path.join(VELO_DIR, f"velo_{year}.csv")
    if os.path.exists(p) and os.path.getsize(p) > 1000:
        return p
    url = ("https://baseballsavant.mlb.com/leaderboard/pitch-arsenals?"
           f"year={year}&min=100&type=avg_speed&hand=&csv=true")
    req = urllib.request.Request(url, headers={"User-Agent": "eephus-io/1.0"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        data = fh.read()
    with open(p, "wb") as out:
        out.write(data)
    return p


def load():
    velo = defaultdict(dict)
    for y in SEASONS:
        try:
            p = fetch(y)
        except Exception as e:                                   # noqa: BLE001
            print(f"  {y}: fetch failed {e}")
            continue
        with io.open(p, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                pid = row.get("pitcher")
                if not pid:
                    continue
                v = None
                for k in ("ff_avg_speed", "si_avg_speed", "fc_avg_speed"):
                    if row.get(k):
                        try:
                            v = float(row[k])
                        except ValueError:
                            v = None
                        if v:
                            break
                if v:
                    velo[int(pid)][y] = v
    return velo


def tj_years(m):
    return sorted(s["year"] for s in (TJ.get(str(m)) or []))


def build(velo, bio):
    rows = []
    for m, ys in velo.items():
        surg = tj_years(m)
        for t in SEASONS[1:]:
            if t not in ys or (t - 1) not in ys:
                continue
            age = bio.get(m)
            if age is None:
                continue
            a = age + (t - 2026)          # age in season t (bio age is 2026-ref)
            prior = [s for s in surg if s < t]
            between = [s for s in surg if s in (t - 1, t)]
            rows.append({
                "m": m, "t": t, "age": float(a),
                "dv": ys[t] - ys[t - 1],
                "v_prev": ys[t - 1],
                "tj_prior": 1.0 if prior else 0.0,
                "tj_n": float(len(prior)),
                "tj_recent": 1.0 if (prior and t - max(prior) <= 2) else 0.0,
                "tj_between": 1.0 if between else 0.0,
                "yrs_since": float(t - max(prior)) if prior else 0.0,
            })
    return rows


def ridge(X, y, lam=1.0):
    A = np.asarray(X, float)
    yv = np.asarray(y, float)
    mu, sd = A.mean(0), A.std(0)
    sd[sd < 1e-12] = 1.0
    Z = np.hstack([np.ones((len(A), 1)), (A - mu) / sd])
    R = np.eye(Z.shape[1]) * lam
    R[0, 0] = 0.0
    return {"w": np.linalg.solve(Z.T @ Z + R, Z.T @ yv), "mu": mu, "sd": sd}


def pred(m, X):
    A = np.asarray(X, float)
    Z = np.hstack([np.ones((len(A), 1)), (A - m["mu"]) / m["sd"]])
    return Z @ m["w"]


def chain(rows, keys, permute=None, seed=0):
    rows = [dict(r) for r in rows]
    if permute:
        rng = random.Random(seed)
        by = defaultdict(list)
        for r in rows:
            by[r["t"]].append(r)
        for t, rs in by.items():
            for k in permute:
                vals = [r[k] for r in rs]
                rng.shuffle(vals)
                for r, v in zip(rs, vals):
                    r[k] = v
    err, per = [], []
    for T in SEASONS[3:]:
        tr = [r for r in rows if r["t"] < T]
        te = [r for r in rows if r["t"] == T]
        if len(tr) < 300 or len(te) < 50:
            continue
        mm = ridge([[r[k] for k in keys] for r in tr], [r["dv"] for r in tr])
        p = pred(mm, [[r[k] for k in keys] for r in te])
        e = [abs(a - r["dv"]) for a, r in zip(p, te)]
        err += e
        per.append((T, len(te), statistics.mean(e)))
    return (statistics.mean(err) if err else None), per, len(err)


def main():
    print("fetching Savant pitch-arsenals velocity 2015-2026 ...")
    velo = load()
    print(f"  velocity seasons loaded: "
          f"{ {y: sum(1 for v in velo.values() if y in v) for y in SEASONS} }")

    # ages from the StatsAPI people cache already fetched for the bonus lane,
    # topped up for any pitcher missing there.
    people = {}
    pp = os.path.join(SCRATCH, "nd_people.json")
    if os.path.exists(pp):
        people = json.load(io.open(pp, encoding="utf-8"))
    need = [m for m in velo if str(m) not in people]
    for k in range(0, len(need), 200):
        chunk = need[k:k + 200]
        url = ("https://statsapi.mlb.com/api/v1/people?personIds="
               + ",".join(str(x) for x in chunk))
        req = urllib.request.Request(url, headers={"User-Agent": "eephus-io/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as fh:
                d = json.loads(fh.read().decode("utf-8"))
        except Exception as e:                                   # noqa: BLE001
            print("  people batch failed", e)
            continue
        for p in d.get("people", []):
            people[str(p["id"])] = {"birth": p.get("birthDate")}
    bio = {}
    for m in velo:
        b = (people.get(str(m)) or {}).get("birth")
        if b:
            bio[m] = 2026 - int(b[:4])
    print(f"  pitchers with velocity {len(velo)}, with birth year {len(bio)}")

    rows = build(velo, bio)
    print(f"  panel rows (velo in BOTH t-1 and t) {len(rows)}, "
          f"pitchers {len({r['m'] for r in rows})}")
    print(f"  tj_prior rows {int(sum(r['tj_prior'] for r in rows))}, "
          f"tj_recent (<=2y) {int(sum(r['tj_recent'] for r in rows))}, "
          f"tj_between {int(sum(r['tj_between'] for r in rows))}")

    print("\n=== descriptive: mean season-over-season velocity change (mph) ===")
    for nm, sel in (("all", lambda r: True),
                    ("no TJ ever prior", lambda r: not r["tj_prior"]),
                    ("TJ prior (any)", lambda r: r["tj_prior"]),
                    ("TJ within prior 2y", lambda r: r["tj_recent"]),
                    ("surgery between t-1,t", lambda r: r["tj_between"])):
        s = [r for r in rows if sel(r)]
        if len(s) < 20:
            print(f"  {nm:<24} n={len(s):>5}  UNAVAILABLE")
            continue
        print(f"  {nm:<24} n={len(s):>5}  mean dv {statistics.mean([r['dv'] for r in s]):+.4f}"
              f"  median {statistics.median([r['dv'] for r in s]):+.4f}"
              f"  mean age {statistics.mean([r['age'] for r in s]):.1f}")
    print("  years-since-TJ ramp (rows with a prior surgery):")
    for k in range(1, 9):
        s = [r for r in rows if r["tj_prior"] and int(r["yrs_since"]) == k]
        if len(s) >= 15:
            print(f"    {k}y since: n={len(s):>4} mean dv "
                  f"{statistics.mean([r['dv'] for r in s]):+.4f}")

    print("\n=== H-V2 forward-chained MAE on the velocity change ===")
    arms = [
        ("age + v_prev (baseline)", ["age", "v_prev"], None),
        ("+ tj_prior", ["age", "v_prev", "tj_prior"], ["tj_prior"]),
        ("+ tj_recent", ["age", "v_prev", "tj_recent"], ["tj_recent"]),
        ("+ tj_prior + tj_recent + tj_n",
         ["age", "v_prev", "tj_prior", "tj_recent", "tj_n"],
         ["tj_prior", "tj_recent", "tj_n"]),
    ]
    res = {}
    for nm, keys, _ in arms:
        mae, per, n = chain(rows, keys)
        res[nm] = (mae, per, n)
        print(f"  {nm:<34} MAE {mae:.5f} n={n}  "
              + " ".join(f"{T}:{x:.3f}" for T, _, x in per))
    base = res["age + v_prev (baseline)"][0]
    bper = dict((T, x) for T, _, x in res["age + v_prev (baseline)"][1])
    for nm, keys, perm in arms[1:]:
        d = res[nm][0] - base
        imp = sum(1 for T, _, x in res[nm][1] if x < bper.get(T, 1e9))
        nul = sorted(chain(rows, keys, permute=perm, seed=s)[0] - base
                     for s in range(1, 61))
        print(f"  {nm:<34} delta {d:+.5f}  folds improved {imp}/{len(res[nm][1])}"
              f"  null max|d| {max(abs(x) for x in nul):.5f}"
              f"  null95 [{nul[1]:+.5f},{nul[-2]:+.5f}]"
              f"  -> outside band: {d < 0 and abs(d) > max(abs(x) for x in nul)}")

    print("\n=== paired bootstrap (cluster on pitcher, refit per draw) ===")
    rng = random.Random(13)
    byp = defaultdict(list)
    for r in rows:
        byp[r["m"]].append(r)
    ks = list(byp)
    d1 = []
    for _ in range(200):
        draw = []
        for _ in range(len(ks)):
            draw += byp[ks[rng.randrange(len(ks))]]
        a = chain(draw, ["age", "v_prev"])[0]
        b = chain(draw, ["age", "v_prev", "tj_prior", "tj_recent", "tj_n"])[0]
        if a and b:
            d1.append(b - a)
    d1.sort()
    print(f"  full TJ block over baseline: delta {statistics.mean(d1):+.5f} "
          f"sd {statistics.pstdev(d1):.5f} "
          f"CI95 [{d1[int(.025*len(d1))]:+.5f},{d1[int(.975*len(d1))]:+.5f}] "
          f"P(improves) {sum(1 for x in d1 if x<0)/len(d1):.3f}")

    print("\n=== full-pool standardized coefficients (direction sanity) ===")
    mm = ridge([[r[k] for k in ("age", "v_prev", "tj_prior", "tj_recent", "tj_n")]
                for r in rows], [r["dv"] for r in rows])
    for k, c in zip(("intercept", "age", "v_prev", "tj_prior", "tj_recent", "tj_n"),
                    mm["w"]):
        print(f"  {k:<12} {c:+.4f}")


if __name__ == "__main__":
    main()
