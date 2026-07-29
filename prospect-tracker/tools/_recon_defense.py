"""RECON ONLY (lane: defense). Ground truth + joins for a positional-conversion model.

Reads:
  data/mlb_def_history.json      BRef war_daily_bat defensive split (war_def, runs_position, pa)
  data/def_home.json             prospect defensive-home certainty sidecar
  data/positions_played.json     StatsAPI career games/starts by position ("versa")
  .cache/savant_oaa/oaa_YYYY.csv Savant OAA leaderboard (fetched live, min=q)
  .cache/statsapi_field/fld_YYYY.json  StatsAPI season fielding split by position

Writes nothing outside .cache / data/sources/samples.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache"

POS_ADJ_STD = {"C": 12.5, "SS": 7.5, "CF": 2.5, "2B": 2.5, "3B": 2.5,
               "RF": -7.5, "LF": -7.5, "1B": -12.5, "DH": -17.5}
FIELD_POS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")


def sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


# ---------------------------------------------------------------- loaders
def def_history():
    d = json.loads((DATA / "mlb_def_history.json").read_text(encoding="utf-8"))
    rows = {}
    for k, v in d["rows"].items():
        mid, yr = k.split(":")
        rows[(int(mid), int(yr))] = v
    return d, rows


def statsapi_fielding():
    """(mlbam, season) -> {POS: {'g','gs','inn'}}"""
    out = defaultdict(dict)
    for f in sorted((CACHE / "statsapi_field").glob("fld_*.json")):
        yr = int(f.stem.split("_")[1])
        d = json.loads(f.read_text(encoding="utf-8"))
        for sp in d["stats"][0]["splits"]:
            pos = sp["position"]["abbreviation"]
            st = sp["stat"]
            inn = st.get("innings")
            try:
                inn = float(str(inn).replace(".1", ".333").replace(".2", ".667")) if inn else 0.0
            except ValueError:
                inn = 0.0
            slot = out[(sp["player"]["id"], yr)].setdefault(
                pos, {"g": 0, "gs": 0, "inn": 0.0})
            slot["g"] += int(st.get("games") or st.get("gamesPlayed") or 0)
            slot["gs"] += int(st.get("gamesStarted") or 0)
            slot["inn"] += inn
    return out


def primary_pos(by_pos, exclude_dh=False):
    cand = {p: v for p, v in by_pos.items()
            if p != "P" and not (exclude_dh and p == "DH")}
    if not cand:
        return None
    # rank by innings, fall back to games (DH has no innings)
    return max(cand.items(), key=lambda kv: (kv[1]["inn"], kv[1]["g"]))[0]


def oaa_rows():
    out = {}
    for f in sorted((CACHE / "savant_oaa").glob("oaa_*.csv")):
        yr = int(f.stem.split("_")[1])
        rr = list(csv.DictReader(f.open(encoding="utf-8-sig")))
        out[yr] = rr
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def spearman(xs, ys):
    def rk(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        for j, i in enumerate(order):
            r[i] = j
        return r
    return pearson(rk(xs), rk(ys))


def boot_ci(xs, ys, fn, B=1000, seed=7):
    import random
    rng = random.Random(seed)
    n = len(xs)
    vals = []
    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(fn([xs[i] for i in idx], [ys[i] for i in idx]))
    vals.sort()
    return vals[int(.025 * B)], vals[int(.975 * B)]


def perm_null(xs, ys, fn, B=500, seed=11):
    import random
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        y2 = ys[:]
        rng.shuffle(y2)
        vals.append(abs(fn(xs, y2)))
    vals.sort()
    return vals[int(.95 * B)]


def main():
    dh_meta, dh = def_history()

    # ---------------- (a) mlb_def_history ----------------
    sec("(a1) data/mlb_def_history.json")
    print("meta:", {k: dh_meta[k] for k in ("generated_from", "first_season", "fields", "count")})
    seasons = sorted({y for _, y in dh})
    players = {m for m, _ in dh}
    print(f"player-seasons={len(dh)}  unique mlbam={len(players)}  seasons {seasons[0]}-{seasons[-1]}")
    print("key format 'mlbam:season' -> {war_def, runs_position, pa}")
    print()
    print(f"{'yr':>5} {'rows':>5} {'n>=100pa':>8} {'sum_pa':>9} "
          f"{'war_def mean':>12} {'sd':>7} {'runs_pos mean':>13} {'sd':>7}")
    for y in seasons:
        rr = [v for (m, yy), v in dh.items() if yy == y]
        wd = [v["war_def"] for v in rr]
        rp = [v["runs_position"] for v in rr]
        print(f"{y:>5} {len(rr):>5} {sum(1 for v in rr if v['pa']>=100):>8} "
              f"{int(sum(v['pa'] for v in rr)):>9} {statistics.mean(wd):>12.3f} "
              f"{statistics.pstdev(wd):>7.3f} {statistics.mean(rp):>13.2f} {statistics.pstdev(rp):>7.2f}")

    # ---------------- (a2) def_home / positions_played ----------------
    sec("(a2) def_home.json / positions_played.json")
    dhome = json.loads((DATA / "def_home.json").read_text(encoding="utf-8"))
    bm = dhome["by_mlbam"]
    print(f"def_home: n={len(bm)} keyed by mlbam(str); also key_to_mlbam n={len(dhome['key_to_mlbam'])}")
    print("  fields:", sorted(next(iter(bm.values())).keys()))
    print("  listed_pos:", Counter(v["listed_pos"] for v in bm.values()).most_common())
    print("  band:", Counter(v["band"] for v in bm.values()).most_common())
    print("  entropy_band:", Counter(v["entropy_band"] for v in bm.values()).most_common())
    print("  basis:", Counter(v["basis"] for v in bm.values()).most_common())
    ph = [v["p_hold"] for v in bm.values()]
    print(f"  p_hold mean={statistics.mean(ph):.3f} median={statistics.median(ph):.3f} "
          f"min={min(ph):.3f} max={max(ph):.3f}")

    pp = json.loads((DATA / "positions_played.json").read_text(encoding="utf-8"))
    pl = pp["players"]
    print(f"\npositions_played: n={len(pl)} keyed by PLAYER_KEY (no mlbam inside) "
          f"min_games={pp['min_games']} min_starts={pp['min_starts']}")
    nv = Counter(len(v["versa"]) for v in pl.values())
    print("  #versa positions:", sorted(nv.items()))
    posc = Counter()
    for v in pl.values():
        for p in v["by_pos"]:
            posc[p] += 1
    print("  players appearing at each pos:", posc.most_common())
    # join def_home key_to_mlbam <-> positions_played keys
    k2m = dhome["key_to_mlbam"]
    both = set(k2m) & set(pl)
    print(f"  join def_home.key_to_mlbam ^ positions_played keys: {len(both)} "
          f"({100*len(both)/max(1,len(k2m)):.1f}% of def_home)")
    # def_home <-> mlb_def_history
    dh_ids = {str(m) for m in players}
    print(f"  join def_home mlbam ^ mlb_def_history mlbam: {len(set(bm)&dh_ids)} "
          f"({100*len(set(bm)&dh_ids)/len(bm):.1f}%) -- def_home is a PROSPECT list, "
          f"def_history is MLB-only, so overlap == graduated")

    # ---------------- (c) Savant OAA ----------------
    sec("(c) Savant OAA live fetch")
    oaa = oaa_rows()
    fld = statsapi_fielding()
    universe = dh_ids  # our MLB player universe from BRef
    print(f"{'yr':>5} {'rows':>5} {'uniq_id':>7} {'join_defhist':>12} {'join%':>6} "
          f"{'join_statsapi':>13} {'j%':>6}")
    for y in sorted(oaa):
        rr = oaa[y]
        ids = {r["player_id"] for r in rr}
        j1 = sum(1 for i in ids if (int(i), y) in dh)
        sa = {m for (m, yy) in fld if yy == y}
        j2 = sum(1 for i in ids if int(i) in sa)
        print(f"{y:>5} {len(rr):>5} {len(ids):>7} {j1:>12} {100*j1/len(ids):>5.1f}% "
              f"{j2:>13} {100*j2/len(ids):>5.1f}%")
    print("\ncolumns:", list(oaa[2024][0].keys()))
    print("\nprimary_pos_formatted counts by year:")
    allpos = sorted({r["primary_pos_formatted"] for y in oaa for r in oaa[y]})
    print(f"{'yr':>5} " + " ".join(f"{p:>4}" for p in allpos))
    for y in sorted(oaa):
        c = Counter(r["primary_pos_formatted"] for r in oaa[y])
        print(f"{y:>5} " + " ".join(f"{c.get(p,0):>4}" for p in allpos))
    print("\nNOTE: 'year' column is EMPTY in the CSV (the year is only in the request); "
          "stamp it yourself.")
    print("min=q -> QUALIFIED fielders only. Probe min=1 coverage separately.")

    # OAA value distributions
    print("\nOAA / fielding_runs_prevented distribution (all years pooled):")
    o = [float(r["outs_above_average"]) for y in oaa for r in oaa[y] if r["outs_above_average"] not in ("", None)]
    frp = [float(r["fielding_runs_prevented"]) for y in oaa for r in oaa[y] if r["fielding_runs_prevented"] not in ("", None)]
    print(f"  OAA n={len(o)} mean={statistics.mean(o):.2f} sd={statistics.pstdev(o):.2f} "
          f"min={min(o):.0f} max={max(o):.0f}")
    print(f"  FRP n={len(frp)} mean={statistics.mean(frp):.2f} sd={statistics.pstdev(frp):.2f} "
          f"min={min(frp):.0f} max={max(frp):.0f}")
    pairs = [(float(r["outs_above_average"]), float(r["fielding_runs_prevented"]))
             for y in oaa for r in oaa[y]]
    xs = [a for a, b in pairs]
    ys = [b for a, b in pairs]
    print(f"  r(OAA, FRP) = {pearson(xs, ys):.4f}  "
          f"implied runs/out slope = {statistics.mean([b/a for a,b in pairs if a!=0]):.3f}")

    # ---------------- (d) OAA vs BRef war_def ----------------
    sec("(d) OAA / FRP  vs  BRef war_def, runs_position (same player-season)")
    rows = []
    for y in sorted(oaa):
        for r in oaa[y]:
            mid = int(r["player_id"])
            h = dh.get((mid, y))
            if not h:
                continue
            try:
                O = float(r["outs_above_average"]); F = float(r["fielding_runs_prevented"])
            except ValueError:
                continue
            rows.append({"y": y, "mlbam": mid, "pos": r["primary_pos_formatted"],
                         "oaa": O, "frp": F, "war_def": h["war_def"],
                         "runs_position": h["runs_position"], "pa": h["pa"]})
    print(f"matched player-seasons: {len(rows)}  (OAA qualified ^ BRef def history)")

    def report(name, fx, fy, sub):
        xs = [fx(r) for r in sub]; ys = [fy(r) for r in sub]
        if len(xs) < 20:
            print(f"  {name:<44} n={len(xs)} (too few)")
            return
        rp = pearson(xs, ys); rs = spearman(xs, ys)
        lo, hi = boot_ci(xs, ys, pearson)
        nb = perm_null(xs, ys, pearson)
        print(f"  {name:<44} n={len(xs):>5} r={rp:>6.3f} [{lo:.3f},{hi:.3f}] "
              f"rho={rs:>6.3f} perm95|r|={nb:.3f}")

    print("\npooled 2016-2025:")
    report("OAA  vs war_def", lambda r: r["oaa"], lambda r: r["war_def"], rows)
    report("FRP  vs war_def", lambda r: r["frp"], lambda r: r["war_def"], rows)
    report("OAA  vs runs_position", lambda r: r["oaa"], lambda r: r["runs_position"], rows)
    report("FRP  vs runs_position", lambda r: r["frp"], lambda r: r["runs_position"], rows)
    # war_def contains the positional adjustment; strip it to isolate FIELDING
    RUNS_PER_WIN = 9.7
    report("OAA  vs (war_def*9.7 - runs_position) [fielding only]",
           lambda r: r["oaa"], lambda r: r["war_def"] * RUNS_PER_WIN - r["runs_position"], rows)
    report("FRP  vs (war_def*9.7 - runs_position) [fielding only]",
           lambda r: r["frp"], lambda r: r["war_def"] * RUNS_PER_WIN - r["runs_position"], rows)

    print("\nby season (FRP vs fielding-only runs):")
    for y in sorted({r["y"] for r in rows}):
        sub = [r for r in rows if r["y"] == y]
        report(f"  {y}", lambda r: r["frp"],
               lambda r: r["war_def"] * RUNS_PER_WIN - r["runs_position"], sub)

    print("\nby position (FRP vs fielding-only runs, pooled):")
    for p in sorted({r["pos"] for r in rows}):
        sub = [r for r in rows if r["pos"] == p]
        report(f"  {p}", lambda r: r["frp"],
               lambda r: r["war_def"] * RUNS_PER_WIN - r["runs_position"], sub)

    # calibration: regress fielding-runs on FRP
    print("\ncalibration OLS  fielding_runs ~ a + b*FRP (pooled):")
    xs = [r["frp"] for r in rows]
    ys = [r["war_def"] * RUNS_PER_WIN - r["runs_position"] for r in rows]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
    a0 = my - b * mx
    resid = [c - (a0 + b * a) for a, c in zip(xs, ys)]
    print(f"  b={b:.4f}  a={a0:.3f}  R2={pearson(xs,ys)**2:.4f}  "
          f"resid sd={statistics.pstdev(resid):.2f} runs")

    # ---------------- (e) empirical positional ladder ----------------
    sec("(e) EMPIRICAL POSITIONAL LADDER from BRef runs_position (our data)")
    # per player-season primary position from StatsAPI innings
    lad = defaultdict(list)
    lad_pure = defaultdict(list)
    n_join = n_miss = 0
    for (mid, yr), h in dh.items():
        by = fld.get((mid, yr))
        if not by:
            n_miss += 1
            continue
        n_join += 1
        if h["pa"] < 100:
            continue
        p = primary_pos(by)
        if p is None or p == "P":
            continue
        tot = sum(v["inn"] for k, v in by.items() if k not in ("P", "DH"))
        share = (by[p]["inn"] / tot) if (tot > 0 and p != "DH") else None
        rate = h["runs_position"] * 650.0 / h["pa"]
        lad[p].append((rate, h["pa"]))
        if p == "DH" or (share is not None and share >= 0.90):
            lad_pure[p].append((rate, h["pa"]))
    print(f"def_history rows joined to StatsAPI fielding: {n_join} "
          f"({100*n_join/len(dh):.1f}%), unmatched {n_miss}")
    print("\nrunsPosition per 650 PA by PRIMARY position (pa>=100):")
    print(f"{'pos':>4} {'n':>6} {'PAwtd':>7} {'mean':>7} {'median':>7} {'sd':>6} "
          f"{'std ladder':>10} {'diff':>7} | {'>=90% pure n':>12} {'pure PAwtd':>10}")
    order = ["C", "SS", "2B", "CF", "3B", "RF", "LF", "1B", "DH"]
    emp = {}
    for p in order:
        v = lad.get(p) or []
        if not v:
            continue
        w = sum(r * pa for r, pa in v) / sum(pa for _, pa in v)
        m = statistics.mean([r for r, _ in v])
        med = statistics.median([r for r, _ in v])
        sd = statistics.pstdev([r for r, _ in v])
        vp = lad_pure.get(p) or []
        wp = (sum(r * pa for r, pa in vp) / sum(pa for _, pa in vp)) if vp else float("nan")
        emp[p] = w
        print(f"{p:>4} {len(v):>6} {w:>7.2f} {m:>7.2f} {med:>7.2f} {sd:>6.2f} "
              f"{POS_ADJ_STD[p]:>10.1f} {w-POS_ADJ_STD[p]:>7.2f} | {len(vp):>12} {wp:>10.2f}")
    ks = [p for p in order if p in emp]
    print(f"\n  r(empirical PA-wtd ladder, standard ladder) over {len(ks)} positions = "
          f"{pearson([emp[p] for p in ks],[POS_ADJ_STD[p] for p in ks]):.4f}")
    print(f"  empirical spread C..DH = {emp.get('C',float('nan')):.2f} .. "
          f"{emp.get('DH',float('nan')):.2f}  (std spread 12.5 .. -17.5)")
    # scale fit: empirical = alpha * standard + beta
    X = [POS_ADJ_STD[p] for p in ks]; Y = [emp[p] for p in ks]
    mx, my = statistics.mean(X), statistics.mean(Y)
    bb = sum((a-mx)*(c-my) for a, c in zip(X, Y)) / sum((a-mx)**2 for a in X)
    aa = my - bb*mx
    print(f"  OLS empirical ~ a + b*standard:  b={bb:.4f}  a={aa:.3f}  R2={pearson(X,Y)**2:.4f}")

    # ladder by era (has it moved?)
    print("\nladder by era (PA-weighted runs_position per 650 PA):")
    eras = [(2000, 2007), (2008, 2015), (2016, 2020), (2021, 2025)]
    hdr = f"{'pos':>4} " + " ".join(f"{f'{a}-{b}':>10}" for a, b in eras)
    print(hdr)
    for p in order:
        cells = []
        for a, b in eras:
            v = []
            for (mid, yr), h in dh.items():
                if not (a <= yr <= b) or h["pa"] < 100:
                    continue
                by = fld.get((mid, yr))
                if not by:
                    continue
                if primary_pos(by) != p:
                    continue
                v.append((h["runs_position"] * 650.0 / h["pa"], h["pa"]))
            cells.append(sum(r*pa for r, pa in v)/sum(pa for _, pa in v) if v else float("nan"))
        print(f"{p:>4} " + " ".join(f"{c:>10.2f}" for c in cells))

    # ---------------- ladder measured on OAA-labelled positions ----------------
    sec("(e2) CONVERSION PRICE: what a position MOVE costs, measured in our data")
    # players who changed primary position between consecutive seasons
    byp = {}
    for (mid, yr), h in dh.items():
        by = fld.get((mid, yr))
        if not by or h["pa"] < 200:
            continue
        p = primary_pos(by)
        if p and p != "P":
            byp[(mid, yr)] = (p, h)
    moves = defaultdict(list)
    for (mid, yr), (p, h) in byp.items():
        nxt = byp.get((mid, yr + 1))
        if not nxt:
            continue
        p2, h2 = nxt
        if p2 == p:
            continue
        d_rate = (h2["runs_position"] * 650.0 / h2["pa"]) - (h["runs_position"] * 650.0 / h["pa"])
        moves[(p, p2)].append(d_rate)
    print("observed primary-position transitions (pa>=200 both seasons), "
          "delta runs_position/650PA:")
    print(f"{'from->to':>12} {'n':>5} {'obs delta':>10} {'std delta':>10} {'err':>7}")
    tot_n = sum(len(v) for v in moves.values())
    for (p, p2), v in sorted(moves.items(), key=lambda kv: -len(kv[1]))[:25]:
        if len(v) < 8:
            continue
        obs = statistics.mean(v)
        std = POS_ADJ_STD.get(p2, float("nan")) - POS_ADJ_STD.get(p, float("nan"))
        print(f"{p+'->'+p2:>12} {len(v):>5} {obs:>10.2f} {std:>10.2f} {obs-std:>7.2f}")
    print(f"total observed transitions: {tot_n}")


if __name__ == "__main__":
    main()
