# SCRATCH: express the anchor de-bias in SHIPPED-GATE units (efv_model._run_eval protocol:
# per-side, per-cut, SCORED_YEARS 2020-2023, pooled raw Spearman -- the numbers that live in
# data/xfv_eval.json), plus a gap-multiplier sweep and the live-board impact.
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
import efv_model as E                                        # noqa: E402
import _frontier_anchor_level2 as L                           # noqa: E402
from _frontier_anchor_level2 import ridge_fit, ridge_pred, wols, spear   # noqa: E402

OUT = HERE / "_frontier_out"
SCORED = E.SCORED_YEARS


def load_cut(side, cut):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    raw = json.loads((ROOT / "data" / fn).read_text("utf-8"))
    if cut == "debuted_km":
        rows = [r for r in raw if r["kind"] == "debuted"]
    else:
        rows = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = E._prep(rows, "target_censored", side)
    keys, _m = E._feature_spec(side)
    by = {r["player_key"]: r for r in rows}
    X = np.array([[d["feats"].get(k, 0.0) for k in keys] for d in data], float)
    y = np.array([d["target"] for d in data], float)
    w = np.clip(np.array([float(d.get("weight", 1.0) or 0.0) for d in data]), 1e-3, None)
    fv = np.array([d["fv"] for d in data], float)
    dy = np.array([d["decision_year"] for d in data], int)
    fg = np.array([np.nan if by[d["player_key"]].get("fv_fangraphs") is None
                   else float(by[d["player_key"]]["fv_fangraphs"]) for d in data])
    mp = np.array([np.nan if by[d["player_key"]].get("fv_mlb_pipeline") is None
                   else float(by[d["player_key"]]["fv_mlb_pipeline"]) for d in data])
    return {"X": X, "y": y, "w": w, "fv": fv, "dy": dy, "fg": fg, "mp": mp,
            "ifv": keys.index("fv"), "n": len(data)}


def gate_eval(a, lam, mult=1.0):
    """Shipped-gate protocol: pooled raw Spearman over SCORED_YEARS."""
    C, R, T = [], [], []
    for Y in SCORED:
        tr = np.flatnonzero(a["dy"] < Y)
        te = np.flatnonzero(a["dy"] == Y)
        if len(te) < 15 or len(tr) < 60:
            continue
        both = np.isfinite(a["fg"][tr]) & np.isfinite(a["mp"][tr])
        gap = (float(np.average(a["mp"][tr][both] - a["fg"][tr][both], weights=a["w"][tr][both]))
               if both.sum() >= 25 else 0.0) * mult

        def adj(idx):
            o = np.zeros(len(idx))
            f, m = np.isfinite(a["fg"][idx]), np.isfinite(a["mp"][idx])
            o[f & ~m] = +gap / 2.0
            o[~f & m] = -gap / 2.0
            return a["fv"][idx] + o
        atr, ate = adj(tr), adj(te)
        Xtr, Xte = a["X"][tr].copy(), a["X"][te].copy()
        Xtr[:, a["ifv"]] = atr
        Xte[:, a["ifv"]] = ate
        o = wols(atr, a["y"][tr], a["w"][tr])
        rg = ridge_fit(Xtr, a["y"][tr], a["w"][tr])
        if o is None or rg is None:
            continue
        C.append(np.maximum(0.0, o[0] + o[1] * ate))
        R.append(ridge_pred(rg, Xte))
        T.append(a["y"][te])
    c, r, t = np.concatenate(C), np.concatenate(R), np.concatenate(T)
    b = (1 - lam) * c + lam * r
    return {"n": len(t), "baseline": spear(c, t), "ridge": spear(r, t), "blend": spear(b, t)}


def main():
    t0 = time.time()
    res = {}
    print("=== SHIPPED-GATE UNITS (efv_model._run_eval protocol, SCORED_YEARS 2020-2023,")
    print("    raw pooled Spearman -- the statistic in data/xfv_eval*.json) ===")
    lam = {"hit": E.blend_lambda("hit"), "pit": E.blend_lambda("pit")}
    print("    live blend_lambda:", lam)
    for side in ("hit", "pit"):
        for cut in ("debuted_km", "full_pool_km"):
            a = load_cut(side, cut)
            base = gate_eval(a, lam[side], mult=0.0)
            cand = gate_eval(a, lam[side], mult=1.0)
            print(f"  {side}/{cut} n={base['n']}")
            for leg in ("baseline", "ridge", "blend"):
                print(f"     {leg:9s} shipped {base[leg]:.4f} -> de-biased {cand[leg]:.4f} "
                      f"(d {cand[leg]-base[leg]:+.4f})")
            res.setdefault("gate", {})[f"{side}_{cut}"] = {
                "n": base["n"], "shipped": base, "debias": cand,
                "delta": {k: float(cand[k] - base[k]) for k in ("baseline", "ridge", "blend")}}

    print("\n=== GAP-MULTIPLIER SWEEP (recommended evaluator, both sides pooled blend) ===")
    sides = {s: L.load(s) for s in ("hit", "pit")}
    save = L.anchor

    def mk(mult):
        def f(kind, a, tri, tei, pat_override=None, ridge_pen=1.0):
            if kind == "shipped":
                return a["fv"][tri], a["fv"][tei]
            pat = a["pat"] if pat_override is None else pat_override
            both = np.isfinite(a["fg"][tri]) & np.isfinite(a["mp"][tri])
            ww = a["w"][tri][both]
            gap = (float((ww * (a["mp"][tri][both] - a["fg"][tri][both])).sum() / ww.sum())
                   if both.sum() >= 25 else 0.0) * mult

            def adj(idx):
                o = np.zeros(len(idx))
                o[pat[idx] == "fg_only"] = +gap / 2.0
                o[pat[idx] == "mp_only"] = -gap / 2.0
                return a["fv"][idx] + o
            return adj(tri), adj(tei)
        return f
    for mult in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        L.anchor = mk(mult)
        r = L.evaluate(sides, ["shipped", "pairgap"])
        d = r["pairgap.blend"] - r["shipped.blend"]
        print(f"     mult {mult:4.2f} -> blend {r['pairgap.blend']:.4f} (d {d:+.4f})  "
              f"cons d {r['pairgap.cons']-r['shipped.cons']:+.4f}")
        res.setdefault("mult_sweep", {})[str(mult)] = float(d)
    L.anchor = save

    json.dump(res, open(OUT / "_anchor_gate.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
