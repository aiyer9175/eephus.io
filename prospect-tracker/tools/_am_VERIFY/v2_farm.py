"""ADVERSARIAL VERIFY v2: independent re-derivation of claim A1 (farm grades /
surplus mass vs count) with my own cluster bootstrap, permutation null, and a
cross-vintage dependence probe the lane did not run. Read-only."""
import json, math, random, statistics
from collections import defaultdict, Counter
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import storage
import value_framework as vf

VINTAGES = (2018, 2019, 2020, 2021, 2022)
WINDOW = 3
MIN_ORG_N = 3
_ALIAS = {"OAK": "ATH"}
_JUNK = {"Office of the Commissioner"}

def spearman(xs, ys):
    n = len(xs)
    if n < 3: return None
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i]); r = [0.0]*n; i = 0
        while i < n:
            j = i
            while j+1 < n and v[order[j+1]] == v[order[i]]: j += 1
            avg = (i+j)/2+1
            for k in range(i, j+1): r[order[k]] = avg
            i = j+1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx)/n; my = sum(ry)/n
    cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    vx = sum((a-mx)**2 for a in rx); vy = sum((b-my)**2 for b in ry)
    if vx == 0 or vy == 0: return None
    return cov/math.sqrt(vx*vy)

# ---- load (independent re-implementation of farm_grade_backtest._load) -------
with storage.connect() as con:
    rows = con.execute("""
        SELECT player_key, source, substr(snapshot_date,1,4) AS y, MIN(snapshot_date) AS d
        FROM snapshots WHERE fv IS NOT NULL AND substr(snapshot_date,1,4) IN ({})
        GROUP BY player_key, source, y""".format(",".join(f"'{y}'" for y in VINTAGES))).fetchall()
    per = defaultdict(list)
    for r in rows:
        s = con.execute("SELECT fv, org FROM snapshots WHERE player_key=? AND source=? AND snapshot_date=?",
                        (r["player_key"], r["source"], r["d"])).fetchone()
        if s and s["fv"] is not None:
            per[(r["player_key"], int(r["y"]))].append((float(s["fv"]), s["org"]))
    listings = {}
    for key, vals in per.items():
        orgs = [_ALIAS.get(o, o) for _, o in vals if o and o not in _JUNK]
        listings[key] = {"fv": statistics.median(v for v, _ in vals),
                         "org": Counter(orgs).most_common(1)[0][0] if orgs else None}
    cw = {}
    for r in con.execute("SELECT player_key, payload_json FROM career_war"):
        try: seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
        except ValueError: continue
        cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
    bio = {r["player_key"]: dict(r) for r in con.execute("SELECT player_key, position, is_pitcher FROM players")}

by_ov = defaultdict(list)
for (pk, vy), li in listings.items():
    if li["org"]:
        by_ov[(li["org"], vy)].append((pk, li["fv"]))

# ---- per-org stat table, both pricings -------------------------------------
TAB = {}    # vy -> {org: {stat: val}}, plus realized
for vy in VINTAGES:
    orgs = sorted({o for (o, y) in by_ov if y == vy})
    preds, real = {}, {}
    for org in orgs:
        members = by_ov[(org, vy)]
        if len(members) < MIN_ORG_N: continue
        sur = sur_prod = war6 = cnt50 = 0.0
        rw = 0.0
        for pk, fv in members:
            b = bio.get(pk) or {}
            is_pit = vf.is_pitcher_position(b.get("position"))
            s = vf.point_estimate_surplus_usd(fv, is_pit, b.get("position"))
            if s: sur += s/1e6
            sp = vf.surplus_value_mm(float(fv), is_pit, b.get("position"))
            if sp: sur_prod += float(sp)
            war6 += vf.fv_to_6yr_avg_war(fv) or 0.0
            if fv >= 50: cnt50 += 1
            seasons = cw.get(pk) or {}
            debut = min(seasons) if seasons else None
            if debut is not None and vy <= debut <= vy+WINDOW:
                rw += sum(w for y_, w in seasons.items() if vy <= y_ <= vy+WINDOW)
        preds[org] = {"sum_surplus_mm": sur, "sum_surplus_prod": sur_prod,
                      "sum_expected_war": war6, "count": float(len(members)),
                      "count_fv50plus": cnt50}
        real[org] = rw
    TAB[vy] = (preds, real)

STATS = ["sum_surplus_mm", "sum_surplus_prod", "sum_expected_war", "count_fv50plus", "count"]

def mean_rho(stat, org_pick=None, y_map=None):
    """mean over vintages of Spearman(stat, realized). org_pick: {vy: [orgs]} resample."""
    vals = []
    for vy in VINTAGES:
        preds, real = TAB[vy]
        orgs = org_pick[vy] if org_pick else [o for o in preds if o in real]
        xs = [preds[o][stat] for o in orgs]
        ys = [(y_map[vy][o] if y_map else real[o]) for o in orgs]
        r = spearman(xs, ys)
        if r is not None: vals.append(r)
    return sum(vals)/len(vals) if vals else None, vals

print("=== POINT ESTIMATES (my own re-derivation) ===")
base = {}
for s in STATS:
    m, per_v = mean_rho(s)
    base[s] = m
    print(f"  {s:20s} mean {m:+.4f}   per-vintage " + " ".join(f"{v:+.3f}" for v in per_v))

# ---- cross-vintage dependence probe: roster overlap between consecutive boards
print("\n=== INDEPENDENCE OF THE 5 'TIME SPLITS' ===")
for a, b in zip(VINTAGES, VINTAGES[1:]):
    sa = {pk for (pk, y) in listings if y == a}
    sb = {pk for (pk, y) in listings if y == b}
    print(f"  {a} vs {b}: |A|={len(sa)} |B|={len(sb)} shared players={len(sa&sb)} "
          f"({100*len(sa&sb)/max(1,len(sb)):.0f}% of B)  realized windows overlap "
          f"{a}-{a+WINDOW} vs {b}-{b+WINDOW}")

# ---- paired cluster bootstrap, TWO clustering schemes -----------------------
def boot(stat_a, stat_b, B=4000, seed=7, scheme="per_vintage"):
    rnd = random.Random(seed)
    orgs_by_vy = {vy: [o for o in TAB[vy][0] if o in TAB[vy][1]] for vy in VINTAGES}
    all_orgs = sorted(set().union(*[set(v) for v in orgs_by_vy.values()]))
    out = []
    for _ in range(B):
        if scheme == "per_vintage":
            pick = {vy: [rnd.choice(orgs_by_vy[vy]) for _ in orgs_by_vy[vy]] for vy in VINTAGES}
        else:  # cluster on the ORG across all vintages (handles cross-vintage dependence)
            draw = [rnd.choice(all_orgs) for _ in all_orgs]
            pick = {vy: [o for o in draw if o in orgs_by_vy[vy]] for vy in VINTAGES}
            if any(len(v) < 5 for v in pick.values()): continue
        a, _ = mean_rho(stat_a, pick); b, _ = mean_rho(stat_b, pick)
        if a is not None and b is not None: out.append(a-b)
    out.sort()
    m = sum(out)/len(out)
    sd = (sum((d-m)**2 for d in out)/(len(out)-1))**0.5
    return (base[stat_a]-base[stat_b], sd, out[int(.025*len(out))], out[int(.975*len(out))],
            sum(1 for d in out if d > 0)/len(out), 1.96*sd, len(out))

print("\n=== PAIRED CLUSTER BOOTSTRAP (B=4000) ===")
for sa, sb in [("sum_surplus_mm", "count"), ("sum_surplus_mm", "count_fv50plus"),
               ("sum_surplus_mm", "sum_expected_war"), ("sum_surplus_prod", "sum_surplus_mm")]:
    for scheme in ("per_vintage", "org_block"):
        obs, sd, lo, hi, p, mde, nb = boot(sa, sb, scheme=scheme)
        print(f"  {sa} - {sb:18s} [{scheme:11s}] obs {obs:+.4f} sd {sd:.4f} "
              f"CI95 [{lo:+.4f},{hi:+.4f}] P(>0)={p:.3f} MDE95={mde:.4f} (B={nb})")

# ---- permutation null: shuffle realized WAR across orgs within vintage ------
print("\n=== PERMUTATION NULL (realized permuted within vintage, 2000 draws) ===")
rnd = random.Random(99)
nulls_sur, nulls_diff = [], []
for _ in range(2000):
    ymap = {}
    for vy in VINTAGES:
        preds, real = TAB[vy]
        orgs = [o for o in preds if o in real]
        vals = [real[o] for o in orgs]; rnd.shuffle(vals)
        ymap[vy] = dict(zip(orgs, vals))
    a, _ = mean_rho("sum_surplus_mm", None, ymap)
    c, _ = mean_rho("count", None, ymap)
    nulls_sur.append(a); nulls_diff.append(a-c)
nulls_sur.sort(); nulls_diff.sort()
print(f"  rho(surplus) null mean {sum(nulls_sur)/len(nulls_sur):+.4f} "
      f"CI95 [{nulls_sur[50]:+.4f},{nulls_sur[1949]:+.4f}]  observed {base['sum_surplus_mm']:+.4f} "
      f"p_emp={sum(1 for v in nulls_sur if v >= base['sum_surplus_mm'])/2000:.4f}")
print(f"  diff null mean {sum(nulls_diff)/len(nulls_diff):+.4f} "
      f"CI95 [{nulls_diff[50]:+.4f},{nulls_diff[1949]:+.4f}]  observed "
      f"{base['sum_surplus_mm']-base['count']:+.4f}")

# ---- zero-information control: row-permute the SURPLUS column within vintage
print("\n=== ZERO-INFO CONTROL (surplus column row-permuted within vintage) ===")
rnd = random.Random(5)
ctrl = []
for _ in range(200):
    vals_all = []
    for vy in VINTAGES:
        preds, real = TAB[vy]
        orgs = [o for o in preds if o in real]
        col = [preds[o]["sum_surplus_mm"] for o in orgs]; rnd.shuffle(col)
        vals_all.append(spearman(col, [real[o] for o in orgs]))
    ctrl.append(sum(vals_all)/len(vals_all))
ctrl.sort()
print(f"  permuted-surplus mean rho {sum(ctrl)/len(ctrl):+.4f}  p95 {ctrl[189]:+.4f}  "
      f"(real {base['sum_surplus_mm']:+.4f})")
