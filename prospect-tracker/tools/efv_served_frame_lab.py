"""C-1d: re-fit the level correction on the frame where the level is actually stated.

Gate: docs/efv-2026-08-13/SERVED_FRAME_REFIT_GATE.md, pre-registered before any
coefficient was fitted on the new frame.

Same family, same estimator, same leave-one-fold-out protocol as the incumbent.
ONLY the fitting frame moves: to rows whose prediction resolves on the outcome
curve rather than landing in its flat region, because a level correction should be
estimated on the population whose level it states.

Usage:  python tools/efv_served_frame_lab.py [B]
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
import efv_score as E            # noqa: E402
import value_framework as vf     # noqa: E402

SIDES = ("hit", "pit")
FLOOR = -2.0
TS = 6
MIN_FRAME_ROWS = 400
ART = ROOT / "data" / "xfv_served_frame_eval.json"


def _fit_affine(rows):
    xs = np.array([r["raw"] for r in rows], float)
    ys = np.array([r["war"] for r in rows], float)
    b = LAB._slope(list(xs), list(ys))
    if b is None or b <= 0:
        return None
    return float(ys.mean() - b * xs.mean()), float(b)


def _loo(rows, frame_fn):
    """Leave-one-fold-out. The correction for fold f is fitted on the FRAME rows of
    every other fold, then applied to ALL rows of fold f, because at serve time the
    map is applied to every player regardless of where the fit came from."""
    folds = sorted({r["fold"] for r in rows})
    out = []
    for f in folds:
        tr = [r for r in rows if r["fold"] != f and frame_fn(r)]
        fit = _fit_affine(tr)
        if fit is None:
            return None
        a, b = fit
        for r in rows:
            if r["fold"] == f:
                out.append(dict(r, corr=max(FLOOR, a + b * r["raw"])))
    return out


def _monotone(a, b, lo=-4.0, hi=20.0, n=4000):
    xs = np.linspace(lo, hi, n)
    v = a + b * xs
    return bool(np.all(np.diff(v) >= -1e-12))


def _served_effect(coef):
    """Clauses 2, 3 and half of 4, on the SERVED board, because that is where the
    defect was seen. The currently-served map is inverted to recover the model WAR,
    then the candidate is applied to it."""
    doc = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))
    cur = E._DISPERSION_CORRECTION
    knot = E._outcome_floor_knot()
    elite, sub45, shrunk_vis, tot_vis = [], [], 0, 0
    for _k, v in doc["by_player"].items():
        if v.get("kind") != "active":
            continue
        w, c = v.get("xfv_war_6yr"), v.get("consensus_fv")
        if w is None or c is None:
            continue
        side = "pit" if v.get("side") == "P" else "hit"
        a0, b0 = cur[side]
        raw = (w - a0) / b0
        a1, b1 = coef[side]
        new_w = max(FLOOR, a1 + b1 * raw)
        g = vf.outcome_implied_fv(new_w, exposure_seasons=TS)
        if g is None:
            continue
        if c >= 45:
            tot_vis += 1
            if new_w < raw - 1e-9:
                shrunk_vis += 1
        if c >= 55:
            elite.append(g - c)
        if c < 45:
            sub45.append(g - c)
    return {
        "elite_n": len(elite),
        "elite_mean": round(float(np.mean(elite)), 4) if elite else None,
        "sub45_mean": round(float(np.mean(sub45)), 4) if sub45 else None,
        "visible_n": tot_vis,
        "visible_shrunk_share": round(shrunk_vis / tot_vis, 4) if tot_vis else None,
        "break_even_war": {s: (round(coef[s][0] / (1 - coef[s][1]), 4)
                               if coef[s][1] < 1 else None) for s in SIDES},
    }


def run(B: int = 2000):
    rng = np.random.default_rng(7)
    pools = {}
    for s in SIDES:
        data = LAB.G.load_side(s)
        pools[s] = LAB._pool(data, M._feature_spec(s)[0], M.SCORED_YEARS)

    frames = {
        "incumbent_full_pool": lambda r: True,
        "restricted_resolves_on_curve": lambda r: r["raw"] > 0.0,
    }
    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
                            .isoformat().replace("+00:00", "Z"),
        "gate": "docs/efv-2026-08-13/SERVED_FRAME_REFIT_GATE.md",
        "B": B, "frames": {},
    }
    for name, fn in frames.items():
        blk = {"per_side": {}}
        coef = {}
        ok = True
        for s in SIDES:
            frame_rows = [r for r in pools[s] if fn(r)]
            if len(frame_rows) < MIN_FRAME_ROWS:
                blk["per_side"][s] = {"abort": f"frame has {len(frame_rows)} rows "
                                               f"< {MIN_FRAME_ROWS}"}
                ok = False
                continue
            whole = _fit_affine(frame_rows)
            if whole is None:
                blk["per_side"][s] = {"abort": "b_c <= 0"}
                ok = False
                continue
            coef[s] = whole
            applied = _loo(pools[s], fn)
            if applied is None:
                blk["per_side"][s] = {"abort": "a fold fit failed"}
                ok = False
                continue
            war = np.array([r["war"] for r in applied], float)
            post = np.array([r["corr"] for r in applied], float)
            pre = np.array([r["xfv_war"] for r in applied], float)
            sel = np.array([fn(r) for r in applied], bool)   # clause 1 frame
            slope = LAB._slope(list(post[sel]), list(war[sel]))
            boot = []
            n = int(sel.sum())
            idxs = np.where(sel)[0]
            for _ in range(B):
                i = idxs[rng.integers(0, n, n)]
                sv = LAB._slope(list(post[i]), list(war[i]))
                if sv is not None:
                    boot.append(sv)
            ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
            blk["per_side"][s] = {
                "frame_n": len(frame_rows),
                "a_c": round(whole[0], 6), "b_c": round(whole[1], 6),
                "slope_on_frame": round(float(slope), 4) if slope else None,
                "slope_ci95": [round(c, 4) for c in ci],
                "covers_1": bool(ci[0] <= 1.0 <= ci[1]),
                "monotone": _monotone(*whole),
                "mae_full_pre": round(float(np.mean(np.abs(war - pre))), 4),
                "mae_full_post": round(float(np.mean(np.abs(war - post))), 4),
                "at_floor_pre": int((pre <= FLOOR + 1e-9).sum()),
                "at_floor_post": int((post <= FLOOR + 1e-9).sum()),
            }
        if ok and len(coef) == 2:
            blk["served"] = _served_effect(coef)
            ps = blk["per_side"]
            sv = blk["served"]
            c1 = all(ps[s]["covers_1"] for s in SIDES)
            c2 = (sv["visible_shrunk_share"] is not None
                  and sv["visible_shrunk_share"] < 0.50)
            c3 = (sv["elite_mean"] is not None and -2.0 <= sv["elite_mean"] <= 2.0)
            c4 = (all(ps[s]["at_floor_post"] < ps[s]["at_floor_pre"] for s in SIDES)
                  and sv["sub45_mean"] is not None and sv["sub45_mean"] >= -10.97)
            c5 = all(ps[s]["monotone"] for s in SIDES)
            blk["clauses"] = {"c1_slope_covers_1": c1, "c2_visible_not_shrunk": c2,
                              "c3_elite_within_2fv": c3, "c4_low_end_retained": c4,
                              "c5_monotone": c5}
            blk["verdict"] = "SHIP" if all([c1, c2, c3, c4, c5]) else "NO_SHIP"
        out["frames"][name] = blk

    ART.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = run(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
    for name, blk in res["frames"].items():
        print(f"\n===== {name} =====")
        for s in SIDES:
            p = blk["per_side"].get(s, {})
            if p.get("abort"):
                print(f"  {s}: ABORT {p['abort']}")
                continue
            print(f"  {s}: frame n={p['frame_n']:5d}  a_c={p['a_c']:.6f} b_c={p['b_c']:.6f}"
                  f"  slope {p['slope_on_frame']} CI{p['slope_ci95']} covers1={p['covers_1']}")
            print(f"        MAE full {p['mae_full_pre']:.4f} -> {p['mae_full_post']:.4f}"
                  f"   floor {p['at_floor_pre']} -> {p['at_floor_post']}")
        sv = blk.get("served")
        if sv:
            print(f"  SERVED: break-even {sv['break_even_war']}")
            print(f"          visible rows (cons>=45) shrunk: "
                  f"{sv['visible_shrunk_share']:.1%} of {sv['visible_n']}")
            print(f"          elite mean {sv['elite_mean']:+.2f} (n={sv['elite_n']})"
                  f"   sub45 mean {sv['sub45_mean']:+.2f}")
        if blk.get("clauses"):
            print("  clauses:", blk["clauses"], "->", blk["verdict"])
