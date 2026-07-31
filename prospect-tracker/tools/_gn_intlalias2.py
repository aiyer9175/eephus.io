# scratch lab: intlalias step 2 -- paired bias, player-clustered bootstrap.
import sys, json, sqlite3
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import grade_normalization as gn

INTL = "mlb_pipeline_international"
MP = "mlb_pipeline"
FG = "fangraphs"

def paired_rows():
    """(player_key, role, year, intl_fv, fg_fv, has_main_pipeline_same_cycle)"""
    latest = gn._all_latest()
    rows = []
    for (role, yr), players in latest.items():
        for pk, d in players.items():
            if INTL in d and FG in d:
                rows.append(dict(pk=pk, role=role, year=yr, intl=d[INTL], fg=d[FG],
                                 mp=d.get(MP), has_mp=(MP in d)))
    return rows

def boot_cluster(rows, key, stat, B=4000, seed=17):
    """Cluster bootstrap on `key` (player). Returns (point, lo, hi)."""
    rng = np.random.default_rng(seed)
    clusters = {}
    for r in rows:
        clusters.setdefault(r[key], []).append(r)
    ck = list(clusters.keys())
    pt = stat(rows)
    draws = []
    for _ in range(B):
        idx = rng.integers(0, len(ck), len(ck))
        samp = []
        for i in idx:
            samp.extend(clusters[ck[i]])
        v = stat(samp)
        if v is not None and np.isfinite(v):
            draws.append(v)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return pt, lo, hi, len(ck), len(rows)

def mean_gap(rows):
    if not rows:
        return None
    return float(np.mean([r["intl"] - r["fg"] for r in rows]))

def main():
    rows = paired_rows()
    print("TOTAL intl-FG paired player-cycles:", len(rows))
    print("distinct players:", len({r['pk'] for r in rows}))
    byrole = {}
    for r in rows:
        byrole.setdefault(r["role"], []).append(r)
    for role, rs in sorted(byrole.items()):
        print(f"\nROLE={role} n_rows={len(rs)} n_players={len({r['pk'] for r in rs})}")
        pt, lo, hi, nc, nr = boot_cluster(rs, "pk", mean_gap)
        print(f"  mean(intl - fg) = {pt:+.3f}  CI95 [{lo:+.3f}, {hi:+.3f}]  clusters={nc} rows={nr}")
        # per-year
        byyr = {}
        for r in rs:
            byyr.setdefault(r["year"], []).append(r)
        for yr in sorted(byyr):
            v = byyr[yr]
            print(f"    {yr}: n={len(v):4d} gap={mean_gap(v):+7.3f}  "
                  f"intl_mean={np.mean([x['intl'] for x in v]):.2f} fg_mean={np.mean([x['fg'] for x in v]):.2f}")

    # split by whether the player ALSO has a main-pipeline grade that cycle
    print("\n--- SPLIT: does the player also appear on the MAIN Pipeline list that cycle? ---")
    hit = byrole.get("hitter", [])
    for flag in (True, False):
        sub = [r for r in hit if r["has_mp"] == flag]
        if not sub:
            continue
        pt, lo, hi, nc, nr = boot_cluster(sub, "pk", mean_gap)
        label = "ALSO on main list (alias DROPPED)" if flag else "INTL-ONLY (alias RELABELED -> affected pop)"
        print(f"  {label}: n_rows={nr} n_players={nc} gap={pt:+.3f} CI95 [{lo:+.3f}, {hi:+.3f}]")
        if flag:
            g2 = float(np.mean([r["mp"] - r["fg"] for r in sub]))
            g3 = float(np.mean([r["intl"] - r["mp"] for r in sub]))
            print(f"     (same players) main_pipeline - fg = {g2:+.3f} ; intl - main_pipeline = {g3:+.3f}")

    # what the current pipeline offset would be vs the intl offset
    print("\n--- offsets in play ---")
    for yr in (2024, 2025, 2026):
        s, r, p = gn._paired_dists(MP, "hitter", yr)
        s2, r2, p2 = gn._paired_dists(INTL, "hitter", yr)
        print(f"  {yr}: mlb_pipeline off={np.mean(s)-np.mean(r):+.3f} (n={len(s)}, pooled={p}) | "
              f"intl off={np.mean(s2)-np.mean(r2):+.3f} (n={len(s2)}, pooled={p2}) | "
              f"delta={((np.mean(s2)-np.mean(r2))-(np.mean(s)-np.mean(r))):+.3f}")

if __name__ == "__main__":
    main()
