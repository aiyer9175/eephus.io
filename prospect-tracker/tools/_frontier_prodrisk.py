"""ADVERSARIAL VERIFY -- production impact + risk of the recommended changes.

Read-only. Simulates the anchor lane's recommended consensus-FV repair on the LIVE
served board and measures what actually moves in served numbers:
  - consensus_fv itself
  - xfv_grade_display (the headline served grade) via efv_score's exact quantile map
  - the JOINT board order / top-50 churn
  - surplus_mm dollars (repriced off the display grade, exactly as efv_score does)

Nothing is written back. No shipped module or data file is modified.
"""
import json, os, sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
D = HERE / "data"


def load(p):
    return json.loads((D / p).read_text(encoding="utf-8"))


def rows_of(obj):
    return obj if isinstance(obj, list) else obj.get("players") or obj.get("rows")


hit = rows_of(load("xfv_scored_live.json"))
pit = rows_of(load("xfv_scored_live_pitcher.json"))
mh = rows_of(load("xfv_live_hitter_matrix.json"))
mp = rows_of(load("xfv_live_pitcher_matrix.json"))
print(f"served rows: hit {len(hit)} pit {len(pit)} | live matrix hit {len(mh)} pit {len(mp)}")

src = {}
for r in list(mh) + list(mp):
    src[r["player_key"]] = (r.get("fv_fangraphs"), r.get("fv_mlb_pipeline"),
                            r.get("n_sources"), r.get("consensus_fv_raw"))

# ---- (1) independently re-measure the live paired gap (MP - FG) -------------
pairs = [(f, m) for (f, m, _n, _c) in src.values() if f is not None and m is not None]
import statistics as st
gaps = [m - f for f, m in pairs]
gap = st.mean(gaps)
se = st.pstdev(gaps) / (len(gaps) ** 0.5)
print(f"\n[1] LIVE PAIRED GAP (mlb_pipeline - fangraphs): +{gap:.3f} FV  SE {se:.3f}  n_pair {len(gaps)}"
      f"  median {st.median(gaps):+.1f}")

cov = {"both": 0, "fg_only": 0, "mp_only": 0, "neither": 0}
for f, m, _n, _c in src.values():
    k = "both" if (f is not None and m is not None) else (
        "fg_only" if f is not None else ("mp_only" if m is not None else "neither"))
    cov[k] += 1
print(f"    coverage over live matrix rows: {cov}")


def shift_for(pk):
    e = src.get(pk)
    if not e:
        return 0.0
    f, m, _n, _c = e
    if f is not None and m is not None:
        return 0.0
    if f is not None:
        return +gap / 2.0
    if m is not None:
        return -gap / 2.0
    return 0.0


# ---- (2) display quantile map, replicated exactly from efv_score ------------
def display_map(scored, cons_key):
    """Exact replica of efv_score lines 941-960."""
    target = sorted(s[cons_key] for s in scored)
    order = sorted(range(len(scored)),
                   key=lambda i: (scored[i]["rank_war"], scored[i]["player_key"]))
    m = len(scored)
    out = {}
    for rank_pos, i in enumerate(order):
        p = (rank_pos / (m - 1)) if m > 1 else 0.0
        pos = p * (m - 1)
        lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo
        out[scored[i]["player_key"]] = round(target[lo] * (1 - frac) + target[hi] * frac, 1)
    return out


results = {}
for side, rows in (("hit", hit), ("pit", pit)):
    rr = [r for r in rows if r.get("rank_war") is not None and r.get("consensus_fv") is not None]
    for r in rr:
        r["_cons_new"] = round(r["consensus_fv"] + shift_for(r["player_key"]), 1)
    base = display_map(rr, "consensus_fv")
    new = display_map(rr, "_cons_new")
    # parity check against the SERVED grade already on disk
    served = {r["player_key"]: r.get("xfv_grade_display") for r in rr}
    par = [abs(base[k] - served[k]) for k in base if served.get(k) is not None]
    moved_c = sum(1 for r in rr if abs(r["_cons_new"] - r["consensus_fv"]) > 1e-9)
    dd = [abs(new[k] - base[k]) for k in base]
    unmoved = [abs(new[r["player_key"]] - base[r["player_key"]]) for r in rr
               if abs(r["_cons_new"] - r["consensus_fv"]) <= 1e-9]
    results[side] = (rr, base, new)
    print(f"\n[2] {side}: n={len(rr)}  replica-vs-served display parity: "
          f"mean|d| {sum(par)/len(par):.4f} max {max(par):.2f} (n={len(par)})")
    print(f"    consensus_fv moved for {moved_c}/{len(rr)} rows ({100*moved_c/len(rr):.1f}%)")
    print(f"    DISPLAY grade moved: mean|d| {sum(dd)/len(dd):.3f} FV, "
          f"max {max(dd):.2f}, >=0.5FV {sum(1 for x in dd if x>=0.5)} "
          f"({100*sum(1 for x in dd if x>=0.5)/len(dd):.1f}%), "
          f">=1.0FV {sum(1 for x in dd if x>=1.0)} ({100*sum(1 for x in dd if x>=1.0)/len(dd):.1f}%)")
    print(f"    COLLATERAL (rows whose OWN consensus did NOT move, n={len(unmoved)}): "
          f"mean|d| {sum(unmoved)/len(unmoved):.3f} FV, max {max(unmoved):.2f}, "
          f">=1.0FV {sum(1 for x in unmoved if x>=1.0)}")

# ---- (3) JOINT board order + top-50 churn -----------------------------------
def joint(key):
    allr = []
    for side in ("hit", "pit"):
        rr, base, new = results[side]
        m = base if key == "base" else new
        for r in rr:
            allr.append((m[r["player_key"]], r["player_key"], side))
    allr.sort(key=lambda t: (-t[0], t[1]))
    return [t[1] for t in allr], {t[1]: t[0] for t in allr}


ob, gb = joint("base")
on, gn = joint("new")
for N in (10, 25, 50, 100, 300):
    a, b = set(ob[:N]), set(on[:N])
    print(f"\n[3] JOINT top-{N}: retained {len(a & b)}/{N}  ({N-len(a&b)} in/out)")
posb = {k: i for i, k in enumerate(ob)}
posn = {k: i for i, k in enumerate(on)}
moves = [abs(posn[k] - posb[k]) for k in posb]
top50_moves = [abs(posn[k] - posb[k]) for k in ob[:50]]
print(f"    board-rank |move|: mean {sum(moves)/len(moves):.1f} slots, max {max(moves)}; "
      f"top-50 incumbents mean {sum(top50_moves)/len(top50_moves):.1f} slots, max {max(top50_moves)}")
print(f"    F-SIDE-FIX top-band membership (display >= 55): "
      f"base {sum(1 for v in gb.values() if v>=55)} -> new {sum(1 for v in gn.values() if v>=55)}")

# ---- (4) surplus dollars, repriced exactly as efv_score does ----------------
try:
    import value_framework as vf
    from efv_score import _cal_mm
    tot_b = tot_n = 0.0
    deltas = []
    for side, is_pit in (("hit", False), ("pit", True)):
        rr, base, new = results[side]
        for r in rr:
            pos = r.get("position")
            try:
                sb = vf.expected_surplus_usd(base[r["player_key"]], is_pit, pos, eta_years=1.0)
                sn = vf.expected_surplus_usd(new[r["player_key"]], is_pit, pos, eta_years=1.0)
            except Exception:
                continue
            if sb is None or sn is None:
                continue
            sb = _cal_mm(sb / 1e6, base[r["player_key"]], is_pit)
            sn = _cal_mm(sn / 1e6, new[r["player_key"]], is_pit)
            if sb is None or sn is None:
                continue
            tot_b += sb; tot_n += sn
            deltas.append((abs(sn - sb), sn - sb, r["player_key"], sb, sn))
    deltas.sort(reverse=True)
    ad = [d[0] for d in deltas]
    print(f"\n[4] SURPLUS $ (repriced off display grade, n={len(deltas)}):")
    print(f"    board total ${tot_b:,.0f}M -> ${tot_n:,.0f}M  ({100*(tot_n-tot_b)/tot_b:+.2f}%)")
    print(f"    per-player |d$|: mean ${sum(ad)/len(ad):.2f}M  max ${max(ad):.1f}M  "
          f">= $1M {sum(1 for x in ad if x>=1)}  >= $5M {sum(1 for x in ad if x>=5)}")
    print("    biggest movers: " + ", ".join(
        f"{k} ${b:.0f}->${n:.0f}M" for _a, _s, k, b, n in deltas[:6]))
except Exception as e:
    print(f"\n[4] surplus repricing unavailable: {type(e).__name__}: {e}")
