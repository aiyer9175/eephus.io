# SCRATCH (not shipped): cross-time-split stability of the audited eFV deltas.
# Method item 4: average the effect over MULTIPLE time splits, not one.
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                     # noqa: E402
import _frontier_noisefloor as F          # noqa: E402

AUDIT = {"hit": ["age", "ops_rel", "level_rank"], "pit": ["age", "x_era_k"]}


def fold_years(dy):
    yrs = sorted(set(int(v) for v in dy))
    ok = []
    for y in yrs:
        ntr = int((dy < y).sum())
        nte = int((dy == y).sum())
        if nte >= 15 and ntr >= 60:
            ok.append((y, ntr, nte))
    return ok


def one_fold(X, y, w, fv, dy, yr, lam, cols):
    tr = np.flatnonzero(dy < yr)
    te = np.flatnonzero(dy == yr)
    ols = F.ols_fit(fv[tr], y[tr])
    rg = F.ridge_fit(X[tr][:, cols], y[tr], w[tr])
    if ols is None or rg is None:
        return None
    c = np.maximum(0.0, ols[0] + ols[1] * fv[te])
    r = F.ridge_pred(rg, X[te][:, cols])
    b = (1 - lam) * c + lam * r
    tier = np.round(fv[te] / 5) * 5
    m45 = tier == 45
    return {"rho": F.spear(b, y[te]), "rho_ridge": F.spear(r, y[te]),
            "rho_cons": F.spear(c, y[te]),
            "t45": F.spear(b[m45], y[te][m45]) if m45.sum() >= 15 else np.nan,
            "n": len(te), "n45": int(m45.sum())}


def main():
    for side in ("hit", "pit"):
        keys, _ = E._feature_spec(side)
        lam = E.blend_lambda(side)
        kidx = {k: i for i, k in enumerate(keys)}
        full = np.arange(len(keys))
        for cut in ("debuted_km",):
            data = F.load(side, cut)
            X, y, w, fv, dy = F.arrays(data, keys)
            fy = fold_years(dy)
            print(f"\n### {side}/{cut} lam={lam}  eligible folds: "
                  + ", ".join(f"{a}(tr{b}/te{c})" for a, b, c in fy))
            rows = {}
            for yr, _a, _b in fy:
                base = one_fold(X, y, w, fv, dy, yr, lam, full)
                if base is None:
                    continue
                rec = {"n": base["n"], "n45": base["n45"], "rho": base["rho"],
                       "d_vs_cons": base["rho"] - base["rho_cons"],
                       "d_ridge_vs_cons": base["rho_ridge"] - base["rho_cons"]}
                for f in AUDIT[side]:
                    if f not in kidx:
                        continue
                    cols = np.array([i for i in full if i != kidx[f]])
                    red = one_fold(X, y, w, fv, dy, yr, lam, cols)
                    if red:
                        rec[f"d_{f}"] = base["rho"] - red["rho"]
                        rec[f"d45_{f}"] = base["t45"] - red["t45"]
                rows[yr] = rec
            hdr = ["year", "n", "n45", "rho", "d_vs_cons"] + \
                  [f"d_{f}" for f in AUDIT[side] if f in kidx] + \
                  [f"d45_{f}" for f in AUDIT[side] if f in kidx]
            print("  " + "  ".join(f"{h:>13s}" for h in hdr))
            for yr, rec in rows.items():
                cells = [f"{yr:>13d}", f"{rec['n']:>13d}", f"{rec['n45']:>13d}"]
                for h in hdr[3:]:
                    v = rec.get(h, np.nan)
                    cells.append(f"{v:>13.4f}" if np.isfinite(v) else f"{'na':>13s}")
                print("  " + "  ".join(cells))
            # cross-split mean +/- se
            print("  cross-split mean (se) over folds:")
            for h in hdr[3:]:
                v = np.array([rows[y].get(h, np.nan) for y in rows], dtype=float)
                v = v[np.isfinite(v)]
                if len(v) < 2:
                    continue
                se = v.std(ddof=1) / np.sqrt(len(v))
                print(f"    {h:>16s} mean {v.mean():+.4f}  se {se:.4f}  "
                      f"t {v.mean()/se if se else float('nan'):+.2f}  "
                      f"signs {'/'.join('+' if x > 0 else '-' for x in v)}")


if __name__ == "__main__":
    main()
