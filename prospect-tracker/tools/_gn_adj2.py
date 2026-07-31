# ADJUDICATION LAB 2 -- independent re-derivation of intlalias's load-bearing numbers,
# straight from the DB, not from that lane's labs.
#   (i)  intl vs mlb_pipeline main list, SAME player SAME cycle  (claim +7.279 [+6.438,+8.075], n=147)
#   (ii) the zero-information control: mlb_pipeline's OTHER co-published lists, same date
#        same player  (claim n=1,564, mean |gap| 0.035, share nonzero 0.006)
#  (iii) intl vs fangraphs paired  (claim +11.229 [+10.534,+11.910], n_pair 179)
import os, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE)); os.chdir(_HERE)
import storage  # noqa: E402

RNG = np.random.default_rng(7)
B = 4000


def clustered_boot(pairs, keys):
    """pairs: array of per-row gaps; keys: cluster id per row."""
    by = defaultdict(list)
    for g, k in zip(pairs, keys):
        by[k].append(g)
    ks = list(by)
    arrs = [np.array(by[k], float) for k in ks]
    out = np.empty(B)
    for i in range(B):
        idx = RNG.integers(0, len(ks), len(ks))
        out[i] = np.mean(np.concatenate([arrs[j] for j in idx]))
    return np.percentile(out, [2.5, 97.5])


with storage.connect() as con:
    rows = con.execute(
        "SELECT player_key, source, snapshot_date, fv FROM snapshots "
        "WHERE fv IS NOT NULL").fetchall()
    pos = {r["player_key"]: (r["position"], r["is_pitcher"]) for r in
           con.execute("SELECT player_key, position, is_pitcher FROM players")}

print(f"snapshots with fv: {len(rows)}")
# cycle = calendar year of snapshot_date
by_pc = defaultdict(dict)      # (player, year) -> {source: [(date, fv)]}
for r in rows:
    y = int(r["snapshot_date"][:4])
    by_pc[(r["player_key"], y)].setdefault(r["source"], []).append(
        (r["snapshot_date"], float(r["fv"])))

INTL = "mlb_pipeline_international"

# ---- (i) intl vs mlb_pipeline main, same player same cycle ----
gaps, keys, per_cycle = [], [], defaultdict(list)
for (pk, y), d in by_pc.items():
    if INTL in d and "mlb_pipeline" in d:
        gi = np.mean([v for _, v in d[INTL]])
        gm = np.mean([v for _, v in d["mlb_pipeline"]])
        gaps.append(gi - gm); keys.append(pk); per_cycle[y].append(gi - gm)
gaps = np.array(gaps, float)
lo, hi = clustered_boot(gaps, keys)
print(f"\n(i) intl - mlb_pipeline main, same player same cycle:")
print(f"    n={len(gaps)} player-cycles, {len(set(keys))} players, "
      f"mean {gaps.mean():+.3f}  clustered CI95 [{lo:+.3f}, {hi:+.3f}]")
for y in sorted(per_cycle):
    v = np.array(per_cycle[y]); print(f"      {y}: n={len(v):3d}  mean {v.mean():+.3f}")
# sign-flip permutation null
perm = np.empty(5000)
for i in range(5000):
    perm[i] = np.mean(gaps * RNG.choice([-1.0, 1.0], len(gaps)))
print(f"    sign-flip permutation null band [{np.percentile(perm,2.5):+.3f}, "
      f"{np.percentile(perm,97.5):+.3f}]  vs observed {gaps.mean():+.3f}")
# leave-one-year-out
print("    leave-one-year-out:", end=" ")
for y in sorted(per_cycle):
    m = np.array([g for yy in per_cycle if yy != y for g in per_cycle[yy]])
    print(f"{y}:{m.mean():+.3f}", end="  ")
print()

# ---- (ii) zero-information control: same outlet, same date, same player, 2 rows ----
same_date = defaultdict(list)
for r in rows:
    if r["source"] in (INTL,):
        continue
    same_date[(r["player_key"], r["source"], r["snapshot_date"])].append(float(r["fv"]))
ctl = [max(v) - min(v) for v in same_date.values() if len(v) > 1]
mp_ctl = [max(v) - min(v) for (pk, s, d), v in same_date.items()
          if len(v) > 1 and s == "mlb_pipeline"]
print(f"\n(ii) ZERO-INFO CONTROL, mlb_pipeline same player same date multi-row:")
print(f"    n={len(mp_ctl)}  mean|gap| {np.mean(mp_ctl):.3f}  "
      f"share nonzero {np.mean([g>0 for g in mp_ctl]):.3f}  max {max(mp_ctl) if mp_ctl else 0:.1f}")
fg_ctl = [max(v) - min(v) for (pk, s, d), v in same_date.items()
          if len(v) > 1 and s == "fangraphs"]
print(f"    fangraphs equivalent: n={len(fg_ctl)}")

# ---- (iii) intl vs fangraphs, paired same cycle, hitters ----
for want_pit in (0, 1):
    g2, k2 = [], []
    for (pk, y), d in by_pc.items():
        if INTL in d and "fangraphs" in d:
            p = pos.get(pk)
            if p is None or int(bool(p[1])) != want_pit:
                continue
            g2.append(np.mean([v for _, v in d[INTL]]) -
                      np.mean([v for _, v in d["fangraphs"]]))
            k2.append(pk)
    if len(g2) < 5:
        print(f"\n(iii) intl - fangraphs {'PIT' if want_pit else 'HIT'}: n={len(g2)} too thin")
        continue
    g2 = np.array(g2, float)
    lo, hi = clustered_boot(g2, k2)
    print(f"\n(iii) intl - fangraphs {'PIT' if want_pit else 'HIT'}: n_pair={len(g2)} "
          f"clusters={len(set(k2))}  mean {g2.mean():+.3f}  CI95 [{lo:+.3f}, {hi:+.3f}]")
