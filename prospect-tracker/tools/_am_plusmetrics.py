# Scratch lab (audit-mode, lane=plusmetrics). NOT a production module.
"""Correlation matrix + coherence checks across the '+' metric family."""
from __future__ import annotations
import json, os, sys, itertools, math
import numpy as np
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")


def load(f):
    with open(os.path.join(D, f), encoding="utf-8") as fh:
        return json.load(fh)


def spear(a, b):
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 8:
        return float("nan"), int(m.sum())
    return float(stats.spearmanr(a[m], b[m]).statistic), int(m.sum())


def matrix(rows, cols, label):
    arr = {c: np.array([_f(r.get(c)) for r in rows]) for c in cols}
    print(f"\n===== {label}  (n rows = {len(rows)}) =====")
    print("coverage:", {c: int((~np.isnan(arr[c])).sum()) for c in cols})
    out = []
    hdr = "                 " + " ".join(f"{c[:9]:>10}" for c in cols)
    print(hdr)
    for c in cols:
        line = f"{c[:16]:<16} "
        for c2 in cols:
            r, n = spear(arr[c], arr[c2])
            line += f"{r:>10.3f}" if r == r else f"{'na':>10}"
            line += " "
            if c < c2:
                out.append((c, c2, r, n))
        print(line)
    print(f"\n-- pairs |rho| >= 0.85 in {label} --")
    for c, c2, r, n in sorted(out, key=lambda t: -abs(t[2]) if t[2] == t[2] else 0):
        if r == r and abs(r) >= 0.85:
            print(f"  {c:<18} {c2:<18} rho={r:+.4f}  n={n}")
    return out


def _f(v):
    try:
        if v is None:
            return float("nan")
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("all", "hit"):
        h = load("hitter_leaderboards.json")["hitters"]
        matrix(h, ["hem_plus", "hem_plus_3yr", "xhem_plus", "fwdhem_plus", "pwoba",
                   "woba", "woba_raw", "xwoba", "ops", "iso", "avg", "obp", "luck_gap"],
               "MLB HITTERS 2026")
        hq = [r for r in h if r.get("qualified")]
        matrix(hq, ["hem_plus", "hem_plus_3yr", "xhem_plus", "fwdhem_plus", "pwoba",
                    "woba", "xwoba", "ops"], "MLB HITTERS 2026 (qualified only)")

    if which in ("all", "sp"):
        s = load("starter_leaderboards.json")["starters"]
        matrix(s, ["sem_plus", "sem_plus_3yr", "xsem_plus", "fip", "era",
                   "k_bb_pct", "k_pct", "bb_pct", "xwoba_against", "hr9", "luck"],
               "MLB STARTERS 2026")
        sq = [r for r in s if r.get("qualified")]
        matrix(sq, ["sem_plus", "sem_plus_3yr", "xsem_plus", "fip", "era", "k_bb_pct"],
               "MLB STARTERS 2026 (qualified only)")

    if which in ("all", "rp"):
        r = load("bullpen_leaderboards.json")["relievers"]
        matrix(r, ["rem_plus", "rem_plus_3yr", "xrem_plus", "riv_plus", "fip", "era",
                   "k_bb_pct", "swstr_pct", "xwoba_against", "wpa", "gmli", "gmli_3yr"],
               "MLB RELIEVERS 2026")
        rq = [x for x in r if x.get("qualified")]
        matrix(rq, ["rem_plus", "rem_plus_3yr", "xrem_plus", "riv_plus", "fip", "era",
                    "k_bb_pct", "swstr_pct"], "MLB RELIEVERS 2026 (qualified only)")
