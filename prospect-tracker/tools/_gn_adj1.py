# ADJUDICATION LAB 1 -- specification robustness of blastradius TEST A.
# TEST A fits W = a + b*fv + c*is_mp_only with a LINEAR fv term across two groups
# whose fv means differ by ~10 points (FG-only 37.15 vs MP-only 47.19). If the true
# FV->WAR relation is convex, the dummy absorbs curvature and d = -c/b is not an
# offset. Re-derive, then re-fit with (i) a quadratic fv term, (ii) FV fixed effects
# (fully nonparametric in fv), (iii) common-support restriction.
import json, os, sys
from pathlib import Path
import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE)); os.chdir(_HERE)
RNG = np.random.default_rng(20260725)
B = 2000


def load(side):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    rows = json.loads((_HERE / "data" / fn).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        y = r.get("target_censored")
        if y is None:
            y = r.get("target_resolved")
        if y is None:
            continue
        a = r.get("asof_date") or ""
        yr = r.get("debut_year") or (int(a[:4]) if a[:4].isdigit() else None)
        if yr is None:
            continue
        out.append({"fg": r.get("fv_fangraphs"), "mp": r.get("fv_mlb_pipeline"),
                    "y": float(y), "yr": int(yr), "k": r["player_key"]})
    return out


def ols(X, Y):
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    return beta


def d_linear(fv, y, ismp):
    X = np.column_stack([np.ones(len(fv)), fv, ismp])
    b = ols(X, y)
    return (np.nan if abs(b[1]) < 1e-9 else -b[2] / b[1])


def d_quad(fv, y, ismp):
    # local slope evaluated at the pooled mean fv, so d is still in FV units
    z = fv - fv.mean()
    X = np.column_stack([np.ones(len(fv)), z, z ** 2, ismp])
    b = ols(X, y)
    slope = b[1]  # dW/dfv at fv = mean
    return (np.nan if abs(slope) < 1e-9 else -b[3] / slope)


def d_fe(fv, y, ismp, levels):
    # FV fixed effects: fully nonparametric in fv. d is the dummy converted to FV
    # units using the within-FE slope of the fv-level means (estimated on the FG arm).
    cols = [np.ones(len(fv))]
    for lv in levels[1:]:
        cols.append((fv == lv).astype(float))
    cols.append(ismp)
    X = np.column_stack(cols)
    b = ols(X, y)
    c = b[-1]
    # slope from the FE profile itself (regress level effects on level value)
    eff = np.array([0.0] + list(b[1:-1]))
    lv = np.array(levels, float)
    if len(lv) < 3:
        return np.nan
    s = ols(np.column_stack([np.ones(len(lv)), lv]), eff)[1]
    return (np.nan if abs(s) < 1e-9 else -c / s)


def boot(fn, fv, y, ismp, **kw):
    n = len(fv)
    out = np.empty(B)
    for i in range(B):
        idx = RNG.integers(0, n, n)
        try:
            out[i] = fn(fv[idx], y[idx], ismp[idx], **kw)
        except Exception:
            out[i] = np.nan
    return out


for side in ("hit", "pit"):
    rows = load(side)
    fgo = [r for r in rows if r["fg"] is not None and r["mp"] is None]
    mpo = [r for r in rows if r["mp"] is not None and r["fg"] is None]
    fv = np.array([r["fg"] for r in fgo] + [r["mp"] for r in mpo], float)
    y = np.array([r["y"] for r in fgo] + [r["y"] for r in mpo], float)
    ismp = np.array([0.0] * len(fgo) + [1.0] * len(mpo))
    print(f"\n=========== {side.upper()}  n={len(fv)}  FG-only {len(fgo)} MP-only {len(mpo)} ===========")
    print(f"  fv mean FG-only {fv[ismp==0].mean():.2f}  MP-only {fv[ismp==1].mean():.2f}")
    # support overlap
    for lv in sorted(set(fv.tolist())):
        a = int(((fv == lv) & (ismp == 0)).sum()); b_ = int(((fv == lv) & (ismp == 1)).sum())
        print(f"    fv {lv:5.1f}: FG-only {a:4d}  MP-only {b_:4d}"
              + ("   <- MP-only has no FG-only counterpart" if a == 0 and b_ else "")
              + ("   <- FG-only has no MP-only counterpart" if b_ == 0 and a else ""))

    for name, fn, kw in (("LINEAR (the shipped TEST A)", d_linear, {}),
                         ("QUADRATIC fv", d_quad, {})):
        d = fn(fv, y, ismp, **kw)
        bs = boot(fn, fv, y, ismp, **kw)
        lo, hi = np.nanpercentile(bs, [2.5, 97.5])
        print(f"  {name:28s} d = {d:+8.3f}  boot CI95 [{lo:+8.3f}, {hi:+8.3f}]  "
              f"P(d>0) {float(np.nanmean(bs > 0)):.3f}")

    levels = sorted(set(fv.tolist()))
    d = d_fe(fv, y, ismp, levels)
    bs = np.empty(B)
    n = len(fv)
    for i in range(B):
        idx = RNG.integers(0, n, n)
        try:
            bs[i] = d_fe(fv[idx], y[idx], ismp[idx], levels)
        except Exception:
            bs[i] = np.nan
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    print(f"  {'FV FIXED EFFECTS':28s} d = {d:+8.3f}  boot CI95 [{lo:+8.3f}, {hi:+8.3f}]  "
          f"P(d>0) {float(np.nanmean(bs > 0)):.3f}")

    # COMMON SUPPORT: keep only fv levels where BOTH arms have >= 20 rows
    keep = set()
    for lv in levels:
        if ((fv == lv) & (ismp == 0)).sum() >= 20 and ((fv == lv) & (ismp == 1)).sum() >= 20:
            keep.add(lv)
    m = np.array([v in keep for v in fv])
    print(f"  COMMON-SUPPORT levels {sorted(keep)}  n={int(m.sum())} "
          f"(FG {int((ismp[m]==0).sum())} / MP {int((ismp[m]==1).sum())})")
    if m.sum() > 60 and (ismp[m] == 1).sum() > 20 and (ismp[m] == 0).sum() > 20:
        d = d_linear(fv[m], y[m], ismp[m])
        bs = boot(d_linear, fv[m], y[m], ismp[m])
        lo, hi = np.nanpercentile(bs, [2.5, 97.5])
        print(f"  {'LINEAR on common support':28s} d = {d:+8.3f}  boot CI95 "
              f"[{lo:+8.3f}, {hi:+8.3f}]  P(d>0) {float(np.nanmean(bs > 0)):.3f}")
        # per-level mean WAR difference, the assumption-free view
        print("  ASSUMPTION-FREE per-level mean WAR (MP-only minus FG-only at the SAME grade):")
        for lv in sorted(keep):
            a = y[(fv == lv) & (ismp == 0)]; b_ = y[(fv == lv) & (ismp == 1)]
            print(f"    fv {lv:5.1f}: FG-only n={len(a):4d} meanW {a.mean():+6.3f} | "
                  f"MP-only n={len(b_):4d} meanW {b_.mean():+6.3f} | diff {b_.mean()-a.mean():+6.3f}")
