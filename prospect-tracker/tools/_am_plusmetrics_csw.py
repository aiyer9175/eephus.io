# Scratch lab (audit-mode, lane=plusmetrics), item (e).
"""Does data/milb_pitch_rates.json (CSW%/SwStr%) improve a '+'-family pitcher
index that carries NO strikeout term?

The only '+' metric on the MiLB pitcher population without a K term is the
level-relative run-prevention index (RPS+ pitcher / the era_rel leg of KRP+).
KRP+ itself is (-era_rel)*k_rel, so it is EXCLUDED by the brief's own logic.

M0  = -era_rel                        (no-K run prevention, the RPS+-pitcher analog)
M1  = M0 + k_rel                      (what KRP+ effectively adds)
M2  = M0 + csw_rel                    (the candidate: CSW instead of K)
M3  = M0 + k_rel + csw_rel            (does CSW add ON TOP of K?)
CTRL= M0 + row-permuted csw_rel       (zero-information twin, same marginal)

Target: target_resolved (eFV pitcher label, career WAR through the served window).
Forward-chained on milb_season. Paired bootstrap resamples TRAIN and TEST with a
refit per draw. Permutation null band on the candidate column.
"""
from __future__ import annotations
import json, os, sys, math
import numpy as np
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
RNG = np.random.default_rng(20260725)

COMPLEX = {"DSL", "CPX", "R", "Rk", "ROK", "FCL", "ACL"}     # pre-2025 logs biased


def build():
    rows = json.load(open(os.path.join(D, "xfv_pitcher_matrix.json"), encoding="utf-8"))
    feat = json.load(open(os.path.join(D, "milb_pitch_rates.json"), encoding="utf-8"))["features"]
    out = []
    for r in rows:
        m = r.get("milb") or {}
        mid, s, lv = r.get("mlbam_id"), m.get("milb_season"), m.get("milb_level")
        if mid is None or s is None or not lv:
            continue
        if str(lv) in COMPLEX:
            continue
        f = feat.get(f"{int(mid)}|{int(s)}|{lv}")
        if not f:
            continue
        if m.get("era_rel") is None or m.get("k_rel") is None:
            continue
        if float(m.get("rates_missing", 1.0) or 0.0) != 0.0:
            continue
        out.append({
            "season": int(s), "level": str(lv),
            "y": float(r["target_resolved"]),
            "era_rel": float(m["era_rel"]),
            "k_rel": float(m["k_rel"]),
            "bb_rel": float(m.get("bb_rel") or 0.0),
            "csw_rel": float(f["csw_rel"]),
            "swstr_rel": float(f["swstr_rel"]),
            "shrink_w": float(f.get("shrink_w") or 1.0),
        })
    return out


def _fit_predict(Xtr, ytr, Xte, lam=1.0):
    """Ridge with standardized columns + intercept."""
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd = np.where(sd <= 0, 1.0, sd)
    A = (Xtr - mu) / sd
    B = (Xte - mu) / sd
    ybar = ytr.mean()
    p = A.shape[1]
    w = np.linalg.solve(A.T @ A + lam * np.eye(p), A.T @ (ytr - ybar))
    return B @ w + ybar


SPECS = {
    "M0 -era_rel (no K)": ["era_rel"],
    "M1 +k_rel":          ["era_rel", "k_rel"],
    "M2 +csw_rel":        ["era_rel", "csw_rel"],
    "M2b +swstr_rel":     ["era_rel", "swstr_rel"],
    "M3 +k_rel+csw_rel":  ["era_rel", "k_rel", "csw_rel"],
}


def cols(rows, names, perm_idx=None, perm_col=None):
    X = np.column_stack([np.array([r[n] for r in rows]) for n in names])
    if perm_col is not None and perm_col in names:
        j = names.index(perm_col)
        X[:, j] = X[perm_idx, j]
    return X


def forward_folds(data, test_seasons):
    for t in test_seasons:
        tr = [r for r in data if r["season"] < t]
        te = [r for r in data if r["season"] == t]
        if len(tr) >= 60 and len(te) >= 40:
            yield t, tr, te


def run_once(tr, te, names, perm_col=None, rng=None):
    ptr = None
    if perm_col:
        ptr = (rng or RNG).permutation(len(tr))
    Xtr = cols(tr, names, ptr, perm_col)
    ytr = np.array([r["y"] for r in tr])
    pte = (rng or RNG).permutation(len(te)) if perm_col else None
    Xte = cols(te, names, pte, perm_col)
    yte = np.array([r["y"] for r in te])
    pred = _fit_predict(Xtr, ytr, Xte)
    return float(stats.spearmanr(pred, yte).statistic)


if __name__ == "__main__":
    data = build()
    import collections
    print(f"joined rows (non-complex, rates present): {len(data)}")
    print("by season:", sorted(collections.Counter(r['season'] for r in data).items()))
    print("by level :", sorted(collections.Counter(r['level'] for r in data).items()))
    x = np.array([r["csw_rel"] for r in data]); k = np.array([r["k_rel"] for r in data])
    sw = np.array([r["swstr_rel"] for r in data]); er = np.array([r["era_rel"] for r in data])
    print(f"\ncollinearity on THIS pool  n={len(data)}")
    print(f"  rho(csw_rel , k_rel)   = {stats.spearmanr(x,k).statistic:+.4f}")
    print(f"  rho(swstr_rel, k_rel)  = {stats.spearmanr(sw,k).statistic:+.4f}")
    print(f"  rho(csw_rel , era_rel) = {stats.spearmanr(x,er).statistic:+.4f}")
    print(f"  rho(k_rel   , era_rel) = {stats.spearmanr(k,er).statistic:+.4f}")

    TEST = [2019, 2021, 2022, 2023]
    folds = list(forward_folds(data, TEST))
    print(f"\nforward-chained folds: {[(t, len(tr), len(te)) for t, tr, te in folds]}")

    print("\n--- per-fold OOS Spearman (pred vs realized WAR label) ---")
    hdr = f"{'model':<22}" + "".join(f"{t:>9}" for t, _, _ in folds) + f"{'MEAN':>10}"
    print(hdr)
    base = {}
    for lab, names in SPECS.items():
        vals = [run_once(tr, te, names) for _, tr, te in folds]
        base[lab] = vals
        print(f"{lab:<22}" + "".join(f"{v:>9.4f}" for v in vals) + f"{np.mean(vals):>10.4f}")
    # zero-information control: csw_rel row-permuted
    ctrl = [run_once(tr, te, SPECS["M2 +csw_rel"], perm_col="csw_rel") for _, tr, te in folds]
    print(f"{'CTRL M0+perm(csw)':<22}" + "".join(f"{v:>9.4f}" for v in ctrl) + f"{np.mean(ctrl):>10.4f}")

    # ---- paired bootstrap (resample TRAIN and TEST, refit each draw) --------
    B = 600
    print(f"\n--- paired bootstrap, B={B}, resampling TRAIN and TEST with refit ---")
    for cand, ref in [("M2 +csw_rel", "M0 -era_rel (no K)"),
                      ("M1 +k_rel", "M0 -era_rel (no K)"),
                      ("M3 +k_rel+csw_rel", "M1 +k_rel"),
                      ("M2b +swstr_rel", "M0 -era_rel (no K)")]:
        gaps = []
        for b in range(B):
            g = []
            for _, tr, te in folds:
                itr = RNG.integers(0, len(tr), len(tr))
                ite = RNG.integers(0, len(te), len(te))
                trb = [tr[i] for i in itr]; teb = [te[i] for i in ite]
                try:
                    g.append(run_once(trb, teb, SPECS[cand]) - run_once(trb, teb, SPECS[ref]))
                except Exception:
                    pass
            if g:
                gaps.append(float(np.mean(g)))
        gaps = np.array(gaps)
        obs = np.mean(base[cand]) - np.mean(base[ref])
        print(f"  {cand:<20} vs {ref:<20} obs {obs:+.4f}  "
              f"boot mean {gaps.mean():+.4f}  lo95 {np.percentile(gaps,2.5):+.4f}  "
              f"hi95 {np.percentile(gaps,97.5):+.4f}  P(>0)={float((gaps>0).mean()):.3f}")

    # ---- permutation null band for the csw add ------------------------------
    P = 600
    print(f"\n--- permutation null band, P={P} (csw_rel row-permuted, same marginal) ---")
    null = []
    for p in range(P):
        v = [run_once(tr, te, SPECS["M2 +csw_rel"], perm_col="csw_rel") for _, tr, te in folds]
        null.append(np.mean(v) - np.mean(base["M0 -era_rel (no K)"]))
    null = np.array(null)
    obs = np.mean(base["M2 +csw_rel"]) - np.mean(base["M0 -era_rel (no K)"])
    print(f"  observed csw add   = {obs:+.4f}")
    print(f"  null mean {null.mean():+.4f}  p50 {np.percentile(null,50):+.4f}  "
          f"p95 {np.percentile(null,95):+.4f}  p99 {np.percentile(null,99):+.4f}")
    print(f"  MDE95 (null p95 as the floor) = {np.percentile(null,95):+.4f}")
    print(f"  permutation p-value = {float((null >= obs).mean()):.4f}")
