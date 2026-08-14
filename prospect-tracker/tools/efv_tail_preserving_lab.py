"""C-1b: fit and gate a tail-preserving level correction.

Gate: docs/efv-2026-08-13/TAIL_PRESERVING_REFIT_GATE.md, pre-registered before any
family was fitted.

Three candidate families, declared in advance. The affine incumbent is re-measured
in the SAME run at the same folds so no candidate is ever compared against a stored
figure, and the identity map is carried as a control that MUST fail clause 4.

Usage:  python tools/efv_tail_preserving_lab.py [B]
"""
from __future__ import annotations

import datetime as _dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

_spec = _ilu.spec_from_file_location("_lab", HERE / "efv_dispersion_repair_lab.py")
LAB = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(LAB)

import efv_model as M            # noqa: E402
import value_framework as vf     # noqa: E402

SIDES = ("hit", "pit")
FLOOR = -2.0
TS = 6
ART = ROOT / "data" / "xfv_tail_preserving_eval.json"
ELITE_CONS = 55.0


# ── the declared families ──────────────────────────────────────────────────────
def fam_identity(rows):
    return lambda w: float(w)


def fam_affine(rows):
    """The incumbent. Unweighted OLS of realized on predicted."""
    xs = np.array([r["raw"] for r in rows], float)
    ys = np.array([r["war"] for r in rows], float)
    b = LAB._slope(list(xs), list(ys))
    if b is None or b <= 0:
        return None
    a = float(ys.mean() - b * xs.mean())
    return lambda w, a=a, b=b: a + b * float(w)


def fam_war_weighted(rows):
    """Same family, weighted by 1 + realized WAR so the sparse tail is not outvoted
    by the mass at zero. Weighted least squares, closed form."""
    x = np.array([r["raw"] for r in rows], float)
    y = np.array([r["war"] for r in rows], float)
    w = 1.0 + np.maximum(y, 0.0)
    xm = np.average(x, weights=w)
    ym = np.average(y, weights=w)
    denom = np.sum(w * (x - xm) ** 2)
    if denom <= 0:
        return None
    b = float(np.sum(w * (x - xm) * (y - ym)) / denom)
    if b <= 0:
        return None
    a = float(ym - b * xm)
    return lambda v, a=a, b=b: a + b * float(v)


def fam_isotonic(rows):
    """Isotonic regression of realized on predicted, with LINEAR extrapolation above
    the top fitted knot so the sparse high end is not pinned flat (a flat top would
    tie every elite row and is exactly what clause 3 forbids)."""
    from sklearn.isotonic import IsotonicRegression
    x = np.array([r["raw"] for r in rows], float)
    y = np.array([r["war"] for r in rows], float)
    iso = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(x, y)
    xs = np.sort(np.unique(x))
    ys = iso.predict(xs)
    # slope of the top decile of the fitted curve, for extrapolation
    cut = max(1, int(len(xs) * 0.9))
    x_hi, y_hi = xs[cut:], ys[cut:]
    if len(x_hi) >= 2 and x_hi[-1] > x_hi[0]:
        slope = float((y_hi[-1] - y_hi[0]) / (x_hi[-1] - x_hi[0]))
    else:
        slope = 1.0
    slope = max(slope, 1e-6)
    x_top, y_top = float(xs[-1]), float(ys[-1])

    def f(v, iso=iso, x_top=x_top, y_top=y_top, slope=slope):
        v = float(v)
        if v <= x_top:
            return float(iso.predict([v])[0])
        return y_top + slope * (v - x_top)
    return f


def fam_quantile_pl(rows):
    """Monotone piecewise-linear on prediction deciles, top slope constrained >= 1
    so the map cannot shrink the top."""
    x = np.array([r["raw"] for r in rows], float)
    y = np.array([r["war"] for r in rows], float)
    qs = np.quantile(x, np.linspace(0, 1, 11))
    qs = np.unique(qs)
    if len(qs) < 3:
        return None
    knots_y = []
    for i in range(len(qs)):
        lo = qs[max(0, i - 1)]
        hi = qs[min(len(qs) - 1, i + 1)]
        sel = (x >= lo) & (x <= hi)
        knots_y.append(float(y[sel].mean()) if sel.any() else float(y.mean()))
    # enforce strict monotonicity
    for i in range(1, len(knots_y)):
        if knots_y[i] <= knots_y[i - 1]:
            knots_y[i] = knots_y[i - 1] + 1e-6
    ky = np.array(knots_y, float)
    top_slope = (ky[-1] - ky[-2]) / (qs[-1] - qs[-2]) if qs[-1] > qs[-2] else 1.0
    top_slope = max(float(top_slope), 1.0)          # clause-3 guard, declared

    def f(v, qs=qs, ky=ky, top_slope=top_slope):
        v = float(v)
        if v >= qs[-1]:
            return float(ky[-1] + top_slope * (v - qs[-1]))
        if v <= qs[0]:
            lo_slope = (ky[1] - ky[0]) / (qs[1] - qs[0]) if qs[1] > qs[0] else 1.0
            return float(ky[0] + lo_slope * (v - qs[0]))
        return float(np.interp(v, qs, ky))
    return f


FAMILIES = {
    "identity": fam_identity,
    "affine_incumbent": fam_affine,
    "war_weighted_affine": fam_war_weighted,
    "isotonic_lin_extrap": fam_isotonic,
    "quantile_piecewise": fam_quantile_pl,
}


# ── evaluation ─────────────────────────────────────────────────────────────────
def _loo_apply(rows, builder):
    """Leave-one-fold-out: for scored fold f, fit on every OTHER fold."""
    folds = sorted({r["fold"] for r in rows})
    out = []
    for f in folds:
        tr = [r for r in rows if r["fold"] != f]
        fn = builder(tr)
        if fn is None:
            return None
        for r in rows:
            if r["fold"] == f:
                out.append(dict(r, corr=max(FLOOR, fn(r["raw"]))))
    return out


def _monotone(fn, lo=-4.0, hi=20.0, n=4000):
    xs = np.linspace(lo, hi, n)
    prev = None
    for x in xs:
        v = fn(x)
        if prev is not None and v < prev - 1e-9:
            return False
        prev = v
    return True


def _stat(rows, B, rng):
    war = np.array([r["war"] for r in rows], float)
    post = np.array([r["corr"] for r in rows], float)
    pre = np.array([r["xfv_war"] for r in rows], float)
    cut = np.percentile(war, 90)
    tail = war >= cut
    slope = LAB._slope(list(post), list(war))
    boot = []
    n = len(rows)
    for _ in range(B):
        idx = rng.integers(0, n, n)
        s = LAB._slope(list(post[idx]), list(war[idx]))
        if s is not None:
            boot.append(s)
    ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))] if boot else [None, None]
    return {
        "n": n,
        "slope_pre": round(float(LAB._slope(list(pre), list(war))), 4),
        "slope_post": round(float(slope), 4) if slope else None,
        "slope_ci95": [round(c, 4) if c is not None else None for c in ci],
        "covers_1": bool(ci[0] is not None and ci[0] <= 1.0 <= ci[1]),
        "mae_pre": round(float(np.mean(np.abs(war - pre))), 4),
        "mae_post": round(float(np.mean(np.abs(war - post))), 4),
        "tail_mae_pre": round(float(np.mean(np.abs(war[tail] - pre[tail]))), 4),
        "tail_mae_post": round(float(np.mean(np.abs(war[tail] - post[tail]))), 4),
        "tail_n": int(tail.sum()),
        "at_floor_pre": int((pre <= FLOOR + 1e-9).sum()),
        "at_floor_post": int((post <= FLOOR + 1e-9).sum()),
    }


def _served_effect(fn_by_side):
    """Clause 3 and half of clause 4, measured on the SERVED board, because that is
    where the defect was found."""
    doc = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))
    import efv_score as E
    A = E._DISPERSION_CORRECTION
    elite, sub45 = [], []
    for _k, v in doc["by_player"].items():
        if v.get("kind") != "active":
            continue
        w, c = v.get("xfv_war_6yr"), v.get("consensus_fv")
        if w is None or c is None:
            continue
        side = "pit" if v.get("side") == "P" else "hit"
        a_c, b_c = A[side]
        raw = (w - a_c) / b_c                       # invert what is currently served
        g = vf.outcome_implied_fv(max(FLOOR, fn_by_side[side](raw)), exposure_seasons=TS)
        if g is None:
            continue
        d = g - c
        if c >= ELITE_CONS:
            elite.append(d)
        if c < 45:
            sub45.append(d)
    return {
        "elite_n": len(elite),
        "elite_mean_efv_minus_cons": round(float(np.mean(elite)), 4) if elite else None,
        "sub45_n": len(sub45),
        "sub45_mean_efv_minus_cons": round(float(np.mean(sub45)), 4) if sub45 else None,
    }


def run(B: int = 500):
    rng = np.random.default_rng(7)
    pools = {}
    for s in SIDES:
        data = LAB.G.load_side(s)
        keys = M._feature_spec(s)[0]
        pools[s] = LAB._pool(data, keys, M.SCORED_YEARS)

    # generated_at is REQUIRED, not decoration. model_registry.freshness() ages an
    # undated artifact by file mtime, and the deploy box rewrites every mtime on its
    # nightly `git checkout -- .`, so the age it would report there is the checkout
    # rather than the measurement.
    out = {"generated_at": _dt.datetime.now(_dt.timezone.utc)
                              .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
           "gate": "docs/efv-2026-08-13/TAIL_PRESERVING_REFIT_GATE.md",
           "B": B, "families": {}}

    for name, builder in FAMILIES.items():
        fam = {"per_side": {}, "monotone": {}}
        fns = {}
        ok = True
        for s in SIDES:
            applied = _loo_apply(pools[s], builder)
            if applied is None:
                ok = False
                break
            fam["per_side"][s] = _stat(applied, B, rng)
            whole = builder(pools[s])
            fns[s] = whole
            fam["monotone"][s] = bool(_monotone(whole))
        if not ok:
            out["families"][name] = {"error": "fit failed"}
            continue
        fam["served"] = _served_effect(fns)

        c1 = all(fam["per_side"][s]["covers_1"] for s in SIDES)
        c2 = all(fam["per_side"][s]["tail_mae_post"] <= fam["per_side"][s]["tail_mae_pre"] + 1e-9
                 for s in SIDES)
        c3 = (fam["served"]["elite_mean_efv_minus_cons"] is not None
              and fam["served"]["elite_mean_efv_minus_cons"] >= 0.0)
        c4 = (all(fam["per_side"][s]["at_floor_post"] < fam["per_side"][s]["at_floor_pre"]
                  for s in SIDES)
              and fam["served"]["sub45_mean_efv_minus_cons"] is not None
              and fam["served"]["sub45_mean_efv_minus_cons"] > -10.97)
        mono = all(fam["monotone"].values())
        fam["clauses"] = {"c1_slope_covers_1": c1, "c2_tail_mae_not_worse": c2,
                          "c3_elite_not_inverted": c3, "c4_low_end_retained": c4,
                          "monotone": mono}
        fam["verdict"] = "SHIP" if (c1 and c2 and c3 and c4 and mono) else "NO_SHIP"
        out["families"][name] = fam

    ART.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    res = run(B)
    print(f"{'family':24s} {'c1':>4s} {'c2':>4s} {'c3':>4s} {'c4':>4s} {'mono':>5s}  verdict")
    for name, f in res["families"].items():
        if "clauses" not in f:
            print(f"{name:24s}  {f.get('error')}")
            continue
        c = f["clauses"]
        print(f"{name:24s} {str(c['c1_slope_covers_1'])[:4]:>4s} "
              f"{str(c['c2_tail_mae_not_worse'])[:4]:>4s} "
              f"{str(c['c3_elite_not_inverted'])[:4]:>4s} "
              f"{str(c['c4_low_end_retained'])[:4]:>4s} "
              f"{str(c['monotone'])[:5]:>5s}  {f['verdict']}")
        s = f["served"]
        print(f"{'':24s}   elite(n={s['elite_n']}) {s['elite_mean_efv_minus_cons']:+.2f}   "
              f"sub45 {s['sub45_mean_efv_minus_cons']:+.2f}   "
              f"tailMAE hit {f['per_side']['hit']['tail_mae_pre']:.2f}->"
              f"{f['per_side']['hit']['tail_mae_post']:.2f}")
